# OpenCCA SD Kernel Flash And GPU 32MiB Report

Date: 2026-06-11

Target board: ROCK 5B / RK3588 at `root@192.168.31.18`
Flash host: Raspberry Pi at `mzh@192.168.31.52`

## Summary

- The board is booting OpenCCA from SD card, not eMMC. The Rockchip storage ID
  used for kernel-slot flashing is `2=SD`.
- The SD card uses p3 as a 128 MiB ext4/extlinux `kernel` boot partition at LBA
  `0x8000`, and p4 as the `root` partition at LBA `0x48000`.
- The running kernel is the locally rebuilt `6.12.0-opencca-pmthor`; rootfs has
  the matching `/lib/modules/6.12.0-opencca-pmthor`, following
  `docs/kernel_flash_patches/README.md`'s compatibility rule.
- The final SD p3 image is
  `opencca/snapshot/kernel-pmthor-rootfs-matched-extlinux.img`,
  SHA256 `4dc22f56de99fddf9828d2e6c7155df292dc04003b769f893618d8703549e1a0`.
- The board defaults to the host `pmthor` driver and exposes `/dev/pmthor`.
  Host-direct Panfrost testing is still possible because the p3 cmdline no
  longer uses `module_blacklist=panthor,pmthor`; automatic Panthor binding is
  controlled by rootfs `modprobe.d` instead.
- Both 32 MiB GPU tests completed successfully:
  host vs passthrough GLES PASS, and 2-client shared GLES PASS.

## Current Boot Evidence

```text
Linux opencca-rock5b-rk3588 6.12.0-opencca-pmthor #1 SMP PREEMPT Thu Jun 11 23:04:28 CST 2026 aarch64
root=PARTLABEL=root rootwait isolcpus=1,2,3 maxcpus=2 nohlt cpuidle.off=1 rcupdate.rcu_cpu_st ignore_loglevel initcall_debug maxcpus=2
/dev/mmcblk1p4 / ext4 rw,relatime
mmcblk1p3 128M ext4 kernel
mmcblk1p4 29.6G ext4 root /
/sys/bus/platform/drivers/pmthor
/dev/pmthor present
```

The root partition was expanded online after the initial full SD image flash:

```text
before: p4 size 7779699 sectors, about 3.7G
after:  p4 size 29.6G, root filesystem about 30G
backup: /root/opencca-sd-sfdisk-before-20260611-151548.txt
```

## Kernel Build And Flash

The successful kernel build used a real kernel release string:

```text
kernelrelease: 6.12.0-opencca-pmthor
Image sha256: 5705b24385b19e36e80b8361ee39106c48b0ee4bdb4f8df0d504b1057450fc6b
pmthor_drv.ko sha256: ef16bd598cfb4c2c3f2600322eacf6189f9f1d1fffb5a9ece82df90668ef3ba1
panthor.ko sha256: f564165f7b115b400115310294a91d20c41abea84d6ee20294398f9d6acf9dfe
r8169.ko sha256: c604aa373c34777d6b3d096bc671f3e637d68a785aa137840bf356c1292def35
vermagic: 6.12.0-opencca-pmthor SMP preempt mod_unload aarch64
```

Modules were installed into the RK rootfs as stripped modules to keep the SD
root filesystem small enough:

```text
/lib/modules/6.12.0-opencca-pmthor
```

The rootfs boot defaults are:

```text
/etc/modprobe.d/opencca-gpu.conf:
blacklist panthor

/etc/modules-load.d/opencca-gpu.conf:
pmthor_drv
```

This keeps boot on `pmthor`, while allowing the test script to explicitly
unbind `pmthor`, `modprobe panthor`, run host-direct GLES, and restore `pmthor`.

The final initrd and p3 boot image were:

```text
opencca/snapshot/initrd.img-6.12.0-opencca-pmthor
sha256=aba43936324ff7693cfcebf8b5bf6b740ed6e90eca3f4557b1d24516236361d0

opencca/snapshot/kernel-pmthor-rootfs-matched-extlinux.img
sha256=4dc22f56de99fddf9828d2e6c7155df292dc04003b769f893618d8703549e1a0
size=134217728 bytes
```

The extlinux cmdline intentionally does not contain `module_blacklist`:

```text
append root=PARTLABEL=root rootwait isolcpus=1,2,3 maxcpus=2 nohlt cpuidle.off=1 rcupdate.rcu_cpu_st ignore_loglevel initcall_debug
```

Kernel-only SD flash command:

```bash
OPENCCA_RPI_PASSWORD=root OPENCCA_RPI_SUDO_PASSWORD=root OPENCCA_RK_PASSWORD=root \
  ./scripts/firmware/flash-rk3588-via-pi.sh \
  --kernel-image snapshot/kernel-pmthor-rootfs-matched-extlinux.img \
  --flash-kernel --wait-rk
```

The flash log showed:

```text
live RK kernel-slot preflight passed
selecting Rockchip storage ID 2
Flash Size: 30436 MB
writing kernel-pmthor-rootfs-matched-extlinux.img to kernel slot LBA 0x8000
kernel flash complete; board reset requested
```

## 32 MiB Test Method

Workload size: 32 MiB, `--count 8388608` uint32 elements.

Because the fresh OpenCCA rootfs could not install build dependencies through
APT, the GLES smoke binary was reused from
`GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4`:

```text
GPU-SFTP/firecracker-bins/bin/gles-compute-smoke
sha256=611adf53dc574c15d053112d7bdb5b456abcd024a62215ea6c520795710c5ab3
```

This binary does not support `--exclude-cpu-prepare`, so these numbers include
the `cpu_prepare` phase. Correctness is still checked separately with
`COMPUTE_CHECK=PASS`.

APT note: `/etc/apt/sources.list.d/rk3588.sources` was disabled as
`rk3588.sources.disabled-opencca-20260611` because the Collabora source failed
signature validation under the 2026 SHA1 policy.

## 32 MiB Results

Host vs passthrough run:

```text
run: GPU-SFTP/log/passthrough/perf/gpu-perf-32m-opencca-pmthor-20260611-234401
result: PASS
renderer: Mali-G610 (Panfrost)
GL: OpenGL ES 3.1 Mesa 25.0.7-2
host avg iter_total: 25471.05 us
passthrough VM avg iter_total: 33016.80 us
host/vm ratio: 0.771
restored driver: pmthor
```

Shared 2-client run:

```text
run: GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-opencca-pmthor-20260611-234503
result: GLES_PASS
GLES remote build: 0
renderer: Mali-G610 (Panfrost)
GL: OpenGL ES 3.1 Mesa 25.0.7-2
client0 avg iter_total: 48595.90 us
client1 avg iter_total: 52102.55 us
shared average: 50349.23 us
```

Comparison table:

| Mode | Result | Avg iter_total | Ratio vs host |
| --- | --- | ---: | ---: |
| Host direct Panfrost | PASS | 25471.05 us | 1.000 |
| Passthrough VM Panfrost | PASS | 33016.80 us | 0.771 |
| Shared VM GPU client0 | PASS | 48595.90 us | 0.524 |
| Shared VM GPU client1 | PASS | 52102.55 us | 0.489 |
| Shared VM GPU average | PASS | 50349.23 us | 0.506 |

The host-vs-passthrough script also reported this formal phase-ratio row:

```text
| 32.00 MiB | 20 | 0.771 | 0.836 | 0.908 | 0.577 | 0.681 | 80.0/1.2/18.8/0.01 |
```

## Script Change

`scripts/run/run-vmshm-2client-e2e.sh` now supports
`--skip-gles-remote-build`. In GLES mode this reuses an existing executable
`${REMOTE_BINS}/bin/gles-compute-smoke` and records `GLES remote build: 0` in
the result. Default behavior is unchanged: without the option, the script still
builds the smoke binary on the remote host.

## Remaining Work

1. Rebuild the current GLES smoke binary against the target rootfs once APT or a
   matching sysroot is fixed, then rerun with `--exclude-cpu-prepare`.
2. Restore or replace the disabled Collabora APT source if package installation
   on the RK rootfs is needed again.
3. Keep using SD storage ID `2`; do not switch these scripts to eMMC ID `1`.
