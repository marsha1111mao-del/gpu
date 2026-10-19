#!/usr/bin/env python3
"""Probe IOMMU admission or real PL330 DMA using test-owned pages."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from pi_uart import PiUartCapture

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--module', type=Path, required=True)
p.add_argument('--images', type=Path, help='Also probe a live GPU page during full 720p glmark')
p.add_argument('--device', default='fdb50000.video-codec', help='Platform device with an active IOMMU')
p.add_argument('--audit-bypass', action='store_true', help='Additionally audit direct driver PTE bypass (outside mapping API scope)')
p.add_argument('--transfer', action='store_true', help='Run the real delegated-page PL330 DMA probe')
p.add_argument('--transfer-controller', default='fea10000.dma-controller')
p.add_argument('--transfer-channel', default='dma0chan10')
p.add_argument('--uart-capture', action='store_true',
              help='Capture RK UART during the probe')
a = p.parse_args()
if a.transfer and (a.images or a.audit_bypass):
    p.error('--transfer cannot combine with --images or --audit-bypass')
module_name = 'opencca_dma_transfer_probe' if a.transfer else 'opencca_dma_probe'
if a.module.name != module_name+'.ko':
    p.error('module filename must be '+module_name+'.ko')
run_id = os.getenv('RUN_ID', '')
if not run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '0':
    p.error('requires lab-run.py without --allow-rk-reboot')
out = ROOT/'build/lab-runs'/run_id
state_path = out/'result.json'
if not state_path.is_file() or json.loads(state_path.read_text()).get('status') != 'RUNNING':
    p.error('matching lab wrapper is not running')
target = '/root/GPU-SFTP/log/dma-guard/'+run_id+'/'+module_name+'.ko'
result = {'run_id': run_id, 'admission': 'NOT_RUN',
          'configuration_protection': 'NOT_RUN', 'actual_dma_transfer': 'NOT_RUN',
          'full_dma_protection': 'INCOMPLETE',
          'module_sha256': hashlib.sha256(a.module.read_bytes()).hexdigest(),
          'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'mode': 'transfer' if a.transfer else 'admission',
          'scope': 'actual_dma_diagnostic' if a.transfer else 'iommu_mapping_api',
          'iommu_mapping_firewall': 'NOT_RUN',
          'managed_iommu': 'NOT_DETECTED',
          'non_iommu_dma': 'OUT_OF_SCOPE' if not a.transfer else 'DIAGNOSTIC',
          'performance_comparability': 'probe runs during glmark' if a.images else 'no GPU benchmark',
          'uart_capture': 'ENABLED' if a.uart_capture else 'NOT_RUN'}
failure_key = 'transfer_probe' if a.transfer else 'admission'
child = None
loaded = False
log = None
uart = None
if a.uart_capture:
    uart = PiUartCapture(out/'rmm-uart.log',
                         '/tmp/'+run_id+'-dma-guard-uart-stop')


def ssh(command, **kwargs):
    args, env = resources.ssh('rk')
    return subprocess.run(args+[command], env=env, **kwargs)


def save():
    (out/'dma-guard.json').write_text(json.dumps(result, indent=2)+'\n')


def channel_state():
    # Quote the complete Python program as one SSH shell argument.
    code = ('import json; from pathlib import Path; '
            f'p=Path("/sys/class/dma")/{a.transfer_channel!r}; '
            'print(json.dumps({"path":str(p.resolve()),'
            '"in_use":p.joinpath("in_use").read_text().strip(),'
            '"memcpy_count":p.joinpath("memcpy_count").read_text().strip(),'
            '"bytes_transferred":p.joinpath("bytes_transferred").read_text().strip()}))')
    return json.loads(ssh('python3 -c '+shlex.quote(code), text=True,
                          capture_output=True, check=True).stdout)


save()
try:
    if uart:
        uart.start()
    guard = ssh('zcat /proc/config.gz', text=True, capture_output=True, check=True).stdout
    if 'CONFIG_OPENCCA_DMA_GUARD=y\n' not in guard:
        raise RuntimeError('running Host lacks CONFIG_OPENCCA_DMA_GUARD=y')
    if not a.transfer and 'CONFIG_OPENCCA_MANAGED_IOMMU=y\n' not in guard:
        raise RuntimeError('running Host lacks CONFIG_OPENCCA_MANAGED_IOMMU=y')
    if ssh('test -d /sys/module/'+module_name).returncode == 0:
        raise RuntimeError('probe module already loaded; refusing to disturb it')
    if a.transfer:
        result['channel_before'] = channel_state()
        expected = '/sys/devices/platform/'+a.transfer_controller+'/dma/'+a.transfer_channel
        if result['channel_before']['path'] != expected or result['channel_before']['in_use'] != '0':
            raise RuntimeError('requested channel is busy or belongs to another controller')
    else:
        code = ('import json; from pathlib import Path; '
                f'p=Path("/sys/bus/platform/devices")/{a.device!r}; '
                'print(json.dumps({"device":p.name,"has_iommus":(p/"of_node/iommus").exists(),'
                '"iommu_group":str((p/"iommu_group").resolve()) if (p/"iommu_group").exists() else None}))')
        result['device'] = json.loads(ssh('python3 -c '+shlex.quote(code), text=True,
                                          capture_output=True, check=True).stdout)
        if not result['device']['has_iommus'] or not result['device']['iommu_group']:
            raise RuntimeError('selected device has no active IOMMU association')
    ssh('mkdir -p '+shlex.quote(str(Path(target).parent)), check=True)
    with a.module.open('rb') as source:
        ssh('cat > '+shlex.quote(target), stdin=source, check=True)
    actual = ssh('sha256sum '+shlex.quote(target), text=True, capture_output=True, check=True)
    if actual.stdout.split()[0] != result['module_sha256']:
        raise RuntimeError('module upload hash mismatch')
    before = ssh('dmesg', text=True, capture_output=True, check=True).stdout
    if a.images:
        command = ['python3', str(ROOT/'scripts/run/run-realm-xshm.py'),
                   '--images', str(a.images), '--workload', 'glmark', '--performance',
                   '--benchmark-only', '--suite', '--profiles', 'glmark-720']
        log = (out/'gpu.log').open('w')
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        result['gpu_command'] = command
    deadline = time.monotonic()+600
    while True:
        params = ('controller='+shlex.quote(a.transfer_controller)+' channel='+shlex.quote(a.transfer_channel)
                  if a.transfer else 'gpu_required='+str(int(bool(a.images)))+
                  ' probe_bypass='+str(int(a.audit_bypass))+' device='+shlex.quote(a.device))
        command = 'insmod '+shlex.quote(target)+' '+params
        result['probe_command'] = command
        probe = ssh(command,
                    text=True, capture_output=True, timeout=180)
        result['probe_rc'] = probe.returncode
        if probe.returncode == 0:
            loaded = True
            break
        if not a.images or 'Resource temporarily unavailable' not in probe.stderr:
            result['probe_stderr'] = probe.stderr
            raise RuntimeError(f'probe init failed: rc={probe.returncode}')
        if child.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError('GPU lease did not become available before workload completion/deadline')
        time.sleep(2)
    cleanup = ssh('rmmod '+module_name, text=True, capture_output=True)
    result['module_cleanup_rc'] = cleanup.returncode
    if cleanup.returncode:
        raise RuntimeError('module cannot be unloaded; inspect quarantined resources')
    loaded = False
    if child:
        # The wrapper continues to own the lab while glmark completes.
        result['gpu_rc'] = child.wait(timeout=1800)
        if result['gpu_rc'] != 0:
            raise RuntimeError('GPU workload failed; retain its logs')
    after = ssh('dmesg', text=True, capture_output=True, check=True).stdout
    if not after.startswith(before):
        raise RuntimeError('kernel log rotated; cannot establish the probe evidence boundary')
    delta = after[len(before):]
    (out/'kernel-delta.log').write_text(delta)
    if a.transfer:
        result['channel_after'] = channel_state()
        required = ['exclusive_channel', 'normal_dma_complete', 'normal_data',
                    'existing_mapping_dma_complete', 'existing_mapping_data',
                    'existing_mapping_read_dma_complete', 'existing_mapping_read_data',
                    'new_mapping_dma_complete', 'new_mapping_data',
                    'new_mapping_read_dma_complete', 'new_mapping_read_data',
                    'reservation_recovery', 'cleanup']
        result['checks'] = {name: f'[DMA_TRANSFER_TEST] {name}=PASS' in delta for name in required}
        result['actual_dma_transfer'] = 'PASS' if all(result['checks'].values()) else 'FAIL'
        result['delegated_page_dma_protection'] = {
            phase: ('FAIL_BYPASS_DETECTED' if
                    f'[DMA_TRANSFER_TEST] {phase}_protection=FAIL_BYPASS_DETECTED' in delta
                    else 'NOT_PROVEN') for phase in ['existing_mapping', 'new_mapping']}
        result['scope'] = 'test-owned DELEGATED page; no active Realm or GPU BO targeted'
        result['kernel_errors'] = [line for line in delta.splitlines() if
                                   re.search(r'BUG:|Oops:|WARNING:|Unable to handle kernel|Kernel panic', line)]
        result['channel_restored'] = result['channel_after']['in_use'] == result['channel_before']['in_use']
        if (not all(result['checks'].values()) or not result['channel_restored'] or result['kernel_errors'] or
                '[DMA_TRANSFER_TEST] probe_result=BYPASS_REPRODUCED' not in delta or
                any(v != 'FAIL_BYPASS_DETECTED' for v in result['delegated_page_dma_protection'].values())):
            raise RuntimeError('DMA bypass reproduction or resource recovery incomplete')
        result['transfer_probe'] = 'BYPASS_REPRODUCED'
    else:
        result['managed_iommu'] = ('ENABLED' if
            '[DMA_GUARD_TEST] managed_iommu=ENABLED\n' in delta else 'DISABLED')
        if result['managed_iommu'] != 'ENABLED':
            raise RuntimeError('probe was not built for managed IOMMU mode')
        required = ['allowed_mapping', 'existing_dma_blocks_delegation', 'allowed_unmap',
                    'delegation_after_unmap', 'delegated_page_mapping_denied',
                    'covering_mapping_denied', 'mapping_after_undelegation',
                    'final_unmap', 'reservation_recovery', 'allowed_sg_mapping', 'allowed_sg_unmap',
                    'delegated_page_write_mapping_denied', 'delegated_page_alias_mapping_denied',
                    'delegated_sg_mapping_denied', 'delegated_sg_rollback',
                    'direct_driver_delegation_denied', 'managed_domain_root_ownership',
                    'managed_recovery_mapping', 'unbind_parking',
                    'managed_recovery_after_unbind', 'recovery_mapping_after_rebind',
                    'recovery_unmap']
        if a.images:
            required += ['live_gpu_page_mapping_denied', 'live_gpu_write_mapping_denied',
                         'live_gpu_alias_mapping_denied', 'live_gpu_covering_mapping_denied',
                         'live_gpu_sg_mapping_denied', 'live_gpu_sg_rollback']
        result['checks'] = {name: f'[DMA_GUARD_TEST] {name}=PASS' in delta for name in required}
        if not all(result['checks'].values()) or '[DMA_GUARD_TEST] admission_result=PASS' not in delta:
            raise RuntimeError('missing admission correctness markers')
        result['admission'] = 'PASS'
        result['kernel_errors'] = [line for line in delta.splitlines() if
                                   re.search(r'BUG:|Oops:|WARNING:|Unable to handle kernel|Kernel panic', line)]
        if result['kernel_errors']:
            raise RuntimeError('kernel errors during the mapping test')
        result['iommu_mapping_firewall'] = 'PASS'
        result['live_gpu_mapping_check'] = 'PASS' if a.images else 'NOT_RUN'
        if a.audit_bypass and 'configuration_protection=FAIL_BYPASS_DETECTED\n' in delta:
            result['configuration_protection'] = 'FAIL_BYPASS_DETECTED'
        else:
            result['configuration_protection'] = ('PASS_DIRECT_DRIVER_PATH' if
                result['checks']['direct_driver_delegation_denied'] else
                'NOT_PROVEN')
except Exception as exc:
    result['error'] = str(exc)
    result[failure_key] = 'FAIL'
    if not a.transfer:
        result['iommu_mapping_firewall'] = 'FAIL'
    # Preserve the diagnostic even when module initialization failed.
    try:
        failed_log = ssh('dmesg', text=True, capture_output=True, timeout=15)
        (out/'kernel-after-failure.log').write_text(failed_log.stdout)
    except (subprocess.SubprocessError, OSError) as log_error:
        result['kernel_after_failure_error'] = str(log_error)
finally:
    if uart:
        try:
            uart.stop()
        except (subprocess.SubprocessError, OSError) as uart_error:
            result['uart_cleanup_error'] = str(uart_error)
    if loaded:
        cleanup = ssh('rmmod '+module_name, text=True, capture_output=True)
        result['module_cleanup_rc'] = cleanup.returncode
        if cleanup.returncode:
            result[failure_key] = 'FAIL'
            result['error'] = 'test module cleanup failed; inspect its ownership before another run'
    if child and child.poll() is None:
        # Let the GPU runner perform its own resource cleanup.
        try:
            result['gpu_rc'] = child.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            result[failure_key] = 'FAIL'
            result['error'] = 'GPU runner still active after deadline; inspect its recorded processes'
    if child and child.poll() not in (None, 0):
        result[failure_key] = 'FAIL'
        result['error'] = 'GPU runner failed; retain its logs'
    if log:
        log.close()
    if not a.transfer and result.get(failure_key) != 'PASS':
        result['iommu_mapping_firewall'] = 'FAIL'
    save()
print(json.dumps(result, indent=2))
if (not a.transfer and not a.audit_bypass and
        result.get(failure_key) == 'PASS'):
    # The user's acceptance scope is IOMMU mapping admission. Broader physical
    # isolation remains explicitly unclaimed in the result above.
    raise SystemExit(0)
raise SystemExit(2 if result.get(failure_key) in ('PASS', 'BYPASS_REPRODUCED') else 1)
