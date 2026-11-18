/* SPDX-License-Identifier: BSD-3-Clause */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned int u32;
typedef unsigned long long u64;

#define PAGE_SIZE 4096UL
#define PAGE_ALIGN(value) (((value) + PAGE_SIZE - 1UL) & ~(PAGE_SIZE - 1UL))
#define U64_MAX (~0ULL)
#define ENOMEM 12
#define EINVAL 22
#define EACCES 13
#define REALM_GPU_BO_INSPECT 1009UL

struct drm_gem_object;
struct drm_printer;

struct drm_gem_object_funcs {
	void (*print_info)(struct drm_printer *printer, unsigned int indent,
			   const struct drm_gem_object *obj);
};

struct drm_gem_object {
	size_t size;
	u32 refs;
	u32 handle_count;
	const struct drm_gem_object_funcs *funcs;
	void *resv;
};

struct drm_gem_shmem_object {
	struct drm_gem_object base;
};

struct panthor_gem_object {
	struct drm_gem_shmem_object base;
	u32 flags;
	u64 rmm_private_handle;
	u64 rmm_channel;
	struct drm_gem_object *exclusive_vm_root_gem;
};

struct drm_device { int unused; };
struct drm_file { int unused; };
struct panthor_vm { int unused; };

struct realm_gpu_call {
	unsigned long operation;
	u64 handle;
	u64 args[4];
	long status;
	u64 result[4];
};

static struct drm_gem_object_funcs standard_funcs;
static struct drm_gem_object_funcs private_gem_funcs;
static struct drm_gem_object *published;
static unsigned int object_puts;
static unsigned int frees;
static unsigned int diagnostic_prints;
static bool handle_create_fails;
static bool share_fails;
static bool private_create_active;
static struct panthor_gem_object *allocated[16];
static unsigned int allocated_count;

#define to_panthor_bo(gem) ((struct panthor_gem_object *)(gem))
#define IS_ERR(value) ((value) == NULL)
#define PTR_ERR(value) ((long)(uintptr_t)(value))

static long realm_gpu_private_call(struct realm_gpu_call *call)
{
	assert(call != NULL && call->operation == 1009U && call->handle == 0x1234U);
	call->status = 0;
	call->result[0] = PAGE_SIZE;
	return 0;
}

static struct drm_gem_shmem_object *drm_gem_shmem_create(
		struct drm_device *ddev, size_t size)
{
	struct panthor_gem_object *bo;

	assert(ddev != NULL && size == PAGE_SIZE);
	bo = calloc(1, sizeof(*bo));
	assert(bo != NULL);
	assert(allocated_count < 16U);
	allocated[allocated_count++] = bo;
	bo->base.base.size = size;
	bo->base.base.refs = 1U;
	bo->base.base.funcs = &standard_funcs;
	private_create_active = true;
	return &bo->base;
}

static long drm_gem_handle_create(struct drm_file *file,
		struct drm_gem_object *obj, u32 *handle)
{
	assert(file != NULL && obj != NULL && handle != NULL);
	published = obj;
	assert(obj->size == PAGE_SIZE && obj->funcs != NULL);
	if (private_create_active) {
		struct panthor_gem_object *bo = to_panthor_bo(obj);

		if (!(bo->flags == 0x5aU && bo->rmm_channel == 0x1234U &&
			bo->rmm_private_handle == 0x5678U && obj->funcs == &private_gem_funcs))
			fprintf(stderr, "private publication fields flags=%x channel=%llx handle=%llx funcs=%p expected=%p\\n",
				bo->flags, (unsigned long long)bo->rmm_channel,
				(unsigned long long)bo->rmm_private_handle, (void *)obj->funcs,
				(void *)&private_gem_funcs);
		assert(bo->flags == 0x5aU && bo->rmm_channel == 0x1234U &&
			bo->rmm_private_handle == 0x5678U && obj->funcs == &private_gem_funcs);
	}
	if (handle_create_fails)
		return -ENOMEM;
	obj->refs++;
	obj->handle_count++;
	*handle = 77U;
	return 0;
}

static void drm_gem_object_get(struct drm_gem_object *obj)
{
	assert(obj != NULL);
	obj->refs++;
}

static void drm_gem_object_put(struct drm_gem_object *obj)
{
	assert(obj != NULL && obj->refs != 0U);
	object_puts++;
	if (--obj->refs == 0U)
		frees++;
}

static long panthor_gem_share_realm_gpu_pages(struct panthor_gem_object *bo)
{
	assert(bo != NULL && bo->base.base.size == PAGE_SIZE);
	private_create_active = false;
	return share_fails ? -ENOMEM : 0;
}

static struct drm_gem_object *panthor_vm_root_gem(struct panthor_vm *vm)
{
	assert(vm != NULL);
	return NULL;
}

#include "actual.inc"

static void reset(bool fail_handle, bool fail_share)
{
	handle_create_fails = fail_handle;
	share_fails = fail_share;
	published = NULL;
	object_puts = frees = 0U;
}

static void close_handle(struct drm_gem_object *obj)
{
	assert(obj != NULL && obj->handle_count == 1U);
	obj->handle_count--;
	drm_gem_object_put(obj);
}

static void diagnostic_print(struct drm_printer *printer, unsigned int indent,
	const struct drm_gem_object *obj)
{
	(void)printer;
	(void)indent;
	assert(obj != NULL && obj->refs >= 2U);
	diagnostic_prints++;
}

static void test_private_publication(void)
{
	struct drm_file file;
	struct drm_device device;
	u64 size = PAGE_SIZE;
	u32 handle = 0xdeadU;
	struct drm_gem_object *obj;
	long ret;

	reset(true, false);
	ret = panthor_gem_create_private_with_handle(&file, &device, NULL,
		&size, 0x5aU, &handle, 0x1234U, 0x5678U);
	assert(ret == -ENOMEM && handle == 0xdeadU);
	assert(published != NULL && published->refs == 0U && published->handle_count == 0U);
	assert(object_puts == 1U && frees == 1U);

	reset(false, false);
	size = PAGE_SIZE;
	handle = 0U;
	ret = panthor_gem_create_private_with_handle(&file, &device, NULL,
		&size, 0x5aU, &handle, 0x1234U, 0x5678U);
	obj = published;
	assert(ret == 0 && handle == 77U && size == PAGE_SIZE);
	assert(obj != NULL && obj->refs == 1U && obj->handle_count == 1U && frees == 0U);
	close_handle(obj);
	assert(obj->refs == 0U && obj->handle_count == 0U && frees == 1U);

	reset(false, false);
	size = PAGE_SIZE;
	handle = 0U;
	ret = panthor_gem_create_private_with_handle(&file, &device, NULL,
		&size, 0x5aU, &handle, 0x1234U, 0x5678U);
	obj = published;
	assert(ret == 0);
	obj->funcs = &((struct drm_gem_object_funcs){
		.print_info = diagnostic_print,
	});
	obj->refs++;
	obj->funcs->print_info(NULL, 2U, obj);
	assert(diagnostic_prints == 1U && obj->refs == 2U && frees == 0U);
	drm_gem_object_put(obj);
	assert(obj->refs == 1U && frees == 0U && diagnostic_prints == 1U);
	close_handle(obj);
	assert(obj->refs == 0U && frees == 1U);
}

static void test_shared_publication(void)
{
	struct drm_file file;
	struct drm_device device;
	u64 size = PAGE_SIZE;
	u32 handle = 0xdeadU;
	struct drm_gem_object *obj;
	long ret;

	reset(false, true);
	ret = panthor_gem_create_with_handle(&file, &device, NULL, &size, 0x3U, &handle);
	assert(ret == -ENOMEM && handle == 0xdeadU && published == NULL);
	assert(object_puts == 1U && frees == 1U);

	reset(true, false);
	size = PAGE_SIZE;
	handle = 0U;
	ret = panthor_gem_create_with_handle(&file, &device, NULL, &size, 0x3U, &handle);
	obj = published;
	assert(ret == -ENOMEM && obj != NULL && obj->refs == 0U);
	assert(object_puts == 1U && frees == 1U);

	reset(false, false);
	size = PAGE_SIZE;
	handle = 0U;
	ret = panthor_gem_create_with_handle(&file, &device, NULL, &size, 0x3U, &handle);
	obj = published;
	assert(ret == 0 && handle == 77U && obj->refs == 1U && frees == 0U);
	close_handle(obj);
	assert(obj->refs == 0U && frees == 1U);
}

int main(void)
{
	test_private_publication();
	test_shared_publication();
	for (unsigned int i = 0U; i < allocated_count; i++)
		free(allocated[i]);
	puts("GPU_GEM_LIFECYCLE=PASS pre-publication initialization, exact failure cleanup, immediate close, and diagnostic lookup references");
	return 0;
}
