---
name: gpu-passthrough-autotest
description: Use when running, debugging, or reporting the RK3588/OpenCCA single-VM GPU passthrough path, including host-vs-passthrough GLES performance, pmthor-to-panthor host-direct switching, Firecracker passthrough VM runs, SD-card kernel/rootfs flashing through the Raspberry Pi, hardware connection checks, and passthrough log collection on /home/mzh/RK3588/gpu.
---

# GPU Passthrough Autotest

## Scope

Use this skill for the single-VM Mali/Panthor GPU passthrough path:

```text
OpenCCA host pmthor / KVM / Firecracker
  -> one passthrough VM
  -> guest Panthor owns the passed-through GPU view
  -> GLES compute smoke/perf workload
```

Do not use this skill for vmshm proxy/client GPU sharing; use
`gpu-shared-virtualization-autotest` for that path.

## Current Environment

Treat these as the current defaults unless the user gives a newer runbook:

- Local workspace: `/home/mzh/RK3588/gpu`
- OpenCCA wrapper workspace: `/home/mzh/RK3588/gpu/opencca`
- Remote RK3588: `root@192.168.31.18`, password `root`
- Remote artifact root: `/root/GPU-SFTP`
- Local artifact root: `/home/mzh/RK3588/gpu/GPU-SFTP`
- Raspberry Pi flasher: `mzh@192.168.31.52`, password/sudo password `root`
- Pi flash root: `/home/mzh/opencca-flash`
- Rockchip storage IDs: `1=EMMC`, `2=SD`, `9=SPINOR`
- This workflow targets SD-card boot only. Do not write eMMC.
- Verified SD layout: p3 `kernel` ext4/extlinux at LBA `0x8000`, p4 `root`
  mounted from `/dev/mmcblk1p4`.
- Verified kernel/driver: `6.12.0-opencca-pmthor`, `/dev/pmthor`, platform
  driver `pmthor`.

Important docs to consult before changing hardware or flash behavior:

- `/home/mzh/RK3588/gpu/docs/start/RASPBERRY_PI_FLASH_RUNBOOK.md`
- `/home/mzh/RK3588/gpu/opencca/docs/SD_CARD_FLASH_RUNBOOK.md`
- `/home/mzh/RK3588/gpu/docs/kernel_flash_patches/README.md`
- `/home/mzh/RK3588/gpu/docs/start/OPENCCA_SD_KERNEL_FLASH_AND_GPU_32M_REPORT_20260611.md`

## Hardware And Pi Control

Expected physical topology:

```text
control host -> LAN -> Raspberry Pi 192.168.31.52
Raspberry Pi -> USB OTG/Maskrom -> RK3588
Raspberry Pi -> optional USB-TTL UART -> RK3588 serial console
Raspberry Pi -> power control -> RK3588 board power
```

Quick checks:

```bash
cd /home/mzh/RK3588/gpu
sshpass -p root ssh -o StrictHostKeyChecking=accept-new mzh@192.168.31.52 \
  'hostname; test -x /home/mzh/opencca-flash/flash.sh && echo flash.sh=ok; ls -l /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null || true'

sshpass -p root ssh -o StrictHostKeyChecking=accept-new root@192.168.31.18 \
  'hostname; uname -r; findmnt -no SOURCE,TARGET,FSTYPE /; basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)"; ls -l /dev/pmthor /dev/dri/card0 2>/dev/null || true'
```

Use the Pi wrapper for reboot/Maskrom/flash operations:

```bash
cd /home/mzh/RK3588/gpu
OPENCCA_RPI_HOST=mzh@192.168.31.52 \
OPENCCA_RPI_PASSWORD=root \
OPENCCA_RPI_SUDO_PASSWORD=root \
OPENCCA_RK_HOST=root@192.168.31.18 \
OPENCCA_RK_PASSWORD=root \
  ./opencca/scripts/firmware/flash-rk3588-via-pi.sh --reboot --wait-rk
```

For serial logs:

```bash
sshpass -p root ssh -t mzh@192.168.31.52 \
  'cd /home/mzh/opencca-flash && ./flash.sh minicom'
```

If `/dev/ttyUSB0` is absent on the Pi, do not assume serial is connected. Check
the USB-TTL wiring and the runbook before interpreting missing serial logs.

## SD Flashing Guardrails

For firmware/rootfs/kernel flashing, keep the storage target on SD:

```text
OPENCCA_FIRMWARE_STORAGE_ID=2
OPENCCA_ROOTFS_STORAGE_ID=2
OPENCCA_KERNEL_STORAGE_ID=2
```

SD firmware only:

```bash
cd /home/mzh/RK3588/gpu/opencca
OPENCCA_RPI_PASSWORD=root OPENCCA_RPI_SUDO_PASSWORD=root OPENCCA_RK_PASSWORD=root \
  ./scripts/firmware/flash-rk3588-via-pi.sh --flash-sd-firmware --wait-rk
```

Kernel-only p3 update after the compatible SD layout exists:

```bash
cd /home/mzh/RK3588/gpu/opencca
./scripts/image/build-raw-kernel-image.sh \
  --image /path/to/Image \
  --initrd /path/to/initrd.img \
  --dtb snapshot/rk3588-rock-5b.dtb \
  --root PARTLABEL=root \
  --version 6.12.0-opencca-pmthor \
  --cmdline 'rootwait isolcpus=1,2,3 maxcpus=2 nohlt cpuidle.off=1 rcupdate.rcu_cpu_st ignore_loglevel initcall_debug' \
  --output snapshot/kernel-pmthor-rootfs-matched-extlinux.img

OPENCCA_RPI_PASSWORD=root OPENCCA_RPI_SUDO_PASSWORD=root OPENCCA_RK_PASSWORD=root \
  ./scripts/firmware/flash-rk3588-via-pi.sh \
  --kernel-image snapshot/kernel-pmthor-rootfs-matched-extlinux.img \
  --flash-kernel --wait-rk
```

Do not put `module_blacklist=panthor,pmthor` in extlinux. That blocks the
passthrough runner from manually loading `panthor` for the host-direct half.
The current rootfs keeps boot on `pmthor` with:

```text
/etc/modprobe.d/opencca-gpu.conf: blacklist panthor
/etc/modules-load.d/opencca-gpu.conf: pmthor_drv
```

## Passthrough Test Flow

Before a run:

```bash
cd /home/mzh/RK3588/gpu
sshpass -p root ssh root@192.168.31.18 '
  uname -r
  findmnt -no SOURCE,TARGET,FSTYPE /
  basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)"
  test -e /dev/pmthor
  pkill -f firecracker || true
  pkill -f vmshm-broker || true
'
```

The RK rootfs may not have working build dependencies. For known-good 32 MiB
runs, reuse the staged ARM64 smoke binary at
`GPU-SFTP/firecracker-bins/bin/gles-compute-smoke` and pass
`--skip-remote-build`.

Primary 32 MiB host-vs-passthrough command:

```bash
cd /home/mzh/RK3588/gpu
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=gpu-perf-32m-opencca-pmthor-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --skip-sync \
  --skip-remote-build \
  --skip-fetch-logs \
  --count 8388608 \
  --iterations 20 \
  --warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900
```

When `--skip-fetch-logs` is used, fetch the run manually:

```bash
RUN_ID=<run-id>
sshpass -p root ssh root@192.168.31.18 \
  "cd /root/GPU-SFTP/log/passthrough/perf && tar czf /tmp/${RUN_ID}.tar.gz ${RUN_ID}"
sshpass -p root scp root@192.168.31.18:/tmp/${RUN_ID}.tar.gz /tmp/
mkdir -p "/home/mzh/RK3588/gpu/GPU-SFTP/log/passthrough/perf/${RUN_ID}"
tar xzf "/tmp/${RUN_ID}.tar.gz" \
  -C /home/mzh/RK3588/gpu/GPU-SFTP/log/passthrough/perf
```

Formal broader sweeps can use the runner defaults for 4 MiB, 16 MiB, and
64 MiB:

```bash
cd /home/mzh/RK3588/gpu
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=gpu-perf-host-vs-passthrough-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900
```

Use diagnostic flags such as `--guest-panthor-pt-timing`,
`--pmthor-irq-stats`, `--guest-panthor-irq-stats`,
`--guest-panthor-submit-stats`, `--vm-huge-pages-2m`, taskset, IRQ affinity, or
perf tracing only when explaining an anomaly. Label those runs as diagnostic,
not formal baselines.

## Pass Criteria And Reporting

Always inspect logs before reporting success. Required evidence:

- `RESULT: PASS`
- `GPU_SMOKE_RESULT=PASS` and `COMPUTE_CHECK=PASS`
- Renderer is Mali/Panfrost, not a software renderer
- No GPU fault, job timeout, panic, Oops, or Firecracker-killed symptom
- The runner restored the host driver to `pmthor`

Verified 2026-06-11 32 MiB reference:

```text
run: GPU-SFTP/log/passthrough/perf/gpu-perf-32m-opencca-pmthor-20260611-234401
host avg iter_total: 25471.05 us
passthrough VM avg iter_total: 33016.80 us
host/vm ratio: 0.771
renderer: Mali-G610 (Panfrost)
GL: OpenGL ES 3.1 Mesa 25.0.7-2
restored driver: pmthor
```

A good final report includes the run ID, local log path, rebuilt/synced/skipped
components, active rootfs/config, the Host/VM ratio table or 32 MiB numbers,
and the first meaningful failure log if the run failed.
