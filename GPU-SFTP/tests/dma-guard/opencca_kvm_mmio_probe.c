// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <asm/kvm.h>
#include <linux/kvm.h>

#include <stdbool.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <string.h>
#include <unistd.h>

#ifndef KVM_VM_TYPE_ARM_REALM
#define KVM_VM_TYPE_ARM_REALM ((1ULL << 8) & 0xf00ULL)
#endif
#ifndef KVM_CAP_ARM_RME
#define KVM_CAP_ARM_RME 300
#endif
#ifndef KVM_CAP_ARM_RME_CREATE_RD
#define KVM_CAP_ARM_RME_CREATE_RD 1
#endif
#ifndef KVM_CAP_ARM_RME_CONFIG_REALM
#define KVM_CAP_ARM_RME_CONFIG_REALM 0
#endif
#ifndef KVM_CAP_ARM_RME_CFG_HASH_ALGO
#define KVM_CAP_ARM_RME_CFG_HASH_ALGO 1
#define KVM_CAP_ARM_RME_MEASUREMENT_ALGO_SHA256 0
struct kvm_cap_arm_rme_config_item {
	uint32_t cfg;
	union {
		uint32_t hash_algo;
		uint8_t reserved[256];
	};
};
#endif
#ifndef KVM_CAP_ARM_VM_IPA_SIZE
#define KVM_CAP_ARM_VM_IPA_SIZE 51
#endif
#ifndef KVM_SET_MMIO_REGION
struct kvm_mmio_region {
	__u64 guest_phys_addr;
	__u64 memory_size;
};
#define KVM_SET_MMIO_REGION _IOR(0xae, 0xb7, struct kvm_mmio_region)
#endif

#define GPU_MMIO_BASE 0xfb000000ULL
#define GPU_MMIO_SIZE 0x200000ULL
#define GPU_DEVFREQ "/sys/class/devfreq/fb000000.gpu"
#define FREQUENCY_CAPACITY 64U
#define GPU_INT_RAWSTAT 0x20U
#define GPU_INT_MASK 0x28U
#define GPU_STATUS 0x34U
#define GPU_IRQ_FAULT 1U
#define GPU_BUSY_MASK 3U

static int write_sysfs(const char *path, const char *value)
{
	FILE *file = fopen(path, "w");
	int ret;

	if (!file)
		return -1;
	ret = fputs(value, file) == EOF ? -1 : 0;
	if (fclose(file) != 0)
		return -1;
	return ret;
}

static int read_sysfs_ll(const char *path, long long *value)
{
	FILE *file = fopen(path, "r");

	if (!file)
		return -1;
	if (fscanf(file, "%lld", value) != 1) {
		fclose(file);
		return -1;
	}
	return fclose(file) == 0 ? 0 : -1;
}

static int check(const char *name, bool passed)
{
	printf("[KVM_MMIO_TEST] %s=%s errno=%d\n", name,
	       passed ? "PASS" : "FAIL", errno);
	return passed ? 0 : -1;
}

static int create_realm(void)
{
	struct kvm_cap_arm_rme_config_item config;
	struct kvm_enable_cap cap;
	int kvm = open("/dev/kvm", O_RDWR | O_CLOEXEC);
	int ipa_size, vm, vcpu, memfd = -1;
	void *host_addr = MAP_FAILED;
	struct kvm_create_guest_memfd guest_memfd;
	struct kvm_userspace_memory_region2 memory_region;
	struct kvm_vcpu_init vcpu_init;

	if (kvm < 0)
		return -1;
	if (ioctl(kvm, KVM_CHECK_EXTENSION, KVM_CAP_ARM_RME) <= 0) {
		close(kvm);
		errno = ENXIO;
		return -1;
	}
	ipa_size = ioctl(kvm, KVM_CHECK_EXTENSION, KVM_CAP_ARM_VM_IPA_SIZE);
	if (ipa_size <= 0) {
		close(kvm);
		errno = ENXIO;
		return -1;
	}
	vm = ioctl(kvm, KVM_CREATE_VM,
		   KVM_VM_TYPE_ARM_REALM | (unsigned int)ipa_size);
	close(kvm);
	kvm = -1;
	if (vm < 0) {
		perror("KVM_CREATE_VM");
		return -1;
	}
	memset(&guest_memfd, 0, sizeof(guest_memfd));
	guest_memfd.size = 2U << 20;
	memfd = ioctl(vm, KVM_CREATE_GUEST_MEMFD, &guest_memfd);
	if (memfd < 0) {
		perror("KVM_CREATE_GUEST_MEMFD");
		goto error;
	}
	host_addr = mmap(NULL, guest_memfd.size, PROT_READ | PROT_WRITE,
			 MAP_SHARED | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
	if (host_addr == MAP_FAILED) {
		perror("mmap guest memory");
		goto error;
	}
	memset(&memory_region, 0, sizeof(memory_region));
	memory_region.slot = 0;
	memory_region.guest_phys_addr = 0x80000000ULL;
	memory_region.memory_size = guest_memfd.size;
	memory_region.userspace_addr = (uint64_t)(uintptr_t)host_addr;
	memory_region.flags = KVM_MEM_GUEST_MEMFD;
	memory_region.guest_memfd = memfd;
	if (ioctl(vm, KVM_SET_USER_MEMORY_REGION2, &memory_region)) {
		perror("KVM_SET_USER_MEMORY_REGION2");
		goto error;
	}
	vcpu = ioctl(vm, KVM_CREATE_VCPU, 0);
	if (vcpu < 0) {
		perror("KVM_CREATE_VCPU");
		goto error;
	}
	memset(&vcpu_init, 0, sizeof(vcpu_init));
	if (ioctl(vm, KVM_ARM_PREFERRED_TARGET, &vcpu_init)) {
		perror("KVM_ARM_PREFERRED_TARGET");
		goto error_close_vcpu;
	}
	vcpu_init.features[0] |= 1U << KVM_ARM_VCPU_PSCI_0_2;
	if (ioctl(vcpu, KVM_ARM_VCPU_INIT, &vcpu_init)) {
		perror("KVM_ARM_VCPU_INIT");
		goto error_close_vcpu;
	}

	memset(&config, 0, sizeof(config));
	config.cfg = KVM_CAP_ARM_RME_CFG_HASH_ALGO;
	config.hash_algo = KVM_CAP_ARM_RME_MEASUREMENT_ALGO_SHA256;
	cap = (struct kvm_enable_cap){
		.cap = KVM_CAP_ARM_RME,
		.args = { KVM_CAP_ARM_RME_CONFIG_REALM,
			  (uint64_t)(uintptr_t)&config },
	};
	if (ioctl(vm, KVM_ENABLE_CAP, &cap)) {
		perror("KVM_CAP_ARM_RME_CONFIG_REALM");
		goto error_close_vcpu;
	}
	cap = (struct kvm_enable_cap){
		.cap = KVM_CAP_ARM_RME,
		.args = { KVM_CAP_ARM_RME_CREATE_RD },
	};
	if (ioctl(vm, KVM_ENABLE_CAP, &cap)) {
		perror("KVM_CAP_ARM_RME_CREATE_RD");
		goto error_close_vcpu;
	}
	close(vcpu);
	munmap(host_addr, guest_memfd.size);
	close(memfd);
	return vm;

error_close_vcpu:
	close(vcpu);
error:
	if (host_addr != MAP_FAILED)
		munmap(host_addr, guest_memfd.size);
	if (memfd >= 0)
		close(memfd);
	if (kvm >= 0)
		close(kvm);
	close(vm);
	return -1;
}

static int set_gpu_region(int vm, uint64_t address, uint64_t size)
{
	struct kvm_mmio_region region = {
		.guest_phys_addr = address,
		.memory_size = size,
	};

	return ioctl(vm, KVM_SET_MMIO_REGION, &region);
}

static int rejected(int vm, uint64_t address, uint64_t size)
{
	errno = 0;
	return set_gpu_region(vm, address, size) == -1 &&
	       (errno == EPERM || errno == EINVAL);
}

static int exercise_owner_opp_transition(void)
{
	static const char *root = GPU_DEVFREQ;
	char path[256], governor[64] = "", request[32] = "", target[32] = "";
	long long frequencies[64] = {0}, before = 0, after = 0;
	unsigned int count = 0, selected = FREQUENCY_CAPACITY;
	bool passed = false;
	FILE *file;

	errno = 0;
	snprintf(path, sizeof(path), "%s/governor", root);
	file = fopen(path, "r");
	if (!file || !fgets(governor, sizeof(governor), file)) {
		if (file)
			fclose(file);
		goto out;
	}
	if (fclose(file) != 0)
		goto out;
	governor[strcspn(governor, "\n")] = '\0';

	snprintf(path, sizeof(path), "%s/cur_freq", root);
	file = fopen(path, "r");
	if (!file || !fgets(request, sizeof(request), file)) {
		if (file)
			fclose(file);
		goto out;
	}
	if (fclose(file) != 0)
		goto out;
	request[strcspn(request, "\n")] = '\0';
	if (sscanf(request, "%lld", &before) != 1)
		goto out;

	snprintf(path, sizeof(path), "%s/available_frequencies", root);
	file = fopen(path, "r");
	if (!file)
		goto out;
	while (count < FREQUENCY_CAPACITY &&
	       fscanf(file, "%lld", &frequencies[count]) == 1)
		count++;
	if (fclose(file) != 0 || count < 2)
		goto out;
	for (unsigned int i = 0; i < count; i++) {
		if (frequencies[i] != before &&
		    (selected == FREQUENCY_CAPACITY ||
		     llabs(frequencies[i] - before) <
		     llabs(frequencies[selected] - before)))
			selected = i;
	}
	if (selected == FREQUENCY_CAPACITY)
		goto out;
	if (snprintf(target, sizeof(target), "%lld\n", frequencies[selected]) >=
	    (int)sizeof(target))
		goto out;

	snprintf(path, sizeof(path), "%s/governor", root);
	if (write_sysfs(path, "userspace\n") ||
	    write_sysfs(GPU_DEVFREQ "/userspace/set_freq", target))
		goto restore;
	snprintf(path, sizeof(path), "%s/cur_freq", root);
	if (read_sysfs_ll(path, &after) || after != frequencies[selected])
		goto restore;
	passed = true;

restore:
	(void)write_sysfs(GPU_DEVFREQ "/userspace/set_freq", request);
	(void)write_sysfs(GPU_DEVFREQ "/governor", governor);
	snprintf(path, sizeof(path), "%s/cur_freq", root);
	{
		char restored[32] = "";
		FILE *check = fopen(path, "r");

		if (!check || !fgets(restored, sizeof(restored), check)) {
			if (check)
				fclose(check);
			passed = false;
		} else {
			if (fclose(check) != 0)
				passed = false;
			restored[strcspn(restored, "\n")] = '\0';
			if (strcmp(restored, request) != 0)
				passed = false;
		}
	}
out:
	return check("owner_opp_transition_succeeds", passed);
}

static sigjmp_buf mmio_fault_return;
static volatile sig_atomic_t mmio_fault_armed;
static volatile sig_atomic_t mmio_fault_signal;
static volatile sig_atomic_t mmio_fault_code;
static volatile uintptr_t mmio_fault_address;

static void user_mmio_fault(int signal_number, siginfo_t *info, void *context)
{
	(void)context;
	if (!mmio_fault_armed || signal_number != SIGBUS || info->si_code != BUS_OBJERR ||
	    (uintptr_t)info->si_addr != mmio_fault_address)
		_exit(1);
	mmio_fault_signal = signal_number;
	mmio_fault_code = info->si_code;
	mmio_fault_armed = 0;
	siglongjmp(mmio_fault_return, 1);
}

static int user_mmio_access(volatile uint32_t *address, bool write, uint32_t *value)
{
	mmio_fault_address = (uintptr_t)address;
	if (sigsetjmp(mmio_fault_return, 1))
		return -EFAULT;
	mmio_fault_armed = 1;
	if (write)
		*address = *value;
	else
		*value = *address;
	__asm__ volatile("dsb sy" : : : "memory");
	mmio_fault_armed = 0;
	return 0;
}

static int audit_host_mmio_write(void)
{
	volatile uint32_t *registers;
	uint32_t original, requested, observed, restored, raw, status;
	struct sigaction action = { .sa_sigaction = user_mmio_fault, .sa_flags = SA_SIGINFO };
	long page_size = sysconf(_SC_PAGESIZE);
	int memory, outcome;
	int initial_read_error, write_error, read_error, restore_error, restore_read_error;

	if (page_size <= GPU_STATUS)
		return 1;
	memory = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
	if (memory < 0) {
		perror("host MMIO diagnostic open /dev/mem");
		return 1;
	}
	registers = mmap(NULL, page_size, PROT_READ | PROT_WRITE,
			 MAP_SHARED, memory, GPU_MMIO_BASE);
	close(memory);
	if (registers == MAP_FAILED) {
		perror("host MMIO diagnostic mmap");
		return 1;
	}
	sigemptyset(&action.sa_mask);
	if (sigaction(SIGBUS, &action, NULL)) {
		munmap((void *)registers, page_size);
		return 1;
	}
	initial_read_error = user_mmio_access(registers + GPU_INT_MASK / sizeof(uint32_t),
					    false, &original);
	if (initial_read_error == -EFAULT) {
		requested = GPU_IRQ_FAULT;
		restored = 0;
		write_error = user_mmio_access(registers + GPU_INT_MASK / sizeof(uint32_t),
					       true, &requested);
		read_error = user_mmio_access(registers + GPU_INT_MASK / sizeof(uint32_t),
					      false, &observed);
		restore_error = user_mmio_access(registers + GPU_INT_MASK / sizeof(uint32_t),
						 true, &restored);
		restore_read_error = user_mmio_access(registers + GPU_INT_MASK / sizeof(uint32_t),
						      false, &observed);
		outcome = write_error == -EFAULT && read_error == -EFAULT &&
			restore_error == -EFAULT && restore_read_error == -EFAULT ? 0 : 1;
		printf("[HOST_USER_MMIO_TEST] blocked_address=%#llx initial_read_error=%d write_error=%d read_error=%d restore_error=%d restore_read_error=%d signal=%d code=%d\n",
		       (unsigned long long)(GPU_MMIO_BASE + GPU_INT_MASK), initial_read_error,
		       write_error, read_error, restore_error, restore_read_error,
		       mmio_fault_signal, mmio_fault_code);
		printf("[HOST_MMIO_TEST] physical_write=%s restoration=NOT_APPLICABLE\n",
		       outcome == 0 ? "DENIED" : "NOT_PROVEN");
		if (munmap((void *)registers, page_size))
			outcome = 1;
		return outcome;
	}
	status = registers[GPU_STATUS / sizeof(uint32_t)];
	raw = registers[GPU_INT_RAWSTAT / sizeof(uint32_t)];
	original = registers[GPU_INT_MASK / sizeof(uint32_t)];
	if ((status & GPU_BUSY_MASK) || (raw & GPU_IRQ_FAULT)) {
		printf("[HOST_MMIO_TEST] physical_write=NOT_PROVEN busy=%#x raw=%#x\n",
		       status, raw);
		munmap((void *)registers, page_size);
		return 1;
	}
	requested = original ^ GPU_IRQ_FAULT;
	registers[GPU_INT_MASK / sizeof(uint32_t)] = requested;
	__asm__ volatile("dsb sy" : : : "memory");
	observed = registers[GPU_INT_MASK / sizeof(uint32_t)];
	registers[GPU_INT_MASK / sizeof(uint32_t)] = original;
	__asm__ volatile("dsb sy" : : : "memory");
	restored = registers[GPU_INT_MASK / sizeof(uint32_t)];
	printf("[HOST_MMIO_TEST] address=%#llx before=%#x requested=%#x observed=%#x restored=%#x\n",
	       (unsigned long long)(GPU_MMIO_BASE + GPU_INT_MASK),
	       original, requested, observed, restored);
	printf("[HOST_MMIO_TEST] physical_write=%s restoration=%s\n",
	       observed == requested ? "FAIL_BYPASS_DETECTED" : "NOT_PROVEN",
	       restored == original ? "PASS" : "FAIL");
	outcome = observed == requested && restored == original ? 2 : 1;
	if (munmap((void *)registers, page_size))
		outcome = 1;
	return outcome;
}

static int run_host_mmio_audit(void)
{
	int status;
	pid_t child;

	if (fflush(NULL))
		return 1;
	child = fork();
	if (child < 0)
		return 1;
	if (!child) {
		int outcome = audit_host_mmio_write();

		fflush(NULL);
		_exit(outcome);
	}
	while (waitpid(child, &status, 0) < 0) {
		if (errno != EINTR)
			return 1;
	}
	if (!WIFEXITED(status)) {
		printf("[HOST_MMIO_TEST] physical_write=NOT_PROVEN signal=%d\n",
		       WIFSIGNALED(status) ? WTERMSIG(status) : 0);
		return 1;
	}
	return WEXITSTATUS(status);
}

static int run_command(const char *command, const char *argument)
{
	int status;
	pid_t child;

	if (fflush(NULL))
		return -1;
	child = fork();
	if (child < 0)
		return -1;
	if (!child) {
		execlp(command, command, argument, NULL);
		_exit(127);
	}
	while (waitpid(child, &status, 0) < 0) {
		if (errno != EINTR)
			return -1;
	}
	return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}

static int run_host_kernel_mmio_audit(const char *module)
{
	long long outcome = 1;
	int read_error, unload_error;

	if (run_command("insmod", module))
		return 1;
	read_error = read_sysfs_ll("/sys/module/opencca_gpu_mmio_probe/parameters/outcome",
				   &outcome);
	unload_error = run_command("rmmod", "opencca_gpu_mmio_probe");
	printf("[HOST_MMIO_TEST] kernel_physical_write=%s restoration=%s module_cleanup=%s\n",
	       !read_error && outcome == 0 ? "DENIED" :
	       !read_error && outcome == 2 ? "FAIL_BYPASS_DETECTED" : "NOT_PROVEN",
	       !read_error && outcome == 0 ? "NOT_APPLICABLE" :
	       !read_error && outcome == 2 ? "PASS" : "NOT_PROVEN",
	       !unload_error ? "PASS" : "FAIL");
	if (read_error || unload_error)
		return 1;
	return outcome == 0 || outcome == 2 ? outcome : 1;
}

int main(int argc, char **argv)
{
	int first, second, third;
	int pmthor = -1;
	int ret;
	int audit_result = 0;
	bool audit = argc == 2 && !strcmp(argv[1], "--audit-host-mmio");
	bool kernel_audit = argc == 3 && !strcmp(argv[1], "--audit-host-kernel-mmio");
	bool ordinary_audit = argc == 3 && !strcmp(argv[1], "--audit-ordinary-vm-mmio");

	if (argc != 1 && !audit && !kernel_audit && !ordinary_audit) {
		fprintf(stderr, "usage: %s [--audit-host-mmio | --audit-host-kernel-mmio MODULE | --audit-ordinary-vm-mmio PROBE]\n",
			argv[0]);
		return 1;
	}

	first = create_realm();
	if (first < 0) {
		perror("create first Realm");
		return 1;
	}

	ret = check("non_gpu_mmio_denied", rejected(first, 0xfd000000ULL, 0x1000));
	ret |= check("misaligned_gpu_mmio_denied",
		     rejected(first, GPU_MMIO_BASE + 0x1000ULL, 0x1000));
	ret |= check("oversized_gpu_mmio_denied",
		     rejected(first, GPU_MMIO_BASE, GPU_MMIO_SIZE + 0x1000));
	ret |= check("undersized_gpu_mmio_denied",
		     rejected(first, GPU_MMIO_BASE, GPU_MMIO_SIZE - 0x1000));
	pmthor = open("/dev/pmthor", O_RDWR | O_CLOEXEC);
	ret |= check("pmthor_owner_session_opens", pmthor >= 0);
	ret |= check("authorized_proxy_mmio_succeeds",
		     set_gpu_region(first, GPU_MMIO_BASE, GPU_MMIO_SIZE) == 0);
	ret |= exercise_owner_opp_transition();
	if (ret)
		goto close_first;

	second = create_realm();
	if (second < 0) {
		perror("create second Realm");
		ret = -1;
		goto close_first;
	}
	ret = check("second_realm_mmio_denied",
		    rejected(second, GPU_MMIO_BASE, GPU_MMIO_SIZE));
	close(second);
	if (ret)
		goto close_first;

	if (audit)
		audit_result = run_host_mmio_audit();
	if (kernel_audit)
		audit_result = run_host_kernel_mmio_audit(argv[2]);
	if (ordinary_audit)
		audit_result = run_command(argv[2], "--audit-mmio");

	ret |= check("pmthor_owner_release_succeeds", close(pmthor) == 0);
	pmthor = -1;
	close(first);
	first = -1;
	third = create_realm();
	if (third < 0) {
		perror("create Realm after owner destroy");
		return 1;
	}
	pmthor = open("/dev/pmthor", O_RDWR | O_CLOEXEC);
	ret = check("pmthor_owner_session_reopens", pmthor >= 0);
	ret |= check("destroy_releases_mmio_owner",
		     set_gpu_region(third, GPU_MMIO_BASE, GPU_MMIO_SIZE) == 0);
	if (pmthor >= 0)
		close(pmthor);
	close(third);
	if (ret)
		return 1;

	puts("[KVM_MMIO_TEST] result=PASS");
	return audit_result;

close_first:
	if (pmthor >= 0)
		close(pmthor);
	if (first >= 0)
		close(first);
	return 1;
}
