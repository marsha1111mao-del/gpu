# From-Zero GPU Test Reproduction

This runbook describes how to reproduce the current GPU workspace on a new
control machine and use it to drive the existing remote GPU host tests.

The two target workflows are:

- GPU sharing virtualization smoke test:
  `OPEN_SESSION -> DEV_QUERY GPU_INFO/CSIF_INFO -> VM_CREATE -> VM_DESTROY -> CLOSE_SESSION`.
- GPU passthrough host-vs-VM GLES compute performance test.

The commands below assume the current lab defaults:

```text
local workspace:  /home/mzh/gpu
remote GPU host:  root@192.168.137.10
remote password:  root
remote runtime:   /root/GPU-SFTP
```

If the workspace is cloned somewhere else, most scripts still work because they
derive paths from their own location. The Codex skill files and some historical
docs still name `/home/mzh/gpu`; use the actual checkout path when running
commands manually.

## What "From Zero" Means

This document covers a new control machine plus a reachable remote GPU host.
It does not install the remote host operating system, bootloader, GPU hardware,
KVM support, or base network access.

Expected starting state:

- The control machine can reach `192.168.137.10` over SSH as `root`.
- The remote host can be rebooted during host-kernel setup.
- The remote host is the GPU test machine with the RK/Mali GPU exposed at the
  expected platform device path.
- The remote host has enough disk space for `/root/GPU-SFTP`, rootfs images,
  logs, and kernel payloads.
- The remote host boot path accepts `/boot/vmlinuz-6.12.0-opencca-wip`, which is
  the default `REMOTE_BOOT_IMAGE` used by the deploy script.

The repository provides:

- Source repositories as submodules.
- Runtime layout, configs, launch scripts, and docs under `GPU-SFTP/`.
- Build, deploy, run, and artifact helper scripts under `scripts/`.
- Pinned rootfs images as GitHub Release assets, restored by manifest and
  checksum.

## 1. Install Local Prerequisites

Install the ordinary shell, Git, SSH, rsync, kernel-build, and cross-build tools
on the new control machine.

Example Debian/Ubuntu package set:

```bash
sudo apt-get update
sudo apt-get install -y \
  git curl python3 rsync openssh-client \
  make gcc g++ bc bison flex libssl-dev libelf-dev dwarves pkg-config \
  gcc-aarch64-linux-gnu g++-aarch64-linux-gnu
```

Install Rust/Cargo and add the Firecracker/vmshm target:

```bash
rustup target add aarch64-unknown-linux-musl
```

The Firecracker runtime build also needs an ARM64 musl linker named
`aarch64-linux-musl-gcc` by default. If the linker is installed at a different
path, pass it explicitly:

```bash
LINKER=/path/to/aarch64-linux-musl-gcc ./scripts/build/build-firecracker-runtime.sh
```

Useful local commands that should exist before starting:

```bash
command -v git
command -v curl
command -v python3
command -v rsync
command -v ssh
command -v setsid
command -v aarch64-linux-gnu-gcc
command -v cargo
```

## 2. Clone The Workspace

Clone the superproject and initialize the first-level component repositories:

```bash
cd /home/mzh
git clone https://github.com/marsha1111mao-del/gpu.git
cd /home/mzh/gpu
git submodule update --init
```

Expected first-level submodules:

```text
Linux-Host-GPU
Linux-Guest-GPU
firecracker/Firecracker-CCA-MZH
firecracker/firecracker-deps
firecracker/vmshm-broker
```

Do not use generated runtime binaries from Git history. They are intentionally
ignored and rebuilt locally.

## 3. Restore Pinned Rootfs Images

Restore both rootfs images from the `rootfs-20260603` GitHub Release assets:

```bash
cd /home/mzh/gpu
./scripts/artifacts/fetch-rootfs.sh
```

The script reads `GPU-SFTP/rootfs-manifest.json`, downloads the images to
`GPU-SFTP/firecracker-bins/rootfs/`, verifies size and SHA-256, and leaves
already-valid files untouched.

Expected local files:

```text
GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2
GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4
```

Expected checksums:

```text
ccfe04443e5a9dd16a2dd1111399d9473b140f53a0545e8d7f502fd84c22d1f2  rootfs.ext2
3e491917386cec88ed4eba1d59036c8ba4a94ea8547444c9da4c48e1a22c5174  rootfs-panfrost.ext4
```

Manual verification:

```bash
sha256sum \
  GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2 \
  GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4
```

Force a redownload only when the local files are corrupted or intentionally
being refreshed:

```bash
./scripts/artifacts/fetch-rootfs.sh --force
```

## 4. Remote Runtime Update Policy

Do not delete `/root/GPU-SFTP` on the remote server. Treat it as the persistent
runtime artifact store for base rootfs images, generated binaries, kernels, DTB
dumps, and historical logs.

The remote host state normally changes slowly, and the workspace scripts are
written to update it in place:

- They `rsync` the tracked `GPU-SFTP/` layout to `/root/GPU-SFTP/`.
- They exclude logs by default so historical run data is preserved.
- They exclude rootfs images by default unless `--sync-rootfs` is passed.
- They call `scripts/lib/gpu_sftp_layout.sh` to migrate old scattered remote
  files into the current semantic layout.

For from-zero reproduction, "zero" means a new local control checkout and a
known remote GPU host. It does not mean wiping the remote runtime tree. Let the
build/deploy/run scripts update the existing remote directory.

## 5. Build Shared-GPU Runtime Artifacts

The one-client shared-GPU script can build everything it needs. For a from-zero
run, do not use `--skip-build`.

The full command in step 6 will build:

```text
GPU-SFTP/firecracker-bins/bin/firecracker
GPU-SFTP/firecracker-bins/bin/vmshm-broker
GPU-SFTP/firecracker-bins/bin/vmshm-client-test
GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

The build outputs are intentionally ignored by Git and reused by later runs.

If you want to build the pieces manually before running:

```bash
cd /home/mzh/gpu
./scripts/build/build-guest-vmshm-kernels.sh
./scripts/build/build-firecracker-runtime.sh
./scripts/build/build-panthor-ioctl-smoke.sh
```

## 6. Run The Shared-GPU VM_CREATE Smoke Test

Use the full build path for the first run from a new machine or empty remote
runtime tree:

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-1client-vm-create-fromzero-$(date +%Y%m%d-%H%M%S)
./scripts/run/run-vmshm-e2e.sh \
  --sync-rootfs \
  --vm-create-smoke \
  --run-id "${RUN_ID}"
```

Important details:

- `--sync-rootfs` sends `rootfs.ext2` to the remote host. It may also send other
  files under `firecracker-bins/rootfs/`; use it for first setup.
- `--vm-create-smoke` enables the Panthor IOCTL payload that checks the current
  virtualized surface.
- The script syncs `GPU-SFTP/` to `/root/GPU-SFTP/` and runs the remote layout
  migration helper.
- The script starts one broker, one proxy VM, and one client VM.

Expected remote runtime paths:

```text
/root/GPU-SFTP/firecracker-bins/bin/firecracker
/root/GPU-SFTP/firecracker-bins/bin/vmshm-broker
/root/GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke
/root/GPU-SFTP/firecracker-bins/kernels/shared/client/Image
/root/GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
/root/GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2
```

Expected local result file:

```text
GPU-SFTP/log/shared/vmshm-1client/${RUN_ID}/result
```

A successful VM_CREATE smoke result should contain:

```text
RESULT: PASS
PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS
PANTHOR_VM_CREATE_SMOKE=PASS
```

Useful logs when debugging:

```text
GPU-SFTP/log/shared/vmshm-1client/${RUN_ID}/broker.log
GPU-SFTP/log/shared/vmshm-1client/${RUN_ID}/proxy.log
GPU-SFTP/log/shared/vmshm-1client/${RUN_ID}/client.log
GPU-SFTP/log/shared/vmshm-1client/${RUN_ID}/ioctl-smoke-rootfs.log
```

## 7. Build Passthrough Runtime Artifacts

The passthrough performance script expects the runtime artifacts to already be
present on the remote host. Build the local Firecracker runtime and passthrough
guest kernel first:

```bash
cd /home/mzh/gpu
./scripts/build/build-firecracker-runtime.sh
./scripts/build/build-guest-passthrough-kernel.sh
```

Expected local files:

```text
GPU-SFTP/firecracker-bins/bin/firecracker
GPU-SFTP/firecracker-bins/kernels/passthrough/Image
GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2
GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4
```

`rootfs.ext2` is used by the lightweight passthrough probe config.
`rootfs-panfrost.ext4` is used by the host-vs-VM GLES performance config.

## 8. Deploy Host Kernel And Sync Passthrough Runtime

The host deploy script builds the host kernel payload, syncs `GPU-SFTP/`, can
sync rootfs images, installs the host kernel under `/boot`, and reboots the
remote host.

For a first setup, run:

```bash
cd /home/mzh/gpu
./scripts/deploy/deploy-host-kernel-and-test.sh \
  --skip-firecracker-build \
  --sync-rootfs \
  --skip-tests \
  --run-id-prefix fromzero-host-setup
```

This command may take time and will reboot `192.168.137.10`.

Why these options are used:

- `--skip-firecracker-build`: Firecracker was built in step 7.
- `--sync-rootfs`: sends both rootfs images to the remote runtime tree.
- `--skip-tests`: performs setup only; the formal performance run happens in
  step 9.

Expected remote files after the reboot:

```text
/root/GPU-SFTP/firecracker-bins/bin/firecracker
/root/GPU-SFTP/firecracker-bins/kernels/passthrough/Image
/root/GPU-SFTP/firecracker-bins/rootfs/rootfs.ext2
/root/GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4
/root/GPU-SFTP/firecracker-bins/configs/passthrough/gpu-panfrost-vm-config.json
/root/GPU-SFTP/firecracker-bins/scripts/passthrough/run-gpu-panfrost-vm.sh
```

If the remote host already has the correct host kernel and you only need to sync
runtime artifacts, use a setup-only sync instead:

```bash
cd /home/mzh/gpu
./scripts/deploy/deploy-host-kernel-and-test.sh \
  --skip-host-build \
  --skip-firecracker-build \
  --skip-install-reboot \
  --sync-rootfs \
  --skip-tests \
  --run-id-prefix fromzero-runtime-sync
```

## 9. Run The Passthrough Host-vs-VM Performance Test

Run the formal host-vs-passthrough GLES compute sweep:

```bash
cd /home/mzh/gpu
RUN_ID=gpu-perf-fromzero-$(date +%Y%m%d-%H%M%S)
./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --install-remote-deps \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900 \
  --run-id "${RUN_ID}"
```

Important details:

- This script syncs `GPU-SFTP/` but intentionally excludes
  `firecracker-bins/rootfs/`. Step 8 must have already placed
  `rootfs-panfrost.ext4` on the remote host.
- The script builds `gles-compute-smoke` on the remote host and installs it
  under `/root/GPU-SFTP/firecracker-bins/bin/`.
- `--install-remote-deps` installs remote build dependencies with `apt-get`.
  Omit it on later runs if the dependencies are already installed.
- `--host-rootfs-userspace` runs the host-direct workload inside the VM rootfs
  userspace so host and VM use the same Mesa/Panfrost userspace.

Expected local result file:

```text
GPU-SFTP/log/passthrough/perf/${RUN_ID}/result
```

A successful result should contain:

```text
RESULT: PASS
Formal Host/VM performance ratio table
```

Useful logs when debugging:

```text
GPU-SFTP/log/passthrough/perf/${RUN_ID}/remote-steps.log
GPU-SFTP/log/passthrough/perf/${RUN_ID}/preflight.txt
GPU-SFTP/log/passthrough/perf/${RUN_ID}/vm-count*.log
GPU-SFTP/log/passthrough/perf/${RUN_ID}/host-count*.log
GPU-SFTP/log/passthrough/perf/${RUN_ID}/result
```

## 10. Optional Lightweight Passthrough Probe

The deploy script can also run a lightweight single-VM passthrough probe using
`rootfs.ext2` and `gpu-passthrough-vm-config.json`.

Run it after the host kernel and runtime artifacts are synced:

```bash
cd /home/mzh/gpu
./scripts/deploy/deploy-host-kernel-and-test.sh \
  --skip-host-build \
  --skip-firecracker-build \
  --skip-install-reboot \
  --runs 1 \
  --vm-timeout 35 \
  --run-id-prefix passthrough-probe-fromzero
```

Expected local logs:

```text
GPU-SFTP/log/passthrough/probe/<generated-run-id>/result
```

## 11. Later Fast Reruns

After one successful from-zero setup, avoid rebuilding everything unless a
relevant source tree changed.

Shared VM_CREATE retest when artifacts are already present:

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-1client-vm-create-rerun-$(date +%Y%m%d-%H%M%S)
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --vm-create-smoke \
  --run-id "${RUN_ID}"
```

Passthrough performance retest when remote dependencies and rootfs are already
present:

```bash
cd /home/mzh/gpu
RUN_ID=gpu-perf-rerun-$(date +%Y%m%d-%H%M%S)
./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900 \
  --run-id "${RUN_ID}"
```

Rebuild only the affected layer:

```text
Linux-Guest-GPU shared client/proxy code:
  ./scripts/build/build-guest-vmshm-kernels.sh

Linux-Guest-GPU passthrough guest kernel code:
  ./scripts/build/build-guest-passthrough-kernel.sh

Firecracker or vmshm-broker code:
  ./scripts/build/build-firecracker-runtime.sh

Panthor IOCTL smoke source:
  ./scripts/build/build-panthor-ioctl-smoke.sh

Host kernel code:
  ./scripts/deploy/deploy-host-kernel-and-test.sh --skip-firecracker-build --skip-tests
```

## 12. Common Failure Points

Missing local rootfs:

```text
Run ./scripts/artifacts/fetch-rootfs.sh and verify SHA-256.
```

Missing remote `rootfs.ext2` during shared or probe tests:

```text
Rerun the setup command with --sync-rootfs.
```

Missing remote `rootfs-panfrost.ext4` during passthrough performance:

```text
Run step 8 with --sync-rootfs. The performance script itself excludes rootfs
from its normal rsync.
```

Missing `aarch64-linux-musl-gcc`:

```text
Install/provide an ARM64 musl cross linker or pass LINKER=/path/to/linker to
scripts/build/build-firecracker-runtime.sh.
```

Missing remote GLES build dependencies:

```text
Use --install-remote-deps on run-host-vs-passthrough-gles-perf.sh.
```

Remote SSH does not return after host-kernel deploy:

```text
Check the remote serial console or bootloader. The deploy script replaces the
configured REMOTE_BOOT_IMAGE and reboots the host.
```

Logs do not show `RESULT: PASS`:

```text
Inspect the local log directory first. Do not infer success from script exit
code alone.
```

## 13. Artifact And Git Hygiene

Generated runtime files remain ignored by Git:

```text
GPU-SFTP/firecracker-bins/bin/*
GPU-SFTP/firecracker-bins/kernels/**/Image
GPU-SFTP/firecracker-bins/rootfs/*.ext2
GPU-SFTP/firecracker-bins/rootfs/*.ext4
GPU-SFTP/linux-host-kernel/Image
GPU-SFTP/log/**
```

Only source, configs, scripts, docs, manifest metadata, and `.gitkeep` directory
skeletons should be committed. Rootfs images are stored as GitHub Release
assets and restored through `scripts/artifacts/fetch-rootfs.sh`.
