#!/usr/bin/env python3
"""Exercise actual group bridge functions with host-side kernel/RSI doubles.

This checks branch/lifetime behavior, not Realm execution, Linux concurrency,
actual RMM authorization or hardware enforcement (covered separately).
"""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
out = root / 'build/rmm-client-bo-20261030/group-bridge-unit'
out.mkdir(parents=True, exist_ok=True)
guest = root / 'Linux-Guest-GPU'


def function(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*\(', source)
    assert match, name
    start = source.rfind('\n', 0, match.start()) + 1
    if source[start:match.start()].strip() == '':
        start = source.rfind('\n', 0, start - 1) + 1
    end = source.index('\n}', match.end()) + 2
    text = source[start:end]
    assert '{' in text and ';' not in text[:text.index('{')], name
    return text + '\n'


def structure(source, name):
    match = re.search(r'^struct ' + re.escape(name) + r' \{', source, re.M)
    assert match, name
    return source[match.start():source.index('\n};', match.end()) + 3] + '\n'


kernel = (guest / 'drivers/char/realm_gpu.c').read_text()
proxy = (guest / 'drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c').read_text()
wire = (guest / 'include/linux/panthor_vmshm.h').read_text()
parts = [structure(kernel, n) for n in ('realm_gpu_context', 'realm_gpu_group')]
parts += [structure(proxy, n) for n in ('panthor_proxy_vm', 'panthor_proxy_group')]
parts += [structure(wire, n) for n in ('panthor_vmshm_group_create_req', 'panthor_vmshm_group_create_rsp')]
(out / 'actual-structures.inc').write_text('\n'.join(parts))
parts = [function(kernel, n) for n in ('private_status', 'managed_context', 'managed_group', 'reap_groups', 'reap_contexts', 'realm_gpu_group_create', 'realm_gpu_group_handle', 'realm_gpu_group_configure', 'realm_gpu_group_put', 'realm_gpu_context_put')]
parts += [function(proxy, n) for n in ('panthor_proxy_session_translate_group_locked', 'panthor_proxy_session_group_create', 'panthor_proxy_session_group_destroy')]
(out / 'actual-functions.inc').write_text('\n'.join(parts))
cc = os.environ.get('HOST_CC', 'cc')
subprocess.run([cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-D__user=', '-I' + str(out), '-iquote', str(guest / 'include/uapi'), str(root / 'GPU-SFTP/tests/gpu-group-bridge/group-bridge-test.c'), '-o', str(out / 'group-bridge-test')], check=True)
subprocess.run([str(out / 'group-bridge-test')], check=True)
