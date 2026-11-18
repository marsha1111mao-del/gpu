#!/usr/bin/env python3
"""Exercise private GROUP_GET_STATE and its actual RMM wrapper with doubles.

Checks native status-query compatibility and failure propagation. This does
not replace real RMM ownership checks, device observation or GPU completion.
"""
import argparse
import os
from pathlib import Path
import subprocess

from gpu_c_source import extract_c_function

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, default=ROOT/'build/rmm-client-bo-20261030/group-state-unit')
p.add_argument('--client-source', type=Path,
               default=ROOT/'Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c')
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)


kernel = (ROOT/'Linux-Guest-GPU/drivers/char/realm_gpu.c').read_text()
client = a.client_source.read_text()
structures = []
for source, name in [(kernel, 'realm_gpu_group')]:
    start = source.index('struct '+name+' {')
    structures.append(source[start:source.index('\n};', start)+3])
(a.out/'structures.inc').write_text('\n'.join(structures)+'\n')
(a.out/'actual.inc').write_text(
    extract_c_function(kernel, 'realm_gpu_group_unusable') +
    extract_c_function(client, 'panthor_client_group_get_state'))
subprocess.run([os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra',
                '-Werror', '-Wno-unused-parameter', '-g', '-fsanitize=address,undefined',
                '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-I'+str(a.out),
                '-iquote', str(ROOT/'Linux-Guest-GPU/include/uapi'),
                str(ROOT/'GPU-SFTP/tests/gpu-private-submit/group-state-test.c'),
                '-o', str(a.out/'group-state-test')], check=True)
subprocess.run([str(a.out/'group-state-test')], check=True)
