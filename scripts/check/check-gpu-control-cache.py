#!/usr/bin/env python3
"""Test actual RMM control-read and full-page data synchronization callbacks.

Only the slot/granule operations and noncoherent memory are modeled. The actual
cache helper assembly rounds the requested range to architectural cache lines;
this host model does not execute DC IVAC or prove physical isolation.
"""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
out = Path(os.environ.get('GPU_CONTROL_CACHE_TEST_OUT',
                         root / 'build/rmm-client-bo-20261030/control-cache-unit'))
out.mkdir(parents=True, exist_ok=True)
source = (rmm / 'runtime/rsi/opencca_gpu_private.c').read_text()
functions = []
for name in ('read_page', 'sync_page_for_device', 'sync_page_for_cpu'):
    match = re.search(r'^static bool ' + name + r'\([^;{}]*\)\s*\{', source, re.M)
    assert match, name
    end = source.index('\n}', match.end()) + 2
    functions.append(source[match.start():end])
(out / 'control-cache.inc').write_text('\n\n'.join(functions) + '\n')
# Both the retained whole-page callback and the experimental range callback
# must obey the same freshness/order contract. Range size is not a GPU timing
# prediction; the whole-page baseline remains valid when a trial is withdrawn.
if 'inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);' in functions[0]:
    mode = 'full-reference'
else:
    assert 'inv_dcache_range((uintptr_t)memory + offset, bytes);' in functions[0]
    mode = 'range'
binary = out / 'control-cache-test'
subprocess.run([os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
                '-Werror', '-O2', '-g', '-fsanitize=address,undefined',
                '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-I' + str(out),
                str(rmm / 'runtime/tests/opencca_gpu_control_cache_test.c'),
                '-o', str(binary)], check=True)
subprocess.run([str(binary), mode], check=True)
