# OpenCCA SD Kernel Flash And GPU 32MiB Report

Date: 2026-06-11

Target board: ROCK 5B / RK3588 at `root@192.168.31.18`
Flash host: Raspberry Pi at `mzh@192.168.31.52`

## Summary

- The OpenCCA SD image now separates kernel boot content and rootfs:
  `p3 kernel` starts at LBA `0x8000`, and `p4 root` starts at LBA `0x48000`.
- The kernel slot is a 128 MiB ext4 boot partition with extlinux, vmlinuz,
  initrd, and `rk3588-rock-5b.dtb`. This replaced the earlier raw FIT attempt
  because the extlinux/initrd path matches the known-working OpenCCA Debian boot.
- A one-time full SD flash initialized the new layout, and a later kernel-only
  flash wrote only the `kernel` partition on SD storage ID `2`.
- The board is currently online from SD with root mounted from `/dev/mmcblk1p4`.
- Two pmthor host-kernel boot attempts were made through the kernel-only p3
  workflow. Both flashed successfully but did not return SSH, so the board was
  recovered by flashing only the known-good stock p3 kernel partition.
- GPU performance testing remains blocked by the custom host `pmthor` boot path.
  The recovered kernel exposes stock `panthor` and no `/dev/pmthor`, so shared
  and passthrough measurements must not be treated as valid yet.
- GitHub repositories `marsha1111mao-del/gpu`, `marsha1111mao-del/opencca`,
  `marsha1111mao-del/tf-rmm`, and `marsha1111mao-del/vmshm-broker` were checked
  on 2026-06-11 22:24 CST and are public (`isPrivate=false`).

## Implemented OpenCCA Changes

OpenCCA submodule:

- `scripts/image/build-raw-kernel-image.sh`
  Builds `snapshot/kernel-extlinux.img`, a fixed-size ext4 kernel boot
  partition. The script name is retained for compatibility with the earlier
  patch notes.
- `scripts/image/convert-opencca-image-to-raw-kernel-layout.py`
  Converts an old root-at-`0x8000` OpenCCA image into the separated layout by
  writing the kernel boot partition at p3 and moving rootfs to p4.
- `scripts/firmware/flash-raw-kernel-on-pi.sh`
  Pi-side SD kernel-slot writer. It enters Maskrom, selects Rockchip storage ID
  `2`, validates GPT, writes only LBA `0x8000`, releases Maskrom, and resets the
  board.
- `scripts/firmware/validate-gpt-slot.py`
  Validates that the GPT dump has a non-overlapping `kernel` partition at the
  expected LBA and size.
- `scripts/firmware/configure-raw-kernel-slot-sources.sh`
  Patches U-Boot to `CONFIG_BOOTCOMMAND="bootflow scan"` and updates
  `debian-image-recipes` to generate p3 `kernel` plus p4 `root`.
- `scripts/firmware/flash-rk3588-via-pi.sh`
  Adds `--build-kernel-image`, `--sync-kernel`, `--flash-kernel`, and
  `--kernel-image`.

Nested source changes applied in the current local worktree and reproducible by
`opencca/scripts/firmware/configure-raw-kernel-slot-sources.sh`:

- `opencca/u-boot/rk3588_fragment.config`
  Uses `bootflow scan`.
- `opencca/debian-image-recipes/opencca-image-rockchip-rk3588.yaml`
  Defines p3 `kernel` ext4 and p4 `root` ext4.

## Verified Kernel/Rootfs Split

Converted image:

```text
rootfs/opencca-image-rockchip-rock5b-rk3588-extlinux-kernel.img
size=4134218240 bytes
```

GPT:

```text
loader1 start=64     size=7105
loader2 start=16384  size=8192
kernel start=32768   size=262144  label=kernel
root   start=294912  size=7779699 label=root
```

Known-good kernel boot partition:

```text
snapshot/kernel-extlinux.img
size=134217728 bytes
sha256=5b41a8d86bdc52722ca20c4d81a2e9fc4db230b4de4b19c44430beae81ccbc2e
```

Input artifact hashes:

```text
vmlinuz-6.12.0-opencca-wip sha256=6c4e7dbd7afd5680d30437a84baa1a307fc29c11e74c4039724932e1c60494d6
initrd.img-6.12.0-opencca-wip sha256=535902f4aec8a8f2b7afff6ca0c93c6ab74e3265ef32dbb025798ac7ed5111cd
rk3588-rock-5b.dtb sha256=2a186c6e0511daaab791ee53e83feb4f58078c1342b4aae56037e9337b5fecaf
```

Kernel-only flash command verified:

```bash
OPENCCA_RPI_PASSWORD=root OPENCCA_RPI_SUDO_PASSWORD=root OPENCCA_RK_PASSWORD=root \
  ./scripts/firmware/flash-rk3588-via-pi.sh \
  --kernel-image snapshot/kernel-extlinux.img \
  --flash-kernel --wait-rk
```

Current RK evidence after the kernel-only flash:

```text
opencca-rock5b-rk3588
Linux opencca-rock5b-rk3588 6.12.0-opencca-wip #wip SMP PREEMPT Thu Jul 31 08:44:48 UTC 2025 aarch64
root=PARTLABEL=root rootwait isolcpus=1,2,3 maxcpus=2 nohlt cpuidle.off=1 rcupdate.rcu_cpu_st maxcpus=2
/dev/mmcblk1p4 / ext4
mmcblk1p3 128M ext4 kernel kernel
mmcblk1p4 3.7G ext4 root   root /
```

## GPU 32MiB Status

Requested workload size: 32 MiB, represented by `--count 8388608` uint32
elements.

Current host GPU state:

```text
no /dev/pmthor
/dev/dri/card0
/dev/dri/card1
/dev/dri/renderD128
panthor loaded
```

The shared and passthrough paths require the custom host `pmthor` driver because
Proxy VM passthrough depends on host-side pmthor IRQ/MMIO handling. Therefore
the current stock OpenCCA boot cannot produce a valid shared/passthrough/Host
comparison.

The pmthor host kernel source artifact used for both attempts was:

```text
GPU-SFTP/linux-host-kernel/Image
sha256=628413abab5b03cdbf8c5bf719650bb08f2d410c62d3d5d525aa68f5d5ec1fc8
Linux version 6.12.0-opencca-wip #2 SMP PREEMPT Thu Jun 11 15:07:12 CST 2026
```

Attempt 1 built and flashed:

```text
snapshot/kernel-pmthor-extlinux.img
sha256=3e29aff748388b5bdde6a81a2fa707b51a3eaea3b56d97f6da7d14c211606a81
```

Result: p3 SD write completed, board reset, but SSH did not return. Independent
checks showed `ssh: No route to host`; Pi-side `rkdeveloptool ld` also reported
`not found any devices!`.

Attempt 2 added diagnostic cmdline options:
`module_blacklist=panthor ignore_loglevel initcall_debug`.

```text
snapshot/kernel-pmthor-blacklist-extlinux.img
sha256=622958c41c92395235cbd2a9aec5e0d6f23953a76652985b6046dc75837c1e86
```

Result: p3 SD write completed, board reset, but SSH again did not return. The
board was recovered with a kernel-only stock p3 flash:

```bash
OPENCCA_RPI_PASSWORD=root OPENCCA_RPI_SUDO_PASSWORD=root OPENCCA_RK_PASSWORD=root \
  ./scripts/firmware/flash-rk3588-via-pi.sh \
  --kernel-image snapshot/kernel-extlinux.img \
  --flash-kernel --wait-rk
```

After recovery, the board returned to:

```text
opencca-rock5b-rk3588
Linux opencca-rock5b-rk3588 6.12.0-opencca-wip #wip SMP PREEMPT Thu Jul 31 08:44:48 UTC 2025 aarch64
/dev/mmcblk1p4 / ext4 root
no /dev/pmthor
panthor fb000000.gpu: [drm] CSF FW v1.1.0
```

The clean OpenCCA rootfs also lacks the GPU test workspace and build tools:
`/root/GPU-SFTP` is absent, `rsync`, `gcc`, `cc`, and `pkg-config` are missing,
and EGL/GLES headers such as `/usr/include/EGL/egl.h` are not installed. A
fresh 32 MiB comparison should install or stage those prerequisites only after
the pmthor host kernel reaches SSH and exposes `/dev/pmthor`.

## Result Table

No valid 32 MiB comparison numbers have been produced after the layout change
yet.

| Mode | 32MiB result |
| --- | --- |
| Shared VM GPU | Not measured. Blocked by pmthor host-kernel boot failure. |
| Passthrough VM GPU | Not measured. Blocked by missing `/dev/pmthor`. |
| Host direct GPU | Not measured in the final set; rootfs test prerequisites are absent after recovery. |

## Remaining Work

1. Diagnose why the local pmthor host kernel does not return SSH when booted
   from the extlinux p3 kernel slot. Serial capture or a kernel/modules/initrd
   rebuild with matching pmthor dependencies is needed.
2. Keep using the stock `snapshot/kernel-extlinux.img` as the SD p3 recovery
   path while iterating.
3. After `/dev/pmthor` is present, deploy or install the missing GPU test
   prerequisites on the fresh rootfs.
4. Run one 32 MiB set with the formal `--exclude-cpu-prepare`口径:
   shared VM GPU, passthrough VM GPU, and Host direct GPU.
5. Parse the logs and append the final comparison table and analysis.
