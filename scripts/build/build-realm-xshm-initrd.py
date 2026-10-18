#!/usr/bin/env python3
"""Package the built static Realm test tools as newc initrd."""
import argparse
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--ioctl-perf', type=Path, help='Include the common-profile timing probe')
p.add_argument('--performance-suite', type=Path, help='Include a read-only workload dispatcher')
p.add_argument('--output', type=Path, default=ROOT/'build/realm-xshm/initrd.cpio')
p.add_argument('--gpu-smoke', type=Path, help='Include the static DRM validation tool')
p.add_argument('--glmark-env', type=Path, help='Include the glmark workload configuration and current smoke script')
a = p.parse_args()
if a.performance_suite and (not a.ioctl_perf or not a.glmark_env):
    p.error('--performance-suite requires --ioctl-perf and --glmark-env')
entries = [('init', ROOT/'build/realm-xshm/init', 0o755),
           ('realm-xshm', ROOT/'build/realm-xshm/realm-xshm', 0o755)]
if a.ioctl_perf:
    entries.append(('ioctl-perf', a.ioctl_perf, 0o755))
if a.performance_suite:
    entries.append(('performance-suite.sh', a.performance_suite, 0o755))
if a.gpu_smoke:
    entries.append(('panthor_ioctl_smoke', a.gpu_smoke, 0o755))
if a.glmark_env:
    entries += [('glmark.env', a.glmark_env, 0o644),
                ('gpu-smoke.sh', ROOT/'GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh', 0o755)]
# Read everything before writing, so missing inputs cannot leave a partial archive.
files = [('dev', b'', stat.S_IFDIR | 0o755, 0, 0),
         ('dev/console', b'', stat.S_IFCHR | 0o600, 5, 1)]
files += [(name, path.read_bytes(), stat.S_IFREG | mode, 0, 0)
          for name, path, mode in entries]
archive = bytearray()
for ino, (name, data, mode, major, minor) in enumerate(files + [('TRAILER!!!', b'', 0, 0, 0)], 1):
    encoded = name.encode() + b'\0'
    fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0)
    archive += b'070701' + ''.join(f'{x:08x}' for x in fields).encode() + encoded
    archive += b'\0' * (-len(archive) % 4)
    archive += data
    archive += b'\0' * (-len(archive) % 4)
# The pinned Firecracker passes initrd size directly to RME population;
# KVM requires a whole number of 4 KiB pages. CPIO permits zero padding.
archive += b'\0' * (-len(archive) % 4096)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_bytes(archive)
print(a.output)
