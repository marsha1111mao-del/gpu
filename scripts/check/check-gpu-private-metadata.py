#!/usr/bin/env python3
"""Exercise actual native private GPUVA callbacks with MMIO/page-table doubles.

Checks that metadata updates never edit hardware mappings. No Linux concurrency
or hardware execution is modeled here.
"""
from pathlib import Path
import argparse, os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=root / 'build/client-direct-map-20261102/native-metadata')
out = parser.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=True)
source = (root / 'Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c').read_text()
parts = []
for name in ('panthor_vm_flush_range', 'panthor_vm_unmap_pages',
             'panthor_gpuva_sm_step_map', 'panthor_vm_bind_check_metadata'):
    match = re.search(r'^static int ' + name + r'\(', source, re.M)
    assert match, name
    parts.append(source[match.start():source.index('\n}', match.end()) + 2])
(out / 'actual.inc').write_text('\n'.join(parts) + '\n')
subprocess.run([os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra',
                '-Werror', '-Wno-unused-parameter', '-g', '-fsanitize=address,undefined',
                '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-I' + str(out),
                str(root / 'GPU-SFTP/tests/gpu-private-bind/metadata-test.c'),
                '-o', str(out / 'test')], check=True)
subprocess.run([str(out / 'test')], check=True)
