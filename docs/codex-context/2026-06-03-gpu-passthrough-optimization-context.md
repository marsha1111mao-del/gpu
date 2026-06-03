# Codex Context - GPU passthrough optimization lessons

Date: 2026-06-03
Root workspace: `/home/mzh/gpu`

## Purpose

This note records high-level lessons from the recent Mali/Panthor GPU
passthrough optimization cycle: optimize code, run host-vs-VM tests, inspect
stage timings, keep useful changes, and remove ideas that did not survive real
workload testing.

This is intentionally not a code-level changelog. For detailed patches, test
commands, and numerical runs, use:

- `/home/mzh/gpu/docs/passthrough/GPU_PASSTHROUGH_OPTIMIZATION_LOG.md`
- `/home/mzh/gpu/docs/passthrough/GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md`

## Testing Principle

The performance target should be a real GPU task lifecycle. A representative
measured iteration should include CPU-side prepare, buffer upload, one GPU
submission, result wait/map, and unmap. Tests that repeatedly submit the same
already-prepared task can hide the costs that real applications actually pay,
so they should not guide the main optimization direction.

The stable comparison shape is currently:

- 4 MiB, 16 MiB, and 64 MiB workloads.
- Host and VM tested with comparable userspace/rootfs conditions.
- Formal runs without heavy tracing.
- Separate VM-only diagnostic runs when attribution is needed.

## Useful Optimizations

Hot-path logging can dominate this project. Printing inside KVM, VGIC,
resample, IRQ, and GPU completion paths is often more expensive than the thing
being measured. Default-off counters or aggregated timing are much safer than
per-event printk.

GPU page-table mapping batching is a real win. The useful direction is reducing
per-page overhead and keeping map/unmap work coarse where correctness allows.
The 2 MiB block path is conceptually valuable, but current tests often fall
back because the translated HPA base is not aligned enough for a true block
mapping. That means the next 2 MiB improvement is more about allocation/backing
alignment than about only changing the PTE writer.

Batch GPA-to-HPA translation is worth keeping, especially the host-side
in-place guest array handling. It removes avoidable guest-memory copy overhead.
However, after batching, HVC translation is no longer the only or dominant
metadata cost in the measured path. Future work should avoid assuming that
"fewer HVC calls" alone will fix the remaining overhead.

Changing the Panthor scheduler workqueue from unbound to bound helped. In
contrast, making the scheduler path aggressively high-priority or trying to
force raw IRQ shortcuts did not become a stable improvement. For this workload,
predictable CPU locality was more useful than simply increasing priority.

Faster deployment matters for iteration speed. For passthrough performance
work, building and deploying the single normal Image is usually enough. The
vmshm proxy/client kernels should not be rebuilt unless that path is being
tested. Host deployment should prefer Image-only or selected-module syncs;
full module install/sync is expensive and should be reserved for cases where
module changes truly require it.

## Rejected Directions

The main lesson from the discarded buffer-lifetime experiments is to avoid
optimizing for narrow repeated-task scenarios. They can make controlled tests
look faster while moving away from the real application cost model. Future
changes should be judged against the full task lifecycle unless there is a
separate, explicit diagnostic reason to isolate one mechanism.

Guest IRQ hardirq fast paths, raw ACK/prequeue experiments, raw unmask HVC from
guest IRQ, guest IRQ thread boosting, Firecracker nice-level tweaks, and
`nohlt cpuidle.off=1` were not stable wins. Some helped one case briefly, but
regressed other sizes or introduced semantic risks such as duplicate unmask or
resample behavior.

CPU and IRQ affinity are useful diagnostic controls, but not yet a universal
default. They can help isolate scheduling effects, but they should be validated
per workload before being treated as an optimization.

## Bottleneck Map

For 4 MiB workloads, fixed costs dominate. Completion wait and map/fence wait
matter disproportionately, so even small host masked/resample/EOI tails or
Mesa/fence wait behavior can outweigh pure GPU execution time.

For 16 MiB workloads, the path is mixed. Metadata cost and completion wait both
matter, so a single optimization rarely explains the full result. This size is
useful for catching changes that help throughput but hurt latency, or vice
versa.

For 64 MiB workloads, metadata and data movement dominate more visibly.
Completion tends to be closer to host behavior, while CPU upload, Mesa/DRM
setup, BO creation, VM_BIND/page-table work, and translation overhead shape
most of the VM tax.

Recent VM-only timing suggests the guest IRQ thread itself is not the main
completion bottleneck: guest raw-to-thread latency and handler body time are
small compared with the total completion wait. The more plausible completion
sources are host-side masked/resample/EOI long tails and userspace fence wait
behavior.

## How To Interpret Tests

Formal host-vs-VM runs answer "did performance improve?" Diagnostic timing
runs answer "where did the time go?" Do not mix the two too casually, because
instrumentation changes the timing profile.

A good test pass should report:

- Overall host and VM averages for 4/16/64 MiB.
- VM overhead or host/VM ratio.
- Stage shares: metadata, dispatch, completion/wait.
- Page-table/HVC timing when investigating metadata.
- Host and guest IRQ stats when investigating completion.

The important comparison is not only the absolute average. Watch whether an
optimization moves time from one stage to another, improves one workload size
while regressing another, or only helps an unrealistic repeated scenario.

## Current Direction

The most promising next work is better attribution inside the real metadata
path. Split costs above and around page-table mapping: CPU prepare, buffer
upload, Mesa BO metadata, DRM ioctl path, Panthor BO create, VM_BIND, page-table
population, and GPA-to-HPA translation.

For completion, split beyond "IRQ latency" into userspace fence wait,
scheduler completion, KVM irqfd delivery, VGIC resample/EOI, and host masked
time. The current evidence says completion loss is not explained by guest IRQ
thread scheduling alone.

If real 2 MiB GPU block mappings are pursued again, solve physical alignment
first. The current fallback behavior shows that the blocker is often HPA
alignment of the backing memory, not only the lack of a block-PTE writer.

The general rule from this cycle: optimize the actual GPU task lifecycle,
measure by workload size, keep changes that improve realistic paths, and delete
clever mechanisms that only win under artificial repetition.
