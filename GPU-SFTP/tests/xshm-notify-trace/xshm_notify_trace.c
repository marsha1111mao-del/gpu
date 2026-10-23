#include <linux/debugfs.h>
#include <linux/kprobes.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/seq_file.h>
#include <linux/tracepoint.h>
#include <linux/vmalloc.h>
#include <asm/arch_timer.h>

#define TRACE_CAPACITY 262144U

struct notify_record {
	u64 tick0, tick1, target, state;
	u32 kind, cpu, tid, peer;
};

struct notify_probe_data {
	u64 tick, target;
};

static struct notify_record *records;
static u32 record_count;
static u64 dropped, period_ticks, window_ticks;
static DEFINE_RAW_SPINLOCK(record_lock);
static struct dentry *directory;
static struct tracepoint *wakeup_point, *switch_point;

static u64 trace_counter(void)
{
	isb();
	return read_sysreg(cntpct_el0);
}

static bool trace_sample(u64 tick)
{
	return tick % period_ticks < window_ticks;
}

static bool trace_vcpu(struct task_struct *task)
{
	return !strncmp(task->comm, "fc_vcpu", 7);
}

static void trace_record(const struct notify_record *record)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&record_lock, flags);
	if (record_count < TRACE_CAPACITY)
		records[record_count++] = *record;
	else
		dropped++;
	raw_spin_unlock_irqrestore(&record_lock, flags);
}

static int wake_enter(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct notify_probe_data *data = (void *)instance->data;
	u64 tick = trace_counter();

	if (!trace_sample(tick))
		return 1;
	data->tick = tick;
	data->target = regs_get_kernel_argument(regs, 0);
	return 0;
}

static int wake_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct notify_probe_data *data = (void *)instance->data;
	struct notify_record record = {
		.kind = 1, .cpu = raw_smp_processor_id(), .tid = current->pid,
		.tick0 = data->tick, .tick1 = trace_counter(), .target = data->target,
	};

	trace_record(&record);
	return 0;
}

static struct kretprobe wake_probe = {
	.kp.symbol_name = "kvm_realm_xshm_wake",
	.entry_handler = wake_enter,
	.handler = wake_return,
	.data_size = sizeof(struct notify_probe_data),
	.maxactive = 64,
};

static void trace_wakeup(void *unused, struct task_struct *task)
{
	struct notify_record record = {
		.kind = 2, .tick0 = trace_counter(), .cpu = raw_smp_processor_id(),
		.tid = current->pid, .peer = task->pid,
	};

	if (trace_vcpu(task) && trace_sample(record.tick0))
		trace_record(&record);
}

static void trace_switch(void *unused, bool preempt, struct task_struct *previous,
			 struct task_struct *next, unsigned int state)
{
	struct notify_record record = {
		.kind = 3, .tick0 = trace_counter(), .cpu = raw_smp_processor_id(),
		.tid = previous->pid, .peer = next->pid, .state = state,
	};

	if ((trace_vcpu(previous) || trace_vcpu(next)) && trace_sample(record.tick0))
		trace_record(&record);
}

static void find_tracepoints(struct tracepoint *point, void *unused)
{
	if (!strcmp(point->name, "sched_wakeup"))
		wakeup_point = point;
	if (!strcmp(point->name, "sched_switch"))
		switch_point = point;
}

static int trace_show(struct seq_file *stream, void *unused)
{
	struct notify_record record;
	unsigned long flags;
	u32 count, index;
	u64 lost;

	raw_spin_lock_irqsave(&record_lock, flags);
	count = record_count;
	lost = dropped;
	raw_spin_unlock_irqrestore(&record_lock, flags);
	seq_printf(stream, "HOST_XSHM_TRACE clock=cntpct freq=%llu count=%u dropped=%llu missed=%d period=%llu window=%llu\n",
		   read_sysreg(cntfrq_el0), count, lost, wake_probe.nmissed,
		   period_ticks, window_ticks);
	seq_puts(stream, "kind cpu tid peer tick0 tick1 target state\n");
	for (index = 0; index < count; index++) {
		raw_spin_lock_irqsave(&record_lock, flags);
		record = records[index];
		raw_spin_unlock_irqrestore(&record_lock, flags);
		seq_printf(stream, "%u %u %u %u %llu %llu %llu %llu\n",
			   record.kind, record.cpu, record.tid, record.peer,
			   record.tick0, record.tick1, record.target, record.state);
	}
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(trace);

static int __init notify_trace_init(void)
{
	struct dentry *file;
	int ret;

	period_ticks = read_sysreg(cntfrq_el0) / 10;
	window_ticks = read_sysreg(cntfrq_el0) / 500;
	if (!window_ticks)
		return -EINVAL;
	records = vzalloc(array_size(TRACE_CAPACITY, sizeof(*records)));
	if (!records)
		return -ENOMEM;
	for_each_kernel_tracepoint(find_tracepoints, NULL);
	if (!wakeup_point || !switch_point) {
		ret = -ENOENT;
		goto free_records;
	}
	directory = debugfs_create_dir("xshm_notify_trace", NULL);
	if (IS_ERR(directory)) {
		ret = PTR_ERR(directory);
		goto free_records;
	}
	file = debugfs_create_file("samples", 0400, directory, NULL, &trace_fops);
	if (IS_ERR(file)) {
		ret = PTR_ERR(file);
		goto remove_directory;
	}
	ret = register_kretprobe(&wake_probe);
	if (ret)
		goto remove_directory;
	ret = tracepoint_probe_register(wakeup_point, trace_wakeup, NULL);
	if (ret)
		goto remove_probe;
	ret = tracepoint_probe_register(switch_point, trace_switch, NULL);
	if (!ret)
		return 0;
	tracepoint_probe_unregister(wakeup_point, trace_wakeup, NULL);
	tracepoint_synchronize_unregister();
remove_probe:
	unregister_kretprobe(&wake_probe);
remove_directory:
	debugfs_remove_recursive(directory);
free_records:
	vfree(records);
	return ret;
}

static void __exit notify_trace_exit(void)
{
	tracepoint_probe_unregister(switch_point, trace_switch, NULL);
	tracepoint_probe_unregister(wakeup_point, trace_wakeup, NULL);
	tracepoint_synchronize_unregister();
	unregister_kretprobe(&wake_probe);
	debugfs_remove_recursive(directory);
	vfree(records);
}

module_init(notify_trace_init);
module_exit(notify_trace_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded physical-counter XSHM wake and scheduler diagnosis");
