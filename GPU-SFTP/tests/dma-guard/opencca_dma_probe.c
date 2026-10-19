// SPDX-License-Identifier: GPL-2.0-only
/* Admission tests use an unattached Rockchip domain: no device DMA is issued. */
#include <linux/arm-smccc.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/iommu.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/scatterlist.h>

#define GUARD 0xc400016aUL
#define STATUS 0xc400016bUL
#define DELEGATE 0xc4000151UL
#define UNDELEGATE 0xc4000152UL

static bool gpu_required;
module_param(gpu_required, bool, 0400);
static bool probe_bypass;
module_param(probe_bypass, bool, 0400);
static char *device = "fdb50000.video-codec";
module_param(device, charp, 0400);

static int check(const char *name, bool passed)
{
	pr_info("[DMA_GUARD_TEST] %s=%s\n", name, passed ? "PASS" : "FAIL");
	return passed ? 0 : -EIO;
}

#ifdef CONFIG_OPENCCA_MANAGED_IOMMU
static int managed_direct_mapping(struct iommu_domain *domain, phys_addr_t pa)
{
	size_t mapped = 0;
	int ret;

	ret = domain->ops->map_pages(domain, PAGE_SIZE, pa, PAGE_SIZE, 1,
				     IOMMU_READ, GFP_KERNEL, &mapped);
	return check("direct_driver_delegation_denied",
		     ret == -EPERM && mapped == 0 &&
		     !iommu_iova_to_phys(domain, PAGE_SIZE));
}
#endif

static int denied_mapping(struct iommu_domain *domain, unsigned long iova,
		phys_addr_t pa, size_t size, int prot, const char *name)
{
	int ret = iommu_map(domain, iova, pa, size, prot, GFP_KERNEL);

	if (!ret)
		iommu_unmap(domain, iova, size);
	return check(name, ret == -EPERM && !iommu_iova_to_phys(domain, iova));
}

static int denied_sg(struct iommu_domain *domain, struct page *allowed,
		struct page *protected, const char *denied_name, const char *rollback_name)
{
	struct scatterlist sg[4];
	struct arm_smccc_res res;
	unsigned long before, iova = 0x1000000UL;
	ssize_t mapped;
	bool empty = true;
	int ret;

	arm_smccc_1_1_smc(STATUS, 2UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (res.a0)
		return -EIO;
	before = res.a1;
	sg_init_table(sg, ARRAY_SIZE(sg));
	/* Repeating a physical page prevents coalescing the entire SG. At
	 * least the first allowed segment is installed before the refusal.
	 */
	sg_set_page(&sg[0], allowed, PAGE_SIZE, 0);
	sg_set_page(&sg[1], allowed, PAGE_SIZE, 0);
	sg_set_page(&sg[2], protected, PAGE_SIZE, 0);
	sg_set_page(&sg[3], allowed, PAGE_SIZE, 0);
	mapped = iommu_map_sg(domain, iova, sg, ARRAY_SIZE(sg),
			      IOMMU_READ | IOMMU_WRITE, GFP_KERNEL);
	if (mapped > 0)
		iommu_unmap(domain, iova, mapped);
	ret = check(denied_name, mapped == -EPERM);
	for (size_t i = 0; i < ARRAY_SIZE(sg); i++)
		empty &= !iommu_iova_to_phys(domain, iova + i * PAGE_SIZE);
	arm_smccc_1_1_smc(STATUS, 2UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	return check(rollback_name, !ret && empty && !res.a0 && res.a1 == before);
}

static int __init probe_init(void)
{
	struct arm_smccc_res res;
	struct iommu_domain *domain;
	struct device *dev;
	struct page *page, *allowed_page;
	phys_addr_t pa, gpu_pa;
	unsigned long reservations_before;
	bool delegated = false, mapped = false, attached = false;
	int ret;
	size_t done = 0;

	arm_smccc_1_1_smc(STATUS, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (res.a0 || res.a1 != 1UL)
		return -ENODEV;
	arm_smccc_1_1_smc(STATUS, 1UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (gpu_required && (!res.a1 || !res.a2))
		return -EAGAIN;
	gpu_pa = res.a1 ? res.a2 : 0;
	arm_smccc_1_1_smc(STATUS, 2UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (res.a0)
		return -ENODEV;
	reservations_before = res.a1;
	dev = bus_find_device_by_name(&platform_bus_type, NULL, device);
	if (!dev)
		return -ENODEV;
	domain = iommu_paging_domain_alloc(dev);
	if (IS_ERR(domain)) {
		ret = PTR_ERR(domain);
		put_device(dev);
		return ret;
	}
	page = alloc_page(GFP_KERNEL | GFP_DMA32);
	allowed_page = alloc_page(GFP_KERNEL | GFP_DMA32);
	if (!page || !allowed_page) {
		if (page)
			__free_page(page);
		if (allowed_page)
			__free_page(allowed_page);
		ret = -ENOMEM;
		goto put_device;
	}
	pa = page_to_phys(page);
	{
		struct scatterlist sg[2];
		ssize_t mapped_bytes;

		sg_init_table(sg, ARRAY_SIZE(sg));
		sg_set_page(&sg[0], page, PAGE_SIZE, 0);
		sg_set_page(&sg[1], page, PAGE_SIZE, 0);
		mapped_bytes = iommu_map_sg(domain, 0x1000000UL, sg, ARRAY_SIZE(sg),
					    IOMMU_READ | IOMMU_WRITE, GFP_KERNEL);
		ret = check("allowed_sg_mapping", mapped_bytes == 2 * PAGE_SIZE &&
			    iommu_iova_to_phys(domain, 0x1000000UL) == pa &&
			    iommu_iova_to_phys(domain, 0x1000000UL + PAGE_SIZE) == pa);
		if (mapped_bytes > 0) {
			size_t unmapped = iommu_unmap(domain, 0x1000000UL, mapped_bytes);

			ret |= check("allowed_sg_unmap", unmapped == mapped_bytes);
		}
		if (ret)
			goto free_page;
	}
	ret = iommu_map(domain, PAGE_SIZE, pa, PAGE_SIZE,
			IOMMU_READ | IOMMU_WRITE, GFP_KERNEL);
	if (ret)
		goto free_page;
	mapped = true;
	ret = check("allowed_mapping", iommu_iova_to_phys(domain, PAGE_SIZE) == pa);
	if (ret)
		goto free_page;
	arm_smccc_1_1_smc(DELEGATE, pa, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (!res.a0) {
		/* The guard failed: restore the test-owned page before cleanup. */
		delegated = true;
		ret = check("existing_dma_blocks_delegation", false);
		goto free_page;
	}
	ret = check("existing_dma_blocks_delegation", res.a0 == 1UL);
	if (ret)
		goto free_page;
	ret = check("allowed_unmap", iommu_unmap(domain, PAGE_SIZE, PAGE_SIZE) == PAGE_SIZE);
	mapped = iommu_iova_to_phys(domain, PAGE_SIZE) != 0;
	if (ret || mapped)
		goto free_page;
	arm_smccc_1_1_smc(DELEGATE, pa, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	delegated = res.a0 == 0UL;
	ret = check("delegation_after_unmap", delegated);
	if (ret)
		goto free_page;
	ret = iommu_map(domain, PAGE_SIZE, pa, PAGE_SIZE, IOMMU_READ, GFP_KERNEL);
	mapped = ret == 0;
	ret = check("delegated_page_mapping_denied", ret == -EPERM &&
			 !iommu_iova_to_phys(domain, PAGE_SIZE));
	if (ret)
		goto free_page;
	/* Exercise the whole covering interval, not just its first page. */
	ret = iommu_map(domain, 0x400000UL, pa & ~0x3fffffUL,
			0x400000UL, IOMMU_READ, GFP_KERNEL);
	if (ret == 0)
		iommu_unmap(domain, 0x400000UL, 0x400000UL);
	ret = check("covering_mapping_denied", ret == -EPERM &&
			 !iommu_iova_to_phys(domain, 0x400000UL));
	if (ret)
		goto free_page;
	ret = denied_mapping(domain, 0x20000UL, pa, PAGE_SIZE, IOMMU_WRITE,
			     "delegated_page_write_mapping_denied");
	if (!ret)
		ret = denied_mapping(domain, 0x30000UL, pa, PAGE_SIZE, IOMMU_READ,
				     "delegated_page_alias_mapping_denied");
	if (!ret)
		ret = denied_sg(domain, allowed_page, page, "delegated_sg_mapping_denied",
				"delegated_sg_rollback");
	if (ret)
		goto free_page;
#ifdef CONFIG_OPENCCA_MANAGED_IOMMU
	ret = managed_direct_mapping(domain, pa);
	if (ret)
		goto free_page;
#endif
	if (probe_bypass) {
		/* Deliberately bypass generic admission on an unattached domain.
		 * A successful write exposes missing configuration enforcement.
		 */
		int bypass_ret = domain->ops->map_pages(domain, PAGE_SIZE, pa,
			PAGE_SIZE, 1, IOMMU_READ, GFP_KERNEL, &done);

		pr_info("[DMA_GUARD_TEST] configuration_protection=%s direct_ret=%d mapped=%zu\n",
			(!bypass_ret && done) ? "FAIL_BYPASS_DETECTED" : "NOT_PROVEN",
			bypass_ret, done);
		if (done) {
			struct iommu_iotlb_gather gather;
			size_t cleared;

			iommu_iotlb_gather_init(&gather);
			cleared = domain->ops->unmap_pages(domain, PAGE_SIZE, PAGE_SIZE, 1, &gather);
			iommu_iotlb_sync(domain, &gather);
			ret = check("direct_mapping_cleanup", cleared == done &&
				    !iommu_iova_to_phys(domain, PAGE_SIZE));
			if (ret)
				goto free_page;
		}
	}
	arm_smccc_1_1_smc(UNDELEGATE, pa, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (res.a0) {
		ret = check("undelegation", false);
		goto free_page;
	}
	delegated = false;
	ret = iommu_map(domain, PAGE_SIZE, pa, PAGE_SIZE, IOMMU_READ, GFP_KERNEL);
	mapped = ret == 0;
	ret = check("mapping_after_undelegation", mapped);
	if (ret)
		goto free_page;
	ret = check("final_unmap", iommu_unmap(domain, PAGE_SIZE, PAGE_SIZE) == PAGE_SIZE);
	mapped = iommu_iova_to_phys(domain, PAGE_SIZE) != 0;
	if (ret || mapped)
		goto free_page;
	if (gpu_pa) {
		ret = denied_mapping(domain, PAGE_SIZE, gpu_pa, PAGE_SIZE, IOMMU_READ,
				     "live_gpu_page_mapping_denied");
		if (!ret)
			ret = denied_mapping(domain, 0x20000UL, gpu_pa, PAGE_SIZE, IOMMU_WRITE,
					     "live_gpu_write_mapping_denied");
		if (!ret)
			ret = denied_mapping(domain, 0x30000UL, gpu_pa, PAGE_SIZE,
					     IOMMU_READ | IOMMU_WRITE, "live_gpu_alias_mapping_denied");
		if (!ret)
			ret = denied_mapping(domain, 0x400000UL, gpu_pa & ~0x3fffffUL,
					     0x400000UL, IOMMU_READ, "live_gpu_covering_mapping_denied");
		if (!ret && !pfn_valid(PHYS_PFN(gpu_pa)))
			ret = -EINVAL;
		if (!ret)
			ret = denied_sg(domain, allowed_page, pfn_to_page(PHYS_PFN(gpu_pa)),
					"live_gpu_sg_mapping_denied", "live_gpu_sg_rollback");
		if (ret)
			goto free_page;
	} else {
		pr_info("[DMA_GUARD_TEST] live_gpu_page_mapping_denied=NOT_RUN\n");
	}
	arm_smccc_1_1_smc(STATUS, 2UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	ret = check("reservation_recovery", !res.a0 && res.a1 == reservations_before);
	if (ret)
		goto free_page;
#ifdef CONFIG_OPENCCA_MANAGED_IOMMU
	pr_info("[DMA_GUARD_TEST] managed_iommu=ENABLED\n");
	ret = check("managed_domain_root_ownership",
		    iommu_attach_device(domain, dev) == 0);
	if (ret)
		goto free_page;
	attached = true;
	ret = iommu_map(domain, PAGE_SIZE, pa, PAGE_SIZE, IOMMU_READ, GFP_KERNEL);
	mapped = ret == 0;
	ret = check("managed_recovery_mapping", mapped &&
		    iommu_iova_to_phys(domain, PAGE_SIZE) == pa);
	if (ret)
		goto free_page;
	iommu_detach_device(domain, dev);
	attached = false;
	ret = check("unbind_parking", iommu_get_domain_for_dev(dev) != domain);
	if (ret)
		goto free_page;
	ret = check("managed_recovery_after_unbind",
		    iommu_attach_device(domain, dev) == 0);
	if (ret)
		goto free_page;
	attached = true;
	ret = check("recovery_mapping_after_rebind",
		    iommu_iova_to_phys(domain, PAGE_SIZE) == pa);
	if (ret)
		goto free_page;
	ret = check("recovery_unmap",
		    iommu_unmap(domain, PAGE_SIZE, PAGE_SIZE) == PAGE_SIZE);
	mapped = iommu_iova_to_phys(domain, PAGE_SIZE) != 0;
	if (ret || mapped)
		goto free_page;
	iommu_detach_device(domain, dev);
	attached = false;
#else
	pr_info("[DMA_GUARD_TEST] managed_iommu=DISABLED\n");
#endif
	pr_info("[DMA_GUARD_TEST] admission_result=PASS dma_reservations=%lu\n", res.a1);
	ret = 0;
free_page:
	if (attached)
		iommu_detach_device(domain, dev);
	if (mapped)
		iommu_unmap(domain, PAGE_SIZE, PAGE_SIZE);
	if (delegated) {
		arm_smccc_1_1_smc(UNDELEGATE, pa, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
		if (res.a0) {
			pr_err("[DMA_GUARD_TEST] cleanup=FAIL page quarantined\n");
			page = NULL;
			ret = -EIO;
		}
	}
	if (page)
		__free_page(page);
	__free_page(allowed_page);
	iommu_domain_free(domain);
put_device:
	put_device(dev);
	return ret;
}

static void __exit probe_exit(void) { }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA DMA admission and configuration bypass probe");
