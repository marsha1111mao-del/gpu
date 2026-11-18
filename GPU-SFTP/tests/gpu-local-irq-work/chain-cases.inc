
static struct dma_fence *leaf(void){struct dma_fence *f=calloc(1,sizeof(*f));assert(f);init_fence(f,false);return f;}
static struct dma_fence_chain *link_chain(struct dma_fence *f,struct dma_fence *prev)
{struct dma_fence_chain *c=calloc(1,sizeof(*c));assert(c);init_fence(&c->base,true);c->fence=dma_fence_get(f);c->prev=dma_fence_get(prev);return c;}
static void signal_scope(struct dma_fence *f,bool enabled)
{struct irq_work_local_batch b;assert(irq_work_local_begin(&b,enabled,true));dma_fence_signal(f);irq_work_local_end(&b);if(!enabled)pump();assert(!local_completion_batch[0] && !model_rcu && !model_preempt && !a.migration);}
int main(void)
{
 (void)b;(void)c;
 for(unsigned int enabled=0;enabled<2;enabled++){
  unsigned int start_alloc=allocations,start_free=releases;
  struct dma_fence *f=leaf();f->error=-5;struct dma_fence_chain *h=link_chain(f,NULL);
  assert(dma_fence_chain_enable_signaling(&h->base));
  assert(h->base.refs==2 && f->refs==3);signal_scope(f,enabled);
  assert(h->base.signaled && h->base.refs==1 && f->refs==2 && f->error==-5);
  dma_fence_put(&h->base);dma_fence_put(f);assert(allocations-start_alloc==releases-start_free);
  start_alloc=allocations;start_free=releases;
  struct dma_fence *first=leaf(),*second=leaf();struct dma_fence_chain *prev=link_chain(first,NULL),*head=link_chain(second,&prev->base);
  assert(dma_fence_chain_enable_signaling(&head->base));signal_scope(second,enabled);
  assert(!head->base.signaled && head->base.refs==2);
  /* The callback/IRQ-work union has now rearmed as an actual callback;
   * native irq_work_single's post-callback cmpxchg must not corrupt it. */
  assert(head->cb.func==dma_fence_chain_cb);
  signal_scope(first,enabled);assert(head->base.signaled && head->base.refs==1);
  dma_fence_put(&head->base);dma_fence_put(&prev->base);dma_fence_put(first);dma_fence_put(second);
  assert(allocations-start_alloc==releases-start_free);
  start_alloc=allocations;start_free=releases;
  f=leaf();h=link_chain(f,NULL);assert(dma_fence_chain_enable_signaling(&h->base));dma_fence_put(&h->base);
  signal_scope(f,enabled);dma_fence_put(f);assert(allocations-start_alloc==releases-start_free && !retired_n);
 }
 unsigned int start_alloc=allocations,start_free=releases;
 struct dma_fence *f=leaf();struct dma_fence_chain *heads[100];
 for(unsigned int i=0;i<100;i++){
  heads[i]=link_chain(i?&heads[i-1]->base:f,NULL);
  assert(dma_fence_chain_enable_signaling(&heads[i]->base));
 }
 struct irq_work_local_batch batch;assert(irq_work_local_begin(&batch,true,false));dma_fence_signal(f);irq_work_local_end(&batch);
 assert(heads[63]->base.signaled && !heads[64]->base.signaled && batch.drained==64 && batch.spilled==1);
 pump();assert(heads[99]->base.signaled);
 for(unsigned int i=100;i>0;i--){dma_fence_put(&heads[i-1]->base);}
 dma_fence_put(f);
 assert(allocations-start_alloc==releases-start_free);
 assert(!local_completion_batch[0] && !raised_list[0].first && !model_rcu && !model_preempt);
 puts("S8_CHAIN=PASS actualnativecallback/enable/rearm+cb_work_union/refgraph/errorpreserved/nativefallback/RCUselfree/100nodebudgetspill MODEL_ONLY");return 0;
}
