// SPDX-License-Identifier: MIT
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/ioctl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define VMSHM_MANAGER_LOOKUP_HANDLE 1U
#define VMSHM_MANAGER_LOOKUP_GRANT 2U

#define PROXY_VMSHM_PERM_CPU_READ  (1U << 0)
#define PROXY_VMSHM_PERM_CPU_WRITE (1U << 1)
#define PROXY_VMSHM_PERM_MMAP      (1U << 2)

struct vmshm_manager_desc {
	uint64_t handle;
	uint32_t id;
	uint32_t generation;
	uint32_t type;
	uint32_t perms;
	uint64_t offset;
	uint64_t size;
	uint64_t alloc_size;
	uint64_t gpa;
	uint32_t flags;
	uint32_t nr_segments;
};

struct client_vmshm_manager_user_lookup {
	uint64_t handle;
	uint64_t grant_id;
	uint32_t lookup;
	uint32_t requester_vmid;
	uint32_t required_perms;
	uint32_t flags;
	struct vmshm_manager_desc desc;
};

#define CLIENT_VMSHM_MANAGER_IOC_MAGIC 'v'
#define CLIENT_VMSHM_MANAGER_IOC_GET_OBJECT \
	_IOWR(CLIENT_VMSHM_MANAGER_IOC_MAGIC, 2, \
	      struct client_vmshm_manager_user_lookup)

static void usage(const char *prog)
{
	fprintf(stderr,
		"usage: %s --handle HANDLE [--spoof-vmid VMID] [--expect denied|success]\n",
		prog);
}

static int parse_u64(const char *label, const char *value, uint64_t *out)
{
	char *end = NULL;
	unsigned long long parsed;

	errno = 0;
	parsed = strtoull(value, &end, 0);
	if (errno || !end || *end) {
		fprintf(stderr, "invalid %s: %s\n", label, value);
		return -1;
	}

	*out = (uint64_t)parsed;
	return 0;
}

static int parse_u32(const char *label, const char *value, uint32_t *out)
{
	uint64_t parsed;

	if (parse_u64(label, value, &parsed))
		return -1;
	if (parsed > UINT32_MAX) {
		fprintf(stderr, "invalid %s: %s\n", label, value);
		return -1;
	}

	*out = (uint32_t)parsed;
	return 0;
}

int main(int argc, char **argv)
{
	const char *expect = "denied";
	const char *dev = "/dev/client_vmshm_manager";
	struct client_vmshm_manager_user_lookup lookup;
	uint64_t handle = 0;
	uint32_t spoof_vmid = 0;
	int fd;
	int ret;
	int saved_errno = 0;

	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--handle")) {
			if (++i >= argc || parse_u64("--handle", argv[i], &handle))
				return 2;
		} else if (!strcmp(argv[i], "--spoof-vmid")) {
			if (++i >= argc ||
			    parse_u32("--spoof-vmid", argv[i], &spoof_vmid))
				return 2;
		} else if (!strcmp(argv[i], "--expect")) {
			if (++i >= argc)
				return 2;
			expect = argv[i];
		} else if (!strcmp(argv[i], "--device")) {
			if (++i >= argc)
				return 2;
			dev = argv[i];
		} else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
			usage(argv[0]);
			return 0;
		} else {
			usage(argv[0]);
			return 2;
		}
	}

	if (!handle) {
		usage(argv[0]);
		return 2;
	}

	fd = open(dev, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "open %s failed: %s\n", dev, strerror(errno));
		return 3;
	}

	memset(&lookup, 0, sizeof(lookup));
	lookup.handle = handle;
	lookup.lookup = VMSHM_MANAGER_LOOKUP_HANDLE;
	lookup.requester_vmid = spoof_vmid;
	lookup.required_perms = PROXY_VMSHM_PERM_CPU_READ |
				PROXY_VMSHM_PERM_CPU_WRITE |
				PROXY_VMSHM_PERM_MMAP;

	ret = ioctl(fd, CLIENT_VMSHM_MANAGER_IOC_GET_OBJECT, &lookup);
	if (ret < 0)
		saved_errno = errno;
	close(fd);

	if (!strcmp(expect, "denied")) {
		if (ret == 0) {
			fprintf(stderr,
				"VMSHM_LOOKUP_PROBE_FAIL unexpected_success handle=0x%llx desc_owner_unknown offset=0x%llx size=0x%llx\n",
				(unsigned long long)handle,
				(unsigned long long)lookup.desc.offset,
				(unsigned long long)lookup.desc.size);
			return 10;
		}
		printf("VMSHM_LOOKUP_PROBE_DENIED handle=0x%llx errno=%d (%s) spoof_vmid=%u\n",
		       (unsigned long long)handle, saved_errno,
		       strerror(saved_errno), spoof_vmid);
		if (saved_errno != EACCES) {
			fprintf(stderr,
				"VMSHM_LOOKUP_PROBE_FAIL expected_EACCES got=%d (%s)\n",
				saved_errno, strerror(saved_errno));
			return 11;
		}
		return 0;
	}

	if (!strcmp(expect, "success")) {
		if (ret < 0) {
			fprintf(stderr,
				"VMSHM_LOOKUP_PROBE_FAIL unexpected_errno=%d (%s) handle=0x%llx\n",
				saved_errno, strerror(saved_errno),
				(unsigned long long)handle);
			return 12;
		}
		printf("VMSHM_LOOKUP_PROBE_SUCCESS handle=0x%llx offset=0x%llx size=0x%llx alloc_size=0x%llx gpa=0x%llx\n",
		       (unsigned long long)handle,
		       (unsigned long long)lookup.desc.offset,
		       (unsigned long long)lookup.desc.size,
		       (unsigned long long)lookup.desc.alloc_size,
		       (unsigned long long)lookup.desc.gpa);
		return 0;
	}

	usage(argv[0]);
	return 2;
}
