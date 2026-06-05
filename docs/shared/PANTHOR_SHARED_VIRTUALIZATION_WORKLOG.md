# Panthor Shared GPU Virtualization Worklog

This log records implementation work toward the Panthor shared-GPU ioctl
virtualization plan. It intentionally separates tested designs from partial or
incorrect designs so future work can reuse the stable pieces and avoid repeating
dead ends.

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
