#!/usr/bin/env python3
"""Run the minimal KVM/RMM GPU-MMIO ownership probe on the RK Host."""
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
parser.add_argument('--probe', type=Path, required=True)
parser.add_argument('--uart-capture', action='store_true',
                    help='Capture RK UART during the probe for RMI diagnostics')
audit_options = parser.add_mutually_exclusive_group()
audit_options.add_argument('--audit-host-mmio', action='store_true',
                           help='Diagnose Host /dev/mem writes in an idle assigned session; exit 2 if bypassed')
audit_options.add_argument('--kernel-mmio-module', type=Path,
                           help='Use opencca_gpu_mmio_probe.ko to diagnose Host kernel ioremap writes')
audit_options.add_argument('--ordinary-vm-probe', type=Path,
                           help='Check ordinary VM RAM execution, then physical GPU writes while a Realm owns MMIO')
args = parser.parse_args()
audit = args.audit_host_mmio or args.kernel_mmio_module is not None or args.ordinary_vm_probe is not None
protection_key = 'ordinary_vm_mmio_protection' if args.ordinary_vm_probe else 'host_mmio_protection'
if args.kernel_mmio_module and args.kernel_mmio_module.name != 'opencca_gpu_mmio_probe.ko':
    parser.error('kernel MMIO module filename must be opencca_gpu_mmio_probe.ko')

run_id = os.getenv('RUN_ID', '')
if not run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '0':
    parser.error('requires lab-run.py without --allow-rk-reboot')
out = ROOT/'build/lab-runs'/run_id
state_path = out/'result.json'
if not state_path.is_file() or json.loads(state_path.read_text()).get('status') != 'RUNNING':
    parser.error('matching lab wrapper is not running')

target = '/root/GPU-SFTP/log/kvm-mmio/'+run_id+'/opencca_kvm_mmio_probe'
checks = ['non_gpu_mmio_denied', 'misaligned_gpu_mmio_denied',
          'oversized_gpu_mmio_denied', 'undersized_gpu_mmio_denied',
          'authorized_proxy_mmio_succeeds',
          'pmthor_owner_session_opens', 'second_realm_mmio_denied',
          'owner_opp_transition_succeeds', 'pmthor_owner_release_succeeds',
          'pmthor_owner_session_reopens', 'destroy_releases_mmio_owner']
result = {'run_id': run_id, 'probe': 'NOT_RUN',
          'host_mmio_protection': 'NOT_RUN',
          'ordinary_vm_mmio_protection': 'NOT_RUN',
          'probe_sha256': hashlib.sha256(args.probe.read_bytes()).hexdigest(),
          'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'scope': 'KVM/RMM MMIO authorization, owner OPP transition and pmthor reset/release; no GPU workload or DMA'}

def ssh(command, **kwargs):
    ssh_args, env = resources.ssh('rk')
    return subprocess.run(ssh_args+[command], env=env, **kwargs)

uart = None
host_before = None
module_owned = False
module_target = str(Path(target).with_name('opencca_gpu_mmio_probe.ko'))
module_directory = '/sys/module/opencca_gpu_mmio_probe'
if args.uart_capture:
    uart = PiUartCapture(out/'rmm-uart.log',
                         '/tmp/'+run_id+'-kvm-mmio-uart-stop', 300)

try:
    host_before = ssh('dmesg', capture_output=True, check=True).stdout
    if uart:
        uart.start()
    config = ssh('zcat /proc/config.gz', text=True, capture_output=True, check=True).stdout
    if 'CONFIG_OPENCCA_MANAGED_IOMMU=y\n' not in config:
        raise RuntimeError('running Host lacks CONFIG_OPENCCA_MANAGED_IOMMU=y')
    ssh('mkdir -p '+shlex.quote(str(Path(target).parent)), check=True)
    with args.probe.open('rb') as source:
        ssh('cat > '+shlex.quote(target), stdin=source, check=True)
    remote_hash = ssh('sha256sum '+shlex.quote(target), text=True,
                      capture_output=True, check=True).stdout.split()[0]
    if remote_hash != result['probe_sha256']:
        raise RuntimeError('probe upload hash mismatch')
    probe_command = shlex.quote(target)
    if args.audit_host_mmio:
        probe_command += ' --audit-host-mmio'
    if args.ordinary_vm_probe:
        ordinary_target = str(Path(target).with_name('opencca_ordinary_mmio_probe'))
        result['ordinary_probe_sha256'] = hashlib.sha256(args.ordinary_vm_probe.read_bytes()).hexdigest()
        with args.ordinary_vm_probe.open('rb') as source:
            ssh('cat > '+shlex.quote(ordinary_target), stdin=source, check=True)
        ordinary_hash = ssh('sha256sum '+shlex.quote(ordinary_target), text=True,
                            capture_output=True, check=True).stdout.split()[0]
        if ordinary_hash != result['ordinary_probe_sha256']:
            raise RuntimeError('ordinary VM probe upload hash mismatch')
        ssh('chmod 0700 '+shlex.quote(ordinary_target), check=True)
        probe_command += ' --audit-ordinary-vm-mmio '+shlex.quote(ordinary_target)
    if args.kernel_mmio_module:
        absent = ssh('test ! -d '+module_directory)
        if absent.returncode != 0:
            raise RuntimeError('kernel MMIO probe module already loaded or state check failed')
        result['module_sha256'] = hashlib.sha256(args.kernel_mmio_module.read_bytes()).hexdigest()
        with args.kernel_mmio_module.open('rb') as source:
            ssh('cat > '+shlex.quote(module_target), stdin=source, check=True)
        module_hash = ssh('sha256sum '+shlex.quote(module_target), text=True,
                          capture_output=True, check=True).stdout.split()[0]
        if module_hash != result['module_sha256']:
            raise RuntimeError('kernel MMIO module upload hash mismatch')
        release = ssh('uname -r', text=True, capture_output=True, check=True).stdout.strip()
        vermagic = ssh('modinfo -F vermagic '+shlex.quote(module_target), text=True,
                       capture_output=True, check=True).stdout.split()[0]
        if vermagic != release:
            raise RuntimeError('kernel MMIO module release mismatch')
        probe_command += ' --audit-host-kernel-mmio '+shlex.quote(module_target)
        module_owned = True
    result['probe_command'] = probe_command
    probe = ssh('chmod 0700 '+shlex.quote(target)+' && '+probe_command,
                text=True, capture_output=True)
    result['probe_rc'] = probe.returncode
    result['stdout'] = probe.stdout
    result['stderr'] = probe.stderr
    (out/'kvm-mmio-probe.log').write_text(probe.stdout+probe.stderr)
    result['checks'] = {
        name: any(line.startswith(f'[KVM_MMIO_TEST] {name}=PASS ') for line in probe.stdout.splitlines())
        for name in checks
    }
    if audit:
        access = ('ordinary VM stage-2' if args.ordinary_vm_probe else
                  'kernel ioremap' if args.kernel_mmio_module else '/dev/mem')
        result['scope'] += '; direct Host '+access+' IRQ mask write/readback/restore in idle assigned session'
        result[protection_key] = 'NOT_PROVEN'
        marker = ('[HOST_MMIO_TEST] kernel_physical_write=FAIL_BYPASS_DETECTED restoration=PASS module_cleanup=PASS'
                  if args.kernel_mmio_module else
                  '[ORDINARY_VM_MMIO_TEST] physical_write=FAIL_BYPASS_DETECTED restoration=PASS'
                  if args.ordinary_vm_probe else
                  '[HOST_MMIO_TEST] physical_write=FAIL_BYPASS_DETECTED restoration=PASS')
        if marker in probe.stdout:
            result[protection_key] = 'FAIL_BYPASS_DETECTED'
        if args.kernel_mmio_module and (
                '[HOST_MMIO_TEST] kernel_physical_write=DENIED '
                'restoration=NOT_APPLICABLE module_cleanup=PASS') in probe.stdout:
            result['host_mmio_protection'] = 'HOST_CPU_ACCESS_DENIED'
        if args.audit_host_mmio and (
                '[HOST_MMIO_TEST] physical_write=DENIED restoration=NOT_APPLICABLE') in probe.stdout:
            records = re.findall(r'\[HOST_USER_MMIO_TEST\] blocked_address=[^\r\n]+', probe.stdout)
            result['user_mmio_records'] = records
            verified = False
            if len(records) == 1:
                fields = dict(re.findall(r'(\w+)=(\S+)', records[0]))
                try:
                    errors = ('initial_read_error', 'write_error', 'read_error',
                              'restore_error', 'restore_read_error')
                    verified = (int(fields['blocked_address'], 0) == 0xfb000028 and
                                all(int(fields[name], 0) == -14 for name in errors) and
                                int(fields['signal']) == 7 and int(fields['code']) == 3)
                except (ValueError, KeyError):
                    pass
            if verified:
                result['host_mmio_protection'] = 'HOST_CPU_ACCESS_DENIED'
    expected_rc = (2 if result[protection_key] == 'FAIL_BYPASS_DETECTED' else
                   1 if audit and result[protection_key] != 'HOST_CPU_ACCESS_DENIED' else 0)
    if probe.returncode != expected_rc or not all(result['checks'].values()) or \
            '[KVM_MMIO_TEST] result=PASS' not in probe.stdout:
        raise RuntimeError('KVM MMIO authorization probe failed')
    result['probe'] = 'PASS'
    if args.ordinary_vm_probe and result[protection_key] == 'FAIL_BYPASS_DETECTED':
        records = re.findall(r'\[ORDINARY_VM_MMIO_TEST\] address=[^\r\n]+', probe.stdout)
        result['ordinary_vm_mmio_records'] = records
        verified = False
        if len(records) == 1 and '[ORDINARY_VM_MMIO_TEST] ram_control=PASS' in probe.stdout:
            fields = dict(re.findall(r'(\w+)=(\S+)', records[0]))
            try:
                values = {name: int(value, 0) for name, value in fields.items()}
                verified = (values['address'] == 0xfb000028 and
                            values['requested'] == (values['before'] ^ 1) and
                            values['observed'] == values['requested'] and
                            values['restored'] == values['before'])
            except (ValueError, KeyError):
                pass
        if not verified:
            raise RuntimeError('ordinary VM MMIO write/readback/restore was not verified')
except Exception as exc:
    result['probe'] = 'FAIL'
    result['error'] = str(exc)
finally:
    if module_owned:
        cleanup = ssh('if test -d '+module_directory+'; then rmmod opencca_gpu_mmio_probe; fi',
                      text=True, capture_output=True)
        result['module_cleanup_rc'] = cleanup.returncode
        if cleanup.returncode:
            result['module_cleanup_error'] = cleanup.stderr
            result['probe'] = 'FAIL'
    if uart:
        try:
            uart.stop()
        except (subprocess.SubprocessError, OSError) as uart_error:
            result['uart_cleanup_error'] = str(uart_error)
    dmesg = ssh('dmesg', text=True, capture_output=True)
    result['dmesg_rc'] = dmesg.returncode
    (out/'kernel-dmesg.log').write_text(dmesg.stdout+dmesg.stderr)
    if dmesg.returncode or host_before is None:
        result['probe'] = 'FAIL'
    else:
        before_text = host_before.decode(errors='replace')
        result['dmesg_ring_wrapped'] = not dmesg.stdout.startswith(before_text)
        delta = dmesg.stdout[len(before_text):] if not result['dmesg_ring_wrapped'] else dmesg.stdout
        result['host_kernel_errors'] = re.findall(
            r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel|RMM GPU release failed)[^\r\n]*',
            delta)
        if result['dmesg_ring_wrapped'] or result['host_kernel_errors']:
            result['probe'] = 'FAIL'
        if args.kernel_mmio_module and result['host_mmio_protection'] == 'FAIL_BYPASS_DETECTED':
            records = re.findall(r'\[HOST_KERNEL_MMIO_TEST\] address=[^\r\n]+', delta)
            result['kernel_mmio_records'] = records
            if len(records) != 1:
                result['probe'] = 'FAIL'
            else:
                fields = dict(re.findall(r'(\w+)=(\S+)', records[0]))
                try:
                    values = {name: int(value, 0) for name, value in fields.items()}
                    verified = (values['address'] == 0xfb000028 and values['requested'] == (values['before'] ^ 1) and
                                values['observed'] == values['requested'] and values['restored'] == values['before'] and
                                not any(values[name] for name in ('write_error', 'read_error', 'restore_error', 'restore_read_error')))
                except (ValueError, KeyError):
                    verified = False
                if not verified:
                    result['probe'] = 'FAIL'
        if args.kernel_mmio_module and result['host_mmio_protection'] == 'HOST_CPU_ACCESS_DENIED':
            records = re.findall(r'\[HOST_KERNEL_MMIO_TEST\] blocked_address=[^\r\n]+', delta)
            result['kernel_mmio_records'] = records
            errors = ('status_error', 'raw_error', 'mask_error', 'write_error',
                      'read_error', 'restore_error', 'alias_read_error',
                      'alias_write_error', 'alias_restore_error', 'recheck_error')
            verified = False
            if len(records) == 1:
                fields = dict(re.findall(r'(\w+)=(\S+)', records[0]))
                try:
                    verified = (int(fields['blocked_address'], 0) == 0xfb000028 and
                                all(int(fields[name], 0) == -14 for name in errors) and
                                '[HOST_KERNEL_MMIO_TEST] physical_access=DENIED' in delta)
                except (ValueError, KeyError):
                    pass
            if not verified:
                result['probe'] = 'FAIL'
    (out/'kvm-mmio.json').write_text(json.dumps(result, indent=2)+'\n')

print(json.dumps(result, indent=2))
raise SystemExit(1 if result['probe'] != 'PASS' else
                 2 if result[protection_key] == 'FAIL_BYPASS_DETECTED' else
                 1 if audit and result[protection_key] != 'HOST_CPU_ACCESS_DENIED' else 0)
