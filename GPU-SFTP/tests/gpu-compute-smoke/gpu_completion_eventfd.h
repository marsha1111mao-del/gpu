/* SPDX-License-Identifier: MIT */
/* The caller exports this borrowed sync_file after a nonempty GPU dispatch.
 * No CPU SIGNAL is issued. All syncobjs/eventfds created here are released. */
#ifndef GPU_COMPLETION_EVENTFD_H
#define GPU_COMPLETION_EVENTFD_H
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <drm.h>
#include <linux/sync_file.h>
#include <poll.h>
#include <stdbool.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>

#ifndef DRM_IOCTL_SYNCOBJ_EVENTFD
struct drm_syncobj_eventfd {
    uint32_t handle, flags;
    uint64_t point;
    int32_t fd;
    uint32_t pad;
};
#define DRM_IOCTL_SYNCOBJ_EVENTFD DRM_IOWR(0xCF, struct drm_syncobj_eventfd)
#endif
_Static_assert(sizeof(struct drm_syncobj_handle) == 16,
               "Build with the target kernel's binary syncobj UAPI");

static int gpu_completion_fence_info(int fd, bool completed)
{
    struct sync_fence_info fences[32] = { 0 };
    struct sync_file_info info = { 0 };

    if (ioctl(fd, SYNC_IOC_FILE_INFO, &info) ||
        info.num_fences == 0 || info.num_fences > 32 ||
        info.status < 0 || info.status > 1 || (completed && info.status != 1))
        return -1;
    unsigned int count = info.num_fences;
    info.sync_fence_info = (uint64_t)(uintptr_t)fences;
    if (ioctl(fd, SYNC_IOC_FILE_INFO, &info) || info.num_fences != count ||
        info.status < 0 || info.status > 1 || (completed && info.status != 1))
        return -1;
    for (unsigned int i = 0; i < count; i++) {
        /* Require a private task fence, not a CPU stub or shared-mode fence. */
        if (strncmp(fences[i].driver_name, "panthor-client-private",
                    sizeof(fences[i].driver_name)) ||
            fences[i].status < 0 || fences[i].status > 1 ||
            (completed && fences[i].status != 1))
            return -1;
    }
    return 0;
}

static int gpu_completion_eventfd_read(int fd)
{
    struct pollfd wait = { .fd = fd, .events = POLLIN };
    struct timespec start, now;
    uint64_t count;
    int timeout = 10000;

    if (clock_gettime(CLOCK_MONOTONIC, &start))
        return -1;
    for (;;) {
        int ready = poll(&wait, 1, timeout);
        if (ready == 1 && wait.revents == POLLIN)
            break;
        if (ready >= 0 || errno != EINTR || clock_gettime(CLOCK_MONOTONIC, &now))
            return -1;
        int64_t elapsed = (int64_t)(now.tv_sec - start.tv_sec) * 1000 +
                          (now.tv_nsec - start.tv_nsec) / 1000000;
        if (elapsed >= 10000)
            return -1;
        timeout = 10000 - (int)elapsed;
    }
    ssize_t bytes;
    do { bytes = read(fd, &count, sizeof(count)); } while (bytes < 0 && errno == EINTR);
    if (bytes != (ssize_t)sizeof(count) || count != 1)
        return -1;
    /* A consumed, one-shot registration must leave no second notification. */
    do { bytes = read(fd, &count, sizeof(count)); } while (bytes < 0 && errno == EINTR);
    return bytes == -1 && errno == EAGAIN ? 0 : -1;
}

static int gpu_completion_eventfd_check(int drm_fd, int sync_fd)
{
    uint32_t handles[2] = { 0 };
    int notify[2] = { -1, -1 };
    int result = -1;

    if (gpu_completion_fence_info(sync_fd, false))
        goto out;
    for (unsigned int i = 0; i < 2; i++) {
        struct drm_syncobj_create create = { 0 };
        if (ioctl(drm_fd, DRM_IOCTL_SYNCOBJ_CREATE, &create))
            goto out;
        handles[i] = create.handle;
        if (!handles[i])
            goto out;
        notify[i] = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
        if (notify[i] < 0)
            goto out;
    }
    struct drm_syncobj_handle imported = {
        .handle = handles[0], .fd = sync_fd,
        .flags = DRM_SYNCOBJ_FD_TO_HANDLE_FLAGS_IMPORT_SYNC_FILE,
    };
    if (ioctl(drm_fd, DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE, &imported))
        goto out;
    struct drm_syncobj_transfer transfer = {
        .src_handle = handles[0], .dst_handle = handles[1], .dst_point = 7,
    };
    if (ioctl(drm_fd, DRM_IOCTL_SYNCOBJ_TRANSFER, &transfer))
        goto out;
    for (unsigned int i = 0; i < 2; i++) {
        struct drm_syncobj_eventfd request = {
            .handle = handles[i], .fd = notify[i], .point = i ? 7 : 0,
        };
        if (ioctl(drm_fd, DRM_IOCTL_SYNCOBJ_EVENTFD, &request))
            goto out;
    }
    for (unsigned int i = 0; i < 2; i++)
        if (gpu_completion_eventfd_read(notify[i]))
            goto out;
    /* Error fences also notify eventfd; notification alone is insufficient. */
    if (gpu_completion_fence_info(sync_fd, true))
        goto out;
    result = 0;
out:
    for (unsigned int i = 0; i < 2; i++) {
        if (notify[i] >= 0 && close(notify[i]))
            result = -1;
        if (handles[i]) {
            struct drm_syncobj_destroy destroy = { .handle = handles[i] };
            if (ioctl(drm_fd, DRM_IOCTL_SYNCOBJ_DESTROY, &destroy))
                result = -1;
        }
    }
    return result;
}
#endif
