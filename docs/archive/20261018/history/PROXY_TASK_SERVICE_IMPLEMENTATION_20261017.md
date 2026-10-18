# Proxy GPU 任务服务重构记录

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-17。记录[整体方案](../research/PROXY_REALM_GPU_ARCHITECTURE_V2_20261017.md)的任务代理、队列加固和 RMM 通信实现。各阶段结果分别对应实际测试的源码与载荷。

2026-10-18 性能专项另见[glmark 优化记录](PROXY_REALM_PERFORMANCE_OPTIMIZATION_20261018.md)。按用户要求，优化期间只跑完整 720p、33 场景 glmark，以超过 1000 分为门槛；达到理想分数后再恢复其他回归。每次大改列出前后分数、绝对/百分比变化、条件差异与保留/撤回结论；全部历史版本与证据集中在该记录，不在本页重复展开。

当前性能状态：P42完整720p glmark同镜像两轮 **1159、1163分**，对P41的1023为 **+136～140 / +13.29～13.69%**；保留P42，三Realm生命周期及两次17类API、双Client各17类API与两边真实计算验收均通过。RMM授权共享内存与可信IRQ保留，当前组合的其余验收按下文证据判定。以下P25–P41为历史演进，不能当作当前成绩。

历史无完成页的对照候选 **P28：914 分**，对 P27 902 分为 **+12 / +1.33%**，只将 Client 回复轮询上限 200→1000 µs，两份内核与 RMM 不变；完整 glmark 校验、内核与清理检查通过，但仅一轮，未证明稳定收益。基础代码 P25 的两轮成绩为 882、881，对 P19 864 为 +18 / +2.08%、+17 / +1.97%。旧普通 VM 为 1058 分，环境路径不同，只用于目标差距，该阶段尚未达到目标。

P26 延迟 binary syncobj 的独立实验为 **881→862（-19 / -2.16%）**，已撤回；只独立保留数组查询失败时重复释放引用的正确性修复，不宣称提分。P29 将延迟容器与原生 fence 完成页结合，实测 **914→918（+4 / +0.44%）**，正确性、内核与清理通过，但本地等待命中率只有 1.44%，尚未证明稳定收益。P30 仅将其轮询预算 100→1000 µs，实测 **918→957（+39 / +4.25%）**，完成页命中率 1.44%→99.58%，校验/内核/清理通过；当时单轮候选为 **957 分**，后续复测见下文。P31 复用较小完成点实测 **957→957（0 / 0.00%）**，未提分，已撤回该扩展；当时保留关闭缓存期间跟踪失效的 F2，后续核对只读参数后已删除该额外跟踪（见下文）。回退重建组合未独立硬件测量，各轮不能混为同一改动。该组合保留 RMM 授权共享内存、可信 IRQ 和既有错误回退；当前 GPT/GPC 硬件保护限制不变。

P31 撤回后的实际保留组合完整复测为 **957→957（0 / 0.00%）**，正确性、受检内核标记及 Host 恢复检查通过。P32 为 **957→955（-2 / -0.21%）**；P33 为 **957→957（0 / 0.00%）**（均对保留基线）。两轮新增路径计数全部为0，未证明新设计收益；P32–P34 扩展已整体从源码撤回，P34 未部署、无硬件成绩。保留完成页、RMM通信及 F1 数组引用修复；同时移除只读缓存参数下无消费者的 F2 跟踪。源码逐文件恢复到已测 P30，撤回重建不冒用历史分数。详情、命令、run-id、条件和日志均见性能专项记录。

后续 P35 只开启已有完成快照参数，完整实测 **957→928（-29 / -3.03%）**，不启用；校验、受检内核标记和Host恢复检查通过。固定Mesa源码另发现context初始化提交已提前物化syncobj，故P36改为支持真实已物化目标的TRANSFER/不可变导出快照融合；局部检查与双侧构建通过，完整实测 **957→951（-6 / -0.63%）**；路径确实命中，但未提分，已整体撤回。P37仅改Proxy从CPU1到物理GPU IRQ所在的CPU0，Client仍CPU2，完整实测 **957→944（-13 / -1.36%）**，不采用；正确性、受检内核与Host恢复检查通过。P38精确原生timeline完成凭据实测 **957→962（+5 / +0.52%）**，未证明稳定收益；正确性、受检内核与Host恢复检查通过。P39在同对象/无后续写入的前提下扩展完整原生chain的较早点证明，两轮同一冻结输入完整实测均为 **957→1022（+65 / +6.79%）**，校验、受检内核和Host恢复均通过；有效组合保留。P40回调对象复用完整实测 **1022→1024（+2 / +0.20%）**，正确性、受检内核与Host恢复通过，但未证明稳定且值得增加复杂度的收益，复用逻辑撤回，仅保留删除无调用者接口。P41日志清理完整实测 **1022→1023（+1 / +0.10%）**，校验、受检内核与Host恢复通过，不宣称性能收益；先作为日志清理保留。P42采用最后引用释放后有界排队、下一次导出附带回收旧快照的方式，保持新快照不可变和RMM授权路径，同镜像两轮完整实测 **1023→1159、1163（+136～140 / +13.29～13.69%）**，两轮校验、受检内核及Host恢复通过，各七份原始证据SHA一致，保留该增量；当前三Realm生命周期/API验收通过（两次17类API、256MiB逐页/撤销/提供方更换、通知归属/合并，三VM正常退出，原始9文件SHA一致），双Client各17类API与两边真实计算亦通过（三VM退出0、原始9文件SHA一致）。高于旧1058为+101～105 / +9.55～9.92%，但旧环境条件不同，不能作单变量归因；当前性能优化及既有RMM通信功能验收完成，不扩大为GPU shadow隔离或硬件机密性证明。RMM路径保持不变；当前源码58份哈希与部署包一致，四轮Host恢复与受检内核健康均通过，证据详见性能专项记录。

本次精简此页的重复历史属于文档整理，未改运行代码，无新增性能测量。下面保留原功能阶段状态。

历史功能阶段状态（非当前性能成绩）：本阶段任务代理与 RMM 通信流程已打通。当前队列发布版本通过双 Client
各 17 类 API、实际 GPU 计算、6-job 批次及无效批次拒绝检查；独立完整 Realm glmark
通过 33 场景，score 98，使用 256 MiB 池，主会话完成 40,599 次计划运行。
两轮五类受检内核故障均为 0，VM 正常退出，证据已逐文件校验。
WFI 失败候选及旧提交路径已从源码撤出，历史失败保留。完整结果见文末。

| 本阶段范围 | 已验收内容 / 边界 |
| --- | --- |
| 任务代理 | 资源引用与计划注册、重复执行、最多 6-job 提交；删除直接 GROUP_SUBMIT RPC，保留资源控制所需 DRM 兼容接口 |
| 多 Realm 内存 | RMM 识别调用者并授权映射；独立队列/池、256 MiB 映射、撤销及提供方更换 |
| 可信通知 | RMM 持久事件、ACK/ARM 和 IPC IRQ；非参与者拒绝、合并通知测试通过；Host 仍可拒绝调度 |
| 生命周期 | 活动引用阻止提前拆映射，释放后回收；计划失效及句柄复用检查通过 |
| 尚未验收 | 当前新组合完整 32 项、同条件原生性能对照、长期压力、多 vCPU 与完整远程证明策略 |
| 明确暂缓 | GPU shadow 页表；RK3588/OpenCCA 无真实 GPT/GPC，不能声称已实现恶意 Host 下的硬件机密性或恶意 GPU 任务间隔离 |

以下按功能里程碑保留实现、失败和复测过程；单次 score 不能证明性能提升。
新旧配置、固定帧等待、SMC/IRQ 与完成查询开销的源码复盘见
[性能下降原因分析（2026-10-18）](PROXY_REALM_PERFORMANCE_CAUSE_ANALYSIS_20261018.md)。

## 已实现的功能

Client 保持应用可用的 DRM/Panthor 接口，将提交转换为两类服务请求：

- `PLAN_REGISTER`：一次注册队列布局、Group 和同步对象绑定；Proxy 验证、转换并持有实际资源引用，返回会话内不复用的计划 ID。
- `PLAN_EXEC`：携带计划 ID、命令流地址/长度、flush ID 和时间线值；Proxy 构造实际 Panthor 提交，通过已有会话公平调度器执行。

每个会话最多缓存 8 个计划。计划替换先完成新计划校验，再释放旧计划。Group 或相关同步对象销毁时，Proxy 主动使其计划失效；会话关闭释放全部计划引用。Client 只对明确发生在派发前的 `ESTALE` 响应重新注册；传输超时及执行结果不明的请求不重试，避免重复执行。

**清理后的协议版本为 2，Client/Proxy 必须成套部署。** 已删除原直接 `GROUP_SUBMIT` RPC 处理器、重复的后端任务转换路径、调度器双分支和 Client 兼容开关。计划注册与执行使用独立的数据结构，注册消息不再包含无效的动态字段。

| 数据 | 原提交消息 | 新注册消息 | 新执行消息 |
| --- | ---: | ---: | ---: |
| 固定 payload | 472 字节 | 248 字节 | 248 字节 |
| 使用频率 | 每次提交 | 新计划或失效后 | 每次执行 |

复用时单次提交 payload 减少 47.5%。这不代表全部通信量或执行时间下降 47.5%；新计划额外需要一次注册 RPC，资源创建、绑定和同步控制请求仍存在。目前提交批次上限沿用 6 个 job、16 个同步操作。

## 测试记录

控制机证据目录：`build/proxy-service-v2/`。硬件外层记录在 `build/lab-runs/<run-id>/`，工作负载日志在 `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`。失败记录保留。

| run-id | 检查及结果 | 退出码 |
| --- | --- | ---: |
| `plan-v2-bringup-20261017` | 首项提交及 fence 成功，但新路径缺少 runner 要求的逻辑提交审计行，外层 FAIL；后续快照项 NOT_RUN。随后补充相同语义的审计记录 | 1 |
| `plan-v3-bringup-20261017` | `group-submit-syncpoint`、`sync-file-snapshot` 均 PASS | 0 |
| `plan-v3-glmark720-20261017` | glmark 工作负载 PASS、score 806；运行期间修改 runner 导致外层 Bash 后续读取失败，整次运行记 FAIL；已单独回收日志 | 2 |
| `plan-v4-validation-20261017` | 固定 runner 副本；增强的句柄复用回归及完整 glmark720 均 PASS | 0 |
| `task-service-v2-src7-regression-20261017` | 延后队列 READY 发布后，owner 初始化误用要求 READY 的旧检查，启动失败；1 PASS、1 FAIL、30 NOT_RUN | 1 |
| `task-service-v2-src8-bringup-20261017` | 修复初始化顺序；队列边界自检及 4 次新 fence/同句柄复用 PASS | 0 |
| `task-service-v2-src8-regression-20261017` | 通信加固版本完整矩阵 32/32 PASS，外层 COMPLETED，Host 恢复检查通过 | 0 |
| `task-service-v2-src6-regression-20261017` | 清理旧路径、压缩注册结构后的协议 v2 完整矩阵；32/32 PASS，外层 COMPLETED，Host 恢复检查通过 | 0 |

前四次验证任务计划引入阶段，src6 验证清理后的协议 v2；src7/src8 又加入通信边界加固。前后源代码组合有变化，结果分别保留。

`plan-v4-lifecycle-20261017` 的 4 次提交均等待新的 fence 完成：第 2 次提交前 reset 同步对象，第 3 次前销毁并重新分配同一个句柄，第 4 次再次 reset。Proxy 统计 `registered=2 runs=4`；Client 的本地形状查找统计 `hits=3 misses=1`，其中一次命中后由 Proxy 判定失效并重新注册。最终 Group 无 timeout、fatal fault 或 fatal queue。

`plan-v4-glmark720-20261017` 使用 1280×720、null-noop、finish、默认全部 33 个计时场景及完整 validation：

- score 806；Mali renderer；`COMPUTE_CHECK=PASS`、`GLMARK_CLEAN_RESULT=PASS`、`GLMARK_RESULT=PASS`。
- validation：26 成功、1 已知 function/medium 数值校验例外、6 无判据；unexpected failures 为 0。不能写成全部场景 validation 成功。
- 计时会话 `session=4`：`registered=76 runs=333047`，平均每个注册对应约 4,382 次成功执行。该统计证明复用生效，不能代替与旧实现的同条件性能对照。

固定副本的复测命令保存在 `build/proxy-service-v2/run-plan-v4.sh`；内层调用 `vmshm-runner-v4.sh`，避免开发时改动正在执行的脚本。完整矩阵入口是：

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id task-service-v2-src6-regression-20261017 -- \
  bash build/proxy-service-v2/run-service-v6-regression.sh
```

其控制脚本校验并安装两份 Image，随后执行 `run-regression.py --remote-prepared --passthrough`；命令、全部 32 项状态与退出码记录在 `GPU-SFTP/log/regression/task-service-v2-20261017-src6/summary.json`。输入与镜像哈希记录在 `build/proxy-service-v2/service-v6-{inputs,images}.sha256`。

最终协议 v2（src6）的 32 项全部 PASS，没有 FAIL 或 NOT_RUN；包含 17 项 ioctl、
PFN 生命周期及日志检查、4 档 compute、ML、attention、NCNN、两档完整 glmark、
双 Client、直通对照及运行前后检查。外层运行于 08:52:08–09:16:27 UTC，退出 0。
结束时无 Firecracker/broker 和 loop 残留，Host 恢复为 `pmthor`、CPU `0-1`。

| src6 glmark | Score | validation 成功/已知例外/无判据 | unexpected failures | 计时会话 registered / runs |
| --- | ---: | --- | ---: | ---: |
| 1280×720 | 507 | 26 / 1 / 6 | 0 | 76 / 212182 |
| 1920×1080 | 455 | 26 / 1 / 6 | 0 | 76 / 189683 |

两档都执行默认完整计时场景，且 clean、compute、renderer 和最终结果检查通过。
本矩阵使用 Host CPU `0-1`，前述 src4 glmark 使用了不同 CPU 配置，因此 507 与
806 不能用于判断新旧提交路径的性能变化。任务计划复用已在实际工作负载生效，
性能提升仍需固定条件的新旧内核 A/B 实验。

src6 通过后又修改了通信层以修复共享元数据重复读取问题；上面结果只对应保存的
src6 镜像与补丁快照，不涵盖后续修改。

## 共享队列边界加固

src6 之后修复共享元数据 double-fetch：不能先检查共享 `len`，随后再读同一字段作为复制长度。
接收端现在先取私有 descriptor 快照，再将固定 512 字节槽位复制到私有内存，最后校验并解析
私有字段。队列几何及本端生产/消费进度只保存在私有状态中；对端进度超过容量返回错误，
不能通过篡改共享索引改变本端进度。启动自检覆盖伪造几何、本端索引、u32 环绕和生产者越界，
通过后才发布 READY；只允许接入进度为零的新队列。

src8 启动验证记录为 `task-service-v2-20261017-src8-lifecycle`，
`VMSHM_BOUNDARY_CHECK=PASS geometry=private own_indices=private wrap=u32 producer_overflow=rejected`。
完整 32 项重跑使用外层 `task-service-v2-src8-regression-20261017`，结果独立记录于
`GPU-SFTP/log/regression/task-service-v2-20261017-src8/summary.json`；实际结果为 32 PASS、0 FAIL、0 NOT_RUN，所有退出码为 0。
这些检查防止共享队列元数据破坏内核边界，不提供 Host 机密性或 RMM 身份认证。

src8 外层退出 0，运行结束后无 VM/broker、loop 残留，Host 恢复为 pmthor、CPU 0-1。
Client Image SHA-256：`702127073aa27cfe91738843550db48905eb570149a4d22f2b8544e54bbfe285`；
Proxy Image：`b97df6fefdc6d36725fe9bf8317d8d1c251984810f758506c4bb1abd080f4d27`。

| src8 glmark | Score | validation 成功/已知例外/无判据 | unexpected failures | registered / runs |
| --- | ---: | --- | ---: | ---: |
| 1280×720 | 507 | 26 / 1 / 6 | 0 | 76 / 212454 |
| 1920×1080 | 455 | 26 / 1 / 6 | 0 | 76 / 189887 |

两档均通过 compute、Mali renderer、完整计时场景和 clean 检查；不能把已知例外/无判据写成
validation 全部成功。src6 与 src8 均使用 CPU 0-1，分数一致；这仅说明本轮未观察到 glmark
分数退步，不代替固定环境下多次重复的统计性能实验。

## 删除重复协议定义（src9）

Client 与 Proxy 原先分别定义了相同的队列 header、descriptor、ring、消息结构和常量。
现统一到 `Linux-Guest-GPU/include/linux/vmshm_comm_protocol.h`，两侧直接引用，
删除重复定义和从未使用的 IDX_TABLE、BITMAP、PRIVATE_SCRATCH 预留类型。
分配器实际使用的对象类型继续保留为其私有定义。

公共头文件用编译断言固定实际 wire 大小与 payload 偏移；未改变队列 ABI 1，
任务服务 ABI 仍为 2。固定消息槽快照、私有几何/索引及越界校验均保留。
这里没有为后续 Realm 通道再造一份协议或加入空 transport 抽象。
Client/Proxy Image 均构建成功；输入及镜像哈希为
`build/proxy-service-v2/service-v9/inputs.json`，构建日志为
`build/proxy-service-v2/comm-protocol-{client,proxy}-image-build.log`。

新 RMM 固件部署后的验证：

```bash
python3 scripts/maintenance/lab-run.py --run-id task-service-v2-src9-validation-20261017 -- \
  python3 build/proxy-service-v2/run-comm-protocol-validation.py
```

外层退出 0，分别执行 `task-service-v2-src9-lifecycle-20261017` 和
`task-service-v2-src9-glmark720-20261017`，各退出 0。命令及退出码为
`build/proxy-service-v2/service-v9/validation.json`；日志在
`GPU-SFTP/log/shared/vmshm-1client/<run-id>/`。

- 生命周期：4 次新 fence、reset 与同句柄复用通过；`registered=2 runs=4`，队列边界自检通过。
- glmark：1280×720、33 个计时场景、Mali renderer、score **1058**，compute/clean/最终结果 PASS；validation 为 26 成功、1 已知例外、6 无判据，unexpected failures 0。计时会话 `registered=76 runs=433347`。
- 使用 `glmark-clientproxy-opp3.env`：CPU 0–3、GPU 请求 600 MHz、完成点缓存启用、Proxy 统计关闭。与 src4/src8 参数不同，**不能把分数差归因于本次协议去重**。
- 结束时 Host 恢复为 pmthor、CPU 0–1，无测试进程及 loop 残留。新固件下本次只运行以上 GPU 验证，未重跑完整 32 项。

完整 glmark 日志保留一条 `rm: not found`：精简 Guest 没有该 applet，旧进度文件清理未执行。
这是辅助日志清理缺陷，GPU 结果仍独立记录。随后改用 shell 内建 `: > file` 截断，
避免新增 Guest 依赖。`task-service-v2-progress-cleanup-20261017` 外层退出 0：
只运行 build 短场景、跳过 validation，进度记录和最终结果 PASS，日志中无该缺失命令错误。
命令为 `lab-run.py --run-id task-service-v2-progress-cleanup-20261017 -- bash build/proxy-service-v2/run-progress-cleanup-check.sh`，
输入哈希与日志为 `build/proxy-service-v2/progress-cleanup-{inputs.sha256,run.log}`；
该短测不替代上面的完整 glmark，结束后恢复检查通过。

## 构建和流程清理

RMM 固定依赖已初始化，RK3588 Debug 构建产物为 `build/proxy-service-v2/rmm/Debug/rmm.elf`；内存版本固件的部署与实际验证见下文。

修复构建自动补丁流程：删除 `git checkout .` / `git clean -f`，已应用的补丁重复配置时跳过，冲突时失败并保留工作文件。移除 mbedTLS 补丁中的 `#if 0` 死代码及 t_cose 重复 include，使构建后的依赖差异与发布补丁一致。补丁清单校验支持 Git 对象缩写变长，同时继续拒绝内容、模式或对象前缀变化。

实际检查：RMM 重复配置及构建成功，构建后补丁清单校验通过；临时仓库验证首次应用、重复应用、冲突拒绝和未跟踪文件保留；模拟首项退出 7，回归汇总正确保留 1 FAIL 和 31 NOT_RUN。模拟检查没有运行 GPU 工作负载。

一次性源码修改辅助脚本已删除；保留构建日志、失败证据和必要的变更前镜像。执行中的 runner 固定副本应保留至该次测试结束。

## RMM 端点与持久事件状态

新增实验接口 `SMC_RSI_OPENCCA_XSHM`（`0xc40001ad`），包含 REGISTER、OFFER、ACCEPT、CLOSE、NOTIFY、QUERY、ACK、ARM 和 UNREGISTER。

授权依据为执行 RSI 的 REC 所属 RD，不能用请求载荷中的 VMID 冒充调用方。双方显式建立通道后才能通知；端点和通道使用本次 RMM 启动内不复用的 64 位 ID。Realm 成功销毁前清除相关端点和通道，防止 RD 地址复用后继承旧授权。端点身份并不替代上层的可信发现、证明及参与者策略。

事件序列保存在 RMM 私有状态中。NOTIFY 递增接收方 pending；ACK 只能确认已产生且不倒退的序列；ARM 原子检查已确认序列是否仍等于 pending，有新事件时拒绝进入等待状态。第一次唤醒后合并后续通知，pending 仍保留。CLOSE 返回终止唤醒提示。

最初端点版本只宣告端点与事件状态两项 capability；后续内存版本增加共享映射 capability，仍不宣告中断注入能力。NOTIFY 返回唤醒提示，不等于已经跨核注入了中断。

验证命令：`bash scripts/check/check-rmm-xshm-events.sh`，退出 0；实际编译策略代码，在 AddressSanitizer / UndefinedBehaviorSanitizer 下验证冒用、第三方接受/通知/确认、超前或倒退 ACK、身份重建、旧句柄、容量，以及 10,000 次事件到达 ACK/ARM 间隙的交错。`cmake --build build/proxy-service-v2/rmm -j8` 退出 0。该条为端点版本的原生检查记录；后续板端结果另列。日志为 `build/proxy-service-v2/{xshm-endpoint-test,rmm-endpoint-build}.log`。

参考 CAEC 的公开代码固定在 RMM [`43ffec10b98a6a5ea6b1116c4429fee684069233`](https://github.com/comet-cc/RMM-CAEC/tree/43ffec10b98a6a5ea6b1116c4429fee684069233) 与模块 [`d589ecaf95ef96abf5f34a0fb6792d9e6972f6a2`](https://github.com/comet-cc/External-Modules-CAEC/tree/d589ecaf95ef96abf5f34a0fb6792d9e6972f6a2)，仅用于分析，未整体导入或执行其安装脚本。本文新增端点/事件代码不是 CAEC 代码的直接移植。

### Guest 调用入口

当前使用内建 `CONFIG_REALM_XSHM=y` 和 `/dev/realm-xshm`，只在 Realm 中注册。
72 字节 ioctl 保留 RMM 状态和四个返回寄存器，通过 SMCCC 1.2 调用；设备 0600，
检查 `CAP_SYS_ADMIN`。关闭 fd 不清理 Realm 级端点，旧 RMM 明确返回不支持。
早期端点版本曾单独验证模块构建；当前池版本依赖内核内 CMA/cache 接口，不再提供模块卸载。
`bash scripts/build/build-realm-xshm.sh` 构建 ARM64 静态工具；原生检查同时断言
Guest/RMM 命令值与 ioctl 大小。实际三方负面测试结果见下表，用法见
[工具说明](../../../../GPU-SFTP/tests/realm-xshm/README.md)。

## RMM 共享映射实现与验证边界

新增 MEM_OFFER / ATTACH / DETACH / REVOKE / STATUS / CONTINUE。Guest 72 字节 ioctl
保持兼容布局，内存 OFFER 使用原保留字段传 size。原始 CALL 只调用服务，
另由内建 POOL 接口分配并准备固定池；都尚未接入 GPU 数据通路。
服务入口根据真实 RD 和本次启动不复用的端点 ID 授权；OFFER 与 ATTACH 都要求双方的通道
当前处于 live 状态。未附着的 offer 不阻止接收方退出，重新注册或 RD 复用也不能继承旧授权。
附着后，关闭通道、注销端点或销毁相关 Realm 均须先解除映射。

内存后端直接修改受保护 IPA 的 RTT，要求源页对应真实 DATA granule、目标为 L3
unassigned RAM；映射和恢复维护 RTT 引用计数并执行 TLBI。物理页继续属于提供方，
不改成 Normal PAS，不额外分配目标数据页。源 RTT 保持权威映射，去掉重复的逐页 PA 列表；
私有元数据按区域计，最多 64 个区域、每提供方 8 个，每区域最多 256 MiB。
每次调用最多处理 64 页，调用方显式继续；部分安装失败撤销已安装前缀，恢复异常则隔离保留，
不能继续释放物理页。

XSHM 与 Host RMI 的所有权修改共用策略锁，锁先于 RD/RTT 获取，**不跨 REC_ENTER 持有**。
租约存续期间拒绝覆盖相关范围的 DATA_CREATE/DESTROY、RTT_FOLD/DESTROY、RIPAS 修改
及 Realm 销毁；允许保持映射语义的 RTT 分裂。此时 GPU 仍须由可信 Proxy 在 fence 完成后
撤销自己的数据池，RMM 的 CPU RTT/TLBI 不等于 GPU DMA 已停止。

`bash scripts/check/check-rmm-xshm-events.sh` 退出 0：实际状态机与实际服务入口在 ASan/UBSan
下验证三方冒用、关闭通道后禁止附着、端点代际、附着期间关闭/注销拒绝、借用页再授权拒绝、
129 页分段进度、安装第 70 页失败回滚、提供方撤销优先、配额耗尽及恢复失败隔离。
翻译后端在该原生测试中为有界模拟表，**不是实际 RTT/TLBI 硬件测试**。
含实际后端与 RMI 入口保护的 RK3588 RMM 编译成功，日志
`build/proxy-service-v2/rmm-memory-build.log`；板端部署及真实 RTT 映射结果如下。

完整固件入口的 RMM、TF-A、U-Boot 曾分别构建成功；修复输出目录创建和缺失 RMM ELF
被忽略的问题，并验证缺失 ELF 时构建失败。为兼容控制机 SWIG 4.4，按
[上游 dtc 修复](https://kernel.googlesource.com/pub/scm/utils/dtc/dtc/+/d1e2384185c5eeb8e238f7a8174ff43ea0da5d92)
替换 3 处旧私有 AppendOutput 调用，没有更新固定 U-Boot 提交。
补丁与 manifest 同步更新，构建后清单校验通过。内存版本重新打包产物为
`build/proxy-service-v2/firmware-memory/`，哈希为 `firmware-memory-images.sha256`；
实际部署使用该版本，不沿用早期端点版本的 ITB。

## 板端 Realm 通信验证

新 RMM 固件已于 `xshm-memory-firmware-20261017` 部署到 SD（storage ID 2），
外层与部署命令均退出 0；先将实际 SD 启动区备份至控制机，再校验传输哈希并刷写固件。
未更新 Host 内核或 rootfs，结束后驱动和 CPU 状态恢复。UART 确认新 RMM 启动，
实际 REGISTER 返回 `[1, endpoint, 7, 128]`。这仍是 OpenCCA spoofed CCA，
**不构成恶意 Host 无法读内存的硬件证明**。

| run-id | 实际结果 | 退出码 |
| --- | --- | ---: |
| `xshm-realms-events-20261017` | SSH 子命令缺失密码环境，未启动 Realm；子命令 -11，外层 shell 245 | 245 |
| `xshm-realms-events-v2-20261017` | 测试配置缺少必填 drives，Realm 启动失败，通信未执行 | 1 |
| `xshm-realms-events-v3-20261017` | initrd 长度未按 RME 4 KiB 要求对齐，populate 失败；打包器增加合法零填充 | 1 |
| `xshm-realms-events-v4-20261017` | 未沿用实验室 no-seccomp 参数，VMM 被现有过滤器拒绝 mmap；通信未执行 | 1 |
| `xshm-realms-events-v5-20261017` | 三 Realm、34 条真实调用 PASS，VM 退出码均 0，外层检查通过 | 0 |
| `xshm-realms-memory129-20261017` | 129 页（528384 字节）、322 条调用 PASS，逐页校验、双向写读、detach/reattach、revoke、第三方拒绝通过，VM 均退出 0 | 0 |
| `xshm-realms-memory1025-20261017` | 并发启动时一 Realm 未就绪，启动超时；共享内存检查 NOT_RUN，清理后 Host 恢复 | 1 |
| `xshm-realms-memory1025-v2-20261017` | 改为依次启动、三者同时存续；1025 页（4198400 字节）、2212 条调用 PASS，VM 均退出 0，覆盖多个 L3 表及 64 页分段边界 | 0 |
| `xshm-realms-memory16m-20261017` | 源页准备时 JSON 后附带 printk，解析器失败；尚未创建 grant，共享映射 NOT_RUN，VM 均退出 0 | 1 |
| `xshm-realms-memory16m-v2-20261017` | 4096 页（16 MiB）、8685 条调用 PASS；逐页模式字、双向写读、detach/reattach、revoke 与第三方拒绝通过，VM 均退出 0 | 0 |
| `xshm-realms-provider-replacement-20261017` | 129 页、347 条调用，更换提供方后复用相同目标 IPA，首/中/末尾校验为新提供方数据；原提供方内容保持且无权撤销新 grant，VM 均退出 0 | 0 |

原始 Guest/命令/响应日志与生成配置在 `GPU-SFTP/log/realm-xshm/<run-id>/`，
外层命令与前后检查在 `build/lab-runs/<run-id>/`。失败均保留，不计入通过。
并发 bootstrap 超时的根因尚未定位，串行启动通过不能证明该问题已解决。

共享页版本使用内建 `CONFIG_REALM_XSHM=y`：每 Realm 一个有界、按服务生命周期持有的
CMA 池。直接申请连续页，不经过会改变 Realm 内存状态的 DMA 映射接口。
目标转换前清理缓存，释放原 DATA 后创建未分配的受保护 RAM L3 entries；
RMM 将其映射到提供方的真实页。访问目标前校验本地附着的 grant 仍为 ACTIVE。
部分准备失败保留池而不回收，避免物理页仍被引用时交回分配器。

该数据池入口是验证与后续内核消费者的基础，目前仅提供字访问，尚未接入 GPU 资源分配。
逐页检查为每个 4 KiB 页的首个 64 位模式字，并额外验证末尾双向写读；不是全缓冲区逐字节校验。
当前测试使用 CPU 缓冲区，**没有测量 DMA 吞吐或通信延迟**，也未对恶意 Host 的全部
RMI 修改路径执行板端攻击测试。串口解析器使用 raw_decode 读取一个完整 JSON 对象，
再核对响应命令；原始串口行仍保存。更换提供方回归保存 runner 副本及 runner、Image、initrd、
Firecracker 的 SHA-256 于运行目录；更早的 16 MiB 运行保留原 runner 于
`build/proxy-service-v2/realm-memory16m-tested-runner.py`，不能用新版 runner 的哈希替代。

前述 src8 GPU 完整 32 项发生在新 RMM 固件部署之前，不能沿用为新固件的 GPU 回归结论。

## 尚未实现的范围

前述 GPU 32 项仍使用普通 VM 的 vmshm 数据通路。后续已完成单个 Client Realm 经 RMM 队列与
数据池访问 Proxy Realm 实际 GPU 的 BO/fence 验证，见文末逐轮记录。多个 Client Realm
同时使用新数据池的 BO/fence/计算验证也已通过。完整 Realm glmark 功能随后通过，但性能未达标，见文末记录。
**可信中断派发、性能与长期稳定性仍需验证**；不能把普通 VM 的任务计划
通过写成整个机密通信方案完成。GPU shadow 页表按用户要求暂缓。

本阶段也没有证明恶意 Host 无法读取共享数据或保证 GPU 跨 Group 的硬件隔离。
已有 RMM 授权/映射/持久事件的功能和负面测试，不等于可信 IRQ 或端到端机密性完成。

## RMM 身份绑定队列与 Host populate 修复（进行中）

新增 `MEM_DESCRIBE`（命令 15，capability bit 3）：RMM 验证 grant、调用 Realm 及端点代际，
返回通道、提供方/借用方端点和调用方自己的 IPA，不泄露 RD、PA 或对方 IPA。
带内存后端的 REGISTER capability 由 7 增为 15。原生 ASan/UBSan 状态机与服务入口测试
退出 0，覆盖双方描述、第三方拒绝、撤销和旧代际；证据为
`build/proxy-service-v2/xshm-memory-identity-native.log`。RMM 与完整固件构建退出 0，
补丁清单全部 APPLIED。`xshm-memory-identity-firmware-20261017` 已仅向 SD2 部署新固件，
命令退出 0，实际 SD 启动区备份和 UART 保存在对应 `build/firmware-runs/` 目录。

Guest 新增 POOL_BIND/UNBIND，依据 RMM 返回的身份和 ACTIVE 状态，在池的前 1 MiB
创建真实 Client/Proxy comm platform device。Realm 路径拒绝仅由 Host DT 声明的队列；
Normal VM 原有路径仍用于既有 GPU 回归。队列发布调用真实 RMM NOTIFY，接收端目前仍轮询，
**尚无可信 IRQ 派发**。通信 fd、Client DRM file、Proxy session 持有队列引用，活动引用下
UNBIND 返回 EBUSY；绑定期间禁止本地 revoke/detach 和原始字读写。
这不等于完成 GPU payload/fence 生命周期：数据池 manager 尚未接入，不能据此撤销 GPU 缓冲区。

Guest 完整 fixture 内核与 Proxy 修改对象均构建成功。首轮
`xshm-realms-transport-20261017` 在第二 Realm populate 阶段超时，退出 1；调用记录为空，
**队列和内存验证 NOT_RUN**，VM 退出码为 `[0, -15]`。失败日志保留在
`GPU-SFTP/log/realm-xshm/xshm-realms-transport-20261017/`。

现场 Host 栈停在 `get_user_pages_unlocked → hva_to_pfn → gfn_to_pfn_memslot →
kvm_realm_enable_cap`。`populate_par_region()` 外层持有 mmap_read_lock，而 GUP 自行获取
该锁，存在待写者阻塞时递归读锁自锁的条件；未抓到待写线程栈，因果结论仍需修复后回归。
该现象也发生于依次启动，修正之前“仅并发 bootstrap 超时”的判断。
Host 修复删除外层锁以及实际不可达的 2 MiB populate 分支，保留实际支持的 4 KiB PFN
获取、DATA_CREATE 和成对释放路径。Image 构建退出 0，配置与运行版本一致，Module.symvers
未变化。实际 SD kernel 分区已完整备份，候选仅替换内核，保留 DTB/initrd/启动参数。
构建、原始分区回退、候选、配置及源码 diff 位于
`build/proxy-service-v2/host-rme-populate/`。新 Host/队列结果以下续记，不能沿用旧 PASS。

`host-rme-populate-deploy-20261017` 退出 0：仅刷 SD2 kernel slot，新 Host 为
`6.12.0-opencca-pmthor-opp3 #6`，恢复后 pmthor、CPU 0–1、无 VM/loop 检查通过。
新 Image SHA-256 为 `5cae42ef834c5f05351c398fc0ff9d594923ba21a9da927484140511503ea0fd`。
构建目录中的源码差异为该 Image 的归档输入，不以同名旧 release 的测试替代本次验证。

`xshm-realms-transport-v2-20261017` **PASS，退出 0**：三个 Realm 并发 bootstrap 成功，
257 页、643 条实际调用，VM 均退出 0。包括 RMM MEM_DESCRIBE 双方身份一致/第三方拒绝，
真实内核 comm probe HELLO/ACK、RMM NOTIFY 计数增加、活动通信 fd 拒绝 UNBIND、
绑定期间拒绝本地 revoke/detach/原始写、解绑、grant detach/reattach/revoke、不同提供方复用目标 IPA。
队列路径直接使用实际 RTT alias，没有 Host memfd。fixture 同时编入双方 HELLO selftest；
运行目录保存执行 runner、三个配置、命令及响应、Image/initrd/Firecracker 哈希。
日志已回收控制机 `GPU-SFTP/log/realm-xshm/xshm-realms-transport-v2-20261017/`。
这是新 Host 下的一轮并发启动验证，不能据此声称全部启动竞争问题已消除；
GPU payload、可信 IRQ 与 Realm GPU glmark 仍未执行。

`xshm-realms-transport-rebind-20261017` **PASS，退出 0**：再次并发启动三个 Realm，
257 页、659 条调用，VM 均退出 0。同一 ACTIVE grant 连续完成两轮真实绑定/HELLO/ACK/
忙引用拒绝/解绑；每轮分别取通知基线并验证双方 pending 增加，避免旧计数掩盖第二轮未通信。
同时重复第三方拒绝、共享内存与更换提供方检查。日志已回收至同名控制机运行目录。
两次通过是当前覆盖范围，之前失败仍保留。

按“删除无实际功能路径”的要求，检索整个工作区 C/H 后，删除 Client manager 无任何调用方的
`client_vmshm_manager_ready`、`client_vmshm_manager_map_offset` 两个导出接口，连同头文件声明
与 config-off 空桩；实际 BO 路径继续使用带 handle、归属和范围校验的对象查询。
受影响 manager 对象构建退出 0：`build/proxy-service-v2/client-manager-cleanup-build.log`。
此清理发生在上述硬件运行之后，板端 fixture 与运行目录所记哈希保持不变，未冒称硬件测试了清理后的新 Image。

## GPU 数据池缓存与对象管理器接入（进行中）

Realm 池保持前 1 MiB WB 控制队列；其余页在初始 WB 清零与 PoC 清理后，删除线性 WB 映射，
再用 `dma_common_contiguous_remap` 建立 WC 映射，与 Client BO mmap 默认属性一致。
这个 helper 仅建立虚拟映射，不使用会改变页面私有状态的 DMA 分配/映射流程。
失效映射或 remap 失败时保留整池，不将页面交回分配器。原始字访问按区域选择正确别名。

首轮 Image 构建因缺少命令行 CONFIG_EXTRA_FIRMWARE_DIR 失败（退出 2），记录于
`realm-payload-cache-build.log`；显式指定固定固件目录后构建成功（`realm-payload-cache-build-v2.log`）。
`xshm-realms-payload-cache-20261017` **PASS，退出 0**：新 Image
`504c4a3142cda32bcce6a872bcd6a3d1476a4c2a58d57325a9254eb7254d679c`，
257 页、659 条命令，含 WC 区首个页面、WB 队列两轮绑定、通知与撤销/更换提供方，VM 均退出 0。
日志已回收控制机。这不等于 GPU DMA 验证，也不代表整个 WC 缓冲区逐字节校验。

新增 `pool-bind-gpu`：在同一 RMM 身份检查后，将池后部同时绑定到 Proxy 按 Client endpoint
索引的 allocator domain，以及 Client 本地对象视图；不再从 Host DT 获取 Realm payload 窗口。
原有 `pool-bind` 继续用于纯通信验证。GPU 绑定至少要求池大于 3 MiB、双方编入对应 manager。
Client 对象自己持有 comm 引用，故非 DRM 调用者获得的对象也能阻止解绑；Proxy domain 统计
所有活跃对象，包括已从 handle 表摘除但仍被 pin 的 zombie，尚有对象时不释放 domain。
UNBIND 先 quiesce 队列，再撤销对象 domain；若等待后台 pin，保持 quiesced 并允许后续重试，
不重新开放分配。GPU fence 与对象 pin 仍是实际 GPU 数据回收前提。

同时删除无人调用的 manager_init 和全局破坏式 manager_destroy，失败清理只撤销当前 domain；
删除其写后不读的 handler_registered 字段，去掉正常 KBO 映射时的无条件 drm_err 调试打印。
这些清理的 Image 构建和板端结果以下续记。

`xshm-realms-gpu-flow-20261017` 退出 1：Proxy Realm GPU 被既有 VMM 默认关闭开关拒绝，
命令记录为空，GPU/共享池验证 NOT_RUN。后续 runner 只在显式 `--gpu-flow` 且 VM0 为提供方时
设置 `FC_ALLOW_TRUSTED_GPU_REALM=1`，继续使用项目已有本地可信 GPU 实验模型；
没有跳过 IRQ 或 MMIO 映射，也没有将 spoofed CCA 写成硬件机密保证。

`xshm-realms-gpu-flow-v2-20261017` 退出 1：2049 页逐页校验、RMM 数据 domain 与队列绑定通过，
首次 GPU basic 因 Client 没有 render 节点失败。原因是同一内核启用原生 Panthor 后，Kconfig
按互斥约束禁用了 Client 前端；修复测试使用独立 Client/Proxy 内核，没有删除这个正确约束。
4277 条命令，清理后 VM 均退出 0，后续 GPU 用例 NOT_RUN；原始失败日志已回收。

`xshm-realms-gpu-flow-v3-20261017` **PASS，退出 0**：三个真实 Realm 并发启动，Proxy 独占
实际 GPU，Client 只暴露前端。2049 页（8392704 字节）共享池，463 条串口命令，VM 均退出 0。
双方 `pool-bind-gpu` 两轮绑定成功；每轮 basic、BO mmap 读写、BO lifecycle 和
Group submit syncpoint 均通过，后者各验证 4 次 fence 完成与同编号 syncobj 替换。
完整共享池/第三方拒绝、detach/reattach/revoke、更换提供方回归仍通过。
此处提交使用 syncpoint 测试的零长度 stream，**尚不作为实际图形渲染证明**。

该轮逐页校验改为静态工具在一次命令中逐页执行原有 ioctl：`pool-fill-pages` /
`pool-check-pages`。检查每个 4 KiB 页首个 64 位模式字，首错即失败并记录页号、预期与实际值；
另保留末尾字双向读写。减少串口往返与 fork，不缩减页面覆盖；463 是串口命令数，不能当成
ioctl 或 RSI 调用总数。独立内核、配置、源码 diff、工具 initrd 输入见
`build/proxy-service-v2/realm-payload-manager-v2/`；运行目录记录实际两个 Image 的哈希。
本轮包含 scoped domain 清理、zombie 元数据计数及移除无条件 KBO 调试错误打印后的源码。

## 后续清理：提交路径诊断与权限空实现

在冻结 `xshm-realms-glmark720-20261017` 输入后，删除每次实际任务提交都执行的
`PANTHOR_SYNC_ADDR` 物理地址打印及两次仅供打印的 GPU 页表遍历；保留显式启用的
sync-only 故障诊断。删除无调用者的 `proxy_vmshm_lookup` / `proxy_vmshm_grant_lookup`
重复导出包装，连同声明和 config-off 空桩，实际调用统一使用明确返回 pin 的接口。

检查发现 `required_perms` 原先被忽略，现补齐对象查询的权限包含检查；grant 创建只能
从对象权限降权，grant 查询同时受 grant 和对象权限上限约束。新增自测覆盖对象查询提权拒绝、
grant 创建提权拒绝、只读 grant 写请求拒绝，以及允许权限查询成功与引用释放。
这些是对象 API 的授权检查，不能据此声称共享池内部获得硬件页面隔离。

Proxy 完整 Image 构建退出 0，日志 `build/proxy-service-v2/realm-cleanup-build.log`；
源码 `git diff --check` 通过。以上清理尚未部署，权限自测尚未在硬件执行，不能沿用正在运行的
冻结镜像结果作为此版本的硬件通过证据。

## 128 MiB Realm glmark 首轮：失败保留

`xshm-realms-glmark720-20261017` **FAIL，退出 1**。三个 Realm、每个 512 MiB，
128 MiB RMM 授权池；实际计算着色器 `COMPUTE_CHECK=PASS`，随后 glmark 完整画面校验报告
26 Success / 1 Failure / 6 Unknown。其中 medium-function Failure 是既有精确白名单项，
但 `refract` 另外出现 `GL_OUT_OF_MEMORY`、render target 创建失败，因此不能判 PASS。
失败诊断重跑期间触发 runner 900 秒期限，最终 error 为等待 `XSHM_COMMAND_EXIT` 超时；
完整性能场景、计划缓存统计及正常后续生命周期用例 **NOT_RUN**。

Proxy 还出现 CSG update timeout；Host 三个 Realm vCPU 均在 CPU0 各占约 33%，
不能把全部异常单独归因于池容量。后续候选删除每任务物理地址打印、扩大池，并显式隔离
Proxy/Client 的 CPU 调度；该组合验证只能证明候选整体，不能直接归因某单项收益。
清理阶段记录一条 Client unbind 串口响应歧义；实际日志随后包含 unbind 成功，
三个 VM 最终均退出 0，Host GPU session 释放。完整命令、输入哈希和失败原始日志已回收：
`GPU-SFTP/log/realm-xshm/xshm-realms-glmark720-20261017/`；
外层退出状态位于 `build/lab-runs/xshm-realms-glmark720-20261017/result.json`。

## 多 Client 分池候选（硬件验证中）

移除单池全局状态，改为每 Realm 最多 8 个持久池。每个池独立记录 WC payload、RMM grant、
通道与实际 Client endpoint；BIND 根据 RMM MEM_DESCRIBE 解析本地 IPA。
多个池下普通 INFO/READ/WRITE 必须显式指定本地 IPA，避免隐式选错 Client；
UNBIND 根据已有 grant 定位，关闭/附着的忙保护仅作用于对应通道和池。
不返回部分转换失败的页面，也不以 Host 标识创建授权。

新增双 Client runner：同时保留两套 Proxy domain/队列，逐页核验两块数据，交叉身份拒绝，
并行发起双方 BO/fence 与实际计算检查，再清理双方绑定和 grant。权限自测在测试配置下
针对每个实际 domain owner 运行；生产关闭该配置时不引入测试执行。
候选构建成功，冻结输入位于 `build/proxy-service-v2/realm-multipool/`。
`xshm-realms-two-clients-20261017` 当前运行中，尚无硬件 PASS 结论。

双 Client 首轮 `xshm-realms-two-clients-20261017` **FAIL，退出 1**：两边 BO/fence 检查与
实际计算程序均退出 0，原始日志均为 `COMPUTE_CHECK=PASS count=65536 samples=16 ... alu_iters=64`。
runner 错将最终抽样点数量 `samples` 当成 `--iterations 4`，断言期待 samples=4，触发误判。
按计算源码的 `min(count, 16)` 修正为精确 samples=16，不修改计算程序或成功标准。
首轮后续权限日志收集与正常解绑生命周期 **NOT_RUN**，清理有一条串口响应歧义，
VM 最终均退出 0。日志回收至同名控制机目录，新 run-id 独立重跑。

`xshm-realms-two-clients-v2-20261017` **PASS，退出 0**：332 条串口操作，三个 Realm 均退出 0。
同一 Proxy 同时保留两个 Client 的独立 RMM 池与实际队列；两块 2049 页池逐页校验通过，
歧义池访问和第三方 grant 身份查询被拒绝。双方同时发起的 basic、BO mmap/lifecycle、
Group submit fence 共 8 项检查通过。两边实际计算均为 65536 元素、4 次迭代、64 次 ALU 混合，
最终各抽查 16 个位置，`COMPUTE_CHECK=PASS`。不是对所有 65536 输出逐个比较的证明。
两个实际 owner 的对象/grant 权限拒绝自测通过，解绑、detach/revoke、端点代际检查完成。
更换提供方复用目标 IPA 此轮 **NOT_RUN**，由单 Client 生命周期用例单独覆盖。

命令：`python3 scripts/maintenance/lab-run.py --run-id xshm-realms-two-clients-v2-20261017 --
python3 build/proxy-service-v2/run-realm-multipool.py`；其实际远端完整参数、镜像哈希、输入 runner、
命令响应及日志已回收至 `GPU-SFTP/log/realm-xshm/xshm-realms-two-clients-v2-20261017/`。
Client Image `aeec2d7f146932dffa128ade4ae8b06ee5dbedc17d392c1f3d987893e55e550a`；
Proxy Image `0fb27c3769d1127e6869469e5a507ce53de81e72fe265afd89c4655a6527dbc5`；
initrd `64924e65c6b522c9c7f8eb597bf8a9c549ce419b3caa06b38c77a85b086456ec`。
Proxy CPU0，双方 Client CPU1，各 768 MiB、CMA 320 MiB。此结果证明同时服务两个 Realm 的
功能链路，不声称恶意 GPU 跨 Group 硬件隔离或 GPU 物理执行单元已经同时执行两任务。

**双 Client 通过的可靠性限制：**回收 Proxy kernel-log 后发现一组 `csg-update-timeout`
诊断（约 38.8 秒）；之后两边计算校验和退出均成功。因此上述 PASS 指功能与结果检查通过，
不表示无 GPU 恢复、无超时或适合直接计性能。此异常仍待定位，不能被通过 marker 覆盖。

256 MiB 首轮 `xshm-realms-glmark256-20261017` **FAIL，退出 1**，三个 VM 均退出 0。
附着仍在推进，串口出现 `XSHM_COMMAND_EXIT=3[   82.060605] random: crng init done`；
runner 直接 int() 解析整行失败，GPU 与 glmark **NOT_RUN**。失败记录已回收同名日志目录。
修正为只接受十进制退出码以及可识别的 printk 时间戳后缀，拒绝含混垃圾字符串或越界退出码；
对捕获行、正常退出码和 6 种非法输入做解析验证。无内核、RMM 或 GPU 成功标准变化，
以 `xshm-realms-glmark256-v2-20261017` 独立重跑。

## 实际阻塞：旧 RMM GPU 软件记录表的 32 MiB 上限

`xshm-realms-glmark256-v2-20261017` **FAIL，退出 1**：计算与基础 BO/fence 通过，
glmark 校验仍出现 OOM，三个 VM 均退出 0。该轮日志同时包含大量
`[GPA2HPA] translation failed ret=1 ... entries=512 realm=1`，不能继续把错误简化为共享池容量不足。
性能场景与正常后续生命周期 **NOT_RUN**，日志已回收同名目录。

代码确认 `opencca_gpu.c` 旧软件表只有全局 8192 个不同 HPA，即约 32 MiB；
固件、队列、页表和用户 BO 都会占用。每页线性查整表，批量中途失败还会遗留此前增加的引用，
并已将输入数组前缀改写成 HPA。这个既有上限也曾记于 2026-10-08 路线图。
结合新轮转换失败，这是当前主要阻塞；扩大共享池没有改变它。

候选删除旧表和逐元素改写流程：用 HPA 哈希桶和空闲链表保存归属/引用，固定上限
131072 页（512 MiB，包括所有 GPU 映射用途）。保留跨 Realm HPA 归属拒绝与引用溢出拒绝；
批量获取失败整体回滚，包括给已存在页新增的引用。RSI 使用每 CPU 私有 4 KiB 批次快照，
先完成全部翻译和引用，再在单次数组 RTT 锁下提交全部输出；提交前故障撤销全部新增引用。
撤销也先快照并验证整批输入。常规查询/释放不再扫描全局大数组。

RMM 完整构建退出 0。原生 ASan/UBSan 用例覆盖 131072 个不同页、满表后失败/回收复用、
跨 owner 获取/释放、同页引用溢出和失败批次的新旧引用回滚；同时原端点、共享内存状态机测试通过。
统一入口为 `bash scripts/check/check-rmm-xshm-events.sh`，日志
`build/proxy-service-v2/rmm-gpu-lease-native.log`。这是实际 core 单元测试，
不是设备 GPT/GPC 或真实 RTT 故障注入验证。该表仍只做软件记录，**不配置硬件设备权限**。

新 RMM BSS 为 6831172 字节，总 text/data/bss 约 7 MiB，在平台约 38 MiB 上限内；
完整候选固件位于 `build/proxy-service-v2/firmware-gpu-lease/`。
已通过补丁清单检查。`xshm-gpu-lease-firmware-20261017` 按 SD2 入口部署中，先备份实际启动区，
保留 Host 内核/rootfs；新固件的硬件 GPU 结果尚待验证。

### 固件首轮启动失败与已完成回退

`xshm-gpu-lease-firmware-20261017` **FAIL，退出 1**，SD2 写入后 RMM 初始化完成，
但 Host 未恢复。只校验 RMM 最大尺寸漏掉了另一个装载约束：新 RMM 实际内存
`0x401000..0xa88000`（含 BSS/stack）与 U-Boot 初始代码
`0xa00000..0xaed5c0` 交叠。RMM 清零覆盖后者，不能把该固件视作已部署可用。

`xshm-gpu-lease-rollback-20261017` **恢复成功，退出 0**：在 Pi 独占锁下，仅向 SD2
重写前一版已验证的 identity 固件；Host `#6`、CPU0–1 和 pmthor 恢复，内核/rootfs 不变。
原启动区 12 MiB 备份及失败 UART 保留在
`build/firmware-runs/xshm-gpu-lease-firmware-20261017/`；
该次备份 SHA-256 `8862adbff9d8eae413bf1d14fd7ed22fba6234a39fb2ec3330cbb52ac2f35a76`。
离线恢复无法取得 Host 开始状态，对照明确记 NOT_RUN，不伪造完整前后检查。

根治候选将 U-Boot 初始 `CONFIG_TEXT_BASE` 改为 `0x10400000`，位于平台预留区之外、
现有 script/kernel/fdt/ramdisk 装载点之前。新增实际 ELF 布局检查，包含独立 BSS；
已验证拒绝冲突组合、接受原始回退组合。检查接入固件构建和正常刷写前，
u-boot/opencca-build 的固定 local.patch 与 manifest 校验值同步更新，无上游版本漂移。
修正候选构建/硬件结果以后续记录为准。

### 修正布局固件部署成功

`xshm-gpu-lease-firmware-v2-20261017` **部署与 Host 恢复 PASS，退出 0**。
实际命令为：

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id xshm-gpu-lease-firmware-v2-20261017 --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py \
    --run-id xshm-gpu-lease-firmware-v2-20261017 \
    --firmware build/proxy-service-v2/firmware-gpu-lease-v2
```

构建和刷写前 ELF 检查均通过；新 U-Boot 装载区从 `0x10400000` 开始，
与 RMM 运行区分离。固定补丁 manifest 校验全部 APPLIED。实际写入 SD2：

- idbloader：`3f4e04fffdf17fb5d9ccc286cea5bfcc2fd410657c2f9e791625e20fc71b19ff`。
- ITB：`eb421b38d53c794ec2bb30b73b2a34ba78c86257d6f0f5e01acdf4633cd3250b`。
- RMM ELF：`b51e5b5e8026ef784f04c3db970ea41e092b63a974fef211d7793ff52d927f69`。

证据位于 `build/firmware-runs/xshm-gpu-lease-firmware-v2-20261017/` 和同名
`build/lab-runs/` 目录。Host 内核/rootfs 未替换，CPU 和驱动前后检查通过。
这仅证明固件启动和环境恢复；新 RMM 的 GPU 负载以接下来的独立运行判定。

### 新 GPU lease 固件的双 Client 实际 GPU 回归

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id xshm-realms-two-clients-v3-20261017 -- \
  python3 build/proxy-service-v2/run-realm-multipool.py
```

**PASS，退出 0**，332 条串口操作，三个 Realm 退出码 `[0,0,0]`。
Guest Image/initrd 沿用上述 multipool 固定哈希，RMM 使用本节新固件。
Proxy 同时绑定两个独立 Client 池，分别完成逐页校验、8 项 BO/fence 检查，
两边实际 GLES compute 均为 `count=65536`、4 次执行、`alu_iters=64`，
结果检查 `samples=16` PASS。对象权限自检、解绑、detach/revoke 和端点清理通过。
provider replacement 明确 **NOT_RUN**，由单 Client 的独立生命周期测试覆盖。

日志完整回收到 `GPU-SFTP/log/realm-xshm/xshm-realms-two-clients-v3-20261017/`，
保存逐文件 SHA-256。扫描本次三份 Realm 日志，未见 `csg-update-timeout`、
`timedout`、`translation failed`、FW ping timeout、Oops 或 WARNING marker。
这不抹去上一轮的恢复性 CSG 超时，也不是长期稳定性或性能 A/B 结论。
下一步为同固件 256 MiB 共享池完整 glmark，不能以本轮小池计算代替。

### 删除遗留命令流扫描诊断

按“只保留实际功能”的开发要求，删除 `panthor_drv.c` 中早期 STREAM_TRACE 的
命令流读取、FNV 哈希和前 32 字节打印。该路径为前 512 次提交额外查 BO，
最多扫描每个 stream 的 64 KiB；空 stream 还会打印无实际提交错误含义的 lookup error。
仓库测试和运行脚本没有使用这些 marker，不属于提交或安全校验。

同步删除跨 Proxy 调度器和 Panthor submit 的专用 trace 参数、请求字段，以及每次提交
都会递增的全局原子计数器；没有保留默认关闭的旧分支。资源验证、缓存同步、
fence、任务计划统计和逻辑 GROUP_SUBMIT 审计继续使用原路径。
此处只说明删掉的工作，不声称已量化吞吐提升。
Client/Proxy 构建及独立硬件验证以后续结果为准，当前进行中的 glmark 使用修改前固定镜像。

进一步核对定义、声明、同文件调用和整个工作区调用后，删除 10 个无人调用的函数：
`proxy_vmshm_alloc/free_handle/get/put/obj_order`、`client_vmshm_object_kva`、
`proxy_comm_vmshm_channel_ready/channel_max_payload`、`client_comm_vmshm_max_payload`、
`panthor_vmshm_bo_create`。最后一个已由实际使用的 payload-backed BO 创建路径替代。
相应 EXPORT_SYMBOL、公共声明和配置关闭时的 stub 一起删除。
随后构建指出 max_payload 导出删除后其私有 helper 也已无人调用，继续删除该 helper，
共移除 11 个函数；不以 unused 标记保留死代码。

另将只在本文件使用的 6 个函数改为 static：对象 type/perms/gpa 查询，
Client 通信 ready/send/recv。保留其实际逻辑，删除公共导出、声明及 stub。
不是按“其他文件无调用”直接删函数；这些内部调用继续服务实际管理器和 RPC 路径。

### 256 MiB 共享池完整 Realm glmark：功能通过，性能未达标

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id xshm-realms-glmark256-v3-20261017 -- \
  python3 build/proxy-service-v2/run-realm-multipool.py --glmark
```

**功能 PASS，退出 0**。共 11369 条串口操作，三个 VM 退出码 `[0,0,0]`。
使用 GPU lease v2 固件与前述 multipool Guest 固定镜像，不包含随后删除诊断/API 的候选。
256 MiB（65536 页）共享池、控制队列、两次 GPU 绑定周期、BO/fence、解绑和撤销通过；
更换提供方后复用相同 borrower IPA，并验证读取的是新提供方数据，检查通过。

| 项目 | 实际结果 |
| --- | --- |
| renderer / 完整计时场景 | Mali-G610 (Panfrost) / 33 |
| validation | 26 成功、1 已知基线例外、6 无判据；unexpected failures 0 |
| compute / glmark / allocation clean marker | PASS / PASS / PASS |
| 任务计划合计 | registered=88，runs=3760，复用生效 |
| GPU 地址转换失败 marker | 0 |
| 独立 CSG update timeout | **7 次**，按时间戳去重，排除 kernel-log 重复转储 |
| glmark score | **7，性能未达标，不作为性能通过或加速证据** |

超时时间为启动后 359.690687、360.292412、559.904452、570.178028、650.478281、
651.286057、710.757490 秒。任务随后继续完成，但不能以成功退出覆盖它们。
`GLMARK_CLEAN_RESULT=PASS` 只涵盖脚本中的分配/导出/映射/OOM 检查，
不表示内核没有 CSG 超时；性能问题仍需定位。此测试使用三 Realm、两在线 CPU 的功能配置，
也不是与普通 VM/原生驱动的同条件 A/B。

日志、原始 summary 和额外分项判定在
`GPU-SFTP/log/realm-xshm/xshm-realms-glmark256-v3-20261017/`。
与上一轮双 Client 日志均已回收，并逐文件对照板端 SHA-256 验证；
`assessment.json` 区分功能 PASS、稳定性 WARN、性能 NOT_QUALIFIED。
这补齐了此前大内存图形流程，但不替代新组合的完整 32 项或可信 IRQ 验收。

### 无用代码清理版本的独立验收

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id xshm-realms-api-prune-20261017 -- \
  python3 build/proxy-service-v2/run-realm-multipool.py \
    --images build/proxy-service-v2/realm-no-stream-trace
```

**PASS，退出 0**：332 条操作，两个 Client 同时绑定独立池，8 项 BO/fence 检查和两边实际
GPU compute 的 16 个抽样位置校验通过；权限自检、解绑、detach/revoke、端点清理通过。
provider replacement **NOT_RUN**，由上一轮大池生命周期独立覆盖。三 Realm 退出码均为 0。
本轮三份日志中未见 CSG timeout、地址转换失败、FW ping timeout、Oops、WARNING，
也没有已删除的 STREAM_TRACE marker；不由此推断长负载超时已经修复。

- Client Image：`cca26bce75f3951f87b3cb1ba2f96e670cfe374c886b69f0278b97aa02eb6b2c`。
- Proxy Image：`24d502b69776f371e668d2d96f71dc7e33c06c04f5d8f43f88ac4fb24ba5404a`。
- initrd 沿用 `64924e65c6b522c9c7f8eb597bf8a9c549ce419b3caa06b38c77a85b086456ec`。

实际输入哈希与固定候选逐一匹配。候选保存 tracked diff、新增源码、配置和各组件基础提交，
位于 `build/proxy-service-v2/realm-no-stream-trace/`。Client/Proxy 最终构建均退出 0，
日志 `client-pruned-apis-final-build.log`、`proxy-pruned-apis-final-build.log` 无编译 warning/error；
Guest 源码和主仓库 diff whitespace 检查通过。完整 glmark 没有在这个仅删无用代码的镜像上重复执行，
不能把前一轮镜像哈希改写为本轮。

日志回收到 `GPU-SFTP/log/realm-xshm/xshm-realms-api-prune-20261017/`，9 个板端文件逐一
SHA-256 对照通过。结束审计确认 pmthor、CPU0–1，无残留 VM/broker 或 loop；
RK MemAvailable 约 3.05 GiB，根分区空闲约 14.22 GiB。


## RMM 事件 IRQ 接入（开发中，实测结果另列）

轮询版本的 Proxy 空队列使用 `msleep(1)`，在当前 HZ=250 配置下会引入 tick 级等待。
本阶段接入真实虚拟中断，保留现有队列和持久事件协议，不再另建消息通道。

- RMM 为所有 Realm 保留最后一个 GIC LR，并独占虚拟 INTID 127。Host 提交的该 LR 必须为零，
  其他有效 LR 不得使用 INTID 127；进出 Host 时不导出、覆盖私有 LR。RMM 在 REC0 进入时依据
  自己的 endpoint pending 状态注入，保留 Active/Pending 状态并合并通知。
- 新 `IRQ_BIND` 为命令 16，仅允许 REC0。REGISTER 增加 capability 16，完整能力为 31。
  所有现有命令值和 ioctl 结构大小保持不变。Guest 安装 GIC 处理器后才绑定 IRQ。
- 已授权对端 NOTIFY 命中接收者 ARM 状态时，RMM 持久记录 IRQ pending，再以实验性
  RMI exit `0x70` 请求 Host 唤醒目标 RD 的 REC0。Host 通过安全 KVM 引用和 vCPU kick 转发调度提示；
  它不决定通知授权、事件序列、中断号或实际注入内容。Host 仍可拒绝调度，不能提供可用性保证。
- Guest 的单个 IRQ 接收器检查各已绑定通道的 RMM 状态，仅调度对应 RX work。RX 排空队列，
  QUERY/ACK/ARM 后再检查一次队列，处理“发布发生在布防前后”的竞态；移除 transport 时同步取消
  订阅与 RX work。Client 复用已有 completion/waiter，Proxy 复用已有 dispatch worker。
  有 IRQ 的 Realm 不启动轮询 dispatcher；普通 VM 的已有 IRQ/轮询路径仍有实际用途。

当前实现范围为本平台 GICv3、固定 INTID 127、每 Realm 一个 vCPU（REC0）。当前 VMM 的 GPU
中断使用 124–126，fixture 不分配 127；推广到更多设备或多 vCPU 前须统一保留 IRQ 号并验证路由。
新 Host 为 Realm 少使用一个 LR，需与该 RMM 成套部署；不能将新 RMM 单独换到未预留 LR 的 Host。
这仍是 OpenCCA 上的软件授权/事件保护实验，不恢复该板缺失的真实 GPT/GPC 或 GPU SMMU 保护。

构建与策略检查：Host、Client、Proxy 的 Image 构建退出 0，未发现编译 warning/error；
RMM ARM 构建退出 0，保留原有 RWX LOAD / discarded build-id 链接提示。
`bash scripts/check/check-rmm-xshm-events.sh` 退出 0，包括实际 IRQ core 的 Host 伪造拒绝、
私有 LR、Active+Pending 和合并检查；这些 ASan/UBSan 原生结果不冒充硬件攻击测试。
日志为 `build/proxy-service-v2/{host,client,proxy,rmm}-trusted-irq-build.log`、
`rmm-trusted-irq-native.log`。固定输入位于 `build/proxy-service-v2/realm-trusted-irq/`。
新增 runner `--trusted-events` 要求 capability、真实 `/proc/interrupts` 计数、第三方拒绝和合并判定，
避免只根据事件计数或“ARM 成功”宣称中断工作。


### IRQ 组合部署与真实事件首轮

| run-id | 结果 | 退出码 |
| --- | --- | ---: |
| `xshm-host-trusted-irq-20261017` | 实际 SD p3 备份、替换 Image、文件系统/提取哈希检查、SD2 部署与 Host 恢复 PASS | 0 |
| `xshm-host-irq-reservation-baseline-20261017` | 新 Host 配旧 cap15 固件/清理版 Guest；双 Client 332 条操作，BO/fence、两边实际 GLES 计算、权限/生命周期、VM[0,0,0] PASS | 0 |
| `xshm-trusted-irq-firmware-20261017` | ELF 布局、实际启动区备份、SD2 固件部署与 Host 恢复 PASS | 0 |
| `xshm-trusted-events-v1-20261017` | 新组合三真实 Realm：cap31、IRQ_BIND127、第三方请求拒绝且无中断、两次合法通知合并为一次真实 GIC 中断、VM[0,0,0] PASS | 0 |

Host 为 `6.12.0-opencca-pmthor-opp3 #7`，Image SHA-256
`9eb02466ea282125bd29cab14bd0c04a88849dab8b840cb551a482d1d3fbeacf`，
Module.symvers 与部署前一致。新 kernel 分区 SHA-256
`b92c03540ae240369d250c8a75be6799be8da4ce8068d52cb09e32d6c7ee3abd`；
备份为 `build/proxy-service-v2/host-trusted-irq/kernel-before.img`，
等于已验证的 populate 分区 `d8e915e776bddccbe09e673c18f550f9286c19589c25918e593dbfff302e04f0`。

新固件 idbloader SHA-256 `306660354fa41947f42ee99e156957e625256adff8fffecb93a2afbba5242581`，
ITB `03abbb527962368530a335c04cc722583adad16d25805d2519df402145449ba7`，
RMM ELF `5ead15ccb30454ca1fad932f67b4e79ae3459f5dc609814d768a1a4fdbfb7d3b`。
固件刷写前实际 12 MiB 备份 SHA-256
`f69ca27a483761a8dd9e5182c5b5ee5398a1ced7db59ff55c0e1852caafbdd5e`。
启动证据位于 `build/firmware-runs/xshm-trusted-irq-firmware-20261017/`。

首轮 IRQ 实测从 `/proc/interrupts` 得到计数 `[0,0,0] → [0,1,0]`，
不是以 pending 序列充当 IRQ。此轮未绑定数据池或 GPU，GPU 与完整 glmark 必须另行验收。
对应的控制命令为 `lab-run.py --run-id <上表ID> [--allow-rk-reboot] --` 后分别调用：

```text
python3 build/proxy-service-v2/host-trusted-irq/deploy.py
python3 build/proxy-service-v2/run-realm-multipool.py --images build/proxy-service-v2/realm-no-stream-trace
python3 scripts/run/deploy-rmm-firmware.py --run-id xshm-trusted-irq-firmware-20261017 --firmware build/proxy-service-v2/firmware-trusted-irq
python3 build/proxy-service-v2/run-trusted-events.py
```

两轮 Realm 原始日志各 9 个文件已回收并逐文件 SHA-256 对照板端，验证结果保存在
`GPU-SFTP/log/realm-xshm/<run-id>/controller-verification.json`。部署与 wrapper 证据均保留，未覆盖旧失败。


### 中断版双 Client GPU 首轮通过

`xshm-realms-trusted-irq-two-clients-v1-20261017`，退出 0，VM 退出码 `[0,0,0]`。
命令为 `lab-run.py --run-id <该ID> -- python3 build/proxy-service-v2/run-realm-multipool.py
--images build/proxy-service-v2/realm-trusted-irq --trusted-events`。
两个独立 2049 页共享池、两个同时存续的绑定，8 个实际 BO/提交 fence 用例均通过；
两 Client 并发 GLES `count=65536 / iterations=4 / alu-iters=64`，各检查 16 个结果样本通过。
权限负面、解绑、撤销和端点清理通过；更换 provider 在本轮明确 NOT_RUN，交由单 Client 生命周期轮次。

真实事件中断计数：三方负面测试前 `[0,0,0]`，两次通知后 `[0,1,0]`，
GPU 工作负载和解除绑定后 `[313,126,129]`。没有用轮询顶替中断验收。
原始日志未发现 CSG/FW ping timeout、translation fault、WARNING/Oops 或 STREAM_TRACE marker。
9 个文件已回收到 `GPU-SFTP/log/realm-xshm/<该ID>/` 并逐文件校验；
完整 33 场景 glmark 和性能资格以后续独立结果为准。


### 中断版完整 Realm glmark：功能 PASS，稳定性 WARN

`xshm-realms-trusted-irq-glmark-v1-20261017` 退出 0，VM `[0,0,0]`，
11,384 条操作、256 MiB 全页首字校验、两轮队列/GPU 绑定、更换 provider/同 IPA 新数据、
解绑和撤销均通过。完整 33 场景、Mali-G610 (Panfrost)、validation 26 成功/1 已知例外/6 无判据、
unexpected 0，score **10**。任务计划 `registered=86 / runs=4884`，事件 IRQ 最终 `[41817,24114,0]`。
命令为上一条双 Client 命令增加 `--glmark`，run-id 换为本条。

按实际时间戳去重的 `CSG ... update request timedout` 共 **15 次**；未发现 FW ping timeout、
translation fault、WARNING/Oops marker。该轮的 `GLMARK_RESULT=PASS` 和 clean marker
不覆盖这些内核超时；`assessment.json` 明确 functional PASS、stability WARN、performance NOT_QUALIFIED。
与此前轮询 score 7 的比较包含不同 Host/RMM/Guest 实现，不能称严格单因素 IRQ 加速结果。

原始 9 文件已回收并与 RK 逐文件 SHA-256 对照，位于
`GPU-SFTP/log/realm-xshm/xshm-realms-trusted-irq-glmark-v1-20261017/`。
Client Image `081292c8f7f17f6eaf14e30f21511073e5e623a60e8c08d97b36f9beaaf36a52`，
Proxy Image `5de751322ac56be9b080c6601dc99fb05a6057ee39d61445f985655cdfc0dabf`，
initrd `0fe9d08fb1fa0568fc79c684b63e19a68a792c605f3e187dd19e3777e999aef1`。

## 固件缓存同步修正候选

代码中 Realm 私有 GEM 使用 cached CPU 映射。此前运行时读取固件 ACK 或状态，
会对整个 MCU shared section 调用 DMA_FROM_DEVICE 失效，包括仍可能由 CPU 修改的 input；
而 doorbell toggle 直接读取 cached ACK。这不符合输入/输出的缓存所有权划分，
但不能仅凭审查断言它解释了全部 CSG 超时或性能差距。

本候选删除旧运行时整区失效 helper，改为仅失效已初始化的 global/CSG/CS output 范围。
ACK 轮询只同步对应字所在缓存行，toggle 在锁内同步 ACK 后再构造新请求；
独立 queue interface 的 CPU 同步也只覆盖 4 KiB 偏移后的 output。
启动/重载时的整区同步、发布输入前的 device clean 仍有实际用途，继续保留。
未增大 CSG 等待期限或删除超时检查。

同次构建发现 `panthor_clk_init()` 已没有调用者，原调用与 devfreq init 只剩注释。
已删除该闲置函数和注释残留；Guest 的实际 GPU 时钟归 Host 管理，未改动 Host 时钟驱动。
最后 Proxy 构建退出 0，无 warning/error；日志
`build/proxy-service-v2/proxy-fw-output-sync-final-build.log`，冻结输入
`build/proxy-service-v2/realm-fw-output-sync/`，Proxy Image SHA-256
`5acc7e8bdace9cffc0eebd5f080b3c707b9c3f51f52e6367efee96ad320d01e8`。

`xshm-realms-fw-output-sync-two-clients-v1-20261017` 双 Client 回归退出 0，VM `[0,0,0]`，
347 条操作、BO/fence、两侧真实 GLES 计算、权限负面、IRQ 合并/送达、解绑撤销均通过。
原始日志已回收校验；kernel listed markers 以 assessment 为准。
命令：`lab-run.py --run-id <该ID> -- python3 build/proxy-service-v2/run-realm-multipool.py
--images build/proxy-service-v2/realm-fw-output-sync --trusted-events`。
完整同条件 glmark 的功能、超时及性能须以后续结果判定。


### 缓存修正版完整 Realm glmark：功能通过，超时仍未消除

`xshm-realms-fw-output-sync-glmark-v1-20261017`，外层退出 0、VM `[0,0,0]`。
运行时间 UTC 13:24:31–13:41:27。完整命令：

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id xshm-realms-fw-output-sync-glmark-v1-20261017 -- \
  python3 build/proxy-service-v2/run-realm-multipool.py \
  --images build/proxy-service-v2/realm-fw-output-sync --trusted-events --glmark
```

11,384 条操作通过，包括 256 MiB 全页首字校验、两轮绑定、BO/fence、
同 IPA 更换 provider 后读取新数据、解绑、撤销及端点清理。
完整 33 个计时场景，renderer Mali-G610 (Panfrost)，score **10**；
validation 为 26 成功、1 已知例外、6 无判据，unexpected 0。
计时会话计划 `registered=88 / runs=4945`；全轮汇总为 `90 / 4949`。
真实事件 IRQ `[0,0,0] → [0,1,0] → [42988,24957,0]`，第三方拒绝及通知合并检查通过。

| 同参数单轮对照 | 原 IRQ 版 | 缓存修正版 |
| --- | ---: | ---: |
| 完整 glmark 功能 | PASS | PASS |
| score | 10 | 10 |
| 唯一时间戳 CSG 超时 | 15 | 4 |
| FW ping / translation fault / WARNING / Oops marker | 0 | 0 |
| 性能资格 | NOT_QUALIFIED | NOT_QUALIFIED |

对照保持 Host、RMM、Client、initrd、rootfs 和 runner 相同，只替换 Proxy Image；
Proxy 差异为运行时 output 缓存同步及无调用者时钟代码清理。
本轮 4 次超时时间戳为 `488.674811`、`506.920907`、`687.132732`、`699.036297`。
单轮计数降低不足以证明全部因果关系或可重复的稳定性改善；分数相同，未测得吞吐提升。
`GLMARK_CLEAN_RESULT=PASS` 不覆盖 Proxy 内核中的 CSG 超时。

原始 9 文件已回收到 `GPU-SFTP/log/realm-xshm/<run-id>/`，逐文件 SHA-256 与 RK 对照一致；
`controller-verification.json`、`assessment.json` 和外层
`build/lab-runs/<run-id>/{result,before,after}.json` 保留。
最终判定：functional PASS、stability WARN、performance NOT_QUALIFIED。
新 Host/RMM/Realm 组合的完整 32 项仍为 NOT_RUN，不沿用普通 VM 旧版的 32 PASS。

后续应先定位残余 CSG ACK/中断与调度延迟，再验收性能；不通过增大超时或删除检查制造 PASS。
成功路径热日志还被旧回归作为验收依据，后续清理须同步改为结果/状态检查。
GPU shadow 页表未在本阶段实现。


## 补齐 ACK 读取与 Realm 空闲调度诊断

### ACK 读取修正：双 Client 和完整 glmark 功能通过

`panthor_fw_read_ack()` 统一承担 Realm ACK 缓存同步和 `READ_ONCE`。
原请求 toggle 宏复用该函数；调度器生成 `CSG_STATUS_UPDATE`、`CSG_ENDPOINT_CONFIG`
以及 tiler OOM 应答时，也先取得同步后的 ACK，不再直接读取可能陈旧的 cached ACK。
同步 helper 中未经运行时验证的“output 独占页面”注释已删除，仍按缓存行执行维护。

Proxy Image `c3cb2a35bb136724aab76ceb5daa8d0ee14aedbceb7018505ff73e2b823b639d`；
冻结包 `build/proxy-service-v2/realm-ack-read/`。Client、initrd、rootfs、runner、Host #7 和
已部署 IRQ 固件均与前一轮相同。Proxy 构建退出 0，无 warning/error。

| run-id | 范围 | 结果 |
| --- | --- | --- |
| `xshm-realms-ack-read-two-clients-v1-20261017` | 347 条操作、独立双池、实际双 Client GLES、BO/fence、IRQ、权限与释放 | rc 0，VM `[0,0,0]`，PASS，所列内核异常 marker 为 0 |
| `xshm-realms-ack-read-glmark-v1-20261017` | 11,384 条操作、256 MiB、完整 33 场景、provider 更换与最终撤销 | rc 0，VM `[0,0,0]`，功能 PASS，score 10，稳定性 WARN |

命令沿用 `run-realm-multipool.py --images build/proxy-service-v2/realm-ack-read --trusted-events`，
第二轮增加 `--glmark`；均通过 `lab-run.py --run-id <对应ID> --` 执行。
glmark validation 26 成功/1 已知例外/6 无判据，unexpected 0。
唯一时间戳 CSG 超时 2 次：`159.952990`、`653.461827`。
未发现 FW ping timeout、translation fault、WARNING/Oops marker。
IRQ 最终 `[42750,24812,0]`。两轮各 9 个原始文件已回收并逐文件 SHA-256 验证；
`GPU-SFTP/log/realm-xshm/<run-id>/assessment.json` 保留稳定性及性能 NOT_QUALIFIED 判定。

15 → 4 → 2 是三个候选各一次运行的计数，不是统计显著性结论；三者 score 均为 10。

### WFI 与定时器候选的依据及边界

对 Host #7 的 20 秒实际观测保存在 `build/proxy-service-v2/realm-idle-host7.json`：
三台 VM 的 `wfi_exit_stat/blocking/halt_wakeup` 均为 0；Proxy vCPU 占用约 99% 核，
Client 与空闲观察者各占用约 50% 核。源码中 REC entry 未请求 WFI/WFE trap，
Realm timer enable 还在设置软件 timer enabled 前提前返回。

候选实现：Host 请求 WFI/WFE trap；WFI 使用 KVM halt，WFE 使用已有 yield；
RMM 已递增 PC，Host 不再次递增。RMM 在 WFx 出口检查私有 LR 的 Pending 状态，
避免 Host 在看不到该中断时阻塞 REC。Host 为 Realm 启用软件 deadline 唤醒，
只使用 RMM 报告的 timer snapshot，不装载/保存 Realm 硬件 timer 寄存器；
到期后重新进入 RMM，由 RMM 检查实际 timer。通知期间的 Host wake flag 只负责调度，
INTID 127 的注入权仍在 RMM；不保证恶意 Host 的调度可用性。

另一项实测：20 秒 UART 采集 `uart-irq-firmware-runtime.log` 得到 56,403 字节，
出现逐条 `SMC_c40001ad` XSHM 调用输出，采集时处于共享池生命周期阶段。
通用 RSI logger 在 `RSI_LOG_LEVEL=40` 下确实打印自定义调用，不能只搜索 XSHM handler 的 INFO。
新平台构建默认 `RSI_LOG_LEVEL=0`，保留 LOG_LEVEL=40 的错误/警告等诊断；需要逐调用 trace 时显式开启。
这项配置也属于新固件的差异，因此未来组合分数变化不能单独归因于 WFI。

Native ASan/UBSan endpoint/memory/GPU lease/IRQ 检查通过，RMM/Host 构建和固件布局检查通过。
固件第一次打包因错误 ELF 路径失败，修正后成功，失败日志 `firmware-realm-wfi-pack-missing-input.log` 保留。
Host 候选 #10 Image `ddd76575bc467b10f9afb7593a66f7e4b7c733a1be730db3d68fddb248f0ce98`。
RMM ELF `b70d9d28bc4fa1340a40e7dd61c235e4d53c943a4886c368cc4b3587081e8c96`。
以上构建证据不能替代板端结果，部署与实际运行结论以下续记录为准。


### WFI 候选失败与撤回：不属于当前实现

以下失败没有被后续 PASS 覆盖：

| run-id | 事实与处置 |
| --- | --- |
| `xshm-host-realm-wfi-20261017` | 初次 Host 构建漏传 LOCALVERSION，实际 release 为 `6.12.0+`，与模块目录不匹配；UART 可登录、网络未起来。确认刷写结束后仅中断该 run 的 SSH 等待，外层 rc 130，保留 Image/分区/UART |
| `xshm-host-realm-wfi-v2-20261017` | 用显式 `LOCALVERSION=-opencca-pmthor-opp3` 重建，Pi-only offline 恢复 SD2 成功，rc 0。Host #11 Image `a105561c689aedde68666caf9ecc85540653e70bb2c6069ff6956bb254571747`，分区 `c62218b39643d287cf88529a0eeac6a76c1321fbcfc27852263f9d22879f1f89`，SSH/pmthor 正常 |
| `xshm-realm-wfi-events-v1-20261017` | 三 Realm 早期启动等待 XSHM_READY 超时，rc 1；清理后 VM `[-15,-15,-15]`。权限、通知、GPU 项均 NOT_RUN。9 文件已回收校验 |
| `xshm-host-wfi-rollback-20261017` | 从实际 SD 读回失败 #11 分区并核对上列 SHA；随后恢复已验证 Host #7，rc 0，CPU 0–1、SSH、pmthor 正常 |

对启动失败时的串行只读观察显示 `wfi_exit_stat=6 / blocking=3`，三 vCPU 为 S 状态，
但没有保存该瞬时观察为独立结构化文件，不能当作完整唤醒证明。
源码审查另发现 `opencca_check_pending_timers()` 在保存 old state 前已覆盖它，
并直接修改硬件 IMASK；原始 timer 状态与 RMI 报告的关系需要单独验证。
这只是失败定位线索，尚未通过修正后的启动测试证明全部根因。

为避免引入未完成的 timer 虚拟化，已删除本轮 WFI/WFE handler、trap 配置、软件 timer 候选分支、
私有 LR pending helper 和相应候选测试。Host/RMM tracked patch 与 `realm-ack-read/` 中保存的
已通过 IRQ 基线逐字节比较一致，新增 IRQ 文件也恢复到该基线。
候选 patch 和失败镜像只保存在忽略的 build 证据目录，不作为可执行源码备用实现。
原 IRQ 机制已通过真实中断计数和实际任务测试，但尚未证明可从真正阻塞的 Host vCPU 唤醒。

### 独立的关闭 RSI trace 候选

恢复已验证 Host #7 Image `9eb02466ea282125bd29cab14bd0c04a88849dab8b840cb551a482d1d3fbeacf`、
分区 `b92c03540ae240369d250c8a75be6799be8da4ce8068d52cb09e32d6c7ee3abd` 后，
构建并部署 `xshm-no-rsi-trace-firmware-20261017`，rc 0。
RMM 实现恢复到原 IRQ 版，只将 `RSI_LOG_LEVEL` 从 40 设为 0；`LOG_LEVEL=40` 不变。
平台 makefile 显式传入该配置，逐调用 trace 为 opt-in。

- RMM ELF：`1e5f07ff2e2bb951b736003c1eb5c9c6676de8d427a0dc12050dcdfe4f543498`。
- idbloader：`15ce031bf1dd450f16a5364641fc4a8a1099fde9674547eec61c6f3e9bacb55b`。
- ITB：`c9f8a2583a957e2f5b5258c1d4b672634a4734d43316db15b6d2dfe891f81dba`。
- 源码/配置/构建证据：`build/proxy-service-v2/firmware-no-rsi-trace/`；实际 SD 启动区备份、UART、恢复检查在 `build/firmware-runs/xshm-no-rsi-trace-firmware-20261017/`。

前置 `xshm-wfi-firmware-events-20261017`（旧 Host #7、带未启用 WFI guard 的 RSI trace-off 固件）
已通过 49 条事件操作、实际 INTID127、权限拒绝和合并检查，rc 0。
它不等于当前纯 trace-off 固件的 GPU 验收，当前双 Client/glmark 必须独立记录。

正式控制机入口 `scripts/run/run-realm-xshm.py` 已用于两轮事件测试：
读取冻结包的 `hashes.json`，使用包内 runner；校验远端哈希，相同则跳过上传，
实际命令和输入记录在外层 `realm-launch.json`。入口要求对应 lab wrapper 正在运行。
wrapper 的 RUN_ID 改为始终使用本轮参数，避免继承父进程旧值；固件部署已验证该修正。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/proxy-service-v2/realm-ack-read --workload compute
# --workload events 为三方事件检查；--workload glmark 为完整 256 MiB/33 场景流程。
```


### 关闭逐调用日志、删除临时追踪及独立回归

本轮清理直接作用于实际调用路径：删除 Proxy 的 VM_BIND 明细追踪函数、类型名转换、
全局原子计数器、参数传递及两个旧 TRACE_LIMIT 定义；将 Client/Proxy 的提交、等待、
BO 创建和 VM_BIND 高频常规日志改为按需启用的 `pr_debug`。
错误、跨会话权限拒绝、资源生命周期和任务计划汇总仍保留。
旧单 VM runner 删除了 24 条针对这些可选调试日志的强制检查；实际探针 PASS、
负面用例、三轮 Group 提交、syncobj 替换及 fence 完成检查均保留。

Client/Proxy ARM64 Image 均编译退出 0，无 `warning:` / `error:`，Guest 与父仓库
`git diff --check`、runner shell 语法检查通过。源码与构建输入冻结在
`build/proxy-service-v2/realm-quiet-rpc/`，没有修改正在运行的载荷。

| run-id | Guest 冻结包 / workload | 结果 | CSG 超时 / GPU 翻译故障 |
| --- | --- | --- | --- |
| `xshm-no-rsi-trace-two-clients-v1-20261017` | realm-ack-read / compute | rc 0；347 条操作、双 Client 实际计算与权限检查 PASS | 1 / 0；稳定性 WARN |
| `xshm-no-rsi-trace-glmark-v1-20261017` | realm-ack-read / glmark | rc 1；terrain 提交错误，计时结果只识别 32/33；功能 FAIL | 94 / 1；性能未合格 |
| `xshm-quiet-rpc-two-clients-v1-20261017` | realm-quiet-rpc / compute | rc 0；347 条操作、双 Client 实际计算、独立池、权限与释放 PASS | 0 / 0；仅代表本轮短测 |
| `xshm-quiet-rpc-glmark-v1-20261017` | realm-quiet-rpc / glmark | rc 0；11,384 条操作、完整 33 场景、256 MiB 池及提供方更换 PASS | 74 / 0；稳定性 WARN，性能未合格 |

以上均使用 Host #7 与纯 IRQ、RSI_LOG_LEVEL=0 固件，准确固件哈希见上一节。
命令为 `python3 scripts/maintenance/lab-run.py --run-id <表中ID> --`
加 `python3 scripts/run/run-realm-xshm.py --images build/proxy-service-v2/<对应包> --workload <对应模式>`。
每轮外层退出码、输入哈希和完整命令在 `build/lab-runs/<run-id>/`。
工作负载的九个原始文件均回收到 `GPU-SFTP/log/realm-xshm/<run-id>/`，
逐文件 SHA-256 与远端一致；`assessment.json` 按唯一 Guest 内核时间戳去重统计上述故障。

新 Guest：Client SHA-256 `e1896ec9fbc6483d0271cbf62620681383c1e5c569add7bc649cee7624a9ebab`；
Proxy `304ad24bb63cf21ef4d94ee729504980a4f6165d364d2b466462c4538ffa0047`。
initrd、runner 和 rootfs 沿用上一节冻结版本，没有覆盖只读准备好的 rootfs。

完整新 Guest 运行 renderer 为 Mali-G610 (Panfrost)，1280×720、null-noop、finish，
validation 为 26 成功 / 1 已知例外 / 6 无判据，unexpected 0；score 94。
记录到 78 次计划注册、39,244 次成功执行，IRQ 最终计数 `[419963,419354,0]`；
VM 正常退出 `[0,0,0]`。CPU/GPU 观测为 1.8 GHz / 300 MHz，证据在
`build/proxy-service-v2/quiet-rpc-clock-observation.json`。
与日志开启时 score 10 相比，单轮分数上升，但 CSG 超时仍未解决，不能据此宣称稳定加速。
只关闭 RSI trace 的失败轮也输出 score 94，故不能把分数变化归因于本轮 Guest 日志清理。
74 与 94 次故障是两个不同候选的单轮计数，不是统计显著的改善证明。

失败轮 terrain 出现 `MESA: error: panfrost_batch_submit failed: 22`，
Proxy 有 `TRANSLATION_FAULT_0`，但旧底层脚本仍输出 CLEAN_RESULT/RESULT=PASS。
外层因 32/33 场景严格检查拒绝，未把它计入成功；提供方更换等后续流程没有完整执行。

已修正源码中的判定缺口：底层 gpu-smoke 将提交错误纳入 validation/clean 检查，
clean 失败使总体失败；Realm runner 在断言前保存分数、场景数和提交错误，并明确拒绝提交错误。
以真实旧成功与本次失败日志回放，成功保持通过，失败返回 125 或断言拒绝，且保留 score 94。
这两项判定修正在上述 quiet-rpc 冻结测试之后完成；随后已重建进下节
input-publish、idle-irq-ack 的 initrd/runner，并用于实际硬件测试。
完整 32 项新组合仍为 NOT_RUN。

两轮 glmark 后 Host 均恢复 pmthor、CPU 0–1，无 Firecracker 或 loop 遗留。
下一步仍是定位 CSG_STATUS_UPDATE 握手超时；不放宽等待期限、不恢复逐调用日志来掩盖问题，
也不将本轮功能通过解释为 GPU 跨 Group 的硬件机密隔离。

### 运行时输入区发布与 IRQ 线程应答 idle

继续精简固件接口的缓存维护边界：启动/重载仍同步完整固件区，运行时 CPU
只发布 global、CSG、CS 的输入结构，不再每次 doorbell 清理整个共享固件区。
GPU 输出只经输出区同步读取，避免把 CPU 缓存中的过期输出重新写回。
新增输入同步函数检查偏移与长度；缓存同步失败继续报告，不忽略错误。

第一版同时补齐 idle 应答的发布：更新 GLB_IDLE 请求后立即同步 global input，
不再依赖后续可能根本不发生的 doorbell。第二版把该应答移入 job IRQ 线程，
避免等待持有调度锁的 tick；删除旧的延迟 global/idle 处理函数，保留一个原子事件位，
由原有工作队列在调度锁内消费并触发 tick。CSG 处理、100 ms 应答期限、
超时诊断与复位策略均保留，没有通过跳过状态查询消除错误记录。
请求位更新继续使用 firmware interface 自身的自旋锁，未增加一套重复调度框架。

两版均 ARM64 Image 编译退出 0，日志无 `warning:` / `error:`；
Guest `git diff --check`、Python runner 编译及 gpu-smoke shell 语法检查通过。
Host #7、RMM 纯 IRQ/RSI_LOG_LEVEL=0 固件不变。冻结包分别是
`build/proxy-service-v2/realm-input-publish/` 与
`build/proxy-service-v2/realm-idle-irq-ack/`，运行期间未修改。

| 输入 | SHA-256 |
| --- | --- |
| Client Image，两版相同 | `e1896ec9fbc6483d0271cbf62620681383c1e5c569add7bc649cee7624a9ebab` |
| input-publish Proxy Image | `6b932f281df1f356b573820a09fc00999cb4bf3791ab275d52814f5bf1fb79df` |
| idle-irq-ack Proxy Image | `07a1e18d30bb5ceca74b1544cf8f1d4eb0daae29d4f1a67508eecbfef728644e` |
| 新 initrd，两版相同 | `7dcebe1158e78890c47399172988302049af0adcf45717697dabe5a300aded1e` |
| 新 runner，两版相同 | `eeb5497891bf4670adcec094134eb7d5d2bd1c9ce8182865afbe8ada63db0867` |

新 initrd/runner 已包含上节提交错误判定修正；准备好的只读 rootfs 未覆盖，
仍为 `5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60`。
每轮完整命令、退出码、冻结输入见 `build/lab-runs/<run-id>/`；命令使用上节同一
lab wrapper/Realm launcher，包名与 workload 见下表。

| run-id | 冻结包 / workload | 结果 | 唯一 CSG 超时 / 翻译故障 |
| --- | --- | --- | --- |
| `xshm-input-publish-two-clients-v1-20261017` | realm-input-publish / compute | rc 0；347 操作、双 Client 实算、独立池、权限与释放 PASS | 0 / 0 |
| `xshm-input-publish-glmark-v1-20261017` | realm-input-publish / glmark | rc 0；11,384 操作、33 场景、256 MiB 池与提供方更换 PASS；score 96 | 42 / 0；稳定性 WARN |
| `xshm-idle-irq-ack-two-clients-v1-20261017` | realm-idle-irq-ack / compute | rc 0；347 操作、双 Client 实算、独立池、权限与释放 PASS | 0 / 0 |
| `xshm-idle-irq-ack-glmark-v1-20261017` | realm-idle-irq-ack / glmark | rc 0；11,384 操作、33 场景、256 MiB 池与提供方更换 PASS；score 95 | 53 / 0；稳定性 WARN |

input-publish 长测 renderer 为 Mali-G610 (Panfrost)，validation 26 成功 / 1 已知例外 /
6 无判据，提交错误列表为空；78 次计划注册、39,790 次成功运行。
IRQ 最终计数 `[427245,426605,0]`，VM 退出 `[0,0,0]`。
两次 compute 最终 IRQ 分别为 `[370,186,186]`、`[346,174,174]`，VM 均退出 `[0,0,0]`。
上述四轮每轮九个原始文件均已回收到 `GPU-SFTP/log/realm-xshm/<run-id>/` 并逐文件验证 SHA-256；
各目录 `assessment.json` 保留功能判定和按 Guest 内核时间戳去重的故障计数。

idle-irq-ack 长测同样 validation 26 / 1 / 6、提交错误列表为空；
78 次计划注册、39,604 次成功运行；IRQ 最终 `[423978,423342,0]`，VM 退出 `[0,0,0]`。
没有上述统计口径中的 FW ping 超时、GPU 翻译故障、WARNING 或 Oops；
有 CSG 超时，因此性能判定仍为 NOT_QUALIFIED。CPU/GPU 观测为 1.8 GHz / 300 MHz，
见 `build/proxy-service-v2/idle-irq-ack-clock-observation.json`。
96 与 95 是不同候选各一轮的结果，不能作为性能提升或下降的可靠结论。

进一步检查 quiet-rpc 与 input-publish 长测中的超时快照：分别有 74、42 个唯一 CSG
快照，全部只有 CSG_STATUS_UPDATE 位（0x20）未应答，全部伴随 global idle 待应答；
对应队列快照均无 in-flight 作业。这只能缩小定位范围：没有 in-flight fence
不能证明命令尾部、scoreboard 和阻塞状态均已完全排空，故没有据此跳过查询。
idle-irq-ack 长测的全部 53 个唯一超时快照中 global REQ 已等于 ACK，但 CSG 仍差 0x20，
说明 global idle 应答延迟不是超时的唯一原因，不能把第二版称作根因修复。
该轮对应队列快照也全部无 in-flight 作业；三轮对照统计保存在
`build/proxy-service-v2/idle-irq-ack-diag-comparison.json`。
外层后检查确认 Host 恢复 pmthor、CPU 0–1，无 Firecracker/loop 遗留。

冻结第二版后，源码另将 idle 事件发布从 `atomic_set` 改为有完整顺序保证的
`atomic_xchg`，保证另一个 CPU 的工作线程观察到 fw_events 前已能观察到 idle 事件。
该源码增量 Image 编译退出 0、无警告错误，尚未部署；上述第二版硬件测试仍使用
表中 `07a1e18d…` Image。当前每个 Realm 为单 vCPU，不能代替多 vCPU 顺序性回归。
当前新组合完整 32 项仍为 NOT_RUN；GPU shadow 页表仍按范围约定未实施。

### 分层 doorbell 发布顺序：首次完整无所列故障的长测

检查实际缓存同步调用顺序发现：旧代码先更新 global `doorbell_req`，再按
global → CSG → CS 顺序清理输入。于是存在 MCU 已看到父 doorbell、却仍读到旧子输入的
时间窗口；后续 MMIO doorbell 本身不能保证重新产生一次请求位变化。
这是从代码推导的失序风险，没有捕获 MCU 内部逐条读取轨迹，不能将推导说成硬件直接观测。

新代码按依赖关系发布：CS 输入 → CSG doorbell 位 → CSG 输入 → global doorbell 位
→ global 输入 → MMIO。CSG 状态请求同样先发布到内存，再修改 global doorbell。
只同步本次选中的 CSG/CS；ping、halt 和 global 初始化只发布 global 输入，
不再无差别扫描全部组。原生非 Realm 路径保留原有通知语义。
固件加载处重复的 `map_wc=false` 赋值及其日志删除，该属性已由 GEM 创建路径统一设置。
上一节仅编译的 idle 事件 `atomic_xchg` 顺序修正也包含在本候选中。

该处理遵循设备通知前先完成数据可见性的基本约束；缓存同步与 CPU 内存屏障分别处理，
不能用普通 `wmb()` 代替非一致性 DMA 缓存维护。参考
[Linux DMA API 指南](https://docs.kernel.org/core-api/dma-api-howto.html)。

Proxy Image 编译 rc 0，无 `warning:` / `error:`；冻结包
`build/proxy-service-v2/realm-doorbell-order/`，Proxy SHA-256 为
`7e860516684c6eff7e5ee1892337fb54d61d69f59a60071163f56618425296e7`。
Client、initrd、runner 与上一节相同；Host #7、纯 IRQ trace-off 固件及 rootfs 不变。

| run-id | workload | 结果 | 内核故障统计 |
| --- | --- | --- | --- |
| `xshm-doorbell-order-two-clients-v1-20261017` | compute | rc 0，347 操作，双 Client 实算、独立池、权限负面及释放 PASS；IRQ `[346,174,174]` | 五类均 0 |
| `xshm-doorbell-order-glmark-v1-20261017` | glmark | rc 0，11,384 操作，33 场景、256 MiB 池、撤销及提供方更换 PASS；score 98 | 五类均 0 |

五类指按唯一 Guest 内核时间戳统计的 CSG update timeout、FW ping timeout、GPU translation
fault、WARNING、Oops，并非声称穷尽所有可能故障。两轮 VM 均退出 `[0,0,0]`；
外层后检查 pmthor、CPU 0–1，无 Firecracker 或 loop 遗留。
每轮九个原始文件均拉回 `GPU-SFTP/log/realm-xshm/<run-id>/`，与远端逐文件 SHA-256 一致；
目录内 `assessment.json` 保存判定，外层 `build/lab-runs/<run-id>/` 保存命令、输入和退出码。

命令均为 `python3 scripts/maintenance/lab-run.py --run-id <表中ID> --`
加 `python3 scripts/run/run-realm-xshm.py --images build/proxy-service-v2/realm-doorbell-order`
及 `--workload compute|glmark`。
长测 Mali-G610 (Panfrost)，validation 26 成功 / 1 已知例外 / 6 无判据，提交错误为空；
78 次计划注册、40,706 次成功运行，最终 IRQ `[436089,435475,0]`。
观测 CPU/GPU 为 1.8 GHz / 300 MHz，证据
`build/proxy-service-v2/doorbell-order-clock-observation.json`。
与上一版 53 次超时相比，本轮没有再出现该签名；单轮 score 95→98 不能证明统计显著的性能改善。

随后准备独立队列发布候选：先同步命令字节再写 INSERT，运行时仅发布 CPU 输入页；
GPU 输出读取按完整缓存行失效，启动时仍初始化并同步完整 8 KiB 接口。
该候选 Proxy `7165c2185e9e63612611942eb6ceb5d2fee2098de9f1d4552b562bf51641c025`，
冻结包 `build/proxy-service-v2/realm-queue-publish/`。
runner 扩展到与普通 VM 矩阵对应的全部 17 类 DRM 检查，并在结束前检查三个 Realm 的内核日志；
上述五类故障任一出现则整体 FAIL，保留故障行与前面已完成的命令。
新 runner SHA-256 `d235448dadb29526b04d9d0af01e6ca48f92ec1b4b0360675e17f64e0d467ee6`。
真实旧 53 次超时日志回放被拒绝，无故障双 Client 日志回放通过；17 个模式与工具 PASS marker
及普通 VM 清单逐项对应检查通过。这些离线检查不代替候选的硬件结果。

### 队列发布与扩展 API：双 Client 通过，保留脚本失败轮

队列候选 Image 编译 rc 0，无编译警告/错误，源码与冻结补丁一致。
命令字节的缓存发布移到 INSERT 更新之前；运行时不再清理 GPU 输出页，
输出失效长度向上取整到 DMA 缓存行。初始化仍先清零并同步完整接口。
统计开启时，命令缓存发布费用计入 ringbuf_write，避免把该成本漏出阶段统计。

| run-id | 输入 / workload | 整体结果 |
| --- | --- | --- |
| `xshm-queue-publish-two-clients-v1-20261017` | realm-queue-publish / compute | rc 1，FAIL；两边各 17 类 API 与实际计算已通过，但末尾权限日志检查失败；后续正常生命周期与内核健康门槛 NOT_RUN，执行失败清理 |
| `xshm-queue-publish-two-clients-v2-20261017` | realm-queue-publish-v2 / compute | rc 0，PASS；376 条控制操作，两边各 17 类 API、实际计算、权限及完整释放均通过 |

v1 失败原因是证据读取时机：末尾读取的 Proxy dmesg 从 Guest 10.927273 秒开始，
启动绑定阶段的权限自测日志已回卷；旧断言没有错误说明，summary 中 error 为空。
不将已完成的 API 检查等同整体 PASS，也不据缺失日志断言权限实现失败。
v2 把权限日志断言移到两边绑定成功之后、工作负载之前，仍要求两个 owner 各自 PASS，
并为缺失情况提供明确端点信息。最终内核健康检查同时读取当前 dmesg 和持续保存的串口文件，
避免早期错误因 dmesg 回卷而漏检；五类故障门槛保留，没有放宽。

两轮 Proxy Image 均为 `7165c2185e9e63612611942eb6ceb5d2fee2098de9f1d4552b562bf51641c025`；
v2 runner 为 `79ff65cfc0e785464a40371097aaf895a17b4280bc40733cdddcda1e8091611e`。
Client/initrd/Host/RMM/rootfs 未改。v2 三个 Realm 的五类内核故障列表均为空，
最终 IRQ `[3615,1803,1807]`，VM 退出 `[0,0,0]`；provider replacement 仍由单 Client
长测覆盖，不冒充本轮已测试。两轮各九个原始文件均回收并逐文件 SHA-256 验证。
命令与前后资源见 `build/lab-runs/<run-id>/`，原始结果与 assessment 见
`GPU-SFTP/log/realm-xshm/<run-id>/`。后检查均恢复 pmthor、CPU 0–1，无实验进程或 loop 遗留。

命令沿用 lab wrapper + Realm launcher，`--images build/proxy-service-v2/<表中输入>`
及 `--workload compute`。同一 v2 冻结包随后启动独立完整长测
`xshm-queue-publish-glmark-v2-20261017`（相同入口、`--workload glmark`）；
结果见下一节。原来的 32 项普通 VM 矩阵包含 Host PFN、
直通及 ML 等不同项目；Realm 两边各 17 类 API 不能改称新组合“32 项全部通过”。

### 队列发布版本完整长测通过

`xshm-queue-publish-glmark-v2-20261017` 于 15:43:58–15:56:10 UTC 完成，
外层及工作负载均 rc 0；11,413 条控制操作。相同冻结包、Host #7 和 trace-off RMM，
没有在运行中替换脚本或内核。

- Mali-G610 (Panfrost)，默认 33 个场景，score 98；validation 26 成功、1 已知例外、
  6 无判据，提交错误列表为空。
- 256 MiB 池的映射、撤销、不同提供方复用同一借用方 IPA 均 PASS；两次绑定各执行
  17 类 API。三个 Realm 的内核健康门槛通过，五类故障列表均为空。
- 末次 Proxy 内核快照保留的会话统计为 78 次计划注册、40,603 次运行；其中 glmark
  主会话 `session=21` 为 76 / 40,599。此统计不是启动以来所有会话的总和，
  不用 dmesg 已回卷的早期记录补算。复用确实生效，不能据此宣称总 RPC 降低同等比例。
- IRQ 最终 `[438304,437463,0]`；VM 退出 `[0,0,0]`。结束恢复 pmthor、CPU 0–1，
  没有 Firecracker 或 loop 遗留，RK 可用内存约 3.05 GiB、磁盘约 14.12 GiB。

原始目录 `GPU-SFTP/log/realm-xshm/xshm-queue-publish-glmark-v2-20261017/`
九个文件全部与远端逐文件 SHA-256 一致；`summary.json`、`assessment.json`、
`controller-verification.json` 分别保存完整状态、故障计数和回收校验。
外层 `build/lab-runs/xshm-queue-publish-glmark-v2-20261017/` 保存命令、输入、退出码与资源前后状态。
这是本组合的一次完整长测，不是同条件原生性能对比或长期稳定性结论。

### 6-job 批量提交与拒绝语义验收

现有 `group-submit-syncpoint` 保留原有四次句柄/fence 生命周期检查，并补充：
同一 Group 的 6 个 job 各自 signal 独立同步对象，连续两次提交，每次先 reset 再等待
全部六个 fence；随后把末尾 job 的队列索引设为无效，要求整批返回 EINVAL。
再尝试导出全部六个 sync_file，均须返回 EINVAL，验证被拒绝批次没有发布部分 fence，
包括尚未 signal 的 fence。该探针使用空 stream，验证批次与同步语义；实际 GPU 执行由
同轮 compute 和前节 glmark 验证，不将空任务称为 shader 计算。

静态 AArch64 工具构建 rc 0，无编译警告；只替换 initrd 中的探针，生产内核、RMM、
Host 和 runner 均与前节相同。冻结包 `build/proxy-service-v2/realm-batch-smoke/`
另存探针源码与二进制，逐文件哈希检查通过，生产 Guest diff 与包内补丁一致。

| 新输入 | SHA-256 |
| --- | --- |
| initrd.cpio | `e782a24c38ca9074363cfd79ef0dc9d19f0385fb35057a7e79a6e97738b0300a` |
| panthor_ioctl_smoke | `4666c4d5413a92d36fc72b2105032068cae6c47580df97f4e222f403a68e23b3` |
| panthor_ioctl_smoke.c | `f9a03a6a7a28f9b795f5a73fe5d975a6e6874c81aae59d6ab1db3649134ed188` |

命令：

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id xshm-batch-two-clients-v1-20261017 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/proxy-service-v2/realm-batch-smoke --workload compute
```

结果 rc 0、PASS，376 条控制操作；双 Client 各 17 类 API、实际计算、权限负面及释放
检查均通过。两个 Client 各自打印两条 `GROUP_SUBMIT_BATCH ... fences=all PASS`
及一条 `GROUP_SUBMIT_BATCH_REJECT jobs=6 partial_fences=0 PASS`，已从回收日志逐项核对。
三个 Realm 的五类内核故障均为 0，IRQ `[3681,1823,1839]`，VM 退出 `[0,0,0]`。
该双 Client 轮不执行提供方更换，覆盖由前节独立长测提供。

九个原始文件均已拉回 `GPU-SFTP/log/realm-xshm/xshm-batch-two-clients-v1-20261017/`
并与远端 SHA-256 一致；外层 `build/lab-runs/xshm-batch-two-clients-v1-20261017/`
记录退出码、输入及前后资源。结束 pmthor、CPU 0–1，无 Firecracker 或 loop 遗留。
当前生产内核已有完整长测及补强探针验证；没有因探针增加而重跑同一内核的 33 场景，
也没有把本轮双 Client API 数量改称完整 32 项回归。
