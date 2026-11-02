#!/usr/bin/env python3
"""Check that every FIT configuration loads the supplied RMM ELF segments.

Uses fdtget from device-tree-compiler. This is a local packaging check, not
firmware authentication, attestation or evidence that the firmware boots.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def elf_segments(data, base):
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('RMM must be little-endian AArch64 ELF64')
    entry, offset = struct.unpack_from('<QQ', data, 24)
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or not count or offset + size * count > len(data):
        raise ValueError('invalid RMM program headers')
    segments = []
    for i in range(count):
        kind, flags, pos, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, offset + i * size)
        if kind != 1:
            continue
        if filesz > memsz or pos + filesz > len(data):
            raise ValueError('invalid RMM LOAD segment')
        if filesz:
            if any(pa + base < old['end'] and old['load'] < pa + memsz + base for old in segments):
                raise ValueError('overlapping RMM LOAD segments')
            segments.append({'load': pa + base, 'end': pa + base + memsz,
                             'data': data[pos:pos + filesz], 'executable': bool(flags & 1)})
    if not segments or not any(s['executable'] and s['load'] <= entry + base < s['load'] + len(s['data']) for s in segments):
        raise ValueError('RMM entry is outside executable file-backed memory')
    return entry + base, segments


def verify(fit, rmm, base=0x201000):
    fit_data, rmm_data = fit.read_bytes(), rmm.read_bytes()
    if len(fit_data) < 40 or fit_data[:4] != b'\xd0\x0d\xfe\xed':
        raise ValueError('invalid FIT header')
    total = struct.unpack_from('>I', fit_data, 4)[0]
    if not 40 <= total <= len(fit_data):
        raise ValueError('truncated FIT tree')
    expected_entry, expected = elf_segments(rmm_data, base)

    def get(node, prop=None, kind='s', listing=None):
        cmd = ['fdtget'] + ([listing] if listing else ['-t', kind]) + [str(fit), node]
        if prop is not None:
            cmd.append(prop)
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def number(node, prop):
        cells = get(node, prop, 'x').split()
        if not 1 <= len(cells) <= 2:
            raise ValueError('invalid FIT integer: ' + node + '/' + prop)
        return int(''.join(f'{int(cell, 16):08x}' for cell in cells), 16)

    images = get('/images', listing='-l').splitlines()
    rmm_names, actual = [], []
    for name in images:
        node = '/images/' + name
        props = get(node, listing='-p').splitlines()
        if 'os' not in props or get(node, 'os') != 'rmm':
            continue
        if get(node, 'arch') != 'arm64' or get(node, 'type') != 'firmware' or get(node, 'compression') != 'none':
            raise ValueError('unsupported RMM FIT metadata: ' + name)
        if 'data' in props:
            if any(key in props for key in ('data-offset', 'data-position', 'data-size')):
                raise ValueError('ambiguous RMM FIT data: ' + name)
            payload = bytes(int(byte, 16) for byte in get(node, 'data', 'bx').split())
        else:
            if ('data-offset' in props) == ('data-position' in props):
                raise ValueError('missing or ambiguous RMM FIT data location: ' + name)
            start = number(node, 'data-position') if 'data-position' in props else ((total + 3) & ~3) + number(node, 'data-offset')
            size = number(node, 'data-size')
            if start < total or not size or start + size > len(fit_data):
                raise ValueError('truncated or invalid RMM FIT data: ' + name)
            payload = fit_data[start:start + size]
        load = number(node, 'load')
        matches = [s for s in expected if s['load'] == load and s['data'] == payload]
        if len(matches) != 1 or load in [s['load'] for s in actual]:
            raise ValueError('FIT RMM segment differs from supplied ELF: ' + name)
        if 'entry' in props and number(node, 'entry') != expected_entry:
            raise ValueError('FIT RMM entry differs from supplied ELF: ' + name)
        digest = bytes(int(byte, 16) for byte in get(node + '/hash', 'value', 'bx').split())
        if get(node + '/hash', 'algo') != 'sha256' or digest != hashlib.sha256(payload).digest():
            raise ValueError('FIT RMM hash differs from payload: ' + name)
        actual.append({'image': name, 'load': load, 'bytes': len(payload),
                       'sha256': hashlib.sha256(payload).hexdigest(), 'entry': 'entry' in props})
        rmm_names.append(name)
    if len(actual) != len(expected) or sum(s['entry'] for s in actual) != 1:
        raise ValueError('FIT does not contain all RMM segments and exactly one entry')
    configurations = get('/configurations', listing='-l').splitlines()
    if not configurations or get('/configurations', 'default') not in configurations:
        raise ValueError('missing or invalid FIT default configuration')
    for name in configurations:
        node = '/configurations/' + name
        selected = [get(node, 'firmware')] + get(node, 'loadables').split()
        if len(set(selected)) != len(selected) or any(image not in images for image in selected):
            raise ValueError('invalid FIT configuration image references: ' + name)
        if set(rmm_names) - set(selected):
            raise ValueError('FIT configuration omits an RMM segment: ' + name)
    # Reject a file changed between the byte snapshot and fdtget queries.
    if fit.read_bytes() != fit_data or rmm.read_bytes() != rmm_data:
        raise ValueError('firmware input changed during verification')
    return {'status': 'PASS', 'fit_sha256': hashlib.sha256(fit_data).hexdigest(),
            'rmm_sha256': hashlib.sha256(rmm_data).hexdigest(),
            'rmm_entry': expected_entry, 'segments': actual,
            'configurations': configurations, 'boot_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit', type=Path, required=True)
    parser.add_argument('--rmm', type=Path, required=True)
    parser.add_argument('--rmm-base', type=lambda s: int(s, 0), default=0x201000)
    args = parser.parse_args()
    try:
        result = verify(args.fit, args.rmm, args.rmm_base)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f'RMM_FIT=FAIL {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
