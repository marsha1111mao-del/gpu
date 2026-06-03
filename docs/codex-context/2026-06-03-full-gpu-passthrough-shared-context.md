# Codex Context - Full GPU Passthrough and Shared Virtualization Session

Date: 2026-06-03
Workspace root: `/home/mzh/gpu`

This document is the compact context snapshot for the long GPU passthrough and
shared virtualization conversation. It is intended for future Codex sessions so
they can continue without rereading the whole chat or the old detailed
optimization log.

## User Intent And Working Style

The main research goal is to optimize the immature Mali/Panthor GPU
passthrough design at the driver/kernel/Firecracker level, then prove each
important change with remote host-vs-VM performance tests. Userspace drivers
and OpenGL programs are test tools only; do not treat userspace-driver tricks as
real optimization unless the user explicitly asks for a separate userspace
experiment.

The user prefers practical, measurable work:

- Keep effective kernel/driver optimizations.
- Delete failed ideas completely, even if they can be hidden behind optional
  compile flags.
- Avoid noisy historical data that can bias later judgment.
- Use English folder and file names.
- Do not over-focus on git branch management; one `main` branch is enough for
  this single-developer workflow.
- When testing passthrough performance, follow the formal guide and report the
  single Host/VM ratio table.

## Repository And Document Layout

Current top-level organization:

```text
/home/mzh/gpu/
  docs/
    passthrough/
    shared/
    codex-context/
  scripts/
  GPU-SFTP/
  Linux-Guest-GPU/
  Linux-Host-GPU/
  firecracker/
```

Important documents:

- `docs/passthrough/GPU_PASSTHROUGH_IMPLEMENTATION_ANALYSIS.md`
- `docs/passthrough/GPU_PASSTHROUGH_EFFECTIVE_OPTIMIZATIONS.md`
- `docs/passthrough/GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md`
- `docs/passthrough/GPU_PASSTHROUGH_OPTIMIZATION_LOG.md`
- `docs/shared/GPU_VIRTUALIZATION_DRIVER_ANALYSIS.md`
- `docs/shared/PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md`
- `docs/shared/PANTHOR_GLES_COMPUTE_SMOKE_BASELINE_ANALYSIS.md`
- `docs/codex-context/2026-05-28-vmshm-panthor-context.md`
- `docs/codex-context/2026-06-03-gpu-passthrough-optimization-context.md`

`GPU_PASSTHROUGH_EFFECTIVE_OPTIMIZATIONS.md` is now the durable summary of
important passthrough optimization designs and blacklisted failed directions.
`GPU_PASSTHROUGH_OPTIMIZATION_LOG.md` should be a lightweight incremental log
for future important optimization attempts, using simple self-incrementing
entries that combine design and test result in one place.

## Skills

The old broad GPU remote autotest skill was split into two focused skills:

- `/home/mzh/.codex/skills/gpu-passthrough-autotest/SKILL.md`
- `/home/mzh/.codex/skills/gpu-shared-virtualization-autotest/SKILL.md`

Use `gpu-passthrough-autotest` for single-VM passthrough performance,
pmthor/Firecracker passthrough, guest/host Panthor passthrough kernel work,
GPA-to-HPA/page-table work, passthrough diagnostics, and host-vs-VM GLES
performance sweeps.

Use `gpu-shared-virtualization-autotest` for vmshm GPU sharing, proxy/client
VMs, broker tests, Panthor client/proxy drivers, DEV_QUERY forwarding, one
proxy plus one client tests, explicit two-client experiments, and shared
virtualization run logs.

Do not mix these two paths casually. Passthrough uses one VM owning the passed
through GPU view. Shared virtualization uses client/proxy VMs and vmshm RPC.

## Remote Environment

Fixed remote test machine:

```text
Remote SSH target: root@192.168.137.10
Remote password: root
Local artifact root: /home/mzh/gpu/GPU-SFTP
Remote artifact root: /root/GPU-SFTP
```

Scripts provide password handling through their own `setsid`/`SSH_ASKPASS`
helpers. Prefer scripts over ad hoc SSH. If manual SSH is needed, create a
temporary askpass helper or use the same style as the scripts.

## Current Log Layout

Logs were moved out of `GPU-SFTP/firecracker-bins/run-logs` and into
`GPU-SFTP/log`, split by test content.

Current layout:

```text
Passthrough performance:
  local  /home/mzh/gpu/GPU-SFTP/log/passthrough/perf/<RUN_ID>
  remote /root/GPU-SFTP/log/passthrough/perf/<RUN_ID>

Passthrough probe/deploy:
  local  /home/mzh/gpu/GPU-SFTP/log/passthrough/probe/<RUN_ID>
  remote /root/GPU-SFTP/log/passthrough/probe/<RUN_ID>

Shared virtualization one-client:
  local  /home/mzh/gpu/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>
  remote /root/GPU-SFTP/log/shared/vmshm-1client/<RUN_ID>

Shared virtualization two-client:
  local  /home/mzh/gpu/GPU-SFTP/log/shared/vmshm-2client/<RUN_ID>
  remote /root/GPU-SFTP/log/shared/vmshm-2client/<RUN_ID>
```

The scripts exclude both `log/` and old `firecracker-bins/run-logs/` during
artifact sync. They also remove obsolete remote `firecracker-bins/run-logs`
during sync so stale remote history does not survive simply because rsync
excluded it.

As of the latest verification:

- Local old `GPU-SFTP/firecracker-bins/run-logs` was absent.
- Remote old `/root/GPU-SFTP/firecracker-bins/run-logs` was absent.
- New local and remote result files existed under `GPU-SFTP/log/...`.

## Passthrough Formal Performance Protocol

Formal passthrough performance testing compares Host direct and passthrough VM
using the same GLES compute smoke workload. The result format is one table
only:

```text
Workload | iter | total | metadata | submit | completion | map_unmap | Host phase share ref
```

All performance values are `host/vm` ratios. Closer to `1.000` means the VM is
closer to host performance. Do not report old overhead tables unless the user
explicitly asks.

Default formal workloads:

- 4 MiB: 100 iterations, 5 warmup.
- 16 MiB: 100 iterations, 5 warmup.
- 64 MiB: 20 iterations, 5 warmup.

Formal runs must not enable timing diagnostics, tracing, CPU affinity, IRQ
affinity, hugepage toggles, `perf record`, `strace`, `ftrace`, or similar
instrumentation. Those are diagnostic runs only.

Standard command:

```bash
cd /home/mzh/gpu
RUN_ID=gpu-perf-host-vs-passthrough-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900
```

## Latest Verified Passthrough Performance Result

Run ID:

```text
gpu-perf-logpath-passthrough-20260603-174020
```

Result:

```text
RESULT: PASS
Local logs:  /home/mzh/gpu/GPU-SFTP/log/passthrough/perf/gpu-perf-logpath-passthrough-20260603-174020
Remote logs: /root/GPU-SFTP/log/passthrough/perf/gpu-perf-logpath-passthrough-20260603-174020
```

Formal Host/VM ratio table:

| **Workload** | **iter** | **total** | **metadata** | **submit** | **completion** | **map_unmap** | **Host phase share ref** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 100 | 0.788 | 0.882 | 0.796 | 0.478 | 0.753 | 79.0/6.7/14.4/0.07 |
| 16 MiB | 100 | 0.767 | 0.794 | 1.061 | 0.641 | 0.755 | 81.0/2.0/16.3/0.02 |
| 64 MiB | 20 | 0.889 | 0.912 | 0.259 | 0.876 | 1.268 | 80.0/0.75/19.3/0.01 |

This test was also used to verify the new passthrough log path.

## Effective Passthrough Optimizations To Keep

The following have evidence and should remain part of the default design:

- GPU page-table mapping batching, including 2 MiB candidate handling with
  correctness-preserving fallback to 4 KiB leaf PTEs when HPA alignment or
  continuity is insufficient.
- GPA-to-HPA batch translation and per-io-pgtable scratch page.
- Host GPA-to-HPA HVC in-place guest array handling through `kvm_vcpu_map()`,
  avoiding `kmalloc + kvm_read_guest + kvm_write_guest` around the array.
- Panthor scheduler workqueue changed from unbound to bound, preserving
  `WQ_MEM_RECLAIM` but removing `WQ_UNBOUND`.
- Hot-path logging cleanup in KVM/VGIC/pmthor/Panthor/page-table/IRQ/submit
  paths. No `pr_info()` style high-frequency printing in formal paths.
- Default-off PT/IRQ/submit diagnostic stats. Use them only for attribution.
- Host/VM userspace alignment and the single formal Host/VM ratio table.
- Faster iteration through single passthrough guest Image builds, host
  Image-only deploy, or selected-module deploy instead of full client/proxy
  role-kernel or full module sync when not needed.

## Rejected Passthrough Directions

Do not reintroduce these unless the user explicitly starts a new research
attempt with a changed design and new tests:

- BO preallocation.
- BO bucket pool.
- BO capacity reuse.
- BO resident-buffer testing.
- BO reuse/lazy unmap/suballocation as a default optimization.
- Any test mode based on repeating the exact same GPU task to keep buffers
  resident, because real task submission does not normally match that scenario.
- Userspace-driver or OpenGL-level tricks as the primary optimization.
- New IOCTLs just to support the failed BO reuse idea.
- Guest raw-unmask HVC.
- Raw ACK/prequeue/hardirq job IRQ fast paths.
- Guest Panthor IRQ thread boost.
- `WQ_HIGHPRI`, `WQ_CPU_INTENSIVE`, deferred scheduler wake as defaults.
- Firecracker `nice -10`, guest `nohlt`, cpuidle-off boot as defaults.
- CPU/IRQ affinity as a formal default. It is diagnostic only unless retested.
- Hot-path `printk` or `pr_info` used to debug timing in formal runs.

The buffer-lifetime story is important: the user and Codex explored bucket
preallocation, capacity reuse, idle BO pools, cached HPA lists, lazy unmap, and
same-VM reuse. This was eventually judged too narrow and likely to optimize an
unrealistic repeated-task case. The user explicitly required all BO
preallocation/reuse/bucket/resident/capacity-related code, scripts, tests, and
docs to be removed, while preserving only the blacklist/lesson in durable docs.

## Current Bottleneck Understanding

For small workloads such as 4 MiB, fixed costs dominate. Completion wait and
fence/map wait can outweigh the pure GPU execution time. Guest IRQ thread
latency itself did not look like the full explanation; host masked/resample/EOI
tails or Mesa/fence wait behavior are more plausible contributors.

For 16 MiB, metadata and completion both matter. This size is useful for
detecting changes that help throughput but hurt latency, or vice versa.

For 64 MiB, metadata/data movement dominates more visibly. GPA-to-HPA HVC and
page-table population were reduced by batching and in-place HVC array handling,
but CPU prepare, buffer upload, Mesa/DRM BO path, VM_BIND, and page-table work
still need whole-path attribution.

The 2 MiB GPU block-PTE direction remains conceptually valuable, but current
evidence says the blocker is often HPA backing alignment and continuity, not
only the PTE writer. Future 2 MiB work needs allocation/backing alignment work.

## Shared Virtualization State

The shared virtualization path is vmshm-based:

```text
client VM userspace /dev/panthor ioctl
  -> panthor-client DRM frontend
  -> client_vmshm_comm / shared-memory RPC
  -> vmshm-broker eventfd relay
  -> proxy_vmshm_comm
  -> panthor-proxy
  -> real panthor driver in proxy VM
```

The current functional surface has moved beyond discovery-only. The shared path
now validates per-open `OPEN_SESSION` / `CLOSE_SESSION`, Panthor `DEV_QUERY`
for `GPU_INFO` and `CSIF_INFO`, and `VM_CREATE` / `VM_DESTROY` through a real
proxy-side Panthor session. Full GPU submission, BO lifecycle virtualization,
VM_BIND, fences/syncobj, event delivery, mmap/BO sharing, and command stream
execution are still design work or partial work. Use
`PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md` before changing handle mapping,
session namespace, user-pointer copying, VM_BIND, group submit, syncobj, or
mmap behavior.

Default shared test is one proxy VM plus one client VM:

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-1client-devquery-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run-vmshm-e2e.sh
```

Fast log-path or behavior verification can use:

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-logpath-1client-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run-vmshm-e2e.sh --skip-build
```

Fast retest of the current session/devquery/vm-create surface should avoid
full rebuilds when code has not changed:

```bash
cd /home/mzh/gpu
RUN_ID=vmshm-1client-vm-create-rerun-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run-vmshm-e2e.sh --skip-build --vm-create-smoke
```

Shared virtualization build policy is artifact-reuse first. The known-good
outputs in `GPU-SFTP/firecracker-bins/` and
`Linux-Guest-GPU/out/vmshm-arm64/{client,proxy}` should be treated as the
incremental base for later tests, not as disposable state. Before running a
test, classify the changed files and rebuild only the component invalidated by
those changes:

| Changed area | Rebuild | Test flags |
| --- | --- | --- |
| No relevant code/config change | Nothing | `--skip-build` |
| `Linux-Guest-GPU/` Panthor client/proxy, vmshm comm/manager, UAPI, Kconfig, or role config | Client/proxy role kernels only | skip Firecracker build if invoking manually, or use the existing kernel build path and preserve `out/vmshm-arm64` |
| `firecracker/Firecracker-CCA-MZH/` or `firecracker/vmshm-broker/` | Firecracker/broker only | `--skip-kernel-build` |
| `GPU-SFTP/tests/panthor-ioctl-smoke/` | Smoke binary only | skip kernel and Firecracker/broker builds |
| `GPU-SFTP/firecracker-bins/configs/shared/...` or config installer | Config regeneration/sync only | skip kernel and Firecracker/broker builds unless new code is required |
| rootfs image/content | Rootfs sync only when requested or required | do not sync rootfs for ordinary IOCTL smoke |

Do not rerun a full from-scratch build for ordinary smoke retests. Full builds
are for first setup, missing/corrupted artifacts, broad build-system changes,
Kconfig changes that invalidate both role kernels, or explicit user requests.
In particular, do not delete `Linux-Guest-GPU/out/vmshm-arm64` just to make a
test feel clean; keeping it is what makes subsequent kernel builds incremental.

Use two-client tests only when explicitly testing multi-client behavior.

## Latest Verified Shared Virtualization Result

Current VM-create smoke verification:

```text
Run ID: vmshm-1client-vm-create-rerun-20260603-182401
RESULT: PASS
Local logs:  /home/mzh/gpu/GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vm-create-rerun-20260603-182401
Remote logs: /root/GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vm-create-rerun-20260603-182401
```

Verified chain:

```text
OPEN_SESSION
DEV_QUERY GPU_INFO
DEV_QUERY CSIF_INFO
VM_CREATE client_vm=1 proxy_vm=1 user_va_range=0x800000000000
VM_DESTROY client_vm=1 proxy_vm=1
CLOSE_SESSION
PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS
```

Final log-path and remote-cleanup verification run:

```text
Run ID: vmshm-logpath-cleancheck-20260603-174637
RESULT: PASS
Local logs:  /home/mzh/gpu/GPU-SFTP/log/shared/vmshm-1client/vmshm-logpath-cleancheck-20260603-174637
Remote logs: /root/GPU-SFTP/log/shared/vmshm-1client/vmshm-logpath-cleancheck-20260603-174637
```

Important evidence from the result:

```text
proxy_comm_vmshm: selftest passed
panthor-proxy: vmshm handler registered
client_comm_vmshm: perf selftest passed
panthor-client: DEV_QUERY selftest passed
panthor-client: DEV_QUERY perf selftest passed
panthor-client: registered DRM frontend
```

This run verified that the new shared log path works and that obsolete remote
`firecracker-bins/run-logs` is removed during sync.

## Scripts

Main scripts are under `/home/mzh/gpu/scripts`:

- `run-host-vs-passthrough-gles-perf.sh`
- `deploy-host-kernel-and-test.sh`
- `run-vmshm-e2e.sh`
- `run-vmshm-2client-e2e.sh`

They were updated to use `SFTP_LOG_ROOT="${SFTP_ROOT}/log"` and
`REMOTE_LOG_ROOT="${REMOTE_ROOT}/log"`, with subdirectories by test kind. They
also exclude logs during artifact sync and clean obsolete remote
`firecracker-bins/run-logs`.

The four scripts passed `bash -n` and `--help` after the log-path migration.

## Testing Discipline For Future Work

When a future passthrough optimization is important:

1. Implement the kernel/driver/Firecracker change.
2. Run the formal host-vs-VM table for 4/16/64 MiB.
3. Use VM-only PT/IRQ/submit diagnostics only if attribution is needed.
4. Record the concise design and result together in
   `docs/passthrough/GPU_PASSTHROUGH_OPTIMIZATION_LOG.md`.
5. If it does not improve the realistic workload, delete the code and keep only
   the lesson/blacklist entry if it is useful.

Avoid frequent expensive tests for tiny edits, but do not keep unverified
optimization code. Group related changes, then run a meaningful test.

For passthrough code changes, do not rebuild vmshm client/proxy role kernels
unless the shared path is being tested. Use the normal passthrough guest Image.
For host kernel changes, prefer Image-only or selected-module deployment unless
full module install is really needed.

## Final State To Preserve

The final direction is conservative and measurement-driven:

- Optimize actual GPU task lifecycle, not artificial repeated/resident buffer
  scenarios.
- Keep page-table/HVC batching, host HVC in-place array, bound Panthor
  scheduler workqueue, and hot-path logging cleanup.
- Keep diagnostics default-off.
- Keep the formal performance report as one Host/VM ratio table.
- Keep logs in `GPU-SFTP/log/<path-kind>/<run-id>`.
- Keep passthrough and shared virtualization testing workflows separated.
- Delete failed mechanisms instead of hiding them behind optional flags.
