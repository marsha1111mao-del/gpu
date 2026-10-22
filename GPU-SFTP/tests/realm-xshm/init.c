// SPDX-License-Identifier: GPL-2.0-only
/* Minimal PID 1 for real Realm RSI tests, controlled through its serial port. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/klog.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t telemetry_pid;

static int telemetry_start(void)
{
	if (telemetry_pid)
		return 1;
	telemetry_pid = fork();
	if (telemetry_pid < 0) {
		telemetry_pid = 0;
		return 1;
	}
	if (!telemetry_pid) {
		FILE *output = fopen("/cpu-samples.log", "w");
		char buffer[512];

		if (!output)
			_exit(1);
		for (;;) {
			FILE *input = fopen("/proc/uptime", "r");
			double uptime = 0;

			if (input) {
				if (fscanf(input, "%lf", &uptime) != 1)
					uptime = 0;
				fclose(input);
			}
			input = fopen("/proc/stat", "r");
			if (input) {
				if (fgets(buffer, sizeof(buffer), input))
					fprintf(output, "REALM_CPU_SAMPLE uptime=%.2f %s", uptime, buffer);
				fclose(input);
			}
			fflush(output);
			sleep(2);
		}
	}
	return 0;
}

static int telemetry_stop(void)
{
	FILE *input;
	char buffer[512];
	int status;

	if (!telemetry_pid)
		return 1;
	if (kill(telemetry_pid, SIGTERM) && errno != ESRCH)
		return 1;
	while (waitpid(telemetry_pid, &status, 0) < 0)
		if (errno != EINTR)
			return 1;
	telemetry_pid = 0;
	input = fopen("/cpu-samples.log", "r");
	if (!input)
		return 1;
	while (fgets(buffer, sizeof(buffer), input))
		fputs(buffer, stdout);
	status = ferror(input);
	fclose(input);
	puts("XSHM_CPU_SAMPLES_END");
	return status ? 1 : 0;
}

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
		if ((!strncmp(profile, "ml-", 3) || !strncmp(profile, "attention-", 10)) &&
		    mount("/gles-ml-smoke", "/work/root/gles-ml-smoke", NULL, MS_BIND, NULL))
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

static void memory_info(void)
{
	char buffer[4096];
	FILE *stream = fopen("/proc/meminfo", "r");
	size_t count;

	if (!stream)
		_exit(1);
	while ((count = fread(buffer, 1, sizeof(buffer), stream)))
		if (fwrite(buffer, 1, count, stdout) != count)
			_exit(1);
	if (ferror(stream) || fclose(stream))
		_exit(1);
	puts("XSHM_MEMORY_INFO_END");
	_exit(0);
}

static void notify_trace_dump(void)
{
	char buffer[4096];
	FILE *stream;
	size_t count;

	mkdir("/sys/kernel/debug", 0755);
	if (mount("debugfs", "/sys/kernel/debug", "debugfs", 0, NULL) && errno != EBUSY)
		_exit(1);
	stream = fopen("/sys/kernel/debug/realm_xshm/notify_trace", "r");
	if (!stream)
		_exit(1);
	puts("XSHM_NOTIFY_TRACE_BEGIN");
	while ((count = fread(buffer, 1, sizeof(buffer), stream)))
		if (fwrite(buffer, 1, count, stdout) != count)
			_exit(1);
	if (ferror(stream) || fclose(stream))
		_exit(1);
	puts("XSHM_NOTIFY_TRACE_END");
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
		int module_load = 0, module_unload = 0;
		int iommu_device = 0;

		if (!word)
			continue;
		if (!strcmp(word, "halt"))
			break;
		if (!strcmp(word, "telemetry-start") || !strcmp(word, "telemetry-stop")) {
			status = !strcmp(word, "telemetry-start") ? telemetry_start() : telemetry_stop();
			printf("XSHM_COMMAND_EXIT=%d\n", status);
			continue;
		}
		graphics = !strcmp(word, "glmark");
		compute = !strcmp(word, "compute");
		performance = !strcmp(word, "performance");
		klog = !strcmp(word, "kernel-log");
		module_load = !strcmp(word, "insmod");
		module_unload = !strcmp(word, "rmmod");
		iommu_device = !strcmp(word, "iommu-device");
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
			if (!strcmp(args[1], "memory-info"))
				memory_info();
			if (!strcmp(args[1], "notify-trace"))
				notify_trace_dump();
			if (iommu_device) {
				int descriptor;
				ssize_t written;

				if (count != 3 || (strcmp(args[2], "5") && strcmp(args[2], "6") &&
						   strcmp(args[2], "11")))
					_exit(2);
				descriptor = open("/sys/module/opencca_guest_iommu_probe/parameters/device_action",
						  O_WRONLY | O_CLOEXEC);
				if (descriptor < 0)
					_exit(1);
				written = write(descriptor, args[2], strlen(args[2]));
				close(descriptor);
				_exit(written == (ssize_t)strlen(args[2]) ? 0 : 1);
			}
			if (module_load) {
				char parameters[256] = "";
				size_t offset = 0;
				int fd;
				if (count < 3)
					_exit(2);
				for (unsigned int index = 3; index < count; index++) {
					int written = snprintf(parameters + offset,
							       sizeof(parameters) - offset,
							       "%s%s", index == 3 ? "" : " ", args[index]);
					if (written < 0 || (size_t)written >= sizeof(parameters) - offset)
						_exit(2);
					offset += written;
				}
				fd = open(args[2], O_RDONLY | O_CLOEXEC);
				if (fd < 0)
					_exit(2);
				errno = 0;
				if (syscall(SYS_finit_module, fd, parameters, 0))
					perror("insmod");
				_exit(errno);
			}
			if (module_unload) {
				if (count != 3)
					_exit(2);
				errno = 0;
				if (syscall(SYS_delete_module, args[2], 0))
					perror("rmmod");
				_exit(errno);
			}
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
