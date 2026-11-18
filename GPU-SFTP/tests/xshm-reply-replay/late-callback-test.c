// SPDX-License-Identifier: GPL-2.0-only
/* Actual RPC call/dispatcher functions with deterministic late-reply windows. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int16_t s16;
typedef int32_t s32;
typedef int atomic_t;
typedef uint64_t atomic64_t;
typedef int mutex_t;
typedef int spinlock_t;

#define unlikely(value) (__builtin_expect(!!(value), 0))
#define PROXY_COMM_VMSHM_MSG_SIZE 512U
#define PANTHOR_VMSHM_MSG_CLOSE_SESSION_REQ 0x1002U
#define INIT_LIST_HEAD(pointer) do { \
	(pointer)->next = (pointer); (pointer)->prev = (pointer); \
} while (0)
#define container_of(pointer, type, member) \
	((type *)((char *)(pointer) - offsetof(type, member)))
#define list_for_each_entry(position, head, member) \
	for (position = container_of((head)->next, __typeof__(*position), member); \
	     &position->member != (head); \
	     position = container_of(position->member.next, __typeof__(*position), member))

struct list_head { struct list_head *next, *prev; };
struct completion { bool done; };
struct proxy_comm_vmshm_msg {
	u32 type, flags, len;
	s32 status;
	u64 seq, reply_to;
	u32 reserved;
	u8 payload[];
};

struct vmshm_comm_tx {
	u32 type, flags;
	const void *payload;
	u32 len;
	u64 seq;
};

struct vmshm_comm_rx {
	u32 type, flags;
	u64 seq, reply_to;
	s32 status;
	void *payload;
	u32 payload_capacity, len;
	void *proxy_channel;
};

struct client_comm_vmshm_waiter {
	struct list_head node;
	struct completion done;
	u64 seq;
	u32 rsp_type;
	void *rsp_payload;
	u32 rsp_payload_capacity;
	struct vmshm_comm_rx rsp_rx;
	int status;
};

struct client_comm_vmshm_dev {
	mutex_t rpc_lock;
	spinlock_t waiters_lock;
	struct list_head waiters;
	atomic64_t next_seq;
};

struct client_comm_vmshm_rpc_sample {
	u32 req_type;
	int ret;
	u64 total_ns, lock_wait_ns, send_ns, wait_ns, poll_recv_ns;
	u64 poll_sleeps, queue_ns, notify_ns, reply_poll_ns, arm_ns;
	u64 completion_wait_ns;
};

enum late_mode { DISPATCHER_WINS, TIMEOUT_WINS };

static struct client_comm_vmshm_dev client_comm_vmshm_dev;
static atomic_t client_comm_vmshm_rpc_active;
static atomic_t client_comm_vmshm_rpc_peak;
static unsigned long jiffies = 100;
static pthread_mutex_t spin_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t rpc_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t sync_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t sync_cond = PTHREAD_COND_INITIALIZER;
static struct vmshm_comm_rx incoming;
static unsigned char incoming_payload[16];
static enum late_mode mode = DISPATCHER_WINS;
static bool orchestrate_timeout;
static bool timeout_phase;
static bool dispatcher_waiting, release_late, dispatcher_done;
static bool timeout_removed;

static void list_add_tail(struct list_head *entry, struct list_head *head)
{
	entry->prev = head->prev;
	entry->next = head;
	head->prev->next = entry;
	head->prev = entry;
}

static void list_del_init(struct list_head *entry)
{
	entry->prev->next = entry->next;
	entry->next->prev = entry->prev;
	entry->next = entry;
	entry->prev = entry;
}

static bool list_empty(const struct list_head *head)
{
	return head->next == head;
}

static void complete(struct completion *completion)
{
	completion->done = true;
}

static bool completion_done(struct completion *completion)
{
	return completion->done;
}

static bool client_comm_vmshm_rpc_stats_is_enabled(void)
{
	return false;
}

static u64 ktime_get_ns(void)
{
	return 0;
}

static bool client_comm_vmshm_concurrent_rpc;

static void mutex_lock(mutex_t *lock)
{
	pthread_mutex_lock(&rpc_mutex);
	assert(!*lock);
	*lock = 1;
	pthread_mutex_unlock(&rpc_mutex);
}

static void mutex_unlock(mutex_t *lock)
{
	pthread_mutex_lock(&rpc_mutex);
	assert(*lock);
	*lock = 0;
	pthread_mutex_unlock(&rpc_mutex);
}

static int atomic_inc_return(atomic_t *value)
{
	return ++*value;
}

static int atomic_read(const atomic_t *value)
{
	return *value;
}

static int atomic_cmpxchg(atomic_t *value, int expected, int replacement)
{
	int old = *value;
	if (old == expected)
		*value = replacement;
	return old;
}

static void atomic_dec(atomic_t *value)
{
	--*value;
}

static u64 atomic64_inc_return(atomic64_t *value)
{
	return ++*value;
}

static bool client_comm_vmshm_ready(void)
{
	return true;
}

static unsigned int client_comm_vmshm_rpc_timeout(void)
{
	return 1;
}

static void init_completion(struct completion *completion)
{
	memset(completion, 0, sizeof(*completion));
}

static void spin_lock(spinlock_t *lock)
{
	pthread_mutex_lock(&spin_mutex);
	assert(!*lock);
	*lock = 1;
	if (lock == &client_comm_vmshm_dev.waiters_lock && orchestrate_timeout && timeout_phase) {
		pthread_mutex_lock(&sync_mutex);
		while (!dispatcher_waiting)
			pthread_cond_wait(&sync_cond, &sync_mutex);
		release_late = true;
		pthread_cond_broadcast(&sync_cond);
		pthread_mutex_unlock(&sync_mutex);
	}
	pthread_mutex_unlock(&spin_mutex);
}

static void spin_unlock(spinlock_t *lock)
{
	pthread_mutex_lock(&spin_mutex);
	assert(*lock);
	*lock = 0;
	if (lock == &client_comm_vmshm_dev.waiters_lock && orchestrate_timeout && timeout_phase) {
		timeout_removed = true;
		orchestrate_timeout = false;
		timeout_phase = false;
	}
	pthread_mutex_unlock(&spin_mutex);
}

static int client_comm_vmshm_send_to_proxy(
	const struct vmshm_comm_tx *tx,
	struct client_comm_vmshm_rpc_sample *sample)
{
	(void)tx;
	(void)sample;
	return 0;
}

static unsigned long msecs_to_jiffies(unsigned int milliseconds)
{
	return milliseconds;
}

static bool time_before(unsigned long left, unsigned long right)
{
	return left < right;
}

static void client_comm_vmshm_poll_response(
	struct client_comm_vmshm_dev *d,
	struct client_comm_vmshm_waiter *waiter)
{
	(void)d;
	(void)waiter;
}

static void client_comm_vmshm_prepare_response_wait(
	struct client_comm_vmshm_dev *d,
	struct client_comm_vmshm_waiter *waiter)
{
	(void)d;
	(void)waiter;
}

static const char *client_comm_vmshm_req_name(u32 type)
{
	(void)type;
	return "LATE_CALLBACK";
}

static void pr_warn_ratelimited(const char *format, ...)
{
	(void)format;
}

static void pr_info_ratelimited(const char *format, ...)
{
	(void)format;
}

static void pr_info(const char *format, ...)
{
	(void)format;
}

static void client_comm_vmshm_rpc_stats_dump_current_if_enabled(
	const char *reason)
{
	(void)reason;
}

static void client_comm_vmshm_rpc_stats_record(
	const struct client_comm_vmshm_rpc_sample *sample)
{
	(void)sample;
}

static void prepare_reply(void)
{
	memset(&incoming, 0, sizeof(incoming));
	memset(incoming_payload, 0x5a, sizeof(incoming_payload));
	incoming.type = 0x52535031U;
	incoming.reply_to = client_comm_vmshm_dev.next_seq;
	incoming.len = 4;
	incoming.status = 0;
	incoming.payload = incoming_payload;
	incoming.payload_capacity = sizeof(incoming_payload);
}

static int client_comm_vmshm_dispatch_response(
	struct client_comm_vmshm_dev *d);

static void *late_dispatcher(void *argument)
{
	struct client_comm_vmshm_dev *d = argument;
	int ret = client_comm_vmshm_dispatch_response(d);

	assert(ret == 0);
	dispatcher_done = true;
	return NULL;
}

static int client_comm_vmshm_recv_from_proxy(struct vmshm_comm_rx *rx)
{
	void *destination = rx->payload;

	if (mode == TIMEOUT_WINS) {
		pthread_mutex_lock(&sync_mutex);
		dispatcher_waiting = true;
		pthread_cond_broadcast(&sync_cond);
		while (!release_late)
			pthread_cond_wait(&sync_cond, &sync_mutex);
		pthread_mutex_unlock(&sync_mutex);
	}
	*rx = incoming;
	if (rx->len)
		memcpy(destination, incoming_payload, rx->len);
	return 0;
}

static unsigned long wait_for_completion_timeout(
	struct completion *completion, unsigned long timeout)
{
	pthread_t thread;

	assert(timeout != 0);
	prepare_reply();
	if (mode == DISPATCHER_WINS) {
		assert(client_comm_vmshm_dispatch_response(&client_comm_vmshm_dev) == 0);
		assert(completion_done(completion));
		return 0;
	}
	assert(pthread_create(&thread, NULL, late_dispatcher, &client_comm_vmshm_dev) == 0);
	timeout_phase = true;
	return 0;
}

#include "actual.inc"

static void reset(enum late_mode next_mode)
{
	pthread_mutex_lock(&spin_mutex);
	assert(!client_comm_vmshm_dev.waiters_lock && !client_comm_vmshm_dev.rpc_lock);
	pthread_mutex_unlock(&spin_mutex);
	memset(&client_comm_vmshm_dev, 0, sizeof(client_comm_vmshm_dev));
	INIT_LIST_HEAD(&client_comm_vmshm_dev.waiters);
	memset(&incoming, 0, sizeof(incoming));
	memset(incoming_payload, 0, sizeof(incoming_payload));
	mode = next_mode;
	orchestrate_timeout = next_mode == TIMEOUT_WINS;
	timeout_phase = false;
	dispatcher_waiting = release_late = dispatcher_done = false;
	timeout_removed = false;
}

int main(void)
{
	unsigned char payload[16];
	struct vmshm_comm_rx response;

	reset(DISPATCHER_WINS);
	memset(payload, 0, sizeof(payload));
	memset(&response, 0, sizeof(response));
	assert(client_comm_vmshm_call(0x51524551U, 0, NULL, 0, 0x52535031U,
		payload, sizeof(payload), &response) == 0);
	assert(!memcmp(payload, incoming_payload, 4));
	assert(response.reply_to == 1 && list_empty(&client_comm_vmshm_dev.waiters));

	reset(TIMEOUT_WINS);
	memset(payload, 0, sizeof(payload));
	memset(&response, 0, sizeof(response));
	assert(client_comm_vmshm_call(0x51524551U, 0, NULL, 0, 0x52535031U,
		payload, sizeof(payload), &response) == -ETIMEDOUT);
	while (!dispatcher_done)
		sched_yield();
	assert(timeout_removed && dispatcher_done && list_empty(&client_comm_vmshm_dev.waiters));
	assert(payload[0] == 0 && payload[1] == 0);
	puts("RPC_LATE_WAITER=PASS dispatcher-first and timeout-first interleavings; actual call/dispatcher functions with host doubles");
	return 0;
}
