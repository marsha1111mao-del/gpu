#!/usr/bin/env python3
"""Read-only Pi/RK resource audit; --check applies minimum headroom gates."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

PROBE = r'''
import json, os, platform, subprocess
from pathlib import Path
role = ROLE
os.environ['PATH'] = os.environ.get('PATH', '') + ':/usr/sbin:/sbin'
mem = {line.split(':')[0]: int(line.split()[1])*1024
       for line in Path('/proc/meminfo').read_text().splitlines()}
root = '/home/mzh/opencca-flash' if role == 'pi' else '/root/GPU-SFTP'
marker = root+'/flash.sh' if role == 'pi' else '/sys/bus/platform/devices/fb000000.gpu'
def command(args):
    try:
        p = subprocess.run(args, text=True, capture_output=True)
        return {'rc': p.returncode, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()}
    except OSError as e:
        return {'rc': 127, 'stdout': '', 'stderr': str(e)}
disks = {}
for path in ['/', '/tmp', root]:
    if not Path(path).exists(): continue
    s = os.statvfs(path)
    disks[path] = {'total_bytes': s.f_blocks*s.f_frsize,
                   'available_bytes': s.f_bavail*s.f_frsize,
                   'free_inodes': s.f_favail}
processes = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        comm = (p/'comm').read_text().strip()
        if comm in ('firecracker', 'vmshm-broker', 'rkdeveloptool', 'upgrade_tool'):
            processes.append({'pid': int(p.name), 'comm': comm})
    except (OSError, UnicodeError): pass
snapshots = []
if role == 'pi':
    for p in sorted((Path(root)/'snapshot').glob('*')):
        if p.is_symlink() or not p.is_file(): continue
        s = p.stat()
        snapshots.append({'name': p.name, 'bytes': s.st_size,
                          'allocated_bytes': s.st_blocks*512, 'mtime_ns': s.st_mtime_ns})
print(json.dumps({'role': role, 'role_verified': Path(marker).exists(),
 'hostname': platform.node(), 'kernel': platform.release(),
 'online_cpus': Path('/sys/devices/system/cpu/online').read_text().strip(),
 'gpu_driver': os.path.realpath('/sys/bus/platform/devices/fb000000.gpu/driver') if role == 'rk' else None,
 'memory': {k: mem[k] for k in ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree']},
 'disks': disks, 'active_lab_processes': processes, 'snapshots': snapshots,
 'mounts': command(['findmnt', '-rn', '-o', 'TARGET,SOURCE,FSTYPE']),
 'loops': command(['losetup', '-l', '-n', '-O', 'NAME,BACK-FILE']),
 'usage': command(['du', '-x', '-B1', '--max-depth=1', root])}))
'''


def ssh(role):
    if role == 'pi':
        host = os.getenv('PI_HOST', os.getenv('OPENCCA_RPI_HOST', 'mzh@192.168.31.189'))
        password = os.getenv('PI_PASSWORD', os.getenv('OPENCCA_RPI_PASSWORD'))
    else:
        host = os.getenv('RK_HOST', os.getenv('OPENCCA_RK_HOST',
                         os.getenv('REMOTE_USER', 'root')+'@'+os.getenv('REMOTE_HOST', '192.168.31.18')))
        password = os.getenv('RK_PASSWORD', os.getenv('REMOTE_PASS', os.getenv('OPENCCA_RK_PASSWORD')))
    env = os.environ.copy()
    prefix = []
    if password:
        env['SSHPASS'] = password
        prefix = ['sshpass', '-e']
    return prefix + ['ssh', '-o', 'ConnectTimeout=8', '-o',
            'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=3', '-o',
            'StrictHostKeyChecking=accept-new', host], env


def audit(role):
    cmd, env = ssh(role)
    p = subprocess.run(cmd+['python3 -'], input=PROBE.replace('ROLE', repr(role)),
                       env=env, text=True, capture_output=True, timeout=90)
    if p.returncode:
        raise RuntimeError(f'{role}: SSH/probe rc={p.returncode}: {p.stderr.strip()}')
    return json.loads(p.stdout)


def violations(report):
    role = report['role']
    issues = []
    if not report['role_verified']:
        issues.append(f'{role}: role marker missing')
    disk_min = (2 if role == 'pi' else 4)*1024**3
    if report['disks']['/']['available_bytes'] < disk_min:
        issues.append(f'{role}: root filesystem below {disk_min//1024**3} GiB free')
    if report['disks']['/']['free_inodes'] < 10000:
        issues.append(f'{role}: fewer than 10000 free inodes')
    if report['memory']['MemAvailable'] < (128 if role == 'pi' else 512)*1024**2:
        issues.append(f'{role}: insufficient baseline MemAvailable')
    # These are minimum idle gates, not a workload memory reservation.
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['pi', 'rk', 'all'], default='all')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    reports = []
    errors = []
    for role in (['pi', 'rk'] if args.role == 'all' else [args.role]):
        try:
            reports.append(audit(role))
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            errors.append(str(e))
    issues = errors + [i for r in reports for i in violations(r)]
    result = {'timestamp': dt.datetime.now(dt.timezone.utc).isoformat(),
              'reports': reports, 'issues': issues}
    encoded = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end='')
    return 1 if errors or (args.check and issues) else 0


if __name__ == '__main__':
    sys.exit(main())
