#!/usr/bin/env python3
"""Execute the native Panthor GPUVA debugfs path and classify address disclosure."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PANTHOR_MMU = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c"
DRM_DEBUGFS = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/drm_debugfs.c"
CLIENT_CONFIG = ROOT / "configs/verified-20261015/client.config"
PROXY_CONFIG = ROOT / "configs/verified-20261015/proxy.config"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)


def extract_function(source: str, name: str) -> str:
    match = re.search(
        rf"^(?:static )?(?:int|void)\s+{re.escape(name)}\s*\([^;{{]*\)\s*\{{",
        source,
        re.MULTILINE,
    )
    assert match, name
    end = source.index("\n}", match.end())
    return source[match.start():end + 2] + "\n"


panthor_source = PANTHOR_MMU.read_text(encoding="utf-8")
drm_source = DRM_DEBUGFS.read_text(encoding="utf-8")
panthor_functions = "\n".join(
    extract_function(panthor_source, name)
    for name in ("show_vm_gpuvas", "show_each_vm")
)
gpuva_function = extract_function(drm_source, "drm_debugfs_gpuva_info")

prelude = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

typedef unsigned long long u64;
struct mutex { int locked; };
struct list_head { struct list_head *next, *prev; };
struct seq_file { char *buffer; size_t length; size_t capacity; void *private; };
struct drm_minor { struct drm_device *dev; };
struct drm_device { int unused; };
struct drm_gem_object { unsigned char backing[16]; };
struct drm_gpuva {
    struct list_head node;
    struct { u64 addr; u64 range; } va;
    struct { struct drm_gem_object *obj; u64 offset; } gem;
};
struct drm_gpuvm {
    const char *name;
    u64 mm_start;
    u64 mm_range;
    struct drm_gpuva kernel_alloc_node;
    struct list_head mappings;
};
struct panthor_vm {
    struct list_head node;
    struct mutex op_lock;
    struct drm_gpuvm base;
};
struct panthor_mmu {
    struct { struct mutex lock; struct list_head list; } vm;
};
struct panthor_device { struct drm_device base; struct panthor_mmu *mmu; };
struct drm_info_list { void *data; };
struct drm_info_node { struct drm_minor *minor; const struct drm_info_list *info_ent; };

#define container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))
#define list_for_each_entry(pos, head, member) \
    for (pos = container_of((head)->next, typeof(*pos), member); \
         &pos->member != (head); \
         pos = container_of(pos->member.next, typeof(*pos), member))
#define drm_gpuvm_for_each_va(pos, gpuvm) \
    list_for_each_entry(pos, &(gpuvm)->mappings, node)
#define mutex_lock(lock) do { assert(!(lock)->locked); (lock)->locked = 1; } while (0)
#define mutex_unlock(lock) do { assert((lock)->locked); (lock)->locked = 0; } while (0)
#define unlikely(value) (__builtin_expect(!!(value), 0))

int drm_debugfs_gpuva_info(struct seq_file *m, struct drm_gpuvm *gpuvm);

static void seq_vappend(struct seq_file *m, const char *format, va_list arguments)
{
    int written = vsnprintf(m->buffer + m->length, m->capacity - m->length,
                            format, arguments);
    assert(written >= 0);
    assert((size_t)written < m->capacity - m->length);
    m->length += (size_t)written;
}

static void seq_printf(struct seq_file *m, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    seq_vappend(m, format, arguments);
    va_end(arguments);
}

static void seq_puts(struct seq_file *m, const char *text)
{
    size_t length = strlen(text);
    assert(length < m->capacity - m->length);
    memcpy(m->buffer + m->length, text, length + 1);
    m->length += length;
}
'''

tests = r'''
static void list_add_tail(struct list_head *entry, struct list_head *head)
{
    entry->prev = head->prev;
    entry->next = head;
    head->prev->next = entry;
    head->prev = entry;
}

int main(void)
{
    struct drm_gem_object objects[2] = {{
        .backing = { 0xde, 0xad, 0xbe, 0xef, 0xca, 0xfe, 0xf0, 0x0d,
                     0xa5, 0xa5, 0x5a, 0x5a, 0x13, 0x37, 0x80, 0x7f },
    }};
    struct drm_gpuva mappings[2] = {{
        .va = { .addr = 0x100000000ULL, .range = 0x10000ULL },
        .gem = { .obj = &objects[0], .offset = 0 },
    }};
    struct panthor_vm virtual_machines[2] = {{
        .base = {
            .name = "client-a",
            .mm_start = 0x100000000ULL,
            .mm_range = 0x100000000ULL,
            .kernel_alloc_node = { .va = { .addr = 0ULL, .range = 0x1000ULL } },
        },
    }};
    struct panthor_mmu mmu = { 0 };
    struct panthor_device device = { .mmu = &mmu };
    struct drm_minor minor = { .dev = &device.base };
    struct drm_info_list info = { .data = show_vm_gpuvas };
    struct drm_info_node node = { .minor = &minor, .info_ent = &info };
    char output[8192] = { 0 };
    struct seq_file sequence = { .buffer = output, .capacity = sizeof(output), .private = &node };
    char pointer_a[32];
    char pointer_b[32];

    objects[1] = objects[0];
    mappings[1] = mappings[0];
    mappings[1].va.addr = 0x200000000ULL;
    mappings[1].gem.obj = &objects[1];
    mappings[1].gem.offset = 0x4000ULL;
    virtual_machines[1] = virtual_machines[0];
    virtual_machines[1].base.name = "client-b";
    virtual_machines[1].base.kernel_alloc_node.va.addr = 0x200000000ULL;

    mmu.vm.list.next = &mmu.vm.list;
    mmu.vm.list.prev = &mmu.vm.list;
    virtual_machines[0].base.mappings.next = &virtual_machines[0].base.mappings;
    virtual_machines[0].base.mappings.prev = &virtual_machines[0].base.mappings;
    virtual_machines[1].base.mappings.next = &virtual_machines[1].base.mappings;
    virtual_machines[1].base.mappings.prev = &virtual_machines[1].base.mappings;
    list_add_tail(&mappings[0].node, &virtual_machines[0].base.mappings);
    list_add_tail(&mappings[1].node, &virtual_machines[1].base.mappings);
    list_add_tail(&virtual_machines[0].node, &mmu.vm.list);
    list_add_tail(&virtual_machines[1].node, &mmu.vm.list);

    assert(show_each_vm(&sequence, NULL) == 0);
    snprintf(pointer_a, sizeof(pointer_a), "%016llx",
             (unsigned long long)(uintptr_t)&objects[0]);
    snprintf(pointer_b, sizeof(pointer_b), "%016llx",
             (unsigned long long)(uintptr_t)&objects[1]);
    bool allowed_metadata = strstr(output, "client-a") && strstr(output, "client-b") &&
                            strstr(output, "0x0000000100000000") &&
                            strstr(output, "0x0000000200000000") &&
                            strstr(output, "0x0000000000004000");
    bool backing_content_disclosed = strstr(output, "deadbeef") ||
                                     strstr(output, "cafe") || strstr(output, "5a5a");
    bool raw_object_pointer_disclosed = strstr(output, pointer_a) && strstr(output, pointer_b);
    assert(allowed_metadata);
    assert(!backing_content_disclosed);

    printf("GPU_DEBUG_DISCLOSURE=%s aggregate_all_vms=1 backing_content_disclosed=0 "
           "raw_object_pointer_disclosed=%d MODEL_ONLY\n",
           raw_object_pointer_disclosed ? "FAIL" : "PASS", raw_object_pointer_disclosed);
    return 0;
}
'''

variants = {
    "candidate": gpuva_function,
    "sanitized-object-pointer": gpuva_function.replace(
        "va->gem.obj ? 1ULL : 0ULL", "0ULL", 1
    ),
}
records = []
for name, function in variants.items():
    source_path = out / f"{name}.c"
    source_path.write_text(
        prelude + panthor_functions + function + tests,
        encoding="utf-8",
    )
    build_command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra",
        "-Werror", "-Wno-unused-parameter", "-g", "-fsanitize=address,undefined",
        "-fno-sanitize-recover=undefined", "-fno-omit-frame-pointer",
        "-fno-pie", "-no-pie", str(source_path), "-o", str(out / name),
    ]
    with (out / f"{name}-build.log").open("w", encoding="utf-8") as log:
        built = subprocess.run(build_command, stdout=log, stderr=subprocess.STDOUT,
                               check=False)
    record = {"name": name, "build_exit_code": built.returncode, "run_exit_code": None}
    assert built.returncode == 0, (name, (out / f"{name}-build.log").read_text(
        encoding="utf-8", errors="replace"
    ))
    with (out / f"{name}.log").open("w", encoding="utf-8") as log:
        executed = subprocess.run([str(out / name)], stdout=log,
                                  stderr=subprocess.STDOUT, check=False)
    text = (out / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    record["run_exit_code"] = executed.returncode
    record["raw_object_pointer_disclosed"] = "raw_object_pointer_disclosed=1" in text
    record["oracle"] = "FAIL" if record["raw_object_pointer_disclosed"] else "PASS"
    records.append(record)
    assert executed.returncode == 0, (name, executed.returncode, text)

assert records[1]["oracle"] == "PASS"
candidate = records[0]
security_gap = candidate["oracle"] == "FAIL"

for config in (CLIENT_CONFIG, PROXY_CONFIG):
    text = config.read_text(encoding="utf-8")
    assert re.search(r"^CONFIG_DEBUG_FS=y$", text, re.MULTILINE), config
    assert re.search(r"^CONFIG_DEBUG_FS_ALLOW_ALL=y$", text, re.MULTILINE), config

assert "list_for_each_entry(vm, &ptdev->mmu->vm.list, node)" in panthor_functions
assert "va->gem.obj ? 1ULL : 0ULL" in gpuva_function

source_files = [PANTHOR_MMU, DRM_DEBUGFS, CLIENT_CONFIG, PROXY_CONFIG, Path(__file__)]
record = {
    "status": "FAIL_DEBUG_RAW_OBJECT_POINTER_DISCLOSURE" if security_gap else "PASS_DEBUG_DISCLOSURE_MODEL",
    "candidate": candidate,
    "sanitized_control": records[1],
    "debugfs_enabled": {"client": True, "proxy": True},
    "security_gap": (
        "The enabled native Panthor GPUVA debugfs callback aggregates every VM and prints each mapping's raw drm_gem_object pointer. The threat model permits only necessary service metadata; a colluding Host/Proxy reader therefore receives another Client's raw object address even though backing bytes are not printed."
        if security_gap else None
    ),
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Actual unmodified show_each_vm/show_vm_gpuvas/drm_debugfs_gpuva_info with a controlled seq_file and two synthetic Client VMs; candidate and pointer-sanitized control both execute. Frozen Client/Proxy configs enable unrestricted debugfs.",
    "not_covered": "No real debugfs mount permission check, performance counter, trace, coredump, FW debug/readback command, physical timing side channel, or L3 hardware execution; the finding is conditional on a Host/Proxy reader authorized to open debugfs.",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
raise SystemExit(1 if security_gap else 0)
