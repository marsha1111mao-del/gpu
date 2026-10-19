#!/usr/bin/env python3
"""Run owner OPP/reset checks and a real Realm GPU teardown under one lab lease."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

from pi_uart import PiUartCapture

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--images', type=Path, required=True,
                    help='Frozen Realm bundle accepted by run-realm-xshm.py')
parser.add_argument('--kvm-probe', type=Path, required=True,
                    help='Static opencca_kvm_mmio_probe built for RK')
parser.add_argument('--lease-monitor', type=Path, required=True,
                    help='Matching Host opencca_lease_monitor.ko')
parser.add_argument('--workload', choices=('compute',), default='compute')
parser.add_argument('--rootfs', type=Path,
                    help='Absolute prepared rootfs path on RK')
parser.add_argument('--remote-root', default='/root/GPU-SFTP')
parser.add_argument('--uart-capture', action='store_true',
                    help='Capture RK UART during KVM probe and workload teardown')
args = parser.parse_args()

run_id = os.getenv('RUN_ID', '')
if not run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '0':
    parser.error('requires scripts/maintenance/lab-run.py without --allow-rk-reboot')
outer_state = ROOT/'build/lab-runs'/run_id/'result.json'
if not outer_state.is_file() or json.loads(outer_state.read_text()).get('status') != 'RUNNING':
    parser.error('matching lab wrapper is not running')
if not args.images.is_absolute():
    args.images = args.images.resolve()
if args.rootfs is not None and not args.rootfs.is_absolute():
    parser.error('--rootfs must be an absolute path on RK')

out = ROOT/'build/lab-runs'/run_id
result_path = out/'gpu-pm-regression.json'
if result_path.exists():
    parser.error('GPU PM regression evidence already exists')
result = {
    'run_id': run_id,
    'status': 'RUNNING',
    'workload': args.workload,
    'images': str(args.images),
    'kvm_probe_sha256': hashlib.sha256(args.kvm_probe.read_bytes()).hexdigest(),
    'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'lease_monitor_sha256': hashlib.sha256(args.lease_monitor.read_bytes()).hexdigest(),
}
uart = None
if args.uart_capture:
    uart = PiUartCapture(out/'rmm-uart.log',
                         '/tmp/'+run_id+'-gpu-pm-uart-stop', 1800)


def save():
    result_path.write_text(json.dumps(result, indent=2)+'\n')


def remote(command, **kwargs):
    ssh_args, env = resources.ssh('rk')
    return subprocess.run(ssh_args+[command], env=env, **kwargs)


def capture_dmesg(name):
    proc = remote('dmesg', capture_output=True, check=True)
    data = proc.stdout
    (out/name).write_bytes(data)
    return data


def run_child(name, command):
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (out/f'{name}.log').write_text(proc.stdout+proc.stderr)
    result[name] = {'command': command, 'returncode': proc.returncode}
    return proc


save()
before = capture_dmesg('host-dmesg-before.log')
workload_command = []
monitor_loaded = False
try:
    if uart:
        uart.start()
    kvm = run_child('kvm-pm', [
        'python3', str(ROOT/'scripts/run/run-kvm-mmio-probe.py'),
        '--probe', str(args.kvm_probe),
    ])
    if kvm.returncode != 0:
        raise RuntimeError('KVM MMIO/owner PM probe failed')
    before = capture_dmesg('host-dmesg-workload-before.log')
    monitor_target = args.remote_root+'/log/gpu-pm/'+run_id+'/opencca_lease_monitor.ko'
    remote('mkdir -p '+shlex.quote(str(Path(monitor_target).parent)), check=True)
    with args.lease_monitor.open('rb') as source:
        remote('cat > '+shlex.quote(monitor_target), stdin=source, check=True)
    monitor_hash = remote('sha256sum '+shlex.quote(monitor_target),
                          capture_output=True, text=True, check=True).stdout.split()[0]
    if monitor_hash != result['lease_monitor_sha256']:
        raise RuntimeError('lease monitor upload hash mismatch')
    remote('insmod '+shlex.quote(monitor_target), check=True)
    monitor_loaded = True

    workload_command = [
        'python3', str(ROOT/'scripts/run/run-realm-xshm.py'),
        '--images', str(args.images), '--workload', args.workload,
        '--performance', '--remote-root', args.remote_root,
    ]
    if args.rootfs is not None:
        workload_command += ['--rootfs', str(args.rootfs)]
    workload = run_child('realm-workload', workload_command)
    if workload.returncode != 0:
        raise RuntimeError('Realm GPU workload failed')
    remote('rmmod opencca_lease_monitor', check=True)
    monitor_loaded = False

    after = capture_dmesg('host-dmesg-after.log')
    if not after.startswith(before):
        result['dmesg_ring_wrapped'] = True
        raise RuntimeError('Host dmesg ring wrapped; PM teardown evidence is inconclusive')
    result['dmesg_ring_wrapped'] = False
    new = after[len(before):]
    (out/'host-dmesg-new.log').write_bytes(new)
    text = new.decode(errors='replace')
    release = re.search(r'pmthor: released GPU page references=([0-9]+)', text)
    leases = re.search(r'\[GPU_LEASE_MONITOR\] peak=([0-9]+) final=([0-9]+) '
                       r'dma_final=([0-9]+) errors=([0-9]+)', text)
    quiesce = re.search(r'pmthor: RMM hardware quiesced for (last VM teardown|session release)', text)
    forbidden = re.findall(r'pmthor: RMM GPU op .* failed|pmthor: GPU reset failed|BUG:|Oops:|WARNING:', text)
    workload_summary = json.loads((out/'realm-workload.log').read_text())
    workload_completed = all(workload_summary.get(name) == 'PASS' for name in (
        'two_client_compute_check', 'two_client_gpu_flow_check', 'memory_check'))
    result['checks'] = {
        'real_workload_completed': workload_completed,
        'host_page_reference_release_logged': release is not None,
        'rmm_active_gpu_leases_observed': bool(leases and int(leases.group(1)) > 0),
        'rmm_gpu_and_dma_leases_drained': bool(leases and
                                              all(int(leases.group(index)) == 0
                                                  for index in (2, 3, 4))),
        'teardown_reset': bool(quiesce),
        'no_new_kernel_or_pm_failure': not forbidden,
    }
    result['host_released_pages_count'] = int(release.group(1)) if release else None
    result['rmm_gpu_lease_peak'] = int(leases.group(1)) if leases else None
    if forbidden:
        result['kernel_or_pm_failures'] = forbidden
    if not all(result['checks'].values()):
        raise RuntimeError('GPU PM teardown log checks failed: '+json.dumps(result['checks']))
    result['status'] = 'PASS'
except Exception as exc:
    result['status'] = 'FAIL'
    result['error'] = str(exc)
    try:
        capture_dmesg('host-dmesg-failure.log')
    except Exception as dmesg_error:
        result['dmesg_capture_error'] = str(dmesg_error)
finally:
    if monitor_loaded:
        try:
            remote('rmmod opencca_lease_monitor', check=True)
        except subprocess.SubprocessError as monitor_error:
            result['monitor_cleanup_error'] = str(monitor_error)
            result['status'] = 'FAIL'
    if uart:
        try:
            uart.stop()
        except (subprocess.SubprocessError, OSError) as uart_error:
            result['uart_cleanup_error'] = str(uart_error)
            result['status'] = 'FAIL'
    if not workload_command:
        workload_command = ['not reached: KVM probe failed']
    result['command_display'] = shlex.join(workload_command)
    save()

print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
