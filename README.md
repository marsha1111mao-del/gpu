# GPU Workspace

This repository is a superproject for the local GPU virtualization workspace.
It tracks the top-level orchestration files and records the exact commits of
the component repositories used together.

## Submodules

- `docs`
- `GPU-SFTP`
- `Linux-Host-GPU`
- `Linux-Guest-GPU`
- `firecracker/Firecracker-CCA-MZH`
- `firecracker/firecracker-deps`
- `firecracker/vmshm-broker`

Clone the workspace and first-level component repositories with:

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
