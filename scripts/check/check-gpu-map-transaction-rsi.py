#!/usr/bin/env python3
"""Exercise actual mapping transaction RSI dispatch with the GPU core fixture."""
import argparse
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
subprocess.run(['python3', str(root / 'scripts/check/check-gpu-domain-dispatch.py'),
                '--out', str(out), '--prepare-only'], check=True)
includes = ['runtime/tests/mmio-stubs', 'runtime/tests', 'runtime/include',
            'ext/mbedtls/include', 'ext/mbedtls/library']
sources = ['plat/rk3588/src/rk3588_gpu.c', 'runtime/core/opencca_gpu.c',
           'runtime/core/xshm_endpoint.c',
           'runtime/core/opencca_gpu_lease.c', 'runtime/core/opencca_gpu_private.c',
           'runtime/core/opencca_gpu_firmware.c', 'ext/mbedtls/library/sha256.c',
           'ext/mbedtls/library/platform_util.c',
           'runtime/tests/opencca_gpu_map_transaction_rsi_test.c']
cmd = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-g',
       '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
       '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
       '-DGPU_DOMAIN_RSI_TEST', '-I' + str(out)]
cmd += ['-I' + str(rmm / p) for p in includes]
cmd += [str(rmm / p) for p in sources] + ['-o', str(out / 'test')]
records = []
for name, command in [('build', cmd)] + [(str(i), [str(out / 'test'), str(i)]) for i in range(3)]:
    log = out / (name + '.log')
    with log.open('w') as stream:
        done = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    records.append(dict(name=name, command=command, exit_code=done.returncode, log=str(log)))
    (out / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
    if done.returncode:
        raise SystemExit(f'MAP_TRANSACTION_RSI FAIL {name}: rc={done.returncode}, log={log}')
print('MAP_TRANSACTION_RSI=PASS scenarios=3; actual dispatcher/core, modeled REC/RTT/device')
