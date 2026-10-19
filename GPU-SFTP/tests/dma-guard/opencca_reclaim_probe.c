#include <linux/file.h>
#include <linux/fdtable.h>
#include <linux/kvm_host.h>
#include <linux/module.h>
#include <linux/pid.h>
#include <linux/sched/task.h>
#include <asm/rmi_cmds.h>

static int realm_pid;
module_param(realm_pid, int, 0400);
static unsigned long ipa;
module_param(ipa, ulong, 0400);

static int find_vm(const void *context, struct file *file, unsigned int descriptor)
{
	struct file **target = (struct file **)context;

	if (strcmp(file->f_path.dentry->d_name.name, "kvm-vm"))
		return 0;
	*target = get_file(file);
	return 1;
}

static int __init probe_init(void)
{
	struct pid *target_pid;
	struct task_struct *task;
	struct file *vm_file = NULL;
	struct kvm *kvm;
	struct rtt_entry before, after;
	unsigned long rd;
	int status, ret = -EIO;

	if (realm_pid <= 0 || !IS_ALIGNED(ipa, PAGE_SIZE))
		return -EINVAL;
	target_pid = find_get_pid(realm_pid);
	task = get_pid_task(target_pid, PIDTYPE_PID);
	put_pid(target_pid);
	if (!task)
		return -ESRCH;
	task_lock(task);
	iterate_fd(task->files, 0, find_vm, &vm_file);
	task_unlock(task);
	put_task_struct(task);
	if (!vm_file)
		return -ENOENT;
	kvm = vm_file->private_data;
	mutex_lock(&kvm->slots_lock);
	if (!kvm->arch.realm.rd)
		goto out;
	rd = virt_to_phys(kvm->arch.realm.rd);
	status = rmi_rtt_read_entry(rd, ipa, 3, &before);
	if (status || before.walk_level != 3 || before.state != RMI_ASSIGNED ||
	    before.ripas != RMI_RAM)
		goto out;
	status = rmi_data_destroy(rd, ipa, NULL, NULL);
	pr_info("[RECLAIM_TEST] active_backing_destroy_denied=%s status=%d\n",
		status == RMI_ERROR_INPUT ? "PASS" : "FAIL", status);
	if (status != RMI_ERROR_INPUT)
		goto out;
	status = rmi_rtt_read_entry(rd, ipa, 3, &after);
	if (status || after.walk_level != before.walk_level ||
	    after.state != before.state || after.desc != before.desc ||
	    after.ripas != before.ripas)
		goto out;
	pr_info("[RECLAIM_TEST] backing_entry_unchanged=PASS\n");
	ret = 0;
out:
	mutex_unlock(&kvm->slots_lock);
	fput(vm_file);
	return ret;
}

static void __exit probe_exit(void)
{
}

module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Direct Host RMI destroy attempt against a test-owned Realm backing page");
