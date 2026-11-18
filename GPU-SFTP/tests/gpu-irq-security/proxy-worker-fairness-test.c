// SPDX-License-Identifier: GPL-2.0-only
/* Actual Proxy IRQ worker with modelled sessions/xarray/RMM events. */
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
typedef uint64_t u64;

#define READ_ONCE(value) (value)
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define container_of(pointer, type, member) \
	((type *)((char *)(pointer) - offsetof(type, member)))
#define list_for_each_entry(position, head, member) \
	for (position = container_of((head)->next, __typeof__(*position), member); \
	     &position->member != (head); \
	     position = container_of(position->member.next, __typeof__(*position), member))
#define xa_for_each(xarray, index, entry) \
	for ((index) = 0; ((entry) = xa_find((xarray), &(index))) != NULL; (index)++)

struct list_head { struct list_head *next, *prev; };
struct work_struct { int unused; };
struct mutex { int locked; };
struct xarray { void **entries; unsigned long count; };
struct refcount_t { unsigned int value; };
struct realm_gpu_call { u32 operation; u64 handle, args[6], result[4]; long status; };
struct proxy_comm_vmshm_channel { u64 rmm_channel; };

struct panthor_proxy_group {
	u64 private_group;
	bool irq_probed;
};

struct panthor_proxy_session {
	struct list_head node;
	u64 session_id;
	struct mutex lock;
	struct proxy_comm_vmshm_channel *channel;
	struct xarray groups;
	unsigned long irq_group_cursor;
	struct refcount_t refcnt;
	bool closing;
};

#define REALM_GPU_GROUP_IRQ_PEEK 9000U
#define REALM_GPU_GROUP_IRQ_CLAIM 9001U
#define REALM_GPU_IRQ_EVENT_FAULT (1UL << 4)
#define REALM_GPU_IRQ_FAULT 1UL
#define REALM_GPU_IRQ_PROGRESS 2UL

static struct list_head panthor_proxy_sessions;
static struct mutex panthor_proxy_sessions_lock;
static u64 panthor_proxy_irq_cursor;
static unsigned int worker_kicks;
static bool panthor_proxy_irq_probe;
static unsigned int peeks[12], claims[12];

static void *xa_find(struct xarray *xarray, unsigned long *index)
{
	while (*index < xarray->count) {
		void *entry = xarray->entries[*index];
		if (entry)
			return entry;
		(*index)++;
	}
	return NULL;
}

static bool list_empty(const struct list_head *head)
{
	return head->next == head;
}

static void mutex_lock(struct mutex *mutex)
{
	assert(mutex && !mutex->locked);
	mutex->locked = true;
}

static void mutex_unlock(struct mutex *mutex)
{
	assert(mutex && mutex->locked);
	mutex->locked = false;
}

static bool refcount_inc_not_zero(struct refcount_t *refcount)
{
	assert(refcount->value);
	refcount->value++;
	return true;
}

static void panthor_proxy_session_put(struct panthor_proxy_session *session)
{
	assert(session->refcnt.value);
	session->refcnt.value--;
}

static u64 proxy_comm_vmshm_channel_rmm_channel(
	struct proxy_comm_vmshm_channel *channel)
{
	assert(channel && channel->rmm_channel);
	return channel->rmm_channel;
}

static int realm_gpu_private_call(struct realm_gpu_call *call)
{
	unsigned int group = (unsigned int)(call->handle - 1U);

	assert(group < 12U && call->args[0]);
	if (call->operation == REALM_GPU_GROUP_IRQ_PEEK) {
		peeks[group]++;
		call->status = 0;
		call->result[0] = 0x100 + group;
		call->result[1] = 1;
		call->result[2] = 0;
		call->result[3] = 0x200 + group;
		return 0;
	}
	assert(call->operation == REALM_GPU_GROUP_IRQ_CLAIM);
	claims[group]++;
	call->status = 0;
	return 0;
}

static void schedule_delayed_work(void *work, unsigned long delay)
{
	(void)work;
	(void)delay;
	worker_kicks++;
}

static void panthor_proxy_irq_kick(void)
{
	schedule_delayed_work(NULL, 0);
}

#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)

#include "actual.inc"

int main(void)
{
	struct panthor_proxy_group groups[12];
	struct panthor_proxy_group *group_ptrs[12];
	struct panthor_proxy_session session;
	struct proxy_comm_vmshm_channel channel = { .rmm_channel = 77 };

	panthor_proxy_sessions.next = &panthor_proxy_sessions;
	panthor_proxy_sessions.prev = &panthor_proxy_sessions;
	memset(&session, 0, sizeof(session));
	memset(groups, 0, sizeof(groups));
	session.node.next = &panthor_proxy_sessions;
	session.node.prev = &panthor_proxy_sessions;
	panthor_proxy_sessions.next = &session.node;
	panthor_proxy_sessions.prev = &session.node;
	session.session_id = 1;
	session.channel = &channel;
	session.refcnt.value = 1;
	for (unsigned int i = 0; i < 12U; i++)
		group_ptrs[i] = &groups[i];
	session.groups.entries = (void **)group_ptrs;
	session.groups.count = 12;
	for (unsigned int i = 0; i < 12U; i++)
		groups[i].private_group = i + 1U;

	panthor_proxy_irq_work(&(struct work_struct){0});
	panthor_proxy_irq_work(&(struct work_struct){0});
	panthor_proxy_irq_work(&(struct work_struct){0});
	panthor_proxy_irq_work(&(struct work_struct){0});
	for (unsigned int i = 0; i < 12U; i++)
		assert(peeks[i] && claims[i]);
	assert(peeks[0] == 1 && peeks[11] == 1);
	assert(worker_kicks == 4);

	panthor_proxy_irq_work(&(struct work_struct){0});
	assert(peeks[0] == 2 && peeks[11] == 1);
	puts("PROXY_IRQ_WORKER_FAIRNESS=PASS 12 groups all visited within two budget-8 rounds");
	return 0;
}
