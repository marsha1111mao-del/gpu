// SPDX-License-Identifier: GPL-2.0-only
/* Exercise the actual Guest ioctl/RSI path; no transport emulation. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "linux/realm_xshm.h"

static __u64 pool_selector;

static const struct {
	const char *name;
	unsigned int arguments;
} commands[] = {
	[REALM_XSHM_REGISTER] = { "register", 0 },
	[REALM_XSHM_OFFER] = { "offer", 1 },
	[REALM_XSHM_ACCEPT] = { "accept", 1 },
	[REALM_XSHM_CLOSE] = { "close", 1 },
	[REALM_XSHM_NOTIFY] = { "notify", 1 },
	[REALM_XSHM_ARM] = { "arm", 2 },
	[REALM_XSHM_ACK] = { "ack", 2 },
	[REALM_XSHM_QUERY] = { "query", 1 },
	[REALM_XSHM_UNREGISTER] = { "unregister", 0 },
	[REALM_XSHM_MEM_OFFER] = { "mem-offer", 3 },
	[REALM_XSHM_MEM_ATTACH] = { "mem-attach", 2 },
	[REALM_XSHM_MEM_DETACH] = { "mem-detach", 1 },
	[REALM_XSHM_MEM_REVOKE] = { "mem-revoke", 1 },
	[REALM_XSHM_MEM_STATUS] = { "mem-status", 1 },
	[REALM_XSHM_MEM_CONTINUE] = { "mem-continue", 1 },
	[REALM_XSHM_MEM_DESCRIBE] = { "mem-describe", 1 },
	[REALM_XSHM_IRQ_BIND] = { "irq-bind", 0 },
	[REALM_XSHM_ACK_ARM] = { "ack-arm", 1 },
};

static int parse_number(const char *text, __u64 *value)
{
	char *end;
	unsigned long long parsed;

	if (*text < '0' || *text > '9')
		return -1;
	errno = 0;
	parsed = strtoull(text, &end, 0);
	if (errno || *end)
		return -1;
	*value = parsed;
	return 0;
}

static int ioctl_error(int fd, const char *command, const char *label)
{
	int error = errno;

	perror(label);
	close(fd);
	printf("{\"command\":\"%s\",\"status\":%d,\"result\":[0,0,0,0]}\n",
	       command, -error);
	return 1;
}

/* Keep full page coverage without a serial round trip/fork for every word. */
static int pool_pages_command(int argc, char **argv)
{
	struct realm_xshm_pool pool = { .operation = REALM_XSHM_POOL_INFO,
					.ipa = pool_selector };
	__u64 seed, grant = 0, pages, index;
	int fill = !strcmp(argv[1], "pool-fill-pages");
	int fd;

	if ((argc != 3 && argc != 4) || parse_number(argv[2], &seed) ||
	    (argc == 4 && parse_number(argv[3], &grant)))
		return 2;
	fd = open("/dev/realm-xshm", O_RDWR | O_CLOEXEC);
	if (fd < 0)
		return ioctl_error(fd, argv[1], "open realm-xshm");
	if (ioctl(fd, REALM_XSHM_POOL, &pool))
		return ioctl_error(fd, argv[1], "pool-info");
	pages = pool.size / 4096;
	if (!pages || seed > UINT64_MAX - (pages - 1)) {
		close(fd);
		return 2;
	}
	pool.operation = fill ? REALM_XSHM_POOL_WRITE : REALM_XSHM_POOL_READ;
	pool.grant = grant;
	for (index = 0; index < pages; index++) {
		pool.offset = index * 4096;
		pool.value = seed + index;
		if (ioctl(fd, REALM_XSHM_POOL, &pool))
			return ioctl_error(fd, argv[1], "pool page access");
		if (!fill && pool.value != seed + index) {
			fprintf(stderr, "page=%" PRIu64 " expected=%" PRIu64 " actual=%" PRIu64 "\n",
				(uint64_t)index, (uint64_t)(seed + index), (uint64_t)pool.value);
			errno = EILSEQ;
			return ioctl_error(fd, argv[1], "pool page mismatch");
		}
	}
	close(fd);
	printf("{\"command\":\"%s\",\"status\":0,\"result\":[%" PRIu64
	       ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]}\n", argv[1],
	       (uint64_t)pool.ipa, (uint64_t)pool.size,
	       (uint64_t)pages, (uint64_t)grant);
	return 0;
}

static int pool_command(int argc, char **argv)
{
	struct realm_xshm_pool pool = { .ipa = pool_selector };
	int fd, held = -1, busy_probe = 0, ret, error;

	if (!strcmp(argv[1], "pool-source") || !strcmp(argv[1], "pool-target")) {
		if (pool_selector)
			return 2;
		pool.operation = !strcmp(argv[1], "pool-source") ?
			REALM_XSHM_POOL_SOURCE : REALM_XSHM_POOL_TARGET;
		if (argc != 3 || parse_number(argv[2], &pool.size))
			return 2;
	} else if (!strcmp(argv[1], "pool-info")) {
		pool.operation = REALM_XSHM_POOL_INFO;
		if (argc != 2)
			return 2;
	} else if (!strcmp(argv[1], "pool-bind") || !strcmp(argv[1], "pool-bind-gpu") || !strcmp(argv[1], "pool-unbind") ||
		   !strcmp(argv[1], "pool-unbind-busy")) {
		pool.operation = !strcmp(argv[1], "pool-bind") ?
			REALM_XSHM_POOL_BIND : REALM_XSHM_POOL_UNBIND;
		if (!strcmp(argv[1], "pool-bind-gpu"))
			pool.operation = REALM_XSHM_POOL_BIND_GPU;
		busy_probe = !strcmp(argv[1], "pool-unbind-busy");
		if ((argc != 3 && !(busy_probe && argc == 4)) ||
		    parse_number(argv[2], &pool.grant))
			return 2;
	} else if (!strcmp(argv[1], "pool-read") || !strcmp(argv[1], "pool-write")) {
		int write = !strcmp(argv[1], "pool-write");

		pool.operation = write ? REALM_XSHM_POOL_WRITE : REALM_XSHM_POOL_READ;
		if ((argc != 3 + write && argc != 4 + write) ||
		    parse_number(argv[2], &pool.offset) ||
		    (write && parse_number(argv[3], &pool.value)) ||
		    (argc == 4 + write && parse_number(argv[3 + write], &pool.grant)))
			return 2;
	} else {
		return 2;
	}
	fd = open("/dev/realm-xshm", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror("/dev/realm-xshm");
		return 1;
	}
	if (busy_probe) {
		held = open(argc == 4 ? argv[3] : "/dev/client_comm_vmshm",
			    O_RDONLY | O_CLOEXEC);
		if (held < 0)
			return ioctl_error(fd, argv[1], "open comm consumer");
	}
	ret = ioctl(fd, REALM_XSHM_POOL, &pool);
	error = errno;
	if (held >= 0)
		close(held);
	if (busy_probe) {
		pool.value = error;
		if (ret && error == EBUSY)
			ret = 0;
		else {
			ret = -1;
			error = EPROTO;
		}
	}
	if (ret) {
		errno = error;
		return ioctl_error(fd, argv[1], "REALM_XSHM_POOL");
	}
	close(fd);
	printf("{\"command\":\"%s\",\"status\":0,\"result\":[%" PRIu64
	       ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]}\n", argv[1],
	       (uint64_t)pool.ipa, (uint64_t)pool.size,
	       (uint64_t)pool.value, (uint64_t)pool.grant);
	return 0;
}

/* Actual GIC dispatch counter, not an event-sequence or software wake count. */
static int irq_stats(void)
{
	char *line = NULL;
	size_t size = 0;
	FILE *file = fopen("/proc/interrupts", "r");
	unsigned long long count = 0;
	int found = 0;

	if (!file)
		return 1;
	while (getline(&line, &size, file) >= 0) {
		char *cursor, *end;

		if (!strstr(line, "realm-xshm"))
			continue;
		cursor = strchr(line, ':');
		if (!cursor)
			break;
		cursor++;
		for (;;) {
			unsigned long long value = strtoull(cursor, &end, 10);

			if (cursor == end)
				break;
			count += value;
			cursor = end;
		}
		found = 1;
		break;
	}
	free(line);
	fclose(file);
	printf("{\"command\":\"irq-stats\",\"status\":%d,\"result\":[%llu,0,0,0]}\n",
	       found ? 0 : -ENODEV, count);
	return found ? 0 : 1;
}

int main(int argc, char **argv)
{
	struct realm_xshm_call call = {0};
	unsigned int command;
	int fd;

	_Static_assert(sizeof(call) == 72, "ioctl ABI size");
	if (argc == 2 && !strcmp(argv[1], "irq-stats"))
		return irq_stats();
	if (argc > 1 && !strcmp(argv[1], "--pool")) {
		if (argc < 4 || parse_number(argv[2], &pool_selector) ||
		    !pool_selector || strncmp(argv[3], "pool-", 5))
			return 2;
		argc -= 2;
		argv += 2;
	}
	if (argc > 1 && (!strcmp(argv[1], "pool-fill-pages") ||
			 !strcmp(argv[1], "pool-check-pages")))
		return pool_pages_command(argc, argv);
	if (argc < 2 || !strcmp(argv[1], "--help")) {
		puts("realm-xshm [--pool LOCAL_IPA] pool-... (required for ambiguous pools)\n"
		     "realm-xshm register|unregister|irq-bind|irq-stats\n"
		     "realm-xshm offer PEER_ENDPOINT\n"
		     "realm-xshm accept|close|notify|query CHANNEL\n"
		     "realm-xshm ack|arm CHANNEL SEQUENCE\n"
		     "realm-xshm mem-offer CHANNEL SOURCE_IPA SIZE\n"
		     "realm-xshm mem-attach GRANT TARGET_IPA\n"
		     "realm-xshm mem-detach|mem-revoke|mem-status|mem-continue|mem-describe GRANT\n"
		     "realm-xshm pool-source|pool-target SIZE\n"
		     "realm-xshm pool-info\n"
		     "realm-xshm pool-bind|pool-bind-gpu|pool-unbind GRANT\n"
		     "realm-xshm pool-fill-pages|pool-check-pages SEED [GRANT]\n"
		     "realm-xshm pool-unbind-busy GRANT [COMM_DEVICE]\n"
		     "realm-xshm pool-read OFFSET [GRANT]\n"
		     "realm-xshm pool-write OFFSET VALUE [GRANT]");
		return argc < 2 ? 2 : 0;
	}
	if (!strncmp(argv[1], "pool-", 5))
		return pool_command(argc, argv);
	for (command = 0; command < sizeof(commands) / sizeof(commands[0]); command++)
		if (!strcmp(argv[1], commands[command].name))
			break;
	if (command == sizeof(commands) / sizeof(commands[0]) ||
	    argc != 2 + (int)commands[command].arguments ||
	    (argc > 2 && parse_number(argv[2], &call.id)) ||
	    (argc > 3 && parse_number(argv[3], &call.sequence)) ||
	    (argc > 4 && parse_number(argv[4], &call.size))) {
		fputs("invalid command/arguments; use --help\n", stderr);
		return 2;
	}
	call.command = command;
	fd = open("/dev/realm-xshm", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror("/dev/realm-xshm");
		return 1;
	}
	if (ioctl(fd, REALM_XSHM_CALL, &call))
		return ioctl_error(fd, argv[1], "REALM_XSHM_CALL");
	close(fd);
	printf("{\"command\":\"%s\",\"status\":%" PRIu64
	       ",\"result\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]}\n",
	       commands[command].name, (uint64_t)call.status,
	       (uint64_t)call.result[0], (uint64_t)call.result[1],
	       (uint64_t)call.result[2], (uint64_t)call.result[3]);
	return call.status ? 3 : 0;
}
