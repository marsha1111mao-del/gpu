// SPDX-License-Identifier: GPL-2.0-only
/* Client registration/PT, prelaunch task staging and service MCU bring-up. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <linux/sync_file.h>
/* Source-tree UAPI headers retain sparse's userspace pointer annotation. */
#ifndef __user
#define __user
#endif
#include "drm/panthor_drm.h"
#include "linux/realm_gpu.h"

#define PAGE 4096UL
#define BASE 0x2000000UL

static int number(const char *text, uint64_t *value)
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

/* Check the actual read-only driver parameter, not just /proc/cmdline: an
 * older kernel may accept an unknown boot argument without enabling isolation.
 * The RMM checks in bootstrap/open remain the independent authority.
 */
static int private_mode(const char *role)
{
	const char *path;
	FILE *parameter;
	int enabled;

	if (!strcmp(role, "client"))
		path = "/sys/module/panthor_client/parameters/rmm_private_data";
	else if (!strcmp(role, "proxy"))
		path = "/sys/module/panthor/parameters/rmm_service";
	else
		return 2;
	parameter = fopen(path, "r");
	if (!parameter) {
		perror(path);
		return 1;
	}
	enabled = fgetc(parameter);
	fclose(parameter);
	if (enabled != 'Y' && enabled != '1') {
		fprintf(stderr, "%s requires private driver mode; no shared fallback\n", role);
		return 1;
	}
	return 0;
}

static int call(int fd, unsigned int operation, uint64_t handle,
		uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e,
		struct realm_gpu_call *result)
{
	*result = (struct realm_gpu_call) {
		.operation = operation, .handle = handle, .args = { a, b, c, d, e },
	};
	return ioctl(fd, REALM_GPU_CALL, result);
}

static int success(int fd, unsigned int operation, uint64_t handle,
		uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e,
		struct realm_gpu_call *result)
{
	if (call(fd, operation, handle, a, b, c, d, e, result)) {
		perror("REALM_GPU_CALL");
		return -1;
	}
	if (result->status) {
		fprintf(stderr, "operation=%u RMM-status=%" PRIu64 "\n",
			operation, (uint64_t)result->status);
		return -1;
	}
	return 0;
}

static void output(const struct realm_gpu_call *result)
{
	printf("{\"operation\":%" PRIu64 ",\"status\":%" PRIu64
	       ",\"result\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]}\n",
	       (uint64_t)result->operation, (uint64_t)result->status,
	       (uint64_t)result->result[0], (uint64_t)result->result[1],
	       (uint64_t)result->result[2], (uint64_t)result->result[3]);
}

static int firmware_snapshot(int fd, const char *path)
{
	unsigned char page[PAGE];
	struct realm_gpu_call result;
	struct stat info;
	uint64_t offset = 0;
	int source = open(path, O_RDONLY | O_CLOEXEC), ret = 1;

	if (source < 0) {
		perror(path);
		return 1;
	}
	if (fstat(source, &info) || !S_ISREG(info.st_mode) || info.st_size <= 0)
		goto out;
	if (success(fd, REALM_GPU_VERSION, 0, 0, 0, 0, 0, 0, &result) ||
	    !(result.result[1] & REALM_GPU_CAP_FW_SNAPSHOT))
		goto out;
	if (success(fd, REALM_GPU_FW_BEGIN, 0, info.st_size, 0, 0, 0, 0, &result))
		goto out;
	while (offset < (uint64_t)info.st_size) {
		ssize_t got;
		size_t bytes;

		do {
			got = read(source, page, sizeof(page));
		} while (got < 0 && errno == EINTR);
		if (got <= 0 || (uint64_t)got > (uint64_t)info.st_size - offset) {
			fputs("firmware input changed, truncated or unreadable\n", stderr);
			goto out;
		}
		bytes = (size_t)got;
		if (success(fd, REALM_GPU_FW_WRITE, 0, (uintptr_t)page, bytes, offset,
			    0, 0, &result) || result.result[0] != offset + bytes)
			goto out;
		offset += bytes;
	}
	if (success(fd, REALM_GPU_FW_SEAL, 0, 0, 0, 0, 0, 0, &result))
		goto out;
	output(&result);
	if (result.result[0] != 2 || result.result[1] != offset)
		goto out;
	puts("GPU_FIRMWARE_SNAPSHOT=VERIFIED GPU_FIRMWARE_BOOT=NOT_RUN GPU_EXECUTION=NOT_RUN");
	ret = 0;
out:
	close(source);
	return ret;
}

static int firmware_control(int fd, uint64_t bytes)
{
	struct realm_gpu_alloc alloc = { .size = bytes };
	struct realm_gpu_call result;
	void *mapping;
	int ret = 1;

	if (success(fd, REALM_GPU_VERSION, 0, 0, 0, 0, 0, 0, &result) ||
	    !(result.result[1] & REALM_GPU_CAP_CONTROL_MEMORY))
		return 1;
	if (ioctl(fd, REALM_GPU_CONTROL_ALLOC, &alloc)) {
		perror("REALM_GPU_CONTROL_ALLOC");
		return 1;
	}
	if (!alloc.handle || alloc.fd < 0)
		goto out;
	errno = 0;
	mapping = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, alloc.fd, 0);
	if (mapping != MAP_FAILED) {
		munmap(mapping, PAGE);
		fputs("control donation unexpectedly permits CPU mmap\n", stderr);
		goto out;
	}
	if (errno != EACCES) {
		perror("control mmap denial");
		goto out;
	}
	if (success(fd, REALM_GPU_FW_CONTROL_BIND, alloc.handle, 0, 0, 0, 0, 0, &result) ||
	    result.result[0] != bytes || result.result[1] != bytes / PAGE)
		goto out;
	output(&result);
	puts("GPU_CONTROL_ARENA=BOUND CPU_MMAP=DENIED GPU_EXECUTION=NOT_RUN BACKING_RETAINED_UNTIL_TRUSTED_RESET");
	ret = 0;
out:
	/* Successful binding owns the backing now. Closing its lifetime fd must
	 * retain all pages until trusted reset, not restore CPU access early.
	 */
	if (alloc.fd >= 0)
		close(alloc.fd);
	return ret;
}

static int service_bootstrap(int fd, const char *image)
{
	struct realm_gpu_call state;

	/* This does not revoke a running native driver. The metadata-only
	 * panthor.rmm_service mode must have handed MMIO to RMM at probe time,
	 * or an operator must already have stopped/unbound the native driver.
	 * Never reset or silently restart an existing, partially used instance.
	 */
	if (success(fd, REALM_GPU_FW_INSPECT, 0, 0, 0, 0, 0, 0, &state))
		return 1;
	if (state.result[0] == 7)
		goto configured;
	if (state.result[0] != 0) {
		fputs("service bootstrap requires an empty or already configured RMM instance; partial state retained\n", stderr);
		return 1;
	}
	if (firmware_snapshot(fd, image) ||
	    success(fd, REALM_GPU_FW_PREPARE, 0, 0, 0, 0, 0, 0, &state) ||
	    state.result[0] != 3 ||
	    firmware_control(fd, REALM_GPU_CONTROL_MAX_PAGES * PAGE) ||
	    success(fd, REALM_GPU_FW_BOOT, 0, 0, 0, 0, 0, 0, &state) ||
	    state.result[0] != 5 ||
	    success(fd, REALM_GPU_FW_CONFIGURE, 0, 0, 0, 0, 0, 0, &state) ||
	    state.result[0] != 7)
		return 1;
configured:
	output(&state);
	puts("GPU_RMM_SERVICE_BOOTSTRAP=CONFIGURED GPU_TASK_EXECUTION=NOT_RUN");
	return 0;
}

static int release_group(int fd, uint64_t group)
{
	struct realm_gpu_call result;

	for (unsigned int i = 0; i < 16; i++) {
		if (call(fd, REALM_GPU_GROUP_DESTROY, group, 0, 0, 0, 0, 0, &result))
			return -1;
		if (!result.status)
			return 0;
		if (result.status != 4)
			return -1;
	}
	return -1;
}

static int task_prelaunch_selftest(int fd, uint64_t channel, uint64_t context, uint64_t group, uint64_t streams)
{
	struct realm_gpu_alloc alloc = { .channel = channel, .size = 2 * PAGE,
		.access = REALM_GPU_READ | REALM_GPU_WRITE };
	struct realm_gpu_call result;
	uint64_t token = 0, retired;
	int ret = 1;
	bool mapped = false;

	if (ioctl(fd, REALM_GPU_ALLOC, &alloc))
		return 1;
	if (success(fd, REALM_GPU_MAP, context, alloc.handle, 0, BASE, 2,
		REALM_GPU_READ, &result))
		goto out;
	mapped = true;
	if (success(fd, REALM_GPU_TASK_STAGE, group, channel, 0, BASE + PAGE - 8, 16, 7, &result))
		goto out;
	token = result.result[0];
	if (!token || result.result[1] || result.result[2] || result.result[3])
		goto out;
	if (call(fd, REALM_GPU_UNMAP, context, BASE, 2, 0, 0, 0, &result) || result.status != 2)
		goto out;
	if (call(fd, REALM_GPU_GROUP_DESTROY, group, 0, 0, 0, 0, 0, &result) || result.status != 2)
		goto out;
	if (call(fd, REALM_GPU_TASK_VALIDATE, token, channel, context, group, 0, 0, &result) ||
	    result.status != 1)
		goto out; /* Actual Client cannot impersonate the service validator. */
	if (call(fd, REALM_GPU_TASK_PROGRESS, token, channel, 0, 0, 0, 0, &result) ||
	    result.status != 2 || result.result[0])
		goto out; /* Staging is neither execution nor a valid progress proof. */
	if (call(fd, REALM_GPU_TASK_PUBLISH, token, channel, 1, 0, 0, 0, &result) ||
	    result.status != 2 || result.result[0])
		goto out; /* Publication cannot skip trusted PREPARE and cache READY. */
	if (success(fd, REALM_GPU_TASK_CANCEL, token, 0, 0, 0, 0, 0, &result))
		goto out;
	retired = token;
	token = 0;
	if (call(fd, REALM_GPU_TASK_CANCEL, retired, 0, 0, 0, 0, 0, &result) || result.status != 1)
		goto out;
	if (call(fd, REALM_GPU_TASK_PROGRESS, retired, channel, 0, 0, 0, 0, &result) || result.status != 1)
		goto out;
	/* Same diagnostic exercises userspace -> private kernel page -> RMM array
	 * snapshot. No command is launched, even when a real Realm runs this test.
	 */
	struct realm_gpu_task_command commands[REALM_GPU_TASK_BATCH_MAX] = {
		{ .start = BASE, .bytes = 8 }, { .start = BASE + PAGE, .bytes = 8 }
	};
	commands[1].queue = streams > 1 ? 1 : 0;
	commands[5].pad = 1;
	if (call(fd, REALM_GPU_TASK_STAGE_BATCH, group, (uintptr_t)commands, channel,
		REALM_GPU_TASK_BATCH_MAX, 0, 0, &result) || result.status != 1)
		goto out;
	/* Bad later member must leave mappings mutable. */
	if (success(fd, REALM_GPU_UNMAP, context, BASE, 2, 0, 0, 0, &result))
		goto out;
	mapped = false;
	if (success(fd, REALM_GPU_MAP, context, alloc.handle, 0, BASE, 2, REALM_GPU_READ, &result))
		goto out;
	mapped = true;
	commands[5].pad = 0;
	if (success(fd, REALM_GPU_TASK_STAGE_BATCH, group, (uintptr_t)commands, channel,
		REALM_GPU_TASK_BATCH_MAX, REALM_GPU_TASK_DEFERRED, 0, &result))
		goto out;
	token = result.result[0];
	if (!token || result.result[1] != REALM_GPU_TASK_BATCH_MAX ||
	    result.result[2] != (streams > 1 ? 3U : 1U) || result.result[3])
		goto out;
	memset(commands, 0xff, sizeof(commands));
	if (call(fd, REALM_GPU_TASK_PUBLISH, token, channel,
		(1U << REALM_GPU_TASK_BATCH_MAX) - 1U, 0, 0, 0, &result) ||
	    result.status != 2 || result.result[0])
		goto out;
	if (call(fd, REALM_GPU_UNMAP, context, BASE, 2, 0, 0, 0, &result) || result.status != 2)
		goto out;
	if (success(fd, REALM_GPU_TASK_CANCEL, token, 0, 0, 0, 0, 0, &result))
		goto out;
	token = 0;
	ret = 0;
out:
	if (token && (call(fd, REALM_GPU_TASK_CANCEL, token, 0, 0, 0, 0, 0, &result) || result.status)) {
		fputs("prelaunch task retained; context and backing cannot be retired\n", stderr);
		ret = 1;
	}
	if (mapped && (call(fd, REALM_GPU_UNMAP, context, BASE, 2, 0, 0, 0, &result) || result.status)) {
		fputs("prelaunch task mapping retained\n", stderr);
		ret = 1;
	}
	close(alloc.fd);
	printf("GPU_TASK_STAGING=%s actual Client authorization, single and six-member batch, mapping freeze, atomic rejection, prelaunch cancellation and old token; no GPU execution\n",
		ret ? "FAIL" : "PASS");
	return ret;
}

static int group_selftest(int fd, uint64_t channel, uint64_t streams)
{
	struct realm_gpu_call result;
	uint64_t context = 0, group = 0, retired;
	struct realm_gpu_queue_config queues[REALM_GPU_MAX_GROUP_STREAMS] = { 0 };
	int ret = 1;

	if (success(fd, REALM_GPU_VERSION, 0, 0, 0, 0, 0, 0, &result) ||
	    (result.result[1] & (REALM_GPU_CAP_GROUP_MEMORY | REALM_GPU_CAP_GROUP_RINGS |
		REALM_GPU_CAP_TASK_STAGING | REALM_GPU_CAP_TASK_BATCH | REALM_GPU_CAP_TASK_PROGRESS |
		REALM_GPU_CAP_TASK_PUBLISH)) !=
		(REALM_GPU_CAP_GROUP_MEMORY | REALM_GPU_CAP_GROUP_RINGS | REALM_GPU_CAP_TASK_STAGING |
		 REALM_GPU_CAP_TASK_BATCH | REALM_GPU_CAP_TASK_PROGRESS | REALM_GPU_CAP_TASK_PUBLISH) ||
	    !streams || streams > REALM_GPU_MAX_GROUP_STREAMS)
		return 1;
	if (success(fd, REALM_GPU_CONTEXT_CREATE, channel, 0, 0, 0, 0, 0, &result))
		return 1;
	context = result.result[0];
	if (call(fd, REALM_GPU_GROUP_CREATE, context, channel, streams, 0, 0, 0, &result))
		goto out;
	/* A failed clearing may still return a quarantined cleanup handle. */
	group = result.result[0];
	if (result.status || !group || result.result[1] != streams ||
	    !result.result[2] || result.result[3] <= streams * 2)
		goto out;
	output(&result);
	for (uint64_t i = 0; i < streams; i++)
		queues[i].ring_bytes = 4096;
	if (success(fd, REALM_GPU_GROUP_CONFIGURE, group, (uintptr_t)queues,
		channel, streams, 0, 0, &result) || result.result[0] != streams ||
	    result.result[1] != streams + 1)
		goto out;
	if (success(fd, REALM_GPU_GROUP_INSPECT, group, channel, 0, 0, 0, 0, &result) ||
	    result.result[0] != 1 || result.result[1] != streams)
		goto out;
	if (call(fd, REALM_GPU_CONTEXT_DESTROY, context, 0, 0, 0, 0, 0, &result) ||
	    result.status != 2)
		goto out; /* The real context must remain held by its group. */
	if (call(fd, REALM_GPU_GROUP_INSPECT, group, 0, 0, 0, 0, 0, &result) ||
	    result.status != 1)
		goto out; /* An unauthenticated channel cannot inspect the group. */
	if (call(fd, REALM_GPU_GROUP_VALIDATE, group, channel, context, streams, 0, 0, &result) ||
	    result.status != 1)
		goto out; /* Only the isolated service may import a Client group. */
	if (call(fd, REALM_GPU_GROUP_DESTROY, group ^ UINT64_C(0x10000),
		0, 0, 0, 0, 0, &result) || result.status != 1)
		goto out;
	if (task_prelaunch_selftest(fd, channel, context, group, streams))
		goto out;
	if (release_group(fd, group))
		goto out;
	retired = group;
	group = 0;
	if (call(fd, REALM_GPU_GROUP_INSPECT, retired, channel, 0, 0, 0, 0, &result) ||
	    result.status != 1)
		goto out;
	if (success(fd, REALM_GPU_CONTEXT_DESTROY, context, 0, 0, 0, 0, 0, &result))
		goto out;
	context = 0;
	ret = 0;
out:
	if (group && release_group(fd, group))
		fputs("group cleanup retained; trusted reset may be required\n", stderr);
	if (context && (call(fd, REALM_GPU_CONTEXT_DESTROY, context, 0, 0, 0, 0, 0, &result) || result.status))
		fputs("context retained while group cleanup is uncertain\n", stderr);
	printf("GPU_GROUP_MEMORY=%s context hold, authenticated channel, stale handles and typed retirement\n",
	       ret ? "FAIL" : "PASS");
	puts("GPU_PRIVATE_EXECUTION=NOT_RUN CPU_REALM_ISOLATION=NOT_RUN HARDWARE_GPC=NOT_RUN");
	return ret;
}

static int selftest(int fd, uint64_t channel, unsigned long pages)
{
	struct realm_gpu_call result;
	struct realm_gpu_alloc alloc = { .channel = channel, .size = pages * PAGE,
		.access = REALM_GPU_READ | REALM_GPU_WRITE };
	uint64_t context = 0;
	uint64_t authorization = 0;
	uint64_t *memory = MAP_FAILED, *alias = MAP_FAILED;
	unsigned long index, mapped = 0;
	int backing_fd = -1, ret = 1;
	void *bad;

	if (success(fd, REALM_GPU_VERSION, 0, 0, 0, 0, 0, 0, &result))
		return 1;
	if (result.result[0] != REALM_GPU_ABI ||
	    (result.result[1] & (REALM_GPU_CAP_REGISTRATION | REALM_GPU_CAP_PAGE_TABLES |
		REALM_GPU_CAP_MAPPING_AUTH | REALM_GPU_CAP_CONTROL_HANDOFF |
		REALM_GPU_CAP_PT_INSTALL | REALM_GPU_CAP_UNMAP_BO)) !=
		(REALM_GPU_CAP_REGISTRATION | REALM_GPU_CAP_PAGE_TABLES |
		 REALM_GPU_CAP_MAPPING_AUTH | REALM_GPU_CAP_CONTROL_HANDOFF |
		 REALM_GPU_CAP_PT_INSTALL | REALM_GPU_CAP_UNMAP_BO)) {
		fputs("required RMM ABI/capabilities unavailable\n", stderr);
		return 1;
	}
	if (ioctl(fd, REALM_GPU_ALLOC, &alloc)) {
		perror("REALM_GPU_ALLOC");
		return 1;
	}
	backing_fd = alloc.fd;
	printf("PRIVATE_BO handle=%" PRIu64 " bytes=%" PRIu64 "\n",
	       (uint64_t)alloc.handle, (uint64_t)alloc.size);
	if (!alloc.handle || alloc.fd < 0 || alloc.size != pages * PAGE)
		goto cleanup;
	memory = mmap(NULL, alloc.size, PROT_READ | PROT_WRITE,
		      MAP_SHARED, backing_fd, 0);
	if (memory == MAP_FAILED) {
		perror("mmap private BO");
		goto cleanup;
	}
	for (index = 0; index < pages; index++) {
		uint64_t *page = memory + index * PAGE / sizeof(*memory);
		unsigned long word;

		for (word = 0; word < PAGE / sizeof(*page); word++)
			if (page[word]) {
				fputs("private backing was not zero initialized\n", stderr);
				goto cleanup;
			}
		page[0] = 0xa55a0000UL + index;
	}
	alias = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, backing_fd,
		     (pages - 1) * PAGE);
	if (alias == MAP_FAILED || *alias != 0xa55a0000UL + pages - 1)
		goto cleanup;
	*alias = 0x12345678UL;
	if (memory[(pages - 1) * PAGE / sizeof(*memory)] != *alias)
		goto cleanup;
	munmap(alias, PAGE);
	alias = MAP_FAILED;

	bad = mmap(NULL, PAGE, PROT_READ, MAP_SHARED, backing_fd, alloc.size);
	if (bad != MAP_FAILED) {
		munmap(bad, PAGE);
		fputs("out-of-range mmap accepted\n", stderr);
		goto cleanup;
	}
	bad = mmap(NULL, PAGE, PROT_READ, MAP_PRIVATE, backing_fd, 0);
	if (bad != MAP_FAILED) {
		munmap(bad, PAGE);
		fputs("private/COW mmap accepted\n", stderr);
		goto cleanup;
	}
	bad = mmap(NULL, PAGE, PROT_READ | PROT_EXEC, MAP_SHARED, backing_fd, 0);
	if (bad != MAP_FAILED) {
		munmap(bad, PAGE);
		fputs("executable mmap accepted\n", stderr);
		goto cleanup;
	}
	if (!mprotect(memory, PAGE, PROT_READ | PROT_EXEC)) {
		fputs("mprotect bypassed non-executable backing policy\n", stderr);
		goto cleanup;
	}
	errno = 0;
	if (call(fd, REALM_GPU_BO_DESTROY, alloc.handle, 0, 0, 0, 0, 0, &result) != -1 ||
	    errno != EBUSY) {
		fputs("diagnostic ioctl destroyed a kernel-owned BO\n", stderr);
		goto cleanup;
	}
	if (success(fd, REALM_GPU_CONTEXT_CREATE, channel, 0, 0, 0, 0, 0, &result))
		goto cleanup;
	context = result.result[0];
	if (!context)
		goto cleanup;
	if (success(fd, REALM_GPU_MAP_AUTHORIZE, context, alloc.handle, 0, BASE,
		    pages, REALM_GPU_READ | REALM_GPU_WRITE, &result))
		goto cleanup;
	authorization = result.result[0];
	if (!authorization ||
	    call(fd, REALM_GPU_CONTEXT_DESTROY, context, 0, 0, 0, 0, 0, &result) ||
	    result.status != 2) {
		fputs("pending mapping authorization failed to retain context\n", stderr);
		goto cleanup;
	}
	if (success(fd, REALM_GPU_MAP_CANCEL, authorization, 0, 0, 0, 0, 0, &result))
		goto cleanup;
	if (call(fd, REALM_GPU_MAP_CANCEL, authorization, 0, 0, 0, 0, 0, &result) ||
	    result.status != 1) {
		fputs("cancelled mapping authorization remained usable\n", stderr);
		goto cleanup;
	}
	authorization = 0;
	while (mapped < pages) {
		unsigned long count = pages - mapped;

		if (count > REALM_GPU_BATCH_PAGES)
			count = REALM_GPU_BATCH_PAGES;
		if (success(fd, REALM_GPU_MAP, context, alloc.handle, mapped * PAGE,
			    BASE + mapped * PAGE, count, REALM_GPU_READ | REALM_GPU_WRITE,
			    &result) || result.result[0] != count * PAGE)
			goto cleanup;
		mapped += count;
	}
	if (success(fd, REALM_GPU_QUERY, context, BASE, 0, 0, 0, 0, &result) ||
	    result.result[0] != pages || result.result[1] || result.result[2])
		goto cleanup;
	/* Exact cleanup is idempotent while the BO is still live. A wrong page
	 * offset must leave the real mapped prefix intact, rather than removing
	 * a leaf on address alone. These are CPU/RSI probes, not GPU execution.
	 */
	if (pages > 1 && (call(fd, REALM_GPU_UNMAP_BO, context, alloc.handle, PAGE,
			      BASE, 1, 0, &result) || result.status != 2))
		goto cleanup;
	if (success(fd, REALM_GPU_UNMAP_BO, context, alloc.handle, 0, BASE, 1, 0, &result) ||
	    result.result[0] != PAGE ||
	    success(fd, REALM_GPU_UNMAP_BO, context, alloc.handle, 0, BASE, 1, 0, &result) ||
	    result.result[0] != PAGE ||
	    success(fd, REALM_GPU_QUERY, context, BASE, 0, 0, 0, 0, &result) ||
	    result.result[0] != pages - 1 ||
	    success(fd, REALM_GPU_MAP, context, alloc.handle, 0, BASE, 1,
		    REALM_GPU_READ | REALM_GPU_WRITE, &result))
		goto cleanup;

	/* Close fd while CPU VMA still holds the backing, then remove the VMA
	 * while the RMM context still maps it. Kernel must retain the pages.
	 */
	close(backing_fd);
	backing_fd = -1;
	if (memory[0] != 0xa55a0000UL && pages != 1)
		goto cleanup;
	munmap(memory, alloc.size);
	memory = MAP_FAILED;
	if (success(fd, REALM_GPU_QUERY, context, BASE, 0, 0, 0, 0, &result) ||
	    result.result[0] != pages)
		goto cleanup;
	while (mapped) {
		unsigned long count = mapped > REALM_GPU_BATCH_PAGES ? REALM_GPU_BATCH_PAGES : mapped;

		if (success(fd, REALM_GPU_UNMAP, context, BASE + (mapped - count) * PAGE,
			    count, 0, 0, 0, &result))
			goto cleanup;
		mapped -= count;
	}
	/* UNMAP reaps the last closed BO only after RMM authorizes destroy. */
	if (call(fd, REALM_GPU_MAP, context, alloc.handle, 0, BASE, 1,
		 REALM_GPU_READ, &result) || result.status != 1) {
		fputs("stale BO remained usable after trusted cleanup\n", stderr);
		goto cleanup;
	}
	if (success(fd, REALM_GPU_CONTEXT_DESTROY, context, 0, 0, 0, 0, 0, &result))
		goto cleanup;
	context = 0;
	ret = 0;
	puts("GPU_PRIVATE_GUEST=PASS allocation, zeroing, mmap bounds, non-executable CPU mapping, registration batches, real PT construction, retained backing, stale handles");
	puts("GPU_PRIVATE_EXECUTION=NOT_RUN CPU_REALM_ISOLATION=NOT_RUN HARDWARE_GPC=NOT_RUN");
cleanup:
	if (ret)
		fputs("GPU_PRIVATE_GUEST=FAIL\n", stderr);
	if (authorization &&
	    success(fd, REALM_GPU_MAP_CANCEL, authorization, 0, 0, 0, 0, 0, &result))
		fputs("mapping authorization retained after failed cleanup\n", stderr);
	if (alias != MAP_FAILED)
		munmap(alias, PAGE);
	if (memory != MAP_FAILED)
		munmap(memory, alloc.size);
	while (mapped) {
		unsigned long count = mapped > REALM_GPU_BATCH_PAGES ? REALM_GPU_BATCH_PAGES : mapped;

		if (success(fd, REALM_GPU_UNMAP, context, BASE + (mapped - count) * PAGE,
			    count, 0, 0, 0, &result))
			break;
		mapped -= count;
	}
	if (context && success(fd, REALM_GPU_CONTEXT_DESTROY, context, 0, 0, 0, 0, 0, &result))
		fputs("context retained: cleanup did not prove revocation\n", stderr);
	if (backing_fd >= 0)
		close(backing_fd);
	return ret;
}

static int drm_bind(int fd, uint32_t vm, uint32_t bo, uint64_t va,
		uint64_t offset, uint64_t size, uint32_t flags)
{
	struct drm_panthor_vm_bind_op op = {
		.flags = flags, .bo_handle = bo, .va = va, .bo_offset = offset, .size = size,
	};
	struct drm_panthor_vm_bind bind = { .vm_id = vm,
		.ops = { .count = 1, .stride = sizeof(op), .array = (uint64_t)(uintptr_t)&op },
	};

	return ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind);
}

/* Exercise real Client DRM syncobjs without requiring a GPU task. A CPU
 * SIGNAL is a local userspace action, not a claim of trusted GPU completion.
 * Legacy WAIT layouts also exercise DRM core's smaller-ioctl compatibility.
 */
static int drm_private_sync_selftest(int fd)
{
	struct drm_syncobj_create binary = { 0 }, timeline = { 0 }, imported = { 0 };
	struct drm_syncobj_handle handle = { .fd = -1 };
	struct drm_syncobj_destroy destroy;
	struct drm_syncobj_transfer transfer = { 0 };
	struct drm_syncobj_array array = { .count_handles = 1 };
	struct drm_syncobj_timeline_array timelines = { .count_handles = 1 };
	struct drm_syncobj_wait wait = { .count_handles = 1, .timeout_nsec = 0,
		.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT };
	struct drm_syncobj_timeline_wait twait = { .count_handles = 1, .timeout_nsec = 0,
		.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT };
	struct {
		uint64_t handles;
		int64_t timeout_nsec;
		uint32_t count_handles, flags, first_signaled, pad;
	} legacy = { .count_handles = 1, .timeout_nsec = 0 };
	struct {
		uint64_t handles, points;
		int64_t timeout_nsec;
		uint32_t count_handles, flags, first_signaled, pad;
	} tlegacy = { .count_handles = 1, .timeout_nsec = 0 };
	struct pollfd pollfd = { .fd = -1, .events = POLLIN };
	uint32_t id;
	uint64_t point = 9;
	int ret = 1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &binary) || !binary.handle ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &timeline) || !timeline.handle ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &imported) || !imported.handle)
		goto out;
	id = binary.handle;
	wait.handles = (uintptr_t)&id;
	errno = 0;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) != -1 || errno != ETIME)
		goto out;
	array.handles = (uintptr_t)&id;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_SIGNAL, &array) ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait))
		goto out;
	legacy.handles = (uintptr_t)&id;
	if (ioctl(fd, DRM_IOWR(0xC3, typeof(legacy)), &legacy))
		goto out;
	handle.handle = binary.handle;
	handle.flags = DRM_SYNCOBJ_HANDLE_TO_FD_FLAGS_EXPORT_SYNC_FILE;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD, &handle) || handle.fd < 0)
		goto out;
	pollfd.fd = handle.fd;
	if (poll(&pollfd, 1, 0) != 1 || !(pollfd.revents & POLLIN))
		goto out;
	handle.handle = imported.handle;
	handle.flags = DRM_SYNCOBJ_FD_TO_HANDLE_FLAGS_IMPORT_SYNC_FILE;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE, &handle) ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_RESET, &array))
		goto out;
	errno = 0;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) != -1 || errno != ETIME)
		goto out;
	id = imported.handle;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) ||
	    poll(&pollfd, 1, 0) != 1 || !(pollfd.revents & POLLIN))
		goto out; /* Resetting the source cannot change an exported snapshot. */
	id = timeline.handle;
	timelines.handles = (uintptr_t)&id;
	timelines.points = (uintptr_t)&point;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_SIGNAL, &timelines))
		goto out;
	point = 0;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_QUERY, &timelines) || point != 9)
		goto out;
	twait.handles = (uintptr_t)&id;
	twait.points = (uintptr_t)&point;
	point = 8;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &twait))
		goto out;
	tlegacy.handles = (uintptr_t)&id;
	tlegacy.points = (uintptr_t)&point;
	if (ioctl(fd, DRM_IOWR(0xCA, typeof(tlegacy)), &tlegacy))
		goto out;
	point = 10;
	errno = 0;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &twait) != -1 || errno != ETIME)
		goto out;
	transfer.src_handle = timeline.handle;
	transfer.src_point = 9;
	transfer.dst_handle = binary.handle;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TRANSFER, &transfer))
		goto out;
	id = binary.handle;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait))
		goto out;
	ret = 0;
out:
	if (ret)
		perror("private local DRM syncobj probe");
	if (handle.fd >= 0)
		close(handle.fd);
	uint32_t handles[] = { binary.handle, timeline.handle, imported.handle };
	for (unsigned int i = 0; i < sizeof(handles) / sizeof(handles[0]); i++) {
		if (!handles[i])
			continue;
		destroy = (struct drm_syncobj_destroy) { .handle = handles[i] };
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy))
			ret = 1;
	}
	printf("GPU_PRIVATE_LOCAL_SYNCOBJ=%s binary/timeline/legacy wait, CPU signal, reset, query, transfer and immutable sync_file; GPU_EXECUTION=NOT_RUN\n",
		ret ? "FAIL" : "PASS");
	return ret;
}

/* Normal asynchronous DRM VM_BIND, including dependencies within one batch.
 * The actual Client worker must emit local fences only after RMM checks.
 * Uses one temporary mapping at BASE, removed before the BO/mmap test.
 */
static int drm_private_async_bind_selftest(int fd, uint32_t vm, uint32_t bo)
{
	struct drm_syncobj_create input = { .flags = DRM_SYNCOBJ_CREATE_SIGNALED };
	struct drm_syncobj_create timeline = { 0 }, binary = { 0 };
	struct drm_panthor_sync_op syncs[5] = { 0 };
	struct drm_panthor_vm_bind_op ops[3] = { 0 };
	struct drm_panthor_vm_bind bind = { .vm_id = vm, .flags = DRM_PANTHOR_VM_BIND_ASYNC,
		.ops = { .count = 3, .stride = sizeof(ops[0]), .array = (uintptr_t)ops } };
	struct drm_syncobj_timeline_wait wait = { .count_handles = 1,
		.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT };
	struct drm_syncobj_timeline_array query = { .count_handles = 1 };
	struct drm_syncobj_handle exported = { .fd = -1,
		.flags = DRM_SYNCOBJ_HANDLE_TO_FD_FLAGS_EXPORT_SYNC_FILE };
	struct sync_file_info info = { 0 };
	struct timespec now;
	uint64_t point = 2;
	uint32_t handle;
	int ret = 1;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &input) ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &timeline) ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &binary))
		goto out;
	syncs[0] = (struct drm_panthor_sync_op) { .handle = input.handle };
	syncs[1] = (struct drm_panthor_sync_op) { .handle = timeline.handle, .timeline_value = 1,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL | DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ };
	syncs[2] = (struct drm_panthor_sync_op) { .handle = timeline.handle, .timeline_value = 1,
		.flags = DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ };
	syncs[3] = (struct drm_panthor_sync_op) { .handle = binary.handle, .flags = DRM_PANTHOR_SYNC_OP_SIGNAL };
	syncs[4] = (struct drm_panthor_sync_op) { .handle = timeline.handle, .timeline_value = 2,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL | DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ };
	ops[0] = (struct drm_panthor_vm_bind_op) { .bo_handle = bo, .va = BASE, .size = PAGE,
		.flags = DRM_PANTHOR_VM_BIND_OP_MAP_NOEXEC,
		.syncs = { .count = 2, .stride = sizeof(syncs[0]), .array = (uintptr_t)&syncs[0] } };
	ops[1] = (struct drm_panthor_vm_bind_op) { .va = BASE, .size = PAGE,
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP,
		.syncs = { .count = 2, .stride = sizeof(syncs[0]), .array = (uintptr_t)&syncs[2] } };
	ops[2] = (struct drm_panthor_vm_bind_op) { .flags = DRM_PANTHOR_VM_BIND_OP_TYPE_SYNC_ONLY,
		.syncs = { .count = 1, .stride = sizeof(syncs[0]), .array = (uintptr_t)&syncs[4] } };
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) || clock_gettime(CLOCK_MONOTONIC, &now))
		goto out;
	handle = timeline.handle;
	wait.handles = (uintptr_t)&handle;
	wait.points = (uintptr_t)&point;
	wait.timeout_nsec = (int64_t)now.tv_sec * 1000000000 + now.tv_nsec + INT64_C(60000000000);
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &wait))
		goto out;
	query.handles = (uintptr_t)&handle;
	query.points = (uintptr_t)&point;
	point = 0;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_QUERY, &query) || point != 2)
		goto out;
	/* A successful DRM wait can also wake on an error fence. Inspect the
	 * exact UNMAP fence's status so an asynchronous failure cannot PASS.
	 */
	exported.handle = binary.handle;
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD, &exported) || exported.fd < 0 ||
	    ioctl(exported.fd, SYNC_IOC_FILE_INFO, &info) || info.status != 1)
		goto out;
	ret = 0;
out:
	if (ret)
		perror("private asynchronous VM_BIND probe");
	if (exported.fd >= 0)
		close(exported.fd);
	if (drm_bind(fd, vm, 0, BASE, 0, PAGE, DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP))
		ret = 1;
	uint32_t handles[] = { input.handle, timeline.handle, binary.handle };
	for (unsigned int i = 0; i < sizeof(handles) / sizeof(handles[0]); i++) {
		struct drm_syncobj_destroy destroy = { .handle = handles[i] };

		if (handles[i] && ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy))
			ret = 1;
	}
	printf("GPU_PRIVATE_ASYNC_BIND=%s normal DRM MAP/UNMAP/SYNC_ONLY, Client-local dependencies and fences; GPU_EXECUTION=NOT_RUN\n",
		ret ? "FAIL" : "PASS");
	return ret;
}

/* Normal DRM initial heap creation, with no GPU execution or OOM growth. */
static int drm_private_heap_selftest(int fd, uint32_t vm, uint64_t user_end)
{
	struct drm_panthor_tiler_heap_create heap = { .vm_id = vm, .initial_chunk_count = 1,
		.chunk_size = 8U * 1024U * 1024U, .max_chunks = 8, .target_in_flight = 3 };
	struct drm_panthor_tiler_heap_destroy destroy = { 0 };
	struct drm_panthor_tiler_heap_create bad = heap;
	int ret = 1;

	bad.initial_chunk_count = 0;
	if (!ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE, &bad)) {
		fputs("private heap accepted zero chunks\n", stderr);
		destroy.handle = bad.handle;
		ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY, &destroy);
		goto out;
	}
	if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE, &heap))
		goto out;
	destroy.handle = heap.handle;
	if (!heap.handle || heap.tiler_heap_ctx_gpu_va < user_end ||
	    heap.tiler_heap_ctx_gpu_va % PAGE || heap.first_heap_chunk_gpu_va % PAGE ||
	    heap.first_heap_chunk_gpu_va != heap.tiler_heap_ctx_gpu_va + PAGE)
		goto cleanup;
	if (!drm_bind(fd, vm, 0, heap.tiler_heap_ctx_gpu_va, 0, PAGE,
		      DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP)) {
		fputs("private user VM_BIND modified kernel heap VA\n", stderr);
		goto cleanup;
	}
	if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY, &destroy))
		goto cleanup;
	destroy.handle = 0;
	struct drm_panthor_tiler_heap_destroy again = { .handle = heap.handle };
	if (!ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY, &again)) {
		fputs("private heap duplicate destroy accepted\n", stderr);
		goto out;
	}
	ret = 0;
	goto out;
cleanup:
	if (destroy.handle && ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY, &destroy))
		perror("private heap cleanup");
out:
	printf("GPU_PRIVATE_INITIAL_HEAP=%s normal DRM create/destroy, cross-batch initial storage, kernel VA refusal; GPU_EXECUTION_AND_DYNAMIC_GROWTH=NOT_RUN\n",
		ret ? "FAIL" : "PASS");
	return ret;
}

/* Real frontend/RPC/native VM_BIND plumbing, with execution deliberately absent.
 * Require the private-mode parameter so the existing shared path cannot PASS.
 */
static int drm_selftest(const char *device, unsigned long pages)
{
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_bo_create bo = { .size = pages * PAGE };
	struct drm_panthor_bo_mmap_offset offset = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_gem_close close_bo = { 0 };
	uint64_t *memory = MAP_FAILED, *alias = MAP_FAILED;
	unsigned long page;
	int fd, other_fd = -1, ret = 1, mapped = 0;
	void *bad;

	if (private_mode("client"))
		return 1;
	fd = open(device, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror(device);
		return 1;
	}
	if (drm_private_sync_selftest(fd))
		goto cleanup;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) || !vm.id || !vm.user_va_range) {
		perror("private VM_CREATE");
		goto cleanup;
	}
	if (drm_private_heap_selftest(fd, vm.id, vm.user_va_range))
		goto cleanup;
	bo.exclusive_vm_id = vm.id;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bo) || !bo.handle || bo.size != pages * PAGE) {
		perror("private BO_CREATE");
		goto cleanup;
	}
	if (drm_private_async_bind_selftest(fd, vm.id, bo.handle))
		goto cleanup;
	offset.handle = bo.handle;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET, &offset)) {
		perror("private BO_MMAP_OFFSET");
		goto cleanup;
	}
	memory = mmap(NULL, bo.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, offset.offset);
	if (memory == MAP_FAILED) {
		perror("private DRM mmap");
		goto cleanup;
	}
	for (page = 0; page < pages; page++) {
		uint64_t *words = memory + page * PAGE / sizeof(*memory);
		unsigned long i;

		for (i = 0; i < PAGE / sizeof(*words); i++)
			if (words[i]) {
				fputs("private DRM BO is not zeroed\n", stderr);
				goto cleanup;
			}
		words[0] = 0xa55a0000UL + page;
	}
	alias = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		     offset.offset + (pages - 1) * PAGE);
	if (alias == MAP_FAILED || *alias != 0xa55a0000UL + pages - 1)
		goto cleanup;
	bad = mmap(NULL, PAGE, PROT_READ | PROT_EXEC, MAP_SHARED, fd, offset.offset);
	if (bad != MAP_FAILED) {
		munmap(bad, PAGE);
		fputs("executable private DRM mmap accepted\n", stderr);
		goto cleanup;
	}
	bad = mmap(NULL, PAGE, PROT_READ, MAP_PRIVATE, fd, offset.offset);
	if (bad != MAP_FAILED) {
		munmap(bad, PAGE);
		fputs("COW private DRM mmap accepted\n", stderr);
		goto cleanup;
	}
	if (!mprotect(memory, PAGE, PROT_READ | PROT_EXEC)) {
		fputs("private DRM mprotect granted execution\n", stderr);
		goto cleanup;
	}
	other_fd = open(device, O_RDWR | O_CLOEXEC);
	if (other_fd < 0)
		goto cleanup;
	bad = mmap(NULL, PAGE, PROT_READ, MAP_SHARED, other_fd, offset.offset);
	if (bad != MAP_FAILED) {
		munmap(bad, PAGE);
		fputs("private DRM mapping crossed file ownership\n", stderr);
		goto cleanup;
	}
	close(other_fd);
	other_fd = -1;
	if (drm_bind(fd, vm.id, bo.handle, BASE, 0, bo.size,
		     DRM_PANTHOR_VM_BIND_OP_TYPE_MAP | DRM_PANTHOR_VM_BIND_OP_MAP_NOEXEC)) {
		perror("private VM_BIND map");
		goto cleanup;
	}
	mapped = 1;
	if (!drm_bind(fd, vm.id, bo.handle, BASE + bo.size + PAGE, bo.size, PAGE,
		      DRM_PANTHOR_VM_BIND_OP_TYPE_MAP)) {
		fputs("private VM_BIND accepted out-of-range backing\n", stderr);
		goto cleanup;
	}
	/* Replacing one page exercises split/remap metadata and exact RMM leaves. */
	if (drm_bind(fd, vm.id, bo.handle, BASE, 0, PAGE,
		     DRM_PANTHOR_VM_BIND_OP_TYPE_MAP | DRM_PANTHOR_VM_BIND_OP_MAP_READONLY |
		     DRM_PANTHOR_VM_BIND_OP_MAP_NOEXEC)) {
		perror("private VM_BIND remap");
		goto cleanup;
	}
	if (pages >= 8) {
		struct drm_panthor_vm_bind_op ops[8] = { 0 };
		struct drm_panthor_vm_bind bind = { .vm_id = vm.id,
			.ops = { .count = 8, .stride = sizeof(ops[0]),
				 .array = (uint64_t)(uintptr_t)ops },
		};
		unsigned int i;

		/* Exercise every operation slot and nonzero page offsets in ABI 3.
		 * These replace mappings already covered by the cleanup range.
		 */
		for (i = 0; i < 8; i++) {
			ops[i].bo_handle = bo.handle;
			ops[i].bo_offset = i * PAGE;
			ops[i].va = BASE + i * PAGE;
			ops[i].size = PAGE;
			ops[i].flags = DRM_PANTHOR_VM_BIND_OP_TYPE_MAP |
				DRM_PANTHOR_VM_BIND_OP_MAP_NOEXEC;
		}
		if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind)) {
			perror("private eight-operation VM_BIND");
			goto cleanup;
		}
	}
	close_bo.handle = bo.handle;
	if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &close_bo))
		goto cleanup;
	bo.handle = 0;
	*alias = 0x12345678UL;
	if (memory[(pages - 1) * PAGE / sizeof(*memory)] != *alias)
		goto cleanup;
	/* VMA and GPU mappings retain backing after the GEM handle disappears. */
	if (drm_bind(fd, vm.id, 0, BASE, 0, bo.size, DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP)) {
		perror("private VM_BIND unmap after GEM_CLOSE");
		goto cleanup;
	}
	mapped = 0;
	ret = 0;
cleanup:
	if (other_fd >= 0)
		close(other_fd);
	if (mapped && drm_bind(fd, vm.id, 0, BASE, 0, bo.size, DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP))
		ret = 1;
	if (bo.handle) {
		close_bo.handle = bo.handle;
		if (ioctl(fd, DRM_IOCTL_GEM_CLOSE, &close_bo))
			ret = 1;
	}
	if (vm.id) {
		destroy.id = vm.id;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy))
			ret = 1;
	}
	if (alias != MAP_FAILED)
		munmap(alias, PAGE);
	if (memory != MAP_FAILED)
		munmap(memory, bo.size);
	close(fd);
	printf("GPU_PRIVATE_DRM=%s BO_CREATE, WB mmap, noexec/COW/file bounds, VM_BIND batching/remap, GEM/VMA lifetime\n",
	       ret ? "FAIL" : "PASS");
	puts("GPU_PRIVATE_EXECUTION=NOT_RUN CPU_REALM_ISOLATION=NOT_RUN HARDWARE_GPC=NOT_RUN");
	return ret;
}

/* A real DRM/RSI/firmware probe, kept separate from the non-execution probe.
 * Zero-sized streams still execute protected RMM completion wrappers. This
 * checks task fences, not shader computation or malicious-Proxy isolation.
 */
static int drm_submit_selftest(const char *device)
{
	struct drm_panthor_gpu_info gpu = { 0 };
	struct drm_panthor_dev_query query = { .type = DRM_PANTHOR_DEV_QUERY_GPU_INFO,
		.size = sizeof(gpu), .pointer = (uintptr_t)&gpu };
	struct drm_panthor_vm_create vm = { 0 };
	struct drm_panthor_queue_create queues[2] = {
		{ .ringbuf_size = 4096 }, { .ringbuf_size = 4096 } };
	struct drm_panthor_group_create group = {
		.queues = { .count = 2, .stride = sizeof(queues[0]), .array = (uintptr_t)queues },
		.max_compute_cores = 1, .max_fragment_cores = 1, .max_tiler_cores = 1,
		.priority = PANTHOR_GROUP_PRIORITY_LOW };
	struct drm_syncobj_create objects[5] = { { .flags = DRM_SYNCOBJ_CREATE_SIGNALED } };
	struct drm_panthor_sync_op syncs[8] = { 0 };
	struct drm_panthor_queue_submit jobs[2] = { 0 };
	struct drm_panthor_group_submit submit = {
		.queue_submits = { .count = 2, .stride = sizeof(jobs[0]), .array = (uintptr_t)jobs } };
	struct drm_syncobj_timeline_wait wait = { .count_handles = 1,
		.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT };
	struct timespec now;
	uint64_t point = 2;
	uint32_t handle;
	int fd, ret = 1;

	if (private_mode("client"))
		return 1;
	fd = open(device, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		return 1;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_DEV_QUERY, &query) ||
	    !gpu.shader_present || !gpu.tiler_present ||
	    ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) || !vm.id)
		goto out;
	group.vm_id = vm.id;
	group.compute_core_mask = gpu.shader_present & -gpu.shader_present;
	group.fragment_core_mask = group.compute_core_mask;
	group.tiler_core_mask = gpu.tiler_present & -gpu.tiler_present;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &group) || !group.group_handle)
		goto out;
	for (unsigned int i = 0; i < 5; i++)
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &objects[i]) || !objects[i].handle)
			goto out;
	/* q0 waits for input, q1 waits for q0. The next ioctl then appends q1. */
	syncs[0].handle = objects[0].handle;
	syncs[1] = (struct drm_panthor_sync_op) { .handle = objects[1].handle,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL };
	syncs[2].handle = objects[1].handle;
	syncs[3] = (struct drm_panthor_sync_op) { .handle = objects[2].handle,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL };
	syncs[4] = (struct drm_panthor_sync_op) { .handle = objects[4].handle, .timeline_value = 1,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL | DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ };
	syncs[5].handle = objects[2].handle;
	syncs[6] = (struct drm_panthor_sync_op) { .handle = objects[3].handle,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL };
	syncs[7] = syncs[4];
	syncs[7].timeline_value = 2;
	jobs[0].syncs = (struct drm_panthor_obj_array) { .count = 2,
		.stride = sizeof(syncs[0]), .array = (uintptr_t)&syncs[0] };
	jobs[1].queue_index = 1;
	jobs[1].syncs = (struct drm_panthor_obj_array) { .count = 3,
		.stride = sizeof(syncs[0]), .array = (uintptr_t)&syncs[2] };
	submit.group_handle = group.group_handle;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_SUBMIT, &submit))
		goto out;
	jobs[0].queue_index = 1;
	jobs[0].syncs.array = (uintptr_t)&syncs[5];
	jobs[0].syncs.count = 3;
	submit.queue_submits.count = 1;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_SUBMIT, &submit) || clock_gettime(CLOCK_MONOTONIC, &now))
		goto out;
	handle = objects[4].handle;
	wait.handles = (uintptr_t)&handle;
	wait.points = (uintptr_t)&point;
	wait.timeout_nsec = (int64_t)now.tv_sec * 1000000000 + now.tv_nsec + INT64_C(60000000000);
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT, &wait))
		goto out;
	/* WAIT also wakes on errors. Inspect each exact job's binary sync_file. */
	for (unsigned int i = 1; i < 4; i++) {
		struct drm_syncobj_handle exported = { .handle = objects[i].handle, .fd = -1,
			.flags = DRM_SYNCOBJ_HANDLE_TO_FD_FLAGS_EXPORT_SYNC_FILE };
		struct sync_file_info info = { 0 };
		int bad = ioctl(fd, DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD, &exported);

		if (!bad && exported.fd >= 0)
			bad = ioctl(exported.fd, SYNC_IOC_FILE_INFO, &info) || info.status != 1;
		else
			bad = 1;
		if (exported.fd >= 0)
			close(exported.fd);
		if (bad)
			goto out;
	}
	ret = 0;
out:
	for (unsigned int i = 0; i < 5; i++) {
		struct drm_syncobj_destroy destroy = { .handle = objects[i].handle };

		if (destroy.handle && ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy))
			ret = 1;
	}
	if (group.group_handle) {
		struct drm_panthor_group_destroy destroy = { .group_handle = group.group_handle };

		if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY, &destroy))
			ret = 1;
	}
	if (vm.id) {
		struct drm_panthor_vm_destroy destroy = { .id = vm.id };

		if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy))
			ret = 1;
	}
	close(fd);
	printf("GPU_PRIVATE_DRM_SUBMIT=%s two queues, cross-submit dependencies, three exact successful job fences; PAYLOAD_COMPUTE_AND_ISOLATION_ATTACKS=NOT_RUN\n",
		ret ? "FAIL" : "PASS");
	return ret;
}

int main(int argc, char **argv)
{
	struct realm_gpu_call result;
	uint64_t args[7] = { 0 }, pages = 513;
	int fd, index, ret;

	_Static_assert(sizeof(struct realm_gpu_call) == 96, "GPU call ABI size");
	_Static_assert(sizeof(struct realm_gpu_alloc) == 40, "GPU alloc ABI size");
	if (argc == 2 && !strcmp(argv[1], "--help")) {
		puts("realm-gpu-private version\n"
		     "realm-gpu-private mode-check client|proxy  (require actual read-only private driver mode)\n"
		     "realm-gpu-private selftest CHANNEL [PAGES]  (default 513, max 131072)\n"
		     "realm-gpu-private drm-selftest [DEVICE [PAGES]]  (default /dev/dri/renderD128, 513)\n"
		     "realm-gpu-private drm-submit-selftest [DEVICE]  (private Client; configured trusted service; real fence-only execution)\n"
		     "realm-gpu-private firmware-snapshot FILE  (isolated GPU service only; no firmware boot)\n"
		     "realm-gpu-private firmware-control BYTES  (isolated service; after call 22, before call 23; max 16 MiB)\n"
		     "realm-gpu-private service-bootstrap FILE  (upload/prepare/donate/boot/configure; requires prior MMIO handoff)\n"
		     "realm-gpu-private group-selftest CHANNEL [STREAMS]  (Client; configured service with donated arena; default 1)\n"
		     "realm-gpu-private call OP HANDLE [A B C D E]\n"
		     "Requires Client Realm, matching RMM and a channel to the designated GPU service.\n"
		     "Private registration requires prior service MMIO handoff (service call 17, zero inputs).\n"
		     "panthor.rmm_service=1 hands off at probe and retains metadata-only service; otherwise stop/unbind native driver before handoff.\n"
		     "Service call 8 CONTEXT AS_SLOT can install a root after handoff, with MCU/GPU stopped.\n"
		     "After firmware-snapshot, service call 22 0 prepares protected MCU mappings; call 23 0 boots the MCU.\n"
		     "Service call 24 0 configures the private global interface and checks real ACK; call 25 0 0 (or 1) reads sanitized properties.\n"
		     "MCU boot does not publish Client queues or start GPU tasks; execution support is incomplete.");
		return 0;
	}
	if (argc < 2)
		return 2;
	if (!strcmp(argv[1], "mode-check")) {
		if (argc != 3)
			return 2;
		ret = private_mode(argv[2]);
		if (!ret)
			printf("GPU_PRIVATE_MODE=PASS role=%s\n", argv[2]);
		return ret;
	}
	if (!strcmp(argv[1], "drm-submit-selftest")) {
		if (argc > 3)
			return 2;
		return drm_submit_selftest(argc == 3 ? argv[2] : "/dev/dri/renderD128");
	}
	if (!strcmp(argv[1], "drm-selftest")) {
		if (argc > 4 || (argc == 4 && number(argv[3], &pages)) ||
		    !pages || pages > 131072)
			return 2;
		return drm_selftest(argc >= 3 ? argv[2] : "/dev/dri/renderD128", pages);
	}
	if (!strcmp(argv[1], "version")) {
		if (argc != 2)
			return 2;
	} else if (!strcmp(argv[1], "firmware-snapshot") || !strcmp(argv[1], "service-bootstrap")) {
		if (argc != 3)
			return 2;
	} else if (!strcmp(argv[1], "firmware-control")) {
		if (argc != 3 || number(argv[2], &args[0]) || !args[0] ||
		    args[0] % PAGE || args[0] / PAGE > REALM_GPU_CONTROL_MAX_PAGES)
			return 2;
	} else if (!strcmp(argv[1], "selftest")) {
		if ((argc != 3 && argc != 4) || number(argv[2], &args[0]) || !args[0] ||
		    (argc == 4 && number(argv[3], &pages)) || !pages || pages > 131072)
			return 2;
	} else if (!strcmp(argv[1], "group-selftest")) {
		args[1] = 1;
		if ((argc != 3 && argc != 4) || number(argv[2], &args[0]) || !args[0] ||
		    (argc == 4 && number(argv[3], &args[1])) || !args[1] || args[1] > 32)
			return 2;
	} else if (!strcmp(argv[1], "call")) {
		if (argc < 4 || argc > 9)
			return 2;
		for (index = 2; index < argc; index++)
			if (number(argv[index], &args[index - 2]))
				return 2;
		if (args[0] > REALM_GPU_MAX_OPERATION || args[0] == REALM_GPU_BO_APPEND ||
		    args[0] == REALM_GPU_CONTROL_APPEND || args[0] == REALM_GPU_FW_WRITE)
			return 2; /* No unpinned arbitrary IPA list from userspace. */
	} else {
		return 2;
	}
	fd = open("/dev/realm-xshm", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror("/dev/realm-xshm");
		return 1;
	}
	if (!strcmp(argv[1], "selftest")) {
		ret = selftest(fd, args[0], pages);
	} else if (!strcmp(argv[1], "group-selftest")) {
		ret = group_selftest(fd, args[0], args[1]);
	} else if (!strcmp(argv[1], "firmware-snapshot")) {
		ret = firmware_snapshot(fd, argv[2]);
	} else if (!strcmp(argv[1], "firmware-control")) {
		ret = firmware_control(fd, args[0]);
	} else if (!strcmp(argv[1], "service-bootstrap")) {
		ret = service_bootstrap(fd, argv[2]);
	} else {
		ret = call(fd, args[0], args[1], args[2], args[3], args[4], args[5], args[6], &result);
		if (ret) {
			perror("REALM_GPU_CALL");
			ret = 1;
		} else {
			output(&result);
			ret = result.status ? 3 : 0;
		}
	}
	close(fd);
	return ret;
}
