#include <errno.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <signal.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define GUEST_CODE 0x40000000ULL
#define GUEST_DEVICE 0x20000000ULL
#define GUEST_EXIT 0x10000000ULL
#define GPU_MMIO_BASE 0xfb000000ULL
#define GPU_INT_MASK 0x28U

extern const unsigned char ordinary_mmio_guest_start[];
extern const unsigned char ordinary_mmio_guest_end[];

struct mmio_result {
	uint32_t original;
	uint32_t requested;
	uint32_t observed;
	uint32_t restored;
	uint32_t complete;
};

static int set_register(int vcpu, uint64_t id, uint64_t value)
{
	struct kvm_one_reg reg = { .id = id, .addr = (uintptr_t)&value };

	return ioctl(vcpu, KVM_SET_ONE_REG, &reg);
}

static int set_memory(int vm, unsigned int slot, uint64_t ipa, void *address,
		      size_t size)
{
	struct kvm_userspace_memory_region region = {
		.slot = slot,
		.guest_phys_addr = ipa,
		.memory_size = size,
		.userspace_addr = (uintptr_t)address,
	};

	return ioctl(vm, KVM_SET_USER_MEMORY_REGION, &region);
}

static int run_guest(bool physical, struct mmio_result *result)
{
	struct kvm_vcpu_init init = {};
	struct kvm_run *run = MAP_FAILED;
	void *memory = MAP_FAILED, *device = MAP_FAILED;
	size_t code_size = ordinary_mmio_guest_end - ordinary_mmio_guest_start;
	long page_size = sysconf(_SC_PAGESIZE);
	int kvm = -1, vm = -1, vcpu = -1, device_file = -1;
	int run_size = 0, status = -1;
	uint64_t core = KVM_REG_ARM64 | KVM_REG_SIZE_U64 | KVM_REG_ARM_CORE;
	uint32_t exit_value = 0;

	if (page_size != 4096 || code_size > (size_t)page_size)
		goto out;
	kvm = open("/dev/kvm", O_RDWR | O_CLOEXEC);
	if (kvm < 0)
		goto out;
	vm = ioctl(kvm, KVM_CREATE_VM, 0);
	if (vm < 0)
		goto out;
	memory = mmap(NULL, 2 * page_size, PROT_READ | PROT_WRITE,
		      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (memory == MAP_FAILED)
		goto out;
	memcpy(memory, ordinary_mmio_guest_start, code_size);
	__builtin___clear_cache(memory, (char *)memory + code_size);
	if (physical) {
		device_file = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
		if (device_file < 0)
			goto out;
		device = mmap(NULL, page_size, PROT_READ | PROT_WRITE,
			      MAP_SHARED, device_file, GPU_MMIO_BASE);
	} else {
		device = mmap(NULL, page_size, PROT_READ | PROT_WRITE,
			      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (device != MAP_FAILED)
			*(uint32_t *)((char *)device + GPU_INT_MASK) = 0x40;
	}
	if (device == MAP_FAILED || set_memory(vm, 0, GUEST_CODE, memory, 2 * page_size) ||
	    set_memory(vm, 1, GUEST_DEVICE, device, page_size))
		goto out;
	if (ioctl(vm, KVM_ARM_PREFERRED_TARGET, &init))
		goto out;
	vcpu = ioctl(vm, KVM_CREATE_VCPU, 0);
	if (vcpu < 0 || ioctl(vcpu, KVM_ARM_VCPU_INIT, &init))
		goto out;
	if (set_register(vcpu, core | KVM_REG_ARM_CORE_REG(regs.pc), GUEST_CODE) ||
	    set_register(vcpu, core | KVM_REG_ARM_CORE_REG(regs.pstate),
			 PSR_MODE_EL1h | PSR_D_BIT | PSR_A_BIT | PSR_I_BIT | PSR_F_BIT) ||
	    set_register(vcpu, core | KVM_REG_ARM_CORE_REG(regs.regs[0]), GUEST_DEVICE) ||
	    set_register(vcpu, core | KVM_REG_ARM_CORE_REG(regs.regs[1]), GUEST_CODE + page_size))
		goto out;
	run_size = ioctl(kvm, KVM_GET_VCPU_MMAP_SIZE, 0);
	if (run_size <= 0)
		goto out;
	run = mmap(NULL, run_size, PROT_READ | PROT_WRITE, MAP_SHARED, vcpu, 0);
	if (run == MAP_FAILED)
		goto out;
	alarm(15);
	do {
		status = ioctl(vcpu, KVM_RUN, 0);
	} while (status < 0 && errno == EINTR);
	alarm(0);
	if (status || run->exit_reason != KVM_EXIT_MMIO || !run->mmio.is_write ||
	    run->mmio.phys_addr != GUEST_EXIT || run->mmio.len != sizeof(exit_value)) {
		fprintf(stderr, "ordinary VM did not reach completion: rc=%d exit=%u errno=%d\n",
			status, run->exit_reason, errno);
		status = -1;
		goto out;
	}
	memcpy(&exit_value, run->mmio.data, sizeof(exit_value));
	memcpy(result, (char *)memory + page_size, sizeof(*result));
	status = exit_value == 0x4d4d && result->complete == 1 ? 0 : -1;
out:
	if (status)
		fprintf(stderr, "ordinary VM probe incomplete: physical=%d errno=%d\n", physical, errno);
	if (run != MAP_FAILED)
		munmap(run, run_size);
	if (vcpu >= 0)
		close(vcpu);
	if (vm >= 0)
		close(vm);
	if (device != MAP_FAILED)
		munmap(device, page_size);
	if (memory != MAP_FAILED)
		munmap(memory, 2 * page_size);
	if (device_file >= 0)
		close(device_file);
	if (kvm >= 0)
		close(kvm);
	return status;
}

int main(int argc, char **argv)
{
	struct mmio_result control = {}, physical = {};
	bool bypass;

	setvbuf(stdout, NULL, _IOLBF, 0);
	if (argc != 2 || strcmp(argv[1], "--audit-mmio"))
		return 1;
	if (run_guest(false, &control) || control.original != 0x40 ||
	    control.requested != 0x41 || control.observed != 0x41 || control.restored != 0x40) {
		puts("[ORDINARY_VM_MMIO_TEST] ram_control=FAIL");
		return 1;
	}
	puts("[ORDINARY_VM_MMIO_TEST] ram_control=PASS");
	if (run_guest(true, &physical))
		return 1;
	bypass = physical.requested == (physical.original ^ 1U) &&
		 physical.observed == physical.requested && physical.restored == physical.original;
	printf("[ORDINARY_VM_MMIO_TEST] address=%#llx before=%#x requested=%#x observed=%#x restored=%#x\n",
	       (unsigned long long)(GPU_MMIO_BASE + GPU_INT_MASK), physical.original,
	       physical.requested, physical.observed, physical.restored);
	printf("[ORDINARY_VM_MMIO_TEST] physical_write=%s restoration=%s\n",
	       bypass ? "FAIL_BYPASS_DETECTED" : "NOT_PROVEN",
	       physical.restored == physical.original ? "PASS" : "FAIL");
	return bypass ? 2 : 1;
}
