// SPDX-License-Identifier: GPL-2.0-only
#include <linux/arm-smccc.h>
#include <linux/err.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/printk.h>

#define OPENCCA_RSI_IOMMU 0xc40001b0UL
#define OPENCCA_RSI_GPU_CONTROL 0xc40001b1UL
#define IOMMU_VERSION 0UL
#define IOMMU_CREATE 1UL
#define IOMMU_MAP 2UL
#define IOMMU_UNMAP 3UL
#define IOMMU_QUERY 4UL
#define IOMMU_BIND 5UL
#define IOMMU_UNBIND 6UL
#define IOMMU_DESTROY 8UL
#define IOMMU_FAULT 11UL
#define IOMMU_FAULT_GUEST BIT_ULL(32)
#define PAGE_GRANULE 4096UL
#define OPENCCA_RSI_GPU_TRANSLATE 0xc40001afUL
#define OPENCCA_RSI_GPU_REVOKE 0xc40001aeUL

static bool hold_mapping;
module_param(hold_mapping, bool, 0400);
static bool gpu_lease;
module_param(gpu_lease, bool, 0400);
static bool device_test;
module_param(device_test, bool, 0400);
static unsigned long held_page;
static unsigned long held_array;
static unsigned long held_domain;

static int check(const char *name, bool passed)
{
	pr_info("[GUEST_IOMMU_TEST] %s=%s\n", name, passed ? "PASS" : "FAIL");
	return passed ? 0 : -EIO;
}

static struct arm_smccc_1_2_regs call(unsigned long operation,
					unsigned long handle, unsigned long arg1,
					unsigned long arg2, unsigned long arg3)
{
	struct arm_smccc_1_2_regs args = {
		.a0 = OPENCCA_RSI_IOMMU,
		.a1 = operation,
		.a2 = handle,
		.a3 = arg1,
		.a4 = arg2,
		.a5 = arg3,
	};
	struct arm_smccc_1_2_regs result;

	arm_smccc_1_2_smc(&args, &result);
	return result;
}

static int device_action_set(const char *value, const struct kernel_param *parameter)
{
	struct arm_smccc_1_2_regs result;
	unsigned long operation;

	if (!device_test || !held_domain || kstrtoul(value, 0, &operation) ||
	    (operation != IOMMU_BIND && operation != IOMMU_UNBIND && operation != IOMMU_FAULT))
		return -EINVAL;
	result = call(operation, held_domain, 0xfdb50800UL, 0, 0);
	if (operation == IOMMU_FAULT && !result.a0 &&
	    (result.a1 != IOMMU_FAULT_GUEST || result.a2 || result.a3 || result.a4 != held_domain))
		return -EIO;
	pr_info("[GUEST_IOMMU_TEST] device_operation=%lu status=%lu\n",
		operation, result.a0);
	return result.a0 ? -EPERM : 0;
}

static const struct kernel_param_ops device_action_ops = {
	.set = device_action_set,
};
module_param_cb(device_action, &device_action_ops, NULL, 0200);

static int hold_backing(void)
{
	struct arm_smccc_1_2_regs result;
	struct arm_smccc_res gpu_result;

	held_page = get_zeroed_page(GFP_KERNEL);
	if (!held_page)
		return -ENOMEM;
	if (gpu_lease) {
		held_array = get_zeroed_page(GFP_KERNEL);
		if (!held_array)
			goto fail;
		*(unsigned long *)held_array = __pa(held_page);
		arm_smccc_1_1_smc(OPENCCA_RSI_GPU_TRANSLATE, __pa(held_array), 1,
				  0, 0, 0, 0, 0, &gpu_result);
		if (gpu_result.a0)
			goto fail;
	} else {
		result = call(IOMMU_CREATE, 0, 0, 0, 0);
		if (result.a0)
			goto fail;
		held_domain = result.a1;
		result = call(IOMMU_MAP, held_domain, PAGE_GRANULE,
			      __pa(held_page), PAGE_GRANULE | 1);
		if (result.a0) {
			call(IOMMU_DESTROY, held_domain, 0, 0, 0);
			held_domain = 0;
			goto fail;
		}
	}
	pr_info("[GUEST_IOMMU_TEST] backing_held=PASS ipa=0x%lx gpu=%u domain=0x%lx\n",
		(unsigned long)__pa(held_page), gpu_lease, held_domain);
	return 0;
fail:
	if (held_array)
		free_page(held_array);
	free_page(held_page);
	held_array = 0;
	held_page = 0;
	return -EIO;
}

static int __init probe_init(void)
{
	struct arm_smccc_1_2_regs result;
	unsigned long handle, page, ipa;
	int ret;

	if (hold_mapping)
		return hold_backing();

	for (unsigned long operation = 0; operation < 2; operation++) {
		struct arm_smccc_res control;

		arm_smccc_1_1_smc(OPENCCA_RSI_GPU_CONTROL, operation,
				  0, 0, 0, 0, 0, 0, &control);
		ret = check(operation == 0 ? "unowned_gpu_claim_denied" :
			    "unowned_gpu_reset_denied", control.a0 == 1);
		if (ret)
			return ret;
	}

	result = call(IOMMU_VERSION, 0, 0, 0, 0);
	ret = check("version", result.a0 == 0 && result.a1 == 1);
	if (ret)
		return ret;

	result = call(IOMMU_CREATE, 0, 0, 0, 0);
	ret = check("create", result.a0 == 0 && result.a1 != 0);
	if (ret)
		return ret;
	handle = result.a1;
	result = call(IOMMU_BIND, handle, 0xfdb50800UL, 0, 0);
	ret = check("unassigned_codec_bind_denied", result.a0 == 2);
	if (!ret) {
		result = call(IOMMU_BIND, handle, 0xfdd97e00UL, 0, 0);
		ret = check("unpowered_vop_bind_denied", result.a0 == 2);
	}
	if (!ret) {
		result = call(IOMMU_FAULT, handle, 0xfdb50800UL, 0, 0);
		ret = check("unassigned_codec_fault_denied", result.a0 == 1);
	}
	if (!ret) {
		result = call(IOMMU_FAULT, handle, 0xfdd97e00UL, 0, 0);
		ret = check("unpowered_vop_fault_denied", result.a0 == 1);
	}
	if (ret) {
		call(IOMMU_DESTROY, handle, 0, 0, 0);
		return ret;
	}

	page = __get_free_pages(GFP_KERNEL, 0);
	if (!page) {
		call(IOMMU_DESTROY, handle, 0, 0, 0);
		return -ENOMEM;
	}
	ipa = __pa(page);

	result = call(IOMMU_MAP, handle, PAGE_GRANULE, ipa,
		      PAGE_GRANULE | 1);
	ret = check("map", result.a0 == 0 && result.a1 == PAGE_GRANULE);
	if (ret)
		goto free_page;

	result = call(IOMMU_QUERY, handle, PAGE_GRANULE, 0, 0);
	ret = check("query", result.a0 == 0 && result.a1 != 0 &&
		    result.a2 == 1 && result.a3 != 0 && result.a4 == 1);
	if (ret)
		goto unmap;

	result = call(IOMMU_DESTROY, handle, 0, 0, 0);
	ret = check("destroy_denied_while_mapped", result.a0 != 0);
	if (ret)
		goto unmap;

	result = call(IOMMU_UNMAP, handle, PAGE_GRANULE, 0, PAGE_GRANULE);
	ret = check("unmap", result.a0 == 0 && result.a1 == PAGE_GRANULE);
	if (ret)
		goto free_page;

	result = call(IOMMU_QUERY, handle, PAGE_GRANULE, 0, 0);
	ret = check("query_after_unmap", result.a0 == 0 && result.a1 == 0 &&
		    result.a2 == 0 && result.a4 == 0);
	if (ret)
		goto free_page;

	result = call(IOMMU_MAP, handle, (1UL << 32) - PAGE_GRANULE, ipa,
		      2UL * PAGE_GRANULE | 1);
	ret = check("overflow_mapping_denied", result.a0 != 0);
	if (ret)
		goto free_page;

	result = call(IOMMU_DESTROY, handle, 0, 0, 0);
	ret = check("destroy", result.a0 == 0);
	if (ret)
		goto free_page;

	result = call(IOMMU_QUERY, handle, PAGE_GRANULE, 0, 0);
	ret = check("stale_handle_denied", result.a0 != 0);
	if (ret)
		goto free_page;

	pr_info("[GUEST_IOMMU_TEST] result=PASS\n");
	free_pages(page, 0);
	return 0;

unmap:
	call(IOMMU_UNMAP, handle, PAGE_GRANULE, 0, PAGE_GRANULE);
free_page:
	free_pages(page, 0);
	call(IOMMU_DESTROY, handle, 0, 0, 0);
	return ret;
}

static void __exit probe_exit(void)
{
	struct arm_smccc_res gpu_result;
	struct arm_smccc_1_2_regs result;
	bool released;

	if (!held_page)
		return;
	if (gpu_lease) {
		arm_smccc_1_1_smc(OPENCCA_RSI_GPU_REVOKE, __pa(held_array), 1,
				  0, 0, 0, 0, 0, &gpu_result);
		released = gpu_result.a0 == 0;
	} else {
		result = call(IOMMU_UNMAP, held_domain, PAGE_GRANULE, 0, PAGE_GRANULE);
		released = result.a0 == 0;
		if (released) {
			result = call(IOMMU_DESTROY, held_domain, 0, 0, 0);
			released = result.a0 == 0;
		}
	}
	pr_info("[GUEST_IOMMU_TEST] backing_release=%s\n", released ? "PASS" : "FAIL");
	if (released) {
		if (held_array)
			free_page(held_array);
		free_page(held_page);
	}
}

module_init(probe_init);
module_exit(probe_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA Guest RSI managed-IOMMU probe");
