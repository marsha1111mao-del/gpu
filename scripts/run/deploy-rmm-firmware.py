#!/usr/bin/env python3
"""Deploy built RMM firmware to SD only, with boot backup and UART capture.

Run under lab-run.py --allow-rk-reboot. Does not update Host kernel or rootfs.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--firmware', type=Path, required=True)
p.add_argument('--run-id', required=True)
a = p.parse_args()
if os.getenv('RUN_ID') != a.run_id or os.getenv('GPU_LAB_ALLOW_RK_REBOOT') != '1':
    p.error('run through the lab wrapper with matching --run-id')
if not a.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run_id):
    p.error('invalid run-id')
out = ROOT/'build/firmware-runs'/a.run_id
out.mkdir(parents=True, exist_ok=False)
candidate = '/home/mzh/opencca-flash/snapshot/'+a.run_id
stop = candidate+'/.uart-stop'
reader = None
logs = []
result = {'run_id': a.run_id, 'status': 'PREPARING', 'storage_id': 2,
          'firmware': str(a.firmware.resolve()), 'images': {}}


def save():
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')


def ssh(role, command, **kwargs):
    args, env = resources.ssh(role)
    return subprocess.run(args+[command], env=env, check=True, **kwargs)


def quote(value):
    return shlex.quote(str(value))


save()
try:
    with (out/'layout.json').open('w') as layout:
        subprocess.run(['python3', str(ROOT/'opencca/scripts/check-firmware-layout.py'),
                        '--rmm', str(a.firmware/'tf-rmm.elf'),
                        '--uboot', str(a.firmware/'u-boot')], check=True, stdout=layout)
    before = resources.audit('rk')
    pi = resources.audit('pi')
    (out/'pi-before.json').write_text(json.dumps(pi, indent=2)+'\n')
    if resources.violations(pi) or pi['active_lab_processes']:
        raise RuntimeError('Pi resources/flash activity failed preflight')
    # Check actual SD layout before backing up or entering Maskrom.
    ssh('rk', "test \"$(findmnt -no SOURCE /)\" = /dev/mmcblk1p4 && "
                "test \"$(cat /sys/class/block/mmcblk1/device/type)\" = SD && "
                "test \"$(cat /sys/class/block/mmcblk1p1/start)\" = 64 && "
                "test \"$(cat /sys/class/block/mmcblk1p2/start)\" = 16384 && "
                "test \"$(cat /sys/class/block/mmcblk1p2/size)\" = 8192",
                capture_output=True)
    for name, maximum in (('idbloader.img', 7105*512), ('u-boot.itb', 8192*512)):
        image = a.firmware/name
        if not 0 < image.stat().st_size <= maximum:
            raise RuntimeError(f'{name} exceeds the verified SD slot')
        result['images'][name] = hashlib.sha256(image.read_bytes()).hexdigest()
    print('Backing up actual SD boot area to controller', flush=True)
    backup = out/'sd-boot-before.bin'
    with backup.open('wb') as target:
        ssh('rk', 'dd if=/dev/mmcblk1 bs=512 count=24576 status=none', stdout=target)
    if backup.stat().st_size != 24576*512:
        raise RuntimeError('incomplete SD boot backup')
    result['backup_sha256'] = hashlib.sha256(backup.read_bytes()).hexdigest()
    save()
    ssh('pi', 'mkdir '+quote(candidate))
    for name in result['images']:
        with (a.firmware/name).open('rb') as source:
            ssh('pi', 'cat > '+quote(candidate+'/'+name), stdin=source)
        verified = ssh('pi', 'sha256sum '+quote(candidate+'/'+name), capture_output=True, text=True)
        if verified.stdout.split()[0] != result['images'][name]:
            raise RuntimeError(f'Pi hash mismatch: {name}')
    # Verify the deployed flash entry actually selects storage, rather than
    # trusting an environment variable which an older script might ignore.
    ssh('pi', "grep -Fq 'select_storage \"$OPENCCA_FIRMWARE_STORAGE_ID\"' /home/mzh/opencca-flash/flash.sh")
    uart = (out/'uart.log').open('wb')
    uart_err = (out/'uart.stderr').open('wb')
    logs += [uart, uart_err]
    code = ('import os,select,sys,time; from pathlib import Path\n'
            'fd=os.open("/dev/ttyUSB0",os.O_RDONLY|os.O_NONBLOCK)\n'
            'end=time.monotonic()+120\n'
            f'while time.monotonic()<end and not Path({stop!r}).exists():\n'
            ' if select.select([fd],[],[],1)[0]:\n'
            '  data=os.read(fd,65536)\n'
            '  if data: sys.stdout.buffer.write(data);sys.stdout.buffer.flush()\n')
    args, env = resources.ssh('pi')
    reader = subprocess.Popen(args+['stty -F /dev/ttyUSB0 1500000 raw -echo && python3 -u -c '+quote(code)],
                              env=env, stdout=uart, stderr=uart_err)
    result['status'] = 'FLASHING'
    save()
    print('Flashing idbloader/u-boot to SD storage ID 2', flush=True)
    command = ('cd /home/mzh/opencca-flash && sudo -S -p "" env '
               'OPENCCA_FIRMWARE_STORAGE_ID=2 OPENCCA_NO_COLOR=1 '
               'OPENCCA_FLASH_IDBLOADER='+quote(candidate+'/idbloader.img')+' '
               'OPENCCA_FLASH_UBOOT='+quote(candidate+'/u-boot.itb')+' ./flash.sh firmware')
    with (out/'flash.log').open('wb') as target:
        sudo_password = os.getenv('OPENCCA_RPI_SUDO_PASSWORD', resources.ssh('pi')[1]['SSHPASS'])
        ssh('pi', command, input=(sudo_password+'\n').encode(), stdout=target,
            stderr=subprocess.STDOUT, timeout=100)
    print('Waiting for Host SSH', flush=True)
    deadline = time.monotonic()+180
    while True:
        try:
            ssh('rk', 'uname -a', capture_output=True, timeout=12)
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if time.monotonic() >= deadline:
                raise RuntimeError('Host did not recover; preserve UART and boot backup')
            time.sleep(2)
    # Restore exactly the CPU set recorded before reboot, before wrapper audit.
    restore = ('from pathlib import Path\n'
               f'wanted={before["online_cpus"]!r}\n'
               'cpus=set()\n'
               'for token in wanted.split(","):\n'
               ' ends=list(map(int,token.split("-")))\n'
               ' cpus.update(range(ends[0],ends[-1]+1))\n'
               'for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/online"):\n'
               ' number=int(path.parent.name[3:])\n'
               ' value="1" if number in cpus else "0"\n'
               ' if path.read_text().strip()!=value: path.write_text(value)\n')
    ssh('rk', 'python3 -c '+quote(restore))
    capability = ('import fcntl,os\n'
                  'device=os.open("/dev/kvm",os.O_RDWR|os.O_CLOEXEC)\n'
                  'try: print(fcntl.ioctl(device,0xae03,300))\n'
                  'finally: os.close(device)\n')
    result['rme_capability'] = int(ssh('rk', 'python3 -c '+quote(capability),
                                       capture_output=True, text=True).stdout.strip())
    if result['rme_capability'] != 1:
        raise RuntimeError('Host recovered but RMM/Realm capability is unavailable')
    result['status'] = 'DEPLOYED_HOST_RECOVERED'
except Exception as exc:
    result['status'] = 'FAIL'
    result['error'] = str(exc)
finally:
    if reader is not None:
        try:
            ssh('pi', 'touch '+quote(stop), timeout=12)
            reader.wait(timeout=8)
            ssh('pi', 'rm -- '+quote(stop), timeout=12)
        except (subprocess.SubprocessError, OSError) as exc:
            result['uart_cleanup_error'] = str(exc)
            result['status'] = 'FAIL'
            reader.terminate()
            reader.wait(timeout=8)
    for stream in logs:
        stream.close()
    save()
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'DEPLOYED_HOST_RECOVERED' else 1)
