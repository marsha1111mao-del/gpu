#!/usr/bin/env python3
"""Prepare and run the Guest RSI managed-IOMMU probe in one minimal Realm."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
REALM_POPULATE_PAGE_SIZE = 4096
spec = importlib.util.spec_from_file_location(
    'resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def image_release(path):
    with Path(path).open('rb') as source:
        data = source.read()
    match = re.search(rb'Linux version ([^\s\x00]+)', data)
    if not match:
        raise RuntimeError(f'Image has no embedded Linux release: {path}')
    return match.group(1).decode('ascii')


def module_vermagic(path):
    data = Path(path).read_bytes()
    if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 1:
        raise RuntimeError(f'Guest module is not a 64-bit little-endian ELF: {path}')
    if struct.unpack_from('<H', data, 18)[0] != 183:
        raise RuntimeError(f'Guest module is not AArch64: {path}')
    section_offset = struct.unpack_from('<Q', data, 40)[0]
    section_size = struct.unpack_from('<H', data, 58)[0]
    section_count = struct.unpack_from('<H', data, 60)[0]
    string_index = struct.unpack_from('<H', data, 62)[0]
    if section_offset + section_count*section_size > len(data):
        raise RuntimeError(f'Guest module ELF section table is truncated: {path}')
    sections = []
    for index in range(section_count):
        start = section_offset+index*section_size
        sections.append(struct.unpack_from('<IIQQQQIIQQ', data, start))
    if string_index >= len(sections):
        raise RuntimeError(f'Guest module lacks an ELF section-name table: {path}')
    names = sections[string_index]
    names_start = names[4]
    names_size = names[5]
    for section in sections:
        offset = names_start+section[0]
        end = offset
        while end < names_start+names_size and end < len(data) and data[end] != 0:
            end += 1
        if end >= len(data) or data[end] != 0:
            continue
        name = data[offset:end].decode('ascii', errors='replace')
        if name != '.modinfo' or section[1] != 1:
            continue
        values = data[section[4]:section[4]+section[5]].split(b'\0')
        for value in values:
            if value.startswith(b'vermagic='):
                return value[len(b'vermagic='):].decode('ascii')
    raise RuntimeError(f'Guest module lacks vermagic: {path}')


def align4(offset):
    return (offset+3) & ~3


def newc_header(field_values, name):
    name_bytes = name.encode('ascii')+b'\0'
    fields = [*field_values, len(name_bytes), 0]
    header = b'070701'+''.join(f'{value:08x}' for value in fields).encode('ascii')
    return header+name_bytes+b'\0'*(align4(len(header)+len(name_bytes)) -
                                     len(header)-len(name_bytes))


def newc_file(name, content):
    header = newc_header([0x4f434341, 0o100644, 0, 0, 1, 0, len(content),
                          0, 0, 0, 0], name)
    return header+content+b'\0'*(align4(len(content))-len(content))


def newc_raw_entry(fields, name, content):
    return (newc_header(fields[:11], name)+content+
            b'\0'*(align4(len(content))-len(content)))


def newc_trailer():
    return newc_file('TRAILER!!!', b'')


def parse_newc_entries(data):
    offset = 0
    entries = []
    saw_trailer = False
    while True:
        if offset+110 > len(data):
            raise RuntimeError('initrd has a truncated newc header')
        header = data[offset:offset+110]
        if not header.startswith((b'070701', b'070702')):
            raise RuntimeError('initrd is not an uncompressed newc archive')
        fields = [int(header[index:index+8], 16) for index in range(6, 110, 8)]
        file_size = fields[6]
        name_size = fields[11]
        name_start = offset+110
        data_start = align4(name_start+name_size)
        next_offset = align4(data_start+file_size)
        if name_size == 0 or data_start+file_size > len(data):
            raise RuntimeError('initrd has a truncated newc entry')
        name = data[name_start:name_start+name_size-1].decode('utf-8')
        if data[name_start+name_size-1] != 0:
            raise RuntimeError('initrd newc entry name is not NUL terminated')
        content = data[data_start:data_start+file_size]
        if name == 'TRAILER!!!':
            saw_trailer = True
            remaining = data[next_offset:]
            next_nonzero = next((index for index, byte in enumerate(remaining) if byte), None)
            if next_nonzero is None:
                break
            offset = next_offset+next_nonzero
        else:
            entries.append((fields, name, content))
            offset = next_offset
    if not saw_trailer:
        raise RuntimeError('initrd lacks a newc trailer')
    return entries


def parse_newc(data, required_entry):
    entries = set()
    for _, name, _ in parse_newc_entries(data):
        entries.add(name)
    if required_entry in entries:
        raise RuntimeError(f'initrd already contains {required_entry}')
    return entries


def build_initrd(base_initrd, module, realm_init, candidate):
    original = Path(base_initrd).read_bytes()
    parse_newc(original, '/opencca_guest_iommu_probe.ko')
    entries = parse_newc_entries(original)
    init_indexes = [index for index, (_, name, _) in enumerate(entries) if name == 'init']
    if len(init_indexes) != 1:
        raise RuntimeError(f'base initrd must contain exactly one init: {len(init_indexes)}')
    init_index = init_indexes[0]
    fields, _, _ = entries[init_index]
    init_content = Path(realm_init).read_bytes()
    fields[6] = len(init_content)
    entries[init_index] = (fields, 'init', init_content)
    with Path(candidate).open('wb') as target:
        for entry_fields, name, content in entries:
            target.write(newc_raw_entry(entry_fields, name, content))
        target.write(newc_trailer())
        target.write(newc_file('/opencca_guest_iommu_probe.ko',
                               Path(module).read_bytes()))
        target.write(newc_trailer())
        target.write(b'\0' * (-target.tell() % REALM_POPULATE_PAGE_SIZE))
    parsed = parse_newc(Path(candidate).read_bytes(), '/not-present')
    if '/opencca_guest_iommu_probe.ko' not in parsed:
        raise RuntimeError('candidate initrd does not contain the Guest module')


def remote(command, **kwargs):
    ssh_args, env = resources.ssh('rk')
    return subprocess.run(ssh_args+[command], env=env, **kwargs)


def upload(source, target, digest, result):
    target_quoted = shlex.quote(str(target))
    remote('mkdir -p '+shlex.quote(str(PurePosixPath(target).parent)), check=True)
    with Path(source).open('rb') as source_file:
        remote('cat > '+target_quoted, stdin=source_file, check=True)
    actual = remote('sha256sum '+target_quoted, text=True,
                    capture_output=True, check=True).stdout.split()[0]
    if actual != digest:
        raise RuntimeError(f'remote hash mismatch: {target}')
    result.append({'source': str(Path(source).resolve()), 'target': str(target),
                   'sha256': digest})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', type=Path, required=True,
                       help='Frozen bundle containing proxy-Image, initrd.cpio and hashes.json')
    parser.add_argument('--module', type=Path, required=True,
                       help='opencca_guest_iommu_probe.ko built for the frozen proxy Image')
    parser.add_argument('--remote-root', type=PurePosixPath,
                       default=PurePosixPath('/root/GPU-SFTP'))
    parser.add_argument('--realm-init', type=Path,
                       default=ROOT/'build/realm-xshm/init',
                       help='Static PID 1 with the insmod/rmmod test whitelist')
    parser.add_argument('--reclaim-module', type=Path,
                       help='Matching Host module that attempts raw RMI DATA_DESTROY')
    parser.add_argument('--assignment-module', type=Path,
                       help='Matching Host module that grants a powered codec IOMMU')
    parser.add_argument('--gpu-backing', action='store_true',
                       help='Retain a GPU lease instead of a Guest IOMMU mapping')
    args = parser.parse_args()
    if args.gpu_backing and not args.reclaim_module:
        parser.error('--gpu-backing requires --reclaim-module')
    if args.assignment_module and args.reclaim_module:
        parser.error('--assignment-module and --reclaim-module are exclusive')
    if args.assignment_module:
        assignment_data = args.assignment_module.read_bytes()
        required_checks = (b'host_fault_for_parked_guest', b'host_fault_for_bound_guest')
        if any(marker not in assignment_data for marker in required_checks):
            parser.error('--assignment-module lacks the required Host fault checks; use the matching IOMMU IRQ probe')

    run_id = os.getenv('RUN_ID', '')
    if not run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '0':
        parser.error('run through scripts/maintenance/lab-run.py without --allow-rk-reboot')
    if any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
           for char in run_id):
        parser.error('invalid RUN_ID')
    if not args.remote_root.is_absolute():
        parser.error('--remote-root must be absolute')

    run_dir = ROOT/'build/lab-runs'/run_id
    state = json.loads((run_dir/'result.json').read_text())
    if state.get('status') != 'RUNNING':
        parser.error('matching lab wrapper is not running')
    evidence_path = run_dir/'guest-iommu-launch.json'
    if evidence_path.exists():
        parser.error('Guest IOMMU launch evidence already exists')

    frozen_manifest = json.loads((args.images/'hashes.json').read_text())
    frozen = {}
    for name in ('proxy-Image', 'initrd.cpio'):
        digest = sha256(args.images/name)
        if frozen_manifest.get(name) != digest:
            raise RuntimeError(f'frozen input hash mismatch: {args.images/name}')
        frozen[name] = digest

    release = image_release(args.images/'proxy-Image')
    vermagic = module_vermagic(args.module)
    if vermagic.split()[:1] != [release]:
        raise RuntimeError(f'Guest module vermagic {vermagic!r} does not match Image {release!r}')

    local_log = run_dir/'guest-iommu'
    local_log.mkdir(parents=True, exist_ok=False)
    candidate = local_log/'initrd-with-module.cpio'
    build_initrd(args.images/'initrd.cpio', args.module, args.realm_init, candidate)

    runner_path = ROOT/'GPU-SFTP/tests/dma-guard/run_guest_iommu_probe.py'
    module_digest = sha256(args.module)
    initrd_digest = sha256(candidate)
    runner_digest = sha256(runner_path)
    evidence = {
        'run_id': run_id,
        'image_release': release,
        'module_vermagic': vermagic,
        'frozen_sha256': frozen,
        'candidate_initrd_sha256': initrd_digest,
        'module_sha256': module_digest,
        'realm_init_sha256': sha256(args.realm_init),
        'runner_sha256': runner_digest,
        'inputs': [],
    }
    evidence_path.write_text(json.dumps(evidence, indent=2)+'\n')

    remote_run = args.remote_root/'log/guest-iommu'/run_id
    remote('test ! -e '+shlex.quote(str(remote_run)), check=True)
    remote_image = args.remote_root/'firecracker-bins/kernels/guest-iommu'/run_id/'proxy-Image'
    remote_initrd = remote_image.with_name('initrd-with-module.cpio')
    remote_runner = args.remote_root/'tests/dma-guard/run_guest_iommu_probe.py'
    upload(args.images/'proxy-Image', remote_image, frozen['proxy-Image'], evidence['inputs'])
    upload(candidate, remote_initrd, initrd_digest, evidence['inputs'])
    upload(runner_path, remote_runner, runner_digest, evidence['inputs'])
    remote_reclaim = remote_image.with_name('opencca_reclaim_probe.ko')
    if args.reclaim_module:
        upload(args.reclaim_module, remote_reclaim, sha256(args.reclaim_module), evidence['inputs'])
    remote_assignment = remote_image.with_name('opencca_iommu_assignment_probe.ko')
    if args.assignment_module:
        upload(args.assignment_module, remote_assignment, sha256(args.assignment_module), evidence['inputs'])
    evidence_path.write_text(json.dumps(evidence, indent=2)+'\n')

    command = [
        'python3', str(remote_runner), '--root', str(args.remote_root),
        '--run-id', run_id, '--proxy-image', str(remote_image),
        '--initrd', str(remote_initrd),
    ]
    if args.reclaim_module:
        command += ['--reclaim-module', str(remote_reclaim)]
    if args.assignment_module:
        command += ['--assignment-module', str(remote_assignment)]
    if args.gpu_backing:
        command += ['--gpu-backing']
    evidence['command'] = command
    evidence_path.write_text(json.dumps(evidence, indent=2)+'\n')
    process = remote(shlex.join(command), text=True, capture_output=True)
    (local_log/'remote-runner.log').write_text(process.stdout+process.stderr)
    for name in ('realm.json', 'realm.log', 'result.json', 'host-reclaim.log',
                 'host-assignment.log', 'host-lifecycle.log'):
        fetched = remote('cat '+shlex.quote(str(remote_run/name)), capture_output=True)
        if fetched.returncode == 0:
            (local_log/name).write_bytes(fetched.stdout)
    print(process.stdout, end='')
    print(process.stderr, end='', file=sys.stderr)
    return process.returncode


if __name__ == '__main__':
    raise SystemExit(main())
