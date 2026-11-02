/* SPDX-License-Identifier: MIT */
/* Notification API checks only; CPU signaling here is not GPU completion. */
static int private_syncobj_mode(void)
{
	char mode[8];
	FILE *input = fopen("/sys/module/panthor_client/parameters/rmm_private_data", "r");
	int result = -1;

	if (!input)
		return errno == ENOENT ? 0 : -1;
	if (fgets(mode, sizeof(mode), input) && !ferror(input)) {
		if (!strcmp(mode, "Y\n") || !strcmp(mode, "1\n"))
			result = 1;
		else if (!strcmp(mode, "N\n") || !strcmp(mode, "0\n"))
			result = 0;
	}
	if (fclose(input))
		return -1;
	return result;
}

static int syncobj_eventfd_readiness(int fd, bool ready)
{
	struct pollfd wait = { .fd = fd, .events = POLLIN };
	uint64_t count = 0;
	ssize_t bytes;
	int ret;

	do {
		ret = poll(&wait, 1, ready ? 2000 : 0);
	} while (ret < 0 && errno == EINTR);
	if (ret != (ready ? 1 : 0) || (ready && wait.revents != POLLIN))
		return -1;
	do {
		bytes = read(fd, &count, sizeof(count));
	} while (bytes < 0 && errno == EINTR);
	if (!ready)
		return bytes == -1 && errno == EAGAIN ? 0 : -1;
	return bytes == sizeof(count) && count == 1 ? 0 : -1;
}

static int private_syncobj_eventfd_check(int fd)
{
	struct drm_syncobj_create object = { 0 };
	struct drm_syncobj_destroy destroy = { 0 };
	struct drm_syncobj_eventfd request = { 0 }, invalid;
	struct drm_syncobj_array binary = { .count_handles = 1 };
	struct drm_syncobj_timeline_array timeline = { .count_handles = 1 };
	uint64_t point = 6;
	int notify = -1, ret = -1;

	for (unsigned int kind = 0; kind < 2; kind++) {
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &object))
			goto out;
		destroy.handle = object.handle;
		notify = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
		if (notify < 0)
			goto out;
		request = (struct drm_syncobj_eventfd) {
			.handle = object.handle, .fd = notify, .point = kind ? 7 : 0,
		};
		/* Private mode must support this valid request. Treating ENOENT or
		 * EOPNOTSUPP as success would conceal a missing local syncobj path.
		 */
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_EVENTFD, &request) ||
		    syncobj_eventfd_readiness(notify, false))
			goto out;
		invalid = request;
		invalid.handle = 0;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_EVENTFD, &invalid) != -1 || errno != ENOENT)
			goto out;
		invalid = request;
		invalid.fd = -1;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_EVENTFD, &invalid) != -1 || errno != EBADF)
			goto out;
		invalid = request;
		invalid.flags = UINT32_MAX;
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_EVENTFD, &invalid) != -1 || errno != EINVAL)
			goto out;
		binary.handles = (uint64_t)(uintptr_t)&object.handle;
		timeline.handles = binary.handles;
		timeline.points = (uint64_t)(uintptr_t)&point;
		if (kind) {
			/* An earlier timeline point must not notify this future wait. */
			point = 6;
			if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_SIGNAL, &timeline) ||
			    syncobj_eventfd_readiness(notify, false))
				goto out;
			point = 7;
			if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_SIGNAL, &timeline))
				goto out;
		} else if (ioctl(fd, DRM_IOCTL_SYNCOBJ_SIGNAL, &binary)) {
			goto out;
		}
		if (syncobj_eventfd_readiness(notify, true) ||
		    syncobj_eventfd_readiness(notify, false))
			goto out;
		/* Entries are one-shot; another signal cannot replay the notification. */
		if (kind) {
			point = 8;
			if (ioctl(fd, DRM_IOCTL_SYNCOBJ_TIMELINE_SIGNAL, &timeline))
				goto out;
		} else if (ioctl(fd, DRM_IOCTL_SYNCOBJ_SIGNAL, &binary)) {
			goto out;
		}
		if (syncobj_eventfd_readiness(notify, false))
			goto out;
		if (kind) {
			request.point = 11;
			if (ioctl(fd, DRM_IOCTL_SYNCOBJ_EVENTFD, &request))
				goto out;
		}
		if (ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy))
			goto out;
		destroy.handle = 0;
		if (syncobj_eventfd_readiness(notify, false))
			goto out;
		close(notify);
		notify = -1;
		object = (struct drm_syncobj_create) { 0 };
	}
	puts("PANTHOR_SYNCOBJ_EVENTFD_SMOKE=PASS binary=1 timeline=1 one_shot=1 invalid_inputs=1 destroy_pending=1 source=CPU_SIGNAL_NOT_GPU_COMPLETION");
	ret = 0;
out:
	if (ret)
		fprintf(stderr, "PANTHOR_SYNCOBJ_EVENTFD_SMOKE=FAIL errno=%d (%s)\n",
			errno, strerror(errno));
	if (notify >= 0)
		close(notify);
	if (destroy.handle && ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy))
		ret = -1;
	return ret;
}
