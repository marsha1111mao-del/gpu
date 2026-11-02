#!/usr/bin/env python3
"""Package the built static Realm test tools as newc initrd."""
import argparse
import hashlib
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--ioctl-perf', type=Path, help='Include the common-profile timing probe')
p.add_argument('--performance-suite', type=Path, help='Include a read-only workload dispatcher')
p.add_argument('--output', type=Path, default=ROOT/'build/realm-xshm/initrd.cpio')
p.add_argument('--gpu-smoke', type=Path, help='Include the static DRM validation tool')
p.add_argument('--gpu-private', type=Path, help='Include the private BO/RSI validation tool')
p.add_argument('--gpu-firmware', type=Path, help='Include the pinned firmware for RMM private-service bootstrap')
p.add_argument('--gles-ml', type=Path, help='Include the matched AArch64 ML workload override')
p.add_argument('--gles-compute', type=Path, help='Include the matched GLES compute/GPU eventfd probe override')
p.add_argument('--tools-dir', type=Path, default=ROOT/'build/realm-xshm',
               help='Directory containing the built init and realm-xshm tools')
p.add_argument('--glmark-env', type=Path, help='Include the glmark workload configuration and current smoke script')
a = p.parse_args()
if a.performance_suite and not a.glmark_env:
    p.error('--performance-suite requires --glmark-env; the ioctl profile additionally needs --ioctl-perf')
if a.gpu_firmware and not a.gpu_private:
    p.error('--gpu-firmware requires --gpu-private')
if a.gles_compute and not a.glmark_env:
    p.error('--gles-compute requires --glmark-env')
entries = [('init', a.tools_dir/'init', 0o755),
           ('realm-xshm', a.tools_dir/'realm-xshm', 0o755)]
if a.ioctl_perf:
    entries.append(('ioctl-perf', a.ioctl_perf, 0o755))
if a.performance_suite:
    entries.append(('performance-suite.sh', a.performance_suite, 0o755))
if a.gpu_smoke:
    entries.append(('panthor_ioctl_smoke', a.gpu_smoke, 0o755))
if a.gpu_private:
    entries.append(('realm-gpu-private', a.gpu_private, 0o755))
if a.gles_ml:
    entries.append(('gles-ml-smoke', a.gles_ml, 0o755))
if a.gles_compute:
    entries.append(('gles-compute-smoke', a.gles_compute, 0o755))
if a.gpu_firmware:
    firmware = a.gpu_firmware.read_bytes()
    if len(firmware) != 274432 or hashlib.sha256(firmware).hexdigest() != '43c3c36b914c031d88ae152fd89019d8f99ad41d9879fb5ab7496ed13f7b378b':
        p.error('--gpu-firmware does not match the firmware pinned by RMM')
if a.glmark_env:
    entries += [('glmark.env', a.glmark_env, 0o644),
                ('gpu-smoke.sh', ROOT/'GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh', 0o755)]
# Read everything before writing, so missing inputs cannot leave a partial archive.
files = [('dev', b'', stat.S_IFDIR | 0o755, 0, 0),
         ('dev/console', b'', stat.S_IFCHR | 0o600, 5, 1)]
files += [(name, path.read_bytes(), stat.S_IFREG | mode, 0, 0)
          for name, path, mode in entries]
if a.gpu_firmware:
    files.append(('mali_csffw.bin', firmware, stat.S_IFREG | 0o644, 0, 0))
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
