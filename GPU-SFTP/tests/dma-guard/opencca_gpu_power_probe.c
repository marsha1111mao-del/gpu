#include <linux/arm-smccc.h>
#include <linux/module.h>

#define GPU_PM 0xc400016eUL
#define GPU_OPP_BEGIN 2UL
#define GPU_STATUS 4UL

static unsigned long expected_state;
module_param(expected_state, ulong, 0400);

static int __init power_probe_init(void)
{
	struct arm_smccc_res result;

	arm_smccc_1_1_smc(GPU_PM, GPU_STATUS, 0, 0, 0, 0, 0, 0, &result);
	pr_info("[GPU_POWER_TEST] state=%lu expected=%lu result=%s\n",
		result.a1, expected_state,
		!result.a0 && result.a1 == expected_state ? "PASS" : "FAIL");
	if (result.a0 || result.a1 != expected_state)
		return -EIO;
	arm_smccc_1_1_smc(GPU_PM, GPU_OPP_BEGIN, 1, 0, 0, 0, 0, 0, &result);
	pr_info("[GPU_POWER_TEST] invalid_opp_rejected=%s\n", result.a0 == 1 ? "PASS" : "FAIL");
	if (result.a0 != 1)
		return -EIO;
	arm_smccc_1_1_smc(GPU_PM, GPU_STATUS, 0, 0, 0, 0, 0, 0, &result);
	return !result.a0 && result.a1 == expected_state ? 0 : -EIO;
}

static void __exit power_probe_exit(void)
{
}

module_init(power_probe_init);
module_exit(power_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA RMM GPU power-state and illegal OPP probe");
