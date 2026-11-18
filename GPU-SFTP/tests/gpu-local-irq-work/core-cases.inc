
struct item {struct irq_work work;unsigned int id,seen,again;bool self_free;};
static unsigned int order[512],order_n;
static void callback(struct irq_work *w)
{
 struct item *i=llist_entry(w,struct item,work);
 assert(model_irqs && model_preempt && model_rcu);
 assert(!(atomic_read(&w->node.a_flags)&IRQ_WORK_PENDING));
 i->seen++;order[order_n++]=i->id;
 if(i->again){i->again--;assert(irq_work_queue_local_batch(w));}
 if(i->self_free)retire_after_rcu(i);
}
static void init(struct item *i,unsigned int id){memset(i,0,sizeof(*i));i->work.func=callback;i->id=id;}
static void pump(void)
{
 unsigned long flags;bool before=model_irq;model_irq=true;preempt_disable();rcu_read_lock();local_irq_save(flags);
 for(unsigned int guard=0;guard<512;guard++){
  struct llist_node *n=llist_del_first(&raised_list[model_cpu]);
  if(!n)n=llist_del_first(&lazy_list[model_cpu]);
  if(!n){break;}
  irq_work_single(llist_entry(n,struct irq_work,node.llist));
  assert(guard<511);
 }
 local_irq_restore(flags);rcu_read_unlock();preempt_enable();model_irq=before;
}
static bool queue(struct item *i){unsigned long flags;local_irq_save(flags);bool r=irq_work_queue_local_batch(&i->work);local_irq_restore(flags);return r;}
int main(void)
{
 struct item x,y,foreign;struct irq_work_local_batch batch,nested,other;
 init(&x,1);init(&y,2);assert(irq_work_local_begin(&batch,true,true));
 assert(queue(&x) && !queue(&x) && queue(&y) && !raises);
 assert(batch.queued==2 && batch.coalesced==1 && !raised_list[0].first);
 irq_work_local_end(&batch);assert(x.seen==1 && y.seen==1 && order[0]==2 && order[1]==1);
 assert(batch.drained==2 && !batch.spilled && !batch.owner && !local_completion_batch[0] && !a.migration && !model_preempt && !model_rcu);
 init(&x,3);assert(irq_work_local_begin(&batch,false,true));assert(queue(&x));
 assert(batch.native_calls==1 && batch.native_samples==1 && batch.native_ns>=20000 && !batch.queued);
 irq_work_local_end(&batch);assert(!x.seen);pump();assert(x.seen==1);
 init(&x,4);init(&foreign,5);assert(irq_work_local_begin(&batch,true,false));assert(queue(&x));
 assert(!irq_work_local_begin(&nested,true,false));
 current=&b;assert(queue(&foreign));assert(!irq_work_local_begin(&nested,true,false));
 assert(batch.queued==1 && !foreign.seen);current=&a;
 irq_work_local_end(&batch);assert(x.seen==1 && !foreign.seen);pump();assert(foreign.seen==1);
 init(&x,6);init(&y,7);assert(irq_work_local_begin(&batch,true,false));assert(queue(&x));
 model_cpu=1;current=&c;assert(irq_work_local_begin(&other,true,false));assert(queue(&y));irq_work_local_end(&other);assert(y.seen==1 && !x.seen && !local_completion_batch[1]);
 model_cpu=0;current=&a;irq_work_local_end(&batch);assert(x.seen==1);
 init(&x,8);assert(irq_work_local_begin(&batch,true,false));model_irq=true;assert(queue(&x));model_irq=false;
 assert(!batch.queued);irq_work_local_end(&batch);pump();assert(x.seen==1);
 for(unsigned int kind=0;kind<2;kind++){
  init(&x,10+kind);x.work.node.a_flags.value=kind?IRQ_WORK_HARD_IRQ:IRQ_WORK_LAZY;
  assert(irq_work_local_begin(&batch,true,true));assert(queue(&x));assert(!batch.queued && batch.native_calls==1);
  irq_work_local_end(&batch);pump();assert(x.seen==1);
 }
 model_rt=true;assert(!irq_work_local_begin(&batch,true,false) && !a.migration);model_rt=false;
 model_irq=true;assert(!irq_work_local_begin(&batch,true,false));model_irq=false;
 model_irqs=true;assert(!irq_work_local_begin(&batch,true,false));model_irqs=false;
 init(&x,12);x.again=99;assert(irq_work_local_begin(&batch,true,false));assert(queue(&x));
 unsigned int before=raises;irq_work_local_end(&batch);
 assert(x.seen==64 && batch.drained==64 && batch.queued==65 && batch.spilled==1 && raises==before+1);
 assert(raised_list[0].first && !batch.works.first && !local_completion_batch[0]);
 pump();assert(x.seen==100 && !(atomic_read(&x.work.node.a_flags)&IRQ_WORK_CLAIMED));
 struct item *self=calloc(1,sizeof(*self));assert(self);init(self,13);self->self_free=true;
 assert(irq_work_local_begin(&batch,true,false));assert(queue(self));irq_work_local_end(&batch);
 assert(!retired_n && !model_rcu && !local_completion_batch[0]);
 puts("S8_BATCH=PASS nativeclaim/single/PENDING_BUSY/coalescing/owner+CPU/IRQ_RTfallback/requeue/budgetspill/RCUselfree/scopecleanup MODEL_ONLY");return 0;
}
