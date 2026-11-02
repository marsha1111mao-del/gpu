# ProxyClient general performance optimization exploration

This document tracks performance candidates tested after the 1158-point
single-Client complete 720p baseline. A candidate is retained only after a
comparable full 720p run improves the score by at least 2-3%, while glmark
validation, all 33 scenes, kernel health, VM exit and resource recovery remain
correct. Failed candidates are reverted completely and remain listed here to
prevent unchanged retries.

## Original comparison baseline

| Item | Value |
| --- | --- |
| Score | 1158 |
| Run ID | `request-coalesce-us0-720-20261024-a` |
| Resolution / scenes | 1280x720 / 33 |
| Validation | 26 success / 1 known failure / 6 unknown |
| Client count | 1 |
| Client/Proxy CPU | fixed 1.8 GHz |
| GPU | selected 600 MHz, actual 594 MHz |
| Shared pool | compact 128 MiB |
| Placement | round-robin |
| Optional paths | telemetry and TRANSFER capture enabled |

Current retained local baseline is1405 (bounded raw native fence observation,
A/B1406/1404), with the same conditions above. Six designs qualify:
resident request wake1158->1182,+24/+2.07%; the complete ownership combination
1182->1208,+26/+2.20%; target-side direct return1208->1237,+29/+2.40%;
joint native handoffs1237->1267,+30/+2.43%; prefix-proven native callbacks
1267->1311,+44/+3.47%; bounded raw completion1311->1405,+94/+7.17%.
Cumulative1158->1405,+247/+21.33%. The fifth and sixth designs are two
independently retained results after the request to keep exploring; the
earlier four are not counted again. Next2% integer gate1434.
The fourth design's second run alone improved1.86%; the predeclared gate uses
the repeated mean, not a claim that every run exceeds2%. Each has full720p repeats and selected
dualClient API/compute plus GEMM/conv correctness validation. See the
[first retained design](GPU_RESIDENT_REQUEST_WAKE_20261024.md) and the
[new combined design](GPU_PIPELINE_OWNERSHIP_OPTIMIZATION_20261024.md), and
[third design](GPU_TARGET_IRQ_RETURN_OPTIMIZATION_20261024.md), and
[fourth design](GPU_NATIVE_HANDOFF_OPTIMIZATION_20261024.md).
The [fifth design](GPU_FENCE_CALLBACK_OPTIMIZATION_20261024.md) additionally
passed1000 real kernel fence-chain cases and both Clients' snapshot/timeline
reset/import/destroy/recreate checks; actual source/runtime/firmware audited.
Each combined design is one success; its earlier standalone subthreshold
components below remain historically rejected, not independently qualified.
The following rejected candidates were compared to the original1158 unless
an entry explicitly names the newer baseline.

## Second new retained design: bounded early native completion

Purpose | Shorten the critical delay from Guest raw JOB IRQ to publication of
real fence completion. Preserve original device masking, IRQ thread and full
ACK/drain/unmask. Only Realm managed GPUVMs enter the bounded atomic observer;
real synchronized counters, successful status, trylocks and strong references
are mandatory. Release completed jobs in process context. No polling loop,
synthetic completion, frequency/priority change or new RPC protocol.

Comparison | Retained1311 ->1406/1404,mean1405,+94/+7.17%,both above1338.
Same complete720p/33scenes,1Client/128MiB/CPU1.8GHz/GPU594MHz/round-robin,
telemetry/TRANSFER and all timing off. OnlyProxy Image changed. Both runs
validation26/1/6,VM0/0,health/restoration and VERIFIED11 files; wrapper/runner
rc0. The repeated per-scene means show30higher/3equal/0lower,descriptive only.
Raw-completed jobs547491/547954; physical JOB IRQ1108535/1109917. This is a
latency-path optimization,not evidence of fewer IRQs or an isolated timing gain.

Qualification | DualClient each18API and actual GPU compute,permissions/IRQ/
memory,snapshot/timeline reset/import/destroy passed; GEMM/conv correctness
29.28419/33.63555ms passed,without ML speed claims. Those runs exercise raw
completion73/210times; VM0/0/0 and0/0,health/restoration,wrapper/runner rc0 and
10verified files each. Four runs42files. Final exclusive audit
`raw-fence-observation-final-audit-20261024-a` rc0 verifies exact source/full
Guest diff,unchanged callback helper,RMM/Root,SGI module,actual SD firmware
and boardProxy SHA,with no workload/mount/loop/module left active.

Decision | Retain1405 as the new local baseline; continued goal now has two
new independently qualifying designs. Frozen bundle,patches,hashes,review,
build/logs/audits and NOT_RUN scope are in
`build/raw-fence-observation-20261024/`; portable summary and evidence links:
[raw completion report](GPU_RAW_FENCE_COMPLETION_OPTIMIZATION_20261024.md).
1311 remains rollback. No commits/pushes or new Host/firmware deployment.

## Reverted candidates

### Demand-driven firmware CSG idle IRQ notification

Purpose | Mask only CSG_IDLE for one resident group without runnable/blocked
competitors; restore at each scheduling tick and force an immediate fresh-status
tick for a new nonresident group. Retain real completion/fault/progress and
global idle/PM,original ACK/cache/doorbell paths. This changes notification
generation rather than merely deferring idle work.

Comparison | Retained1311 ->1313,+2/+0.15%, below1338. Run
`selective-idle-irq-720-20261024-a`,wrapper/runner rc0,33scenes,
validation26/1/6,VM0/0,health,no ring wrap,restoration and VERIFIED11files.
OnlyProxy changed; same720p/1Client/128MiB/CPU1.8GHz/GPU594MHz/round-robin,
telemetry/TRANSFER,all timing off. 69mask updates,0restore updates,
515303masked idle events observed on other notifications. Actual physical JOB
IRQ1039090 versus retainedA1041586; no large IRQ reduction. Competition/restore
branch and separate PM timing NOT_RUN. No repeat/API/ML; exact source/helper
and boardProxy restored1311 under `selective-idle-irq-rollback-20261024-a`.
Full argv,patches,hashes,build/raw evidence,audit and rollback:
`build/selective-idle-irq-20261024/report.md`. Do not retry unchanged.

Historical count correction | Existing SGI-wrapper Host /proc/interrupts logs
prove the earlier idle-tick deferral DID reduce physical JOB IRQ1041586->544487
and IRQ/plan2.026->1.028,while scoring only1320(+0.69%). This newly extracted
historical evidence supersedes the earlier statement that no physical-IRQ
reduction had been demonstrated. It is not a rerun or proof of critical
latency savings; extraction is in the above experiment's
`historical-physical-irqs.json`.

### Direct-fence capture piggybacked on PLAN_EXEC

Purpose | Combine removal of the follow-up TRANSFER RPC with lazy native
snapshot materialization. Retain the exact complete real fence and shared
observer; use session capabilities, epoch/sole-writer checks and bounded
retirement. Unlike old eager PLAN capture, no native syncobj is allocated on
the normal submit path; unlike standalone direct-fence capture, no second RPC
is needed for an exact matching binary transfer.

Comparison | Retained1311 ->1304,-7/-0.53%, below1338. Run
`direct-plan-snapshot-720-20261024-a`,wrapper/runner rc0,33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,restoration and
VERIFIED11files. Same720p/1Client/128MiB/CPU1.8GHz/GPU594MHz/round-robin,
telemetry/TRANSFER and disabled timing; Client and Proxy changed.

Evidence | 511144 exact local transfers,0misses/0capture failures;3083 native
materializations and31deferred Client materializations. The boundary was
removed but did not yield a qualifying score; no isolated overlap/latency
measurement. No repeat/API/ML. Exact Guest diff/helper and board Client/Proxy
restored1311 under `direct-plan-snapshot-rollback-20261024-a`. Full argv,
source/input hashes,builds,patches,evidence,audit and rollback:
`build/direct-plan-snapshot-20261024/report.md`. Do not retry unchanged.

Historical checkpoint before the newer experiments: the three candidates below were each tested once and
reverted after missing1338. Independent final audit
`optimization-exploration-final-audit-20261024-b` exited0 after verifying the
exact retained1311 Guest diff/untracked fence helper, RMM/Root source, actual
SD firmware and boardProxy SHA; no workload, mount/loop or module was left
active. The retained combination's original four qualification runs were
re-audited; they were not rerun. Aggregate evidence:
`build/uncontended-idle-tick-20261024/exploration-checkpoint.json` and
`retained-final-audit.json`. The new doubleClient ML baseline is recorded
separately below. No additional qualifying design this checkpoint; new-success
count remains1, so the continued2–3-design goal is still active. Shared Proxy
build cache contains the last rejected candidate; rebuild before a new freeze.

### Defer group-idle scheduling while no competitor exists

Purpose | Keep the firmware idle event/ACK and might_have_idle_groups hint;
defer its immediate scheduling tick only when all runnable lists and the
blocked-waiter list are empty. Existing800us global idle still requests the
PM/accounting tick; new runnable groups force a tick through the retained hint.
Competition, faults, progress timeout, destruction/reset and fence handling
retain their original paths. No frequency/poll/priority changes.

Comparison | Retained1311 ->1320,+9/+0.69%, below1338 gate. Run
`uncontended-idle-tick-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resources restored and
VERIFIED11-file collection. OnlyProxy changed; same full720p/1Client/128MiB,
CPUperformance1.8GHz/GPU594MHz,round-robin,telemetry/TRANSFER and diagnostics
off. Deferred529687 idle-tick requests,required0. IRQ-tail attempts changed
from retained A516890direct/524690deferred to537012/7469, but these are not
physical IRQ counts or critical waits saved. Fewer handoffs did not establish
enough overall benefit. Competition branch and separate runtime autosuspend
instrumentation NOT_RUN; no repeat/API/ML after failed gate.

Decision | Exact source/Guest diff/fence helper restored1311; boardProxy
restored under `uncontended-idle-tick-rollback-20261024-a`,rc0,SHA/resources
verified. Full argv,patch/build/hash/evidence/audit and rollback:
`build/uncontended-idle-tick-20261024/report.md`. Do not retry unchanged.

### Observe genuine completion while scheduler mutex is busy

Purpose | Protect slot/group reference acquisition with a short independent
spinlock; on busy scheduler mutex, observe the same real GPU counters and
complete native fences outside both locks. Keep all pending firmware bits and
the original worker for ACK, fault/idle handling and scheduling. Strong refs
and the existing group completion mutex protect unbind/destroy races.

Comparison | Retained1311 ->1317,+6/+0.46%, below1338 gate. Run
`busy-scheduler-completion-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resources restored and
VERIFIED11-file collection. OnlyProxy changed; same full720p/1Client/128MiB,
CPUperformance1.8GHz/GPU594MHz,round-robin,telemetry/TRANSFER and diagnostics
off. 538791 busy-path group observations prove activation, not critical waits
or actual completed jobs saved. No repeat/API/ML.

Decision | Exact source and Guest diff restored1311; boardProxy restored with
SHA/resources verified under `busy-scheduler-completion-rollback-20261024-a`,
rc0. Full argv,patches,build/hash/evidence/audit and rollback:
`build/busy-scheduler-completion-20261024/report.md`. Do not retry unchanged.
Upstream Panthor [independent event lock](https://github.com/torvalds/linux/commit/e6187c990af2ce2c9eaee7826be9182938d815df)
motivated reference acquisition; its full spinlocked event processing was not
transplanted because our Realm cache maintenance may sleep.

### Process completion inside the masked JOB IRQ drain

Purpose | Move the existing post hook from after unmask to each status batch
inside the threaded drain. Keep physical masking, hardIRQ/thread separation,
real ACK/cache/fence and scheduler trylock fallback; this is distinct from P18.

Comparison | Retained1311 ->1313,+2/+0.15%, below1338 gate. Run
`masked-completion-drain-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resource restoration and
VERIFIED11-file collection. OnlyProxy changed; same full720p/1Client/128MiB,
CPUperformance1.8GHz/GPU594MHz,round-robin,telemetry/TRANSFER and diagnostics
off. Direct516509/deferred524381 attempts do not establish reduced IRQ count
or a latency gain.

Decision | Reverted exact header and retained1311 Guest diff. BoardProxy
restored to exact1311 under lease `masked-completion-drain-rollback-20261024-a`,
rc0, SHA and resources verified. No repeat/API/ML. Exact argv, builds,
isolated/full patches, source/input hashes, audits, evidence and rollback:
`build/masked-completion-drain-20261024/report.md`. Do not retry unchanged.

### Skip scheduler-wide sync scans while no group is waiting

Purpose | Under the existing scheduler mutex, skip CSG-event global sync
scan queueing when groups.waiting is empty. Pair this with a scan request
after suspended-queue wait metadata is fully captured, so an older completion
event cannot be lost before a newly discovered waiter is inserted. Leave
termination/reset producers, per-group completion and real fences unchanged.

Comparison | Retained1311 ->1320,+9/+0.69%; independent2% gate1338 missed.
Run `no-empty-sync-work-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resource restoration and
VERIFIED11 collection. Counter empty-scan skips517438, waiting-list scan
requests0, suspended-waiter rechecks0. The hot empty-list guard activated;
the nonempty/recheck branches were not exercised by this workload. Counts
are suppressed queue attempts, not actual avoided worker executions, since
workqueue may already coalesce requests. The small single-run gain does not
establish a stable performance improvement or qualify for retention.

Conditions | OnlyProxy changed from1311; same full720p/1Client/128MiB,
CPU1.8GHz/GPU594MHz/round-robin,telemetry/TRANSFER and disabled timing.
Proxy build rc0 without warning/error. No Host/firmware change.

Decision | Reverted the one source file and verified full Guest tracked diff
plus retained callback helper hashes exactly match1311. Board rollback
`no-empty-sync-work-rollback-20261024-a` restores the1311 Proxy. No repeat,
API/ML expansion or claimed waiter-race integration coverage. Command,
Image/sourceSHA,patch,raw logs,audit and runtime restoration record are in
`build/no-empty-sync-work-20261024/`. Do not retry unchanged.

### Firmware completion processing at submit-thread tail

Purpose | After reservation cleanup and release of inline dispatcher locks,
try the same pending firmware-event processing used by the retained IRQ tail.
The hypothesis was that an IRQ arriving while submit owns the scheduler mutex
could otherwise defer its completion work. Lock-busy paths keep the worker;
real fences, references, reset and ownership checks remain unchanged.

Comparison | Retained1267 ->1262,-5/-0.39%; independent2% gate1293 missed.
Run `submit-tail-events-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resource restoration and
VERIFIED11 collection. Submit-tail direct12303/deferred1194, IRQ-tail
direct502242/deferred506760 and fast returns1058034 confirm activation.
These counters do not measure saved latency; the small one-run score change
does not establish a significant regression. OnlyProxy changed; the other
1267 inputs and full720p/128MiB/CPU1.8GHz/GPU594MHz/round-robin,
telemetry/TRANSFER and disabled timing diagnostics matched.

Decision | Reverted all three changed source files to the exact1267 full
Guest diff. Board Proxy restored by `submit-tail-events-rollback-20261024-a`,
rc0 and baselineSHA verified. No repeat/API/ML expansion. Command, ImageSHA,
patch, logs, audit and rollback are in `build/submit-tail-events-20261024/`.
Do not repeat unchanged.

### Opportunistic completed-job retirement before inline dispatch

Purpose | Under the existing dispatcher trylock, cancel pending free-job work,
retire at most one genuinely completed job with the original get_finished and
free_job helpers, requeue any remaining completed jobs, then dispatch normally.
Preserve real fences, credits, dependencies, stop/reset and reference ownership.
No pending-job counter, hardIRQ freeing or earlier completion was introduced.

Comparison | Retained1267 ->1256,-11/-0.87%; independent2% gate1293 missed.
Run `inline-job-retirement-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resource restoration and
VERIFIED11 collection. Actual inline-retirement marker confirms activation;
it is not a count or isolated timing measurement. OnlyProxy changed; other
1267 inputs, firmware,720p/128MiB/CPU1.8GHz/GPU594MHz/round-robin,
telemetry/TRANSFER and disabled timing diagnostics matched.

Decision | Reverted the single changed source file; complete Guest diff
matches retained1267. No repeat/API/ML expansion. First build failed because
the one-time marker used a DRM-device macro on struct device; corrected to
dev_info_once and rebuilt rc0 without new warnings. Both build logs retained.
Full command,Image/sourceSHA,patch,health audit and board rollback evidence:
`build/inline-job-retirement-20261024/`. Do not repeat unchanged.

History review also rejected a proposed runnable-aware5us RX polling retry
before implementation. The existing8us Proxy RX poll already regressed
1167->1125(-3.60%), alongside archivedP5's318->296. A shorter window and
runnable guard alone do not establish a distinct critical-path benefit.
No code or test was added for that proposal; notes are in
`build/guarded-rx-poll-20261024/design.md` and the earlier
[RPC critical-path report](GPU_RPC_CRITICAL_PATH_20261022.md).

### IRQ-thread tail completion

Purpose | Keep original JOB hardIRQ/thread, status drain and device masking;
after unmask, trylock scheduler events and complete referenced groups in the
same IRQ thread. Busy/reset paths retain the worker. Real fences, cache
maintenance, group refs and owner checks remain. This differs from P18's
hardIRQ execution and earlier unmasking.

Comparison | Retained1237 ->1252,+15/+1.21%, below1262 gate. Run
`irq-tail-completion-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6,VM0/0,Host/Guest health,no ring wrap,resource recovery and
VERIFIED11 collection. OnlyProxy changed; exact final1237 Client/initrd/
runner/SGI15 and firmware,720p/128MiB/CPU1.8GHz/GPU594MHz,round-robin,
telemetry/TRANSFER and diagnostics off. Direct503047/deferred496718 events
prove activation, not isolated latency savings. No repeat/API/ML expansion.

Decision | Five candidate files reverted to exact final1237 Guest diff,
boardProxy restored under lab lease. Full argv,build/source/Image hashes,
audit and rollback evidence: `build/irq-tail-completion-20261024/report.md`.
Do not retry unchanged. The later joint submission/completion handoff
experiment qualified as one combination with1274/1260 and selected correctness;
this standalone result stays failed. Source and runtime now contain that
validated whole combination, rather than the historical standalone candidate.

### Direct-fence private snapshots with lazy native handles

Purpose | TRANSFER_CAPTURE retains the exact complete native dma_fence in
the Proxy snapshot, letting its watcher use that reference directly. Create
a native DRM syncobj only for subsequent wait/query/transfer/VM-bind/plan
operations that actually require a native handle. Keep immutable snapshots,
native destination transfer, errors, owner checks and RPC count unchanged.

Comparison | Retained1237 ->1249,+12/+0.97%; integer2% gate1262 missed.
Run `direct-fence-snapshot-720-20261024-a`, wrapper/runner rc0, full33scenes,
validation26/1/6, VM0/0, Guest/Host health without dmesg wrap, resource recovery
and VERIFIED11 collection. Only Proxy Image changed; final1237 Client,
initrd, runner, SGI15 module and actual SD firmware matched. Same CPU1.8GHz,
GPU594MHz,128MiB compact pool, round-robin, telemetry/TRANSFER and disabled
phase/notify/completion diagnostics. One run does not prove stable speedup.

Mechanism | 492280 captures,2222 lazy materializations: native snapshot
creation was avoided for99.55% of captures. This removes more fence/table
work than the earlier handle pool, yet still does not meet the score gate.
Do not attribute the single-run12-point difference to any individual change.

Decision | Reverted all three candidate files to the exact1237 Guest patch;
no repeat/API/ML expansion. Full argv, Image/source SHA, build log, native
handle-consumer review, collection/audit and runtime rollback evidence are
in `build/direct-fence-snapshot-20261024/`. Do not retry unchanged. Follow-up
measurement will profile the retained1237 path because the historical81us
PLAN_EXEC breakdown predates the three retained optimizations.

### Receiver-negotiated rearm at trusted IRQ delivery

Purpose | RMM acknowledges/rearms opted-in receiver channels when taking a
pending trustedIRQ; Proxy acquire-drains/rechecks without another ACK_ARM
RSI. Manual channels,Clientreply,owner and realfence checks remain unchanged.

Comparison | Retained1208 ->1205,-3/-0.25%;2% gate1233 missed. One run does
not establish stable regression. delivery-rearm-720-20261024-a,wrapper/
runner rc0,33scenes,validation26/1/6,VM0/0,Host/Guest health PASS,no ring
wrap,resource recovery and VERIFIED11collection. enabled=1 confirms use.
Same720p/128MiB/CPU1.8GHz/GPU594MHz; Proxy and RMM changed; actualRootBL31,
Host,Client/initrd/runner and RMM options match retained inputs.

Decision | All candidate source reverted to exact1208Guest/RMM patches;
retained source/selected evidence re-audited. New ASan/UBSan state-machine
tests and RMM/Proxy/U-Boot builds passed, but no repeat/API/ML expansion for
the failed gate. Exact command,SHA,evidence and firmware/runtime rollback
records: build/delivery-rearm-20261024/report.md. Do not retry unchanged.

### Inline ready native job dispatch

Purpose | Run the existing DRM ready-job dispatcher in the submitting Proxy
thread after reservation cleanup, preserving dependencies/credits/fences and
serializing ordinary run/free workers. Distinct from the older flush_work
handoff experiment.

Comparison | Retained1208 ->1219,+11/+0.91%; first-run2% gate1233 missed.
Run inline-native-dispatch-720-20261024-a, wrapper/runner rc0, full33scenes,
validation26/1/6, VM0/0, Host/Guest health and resource recovery. Eleven files
collected withSHA verification; actual inline dispatch marker present.
Same720p/128MiB/CPU1.8GHz/GPU594MHz; Proxy alone changed.

Decision | Three-file candidate reverted; fullGuestdiff exactly matches the
retained1208 patch. No repeat/API/ML expansion. Command, hashes, build logs,
frozen candidate and evidence: build/inline-native-dispatch-20261024/report.md.

### Per-writer firmware CS input publication

Purpose | Replace each CSG doorbell's whole-CS input scan with exact
publication at program/heap/reset/fault acknowledgment writers, preserving
real DMA maintenance and child-before-parent ordering.

Comparison | Resident1182 ->1186,+4/+0.34%;2% gate1206 missed.
cs-input-publication-720-20261024-a,wrapper/runner rc0,33scenes/26-1-6,
VM0/0,Guest/Host health PASS,no ring wrap,VERIFIED11 and resource recovery.
Same full720p/128MiB/CPU1.8GHz/GPU594MHz conditions; Proxy alone changed.

Decision | Standalone source reverted. Earlier archival P22 also tested this
principle with no gain; do not retry it alone. No API/ML expansion or per-call
latency claim. Evidence and exact command: build/cs-input-publication-20261024/report.md.

### Managed native ownership plus identical-fence observers

Purpose | Combine managed root-only reservations, precise kernel-BO ownership,
aligned live cache-maintenance ranges and refcounted observers shared only
after actual complete native fence pointer equality.

Comparison | Retained1182 ->1199, +17 /+1.44%; below2% gate1206.
Main session executed471659 plans and reused471625 fence observers, confirming
coverage without demonstrating sufficient end-to-end gain. Full720p/33scenes,
validation26/1/6, wrapper/runner rc0, VM0/0, Host health PASS and VERIFIED11
collection. Conditions match retained resident baseline; Proxy alone changed.

Decision | Entire combination reverted, resident support preserved. No
component percentage or ML speedup claim. Do not retry unchanged; the existing
GEMM512/conv tests are GPU-dominated and were not rerun merely to search for a
passing metric. Command and evidence: build/managed-completion-ownership-20261024/report.md.

### Proxy receive high-priority workqueue

Purpose | Preserve the bounded hard IRQ callback and coalesced workqueue drain,
but move Proxy request receive work from `system_wq` to `system_highpri_wq`.
Earlier tracing measured IRQ-to-worker at 9.910 us mean / 36.750 us p95, so
this tested a bounded scheduling target without repeating direct IRQ handling.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1146
(`highpri-rx-720-20261024-a`), -12 points / -1.04%.

Evidence | Client/initrd/runner were byte-identical; only Proxy changed. The
wrapper and runner returned 0, all 33 scenes completed, validation was 26/1/6,
VM exits were 0/0, kernels were clean, and resources were restored. Plan
executions fell from 457,424 to 449,983; most submit-sensitive scenes declined
by 0.5-2%, with larger losses in terrain and refract.

Decision | Reverted. High priority cannot remove the larger Realm/Host notify
path and may compete with the normal-priority native GPU work enabled by the
receiver on the one-vCPU Proxy, but that cause is not independently isolated.
Do not retry the plain priority substitution. Full evidence is in
`build/highpri-rx-20261024/report.md`.

### Threaded event IRQ with direct queue drain

Purpose | Replace the hard-IRQ-to-system-workqueue path with a minimal hard
handler, an `IRQF_ONESHOT` IRQ thread, and direct queue draining in that
thread, removing one scheduler handoff without restoring QUERY SMC.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 930
(`threaded-irq-direct-720-20261024-a`), -228 points / -19.69%.

Evidence | The wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, kernels were clean, and resources
were restored. Proxy/Client event IRQs decreased from 991,035/7,036 to
800,066/4,649 because frame and plan throughput fell; they do not prove an IRQ
storm. Most submit-sensitive scenes regressed by 15-24%, while fixed buffer
scenes remained approximately 46/46/65.

Decision | Reverted. Executing long Panthor receive handlers in an ONESHOT IRQ
thread changes scheduling and keeps the event interrupt masked during the
drain. Those effects are plausible but not independently isolated. Do not
retry this direct-drain design unchanged. Full commands, hashes, counters,
patch and logs are in `build/threaded-irq-direct-20261024/report.md`.

### Object-scoped monotonic timeline wait caching

Purpose | Keep a proven completed syncobj timeline prefix valid across later
monotonic submissions, with per-object generation checks and precise signal
target invalidation.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1155
(`object-wait-cache-720-20261024-a`), -3 points / -0.26%.

Mechanism evidence | `cache_hits` increased from 19,772 to 38,567, the new
prefix path hit 983 times, and `cache_miss_epoch` fell from 14,271 to 63. The
optimization nevertheless removed no PLAN_EXEC RPC or completion boundary;
response arms before sleep increased from 398 to 861 and trusted request IRQs
from 7,036 to 7,494.

Validation | Candidate wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, kernels were clean, and resources were
restored. Full command, hashes, counters, patch and logs are in
`build/object-wait-cache-20261024/report.md`.

Decision | Reverted. A completed-prefix cache alone is below the workload's
measurement sensitivity and adds invalidation bookkeeping. Do not retry it
unchanged; any successor must eliminate or overlap a synchronous RPC boundary.

### Proxy receive-side sleep coalescing

Purpose | Delay request IRQ re-arm briefly so a persistent queue arrival can
be processed without another Host wake.

Comparison | 1158 (`request_coalesce_us=0`) -> 1150
(`request_coalesce_us=10`), -8 points / -0.69%.

Evidence | Baseline `request-coalesce-us0-720-20261024-a`; candidate
`request-coalesce-us10-720-20261024-a`; both wrapper return code 0, 33 scenes,
validation 26/1/6, VM exit codes 0/0, clean Guest/Host kernels and restored
CPU/GPU state. Full commands, hashes and downloaded logs are in
`build/request-coalesce-20261024/report.md`.

Decision | Reverted. Do not retry fixed 10/20/40 us sleeps on the empty
request path. Any future batching design must avoid delaying a lone
synchronous request and first prove that useful concurrent work is available.

### Client response-poll lockless empty probe

Purpose | During the existing bounded Client reply poll, compare the locally
owned response-consumer index with the Proxy release-published avail index
before entering the existing locked dequeue path. A visible response still
used the unchanged private snapshot, bounds checks, sequence/type matching and
waiter lifetime rules; IRQ work remained unchanged.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1152
(`response-empty-fastpath-720-20261024-a`), -6 points / -0.52%.

Evidence | Proxy, initrd and runner were byte-identical; only the Client Image
changed. The wrapper and runner returned 0, all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, kernels were clean, and resources
were restored. Poll calls fell with workload throughput from 985,114 to
977,956; replies completed before sleep were 984,716/985,114 versus
977,521/977,956, while sleep arms increased from 398 to 435. The optimization
did not remove an RPC, notification or completion boundary.

Decision | Reverted. A faster empty probe only makes the already busy Client
spin loop cheaper per iteration and may increase shared-index polling rate; it
does not shorten the dominant Proxy service and Realm/Host scheduling path.
That explanation is not independently isolated, so the score is the rejection
authority. Do not retry this probe unchanged. Full patch, hashes, build logs,
run logs and rollback evidence are in
`build/response-empty-fastpath-20261024/report.md`.

### Proven-complete binary TRANSFER elision

Purpose | When a binary `SYNCOBJ_TRANSFER` copied an exact positive timeline
point whose PLAN_EXEC completion cookie had already been published, keep the
destination as a locally signaled object. Export could then return a signaled
local sync_file without `TRANSFER_CAPTURE`; any later Proxy-visible use first
materialized the state with `SYNCOBJ_SIGNAL`.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1154
(`completed-transfer-elision-720-20261024-a`), -4 points / -0.35%.

Mechanism evidence | The workload issued 456,642 eligible binary transfers,
but only 45 found the exact source point already proven complete, a 0.0099%
hit rate. `TRANSFER_CAPTURE` calls fell by exactly 45, while all 45 local
states later required a `SYNCOBJ_SIGNAL` flush; 35 were exported locally first.
The candidate therefore moved those rare RPCs instead of removing a durable
synchronous boundary.

Validation | Wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, both Guest kernels and the Host were
clean, and CPU/GPU/process/loop resources were restored. Proxy Image, initrd
and all runtime options except the Client feature switch were identical to the
baseline.

Decision | Reverted. The exact completion proof normally arrives after Mesa's
binary transfer, and every hit in this run was later materialized. Do not retry
this exact-point local-signaled design unchanged. A successor needs a proof
available before the transfer or must eliminate the later materialization RPC,
not merely replace `TRANSFER_CAPTURE` with `SYNCOBJ_SIGNAL`. Full evidence is
in `build/completed-transfer-elision-20261024/report.md`.

### Proxy GPUVM precise cache synchronization

Purpose | Restrict the conservative submit/completion scan of every mapped
Realm-private BO to ordinary DRM ioctl GPUVMs. Trusted vmshm GPUVMs instead
used existing exact synchronization for queue ringbuffers and group syncobjs,
one-time ownership handoff for GPU-only tiler chunks, and a new exact
initialization sync for tiler heap contexts.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1173
(`precise-realm-sync-720-20261024-a`), +15 points / +1.30%. The result is below
the minimum retention score of about 1181.

Evidence | Client Image, initrd, runner and all runtime options were
byte-identical; only the Proxy Image changed. The wrapper and runner returned
0, all 33 scenes completed, validation was 26/1/6, VM exits were 0/0, both
Guest kernels and the Host were clean, and CPU/GPU/process/loop resources were
restored. Most submit-sensitive scenes improved by about 1-2%, but this gate
did not enable per-submit diagnostics and therefore does not independently
prove the expected 4.69 us mapped-BO scan removal.

Decision | Reverted. The direction was positive but did not reach the required
2-3% end-to-end gain. Do not retry the precise-sync-only patch unchanged. A
successor may reuse the ownership analysis only if it also removes another
material synchronous boundary and the complete combined design independently
passes the gate. Full patch, build log, hashes, downloaded run and wrapper
evidence are in `build/precise-realm-sync-20261024/`.

### Receiver-active request notification suppression

Purpose | While the Proxy RX worker was actively draining the Client-to-Proxy
queue, publish the receiver-owned `USED_NO_NOTIFY` hint. A Client that had
release-published its next request could skip RMM `NOTIFY`; Proxy cleared the
hint with a full barrier and rechecked after the existing `ACK_ARM`, preserving
the no-lost-wakeup protocol without adding a sleep or changing the ABI.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1154
(`receiver-active-notify-720-20261024-a`), -4 points / -0.35%.

Mechanism evidence | The Client sent 984,874 request notifications and
suppressed only 1,399, a 0.142% hit rate. PLAN_EXEC operations also fell from
457,424 to 454,624, so the lower Proxy event IRQ count, 991,035 -> 984,873,
mostly follows lower benchmark throughput and is not evidence of useful
coalescing. The extra barriers, flag accesses and Proxy lock operations apply
far more often than the optimization hits.

Validation | Wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, both Guest kernels and the Host were
clean, and CPU/GPU/process/loop resources were restored. The candidate changed
only the Client and Proxy Images; initrd, runner and runtime options matched
the 1158 baseline.

Decision | Reverted. This is also a current-baseline confirmation of archived
P14, which scored 829 -> 826 (-0.36%) despite a higher 2.34% suppression rate.
Do not retry receiver-active request notification suppression unchanged. It
does not shorten the mandatory synchronous RPC, and the next request almost
always arrives after the Proxy has already cleared the active hint. Full
evidence is in `build/receiver-active-notify-20261024/report.md`.

### PLAN_EXEC follow-up notification credit with hrtimer fallback

Purpose | Before publishing a successful `PLAN_EXEC` response, expose a
one-shot request `USED_NO_NOTIFY` credit. Client skips RMM `NOTIFY` for the
next request when it observes the credit; a pinned Proxy hrtimer clears the
credit and schedules receive processing if the active worker did not consume
the request first.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1154 with a
20 us window (`followup-notify-us20-720-20261024-a`), -4 / -0.35%; shortening
the window to 5 us (`followup-notify-us5-720-20261024-a`) scored 1082,
-76 / -6.56%.

Mechanism evidence | The 20 us run suppressed 442350 of 974102 request
notifications (45.41%); the 5 us run suppressed 418566 of 931723 (44.92%).
However, every opened window expired in both runs: 452428/452428 and
428363/428363 timers fired, while the current receive worker consumed zero
follow-ups before expiry. The scheme therefore replaced a trusted notify with
one hrtimer/workqueue wake per plan instead of extending useful queue draining.

Validation | Both wrappers and runners returned 0, all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, kernels were clean, and CPU/GPU,
process and loop resources were restored. The two candidates used identical
Client/Proxy Images and differed only in the frozen runner's 20/5 us boot
argument.

Decision | Reverted. A 20 us fallback was neutral-to-negative despite a high
suppression rate, while 5 us increased scheduling contention and materially
reduced plan throughput. Do not retry fixed hrtimer follow-up wakeups or sweep
intermediate delays unchanged. A successor must avoid one timer/workqueue
event per `PLAN_EXEC`. Full patch, hashes, logs and analysis are in
`build/followup-notify-20261024/report.md`.

### Managed GPUVM root reservation plus precise cache ownership

Purpose | For Proxy-created vmshm GPUVMs, prepare and update only the VM root
reservation during GPU submission instead of locking every mapped BO. Combine
this with the previously positive precise Realm cache ownership path. VM_BIND
continued to lock the root and target BO; ordinary DRM GPUVMs were unchanged.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1178
(`managed-vm-resv-720-20261024-a`), +20 / +1.73%. This missed the minimum
retention score of about 1181.

Correctness evidence | The wrapper and runner returned 0, all 33 scenes
completed, validation was 26/1/6, VM exits were 0/0, both Guest kernels and the
Host were clean, and CPU/GPU/process/loop resources were restored. Mappings
retain GEM/GPUVM references, vmshm submissions use explicit syncobj
dependencies, and VM_BIND retained its original root-plus-target-BO path.

Decision | Reverted. The combination was positive but still below the required
2-3% gate. Do not retry these two changes alone. They may only be reused with
an independent optimization that removes or overlaps another high-frequency
synchronous boundary. Full patch, build logs, run evidence and rollback proof
are in `build/managed-vm-resv-20261024/report.md`.

### PLAN_EXEC piggyback immutable snapshot capture

Purpose | Extend a cached `PLAN_EXEC` so the Proxy captures its newly signaled
timeline point into a private immutable binary snapshot and returns that
snapshot in the same response. The immediately following exact binary
`SYNCOBJ_TRANSFER` then aliases the snapshot locally instead of issuing a
second synchronous `TRANSFER_CAPTURE` RPC. Later Proxy-visible use materializes
the deferred state through the existing transfer path, and later plan requests
piggyback retirement of the previous snapshot.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1147
(`plan-capture-720-20261024-b`), -11 points / -0.95%. This is below both the
baseline and the minimum retention score of about 1181.

Mechanism evidence | The candidate recorded 455733 plan snapshots with zero
capture failures and locally elided all 455733 eligible binary transfers;
ordinary `capture_calls` fell from 457687 to zero. Only 33 deferred states
needed later materialization. Proxy trusted event IRQs fell from 991035 to
542811 and response-notification opportunities from 991488 to 543173, proving
that the extra request boundary was actually removed. Plan throughput still
fell from 457424 to 455470 and the score did not improve. The result therefore
rejects the end-to-end design even though its protocol-level mechanism worked.

Validation | The corrected run returned 0, completed all 33 scenes with
validation 26/1/6, VM exits 0/0, clean Client/Proxy/Host kernels and complete
CPU/GPU/process/loop resource restoration. The first run
`plan-capture-720-20261024-a` failed before glmark because the new message
exhausted the fixed 32-entry Proxy handler table; increasing the table capacity
to 64 fixed that implementation error, and the failed evidence is retained.

Decision | Reverted. Moving snapshot creation into the mandatory `PLAN_EXEC`
critical path and eliminating its follow-up RPC did not improve complete
720p glmark under the current one-vCPU Proxy architecture. Do not retry the
same piggyback-capture protocol unchanged. Any successor must first isolate
why the removed request/IRQ boundary was not score-critical, or reduce the
native syncobj create/capture/destroy work itself rather than only moving it
between RPC handlers. Full commands, hashes, patch, both runs and rollback
evidence are in `build/plan-capture-20261024/report.md`.

### Proxy-private native syncobj handle pool

Purpose | Keep a bounded per-session pool of eight native DRM syncobj handles
for immutable transfer snapshots. Retirement deleted the old Client-visible
handle and watcher, then returned the native handle to the pool; the next
snapshot allocated a new Client handle but reused the native object. No ABI,
protocol or RPC-count change was introduced.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1157
(`private-syncobj-pool-720-20261024-a`), -1 point / -0.09%.

Mechanism evidence | The pool recorded 455927 hits, 8 misses, 455935 returns,
zero overflow and 8 final drains across 455934 retired snapshots. The intended
native create/destroy reuse therefore occurred for 99.998% of eligible
snapshots. The mandatory transfer capture still replaced the fence, and RPC,
queueing and native submission costs were unchanged.

Validation | Wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, both Guest kernels and the Host were
clean, and CPU/GPU/process/loop resources were restored.

Decision | Reverted. Native syncobj object allocation/destruction is not a
material 720p bottleneck under the current flow, despite near-perfect reuse.
Do not retry handle pooling alone; a successor must remove or overlap a
synchronous boundary or reduce per-capture fence work. Full patch, build log,
run evidence and rollback proof are in
`build/private-syncobj-pool-20261024/report.md`.

### Managed GPUVM plus borrowed submit arrays

Purpose | Restore the previously positive managed GPUVM root-only reservation
and precise cache-ownership combination, then additionally remove temporary
job-array allocation and per-job sync-array allocation/copy/free from the
bounded vmshm group-submit path. Ordinary DRM ioctl submissions retained their
owned arrays.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1179
(`managed-borrowed-submit-720-20261024-a`), +21 / +1.81%. This missed the
minimum retention score of about 1181.

Mechanism evidence | The predecessor with only managed-root reservation and
precise cache ownership scored 1178. Adding borrowed arrays scored 1179 in a
separate run. That one-point difference is below run-level isolation and cannot
be attributed precisely; the authoritative result is that the full combination
still missed the 2% gate. Removing these short-lived allocations and copies is
therefore not sufficient as an independent end-to-end optimization.

Validation | The wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, both Guest kernels and the Host were
clean, and CPU/GPU/process/loop resources were restored. Client Image, initrd,
runner and runtime options matched the baseline; only the Proxy Image changed.

Decision | Reverted. Do not retry borrowed vmshm job/sync arrays alone or this
three-part combination unchanged. Managed root-only reservation and precise
ownership remain reusable only with an independent change that removes or
overlaps a high-frequency synchronous boundary. Full patch, build log, run
evidence and rollback proof are in
`build/managed-borrowed-submit-20261024/report.md`.

### Native Panthor submission-plan caching

Purpose | Resolve and pin the native group and syncobj handles plus immutable
submit layout during `PLAN_REGISTER`, then let each `PLAN_EXEC` update only
stream addresses, sizes, flush values and timeline points before calling the
native driver.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1153
(`native-submit-plan-720-20261024-a`), -5 / -0.43%.

Mechanism evidence | The candidate executed 455919 plans and recorded 455916
Client plan hits with only 3 misses, so the native cache covered effectively
all steady-state submissions. Request/response event IRQ counts were
977317/7045. The negative score confirms that rebuilding the small native
submit wrapper is not material beside transport, queueing, admission and
completion costs.

Validation | The wrapper and runner returned 0; all 33 scenes completed,
validation was 26/1/6, VM exits were 0/0, both Guest kernels and the Host were
clean, and CPU/GPU/process/loop resources were restored.

Decision | Reverted. Do not retry native submission-plan caching unchanged or
combine it with managed-root changes solely to mask its independent negative
result. Full patch, hashes, logs, rebuild and rollback evidence are in
`build/native-submit-plan-20261024/report.md`.

### Persistent completion point feed and deferred binary transfer

Purpose | Publish completed timeline points persistently, defer binary
TRANSFER locally, and materialize only before a later native operation.

Comparison | 1158 (`request-coalesce-us0-720-20261024-a`) -> 1150
(`point-feed-720-20261024-b`), -8 points / -0.69%.

Mechanism evidence | `feed_transfers=449071`, `feed_materializations=32`,
`feed_fallbacks=0`, `capture_calls=0`, and `plan_runs=448808`. Proxy event IRQs
fell from 991035 to 453599, yet the complete score regressed. Eliminating the
follow-up request alone did not shorten the measured end-to-end critical path.

Validation | Wrapper and runner rc0; 33 scenes; validation 26/1/6; VM exits
0/0; Guest/Host kernels healthy; resources restored. Preparation run
`point-feed-720-20261024-a` lacked the frozen manifest and failed before
deployment; no hardware/performance result is attributed to it.

Decision | Reverted. RK baseline restore `point-feed-rollback-20261024-a`
returned 0. Do not retry point-feed/local transfer alone; reuse is limited to
necessary infrastructure for a genuinely asynchronous PLAN_EXEC successor.
Conditions, command, hashes and evidence are in
`build/point-feed-20261024/report.md`.

### Fresh Proxy-side FLUSH_ID sampling

Purpose | Negotiate a read-only virtual FLUSH_ID token and resolve it only in
the vmshm native path to a fresh hardware observation immediately before GPU
ring insertion, after DMA synchronization and dependencies. Preserve explicit
zero's unconditional flush, native PM/reset serialization, validation and all
CPU/GPU cache maintenance. A stale counter mirror remains unsafe.

Comparison | 1158 ->1158, 0 /0.00%; run `proxy-flush-720-20261024-a`.

Mechanism evidence | The benchmark session requested457328 samples alongside
457328 plan executions. An earlier sample marker reports0x00ffffe0. The
candidate was active, but no actual flush-elimination rate was measured;
these counts cannot establish a saved GPU operation or its latency.

Validation | Both Image builds rc0; wrapper/runner rc0; collection VERIFIED
with11 remote files;33 scenes, validation26/1/6, VM exits0/0, Guest/Host
kernels clean and CPU/GPU/process/loop resources restored. Both Images
changed; initrd, runner and runtime conditions match the1158 baseline.

Decision | Reverted. Score below1182; API/ML/multi-Client expansion NOT_RUN.
Source restored and managed board rollback recorded in
`build/proxy-flush-20261024/rollback.log`. Full patch, design, command,
hashes and evidence are in `build/proxy-flush-20261024/report.md`.

### Dedicated ordinary-priority Proxy receive thread

Purpose | Replace system_wq receive work with one sleeping normal-priority
kthread per authenticated channel. Preserve the bounded hard IRQ, coalesced
wake, private snapshot, ACK_ARM/recheck and unsubscribe/stop/join lifecycle.
Unlike the earlier direct IRQ thread, this does not use FIFO or ONESHOT.

Comparison | 1158 -> 1147, -11 / -0.95%; run
`dedicated-rx-720-20261024-a`.

Mechanism evidence | Dedicated RX PID568 and982604 drain passes were logged;
Proxy/Client IRQs982604/6601. The substitution was active, but no per-stage
timing was collected, so no IRQ-latency or scheduling cause is claimed.

Validation | Proxy build rc0 without new warnings/errors; wrapper/runner rc0;
collection VERIFIED11 remote files;33 scenes, validation26/1/6, VM exits0/0,
all Guest/Host kernel health checks clean; CPU/GPU/process/loop resources
restored. Only Proxy Image changes; Client/initrd/runner and options match.

Decision | Reverted. Managed board restore is
`dedicated-rx-rollback-20261024-a`; API/ML/multiple-Client expansion NOT_RUN.
Do not retry the same task substitution unchanged. Full conditions, command,
hashes, lifecycle review and evidence are in
`build/dedicated-rx-20261024/report.md`.

### DRM scheduler empty-work suppression

Purpose | Count jobs still queued in scheduler entities and skip run-job
workqueue wakeups when the count is zero. Dependency-blocked jobs retain
their count; actual pops and killed-entity drains remove it.

Comparison | 1158 -> 1152, -6 / -0.52%, run
`sched-idle-720-20261024-a`; below the minimum1182 gate.

Validation | Proxy build rc0, workload runner rc0,33 scenes, validation26/1/6,
VM exits0/0 and Guest health clean. Outer wrapper rc1 because Host dmesg
wrapped; errors=[], but full Host health coverage remains INCOMPLETE.
Collection VERIFIED11 files; CPU/GPU/process/loop resources restored. Final
scheduler-fini skip counters NOT_CAPTURED; no saved-work amount is claimed.
Only Proxy Image changed; Client/initrd/runner and runtime options matched.

Decision | Reverted all15 additions. Board rollback
`sched-idle-rollback-20261024-a` rc0 restored exact baseline hashes. API/ML/
multi-Client expansion NOT_RUN. Full command, images and incomplete-health
evidence are in `build/sched-idle-20261024/report.md`. Do not retry alone.

## Next selection rule

### Shared-slot extent plus producer credit caching: reverted

Purpose | Cache peer consumption privately and refresh with acquire only when
cached free capacity is exhausted, together with bounded message clearing/copy.
Reject retirement of unsent slots and backward progress; preserve actual
full/EAGAIN and u32 wrap. Real boot tests extend full/drain/refill and forged
consumer progress coverage.

Comparison | Resident-only1182 ->1189,+7/+0.59%, run
`transport-credit-cache-720-20261024-a`; below1206 gate. Wrapper/runner rc0,
33scenes,validation26/1/6,VM exits0/0,Guest/Host health PASS without dmesg
wrapping,resource recovery PASS,collection VERIFIED11. Both Images rebuilt;
initrd/runner/resident firmware and runtime options matched. No independent
per-copy/credit latency measured; do not assign the7-point run difference to
one operation. API/ML/multi-Client expansion NOT_RUN.

Decision | Full transport combination reverted. The next native candidate
contains neither transport change; baseline remains1182. Exact conditions,
command,SHA and evidence: `build/transport-credit-cache-20261024/report.md`.
Do not retry unchanged.

### Bounded shared-slot clearing/copy: no independent gain

Purpose | Clear complete fixed headers and actual outgoing payloads; snapshot
only the extent from a privately copied and validated descriptor. Keep a
fixed bounded private receive buffer and all consistency/ownership checks.

Comparison | Resident-only1182 ->1182,0/0.00%, run
`transport-slot-bytes-720-20261024-a`. Wrapper/runner rc0;33scenes,
validation26/1/6, VM exits0/0, Guest/Host health PASS without dmesg wrapping,
resource recovery PASS and collection VERIFIED11. Both Guest Images rebuilt;
initrd/runner/resident firmware and runtime options matched. No per-copy
latency saving is claimed. Additional API/ML/multi-Client expansion NOT_RUN.

Decision | Not retained independently. A separate frozen combination adds
private consumed-credit caching and real full/drain/forged-progress/u32-wrap
queue selftests, compared independently against1182. Mutable transport source
is already restored; neither part becomes retained through reuse in a candidate.
Exact conditions, command, SHA and evidence:
`build/transport-slot-bytes-20261024/report.md`. Do not retry bytes-only unchanged.

### Native scheduler dispatch handoff: reverted

Purpose | Publish managed jobs, release submission reservation locks, then
flush each distinct native queue's already queued run-job work before the
RPC reply, retaining job/group lifetime references. Wait for dispatch work,
not GPU completion; preserve native scheduling and fences.

Comparison | Resident-only1182 ->1180, -2/-0.17%, run
`native-dispatch-handoff-720-20261024-a`; required new gate1206. Original1158
->1180 includes the already retained notification design and is not a second
independent gain. Only Proxy changed; Client/initrd/runner, resident firmware
and full720p runtime options matched.

Validation | Wrapper/runner rc0;33scenes, validation26/1/6, VM exits0/0,
Guest/Host health PASS without dmesg wrapping, resource recovery PASS,
collection VERIFIED11. All19 additions reverted and absent from the next
transport-only candidate. API/ML/multi-Client expansion NOT_RUN. Full command,
SHA, conditions and evidence: `build/native-dispatch-handoff-20261024/report.md`.
Do not repeat unchanged; no scheduler-latency saving is claimed.

Receiver-opted-in resident request wake is retained:1158→1183/1181,
mean1182 (+24/+2.07%); B individually+1.99%, so evidence is close to the gate.
Full720p, dual-Client API/compute and GEMM/conv pass with wrapper/runner rc0,
Guest/Host health and resource restoration clean. No same-condition ML speed
comparison was made. New baseline is the resident-only frozen combination;
next independent candidate must reach1206 for at least2%. Design, exact
conditions, run-ids, commands, SHA and rollback are in
[resident wake report](GPU_RESIDENT_REQUEST_WAKE_20261024.md). Archived
two-direction P20 remains rejected; this is request-only receiver opt-in.

Prefer designs that remove or overlap a synchronous RPC boundary. Existing
measurements place lookup, validation and assembly near 1.14 us combined,
while transport, queueing and wait account for most PLAN_EXEC latency;
micro-optimizing Proxy object lookup alone is therefore unlikely to reach the
retention threshold. Completion-based transfer elision must also prove that
its state survives the next Proxy-visible use without an equal replacement
RPC; exact-point completion observed only at transfer time is too late for the
current glmark flow. Eliminating the remaining conservative mapped-BO cache
scan produced only +1.30% by itself, so the next candidate must remove or
overlap an additional high-frequency synchronous boundary rather than stack
more per-submit bookkeeping around the same scan.

## Code-backed selection notes

The exact integer retention gate against 1158 is **1182** for at least 2%
and **1193** for at least 3%. Scores below 1182 do not qualify by rounding.

### Response receive initialization: reverted

The compiled `client_comm_vmshm_dispatch_response()` cleared a 472-byte
payload and 56 bytes of receive metadata before checking whether a response
was available. This applies to every dispatch attempt inside the bounded
reply poll, rather than only the 985114 baseline RPC poll windows.

Successful `client_comm_vmshm_queue_recv()` writes all response fields and
exactly the validated payload length. The candidate initializes only input
buffer/capacity and `proxy_channel = NULL`, preserving the fixed 512-byte
private snapshot, descriptor/length checks, waiter matching and locking.
ARM64 disassembly confirms both memset calls disappear. Full 720p scored
1158 -> 1160 (+2 / +0.17%), below the 1182 gate. Run
`response-init-720-20261024-a` passed 33 scenes, validation 26/1/6, VM exits
0/0, kernel health, collection verification and resource restoration;
wrapper/runner rc0. Only the Client Image changed. Source was reverted;
conditions, command, hashes and logs are in
`build/response-init-20261024/report.md`. Do not retry the memset removals alone.

### Completion subscription: limited current glmark coverage

The 1158 baseline reports `waits=0`, `polls=0`, 382480 snapshot waits and
381076 completion hits, with only 1404 completion fallbacks. Consequently,
replacing the sync_file worker's query/sleep loop is not expected to explain
a large score gain in this workload. A future subscription design must first
identify a workload that actually blocks on these workers, preserve fence
errors and cancellation, and separately report the coverage difference.
These are code/counter observations, not a new performance measurement.

A later exact1311 baseline coverage run,
`immutable-wait-baseline-ml-20261024-a`, measured doubleClient GEMM
57.58834/57.87922ms and conv66.77865/67.11385ms, common-window fractions
99.14%/99.18%. Both Clients had210 snapshot checks/0 cookie hits/210 fallbacks,
but sync_file worker waits/polls still0. These ML tasks exercise blocking ioctl
waits, so optimizing only the sync_file worker would miss them too. Source
inspection also confirms per-channel rx_work on system_wq, not one global
dispatch worker: a sleeping channel does not by itself block all others.
No runtime change and no optimization gain claim. Wrapper/runner rc0,
correctness,VM0/0/0,kernel health,resource restoration and VERIFIED14 files
passed. Conditions,exact argv,hash audit and limitations:
`build/immutable-wait-fairness-20261024/report.md`.

### FLUSH_ID shadowing: stale values are not a safe optimization

Client mmap exposes a zero-initialized local FLUSH_ID page. Panthor's UAPI
explicitly defines zero as unconditional flush; the native ring wrapper emits
FLUSH_CACHE2 before CALL. A periodically mirrored older hardware counter
cannot simply replace zero: the GPU might flush, then the CPU modify a
buffer, and a stale earlier ID might incorrectly authorize flush elimination.
Do not set the page to a constant nonzero value or publish an approximate
counter for performance. Any successor needs a fresh observation with the
required ordering, PM/reset handling and preserved unconditional-zero UAPI
semantics. This direction is analysis-only and has no measured gain.

### Research reference and applicability

[eRPC, NSDI 2019](https://www.usenix.org/system/files/nsdi19-kalia.pdf),
sections 4.2.3 and 4.3, motivates reducing receive copies under a proven buffer
ownership guarantee and using bounded outstanding RPC slots. Its zero-copy
receive argument relies on the NIC being unable to change a buffer while the
handler owns it. Our shared peer can mutate memory, so a bounded private
snapshot remains necessary; only redundant copies after that snapshot are
candidates. Likewise, extra outstanding slots cannot pipeline requests that
Mesa's calling thread has not generated while blocked in GROUP_SUBMIT.
No paper performance percentage is transferred to this project.
