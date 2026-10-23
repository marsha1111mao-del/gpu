#!/usr/bin/env python3
"""Collect Host XSHM wake and scheduler samples around a leased workload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    run_id = os.environ.get('RUN_ID', '')
    output = ROOT / 'build/lab-runs' / run_id
    state = output / 'result.json'
    if not run_id or not state.is_file() or not command:
        parser.error('run a workload under lab-run.py')
    if json.loads(state.read_text()).get('status') != 'RUNNING':
        parser.error('matching lab run is not active')
    resources = runpy.run_path(str(ROOT / 'scripts/maintenance/lab-resources.py'))
    ssh, env = resources['ssh']('rk')

    def remote(command, **kwargs):
        return subprocess.run(ssh + [command], env=env, check=True, **kwargs)

    target = f'/root/GPU-SFTP/log/notify-trace/{run_id}/xshm_notify_trace.ko'
    data = args.module.read_bytes()
    record = {'run_id': run_id, 'module_sha256': hashlib.sha256(data).hexdigest(),
              'command': command}
    remote('test ! -d /sys/module/xshm_notify_trace && mkdir -p ' +
           shlex.quote(str(Path(target).parent)))
    remote('cat > ' + shlex.quote(target), input=data)
    actual = remote('sha256sum ' + shlex.quote(target), capture_output=True,
                    text=True).stdout.split()[0]
    if actual != record['module_sha256']:
        raise RuntimeError('Host trace module hash mismatch')
    remote('insmod ' + shlex.quote(target))
    try:
        record['workload_returncode'] = subprocess.run(command, cwd=ROOT).returncode
    finally:
        try:
            trace = remote('cat /sys/kernel/debug/xshm_notify_trace/samples',
                           capture_output=True).stdout
            (output / 'host-notify-trace.log').write_bytes(trace)
            record['trace_sha256'] = hashlib.sha256(trace).hexdigest()
        finally:
            remote('rmmod xshm_notify_trace')
            (output / 'host-notify-trace.json').write_text(json.dumps(record, indent=2) + '\n')
    return record['workload_returncode']


if __name__ == '__main__':
    raise SystemExit(main())
