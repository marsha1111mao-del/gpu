/* SPDX-License-Identifier: GPL-2.0-only */
/* Production cache functions; modeled allocator, RTT query and locks. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef unsigned long long u64;
typedef uint32_t u32;
typedef unsigned int refcount_t;
#define PAGE_SIZE 4096UL
/* Scale cache budget only; production uses 1 MiB through 256 MiB. */
#define SZ_1M (2 * PAGE_SIZE)
#define SZ_256M (8 * PAGE_SIZE)
#define GFP_KERNEL 0
#define REALM_GPU_BO_IDLE 69
#define REALM_GPU_BO_UNCACHED 54
#define REALM_GPU_BATCH_PAGES 2
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define EXPORT_SYMBOL_GPL(x)
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define pr_info(...) ((void)0)
struct page { unsigned char data[PAGE_SIZE]; };
struct list_head { int unused; };
struct realm_gpu_call { u64 operation, handle, status, result[4]; };
static int gpu_lock, live_caches, live_bos, allocs, queries, clears, frees, denies, fail_release, bad_reply;
static bool idle = true;
static int private_status(u64 status) { return status == 4 ? -EAGAIN : status ? -EIO : 0; }
static unsigned long nc_pages = 4;
static void mutex_lock(int *l) { assert(!*l); *l = 1; }
static void mutex_unlock(int *l) { assert(*l); *l = 0; }
static void refcount_set(refcount_t *p, unsigned n) { *p = n; }
static void refcount_inc(refcount_t *p) { assert(*p); ++*p; }
static bool refcount_dec_and_test(refcount_t *p) { assert(*p); return --*p == 0; }
static void *kzalloc(size_t n, int flags) { (void)flags; live_caches++; return calloc(1,n); }
static void kfree(void *p) { if(p) { live_caches--; free(p); } }
static void cond_resched(void) { }
static void wmb(void) { }
static void list_del(struct list_head *l) { (void)l; }
static void clear_highpage(struct page *p) { assert(gpu_lock && idle); clears++; memset(p->data,0,PAGE_SIZE); }
#include "cache-structs.inc"
static struct realm_gpu_bo *private_bo_alloc(u64 channel,u64 bytes,u32 access,bool control)
{
	assert(channel && access && !control && !gpu_lock);
	struct realm_gpu_bo *bo = calloc(1,sizeof(*bo));
	bo->nr_pages = bytes / PAGE_SIZE; bo->pages = calloc(bo->nr_pages,sizeof(*bo->pages));
	for(unsigned long i=0;i<bo->nr_pages;i++) bo->pages[i]=calloc(1,sizeof(struct page));
	bo->handle = ++allocs; bo->refs=1; bo->uncached=true; bo->uncached_complete=true; live_bos++; return bo;
}
static void free_backing(struct realm_gpu_bo *bo)
{
	assert(gpu_lock); for(unsigned long i=0;i<bo->nr_pages;i++)free(bo->pages[i]);
	free(bo->pages);free(bo);live_bos--;frees++;
}
static int unregister_bo(struct realm_gpu_bo *bo) { (void)bo; assert(gpu_lock); return fail_release ? -EBUSY : 0; }
static int gpu_call_locked(struct realm_gpu_call *call,void *p)
{
	assert(gpu_lock && !p);
	if(call->operation==REALM_GPU_BO_UNCACHED) { call->result[0]=nc_pages; return 0; }
	assert(call->operation==REALM_GPU_BO_IDLE); queries++;
	if(!idle){call->status=2;denies++;return 0;}
	/* Test sizes always four pages except size-change scenarios. */
	call->result[0]=4*PAGE_SIZE;
	call->result[1]=bad_reply; return 0;
}
#define pr_warn(...) ((void)0)
void realm_gpu_bo_put(struct realm_gpu_bo *bo);
#include "cache-functions.inc"
static void dirty(struct realm_gpu_bo *bo)
{
	for(unsigned long i=0;i<bo->nr_pages;i++) memset(bo->pages[i]->data,0xab,PAGE_SIZE);
}
static void clean(struct realm_gpu_bo *bo)
{
	for(unsigned long i=0;i<bo->nr_pages;i++)for(unsigned j=0;j<PAGE_SIZE;j++)assert(!bo->pages[i]->data[j]);
}
int main(void)
{
	struct realm_gpu_bo_cache *c=realm_gpu_bo_cache_create(1,7), *d;
	struct realm_gpu_bo *a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE),*b;
	u64 original=a->handle;
	dirty(a); realm_gpu_bo_put(a); assert(c->idle && live_bos==1);
	a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE); assert(a->handle==original && allocs==1); clean(a);
	assert(realm_gpu_bo_set_uncached(a)==0);
	/* Separate DRM files cannot obtain each other's contents/backing. */
	d=realm_gpu_bo_cache_create(1,7);b=realm_gpu_bo_alloc_cached(d,4*PAGE_SIZE);assert(b->handle!=original);
	realm_gpu_bo_put(b);realm_gpu_bo_cache_close(d);
	/* Final local ref is required; an active holder cannot enter cache. */
	refcount_inc(&a->refs);realm_gpu_bo_put(a);assert(!c->idle && a->refs==1);
	/* Fresh RMM refusal on put prevents reuse, even after local refs vanish. */
	idle=false;realm_gpu_bo_put(a);assert(!c->idle);idle=true;
	a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);original=a->handle;realm_gpu_bo_put(a);
	/* Refusal after caching also prevents reading/writing old pages. */
	int before=clears;idle=false;a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);assert(a->handle!=original && clears==before);idle=true;
	realm_gpu_bo_put(a);bad_reply=1;a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);assert(clears==before);bad_reply=0;
	/* Only one idle slot; another object's put follows normal release. */
	b=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);realm_gpu_bo_put(a);before=frees;realm_gpu_bo_put(b);assert(frees==before+1 && c->idle);
	/* Size mismatch evicts, never returns an undersized/oversized object. */
	a=realm_gpu_bo_alloc_cached(c,3*PAGE_SIZE);assert(a->nr_pages==3 && !c->idle);realm_gpu_bo_put(a);assert(!c->idle);
	/* Above budget never enters the cache. */
	a=realm_gpu_bo_alloc_cached(c,9*PAGE_SIZE);assert(!a->cache);realm_gpu_bo_put(a);
	/* Close drains slot while outstanding BOs keep the cache object alive. */
	a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);b=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);realm_gpu_bo_put(a);
	realm_gpu_bo_cache_close(c);assert(live_caches==1 && live_bos==1);realm_gpu_bo_put(b);assert(!live_caches && !live_bos);
	/* Failed real release retains backing; cache closure cannot free it. */
	c=realm_gpu_bo_cache_create(1,7);a=realm_gpu_bo_alloc_cached(c,4*PAGE_SIZE);idle=false;fail_release=1;realm_gpu_bo_put(a);realm_gpu_bo_cache_close(c);
	assert(live_bos==1 && !live_caches && !a->cache && !a->refs);
	fail_release=0;idle=true;refcount_set(&a->refs,1);realm_gpu_bo_put(a);assert(!live_bos);
	/* Only proven completion may bypass repeat NC conversion. An uncertain
	 * release-intent flag cannot suppress validation of a malformed reply. */
	a=private_bo_alloc(1,4*PAGE_SIZE,7,false);a->uncached_complete=false;
	assert(realm_gpu_bo_set_uncached(a)==-EPROTO && !a->uncached_complete);
	realm_gpu_bo_put(a);
	a=private_bo_alloc(1,2*PAGE_SIZE,7,false);a->uncached_complete=false;nc_pages=2;
	assert(!realm_gpu_bo_set_uncached(a) && a->uncached_complete);
	assert(!realm_gpu_bo_set_uncached(a));realm_gpu_bo_put(a);
	assert(!gpu_lock && queries && denies && clears && !live_bos);
	puts("CLIENT_BO_CACHE=PASS reuse zeroing, owner scope, refs, RMM refusal, eviction, close and failed release retention");
}
