#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "linux/realm_gpu.h"

typedef uint32_t u32;
typedef unsigned long long u64;
struct mutex { pthread_mutex_t native; };
struct list_head { struct list_head *next, *prev; };
struct xarray { void *entries[2]; };
typedef struct { atomic_int value; } atomic_t;
typedef struct { _Atomic u64 value; } atomic64_t;
typedef atomic_t refcount_t;
struct proxy_comm_vmshm_channel { u32 owner; atomic_int refs; bool available; };
struct panthor_vmshm_session { unsigned int marker; };
struct panthor_proxy_bo { u32 proxy_bo_handle; };
struct panthor_proxy_group { unsigned int unused; };
struct panthor_proxy_vm { unsigned int unused; };
struct vmshm_comm_rx { u64 seq; };

#define GFP_KERNEL 0
#define XA_FLAGS_ALLOC1 0
#define ATOMIC_INIT(value_) { ATOMIC_VAR_INIT(value_) }
#define ATOMIC64_INIT(value_) { ATOMIC_VAR_INIT(value_) }
#define DEFINE_MUTEX(name) struct mutex name = { PTHREAD_MUTEX_INITIALIZER }
#define LIST_HEAD(name) struct list_head name = { &(name), &(name) }
#define pr_info(...) ((void)0)
#define pr_warn_ratelimited(...) ((void)0)
#define container_of(pointer, type, member) ((type *)((char *)(pointer) - offsetof(type, member)))
#define list_for_each_entry(entry, head, member) \
	for (struct list_head *cursor = (head)->next; \
	     cursor != (head) && ((entry) = container_of(cursor, __typeof__(*(entry)), member), true); \
	     cursor = cursor->next)
#define list_for_each_entry_safe(entry, temporary, head, member) \
	for (struct list_head *cursor = (head)->next, *next_cursor = cursor->next; \
	     cursor != (head) && ((entry) = container_of(cursor, __typeof__(*(entry)), member), \
	     (temporary) = next_cursor == (head) ? NULL : container_of(next_cursor, __typeof__(*(entry)), member), \
	     (void)(temporary), true); cursor = next_cursor, next_cursor = cursor->next)
#define xa_for_each(array, index, entry) \
	for ((index) = 0; (index) < 2; (index)++) \
		if (((entry) = (array)->entries[index]) != NULL)

static atomic_int allocations, native_sessions, native_open_calls, warnings;
static bool fail_allocation, fail_native_open, fail_response;
static unsigned int dumps;

static void mutex_init(struct mutex *lock) { assert(!pthread_mutex_init(&lock->native, NULL)); }
static void mutex_lock(struct mutex *lock) { assert(!pthread_mutex_lock(&lock->native)); }
static void mutex_unlock(struct mutex *lock) { assert(!pthread_mutex_unlock(&lock->native)); }
static int atomic_read(atomic_t *value) { return atomic_load(&value->value); }
static void atomic_inc(atomic_t *value) { atomic_fetch_add(&value->value, 1); }
static bool atomic_dec_and_test(atomic_t *value) { return atomic_fetch_sub(&value->value, 1) == 1; }
static u64 atomic64_inc_return(atomic64_t *value) { return atomic_fetch_add(&value->value, 1) + 1; }
static void refcount_set(refcount_t *value, int count) { atomic_store(&value->value, count); }
static void refcount_inc(refcount_t *value) { atomic_inc(value); }
static bool refcount_dec_and_test(refcount_t *value) { return atomic_dec_and_test(value); }
static bool warn_once(bool failed) { if (failed) atomic_fetch_add(&warnings, 1); return failed; }
#define WARN_ON_ONCE(condition) warn_once(condition)

static void list_add_tail(struct list_head *node, struct list_head *head)
{
	node->prev = head->prev; node->next = head;
	head->prev->next = node; head->prev = node;
}
static void list_del(struct list_head *node)
{
	node->prev->next = node->next; node->next->prev = node->prev;
	node->next = node; node->prev = node;
}
static void list_move_tail(struct list_head *node, struct list_head *head)
{ list_del(node); list_add_tail(node, head); }
static void xa_init_flags(struct xarray *array, unsigned int flags)
{ memset(array, 0, sizeof(*array)); }
static void xa_destroy(struct xarray *array) { memset(array, 0, sizeof(*array)); }
static void *kzalloc(size_t bytes, unsigned int flags)
{
	if (fail_allocation) return NULL;
	void *memory = calloc(1, bytes);
	assert(memory); atomic_fetch_add(&allocations, 1); return memory;
}
static void kfree(void *memory)
{ assert(memory && atomic_fetch_sub(&allocations, 1) > 0); free(memory); }
static bool proxy_comm_vmshm_channel_get(struct proxy_comm_vmshm_channel *channel)
{
	if (!channel || !channel->available) return false;
	atomic_fetch_add(&channel->refs, 1); return true;
}
static void proxy_comm_vmshm_channel_put(struct proxy_comm_vmshm_channel *channel)
{ assert(atomic_fetch_sub(&channel->refs, 1) > 0); }
static u32 proxy_comm_vmshm_channel_client_vmid(struct proxy_comm_vmshm_channel *channel)
{ return channel->owner; }
static u64 proxy_comm_vmshm_channel_rmm_channel(struct proxy_comm_vmshm_channel *channel)
{ return channel->available ? 1 : 0; }
static int panthor_vmshm_session_open(struct panthor_vmshm_session **session)
{
	atomic_fetch_add(&native_open_calls, 1);
	if (fail_native_open) return -EIO;
	*session = calloc(1, sizeof(**session)); assert(*session);
	atomic_fetch_add(&native_sessions, 1); return 0;
}
static void panthor_vmshm_session_close(struct panthor_vmshm_session *session)
{ assert(session && atomic_fetch_sub(&native_sessions, 1) > 0); free(session); }
static void panthor_vmshm_bo_destroy(struct panthor_vmshm_session *session, u32 handle) {}
static void panthor_proxy_rpc_stats_dump_current_if_enabled(const char *reason) { dumps++; }
static void panthor_proxy_log_session_access_denied(const char *operation, u64 session, u32 owner, u32 requester) {}
static int realm_gpu_private_call(struct realm_gpu_call *call)
{ call->status = 0; call->result[0] = REALM_GPU_ABI; call->result[1] = UINT64_MAX; return 0; }
static bool panthor_proxy_rmm_task_control_available(struct realm_gpu_call *call) { return true; }

#include "structures.inc"

static DEFINE_MUTEX(panthor_proxy_sessions_lock);
static LIST_HEAD(panthor_proxy_sessions);
static atomic64_t panthor_proxy_next_session_id = ATOMIC64_INIT(0);
static atomic_t panthor_proxy_active_sessions = ATOMIC_INIT(0);
static struct panthor_proxy_session_budget panthor_proxy_session_budgets[PANTHOR_PROXY_MAX_SESSIONS];
static bool panthor_proxy_session_id_exhausted;
static struct panthor_vmshm_open_session_rsp last_response;

static int panthor_proxy_send_rsp(struct proxy_comm_vmshm_channel *channel,
		u64 sequence, u32 type, int status, const void *payload, u32 bytes)
{
	assert(type == PANTHOR_VMSHM_MSG_OPEN_SESSION_RSP && bytes == sizeof(last_response));
	memcpy(&last_response, payload, bytes);
	return fail_response ? -ENOSPC : 0;
}

#include "actual.inc"

static struct proxy_comm_vmshm_channel channels[10];

static void clean_state(void)
{
	assert(atomic_read(&panthor_proxy_active_sessions) == 0);
	assert(atomic_load(&allocations) == 0 && atomic_load(&native_sessions) == 0);
	assert(atomic_load(&warnings) == 0);
	assert(panthor_proxy_sessions.next == &panthor_proxy_sessions);
	for (unsigned int index = 0; index < PANTHOR_PROXY_MAX_SESSIONS; index++)
		assert(!panthor_proxy_session_budgets[index].owner_vmid && !panthor_proxy_session_budgets[index].sessions);
	for (unsigned int index = 0; index < 10; index++) assert(!atomic_load(&channels[index].refs));
}

static void rollback_cases(void)
{
	u64 handle = 0;
	assert(panthor_proxy_session_create(&channels[0], 0, &handle) == -EINVAL);
	assert(panthor_proxy_session_create(&channels[0], 1, NULL) == -EINVAL);
	channels[0].available = false;
	assert(panthor_proxy_session_create(&channels[0], 1, &handle) == -ENODEV);
	channels[0].available = true; clean_state();
	fail_allocation = true;
	assert(panthor_proxy_session_create(&channels[0], 1, &handle) == -ENOMEM);
	fail_allocation = false; clean_state();
	fail_native_open = true;
	assert(panthor_proxy_session_create(&channels[0], 1, &handle) == -EIO);
	fail_native_open = false; clean_state();
}

static void held_close_case(void)
{
	u64 handles[PANTHOR_PROXY_MAX_SESSIONS_PER_CLIENT], extra = 0;
	for (unsigned int index = 0; index < PANTHOR_PROXY_MAX_SESSIONS_PER_CLIENT; index++)
		assert(!panthor_proxy_session_create(&channels[0], 1, &handles[index]));
	assert(panthor_proxy_session_create(&channels[0], 1, &extra) == -ENOSPC);
	assert(!panthor_proxy_session_lookup(handles[0], 2));
	assert(panthor_proxy_session_destroy(handles[0], 2) == -ENOENT);
	struct panthor_proxy_session *held = panthor_proxy_session_lookup(handles[0], 1);
	assert(held && !panthor_proxy_session_destroy(handles[0], 1));
	assert(!panthor_proxy_session_lookup(handles[0], 1));
	assert(panthor_proxy_session_destroy(handles[0], 1) == -ENOENT);
	assert(panthor_proxy_session_create(&channels[0], 1, &extra) == -ENOSPC);
	assert(atomic_read(&panthor_proxy_active_sessions) == PANTHOR_PROXY_MAX_SESSIONS_PER_CLIENT);
	panthor_proxy_session_put(held);
	assert(!panthor_proxy_session_create(&channels[0], 1, &extra));
	assert(extra != handles[0]);
	assert(!panthor_proxy_session_create(&channels[1], 2, &handles[0]));
	panthor_proxy_sessions_destroy_all(); clean_state();
}

static void global_limit_case(void)
{
	u64 handle;
	for (unsigned int owner = 0; owner < 8; owner++)
		for (unsigned int session = 0; session < PANTHOR_PROXY_MAX_SESSIONS_PER_CLIENT; session++)
			assert(!panthor_proxy_session_create(&channels[owner], owner + 1, &handle));
	assert(atomic_read(&panthor_proxy_active_sessions) == PANTHOR_PROXY_MAX_SESSIONS);
	assert(panthor_proxy_session_create(&channels[8], 9, &handle) == -ENOSPC);
	panthor_proxy_sessions_destroy_all(); clean_state();
}

struct thread_result { int status; u64 handle; };
static void *concurrent_create(void *opaque)
{
	struct thread_result *result = opaque;
	result->status = panthor_proxy_session_create(&channels[0], 1, &result->handle);
	return NULL;
}
static void concurrent_case(void)
{
	pthread_t threads[32];
	struct thread_result results[32] = {0};
	unsigned int admitted = 0;
	for (unsigned int index = 0; index < 32; index++)
		assert(!pthread_create(&threads[index], NULL, concurrent_create, &results[index]));
	for (unsigned int index = 0; index < 32; index++) {
		assert(!pthread_join(threads[index], NULL));
		assert(results[index].status == 0 || results[index].status == -ENOSPC);
		admitted += results[index].status == 0;
	}
	assert(admitted == PANTHOR_PROXY_MAX_SESSIONS_PER_CLIENT);
	assert(atomic_read(&panthor_proxy_active_sessions) == (int)admitted);
	panthor_proxy_sessions_destroy_all(); clean_state();
}

static void open_response_case(void)
{
	struct panthor_vmshm_open_session_req request = {.version = PANTHOR_VMSHM_ABI_VERSION};
	struct vmshm_comm_rx rx = {.seq = 1};
	fail_response = true;
	panthor_proxy_handle_open_session(&channels[0], &rx, &request);
	assert(!last_response.ret && last_response.session_id);
	fail_response = false; clean_state();
	panthor_proxy_handle_open_session(&channels[0], &rx, &request);
	assert(!last_response.ret && last_response.session_id);
	assert(!panthor_proxy_session_destroy(last_response.session_id, 1)); clean_state();
}

static void exhaustion_case(void)
{
	u64 handle = 0;
	atomic_store(&panthor_proxy_next_session_id.value, UINT64_MAX);
	assert(panthor_proxy_session_create(&channels[0], 1, &handle) == -EOVERFLOW);
	assert(panthor_proxy_session_id_exhausted); clean_state();
	int opened = atomic_load(&native_open_calls);
	for (unsigned int index = 0; index < 10; index++)
		assert(panthor_proxy_session_create(&channels[0], 1, &handle) == -EOVERFLOW);
	assert(atomic_load(&native_open_calls) == opened); clean_state();
}

int main(void)
{
	for (unsigned int index = 0; index < 10; index++) {
		channels[index].owner = index + 1;
		channels[index].available = true;
	}
	clean_state(); rollback_cases(); held_close_case(); global_limit_case();
	concurrent_case(); open_response_case(); exhaustion_case();
	assert(dumps > 0);
	puts("GPU_PROXY_SESSION_BUDGET=PASS total=64 per_client=8 threads=32 rollback/retained-close/cross-owner/reply-failure/ID-exhaustion actual_functions pthread_native_doubles");
	return 0;
}
