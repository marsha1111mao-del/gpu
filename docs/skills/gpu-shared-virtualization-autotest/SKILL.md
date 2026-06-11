---
name: gpu-shared-virtualization-autotest
description: Use when running, debugging, or reporting the RK3588/OpenCCA shared GPU virtualization path, including vmshm-broker, proxy/client Firecracker VMs, Panthor IOCTL forwarding, two-client GLES shared performance, SD-card kernel/rootfs flashing through the Raspberry Pi, hardware connection checks, and shared run-log collection on /home/mzh/RK3588/gpu.
---

# GPU Shared Virtualization Autotest

## Scope

Use this skill for the vmshm-based GPU sharing path:

```text
client VM userspace /dev/panthor ioctl
  -> panthor-client DRM frontend
  -> client_vmshm_comm / shared-memory RPC
  -> vmshm-broker eventfd relay
  -> proxy_vmshm_comm
  -> panthor-proxy
  -> real Panthor driver in proxy VM
```

Use this skill for one-proxy-one-client smokes and explicit two-client shared
GLES experiments. Do not use it for single-VM passthrough host-vs-VM testing;
use `gpu-passthrough-autotest` for that path.

## Current Environment

Treat these as the current defaults unless the user gives a newer runbook:

- Local workspace: `/home/mzh/RK3588/gpu`
- OpenCCA wrapper workspace: `/home/mzh/RK3588/gpu/opencca`
- Remote RK3588: `root@192.168.31.18`, password `root`
- Remote artifact root: `/root/GPU-SFTP`
- Local artifact root: `/home/mzh/RK3588/gpu/GPU-SFTP`
- Runtime tree: `GPU-SFTP/firecracker-bins`
- Raspberry Pi flasher: `mzh@192.168.31.52`, password/sudo password `root`
- Pi flash root: `/home/mzh/opencca-flash`
- Rockchip storage IDs: `1=EMMC`, `2=SD`, `9=SPINOR`
- This workflow targets SD-card boot only. Do not write eMMC.
- Verified SD layout: p3 `kernel` ext4/extlinux at LBA `0x8000`, p4 `root`
  mounted from `/dev/mmcblk1p4`.
- Verified host kernel/driver: `6.12.0-opencca-pmthor`, `/dev/pmthor`,
  platform driver `pmthor`.

Current runtime layout:

- `firecracker-bins/bin/`: `firecracker`, `vmshm-broker`,
  `gles-compute-smoke`, `panthor_ioctl_smoke`, and helpers.
- `firecracker-bins/configs/shared/vmshm-1client/`: one proxy/client configs.
- `firecracker-bins/configs/shared/vmshm-2client/`: two-client configs.
- `firecracker-bins/kernels/shared/client/Image`: client guest kernel.
- `firecracker-bins/kernels/shared/proxy/Image`: proxy guest kernel.
- `firecracker-bins/rootfs/rootfs.ext2`: lightweight IOCTL/comm base image.
- `firecracker-bins/rootfs/rootfs-panfrost.ext4`: GLES/Panfrost base image.

Important docs to consult before changing hardware, flash, or shared GPU
behavior:

- `/home/mzh/RK3588/gpu/docs/start/RASPBERRY_PI_FLASH_RUNBOOK.md`
- `/home/mzh/RK3588/gpu/opencca/docs/SD_CARD_FLASH_RUNBOOK.md`
- `/home/mzh/RK3588/gpu/docs/kernel_flash_patches/README.md`
- `/home/mzh/RK3588/gpu/docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md`
- `/home/mzh/RK3588/gpu/docs/shared/PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md`
- `/home/mzh/RK3588/gpu/docs/shared/GPU_VIRTUALIZATION_DRIVER_ANALYSIS.md`
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

Do not put `module_blacklist=panthor,pmthor` in extlinux. The current rootfs
keeps boot on `pmthor` with:

```text
/etc/modprobe.d/opencca-gpu.conf: blacklist panthor
/etc/modules-load.d/opencca-gpu.conf: pmthor_drv
```

## Build And Sync Selection

Rebuild only what changed:

- Guest client/proxy kernel code or Kconfig: run
  `scripts/build/build-guest-vmshm-kernels.sh`.
- Firecracker or `vmshm-broker`: run
  `scripts/build/build-firecracker-runtime.sh`.
- IOCTL smoke source: run `scripts/build/build-panthor-ioctl-smoke.sh`.
- vmshm lookup/isolation probe source: run
  `scripts/build/build-vmshm-lookup-probe.sh`.
- GLES smoke source only: prefer the existing ARM64
  `GPU-SFTP/firecracker-bins/bin/gles-compute-smoke`; if remote build deps are
  unavailable, pass `--skip-gles-remote-build`. The current RK host does not
  have `pkg-config`; do not expect remote GLES rebuilds to work until the build
  dependencies are installed.
- Config-only changes: regenerate/sync configs only.
- Rootfs images are not part of ordinary runs; use `--sync-rootfs` only when
  seeding or intentionally replacing base images.

The shared scripts sync `GPU-SFTP/` to `root@192.168.31.18:/root/GPU-SFTP/`
and exclude logs and rootfs unless explicitly requested. The current RK host
has `tar` but may not have `rsync`; the two-client runner has a tar-stream
fallback and atomic `--sync-rootfs` file streaming. Avoid ad hoc sync commands
that overwrite historical logs or rootfs images.

## Shared Test Flow

Before a run:

```bash
cd /home/mzh/RK3588/gpu
sshpass -p root ssh root@192.168.31.18 '
  uname -r
  findmnt -no SOURCE,TARGET,FSTYPE /
  basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)"
  test -e /dev/pmthor
  test -x /root/GPU-SFTP/firecracker-bins/bin/gles-compute-smoke
  pkill -x firecracker || true
  pkill -x vmshm-broker || true
'
```

One-proxy-one-client IOCTL smoke:

```bash
cd /home/mzh/RK3588/gpu
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=vmshm-1client-vm-create-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --vm-create-smoke
```

Primary 32 MiB two-client shared GLES command:

```bash
cd /home/mzh/RK3588/gpu
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=vmshm-2client-gles-32m-opencca-pmthor-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-vmshm-2client-e2e.sh \
  --skip-sync \
  --skip-fetch-logs \
  --gles-compute-smoke \
  --skip-gles-remote-build \
  --gles-smoke-args '--count 8388608 --iterations 20 --warmup 5 --perf' \
  --gles-client-mem-mib 128 \
  --gles-proxy-mem-mib 384
```

For GLES mode, this runner applies the verified default `auto-4cpu-split` when
no explicit CPU placement knobs are supplied:

```text
temporary host online CPUs: 0-3
broker:                     CPU 0
proxy VM:                   CPU 1
client0 VM:                 CPU 2
client1 VM:                 CPU 3
```

The runner restores the previous online CPU mask on exit. Pass
`--no-gles-auto-affinity` only for a deliberate diagnostic run.

When `--skip-fetch-logs` is used, fetch the run manually:

```bash
RUN_ID=<run-id>
sshpass -p root ssh root@192.168.31.18 \
  "cd /root/GPU-SFTP/log/shared/vmshm-2client && tar czf /tmp/${RUN_ID}.tar.gz ${RUN_ID}"
sshpass -p root scp root@192.168.31.18:/tmp/${RUN_ID}.tar.gz /tmp/
mkdir -p "/home/mzh/RK3588/gpu/GPU-SFTP/log/shared/vmshm-2client/${RUN_ID}"
tar xzf "/tmp/${RUN_ID}.tar.gz" \
  -C /home/mzh/RK3588/gpu/GPU-SFTP/log/shared/vmshm-2client
```

Useful two-client GLES knobs:

- `--gles-min-host-available-mib auto` is the normal OOM guard. Use `0` only
  for a deliberate diagnostic run.
- `--gles-host-online-cpus`, `--gles-broker-cpus`, `--gles-proxy-cpus`,
  `--gles-client0-cpus`, and `--gles-client1-cpus` override the default
  `auto-4cpu-split`. Treat alternate placement as diagnostic.
- `--gles-proxy-panthor-stats`, `--gles-panthor-sched-tick-ms`,
  `--gles-panthor-sched-highpri-wq`, and
  `--gles-panthor-proxy-group-core-partitions` change timing; label those runs
  as diagnostic.
- `--gles-vmshm-isolation-probe` is the negative isolation harness. It keeps a
  client0 vmshm-backed BO alive, extracts that `payload=0x...` handle from the
  proxy log, and makes client1 try to look it up while spoofing VMID 1. Treat
  the run as passing only when both clients pass GLES and client1 logs
  `VMSHM_ISOLATION_RESULT=PASS`.

Shared GLES runners reuse the remote base `rootfs-panfrost.ext4` and inject the
payload immediately before VM launch. Do not create per-count rootfs variants;
`--gles-smoke-args` controls workload size and iteration policy.

## Pass Criteria And Reporting

Always inspect logs before reporting success. Required evidence:

- `RESULT: GLES_PASS` for shared GLES or `RESULT: PASS` for IOCTL/comm smokes
- `GPU_SMOKE_RESULT=PASS` and `COMPUTE_CHECK=PASS` for GLES runs
- Both clients show Mali/Panfrost renderer, not a software renderer
- `rootfs_payload_inject_done payload=gles-compute` in rootfs-prep logs
- For the default 32 MiB shared run, `GLES affinity profile: auto-4cpu-split`
  and CPU restore evidence in `affinity.log`
- No GPU fault, job timeout, panic, Oops, host OOM, or Firecracker-killed symptom

Verified 2026-06-12 32 MiB default reference:

```text
run: GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-autoaffinity-20260612-010111
result: GLES_PASS
GLES remote build: 0
GLES affinity profile: auto-4cpu-split
renderer: Mali-G610 (Panfrost)
GL: OpenGL ES 3.1 Mesa 25.0.7-2
client0 avg iter_total: 27311.35 us
client1 avg iter_total: 27453.75 us
shared average: 27382.55 us
host baseline: 25458.05 us
host/share: 0.930
target: >= 0.85
```

A good final report includes the run ID, local log path, rebuilt/synced/skipped
components, rootfs/config paths, client0/client1 result summaries, and the first
meaningful failure log if the run failed.
