#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
typedef struct {int value;} atomic_t;
static int atomic_read(atomic_t *p){return p->value;}
static void atomic_set(atomic_t *p,int v){p->value=v;}
static int atomic_fetch_or(int v,atomic_t *p){int old=p->value;p->value|=v;return old;}
static int atomic_cmpxchg(atomic_t *p,int old,int v){int was=p->value;if(was==old)p->value=v;return was;}
enum {
 CSD_FLAG_LOCK=0x01,
 IRQ_WORK_PENDING=0x01,IRQ_WORK_BUSY=0x02,IRQ_WORK_LAZY=0x04,IRQ_WORK_HARD_IRQ=0x08,
 IRQ_WORK_CLAIMED=(IRQ_WORK_PENDING|IRQ_WORK_BUSY),
 CSD_TYPE_ASYNC=0x00,CSD_TYPE_SYNC=0x10,CSD_TYPE_IRQ_WORK=0x20,CSD_TYPE_TTWU=0x30,
 CSD_FLAG_TYPE_MASK=0xF0
};
#define CONFIG_PREEMPT_RT model_rt
#define IS_ENABLED(x) (x)
#define EXPORT_SYMBOL_GPL(name)
static bool model_rt,model_irq,model_irqs;static unsigned int model_cpu,model_preempt,model_rcu,raises;
static u64 model_ticks=100;static bool tick_stopped;
struct task_struct {unsigned int migration;};
static struct task_struct a,b,c;static struct task_struct *current=&a;
#define DEFINE_PER_CPU(type,name) type name[2]
#define __this_cpu_read(name) ((name)[model_cpu])
#define __this_cpu_write(name,value) do{(name)[model_cpu]=(value);}while(0)
#define this_cpu_ptr(ptr) (&(*(ptr))[model_cpu])
static bool in_task(void){return !model_irq;}
static bool irqs_disabled(void){return model_irqs;}
static unsigned int smp_processor_id(void){return model_cpu;}
static void migrate_disable(void){current->migration++;}
static void migrate_enable(void){assert(current->migration);current->migration--;}
static void preempt_disable(void){model_preempt++;}
static void preempt_enable(void){assert(model_preempt);model_preempt--;}
#define local_irq_save(flags) do{flags=model_irqs;model_irqs=true;}while(0)
#define local_irq_restore(flags) do{model_irqs=!!(flags);}while(0)
#define BUG_ON(x) assert(!(x))
#define smp_mb() do{assert(model_irqs);}while(0)
#define lockdep_irq_work_enter(flags) do{assert(model_irqs);}while(0)
#define lockdep_irq_work_exit(flags) do{assert(model_irqs);}while(0)
struct llist_node {struct llist_node *next;};struct llist_head {struct llist_node *first;};
static void init_llist_head(struct llist_head *h){h->first=NULL;}
static bool llist_add(struct llist_node *n,struct llist_head *h){bool empty=!h->first;n->next=h->first;h->first=n;return empty;}
static struct llist_node *llist_del_first(struct llist_head *h){struct llist_node *n=h->first;if(n)h->first=n->next;return n;}
#define llist_entry(p,t,m) ((t *)((char *)(p)-__builtin_offsetof(t,m)))
struct rcuwait {unsigned int unused;};
struct irq_work {struct {struct llist_node llist;atomic_t a_flags;} node;void (*func)(struct irq_work *);struct rcuwait irqwait;};
static bool irq_work_is_hard(struct irq_work *w){return !!(atomic_read(&w->node.a_flags)&IRQ_WORK_HARD_IRQ);}
static bool arch_irq_work_has_interrupt(void){return true;}
static bool tick_nohz_tick_stopped(void){return tick_stopped;}
static bool trace_ipi_send_cpu_enabled(void){return false;}
#define trace_ipi_send_cpu(cpu,ip,func) do{(void)(cpu);(void)(ip);assert(func);}while(0)
#define _RET_IP_ 0
static void arch_irq_work_raise(void){assert(model_irqs);raises++;model_ticks+=20000;}
static void rcuwait_wake_up(struct rcuwait *w){(void)w;}
static u64 ktime_get_ns(void){return ++model_ticks;}
static DEFINE_PER_CPU(struct llist_head,raised_list);
static DEFINE_PER_CPU(struct llist_head,lazy_list);
static void *retired[16];static unsigned int retired_n;
static void rcu_read_lock(void){model_rcu++;}
static void rcu_read_unlock(void){assert(model_rcu);if(!--model_rcu){for(unsigned int i=0;i<retired_n;i++)free(retired[i]);retired_n=0;}}
static void retire_after_rcu(void *p){assert(model_rcu && retired_n<16);retired[retired_n++]=p;}
