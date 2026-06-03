// SPDX-License-Identifier: GPL-2.0
/*
 * vmshm_demo - cross-VM userspace smoke test for /dev/vmshm
 *
 * Build:
 *   aarch64-linux-gnu-gcc -O2 -Wall -static -o vmshm_demo \
 *     drivers/char/vmshm/vmshm_demo.c
 *
 * Example:
 *   VM A: ./vmshm_demo read  --offset 0x1000 --seq 1 --timeout 30000
 *   VM B: ./vmshm_demo write --offset 0x1000 --seq 1 "hello from vm B"
 */

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/types.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define VMSHM_IOC_MAGIC 'V'
#define VMSHM_IOC_GET_SIZE _IOR(VMSHM_IOC_MAGIC, 1, __u64)
#define VMSHM_IOC_GET_BASE _IOR(VMSHM_IOC_MAGIC, 2, __u64)

#define VMSHM_DEV "/dev/vmshm"

#define XVM_MAGIC 0x564d5854u /* "VMXT" */
#define XVM_VERSION 1u

#define XVM_STATE_EMPTY 0u
#define XVM_STATE_WRITING 1u
#define XVM_STATE_READY 2u

struct xvm_slot {
	uint32_t magic;
	uint32_t version;
	uint32_t state;
	uint32_t header_size;
	uint64_t seq;
	uint64_t payload_len;
	uint32_t checksum;
	uint32_t reserved;
	uint8_t payload[];
};

struct options {
	const char *dev;
	uint64_t offset;
	uint64_t seq;
	int timeout_ms;
};

static void usage(const char *prog)
{
	fprintf(stderr,
		"Usage:\n"
		"  %s write [--dev PATH] [--offset N] [--seq N] MESSAGE...\n"
		"  %s read  [--dev PATH] [--offset N] [--seq N] [--timeout MS]\n"
		"  %s clear [--dev PATH] [--offset N]\n",
		prog, prog, prog);
}

static uint64_t parse_u64(const char *s, const char *name)
{
	char *end = NULL;
	unsigned long long v;

	errno = 0;
	v = strtoull(s, &end, 0);
	if (errno || !end || *end) {
		fprintf(stderr, "invalid %s: %s\n", name, s);
		exit(2);
	}

	return (uint64_t)v;
}

static uint32_t checksum32(const void *data, size_t len)
{
	const uint8_t *p = data;
	uint32_t sum = 0;
	size_t i;

	for (i = 0; i < len; i++)
		sum = (sum << 5) ^ (sum >> 27) ^ p[i];

	return sum;
}

static long long now_ms(void)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts)) {
		perror("clock_gettime");
		exit(1);
	}

	return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static char *join_message(int argc, char **argv, int first, size_t *len)
{
	size_t total = 0;
	char *msg;
	int i;

	for (i = first; i < argc; i++)
		total += strlen(argv[i]) + (i + 1 < argc ? 1 : 0);

	msg = malloc(total + 1);
	if (!msg) {
		perror("malloc");
		exit(1);
	}

	msg[0] = '\0';
	for (i = first; i < argc; i++) {
		strcat(msg, argv[i]);
		if (i + 1 < argc)
			strcat(msg, " ");
	}

	*len = total;
	return msg;
}

static int open_and_map(const char *dev, uint64_t *base, uint64_t *size,
			void **map)
{
	int fd;

	fd = open(dev, O_RDWR);
	if (fd < 0) {
		perror(dev);
		return -1;
	}

	if (ioctl(fd, VMSHM_IOC_GET_SIZE, size) < 0) {
		perror("ioctl GET_SIZE");
		close(fd);
		return -1;
	}

	if (ioctl(fd, VMSHM_IOC_GET_BASE, base) < 0) {
		perror("ioctl GET_BASE");
		close(fd);
		return -1;
	}

	*map = mmap(NULL, *size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (*map == MAP_FAILED) {
		perror("mmap");
		close(fd);
		return -1;
	}

	return fd;
}

static struct xvm_slot *slot_at(void *map, uint64_t region_size,
				uint64_t offset, size_t need)
{
	if (offset > region_size || need > region_size - offset) {
		fprintf(stderr,
			"slot out of range: offset=0x%" PRIx64
			" need=0x%zx region=0x%" PRIx64 "\n",
			offset, need, region_size);
		exit(2);
	}

	return (struct xvm_slot *)((uint8_t *)map + offset);
}

static int do_write(const struct options *opt, const void *msg, size_t msg_len)
{
	uint64_t base = 0, size = 0;
	size_t need = sizeof(struct xvm_slot) + msg_len;
	struct xvm_slot *slot;
	void *map;
	int fd;

	fd = open_and_map(opt->dev, &base, &size, &map);
	if (fd < 0)
		return 1;

	printf("vmshm: base=0x%" PRIx64 " size=0x%" PRIx64
	       " offset=0x%" PRIx64 " seq=%" PRIu64 "\n",
	       base, size, opt->offset, opt->seq);

	slot = slot_at(map, size, opt->offset, need);

	__atomic_store_n(&slot->state, XVM_STATE_WRITING, __ATOMIC_RELEASE);
	slot->magic = XVM_MAGIC;
	slot->version = XVM_VERSION;
	slot->header_size = sizeof(*slot);
	slot->seq = opt->seq;
	slot->payload_len = msg_len;
	memcpy(slot->payload, msg, msg_len);
	slot->checksum = checksum32(slot->payload, msg_len);
	__atomic_thread_fence(__ATOMIC_RELEASE);
	__atomic_store_n(&slot->state, XVM_STATE_READY, __ATOMIC_RELEASE);

	printf("write: len=%zu checksum=0x%08x message=\"%.*s\"\n",
	       msg_len, slot->checksum, (int)msg_len,
	       (const char *)slot->payload);

	munmap(map, size);
	close(fd);
	return 0;
}

static int do_read(const struct options *opt)
{
	uint64_t base = 0, size = 0;
	struct xvm_slot *slot;
	long long deadline;
	void *map;
	int fd;

	fd = open_and_map(opt->dev, &base, &size, &map);
	if (fd < 0)
		return 1;

	printf("vmshm: base=0x%" PRIx64 " size=0x%" PRIx64
	       " offset=0x%" PRIx64 " seq=%" PRIu64 "\n",
	       base, size, opt->offset, opt->seq);

	slot = slot_at(map, size, opt->offset, sizeof(*slot));
	deadline = opt->timeout_ms < 0 ? -1 : now_ms() + opt->timeout_ms;

	for (;;) {
		uint32_t state = __atomic_load_n(&slot->state, __ATOMIC_ACQUIRE);

		if (slot->magic == XVM_MAGIC && slot->version == XVM_VERSION &&
		    state == XVM_STATE_READY && slot->seq == opt->seq) {
			uint64_t payload_len = slot->payload_len;
			uint32_t expected;
			uint32_t actual;

			if (payload_len > size - opt->offset - sizeof(*slot)) {
				fprintf(stderr, "read: invalid payload_len=%" PRIu64 "\n",
					payload_len);
				munmap(map, size);
				close(fd);
				return 1;
			}

			__atomic_thread_fence(__ATOMIC_ACQUIRE);
			expected = slot->checksum;
			actual = checksum32(slot->payload, payload_len);
			if (actual != expected) {
				fprintf(stderr,
					"read: checksum mismatch expected=0x%08x actual=0x%08x\n",
					expected, actual);
				munmap(map, size);
				close(fd);
				return 1;
			}

			printf("read: len=%" PRIu64 " checksum=0x%08x message=\"%.*s\"\n",
			       payload_len, actual, (int)payload_len,
			       (const char *)slot->payload);
			munmap(map, size);
			close(fd);
			return 0;
		}

		if (deadline >= 0 && now_ms() > deadline) {
			fprintf(stderr,
				"read: timed out waiting for seq=%" PRIu64
				" magic=0x%08x version=%u state=%u current_seq=%" PRIu64 "\n",
				opt->seq, slot->magic, slot->version, state,
				slot->seq);
			munmap(map, size);
			close(fd);
			return 1;
		}

		usleep(1000);
	}
}

static int do_clear(const struct options *opt)
{
	uint64_t base = 0, size = 0;
	struct xvm_slot *slot;
	void *map;
	int fd;

	fd = open_and_map(opt->dev, &base, &size, &map);
	if (fd < 0)
		return 1;

	slot = slot_at(map, size, opt->offset, sizeof(*slot));
	memset(slot, 0, sizeof(*slot));
	__atomic_store_n(&slot->state, XVM_STATE_EMPTY, __ATOMIC_RELEASE);
	printf("clear: offset=0x%" PRIx64 "\n", opt->offset);

	munmap(map, size);
	close(fd);
	return 0;
}

int main(int argc, char **argv)
{
	struct options opt = {
		.dev = VMSHM_DEV,
		.offset = 0x1000,
		.seq = 1,
		.timeout_ms = 10000,
	};
	const char *cmd;
	int i;

	if (argc < 2) {
		usage(argv[0]);
		return 2;
	}

	cmd = argv[1];
	for (i = 2; i < argc;) {
		if (!strcmp(argv[i], "--dev") && i + 1 < argc) {
			opt.dev = argv[i + 1];
			i += 2;
		} else if (!strcmp(argv[i], "--offset") && i + 1 < argc) {
			opt.offset = parse_u64(argv[i + 1], "offset");
			i += 2;
		} else if (!strcmp(argv[i], "--seq") && i + 1 < argc) {
			opt.seq = parse_u64(argv[i + 1], "seq");
			i += 2;
		} else if (!strcmp(argv[i], "--timeout") && i + 1 < argc) {
			opt.timeout_ms = (int)parse_u64(argv[i + 1], "timeout");
			i += 2;
		} else {
			break;
		}
	}

	if (!strcmp(cmd, "write")) {
		char *msg;
		size_t msg_len;
		int ret;

		if (i >= argc) {
			fprintf(stderr, "write requires MESSAGE\n");
			usage(argv[0]);
			return 2;
		}

		msg = join_message(argc, argv, i, &msg_len);
		ret = do_write(&opt, msg, msg_len);
		free(msg);
		return ret;
	}

	if (!strcmp(cmd, "read"))
		return do_read(&opt);

	if (!strcmp(cmd, "clear"))
		return do_clear(&opt);

	usage(argv[0]);
	return 2;
}
