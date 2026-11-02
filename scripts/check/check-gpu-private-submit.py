#!/usr/bin/env python3
"""Exercise the actual private GROUP_SUBMIT planner and ready-slice worker.

Kernel fences/locks/workqueues, transport and typed RMM calls are host doubles.
Checks dependency/lifetime/error flow; not real RSI, Linux concurrency or GPU.
"""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
guest = root / 'Linux-Guest-GPU'
out = root / 'build/rmm-client-bo-20261030/private-submit-unit'
out.mkdir(parents=True, exist_ok=True)
source = (guest / 'drivers/gpu/drm/panthor-client/panthor_client_drv.c').read_text()
wire = (guest / 'include/linux/panthor_vmshm.h').read_text()


def function(name):
    match = re.search(r'\b' + re.escape(name) + r'\s*\(', source)
    assert match, name
    start = source.rfind('\n', 0, match.start()) + 1
    if not source[start:match.start()].strip():
        start = source.rfind('\n', 0, start - 1) + 1
    end = source.index('\n}', match.end()) + 2
    result = source[start:end]
    assert ';' not in result[:result.index('{')], name
    return result + '\n'


def structure(text, name):
    match = re.search(r'^struct ' + name + r' \{', text, re.M)
    assert match, name
    return text[match.start():text.index('\n};', match.end()) + 3] + '\n'


# Reuse the existing binary/timeline fence and allocation test doubles, not
# another copy of the product planner. Both suites exercise the same semantics.
common = (root / 'GPU-SFTP/tests/gpu-private-bind/bind-test.c').read_text()
common = common[:common.index('struct realm_gpu_context {')]
(out / 'kernel-doubles.inc').write_text(common)
parts = [line for line in wire.splitlines() if line.startswith('#define PANTHOR_VMSHM_') and
         ('RMM_TASK' in line or 'MAX_GROUP_' in line)]
parts += [structure(source, name) for name in (
    'panthor_client_group', 'panthor_client_heap', 'panthor_client_private_fence', 'panthor_client_private_signal')]
parts += [structure(wire, name) for name in (
    'panthor_vmshm_rmm_task_req', 'panthor_vmshm_rmm_task_rsp')]
(out / 'structures.inc').write_text('\n'.join(parts))
parts = [function(name) for name in (
    'panthor_client_private_fence_driver', 'panthor_client_private_fence_timeline',
    'panthor_client_private_fence_release', 'panthor_client_private_fence_alloc')]
# The allocator uses the real ops table.
table_start = source.index('static const struct dma_fence_ops panthor_client_private_fence_ops')
table_end = source.index('\n};', table_start) + 3
parts.insert(3, source[table_start:table_end])
parts += [function(name) for name in (
    'panthor_client_group_put', 'panthor_client_group_get',
    'panthor_client_check_group_submit_sync_op', 'panthor_client_copy_group_submit')]
start = source.index('/* Private GROUP_SUBMIT:')
end = source.index('\n}', source.index('static int panthor_client_private_group_submit(', start)) + 2
parts.append(source[start:end])
parts += [function(name) for name in (
    'panthor_client_ioctl_tiler_heap_create', 'panthor_client_ioctl_tiler_heap_destroy')]
(out / 'actual.inc').write_text('\n'.join(parts))
subprocess.run([os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra',
    '-Werror', '-Wno-unused-parameter', '-Wno-unused-function', '-D__user=', '-g',
    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
    '-I' + str(out), '-iquote', str(guest / 'include/uapi'),
    str(root / 'GPU-SFTP/tests/gpu-private-submit/submit-test.c'),
    '-o', str(out / 'submit-test')], check=True)
subprocess.run([str(out / 'submit-test')], check=True)
