#!/usr/bin/env python3
"""Check actual firmware status loads against an incoherent device double."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
out = Path(os.getenv('GPU_STREAM_STATUS_OUT', str(root / 'build/rmm-client-bo-20261030/stream-status-unit')))
out.mkdir(parents=True, exist_ok=True)
source = (rmm / 'runtime/core/opencca_gpu_firmware.c').read_text()
start = source.index('struct fw_stream_status {')
end = source.index('\n}', source.index('static void stream_status(', start)) + 2
(out / 'stream-status.inc').write_text(source[start:end] + '\n')
subprocess.run([
    os.getenv('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
    '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
    '-fno-pie', '-no-pie', '-I' + str(out),
    str(rmm / 'runtime/tests/opencca_gpu_stream_status_test.c'),
    '-o', str(out / 'stream-status-test'),
], check=True)
args = [str(out / 'stream-status-test')]
if 'ops->invalidate(output, FW_STREAM_OUTPUT_SIZE);' in source[start:end]:
    args.append('full-reference')
subprocess.run(args, check=True)
