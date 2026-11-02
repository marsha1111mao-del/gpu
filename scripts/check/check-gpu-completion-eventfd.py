#!/usr/bin/env python3
"""Test actual GPU completion probe/bridge with real eventfds and DRM/EGL doubles.

This tests the test tool, not GPU execution, interrupt security or isolation.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=ROOT / 'build/rmm-client-bo-20261030/completion-eventfd-model')
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
uapi_root = ROOT / 'build/panthor-ioctl-uapi'
subprocess.run(['make', '-s', '-C', str(ROOT / 'Linux-Guest-GPU'),
                'O=' + str(uapi_root / 'kbuild'), 'ARCH=arm64',
                'INSTALL_HDR_PATH=' + str(uapi_root / 'export'), 'headers_install'], check=True)
source = (ROOT / 'GPU-SFTP/tests/gpu-compute-smoke/gles_compute_smoke.c').read_text()


def function(name):
    start = source.index('static int ' + name + '(')
    return source[start:source.index('\n}', start) + 2] + '\n'


bridge = r'''
/* EGL ABI doubles sufficient for the two actual bridge functions. */
typedef void *EGLDisplay;
typedef void *EGLSyncKHR;
typedef int EGLint;
typedef int EGLBoolean;
typedef unsigned long long EGLTimeKHR;
typedef EGLSyncKHR (*PFNEGLCREATESYNCKHRPROC)(EGLDisplay,EGLint,const EGLint *);
typedef EGLBoolean (*PFNEGLDESTROYSYNCKHRPROC)(EGLDisplay,EGLSyncKHR);
typedef int (*PFNEGLDUPNATIVEFENCEFDANDROIDPROC)(EGLDisplay,EGLSyncKHR);
typedef EGLint (*PFNEGLCLIENTWAITSYNCKHRPROC)(EGLDisplay,EGLSyncKHR,EGLint,EGLTimeKHR);
#define EGL_NO_SYNC_KHR NULL
#define EGL_EXTENSIONS 0x3055
#define EGL_SYNC_NATIVE_FENCE_FD_ANDROID 0x3145
#define EGL_NO_NATIVE_FENCE_FD_ANDROID -1
#define EGL_NONE 0x3038
#define EGL_SYNC_NATIVE_FENCE_ANDROID 0x3144
#define EGL_CONDITION_SATISFIED_KHR 0x30f6
static int egl_fault, sync_alive, export_fd, wait_calls, destroy_calls;
static int sync_token, display_token;
static const char *eglQueryString(EGLDisplay d, EGLint name)
{
    assert(d == &display_token && name == EGL_EXTENSIONS);
    if(egl_fault == 1) return NULL;
    if(egl_fault == 2) return "EGL_ANDROID_native_fence_syncx EGL_KHR_fence_sync";
    if(egl_fault == 3) return "xEGL_ANDROID_native_fence_sync EGL_KHR_fence_sync";
    if(egl_fault == 4) return "EGL_ANDROID_native_fence_sync EGL_KHR_fence_syncx";
    return "EGL_ANDROID_native_fence_sync EGL_KHR_fence_sync";
}
static EGLSyncKHR bridge_create(EGLDisplay d,EGLint type,const EGLint *attr)
{
    assert(d==&display_token && type==EGL_SYNC_NATIVE_FENCE_ANDROID &&
           attr[0]==EGL_SYNC_NATIVE_FENCE_FD_ANDROID &&
           attr[1]==EGL_NO_NATIVE_FENCE_FD_ANDROID && attr[2]==EGL_NONE);
    assert(!sync_alive && !flush_calls && !probe_calls);
    if(egl_fault == 6) return NULL;
    sync_alive=1; return &sync_token;
}
static EGLBoolean bridge_destroy(EGLDisplay d,EGLSyncKHR s)
{
    assert(d==&display_token && s==&sync_token && sync_alive);
    sync_alive=0;destroy_calls++;return egl_fault==11 ? 0 : 1;
}
static int bridge_duplicate(EGLDisplay d,EGLSyncKHR s)
{
    assert(d==&display_token && s==&sync_token && sync_alive && flush_calls==1);
    if(egl_fault==8)return -1;
    export_fd=dup(source_fd);assert(export_fd>=0);return export_fd;
}
static EGLint bridge_wait(EGLDisplay d,EGLSyncKHR s,EGLint flags,EGLTimeKHR time)
{
    assert(d==&display_token && s==&sync_token && sync_alive && !flags && !time && probe_calls==1);
    wait_calls++;return egl_fault==10 ? 0 : EGL_CONDITION_SATISFIED_KHR;
}
static void (*eglGetProcAddress(const char *name))(void)
{
    if(egl_fault==5)return NULL;
    if(!strcmp(name,"eglCreateSyncKHR"))return (void (*)(void))bridge_create;
    if(!strcmp(name,"eglDestroySyncKHR"))return (void (*)(void))bridge_destroy;
    if(!strcmp(name,"eglDupNativeFenceFDANDROID"))return (void (*)(void))bridge_duplicate;
    if(!strcmp(name,"eglClientWaitSyncKHR"))return (void (*)(void))bridge_wait;
    assert(!"unexpected EGL entrypoint");return NULL;
}
static void glFlush(void){assert(sync_alive && !flush_calls);flush_calls++;}
static int check_gl(const char *stage){assert(!strcmp(stage,"GPU eventfd glFlush"));return egl_fault==7?-1:0;}
static int bridge_probe_check(int drm_fd,int fd)
{
    assert(drm_fd==900 && fd==export_fd && sync_alive && flush_calls==1 && !wait_calls);
    probe_calls++;return egl_fault==9 ? -1 : 0;
}
#define gpu_completion_eventfd_check bridge_probe_check
''' + function('egl_has_extension') + function('gpu_dispatch_eventfd') + r'''
#undef gpu_completion_eventfd_check
static unsigned int test_egl_bridge(void)
{
    assert(egl_has_extension("one target", "target"));
    assert(egl_has_extension("target one", "target"));
    assert(!egl_has_extension("xtarget targetx", "target"));
    assert(!egl_has_extension(NULL,"target"));
    for(egl_fault=0;egl_fault<=11;egl_fault++){
        sync_alive=flush_calls=probe_calls=wait_calls=destroy_calls=0;export_fd=-1;
        assert(gpu_dispatch_eventfd(&display_token,900)==(egl_fault ? -1 : 0));
        assert(!sync_alive);
        if(export_fd>=0)assert(fcntl(export_fd,F_GETFD)==-1 && errno==EBADF);
        assert(fcntl(source_fd,F_GETFD)>=0);
        assert(destroy_calls==(egl_fault==0 || egl_fault>=7));
    }
    return 16;
}
'''
(out / 'egl-bridge-test.inc').write_text(bridge)
command = [os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
           '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
           '-I' + str(uapi_root / 'export/include/drm'), '-I' + str(out),
           str(ROOT / 'GPU-SFTP/tests/gpu-compute-smoke/gpu_completion_eventfd_test.c'),
           '-o', str(out / 'probe')]
built = subprocess.run(command, capture_output=True, text=True)
(out / 'build.log').write_text(built.stdout + built.stderr)
results = {'command': command, 'compile_exit_code': built.returncode,
           'scope': 'REAL_EVENTFD_DRM_EGL_DOUBLES_ONLY_NO_GPU_EXECUTION_PROOF'}
if not built.returncode:
    run = subprocess.run([str(out / 'probe')], capture_output=True, text=True)
    (out / 'stdout.log').write_text(run.stdout)
    (out / 'stderr.log').write_text(run.stderr)
    results['run_exit_code'] = run.returncode
(out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
if built.returncode:
    raise RuntimeError(built.stderr)
if run.returncode:
    raise RuntimeError(run.stderr)
markers = [line for line in run.stdout.splitlines() if line.startswith('GPU_COMPLETION_EVENTFD_PROBE_MODEL=PASS')]
assert len(markers) == 1
print(markers[0])
