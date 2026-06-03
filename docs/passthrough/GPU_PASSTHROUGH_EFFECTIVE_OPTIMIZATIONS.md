# GPU Passthrough Effective Optimization Designs

本文档记录真正值得保留的 GPU passthrough 优化设计、诊断能力和失败方向黑名单。它不是逐轮实验日志，而是当前代码和测试结论的压缩版：即使 `GPU_PASSTHROUGH_OPTIMIZATION_LOG.md` 被清零或只保留近期条目，仍能通过本文知道哪些修改确实解决了问题、哪些只是诊断工具、哪些方向已经被证明不适合作为默认优化。

当前默认判断口径见 `GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md`：正式结果只看 `4 MiB / 16 MiB / 64 MiB` 三个真实 GPU task workload 的一张 `Formal Host/VM performance ratio table`，所有性能数字使用 `host/vm` ratio，越接近 `1.000` 越好。

## 背景约束

Mali/Panthor passthrough 和传统 VFIO GPU passthrough 不完全一样。guest Panthor 仍要构造 GPU 可见页表，但 Mali GPU 使用的地址翻译路径不能简单依赖 CPU stage-2 页表完成 GPU DMA 地址转换；GPU 页表项最终需要写入 host physical address。于是 guest 侧 GPU shadow page-table 更新必须把 guest physical address 转换成 host physical address，再写入 GPU page table。

这个约束带来了三类主要开销：

- GPU VM_BIND/page-table population 中的 GPA->HPA translation。
- GPU task submit/completion 中的 scheduler、IRQ injection、resample/EOI 和 fence wait。
- 测试和日志本身对热路径时序的扰动。

因此当前有效优化大致分为两层：

- 真正改变默认性能路径的技术优化。
- 不直接优化 GPU 执行，但保证测试可信、迭代高效、诊断低扰动的工程优化。

## 当前采用的有效优化

| 设计 | 类型 | 当前状态 | 主要收益 |
| --- | --- | --- | --- |
| GPU 页表映射批处理化和 2 MiB candidate/fallback | 核心技术优化 | 默认采用 | 降低大 buffer VM_BIND/page-table population 的 per-page 成本。 |
| GPA->HPA batch translation 与 per-io-pgtable scratch page | 核心技术优化 | 默认采用 | 减少 HVC 调用准备和 guest scratch allocation/copy 成本。 |
| Host GPA->HPA HVC 原地数组处理 | 核心技术优化 | 默认采用 | 去掉 host HVC 中的 `kmalloc + kvm_read_guest + kvm_write_guest` 数组处理。 |
| Panthor scheduler workqueue 从 unbound 改 bound | 核心技术优化 | 默认采用 | 显著降低 scheduler worker queue-to-start 长尾，改善 4/16 MiB。 |
| 清理 IRQ/KVM/VGIC/Panthor hot-path printk | 性能卫生，也是有效优化 | 默认采用 | 去掉人为毫秒级 completion/IRQ 扰动。 |
| 默认关闭的 PT/IRQ/submit timing stats | 诊断设计 | 默认关闭，按需启用 | 定位瓶颈而不污染正式 baseline。 |
| Host/VM 测试规范单表化和 rootfs userspace 对齐 | 测试设计 | 默认采用 | 减少误判，保证之后比较口径统一。 |
| Host kernel Image-only / selected-module 部署 | 迭代效率优化 | 默认采用 | 避免无意义的全量 module sync/install，缩短测试循环。 |

## 1. GPU 页表映射批处理化和 2 MiB candidate/fallback

### 要解决的问题

最初的安全实现倾向于把 GPU VM_BIND 全部拆成 4 KiB PTE。这样正确性较强，因为 guest 连续 GPA 并不等于 host 连续 HPA；如果直接写大页 block PTE，可能把 GPU 映射到错误 host page。但对 16/64 MiB 这类 buffer，纯 4 KiB 更新会产生大量 PTE 初始化、页表 walk/update 和 GPA->HPA translation 成本。

### 设计

当前 guest Panthor VM map 路径允许 `SZ_4K | SZ_2M`，在 IOVA 和长度满足条件时先产生 2 MiB candidate。custom `io-pgtable-arm` 路径对每个 2 MiB range 一次性翻译 512 个 4 KiB page 的 HPA：

- 如果 HPA base 2 MiB 对齐，并且 512 个 HPA page 连续，则写入真实 2 MiB GPU block PTE。
- 如果 HPA 不满足条件，则分配一个 leaf table，一次性填入 512 个 4 KiB PTE，再把 table 安装进上级 PTE。

这避免了“为了追求大页而牺牲正确性”。实际大页 block 只有在 HPA 连续性和对齐都被证明后才使用；否则仍然保持 4 KiB leaf correctness，但把 fallback 构建做成批处理。

### 测试结论

Attempt 3 的正式 run 中：

```text
Baseline: 4/16/64 MiB Host/VM = 0.208 / 0.505 / 0.765
Attempt 3: 4/16/64 MiB Host/VM = 0.269 / 0.519 / 0.808
```

64 MiB 明显改善。关键点是 `2m_blocks=0`，也就是说当时没有真正形成 GPU 2 MiB block PTE；收益主要来自 2 MiB candidate 下的批量 fallback/table 构建和批量 HPA 检查，而不是 GPU TLB 大页收益。

### 保留原因

这个设计解决的是大 buffer 页表更新的结构性问题，而且在不牺牲 HPA 正确性的前提下提供了后续真实 2 MiB block PTE 的入口。即使当前很多 workload 仍 fallback，它也是后续 HPA 对齐优化的基础。

### 当前限制

当前 `2m_hpa_unaligned` 通常接近 `2m_attempts`，说明 blocker 主要是 backing HPA base 不满足 2 MiB 对齐。后续如果继续追真实 2 MiB GPU block PTE，方向应是 BO allocation、guest memory backing、Firecracker memory offset、hugepage/CMA/SG layout 的联合对齐，而不是只改 PTE writer。

## 2. GPA->HPA batch translation 与 scratch page

### 要解决的问题

GPU shadow page-table 写 HPA，每个 GPA 都需要向 host KVM 查询对应 HPA。如果每个 PTE 都单独 HVC，或者每次 batch 都临时分配 scratch array，会产生明显固定成本。早期尝试证明，粗暴地把所有 leaf BO page 都放进 hash cache 可能会带来额外开销，尤其是大 buffer 上 cache/alloc 成本会抵消收益。

### 设计

当前 guest `io-pgtable-arm` 为每个 Panthor io-pgtable 保存一个 scratch page 和锁：

- batch 输入和输出都通过一页 `u64` array 传递。
- 单次最多处理 `PAGE_SIZE / sizeof(u64)` 个 entry。
- GPA->HPA 统计包括 batch 数、entry 数、HVC 数、cache hit/miss。
- cache mode 区分 table/leaf/none，用来避免把所有场景都用同一种缓存策略处理。

这个设计减少了反复分配临时数组的开销，也让 page-table page、leaf page、2 MiB fallback 等路径可以用统一的 batch translation 入口。

### 测试结论

Attempt 1 的“所有 page 都 hash cache”不是稳定收益，4 MiB 改善但 16/64 MiB 回退。Attempt 2 调整策略后，4/16 MiB 比 baseline 改善，64 MiB 仍不足。真正稳定的结论是：

- batch translation 是必要基础。
- cache 不能盲目覆盖所有 leaf BO page。
- 需要继续把 HVC 里的 guest array 处理和 page-table fallback 结合优化。

### 保留原因

这是整个 passthrough shadow page-table 方案的基础设施。它本身不总是单独带来大幅性能提升，但没有它，后续 2 MiB candidate/fallback、PT timing、host HVC in-place array 都无法干净实现。

## 3. Host GPA->HPA HVC 原地数组处理

### 要解决的问题

Attempt 29 的 page-table timing 证明，64 MiB metadata/page-table 路径里真正重的是 GPA->HPA HVC：

```text
Attempt 29 VM-only 64 MiB:
gpa2hpa_hvc_ns = 7.34 ms
map_2m_translate_ns = 6.42 ms
```

当时 host HVC 对 guest array 的处理包含：

```text
kmalloc host buffer
kvm_read_guest() 读取 guest GPA array
逐 entry gfn_to_pfn_prot()
kvm_write_guest() 写回 HPA array
```

这里的数组 copy/alloc 是纯管理开销，不改变真正的 GPA->HPA pin 语义。

### 设计

Attempt 30 把 host KVM GPA->HPA hypercall 改为：

- 用 `kvm_vcpu_map()` 映射 guest 传入的一页 GPA/HPA array。
- host 直接在映射出的 HVA 上原地读取 GPA、写回 HPA。
- 每个 data page 仍通过 `gfn_to_pfn_prot()` 获取/固定 PFN，保持原有 pin 语义。
- 最后 `kvm_vcpu_unmap(..., dirty=true)` 写回。

这相当于只移除 guest array 的中间拷贝和临时 host buffer，不改变 data page 翻译的 correctness 约束。

### 测试结论

VM-only PT timing：

```text
Attempt 29 64 MiB gpa2hpa_hvc_ns = 7.34 ms
Attempt 30 64 MiB gpa2hpa_hvc_ns = 5.56 ms
Attempt 29 64 MiB map_2m_translate_ns = 6.42 ms
Attempt 30 64 MiB map_2m_translate_ns = 5.14 ms
```

正式 repeat：

```text
Attempt 26 bound workqueue baseline: 0.788 / 0.767 / 0.852
Attempt 30 repeat:                 0.830 / 0.875 / 0.907
```

16 MiB 和 64 MiB 达到或超过 `Host/VM >= 0.87`，4 MiB 也从 `0.788` 提升到 `0.830`。

### 保留原因

这是当前最明确的 page-table/HVC 技术优化。它直接减少 host hypercall 管理成本，并且没有引入新的用户态 API 或改变 guest userspace 语义。

### 当前限制

这个优化降低的是 HVC array handling，不会消除每个 data page 的 `gfn_to_pfn_prot()` 成本。后续如果 metadata 仍慢，不能只继续在这个 HVC 函数里微调；需要看 CPU prepare、buffer upload、Mesa/DRM BO path、VM_BIND 和 page-table population 的完整链路。

## 4. Panthor scheduler workqueue 从 unbound 改 bound

### 要解决的问题

submit diagnostics 显示，Panthor group submit 的主要成本不是 ringbuf write、doorbell 或 backend `run_job` 本体，而是在 DRM scheduler wake/workqueue 之后，worker 从 queued 到真正开始执行之间的等待。

Attempt 25 VM-only stats 显示：

```text
queued_to_start_avg_ns ~= 409 us / 1022 us / 872 us
```

这说明 `queue_work()` 之后的 worker 调度长尾是主要 submit/scheduler 成本之一。

### 设计

guest Panthor 主 scheduler workqueue 从：

```c
alloc_workqueue("panthor-csf-sched", WQ_MEM_RECLAIM | WQ_UNBOUND, 0);
```

改为：

```c
alloc_workqueue("panthor-csf-sched", WQ_MEM_RECLAIM, 0);
```

也就是保留内存回收语义，但不再使用 unbound worker。

### 测试结论

Attempt 26 VM-only stats：

```text
queued_to_start_avg_ns ~= 37 us / 17 us / 322 us
4/16 MiB scheduler wake 总量从 88 ms / 244 ms 降到 1.4 ms / 0.92 ms
```

正式 run：

```text
Attempt 26 Host/VM = 0.788 / 0.767 / 0.852
```

相对前面的 clean baseline，这对 4/16 MiB 是非常明显的改善，并且让 64 MiB 接近目标。

### 保留原因

这是当前 submit/scheduler path 上最有效且最简单的默认优化。它解决的是当前 2 vCPU/host 调度环境里 unbound worker 带来的 locality 和调度长尾问题。

### 不要混淆的反例

以下方向已经测试过，不是默认优化：

- `WQ_HIGHPRI`
- `WQ_HIGHPRI | WQ_CPU_INTENSIVE`
- deferred scheduler wake
- guest IRQ thread boost
- Firecracker `nice -10`
- guest `nohlt cpuidle.off=1`

这些方向要么只是移动了 wake 成本，要么改变 worker/vCPU 竞争，正式结果不稳定甚至回退。当前采用的是 bound workqueue，不是 high-priority workqueue。

## 5. Hot-path logging 清理

### 要解决的问题

GPU passthrough 的 completion path 很容易被日志污染。KVM ACK、VGIC IRQ inject、EOI fold、resample/unmask、Panthor map/PTE 等路径如果每次事件都 `pr_info()`，日志成本本身就会成为性能瓶颈。

历史上热路径日志导致：

- host `pmthor-job` masked window 达到毫秒级。
- guest raw-to-thread wait 达到毫秒级。
- 正式 Host/VM ratio 被人为压低，尤其是 4/16 MiB。

### 设计

保留必要错误日志，把热路径普通调试输出改为以下方式：

- 删除无条件 `pr_info()`。
- 改为 `pr_debug()`。
- 或做成默认关闭的 module parameter 统计。
- 或只在 perf loop 外 dump 聚合统计。

清理范围包括：

- host KVM ACK/resample notifier 路径。
- host VGIC IRQ inject、EOI fold、resample 路径。
- host direct Panthor/io-pgtable map/PTE 热路径。
- guest/host submit、IRQ、completion 路径的高频调试打印。

### 测试结论

关键正式结果：

```text
Attempt 15 清理 KVM ACK printk: 0.343 / 0.576 / 0.802
Attempt 16 继续清理 VGIC hot-path printk: 0.460 / 0.699 / 0.838
Attempt 18 清理 host map/PTE hot-path log: 4 MiB clean baseline 到 0.500
```

诊断结果显示，清理后 guest raw-to-thread 从毫秒级下降到几十微秒量级，host masked window 也大幅下降。

### 保留原因

这类修改看似只是“减少输出语句”，但在本项目里属于性能正确性的一部分。它不只是让日志变干净，而是去掉了对 IRQ/completion path 的人为干扰。后续任何热路径 debug 都必须默认关闭或聚合输出。

## 6. 默认关闭的低扰动诊断能力

### 设计目的

正式性能 run 不能打开 stats/timing，但没有诊断就无法判断下一步优化方向。因此保留一组默认关闭、按需打开、workload 后 dump 的诊断能力：

- `--guest-panthor-pt-timing`
- `--pmthor-irq-stats`
- `--guest-panthor-irq-stats`
- `--guest-panthor-submit-stats`
- `--vm-taskset-cpu`
- `--pmthor-irq-affinity-cpu`
- `--vm-huge-pages-2m`

这些开关的价值不是作为默认优化，而是帮助回答“为什么正式表里某个阶段慢”。

### 已经提供的关键认识

Page-table timing 证明：

- 64 MiB 早期主要成本是 GPA->HPA HVC，不是 fallback PTE fill。
- Attempt 30 后 HVC 成本明显降低，但 metadata 剩余开销不只来自 HVC。

IRQ timing 证明：

- 清理热路径日志后，guest IRQ thread scheduling 平均值已经不是主要瓶颈。
- 剩余 completion 问题更可能来自 host masked/resample/EOI 长尾、IRQ 密度、Mesa/fence wait。

Submit stats 证明：

- group submit 大头在 DRM scheduler wake/workqueue queue-to-start，不在 Panthor ringbuf/doorbell 本体。
- 这直接导向了 bound workqueue 优化。

### 保留原因

这些诊断能力避免了“凭感觉优化”。它们本身不应出现在正式 baseline，但它们指导出了真正有效的 Attempt 26 和 Attempt 30。

## 7. 测试规范和结果表达优化

### 设计

当前正式测试规范已经收敛为一张表：

```text
Workload | iter | total | metadata | submit | completion | map_unmap | Host phase share ref
```

所有性能列都是 `host/vm` ratio。阶段占总时间比例不再每次重算，而是使用固定 Host reference：

| Workload | metadata | submit | completion | map_unmap |
| ---: | ---: | ---: | ---: | ---: |
| 4 MiB | 79.0% | 6.7% | 14.4% | 0.07% |
| 16 MiB | 81.0% | 2.0% | 16.3% | 0.02% |
| 64 MiB | 80.0% | 0.75% | 19.3% | 0.01% |

### 保留原因

这不是内核技术优化，但非常重要。旧文档同时报告 absolute avg、VM perf percent、vm/host overhead、多张 phase 表和每次重算 share，很容易让判断分散。新格式把问题压缩成：

- 当前 VM 相对 host 的性能比例是多少。
- 哪个阶段慢。
- 这个阶段在 host 标准 workload 中大约有多重要。

这样后续优化可以快速判断“一个阶段 ratio 变好是否真的影响 total”。

## 8. 构建与部署效率优化

### 设计

当前默认规则：

- 单 VM passthrough 性能测试只构建普通 guest `Image`，不构建 vmshm client/proxy role kernel。
- host kernel 性能迭代优先 Image-only 部署。
- 如果只改少量 host module，用 selected-module sync，不做全量 modules install。
- `GPU-SFTP` 同步排除 run logs、大 rootfs 和 host kernel staging。

### 保留原因

这不直接改变 GPU task 性能，但极大影响优化效率。尤其 host module 全量 sync/install 很慢，而且很多 host kernel 改动只需要替换 boot Image。把构建和同步路径变短，可以让每次设计变更更快进入真实远程测试，而不是把时间耗在无关 artifact 上。

## 当前有效代码状态

当前默认性能代码状态可以概括为：

```text
guest Panthor/io-pgtable:
  - GPU page table 支持 SZ_4K | SZ_2M candidate。
  - 2 MiB candidate 安全检查 HPA 对齐/连续性，不满足时批量 fallback 到 4 KiB leaf table。
  - GPA->HPA batch translation 使用 per-io-pgtable scratch page 和统计。
  - PT timing stats 默认关闭。

host KVM:
  - GPA->HPA HVC 用 kvm_vcpu_map() 原地处理 guest array。
  - 保留 per page gfn_to_pfn_prot() pin/translation 语义。
  - KVM ACK/VGIC/resample hot-path printk 已清理。

guest Panthor scheduler:
  - panthor-csf-sched 使用 bound WQ_MEM_RECLAIM workqueue。
  - WQ_HIGHPRI / deferred wake 等反例不采用。

test harness:
  - 正式 run 不使用 tracing/stats/hugepages/affinity/nice/low-latency boot。
  - 正式 result 使用单张 Host/VM ratio 表。
  - 诊断开关默认关闭，按需 VM-only 使用。
```

当前采用主线的代表性高点是 Attempt 30 repeat：

```text
Host/VM = 0.830 / 0.875 / 0.907
```

最新单表格式验证 run 为：

```text
Run ID: gpu-perf-ratio-table-20260603-154030
RESULT: PASS
```

| **Workload** | **iter** | **total** | **metadata** | **submit** | **completion** | **map_unmap** | **Host phase share ref** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 100 | 0.779 | 0.847 | 1.109 | 0.485 | 0.723 | 79.0/6.7/14.4/0.07 |
| 16 MiB | 100 | 0.792 | 0.843 | 0.856 | 0.590 | 0.714 | 81.0/2.0/16.3/0.02 |
| 64 MiB | 20 | 0.882 | 0.865 | 0.694 | 0.971 | 0.923 | 80.0/0.75/19.3/0.01 |

两者差异说明正式性能仍有 run-to-run 波动，特别是 4/16 MiB completion/map_wait 长尾明显。因此看优化是否有效时，应优先看完整三档正式 sweep，并结合必要的 VM-only 诊断，而不是单次单档结果。

## 失败方向黑名单

这些方向已经证明不适合作为当前默认优化。除非前提条件发生实质变化，否则不要重复投入；如果重新测试，必须先说明新的假设和判定标准。

| 方向 | 黑名单原因 | 后续处理 |
| --- | --- | --- |
| BO 预分配、resident buffer、capacity reuse、bucket pool、BO reuse | 偏向同一任务重复提交或窄生命周期场景，不符合当前“每轮真实准备、上传、提交、等待、读回”的 GPU task 测试口径；相关代码和测试已删除。 | 不再作为默认优化方向。只在用户明确要求研究长期驻留资源或新 API 生命周期时重开。 |
| guest job IRQ hardirq fast path、raw ack、raw prequeue | 改变 IRQ clear、EOI、event 和 scheduler 排队时序，正式结果回退，且容易把成本转移到 hardirq path。 | 不再采用。若追 completion，只先做低扰动 timing，再分析 host masked/resample/EOI 长尾和 fence wait。 |
| raw-unmask HVC | 64 MiB 单次可达标，但 16 MiB 回退；存在 duplicate unmask/resample 语义问题，并给 guest raw handler 增加 HVC 成本。 | 相关代码和脚本入口已删除；只作为历史反例保留在黑名单中。 |
| `WQ_HIGHPRI`、`WQ_HIGHPRI | WQ_CPU_INTENSIVE`、deferred scheduler wake | 没有稳定改善整体结果；deferred wake 只是移动成本，高优先级 workqueue 会改变 vCPU/worker 竞争并引入长尾。 | 不再简单调高优先级或移动 wake 调用。scheduler 方向只保留已采用的 bound workqueue。 |
| guest IRQ thread boost | Linux IRQ thread 已有实时调度语义，显式 boost 没有降低 raw-to-thread 延迟，反而使 VM-only timing 变差。 | 相关开关已删除；不再默认或诊断使用。 |
| Firecracker `nice -10` | 没有降低核心 IRQ latency，VM iteration time 变差。 | 相关脚本入口已删除；只作为历史反例保留在黑名单中。 |
| guest `nohlt cpuidle.off=1` 低延迟启动 | VM-only timing 明显变差，不能作为默认低延迟方案。 | 相关脚本入口已删除；只作为历史反例保留在黑名单中。 |
| 默认固定 affinity | VM/IRQ 分核对部分小中 workload 有帮助，但 64 MiB 回退，跨 workload 不稳定。 | 可作为诊断工具；正式 baseline 不固定 affinity，除非实验明确研究拓扑。 |
| 单纯增加 shader ALU workload | `--alu-iters 64` 没有摊薄虚拟化开销，反而让 completion 行为更差。 | 只能作为单独 workload 轴分析，不用它证明默认 passthrough 优化有效。 |
| 只靠远端临时 hugepage 申请验证 2 MiB block PTE | 远端 hugepage 可用性受内存碎片影响，曾因需要 `960` 个 2M hugepages 但只有 `108` 个而失败，不能直接得出性能结论。 | 若继续追真实 2 MiB block PTE，需要提前规划 guest memory/backing 对齐或缩小 VM memory，再正式测试。 |

## 后续优先方向

1. 继续追 4 MiB completion/map_wait 长尾。

   Attempt 31 之后，平均 guest IRQ thread latency 已经很低，下一步要看 host masked/resample/EOI 长尾、job IRQ density、Mesa/fence wait 和 map_wait 内部拆分。

2. 对 metadata path 做更细分归因。

   Attempt 30 已经降低 HVC array handling，后续应区分 CPU prepare、buffer upload、Mesa/DRM BO create、VM_BIND、page-table population、GPA->HPA translation，而不是把所有 metadata 都归因到 HVC。

3. 如果继续追真实 2 MiB GPU block PTE，先解决 HPA 对齐。

   当前 `2m_blocks=0` 的根因多半是 backing HPA base unaligned。需要从 allocation/backing 侧解决，而不是只改 io-pgtable。

4. 保持正式测试口径稳定。

   任何优化完成后，都必须回到无 tracing、无 stats、无诊断开关的正式 host-vs-VM sweep，并用单张 Host/VM ratio 表判断是否真的提升。
