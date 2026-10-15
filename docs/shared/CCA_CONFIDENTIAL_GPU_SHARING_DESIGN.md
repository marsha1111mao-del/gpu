# CCA Realm Direct GPU Memory Design

Date: 2026-07-18

## Goal

Run Panthor directly in one Realm VM while keeping GPU buffers inaccessible to
Host CPU software. Memory encryption and physical-memory attacks are outside
the threat model.

The design uses an asymmetric access path:

```text
Realm CPU -> Realm translation + GPC/GPT -> Realm HPA -> allowed
Host CPU  -> NS translation    + GPC/GPT -> Realm HPA -> denied
Mali DMA  -> GPU MMU HPA, bypassing GPC  -> DRAM      -> allowed
```

This is not a new GPT memory type. GPU buffers remain ordinary delegated Realm
granules (`GPT_GPI_REALM`). The isolation property comes from applying GPT to
Host CPU accesses while the local Mali DMA path accesses physical DRAM without
consuming a GPC identity.

## Platform Assumption

The design depends on this RK3588/OpenCCA integration assumption:

```text
Mali normal-memory transactions are not rejected by the CPU-side GPC/GPT path.
```

The GPU does not need a Realm PAS tag, an SMMU stage-2, a protected-mode
firmware feature, a GPC-exempt identity configured by this patch, or an EL3
per-page allow-list. Its embedded MMU translates GPU VA to the HPA written by
the guest Panthor driver, then accesses that HPA normally.

The absence of an SMMU is therefore not a blocker for the single-Realm direct
path. It means there is no hardware per-VM DMA isolation, so this model must
assign the whole GPU to one Realm at a time.

This assumption is now confirmed for a minimal compute workload. With the
current Host RMI mapping, the Realm reads the real G610 ID, loads CSF firmware
through HPA-backed Mali page tables, completes Panthor DRM initialization, and
passes a 4096-element GLES compute check.

Host CPU access to the same Realm HPA has also been tested on RK3588. The
runtime probe returns `HOST_READ_SUCCEEDED`, which is expected for this
OpenCCA-on-RK3588 experiment because RK3588 does not provide real hardware
`GPC/GPT` enforcement and OpenCCA folds `Realm PAS` into `NS PAS` at the
translation layer.

```text
run: GPU-SFTP/log/passthrough/perf/trusted-gpu-realm-host-deny-20260718-185436
selected_hpa=0x000000003573a000
COMPUTE_CHECK=PASS
realm_host_access_probe: HOST_READ_SUCCEEDED hpa=0x3573a000 ...
```

The design-level Host denial claim is therefore checked from the simulated
`GPT/GPC` model rather than by forcing Linux to reject the mapping. Use:

```bash
scripts/check/check-opencca-gpt-design-denial.sh
```

This check verifies the RMM-to-EL3 `GTSI_DELEGATE` path, the TF-A GPT model's
`GPT_GPI_REALM` transition, and the RK3588/OpenCCA caveat that `GPCCR_EL3` and
`GPTBR_EL3` are spoofed while `Realm PAS` is folded to `NS`.

## Memory Lifecycle

The intended mapping sequence is:

```text
1. Realm allocates a private BO or GPU page-table page.
2. Host delegates its backing granule; GPT marks it Realm.
3. Guest calls RSI_OPENCCA_GPA_TO_HPA with the Realm IPA.
4. RMM walks the current Realm RTT and verifies that the IPA belongs to it.
5. RMM returns the HPA and records a Realm-local mapping lease.
6. Guest writes that HPA into the Mali page table and cleans CPU caches.
7. Mali reads or writes the HPA directly.
8. Guest quiesces GPU work, invalidates the Mali mapping, and releases the
   mapping lease through RSI_OPENCCA_GPU_REVOKE.
9. Realm teardown drops all remaining leases before the RD is destroyed.
```

`GPU_REVOKE` is retained as the existing experimental RSI ABI name. It now
releases RMM bookkeeping only; it does not change GPT state or revoke a
hardware GPU permission.

## RMM Responsibilities

`opencca/tf-rmm/runtime/rsi/opencca_gpu.c` is the trust-boundary component for
address disclosure:

- validate the exchange array as an IPA in the calling Realm;
- walk every requested IPA through the current Realm's RTT;
- return only an HPA backed by that Realm mapping;
- reject the same active HPA being associated with a different RD;
- refcount repeated mappings and clean all records on Realm destruction.

The mapping table is a lifetime and ownership check. It is not an access-control
table consumed by Mali. RMM no longer sends GPU grant/revoke SMCs to EL3, and
TF-A does not maintain a parallel trusted-GPU grant table for this direct path.

## Guest Panthor Responsibilities

The Realm guest keeps BO payloads and GPU page tables private. It does not call
`set_memory_decrypted()` for the direct path.

`Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c` translates Realm GPAs through
RMM before publishing Mali PTEs. Since Mali walks those page tables itself, all
table descriptors and leaf entries visible to Mali must contain HPA values,
not guest IPA values.

The driver must also maintain non-coherent cache visibility:

- clean command buffers, page tables, and CPU-produced BO data before submit;
- invalidate CPU caches before reading GPU-produced sync objects or BO data;
- publish PTEs before issuing the relevant Mali MMU/TLB operation;
- drain queues and invalidate GPU translations before freeing backing pages.

The private RSI exchange page is read and written by RMM through its protected
mapping helpers; it is not converted to Host-shared memory.

## MMIO And Interrupts

GPU MMIO remains a non-secure device aperture. A Realm guest accesses it through
the shared IPA alias, and Host KVM installs that alias with
`RTT_MAP_UNPROTECTED`. This is separate from GPU buffer memory:

```text
GPU registers: shared/unprotected device mapping
GPU buffers:   private Realm granules
```

The existing three GPU IRQ routes can remain attached to the Realm VM. Current
diagnostics show that IRQ delivery and CS scheduling are active enough to debug
the memory path.

## Security Boundary

Architectural GPT should protect Realm granules from direct Host CPU loads and
stores. On this RK3588/OpenCCA branch that property is a design/model property:
the GPT library can transition granules to `GPT_GPI_REALM`, but the hardware
does not consume that state as a real GPC fault. GPT also does not constrain
Mali DMA in this design. Consequently, the following additional condition is
mandatory if a malicious Host is in the threat model:

```text
After assignment, Host software must not be able to program GPU MMIO, submit
command streams, replace Mali page tables, or reset/reclaim the GPU until RMM
has ended the Realm assignment.
```

Otherwise the Host can program the unrestricted GPU to read Realm HPAs and use
it as a DMA oracle, bypassing the CPU-side GPT denial. Detaching the Host Panthor
driver is operational exclusivity, but by itself does not defend against a
malicious Host kernel. Strong Host-adversary protection needs a trusted device
control plane, for example EL3/RMM-owned assignment and MMIO mediation.

The current implementation target is therefore precise, and the demonstrated
properties should be stated with this boundary:

- **Demonstrated functional property:** Realm CPU and Mali can access Realm GPU
  memory through RMM-validated HPA-backed Mali page tables.
- **Design/model property:** simulated GPT transitions delegated granules to
  `GPT_GPI_REALM`, which is the intended reason Host CPU access is denied in
  an architectural CCA platform.
- **Not architecturally achieved on RK3588/OpenCCA:** hardware `GPT/GPC` Host
  CPU denial for live Host loads/stores; runtime Host probes can still read.
- **Deployment property:** one Realm owns the whole GPU during a run.
- **Not yet proven:** a malicious Host cannot reprogram Mali to DMA Realm
  memory.
- **Not supported by this model:** mutually distrusting Realms sharing one GPU
  concurrently without an SMMU or trusted scheduler.

## Hardware Status On 2026-07-18

The current Host kernel maps the 2 MiB GPU aperture as:

```text
Realm shared IPA 0x40fb000000 -> NS HPA 0xfb000000
RMI_RTT_MAP_UNPROTECTED, Device access selected by guest Stage-1 attributes
```

The following path is verified with one Realm vCPU and 512 MiB RAM:

- all three GPU IRQs attach to GSIs 92-94;
- the Realm reads G610 ID `0xa867` and the expected feature registers;
- GPA-to-HPA RSI translation supplies HPA leaves to the Mali page tables;
- CSF firmware v1.1.0 is parsed and initialized;
- Panthor scheduler and DRM render node initialization complete;
- the Realm reaches a shell and the Host remains responsive.
- Mesa reports `Mali-G610 (Panfrost)` and OpenGL ES 3.1;
- a 4096-element compute dispatch returns `COMPUTE_CHECK=PASS`;
- `scripts/check/check-opencca-gpt-design-denial.sh` returns
  `DESIGN_GPT_HOST_DENIAL_CHECK=PASS`.

A 4 KiB-only MMIO diagnostic also reads the real GPU ID, then fails later when
Panthor needs registers outside the first page. This confirms that the old
whole-Host hang was caused by running an older Host kernel whose custom MMIO
ioctl used the normal KVM Stage-2 mapper even for a Realm. It was not caused by
GPC, GPU IRQ attachment, or a 2 MiB RMI block descriptor.

The initial `EGL_NOT_INITIALIZED` result was a test-environment error: the
minimal `init=/bin/sh` configuration had not mounted `/proc` and `/sys`, so
Mesa could not correlate the DRM card and render nodes through sysfs. Mounting
those filesystems made EGL initialize and the compute check pass. The earlier
first-submit cache-clean fix is therefore functional for this minimal job, but
larger repeated workloads and teardown/error paths still need coverage.

Do not add another EL3 grant predicate to solve a data-path symptom: unless a
real Mali transaction consumes that predicate, it is bookkeeping rather than
an enforcement or visibility mechanism.

The Host read-success result shows why this cannot be called a hardware GPT/GPC
fix. In the current tree,
`opencca/trusted-firmware-a/lib/xlat_tables_v2/aarch64/xlat_tables_arch.c`
contains an OpenCCA path that treats `Realm PAS` as `NS`, and
`opencca/trusted-firmware-a/opencca/include/opencca.h` uses dummy accessors for
`GPCCR_EL3/GPTBR_EL3`. The repository therefore records Host denial as a
design/model check, not as a runtime hardware-enforced property on RK3588.

## Controlled Smoke Gate

Firecracker continues to reject `realm_config` together with
`gpu_passthrough=true` unless the process explicitly sets:

```text
FC_ALLOW_TRUSTED_GPU_REALM=1
```

The repository runner exposes this through
`--vm-realm-trusted-gpu-experimental`. This gate limits accidental use while
the data path and GPU control-plane boundary are still experimental.

Firecracker also has default-off diagnostic switches:

```text
FC_TRUSTED_GPU_REALM_SKIP_IRQ=1
FC_TRUSTED_GPU_REALM_SKIP_MMIO=1
FC_TRUSTED_GPU_REALM_MMIO_4K=1
```

Run serial diagnostics directly on a PTY. Piping Firecracker through `tee` can
buffer Guest serial output and produce a false impression that the REC did not
start.

For a minimal `init=/bin/sh` rootfs, mount kernel filesystems before running
Mesa:

```sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
```
