#!/usr/bin/env python3
"""Actual RSI dispatcher + actual GPU cores; synthetic REC/RTT/device adapters."""
import argparse
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=root / 'build/rmm-client-bo-20261030/domain-rsi-unit')
parser.add_argument('--prepare-only', action='store_true')
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
source = (rmm / 'runtime/rsi/opencca_gpu_private.c').read_text()

def function(name):
    # Both functions are top-level void definitions; nested blocks are indented.
    start = source.index(('static ' if name == 'task_heap_call' else '') + 'void ' + name + '(')
    end = source.index('\n}', start) + 2
    return source[start:end]

(out / 'opencca_gpu_domain_dispatch.inc').write_text(
    '\n'.join(function(name) for name in ('task_heap_call', 'handle_rsi_opencca_gpu_private')) + '\n')
if not args.prepare_only:
    includes = ['runtime/tests/mmio-stubs', 'runtime/include', 'ext/mbedtls/include', 'ext/mbedtls/library']
    sources = ['plat/rk3588/src/rk3588_gpu.c', 'runtime/core/opencca_gpu.c',
               'runtime/core/opencca_gpu_lease.c', 'runtime/core/opencca_gpu_private.c',
               'runtime/core/opencca_gpu_firmware.c', 'ext/mbedtls/library/sha256.c',
               'ext/mbedtls/library/platform_util.c', 'runtime/tests/opencca_gpu_backend_test.c']
    cmd = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-g',
           '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
           '-DGPU_DOMAIN_RSI_TEST', '-I' + str(out)]
    cmd += ['-I' + str(rmm / p) for p in includes] + [str(rmm / p) for p in sources]
    subprocess.run(cmd + ['-o', str(out / 'test')], check=True)
    subprocess.run([str(out / 'test'), str(root / 'GPU-SFTP/panthor_fw/mali_csffw.bin'), '--domain-only'], check=True)
