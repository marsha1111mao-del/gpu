// SPDX-License-Identifier: GPL-2.0-only
/* Actual driver functions, with small host kernel/RSI test doubles.
 * RMM permission checks and GPU MMIO are NOT exercised by this fixture.
 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "linux/realm_gpu.h"
#include "drm/panthor_drm.h"

struct realm_gpu_heap { bool abandoned; };
typedef uint32_t u32;
typedef uint64_t u64;
#define GFP_KERNEL 0
#define PRIVATE_STATUS_INPUT 1U
#define PRIVATE_STATUS_STATE 2U
#define PRIVATE_STATUS_FULL 3U
#define PRIVATE_STATUS_INCOMPLETE 4U
#define PANTHOR_VMSHM_MAX_GROUP_QUEUES 16
#define PANTHOR_PROXY_MAX_GROUPS_PER_SESSION 128
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095L)
#define DIV_ROUND_UP(a, b) (((a) + (b) - 1) / (b))
#define is_power_of_2(n) ((n) && !((n) & ((n) - 1)))
static unsigned int allocations, frees;
static void *kzalloc(size_t n, int flags)
{
	(void)flags;
	void *p = calloc(1, n);
	assert(p);
	allocations++;
	return p;
}
static void kfree(void *p) { if (p) { frees++; free(p); } }
#define __GFP_ZERO 0
struct page { unsigned char data[4096]; };
static bool fail_snapshot_alloc;
static struct page *alloc_page(int flags)
{
	return fail_snapshot_alloc ? NULL : kzalloc(sizeof(struct page), flags);
}
static void __free_page(struct page *p) { kfree(p); }
static void *page_address(struct page *p) { return p->data; }
struct list_head { struct list_head *next, *prev; };
#define LIST_HEAD(n) struct list_head n = { &(n), &(n) }
#define entry(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define list_for_each_entry(p, h, m) \
	for (p = entry((h)->next, __typeof__(*p), m); &(p)->m != (h); \
	     p = entry((p)->m.next, __typeof__(*p), m))
#define list_for_each_entry_safe(p, n, h, m) \
	for (p = entry((h)->next, __typeof__(*p), m), n = entry((p)->m.next, __typeof__(*p), m); \
	     &(p)->m != (h); p = n, n = entry((n)->m.next, __typeof__(*n), m))
static void list_add_tail(struct list_head *p, struct list_head *h)
{
	p->next = h; p->prev = h->prev; h->prev->next = p; h->prev = p;
}
static void list_del(struct list_head *p) { p->prev->next = p->next; p->next->prev = p->prev; }
static bool list_empty(struct list_head *p) { return p->next == p; }
static int gpu_lock;
static void mutex_lock(int *lock) { assert(!*lock); *lock = 1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static void cond_resched(void) { }
static bool is_realm_world(void) { return true; }
static void reap_backing(unsigned int budget) { (void)budget; }
struct xarray { void *slots[129]; bool fail_alloc; };
struct xa_limit { u32 min, max; };
#define XA_LIMIT(a,b) ((struct xa_limit){a,b})
#define xa_for_each(x, i, p) \
	for (i = 0; i < 129 && ((p) = (x)->slots[i], true); i++) if (p)
static void *xa_load(struct xarray *x, u32 i) { return i < 129 ? x->slots[i] : NULL; }
static void *xa_erase(struct xarray *x, u32 i)
{
	void *p = xa_load(x, i); if (i < 129) x->slots[i] = NULL; return p;
}
static int xa_alloc(struct xarray *x, u32 *id, void *p, struct xa_limit lim, int flags)
{
	(void)flags;
	if (x->fail_alloc) return -ENOMEM;
	for (u32 i = lim.min; i <= lim.max; i++) if (!x->slots[i]) {
		*id = i; x->slots[i] = p; return 0;
	}
	return -ENOSPC;
}
struct panthor_proxy_session {
	int lock;
	struct xarray vms, groups;
	void *real_session, *channel;
};
#include "actual-structures.inc"
_Static_assert(sizeof(struct panthor_vmshm_group_create_req) <= 476,
	"GROUP_CREATE must fit the unchanged RPC payload slot");
static LIST_HEAD(private_groups);
static LIST_HEAD(private_contexts);
static unsigned int create_status, destroy_status, retire_batches;
static unsigned int configure_status;
static unsigned int destroy_calls, context_destroy_calls, reschedules;
static bool rsi_transport_failure, group_exists;
static u64 next_handle = 0xcca5000000010001ULL;
static int gpu_call_locked(struct realm_gpu_call *call, void *unused)
{
	(void)unused;
	assert(gpu_lock);
	if (rsi_transport_failure) return -EIO;
	memset(call->result, 0, sizeof(call->result));
	if (call->operation == REALM_GPU_GROUP_CREATE) {
		assert(call->handle == 41 && call->args[0] == 7 && call->args[1] == 2);
		call->status = create_status;
		if (create_status == PRIVATE_STATUS_INPUT) return 0;
		assert(!group_exists);
		group_exists = true;
		call->result[0] = next_handle++;
		call->result[1] = 2;
		call->result[2] = 0x40000;
		call->result[3] = 68;
	} else if (call->operation == REALM_GPU_GROUP_CONFIGURE) {
		const struct realm_gpu_queue_config *q = page_address(unused);

		assert(group_exists && unused && call->args[1] == 7 && call->args[2] == 2);
		assert(q[0].ring_bytes == 4096 && q[1].ring_bytes == 65536 && q[1].priority == 15);
		call->status = configure_status;
		call->result[0] = 2; call->result[1] = 18;
	} else if (call->operation == REALM_GPU_GROUP_DESTROY) {
		destroy_calls++;
		call->status = destroy_status;
		if (!group_exists) call->status = PRIVATE_STATUS_INPUT;
		else if (retire_batches) { retire_batches--; call->status = PRIVATE_STATUS_INCOMPLETE; reschedules++; }
		else if (!call->status) group_exists = false;
	} else {
		assert(call->operation == REALM_GPU_CONTEXT_DESTROY);
		context_destroy_calls++;
		call->status = group_exists ? PRIVATE_STATUS_STATE : 0;
	}
	return 0;
}
static unsigned int native_creates, native_destroys, validations, invalidations;
static int validate_result;
static u64 expected_context = 41, expected_group = 81;
static u64 proxy_comm_vmshm_channel_rmm_channel(void *p) { assert(p); return 7; }
static int realm_gpu_private_call_checked(struct realm_gpu_call *call)
{
	validations++;
	assert(call->operation == REALM_GPU_GROUP_VALIDATE && call->args[0] == 7);
	if (call->handle != expected_group || call->args[1] != expected_context || call->args[2] != 2)
		return -EINVAL;
	if (call->args[3] && (call->args[3] > 2 || call->args[4] !=
	    (call->args[3] == 1 ? 4096UL : 65536UL)))
		return -EINVAL;
	return validate_result;
}
static void panthor_proxy_apply_group_core_partition(struct panthor_proxy_session *s, struct drm_panthor_group_create *a) { (void)s; (void)a; }
static void panthor_proxy_plans_invalidate(struct panthor_proxy_session *s, u32 g, u32 b) { (void)s; assert(g && !b); invalidations++; }
static int panthor_vmshm_group_create(void *s, struct drm_panthor_group_create *a, const struct drm_panthor_queue_create *q)
{
	(void)s; assert(a->vm_id == 9 && q[0].ringbuf_size == 4096); native_creates++; a->group_handle = 77; return 0;
}
static int panthor_vmshm_group_destroy(void *s, u32 handle) { (void)s; assert(handle == 77); native_destroys++; return 0; }
static void reap_heaps(void) { }
static bool heap_context_busy(u64 context) { (void)context; return false; }
#include "actual-functions.inc"

static struct realm_gpu_context *context(void)
{
	struct realm_gpu_context *c = kzalloc(sizeof(*c), 0);
	c->handle = 41; list_add_tail(&c->link, &private_contexts); return c;
}
static void kernel_lifetimes(void)
{
	struct realm_gpu_context *c = context();
	struct realm_gpu_group *g = realm_gpu_group_create(c, 7, 2);
	assert(!IS_ERR(g) && realm_gpu_group_handle(g) && managed_group(g->handle));
	assert(group_exists && !list_empty(&private_groups));
	struct realm_gpu_queue_config queues[2] = {
		{ .ring_bytes = 4096 }, { .ring_bytes = 65536, .priority = 15 }
	};

	assert(realm_gpu_group_configure(g, 7, queues, 0) == -EINVAL);
	fail_snapshot_alloc = true;
	assert(realm_gpu_group_configure(g, 7, queues, 2) == -ENOMEM);
	fail_snapshot_alloc = false; configure_status = PRIVATE_STATUS_STATE;
	assert(realm_gpu_group_configure(g, 7, queues, 2) == -EBUSY && group_exists);
	configure_status = 0;
	assert(!realm_gpu_group_configure(g, 7, queues, 2));
	destroy_status = PRIVATE_STATUS_STATE;
	realm_gpu_context_put(c);
	assert(!list_empty(&private_contexts)); /* RMM group holds context. */
	realm_gpu_group_put(g);
	assert(group_exists && managed_group(g->handle));
	assert(!list_empty(&private_contexts)); /* Scrub failure cannot release context. */
	destroy_status = 0; retire_batches = 3;
	mutex_lock(&gpu_lock); reap_groups(); reap_contexts(); mutex_unlock(&gpu_lock);
	assert(!group_exists && list_empty(&private_groups) && list_empty(&private_contexts));
	assert(reschedules == 3 && context_destroy_calls >= 2);

	/* CREATE failure may already own a quarantined RMM extent. */
	c = context(); create_status = PRIVATE_STATUS_STATE; destroy_status = PRIVATE_STATUS_STATE;
	g = realm_gpu_group_create(c, 7, 2);
	assert(IS_ERR(g) && group_exists && !list_empty(&private_groups));
	realm_gpu_context_put(c);
	assert(!list_empty(&private_contexts));
	rsi_transport_failure = true;
	mutex_lock(&gpu_lock); reap_groups(); mutex_unlock(&gpu_lock);
	assert(!list_empty(&private_groups));
	rsi_transport_failure = false; destroy_status = 0;
	mutex_lock(&gpu_lock); reap_groups(); reap_contexts(); mutex_unlock(&gpu_lock);
	assert(list_empty(&private_groups) && list_empty(&private_contexts));

	/* Definitive no-object rejection creates no managed handle or backing. */
	c = context(); create_status = PRIVATE_STATUS_INPUT;
	assert(IS_ERR(realm_gpu_group_create(c, 7, 2)) && list_empty(&private_groups));
	realm_gpu_context_put(c);
	assert(list_empty(&private_contexts));
	create_status = 0;
	c = context(); g = realm_gpu_group_create(c, 7, 2); assert(!IS_ERR(g));
	group_exists = false; /* Verified reset retired the RMM object. */
	realm_gpu_group_put(g); realm_gpu_context_put(c);
	assert(list_empty(&private_groups) && list_empty(&private_contexts));
}

static void proxy_paths(void)
{
	struct panthor_proxy_session s = { .channel = (void *)1 };
	struct panthor_proxy_vm vm = { .client_vm_id = 1, .proxy_vm_id = 9,
		.rmm_private = true, .private_context = 41 };
	struct panthor_vmshm_group_create_req req = { .client_vm_id = 1, .queue_count = 2, .private_group = 81,
		.queues = { { .ringbuf_size = 4096 }, { .ringbuf_size = 65536 } } };
	struct panthor_vmshm_group_create_rsp rsp = {0};
	u32 translated = 123;
	s.vms.slots[1] = &vm;
	assert(!panthor_proxy_session_group_create(&s, &req, &rsp));
	assert(validations == 3 && !native_creates && rsp.client_group_handle && !rsp.proxy_group_handle);
	assert(panthor_proxy_session_translate_group_locked(&s, rsp.client_group_handle, &translated) == -EOPNOTSUPP);
	assert(translated == 123); /* Never turn a reservation into native handle zero. */
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EEXIST);
	assert(validations == 3 && !native_creates);
	assert(!panthor_proxy_session_group_destroy(&s, rsp.client_group_handle, NULL));
	assert(!native_destroys && invalidations == 1);
	req.queues[0].ringbuf_size = 8192;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.queues[0].ringbuf_size = 4096; req.queues[1].priority = 1;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.queues[1].priority = 0;
	vm.private_context = 42;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	vm.private_context = 41; req.queue_count = 1;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.queue_count = 2; validate_result = -EBUSY;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EBUSY);
	validate_result = 0; s.groups.fail_alloc = true;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -ENOMEM);
	assert(!native_creates && !native_destroys); /* No native cleanup of Client token. */
	s.groups.fail_alloc = false; req.private_group = 0;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.private_group = 81; vm.rmm_private = false;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.private_group = 0; req.queues[0].ringbuf_size = 4097;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.queues[0].ringbuf_size = 4096; req.queues[1].pad[1] = 1;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -EINVAL);
	req.queues[1].pad[1] = 0;
	assert(!panthor_proxy_session_group_create(&s, &req, &rsp));
	assert(native_creates == 1 && rsp.proxy_group_handle == 77);
	assert(!panthor_proxy_session_translate_group_locked(&s, rsp.client_group_handle, &translated) && translated == 77);
	assert(!panthor_proxy_session_group_destroy(&s, rsp.client_group_handle, NULL) && native_destroys == 1);
	s.groups.fail_alloc = true;
	assert(panthor_proxy_session_group_create(&s, &req, &rsp) == -ENOMEM);
	assert(native_creates == 2 && native_destroys == 2); /* Existing native rollback retained. */
}
int main(void)
{
	kernel_lifetimes(); proxy_paths(); assert(allocations == frees);
	printf("GPU_GROUP_BRIDGE=PASS actual Guest helpers and Proxy create/destroy/translation; quarantine/transport failure retention, context ordering, bounded retirement, no native fallback, substitution/duplicate rejection, native rollback; host doubles only (%u destroy calls)\n", destroy_calls);
	return 0;
}
