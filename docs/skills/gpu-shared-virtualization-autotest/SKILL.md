---
name: gpu-shared-virtualization-autotest
description: Use when building, deploying, or testing the multi-VM GPU sharing virtualization path on the remote GPU host, including vmshm, Firecracker broker, proxy VM/client VM Panthor IOCTL forwarding, Panthor client/proxy drivers, one-proxy-one-client tests, explicit two-client experiments, handle/session namespace tests, shared-memory transport, and shared virtualization run-log reporting.
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
  -> real panthor driver in proxy VM
```

Default tests use one Proxy VM and one Client VM. Use two Client VMs only when the user explicitly asks for multi-client behavior such as namespace isolation, sharing, fairness, or scheduling.

Do not use this skill for single-VM passthrough host-vs-VM performance testing. Use `gpu-passthrough-autotest` for that path.

## Fixed Environment

Work from `/home/mzh/gpu` unless the user gives another checkout.

- Remote SSH target: `root@192.168.137.10`
- Remote password: `root`
- Local artifact root: `/home/mzh/gpu/GPU-SFTP`
- Remote artifact root: `/root/GPU-SFTP`
- Local runtime artifact tree: `/home/mzh/gpu/GPU-SFTP/firecracker-bins`
- Remote runtime artifact tree: `/root/GPU-SFTP/firecracker-bins`
- Local one-client logs: `/home/mzh/gpu/GPU-SFTP/log/shared/vmshm-1client`
- Remote one-client logs: `/root/GPU-SFTP/log/shared/vmshm-1client`
- Local two-client logs: `/home/mzh/gpu/GPU-SFTP/log/shared/vmshm-2client`
- Remote two-client logs: `/root/GPU-SFTP/log/shared/vmshm-2client`

## Documentation Sync Map

When shared GPU virtualization behavior changes, update the relevant docs from
this list. Do not mechanically edit every file; use the category that matches
the change.

- Current shared design, progress, scheduling decisions, and latest test
  conclusions: `/home/mzh/gpu/docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md`
- Panthor IOCTL forwarding/virtualization design and remaining IOCTL work:
  `/home/mzh/gpu/docs/shared/PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md`
- Shared driver/module architecture and client/proxy/vmshm relationships:
  `/home/mzh/gpu/docs/shared/GPU_VIRTUALIZATION_DRIVER_ANALYSIS.md`
- Artifact layout, rootfs injection flow, Firecracker config layout, and
  remote/local runtime paths: `/home/mzh/gpu/docs/shared/GPU_SFTP_ARTIFACT_LAYOUT.md`
- GLES smoke timing model, shared-vs-host-vs-passthrough comparisons, and
  performance interpretation: `/home/mzh/gpu/docs/shared/PANTHOR_GLES_COMPUTE_SMOKE_BASELINE_ANALYSIS.md`
- From-zero reproduction or ordinary workflow changes:
  `/home/mzh/gpu/docs/start/FROM_ZERO_REPRODUCTION.md`
- Project management/testing principles that affect how results are recorded:
  `/home/mzh/gpu/docs/start/PROJECT_MANAGEMENT_PRINCIPLES.md`
- Runtime skill and repo skill copy; keep both synchronized after workflow,
  script, rootfs, or test-procedure changes:
  `/home/mzh/.codex/skills/gpu-shared-virtualization-autotest/SKILL.md`
  and `/home/mzh/gpu/docs/skills/gpu-shared-virtualization-autotest/SKILL.md`
- Passthrough constraints that affect the Proxy VM, especially custom
  passthrough interrupt and memory-management behavior:
  `/home/mzh/gpu/docs/passthrough/GPU_PASSTHROUGH_IMPLEMENTATION_ANALYSIS.md`,
  `/home/mzh/gpu/docs/passthrough/GPU_PASSTHROUGH_EFFECTIVE_OPTIMIZATIONS.md`,
  and `/home/mzh/gpu/docs/passthrough/GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md`
- Historical context notes, only for broad design pivots that need a checkpoint:
  `/home/mzh/gpu/docs/codex-context/2026-05-28-vmshm-panthor-context.md` and
  `/home/mzh/gpu/docs/codex-context/2026-06-03-full-gpu-passthrough-shared-context.md`

Current semantic layout under `GPU-SFTP/firecracker-bins/`:

- `bin/`: `firecracker`, `vmshm-broker`, `vmshm-client-test`, `panthor_ioctl_smoke`, and other small runtime binaries.
- `configs/shared/vmshm-1client/`: one-proxy-one-client broker/proxy/client configs.
- `configs/shared/vmshm-2client/`: explicit two-client experiment configs.
- `kernels/shared/client/Image` and `kernels/shared/proxy/Image`: role-specific guest kernels.
- `rootfs/`: base rootfs images. Keep only `rootfs.ext2` for lightweight
  comm/IOCTL tests and `rootfs-panfrost.ext4` for GLES/Panfrost userspace.
  Test payloads are injected into those base images by loop-mounting them
  immediately before VM launch.
- `scripts/shared/vmshm-1client/` and `scripts/shared/vmshm-2client/`: semantic launch/config helper scripts.

Test source trees live under `GPU-SFTP/tests/`:

- `GPU-SFTP/tests/panthor-ioctl-smoke`
- `GPU-SFTP/tests/gpu-compute-smoke`
- `GPU-SFTP/tests/vmshm-test`

Generated/dumped Firecracker device trees live under
`GPU-SFTP/artifacts/dtb/`. Firecracker accepts optional
`machine-config.dump_fdt_path`; configs should write DTB dumps there, not at
the old top-level DTB dump path.

Prefer the repo scripts over ad hoc SSH. If manual SSH is needed:

```bash
ssh -p 22 -oBatchMode=no -oStrictHostKeyChecking=accept-new root@192.168.137.10 '<command>'
```

Use existing `setsid`/`SSH_ASKPASS` wrappers in scripts for noninteractive password auth.

## Build Selection

Rebuild only affected components. Treat the artifacts already installed under
`GPU-SFTP/firecracker-bins/` as the persistent artifact store for the next run,
not as disposable state. Before starting a test, classify what changed and preserve existing
outputs unless that change invalidates them.

- No relevant code/config changes since a known-good run: do not build. Use
  `scripts/run/run-vmshm-e2e.sh --skip-build` and reuse the existing local/remote
  `kernels/shared/client/Image`, `kernels/shared/proxy/Image`, `bin/firecracker`,
  `bin/vmshm-broker`, and `bin/panthor_ioctl_smoke`.
- `Linux-Guest-GPU/` Panthor client/proxy, vmshm comm/manager, Kconfig, UAPI,
  or kernel config changes: rebuild only the proxy/client role kernels with
  `scripts/build/build-guest-vmshm-kernels.sh`. It installs images to
  `GPU-SFTP/firecracker-bins/kernels/shared/client/Image` and
  `GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image`. Keep
  `Linux-Guest-GPU/out/vmshm-arm64/{client,proxy}` so the kernel build remains
  incremental; do not delete output directories unless explicitly requested or
  diagnosing a corrupted build.
- `firecracker/Firecracker-CCA-MZH/`, `firecracker/vmshm-broker/`, or vmshm
  broker protocol/userspace relay changes: rebuild only Firecracker/broker
  through `scripts/build/build-firecracker-runtime.sh`; it installs to `firecracker-bins/bin/`.
  Skip the kernel build.
- `GPU-SFTP/tests/panthor-ioctl-smoke/` changes: rebuild only the userspace
  smoke payload with `GPU-SFTP/tests/panthor-ioctl-smoke/build.sh`. Skip both
  kernel and Firecracker/broker builds.
- `GPU-SFTP/tests/gpu-compute-smoke/` changes for shared GLES performance:
  sync the source; the runners compile the current `gles-compute-smoke` on the
  remote host and inject the binary, `gpu-smoke.sh`, `init`, and
  `/root/gpu-smoke.env` into `rootfs-panfrost.ext4` before launch. Runtime
  smoke arguments such as `--count`, `--iterations`, and `--warmup` are passed
  through the guest kernel command line. Skip kernel and Firecracker/broker
  builds unless guest driver or vmshm runtime code also changed.
- `GPU-SFTP/firecracker-bins/configs/shared/...` or config installer changes:
  regenerate and sync configs only. Skip kernel and Firecracker/broker builds
  unless the config change depends on new Firecracker code, such as a new JSON
  field.
- Rootfs changes are not part of ordinary IOCTL/vmshm smoke testing. Sync
  rootfs images only when the user asks, when the selected test requires a new
  rootfs, or when remote preflight shows the rootfs is missing.
- A full build is reserved for first setup, missing/corrupted artifacts, broad
  build-system or Kconfig changes that invalidate both roles, or an explicit
  user request to refresh all artifacts.

SFTP vmshm configs live under
`GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/` and
`GPU-SFTP/firecracker-bins/configs/shared/vmshm-2client/`; do not store
`broker-config.toml` or VM config JSON in the Linux kernel repos.

## Sync Policy

Sync `/home/mzh/gpu/GPU-SFTP/` to `root@192.168.137.10:/root/GPU-SFTP/` after relevant builds. Exclude `log/` and old `firecracker-bins/run-logs/`; do not overwrite or fetch historical logs during artifact sync.

Default rsync exclusions:

```bash
rsync -av --info=stats2,name1 \
  --exclude='.vscode/' \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='log/' \
  --exclude='firecracker-bins/run-logs/' \
  --exclude='firecracker-bins/rootfs/' \
  --exclude='linux-host-kernel/' \
  /home/mzh/gpu/GPU-SFTP/ \
  root@192.168.137.10:/root/GPU-SFTP/
```

Sync rootfs images only when the user asks, when a script explicitly requires it, or when remote preflight shows the needed base image is missing.
`--gles-compute-smoke` does not by itself require `--sync-rootfs`: normal GLES
runs reuse the remote `rootfs-panfrost.ext4` base image and inject the current
payload into it before launch. Use `--sync-rootfs` only to seed or reseed the
base `rootfs.ext2` and `rootfs-panfrost.ext4` images on the remote host.
The repo sync scripts call `scripts/lib/gpu_sftp_layout.sh` after rsync to
migrate old remote top-level binaries, `config/`, `config-2client/`,
`kernel-client/`, `kernel-proxy/`, old test source directories, and top-level
DTB files into the semantic layout. Prefer those scripts to ad hoc `rsync`.

## Default One-Client Test

Use `/home/mzh/gpu/scripts/run/run-vmshm-e2e.sh` for the default one Proxy VM plus one Client VM GPU sharing path. It validates the vmshm transport and current Panthor DEV_QUERY-style IOCTL forwarding.

After a known-good build, start from artifact reuse. The default retest of the
current `OPEN_SESSION -> DEV_QUERY -> VM_CREATE -> VM_DESTROY -> CLOSE_SESSION`
surface should be a skip-build run unless local context shows that one of the
components above changed. If something did change, rebuild only that component,
then run the smoke test with the complementary skip flags.

Useful commands:

```bash
cd /home/mzh/gpu
./scripts/run/run-vmshm-e2e.sh --skip-build --run-id vmshm-1client-devquery-$(date +%Y%m%d-%H%M%S)
./scripts/run/run-vmshm-e2e.sh --skip-build --vm-create-smoke --run-id vmshm-1client-vm-create-$(date +%Y%m%d-%H%M%S)
./scripts/run/run-vmshm-e2e.sh --skip-kernel-build --skip-firecracker-build --run-id vmshm-1client-devquery-$(date +%Y%m%d-%H%M%S)
```

Use the full build form only when intentionally refreshing all artifacts, or
when the artifact store is missing/corrupted:

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-1client-devquery-fullbuild-$(date +%Y%m%d-%H%M%S) ./scripts/run/run-vmshm-e2e.sh
```

Common options:

- `--skip-kernel-build`
- `--skip-firecracker-build`
- `--skip-build`
- `--skip-sync`
- `--skip-remote-run`
- `--skip-fetch-logs`
- `--sync-rootfs`
- `--ioctl-smoke`
- `--vm-create-smoke`
- `--run-id ID`

## Shared GLES Performance Smoke

Use `--gles-compute-smoke` for the shared client/proxy GLES compute path. For
performance comparisons, exclude the CPU-side `input[]` fill from the primary
metric so shared, passthrough, and host use the same formal timing definition.
The smoke still prints `cpu_prepare`, but `PERF_ITER_US` / `iter_total` and the
formal `metadata` group exclude it; `metadata=buffer_upload`.

Current one-client commands:

```bash
cd /home/mzh/gpu
./scripts/run/run-vmshm-e2e.sh --skip-build --skip-config-install \
  --gles-compute-smoke \
  --gles-smoke-args "--count 1048576 --iterations 100 --warmup 5 --perf --exclude-cpu-prepare" \
  --run-id vmshm-1client-perf-4m-$(date +%Y%m%d-%H%M%S)

./scripts/run/run-vmshm-e2e.sh --skip-build --skip-config-install \
  --gles-compute-smoke \
  --gles-smoke-args "--count 4194304 --iterations 100 --warmup 5 --perf --exclude-cpu-prepare" \
  --run-id vmshm-1client-perf-16m-$(date +%Y%m%d-%H%M%S)

./scripts/run/run-vmshm-e2e.sh --skip-build --skip-config-install \
  --gles-compute-smoke \
  --gles-smoke-args "--count 16777216 --iterations 20 --warmup 5 --perf --exclude-cpu-prepare" \
  --run-id vmshm-1client-perf-64m-$(date +%Y%m%d-%H%M%S)
```

Shared runners use only the base images and inject the current payload before
VM launch:

- `rootfs.ext2` is the lightweight base image for comm/query and one-client
  IOCTL semantic smokes. For IOCTL smokes the runner loop-mounts it read-write,
  installs `/panthor_ioctl_smoke` and `/panthor_ioctl_smoke_init`, unmounts it,
  then boots the client from that image.
- `rootfs-panfrost.ext4` is the GLES/Panfrost userspace base image. For GLES
  smokes the runner builds `gles-compute-smoke` on the remote host, loop-mounts
  this image read-write, installs `/root/gles-compute-smoke`,
  `/root/gpu-smoke.sh`, `/root/gpu-smoke.env`, and `/init`, unmounts it, then
  boots one or both clients from that image read-only.

Runtime choices stay outside the rootfs image. IOCTL semantic mode is passed as
`panthor_ioctl_smoke_mode=<mode>`. GLES workload and timing arguments are
passed as `gpu_smoke_args_tokens=--count:<N>:...`; the token transport supports
whitespace-free tokens without colons, quotes, or backslashes.

Before reporting PASS, inspect the rootfs-prep log for the injection markers:

- IOCTL: `rootfs_payload_inject_start payload=panthor-ioctl-smoke` and
  `rootfs_payload_inject_done payload=panthor-ioctl-smoke` in
  `ioctl-smoke-rootfs.log`.
- GLES: `rootfs_payload_inject_start payload=gles-compute` and
  `rootfs_payload_inject_done payload=gles-compute` in
  `gles-compute-rootfs.log`.

The runners prune rootfs artifacts before injection with a base-image
allowlist: only `rootfs.ext2`, `rootfs-panfrost.ext4`, `.gitkeep`, `mounts/`,
and `work/` belong in `firecracker-bins/rootfs/`. Do not add a rootfs selection
layer or per-test image path; all smoke payload changes go through loop-mount
injection.

Before reporting PASS, fetch and inspect local logs for
`PERF_CPU_PREPARE_EXCLUDED=1`, `GPU_SMOKE_RESULT=PASS`,
`COMPUTE_CHECK=PASS`, a Mali/Panfrost renderer, and absence of software
renderer, mismatch, GPU fault, job timeout, panic, or Oops markers.

## Two-Client Experiments

Use `/home/mzh/gpu/scripts/run/run-vmshm-2client-e2e.sh` only for explicit two-client or namespace-isolation coverage. It uses `firecracker-bins/configs/shared/vmshm-2client` and should not be the default.

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-2client-devquery-$(date +%Y%m%d-%H%M%S) ./scripts/run/run-vmshm-2client-e2e.sh
```

For two-client shared GLES, pass the workload explicitly; both clients boot the
same injected `rootfs-panfrost.ext4` image read-only:

```bash
cd /home/mzh/gpu
./scripts/run/run-vmshm-2client-e2e.sh \
  --skip-sync \
  --gles-compute-smoke \
  --gles-client-mem-mib 128 \
  --gles-proxy-mem-mib 184 \
  --gles-client-vcpus 1 \
  --gles-proxy-vcpus 2 \
  --gles-client-start-gap-sec 0 \
  --gles-sync-start-delay-sec 60 \
  --gles-min-host-available-mib 560 \
  --gles-host-online-cpus 0-3 \
  --gles-broker-cpus 0-1 \
  --gles-proxy-cpus 0-1 \
  --gles-client0-cpus 2 \
  --gles-client1-cpus 3 \
  --gles-smoke-args "--count 8388608 --iterations 20 --warmup 5 --perf --exclude-cpu-prepare" \
  --run-id vmshm-2client-gles-32m-$(date +%Y%m%d-%H%M%S)
```

The two-client GLES runner has a host-memory preflight guard to avoid repeating
host OOM cases that kill Firecracker and leave SSH unresponsive.  By default
`--gles-min-host-available-mib auto` requires:

```text
proxy_mem + 2 * client_mem + object window + 64 MiB comm windows + 512 MiB guard
```

For `--gles-compute-smoke`, the object window is selected from the runtime
`--count` because it represents the vmshm-object BO payload budget, not rootfs
selection:

```text
--count 1048576   ->  64 MiB object window
--count 4194304   ->  96 MiB object window
--count 8388608   -> 128 MiB object window
--count 16777216  -> 224 MiB object window
unknown/custom    -> 224 MiB conservative fallback
```

Use `--gles-client-mem-mib`, `--gles-proxy-mem-mib`,
`--gles-client-vcpus`, `--gles-proxy-vcpus`, and
`--gles-client-start-gap-sec` when narrowing the 64 MiB launch envelope.
For GLES, `--gles-client-start-gap-sec 0` starts client1 immediately after
client0, while a positive value waits for client0's DRM frontend and then
sleeps before launching client1.  Treat positive-gap performance as a staggered
diagnostic result, not proof of near-parallel multi-client scheduling.  Use
`--gles-min-host-available-mib 0` only for a deliberate diagnostic run where
preflight protection should be disabled.  Inspect `preflight.txt` and the
`== Host memory preflight ==` section in `result` before interpreting OOM,
timeout, or Firecracker-killed runs as GPU correctness failures.

For scheduler/host-CPU diagnosis, the two-client GLES runner also supports
temporary CPU online and process affinity knobs:

```text
--gles-host-online-cpus LIST
--gles-broker-cpus LIST
--gles-proxy-cpus LIST
--gles-client0-cpus LIST
--gles-client1-cpus LIST
```

These are diagnostic scheduling controls, not default functional behavior.  Use
them only when studying near-parallel performance on a constrained host, and
inspect `affinity.log` plus the `== Host CPU affinity ==` section in `result`.
If these knobs are used for a `host/shared` claim, rerun or otherwise obtain
the host-direct baseline under the same host CPU online condition; do not mix a
two-online-CPU host baseline with a four-online-CPU shared run.

For proxy-VM scheduling diagnosis, the same two-client GLES runner exposes
proxy Panthor scheduler controls:

```text
--gles-panthor-sched-tick-ms N
--gles-panthor-sched-highpri-wq
--gles-panthor-proxy-group-core-partitions N
```

Use 32 MiB as the main two-client scheduling baseline unless the user asks for
another size.  The current design keeps `proxy_comm_vmshm` as a fast transport
layer and schedules GPU work inside `panthor-proxy` after requests have reached
the proxy VM but before `GROUP_SUBMIT` enters the real Panthor driver:

```text
--gles-host-online-cpus 0-3
--gles-broker-cpus 0-1
--gles-proxy-cpus 0-1
--gles-client0-cpus 2
--gles-client1-cpus 3
--gles-client-vcpus 1
--gles-proxy-vcpus 2
--gles-client-mem-mib 128
--gles-proxy-mem-mib 184
--gles-sync-start-delay-sec 60
--gles-smoke-args "--count 8388608 --iterations 20 --warmup 5 --perf --exclude-cpu-prepare"
```

For this 32 MiB baseline, do not enable `--gles-panthor-sched-tick-ms`,
`--gles-panthor-sched-highpri-wq`, or
`--gles-panthor-proxy-group-core-partitions` for the formal timing run unless
you are deliberately testing that knob.  Historical evidence:

```text
old transport-layer default:
  vmshm-2client-gles-32m-corepart-baseline-20260605-150001
  shared avg = 15519.33 us

group core partition 2:
  vmshm-2client-gles-32m-corepart2-20260605-150103
  shared avg = 23737.80 us
  map_wait roughly doubled, so it is diagnostic only.

old transport-layer global b1 high-priority comm + Panthor tick=2/highpri:
  vmshm-2client-gles-32m-global-b1-hi-t2-recheck-20260605-150208
  shared avg = 15718.45 us
  correctness-valid but slightly slower than the transport-layer default.
```

Interpretation for future scheduler work: do not reintroduce channel-level
fairness knobs.  Let client requests enter the proxy VM normally, then make
scheduling decisions at the panthor-proxy submit-before-real-DRM boundary where
session, group, priority, quota, and future policy metadata are visible.
Preserve per-client request order, let the real Panthor driver manage shader
cores, and keep CPU placement explicit.

The older two-client 64 MiB scheduling-policy sample used:

```text
--gles-host-online-cpus 0-3
--gles-broker-cpus 0-1
--gles-proxy-cpus 0-1
--gles-client0-cpus 2
--gles-client1-cpus 3
--gles-client-vcpus 1
--gles-proxy-vcpus 2
--gles-panthor-sched-highpri-wq
--gles-panthor-sched-tick-ms 2
```

Treat that 64 MiB global fair policy as historical evidence from the removed
transport-layer scheduler, not as an available runner configuration.

Use no-stats runs for formal `host/shared` timing.  Use
`--gles-proxy-panthor-stats` only for short diagnostic runs because it changes
timing.

For formal 64 MiB two-client runs, keep proxy VM memory at 184 MiB or higher
unless intentionally testing OOM boundaries.  A proxy VM with 128 MiB panicked
in the Panthor GEM/shmem allocation path during a two-client 4 MiB
stats/global run, so do not treat proxy=128 MiB failures as GPU scheduling
regressions without checking `proxy.log` for OOM/panic evidence.

If the remote host is memory-degraded and a manual
`--gles-min-host-available-mib` override is required, record the override in
the worklog/result summary and treat that run as a diagnostic sample.  Do not
hide the guard setting when comparing against passthrough or host-direct
baselines.

For latency diagnosis, `--gles-proxy-panthor-stats` enables proxy VM Panthor
submit/job IRQ stats, proxy-side RPC handler stats, and client-side
`client_comm_vmshm.rpc_stats=1` segmented RPC stats.  Inspect
`PANTHOR_PROXY_RPC_STATS` in `proxy.log` and `CLIENT_COMM_RPC_STATS` in
`client0.log`/`client1.log` before attributing time to submit, completion, or
transport wait paths.  The GLES smoke script explicitly disables
`client_comm_vmshm.rpc_stats` after the workload to force the client-side dump
into dmesg even when `GPU_SMOKE_AFTER_RUN=shell` leaves the guest alive for the
outer harness.

Keep stdout from rootfs/config preparation helpers reserved for returned paths
when the caller uses command substitution. Send diagnostics such as
`rootfs_payload_inject_start`, `rootfs_payload_inject_done`, and compile status
to stderr so they land in prep logs without corrupting Firecracker config
paths.

## Rootfs Selection

- Lightweight comm/query tests use `firecracker-bins/rootfs/rootfs.ext2` with `init=/bin/sh`, commonly through `firecracker-bins/configs/shared/vmshm-1client/*-vm-config.json` or `firecracker-bins/configs/shared/vmshm-2client/*-vm-config.json`.
- One-client IOCTL semantic smokes inject `panthor_ioctl_smoke` and its init script into `rootfs.ext2`; the selected semantic mode comes from the Firecracker boot args.
- Shared GLES compute/perf smokes inject the GLES payload into `rootfs-panfrost.ext4`; the workload size and iteration policy come from the Firecracker boot args.
- Full GPU userspace workloads require a rootfs with Mesa/Panthor or Panfrost userspace. Do not switch rootfs assumptions without inspecting the active Firecracker JSON config or launcher script.

Do not switch rootfs images just to switch IOCTL mode, GLES `--count`,
`--iterations`, `--warmup`, or wrapper scripts. Those choices belong in the
generated Firecracker config and the payload injected into the base image before
launch.

## Current Functional Surface

The current shared path is beyond discovery-only testing.  The GLES compute
smoke exercises the client/proxy Panthor path through BO creation, mmap,
VM_BIND, group creation, nonzero GROUP_SUBMIT, syncobj/timeline waits,
completion, readback, and teardown.  Treat this as a working prototype surface,
not as a finished scheduler or production ABI: handle namespaces, vmshm-object
BO payload ownership, vmshm-comm metadata transport, sync semantics, proxy VM
passthrough interrupts, and multi-client scheduling still need careful
regression testing when touched.

When adding IOCTL coverage, prefer focused payloads/tests that validate one
semantic boundary at a time.

For IOCTL design details, read `/home/mzh/gpu/docs/shared/PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md` before changing handle mapping, user-pointer copying, mmap/BO sharing, VM_BIND, group submit, or syncobj behavior.

## Reporting

A good report includes:

- Run ID and `RESULT: PASS/FAIL`.
- Local log path.
- Which components were rebuilt, synced, skipped, or deployed.
- Which rootfs/config path was used.
- Key evidence such as `panthor-client: DEV_QUERY selftest passed`, `proxy_comm_vmshm: selftest passed`, `panthor-proxy: vmshm handler registered`, or IOCTL smoke output.
- First meaningful failure symptom and the specific proxy/client/broker log where it appears.

Always fetch and inspect local logs before reporting success. Do not infer success from exit code alone. Keep complete logs under the selected `GPU-SFTP/log/shared/<test-kind>/${RUN_ID}` directory.
