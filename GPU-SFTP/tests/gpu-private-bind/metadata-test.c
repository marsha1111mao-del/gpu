// SPDX-License-Identifier: GPL-2.0-only
/* Actual native callbacks; device/page-table and DRM bookkeeping doubles. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>
typedef uint64_t u64;
#define SZ_4K 4096UL
#define IS_ALIGNED(v, a) (!((v) & ((a) - 1)))
#define AS_COMMAND_FLUSH_PT 1
#define CC_ATTR_MEM_ENCRYPT 1
#define PANTHOR_VM_MAP_FLAGS 0x70
#define drm_dbg(...) ((void)0)
#define drm_err(...) ((void)0)
#define drm_WARN_ON(dev, cond) ((void)(dev), !!(cond))
struct panthor_device { int base; };
struct io_pgtable_ops {
    size_t (*unmap_pages)(struct io_pgtable_ops *, u64, size_t, size_t, void *);
};
struct panthor_vma { int base; unsigned int flags; };
struct panthor_gem_object {
    bool private;
    struct { struct { void *import_attach; } base; } base;
};
struct panthor_vm_op_ctx {
    unsigned int flags;
    struct panthor_vma *vma;
    struct { void *sgt, *vm_bo; } map;
};
struct panthor_vm {
    struct panthor_device *ptdev;
    struct io_pgtable_ops *pgtbl_ops;
    struct panthor_vm_op_ctx *op_ctx;
    struct { int id; } as;
    u64 private_context;
    int base;
};
struct drm_gpuva_map {
    struct { u64 addr, range; } va;
    struct { struct panthor_gem_object *obj; u64 offset; } gem;
};
struct drm_gpuva_op { struct drm_gpuva_map map; };
struct drm_panthor_vm_bind_op { unsigned int flags; };
static unsigned int hardware_calls, metadata_maps, metadata_links;
static int hardware_error;
static bool drm_dev_enter(int *d, int *cookie) { *cookie=1; return true; }
static void drm_dev_exit(int cookie) { assert(cookie==1); }
static int mmu_hw_do_operation(struct panthor_vm *vm,u64 va,u64 size,int op)
{ hardware_calls++; return hardware_error; }
static size_t get_pgsize(u64 va,u64 bytes,size_t *count)
{ *count=bytes/SZ_4K;return SZ_4K; }
static size_t unmap(struct io_pgtable_ops *ops,u64 va,size_t size,size_t count,void *gather)
{ hardware_calls++;return size*count; }
static struct panthor_vma *panthor_vm_op_ctx_get_vma(struct panthor_vm_op_ctx *ctx)
{ return ctx->vma; }
static struct panthor_gem_object *to_panthor_bo(struct panthor_gem_object *bo) { return bo; }
static void panthor_vma_init(struct panthor_vma *vma,unsigned int flags) { vma->flags=flags; }
static bool panthor_gem_is_private(struct panthor_gem_object *bo) { return bo->private; }
static int flags_to_prot(unsigned int flags) { return flags; }
static bool cc_platform_has(int cap) { return false; }
static int panthor_vm_map_shmem_pages(struct panthor_vm *vm,struct panthor_gem_object *bo,
                                    u64 va,int prot,u64 offset,u64 bytes)
{ hardware_calls++;return hardware_error; }
static int panthor_vm_map_pages(struct panthor_vm *vm,u64 va,int prot,void *sgt,u64 offset,u64 bytes)
{ hardware_calls++;return hardware_error; }
static void drm_gpuva_map(int *vm,int *vma,struct drm_gpuva_map *map) { metadata_maps++; }
static void panthor_vma_link(struct panthor_vm *vm,struct panthor_vma *vma,void *bo)
{ assert(bo);metadata_links++; }
#include "actual.inc"
int main(void)
{
    struct panthor_device dev={0};
    struct io_pgtable_ops ops={.unmap_pages=unmap};
    struct panthor_vma vma={0};
    struct panthor_gem_object bo={.private=true};
    struct panthor_vm_op_ctx ctx={.vma=&vma,.map.vm_bo=&bo,.flags=0x50};
    struct panthor_vm vm={.ptdev=&dev,.pgtbl_ops=&ops,.op_ctx=&ctx,.private_context=7,.as.id=2};
    struct drm_gpuva_op op={.map={.va={0x2000000,513*SZ_4K},.gem.obj=&bo}};
    struct drm_panthor_vm_bind_op bind={0};
    assert(!panthor_vm_bind_check_metadata(&vm,&bind,8));
    assert(panthor_vm_bind_check_metadata(&vm,&bind,0)==-EACCES);
    assert(!panthor_gpuva_sm_step_map(&op,&vm));
    assert(metadata_maps==1 && metadata_links==1 && !ctx.map.vm_bo && vma.flags==0x50);
    assert(!panthor_vm_unmap_pages(&vm,op.map.va.addr,op.map.va.range));
    assert(!panthor_vm_flush_range(&vm,op.map.va.addr,op.map.va.range));
    assert(panthor_vm_unmap_pages(&vm,op.map.va.addr+1,op.map.va.range)==-EINVAL);
    assert(!hardware_calls);
    ctx.vma=NULL;
    assert(panthor_gpuva_sm_step_map(&op,&vm)==-EINVAL);
    assert(metadata_maps==1 && metadata_links==1);
    ctx.vma=&vma;ctx.map.vm_bo=&bo;vm.private_context=0;
    assert(panthor_gpuva_sm_step_map(&op,&vm)==-EACCES);
    assert(!hardware_calls && ctx.map.vm_bo==&bo);
    assert(!panthor_vm_bind_check_metadata(&vm,&bind,0));
    assert(panthor_vm_bind_check_metadata(&vm,&bind,8)==-EACCES);
    bo.private=false;hardware_error=-EIO;
    assert(panthor_gpuva_sm_step_map(&op,&vm)==-EIO);
    assert(hardware_calls==1 && metadata_maps==1 && ctx.map.vm_bo==&bo);
    hardware_error=0;
    assert(!panthor_gpuva_sm_step_map(&op,&vm));
    assert(hardware_calls==2 && metadata_maps==2 && !ctx.map.vm_bo);
    assert(!panthor_vm_unmap_pages(&vm,op.map.va.addr,op.map.va.range));
    assert(hardware_calls==4);
    puts("GPU_PRIVATE_METADATA=PASS actual native map/unmap/flush callbacks; HW_DRM_DOUBLES_ONLY");
    return 0;
}
