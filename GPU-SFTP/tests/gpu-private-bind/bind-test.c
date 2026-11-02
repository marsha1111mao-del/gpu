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
#define PANTHOR_VMSHM_VM_BIND_FAILED_OP_NONE UINT32_MAX
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
static void cond_resched(void) { jiffies++; }
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
static int atomic_read(atomic_t *a) { return a->value; }
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
static struct work_struct *queued[128];
static unsigned int queued_count;
static void INIT_WORK(struct work_struct *w,void (*fn)(struct work_struct *)) { w->fn=fn; }
static bool queue_work(struct workqueue_struct *q,struct work_struct *w) { assert(queued_count<128);queued[queued_count++]=w;return true; }
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
struct realm_gpu_bo { u64 handle; };
static u64 realm_gpu_context_handle(struct realm_gpu_context *c) {return c->handle;}
static u64 realm_gpu_context_user_va_range(const struct realm_gpu_context *c) {return 0x80000000;}
static u64 realm_gpu_bo_handle(struct realm_gpu_bo *b) {return b->handle;}
struct panthor_client_bo { struct realm_gpu_bo *private_bo;u64 size;u32 client_handle;unsigned int refs; };
static bool panthor_client_bo_get(struct panthor_client_bo *b) { if (!b->refs)return false;b->refs++;return true; }
static void panthor_client_bo_put(struct panthor_client_bo *b) {if(b){assert(b->refs>1);b->refs--;}}
struct panthor_client_file {
    u64 session_id;struct workqueue_struct *private_wq;struct mutex private_submit_lock,private_gpu_lock,lock;
    atomic_t private_pending,private_gpu_pending;bool private_closing;struct xarray private_vms,bos;
};
static const char *bind_error_stage;
static int bind_error_result,bind_error_pending;
static unsigned int bind_error_logs;
static void capture_bind_error(const char *fmt,u64 session,u32 vm,const char *stage,
        int ret,int pending,int gpu_pending,u32 flags) {
    assert(session==222 && vm==1 && ret<0);bind_error_stage=stage;
    bind_error_result=ret;bind_error_pending=pending;bind_error_logs++;
}
#define pr_warn_ratelimited(...) capture_bind_error(__VA_ARGS__)
/* The actual gate is exercised with the GPU worker by private-submit tests.
 * These binder doubles check the lock spans grant/RPC/check/cancel and that
 * refusal cannot leak authorization. SYNC_ONLY must not call this gate.
 */
static int mapping_lock_error;
static unsigned int mapping_locks;
static int panthor_client_private_mapping_lock(struct panthor_client_file *p,u32 vm) {
    assert(vm==1);mapping_locks++;
    if(mapping_lock_error)return mapping_lock_error;
    mutex_lock(&p->private_gpu_lock);return 0;
}
#include "wire.inc"
static unsigned int grants,rpcs,checks,cancels;
static int rpc_error,check_error,grant_error,proxy_error;
static unsigned int rpc_fail_at;
static bool skip_mapping,change_epoch,bad_response;
static u64 epoch=1,mapped_bo,mapped_start,mapped_offset,mapped_bytes;
static struct panthor_vmshm_vm_bind_req last_request;
static bool *mapping_held;
static int realm_gpu_private_call(struct realm_gpu_call *c) {
    assert(mapping_held && *mapping_held);
    assert(c->operation==REALM_GPU_MAP_CANCEL && c->handle==999);cancels++;return 0;
}
static int realm_gpu_private_call_checked(struct realm_gpu_call *c) {
    assert(mapping_held && *mapping_held);
    assert(c->handle==111);
    if(c->operation==REALM_GPU_MAP_AUTHORIZE){grants++;if(grant_error)return grant_error;c->result[0]=999;return 0;}
    assert(c->operation==REALM_GPU_MAPPING_CHECK);checks++;
    if(check_error)return check_error;
    if(c->args[0]){
        if(c->args[0]!=mapped_bo || c->args[2]<mapped_start || c->args[2]-mapped_start+c->args[3]*PAGE_SIZE>mapped_bytes ||
           c->args[1]!=mapped_offset+c->args[2]-mapped_start)return -EIO;
    }else if(mapped_bytes)return -EIO;
    c->result[0]=c->args[3]*PAGE_SIZE;c->result[1]=epoch+(change_epoch?checks:0);return 0;
}
static int panthor_client_rpc_vm_bind(const struct panthor_vmshm_vm_bind_req *q,struct panthor_vmshm_vm_bind_rsp *r) {
    assert(mapping_held && *mapping_held);
    assert(q->session_id==222 && q->client_vm_id==1 && q->flags==0 && q->op_count==1 && q->sync_count==0);
    assert(q->ops[0].sync_count==0 && q->ops[0].sync_start==0);last_request=*q;rpcs++;
    r->ret=proxy_error;r->proxy_vm_id=7;r->op_count=bad_response?2:1;r->failed_op=PANTHOR_VMSHM_VM_BIND_FAILED_OP_NONE;
    if(rpc_error && (!rpc_fail_at || rpcs==rpc_fail_at))return rpc_error;
    if(!skip_mapping){
        if((q->ops[0].flags & DRM_PANTHOR_VM_BIND_OP_TYPE_MASK)==DRM_PANTHOR_VM_BIND_OP_TYPE_MAP){
            assert(q->ops[0].authorization==999 && q->ops[0].client_bo_handle==2);
            mapped_bo=333;mapped_start=q->ops[0].va;mapped_offset=(u64)q->ops[0].bo_page_offset*PAGE_SIZE;mapped_bytes=q->ops[0].size;
        }else{assert(!q->ops[0].authorization);mapped_bytes=0;}
        epoch++;
    }
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
static struct workqueue_struct wq;
static struct drm_panthor_vm_bind_op input_ops[8];
static struct drm_panthor_sync_op input_syncs[8];
static struct drm_panthor_vm_bind args;
static void setup(void) {
    assert(!queued_count);
    memset(&pc,0,sizeof(pc));memset(&file,0,sizeof(file));
    memset(input_ops,0,sizeof(input_ops));memset(input_syncs,0,sizeof(input_syncs));
    for(unsigned int i=1;i<16;i++)file.objects[i].refs=1;
    pc.private_wq=&wq;pc.session_id=222;pc.private_vms.entries[1]=&ctx;
    bo=(struct panthor_client_bo){.private_bo=&backing,.size=513*PAGE_SIZE,.client_handle=2,.refs=1};pc.bos.entries[2]=&bo;
    args=(struct drm_panthor_vm_bind){.vm_id=1,.flags=DRM_PANTHOR_VM_BIND_ASYNC,
        .ops={.array=(uintptr_t)input_ops,.count=1,.stride=sizeof(input_ops[0])}};
    input_ops[0]=(struct drm_panthor_vm_bind_op){.bo_handle=2,.va=0x2000000,.size=PAGE_SIZE};
    grants=rpcs=checks=cancels=0;rpc_error=check_error=grant_error=proxy_error=0;
    bind_error_stage=NULL;bind_error_result=bind_error_pending=0;bind_error_logs=0;rpc_fail_at=0;interrupt_wait=false;
    mapping_lock_error=0;mapping_locks=0;mapping_held=&pc.private_gpu_lock.held;
    skip_mapping=change_epoch=bad_response=false;mapped_bytes=0;wait_hook=NULL;fail_alloc_after=-1;
}
static void sync_range(unsigned int op,unsigned int start,unsigned int count) {
    input_ops[op].syncs=(struct drm_panthor_obj_array){.array=(uintptr_t)&input_syncs[start],.count=count,.stride=sizeof(input_syncs[0])};
}
static void signal(unsigned int index,u32 handle,u64 point) {
    input_syncs[index]=(struct drm_panthor_sync_op){.handle=handle,.timeline_value=point,
        .flags=DRM_PANTHOR_SYNC_OP_SIGNAL|(point?DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ:DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ)};
}
static void cleanup(void) {
    run_queue();assert(!pc.private_pending.value && !pc.lock.held && !pc.private_submit_lock.held && !pc.private_gpu_lock.held && bo.refs==1);
    for(unsigned int i=1;i<16;i++){assert(file.objects[i].refs==1);dma_fence_put(file.objects[i].fence);file.objects[i].fence=NULL;}
    assert(fence_allocs==fence_frees);
}
static struct dma_fence *dependency;
static void release_dependency(void) {assert(!grants && !rpcs);dma_fence_signal(dependency);wait_hook=NULL;}
static void close_during_wait(void) {assert(!grants && !rpcs);pc.private_closing=true;wait_hook=NULL;}
int main(void) {
    /* Distinguish identical EBUSY failures without replaying uncertain work. */
    const char *stages[]={"authorize","rpc-transport","proxy-bind","pte-check","mapping-lock"};
    for(unsigned int i=0;i<5;i++) {
        setup();args.flags=0;
        if(i==0)grant_error=-EBUSY;
        if(i==1)rpc_error=-EBUSY;
        if(i==2)proxy_error=-EBUSY;
        if(i==3)check_error=-EBUSY;
        if(i==4)mapping_lock_error=-EBUSY;
        assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY);
        assert(bind_error_logs==1 && !strcmp(bind_error_stage,stages[i]) && bind_error_result==-EBUSY);
        assert(grants==(i==4?0:1) && rpcs==(i==0 || i==4?0:1));
        assert(cancels==(i==0 || i==4?0:1));cleanup();
    }
    setup();pc.private_pending.value=128;
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY);
    assert(bind_error_logs==1 && !strcmp(bind_error_stage,"admission") && bind_error_pending==128 && !grants && !rpcs);
    pc.private_pending.value=0;cleanup();
    setup();pc.private_closing=true;
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY && !strcmp(bind_error_stage,"closing"));cleanup();
    setup();pc.private_wq=NULL;
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY && !strcmp(bind_error_stage,"no-worker"));cleanup();
    setup();dependency=panthor_client_private_fence_alloc();
    dma_fence_set_error(dependency,-EBUSY);dma_fence_signal(dependency);
    drm_syncobj_replace_fence(&file.objects[1],dependency);
    input_syncs[0]=(struct drm_panthor_sync_op){.handle=1};signal(1,2,0);sync_range(0,0,2);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
    assert(bind_error_logs==1 && !strcmp(bind_error_stage,"dependency") && !grants && !rpcs &&
        dma_fence_get_status(file.objects[2].fence)==-EBUSY);
    dma_fence_put(dependency);cleanup();
    /* Batch-local dependencies, operation ordering and no shared sync handles. */
    setup();args.ops.count=2;input_ops[1]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,.va=0x2000000,.size=PAGE_SIZE};
    signal(0,2,0);input_syncs[1]=(struct drm_panthor_sync_op){.handle=2};signal(2,3,9);
    sync_range(0,0,1);sync_range(1,1,2);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));assert(!grants && !rpcs && !dma_fence_is_signaled(file.objects[3].fence));
    run_queue();assert(grants==1 && rpcs==2 && checks==2 && cancels==1 && dma_fence_is_signaled(file.objects[3].fence));cleanup();
    /* Every failure must error its local output, never trust an RPC success. */
    for(unsigned int mode=0;mode<5;mode++){
        setup();signal(0,2,0);sync_range(0,0,1);
        if(mode==0)skip_mapping=true;
        if(mode==1){change_epoch=true;input_ops[0].size=513*PAGE_SIZE;}
        if(mode==2)rpc_error=-EIO;
        if(mode==3)check_error=-EACCES;
        if(mode==4)bad_response=true;
        assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
        assert(dma_fence_get_status(file.objects[2].fence)<0 && cancels==1);cleanup();
    }
    /* Existing Client dependency, close cancellation, timeout and error. */
    for(unsigned int mode=0;mode<4;mode++){
        setup();dependency=panthor_client_private_fence_alloc();drm_syncobj_replace_fence(&file.objects[1],dependency);
        input_syncs[0]=(struct drm_panthor_sync_op){.handle=1};signal(1,2,0);sync_range(0,0,2);
        if(mode==0)wait_hook=release_dependency;
        if(mode==1)wait_hook=close_during_wait;
        if(mode==3){dma_fence_set_error(dependency,-EIO);dma_fence_signal(dependency);}
        assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
        int status=dma_fence_get_status(file.objects[2].fence);
        if(mode==0)assert(status==1 && grants==1);else assert(status<0 && !grants && !rpcs);
        dma_fence_put(dependency);cleanup();
    }
    /* No user-memory rereads after enqueue; complete 513-page RMM checking. */
    setup();input_ops[0].size=513*PAGE_SIZE;signal(0,2,0);sync_range(0,0,1);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));input_ops[0].va=0;input_ops[0].size=0;
    run_queue();assert(last_request.ops[0].va==0x2000000 && checks==2 && dma_fence_get_status(file.objects[2].fence)==1);cleanup();
    /* Allocation/invalid-handle failures leave original syncobjs untouched. */
    for(int fail=0;fail<3;fail++){
        setup();signal(0,2,9);sync_range(0,0,1);fail_alloc_after=fail;
        assert(panthor_client_private_vm_bind(&pc,&file,&args)==-ENOMEM);
        assert(!file.objects[2].fence && !queued_count && !grants && !rpcs);fail_alloc_after=-1;cleanup();
    }
    setup();signal(0,16,0);sync_range(0,0,1);assert(panthor_client_private_vm_bind(&pc,&file,&args)==-ENOENT);cleanup();
    setup();pc.private_pending.value=128;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EBUSY);pc.private_pending.value=0;cleanup();
    /* Duplicate signals use the last fence; waits use the prior batch job. */
    setup();args.ops.count=2;input_ops[1]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_SYNC_ONLY};
    signal(0,2,0);input_syncs[1]=(struct drm_panthor_sync_op){.handle=2};signal(2,2,0);sync_range(0,0,1);sync_range(1,1,2);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();assert(rpcs==1 && dma_fence_get_status(file.objects[2].fence)==1);cleanup();
    /* Sync bindings use the same ordered worker and report the failing op. */
    setup();args.flags=0;rpc_error=-EIO;assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EIO && args.ops.count==0);cleanup();
    /* The chain container reports success even when its current point failed. */
    for(unsigned int mode=0;mode<3;mode++){
        setup();dependency=panthor_client_private_fence_alloc();
        struct dma_fence_chain *chain=dma_fence_chain_alloc();assert(chain);
        drm_syncobj_add_point(&file.objects[1],chain,dependency,5);
        if(mode==0)dma_fence_set_error(dependency,-EIO);
        if(mode==1)dma_fence_set_error(&chain->base,-EACCES);
        dma_fence_signal(dependency);
        assert(dma_fence_get_status(&chain->base)==(mode==1?-EACCES:1));
        input_syncs[0]=(struct drm_panthor_sync_op){.handle=1,.timeline_value=5,
            .flags=DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ};signal(1,2,0);sync_range(0,0,2);
        assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
        assert(dma_fence_get_status(file.objects[2].fence)==(mode==0?-EIO:mode==1?-EACCES:1));
        assert(grants==(mode==2) && rpcs==(mode==2));dma_fence_put(dependency);cleanup();
    }
    /* False-success UNMAP must not signal success while a PTE remains. */
    setup();mapped_bo=333;mapped_start=0x2000000;mapped_offset=0;mapped_bytes=PAGE_SIZE;skip_mapping=true;
    input_ops[0]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,.va=mapped_start,.size=PAGE_SIZE};
    signal(0,2,0);sync_range(0,0,1);assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
    assert(dma_fence_get_status(file.objects[2].fence)==-EIO && !grants && !cancels);cleanup();
    /* A later operation's failure cannot overwrite an earlier success. */
    setup();args.ops.count=2;input_ops[1]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,.va=0x2000000,.size=PAGE_SIZE};
    signal(0,2,0);signal(1,3,0);sync_range(0,0,1);sync_range(1,1,1);rpc_error=-EIO;rpc_fail_at=2;
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
    assert(dma_fence_get_status(file.objects[2].fence)==1 && dma_fence_get_status(file.objects[3].fence)==-EIO && checks==1);cleanup();
    /* Authorization failure never reaches the Proxy or invents a grant. */
    setup();grant_error=-EACCES;signal(0,2,0);sync_range(0,0,1);
    assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
    assert(dma_fence_get_status(file.objects[2].fence)==-EACCES && !rpcs && !cancels);cleanup();
    /* Interrupted synchronous callers leave worker/BO references alive. */
    setup();args.flags=0;interrupt_wait=true;
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINTR && queued_count==1 && bo.refs==2);
    run_queue();assert(grants==1 && checks==1);cleanup();
    /* User binds may not touch or cross into kernel heap VA, before RPC. */
    setup();input_ops[0].va=0x80000000;
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL && !grants && !rpcs);cleanup();
    setup();input_ops[0].va=0x7ffff000;input_ops[0].size=8192;
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL && !grants && !rpcs);cleanup();
    /* A mapping guard refusal must precede grant/RPC/check/cancel. */
    const int guard_errors[]={-ETIMEDOUT,-ECANCELED,-EIO};
    for(unsigned int i=0;i<3;i++){
        setup();mapping_lock_error=guard_errors[i];signal(0,2,0);sync_range(0,0,1);
        assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
        assert(mapping_locks==1 && !grants && !rpcs && !checks && !cancels);
        assert(dma_fence_get_status(file.objects[2].fence)==guard_errors[i]);cleanup();
    }
    /* SYNC_ONLY stays runnable even when mapping changes are refused. */
    setup();mapping_lock_error=-EIO;
    input_ops[0]=(struct drm_panthor_vm_bind_op){.flags=DRM_PANTHOR_VM_BIND_OP_TYPE_SYNC_ONLY};
    signal(0,2,0);sync_range(0,0,1);assert(!panthor_client_private_vm_bind(&pc,&file,&args));run_queue();
    assert(!mapping_locks && !grants && !rpcs && dma_fence_get_status(file.objects[2].fence)==1);cleanup();
    /* Synchronous native VM_BIND rejects explicit sync objects atomically. */
    setup();args.flags=0;signal(0,2,0);sync_range(0,0,1);
    assert(panthor_client_private_vm_bind(&pc,&file,&args)==-EINVAL);
    assert(!queued_count && !file.objects[2].fence && !mapping_locks && !grants);cleanup();
    puts("GPU_PRIVATE_BIND_BRIDGE=PASS cases=41 actual Client copy/planning/worker/check functions; ordered local binary/timeline fences, batch dependencies, contained timeline point errors, error/timeout/close, 513 pages, no remote sync handles, false MAP/UNMAP success and epoch changes refused, immutable inputs, guarded grant/RPC/check/cancel, guard refusal before authorization, SYNC_ONLY bypass and synchronous sync rejection, interrupted caller/backing cleanup; HOST_DOUBLES_ONLY");
    return 0;
}
