# CCA Confidential GPU Sharing Design

Date: 2026-06-12

This note records the current design for running Panthor GPU work from ARM CCA
Realm VMs on RK3588/OpenCCA. It is intentionally explicit about what the
hardware can and cannot enforce on this board.

## Boundary

RK3588's Mali GPU uses its embedded GPU MMU. It is not behind an Arm SMMU that
can enforce stage-2 translation, GPC ownership, or per-Realm DMA permissions.
For this local platform, the GPU itself must therefore be treated as trusted
while the host kernel, KVM userspace, and other VMs remain outside the Realm
trust boundary.

The immediate security target is:

- a VM must not map or submit another VM's GPU objects;
- host/KVM must not accidentally translate private Realm guestmemfd pages into
  GPU-visible HPA;
- a Realm guest must explicitly convert pages that the trusted GPU is allowed to
  consume;
- vmshm/session/object ownership stays VMID-scoped for shared GPU
  virtualization.

This does not yet mean that GPU-visible payload bytes are confidential from the
host. Without SMMU/GPC enforcement, a page converted to normal shared memory is
device-reachable and host-reachable. Full host-confidential GPU payloads require
an OpenCCA model change that represents the trusted GPU as a protected device
domain.

## Design Options

| Option | Description | Status |
| --- | --- | --- |
| A. Realm marks GPU-visible pages shared | The Panthor Realm guest uses `set_memory_decrypted()` for BO payloads, GPU page tables, and GPA-to-HPA exchange pages before those pages are given to the GPU or host translation hypercall. | Implemented as the first stage. It is the smallest correct step and prevents private guestmemfd pages from being used as GPU PTE targets. |
| B. Per-Realm GPT view switching | Extend OpenCCA so EL3/RMM selects a CPU-local GPT view on Realm entry and restores the host view on exit. Each RD gets a GPT view, so one Realm cannot CPU-load another Realm's private pages. | Feasible in OpenCCA simulation. It protects CPU accesses but not GPU DMA on RK3588 unless combined with a trusted GPU/device view. |
| C. Trusted GPU protected-device view | Add an OpenCCA software device domain for the Mali GPU. GPU-owned pages are visible to the trusted GPU and the owning Realm, but not to host CPU mappings or other Realms. | Required for the final host-confidential design. This is the correct replacement for missing SMMU/GPC hardware in the local simulator. |
| D. Secure shared guestmemfd object | Change KVM/RMM guestmemfd so a protected object can be attached to multiple Realms by ACL while remaining unmappable by host userspace/KVM. | Useful for Realm-to-Realm proxy/client sharing. Larger ABI change: current guestmemfd is bound to one `struct kvm`. |
| E. Encrypted or bounced GPU buffers | Keep private Realm memory encrypted and copy/encrypt around the GPU boundary. | Limited. A normal GPU cannot compute on ciphertext, so this only helps command transport or workloads designed for encrypted data. |

## Per-Realm GPT View Shape

The per-Realm GPT idea is valid in OpenCCA because the platform is simulated.
The clean place to switch views is the RMM CPU world-switch path:

```text
host/non-secure world
  -> RMM rec_run_loop()
     save_ns_state()
     opencca_gpt_select_realm_view(rd->opencca_gpt_view)
     run_realm()
     opencca_gpt_select_host_view()
     restore_ns_state()
  -> host/non-secure world
```

TF-A's current GPT code uses one global `gpt_config` and one global table root.
The OpenCCA extension should make this a set of view objects:

- host view: host pages are NS, Realm private pages are not host-accessible;
- Realm view N: Realm N private pages are Realm-accessible, other Realm private
  pages are not accessible;
- trusted GPU view: GPU-visible objects are accessible to the GPU and the
  owning Realm according to an OpenCCA ACL.

Because GPT selection is CPU-local, this alone does not constrain RK3588 GPU
DMA. Option B must therefore be paired with Option C before it is treated as a
confidential GPU payload design.

Concrete code landing points after source inspection:

- TF-A GPT state lives in
  `opencca/trusted-firmware-a/lib/gpt_rme/gpt_rme.c`. `gpt_config` is currently
  one global instance, and `gpt_enable()` writes one L0 base to `GPTBR_EL3`.
  A multi-view prototype should introduce a `gpt_view` table, copy or derive
  L0/L1 roots per view, and add a CPU-local `gpt_select_view(view_id)` helper
  that rewrites `GPTBR_EL3`, invalidates cached GPT/TLB state, and keeps
  `GPCCR_EL3` policy unchanged.
- RMM world switch lives in
  `opencca/tf-rmm/runtime/core/run.c`. `rec_run_loop()` calls
  `save_ns_state()`, `restore_realm_state()`, then `run_realm()`, and later
  `save_realm_state()` and `restore_ns_state()`. The switch hook belongs
  immediately before `run_realm()` and immediately after it returns.
- Realm metadata lives in `opencca/tf-rmm/runtime/include/realm.h`. `struct rd`
  can carry an OpenCCA-only `gpt_view_id` or trusted-device ACL handle; the
  value is copied into each REC through `rec->realm_info` or looked up from
  `rec->realm_info.g_rd`.
- The existing RMM-to-EL3 transition path for granule delegate/undelegate is
  handled by RMMD in
  `opencca/trusted-firmware-a/services/std_svc/rmmd/rmmd_main.c`. A prototype
  view-select call can follow this pattern as an OpenCCA-private RMM-EL3 SMC,
  but it should not be exposed as normal guest ABI until the object model is
  settled.

The required ordering is:

```text
RMM before run_realm:
  select Realm CPU GPT view
  run Realm
RMM immediately after run_realm returns:
  select host CPU GPT view
  handle exit
```

For GPU work, a separate trusted-device view or object ACL must be updated when
Panthor maps or unmaps a GPU object. CPU GPT view switching alone must not be
used as proof of GPU payload confidentiality.

## First Stage Implemented Now

The current code implements Option A and keeps the unsafe shortcut blacklisted.

Guest Panthor changes:

- ordinary shmem GEM BOs are pinned and converted with
  `set_memory_decrypted()` before the handle is returned to userspace;
- Panthor kernel BOs are converted before VM_BIND maps them into the GPU address
  space;
- Panthor GPU page-table pages are converted before page-table entries are
  written;
- the private GPA-to-HPA batch page is converted before it is passed to the host
  hypercall;
- teardown calls `set_memory_encrypted()` before freeing those pages.

Host KVM guard:

- `GPA_TO_HPA` rejects the GPA array page and payload entries if they are still
  private according to `kvm_mem_is_private(kvm, gfn)`.

Runner/VMM guard:

- direct `realm_config && gpu_passthrough=true` remains blocked. The first stage
  fixes the memory class, but the project still needs a trusted GPU owner view,
  MMIO policy, IRQ teardown policy, and a controlled enable switch before
  hardware Realm GPU smokes should resume.

## Final Direction

The final local RK3588/OpenCCA design should be:

```text
Realm client/proxy private RAM: guestmemfd private
GPU-visible trusted objects: OpenCCA trusted-GPU domain, owner VMID/session ACL
Host/KVM userspace: cannot map trusted-GPU objects
Other Realms: cannot map objects unless an RMM/OpenCCA ACL grants them
GPU: trusted consumer of its object domain
```

For shared GPU virtualization, the existing vmshm manager/session isolation is
the right object-policy layer. The missing piece is replacing host-readable
vmshm payload backing with protected shared guestmemfd/OpenCCA objects or with a
trusted GPU domain object that both the owning Realm and the trusted GPU can
access.
