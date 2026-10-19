#include <linux/bitfield.h>
#include <linux/mm.h>
#include <linux/module.h>

#include <asm/io.h>
#include <asm/rmi_cmds.h>
#include <asm/sysreg.h>

struct probe_realm {
	void *rd;
	void *rtt;
	bool rd_delegated;
	bool rtt_delegated;
	bool created;
};

static int prepare_realm(struct probe_realm *realm)
{
	realm->rd = (void *)get_zeroed_page(GFP_KERNEL);
	realm->rtt = (void *)get_zeroed_page(GFP_KERNEL);
	if (!realm->rd || !realm->rtt)
		return -ENOMEM;
	if (rmi_granule_delegate(virt_to_phys(realm->rd)))
		return -EIO;
	realm->rd_delegated = true;
	if (rmi_granule_delegate(virt_to_phys(realm->rtt)))
		return -EIO;
	realm->rtt_delegated = true;
	return 0;
}

static int destroy_realm(struct probe_realm *realm)
{
	if (realm->created && rmi_realm_destroy(virt_to_phys(realm->rd)))
		return -EIO;
	realm->created = false;
	return 0;
}

static int release_realm(struct probe_realm *realm)
{
	int result = 0;

	if (destroy_realm(realm))
		return -EIO;
	if (realm->rd_delegated && rmi_granule_undelegate(virt_to_phys(realm->rd)))
		result = -EIO;
	else
		free_page((unsigned long)realm->rd);
	if (realm->rtt_delegated && rmi_granule_undelegate(virt_to_phys(realm->rtt)))
		result = -EIO;
	else
		free_page((unsigned long)realm->rtt);
	return result;
}

static int check_create(struct probe_realm *realm, struct realm_params *params,
			unsigned int vmid, int expected, const char *name)
{
	int result;

	params->vmid = vmid;
	params->rtt_base = virt_to_phys(realm->rtt);
	result = rmi_realm_create(virt_to_phys(realm->rd), virt_to_phys(params));
	if (!result)
		realm->created = true;
	pr_info("[VMID_TEST] %s=%s vmid=%u status=%d expected=%d\n",
		name, result == expected ? "PASS" : "FAIL", vmid, result, expected);
	return result == expected ? 0 : -EIO;
}

static int __init vmid_probe_init(void)
{
	struct probe_realm first = {}, second = {};
	struct realm_params *params;
	unsigned long features;
	unsigned int bits, limit;
	int result, cleanup;

	if (!IS_ENABLED(CONFIG_KVM_ARM_OPENCCA) || PAGE_SIZE != 4096)
		return -EOPNOTSUPP;
	bits = SYS_FIELD_GET(ID_AA64MMFR1_EL1, VMIDBits,
			     read_sysreg(id_aa64mmfr1_el1));
	if (bits != ID_AA64MMFR1_EL1_VMIDBits_8 &&
	    bits != ID_AA64MMFR1_EL1_VMIDBits_16)
		return -EOPNOTSUPP;
	bits = bits == ID_AA64MMFR1_EL1_VMIDBits_16 ? 16 : 8;
	limit = 1U << bits;
	params = (struct realm_params *)get_zeroed_page(GFP_KERNEL);
	if (!params)
		return -ENOMEM;
	result = -EIO;
	if (rmi_features(0, &features))
		goto out;
	params->s2sz = 32;
	params->num_bps = FIELD_GET(RMI_FEATURE_REGISTER_0_NUM_BPS, features);
	params->num_wps = FIELD_GET(RMI_FEATURE_REGISTER_0_NUM_WPS, features);
	params->rtt_level_start = 1;
	params->rtt_num_start = 1;
	if (prepare_realm(&first) || prepare_realm(&second))
		goto out;
	if (check_create(&first, params, 0, RMI_ERROR_INPUT, "host_zero_denied") ||
	    check_create(&first, params, limit / 2 - 1, RMI_ERROR_INPUT,
			 "ordinary_upper_denied") ||
	    check_create(&first, params, limit / 2, RMI_SUCCESS,
			 "realm_lower_allowed") ||
	    check_create(&second, params, limit / 2, RMI_ERROR_INPUT,
			 "duplicate_denied") || destroy_realm(&first) ||
	    check_create(&second, params, limit / 2, RMI_SUCCESS,
			 "destroy_allows_reuse") || destroy_realm(&second) ||
	    check_create(&first, params, limit - 1, RMI_SUCCESS,
			 "realm_upper_allowed"))
		goto out;
	result = 0;
out:
	cleanup = release_realm(&first);
	cleanup |= release_realm(&second);
	free_page((unsigned long)params);
	pr_info("[VMID_TEST] result=%s bits=%u cleanup=%s\n",
		!result && !cleanup ? "PASS" : "FAIL", bits,
		cleanup ? "FAIL_RETAINED" : "PASS");
	return result ?: cleanup;
}

static void __exit vmid_probe_exit(void)
{
}

module_init(vmid_probe_init);
module_exit(vmid_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("OpenCCA trusted VMID partition and reuse verification");
