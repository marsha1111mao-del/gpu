// SPDX-License-Identifier: GPL-2.0-only

#include <linux/mm.h>
#include <linux/module.h>
#include <linux/printk.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include <linux/vmalloc.h>

static unsigned long hpa;
module_param(hpa, ulong, 0400);
MODULE_PARM_DESC(hpa, "Page-aligned live Realm HPA to probe read-only");

static void *probe_va;

static int __init realm_host_access_probe_init(void)
{
	struct page *page;
	u8 *sample;
	u8 *first_nonzero;
	size_t dump_offset;
	int ret;

	if (!hpa || !PAGE_ALIGNED(hpa) || !pfn_valid(PHYS_PFN(hpa))) {
		pr_err("realm_host_access_probe: invalid hpa=0x%lx\n", hpa);
		return -EINVAL;
	}

	page = pfn_to_page(PHYS_PFN(hpa));
	probe_va = vmap(&page, 1, VM_MAP, PAGE_KERNEL);
	if (!probe_va) {
		pr_info("realm_host_access_probe: HOST_READ_DENIED hpa=0x%lx ret=%d\n",
			hpa, -ENOMEM);
		return 0;
	}

	sample = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!sample) {
		vunmap(probe_va);
		probe_va = NULL;
		return -ENOMEM;
	}

	ret = copy_from_kernel_nofault(sample, probe_va, PAGE_SIZE);
	if (ret) {
		pr_info("realm_host_access_probe: HOST_READ_DENIED hpa=0x%lx ret=%d\n",
			hpa, ret);
		kfree(sample);
		return 0;
	}

	first_nonzero = memchr_inv(sample, 0, PAGE_SIZE);
	dump_offset = first_nonzero ? round_down(first_nonzero - sample, 16) : 0;
	pr_crit("realm_host_access_probe: HOST_READ_SUCCEEDED hpa=0x%lx bytes=%lu first_nonzero=%ld\n",
		hpa, PAGE_SIZE, first_nonzero ? first_nonzero - sample : -1L);
	print_hex_dump(KERN_CRIT, "realm_host_access_probe: data ",
		       DUMP_PREFIX_OFFSET, 16, 1, sample + dump_offset,
		       min_t(size_t, 64, PAGE_SIZE - dump_offset), false);
	kfree(sample);
	return 0;
}

static void __exit realm_host_access_probe_exit(void)
{
	if (probe_va)
		vunmap(probe_va);
}

module_init(realm_host_access_probe_init);
module_exit(realm_host_access_probe_exit);

MODULE_DESCRIPTION("Read-only Host mapping probe for a live Realm HPA");
MODULE_LICENSE("GPL");
