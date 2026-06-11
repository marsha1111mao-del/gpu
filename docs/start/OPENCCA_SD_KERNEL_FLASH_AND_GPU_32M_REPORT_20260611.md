# OpenCCA SD Kernel Flash And GPU 32MiB Report

Date: 2026-06-11

Target board: ROCK 5B / RK3588 at `root@192.168.31.18`
Flash host: Raspberry Pi at `mzh@192.168.31.52`

## Summary

- The OpenCCA workspace now has an SD-only raw kernel slot workflow. It builds a
  fixed 128 MiB FIT `snapshot/kernel.img`, syncs it to the Raspberry Pi, and
  refuses to write it unless the SD GPT contains `PARTLABEL=kernel` at LBA
  `0x8000`.
- The current SD card on the target board was restored successfully by flashing
  the full OpenCCA rootfs image back to SD. The board is online again, booted
  from `/dev/mmcblk1p3`.
- The current SD image still uses the old layout where `root` starts at
  `0x8000`. Single-kernel flashing is therefore intentionally blocked until the
  SD card is initialized with a compatible raw-kernel-slot image.
- The 32 MiB GPU comparison could not produce valid shared/passthrough/host
  numbers. The board restored to the stock OpenCCA `panthor` kernel; no
  `/dev/pmthor` exists, and the attempted `pmthor` host kernel boot did not
  return over SSH.

## Implemented OpenCCA Changes

OpenCCA submodule:

- `scripts/image/build-raw-kernel-image.sh`
  Builds `snapshot/kernel.img` from a Linux `Image` and `rk3588-rock-5b.dtb`.
- `scripts/firmware/flash-raw-kernel-on-pi.sh`
  Pi-side SD raw kernel writer. It enters Maskrom, selects storage ID `2`, reads
  GPT, validates the kernel partition, writes LBA `0x8000`, releases Maskrom,
  and resets the board.
- `scripts/firmware/validate-gpt-slot.py`
  Validates that the GPT dump has a non-overlapping `kernel` partition at the
  expected LBA and size.
- `scripts/image/convert-opencca-image-to-raw-kernel-layout.py`
  Converts an old root-at-`0x8000` OpenCCA image into the raw-kernel-slot layout
  by moving root to `0x48000`.
- `scripts/firmware/configure-raw-kernel-slot-sources.sh`
  Optional local source patch helper for U-Boot and debian-image-recipes.
- `scripts/firmware/flash-rk3588-via-pi.sh`
  Adds `--build-kernel-image`, `--sync-kernel`, `--flash-kernel`, and
  `--kernel-image`.

Parent repo docs:

- `docs/start/RASPBERRY_PI_FLASH_RUNBOOK.md`
  Documents that this workflow flashes SD, not eMMC, and records the raw kernel
  slot preflight/refusal behavior.

## Verification

Kernel artifact build:

- `snapshot/kernel.img` was generated locally.
- Size: `134217728` bytes.
- SHA-256:
  `eaae4126a077a5bd00f87febec59263027c38de04fab1144d7fc699f895f041d`.
- The same hash was confirmed after syncing to the Raspberry Pi.

Script checks:

- `bash -n` passed for the modified shell scripts.
- `python3 -m py_compile` passed for the Python helpers.
- `--flash-kernel --dry-run` on the current board refused before entering
  Maskrom:

```text
OPENCCA_KERNEL_PREFLIGHT_INCOMPATIBLE=1
Expected PARTLABEL=kernel start=32768 sectors>=262144.
mmcblk1p1 label=loader1 start=64 sectors=7105
mmcblk1p2 label=loader2 start=16384 sectors=8192
mmcblk1p3 label=root start=32768 sectors=62301144
```

Board recovery after the failed `pmthor` kernel boot attempt:

```text
opencca-rock5b-rk3588
Linux opencca-rock5b-rk3588 6.12.0-opencca-wip #wip SMP PREEMPT Thu Jul 31 08:44:48 UTC 2025 aarch64
/dev/mmcblk1p3 / ext4
mmcblk1p1 loader1
mmcblk1p2 loader2
mmcblk1p3 root /
```

GPU driver state after recovery:

```text
/dev/dri/card0
/dev/dri/card1
/dev/dri/renderD128
panthor loaded
no /dev/pmthor
```

## GPU 32MiB Reproduction Attempt

Requested workload size: 32 MiB, represented by `--count 8388608` uint32
elements.

What was attempted:

- Baseline stock OpenCCA boot was confirmed from SD with `panthor`.
- Dependencies were installed once before the kernel experiment.
- A host `pmthor` kernel image from `GPU-SFTP/linux-host-kernel/Image` was
  deployed to `/boot/vmlinuz-6.12.0-opencca-wip`.
- After reboot, SSH did not return within the configured wait window. The
  Raspberry Pi had no serial device available for boot log capture, and the
  board was not visible in Maskrom. The board was recovered by flashing the full
  OpenCCA SD rootfs image again.
- After recovery, a low-risk host-only `panthor` 32 MiB smoke attempt was made.
  The clean rootfs no longer had `gcc/pkg-config`; dependency installation from
  Debian stalled before `gcc-14-aarch64-linux-gnu` downloaded, so no valid
  host-only measurement was produced.

Invalid data excluded from comparison:

- `GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-rk31-20260611-144824`
  is not a performance result. It failed before workload execution because the
  remote host had no compiler and `gles-compute-smoke` was missing.

Result table:

| Mode | 32MiB result |
| --- | --- |
| Shared VM GPU | Not measured. Requires booted `pmthor` host path. |
| Passthrough VM GPU | Not measured. Requires `/dev/pmthor`. |
| Host direct GPU | Not measured. Host-only retry was blocked by dependency install after full SD recovery. |

## Current Blockers

- The current SD card lacks a raw `kernel` GPT partition; `--flash-kernel` is
  correctly blocked to avoid overwriting rootfs.
- Shared and passthrough GPU tests require the custom host `pmthor` path. The
  tested host kernel image did not return over SSH when installed as the boot
  kernel.
- No serial console was available on the Raspberry Pi (`/dev/ttyUSB0` absent),
  so the failed `pmthor` boot could not be diagnosed safely.
- The stock OpenCCA command line includes `maxcpus=2`, so the old multi-core
  CPU-affinity assumptions in prior GPU logs are not valid for this boot.

## Next Safe Steps

1. Convert or rebuild the SD image with the raw-kernel-slot layout, then full
   flash that image once. After that, use `--flash-kernel` for kernel-only
   updates.
2. Attach serial logging before retrying the `pmthor` host kernel.
3. Rebuild/deploy the `pmthor` kernel together with any required modules or
   rootfs payload, then verify `/dev/pmthor` before running VM tests.
4. Re-run exactly one 32 MiB set only after `/dev/pmthor` is present:
   shared VM GPU, passthrough VM GPU, and host direct GPU.
