#!/usr/bin/env python3
"""Verify the RMM VMID partition through direct RMI calls under the lab lease."""
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--module', type=Path, required=True)
args = parser.parse_args()
run_id = os.getenv('RUN_ID', '')
if not run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '0':
    parser.error('requires lab-run.py without --allow-rk-reboot')
if args.module.name != 'opencca_vmid_probe.ko':
    parser.error('module must be opencca_vmid_probe.ko')
output = ROOT/'build/lab-runs'/run_id
if json.loads((output/'result.json').read_text()).get('status') != 'RUNNING':
    parser.error('matching lab wrapper is not running')
resources = runpy.run_path(str(ROOT/'scripts/maintenance/lab-resources.py'))
arguments, environment = resources['ssh']('rk')
target = '/root/GPU-SFTP/log/vmid/'+run_id+'/opencca_vmid_probe.ko'
module_directory = '/sys/module/opencca_vmid_probe'
result = {'run_id': run_id, 'status': 'NOT_RUN',
          'module_sha256': hashlib.sha256(args.module.read_bytes()).hexdigest()}


def ssh(command, **kwargs):
    return subprocess.run(arguments+[command], env=environment, check=True,
                           timeout=30, **kwargs)


owned = False
before = None
try:
    ssh('test ! -d '+module_directory, capture_output=True)
    before = ssh('dmesg', capture_output=True).stdout
    ssh('mkdir -p '+shlex.quote(str(Path(target).parent)), capture_output=True)
    with args.module.open('rb') as stream:
        ssh('cat > '+shlex.quote(target), stdin=stream)
    actual = ssh('sha256sum '+shlex.quote(target), capture_output=True, text=True).stdout.split()[0]
    if actual != result['module_sha256']:
        raise RuntimeError('module upload hash mismatch')
    release = ssh('uname -r', capture_output=True, text=True).stdout.strip()
    vermagic = ssh('modinfo -F vermagic '+shlex.quote(target), capture_output=True, text=True).stdout.split()[0]
    if vermagic != release:
        raise RuntimeError('module release mismatch')
    owned = True
    ssh('insmod '+shlex.quote(target), capture_output=True)
    result['status'] = 'PASS'
except (OSError, RuntimeError, subprocess.SubprocessError) as error:
    result['status'] = 'FAIL'
    result['error'] = str(error)
finally:
    if owned:
        try:
            ssh('if test -d '+module_directory+'; then rmmod opencca_vmid_probe; fi', capture_output=True)
            result['module_cleanup'] = 'PASS'
        except subprocess.SubprocessError as error:
            result['module_cleanup'] = 'FAIL'
            result['status'] = 'FAIL'
            result['cleanup_error'] = str(error)
    try:
        after = ssh('dmesg', capture_output=True).stdout
        (output/'kernel-dmesg.log').write_bytes(after)
        if before is None or not after.startswith(before):
            raise RuntimeError('kernel log baseline missing or wrapped')
        delta = after[len(before):].decode(errors='replace')
        (output/'vmid-probe.log').write_text(delta)
        checks = ('host_zero_denied', 'ordinary_upper_denied', 'realm_lower_allowed',
                  'duplicate_denied', 'destroy_allows_reuse', 'realm_upper_allowed')
        result['checks'] = {name: f'[VMID_TEST] {name}=PASS ' in delta for name in checks}
        result['kernel_errors'] = re.findall(r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel)[^\r\n]*', delta)
        if not all(result['checks'].values()) or result['kernel_errors'] or not re.search(
                r'\[VMID_TEST\] result=PASS bits=(8|16) cleanup=PASS', delta):
            raise RuntimeError('VMID checks, trusted cleanup or kernel health failed')
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        result['status'] = 'FAIL'
        result['verification_error'] = str(error)
    (output/'vmid.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
