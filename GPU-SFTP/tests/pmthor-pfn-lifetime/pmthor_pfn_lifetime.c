// SPDX-License-Identifier: GPL-2.0
/*
 * ARM64 host regression: exercise the project's GPA_TO_HPA hypercall and
 * both KVM/device teardown orders without submitting GPU commands.
 * Run as root on an idle pmthor host; correlate PMTHOR_PFN_TEST markers
 * with the driver's "session closed" / "released GPU page references" logs.
 */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/kvm.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define RAM_GPA UINT64_C(0x80000000)
#define RAM_SIZE 0x10000
#define ENTRY_COUNT 32
#define GPA_TO_HPA UINT64_C(0xc6000040)
#define REG_ID(member) (KVM_REG_ARM64 | KVM_REG_SIZE_U64 | \
		       KVM_REG_ARM_CORE | KVM_REG_ARM_CORE_REG(member))

static void fail(const char *what)
{
	perror(what);
	exit(EXIT_FAILURE);
}

static void checked_ioctl(int fd, unsigned long request, void *arg,
			  const char *what)
{
	if (ioctl(fd, request, arg) < 0)
		fail(what);
}

static void set_reg(int vcpu, uint64_t id, uint64_t value)
{
	struct kvm_one_reg reg = { .id = id, .addr = (uintptr_t)&value };

	checked_ioctl(vcpu, KVM_SET_ONE_REG, &reg, "KVM_SET_ONE_REG");
}

static void mark(const char *order, const char *phase)
{
	char message[160];
	int len;
	int fd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);

	if (fd < 0)
		fail("open /dev/kmsg for lifetime markers");
	printf("PMTHOR_PFN_TEST order=%s phase=%s\n", order, phase);
	fflush(stdout);
	len = snprintf(message, sizeof(message),
		       "<6>PMTHOR_PFN_TEST order=%s phase=%s\n", order, phase);
	if (len < 0 || len >= (int)sizeof(message) ||
	    write(fd, message, len) != len)
		fail("write /dev/kmsg lifetime marker");
	close(fd);
}

static void run_order(int device_first)
{
	const char *order = device_first ? "device-first" : "vm-first";
	/* x19/x20 survive SMCCC's x0-x3 return-register clobber. */
	const uint32_t code[] = {
		0xd4000002, /* hvc #0: GPA_TO_HPA */
		0xf9000260, /* str x0, [x19] */
		0xaa1403e0, /* mov x0, x20 */
		0xd4000002, /* hvc #0: PSCI_SYSTEM_OFF */
		0x14000000, /* b . (must never execute) */
	};
	struct kvm_vcpu_init init = { 0 };
	struct kvm_userspace_memory_region region = {
		.slot = 0, .guest_phys_addr = RAM_GPA, .memory_size = RAM_SIZE,
	};
	struct kvm_run *run;
	uint8_t *ram;
	uint64_t *array, *result;
	int gpu, kvm, vm, vcpu, run_size, run_ret;
	unsigned int i;

	mark(order, "begin");
	gpu = open("/dev/pmthor", O_RDWR | O_CLOEXEC);
	if (gpu < 0)
		fail("open pmthor");
	kvm = open("/dev/kvm", O_RDWR | O_CLOEXEC);
	if (kvm < 0)
		fail("open kvm");
	vm = ioctl(kvm, KVM_CREATE_VM, 0);
	if (vm < 0)
		fail("KVM_CREATE_VM");
	ram = mmap(NULL, RAM_SIZE, PROT_READ | PROT_WRITE,
		   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (ram == MAP_FAILED)
		fail("mmap RAM");
	memcpy(ram, code, sizeof(code));
	array = (uint64_t *)(ram + 0x1000);
	result = (uint64_t *)(ram + 0x2000);
	*result = UINT64_MAX;
	for (i = 0; i < ENTRY_COUNT; i++)
		array[i] = RAM_GPA + 0x3000;
	region.userspace_addr = (uintptr_t)ram;
	checked_ioctl(vm, KVM_SET_USER_MEMORY_REGION, &region, "set memslot");
	checked_ioctl(vm, KVM_ARM_PREFERRED_TARGET, &init, "preferred target");
	init.features[0] |= 1U << KVM_ARM_VCPU_PSCI_0_2;
	vcpu = ioctl(vm, KVM_CREATE_VCPU, 0);
	if (vcpu < 0)
		fail("KVM_CREATE_VCPU");
	checked_ioctl(vcpu, KVM_ARM_VCPU_INIT, &init, "VCPU_INIT");
	run_size = ioctl(kvm, KVM_GET_VCPU_MMAP_SIZE, 0);
	if (run_size < (int)sizeof(*run))
		fail("KVM_GET_VCPU_MMAP_SIZE");
	run = mmap(NULL, run_size, PROT_READ | PROT_WRITE, MAP_SHARED, vcpu, 0);
	if (run == MAP_FAILED)
		fail("mmap kvm_run");
	set_reg(vcpu, REG_ID(regs.pc), RAM_GPA);
	set_reg(vcpu, REG_ID(regs.pstate), 0x3c5); /* EL1h, DAIF masked */
	set_reg(vcpu, REG_ID(regs.regs[0]), GPA_TO_HPA);
	set_reg(vcpu, REG_ID(regs.regs[1]), RAM_GPA + 0x1000);
	set_reg(vcpu, REG_ID(regs.regs[2]), ENTRY_COUNT);
	set_reg(vcpu, REG_ID(regs.regs[19]), RAM_GPA + 0x2000);
	set_reg(vcpu, REG_ID(regs.regs[20]), 0x84000008); /* PSCI off */
	do {
		run_ret = ioctl(vcpu, KVM_RUN, 0);
	} while (run_ret < 0 && errno == EINTR);
	if (run_ret < 0)
		fail("KVM_RUN");
	if (run->exit_reason != KVM_EXIT_SYSTEM_EVENT ||
	    run->system_event.type != KVM_SYSTEM_EVENT_SHUTDOWN || *result ||
	    !array[0] || (array[0] & 0xfff)) {
		fprintf(stderr, "bad result: exit=%u type=%u ret=%" PRIx64
			" hpa=%" PRIx64 "\n", run->exit_reason,
			run->system_event.type, *result, array[0]);
		exit(EXIT_FAILURE);
	}
	for (i = 1; i < ENTRY_COUNT; i++) {
		if (array[i] != array[0]) {
			fprintf(stderr, "duplicate GPA yielded different HPA\n");
			exit(EXIT_FAILURE);
		}
	}
	mark(order, "translated-32-duplicate-pages");
	if (device_first) {
		int reopened;

		close(gpu);
		mark(order, "device-closed-vm-alive");
		errno = 0;
		reopened = open("/dev/pmthor", O_RDWR | O_CLOEXEC);
		if (reopened >= 0 || errno != EBUSY) {
			if (reopened >= 0)
				close(reopened);
			fprintf(stderr, "GPU must remain exclusive to live VM\n");
			exit(EXIT_FAILURE);
		}
		mark(order, "reopen-blocked");
	}
	munmap(run, run_size);
	close(vcpu);
	close(vm);
	close(kvm);
	mark(order, "vm-closed");
	if (!device_first) {
		close(gpu);
		mark(order, "device-closed");
	}
	munmap(ram, RAM_SIZE);
	mark(order, "pass");
}

int main(void)
{
	setbuf(stdout, NULL);
	alarm(30);
	run_order(0);
	run_order(1);
	puts("PMTHOR_PFN_TRANSLATION_RESULT=PASS");
	/* PFN release/count assertions require the matching kernel log. */
	return 0;
}
