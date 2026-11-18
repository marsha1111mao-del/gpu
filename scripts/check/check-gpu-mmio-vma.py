#!/usr/bin/env python3
"""Exercise actual Guest control/BO and read-only MMIO VMA policy paths."""

from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
REALM_GPU = ROOT / "Linux-Guest-GPU/drivers/char/realm_gpu.c"
PANTHOR_CLIENT = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)


def extract_function(source: str, name: str) -> str:
    match = re.search(rf"^(?:static )?(?:int|void)\s+{re.escape(name)}\s*\([^;{{]*\)\s*\{{", source, re.MULTILINE)
    assert match, name
    end = source.index("\n}", match.end())
    return source[match.start():end + 2] + "\n"


realm_source = REALM_GPU.read_text()
client_source = PANTHOR_CLIENT.read_text()
realm_functions = "\n".join(
    extract_function(realm_source, name)
    for name in ("private_vma_open", "private_vma_close", "realm_gpu_bo_mmap")
)
realm_functions += r'''
static const struct vm_operations_struct private_vm_ops = {
    .open = private_vma_open,
    .close = private_vma_close,
};
'''
flush_function = extract_function(client_source, "panthor_client_mmap_flush_id")

prelude = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef unsigned long vm_flags_t;
#define PAGE_SIZE 4096UL
#define VM_SHARED (1UL << 0)
#define VM_MAYREAD (1UL << 1)
#define VM_MAYWRITE (1UL << 2)
#define VM_MAYEXEC (1UL << 3)
#define VM_WRITE (1UL << 4)
#define VM_EXEC (1UL << 5)
#define VM_DONTCOPY (1UL << 6)
#define VM_DONTEXPAND (1UL << 7)
#define VM_DONTDUMP (1UL << 8)
#define PAGE_SHIFT 12
#define PAGE_ALIGNED(value) (((value) & (PAGE_SIZE - 1UL)) == 0UL)
#define vma_pages(vma) (((vma)->vm_end - (vma)->vm_start) / PAGE_SIZE)
#define DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET 0x1000ULL
#define pr_info(...) ((void)0)

typedef struct { unsigned int value; } refcount_t;
struct page { int unused; };
struct realm_gpu_bo {
    bool control;
    bool resident;
    unsigned long nr_pages;
    struct page **pages;
    refcount_t refs;
};
struct vm_area_struct {
    unsigned long vm_start;
    unsigned long vm_end;
    unsigned long vm_pgoff;
    vm_flags_t vm_flags;
    void *vm_private_data;
    const struct vm_operations_struct *vm_ops;
};
struct vm_operations_struct {
    void (*open)(struct vm_area_struct *);
    void (*close)(struct vm_area_struct *);
};
struct panthor_client_device { struct page *flush_id_page; };

static const struct vm_operations_struct private_vm_ops;

typedef uint64_t u64;
typedef uint32_t u32;
int realm_gpu_bo_mmap(struct realm_gpu_bo *bo, struct vm_area_struct *vma,
                      u64 offset);
static int panthor_client_mmap_flush_id(struct vm_area_struct *vma);

static struct page backing_page;
static struct page *backing_table = &backing_page;
static unsigned int mapped_pages;
static struct page *inserted_page;
static unsigned long inserted_address;
static struct panthor_client_device client_device;
static struct panthor_client_device *panthor_client = &client_device;
static uint32_t flush_value = 0x12345678U;

static void refcount_inc(refcount_t *refs) { refs->value++; }
static void realm_gpu_bo_put(struct realm_gpu_bo *bo) { (void)bo; }
static void vm_flags_clear(struct vm_area_struct *vma, vm_flags_t flags) { vma->vm_flags &= ~flags; }
static void vm_flags_set(struct vm_area_struct *vma, vm_flags_t flags) { vma->vm_flags |= flags; }
static int vm_map_pages_zero(struct vm_area_struct *vma, struct page **pages,
                             unsigned long count)
{
    assert(vma && pages == &backing_table && count == 1UL);
    mapped_pages += count;
    return 0;
}
static int vm_insert_page(struct vm_area_struct *vma, unsigned long address, struct page *page)
{
    assert(vma && page == client_device.flush_id_page);
    inserted_page = page;
    inserted_address = address;
    return 0;
}
static void *page_address(struct page *page)
{
    assert(page == client_device.flush_id_page);
    return &flush_value;
}

static int mprotect_guard(struct vm_area_struct *vma, vm_flags_t requested)
{
    if ((requested & VM_EXEC) && !(vma->vm_flags & VM_MAYEXEC))
        return -EACCES;
    if ((requested & VM_WRITE) && !(vma->vm_flags & VM_MAYWRITE))
        return -EACCES;
    return 0;
}
'''

tests = r'''
int main(void)
{
    struct realm_gpu_bo bo = {
        .nr_pages = 1UL,
        .pages = &backing_table,
        .refs = { .value = 1U },
    };
    struct vm_area_struct vma = {
        .vm_start = 0x10000UL,
        .vm_end = 0x11000UL,
        .vm_pgoff = 0UL,
        .vm_flags = VM_SHARED | VM_MAYREAD | VM_MAYWRITE | VM_MAYEXEC,
    };

    bo.control = true;
    assert(realm_gpu_bo_mmap(&bo, &vma, 0UL) == -EACCES);
    assert(!mapped_pages && vma.vm_flags & VM_MAYEXEC);
    bo.control = false;
    bo.resident = true;
    assert(realm_gpu_bo_mmap(&bo, &vma, 0UL) == -EACCES);
    bo.resident = false;

    vma.vm_flags &= ~VM_SHARED;
    assert(realm_gpu_bo_mmap(&bo, &vma, (u64)vma.vm_pgoff << PAGE_SHIFT) == -EINVAL);
    vma.vm_flags |= VM_SHARED;
    vma.vm_flags |= VM_EXEC;
    assert(realm_gpu_bo_mmap(&bo, &vma, 0UL) == -EINVAL);
    vma.vm_flags &= ~VM_EXEC;
    vma.vm_pgoff = 1UL;
    assert(realm_gpu_bo_mmap(&bo, &vma, (u64)vma.vm_pgoff << PAGE_SHIFT) == -EINVAL);
    vma.vm_pgoff = 0UL;

    assert(realm_gpu_bo_mmap(&bo, &vma, 0UL) == 0);
    assert(mapped_pages == 1UL && bo.refs.value == 2U && vma.vm_private_data == &bo);
    assert(!(vma.vm_flags & VM_MAYEXEC) && vma.vm_flags & VM_DONTEXPAND && vma.vm_flags & VM_DONTDUMP);
    assert(mprotect_guard(&vma, VM_EXEC) == -EACCES);

    client_device.flush_id_page = &backing_page;
    assert(page_address(client_device.flush_id_page) == &flush_value);
    vma = (struct vm_area_struct){
        .vm_start = 0x20000UL,
        .vm_end = 0x21000UL,
        .vm_flags = VM_SHARED | VM_MAYREAD | VM_MAYWRITE | VM_MAYEXEC,
    };
    vma.vm_flags &= ~VM_SHARED;
    assert(panthor_client_mmap_flush_id(&vma) == -EINVAL);
    vma.vm_flags |= VM_SHARED | VM_WRITE;
    assert(panthor_client_mmap_flush_id(&vma) == -EINVAL);
    vma.vm_flags &= ~VM_WRITE;
    vma.vm_end += PAGE_SIZE;
    assert(panthor_client_mmap_flush_id(&vma) == -EINVAL);
    vma.vm_end -= PAGE_SIZE;

    assert(panthor_client_mmap_flush_id(&vma) == 0);
    assert(inserted_page == &backing_page && inserted_address == vma.vm_start);
    assert(!(vma.vm_flags & VM_MAYWRITE));
    assert(vma.vm_flags & VM_DONTCOPY && vma.vm_flags & VM_DONTEXPAND && vma.vm_flags & VM_DONTDUMP);
    assert(mprotect_guard(&vma, VM_WRITE) == -EACCES);
    assert(vma.vm_flags & VM_DONTCOPY);

    puts("GPU_MMIO_VMA=PASS control_mmap_denied private_cow_denied exec_denied "
         "mprotect_maywrite_mayexec_cleared flush_id_dontcopy MODEL_ONLY");
    return 0;
}
'''

variants = {
    "candidate": (realm_functions, flush_function),
    "skip-control-guard": (
        realm_functions.replace("if (bo && (bo->control || bo->resident))", "if (bo && bo->resident)", 1),
        flush_function,
    ),
    "skip-bo-mayexec-clear": (
        realm_functions.replace("vm_flags_clear(vma, VM_MAYEXEC);", "((void)0);", 1),
        flush_function,
    ),
    "skip-flush-maywrite-clear": (
        realm_functions,
        flush_function.replace("vm_flags_clear(vma, VM_MAYWRITE);", "((void)0);", 1),
    ),
    "skip-flush-dontcopy": (
        realm_functions,
        flush_function.replace("VM_DONTCOPY | ", "", 1),
    ),
}
records = []
for name, (realm_variant, flush_variant) in variants.items():
    source_path = out / f"{name}.c"
    source_path.write_text(prelude + realm_variant + flush_variant + tests)
    build_command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
        str(source_path), "-o", str(out / name),
    ]
    with (out / f"{name}-build.log").open("w", encoding="utf-8") as log:
        built = subprocess.run(build_command, stdout=log, stderr=subprocess.STDOUT, check=False)
    records.append({"name": name, "build_exit_code": built.returncode, "run_exit_code": None})
    if built.returncode != 0:
        assert False, (name, (out / f"{name}-build.log").read_text(encoding="utf-8", errors="replace"))
    run_command = [str(out / name)]
    with (out / f"{name}.log").open("w", encoding="utf-8") as log:
        executed = subprocess.run(run_command, stdout=log, stderr=subprocess.STDOUT, check=False)
    text = (out / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    records[-1]["run_exit_code"] = executed.returncode
    if name == "candidate":
        passed = built.returncode == 0 and executed.returncode == 0 and "GPU_MMIO_VMA=PASS" in text
    else:
        assert built.returncode == 0, name
        assert executed.returncode != 0 and "Assertion" in text, (name, executed.returncode, text)

assert passed
source_files = [REALM_GPU, PANTHOR_CLIENT, Path(__file__)]
record = {
    "status": "PASS_MMIO_VMA_MODEL",
    "candidate_exit_codes": {"build": 0, "run": 0},
    "negative_variants": records[1:],
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files
    },
    "scope": "Actual realm_gpu_bo_mmap and panthor_client_mmap_flush_id with host VMA/page doubles; control/resident backing is denied, MAP_PRIVATE and executable BO mappings are rejected, BO VM_MAYEXEC is cleared, read-only flush-id VM_MAYWRITE is cleared and VM_DONTCOPY is set, and Linux mprotect/fork policy is modeled from those VMA flags",
    "not_covered": "No real Linux mmap/mprotect/fork syscall, concurrent VMA split/merge, RTT install, physical MMIO write, SMMU/DMA request, mixed-page alias, or L3 hardware isolation",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
