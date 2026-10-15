# Panthor Shared GPU Virtualization Worklog

This log records implementation work toward the Panthor shared-GPU ioctl
virtualization plan. It intentionally separates tested designs from partial or
incorrect designs so future work can reuse the stable pieces and avoid repeating
dead ends.

## 2026-06-12: ARM CCA Realm GPU Sharing Decomposition

### Current conclusion

Do not treat `realm_config + gpu_passthrough=true` as a valid shortcut for
confidential GPU passthrough. The project now has enough negative evidence to
blacklist that route until the local trusted-GPU device-memory and interrupt
model is implemented.

Evidence:

- `GPU-SFTP/log/passthrough/perf/gpu-passthrough-realm-smoke-20260612-075604`
  started a single GPU-owning passthrough VM as a Realm. Firecracker created the
  Realm, initialized both vCPUs, mapped the GPU MMIO aperture, and printed
  `Successfully started microvm`, but the board then stopped making useful
  progress and required a manual reboot.
- `GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-realm-smoke-20260612-033031`
  and
  `GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-realm-sha512-smoke-20260612-074227`
  show the same unsafe direction in the full shared stack: a GPU-owning proxy
  Realm plus vmshm windows reaches early Realm/GPU setup and then hangs.
- `GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-client-realm-smoke-20260612-074826`
  is a useful partial diagnostic only. Client Realms booted and reached the
  proxy through the vmshm control path; basic Panthor IOCTLs passed, but GLES
  failed at GBM device creation. This does not satisfy the requirement that each
  real GPU task can run in a confidential VM.

The important implementation fact is that Firecracker already has the Realm main
memory scaffold:

- `VmResources::allocate_guest_memory()` selects guestmemfd-backed memory when
  `machine_config.realm_config` is present.
- `Vm::set_kvm_memory_regions2()` registers the memslot with
  `KVM_MEM_GUEST_MEMFD`.
- `config_realm()` sets `KVM_MEMORY_ATTRIBUTE_PRIVATE` over the guest memory.

That is necessary but not sufficient for a non-secure physical GPU. The GPU is
not an RME-aware Realm device, so its DMA-visible buffers, MMIO aperture, IRQ
delivery, and passthrough GPU page tables must be explicitly adapted. In
particular:

- GPU command/data BO pages that the physical GPU reads or writes cannot remain
  ordinary private Realm memory. They need a shared/device-reachable allocation
  model with explicit ownership, lifetime, and cache maintenance.
- The current passthrough GPU page-table path writes HPA into GPU PTEs. For
  Realm-owned BOs, this HPA must correspond to pages that have been safely
  shared or otherwise delegated for non-secure device access; translating private
  Realm IPA/HPA is not enough.
- GPU MMIO and IRQ injection need a Realm-aware policy. The existing pmthor
  irqfd/resample path proves useful for normal VMs but does not by itself prove
  safe interrupt delivery into a Realm.
- vmshm memfd windows are explicitly shared mappings and must stay outside the
  private Realm memory model. Their slots, notification doorbells, and client
  access policy need to be reasoned about separately from guestmemfd RAM.

The current safety net is intentionally conservative:

- Firecracker rejects `realm_config && gpu_passthrough=true` before KVM VM
  memory, pmthor IRQ, or GPU MMIO setup.
- The host `GPA_TO_HPA` hypercall rejects Realm private GPA via
  `kvm_mem_is_private(kvm, gfn)`. GPU PTE construction can only receive HPA for
  normal/shared GPA, not private guestmemfd pages.
- Runner flags that would create a GPU-owning Realm exit locally before SSH.

### Blacklisted direction

The following direction is blacklisted:

```text
Take a normal GPU passthrough or shared proxy VM config,
add machine-config.realm_config,
and run it as a GPU-owning Realm without changing the memory/IRQ/device model.
```

The runners now reflect this:

- `scripts/run/run-host-vs-passthrough-gles-perf.sh --vm-realm` refuses to run
  before it touches the remote board.
- `scripts/run/run-vmshm-2client-e2e.sh --gles-realm` and
  `--gles-proxy-realm` refuse to run for the same reason.
- `scripts/run/run-vmshm-2client-e2e.sh --gles-client-realm` is also blocked
  for now. The earlier client-only Realm diagnostic is useful evidence about
  the control path, but it is not an end-to-end confidential GPU task and should
  not be rerun as if it proved the design.
- Firecracker also rejects a direct JSON/API boot with both `realm_config` and
  `gpu_passthrough=true`, so this is blocked below the runner layer too.

### Required design path

The next implementation work should proceed in this order:

1. Define a CCA-safe GPU shared-buffer ABI for Realm GPU BO payloads. This is
   the core blocker: GPU-visible pages must be shared/device-accessible by
   construction rather than accidentally backed by private guestmemfd memory.
2. Keep the host GPA-to-HPA hypercall as a hard gate: it must reject private
   Realm GPA and accept only normal/shared GPA from the explicit shared GPU BO
   pool.
3. Convert every GPU-visible proxy BO class to that pool, including user BO
   payloads, firmware/shared sections, command queues, syncwait buffers,
   suspend buffers, tiler heaps, and page-table pages.
4. Audit pmthor IRQ injection and GPU MMIO mapping against the local trusted-GPU
   Realm model, including reset and teardown when a Realm exits or faults.
5. Only after those pieces exist, rerun a single GPU-owning proxy-equivalent
   Realm smoke with a tiny GPU task.
6. Re-enter the shared path: normal client to proxy Realm, client Realm to
   normal proxy, then full client Realm to proxy Realm.

### GPU-visible memory audit

This is the current inventory of objects that can be consumed by the physical
GPU or its page-table walker in the shared stack. Anything listed as ordinary
shmem or kernel page allocation is not CCA-safe for a GPU-owning Realm until it
is moved to an explicit shared/device-reachable pool.

| Object class | Current backing/path | CCA status |
| --- | --- | --- |
| Client BO payloads in the shared path | `panthor_proxy_session_bo_create()` obtains a `proxy_vmshm_object`; `panthor_gem_create_vmshm_with_handle()` stores it as `bo->vmshm_payload`; VM_BIND maps it through `panthor_vm_map_vmshm_spans()` using vmshm GPA spans. | This is the right direction for payload data because the GPU-visible bytes come from explicit vmshm windows, not from the proxy Realm's private RAM. It still needs a formal CCA ABI, cache policy, and lifetime rules. |
| Ordinary Panthor user BOs | `panthor_gem_create_with_handle()` uses `drm_gem_shmem_create()` and `panthor_vm_map_pages()` maps the resulting pages into GPU PTEs. | Unsafe for a GPU-owning Realm. These pages would be normal guest allocations and can become private guestmemfd memory. |
| Proxy BO metadata for vmshm-backed BOs | The GEM object is still shmem, but VM_BIND bypasses those shmem pages when `bo->vmshm_payload` is present. | CPU metadata can remain private if the GPU never maps it. The payload mapping path must keep rejecting accidental fallback to shmem. |
| Firmware sections and FW shared interface | `panthor_fw_load_section_entry()` and `panthor_fw_alloc_queue_iface_mem()` allocate `panthor_kernel_bo_create()` objects backed by `drm_gem_shmem_create()`. | Unsafe. Firmware-visible shared sections and queue interfaces must be allocated from the CCA-safe GPU shared pool. |
| Queue ring buffers | `group_create_queue()` allocates `queue->ringbuf` with `panthor_kernel_bo_create()`. | Unsafe. Command buffers read by the GPU/FW cannot be private Realm pages. |
| Suspend and protected-mode suspend buffers | `panthor_fw_alloc_suspend_buf_mem()` returns `panthor_kernel_bo_create()` memory. | Unsafe until moved to shared/device-reachable memory. |
| Group sync objects | `panthor_group_create()` allocates `group->syncobjs` with `panthor_kernel_bo_create()`. | Unsafe. The GPU/FW observes these synchronization structures. |
| Tiler heap contexts and chunks | `panthor_heap_pool_create()` and `panthor_alloc_heap_chunk()` allocate kernel BOs through `panthor_kernel_bo_create()`. | Unsafe. Heap context and chunk headers are GPU-consumed data structures. |
| GPU page-table pages, including PGD | `panthor_mmu.c` uses `alloc_pt()` with ordinary pages or `pt_cache`; `io-pgtable-arm.c` translates PGD/table GPA to HPA for TTBR and descriptors. | Unsafe for a Realm unless page-table pages themselves come from shared/device-reachable memory. The host `GPA_TO_HPA` rejection of private GPA is a guardrail, not the full implementation. |
| vmshm communication windows and doorbells | Firecracker maps vmshm memfd windows as shared KVM memory slots, not guestmemfd private RAM. | Keep separate from private guest memory. The existing VMID/session isolation tests cover cross-client access, but Realm use still needs explicit ABI and reset/teardown policy. |

The likely implementation shape is a VMM-provided GPU shared pool, separate from
guest private RAM, exposed through FDT to the GPU-owning guest and registered as
normal/shared KVM memory. The Panthor proxy side should allocate all
GPU-visible kernel BOs and page-table pages from that pool, while CPU-only
metadata can stay private. The existing vmshm object path can be the payload
model, but it must be tightened into an ABI rather than relying on ordinary GEM
fallback behavior.

Follow-up design note:

- `docs/shared/CCA_CONFIDENTIAL_GPU_SHARING_DESIGN.md` records the current
  trusted-GPU boundary for RK3588. The GPU is not behind an SMMU/GPC-capable
  stage-2 path, so OpenCCA per-Realm GPT view switching can protect CPU access
  but cannot, by itself, protect GPU DMA. The first implementation stage marks
  GPU-visible Panthor pages as explicit Realm shared memory and keeps direct
  Realm GPU boot blocked until a trusted GPU owner/domain model is added.

### Realm MMIO and smoke gate update

Source inspection found that the old GPU MMIO path was still a normal-VM
shortcut. `kvm_phys_addr_ioremap()` rejects Realms, and the local
`KVM_SET_MMIO_REGION` implementation identity-mapped the device through the
ordinary stage-2 page table. That is wrong for a Realm GPU task because the
Realm guest `ioremap()` path marks non-protected MMIO as a shared/decrypted IPA
alias.

The host Realm path now maps GPU MMIO through RMM `RTT_MAP_UNPROTECTED` at
`ipa | shared_bit` with device-nGnRE attributes. This aligns the host mapping
with the guest MMIO alias and avoids installing the device aperture in the
private/base IPA view.

Firecracker remains conservative. A GPU-owning Realm still fails unless the VMM
process has `FC_ALLOW_TRUSTED_GPU_REALM=1`. The passthrough runner now exposes a
single explicit smoke gate, `--vm-realm-trusted-gpu-experimental`, which creates
a temporary Realm JSON in the run log directory and passes that environment
variable to Firecracker. The shared vmshm runner still blocks proxy/client Realm
GPU modes; the single-VM passthrough Realm smoke must pass first, then protected
vmshm or multi-Realm guestmemfd sharing can be designed on top.

### First implementation stage

The first memory adaptation stage is now implemented in `Linux-Guest-GPU`:

- `drivers/gpu/drm/panthor/panthor_gem.c` pins ordinary shmem BOs for their
  lifetime in a Realm and converts their pages with `set_memory_decrypted()`
  before userspace receives a handle. This avoids the broken ordering where a
  user writes private Realm pages and the driver later converts them to shared
  memory during VM_BIND.
- `panthor_kernel_bo_create()` uses the same conversion path before firmware,
  queue, suspend, sync, and heap kernel BOs are mapped into GPU VA space.
- `drivers/gpu/drm/panthor/panthor_mmu.c` converts Panthor GPU page-table pages
  before writing descriptors. Teardown converts them back with
  `set_memory_encrypted()`; if protection fails, the page table is leaked rather
  than returned to the allocator in an unknown security state.
- `drivers/iommu/io-pgtable-arm.c` converts the `GPA_TO_HPA` batch exchange
  page before passing its GPA to the host hypercall and protects it again on
  teardown.

This stage is a correctness gate for Realm GPU bring-up under the local trusted
GPU assumption. It still makes those pages normal/shared from the Realm point of
view, so it does not claim host-confidential GPU payloads. The final
host-confidential design still needs an OpenCCA trusted GPU device domain or a
protected multi-Realm guestmemfd object model.

## 2026-06-12: VMID-Scoped Isolation Probe Harness And Runner Hardening

### Goal

Make the two-client shared-GPU path easier to validate as an isolation boundary:
client0 creates a live vmshm-backed BO, client1 tries to look up that payload
handle while spoofing `requester_vmid=1`, and the run passes only if the lookup
is rejected with `EACCES`. The same probe now also covers a stronger malicious
client model: client1 writes raw Panthor RPC messages directly into
`/dev/client_comm_vmshm`, bypassing the `panthor-client` DRM frontend, and tries
to use client0's session for both a read-style `DEV_QUERY` and a destructive
`CLOSE_SESSION`.

### Implementation

New pieces:

- `GPU-SFTP/tests/vmshm-lookup-probe/vmshm_lookup_probe.c`
  - opens `/dev/client_vmshm_manager`
  - calls `CLIENT_VMSHM_MANAGER_IOC_GET_OBJECT`
  - supports `--handle`, `--spoof-vmid`, and
    `--expect denied|inaccessible|success`
  - treats `EACCES` as the required result for strict cross-VM lookup denial;
    `inaccessible` also accepts `ENOENT` for stale/non-live handles
- `scripts/build/build-vmshm-lookup-probe.sh`
  - cross-builds the probe as a static AArch64 binary
  - installs it to `GPU-SFTP/firecracker-bins/bin/vmshm_lookup_probe`
- `GPU-SFTP/tests/panthor-ioctl-smoke/panthor_ioctl_smoke.c`
  - adds `--bo-hold --hold-sec N --bo-size BYTES`
  - creates a Panthor BO, prints `BO_HOLD_READY`, keeps the BO live for the
    requested window, then closes it
- `GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh`
  - reads `gpu_smoke_vmshm_probe_*` kernel cmdline keys
  - runs `/root/vmshm_lookup_probe`
  - emits `VMSHM_ISOLATION_RESULT=PASS|FAIL`
  - reads `gpu_smoke_raw_rpc_probe_*` keys and runs the raw vmshm RPC probe
    before normal GLES setup
  - reads `gpu_smoke_ioctl_mode=holder` and
    `gpu_smoke_ioctl_args_tokens=...` so client0 can run the IOCTL holder
    instead of GLES during the negative isolation probe
- `GPU-SFTP/tests/vmshm-raw-rpc-probe/vmshm_raw_rpc_probe.c`
  - opens `/dev/client_comm_vmshm`
  - parses the shared comm queue layout
  - writes raw `PANTHOR_VMSHM_MSG_DEV_QUERY_REQ` and
    `PANTHOR_VMSHM_MSG_CLOSE_SESSION_REQ` messages with client0's session id
  - verifies proxy consumption through the C2P used ring
  - uses a normal Panthor `DEV_QUERY` as a doorbell kick in irq-notify mode; the
    kick does not participate in the security decision
- `Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c`
  - logs `SESSION_ACCESS_DENIED op=lookup|destroy session=... owner_vmid=...
    requester_vmid=...` when a channel tries to access a session owned by
    another VMID
- `scripts/run/run-vmshm-2client-e2e.sh`
  - adds `--gles-vmshm-isolation-probe`
  - in probe mode, starts client0 as a 32 MiB IOCTL BO holder, extracts a live
    `owner_vmid=1` session id and `payload=0x...` handle from `proxy.log`, then
    starts client1 with that handle and client0's session id
  - requires normal GLES success, `VMSHM_ISOLATION_RESULT=PASS`,
    `VMSHM_RAW_RPC_RESULT=PASS`, and proxy-side denied logs for both lookup and
    destroy attempts when the probe mode is enabled

Runner hardening added at the same time:

- The RK3588 target currently has `tar` but not `rsync`. The two-client runner
  now falls back to a tar stream for normal source/runtime sync and log fetch.
- `--sync-rootfs` uses explicit atomic file streaming for rootfs images instead
  of coarse directory replacement.
- The proxy-side client1 object window moved from GPA `0x38000000` to
  `0x50000000`; `0x38000000` overlaps when the object window is 224 MiB.

### Verification

Static and build checks:

```text
bash -n scripts/run/run-vmshm-2client-e2e.sh
sh -n GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh
gcc -fsyntax-only -Wall -Wextra GPU-SFTP/tests/vmshm-lookup-probe/vmshm_lookup_probe.c
gcc -fsyntax-only -Wall -Wextra GPU-SFTP/tests/vmshm-raw-rpc-probe/vmshm_raw_rpc_probe.c
gcc -fsyntax-only -I/usr/include/drm -ILinux-Guest-GPU/include/uapi/drm GPU-SFTP/tests/panthor-ioctl-smoke/panthor_ioctl_smoke.c
./scripts/build/build-vmshm-lookup-probe.sh
./scripts/build/build-vmshm-raw-rpc-probe.sh
./scripts/build/build-panthor-ioctl-smoke.sh
TARGETS=Image ./scripts/build/build-guest-vmshm-kernels.sh
```

The secure split path already passed after the GPA/tar fixes:

```text
run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-secure-split-20260612-015506

result:                 GLES_PASS
client0 iter_total avg: 27474.45 us
client1 iter_total avg: 27687.75 us
shared mean:            27581.10 us
host baseline:          25458.05 us
host/share:             0.923
```

Live-BO negative isolation pass:

```text
command:
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=vmshm-2client-gles-isolation-holder2-20260612-024226 \
  ./scripts/run/run-vmshm-2client-e2e.sh \
  --gles-compute-smoke \
  --skip-gles-remote-build \
  --gles-vmshm-isolation-probe \
  --gles-smoke-args '--count 64 --iterations 1 --warmup 0' \
  --gles-client-mem-mib 128 \
  --gles-proxy-mem-mib 384

run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-isolation-holder2-20260612-024226

result:                         GLES_PASS
client0 holder:                 PANTHOR_BO_HOLD_SMOKE=PASS
client0 live payload:           0x100000001, size=0x2000000
client1 lookup result:          VMSHM_LOOKUP_PROBE_INACCESSIBLE errno=13 (EACCES)
client1 isolation marker:       VMSHM_ISOLATION_RESULT=PASS
client1 GLES correctness:       COMPUTE_CHECK=PASS, Mali-G610 (Panfrost)
proxy evidence:
  session=2 owner_vmid=1 BO_CREATE payload=0x100000001 payload_size=0x2000000
  session=4 owner_vmid=2 runs GLES while session=2 remains live
```

The probe now proves the intended negative property for a live object: even when
client1 spoofs `requester_vmid=1`, proxy/client manager lookup returns
`-EACCES` instead of exposing client0's BO descriptor.

Raw vmshm RPC cross-session attack pass:

```text
command:
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=vmshm-2client-gles-isolation-rawrpc-kick-20260612-031721 \
  ./scripts/run/run-vmshm-2client-e2e.sh \
  --gles-compute-smoke \
  --skip-gles-remote-build \
  --gles-vmshm-isolation-probe \
  --gles-smoke-args '--count 64 --iterations 1 --warmup 0' \
  --gles-client-mem-mib 128 \
  --gles-proxy-mem-mib 384

run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-isolation-rawrpc-kick-20260612-031721

result:                         GLES_PASS
client0 holder:                 PANTHOR_BO_HOLD_SMOKE=PASS
client0 live session/BO:        session=2, payload=0x100000001, size=0x2000000
client1 raw DEV_QUERY:          VMSHM_RAW_RPC_CONSUMED, proxy denied lookup
client1 raw CLOSE_SESSION:      VMSHM_RAW_RPC_CONSUMED, proxy denied destroy
client1 raw marker:             VMSHM_RAW_RPC_RESULT=PASS
client1 lookup result:          VMSHM_LOOKUP_PROBE_INACCESSIBLE errno=13 (EACCES)
client1 isolation marker:       VMSHM_ISOLATION_RESULT=PASS
client1 GLES correctness:       COMPUTE_CHECK=PASS, Mali-G610 (Panfrost)
proxy evidence:
  SESSION_ACCESS_DENIED op=lookup session=2 owner_vmid=1 requester_vmid=2
  SESSION_ACCESS_DENIED op=destroy session=2 owner_vmid=1 requester_vmid=2
```

This proves the current session boundary is derived from the proxy comm channel
VMID, not from the raw message body or the client DRM frontend. A malicious
client1 can place forged requests in its own comm ring, but it cannot make the
proxy query or close a live client0 session, and client0's 60-second holder still
finishes normally after the attempted close-session attack.

32 MiB normal-path regression after adding the holder harness:

```text
run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-security-regression-20260612-024422

result:                 GLES_PASS
client0 iter_total avg: 27735.80 us
client1 iter_total avg: 27872.90 us
shared mean:            27804.35 us
host baseline:          25458.05 us
host/share:             0.916
```

The security harness therefore does not regress the already-passing 32 MiB
default performance path.

### Failed Design Blacklist

- Do not reuse proxy client1 object GPA `0x38000000` for variable-size object
  windows. It overlaps the client0 object window at the 224 MiB setting.
- Do not stream rootfs images into the remote tree with non-atomic coarse tar
  replacement. Use the runner's explicit `--sync-rootfs` atomic stream.
- Do not hard-code `session=1` when extracting a client0 payload handle.
  `gpu-smoke.sh` runs an optional basic IOCTL smoke first, so the live holder can
  be `session=2` or later. Extract sessions from `OPEN_SESSION ... owner_vmid=1`
  and then find a matching live BO payload.
- Do not depend on a newly rebuilt `gles-compute-smoke` for the hold window on
  the current RK3588 host. The target lacks `pkg-config`; use the static
  `panthor_ioctl_smoke --bo-hold` holder for this validation.
- Do not assume raw userspace `pwrite()` to `/dev/client_comm_vmshm` wakes the
  proxy in irq-notify mode. The proxy does not start the polling dispatcher when
  notify is enabled; use a normal client DRM ioctl as a doorbell kick after
  placing the raw request in the C2P queue.

## 2026-06-12: 32 MiB Shared GLES Auto-Affinity Performance Pass

### Goal

Bring the two-client shared-GPU 32 MiB GLES smoke above the required
`host/share >= 0.85` performance ratio, using the same workload size and timing
metric as the OpenCCA pmthor host baseline:

```text
workload:    --count 8388608, 32 MiB, 20 measured iterations, 5 warmup
metric:      host iter_total avg / shared two-client mean iter_total avg
pass gate:   GLES_PASS, COMPUTE_CHECK=PASS on both clients, host/share >= 0.85
```

### Bottleneck Analysis

The 2026-06-11 OpenCCA pmthor shared baseline ran the proxy VM, two client VMs,
and broker on a host booted with only CPUs `0-1` online:

```text
shared baseline:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-opencca-pmthor-20260611-234503

client0 iter_total avg: 48595.90 us
client1 iter_total avg: 52102.55 us
shared mean:            50349.23 us
host baseline:          25471.05 us
host/share:             0.506
```

The phase split showed that the expensive part was not GPU execution itself. The
dominant overhead was CPU-side client work and host scheduling pressure:

| phase | old shared mean | 4-CPU split mean |
| --- | ---: | ---: |
| cpu_prepare | 27267.55 us | 14610.85 us |
| buffer_upload | 14239.45 us | 6859.48 us |
| dispatch_call | 4335.95 us | 1632.25 us |
| memory_barrier | 90.23 us | 83.15 us |
| map_wait | 4409.58 us | 4054.55 us |
| unmap | 6.48 us | 2.90 us |
| iter_total | 50349.23 us | 27243.18 us |

This points at CPU placement and concurrent VM scheduling as the first-order
bottleneck. With only two host CPUs online, both clients were contending while
filling and uploading the 32 MiB buffer, and the proxy/broker path also shared
those CPUs.

### Passing Design

The shared two-client GLES runner now applies a default 4-CPU split when all of
the following are true:

- `--gles-compute-smoke` is active.
- `GLES_AUTO_AFFINITY=1`, the default.
- No explicit GLES CPU placement knobs were provided.

The default placement is:

```text
temporary host online CPUs: 0-3
broker:                     CPU 0
proxy Firecracker VM:        CPU 1
client0 Firecracker VM:      CPU 2
client1 Firecracker VM:      CPU 3
profile label:               auto-4cpu-split
```

The runner records the profile in `result`, `rootfs-prep.log`,
`memory-preflight.log`, and `affinity.log`, and restores the original online CPU
mask when the run exits. `--no-gles-auto-affinity` disables this default for
diagnostics or scheduler experiments.

Implementation:

```text
scripts/run/run-vmshm-2client-e2e.sh
```

### Verification

Manual 4-CPU diagnostic pass:

```text
run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-4cpu-affinity-20260612-005258

result:                 GLES_PASS
client0 iter_total avg: 27249.95 us
client1 iter_total avg: 27236.40 us
shared mean:            27243.18 us
host baseline:          25458.05 us
host/share:             0.934
speedup vs old shared:  1.85x
```

Default-command auto-affinity pass after the runner change:

```text
command:
REMOTE_HOST=192.168.31.18 REMOTE_PASS=root \
RUN_ID=vmshm-2client-gles-32m-autoaffinity-20260612-010111 \
  ./scripts/run/run-vmshm-2client-e2e.sh \
  --skip-sync \
  --skip-fetch-logs \
  --gles-compute-smoke \
  --skip-gles-remote-build \
  --gles-smoke-args '--count 8388608 --iterations 20 --warmup 5 --perf' \
  --gles-client-mem-mib 128 \
  --gles-proxy-mem-mib 384

run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-autoaffinity-20260612-010111

result:                 GLES_PASS
affinity profile:       auto-4cpu-split
client0 iter_total avg: 27311.35 us
client1 iter_total avg: 27453.75 us
shared mean:            27382.55 us
host baseline:          25458.05 us
host/share:             0.930
speedup vs old shared:  1.84x
post-run CPU online:    restored to 0-1
```

Host comparison baseline:

```text
run:
GPU-SFTP/log/passthrough/perf/gpu-host-32m-4cpu-baseline-20260612-005518

result:                 PASS
host renderer:          Mali-G610 (Panfrost)
host iter_total avg:    25458.05 us
```

The tested default path therefore meets the requested performance target:

```text
host/share = 25458.05 / 27382.55 = 0.930 >= 0.85
```

### Failed Design Blacklist

Do not use client BO cached mmap as the default 32 MiB optimization:

```text
run:
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-cached-diagnostic-20260612-005235

result:                 GLES_PASS
client0 iter_total avg: 50062.30 us
client1 iter_total avg: 52749.80 us
shared mean:            51406.05 us
host/share:             0.495
```

Although correctness passed, cached client BO mmap was slower than the old
write-combine path for this workload. Keep it blacklisted for the performance
default unless the data-plane is redesigned with explicit coherency and cache
maintenance support.

## 2026-06-03: BO_CREATE Control-Plane Foundation

### Goal

Move beyond the existing `OPEN_SESSION -> DEV_QUERY -> VM_CREATE -> VM_DESTROY`
surface by adding the first BO lifecycle boundary:

```text
client DRM_IOCTL_PANTHOR_BO_CREATE
  -> panthor-client BO_CREATE RPC
  -> panthor-proxy session BO table
  -> proxy vmshm payload object allocation
  -> real Panthor GEM BO create in the proxy session
  -> client-visible BO handle returned
```

This is intentionally the control-plane and lifetime foundation for BO
virtualization. It does not yet claim that client mmap pages and real Panthor GEM
pages are the same backing storage.

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_BO_CREATE_REQ/RSP` and
  `PANTHOR_VMSHM_MSG_BO_DESTROY_REQ/RSP` to the shared Panthor vmshm ABI.
- Kept client-visible BO handles local to the proxy session by allocating them
  from a proxy-side `xarray`. The client never receives the real proxy GEM handle
  as its UAPI handle.
- Added a proxy `struct panthor_proxy_bo` that records:
  - client BO handle
  - proxy GEM handle
  - vmshm payload object pointer
  - payload handle, offset, and allocation size
- Allocated a `PROXY_VMSHM_OBJ_GPU_BO` payload object for each BO. This is the
  future data-plane object that client `.mmap`, proxy VM_BIND, and readback
  should converge on.
- Added a real Panthor `panthor_vmshm_bo_create()` helper so proxy BO creation
  reuses the normal Panthor GEM creation path instead of hand-rolling a second
  GEM implementation in `panthor-proxy`.
- Added a client ioctl wrapper for `DRM_IOCTL_GEM_CLOSE` so client BO handles are
  destroyed through `BO_DESTROY` RPC instead of falling into the local DRM core
  GEM table, which does not own these virtual BO handles.

### Important Constraint Found

The current real Panthor GEM path uses `drm_gem_shmem_create()`. The newly
allocated vmshm payload object is therefore metadata/lifetime-correct, but it is
not yet the real GEM backing. This means the following remains unimplemented:

```text
client mmap writes payload pages
  -> proxy real GEM/VM_BIND maps the exact same pages
```

Until this is solved, `VM_BIND` and `GROUP_SUBMIT` must not be considered data
correct for client-written command streams or SSBOs.

### Short-Lived Wrong Direction

One considered design was to make `panthor_vmshm_session` own a full internal
`struct drm_file` via `drm_file_alloc()`/`drm_file_free()`. That would align well
with DRM GEM and syncobj namespaces, but those helpers are not exported for
ordinary driver modules. The implementation instead initializes only the GEM
handle `idr` fields that are required by exported GEM handle helpers.

### Tests

Kernel and smoke builds passed:

- `./scripts/build/build-guest-vmshm-kernels.sh`
  - Result: PASS
  - Installed role kernels under
    `GPU-SFTP/firecracker-bins/kernels/shared/{client,proxy}/Image`.
- `GPU-SFTP/tests/panthor-ioctl-smoke/build.sh`
  - Result: PASS
  - The binary is arm64; local execution on the x86 host produced the expected
    `Exec format error`.

BO lifecycle smoke passed:

```text
run id: vmshm-1client-bo-create-20260604-001114
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-bo-create-20260604-001114
result: PASS

PANTHOR_BASIC_SMOKE=PASS
panthor-client: VM_CREATE ...
panthor-client: BO_CREATE session=1 client_bo=1 proxy_bo=1 size=0x1000 payload=0x100000001 payload_size=0x1000
panthor-proxy: BO_CREATE session=1 client_bo=1 proxy_bo=1 size=0x1000 payload=0x100000001 payload_size=0x1000
panthor-client: BO_DESTROY session=1 client_bo=1 proxy_bo=1
panthor-proxy: BO_DESTROY session=1 client_bo=1 proxy_bo=1
PANTHOR_BO_CREATE_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=BO_CREATE_PASS
RESULT: PASS
```

VM_CREATE regression smoke also passed after the BO changes:

```text
run id: vmshm-1client-vm-create-regression-20260604-001213
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vm-create-regression-20260604-001213
result: PASS
```

### Known Risks

- `BO_CREATE` currently creates both a proxy real GEM object and a vmshm payload
  object, but they are not yet the same backing memory.
- `compat_ioctl` still goes through the normal DRM compat path; the first smoke
  target is 64-bit userspace.
- Session close now has to clean up any BO handles that userspace did not close.
  This path needs build and runtime verification.

## 2026-06-04: BO Lifecycle Stress And Session-Close Cleanup

### Goal

Strengthen the BO control-plane foundation before moving to `BO_MMAP_OFFSET`,
client `.mmap`, and `VM_BIND`.

The previous BO smoke proved one simple happy path:

```text
VM_CREATE -> BO_CREATE -> GEM_CLOSE/BO_DESTROY -> VM_DESTROY -> CLOSE_SESSION
```

This step validates more of the namespace and teardown semantics that Mesa will
exercise under normal operation:

```text
VM_CREATE
BO_CREATE x4
  - normal BO
  - NO_MMAP BO
  - exclusive_vm_id BO
  - exclusive_vm_id + NO_MMAP BO
GEM_CLOSE two BOs
GEM_CLOSE already-closed BO, expect failure
GEM_CLOSE invalid BO, expect failure
VM_DESTROY
CLOSE_SESSION, implicitly freeing two leftover BOs
```

### Design Decisions

- Added `--bo-lifecycle` to `GPU-SFTP/tests/panthor-ioctl-smoke`.
- The smoke creates four BOs with different sizes and flags so handle allocation,
  size alignment, `DRM_PANTHOR_BO_NO_MMAP`, and `exclusive_vm_id` translation all
  cross the client/proxy path in one run.
- The smoke explicitly closes BO handles 1 and 3, then deliberately leaves BO
  handles 2 and 4 open until `close(fd)`. This tests proxy session teardown as
  an intentional path rather than an accidental leak.
- The smoke checks that a second close of handle 1 and a close of an invalid
  large handle fail with normal ioctl failure. This protects the proxy `xarray`
  namespace from silently accepting stale or bogus client handles.
- Added `--bo-lifecycle-smoke` to `scripts/run/run-vmshm-e2e.sh`, including
  mode selection in the guest init script, PASS markers, proxy/client log gates,
  and result summary extraction.
- Added a proxy release log:

```text
panthor-proxy: SESSION_RELEASE session=N leftover_bos=X leftover_vms=Y
```

This is only emitted when cleanup has leftover resources. It gives the test a
direct signal that `CLOSE_SESSION` performed the intended BO cleanup.

### Tests

Local checks and builds:

- `bash -n scripts/run/run-vmshm-e2e.sh`
  - Result: PASS
- `GPU-SFTP/tests/panthor-ioctl-smoke/build.sh`
  - Result: PASS
  - Installed `GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke`.
- `./scripts/build/build-guest-vmshm-kernels.sh`
  - Result: PASS
  - Installed updated client/proxy role kernels under
    `GPU-SFTP/firecracker-bins/kernels/shared/{client,proxy}/Image`.

Remote one-proxy-one-client BO lifecycle smoke:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --bo-lifecycle-smoke \
  --run-id vmshm-1client-bo-lifecycle-20260604-002327

run id: vmshm-1client-bo-lifecycle-20260604-002327
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-bo-lifecycle-20260604-002327
result: PASS
```

Key client evidence:

```text
PANTHOR_BASIC_SMOKE=PASS
VM_CREATE id=1 user_va_range=0x800000000000
BO_CREATE[0] handle=1 size=0x1000 flags=0x0 exclusive_vm_id=0
BO_CREATE[1] handle=2 size=0x2000 flags=0x1 exclusive_vm_id=0
BO_CREATE[2] handle=3 size=0x3000 flags=0x0 exclusive_vm_id=1
BO_CREATE[3] handle=4 size=0x4000 flags=0x1 exclusive_vm_id=1
GEM_CLOSE[0] handle=1
GEM_CLOSE[2] handle=3
GEM_CLOSE_DOUBLE handle=1 expected_failure errno=22 (Invalid argument)
GEM_CLOSE_INVALID handle=2147483646 expected_failure errno=22 (Invalid argument)
VM_DESTROY id=1
PANTHOR_BO_LIFECYCLE_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=BO_LIFECYCLE_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: BO_CREATE session=1 client_bo=1 proxy_bo=1 size=0x1000 payload=0x100000001 payload_size=0x1000
panthor-proxy: BO_CREATE session=1 client_bo=2 proxy_bo=2 size=0x2000 payload=0x200000002 payload_size=0x2000
panthor-proxy: BO_CREATE session=1 client_bo=3 proxy_bo=3 size=0x3000 payload=0x300000003 payload_size=0x4000
panthor-proxy: BO_CREATE session=1 client_bo=4 proxy_bo=4 size=0x4000 payload=0x400000004 payload_size=0x4000
panthor-proxy: BO_DESTROY session=1 client_bo=1 proxy_bo=1
panthor-proxy: BO_DESTROY session=1 client_bo=3 proxy_bo=3
panthor-proxy: BO_DESTROY session=1 client_bo=1 ret=-22
panthor-proxy: BO_DESTROY session=1 client_bo=2147483646 ret=-22
panthor-proxy: VM_DESTROY session=1 client_vm=1 proxy_vm=1
panthor-proxy: SESSION_RELEASE session=1 leftover_bos=2 leftover_vms=0
panthor-proxy: CLOSE_SESSION session=1
RESULT: PASS
```

### What This Proves

- Client-visible BO handles are allocated as a live per-session namespace and do
  not collide while live.
- `exclusive_vm_id` survives client-to-proxy translation for BO creation.
- `DRM_PANTHOR_BO_NO_MMAP` is accepted and carried through BO creation.
- Explicit `GEM_CLOSE` uses the `BO_DESTROY` RPC path.
- Stale and invalid BO handles are rejected instead of being silently accepted.
- `CLOSE_SESSION` releases BOs that userspace did not explicitly close.

### Remaining Risks

- This still does not prove data-plane correctness. The proxy real GEM BO and
  vmshm payload object are still separate backing objects.
- `BO_MMAP_OFFSET`, client `.mmap`, and real proxy VM_BIND to shared backing are
  still the next major correctness boundary.
- `compat_ioctl` is still not intercepted for virtual `GEM_CLOSE`; all current
  smoke tests use 64-bit userspace.

## 2026-06-04: BO_MMAP_OFFSET And Client Payload mmap POC

### Goal

Validate the first client-visible data-plane boundary without yet claiming GPU
execution correctness:

```text
BO_CREATE
  -> proxy allocates vmshm-object payload memory
  -> client looks up the payload descriptor through client_vmshm_manager
  -> BO_MMAP_OFFSET returns a client-local fake mmap offset
  -> client .mmap maps vmshm-object pages into userspace
  -> userspace writes and reads the mapped bytes
```

The important design boundary is the two-memslot split:

- `vmshm-comm` carries the control RPCs and metadata:
  `BO_CREATE`, `BO_DESTROY`, returned handles, sizes, payload handles, and
  status codes.
- `vmshm-object` carries only the BO payload bytes that client userspace can
  directly map and access.

This matches the long-term rule that only BO payloads or other structures the
client VM genuinely needs to mmap/read/write should use the object memslot.
Transient ioctl control arrays should stay in the comm/control path unless a
future measured payload-size limit forces a dedicated transfer design.

### Design Decisions

- Added local BO metadata to `panthor-client`:
  - client-visible BO handle
  - proxy GEM handle
  - vmshm payload handle, offset, allocation size, and descriptor
  - client fake mmap offset
  - BO flags and refcount/lifetime state
- `BO_CREATE` now rolls back the proxy BO with `BO_DESTROY` if the client cannot
  allocate local metadata or cannot resolve the returned payload descriptor.
- `BO_MMAP_OFFSET` returns a client-local fake offset beginning at
  `1ULL << 32`. It does not expose the proxy DRM fake mmap offset.
- `.mmap` translates that fake offset to the BO payload object and maps the
  payload GPA with `remap_pfn_range()`.
- `DRM_PANTHOR_BO_NO_MMAP` is rejected by `BO_MMAP_OFFSET` and by `.mmap`.
- BO metadata survives an mmap VMA through VMA open/close refcounts. If userspace
  closes a BO while a mapping is still live, proxy destruction is delayed until
  the mapping reference is released.
- Panthor MMIO/flush-id mmap is still rejected with `-EOPNOTSUPP`; it remains a
  separate required path before Mesa userspace driver execution.

### Tests

Local checks and builds passed:

- `bash -n scripts/run/run-vmshm-e2e.sh`
  - Result: PASS
- `GPU-SFTP/tests/panthor-ioctl-smoke/build.sh`
  - Result: PASS
- `./scripts/build/build-guest-vmshm-kernels.sh`
  - Result: PASS

Remote one-proxy-one-client BO mmap smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --bo-mmap-smoke \
  --run-id vmshm-1client-bo-mmap-formatfix-20260604-004254

run id: vmshm-1client-bo-mmap-formatfix-20260604-004254
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-bo-mmap-formatfix-20260604-004254
result: PASS
```

Key client evidence:

```text
BO_MMAP_OFFSET handle=1 offset=0x100000000
panthor-client: MMAP ... payload_gpa=0x0000000023e00000
BO_MMAP_RW handle=1 word0=0x13579bdf word1=0x2468ace0
BO_MMAP_OFFSET_NO_MMAP ... expected_failure errno=22
PANTHOR_BO_MMAP_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=BO_MMAP_PASS
PANTHOR_IOCTL_INIT=PASS
```

### What This Proves

- Client userspace can obtain a Panthor-style BO mmap offset and use it on the
  client DRM fd.
- The fake offset is local to the client frontend and maps the intended
  `vmshm-object` payload, not a proxy DRM VMA namespace.
- Client CPU writes and reads reach the payload object memory.
- `NO_MMAP` BOs are correctly prevented from acquiring a CPU mmap offset.

### Remaining Risks

- This does not prove GPU data-plane correctness. The current proxy real GEM BO
  and vmshm payload object are still separate backing objects.
- `VM_BIND` may be made control-path correct next, but `GROUP_SUBMIT` cannot be
  considered command-stream/SSBO correct until real GEM/VM_BIND maps the exact
  same pages that client userspace mapped through `vmshm-object`.
- Flush-id MMIO mmap remains unimplemented.

## 2026-06-04: Synchronous VM_BIND Control-Plane POC

### Goal

Add the next narrow ioctl boundary after BO creation and client payload mmap:

```text
VM_CREATE
BO_CREATE
VM_BIND MAP
VM_BIND UNMAP
GEM_CLOSE
VM_DESTROY
```

This step is intentionally scoped to synchronous `DRM_IOCTL_PANTHOR_VM_BIND`
with small flattened op arrays. It proves that the client/proxy handle and VM
translation path can reach the real proxy-side Panthor VM_BIND helper. It does
not yet claim that client-written `vmshm-object` payload pages are the pages
mapped into the GPU page table.

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_VM_BIND_REQ/RSP` to the Panthor vmshm ABI.
- The VM_BIND request is fixed-size and carries at most
  `PANTHOR_VMSHM_MAX_VM_BIND_OPS == 8` operations. This keeps the ioctl control
  array in `vmshm-comm`, which is the right memslot for transient ioctl
  metadata.
- The `vmshm-object` memslot is not used for VM_BIND op arrays. It remains
  reserved for BO payload/shared objects or future client-visible structures
  that actually need CPU mmap/read/write semantics.
- The POC rejects:
  - `DRM_PANTHOR_VM_BIND_ASYNC`
  - nested `syncs[]` on VM_BIND ops
  - `SYNC_ONLY` ops
  - op counts above the fixed comm-payload limit
- MAP ops translate:
  - client VM id to proxy VM id
  - client BO handle to proxy GEM handle
  - `va`, `bo_offset`, `size`, and mapping flags unchanged
- UNMAP ops preserve Panthor UAPI semantics: `bo_handle == 0` and
  `bo_offset == 0`, with `va` and `size` unchanged.
- `panthor-client` pins mapped BO metadata references while the VM_BIND RPC is
  in flight, so a same-fd concurrent `GEM_CLOSE` cannot immediately free the
  proxy BO behind the request.
- Added `panthor_vmshm_vm_bind()` in real Panthor so the proxy path reuses
  `panthor_vm_bind_exec_sync_op()` rather than duplicating Panthor GPUVA logic.

### Passthrough Constraint

The proxy VM uses the custom GPU passthrough stack, not ordinary bare-metal
Panthor. A successful proxy `VM_BIND` eventually enters the passthrough
page-table path:

```text
proxy real Panthor VM_BIND
  -> panthor_vm_map_pages()
  -> custom ARM_64_PANATHOR_LPAE_S1 io-pgtable
  -> GPA_TO_HPA hypercall
  -> GPU-visible PTEs contain HPA
```

Therefore future data-plane VM_BIND work must preserve these passthrough rules:

- GPU TTBR/root table, non-leaf descriptors, and leaf PTEs must contain HPA,
  not GPA.
- Map/unmap must remain correct at 4 KiB granularity because guest-contiguous
  GPA does not imply host-contiguous HPA.
- IRQ/fence validation for later `GROUP_SUBMIT` depends on the pmthor
  irqfd/resamplefd completion path; submit success alone is not GPU completion.

### Local Checks

These local checks passed before remote execution:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

The kernel build installed updated role images:

```text
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

### Remote Test

Remote one-proxy-one-client VM_BIND smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --vm-bind-smoke \
  --run-id vmshm-1client-vm-bind-20260604-010641

run id: vmshm-1client-vm-bind-20260604-010641
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vm-bind-20260604-010641
result: PASS
```

Key client evidence:

```text
PANTHOR_BASIC_SMOKE=PASS
VM_CREATE id=1 user_va_range=0x800000000000
BO_CREATE_BIND handle=1 size=0x1000
panthor-client: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1
VM_BIND_MAP vm=1 bo=1 va=0x100000 size=0x1000
panthor-client: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1
VM_BIND_UNMAP vm=1 va=0x100000 size=0x1000
GEM_CLOSE handle=1
VM_DESTROY id=1
PANTHOR_VM_BIND_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=VM_BIND_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: VM_CREATE session=1 client_vm=1 proxy_vm=1 user_va_range=0x800000000000
panthor-proxy: BO_CREATE session=1 client_bo=1 proxy_bo=1 size=0x1000 payload=0x100000001 payload_size=0x1000
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
panthor-proxy: BO_DESTROY session=1 client_bo=1 proxy_bo=1
panthor-proxy: VM_DESTROY session=1 client_vm=1 proxy_vm=1
panthor-proxy: CLOSE_SESSION session=1
RESULT: PASS
```

### What This Proves

- Client userspace can issue a synchronous Panthor VM_BIND ioctl to the virtual
  client DRM node.
- Client VM id and BO handles are translated through the proxy session namespace.
- Proxy-side VM_BIND reaches the real Panthor VM_BIND sync helper and returns
  success for both MAP and UNMAP.
- The result path preserves Panthor sync failure semantics by carrying
  `failed_op`; success uses `PANTHOR_VMSHM_VM_BIND_FAILED_OP_NONE`.
- The control array belongs in `vmshm-comm`; no object-memslot misuse was
  introduced for transient ioctl metadata.

### Current Limitation

This is still a control-plane POC. The proxy real GEM object and the
`vmshm-object` payload object are separate backing allocations today. That means
this VM_BIND path can validate:

```text
client handles -> proxy handles -> real Panthor VM_BIND call
```

but it cannot yet validate:

```text
client mmap writes vmshm-object payload
  -> proxy VM_BIND maps those exact same pages
  -> GPU reads/writes the client-visible payload
```

The next VM_BIND design step must either make real Panthor GEM backing come from
the vmshm payload pages or introduce a proven import/registration path that
maps the exact shared backing into the proxy real GEM.

## 2026-06-04: VM_GET_STATE And Flush-ID mmap

### Goal

Fill two small but Mesa-visible gaps before moving into syncobj and submit
virtualization:

```text
VM_CREATE
VM_GET_STATE
mmap(DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET)
VM_DESTROY
```

`VM_GET_STATE` proves another VM-lifetime ioctl can cross the client/proxy
handle namespace. The flush-id mmap proves the client Panthor frontend can
serve the special Panthor user MMIO page without exposing real GPU MMIO to the
client VM.

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_VM_GET_STATE_REQ/RSP` to the Panthor vmshm ABI.
- Kept `VM_GET_STATE` entirely in `vmshm-comm`:
  - request carries `session_id` and `client_vm_id`
  - proxy translates `client_vm_id -> proxy_vm_id`
  - response carries `ret`, `proxy_vm_id`, and Panthor VM state
- Added `panthor_vmshm_vm_get_state()` in the real Panthor driver. It reuses the
  same VM lookup and `panthor_vm_is_unusable()` state decision as the normal
  `DRM_IOCTL_PANTHOR_VM_GET_STATE` path.
- Added client and proxy logs:

```text
panthor-client: VM_GET_STATE session=N client_vm=X proxy_vm=Y state=S
panthor-proxy: VM_GET_STATE session=N client_vm=X proxy_vm=Y state=S ret=R
```

- Added a client-side flush-id dummy page:
  - one zeroed kernel page allocated at `panthor-client` init
  - mapped only for `DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET`
  - requires `MAP_SHARED`, exactly one page, and no write/exec VMA flags
  - maps read-only via `vm_insert_page()`
  - clears `VM_MAYWRITE`
- The dummy flush-id value is deliberately `0`. This is conservative for the
  virtualized path: userspace may over-flush, but it should not incorrectly skip
  a required flush by observing a value newer than the proxy/GPU reality.

### Two-Memslot Boundary

This step does not use `vmshm-object`.

- `VM_GET_STATE` is pure control-plane metadata and belongs in `vmshm-comm`.
- The flush-id page is a local client frontend dummy page. It is not a BO, not a
  proxy-shared payload, and not something the proxy or physical GPU must access.

This preserves the project rule that `vmshm-object` is reserved for BO payloads
or other client-visible shared objects with real mmap/read/write data-plane
semantics.

### Local Checks

These checks passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

The kernel build installed updated role images:

```text
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

### Remote Test

Remote one-proxy-one-client VM state/flush-id smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --vm-state-flush-smoke \
  --run-id vmshm-1client-vm-state-flush-20260604-012031

run id: vmshm-1client-vm-state-flush-20260604-012031
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vm-state-flush-20260604-012031
result: PASS
```

Key client evidence:

```text
PANTHOR_BASIC_SMOKE=PASS
VM_CREATE id=1 user_va_range=0x800000000000
panthor-client: VM_GET_STATE session=1 client_vm=1 proxy_vm=1 state=0
VM_GET_STATE vm=1 state=0
panthor-client: MMAP_FLUSH_ID offset=0x100000000000000 size=0x1000 value=0x00000000
MMAP_FLUSH_ID offset=0x100000000000000 value=0x00000000
MUNMAP_FLUSH_ID
VM_DESTROY id=1
PANTHOR_VM_STATE_FLUSH_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=VM_STATE_FLUSH_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: VM_CREATE session=1 client_vm=1 proxy_vm=1 user_va_range=0x800000000000
panthor-proxy: VM_GET_STATE session=1 client_vm=1 proxy_vm=1 state=0 ret=0
panthor-proxy: VM_DESTROY session=1 client_vm=1 proxy_vm=1
panthor-proxy: CLOSE_SESSION session=1
RESULT: PASS
```

### What This Proves

- The client can issue `DRM_IOCTL_PANTHOR_VM_GET_STATE` to the virtual Panthor
  node and receive `DRM_PANTHOR_VM_STATE_USABLE`.
- The proxy session VM namespace is used; the client never sees or depends on a
  raw proxy VM id even though the single-client POC currently allocates matching
  ids.
- The client Panthor frontend can satisfy the special flush-id mmap path without
  real client-side GPU MMIO.
- No object-memslot misuse was introduced for control-only state or virtual MMIO
  dummy data.

### Remaining Risks

- The flush-id page is intentionally conservative and static. It does not yet
  mirror the real proxy latest-flush register/page.
- A static zero page may increase flush traffic when Mesa starts submitting real
  workloads. That is acceptable for correctness bring-up, but should be measured
  when moving to performance work.
- This step does not change the larger data-plane limitation: proxy real GEM
  backing and client-visible `vmshm-object` payload backing are still separate.

## 2026-06-04: SYNCOBJ_CREATE/DESTROY Lifecycle Mirror

### Goal

Add the first DRM core syncobj virtualization boundary after BO/VM work:

```text
client DRM_IOCTL_SYNCOBJ_CREATE
  -> panthor-client virtual syncobj handle
  -> vmshm control RPC
  -> panthor-proxy session syncobj table
  -> real proxy Panthor drm_file syncobj handle

client DRM_IOCTL_SYNCOBJ_DESTROY
  -> remove client-visible handle
  -> destroy/drop the real proxy syncobj handle
```

This is a lifecycle and namespace step only. It does not yet wait on GPU fences
or signal GPU completion back to the client.

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_SYNCOBJ_CREATE_REQ/RSP` and
  `PANTHOR_VMSHM_MSG_SYNCOBJ_DESTROY_REQ/RSP` to the Panthor vmshm ABI.
- Kept syncobj messages entirely in `vmshm-comm`; they carry only control
  metadata and handles.
- Did not create authoritative local DRM core syncobjs in `panthor-client`.
  The proxy real syncobj is authoritative because future Panthor submit fences
  are signaled by the real proxy driver.
- Added proxy-side `client_syncobj_handle -> proxy_syncobj_handle` mapping under
  each `panthor_proxy_session`.
- Added real Panthor helpers using exported DRM syncobj primitives:
  `drm_syncobj_create()`, `drm_syncobj_get_handle()`, and direct idr removal for
  destroy.
- Avoided `drm_internal.h` and the static DRM core ioctl wrappers from driver
  code. This remains a blacklisted direction for Panthor vmshm helpers.
- Avoided calling `drm_syncobj_open()`/`drm_syncobj_release()` directly because
  they are not exported for ordinary driver use. The vmshm session initializes
  `syncobj_idr` and `syncobj_table_lock` directly and releases remaining idr
  entries on session close.

### Tests

Local checks passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

Remote one-proxy-one-client syncobj lifecycle smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --syncobj-lifecycle-smoke \
  --run-id vmshm-1client-syncobj-lifecycle-20260604-013041

run id: vmshm-1client-syncobj-lifecycle-20260604-013041
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-lifecycle-20260604-013041
result: PASS
```

Key evidence:

```text
SYNCOBJ_CREATE[0] handle=1 flags=0x0
SYNCOBJ_CREATE[1] handle=2 flags=0x1
SYNCOBJ_DESTROY[0] handle=1
SYNCOBJ_DESTROY_DOUBLE handle=1 expected_failure errno=22
SYNCOBJ_DESTROY[1] handle=2
PANTHOR_SYNCOBJ_LIFECYCLE_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=SYNCOBJ_LIFECYCLE_PASS

panthor-proxy: SYNCOBJ_CREATE session=1 client_sync=1 proxy_sync=1 flags=0x0
panthor-proxy: SYNCOBJ_CREATE session=1 client_sync=2 proxy_sync=2 flags=0x1
panthor-proxy: SYNCOBJ_DESTROY session=1 client_sync=1 proxy_sync=1
panthor-proxy: SYNCOBJ_DESTROY session=1 client_sync=2 proxy_sync=2
```

After adding `SYNCOBJ_WAIT`, a regression run also passed:

```text
run id: vmshm-1client-syncobj-lifecycle-regression-20260604-015717
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-lifecycle-regression-20260604-015717
result: PASS
```

### Remaining Risks

- This lifecycle mirror alone does not implement wait/transfer/timeline wait.
- `compat_ioctl` still needs equivalent virtual-handle interception before
  32-bit userspace is considered supported.

## 2026-06-04: SYNCOBJ_WAIT Binary Poll Path

### Goal

Add the first sync wait boundary:

```text
client DRM_IOCTL_SYNCOBJ_WAIT
  -> copy handles[] from client userspace
  -> keep handles[] in vmshm-comm as flattened control metadata
  -> proxy translates client syncobj handles to real proxy syncobj handles
  -> real Panthor vmshm session waits using DRM core syncobj semantics
  -> first_signaled/ret returned to client userspace
```

This step proves that client waits can observe proxy real syncobj state. It is
not yet the long blocking wait path needed for GPU submit completion.

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_SYNCOBJ_WAIT_REQ/RSP`.
- Added fixed `PANTHOR_VMSHM_MAX_SYNCOBJ_WAIT_HANDLES == 16`. This keeps the
  handle array in the 512-byte `vmshm-comm` message budget.
- Did not use `vmshm-object` for wait handles. They are transient ioctl control
  metadata, not client-visible mmap/read/write payload.
- Client converts the userspace absolute `CLOCK_MONOTONIC` timeout into a
  relative duration before RPC. The proxy converts that relative duration back
  into its own local absolute timeout before calling DRM wait helpers. This
  avoids interpreting a client VM monotonic timestamp in the proxy VM clock
  domain.
- Added `drm_syncobj_wait_handles()` as a small exported DRM helper so Panthor
  vmshm can reuse the existing DRM core `WAIT_ALL`, `WAIT_FOR_SUBMIT`, and
  `WAIT_DEADLINE` validation/wait semantics without copying the static DRM wait
  state machine into Panthor.
- Added client/proxy syncobj refcounts and `destroy_pending` handling so an
  in-flight wait keeps the virtual syncobj mapping alive while another thread
  destroys the same handle.
- Added legacy userspace ioctl number support for older rootfs DRM headers whose
  `struct drm_syncobj_wait` does not yet include `deadline_nsec`. Without this,
  wait fell through to the local DRM core path and returned `-ENOENT`.

### Failed Direction Removed

The first test run failed because the rootfs userspace binary used the old
`DRM_IOCTL_SYNCOBJ_WAIT` encoding (`0xc02864c3`), while the guest kernel UAPI
has the newer structure with `deadline_nsec`. The old request bypassed
`panthor-client`'s new ioctl comparison and landed in local DRM core, producing:

```text
SYNCOBJ_WAIT[0] failed: No such file or directory
```

That mismatch was fixed by explicitly recognizing the legacy wait ioctl number
and translating it into the current in-kernel wait structure. The broken
"current ioctl number only" assumption is blacklisted for DRM core ioctls that
have had structure-size changes; future syncobj/timeline/fd ioctls must check
the rootfs UAPI encoding before assuming one command number is enough.

### Tests

Local checks passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

The final one-proxy-one-client syncobj wait smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --syncobj-wait-smoke \
  --run-id vmshm-1client-syncobj-wait-logclean-20260604-015843

run id: vmshm-1client-syncobj-wait-logclean-20260604-015843
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-wait-logclean-20260604-015843
result: PASS
```

Key client evidence:

```text
SYNCOBJ_CREATE_WAIT[0] handle=1 flags=0x1
SYNCOBJ_CREATE_WAIT[1] handle=2 flags=0x1
SYNCOBJ_CREATE_WAIT_UNSIGNALED handle=3 flags=0x0
panthor-client: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0
SYNCOBJ_WAIT[0] count=1 flags=0x0 first=0
panthor-client: SYNCOBJ_WAIT session=1 count=2 flags=0x1 first=0
SYNCOBJ_WAIT_ALL count=2 flags=0x1 first=0
SYNCOBJ_WAIT_UNSIGNALED_POLL expected_failure errno=22
SYNCOBJ_WAIT_INVALID expected_failure errno=2
PANTHOR_SYNCOBJ_WAIT_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=SYNCOBJ_WAIT_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=2 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=4294967295 ret=-22
RESULT: PASS
```

### Current Limitations

- The smoke intentionally exercises poll/ready paths only. Long blocking waits
  are not yet reliable because `client_comm_vmshm_call()` currently has a fixed
  one-second synchronous RPC timeout. GPU submit completion will need either a
  longer/call-specific wait timeout or an asynchronous wait/completion path.
- Timeline wait and syncobj transfer are implemented in later sections.
- The userspace smoke rootfs has older DRM syncobj headers, so
  `WAIT_DEADLINE` is implemented in kernel but not covered by this smoke.
- The proxy still depends on the custom passthrough IRQ path for real GPU fence
  completion. This wait path has not yet proven `GROUP_SUBMIT -> physical GPU
  IRQ -> proxy fence signal -> client wait`.

## 2026-06-04: SYNCOBJ_TRANSFER Binary And Timeline Fence Copy

### Goal

Add syncobj fence transfer after create/destroy/wait:

```text
client DRM_IOCTL_SYNCOBJ_TRANSFER
  -> translate client src/dst syncobj handles
  -> keep src_point/dst_point/flags in vmshm-comm
  -> proxy translates to real syncobj handles
  -> real DRM syncobj transfer moves/copies the proxy fence
```

This is required because Panthor and Mesa commonly move a binary submit fence
into a timeline point before waiting from userspace.

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_SYNCOBJ_TRANSFER_REQ/RSP`.
- Kept transfer entirely in `vmshm-comm`; it carries only handles, points,
  flags, and status.
- Did not use `vmshm-object`. Transfer arrays and handles are transient ioctl
  control metadata, not client-visible mmap/read/write data.
- Client validates both virtual syncobj handles locally and keeps references
  while the RPC is in flight.
- Proxy translates both handles to authoritative real DRM syncobjs before
  calling the real Panthor vmshm helper.
- Added/exported a small DRM helper around the existing core transfer logic
  rather than copying DRM core's static transfer implementation into Panthor.

### Tests

Remote one-proxy-one-client syncobj transfer smoke passed before the timeline
wait work:

```text
run id: vmshm-1client-syncobj-transfer-regression-20260604-015928
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-transfer-regression-20260604-015928
result: PASS
```

The later timeline-wait smoke also covered timeline transfer to points 7 and
11:

```text
panthor-proxy: SYNCOBJ_TRANSFER session=1 src=1 dst=3 src_point=0 dst_point=7 flags=0x0 ret=0
panthor-proxy: SYNCOBJ_TRANSFER session=1 src=2 dst=4 src_point=0 dst_point=11 flags=0x0 ret=0
SYNCOBJ_TRANSFER_TIMELINE[0] src=1 dst=3 src_point=0 dst_point=7 flags=0x0
SYNCOBJ_TRANSFER_TIMELINE[1] src=2 dst=4 src_point=0 dst_point=11 flags=0x0
```

### Remaining Risks

- This proves proxy syncobj namespace correctness, not GPU fence completion.
- Real submit completion still depends on the proxy VM passthrough IRQ path and
  later `GROUP_SUBMIT` wiring.

## 2026-06-04: SYNCOBJ_TIMELINE_WAIT

### Goal

Add timeline wait support after binary wait and transfer:

```text
client DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT
  -> copy handles[] and points[] from userspace
  -> validate virtual syncobj handles locally
  -> keep handles[] and points[] in vmshm-comm
  -> proxy translates handles to real syncobjs
  -> real DRM timeline wait observes proxy real fence state
```

### Design Decisions

- Added `PANTHOR_VMSHM_MSG_SYNCOBJ_TIMELINE_WAIT_REQ/RSP`.
- Reused `PANTHOR_VMSHM_MAX_SYNCOBJ_WAIT_HANDLES == 16` for the fixed-size
  control message.
- Kept both `handles[]` and `points[]` in `vmshm-comm`. These arrays are
  transient ioctl control metadata and must not consume the object memslot.
- Preserved all timeline points exactly. The proxy only translates handles.
- Client converts userspace absolute monotonic timeout/deadline to relative
  durations before RPC; proxy converts them into its local absolute clock
  domain.
- Added an exported `drm_syncobj_timeline_wait_handles()` helper so Panthor
  vmshm reuses DRM core timeline wait semantics without copying the static wait
  state machine.
- Added legacy ioctl encoding support for rootfs headers where
  `struct drm_syncobj_timeline_wait` is smaller than the guest kernel UAPI
  version with `deadline_nsec`.

### Tests

Local checks passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

Final remote one-proxy-one-client timeline wait smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --syncobj-timeline-wait-smoke \
  --run-id vmshm-1client-syncobj-timeline-wait-20260604-023036

run id: vmshm-1client-syncobj-timeline-wait-20260604-023036
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-timeline-wait-20260604-023036
result: PASS
```

Key client evidence:

```text
SYNCOBJ_TRANSFER_TIMELINE[0] src=1 dst=3 src_point=0 dst_point=7 flags=0x0
SYNCOBJ_TRANSFER_TIMELINE[1] src=2 dst=4 src_point=0 dst_point=11 flags=0x0
SYNCOBJ_TIMELINE_WAIT[0] handle=3 point=7 flags=0x0 first=0
SYNCOBJ_TIMELINE_WAIT_AVAILABLE[0] handle=3 point=7 first=0
SYNCOBJ_TIMELINE_WAIT_ALL count=2 flags=0x1 first=0
SYNCOBJ_TIMELINE_WAIT_AVAILABLE_EMPTY expected_failure errno=62
SYNCOBJ_TIMELINE_WAIT_MISSING_POINT expected_failure errno=22
SYNCOBJ_TIMELINE_WAIT_INVALID expected_failure errno=2
PANTHOR_SYNCOBJ_TIMELINE_WAIT_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=SYNCOBJ_TIMELINE_WAIT_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x0 first=0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x4 first=0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=2 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x4 first=4294967295 ret=-62
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x0 first=4294967295 ret=-22
```

### Failed Direction Removed And Blacklisted

The first timeline-wait run failed before any Panthor ioctl reached the proxy:

```text
run id: vmshm-1client-syncobj-timeline-wait-20260604-022629
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-timeline-wait-20260604-022629
symptom: proxy never printed "panthor-proxy: vmshm handler registered";
         client DEV_QUERY timed out with -110.
```

Root cause: `PROXY_COMM_VMSHM_MAX_HANDLERS == 16` was too small after adding
Panthor ioctl handlers on top of the existing selftest/perf/manager handlers.
Proxy handler registration failed and `panthor_proxy_init()` rolled back before
the Panthor handlers became available.

Blacklist:

- Do not assume 16 proxy-comm handler slots are enough. The control transport
  must size handler registration for the full manager/selftest/Panthor ioctl
  surface, with registration failure logged clearly.
- Do not assume "current ioctl number only" for DRM core syncobj ioctls whose
  structs have changed across rootfs/kernel headers. Check the userspace rootfs
  UAPI encoding when adding virtualized syncobj commands.

### Remaining Risks

- Timeline wait currently proves proxy real syncobj state transitions, not real
  GPU job completion.
- Long GPU waits still need the `client_comm_vmshm_call()` timeout/asynchronous
  completion design before relying on waits for submitted GPU work.
- Eventfd/fd import/export remain deliberately unimplemented because cross-VM
  fd numbers cannot be forwarded directly.

## 2026-06-04: SYNCOBJ_RESET/SIGNAL/TIMELINE_SIGNAL/QUERY

### Goal

Finish the remaining low-risk DRM syncobj state-control ioctls before moving
from synchronization control-plane work to Panthor group/submit work:

```text
SYNCOBJ_SIGNAL
  -> make proxy real binary syncobj signaled

SYNCOBJ_RESET
  -> clear proxy real binary syncobj fence

SYNCOBJ_TIMELINE_SIGNAL
  -> attach proxy real stub fences to timeline points

SYNCOBJ_QUERY
  -> return proxy real timeline point state to client userspace
```

### Design Decisions

- Added vmshm messages:
  - `PANTHOR_VMSHM_MSG_SYNCOBJ_RESET_REQ/RSP`
  - `PANTHOR_VMSHM_MSG_SYNCOBJ_SIGNAL_REQ/RSP`
  - `PANTHOR_VMSHM_MSG_SYNCOBJ_TIMELINE_SIGNAL_REQ/RSP`
  - `PANTHOR_VMSHM_MSG_SYNCOBJ_QUERY_REQ/RSP`
- Kept all four ioctls entirely in `vmshm-comm`.
  - `handles[]` and `points[]` are flattened into fixed-size RPC messages.
  - No `vmshm-object` usage was added because these arrays are transient ioctl
    control metadata, not client-visible mmap/read/write payload.
- Reused `PANTHOR_VMSHM_MAX_SYNCOBJ_WAIT_HANDLES == 16` for the state-control
  arrays to keep the ABI bounded.
- Client validates virtual syncobj handles locally and holds references across
  the RPC.
- Proxy translates client syncobj handles to real proxy syncobj handles and
  keeps mapping references while calling the real Panthor vmshm helper.
- Added exported DRM helpers for kernel arrays:
  - `drm_syncobj_reset_handles()`
  - `drm_syncobj_signal_handles()`
  - `drm_syncobj_timeline_signal_handles()`
  - `drm_syncobj_query_handles()`
- The Panthor vmshm helpers call those exported DRM helpers instead of including
  `drm_internal.h` or copying DRM core ioctl bodies.
- `SYNCOBJ_QUERY` treats `points[]` as output-only on the client side. The
  client does not pre-read the user output buffer.
- `SYNCOBJ_TIMELINE_SIGNAL` preserves DRM core's `flags == 0` requirement.

### Tests

Local checks/builds passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

Final new smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --syncobj-signal-query-smoke \
  --run-id vmshm-1client-syncobj-signal-query-20260604-024933

run id: vmshm-1client-syncobj-signal-query-20260604-024933
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-syncobj-signal-query-20260604-024933
result: PASS
```

Key client evidence:

```text
SYNCOBJ_SIGNAL_BINARY handle=1
SYNCOBJ_WAIT_AFTER_SIGNAL handle=1 first=0
SYNCOBJ_RESET_BINARY handle=1
SYNCOBJ_WAIT_AFTER_RESET expected_failure errno=22
SYNCOBJ_SIGNAL_INVALID expected_failure errno=2
SYNCOBJ_TIMELINE_SIGNAL count=2 point0=5 point1=9
SYNCOBJ_TIMELINE_WAIT_AFTER_SIGNAL count=2 first=0
SYNCOBJ_QUERY count=2 point0=5 point1=9
SYNCOBJ_QUERY_LAST_SUBMITTED count=2 point0=5 point1=9
SYNCOBJ_QUERY_INVALID expected_failure errno=2
PANTHOR_SYNCOBJ_SIGNAL_QUERY_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=SYNCOBJ_SIGNAL_QUERY_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: SYNCOBJ_SIGNAL session=1 count=1 first=1 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
panthor-proxy: SYNCOBJ_RESET session=1 count=1 first=1 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=4294967295 ret=-22
panthor-proxy: SYNCOBJ_TIMELINE_SIGNAL session=1 count=2 flags=0x0 first=2 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=2 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_QUERY session=1 count=2 flags=0x0 first=2 ret=0
panthor-proxy: SYNCOBJ_QUERY session=1 count=2 flags=0x1 first=2 ret=0
```

Regression smokes also passed after the helper split:

```text
run id: vmshm-1client-syncobj-timeline-wait-regression-20260604-025024
result: PASS

run id: vmshm-1client-syncobj-transfer-regression-20260604-025108
result: PASS

run id: vmshm-1client-syncobj-wait-regression-20260604-025143
result: PASS
```

### Remaining Risks

- This completes the currently selected in-VM syncobj state-control surface, but
  it still does not prove `GROUP_SUBMIT -> physical GPU IRQ -> proxy fence
  signal -> client wait`.
- `DRM_IOCTL_SYNCOBJ_EVENTFD`, `SYNCOBJ_HANDLE_TO_FD`, and
  `SYNCOBJ_FD_TO_HANDLE` remain intentionally unimplemented because fd numbers
  are process/VM local and cannot be raw-forwarded. They need a separate design
  only if Mesa/userspace traces prove they are required.
- The wait path still uses synchronous RPC. Long waits for real GPU jobs need a
  longer timeout or async completion path.

## 2026-06-04: GROUP_CREATE/DESTROY/GET_STATE Lifecycle

### Scope

This step adds and validates Panthor scheduling group lifecycle virtualization:

```text
client DRM_IOCTL_PANTHOR_GROUP_CREATE
  -> copy GROUP_CREATE queues[] in panthor-client
  -> send fixed vmshm-comm RPC
  -> proxy translates client VM id to proxy VM id
  -> real panthor_group_create() in the proxy VM
  -> return client group handle mapped to proxy group handle

client DRM_IOCTL_PANTHOR_GROUP_GET_STATE
  -> translate client group handle
  -> query proxy real group state
  -> return state/fatal_queues

client DRM_IOCTL_PANTHOR_GROUP_DESTROY
  -> retire client group handle
  -> proxy destroys real group
  -> double destroy rejects the stale client handle
```

This is a lifecycle/control-plane milestone only. It does not implement
`GROUP_SUBMIT`, does not prove physical GPU job completion, and does not yet
connect BO payload backing to real GPU command/data execution.

### Design

- Added Panthor vmshm ABI messages:
  - `PANTHOR_VMSHM_MSG_GROUP_CREATE_REQ/RSP`
  - `PANTHOR_VMSHM_MSG_GROUP_DESTROY_REQ/RSP`
  - `PANTHOR_VMSHM_MSG_GROUP_GET_STATE_REQ/RSP`
- Added client-side `struct panthor_client_group` and a per-open `groups`
  xarray.
- Added proxy-side `struct panthor_proxy_group` and a per-session `groups`
  xarray.
- `GROUP_CREATE queues[]` are copied from client userspace by
  `panthor-client`, flattened into the request, and carried in `vmshm-comm`.
  The fixed `PANTHOR_VMSHM_MAX_GROUP_QUEUES == 16` limit keeps the request
  below the comm payload budget for the current UAPI
  (`struct drm_panthor_queue_create` is 8 bytes).
- Added `PANTHOR_VMSHM_COMM_PAYLOAD_LIMIT == 476` and a `static_assert()` that
  `struct panthor_vmshm_group_create_req` fits in one vmshm-comm payload.
  This catches future UAPI/request growth at build time.
- `vmshm-object` is not used for group queues. Queue creation arguments are
  transient ioctl metadata, not client-mappable GPU payload.
- The proxy translates `client_vm_id -> proxy_vm_id`, calls
  `panthor_vmshm_group_create()`, and maps the returned real group handle to a
  client-visible group handle.
- High group priority is rejected in the vmshm path for now. The current RPC
  does not carry client credentials, `CAP_SYS_NICE`, or DRM master status, so
  allowing high priority would silently weaken the real driver's permission
  model.
- Session cleanup destroys groups before BOs/VMs so leftover groups cannot
  reference already-destroyed VM state.

### Fixes During Bring-Up

- `panthor_group_get_state()` clears the passed UAPI struct internally. The
  proxy wrapper now saves the translated proxy group handle before calling the
  real helper and writes that saved handle into the response afterward. Without
  this, successful `GROUP_GET_STATE` responses reported `proxy_group=0` even
  though the query succeeded.
- Client `GROUP_DESTROY` no longer attempts a fragile local xarray rollback
  after an RPC failure. The local handle is retired and the group object is
  freed. This avoids leaking an object if rollback insertion fails, and avoids
  leaving a half-trusted local mapping after proxy-side state may already have
  changed.

### Blacklisted Directions

- Do not put `GROUP_CREATE queues[]` in `vmshm-object`. They are transient
  ioctl control metadata and belong in `vmshm-comm`. If the fixed inline
  request stops fitting, the right design is a comm transfer/segmented comm
  protocol, not object-memslot misuse.
- Do not keep a client-side group destroy rollback path that can resurrect a
  local handle after proxy state is uncertain. The safer POC behavior is to
  retire the local handle and rely on close/session cleanup plus explicit
  errors.
- Do not trust the real Panthor helper's input UAPI struct to preserve handle
  fields after a helper call. For RPC responses, save translated handles
  separately and fill response fields explicitly.

### Passthrough Constraints

Group lifecycle itself is mostly scheduler/control-plane work, but it allocates
real proxy-side Panthor queues and kernel BOs under the proxy VM's passthrough
driver. Later `GROUP_SUBMIT` work must continue to honor the passthrough rules:

- Real GPU page tables must contain HPA, not GPA.
- TTBR/root tables, non-leaf descriptors, and leaf PTEs must all ultimately be
  HPA-visible to the physical GPU page walker.
- VM_BIND data-plane work must stay 4K-correct because contiguous guest GPA
  does not imply contiguous host HPA.
- Real job completion depends on the `pmthor -> eventfd -> KVM irqfd -> guest
  IRQ -> resamplefd/EOI` path, not bare-metal interrupt assumptions.

### Tests

Local checks/builds passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
./scripts/build/build-guest-vmshm-kernels.sh
```

Final remote one-proxy-one-client smoke passed:

```text
command:
RUN_ID=vmshm-1client-group-lifecycle-20260604-031737 \
./scripts/run/run-vmshm-e2e.sh \
  --skip-firecracker-build \
  --group-lifecycle-smoke

run id: vmshm-1client-group-lifecycle-20260604-031737
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-group-lifecycle-20260604-031737
result: PASS
```

Key client evidence:

```text
VM_CREATE id=1 user_va_range=0x800000000000
GROUP_CREATE handle=1 vm=1 queues=1 queue_ring=0x1000 compute_mask=0x1 fragment_mask=0x1 tiler_mask=0x1
GROUP_GET_STATE handle=1 state=0x0 fatal_queues=0x0
GROUP_DESTROY handle=1
GROUP_DESTROY_DOUBLE handle=1 expected_failure errno=22 (Invalid argument)
VM_DESTROY id=1
PANTHOR_GROUP_LIFECYCLE_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=GROUP_LIFECYCLE_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: VM_CREATE session=1 client_vm=1 proxy_vm=1 user_va_range=0x800000000000
panthor-proxy: GROUP_CREATE session=1 client_group=1 proxy_group=1 client_vm=1 proxy_vm=1 queues=1 ret=0
panthor-proxy: GROUP_GET_STATE session=1 client_group=1 proxy_group=1 state=0x0 fatal_queues=0x0 ret=0
panthor-proxy: GROUP_DESTROY session=1 client_group=1 proxy_group=1 ret=0
panthor-proxy: VM_DESTROY session=1 client_vm=1 proxy_vm=1
```

Log grep found no kernel panic, Oops, call trace, WARN, or unexpected FAIL in
the final `client.log`, `proxy.log`, or `broker.log`. The only `failed` text was
the expected `GROUP_DESTROY_DOUBLE` stale-handle rejection.

### Remaining Risks

- This validates group lifecycle handle translation only. `GROUP_SUBMIT` is not
  implemented yet.
- The real proxy group internally allocates queue/kernel BOs. This has not yet
  proven client-submitted command streams, shared BO payload backing, or
  physical GPU IRQ/fence completion.
- The group lifecycle smoke creates one low-priority queue. Multi-queue and
  higher-priority policy need separate tests once credential/priority handling
  is designed.

## 2026-06-04: TILER_HEAP_CREATE/DESTROY Lifecycle

### Scope

This step adds and validates Panthor tiler heap lifecycle virtualization:

```text
client DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE
  -> panthor-client copies fixed UAPI fields
  -> vmshm-comm RPC carries VM id and heap parameters
  -> proxy translates client VM id to proxy VM id
  -> real panthor_heap_create() in the proxy VM Panthor session
  -> proxy returns GPU VAs and a client-visible heap handle

client DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY
  -> retire client heap handle
  -> proxy translates to real proxy heap handle
  -> real panthor_heap_destroy()
  -> double destroy rejects the stale client handle
```

This is a lifecycle/control-plane milestone. It does not implement
`GROUP_SUBMIT`, does not prove a tiler/render workload, and does not change BO
payload backing.

### Design

- Added Panthor vmshm ABI messages:
  - `PANTHOR_VMSHM_MSG_TILER_HEAP_CREATE_REQ/RSP`
  - `PANTHOR_VMSHM_MSG_TILER_HEAP_DESTROY_REQ/RSP`
- Added client-side `struct panthor_client_heap` and a per-open `heaps`
  xarray.
- Added proxy-side `struct panthor_proxy_heap` and a per-session `heaps`
  xarray.
- The client never exposes the real proxy heap handle as the UAPI heap handle.
  The proxy allocates a client-visible heap handle and records:

```text
client_heap_handle -> proxy_heap_handle
client_vm_id       -> proxy_vm_id
tiler_heap_ctx_gpu_va
first_heap_chunk_gpu_va
```

- The real Panthor helper returns heap handles with the usual Panthor encoding:

```text
proxy_heap_handle = (proxy_vm_id << 16) | heap_id
```

  That encoded handle stays inside the proxy namespace. This is important
  because client VM ids are virtual and may diverge from proxy VM ids.
- `tiler_heap_ctx_gpu_va` and `first_heap_chunk_gpu_va` are returned unchanged
  to the client. They are GPU virtual addresses in the proxy-created real GPU VM,
  and later command streams must use that same GPU VA space.
- No `vmshm-object` allocation is used. Tiler heap ioctl arguments and returned
  GPU VAs are control metadata carried by `vmshm-comm`. The heap's internal real
  kernel BOs are owned by the proxy real Panthor driver and are not client
  mappable BO payloads.
- Session cleanup now destroys leftover groups before leftover heaps, and heaps
  before BOs/VMs. This avoids destroying the VM while a real heap handle still
  refers to that VM's heap pool.

### Passthrough Constraints

The tiler heap itself is created by the proxy VM's real Panthor driver, which in
this project reaches the physical GPU through the custom passthrough path.
Therefore the usual passthrough constraints still apply to any heap-internal
GPU mappings:

- GPU-visible page tables must contain HPA, not GPA.
- Root tables, non-leaf descriptors, and leaf PTEs must all be valid for the
  physical GPU page walker.
- Any heap pages mapped through the proxy VM must respect the GPA->HPA
  translation rules. Contiguous guest GPA is not proof of contiguous HPA.
- Future jobs that use this heap will complete only when the full
  `pmthor -> eventfd -> KVM irqfd -> guest IRQ -> resamplefd/EOI` path works.

### Tests

Local checks/builds passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
git diff --check
git -C Linux-Guest-GPU diff --check
./scripts/build/build-guest-vmshm-kernels.sh
```

Final remote one-proxy-one-client smoke passed:

```text
command:
RUN_ID=vmshm-1client-tiler-heap-20260604-033754 \
./scripts/run/run-vmshm-e2e.sh \
  --skip-firecracker-build \
  --tiler-heap-lifecycle-smoke

run id: vmshm-1client-tiler-heap-20260604-033754
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-tiler-heap-20260604-033754
result: PASS
```

Key client evidence:

```text
VM_CREATE id=1 user_va_range=0x800000000000
TILER_HEAP_CREATE handle=1 vm=1 initial_chunks=1 chunk_size=0x20000 max_chunks=2 target_in_flight=1 ctx_va=0x800000000000 first_chunk_va=0x800000002000
TILER_HEAP_DESTROY handle=1
TILER_HEAP_DESTROY_DOUBLE handle=1 expected_failure errno=22 (Invalid argument)
VM_DESTROY id=1
PANTHOR_TILER_HEAP_LIFECYCLE_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=TILER_HEAP_LIFECYCLE_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: VM_CREATE session=1 client_vm=1 proxy_vm=1 user_va_range=0x800000000000
panthor-proxy: TILER_HEAP_CREATE session=1 client_heap=1 proxy_heap=65536 client_vm=1 proxy_vm=1 ctx_va=0x800000000000 first_chunk_va=0x800000002000 ret=0
panthor-proxy: TILER_HEAP_DESTROY session=1 client_heap=1 proxy_heap=65536 ret=0
panthor-proxy: VM_DESTROY session=1 client_vm=1 proxy_vm=1
```

The final run's result summary was `RESULT: PASS`. A log scan found no kernel
panic, Oops, call trace, BUG, WARN, ERROR, or unexpected FAIL in the fetched
logs. The only expected failure was the stale-handle
`TILER_HEAP_DESTROY_DOUBLE` check.

### Blacklisted Directions

- Do not put tiler heap create/destroy parameters in `vmshm-object`. They are
  fixed control metadata and belong in `vmshm-comm`.
- Do not expose proxy real heap handles as client UAPI handles. Real heap
  handles encode the proxy VM id, so the client must receive a virtual heap
  handle mapped by the proxy session.

### Remaining Risks

- This proves heap lifecycle only. No `GROUP_SUBMIT` path uses the returned heap
  GPU VAs yet.
- The heap's internal backing is allocated by the proxy real Panthor driver. It
  is not a client-mappable BO and does not solve the shared BO payload backing
  problem.
- Compute-only Mesa traces may still create tiler heaps during context setup.
  This path should therefore remain enabled even before render/tiler workloads
  are attempted.

## 2026-06-04: GROUP_SUBMIT Zero-Length Syncpoint POC

### Scope

This step adds the first virtualized `DRM_IOCTL_PANTHOR_GROUP_SUBMIT` path, but
intentionally limits it to zero-length queue submissions:

```text
client DRM_IOCTL_PANTHOR_GROUP_SUBMIT
  -> panthor-client copies queue_submits[] and nested syncs[]
  -> client validates stream_addr == 0 && stream_size == 0
  -> vmshm-comm RPC carries flattened job/sync metadata
  -> proxy translates client group/syncobj handles to proxy handles
  -> real panthor_vmshm_group_submit() submits to the proxy real Panthor session
  -> signal syncobj fence is observed through virtualized SYNCOBJ_WAIT
```

This is a control/scheduler/fence POC. It does not prove client command stream
execution, BO payload data correctness, or final physical GPU IRQ delivery.

### Design

- Added client-side `DRM_IOCTL_PANTHOR_GROUP_SUBMIT` dispatch.
- Added `panthor_client_rpc_group_submit()` for
  `PANTHOR_VMSHM_MSG_GROUP_SUBMIT_REQ/RSP`.
- Added proxy handler table entry and `panthor_proxy_handle_group_submit()`.
- Added proxy-side `panthor_proxy_session_group_submit()` which:
  - translates the client group handle to the proxy group handle,
  - translates every client syncobj handle to the proxy syncobj handle,
  - builds kernel `drm_panthor_queue_submit[]`,
    `drm_panthor_sync_op[]`, `sync_starts[]`, and `sync_counts[]`,
  - calls real `panthor_vmshm_group_submit()`.
- Added real-driver helper `panthor_vmshm_group_submit()` in the Panthor driver.
  It reuses the normal submit context helpers, including signal collection,
  dependency registration, job arming, scheduler push, and syncobj fence push.
- Added `panthor_submit_ctx_add_job_kernel_syncs()` so vmshm submit can pass
  already-copied kernel sync arrays without feeding kernel pointers into
  `PANTHOR_UOBJ_GET_ARRAY()`.
- Added group refcounting in `panthor-client`. `GROUP_SUBMIT` and
  `GROUP_GET_STATE` hold a temporary group reference, while `GROUP_DESTROY`
  removes the client handle and delays the real destroy RPC until the final
  reference drops. This mirrors the already-tested syncobj delayed-destroy
  pattern and avoids local destroy racing a submit RPC.
- Fixed proxy syncobj-array translation cleanup to clear pointers after
  releasing partially translated entries. Without clearing them, a caller that
  also runs common cleanup could double-put already released syncobjs.

### Memslot Use

- `queue_submits[]`, per-submit `syncs[]`, `sync_starts[]`, and `sync_counts[]`
  are transient ioctl metadata. They are copied into the client kernel,
  flattened into the fixed vmshm protocol payload, and carried by
  `vmshm-comm`.
- No `vmshm-object` allocation is used for this submit POC.
- This matches the two-memslot rule:
  - `vmshm-comm`: control/RPC/metadata/flattened ioctl arrays.
  - `vmshm-object`: only BO payloads or structures that the client VM must
    directly `mmap/read/write`.

### Validation Rules

The client and proxy both reject unsupported or malformed submit input:

- `job_count == 0` or more than `PANTHOR_VMSHM_MAX_GROUP_SUBMITS`: reject.
- total flattened sync ops above `PANTHOR_VMSHM_MAX_GROUP_SUBMIT_SYNCS`: reject.
- nonzero `stream_addr` or nonzero `stream_size`: `-EOPNOTSUPP`.
- binary syncobj with nonzero `timeline_value`: reject.
- sync op flags outside
  `DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_MASK | DRM_PANTHOR_SYNC_OP_SIGNAL`: reject.
- stale group or syncobj handles: reject before RPC/real-submit use.

The nonzero command-stream rejection is deliberate. Real command streams require
client-written BO payloads, VM_BIND GPU VA mappings, and proxy real GEM backing
to be the same GPU-visible memory. That is not true yet.

### Passthrough Constraints

The proxy VM submits through this project's custom passthrough stack, not
bare-metal Panthor. Later nonzero submit work must keep these rules intact:

- GPU page tables must contain HPA, not GPA.
- TTBR/root table addresses, non-leaf descriptors, and leaf PTEs must all be
  physical addresses valid to the GPU page walker.
- VM_BIND map/unmap must remain 4K-correct. Contiguous client/proxy GPA cannot
  be assumed to mean contiguous HPA.
- Real GPU completion must be validated through:

```text
pmthor -> eventfd -> KVM irqfd -> guest IRQ -> resamplefd/EOI
```

### Tests

Local checks/builds passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
git diff --check
git -C Linux-Guest-GPU diff --check
./scripts/build/build-guest-vmshm-kernels.sh
```

Final remote one-proxy-one-client smoke passed:

```text
command:
RUN_ID=vmshm-1client-group-submit-syncpoint-20260604-041543 \
./scripts/run/run-vmshm-e2e.sh \
  --skip-firecracker-build \
  --group-submit-syncpoint-smoke

run id: vmshm-1client-group-submit-syncpoint-20260604-041543
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-group-submit-syncpoint-20260604-041543
result: PASS
```

Key client evidence:

```text
VM_CREATE id=1 user_va_range=0x800000000000
SYNCOBJ_CREATE_GROUP_SUBMIT_SIGNAL handle=1 flags=0x0
GROUP_CREATE handle=1 vm=1 queues=1 queue_ring=0x1000 compute_mask=0x1 fragment_mask=0x1 tiler_mask=0x1
GROUP_SUBMIT_SYNCPOINT group=1 sync=1 queue=0 stream_addr=0x0 stream_size=0 sync_flags=0x80000000
SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=1 timeout_nsec=1000000000 flags=0x2 first=0
GROUP_GET_STATE_AFTER_SUBMIT handle=1 state=0x0 fatal_queues=0x0
GROUP_DESTROY_AFTER_SUBMIT handle=1
SYNCOBJ_DESTROY_GROUP_SUBMIT_SIGNAL handle=1
VM_DESTROY id=1
PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=GROUP_SUBMIT_SYNCPOINT_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor-proxy: VM_CREATE session=1 client_vm=1 proxy_vm=1 user_va_range=0x800000000000
panthor-proxy: SYNCOBJ_CREATE session=1 client_sync=1 proxy_sync=1 flags=0x0
panthor-proxy: GROUP_CREATE session=1 client_group=1 proxy_group=1 client_vm=1 proxy_vm=1 queues=1 ret=0
panthor-proxy: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=1 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x2 first=0 ret=0
panthor-proxy: GROUP_GET_STATE session=1 client_group=1 proxy_group=1 state=0x0 fatal_queues=0x0 ret=0
panthor-proxy: GROUP_DESTROY session=1 client_group=1 proxy_group=1 ret=0
panthor-proxy: SYNCOBJ_DESTROY session=1 client_sync=1 proxy_sync=1
panthor-proxy: VM_DESTROY session=1 client_vm=1 proxy_vm=1
```

The final run's result summary was `RESULT: PASS`. Manual log inspection found
the expected submit/wait/pass markers and no kernel panic, Oops, call trace,
BUG, WARN, ERROR, or unexpected FAIL in the fetched logs.

### Blacklisted Directions

- Do not pass kernel-resident sync arrays through `PANTHOR_UOBJ_GET_ARRAY()` or
  any helper that expects userspace pointers. The vmshm path must use a
  kernel-array helper such as `panthor_submit_ctx_add_job_kernel_syncs()`.
- Do not put `GROUP_SUBMIT queue_submits[]` or nested `syncs[]` in
  `vmshm-object`. They are transient control metadata and belong in
  `vmshm-comm`.
- Do not enable nonzero `stream_addr/stream_size` until BO payload backing and
  GPU page table HPA mapping are data-correct. Returning success for real
  command streams before that would create a false-positive Mesa/GPU execution
  result.
- Do not treat zero-length submit success as proof of physical GPU command
  execution or full IRQ completion.

### Remaining Risks

- Zero-length jobs are synchronization points. In the real scheduler,
  `queue_run_job()` may attach the prior queue fence and can complete
  immediately when there is no prior real GPU work. This means the POC proves
  ioctl/RPC/handle translation/scheduler fence plumbing, not shader execution.
- Real BO backing and `vmshm-object` payload backing are still separate. Until
  they converge, client-written command buffers and SSBO data are not
  GPU-data-correct.
- Nonzero submit must be opened only after VM_BIND maps the exact GPU-visible
  shared pages and after passthrough page tables and IRQ completion are
  validated end to end.

## 2026-06-04: VM_BIND Async Sync Arrays And SYNC_ONLY

### Scope

This step targets the next VM_BIND semantic gap after synchronous MAP/UNMAP:

```text
VM_BIND_ASYNC MAP + signal syncobj
VM_BIND_ASYNC SYNC_ONLY + signal syncobj
VM_BIND_ASYNC UNMAP + signal syncobj
client SYNCOBJ_WAIT observes proxy real syncobj completion
```

This is still an ioctl/fence-path smoke, not a nonzero command-stream execution
test. It proves that VM_BIND nested `syncs[]` can cross the client/proxy
boundary as flattened control metadata and that the proxy can feed kernel-resident
sync arrays into the real Panthor VM bind scheduler path.

### Design

- Extended `struct panthor_vmshm_vm_bind_req` with:
  - `sync_count`
  - per-op `sync_start` / `sync_count`
  - `syncs[PANTHOR_VMSHM_MAX_VM_BIND_SYNCS]`
- Set `PANTHOR_VMSHM_MAX_VM_BIND_SYNCS == 8` so the fixed request remains within
  the 476-byte `vmshm-comm` payload limit.
- Kept all VM_BIND op and sync arrays in `vmshm-comm`. No transient VM_BIND
  metadata was moved to `vmshm-object`.
- Preserved UAPI semantics:
  - synchronous VM_BIND still rejects nested `syncs[]`
  - `SYNC_ONLY` is accepted only with `DRM_PANTHOR_VM_BIND_ASYNC`
  - `SYNC_ONLY` must have at least one sync op and all BO/VA/size fields zero
- Added a real Panthor `panthor_vmshm_vm_bind()` async path that creates
  VM_BIND scheduler jobs and attaches kernel-copied sync arrays with
  `panthor_submit_ctx_add_job_kernel_syncs()`. The vmshm path still does not
  pass kernel arrays through `PANTHOR_UOBJ_GET_ARRAY()`.
- Hardened `panthor_vm_bind_job_put()` so failed async VM_BIND setup can safely
  clean partially populated submit contexts.
- Added `--vm-bind-async-sync` to `panthor_ioctl_smoke` and
  `--vm-bind-async-sync-smoke` to `run-vmshm-e2e.sh`.

### Memslot Boundary

- `vmshm-comm`: VM_BIND flags, op array, flattened sync array, translated
  syncobj handles, return code, and failed-op index.
- `vmshm-object`: still only BO payload memory that client userspace can
  `mmap/read/write`.

This explicitly avoids using `vmshm-object` for VM_BIND sync arrays.

### Passthrough Constraint

The MAP operation in the async smoke still maps a vmshm-backed BO payload. It
therefore must continue through the proxy VM passthrough path:

```text
payload GPA span -> GPA_TO_HPA -> GPU PTE contains HPA
```

The SYNC_ONLY operation intentionally does not touch GPU page tables. It only
tests scheduler/fence sequencing and syncobj signal propagation.

### Local Checks

Passed before remote execution:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
git diff --check
git -C Linux-Guest-GPU diff --check
./scripts/build/build-guest-vmshm-kernels.sh
```

The kernel build installed updated role images:

```text
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

### Remote Test

The first remote attempt had an invocation bug and a real implementation bug:

- The shell form
  `RUN_ID=vmshm-1client-vm-bind-async-sync-... ./scripts/run/run-vmshm-e2e.sh --run-id "$RUN_ID"`
  expanded `"$RUN_ID"` before the temporary assignment was visible, so the
  runner received an empty run id and fetched logs into the top-level
  `GPU-SFTP/log/shared/vmshm-1client/` directory.
- That attempt then failed at `VM_BIND_ASYNC_SYNC_ONLY failed: Invalid argument`.
  Root cause: the vmshm helper passed a kernel op copy to
  `panthor_vm_bind_job_create()` with `op.syncs.count == 0`, while the real
  Panthor async VM_BIND path validates `SYNC_ONLY` through the op's sync count.
- Fix: before job creation, populate the kernel op's sync metadata with
  `op.syncs.count = sync_counts[i]`,
  `op.syncs.stride = sizeof(*op_syncs)`, and `op.syncs.array = 0`. This is an
  implementation bug fix, not a blacklisted design.

Final remote one-proxy-one-client smoke passed:

```text
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --vm-bind-async-sync-smoke \
  --run-id vmshm-1client-vm-bind-async-sync-20260604-052208

run id: vmshm-1client-vm-bind-async-sync-20260604-052208
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vm-bind-async-sync-20260604-052208
result: PASS
```

Key client evidence:

```text
VM_BIND_ASYNC_MAP vm=1 bo=1 sync=1 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_MAP handle=1 first=0
VM_BIND_ASYNC_SYNC_ONLY vm=1 sync=2
SYNCOBJ_WAIT_AFTER_VM_BIND_SYNC_ONLY handle=2 first=0
VM_BIND_ASYNC_UNMAP vm=1 sync=3 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_UNMAP handle=3 first=0
PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=VM_BIND_ASYNC_SYNC_PASS
PANTHOR_IOCTL_INIT=PASS
```

Key proxy evidence:

```text
panthor: VM_BIND vmshm payload mapped iova=0x200000 size=0x1000 spans=1 first_gpa=0x0000000023e00000
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x2 first=0 ret=0
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x2 first=0 ret=0
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x2 first=0 ret=0
RESULT: PASS
```

No design blacklist was added for the failed attempt. The implementation bug
was removed, and the existing blacklisted directions remain: do not pass
kernel sync arrays through user-pointer helpers, and do not put transient
VM_BIND arrays in `vmshm-object`.

## 2026-06-04: vmshm-backed BO VM_BIND Data-Plane Boundary

### Scope

This step removes the previous shared-virtualization BO backing mismatch:

```text
client BO mmap
  -> vmshm-object payload pages
  -> proxy real Panthor GEM metadata
  -> VM_BIND maps the same payload GPA spans
  -> custom passthrough io-pgtable converts GPA to HPA for GPU PTEs
```

The goal is still narrower than real command stream execution. It proves that
the proxy `BO_CREATE` path no longer creates an unrelated real shmem GEM backing
for shared BOs, and that synchronous VM_BIND MAP consumes `vmshm-object` payload
spans.

### Design

- Added `struct proxy_vmshm_object *vmshm_payload` to
  `struct panthor_gem_object`.
- Added `panthor_gem_create_vmshm_with_handle()`.
  It creates a normal shmem GEM shell for DRM/GPUVA metadata and reservation
  handling, pins the `vmshm-object` payload for the GEM lifetime, records the
  payload pointer on the Panthor GEM, and lets VM_BIND bypass the shell shmem
  pages when `vmshm_payload` is set.
- Added `panthor_vmshm_bo_create_from_payload()` in the real Panthor driver.
  The proxy shared-virtualization BO path calls this helper instead of the old
  `panthor_vmshm_bo_create()` helper.
- Changed proxy `BO_CREATE` to allocate the payload object at the page-aligned
  BO size before calling the real vmshm-backed GEM helper. This keeps:

```text
client-visible BO size
payload logical size
VM_BIND translate range
```

  aligned to the same range.
- In `panthor_vm_prepare_map_op_ctx()`, vmshm-backed BOs:
  skip `drm_gem_shmem_pin()`, skip `drm_gem_shmem_get_pages_sgt()`, translate
  the payload range through `proxy_vmshm_obj_translate()`, and keep the
  translated `proxy_vmshm_span[]` in the map operation context.
- In `panthor_gpuva_sm_step_map()`, vmshm-backed BOs call
  `panthor_vm_map_vmshm_spans()` instead of `panthor_vm_map_pages()`.
- `panthor_vm_map_vmshm_spans()` maps payload GPA spans into the real Panthor
  GPU VA. The proxy VM's passthrough `ARM_64_PANATHOR_LPAE_S1` io-pgtable still
  performs GPA-to-HPA conversion before GPU-visible PTEs are written.
- Added rollback for incomplete span coverage after partial mapping, so a
  malformed span set cannot leave a partial GPU VA mapping behind.
- Added vmshm-backed evidence logs:

```text
panthor: BO_CREATE vmshm-backed handle=... payload=... segments=...
panthor-proxy: BO_CREATE vmshm-backed session=...
panthor: VM_BIND vmshm payload mapped iova=... spans=... first_gpa=...
```

- Updated the one-client runner's `--vm-bind-smoke` gate so it now requires the
  vmshm-backed BO_CREATE and payload VM_BIND evidence. This prevents regression
  back to the old separate-shmem design.
- Updated the `--bo-mmap-smoke` gate to require vmshm-backed BO_CREATE evidence
  while not requiring a VM_BIND payload-map log, because BO mmap does not issue
  VM_BIND.
- Added `DRM_PANTHOR_PROXY depends on PROXY_VMSHM_MANAGER`, making the proxy
  kernel config dependency explicit.

### Memslot Boundary

This step keeps the two-memslot rule intact:

- `vmshm-object` is used only for BO payload memory that the client VM can
  `mmap/read/write`.
- `vmshm-comm` continues to carry BO_CREATE/BO_DESTROY metadata and VM_BIND op
  arrays.
- No transient VM_BIND arrays, submit arrays, sync arrays, or syncobj handle
  arrays were moved into `vmshm-object`.

### Passthrough Constraint

The proxy VM uses the custom GPU passthrough stack. The new direct payload
mapping deliberately passes payload GPA spans to the existing Panthor MMU path
instead of fabricating `struct page` or sg-table backing for the vmshm memslot.
This preserves the passthrough invariant:

```text
payload GPA span
  -> arm_panthor_lpae_map_pages()
  -> KVM GPA_TO_HPA hypercall
  -> GPU leaf PTE contains HPA
```

TTBR/root tables and non-leaf descriptors are still handled by the existing
passthrough page-table code. Contiguous GPA must still not be treated as proof
of contiguous HPA; the passthrough path remains responsible for 4K correctness.

### Blacklisted Directions

- Do not reintroduce the design where proxy `BO_CREATE` allocates a
  `vmshm-object` payload for the client but maps a separate ordinary shmem GEM
  into the real GPU VM. That design is control-plane correct but data-plane
  incorrect.
- Do not try to repair the separate-shmem design by submit-time memcpy, dirty
  mirroring, or ad hoc payload synchronization. It would break async fence
  ordering, cache visibility, and SSBO readback semantics.
- Do not enable nonzero `GROUP_SUBMIT stream_addr/stream_size` merely because
  VM_BIND now maps payload spans. Real command stream execution still needs
  command buffer contents, cache maintenance, sync waits, and IRQ/fence
  completion validation.

### Local Checks

These local checks passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
git diff --check
git -C Linux-Guest-GPU diff --check
./scripts/build/build-guest-vmshm-kernels.sh
```

The kernel build installed updated role images:

```text
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

### Remote Tests

VM_BIND smoke with vmshm-backed payload mapping passed:

```text
command:
RUN_ID=vmshm-1client-vmshm-backed-bind-20260604-045509 \
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --vm-bind-smoke \
  --run-id "$RUN_ID"

run id: vmshm-1client-vmshm-backed-bind-20260604-045509
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-vmshm-backed-bind-20260604-045509
result: PASS
```

Key proxy evidence:

```text
panthor: BO_CREATE vmshm-backed handle=1 size=0x1000 payload=0x100000001 payload_size=0x1000 segments=1
panthor-proxy: BO_CREATE vmshm-backed session=1 client_bo=1 proxy_bo=1 size=0x1000 payload=0x100000001 payload_size=0x1000
panthor: VM_BIND vmshm payload mapped iova=0x100000 size=0x1000 spans=1 first_gpa=0x0000000023e00000
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
RESULT: PASS
```

BO mmap regression with vmshm-backed BO creation passed:

```text
command:
RUN_ID=vmshm-1client-bo-mmap-vmshmbacked-regression-20260604-045727 \
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --bo-mmap-smoke \
  --run-id "$RUN_ID"

run id: vmshm-1client-bo-mmap-vmshmbacked-regression-20260604-045727
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-bo-mmap-vmshmbacked-regression-20260604-045727
result: PASS
```

Key evidence:

```text
panthor: BO_CREATE vmshm-backed handle=1 size=0x2000 payload=0x100000001 payload_size=0x2000 segments=1
panthor-client: MMAP session=1 client_bo=1 ... payload_gpa=0x0000000023e00000
BO_MMAP_RW handle=1 word0=0x13579bdf word1=0x2468ace0
PANTHOR_BO_MMAP_SMOKE=PASS
RESULT: PASS
```

### Remaining Risks

- This proves the BO payload backing and VM_BIND mapping converge for the tested
  synchronous MAP/UNMAP path. It still does not prove real command stream
  execution.
- `GROUP_SUBMIT` still intentionally rejects nonzero `stream_addr` and
  `stream_size`.
- Cache maintenance for client CPU writes before submit and client CPU readback
  after GPU completion still needs explicit validation.
- Real GPU completion still needs an end-to-end IRQ/fence proof through:

```text
pmthor -> eventfd -> KVM irqfd -> guest IRQ -> resamplefd/EOI
```

## 2026-06-04: Post-Async-VM_BIND Regression Sweep

### Scope

After adding async VM_BIND sync arrays and fixing the `SYNC_ONLY` implementation
bug, rerun the narrow one-client smokes that protect the current data/control
boundary:

```text
BO_MMAP
VM_BIND synchronous MAP/UNMAP
VM_BIND async MAP/SYNC_ONLY/UNMAP with syncobj waits
GROUP_SUBMIT zero-length syncpoint
```

This sweep is still ioctl/fence plumbing validation. It does not claim nonzero
command-stream execution.

### Local Checks

Passed before the remote sweep:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
git diff --check
git -C Linux-Guest-GPU diff --check
```

The smoke binary was rebuilt and synced. Kernel and Firecracker artifacts were
reused with `--skip-build`.

### Remote Regression Results

BO mmap regression passed:

```text
run id: vmshm-1client-regress-bo-mmap-20260604-053039
command:
./scripts/run/run-vmshm-e2e.sh --skip-build --bo-mmap-smoke \
  --run-id vmshm-1client-regress-bo-mmap-20260604-053039
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-regress-bo-mmap-20260604-053039
result: PASS
```

Key evidence:

```text
panthor: BO_CREATE vmshm-backed handle=1 size=0x2000 payload=0x100000001 payload_size=0x2000 segments=1
panthor-client: MMAP session=1 client_bo=1 ... payload_gpa=0x0000000023e00000
BO_MMAP_RW handle=1 word0=0x13579bdf word1=0x2468ace0
PANTHOR_BO_MMAP_SMOKE=PASS
```

Synchronous VM_BIND regression passed:

```text
run id: vmshm-1client-regress-vm-bind-20260604-053121
command:
./scripts/run/run-vmshm-e2e.sh --skip-build --vm-bind-smoke \
  --run-id vmshm-1client-regress-vm-bind-20260604-053121
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-regress-vm-bind-20260604-053121
result: PASS
```

Key evidence:

```text
panthor: VM_BIND vmshm payload mapped iova=0x100000 size=0x1000 spans=1 first_gpa=0x0000000023e00000
VM_BIND_MAP vm=1 bo=1 va=0x100000 size=0x1000
VM_BIND_UNMAP vm=1 va=0x100000 size=0x1000
PANTHOR_VM_BIND_SMOKE=PASS
```

Async VM_BIND regression passed:

```text
run id: vmshm-1client-regress-vm-bind-async-sync-20260604-053203
command:
./scripts/run/run-vmshm-e2e.sh --skip-build --vm-bind-async-sync-smoke \
  --run-id vmshm-1client-regress-vm-bind-async-sync-20260604-053203
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-regress-vm-bind-async-sync-20260604-053203
result: PASS
```

Key evidence:

```text
VM_BIND_ASYNC_MAP vm=1 bo=1 sync=1 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_MAP handle=1 first=0
VM_BIND_ASYNC_SYNC_ONLY vm=1 sync=2
SYNCOBJ_WAIT_AFTER_VM_BIND_SYNC_ONLY handle=2 first=0
VM_BIND_ASYNC_UNMAP vm=1 sync=3 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_UNMAP handle=3 first=0
PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE=PASS
```

Zero-length GROUP_SUBMIT syncpoint regression passed:

```text
run id: vmshm-1client-regress-group-submit-syncpoint-20260604-053402
command:
./scripts/run/run-vmshm-e2e.sh --skip-build --group-submit-syncpoint-smoke \
  --run-id vmshm-1client-regress-group-submit-syncpoint-20260604-053402
local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-regress-group-submit-syncpoint-20260604-053402
result: PASS
```

Key evidence:

```text
GROUP_CREATE handle=1 vm=1 queues=1 queue_ring=0x1000 compute_mask=0x1 fragment_mask=0x1 tiler_mask=0x1
GROUP_SUBMIT_SYNCPOINT group=1 sync=1 queue=0 stream_addr=0x0 stream_size=0 sync_flags=0x80000000
SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=1 timeout_nsec=1000000000 flags=0x2 first=0
PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS
```

The runner fetched and inspected all logs. No kernel panic, Oops, call trace,
BUG, WARN, ERROR, or unexpected FAIL was reported for the four runs.

### Remaining Risks

- Nonzero `GROUP_SUBMIT` is still intentionally closed.
- Cache maintenance for client-written command buffers and GPU-written readback
  BOs still needs a real command-stream test.
- The zero-length submit still proves scheduler/sync plumbing only, not physical
  shader execution or IRQ-backed completion after real GPU work.

## 2026-06-04: Nonzero GROUP_SUBMIT Preparation And Regression

### Scope

Prepare the existing `GROUP_SUBMIT` virtualization path for real command stream
testing by removing the artificial client/proxy/real-helper rejection of
nonzero `stream_addr` and `stream_size`.

This does **not** claim that a nonzero command stream has executed yet. The
authoritative validator for nonzero submit is now the real Panthor job creation
path in the proxy VM. Real success still requires a userspace-driver workload
that submits a valid command stream, waits on the real proxy fence, and verifies
client-side readback.

### Design

- `GROUP_SUBMIT queue_submits[]` and nested `syncs[]` remain transient ioctl
  arrays in `vmshm-comm`. They are not placed in `vmshm-object`.
- `stream_addr`, `stream_size`, and `latest_flush` are copied through the
  flattened control request. `stream_addr` is a GPU VA, not a user pointer, so
  it must preserve the client/Mesa GPU VA semantic established by `VM_BIND`.
- The client and proxy now log the first submit's stream fields:

```text
first_stream=...
first_size=...
first_latest_flush=...
```

  This gives the next userspace-driver test a direct signal that a real command
  stream reached both virtualization endpoints.
- Client BO mmap now uses write-combine page protection as a coarse POC
  cache/coherency step for client-written command, descriptor, shader, and SSBO
  payloads:

```text
vma->vm_page_prot = pgprot_writecombine(vma->vm_page_prot)
```

  This is not yet a complete cache policy. It is a bring-up choice that should
  be validated by `COMPUTE_CHECK=PASS` before treating it as sufficient.
- Fixed a client-side `-Wmisleading-indentation` warning introduced while
  removing the artificial nonzero submit rejection. The warning was around the
  `jobs[i].pad` and `latest_flush` validation in
  `panthor_client_copy_group_submit()`. This was a formatting bug, not a design
  change.

### Passthrough Constraint

Nonzero submit will run through the proxy VM's custom GPU passthrough stack, not
ordinary bare-metal Panthor. The next test must therefore validate more than
`GROUP_SUBMIT ret == 0`:

```text
proxy real Panthor GROUP_SUBMIT
  -> proxy passthrough GPU page tables contain HPA
  -> physical GPU reads command BOs through HPA PTEs
  -> physical IRQ
  -> pmthor eventfd
  -> KVM irqfd
  -> proxy guest IRQ
  -> Panthor fence signal
  -> proxy syncobj wait observed by client
  -> client mmap readback sees GPU writes
```

The direct VM_BIND page-table path must remain 4 KiB correct because
guest-contiguous GPA does not imply host-contiguous HPA.

### Local Checks

Passed after the indentation fix:

```text
bash -n scripts/run/run-vmshm-e2e.sh
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
git diff --check
git -C Linux-Guest-GPU diff --check
./scripts/build/build-guest-vmshm-kernels.sh
```

The kernel build installed updated role images:

```text
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

No warning from the changed `panthor-client` code remained in the build output.

### Remote Regression Results

Zero-length `GROUP_SUBMIT` syncpoint regression passed with the new first-stream
logging:

```text
run id: vmshm-1client-nonzero-prep-group-syncpoint-20260604-054552
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-kernel-build \
  --skip-firecracker-build \
  --group-submit-syncpoint-smoke \
  --run-id vmshm-1client-nonzero-prep-group-syncpoint-20260604-054552
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-nonzero-prep-group-syncpoint-20260604-054552
result: PASS
```

Key evidence:

```text
panthor-client: GROUP_SUBMIT ... jobs=1 syncs=1 first_stream=0x0 first_size=0 first_latest_flush=0x0
panthor-proxy: GROUP_SUBMIT ... jobs=1 syncs=1 first_stream=0x0 first_size=0 first_latest_flush=0x0 ret=0
PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS
RESULT: PASS
```

BO mmap regression passed:

```text
run id: vmshm-1client-nonzero-prep-bo-mmap-regress-20260604-054654
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-nonzero-prep-bo-mmap-regress-20260604-054654
result: PASS
```

Key evidence:

```text
panthor: BO_CREATE vmshm-backed handle=1 size=0x2000 payload=0x100000001 payload_size=0x2000 segments=1
panthor-client: MMAP session=1 client_bo=1 ... payload_gpa=0x0000000023e00000
BO_MMAP_RW handle=1 word0=0x13579bdf word1=0x2468ace0
PANTHOR_BO_MMAP_SMOKE=PASS
```

Synchronous VM_BIND regression passed:

```text
run id: vmshm-1client-nonzero-prep-vm-bind-regress-20260604-054738
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-nonzero-prep-vm-bind-regress-20260604-054738
result: PASS
```

Key evidence:

```text
panthor: VM_BIND vmshm payload mapped iova=0x100000 size=0x1000 spans=1 first_gpa=0x0000000023e00000
VM_BIND_MAP vm=1 bo=1 va=0x100000 size=0x1000
VM_BIND_UNMAP vm=1 va=0x100000 size=0x1000
PANTHOR_VM_BIND_SMOKE=PASS
```

Async VM_BIND and `SYNC_ONLY` regression passed:

```text
run id: vmshm-1client-nonzero-prep-vm-bind-async-regress-20260604-054819
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-nonzero-prep-vm-bind-async-regress-20260604-054819
result: PASS
```

Key evidence:

```text
VM_BIND_ASYNC_MAP vm=1 bo=1 sync=1 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_MAP handle=1 first=0
VM_BIND_ASYNC_SYNC_ONLY vm=1 sync=2
SYNCOBJ_WAIT_AFTER_VM_BIND_SYNC_ONLY handle=2 first=0
VM_BIND_ASYNC_UNMAP vm=1 sync=3 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_UNMAP handle=3 first=0
PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE=PASS
```

A log scan across all four fetched run directories found no kernel panic, Oops,
call trace, BUG, WARN, ERROR, timeout, or unexpected FAIL strings.

### Remaining Risks

- A zero-length syncpoint still proves scheduler/sync plumbing only. It does not
  prove physical shader execution.
- The first nonzero submit test must use a real userspace-driver command stream
  instead of a hand-written fake stream unless a proven Panthor command encoder
  is introduced.
- Cache maintenance is still a correctness risk. If submit and fence wait
  succeed but readback is stale, inspect client BO mmap policy and GPU-write
  invalidation before treating the command stream path as broken.
- IRQ completion is still unproven for real GPU work in the shared path. The
  next userspace workload must distinguish submit success from
  `pmthor -> irqfd -> proxy guest IRQ -> fence signal` completion.

## 2026-06-04: Shared GLES Compute Smoke First PASS

### Scope

Add and run the first real userspace-driver GPU workload through the shared
client/proxy path:

```text
client VM rootfs-panfrost.ext4
  -> Mesa/Panfrost userspace
  -> /dev/dri/card0 panthor-client frontend
  -> vmshm-comm RPC and vmshm-object BO payloads
  -> panthor-proxy
  -> proxy real Panthor driver
  -> proxy VM GPU passthrough
  -> physical Mali GPU
  -> proxy fences/syncobj
  -> client CPU readback
```

This is the first test in this worklog that proves more than ioctl plumbing:
the client VM used Mesa/Panfrost, submitted nonzero command streams, waited for
completion, and verified SSBO readback.

### Runner Design

- Added `--gles-compute-smoke` to `scripts/run/run-vmshm-e2e.sh`.
- The mode uses the existing `rootfs-panfrost.ext4` userspace image, which
  already contains:
  - `/root/gpu-smoke.sh`
  - `/root/gles-compute-smoke`
  - Mesa/Panfrost userspace
- The current runner injects the smoke payload into `rootfs-panfrost.ext4`
  before VM launch.  The injected environment includes:

```text
GPU_SMOKE_ARGS="--count 64"
GPU_SMOKE_QUIET_CONSOLE=0
GPU_SMOKE_AFTER_RUN=shell
```

  Current performance runs pass the workload through `gpu_smoke_args_tokens`
  on the guest command line and keep the image set limited to base rootfs
  images.
- The generated client Firecracker config keeps the shared virtualization
  topology:
  - shared client kernel: `kernels/shared/client/Image`
  - no client GPU passthrough
  - `vmshm-object` at GPA `0x20000000`, slot 1
  - `vmshm-comm` at GPA `0x24000000`, slot 2, notify IRQ 80
- The runner requires the remote `rootfs-panfrost.ext4` base image to exist.
  Ordinary smoke reruns inject the current payload into that base image instead
  of syncing a new rootfs image.
- The PASS gate is:

```text
GPU_SMOKE_RESULT=PASS
COMPUTE_CHECK=PASS
GL_RENDERER=Mali-G610 (Panfrost)
no software renderer / mismatch / GPU fault / timeout / panic indicators
```

### Important Harness Fix

The first run reached `COMPUTE_CHECK=PASS`, but the result gate reported FAIL
because the temporary env used:

```text
GPU_SMOKE_AFTER_RUN=poweroff
```

The rootfs init script then triggered a harmless kernel message:

```text
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000000
```

Firecracker exited successfully and the GPU workload had already passed. This
was a test harness false negative, not a GPU virtualization failure. The runner
was changed to use:

```text
GPU_SMOKE_AFTER_RUN=shell
```

The runner observes the PASS marker and then terminates the VM from outside,
avoiding the init-exit panic string.

This direction is retained. The blacklisted direction is treating an init-exit
panic string after `GPU_SMOKE_RESULT=PASS` as a GPU execution failure.

### Successful Run

```text
run id: vmshm-1client-gles-compute-passcheck-20260604-060143
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --gles-compute-smoke \
  --run-id vmshm-1client-gles-compute-passcheck-20260604-060143
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-gles-compute-passcheck-20260604-060143
result: PASS
```

Client userspace evidence:

```text
DRM_NODE=/dev/dri/card0
GBM_BACKEND=drm
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
STAGE=dispatch
STAGE=map-result
COMPUTE_CHECK=PASS count=64 samples=16 formula=x*3+7+alu_mix alu_iters=1
GPU_SMOKE_RESULT=PASS
```

Client virtualization evidence:

```text
panthor-client: GROUP_SUBMIT ... first_stream=0x7ffffffea000 first_size=40 first_latest_flush=0x0
panthor-client: GROUP_SUBMIT ... first_stream=0x7ffffffcf000 first_size=160 first_latest_flush=0x0
panthor-client: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0
panthor-client: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0
```

Proxy and real Panthor evidence:

```text
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffd7000 size=0x10000 spans=1 first_gpa=0x0000000023e20000
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffcf000 size=0x8000 spans=1 first_gpa=0x0000000023e30000
panthor-proxy: GROUP_SUBMIT ... first_stream=0x7ffffffea000 first_size=40 first_latest_flush=0x0 ret=0
panthor-proxy: GROUP_SUBMIT ... first_stream=0x7ffffffcf000 first_size=160 first_latest_flush=0x0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
```

The fetched logs were scanned for:

```text
panic
Oops
Call trace
BUG:
WARNING:
WARN
ERROR
FAIL
TIMEOUT
timed out
job timeout
gpu fault
mismatch
software renderer
```

No real failure signal was found in the successful run. Matches for
`panic=-1` were only the kernel command line text and are not failure evidence.

### What This Proves

- Mesa selected the hardware Panfrost path in the client VM, not llvmpipe.
- Nonzero `GROUP_SUBMIT` command streams crossed client/proxy virtualization.
- Command stream BOs, shader/state BOs, and SSBO/readback BOs were backed by
  `vmshm-object` payloads and mapped through real proxy Panthor VM_BIND.
- The proxy real Panthor driver and GPU passthrough path completed the submitted
  GPU work well enough for Mesa's sync waits and final SSBO readback to pass.
- The syncobj mirror and timeline wait path are sufficient for this real GLES
  compute workload.
- The coarse write-combine client BO mmap policy is sufficient for this
  correctness smoke, though not yet a complete cache-maintenance strategy.

### Repeatability Check

The same shared GLES compute smoke was repeated without rebuilding:

```text
run id: vmshm-1client-gles-compute-repeat-20260604-060744
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --gles-compute-smoke \
  --run-id vmshm-1client-gles-compute-repeat-20260604-060744
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-gles-compute-repeat-20260604-060744
result: PASS
```

Client userspace again reached the real Panfrost path and completed the
readback check:

```text
DRM_NODE=/dev/dri/card0
GBM_BACKEND=drm
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
STAGE=dispatch
STAGE=map-result
COMPUTE_CHECK=PASS count=64 samples=16 formula=x*3+7+alu_mix alu_iters=1
GPU_SMOKE_RESULT=PASS
RESULT: PASS
```

The repeat run again exercised nonzero command streams and proxy-side waits:

```text
panthor-client: GROUP_SUBMIT ... first_stream=0x7ffffffea000 first_size=40 first_latest_flush=0x0
panthor-client: GROUP_SUBMIT ... first_stream=0x7ffffffcf000 first_size=160 first_latest_flush=0x0
panthor-client: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0
panthor-client: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0
panthor-proxy: GROUP_SUBMIT ... first_stream=0x7ffffffea000 first_size=40 first_latest_flush=0x0 ret=0
panthor-proxy: GROUP_SUBMIT ... first_stream=0x7ffffffcf000 first_size=160 first_latest_flush=0x0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
```

The repeat run result was scanned for panic, Oops, call trace, BUG, WARNING,
WARN, ERROR, FAIL, TIMEOUT, timed-out jobs, GPU faults, mismatches, and software
renderer markers. No failure signal was present.

This confirms the shared one-client path is repeatable for the current short
GLES compute workload. It still does not replace larger-buffer, repeated
iteration, reset, or multi-client stress testing.

## 2026-06-04: Post-GLES IOCTL Regression

### Scope

After adding and validating the shared GLES compute runner mode, rerun a
representative ioctl-only path to make sure the normal lightweight vmshm smoke
mode was not disturbed by the rootfs/config generation changes.

### GROUP_SUBMIT Syncpoint Regression

```text
run id: vmshm-1client-post-gles-group-syncpoint-20260604-061903
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --group-submit-syncpoint-smoke \
  --run-id vmshm-1client-post-gles-group-syncpoint-20260604-061903
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-post-gles-group-syncpoint-20260604-061903
result: PASS
```

Key evidence:

```text
GROUP_CREATE handle=1 vm=1 queues=1 queue_ring=0x1000 compute_mask=0x1 fragment_mask=0x1 tiler_mask=0x1
GROUP_SUBMIT_SYNCPOINT group=1 sync=1 queue=0 stream_addr=0x0 stream_size=0 sync_flags=0x80000000
SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=1 timeout_nsec=1000000000 flags=0x2 first=0
GROUP_GET_STATE_AFTER_SUBMIT handle=1 state=0x0 fatal_queues=0x0
PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=GROUP_SUBMIT_SYNCPOINT_PASS
RESULT: PASS
```

Proxy evidence:

```text
panthor-proxy: GROUP_CREATE session=1 client_group=1 proxy_group=1 client_vm=1 proxy_vm=1 queues=1 ret=0
panthor-proxy: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=1 first_stream=0x0 first_size=0 first_latest_flush=0x0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x2 first=0 ret=0
panthor-proxy: GROUP_GET_STATE session=1 client_group=1 proxy_group=1 state=0x0 fatal_queues=0x0 ret=0
```

The fetched run directory was scanned for panic, Oops, call trace, BUG,
WARNING, WARN, ERROR, FAIL, TIMEOUT, timed-out jobs, GPU faults, mismatches, and
software renderer markers. No failure signal was found.

This remains an ioctl/scheduler/sync plumbing regression, not proof of shader
execution. The real GPU execution proof remains the shared GLES compute smoke
above.

### VM_BIND Async Sync Regression

```text
run id: vmshm-1client-post-gles-vm-bind-async-20260604-062042
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --vm-bind-async-sync-smoke \
  --run-id vmshm-1client-post-gles-vm-bind-async-20260604-062042
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-post-gles-vm-bind-async-20260604-062042
result: PASS
```

Key evidence:

```text
BO_CREATE_ASYNC_BIND handle=1 size=0x1000
SYNCOBJ_CREATE_VM_BIND map=1 sync_only=2 unmap=3
VM_BIND_ASYNC_MAP vm=1 bo=1 sync=1 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_MAP handle=1 first=0
VM_BIND_ASYNC_SYNC_ONLY vm=1 sync=2
SYNCOBJ_WAIT_AFTER_VM_BIND_SYNC_ONLY handle=2 first=0
VM_BIND_ASYNC_UNMAP vm=1 sync=3 va=0x200000 size=0x1000
SYNCOBJ_WAIT_AFTER_VM_BIND_UNMAP handle=3 first=0
PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=VM_BIND_ASYNC_SYNC_PASS
RESULT: PASS
```

Proxy/real Panthor evidence:

```text
panthor: BO_CREATE vmshm-backed handle=1 size=0x1000 payload=0x100000001 payload_size=0x1000 segments=1
panthor: VM_BIND vmshm payload mapped iova=0x200000 size=0x1000 spans=1 first_gpa=0x0000000023e00000
panthor-proxy: VM_BIND session=1 client_vm=1 proxy_vm=1 ops=1 ret=0 failed_op=4294967295
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x2 first=0 ret=0
```

This regression is important for the two-memslot rule:

- `vmshm-object` carried only the BO payload that client userspace/GPU mappings
  need to access.
- Async VM_BIND ops and sync arrays remained flattened ioctl metadata in
  `vmshm-comm`.
- The proxy mapped the payload GPA span through the real Panthor VM_BIND path,
  leaving the custom passthrough GPA-to-HPA page-table path responsible for the
  final GPU-visible PTEs.

The fetched run directory was scanned for panic, Oops, call trace, BUG,
WARNING, WARN, ERROR, FAIL, TIMEOUT, timed-out jobs, GPU faults, mismatches, and
software renderer markers. No failure signal was found.

### Full IOCTL Smoke Sweep

After the focused post-GLES regressions, all currently supported one-client
ioctl smoke modes were run as a sweep using the already-deployed shared
client/proxy artifacts:

```text
base run id: vmshm-1client-full-ioctl-sweep-20260604-062924
command form:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --skip-config-install \
  --skip-sync \
  --<mode> \
  --run-id vmshm-1client-full-ioctl-sweep-20260604-062924-<mode>
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-full-ioctl-sweep-20260604-062924-*
```

Results:

```text
ioctl-smoke                  PANTHOR_IOCTL_SMOKE=BASIC_PASS                  PASS
vm-create-smoke              PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS              PASS
bo-create-smoke              PANTHOR_IOCTL_SMOKE=BO_CREATE_PASS              PASS
bo-lifecycle-smoke           PANTHOR_IOCTL_SMOKE=BO_LIFECYCLE_PASS           PASS
bo-mmap-smoke                PANTHOR_IOCTL_SMOKE=BO_MMAP_PASS                PASS
vm-bind-smoke                PANTHOR_IOCTL_SMOKE=VM_BIND_PASS                PASS
vm-bind-async-sync-smoke     PANTHOR_IOCTL_SMOKE=VM_BIND_ASYNC_SYNC_PASS     PASS
vm-state-flush-smoke         PANTHOR_IOCTL_SMOKE=VM_STATE_FLUSH_PASS         PASS
syncobj-lifecycle-smoke      PANTHOR_IOCTL_SMOKE=SYNCOBJ_LIFECYCLE_PASS      PASS
syncobj-wait-smoke           PANTHOR_IOCTL_SMOKE=SYNCOBJ_WAIT_PASS           PASS
syncobj-transfer-smoke       PANTHOR_IOCTL_SMOKE=SYNCOBJ_TRANSFER_PASS       PASS
syncobj-timeline-wait-smoke  PANTHOR_IOCTL_SMOKE=SYNCOBJ_TIMELINE_WAIT_PASS  PASS
syncobj-signal-query-smoke   PANTHOR_IOCTL_SMOKE=SYNCOBJ_SIGNAL_QUERY_PASS   PASS
group-lifecycle-smoke        PANTHOR_IOCTL_SMOKE=GROUP_LIFECYCLE_PASS        PASS
group-submit-syncpoint-smoke PANTHOR_IOCTL_SMOKE=GROUP_SUBMIT_SYNCPOINT_PASS PASS
tiler-heap-lifecycle-smoke   PANTHOR_IOCTL_SMOKE=TILER_HEAP_LIFECYCLE_PASS   PASS
```

Every fetched result contained `RESULT: PASS`. A sweep-wide scan across the
fetched run directories found no panic, Oops, call trace, BUG, WARNING, WARN,
ERROR, FAIL, TIMEOUT, timed-out job, GPU fault, mismatch, or software-renderer
marker.

This establishes that the current one-client ioctl virtualization surface can
execute cleanly for the available smoke coverage:

- basic DRM identity/capability and Panthor DEV_QUERY
- VM create/destroy/get-state and virtual flush-id mmap
- vmshm-backed BO create/close/lifecycle/mmap
- synchronous and async VM_BIND, including SYNC_ONLY
- syncobj lifecycle, wait, transfer, timeline wait, reset, signal, timeline
  signal, and query
- group lifecycle and zero-length submit syncpoint
- tiler heap lifecycle

The sweep keeps the data/control split intact. The modes that carry transient
arrays use `vmshm-comm`; the modes that require client direct access to BO data
use `vmshm-object` payloads. The VM_BIND modes again require proxy logs showing
`panthor: VM_BIND vmshm payload mapped ...`, which preserves the proxy
passthrough invariant that the real Panthor mapping path will convert payload
GPA spans to HPA-backed GPU PTEs.

This is stronger than individual historical passes but still bounded by smoke
coverage. It does not prove multi-client fairness/isolation, long-run resource
cleanup, reset recovery, PRIME/fd transport, or sustained high-throughput
performance.

## 2026-06-04: GLES Stress Harness Cleanup

### Blacklisted Harness Usage

While preparing a larger GLES compute stress run, two harness invocation mistakes
were found and cleaned up:

1. This form does not pass the intended stress arguments to the script:

```text
GLES_SMOKE_ARGS="--count 4096 --iterations 5 --warmup 1 --perf" \
RUN_ID=...; ./scripts/run/run-vmshm-e2e.sh ...
```

Because the environment assignments are not attached to the script process, the
runner falls back to the default:

```text
GLES smoke args: --count 64
```

That run passed, but it is not stress evidence.

2. This form attaches the temporary environment to the script, but expands
`"$RUN_ID"` for `--run-id` before the temporary assignment is visible to the
current shell:

```text
RUN_ID=vmshm-... GLES_SMOKE_ARGS="..." \
  ./scripts/run/run-vmshm-e2e.sh ... --run-id "$RUN_ID"
```

The workload itself passed with `count=4096`, but the run id was empty and logs
were fetched into the parent `GPU-SFTP/log/shared/vmshm-1client/` directory
instead of a run-specific directory. Those misplaced local files were deleted so
they cannot be mistaken for canonical evidence.

Blacklisted direction:

```text
Do not use same-command temporary environment assignment and also expand that
temporary variable as a shell argument in the same command.
```

Retained command pattern:

```text
run_id=vmshm-...
GLES_SMOKE_ARGS="--count 4096 --iterations 5 --warmup 1 --perf" \
  ./scripts/run/run-vmshm-e2e.sh \
    --skip-build \
    --skip-config-install \
    --skip-sync \
    --gles-compute-smoke \
    --run-id "$run_id"
```

### Remaining Risks

- This is one client VM, one proxy VM, one short compute workload, count 64. It
  does not prove sustained workloads, multi-client sharing, isolation, fairness,
  reset recovery, or memory accounting.
- The runner currently keeps the shared client at 512 MiB because the vmshm
  slots start at GPA `0x20000000`. Raising client RAM to the passthrough
  baseline size would require moving vmshm slots above guest RAM to avoid GPA
  overlap.
- Cache policy still needs stress testing with larger buffers and repeated
  iterations.
- IRQ/fence completion is functionally covered by the successful wait/readback,
  but detailed timing and interrupt accounting should be measured separately.

## 2026-06-04: GLES Compute Stress PASS

After the full one-client ioctl sweep and the first shared GLES compute pass,
a larger repeated GLES compute run was executed with the already-deployed shared
client/proxy artifacts:

```text
run id: vmshm-1client-gles-compute-stress-20260604-065004
command:
run_id=vmshm-1client-gles-compute-stress-20260604-065004
GLES_SMOKE_ARGS="--count 4096 --iterations 5 --warmup 1 --perf" \
  ./scripts/run/run-vmshm-e2e.sh \
    --skip-build \
    --skip-config-install \
    --skip-sync \
    --gles-compute-smoke \
    --run-id "$run_id"
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-gles-compute-stress-20260604-065004
result: PASS
```

Userspace evidence:

```text
GLES smoke args: --count 4096 --iterations 5 --warmup 1 --perf
STAGE=open-drm
STAGE=gbm-create-device
STAGE=egl-initialize
EGL_VERSION=1.5
STAGE=egl-create-context
STAGE=egl-make-current
STAGE=gl-query
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
STAGE=buffer-setup
PERF_CONFIG iterations=5 warmup=1 count=4096 bytes=16384 alu_iters=1
STAGE=perf-loop
COMPUTE_CHECK=PASS count=4096 samples=16 formula=x*3+7+alu_mix alu_iters=1
GPU_SMOKE_RESULT=PASS
RESULT: PASS
```

Proxy/client evidence shows repeated nonzero command submission, timeline waits,
and vmshm-backed payload mapping through the real Panthor path:

```text
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffd4000 size=0x10000 spans=1 first_gpa=0x0000000023e20000
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffcc000 size=0x8000 spans=1 first_gpa=0x0000000023e30000
panthor-proxy: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=1 first_stream=0x7ffffffcc000 first_size=160 first_latest_flush=0x0 ret=0
panthor-proxy: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=2 first_stream=0x7ffffffcc000 first_size=160 first_latest_flush=0x0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
panthor-client: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=2 first_stream=0x7ffffffcc000 first_size=160 first_latest_flush=0x0
panthor-client: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0
```

One proxy log entry showed a short timeline wait timeout while Mesa was polling:

```text
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=4294967295 ret=-62
```

This is not classified as a failure for this run because later timeline waits
succeeded, the final GPU fence wait succeeded, the readback check passed, and
the result file ended with `RESULT: PASS`.

The fetched run directory was scanned for panic, Oops, call trace, BUG,
WARNING, WARN, ERROR, FAIL, TIMEOUT, timed-out jobs, GPU faults, mismatches,
and software-renderer markers. No failure signal was found.

## 2026-06-04: Unsupported fd/PRIME IOCTL Rejection

### Goal

Close a semantic hole in the virtual Panthor frontend. `DRIVER_GEM` and
`DRIVER_SYNCOBJ` are now enabled because Mesa needs GEM and syncobj semantics,
but fd-based DRM core ioctls are not safe to expose in the client VM unless a
real cross-VM fd/grant/eventfd design exists.

The intentionally unsupported ioctls are:

```text
DRM_IOCTL_PRIME_HANDLE_TO_FD
DRM_IOCTL_PRIME_FD_TO_HANDLE
DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD
DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE
DRM_IOCTL_SYNCOBJ_EVENTFD
```

### Design

- `panthor-client` now overrides `DRM_IOCTL_GET_CAP` for `DRM_CAP_PRIME` and
  reports `0`, instead of allowing DRM core to advertise PRIME import/export.
- `panthor-client` explicitly returns `-EOPNOTSUPP` for PRIME fd import/export,
  syncobj fd import/export, and syncobj eventfd registration.
- `compat_ioctl` now routes the virtualized DRM core ioctls back through
  `panthor_client_ioctl()` before falling back to `drm_compat_ioctl()`. This
  prevents 32-bit userspace from bypassing the virtual handle namespace or the
  explicit fd/PRIME rejection.
- The userspace basic ioctl smoke now checks `DRM_CAP_PRIME=0` and verifies the
  unsupported fd/eventfd ioctls fail.

This is a deliberate negative capability, not an incomplete optional feature.
The blacklisted direction remains:

```text
Do not raw-forward process-local fd numbers, dma-buf fds, or eventfd-backed
syncobj notification across client/proxy VMs.
```

If PRIME, sync-file export/import, or syncobj eventfd becomes required later,
it needs a new explicit cross-VM fd/grant/eventfd protocol and tests.

### Validation

The shared client/proxy kernels were rebuilt and installed, the ioctl smoke
payload was rebuilt, artifacts were synced, and the basic ioctl smoke passed:

```text
run id: vmshm-1client-basic-fd-reject-20260604-071027
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-firecracker-build \
  --ioctl-smoke \
  --run-id vmshm-1client-basic-fd-reject-20260604-071027
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-basic-fd-reject-20260604-071027
result: PASS
```

After updating the runner result summary grep to include `PRIME_` evidence, a
skip-build/skip-sync rerun also passed:

```text
run id: vmshm-1client-basic-fd-reject-summary-20260604-071238
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --skip-config-install \
  --skip-sync \
  --ioctl-smoke \
  --run-id vmshm-1client-basic-fd-reject-summary-20260604-071238
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-basic-fd-reject-summary-20260604-071238
result: PASS
```

Key evidence from the rerun:

```text
GET_CAP DRM_CAP_PRIME=0
PRIME_HANDLE_TO_FD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
PRIME_FD_TO_HANDLE_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_HANDLE_TO_FD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_FD_TO_HANDLE_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_EVENTFD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
PANTHOR_BASIC_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=BASIC_PASS
RESULT: PASS
```

The fetched run directory was scanned for panic, Oops, call trace, BUG,
WARNING, WARN, ERROR, FAIL, TIMEOUT, timed-out jobs, GPU faults, mismatches,
and software-renderer markers. No failure signal was found.

## 2026-06-04: Full IOCTL Sweep After fd/PRIME Rejection PASS

After explicitly rejecting fd/PRIME/eventfd-based ioctls in the client frontend,
the complete currently-supported one-client ioctl smoke suite was rerun with
the deployed shared client/proxy artifacts:

```text
base run id: vmshm-1client-fd-reject-full-sweep-20260604-071449
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-fd-reject-full-sweep-20260604-071449-*
```

Results:

```text
ioctl-smoke                  PANTHOR_IOCTL_SMOKE=BASIC_PASS                  PASS
vm-create-smoke              PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS              PASS
bo-create-smoke              PANTHOR_IOCTL_SMOKE=BO_CREATE_PASS              PASS
bo-lifecycle-smoke           PANTHOR_IOCTL_SMOKE=BO_LIFECYCLE_PASS           PASS
bo-mmap-smoke                PANTHOR_IOCTL_SMOKE=BO_MMAP_PASS                PASS
vm-bind-smoke                PANTHOR_IOCTL_SMOKE=VM_BIND_PASS                PASS
vm-bind-async-sync-smoke     PANTHOR_IOCTL_SMOKE=VM_BIND_ASYNC_SYNC_PASS     PASS
vm-state-flush-smoke         PANTHOR_IOCTL_SMOKE=VM_STATE_FLUSH_PASS         PASS
syncobj-lifecycle-smoke      PANTHOR_IOCTL_SMOKE=SYNCOBJ_LIFECYCLE_PASS      PASS
syncobj-wait-smoke           PANTHOR_IOCTL_SMOKE=SYNCOBJ_WAIT_PASS           PASS
syncobj-transfer-smoke       PANTHOR_IOCTL_SMOKE=SYNCOBJ_TRANSFER_PASS       PASS
syncobj-timeline-wait-smoke  PANTHOR_IOCTL_SMOKE=SYNCOBJ_TIMELINE_WAIT_PASS  PASS
syncobj-signal-query-smoke   PANTHOR_IOCTL_SMOKE=SYNCOBJ_SIGNAL_QUERY_PASS   PASS
group-lifecycle-smoke        PANTHOR_IOCTL_SMOKE=GROUP_LIFECYCLE_PASS        PASS
group-submit-syncpoint-smoke PANTHOR_IOCTL_SMOKE=GROUP_SUBMIT_SYNCPOINT_PASS PASS
tiler-heap-lifecycle-smoke   PANTHOR_IOCTL_SMOKE=TILER_HEAP_LIFECYCLE_PASS   PASS
```

All 16 fetched result files contain `RESULT: PASS`. Every mode also repeated the
basic negative capability checks:

```text
GET_CAP DRM_CAP_PRIME=0
PRIME_HANDLE_TO_FD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
PRIME_FD_TO_HANDLE_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_HANDLE_TO_FD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_FD_TO_HANDLE_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_EVENTFD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
```

The sweep-wide log scan found no panic, Oops, call trace, BUG, WARNING, WARN,
ERROR, real FAIL, TIMEOUT, timed-out job, GPU fault, mismatch, llvmpipe,
softpipe, or software-renderer marker. The only `failure` strings are expected
negative ioctl checks.

This proves the fd/PRIME hardening did not regress the currently-supported
one-client virtualization surface. The two-memslot rule remains intact:
transient ioctl arrays stay flattened in `vmshm-comm`, while BO payloads and
client-mappable GPU data live in `vmshm-object`.

Remaining limits:

- no proof of multi-client isolation, sharing policy, fairness, or reset
  recovery
- no cross-VM fd, dma-buf, sync-file, or syncobj-eventfd transport design
- no long-run leak, memory-pressure, or high-throughput performance proof
- zero-length `GROUP_SUBMIT` remains protocol/sync plumbing evidence, not
  shader execution evidence

## 2026-06-04: Post-hardening GLES Compute Stress PASS

After the fd/PRIME rejection sweep, a repeated GLES compute workload was run
again to confirm the real GPU execution path still works:

```text
run id: vmshm-1client-post-fd-reject-gles-stress-20260604-072537
command:
run_id=vmshm-1client-post-fd-reject-gles-stress-20260604-072537
GLES_SMOKE_ARGS="--count 4096 --iterations 5 --warmup 1 --perf" \
  ./scripts/run/run-vmshm-e2e.sh \
    --skip-build \
    --skip-config-install \
    --skip-sync \
    --gles-compute-smoke \
    --run-id "$run_id"
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-post-fd-reject-gles-stress-20260604-072537
result: PASS
```

Userspace evidence:

```text
GLES smoke args: --count 4096 --iterations 5 --warmup 1 --perf
EGL_VERSION=1.5
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
PERF_CONFIG iterations=5 warmup=1 count=4096 bytes=16384 alu_iters=1
COMPUTE_CHECK=PASS count=4096 samples=16 formula=x*3+7+alu_mix alu_iters=1
GPU_SMOKE_RESULT=PASS
RESULT: PASS
```

Proxy/client logs show repeated nonzero command streams, sync waits, and
vmshm-backed payloads being mapped through the real proxy Panthor path:

```text
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffcc000 size=0x8000 spans=1 first_gpa=0x0000000023e30000
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffbc000 size=0x10000 spans=1 first_gpa=0x0000000023e40000
panthor-proxy: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=2 first_stream=0x7ffffffb4000 first_size=160 first_latest_flush=0x0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
```

Two early timeline waits returned `-62` while Mesa was polling. They are not
classified as failures because later timeline waits succeeded, the final fence
wait succeeded, userspace readback passed, and the result ended with
`RESULT: PASS`.

The fetched run directory was scanned for panic, Oops, call trace, BUG,
WARNING, WARN, ERROR, FAIL, TIMEOUT, timed-out jobs, GPU faults, mismatches,
and software-renderer markers. No failure signal was found.

This run strengthens the current one-client evidence in four areas:

- repeated nonzero `GROUP_SUBMIT` through the client/proxy ioctl path
- proxy real Panthor `VM_BIND` mapping vmshm-backed BO payloads
- syncobj/timeline wait behavior across repeated dispatches
- client CPU readback coherence after real GPU writes to shared BO backing

It still does not prove multi-client fairness/isolation, reset recovery,
long-run leak freedom, PRIME/fd transport, or sustained performance under
large memory pressure. The next useful stress direction is either a larger
single-client GLES run with more ALU work and larger buffers, or explicit
two-client namespace/isolation tests.

## 2026-06-04: One-client shared GPU virtualization final status

This section records the current end state after the ioctl sweep and the final
GLES compute rerun.  It is intentionally more detailed than the incremental
notes above so the next round of work can start from a stable design boundary
instead of rediscovering the same constraints.

### Scope that is now implemented and tested

The implemented scope is:

```text
one proxy VM + one client VM

client VM userspace /dev/dri/card0 or renderD128
  -> panthor-client DRM frontend
  -> client_vmshm_comm / vmshm-comm RPC
  -> vmshm-broker notify relay
  -> proxy_vmshm_comm
  -> panthor-proxy
  -> real proxy-side DRM_PANTHOR
  -> physical Mali-G610 through the custom passthrough path
```

The current code and tests support a complete one-client Panthor userspace
path: device discovery, VM creation, BO creation and mmap, VM_BIND, syncobj and
timeline waits, group creation, nonzero GROUP_SUBMIT, tiler heap lifecycle,
cleanup, and client CPU readback after real GPU execution.

The current scope does not claim:

- multiple concurrent client VMs
- fair scheduling or resource partition across clients
- reset recovery after a proxy GPU reset
- PRIME/dma-buf/sync-file/eventfd transport across VM boundaries
- long-run leak freedom under days of churn
- high-pressure performance behavior with many large BOs

Those items are listed under "Remaining design work" below and should remain
explicitly out of the one-client completion claim.

### Implemented design: two vmshm memslots

The two-memslot design is now the core invariant of the shared GPU path:

```text
vmshm-comm:
  small control messages, RPC metadata, flattened ioctl arrays, return values

vmshm-object:
  BO payloads and other memory that client userspace or the real GPU must
  directly read/write/map
```

The implemented Panthor control ABI keeps transient ioctl data inside the
512-byte `vmshm-comm` message slots.  Examples:

- `VM_BIND ops[]`
- `VM_BIND syncs[]`
- `SYNCOBJ_WAIT handles[]`
- `SYNCOBJ_TIMELINE_WAIT handles[]/points[]`
- `SYNCOBJ_RESET/SIGNAL handles[]`
- `SYNCOBJ_TIMELINE_SIGNAL/QUERY handles[]/points[]`
- `GROUP_CREATE queues[]`
- `GROUP_SUBMIT jobs[]/syncs[]`

These arrays are not client-mappable objects.  They describe a single ioctl
transaction and are copied, checked, translated, and discarded.

The object/data memslot is reserved for payloads with real sharing semantics:

- shader/code BOs
- command stream BOs
- descriptor/state BOs
- SSBO/UBO/storage BOs
- Mesa/Panthor queue and context backing BOs
- tiler/context backing that must be GPU-visible through BOs
- future fence/event pages, if a real design is added

This avoids the failed direction of using vmshm-object as a generic large ioctl
scratchpad.  That direction is blacklisted because it weakens ownership,
permission checks, and lifetime handling while bringing no value for transient
metadata.

```text
BLACKLISTED:
  placing transient ioctl arrays in vmshm-object

REASON:
  they are not shared payloads, do not need client mmap access, and should stay
  as bounded control-plane RPC metadata.
```

### Implemented design: client/proxy sessions and handle namespaces

Every client DRM open creates a proxy session.  The proxy session owns a real
Panthor session and all object maps for that open:

```text
client drm_file / panthor_client_file
  -> session_id
  -> proxy panthor_proxy_session
  -> real panthor_vmshm_session
```

The virtualized handle namespaces are:

```text
client VM id      -> proxy VM id
client BO handle  -> proxy GEM handle + vmshm payload object
client syncobj    -> proxy syncobj handle
client group      -> proxy group handle
client tiler heap -> proxy tiler heap handle
```

The client-visible handles are never trusted as proxy handles.  The proxy always
looks up the client handle inside the owning session before calling the real
Panthor helper.  This is the current safety boundary for one-client correctness,
and it is also the base needed for future multi-client isolation.

Close and cleanup now matter as much as creation.  `GEM_CLOSE`,
`SYNCOBJ_DESTROY`, `GROUP_DESTROY`, `TILER_HEAP_DESTROY`, `VM_DESTROY`, and
`CLOSE_SESSION` are all part of the supported surface.  Session release remains
the final cleanup net if userspace exits early or skips some destroy calls.

### Implemented design: discovery and capabilities

The client VM exposes a Panthor-compatible DRM frontend instead of a private
test-only character device.  Mesa sees:

```text
VERSION name=panthor
DRM_CAP_SYNCOBJ=1
DRM_CAP_SYNCOBJ_TIMELINE=1
DRM_CAP_PRIME=0
```

The frontend forwards Panthor `DEV_QUERY` to the proxy and returns real
GPU/CSIF information:

```text
GPU_INFO gpu_id=0xa8670005 ...
CSIF_INFO csg_slots=8 cs_slots=8 ...
```

`DRM_CAP_PRIME=0` is intentional.  The current design supports virtual GEM/BO
and syncobj semantics, but it does not support passing fd-backed resources
between VMs.

The following ioctls are explicitly unsupported and must stay rejected until a
real cross-VM fd/eventfd/dma-buf protocol exists:

```text
DRM_IOCTL_PRIME_HANDLE_TO_FD
DRM_IOCTL_PRIME_FD_TO_HANDLE
DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD
DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE
DRM_IOCTL_SYNCOBJ_EVENTFD
```

```text
BLACKLISTED:
  raw-forwarding fd numbers, dma-buf fds, sync-file fds, or eventfd-backed
  syncobj notification across client/proxy VMs

REASON:
  fd values are process-local and VM-local.  Passing the integer would not pass
  the referenced kernel object, ownership, lifetime, poll state, or security
  context.
```

### Implemented design: BO and mmap data plane

BO creation is no longer only a fake client handle.  The proxy allocates a
vmshm payload object, creates or registers a proxy-side Panthor BO backed by
that payload, and returns the metadata needed by the client frontend.

Client mmap uses a client-local fake DRM mmap offset:

```text
client BO_MMAP_OFFSET
  -> client fake offset
  -> client .mmap lookup
  -> validated vmshm-object descriptor
  -> map payload pages into client userspace VMA
```

The proxy DRM mmap offset is not returned to the client.  It belongs to the
proxy DRM file namespace and is meaningless in the client VM.  The client can
only map payloads it has received through its own BO table and object
descriptor path.

The important data-plane property now validated by the BO mmap smoke and GLES
compute run is:

```text
client CPU writes the BO payload
  -> proxy real Panthor VM_BIND maps the same payload backing
  -> physical GPU reads/writes those pages
  -> client CPU reads the result through the same payload mapping
```

`DRM_PANTHOR_BO_NO_MMAP` remains enforced: the BO can be GPU-visible but cannot
be mapped into client userspace.

### Implemented design: VM_BIND with proxy passthrough constraints

`VM_BIND` is implemented as a flattened RPC.  The client copies user arrays,
translates local handles, and sends bounded metadata through `vmshm-comm`.
The proxy translates the client VM id, BO handles, and syncobj handles before
calling the real Panthor VM_BIND helper.

Supported VM_BIND cases:

- synchronous MAP
- synchronous UNMAP
- async MAP
- async UNMAP
- async SYNC_ONLY
- VM_BIND sync arrays and returned failed-op state

The payload mapping evidence is visible in proxy logs:

```text
panthor: VM_BIND vmshm payload mapped iova=... size=... spans=... first_gpa=...
panthor-proxy: VM_BIND session=... client_vm=... proxy_vm=... ops=... ret=0
```

Because the proxy VM uses the custom GPU passthrough path, a successful
proxy-side VM_BIND is not just ordinary guest memory management.  The real GPU
will walk page tables created inside the proxy guest, so the passthrough page
table invariant must hold:

```text
TTBR/root table address: HPA
non-leaf table descriptor: HPA
leaf BO/heap/buffer PTE: HPA
```

The Panthor custom io-pgtable path must continue to translate GPA to HPA by
hypercall and must preserve 4K-correct map/unmap behavior.  Contiguous GPA in
the proxy guest must never be assumed to imply contiguous HPA.

```text
BLACKLISTED:
  writing GPA into GPU-visible Panthor TTBR/table descriptors/leaf PTEs in the
  proxy passthrough VM

REASON:
  the physical GPU does not perform KVM stage-2 translation while walking its
  own GPU page tables.  A GPA in a GPU PTE is interpreted as a host physical
  address and causes wrong memory access, GPU faults, or job timeouts.
```

### Implemented design: syncobj and timeline synchronization

The virtual sync path now mirrors sync objects into the proxy session:

```text
client syncobj handle
  -> proxy syncobj handle
  -> real Panthor submit/VM_BIND waits and signals
  -> client wait/query observes proxy completion state
```

Implemented sync ioctl surface:

- `SYNCOBJ_CREATE`
- `SYNCOBJ_DESTROY`
- `SYNCOBJ_WAIT`
- `SYNCOBJ_TRANSFER`
- `SYNCOBJ_TIMELINE_WAIT`
- `SYNCOBJ_RESET`
- `SYNCOBJ_SIGNAL`
- `SYNCOBJ_TIMELINE_SIGNAL`
- `SYNCOBJ_QUERY`

The wait path uses relative timeout semantics in the transport instead of
blindly forwarding the client VM's absolute monotonic timestamp.  This matters
because client and proxy VM monotonic clocks are not guaranteed to match.

Short timeline wait timeouts such as `ret=-62` can be valid Mesa polling.  They
are not treated as failures when later waits succeed, final fences signal, and
readback passes.

### Implemented design: group, submit, and tiler heap

The group and submit path now reaches real GPU execution:

```text
GROUP_CREATE
  -> translate client VM id
  -> create real proxy Panthor group
  -> return client group handle

GROUP_SUBMIT
  -> flatten queue submit and sync arrays in vmshm-comm
  -> translate group and sync handles
  -> preserve stream_addr as GPU VA
  -> call real proxy Panthor submit
  -> wait/query proxy syncobj completion from client
```

Important rule: `stream_addr` is a GPU virtual address, not a user pointer and
not a shared-memory offset.  It must remain the same value Mesa wrote into its
command stream.  The BO handle and sync handles are translated; GPU VA is not.

`TILER_HEAP_CREATE/DESTROY` is supported and mapped through a client heap handle
to a proxy heap handle.  The proxy heap handle must not be raw-returned as the
client handle because real Panthor heap handles can encode VM-related state.

Zero-length submit smoke proves submit/sync plumbing.  It is useful but is not
treated as proof of shader execution.  The GLES compute run provides the real
nonzero command-stream evidence.

### Implemented design: interrupt and completion dependency

The shared virtualization path still depends on the proxy VM's passthrough IRQ
implementation.  Real GPU completion requires this chain:

```text
physical GPU IRQ
  -> host pmthor IRQ handler
  -> eventfd trigger
  -> KVM irqfd
  -> proxy guest GPU/JOB/MMU IRQ
  -> guest Panthor IRQ handler and scheduler completion
  -> KVM resamplefd/EOI
  -> host pmthor unmask
  -> proxy syncobj signal
  -> client wait returns
```

If this chain regresses, `GROUP_SUBMIT` may return 0 while timeline waits,
final waits, or readback fail.  Therefore the final validation requires both
nonzero submit evidence and successful sync/readback, not only submit return
codes.

### Final validation run: static checks

The final local static/build checks passed:

```text
bash -n scripts/run/run-vmshm-e2e.sh
git diff --check
git -C Linux-Guest-GPU diff --check
GPU-SFTP/tests/panthor-ioctl-smoke/build.sh
```

The smoke build refreshed:

```text
GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke
```

### Final validation run: runner cleanup basic smoke

A basic skip-build ioctl smoke was run to validate the runner cleanup and the
negative fd/PRIME checks:

```text
run id: vmshm-1client-runner-cleanup-basic-20260604-074651
command:
./scripts/run/run-vmshm-e2e.sh \
  --skip-build \
  --skip-config-install \
  --skip-sync \
  --ioctl-smoke \
  --run-id vmshm-1client-runner-cleanup-basic-20260604-074651
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-runner-cleanup-basic-20260604-074651
result: PASS
```

Key evidence:

```text
VERSION name=panthor
GET_CAP DRM_CAP_SYNCOBJ=1
GET_CAP DRM_CAP_SYNCOBJ_TIMELINE=1
GET_CAP DRM_CAP_PRIME=0
PRIME_HANDLE_TO_FD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
PRIME_FD_TO_HANDLE_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_HANDLE_TO_FD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_FD_TO_HANDLE_UNSUPPORTED expected_failure errno=95 (Operation not supported)
SYNCOBJ_EVENTFD_UNSUPPORTED expected_failure errno=95 (Operation not supported)
PANTHOR_BASIC_SMOKE=PASS
PANTHOR_IOCTL_SMOKE=BASIC_PASS
RESULT: PASS
```

### Final validation run: complete ioctl sweep

The full one-client ioctl sweep passed after the runner cleanup:

```text
base run id: vmshm-1client-runner-cleanup-full-sweep-20260604-074833
summary:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-runner-cleanup-full-sweep-20260604-074833-summary/summary.txt
logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-runner-cleanup-full-sweep-20260604-074833-*
result: PASS
```

Mode results:

```text
ioctl-smoke                      BASIC_PASS                       PASS
vm-create-smoke                  VM_CREATE_PASS                   PASS
bo-create-smoke                  BO_CREATE_PASS                   PASS
bo-lifecycle-smoke               BO_LIFECYCLE_PASS                PASS
bo-mmap-smoke                    BO_MMAP_PASS                     PASS
vm-bind-smoke                    VM_BIND_PASS                     PASS
vm-bind-async-sync-smoke         VM_BIND_ASYNC_SYNC_PASS          PASS
vm-state-flush-smoke             VM_STATE_FLUSH_PASS              PASS
syncobj-lifecycle-smoke          SYNCOBJ_LIFECYCLE_PASS           PASS
syncobj-wait-smoke               SYNCOBJ_WAIT_PASS                PASS
syncobj-transfer-smoke           SYNCOBJ_TRANSFER_PASS            PASS
syncobj-timeline-wait-smoke      SYNCOBJ_TIMELINE_WAIT_PASS       PASS
syncobj-signal-query-smoke       SYNCOBJ_SIGNAL_QUERY_PASS        PASS
group-lifecycle-smoke            GROUP_LIFECYCLE_PASS             PASS
group-submit-syncpoint-smoke     GROUP_SUBMIT_SYNCPOINT_PASS      PASS
tiler-heap-lifecycle-smoke       TILER_HEAP_LIFECYCLE_PASS        PASS
SWEEP_RESULT=PASS
```

The sweep-wide hidden failure scan found no panic, Oops, BUG, warning, GPU
fault, job timeout, mismatch, software-renderer marker, or real failure.  The
only negative strings in the logs are the expected unsupported ioctl checks.

### Final validation run: GLES compute through userspace driver

A final GLES compute run was executed through the current runner and artifacts:

```text
run id: vmshm-1client-final-gles-compute-20260604-075823
command:
GLES_SMOKE_ARGS="--count 1024 --iterations 2 --warmup 1 --perf" \
  ./scripts/run/run-vmshm-e2e.sh \
    --skip-build \
    --skip-config-install \
    --skip-sync \
    --gles-compute-smoke \
    --run-id vmshm-1client-final-gles-compute-20260604-075823
local logs:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-final-gles-compute-20260604-075823
result: PASS
```

Userspace evidence:

```text
EGL_VERSION=1.5
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
PERF_CONFIG iterations=2 warmup=1 count=1024 bytes=4096 alu_iters=1
COMPUTE_CHECK=PASS count=1024 samples=16 formula=x*3+7+alu_mix alu_iters=1
GPU_SMOKE_RESULT=PASS
RESULT: PASS
```

Proxy/client evidence:

```text
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffcf000 size=0x8000 spans=1 first_gpa=0x0000000023e30000
panthor: VM_BIND vmshm payload mapped iova=0x7ffffffbf000 size=0x10000 spans=1 first_gpa=0x0000000023e40000
panthor-proxy: GROUP_SUBMIT session=1 client_group=1 proxy_group=1 jobs=1 syncs=2 first_stream=0x7ffffffcf000 first_size=160 first_latest_flush=0x0 ret=0
panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=1 count=1 flags=0x1 first=0 ret=0
panthor-proxy: SYNCOBJ_WAIT session=1 count=1 flags=0x0 first=0 ret=0
```

The final GLES run was scanned for panic, Oops, BUG, warnings, GPU faults, job
timeouts, mismatches, software renderer, `GPU_SMOKE_RESULT=FAIL`, and
`COMPUTE_CHECK=FAIL`.  No hidden failure signal was found.  The short
`SYNCOBJ_TIMELINE_WAIT ret=-62` entries are Mesa polling and are covered by
later successful waits plus final `COMPUTE_CHECK=PASS`.

### Remaining design work

The one-client objective is satisfied by the current evidence, but the project
is not a complete production multi-VM GPU sharing system.  The next work should
be explicit and should not be mixed into the one-client completion claim.

#### 1. Multi-client isolation and namespace tests

Needed:

- two-client launch using the shared virtualization path
- independent per-client sessions
- handle namespace collision tests for VM/BO/syncobj/group/heap ids
- one client closing or crashing while another continues
- no cross-client BO mapping or syncobj access by guessed handle
- explicit owner VMID/grant validation in every object descriptor path

The current one-client maps are the right shape, but one-client evidence cannot
prove isolation.

#### 2. Scheduling, fairness, and resource partition

Needed:

- per-client memory accounting
- per-client BO and VM quotas
- group/queue count quotas
- priority policy, especially whether client RT/high priorities are allowed
- optional core mask or CSG slot partitioning
- starvation tests with two clients submitting concurrently
- accounting for vmshm-object pressure and proxy real Panthor memory pressure

Current `DEV_QUERY` exposes real device resources.  A real sharing product may
need to expose virtualized resource limits instead.

#### 3. Reset recovery and fault containment

Needed:

- behavior when proxy real Panthor reports group fatal fault
- behavior when VM becomes unusable
- behavior after GPU reset in the proxy passthrough VM
- mapping from proxy reset/fault state back to client sessions
- explicit invalidation of stale client handles after reset
- tests proving one bad client does not silently corrupt another client

The current code proves normal completion, not reset recovery.

#### 4. Long-run lifecycle and leak testing

Needed:

- repeated open/close loops
- repeated BO/mmap/VM_BIND/unmap/GEM_CLOSE loops
- repeated syncobj create/wait/destroy loops
- repeated GLES workload loops
- proxy session release accounting after client crash/poweroff
- slab/page/payload object leak checks in both client and proxy VMs

The smoke tests cover semantics, not long-run leak freedom.

#### 5. Cache and memory-coherency refinement

Needed:

- formal cache policy for client BO mmap
- submit-time flush strategy for dirty client CPU writes
- wait/readback invalidate strategy for GPU-written BOs
- tracking which BO ranges were CPU-written or GPU-written
- tests that deliberately reuse BOs across many dispatches and validate no stale
  readback

The current compute pass proves the present workload is coherent enough.  It is
not yet a complete cache-maintenance design for all workloads.

#### 6. Non-contiguous payload objects

Needed:

- segment-list descriptor support if vmshm-object allocation becomes
  non-contiguous
- proxy-owned segment metadata with generation/permission checks
- client descriptor validation without writable metadata exposure
- VM_BIND mapping that preserves 4K GPA-to-HPA correctness for each segment

Until this is designed, prefer contiguous payload objects for tested BO paths.

#### 7. Performance and transport scalability

Needed:

- concurrent RPC or pipelined control transport if Mesa workloads become
  bottlenecked by serialized `client_comm_vmshm_call()`
- larger queue depth or backpressure policy
- latency measurement for DEV_QUERY, BO_CREATE, VM_BIND, GROUP_SUBMIT, and waits
- broker CPU overhead measurement when `perf` is available
- comparison against single-VM passthrough baseline for representative workloads

The current result includes simple comm perf selftests, but not a full GPU
sharing performance model.

#### 8. Cross-VM fd/dma-buf/eventfd support, if ever required

Needed only if the project deliberately chooses to support these UAPIs later:

- cross-VM fd broker, not raw fd integer forwarding
- dma-buf export/import lifetime and permission model
- sync-file export/import semantics
- eventfd registration and notification relay model
- revoke behavior when either VM closes the object
- negative tests proving stale or forged ids fail

Until then, fd/PRIME/eventfd support remains blacklisted and explicitly
rejected.

### Completion statement for the current goal

For the declared one-client goal, the current implementation has reached:

```text
all virtualized ioctl smoke modes pass
real Mesa/Panfrost GLES compute task passes through client -> proxy -> GPU
two-memslot control/object rule preserved
proxy passthrough VM_BIND evidence present
fd/PRIME/eventfd unsafe paths explicitly rejected
final logs scanned without hidden panic/Oops/GPU fault/job timeout/mismatch
docs updated with implemented design and remaining work
```

This is the point where the one-client shared GPU virtualization goal can be
closed.  Future work should reopen the project under a multi-client,
reset-recovery, or performance-hardening objective rather than treating those
as missing pieces of the completed one-client milestone.

## 2026-06-04: 4 MiB Shared GLES Smoke Performance

This is the first same-size performance check after the one-client shared
virtualization path started running real Mesa/Panfrost GLES compute through:

```text
client VM -> panthor-client -> vmshm-comm/vmshm-object -> broker ->
proxy VM -> panthor-proxy -> proxy passthrough Panthor -> physical GPU
```

Command:

```bash
GLES_SMOKE_ARGS="--count 1048576 --iterations 100 --warmup 5 --perf" \
  ./scripts/run/run-vmshm-e2e.sh \
    --skip-build --skip-config-install --skip-sync \
    --gles-compute-smoke \
    --run-id vmshm-1client-perf-4m-20260604-100018
```

Local logs:

```text
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-4m-20260604-100018
```

Result:

```text
RESULT: PASS
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
PERF_CONFIG iterations=100 warmup=5 count=1048576 bytes=4194304 alu_iters=1
COMPUTE_CHECK=PASS count=1048576 samples=16 formula=x*3+7+alu_mix alu_iters=1
```

No hidden panic, Oops, GPU fault, job timeout, mismatch, timeout, or smoke
failure marker was found in the fetched local logs.

The comparison uses the existing formal passthrough baseline:

```text
GPU-SFTP/log/passthrough/perf/gpu-perf-logpath-passthrough-20260603-174020
```

Metric is `host/current-path`; closer to `1.000` means closer to host direct
performance.

| Path | 4 MiB iter_total avg | Host/current-path |
| --- | ---: | ---: |
| Host direct | 3140.41 us | 1.000 |
| Single-VM passthrough | 3986.15 us | 0.788 |
| One-client shared virtualization | 21854.55 us | 0.144 |

Derived comparison:

| Comparison | Value |
| --- | ---: |
| passthrough overhead vs host | 26.93% |
| shared overhead vs host | 595.91% |
| shared slowdown vs passthrough | 5.48x |
| shared throughput relative to passthrough | 18.24% |

Per-phase averages:

| Phase | Host | Passthrough | Shared | Shared / passthrough |
| --- | ---: | ---: | ---: | ---: |
| cpu_prepare | 1778.64 us | 1960.09 us | 1770.35 us | 0.90x |
| buffer_upload | 732.70 us | 888.56 us | 812.61 us | 0.91x |
| dispatch_call | 211.83 us | 266.19 us | 14275.60 us | 53.63x |
| memory_barrier | 40.64 us | 38.68 us | 3605.15 us | 93.20x |
| map_wait | 374.71 us | 830.12 us | 1388.12 us | 1.67x |
| unmap | 1.89 us | 2.51 us | 2.72 us | 1.08x |
| iter_total | 3140.41 us | 3986.15 us | 21854.55 us | 5.48x |

Current interpretation:

- `cpu_prepare` and `buffer_upload` are not the dominant regression; the shared
  run is roughly comparable to the passthrough baseline in those phases.
- The main cost is in command submission and completion synchronization:
  `dispatch_call` grows from 266.19 us in passthrough to 14275.60 us in shared,
  and `memory_barrier` grows from 38.68 us to 3605.15 us.
- This matches the current architecture: GLES submit/wait traffic crosses the
  serialized shared-memory RPC path, then the proxy VM drives the real GPU
  through the project's passthrough stack, whose interrupt and memory-management
  behavior is already different from native host execution.
- The result should be treated as a functional performance snapshot, not a
  final optimized baseline.  16 MiB and 64 MiB were intentionally not tested in
  this run because their stability is not yet guaranteed.

## 2026-06-04: 16/64 MiB Shared GLES Smoke Performance and Object Memslot Resize

This follow-up extends the shared virtualization smoke performance check from
4 MiB to 16 MiB and 64 MiB.  The test keeps the same metric used by the
passthrough baseline:

```text
host/current-path = Host direct iter_total avg / current-path iter_total avg
```

Closer to `1.000` means the tested path is closer to native host direct
execution.

The shared path under test is still the one-client architecture:

```text
client VM userspace
  -> panthor-client
  -> vmshm-comm / vmshm-object
  -> vmshm-broker
  -> panthor-proxy
  -> proxy VM passthrough Panthor
  -> physical GPU
```

The proxy VM does not drive the GPU as a normal host process.  It reaches the
GPU through the project's passthrough machinery, so the proxy side inherits the
passthrough path's different interrupt delivery and memory-management behavior.
The shared virtualization numbers below therefore include both the current
client/proxy RPC overhead and the proxy VM's passthrough execution costs.

### Memslot issue found at 64 MiB

The original one-client object window was exactly 64 MiB:

```text
vmshm-object GPA  = 0x20000000
vmshm-object size = 0x04000000
vmshm-comm GPA    = 0x24000000
vmshm-comm size   = 0x02000000
```

That is enough for smaller BOs, but it is not enough for a 64 MiB compute
workload.  The main GLES BO alone requests a 64 MiB payload, while Mesa also
allocates small auxiliary BOs for descriptors, state, and driver bookkeeping.
With a 64 MiB `vmshm-object` window, the main BO and the allocator reserve area
consume the available object space before those auxiliary BOs can be satisfied.

Failed run:

```text
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-64m-20260604-101419
```

Failure evidence:

```text
registered vmshm window ... gpa=0x20000000 size=0x4000000
proxy_manager_vmshm: manager ready base=0x0000000020000000 size=0x4000000 alloc=[0x200000,0x3e00000]
MESA: error: DRM_IOCTL_PANTHOR_BO_CREATE failed (err=12)
RESULT: FAIL
```

This confirms that `vmshm-object` should be sized for the largest client-visible
BO plus allocator reserve and Mesa/Panthor auxiliary objects.  The two-memslot
rule remains unchanged:

- `vmshm-comm` carries control/RPC metadata and transient flattened ioctl
  arrays.
- `vmshm-object` carries BO payloads and other structures that must be directly
  visible to the client VM, proxy VM, or GPU mapping path.

### Rejected 256 MiB low-GPA attempt

A direct attempt to raise `vmshm-object` to 256 MiB at `0x30000000` failed
before the GPU smoke test could run:

```text
vmshm-object GPA  = 0x30000000
vmshm-object size = 0x10000000
range             = 0x30000000 - 0x40000000
```

Failed run:

```text
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-64m-object256m-20260604-102211
```

Failure evidence:

```text
registered vmshm window ... gpa=0x30000000 size=0x10000000
GICv3: /intc: no distributor detected, giving up
panthor-client: DEV_QUERY selftest failed (-19)
VFS: Cannot open root device "/dev/vda" or unknown-block(0,0): error -6
RESULT: FAIL
```

This was not a BO virtualization failure.  The 256 MiB low-GPA window extends
up to `0x40000000`, which collides with or crowds the low Firecracker device
layout used by these small VMs.  The result is early platform breakage
including GIC/rootfs symptoms.

### Working 128 MiB one-client layout

The working configuration keeps the control window unchanged and moves the
object/data window away from the old 64 MiB range while staying below the
problematic `0x40000000` boundary:

```text
vmshm-object GPA  = 0x30000000
vmshm-object size = 0x08000000
range             = 0x30000000 - 0x38000000

vmshm-comm GPA    = 0x24000000
vmshm-comm size   = 0x02000000

client doorbell   = 0x2f000000
proxy doorbell    = 0x2f100000
```

Updated one-client config files:

```text
scripts/run/run-vmshm-e2e.sh
GPU-SFTP/firecracker-bins/scripts/shared/vmshm-1client/install-vmshm-irq-configs.sh
GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/broker-config.toml
GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/client-vm-config.json
GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/proxy-vm-config.json
```

The two-client configuration was intentionally not changed by this test.  It
should receive a separate layout review before multi-client 64 MiB testing.

64 MiB pass evidence from the working layout:

```text
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-64m-object128m-20260604-102826

registered vmshm window ... gpa=0x30000000 size=0x8000000
proxy_manager_vmshm: manager ready base=0x0000000030000000 size=0x8000000 alloc=[0x200000,0x7e00000]
BO_CREATE ... size=0x4000000 ... payload_gpa=0x0000000030200000
VM_BIND vmshm payload mapped ... size=0x4000000 ... first_gpa=0x0000000030200000
COMPUTE_CHECK=PASS
GPU_SMOKE_RESULT=PASS
RESULT: PASS
```

### Successful shared runs

All successful runs used `Mali-G610 (Panfrost)` with
`OpenGL ES 3.1 Mesa 25.0.7-2`.  Fetched logs were scanned for hidden panic,
Oops, GPU fault, job timeout, mismatch, timeout, smoke failure, ENOMEM, and
Mesa BO allocation failure markers.

| Workload | Shared run | Iterations | Result | Shared iter_total avg |
| --- | --- | ---: | --- | ---: |
| 4 MiB | `vmshm-1client-perf-4m-20260604-100018` | 100 | PASS | 21854.55 us |
| 16 MiB | `vmshm-1client-perf-16m-object128m-20260604-103401` | 100 | PASS | 30460.89 us |
| 64 MiB | `vmshm-1client-perf-64m-object128m-20260604-102826` | 20 | PASS | 65024.70 us |

The 16 MiB run was repeated with the final 128 MiB object layout so that the
16/64 MiB comparison does not mix different object-window configurations.

### Comparison with host and passthrough baseline

Baseline:

```text
GPU-SFTP/log/passthrough/perf/gpu-perf-logpath-passthrough-20260603-174020
```

| Workload | Host direct iter_total | Single-VM passthrough iter_total | Shared iter_total | Host/passthrough | Host/shared | Shared/passthrough |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 3140.41 us | 3986.15 us | 21854.55 us | 0.788 | 0.144 | 5.48x |
| 16 MiB | 12124.24 us | 15803.26 us | 30460.89 us | 0.767 | 0.398 | 1.93x |
| 64 MiB | 49302.00 us | 55482.55 us | 65024.70 us | 0.889 | 0.758 | 1.17x |

Derived overheads:

| Workload | Shared overhead vs passthrough | Shared overhead vs host |
| --- | ---: | ---: |
| 4 MiB | 448.26% | 595.91% |
| 16 MiB | 92.75% | 151.24% |
| 64 MiB | 17.20% | 31.89% |

The trend matches the expected amortization behavior.  The shared path still
has a large nearly fixed submit/synchronization component, so small buffers are
punished heavily.  As the buffer grows, CPU preparation, buffer upload, and
real GPU work dominate more of `iter_total`, and the fixed cross-VM overhead
becomes a smaller fraction of the iteration.

### Phase detail

| 4 MiB phase | Host | Passthrough | Shared | Shared / passthrough |
| --- | ---: | ---: | ---: | ---: |
| cpu_prepare | 1778.64 us | 1960.09 us | 1770.35 us | 0.90x |
| buffer_upload | 732.70 us | 888.56 us | 812.61 us | 0.91x |
| dispatch_call | 211.83 us | 266.19 us | 14275.60 us | 53.63x |
| memory_barrier | 40.64 us | 38.68 us | 3605.15 us | 93.20x |
| map_wait | 374.71 us | 830.12 us | 1388.12 us | 1.67x |
| unmap | 1.89 us | 2.51 us | 2.72 us | 1.08x |
| iter_total | 3140.41 us | 3986.15 us | 21854.55 us | 5.48x |

| 16 MiB phase | Host | Passthrough | Shared | Shared / passthrough |
| --- | ---: | ---: | ---: | ---: |
| cpu_prepare | 6902.58 us | 8009.35 us | 7292.96 us | 0.91x |
| buffer_upload | 2944.47 us | 4397.91 us | 3268.62 us | 0.74x |
| dispatch_call | 248.96 us | 234.58 us | 14343.07 us | 61.14x |
| memory_barrier | 40.30 us | 41.80 us | 3771.48 us | 90.23x |
| map_wait | 1985.71 us | 3116.68 us | 1780.90 us | 0.57x |
| unmap | 2.22 us | 2.94 us | 3.86 us | 1.31x |
| iter_total | 12124.24 us | 15803.26 us | 30460.89 us | 1.93x |

| 64 MiB phase | Host | Passthrough | Shared | Shared / passthrough |
| --- | ---: | ---: | ---: | ---: |
| cpu_prepare | 27313.95 us | 30938.20 us | 28468.65 us | 0.92x |
| buffer_upload | 12094.55 us | 12264.15 us | 12741.05 us | 1.04x |
| dispatch_call | 362.15 us | 1397.40 us | 14867.05 us | 10.64x |
| memory_barrier | 42.85 us | 39.85 us | 3622.80 us | 90.91x |
| map_wait | 9484.95 us | 10840.15 us | 5320.40 us | 0.49x |
| unmap | 3.55 us | 2.80 us | 4.75 us | 1.70x |
| iter_total | 49302.00 us | 55482.55 us | 65024.70 us | 1.17x |

Key interpretation:

- `dispatch_call` remains around 14-15 ms in the current shared path for all
  three sizes.  This is the dominant fixed cost from serialized client/proxy
  command submission and the proxy VM driving the real GPU through passthrough.
- `memory_barrier` remains around 3.6-3.8 ms, also mostly size-independent in
  this workload.
- `cpu_prepare` and `buffer_upload` scale with payload size and are already
  close to the host/passthrough values.  They are not the primary reason for
  the 4 MiB regression.
- At 64 MiB, the fixed shared overhead is amortized enough that the shared path
  is only `1.17x` slower than single-VM passthrough for this smoke workload.
- The current result is a functional performance snapshot, not an optimized
  transport baseline.  Optimizing the submit/wait RPC path, reducing serialized
  proxy round trips, and tightening proxy passthrough completion handling remain
  the likely next performance work items.

### Current conclusion

The 64 MiB failure was a configuration/layout problem in the object memslot,
not a fundamental compute-smoke correctness failure.  A 128 MiB object window
at `0x30000000` is sufficient for the present 64 MiB one-client smoke workload
without colliding with the low Firecracker device layout.

The expected performance trend is confirmed:

```text
host/shared improves from 0.144 at 4 MiB
                 to 0.398 at 16 MiB
                 to 0.758 at 64 MiB
```

The shared path is still much slower for small workloads because every GLES
iteration pays the same large cross-VM submit/barrier cost.  Larger buffers
make that cost a smaller part of total execution time, so the shared path moves
closer to passthrough as buffer size increases.

## 2026-06-04: Shared GLES Smoke Phase-Level Performance Analysis

This section mirrors the phase grouping used by the formal host-vs-passthrough
performance report and applies it to the one-client shared virtualization runs.

Source logs:

```text
Passthrough baseline:
GPU-SFTP/log/passthrough/perf/gpu-perf-logpath-passthrough-20260603-174020

Shared:
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-4m-20260604-100018
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-16m-object128m-20260604-103401
GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-64m-object128m-20260604-102826
```

Phase groups:

```text
metadata   = cpu_prepare + buffer_upload
submit     = dispatch_call
completion = memory_barrier + map_wait
map_unmap  = unmap
total      = iter_total
```

The ratios below use the same convention as the passthrough report:

```text
host/shared = Host direct phase time / Shared phase time
```

Closer to `1.000` means the shared path is closer to host direct performance
for that phase.  A very small ratio means that phase is much slower in shared
virtualization.

### Formal host/shared phase ratio table

| Workload | iter | total | metadata | submit | completion | map_unmap | Shared phase share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 100 | 0.144 | 0.972 | 0.015 | 0.083 | 0.695 | 11.8/65.3/22.8/0.01 |
| 16 MiB | 100 | 0.398 | 0.932 | 0.017 | 0.365 | 0.575 | 34.7/47.1/18.2/0.01 |
| 64 MiB | 20 | 0.758 | 0.956 | 0.024 | 1.065 | 0.747 | 63.4/22.9/13.8/0.01 |

The `Shared phase share` column is:

```text
metadata / submit / completion / map_unmap
```

This table shows the same amortization trend as the total-time comparison, but
with the cost center separated:

- `metadata` is already close to host: `0.972`, `0.932`, and `0.956`.
- `submit` is the dominant regression: `0.015`, `0.017`, and `0.024`.
- `completion` is poor for 4 MiB and 16 MiB, but no longer worse than host at
  64 MiB by this phase accounting.
- `map_unmap` is tiny in absolute time and does not meaningfully affect total
  performance.

The 64 MiB `completion=1.065` should not be read as the shared path having a
strictly better completion mechanism than host direct.  In this architecture,
the serialized cross-VM submit path can absorb work that would otherwise appear
later in `memory_barrier` or `map_wait`.  The phase boundary shifts part of the
wait into `dispatch_call`, so the lower completion time is best interpreted as
cost redistribution, not as a real completion fast path.

### Shared compared with single-VM passthrough

This table uses:

```text
passthrough/shared = Single-VM passthrough phase time / Shared phase time
```

Closer to `1.000` means shared is closer to the passthrough VM for that phase.
Values above `1.000` mean the measured shared phase is lower than passthrough
for that phase, usually because the work has moved into another phase.

| Workload | total | metadata | submit | completion | map_unmap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 0.182 | 1.103 | 0.019 | 0.174 | 0.923 |
| 16 MiB | 0.519 | 1.175 | 0.016 | 0.569 | 0.762 |
| 64 MiB | 0.853 | 1.048 | 0.094 | 1.217 | 0.589 |

Important points:

- Shared `metadata` is not the problem.  It is comparable to passthrough and is
  sometimes measured lower than passthrough.
- Shared `submit` is far behind passthrough for all sizes.  Even at 64 MiB,
  passthrough/shared submit is only `0.094`.
- Shared `completion` catches up by 64 MiB, but that is partly because the
  shared `submit` phase has already paid a large serialized cost before the
  workload reaches the explicit barrier/map-wait phase.

### Absolute grouped phase timings

| Workload | Path | metadata | submit | completion | map_unmap | total |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | Host | 2511.34 us | 211.83 us | 415.35 us | 1.89 us | 3140.41 us |
| 4 MiB | Passthrough | 2848.65 us | 266.19 us | 868.80 us | 2.51 us | 3986.15 us |
| 4 MiB | Shared | 2582.96 us | 14275.60 us | 4993.27 us | 2.72 us | 21854.55 us |
| 16 MiB | Host | 9847.05 us | 248.96 us | 2026.01 us | 2.22 us | 12124.24 us |
| 16 MiB | Passthrough | 12407.26 us | 234.58 us | 3158.48 us | 2.94 us | 15803.26 us |
| 16 MiB | Shared | 10561.58 us | 14343.07 us | 5552.38 us | 3.86 us | 30460.89 us |
| 64 MiB | Host | 39408.50 us | 362.15 us | 9527.80 us | 3.55 us | 49302.00 us |
| 64 MiB | Passthrough | 43202.35 us | 1397.40 us | 10880.00 us | 2.80 us | 55482.55 us |
| 64 MiB | Shared | 41209.70 us | 14867.05 us | 8943.20 us | 4.75 us | 65024.70 us |

The absolute timing table makes the fixed-cost nature of the current shared
path visible:

- Shared `submit` is `14275.60 us`, `14343.07 us`, and `14867.05 us`.
- Shared `completion` is `4993.27 us`, `5552.38 us`, and `8943.20 us`.
- Shared `metadata` grows with payload size and remains close to the host and
  passthrough values.

### Overhead decomposition versus host

| Workload | Net shared overhead | metadata delta | submit delta | completion delta | map_unmap delta | Dominant overhead |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 18714.14 us | +71.62 us (+0.4%) | +14063.77 us (+75.2%) | +4577.92 us (+24.5%) | +0.83 us (+0.00%) | submit |
| 16 MiB | 18336.65 us | +714.53 us (+3.9%) | +14094.11 us (+76.9%) | +3526.37 us (+19.2%) | +1.64 us (+0.01%) | submit |
| 64 MiB | 15722.70 us | +1801.20 us (+11.5%) | +14504.90 us (+92.3%) | -584.60 us (-3.7%) | +1.20 us (+0.01%) | submit |

The dominant overhead is unambiguous: `submit` contributes roughly
`14.1-14.5 ms` of additional time over host direct execution for every tested
size.  This is why the total overhead percentage shrinks as the buffer becomes
larger even though the raw submit overhead stays almost constant.

### Overhead decomposition versus passthrough

| Workload | Net shared overhead | metadata delta | submit delta | completion delta | map_unmap delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 17868.40 us | -265.69 us (-1.5%) | +14009.41 us (+78.4%) | +4124.47 us (+23.1%) | +0.21 us (+0.00%) |
| 16 MiB | 14657.63 us | -1845.68 us (-12.6%) | +14108.49 us (+96.3%) | +2393.90 us (+16.3%) | +0.92 us (+0.01%) |
| 64 MiB | 9542.15 us | -1992.65 us (-20.9%) | +13469.65 us (+141.2%) | -1936.80 us (-20.3%) | +1.95 us (+0.02%) |

Against passthrough, the same conclusion holds: the shared path's measured
metadata and completion groups are not consistently worse, but `submit` is
always much slower.  At 64 MiB, shared is only `9542.15 us` slower than
passthrough overall, while submit alone is `13469.65 us` slower.  The apparent
metadata/completion savings offset part of that submit cost in the grouped
accounting, which again suggests phase redistribution rather than a true
end-to-end advantage.

### Interpretation by phase

#### Metadata

`metadata` includes CPU-side data preparation and buffer upload.  It is already
near native behavior in the current smoke workload:

```text
host/shared metadata = 0.972, 0.932, 0.956
```

The shared client maps BO payloads through `vmshm-object`, so the hot data path
for this test is mostly ordinary memory writes into client-visible shared
payload pages.  That is exactly where the two-memslot design helps: control
metadata stays in `vmshm-comm`, while BO payloads live in `vmshm-object` and do
not require copying through the control RPC channel.

This phase is therefore not the first optimization target for the current
smoke workload.  It still needs future validation for non-contiguous payloads,
cache-maintenance policy, and multi-client pressure, but the current 4/16/64
MiB numbers do not point to payload upload as the dominant bottleneck.

#### Submit

`submit` is the main performance problem:

```text
Shared submit:
4 MiB  = 14275.60 us
16 MiB = 14343.07 us
64 MiB = 14867.05 us
```

The size independence is the important signal.  The workload grows by 16x from
4 MiB to 64 MiB, but submit remains around `14-15 ms`.  That points to fixed
cross-VM machinery rather than payload size:

- client DRM ioctl enters `panthor-client`
- client/proxy request is serialized through `client_comm_vmshm_call()`
- broker relays doorbell/eventfd state between VMs
- `panthor-proxy` reconstructs or validates the proxy-side ioctl
- proxy VM calls the real Panthor driver through the project's passthrough
  stack
- proxy passthrough execution has non-native interrupt and memory-management
  behavior
- any serialized wait or readiness check before returning to Mesa is charged to
  the userspace `dispatch_call` phase

This explains why 4 MiB is so poor: `submit` alone is 65.3% of the shared
iteration.  At 64 MiB it is still expensive, but it is only 22.9% of the shared
iteration because metadata and real GPU work have grown.

#### Completion

`completion` combines `memory_barrier` and `map_wait`.  For small workloads it
is another visible overhead:

```text
4 MiB shared completion  = 4993.27 us
16 MiB shared completion = 5552.38 us
```

The `memory_barrier` subphase alone stays around `3.6-3.8 ms`, which suggests
another mostly fixed synchronization cost in the current shared path.  The
`map_wait` part scales with where the actual GPU completion wait lands.  At
64 MiB, shared completion is lower than the host and passthrough grouped
completion values, but this should be treated as wait shifting: the shared
submit path has already spent much more time before the explicit barrier and
map-wait measurement begins.

The real optimization question is therefore not only "make completion faster",
but "move less serialized wait into submit and reduce the number of synchronous
cross-VM round trips across submit/barrier/readback".

#### Map/unmap

`map_unmap` is negligible:

```text
Shared map_unmap:
4 MiB  = 2.72 us
16 MiB = 3.86 us
64 MiB = 4.75 us
```

It is measurable but too small to matter for the current totals.  It should not
be a priority unless future workloads repeatedly map and unmap many small BOs
inside the hot loop.

### Optimization direction suggested by the phase data

The next performance work should focus on submit/wait transport rather than BO
payload upload:

- add lower-level timing around `client_comm_vmshm_call()` for `GROUP_SUBMIT`,
  `VM_BIND`, syncobj wait/signal, and barrier-related ioctls
- separate pure RPC latency from proxy real-ioctl latency
- measure broker wakeup/relay latency and eventfd delivery cost
- audit whether Mesa-visible `dispatch_call` is synchronously waiting for proxy
  or GPU progress that could be moved to a later explicit wait
- reduce serialized round trips in submit/barrier paths where the UAPI allows
  batching
- keep BO payloads in `vmshm-object`; avoid routing payload-sized data through
  `vmshm-comm`
- evaluate proxy passthrough completion and interrupt handling, because the
  proxy VM still depends on the project's non-native GPU passthrough path

The phase data supports the same high-level conclusion as the total-time data:
the current design is functionally correct for the one-client 4/16/64 MiB
smoke workload, and the two-memslot object/control split is doing the right
thing for payload data.  The remaining performance gap is dominated by fixed
cross-VM submit/synchronization overhead, not by buffer-size-proportional
payload handling.

## 2026-06-04: Passthrough and Shared BO Backing Separation

A code inspection confirms that the ordinary Panthor path and the shared
virtualization path are separated by BO backing type.  The shared work did not
replace the normal single-VM passthrough BO allocation path with the vmshm
object allocator.

### Ordinary DRM / single-VM passthrough path

The normal userspace ioctl path still creates GEM objects through the regular
Panthor shmem helper path:

```text
DRM_IOCTL_PANTHOR_BO_CREATE
  -> panthor_ioctl_bo_create()
  -> panthor_gem_create_with_handle()
  -> drm_gem_shmem_create()
```

The exported vmshm session helper `panthor_vmshm_bo_create()` also uses the
same regular helper:

```text
panthor_vmshm_bo_create()
  -> panthor_gem_create_with_handle()
  -> drm_gem_shmem_create()
```

This means a single passthrough VM using the normal Panthor DRM device can
continue to allocate BOs from the guest kernel's ordinary GEM shmem backing.
Its GPU page-table path then follows the passthrough design: shmem BO pages are
pinned, converted to an sg-table, and mapped through the custom GPA-to-HPA
passthrough page-table machinery.

### Shared virtualization payload path

The shared client/proxy path takes a different branch.  A client BO_CREATE RPC
is handled by the proxy module, which first allocates a `proxy_vmshm` object
from the `vmshm-object` window:

```text
client BO_CREATE RPC
  -> panthor_proxy_session_bo_create()
  -> proxy_vmshm_alloc_ext(PROXY_VMSHM_OBJ_GPU_BO)
  -> panthor_vmshm_bo_create_from_payload()
  -> panthor_gem_create_vmshm_with_handle()
```

`panthor_gem_create_vmshm_with_handle()` still creates a GEM shmem object as
the DRM object shell, but it pins and stores the shared payload in
`bo->vmshm_payload`.  The comment on `vmshm_payload` is the intended contract:
when this field is set, VM_BIND maps the shared payload directly instead of
using the shmem GEM page list.

### VM_BIND runtime split

The actual mapping decision is runtime-gated by
`panthor_gem_is_vmshm_backed(bo)`:

```text
if BO is vmshm-backed:
  proxy_vmshm_obj_translate()
  panthor_vm_map_vmshm_spans()

else:
  drm_gem_shmem_pin()
  drm_gem_shmem_get_pages_sgt()
  panthor_vm_map_pages()
```

So the split is not only conceptual; it is enforced at the VM_BIND hot path.
Only BOs that have `bo->vmshm_payload` set take the `vmshm-object` span mapping
path.  Ordinary BOs, including the single-VM passthrough workload's BOs, remain
on the kernel shmem allocation and sg-table mapping path.

### Client-side shared mapping

On the client VM side, the client frontend receives the proxy's payload handle,
looks it up through `client_vmshm_manager_get()`, and maps the payload GPA with
`remap_pfn_range()`.  This is separate from the real Panthor driver's ordinary
GEM mmap path and exists only in the panthor-client frontend.

### Conclusion

Current code separates the two memory designs:

```text
single-VM passthrough / ordinary Panthor:
  drm_gem_shmem_create()
  drm_gem_shmem_pin()
  drm_gem_shmem_get_pages_sgt()
  normal passthrough GPA-to-HPA GPU page-table handling

shared client/proxy virtualization:
  proxy_vmshm_alloc_ext() for BO payload
  GEM shmem object only as DRM object shell
  bo->vmshm_payload marks the object
  VM_BIND maps vmshm-object spans instead of shmem page list
```

This distinction is important for performance interpretation.  Shared
metadata being close to host does not mean the passthrough path was converted
to vmshm memory.  It means the shared path's client-visible BO payloads are
using a separate `vmshm-object` data plane, while the ordinary passthrough path
continues to use the kernel's regular GEM shmem allocation and passthrough
GPA-to-HPA mapping flow.

## 2026-06-04: GLES Perf Metric Revision - Exclude CPU Input Fill

The earlier 4/16/64 MiB shared performance tables used the same smoke output
that passthrough used at the time:

```text
metadata   = cpu_prepare + buffer_upload
submit     = dispatch_call
completion = memory_barrier + map_wait
map_unmap  = unmap
total      = iter_total including cpu_prepare
```

That grouping was useful as a first end-to-end view, but it is not the cleanest
metric for comparing GPU virtualization overhead.  `cpu_prepare` is just the
userspace loop that fills the input array before `glBufferData()`.  It measures
ordinary CPU memory-store behavior in the current process and rootfs, not an
ioctl virtualization boundary, a BO mapping decision, vmshm payload handling,
or GPU completion behavior.

This matters because the old grouped `metadata` number made shared look very
close to host and sometimes better than passthrough.  That does not imply that
shared has a magically faster Panthor BO metadata path.  A large part of the
old group was CPU input fill, and that phase can move independently of the
actual GPU/DRM/VM path.  Shared and passthrough also differ structurally:

- Passthrough still allocates ordinary Panthor GEM shmem BOs and maps them
  through the passthrough GPA-to-HPA page-table path.
- Shared client-visible BO payloads use the `vmshm-object` memslot and the
  proxy-owned object allocator, while transient ioctl metadata stays in
  `vmshm-comm`.
- The proxy VM itself reaches the physical GPU through the project's custom
  passthrough path, so submit/completion includes both cross-VM RPC cost and
  non-native proxy passthrough behavior.

The smoke test now has an explicit mode:

```text
--exclude-cpu-prepare
```

When enabled:

```text
PERF_CPU_PREPARE_EXCLUDED=1
PERF_ITER_US / iter_total = iter_end - cpu_prepare_done
```

`cpu_prepare` is still printed as `PERF_PHASE_US name=cpu_prepare`, so we can
check whether input fill is unusual, but it is excluded from the formal
`total` and from the formal `metadata` group.

The revised formal grouping is:

```text
metadata   = buffer_upload
submit     = dispatch_call
completion = memory_barrier + map_wait
map_unmap  = unmap
total      = buffer_upload + dispatch_call + memory_barrier + map_wait + unmap
```

Related runner/script changes:

- `GPU-SFTP/tests/gpu-compute-smoke/gles_compute_smoke.c`
  - accepts `--exclude-cpu-prepare`
  - emits `PERF_CPU_PREPARE_EXCLUDED=0/1`
  - keeps measuring `cpu_prepare` as a separate phase
  - changes only the formal iter total when the flag is enabled
- `scripts/run/run-host-vs-passthrough-gles-perf.sh`
  - accepts `--exclude-cpu-prepare`
  - injects the flag into VM rootfs `GPU_SMOKE_ARGS`
  - passes the flag to host direct runs
  - treats `metadata=buffer_upload` under the new mode
  - requires `PERF_CPU_PREPARE_EXCLUDED=1` in VM and host logs before PASS
- `scripts/run/run-vmshm-e2e.sh`
  - for `--gles-compute-smoke`, compiles the current smoke source on the remote
    host and injects that binary into the base Panfrost client rootfs
  - installs current `gpu-smoke.sh` and `init` into the base rootfs before VM
    launch
  - leaves `GPU_SMOKE_AFTER_RUN=shell` so the external runner can stop the VM
    after seeing PASS markers, avoiding a false guest `init` exit panic marker
  - requires `PERF_CPU_PREPARE_EXCLUDED=1` if the requested GLES args include
    `--exclude-cpu-prepare`
- `docs/passthrough/GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md` and both skill
  copies now document the revised formal metric.

This revised metric is the one to use for the next host/passthrough/shared
comparison.  Old tables in this worklog remain useful historical evidence for
functional correctness and coarse trends, but they should not be used as the
final performance comparison when discussing BO or vmshm data-plane overhead.

## 2026-06-04: CPU-Fill-Excluded Host/Passthrough/Shared Results

The revised smoke metric was tested on the same 4/16/64 MiB GLES compute
workloads.  The formal `total` below excludes per-iteration CPU input fill.
`cpu_prepare` is still reported for sanity, but does not contribute to
`PERF_ITER_US` / `iter_total`.

### Runs

Passthrough host-vs-VM sweep:

```text
run id: gpu-perf-exclude-cpu-prepare-20260604-153928
local logs: GPU-SFTP/log/passthrough/perf/gpu-perf-exclude-cpu-prepare-20260604-153928
command:
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh
    --host-rootfs-userspace
    --exclude-cpu-prepare
    --iterations 100
    --warmup 5
    --large-count-iterations 20
    --large-count-warmup 5
    --vm-timeout 900
    --host-timeout 900
result: PASS
```

Shared one-client runs:

```text
4 MiB:
  run id: vmshm-1client-perf-4m-exclude-cpu-prepare-rerun-20260604-155550
  local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-4m-exclude-cpu-prepare-rerun-20260604-155550
  result: PASS

16 MiB:
  run id: vmshm-1client-perf-16m-exclude-cpu-prepare-20260604-160553
  local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-16m-exclude-cpu-prepare-20260604-160553
  result: PASS

64 MiB:
  run id: vmshm-1client-perf-64m-exclude-cpu-prepare-20260604-161512
  local logs: GPU-SFTP/log/shared/vmshm-1client/vmshm-1client-perf-64m-exclude-cpu-prepare-20260604-161512
  result: PASS
```

The first 4 MiB attempt after adding `GPU_SMOKE_AFTER_RUN=poweroff` is not used
as a formal result.  The compute workload itself passed and emitted
`PERF_CPU_PREPARE_EXCLUDED=1`, but the shared client rootfs then produced a
guest `init` exit panic marker during poweroff.  The runner was corrected to
leave `GPU_SMOKE_AFTER_RUN=shell` and let the outer test harness stop the VM.

All accepted logs contain:

```text
PERF_CPU_PREPARE_EXCLUDED=1
COMPUTE_CHECK=PASS
GPU_SMOKE_RESULT=PASS
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
```

No accepted shared result contains the earlier false `Kernel panic` marker.

### Total Time Ratios

Metric:

```text
host/path = Host elapsed time / path elapsed time
```

Higher is better; `1.000` means equal to host.  `Passthrough/shared` is included
to show how close shared is to the already virtualized single-VM passthrough
path.

| Workload | Host us | Passthrough us | Shared us | Host/passthrough | Host/shared | Passthrough/shared |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 1349.27 | 1819.29 | 6285.86 | 0.742 | 0.215 | 0.289 |
| 16 MiB | 5304.48 | 7789.52 | 10272.35 | 0.681 | 0.516 | 0.758 |
| 64 MiB | 22743.35 | 25156.05 | 27337.20 | 0.904 | 0.832 | 0.920 |

The size trend now matches the expected amortization model much more cleanly:

```text
host/shared:
  4 MiB  = 0.215
  16 MiB = 0.516
  64 MiB = 0.832

passthrough/shared:
  4 MiB  = 0.289
  16 MiB = 0.758
  64 MiB = 0.920
```

At 64 MiB, shared is only about `8.0%` slower than passthrough by this smoke
metric:

```text
1 - passthrough/shared = 1 - 0.920 = 0.080
```

This does not mean shared has no fixed overhead.  It means the fixed overhead
is largely amortized once buffer upload and GPU work dominate the iteration.

### Phase Ratios

Revised phase grouping:

```text
metadata   = buffer_upload
submit     = dispatch_call
completion = memory_barrier + map_wait
map_unmap  = unmap
```

Host/shared ratios:

| Workload | total | metadata | submit | completion | map_unmap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 0.215 | 0.925 | 0.049 | 0.310 | 0.631 |
| 16 MiB | 0.516 | 0.900 | 0.057 | 0.752 | 0.514 |
| 64 MiB | 0.832 | 0.923 | 0.080 | 1.048 | 1.061 |

Absolute phase averages:

| Workload | Path | total | metadata | submit | completion | map_unmap | cpu_prepare reported |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 MiB | Host | 1349.27 | 723.87 | 204.71 | 418.83 | 1.86 | 1787.33 |
| 4 MiB | Passthrough | 1819.29 | 752.42 | 208.80 | 854.68 | 3.39 | 2185.72 |
| 4 MiB | Shared | 6285.86 | 782.68 | 4151.06 | 1349.17 | 2.95 | 1809.81 |
| 16 MiB | Host | 5304.48 | 2945.39 | 238.17 | 2118.91 | 2.01 | 6903.44 |
| 16 MiB | Passthrough | 7789.52 | 4569.04 | 308.34 | 2908.06 | 4.08 | 8297.27 |
| 16 MiB | Shared | 10272.35 | 3271.22 | 4180.75 | 2816.47 | 3.91 | 7285.56 |
| 64 MiB | Host | 22743.35 | 11842.75 | 357.80 | 10536.75 | 6.05 | 27347.50 |
| 64 MiB | Passthrough | 25156.05 | 14326.55 | 533.30 | 10292.35 | 3.85 | 34283.00 |
| 64 MiB | Shared | 27337.20 | 12830.80 | 4445.20 | 10055.50 | 5.70 | 29082.40 |

### Interpretation

The revised data changes the earlier interpretation in a useful way:

- `metadata=buffer_upload` is close to host for shared across all sizes:
  `0.925`, `0.900`, and `0.923`.  This supports the two-memslot design: large
  client-visible BO payloads belong in `vmshm-object`, while transient ioctl
  metadata remains in `vmshm-comm`.
- The main shared penalty is still `submit`, but the new quiet-console,
  CPU-fill-excluded run measures it around `4.1-4.4 ms`, not the old
  `14-15 ms` seen in the earlier console-noisy/shared grouping.  It is still a
  fixed per-iteration cost and remains the dominant 4 MiB problem.
- `completion` is worse than host at 4 MiB, improves at 16 MiB, and is roughly
  host-level at 64 MiB.  The 64 MiB `completion > 1.0` ratio should be treated
  as measurement/scheduling variance, not proof that shared completion is
  intrinsically faster than host.
- `cpu_prepare` remains visible for sanity.  It scales with buffer size and is
  ordinary CPU memory-store work, so it is intentionally excluded from the
  formal ratio.
- The proxy VM still uses the project's custom passthrough technology to reach
  the real GPU.  Shared results therefore combine cross-VM client/proxy RPC
  overhead with the proxy VM's non-native interrupt and memory-management
  behavior.  They should not be interpreted as a pure vmshm transport number.

The most important conclusion is that the apparent old `metadata` advantage was
not reliable because it included CPU input fill.  With the revised metric,
shared BO payload handling still looks healthy, but the credible remaining
target is fixed submit/RPC/synchronization overhead.

### Runner Notes

Two runner reliability details were found while collecting these logs:

- Older shared perf harness revisions spent most of their wall-clock setup time
  preparing a separate GLES rootfs for each run.  This is outside
  `PERF_ITER_US`, but it slows experiment iteration.  The later 2026-06-05
  runner update replaces that with base-image loop-mount payload injection.
- The shared GLES client intentionally leaves `GPU_SMOKE_AFTER_RUN=shell` to
  avoid false init-exit panic markers.  Some runs still required manual remote
  cleanup and log fetch after `RESULT: PASS` had already been written.  The
  script now redirects background process stdin from `/dev/null` and uses
  stronger pid cleanup, but the harness should still be watched for SSH-session
  teardown hangs during long perf sweeps.

## 2026-06-05: Rootfs Injection Policy Locked In

### User Direction

The shared-GPU test harness should not keep making separate rootfs images for
each test program, smoke mode, or GLES workload size.  Updating a shell script
or smoke binary should be cheap enough for 32 MiB and 64 MiB scheduling
iteration, so the harness now uses base images plus loop-mount payload
injection before VM launch.

### Current Rootfs Layout

Only the base images belong in the shared runtime rootfs directory:

```text
firecracker-bins/rootfs/rootfs.ext2
firecracker-bins/rootfs/rootfs-panfrost.ext4
firecracker-bins/rootfs/mounts/
firecracker-bins/rootfs/work/
```

`rootfs.ext2` is the lightweight comm/query base image.  One-client Panthor
IOCTL semantic smokes use this same base image: the runner mounts it read-write,
installs `/panthor_ioctl_smoke` and `/panthor_ioctl_smoke_init`, unmounts it,
and then boots the client from that image.

`rootfs-panfrost.ext4` is the GLES/Panfrost userspace base image.  One-client
and two-client GLES smokes use this same base image: the runner builds the
current `gles-compute-smoke` on the remote host, mounts the image read-write,
installs `/root/gles-compute-smoke`, `/root/gpu-smoke.sh`,
`/root/gpu-smoke.env`, and `/init`, unmounts it, and then boots the GLES
client VM or VMs from that image.

The rootfs directory is pruned with a base-image allowlist before injection:
only `rootfs.ext2`, `rootfs-panfrost.ext4`, `.gitkeep`, `mounts/`, and `work/`
should remain.  Test selection now lives in per-run Firecracker config and boot
arguments, not in rootfs identity.

### Runtime Argument Transport

IOCTL semantic mode is passed through the client command line:

```text
panthor_ioctl_smoke_mode=<mode>
```

The generated `/panthor_ioctl_smoke_init` reads `/proc/cmdline`, maps the mode
to the corresponding `panthor_ioctl_smoke` option, and runs the injected smoke
binary.

GLES workload and timing arguments are also passed through the generated client
command line:

```text
gpu_smoke_args_tokens=--count:<N>:--iterations:<N>:--warmup:<N>:--perf:--exclude-cpu-prepare
gpu_smoke_quiet_console=1
gpu_smoke_after_run=shell
```

`GPU-SFTP/tests/gpu-compute-smoke/init` and
`GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh` decode that token list back
into `GPU_SMOKE_ARGS`.  The token format deliberately supports only the smoke
arguments this harness needs: whitespace-free tokens without colons, quotes, or
backslashes.  Unsupported tokens fail before VM launch.

### Runner Evidence

Rootfs preparation is now evidenced by injection markers rather than rootfs
selection markers:

```text
rootfs_payload_inject_start payload=panthor-ioctl-smoke ...
rootfs_payload_inject_done  payload=panthor-ioctl-smoke ...
rootfs_payload_inject_start payload=gles-compute ...
rootfs_payload_inject_done  payload=gles-compute ...
```

The one-client runner writes the IOCTL markers to `ioctl-smoke-rootfs.log` and
the GLES markers to `gles-compute-rootfs.log`.  The two-client runner writes
GLES markers to `gles-compute-rootfs.log`.  A valid shared GLES run should still
also prove the actual GPU path with:

```text
GL_RENDERER=Mali-G610 (Panfrost)
PERF_CPU_PREPARE_EXCLUDED=1
COMPUTE_CHECK=PASS
GPU_SMOKE_RESULT=PASS
```

### Two-Memslot Boundary

The rootfs injection policy is only a test-harness change.  It does not alter
the shared GPU virtualization memory design:

```text
vmshm-object -> BO payloads and other proxy/client-visible shared objects
vmshm-comm   -> ioctl metadata, flattened arrays, handles, transient RPC/control data
```

For GLES, `--count` still controls the `vmshm-object` window size because it
represents BO payload demand:

```text
--count 1048576   ->  64 MiB object window
--count 4194304   ->  96 MiB object window
--count 8388608   -> 128 MiB object window
--count 16777216  -> 224 MiB object window
unknown/custom    -> 224 MiB conservative fallback
```

The per-run broker `window_size`, client/proxy Firecracker `expected_size`, and
host-memory preflight guard continue to use that object-window value.  The
32 MiB workload remains a useful fallback when the remote host cannot safely
hold a 64 MiB two-client launch envelope, but it uses the same injected
Panfrost base image as the other GLES workloads.

### Launch And Memory Guard Rules

The two-client GLES runner keeps the memory guard because previous 64 MiB runs
proved that host memory pressure can kill Firecracker processes and leave SSH
unresponsive.  The default automatic guard is:

```text
proxy_mem + 2 * client_mem + object window + 64 MiB comm windows + 512 MiB guard
```

`--gles-client-start-gap-sec 0` now means near-parallel launch: client1 starts
immediately after client0.  Positive values deliberately stagger the workload by
waiting for client0's DRM frontend and then sleeping before launching client1.
Positive-gap runs are useful diagnostics, but they should not be counted as
near-parallel multi-client scheduling results.

### Files Updated

```text
scripts/run/run-vmshm-e2e.sh
scripts/run/run-vmshm-2client-e2e.sh
GPU-SFTP/tests/gpu-compute-smoke/init
GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh
docs/shared/GPU_SFTP_ARTIFACT_LAYOUT.md
docs/skills/gpu-shared-virtualization-autotest/SKILL.md
/home/mzh/.codex/skills/gpu-shared-virtualization-autotest/SKILL.md
docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md
```

### Validation

Local checks for the injection-oriented harness:

```text
bash -n scripts/run/run-vmshm-e2e.sh
bash -n scripts/run/run-vmshm-2client-e2e.sh
sh -n GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh
sh -n GPU-SFTP/tests/gpu-compute-smoke/init
```

The repo skill copy and the active local skill copy should remain identical.
Remote rootfs cleanup should leave only the two base images and the two helper
directories under `/root/GPU-SFTP/firecracker-bins/rootfs/`.

## 2026-06-05: Client BO WB mmap Experiment

### Reason

The same-workload 32 MiB two-client evidence showed that shared performance was
not dominated by GPU completion alone.  `buffer_upload` remained much higher
than host and passthrough in the two-client shared run, while the shared BO
payload mapping differed from the normal Panthor paths:

```text
client_vmshm_manager probe: memremap(..., MEMREMAP_WB)
proxy_vmshm_manager probe:  memremap(..., MEMREMAP_WB)
panthor-client mmap:        pgprot_writecombine(vma->vm_page_prot)
normal Panthor GEM mmap:    drm_gem_shmem_object_mmap(), map_wc = !ptdev->coherent
```

So the shared `vmshm-object` payload is WB from the client/proxy kernel view,
but the client userspace BO mmap path defaults to WC.  The GLES smoke repeatedly
writes a large SSBO from userspace during `buffer_upload`, so this policy is a
plausible contributor to the upload gap.

### Design

Added a controlled experimental module parameter in `panthor-client`:

```text
panthor_client.bo_mmap_cached=1
```

Default remains unchanged:

```text
bo_mmap_cached=0 -> client BO mmap uses WC
bo_mmap_cached=1 -> client BO mmap uses default WB page attributes
```

The MMAP log includes the selected attribute:

```text
panthor-client: MMAP ... attr=WC
panthor-client: MMAP ... attr=WB
```

This is intentionally not a default behavior change.  The shared path uses
Firecracker/vmshm memfd-backed memory and the proxy VM reaches the real GPU
through the custom passthrough path, so coherency behavior must be proven by
correctness tests before treating WB mmap as a stable design.

The runner exposes the experiment without hand-editing JSON:

```text
./scripts/run/run-vmshm-e2e.sh --gles-client-bo-mmap-cached ...
./scripts/run/run-vmshm-2client-e2e.sh --gles-client-bo-mmap-cached ...
```

For two-client GLES, both client VMs receive the same boot argument.  The proxy
VM is unchanged, and the two-memslot boundary is unchanged.

## 2026-06-05: Two-Client 64 MiB Host CPU Affinity Reaches Target

### Goal

The previous valid near-parallel 64 MiB two-client runs were functionally
correct, but they stayed around `host/shared=0.50-0.56`.  Logs showed the remote
host normally exposes only two online A55 CPUs (`0-1`), while the near-parallel
shared run launches:

```text
proxy VM:   2 vCPUs
client0 VM: 1 vCPU
client1 VM: 1 vCPU
broker:     host process
```

That means the test was oversubscribing two online host CPUs with two
simultaneous 64 MiB client uploads plus the proxy passthrough VM.  Merely
onlining CPUs `2-3` without process placement had already been tested and was
not enough.  This round tested an explicit host scheduling policy:

```text
online host CPUs: 0-3
broker:           taskset -c 0-1
proxy Firecracker:taskset -c 0-1
client0:          taskset -c 2
client1:          taskset -c 3
```

This keeps the proxy/broker side on CPUs `0-1` while giving each client upload
path its own host CPU.  It does not change the GPU virtualization ABI, BO
backing, sync semantics, or the two memslot split:

```text
vmshm-object -> BO payloads and proxy/client-visible shared objects
vmshm-comm   -> ioctl metadata, flattened arrays, handles, RPC/control data
```

### Runner Changes

Added diagnostic scheduling controls to `scripts/run/run-vmshm-2client-e2e.sh`:

```text
--gles-host-online-cpus LIST
--gles-broker-cpus LIST
--gles-proxy-cpus LIST
--gles-client0-cpus LIST
--gles-client1-cpus LIST
```

The runner records the chosen policy in `preflight.txt`, `affinity.log`, and
the `== Host CPU affinity ==` section of `result`.  CPUs that were offline
before the run and were onlined by `--gles-host-online-cpus` are restored at
runner exit.  This was verified after the run:

```text
before optional host cpu online: online_cpus=0-1
after optional host cpu online:  online_cpus=0-3
after restore:                  online_cpus=0-1
```

The runner help and shared autotest skill now mark these as diagnostic
scheduling controls.  They are not default behavior for semantic correctness
tests.

### Shared 64 MiB Affinity Run

Run:

```text
run id:
  vmshm-2client-gles-64m-nostats-wc-affinity-20260605-1154
command:
./scripts/run/run-vmshm-2client-e2e.sh
  --skip-sync
  --gles-compute-smoke
  --gles-client-mem-mib 248
  --gles-proxy-mem-mib 248
  --gles-client-vcpus 1
  --gles-proxy-vcpus 2
  --gles-client-start-gap-sec 0
  --gles-host-online-cpus 0-3
  --gles-broker-cpus 0-1
  --gles-proxy-cpus 0-1
  --gles-client0-cpus 2
  --gles-client1-cpus 3
  --gles-smoke-args "--count 16777216 --iterations 20 --warmup 5 --perf --exclude-cpu-prepare"
  --run-id vmshm-2client-gles-64m-nostats-wc-affinity-20260605-1154
```

Local logs:

```text
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-64m-nostats-wc-affinity-20260605-1154
```

Correctness evidence:

```text
client0: GL_RENDERER=Mali-G610 (Panfrost)
client0: PERF_CPU_PREPARE_EXCLUDED=1
client0: COMPUTE_CHECK=PASS
client0: GPU_SMOKE_RESULT=PASS

client1: GL_RENDERER=Mali-G610 (Panfrost)
client1: PERF_CPU_PREPARE_EXCLUDED=1
client1: COMPUTE_CHECK=PASS
client1: GPU_SMOKE_RESULT=PASS

result: RESULT: GLES_PASS
```

Rootfs and memory evidence:

```text
rootfs_payload_inject_done payload=gles-compute rootfs=/root/GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4
gles_object_window_mib=224
gles_object_window_bytes=234881024
gles_mem_available_mib=2263
```

Shared performance:

```text
client0 iter_total avg = 24291.50 us
client1 iter_total avg = 24306.95 us
shared avg             = 24299.23 us

phase averages:
  buffer_upload  = 13772.95 us
  dispatch_call  =  1642.33 us
  memory_barrier =    86.18 us
  map_wait       =  8793.63 us
  unmap          =     4.15 us
  cpu_prepare    = 28372.45 us  # excluded
```

The proxy log confirms a real near-parallel run: both sessions open within the
same time window and `GROUP_SUBMIT` lines from session 1 and session 2 overlap
between roughly `3.15s` and `4.06s`.

### Fair Host Baseline Under Same CPU Online Condition

A new host-direct 64 MiB diagnostic baseline was collected with the same host
CPU online condition (`0-3`) and the same formal smoke metric
(`--exclude-cpu-prepare`):

```text
run id:
  gpu-perf-host-direct-64m-cpu4-for-shared-affinity-20260605-1200
local logs:
  GPU-SFTP/log/passthrough/perf/gpu-perf-host-direct-64m-cpu4-for-shared-affinity-20260605-1200
mode:
  host direct only, VM skipped
  host userspace from rootfs
  count=16777216
  iterations=20
  warmup=5
  PERF_CPU_PREPARE_EXCLUDED=1
```

Host direct evidence:

```text
GL_RENDERER=Mali-G610 (Panfrost)
COMPUTE_CHECK=PASS
PERF_CPU_PREPARE_EXCLUDED=1
PERF_ITER_US avg=21354.50 us
```

Host phases:

```text
buffer_upload  = 11657.55 us
dispatch_call  =   347.90 us
memory_barrier =    40.90 us
map_wait       =  9303.50 us
unmap          =     4.65 us
cpu_prepare    = 27365.65 us  # excluded
```

### Result

Using the same CPU-online host baseline:

```text
host/shared = 21354.50 / 24299.23 = 0.879
```

Using the previous formal 64 MiB host baseline (`22743.35 us`) gives:

```text
host/shared = 22743.35 / 24299.23 = 0.936
```

The stricter same-topology value is the one to use for this scheduling
diagnostic, and it still exceeds the target `host/shared > 0.8`.

Compared with the previous no-stats 64 MiB shared baseline:

```text
no affinity shared avg = 40343.03 us
affinity shared avg    = 24299.23 us
improvement            = 39.8%

buffer_upload: 27178.78 -> 13772.95 us
dispatch_call:  4501.20 ->  1642.33 us
map_wait:        8563.22 ->  8793.63 us
```

This strongly indicates that the previous 64 MiB two-client bottleneck was not
only GPU/proxy RPC work.  A large part was host scheduling of the two
concurrent client upload paths and proxy passthrough vCPUs on a two-online-CPU
host envelope.

### Interpretation

This is a valid achieved-performance design for the current constrained remote
host:

```text
1. Keep the proxy VM at 2 vCPUs so proxy-side passthrough submit/completion can
   progress while serving both clients.
2. Temporarily online enough host CPUs for near-parallel client upload and
   proxy execution.
3. Pin proxy/broker separately from each client Firecracker process.
4. Restore host CPU online state after the diagnostic run.
```

The scheduling policy is deliberately explicit instead of hidden in the
default semantic runner.  Correctness tests can continue to run without CPU
affinity knobs, while performance runs that claim near-parallel `host/shared`
must record CPU online state and process affinity.

### Remaining Risks And Next Design Work

This result satisfies the current two-client smoke performance target, but it
does not remove all shared overhead.  Against the same-topology host baseline:

```text
buffer_upload overhead = 13772.95 - 11657.55 = 2115.40 us
dispatch_call overhead =  1642.33 -   347.90 = 1294.43 us
completion difference  = (86.18 + 8793.63) - (40.90 + 9303.50)
                       = -464.59 us
```

The remaining optimization directions are:

```text
1. Reduce or batch vmshm-comm GROUP_SUBMIT metadata handling.
   dispatch_call is still about 4.7x host even after CPU affinity.

2. Keep investigating client BO upload policy, but do not promote WB mmap by
   default yet.  The cached mmap experiment was correctness-valid but did not
   materially improve 32 MiB no-stats performance.

3. Treat process affinity as part of the multi-client scheduler design on this
   host.  Future larger-client tests should allocate host CPUs deliberately
   instead of letting Firecracker processes migrate across a tiny online set.

4. Do not collapse `vmshm-object` and `vmshm-comm`.  The performance win came
   from host scheduling, not from changing memslot semantics.
```

### Validation

Local checks after the runner update:

```text
bash -n scripts/run/run-vmshm-2client-e2e.sh
git diff --check -- scripts/run/run-vmshm-2client-e2e.sh
```

Remote cleanup check after both shared and host-direct runs:

```text
online=0-1
/dev/pmthor present
/dev/dri/card0 present
```

## 2026-06-05: Proxy VM Multi-Client Scheduling Policy

This pass extends the two-client shared-GPU work from host CPU affinity into
the proxy VM and Panthor-driver scheduling layers.  The goal is not only to
make one two-client smoke pass, but to define a repeatable scheduling policy
for the proxy VM when multiple client VMs concurrently submit GPU work through
the same physical Panthor device.

The tested topology remains:

```text
client0 VM /dev/panthor
client1 VM /dev/panthor
  -> panthor-client DRM frontend
  -> client_vmshm_comm
  -> vmshm-broker eventfd relay
  -> proxy_comm_vmshm channels in proxy VM
  -> panthor-proxy RPC handlers
  -> real Panthor driver in proxy VM
  -> custom passthrough GPU path
```

This matters because the proxy VM is not a normal native Linux GPU host.  Its
real GPU access still goes through the custom passthrough path, so memory
management, interrupt delivery, Firecracker vCPU scheduling, and Panthor
completion work all interact.  A useful shared-GPU scheduler therefore has to
cover four layers at once:

```text
1. host scheduler placement for Firecracker and broker processes;
2. proxy_comm_vmshm fast transport into the proxy VM;
3. panthor-proxy submit-before-real-DRM scheduling and RPC latency;
4. proxy-VM Panthor CSF scheduler/completion work.
```

The two vmshm memslots are still kept separate:

```text
vmshm-object: BO payloads and GPU-visible shared objects that clients need to
              expose to the proxy/physical GPU path.
vmshm-comm:   ioctl metadata, queue descriptors, flattened arrays, handles,
              and request/response control messages.
```

The scheduling changes below do not merge these regions.  The current design
lets the proxy accept control requests normally through `vmshm-comm`, then
schedules GPU work inside `panthor-proxy` immediately before a translated
`GROUP_SUBMIT` enters the real Panthor driver.

### Current Code Scheduling Model

The current multi-client scheduling model should be understood as an
approximation of two independent Panthor users in the proxy VM:

```text
client0 VM -> vmshm RPC -> panthor-proxy session 1 -> real Panthor file/session
client1 VM -> vmshm RPC -> panthor-proxy session 2 -> real Panthor file/session
```

From the real Panthor driver's scheduling layer, two client VMs submitting GPU
work look much like two separate proxy-VM Panthor file/session owners creating
VMs, BOs, groups, and queue submits.  `panthor-proxy` creates one
`panthor_proxy_session` per client `OPEN_SESSION`, and each proxy session owns
its own `real_session`, `session->lock`, and per-session xarrays for VMs, BOs,
syncobjs, groups, and heaps.  A request from one client is translated only
inside that session namespace before being passed to the real Panthor helper
such as `panthor_vmshm_group_submit()`.

The approximation is intentionally limited:

```text
ordinary proxy-VM process:
  userspace ioctl -> real Panthor ioctl path -> Panthor scheduler

shared client VM:
  client ioctl -> vmshm-comm RPC -> proxy worker -> panthor-proxy handler
  -> real Panthor vmshm helper -> Panthor scheduler
```

So the GPU scheduling object is similar, but the submission path is not.  The
shared path adds client RPC latency, proxy comm IRQ/workqueue scheduling,
metadata validation, handle translation, and response delivery back through the
same client comm channel.

BO allocation is also deliberately different from a normal proxy-VM process.
Client-visible BO payloads are allocated from `vmshm-object` by the proxy
allocator and then turned into real Panthor BOs with
`panthor_vmshm_bo_create_from_payload()`.  Transient ioctl metadata, submit
arrays, VM_BIND arrays, sync handles, and request/response structs remain in
`vmshm-comm`.  This is why the two-client design can look like two proxy-VM
processes at the Panthor scheduler layer while still having a different data
plane and memory-allocation path.

The current proxy does not implement a full multi-tenant GPU scheduler with
quotas, weighted fair queueing, deadlines, or per-client inflight limits.
Fairness today comes from three layers working together:

```text
1. proxy_comm_vmshm transport:
   each client has its own comm window, IRQ/doorbell, and proxy channel.
   This layer is intentionally kept as a transport/receive path.  It should
   accept and deliver requests into the proxy VM quickly instead of deciding GPU
   fairness at the channel-drain level.

2. panthor-proxy session isolation and submit scheduler:
   each client session has independent handle namespaces and an independent
   session lock.  Requests from the same client session are serialized where
   they mutate or translate that session state; requests from different
   sessions are not intentionally serialized by panthor-proxy.  GROUP_SUBMIT is
   the first ioctl routed through an internal panthor-proxy scheduler queue:
   requests are accepted from proxy comm, queued per session, and selected by a
   proxy-side policy before calling `panthor_vmshm_group_submit()`.

3. real Panthor scheduler in the proxy VM:
   after translation, GROUP_SUBMIT creates normal Panthor scheduler jobs.
   The real Panthor driver, drm_gpu_scheduler, CSF firmware, group priority,
   CSG slot availability, and timeslice/round-robin behavior decide the final
   GPU execution order.
```

This model also preserves the passthrough caveat: the proxy VM is not a native
host GPU process owner.  It reaches the physical GPU through the custom
passthrough path, so interrupt completion, memory-management behavior, and
Firecracker vCPU scheduling still affect `dispatch_call` and `map_wait`
latency even if the real Panthor scheduler sees ordinary-looking groups.

One security/isolation follow-up remains important.  A proxy session is
currently looked up by `session_id`, while the response is sent through the
current `rx->proxy_channel`.  The controlled tests use the session ID returned
to each client, but a stricter multi-tenant design should bind each
`panthor_proxy_session` to the channel/client identity that created it and
reject later requests for that session from any other proxy comm channel.

### Implemented Scheduler Path

The previous `proxy_comm_vmshm` channel-level policy knobs
`global_dispatch`, `dispatch_budget`, `highpri_work`, and `dispatch_stats`
were removed.  They made the transport layer decide fairness before the proxy
could see the real scheduling object.  That was too rigid for future quota,
priority, deadline, or weighted-fair policies.

The current code instead accepts requests through the normal proxy comm receive
path and moves the scheduling point into `panthor-proxy`:

```text
client request
  -> proxy_comm_vmshm receive
  -> panthor-proxy handler
  -> per-session GROUP_SUBMIT queue
  -> proxy submit scheduler worker
  -> panthor_vmshm_group_submit()
  -> real Panthor driver scheduler
```

The first implemented proxy-side policy is a small global submit scheduler with
per-session FIFO queues.  It picks one pending `GROUP_SUBMIT` from a runnable
session, requeues the session if more submits remain, and only then calls the
real Panthor submit helper.  This gives us a real policy hook at the correct
boundary: after requests have entered the proxy VM and after session identity is
known, but before work is pushed into the real DRM/Panthor scheduler.

The proxy comm handler registry was also changed from a mutex held across the
handler call into an `rwsem` at
`Linux-Guest-GPU/drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c:297`:

```text
dispatch path:        down_read() while looking up and executing the handler
register/unregister: down_write()
```

This removes a hidden multi-client serialization point.  The old lock shape
protected handler lifetime, but it also forced proxy-side Panthor RPC handling
from different client channels to run one at a time.  That meant two ready
client channels could still behave like a single proxy-side channel once they
entered the shared handler registry.  The new shape still prevents unregister
while a handler is active, while allowing multiple client channels to execute
registered handlers concurrently when the rest of the proxy/Panthor path can
make progress.

Because global dispatch scans a shared channel list, the proxy comm device now
uses `dispatch_refs` plus a wait queue so device removal waits until global
dispatch is no longer using that channel.

The real Panthor scheduler in the proxy VM now has diagnostic parameters:

```text
panthor.sched_tick_ms=N
panthor.sched_highpri_wq=1
```

`sched_tick_ms` changes the CSF scheduler tick period from the default 10 ms
for experiments such as `2 ms`.  `sched_highpri_wq=1` allocates the
`panthor-csf-sched` workqueue with `WQ_HIGHPRI`, while preserving
`WQ_MEM_RECLAIM`.  These knobs should be treated as proxy-VM scheduling
experiments, not as proof that the upstream Panthor defaults are wrong.

The two-client runner now exposes only host placement, Panthor diagnostic knobs,
and proxy group-core partitioning.  The removed transport-layer proxy comm
knobs are intentionally not part of the current interface:

```text
--gles-host-online-cpus LIST
--gles-broker-cpus LIST
--gles-proxy-cpus LIST
--gles-client0-cpus LIST
--gles-client1-cpus LIST
--gles-panthor-sched-tick-ms N
--gles-panthor-sched-highpri-wq
```

The older recommended policy for two 64 MiB GLES shared clients on the
constrained remote host was:

```text
host CPUs online:        0-3 during the run, then restore the previous state
broker/proxy placement: broker 0-1, proxy Firecracker 0-1
client placement:       client0 on CPU 2, client1 on CPU 3
proxy vCPUs:            2
client vCPUs:           1 each
proxy memory:           at least 184 MiB in current tests
client memory:          184 MiB for formal 64 MiB samples, 128 MiB is OK only
                        for the final short 4 MiB sanity smoke
proxy comm:             historical global_dispatch=1, dispatch_budget=1,
                        highpri_work=1; removed in the current code
proxy Panthor:          sched_highpri_wq=1, sched_tick_ms=2
stats:                  off for formal timing, on only for diagnosis
metric:                 PERF_ITER_US with --exclude-cpu-prepare
```

Those runs are kept as historical evidence, but the channel-level fairness
knobs are no longer the design direction.  The host affinity result still
matters because it keeps concurrent client upload paths and proxy passthrough
vCPUs from thrashing on a tiny online CPU set.  The handler `rwsem` still
matters because it avoids cross-channel serialization inside the proxy comm
handler registry.  GPU work scheduling, however, now belongs inside
`panthor-proxy` before real Panthor submit, not inside proxy comm channel
drain policy.

### Two-Client 64 MiB Results

The host-direct reference for this section is the same-topology host baseline:

```text
run id: gpu-perf-host-direct-64m-cpu4-for-shared-affinity-20260605-1200
host direct avg: 21354.50 us
metric: PERF_ITER_US avg, --exclude-cpu-prepare
```

Formal shared numbers below are no-stats runs.  Stats-on runs are excluded from
the main performance comparison because instrumentation changes timing.

| Run | Config | Result | client0 avg/max | client1 avg/max | shared avg | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `vmshm-2client-gles-64m-newdefault-m184-nostats-20260605-130737` | default proxy dispatch, m184, auto guard | PASS | 25110.00 / 28038 us | 24364.25 / 25799 us | 24737.13 us | stable post-change baseline |
| `vmshm-2client-gles-64m-global-b1-hi-t2-m184-guard900-nostats-20260605-131044` | historical removed transport-layer `global_dispatch=1`, `budget=1`, high-priority proxy comm, Panthor high-priority scheduler WQ, `sched_tick_ms=2`, m184, manual guard 900 MiB | PASS | 24095.50 / 24304 us | 24783.90 / 31322 us | 24439.70 us | old channel-fairness sample |
| `vmshm-2client-gles-64m-newdefault-m232-nostats-20260605-130545` | default proxy dispatch, m232 | PASS | 27949.55 / 80007 us | 24399.40 / 25787 us | 26174.48 us | one client hit a large `dispatch_call` tail |
| `vmshm-2client-gles-4m-global-final-mixmem-nostats-20260605-131645` | final `rwsem` kernel, 4 MiB, proxy184/client128, global fair policy | PASS | 5285.33 us | 5591.00 us | 5438.17 us | final sanity smoke after the handler-lock change |
| `vmshm-2client-gles-4m-global-final-smoke-20260605-131448` | proxy128/client128, stats/global mode | FAIL | - | - | - | proxy VM OOM in Panthor GEM/shmem metadata path; not a performance data point |

Derived ratios:

```text
default m184 host/shared:
  21354.50 / 24737.13 = 0.863

global fair policy host/shared:
  21354.50 / 24439.70 = 0.874

global fair policy improvement over default m184:
  24737.13 -> 24439.70 us = 1.20%

previous best affinity sample:
  vmshm-2client-gles-64m-nostats-wc-affinity-20260605-1154
  shared avg = 24299.23 us
  host/shared = 21354.50 / 24299.23 = 0.879
```

The old global fair policy was only slightly faster than the stable m184
default sample, and slightly slower than the earlier best affinity sample.  It
showed that fairness mattered, but it also proved the channel layer was a poor
place to encode long-term policy because it could not see session/group
semantics.  The current replacement is the panthor-proxy submit scheduler.

Phase averages for the two relevant 64 MiB no-stats runs:

| Run | buffer_upload | dispatch_call | map_wait | Shared avg |
| --- | ---: | ---: | ---: | ---: |
| default m184 | 14119.98 us | 1642.23 us | 8887.73 us | 24737.13 us |
| global fair m184 | 13747.75 us | 1817.00 us | 8788.20 us | 24439.70 us |

This split shows that the old channel-level policy was not a simple
`GROUP_SUBMIT` win.  The
overall average improved mostly through slightly better upload/completion
balance in this sample, while `dispatch_call` itself was a little higher than
the default m184 run.  The real benefit is fairness and tail avoidance rather
than a large mean-latency collapse.

### Stats-On Diagnostic Run

The short stats run was:

```text
run id:
  vmshm-2client-gles-64m-global-b1-hi-t2-m184-guard850-stats8-20260605-131133
workload:
  64 MiB, iterations=8, warmup=2, --exclude-cpu-prepare
```

Historical proxy comm dispatch evidence from the removed channel-level policy:

```text
minor=0 highpri_work=1 global_dispatch=1 dispatch_budget=1
entries=7584 msgs=3171 empty=4413 errors=0 budget_yields=3171
max_batch=1 handler_avg_ns=277322 handler_max_ns=93046334

minor=1 highpri_work=1 global_dispatch=1 dispatch_budget=1
entries=7581 msgs=3170 empty=4411 errors=0 budget_yields=3170
max_batch=1 handler_avg_ns=264822 handler_max_ns=92369959
```

This confirmed that global dispatch was active and that one channel never
processed more than one request in a pass (`max_batch=1`).  The almost equal
message counts also show that both client channels were serviced under the
same dispatch policy.

Important Panthor/proxy RPC evidence:

```text
PANTHOR_JOB_IRQ_STATS:
  raw_to_thread_avg_ns = 14220
  raw_to_thread_max_ns = 78458

PANTHOR_PROXY_RPC_STATS:
  DEV_QUERY              calls=2014 avg=566026 ns  max=4239667 ns
  VM_BIND                calls=56   avg=3893994 ns max=93043708 ns
  SYNCOBJ_TIMELINE_WAIT  calls=64   avg=2587279 ns max=11580041 ns
  GROUP_SUBMIT           calls=22   avg=622840 ns  max=1503542 ns
  TILER_HEAP_CREATE      calls=2    avg=31024729 ns max=36977209 ns
```

The key conclusion is that `GROUP_SUBMIT` is not the dominant cost in this
GLES smoke.  The large tails are in setup/control operations such as `VM_BIND`
and `TILER_HEAP_CREATE`, plus sync wait paths.  The Panthor threaded IRQ path
itself is not showing a multi-millisecond completion delay in this sample.

### Bottleneck Assessment

Current bottlenecks, ordered by evidence:

```text
1. Control-plane and setup RPC tails in the proxy VM.
   VM_BIND reached a 93 ms max in the stats run.  TILER_HEAP_CREATE averaged
   about 31 ms for two calls.  These operations are not per-kernel GPU compute
   time, but they strongly affect short and first-use workloads.

2. Client BO upload remains larger than host-direct.
   The best affinity/global samples still spend about 13.7-14.1 ms in
   buffer_upload for 64 MiB, while the same-topology host direct baseline was
   about 11.7 ms.  This is expected because the shared path writes through the
   client VM, vmshm-object mappings, Firecracker placement, and proxy-visible
   BO setup rather than a native host userspace mapping.

3. Dispatch-call mean is acceptable, but tails still matter.
   Stable samples show about 1.6-1.8 ms dispatch_call.  A default m232 run
   still produced an 80 ms iteration max driven by a dispatch-call tail, which
   is exactly the class of behavior the new panthor-proxy submit scheduler is
   meant to bound under multi-client pressure.

4. Proxy VM memory pressure is real.
   proxy=128 MiB produced an OOM panic in
   panthor_gem_create_vmshm_with_handle -> drm_gem_shmem_create during a
   two-client 4 MiB stats/global run.  Current formal 64 MiB tests should keep
   proxy memory at 184 MiB or higher, and any manual memory guard override must
   be recorded with the result.

5. Panthor CSG round-robin is not yet the main measured limiter for this
   smoke.
   With only two clients and enough available CSG slots, the dominant
   evidence points to proxy control/setup paths and host/proxy scheduling,
   not to steady-state GPU command-stream slot starvation.  Larger client
   counts or workloads with persistent queues may change this.
```

### Next Optimization Directions

Near-term optimizations that match the measured bottlenecks:

```text
1. Reduce first-use RPC volume.
   Cache immutable DEV_QUERY results per proxy device/session class instead of
   forwarding hundreds or thousands of identical queries during setup-heavy
   GLES startup.

2. Batch VM_BIND metadata where the UAPI sequence allows it.
   Flattened BO and mapping arrays already live in vmshm-comm.  The next step
   is to reduce request/response turns and avoid one vmshm doorbell per small
   bind fragment when a client submits a burst.

3. Pre-create or pool proxy-side shared GEM wrappers for common BO sizes.
   The OOM and TILER/VM_BIND tails both point at expensive allocation/setup
   paths.  Pooling must preserve per-client handle namespaces and vm lifetime,
   and it must keep vmshm-object ownership separate from vmshm-comm control
   metadata.

4. Extend the panthor-proxy submit scheduler.
   The new scheduling point is after proxy request reception and before real
   Panthor submit.  For N clients and mixed workloads, add weighted fair
   queueing, per-client inflight limits, priorities, or deadlines here rather
   than in the proxy comm channel drain path.

5. Move from diagnostic Panthor knobs to workload-aware proxy policy.
   `sched_tick_ms=2` and high-priority scheduler workqueue are useful probes.
   A production policy should instead classify proxy-submitted groups by
   client/session, keep per-client queue depth visible, and avoid letting one
   client monopolize available CSG slots when more client VMs are active.

6. Keep formal timing no-stats and CPU-prepare-excluded.
   Proxy RPC stats and client RPC stats are essential for diagnosis, but they
   change timing.  Use short stats runs to locate the bottleneck, then repeat
   no-stats runs for the performance table.
```

### Validation

Local kernel build after the scheduler changes:

```text
./scripts/build/build-guest-vmshm-kernels.sh
result: PASS
installed:
  GPU-SFTP/firecracker-bins/kernels/shared/client/Image
  GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

Static checks used during the scheduler update:

```text
bash -n scripts/run/run-vmshm-2client-e2e.sh
git diff --check -- Linux-Guest-GPU/drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c scripts/run/run-vmshm-2client-e2e.sh
```

Final short smoke after the handler `rwsem` change:

```text
run id:
  vmshm-2client-gles-4m-global-final-mixmem-nostats-20260605-131645
result:
  RESULT: GLES_PASS
client0:
  COMPUTE_CHECK=PASS
  GPU_SMOKE_RESULT=PASS
  PERF_ITER_US avg=5285.33 us
client1:
  COMPUTE_CHECK=PASS
  GPU_SMOKE_RESULT=PASS
  PERF_ITER_US avg=5591.00 us
```

## 2026-06-05: 32 MiB Two-Client Proxy Scheduling Rebaseline

### Goal

The scheduling target is now the 32 MiB GLES smoke with two concurrent client
VMs submitting through one proxy VM.  Smaller 4 MiB and 16 MiB runs are still
useful for smoke coverage, but they are too dominated by fixed overheads to be
the main scheduling signal.  The formal timing remains:

```text
--count 8388608 --iterations 20 --warmup 5 --perf --exclude-cpu-prepare
```

The tested topology is unchanged:

```text
client0 VM / client1 VM
  -> panthor-client
  -> client_vmshm_comm
  -> vmshm-broker
  -> proxy_comm_vmshm
  -> panthor-proxy
  -> real Panthor in the proxy VM
  -> custom passthrough GPU path
```

This means scheduling has to consider host process placement, proxy comm
transport latency, panthor-proxy submit-before-real-DRM policy, real Panthor
CSF scheduling, and the custom passthrough interrupt/memory-management path
used by the proxy VM.

The two memslots remain separate and unchanged:

```text
vmshm-object: BO payloads and other proxy/client-visible shared objects.
vmshm-comm:   ioctl metadata, flattened arrays, handles, RPC/control data.
```

### New Experimental Knob

Added an explicit proxy-side group core partition experiment:

```text
panthor_proxy.group_core_partitions=N
```

The two-client runner exposes it as:

```text
--gles-panthor-proxy-group-core-partitions N
```

Default is `0`, which preserves Mesa/Panthor group masks.  With `N=2`, the
proxy splits each group's shader core mask by proxy session ID before calling
real Panthor `GROUP_CREATE`.  For the current RK3588/Mali-G610 mask
`0x50005`, the two sessions were assigned:

```text
session 1: compute_mask 0x50005 -> 0x5,     max_compute 4 -> 2
session 2: compute_mask 0x50005 -> 0x50000, max_compute 4 -> 2
```

This is intentionally an experiment, not a default scheduling policy.  It is
useful for testing whether explicit proxy partitioning can outperform the real
Panthor/FW scheduler when two client VMs submit concurrently.

### Test Matrix

All three runs used:

```text
proxy/client memory: proxy 184 MiB, each client 128 MiB
vCPUs:               proxy 2, each client 1
host CPUs online:    0-3
broker/proxy CPUs:   0-1
client CPUs:         client0 CPU 2, client1 CPU 3
sync start:          60 seconds
stats:               off
metric:              PERF_ITER_US / iter_total, CPU prepare excluded
```

| Run | Proxy policy | Result | client0 avg/max | client1 avg/max | shared avg |
| --- | --- | --- | ---: | ---: | ---: |
| `vmshm-2client-gles-32m-corepart-baseline-20260605-150001` | historical transport-layer default, no Panthor/proxy knobs | PASS | 15700.75 / 19094 us | 15337.90 / 20646 us | 15519.33 us |
| `vmshm-2client-gles-32m-corepart2-20260605-150103` | `group_core_partitions=2` | PASS | 22999.40 / 26489 us | 24476.20 / 29688 us | 23737.80 us |
| `vmshm-2client-gles-32m-global-b1-hi-t2-recheck-20260605-150208` | historical removed transport-layer `global_dispatch=1`, `dispatch_budget=1`, high-priority proxy comm, Panthor high-priority scheduler WQ, `sched_tick_ms=2` | PASS | 15959.85 / 22524 us | 15477.05 / 18092 us | 15718.45 us |

### Phase Evidence

| Run | buffer_upload avg | dispatch_call avg | map_wait avg | shared avg |
| --- | ---: | ---: | ---: | ---: |
| historical transport default | 6960.65 us | 1799.10 us | 6669.78 us | 15519.33 us |
| core partition 2 | 7561.10 us | 2276.68 us | 13795.20 us | 23737.80 us |
| global b1 hi t2 | 6991.25 us | 1951.63 us | 6685.20 us | 15718.45 us |

The core partition run is correctness-valid but performance-negative.  The
regression is dominated by `map_wait`, which roughly doubled from about
`6.67 ms` to `13.80 ms`.  That strongly suggests the compute kernel became
slower because each client group was restricted to half the shader cores.  It
does not look like a proxy RPC or `GROUP_SUBMIT` metadata win/loss.

The global dispatch recheck was also correctness-valid, but it was slightly
slower than the transport default at this workload size.  This historical
result is why the channel-level global worker has been removed: it was fair in
a narrow queueing sense, but it could not see GPU scheduling semantics and sync
wait handlers could still block in the proxy.  The current design lets channel
requests enter the proxy VM and schedules only `GROUP_SUBMIT` before real DRM
submission.

### Current 32 MiB Scheduling Policy

For two-client 32 MiB shared-GPU performance runs, the current best policy is:

```text
host CPUs online:        0-3
broker/proxy placement: broker 0-1, proxy Firecracker 0-1
client placement:       client0 on CPU 2, client1 on CPU 3
proxy vCPUs:            2
client vCPUs:           1 each
proxy memory:           at least 184 MiB
client memory:          128 MiB for this 32 MiB smoke
proxy comm:             fast transport only; no channel-level fairness knobs
proxy submit scheduler: panthor-proxy per-session FIFO, global runnable-session
                        round-robin before real Panthor GROUP_SUBMIT
proxy Panthor knobs:    default scheduler tick/workqueue
proxy group cores:      no manual partitioning
stats:                  off for formal timing
metric:                 PERF_ITER_US with --exclude-cpu-prepare
```

In short: keep the host/proxy/client CPU placement explicit, keep proxy comm as
a transport, schedule GPU work at the panthor-proxy submit boundary, and let the
real Panthor driver manage shader cores.  Do not reintroduce
`global_dispatch=1`/`dispatch_budget=1` at the channel layer, and do not make
`group_core_partitions=2` the default for 32 MiB.

### Current Proxy Submit Scheduler Smoke

After moving scheduling out of proxy comm and into `panthor-proxy`, the first
32 MiB two-client smoke is:

```text
run id:
  vmshm-2client-gles-32m-proxy-submit-sched-20260605-162753
config:
  host CPUs online 0-3
  broker/proxy CPUs 0-1
  client0 CPU 2, client1 CPU 3
  proxy vCPUs 2, client vCPUs 1 each
  proxy memory 184 MiB, client memory 128 MiB each
  no proxy comm channel-level scheduling knobs
  default Panthor scheduler tick/workqueue
metric:
  PERF_ITER_US, --exclude-cpu-prepare
result:
  RESULT: GLES_PASS
```

| Run | Proxy policy | Result | client0 avg/max | client1 avg/max | shared avg |
| --- | --- | --- | ---: | ---: | ---: |
| `vmshm-2client-gles-32m-proxy-submit-sched-20260605-162753` | panthor-proxy per-session submit scheduler before real Panthor submit | PASS | 14668.00 / 45731 us | 13232.45 / 16140 us | 13950.23 us |

Phase averages:

| Client | buffer_upload avg | dispatch_call avg | map_wait avg | iter_total avg |
| --- | ---: | ---: | ---: | ---: |
| client0 | 6768.30 us | 3896.60 us | 3921.30 us | 14668.00 us |
| client1 | 6843.50 us | 2195.90 us | 4079.55 us | 13232.45 us |

The smoke confirms that the new scheduling point is functional with two
concurrent clients.  The mean result is better than the earlier 32 MiB
transport-layer baseline (`15519.33 us`), but client0 still had one large
`dispatch_call` tail (`38567 us`).  That means the direction is right, while
the next policy work should add scheduler diagnostics and real per-client
inflight/priority accounting inside `panthor-proxy`.

### Design Conclusion

The proxy VM should not try to "perfect" scheduling by hard-slicing shader
cores for this workload.  The real Panthor scheduler and firmware are already
better at exploiting the available G610 cores than the coarse proxy split.  The
proxy should instead:

```text
1. Preserve per-client request order by queueing `GROUP_SUBMIT` per session.
2. Keep blocking sync waits and setup RPCs out of the GPU submit scheduler.
3. Maintain explicit host CPU placement for client upload, proxy passthrough,
   and broker work.
4. Use Panthor scheduler knobs and core partitioning only as diagnostics until
   a workload proves they help.
5. Optimize remaining overhead in BO upload, sync wait behavior, VM_BIND/setup
   batching, and immutable DEV_QUERY caching rather than reducing GPU cores per
   client.
```

### Validation

Build and static checks:

```text
bash -n scripts/run/run-vmshm-2client-e2e.sh
git diff --check -- scripts/run/run-vmshm-2client-e2e.sh \
  docs/skills/gpu-shared-virtualization-autotest/SKILL.md \
  docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md \
  Linux-Guest-GPU/include/linux/vmshm_comm.h \
  Linux-Guest-GPU/drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c \
  Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c
git -C Linux-Guest-GPU diff --check -- \
  drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c \
  drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c \
  include/linux/vmshm_comm.h
./scripts/build/build-guest-vmshm-kernels.sh
```

Current proxy-submit-scheduler 32 MiB smoke passed:

```text
run id: vmshm-2client-gles-32m-proxy-submit-sched-20260605-162753
RESULT: GLES_PASS
GL_RENDERER=Mali-G610 (Panfrost)
PERF_CPU_PREPARE_EXCLUDED=1
COMPUTE_CHECK=PASS
GPU_SMOKE_RESULT=PASS
```

## 2026-06-05: 32 MiB Two-Client Clean-Memory Recheck

### Goal

Before committing the current shared virtualization scheduling work, clean the
remote host memory as much as possible, rerun the formal two-client 32 MiB GLES
smoke, and compute the `host/client` ratios with the CPU input-fill time
excluded.

### Cleanup

The remote host was cleaned before the run:

```text
pkill firecracker/vmshm-broker
sync
drop_caches=3
compact_memory=1
```

The manual cleanup raised the remote host free memory from about `1475 MiB` to
about `1922 MiB`, and the runner preflight saw `MemAvailable=1902 MiB` before
VM launch.  After the test, the host was cleaned again and returned to
`MemAvailable=1822 MiB`; host CPUs were restored to `0-1`.

### Test

```text
run id: vmshm-2client-gles-32m-cleanmem-20260605-165531
result: RESULT: GLES_PASS
workload: 32 MiB, count=8388608
iterations: 20 measured, 5 warmup
metric: PERF_ITER_US / iter_total, --exclude-cpu-prepare
host direct baseline: gpu-perf-host-direct-32m-current-20260605-152347
host direct avg: 11058.75 us
```

Placement and policy:

```text
host CPUs online:        0-3
broker/proxy placement: 0-1
client placement:       client0 CPU 2, client1 CPU 3
proxy vCPUs:            2
client vCPUs:           1 each
proxy memory:           184 MiB
client memory:          128 MiB each
object memslot:         128 MiB for this 32 MiB workload
proxy comm:             no channel-level scheduling knobs
proxy submit scheduler: per-session FIFO plus global runnable-session
                        round-robin before real Panthor GROUP_SUBMIT
```

### Result

| Workload | Host direct | Client0 shared | Client1 shared | Shared avg | Host/client0 | Host/client1 | Host/shared avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 MiB | 11058.75 us | 13207.50 us | 13146.20 us | 13176.85 us | 0.837 | 0.841 | 0.839 |

Phase detail:

| Client | buffer_upload avg | dispatch_call avg | map_wait avg | iter_total avg/max |
| --- | ---: | ---: | ---: | ---: |
| client0 | 7118.70 us | 1777.20 us | 4230.65 us | 13207.50 / 15442 us |
| client1 | 6732.75 us | 1866.40 us | 4450.20 us | 13146.20 / 17939 us |

### Interpretation

This clean-memory rerun is better than the first proxy-submit-scheduler sample
(`13950.23 us` shared avg) and keeps the two clients very close:

```text
client delta: 13207.50 - 13146.20 = 61.30 us
shared overhead vs host: 13176.85 / 11058.75 - 1 = about 19.2%
```

The important conclusion is not that the proxy scheduler is perfect, but that
the current placement plus proxy-side submit scheduling is stable enough to use
as the 32 MiB baseline.  The remaining overhead is still concentrated in
`buffer_upload`, `dispatch_call`, and `map_wait`; the scheduler work should now
focus on per-client inflight accounting, submit batching opportunities, and
diagnostics for tail latency rather than reviving channel-level dispatch
policy.

## 2026-10-14: One-Client Native/Proxy ML And glmark2 Recheck

This recheck answered a narrower question than a full ML/graphics qualification:
with one vmshm client, do the two formal correctness-checked ML kernels retain
correctness and near-native throughput, and where does glmark2 stop?  No SD or
eMMC flashing was performed in this recheck.

### Node selection and artifacts

The one-client runner now defaults `GLES_DRM_NODE` to
`/dev/dri/renderD128`.  An explicitly empty `GLES_DRM_NODE` still selects the
old card-then-render-node discovery path.  `gpu-smoke.sh` consumes that value as
`GPU_SMOKE_DRM_NODE` for both glmark2 renderer qualification and the ML
workload, avoiding accidental double positional node arguments.

glmark2 was no longer treated as a blocked prerequisite.  It was built natively
on the RK3588 from upstream commit
`22c527cb0556f3a1ac4445aaa52cc532760928d5` in these flavors:

- stock GBM;
- stock surfaceless null;
- null-noop, which skips the invalid `eglSwapBuffers(EGL_NO_SURFACE)` call;
- GBM render-only and render-only-debug diagnostic builds.

Artifacts and build metadata are under `GPU-SFTP/artifacts/glmark2-arm64/`.

### Interleaved proxy ML repeatability

Eight one-client runs used 20 measured iterations and 5 warmup iterations.
Client and proxy VM memory were both 512 MiB.  All runs passed `ML_CHECK` and
`ML_RESULT`.

| Kernel | DRM node | Runs | Mean iteration | Mean throughput | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `conv2d_64x64x32_3x3_fp32` | `/dev/dri/card0` | 2 | 24747.15 us | 3.051 GOps/s | PASS |
| `conv2d_64x64x32_3x3_fp32` | `/dev/dri/renderD128` | 2 | 25396.72 us | 2.976 GOps/s | PASS |
| `depthwise_conv_128x128x128_3x3_fp32` | `/dev/dri/card0` | 2 | 17708.85 us | 2.132 GOps/s | PASS |
| `depthwise_conv_128x128x128_3x3_fp32` | `/dev/dri/renderD128` | 2 | 18566.90 us | 2.033 GOps/s | PASS |

Run family:

```text
shared-ml-{conv,depthwise}-{renderD128,card0}-repeat{1,2}-20261014-175633
```

The earlier one-order-of-magnitude slowdown attributed to proxy `card0` was not
reproduced.  That historical sample remains a diagnostic observation, not an
inherent node-selection result.

### 100-iteration native/proxy comparison

The native Panthor run temporarily replaced `pmthor` with `panthor`, ran both
nodes, and restored the host to `pmthor`:

```text
native run: native-panthor-ml-conv-depthwise-repeat3-100it-20261014-180343
restore:    RESTORE_FINAL=pmthor; PMTHOR_NODE=yes
```

| Path | Kernel | DRM node | Correctness | Avg iteration | Throughput | Run |
| --- | --- | --- | --- | ---: | ---: | --- |
| native Panthor | conv2d | renderD128 | PASS | 24193.37 us | 3.121 GOps/s | native repeat3 |
| native Panthor | depthwise | renderD128 | PASS | 18796.35 us | 2.008 GOps/s | native repeat3 |
| native Panthor | conv2d | card0 | PASS | 25318.33 us | 2.982 GOps/s | native repeat3 |
| native Panthor | depthwise | card0 | PASS | 19286.89 us | 1.957 GOps/s | native repeat3 |
| proxy one-client | conv2d | card0 | PASS | 25184.86 us | 2.998 GOps/s | `shared-ml-conv-default-repeat-100it-20261014-175948` |
| proxy one-client | depthwise | card0 | PASS | 17060.03 us | 2.213 GOps/s | `shared-ml-depthwise-default-repeat-100it-20261014-175948` |
| proxy one-client | conv2d | renderD128 | PASS | 24068.85 us | 3.137 GOps/s | `shared-ml-conv-renderd128-repeat-100it-20261014-180417` |
| proxy one-client | depthwise | renderD128 | PASS | 19789.62 us | 1.908 GOps/s | `shared-ml-depthwise-renderd128-repeat-100it-20261014-180417` |

Two earlier native attempts are not performance samples.  Their shell loop
passed bare `renderD128`/`card0` names to the binary, which tried to open those
strings as relative paths.  Both traps nevertheless restored `pmthor`.  The
successful third attempt used absolute `/dev/dri/...` paths.

Every proxy 100-iteration client log also contains exactly 110
`MESA: error: export failed` messages: one per warmup or measured dispatch.
This does not invalidate the ML correctness marker or timing, but the proxy ML
path is not error-free and must not be described as a fully native-equivalent
frontend.

### glmark2 outcome

| Path and configuration | Size | Result | Score | First meaningful failure or caveat |
| --- | ---: | --- | ---: | --- |
| native Panthor GBM | 800x600 | PASS | 2899 | none |
| native Panthor GBM | 1280x720 | PASS | 2728 | none |
| native Panthor null-noop + finish | 800x600 | PASS | 1672 | none |
| native Panthor null-noop + finish | 1280x720 | PASS | 1499 | none |
| native Panthor null-noop + none | 800x600 | FAIL | none | repeated `VM_BIND err=12`, then process killed (`rc=137`) |
| proxy GBM | 800x600 | FAIL | none | SIGSEGV before renderer/score |
| proxy upstream null | 800x600 | FAIL | none | validation reaches 26 success / 1 failure / 6 unknown, but refract setup hits `BO_CREATE err=12`; full run times out with 131401 export failures |
| proxy null-noop + none | 800x600 | FAIL | none | 83381 `BO_CREATE err=12`, one `VM_BIND err=110`, then SIGSEGV; 768 MiB only delays it |
| proxy null-noop + finish | 800x600 | diagnostic dirty run | raw 500 | `rc=0`, but 160460 export failures and 28 `VM_BIND err=17`; parser correctly does not promote it to PASS |
| proxy null-noop + finish | 1280x720 | FAIL | none | 108080 export failures, `BO_CREATE err=12`, then SIGSEGV |
| proxy GBM render-only | 800x600 | FAIL | none | early SIGSEGV |
| proxy GBM render-only-debug | 800x600 | FAIL | none | GBM device, EGL display/config/surface/context creation succeed; SIGSEGV inside `eglMakeCurrent()` |

Native fixed validation run:

```text
native-panthor-glmark2-gbm-validate-fixed-20261014-074620
GLMARK_VALIDATE_RC=0
GLMARK_VALIDATE_SUCCESS=26 FAILURE=1 UNKNOWN=6
```

The one deterministic validation mismatch is
`[function] fragment-complexity=medium`; it is also present on native
Panfrost/Panthor and is not evidence of a vmshm-client-only rendering defect.

### Bounded conclusion

For the two formal ML kernels and a single vmshm client, both DRM nodes are
currently usable and throughput is close to the native Panthor samples; some
proxy samples are faster and some slower, so this dataset bounds the path but
does not establish a precise overhead percentage.  glmark2 does not yet pass
through the proxy.  The failures converge on frontend resource lifecycle, fence
export, `BO_CREATE`/`VM_BIND` exhaustion, or `eglMakeCurrent()`, rather than on
the absence of the benchmark binary.

The result must not be generalized to “all ML kernels pass”: at this checkpoint
GEMM was still a diagnostic implementation, while reduction, softmax, and
attention failed
correctness on both native and proxy paths and are not vmshm attribution
evidence.  `GPU_SMOKE_RESULT=PASS` also never overrides a failed glmark2
summary.

Final host state after the recheck:

```text
driver=pmthor
pmthor_node=yes
firecracker=none
vmshm-broker=none
gpu-smoke.sh sha256=de2069ec9fa9056a748bc4b6f15155efc554a5d7b80980708dfb9be74dc1c05a
```

## 2026-10-14: Post-reboot GEMM formalization and native 1080p glmark2

This follow-up did not repeat the failed proxy glmark2 configurations or touch
SD/eMMC storage.  It recovered the RK3588 host memory baseline with an ordinary
SSH reboot, completed the larger GEMM formal comparisons, and reduced wasted
wait time after a Firecracker client exits early.

### Host memory recovery and runner behavior

Before the reboot, with no Firecracker or `vmshm-broker` process alive, the host
still reported only about 247–257 MiB `MemAvailable`, about 2.5 GiB
`Active(anon)`, and no swap.  Under that state:

| Run | Client/proxy memory | Result | First meaningful failure |
| --- | ---: | --- | --- |
| `shared-ml-v6-gemm256-formal-112c64p-20261014-193822` | 112/64 MiB | FAIL | proxy 64 MiB was too small for its kernel image; this configuration is not valid |
| `shared-ml-v6-gemm256-formal-112c96p-20261014-194005` | 112/96 MiB | FAIL | client kernel reached `System is deadlocked on memory` |
| `shared-ml-v6-gemm256-formal-128c96p-20261014-194239` | 128/96 MiB | FAIL | host OOM killed the client Firecracker before `gles-ml-smoke` printed a result |

The ordinary reboot restored the SD-booted `6.12.0-opencca-pmthor` system to
about 3.2 GiB `MemAvailable`.  The same 128/96 MiB VM configuration then
passed.  Therefore the v6 GEMM failures are host/guest memory-capacity
observations, not GPU-sharing performance data.

`scripts/run/run-vmshm-e2e.sh` now has `wait_for_client_log()`, which checks the
expected result marker while also checking `client.pid`.  If the client
Firecracker process is OOM-killed or exits early, the run reports:

```text
client process exited before producing a result marker
```

The client smoke, glmark2, ML, compute, and DRM frontend waits use this helper,
so an early client exit no longer consumes the full 900-second workload wait.
The helper still does not watch a proxy process that exits first; that remains
a useful follow-up improvement.

### Native 1080p glmark2 completion

The previously captured 1080p native sample was parsed and retained locally:

| Path | Configuration | Size | Result | Score | Renderer | Restore |
| --- | --- | ---: | --- | ---: | --- | --- |
| native Panthor | stock GBM, `--off-screen=3` | 1920x1080 | PASS | 1960 | Mali-G610 (Panfrost) | `RESTORE_FINAL=pmthor; PMTHOR_NODE=yes` |

Run and local artifact:

```text
remote run: native-panthor-glmark2-gbm-1080p-20261014-104006
local log:  GPU-SFTP/log/native/native-panthor-glmark2-gbm-1080p-20261014-104006/
source tar: /tmp/native-panthor-glmark2-gbm-1080p-20261014-104006.tar.gz
```

### Formal native/proxy GEMM comparison

All rows below use the current v5 ML harness, 100 measured iterations, 10
warmup iterations, and report `ML_CHECK=PASS` plus `ML_RESULT=PASS`.  Native
rows temporarily switched `pmthor` to Panthor and then restored `pmthor`; proxy
rows used one Firecracker client, one Firecracker proxy, 128 MiB client memory,
and 96 MiB proxy memory.

For the ratio column, the native baseline is the arithmetic mean of that
kernel's successful renderD128 and `card0` samples.  The first post-reboot
renderD128 proxy sample in each kernel is retained as a cold-start diagnostic:
it is much slower than all following repeats and is not used for the stable
overhead conclusion.

| Kernel | Path and run phase | DRM node | Avg iteration | Throughput | Relative time vs native mean | Run |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `gemm_256_fp32` | native Panthor | renderD128 | 3114.45 us | 10.774 GOps/s | 1.01x | `native-panthor-ml-gemm256-v5-100it-20261014-114641` |
| `gemm_256_fp32` | native Panthor | card0 | 3043.35 us | 11.025 GOps/s | 0.99x | `native-panthor-ml-gemm256-v5-100it-20261014-114641` |
| `gemm_256_fp32` | proxy one-client, post-reboot cold diagnostic | renderD128 | 12237.97 us | 2.742 GOps/s | 3.97x | `shared-ml-v7-gemm256-formal-128c96p-postreboot-20261014-194506` |
| `gemm_256_fp32` | proxy one-client, warm repeat | card0 | 4993.91 us | 6.719 GOps/s | 1.62x | `shared-ml-v7-gemm256-formal-card0-128c96p-postreboot-20261014-194913` |
| `gemm_256_fp32` | proxy one-client, warm repeat | renderD128 | 5013.85 us | 6.692 GOps/s | 1.63x | `shared-ml-v7-gemm256-formal-renderd128-r2-128c96p-postreboot-20261014-195008` |
| `gemm_256_fp32` | proxy one-client, warm repeat | renderD128 | 5039.96 us | 6.658 GOps/s | 1.64x | `shared-ml-v7-gemm256-formal-renderd128-r3-128c96p-postreboot-20261014-195102` |
| `gemm_512_fp32` | native Panthor | renderD128 | 20670.78 us | 12.986 GOps/s | 1.00x | `native-panthor-ml-gemm512-v5-100it-20261014-114743` |
| `gemm_512_fp32` | native Panthor | card0 | 20695.01 us | 12.971 GOps/s | 1.00x | `native-panthor-ml-gemm512-v5-100it-20261014-114743` |
| `gemm_512_fp32` | proxy one-client, post-reboot cold diagnostic | renderD128 | 59148.85 us | 4.538 GOps/s | 2.86x | `shared-ml-v7-gemm512-formal-128c96p-postreboot-20261014-194703` |
| `gemm_512_fp32` | proxy one-client, warm repeat | card0 | 35752.40 us | 7.508 GOps/s | 1.73x | `shared-ml-v7-gemm512-formal-card0-128c96p-postreboot-20261014-194933` |
| `gemm_512_fp32` | proxy one-client, warm repeat | renderD128 | 35656.24 us | 7.528 GOps/s | 1.72x | `shared-ml-v7-gemm512-formal-renderd128-r2-128c96p-postreboot-20261014-195027` |
| `gemm_512_fp32` | proxy one-client, warm repeat | renderD128 | 35719.38 us | 7.515 GOps/s | 1.73x | `shared-ml-v7-gemm512-formal-renderd128-r3-128c96p-postreboot-20261014-195325` |

Warm proxy aggregates are:

| Kernel | Native two-node mean | Warm proxy mean | Warm relative time |
| --- | ---: | ---: | ---: |
| `gemm_256_fp32` | 3078.90 us | 5015.91 us | 1.63x |
| `gemm_512_fp32` | 20682.90 us | 35709.34 us | 1.73x |

The warm `renderD128` and `card0` proxy samples are close for both kernels.
The cold-start samples are observations only; this dataset does not identify
their cause.

Every proxy GEMM client log contains exactly 110
`MESA: error: export failed` messages: one per warmup or measured dispatch.
The errors do not invalidate the explicit correctness and timing markers, but
they confirm that the proxy ML frontend is not error-free.

The native GEMM256 wrapper exited with rc=1 because its script initialized the
aggregate `TEST_RC` to one and never changed it after both child-node runs
passed.  Both child commands exited zero and produced `ML_CHECK=PASS`,
`ML_ITER_US`, and `ML_RESULT=PASS`; the wrapper bug does not change the two
performance samples.  The native GEMM512 wrapper corrected that aggregate
result handling and exited zero.

### Final state and bounded conclusion

```text
kernel: 6.12.0-opencca-pmthor
root:   /dev/mmcblk1p4
driver: pmthor
pmthor: /dev/pmthor present
firecracker/vmshm-broker: none
MemAvailable after the final GEMM512 r3 run: about 2.91 GiB
```

With a recovered host memory baseline, the single-client proxy path formally
passes the corrected GEMM256 and GEMM512 kernels.  Across the stable warm
repeats, proxy time is about 1.63x native for GEMM256 and about 1.73x native
for GEMM512; the much slower first post-reboot samples are cold-start
diagnostics rather than the formal overhead estimate.  This is a different
outcome from the near-native conv2d/depthwise results and should not be
collapsed into one average “GPU-sharing overhead”: kernel size, dispatch
pattern, buffer count, and frontend export/synchronization behavior all affect
the ratio.

### 2026-10-14 v7 softmax and attention completion

The v7 harness corrected attention dispatch timing so that the reported
iteration covers dispatch, fence, map, and readback.  All formal rows below use
100 measured iterations, 10 warmup iterations, and explicit `ML_CHECK` markers.
Native rows again restored `pmthor`; the proxy rows used one client VM at
128 MiB and one proxy VM at 96 MiB.

| Kernel | Path | Result | Avg iteration | Relative time | Run |
| --- | --- | --- | ---: | ---: | --- |
| `row_softmax_16384x256_fp32` | native, renderD128 | PASS | 14889.15 us | 0.98x vs native two-node mean | `native-panthor-ml-v7-softmax-formal-100it-20261014-202814` |
| `row_softmax_16384x256_fp32` | native, card0 | PASS | 15468.79 us | 1.02x vs native two-node mean | `native-panthor-ml-v7-softmax-formal-100it-20261014-202814` |
| `row_softmax_16384x256_fp32` | proxy one-client | PASS | 36881.74 us | 2.43x | `shared-ml-v7-softmax-formal-100it-128c96p-20261014-202734` |
| `single_head_attention_256x64_fp32` | native, renderD128 | PASS | 542428.17 us | 1.00x vs native two-node mean | `native-panthor-ml-v7-attention-formal-100it-20261014-123038` |
| `single_head_attention_256x64_fp32` | native, card0 | PASS | 540633.49 us | 1.00x vs native two-node mean | `native-panthor-ml-v7-attention-formal-100it-20261014-123038` |
| `single_head_attention_256x64_fp32` | proxy one-client | FAIL | not valid | not valid | `shared-ml-v7-attention-correctness-128c96p-20261014-202528` |

The native attention wrapper restored the expected runtime state:

```text
RESTORE_FINAL=pmthor; PMTHOR_NODE=yes; FIRECRACKER_COUNT=0; BROKER_COUNT=0
```

The proxy attention failure is a frontend synchronization/readback failure, not
a benchmark-availability failure.  Its first meaningful errors are:

```text
MESA: error: export failed
MESA: error: DMA_BUF_IOCTL_EXPORT_SYNC_FILE failed (err=-110)
Attention mismatch d=0 got=0.000000 expected=1.112571
ML_RESULT=FAIL
```

Do not report a proxy attention slowdown from that run: the output is zero at
readback, so there is no valid comparable execution time.  Every passing proxy
ML run in this set still emits 110 `MESA: error: export failed` messages, one
per warmup/measured dispatch; the frontend is functional for those kernels but
not error-free.

## 2026-10-14: One-client configuration matrix and NCNN/ONNX completion

This checkpoint stopped treating glmark2 availability as a prerequisite.  The
missing benchmark was built locally on the RK3588, the GLES size/configuration
matrix was completed, and testing moved on to NCNN and ONNX Runtime.  No SD or
eMMC storage was written.

### W1: one-client GLES compute size/configuration matrix

All formal rows use the corrected compute workload with 20 measured iterations,
5 warmup iterations, the Mali-G610/Panfrost renderer, `COMPUTE_CHECK=PASS`,
and CPU input preparation excluded from `iter_total`.  Unless stated otherwise,
client/proxy VM memory was 512/512 MiB and each VM had one vCPU.

| Workload/configuration | Client/proxy memory | Object window | Avg `iter_total` | Result and boundary | Run |
| --- | ---: | ---: | ---: | --- | --- |
| 4 MiB, default placement | 512/512 MiB | default | 3557.25 us | PASS | `shared-gles-size-4m-default-20261014-181724` |
| 16 MiB, default placement | 512/512 MiB | default | 5985.45 us | PASS | `shared-gles-size-16m-default-20261014-181916` |
| 64 MiB, default placement | 512/512 MiB | default | 21067.15 us | PASS | `shared-gles-size-64m-default-20261014-181930` |
| 64 MiB, proxy VM 384 MiB | 512/384 MiB | default | 21298.10 us | PASS; no improvement over default | `shared-gles-size-64m-proxy384-20261014-182310` |
| 64 MiB, cached client BO mmap | 512/512 MiB | default | 20763.75 us | PASS; diagnostic configuration | `shared-gles-size-64m-cached-bo-20261014-182238` |
| 64 MiB, broker/proxy/client CPUs 0/0/1 | 512/512 MiB | 128 MiB | 20129.65 us | PASS; best diagnostic placement | `shared-gles-size-64m-placement01-20261014-200409` |
| 64 MiB, proxy VM 2 vCPUs | 512/512 MiB | 128 MiB | 20339.35 us | PASS after wait fix | `shared-gles-size-64m-proxy2vcpu-fixedwait-20261014-200643` |
| 128 MiB, default object window | 512/512 MiB | default | not valid | FAIL: `DRM_IOCTL_PANTHOR_BO_CREATE err=12`, then `GL_OUT_OF_MEMORY` in `glBufferData` | `shared-gles-size-128m-default-20261014-181945` |
| 128 MiB, enlarged object window | 512/512 MiB | 224 MiB | 39820.80 us | PASS | `shared-gles-size-128m-object224-default-20261014-200349` |

The aborted `shared-gles-size-64m-placement-20261014-182307` attempt requested
client CPU 2 while only CPUs 0-1 were online; it is an invalid harness
configuration, not a GPU sample.  The first proxy-2-vCPU run reached
`COMPUTE_CHECK=PASS` but its wrapper failed to wait for the final marker; the
later `fixedwait` row is the formal sample.

### W3 reduction completion and shared 1080p glmark2 boundary

The v6 reduction result was completed with the same explicit
`dispatch_barrier_map` timing phase and 100 measured/10 warmup iterations on
both native and proxy paths:

| Kernel | Path | DRM node | Correctness | Avg iteration | Throughput | Relative time vs native mean | Run |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| `block_reduction_32mib_fp32` | native Panthor | renderD128 | PASS | 8076.82 us | 1.039 GOps/s | 1.00x | `native-panthor-ml-v6-rsa-formal-100it-20261014-121528` |
| `block_reduction_32mib_fp32` | native Panthor | card0 | PASS | 8109.75 us | 1.035 GOps/s | 1.00x | same run |
| `block_reduction_32mib_fp32` | proxy one-client | renderD128 | PASS | 20451.06 us | 0.410 GOps/s | 2.53x | `shared-ml-v6-reduction-formal-128c96p-20261014-201607` |

The native two-node mean is 8093.29 us.  The proxy client used the
Mali-G610/Panfrost renderer and passed `ML_CHECK`/`ML_RESULT`, but again
emitted 110 `MESA: error: export failed` messages (one per warmup/measured
dispatch).  Thus the timing is valid while the proxy frontend remains
non-native-equivalent.

The shared 1080p glmark2 run used null-noop with `--frame-end finish`, 512 MiB
client/proxy memory, and `/dev/dri/renderD128`:

```text
run: shared-glmark2-1080p-null-noop-finish-20261014-185651
payload qualification: Mali-G610/Panfrost, COMPUTE_CHECK=PASS, GLMARK_VERSION_RC=0
formal result: FAIL, no score
```

After starting `glmark2-es2-null-noop --validate --off-screen=1 --size
1920x1080`, the client emitted neither `GLMARK_VALIDATE` nor
`GLMARK_RESULT`/score before the runner's 900-second wait expired.  Unlike the
720p failures, this particular 1080p log has no `export failed`,
`BO_CREATE`/`VM_BIND` errno, or SIGSEGV.  The proxy's final recorded activity
is successful timeline-wait and BO teardown around guest time 27.74 s.  This is
therefore a shared-frontend hang/no-progress boundary, not a valid performance
sample or evidence of benchmark unavailability.

### NCNN build and native topology benchmarks

NCNN was downloaded and built on the RK3588 from source identified as tag
`20260526`, commit `e54f7b1f88434e1d844ea0551b880a1cfb079ce1`, with:

```text
CMAKE_BUILD_TYPE=Release
NCNN_VULKAN=ON
NCNN_BUILD_BENCHMARK=ON
NCNN_BUILD_TOOLS=OFF
NCNN_BUILD_EXAMPLES=OFF
NCNN_BUILD_TESTS=OFF
NCNN_PYTHON=OFF
```

The build produced `libncnn.a` and `benchncnn`; the Vulkan device probe reused
the actual link order from `benchmark/CMakeFiles/benchncnn.dir/link.txt`, rather
than guessing Vulkan/StaticSPIRV dependencies.  Payload runtime libraries
`libgomp.so.1`, `libm.so.6`, and `libmvec.so.1` were added to the injected
rootfs payload.

The native CPU run used 100 loops, two threads, `powersave=2`,
`gpu_device=-1`, and `cooling_down=0`.  The native PanVK run also used 100
loops and `gpu_device=0`, and first qualified exactly one discrete Vulkan
device: Mali-G610, driver `panvk`, Vulkan API `4198705`.

| Path | Model | Raw rc | Avg iteration | Evidence class | Run |
| --- | --- | ---: | ---: | --- | --- |
| native CPU | mobilenet_v2 | 0 | 40.86 ms | timing-valid topology benchmark | `native-ncnn-realmodels-cpu-formal-20261014-133939` |
| native CPU | mobilenet_v3 | 0 | 36.16 ms | timing-valid topology benchmark | same run |
| native CPU | resnet50 | 0 | 291.18 ms | timing-valid topology benchmark | same run |
| native PanVK | mobilenet_v2 | 0 | 24.44 ms | timing-valid topology benchmark | `native-ncnn-realmodels-panvk-direct-20261014-134235` |
| native PanVK | mobilenet_v3 | 0 | 23.05 ms | timing-valid topology benchmark | same run |
| native PanVK | resnet50 | 0 | 1270.18 ms | timing-valid topology benchmark | same run |

This is intentionally not called trained-model correctness testing: NCNN's
`DataReaderFromEmpty::read()` fills every model-weight byte with zero.  It is
an architecture/zero-weight execution benchmark.  The native result shows
PanVK faster than CPU for the two MobileNet topologies but much slower for
resnet50; that observation is topology-specific and must not be generalized.

The original PanVK wrapper summary incorrectly marked MobileNet v2/v3 as
`timing=none` because NCNN writes NUL bytes and the old `grep` treated the log
as binary.  Raw model logs have valid `min/max/avg` lines and rc 0.  The parser
now uses `grep -a`; `summary-corrected.log` records the correction without
altering raw logs.  All three rows in the table above are timing-valid passes.

### Shared NCNN: first meaningful frontend failure

The first two shared payload attempts failed on missing runtime libraries and
were fixed:

| Probe | Result | Boundary |
| --- | --- | --- |
| `shared-ncnn-realmodels-panvk-probe-20261014-214715` | payload qualification FAIL | missing `libgomp.so.1`; not a GPU result |
| `shared-ncnn-realmodels-panvk-probe2-20261014-214859` | payload qualification FAIL | missing `libmvec.so.1`; loader preflight then passed after adding `libm.so.6`/`libmvec.so.1` |
| `shared-ncnn-realmodels-panvk-probe3-20261014-215123` | authoritative shared frontend FAIL | first meaningful Vulkan runtime failure |

In probe 3, the client enumerated the expected Mali-G610/PanVK device, but
creation of NCNN's valid `VulkanDevice` failed while initializing its dummy
buffer/image workload:

```text
vkQueueSubmit failed -4
VulkanDevice create_dummy_buffer_image failed -1
NCNN_VK_PROBE_RESULT=FAIL reason=invalid-device
NCNN_BACKEND_QUALIFICATION=FAIL rc=2
NCNN_RESULT=FAIL reason=vulkan-device-qualification
```

Vulkan error `-4` is `VK_ERROR_DEVICE_LOST`.  The proxy log shows successful
session, BO, VM bind, group submit, sync-object wait/reset, and cleanup
activity around the probe, but no proxy-side errno directly explaining the
client-side device-lost result.  Repeating this configuration would only
reproduce the same qualification gate, so shared NCNN stopped at the first
meaningful error.  There is no valid shared NCNN timing and therefore no
native-versus-shared slowdown ratio for NCNN.

### ONNX Runtime trained-model CPU fallback

ONNX Runtime 1.21.0 exposed only
`DnnlExecutionProvider,XnnpackExecutionProvider,CPUExecutionProvider`; there
was no Panthor/PanVK/GLES GPU execution provider.  All rows below therefore
have `ACTUAL_BACKEND=CPU` and `EXECUTION_FALLBACK_FROM_GPU=YES`.

| Model | Loops/warmup/threads | Model bytes | Load time | Mean iteration | Output evidence | Run |
| --- | --- | ---: | ---: | ---: | --- | --- |
| mobilenetv2 | 100/10/2 | 13,964,571 | 472.577 ms | 621.759 ms | 1000 finite outputs, sum 0.137375584 | `native-onnxruntime-mobilenetv2-cpu-formal-20261014-2110` |
| mobilenet_v3_large | 100/10/2 | 21,922,120 | 285.333 ms | 288.634 ms | 1000 finite outputs, sum -0.018742808 | `native-onnxruntime-mobilenetv3-cpu-formal-20261014-134029` |
| resnet50-v2 | 30/5/2 | 102,442,452 | 624.296 ms | 1627.725 ms | 1000 finite outputs, sum 0.127615254 | `native-onnxruntime-resnet50-cpu-formal-20261014-134101` |

These are trained real-model executions, unlike NCNN's zero-weight benchmark,
but they are CPU fallback evidence only.  Finite logits prove numerical
execution, not classification accuracy, and do not provide a GPU-sharing
comparison.

### Checkpoint evidence classification

| Evidence | Classification |
| --- | --- |
| W1 4-128 MiB one-client compute rows | PASS or bounded capacity failure; valid for configuration comparison |
| Native glmark2 GBM/null-noop-finish rows | PASS; 800x600, 1280x720, and 1920x1080 native samples completed |
| Proxy glmark2 rows | frontend compatibility/resource-lifecycle failures; no valid score |
| Conv2d/depthwise, reduction, GEMM256/512, softmax native-versus-proxy rows | correctness/timing PASS where marked; per-kernel overhead varies from near-native to 2.53x |
| Proxy attention | correctness/readback FAIL; no valid timing or slowdown |
| Native NCNN CPU/PanVK | architecture-only, zero-weight topology timing; not trained-model correctness |
| Shared NCNN | frontend qualification FAIL at `VK_ERROR_DEVICE_LOST`; no timing |
| ONNX Runtime | trained real model, CPU fallback only; no GPU comparison |

The checkpoint must not be summarized as one average sharing overhead.  GL
compute, glmark2, synthetic kernels, NCNN topologies, and ONNX CPU fallback
exercise different frontend paths and have different validity boundaries.

### Completion artifact audit

After fetching the authoritative run logs, a 31-item artifact audit checked
that each objective run exists and contains its expected terminal evidence
(not necessarily a PASS marker):

```text
ARTIFACT_AUDIT_PASS=31 FAIL=0 TOTAL=31
```

The two initially ambiguous native conv/depthwise and softmax entries were
resolved by checking their concrete per-node log files (`renderD128_conv.log`,
`renderD128_depthwise.log`, and `test.log`) rather than nonexistent or
kernel-less aggregate files.  Bounded failures such as default-placement
128 MiB capacity exhaustion, shared glmark2, shared attention, and shared
NCNN count as completed evidence when their authoritative error/result markers
are present.

Final runtime check after fetching and documenting the artifacts:

```text
kernel=6.12.0-opencca-pmthor
root=/dev/mmcblk1p4
driver=pmthor
pmthor_node=yes
online_cpus=0-1
firecracker_count=0
vmshm_broker_count=0
```

## 2026-10-15: NUL-safe parsing, 100-iteration ML suite, and NCNN failure isolation

The shared payload parsers were repaired after observing that glmark2 and NCNN
write NUL bytes into otherwise textual stdout/stderr.  The authoritative logs
are now normalized with `tr -d '\000'` before renderer/score/timing parsing in
`GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh`.  This fixes false `none`
scores/timings only; it does not suppress a real Vulkan, Panthor, or EGL error.

### Formal one-client ML kernels

All native rows use `/dev/dri/renderD128`, 100 samples, and the Panfrost
renderer.  The shared rows use one proxy and one client, client=128 MiB,
proxy=96 MiB, and the submit-6 scheduler configuration.  The first three
shared kernels came from one suite whose per-kernel correctness/timing markers
are valid, although the suite wrapper ended with `ML_RESULT=FAIL rc=99`;
reduction, softmax, and attention were then repeated as independent PASS runs.

| Kernel | Native GOps/s | Shared GOps/s | Native/shared | Shared evidence |
| --- | ---: | ---: | ---: | --- |
| `gemm_512_fp32` | 12.986 | 3.654 | 3.55x | per-kernel PASS; suite rc=99 |
| `conv2d_64x64x32_3x3_fp32` | 3.121 | 0.835 | 3.74x | per-kernel PASS; suite rc=99 |
| `depthwise_conv_128x128x128_3x3_fp32` | 2.008 | 0.639 | 3.14x | per-kernel PASS; suite rc=99 |
| `block_reduction_32mib_fp32` | 1.039 | 0.251 | 4.14x | independent run PASS |
| `row_softmax_16384x256_fp32` | 1.409 | 0.400 | 3.52x | independent run PASS |
| `single_head_attention_256x64_fp32` | 0.0313 | 0.0109 | 2.88x | independent run PASS |

Representative runs:

```text
native-panthor-ml-gemm512-v5-100it-20261014-114743
native-panthor-ml-conv-depthwise-repeat3-100it-20261014-180343
native-panthor-ml-v6-rsa-formal-100it-20261014-121528
native-panthor-ml-v7-softmax-formal-100it-20261014-122823
native-panthor-ml-v7-attention-formal-100it-20261014-123038
shared-ml-submit6-suite-r2-100it-gemm512-128c96p-20261015-003155
shared-ml-submit6-reduction-100it-128c96p-20261015-003249
shared-ml-submit6-softmax-100it-128c96p-20261015-003313
shared-ml-submit6-attention-100it-128c96p-20261015-003345
```

The ratios describe this harness/configuration pair, not a universal sharing
overhead.  Nevertheless, all six shared kernels passed correctness and landed
at roughly native/2.9 through native/4.1 throughput.

### NCNN 100-loop PanVK diagnostics

The shared client qualified the real Mali-G610 device and `panvk` driver in
every run, but the model benchmark itself is not a formal PASS:

| Model | Qualification | Raw avg | Authoritative error | Result class |
| --- | --- | ---: | --- | --- |
| mobilenet_v2 | Mali-G610/panvk PASS | 19.92 ms | `vkWaitForFences failed -4` | diagnostic timing only |
| mobilenet_v3 | Mali-G610/panvk PASS | 19.18 ms | `vkWaitForFences failed -4`; one `VM_BIND` err=110 | diagnostic timing only |
| resnet50 | Mali-G610/panvk PASS | 19.53 ms | 110 `BO_CREATE` err=12 plus `vkWaitForFences failed -4` | timing invalid |

The resnet50 timing cannot be compared with the native 1270.18 ms result: its
19.53 ms average is associated with repeated resource-allocation failure and
therefore likely measures a failed/degenerate graph rather than full execution.
The mobile-net timings are useful diagnostics but remain FAIL because device
loss was observed during synchronization.

For comparison, shared NCNN CPU fallback completed 100 loops with mobilenet_v2
43.08 ms, mobilenet_v3 37.86 ms, and (after raising the client to 256 MiB)
resnet50 284.38 ms.  These are CPU rows and are not GPU-sharing performance.

### Raw Vulkan fence/semaphore isolation

The raw Vulkan probe narrows the NCNN failure boundary:

```text
device creation, buffer/image creation, command recording: PASS
empty/barrier command submit without a fence:             PASS
empty command submit with a fence:                        VK_ERROR_DEVICE_LOST
barrier command submit with a fence:                      VK_ERROR_DEVICE_LOST
empty command submit with a semaphore:                    VK_ERROR_DEVICE_LOST
full case after the submit-6 scheduler update:             PASS in one later run
```

This result must not be flattened into a permanent pass/fail statement.  It
shows that the shared frontend can create a PanVK device and forward ordinary
submits, while signal-carrying submissions are the important fragile boundary;
later scheduler state allowed one full case to pass.  NCNN and glmark2 exercise
that same boundary much more heavily and can still fail or hang.

### Current glmark2 and host-state boundary

The parser-fixed shared null-noop `frame-end=none` retest did not produce a
score.  The first attempt was stopped by the host memory guard, and the second
hung while repeatedly logging `DRM_IOCTL_PANTHOR_BO_CREATE failed (err=12)`;
it was manually terminated and classified FAIL.  The previous finish run did
print a raw score of 53, but also had `VM_BIND` err=17, `GL_OUT_OF_MEMORY`, and
failed shadow/refract setup, so 53 is diagnostic only.

After cleanup there was no `firecracker` or `vmshm-broker` residue, but host
`MemAvailable` remained near 0.5 GiB.  Do not attribute that state to a specific
leak without a clean-reboot baseline and allocation audit.  Until then, treat
it as a run-blocking resource-pressure observation.

## 2026-10-15: raw Vulkan probe correction and continued NCNN isolation

The earlier raw-Vulkan SIGSEGV investigation found two defects in the probe
harness rather than in the vmshm RPC path:

1. `decode_spirv_words()` decoded each four-byte SPIR-V group with the wrong
   byte order.  The byte stream starts with `03 02 23 07`, whose little-endian
   word is `0x07230203`; the old code constructed `0x03022307` and therefore
   fed Mesa an invalid SPIR-V magic number.
2. The minimal-shader path decoded the global full-shader constant instead of
   its own `hex` argument, so `compute-storage-min` was not running the intended
   minimal module.

The function now decodes two hexadecimal characters as one byte, assembles each
word little-endian, uses its argument, and rejects a non-`0x07230203` first
word.  The corrected AArch64 binary is
`GPU-SFTP/tests/vulkan-bench/bin/raw-vk-probe`, SHA-256
`66bcf0e7d90e282f3f6b9f4ab10d108779c600f1ca97896c76c5107b3f53c240`.

### Corrected native PanVK probe

Run: `native-panthor-raw-vk-compute-fixed-r2-20261015-035613`

The PanVK userspace is
`GPU-SFTP/artifacts/ncnn-arm64/rootfs-ncnn-libs/libvulkan_panfrost.so`, SHA-256
`8c84721328137cfb57153d507f57fe07293e689270a8abadf7f1984491bb6523`.

| Case | Result | Boundary |
| --- | --- | --- |
| `compute-storage` | PASS | shader, compute pipeline, dispatch, fence wait, and output check all succeeded |
| `full` | PASS | empty command submission with signal-carrying synchronization succeeded |
| `compute-storage-min` | FAIL | shader module creation succeeded, then compute-pipeline creation returned `-13` |
| `compute-storage-cache` | FAIL | same native `-13` boundary with an explicit pipeline cache |

The important correction is that the prior SIGSEGV disappeared.  It was
triggered by the probe's invalid SPIR-V input; Mesa's behavior while logging
that invalid input is a separate robustness issue.  The minimal/cache `-13`
result also reproduces on native PanVK, so it is not evidence of a shared-only
regression.

### Corrected shared one-client probe

Run: `shared-raw-vk-fixed-compute-full-1q-128c96p-20261015-035655`

Configuration: one queue, sequential submit, client=128 MiB, proxy=96 MiB,
and guest render node `/dev/dri/renderD128`.

| Case | Result | Authoritative marker |
| --- | --- | --- |
| `compute-storage` | PASS | `RAW_VK_CREATE_COMPUTE_PIPELINE=0`; `RAW_VK_COMPUTE_CHECK=PASS` |
| `full` | PASS | `RAW_VK_CASE_RESULT=PASS` |

The run summary records `RAW_VK_SUITE_RESULT=PASS cases=2`,
`GPU_SMOKE_RESULT=PASS`, and `RESULT: PASS`.  This establishes that the
corrected bounds-checked compute pipeline and the signal-carrying submit path
can work through the current one-client vmshm/panthor-proxy path.  It does not
claim that every NCNN graph or glmark2 scene is fixed.

### NCNN memory diagnostic after the probe correction

Run:
`shared-ncnn-fixed-rawvk-mobilenet_v2-1loop-192c96p-20261015-035855`

Raising the client from 128 MiB to 192 MiB did not clear the NCNN model error.
Device qualification still passed with exactly one Mali-G610/panvk Vulkan
device, but `benchncnn` reported `vkWaitForFences failed -4`, repeated
subsequent submits with `-4`, and printed a diagnostic 18.96 ms timing.
`NCNN_MODEL_RESULT=FAIL`, `NCNN_RESULT=FAIL`, and `RESULT: FAIL` remain the
authoritative classification.  This narrows the remaining issue toward NCNN's
heavier graph/resource/synchronization behavior rather than simple client-VM
memory capacity or the now-passing basic raw compute/fence path.

### glmark2 artifact audit and test priority

No glmark2 download was needed: ARM64 payloads already exist under
`GPU-SFTP/artifacts/glmark2-arm64/`, including `rootfs-gbm`,
`rootfs-gbm-render-only`, `rootfs-gbm-render-only-debug`, `rootfs-null`, and
`rootfs-null-noop`.  Native GBM/null-noop runs already have PASS evidence.
Current shared glmark2 output remains diagnostic-only because it contains
resource-lifecycle or EGL/GBM failures even when a partial score is printed.

Do not block raw-Vulkan, ML-kernel, or NCNN diagnostics on first obtaining a
formal shared glmark2 score.  Use glmark2 as a separate frontend stress track.

Final state after the corrected shared run and NCNN diagnostic:

```text
kernel=6.12.0-opencca-pmthor
driver=pmthor
pmthor_node=yes
firecracker_count=0
vmshm_broker_count=0
MemAvailable=1269172 kB
```

## 2026-10-15: Continue past glmark2 and isolate NCNN/raw-compute nondeterminism

The ARM64 glmark2 payloads were already local, so no download was needed:

```text
GPU-SFTP/artifacts/glmark2-arm64/
  rootfs-gbm
  rootfs-gbm-render-only
  rootfs-gbm-render-only-debug
  rootfs-null
  rootfs-null-noop
```

Shared glmark2 remains a separate frontend/resource-lifecycle stress track.
Raw Vulkan and NCNN diagnostics were continued with `--skip-sync`, one fresh
proxy/client session per run, client=192 MiB, proxy=96 MiB, and one vCPU per
guest.  No flashing, reboot, or eMMC access occurred.

### Native/shared NCNN prefix8 control

The same `mobilenet_v2_prefix8_out96` graph passed on native PanVK in
`GPU-SFTP/log/native/native-ncnn-prefix8-out96-panvk-r1-20261014-215154`:

```text
DRIVER_BEFORE=pmthor
DRIVER_TEST=panthor
NCNN_VK_PROBE_RESULT=PASS
NCNN_BACKEND_QUALIFICATION=PASS
NCNN_MODEL_RESULT=PASS
NATIVE_OUT96_RC=0
avg=14.27 ms
```

The client qualified Mali-G610 through the shared path, but the cached-WB
variant of the same model failed in
`GPU-SFTP/log/shared/vmshm-1client/shared-ncnn-prefix8-out96-cached-1loop-192c96p-r1-20261015-054057`.
The first meaningful GPU event was a read translation fault at VA `0x8` after
a six-job `GROUP_SUBMIT`; `vkWaitForFences failed -4` followed it.  Therefore
the model file and direct PanVK userspace are not the primary boundary.  The
fault is in the shared client/proxy execution path.

### Prefix8 output/shape reduction is timing-dominated

Each first-pass variant used one model, one loop, one thread, and one fresh VM:

| Variant | First-pass result | Repeat evidence | Interpretation |
| --- | ---: | ---: | --- |
| `prefix8_out16` | FAIL | FAIL/PASS/FAIL | Intermittent; output-buffer size is not a stable boundary |
| `prefix8_out32` | FAIL | one sample | FAIL |
| `prefix8_out48` | PASS | PASS/FAIL/FAIL | Same graph can pass and fail |
| `prefix8_s28` | FAIL | one sample | FAIL |
| `prefix8_in48` | PASS | one sample | PASS |
| `prefix8_k3` | FAIL | one sample | FAIL |

The failure mode also changes between independent sessions:

```text
prefix8_out16 r1: job-timeout, no page fault
prefix8_out16 r3: cs-fatal, no page fault
prefix8_k3:       WRITE TRANSLATION_FAULT_1 at VA 0x04980000, then cs-fault
```

Consequently, a single NCNN pass/fail must not be interpreted as a stable
graph-size threshold.  Prefix8-class execution is nondeterministic through the
current shared path, with submit/fence completion, ring progress, and GPU VA
validity all capable of becoming the first visible failure.

### Corrected raw-compute repeats

The corrected `compute-storage` case passed three consecutive independent solo
runs:

```text
shared-raw-vk-fixed-compute-solo-r1-1q-192c96p-20261015-055815 PASS
shared-raw-vk-fixed-compute-solo-r2-1q-192c96p-20261015-055831 PASS
shared-raw-vk-fixed-compute-solo-r3-1q-192c96p-20261015-055847 PASS
```

The five-case sequential matrix also passed 5/5 in
`shared-raw-vk-fixed-sequential-5case-1q-192c96p-20261015-060207`, and a second
concurrent-labeled matrix passed 5/5 in
`shared-raw-vk-fixed-concurrent-5case-r2-1q-192c96p-20261015-060227`.
The earlier
`shared-raw-vk-fixed-concurrent-1q2q3q-matrix-192c96p-20261015-055405` had
failed only `compute-storage` after an AS1 read fault at VA `0x20`, while the
other four cases passed.  Since `run_compute_storage_case()` does not consume
the submit-mode argument and the same case now passes solo, sequentially, and
in a repeated matrix, that event is classified as a nondeterministic shared-path
failure rather than proof that concurrent submit mode is the root cause.

Current working boundary: corrected raw shader creation, dispatch, storage
output, and signal-carrying submission work repeatedly in one-client sessions,
but low-probability GPU faults remain.  NCNN prefix8-class graphs exercise the
fragile region much more reliably.  The next source-level audit should compare
the first failed NCNN submit with its immediately preceding `VM_BIND`,
`BO_DESTROY`, sync-object reset/transfer, and ring-buffer lifetime operations,
rather than treating the later `vkWaitForFences -4` or expanded
`fatal_queues` mask as the cause.

## 2026-10-15: Do not block on glmark2; complete individual ML kernels

The ARM64 glmark2 payloads were already present under
`GPU-SFTP/artifacts/glmark2-arm64/`, including stock GBM, upstream null,
null-noop, GBM render-only, render-only-debug, and their build metadata.  No
download was required.  glmark2 remains a separate frontend/resource-lifecycle
track; it must not gate the ML and raw-Vulkan matrix.

The second low-memory conv attempt passed after one non-destructive host cache
drop:

```text
run:     shared-ml-postsync-conv-solo-100it-128c96p-manual550-20261015-064150
result:  ML_CHECK=PASS; ML_RESULT=PASS; GPU_SMOKE_RESULT=PASS; RESULT: PASS
kernel:  conv2d_64x64x32_3x3_fp32
avg:     92726.80 us
throughput: 0.814 GOps/s
```

The first attempt
`shared-ml-postsync-conv-solo-100it-128c96p-manual550-20261015-064123` had been
rejected only by the preflight guard at 548/550 MiB, not by a GPU fault.

Host `MemAvailable` then remained near the guard and fell after each completed
session even though no Firecracker or broker process survived.  To avoid
stalling the matrix, the final two kernels were run as explicitly diagnostic
one-client samples at 128 MiB client / 96 MiB proxy and one vCPU per VM:

| Kernel | Run | Guard | Preflight | Result | Avg / throughput |
| --- | --- | ---: | ---: | --- | ---: |
| `depthwise_conv_128x128x128_3x3_fp32` | `shared-ml-postsync-depthwise-solo-100it-128c96p-diag530-20261015-064512` | 530 MiB | 533 MiB | PASS | 61817.15 us / 0.611 GOps/s |
| `block_reduction_32mib_fp32` | `shared-ml-postsync-reduction-solo-100it-128c96p-diag500-20261015-064605` | 500 MiB | 505 MiB | PASS | 36273.75 us / 0.231 GOps/s |

Both used `/dev/dri/renderD128`, reported Mali-G610 through Panfrost, printed
`ML_CHECK=PASS samples=100 warmup=10`, and ended with `RESULT: PASS`.  Neither
sample had an OOM kill, `CS_FAULT`, `CS_FATAL`, or a job timeout.  Because the
guards were lowered only to bypass a small host-memory accounting/reclamation
boundary, these two rows are diagnostic rather than formal qualification rows.

Together with the prior low-memory softmax, attention, and gemm samples, all
six individual ML kernels now have 100-iteration authoritative shared-path
passes:

| Kernel | Low-memory shared result |
| --- | --- |
| `gemm_512_fp32` | PASS |
| `conv2d_64x64x32_3x3_fp32` | PASS |
| `depthwise_conv_128x128x128_3x3_fp32` | PASS |
| `block_reduction_32mib_fp32` | PASS |
| `row_softmax_16384x256_fp32` | PASS |
| `single_head_attention_256x64_fp32` | PASS |

The six-kernel all-run remains a distinct allocation/lifecycle boundary: it
passed its first five kernels at 192/96 MiB but failed softmax allocation with
`DRM_IOCTL_PANTHOR_VM_BIND err=17` and `GL_OUT_OF_MEMORY`; lower-memory or
higher-guard all-run attempts were preflight guard rejections, not GPU
failures.

Memory observations around these runs were:

```text
before conv retry after drop_caches: about 556 MiB
conv retry preflight:                  554 MiB
after conv:                            about 531 MiB
depthwise preflight:                   533 MiB (manual 530 diagnostic)
after depthwise:                       about 493 MiB
after reclaim:                         about 510 MiB
reduction preflight:                   505 MiB (manual 500 diagnostic)
after reduction:                       about 453 MiB
```

No `firecracker` or `vmshm-broker` process remained after the drops.
`drop_caches` and cgroup `memory.reclaim` recovered only part of the memory.
This points to a host-side lifecycle/accounting leak or pinned-page retention
across repeated shared sessions, and is now a first-class test issue.  A
controlled reboot/recovery experiment is the obvious next isolation step, but
it was not performed because the current test boundary explicitly avoids
rebooting or flashing.

## 2026-10-15: VM_BIND lifecycle evidence and diagnostic guest kernels

The glmark2 dependency was not missing, so no download or rebuild was needed:
`GPU-SFTP/artifacts/glmark2-arm64/` already contains ARM64 GBM, DRM-derived
GBM, null, null-noop, render-only, and render-only-debug payloads.  The
upstream build marker is commit `22c527cb0556f3a1ac4445aaa52cc532760928d5`.
Those payloads remain a separate frontend/resource-lifecycle track and must not
gate ML, raw-Vulkan, NCNN, or kernel lifecycle debugging.

### Host memory state after the shared matrix

The RK3588 host remained on the required runtime baseline:

```text
kernel: 6.12.0-opencca-pmthor
driver: pmthor
firecracker processes: 0
vmshm-broker processes: 0
MemTotal:             3386876 kB
MemAvailable:          468604 kB
user.slice memory:    3050504192 bytes
```

The direct `user.slice/cgroup.procs` list was empty and no populated descendant
explained the charge.  `memory.events` still reported no OOM.  The anomalous
numbers were instead:

```text
anon:                  about 10 MiB
active_anon:           about 2.21 GiB
inactive_anon:         about 438 MiB
file:                  about 193 MiB
nr_dying_descendants:       122
nr_dying_subsys_memory:     122
```

A read-only `/proc/kpageflags` plus `/proc/kpagecgroup` scan over the System RAM
PFN ranges found 173,601 `KPF_ANON | KPF_ACTIVE` pages charged directly to the
`user.slice` cgroup inode, while only trivial counts belonged to live service
or session cgroups.  Together with zero entries in the live DRM
`gem_names` debugfs file and no visible VM processes, this strengthens the
orphaned/dying-cgroup or still-pinned unmapped-page hypothesis.  The scan does
not identify the allocating stack (host `CONFIG_PAGE_OWNER` is disabled) and
does not by itself distinguish a vmshm payload pin from another long-lived page
reference.  A controlled recovery/reboot baseline remains necessary to close
that boundary; it was not attempted here.

### VM_BIND and BO lifetime source boundary

The relevant static path is:

```text
panthor-proxy VM_BIND translation
  -> panthor_vmshm_vm_bind_async()
  -> panthor_vm_bind_job_create()
  -> panthor_vm_bind_prepare_op_ctx()
  -> panthor_vm_prepare_map_op_ctx()
  -> drm_gpuvm_bo_create/obtain()
```

`panthor_vmshm_group_submit()` also prepares mapped-BO reservations, and the
map-job context retains `vm_bo`/GEM references until scheduler cleanup.  This
weakens both the earlier "submit never references stream BOs" and "BO_DESTROY
immediately causes payload/GEM UAF" hypotheses.  Async map/unmap ordering,
pending fences, sync-object reset/transfer, and BO destruction around queued
jobs remain the candidate timing races.

Three NCNN runs showed `client BO_MMAP=82` but `proxy BO_MMAP=0`, and the RPC
table has no forwarded BO-mmap operation.  The client maps its vmshm payload
GPA locally; proxy userspace does not CPU-map the real Panthor GEM.  Therefore
"proxy userspace CPU mmap creates double backing" is not currently supported as
the primary NCNN PASS/FAIL explanation.  The corrected r8 fatal information is
`fatal_info=0xfffadae0`; the first meaningful cached-WB exception was
`CS_RES_TERM (0xf)` rather than the later queue fatal.

### Diagnostic-only VM_BIND trace build

`Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c` now emits a
bounded `VM_BIND_TRACE` series for the first 2,048 calls.  Each request logs:

- session/client VM/proxy VM, async mode, request flags, result, and failed op;
- per-op type, flags, client and translated proxy BO handles, BO offset, GPUVA,
  size, and sync window;
- per-sync flags, client and translated proxy sync-object handles, and timeline
  value.

This is diagnostic-only logging; it changes no VM_BIND semantics and must not be
used as a formal performance kernel.  Both shared guest kernels rebuilt
successfully:

```text
client: GPU-SFTP/firecracker-bins/kernels/shared/client/Image
sha256: 54236417591461bb40fc2089bbcc581fe61ed7aa78d8e1d899f2c99033e0b135

proxy:  GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
sha256: 818ade7149edeee8ea46a5fa81d665a388dba7252a82fbce0244c8f99a880652
```

The proxy image contains the new `VM_BIND_TRACE` format strings.  The artifacts
were intentionally not synced to the RK3588 and no VM was launched, because the
host still has only about 469 MiB available and the active boundary forbids
reboot/flash/eMMC operations.

## 2026-10-15: NCNN first-fault timeline and Mesa export-path boundaries

The glmark2 dependency did not block the rest of the matrix: the local payload
inventory contains ARM64 GBM, DRM-derived GBM, upstream null, null-noop,
render-only, and render-only-debug trees.  More importantly, the non-glmark
tracks completed independently:

| Track | Current evidence |
| --- | --- |
| Six individual ML kernels | Each has a 100-iteration authoritative shared-path PASS (two rows are diagnostic because their low-memory guards were manually relaxed). |
| Raw PanVK compute | Sequential five-case, concurrent five-case, and 12-case fixed matrices all ended with `RAW_VK_RESULT=PASS`, `GPU_SMOKE_RESULT=PASS`, and `RESULT: PASS`. |
| NCNN MobileNet prefix | `mobilenet_v2_prefix8_out16` still fails; this is the active lifecycle fault, not a missing workload payload. |

### NCNN first meaningful fault

For
`shared-ncnn-prefix8-out16-cached-r1-1loop-192c96p-manual600-20261015-063145`,
the first meaningful GPU exception is not userspace's later `vkWaitForFences
-4`.  The proxy order is:

1. `GROUP_SUBMIT_TRACE seq=13` completes with `ret=0`, followed by successful
   sync transfer/reset and `GROUP_GET_STATE state=0x0 fatal_queues=0x0`.
2. Transient BO handles 10, 11, and 12 are destroyed, sync object 3 is
   recreated, and the client maps a new allocation generation (including the
   16 MiB staging payload logged as client BO 11).
3. `GROUP_SUBMIT_TRACE seq=14` submits stream sizes `856/856/7744` at GPU VAs
   `0xfffcc000/0xfffbc000/0xfffac000`.
4. Queues 0 and 1 first report `CS_RES_TERM (0xf)` with exception data
   `0x900`; queue 2 then reports `DATA_INVALID_FAULT (0x58)`.
5. A following submission reaches `CS_INSTR_INVALID (0x49)` and
   `GROUP_GET_STATE state=0x2 fatal_queues=0x4`; the later
   `vkWaitForFences -4` is a consequence, not the first fault.

This narrows the boundary to allocations/mappings and queued command-stream
lifetime between two successful NCNN submit generations.  It does **not** yet
prove a BO use-after-free: the production run's `BO_CREATE` and `VM_BIND`
messages use `pr_info_ratelimited()`, so almost all session-3 BO/mapping events
for the reproducer were suppressed.  In particular, the proxy log cannot answer
whether the seq-14 stream VAs still had live, correctly translated mappings
when the hardware consumed them.

The diagnostic proxy kernel built in the preceding section addresses that
observability gap with bounded, non-rate-limited `VM_BIND_TRACE` records and
per-job `GROUP_SUBMIT_TRACE` records.  It remains un-deployed because the host
still reports only about 467 MiB `MemAvailable`, roughly 3.06 GiB
`user.slice/memory.current`, and 130 dying descendants with zero surviving
Firecracker/broker processes.  Launching another VM now would conflate NCNN
lifecycle behavior with an unrelated low-memory condition.

### Mesa sync/export error paths

Mesa 25.0.7 source separates the two historically conflated messages:

- `MESA: error: export failed` comes from
  `pan_fence.c` when `drmSyncobjExportSyncFile()` cannot export a Panfrost
  context syncobj to a sync-file FD.
- `DMA_BUF_IOCTL_EXPORT_SYNC_FILE failed (err=...)` can come from the Panthor
  kmod shared-BO wait path in `panthor_kmod.c`, or from WSI direct dma-buf
  export in `wsi_common_drm.c`.
- In `panthor_kmod.c`, the same user-visible string is also emitted after a
  later `sync_wait()` timeout; `err=-110` therefore does not by itself identify
  whether the export ioctl or the following wait timed out.

The old attention run had one of each Mesa error followed by all-zero readback
and `ML_RESULT=FAIL`.  The recheck and postsync runs instead show repeated
successful client-side `SYNCOBJ_EXPORT_SYNC_FILE` / `IMPORTDIAG` activity (141
and 146 export records in their client logs, respectively) and end with
`ML_CHECK=PASS` over 100 samples.  Attention is therefore a historical
shared-sync failure that current runs pass; the old run must not be quoted as
the present attention status.

## 2026-10-15: Bounded glmark2 scene ladder and host-starvation boundary

glmark2 was not a missing dependency at this point.  The ARM64 payload tree
already contained GBM, render-only, render-only-debug, null, and null-noop
install roots, and the diagnostic binary was:

```text
GPU-SFTP/artifacts/glmark2-arm64/rootfs-null-noop/usr/bin/glmark2-es2-null-noop
sha256=2251afb6b792c08181e14205756a29c13f8dd15d5a3eb8ab6652efe55a65bb2c
```

The bounded scene ladder therefore proceeded without downloading or rebuilding
the benchmark.  All rows below are low-memory diagnostics, not formal
performance qualification.

| Scene/configuration | Result | Classification |
| --- | --- | --- |
| `build:duration=2:use-vbo=false`, 320x240, null-noop, client/proxy 192/96 MiB | score 82, `GLMARK_RESULT=PASS` | workload PASS, shared-path clean FAIL: one real `DRM_IOCTL_PANTHOR_VM_BIND failed (err=110)` |
| `clear:duration=2`, proxy 64 MiB | no renderer qualification | configuration floor: proxy guest kernel could not load its PE kernel image |
| `clear:duration=2`, 320x240, null-noop, client/proxy 128/96 MiB, object window 128 MiB | score 416054, `GLMARK_RESULT=PASS` | post-hoc shared-path clean PASS: zero `BO_CREATE`/`VM_BIND` errors; the sole incomplete-framebuffer `glClear` message is expected for null-noop without a color attachment |
| `buffer:duration=2`, same 128/96 MiB limits | no local guest result captured | RK3588 remained ICMP-reachable and accepted TCP port 22, but repeated SSH sessions timed out during banner exchange; classify as host userspace/memory starvation, not evidence that the scene itself passed or failed |

The historical top-level `RESULT: FAIL` on the clear run mixed two runner
problems: it predated the expected-null-noop framebuffer classification, and
guest CRLF output defeated an anchor that required an end-of-line after
`GLMARK_SCORE`/`GLMARK_RENDERER`.  The guest wrapper now reports separate
`GLMARK_RESULT` and `GLMARK_CLEAN_RESULT` markers, treats only unexpected
framebuffer messages as clean failures, and the top-level runner accepts the
prefix without the line-ending suffix and requires `GLMARK_CLEAN_RESULT=PASS`.

During the buffer attempt, a 30-second read from the RK3588 serial console
produced no bytes.  The Magic SysRq memory request was disabled by policy.  The
local runner was interrupted after its expected guest wait window and did not
launch another workload.  No reboot, power-cycle, SD flash, or eMMC operation
was performed.  Continuing the scene ladder requires a controlled host recovery
first; after that, rerun the 96 MiB clear configuration once to validate the new
markers natively, then use the reduced buffer selector:

```text
buffer:duration=1:update-fraction=0.1:update-dispersion=0.5:columns=8:update-method=subdata:interleave=false
```

## 2026-10-15: Stable control addresses and client RPC timeout mitigation

### Control-network state

The fixed control addresses were re-verified while no VM was running:

| Device | Interface/address | Persistent mode |
| --- | --- | --- |
| Raspberry Pi preferred | `eth0` `192.168.31.189/24` | NetworkManager manual, metric 100 |
| Raspberry Pi fallback | `wlan0` `192.168.31.52/24` | NetworkManager manual, metric 600 |
| RK3588 | `enP4p65s0` `192.168.31.18/24` | systemd-networkd static |

The discovery scan identified the expected Pi at `.189`, the same Pi's fallback
address at `.52`, and the RK3588 at `.18`.  This reduces but does not eliminate
address risk: the router should still reserve or exclude all three addresses
from its DHCP pool.  Discovery remains the fallback for an unexpected conflict,
not the normal path.

### Why `err=110` is not necessarily a proxy-side BO allocation failure

Static source inspection of
`Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c` showed
that every client RPC used a fixed one-second response deadline: the interrupt
path waited for `CLIENT_COMM_VMSHM_RPC_TIMEOUT_MS`, and the polling path made
1,000 approximately 1--2 ms attempts.  Both converted a late response into
`-ETIMEDOUT` (`errno 110`).

Consequently, the historical glmark2 message
`DRM_IOCTL_PANTHOR_BO_CREATE failed (err=110)` proves that the client stopped
waiting after one second; it does not by itself prove that the proxy's real
Panthor `BO_CREATE` failed.  This is consistent with the observed client D-state
under host memory starvation and with proxy-side successful BO/mapping traffic.

### Minimal timeout/observability change

The diagnostic guest kernels now make that deadline explicit and bounded:

```text
default: 10000 ms
minimum: 100 ms
maximum: 60000 ms
parameter: client_comm_vmshm.rpc_timeout_ms
```

Both the interrupt and polling paths consume the same configured deadline.  A
timeout now prints the request operation/type, sequence, and configured
deadline.  An unexpected late response is also logged with response type,
`reply_to`, status, and length rather than remaining `pr_debug()`-only.

`panthor_proxy_handle_bo_create()` now records the request sequence in success,
slow, failure, and response-send-failure paths.  BO_CREATE handlers slower than
100 ms emit a `BO_CREATE slow` record with duration.  This should distinguish
the next failure as one of:

1. proxy real-BO allocation failure;
2. response-send failure;
3. late response dropped by the client;
4. a genuine client-side timeout while the proxy eventually succeeds.

This patch deliberately does not change handle translation, BO lifetime,
VM_BIND ordering, or the global client RPC serialization.  Those larger design
changes remain gated on runtime evidence.

### Build and deployment evidence

Both guest kernels rebuilt successfully and were manually copied to the RK3588
runtime artifact directories:

```text
client sha256:
4683788c825d12e7e4f196c09fcd89e377d10b91b3fe8f0b89bbc12b5c529d8d

proxy sha256:
0d0ba2f408d54115e4f3e5213ca9434aab0b43d0f9379dc3ab4213c534a228fd
```

The previous remote images were preserved under
`GPU-SFTP/firecracker-bins/kernels/shared/archive/` with timestamp
`20261015-005638`.  The remote hashes now match the rebuilt local artifacts.
The host remained on `6.12.0-opencca-pmthor` with `/dev/pmthor`, SD root
`/dev/mmcblk1p4`, and no surviving Firecracker or broker process.  No SD or
eMMC flash was performed.

### Testing boundary

The timeout patch is currently source/build/deployment evidence, not a runtime
fix claim.  Immediately before deployment the RK3588 still reported only about
75 MiB `MemAvailable`, about 3.05 GiB charged to `user.slice`, and 115 dying
memory-cgroup descendants.  Launching glmark2 or an ML VM in that state would
conflate the RPC change with host starvation and folio/swap waits.

The next clean-host regression, after an explicitly authorized controlled
reboot and host-state verification, should run one workload at a time:

1. reduced buffer glmark2 scene;
2. build glmark2 scene;
3. short attention ML regression.

Pass requires `GLMARK_CLEAN_RESULT=PASS` with zero BO_CREATE, VM_BIND, and
unexpected framebuffer errors, plus `ML_CHECK=PASS`.  If an `err=110` remains,
correlate the new client timeout sequence with the proxy BO_CREATE sequence and
duration before changing object lifetime.

## 2026-10-15: Sync-file cleanup fixes and failure-stage diagnostics

### Runtime evidence after the timeout deployment

The following logs were inspected locally. These are reduced-workload
diagnostics under host memory pressure, not qualification of the full matrix:

| Run suffix under `GPU-SFTP/log/shared/vmshm-1client/` | Evidence | Boundary |
| --- | --- | --- |
| `shared-glmark2-newkernel-buffer-d1-reduced-nullnoop-320x240-128c96p-swapdiag-countfix-20261015-084351` | `GLMARK_CLEAN_RESULT=PASS`, `RESULT: PASS`; no counted BO creation, export, or VM bind errors | Reduced buffer scene only |
| `shared-ml-newkernel-attention-100it-128c96p-swapdiag-r2-20261015-083554` | `ML_CHECK=PASS samples=100 warmup=1`, `RESULT: PASS` | Attention regression only; does not prove larger configurations |
| `shared-glmark2-newkernel-build-d2-novbo-nullnoop-320x240-128c96p-swapdiag-countfix-20261015-084512` | Score 40, `GLMARK_RESULT=PASS`, but `GLMARK_CLEAN_RESULT=FAIL` and `RESULT: FAIL` | One `BO_CREATE err=110` remains |

The preceding statement that historical `err=110` *proves* an outer client
response timeout was too strong. BO_CREATE also calls
`client_vmshm_manager_get()` after the Panthor RPC succeeds, and can propagate
errors from either RPC or a proxy return value. The build log lacks the new
timeout and sequence-bearing proxy records. A local image hash matching a
remote artifact does not establish which image an earlier guest actually booted.
The neighboring client BO events are about 1.37 seconds apart, which also
requires checking the running guest before attributing this to a ten-second
deadline. No definitive timeout origin is claimed.

### Definite source fixes in sync-file export

In `panthor_client_syncobj_export_sync_file()`:

- If allocation of `sync_fence` fails, `out_put_fd` previously fell through
  into `dma_fence_put(&sync_fence->base)` with a null pointer. Cleanup now
  jumps directly to releasing the syncobj reference after releasing the FD.
- If queueing work or creating the sync_file fails, the reserved FD must
  also be released. Both failure paths now call `put_unused_fd()`.

These are verified source defects and both guest kernels build successfully.
They are **not** yet a demonstrated cause of the historical Mesa SIGSEGV,
all-zero readback, or NCNN device loss. No allocation-failure runtime injection
has been performed.

BO_CREATE failure records now distinguish argument validation, RPC transport,
proxy response status, response validation, local allocation, requester VMID,
manager lookup, descriptor validation, and xarray insertion. Manager GET_OBJECT
errors record handle, authenticated requester VMID, permissions, and reply
sequence. BO_CREATE and manager error records no longer share rate-limited
suppression with bursty successful traffic. Successful traffic remains limited.
Client request naming now identifies `MANAGER_GET_OBJECT`.

### glmark2 observability and verdicts

Progress tracing defaults to enabled in the one-client runner and guest wrapper;
an explicit `GLES_GLMARK_PROGRESS_TRACE=0` still disables it. Existing samples
include process state, wait channel, log growth, RSS, FD count, current scene,
and error counters, with a stall marker after unchanged samples. A stall marker
is a diagnostic hint and does not by itself prove GPU deadlock.

`GLMARK_EXPORT_ERRORS` counts both Mesa export failures and dma-buf sync-file
export/wait failures. Any such error now prevents `GLMARK_CLEAN_RESULT=PASS`.
This closes a verdict gap; a positive score alone remains insufficient.

### Reference review and remaining synchronization question

The Linux dma-buf documentation was retrieved on this date from
`https://docs.kernel.org/driver-api/dma-buf.html`. It describes exporting the
current fence set for later waiting and separately describes CPU-access cache
coherency. The matching local DRM implementation is
`Linux-Guest-GPU/drivers/gpu/drm/drm_syncobj.c`:
`drm_syncobj_export_sync_file()` first obtains a referenced fence with
`drm_syncobj_find_fence()`, then passes that fence to `sync_file_create()`.

The custom client worker currently waits by session and syncobj handle.
It therefore needs a separate review for source syncobj reset/replacement
between export and worker execution, and for session close while an exported
fence remains live. Holding an object reference alone does not establish
snapshot semantics. This is an open correctness question, not a verified fix
or an established explanation for the earlier failures.

### Build/deployment and pending validation

New diagnostic Image hashes:

```text
client e1c15945d48a83770ec3eb5f46fa54750b701569f1ce149429492c466d249f56
proxy  722e1fd790faa2951387b5340bbfe6662666edc335c6d5fda6c8ecc25eb4f9e7
```

The previous remote Images were archived as
`kernels/shared/archive/sync-cleanup-diag-20261015-013508/{client,proxy}/Image`.
Both new remote Image hashes were checked before activation by renaming the
uploaded `.new` files. The uploaded guest smoke wrapper was syntax-checked and
its hash matches locally:
`bb4570fd63c9b07c365ce01079405cc53788e435cbba7937d3b05f1f67172ea8`.
Only shared guest artifacts and the guest smoke wrapper were updated;
the host kernel, base rootfs, and boot storage are untouched.
Shell syntax and scoped diff whitespace checks pass. Four CRLF log fixtures
(clean, export error, sync-file error, and both) also verify the error-count
helper. Those checks do not replace the pending GPU regression.

The host recheck still found `MemAvailable=76108 kB`, `Inactive(anon)=2253932 kB`,
and `AnonPages=12832 kB`, with no Firecracker or broker process. A clean-host
runtime regression is pending. The five requested tracks remain:

1. ML export: historical successful individual kernels do not qualify all sizes.
2. Attention: 100 samples pass, larger and repeated lifecycle tests remain.
3. NCNN: prefix reproducer still fails; correlate traced mappings and first fault.
4. 1080p glmark2: default progress instrumentation is ready; full run remains.
5. 720p glmark2: resource exhaustion/SIGSEGV regression remains.

No reboot, power cycle, SD flash, or eMMC operation was performed in this step.

## 2026-10-15: Export fence snapshots and DRM-session lifetime

### Source-level synchronization defect

The export worker previously saved only the source syncobj handle and later
issued SYNCOBJ_WAIT against that mutable handle. Export returned to userspace
before the worker necessarily ran. Resetting, destroying, or reusing the
source between those operations could therefore change what the exported
sync_file waited for. The temporary source reference in the export function
was dropped before the asynchronous worker completed. A local fence reference
alone did not keep the proxy session alive after the userspace DRM FD closed.

This differs from the native implementation in `drm_syncobj.c`, which takes a
reference to the fence at export time. The existing
`drm_syncobj_transfer_to_binary()` also takes such a reference and replaces the
destination fence. The custom proxy's SYNCOBJ_TRANSFER already forwards to
that implementation.

### Implemented change

Export now creates a private proxy syncobj and uses the existing binary
SYNCOBJ_TRANSFER RPC to snapshot the source's current fence before returning
the sync_file FD. This destination is absent from the client userspace handle
table and is used only by the export worker. The worker waits on the snapshot
and destroys it after completion/error. It holds a reference to the originating
DRM file until wait and cleanup finish, keeping the session alive across
userspace close. No new wire opcode or message layout was introduced.

Source reset/destruction after snapshot capture cannot replace the captured
fence. This is a source-level correction, not yet runtime proof that the
historical Mesa errors, attention readback, or NCNN failures are fixed.
The existing bounded wait policy remains; full native synchronization
equivalence is not claimed. Export now costs two extra RPCs plus snapshot
destruction, and its performance impact has not been measured.

The worker's error logging now tests its actual wait result rather than
querying a still-unsignaled local fence. The export ioctl also closes an
installed FD if copying its result to userspace fails.

### Dedicated regression mode

The ARM64 ioctl smoke gained `--sync-file-snapshot`. It:

1. Checks that exporting an empty syncobj fails with `EINVAL`.
2. Exports 64 initially signaled syncobjs, immediately resetting and destroying
   each source and creating/destroying another empty object to exercise reuse.
3. Closes its sole userspace DRM FD before checking all exported FDs.
4. Requires each sync_file to become poll-readable within five seconds and
   report `SYNC_IOC_FILE_INFO.status=1`, rather than merely accepting any
   signaled/error fence.

This is scheduling stress, not a deterministic injection of every race window.
It also does not exercise pending GPU fences, cross-session imports, or
allocation failures. Those cases remain outside this test's evidence.

The one-client runner supports it end-to-end, including payload selection,
completion wait, and result markers:

```bash
RUN_ID="shared-sync-file-snapshot-$(date +%Y%m%d-%H%M%S)" \
  ./scripts/run/run-vmshm-e2e.sh \
  --skip-build --skip-sync --sync-file-snapshot-smoke
```

Run only after restoring and checking a healthy host baseline. There is no
hardware PASS result for this mode yet.

### Verification and deployment

Both guest kernel builds and the static ARM64 smoke build succeeded. No
warnings/errors were found in the kernel build log; shell syntax and scoped
diff checks pass. The smoke's help/argument handling was executed on RK3588,
which verifies the ARM64 binary launches, not DRM semantics.

```text
client Image 5879f05de820129eb412e545ec956abd9a0134e1cbfc59dddeaaa394839f0544
proxy Image  722e1fd790faa2951387b5340bbfe6662666edc335c6d5fda6c8ecc25eb4f9e7
ioctl smoke  654d900305efda918c8f49fde03ba5cb23b1a0090be10846c020a09a49bc4330
```

The client Image and smoke binary were uploaded, hash-verified, then activated.
The previous versions were archived under
`kernels/shared/archive/sync-snapshot-20261015-014350/`.
The proxy Image is unchanged from the preceding diagnostic deployment.

No GPU workload was launched in this step. Host recovery is still pending;
no reboot, power cycle, flash, base-rootfs replacement, or eMMC access occurred.
The full ML, attention, NCNN, 720p, and 1080p completion gates remain open.

## 2026-10-15: Import installs the captured dependency synchronously

### Defect in the pending-import path

The previous custom `panthor_client_syncobj_import_sync_file()` accepted an
own-session pending fence, queued a worker, and returned success immediately.
The worker waited for the local fence and later called SYNCOBJ_SIGNAL on the
target. Until then, the target retained its earlier fence. If that earlier
fence was signaled, a subsequent submission could observe a satisfied
dependency before the imported work finished. If userspace reset or reused
the target, the late signal could instead affect a newer generation.

The native reference at
`Linux-Guest-GPU/drivers/gpu/drm/drm_syncobj.c::drm_syncobj_import_sync_file_fence()`
replaces the target fence before returning. It does not model import as a
future signal operation.

### Implemented correction and locking

Own-session pending imports now transfer the proxy snapshot fence into the
target before the import ioctl returns. Completed successful local fences use
the existing synchronous signal operation; error fences return their error.
Foreign fences and cross-session imports remain unsupported as before.

Each exported fence now has a snapshot mutex. Import holds it while checking
local completion and transferring the still-live snapshot. The export worker
holds the same mutex while signaling local completion, destroying its snapshot,
and clearing its handle. Thus import cannot race a successful snapshot
destruction and accidentally transfer a recycled handle.

The asynchronous import worker, its workqueue, allocation, and delayed signal
path have been removed. Lock order is snapshot mutex followed by the RPC lock;
the export worker completes its wait RPC before acquiring the snapshot mutex.
No RPC wait holds the snapshot mutex and then depends on the removed importer.
Hardware validation of this change remains pending.

### Expanded regression, with explicit limits

`--sync-file-snapshot-smoke` now performs 64 rounds of export, import into an
initially signaled target, re-export, target reset/destruction, and source
reset/destruction. After closing the DRM FD, it checks all 128 sync_file FDs
for successful completion. The runner requires both markers:

```text
PANTHOR_SYNC_FILE_SNAPSHOT_SMOKE=PASS exports=128 source_reset=1 source_destroy=1 drm_close=1
PANTHOR_SYNC_FILE_IMPORT_SMOKE=PASS imports=64 target_reset=1 target_destroy=1
```

Fixtures verify that complete CRLF markers are accepted, a missing import
marker is rejected, and the earlier export-only 64-FD marker is rejected.
This is scheduling stress with initially signaled source fences. It does not
force the pending-import branch or establish correctness for real pending GPU
work. A real workload or a deterministic pending-fence test is still required.

### NCNN is a separate unresolved track

The prefix reproducer
`shared-ncnn-prefix8-out16-cached-r1-1loop-192c96p-manual600-20261015-063145`
contains no `SYNCOBJ_EXPORT_SYNC_FILE` records. Its only IMPORTDIAG invocation
is the boot smoke's invalid `handle=0 fd=0 flags=0`, repeated in the later dmesg
excerpt; it is not a workload fence import. The first rendering fault remains
after `GROUP_SUBMIT_TRACE seq=14`: `CS_RES_TERM`, then `DATA_INVALID_FAULT`.
Therefore the current sync-file corrections must not be presented as a
demonstrated fix for NCNN. Its traced mapping/allocation-generation regression
still needs to run.

### Build/deployment evidence

Both guest kernels and the static ARM64 smoke rebuilt successfully. No build
warnings/errors were found; shell syntax and scoped diff checks pass. Uploaded
client Image and smoke hashes were verified before activation:

```text
client Image 0fae057fb4c7e4f153dc440915796532b16b76a91574ff699e767fa00cb4d60f
proxy Image  722e1fd790faa2951387b5340bbfe6662666edc335c6d5fda6c8ecc25eb4f9e7
ioctl smoke  18caaf143a1d5f5761ae4a0f192ec920b3474304f85086b057f88a7f02356bf0
```

Previous remote client Image and smoke are archived under
`kernels/shared/archive/sync-import-transfer-20261015-015039/`.
The new smoke binary's `--help` ran on RK3588; no DRM/GPU test was executed.

The host still has only `MemAvailable=77636 kB`, with
`Inactive(anon)=3006696 kB` and `AnonPages=12548 kB`, and no running
Firecracker or broker. No reboot, power cycle, flash, or eMMC operation
occurred. All five full workload qualification gates remain open.

## 2026-10-15: Clean-host runtime recovery and confirmed page-table replacement fix

### Host recovery and read-only shared roots

The live host had about 74 MiB MemAvailable and no Firecracker/broker process.
Diagnostics were saved to `GPU-SFTP/log/shared/host-recovery-20261015/`.
A software reboot did not promptly restore SSH; the existing Pi reboot wrapper
then recovered the board. The fresh host had about 3151 MiB available,
`6.12.0-opencca-pmthor`, and `/dev/pmthor`.

The first sync-file test (`shared-sync-snapshot-cleanhost-20261015-1023`)
failed before userspace: the proxy mounted the same `rootfs.ext2` read-write
before the read-only client booted. The client reported ext4 journal recovery
required, write access unavailable, and VFS error -30/panic. Both shared config
generators and GLES proxy generators now use `root=/dev/vda ro` and a read-only
VMM block device. They run `/bin/sh` and need no persistent root writes.
Payload injection still happens through a host loop mount before VM launch.

`shared-sync-snapshot-readonly-20261015-1025` then recorded:

```text
PANTHOR_SYNC_FILE_SNAPSHOT_SMOKE=PASS exports=128 source_reset=1 source_destroy=1 drm_close=1
PANTHOR_SYNC_FILE_IMPORT_SMOKE=PASS imports=64 target_reset=1 target_destroy=1
RESULT: PASS
```

This exercises initially signaled fences, not a deterministic pending-fence
race. Later ML logs do exercise import with `status=0` (pending).

### Nonblocking export-fence monitoring

The export worker's 750 ms proxy wait shared the serialized RPC channel with
submission/import traffic. It now polls its immutable snapshot with a zero
relative timeout and sleeps 1--2 ms outside the RPC between pending results.
The 60-second total bound remains. Both guest kernels build successfully.
This removes this worker's intentional blocking RPC; it is not a measured
end-to-end speedup claim. In particular, attention still takes about 2.37 s
per iteration in the tested WC configuration.

### Deterministic EEXIST reproduction and correction

`shared-ml-all-nonblocking-20261015-1030` ran six kernels in one process with
100 measured/5 warmup iterations and GEMM size 256. Five kernels passed, but
softmax allocation failed four times with `DRM_IOCTL_PANTHOR_VM_BIND err=17`.
The first proxy failure was VM_BIND_TRACE seq=37: a 16 MiB MAP at
`0x7ffffee00000`, after earlier mappings/unmaps had left lower-level tables.
Thus this was not an allocation-pressure failure on the recovered host.

`arm_panthor_lpae_init_2m_block_or_pages()` rejected any existing descriptor,
including an empty lower-level table. The native map semantics remove a table
before replacing its whole range. The Panthor path now does the same through
`__arm_panthor_lpae_unmap()`. The generic Panthor PTE initialization path also
now uses that HPA-aware walker rather than `__arm_lpae_unmap()`.

The existing `--vm-bind-smoke` now allocates a 2 MiB BO and tests the same VA
with MAP/UNMAP sizes 4 KiB, 2 MiB, 64 KiB, 2 MiB. Hardware A/B evidence:

| Run | Result |
| --- | --- |
| `shared-vm-bind-size-reuse-oldkernel-20261015-1043` | Old proxy `722e1fd...`: round=1, size=0x200000 fails with File exists / ret=-17; RESULT: FAIL. |
| `shared-vm-bind-size-reuse-fixed-gate-20261015-1042` | Fixed proxy `f1d73814...`: `PANTHOR_VM_BIND_SIZE_REUSE=PASS rounds=4`; RESULT: PASS. |
| `shared-ml-all-tablefix-10it-20261015-1037` | All six kernels, including softmax, pass 10 measured/2 warmup iterations in one process; ML_RESULT/GPU_SMOKE_RESULT PASS; no Mesa/VM_BIND error. Historical runner RESULT remains FAIL because the remote wrapper lacked the new ML_CLEAN_RESULT marker. Do not rewrite this result as a formal gate PASS. |

The remote smoke wrapper has since been synchronized and hash-verified
(`c9c7a35ff4f510c6ccf94b6ace08a81eed88a0793e02be6827bce9ee5c61fc15`).
The runner now accepts the BO_CREATE diagnostic `seq=` field, requires the
size-reuse marker for VM-bind smoke, and requires all six named kernels for
`--kernel all`, honoring an explicit GEMM size. CRLF fixtures check full/missing
kernel sets, individual attention selection, and export-error rejection.

The formal rerun `shared-ml-all-tablefix-100it-20261015-1053` then passed
all six kernels with 100 measured/5 warmup iterations and GEMM 256, using the
synchronized wrapper: `ML_RESULT=PASS`, `ML_CLEAN_RESULT=PASS`,
`ML_EXPORT_ERRORS=0`, and runner `RESULT: PASS`.

Active guest artifacts after restoring the fixed proxy from the A/B test:

```text
client 2e04897b579ed74dd0c5b52bd2f5fcfacaa9d7cc75875f6498677b77bafe2922
proxy  f1d73814b6e73655d07863dcf68ab5b4633cf4bbeab4b22d3de8bdf8a3a71ea4
```

### NCNN remains a separate first-fault investigation

`shared-ncnn-prefix8-tablefix-20261015-1045` used the cached-client diagnostic,
512/384 MiB guest RAM, and one prefix8-out16 loop. Qualification passed, but
NCNN still returned device loss. Immediately after seq=14, the first recorded
MMU error was an AS1 READ at GPU VA `0x8`, `TRANSLATION_FAULT_1`; CS_BUS_FAULT
followed. The three nonempty seq=14 streams were resolved to live mappings
and payload generations 40/41/42, after explicit seq=61--69 unmaps/remaps.
This narrows the next investigation to referenced descriptors/data visibility
and cache ownership; it does not prove a particular null-pointer/cache cause.
A default-WC comparison and the full model matrix remain required.

A full 720p null-noop/finish glmark run was started as
`shared-glmark720-tablefix-full-20261015-1047`. It completed the full suite:
`GLMARK_SCORE=59`, `GLMARK_CLEAN_RESULT=PASS`, `GLMARK_RESULT=PASS`,
`GPU_SMOKE_RESULT=PASS`, and runner `RESULT: PASS`. BO_CREATE, export, and
VM_BIND error counts were all zero. The existing validation exception remains
visible (`GLMARK_EXPECTED_FRAMEBUFFER_ERRORS=1`, unexpected=0).
Null-noop is the existing diagnostic frontend; it does not qualify stock
GBM/PRIME interoperability.

The default-WC NCNN comparison
`shared-ncnn-prefix8-wc-tablefix-20261015-1051` also failed. Qualification passed;
the model reached submit seq=19, then a job timed out with queue 2's fence at
8 while the pending job expected 9. Unlike the WB-client run, no MMU page fault
preceded this timeout. Several proxy stream prefixes read as zero. This does
not establish whether those bytes were actually stale.

The object managers used WB kernel mappings while the default client BO mmap
used WC. A follow-up experiment changes both managers' object-window mappings
and the proxy debug mmap to WC, keeping the separate WB communication ring
unchanged. This removes that specific mixed-attribute alias; its effect on
NCNN and the GLES regressions must be measured before calling it a runtime fix.

Both guests build without warnings/errors with this change. Runtime artifacts:

```text
client e797e3180e65407eecb5cfed894725f9e5f8b31f822f1089feb38a820062e68f
proxy  29aade4ada0b22dd3018bd4e85145a4dd860156350ac2896f0e02d6b96aafe1e
```

`shared-ncnn-prefix8-matchedwc-20261015-1058` passed the same prefix8-out16
test with the default WC client: qualification PASS, model PASS, NCNN_RESULT
PASS, and runner PASS. The old WB-manager/default-WC-client comparison above
failed. This supports the mixed-attribute mapping as a runtime defect, while
larger model and GLES regressions are still necessary.

`shared-ncnn-fullmodels-matchedwc-1loop-20261015-1100` passed mobilenet_v2
and mobilenet_v3, but resnet50 failed. Its first recorded BO failure requested
`0x9800000` (152 MiB) with ret=-12; the default object window was only 224 MiB
and its buddy max_order was 15 (128 MiB). A later GPU WRITE fault at VA
`0x4000000` followed these allocation failures. This result does not qualify
resnet50; a larger window is needed before diagnosing any independent GPU fault.
NCNN uses benchncnn's zero-filled weights, so these are graph execution/timing
checks, not pretrained-model accuracy tests.

The first matched-WC full 1080p glmark run
`shared-glmark1080-matchedwc-full-20261015-1103` likewise exhausted the old
224 MiB window during terrain/shadow: BO requests of `0x8a2000` and
`0x2060000` returned -12. A score despite such errors cannot qualify the run.
The runner now selects 512 MiB for glmark and 768 MiB for NCNN when the object
window is `auto`; ordinary compute/ML retain their existing count-based policy.
An explicit window override is preserved. Automatic host-memory preflight now
requires at least guest RAM + configured object capacity + 256 MiB, with the
previous 900 MiB minimum retained. These capacity defaults still require the
larger-window runtime reruns.

Those reruns exposed two independent setup defects before model execution:

- `shared-ncnn-resnet50-matchedwc-768m-20261015-1110` was explicitly
  **ABORTED**: extending the legacy `0x30000000` window to 768 MiB covered
  UART/virtio MMIO at `0x40000000`, and the proxy console never booted.
  Object windows above 256 MiB now move to GPA `0x100000000` in both guests;
  preflight and launch logs record the GPA.
- `shared-ncnn-resnet50-matchedwc-high768m-20261015-1114` booted at the high
  GPA, but the allocator failed initialization with -12. The warning stack
  points to the `kcalloc` for per-page buddy metadata (about 4.5 MiB,
  order 11), not exhausted payload capacity. That CPU-only metadata now
  uses `kvcalloc`, with both error cleanup and destruction using `kvfree`.
  The follow-up guest build/runtime must qualify this correction.

`shared-ncnn-resnet50-large-meta-fixed-20261015-1117` qualifies that correction:
the high-GPA 768 MiB domain initialized with max_order=17; resnet50 completed
with `NCNN_MODEL_RESULT=PASS`, `NCNN_RESULT=PASS`, `GPU_SMOKE_RESULT=PASS`,
and runner `RESULT: PASS`. BO_CREATE/VM_BIND failure counts were both zero.
Its one measured loop was 985.54 ms; this is a functional checkpoint, not the
100-loop performance result. The updated proxy Image is
`24e213e91b4ecc2ce2c4e6dece0b1bad15d445d3b7207e8701f4f70da5922b55`;
the client remains `e797e318...`.

The NCNN model gate also rejects any Mesa error, Vulkan `vk* failed`, or
`VK_ERROR_` marker even if benchncnn exits zero and prints timing. The host
runner independently rejects BO_CREATE/VM_BIND failures. NUL/CRLF fixtures
confirm that a clean timing passes while allocation and fence errors fail.

### Host PFN-reference lifetime patch: built, not deployed

`kvm_gpa_to_hpa()` obtains a reference with `gfn_to_pfn_prot()` for every
translated page but had no corresponding release, even on VM teardown.
A source patch retains one reference per PFN in a per-VM xarray, releases
duplicate acquisition references, and releases retained references at teardown.
Indexing by PFN retains old backing across memslot replacement and deduplicates
aliases. This is bounded by unique exposed pages, not by translation count.

The host Image builds without warnings/errors and was packed into
`opencca/snapshot/kernel-pmthor-gpa-pin-lifetime-20261015.img`; its flash wrapper
dry run passed the live SD layout preflight. It has not been flashed/booted.
Runtime memory-recovery proof and the device-quiesce-before-final-page-release
lifecycle audit remain required before deployment. A retained reference is
also not a complete DMA pin/migration/revoke protocol.

No SD/eMMC/firmware flash occurred in this checkpoint. The subsequent
clean-host matrix reboot recovered about 3159 MiB available. Runtime
`shared-ncnn-all-matchedwc-100loops-20261015-1122` then passed all three
models, 100 measured loops each, zero failed models. Means were 178.16 ms
(mobilenet_v2), 174.32 ms (mobilenet_v3), and 872.29 ms (resnet50).
The remote result is PASS; editing the live local runner caused its later
log-fetch tail to fail (`n: command not found`), so logs were fetched in a
separate read-only invocation. Later launches use immutable script copies.

`shared-glmark1080-wc-high512m-full-20261015-1127` completed the full
1080p suite with Score 57, BO_CREATE/export/VM_BIND errors all zero,
GLMARK_CLEAN_RESULT/GLMARK_RESULT/GPU_SMOKE_RESULT PASS, and remote
`RESULT: PASS`. This validates the matched-WC mapping plus 512 MiB high-GPA
window through the earlier terrain/shadow failure point.

Latest-kernel GEMM 512/all-kernel ML regression, larger/repeated Attention,
pending-fence regression, and repeat-run host memory recovery remain open.
The concise current matrix and limitations are maintained in
`docs/shared/PANTHOR_SHARED_GPU_FIX_VERIFICATION_20261015.md`.


### Latest Guest matrix completion and deployed joint Host session lifetime

The earlier per-VM-only PFN candidate and the later device-only candidate were
never deployed. Audit found that KVM teardown and `/dev/pmthor` file release
can occur in either order, and GPU MMIO is mapped separately via `/dev/mem`.
The final candidate therefore uses a reference-counted GPU session owned by
both the device file and each VM that translates pages through it. The session
xarray keeps one reference per PFN; duplicate translation references are
returned immediately. A VM cannot rebind its cached HPAs to another session.
Tracking requires the current VMM mm to match the device opener's mm.

Final release requires both ownerships to end and a successful GPU reset.
The driver now checks soft/hard-reset completion rather than printing a
successful quiesce after both timeouts. A failed reset retains the device
ownership on a retired-session list; a later successful reset can retire it.
No runtime reset-failure injection has been performed. Active platform unbind
and a complete DMA pin/migration/revoke protocol remain outside this fix.

The final Host Image built without warnings/errors and was packed using the
existing initrd/DTB. The Pi wrapper verified the live SD kernel layout and GPT,
selected storage ID 2, and wrote only p3 at LBA 0x8000. Rootfs and firmware were
not flashed. The board booted `6.12.0-opencca-pmthor #9`, built
`Thu Oct 15 11:57:13 CST 2026`; `pmthor_gpu_track_pfn` is present in kallsyms.

- Host Image SHA256: `fc198ee4371b86d5c740ad06f151ea80eb13e2e7ce2a3c8af3f64fff16791dc5`
- Boot image: `opencca/snapshot/kernel-pmthor-joint-session-pfn-20261015.img`
- Boot image SHA256: `33c5d968a1ed011ec94333e6c84de1746464678b42c35dd2744bb386372dc816`
- Deployment/build/KVM proof: `GPU-SFTP/log/shared/host-recovery-20261015/joint-*`

The new ARM64 test in `GPU-SFTP/tests/pmthor-pfn-lifetime/` invokes the actual
GPA_TO_HPA HVC with 32 copies of one GPA, then exercises VM-first and
device-first teardown. Old Host control passed translation (before deployment).
The new Host passed both translation and the kernel-log lifetime checker:
VM-first closes with pages=1/vm_refs=0 and releases after reset; device-first
closes with pages=1/vm_refs=1 and releases only after VM teardown. Both release
exactly one PFN. Initial diagnostic markers used libc dprintf, which returned
EINVAL on /dev/kmsg; switching to one direct write fixed the test marker path.
Negative log fixtures reject missing releases, wrong counts, and bad ordering.

Before this Host deployment, the final matched-WC Guest pair also completed:

- `shared-ml-all512-latestwc-100it-20261015-1134`: six kernels, 100 measured /
  5 warmup iterations, GEMM 512, all correctness/clean markers PASS.
- `shared-attention320-lifecycle-r{1,2,3}-20261015-1141`: three separate VM
  lifecycles, 10 measured / 2 warmup iterations at 320x64, all PASS and launcher
  exit 0. Single naive-attention dispatch is approximately 3.74 seconds; the
  accepted CLI range does not guarantee larger sizes fit the GPU watchdog.
- `shared-latestwc-vm-bind-regression-20261015-1145` and
  `shared-latestwc-sync-snapshot-regression-20261015-1145`: PASS.
- `shared-2client-latestwc-4mib-100it-20261015-1148`: two concurrent clients,
  each 4 MiB / 100 measured iterations, GLES_PASS and launcher exit 0.
- `shared-glmark720-latestwc-high512m-full-20261015-1153`: full null-noop /
  finish suite, Score 58, zero unexpected framebuffer/BO/export/VM_BIND errors,
  all clean/result markers PASS and launcher exit 0.

Long idle SSH sessions previously stalled after a terminal remote PASS; the
local stale connection was terminated and logs fetched separately. Both
runners now use SSH server-alive probes. Latest 720p completed the full long
run and fetch with launcher exit 0. All subsequent runners execute immutable
same-directory snapshots to prevent source edits changing Bash read offsets.

A sequential all-kernel 100-iteration / NCNN three-model 100-loop / full 720p /
full 1080p matrix is now running on the new Host with per-run memory captures.
These results must be recorded separately from the pre-Host-fix matrix.


### Final Host #10: block takeover until VM teardown and reset again

Host #9 completed the four-run matrix without reboot: ML all512/100 PASS,
NCNN three models/100 PASS, full 720p Score 59 PASS, full 1080p Score 58 PASS.
MemAvailable remained approximately 3150--3151 MiB and Shmem returned to
1328 KiB after each run. These are #9 results, retained as historical evidence.

Further lifecycle audit found that a VM can continue MMIO after device-file
close. Merely retaining pages until VM teardown while remembering an earlier
reset is insufficient: the VM could restart GPU work after that reset, and a
new owner must not take over while that old VM survives. The stronger KVM test
actually failed on #9 because reopening the GPU succeeded with the old VM alive
(`joint-host-pfn-reopen-control.log`, expected negative-control failure).

Final #10 replaces the callback/refcount/retired-list candidate with one
owner-lock-protected active session and an explicit bound-VM count. Device
close resets promptly but retains the session and its PFNs while any VM lives.
New opens return EBUSY until those VMs end. Last-VM teardown resets again, then
releases unique PFNs; a failed reset keeps the session for a later open/reset
retry. If VM teardown occurs first, final device close performs the reset and
release. Registry/owner locking serializes publication, close, VM teardown,
and takeover. Active platform unbind and full DMA pin/migration/revoke remain
unsupported; this is not a confidential-isolation proof.

Final #10 built without warnings/errors and was flashed through the Pi wrapper
only to SD p3. It booted `6.12.0-opencca-pmthor #10`, built
`Thu Oct 15 12:23:44 CST 2026`.

- Host Image SHA256: `ca8fb02a1ca95b588ef1e2fcd3191865c98ab3b1b758d586d3b36e90c88c3f6c`
- Boot image: `opencca/snapshot/kernel-pmthor-final-session-pfn-20261015.img`
- Boot image SHA256: `27c6ad71937d8cee1d8c7d976f6e76cca41ed6ab51b6f9eb0bebeacfb44ae4bb`
- Proof: `final-host-pfn-{test,kernel,check}.log` under the host-recovery log directory.

The enhanced two-order/32-duplicate KVM regression passed, including EBUSY on
reopen and an additional successful reset after last-VM teardown before PFN
release. `shared-final-host-proxy-sigkill-20261015-1228` then intentionally
killed Proxy after at least five pending-import observations in a long
Attention 320 run. Client/broker were stopped afterward. The workload FAIL /
launcher exit 1 is expected and labelled by fault-injection-intent.txt; Host
completed both resets and released 2968 PFNs. MemAvailable returned to about
3154 MiB. This is a fault-exit test, not a successful inference benchmark.

The shared runner now defaults to the tested null-noop frontend plus finish;
explicit overrides remain available. The common gpu-smoke wrapper retains
its other modes for non-shared workflows. The final #10 sequential matrix is
running without intermediate reboots: post-fault Attention 320, ML all512/100,
NCNN all/100, full default 720p/1080p, mapping-size reuse, sync snapshots, and
two-client 4 MiB/100. Detailed results will follow in the concise report.


### Final #10 completion, repeat-client check and PCP accounting

All final #10 cases in `shared-final-host-*-20261015-1230` passed with individual
launcher exit 0: post-fault Attention 320 (10 measured/2 warmup), all six ML
kernels (100/5, GEMM 512), NCNN three models (100 each, zero failed), full default
720p glmark (Score 59), full default 1080p (Score 58), VM_BIND size reuse,
sync snapshot/import, and two concurrent 4 MiB clients (100/5 each).
The two-client orchestration first passed an unsupported single-client
--skip-build flag and exited before remote work; its CLI error log is retained,
and the corrected invocation passed. An additional identical two-client run
`shared-final-host-2client-repeat-20261015-1258` also passed with launcher exit 0.
All four major long runs restored roughly 3151--3153 MiB MemAvailable and
1328 KiB Shmem without an intervening reboot. Final teardown logs show both
reset stages and matching unique-PFN close/release counts.

The raw two-client MemAvailable snapshot was approximately 3055 MiB, so it was
investigated rather than called full recovery. CPU1 PCP held about 24960 free
pages. Repeated stat_refresh reads invoke refresh_cpu_vm_stats(true) and
PCP decay, without changing sysctl configuration: PCP 23949 -> 4032 pages
(-79668 KiB), MemAvailable 3127236 -> 3206776 KiB (+79540 KiB), Shmem unchanged
at 1328 KiB. This accounts for the apparent extra usage as retained free PCP
pages; the small remaining difference includes ordinary kernel/cache overhead.
Source anchors: mm/page_alloc.c free_unref_page_commit()/decay_pcp_high(),
mm/vmstat.c vmstat_refresh(), mm/show_mem.c si_mem_available().
Proof is in pcp-refresh-proof.log and the repeat-run before/after snapshots.

Final remote Guest hashes match the recorded pair, Host remains #10, no
Firecracker/broker processes remain, CPU online is restored to 0-1. Detailed
matrix, exact hashes, raw memory table, known frontend/accuracy/lifecycle
limits and reproduction commands are in PANTHOR_SHARED_GPU_FIX_VERIFICATION_20261015.md.
