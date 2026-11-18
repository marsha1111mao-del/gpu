#!/usr/bin/env python3
"""Exercise native Panthor worker/timer teardown ordering around unplug."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DEVICE_C = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_device.c"
DEVICE_H = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_device.h"
SCHED_C = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_sched.c"
FW_C = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_fw.c"
DRV_C = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_drv.c"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)


def extract_function(source: str, name: str) -> str:
    match = re.search(
        rf"^(?:static inline |static )?(?:int|void)\s+{re.escape(name)}\s*\([^;{{]*\)\s*\{{",
        source,
        re.MULTILINE,
    )
    assert match, name
    end = source.index("\n}", match.end())
    return source[match.start():end + 2] + "\n"


device_source = DEVICE_C.read_text(encoding="utf-8")
device_header = DEVICE_H.read_text(encoding="utf-8")
driver_source = DRV_C.read_text(encoding="utf-8")
sched_source = SCHED_C.read_text(encoding="utf-8")
fw_source = FW_C.read_text(encoding="utf-8")

device_functions = "\n".join(
    extract_function(device_source, name)
    for name in ("panthor_device_unplug", "panthor_device_reset_cleanup",
                 "panthor_device_reset_work")
)
device_functions += extract_function(device_header, "panthor_device_schedule_reset")
sched_functions = extract_function(sched_source, "panthor_sched_unplug")
fw_functions = extract_function(fw_source, "panthor_fw_unplug")

prelude = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef int atomic_t;
typedef struct { int value; } atomic_t_impl;
struct mutex { int locked; };
struct completion { int done; };
struct drm_device { bool unplugged; struct device *dev; };
struct device { int unused; };
struct work_struct { void (*func)(struct work_struct *); bool pending; };
struct delayed_work { struct work_struct work; bool canceled; };
struct workqueue_struct { bool destroyed; };
struct list_head { struct list_head *next, *prev; };

struct panthor_scheduler {
    struct delayed_work tick_work;
    struct mutex lock;
    struct { bool has_ref; } pm;
};
struct panthor_fw_irq { unsigned int irq; };
struct panthor_kernel_bo { int unused; };
struct panthor_vm { int unused; };
struct panthor_fw_section { struct list_head node; struct panthor_kernel_bo *mem; };
struct panthor_fw {
    struct { struct delayed_work ping_work; } watchdog;
    struct panthor_fw_irq irq;
    struct list_head sections;
    struct panthor_fw_section section;
    struct panthor_vm *vm;
};
enum panthor_gpu_power_domain { L2 };
struct panthor_device {
    struct drm_device base;
    struct device *dev;
    void *rmm_service;
    struct { struct mutex lock; struct completion done; } unplug;
    struct { struct workqueue_struct *wq; struct work_struct work; atomic_t pending; } reset;
    struct { atomic_t state; } pm;
    struct panthor_scheduler *scheduler;
    struct panthor_fw *fw;
    struct { uint64_t l2_present; } gpu_info;
};

#define PANTHOR_DEVICE_PM_STATE_ACTIVE 1
#define container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))
#define list_for_each_entry(pos, head, member) \
    for (pos = container_of((head)->next, typeof(*pos), member); \
         &pos->member != (head); \
         pos = container_of(pos->member.next, typeof(*pos), member))
#define drm_WARN_ON(dev, condition) ({ (void)(dev); condition; })
#define IS_ENABLED(option) 1

static char order[4096];
static size_t order_length;
static unsigned int hardware_reset_entries;
static bool mmu_unplugged;
static bool gpu_unplugged;
static struct panthor_kernel_bo section_bo;
static struct panthor_vm firmware_vm;

static void record(const char *event)
{
    size_t length = strlen(event);
    assert(order_length + length + 2 < sizeof(order));
    if (order_length) order[order_length++] = ',';
    memcpy(order + order_length, event, length);
    order_length += length;
    order[order_length] = '\0';
}

static void mutex_lock(struct mutex *mutex)
{
    assert(mutex && !mutex->locked);
    mutex->locked = 1;
}

static void mutex_unlock(struct mutex *mutex)
{
    assert(mutex && mutex->locked);
    mutex->locked = 0;
}

static bool drm_dev_is_unplugged(struct drm_device *drm)
{
    return drm->unplugged;
}

static void drm_dev_unplug(struct drm_device *drm)
{
    assert(!drm->unplugged);
    drm->unplugged = true;
    record("drm_dev_unplug");
}

static void wait_for_completion(struct completion *completion)
{
    assert(completion->done);
}

static void complete_all(struct completion *completion)
{
    completion->done = 1;
    record("unplug_done");
}

static int atomic_read(const atomic_t *value) { return *value; }
static void atomic_set(atomic_t *value, int new_value) { *value = new_value; }
static int atomic_cmpxchg(atomic_t *value, int expected, int desired)
{
    int old = *value;
    if (old == expected) *value = desired;
    return old;
}

static bool queue_work(struct workqueue_struct *wq, struct work_struct *work)
{
    assert(wq && !wq->destroyed && !work->pending);
    work->pending = true;
    record("queue_reset");
    return true;
}

static bool cancel_delayed_work_sync(struct delayed_work *work)
{
    assert(work && !work->canceled);
    work->canceled = true;
    record("cancel_delayed_work");
    return true;
}

static bool cancel_work_sync(struct work_struct *work)
{
    assert(work);
    if (work->pending) {
        work->pending = false;
        record("reset_cancel_drain");
        work->func(work);
    }
    record("cancel_reset_work");
    return true;
}

static void destroy_workqueue(struct workqueue_struct *wq)
{
    assert(wq && !wq->destroyed);
    wq->destroyed = true;
    record("destroy_reset_wq");
}

static bool drm_dev_enter(struct drm_device *drm, int *cookie)
{
    if (drm->unplugged) return false;
    *cookie = 1;
    return true;
}

static void drm_dev_exit(int cookie) { assert(cookie == 1); }
static void drm_err(struct drm_device *drm, const char *format, ...) { (void)drm; (void)format; }
static int pm_runtime_get_sync(struct device *dev) { (void)dev; return 0; }
static int pm_runtime_put(struct device *dev) { (void)dev; record("sched_pm_put"); return 0; }
static void pm_runtime_dont_use_autosuspend(struct device *dev) { (void)dev; }
static void pm_runtime_put_sync_suspend(struct device *dev) { (void)dev; }
static void panthor_device_suspend(struct device *dev) { (void)dev; }
static void panthor_job_irq_suspend(struct panthor_fw_irq *irq)
{
    assert(irq && irq->irq); record("irq_suspend");
}
static void panthor_fw_stop(struct panthor_device *ptdev) { assert(ptdev); record("fw_stop"); }
static void panthor_kernel_bo_destroy(struct panthor_kernel_bo *bo)
{
    assert(bo == &section_bo); record("fw_section_bo_put");
}
static void panthor_vm_put(struct panthor_vm *vm) { assert(vm == &firmware_vm); record("fw_vm_put"); }
static void panthor_gpu_power_off(struct panthor_device *ptdev,
                                  enum panthor_gpu_power_domain domain,
                                  uint64_t mask, int timeout)
{
    assert(ptdev && domain == L2 && mask && timeout); record("gpu_l2_power_off");
}
static void panthor_mmu_unplug(struct panthor_device *ptdev)
{
    assert(ptdev); mmu_unplugged = true; record("mmu_unplug");
}
static void panthor_gpu_unplug(struct panthor_device *ptdev)
{
    assert(ptdev); gpu_unplugged = true; record("gpu_unplug");
}
static void panthor_sched_pre_reset(struct panthor_device *ptdev) { assert(ptdev); hardware_reset_entries++; }
static void panthor_fw_pre_reset(struct panthor_device *ptdev, bool on_hang) { assert(ptdev && on_hang); hardware_reset_entries++; }
static void panthor_mmu_pre_reset(struct panthor_device *ptdev) { assert(ptdev); hardware_reset_entries++; }
static void panthor_gpu_soft_reset(struct panthor_device *ptdev) { assert(ptdev); hardware_reset_entries++; }
static void panthor_gpu_l2_power_on(struct panthor_device *ptdev) { assert(ptdev); hardware_reset_entries++; }
static void panthor_mmu_post_reset(struct panthor_device *ptdev) { assert(ptdev); hardware_reset_entries++; }
static int panthor_fw_post_reset(struct panthor_device *ptdev)
{
    assert(ptdev); hardware_reset_entries++; return 0;
}
static void panthor_sched_post_reset(struct panthor_device *ptdev, bool failed)
{
    assert(ptdev && !failed); hardware_reset_entries++;
}
'''

tests = r'''
int main(void)
{
    struct workqueue_struct reset_wq = { 0 };
    struct panthor_scheduler scheduler = { 0 };
    struct panthor_fw firmware = { 0 };
    struct panthor_device device = {
        .dev = &(struct device){ 0 },
        .reset = { .wq = &reset_wq },
        .pm = { .state = PANTHOR_DEVICE_PM_STATE_ACTIVE },
        .scheduler = &scheduler,
        .fw = &firmware,
        .gpu_info = { .l2_present = 1 },
    };

    firmware.irq.irq = 42;
    firmware.vm = &firmware_vm;
    firmware.sections.next = &firmware.section.node;
    firmware.sections.prev = &firmware.section.node;
    firmware.section.node.next = &firmware.sections;
    firmware.section.node.prev = &firmware.sections;
    firmware.section.mem = &section_bo;
    scheduler.pm.has_ref = true;

    panthor_device_schedule_reset(&device);
    assert(device.reset.pending == 1 && device.reset.work.pending);
    device.reset.work.func = panthor_device_reset_work;

    device.reset.pending = 0;
    device.reset.work.pending = false;
    panthor_device_unplug(&device);
    assert(device.base.unplugged && device.unplug.done.done);
    assert(firmware.watchdog.ping_work.canceled && firmware.irq.irq == 42);
    assert(mmu_unplugged && gpu_unplugged);

    device.reset.pending = 0;
    panthor_device_schedule_reset(&device);
    assert(device.reset.work.pending);

    panthor_device_reset_cleanup(&device.base, NULL);
    assert(!device.reset.work.pending && reset_wq.destroyed);
    assert(hardware_reset_entries == 0);

    const char *expected =
        "queue_reset,drm_dev_unplug,cancel_delayed_work,sched_pm_put,"
        "cancel_delayed_work,irq_suspend,fw_stop,fw_section_bo_put,fw_vm_put,"
        "gpu_l2_power_off,mmu_unplug,gpu_unplug,unplug_done,queue_reset,"
        "reset_cancel_drain,cancel_reset_work,destroy_reset_wq";
    assert(strcmp(order, expected) == 0);
    puts("GPU_FW_WORKER_TEARDOWN=PASS unplug_before_callbacks callback_work_drained "
         "post_unplug_reset_denied cleanup_after_drain MODEL_ONLY");
    return 0;
}
'''

variants = {
    "candidate": (device_functions, sched_functions, fw_functions),
    "skip-drm-unplug": (
        device_functions.replace("drm_dev_unplug(&ptdev->base);", "((void)0);", 1),
        sched_functions,
        fw_functions,
    ),
    "skip-fw-work-drain": (
        device_functions,
        sched_functions,
        fw_functions.replace(
            "cancel_delayed_work_sync(&ptdev->fw->watchdog.ping_work);", "((void)0);", 1
        ),
    ),
    "skip-reset-work-drain": (
        device_functions.replace("cancel_work_sync(&ptdev->reset.work);", "((void)0);", 1),
        sched_functions,
        fw_functions,
    ),
}
records = []
for name, (device_variant, sched_variant, fw_variant) in variants.items():
    source_path = out / f"{name}.c"
    source_path.write_text(
        prelude + sched_variant + fw_variant + device_variant + tests,
        encoding="utf-8",
    )
    command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
        "-Werror", "-Wno-unused-parameter", "-Wno-unused-function",
        "-g", "-fsanitize=address,undefined",
        "-fno-sanitize-recover=undefined", "-fno-omit-frame-pointer",
        "-fno-pie", "-no-pie", str(source_path), "-o", str(out / name),
    ]
    with (out / f"{name}-build.log").open("w", encoding="utf-8") as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    record = {"name": name, "build_exit_code": built.returncode, "run_exit_code": None}
    assert built.returncode == 0, (name, (out / f"{name}-build.log").read_text(
        encoding="utf-8", errors="replace"
    ))
    with (out / f"{name}.log").open("w", encoding="utf-8") as log:
        executed = subprocess.run([str(out / name)], stdout=log,
                                  stderr=subprocess.STDOUT, check=False)
    text = (out / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    record["run_exit_code"] = executed.returncode
    records.append(record)
    if name == "candidate":
        passed = "GPU_FW_WORKER_TEARDOWN=PASS" in text
    else:
        assert executed.returncode != 0, (name, executed.returncode, text)

assert passed
exit_position = driver_source.index("platform_driver_unregister(&panthor_driver);")
cleanup_position = driver_source.index("destroy_workqueue(panthor_cleanup_wq);", exit_position)
assert exit_position < cleanup_position
release_position = sched_source.index("queue_work(panthor_cleanup_wq, &group->release_work);")
assert release_position >= 0

source_files = [DEVICE_C, DEVICE_H, SCHED_C, FW_C, DRV_C, Path(__file__)]
record = {
    "status": "PASS_FW_WORKER_TEARDOWN_MODEL",
    "candidate_exit_codes": {"build": 0, "run": 0},
    "negative_variants": records[1:],
    "observed_order": "reset queued before unplug; drm_dev_unplug; scheduler tick and PM reference drained; FW watchdog drained; IRQ suspended; FW stopped; FW sections/VM/L2 torn down; MMU/GPU unplugged; post-unplug reset enqueue denied by drm_dev_enter and drained; reset workqueue destroyed last",
    "source_audit": "Module exit unregisters the platform driver before destroying panthor_cleanup_wq; group_release queues to that drainable cleanup workqueue.",
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Actual unmodified Panthor device/scheduler/FW unplug and reset-work functions with modeled Linux workqueue cancellation; native service path only",
    "not_covered": "No real Linux workqueue concurrency, IRQ injection, hotplug bus teardown, Realm exit, physical device revocation, KASAN, fence callback execution, or L3 hardware timing. The RMM-service branch intentionally retains live resources and is not treated as revoke evidence.",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
