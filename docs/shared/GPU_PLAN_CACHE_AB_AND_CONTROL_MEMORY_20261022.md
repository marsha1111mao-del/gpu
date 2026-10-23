# GLMark：Submission-Plan Caching 收益与控制结构内存计量

本实验用同一组 Client/Proxy 内核，切换 `panthor_client.plan_cache=1/0`，比较缓存执行与单 RPC 即时解析。正式分数关闭 RPC 计时及分配账本；内存与提交阶段另用诊断轮测量。

> 当前状态（2026-10-23）：本页是已完成实验的历史证据。由于对照未证明稳定明显提分，当前开发源码已删除仅供A/B使用的`plan_cache=0`/`UNCACHED_SUBMIT`旁路和控制结构分配账本，只保留正式`PLAN_REGISTER/PLAN_EXEC`实现。下列结果、失败项、源码diff、冻结输入及分析工具继续保留；这里记录的实验接口不再是当前兼容ABI。此次清理未改板端载荷，无新增性能测量。

## 同条件分数对照

| 分辨率 | 关闭缓存，两轮 | 开启缓存，两轮 | 关闭均分 | 开启均分 | 分差 | 变化 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1280×720，单 Client | 1157 / 1150 | 1158 / 1158 | 1153.50 | 1158.00 | +4.50 | +0.39% |
| 1920×1080，单 Client | 900 / 902 | 900 / 902 | 901.00 | 901.00 | +0.00 | +0.00% |

**本轮结论：未证明 Submission-Plan Caching 带来可重复的 GLMark 明显提分。720p 观测增加 0.39%，小于关闭组两轮的 7 分差；1080p 开关两组均分完全相同。不能把此前较低的 lookup / validate / assemble 耗时或已有整体性能归功于缓存一项。**

变化按 `(开启均分 / 关闭均分 − 1) × 100%` 计算。每组只有两轮；小于轮间波动的差异只能视为本次观测，不能包装成稳定收益，也不能把提交阶段的时间占比当作整帧提分比例。

条件：RK3588 / Mali-G610；同一 Host #31、RMM、VMM、只读用户态、33 个 glmark 场景及 null-noop / finish；单 Client，CPU 最低＝最高＝1.8 GHz，GPU 请求 600 MHz / 实际 594 MHz。Proxy vCPU 在 CPU1、Client 在 CPU2，VMM I/O 在 CPU0；720p / 1080p 分别使用 128 / 192 MiB 源池，TRANSFER 预捕获、完成证明、短时回复轮询和通知策略保持一致。实际频率与落核经 Host 采样独立核对。

720p 按开启→关闭→关闭→开启运行，1080p 按关闭→开启→开启→关闭运行。Native 本轮未重跑，不用历史 Native 分数计算新的同期保留比例。

实验从 2026-10-22 延续至 2026-10-23，run-id 沿用开始日期；每轮时间以 lab 记录为准。

## 对照究竟关闭了什么

- 开启：首次 `PLAN_REGISTER` 固定 group、queue/sync 布局和原生对象引用；命中后 `PLAN_EXEC` 发送计划标识及动态字段。
- 关闭：`UNCACHED_SUBMIT` 一次传入完整结构，每次查找对象、检查固定关系、临时持有引用并提交，随后释放临时引用。它不先发 REGISTER，因此没有人为增加一次串行往返。
- 两条路径共用固定结构检查、动态参数检查、原生 Panthor 接纳、调度器和完成证明。关闭缓存仍保留真实 fence 语义。

关闭路径是为本轮隔离变量新增的单 RPC 对照，并未回退历史上其他提交、同步和通知机制。因此结果回答的是“当前架构中缓存模板的边际收益”，不能当成缓存引入前后所有历史改动的组合收益。

固定请求 payload 从 472 B 变为 248 B，减少 47.46%；消息槽仍为固定 512 B，接收端也保留完整槽快照。因此这不代表队列容量、总复制量、RPC 延迟或整帧时间同比下降。Client 的计划槽内嵌在文件对象内，运行时关闭缓存不会自动缩小这个结构。

## 1080p 提交阶段诊断

以下来自同时开启内存账本和 RPC 计时的独立诊断轮，不能替换正式分数。均值为完整运行中各阶段累计时间除以执行尝试数，包含验证、计分和退出阶段；两侧任务构成的加权可能不同。

| 阶段 | 关闭缓存 μs | 开启缓存 μs | 关闭 − 开启 μs |
| --- | ---: | ---: | ---: |
| RPC 残差：传输、排队及剩余等待 | 62.847 | 63.213 | -0.366 |
| lookup | 1.007 | 0.406 | +0.601 |
| validate | 0.879 | 0.549 | +0.329 |
| assemble | 0.664 | 0.309 | +0.355 |
| native | 16.645 | 16.635 | +0.011 |
| aux：完成观察及尾部记账 | 3.579 | 3.662 | -0.083 |
| 同步往返合计 | 85.621 | 84.774 | +0.847 |

lookup + validate + assemble 从 2.549 降至 1.264 μs，减少 1.286 μs / 50.43%。这说明缓存确实减少了重复解析；但 RPC 残差仍约 63 μs、原生同步接纳约 16.6 μs，局部节省仅约 1 μs，未转化为正式 GLMark 明显提分。诊断均值按各自运行调用数加权，不能当作相同每帧工作的严格配对时间。

关闭：执行尝试 345950 次，实际原生提交 345950 次，注册 0 次；执行及注册 RPC 时间摊到每次最终原生提交为 85.621 μs。
开启：执行尝试 347395 次，实际原生提交 347253 次，注册 150 次；执行及注册 RPC 时间摊到每次最终原生提交为 84.833 μs。

`native` 是创建 job、处理依赖和接纳调度的同步时间，不是 GPU 执行时间；RPC 是扣除已单列处理阶段后的残差，不是纯 RMM 时间。低 validate 均值也不表示所有安全检查都在这一阶段。旧 81.152 μs 测量未启用本轮分配账本，不能把两轮绝对延迟差全部归因于缓存。

## 私有控制结构：直接计量

启动参数 `realm_xshm_control.enabled=1` 开启账本，`/proc/xshm_control_memory` 输出总账和分配点账本；默认关闭。`requested/allocated` 为当前存量，`peak_requested/peak_allocated` 为该 Guest 内的统一峰值，`*_in/*_out` 为累计分配/释放字节。累计分配字节不能当作驻留内存。

在 Client/Proxy DRM 桥、对象管理器与通信层的分配/释放处记账，以分配地址对应真实生命周期。记录申请字节、分配器对象容量、累计分配/释放、当前存量和峰值；自建 slab 用其对象申请大小及 ksize，vmalloc 后备用页按页取整。devm 管理对象的分配器容量包含其同一后备对象的 devres 头部，不能视作全部可写业务空间。计量工具自身的记录与读缓冲单独列出，不混入业务结构。Client fence 在实际 RCU 释放回调中扣账。

| 场景 | Proxy 跟踪申请峰值 KiB | Proxy 分配器峰值 KiB | Client 跟踪申请峰值 KiB | Client 分配器峰值 KiB |
| --- | ---: | ---: | ---: | ---: |
| 1080p，缓存关闭 | 1173.62 | 2098.05 | 35.49 | 43.73 |
| 1080p，缓存开启 | 1187.29 | 2116.05 | 35.49 | 43.73 |
| 720p，缓存开启 | 782.61 | 1061.05 | 36.24 | 44.62 |

每个 Guest 的总峰值在每次分配/释放时统一更新，避免各类历史峰值相加。Proxy 与 Client 的峰值可能不同时发生，因此也不能把两列峰值相加称为系统同时峰值。分配器对象容量不含完整 slab 空闲页、vmalloc 辅助结构等成本，不能等同整机物理内存增量。

1080p 两轮同时开启 RPC 计时，跟踪总量还包含 Client 的 RPC 统计快照临时缓冲：`rpc_stats_dump_current_if_enabled` 和 `rpc_stats_set`。它们属于诊断开销，各分配点单列，不能包装为正常转发必须的业务内存，也不能直接从总峰值减去两个独立峰值。720p 内存轮未开启 RPC 计时，没有这些诊断快照分配。分配账本自身的记录与读取缓冲则始终另列，不计入上述跟踪总量。

| 场景 / Guest | workload 后当前 KiB | detach 后当前 KiB | 观察记录峰值 KiB | 账本静态区 KiB | 单次读取缓冲 KiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1080p，缓存off / Proxy | 2050.25 | 0.00 | 16.75 | 11.09 | 16.00 |
| 1080p，缓存off / Client | 0.00 | 0.00 | 24.44 | 11.09 | 16.00 |
| 1080p，缓存on / Proxy | 2050.25 | 0.00 | 16.88 | 11.09 | 16.00 |
| 1080p，缓存on / Client | 0.00 | 0.00 | 24.44 | 11.09 | 16.00 |
| 720p，缓存on / Proxy | 1026.25 | 0.00 | 17.19 | 11.09 | 16.00 |
| 720p，缓存on / Client | 0.00 | 0.00 | 24.94 | 11.09 | 16.00 |

观察记录、账本静态区及读取缓冲属于计量工具，单列而不计入业务控制结构。detach 后的当前存量需要结合设备及通信层仍存活的分配点解释，不能仅凭非零值判内存泄漏。

1080p 缓存开启时，以下展示各分配点的独立峰值；这些行不能相加作为同时峰值：

| Guest / 分配点 | 申请峰值 KiB | 分配器峰值 KiB |
| --- | ---: | ---: |
| Proxy：`proxy-manager:proxy_vmshm_buddy_init` | 1134.250 | 2048.250 |
| Proxy：`proxy-manager:proxy_vmshm_sg_alloc_backing_locked` | 36.000 | 48.000 |
| Proxy：`proxy-manager:proxy_vmshm_alloc_ext` | 24.000 | 24.000 |
| Proxy：`proxy-drm:panthor_proxy_session_bo_create` | 4.961 | 7.938 |
| Proxy：`proxy-drm:panthor_proxy_plan_register` | 1.148 | 1.500 |
| Proxy：`proxy-manager:proxy_vmshm_manager_register_domain` | 0.523 | 1.000 |
| Proxy：`proxy-transport:proxy_comm_vmshm_probe` | 0.633 | 1.000 |
| Proxy：`proxy-drm:panthor_proxy_point_watch` | 0.688 | 0.750 |
| Proxy：`proxy-drm:panthor_proxy_session_create` | 0.320 | 0.500 |
| Proxy：`proxy-drm:panthor_proxy_session_syncobj_create` | 0.281 | 0.281 |
| Proxy：`proxy-manager:proxy_vmshm_grant_create` | 0.062 | 0.062 |
| Proxy：`proxy-drm:panthor_proxy_session_vm_create` | 0.023 | 0.031 |
| Proxy：`proxy-drm:panthor_proxy_session_tiler_heap_create` | 0.031 | 0.031 |
| Proxy：`proxy-drm:panthor_proxy_session_group_create` | 0.016 | 0.016 |
| Client：`client-drm:panthor_client_bo_create` | 17.859 | 23.812 |
| Client：`client-transport:client_comm_vmshm_rpc_stats_dump_current_if_enabled`（RPC诊断临时缓冲） | 10.000 | 16.000 |
| Client：`client-transport:client_comm_vmshm_rpc_stats_set`（RPC诊断临时缓冲） | 10.000 | 16.000 |
| Client：`client-manager:client_vmshm_manager_get` | 14.000 | 14.000 |
| Client：`client-drm:panthor_client_syncobj_export_sync_file` | 4.688 | 4.688 |
| Client：`client-drm:panthor_client_open` | 2.203 | 4.000 |
| Client：`client-drm:panthor_client_syncobj_alloc` | 1.805 | 2.062 |
| Client：`client-drm:panthor_client_completion_page_init` | 0.609 | 1.000 |
| Client：`client-drm:panthor_client_tiler_heap_create` | 0.039 | 0.062 |
| Client：`client-drm:panthor_client_group_create` | 0.023 | 0.031 |

1080p 的 Proxy buddy 管理分配点申请峰值约 1.11 MiB，分配器对象容量约 2.00 MiB，是本次已跟踪管理开销的主要来源；计划缓存分配点峰值仅 1.50 KiB。开关两轮 BO/SG 同时存活数量和采样峰值不同，不能把两轮总峰值之差全部归因于缓存。

对象引用不重复计费：保存一个 syncobj 引用只计指针所在的结构，底层对象本身按一次分配记录；内嵌计划数组已经包含在 Client 文件对象中。Guest 账本覆盖列出的分配点，未覆盖 XArray/IDA 内部分配、原生驱动公共对象、固件全局静态资源以及全部 OS/VM 固定预算。这里是明确范围内的直接计量，不能声称整个系统控制内存已完整覆盖。

## RMM 租约表：全局固定容量

RMM 未重新部署。对当前使用的已部署固件 ELF 核验 SHA，再读取符号大小，可以单独确认以下固定 BSS 数组。这是全局容量成本，不是每 Client 独占开销，也不是本轮新增分配：

| 固件结构 | 字节 | MiB |
| --- | ---: | ---: |
| `buckets` | 524288 | 0.50000 |
| `dma_maps` | 32768 | 0.03125 |
| `gpu_batch` | 65536 | 0.06250 |
| `leases` | 12582912 | 12.00000 |
| 上述四项合计 | 13205504 | 12.59375 |

其中 `leases` 为 524288 项 × 24 B，预留支持 2 GiB 不重复 4 KiB 页；`buckets` 为哈希桶，`dma_maps` 为 DMA 映射记录容量，`gpu_batch` 为每 CPU 批处理暂存。GPU/DMA 租约数归零仅代表没有活跃记录，不会回收这些静态数组。此表不包含 RMM 其他全局结构、GPU 页表和保护粒度取整，不把它与 Guest 独立峰值混加为整机实测峰值。

## 共享池：容量成本独立列出

池与进程 PSS 每 200 ms 采样；下表取 GPU BO 请求最大的采样点，可能漏掉更短暂的瞬时峰值。前述私有控制账本的峰值则在每次分配/释放时更新，不依赖采样周期。

| 场景 | 源池 MiB | GPU BO 请求采样峰值 MiB | 当时 buddy 空闲 MiB | 当时其他池内对象 MiB | 分配取整/未归属占用 MiB | 控制窗口及对齐预留 MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1080p，缓存关闭 | 192.000 | 165.625 | 23.371 | 0.004 | 0.000 | 3.000 |
| 1080p，缓存开启 | 192.000 | 169.645 | 19.352 | 0.004 | 0.000 | 3.000 |
| 720p，缓存开启 | 128.000 | 90.555 | 34.441 | 0.004 | 0.000 | 3.000 |

源池全部已有物理后备。3 MiB 包括 1 MiB 通信控制窗口和 2 MiB manager 对齐/保留，不能整体称为实际控制结构；buddy 空闲同样是已占用源池中的容量余量。BO 请求与其他对象之和若小于 buddy 已占用量，差额保留为分配取整或未归属占用，不直接归给控制数据。

固定通信布局按本次 ABI 的 2 个队列、每队列 256 个 512 B 消息槽核算，占用区间为 282176 B（275.56 KiB，含对象表容量及对齐）；其中消息槽容量为 256 KiB。该布局包含在上述 1 MiB 控制窗口内，不能再加到完整源池之外。这是源码布局核算，不冒充逐请求活跃 payload 实测。

CPU 用户态仍采集 glmark 的匿名页及文件页 PSS，Proxy 内核协议结构由独立账本覆盖；进程 PSS不当作整个 Client/Proxy 系统成本。本轮不把共享池余量、两个 Guest 的独立峰值及历史 Native 分项混合相减来推算安全开销。

旧目标后备页沿用已验证的回收实现；本轮未重新启用 Host gmem 探针，不将旧的 0 MiB 当成本轮新测读数。

## 正确性、失败与复现

正式分数与诊断轮均完成 33 个场景，Mali renderer、validation（26 成功 / 1 既有数值例外 / 6 无判据）及 clean 检查通过；缓存开/关各有双 Client 功能、19 项 API/快照语义及实际计算验收。每轮 Host/Guest 内核健康、GPU/DMA 租约最终归零、CPU/频率/驱动及普通运行输入恢复均独立检查，原始证据逐文件 SHA 校验。内存账本 lost=0，分类累计值和总账守恒检查通过。

先前一个准备轮在进入 glmark 前因通信处理器表满而失败，已将新增实验请求所需的容量从32修正为33；该轮不计成绩。另有分配适配和模块符号表准备的构建失败，均修正后才部署。旧门槛轮1160分单独保留，不混入最终同镜像两轮均值。未进行多 Client 性能及 Native 新矩阵。

| run-id | 类型 | 结果 |
| --- | --- | --- |
| `plan-cache-api-off-0-20261022-a` | api / cache off | PASS / rc0，双Client功能 |
| `plan-cache-api-on-0-20261022-a` | api / cache on | PASS / rc0，双Client功能 |
| `plan-cache-memory-off-1080-20261022-a` | memory / cache off | PASS / rc0，870分 |
| `plan-cache-memory-on-1080-20261022-a` | memory / cache on | PASS / rc0，874分 |
| `plan-cache-memory-on-720-20261022-a` | memory / cache on | PASS / rc0，1129分 |
| `plan-cache-performance-off-1080-20261022-a` | performance / cache off | PASS / rc0，900分 |
| `plan-cache-performance-off-1080-20261022-b` | performance / cache off | PASS / rc0，902分 |
| `plan-cache-performance-off-720-20261022-a` | performance / cache off | PASS / rc0，1157分 |
| `plan-cache-performance-off-720-20261022-b` | performance / cache off | PASS / rc0，1150分 |
| `plan-cache-performance-on-1080-20261022-a` | performance / cache on | PASS / rc0，900分 |
| `plan-cache-performance-on-1080-20261022-b` | performance / cache on | PASS / rc0，902分 |
| `plan-cache-performance-on-720-20261022-b` | performance / cache on | PASS / rc0，1158分 |
| `plan-cache-performance-on-720-20261022-c` | gate / cache on | PASS / rc0，1160分 |
| `plan-cache-performance-on-720-20261022-d` | performance / cache on | PASS / rc0，1158分 |
| `plan-cache-performance-on-720-20261022-a` | 准备失败，不计成绩 | FAIL / rc1，进入GLMark前处理器表容量不足 |

证据根：`build/plan-cache-ab-20261022/`。`v3/`保存最终四组冻结输入，`provenance.json`记录源码及构建哈希，`runs/<run-id>/`保存验证后的原始日志，`observations/`保存频率/落核采样，`analysis.json`保存未取整字节及计时；每轮实际命令、退出码、租约和恢复记录位于`build/lab-runs/<run-id>/`。

末次 Pi/RK 资源检查 `final-resources.json` 为 issues=[]，无实验残留进程；RK 已恢复 CPU0–1 / pmthor，无实验 loop 或挂载。普通 candidate-c 的四项运行输入逐文件恢复并校验，未把实验 bundle 留作默认部署。

复核命令：

```bash
python3 scripts/analysis/analyze-plan-cache-glmark.py --experiment build/plan-cache-ab-20261022
```

复测使用标准 lab-run 独占入口和新的 run-id，按冻结 bundle 选择缓存开/关；正式分数不启用 `--rpc-stats` 或 `realm_xshm_control.enabled=1`，诊断轮才开启。实验未替换正式性能主表或发布载荷。

例如，设置好实验室凭据后复测关闭缓存的 720p（`RUN_TAG` 必须为新的唯一标识；冻结目录需先核对 `hashes.json`）：

```bash
python3 scripts/maintenance/lab-run.py --run-id "$RUN_TAG" -- \
  python3 build/plan-cache-ab-20261022/restore-after.py \
  python3 build/plan-cache-ab-20261022/observe-run.py \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/plan-cache-ab-20261022/v3/performance-off \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720 \
  --clients 1 --compact-memory --pool-mib 128 --client-cpu-layout round-robin \
  --cpu-frequency-khz 1800000 --telemetry --transfer-capture
```
