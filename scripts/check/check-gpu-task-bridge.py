#!/usr/bin/env python3
"""Exercise actual task owner/RPC source with kernel, transport and RSI doubles.

Checks ownership, copied input, typed replies and retention. It does not run
Linux concurrency, real RSI, device firmware or DRM dependency scheduling.
"""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
guest = root / 'Linux-Guest-GPU'
out = root / 'build/rmm-client-bo-20261030/task-bridge-unit'
out.mkdir(parents=True, exist_ok=True)


def function(source, name):
    match = re.search(r'^(?:static )?(?:struct \w+ \*|int |long |bool |void |u64 )' +
                      re.escape(name) + r'\s*\(', source, re.M)
    assert match, name
    end = source.index('\n}', match.end()) + 2
    body = source[match.start():end]
    assert ';' not in body[:body.index('{')], name
    return body + '\n'


def structure(source, name):
    match = re.search(r'^struct ' + re.escape(name) + r' \{', source, re.M)
    assert match, name
    return source[match.start():source.index('\n};', match.end()) + 3] + '\n'


kernel = (guest / 'drivers/char/realm_gpu.c').read_text()
proxy = (guest / 'drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c').read_text()
wire = (guest / 'include/linux/panthor_vmshm.h').read_text()
parts = [structure(kernel, name) for name in ('realm_gpu_group', 'realm_gpu_task')]
parts += [structure(proxy, name) for name in ('panthor_proxy_group', 'panthor_proxy_vm')]
parts += [structure(wire, name) for name in ('panthor_vmshm_rmm_task_req', 'panthor_vmshm_rmm_task_rsp')]
# Keep request types/actions and the feature bit sourced from the real header.
parts += [line for line in wire.splitlines() if line.startswith('#define PANTHOR_VMSHM_') and
          ('RMM_TASK' in line or 'MAX_GROUP_QUEUES' in line)]
(out / 'structures.inc').write_text('\n'.join(parts))
parts = [function(kernel, name) for name in ('private_status', 'managed_group',
    'managed_task', 'reap_tasks', 'realm_gpu_task_stage', 'realm_gpu_task_handle',
    'realm_gpu_task_cancel_unprepared',
    'task_call', 'realm_gpu_task_call', 'realm_gpu_task_publish', 'realm_gpu_task_put', 'realm_gpu_ioctl')]
parts += [function(proxy, name) for name in ('panthor_proxy_rmm_task_control_available',
    'panthor_proxy_session_rmm_task', 'panthor_proxy_handle_rmm_task')]
(out / 'actual.inc').write_text('\n'.join(parts))
subprocess.run([os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra',
    '-Werror', '-Wno-unused-parameter', '-g', '-fsanitize=address,undefined',
    '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-D__user=', '-I' + str(out),
    '-iquote', str(guest / 'include/uapi'),
    str(root / 'GPU-SFTP/tests/gpu-task-bridge/task-test.c'), '-o', str(out / 'task-test')], check=True)
subprocess.run([str(out / 'task-test')], check=True)
