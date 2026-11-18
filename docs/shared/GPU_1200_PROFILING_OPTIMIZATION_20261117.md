# GPU 1200 分优化：基线、profiling 与候选记录

用户于 2026-11-17 重新指定完整 720p 达到 1200 分的目标，并要求保持关键安全机制。已验收的运行版本仍是[当前基线](CURRENT_BASELINE.md)中的 1170 分组合；本轮实验独立保存，不覆盖工作区尚未验收的安全诊断候选。

本轮已完成同期对照、3轮分段诊断及C1/C2/C3候选验证，尚无新增保留提分。C1/C2已撤回；C3修正环境入口后仍未见实际worker启用证据且未达保留线。当前目标仍是相同条件下1200分，不以这些局部结果宣布完成。

## 比较条件与验收

单 Client、Mesa 25.0.7、1280×720 全部 33 场景、实际 GPU 594 MHz，沿用原 CPU 布局、内存预算、会话配额 8、固件与 rootfs。每轮保留 validation 26/1/6、重点场景保护、可信 IRQ 与 Proxy 负例、内核健康及资源恢复检查。Native 不重跑，历史 Native 只能作为注明版本和条件的参照。

用户已再次确认：1200目标按相同GPU594MHz、原CPU布局与资源预算验收，继续进行软件优化。

先运行当前冻结共享版本对照，再运行独立诊断镜像；根据当前热点实现候选，以未插桩的完整 720p 判断收益。目标分数需要确认轮，并在保留候选上完成相关离线安全检查和双 Client 功能回归，不能把诊断成绩、局部耗时或操作数下降当成目标完成。

硬件测试统一通过 `scripts/maintenance/lab-run.py` 持有 Pi/RK 独占锁。本轮起始资源检查通过，Host 为 `6.12.0-opencca-pmthor-opp3`，pmthor，CPU0–3 在线，无实验 VM/broker 和 RK loop 残留。历史验收闲置 CPU0–1，计分时同样为 CPU0–3；各轮均检查并恢复实际进入时的设置。实体 SD2 FIT 逐字节摘要必须匹配冻结固件。

## 为什么重新 profiling

历史 S8 已将可信完成后的 Client chain IRQ-work 在本地有界处理，不能继续把 S8 之前约 26 µs 的回调耗时当成当前可消除开销。历史任务释放约 0.316 µs、job 释放约 1.467 µs，尚不支持优先引入复杂对象池；这些不同轮次数据也不能直接相加预测分数。

本轮诊断只修改 Client 的统计代码，每 61 次采样一次：

| 位置 | 分解内容 | 用途 |
| --- | --- | --- |
| 成功的单成员任务清理 | run finish 总量、task put、job finish、job put、run free | 确认已完成任务的清理是否仍在关键路径 |
| 原 fence 通知 | scope 初始化、原 dma_fence_signal 及回调、原本地 IRQ-work drain | 确认 S8 之后剩余通知开销及实际处理项数 |
| 真实 task staging | 原 realm_gpu_task_stage 调用耗时与错误数 | 判断请求捕获、命令快照、准入或准备是否值得继续拆分 |
| 既有计数 | PREPARE/READY/COMPLETE、worker 队列间隔及有界等待 | 将新增子区间放回原执行流程，避免只看局部 |

清理的父子区间重叠；staging 与清理的采样总体不同。时钟、抢占和插桩包含在墙钟中，不能作为纯 CPU 成本。解析器只接受完整终态报告，并核验回收日志 SHA；缺行和总体不一致时拒绝分析。

诊断从已验收的完整 Guest 源码快照生成，16 项受记录的 Guest 源文件摘要核验通过。移除标记统计块可逐字节恢复原 Client 源码。独立 AArch64 构建通过，配置摘要保持 `7f1854c4530abcd39ee4b1ffa372446a7cccdfa1808daf1300eff9dc82295f9f`；Proxy、initrd、runner、RMM/Root/FW 均沿用冻结输入。原本地 IRQ-work 实际核心与 chain 模型、4 个编译错误变体拒绝检查通过。

## 研究来源与待验证方向

| 来源或方向 | 可借鉴的具体机制 | 本项目采用前的约束 |
| --- | --- | --- |
| 既有设计复核 | 预处理、事务批量提交、复用初始化以及执行期间准备后续请求 | 按本轮热点选择；S3/S8 已有收益不再次计功；不恢复已否决的 S5 提前完整 DRAIN |
| [AvA batching 队列](https://github.com/utcs-scea/ava/blob/c40e33fada3520990552f99af6113f4671aaaa06/guestlib/extensions/guest_cmd_batching_queue.cpp) | 异步请求排队；按容量、等待预算或同步边界发送；同步请求无积压时直接发送 | 借鉴边界，不照搬等待常数。逐任务身份、快照、授权、依赖错误传播、部分执行状态和独立终态必须保留 |
| [Linux 6.12 dma-fence 文档](https://docs.kernel.org/6.12/driver-api/dma-buf.html) | 正确安排 signalling、回调及锁，避免通知阶段引入阻塞依赖 | 不提前 signal；不绕过原回调、RCU、PENDING/BUSY 和错误传播；不在完成关键路径新增可阻塞分配 |
| [Linux 6.12 workqueue 文档](https://docs.kernel.org/6.12/core-api/workqueue.html) | 按实测决定接收worker是否需要调整调度；WQ_HIGHPRI使用提高nice优先级的独立worker池 | 同一work的不可重入条件包括不更换workqueue；不得混用普通与高优先级队列。原接收预算、锁、ARM重查和cancel_work_sync仍须保留 |
| 请求/内存预初始化 | 有界槽位或可复用不可变描述，减少确有实测占比的分配及初始化 | 每次仍捕获新请求并绑定当前代次；引用、旧访问和安全退休结束前不得复用 |
| 单次请求阶段合并 | 在同一可信事务内减少重复封装、调用与调度 | 不跨不可信修改或硬件副作用复用证明；按任务保留完成和撤权依据 |

AvA 固定研究提交为 `c40e33fada3520990552f99af6113f4671aaaa06`，README 和三份 batching 源文件已下载并记录 SHA。其 worker 示例的长度/返回值处理不构成本项目可信接口实现依据。外部方案的收益不能搬用为本项目的收益。

## 运行与证据

| 项目 | run-id / 输出 | 当前状态 |
| --- | --- | --- |
| 起始资源与身份 | `build/gpu1200-20261117/resources-preflight-r1.json` | PASS；两台角色确认，无资源门槛问题 |
| 独立诊断构建 | `build/gpu1200-20261117/profile-build-r1/result.json` | 构建退出 0；硬件 profiling 待测 |
| 原通知机制回归 | `build/gpu1200-20261117/local-irq-regression-r1/summary.json` | 实际核心/chain 模型 PASS；4 变体拒绝 |
| 同期共享对照 | `gpu1200-control-720-r1-20261117` | 完整720p 1170；外层、负载、UART与Realm退出0，9份日志SHA及原全部门槛通过 |
| 当前完成与 staging 诊断 | `gpu1200-profile-720-r1-20261117` | 1168，仅诊断；外层/原全部门槛通过，9份日志SHA；Client Image SHA `d2cfe6cce7d7009c019bc69125fa8800998cbb1878657cd3edf29b270857704c` |
| Proxy 等待内部诊断 | `gpu1200-proxy-profile-720-r1-20261117` | 1170，仅诊断；外层/原全部门槛通过，9份日志SHA；原200µs/64次窗口未改 |
| C1：分散剩余提示许可 | `gpu1200-c1-720-r1-20261117` | 1121，较同期1170为−49/−4.1880%，撤回；96组模型、5变体与完整原运行门槛通过不代表提速 |
| C1后恢复 | `gpu1200-restore-after-c1-20261117` | 原四输入SHA核验、前后资源/驱动/CPU恢复通过；未运行新负载，不算新性能结果 |
| P16：通信返回路径诊断 | `gpu1200-p16-rpc-720-r1-20261117` | 1167，仅诊断；9份日志SHA及原门槛通过，IRQ→RX-work平均22.730µs |
| C2：Client接收队列调度 | `gpu1200-c2-720-r1-20261117` | 1133，较1170为−37/−3.1624%，撤回；原运行检查通过，主源码3处入队修改已逐字回退 |
| C2后恢复 | `gpu1200-restore-after-c2-20261117` | 原四输入SHA、前后资源/驱动/CPU核验通过，退出0；未新增负载或性能成绩 |
| C3首轮：环境未进入suite | `gpu1200-c3-glthread-720-r1-20261117` | 1169，配置未生效，不能评价GLThread效果；未保留 |
| C3修正入口 | `gpu1200-c3-glthread-720-r2-20261117` | 1160，较1170为−10/−0.8547%，环境已被读取但未见实际GLThread worker；原全部运行门槛通过，未保留 |
| C3后恢复 | `gpu1200-restore-after-c3-r2-20261117` | 原四输入SHA及前后资源核验通过，退出0；CPU0–3/pmthor，无VM/loop；不计新性能成绩 |
| C4首轮：构建组合错误 | `gpu1200-c4-720-r1-20261117` | 1132，但对象文件核验发现混入旧C2接收策略与P15插桩，不能归因纯C4；证据保留 |
| 原冻结包交错对照 | `gpu1200-control-720-r2-20261117` | 1164，较首轮1170为−6/−0.5128%，原全部运行门槛及9SHA通过 |
| 强制重建的原版Client | `gpu1200-rebuild-control-720-r1-20261117` | 1163，与同期原包1164相差−1/−0.0859%；对象策略/无旧插桩及原全部运行门槛/9SHA通过 |
| 强制重建的纯C4 | `gpu1200-c4-clean-720-r1-20261117` | 1166，相对同构建控制1163为+3/+0.2580%，未达预定1182保留线；原全部运行门槛及9SHA通过，不保留 |

可复验命令与构建日志保存在上述目录，硬件外层命令、退出码、FIT/UART/健康及前后资源记录保存在 `build/lab-runs/<run-id>/`。研究下载失败（404/429）也保留，不将失败页面作为论文证据。

同期对照既有 Client 计数覆盖458122个成功单任务：主动短暂停约60.614µs/任务、完成阶段立即排队间隔约3.316µs/任务、entry-lock区间约0.290µs/任务。observer RPC自身总体约276.523µs/任务。后者的全部调用与COMPLETE计时保留的调用总体不同，不能从COMPLETE总时长扣除observer总时长。暂停也与GPU执行重叠，不能全部作为可消除CPU时间。证据为 `build/gpu1200-20261117/control-existing-profile.json`；下一步进一步确认Proxy原有限等待的退出原因，区分调度等待、设备未完成与查询额度。

Client诊断的7497个完整清理样本：run finish约6.894µs、task put约0.358µs、job finish约5.936µs，其中scope开始0.376µs、原fence signal及回调0.511µs、本地IRQ drain3.763µs、job put0.862µs，run free约0.203µs。独立staging总体7497样本、约17.826µs。父子区间不能相加。日志前缀保留了一个缺失header的零计数quota-probe末行，初版解析器因此拒绝；修订后只明确剔除该零行，全部非零数据仍要求完整header、8行、总体及区间守恒。失败记录与最终分析均保留，未补值。

Proxy诊断包含14个完整session报告、458092次wait、26556099次实际查询：ready92901（20.280%）、额度耗尽330915（72.238%）、窗口结束仍pending34276（7.482%）、错误0；平均57.971次查询/wait。7509个有限窗口内部样本约169.926µs，不与Client异群体RPC时长相减作为纯通信成本。证据分别为 `gpu1200-profile-720-r1-20261117-profile.json` 与 `gpu1200-proxy-profile-720-r1-20261117-proxy-profile.json`。

## C1 候选及保留条件

当前证据支持尝试把剩余提示观察留在已有Proxy vCPU，使Client能够运行其他工作：前16次仍立即查询；其后各次查询间增加4µs有限间隔，总窗口上限400µs，每任务仍最多64次。等待到达deadline后不再发起下一次查询。每次实际读取仍完整进入原RMM checked操作，hint仍不能signal fence或释放资源；Client仍核对关闭/绝对deadline并执行真实FINISH。请求布局、owner、token/代次、RMM许可额度及硬件控制均不变。

它与历史S4的“所有查询间隔25µs、原窗口200µs”不同：保留快速前缀，并把已有额度用于更长的有限重叠观察。400µs不是被证明最优的参数，可能延后OOM/故障服务或增加共享session占用，必须以完整720p、重点场景和后续相关功能验证决定保留；不预报得分。第一轮时序模型发现等待已到deadline后仍可能进行一次短间隔查询，候选补充deadline退出后第二轮96组时序及授权/错误用例通过；初轮失败保留，没有部署失败原型。

C1模型另拒绝5个成功编译的错误变体：取消后段间隔、放大窗口、跳过checked读取、伪造ready、绕过保留字段检查。模型底层时钟、RSI、锁与session均为替身，不证明实体并发或GPU安全。

另一次独立构建缓存搬移实验未通过逐字节Image身份检查，已否决、不用于C1。C1沿用已完成的独立Proxy全量构建目录做正常单文件增量构建，原诊断source/Image事先冻结；已验收源码、冻结包和工作区安全候选均未覆盖。

C1统一记录：在同样64次许可内延长有限提示观察｜同期共享1170→C1 1121｜−49/−4.1880%｜仅Proxy提示时机改变，原Client/RMM/Root/FW/initrd/负载及CPU/GPU/内存/配额保持｜`gpu1200-c1-720-r1-20261117`，外层/负载/UART/Realm退出0，33场景、validation26/1/6、全部重点场景、IRQ负例/健康恢复及9份日志SHA通过，详见 `gpu1200-c1-720-r1-20261117-audit.json`｜**撤回，不保留、不以减少轮询宣称提速。**

实测Client短暂停60.614→16.456µs/任务（−72.851%）、立即排队间隔3.316→2.074µs/任务，但observer RPC自身总体276.523→358.700µs/次（+29.718%）。不能把不同总体的COMPLETE计时与observer总时长相减；独立RPC增加与整机降速共同否定本候选。完整比较见 `gpu1200-c1-720-r1-20261117-wait-comparison.json`。不直接用另一组窗口/间隔常数重试同机制；下一步定位原通信发送、ARM/等待和IRQ到接收worker的开销，保留原200µs/64次提示策略。

## P16、C2与工作区离线检查

P16在原RPC统计输出处读取已有IRQ→RX-work计数，不修改原统计时点或执行策略。456407个通知合并后的样本均值22.730µs；RMM_TASK类型460301次、错误/超时0，平均279.949µs，其中发送5.274µs、ARM/重查1.630µs、completion wait270.323µs。IRQ记录可能覆盖/合并多个通知，RPC类型混有提示/dispatch/stop，不能相减得到纯通信或CPU成本。统计是全局累计快照，解析器取最后完整快照，不累加重复输出。

C2仅将Client IRQ、startup、budget续排的3个入队点统一改为`queue_work(system_highpri_wq, ...)`；256条预算、原work函数/解析/锁/ARM重查/waiter寿命/同步cancel保持。反向替换可逐字恢复原源。实际RX模型验证8192条响应分32批、ARM到达竞态、错误/空队列/启动路径，并拒绝4个编译错误变体；原迟到回复2变体和重放5项通过，相关未改函数与候选逐字一致。Linux真实调度仍由硬件负载验证。

C2统一记录：提高Client接收work的nice优先级｜同期1170→1133｜−37/−3.1624%｜仅Client3处入队改变，RPC诊断关闭，原其他输入与资源不变｜`gpu1200-c2-720-r1-20261117`，外层/负载/UART/Realm退出0，原33场景、validation、重点场景、IRQ/健康/资源与9SHA通过｜**撤回；未达到预先指定的1182保留线，不追加确认轮。** RPC自身总体276.523→269.352µs/次（−7.171µs），短暂停60.614→62.169µs/任务；局部调度或RPC区间改善不足以支持整机提速。证据为对应`-audit.json`、`-wait-comparison.json`。

全量离线矩阵在计划终止前自行完成，不能记为取消或PASS：`gpu1200-c2-full-offline-r1-20261117`实际执行62个非aggregate检查，55通过、7失败；矩阵76项scoped PASS、12项FAIL、4项物理NOT_VERIFIED。7个失败为rsi-memory-chain、memory-ops、private-heap、cache-set、live-summary、control-residue、control-view-lifecycle，主要涉及既有RMM诊断源码的`debug.h`编译依赖及owner-reclaim账本检查。源码与开始时manifest逐项相同，无运行中漂移。回退C2的3处Client改动后，`gpu1200-c2-rollback-offline-control-r1-20261117`定点重跑相同7项，7项全部复现；相关RMM输入未改。因此这些是当前未部署工作区源码/夹具的既有问题，不能归因C2，也不能继承此前全量PASS。本轮保留失败证据，未改这些安全候选来追求分数；实体仍采用原已验收RMM/FW。

## C3：Client用户态批处理候选

在同一GPU594MHz、单vCPU预算下评估已安装Mesa25.0.7的`mesa_glthread=true`。板端libgallium与本地参考库SHA均为`333dfaa45db020be43045149404252cdbc99b7338cd14adffe464758f6d0ac20`。核对固定版本源码：`glFinish`的API描述为`marshal="sync"`，GLThread会先等待/执行队列批次；`glthread_nop_check_framebuffer_status`默认false。保留原shader-cache禁用、完整33场景、validation及`frame-end finish`，不启用no-error或Framebuffer检查旁路。

参考：[Mesa25.0.7 GLThread](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/src/mesa/main/glthread.c)、[DRI环境选项与线程安全检查](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/src/gallium/frontends/dri/dri_context.c)、[同步Finish描述](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/src/mapi/glapi/gen/gl_API.xml)。上游默认在少核环境关闭该功能，因此本轮只是可撤回候选，没有预报收益。

冻结包只改变initrd中的`glmark.env`和只读线程观测；Client/Proxy/runner及RMM/Root/FW逐字沿用基线。原CPIO逐字往返验证通过，其他所有条目保持；原script移除观测块可逐字恢复，shell语法检查通过。观测每5秒最多读取该基准进程64个task，要求实际出现Mesa命名的`:glN`线程，不能仅凭环境变量或ATTENTION文本宣布启用。若有收益，最终配置还需无额外线程观测的确认测量；当前诊断组合不单项归因GLThread。所有GPU任务继续走原授权、FINISH、可见性及退休路径。

首轮实际suite将`GPU_SMOKE_ENV_FILE`设为`/tmp/performance.env`，所以追加到`glmark.env`的变量未进入工作负载。1169只是无效配置尝试的实测，不能用于判断GLThread。此入口选择错误已修正：r2只在冻结`performance-suite.sh`的有效环境入口导出`mesa_glthread=true`，保留原所有工作负载/验证设置，另保留只读线程观测；原`glmark.env`恢复逐字不变。CPIO完整性、其他条目、脚本反变换与shell语法验证通过。

r2日志有69次Mesa环境覆盖提示，证明选项已到达，但整个采样仍只有1个task，`:glN`观测为0，因此未证明GLThread实际启用。Mesa保留其map-unsynchronized线程安全等能力检查；本轮未强制绕过这些检查，也不把环境文本当成启用证据。r2完整720p1160，外层/负载/UART/Realm退出0，原33场景/validation/重点场景/IRQ/健康/恢复及9SHA通过；未达到保留线。结果见 `c3-r2-activation-analysis.json` 与 `gpu1200-c3-glthread-720-r2-20261117-audit.json`，首轮错误归因文件与修订也保留。

统一记录：尝试现有Client API批处理｜同期共享1170→C3有效环境轮1160｜−10/−0.8547%｜只改变有效suite环境及有界只读观测，原内核/RMM/FW、CPU/GPU与完整负载不变；功能实际启用未验证｜`gpu1200-c3-glthread-720-r2-20261117`，原全部运行门槛与9SHA通过｜**未保留，继续维持1170基线与1200目标。**

## 后续：请求快照预初始化的审查边界

对照实现的`realm_gpu_task_stage()`逐任务分配/清零4KiB快照页，RMM同步私下捕获后立即释放；`gpu_call_locked()`对输入页做整页clean。C4已实现并完成独立验证，但尚无保留收益。历史同样本wrapper分解中分配/复制约2.076µs，当前外层staging约17.826µs，两者不是同一轮内部计时，不能相减推导收益。

C4已在独立源码副本实现上述候选，尚未保留为基线：每个managed Group创建时分配一页私有CPU输入，逐任务仍清零、复制并验证；已有`gpu_lock`同时覆盖捕获与原同步RMM调用。Group创建失败时清理未暴露页面；已登记的隔离/失败创建保留页面，失败或未完成销毁仍保留，原可信销毁/失效条件满足后才释放。每个任务对象和token仍重新创建，原引用与畸形返回处理保留。

只有TASK_STAGE_BATCH/HINT且同一已捕获count在1–6范围时，输入clean采用`count × sizeof(command)`；其他输入类别及异常count仍走原整页路径，原`dcache_clean_poc`缓存行取整/顺序语义保持。实际RMM复制位置为`copy_page_input(..., c * sizeof(input_commands[0][0]), ...)`；Kernel/RMM命令结构均24字节，全部字段offset的编译断言通过。未修改固件/IPA列表或GPU数据交接范围。

前置证据在 `build/gpu1200-20261117/`：`c4-bridge-r2`使用同一冻结广范围任务/RPC夹具分别执行原版和候选，均通过；缺失的逐任务页分配失败路径移至实际Group创建失败用例覆盖，未删除错误处理约束。`c4-lifetime-r4`运行实际create/reap/stage/SMC-helper函数，用pthread竞争同一页，验证捕获不被覆盖、隔离/未完成销毁保留、无热路径页分配、输入跨缓存行可见性、全页fallback以及count0/7/极大值边界，并拒绝7个成功编译的错误变体。底层页、cache、RSI和锁行为仍为明确替身，不是实体并发/隔离证明。初轮夹具编译/锚点失败均保留。

`c4-build-r1`固定原配置和编译参数构建通过，内置release与配置SHA核验通过；只替换冻结包Client Image，原接收队列策略、Proxy/Root/RMM/FW/initrd/runner保持。每Group额外4KiB位于原Guest RAM预算内。完整720p run-id为`gpu1200-c4-720-r1-20261117`；保留线预先为1182且需确认，最终1200仍需同条件确认及相关回归。

**构建归因修正。** 上段关于首轮Image仅包含C4的推断已被对象核验否定：恢复文件使用`copy2`保留了较早mtime，Kbuild没有重新编译这些恢复的源文件。源码SHA正确并不证明旧对象已更新。具体证据：Client comm源码已无`system_highpri_wq`，其对象仍引用该符号；Client driver源码已无P15标记，Image仍有`GPU1200_PROFILE`。首轮1132及原全部运行门槛/9SHA确实测得，但它是C4+旧C2RX+P15插桩组合，不能判断纯C4。P16/C2重建Client也残留P15插桩，相关单项归因同样收窄为实际组合；原冻结Image控制及C3不受此问题影响。详见`incremental-object-staleness-evidence.json`。

此为本轮构建验证遗漏，已修正流程：恢复使用新mtime，并在本实验私有cache中删除3个受影响对象，要求build.log明确重编译；随后核对comm对象只引用`system_wq`、Image无旧P15/P16字符串，并反汇编核对原版STAGE含页分配/Group CREATE不含，以及纯C4相反。源SHA、配置/release及冻结输入仍逐项核验。不会把未核对对象的旧成绩当作纯候选结果。当前先交错复测原冻结包，再测试同一新构建条件下的原版与纯C4；尚无新增保留提分。

追加整棵Guest源树checksum比较后，私有构建树仅C4的`drivers/char/realm_gpu.c`内容不同；其余源码与冻结快照一致。恢复的comm与Client driver对象`.text`分别与原已验收对象逐字相同。原冻结包交错控制`gpu1200-control-720-r2-20261117`完整1164，较首轮1170为−6/−0.5128%，原全部运行门槛及9SHA通过；原源码强制重建控制组`gpu1200-rebuild-control-720-r1-20261117`的完成结果为1163，详见下段。构建缓存恢复规则已同步到开发与产物管理手册。

上述强制重建原版控制组已完成1163，较同期原包1164仅−1/−0.0859%，验证了恢复对象后的控制行为。随后纯C4完整720p为1166，对同构建控制+3/+0.25795%，对同期原包+2/+0.17182%，对本轮初始1170为−4/−0.34188%。三轮都保留原33场景、validation26/1/6、重点场景、可信IRQ/Proxy负例、内核健康、FIT及资源恢复和各9份日志SHA。+3未满足预先指定的1182保留线，不新增确认轮或把减少分配/clean操作宣布为有效提分。

统一记录：私有输入页预初始化及typed输入clean｜同构建原版1163→纯C4 1166｜+3/+0.25795%；同期冻结原包1164/初始1170分别作为旁证，不混用对照归因｜固定594MHz、原CPU布局/RAM/配额，唯一功能变化为Client输入存储/clean，原Proxy/RMM/Root/FW/initrd/runner保持；源树、强制对象、符号/反汇编及无旧插桩已核验｜`gpu1200-rebuild-control-720-r1-20261117`、`gpu1200-c4-clean-720-r1-20261117`，外层/负载/UART/Realm退出0，原全部门槛/9SHA，日志及`-audit.json`在本轮目录｜**C4不保留，恢复原冻结包；已验收仍1170，1200未达。**

新增生命周期/cache边界模型`c4-lifetime-r4`在有效count1–6之外验证0/7/极大值仍全页clean并按原合同拒绝，并拒绝第7个“省略count上限”编译错误变体。未据模型操作数宣称应用性能收益。后续优化需要更新较大开销区间的内部profiling，继续保留逐任务授权、当前硬件根/状态、故障历史、真实完成与退休条件；不重试已否决的等待常数或队列优先级。

可审查候选是按已管理Group预分配CPU私有输入页，在原`gpu_lock`覆盖下逐请求重新清零/捕获、逐项验证并完成原同步RMM调用；只在原可信Group销毁/失效条件满足时释放。复用的是输入存储，不是旧token、授权、命令判定或完成证明。错误回复仍保留原真实任务/映射引用规则；Group隔离/销毁失败不能释放其受保护资源或清理他人活动对象。

若进一步研究缩小CPU输入clean范围，必须证明RMM对对应typed operation只读取`count × sizeof(command)`字节，使用已捕获的同一count，覆盖全部实际缓存行并保留barrier；其他IPA列表、FW快照及GPU数据交接保持原合同。前置验证至少覆盖并发staging、未授权/退休Group、错误/部分接纳回复、重复token、重入与失败销毁、页复用及资源记账。未经这些证据及完整720p，不把少分配或少cache操作换算为分数。

统一记录：以当前热点决定下一项安全保持的优化｜已验收1170 → 同期共享对照1170｜0/0%，1200相对1170需增加30分/2.5641%｜相同冻结负载，初始闲置CPU集合差异如上｜`gpu1200-control-720-r1-20261117`，外层与原全部门槛退出0；审计见 `build/gpu1200-20261117/gpu1200-control-720-r1-20261117-audit.json`｜保留同期对照，诊断继续。本轮尚无新增保留提分，未完成1200目标。

当前 PL330 DMA 反例、raw-CSF 跨 Client 可用性和 owner-scoped recovery 的未验证或失败范围继续保留；本轮优化不把这些安全结论升级。


## P17：更新RMM提交与完成内部profiling

P17基于已验收冻结RMM的完整源码，未覆盖工作区的其他安全候选。只在原policy lock内对选定RSI操作每64次取一个外层样本，子区间共享该抽样；计时覆盖DISPATCH、START检查、OBSERVE/STATUS阶段、FINISH、输入捕获、控制页读、映射、cache及IRQ/配置回调。统计按CPU选择活动作用域，其他CPU的回调不计入当前调用；计数溢出后标记并拒绝分析。参数、回调顺序、硬件操作、故障历史、完成及引用条件保持。

三个修改文件可反向撤销全部包装和标记，逐字节恢复冻结源码。p17-counter-model-r1/r2使用实际计数代码验证stride64、CPU作用域、未知操作/越界kind、溢出及双份输出。RMM在全新目录按原固定flags编译，未复用旧对象；静态dump函数被内联而无独立符号，验证已改为检查导出计数helper、状态存储和已链接的BEGIN/ROW/END字符串，不将内联误作编译失败。新Root布局和FIT核验通过，TF-A/GPUFW/Host内核与Guest四输入保持。

首轮gpu1200-p17-rmm-720-r1-20261117完整1164，与同期原冻结包1164差0，原全部运行门槛及9SHA通过；这只是插桩组合诊断成绩。销毁上下文时输出与RMI内存回收串口日志交错，严格解析未得到完整双份快照，因此计时数据拒绝、不补值、不据此选优化。原日志、p17-analysis-initial.log和p17-r1-data-rejection.json保留。随后gpu1200-p17-r1-rollback-20261117已回退原固件，外层0。

第二版保持原程序流程，将输出移到runner已有的、负载后且VM仍运行时的selector6只读查询。原鉴权和四个返回字段不变，不新增Guest操作码/selector；输出在原内部锁释放后、原policy lock作用域内进行。输出加入行数，每轮双份，首轮至少1024次FINISH、其后至少新增65536次才打印，限制重复查询开销。p17-parser-model-r1拒绝单份缺行、双份同丢一行、计数不一致、溢出及错误抽样总体。输出仅为计时元数据，不含地址、对象ID或输入/输出内容。

第二版p17-source-r3、全新构建p17-rmm-build-r2、p17-firmware-package-r2的反变换、计数模型、固定补丁、布局和FIT通过；gpu1200-p17-r2-deploy-20261117经统一独占入口仅刷SD2，保存真实启动区备份/UART，Host与Realm能力及CPU0–3/pmthor恢复通过。第二版完整720p为1160，原全部运行门槛/9SHA通过，但UART两次header和31条row标签仍不足以构成任一完整双份快照，严格解析拒绝全部计时数据。原始日志及解析失败保留；gpu1200-p17-r2-rollback-20261117已退出0，恢复原FIT与Realm能力1、CPU0–3/pmthor且无VM/loop残留。不得据残缺数据归因开销。

第三版取消物理UART输出，改为原GPU_PRIVATE_IRQ_STATUS操作码73下临时只读计时selector7/8/9–200；原selector0–6、保留字段和实际channel/peer/isolated-service鉴权保持。只返回计数/时间，不含地址、对象ID或业务数据。这是诊断接口，结束后回退，不纳入生产。实际支持代码经ASan/UBSan模型验证192个selector、边界201/极大值、stride/CPU/溢出；解析器拒绝7类缺失、不一致及溢出数据。新鲜固定参数构建p17-rmm-build-r3、布局/FIT/固定补丁核验通过。

第三版冻结runner只在完整计分后、VM退出前读取两次完整192项表，要求总体前后及两份全表完全一致；反向删除追加块逐字恢复原runner，原Client/Proxy/initrd保持。部署gpu1200-p17-r3-deploy-20261117仅SD2，原启动区备份保留；新诊断测量尚未完成，无新增优化成绩。

## P17第三轮终态与P18计时边界修正（2026-11-18）

已核实原进程终止且外层COMPLETED/0，未重启或重复测量。P17第三轮完整720p为1161，相对同期冻结1164为−3/−0.2577%，10份回收文件SHA及原运行、场景、IRQ、健康和资源门槛通过。两份192行表与前后总体完全一致。FINISH外层均值71.483µs，OBSERVE49.313µs；DISPATCH_LIVE外层39.220µs；STAGE11.738µs。OBSERVER_ARM_POLL共26599575次，外层抽样415618次均值0.995µs，控制页reader抽样408752次均值0.611µs。父子重叠和不同总体不相加。

**P17部分阶段名称需要纠正。** 代码核查发现`gpu_p17_part(20)`放在无条件`goto failed`之后、`observed:`之前，成功ACK路径跳过该标记。因此kind21的26.657µs包括ACK等待与队列证据，不能作为“队列检查单独26.657µs”的依据；缺失kind20不是ACK零成本。稳定双份计数仍能支持上述外层、reader和回调区间，但不能修复这个分段放置错误。原表与原解析保留，后续按实际代码边界解释。

已通过`gpu1200-p17-r3-rollback-20261118-005903`恢复冻结FIT `239b9cb5d067fbdba84b4c0bed867a6e48ce5f1c10161653fd86fd3b6fc03f47`、Realm能力1、CPU0–3/pmthor和无VM/loop。

P18在同一已验收RMM源码上将ACK标记放到`observed:`之后，并把现有`read_page`拆为DATA加锁、固定CPU视图查找/临时映射、整页失效与DSB、复制、释放排序/解锁五段。全部新增计时标记可剥除，剥除后与P17原体逐字一致；没有改变生产运行条件、回调顺序、缓存范围或状态机。实际计数支持模型通过，新目录按原flags构建、布局/FIT通过。读数仍通过计分后双份标量表取得，解析器额外要求ACK前后阶段和reader父子采样数分别匹配。

研究依据仍包括Custom的按实际字节处理/复用准备思想、固定AvA提交的同步边界批处理，以及Linux v6.12 ARM64 DMA cache实现。尤其Linux的部分边界行可能执行CIVAC，而当前RMM helper始终IVAC，两者不能直接互换。历史控制页range候选AK459→458、BG620→620已被索引否决；仅凭64行变1行不足以重试。只有当前大量observer读取的实测内部成本支持，才考虑重新评估该范围，不从论文或操作数预测1200。

P18完整720p诊断于2026-11-18 01:16完成。统一记录：修正RMM分段计时｜同期冻结1164 → P18诊断1161｜−3分/−0.2577%｜原594MHz、CPU布局、资源及33场景，RMM计时与计分后采集启用｜`gpu1200-p18-720-20261118-010653`外层退出0，10份文件SHA及运行、场景、IRQ、健康和资源门槛通过，见`build/lab-runs/`对应目录和`build/gpu1200-20261117/p18-analysis.log`｜保留诊断证据，1200分目标结束，已验收仍为1170分。

同总体采样中，7420次FINISH的ACK等待及完整错误扫描均值23.263µs，队列证据检查均值4.647µs。402161次OBSERVER_ARM_POLL控制页读取子样本中，整页失效及DSB均值0.236µs。P18跑后最后一次SD2读回与诊断FIT匹配，尚无后续回退记录。

## 保留1170分版本（2026-11-18）

按用户要求保留实测1170分组合。撤回试做的no-op RPC、DEV_QUERY RTT开机压测及专用统计清理，终止对应离线复验并保留已生成日志。本次复核了冻结快照38份源码、Client/Proxy配置及镜像和三组载荷的13项清单哈希。

统一记录：保留原验收版本｜冻结包1170 → 无新增性能测量｜分差及百分比无新增数据｜沿用验收条件，未部署或重新跑分｜原验收 `gpu-normalize2-720-r1-20261114` 退出0，日志见 `build/lab-runs/gpu-normalize2-720-r1-20261114/`｜保留原版，试做清理撤回。
