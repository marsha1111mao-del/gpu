#!/usr/bin/env python3
"""Deploy a frozen Realm test bundle and run it under the lab lease."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--images', type=Path, required=True,
               help='Frozen client-Image, proxy-Image, initrd.cpio, runner.py and hashes.json')
p.add_argument('--workload', choices=('events', 'compute', 'glmark'), default='compute')
p.add_argument('--performance', action='store_true', help='Controlled 600 MHz / separate CPU performance profile')
p.add_argument('--benchmark-only', action='store_true', help='Only full glmark over the real RMM transport')
p.add_argument('--suite', action='store_true', help='Remeasure the common performance suite (requires glmark benchmark profile)')
p.add_argument('--large-pool', action='store_true', help='Opt into bounded 512 MiB pool / 1024 MiB Realms; requires updated RMM')
p.add_argument('--profiles', nargs='+', help='Explicit subset of --suite, validated by the frozen runner')
p.add_argument('--rpc-stats', action='store_true', help='Enable RPC/submission/IRQ timing in the frozen runner when supported')
p.add_argument('--remote-root', type=PurePosixPath, default=PurePosixPath('/root/GPU-SFTP'))
p.add_argument('--rootfs', type=PurePosixPath, help='Prepared read-only Panfrost rootfs on RK')
a = p.parse_args()
if a.profiles and not a.suite:
    p.error('--profiles requires --suite')
if a.large_pool and (a.workload != 'glmark' or not a.benchmark_only):
    p.error('--large-pool requires --workload glmark --benchmark-only')
if a.suite and (a.workload != 'glmark' or not a.benchmark_only):
    p.error('--suite requires --workload glmark --benchmark-only')
if a.benchmark_only and a.workload != 'glmark':
    p.error('--benchmark-only requires --workload glmark')
if a.performance and a.workload == 'events':
    p.error('--performance requires a GPU workload')
run_id = os.getenv('RUN_ID', '')
if not run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '0':
    p.error('run through scripts/maintenance/lab-run.py without --allow-rk-reboot')
if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run_id):
    p.error('invalid RUN_ID')
if not a.remote_root.is_absolute() or (a.rootfs and not a.rootfs.is_absolute()):
    p.error('remote paths must be absolute')
evidence = ROOT/'build/lab-runs'/run_id/'realm-launch.json'
state = evidence.with_name('result.json')
if not state.is_file() or json.loads(state.read_text()).get('status') != 'RUNNING':
    p.error('matching lab wrapper is not running')
if evidence.exists():
    p.error('refusing to reuse Realm launch evidence')

manifest = json.loads((a.images/'hashes.json').read_text())
files = [('client-Image', 'firecracker-bins/kernels/realm-xshm/Image'),
         ('initrd.cpio', 'firecracker-bins/kernels/realm-xshm/initrd.cpio'),
         ('runner.py', 'tests/realm-xshm/run-realms.py')]
if a.workload != 'events':
    files.append(('proxy-Image', 'firecracker-bins/kernels/realm-xshm/proxy/Image'))
inputs = []
for name, target in files:
    source = a.images/name
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest.get(name) != digest:
        p.error(f'frozen input hash mismatch: {source}')
    inputs.append({'source': str(source.resolve()), 'target': str(a.remote_root/target),
                   'sha256': digest})

resources = runpy.run_path(str(ROOT/'scripts/maintenance/lab-resources.py'))
ssh, env = resources['ssh']('rk')
def remote(command, **kwargs):
    return subprocess.run(ssh+[command], env=env, check=True, **kwargs)

for item in inputs:
    target = shlex.quote(item['target'])
    probe = remote('if test -f '+target+'; then sha256sum '+target+'; fi',
                   capture_output=True, text=True).stdout.split()
    item['uploaded'] = not probe or probe[0] != item['sha256']
    if item['uploaded']:
        remote('mkdir -p '+shlex.quote(str(PurePosixPath(item['target']).parent)))
        with Path(item['source']).open('rb') as source:
            remote('cat > '+target, stdin=source)
        actual = remote('sha256sum '+target, capture_output=True, text=True).stdout.split()[0]
        if actual != item['sha256']:
            raise RuntimeError('remote hash mismatch: '+item['target'])

command = ['python3', str(a.remote_root/'tests/realm-xshm/run-realms.py'),
           '--root', str(a.remote_root), '--run-id', run_id,
           '--trusted-events', '--parallel-boot']
if a.performance:
    command += ['--performance']
if a.benchmark_only:
    command += ['--benchmark-only']
if a.suite:
    command += ['--suite']
if a.profiles:
    command += ['--profiles'] + a.profiles
if a.large_pool:
    command += ['--large-pool']
if a.rpc_stats:
    command += ['--rpc-stats']
if a.workload != 'events':
    rootfs = a.rootfs or a.remote_root/'firecracker-bins/rootfs/rootfs-panfrost.ext4'
    remote('test -r '+shlex.quote(str(rootfs)))
    command += ['--transport', '--gpu-flow', '--pin-cpus']
    if a.workload == 'glmark':
        command += ['--memory-pages', '131072' if a.large_pool else '65536', '--glmark-rootfs', str(rootfs)]
    else:
        command += ['--memory-pages', '2049', '--clients', '2', '--compute-rootfs', str(rootfs)]
evidence.write_text(json.dumps({'run_id': run_id, 'inputs': inputs,
                               'command': command}, indent=2)+'\n')
raise SystemExit(subprocess.run(ssh+[shlex.join(command)], env=env).returncode)
