#!/usr/bin/env python3
"""Measure RMM GPU lease capacity around one Realm workload under a lab lease."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--monitor', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    run_id = os.getenv('RUN_ID', '')
    output = ROOT / 'build/lab-runs' / run_id
    state = output / 'result.json'
    if not run_id or not state.is_file() or not command:
        parser.error('run a workload through lab-run.py')
    if json.loads(state.read_text()).get('status') != 'RUNNING':
        parser.error('matching lab run is not active')
    resources = runpy.run_path(str(ROOT / 'scripts/maintenance/lab-resources.py'))
    ssh, env = resources['ssh']('rk')

    def remote(command, **kwargs):
        return subprocess.run(ssh + [command], env=env, check=True, **kwargs)

    target = f'/root/GPU-SFTP/log/lease-monitor/{run_id}/opencca_lease_monitor.ko'
    digest = hashlib.sha256(args.monitor.read_bytes()).hexdigest()
    record = {'run_id': run_id, 'monitor_sha256': digest, 'command': command}
    before = remote('dmesg', capture_output=True).stdout
    remote('mkdir -p ' + shlex.quote(str(Path(target).parent)))
    with args.monitor.open('rb') as source:
        remote('cat > ' + shlex.quote(target), stdin=source)
    actual = remote('sha256sum ' + shlex.quote(target), capture_output=True,
                    text=True).stdout.split()[0]
    if actual != digest:
        raise RuntimeError('lease monitor upload hash mismatch')
    remote('insmod ' + shlex.quote(target))
    try:
        record['workload_returncode'] = subprocess.run(command, cwd=ROOT).returncode
    finally:
        remote('rmmod opencca_lease_monitor')
        after = remote('dmesg', capture_output=True).stdout
        wrapped = not after.startswith(before)
        delta = after[len(before):] if not wrapped else after
        (output / 'lease-monitor-dmesg.log').write_bytes(delta)
        match = re.search(rb'\[GPU_LEASE_MONITOR\] peak=(\d+) final=(\d+) '
                          rb'dma_final=(\d+) errors=(\d+)', delta)
        record['dmesg_ring_wrapped'] = wrapped
        if match:
            record.update(zip(('peak', 'final', 'dma_final', 'errors'),
                              map(int, match.groups())))
        record['monitor_pass'] = bool(match and not wrapped and
                                      all(record[key] == 0 for key in
                                          ('final', 'dma_final', 'errors')))
        (output / 'lease-monitor.json').write_text(json.dumps(record, indent=2) + '\n')
    return record['workload_returncode'] or (0 if record['monitor_pass'] else 1)


if __name__ == '__main__':
    raise SystemExit(main())
