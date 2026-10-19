#!/usr/bin/env python3
"""Verify an idle GPU power cycle and subsequent Realm MMIO reuse."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)
uart_spec = importlib.util.spec_from_file_location('pi_uart', ROOT/'scripts/run/pi_uart.py')
uart_module = importlib.util.module_from_spec(uart_spec)
uart_spec.loader.exec_module(uart_module)

WORKER = r'''
import json
from pathlib import Path
import re
import subprocess
import sys
import time

module = MODULE
driver = Path('/sys/bus/platform/drivers/pmthor')
device = Path('/sys/bus/platform/devices/fb000000.gpu')
frequency = device/'devfreq/fb000000.gpu'
assert (device/'driver').resolve() == driver
before = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
governor = (frequency/'governor').read_text().strip()
selected = (frequency/'cur_freq').read_text().strip()
checks = {}
result = {'status': 'RUNNING', 'checks': checks}
loaded = False

def progress(stage):
    print('GPU_POWER_STAGE='+stage, file=sys.stderr, flush=True)

def power_domain(expected):
    deadline = time.monotonic()+5
    while True:
        rows = [line.split() for line in Path('/sys/kernel/debug/pm_genpd/pm_genpd_summary').read_text().splitlines()]
        states = [fields[1] for fields in rows if len(fields) > 1 and fields[0] == 'gpu']
        if len(states) == 1 and states[0].startswith(expected):
            return states[0]
        if time.monotonic() >= deadline:
            raise RuntimeError('GPU power domain did not reach '+expected+': '+repr(states))
        time.sleep(0.05)

def probe(name, expected):
    global loaded
    subprocess.run(['insmod', module, 'expected_state='+str(expected)], check=True)
    loaded = True
    subprocess.run(['rmmod', 'opencca_gpu_power_probe'], check=True)
    loaded = False
    checks[name] = True

try:
    progress('initial_domain')
    result['initial_power_domain'] = power_domain('on')
    progress('initial_probe')
    probe('initial_unowned_and_illegal_opp_denied', 0)
    progress('unbind')
    (driver/'unbind').write_text('fb000000.gpu')
    progress('unbound')
    assert not (device/'driver').exists() and not Path('/dev/pmthor').exists()
    result['unbound_power_domain'] = power_domain('off')
    probe('unbound_rmm_off_and_illegal_opp_denied', 8)
    progress('bind')
    (driver/'bind').write_text('fb000000.gpu')
    progress('rebound')
    assert (device/'driver').resolve() == driver and Path('/dev/pmthor').exists()
    result['rebound_power_domain'] = power_domain('on')
    probe('rebound_rmm_unowned_and_illegal_opp_denied', 0)
    result['status'] = 'PASS'
except Exception as error:
    result['status'] = 'FAIL'
    result['error'] = str(error)
finally:
    progress('restore')
    try:
        if loaded:
            subprocess.run(['rmmod', 'opencca_gpu_power_probe'], check=True)
        if not (device/'driver').exists():
            (driver/'bind').write_text('fb000000.gpu')
        (frequency/'governor').write_text('userspace')
        (frequency/'userspace/set_freq').write_text(selected)
        (frequency/'governor').write_text(governor)
        checks['driver_and_frequency_restored'] = (
            (device/'driver').resolve() == driver and Path('/dev/pmthor').exists() and
            (frequency/'cur_freq').read_text().strip() == selected and
            (frequency/'governor').read_text().strip() == governor)
        if not checks['driver_and_frequency_restored']:
            raise RuntimeError('GPU environment restoration failed')
    except Exception as error:
        result['status'] = 'FAIL'
        result['cleanup_error'] = str(error)
    after = subprocess.run(['dmesg'], capture_output=True, check=True).stdout
    result['dmesg_ring_wrapped'] = not after.startswith(before)
    delta = after[len(before):].decode(errors='replace') if after.startswith(before) else after.decode(errors='replace')
    result['kernel_errors'] = re.findall(r'[^\r\n]*(?:BUG:|Oops:|WARNING:|Unable to handle kernel|retaining clocks|removing active/unquiesced)[^\r\n]*', delta)
    result['kernel_delta'] = delta
    if result['kernel_errors'] or result['dmesg_ring_wrapped']:
        result['status'] = 'FAIL'
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--kvm-probe', type=Path, required=True)
    args = parser.parse_args()
    run_id = os.environ.get('RUN_ID', '')
    if not run_id or os.environ.get('GPU_LAB_ALLOW_RK_REBOOT') != '0':
        parser.error('run through lab-run.py without --allow-rk-reboot')
    run = ROOT/'build/lab-runs'/run_id
    state = json.loads((run/'result.json').read_text())
    if state['status'] != 'RUNNING':
        parser.error('matching lab wrapper is not running')
    remote_module = '/root/GPU-SFTP/log/gpu-power-cycle/'+run_id+'/opencca_gpu_power_probe.ko'
    ssh, env = resources.ssh('rk')
    subprocess.run(ssh+['mkdir -p '+shlex.quote(str(Path(remote_module).parent))], env=env, check=True)
    with args.module.open('rb') as source:
        subprocess.run(ssh+['cat > '+shlex.quote(remote_module)], stdin=source, env=env, check=True)
    digest = hashlib.sha256(args.module.read_bytes()).hexdigest()
    actual = subprocess.run(ssh+['sha256sum '+shlex.quote(remote_module)], env=env,
                            capture_output=True, text=True, check=True).stdout.split()[0]
    if actual != digest:
        raise RuntimeError('power probe module hash mismatch')
    uart = uart_module.PiUartCapture(run/'power-cycle-uart.log',
                                   '/tmp/'+run_id+'-uart-stop', seconds=150)
    uart.start()
    try:
        process = subprocess.run(ssh+['python3 -'], input=WORKER.replace('MODULE', repr(remote_module)),
                                 env=env, stdout=subprocess.PIPE, stderr=sys.stderr,
                                 text=True, check=True, timeout=120)
    finally:
        uart.stop()
    result = json.loads(process.stdout)
    (run/'power-cycle-kernel.log').write_text(result.pop('kernel_delta'))
    result['run_id'] = run_id
    result['module_sha256'] = digest
    if result['status'] == 'PASS':
        completed = subprocess.run(['python3', str(ROOT/'scripts/run/run-kvm-mmio-probe.py'),
                                    '--probe', str(args.kvm_probe)], cwd=ROOT)
        result['post_power_cycle_kvm_returncode'] = completed.returncode
        if completed.returncode:
            result['status'] = 'FAIL'
    (run/'gpu-power-cycle.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
