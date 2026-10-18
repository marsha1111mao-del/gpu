// SPDX-License-Identifier: GPL-2.0-only
/* Minimal PID 1 for real Realm RSI tests, controlled through its serial port. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/klog.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static void gpu_workload(int compute, const char *profile)
{
	/* An isolated, read-only workload root. Mounts disappear with this child;
	 * the initrd/RMM controller stays available for teardown after failures.
	 */
	if (unshare(CLONE_NEWNS) ||
	    mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL))
		goto error;
	mkdir("/work", 0755);
	if (mount("/dev/vda", "/work", "ext4", MS_RDONLY, NULL) ||
	    mount("/dev", "/work/dev", NULL, MS_BIND | MS_REC, NULL) ||
	    mount("/proc", "/work/proc", NULL, MS_BIND, NULL) ||
	    mount("/sys", "/work/sys", NULL, MS_BIND, NULL) ||
	    mount("tmpfs", "/work/tmp", "tmpfs", 0, "size=256m") ||
	    mount("/glmark.env", "/work/root/gpu-smoke.env", NULL, MS_BIND, NULL) ||
	    mount("/gpu-smoke.sh", "/work/root/gpu-smoke.sh", NULL, MS_BIND, NULL))
		goto error;
	if (profile) {
		int fd = open("/work/tmp/performance-suite.sh", O_WRONLY | O_CREAT, 0700);
		if (fd < 0)
			goto error;
		close(fd);
		fd = open("/work/tmp/ioctl-perf", O_WRONLY | O_CREAT, 0700);
		if (fd < 0)
			goto error;
		close(fd);
		if (mount("/ioctl-perf", "/work/tmp/ioctl-perf", NULL, MS_BIND, NULL))
			goto error;
		if (mount("/performance-suite.sh", "/work/tmp/performance-suite.sh", NULL, MS_BIND, NULL))
			goto error;
	}
	if (chroot("/work") || chdir("/"))
		goto error;
	if (profile) {
		execl("/bin/sh", "sh", "/tmp/performance-suite.sh", profile, NULL);
		goto error;
	}
	if (compute)
		execl("/root/gles-compute-smoke", "gles-compute-smoke",
		      "--count", "65536", "--iterations", "4", "--alu-iters", "64",
		      "/dev/dri/renderD128", NULL);
	else
		execl("/bin/sh", "sh", "/root/gpu-smoke.sh", NULL);
error:
	perror("realm glmark");
	_exit(127);
}

static void kernel_log(void)
{
	int size = klogctl(10, NULL, 0), read;
	char *data;

	if (size < 0 || size > 4 * 1024 * 1024)
		_exit(1);
	data = malloc(size + 1);
	if (!data)
		_exit(1);
	read = klogctl(3, data, size);
	if (read < 0)
		_exit(1);
	fwrite(data, 1, read, stdout);
	puts("\nXSHM_KERNEL_LOG_END");
	free(data);
	_exit(0);
}

int main(void)
{
	char *line = NULL;
	size_t size = 0;
	int module;

	setbuf(stdout, NULL);
	mkdir("/proc", 0755);
	mkdir("/sys", 0755);
	mkdir("/dev", 0755);
	if (mount("proc", "/proc", "proc", 0, NULL) ||
	    mount("sysfs", "/sys", "sysfs", 0, NULL) ||
	    mount("devtmpfs", "/dev", "devtmpfs", 0, NULL))
		goto error;
	module = open("/dev/realm-xshm", O_RDWR | O_CLOEXEC);
	if (module < 0)
		goto error;
	close(module);
	puts("XSHM_READY");
	while (getline(&line, &size, stdin) >= 0) {
		char *args[8] = { "/realm-xshm" };
		char *save, *word = strtok_r(line, " \t\r\n", &save);
		unsigned int count = 1;
		int status;
		pid_t child;
		int graphics = 0, compute = 0, klog = 0, performance = 0;

		if (!word)
			continue;
		if (!strcmp(word, "halt"))
			break;
		graphics = !strcmp(word, "glmark");
		compute = !strcmp(word, "compute");
		performance = !strcmp(word, "performance");
		klog = !strcmp(word, "kernel-log");
		if (!strcmp(word, "gpu-smoke")) {
			args[0] = "/panthor_ioctl_smoke";
			word = strtok_r(NULL, " \t\r\n", &save);
		}
		while (word && count < 7) {
			args[count++] = word;
			word = strtok_r(NULL, " \t\r\n", &save);
		}
		if (word) {
			puts("XSHM_COMMAND_EXIT=2");
			continue;
		}
		child = fork();
		if (child == 0) {
			if (graphics || compute || performance)
				gpu_workload(compute, performance && count == 3 ? args[2] : NULL);
			if (klog)
				kernel_log();
			execv(args[0], args);
			_exit(127);
		}
		if (child < 0)
			goto error;
		while (waitpid(child, &status, 0) < 0)
			if (errno != EINTR)
				goto error;
		printf("XSHM_COMMAND_EXIT=%d\n", WIFEXITED(status) ? WEXITSTATUS(status) : 128);
	}
	free(line);
	reboot(RB_POWER_OFF);
	return 0;
error:
	perror("realm-xshm init");
	puts("XSHM_INIT=FAIL");
	for (;;)
		pause();
}
