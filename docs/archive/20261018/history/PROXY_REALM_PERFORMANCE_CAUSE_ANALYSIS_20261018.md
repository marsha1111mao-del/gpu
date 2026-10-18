# Proxy Realm 性能下降原因分析

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-18。本次只分析本地源码、冻结输入、修改记录与已回收日志；没有改动驱动、固件或板端配置，没有新增硬件性能实验。

当前版本完成了功能流程，但没有达到此前普通 VM 方案的性能。主要问题是：原性能配置没有移入 Realm runner，空闲 Realm/调度问题仍存在，可信事件以多次 SMC 包装了原有高频同步 RPC；任务计划只优化提交的一部分，尚未形成异步提交与完成的流水线。不能把功能 PASS 写成性能目标完成。

## 1. 先核对比较对象

| 记录 | 720p score | 条件 / 含义 |
| --- | ---: | --- |
| 10-16 普通 VM 优化方案 | 1058 | GPU 实际 594 MHz，CPU 0–3；Proxy 1、Client 2；并发 RPC、完成点缓存开启 |
| 10-17 任务计划 src6/src8 | 507 / 507 | CPU 0–1；说明引入计划不自动产生性能提升，亦不可直接与优化 profile 相比 |
| 10-17 任务计划 src9 | 1058 | 普通 VM 路径，使用原 opp3 性能 profile；计划机制本身已有高分运行记录 |
| Realm 早期轮询 / IRQ | 7 / 10 | 功能阶段，存在固件 ACK 超时、逐次 RSI 日志等问题，不能作为合格性能基线 |
| Realm RSI trace-off | 94 | 部分运行仍有 GPU 超时甚至提交失败，失败保留 |
| Realm 分层 doorbell / 队列发布修正 | 98 / 98 | 各一轮完整 33 场景、受检故障为零；GPU 观测 300 MHz，CPU 0–1，默认性能开关关闭 |

分辨率均指 1280×720。高分旧方案与最新 Realm 版均用 null-noop、frame-end finish，故同步往返会直接进入帧时间。
98/1058 约为 9.26%，但两者不是同条件 A/B，不能分解成各模块的下降百分比。
任务计划 src9 已有 1058，尤其不能将退化简单归因于 PLAN_REGISTER/PLAN_EXEC 的设计。
当前 RSI trace 已关闭，受检 CSG 等故障为零；早期日志及超时问题解释部分历史低分，
不能再次将它们作为当前 score 98 的已证实原因。

依据：[旧性能报告](GPU_GLMARK_PERFORMANCE_REPORT_20261016.md)、[实现与修改记录](PROXY_TASK_SERVICE_IMPLEMENTATION_20261017.md)、`configs/performance/glmark-clientproxy-opp3.env`。

## 2. 场景数据指向共同的固定等待

旧记录来自 `docs/shared/evidence/glmark-optimization-20261016/native-client-comparison.json`；新记录来自
`GPU-SFTP/log/realm-xshm/xshm-queue-publish-glmark-v2-20261017/realm-1.log`。

| 场景 | 旧 FPS / 帧时间 ms | Realm FPS / 帧时间 ms |
| --- | --- | --- |
| build VBO | 1524 / 0.656 | 120 / 8.391 |
| texture nearest | 1509 / 0.663 | 122 / 8.223 |
| shading gouraud | 1432 / 0.698 | 123 / 8.152 |
| bump normals | 1545 / 0.647 | 123 / 8.191 |
| desktop blur | 256 / 3.912 | 22 / 46.434 |
| terrain | 51 / 19.942 | 5 / 249.087 |

旧 FPS≥1000 的场景，新旧打印帧时间差的中位数为 7.468 ms。负载不同的多个简单场景集中在
约 120–124 FPS，强烈提示共同的 CPU/通信/调度等待限制吞吐；这不是已完成的时间归因。
复杂场景可能包含更多提交和同步、较低 GPU 频率及内存访问成本，不能只用一个固定常数解释。
两份 Guest 配置 HZ=250；约 8 ms 与两个 tick 接近，但没有逐事件时间线，不能据此断言“两个 jiffy 是根因”。

33 场景对齐、计算口径及输入 SHA 保存在本地 `build/performance-analysis-20261018/historical-comparison.json`。

## 3. 明确存在的配置退步

### 3.1 原优化参数未进入新启动入口

`GPU-SFTP/tests/realm-xshm/run-realms.py` 的 boot_args 固定为
`console=ttyS0 rdinit=/init panic=-1 loglevel=6`。
而旧 runner 会显式加入 `panthor_client.completed_wait_cache=1` 和
`client_comm_vmshm.concurrent_rpc=1`。

当前代码两个参数默认均 false。`client_comm_vmshm_call()` 的 serialize 条件为
`!client_comm_vmshm_concurrent_rpc || !d->irq_notify`，因此即使有可信 IRQ，默认仍持
rpc_lock 覆盖整个请求等待。同一 Client 的提交线程和 fence worker 互相串行。

当前日志证实 `cache_hits=0 cache_candidates=0 cache_records=0`；不是已经开启却没有收益。
旧 720p 日志记录 383,980 次缓存命中，旧短场景 OFF/ON 交替实验有约 0–8% 的差异。
缺失这些优化是确定事实，但既有 A/B 不支持把十倍差距全部归于它们。
只 source 旧 env 也无效：新 runner 不读取这些 GLES 参数并转成对应 boot_args。

### 3.2 GPU 与 CPU 条件不一致

旧 profile 请求 600 MHz，实际采样 594 MHz；Realm 长测同 Host #7 的已保存观测为 300 MHz。
新 Realm launcher 没有接入旧入口的 OPP 设置、达频验证和恢复流程。
频率差会影响 GPU 密集场景，但不能假定 FPS 与频率线性，更不能单独解释简单场景统一约 8 ms。

旧配置在线 CPU 0–3，Proxy、Client、broker 分开；Realm runner 总是启动三个 Realm，
`--pin-cpus` 把 Proxy 放 CPU 0，两个其余 Realm 都放 CPU 1。
因此单 Client glmark 时，不执行 GPU 工作的观察者仍与 Client 争用同一 CPU。
三个 Realm 各 768 MiB，也是功能/负面检查配置，与旧 512+384 MiB 双 VM 不同；没有本轮内存压力证据，不把内存容量列为已证实瓶颈。

### 3.3 空闲 Realm 没有实现正常阻塞

实现记录保存的同 Host #7、20 秒观测：Proxy vCPU 约 99% 核，Client 和空闲观察者各约 50% 核，
WFI/blocking/halt_wakeup 统计为零。它不是最新长测的逐帧 CPU 采样，但当前源码仍未包含可工作的 WFI 阻塞实现。
此前 WFI/软件 timer 候选启动失败后已撤回；不能沿用其“计划支持阻塞”的描述。

因此 IRQ 的真实性与送达已验证，不代表没有空闲 CPU 消耗或调度干扰。
需要将观察者移出计时 CPU 来做单因素实验，并单独修复 timer/WFI；不能直接重新部署失败候选。

## 4. 新增的可信通知开销没有摊薄

关键代码：

- `drivers/char/realm_xshm.c`：notify、arm、irq_thread。
- `drivers/char/{client_vmshm_comm/client_comm_vmshm,proxy_vmshm_comm/proxy_comm_vmshm}.c`：逐消息 kick、接收排空。
- `opencca/tf-rmm/runtime/rsi/xshm.c`：授权与返回 Host 调度提示。
- `Linux-Host-GPU/arch/arm64/kvm/rme-exit.c` / `rme.c`：接收提示、kick 对端 vCPU。

`realm_xshm_arm()` 顺序执行 QUERY、ACK、ARM 三次 SMC。IRQ thread 还要 QUERY 订阅通道，
发送端每条消息调用 NOTIFY。典型“一个请求、一个回复，两边各一次 IRQ并排空”的 RPC 路径是：
两次 NOTIFY + 两次 IRQ QUERY + 两组三次重置通知，共约 10 次 XSHM SMC。
这只是该路径的源码计数，竞态、多个通道和批量排空会改变实际次数，不能当作实测平均值。

若对端已 ARM，RMM 的 NOTIFY 还返回 Host，由 KVM 查路由并 kick 对端，随后重新进入 Realm。
接收端经过 IRQ thread，再 schedule RX work；PLAN_EXEC 还进入另一个 submit work 并等待。
不经过用户态 VMM 选择授权，并不代表没有 Host 调度路径或世界切换费用。

两侧 send 均逐消息 kick；RMM 合并的是已 pending 的唤醒，不是免除每条消息的 NOTIFY SMC。
同步 RPC 使双方频繁排空、重新 ARM，再立刻发送下一请求，恰好很难产生有效批量。
RMM 事件服务又使用全局 policy_lock；这是多通道扩展时的潜在竞争点，当前没有锁等待数据。

最新长测 IRQ 为 Proxy 438,304、Client 437,463，主 glmark 计划执行 40,599 次。
粗比每次计划执行两边合计约 21.6 次 IPC IRQ，范围包括 validation/API 等，不是严格的每提交计数，
也不等于 GPU IRQ 数。它至少说明“计划只注册 76 次”没有使事件次数降低到同一数量级。

## 5. 任务计划有效，但不是已经完成的异步任务引擎

`panthor_client_execute_plan()` 每次仍调用同步 PLAN_EXEC RPC，并持有文件的 plan_lock 到回复。
Proxy 从计划取出绑定后，仍构造 jobs/syncs，调用 `panthor_vmshm_group_submit()`；后者每次创建
drm_sched_job、准备对象锁、收集同步依赖和 signal 操作，再进入真实调度器。
这比重复查找静态绑定少做了一部分工作，没有缓存并重放完整 GPU 硬件任务。

原 472 字节提交 payload 变为 248 字节，减少的是 payload；两侧发送仍 memset 固定槽，接收仍复制
完整 512 字节私有快照后解析。世界切换、IRQ、锁和工作线程调度次数并未随 payload 下降 47.5%。
固定快照有防 double-fetch 的作用，不应为了这点复制开销删除安全检查。

当前支持“调用者一次提交最多 6 个 job”，并有正确性验证；没有自动把后续多个 ioctl 合并为一个
批次，也没有证据表明 Mesa 实际每次填满 6 个 job。6-job 空 stream 探针不是批处理性能证据。
frame-end finish 又限制跨帧流水深度。

Proxy 的全局公平 submit worker、session 锁等路径早于这轮重构已存在，不能把它们列为新增退化。
目前它们仍在，计划引入并没有消除该调度跳转。应该测排队时间，再决定单 Client 快路或异步化。

## 6. GPU 完成仍靠远端查询，没有统一完成队列

`panthor_client_sync_fence_work()` 将 timeout 设为零，对 Proxy 发 SYNCOBJ_WAIT RPC；
未完成时 usleep_range(1000,2000) 后重查。
当前真实 IRQ 主要通知 RPC 请求/回复，并未将 GPU fence 完成转换为主动的 Completion 记录。
因此“通信已经中断化”不等于“GPU 完成已经事件化”。

最新长测统计：32,830 次 sync-file wait，34,662 次查询，累计等待约 49.64 s，平均每次约 1.512 ms；
另有 86,808 次非阻塞 timeline 查询，完成点缓存关闭。
多数 sync-file 查询一次就成功，说明也不能把所有开销归因于反复 sleep；首次往返本身也有成本。
累计时间包含 worker 的 RPC、等待及调度，不是纯 GPU 执行时间，也不能与其他异步阶段相加作独占归因。

应把真实 fence 回调转换成带 session/object generation/submit sequence 的完成记录，批量写 CQ，
只在需要唤醒时发送可信事件。Client 据此更新本地 fence，保留精确快照、reset/import/destroy 等语义。
这能减少查询往返，是比单纯压缩 PLAN_EXEC 更直接的方向；还未实现，不能声称已保证收益。

## 7. Realm 专用缓存维护是额外成本，暂不能定量

普通路径中直接返回的 Realm 同步，在新路径会实际执行：

- panthor_kernel_bo_sync_for_device：vmap flush、屏障、逐页 arch DMA 同步。
- 固件输出同步仍遍历所有已描述的 CSG/CS，调度状态查询和 IRQ 可重复调用。
- panthor_vm_sync_mapped_bos 在提交/完成相关路径扫描整个 VM 映射；真正缓存维护过滤掉
  vmshm-backed BO，但仍有遍历及私有对象同步，不能把所有映射大小都算作实际 flush 字节。

之前已将运行时固件输入发布缩到选定区域、修正子数据到父 doorbell 顺序、避免清 GPU 输出页，
并将命令字节发布移到 INSERT 前。这些正确性修复不能撤掉来追求分数。
当前应统计实际同步字节、调用次数、耗时和重复范围，再考虑按活跃 CSG、对象和脏区同步。
RMM 大共享池映射主要发生在工作负载前，撤销主要在之后；没有证据说明 256 MiB 建池本身就是
计时场景 8 ms 的来源，也没有把数据逐帧交给 RMM 复制。

## 8. 按收益与验证价值排序的下一步

| 顺序 | 动作 | 必须得到的证据 |
| --- | --- | --- |
| 1 | 给 Realm runner 接入明确性能 profile；固定 GPU/CPU、实际读回开关；计时阶段隔离观察者 | 同条件短场景 OFF/ON 交替；恢复状态不变；不要只复制旧 env |
| 2 | 测空队列/echo 的单向通知及 RPC p50/p95，分解 sender SMC、Host kick、IRQ→RX、submit worker | 区分 RMM 开销与 vCPU 调度等待，避免又用逐消息串口日志干扰 |
| 3 | 实现一次可信检查完成 ACK+ARM，并以队列从空到非空/接收者等待状态进行通知 | 继续验证 publish/arm 竞争、无丢唤醒、终止与撤销；不是删掉授权 |
| 4 | GPU fence 主动写完成队列，合并完成通知，保留精确同步对象语义 | 每提交 RPC/SMC/IRQ 计数下降；单线程短帧收益与错误路径测试 |
| 5 | 再优化缓存同步范围、资源控制批量、Proxy 调度路径 | 阶段统计证实占比，再改代码；每阶段先定向回归，再完整长测 |
| 独立项 | 修复 Realm timer/WFI 并验证真实阻塞后的可信唤醒 | 启动、超时与跨核通知均通过；不直接复用失败候选 |

GPU shadow 隔离按用户范围暂缓，当前低性能不是已经为 shadow 校验付出的代价。
当前最该验证的是调度/配置和每帧同步往返，尚无证据支持继续主要围绕计划 payload 大小优化。
本报告没有新增 A/B，不能承诺开启参数后恢复 1058，也不能给各原因分配未经测量的百分比。
