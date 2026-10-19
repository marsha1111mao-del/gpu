#include <linux/arm-smccc.h>
#include <linux/errno.h>
#include <linux/jiffies.h>
#include <linux/minmax.h>
#include <linux/module.h>
#include <linux/printk.h>
#include <linux/workqueue.h>

#define OPENCCA_DMA_STATUS 0xc400016bUL

static unsigned long peak_pages;
static unsigned long query_errors;
static struct delayed_work monitor_work;

static unsigned long active_pages(unsigned long selector)
{
	struct arm_smccc_res result;

	arm_smccc_1_1_smc(OPENCCA_DMA_STATUS, selector, 0, 0, 0, 0, 0, 0, &result);
	if (result.a0) {
		query_errors++;
		return 0;
	}
	return result.a1;
}

static void sample_pages(struct work_struct *work)
{
	peak_pages = max(peak_pages, active_pages(1));
	schedule_delayed_work(&monitor_work, msecs_to_jiffies(100));
}

static int __init monitor_init(void)
{
	unsigned long gpu_pages = active_pages(1);
	unsigned long dma_pages = active_pages(2);

	if (gpu_pages || dma_pages || query_errors)
		return -EBUSY;
	INIT_DELAYED_WORK(&monitor_work, sample_pages);
	schedule_delayed_work(&monitor_work, 0);
	return 0;
}

static void __exit monitor_exit(void)
{
	unsigned long final_pages, dma_pages;

	cancel_delayed_work_sync(&monitor_work);
	final_pages = active_pages(1);
	dma_pages = active_pages(2);
	pr_info("[GPU_LEASE_MONITOR] peak=%lu final=%lu dma_final=%lu errors=%lu\n",
		peak_pages, final_pages, dma_pages, query_errors);
}

module_init(monitor_init);
module_exit(monitor_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA RMM GPU lease lifecycle test monitor");
