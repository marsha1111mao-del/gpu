// SPDX-License-Identifier: GPL-2.0-only
/* Actual Client functions; host doubles do not validate Linux concurrency or GPU. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "linux/realm_gpu.h"
#include "drm/panthor_drm.h"
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;
#define PAGE_SIZE 4096UL
#define PAGE_SHIFT 12
#define SZ_16M (16UL * 1024 * 1024)
#define GFP_KERNEL 0
#define HZ 1000
#define U32_MAX UINT32_MAX
#define PANTHOR_VMSHM_MAX_VM_BIND_OPS 8
#define PANTHOR_VMSHM_MAX_VM_BIND_SYNCS 8
#define PANTHOR_CLIENT_SYNC_FILE_WAIT_NSEC 60000000000ULL
#define PANTHOR_CLIENT_SYNC_OP_FLAGS_MASK (DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_MASK | DRM_PANTHOR_SYNC_OP_SIGNAL)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define max_t(t,a,b) ((t)(a)>(t)(b)?(t)(a):(t)(b))
#define IS_ALIGNED(x,a) (!((x)&((a)-1)))
#define READ_ONCE(x) (x)
#define offsetofend(t,m) (offsetof(t,m)+sizeof(((t *)0)->m))
#define u64_to_user_ptr(x) ((void *)(uintptr_t)(x))
static unsigned long jiffies;
#define nsecs_to_jiffies(x) ((unsigned long)((x)/1000000ULL))
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
static int fail_alloc_after = -1;
static void *kzalloc(size_t n, int flags) {
    if (fail_alloc_after==0) return NULL;
    if (fail_alloc_after>0) fail_alloc_after--;
    return calloc(1,n);
}
static void kfree(void *p) { free(p); }
typedef struct { int value; } refcount_t;
static void refcount_set(refcount_t *r,int n) { r->value=n; }
static void refcount_inc(refcount_t *r) { assert(r->value>0);r->value++; }
static bool refcount_dec_and_test(refcount_t *r) { assert(r->value>0);return !--r->value; }
typedef struct { int value; } atomic_t;
static inline int atomic_read(atomic_t *a) { return a->value; }
static void atomic_inc(atomic_t *a) { a->value++; }
static void atomic_dec(atomic_t *a) { assert(a->value>0);a->value--; }
struct mutex { bool held; };
static void mutex_lock(struct mutex *m) { assert(!m->held);m->held=true; }
static void mutex_unlock(struct mutex *m) { assert(m->held);m->held=false; }
typedef int spinlock_t;
static void spin_lock_init(spinlock_t *s) { *s=0; }
struct dma_fence;
struct dma_fence_ops {
    const char *(*get_driver_name)(struct dma_fence *);
    const char *(*get_timeline_name)(struct dma_fence *);
    void (*release)(struct dma_fence *);
};
struct dma_fence { const struct dma_fence_ops *ops;unsigned int refs;bool signaled;int error;u64 context; };
struct dma_fence_chain { struct dma_fence base;struct dma_fence *prev,*current;u64 point; };
static unsigned int fence_allocs,fence_frees;
static struct dma_fence *dma_fence_get(struct dma_fence *f) { if(f) {assert(f->refs);f->refs++;}return f; }
static void dma_fence_put(struct dma_fence *f) {
    if (!f) return;
    assert(f->refs);
    if (!--f->refs) {fence_frees++;f->ops->release(f);}
}
static void chain_release(struct dma_fence *f) {
    struct dma_fence_chain *c=container_of(f,struct dma_fence_chain,base);
    dma_fence_put(c->prev);dma_fence_put(c->current);free(c);
}
static const struct dma_fence_ops chain_ops={.release=chain_release};
static struct dma_fence *dma_fence_chain_contained(struct dma_fence *f) {
    return f->ops==&chain_ops?container_of(f,struct dma_fence_chain,base)->current:f;
}
static u64 dma_fence_context_alloc(unsigned int n) { static u64 c;return c+=n; }
static void dma_fence_init(struct dma_fence *f,const struct dma_fence_ops *ops,spinlock_t *lock,u64 ctx,u64 seq) {
    *f=(struct dma_fence){.ops=ops,.refs=1,.context=ctx};fence_allocs++;
}
static bool dma_fence_is_signaled(struct dma_fence *f) {
    if (f->ops==&chain_ops) {
        struct dma_fence_chain *c=container_of(f,struct dma_fence_chain,base);
        return (!c->prev || dma_fence_is_signaled(c->prev)) && dma_fence_is_signaled(c->current);
    }
    return f->signaled;
}
static int dma_fence_get_status(struct dma_fence *f) { return dma_fence_is_signaled(f)?(f->error?f->error:1):0; }
static void dma_fence_signal(struct dma_fence *f) { f->signaled=true; }
static void dma_fence_set_error(struct dma_fence *f,int error) { assert(error<0 && !f->signaled);f->error=error; }
static struct dma_fence_chain *dma_fence_chain_alloc(void) { return kzalloc(sizeof(struct dma_fence_chain),0); }
static void dma_fence_chain_free(struct dma_fence_chain *c) { free(c); }
struct drm_syncobj { struct dma_fence *fence;unsigned int refs;u64 point; };
struct drm_file { struct drm_syncobj objects[16];void *driver_priv; };
static struct drm_syncobj *drm_syncobj_find(struct drm_file *f,u32 id) {
    if (!id || id>=16 || !f->objects[id].refs) return NULL;
    f->objects[id].refs++;return &f->objects[id];
}
static void drm_syncobj_put(struct drm_syncobj *o) { assert(o->refs>1);o->refs--; }
static int drm_syncobj_find_fence(struct drm_file *f,u32 id,u64 point,u64 flags,struct dma_fence **out) {
    if (!id || id>=16 || !f->objects[id].refs || !f->objects[id].fence || point>f->objects[id].point) {
        *out=(void *)(uintptr_t)0xdead; /* An error does not promise a usable output pointer. */
        return -EINVAL;
    }
    *out=dma_fence_get(f->objects[id].fence);return 0;
}
static void drm_syncobj_replace_fence(struct drm_syncobj *o,struct dma_fence *f) {
    struct dma_fence *old=o->fence;o->fence=dma_fence_get(f);o->point=0;dma_fence_put(old);
}
static void drm_syncobj_add_point(struct drm_syncobj *o,struct dma_fence_chain *c,struct dma_fence *f,u64 point) {
    static spinlock_t lock;
    dma_fence_init(&c->base,&chain_ops,&lock,dma_fence_context_alloc(1),1);
    c->prev=o->fence;c->current=dma_fence_get(f);c->point=point;o->fence=&c->base;o->point=point;
}
struct work_struct { void (*fn)(struct work_struct *); };
struct workqueue_struct { unsigned int dummy; };
static struct work_struct *queued[512];
static unsigned int queued_count;
static void INIT_WORK(struct work_struct *w,void (*fn)(struct work_struct *)) { w->fn=fn; }
static bool queue_work(struct workqueue_struct *q,struct work_struct *w) { assert(queued_count<512);queued[queued_count++]=w;return true; }
static void run_queue(void) {
    while (queued_count) {
        struct work_struct *w=queued[0];memmove(queued,queued+1,--queued_count*sizeof(queued[0]));w->fn(w);
    }
}
static bool interrupt_wait;
static int dma_fence_wait(struct dma_fence *f,bool intr) {
    if(interrupt_wait){interrupt_wait=false;return -EINTR;}
    run_queue();assert(dma_fence_is_signaled(f));return 0;
}
static void (*wait_hook)(void);
static long dma_fence_wait_timeout(struct dma_fence *f,bool intr,long time) {jiffies+=time;if(wait_hook)wait_hook();return dma_fence_is_signaled(f);}
struct xarray { void *entries[16]; };
static void *xa_load(struct xarray *a,u32 id) { return id<16?a->entries[id]:NULL; }
struct realm_gpu_context { u64 handle; };
#define U64_MAX UINT64_MAX
#define PANTHOR_VMSHM_MSG_VM_SYNC_REQ 0x50547d52U
#define PANTHOR_VMSHM_MSG_VM_SYNC_RSP 0x50547d53U
struct realm_gpu_bo { u64 handle; };
static u64 realm_gpu_context_handle(const struct realm_gpu_context *c) {return c->handle;}
static u64 realm_gpu_context_user_va_range(const struct realm_gpu_context *c) {return 0x80000000;}
struct panthor_client_bo { struct realm_gpu_bo *private_bo;u64 size;u32 client_handle;refcount_t refcnt; };
static bool panthor_client_bo_get(struct panthor_client_bo *b) {if(!b || !b->refcnt.value)return false;refcount_inc(&b->refcnt);return true;}
static void panthor_client_bo_put(struct panthor_client_bo *b) {if(b){assert(b->refcnt.value>0);--b->refcnt.value;}}
struct list_head {struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head *h) {h->next=h->prev=h;}
static void list_add_tail(struct list_head *n,struct list_head *h) {n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *n) {n->next->prev=n->prev;n->prev->next=n->next;}
#define entry(p,t,m) container_of(p,t,m)
#define list_for_each_entry(p,h,m) for(p=entry((h)->next,__typeof__(*p),m);&(p)->m!=(h);p=entry((p)->m.next,__typeof__(*p),m))
#define list_for_each_entry_safe(p,n,h,m) for(p=entry((h)->next,__typeof__(*p),m),n=entry((p)->m.next,__typeof__(*p),m);&(p)->m!=(h);p=n,n=entry((n)->m.next,__typeof__(*n),m))
#include "wire.inc"
#include "vmtypes.inc"
struct panthor_client_file {
    u64 session_id;struct workqueue_struct *private_wq;struct mutex private_submit_lock,private_gpu_lock,lock;
    atomic_t private_pending,private_gpu_pending;bool private_closing;struct xarray private_vms,bos;
};
static unsigned int error_logs;
#define pr_warn_ratelimited(...) ((void)++error_logs)
static int mapping_lock_error;
static unsigned int mapping_locks;
static int panthor_client_private_mapping_lock(struct panthor_client_file *p,u32 vm) {
    assert(vm==1);mapping_locks++;if(mapping_lock_error)return mapping_lock_error;
    mutex_lock(&p->private_gpu_lock);return 0;
}
static unsigned int commits,rpcs,remote_applies,context_puts;
static int map_error,rpc_error,proxy_error;
static bool lose_reply,bad_response;
static u64 epoch,proxy_sequence;
static u64 ptes[1024],offsets[1024];
static struct panthor_vmshm_vm_sync_req last_request;
static struct dma_fence *observe_fence;
static int realm_gpu_context_map(struct realm_gpu_context *ctx,struct realm_gpu_bo *bo,
        u64 offset,u64 va,u64 bytes,u32 prot,u64 *version) {
    assert(ctx->handle==111 && va>=0x2000000 && va+bytes<=0x2000000+sizeof(ptes)/sizeof(ptes[0])*PAGE_SIZE);
    if(map_error)return map_error;
    for(u64 i=0;i<bytes/PAGE_SIZE;i++) {
        unsigned int n=(va-0x2000000)/PAGE_SIZE+i;
        ptes[n]=bo?bo->handle:0;offsets[n]=bo?offset+i*PAGE_SIZE:0;
    }
    *version=++epoch;commits++;return 0;
}
static void realm_gpu_context_put(struct realm_gpu_context *c) {if(c)context_puts++;}
static int panthor_client_rpc_call(u32 type,const void *input,u32 input_size,
        u32 response,void *output,u32 output_size,u32 minimum,void *unused) {
    const struct panthor_vmshm_vm_sync_req *q=input;struct panthor_vmshm_vm_sync_rsp *r=output;
    assert(type==PANTHOR_VMSHM_MSG_VM_SYNC_REQ && response==PANTHOR_VMSHM_MSG_VM_SYNC_RSP);
    assert(input_size==sizeof(*q) && output_size==sizeof(*r) && minimum==sizeof(*r));
    assert(q->session_id==222 && q->client_vm_id==1 && !q->pad && !q->op.reserved && !q->op.sync_count);
    assert(q->mapping_version<=epoch);
    if(observe_fence)assert(dma_fence_get_status(observe_fence)==1);
    rpcs++;
    if(rpc_error)return rpc_error;
    if(proxy_error){r->ret=proxy_error;return 0;}
    if(q->sequence==proxy_sequence)assert(!memcmp(q,&last_request,sizeof(*q)));
    else {assert(q->sequence==proxy_sequence+1);proxy_sequence=q->sequence;last_request=*q;remote_applies++;}
    if(lose_reply)return -ETIMEDOUT;
    *r=(struct panthor_vmshm_vm_sync_rsp){.proxy_vm_id=7,.sequence=q->sequence,.mapping_version=q->mapping_version};
    if(bad_response)r->sequence++;
    return 0;
}
static int copy_struct_from_user(void *dst,size_t n,const void *src,size_t stride) {
    if(!src)return -EFAULT;
    memset(dst,0,n);memcpy(dst,src,stride<n?stride:n);return 0;
}
#include "actual.inc"
static struct panthor_client_file pc;
static struct drm_file file;
static struct realm_gpu_context ctx={.handle=111};
static struct realm_gpu_bo backing={.handle=333};
static struct panthor_client_bo bo;
static struct realm_gpu_bo replacement_backing={.handle=334};
static struct panthor_client_bo replacement_bo;
static struct workqueue_struct wq;
static struct drm_panthor_vm_bind_op input_ops[8];
static struct drm_panthor_sync_op input_syncs[8];
static struct drm_panthor_vm_bind args;
static struct panthor_client_vm *vm;
static unsigned int cases;
static void setup(void) {
    assert(!queued_count);memset(&pc,0,sizeof(pc));memset(&file,0,sizeof(file));
    memset(input_ops,0,sizeof(input_ops));memset(input_syncs,0,sizeof(input_syncs));
    memset(ptes,0,sizeof(ptes));memset(offsets,0,sizeof(offsets));
    vm=calloc(1,sizeof(*vm));assert(vm);vm->context=&ctx;INIT_LIST_HEAD(&vm->mappings);refcount_set(&vm->refs,1);
    for(unsigned int i=1;i<16;i++)file.objects[i].refs=1;
    pc.private_wq=&wq;pc.session_id=222;pc.private_vms.entries[1]=vm;
    bo=(struct panthor_client_bo){.private_bo=&backing,.size=1024*PAGE_SIZE,.client_handle=2};refcount_set(&bo.refcnt,1);pc.bos.entries[2]=&bo;
    replacement_bo=(struct panthor_client_bo){.private_bo=&replacement_backing,.size=1024*PAGE_SIZE,.client_handle=3};refcount_set(&replacement_bo.refcnt,1);pc.bos.entries[3]=&replacement_bo;
    args=(struct drm_panthor_vm_bind){.vm_id=1,.flags=DRM_PANTHOR_VM_BIND_ASYNC,
        .ops={.array=(uintptr_t)input_ops,.count=1,.stride=sizeof(input_ops[0])}};
    input_ops[0]=(struct drm_panthor_vm_bind_op){.bo_handle=2,.va=0x2000000,.size=PAGE_SIZE};
    commits=rpcs=remote_applies=context_puts=error_logs=mapping_locks=0;epoch=1;proxy_sequence=0;
    map_error=rpc_error=proxy_error=mapping_lock_error=0;interrupt_wait=lose_reply=bad_response=false;
    wait_hook=NULL;fail_alloc_after=-1;observe_fence=NULL;
}
static void sync_range(unsigned int op,unsigned int start,unsigned int count) {
    input_ops[op].syncs=(struct drm_panthor_obj_array){.array=(uintptr_t)&input_syncs[start],.count=count,.stride=sizeof(input_syncs[0])};
}
static void signal(unsigned int index,u32 handle,u64 point) {
    input_syncs[index]=(struct drm_panthor_sync_op){.handle=handle,.timeline_value=point,
        .flags=DRM_PANTHOR_SYNC_OP_SIGNAL|(point?DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ:DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ)};
}
static void enqueue(void) {signal(0,2,0);sync_range(0,0,1);assert(!panthor_client_private_vm_bind(&pc,&file,&args));}
static int status(void) {return dma_fence_get_status(file.objects[2].fence);}
static void view_matches(void) {
    u64 seen[1024]={0};struct panthor_client_mapping *m;
    list_for_each_entry(m,&vm->mappings,link)for(u64 i=0;i<m->size/PAGE_SIZE;i++) {
        unsigned int n=(m->va-0x2000000)/PAGE_SIZE+i;assert(!seen[n]);
        seen[n]=m->bo->private_bo->handle;assert(seen[n]==ptes[n] && offsets[n]==m->offset+i*PAGE_SIZE);
    }
    assert(!memcmp(seen,ptes,sizeof(seen)));
}
static void cleanup(void) {
    observe_fence=NULL;map_error=0;run_queue();view_matches();
    assert(!pc.private_pending.value && !pc.lock.held && !pc.private_submit_lock.held && !pc.private_gpu_lock.held);
    assert(vm->refs.value==1);panthor_client_vm_put(vm);
    assert(bo.refcnt.value==1);
    assert(replacement_bo.refcnt.value==(pc.bos.entries[3]==&replacement_bo?1:0));
    assert(context_puts==1);
    for(unsigned int i=1;i<16;i++){assert(file.objects[i].refs==1);dma_fence_put(file.objects[i].fence);}
    assert(fence_allocs==fence_frees);cases++;
}
static struct dma_fence *dependency;
static void release_dependency(void) {assert(!commits && !rpcs);dma_fence_signal(dependency);wait_hook=NULL;}
static void close_during_wait(void) {assert(!commits && !rpcs);pc.private_closing=true;wait_hook=NULL;}
int main(void) {
    /* Real commit + local view + fence precede all Proxy responses. */
    setup();enqueue();observe_fence=file.objects[2].fence;run_queue();assert(status()==1 && commits==1 && remote_applies==1 && !vm->dirty);cleanup();
    for(unsigned int mode=0;mode<4;mode++) {
        setup();if(mode==0)rpc_error=-EIO;if(mode==1)proxy_error=-ENOSPC;if(mode==2)lose_reply=true;if(mode==3)bad_response=true;
        enqueue();observe_fence=file.objects[2].fence;run_queue();assert(status()==1 && commits==1 && vm->dirty && vm->pending_bo==&bo);view_matches();
        unsigned int applied=remote_applies;rpc_error=proxy_error=0;lose_reply=bad_response=false;
        assert(!panthor_client_private_vm_sync(&pc,vm,1));assert(!vm->dirty && commits==1 && remote_applies==1 && applied<=1);cleanup();
    }
    /* A pending earlier delta is reconciled before a later RMM mutation. */
    setup();rpc_error=-EIO;enqueue();run_queue();assert(status()==1 && commits==1);
    input_ops[0].va+=PAGE_SIZE;enqueue();run_queue();assert(status()==-EIO && commits==1);
    rpc_error=0;enqueue();run_queue();assert(status()==1 && commits==2 && remote_applies==2);cleanup();
    /* Commit failures and preallocation failures leave actual and local state unchanged. */
    setup();map_error=-ENOSPC;enqueue();run_queue();assert(status()==-ENOSPC && !commits && !rpcs);cleanup();
    setup();enqueue();fail_alloc_after=0;run_queue();assert(status()==-ENOMEM && !commits && !rpcs);fail_alloc_after=-1;cleanup();
    for(int n=0;n<3;n++) {setup();signal(0,2,5);sync_range(0,0,1);fail_alloc_after=n;
        assert(panthor_client_private_vm_bind(&pc,&file,&args)==-ENOMEM && !queued_count && !file.objects[2].fence);
        fail_alloc_after=-1;cleanup();}
    /* Split, replace with another offset and unmap holes; no overlapping local nodes. */
    setup();input_ops[0].size=8*PAGE_SIZE;enqueue();run_queue();
    input_ops[0].va+=2*PAGE_SIZE;input_ops[0].size=2*PAGE_SIZE;input_ops[0].bo_offset=12*PAGE_SIZE;enqueue();run_queue();view_matches();
    input_ops[0]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,.va=0x2000000+PAGE_SIZE,.size=5*PAGE_SIZE};enqueue();run_queue();view_matches();
    input_ops[0]=(struct drm_panthor_vm_bind_op){.bo_handle=2,.va=0x2000000+PAGE_SIZE,.size=5*PAGE_SIZE,.bo_offset=16*PAGE_SIZE};
    enqueue();run_queue();view_matches();assert(status()==1 && ptes[0] && ptes[1] && ptes[5] && ptes[6]);cleanup();
    /* A failed UNMAP stays published. Retrying and destroying an adjacent
     * node cannot remove it early, double-free it, or leave a stale tree.
     */
    setup();input_ops[0].size=8*PAGE_SIZE;enqueue();run_queue();assert(commits==1);
    input_ops[0]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,
        .va=0x2000000+PAGE_SIZE,.size=5*PAGE_SIZE};
    for(unsigned int retry=0;retry<2;retry++) {
        map_error=-EIO;enqueue();run_queue();view_matches();
        assert(status()==-EIO && commits==1 && rpcs==1 && ptes[1] && ptes[5]);
    }
    map_error=0;input_ops[0]=(struct drm_panthor_vm_bind_op){.bo_handle=3,
        .va=0x2000000+6*PAGE_SIZE,.size=2*PAGE_SIZE};
    enqueue();run_queue();view_matches();assert(status()==1 && commits==2 &&
        ptes[0]==333 && ptes[1]==333 && ptes[5]==333 && ptes[6]==334);
    input_ops[0]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,
        .va=0x2000000+PAGE_SIZE,.size=5*PAGE_SIZE};
    enqueue();run_queue();view_matches();assert(status()==1 && commits==3 &&
        ptes[0]==333 && !ptes[1] && !ptes[5] && ptes[6]==334);
    cleanup();
    /* Boundary split allocations must all succeed before entering RMM. */
    for(int n=0;n<3;n++) {setup();input_ops[0].size=8*PAGE_SIZE;enqueue();run_queue();
        input_ops[0].va+=2*PAGE_SIZE;input_ops[0].size=PAGE_SIZE;enqueue();fail_alloc_after=n;run_queue();
        assert(status()==-ENOMEM && commits==1);fail_alloc_after=-1;cleanup();}
    /* Input is snapshotted, including a range spanning more than one RMM batch. */
    setup();input_ops[0].size=513*PAGE_SIZE;enqueue();input_ops[0].va=0;input_ops[0].size=0;run_queue();
    assert(status()==1 && ptes[512]==333 && last_request.op.va==0x2000000);cleanup();
    for(unsigned int mode=0;mode<4;mode++) {
        setup();dependency=panthor_client_private_fence_alloc();drm_syncobj_replace_fence(&file.objects[1],dependency);
        input_syncs[0]=(struct drm_panthor_sync_op){.handle=1};signal(1,2,0);sync_range(0,0,2);
        if(mode==0)wait_hook=release_dependency;
        if(mode==1)wait_hook=close_during_wait;
        if(mode==3){dma_fence_set_error(dependency,-EIO);dma_fence_signal(dependency);}
        assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
        if(mode==0)assert(status()==1 && commits==1);else assert(status()<0 && !commits && !rpcs);
        dma_fence_put(dependency);cleanup();
    }
    for(unsigned int mode=0;mode<3;mode++) {
        setup();dependency=panthor_client_private_fence_alloc();struct dma_fence_chain *chain=dma_fence_chain_alloc();
        drm_syncobj_add_point(&file.objects[1],chain,dependency,5);
        if(mode==0)dma_fence_set_error(dependency,-EIO);
        if(mode==1)dma_fence_set_error(&chain->base,-EACCES);
        dma_fence_signal(dependency);
        input_syncs[0]=(struct drm_panthor_sync_op){.handle=1,.timeline_value=5,.flags=DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ};
        signal(1,2,0);sync_range(0,0,2);assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
        assert(status()==(mode==0?-EIO:mode==1?-EACCES:1) && commits==(mode==2));dma_fence_put(dependency);cleanup();
    }
    setup();args.ops.count=2;input_ops[1]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_SYNC_ONLY};
    signal(0,2,0);input_syncs[1]=(struct drm_panthor_sync_op){.handle=2};signal(2,2,0);sync_range(0,0,1);sync_range(1,1,2);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();assert(status()==1 && commits==1);cleanup();
    setup();args.flags=0;rpc_error=-EIO;assert(!panthor_client_private_vm_bind(&pc,&file,&args) && vm->dirty && commits==1);cleanup();
    setup();args.flags=0;map_error=-EIO;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EIO && args.ops.count==0);cleanup();
    setup();args.flags=0;interrupt_wait=true;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINTR && queued_count==1 && vm->refs.value==2);run_queue();cleanup();
    const int errors[]={-ETIMEDOUT,-ECANCELED,-EIO};
    for(unsigned int i=0;i<3;i++){setup();mapping_lock_error=errors[i];enqueue();run_queue();assert(status()==errors[i] && !commits && !rpcs);cleanup();}
    setup();mapping_lock_error=-EIO;input_ops[0]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_SYNC_ONLY};enqueue();run_queue();assert(status()==1 && !mapping_locks);cleanup();
    setup();args.flags=0;signal(0,2,0);sync_range(0,0,1);assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL);cleanup();
    setup();input_ops[0].va=0x7ffff000;input_ops[0].size=2*PAGE_SIZE;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL);cleanup();
    setup();input_ops[0].va=0x80000000;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL);cleanup();
    setup();signal(0,16,0);sync_range(0,0,1);assert(panthor_client_private_vm_bind(&pc,&file,&args)==-ENOENT);cleanup();
    /* Backlog is local work, not GPU authorization. Native async VM_BIND
     * must survive more than 128 queued operations and preserve references.
     */
    for(unsigned int cancel=0;cancel<2;cancel++) {
        setup();
        for(unsigned int i=0;i<192;i++){input_ops[0].va=0x2000000+i*PAGE_SIZE;enqueue();}
        assert(pc.private_pending.value==192 && queued_count==192 && !commits && !rpcs);
        assert(vm->refs.value==193 && bo.refcnt.value==193 && !status());
        struct dma_fence *last=dma_fence_get(file.objects[2].fence);
        fail_alloc_after=0;
        assert(panthor_client_private_vm_bind(&pc,&file,&args)==-ENOMEM);
        assert(pc.private_pending.value==192 && queued_count==192 && file.objects[2].fence==last);
        fail_alloc_after=-1;pc.private_closing=cancel;run_queue();
        assert(!pc.private_pending.value && !queued_count);
        assert(commits==(cancel?0:192) && rpcs==commits && status()==(cancel?-ECANCELED:1));
        dma_fence_put(last);cleanup();
    }
    setup();pc.private_closing=true;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY && !queued_count);cleanup();
    setup();pc.private_wq=NULL;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY && !queued_count);cleanup();
    setup();enqueue();vm->closing=true;run_queue();assert(status()==-ENOENT && !commits);cleanup();
    setup();vm->sync_sequence=U64_MAX;enqueue();run_queue();assert(status()==-EOVERFLOW && !commits);cleanup();
    /* BO handle close cannot drop the references held by mapping and pending sync. */
    setup();lose_reply=true;enqueue();run_queue();pc.bos.entries[2]=NULL;panthor_client_bo_put(&bo);
    assert(bo.refcnt.value==2);lose_reply=false;assert(!panthor_client_private_vm_sync(&pc,vm,1));assert(bo.refcnt.value==1);
    refcount_inc(&bo.refcnt);cleanup();
    /* Reuse of the GPUVA reconciles the old remote delta before replacing backing. */
    setup();lose_reply=true;enqueue();run_queue();pc.bos.entries[2]=NULL;panthor_client_bo_put(&bo);
    assert(bo.refcnt.value==2 && vm->dirty && ptes[0]==backing.handle);
    input_ops[0].bo_handle=3;lose_reply=false;enqueue();run_queue();
    assert(bo.refcnt.value==0 && replacement_bo.refcnt.value==2 && remote_applies==2 && commits==2);
    assert(!vm->dirty && ptes[0]==replacement_backing.handle);
    refcount_set(&bo.refcnt,1);
    cleanup();
    /* A stale handle cannot resurrect a local object whose reference count is zero. */
    setup();refcount_set(&bo.refcnt,0);assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL);
    assert(!commits && !queued_count);refcount_set(&bo.refcnt,1);cleanup();
    /* A later dependency failure cannot rewrite an already committed prefix. */
    setup();args.ops.count=2;input_ops[1]=input_ops[0];input_ops[1].va+=PAGE_SIZE;
    dependency=panthor_client_private_fence_alloc();dma_fence_set_error(dependency,-EIO);dma_fence_signal(dependency);
    drm_syncobj_replace_fence(&file.objects[1],dependency);
    signal(0,2,0);input_syncs[1]=(struct drm_panthor_sync_op){.handle=1};signal(2,3,0);
    sync_range(0,0,1);sync_range(1,1,2);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
    assert(status()==1 && dma_fence_get_status(file.objects[3].fence)==-EIO && commits==1 && !ptes[1]);
    dma_fence_put(dependency);cleanup();
    /* Removing the VM handle retains queued work's wrapper until cancellation. */
    setup();enqueue();assert(vm->refs.value==2);pc.private_vms.entries[1]=NULL;vm->closing=true;
    panthor_client_vm_put(vm);assert(!context_puts);vm=NULL;run_queue();
    assert(status()==-ENOENT && context_puts==1 && bo.refcnt.value==1 && !commits);
    assert(!pc.private_pending.value && !pc.lock.held && !pc.private_submit_lock.held && !pc.private_gpu_lock.held);
    for(unsigned int i=1;i<16;i++){assert(file.objects[i].refs==1);dma_fence_put(file.objects[i].fence);}
    assert(fence_allocs==fence_frees);cases++;
    printf("GPU_PRIVATE_BIND_BRIDGE=PASS cases=%u actual planner/worker/GPUVA/fence/reconcile/retirement; HOST_DOUBLES_ONLY\n",cases);
    return 0;
}
