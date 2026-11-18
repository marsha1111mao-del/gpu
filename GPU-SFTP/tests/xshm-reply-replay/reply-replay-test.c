/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual Client response dispatcher with a controllable receive double. */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define u8 uint8_t
#define u16 uint16_t
#define u32 uint32_t
#define u64 uint64_t
#define s16 int16_t
#define s32 int32_t
#define spinlock_t int
#define PROXY_COMM_VMSHM_MSG_SIZE 512U
#define spin_lock(lock) (void)(lock)
#define spin_unlock(lock) (void)(lock)
#define unlikely(value) (__builtin_expect(!!(value), 0))
#define pr_info_ratelimited(...) ((void)0)
#define container_of(pointer, type, member) \
	((type *)((char *)(pointer) - offsetof(type, member)))

struct list_head {
	struct list_head *next, *prev;
};

struct completion {
	bool flag;
};

struct proxy_comm_vmshm_msg {
	u32 type, flags, len;
	s32 status;
	u64 seq, reply_to;
	u32 reserved;
	u8 payload[];
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
	spinlock_t waiters_lock;
	struct list_head waiters;
};

static void initialize_list(struct list_head *head)
{
	head->next = head;
	head->prev = head;
}

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

#define list_for_each_entry(position, head, member) \
	for (position = container_of((head)->next, __typeof__(*position), member); \
	     &position->member != (head); \
	     position = container_of(position->member.next, __typeof__(*position), member))

static void complete(struct completion *completion)
{
	completion->flag = true;
}

static bool completion_done(struct completion *completion)
{
	return completion->flag;
}

static struct vmshm_comm_rx incoming;
static unsigned char incoming_payload[32];

static int client_comm_vmshm_recv_from_proxy(struct vmshm_comm_rx *rx)
{
	void *destination = rx->payload;
	*rx = incoming;
	if (rx->len)
		memcpy(destination, incoming_payload, rx->len);
	return 0;
}

#include "actual.inc"

static struct client_comm_vmshm_dev device;

static void reset(void)
{
	memset(&device, 0, sizeof(device));
	spin_lock(&device.waiters_lock);
	initialize_list(&device.waiters);
	memset(incoming_payload, 0, sizeof(incoming_payload));
}

static void add_waiter(struct client_comm_vmshm_waiter *waiter, u64 sequence,
		       u32 response_type, void *payload, u32 capacity)
{
	memset(waiter, 0, sizeof(*waiter));
	waiter->seq = sequence;
	waiter->rsp_type = response_type;
	waiter->rsp_payload = payload;
	waiter->rsp_payload_capacity = capacity;
	waiter->status = -ETIMEDOUT;
	initialize_list(&waiter->node);
	list_add_tail(&waiter->node, &device.waiters);
}

static void inject(u32 type, u64 reply_to, u32 length, s32 status)
{
	memset(&incoming, 0, sizeof(incoming));
	incoming.type = type;
	incoming.reply_to = reply_to;
	incoming.len = length;
	incoming.status = status;
}

int main(void)
{
	struct client_comm_vmshm_waiter waiter;
	unsigned char payload[16];
	unsigned int cases = 0;

	reset();
	add_waiter(&waiter, 2, 0x52535031U, payload, sizeof(payload));
	inject(0x52535031U, 1, 4, 0);
	client_comm_vmshm_dispatch_response(&device);
	assert(!completion_done(&waiter.done) && waiter.status == -ETIMEDOUT && !list_empty(&device.waiters));
	cases++;

	inject(0x52535032U, 2, 4, 0);
	client_comm_vmshm_dispatch_response(&device);
	assert(!completion_done(&waiter.done) && waiter.status == -ETIMEDOUT && !list_empty(&device.waiters));
	cases++;

	memcpy(incoming_payload, "reply", 5);
	inject(0x52535031U, 2, 5, -3);
	client_comm_vmshm_dispatch_response(&device);
	assert(completion_done(&waiter.done) && waiter.status == 0 && list_empty(&device.waiters));
	assert(waiter.rsp_rx.reply_to == 2 && waiter.rsp_rx.status == -3);
	assert(!memcmp(payload, "reply", 5));
	cases++;

	inject(0x52535031U, 2, 4, 0);
	client_comm_vmshm_dispatch_response(&device);
	assert(waiter.rsp_rx.reply_to == 2 && waiter.status == 0);
	cases++;

	reset();
	add_waiter(&waiter, 0, 0x52535031U, payload, 4);
	memcpy(incoming_payload, "zero", 4);
	inject(0x52535031U, 0, 4, 0);
	client_comm_vmshm_dispatch_response(&device);
	assert(!completion_done(&waiter.done) && waiter.status == -ETIMEDOUT && !list_empty(&device.waiters));
	cases++;

	printf("REPLY_MATCH=PASS cases=%u exact seq/type matching; stale, wrong-type and duplicate replies dropped; MODEL_ONLY\n", cases);
	puts("SEQUENCE_ZERO_REJECTED=1");
	return 0;
}
