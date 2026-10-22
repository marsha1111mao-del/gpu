# 原生与 Client/Proxy GPU 任务内存实测（2026-10-21）

**后续更新（2026-10-22）：** 本文保留优化前测量。旧目标后备回收已实现并实测：384 MiB→0，已测分项峰值合计903.26→519.33 MiB（−42.50%），相对原生额外14.35%。新测试、性能差异及未完成项见[回收优化报告](GPU_SHARED_MEMORY_RECLAIM_20261022.md)；下文“尚未实现”描述仅对应本次优化前状态。

单 Client ResNet50 对照已完成：**按已测各分项峰值合计，原生约454.17 MiB，共享方案约903.26 MiB，增加449.09 MiB / 98.88%；额外部分占共享方案已测合计的49.72%。** 这不是整机内存，也不是所有分项在同一时刻发生的总峰值；尚未逐项计量的协议私有分配未包含在内。

最主要的额外来源是 **Client 挂接目标区原有384 MiB物理后备页仍滞留在 Host guest_memfd 缓存中**，其次是源池内约56.23 MiB空闲及控制/对齐预留。不能再把目标区描述为只增加启动瞬时需求，也不能仅凭 VMM RSS 不变认定它已经释放。

## 对照结果

单位为 MiB（2²⁰字节）。原生是两轮各分项峰值的均值，共享是一轮；未测项不按零处理。

| 内存项目 | 原生 | Client/Proxy | 口径 |
| --- | ---: | ---: | --- |
| GPU 用户 BO：权重、中间结果、工作区等 | 327.77 | 327.77 | 两侧用户 BO 请求峰值均为343687168字节；原生有同等大小已取得后备页的样本，共享包含在下面的384 MiB源池内 |
| CPU侧模型、加载和运行缓冲及用户态库 | 126.40 | 133.02 | `benchncnn`的`Pss_Anon + Pss_File`峰值；不含整个Guest普通内存预算 |
| 池内未被对象占用的空间 | 无本项目固定池 | 56.23 | buddy空闲53.23，加池内控制/分配对齐预留3.00；已在384 MiB源池内 |
| 池内其他对象 | 不适用 | 0.0039 | 4096字节fence页；已在384 MiB源池内 |
| Client原目标后备页 | 不适用 | 384.00 | 与源池不同的物理存储；挂接后仍在guest_memfd缓存中 |
| Proxy分配器私有元数据 | 不适用 | 至少2.24 | 已计量domain、buddy、对象、grant、slab及SG描述结构的申请字节下限 |
| **已测分项峰值合计** | **454.17** | **903.26** | 原生=CPU+用户BO；共享=CPU+完整源池384+目标后备384+元数据下限 |

源池关系为：`384 = 327.765625（GPU BO）+ 0.00390625（fence）+ 53.23046875（buddy空闲）+ 3（控制/对齐预留）`。**表内BO、空闲及fence均为源池分解，不能再在384 MiB之上重复相加。**

原生两轮CPU峰值分别124.79 / 128.02 MiB，用户BO已取得后备页峰值均327.77 MiB，各分项峰值合计452.55 / 455.79 MiB，均值454.17 MiB。共享CPU峰值133.02 MiB。两侧CPU相差约6.61 MiB，包含用户态分配与执行环境差异，不能直接归因为代理协议本身。

相对原生，已测449.09 MiB增量可拆为：目标后备384 MiB、源池剩余空间及fence约56.23 MiB、已计量私有元数据约2.24 MiB、CPU峰值差约6.61 MiB。**约85.51%的已测增量来自滞留的目标后备页。**

若将来确实消除这384 MiB后备页，并假设其他分项不变，已测合计可由903.26降至519.26 MiB，对原生约增加14.33%。这是按本轮分项作的估算，**尚未实现、未测得这个优化结果**。继续压缩池内余量可能降低预留，但本轮未验证更小池能否完成相同负载。

## 为什么目标区还占物理内存

Client先从自身CMA取得目标区，再由共享挂接替换其Realm映射。映射替换并未同时移除该IPA区间原有guest_memfd缓存页。

在共享工作负载仍运行时，对两个VMM各自的guest_memfd进行只读检查：

| 区域 | 请求页数 | 实际缓存页数 | 仅剩缓存引用的页数 |
| --- | ---: | ---: | ---: |
| Proxy源池 | 98304 | 98304 | 0 |
| Client原目标区 | 98304 | 98304 | 98304 |

Client全部目标页`folio_ref_count == 1`，只剩缓存引用；它们仍是实际物理页，源池另有其自身物理页和活动引用。此guest_memfd缓存不能当作普通可随时回收的文件缓存。诊断按VMM fd和IPA区间读取页缓存，不用VMM RSS代替私有Guest物理内存统计。

证据为`build/gpu-task-memory-20261021/gmem-a.json`、`gmem-a-command.log`和`host-backing-a.txt`。挂接路径并未复制一份模型数据；这里多出来的是仍然保留的旧目标后备。

## 实验条件与统计边界

- 同一RK3588 / Mali-G610、Host `6.12.0-opencca-pmthor-opp3 #31`、RMM timer-v6 + 1 GiB租约。原生临时切至nVHE，Realm使用protected hVHE；比较的是两套实际执行栈。
- 同一只读rootfs、Mesa/NCNN及workload脚本；ResNet50、224×224×3、100 loops、2 NCNN threads、GPU0、panvk-direct。随机输入/权重负载不证明模型准确率。
- 共享为单Client、384 MiB池，Proxy/Client配置624/704 MiB；这些VM配置预算不直接放进对比表。Client单vCPU可落CPU2–3，原生进程固定CPU2，Proxy使用CPU1；未锁CPU恒定频率。GPU请求600 MHz，共享记录实际594 MHz，原生sysfs报告600 MHz。
- 每200 ms采样一次。原生两轮各922/923个样本，其中917/919个含模型进程；共享Proxy1744、Client1963个样本，其中934个含模型进程。采样峰值可能漏过极短瞬间。
- 原生probe区分`panthor_gem_create_with_handle`产生的用户BO与驱动内部BO。全部GEM峰值338.04 MiB，表内只使用用户BO327.77 MiB；未将驱动控制BO约10.28 MiB混入用户任务口径。
- 不计Guest/Proxy/Host的普通OS、VM固定预留、Host驱动、GPU页表、采样器及诊断模块本身。CPU排除`Pss_Shmem`，避免与独立统计的GEM后备重复计数。
- 已计量元数据是结构申请字节下限，不包括全部xarray节点、分配器取整，以及Client/Proxy全部队列私有副本、请求快照、完成记录等。池内控制区已经包含在384 MiB内，不能把2.24 MiB当作所有转发及安全检查的总开销；本轮无法给出这部分完整占比。
- 两侧总览均采用各分项峰值相加。原生在同一次采样中观测到的CPU+用户BO峰值为392.03/392.18 MiB，低于分项峰值相加，说明CPU加载峰值与GPU后备峰值有阶段差异。**不把454.17或903.26 MiB称作严格同时发生的物理总峰值。**

## 执行、失败与恢复

| run-id | 状态 / 退出码 | 验证与保留问题 |
| --- | --- | --- |
| `memory-realm-resnet50-20261021-a` | PASS，外层rc0，Realm退出0/0 | 模型1217.04 ms；模型后端及完成标记通过，Host/Guest七类健康检查通过，GPU/DMA租约最终均0；推理结束后回传日志阶段有一条`sched: DL replenish lagged too much`，保留警告 |
| `memory-native-resnet50-20261021-a` | FAIL，rc1，模型未执行 | 上传采样器时缺少可执行位，`PermissionError`；不是内存不足或GPU任务失败。失败输入/日志保留，protected及设备状态恢复通过 |
| `memory-native-resnet50-20261021-b` | PASS，两轮任务及外层rc0 | 修正上传后的chmod与可执行检查后运行；1164.03 / 1165.00 ms，模型与内核检查通过；最终GEM对象0，创建/释放2430/2430，漏记/溢出/漏探针均0 |

耗时只记录本轮观测，不作为内存优化或性能提分证据。Native-b结束后原extlinux逐字节恢复，同Host Image SHA保持不变，已回到protected、Realm能力1、pmthor、CPU0–1及GPU300 MHz；无本次模型/采样进程、诊断模块或loop残留。Pi/RK资源检查rc0。

本轮不修改GPU运行代码，只增加实验诊断工具；仓库runner的健康日志扫描改为逐行匹配，保持七类错误、CR/LF和去重语义，等价检查通过。运行中的冻结旧runner未被修改；新扫描器未进行新硬件部署。原生a的失败不计入均值，历史ResNet50三/四Client的内存准入拒绝及其他ML失败均不改变。

改动目的｜量化排除OS预算后的任务内存与共享增量｜对照既有公平单Client完整720p **1158** → 本轮 **未测glmark**｜分差及百分比不适用｜仅增加诊断测量，Native/Realm模式不同｜下列命令、rc及证据｜保留实测结论，目标后备回收优化待开发验证，不宣称提分。

## 复现与证据

使用已配置的SSH环境变量，经独占入口执行。健康板不重新刷写；本实验Native控制器只临时改启动模式，并恢复相同Image及原启动配置。

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id memory-realm-resnet50-20261021-a -- \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/gpu-task-memory-20261021/bundle \
  --workload glmark --performance --benchmark-only --suite \
  --profiles ncnn-resnet50 --clients 1 --compact-memory --pool-mib 384

python3 scripts/maintenance/lab-run.py \
  --run-id memory-native-resnet50-20261021-b --allow-rk-reboot -- \
  python3 build/gpu-task-memory-20261021/native-mode.py --round b

python3 build/gpu-task-memory-20261021/analyze.py \
  --realm build/gpu-task-memory-20261021/realm/memory-realm-resnet50-20261021-a \
  --native build/gpu-task-memory-20261021/native/memory-native-resnet50-20261021-b \
  --gmem build/gpu-task-memory-20261021/gmem-a.json \
  --output build/gpu-task-memory-20261021/results.json

python3 build/gpu-task-memory-20261021/final-audit.py
```

前三条实际执行退出0，独立核验为PASS/rc0；重跑使用新run-id。`--workload glmark`为既有启动选项，实际仅执行显式ResNet50 profile。

全部本地证据位于`build/gpu-task-memory-20261021/`（Git忽略的实验归档）：

| 内容 | 位置 |
| --- | --- |
| 逐项原始采样、模型日志、summary、逐文件SHA | `realm/memory-realm-resnet50-20261021-a/`、`native/memory-native-resnet50-20261021-b/` |
| 失败及对应输入 | `native/memory-native-resnet50-20261021-a/`、`failed-native-a-inputs/` |
| 结果、独立核验、恢复资源 | `results.json`、`final-audit.json`、`postflight.json`、`restored-diagnostics.json` |
| 诊断源码与冻结输入哈希 | `memory_sample.c`、`pool_memory.c`、`native_memory.c`、`gmem_memory.c`、`bundle/hashes.json`、`native-b-inputs.json`、`sources.json` |
| 外层锁、命令、退出码、租约及恢复记录 | `build/lab-runs/<上述run-id>/`中的`result.json`、`native-mode.json`、`lease-monitor.json`及前后资源 |

共同rootfs SHA-256：`5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60`；Client Image：`31f31f15c148bba2194bb1ccc0335f6bdbd300729ca0278ed1431fa439420647`；Proxy Image：`f3c3f28e25617784d7d681fa6a1270b5561eaf82526e9ce41a97e9fd399103fc`。诊断initrd为`77219acb4ae43c81e2be321cd615aace986b7267bb5a8530756a90de75a9a452`。Native两轮及共享采集文件SHA均由独立核验重新检查。
