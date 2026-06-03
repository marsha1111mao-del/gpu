# Codex Context - vmshm/panthor proxy work

Date: 2026-05-28
Root workspace: `/home/mzh/gpu`

## Current Goal

This workspace is implementing and testing a Firecracker vmshm-based GPU proxy path:

```text
client VM userspace /dev/panthor ioctl
  -> panthor-client DRM frontend
  -> client_vmshm_comm
  -> shared-memory ring + ioeventfd/irqfd notify
  -> vmshm-broker eventfd relay
  -> proxy_vmshm_comm
  -> panthor-proxy
  -> real panthor driver on proxy VM
```

The currently validated ioctl is:

```text
DRM_PANTHOR_DEV_QUERY
```

It is tested by a boot-time panthor-client selftest that logs GPU_INFO and CSIF_INFO.

## Main Repositories And Folders

- Linux guest kernel:
  `/home/mzh/gpu/Linux-Guest-GPU`
- Firecracker and broker:
  `/home/mzh/gpu/firecracker`
- Firecracker fork:
  `/home/mzh/gpu/firecracker/Firecracker-CCA-MZH`
- vmshm broker:
  `/home/mzh/gpu/firecracker/vmshm-broker`
- SFTP sync payload:
  `/home/mzh/gpu/GPU-SFTP`
- SFTP binaries/configs:
  `/home/mzh/gpu/GPU-SFTP/firecracker-bins`
- Context backups:
  `/home/mzh/gpu/docs/codex-context`

## Implemented Linux Guest Pieces

Important paths:

- `drivers/char/client_vmshm_comm/`
- `drivers/char/proxy_vmshm_comm/`
- `drivers/char/client_vmshm_manager/`
- `drivers/char/proxy_vmshm_manager/`
- `drivers/gpu/drm/panthor-client/`
- `drivers/gpu/drm/panthor-proxy/`
- `include/linux/vmshm_comm.h`
- `include/linux/vmshm_manager.h`
- `include/linux/panthor_vmshm.h`
- `include/linux/client_vmshm.h`
- `include/linux/proxy_vmshm.h`

Current design:

- `client_vmshm_comm` and `proxy_vmshm_comm` use shared-memory rings.
- Notification path is now ioeventfd/irqfd based:

```text
write ring -> write doorbell MMIO -> KVM ioeventfd -> broker eventfd relay
  -> peer irqfd -> guest IRQ -> workqueue drains ring
```

- Polling fallback exists when DT notify resources are absent or setup fails.
- `client_comm_vmshm_call()` uses a completion-based RPC waiter path instead of polling the response queue.
- Proxy dispatch keeps handler registration by request type, but IRQ work now drains requests.
- `panthor-client` registers a DRM frontend and `/dev/panthor`.
- `panthor-client` currently selftests `DRM_PANTHOR_DEV_QUERY` at boot.
- `panthor-proxy` accepts vmshm requests and calls the real panthor-side functions to return query results.

## Firecracker/Broker Notify Design

Each vmshm comm entry can have:

```json
"notify": {
  "doorbell_addr": "0x2f000000",
  "doorbell_size": "0x1000",
  "irq": 80
}
```

Firecracker responsibilities:

- Parse optional vmshm notify config.
- Create `kick_eventfd` and `irq_eventfd`.
- Register KVM ioeventfd for guest doorbell writes.
- Register KVM irqfd for guest IRQ injection.
- Send notify fds to broker over the vmshm socket using SCM_RIGHTS.
- Expose FDT properties:
  - `interrupts`
  - `vmshm-doorbell-reg`

Broker responsibilities:

- Manage memfd vmshm domains.
- Receive notify fds from Firecracker participants.
- Relay eventfds only:

```text
client kick_eventfd readable -> read counter -> write proxy irq_eventfd once
proxy kick_eventfd readable -> read counter -> write client irq_eventfd once
```

Broker does not parse shared-memory ring contents.

## SFTP Config Files

These live only under SFTP, not in the Linux kernel repo:

- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/broker-config.toml`
- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/client-vm-config.json`
- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/proxy-vm-config.json`

Config generator:

- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/scripts/shared/vmshm-1client/install-vmshm-irq-configs.sh`

Current notify addresses:

- client comm:
  - doorbell: `0x2f000000`
  - irq: `80`
  - compatible: `client_comm_vmshm`
- proxy comm:
  - doorbell: `0x2f100000`
  - irq: `81`
  - compatible: `proxy_comm_vmshm`

Current shared windows:

- object window:
  - `vmshm-object`
  - 64 MiB
  - guest addr `0x20000000`
- comm window:
  - `vmshm-comm`
  - 32 MiB
  - guest addr `0x24000000`

## Build Scripts

Linux kernel build script:

- `/home/mzh/gpu/Linux-Guest-GPU/build-arm64-vmshm-kernels.sh`

It builds two arm64 kernels:

- client kernel image installed to:
  `/home/mzh/gpu/GPU-SFTP/firecracker-bins/kernels/shared/client/Image`
- proxy kernel image installed to:
  `/home/mzh/gpu/GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image`

Firecracker/broker build scripts:

- Firecracker-only:
  `/home/mzh/gpu/firecracker/Firecracker-CCA-MZH/sftp-build.sh`
- Broker-only:
  `/home/mzh/gpu/firecracker/vmshm-broker/sftp-build.sh`
- Top-level Firecracker+broker build and SFTP install:
  `/home/mzh/gpu/firecracker/sftp-build.sh`

Top-level installs:

- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/firecracker`
- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/vmshm-broker`
- `/home/mzh/gpu/GPU-SFTP/firecracker-bins/vmshm-client-test`

## E2E Automation Script

Added:

- `/home/mzh/gpu/scripts/run-vmshm-e2e.sh`

Default full run:

```bash
cd /home/mzh/gpu
./scripts/run-vmshm-e2e.sh
```

It performs:

1. Build client/proxy kernels.
2. Build Firecracker and vmshm-broker.
3. Regenerate SFTP vmshm irq configs.
4. Rsync `GPU-SFTP` to remote host.
5. SSH to remote and start broker, proxy VM, client VM.
6. Save logs under `GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>/`.
7. Generate `result`.
8. Rsync logs back to local host.

Fast rerun without rebuilding:

```bash
cd /home/mzh/gpu
./scripts/run-vmshm-e2e.sh --skip-build
```

Remote-only rerun after no local changes:

```bash
cd /home/mzh/gpu
./scripts/run-vmshm-e2e.sh --skip-build --skip-sync
```

Fixed run ID:

```bash
cd /home/mzh/gpu
./scripts/run-vmshm-e2e.sh --skip-build --run-id my-test-001
```

Useful options:

- `--skip-kernel-build`
- `--skip-firecracker-build`
- `--skip-build`
- `--skip-sync`
- `--skip-remote-run`
- `--skip-fetch-logs`
- `--sync-rootfs`
- `--run-id ID`

Remote defaults:

- host: `192.168.137.10`
- user: `root`
- password: `root`
- remote root: `/root/GPU-SFTP`
- remote bins: `/root/GPU-SFTP/firecracker-bins`

The password is not written permanently by the script; it is passed to a temporary `SSH_ASKPASS` helper.

Important automation detail:

- The client VM is started only after proxy log contains:

```text
panthor-proxy: vmshm handler registered
```

This avoids a race where client DEV_QUERY times out before the proxy handler is registered.

## Remote Manual Run Procedure

Remote host:

```text
HostName 192.168.137.10
User root
Password root
```

Remote directory:

```bash
cd /root/GPU-SFTP/firecracker-bins
```

Manual startup order:

```bash
./broker-run.sh
./vm-proxy-test.sh
./vm-client-test.sh
```

Recommended log paths:

```text
/root/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>/broker.log
/root/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>/proxy.log
/root/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>/client.log
/root/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>/result
```

## Last Verified Passing Run

Last automated passing run:

- Run ID: `auto-test-20260528-201927`
- Historical log files for this old run have been cleaned from the old
  `firecracker-bins/run-logs` location; keep the excerpts below as the
  durable evidence.

Important result excerpts:

```text
vmshm notify relay started domain="vmshm-comm"
proxy_comm_vmshm: selftest passed
panthor-proxy: vmshm handler registered
client_comm_vmshm 24000000.client_comm_vmshm: irq notify enabled
panthor-client: DEV_QUERY GPU_INFO size=104 gpu_id=0xa8670005
panthor-client: DEV_QUERY CSIF_INFO size=24 csg_slots=8 cs_slots=8
panthor-client: DEV_QUERY selftest passed
panthor-client: registered DRM frontend and /dev/panthor
RESULT: PASS
```

Current full logs are stored under:

```text
/home/mzh/gpu/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>/
```

Previous manual passing run:

- Run ID: `20260528-200915`
- Historical log files for this old run have also been cleaned from the old
  location.

## Known Pitfall

One automated trial failed before the wait condition was fixed:

- Run ID: `auto-test-20260528-201747`
- Failure:

```text
panthor-client: DEV_QUERY selftest failed (-110)
```

Cause:

- Client VM was started after `proxy_comm_vmshm: selftest passed`, but before:

```text
panthor-proxy: vmshm handler registered
```

Fix:

- `scripts/run-vmshm-e2e.sh` now waits for `panthor-proxy: vmshm handler registered`.

## Kernel Config Intent

Client VM kernel enables:

- `CONFIG_DRM=y`
- `CONFIG_DRM_PANTHOR_CLIENT=y`
- `CONFIG_CLIENT_VMSHM_COMM=y`
- `CONFIG_CLIENT_VMSHM_MANAGER=y`
- `CONFIG_DRM_PANTHOR_CLIENT_DEV_QUERY_SELFTEST=y`

Client VM kernel disables:

- real `CONFIG_DRM_PANTHOR`
- `CONFIG_DRM_PANTHOR_PROXY`
- proxy manager/comm

Proxy VM kernel enables:

- `CONFIG_DRM=y`
- `CONFIG_DRM_PANTHOR=y`
- `CONFIG_DRM_PANTHOR_PROXY=y`
- `CONFIG_PROXY_VMSHM_MANAGER=y`
- `CONFIG_PROXY_VMSHM_COMM=y`

Proxy VM kernel disables:

- `CONFIG_DRM_PANTHOR_CLIENT`
- client manager/comm

The old hello-world selftest configs were removed from the build fragments after that test passed.

## Notes For Future Codex Sessions

- Do not store `broker-config.toml`, `client-vm-config.json`, or `proxy-vm-config.json` in the Linux kernel repo. They belong under SFTP only.
- Do not merge Firecracker-only and broker-only build responsibilities; keep subproject scripts narrow.
- Use `/home/mzh/gpu/firecracker/sftp-build.sh` as the top-level Firecracker+broker build/install wrapper.
- Use `/home/mzh/gpu/scripts/run-vmshm-e2e.sh` for full regression or fast reruns.
- Before starting a new remote run, it is normal to kill existing remote `firecracker` and `vmshm-broker` processes with exact-name `pkill -x`; avoid broad `pkill -f` commands.
- The guest Linux IRQ number may show as `irq=14` even though Firecracker/broker config uses GSI `80` or `81`; this is expected after guest IRQ translation.
