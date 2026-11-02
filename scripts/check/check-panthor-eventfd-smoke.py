#!/usr/bin/env python3
"""Exercise the actual eventfd smoke with DRM doubles and real Linux eventfds.

This validates the probe and its failure detection, not DRM/RMM/GPU execution.
"""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[2]
source = (root / 'GPU-SFTP/tests/panthor-ioctl-smoke/panthor_ioctl_smoke.c').read_text()
out = root / 'build/rmm-client-bo-20261030/eventfd-smoke-unit'
out.mkdir(parents=True, exist_ok=True)
uapi_root = root / 'build/panthor-ioctl-uapi'
subprocess.run(['make', '-s', '-C', str(root / 'Linux-Guest-GPU'),
                'O=' + str(uapi_root / 'kbuild'), 'ARCH=arm64',
                'INSTALL_HDR_PATH=' + str(uapi_root / 'export'),
                'headers_install'], check=True)
uapi = uapi_root / 'export/include/drm'


def function(name):
    start = source.index('static int ' + name + '(')
    return source[start:source.index('\n}', start) + 2] + '\n'


harness = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <drm.h>
static const char *mode_value;
static int mode_errno=ENOENT, fault, alive, registered_fd, last_fd=-1, calls, event_calls;
static uint32_t next_handle, active_handle;
static uint64_t requested_point;
static bool pending;
static FILE *mode_file(const char *path,const char *mode) {
    assert(!strcmp(path,"/sys/module/panthor_client/parameters/rmm_private_data") && !strcmp(mode,"r"));
    if(!mode_value){errno=mode_errno;return NULL;}
    return fmemopen((void *)mode_value,strlen(mode_value),"r");
}
static int bounded_poll(struct pollfd *p,nfds_t n,int ms) {
    assert(n==1 && (ms==0 || ms==2000));return poll(p,n,0);
}
static void notify(uint64_t count) {
    assert(registered_fd>=0);assert(write(registered_fd,&count,sizeof(count))==sizeof(count));
}
static int drm_ioctl(int fd,unsigned long cmd,void *arg) {
    assert(fd==10);calls++;
    if(cmd==DRM_IOCTL_GET_CAP){struct drm_get_cap *p=arg;assert(p->capability==DRM_CAP_PRIME);p->value=0;return 0;}
    if(cmd==DRM_IOCTL_SYNCOBJ_CREATE){
        struct drm_syncobj_create *p=arg;assert(!p->flags && !alive);p->handle=active_handle=++next_handle;alive=1;pending=false;return 0;
    }
    if(cmd==DRM_IOCTL_SYNCOBJ_DESTROY){
        struct drm_syncobj_destroy *p=arg;assert(alive && p->handle==active_handle);
        if(fault==8 && pending)notify(1);alive=0;pending=false;return 0;
    }
    if(cmd==DRM_IOCTL_SYNCOBJ_EVENTFD){
        struct drm_syncobj_eventfd *p=arg;event_calls++;
        if(!mode_value || mode_value[0]=='N' || mode_value[0]=='0'){errno=EOPNOTSUPP;return -1;}
        if(fault==9){errno=EOPNOTSUPP;return -1;}
        if(p->flags){if(fault==7)return 0;errno=EINVAL;return -1;}
        if(!alive || p->handle!=active_handle){if(fault==5)return 0;errno=ENOENT;return -1;}
        if(p->fd<0){if(fault==6)return 0;errno=EBADF;return -1;}
        registered_fd=last_fd=p->fd;requested_point=p->point;pending=true;
        if(fault==1)notify(1);return 0;
    }
    if(cmd==DRM_IOCTL_SYNCOBJ_SIGNAL || cmd==DRM_IOCTL_SYNCOBJ_TIMELINE_SIGNAL){
        uint32_t handle;uint64_t point=0;
        if(cmd==DRM_IOCTL_SYNCOBJ_SIGNAL){
            struct drm_syncobj_array *p=arg;assert(p->count_handles==1);handle=*(uint32_t *)(uintptr_t)p->handles;
        }else{
            struct drm_syncobj_timeline_array *p=arg;assert(p->count_handles==1);handle=*(uint32_t *)(uintptr_t)p->handles;point=*(uint64_t *)(uintptr_t)p->points;
        }
        assert(alive && handle==active_handle);
        if(pending && (point>=requested_point || fault==10)){
            if(fault!=2)notify(fault==3?2:1);
            if(fault!=4)pending=false;
        }
        return 0;
    }
    if(cmd==DRM_IOCTL_PRIME_HANDLE_TO_FD || cmd==DRM_IOCTL_PRIME_FD_TO_HANDLE ||
       cmd==DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD || cmd==DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE){errno=EOPNOTSUPP;return -1;}
    assert(!"unexpected ioctl");return -1;
}
#define fopen mode_file
#define poll bounded_poll
#define ioctl drm_ioctl
#include "syncobj_eventfd.h"
''' + function('get_cap') + function('expect_unsupported_ioctl') + function('fd_ioctl_checks') + r'''
int main(void) {
    const char *modes[]={"Y\n","1\n","N\n","0\n","bad\n","","Yextra\n"};
    unsigned int cases=0;
    for(unsigned int i=0;i<sizeof(modes)/sizeof(modes[0]);i++){
        mode_value=modes[i];assert(private_syncobj_mode()==(i<2?1:i<4?0:-1));cases++;
    }
    mode_value=NULL;mode_errno=ENOENT;assert(private_syncobj_mode()==0);cases++;
    mode_errno=EACCES;assert(private_syncobj_mode()==-1);cases++;
    for(unsigned int mode=0;mode<4;mode++){
        mode_value=modes[mode];fault=0;calls=event_calls=0;last_fd=-1;
        assert(!fd_ioctl_checks(10) && !alive && event_calls==(mode<2?9:1));
        if(last_fd>=0)assert(fcntl(last_fd,F_GETFD)==-1 && errno==EBADF);
        cases++;
    }
    for(int bad=1;bad<=10;bad++){
        mode_value="Y\n";fault=bad;last_fd=-1;
        assert(fd_ioctl_checks(10)==-1 && !alive);
        if(last_fd>=0)assert(fcntl(last_fd,F_GETFD)==-1 && errno==EBADF);
        cases++;
    }
    mode_value="?\n";calls=0;assert(fd_ioctl_checks(10)==-1 && !calls);cases++;
    mode_value=NULL;mode_errno=EACCES;assert(fd_ioctl_checks(10)==-1 && !calls);cases++;
    printf("PANTHOR_EVENTFD_PROBE_MODEL=PASS cases=%u actual_probe REAL_EVENTFD DRM_DOUBLES_ONLY NO_GPU_COMPLETION_PROOF\n",cases);
    return 0;
}
'''
(out / 'probe.c').write_text(harness)
command = [os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
           '-Wno-misleading-indentation', '-g', '-fsanitize=address,undefined',
           '-fno-pie', '-no-pie', '-I' + str(uapi),
           '-I' + str(root / 'GPU-SFTP/tests/panthor-ioctl-smoke'),
           str(out / 'probe.c'), '-o', str(out / 'probe')]
subprocess.run(command, check=True)
run = subprocess.run([str(out / 'probe')], text=True, capture_output=True)
(out / 'stdout.log').write_text(run.stdout)
(out / 'stderr.log').write_text(run.stderr)
if run.returncode:
    raise RuntimeError(f'probe model rc={run.returncode}: {run.stderr}')
markers = [line for line in run.stdout.splitlines() if line.startswith('PANTHOR_EVENTFD_PROBE_MODEL=')]
assert len(markers) == 1
print(markers[0])
