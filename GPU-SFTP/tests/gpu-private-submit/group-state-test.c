// SPDX-License-Identifier: GPL-2.0-only
/* Actual Client status-query functions; locks, transport and RSI are doubles. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __user
#include "linux/realm_gpu.h"
#include "drm/panthor_drm.h"

typedef uint32_t u32;
typedef uint64_t u64;
#define PAGE_SIZE 4096UL
#define EXPORT_SYMBOL_GPL(x)
#define pr_info(...) ((void)0)
struct list_head { struct list_head *next, *prev; };
#include "structures.inc"

struct panthor_client_group {
    struct realm_gpu_group *private_group;
    u32 private_queue_count, client_handle;
    unsigned int refs;
};
struct xarray { struct panthor_client_group *group; };
struct panthor_client_file {
    struct xarray groups;
    u64 session_id;
    int lock, private_gpu_lock;
    bool private_gpu_failed;
};
static int gpu_lock, transport_error, inspect_status;
static unsigned int calls, cases;
static bool realm = true, managed = true, ref_allowed = true;
static u64 reply[4] = { 1, 3, 4096, 8 };
static struct realm_gpu_group rmm_group = { .handle = 41 };
static struct panthor_client_group group = {
    .private_group = &rmm_group, .private_queue_count = 3,
    .client_handle = 11, .refs = 1,
};
static struct panthor_client_file file = {
    .groups = { &group }, .session_id = 29,
};
static void mutex_lock(int *lock) { assert(!*lock); *lock = 1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static bool is_realm_world(void) { return realm; }
static bool managed_group(u64 handle) { return managed && handle == rmm_group.handle; }
static u64 client_comm_vmshm_rmm_channel(void) { return 7; }
static void *xa_load(struct xarray *array, u32 id) { return id == 11 ? array->group : NULL; }
static bool panthor_client_group_get(struct panthor_client_group *g)
{
    if (!ref_allowed) return false;
    g->refs++;
    return true;
}
static void panthor_client_group_put(struct panthor_client_group *g)
{
    assert(g->refs > 1);
    g->refs--;
}
static int private_status(u64 status)
{
    if (!status) return 0;
    if (status == 1) return -EINVAL;
    if (status == 2) return -EBUSY;
    if (status == 3) return -ENOSPC;
    if (status == 4) return -EAGAIN;
    return -EIO;
}
static int gpu_call_locked(struct realm_gpu_call *call, void *snapshot)
{
    assert(gpu_lock);
    assert(call->operation == REALM_GPU_GROUP_INSPECT && call->handle == 41);
    assert(call->args[0] == 7 && !call->args[1] && !call->args[2] &&
           !call->args[3] && !call->args[4] && !snapshot);
    calls++;
    call->status = inspect_status;
    memcpy(call->result, reply, sizeof(reply));
    return transport_error;
}
#include "actual.inc"

static void reset(void)
{
    assert(!gpu_lock && !file.lock && !file.private_gpu_lock && group.refs == 1);
    realm = managed = ref_allowed = true;
    transport_error = inspect_status = 0;
    rmm_group.retired = false;
    reply[0] = 1; reply[1] = 3; reply[2] = 4096; reply[3] = 8;
    file.private_gpu_failed = false;
    file.groups.group = &group;
    calls = 0;
}
static void query(int expected, u32 state)
{
    struct drm_panthor_group_get_state args = {
        .group_handle = 11, .state = 0xdead, .fatal_queues = 0xbeef,
    };
    assert(panthor_client_group_get_state(&file, &args) == expected);
    if (!expected) {
        assert(args.state == state && args.fatal_queues == 0);
    } else {
        assert(args.state == 0xdead && args.fatal_queues == 0xbeef);
    }
    assert(group.refs == 1 && !gpu_lock && !file.lock && !file.private_gpu_lock);
    cases++;
}
int main(void)
{
    /* RESERVED, PREPARED, STARTED and QUIESCED are usable metadata states.
     * Closing/quarantined must be unusable, never silently reported healthy.
     */
    for (u64 state = 1; state <= 6; state++) {
        reset(); reply[0] = state;
        query(0, state == 2 || state == 3 ? DRM_PANTHOR_GROUP_STATE_FATAL_FAULT : 0);
        assert(calls == 1);
    }
    reset(); file.private_gpu_failed = true;
    query(0, DRM_PANTHOR_GROUP_STATE_FATAL_FAULT);
    assert(file.private_gpu_failed);
    for (unsigned int bad = 0; bad < 6; bad++) {
        reset();
        if (bad == 0) reply[0] = 0;
        if (bad == 1) reply[0] = 7;
        if (bad == 2) reply[1] = 4;
        if (bad == 3) reply[2] = 0;
        if (bad == 4) reply[2] = (u64)REALM_GPU_CONTROL_MAX_PAGES * PAGE_SIZE + 1;
        if (bad == 5) reply[3] = REALM_GPU_CONTROL_MAX_PAGES + 1;
        query(-EPROTO, 0);
    }
    reset(); inspect_status = 2; query(-EBUSY, 0);
    reset(); inspect_status = 1; query(-EINVAL, 0);
    reset(); transport_error = -EIO; query(-EIO, 0);
    reset(); rmm_group.retired = true; query(-EINVAL, 0); assert(!calls);
    reset(); managed = false; query(-EINVAL, 0); assert(!calls);
    reset(); realm = false; query(-EINVAL, 0); assert(!calls);
    reset(); ref_allowed = false; query(-ENOENT, 0); assert(!calls);
    reset(); file.groups.group = NULL; query(-ENOENT, 0); assert(!calls);
    for (unsigned int bad = 0; bad < 6; bad++) {
        bool unusable = true;
        reset();
        assert(realm_gpu_group_unusable(bad == 0 ? NULL : &rmm_group,
            bad == 1 ? 0 : 7, bad == 2 ? 0 : bad == 3 ? REALM_GPU_MAX_GROUP_STREAMS + 1 : 3,
            bad == 4 ? NULL : &unusable) == (bad == 5 ? 0 : -EINVAL));
        if (bad == 5) assert(!unusable);
        else assert(unusable && !calls);
        cases++;
    }
    reset();
    struct drm_panthor_group_get_state args = { .group_handle = 11 };
    assert(panthor_client_group_get_state(NULL, &args) == -EINVAL);
    assert(panthor_client_group_get_state(&file, NULL) == -EINVAL);
    args.pad = 1; assert(panthor_client_group_get_state(&file, &args) == -EINVAL);
    args.pad = 0; args.group_handle = 0;
    assert(panthor_client_group_get_state(&file, &args) == -EINVAL);
    assert(!calls && group.refs == 1); cases += 4;
    printf("PRIVATE_GROUP_STATE=PASS cases=%u (actual functions; RSI/DRM doubles)\n", cases);
    return 0;
}
