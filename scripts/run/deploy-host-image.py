#!/usr/bin/env python3
"""Replace the active SD extlinux Image, preserving its initrd, DTB and modules."""
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

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--image', type=Path, required=True)
p.add_argument('--config', type=Path, required=True)
p.add_argument('--release', required=True)
p.add_argument('--run-id', required=True)
a = p.parse_args()
if os.getenv('RUN_ID') != a.run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '1':
    p.error('requires lab-run.py --allow-rk-reboot with the same run-id')
if not re.fullmatch(r'[a-zA-Z0-9_-]+', a.run_id):
    p.error('invalid run-id')
out = ROOT/'build/host-runs'/a.run_id
out.mkdir(parents=True, exist_ok=False)
remote_dir = '/root/GPU-SFTP/log/host-deploy/'+a.run_id
mount_dir = remote_dir+'/boot'
state = {'run_id': a.run_id, 'status': 'PREPARING', 'release': a.release,
         'image_sha256': hashlib.sha256(a.image.read_bytes()).hexdigest()}


def save():
    (out/'summary.json').write_text(json.dumps(state, indent=2)+'\n')


def ssh(command, **kwargs):
    args, env = resources.ssh('rk')
    return subprocess.run(args+[command], env=env, check=True, **kwargs)


def py(code, **kwargs):
    return ssh('python3 -c '+shlex.quote(code), **kwargs)


def config(text):
    return {line.split('=', 1)[0]: line for line in text.splitlines()
            if line.startswith(('CONFIG_', '# CONFIG_'))}


mounted = False
save()
try:
    image = a.image.read_bytes()
    version = re.search(rb'Linux version ([^\s\x00]+)', image)
    if not version or version[1].decode() != a.release:
        raise RuntimeError('Image embedded release does not match requested modules')
    before = resources.audit('rk')
    if before['kernel'] != a.release or before['active_lab_processes']:
        raise RuntimeError('Host release/activity mismatch')
    boot_id = ssh('cat /proc/sys/kernel/random/boot_id', capture_output=True, text=True).stdout.strip()
    state['boot_id_before'] = boot_id
    current = ssh('zcat /proc/config.gz', capture_output=True).stdout.decode()
    (out/'running.config').write_text(current)
    old, new = config(current), config(a.config.read_text())
    differences = [key for key in old.keys() | new.keys() if old.get(key) != new.get(key)]
    state['config_differences'] = sorted(differences)
    allowed_config_changes = {'CONFIG_OPENCCA_DMA_GUARD',
                              'CONFIG_OPENCCA_MANAGED_IOMMU',
                              'CONFIG_KVM_ARM_OPENCCA'}
    if any(key not in allowed_config_changes for key in differences):
        raise RuntimeError('configuration changes beyond OpenCCA services require a separate module deployment')
    # This entry updates an already compatible kernel, not arbitrary SD layouts.
    ssh('test "$(findmnt -no SOURCE /)" = /dev/mmcblk1p4 && '
        'test "$(cat /sys/class/block/mmcblk1/device/type)" = SD && '
        'test "$(lsblk -no PARTLABEL /dev/mmcblk1p3)" = kernel && '
        'test "$(cat /sys/class/block/mmcblk1p3/start)" = 32768 && '
        'test "$(cat /sys/class/block/mmcblk1p3/size)" = 262144 && '
        '! findmnt -rn -S /dev/mmcblk1p3', capture_output=True)
    ssh('test -d '+shlex.quote('/lib/modules/'+a.release))
    backup = out/'sd-kernel-before.img'
    with backup.open('wb') as target:
        ssh('dd if=/dev/mmcblk1p3 bs=1M status=none', stdout=target)
    if backup.stat().st_size != 128*1024**2:
        raise RuntimeError('incomplete kernel partition backup')
    state['backup_sha256'] = hashlib.sha256(backup.read_bytes()).hexdigest()
    save()
    ssh('mkdir -p '+shlex.quote(remote_dir))
    ssh('mkdir '+shlex.quote(mount_dir))
    with a.image.open('rb') as source:
        ssh('cat > '+shlex.quote(remote_dir+'/Image'), stdin=source)
    digest = ssh('sha256sum '+shlex.quote(remote_dir+'/Image'), capture_output=True, text=True)
    if digest.stdout.split()[0] != state['image_sha256']:
        raise RuntimeError('uploaded Image hash mismatch')
    ssh('mount /dev/mmcblk1p3 '+shlex.quote(mount_dir))
    mounted = True
    code = ('from pathlib import Path\nimport hashlib,json,os,shutil\n'
            f'base=Path({mount_dir!r})\n'
            'configs=[base/"extlinux/extlinux.conf",base/"boot/extlinux/extlinux.conf"]\n'
            'configs=[p for p in configs if p.is_file()]\nassert len(configs)==1\n'
            'conf=configs[0].read_text()\n'
            'images=sorted({l.split()[1] for l in conf.splitlines() '
            'if l.strip() and l.split()[0].lower()=="linux"})\n'
            'assert len(images)==1 and "root=PARTLABEL=root" in conf\n'
            'target=(base/images[0].lstrip("/")).resolve()\n'
            'assert target.is_relative_to(base) and target.is_file()\n'
            f'assert target.name=="vmlinuz-{a.release}"\n'
            'temporary=target.with_name(target.name+".dma-guard-new")\n'
            'assert not temporary.exists()\n'
            f'source=Path({remote_dir + "/Image"!r})\n'
            'old_hash=hashlib.sha256(target.read_bytes()).hexdigest()\n'
            'atomic=shutil.disk_usage(base).free > source.stat().st_size+8*1024**2\n'
            'if atomic:\n'
            ' shutil.copyfile(source,temporary)\n'
            ' with temporary.open("rb") as f: os.fsync(f.fileno())\n'
            ' os.replace(temporary,target)\n'
            'else:\n'
            ' # The controller already owns a full partition backup. Also keep\n'
            ' # a verified file backup on the root filesystem for write errors.\n'
            ' assert shutil.disk_usage(source.parent).free > target.stat().st_size+8*1024**2\n'
            ' assert shutil.disk_usage(base).free+target.stat().st_size > source.stat().st_size+8*1024**2\n'
            ' backup=source.with_name("kernel-before")\n'
            ' assert not backup.exists()\n'
            ' shutil.copyfile(target,backup)\n'
            ' with backup.open("rb") as f: os.fsync(f.fileno())\n'
            ' assert hashlib.sha256(backup.read_bytes()).hexdigest()==old_hash\n'
            ' try:\n'
            '  shutil.copyfile(source,target)\n'
            '  with target.open("rb") as f: os.fsync(f.fileno())\n'
            ' except Exception:\n'
            '  shutil.copyfile(backup,target)\n'
            '  with target.open("rb") as f: os.fsync(f.fileno())\n'
            '  raise\n'
            'os.sync()\n'
            'print(json.dumps({"extlinux":conf,"image_path":str(target),'
            '"update_mode":"atomic" if atomic else "in_place_with_backups",'
            '"old_image_sha256":old_hash,"new_image_sha256":'
            'hashlib.sha256(target.read_bytes()).hexdigest()}))\n')
    state['boot'] = json.loads(py(code, capture_output=True, text=True).stdout)
    if state['boot']['new_image_sha256'] != state['image_sha256']:
        raise RuntimeError('boot Image hash mismatch')
    ssh('umount '+shlex.quote(mount_dir))
    mounted = False
    state['status'] = 'REBOOTING'
    save()
    try:
        ssh('systemctl reboot', capture_output=True, timeout=12)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    deadline = time.monotonic()+180
    # Require a new boot ID, not the still-running pre-reboot SSH endpoint.
    while True:
        try:
            new_boot_id = ssh('cat /proc/sys/kernel/random/boot_id', capture_output=True,
                              text=True, timeout=12).stdout.strip()
            loaded = ssh('zcat /proc/config.gz', capture_output=True, timeout=12).stdout.decode()
            if new_boot_id != boot_id and config(loaded) == new:
                state['boot_id_after'] = new_boot_id
                break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('candidate kernel did not recover; retain SD backup for Pi recovery')
        time.sleep(2)
    restore = ('from pathlib import Path\n'
               f'wanted={before["online_cpus"]!r}\ncpus=set()\n'
               'for token in wanted.split(","):\n'
               ' ends=list(map(int,token.split("-")));cpus.update(range(ends[0],ends[-1]+1))\n'
               'for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/online"):\n'
               ' value="1" if int(path.parent.name[3:]) in cpus else "0"\n'
               ' if path.read_text().strip()!=value: path.write_text(value)\n')
    py(restore)
    after = resources.audit('rk')
    if after['kernel'] != a.release or after['gpu_driver'] != before['gpu_driver']:
        raise RuntimeError('candidate release/GPU ownership mismatch')
    state['status'] = 'DEPLOYED_HOST_RECOVERED'
except Exception as exc:
    state['status'] = 'FAIL'
    state['error'] = str(exc)
    if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
        state['stderr'] = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr
finally:
    if mounted:
        try:
            ssh('umount '+shlex.quote(mount_dir), timeout=12)
        except subprocess.SubprocessError as exc:
            state['unmount_error'] = str(exc)
    save()
print(json.dumps(state, indent=2))
raise SystemExit(0 if state['status'] == 'DEPLOYED_HOST_RECOVERED' else 1)
