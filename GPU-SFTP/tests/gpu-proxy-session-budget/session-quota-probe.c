#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	int descriptors[65];
	unsigned long limit;
	char *end;
	const char *device;
	FILE *mode;
	bool passed = false;
	int enabled, replacement = -1, extra = -1;

	for (unsigned int index = 0; index < 65; index++)
		descriptors[index] = -1;
	if (argc < 2 || argc > 3) {
		fprintf(stderr, "usage: session-quota-probe EXPECTED_LIMIT [DRM_DEVICE]\n");
		return 2;
	}
	errno = 0;
	limit = strtoul(argv[1], &end, 10);
	if (errno || !*argv[1] || *end || !limit || limit > 64)
		return 2;
	device = argc == 3 ? argv[2] : "/dev/dri/renderD128";
	mode = fopen("/sys/module/panthor_client/parameters/private_gpu", "r");
	if (!mode) {
		perror("private Client mode");
		return 1;
	}
	enabled = fgetc(mode);
	fclose(mode);
	if (enabled != 'Y' && enabled != '1') {
		fprintf(stderr, "private Client required\n");
		return 1;
	}
	for (unsigned long index = 0; index <= limit; index++) {
		descriptors[index] = open(device, O_RDWR | O_CLOEXEC);
		if (index < limit && descriptors[index] < 0) {
			fprintf(stderr, "premature rejection at %lu: errno=%d\n", index, errno);
			goto out;
		}
		if (index == limit && (descriptors[index] >= 0 || errno != ENOSPC)) {
			fprintf(stderr, "limit not enforced at %lu: fd=%d errno=%d\n",
				index, descriptors[index], errno);
			goto out;
		}
	}
	if (close(descriptors[0])) {
		descriptors[0] = -1;
		perror("close one session");
		goto out;
	}
	descriptors[0] = -1;
	replacement = open(device, O_RDWR | O_CLOEXEC);
	if (replacement < 0) {
		perror("reopen released session");
		goto out;
	}
	extra = open(device, O_RDWR | O_CLOEXEC);
	if (extra >= 0 || errno != ENOSPC) {
		fprintf(stderr, "replacement lost quota: fd=%d errno=%d\n", extra, errno);
		goto out;
	}
	passed = true;
out:
	if (replacement >= 0 && close(replacement))
		passed = false;
	if (extra >= 0 && close(extra))
		passed = false;
	for (unsigned int index = 0; index < 65; index++)
		if (descriptors[index] >= 0 && close(descriptors[index]))
			passed = false;
	if (passed) {
		int recovered = open(device, O_RDWR | O_CLOEXEC);

		if (recovered < 0 || close(recovered))
			passed = false;
	}
	printf("GPU_PROXY_SESSION_QUOTA=%s limit=%lu actual_drm_open_close\n",
		passed ? "PASS" : "FAIL", limit);
	return passed ? 0 : 1;
}
