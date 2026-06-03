// SPDX-License-Identifier: MIT
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <drm.h>
#include "panthor_drm.h"

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))

enum smoke_mode {
	SMOKE_BASIC,
	SMOKE_VM_CREATE,
};

static void usage(const char *prog)
{
	fprintf(stderr, "usage: %s [--basic|--vm-create] [drm-node]\n", prog);
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

static int query_gpu_info(int fd)
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

	return 0;
}

static int query_csif_info(int fd)
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

	return 0;
}

static int basic_checks(int fd)
{
	if (get_version(fd) ||
	    get_cap(fd, DRM_CAP_SYNCOBJ, "DRM_CAP_SYNCOBJ", 1) ||
	    get_cap(fd, DRM_CAP_SYNCOBJ_TIMELINE,
		    "DRM_CAP_SYNCOBJ_TIMELINE", 1) ||
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
	    (mode == SMOKE_VM_CREATE && vm_create_check(fd))) {
		close(fd);
		return 1;
	}

	close(fd);
	if (mode == SMOKE_VM_CREATE)
		printf("PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS\n");
	else
		printf("PANTHOR_IOCTL_SMOKE=BASIC_PASS\n");
	return 0;
}
