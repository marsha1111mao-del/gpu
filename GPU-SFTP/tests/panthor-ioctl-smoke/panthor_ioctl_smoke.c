// SPDX-License-Identifier: MIT
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm.h>
#include "panthor_drm.h"

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))

#ifndef DRM_IOCTL_SYNCOBJ_EVENTFD
struct drm_syncobj_eventfd {
	uint32_t handle;
	uint32_t flags;
	uint64_t point;
	int32_t fd;
	uint32_t pad;
};
#define DRM_IOCTL_SYNCOBJ_EVENTFD DRM_IOWR(0xCF, struct drm_syncobj_eventfd)
#endif

enum smoke_mode {
	SMOKE_BASIC,
	SMOKE_VM_CREATE,
	SMOKE_BO_CREATE,
	SMOKE_BO_LIFECYCLE,
	SMOKE_BO_MMAP,
	SMOKE_VM_BIND,
	SMOKE_VM_BIND_ASYNC_SYNC,
	SMOKE_VM_STATE_FLUSH,
	SMOKE_SYNCOBJ_LIFECYCLE,
	SMOKE_SYNCOBJ_WAIT,
	SMOKE_SYNCOBJ_TRANSFER,
	SMOKE_SYNCOBJ_TIMELINE_WAIT,
	SMOKE_SYNCOBJ_SIGNAL_QUERY,
	SMOKE_GROUP_LIFECYCLE,
	SMOKE_GROUP_SUBMIT_SYNCPOINT,
	SMOKE_TILER_HEAP_LIFECYCLE,
};

static void usage(const char *prog)
{
	fprintf(stderr,
		"usage: %s [--basic|--vm-create|--bo-create|--bo-lifecycle|--bo-mmap|--vm-bind|--vm-bind-async-sync|--vm-state-flush|--syncobj-lifecycle|--syncobj-wait|--syncobj-transfer|--syncobj-timeline-wait|--syncobj-signal-query|--group-lifecycle|--group-submit-syncpoint|--tiler-heap-lifecycle] [drm-node]\n",
		prog);
}

static int64_t abs_timeout_after_ns(int64_t delta_ns)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts))
		return delta_ns;

	return (int64_t)ts.tv_sec * 1000000000LL + ts.tv_nsec + delta_ns;
}

static int get_version(int fd)
{
	char name[64] = { 0 };
	char date[64] = { 0 };
	char desc[128] = { 0 };
	struct drm_version version = {
		.name_len = sizeof(name),
		.name = name,
		.date_len = sizeof(date),
		.date = date,
		.desc_len = sizeof(desc),
		.desc = desc,
	};

	if (ioctl(fd, DRM_IOCTL_VERSION, &version) < 0) {
		perror("DRM_IOCTL_VERSION");
		return -1;
	}

	printf("VERSION name=%s major=%d minor=%d patch=%d date=%s desc=%s\n",
	       name, version.version_major, version.version_minor,
	       version.version_patchlevel, date, desc);

	if (strcmp(name, "panthor")) {
		fprintf(stderr, "unexpected DRM driver name: %s\n", name);
		return -1;
	}

	return 0;
}

static int get_cap(int fd, uint64_t cap, const char *name, uint64_t want)
{
	struct drm_get_cap get = {
		.capability = cap,
	};

	if (ioctl(fd, DRM_IOCTL_GET_CAP, &get) < 0) {
		fprintf(stderr, "DRM_IOCTL_GET_CAP %s failed: %s\n",
			name, strerror(errno));
		return -1;
	}

	printf("GET_CAP %s=%llu\n", name,
	       (unsigned long long)get.value);

	if (get.value != want) {
		fprintf(stderr, "unexpected %s value: got %llu want %llu\n",
			name, (unsigned long long)get.value,
			(unsigned long long)want);
		return -1;
	}

	return 0;
}

static int expect_unsupported_ioctl(int fd, unsigned long request, void *arg,
				    const char *label)
{
	int saved_errno;

	if (ioctl(fd, request, arg) == 0) {
		fprintf(stderr, "%s unexpectedly succeeded\n", label);
		return -1;
	}

	saved_errno = errno;
	printf("%s expected_failure errno=%d (%s)\n",
	       label, saved_errno, strerror(saved_errno));

	if (saved_errno != EOPNOTSUPP && saved_errno != ENOTTY &&
	    saved_errno != EINVAL && saved_errno != EBADF) {
		fprintf(stderr, "%s failed with unexpected errno=%d (%s)\n",
			label, saved_errno, strerror(saved_errno));
		return -1;
	}

	return 0;
}

static int unsupported_fd_ioctl_checks(int fd)
{
	struct drm_prime_handle prime = { 0 };
	struct drm_syncobj_handle sync_handle = { 0 };
	struct drm_syncobj_eventfd eventfd = { 0 };

	if (get_cap(fd, DRM_CAP_PRIME, "DRM_CAP_PRIME", 0))
		return -1;

	if (expect_unsupported_ioctl(fd, DRM_IOCTL_PRIME_HANDLE_TO_FD,
				     &prime, "PRIME_HANDLE_TO_FD_UNSUPPORTED"))
		return -1;
	if (expect_unsupported_ioctl(fd, DRM_IOCTL_PRIME_FD_TO_HANDLE,
				     &prime, "PRIME_FD_TO_HANDLE_UNSUPPORTED"))
		return -1;
	if (expect_unsupported_ioctl(fd, DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD,
				     &sync_handle,
				     "SYNCOBJ_HANDLE_TO_FD_UNSUPPORTED"))
		return -1;
	if (expect_unsupported_ioctl(fd, DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE,
				     &sync_handle,
				     "SYNCOBJ_FD_TO_HANDLE_UNSUPPORTED"))
		return -1;
	if (expect_unsupported_ioctl(fd, DRM_IOCTL_SYNCOBJ_EVENTFD,
				     &eventfd, "SYNCOBJ_EVENTFD_UNSUPPORTED"))
		return -1;

	return 0;
}

static int query_size(int fd, uint32_t type, uint32_t *size)
{
	struct drm_panthor_dev_query query = {
		.type = type,
	};

	if (ioctl(fd, DRM_IOCTL_PANTHOR_DEV_QUERY, &query) < 0) {
		fprintf(stderr, "DEV_QUERY size type=%u failed: %s\n",
			type, strerror(errno));
		return -1;
	}

	printf("DEV_QUERY_SIZE type=%u size=%u\n", type, query.size);
	*size = query.size;
	return 0;
}

static int query_gpu_info_out(int fd, struct drm_panthor_gpu_info *out)
{
	struct drm_panthor_gpu_info gpu = { 0 };
	uint32_t size = 0;
	struct drm_panthor_dev_query query;

	if (query_size(fd, DRM_PANTHOR_DEV_QUERY_GPU_INFO, &size))
		return -1;
	if (size > sizeof(gpu)) {
		fprintf(stderr, "GPU_INFO too large: %u > %zu\n",
			size, sizeof(gpu));
		return -1;
	}

	memset(&query, 0, sizeof(query));
	query.type = DRM_PANTHOR_DEV_QUERY_GPU_INFO;
	query.size = size;
	query.pointer = (uint64_t)(uintptr_t)&gpu;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_DEV_QUERY, &query) < 0) {
		fprintf(stderr, "DEV_QUERY GPU_INFO failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("GPU_INFO size=%u gpu_id=0x%08x gpu_rev=0x%08x csf_id=0x%08x shader_present=0x%llx l2_present=0x%llx tiler_present=0x%llx as_present=0x%x\n",
	       query.size, gpu.gpu_id, gpu.gpu_rev, gpu.csf_id,
	       (unsigned long long)gpu.shader_present,
	       (unsigned long long)gpu.l2_present,
	       (unsigned long long)gpu.tiler_present, gpu.as_present);

	if (!gpu.gpu_id || !gpu.shader_present || !gpu.l2_present ||
	    !gpu.tiler_present || !gpu.as_present) {
		fprintf(stderr, "GPU_INFO has empty required capability masks\n");
		return -1;
	}

	if (out)
		*out = gpu;

	return 0;
}

static int query_gpu_info(int fd)
{
	return query_gpu_info_out(fd, NULL);
}

static int query_csif_info_out(int fd, struct drm_panthor_csif_info *out)
{
	struct drm_panthor_csif_info csif = { 0 };
	uint32_t size = 0;
	struct drm_panthor_dev_query query;

	if (query_size(fd, DRM_PANTHOR_DEV_QUERY_CSIF_INFO, &size))
		return -1;
	if (size > sizeof(csif)) {
		fprintf(stderr, "CSIF_INFO too large: %u > %zu\n",
			size, sizeof(csif));
		return -1;
	}

	memset(&query, 0, sizeof(query));
	query.type = DRM_PANTHOR_DEV_QUERY_CSIF_INFO;
	query.size = size;
	query.pointer = (uint64_t)(uintptr_t)&csif;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_DEV_QUERY, &query) < 0) {
		fprintf(stderr, "DEV_QUERY CSIF_INFO failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("CSIF_INFO size=%u csg_slots=%u cs_slots=%u cs_regs=%u scoreboard_slots=%u unpreserved_cs_regs=%u\n",
	       query.size, csif.csg_slot_count, csif.cs_slot_count,
	       csif.cs_reg_count, csif.scoreboard_slot_count,
	       csif.unpreserved_cs_reg_count);

	if (!csif.csg_slot_count || !csif.cs_slot_count || !csif.cs_reg_count) {
		fprintf(stderr, "CSIF_INFO has empty required slot/register counts\n");
		return -1;
	}

	if (out)
		*out = csif;

	return 0;
}

static int query_csif_info(int fd)
{
	return query_csif_info_out(fd, NULL);
}

static int basic_checks(int fd)
{
	if (get_version(fd) ||
	    get_cap(fd, DRM_CAP_SYNCOBJ, "DRM_CAP_SYNCOBJ", 1) ||
	    get_cap(fd, DRM_CAP_SYNCOBJ_TIMELINE,
		    "DRM_CAP_SYNCOBJ_TIMELINE", 1) ||
	    unsupported_fd_ioctl_checks(fd) ||
	    query_gpu_info(fd) ||
	    query_csif_info(fd))
		return -1;

	printf("PANTHOR_BASIC_SMOKE=PASS\n");
	return 0;
}

static int vm_create_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE failed: %s\n", strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);

	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		return -1;
	}

	destroy.id = vm.id;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		return -1;
	}

	printf("VM_DESTROY id=%u\n", vm.id);
	printf("PANTHOR_VM_CREATE_SMOKE=PASS\n");
	return 0;
}

static int bo_create_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_bo_create bo = {
		.size = 4096,
	};
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_gem_close gem_close = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for BO smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);

	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bo) < 0) {
		fprintf(stderr, "BO_CREATE failed: %s\n", strerror(errno));
		goto out_destroy_vm;
	}

	printf("BO_CREATE handle=%u size=0x%llx\n",
	       bo.handle, (unsigned long long)bo.size);

	if (!bo.handle || bo.size < 4096) {
		fprintf(stderr, "BO_CREATE returned invalid handle/size\n");
		goto out_close_bo;
	}

	ret = 0;

out_close_bo:
	if (bo.handle) {
		gem_close.handle = bo.handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) < 0) {
			fprintf(stderr, "GEM_CLOSE handle=%u failed: %s\n",
				bo.handle, strerror(errno));
			ret = -1;
		} else {
			printf("GEM_CLOSE handle=%u\n", bo.handle);
		}
	}

out_destroy_vm:
	destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_BO_CREATE_SMOKE=PASS\n");
	return ret;
}

static int expect_gem_close_failure(int fd, uint32_t handle, const char *label)
{
	struct drm_gem_close gem_close = {
		.handle = handle,
	};
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) == 0) {
		fprintf(stderr, "%s handle=%u unexpectedly succeeded\n",
			label, handle);
		return -1;
	}

	saved_errno = errno;
	printf("%s handle=%u expected_failure errno=%d (%s)\n",
	       label, handle, saved_errno, strerror(saved_errno));
	return 0;
}

static int bo_lifecycle_check(int fd)
{
	static const struct {
		uint64_t size;
		uint32_t flags;
		int exclusive;
		int close_explicitly;
	} cases[] = {
		{ 4096, 0, 0, 1 },
		{ 8192, DRM_PANTHOR_BO_NO_MMAP, 0, 0 },
		{ 12288, 0, 1, 1 },
		{ 16384, DRM_PANTHOR_BO_NO_MMAP, 1, 0 },
	};
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_panthor_bo_create bos[ARRAY_SIZE(cases)] = { 0 };
	struct drm_gem_close gem_close = { 0 };
	size_t i, j;
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for BO lifecycle smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);

	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	for (i = 0; i < ARRAY_SIZE(cases); i++) {
		bos[i].size = cases[i].size;
		bos[i].flags = cases[i].flags;
		if (cases[i].exclusive)
			bos[i].exclusive_vm_id = vm.id;

		if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bos[i]) < 0) {
			fprintf(stderr, "BO_CREATE[%zu] failed: %s\n",
				i, strerror(errno));
			goto out_close_explicit;
		}

		printf("BO_CREATE[%zu] handle=%u size=0x%llx flags=0x%x exclusive_vm_id=%u\n",
		       i, bos[i].handle, (unsigned long long)bos[i].size,
		       bos[i].flags, bos[i].exclusive_vm_id);

		if (!bos[i].handle || bos[i].size < cases[i].size) {
			fprintf(stderr, "BO_CREATE[%zu] returned invalid handle/size\n",
				i);
			goto out_close_explicit;
		}

		for (j = 0; j < i; j++) {
			if (bos[j].handle == bos[i].handle) {
				fprintf(stderr,
					"BO_CREATE[%zu] reused live handle %u\n",
					i, bos[i].handle);
				goto out_close_explicit;
			}
		}
	}

	for (i = 0; i < ARRAY_SIZE(cases); i++) {
		if (!cases[i].close_explicitly || !bos[i].handle)
			continue;

		gem_close.handle = bos[i].handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) < 0) {
			fprintf(stderr, "GEM_CLOSE[%zu] handle=%u failed: %s\n",
				i, bos[i].handle, strerror(errno));
			goto out_close_explicit;
		}

		printf("GEM_CLOSE[%zu] handle=%u\n", i, bos[i].handle);
	}

	if (expect_gem_close_failure(fd, bos[0].handle, "GEM_CLOSE_DOUBLE") ||
	    expect_gem_close_failure(fd, 0x7ffffffeu, "GEM_CLOSE_INVALID"))
		goto out_close_explicit;

	ret = 0;

out_close_explicit:
	for (i = 0; i < ARRAY_SIZE(cases); i++) {
		if (!bos[i].handle || !cases[i].close_explicitly)
			continue;
		bos[i].handle = 0;
	}

out_destroy_vm:
	destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_BO_LIFECYCLE_SMOKE=PASS\n");
	return ret;
}

static int bo_mmap_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_bo_create bo = {
		.size = 8192,
	};
	struct drm_panthor_bo_create no_mmap_bo = {
		.size = 4096,
		.flags = DRM_PANTHOR_BO_NO_MMAP,
	};
	struct drm_panthor_bo_mmap_offset mmap_offset = { 0 };
	struct drm_panthor_bo_mmap_offset no_mmap_offset = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_gem_close gem_close = { 0 };
	volatile uint32_t *words = MAP_FAILED;
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for BO mmap smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);

	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bo) < 0) {
		fprintf(stderr, "BO_CREATE mmap-able failed: %s\n",
			strerror(errno));
		goto out_destroy_vm;
	}

	printf("BO_CREATE_MMAP handle=%u size=0x%llx\n",
	       bo.handle, (unsigned long long)bo.size);

	mmap_offset.handle = bo.handle;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET, &mmap_offset) < 0) {
		fprintf(stderr, "BO_MMAP_OFFSET handle=%u failed: %s\n",
			bo.handle, strerror(errno));
		goto out_close_bo;
	}

	printf("BO_MMAP_OFFSET handle=%u offset=0x%llx\n",
	       bo.handle, (unsigned long long)mmap_offset.offset);

	words = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		     (off_t)mmap_offset.offset);
	if (words == MAP_FAILED) {
		fprintf(stderr, "mmap BO handle=%u failed: %s\n",
			bo.handle, strerror(errno));
		goto out_close_bo;
	}

	words[0] = 0x13579bdfu;
	words[1] = 0x2468ace0u;
	if (words[0] != 0x13579bdfu || words[1] != 0x2468ace0u) {
		fprintf(stderr, "mmap BO readback mismatch: 0x%08x 0x%08x\n",
			words[0], words[1]);
		goto out_unmap;
	}

	printf("BO_MMAP_RW handle=%u word0=0x%08x word1=0x%08x\n",
	       bo.handle, words[0], words[1]);

	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &no_mmap_bo) < 0) {
		fprintf(stderr, "BO_CREATE NO_MMAP failed: %s\n",
			strerror(errno));
		goto out_unmap;
	}

	printf("BO_CREATE_NO_MMAP handle=%u size=0x%llx\n",
	       no_mmap_bo.handle, (unsigned long long)no_mmap_bo.size);

	no_mmap_offset.handle = no_mmap_bo.handle;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET,
		  &no_mmap_offset) == 0) {
		fprintf(stderr,
			"BO_MMAP_OFFSET unexpectedly succeeded for NO_MMAP handle=%u offset=0x%llx\n",
			no_mmap_bo.handle,
			(unsigned long long)no_mmap_offset.offset);
		goto out_close_no_mmap_bo;
	}

	printf("BO_MMAP_OFFSET_NO_MMAP handle=%u expected_failure errno=%d (%s)\n",
	       no_mmap_bo.handle, errno, strerror(errno));
	ret = 0;

out_close_no_mmap_bo:
	if (no_mmap_bo.handle) {
		gem_close.handle = no_mmap_bo.handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) < 0) {
			fprintf(stderr,
				"GEM_CLOSE NO_MMAP handle=%u failed: %s\n",
				no_mmap_bo.handle, strerror(errno));
			ret = -1;
		} else {
			printf("GEM_CLOSE_NO_MMAP handle=%u\n",
			       no_mmap_bo.handle);
		}
	}

out_unmap:
	if (words != MAP_FAILED) {
		if (munmap((void *)words, 4096) < 0) {
			fprintf(stderr, "munmap failed: %s\n", strerror(errno));
			ret = -1;
		} else {
			printf("BO_MUNMAP handle=%u\n", bo.handle);
		}
	}

out_close_bo:
	if (bo.handle) {
		gem_close.handle = bo.handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) < 0) {
			fprintf(stderr, "GEM_CLOSE handle=%u failed: %s\n",
				bo.handle, strerror(errno));
			ret = -1;
		} else {
			printf("GEM_CLOSE handle=%u\n", bo.handle);
		}
	}

out_destroy_vm:
	destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_BO_MMAP_SMOKE=PASS\n");
	return ret;
}

static int vm_bind_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_bo_create bo = {
		.size = 4096,
	};
	struct drm_panthor_vm_bind_op map_op = {
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_MAP,
		.bo_offset = 0,
		.va = 0x100000,
		.size = 4096,
	};
	struct drm_panthor_vm_bind_op unmap_op = {
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,
		.va = 0x100000,
		.size = 4096,
	};
	struct drm_panthor_vm_bind bind = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_gem_close gem_close = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for VM_BIND smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);

	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bo) < 0) {
		fprintf(stderr, "BO_CREATE for VM_BIND smoke failed: %s\n",
			strerror(errno));
		goto out_destroy_vm;
	}

	printf("BO_CREATE_BIND handle=%u size=0x%llx\n",
	       bo.handle, (unsigned long long)bo.size);

	if (!bo.handle || bo.size < 4096) {
		fprintf(stderr, "BO_CREATE returned invalid handle/size\n");
		goto out_close_bo;
	}

	map_op.bo_handle = bo.handle;
	bind.vm_id = vm.id;
	bind.ops.stride = sizeof(map_op);
	bind.ops.count = 1;
	bind.ops.array = (uint64_t)(uintptr_t)&map_op;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) < 0) {
		fprintf(stderr, "VM_BIND MAP failed: %s failed_op=%u\n",
			strerror(errno), bind.ops.count);
		goto out_close_bo;
	}

	printf("VM_BIND_MAP vm=%u bo=%u va=0x%llx size=0x%llx\n",
	       vm.id, bo.handle, (unsigned long long)map_op.va,
	       (unsigned long long)map_op.size);

	memset(&bind, 0, sizeof(bind));
	bind.vm_id = vm.id;
	bind.ops.stride = sizeof(unmap_op);
	bind.ops.count = 1;
	bind.ops.array = (uint64_t)(uintptr_t)&unmap_op;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) < 0) {
		fprintf(stderr, "VM_BIND UNMAP failed: %s failed_op=%u\n",
			strerror(errno), bind.ops.count);
		goto out_close_bo;
	}

	printf("VM_BIND_UNMAP vm=%u va=0x%llx size=0x%llx\n",
	       vm.id, (unsigned long long)unmap_op.va,
	       (unsigned long long)unmap_op.size);
	ret = 0;

out_close_bo:
	if (bo.handle) {
		gem_close.handle = bo.handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) < 0) {
			fprintf(stderr, "GEM_CLOSE handle=%u failed: %s\n",
				bo.handle, strerror(errno));
			ret = -1;
		} else {
			printf("GEM_CLOSE handle=%u\n", bo.handle);
		}
	}

out_destroy_vm:
	destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_VM_BIND_SMOKE=PASS\n");
	return ret;
}

static int wait_syncobj_signaled(int fd, uint32_t handle, const char *label)
{
	struct drm_syncobj_wait wait = {
		.handles = (uint64_t)(uintptr_t)&handle,
		.timeout_nsec = abs_timeout_after_ns(1000000000LL),
		.count_handles = 1,
		.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT,
	};

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "%s handle=%u failed: %s\n",
			label, handle, strerror(errno));
		return -1;
	}

	printf("%s handle=%u first=%u\n", label, handle, wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "%s first=%u want 0\n", label, wait.first_signaled);
		return -1;
	}

	return 0;
}

static int vm_bind_async_sync_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_panthor_bo_create bo = {
		.size = 4096,
	};
	struct drm_gem_close gem_close = { 0 };
	struct drm_syncobj_create sync_map = { 0 };
	struct drm_syncobj_create sync_only = { 0 };
	struct drm_syncobj_create sync_unmap = { 0 };
	struct drm_syncobj_destroy sync_destroy = { 0 };
	struct drm_panthor_sync_op map_signal = {
		.flags = DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ |
			 DRM_PANTHOR_SYNC_OP_SIGNAL,
	};
	struct drm_panthor_sync_op sync_only_signal = {
		.flags = DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ |
			 DRM_PANTHOR_SYNC_OP_SIGNAL,
	};
	struct drm_panthor_sync_op unmap_signal = {
		.flags = DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ |
			 DRM_PANTHOR_SYNC_OP_SIGNAL,
	};
	struct drm_panthor_vm_bind_op map_op = {
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_MAP,
		.bo_offset = 0,
		.va = 0x200000,
		.size = 4096,
	};
	struct drm_panthor_vm_bind_op sync_only_op = {
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_SYNC_ONLY,
	};
	struct drm_panthor_vm_bind_op unmap_op = {
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,
		.va = 0x200000,
		.size = 4096,
	};
	struct drm_panthor_vm_bind bind = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for async VM_BIND smoke failed: %s\n",
			strerror(errno));
		return -1;
	}
	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);
	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bo) < 0) {
		fprintf(stderr, "BO_CREATE for async VM_BIND smoke failed: %s\n",
			strerror(errno));
		goto out_destroy_vm;
	}
	printf("BO_CREATE_ASYNC_BIND handle=%u size=0x%llx\n",
	       bo.handle, (unsigned long long)bo.size);
	if (!bo.handle || bo.size < 4096) {
		fprintf(stderr, "BO_CREATE returned invalid handle/size\n");
		goto out_close_bo;
	}

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_map) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_VM_BIND_MAP failed: %s\n",
			strerror(errno));
		goto out_close_bo;
	}
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_only) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_VM_BIND_SYNC_ONLY failed: %s\n",
			strerror(errno));
		goto out_destroy_sync_map;
	}
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_unmap) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_VM_BIND_UNMAP failed: %s\n",
			strerror(errno));
		goto out_destroy_sync_only;
	}
	printf("SYNCOBJ_CREATE_VM_BIND map=%u sync_only=%u unmap=%u\n",
	       sync_map.handle, sync_only.handle, sync_unmap.handle);

	map_signal.handle = sync_map.handle;
	map_op.bo_handle = bo.handle;
	map_op.syncs.stride = sizeof(map_signal);
	map_op.syncs.count = 1;
	map_op.syncs.array = (uint64_t)(uintptr_t)&map_signal;
	bind.vm_id = vm.id;
	bind.flags = DRM_PANTHOR_VM_BIND_ASYNC;
	bind.ops.stride = sizeof(map_op);
	bind.ops.count = 1;
	bind.ops.array = (uint64_t)(uintptr_t)&map_op;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) < 0) {
		fprintf(stderr, "VM_BIND_ASYNC_MAP failed: %s failed_op=%u\n",
			strerror(errno), bind.ops.count);
		goto out_destroy_sync_unmap;
	}
	printf("VM_BIND_ASYNC_MAP vm=%u bo=%u sync=%u va=0x%llx size=0x%llx\n",
	       vm.id, bo.handle, sync_map.handle,
	       (unsigned long long)map_op.va, (unsigned long long)map_op.size);
	if (wait_syncobj_signaled(fd, sync_map.handle,
				  "SYNCOBJ_WAIT_AFTER_VM_BIND_MAP"))
		goto out_destroy_sync_unmap;

	sync_only_signal.handle = sync_only.handle;
	sync_only_op.syncs.stride = sizeof(sync_only_signal);
	sync_only_op.syncs.count = 1;
	sync_only_op.syncs.array = (uint64_t)(uintptr_t)&sync_only_signal;
	memset(&bind, 0, sizeof(bind));
	bind.vm_id = vm.id;
	bind.flags = DRM_PANTHOR_VM_BIND_ASYNC;
	bind.ops.stride = sizeof(sync_only_op);
	bind.ops.count = 1;
	bind.ops.array = (uint64_t)(uintptr_t)&sync_only_op;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) < 0) {
		fprintf(stderr, "VM_BIND_ASYNC_SYNC_ONLY failed: %s failed_op=%u\n",
			strerror(errno), bind.ops.count);
		goto out_destroy_sync_unmap;
	}
	printf("VM_BIND_ASYNC_SYNC_ONLY vm=%u sync=%u\n",
	       vm.id, sync_only.handle);
	if (wait_syncobj_signaled(fd, sync_only.handle,
				  "SYNCOBJ_WAIT_AFTER_VM_BIND_SYNC_ONLY"))
		goto out_destroy_sync_unmap;

	unmap_signal.handle = sync_unmap.handle;
	unmap_op.syncs.stride = sizeof(unmap_signal);
	unmap_op.syncs.count = 1;
	unmap_op.syncs.array = (uint64_t)(uintptr_t)&unmap_signal;
	memset(&bind, 0, sizeof(bind));
	bind.vm_id = vm.id;
	bind.flags = DRM_PANTHOR_VM_BIND_ASYNC;
	bind.ops.stride = sizeof(unmap_op);
	bind.ops.count = 1;
	bind.ops.array = (uint64_t)(uintptr_t)&unmap_op;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) < 0) {
		fprintf(stderr, "VM_BIND_ASYNC_UNMAP failed: %s failed_op=%u\n",
			strerror(errno), bind.ops.count);
		goto out_destroy_sync_unmap;
	}
	printf("VM_BIND_ASYNC_UNMAP vm=%u sync=%u va=0x%llx size=0x%llx\n",
	       vm.id, sync_unmap.handle, (unsigned long long)unmap_op.va,
	       (unsigned long long)unmap_op.size);
	if (wait_syncobj_signaled(fd, sync_unmap.handle,
				  "SYNCOBJ_WAIT_AFTER_VM_BIND_UNMAP"))
		goto out_destroy_sync_unmap;

	ret = 0;

out_destroy_sync_unmap:
	if (sync_unmap.handle) {
		sync_destroy.handle = sync_unmap.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &sync_destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_VM_BIND_UNMAP handle=%u failed: %s\n",
				sync_unmap.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_VM_BIND_UNMAP handle=%u\n",
			       sync_unmap.handle);
		}
	}
out_destroy_sync_only:
	if (sync_only.handle) {
		sync_destroy.handle = sync_only.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &sync_destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_VM_BIND_SYNC_ONLY handle=%u failed: %s\n",
				sync_only.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_VM_BIND_SYNC_ONLY handle=%u\n",
			       sync_only.handle);
		}
	}
out_destroy_sync_map:
	if (sync_map.handle) {
		sync_destroy.handle = sync_map.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &sync_destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_VM_BIND_MAP handle=%u failed: %s\n",
				sync_map.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_VM_BIND_MAP handle=%u\n",
			       sync_map.handle);
		}
	}
out_close_bo:
	if (bo.handle) {
		gem_close.handle = bo.handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &gem_close) < 0) {
			fprintf(stderr, "GEM_CLOSE handle=%u failed: %s\n",
				bo.handle, strerror(errno));
			ret = -1;
		} else {
			printf("GEM_CLOSE handle=%u\n", bo.handle);
		}
	}
out_destroy_vm:
	destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE=PASS\n");
	return ret;
}

static int vm_state_flush_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_get_state state = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	volatile uint32_t *flush_id = MAP_FAILED;
	uint32_t value;
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for VM state/flush smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);

	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	state.vm_id = vm.id;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_GET_STATE, &state) < 0) {
		fprintf(stderr, "VM_GET_STATE vm=%u failed: %s\n",
			vm.id, strerror(errno));
		goto out_destroy_vm;
	}

	printf("VM_GET_STATE vm=%u state=%u\n", vm.id, state.state);
	if (state.state != DRM_PANTHOR_VM_STATE_USABLE) {
		fprintf(stderr, "VM_GET_STATE vm=%u unexpected state=%u\n",
			vm.id, state.state);
		goto out_destroy_vm;
	}

	flush_id = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd,
			(off_t)DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET);
	if (flush_id == MAP_FAILED) {
		fprintf(stderr, "mmap FLUSH_ID failed: %s\n", strerror(errno));
		goto out_destroy_vm;
	}

	value = flush_id[0];
	printf("MMAP_FLUSH_ID offset=0x%llx value=0x%08x\n",
	       (unsigned long long)DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET,
	       value);
	ret = 0;

	if (munmap((void *)flush_id, 4096) < 0) {
		fprintf(stderr, "munmap FLUSH_ID failed: %s\n", strerror(errno));
		ret = -1;
	} else {
		printf("MUNMAP_FLUSH_ID\n");
	}
	flush_id = MAP_FAILED;

out_destroy_vm:
	destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (flush_id != MAP_FAILED)
		munmap((void *)flush_id, 4096);

	if (!ret)
		printf("PANTHOR_VM_STATE_FLUSH_SMOKE=PASS\n");
	return ret;
}

static int expect_syncobj_destroy_failure(int fd, uint32_t handle,
					  const char *label)
{
	struct drm_syncobj_destroy destroy = {
		.handle = handle,
	};
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) == 0) {
		fprintf(stderr, "%s handle=%u unexpectedly succeeded\n",
			label, handle);
		return -1;
	}

	saved_errno = errno;
	printf("%s handle=%u expected_failure errno=%d (%s)\n",
	       label, handle, saved_errno, strerror(saved_errno));
	return 0;
}

static int syncobj_lifecycle_check(int fd)
{
	struct drm_syncobj_create sync_a = { 0 };
	struct drm_syncobj_create sync_b = {
		.flags = DRM_SYNCOBJ_CREATE_SIGNALED,
	};
	struct drm_syncobj_destroy destroy = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_a) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE[0] failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("SYNCOBJ_CREATE[0] handle=%u flags=0x%x\n",
	       sync_a.handle, sync_a.flags);
	if (!sync_a.handle) {
		fprintf(stderr, "SYNCOBJ_CREATE[0] returned invalid handle\n");
		goto out_destroy_a;
	}

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_b) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE[1] failed: %s\n",
			strerror(errno));
		goto out_destroy_a;
	}

	printf("SYNCOBJ_CREATE[1] handle=%u flags=0x%x\n",
	       sync_b.handle, sync_b.flags);
	if (!sync_b.handle || sync_b.handle == sync_a.handle) {
		fprintf(stderr, "SYNCOBJ_CREATE[1] returned invalid/reused handle\n");
		goto out_destroy_b;
	}

	destroy.handle = sync_a.handle;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
		fprintf(stderr, "SYNCOBJ_DESTROY[0] handle=%u failed: %s\n",
			sync_a.handle, strerror(errno));
		goto out_destroy_b;
	}

	printf("SYNCOBJ_DESTROY[0] handle=%u\n", sync_a.handle);
	if (expect_syncobj_destroy_failure(fd, sync_a.handle,
					   "SYNCOBJ_DESTROY_DOUBLE"))
		goto out_destroy_b;
	sync_a.handle = 0;

	ret = 0;

out_destroy_b:
	if (sync_b.handle) {
		destroy.handle = sync_b.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY[1] handle=%u failed: %s\n",
				sync_b.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY[1] handle=%u\n",
			       sync_b.handle);
		}
	}

out_destroy_a:
	if (sync_a.handle) {
		destroy.handle = sync_a.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY leftover handle=%u failed: %s\n",
				sync_a.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_LEFTOVER handle=%u\n",
			       sync_a.handle);
		}
	}

	if (!ret)
		printf("PANTHOR_SYNCOBJ_LIFECYCLE_SMOKE=PASS\n");
	return ret;
}

static int expect_syncobj_wait_failure(int fd, uint32_t *handles,
				       uint32_t count, uint32_t flags,
				       int64_t timeout_nsec,
				       const char *label)
{
	struct drm_syncobj_wait wait = {
		.handles = (uint64_t)(uintptr_t)handles,
		.timeout_nsec = timeout_nsec,
		.count_handles = count,
		.flags = flags,
	};
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) == 0) {
		fprintf(stderr, "%s unexpectedly succeeded first=%u\n",
			label, wait.first_signaled);
		return -1;
	}

	saved_errno = errno;
	printf("%s expected_failure errno=%d (%s)\n",
	       label, saved_errno, strerror(saved_errno));
	return 0;
}

static int syncobj_wait_check(int fd)
{
	struct drm_syncobj_create sync_a = {
		.flags = DRM_SYNCOBJ_CREATE_SIGNALED,
	};
	struct drm_syncobj_create sync_b = {
		.flags = DRM_SYNCOBJ_CREATE_SIGNALED,
	};
	struct drm_syncobj_create sync_unsignaled = { 0 };
	struct drm_syncobj_destroy destroy = { 0 };
	uint32_t handles[2] = { 0 };
	uint32_t invalid_handle = 0x7ffffff0U;
	struct drm_syncobj_wait wait = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_a) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_WAIT[0] failed: %s\n",
			strerror(errno));
		return -1;
	}
	printf("SYNCOBJ_CREATE_WAIT[0] handle=%u flags=0x%x\n",
	       sync_a.handle, sync_a.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_b) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_WAIT[1] failed: %s\n",
			strerror(errno));
		goto out_destroy_a;
	}
	printf("SYNCOBJ_CREATE_WAIT[1] handle=%u flags=0x%x\n",
	       sync_b.handle, sync_b.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync_unsignaled) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_WAIT_UNSIGNALED failed: %s\n",
			strerror(errno));
		goto out_destroy_b;
	}
	printf("SYNCOBJ_CREATE_WAIT_UNSIGNALED handle=%u flags=0x%x\n",
	       sync_unsignaled.handle, sync_unsignaled.flags);

	handles[0] = sync_a.handle;
	memset(&wait, 0, sizeof(wait));
	wait.handles = (uint64_t)(uintptr_t)handles;
	wait.timeout_nsec = 0;
	wait.count_handles = 1;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_WAIT[0] failed: %s\n",
			strerror(errno));
		goto out_destroy_unsignaled;
	}
	printf("SYNCOBJ_WAIT[0] count=1 flags=0x%x first=%u\n",
	       wait.flags, wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "SYNCOBJ_WAIT[0] first=%u want 0\n",
			wait.first_signaled);
		goto out_destroy_unsignaled;
	}

	handles[0] = sync_a.handle;
	handles[1] = sync_b.handle;
	memset(&wait, 0, sizeof(wait));
	wait.handles = (uint64_t)(uintptr_t)handles;
	wait.timeout_nsec = 0;
	wait.count_handles = 2;
	wait.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_ALL failed: %s\n",
			strerror(errno));
		goto out_destroy_unsignaled;
	}
	printf("SYNCOBJ_WAIT_ALL count=2 flags=0x%x first=%u\n",
	       wait.flags, wait.first_signaled);

	handles[0] = sync_unsignaled.handle;
	if (expect_syncobj_wait_failure(fd, handles, 1, 0, 0,
					"SYNCOBJ_WAIT_UNSIGNALED_POLL"))
		goto out_destroy_unsignaled;

	if (expect_syncobj_wait_failure(fd, &invalid_handle, 1, 0, 0,
					"SYNCOBJ_WAIT_INVALID"))
		goto out_destroy_unsignaled;

	ret = 0;

out_destroy_unsignaled:
	if (sync_unsignaled.handle) {
		destroy.handle = sync_unsignaled.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_WAIT_UNSIGNALED handle=%u failed: %s\n",
				sync_unsignaled.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_WAIT_UNSIGNALED handle=%u\n",
			       sync_unsignaled.handle);
		}
	}

out_destroy_b:
	if (sync_b.handle) {
		destroy.handle = sync_b.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_WAIT[1] handle=%u failed: %s\n",
				sync_b.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_WAIT[1] handle=%u\n",
			       sync_b.handle);
		}
	}

out_destroy_a:
	if (sync_a.handle) {
		destroy.handle = sync_a.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_WAIT[0] handle=%u failed: %s\n",
				sync_a.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_WAIT[0] handle=%u\n",
			       sync_a.handle);
		}
	}

	if (!ret)
		printf("PANTHOR_SYNCOBJ_WAIT_SMOKE=PASS\n");
	return ret;
}

static int expect_syncobj_transfer_failure(int fd,
					   struct drm_syncobj_transfer *transfer,
					   const char *label)
{
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TRANSFER, transfer) == 0) {
		fprintf(stderr, "%s unexpectedly succeeded\n", label);
		return -1;
	}

	saved_errno = errno;
	printf("%s expected_failure errno=%d (%s)\n",
	       label, saved_errno, strerror(saved_errno));
	return 0;
}

static int syncobj_transfer_check(int fd)
{
	struct drm_syncobj_create src = {
		.flags = DRM_SYNCOBJ_CREATE_SIGNALED,
	};
	struct drm_syncobj_create dst = { 0 };
	struct drm_syncobj_destroy destroy = { 0 };
	struct drm_syncobj_transfer transfer = { 0 };
	struct drm_syncobj_wait wait = { 0 };
	uint32_t wait_handle = 0;
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &src) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TRANSFER_SRC failed: %s\n",
			strerror(errno));
		return -1;
	}
	printf("SYNCOBJ_CREATE_TRANSFER_SRC handle=%u flags=0x%x\n",
	       src.handle, src.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &dst) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TRANSFER_DST failed: %s\n",
			strerror(errno));
		goto out_destroy_src;
	}
	printf("SYNCOBJ_CREATE_TRANSFER_DST handle=%u flags=0x%x\n",
	       dst.handle, dst.flags);

	transfer.src_handle = src.handle;
	transfer.dst_handle = dst.handle;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TRANSFER, &transfer) < 0) {
		fprintf(stderr, "SYNCOBJ_TRANSFER_BINARY failed: %s\n",
			strerror(errno));
		goto out_destroy_dst;
	}
	printf("SYNCOBJ_TRANSFER_BINARY src=%u dst=%u src_point=%llu dst_point=%llu flags=0x%x\n",
	       src.handle, dst.handle,
	       (unsigned long long)transfer.src_point,
	       (unsigned long long)transfer.dst_point, transfer.flags);

	wait_handle = dst.handle;
	wait.handles = (uint64_t)(uintptr_t)&wait_handle;
	wait.timeout_nsec = 0;
	wait.count_handles = 1;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_TRANSFER_DST failed: %s\n",
			strerror(errno));
		goto out_destroy_dst;
	}
	printf("SYNCOBJ_WAIT_TRANSFER_DST handle=%u first=%u\n",
	       dst.handle, wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_TRANSFER_DST first=%u want 0\n",
			wait.first_signaled);
		goto out_destroy_dst;
	}

	transfer.src_handle = 0x7ffffff0U;
	transfer.dst_handle = dst.handle;
	transfer.src_point = 0;
	transfer.dst_point = 0;
	transfer.flags = 0;
	if (expect_syncobj_transfer_failure(fd, &transfer,
					    "SYNCOBJ_TRANSFER_INVALID_SRC"))
		goto out_destroy_dst;

	ret = 0;

out_destroy_dst:
	if (dst.handle) {
		destroy.handle = dst.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TRANSFER_DST handle=%u failed: %s\n",
				dst.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TRANSFER_DST handle=%u\n",
			       dst.handle);
		}
	}

out_destroy_src:
	if (src.handle) {
		destroy.handle = src.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TRANSFER_SRC handle=%u failed: %s\n",
				src.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TRANSFER_SRC handle=%u\n",
			       src.handle);
		}
	}

	if (!ret)
		printf("PANTHOR_SYNCOBJ_TRANSFER_SMOKE=PASS\n");
	return ret;
}

static int expect_syncobj_timeline_wait_failure(int fd, uint32_t *handles,
						uint64_t *points,
						uint32_t count, uint32_t flags,
						int64_t timeout_nsec,
						const char *label)
{
	struct drm_syncobj_timeline_wait wait = {
		.handles = (uint64_t)(uintptr_t)handles,
		.points = (uint64_t)(uintptr_t)points,
		.timeout_nsec = timeout_nsec,
		.count_handles = count,
		.flags = flags,
	};
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &wait) == 0) {
		fprintf(stderr, "%s unexpectedly succeeded first=%u\n",
			label, wait.first_signaled);
		return -1;
	}

	saved_errno = errno;
	printf("%s expected_failure errno=%d (%s)\n",
	       label, saved_errno, strerror(saved_errno));
	return 0;
}

static int syncobj_timeline_wait_check(int fd)
{
	struct drm_syncobj_create src_a = {
		.flags = DRM_SYNCOBJ_CREATE_SIGNALED,
	};
	struct drm_syncobj_create src_b = {
		.flags = DRM_SYNCOBJ_CREATE_SIGNALED,
	};
	struct drm_syncobj_create timeline_a = { 0 };
	struct drm_syncobj_create timeline_b = { 0 };
	struct drm_syncobj_create empty = { 0 };
	struct drm_syncobj_destroy destroy = { 0 };
	struct drm_syncobj_transfer transfer = { 0 };
	struct drm_syncobj_timeline_wait wait = { 0 };
	uint32_t handles[2] = { 0 };
	uint32_t invalid_handle = 0x7ffffff0U;
	uint64_t points[2] = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &src_a) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TIMELINE_SRC[0] failed: %s\n",
			strerror(errno));
		return -1;
	}
	printf("SYNCOBJ_CREATE_TIMELINE_SRC[0] handle=%u flags=0x%x\n",
	       src_a.handle, src_a.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &src_b) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TIMELINE_SRC[1] failed: %s\n",
			strerror(errno));
		goto out_destroy_src_a;
	}
	printf("SYNCOBJ_CREATE_TIMELINE_SRC[1] handle=%u flags=0x%x\n",
	       src_b.handle, src_b.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &timeline_a) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TIMELINE_DST[0] failed: %s\n",
			strerror(errno));
		goto out_destroy_src_b;
	}
	printf("SYNCOBJ_CREATE_TIMELINE_DST[0] handle=%u flags=0x%x\n",
	       timeline_a.handle, timeline_a.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &timeline_b) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TIMELINE_DST[1] failed: %s\n",
			strerror(errno));
		goto out_destroy_timeline_a;
	}
	printf("SYNCOBJ_CREATE_TIMELINE_DST[1] handle=%u flags=0x%x\n",
	       timeline_b.handle, timeline_b.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &empty) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_TIMELINE_EMPTY failed: %s\n",
			strerror(errno));
		goto out_destroy_timeline_b;
	}
	printf("SYNCOBJ_CREATE_TIMELINE_EMPTY handle=%u flags=0x%x\n",
	       empty.handle, empty.flags);

	transfer.src_handle = src_a.handle;
	transfer.dst_handle = timeline_a.handle;
	transfer.src_point = 0;
	transfer.dst_point = 7;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TRANSFER, &transfer) < 0) {
		fprintf(stderr, "SYNCOBJ_TRANSFER_TIMELINE[0] failed: %s\n",
			strerror(errno));
		goto out_destroy_empty;
	}
	printf("SYNCOBJ_TRANSFER_TIMELINE[0] src=%u dst=%u src_point=%llu dst_point=%llu flags=0x%x\n",
	       src_a.handle, timeline_a.handle,
	       (unsigned long long)transfer.src_point,
	       (unsigned long long)transfer.dst_point, transfer.flags);

	memset(&transfer, 0, sizeof(transfer));
	transfer.src_handle = src_b.handle;
	transfer.dst_handle = timeline_b.handle;
	transfer.src_point = 0;
	transfer.dst_point = 11;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TRANSFER, &transfer) < 0) {
		fprintf(stderr, "SYNCOBJ_TRANSFER_TIMELINE[1] failed: %s\n",
			strerror(errno));
		goto out_destroy_empty;
	}
	printf("SYNCOBJ_TRANSFER_TIMELINE[1] src=%u dst=%u src_point=%llu dst_point=%llu flags=0x%x\n",
	       src_b.handle, timeline_b.handle,
	       (unsigned long long)transfer.src_point,
	       (unsigned long long)transfer.dst_point, transfer.flags);

	handles[0] = timeline_a.handle;
	points[0] = 7;
	memset(&wait, 0, sizeof(wait));
	wait.handles = (uint64_t)(uintptr_t)handles;
	wait.points = (uint64_t)(uintptr_t)points;
	wait.timeout_nsec = 0;
	wait.count_handles = 1;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_WAIT[0] failed: %s\n",
			strerror(errno));
		goto out_destroy_empty;
	}
	printf("SYNCOBJ_TIMELINE_WAIT[0] handle=%u point=%llu flags=0x%x first=%u\n",
	       timeline_a.handle, (unsigned long long)points[0],
	       wait.flags, wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_WAIT[0] first=%u want 0\n",
			wait.first_signaled);
		goto out_destroy_empty;
	}

	memset(&wait, 0, sizeof(wait));
	wait.handles = (uint64_t)(uintptr_t)handles;
	wait.points = (uint64_t)(uintptr_t)points;
	wait.timeout_nsec = 0;
	wait.count_handles = 1;
	wait.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_AVAILABLE;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_WAIT_AVAILABLE[0] failed: %s\n",
			strerror(errno));
		goto out_destroy_empty;
	}
	printf("SYNCOBJ_TIMELINE_WAIT_AVAILABLE[0] handle=%u point=%llu first=%u\n",
	       timeline_a.handle, (unsigned long long)points[0],
	       wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_WAIT_AVAILABLE[0] first=%u want 0\n",
			wait.first_signaled);
		goto out_destroy_empty;
	}

	handles[0] = timeline_a.handle;
	handles[1] = timeline_b.handle;
	points[0] = 7;
	points[1] = 11;
	memset(&wait, 0, sizeof(wait));
	wait.handles = (uint64_t)(uintptr_t)handles;
	wait.points = (uint64_t)(uintptr_t)points;
	wait.timeout_nsec = 0;
	wait.count_handles = 2;
	wait.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_WAIT_ALL failed: %s\n",
			strerror(errno));
		goto out_destroy_empty;
	}
	printf("SYNCOBJ_TIMELINE_WAIT_ALL count=2 flags=0x%x first=%u\n",
	       wait.flags, wait.first_signaled);

	handles[0] = empty.handle;
	points[0] = 5;
	if (expect_syncobj_timeline_wait_failure(
		    fd, handles, points, 1,
		    DRM_SYNCOBJ_WAIT_FLAGS_WAIT_AVAILABLE, 0,
		    "SYNCOBJ_TIMELINE_WAIT_AVAILABLE_EMPTY"))
		goto out_destroy_empty;

	handles[0] = timeline_a.handle;
	points[0] = 99;
	if (expect_syncobj_timeline_wait_failure(
		    fd, handles, points, 1, 0, 0,
		    "SYNCOBJ_TIMELINE_WAIT_MISSING_POINT"))
		goto out_destroy_empty;

	points[0] = 7;
	if (expect_syncobj_timeline_wait_failure(
		    fd, &invalid_handle, points, 1, 0, 0,
		    "SYNCOBJ_TIMELINE_WAIT_INVALID"))
		goto out_destroy_empty;

	ret = 0;

out_destroy_empty:
	if (empty.handle) {
		destroy.handle = empty.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TIMELINE_EMPTY handle=%u failed: %s\n",
				empty.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TIMELINE_EMPTY handle=%u\n",
			       empty.handle);
		}
	}

out_destroy_timeline_b:
	if (timeline_b.handle) {
		destroy.handle = timeline_b.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TIMELINE_DST[1] handle=%u failed: %s\n",
				timeline_b.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TIMELINE_DST[1] handle=%u\n",
			       timeline_b.handle);
		}
	}

out_destroy_timeline_a:
	if (timeline_a.handle) {
		destroy.handle = timeline_a.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TIMELINE_DST[0] handle=%u failed: %s\n",
				timeline_a.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TIMELINE_DST[0] handle=%u\n",
			       timeline_a.handle);
		}
	}

out_destroy_src_b:
	if (src_b.handle) {
		destroy.handle = src_b.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TIMELINE_SRC[1] handle=%u failed: %s\n",
				src_b.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TIMELINE_SRC[1] handle=%u\n",
			       src_b.handle);
		}
	}

out_destroy_src_a:
	if (src_a.handle) {
		destroy.handle = src_a.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_TIMELINE_SRC[0] handle=%u failed: %s\n",
				src_a.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_TIMELINE_SRC[0] handle=%u\n",
			       src_a.handle);
		}
	}

	if (!ret)
		printf("PANTHOR_SYNCOBJ_TIMELINE_WAIT_SMOKE=PASS\n");
	return ret;
}

static int expect_syncobj_array_failure(int fd, unsigned long request,
					uint32_t *handles, uint32_t count,
					const char *label)
{
	struct drm_syncobj_array array = {
		.handles = (uint64_t)(uintptr_t)handles,
		.count_handles = count,
	};
	int saved_errno;

	if (ioctl(fd, request, &array) == 0) {
		fprintf(stderr, "%s unexpectedly succeeded\n", label);
		return -1;
	}

	saved_errno = errno;
	printf("%s expected_failure errno=%d (%s)\n",
	       label, saved_errno, strerror(saved_errno));
	return 0;
}

static int expect_syncobj_timeline_array_failure(int fd, unsigned long request,
						 uint32_t *handles,
						 uint64_t *points,
						 uint32_t count,
						 uint32_t flags,
						 const char *label)
{
	struct drm_syncobj_timeline_array array = {
		.handles = (uint64_t)(uintptr_t)handles,
		.points = (uint64_t)(uintptr_t)points,
		.count_handles = count,
		.flags = flags,
	};
	int saved_errno;

	if (ioctl(fd, request, &array) == 0) {
		fprintf(stderr, "%s unexpectedly succeeded\n", label);
		return -1;
	}

	saved_errno = errno;
	printf("%s expected_failure errno=%d (%s)\n",
	       label, saved_errno, strerror(saved_errno));
	return 0;
}

static int syncobj_signal_query_check(int fd)
{
	struct drm_syncobj_create binary = { 0 };
	struct drm_syncobj_create timeline_a = { 0 };
	struct drm_syncobj_create timeline_b = { 0 };
	struct drm_syncobj_destroy destroy = { 0 };
	struct drm_syncobj_array array = { 0 };
	struct drm_syncobj_wait wait = { 0 };
	struct drm_syncobj_timeline_wait timeline_wait = { 0 };
	struct drm_syncobj_timeline_array timeline_array = { 0 };
	uint32_t handles[2] = { 0 };
	uint32_t invalid_handle = 0x7ffffff0U;
	uint64_t points[2] = { 0 };
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &binary) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_SIGNAL_BINARY failed: %s\n",
			strerror(errno));
		return -1;
	}
	printf("SYNCOBJ_CREATE_SIGNAL_BINARY handle=%u flags=0x%x\n",
	       binary.handle, binary.flags);

	handles[0] = binary.handle;
	array.handles = (uint64_t)(uintptr_t)handles;
	array.count_handles = 1;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_SIGNAL, &array) < 0) {
		fprintf(stderr, "SYNCOBJ_SIGNAL_BINARY failed: %s\n",
			strerror(errno));
		goto out_destroy_binary;
	}
	printf("SYNCOBJ_SIGNAL_BINARY handle=%u\n", binary.handle);

	wait.handles = (uint64_t)(uintptr_t)handles;
	wait.timeout_nsec = 0;
	wait.count_handles = 1;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_AFTER_SIGNAL failed: %s\n",
			strerror(errno));
		goto out_destroy_binary;
	}
	printf("SYNCOBJ_WAIT_AFTER_SIGNAL handle=%u first=%u\n",
	       binary.handle, wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_AFTER_SIGNAL first=%u want 0\n",
			wait.first_signaled);
		goto out_destroy_binary;
	}

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_RESET, &array) < 0) {
		fprintf(stderr, "SYNCOBJ_RESET_BINARY failed: %s\n",
			strerror(errno));
		goto out_destroy_binary;
	}
	printf("SYNCOBJ_RESET_BINARY handle=%u\n", binary.handle);

	if (expect_syncobj_wait_failure(fd, handles, 1, 0, 0,
					"SYNCOBJ_WAIT_AFTER_RESET"))
		goto out_destroy_binary;

	if (expect_syncobj_array_failure(fd, DRM_IOCTL_SYNCOBJ_SIGNAL,
					 &invalid_handle, 1,
					 "SYNCOBJ_SIGNAL_INVALID"))
		goto out_destroy_binary;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &timeline_a) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_SIGNAL_TIMELINE[0] failed: %s\n",
			strerror(errno));
		goto out_destroy_binary;
	}
	printf("SYNCOBJ_CREATE_SIGNAL_TIMELINE[0] handle=%u flags=0x%x\n",
	       timeline_a.handle, timeline_a.flags);

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &timeline_b) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_SIGNAL_TIMELINE[1] failed: %s\n",
			strerror(errno));
		goto out_destroy_timeline_a;
	}
	printf("SYNCOBJ_CREATE_SIGNAL_TIMELINE[1] handle=%u flags=0x%x\n",
	       timeline_b.handle, timeline_b.flags);

	handles[0] = timeline_a.handle;
	handles[1] = timeline_b.handle;
	points[0] = 5;
	points[1] = 9;
	timeline_array.handles = (uint64_t)(uintptr_t)handles;
	timeline_array.points = (uint64_t)(uintptr_t)points;
	timeline_array.count_handles = 2;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_SIGNAL, &timeline_array) < 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_SIGNAL failed: %s\n",
			strerror(errno));
		goto out_destroy_timeline_b;
	}
	printf("SYNCOBJ_TIMELINE_SIGNAL count=2 point0=%llu point1=%llu\n",
	       (unsigned long long)points[0], (unsigned long long)points[1]);

	memset(&timeline_wait, 0, sizeof(timeline_wait));
	timeline_wait.handles = (uint64_t)(uintptr_t)handles;
	timeline_wait.points = (uint64_t)(uintptr_t)points;
	timeline_wait.timeout_nsec = 0;
	timeline_wait.count_handles = 2;
	timeline_wait.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &timeline_wait) < 0) {
		fprintf(stderr, "SYNCOBJ_TIMELINE_WAIT_AFTER_SIGNAL failed: %s\n",
			strerror(errno));
		goto out_destroy_timeline_b;
	}
	printf("SYNCOBJ_TIMELINE_WAIT_AFTER_SIGNAL count=2 first=%u\n",
	       timeline_wait.first_signaled);

	points[0] = 0;
	points[1] = 0;
	timeline_array.points = (uint64_t)(uintptr_t)points;
	timeline_array.flags = 0;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_QUERY, &timeline_array) < 0) {
		fprintf(stderr, "SYNCOBJ_QUERY failed: %s\n", strerror(errno));
		goto out_destroy_timeline_b;
	}
	printf("SYNCOBJ_QUERY count=2 point0=%llu point1=%llu\n",
	       (unsigned long long)points[0],
	       (unsigned long long)points[1]);
	if (points[0] != 5 || points[1] != 9) {
		fprintf(stderr, "SYNCOBJ_QUERY got %llu/%llu want 5/9\n",
			(unsigned long long)points[0],
			(unsigned long long)points[1]);
		goto out_destroy_timeline_b;
	}

	points[0] = 0;
	points[1] = 0;
	timeline_array.flags = DRM_SYNCOBJ_QUERY_FLAGS_LAST_SUBMITTED;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_QUERY, &timeline_array) < 0) {
		fprintf(stderr, "SYNCOBJ_QUERY_LAST_SUBMITTED failed: %s\n",
			strerror(errno));
		goto out_destroy_timeline_b;
	}
	printf("SYNCOBJ_QUERY_LAST_SUBMITTED count=2 point0=%llu point1=%llu\n",
	       (unsigned long long)points[0],
	       (unsigned long long)points[1]);
	if (points[0] != 5 || points[1] != 9) {
		fprintf(stderr,
			"SYNCOBJ_QUERY_LAST_SUBMITTED got %llu/%llu want 5/9\n",
			(unsigned long long)points[0],
			(unsigned long long)points[1]);
		goto out_destroy_timeline_b;
	}

	if (expect_syncobj_timeline_array_failure(
		    fd, DRM_IOCTL_SYNCOBJ_QUERY, &invalid_handle, points, 1, 0,
		    "SYNCOBJ_QUERY_INVALID"))
		goto out_destroy_timeline_b;

	ret = 0;

out_destroy_timeline_b:
	if (timeline_b.handle) {
		destroy.handle = timeline_b.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_SIGNAL_TIMELINE[1] handle=%u failed: %s\n",
				timeline_b.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_SIGNAL_TIMELINE[1] handle=%u\n",
			       timeline_b.handle);
		}
	}

out_destroy_timeline_a:
	if (timeline_a.handle) {
		destroy.handle = timeline_a.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_SIGNAL_TIMELINE[0] handle=%u failed: %s\n",
				timeline_a.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_SIGNAL_TIMELINE[0] handle=%u\n",
			       timeline_a.handle);
		}
	}

out_destroy_binary:
	if (binary.handle) {
		destroy.handle = binary.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_SIGNAL_BINARY handle=%u failed: %s\n",
				binary.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_SIGNAL_BINARY handle=%u\n",
			       binary.handle);
		}
	}

	if (!ret)
		printf("PANTHOR_SYNCOBJ_SIGNAL_QUERY_SMOKE=PASS\n");
	return ret;
}

static uint64_t first_bit_mask64(uint64_t mask)
{
	return mask & (~mask + 1);
}

static int expect_group_destroy_failure(int fd, uint32_t handle,
					const char *label)
{
	struct drm_panthor_group_destroy destroy = {
		.group_handle = handle,
	};
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY, &destroy) == 0) {
		fprintf(stderr, "%s handle=%u unexpectedly succeeded\n",
			label, handle);
		return -1;
	}

	saved_errno = errno;
	printf("%s handle=%u expected_failure errno=%d (%s)\n",
	       label, handle, saved_errno, strerror(saved_errno));
	return 0;
}

static int group_lifecycle_check(int fd)
{
	struct drm_panthor_gpu_info gpu = { 0 };
	struct drm_panthor_csif_info csif = { 0 };
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_destroy vm_destroy = { 0 };
	struct drm_panthor_queue_create queue = {
		.priority = 0,
		.ringbuf_size = 4096,
	};
	struct drm_panthor_group_create group = { 0 };
	struct drm_panthor_group_get_state state = { 0 };
	struct drm_panthor_group_destroy group_destroy = { 0 };
	uint32_t created_group = 0;
	int ret = -1;

	if (query_gpu_info_out(fd, &gpu) || query_csif_info_out(fd, &csif))
		return -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for GROUP lifecycle smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);
	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	group.queues.count = 1;
	group.queues.stride = sizeof(queue);
	group.queues.array = (uint64_t)(uintptr_t)&queue;
	group.max_compute_cores = 1;
	group.max_fragment_cores = 1;
	group.max_tiler_cores = 1;
	group.priority = PANTHOR_GROUP_PRIORITY_LOW;
	group.compute_core_mask = first_bit_mask64(gpu.shader_present);
	group.fragment_core_mask = first_bit_mask64(gpu.shader_present);
	group.tiler_core_mask = first_bit_mask64(gpu.tiler_present);
	group.vm_id = vm.id;

	if (!group.compute_core_mask || !group.fragment_core_mask ||
	    !group.tiler_core_mask) {
		fprintf(stderr, "GROUP_CREATE missing GPU core masks\n");
		goto out_destroy_vm;
	}

	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &group) < 0) {
		fprintf(stderr, "GROUP_CREATE failed: %s\n", strerror(errno));
		goto out_destroy_vm;
	}

	created_group = group.group_handle;
	printf("GROUP_CREATE handle=%u vm=%u queues=%u queue_ring=0x%x compute_mask=0x%llx fragment_mask=0x%llx tiler_mask=0x%llx\n",
	       created_group, vm.id, group.queues.count, queue.ringbuf_size,
	       (unsigned long long)group.compute_core_mask,
	       (unsigned long long)group.fragment_core_mask,
	       (unsigned long long)group.tiler_core_mask);
	if (!created_group) {
		fprintf(stderr, "GROUP_CREATE returned invalid handle\n");
		goto out_destroy_group;
	}

	state.group_handle = created_group;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_GET_STATE, &state) < 0) {
		fprintf(stderr, "GROUP_GET_STATE handle=%u failed: %s\n",
			created_group, strerror(errno));
		goto out_destroy_group;
	}

	printf("GROUP_GET_STATE handle=%u state=0x%x fatal_queues=0x%x\n",
	       created_group, state.state, state.fatal_queues);
	if (state.state & ~(DRM_PANTHOR_GROUP_STATE_TIMEDOUT |
			    DRM_PANTHOR_GROUP_STATE_FATAL_FAULT)) {
		fprintf(stderr, "GROUP_GET_STATE returned invalid state bits: 0x%x\n",
			state.state);
		goto out_destroy_group;
	}
	if (!(state.state & DRM_PANTHOR_GROUP_STATE_FATAL_FAULT) &&
	    state.fatal_queues) {
		fprintf(stderr, "GROUP_GET_STATE fatal_queues without fatal fault: 0x%x\n",
			state.fatal_queues);
		goto out_destroy_group;
	}

	group_destroy.group_handle = created_group;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY, &group_destroy) < 0) {
		fprintf(stderr, "GROUP_DESTROY handle=%u failed: %s\n",
			created_group, strerror(errno));
		goto out_destroy_group;
	}

	printf("GROUP_DESTROY handle=%u\n", created_group);
	if (expect_group_destroy_failure(fd, created_group,
					 "GROUP_DESTROY_DOUBLE"))
		goto out_destroy_vm;
	created_group = 0;

	ret = 0;
	goto out_destroy_vm;

out_destroy_group:
	if (created_group) {
		group_destroy.group_handle = created_group;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY,
			  &group_destroy) < 0) {
			fprintf(stderr,
				"GROUP_DESTROY leftover handle=%u failed: %s\n",
				created_group, strerror(errno));
			ret = -1;
		} else {
			printf("GROUP_DESTROY_LEFTOVER handle=%u\n",
			       created_group);
		}
	}

out_destroy_vm:
	vm_destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &vm_destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_GROUP_LIFECYCLE_SMOKE=PASS\n");
	return ret;
}

static int group_submit_syncpoint_check(int fd)
{
	struct drm_panthor_gpu_info gpu = { 0 };
	struct drm_panthor_csif_info csif = { 0 };
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_destroy vm_destroy = { 0 };
	struct drm_syncobj_create sync = { 0 };
	struct drm_syncobj_destroy sync_destroy = { 0 };
	struct drm_syncobj_wait wait = { 0 };
	struct drm_panthor_queue_create queue = {
		.priority = 0,
		.ringbuf_size = 4096,
	};
	struct drm_panthor_group_create group = { 0 };
	struct drm_panthor_group_get_state state = { 0 };
	struct drm_panthor_group_destroy group_destroy = { 0 };
	struct drm_panthor_sync_op sync_op = {
		.flags = DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ |
			 DRM_PANTHOR_SYNC_OP_SIGNAL,
	};
	struct drm_panthor_queue_submit submit = {
		.queue_index = 0,
		.stream_size = 0,
		.stream_addr = 0,
		.latest_flush = 0,
	};
	struct drm_panthor_group_submit group_submit = { 0 };
	uint32_t created_group = 0;
	uint32_t wait_handle = 0;
	int ret = -1;

	if (query_gpu_info_out(fd, &gpu) || query_csif_info_out(fd, &csif))
		return -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for GROUP_SUBMIT syncpoint smoke failed: %s\n",
			strerror(errno));
		return -1;
	}
	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);
	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &sync) < 0) {
		fprintf(stderr, "SYNCOBJ_CREATE_GROUP_SUBMIT_SIGNAL failed: %s\n",
			strerror(errno));
		goto out_destroy_vm;
	}
	printf("SYNCOBJ_CREATE_GROUP_SUBMIT_SIGNAL handle=%u flags=0x%x\n",
	       sync.handle, sync.flags);
	if (!sync.handle) {
		fprintf(stderr, "SYNCOBJ_CREATE returned invalid handle\n");
		goto out_destroy_sync;
	}

	group.queues.count = 1;
	group.queues.stride = sizeof(queue);
	group.queues.array = (uint64_t)(uintptr_t)&queue;
	group.max_compute_cores = 1;
	group.max_fragment_cores = 1;
	group.max_tiler_cores = 1;
	group.priority = PANTHOR_GROUP_PRIORITY_LOW;
	group.compute_core_mask = first_bit_mask64(gpu.shader_present);
	group.fragment_core_mask = first_bit_mask64(gpu.shader_present);
	group.tiler_core_mask = first_bit_mask64(gpu.tiler_present);
	group.vm_id = vm.id;
	if (!group.compute_core_mask || !group.fragment_core_mask ||
	    !group.tiler_core_mask) {
		fprintf(stderr, "GROUP_CREATE missing GPU core masks\n");
		goto out_destroy_sync;
	}

	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &group) < 0) {
		fprintf(stderr, "GROUP_CREATE for GROUP_SUBMIT failed: %s\n",
			strerror(errno));
		goto out_destroy_sync;
	}

	created_group = group.group_handle;
	printf("GROUP_CREATE handle=%u vm=%u queues=%u queue_ring=0x%x compute_mask=0x%llx fragment_mask=0x%llx tiler_mask=0x%llx\n",
	       created_group, vm.id, group.queues.count, queue.ringbuf_size,
	       (unsigned long long)group.compute_core_mask,
	       (unsigned long long)group.fragment_core_mask,
	       (unsigned long long)group.tiler_core_mask);
	if (!created_group) {
		fprintf(stderr, "GROUP_CREATE returned invalid handle\n");
		goto out_destroy_group;
	}

	sync_op.handle = sync.handle;
	submit.syncs.stride = sizeof(sync_op);
	submit.syncs.count = 1;
	submit.syncs.array = (uint64_t)(uintptr_t)&sync_op;
	group_submit.group_handle = created_group;
	group_submit.queue_submits.stride = sizeof(submit);
	group_submit.queue_submits.count = 1;
	group_submit.queue_submits.array = (uint64_t)(uintptr_t)&submit;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_SUBMIT, &group_submit) < 0) {
		fprintf(stderr, "GROUP_SUBMIT_SYNCPOINT failed: %s\n",
			strerror(errno));
		goto out_destroy_group;
	}
	printf("GROUP_SUBMIT_SYNCPOINT group=%u sync=%u queue=%u stream_addr=0x%llx stream_size=%u sync_flags=0x%x\n",
	       created_group, sync.handle, submit.queue_index,
	       (unsigned long long)submit.stream_addr, submit.stream_size,
	       sync_op.flags);

	wait_handle = sync.handle;
	wait.handles = (uint64_t)(uintptr_t)&wait_handle;
	wait.timeout_nsec = 1000000000LL;
	wait.count_handles = 1;
	wait.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=%u failed: %s\n",
			sync.handle, strerror(errno));
		goto out_destroy_group;
	}
	printf("SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=%u timeout_nsec=%lld flags=0x%x first=%u\n",
	       sync.handle, (long long)wait.timeout_nsec, wait.flags,
	       wait.first_signaled);
	if (wait.first_signaled != 0) {
		fprintf(stderr, "SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT first=%u want 0\n",
			wait.first_signaled);
		goto out_destroy_group;
	}

	state.group_handle = created_group;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_GET_STATE, &state) < 0) {
		fprintf(stderr, "GROUP_GET_STATE_AFTER_SUBMIT handle=%u failed: %s\n",
			created_group, strerror(errno));
		goto out_destroy_group;
	}
	printf("GROUP_GET_STATE_AFTER_SUBMIT handle=%u state=0x%x fatal_queues=0x%x\n",
	       created_group, state.state, state.fatal_queues);
	if (state.state & ~(DRM_PANTHOR_GROUP_STATE_TIMEDOUT |
			    DRM_PANTHOR_GROUP_STATE_FATAL_FAULT)) {
		fprintf(stderr,
			"GROUP_GET_STATE_AFTER_SUBMIT returned invalid state bits: 0x%x\n",
			state.state);
		goto out_destroy_group;
	}

	group_destroy.group_handle = created_group;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY, &group_destroy) < 0) {
		fprintf(stderr, "GROUP_DESTROY_AFTER_SUBMIT handle=%u failed: %s\n",
			created_group, strerror(errno));
		goto out_destroy_group;
	}
	printf("GROUP_DESTROY_AFTER_SUBMIT handle=%u\n", created_group);
	created_group = 0;

	ret = 0;

out_destroy_group:
	if (created_group) {
		group_destroy.group_handle = created_group;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY,
			  &group_destroy) < 0) {
			fprintf(stderr,
				"GROUP_DESTROY_SUBMIT_LEFTOVER handle=%u failed: %s\n",
				created_group, strerror(errno));
			ret = -1;
		} else {
			printf("GROUP_DESTROY_SUBMIT_LEFTOVER handle=%u\n",
			       created_group);
		}
	}

out_destroy_sync:
	if (sync.handle) {
		sync_destroy.handle = sync.handle;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &sync_destroy) < 0) {
			fprintf(stderr,
				"SYNCOBJ_DESTROY_GROUP_SUBMIT_SIGNAL handle=%u failed: %s\n",
				sync.handle, strerror(errno));
			ret = -1;
		} else {
			printf("SYNCOBJ_DESTROY_GROUP_SUBMIT_SIGNAL handle=%u\n",
			       sync.handle);
		}
	}

out_destroy_vm:
	vm_destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &vm_destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS\n");
	return ret;
}

static int expect_tiler_heap_destroy_failure(int fd, uint32_t handle,
					     const char *label)
{
	struct drm_panthor_tiler_heap_destroy destroy = {
		.handle = handle,
	};
	int saved_errno;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY, &destroy) == 0) {
		fprintf(stderr, "%s handle=%u unexpectedly succeeded\n",
			label, handle);
		return -1;
	}

	saved_errno = errno;
	printf("%s handle=%u expected_failure errno=%d (%s)\n",
	       label, handle, saved_errno, strerror(saved_errno));
	return 0;
}

static int tiler_heap_lifecycle_check(int fd)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_vm_destroy vm_destroy = { 0 };
	struct drm_panthor_tiler_heap_create heap = {
		.initial_chunk_count = 1,
		.chunk_size = 128 * 1024,
		.max_chunks = 2,
		.target_in_flight = 1,
	};
	struct drm_panthor_tiler_heap_destroy heap_destroy = { 0 };
	uint32_t created_heap = 0;
	int ret = -1;

	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		fprintf(stderr, "VM_CREATE for TILER_HEAP lifecycle smoke failed: %s\n",
			strerror(errno));
		return -1;
	}

	printf("VM_CREATE id=%u user_va_range=0x%llx\n",
	       vm.id, (unsigned long long)vm.user_va_range);
	if (!vm.id || !vm.user_va_range) {
		fprintf(stderr, "VM_CREATE returned invalid id/range\n");
		goto out_destroy_vm;
	}

	heap.vm_id = vm.id;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE, &heap) < 0) {
		fprintf(stderr, "TILER_HEAP_CREATE failed: %s\n",
			strerror(errno));
		goto out_destroy_vm;
	}

	created_heap = heap.handle;
	printf("TILER_HEAP_CREATE handle=%u vm=%u initial_chunks=%u chunk_size=0x%x max_chunks=%u target_in_flight=%u ctx_va=0x%llx first_chunk_va=0x%llx\n",
	       created_heap, vm.id, heap.initial_chunk_count, heap.chunk_size,
	       heap.max_chunks, heap.target_in_flight,
	       (unsigned long long)heap.tiler_heap_ctx_gpu_va,
	       (unsigned long long)heap.first_heap_chunk_gpu_va);
	if (!created_heap || !heap.tiler_heap_ctx_gpu_va ||
	    !heap.first_heap_chunk_gpu_va) {
		fprintf(stderr, "TILER_HEAP_CREATE returned invalid handle/GPU VA\n");
		goto out_destroy_heap;
	}

	heap_destroy.handle = created_heap;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY,
		  &heap_destroy) < 0) {
		fprintf(stderr, "TILER_HEAP_DESTROY handle=%u failed: %s\n",
			created_heap, strerror(errno));
		goto out_destroy_heap;
	}

	printf("TILER_HEAP_DESTROY handle=%u\n", created_heap);
	if (expect_tiler_heap_destroy_failure(fd, created_heap,
					      "TILER_HEAP_DESTROY_DOUBLE"))
		goto out_destroy_vm;
	created_heap = 0;

	ret = 0;
	goto out_destroy_vm;

out_destroy_heap:
	if (created_heap) {
		heap_destroy.handle = created_heap;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY,
			  &heap_destroy) < 0) {
			fprintf(stderr,
				"TILER_HEAP_DESTROY_LEFTOVER handle=%u failed: %s\n",
				created_heap, strerror(errno));
			ret = -1;
		} else {
			printf("TILER_HEAP_DESTROY_LEFTOVER handle=%u\n",
			       created_heap);
		}
	}

out_destroy_vm:
	vm_destroy.id = vm.id;
	if (vm.id && ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &vm_destroy) < 0) {
		fprintf(stderr, "VM_DESTROY id=%u failed: %s\n",
			vm.id, strerror(errno));
		ret = -1;
	} else if (vm.id) {
		printf("VM_DESTROY id=%u\n", vm.id);
	}

	if (!ret)
		printf("PANTHOR_TILER_HEAP_LIFECYCLE_SMOKE=PASS\n");
	return ret;
}

int main(int argc, char **argv)
{
	const char *default_nodes[] = {
		"/dev/dri/card0",
		"/dev/dri/renderD128",
	};
	enum smoke_mode mode = SMOKE_BASIC;
	const char *path = NULL;
	int fd = -1;
	size_t i;

	for (i = 1; i < (size_t)argc; i++) {
		if (!strcmp(argv[i], "--basic")) {
			mode = SMOKE_BASIC;
		} else if (!strcmp(argv[i], "--vm-create")) {
			mode = SMOKE_VM_CREATE;
		} else if (!strcmp(argv[i], "--bo-create")) {
			mode = SMOKE_BO_CREATE;
		} else if (!strcmp(argv[i], "--bo-lifecycle")) {
			mode = SMOKE_BO_LIFECYCLE;
		} else if (!strcmp(argv[i], "--bo-mmap")) {
			mode = SMOKE_BO_MMAP;
		} else if (!strcmp(argv[i], "--vm-bind")) {
			mode = SMOKE_VM_BIND;
		} else if (!strcmp(argv[i], "--vm-bind-async-sync")) {
			mode = SMOKE_VM_BIND_ASYNC_SYNC;
		} else if (!strcmp(argv[i], "--vm-state-flush")) {
			mode = SMOKE_VM_STATE_FLUSH;
		} else if (!strcmp(argv[i], "--syncobj-lifecycle")) {
			mode = SMOKE_SYNCOBJ_LIFECYCLE;
		} else if (!strcmp(argv[i], "--syncobj-wait")) {
			mode = SMOKE_SYNCOBJ_WAIT;
		} else if (!strcmp(argv[i], "--syncobj-transfer")) {
			mode = SMOKE_SYNCOBJ_TRANSFER;
		} else if (!strcmp(argv[i], "--syncobj-timeline-wait")) {
			mode = SMOKE_SYNCOBJ_TIMELINE_WAIT;
		} else if (!strcmp(argv[i], "--syncobj-signal-query")) {
			mode = SMOKE_SYNCOBJ_SIGNAL_QUERY;
		} else if (!strcmp(argv[i], "--group-lifecycle")) {
			mode = SMOKE_GROUP_LIFECYCLE;
		} else if (!strcmp(argv[i], "--group-submit-syncpoint")) {
			mode = SMOKE_GROUP_SUBMIT_SYNCPOINT;
		} else if (!strcmp(argv[i], "--tiler-heap-lifecycle")) {
			mode = SMOKE_TILER_HEAP_LIFECYCLE;
		} else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
			usage(argv[0]);
			return 0;
		} else if (!path) {
			path = argv[i];
		} else {
			usage(argv[0]);
			return 2;
		}
	}

	if (path) {
		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0) {
			fprintf(stderr, "open %s failed: %s\n", path,
				strerror(errno));
			return 1;
		}
	} else {
		for (i = 0; i < ARRAY_SIZE(default_nodes); i++) {
			path = default_nodes[i];
			fd = open(path, O_RDWR | O_CLOEXEC);
			if (fd >= 0)
				break;
		}
		if (fd < 0) {
			fprintf(stderr, "open DRM node failed: %s\n",
				strerror(errno));
			return 1;
		}
	}

	printf("OPEN path=%s fd=%d\n", path, fd);

	if (basic_checks(fd) ||
	    (mode == SMOKE_VM_CREATE && vm_create_check(fd)) ||
		    (mode == SMOKE_BO_CREATE && bo_create_check(fd)) ||
		    (mode == SMOKE_BO_LIFECYCLE && bo_lifecycle_check(fd)) ||
		    (mode == SMOKE_BO_MMAP && bo_mmap_check(fd)) ||
		    (mode == SMOKE_VM_BIND && vm_bind_check(fd)) ||
		    (mode == SMOKE_VM_BIND_ASYNC_SYNC &&
		     vm_bind_async_sync_check(fd)) ||
		    (mode == SMOKE_VM_STATE_FLUSH &&
		     vm_state_flush_check(fd)) ||
		    (mode == SMOKE_SYNCOBJ_LIFECYCLE &&
		     syncobj_lifecycle_check(fd)) ||
		    (mode == SMOKE_SYNCOBJ_WAIT &&
		     syncobj_wait_check(fd)) ||
		    (mode == SMOKE_SYNCOBJ_TRANSFER &&
		     syncobj_transfer_check(fd)) ||
			    (mode == SMOKE_SYNCOBJ_TIMELINE_WAIT &&
			     syncobj_timeline_wait_check(fd)) ||
				    (mode == SMOKE_SYNCOBJ_SIGNAL_QUERY &&
				     syncobj_signal_query_check(fd)) ||
					    (mode == SMOKE_GROUP_LIFECYCLE &&
					     group_lifecycle_check(fd)) ||
					    (mode == SMOKE_GROUP_SUBMIT_SYNCPOINT &&
					     group_submit_syncpoint_check(fd)) ||
					    (mode == SMOKE_TILER_HEAP_LIFECYCLE &&
					     tiler_heap_lifecycle_check(fd))) {
		close(fd);
		return 1;
	}

	close(fd);
	if (mode == SMOKE_TILER_HEAP_LIFECYCLE)
		printf("PANTHOR_IOCTL_SMOKE=TILER_HEAP_LIFECYCLE_PASS\n");
	else if (mode == SMOKE_GROUP_SUBMIT_SYNCPOINT)
		printf("PANTHOR_IOCTL_SMOKE=GROUP_SUBMIT_SYNCPOINT_PASS\n");
	else if (mode == SMOKE_GROUP_LIFECYCLE)
		printf("PANTHOR_IOCTL_SMOKE=GROUP_LIFECYCLE_PASS\n");
	else if (mode == SMOKE_SYNCOBJ_SIGNAL_QUERY)
		printf("PANTHOR_IOCTL_SMOKE=SYNCOBJ_SIGNAL_QUERY_PASS\n");
	else if (mode == SMOKE_SYNCOBJ_TIMELINE_WAIT)
		printf("PANTHOR_IOCTL_SMOKE=SYNCOBJ_TIMELINE_WAIT_PASS\n");
	else if (mode == SMOKE_SYNCOBJ_TRANSFER)
		printf("PANTHOR_IOCTL_SMOKE=SYNCOBJ_TRANSFER_PASS\n");
	else if (mode == SMOKE_SYNCOBJ_WAIT)
		printf("PANTHOR_IOCTL_SMOKE=SYNCOBJ_WAIT_PASS\n");
	else if (mode == SMOKE_SYNCOBJ_LIFECYCLE)
		printf("PANTHOR_IOCTL_SMOKE=SYNCOBJ_LIFECYCLE_PASS\n");
	else if (mode == SMOKE_VM_STATE_FLUSH)
		printf("PANTHOR_IOCTL_SMOKE=VM_STATE_FLUSH_PASS\n");
	else if (mode == SMOKE_VM_BIND)
		printf("PANTHOR_IOCTL_SMOKE=VM_BIND_PASS\n");
	else if (mode == SMOKE_VM_BIND_ASYNC_SYNC)
		printf("PANTHOR_IOCTL_SMOKE=VM_BIND_ASYNC_SYNC_PASS\n");
	else if (mode == SMOKE_BO_MMAP)
		printf("PANTHOR_IOCTL_SMOKE=BO_MMAP_PASS\n");
	else if (mode == SMOKE_BO_LIFECYCLE)
		printf("PANTHOR_IOCTL_SMOKE=BO_LIFECYCLE_PASS\n");
	else if (mode == SMOKE_BO_CREATE)
		printf("PANTHOR_IOCTL_SMOKE=BO_CREATE_PASS\n");
	else if (mode == SMOKE_VM_CREATE)
		printf("PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS\n");
	else
		printf("PANTHOR_IOCTL_SMOKE=BASIC_PASS\n");
	return 0;
}
