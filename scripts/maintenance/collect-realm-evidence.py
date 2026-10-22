#!/usr/bin/env python3
"""Copy one completed Realm run and verify every remote file before local analysis."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--remote-root', type=PurePosixPath, default=PurePosixPath('/root/GPU-SFTP'))
    args = parser.parse_args()
    if not args.run_id or any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for character in args.run_id):
        parser.error('invalid run-id')
    if not args.remote_root.is_absolute():
        parser.error('remote-root must be absolute')
    lab = ROOT/'build/lab-runs'/args.run_id
    lab_result = json.loads((lab/'result.json').read_text())
    if lab_result['status'] in ('RUNNING', 'PREFLIGHT'):
        parser.error('lab run has not finished')
    if args.output.exists():
        parser.error('output already exists; preserve the previous collection')
    resources = runpy.run_path(str(ROOT/'scripts/maintenance/lab-resources.py'))
    ssh, env = resources['ssh']('rk')
    remote = args.remote_root/'log/realm-xshm'/args.run_id
    script = '''import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
summary=json.loads((root/'summary.json').read_text())
if summary['status']=='RUNNING' and 'vm_exit_codes' not in summary:
    raise RuntimeError('Realm run has not finished')
files={}
for path in sorted(root.rglob('*')):
    if path.is_symlink(): raise RuntimeError('unexpected symlink')
    if path.is_file(): files[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(files))
'''
    command = shlex.join(['python3', '-c', script, str(remote)])
    expected = json.loads(subprocess.run(ssh+[command], env=env, check=True,
                                       capture_output=True, text=True).stdout)
    args.output.mkdir(parents=True)
    subprocess.run(['rsync', '-a', '--checksum', '-e', shlex.join(ssh[:-1]),
                    ssh[-1]+':'+str(remote)+'/', str(args.output)+'/'], env=env, check=True)
    actual = {str(path.relative_to(args.output)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in args.output.rglob('*') if path.is_file()}
    if actual != expected:
        raise RuntimeError('local evidence differs from remote manifest')
    for source, target in (('result.json', 'lab-result.json'),
                           ('host-kernel-health.json', 'host-kernel-health.json'),
                           ('before.json', 'lab-before.json'), ('after.json', 'lab-after.json'),
                           ('realm-launch.json', 'realm-launch.json')):
        path = lab/source
        if path.is_file():
            (args.output/target).write_bytes(path.read_bytes())
    (args.output/'collection.json').write_text(json.dumps({'run_id': args.run_id,
        'status': 'VERIFIED', 'remote': str(remote), 'files': expected}, indent=2)+'\n')
    print(f'VERIFIED run={args.run_id} files={len(expected)} output={args.output}')


if __name__ == '__main__':
    main()
