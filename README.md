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
- `firecracker/config`
- `firecracker/sftp-build.sh`

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
