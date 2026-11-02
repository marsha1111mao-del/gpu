#!/usr/bin/env python3
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    run_id = os.environ.get('RUN_ID', '')
    output = ROOT / 'build/lab-runs' / run_id
    if not run_id or not command or not (output / 'result.json').is_file():
        parser.error('requires an active lab-run and a workload command')
    if json.loads((output / 'result.json').read_text())['status'] != 'RUNNING':
        parser.error('matching lab-run is not running')
    resources = runpy.run_path(str(ROOT / 'scripts/maintenance/lab-resources.py'))
    ssh, environment = resources['ssh']('rk')

    def remote(command, **kwargs):
        return subprocess.run(ssh + [command], env=environment, check=True, **kwargs)

    remote('test ! -d /sys/module/xshm_wake_sgi && '
           'test "$(uname -r)" = 6.12.0-opencca-pmthor-opp3')
    target = '/root/GPU-SFTP/log/fast-target-irq/' + run_id + '/xshm_wake_sgi.ko'
    digest = hashlib.sha256(args.module.read_bytes()).hexdigest()
    record = {'run_id': run_id, 'module_sha256': digest, 'command': command,
              'module_unloaded': False}
    remote('mkdir -p ' + shlex.quote(str(Path(target).parent)))
    with args.module.open('rb') as source:
        remote('cat > ' + shlex.quote(target), stdin=source)
    actual = remote('sha256sum ' + shlex.quote(target), capture_output=True,
                    text=True).stdout.split()[0]
    if actual != digest:
        raise RuntimeError('module upload hash mismatch')
    before = remote('dmesg', capture_output=True).stdout
    remote('insmod ' + shlex.quote(target))
    try:
        (output / 'sgi-interrupts-loaded.log').write_bytes(
            remote('cat /proc/interrupts', capture_output=True).stdout)
        record['workload_returncode'] = subprocess.run(command, cwd=ROOT).returncode
    finally:
        try:
            remote('! pgrep -x firecracker >/dev/null')
            (output / 'sgi-interrupts-final.log').write_bytes(
                remote('cat /proc/interrupts', capture_output=True).stdout)
            remote('rmmod xshm_wake_sgi')
            remote('test ! -d /sys/module/xshm_wake_sgi')
            record['module_unloaded'] = True
        finally:
            after = remote('dmesg', capture_output=True).stdout
            record['dmesg_ring_wrapped'] = not after.startswith(before)
            delta = after[len(before):] if not record['dmesg_ring_wrapped'] else after
            (output / 'sgi-module-dmesg.log').write_bytes(delta)
            (output / 'sgi-module.json').write_text(json.dumps(record, indent=2) + '\n')
    return record['workload_returncode'] or int(record['dmesg_ring_wrapped'])


if __name__ == '__main__':
    raise SystemExit(main())
