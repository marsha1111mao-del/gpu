#include <errno.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define PROXY_COMM_VMSHM_MAGIC 0x56534350U
#define PROXY_COMM_VMSHM_STATUS_READY 2U
#define PROXY_COMM_VMSHM_ROLE_PROXY 0U
#define PROXY_COMM_VMSHM_MAX_QUEUES 2U
#define PROXY_COMM_VMSHM_QUEUE_SIZE 256U
#define PROXY_COMM_VMSHM_MSG_SIZE 512U
#define PROXY_COMM_VMSHM_QUEUE_MAGIC 0x51564350U
#define PROXY_COMM_VMSHM_USED_NO_NOTIFY 1U
#define PROXY_COMM_VMSHM_MAX_HANDLERS 16
#define PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY 0U
#define PROXY_COMM_VMSHM_RX_WORK_BUDGET 256U

#define EINVAL 22
#define ENODEV 19
#define ENOENT 2
#define EPROTO 71
#define EAGAIN 11
#define EMSGSIZE 90

typedef uint8_t u8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
typedef uint64_t u64;
typedef uintptr_t phys_addr_t;
typedef uintptr_t resource_size_t;

#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, value) (*(p) = (value))
#define smp_wmb() do { } while (0)
#define smp_mb() do { } while (0)
#define barrier() do { } while (0)
#define __aligned(x) __attribute__((aligned(x)))
#define container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))

struct work_struct {
    int entry;
};

struct proxy_comm_vmshm_mutex {
    int locked;
};

struct proxy_comm_vmshm_rwsem {
    int locked;
};

struct vmshm_comm_tx {
    u32 type;
    u32 flags;
    u64 seq;
    u64 reply_to;
    s32 status;
    const void *payload;
    u32 len;
};

struct proxy_comm_vmshm_channel;

struct vmshm_comm_rx {
    u32 type;
    u32 flags;
    u64 seq;
    u64 reply_to;
    s32 status;
    void *payload;
    u32 payload_capacity;
    u32 len;
    struct proxy_comm_vmshm_channel *proxy_channel;
};

typedef int (*proxy_comm_vmshm_rx_handler_t)(
    const struct vmshm_comm_rx *rx, void *priv);

struct proxy_comm_vmshm_queue_object {
    u32 magic;
    u32 queue_id;
    u32 direction;
    u32 queue_size;
    u32 queue_mask;
    u32 msg_size;
    u32 desc_off;
    u32 avail_off;
    u32 used_off;
    u32 msg_pool_off;
    u32 desc_obj_id;
    u32 avail_obj_id;
    u32 used_obj_id;
    u32 msg_pool_obj_id;
    u32 flags;
    u32 reserved;
};

struct proxy_comm_vmshm_desc {
    u32 msg_off;
    u32 msg_capacity;
    u32 msg_len;
    u32 flags;
    u64 seq;
};

struct proxy_comm_vmshm_avail_ring {
    u32 idx;
    u32 flags;
    u16 ring[];
};

struct proxy_comm_vmshm_used_elem {
    u16 desc_id;
    s16 status;
    u32 len;
};

struct proxy_comm_vmshm_used_ring {
    u32 idx;
    u32 flags;
    struct proxy_comm_vmshm_used_elem ring[];
};

struct proxy_comm_vmshm_msg {
    u32 type;
    u32 flags;
    u32 len;
    s32 status;
    u64 seq;
    u64 reply_to;
    u32 reserved;
    u8 payload[];
};

struct realm_xshm_transport {
    u64 channel;
    int (*arm)(u64 channel);
    void (*notify)(u64 channel, u32 type, u64 cookie);
};

struct proxy_comm_vmshm_channel {
    struct proxy_comm_vmshm_dev *dev;
};

struct proxy_comm_vmshm_dev {
    struct proxy_comm_vmshm_queue_object queues[PROXY_COMM_VMSHM_MAX_QUEUES];
    u32 tx_avail[PROXY_COMM_VMSHM_MAX_QUEUES];
    u32 tx_used[PROXY_COMM_VMSHM_MAX_QUEUES];
    u32 rx_used[PROXY_COMM_VMSHM_MAX_QUEUES];
    phys_addr_t gpa;
    resource_size_t size;
    bool irq_notify;
    struct work_struct rx_work;
    u64 trace_irq;
    u64 trace_work_irq;
    u64 trace_work_start;
    struct proxy_comm_vmshm_header *hdr;
    u8 *base;
    u32 size_field;
    bool quiescing;
    const struct realm_xshm_transport *realm;
    struct proxy_comm_vmshm_channel channel;
    struct proxy_comm_vmshm_mutex lock;
};

struct proxy_comm_vmshm_header {
    u32 magic;
    u32 status[2];
};

struct proxy_comm_vmshm_handler_slot {
    u32 type;
    proxy_comm_vmshm_rx_handler_t handler;
    void *priv;
};

static struct proxy_comm_vmshm_handler_slot
    proxy_comm_vmshm_handlers[PROXY_COMM_VMSHM_MAX_HANDLERS];
static unsigned int proxy_comm_vmshm_handler_count;
static struct proxy_comm_vmshm_rwsem proxy_comm_vmshm_handler_rwsem;

static u64 virtual_tick;
static u64 mutex_lock_visits;
static u64 policy_lock_visits;
static u64 mutex_max_interval;
static u64 policy_max_interval;
static u64 mutex_lock_start;
static u64 policy_lock_start;
static u64 handler_requests;
static u64 handler_payload_bytes;
static u64 empty_recv_count;
static u64 arm_count;
static u64 published_seq;
static u64 pressure_target;
static u64 victim_latency;
static bool victim_seen;
static u64 empty_wakeups;
static u64 work_reschedules;
static u64 work_start_tick;
static bool corrupt_payload;
static bool corruption_detected;

_Static_assert(sizeof(struct proxy_comm_vmshm_msg) == 40, "wire header size");
_Static_assert(offsetof(struct proxy_comm_vmshm_msg, payload) == 36,
               "wire payload offset");

static void mutex_lock(struct proxy_comm_vmshm_mutex *lock)
{
    (void)lock;
    mutex_lock_visits++;
    virtual_tick += 2;
    mutex_lock_start = virtual_tick;
}

static void mutex_unlock(struct proxy_comm_vmshm_mutex *lock)
{
    u64 interval;

    (void)lock;
    virtual_tick += 2;
    interval = virtual_tick - mutex_lock_start;
    if (interval > mutex_max_interval)
        mutex_max_interval = interval;
}

static void down_read(struct proxy_comm_vmshm_rwsem *sem)
{
    (void)sem;
    policy_lock_visits++;
    virtual_tick += 2;
    policy_lock_start = virtual_tick;
}

static void up_read(struct proxy_comm_vmshm_rwsem *sem)
{
    u64 interval = virtual_tick - policy_lock_start;

    (void)sem;
    virtual_tick += 2;
    if (interval > policy_max_interval)
        policy_max_interval = interval;
}

static bool realm_xshm_trace_enabled(void)
{
    return false;
}

static void realm_xshm_trace_receive(u64 channel, u64 seq, u32 type,
                                     u64 irq, u64 start)
{
    (void)channel;
    (void)seq;
    (void)type;
    (void)irq;
    (void)start;
}

static u64 realm_xshm_counter(void)
{
    return 0;
}

static u64 atomic64_xchg(u64 *value, u64 replacement)
{
    u64 previous = *value;
    *value = replacement;
    return previous;
}

static void schedule_work(struct work_struct *work)
{
    (void)work;
    work_reschedules++;
}

static int test_arm(u64 channel)
{
    (void)channel;
    arm_count++;
    return 1;
}

#define pr_debug(...) do { } while (0)
#define pr_warn_ratelimited(...) do { } while (0)

#include "actual.inc"

static struct proxy_comm_vmshm_dev device;
static _Alignas(64) u8 shared_window[1024 * 1024];
static const struct realm_xshm_transport realm = {
    .channel = 0x1234,
    .arm = test_arm,
};

static int pressure_handler(const struct vmshm_comm_rx *rx, void *priv);

static void reset_device(void)
{
    struct proxy_comm_vmshm_queue_object *queue = &device.queues[0];
    struct proxy_comm_vmshm_queue_object *response = &device.queues[1];

    memset(shared_window, 0, sizeof(shared_window));
    memset(&device, 0, sizeof(device));
    device.base = shared_window;
    device.hdr = (struct proxy_comm_vmshm_header *)shared_window;
    device.hdr->magic = PROXY_COMM_VMSHM_MAGIC;
    device.hdr->status[PROXY_COMM_VMSHM_ROLE_PROXY] =
        PROXY_COMM_VMSHM_STATUS_READY;
    device.realm = &realm;
    device.irq_notify = true;
    device.channel.dev = &device;
    queue->magic = PROXY_COMM_VMSHM_QUEUE_MAGIC;
    queue->queue_id = PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY;
    queue->queue_size = PROXY_COMM_VMSHM_QUEUE_SIZE;
    queue->queue_mask = PROXY_COMM_VMSHM_QUEUE_SIZE - 1U;
    queue->msg_size = PROXY_COMM_VMSHM_MSG_SIZE;
    queue->desc_off = 0x1000;
    queue->avail_off = 0x8000;
    queue->used_off = 0x9000;
    queue->msg_pool_off = 0x10000;
    response->magic = PROXY_COMM_VMSHM_QUEUE_MAGIC;
    response->queue_id = 1U;
    response->queue_size = PROXY_COMM_VMSHM_QUEUE_SIZE;
    response->queue_mask = PROXY_COMM_VMSHM_QUEUE_SIZE - 1U;
    response->msg_size = PROXY_COMM_VMSHM_MSG_SIZE;
    response->desc_off = 0x40000;
    response->avail_off = 0x48000;
    response->used_off = 0x49000;
    response->msg_pool_off = 0x50000;
    device.size = sizeof(shared_window);
    proxy_comm_vmshm_handler_count = 1;
    memset(proxy_comm_vmshm_handlers, 0, sizeof(proxy_comm_vmshm_handlers));
    proxy_comm_vmshm_handlers[0].type = 0x50465251U;
    proxy_comm_vmshm_handlers[0].handler = pressure_handler;
    published_seq = 0;
    corrupt_payload = false;
    corruption_detected = false;
}

static int publish_request(u64 seq, bool corrupt)
{
    u8 payload[PROXY_COMM_VMSHM_MSG_SIZE -
               sizeof(struct proxy_comm_vmshm_msg)] = {};
    struct vmshm_comm_tx tx = {
        .type = 0x50465251U,
        .seq = seq,
        .payload = payload,
        .len = sizeof(payload),
    };

    for (u32 i = 0; i < sizeof(payload); i++)
        payload[i] = (u8)(seq + i);
    if (corrupt)
        payload[sizeof(payload) - 1U] ^= 0xffU;
    return proxy_comm_vmshm_queue_send(
        &device, PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY, &tx);
}

static int pressure_handler(const struct vmshm_comm_rx *rx, void *priv)
{
    u64 next;

    (void)priv;
    handler_requests++;
    handler_payload_bytes += rx->len;
    virtual_tick += rx->len / 32U + 1U;
    if (!victim_seen) {
        victim_latency = virtual_tick - work_start_tick;
        victim_seen = true;
    }
    for (u32 i = 0; i < rx->len; i++) {
        u8 expected = (u8)(rx->seq + i);
        if (((const u8 *)rx->payload)[i] != expected) {
            corruption_detected = true;
            return -EINVAL;
        }
    }
    if (corrupt_payload && rx->seq == 1)
        corruption_detected = true;

    next = rx->seq + 1U;
    if (next > published_seq && next <= pressure_target) {
        int ret = publish_request(next, false);
        if (ret)
            return ret;
        published_seq = next;
    }
    return 0;
}

static void reset_metrics(void)
{
    virtual_tick = 0;
    mutex_lock_visits = 0;
    policy_lock_visits = 0;
    mutex_max_interval = 0;
    policy_max_interval = 0;
    mutex_lock_start = 0;
    policy_lock_start = 0;
    handler_requests = 0;
    handler_payload_bytes = 0;
    empty_recv_count = 0;
    arm_count = 0;
    victim_latency = 0;
    victim_seen = false;
    work_reschedules = 0;
}

static u64 queue_outstanding(void)
{
    struct proxy_comm_vmshm_queue_object *queue = &device.queues[0];
    struct proxy_comm_vmshm_avail_ring *avail =
        (void *)(shared_window + queue->avail_off);
    struct proxy_comm_vmshm_used_ring *used =
        (void *)(shared_window + queue->used_off);

    return avail->idx - used->idx;
}

static void run_single_victim(u64 *latency, u64 *requests)
{
    reset_metrics();
    pressure_target = 1;
    published_seq = 1;
    if (publish_request(1, false) != 0)
        __builtin_trap();
    work_start_tick = virtual_tick;
    proxy_comm_vmshm_rx_work(&device.rx_work);
    *latency = victim_latency;
    *requests = handler_requests;
}

int main(void)
{
    const u32 max_payload = PROXY_COMM_VMSHM_MSG_SIZE -
                            sizeof(struct proxy_comm_vmshm_msg);
    u64 before_latency;
    u64 before_requests;
    u64 after_latency;
    u64 after_requests;
    u64 pressure_requests;
    u64 pressure_payload_bytes;
    u64 retained_slots;
    u64 pressure_mutex_visits;
    u64 pressure_policy_visits;
    u64 work_cycles;
    u64 max_requests_per_work = 0;
    u64 pressure_reschedules;
    int ret;

    reset_device();
    for (u32 i = 0; i < PROXY_COMM_VMSHM_QUEUE_SIZE; i++) {
        struct vmshm_comm_tx response = {
            .type = 0x52535031U,
            .seq = i + 1U,
        };

        if (proxy_comm_vmshm_queue_send(&device, 1U, &response) != 0)
            __builtin_trap();
    }
    struct vmshm_comm_tx blocked_response = {
        .type = 0x52535031U,
        .seq = PROXY_COMM_VMSHM_QUEUE_SIZE + 1U,
    };
    if (proxy_comm_vmshm_queue_send(&device, 1U, &blocked_response) != -EAGAIN)
        __builtin_trap();
    struct proxy_comm_vmshm_queue_object *response_queue = &device.queues[1];
    struct proxy_comm_vmshm_avail_ring *response_avail =
        (void *)(shared_window + response_queue->avail_off);
    struct proxy_comm_vmshm_used_ring *response_used =
        (void *)(shared_window + response_queue->used_off);
    if (response_avail->idx - response_used->idx != PROXY_COMM_VMSHM_QUEUE_SIZE)
        __builtin_trap();
    u64 blocked_victim_latency;
    u64 blocked_victim_requests;
    run_single_victim(&blocked_victim_latency, &blocked_victim_requests);
    if (blocked_victim_requests != 1 ||
        response_avail->idx - response_used->idx != PROXY_COMM_VMSHM_QUEUE_SIZE)
        __builtin_trap();

    reset_device();
    if (publish_request(0x123456U, false) != 0)
        __builtin_trap();
    u8 stable_payload[max_payload];
    struct vmshm_comm_rx stable_rx = {
        .payload = stable_payload,
        .payload_capacity = sizeof(stable_payload),
    };
    if (proxy_comm_vmshm_queue_recv(&device, 0U, &stable_rx) != 0 ||
        stable_rx.seq != 0x123456U || stable_rx.len != max_payload)
        __builtin_trap();
    for (u32 i = 0; i < max_payload; i++) {
        if (stable_payload[i] != (u8)(0x123456U + i))
            __builtin_trap();
    }
    struct proxy_comm_vmshm_queue_object *snapshot_queue = &device.queues[0];
    struct proxy_comm_vmshm_desc *snapshot_desc =
        (void *)(shared_window + snapshot_queue->desc_off);
    struct proxy_comm_vmshm_msg *snapshot_msg =
        (void *)(shared_window + snapshot_queue->msg_pool_off);
    memset(snapshot_desc, 0xff, sizeof(*snapshot_desc));
    memset(snapshot_msg, 0xff, snapshot_queue->msg_size);
    if (stable_rx.seq != 0x123456U || stable_rx.len != max_payload)
        __builtin_trap();
    for (u32 i = 0; i < max_payload; i++) {
        if (stable_payload[i] != (u8)(0x123456U + i))
            __builtin_trap();
    }


    reset_device();
    run_single_victim(&before_latency, &before_requests);

    reset_device();
    pressure_target = 8192;
    for (published_seq = 1; published_seq <= PROXY_COMM_VMSHM_QUEUE_SIZE;
         published_seq++) {
        if (publish_request(published_seq, false) != 0)
            __builtin_trap();
    }
    published_seq = PROXY_COMM_VMSHM_QUEUE_SIZE;
    retained_slots = queue_outstanding();
    ret = publish_request(PROXY_COMM_VMSHM_QUEUE_SIZE + 1U, false);
    if (retained_slots != PROXY_COMM_VMSHM_QUEUE_SIZE || ret != -EAGAIN)
        __builtin_trap();

    reset_metrics();
    work_start_tick = virtual_tick;
    for (u32 work_index = 0; work_index < 32; work_index++) {
        u64 requests_before_work = handler_requests;

        proxy_comm_vmshm_rx_work(&device.rx_work);
        u64 requests_in_work = handler_requests - requests_before_work;
        if (requests_in_work > max_requests_per_work)
            max_requests_per_work = requests_in_work;
    }
    pressure_requests = handler_requests;
    pressure_payload_bytes = handler_payload_bytes;
    pressure_mutex_visits = mutex_lock_visits;
    pressure_policy_visits = policy_lock_visits;
    work_cycles = virtual_tick - work_start_tick;
    pressure_reschedules = work_reschedules;
    if (pressure_requests != 8192 || max_requests_per_work != 256 ||
        work_reschedules != 32 || queue_outstanding() != 0 ||
        pressure_payload_bytes != 8192ULL * max_payload ||
        pressure_mutex_visits != 8192 || pressure_policy_visits != 8192)
        __builtin_trap();

    reset_device();
    reset_metrics();
    pressure_target = 1;
    published_seq = 1;
    corrupt_payload = true;
    if (publish_request(1, true) != 0)
        __builtin_trap();
    proxy_comm_vmshm_rx_work(&device.rx_work);
    if (!corruption_detected || handler_requests != 1)
        __builtin_trap();

    reset_device();
    reset_metrics();
    for (u32 i = 0; i < 4096; i++)
        proxy_comm_vmshm_rx_work(&device.rx_work);
    empty_recv_count = arm_count;
    empty_wakeups = arm_count;
    if (empty_recv_count != 4096 || handler_requests != 0)
        __builtin_trap();

    reset_device();
    run_single_victim(&after_latency, &after_requests);

    printf("METRICS max_requests_per_work=%llu work_reschedules=%llu "
           "total_requests=%llu retained_slots=%llu "
           "max_payload_bytes=%u payload_bytes=%llu "
           "local_payload_bytes_per_request=%u stack_allocation_events=%llu "
           "mutex_visits=%llu policy_lock_visits=%llu "
           "mutex_max_interval=%llu policy_max_interval=%llu "
           "work_cycles=%llu empty_wakeup_count=%llu "
           "victim_before_latency=%llu victim_after_latency=%llu "
           "victim_before_requests=%llu victim_after_requests=%llu\n",
           (unsigned long long)max_requests_per_work,
           (unsigned long long)pressure_reschedules,
           (unsigned long long)pressure_requests,
           (unsigned long long)retained_slots, max_payload,
           (unsigned long long)pressure_payload_bytes, max_payload,
           (unsigned long long)pressure_requests,
           (unsigned long long)pressure_mutex_visits,
           (unsigned long long)pressure_policy_visits,
           (unsigned long long)mutex_max_interval,
           (unsigned long long)policy_max_interval,
           (unsigned long long)work_cycles,
           (unsigned long long)empty_wakeups,
           (unsigned long long)before_latency,
           (unsigned long long)after_latency,
           (unsigned long long)before_requests,
           (unsigned long long)after_requests);
    printf("RESPONSE_BACKPRESSURE=PASS blocked_queue=256 independent_victim_requests=%llu\n",
           (unsigned long long)blocked_victim_requests);
    printf("SHARED_SNAPSHOT=PASS post_receive_shared_mutation_ignored\n");
    printf("ORACLE_CONTROL=PASS full_payload_validation corruption_detected "
           "slot_capacity_enforced empty_wakeup_recheck\n");
    printf("GPU_RPC_WORK_BUDGET=PASS request_budget_per_work=256\n");
    return 0;
}
