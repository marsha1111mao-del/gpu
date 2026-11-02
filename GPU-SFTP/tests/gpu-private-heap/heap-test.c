// SPDX-License-Identifier: GPL-2.0-only
/* Real RMM core and extracted kernel/frontend functions. HOST DOUBLES ONLY. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "linux/realm_gpu.h"
#include "drm/panthor_drm.h"
#include "opencca_gpu_private.c"
typedef uint32_t u32;
typedef uint64_t u64;
#define PAGE_SIZE 4096ULL
#define PAGE_SHIFT 12
#define PAGE_ALIGNED(n) (((n)&4095)==0)
#define IS_ALIGNED(n,a) (((n)&((a)-1))==0)
#define SZ_128K (128U*1024)
#define SZ_8M (8U*1024*1024)
#define U64_MAX UINT64_MAX
#define U32_MAX UINT32_MAX
#define GFP_KERNEL 0
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define ERR_CAST(e) ((void *)(e))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095L)
#define PTR_ERR(p) ((intptr_t)(p))
#define min(a,b) ((a)<(b)?(a):(b))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define DIV_ROUND_UP(a,b) (((a)+(b)-1)/(b))
#define EXPORT_SYMBOL_GPL(n)
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_warn_ratelimited(...) ((void)0)
#define cpu_to_le64(n) ((u64)(n)) /* Test host, like the target, is little endian. */
static unsigned int cases, allocations, frees, alloc_calls, fail_alloc, source_calls;
static void *kzalloc(size_t n,int flags)
{
    if (++alloc_calls==fail_alloc) return NULL;
    void *p=calloc(1,n);assert(p);allocations++;return p;
}
static void kfree(void *p) { if(p){frees++;free(p);} }
#define kvfree(p) kfree(p)
struct page { unsigned char data[4096]; unsigned long ipa; const void *owner; bool visible, nc; };
static void *page_address(struct page *p) { return p->data; }
static void clear_highpage(struct page *p) { assert(p->visible && !p->nc);memset(p->data,0,4096); }
static void __free_page(struct page *p)
{
    /* No live RMM backing record may survive an actual page free. */
    assert(!gpu_private_range_busy(p->owner,p->ipa,4096));kfree(p);
}
static struct page *alloc_page(int flags) { return kzalloc(sizeof(struct page),flags); }
#define __GFP_ZERO 0
struct list_head { struct list_head *next,*prev; };
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
#define entry(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) \
 for(p=entry((h)->next,__typeof__(*p),m);&(p)->m!=(h);p=entry((p)->m.next,__typeof__(*p),m))
#define list_for_each_entry_safe(p,n,h,m) \
 for(p=entry((h)->next,__typeof__(*p),m),n=entry((p)->m.next,__typeof__(*p),m); \
     &(p)->m!=(h);p=n,n=entry((n)->m.next,__typeof__(*n),m))
#define list_first_entry(h,t,m) entry((h)->next,t,m)
static void list_add_tail(struct list_head *p,struct list_head *h)
{p->next=h;p->prev=h->prev;h->prev->next=p;h->prev=p;}
static void list_del(struct list_head *p) {p->prev->next=p->next;p->next->prev=p->prev;}
static void list_move_tail(struct list_head *p,struct list_head *h) {list_del(p);list_add_tail(p,h);}
static bool list_empty(struct list_head *h) {return h->next==h;}
static void INIT_LIST_HEAD(struct list_head *h) {h->next=h->prev=h;}
typedef unsigned int refcount_t;
static bool refcount_dec_and_test(refcount_t *r) {assert(*r);return !--*r;}
static unsigned int refcount_read(refcount_t *r) {return *r;}
static void refcount_inc(refcount_t *r) { assert(*r);++*r; }
static void refcount_dec(refcount_t *r) { assert(*r);--*r; }
#define wmb() ((void)0)
#define READ_ONCE(n) (n)

static int gpu_lock;
static void mutex_lock(int *lock) {assert(!*lock);*lock=1;}
static void mutex_unlock(int *lock) {assert(*lock);*lock=0;}
static void cond_resched(void) { }
static bool realm=true;
static bool is_realm_world(void) {return realm;}
#include "structures.inc"
static LIST_HEAD(private_groups);
static LIST_HEAD(private_contexts);
static LIST_HEAD(private_bos);
static LIST_HEAD(private_heaps);
static int client_a,client_b,service;
static const void *caller=&client_a;
static unsigned long next_ipa=0x100000;
static unsigned int calls,map_calls,unmap_calls,fail_map_at,fail_unmap_at;
static bool transport_fail,corrupt_map,corrupt_unmap,sync_ok=true,fail_bo;
static u64 oom_token=9001,oom_context,oom_event,oom_heap,oom_counts=1,oom_queue;
static u64 grow_object,grow_va;
static unsigned int event_calls,grow_calls,heap_reply_fault,device_syncs,fail_sync;
static unsigned long live_roots[16];
static bool grow_lost,alloc_abandon;
static unsigned int seal_reply_fault;
static unsigned int uncached_reply_fault;
/* Model another Realm's complete RSI calls at a call boundary. This is not a
 * thread/concurrency test: the actual RMM core executes each call atomically.
 */
static u64 inject_grant, inject_va;
static bool inject_after;
static bool source_page(const void *owner,unsigned long ipa,unsigned long *pa)
{
    source_calls++;assert(owner==&client_a || owner==&client_b);
    *pa=ipa+0x40000000;return true;
}
static unsigned long table_pa(const void *p)
{return 0x100000000UL+(const unsigned char *)p-(const unsigned char *)tables;}
static void clean(const void *p,size_t n) {assert(p && n);}
static bool test_synchronize(unsigned long ctx,unsigned long root) {return sync_ok;}
static bool test_activate(unsigned long ctx,unsigned long root,unsigned int slot) {return true;}
static bool prepare_as(unsigned long root,unsigned int slot,unsigned long fw,bool existing)
{
    assert(slot>0 && slot<16 && fw==0x300000);
    if(existing)return live_roots[slot]==root;
    assert(!live_roots[slot]);live_roots[slot]=root;return true;
}
static bool extend_as(unsigned long root,unsigned int slot,unsigned long fw)
{assert(live_roots[slot]==root && fw==0x300000);return true;}
static bool detach_as(unsigned long root,unsigned int slot,unsigned long fw,bool detached)
{assert(live_roots[slot]==root && fw==0x300000);return true;}
static bool sync_device(unsigned long pa) {return ++device_syncs!=fail_sync;}
static bool sync_cpu(unsigned long pa) {return true;}
static struct page *page_by_pa(unsigned long pa)
{
    struct realm_gpu_bo *bo;
    list_for_each_entry(bo,&private_bos,link)
        for(unsigned long i=0;i<bo->nr_pages;i++)
            if(bo->pages[i]->ipa+0x40000000==pa)return bo->pages[i];
    assert(false);return NULL;
}
static bool hide_page(const void *o,unsigned long ipa,unsigned long pa)
{struct page *p=page_by_pa(pa);assert(p->owner==o && p->ipa==ipa && p->visible);p->visible=false;return true;}
static bool restore_page(const void *o,unsigned long ipa,unsigned long pa)
{struct page *p=page_by_pa(pa);assert(p->owner==o && p->ipa==ipa && !p->visible);p->visible=true;p->nc=false;return true;}
static bool restore_nc(const void *o,unsigned long ipa,unsigned long pa)
{struct page *p=page_by_pa(pa);assert(p->owner==o && p->ipa==ipa && !p->visible);p->visible=true;p->nc=true;return true;}
static bool cache_barrier(void) {return true;}
static bool clear_page(unsigned long pa)
{struct page *p=page_by_pa(pa);assert(!p->visible);memset(p->data,0,4096);return true;}
static const struct gpu_private_ops ops={.source_page=source_page,.table_pa=table_pa,
    .clean=clean,.hide_page=hide_page,.restore_page=restore_page,.clear_page=clear_page,.synchronize=test_synchronize,.activate=test_activate,
    .prepare_as=prepare_as,.extend_as=extend_as,.detach_as=detach_as,
    .sync_page_for_device=sync_device,.sync_page_for_cpu=sync_cpu,
    .restore_page_uncached=restore_nc,.cache_barrier=cache_barrier};
static int gpu_call_locked(struct realm_gpu_call *call,struct page *unused)
{
    assert(gpu_lock && !unused);calls++;
    if (call->operation==REALM_GPU_MAP && ++map_calls==fail_map_at) {
        if(transport_fail)return -EIO;
        sync_ok=false;
    }
    if (call->operation==REALM_GPU_UNMAP_BO && ++unmap_calls>=fail_unmap_at && fail_unmap_at)return -EIO;
    struct gpu_private_result r;
    u64 after=0;
    if(call->operation==REALM_GPU_UNMAP_BO && inject_grant) {
        u64 grant=inject_grant;inject_grant=0;
        if(inject_after)after=grant;
        else {
            gpu_private_service_unmap(&ops,&service,caller,call->handle,inject_va,1,&r);assert(!r.status);
            gpu_private_service_map(&ops,&service,caller,call->handle,grant,0,inject_va,1,3|8,&r);assert(!r.status);
        }
    }
    switch(call->operation) {
    case REALM_GPU_VERSION:r=(struct gpu_private_result){.value={1,REALM_GPU_CAP_TASK_STAGE_HINT}};break;
    case REALM_GPU_TASK_HEAP_EVENT:
        event_calls++;assert(call->handle==oom_token && call->args[0]);
        r=(struct gpu_private_result){.value={oom_event,oom_event?oom_heap:0,
            oom_event?oom_counts:0,oom_event?oom_queue:0}};
        if(heap_reply_fault==1)r.value[1]++;
        if(heap_reply_fault==2)r.value[2]=0;
        if(heap_reply_fault==3)r.value[2]=1ULL<<32|1;
        if(heap_reply_fault==4)r.value[3]=32;
        if(heap_reply_fault==5)r.value[3]=1;
        break;
    case REALM_GPU_TASK_HEAP_GROW:
        grow_calls++;assert(call->handle==oom_token && call->args[0]==7 && call->args[1]==oom_event);
        if(!grow_object && call->args[2])grow_object=call->args[2],grow_va=call->args[3];
        assert(call->args[2]==grow_object && call->args[3]==grow_va);
        r=(struct gpu_private_result){.value={1,oom_event,0,oom_queue}};
        if(grow_object) {
            struct gpu_private_result mapped;
            gpu_private_task_extend(&ops,&service,caller,oom_context,oom_token,grow_object,grow_va,0x300000,&mapped);
            r.status=mapped.status;r.value[0]=!r.status;r.value[2]=mapped.value[0];
        }
        if(grow_lost)return -EIO; /* RMM may already have installed all leaves. */
        if(heap_reply_fault==6)r.value[0]^=1;
        if(heap_reply_fault==7)r.value[1]++;
        if(heap_reply_fault==8)r.value[2]++;
        if(heap_reply_fault==9)r.value[3]++;
        if(heap_reply_fault==10)r.value[2]=0;
        break;
    case REALM_GPU_MAP:
        gpu_private_map(&ops,caller,call->handle,call->args[0],call->args[1],call->args[2],call->args[3],call->args[4],&r);break;
    case REALM_GPU_UNMAP:
        gpu_private_unmap(&ops,caller,call->handle,call->args[0],call->args[1],&r);break;
    case REALM_GPU_UNMAP_BO:
        gpu_private_unmap_bo(&ops,caller,call->handle,call->args[0],call->args[1],call->args[2],call->args[3],&r);break;
    case REALM_GPU_QUERY:gpu_private_query(caller,call->handle,0,&r);break;
    case REALM_GPU_BO_DESTROY:gpu_private_bo_destroy(caller,call->handle,&r);break;
    case REALM_GPU_BO_SEAL:gpu_private_bo_seal(&ops,caller,call->handle,&r);break;
    case REALM_GPU_BO_RELEASE:gpu_private_bo_release(&ops,caller,call->handle,&r);break;
    case REALM_GPU_BO_UNCACHED:gpu_private_bo_uncached(&ops,caller,call->handle,&r);break;
    case REALM_GPU_CONTEXT_DESTROY:gpu_private_context_destroy(&ops,caller,call->handle,&r);break;
    default:assert(false);
    }
    call->status=r.status;memcpy(call->result,r.value,sizeof(r.value));
    if(after) {
        gpu_private_service_map(&ops,&service,caller,call->handle,after,0,inject_va,1,3|8,&r);assert(!r.status);
    }
    if(call->operation==REALM_GPU_BO_SEAL || call->operation==REALM_GPU_BO_UNCACHED) {
        unsigned int fault=call->operation==REALM_GPU_BO_SEAL?seal_reply_fault:uncached_reply_fault;
        if(fault==1)return -EIO;
        if(fault==2)call->result[0]=0;
        if(fault==3)call->result[0]++;
        if(fault==4)call->result[1]=1;
        if(fault==5)call->result[2]=1;
        if(fault==6)call->result[3]=1;
        if(fault==7)call->status=PRIVATE_STATUS_INCOMPLETE;
        if(fault==8)call->status=0; /* Incomplete 513-page transition. */
    }
    if (corrupt_map && call->operation==REALM_GPU_MAP)call->result[3]=1;
    if (corrupt_unmap && call->operation==REALM_GPU_UNMAP_BO)call->result[0]++;
    return 0;
}
static void realm_gpu_heap_put(struct realm_gpu_heap *heap);
static struct realm_gpu_bo *realm_gpu_bo_alloc(u64 channel,u64 bytes,u32 access)
{
    assert(channel==7);
    if(alloc_abandon) {
        assert(!gpu_lock);
        struct realm_gpu_heap *h;
        list_for_each_entry(h,&private_heaps,link)
            if(h->allocating)realm_gpu_heap_put(h);
    }
    if(fail_bo)return ERR_PTR(-ENOMEM);
    struct realm_gpu_bo *bo=kzalloc(sizeof(*bo),0);assert(bo);
    bo->nr_pages=bytes/4096;bo->pages=kzalloc(bo->nr_pages*sizeof(*bo->pages),0);assert(bo->pages);
    struct gpu_private_result r;gpu_private_bo_create(caller,&service,bytes,access,&r);
    assert(!r.status);bo->handle=r.value[0];bo->refs=1;
    for (unsigned long i=0;i<bo->nr_pages;i++) {
        bo->pages[i]=kzalloc(sizeof(struct page),0);assert(bo->pages[i]);
        bo->pages[i]->visible=true;bo->pages[i]->ipa=next_ipa;bo->pages[i]->owner=caller;next_ipa+=4096;
    }
    for (unsigned long first=0;first<bo->nr_pages;) {
        unsigned long ipas[512],count=min(512,bo->nr_pages-first);
        for(unsigned long j=0;j<count;j++)ipas[j]=bo->pages[first+j]->ipa;
        gpu_private_bo_append(&ops,caller,bo->handle,first*4096,ipas,count,&r);assert(!r.status);first+=count;
    }
    list_add_tail(&bo->link,&private_bos);return bo;
}
static void reap_groups(void) { }
static void reap_tasks(void) { }

static bool managed_task(u64 h) {return h==oom_token;}
static void reap_heaps(void);
static void reap_contexts(void);
static void realm_gpu_reap_private(void);
static void realm_gpu_bo_put(struct realm_gpu_bo *bo);
#define CAP_SYS_ADMIN 21
static bool capable(int cap) {return true;}
static int copy_from_user(void *d,const void *s,size_t n) {memcpy(d,s,n);return 0;}
#define copy_to_user(d,s,n) copy_from_user(d,s,n)
#define u64_to_user_ptr(n) ((void *)(uintptr_t)(n))
static int private_alloc_ioctl(unsigned long arg,bool control) {assert(false);return -EIO;}
static bool managed_group(u64 handle) {
 struct realm_gpu_group *g;
 list_for_each_entry(g,&private_groups,link)if(g->handle==handle)return true;
 return false;
}
#include "kernel.inc"
/* DRM file/xarray/transport doubles. The actual frontend functions follow. */
struct xarray {void *slot[140];bool fail_insert,alloc;};
#define XA_FLAGS_ALLOC 1
static void xa_init_flags(struct xarray *x,unsigned int flags)
{memset(x,0,sizeof(*x));x->alloc=flags&XA_FLAGS_ALLOC;}
static void xa_init(struct xarray *x) {xa_init_flags(x,0);}
struct xa_limit {u32 min,max;};
#define XA_LIMIT(a,b) ((struct xa_limit){a,b})
#define XA_PRESENT 1
#define xa_for_each(x,i,p) for(i=0;i<140;i++)if(((p)=(x)->slot[i]))
static void *xa_load(struct xarray *x,u32 i) {return i<140?x->slot[i]:NULL;}
static void *xa_erase(struct xarray *x,u32 i) {void *p=xa_load(x,i);if(i<140)x->slot[i]=NULL;return p;}
static int xa_alloc(struct xarray *x,u32 *id,void *p,struct xa_limit lim,int flags)
{
    if(!x->alloc)return -EINVAL; /* Linux requires free-slot tracking. */
    if(x->fail_insert)return -ENOMEM;
    for(u32 i=lim.min;i<140 && i<=lim.max;i++)if(!x->slot[i]){*id=i;x->slot[i]=p;return 0;}
    return -ENOSPC;
}
static int xa_insert(struct xarray *x,u32 id,void *p,int flags)
{if(id>=140 || x->slot[id])return -EBUSY;x->slot[id]=p;return 0;}
static void *xa_find(struct xarray *x,unsigned long *id,unsigned long maxid,int flags)
{for(;*id<140 && *id<=maxid;(*id)++)if(x->slot[*id])return x->slot[*id];return NULL;}
static void xa_destroy(struct xarray *x) {for(u32 i=0;i<140;i++)assert(!x->slot[i]);}
struct panthor_client_file {u64 session_id;int lock;bool private_data;struct xarray private_vms,heaps,bos,syncobjs,groups;};
static unsigned int heap_rpc_calls,destroy_rpc_calls;
static u64 client_comm_vmshm_rmm_channel(void) {return 7;}
static int panthor_client_rpc_tiler_heap_create(const struct panthor_vmshm_tiler_heap_create_req *req,
    struct panthor_vmshm_tiler_heap_create_rsp *rsp)
{
    heap_rpc_calls++;*rsp=(struct panthor_vmshm_tiler_heap_create_rsp){.client_heap_handle=9,
        .proxy_heap_handle=19,.proxy_vm_id=1,.tiler_heap_ctx_gpu_va=0x10000,.first_heap_chunk_gpu_va=0x11000};return 0;
}
static int panthor_client_tiler_heap_destroy_rpc_session(u64 session,u32 handle,u32 *proxy)
{destroy_rpc_calls++;if(proxy)*proxy=19;return 0;}
#include "client.inc"
static struct realm_gpu_context *context_new(void)
{
    struct gpu_private_result r;gpu_private_context_create(&ops,caller,&service,&r);assert(!r.status);
    struct realm_gpu_context *c=kzalloc(sizeof(*c),0);assert(c);c->handle=r.value[0];list_add_tail(&c->link,&private_contexts);return c;
}
static struct realm_gpu_heap *heap_new(struct realm_gpu_context *c,u32 count,u32 size)
{return realm_gpu_heap_create(c,7,count,size,count+2,3);}
static void no_leaks(void)
{
    realm_gpu_reap_private();assert(list_empty(&private_heaps) && list_empty(&private_bos) && list_empty(&private_contexts));
    assert(allocations==frees && !gpu_lock);cases++;
}
static void check_mapping(struct realm_gpu_heap *h)
{
    struct private_context *c=ctx_lookup(caller,h->context);assert(c);
    for(unsigned int i=0;i<h->bo->nr_pages;i++) {
        unsigned long va=h->base+i*4096UL;
        unsigned int t=walk(&ops,c,va,NULL);assert(t!=GPU_PRIVATE_TABLES);
        uint64_t pte=tables[t][(va>>12)&511];
        assert((pte&ADDRESS_MASK)==h->bo->pages[i]->ipa+0x40000000);
        assert((pte&PTE_XN)==PTE_XN && !(pte&PTE_RO));
        assert(leaf_object[t][(va>>12)&511]!=0);
    }
    struct gpu_private_result r;
    gpu_private_mapping_check(&ops,caller==&client_a?&client_b:&client_a,h->context,h->bo->handle,0,h->base,1,3|8,&r);
    assert(r.status==GPU_PRIVATE_INPUT);cases++;
}
static void exact_cleanup_tests(void)
{
    struct gpu_private_result r;
    /* A preexisting real mapping in either the first or a later failed MAP
     * batch survives heap failure, including all of its original references.
     */
    for(unsigned int later=0;later<2;later++) {
        struct realm_gpu_context *c=context_new();
        assert(!realm_gpu_context_set_va_split(c,0x80000000));
        struct realm_gpu_bo *other=realm_gpu_bo_alloc(7,4096,3);
        u64 va=0x80000000ULL+(later?512*4096ULL:0);
        gpu_private_map(&ops,caller,c->handle,other->handle,0,va,1,3|8,&r);assert(!r.status);
        assert(IS_ERR(heap_new(c,1,later?SZ_8M:SZ_128K)));
        assert(!heap_context_busy(c->handle));
        gpu_private_mapping_check(&ops,caller,c->handle,other->handle,0,va,1,3|8,&r);assert(!r.status);
        assert(ctx_lookup(caller,c->handle)->mapped==1 && bo_lookup(caller,other->handle)->mapped==1);
        gpu_private_unmap(&ops,caller,c->handle,va,1,&r);assert(!r.status);
        realm_gpu_bo_put(other);realm_gpu_context_put(c);no_leaks();cases++;
    }
    /* A preauthorized service grant replaces a heap leaf immediately before
     * cleanup, or maps the now-empty VA immediately afterwards. Neither case
     * permits heap cleanup to delete the foreign mapping or its pending ref.
     */
    for(unsigned int after=0;after<2;after++) {
        struct realm_gpu_context *c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
        struct realm_gpu_bo *other=realm_gpu_bo_alloc(7,4096,3);
        struct realm_gpu_heap *h=heap_new(c,1,SZ_128K);assert(!IS_ERR(h));
        inject_va=h->base;
        gpu_private_map_authorize(caller,c->handle,other->handle,0,inject_va,1,3|8,&r);assert(!r.status);
        inject_grant=r.value[0];inject_after=after;
        realm_gpu_heap_put(h);assert(!inject_grant && !heap_context_busy(c->handle));
        gpu_private_mapping_check(&ops,caller,c->handle,other->handle,0,inject_va,1,3|8,&r);assert(!r.status);
        assert(ctx_lookup(caller,c->handle)->mapped==1 && bo_lookup(caller,other->handle)->mapped==1);
        gpu_private_unmap(&ops,caller,c->handle,inject_va,1,&r);assert(!r.status);
        realm_gpu_bo_put(other);realm_gpu_context_put(c);no_leaks();cases++;
    }
    /* Exact cleanup is not cancellation of previously issued authority.
     * Even an extra grant to the same BO keeps its backing alive after the
     * heap wrapper disappears and until a later actual mapping is removed.
     */
    {
        struct realm_gpu_context *held=context_new();assert(!realm_gpu_context_set_va_split(held,0x80000000));
        struct realm_gpu_heap *h=heap_new(held,1,SZ_128K);assert(!IS_ERR(h));
        u64 object=h->bo->handle, extra_va=h->base+0x100000;
        struct page *page=h->bo->pages[0];
        gpu_private_map_authorize(caller,held->handle,object,0,extra_va,1,3|8,&r);assert(!r.status);
        u64 grant=r.value[0];
        realm_gpu_heap_put(h);
        assert(!heap_context_busy(held->handle) && bo_lookup(caller,object)->pending==1);
        assert(gpu_private_range_busy(caller,page->ipa,4096));
        gpu_private_service_map(&ops,&service,caller,held->handle,grant,0,extra_va,1,3|8,&r);assert(!r.status);
        realm_gpu_reap_private();assert(bo_lookup(caller,object)->mapped==1);
        gpu_private_unmap_bo(&ops,caller,held->handle,object,0,extra_va,1,&r);assert(!r.status);
        realm_gpu_reap_private();assert(!bo_lookup(caller,object));
        realm_gpu_context_put(held);no_leaks();cases++;
    }
    /* Wrong offset late in a batch must leave the valid prefix intact. */
    struct realm_gpu_context *c=context_new();
    struct realm_gpu_bo *bo=realm_gpu_bo_alloc(7,3*4096,3);
    const u64 va=0x80000000;
    gpu_private_map(&ops,caller,c->handle,bo->handle,0,va,1,3|8,&r);assert(!r.status);
    gpu_private_map(&ops,caller,c->handle,bo->handle,2*4096,va+4096,1,3|8,&r);assert(!r.status);
    struct private_context *ctx=ctx_lookup(caller,c->handle);
    unsigned long epoch=ctx->mapping_epoch;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,2,&r);assert(r.status==GPU_PRIVATE_STATE);
    assert(ctx->mapping_epoch==epoch && ctx->mapped==2);
    gpu_private_mapping_check(&ops,caller,c->handle,bo->handle,0,va,1,3|8,&r);assert(!r.status);cases++;
    gpu_private_unmap_bo(&ops,&client_b,c->handle,bo->handle,0,va,1,&r);assert(r.status==GPU_PRIVATE_INPUT);cases++;
    gpu_private_unmap_bo(&ops,&service,c->handle,bo->handle,0,va,1,&r);assert(r.status==GPU_PRIVATE_INPUT);cases++;
    /* Bad non-leaf, including a descriptor pointing into another context,
     * is not allowed to masquerade as an empty, successfully cleaned range.
     */
    unsigned int root_index=(va>>39)&511;
    uint64_t saved=tables[ctx->root][root_index];
    tables[ctx->root][root_index]=2;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,1,&r);assert(r.status==GPU_PRIVATE_STATE);
    assert(ctx->mapped==2 && ctx->mapping_epoch==epoch);tables[ctx->root][root_index]=saved;cases++;
    struct realm_gpu_context *other_ctx=context_new();
    tables[ctx->root][root_index]=table_pa(tables[ctx_lookup(caller,other_ctx->handle)->root])|3;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,1,&r);assert(r.status==GPU_PRIVATE_STATE);
    tables[ctx->root][root_index]=saved;realm_gpu_context_put(other_ctx);cases++;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,1,va,1,&r);assert(r.status==GPU_PRIVATE_INPUT);cases++;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,513,&r);assert(r.status==GPU_PRIVATE_INPUT);cases++;
    ctx->activated=true;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,1,&r);assert(r.status==GPU_PRIVATE_STATE);
    ctx->activated=false;cases++;
    ctx->task_refs=1;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,1,&r);assert(r.status==GPU_PRIVATE_STATE);
    ctx->task_refs=0;cases++;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,1,&r);assert(!r.status && r.value[0]==4096);
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,0,va,1,&r);assert(!r.status && r.value[0]==4096);cases++;
    gpu_private_unmap_bo(&ops,caller,c->handle,bo->handle,2*4096,va+4096,1,&r);assert(!r.status);
    realm_gpu_bo_put(bo);realm_gpu_context_put(c);no_leaks();
}
/* Synthetic firmware events and cache/AS callbacks, actual Client allocation,
 * PT extension, holds, return and cleanup. Real firmware events are separately
 * covered by the production firmware/platform backend suite. */
static void oom_tests(void)
{
    unsigned int first_case=cases;
    assert(realm_gpu_task_heap_service(NULL)==-EINVAL);cases++;
    for(unsigned int scenario=0;scenario<31;scenario++) {
        struct realm_gpu_context *c=context_new();
        u32 size=(scenario==1 || scenario==22 || scenario==23)?SZ_8M:SZ_128K;
        u64 start=scenario==6?PRIVATE_GPU_VA_END-PAGE_SIZE-size:0x80000000;
        assert(!realm_gpu_context_set_va_split(c,start));
        struct realm_gpu_heap *h=heap_new(c,1,size);assert(!IS_ERR(h));
        struct realm_gpu_task task={.handle=oom_token,.channel=7,.context=c->handle,.queue_mask=1};
        struct gpu_private_result r;
        struct gpu_private_command_range empty={0};
        assert(gpu_private_context_hold(&service,caller,c->handle));
        assert(gpu_private_task_hold_batch(&ops,&service,caller,c->handle,&empty,1));
        gpu_private_context_prepare(&ops,&service,caller,c->handle,0x300000,&r);assert(!r.status);
        do {gpu_private_task_cache(&ops,&service,caller,c->handle,oom_token,&r);}
        while(r.status==GPU_PRIVATE_INCOMPLETE);
        assert(!r.status);
        oom_context=c->handle;oom_event=10000+scenario;oom_heap=h->base;oom_queue=0;oom_counts=1;
        grow_object=grow_va=0;grow_calls=event_calls=heap_reply_fault=device_syncs=fail_sync=0;
        bool must_reset=false;
        if(scenario==2)oom_counts=h->target_in_flight+1;
        if(scenario==3)h->max_chunks=h->initial_chunks;
        if(scenario==4)fail_alloc=alloc_calls+1;
        if(scenario==5)fail_bo=true;
        if(scenario==7)oom_heap+=64;
        if(scenario==8)task.context++;
        if(scenario==9)task.channel++;
        if(scenario==10)h->abandoned=true;
        if(scenario>=11 && scenario<=15)heap_reply_fault=scenario-10;
        if(scenario==16)grow_lost=true;
        if(scenario>=17 && scenario<=20)heap_reply_fault=scenario-11;
        if(scenario==21)fail_sync=1;
        if(scenario==22)heap_reply_fault=10;
        if(scenario==24)alloc_abandon=true;
        if(scenario==27)task.abandoned=true;
        if(scenario==28)task.handle=0;
        if(scenario>=29)oom_event=0;
        if(scenario==30)heap_reply_fault=1;
        int ret=realm_gpu_task_heap_service(&task);
        if(scenario==1 || scenario==23) {
            assert(ret==-EAGAIN && task.heap_pages==512 && grow_calls==1 && event_calls==1);
            if(scenario==23) {
                u64 old_object=task.heap_object;
                gpu_private_device_revoked(&ops);memset(live_roots,0,sizeof(live_roots));
                realm_gpu_heap_put(h);h=NULL;
                assert(realm_gpu_task_heap_service(&task)==-EBUSY && grow_calls==1);
                assert(!bo_lookup(caller,old_object));must_reset=true;
            } else {
                while(ret==-EAGAIN)ret=realm_gpu_task_heap_service(&task);
                assert(!ret && grow_calls==4 && event_calls==1 && !task.heap_event);
            }
        } else if((scenario>=7 && scenario<=10)) {
            assert(ret==-ENOENT && !grow_calls && list_empty(&h->chunks));
        } else if((scenario>=11 && scenario<=15) || (scenario>=17 && scenario<=20) || scenario==22 || scenario==30) {
            assert(ret==-EPROTO);must_reset=true;
        } else if(scenario==16) {assert(ret==-EIO && grow_calls==1);must_reset=true;}
        else if(scenario==21) {assert(ret==-EBUSY && grow_calls==0);must_reset=true;}
        else if(scenario==24) {assert(ret==-ECANCELED && h->abandoned && list_empty(&h->chunks));must_reset=true;}
        else if(scenario==27 || scenario==28) {assert(ret==-EINVAL && !event_calls && !grow_calls);}
        else {
            assert(!ret && !task.heap_event);
            if((scenario>=2 && scenario<=6) || scenario==29)
                assert(!grow_object && list_empty(&h->chunks));
            else if(scenario==0 || scenario==25 || scenario==26) {
                assert(grow_object && device_syncs==size/PAGE_SIZE);
                struct realm_gpu_heap_chunk *chunk=list_first_entry(&h->chunks,struct realm_gpu_heap_chunk,link);
                assert(chunk->bo->handle==grow_object && chunk->base==grow_va);
                for(unsigned int i=0;i<64;i++)assert(!chunk->bo->pages[0]->data[i]);
                struct realm_gpu_call raw={.operation=REALM_GPU_MAP,.handle=c->handle,
                    .args={0,0,chunk->base,1}};
                assert(heap_range_busy(&raw));
                assert(heap_free_va_locked(c->handle,h->base,SZ_128K)>=chunk->base+chunk->bytes);
                if(scenario==25) {
                    h->max_chunks=2;oom_event++;grow_object=grow_va=0;
                    assert(!realm_gpu_task_heap_service(&task) && !grow_object && grow_calls==2);
                }
                if(scenario==26) {
                    oom_event++;grow_object=grow_va=0;
                    assert(!realm_gpu_task_heap_service(&task) && grow_calls==2);
                    assert(grow_va>=chunk->base+chunk->bytes);
                }
            }
        }
        fail_alloc=0;fail_bo=alloc_abandon=grow_lost=false;heap_reply_fault=fail_sync=0;
        if(must_reset) {
            gpu_private_device_revoked(&ops);memset(live_roots,0,sizeof(live_roots));
        } else {
            gpu_private_context_quiesce(&ops,&service,caller,c->handle,oom_token,0x300000,&r);assert(!r.status);
            do {gpu_private_task_return(&ops,&service,caller,c->handle,oom_token,&r);}
            while(r.status==GPU_PRIVATE_INCOMPLETE);
            assert(!r.status && gpu_private_task_retire(&service,caller,c->handle,oom_token));
            gpu_private_context_put(caller,c->handle);memset(live_roots,0,sizeof(live_roots));
        }
        if(h)realm_gpu_heap_put(h);
        realm_gpu_context_put(c);realm_gpu_reap_private();no_leaks();
        printf("GPU_PRIVATE_HEAP_GROW=PASS scenario=%u MODEL_ONLY\n",scenario);
    }
    assert(cases-first_case==32);
}
static void resident_client_tests(void)
{
    for(unsigned int fault=0;fault<=8;fault++) {
        struct realm_gpu_bo *bo=realm_gpu_bo_alloc(7,(fault==8?513:1)*PAGE_SIZE,3);
        assert(!IS_ERR(bo));seal_reply_fault=fault;
        mutex_lock(&gpu_lock);int ret=seal_bo_locked(bo);mutex_unlock(&gpu_lock);
        assert(ret==(fault==0?0:fault==1?-EIO:-EPROTO) && bo->resident);
        assert(gpu_private_range_busy(caller,bo->pages[0]->ipa,PAGE_SIZE));
        assert(!bo->pages[0]->visible); /* Bad replies must not restore/free. */
        seal_reply_fault=0;realm_gpu_bo_put(bo);no_leaks();cases++;
    }
    struct realm_gpu_bo *bo=realm_gpu_bo_alloc(7,PAGE_SIZE,3);
    for(unsigned int i=0;i<2;i++) {
        struct realm_gpu_call call={.operation=i?REALM_GPU_BO_RELEASE:REALM_GPU_BO_SEAL,.handle=bo->handle};
        unsigned int before=calls;
        int ret=realm_gpu_private_call(&call);
        assert(ret==(i?-EBUSY:-EINVAL) && calls==before);cases++;
    }
    realm_gpu_bo_put(bo);no_leaks();
}
static void uncached_client_tests(void)
{
    for(unsigned int fault=0;fault<=9;fault++) {
        struct realm_gpu_bo *bo=realm_gpu_bo_alloc(7,(fault>=8?513:1)*PAGE_SIZE,7);
        assert(!IS_ERR(bo));uncached_reply_fault=fault;
        int ret=realm_gpu_bo_set_uncached(bo);
        assert(ret==(fault==0 || fault==9?0:fault==1?-EIO:-EPROTO) && bo->uncached);
        assert(gpu_private_range_busy(caller,bo->pages[0]->ipa,PAGE_SIZE));
        assert(bo->pages[0]->visible && bo->pages[0]->nc);
        uncached_reply_fault=0;realm_gpu_bo_put(bo);no_leaks();cases++;
    }
    struct realm_gpu_bo *bo=realm_gpu_bo_alloc(7,PAGE_SIZE,3);
    struct realm_gpu_call call={.operation=REALM_GPU_BO_UNCACHED,.handle=bo->handle};
    unsigned int before=calls;
    assert(realm_gpu_private_call(&call)==-EINVAL && calls==before);cases++;
    realm_gpu_bo_put(bo);no_leaks();
}
int main(void)
{
    exact_cleanup_tests();
    struct realm_gpu_context *c=context_new();
    assert(realm_gpu_context_set_va_split(c,0)==-EINVAL);
    assert(realm_gpu_context_set_va_split(c,0x80000001)==-EINVAL);
    assert(realm_gpu_context_set_va_split(c,PRIVATE_GPU_VA_END)==-EINVAL);
    assert(!realm_gpu_context_set_va_split(c,0x80000000));
    assert(!realm_gpu_context_set_va_split(c,0x80000000));
    assert(realm_gpu_context_set_va_split(c,0x90000000)==-EINVAL);cases+=6;
    for(unsigned int bad=0;bad<7;bad++) {
        unsigned int before=source_calls;
        if(bad==6)realm=false;
        struct realm_gpu_heap *h=realm_gpu_heap_create(c,7,bad==0?0:bad==1?4:1,
            bad==2?4096:bad==3?SZ_128K+1:bad==4?SZ_8M+4096:SZ_128K,2,3);
        if(bad==5) {assert(!IS_ERR(h));realm_gpu_heap_put(h);}
        else assert(PTR_ERR(h)==-EINVAL && source_calls==before);
        realm=true;cases++;
    }
    fail_alloc=alloc_calls+1;assert(PTR_ERR(heap_new(c,1,SZ_128K))==-ENOMEM);fail_alloc=0;cases++;
    fail_bo=true;assert(PTR_ERR(heap_new(c,1,SZ_128K))==-ENOMEM);fail_bo=false;cases++;
    struct realm_gpu_heap *h=heap_new(c,3,SZ_128K);assert(!IS_ERR(h));check_mapping(h);
    assert(realm_gpu_heap_context_va(h)==0x80000000);
    assert(realm_gpu_heap_first_chunk_va(h)==h->base+4096+2*SZ_128K);
    for(unsigned int j=0;j<4096;j++)assert(!h->bo->pages[0]->data[j]);
    for(unsigned int i=0;i<3;i++) {
        unsigned char *hdr=h->bo->pages[1+i*(SZ_128K/4096)]->data;
        u64 next;memcpy(&next,hdr,8);
        assert(next==(i?((h->base+4096+(i-1)*SZ_128K)|(SZ_128K>>12)):0));
        for(unsigned int j=8;j<64;j++)assert(!hdr[j]);
    }cases++;
    struct realm_gpu_heap *h2=heap_new(c,1,SZ_128K);assert(!IS_ERR(h2) && h2->base>=h->base+h->bytes);cases++;
    for(unsigned int op=0;op<4;op++) {
        struct realm_gpu_call raw={.operation=op==0?REALM_GPU_MAP:op==1?REALM_GPU_MAP_AUTHORIZE:op==2?REALM_GPU_UNMAP:REALM_GPU_UNMAP_BO,.handle=c->handle};
        if(op!=2)raw.args[2]=h->base,raw.args[3]=1;else raw.args[0]=h->base,raw.args[1]=1;
        unsigned int before=calls;
        assert(realm_gpu_private_call(&raw)==-EBUSY && calls==before);
        assert(realm_gpu_ioctl(REALM_GPU_CALL,(unsigned long)&raw)==-EBUSY);
        check_mapping(h);cases++;
    }
    /* A second actual modeled Client can use the same GPUVA, distinct PTEs. */
    caller=&client_b;
    struct realm_gpu_context *cb=context_new();assert(!realm_gpu_context_set_va_split(cb,0x80000000));
    struct realm_gpu_heap *hb=heap_new(cb,1,SZ_128K);assert(!IS_ERR(hb) && hb->base==h->base);
    check_mapping(hb);assert(hb->bo->pages[0]->ipa!=h->bo->pages[0]->ipa);
    realm_gpu_heap_put(hb);realm_gpu_context_put(cb);caller=&client_a;check_mapping(h);cases++;
    realm_gpu_heap_put(h);realm_gpu_heap_put(h2);realm_gpu_context_put(c);no_leaks();
    /* A mapping can be installed before a transport/sync/typed reply fails. */
    for(unsigned int bad=0;bad<3;bad++) {
        c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
        if(bad==1) {
            struct gpu_private_result active;
            gpu_private_context_activate(&ops,&service,c->handle,1,&active);assert(!active.status);
        }
        fail_map_at=map_calls+2;transport_fail=bad==0;corrupt_map=bad==2;
        assert(IS_ERR(heap_new(c,1,SZ_8M)));
        fail_map_at=0;transport_fail=false;corrupt_map=false;sync_ok=true;
        if(bad==1) {assert(heap_context_busy(c->handle));gpu_private_device_revoked(&ops);}
        realm_gpu_context_put(c);no_leaks();cases++;
    }
    /* A genuine RMM task hold blocks unmap and context reuse. */
    c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
    h=heap_new(c,1,SZ_128K);assert(!IS_ERR(h));
    struct gpu_private_command_range range={0};
    assert(gpu_private_context_hold(&service,caller,c->handle));
    assert(gpu_private_task_hold_batch(&ops,&service,caller,c->handle,&range,1));
    u64 ch=c->handle;realm_gpu_heap_put(h);assert(heap_context_busy(ch));
    realm_gpu_context_put(c);assert(managed_context(ch) && heap_context_busy(ch));
    assert(gpu_private_task_put(caller,ch));gpu_private_context_put(caller,ch);realm_gpu_reap_private();no_leaks();cases++;
    /* Partial unmap retains its exact cursor and VA, even after a bad reply. */
    c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
    h=heap_new(c,1,SZ_8M);assert(!IS_ERR(h));corrupt_unmap=true;
    realm_gpu_heap_put(h);assert(heap_context_busy(c->handle));
    corrupt_unmap=false;realm_gpu_reap_private();assert(!heap_context_busy(c->handle));
    realm_gpu_context_put(c);no_leaks();cases++;
    /* Keep the successful unmap prefix and never reuse uncertain VA. */
    c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
    h=heap_new(c,1,SZ_8M);assert(!IS_ERR(h));fail_unmap_at=unmap_calls+2;
    realm_gpu_heap_put(h);assert(heap_context_busy(c->handle) && h->unmap_cursor==512);
    h2=heap_new(c,1,SZ_128K);assert(!IS_ERR(h2) && h2->base>=h->base+h->bytes);
    realm_gpu_heap_put(h2);fail_unmap_at=0;realm_gpu_reap_private();
    realm_gpu_context_put(c);no_leaks();cases++;
    c=context_new();assert(!realm_gpu_context_set_va_split(c,PRIVATE_GPU_VA_END-4096));
    assert(PTR_ERR(heap_new(c,1,SZ_128K))==-ENOSPC);realm_gpu_context_put(c);no_leaks();cases++;
    c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
    struct realm_gpu_heap *quota[128];
    for(unsigned int i=0;i<128;i++){quota[i]=heap_new(c,1,SZ_128K);assert(!IS_ERR(quota[i]));}
    assert(PTR_ERR(heap_new(c,1,SZ_128K))==-ENOSPC);
    for(unsigned int i=0;i<128;i++)realm_gpu_heap_put(quota[i]);
    realm_gpu_context_put(c);no_leaks();cases++;
    /* Actual DRM frontend create/destroy and VM/file teardown; no heap RPC. */
    c=context_new();assert(!realm_gpu_context_set_va_split(c,0x80000000));
    struct panthor_client_file f={.session_id=9,.private_data=true};
    actual_frontend_xarray_init(&f);
    assert(f.heaps.alloc && f.syncobjs.alloc && !f.private_vms.alloc);cases++;
    f.private_vms.slot[1]=c;
    struct drm_panthor_tiler_heap_create args={.vm_id=1,.initial_chunk_count=2,
        .chunk_size=SZ_128K,.max_chunks=8,.target_in_flight=3};
    assert(!panthor_client_tiler_heap_create(&f,&args) && args.handle && !heap_rpc_calls);
    assert(!panthor_client_tiler_heap_destroy(&f,args.handle) && !destroy_rpc_calls);cases++;
    f.heaps.fail_insert=true;assert(panthor_client_tiler_heap_create(&f,&args)==-ENOMEM);
    f.heaps.fail_insert=false;assert(!heap_context_busy(c->handle));cases++;
    args.vm_id=2;assert(panthor_client_tiler_heap_create(&f,&args)==-ENOENT);args.vm_id=1;cases++;
    assert(!panthor_client_tiler_heap_create(&f,&args));
    panthor_client_private_heaps_release_vm(&f,2);assert(xa_load(&f.heaps,args.handle));
    panthor_client_private_heaps_release_vm(&f,1);assert(!xa_load(&f.heaps,args.handle));cases++;
    assert(!panthor_client_tiler_heap_create(&f,&args));panthor_client_heaps_release_local(&f);cases++;
    f.private_vms.slot[1]=NULL;realm_gpu_context_put(c);no_leaks();
    f.private_data=false;
    assert(!panthor_client_tiler_heap_create(&f,&args) && heap_rpc_calls==1);
    assert(!panthor_client_tiler_heap_destroy(&f,args.handle) && destroy_rpc_calls==1);cases++;
    no_leaks();
    oom_tests();
    resident_client_tests();
    uncached_client_tests();

    for(unsigned int gone=0;gone<2;gone++) {
        struct realm_gpu_context *c=context_new();
        assert(!realm_gpu_context_set_va_split(c,0x80000000));
        struct realm_gpu_group g={.context=c->handle,.handle=777};
        list_add_tail(&g.link,&private_groups);
        assert(gpu_private_context_hold(&service,caller,c->handle));
        assert(!realm_gpu_group_local_hint(&g,c,7));
        struct realm_gpu_heap *h=g.local_hint;
        assert(h && h->bo->uncached && h->bo->pages[0]->visible && h->bo->pages[0]->nc);
        struct private_context *rc=ctx_lookup(caller,c->handle);
        unsigned int pt=walk(&ops,rc,h->base,NULL);
        assert(pt!=GPU_PRIVATE_TABLES && (tables[pt][(h->base>>12)&511] & PTE_XN)==PTE_XN);
        assert((tables[pt][(h->base>>12)&511] & (7UL<<2))==0); /* GPU NC */
        struct realm_gpu_task t={.handle=888};
        struct realm_gpu_task_command cmd={.start=0x200000,.bytes=128,.queue=3,.latest_flush=77};
        struct realm_gpu_call stage={.operation=REALM_GPU_TASK_STAGE_BATCH};
        local_hint_commands(&t,&g,&stage);g.local_hint_task=t.handle;
        assert(cmd.start==0x200000 && cmd.bytes==128 && cmd.queue==3 && cmd.latest_flush==77);
        assert(stage.operation==REALM_GPU_TASK_STAGE_HINT && stage.args[4]==h->base);
        u64 *w=page_address(h->bo->pages[0]);
        assert(!w[0] && !w[1] && realm_gpu_task_hint_pending(&t) && h->bo->refs==2);
        w[0]=1;assert(!realm_gpu_task_hint_pending(&t));
        w[0]=0;w[1]=1;assert(!realm_gpu_task_hint_pending(&t));w[1]=0;
        assert(gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base));
        assert(!gpu_private_task_hint_check(&ops,&client_b,caller,c->handle,h->base));
        assert(!gpu_private_task_hint_check(&ops,&service,&client_b,c->handle,h->base));
        assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base+8));
        assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,PRIVATE_GPU_VA_END));
        uint64_t *leaf=&tables[pt][(h->base>>12)&511],saved=*leaf;
        for(unsigned int fault=0;fault<6;fault++) {
            *leaf=saved;
            if(fault==0)*leaf^=4096;
            if(fault==1)*leaf|=PTE_RO;
            if(fault==2)*leaf&=~PTE_XN;
            if(fault==3)*leaf^=1ULL<<2;
            if(fault==4)*leaf&=~PTE_USER;
            if(fault==5)*leaf=0;
            assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base));
        }
        *leaf=saved;
        struct private_bo *rb=bo_lookup(caller,h->bo->handle);
        rb->uncached=false;assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base));rb->uncached=true;
        rb->closing=true;assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base));rb->closing=false;
        rb->hidden=0;assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base));rb->hidden=1;
        rc->revoked=true;assert(!gpu_private_task_hint_check(&ops,&service,caller,c->handle,h->base));rc->revoked=false;
        assert(!gpu_private_task_hold(&ops,&service,caller,c->handle,cmd.start,cmd.bytes));
        assert(gpu_private_task_hold(&ops,&service,caller,c->handle,h->base,16));
        h->abandoned=true;
        mutex_lock(&gpu_lock);reap_heaps();mutex_unlock(&gpu_lock);assert(!list_empty(&private_heaps) && h->bo->refs==2);
        assert(gpu_private_task_put(caller,c->handle));
        if(gone) {
            list_del(&g.link);gpu_private_context_put(caller,c->handle);
            mutex_lock(&gpu_lock);reap_heaps();mutex_unlock(&gpu_lock);assert(list_empty(&private_heaps));
            assert(t.hint_bo->refs==1 && realm_gpu_task_hint_pending(&t));
            task_drop_hint_locked(&t);assert(!t.hint_bo);
        } else {
            task_drop_hint_locked(&t);assert(!t.hint_bo && !g.local_hint_task);
            mutex_lock(&gpu_lock);reap_heaps();mutex_unlock(&gpu_lock);assert(list_empty(&private_heaps));
            list_del(&g.link);gpu_private_context_put(caller,c->handle);
        }
        realm_gpu_context_put(c);no_leaks();cases++;
    }
    printf("GPU_PRIVATE_HEAP=PASS cases=%u actual Client/frontend/kernel heap functions + actual RMM PT/ref core; private initialized data, native chunk links, RW/XN leaves, batching, owned VA, exact-object atomic cleanup, foreign-mapping preservation, prior-grant interleavings, fault retention, real task-hold gate and diagnostic protection; HOST_DOUBLES_ONLY NO_LINUX_CONCURRENCY_OR_PHYSICAL_GPU_EXECUTION\n",cases);
    return 0;
}
