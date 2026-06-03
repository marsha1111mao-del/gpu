# GPU Workspace

This repository is the main workspace for the local GPU virtualization project.
It tracks the orchestration scripts, GPU-SFTP deploy layout, and project docs
directly, while recording the exact commits of the large component source
repositories used together.

## Directories Tracked Directly

- `docs`
- `GPU-SFTP`
- `scripts`
- `.vscode`

Codex skill guidance for GPU passthrough/shared virtualization testing is
versioned under `docs/skills/`. The live runtime copies remain under
`/home/mzh/.codex/skills/`.

Workspace-owned scripts are grouped by purpose:

- `scripts/build`: build and install artifacts produced from component repos.
- `scripts/deploy`: deploy host-side payloads and reboot/test remote hosts.
- `scripts/run`: run end-to-end or performance test workflows.
- `scripts/lib`: shared shell helpers used by workspace scripts.

## Submodules

- `Linux-Host-GPU`
- `Linux-Guest-GPU`
- `firecracker/Firecracker-CCA-MZH`
- `firecracker/firecracker-deps`
- `firecracker/vmshm-broker`

Clone the workspace and first-level component source repositories with:

```bash
git clone https://github.com/marsha1111mao-del/gpu.git
cd gpu
git submodule update --init
./scripts/artifacts/fetch-rootfs.sh
```

For an existing clone, initialize or refresh first-level submodules with:

```bash
git submodule update --init
```

When a component repository changes, commit and push that component first, then
commit the updated submodule pointer in this superproject.

Some component repositories may have their own nested submodule setup. Keep
those nested dependencies managed inside the component repository that owns
them.

## Runtime Artifacts

Large generated payloads stay out of Git history. Most binaries and kernels are
rebuilt from the tracked source repositories through `scripts/build/`; the two
Firecracker rootfs images are distributed as pinned GitHub Release assets:

```bash
./scripts/artifacts/fetch-rootfs.sh
```

The fetch script reads `GPU-SFTP/rootfs-manifest.json`, downloads
`rootfs.ext2` and `rootfs-panfrost.ext4` into
`GPU-SFTP/firecracker-bins/rootfs/`, verifies their sizes and SHA-256 hashes,
and leaves already-valid local copies untouched. See `GPU-SFTP/ARTIFACTS.md`
for the full rebuild/restore policy.
