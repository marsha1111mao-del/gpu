#!/usr/bin/env python3
"""Deploy a frozen Realm test bundle and run it under the lab lease."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shlex
import subprocess
import stat
import struct

ROOT = Path(__file__).resolve().parents[2]


def private_initrd_inputs(path, workload=None, profiles=None):
    """Validate required private-mode inputs before uploading anything.

    This checks packaging/version mistakes, not attestation. RMM independently
    verifies firmware and actual service isolation at runtime.
    """
    data = path.read_bytes()
    if not data or len(data) % 4096:
        raise ValueError('private initrd must be padded to 4096 bytes')
    needed = {'init', 'realm-gpu-private', 'mali_csffw.bin'}
    if workload:
        needed.update(('glmark.env', 'gpu-smoke.sh'))
    if workload == 'compute':
        needed.add('gles-compute-smoke')
    if profiles:
        needed.add('performance-suite.sh')
        if any(profile.startswith(('ml-', 'attention-')) for profile in profiles):
            needed.add('gles-ml-smoke')
    position, names, required = 0, set(), {}
    while True:
        if data[position:position + 6] != b'070701' or position + 110 > len(data):
            raise ValueError('invalid/truncated private initrd header')
        fields = [int(data[position + 6 + 8 * i:position + 14 + 8 * i], 16)
                  for i in range(13)]
        mode, size, name_size = fields[1], fields[6], fields[11]
        start = position + 110
        end = start + name_size
        if not name_size or end > len(data):
            raise ValueError('invalid private initrd name length')
        encoded = data[start:end]
        if encoded[-1:] != b'\0' or b'\0' in encoded[:-1]:
            raise ValueError('invalid private initrd name')
        name = encoded[:-1].decode()
        if name in names:
            raise ValueError('duplicate private initrd entry: ' + name)
        names.add(name)
        body = (end + 3) & ~3
        following = (body + size + 3) & ~3
        if following > len(data) or any(data[end:body]) or any(data[body + size:following]):
            raise ValueError('invalid private initrd payload or padding')
        payload = data[body:body + size]
        if name == 'TRAILER!!!':
            if mode or size or any(data[following:]):
                raise ValueError('invalid private initrd trailer')
            break
        if name in needed:
            if not stat.S_ISREG(mode) or fields[4] != 1:
                raise ValueError('private input must be an ordinary file: ' + name)
            if name in ('init', 'realm-gpu-private', 'gles-ml-smoke', 'gles-compute-smoke'):
                if not mode & 0o111 or len(payload) < 20 or payload[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', payload, 18)[0] != 183:
                    raise ValueError('private tool must be executable AArch64 ELF: ' + name)
            elif name == 'mali_csffw.bin' and (size != 274432 or hashlib.sha256(payload).hexdigest() != '43c3c36b914c031d88ae152fd89019d8f99ad41d9879fb5ab7496ed13f7b378b'):
                raise ValueError('private initrd firmware differs from RMM allowlist')
            elif name.endswith('.sh') and (not size or not mode & 0o111):
                raise ValueError('private workload script must be executable: ' + name)
            if name == 'init' and b'/realm-gpu-private\0' not in payload:
                raise ValueError('init lacks gpu-private command dispatch')
            if name == 'init' and workload == 'compute' and b'compute-eventfd\0' not in payload:
                raise ValueError('init lacks compute-eventfd command dispatch')
            if name == 'gles-compute-smoke' and b'--gpu-eventfd\0' not in payload:
                raise ValueError('compute tool lacks GPU eventfd mode')
            if name == 'realm-gpu-private' and b'mode-check\0' not in payload:
                raise ValueError('private tool lacks actual driver-mode checking')
            required[name] = {'bytes': size, 'sha256': hashlib.sha256(payload).hexdigest(),
                              'mode': oct(mode)}
        position = following
    if set(required) != needed:
        raise ValueError('private initrd missing required inputs: ' + ', '.join(sorted(needed - set(required))))
    return required


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--images', type=Path, required=True,
               help='Frozen client-Image, proxy-Image, initrd.cpio, runner.py and hashes.json')
p.add_argument('--workload', choices=('events', 'compute', 'glmark'), default='compute')
p.add_argument('--private-gpu', action='store_true', help='Require RMM-controlled GPU execution and Client-private data; frozen initrd must include private tools and pinned firmware')
p.add_argument('--performance', action='store_true', help='Controlled 600 MHz / separate CPU performance profile')
p.add_argument('--benchmark-only', action='store_true', help='Only full glmark over the real RMM transport')
p.add_argument('--suite', action='store_true', help='Remeasure the common performance suite (requires glmark benchmark profile)')
p.add_argument('--large-pool', action='store_true', help='Opt into bounded 512 MiB pool / 1024 MiB Realms; requires updated RMM')
p.add_argument('--clients', type=int, choices=(1, 2, 3, 4), help='Concurrent benchmark Clients; compute uses two')
p.add_argument('--compact-memory', action='store_true', help='Size benchmark Realms/CMA from the selected per-Client pool')
p.add_argument('--pool-mib', type=int, choices=(128, 160, 192, 256, 336, 384), help='Per-Client benchmark pool; requires --compact-memory')
p.add_argument('--reclaim-targets', action='store_true', help='Require verified VMM reclamation and staged ResNet50 memory admission')
p.add_argument('--profiles', nargs='+', help='Explicit subset of --suite, validated by the frozen runner')
p.add_argument('--rpc-stats', action='store_true', help='Enable RPC/submission/IRQ timing in the frozen runner when supported')
p.add_argument('--transfer-capture', action='store_true', help='Enable negotiated binary TRANSFER snapshot reuse')
p.add_argument('--notify-trace', action='store_true', help='Collect RMM/notification/receive physical-counter samples')
p.add_argument('--completion-trace', action='store_true', help='Sample full native fence completion to Client proof acceptance')
p.add_argument('--client-cpu-layout', choices=('shared', 'round-robin'))
p.add_argument('--cpu-frequency-khz', type=int)
p.add_argument('--telemetry', action='store_true')
p.add_argument('--gpu-fault-isolation', action='store_true', help='Run the intentional GPU foreign-VA fault and recovery test with compute')
p.add_argument('--bo-sg-mmap', action='store_true', help='Validate fragmented BO CPU mappings with compute; requires matching runner and smoke binary')
p.add_argument('--remote-root', type=PurePosixPath, default=PurePosixPath('/root/GPU-SFTP'))
p.add_argument('--rootfs', type=PurePosixPath, help='Prepared read-only Panfrost rootfs on RK')
a = p.parse_args()
if (a.clients is not None or a.compact_memory or a.pool_mib) and not (a.workload == 'glmark' and a.benchmark_only):
    p.error('--clients/--compact-memory/--pool-mib require glmark --benchmark-only')
if a.pool_mib and not a.compact_memory:
    p.error('--pool-mib requires --compact-memory')
if a.reclaim_targets and not (a.compact_memory and a.profiles == ['ncnn-resnet50']):
    p.error('--reclaim-targets requires compact memory and only ncnn-resnet50')
if a.compact_memory and a.large_pool:
    p.error('--compact-memory and --large-pool are mutually exclusive')
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
if a.gpu_fault_isolation and a.workload != 'compute':
    p.error('--gpu-fault-isolation requires --workload compute')
if a.bo_sg_mmap and a.workload != 'compute':
    p.error('--bo-sg-mmap requires --workload compute')
if a.private_gpu and (a.workload == 'events' or a.large_pool or a.compact_memory or
        a.reclaim_targets or a.transfer_capture or a.completion_trace or
        a.bo_sg_mmap or a.gpu_fault_isolation):
    p.error('--private-gpu requires a GPU workload without shared-data profiles/cookie traces/fault probes')
if a.private_gpu and a.suite and (not a.profiles or not (
        a.profiles in (['glmark-720'], ['glmark-1080']) or
        all(profile.startswith(('ml-', 'attention-', 'ncnn-')) for profile in a.profiles))):
    p.error('--private-gpu suite requires one full glmark profile or explicit ML profiles')
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

private_inputs = None
if a.private_gpu:
    try:
        private_inputs = private_initrd_inputs(a.images/'initrd.cpio', a.workload, a.profiles)
    except (ValueError, UnicodeError, OSError) as exc:
        p.error(str(exc))
    if not re.search(rb"p.add_argument\(['\"]--private-gpu['\"]", (a.images/'runner.py').read_bytes()):
        p.error('frozen runner does not support --private-gpu')

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
if a.private_gpu:
    command += ['--private-gpu']
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
if a.clients is not None:
    command += ['--clients', str(a.clients)]
if a.compact_memory:
    command += ['--compact-memory']
if a.reclaim_targets:
    command += ['--reclaim-targets']
if a.rpc_stats:
    command += ['--rpc-stats']
if a.transfer_capture:
    command += ['--transfer-capture']
if a.notify_trace:
    command += ['--notify-trace']
if a.completion_trace:
    command += ['--completion-trace']
if a.client_cpu_layout:
    command += ['--client-cpu-layout', a.client_cpu_layout]
if a.cpu_frequency_khz is not None:
    command += ['--cpu-frequency-khz', str(a.cpu_frequency_khz)]
if a.telemetry:
    command += ['--telemetry']
if a.gpu_fault_isolation:
    command += ['--gpu-fault-isolation']
if a.bo_sg_mmap:
    command += ['--bo-sg-mmap']
if a.workload != 'events':
    rootfs = a.rootfs or a.remote_root/'firecracker-bins/rootfs/rootfs-panfrost.ext4'
    remote('test -r '+shlex.quote(str(rootfs)))
    command += ['--transport', '--gpu-flow', '--pin-cpus']
    if a.workload == 'glmark':
        pool_pages = (2049 if a.private_gpu else
                      (a.pool_mib or 128)*256 if a.compact_memory else (131072 if a.large_pool else 65536))
        command += ['--memory-pages', str(pool_pages), '--glmark-rootfs', str(rootfs)]
    else:
        command += ['--memory-pages', '2049', '--clients', '2', '--compute-rootfs', str(rootfs)]
evidence.write_text(json.dumps({'run_id': run_id, 'inputs': inputs,
                               'command': command, 'private_gpu': a.private_gpu,
                               'private_initrd_inputs': private_inputs}, indent=2)+'\n')
host_before = remote('dmesg', capture_output=True).stdout
evidence.with_name('host-dmesg-before.log').write_bytes(host_before)
returncode = subprocess.run(ssh+[shlex.join(command)], env=env).returncode
host_after = remote('dmesg', capture_output=True).stdout
evidence.with_name('host-dmesg-after.log').write_bytes(host_after)
wrapped = not host_after.startswith(host_before)
delta = host_after[len(host_before):] if not wrapped else host_after
errors = re.findall(
    r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel|Kernel panic|Out of memory|oom-kill:|RMM GPU release failed)[^\r\n]*',
    delta.decode(errors='replace'))
health = {'status': 'FAIL' if wrapped or errors else 'PASS',
          'dmesg_ring_wrapped': wrapped, 'errors': errors,
          'realm_runner_returncode': returncode}
evidence.with_name('host-kernel-health.json').write_text(json.dumps(health, indent=2)+'\n')
raise SystemExit(returncode or (1 if health['status'] != 'PASS' else 0))
