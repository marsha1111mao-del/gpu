#include <linux/arm-smccc.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/uaccess.h>

#define GPU_MMIO_BASE 0xfb000000UL
#define GPU_INT_RAWSTAT 0x20U
#define GPU_INT_MASK 0x28U
#define GPU_STATUS 0x34U
#define GPU_IRQ_FAULT BIT(0)
#define GPU_BUSY_MASK GENMASK(1, 0)
#define GPU_PM 0xc400016eUL
#define GPU_PM_STATUS 4UL
#define GPU_DESIGNATED 1UL

static unsigned int outcome = 1;
module_param(outcome, uint, 0444);

static int mmio_read(void __iomem *address, u32 *value)
{
	pagefault_disable();
	__get_kernel_nofault(value, address, u32, fault);
	pagefault_enable();
	return 0;
fault:
	pagefault_enable();
	return -EFAULT;
}

static int mmio_write(void __iomem *address, u32 value)
{
	pagefault_disable();
	__put_kernel_nofault(address, &value, u32, fault);
	pagefault_enable();
	dsb(sy);
	return 0;
fault:
	pagefault_enable();
	return -EFAULT;
}

static void probe_denied_access(void __iomem *registers, int status_error,
			       int raw_error, int mask_error)
{
	void __iomem *alias;
	u32 observed = 0;
	int write_error, read_error, restore_error;
	int alias_read_error, alias_write_error, alias_restore_error, recheck_error;

	alias = ioremap(GPU_MMIO_BASE, 2 * PAGE_SIZE);
	if (!alias)
		return;
	write_error = mmio_write(registers + GPU_INT_MASK, GPU_IRQ_FAULT);
	read_error = mmio_read(registers + GPU_INT_MASK, &observed);
	restore_error = mmio_write(registers + GPU_INT_MASK, 0);
	alias_read_error = mmio_read(alias + GPU_INT_MASK, &observed);
	alias_write_error = mmio_write(alias + GPU_INT_MASK, GPU_IRQ_FAULT);
	alias_restore_error = mmio_write(alias + GPU_INT_MASK, 0);
	recheck_error = mmio_read(registers + GPU_INT_MASK, &observed);
	if (write_error == -EFAULT && read_error == -EFAULT &&
	    restore_error == -EFAULT && alias_read_error == -EFAULT &&
	    alias_write_error == -EFAULT && alias_restore_error == -EFAULT &&
	    recheck_error == -EFAULT)
		outcome = 0;
	pr_info("[HOST_KERNEL_MMIO_TEST] blocked_address=%#lx status_error=%d raw_error=%d mask_error=%d write_error=%d read_error=%d restore_error=%d alias_read_error=%d alias_write_error=%d alias_restore_error=%d recheck_error=%d\n",
		GPU_MMIO_BASE + GPU_INT_MASK, status_error, raw_error, mask_error,
		write_error, read_error, restore_error, alias_read_error,
		alias_write_error, alias_restore_error, recheck_error);
	pr_info("[HOST_KERNEL_MMIO_TEST] physical_access=%s\n",
		outcome == 0 ? "DENIED" : "NOT_PROVEN");
	iounmap(alias);
}

static int __init gpu_mmio_probe_init(void)
{
	struct arm_smccc_res result;
	void __iomem *registers;
	u32 original, requested, observed = 0, restored = 0, raw, status;
	int write_error, read_error, restore_error, restore_read_error;
	int status_error, raw_error, mask_error;

	arm_smccc_1_1_smc(GPU_PM, GPU_PM_STATUS, 0, 0, 0, 0, 0, 0, &result);
	if (result.a0 || result.a1 != GPU_DESIGNATED)
		return -EBUSY;
	registers = ioremap(GPU_MMIO_BASE, PAGE_SIZE);
	if (!registers)
		return -ENOMEM;
	status_error = mmio_read(registers + GPU_STATUS, &status);
	raw_error = mmio_read(registers + GPU_INT_RAWSTAT, &raw);
	mask_error = mmio_read(registers + GPU_INT_MASK, &original);
	if (status_error == -EFAULT && raw_error == -EFAULT && mask_error == -EFAULT) {
		probe_denied_access(registers, status_error, raw_error, mask_error);
		goto out;
	}
	if (status_error || raw_error || mask_error) {
		pr_info("[HOST_KERNEL_MMIO_TEST] physical_write=NOT_PROVEN read_fault=1\n");
		goto out;
	}
	if ((status & GPU_BUSY_MASK) || (raw & GPU_IRQ_FAULT)) {
		pr_info("[HOST_KERNEL_MMIO_TEST] physical_write=NOT_PROVEN busy=%#x raw=%#x\n",
			status, raw);
		goto out;
	}
	requested = original ^ GPU_IRQ_FAULT;
	write_error = mmio_write(registers + GPU_INT_MASK, requested);
	read_error = mmio_read(registers + GPU_INT_MASK, &observed);
	restore_error = mmio_write(registers + GPU_INT_MASK, original);
	restore_read_error = mmio_read(registers + GPU_INT_MASK, &restored);
	if (!write_error && !read_error && !restore_error && !restore_read_error &&
	    observed == requested && restored == original)
		outcome = 2;
	pr_info("[HOST_KERNEL_MMIO_TEST] address=%#lx before=%#x requested=%#x observed=%#x restored=%#x write_error=%d read_error=%d restore_error=%d restore_read_error=%d\n",
		GPU_MMIO_BASE + GPU_INT_MASK, original, requested, observed, restored,
		write_error, read_error, restore_error, restore_read_error);
	pr_info("[HOST_KERNEL_MMIO_TEST] physical_write=%s restoration=%s\n",
		outcome == 2 ? "FAIL_BYPASS_DETECTED" : "NOT_PROVEN",
		!restore_error && !restore_read_error && restored == original ? "PASS" : "FAIL");
out:
	iounmap(registers);
	return 0;
}

static void __exit gpu_mmio_probe_exit(void)
{
}

module_init(gpu_mmio_probe_init);
module_exit(gpu_mmio_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA Host kernel GPU-MMIO bypass diagnostic");
