/* SPDX-License-Identifier: MIT */
/* Probe acceptance/failure tests: real Linux eventfds, modeled DRM/GPU. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>
#include <drm.h>
#include <linux/sync_file.h>

enum fault {
    NONE, EMPTY, MANY, COUNT_CHANGED, WRONG_DRIVER, UNTERMINATED_DRIVER,
    PRE_ERROR, PRE_UNKNOWN, PRE_LEAF_ERROR, PRE_LEAF_UNKNOWN,
    FINAL_PENDING, FINAL_ERROR, FINAL_LEAF_PENDING, FINAL_LEAF_ERROR,
    INFO_FIRST, INFO_DETAILS, FINAL_INFO_FIRST, FINAL_INFO_DETAILS,
    CREATE_FIRST, CREATE_SECOND, ZERO_HANDLE, EVENTFD_FIRST, EVENTFD_SECOND,
    IMPORT, TRANSFER, REGISTER_FIRST, REGISTER_SECOND, NO_NOTIFY, DOUBLE_NOTIFY,
    BAD_POLL, POLL_ERROR, POLL_EXPIRED, CLOSE_FIRST, CLOSE_SECOND,
    DESTROY_FIRST, DESTROY_SECOND, POLL_EINTR, FAULT_COUNT
};
static enum fault fault;
static int source_fd, notifications[2], events, creates, registered, details;
static int poll_calls, flush_calls, probe_calls, destroys, closes;
static bool live[2], complete, initially_complete;

static int model_eventfd(unsigned int init, int flags)
{
    assert(!init && flags == (EFD_CLOEXEC | EFD_NONBLOCK) && events < 2);
    int i = events++;
    if (fault == (i ? EVENTFD_SECOND : EVENTFD_FIRST)) {
        errno = EMFILE;
        return -1;
    }
    return notifications[i] = eventfd(init, flags);
}

static int model_close(int fd)
{
    assert(fd == notifications[0] || fd == notifications[1]);
    int result = close(fd);
    assert(!result);
    closes++;
    if (fault == (fd == notifications[0] ? CLOSE_FIRST : CLOSE_SECOND)) {
        errno = EINTR;
        return -1;
    }
    return 0;
}

static void signal_notification(int fd)
{
    uint64_t count = fault == DOUBLE_NOTIFY ? 2 : 1;
    if (fault != NO_NOTIFY)
        assert(write(fd, &count, sizeof(count)) == (ssize_t)sizeof(count));
}

static int model_poll(struct pollfd *p, nfds_t n, int ms)
{
    assert(n == 1 && ms > 0 && ms <= 10000 && registered == 2);
    poll_calls++;
    if (fault == POLL_EXPIRED || (fault == POLL_EINTR && poll_calls == 1)) {
        errno = EINTR;
        return -1;
    }
    if (fault == POLL_ERROR) { errno = EIO; return -1; }
    if (fault == BAD_POLL) { p->revents = POLLHUP; return 1; }
    if (!complete) {
        complete = true;
        for (int i = 0; i < 2; i++) signal_notification(notifications[i]);
    }
    return poll(p, n, 0);
}

static int model_clock(clockid_t id, struct timespec *value)
{
    assert(id == CLOCK_MONOTONIC);
    value->tv_sec = fault == POLL_EXPIRED && poll_calls ? 11 : 0;
    value->tv_nsec = 0;
    return 0;
}

static int model_ioctl(int fd, unsigned long request, void *arg)
{
    if (request == SYNC_IOC_FILE_INFO) {
        struct sync_file_info *p = arg;
        bool second = p->sync_fence_info != 0;
        bool final = registered == 2;
        assert(fd == source_fd);
        details++;
        if (fault == (final ? (second ? FINAL_INFO_DETAILS : FINAL_INFO_FIRST) :
                            (second ? INFO_DETAILS : INFO_FIRST))) return -1;
        p->num_fences = fault == EMPTY ? 0 : fault == MANY ? 33 :
                        fault == COUNT_CHANGED && second ? 2 : 1;
        p->status = complete ? 1 : 0;
        if (!final && fault == PRE_ERROR) p->status = -EIO;
        if (!final && fault == PRE_UNKNOWN) p->status = 2;
        if (final && fault == FINAL_ERROR) p->status = -EIO;
        if (final && fault == FINAL_PENDING) p->status = 0;
        if (second) {
            struct sync_fence_info *f = (void *)(uintptr_t)p->sync_fence_info;
            strcpy(f[0].driver_name, fault == WRONG_DRIVER ? "panthor-client" : "panthor-client-private");
            if (fault == UNTERMINATED_DRIVER) memset(f[0].driver_name, 'x', sizeof(f[0].driver_name));
            f[0].status = complete ? 1 : 0;
            if (!final && fault == PRE_LEAF_ERROR) f[0].status = -EIO;
            if (!final && fault == PRE_LEAF_UNKNOWN) f[0].status = 2;
            if (final && fault == FINAL_LEAF_ERROR) f[0].status = -EIO;
            if (final && fault == FINAL_LEAF_PENDING) f[0].status = 0;
        }
        return 0;
    }
    assert(fd == 900);
    if (request == DRM_IOCTL_SYNCOBJ_CREATE) {
        struct drm_syncobj_create *p = arg;
        int i = creates++;
        assert(i < 2 && !p->flags);
        if (fault == (i ? CREATE_SECOND : CREATE_FIRST)) return -1;
        if (fault == ZERO_HANDLE) return 0;
        live[i] = true; p->handle = i + 1;
        return 0;
    }
    if (request == DRM_IOCTL_SYNCOBJ_DESTROY) {
        struct drm_syncobj_destroy *p = arg;
        assert(p->handle >= 1 && p->handle <= 2 && live[p->handle - 1]);
        live[p->handle - 1] = false;
        destroys++;
        return fault == (p->handle == 1 ? DESTROY_FIRST : DESTROY_SECOND) ? -1 : 0;
    }
    if (request == DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE) {
        struct drm_syncobj_handle *p = arg;
        assert(p->handle == 1 && p->fd == source_fd &&
               p->flags == DRM_SYNCOBJ_FD_TO_HANDLE_FLAGS_IMPORT_SYNC_FILE);
        return fault == IMPORT ? -1 : 0;
    }
    if (request == DRM_IOCTL_SYNCOBJ_TRANSFER) {
        struct drm_syncobj_transfer *p = arg;
        assert(p->src_handle == 1 && !p->src_point && p->dst_handle == 2 &&
               p->dst_point == 7 && !p->flags && !p->pad);
        return fault == TRANSFER ? -1 : 0;
    }
    if (request == DRM_IOCTL_SYNCOBJ_EVENTFD) {
        struct drm_syncobj_eventfd *p = arg;
        int i = registered++;
        assert(i < 2 && p->handle == (uint32_t)i + 1 && p->fd == notifications[i] &&
               p->point == (i ? 7u : 0u) && !p->flags && !p->pad);
        if (fault == (i ? REGISTER_SECOND : REGISTER_FIRST)) return -1;
        if (initially_complete) signal_notification(p->fd);
        return 0;
    }
    /* No CPU SIGNAL, TIMELINE_SIGNAL or WAIT_AVAILABLE path is accepted. */
    assert(!"unexpected/CPU-signaled ioctl");
    return -1;
}

#define eventfd model_eventfd
#define ioctl model_ioctl
#define poll model_poll
#define close model_close
#define clock_gettime model_clock
#include "gpu_completion_eventfd.h"
#undef eventfd
#undef ioctl
#undef poll
#undef close
#undef clock_gettime

static void reset(enum fault next, bool done)
{
    fault = next; initially_complete = complete = done;
    notifications[0] = notifications[1] = -1;
    events = creates = registered = details = poll_calls = destroys = closes = 0;
    assert(!live[0] && !live[1]);
}

static void verify_cleanup(void)
{
    assert(!live[0] && !live[1]);
    for (int i = 0; i < 2; i++)
        if (notifications[i] >= 0)
            assert(fcntl(notifications[i], F_GETFD) == -1 && errno == EBADF);
    assert(fcntl(source_fd, F_GETFD) >= 0); /* borrowed FD must survive */
}

/* The checker appends the actual EGL bridge functions and modeled EGL entry
 * points here. It does not link/run a GPU userspace driver. */
#include "egl-bridge-test.inc"

int main(void)
{
    unsigned int cases = 0;
    source_fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    assert(source_fd >= 0);
    for (int done = 0; done < 2; done++) {
        reset(NONE, done);
        assert(!gpu_completion_eventfd_check(900, source_fd));
        assert(destroys == 2 && closes == 2 && registered == 2 && details == 4);
        verify_cleanup(); cases++;
    }
    for (int bad = 1; bad < FAULT_COUNT; bad++) {
        reset(bad, false);
        assert(gpu_completion_eventfd_check(900, source_fd) == (bad == POLL_EINTR ? 0 : -1));
        verify_cleanup(); cases++;
    }
    unsigned int bridge_cases = test_egl_bridge();
    assert(!close(source_fd));
    printf("GPU_COMPLETION_EVENTFD_PROBE_MODEL=PASS cases=%u egl_cases=%u REAL_EVENTFD DRM_EGL_DOUBLES_ONLY NO_GPU_EXECUTION_PROOF\n", cases, bridge_cases);
    return 0;
}
