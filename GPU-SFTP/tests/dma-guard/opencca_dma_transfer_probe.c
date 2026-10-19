// SPDX-License-Identifier: GPL-2.0-only
/* Real DMA to test-owned pages only; never target an active Realm or GPU BO. */
#include <linux/arm-smccc.h>
#include <linux/delay.h>
#include <linux/dmaengine.h>
#include <linux/dma-mapping.h>
#include <linux/iommu.h>
#include <linux/jiffies.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/of.h>

#define STATUS 0xc400016bUL
#define DELEGATE 0xc4000151UL
#define UNDELEGATE 0xc4000152UL
#define PREFIX "[DMA_TRANSFER_TEST] "

static char *controller = "fea10000.dma-controller";
module_param(controller, charp, 0400);
static char *channel = "dma0chan10";
module_param(channel, charp, 0400);

static struct dma_chan *probe_chan;
static struct device *dma_dev;
static struct page *src_page, *dst_page, *readback_page;
static dma_addr_t src_dma, dst_dma, readback_dma;
static bool src_mapped, dst_mapped, readback_mapped, delegated, quarantined;

static bool select_channel(struct dma_chan *chan, void *unused)
{
	struct device *dev = chan->device->dev;

	return !strcmp(dma_chan_name(chan), channel) &&
	       !strcmp(dev_name(dev), controller) &&
	       of_device_is_compatible(dev->of_node, "arm,pl330");
}

static unsigned long rmi(unsigned long function)
{
	struct arm_smccc_res res;

	arm_smccc_1_1_smc(function, page_to_phys(dst_page),
			 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	return res.a0;
}

static u8 pattern(size_t offset, u8 seed)
{
	return seed + offset * 29 + (offset >> 8);
}

/* Poll instead of installing module callbacks. On all paths terminate before
 * unmapping/freeing, including timeout and failed descriptor submission.
 */
static int transfer(const char *phase, dma_addr_t dst, dma_addr_t src)
{
	struct dma_async_tx_descriptor *desc;
	dma_cookie_t cookie;
	enum dma_status status;
	unsigned long deadline;

	desc = dmaengine_prep_dma_memcpy(probe_chan, dst, src, PAGE_SIZE,
					DMA_CTRL_ACK | DMA_PREP_INTERRUPT);
	if (!desc)
		return -EIO;
	cookie = dmaengine_submit(desc);
	if (dma_submit_error(cookie))
		return cookie;
	dma_async_issue_pending(probe_chan);
	deadline = jiffies + msecs_to_jiffies(3000);
	do {
		status = dma_async_is_tx_complete(probe_chan, cookie, NULL, NULL);
		if (status == DMA_COMPLETE || status == DMA_ERROR)
			break;
		msleep(1);
	} while (time_before(jiffies, deadline));
	pr_info(PREFIX "%s_dma_complete=%s cookie=%d status=%d bytes=%lu\n",
		phase, status == DMA_COMPLETE ? "PASS" : "FAIL",
		cookie, status, PAGE_SIZE);
	return status == DMA_COMPLETE ? 0 : -ETIMEDOUT;
}

static int cleanup_phase(void)
{
	unsigned long result;
	int ret;

	ret = dmaengine_terminate_sync(probe_chan);
	if (ret) {
		pr_err(PREFIX "cleanup=FAIL terminate_rc=%d resources_quarantined=1\n", ret);
		quarantined = true;
		return ret;
	}
	if (delegated) {
		result = rmi(UNDELEGATE);
		pr_info(PREFIX "undelegate=%s rmi_status=%lu\n",
			result ? "FAIL" : "PASS", result);
		if (result) {
			quarantined = true;
			return -EIO;
		}
		delegated = false;
	}
	/* CPU access is allowed only after DMA stopped and undelegation succeeded. */
	if (dst_mapped) {
		dma_unmap_page(dma_dev, dst_dma, PAGE_SIZE, DMA_BIDIRECTIONAL);
		dst_mapped = false;
	}
	if (readback_mapped) {
		dma_unmap_page(dma_dev, readback_dma, PAGE_SIZE, DMA_FROM_DEVICE);
		readback_mapped = false;
	}
	if (src_mapped) {
		dma_unmap_page(dma_dev, src_dma, PAGE_SIZE, DMA_TO_DEVICE);
		src_mapped = false;
	}
	return 0;
}

static int map_destination(void)
{
	dst_dma = dma_map_page(dma_dev, dst_page, 0, PAGE_SIZE, DMA_BIDIRECTIONAL);
	if (dma_mapping_error(dma_dev, dst_dma))
		return -EIO;
	dst_mapped = true;
	return 0;
}

static int run_phase(const char *phase, u8 seed, bool protect, bool map_first)
{
	u8 *src = page_address(src_page), *dst = page_address(dst_page);
	u8 *readback = page_address(readback_page);
	char read_phase[48];
	unsigned long result;
	size_t i, matches = 0, read_matches = 0;
	int ret = -EIO;

	for (i = 0; i < PAGE_SIZE; i++)
		src[i] = pattern(i, seed);
	memset(dst, 0x11, PAGE_SIZE);
	memset(readback, 0x22, PAGE_SIZE);
	src_dma = dma_map_page(dma_dev, src_page, 0, PAGE_SIZE, DMA_TO_DEVICE);
	if (dma_mapping_error(dma_dev, src_dma))
		goto cleanup;
	src_mapped = true;
	if (map_first && map_destination())
		goto cleanup;
	if (protect) {
		result = rmi(DELEGATE);
		pr_info(PREFIX "%s_delegation=%s rmi_status=%lu\n",
			phase, result ? "DENIED" : "SUCCEEDED", result);
		if (result)
			goto cleanup;
		delegated = true;
	}
	if (!map_first && map_destination())
		goto cleanup;
	if (protect) {
		readback_dma = dma_map_page(dma_dev, readback_page, 0, PAGE_SIZE, DMA_FROM_DEVICE);
		if (dma_mapping_error(dma_dev, readback_dma))
			goto cleanup;
		readback_mapped = true;
	}
	pr_info(PREFIX "%s_mapping=SUCCEEDED dma_equals_pa=%d\n",
		phase, dst_dma == page_to_phys(dst_page));
	ret = transfer(phase, dst_dma, src_dma);
	if (!ret && protect) {
		/* Read back through the device while the source is still DELEGATED.
		 * The CPU only checks both buffers after cleanup undelegates the page.
		 */
		snprintf(read_phase, sizeof(read_phase), "%s_read", phase);
		ret = transfer(read_phase, readback_dma, dst_dma);
	}
cleanup:
	if (cleanup_phase())
		return -EIO;
	if (ret)
		return ret;
	for (i = 0; i < PAGE_SIZE; i++)
		if (dst[i] == pattern(i, seed))
			matches++;
	pr_info(PREFIX "%s_data=%s matched=%zu total=%lu\n", phase,
		matches == PAGE_SIZE ? "PASS" : "FAIL", matches, PAGE_SIZE);
	if (protect) {
		for (i = 0; i < PAGE_SIZE; i++)
			if (readback[i] == pattern(i, seed))
				read_matches++;
		pr_info(PREFIX "%s_read_data=%s matched=%zu total=%lu\n", phase,
			read_matches == PAGE_SIZE ? "PASS" : "FAIL", read_matches, PAGE_SIZE);
		pr_info(PREFIX "%s_protection=%s\n", phase,
			matches == PAGE_SIZE && read_matches == PAGE_SIZE ?
			"FAIL_BYPASS_DETECTED" : "NOT_PROVEN");
	}
	return matches == PAGE_SIZE && (!protect || read_matches == PAGE_SIZE) ? 0 : -EIO;
}

static int __init transfer_probe_init(void)
{
	struct arm_smccc_res res;
	dma_cap_mask_t mask;
	unsigned long reservations_before;
	int ret;

	arm_smccc_1_1_smc(STATUS, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (res.a0 || res.a1 != 1UL)
		return -ENODEV;
	pr_info(PREFIX "guard_abi=%lu hardware_flags=%lu\n", res.a1, res.a2);
	arm_smccc_1_1_smc(STATUS, 2UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	if (res.a0)
		return -ENODEV;
	reservations_before = res.a1;
	dma_cap_zero(mask);
	dma_cap_set(DMA_MEMCPY, mask);
	probe_chan = dma_request_channel(mask, select_channel, NULL);
	if (!probe_chan)
		return -EBUSY;
	dma_dev = dmaengine_get_dma_device(probe_chan);
	/* This probe specifically verifies the non-IOMMU DMA path. */
	if (iommu_get_domain_for_dev(dma_dev) ||
	    of_find_property(probe_chan->device->dev->of_node, "iommus", NULL) ||
	    !probe_chan->device->device_terminate_all) {
		ret = -EOPNOTSUPP;
		goto release;
	}
	pr_info(PREFIX "exclusive_channel=PASS controller=%s channel=%s iommu=none\n",
		dev_name(probe_chan->device->dev), dma_chan_name(probe_chan));
	src_page = alloc_page(GFP_KERNEL | GFP_DMA32);
	dst_page = alloc_page(GFP_KERNEL | GFP_DMA32);
	readback_page = alloc_page(GFP_KERNEL | GFP_DMA32);
	if (!src_page || !dst_page || !readback_page) {
		ret = -ENOMEM;
		goto release;
	}
	ret = run_phase("normal", 0x53, false, true);
	if (!ret)
		ret = run_phase("existing_mapping", 0xa7, true, true);
	if (!ret)
		ret = run_phase("new_mapping", 0x3c, true, false);
	arm_smccc_1_1_smc(STATUS, 2UL, 0UL, 0UL, 0UL, 0UL, 0UL, 0UL, &res);
	pr_info(PREFIX "reservation_recovery=%s before=%lu after=%lu\n",
		!res.a0 && res.a1 == reservations_before ? "PASS" : "FAIL",
		reservations_before, res.a1);
	if (res.a0 || res.a1 != reservations_before)
		ret = -EIO;
release:
	if (quarantined) {
		/* Do not unload module text or release memory/channel if stop or
		 * undelegation failed. Recovery must inspect this owned test state.
		 */
		__module_get(THIS_MODULE);
		pr_err(PREFIX "probe_result=FAIL resources_quarantined=1\n");
		return 0;
	}
	dma_release_channel(probe_chan);
	if (src_page)
		__free_page(src_page);
	if (dst_page)
		__free_page(dst_page);
	if (readback_page)
		__free_page(readback_page);
	pr_info(PREFIX "cleanup=PASS\n");
	pr_info(PREFIX "probe_result=%s\n", ret ? "FAIL" : "BYPASS_REPRODUCED");
	return ret;
}

static void __exit transfer_probe_exit(void) { }
module_init(transfer_probe_init);
module_exit(transfer_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA test-owned delegated-page PL330 DMA bypass probe");
