
#define container_of(p,t,m) ((t *)((char *)(p)-__builtin_offsetof(t,m)))
struct list_head {struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head *h){h->next=h->prev=h;}
static void add_tail(struct list_head *n,struct list_head *h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void del(struct list_head *n){n->next->prev=n->prev;n->prev->next=n->next;}
#define list_entry(p,t,m) container_of(p,t,m)
#define list_for_each_entry_safe(p,n,h,m) \
 for(p=list_entry((h)->next,__typeof__(*p),m),n=list_entry(p->m.next,__typeof__(*p),m); \
 &p->m!=(h);p=n,n=list_entry(n->m.next,__typeof__(*n),m))
struct dma_fence;struct dma_fence_cb;
struct dma_fence_cb {struct list_head node;void (*func)(struct dma_fence *,struct dma_fence_cb *);};
struct dma_fence {unsigned int refs;bool chain,signaled;int error;struct list_head callbacks;};
struct dma_fence_chain {
 struct dma_fence base;struct dma_fence *prev;u64 prev_seqno;struct dma_fence *fence;
 union {struct dma_fence_cb cb;struct irq_work work;};
 unsigned long lock;
};
static unsigned int allocations,releases,notifies;
static void init_fence(struct dma_fence *f,bool is_chain){memset(f,0,sizeof(*f));f->refs=1;f->chain=is_chain;INIT_LIST_HEAD(&f->callbacks);allocations++;}
static struct dma_fence *dma_fence_get(struct dma_fence *f){if(f){assert(f->refs);f->refs++;}return f;}
static struct dma_fence_chain *to_dma_fence_chain(struct dma_fence *f){return f && f->chain?container_of(f,struct dma_fence_chain,base):NULL;}
static void dma_fence_put(struct dma_fence *f)
{
 if(!f)return;
 assert(f->refs);if(--f->refs)return;
 releases++;
 if(f->chain){struct dma_fence_chain *c=to_dma_fence_chain(f);dma_fence_put(c->prev);dma_fence_put(c->fence);}
 if(model_rcu)retire_after_rcu(f);else free(f);
}
static struct dma_fence *dma_fence_chain_contained(struct dma_fence *f){struct dma_fence_chain *c=to_dma_fence_chain(f);return c?c->fence:f;}
static struct dma_fence *dma_fence_chain_walk(struct dma_fence *f){struct dma_fence_chain *c=to_dma_fence_chain(f);struct dma_fence *next=c?dma_fence_get(c->prev):NULL;dma_fence_put(f);return next;}
#define dma_fence_chain_for_each(iter,head) for(iter=dma_fence_get(head);iter;iter=dma_fence_chain_walk(iter))
static int dma_fence_add_callback(struct dma_fence *f,struct dma_fence_cb *cb,void (*func)(struct dma_fence *,struct dma_fence_cb *))
{if(f->signaled)return -2;cb->func=func;INIT_LIST_HEAD(&cb->node);add_tail(&cb->node,&f->callbacks);return 0;}
static void dma_fence_signal(struct dma_fence *f)
{
 unsigned long flags;struct dma_fence_cb *cb,*next;
 preempt_disable();local_irq_save(flags);
 if(!f->signaled){
  f->signaled=true;notifies++;
  list_for_each_entry_safe(cb,next,&f->callbacks,node){del(&cb->node);INIT_LIST_HEAD(&cb->node);cb->func(f,cb);}
 }
 local_irq_restore(flags);preempt_enable();
}
static void init_irq_work(struct irq_work *w,void (*func)(struct irq_work *)){memset(w,0,sizeof(*w));w->func=func;}
static bool dma_fence_chain_enable_signaling(struct dma_fence *);
