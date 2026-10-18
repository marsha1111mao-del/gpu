#!/usr/bin/env python3
"""Hold Pi/RK lab leases and collect command/resource evidence, including reboot."""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resources', Path(__file__).with_name('lab-resources.py'))
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)
LEASE = """import fcntl,sys
f=open(PATH,'a')
try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: sys.exit(73)
print('LOCKED',flush=True)
sys.stdin.buffer.read()
"""


def release(proc):
    try:
        proc.stdin.close()
    except BrokenPipeError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def acquire(role, out):
    ssh, env = resources.ssh(role)
    path = '/tmp/gpu-workspace.lock' if role == 'pi' else '/run/lock/gpu-workspace.lock'
    script = LEASE.replace('PATH', repr(path))
    with (out/f'{role}-lease.stderr').open('w') as err:
        proc = subprocess.Popen(ssh+['python3 -u -c '+shlex.quote(script)], env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            if not sel.select(15) or proc.stdout.readline().strip() != b'LOCKED':
                raise RuntimeError(f'{role} lease unavailable; another managed run may own it')
    except BaseException:
        release(proc)
        raise
    return proc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', default='lab-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S'))
    p.add_argument('--allow-rk-reboot', action='store_true',
                   help='release RK lease before command; retain Pi lease through reboot and postflight')
    p.add_argument('--recover-rk-offline', action='store_true',
                   help='Pi-only lease for an offline RK recovery; requires --allow-rk-reboot')
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    if args.recover_rk_offline and not args.allow_rk_reboot:
        p.error('--recover-rk-offline requires --allow-rk-reboot')
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        p.error('provide a runner after --')
    if not args.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run_id):
        p.error('invalid run-id')
    out = ROOT/'build/lab-runs'/args.run_id
    out.mkdir(parents=True, exist_ok=False)
    result = {'run_id': args.run_id, 'command': command, 'cwd': str(ROOT),
              'started': dt.datetime.now(dt.timezone.utc).isoformat(), 'status': 'PREFLIGHT',
              'allow_rk_reboot': args.allow_rk_reboot,
              'recover_rk_offline': args.recover_rk_offline}

    def save():
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')

    save()
    child = before = None
    leases = {}
    rc = 1
    try:
        # Fixed lock order. The Pi lease survives RK reset and is required by
        # every managed test, so another test cannot enter during a firmware run.
        leases['pi'] = acquire('pi', out)
        if args.recover_rk_offline:
            pi = resources.audit('pi')
            (out/'pi-before.json').write_text(json.dumps(pi, indent=2)+'\n')
            if resources.violations(pi) or pi['active_lab_processes']:
                raise RuntimeError('Pi resource/activity check failed before recovery')
            probe, probe_env = resources.ssh('rk')
            try:
                available = subprocess.run(probe+['true'], env=probe_env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=12).returncode == 0
            except subprocess.TimeoutExpired:
                available = False
            if available:
                raise RuntimeError('RK is reachable; use normal preflight instead of offline recovery')
            before = {'role': 'rk', 'available': False,
                      'reason': 'SSH unavailable; physical recovery under Pi lease'}
            result['baseline_comparison'] = 'NOT_RUN (RK offline before recovery)'
        else:
            leases['rk'] = acquire('rk', out)
            before = resources.audit('rk')
            (out/'before.json').write_text(json.dumps(before, indent=2)+'\n')
            issues = resources.violations(before)
            if before['active_lab_processes']:
                issues.append('existing VM/broker/flash process; do not kill it automatically')
            if before['loops']['rc'] != 0 or before['loops']['stdout']:
                issues.append('loop device check failed or loop devices remain; inspect ownership')
            if issues:
                raise RuntimeError('; '.join(issues))
        (out/'before.json').write_text(json.dumps(before, indent=2)+'\n')
        if args.allow_rk_reboot and 'rk' in leases:
            release(leases.pop('rk'))
        result['status'] = 'RUNNING'
        save()
        run_env = os.environ.copy()
        run_env['RUN_ID'] = args.run_id
        run_env['GPU_LAB_ALLOW_RK_REBOOT'] = '1' if args.allow_rk_reboot else '0'
        child = subprocess.Popen(command, cwd=ROOT, env=run_env, start_new_session=True)

        def interrupted(signum, frame):
            raise KeyboardInterrupt

        old = {s: signal.signal(s, interrupted) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            while True:
                try:
                    rc = child.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    if any(proc.poll() is not None for proc in leases.values()):
                        raise RuntimeError('lab lease connection lost during run')
            if any(proc.poll() is not None for proc in leases.values()):
                raise RuntimeError('lab lease connection lost before command completion')
            result['status'] = 'COMPLETED' if rc == 0 else 'FAILED'
        finally:
            for s, handler in old.items():
                signal.signal(s, handler)
    except (RuntimeError, OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as e:
        result['status'] = 'INTERRUPTED' if isinstance(e, KeyboardInterrupt) else 'BLOCKED_OR_FAILED'
        result['error'] = str(e) or 'signal received'
        print(result['error'], file=sys.stderr)
        rc = 130 if isinstance(e, KeyboardInterrupt) else 1
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        # Never audit another run after a lease conflict. Postflight stays
        # protected by the Pi lease even when RK was deliberately rebooted.
        if before is not None:
            try:
                after = resources.audit('rk')
                (out/'after.json').write_text(json.dumps(after, indent=2)+'\n')
                issues = []
                if after['active_lab_processes'] or after['loops']['rc'] != 0 or after['loops']['stdout']:
                    issues.append('VM/broker/loop resources remain')
                    result['cleanup_required'] = True
                changed = [key for key in ('online_cpus', 'gpu_driver')
                           if key in before and after[key] != before[key]]
                if args.recover_rk_offline:
                    issues.extend(resources.violations(after))
                if changed:
                    result['restore_mismatch'] = changed
                    issues.append('Host configuration differs from preflight')
                if issues and child is not None and rc == 0:
                    result['status'] = 'POSTFLIGHT_FAILED'
                    rc = 1
            except Exception as e:
                result['postflight_error'] = str(e)
                if rc == 0:
                    rc = 1
                    result['status'] = 'POSTFLIGHT_FAILED'
        for proc in reversed(list(leases.values())):
            release(proc)
        result.update(returncode=rc, ended=dt.datetime.now(dt.timezone.utc).isoformat())
        save()
        print(f'LAB_RUN status={result["status"]} rc={rc} evidence={out}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
