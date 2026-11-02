#!/usr/bin/env python3
"""Run actual private VM_BIND driver functions with host kernel/DRM/RPC doubles.

Tests control flow, input ownership, fences and failure cleanup. This does not
prove Linux concurrency, actual RSI, native Panthor service or GPU execution.
"""
from pathlib import Path
import os, re, subprocess
root = Path(__file__).resolve().parents[2]
guest = root/'Linux-Guest-GPU'
out = root/'build/rmm-client-bo-20261030/private-bind-unit'
out.mkdir(parents=True, exist_ok=True)
source = (guest/'drivers/gpu/drm/panthor-client/panthor_client_drv.c').read_text()
wire = (guest/'include/linux/panthor_vmshm.h').read_text()
def function(name):
    match = re.search(r'\b'+re.escape(name)+r'\s*\(', source)
    assert match, name
    start = source.rfind('\n', 0, match.start())+1
    if not source[start:match.start()].strip():
        start = source.rfind('\n', 0, start-1)+1
    end = source.index('\n}', match.end())+2
    return source[start:end]+'\n'
def structure(name):
    match = re.search(r'^struct '+name+r' \{', wire, re.M)
    assert match, name
    return wire[match.start():wire.index('\n};', match.end())+3]+'\n'
(out/'wire.inc').write_text('\n'.join(structure(n) for n in (
    'panthor_vmshm_vm_bind_op','panthor_vmshm_vm_bind_sync','panthor_vmshm_vm_bind_req','panthor_vmshm_vm_bind_rsp')))
start = source.index('#define PANTHOR_CLIENT_PRIVATE_BATCH_LIMIT')
end = source.index('static int panthor_client_vm_bind(', start)
parts = [function('panthor_client_check_group_submit_sync_op'),function('panthor_client_copy_vm_bind_ops'),source[start:end]]
(out/'actual.inc').write_text('\n'.join(parts))
subprocess.run([os.environ.get('HOST_CC','cc'),'-std=gnu11','-Wall','-Wextra','-Werror',
    '-Wno-unused-parameter','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
    '-D__user=','-I'+str(out),'-iquote',str(guest/'include/uapi'),
    str(root/'GPU-SFTP/tests/gpu-private-bind/bind-test.c'),'-o',str(out/'bind-test')],check=True)
subprocess.run([str(out/'bind-test')],check=True)
