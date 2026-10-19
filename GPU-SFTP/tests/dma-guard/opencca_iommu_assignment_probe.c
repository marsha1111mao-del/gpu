#include <linux/arm-smccc.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/iommu.h>
#include <linux/module.h>
#include <linux/platform_device.h>

#define IOMMU_SMC 0xc400016cUL
#define IOMMU_UNBIND 6UL
#define IOMMU_GRANT 9UL
#define IOMMU_REVOKE 10UL
#define IOMMU_FAULT 11UL
#define IOMMU_FAULT_GUEST BIT_ULL(32)
#define CODEC_IOMMU 0xfdb50800UL

static unsigned long guest_handle;
module_param(guest_handle, ulong, 0400);
static struct device *codec;
static struct iommu_domain *domain;
static bool granted;
static unsigned long host_handle;

static int fault_check(const char *name)
{
	struct arm_smccc_res result;
	bool passed;

	arm_smccc_1_1_smc(IOMMU_SMC, IOMMU_FAULT, host_handle,
			  CODEC_IOMMU, 0, 0, 0, 0, &result);
	passed = !result.a0 && result.a1 == IOMMU_FAULT_GUEST && !result.a2 && !result.a3;
	pr_info("[IOMMU_ASSIGNMENT_TEST] %s=%s status=%lu flags=%lx\n",
		name, passed ? "PASS" : "FAIL", result.a0, result.a1);
	return passed ? 0 : -EIO;
}

static int revoke(void)
{
	struct arm_smccc_res result;

	if (!granted)
		return 0;
	arm_smccc_1_1_smc(IOMMU_SMC, IOMMU_REVOKE, 0, CODEC_IOMMU, 0, 0, 0, 0, &result);
	pr_info("[IOMMU_ASSIGNMENT_TEST] revoke=%s status=%lu\n",
		result.a0 ? "FAIL" : "PASS", result.a0);
	if (result.a0)
		return -EIO;
	granted = false;
	return 0;
}

static int action_set(const char *value, const struct kernel_param *parameter)
{
	unsigned long action;

	if (kstrtoul(value, 0, &action))
		return -EINVAL;
	if (action == IOMMU_REVOKE)
		return revoke();
	if (action == IOMMU_FAULT && granted)
		return fault_check("host_fault_for_bound_guest");
	return -EINVAL;
}

static const struct kernel_param_ops action_ops = {
	.set = action_set,
};
module_param_cb(action, &action_ops, NULL, 0200);

static void release_domain(void)
{
	iommu_detach_device(domain, codec);
	iommu_domain_free(domain);
	put_device(codec);
}

static int __init assignment_init(void)
{
	struct arm_smccc_res result;
	int ret;

	if (!guest_handle)
		return -EINVAL;
	codec = bus_find_device_by_name(&platform_bus_type, NULL, "fdb50000.video-codec");
	if (!codec)
		return -ENODEV;
	domain = iommu_paging_domain_alloc(codec);
	if (IS_ERR(domain)) {
		ret = PTR_ERR(domain);
		put_device(codec);
		return ret;
	}
	ret = iommu_attach_device(domain, codec);
	if (ret) {
		iommu_domain_free(domain);
		put_device(codec);
		return ret;
	}
	arm_smccc_1_1_smc(IOMMU_SMC, IOMMU_GRANT, 0, CODEC_IOMMU,
			  guest_handle, 0, 0, 0, &result);
	pr_info("[IOMMU_ASSIGNMENT_TEST] grant=%s status=%lu\n",
		result.a0 ? "FAIL" : "PASS", result.a0);
	if (result.a0) {
		release_domain();
		return -EIO;
	}
	granted = true;
	host_handle = result.a1;
	ret = fault_check("host_fault_for_parked_guest");
	if (ret) {
		if (!revoke())
			release_domain();
		return ret;
	}
	arm_smccc_1_1_smc(IOMMU_SMC, IOMMU_UNBIND, host_handle,
			  CODEC_IOMMU, 0, 0, 0, 0, &result);
	pr_info("[IOMMU_ASSIGNMENT_TEST] host_unbind_while_granted=%s status=%lu\n",
		result.a0 == 2 ? "PASS" : "FAIL", result.a0);
	if (result.a0 != 2) {
		if (!revoke())
			release_domain();
		return -EIO;
	}
	return 0;
}

static void __exit assignment_exit(void)
{
	if (!revoke())
		release_domain();
}

module_init(assignment_init);
module_exit(assignment_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA powered codec IOMMU assignment and revocation probe");
