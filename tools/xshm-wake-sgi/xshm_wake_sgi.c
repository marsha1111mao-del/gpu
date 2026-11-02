#include <linux/cpuhotplug.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/percpu.h>

#define XSHM_WAKE_SGI 15U

static unsigned int wake_irq;
static int hotplug_state;
static DEFINE_PER_CPU(unsigned long, fallback_count);

static irqreturn_t wake_handler(int irq, void *data)
{
	unsigned long *counter = data;

	(*counter)++;
	return IRQ_HANDLED;
}

static int wake_online(unsigned int cpu)
{
	enable_percpu_irq(wake_irq, IRQ_TYPE_EDGE_RISING);
	return 0;
}

static int wake_offline(unsigned int cpu)
{
	disable_percpu_irq(wake_irq);
	irq_set_irqchip_state(wake_irq, IRQCHIP_STATE_PENDING, false);
	return 0;
}

static int __init wake_init(void)
{
	struct device_node *node;
	struct irq_domain *domain;
	struct irq_fwspec specification = { .param_count = 1,
		.param = { XSHM_WAKE_SGI } };
	int status;

	node = of_find_compatible_node(NULL, NULL, "arm,gic-v3");
	if (!node)
		return -ENODEV;
	specification.fwnode = of_node_to_fwnode(node);
	domain = irq_find_matching_fwspec(&specification, DOMAIN_BUS_ANY);
	if (!domain || irq_find_mapping(domain, XSHM_WAKE_SGI)) {
		of_node_put(node);
		return -EBUSY;
	}
	wake_irq = irq_create_fwspec_mapping(&specification);
	of_node_put(node);
	if (!wake_irq)
		return -ENXIO;
	status = request_percpu_irq(wake_irq, wake_handler, "xshm-wake",
				  &fallback_count);
	if (status)
		goto dispose;
	status = cpuhp_setup_state(CPUHP_AP_ONLINE_DYN, "xshm/wake:online",
				   wake_online, wake_offline);
	if (status < 0)
		goto free_irq;
	hotplug_state = status;
	pr_info("XSHM_WAKE_SGI loaded intid=%u irq=%u\n", XSHM_WAKE_SGI, wake_irq);
	return 0;
free_irq:
	free_percpu_irq(wake_irq, &fallback_count);
dispose:
	irq_dispose_mapping(wake_irq);
	return status;
}

static void __exit wake_exit(void)
{
	unsigned long total = 0;
	unsigned int cpu;

	cpuhp_remove_state(hotplug_state);
	free_percpu_irq(wake_irq, &fallback_count);
	irq_dispose_mapping(wake_irq);
	for_each_possible_cpu(cpu)
		total += per_cpu(fallback_count, cpu);
	pr_info("XSHM_WAKE_SGI unloaded fallback=%lu\n", total);
}

module_init(wake_init);
module_exit(wake_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Reserved xshm SGI with normal Host fallback");
