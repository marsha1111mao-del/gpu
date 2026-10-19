#!/usr/bin/env python3
"""Run the Guest RSI managed-IOMMU probe in one minimal Realm."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--run-id', required=True)
parser.add_argument('--proxy-image', type=Path, required=True)
parser.add_argument('--initrd', type=Path, required=True)
parser.add_argument('--reclaim-module', type=Path)
parser.add_argument('--assignment-module', type=Path)
parser.add_argument('--gpu-backing', action='store_true')
args = parser.parse_args()
if args.gpu_backing and not args.reclaim_module:
    parser.error('--gpu-backing requires --reclaim-module')
if args.assignment_module and args.reclaim_module:
    parser.error('--assignment-module and --reclaim-module are exclusive')

out = args.root/'log/guest-iommu'/args.run_id
out.mkdir(parents=True, exist_ok=False)
config_path = out/'realm.json'
log_path = out/'realm.log'
result_path = out/'result.json'
result = {'run_id': args.run_id, 'status': 'RUNNING', 'checks': {}}


def save():
    result_path.write_text(json.dumps(result, indent=2)+'\n')


config = {
    'boot-source': {
        'kernel_image_path': str(args.proxy_image.resolve()),
        'initrd_path': str(args.initrd.resolve()),
        'boot_args': 'console=ttyS0 rdinit=/init panic=-1 loglevel=6',
    },
    'drives': [],
    'machine-config': {
        'vcpu_count': 1,
        'mem_size_mib': 512,
        'realm_config': {
            'hash_algorithm': 'SHA256',
            'personalization_value': base64.b64encode(
                b'guest-iommu-probe'.ljust(64, b'\0')).decode(),
        },
    },
}
config_path.write_text(json.dumps(config, indent=2)+'\n')
if args.gpu_backing:
    config['machine-config']['gpu_passthrough'] = True
    config_path.write_text(json.dumps(config, indent=2)+'\n')
command = [
    str(args.root/'firecracker-bins/bin/firecracker'),
    '--no-api', '--no-seccomp', '--config-file', str(config_path),
    '--id', 'guest-iommu-'+args.run_id,
]


def command_output(process, pending, command, timeout=120):
    process.stdin.write((command+'\n').encode())
    process.stdin.flush()
    deadline = time.monotonic()+timeout
    data, pending = read_until_stream(process, pending, b'XSHM_COMMAND_EXIT=', deadline)
    while b'\n' not in pending:
        pending += process.stdout.read1(65536)
    exit_bytes, pending = pending.split(b'\n', 1)
    match = re.fullmatch(rb'([0-9]{1,3})(?:\[\s*[0-9]+\.[0-9]+\].*)?',
                         exit_bytes.strip().strip(b'\r'))
    if not match:
        raise RuntimeError('malformed Realm command exit: '+repr(exit_bytes))
    return data, int(match.group(1)), pending


def read_until_stream(process, pending, marker, deadline):
    data = pending
    while marker not in data:
        if time.monotonic() >= deadline:
            raise TimeoutError('timeout waiting for '+marker.decode())
        chunk = process.stdout.read1(65536)
        if not chunk:
            raise RuntimeError('Realm exited while waiting for '+marker.decode())
        data += chunk
        log_path.open('ab').write(chunk)
    before, pending = data.split(marker, 1)
    return before+marker, pending


save()
process = None
host_module_loaded = False
assignment_loaded = False
guest_module_loaded = False
host_start = None
try:
    host_start = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
    if args.gpu_backing:
        os.environ['FC_ALLOW_TRUSTED_GPU_REALM'] = '1'
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    _, pending = read_until_stream(process, b'', b'XSHM_READY', time.monotonic()+120)
    result['realm_boot'] = 'PASS'
    probe_command = 'insmod /opencca_guest_iommu_probe.ko'
    if args.reclaim_module:
        probe_command += f' hold_mapping=1 gpu_lease={int(args.gpu_backing)}'
    if args.assignment_module:
        probe_command += ' hold_mapping=1 device_test=1'
    output, result['probe_returncode'], pending = command_output(process, pending,
                                                                 probe_command)
    guest_module_loaded = result['probe_returncode'] == 0
    kernel_log, _, pending = command_output(process, pending, 'kernel-log')
    text = (output+kernel_log).decode(errors='replace')
    result['checks'] = {
        'unowned_gpu_claim_denied':
            '[GUEST_IOMMU_TEST] unowned_gpu_claim_denied=PASS' in text,
        'unowned_gpu_reset_denied':
            '[GUEST_IOMMU_TEST] unowned_gpu_reset_denied=PASS' in text,
        'version': '[GUEST_IOMMU_TEST] version=PASS' in text,
        'create': '[GUEST_IOMMU_TEST] create=PASS' in text,
        'unassigned_codec_bind_denied':
            '[GUEST_IOMMU_TEST] unassigned_codec_bind_denied=PASS' in text,
        'unpowered_vop_bind_denied':
            '[GUEST_IOMMU_TEST] unpowered_vop_bind_denied=PASS' in text,
        'unassigned_codec_fault_denied':
            '[GUEST_IOMMU_TEST] unassigned_codec_fault_denied=PASS' in text,
        'unpowered_vop_fault_denied':
            '[GUEST_IOMMU_TEST] unpowered_vop_fault_denied=PASS' in text,
        'map': '[GUEST_IOMMU_TEST] map=PASS' in text,
        'query': '[GUEST_IOMMU_TEST] query=PASS' in text,
        'destroy_denied_while_mapped':
            '[GUEST_IOMMU_TEST] destroy_denied_while_mapped=PASS' in text,
        'unmap': '[GUEST_IOMMU_TEST] unmap=PASS' in text,
        'query_after_unmap':
            '[GUEST_IOMMU_TEST] query_after_unmap=PASS' in text,
        'overflow_mapping_denied':
            '[GUEST_IOMMU_TEST] overflow_mapping_denied=PASS' in text,
        'destroy': '[GUEST_IOMMU_TEST] destroy=PASS' in text,
        'stale_handle_denied':
            '[GUEST_IOMMU_TEST] stale_handle_denied=PASS' in text,
        'result': '[GUEST_IOMMU_TEST] result=PASS' in text,
    }
    if args.assignment_module:
        match = re.search(r'backing_held=PASS ipa=0x[0-9a-f]+ gpu=0 domain=(0x[0-9a-f]+)', text)
        if result['probe_returncode'] != 0 or not match:
            raise RuntimeError('Guest did not publish an assignment domain')
        _, denied, pending = command_output(process, pending, 'iommu-device 5')
        result['checks'] = {'unassigned_bind_denied': denied != 0}
        _, denied, pending = command_output(process, pending, 'iommu-device 11')
        result['checks']['unassigned_fault_denied'] = denied != 0
        attempted = subprocess.run(['insmod', str(args.assignment_module),
                                    'guest_handle='+match.group(1)], capture_output=True)
        result['assignment_module_returncode'] = attempted.returncode
        result['assignment_module_stderr'] = attempted.stderr.decode(errors='replace')
        assignment_loaded = attempted.returncode == 0
        if not assignment_loaded:
            raise RuntimeError('Host did not grant the powered codec IOMMU')
        for name, operation in [('assigned_bind', 5), ('assigned_fault', 11),
                                ('assigned_unbind', 6), ('assigned_rebind', 5)]:
            _, code, pending = command_output(process, pending, f'iommu-device {operation}')
            result['checks'][name] = code == 0
            if code:
                raise RuntimeError('Guest assignment operation failed: '+name)
        Path('/sys/module/opencca_iommu_assignment_probe/parameters/action').write_text('11')
        Path('/sys/module/opencca_iommu_assignment_probe/parameters/action').write_text('10')
        _, denied, pending = command_output(process, pending, 'iommu-device 5')
        result['checks']['revoked_bind_denied'] = denied != 0
        _, denied, pending = command_output(process, pending, 'iommu-device 11')
        result['checks']['revoked_fault_denied'] = denied != 0
        host_log = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
        if not host_log.startswith(host_start):
            raise RuntimeError('Host dmesg rotated during device assignment')
        assignment_log = host_log[len(host_start):].decode(errors='replace')
        (out/'host-assignment.log').write_text(assignment_log)
        for name in ('grant', 'host_unbind_while_granted', 'host_fault_for_parked_guest',
                     'host_fault_for_bound_guest', 'revoke'):
            result['checks'][name] = f'[IOMMU_ASSIGNMENT_TEST] {name}=PASS' in assignment_log
        subprocess.run(['rmmod', 'opencca_iommu_assignment_probe'], check=True)
        assignment_loaded = False
    if args.reclaim_module:
        match = re.search(r'backing_held=PASS ipa=(0x[0-9a-f]+)', text)
        if result['probe_returncode'] != 0 or not match:
            raise RuntimeError('Guest did not retain the test backing page')
        result['backing_kind'] = 'gpu_lease' if args.gpu_backing else 'guest_iommu'
        result['backing_ipa'] = match.group(1)
        host_before = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
        host_command = ['insmod', str(args.reclaim_module),
                        f'realm_pid={process.pid}', f'ipa={match.group(1)}']
        attempted = subprocess.run(host_command, capture_output=True)
        result['host_probe_command'] = host_command
        result['host_probe_returncode'] = attempted.returncode
        result['host_probe_stderr'] = attempted.stderr.decode(errors='replace')
        host_module_loaded = attempted.returncode == 0
        host_after = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
        if not host_after.startswith(host_before):
            raise RuntimeError('Host dmesg rotated during the reclaim probe')
        delta = host_after[len(host_before):].decode(errors='replace')
        (out/'host-reclaim.log').write_text(delta)
        result['host_kernel_errors'] = re.findall(
            r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel)[^\r\n]*', delta)
        result['checks'] = {
            'active_backing_destroy_denied':
                '[RECLAIM_TEST] active_backing_destroy_denied=PASS' in delta,
            'backing_entry_unchanged':
                '[RECLAIM_TEST] backing_entry_unchanged=PASS' in delta,
        }
        if (attempted.returncode != 0 or result['host_kernel_errors'] or
                not all(result['checks'].values())):
            raise RuntimeError('Host RMI backing-page destroy was not safely rejected')
        subprocess.run(['rmmod', 'opencca_reclaim_probe'], check=True)
        host_module_loaded = False
    cleanup_output, cleanup_code, pending = command_output(process, pending,
                                                           'rmmod opencca_guest_iommu_probe')
    result['module_cleanup_returncode'] = cleanup_code
    if cleanup_code == 0:
        guest_module_loaded = False
    if args.reclaim_module or args.assignment_module:
        released_log, _, pending = command_output(process, pending, 'kernel-log')
        result['checks']['backing_release'] = (
            '[GUEST_IOMMU_TEST] backing_release=PASS' in released_log.decode(errors='replace'))
    if (result['probe_returncode'] != 0 or cleanup_code != 0 or
            not all(result['checks'].values())):
        raise RuntimeError('Guest IOMMU probe failed: '+json.dumps(result['checks']))
    result['guest_iommu_probe'] = 'PASS'
    kernel_log, _, _ = command_output(process, pending, 'kernel-log')
    result['kernel_errors'] = re.findall(
        r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel)[^\r\n]*',
        kernel_log.decode(errors='replace'))
    if result['kernel_errors']:
        raise RuntimeError('Guest kernel errors during RSI IOMMU probe')
    result['kernel_health'] = 'PASS'
    result['status'] = 'PASS'
except Exception as exc:
    result['status'] = 'FAIL'
    result['error'] = str(exc)
finally:
    if assignment_loaded:
        result['assignment_cleanup_returncode'] = subprocess.run(
            ['rmmod', 'opencca_iommu_assignment_probe']).returncode
        if result['assignment_cleanup_returncode']:
            result['status'] = 'FAIL'
    if host_module_loaded:
        result['host_module_cleanup_returncode'] = subprocess.run(
            ['rmmod', 'opencca_reclaim_probe']).returncode
        if result['host_module_cleanup_returncode']:
            result['status'] = 'FAIL'
    if guest_module_loaded and process is not None and process.poll() is None:
        try:
            _, cleanup_code, pending = command_output(
                process, pending, 'rmmod opencca_guest_iommu_probe', timeout=30)
            result['guest_module_failure_cleanup_returncode'] = cleanup_code
            if cleanup_code:
                result['status'] = 'FAIL'
        except Exception as cleanup_error:
            result['guest_module_failure_cleanup_error'] = str(cleanup_error)
            result['status'] = 'FAIL'
    if process is not None:
        if process.poll() is None:
            try:
                process.stdin.write(b'halt\n')
                process.stdin.flush()
                process.wait(timeout=10)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        result['realm_exit_code'] = process.returncode
        if process.returncode != 0:
            result['status'] = 'FAIL'
    if host_start is not None:
        try:
            host_end = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
            if not host_end.startswith(host_start):
                raise RuntimeError('Host dmesg rotated during Realm lifecycle')
            delta = host_end[len(host_start):].decode(errors='replace')
            (out/'host-lifecycle.log').write_text(delta)
            result['host_lifecycle_errors'] = re.findall(
                r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel|RMM GPU release failed)[^\r\n]*',
                delta)
            if result['host_lifecycle_errors']:
                result['status'] = 'FAIL'
            result['host_lifecycle_health'] = 'FAIL' if result['host_lifecycle_errors'] else 'PASS'
        except (subprocess.SubprocessError, RuntimeError) as host_error:
            result['host_lifecycle_error'] = str(host_error)
            result['status'] = 'FAIL'
    result['command'] = command
    save()

print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
