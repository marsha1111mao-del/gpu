# Proxy Realm glmark 性能优化记录

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-18。目标：保留 RMM 授权共享内存与可信事件通信，使新方案完整 720p glmark 超过 1000 分，并与旧方案 1058 分比较。

## 测试范围

按用户要求，优化期间每轮只运行完整 glmark；达到理想分数后再执行 API、计算、多 Client 和完整回归。不能把尚未执行的项目标为通过。
每轮保留必要的 renderer、33 场景、validation、提交错误、内核故障、可信 IRQ 与资源恢复检查。分数不能掩盖错误。
固定 null-noop、frame-end finish、1280×720；不删慢场景、不用子集分数代替完整分数。

共享内存仍由 RMM 根据调用 Realm 身份授权，通知仍由 RMM 保存事件状态与注入 IRQ；不退回 Host memfd 授权路径。
当前 RK/OpenCCA 没有真实 GPT/GPC 硬件拒绝证据，软件授权和测试通过不能表述为已证明恶意 Host 下的硬件机密性。

## 变更与分数总表

每次大改都更新下表；分差为本版减去对照版，变化比例以对照版为分母。无有效完整成绩时不填推测收益。
文档的大幅更新须同时交代：改动解决什么问题、对应版本与 run-id、前后完整 glmark 分数、绝对及百分比变化、测试条件差异、是否保留。单次小幅变化标为“未证明稳定收益”；多项一起修改只记录组合效果，失败/未测/撤回均保留。

后续每项重大改动统一附上以下记录，便于直接查看性能得失：

| 记录项 | 必填内容 |
| --- | --- |
| 改动目的 | 修改了什么、解决什么问题 |
| 分数影响 | 对照版本及完整分数 → 本版完整分数；绝对分差及百分比 |
| 可比条件 | 分辨率、完整场景、频率、绑核、诊断开关、固件与镜像差异；说明是否为组合改动 |
| 测试证据 | run-id、实际命令、退出码和日志位置；重复测试时列出各轮分数及范围 |
| 结论 | 保留、撤回或待验证；区分单轮变化与已重复确认的收益 |

未测试或测试失败时，分数影响填“待验证”或“失败，无有效成绩”，不填预估提升。纯文档整理注明“未改运行代码，无新增性能测量”。本次新增记录模板属于纯文档整理，不产生新的分数结果。

| 版本 / 大幅改动 | 对照分数 | 本版分数 | 分差 / 变化 | 可比条件与归因边界 |
| --- | ---: | ---: | --- | --- |
| P1：恢复性能配置、两个独立绑核 Realm | 98 | 196 | +98 / +100.0% | 同 720p 全 33 场景；GPU 频率、CPU 布局、并发 RPC、完成点缓存共同改变，只能归因组合效果 |
| P2：RMM 原子 ACK+ARM | 196 | 197 | +1 / +0.51%；未证明实际性能收益 | 保持 P1 性能配置；额外开启 RPC 计时，仅各一轮，不足以区分小幅波动与改动效果 |
| P3：IRQ 只调度 RX，移除 QUERY 和 IRQ 线程 | 197 | 296 | +99 / +50.25% | 与 P2 相同 runner、RMM、性能配置及 RPC 计时，仅更换两侧内核；各一轮 |
| P4：快照融合与按需等待 | 296 | 318 | +22 / +7.43% | 同内核/RMM，仅开启两个现有参数，按组合解释；各一轮 |
| P5：Proxy 有界主动轮询与通知抑制（已撤回） | 318 | 296 | -22 / -6.92% | 保持 P4 参数和 RMM，改两侧内核并开启 200 µs 活跃窗口；各一轮 |
| P6：补齐代理提交诊断 | 318 | 309 | -9 / -2.83% | 新增分阶段、IRQ 和 Proxy RPC 计时；诊断轮，不是性能优化 |
| P8：tiler heap 缓存所有权 | 309 | 632 | +323 / +104.53% | P6 的 Client、RMM、runner、统计参数不变；只更换 Proxy 内核，不含 P7；各一轮 |
| P9：Client 调用线程短时等待回复 | 632 | 808 | +176 / +27.85% | 保持 P8 缓存所有权、RMM、initrd 和诊断参数；两侧内核新增回复通知提示，Client 窗口 100 µs；另修正原有超时误判 |
| P10：同步对象热路径日志限频 | 808 | 820 | +12 / +1.49%；未证明稳定收益 | 与 P9 同 runner/initrd/RMM/参数，仅两侧各三个日志点改为 pr_info_ratelimited；不含 P7 |
| P11：空闲时内联提交、completion 生命周期 | 820 | 826 | +6 / +0.73%；未证明稳定总分收益 | 仅更换 Proxy 内核；保留 P10 参数与日志限频 |
| P12：仅在准备睡眠时 ARM | 826 | 829 | +3 / +0.36%；未证明稳定总分收益 | 仅替换 Client 内核；Proxy、runner、统计配置与 P11 相同；各一轮 |
| P13：按消息有效范围复制（已撤回） | 829 | 830 | +1 / +0.12%；无有效提分证据 | 保持 P12 其余条件，改两侧复制长度及临时区清零；各一轮，源码已恢复 P12 路径 |
| P14：Proxy 活跃期间合并请求通知（已撤回） | 829 | 826 | -3 / -0.36%；无吞吐收益 | 以 P12 为直接基线，不含 P13；相同 runner/initrd/RMM/诊断配置；各一轮 |
| P15：复用退休私有快照（已撤回） | 829 | 813 | -16 / -1.93%；RPC 减少但未提分 | 直接基于 P12，不含 P13/P14；仅额外启用快照复用，各一轮 |
| P16：批量预分配全新空 syncobj（已撤回） | 829 | 827 | -2 / -0.24%；无提分证据 | 直接基于 P12，不含 P13/P14/P15；只额外启用 batch_creates，各一轮 |
| P17：按读取对象同步固件输出（保留） | 829 | 859 | +30 / +3.62% | 直接基于 P12，仅更换 Proxy 内核；不含 P16，其他输入完全相同；单轮结果 |
| P18：Realm job IRQ 直接排队后续工作（已撤回） | 859 | 849 | -10 / -1.16%；无提分证据 | 直接基于 P17，仅更换 Proxy；无 IRQ 线程，但每 job 的 IRQ 数增多，整体未获益 |
| P19：保留 P17，关闭诊断计时（实际性能基线） | 859 | 864 | +5 / +0.58%；未证明稳定收益 | 两侧内核与 P17 相同，仅关闭 Client/Proxy RPC、提交和 job IRQ 计时；配置对照，不归为代码优化 |
| P20：RMM 驻留对端直接唤醒（已撤回） | 864 | 871 | +7 / +0.81%；未证明稳定收益 | 基于 P19；新增 Root 提示路径大量执行，但控制查询及若干场景退步，不保留新增可信固件复杂度 |
| P21：缩小队列输入与 syncobjs 读回范围（已撤回） | 864 | 865 | +1 / +0.12%；无有效提分证据 | 直接基于 P19，不含 P20；仅更换 Proxy，保留初次全量设备同步、屏障与所有有效队列 |
| P22：仅发布实际写入的 CS 输入（已撤回） | 864 | 856 | -8 / -0.93%；未提分 | 移除 CSG 通知中的全部 CS 扫描；配置/OOM/IRQ ACK/STOP 各自发布，RMM 不变 |
| P23：RMM 确认的私有 NC 固件接口（已撤回） | 864 | 866 | +2 / +0.23%；未证明实质收益 | MCU/group 实际 NC；固件能力查询与私有映射按组合评价，不叠加 P20/P21/P22 |
| P24：TRANSFER 携带精确完成点确认（已撤回） | 864 | 863 | -1 / -0.12%；无提分证据 | 直接基于 P19；完成确认与 CREATE/DESTROY 缓存失效收窄为组合改动；确认请求/记录均为 0，不能评价未命中机制的性能 |
| P25：固件事件 worker 内完成 fence（暂保留） | 864 | 882、881 | +18、+17 / +2.08%、+1.97%；两轮范围 881–882 | 直接基于 P19，仅改 Proxy scheduler；相同冻结镜像重复两轮，缺少同期多轮 P19 对照 |
| P26：Client 本地 binary syncobj 与私有快照引用（已撤回） | P25 复测：881 | 862 | -19 / -2.16%；实际命中但未提分 | 仅修改 Client；Proxy、initrd、runner、RMM 均保持 P25；相对首轮 882 为 -20 / -2.27% |
| P27：Client 回复轮询上限 100→200 µs（候选，待复测） | P25 复测：881 | 902 | +21 / +2.38%；单轮改善 | 保持 P25 两份内核/initrd 及固件，仅修改冻结 runner 一个启动参数；不含 P26 |
| P28：Client 回复轮询上限 200→1000 µs（候选，待复测） | P27：902 | 914 | +12 / +1.33%；单轮改善 | 与 P27 相同内核/RMM，单独测既有参数上限；不含新完成页设计 |
| P29：原生 fence 发布私有快照完成页（未证明稳定收益） | P28：914 | 918 | +4 / +0.44%；命中率仅 1.44% | 延迟 binary 容器、不可变快照及完成页作为组合实验；保持 P28 1000 µs runner、P25 scheduler 和 P19 RMM |
| P30：完成页轮询预算 100→1000 µs（候选，待复测） | P29：918 | 957 | +39 / +4.25%；单轮改善 | 只改 Client 一行预算；其他源码、Proxy/initrd/runner/RMM 均保持 P29；完成页命中率 1.44%→99.58% |
| P31：同 epoch 完整 chain 的较小点完成缓存（已撤回） | P30：957 | 957 | 0 / 0.00%；无提分证据 | 只改 Client 缓存比较，另含后续确认无消费者并删除的F2跟踪；其他源码/二进制/RMM 不变 |
| P32：binary 对象持有 point 快照、导出复用（已撤回，未命中） | P30 保留组合复测：957 | 955 | -2 / -0.21%；两项新路径计数均为 0 | 三个 Guest 文件改变；沿用 RMM、完成页、1000 µs 参数、频率/内存/绑核和完整 33 场景 |
| P33：保留初始 signaled binary 的本地状态，修正新导出 session（已撤回，未命中） | 保留基线：957；P32：955 | 957 | 对基线 0 / 0.00%；对 P32 +2 / +0.21%，未证明收益 | 只更换 Client，含移除无消费者 F2 跟踪；P32 其余三个运行输入和 RMM 不变 |
| P34：独占引用的 private 快照容器复用（未部署即撤回） | P33：957；保留参考957 | 未执行 | 无有效成绩，不预估收益 | 三个 Guest 文件改变；存在导出/导入/等待别名则保持新建；RMM、initrd、runner 和测试条件不变 |
| P35：开启已有 completed_snapshot 参数（不启用） | 保留基线957 | 928 | -29 / -3.03%；未获收益 | 恢复的P30源码重建镜像；只新增一个启动参数，原生成功状态才免建快照 |
| P36：TRANSFER 与不可变导出快照融合（已撤回） | 保留基线957 | 951 | -6 / -0.63%；实际命中但未提分 | 三个Guest文件改变；支持已物化目标，RMM/runner/initrd/固件和配置不变，不含P35参数 |
| P37：Proxy与物理GPU IRQ同CPU（不采用） | 保留基线957 | 944 | -13 / -1.36%；未获收益 | 精确P30源码/同clean镜像；只改Proxy CPU1→CPU0，Client仍CPU2，不含P35/P36 |
| P38：提交回复附带原生timeline精确完成凭据（待评估） | 保留基线957 | 962 | +5 / +0.52%；未证明稳定收益 | 只改四个Guest文件，RMM/initrd/runner/频率/内存/绑核不变，不含P35/P36/P37 |
| P39：完整原生chain的较早点完成证明（保留，两轮） | P38：962；保留参考957 | 1022、1022 | 对P38 +60 / +6.24%；对参考均 +65 / +6.79%；同输入复测总分一致 | 只替换Client；Proxy镜像/runner/initrd/RMM/配置和性能条件与P38逐位相同 |
| P40：复用原生完成回调对象（复用已撤回，仅保留旧接口清理） | P39两轮1022、1022 | 1024 | +2 / +0.20%；未证明稳定且值得增加复杂度的收益 | 仅改Proxy实现及原生接口声明/定义；Client运行镜像逐位沿用P39，RMM/runner/性能配置不变 |
| P41：成功同步日志只保留首次 marker（作为日志清理保留，不宣称提分） | P39两轮1022、1022，不含P40复用 | 1023 | +1 / +0.10%；未证明性能收益 | 五个成功日志点改用内核pr_info_once，错误保留/提升WARN；不改RPC/队列/RMM语义 |
| P42：下一次导出顺带回收已退休私有快照（保留；当前路径验收通过） | P41：1023；P39：1022、1022 | 同镜像1159、1163 | 对P41 +136～140 / +13.29～13.69%；对旧1058 +101～105 / +9.55～9.92% | 四个Guest文件改变；不复用旧快照、不增加原生快照分配；RMM/runner/配置不变；旧方案比较非单变量AB |

当前保留组合为 **P38+P39，两轮相同冻结输入均1022分**，对此前P30参考957均为 **+65 / +6.79%**。
两轮完整33场景、提交正确性、受检内核标记及Host恢复均通过。P38独立962仅作为机制对照，
不把其5分差异单独归为已证明收益。P40完整1024（+2 / +0.20%），复用逻辑因未证明稳定且值得增加复杂度的收益已撤回，只保留无调用者接口清理。
P41日志清理完整1023（+1 / +0.10%），不宣称性能收益；P42批量回收同镜像两轮1159、1163，对P41 +136～140 / +13.29～13.69%，决定保留，不含P40复用。旧普通VM1058仅为不同运行路径下的历史参考；两轮高出101～105 / +9.55～9.92%。当前组合的三Realm通信生命周期、重绑定API和双Client实算均已验收通过，详见末尾汇总；这不等于旧普通VM完整32项或硬件机密性证明。

已超过1000门槛22分；相对旧普通VM1058仍低36分 / 3.40%，继续优化。
旧新环境路径不同，该差距只作目标比较，不归因于单项改动。
P32/P33新路径未命中、P34未执行，相关扩展已撤回；P35参数928不启用、P36融合951已撤回、
P37绑核944不采用。本文后续段落保留各阶段历史条件、失败与未执行证据，不能视为当前仍保留的代码。

## P1：恢复性能配置，建立 Realm 基线

结果：退出码 0，完整 glmark **196 分**，尚未达到目标。33 场景，Mali-G610/Panfrost；validation 为 26 成功、1 已知 framebuffer 例外、6 unknown，意外失败 0，提交错误 0。
两 Realm 的 CSG 超时、FW ping 超时、翻译 fault、WARNING、Oops 均为 0；IRQ `[720036,720774]`，VM 退出 `[0,0]`。
Host 已恢复 CPU 0–1、userspace、请求/实际均 300 MHz；无本轮 VM、挂载或 loop 遗留。
七份原始文件已经回收到 `GPU-SFTP/log/realm-xshm/realm-perf-profile-v1-glmark-20261018/` 并校验远端 SHA-256。

- run-id：`realm-perf-profile-v1-glmark-20261018`。
- 命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-profile-v1-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/profile-v1 --workload glmark --performance --benchmark-only`。
- 使用已测旧 Client/Proxy Image 和 RMM，仅改变 runner：CPU 0–3 在线，Proxy 固定 CPU 1、Client 固定 CPU 2，不启动第三个空闲观察者；启用并发 RPC、完成点缓存。
- GPU 请求 600 MHz，实际观测 594 MHz；测试前为 300 MHz。结束后恢复 CPU 和 governor/频率。
- 两个真实 Realm，共享 256 MiB，经 RMM offer/attach 建立；保留权限检查与有序撤销。
- 冻结 runner SHA-256：`86a1e294fab41c2e156426d1dffbe24b723865802bfe262264d3972750526956`。
- Client Image：`e1896ec9fbc6483d0271cbf62620681383c1e5c569add7bc649cee7624a9ebab`。
- Proxy Image：`7165c2185e9e63612611942eb6ceb5d2fee2098de9f1d4552b562bf51641c025`。
- 控制机启动日志：`build/realm-performance-20261018/profile-v1-glmark.log`；wrapper 证据：`build/lab-runs/realm-perf-profile-v1-glmark-20261018/`。

这些配置同时恢复旧性能 profile，属于组合基线实验；不能由一个分数分别归因于频率、绑核、并发 RPC 或缓存。
相对之前 98 分提高 100%，但仍只有旧普通 VM 1058 分的 18.53%。简单场景仍集中在 240–253 FPS、约 4.0–4.2 ms；配置恢复未消除固定等待。
完成点缓存已生效（31516 次命中），计划执行 79577 次；不能再把本轮低分归于缓存未开启或第三观察者争抢 CPU。

## P2 候选：RMM 原子 ACK+ARM

结果：部署与完整 glmark 均退出码 0；33 场景 **197 分**，相对 P1 为 +1 / +0.51%，没有证明实质性分数改善。
validation 仍为 26/1/6、意外失败 0，提交错误 0；两侧五类受检内核故障均为 0，IRQ `[735779,736669]`，VM 退出 `[0,0]`。
Host 恢复 CPU 0–1、userspace、300 MHz；七份原始文件回收到 `GPU-SFTP/log/realm-xshm/realm-perf-ack-arm-v2-glmark-20261018/` 并校验。
本轮同时开启可选 `--rpc-stats`，记录已有 RPC 分阶段计时；与 P1 比较须注明增加了诊断计时，不能把小幅差异直接归于 ACK+ARM。
原子操作减少调用次数，但当前保留为后续通知链路候选的基础，尚不当作已获性能收益的优化；后续根据累计测量决定是否保留。

- 部署 run-id：`realm-perf-ack-arm-firmware-v2-20261018`，仅 SD storage ID 2 固件，未更换 Host 内核/rootfs；旧启动区备份保留于 `build/firmware-runs/realm-perf-ack-arm-firmware-v2-20261018/`。
- 测试 run-id：`realm-perf-ack-arm-v2-glmark-20261018`。
- 命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-ack-arm-v2-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/ack-arm-v2 --workload glmark --performance --benchmark-only --rpc-stats`。
- Client / Proxy Image：`08d3b30451e5d4830dcdf0f057971f6203aaa05abfbe084cc78340fc90705456` / `65b1c987f81e360888313c959844bfd18a0ecf1650c9ba570d122bf46e715b41`。
- RMM ELF：`c9f382e3666da8674dd370aecc14acf125f013fbbd3293d59f63be59f1f9e9c6`；保持原 BL31 `f2c1e019df09f71c6a4a868cb95d3941d956e1c45a18955e23d3a649e56248d5`。
- runner：`a4ade9e1481222f9b4ed6475f9bde9b7b5bb52a8e59aeedfb79fd7eece5a87d0`；initrd：`b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`。
- 冻结输入与源码：`build/realm-performance-20261018/ack-arm-v2/`；日志：`build/realm-performance-20261018/ack-arm-v2-glmark.log`。

新增 `ACK_ARM=17` 与 capability bit 32，在 RMM 策略锁内将当前 pending 确认并重新置 armed。
Guest 接收端排空队列后，一次调用替代 QUERY、ACK、ARM 三次调用；随后仍进行 acquire 队列重查。
RMM 仍验证调用方身份、通道参与者及生命周期；IRQ 只是通知提示，不能成为访问授权或任务完成依据。
新 Guest 要求固件声明该能力，不保留旧三次调用的运行时回退分支；部署须成套更换内核与固件。

竞态要求：通知发生在重置前，队列重查必须看到待处理数据；通知发生在重置后，由已 armed 的可信事件触发唤醒。
数据先发布、通知后到的情况也由队列重查或后续 IRQ 覆盖。不能只做 ACK+ARM 而删除队列重查。

本地验证命令：`bash scripts/check/check-rmm-xshm-events.sh`，退出码 0。
endpoint/memory/IRQ 策略检查通过，新增 10000 轮通知前后交错及非参与者/非法序列拒绝检查。
日志：`build/realm-performance-20261018/ack-arm-native.log`。这不是硬件性能结果或内存序的形式化证明。

构建异常保留：首轮 Client 缺少 `CONFIG_EXTRA_FIRMWARE_DIR`，首轮 U-Boot 打包错误地使用相对 BL31 路径。
分别在 `ack-arm-client-build.log`、`ack-arm-uboot-build.log` 留痕；修正命令使用明确的固件目录和绝对 BL31 路径，后续结果单独记录。

本轮已去重的 RPC 计时（Guest 启动、renderer/validation 和 benchmark 合计，并发累计耗时不等于独占墙钟时间）：

| 操作 | 次数 | 平均总耗时 µs | 发送 µs | 等回复 µs |
| --- | ---: | ---: | ---: | ---: |
| PLAN_EXEC | 80831 | 892.0 | 29.5 | 861.8 |
| SYNCOBJ_CREATE | 130935 | 472.0 | 19.9 | 451.4 |
| SYNCOBJ_TRANSFER | 171708 | 348.4 | 23.3 | 324.4 |
| SYNCOBJ_TIMELINE_WAIT | 139334 | 275.7 | 26.3 | 248.6 |
| SYNCOBJ_WAIT | 133689 | 255.2 | 14.5 | 240.2 |
| SYNCOBJ_DESTROY | 130935 | 248.3 | 22.2 | 225.4 |

合计 829674 次 RPC，所有统计项 errors/timeouts 为 0。`send` 包含发布及调用通知，`wait` 包含对端处理、IRQ、调度等，不能把它都解释成网络或 GPU 时间。
这表明剩余开销包括大量同步对象操作与提交处理，原子重置通知本身不是主要得分突破。
去重统计保存在 `build/realm-performance-20261018/ack-arm-v2-rpc-stats.json`。

分场景也未显示一致改善：P2 相比 P1，buffer map 为 40→38 FPS（-5.0%），交错 buffer map 为 53→51（-3.77%）；
shadow 为 157→162（+3.18%）。这些是单次整数 FPS 的观测差异，尚不能断言改动造成了稳定回退/收益。
33 场景逐项对照保存在 `build/realm-performance-20261018/scene-comparison.json`，后续版本继续使用同样口径。

## P3 候选：精简 IRQ 接收链路

结果：内核构建、完整 glmark 均退出码 0，**296 分**，相对 P2 为 +99 / +50.25%。以 P2 为对照，不改 RMM 固件和共享内存授权。
33 场景，validation 26/1/6、意外失败 0，提交错误 0；两侧五类受检内核故障为 0，IRQ `[1053068,1098885]`，VM 退出 `[0,0]`。
结束恢复 CPU 0–1、userspace、300 MHz，无本轮 VM/loop 遗留；七份原始文件回收到 `GPU-SFTP/log/realm-xshm/realm-perf-hardirq-v3-glmark-20261018/` 并校验 SHA-256。

- run-id：`realm-perf-hardirq-v3-glmark-20261018`。
- 命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-hardirq-v3-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/hardirq-v3 --workload glmark --performance --benchmark-only --rpc-stats`。
- Client / Proxy：`0bdbc0ded1a7052b4ed3ac592a186dae76cce158dfbaadffb5256c3816a02511` / `efe494e2d66719f1a0e363e5950951324daa831ce731661231782170564d05f8`。
- 冻结输入：`build/realm-performance-20261018/hardirq-v3/`；日志：`build/realm-performance-20261018/hardirq-v3-glmark.log`。

现有 IRQ thread 对每条活跃通道先发 QUERY SMC，再调度 RX work。候选删除该 QUERY 和专用 IRQ thread：
hard IRQ 只遍历最多 8 个已订阅池并调度对应 RX work，不读取请求内容、不睡眠、不发 SMC。
两个实际订阅回调只执行原子计时/`schedule_work`；接口注明 hard IRQ 上下文要求。
接收消息仍由 worker 私有快照、校验序号/类型/长度；排空后执行 RMM ACK+ARM 和 acquire 队列重查。
一个 IRQ 可以提示多个通道重新检查，允许无数据的提示；IRQ 本来就不是消息授权或 GPU 完成凭据。

原 event_lock 继续将回调和 unsubscribe 串行化；移除传输前先取消订阅，再 `cancel_work_sync`，避免回调引用已经释放的设备。
此候选减少调度和跨界次数，同时减少代码；是否带来可用收益，要由完整 glmark 判断。

本轮主计划执行 116286 次（P2 为 80356 次）。IRQ 总数因同一计时时间内处理更多任务而上升，不能单看原始 IRQ 次数认定优化失败；两侧 IRQ 合计/主计划次数约为 P2 的 18.32 与 P3 的 18.51，范围含 validation，不是严格每帧计数。
RPC 平均总耗时对照：SYNCOBJ_DESTROY 248.3→123.0 µs，TIMELINE_WAIT 275.7→130.6 µs，PLAN_EXEC 892.0→752.7 µs；
SYNCOBJ_WAIT 则 255.2→293.0 µs，没有全面变快。仍存在同步查询与 GPU/任务处理成本，不能由这一轮推出已经达到 1000 分。
去重计时：`build/realm-performance-20261018/hardirq-v3-rpc-stats.json`。

## 下一候选：复用已有快照融合与按需等待

结果：退出码 0，完整 glmark **318 分**，相对 P3 为 +22 / +7.43%。独立冻结 runner 保持 P3 的内核/RMM，仅开启现有 `fused_snapshot=1`、`lazy_snapshot_wait=1`。
依据是 P2 大量 SYNCOBJ_CREATE/TRANSFER/WAIT 往返：融合将快照创建与引用捕获交给一次 Proxy 操作；按需等待避免用户只导入后关闭 sync_file 时仍立即启动本地轮询。
GPU 依赖仍由真实 Proxy fence 约束，不能跳过 frame-end finish；源对象 reset/reuse 后仍须保持导出时的不可变快照。
不新增同类实现或三套并存协议，先测现有已实现能力在高延迟 Realm 路径上的效果。

旧普通 VM 实验已有局部场景回退，不能沿用旧组合的总分就认定本轮有收益；也不启用旧实验中极少命中的 completed_snapshot。
这两项一起打开只能统计组合影响，不能分别声称各自贡献。候选放在 `build/realm-performance-20261018/snapshot-v4/`，尚未修改默认性能配置。

run-id：`realm-perf-snapshot-v4-glmark-20261018`；命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-snapshot-v4-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/snapshot-v4 --workload glmark --performance --benchmark-only --rpc-stats`。
runner SHA-256：`c89c0b9a866e5fc16de2b8ee5fa5213729c3e8e520ce21a94477f99e50beaed1`；其他三个冻结文件与 P3 相同。

本轮 33 场景，validation 26/1/6、意外失败 0、提交错误 0；两侧五类受检内核故障均为 0。
IRQ `[921139,958832]`，主计划运行 123932 次，VM 退出 `[0,0]`。Host 恢复 CPU 0–1、userspace、300 MHz，无本轮 VM/loop 遗留。
七份原始文件已回收并验证 SHA-256：`GPU-SFTP/log/realm-xshm/realm-perf-snapshot-v4-glmark-20261018/`；wrapper 记录在 `build/lab-runs/realm-perf-snapshot-v4-glmark-20261018/`。

快照调用 105222 次、lazy discard 105222 次、本地 sync_file 等待/轮询均为 0；共 1054837 次统计 RPC，errors/timeouts 均为 0。
这证明避免了此前无实际消费者的快照等待，仍不意味着所有同步 RPC 都被消除。与 P3 对照：简单场景多提高约 10–13%，buffer subdata 41→40 FPS（-2.44%），另两种 buffer、terrain、refract 不变。
总分提升和局部无改善同时记录；不宣称所有场景受益。逐场景数据在 `build/realm-performance-20261018/scene-comparison.json`。

## P5 通知候选：有界主动轮询与按需可信通知

状态：构建、硬件测试退出码 0，完整 glmark **296 分**，相对 P4 为 -22 / -6.92%。候选实现已从当前源码删除，失败性能证据保留。
Proxy 可在处理请求后短时检查同一已授权队列；活跃接收时将 `used.flags` 的通知抑制提示置位，Client 仍按原协议发布消息，但可以省掉此次 RMM NOTIFY。
此提示只影响唤醒，没有映射、身份、消息可信性或 GPU 完成语义。旧接收端维持 flags=0；旧发送端忽略提示只会多发通知。
仅 Realm 请求方向使用该机制，响应方向仍经原 RMM 可信 IRQ，普通 VM 路径不采用提示。

准备休眠前必须先清提示、执行完整屏障，再在 RMM 中 ACK+ARM，并进行 acquire 队列重查。
发送端发布后也执行完整屏障再看提示，避免双方都错过对方的状态。通知仍需经 RMM 调用者身份校验。
收到消息就重新计算活跃窗口，空队列最多主动检查设定预算（上限 1000 µs），需要调度时退出主动检查；持续请求之间保留调度让出点。
不承诺节电：这是用有限 CPU 检查换延迟，实际 CPU 占用及分数都要测量，当前 idle Realm 本身已存在 busy-idle 问题。

本地顺序交错模型覆盖 20 种发布/看提示与清提示/ARM/重查的交错，退出码 0；故意将清提示移到重查后的负对照出现 2 个丢唤醒反例。
代码/输出在 `build/realm-performance-20261018/poll-race-model.py`、`poll-race-model.log`；该模型仅检查顺序原子交错，不能代替 AArch64 内存序证明和实际运行。

测试 run-id：`realm-perf-poll-v5-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-poll-v5-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/poll-v5 --workload glmark --performance --benchmark-only --rpc-stats`。
冻结输入 `build/realm-performance-20261018/poll-v5/`，保持 P4 快照组合，仅新增两侧通知抑制实现和 Proxy `realm_poll_us=200`。
Client / Proxy SHA-256：`8898baf2d983435f66320a194e2ebbfd92100dd82c5cd5b2ae3de63b2d7bbd6b` / `229e225981c3fbe0eb22d857f6bdd803106875bdb60e7176fa165818ed657b5a`。
runner SHA-256：`19713ecacdde49b44c097a5ea25569310c8b2c35bad92087b5d80423c40a90a9`；initrd 与 P4 相同。

本轮 33 场景，validation 26/1/6、意外失败与提交错误 0，两侧五类受检内核故障均为 0；VM `[0,0]`，Host 恢复 CPU 0–1、userspace、300 MHz。
主计划 114911 次，IRQ `[26912,908679]`；与 P4 相比 Proxy 收到的 IRQ 由 921139 降到 26912（-97.08%），但总分反而下降。
这说明减少 IRQ 本身不保证吞吐改善；活跃轮询可能与提交、GPU IRQ worker 争用单 vCPU，仍需分阶段计时确认，不能当成已证因果。
统计 RPC 997813 次，errors/timeouts 均为 0；通知 sent/suppressed 虽已编入镜像，但工作负载日志筛选未纳入该 marker，最终内核 ring 又发生覆盖，无法给出精确抑制 SMC 次数。
该诊断缺口保留，不将 IRQ 降幅冒充 SMC 降幅。分场景 high-poly 387→334 FPS（-13.70%）、交错 buffer map 53→57（+7.55%）；局部提升未抵消总分下降。
证据：`GPU-SFTP/log/realm-xshm/realm-perf-poll-v5-glmark-20261018/` 七份文件均已校验；wrapper `build/lab-runs/realm-perf-poll-v5-glmark-20261018/`。

按“无收益候选不留在有效代码中”的要求，删除 NO_NOTIFY 提示、200 µs 轮询和对应计数，恢复 P4 通信源文件；仅在 build 下保留实际测试过的 P5 冻结包与失败性能证据。

## 后续诊断：覆盖代理实际使用的提交入口

结果：构建、完整 glmark 退出码 0，**309 分**，相对 P4 为 -9 / -2.83%；新增诊断计时，只各一轮，不能把差值归为稳定回退，不计入性能优化。
发现现有 `panthor.submit_stats` 的提交阶段计时只覆盖原生 ioctl，而 Proxy 使用 `panthor_vmshm_group_submit`。
候选复用同一套统计，覆盖内核提交入口的创建 job、reservation、Realm BO 同步、依赖、入队和清理；增加同步耗时字段。
不改变授权、fence、提交或缓存同步语义，不删除安全检查。需要统计时由既有参数启用，默认关闭。
诊断候选以 P4 为基线，避免带入已回退的 P5；最终冻结包另存 `build/realm-performance-20261018/submit-diag-v6-p4/`，构建日志 `submit-diag-p4-proxy-build.log`。此前基于 P5 的未执行诊断包已删除，不保留两套同类候选。

run-id：`realm-perf-submit-diag-v6-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-submit-diag-v6-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/submit-diag-v6-p4 --workload glmark --performance --benchmark-only --rpc-stats`。
Proxy Image / runner SHA-256：`db8a9bd740669ff9ddcf5b9fdae419e5cba447d43489016383c15c3c7337412e` / `f2a3480c7aa9ed78af1760077236bc1c37ce545ea37b59176a4d5435334ab2cf`；Client/initrd 与 P4 相同。
开启现有 `panthor.submit_stats`、`panthor.job_irq_stats` 和 `panthor_proxy.rpc_stats`，诊断计时本身也可能影响分数，不将本轮当作新的性能优化。

33 场景，validation 26/1/6、意外失败 0、提交错误 0；两侧五类受检内核故障 0，VM `[0,0]`。
主会话注册 76、执行 120314 次，IRQ `[886449,934324]`；Host 恢复 CPU 0–1、userspace、300 MHz；七份原始证据均已回收验证。
目录：`GPU-SFTP/log/realm-xshm/realm-perf-submit-diag-v6-glmark-20261018/`；wrapper `build/lab-runs/realm-perf-submit-diag-v6-glmark-20261018/`。

本轮后端统计覆盖启动、验证、计时的 120646 次提交：平均 **621.163 µs**，其中映射 BO 同步合计 73096693898 ns，即 **605.877 µs/次，占 97.54%**。
GPU `run_job` 平均约 4.98 µs，Proxy PLAN_EXEC handler 平均 664.519 µs。后两者与提交阶段有重叠，不能相加为墙钟耗时。
GPU IRQ raw→thread 平均 30.583 µs，thread 平均 1.796 µs。主要已测瓶颈是提交中的全映射 BO 同步，而非 job 入队函数本身。
去重后端统计：`build/realm-performance-20261018/submit-diag-v6-backend-stats.json`。

## P7 候选：空闲调度器内联提交

状态：源码与内核构建退出码 0，**暂不部署，分数未知**。P6 证明主要成本在缓存同步，因此优先 P8；P7 不进入 P8 当前源码，只在 build 冻结包保留，待缓存瓶颈消除后再判断是否需要测试。
原路径把每次 PLAN_EXEC 交给全局 workqueue，再让接收线程 `wait_event`；无竞争时也有一次交接与唤醒。
候选在同一调度器锁下检查“无队列、无执行者”，持有单一执行者标志，直接复用原计划执行函数；完成后释放所有权并唤醒已排队的 worker。
已有排队者不得被新请求越过，竞争路径保留原会话轮转和队列上限。工作线程与内联路径共用完成/引用释放函数，防止两套提交实现漂移。
会话关闭仍取消排队请求，已接纳的执行持有引用；模块注销仍先注销并等待接收 handler，再清理会话与 worker。
共享内存、通知、身份鉴权、GPU fence 和后端提交校验不变，不改变 GPU 任务实际完成的判定。

互斥边界模型覆盖 70 个状态、6 个终态，两次接纳与一次关闭下无重复完成/遗留请求；移除执行者守卫的负对照检测到重叠执行。
命令 `python3 build/realm-performance-20261018/inline-scheduler-model.py`，rc 0；日志 `inline-scheduler-model.log`。
它只检查简化调度状态，不代替内核并发验证或未来多 Client 回归。本轮按用户要求仍只做完整 glmark 硬件测试。
冻结包 `build/realm-performance-20261018/inline-v7/`；Proxy SHA-256 `7eb04323899322e1ef50521ab7984b7a13aefb21aecb4e2c61609c8330c08eb7`。
Client/initrd/runner 与 P6 相同；构建日志 `inline-proxy-build.log`。若未测得可用收益，将撤回候选而保留测试证据。

## P8 候选：tiler heap 的缓存所有权交接

结果：构建、完整 glmark rc 0，**632 分**，相对 P6 的 309 分为 +323 / +104.53%；保持相同诊断配置，**不包含 P7 内联提交**。
Realm 旧路径在每次提交和 fence 完成时同步所有映射的私有 BO；tiler heap chunk 仅由 CPU 初始化头部后交给 GPU，却也被逐页重复同步。
候选只为此类 kernel chunk 指定内部 `PANTHOR_BO_GPU_ONLY` 角色，创建前即确定该角色，避免通用 VM 同步与头部初始化争用缓存。
头部与链接初始化后，通过现有私有页同步路径对完整 chunk 执行一次 DMA_BIDIRECTIONAL 的 clean/invalidate 到 PoC，再撤销 vmap，才发布到 heap 列表或返回 GPU VA。
内核线性映射仍存在，所有权约束适用于可信驱动的访问路径。后续 `panthor_kernel_bo_vmap` 对已交接对象返回 EACCES；这类对象不再参与每次提交/完成的通用同步。分配失败、同步失败仍销毁对象，不发布地址。

安全和一致性约束：内部角色不是 UAPI 标志；原生和 vmshm BO_CREATE 均只接受 `DRM_PANTHOR_BO_NO_MMAP`，用户不能请求跳过同步。
对象要求 NO_MMAP，绑定 exclusive VM，不能导出为可 mmap 的 dma-buf；只有 heap chunk 一个实际创建者使用该角色，CPU 后续路径仅回收，不读写内容。
普通 BO、heap context、ringbuffer、队列接口、同步对象和固件接口的同步保持原规则。显式 kernel BO 同步不受通用同步跳过规则影响，初始交接仍执行真实缓存维护。
不假设 GPU/CPU 硬件一致，不把 CPU 内存屏障替代缓存维护，不改变 RMM 内存授权/映射、可信 IRQ 或 GPU 页表。
该设计采用 [Linux DMA API 的所有权原则](https://docs.kernel.org/core-api/dma-api-howto.html)：CPU 不再触碰仍由设备使用的区域时，无需在设备操作之间反复交回 CPU；本项目仍需独立验证自定义 Realm 路径。

run-id：`realm-perf-heap-owner-v8-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-heap-owner-v8-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/heap-owner-v8 --workload glmark --performance --benchmark-only --rpc-stats`。
冻结包 `build/realm-performance-20261018/heap-owner-v8/`；Proxy SHA-256 `d1550400deb9ef89747d5988d0df05bd418dca2058f923b192f2c332cc18c01a`，Client/initrd/runner 与 P6 相同。
构建日志：`build/realm-performance-20261018/heap-owner-proxy-build.log`；测试日志 `heap-owner-v8-glmark.log`。

本轮 33 场景，validation 26/1/6、意外失败 0、提交错误 0；两侧五类受检内核故障均为 0，VM `[0,0]`。
主会话注册 76、执行 256583 次，IRQ `[1804073,1877876]`；Host 恢复 CPU 0–1、userspace、300 MHz，无本轮 VM/loop 遗留。
七份原始证据已回收并校验：`GPU-SFTP/log/realm-xshm/realm-perf-heap-owner-v8-glmark-20261018/`；wrapper 同 run-id 位于 `build/lab-runs/`。

| 已测指标 | P6 | P8 | 边界 |
| --- | ---: | ---: | --- |
| 完整 glmark | 309 | 632 | +104.53%，各一轮 |
| 后端提交平均 | 621.163 µs | 20.885 µs | -96.64%，启动/验证/计时合计 |
| 其中 BO 同步平均 | 605.877 µs | 8.075 µs | -98.67%，减少重复同步的直接证据 |
| Client PLAN_EXEC RPC 平均 | 776.610 µs | 148.456 µs | 含传输、对端调度和处理 |
| Client SYNCOBJ_TRANSFER RPC 平均 | 302.609 µs | 124.820 µs | 控制往返仍有明显固定开销 |
| Client SYNCOBJ_CREATE RPC 平均 | 222.735 µs | 125.625 µs | 未消除该 RPC |

统计 RPC 2070051 次，errors/timeouts 均为 0；与 P6 总数不能直接作每帧开销比较，因为相同计时时间内任务数翻倍。
33 场景 FPS 全部提高；最小为 buffer map 41→43（+4.88%），terrain 9→26（+188.89%）、blur 51→146（+186.27%）。
后端与 RPC 去重计时在 `build/realm-performance-20261018/realm-perf-heap-owner-v8-glmark-20261018-{backend,rpc}-stats.json`；逐项场景对照在 `scene-comparison.json`。
仍未超过 1000，下一步以约 100–150 µs 的控制 RPC 往返为测量对象，不把本轮翻倍视作目标完成。

## P9 候选：由 Client 调用线程等待短回复

结果：Client/Proxy 构建与完整 glmark rc 0，未见编译 warning/error；**808 分**，相对 P8 632 分为 +176 / +27.85%，各一轮。保留 P8 的 heap 所有权改动，不含 P7。
P5 让 Proxy 接收 worker 忙等，减少 IRQ 却降低吞吐。本候选让已经等待 RPC 的 Client 调用线程在发送成功后短时检查回复，默认关闭，测试窗口 100 µs，上限 1000 µs；遇 need_resched、完成或期限立即退出。
仅一个调用者通过 trylock 持有回复队列 NO_NOTIFY 提示；其他调用者保留原等待路径，IRQ worker 和调用线程复用同一回复解析函数、队列锁与 waiter 锁。
匹配仍检查 seq/type，长度仍受限，等待者删除与完成在同一锁下；超时不允许晚回复写入已退出的栈。

Proxy 先发布回复，再执行完整屏障后读取提示；Client 退出窗口先清提示、完整屏障、RMM ACK_ARM，再 acquire 重查队列，最后才允许睡眠。
提示只抑制该窗口的回复通知，不授予内存权限，不替代实际回复或 GPU fence。请求通知始终走 RMM；窗口外回复也仍走 RMM，RMM 身份/lease 授权及事件逻辑未改。
通道引用跨 RPC 持有，quiesce 在仍有使用者时拒绝注销。提示仅在发送成功后设置，所有设置后的退出路径恢复通知。预期减少调度/通知开销，是否收益必须以实测判断；不宣称节能。

代码核对同时修正原有超时误判：在 waiters_lock 下先判断 waiter 是否已被回复方取走，再移除尚未完成的 waiter；原顺序先移除再判断会把超时误当成功。
这项修正随 P9 镜像一起测试，因此本轮不能分离其单项影响。20 种顺序交错模型 rc 0，错误清提示顺序的负对照检测到 2 个丢唤醒；仅证明简化顺序模型，不能替代 AArch64 内存序证明。

run-id：`realm-perf-caller-poll-v9-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-caller-poll-v9-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/caller-poll-v9 --workload glmark --performance --benchmark-only --rpc-stats`。
冻结包 `build/realm-performance-20261018/caller-poll-v9/`，测试期间不修改。
Client / Proxy SHA-256：`909443ed9a44b2d03670973a2c26065aa20f69de727a23356ecd3d616724a789` / `0fbb85d4847964829168d2076a42efb225a02eea5d8e1e7d7ca2786d20f673ff`。
runner SHA-256：`ee00244e2e489e907e1e1e1bc2a085c29f47929a52f64dc039bae32c2b09d222`；initrd 与 P8 相同。
构建日志 `caller-poll-{client,proxy}-build.log`，模型 `caller-poll-race-model.log`，测试日志 `caller-poll-v9-glmark.log`，均在 `build/realm-performance-20261018/`。
新增退出时计数 `[REALM_RESPONSE_POLL_STATS]` 与 `[REALM_RESPONSE_NOTIFY_STATS]` 均已完整捕获；benchmark helper 先解绑，随后主流程读取 kernel-log，故不需要重复增加解绑后日志采集代码。
Client attempts 2607682、completed_before_sleep 2406252（92.28%）；完成于睡眠前可能包含 IRQ worker 帮助，不等价于纯轮询命中。
Proxy sent 220398、suppressed 2409795，共 2630193 次回复中 91.62% 未调用回复 NOTIFY。请求通知始终保留。通知计数表示调用/跳过次数，不单独证明注入次数或性能因果。

本轮 33 场景、validation 26/1/6、意外失败 0、提交错误 0；两侧五类受检内核故障均为 0，VM `[0,0]`。
主计划注册 76、执行 326079 次；IRQ `[2572940,186596]`。Host 恢复 CPU 0–1、userspace、300 MHz；wrapper 完成 rc 0，七份原始证据 SHA-256 校验通过。
证据：`GPU-SFTP/log/realm-xshm/realm-perf-caller-poll-v9-glmark-20261018/`；wrapper 同 run-id 位于 `build/lab-runs/`。
统计 RPC 2630193 次，errors/timeouts 0；33 场景 FPS 均提高。最小 buffer subdata 43→45（+4.65%），bump normals 808→1160（+43.56%）。

| RPC 平均耗时 | P8 | P9 | 说明 |
| --- | ---: | ---: | --- |
| PLAN_EXEC | 148.456 µs | 93.251 µs | -37.19% |
| SYNCOBJ_CREATE | 125.625 µs | 62.822 µs | -49.99% |
| SYNCOBJ_TRANSFER | 124.820 µs | 69.091 µs | -44.65% |
| SYNCOBJ_DESTROY | 123.492 µs | 84.368 µs | -31.68% |
| SYNCOBJ_TIMELINE_WAIT | 104.178 µs | 57.549 µs | -44.76% |
| SYNCOBJ_SNAPSHOT | 111.433 µs | 57.425 µs | -48.47% |
| SYNCOBJ_WAIT | 146.648 µs | 212.016 µs | +44.57%，含真实 GPU 完成等待，不能按此单项推断吞吐回退 |

后端提交 18.427 µs，其中 BO 同步平均 7.215 µs。均包含启动/验证/计时，不等同每帧墙钟；同计时时间任务数增加，RPC 总数不能直接作每帧比较。
精确源差异：`build/realm-performance-20261018/P9-vs-P8.patch`；去重 RPC/后端/通知计数和逐场景差异均在同目录 JSON 中。尚未超过 1000，继续优化。

## P10 候选：同步对象热路径日志限频

结果：两侧构建与完整 glmark rc 0、未见编译 warning/error；**820 分**，相对 P9 808 分为 +12 / +1.49%。各一轮且场景有升有降，未证明稳定性能收益；保留限频减少日志刷屏的作用，不将它列为已证的主要吞吐优化。
P9 启动/验证/计时合计处理 2630193 个 RPC，Client/Proxy 的同步对象创建、成功销毁和转移仍逐次写 printk；即使 console 不打印 INFO，格式化和内核日志写入仍会执行，且可能覆盖故障前上下文。
只将两侧各三个现有日志点改为 `pr_info_ratelimited`，保留最初与间隔内的诊断样本、既有错误告警和汇总统计，不新增模式开关，不改 RPC、缓存、身份授权、IRQ 或 GPU 完成语义。
Proxy 单独的销毁失败日志不改；原功能测试所查的生命周期 marker 格式仍保留，但尚未重跑 API 矩阵，不能声称该矩阵通过。
不包含 P7，不修改 100 µs 窗口；runner/initrd 与 P9 完全相同，避免把通信参数变化混入本轮。

run-id：`realm-perf-ratelimit-v10-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-ratelimit-v10-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/ratelimit-v10 --workload glmark --performance --benchmark-only --rpc-stats`。
冻结包 `build/realm-performance-20261018/ratelimit-v10/`；Client / Proxy SHA-256：`854a06e4af68daf0397e69462724e2c9b1524dcff6d1060dc13bcd7e1e7487fc` / `e685cc50c82584bf9282f1aad3b6189cc78c125d94a166447b45574593aa2805`。
runner 仍为 `ee00244e2e489e907e1e1e1bc2a085c29f47929a52f64dc039bae32c2b09d222`。构建日志 `ratelimit-{client,proxy}-build.log`、测试日志 `ratelimit-v10-glmark.log` 均在 `build/realm-performance-20261018/`。

本轮 33 场景、validation 26/1/6、意外失败与提交错误 0，两侧五类受检内核故障均为 0，VM `[0,0]`。
主计划注册 76、执行 330415 次，IRQ `[2613833,243582]`；Host 恢复 CPU 0–1、userspace、300 MHz，无活动 VM 或 loop 遗留。
统计 RPC 2676041 次、errors/timeouts 0；后端提交平均 18.260 µs、BO 同步平均 7.281 µs。
Client CREATE 平均 62.822→55.090 µs，TRANSFER 69.091→56.963 µs，DESTROY 84.368→78.310 µs；含实际 GPU 完成的 SYNCOBJ_WAIT 则为 212.016→280.007 µs，不能将这些重叠时间相加为总开销。
Proxy 回复 NOTIFY sent 290256 / suppressed 2385785；Client 轮询 attempts 2652479 / completed_before_sleep 2386916。Client IRQ 比 P9 更多，不能从日志限频直接推导通知减少。
场景样例：shadow 519→564（+8.67%），conditionals vertex-steps=5 则 1120→1078（-3.75%），不声称所有场景提高。
七份证据已校验：`GPU-SFTP/log/realm-xshm/realm-perf-ratelimit-v10-glmark-20261018/`；wrapper 同 run-id 位于 `build/lab-runs/`。

## P11 本地候选：空闲调度器内联提交与完成生命周期

结果：Proxy 构建和完整 glmark rc 0、未见编译 warning/error，**826 分**，相对 P10 820 为 +6 / +0.73%；各一轮，未证明稳定总分收益。将 P7 的调度改动移植到 P8/P9/P10 代码上，不使用缺少这些优化的旧 P7 Image。
空闲时，在同一调度锁下取得单执行者标志，直接在原接收线程执行计划；有执行者或排队请求时仍排队，保留会话轮转、深度上限、关闭检查和引用持有。
内联结束恢复执行权，并为期间入队的请求重新安排 worker；worker 在内联执行期间不得同时取得执行权。

同时将原栈上 submit 的 waitqueue/done 布尔组合换成内核 completion；执行、取消都先写结果和释放执行引用，再 complete，唤醒后不再访问该请求。
这修正原实现中“发布 done 后、wake_up 尚未结束时，调用者已观察 done 并返回”的潜在栈生命周期竞态。等待不使用超时/可中断退出，排队请求不会提前销毁。
模型 `inline-scheduler-model.py` 覆盖 70 个状态、6 个终态；移除单执行者守卫的负对照检测到重叠。它检查简化调度状态，不替代 completion 内核语义、多 Client 或关闭并发硬件验证。
保持 RMM 共享内存与 IRQ、session owner 校验、计划代际、GPU fence、BO 所有权和后端提交校验。性能影响待 P10 完成后独立测量；如无收益，撤回内联候选，保留必要的生命周期修复及失败证据。
构建日志 `build/realm-performance-20261018/inline-v11-proxy-build.log`，模型输出 `inline-v11-scheduler-model.log`。
run-id：`realm-perf-inline-v11-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-inline-v11-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/inline-v11 --workload glmark --performance --benchmark-only --rpc-stats`。
冻结包 `build/realm-performance-20261018/inline-v11/`，只更换 Proxy Image，SHA-256 `4aa1111783730603c2c22fd611b97262e8b14002f7adadd876ce55f3ed051548`；Client/initrd/runner 与 P10 相同。精确源差异 `P11-vs-P10.patch`。
completion 选择遵循 [Linux completion 生命周期说明](https://docs.kernel.org/scheduler/completion.html)，并核对本树 `include/linux/completion.h` 与 `kernel/sched/completion.c`；调度模型不声称覆盖全部内核生命周期。

P11 的 Client PLAN_EXEC 平均 92.540→79.253 µs（-14.36%），Proxy handler 平均 34.831→22.351 µs（-35.83%）；后端提交平均 18.260→18.367 µs 基本相同。这支持交接开销已降低，尚不证明总分稳定提高，因此暂作后续组合的对照，不把 +0.73% 当作确定吞吐收益。
33 场景、validation 26/1/6、意外失败/提交错误 0，两侧五类受检内核故障均为 0，VM `[0,0]`。
主计划注册 76、执行 333215 次，IRQ `[2627248,248067]`；Host 恢复 CPU 0–1、userspace、300 MHz，无活动 VM 或 loop 遗留。
RPC 2688730 次，errors/timeouts 0；Proxy 回复 NOTIFY sent 295757 / suppressed 2392973，Client attempts 2667007 / completed_before_sleep 2397340。
场景有升有降：build use-vbo=false 820→840（+2.44%），shadow 564→542（-3.90%）。
七份证据已校验：`GPU-SFTP/log/realm-xshm/realm-perf-inline-v11-glmark-20261018/`；wrapper 同 run-id 位于 `build/lab-runs/`。

## P12：仅在准备睡眠时调用 RMM ARM

结果：Client 构建、模型、完整 glmark 均 rc 0，未见编译 warning/error。**826→829 分，+3 / +0.36%**；各一轮，未证明稳定总分收益。与 P11 使用同一套 Proxy、runner 和诊断配置。
33 场景完成，validation 为 26 成功、1 已知 framebuffer 例外、6 unknown，意外失败和提交错误均 0；五类内核故障标记均 0，两 VM 退出 `[0,0]`。RPC 2707681 次，errors/timeouts 均 0；可信 IRQ `[2641384,243688]`。Host 恢复 CPU 0–1、300 MHz，七份原始证据已回收并校验 SHA-256。
调用者轮询 2691724 次、睡前已完成 2410173 次、睡前 ARM 282495 次；后者不含 IRQ worker ARM，不是 SMC 总数。Proxy 回复通知 sent 297443 / suppressed 2410238。后端提交均值 17.965 µs，BO 同步 7.093 µs；分场景有升有降，不能把减少调用等同于稳定提分。
源码还表明：触发对端唤醒的 NOTIFY 会经 RMM 退出到 Host，由 KVM kick 对端；ACK_ARM 则直接返回 Realm。因而“减少 ARM 未显著提分”与两类调用路径成本不同相符，但未做单次 SMC 计时，不能量化归因。
P9/P10 每次调用者结束轮询，无论是否已经收到自己的回复，都执行一次 RMM ACK_ARM。候选保留清 NO_NOTIFY、完整屏障和 acquire 队列重查；只有自己的 waiter 仍未完成、确实准备睡眠时，才调用 RMM ARM，并再次 acquire 重查。
未取得 poll_lock 的并发调用者也必须独立经过 ARM/重查后再睡眠；不能把别人的完成当成本次完成。IRQ worker 的重新使能逻辑不变。默认 realm_poll_us=0 时仍走原 IRQ 路径。
如果自己已完成，则本次 RPC 已不需要后续唤醒；如有其他睡眠中的调用者，它们各自已执行 ARM/重查，轮询线程也仍会通过原队列与 waiter 锁分发它们的回复。
本改动不取消 RMM 通信：请求仍始终通知，窗口外回复仍通知，睡眠等待仍由 RMM 可信事件唤醒；不修改共享区身份、lease 或映射权限。

简化顺序模型 `lazy-arm-v12-model.py` 覆盖 112 种交错；错误地因“其他 waiter 完成”而跳过 ARM 的负对照产生 4 个丢唤醒反例。
模型仅覆盖顺序原子交错，依赖屏障在硬件建立发布/提示顺序，以及 IRQ worker 最终获得调度，不替代 AArch64 内存序或内核活性证明。
新增 `arms_before_sleep` 计数只记录调用者的睡前 ARM，不包含 IRQ worker 的 ARM，不能据此直接推算所有 SMC 总数。

run-id：`realm-perf-lazy-arm-v12-glmark-20261018`。
命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-lazy-arm-v12-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/lazy-arm-v12 --workload glmark --performance --benchmark-only --rpc-stats`。
冻结包 `build/realm-performance-20261018/lazy-arm-v12/`；Client SHA-256 `b4263f50ca143ebdb2c114b2dac51e9856b4dd7e8f5e71e252959ab2de816429`。
Proxy/initrd/runner 与 P11 相同。精确差异 `P12-vs-P11.patch`，构建日志 `lazy-arm-v12-client-build.log`、模型输出 `lazy-arm-v12-model.log` 均在同级 build 目录。

## P13 已撤回：按消息有效范围复制私有快照

结果：两侧构建、边界模型、完整 glmark 均 rc 0。**829→830 分，+1 / +0.12%**；各一轮，场景有升有降，未见有效提分证据，故撤回可变长度复制与取消清零的源码改动，恢复 P12 固定槽复制路径。P14 单独基于 P12，不继承 P13。
33 场景，validation 26 成功 / 1 已知 framebuffer 例外 / 6 unknown；意外 validation 和提交错误 0，五类内核故障标记均 0，两 VM 退出 `[0,0]`。RPC 2708652 次、errors/timeouts 0；可信 IRQ `[2637631,256408]`。后端提交均值 18.240 µs、BO 同步 7.159 µs。Host 恢复 CPU 0–1、300 MHz；七份原始文件已回收到 `GPU-SFTP/log/realm-xshm/realm-perf-bounded-v13-glmark-20261018/` 并校验 SHA-256。
run-id：`realm-perf-bounded-v13-glmark-20261018`。命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-bounded-v13-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/bounded-v13 --workload glmark --performance --benchmark-only --rpc-stats`。
现有消息槽固定 512 字节；两侧接收端每次均从共享区复制全部 512 字节，而常见控制消息只占其中一小段。
候选继续先复制描述符到私有栈，校验固定槽偏移、capacity 与 40≤msg_len≤512；只以这个已校验的私有 desc.msg_len 作为 memcpy 长度，随后仍检查私有消息头的 payload 长度与描述符完全一致。
不从共享消息头读取长度来决定共享区复制范围，不重新读取共享描述符；处理函数只接收已完整复制并校验的私有 payload。队列 geometry 仍在 attach 时验证为固定 512 字节并保存在私有内存。
两侧还取消了临时 payload 未使用部分的预清零；只有 recv 成功并初始化 rx.len 个字节后，才会调用 handler 或向匹配的 waiter 复制这些字节。失败与空队列路径不读取临时 payload。
发送端仍清零完整槽，不改变线格式、尾部初始化、授权、IRQ、序号匹配、fence、错误码或所有权；这组改动按组合测量，不分离归因。

现有线格式 sizeof(msg)=40、payload offset=36，保持不变。长度模型检查 266256 对描述符/消息长度，覆盖 473 个合法 payload 长度，以及 2^31/UINT32_MAX 等非法输入；所有成功解析所读范围均在已复制前缀内。
故意用未经校验的消息头长度确定 memcpy 大小的负对照违反槽边界。模型只检查长度覆盖和整数边界，不能代替实际 C 解析器执行、恶意并发修改测试或硬件回归。
冻结包 `build/realm-performance-20261018/bounded-v13/`；Client / Proxy SHA-256：`e8d961517930ef416e62ded5e2d3785f56feeac6f559f59ce1df6851f08483c1` / `435aff7f8c8a4e8441534cb3eba1f22b99352fc71ffd2554e929024df3b41a45`。
initrd/runner 与 P12 相同。精确差异 `P13-vs-P12.patch`，构建日志 `bounded-v13-{client,proxy}-build.log`、模型 `bounded-v13-length-model.py/.log` 均在同级 build 目录。无有效收益时撤回候选并保留证据。

## P14 已撤回：仅在 Proxy 正在处理请求时合并通知

结果：两侧构建、顺序模型、完整 glmark 均 rc 0；**829→826 分，-3 / -0.36%**，各一轮，无吞吐收益，候选源码已撤回。直接对照 P12，不含 P13。
33 场景，validation 26 成功 / 1 已知 framebuffer 例外 / 6 unknown，意外失败和提交错误均 0，五类内核故障标记 0，两 VM 退出 `[0,0]`。RPC 2691548 次、errors/timeouts 均 0，可信 IRQ `[2624479,253162]`。Host 恢复 CPU 0–1、300 MHz，无 VM 或 loop 遗留；七份原始证据已回收并校验 SHA-256。
请求通知 sent 2628681 / suppressed 62867，仅抑制 **2.34%**；回复 sent 304939 / suppressed 2386609。后端提交均值 18.598 µs、BO 同步 7.376 µs。接收端活跃窗口实际重叠有限，减少的通知量较小，未体现为总分收益；不保留额外提示和屏障逻辑。
run-id：`realm-perf-request-hint-v14-glmark-20261018`。命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-request-hint-v14-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/request-hint-v14-p12 --workload glmark --performance --benchmark-only --rpc-stats`。
Client 发布请求后，经完整屏障读取 C2P 队列的通知提示；Proxy 只有成功取得私有请求快照后才设置 NO_NOTIFY，表示当前 RX worker 执行完 handler 后保证继续排空请求。
队列空、无 handler、关闭或其他错误时，均先清提示并执行完整屏障，再进入原有 RMM ARM / acquire 队列重查。每个 channel 只有一个 RX work；撤销先停通知并等待 worker，再释放映射。
不增加空闲主动轮询，也不让 Proxy 占用额外 CPU 时间等待新请求，区别于已撤回的 P5。旧 peer 不使用该提示时仍发送原有通知；非 Realm 路径保持原状。
通知提示只是调度优化，不参与共享授权、session 身份或 payload 校验；睡眠唤醒仍经过 RMM 可信事件。一个 Client 只能影响自己的 channel。
新增 `REALM_REQUEST_NOTIFY_STATS` 记录实际发送和抑制次数；20 种顺序交错的原通知重启模型适用于反方向队列，错误重启顺序的负对照仍能暴露丢唤醒。该模型不是弱内存或内核活性证明。
冻结包 `build/realm-performance-20261018/request-hint-v14-p12/`，Client / Proxy SHA-256：`f802d00b2df9f9812ad8a9f5dc8372fc75331f9fc307e2c00c3c6f694137ea27` / `e3e59d12cc5589af61041c5529bbb7dbec742f5d0f6457cc1c50322ba39cb25d`，initrd/runner 与 P12 相同。
独立差异 `build/realm-performance-20261018/P14-vs-P12.patch`；核对完整 tracked diff 后，P12→P14 仅两侧 comm 文件变化。构建日志 `request-hint-v14-p12-{client,proxy}-build.log`，模型 `request-hint-v14-model.log`。最初基于 P13 的本地冻结包从未部署，已移除其冗余大镜像，保留 WITHDRAWN、源码、补丁和哈希；实际运行只使用重新基于 P12 的包。无有效收益时撤回有效代码并保留证据。

## P15 已撤回：复用已退休的私有快照

结果：两侧构建、生命周期模型和完整 glmark 均 rc 0；**829→813 分，-16 / -1.93%**，各一轮。虽然减少了 RPC，但未体现为吞吐收益，故撤回私有快照复用、池、对应 feature/消息和关闭清理的有效源码。P16 重新基于 P12，不叠加本候选。
33 场景，validation 26 成功 / 1 已知 framebuffer 例外 / 6 unknown，意外 validation 和提交错误均 0，五类内核故障标记 0，两 VM 退出 `[0,0]`；RPC 2386884 次、errors/timeouts 0，可信 IRQ `[2378458,322569]`。七份原始证据已回收并校验 SHA-256。
快照池日志显示 268565 命中、1 次未命中、268566 退休、0 溢出、关闭时剩 1 个；未见快照销毁失败或 SESSION_RELEASE 的 syncobj 遗留。每次 PLAN_EXEC 对应的 RPC 从 8.086 降为 7.262，但 WAIT 平均时间 **295.244→377.609 µs**，增加约 82.4 µs；后端提交仍为 18.305 µs、BO 同步 7.152 µs。此结果支持“部分控制工作原本与 GPU 执行重叠”的解释，不能把 RPC 数减少直接换算成端到端收益；并未证明分数下降的唯一原因。RMM、initrd、频率、绑核和计时开关不变；冻结 runner 仅新增 `panthor_client.reuse_snapshots=1`。
run-id：`realm-perf-recycle-v15-glmark-20261018`。命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-recycle-v15-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/recycle-v15 --workload glmark --performance --benchmark-only --rpc-stats`。

P12 每个同步文件 export 使用不可变私有 snapshot，最后无人使用后又异步发送 DESTROY。新候选保留不可变性，但将已退休句柄放入每个 DRM file/session 的固定 8 槽池：只有 dma_fence 的 release 路径可以入池，意味着 dup fd、import 或等待 worker 的引用均已释放。仍有引用的快照不复用；已经启动的等待 worker 仍使用原等待、销毁、错误传播路径。
下一次 export 从同 session 池中取出句柄，用单次 SNAPSHOT_REUSE RPC 将其 fence 替换成当前源 fence 的独立引用。它仍需一次 export RPC，不省略捕获 fence 的语义，也不拿可变公开 syncobj 直接充当 sync_file。

- 通过 OPEN_SESSION 新 feature 协商和 `panthor_client.reuse_snapshots=1` 启用，且必须使用已协商的 fused snapshot。未开启、旧 peer 或池满都沿用原有路径，不修改用户态 ioctl ABI。
- Proxy 依据 RMM channel 身份查找 session，并验证源、目标非零且不同、目标是同 session 内的 private_snapshot；在 session 锁内执行 DRM 二进制 transfer。目标的“已无本地引用”由可信 Client 驱动的 release 路径保证，不声称 Proxy 能从消息独立证明这一点。
- 本地 release 可以处于原子上下文，因此只做带 irqsave 的池锁操作；不做 RPC 或分配。导出 fence 已持有的 DRM file 引用保证 driver_priv 存活；池本身不额外持有 file 引用，避免关闭环。
- 池固定最多 8 个额外私有对象，计入既有 session 对象限额；溢出继续异步销毁。postclose 显式销毁池中剩余句柄，再 CLOSE_SESSION；若 destroy 失败则记录，最终 session 释放仍负责回收。
- RPC 失败或返回非法句柄时不把该句柄重新放回池，避免重试歧义。仍保留原 RPC 超时、session 生命周期及共享内存授权，不改变 RMM 通知的可信性边界。

新增 `SNAPSHOT_POOL_STATS` 统计命中、未命中、退休、溢出和关闭时缓存数；需与新 SNAPSHOT_REUSE、旧 SNAPSHOT/DESTROY 的 RPC 次数和完整分数一起判断，而不是把缓存命中当作吞吐提升。
生命周期顺序模型覆盖 81 种 dup/worker/import 捕获/关闭/下一次 export 交错，提前在首次 fd 关闭时复用的负对照有 46 个反例；另检查 8 槽上限和 session 命名空间。模型不执行实际 C，不验证弱内存、恶意并发或真实 GPU fence；硬件结果仍待测。
依据本地 `drm_syncobj_transfer_to_binary()`：在目标对象中替换的是源 fence 的引用；已经复制到其他对象的 fence 引用不会随目标对象后续复用而改变。仅在最后一份导出 fence 引用消失后复用，是本候选必须保持的边界。

冻结包 `build/realm-performance-20261018/recycle-v15/`，Client / Proxy SHA-256：`c56392037d2dd5087c74a954bea56561cc418a95e6d8c231aefa6e6337707fba` / `5de2a08409e001528233f3c34c7f8b2c82823d980da7bf715bbd42dd1ff6c95e`；runner `ab70bf77d859208e310f958e27e364b5e1a03bf1e0751372434091a0d9c073ff`。P12→P15 完整 tracked diff 仅四个文件：Client/Proxy 驱动、协议头和 Client 通信层新增操作名；独立差异 `P15-vs-P12.patch`。源码、完整 patch、hashes、构建日志 `recycle-v15-{client,proxy}-build.log` 和模型 `recycle-v15-lifecycle-model.py/.log` 保留在同级 build 目录。

## P16 已撤回：批量申请全新的空 syncobj

结果：完整 33 场景 **827 分**，相对 P12 829 分为 **−2 / −0.24%**，没有提分证据，候选有效代码已撤回。wrapper 与两 VM 退出码均为 0；validation 26 成功、1 已知 framebuffer 例外、6 unknown，提交错误 0，五类受检内核故障均为 0。可信 IRQ 为 `[2383321,277384]`；Host 已恢复 CPU 0–1、300 MHz。七份原始证据已回收并校验 SHA-256：`GPU-SFTP/log/realm-xshm/realm-perf-create-batch-v16-glmark-20261018/`；wrapper 证据在同 run-id 的 `build/lab-runs/`。

RPC 共 2454396 次，errors/timeouts 均为 0；CREATE_BATCH 34166 次，普通 CREATE 72 次。主渲染 session 的缓存命中 239089 次、补货 34156 次、关闭时未用 3 个。尽管减少了创建往返，SYNCOBJ_WAIT 平均时间由 295.244 升至 354.702 µs；后端提交 18.510 µs、BO 同步 7.247 µs。不能把 RPC 数下降等同吞吐提升，也不能把 WAIT 增长认定为分数变化的唯一原因。P16 的性能参数、诊断开关、RMM 与 initrd 均保持 P12，仅额外启用 batch_creates；不含 P13/P14/P15。
run-id：`realm-perf-create-batch-v16-glmark-20261018`。命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-create-batch-v16-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/create-batch-v16-p12 --workload glmark --performance --benchmark-only --rpc-stats`。候选不改变 RMM、共享内存授权、可信事件或 GPU fence 完成条件。

P12 创建普通 syncobj 274214 次、销毁 548287 次；已撤回的 P15 针对私有 snapshot 的退休；P16 独立针对普通 CREATE 的往返。Mesa 25.0.7 `pan_fence.c` 中，渲染 fence 导出后会创建新的空 syncobj 并导入 sync_file，最后通过 drmSyncobjWait 等待；这为新空对象的批量预分配提供了代码依据，不代表本地二进制每次调用顺序均已逐事件追踪。

开启 `panthor_client.batch_creates=1` 且 OPEN_SESSION 协商支持后，首次无标志 CREATE 一次请求最多 8 个全新空对象，返回其中一个，其余最多 7 个在同 DRM session 的未用池中。后续无标志 CREATE 直接取未用对象；有标志的 CREATE 和公开对象的销毁仍走原 API。这里缓存的是尚未使用的新对象，**不复用旧公开对象**，无需改变已有执行计划的销毁失效规则。

- 使用单独的 create_pool mutex 串行补货，不在 file lock 或 snapshot spinlock 内执行 RPC；不影响其他线程取得 file lock。
- Proxy 校验 channel 的 Realm 身份、session、count=1..8 与保留字段。允许部分成功，至少分配一个才返回成功；零分配保留原错误。申请的对象计入原有每 session 4096 限额。
- Client 私有校验批次数量、非零句柄及批内唯一性后才缓存；每个公开对象仍执行原有本地分配、引用计数、xa_insert、销毁和计划失效路径。不修改用户态 ioctl ABI。
- 有标志 CREATE 遇到容量/内存错误时，在 create_pool mutex 内取出并销毁未用新对象后最多重试一次，避免预分配缓存无端占用可释放配额；没有退休 snapshot 池。
- postclose 显式销毁未使用的预分配对象，再关闭 session。新增 CREATE_POOL_STATS 记录缓存命中、补货和未用数；原 RPC 和关闭错误仍记录。

顺序语义模型检查 24057 组 create/signaled-create/destroy 序列、81 个部分配额/分配失败组合、8 槽上限、缓存配额清理和关闭回收。该模型不执行 C，不验证真实并发、AArch64 内存序或故障注入；完整 glmark 已执行；更广泛语义测试尚未执行。
本地备份 `pre-create-batch-v16/`，最终独立差异 `P16-vs-P12.patch`，构建日志 `create-batch-v16-p12-{client,proxy}-build.log`、模型 `create-batch-v16-model.py/.log` 均在 `build/realm-performance-20261018/`。
源代码依据：[Mesa 25.0.7 pan_fence.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/src/gallium/drivers/panfrost/pan_fence.c)、[同版本 panthor_kmod.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-25.0.7/src/panfrost/lib/kmod/panthor_kmod.c)。已下载固定版本副本到本地 build 参考目录，未修改部署用户态或更新上游 latest。

冻结包 `build/realm-performance-20261018/create-batch-v16-p12/`，Client / Proxy SHA-256：`dcd0f1591b4ff7a5d3f75d1813d305f4830982bd944393cfe592df82ef89acf5` / `c4dad65913e93eca95fb32b6fc418437a880e4f78416260360a0fff41f3eaa14`；runner `0aa35cc00539a02bb1c66a4fbe5a25acc44a52eb1df0e07b86e9d97320ab25a1`，initrd 与 P12 相同。完整 tracked diff 核对为四个文件，冻结源码与 patch 同目录；runner 仅增加 `panthor_client.batch_creates=1`，其余频率、绑核、统计参数保持 P12。

## P17 保留：按事件实际读取的固件输出同步

结果：完整 33 场景 **859 分**，相对 P12 829 分提高 **30 分 / 3.62%**，保留。相同 Client、runner、RMM、initrd 与计时参数，只更换 Proxy 内核，不含已撤回 P16；仍为单轮测量，未证明长期稳定性。wrapper 与两 VM 退出码均为 0；validation 26/1/6，提交错误及五类受检内核故障均为 0；可信 IRQ `[2748664,221301]`。Host 已恢复 CPU 0–1、300 MHz，无本轮 VM 或 loop 残留。七份原始证据回收并核验：`GPU-SFTP/log/realm-xshm/realm-perf-output-range-v17-glmark-20261018/`；wrapper 同 run-id 位于 `build/lab-runs/`。

RPC 2807651 次，errors/timeouts 均为 0；后端提交平均 18.322 µs、BO 同步 7.339 µs，不能把本轮收益归为提交函数本身变快。33 场景均未低于 P12：31 项提高、2 项持平，最高 desktop blur +10.0%。这与减少异步固件事件的同步成本相符，但未单独计时该路径，不能量化每次缓存维护节省。独立改动为 `panthor_sched.c`，备份及差异分别为 `build/realm-performance-20261018/pre-output-range-v17-panthor_sched.c` 与 `P17-vs-P16.patch`。P16 未改此文件，因此该差异也适用于 P12。

run-id：`realm-perf-output-range-v17-glmark-20261018`；命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-output-range-v17-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/output-range-v17-p12 --workload glmark --performance --benchmark-only --rpc-stats`。冻结 Proxy Image SHA-256：`3721af21b1bb28517f009f7c9340b541678e16c3c3acac256b29e4d2b4d50159`，其余输入与 P12 完全相同。恢复 P12 源文件后已强制刷新依赖时间并实际重编 Proxy 驱动，确认产物不含已撤回的 batch_creates/reuse_snapshots 参数；构建日志 `output-range-v17-p12-proxy-build.log`。完整源码与 patch、四项哈希在上述冻结包内。

代码路径显示，原有单个 CSG 中断及队列状态读取会同步全局、所有 CSG 和 CS 的输出；此前提交统计不覆盖这一异步固件事件工作。候选将中断读取限定为当前 CSG 输出和实际报告事件的 CS 输出；队列状态额外同步其独立输出页。优先级读取的是 CPU 所有的输入字段，不再触发全树输出同步。

ACK 轮询只刷新 ACK 所在缓存行，因此在 CSG 更新完成边界仍显式刷新当前 CSG 的完整输出，供状态/空闲判断读取。继续使用现有范围校验、缓存行对齐、DMA_FROM_DEVICE 和屏障，不假设 CPU/GPU 一致性；诊断及停机路径保留完整同步。RMM 授权、可信中断、fence 完成规则、锁和用户 ABI 不变。构建通过及代码读取覆盖核对不能代替硬件正确性与完整 glmark 测量。

## P18 已撤回：移除 Realm job IRQ 的一次线程切换

结果：完整 33 场景 **849 分**，相对 P17 859 分为 **−10 / −1.16%**，没有提分证据；四个文件的有效代码已恢复到 P17，并核对完整 tracked patch 与冻结 P17 完全相同。仅更换 Proxy，Client/runner/initrd/RMM/频率/绑核/诊断开关保持相同。wrapper 与两 VM 退出码均为 0；validation 26/1/6，提交错误与五类受检内核故障均为 0；可信 IRQ `[2716910,244853]`。Host 已恢复 CPU 0–1、300 MHz，无本轮 VM/loop 残留。七份原始证据已回收并校验 SHA-256：`GPU-SFTP/log/realm-xshm/realm-perf-direct-job-v18-glmark-20261018/`。

RPC 2780142 次，errors/timeouts 均为 0；job IRQ 直接处理 888123 次，IRQ 线程样本为 0；raw 平均处理 1.485 µs。但每个后端 job 对应的 IRQ 从 P17 的 2.121 增至 2.575（约 +21.4%），支持中断合并/时序发生变化的解释，不能认定为唯一退分原因。后端提交 18.265 µs、BO 同步 7.158 µs。减少一次线程切换没有换来总分提升，因此不保留。P12 的 job IRQ 原始入口至线程平均延迟为 28.317 µs，线程处理本身平均 1.929 µs；这些是诊断测量，不能直接换算成最终分数。

在 Realm 中，job IRQ 回调只唤醒固件等待者、确认 global idle 事件并排队已有的调度工作，因此候选直接在硬中断执行该回调，保留 fault/OOM/CSG 状态处理的原 workqueue 和锁。每次只读并清除一批当前启用的状态，处理后返回；新事件通过仍启用的电平中断继续触发，不在硬中断内无限轮询。非 Realm job IRQ 以及 GPU/MMU IRQ 继续原线程路径。

该回调会更新固件 req，因此两个 req 修改宏统一采用 spin_lock_irqsave/irqrestore；已核对这些接口锁的获取仅在这两个宏中，防止硬中断打断同 CPU 的持锁者后死锁。ACK 输出同步、输入发布使用预先分配的映射与已有非睡眠缓存操作；回调不获取 sched mutex，不新增分配或 RMM SMC。原 suspend/mask/synchronize_irq 和解除暂停流程不变。诊断增加 raw_handled，与 raw_none、raw_wake_thread 分开；没有线程样本时的 raw_to_thread=0 代表未采样，不能表述为实测延迟为零。

该拆分遵循 [Linux generic IRQ 文档](https://docs.kernel.org/core-api/genericirq.html) 的顶半部、线程和电平中断职责；本项目是否正确仍须检查自身设备状态、锁与实测，不能仅凭引用成立。

run-id：`realm-perf-direct-job-v18-glmark-20261018`；命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-direct-job-v18-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/direct-job-v18 --workload glmark --performance --benchmark-only --rpc-stats`。冻结 Proxy SHA-256：`848e62d08404c4e7e29e35cccc35be686bedbbce5fed3782dd3d50940302e2ac`；其余三项冻结输入与 P17/P12 相同，完整 patch、源码和 hashes 位于该冻结目录。

备份 `build/realm-performance-20261018/pre-direct-job-v18/`，独立差异 `P18-vs-P17.patch`，涉及 `panthor_device.h`、`panthor_fw.h`、`panthor_fw.c`、`panthor_drv.c`。构建与代码调用路径核对不替代硬件验证；不能从候选减少线程切换的意图预填收益。RMM 授权、Realm 间可信事件、共享内存生命周期与 fence 完成判定不变。

## P19 完成：关闭诊断，建立实际性能口径

直接保留 P17 的两个内核和 initrd，采用已补齐相同性能参数的规范 runner，只省去 `--rpc-stats`；因此关闭 Client/Proxy RPC、后端提交和 job IRQ 的诊断计时。**完整 33 场景 864 分，相对 P17 859 分为 +5 / +0.58%，单轮未证明稳定收益**。这不是代码优化，不能把差异归因于 RMM 或 GPU 算法；旧普通 VM 1058 分同样关闭这些计时，但 Host/Realm 路径等差异依然存在。

run-id：`realm-perf-no-diag-v19-glmark-20261018`；命令：`python3 scripts/maintenance/lab-run.py --run-id realm-perf-no-diag-v19-glmark-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/realm-performance-20261018/production-v19-p17 --workload glmark --performance --benchmark-only`。冻结包中 Client/Proxy/initrd SHA-256 与 P17 完全相同，runner 为 `548f837d72596459a0e09b4ed55933558028db232f886a4051353c03b6a8ac47`。逐行核对 runner 差异只涉及帮助文本、参数字符串换行和诊断启用条件。未采集的 RPC 计数写 NOT_CAPTURED，不能把缺失日志统计为零错误。

## 可复现性能配置

规范 runner `GPU-SFTP/tests/realm-xshm/run-realms.py` 的 `--performance` 已补齐实际保留 P12 所用的 Client 100 µs 回复轮询、fused/lazy snapshot 参数，避免后续直接使用规范入口却漏掉已测配置。`--rpc-stats` 显式开启两侧 RPC、后端提交及 GPU IRQ 计时；仅 `--performance` 不开启这些计时。该流程更新不改变正在运行的冻结包，**没有独立分数，不声称提分**；本轮 864 分已测，须注明与 P6–P17 诊断开启轮的条件差异。P16 的 batch_creates 无提分证据，已撤回，不进入规范配置。

## 参考依据

- [Virtio split ring 规范](https://github.com/oasis-tcs/virtio-spec/blob/master/split-ring.tex)：发布、通知抑制及重新使能后的队列重查。借鉴竞态处理，不据此宣称本实现已经获得同等验证。
- [CAEC](https://arxiv.org/html/2512.01594v5)：受保护的 Realm 间共享内存；授权建立与高频数据交换应分离，其实验数据不能直接套用于本项目。
- [Telekine](https://www.usenix.org/system/files/nsdi20-paper-hunt.pdf)：保持依赖关系的命令批处理和 GPU 执行流设计。后续是否引入异步完成队列，须根据本项目测量决定。

性能下降的原始证据见 [原因分析](PROXY_REALM_PERFORMANCE_CAUSE_ANALYSIS_20261018.md)；既有功能与失败历史见 [实现记录](PROXY_TASK_SERVICE_IMPLEMENTATION_20261017.md)。


P19 wrapper 和两个 VM 的退出码均为 0；validation 为 26 成功、1 已知 framebuffer 例外、6 unknown；提交错误与五类受检内核故障均为 0，可信 IRQ `[2769758,216634]`。Host 恢复 CPU 0–1、300 MHz，无本轮 VM/loop 残留。RPC 计时关闭，统计缺失记为 `NOT_CAPTURED`，不能据此宣称 RPC 错误或延迟为零。7 份原始证据已回收、逐文件核对远端 SHA-256，位置 `GPU-SFTP/log/realm-xshm/realm-perf-no-diag-v19-glmark-20261018/`；wrapper 证据 `build/lab-runs/realm-perf-no-diag-v19-glmark-20261018/`。

实际命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-no-diag-v19-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/production-v19-p17 \
  --workload glmark --performance --benchmark-only
```

## P20 完成并撤回：RMM 跟踪实际驻留 REC，经 Root 提示对端物理核

状态：完整 glmark **864 → 871，+7 / +0.81%**，正确性检查通过；未证明稳定总分收益，**新增的 13 个文件改动已恢复为前版，原固件恢复退出 0**。下述设计保留作实验记录，不是当前有效实现。保持 P19 的 GPU 路径与性能设置，只针对通知必须退出 Host 的额外成本；本候选涉及 RMM、Root 固件和诊断接口，按组合评价。

RMM 在 REC0 进入/退出时，在现有事件策略锁下记录实际硬件 MPIDR。仅当经过通道权限检查的 NOTIFY 需要唤醒、且对端 REC0 仍驻留时，调用 Root 的受限服务发送固定 SGI0；发送端无需为这次提示退出 Host。对端没有驻留、Root 拒绝或不可用时沿用原 Host 唤醒路径；CLOSE 保留原路径。SGI 仅是物理唤醒提示，不能选择或伪造 Realm IRQ，IRQ127 的 pending、所有者校验与 LR 注入仍在 RMM。共享内存映射授权不变。

通知发布与退出到休眠在同一策略锁下排序：发布先发生时，退出侧若观察到私有 pending，便将已完成的 WFx/PSCI CPU_SUSPEND 退出转为普通 IRQ 退出，避免 Host 再睡下；退出先发生时，发送侧看见非驻留，改走原 Host 路径。pending 不被此检查消耗，仍在下一次 REC entry 注入。CPU_OFF 不强制恢复为 runnable。

这是固定 OpenCCA/RK Linux GICv3 环境的候选：SGI0 必须与当前 Host 的 reschedule IPI 对齐，不作为通用 CCA 接口或硬件机密性证明。Root 拒绝 Normal/Secure 调用、额外参数、自核目标及非法 affinity；真实物理 affinity 由 RMM 采样，Realm 不可提供目标 CPU 或中断号。新增受调用者身份限制的 `wake-stats`，分别记录发送侧直接提示/Host 回退次数，以及接收侧 idle 退出被 pending 阻止的次数；不在热路径加入打印或时间戳。

本地实际 C 实现的 ASan/UBSan 策略测试已通过，覆盖通知与休眠两个排序、非 idle 退出、迁移、非法 owner、IRQ 未绑定、注销后的身份/状态清理及统计 ABI。日志 `build/realm-performance-20261018/resident-wake-v20-policy-tests.log`；这不能替代固件构建和硬件 glmark 验证。改动前源码备份位于 `build/realm-performance-20261018/pre-resident-wake-v20/`。


P20 实现参考与区别：PORTAL §4.4 以命令队列及 RMM 通知服务 System Realm，§6.6 讨论世界切换成本和专核轮询；这里只借鉴“授权与通知由可信层协作”的思路，不声称论文实现了本候选的 Root 物理核提示。[PORTAL 原文](https://gts3.org/assets/papers/2025/sang:portal.pdf)。Devlore 的 delegate-but-check 强调可信软件核验中断，不能把 Host 唤醒提示当成虚拟中断授权；本候选仍将这两者分开。[Devlore v3](https://arxiv.org/abs/2408.05835v3)。物理 SGI0 的选择依据固定 Host 的 `irq-gic-v3.c:gic_smp_init`、`smp.c:IPI_RESCHEDULE` 及实机 `/proc/interrupts`，检查日志 `resident-wake-v20-host-irq-before.log`。

P20 本地构建：两侧 Guest Image 均退出 0，无编译 warning；RMM/TF-A/U-Boot 组合构建与布局检查退出 0。RMM 链接仍有原有 RWX LOAD 段和丢弃 build-id 警告，不能写成全构建无警告，尚未为此改变链接脚本。最终构建日志 `resident-wake-v20-firmware-freeze-build.log`；两侧内核日志 `resident-wake-v20-{client,proxy}-build.log`。有限 idle 模型穷举 6 个排序，带检查时无模型内丢唤醒，去掉检查的负控制发现 2 个反例；它不覆盖真实 GIC、抢占或硬件时序。对应 `resident-wake-v20-idle-model.py/.log`。

冻结 Guest 包 `build/realm-performance-20261018/resident-wake-v20/`：Client `e155a789d471369107ad123e83464b1bfcfaab2d71b3bb6bd61d5bc055af1466`，Proxy `b9667880aba97f46abcb864191e74ec5b7812a07d924d2aa088c7d60d70d423c`，initrd `4ca4790d7198ba4a4272a24d6fa7eabe92c888216fceaa601ca91ee559854d83`，runner `c18742b582dfdcde52bf0b646d76e0dda11c9fdb65b9f881d02af760001b7700`。initrd 逐条比较仅替换 `realm-xshm` CLI，其余条目与 P19 完全相同；完整差异、源码与 manifest 同目录保留。固件包 `resident-wake-v20-firmware/`：RMM ELF `8ad7369ec7c7e48238a1b34e5401a05f7c761339edc9641527b981860861dc56`，BL31 `f13482be3b4e9229c18fac9a5e0d3747d62e38cdbb9c5527f9d57d7ccce0588e`，ITB `f134b7f90b437f469d0ccfca7b27159e54ddce124967322afc1cab91cc8c5b9d`。

部署 run-id `realm-perf-resident-wake-v20-firmware-20261018`，使用 `lab-run.py --allow-rk-reboot` 包装 `deploy-rmm-firmware.py`，仅 storage ID 2；实际 SD 启动区备份 SHA-256 `38f014f673ba87a464e614c5168c747b3276eec2738189ef764268d86be61b2d`，位于同 run-id 的 `build/firmware-runs/`。固件恢复和后续 glmark 成绩须分别记录，刷写成功本身不代表性能通过。


P20 固件部署与 wrapper 均退出 0，Host 恢复原 `6.12.0-opencca-pmthor-opp3 #7`、CPU 0–1。glmark run-id `realm-perf-resident-wake-v20-glmark-20261018` 已完成；测量前非法通道通知拒绝、重复通知合并和 IRQ127 所有者检查通过，`wake-stats` 已出现直接提示计数。仅证明新路径被执行，不代表完整测试通过或性能提升。重启后的首轮 rootfs 全文件校验需要从 SD 冷读，属于启动成本，不计入场景 FPS。

P20 glmark 实际启动命令（已完成，退出码 0）：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-resident-wake-v20-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/resident-wake-v20 \
  --workload glmark --performance --benchmark-only
```

`wake_stats.workload_delta` 的起点在分配/绑定通信池之前，故包含建立传输后的自检及 glmark，不能称为纯计分场景内计数。本次已确认直接提示大量实际发生；只有预检中的 1 次直接提示不能证明性能路径收益。


P20 最终证据：完整 33 场景 871 分，validation 26/1/6，提交错误及五类受检内核故障均为零，可信 IRQ `[2885627,310970]`；wrapper 和两 VM 退出码均为 0，Host 恢复 CPU 0–1、300 MHz，无本轮 VM/loop 残留。7 份原始文件回收并核验远端 SHA-256，位于 `GPU-SFTP/log/realm-xshm/realm-perf-resident-wake-v20-glmark-20261018/`。直接提示增量 Proxy/Client 分别为 306942 / 2824000，Host 回退 4060 / 61627，直接路径约占需唤醒通知的 97.94%；两侧 pending-idle 退出修正均为 0，故不能说本轮硬件覆盖了该竞态，只有本地策略与有限模型证据。

总分收益很小且分场景有退步：mipmap 1309→1233（−5.81%）、height bump 1319→1264（−4.17%）、VBO build 1324→1279（−3.40%）；terrain 38→41、部分 conditionals/loop 提升。timeline WAIT 实际调用从 409855 增至 525229，cache epoch miss 从 43320 增至 153358；完成于 Client 短时轮询的比例从约 91.3% 降至 87.1%。这些说明新路径改变了控制流与完成时序，不能将省掉 sender Host 退出直接换算成提分，也不能认定某个计数是变化的唯一原因。RPC 计时关闭，不能补写延迟数据。

P20 取舍：不以单轮 +0.81% 为增加 Root 专用 SGI ABI、REC 驻留状态与新的休眠握手提供性能依据，撤回该实验。原有 RMM 授权共享内存和可信 pending/LR 注入均保留。回退固件使用原 `ack-arm-firmware/`，run-id `realm-perf-resident-wake-v20-rollback-20261018`；实际恢复及 wrapper 均退出 0，Host 恢复原 #7 内核、CPU 0–1，回退前实际 SD 启动区备份 SHA-256 `93f68b95295a39022b7d235e91a33badd580496350b7c2dc55b32510ef43aefe`。前版实际源码恢复后运行原 C 策略测试通过，日志 `withdrawn-v20-policy-tests.log`；TF-A tracked diff 已恢复为空。


## P21 完成并撤回：缩小队列输入与同步对象的缓存维护范围

状态：计分已结束，**864 → 865，+1 / +0.12%**，无有效提分证据，两项范围调整已撤回；wrapper 与两 VM 均退出 0，资源恢复与日志核验已完成。不含已撤回 P20。此候选只改 `panthor_sched.c`，没有新增参数、协议或备用实现。

队列输入仅有 INSERT/EXTRACT 两个 64-bit 字段，当前每次发布清理整个 4 KiB 输入页；改为覆盖完整输入对象并按 `dma_get_cache_alignment()` 向上取整。GPU 输出页仍独立处理，分配时全 BO 初始化/首次发布不变。运行时每个 group 的 fence 状态读取同样只刷新 `queue_count × sizeof(struct panthor_syncobj_64b)` 覆盖的完整缓存行；此结构实际为 **16 字节**，名称中的 64b 指 seqno 位宽，不能误解为 64 字节。

保留初次和终止路径的全 syncobjs 设备同步：创建时 `queue_count` 尚未递增，不能直接以它缩短初始化范围。此次只缩短运行时读回范围，保留原 DMA_FROM_DEVICE、DMA_TO_DEVICE、屏障、错误处理和全部有效队列。分配、存活期和 RMM 内存授权不变，未假设硬件缓存一致性。

恢复 P19 基础后的 Proxy 构建退出 0，无编译 warning，日志 `build/realm-performance-20261018/control-range-v21-p19-proxy-build.log`；独立源码差异、Proxy 镜像与基于 P19 的冻结输入位于 `control-range-v21-p19/`，前版 `panthor_sched.c` 保存在 `pre-control-range-v21-panthor_sched.c`。完整 glmark 测量结果及撤回结论见本节末。

P20/P21 的事件保护范围仍是 Realm 通道通知。这里没有实现 Devlore 的完整设备中断保护，不能据此宣称 Mali 物理中断、GPU DMA 或恶意 Host 下的硬件机密性已得到同等保障。


P21 已重新冻结为 `control-range-v21-p19/`：Client / initrd / runner 与 P19 逐字节相同；新 Proxy SHA-256 `ea21ca1953f2efb2e27e1403f0c8f6d6ac901a172d23cb7b2ec7f3d4b5dca538`。完整 tracked patch 与 P19 比较仅 `panthor_sched.c` 不同，恢复的 13 个 P20 文件逐个与备份比较一致，检查清单 `baseline-check.json`。两侧恢复后构建退出 0，日志 `control-range-v21-p19-{client,proxy}-build.log`。未执行的 P20 基础 P21 镜像副本已移除，只保留源码、差异、原 manifest 和 `superseded.json`，不能用它启动测试或引用成绩。


P21 在 P20 固件回退完成、证据收齐后启动，现已完成，以下命令退出码 0、完整 33 场景 865 分：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-control-range-v21-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/control-range-v21-p19 \
  --workload glmark --performance --benchmark-only
```


P21 最终结果：完整 33 场景 **864 → 865，+1 / +0.12%**，无有效提分证据，已撤回两项范围调整。validation 为 26 Success / 1 已知 Failure / 6 Unknown，意外失败 0；提交错误和五类受检内核故障为零；IRQ127 两侧增量 `[2771999,226260]`；wrapper、两 VM 退出码均为 0。Host 恢复 CPU 0–1、300 MHz，无本轮 VM/loop 遗留。7 份原始证据已回收并核验远端 SHA-256，位于 `GPU-SFTP/log/realm-xshm/realm-perf-control-range-v21-glmark-20261018/`，外层记录 `build/lab-runs/realm-perf-control-range-v21-glmark-20261018/`。RPC 诊断未启用，记 NOT_CAPTURED。场景变化约 -2.17% 至 +1.14%，不能把 +1 分当稳定收益。

## P22 完成并撤回：按实际 CS 写入发布固件输入

状态：完整 33 场景 **864 → 856，-8 / -0.93%**，未提分，源码已撤回；wrapper、两 VM 均退出 0，日志已核验。仅测试 CS 发布调整，不含 P20/P21。下文保留实验设计与证据，不是当前有效实现。

审计发现 `panthor_fw_ring_csg_doorbells()` 会对每个目标 CSG 清理全部 `stream_num` 个 CS 输入，再发布 CSG/global 输入。纯 CSG 同步完成、idle 等事件也承担全部 CS 的清理与逐项检查，而大部分 CS 本次没有写入。候选移除这个全量扫描，将发布责任放到实际写入路径：初始化/调度的队列配置及 OOM 恢复继续通过原 `panthor_fw_toggle_cs_doorbells()` 清理对应 CS；CS IRQ 处理显式清理该 CS（包括不切换 CS doorbell 的 fatal-only ACK）；STOP/reset 写入也显式清理。CSG 和 global 的同步、子→父顺序、设备屏障及初始全量交接保持。未增加 feature flag、固件 ABI、RMM/Root 路径或备用实现。

这里借鉴的是 [Linux DMA 文档](https://docs.kernel.org/core-api/dma-api-howto.html) 的 CPU/设备所有权交接及缓存线约束，并非假设屏障可以代替非一致缓存维护。[PORTAL](https://gts3.org/assets/papers/2025/sang:portal.pdf) 的 RMM 通信设计继续保留，不能把该论文直接当作这项驱动修改的性能证明。也未把私有固件页放入 Client 共享池，未将 Realm 页转换为 Host 共享页。当前 OpenCCA 缺少真实 GPT/GPC 强制保护的边界不变。

原 P21 暂存基础备份：`build/realm-performance-20261018/pre-cs-input-v22/`；P19 调度器基线为 `pre-control-range-v21-panthor_sched.c`。首次增量差异 `P22-cs-input.patch`，构建日志 `cs-input-v22-proxy-build.log`。最终镜像哈希、run-id、完整结果与撤回结论见本节末。


P22 首次暂存位置（已被 P19 基础版本替代，未部署）：`build/realm-performance-20261018/cs-input-v22-p21/`；暂存 Proxy SHA-256 `a71cc710968b822ddd807eaa4cedebb81f8d987a2ca78efcc90770ce7efd9183`。当时仅冻结候选 Proxy 和三文件源码、增量及全量 tracked diff；该 Proxy 后来已删除，源码与差异保留作历史记录。构建日志确有 `panthor_fw.o`、`panthor_sched.o` 重编译，没有 `warning:` / `error:`；不能据此替代 GPU 正确性和性能结果。

CS 输入发布调用审计（非性能测量）：

| 写入路径 | 发布位置 | 去掉父级全量扫描后仍覆盖的内容 |
| --- | --- | --- |
| `cs_slot_prog_locked()` → `csg_slot_prog_locked()` | 原有 `panthor_fw_toggle_cs_doorbells(queue_mask)` | 已配置的每个有效队列、ringbuf 地址、状态与 IRQ mask |
| `group_process_tiler_oom()` | 原有 `panthor_fw_toggle_cs_doorbells(BIT(cs_id))` | 新 heap 地址及 OOM ACK |
| `cs_slot_process_irq_locked()` | 新增该 CS 的显式发布 | fatal/fault ACK，包括不会切换 CS doorbell 的 fatal-only 路径 |
| `cs_slot_reset_locked()` | 新增该 CS 的显式发布 | STOP 状态；不依赖以后某次无关事件清理 |
| `panthor_fw_ring_csg_doorbells()` | 保留目标 CSG 输入，再 global 输入及 MMIO doorbell | 父级 ACK、CS IRQ ACK、doorbell 请求及既有屏障 |

以上 CS 配置/复位/事件写入由 scheduler mutex 串行；配置和 OOM 的目标 CS 发布仍发生在父 doorbell 可见之前。初始 section/队列 BO 全量同步未缩减。该审计说明候选的必要发布责任，不声称单次完整 glmark 会覆盖所有 fatal/reset 竞争。

P21 计分后决定撤回两项范围调整，P22 已恢复完整队列输入页及完整 syncobjs 读回范围，当时仅保留独立 CS 发布候选（现已撤回）。重新构建日志 `cs-input-v22-p19-proxy-build.log`。此前基于 P21 的 P22 暂存从未部署，不可引用其哈希作为后续实测组合；实际冻结记录见下文。




P22 最终冻结：`build/realm-performance-20261018/cs-input-v22-p19/`。Client、initrd、runner 均与 P19 逐字节相同，新 Proxy SHA-256 `26a543dee240d6fca8a40f1d1843cb19adfb5a7e0af8a67f1fc190d5811d7b50`。`baseline-check.json` 确认相对 P19 全量 tracked diff 仅三个驱动文件不同，含独立差异 `P22-cs-input.patch`；无 P20/P21 组合。恢复 P19 后构建退出 0，日志 `cs-input-v22-p19-proxy-build.log`。从未部署的 P21 基础暂存 Proxy 已删除，保留源码/差异和 `superseded.json` 的路径、大小、时间与哈希记录。

P22 实际运行命令（完整 33 场景 856 分，退出 0）：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-cs-input-v22-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/cs-input-v22-p19 \
  --workload glmark --performance --benchmark-only
```


P22 最终结果：完整 33 场景 **864 → 856，-8 / -0.93%**，不保留。validation 26/1/6，无新增失败；提交错误和五类受检内核故障为零；IRQ127 两侧增量 `[2736617,227543]`；wrapper、两 VM 退出码均为 0，Host 恢复 CPU 0–1、300 MHz，无本轮 VM/loop 遗留。7 份原始文件已回收并核验远端 SHA-256，位于 `GPU-SFTP/log/realm-xshm/realm-perf-cs-input-v22-glmark-20261018/`；外层证据 `build/lab-runs/realm-perf-cs-input-v22-glmark-20261018/`。RPC timing/counters 未启用，记 NOT_CAPTURED。shadow 604→571（-5.46%）、terrain 38→41（+7.89%），总分没有提升；不能把减少同步次数当收益。P22 已从当前源码撤回，P23 仅保留独立私有 NC 改动。

## P23：RMM 确认属性的私有 NC 固件接口（866 分，撤回）

状态：完整 33 场景和 wrapper 均退出 0，**864 → 866，+2 / +0.23%**，未证明实质性能收益，已撤回 8 文件新增源码，固件也已回退。以下保留候选设计与验证过程；已去掉 P22，不包含 P20/P21/P22 的实验改动。固件属性查询与 Guest 映射作为一项组合评价。该候选针对长期存在的私有 WB 固件页缓存维护，不再只缩小每次清理范围。单轮收益不足以保留新增 RMM ABI 与映射生命周期复杂度。

普通非一致 Panthor 使用 WC 映射。Realm 路径原先统一禁用 map_wc，以 WB + 显式缓存维护保持正确。候选只对内部 `NO_MMAP` 且 GPU 侧 UNCACHED 的 MCU shared section、队列接口、ringbuffer 和 group syncobjs 使用私有 CPU NC 映射；不改变用户 BO、GPU_ONLY heap、页表或 Client 共享池，不调用 `set_memory_decrypted()` 或新增 dma_map_* / bounce 分配。原有 RMM GPA→HPA lease 校验、共享内存授权、可信事件/IRQ 与 doorbell 屏障继续保留。

新增一个 OpenCCA 私有 RSI FEATURES 索引 `0x4f434341`，bit 0 表示当前固定 RMM 的私有 RAM S2 MemAttr=0xf 且当前 REC 未启用 FWB，可以继承 S1 的 NC 属性。RMM 仅在 ENABLE_OPENCCA 且实际 REC HCR_EL2 的架构 bit 46 为零时返回；不能使用本端被定义为零的 HCR_FWB 宏代替实位检查。标准/旧 RMM 或未知索引返回零，Guest 保留原 WB+显式同步路径。该 bit 只是缓存属性契约，不授予设备权限，不宣称真实 CCA/FWB 下同样支持 NC，也不改变 GPT/GPC。

建立映射时：页已 pin、尚未 GPU 发布，先 clean 初始 WB 数据并 invalidate，逐页撤去 WB linear alias，再允许 shmem 建立 WC vmap。只在全部页转换成功后标记 NC；部分失败保留已撤映射页数，释放时逐页恢复。存活期不再通过 phys_to_virt 对无效线性地址执行缓存维护，DMA 屏障和范围检查仍执行。销毁时先撤 WC vmap，完整内存屏障后恢复 WB linear alias，再 unpin/free；有活跃 vmap 或恢复失败时保留对象，不能把线性映射无效的页交回分配器。原 sync-only cache probe 模式不申请 NC。GEM pin 使用 drm_gem_get_pages 的 unevictable mapping，未在运行中暴露用户 CPU mmap。

设计依据：[Arm memory model guide](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Armv8-A%20memory%20model%20guide.pdf?revision=58b1dd0a-3800-4218-b21a-f95a0332034c) §13/14 的别名与 S1/S2 属性组合，以及 [Linux DMA 文档](https://docs.kernel.org/core-api/dma-api-howto.html) 的非一致 DMA 维护要求。本实现是依据当前固定源码推导的 OpenCCA 平台优化，完整测试仅提高 2 分，尚未证明实质收益；不能用论文或架构规则替代测试。

验证：`private-nc-v23-check.py` 从当前实际 prepare/restore 及 RMM feature 实现提取 C 函数，ASan/UBSan、`-Wall -Wextra -Werror`，分别 ENABLE_OPENCCA=0/1 编译并执行通过。覆盖不支持/非私有/非目标角色拒绝、缓存清理先于移除 WB alias、活跃 vmap 禁止恢复、部分移除失败及恢复失败重试、FWB/未知索引拒绝。仅验证软件控制流与故障处理，不验证真实 TLB、缓存属性或 ARM 并发。日志 `build/realm-performance-20261018/private-nc-v23-check.log`，提取源码及源文件哈希在同前缀 check 目录。

固件日志 `private-nc-v23-firmware-build.log`，布局检查 PASS；保留原有 RMM RWX LOAD/build-id 丢弃和 make jobserver 警告，不写成“全构建无警告”。补丁清单检查 `private-nc-v23-patch-check.log` 记录已知 opencca-build 本地差异（RSI_LOG_LEVEL、独立 RMM_BUILD_DIR、布局检查、错误传播和固定 TPL1.16），已经审阅，没有重置。8 文件改动前备份在 `build/realm-performance-20261018/pre-private-nc-v23/`。


P23 固件已构建冻结在 `private-nc-v23-firmware/` 并已完成 SD2 部署。RMM ELF SHA-256 `3f8968a8c83d45982d63f49ced394422dd1feac2a06964cae10f4e10006912ab`，ITB `75e85625f2aad0c1c5f45267681766dd7816cdf404d14a7e18b294fd0a8a7b3b`；其余哈希及 RMM tracked patch 同目录。部署 run-id `realm-perf-private-nc-v23-firmware-20261018`，实际 SD 启动区备份 SHA-256 `7e9d704c1d8d4574f53692ab548a86d836235febc2a1f12eb3a97dafac5958fe`，位于对应 `build/firmware-runs/`。部署已完成；后续 glmark 为 866 分，现撤回候选固件。


P23 固件部署与 wrapper 均退出 0，Host 恢复原 `6.12.0-opencca-pmthor-opp3 #7`、CPU 0–1；部署状态 `DEPLOYED_HOST_RECOVERED`，UART/SD 备份/布局记录齐全。这只证明新属性查询固件可启动，不是 NC 映射或性能通过。

P23 最终 Guest 冻结：`build/realm-performance-20261018/private-nc-v23-p19/`，Proxy SHA-256 `dfa719eef8f8a2facad9b5cb8ef479ae0e004e37320acd5e91192e6a705da764`；Client / initrd / runner 与 P19 相同。`baseline-check.json` 对照 P19 的全量 tracked diff，只有 6 个 Guest 文件和 2 个 RMM 文件不同；未跟踪的既有实现也已归档。`P23-private-nc.patch` 为独立增量。原 `pre-private-nc-v23` 的 fw/sched 带 P22 暂存，不可盲目整包恢复；已另建 `rollback-private-nc-v23-p19/`，8 个文件均为独立 P19 基础并附哈希，固件回退使用 `ack-arm-firmware/`。

首次扩大重编译日志 `private-nc-v23-proxy-build.log` 包含固定源码 ACPI 头的 GCC15 字符串结尾警告；最终去掉 P22 后增量构建日志 `private-nc-v23-p19-proxy-build.log` 退出 0，并实际重编译 fw/sched/device/driver；GEM 对象在首次构建中已重编译，最终检查无需再次重编。不能将最终增量无 warning 推广为整个内核无 warning。新增软件检查在最终源码上重新运行通过。

P23 实际启动命令（最终 wrapper / VM 退出码均为 0）：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-private-nc-v23-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/private-nc-v23-p19 \
  --workload glmark --performance --benchmark-only
```

硬件验收额外核查 MCU shared interface 与 group syncobjs 的 `cpu_nc=1` 标记，确保实际使用候选属性，而不是旧固件/能力拒绝导致的 WB 回退；检查线性映射恢复失败、cache sync、GPU fault、FW ACK timeout、validation 和 teardown。测试前后条件仍为完整 33 场景 null-noop 1280×720 / frame-end finish，600 MHz 请求/594 MHz 实际，Proxy/Client 各 1 vCPU 分别固定 1/2 核，RMM 可信 IRQ 开启，诊断计时关闭。

运行中观测：远端 runner PID 587、Firecracker PID 648/649 已实际启动；Proxy 启动日志包含 `RMM-confirmed private NC interfaces, WB aliases removed` 和 `Realm MCU shared interface cpu_nc=1`。Client validation 已完成，26 成功、1 个已知例外、6 unknown，unexpected failure 为 0；完整计分仍在进行。此观测确认 MCU 接口未回退 WB，不代表最终成绩、所有 group 属性或资源恢复已通过。启动前耗时包含固件重启后的 SD 冷读 rootfs 校验，不能计入 glmark 帧时间。

本次整理将 P21/P22 的终态证据移回各自章节，删除重复命令并更新过时的待测描述；未改运行代码，无新增性能测量。


P23 最终硬件结果：完整 33 场景 **864 → 866（+2 / +0.23%）**，renderer 为 Mali-G610/Panfrost，validation 26/1/6，unexpected failure 为 0，提交错误为 0，受检 CSG/FW ping/translation fault/WARNING/Oops 为 0。MCU 和 group syncobjs 均有实际 `cpu_nc=1`，未见线性映射恢复失败。IRQ127 增量 `[2779069,216297]`；wrapper 和 VM 退出码 `[0,0]`，Host 恢复 CPU 0–1、300 MHz，无本轮 VM、挂载或 loop 遗留。

原始 7 文件已回收到 `GPU-SFTP/log/realm-xshm/realm-perf-private-nc-v23-glmark-20261018/`，逐文件核验远端 SHA-256；`assessment.json` 保存受检错误与成绩，外层资源与退出证据在 `build/lab-runs/realm-perf-private-nc-v23-glmark-20261018/`。RPC timing/counters 未启用，记 NOT_CAPTURED。逐场景比较保存在 `build/realm-performance-20261018/scene-comparison.json`：buffer map/subdata 均 46→45（-2.17%），shadow 604→610（+0.99%），terrain 38→39（+2.63%）。单轮细小涨跌不足以证明稳定收益，不能认定全局 NC 是提分方向；也不据此声称缓存维护绝无成本。

源码撤回：从独立 `rollback-private-nc-v23-p19/` 恢复并逐文件 SHA-256 验证全部 8 个文件，删除新增私有 RSI FEATURES ABI、NC 标志与映射/恢复分支，保留 P19 原有 WB 同步、RMM 共享内存授权及可信 IRQ。冻结 P23 输入及失败优化证据保持不变，记录 `private-nc-v23-withdrawal.json`。固件回退 run-id 为 `realm-perf-private-nc-v23-rollback-20261018`，使用 `ack-arm-firmware/`，部署与 wrapper 均退出 0，状态 DEPLOYED_HOST_RECOVERED，Host 恢复 #7 / CPU 0–1。实际回退前 SD 启动区备份 SHA-256 `9070e6943e0708169f1d0b685fc0a6774d5bed5808041902f2c944d0e0a08fe9`；证据在同 run-id 的 `build/firmware-runs/` 和 `build/lab-runs/`。


## P24：TRANSFER 回复附带精确完成点确认（863 分，已撤回）

**864 → 863，-1 / -0.12%，已撤回**。P23 源码与固件均已撤回，候选直接基于 P19；新增改动只在 Client、Proxy 和共享协议头三个文件，不改变 RMM、共享内存授权、可信 IRQ、GPU 内存隔离或固定测试参数。

动机：P23 观测 412028 次 timeline 查询，411235 次成功、793 次 pending，约 99.8% 的查询到达后端时已完成。此比例包括 validation/startup，不能认定所有 fence 在前一次操作时已经完成。候选在已有 SYNCOBJ_TRANSFER 回复前，就地执行一次同样语义的目标精确 point、WAIT_ALL、零超时查询；成功才附带确认，不成功不改变 transfer 返回值、也不等待 GPU。用已有协议 pad 的协商 bit 承载，不新增完成线程、回调池或共享状态机。

Client 只在启用现有 completed_wait_cache、协商支持且 dst_point 非零时请求确认。缓存仍绑到持有引用的目标 syncobj 和精确 point，捕获当前 mutation epoch；RPC 前后必须始终为本次唯一 mutation，epoch 未变且未回绕，才能记录。并发 reset/import/submit/signal/transfer（包括失败调用）继续使确认失效。不把完成点当单调水位，不推测另一个对象的状态。

同组改动将 SYNCOBJ_CREATE/DESTROY 从全文件 fence mutation 中排除：CREATE 只插入独立的 kzalloc 对象；DESTROY 只移除其 handle，backend 释放等引用清空，传递到其他对象的 fence 不会被撤销。缓存保存在 refcounted 对象上；同整数 ID 重用也不能继承旧对象记录。该调整用于允许销毁临时 source 后，仍使用目标的完成确认。效果按组合评价，不把收益分别归因。

构建均退出 0，日志 `build/realm-performance-20261018/transfer-proof-v24-{client,proxy}-build.log`；准确 P19 三文件回退在 `pre-transfer-proof-v24/` 并附 SHA-256。增加 queries/records 计数，后续必须结合实际 cache_hits、远端查询量、完整 33 场景成绩和内核/退出检查评价；无收益则删除本候选。


本地并发边界检查 `transfer-proof-v24-check.py/.log` 已通过：提取实际 Client 记录函数，以 ASan/UBSan 和 `-Wall -Wextra -Werror` 检查目标对象/精确 point、并发 mutation 尚未结束或已结束但 epoch 改变、回绕、空 point、旧对象保留而整数 handle 重用等状态；移除 epoch 检查的负对照必须在指定断言失败，已验证。该检查只覆盖提取函数的软件边界，不是完整 DRM 并发、协议或 GPU 正确性证据。全量 tracked patch 与 P19 比较仅预期三个文件不同，独立补丁及 `baseline-check.json` 位于 `transfer-proof-v24-source/`；硬件终态成绩与撤回结论见本节末。


P24 的语义依据是固定内核 `drivers/gpu/drm/drm_syncobj.c` 的 `drm_syncobj_transfer()` / `drm_syncobj_timeline_wait_handles()`：确认复用同一精确目标 point 的 WAIT_ALL 查询，不改变 DRM ioctl 的完成或快照定义。另见 [Linux DRM Sync Objects 文档](https://www.kernel.org/doc/html/v6.12/gpu/drm-mm.html#drm-sync-objects)。该版本属于本项目通信语义融合实验，不声称 PORTAL 或 CAGE 实现了相同的完成确认协议。

Proxy 侧提取函数检查 `transfer-proof-v24-proxy-check.py/.log` 已通过 ASan/UBSan、`-Wall -Wextra -Werror`：旧 peer 无确认请求时不额外查询；确认必须对应目标 handle/point、零超时和 WAIT_ALL；pending、查询错误和无有效 first_signaled 不发布确认；TRANSFER 原错误保持；非法 pad、point 与 handle 拒绝；所有路径对象引用平衡。以上为实际函数配合软件 stub 的边界检查，不替代真实 DRM/GPU 行为。板端预检退出 0，Pi/RK 角色与资源门槛通过，均无活跃实验进程。


P24 两侧内核构建均退出 0，实际编译 Client/Proxy 驱动；原 ACPI 头 GCC15 字符串结尾警告保留，不写成全构建无警告。终态记录 `transfer-proof-v24-build-results.json`。首次冻结工具将 ACPI 源注释中的 “Error Record” 误识别成 make 错误，修正为匹配真实 make 错误行后再冻结；没有因该工具问题改动内核，也未启动一次无效硬件运行。

最终冻结包 `build/realm-performance-20261018/transfer-proof-v24-p19/`：Client SHA-256 `722062c4e6c4b04a58310cc07088848557af7aa918878ed07838c8a981bc2911`，Proxy `55a584f0456579e09ff44cd1a832d91830496d1e9d251c299078aaedc5b1d6ed`；initrd `b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`、runner `548f837d72596459a0e09b4ed55933558028db232f886a4051353c03b6a8ac47` 与 P19 相同。`P24-transfer-proof.patch` 为独立增量，包含 58 个当前修改/未跟踪源文件的归档与哈希、组件 HEAD、全量 Guest/RMM diff 和已恢复 P19 固件哈希，便于复现。

实际运行命令（run-id `realm-perf-transfer-proof-v24-glmark-20261018`，完整成绩 863，runner 与 wrapper 均退出 0）：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-transfer-proof-v24-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/transfer-proof-v24-p19 \
  --workload glmark --performance --benchmark-only
```

测试固定完整 33 场景、1280×720 null-noop、frame-end finish、GPU 请求 600/实际 594 MHz、Proxy/Client 各 1 vCPU 768 MiB 分别绑核 1/2，诊断计时关闭，RMM 共享授权和 IRQ127 继续开启。RK Host 远端 runner PID 656 已确认实际存活；先进行固件回退重启后的 rootfs 冷读校验，不能因尚无 VM 日志或 SD 等待就重启本轮测试。该段为启动时状态；最终为 **864 → 863（-1 / -0.12%）**，已撤回。


补充项目调研（未改本轮运行代码，无新增性能测量）：Mesa Venus 在 2026-07-20 合入的两个连续提交提供了更具体的同步设计参照。[4c1938c8：弃用旧 fence feedback](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/4c1938c8adbe0e328f9db69362e79105c1e52d56) 明确描述暂时退回 driver/renderer 同步轮询；紧随的 [6aded3b9：改用 renderer sync](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/6aded3b9d65b8af85f1684d042249f1a0b32a9c9) 取消独立 renderer fence 对象，将创建、状态、等待和 sync-file import/export 统一到 renderer sync，并跳过仅提交 fence 的空 batch。它们不是本项目实测，也不能据此认定共享反馈必然更快或已过时。

可借鉴的是减少重复同步对象与转发层次、保留真实完成原语和精确生命周期；不能直接将 Normal Host 的同步 FD 当作 Realm 内可信完成凭据。本项目的确认仍须来自已授权 Proxy/Broker 对实际 GPU fence 的观察，RMM 事件只负责授权通信和唤醒，不能把 IRQ 到达或共享位变化等同 GPU 完成。P24 是在既有 TRANSFER 中合并一次精确状态观察的较小实验，未迁移 Mesa、未改变固定用户态。

### P24 实测影响与处理结论

**P19 864 → P24 863 分，-1 分 / -0.12%；无有效提分证据，已撤回。** 两版均为完整 1280×720、33 场景、null-noop、frame-end finish；GPU 请求 600 MHz/实际 594 MHz、Proxy/Client 分别绑定 CPU 1/2、关闭 RPC 诊断，RMM 固件、initrd、runner 与 P19 相同。两侧内核同时包含完成确认协议与 CREATE/DESTROY 失效策略调整，只评价组合结果。单轮差异不能证明稳定退步。

`transfer_proof_queries=0`、`transfer_proof_records=0`：新增确认路径未被本轮工作负载触发，不能由 863 分判断确认协议本身的开销或收益。固定 Mesa 的 fence 路径主要使用二值导出/导入与 WAIT，非零 timeline 点来自提交信号；后续优化应先核实实际调用路径，避免优化未使用的接口。

renderer 为 Mali-G610 (Panfrost)，validation 26 成功 / 1 已知例外 / 6 unknown，意外失败与提交错误为 0。两 Realm 的五类内核故障标记均未出现，IRQ `[2765774,225994]`，VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，无活跃实验进程、测试挂载或 loop 遗留。这些检查不替代尚未执行的其他回归。

实际命令见上；runner 和 wrapper 均退出 0。七份原始文件已回收并与远端 SHA-256 校验一致，证据目录 `GPU-SFTP/log/realm-xshm/realm-perf-transfer-proof-v24-glmark-20261018/`，含 `summary.json`、`assessment.json`、`controller-verification.json` 和两 Realm 日志；控制输出 `build/realm-performance-20261018/transfer-proof-v24-glmark.log`，前后资源记录 `build/lab-runs/realm-perf-transfer-proof-v24-glmark-20261018/`。RPC 计时未采集，不能写为零。

已从 `pre-transfer-proof-v24/` 恢复三个文件并逐文件验证 SHA-256，移除新增协议、计数器和 CREATE/DESTROY 策略改动，回到 P19 源码；记录 `transfer-proof-v24-withdrawal.json`。P24 冻结镜像及证据单独保留，不冒充恢复后的新构建结果。固件原本就是 P19，无需再次刷写。

## P25：固件事件 worker 内直接完成 fence（两轮后暂保留）

**P19 864 → 882、881，分别 +18 / +2.08%、+17 / +1.97%。** 两轮证据见本节末；不叠加 P20–P24，仅改 `panthor_sched.c`，Client、initrd、runner 和 RMM 固件均为已测 P19。优化目标是缩短 GPU 已完成到后端 fence 可见的路径；不推测该改动必然提分。

现有 Realm 完成路径为线程化 JOB IRQ → FW worker → group worker → 缓存读回与 fence signal。候选仅在 Realm 的 FW worker 路径中，在持有调度锁时取得 group 强引用并正常处理/应答固件事件，释放调度锁后直接执行原完成逻辑，再释放引用，避免第二次排队。tick、reset/suspend 和普通 VM 保留 group worker。继续从 GPU seqno 判定完成、读回映射 BO 与 syncobjs，不将 IRQ 当完成，不删除缓存维护；RMM 共享授权与 IRQ127 不变。

已排队的 group worker 可能与 FW worker 重叠，新增每 group 的 `completion_lock`，串行化两个完成入口与终止处理。该锁内不取调度锁，不在 fence spinlock 内进行 RMM/cache 调用；完成/终止的 job 引用回收在解锁后执行。一个 CSG 事件最多保留一个 group 引用，slot 改派后仍处理所捕获对象；每条路径引用均须释放。沿用既有 mapped-BO 同步实现及其并发前提，局部检查不能替代完整驱动并发证明。

依据 [Linux 6.12 workqueue 文档](https://www.kernel.org/doc/html/v6.12/core-api/workqueue.html)：普通 workqueue 并不保证所有 work 串行，睡眠时可以调度其他 worker；因此不能靠“同一队列/单 vCPU”推断互斥。这里复用实际完成函数，不直接调用 work callback，也不靠 work_busy 或取消/重新排队判断安全。与 P18 不同，保留线程化 JOB IRQ 和原 ACK/coalescing，不把排队前移到硬 IRQ。

`inline-completion-v25-check.py/.log`：提取实际 slot 捕获、完成 helper、延后 worker 和终止函数，以 ASan/UBSan、`-Wall -Wextra -Werror` 验证内联/延后并发、完成/终止并发、仅信号已到达 seqno、单次 signal/put、空队列、slot 改派后的强引用，以及终止错误。去掉 completion mutex 的负对照必须在指定重叠断言失败，已确认。仅为实际函数配合软件 stub 的局部检查，不是硬件或完整 DRM 并发证明。

Proxy 内核构建退出 0，日志 `build/realm-performance-20261018/inline-completion-v25-proxy-build.log`；实际重新编译 scheduler，无新增编译警告。Client 直接使用已测 P19，不声称重新构建。`baseline-check.json` 验证全量 Guest tracked diff 相对 P19 仅 scheduler 不同，RMM diff 不变。冻结包 `build/realm-performance-20261018/inline-completion-v25-p19/` 含独立补丁、完整组件 diff、58 个修改/未跟踪源文件与哈希、固定组件 HEAD 和已恢复固件来源；Proxy SHA-256 `0f225acde12b90d050b13bae59ce5bd45afae2ccd04c52f5f0a85a48c4770373`，其他三个载荷逐字节等于 P19。独立源码回退 `pre-inline-completion-v25/`。

预检退出 0，角色/资源门槛通过。首轮实际完整 glmark 命令如下，成绩与退出码以本节末的终态记录为准：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-inline-completion-v25-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/inline-completion-v25-p19 \
  --workload glmark --performance --benchmark-only
```

保持 P19 完整 33 场景、1280×720 null-noop、frame-end finish、600/594 MHz、Proxy/Client 各 1 vCPU 768 MiB、绑核 1/2、关闭诊断计时。控制日志 `build/realm-performance-20261018/inline-completion-v25-glmark.log`，wrapper 证据 `build/lab-runs/realm-perf-inline-completion-v25-glmark-20261018/`。运行期间冻结输入不修改。

### P25 首轮实测：864 → 882，+18 / +2.08%

`realm-perf-inline-completion-v25-glmark-20261018` 的 runner 与 wrapper 均退出 0，完整 33 场景 **882 分**。相对 P19 为 **+18 分 / +2.08%**；33 场景中 27 项 FPS 上升、4 项持平、2 项下降（build 无 VBO 与 shadow）。实际命令、冻结哈希与可比条件见上。首轮时不认定稳定收益；相同冻结镜像的第二轮结果在下文单独列出，仍缺少同期重复 P19 对照。目标 >1000 尚未达到。

Mali-G610 (Panfrost)，validation 26 成功 / 1 已知例外 / 6 unknown，意外失败 0；GPU_SMOKE_RESULT=PASS，提交错误及两 Realm 五类内核故障标记均未出现。IRQ `[2820190,226475]`，VM 退出 `[0,0]`。Client timeline 查询 415990 次，成功 415678 / pending 312，cache_hits 317323；这些计数含 startup/validation 且工作总量随 FPS 变化，不能直接按总数归因。RPC 计时关闭，未采集而非零开销。

一次性 INFO 级内联入口标记未保留在最终日志中；console loglevel=6 不输出 INFO，后期 kernel-log 中旧记录已被环形缓冲覆盖。因此本轮分数只支持该冻结代码组合的结果，不能用缺失标记认定路径未执行，也不能声称已计量该入口命中次数或排队开销。局部实际函数检查与板端输入哈希是另外两类证据。

Host 恢复 pmthor、CPU 0–1、userspace 300 MHz，无活跃实验进程、测试挂载或 loop 遗留。七份原始文件已经回收到 `GPU-SFTP/log/realm-xshm/realm-perf-inline-completion-v25-glmark-20261018/` 并核对远端 SHA-256；含 summary、assessment、controller-verification。wrapper 前后资源与退出码在同 run-id 的 `build/lab-runs/`。没有执行 API、计算、多 Client 或完整回归，不能沿用其历史 PASS。

### P25 复测：864 → 881，+17 / +1.97%（暂保留）

run-id `realm-perf-inline-completion-v25-r2-glmark-20261018`，使用相同 `inline-completion-v25-p19/` 四份冻结输入，命令仅替换 run-id；wrapper 和 runner 均退出 0。完整 33 场景 **881 分**，相对 P19 的场景 FPS 为 29 项上升、1 项持平、3 项下降；相对首轮 882 为 -1 / -0.11%；两轮范围 **881–882**、均值 881.5，相对 P19 864 的均值变化 +17.5 / +2.03%。两轮一致改善支持暂保留，但没有同期多轮 P19 对照，不能认定所有环境下均有稳定收益，也不能将组合内锁与内联分别归因。

Mali-G610/Panfrost；validation 26 成功 / 1 已知例外 / 6 unknown，意外失败 0，提交错误 0，GPU_SMOKE_RESULT=PASS。两 Realm 五类内核故障标记均未出现，IRQ `[2818402,230601]`，VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载和 loop 遗留。七份原始文件回收至 `GPU-SFTP/log/realm-xshm/realm-perf-inline-completion-v25-r2-glmark-20261018/`，远端 SHA-256 全部核对；assessment 与 scene-comparison 同目录。控制输出 `build/realm-performance-20261018/inline-completion-v25-r2-glmark.log`；wrapper 前后资源及退出码在同 run-id 的 `build/lab-runs/`。未追加其他测试矩阵。


## P26：Client 本地 binary syncobj 与私有快照引用（实测后撤回）

**P25 881 → 862，-19 / -2.16%；相对 P25 首轮 882 为 -20 / -2.27%。** 只修改 Client 的 `panthor_client_drv.c`，不修改 Proxy 协议、RMM 或共享授权路径。Mesa 的导出→新建 binary 对象→导入→等待→销毁会产生临时容器 RPC；这里将临时对象保留在 Client 本地，导入时持有已有的不可变私有快照，binary wait 直接等待该快照，目标是减少容器往返。减少 RPC 不等于端到端提分，须用完整 glmark 判定。

用户 handle 与 wire handle 分离；对象首次被提交、修改、查询或其他需要后端的路径使用时，才串行创建真实后端对象，并先安装快照再发布 wire handle。空对象的 WAIT_FOR_SUBMIT 仍物化，保持以后提交与等待指向同一后端容器；已经物化的对象导入仍走后端 TRANSFER。binary wait 对捕获的私有快照独立持有引用，后续导入、reset、销毁及 handle 复用不会改变旧等待对象。共享不可变 fence 不等于共享可变 syncobj。

私有快照包装独立引用计数，最后一个引用释放时才远端销毁；本地对象不持有导出的 dma_fence/session file，避免 FD 关闭与文件关闭形成引用环。限制同 session、拒绝自引用，局部物化失败只销毁本次新容器，保留旧快照以供重试。GPU seqno、缓存读回和真实完成判定沿用 P25，不在 Client 伪造完成。

Client 构建退出 0，实际重新编译驱动；`build/realm-performance-20261018/lazy-binary-v26-client-build.log`。`lazy-binary-v26-check.py/.log` 提取实际 helper，ASan/UBSan 和 pthread 检查本地创建/导入/等待、FD 与文件关闭、旧等待跨快照替换、失败重试、8 线程单次物化、signaled 标志、同 session 限制及单次销毁。去掉等待强引用的负对照在指定过早销毁断言失败。该检查使用软件 stub，不能替代完整 DRM、GPU 或安全隔离验证。新增现有统计行中的 lazy_creates/materialized/snapshot_imports/snapshot_waits，用于判断实际负载是否命中。

冻结包 `build/realm-performance-20261018/lazy-binary-v26-v25/` 保存独立补丁、完整 tracked diff、58 个修改/未跟踪源文件及哈希、组件 HEAD、固件清单；相对 P25 仅上述 Client 文件改变，RMM diff 不变。输入 SHA-256：

- Client：`4c70545922dcc116e85bd3c29c154fc369bae58d49364dc9c72d95d64b988742`。
- Proxy：`0f225acde12b90d050b13bae59ce5bd45afae2ccd04c52f5f0a85a48c4770373`，与 P25 一致。
- initrd：`b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`。
- runner：`548f837d72596459a0e09b4ed55933558028db232f886a4051353c03b6a8ac47`。

仍为完整 33 场景 720p、null-noop、frame-end finish、600/594 MHz、每 Realm 1 vCPU/768 MiB、绑核 1/2，关闭 RPC 诊断计时；不修改 Mesa/rootfs。测试命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-lazy-binary-v26-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/lazy-binary-v26-v25 \
  --workload glmark --performance --benchmark-only
```

以下为运行前冻结的证据位置；终态见下文。控制输出 `build/realm-performance-20261018/lazy-binary-v26-glmark.log`；wrapper 证据在同 run-id 的 `build/lab-runs/`，原始日志回收至同 run-id 的 `GPU-SFTP/log/realm-xshm/`。若无有效收益，撤回 Client 改动，保留 P25 scheduler 与本轮证据。


### P26 终态：862 分，源码撤回

`realm-perf-lazy-binary-v26-glmark-20261018` 的 wrapper 与 runner 均退出 0，完整 33 场景 **862 分**。相对 P25 复测 881 为 **-19 / -2.16%**，8 场景上升、4 持平、21 下降；build VBO -7.31%，三项 texture -5.43% 至 -6.18%。Mali-G610/Panfrost，validation 26 成功 / 1 已知例外 / 6 unknown，意外失败 0、提交错误 0；GPU_SMOKE_RESULT=PASS。两 Realm 五类受检内核标记均未出现，IRQ `[1963671,317162]`，VM 退出 `[0,0]`。

lazy_creates=285038、materialized=72、snapshot_imports=snapshot_waits=284897，证明实际负载命中本地临时对象路径；未物化对象的 CREATE/IMPORT/公开 DESTROY 不再发 RPC。reply poll attempts 从 P25 复测 2851500 降至 1949652（-31.63%），但睡前 ARM 从 253259 增至 293797（+16.01%），回复通知 sent 从 278485 增至 317399（+13.97%），Client IRQ 增加 37.54%；睡前已取得回复的比例从 91.27% 降至 84.93%。这些计数含启动和 validation，总工作量随 FPS 改变，不是每 job 归一化数据。结果支持“较早进入等待改变重叠及通知时序”的假设，**没有逐操作时序证据，不将其认定为唯一退分原因**；RPC 计时关闭，不能给出新的 WAIT 平均耗时。

Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载或 loop 遗留。七份原始文件回收至 `GPU-SFTP/log/realm-xshm/realm-perf-lazy-binary-v26-glmark-20261018/` 并核对远端 SHA-256；assessment 和 controller-verification 同目录；scene-comparison 与 transport-stats 在控制机构建目录。wrapper 前后资源和退出码位于同 run-id 的 `build/lab-runs/`。

**结论：撤回 P26 优化，不保留未提分的对象包装/延迟物化设计及计数器。** Client 文件先按独立备份恢复 P25/P19 SHA-256 `b1693e5bb9919c4a5516c6eb39203e39f4c8c058622c94c6055e88864957fd61`，P25 scheduler 和 RMM 不变；撤回证据 `build/realm-performance-20261018/lazy-binary-v26-withdrawal.json`。随后只单独保留下面的引用释放缺陷修复，不属于 P26 性能收益。

### 独立正确性修复：数组查询失败时重复释放引用

现有 `panthor_client_fill_syncobj_handles()` 查询到无效 handle 时，会释放此前成功获取的引用，而两个调用者在失败出口又释放同一数组，导致公开对象仍在 xarray 中时引用被多减。现改为由调用者统一释放；没有新增对象、协议或性能路径。P26 优化已移除，此修复独立保留。

`build/realm-performance-20261018/sync-array-ref-fix-check.py/.log` 提取实际 helper，以 ASan/UBSan 和 `-Wall -Wextra -Werror` 覆盖每个失败位置、重复 handle、成功与部分失败后的调用者清理、无效参数和上限。原 helper 的负对照必须在公开对象引用被误减的指定断言失败，已确认。该检查用软件 stub，不是整套 DRM 或硬件回归。分数影响：**没有新增性能测量，不宣称提分**；Client 内核构建退出 0，实际重新编译 `panthor_client_drv.o`，日志 `build/realm-performance-20261018/sync-array-ref-fix-client-build.log`；独立补丁、源码和构建哈希位于 `sync-array-ref-fix/`。本次 P27 仍使用已测 P25 冻结 Client，不含该修复，避免混淆性能对照。

## P27：延长 Client 回复轮询上限（902 分，候选待复测）

**P25 881 → 902，+21 / +2.38%；相对首轮 882 为 +20 / +2.27%。** P26 再次表明减少控制 RPC 不等于缩短等待；本轮直接基于 P25，复用其三个二进制及 RMM，只将既有 `client_comm_vmshm.realm_poll_us=100` 改为 `200`。目标是测量更多短回复能否在 Client 调用线程中取得，从而减少 ARM/可信 IRQ 和睡眠；Client 与 Proxy 分别固定在 CPU 2/1，不增加 Proxy 的忙等，也不以轮询结果伪造 GPU 完成。所有授权与事件确认保持原实现。当前 Realm 本身存在 idle busy 行为，本轮不声称节电；改变轮询窗口属于性能配置实验。

冻结包 `build/realm-performance-20261018/reply-poll200-v27-p25/`：Client `b4263f50ca143ebdb2c114b2dac51e9856b4dd7e8f5e71e252959ab2de816429`、Proxy `0f225acde12b90d050b13bae59ce5bd45afae2ccd04c52f5f0a85a48c4770373`、initrd `b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7` 均与 P25 完全相同；runner `55b20b27d2a83e438de584e06448f26a8f6077edadf87281e0316831e393e965`，只改上述单个参数。源码、完整 tracked diff、组件 HEAD 与哈希随包保存。完整 33 场景 720p、频率、绑核、内存、诊断开关及校验口径不变。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-reply-poll200-v27-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/reply-poll200-v27-p25 \
  --workload glmark --performance --benchmark-only
```

硬件测试终态见下文。控制输出 `build/realm-performance-20261018/reply-poll200-v27-glmark.log`，wrapper 证据为同 run-id 的 `build/lab-runs/`；先收齐原始日志、校验和清理结果再决定是否保留参数。未追加其他硬件测试矩阵。


### P27 终态：881 → 902，+21 / +2.38%（单轮候选）

run-id `realm-perf-reply-poll200-v27-glmark-20261018` 的 wrapper 与 runner 均退出 0，完整 33 场景 **902 分**。相对 P25 复测 881，27 场景 FPS 上升、5 持平、1 下降；build 无 VBO 870→868（-0.23%），conditionals / function / loop 部分场景约 +5%–6%。输入镜像相同，只有 Client 回复轮询上限改变；仅一轮，不认定稳定收益，不将配置收益算成新协议或 RMM 优化。候选冻结包保留，P25 原参数可回退。

Mali-G610/Panfrost；validation 26 成功 / 1 已知例外 / 6 unknown，意外失败 0、提交错误 0，GPU_SMOKE_RESULT=PASS。两 Realm 五类内核故障标记均未出现，IRQ `[2917416,121428]`、VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载和 loop 遗留。七份原始文件在 `GPU-SFTP/log/realm-xshm/realm-perf-reply-poll200-v27-glmark-20261018/` 已核对远端 SHA-256；assessment、controller-verification 同目录，wrapper 前后资源与退出码在同 run-id 的 `build/lab-runs/`。

reply poll attempts=2914623、睡前完成=2805400（96.25%，P25 复测为 91.27%）、睡前 ARM=113512（相对 253259 为 -55.18%），回复 sent=128613 / suppressed=2817893；Client IRQ 相对 230601 为 -47.34%。计数含启动/validation，工作总量随帧率改变，不直接作为每任务值。结果支持等待窗口影响休眠/通知成本；未采集逐 RPC 时序，不声称解释了全部 21 分。距旧普通 VM 1058 仍低 156 / 14.74%，环境路径不同，只作目标差距。没有运行其他硬件矩阵。

## P28：已有回复轮询上限 1000 µs（914 分，候选待复测）

**P27 902 → P28 914，+12 / +1.33%；单轮候选。** P27 中扩大窗口减少了 ARM 与 Client IRQ，本轮直接测试既有实现的最大窗口 1000 µs，判断剩余短等待能否继续避免睡眠；不是新增忙等机制或放宽授权。循环仍在回复完成、出现 need_resched 或到达预算时退出，不对每个 RPC 强制等待满 1 ms。共享队列读不到真实回复时仍须正常 ARM、复查、超时与错误处理。CPU 占用/功耗尚未单独测量，不宣称节电。

冻结包 `build/realm-performance-20261018/reply-poll1000-v28-p25/` 的 Client、Proxy、initrd 与 P27/P25 完全一致（沿用 P27 节三份哈希）；runner `eab716a5d716e61059a9657d51782a5ceafa8ac7e9510d746892cb98733fa2a4`，仅 `client_comm_vmshm.realm_poll_us=200` 改为 `1000`。独立参数补丁、源码、组件 HEAD 与哈希随包保存；不变的冻结文件用硬链接去重，runner 独立存储，所有冻结输入保持只读使用。仍不包含已撤回 P26、新完成页设计或独立引用释放修复。测试条件、完整 33 场景和校验口径不变。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-reply-poll1000-v28-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/reply-poll1000-v28-p25 \
  --workload glmark --performance --benchmark-only
```

本轮 wrapper 与 runner 均退出 0，完整 33 场景 **914 分**；对 P27 902 为 +12 / +1.33%，对 P25 复测 881 为 +33 / +3.75%。24 场景上升、3 持平、6 下降；high-poly bump 856→898（+4.91%），refract 131→130（-0.76%）。保留冻结参数候选，尚未重复确认稳定收益。

Mali-G610/Panfrost；validation 26 成功 / 1 已知例外 / 6 unknown，意外失败及提交错误 0；两 Realm 五类受检内核故障标记均未出现，IRQ `[2972441,40127]`，VM 退出 `[0,0]`。Host 已恢复 pmthor、CPU 0–1、300 MHz，无本轮实验进程、挂载或 loop 遗留。七份原始文件回收到 `GPU-SFTP/log/realm-xshm/realm-perf-reply-poll1000-v28-glmark-20261018/`，均已核对远端 SHA-256；assessment 与 controller-verification 同目录。控制输出 `build/realm-performance-20261018/reply-poll1000-v28-glmark.log`，wrapper 前后资源与退出码在同 run-id 的 `build/lab-runs/`。

reply poll attempts=2940307、睡前完成=2938465（99.94%）、睡前 ARM=7779（P27 为 113512，-93.15%），回复 sent=40665 / suppressed=2939613；Client IRQ 比 P27 减少 66.95%。计数包括启动/validation，不能直接当作每帧开销；逐 RPC 时序未采集，CPU 占用/功耗未单独测量。不能仅凭中断减少声称节电或解释全部分差。完成页方案不在本轮镜像中。


## P29：原生 fence 发布不可变快照完成页（918 分，未证明稳定收益）

**P28 914 → P29 918，+4 / +0.44%；未证明稳定收益。** P26 表明仅减少 CREATE/IMPORT/DESTROY RPC 会让等待更早进入睡眠，实际反而掉分。本轮将延迟 binary 容器与原生完成页结合：Proxy 为已复制的不可变 snapshot 捕获真实 `dma_fence`，成功回调向会话专属 4 KiB 页发布唯一 cookie；Client 对相同快照最多轮询 100 µs，成功直接完成等待，未完成、错误、无空槽或调度需要均回退原有 WAIT RPC。普通可变 syncobj 的等待不使用该提示。不是重新保留 P26 单独优化，其收益必须作为本轮组合评估。

页有 64 个独立槽位，每次捕获 cookie 不重用，回调撤销/排空后才能释放槽位；Client 引用页和快照直到在途等待结束。Proxy 阻止私有快照作为 TRANSFER/RESET/SIGNAL、timeline signal、VM_BIND 或提交计划的写入目标，避免已捕获 fence 被替换。页按已认证会话 owner 分配，Client 仅申请 CPU_READ，无用户 mmap 或 GPU 权限。当前对象描述符权限属于软件策略，不宣称能阻挡已攻陷 Client 内核或恶意 Host；仍受本文 GPT/GPC 硬件限制。

代码审查中修正了尚未部署版本的两处问题：回调内不能通过 `dma_fence_get_status()` 重入原生 fence 锁，改为读取完成时已确定的 error；完成页必须在真正的会话释放路径、所有快照回调结束后释放。两侧内核需以最终源码重新构建成功后才能冻结和部署。

本地 ASan/UBSan 检查提取实际注册/回调/取消及 Client 完成检查与等待函数，覆盖 cookie 身份、旧槽位重用、在途回调排空、原生持锁回调、64 槽上限、错误/分配失败、ALL/ANY、原始绝对超时和调度回退；去掉排空和接受任意非零 cookie 两个负对照均触发指定断言。另提取实际 Client 生命周期函数，覆盖 FD/file 关闭、在途等待持有完成页、别名替换、物化失败与并发物化，去掉等待强引用的负对照触发指定断言。日志为 `build/realm-performance-20261018/immutable-completion-v29-{check,alias-check}.log`；这些是带底层 stub 的局部检查，不是全 DRM、完整回归或硬件隔离证明。另在启动后增加只读源码检查的负对照：将回调改回带锁的 status helper，会在持有非递归 fence 锁的指定断言失败，日志 `immutable-completion-v29-lock-check.log`；未修改运行代码或冻结输入，不产生新增分数结果。

保持 P28 的 1000 µs runner、initrd、频率/绑核/内存与完整 33 场景，P25 scheduler 及 P19 RMM 不变；改动仅六个 Guest 源文件。含独立数组失败清理引用修复，不宣称其性能收益。回退源码与哈希为 `build/realm-performance-20261018/pre-immutable-completion-v29/`；该回退保留 P25 和独立引用修复。最终两侧内核构建退出码均为 0，日志为 `immutable-completion-v29-{client,proxy}-final-build.log`；`git diff --check` 通过。冻结包 `build/realm-performance-20261018/immutable-completion-v29-p28/` 保存完整源码差异、58 份改动/新增源码及哈希、组件 HEAD、独立六文件补丁、局部检查与构建日志、已部署固件清单。Client Image `fdea3e3c07c1eee8ec147fef1c5819662f950c35b30ad33b0a5a2a9bfff5bf17`，Proxy Image `04e7c42679fa68b650044874e2236f34a655b4a1594d17b3dde713ff95f5f4fd`；initrd 与 runner 和 P28 完全一致，RMM diff 与 P28 一致，不重新刷固件。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-immutable-completion-v29-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/immutable-completion-v29-p28 \
  --workload glmark --performance --benchmark-only
```

本轮完整硬件终态见下文。控制输出 `build/realm-performance-20261018/immutable-completion-v29-glmark.log`，wrapper 证据在同 run-id 的 `build/lab-runs/`，原始证据按现有流程回收到 `GPU-SFTP/log/realm-xshm/`；以成功分配页数、cookie checks/hits/fallbacks 判断路径实际命中，最终仍以完整分数和正确性/恢复判断是否保留。


### P29 终态：914 → 918，+4 / +0.44%（低命中，不认定有效收益）

run-id `realm-perf-immutable-completion-v29-glmark-20261018`，wrapper 与 runner 均退出 0，完整 33 场景 **918 分**，对 P28 为 +4 / +0.44%；14 场景上升、4 持平、15 下降，shadow 626→609（-2.72%），normals bump 1318→1401（+6.30%）。各仅一轮，分差很小，不将本方案列为已获稳定提分的改动；暂作为 P30 单参数实验的候选基础，若进一步实测无效，整体六文件回退，不单独保留 P26 延迟容器。

Mali-G610/Panfrost；validation 26 成功 / 1 已知例外 / 6 unknown，意外失败及提交错误 0，GPU_SMOKE_RESULT=PASS；两 Realm 五类受检内核故障标记均未出现，IRQ `[2074543,25515]`、VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载或 loop 遗留。七份原始文件回收到同 run-id 的 `GPU-SFTP/log/realm-xshm/` 并核对远端 SHA-256，assessment/controller-verification 同目录。

本轮 completion_pages=4、completion_checks=303317、hits=4368、fallbacks=298949，命中率 **1.44%**；lazy_creates=303458、materialized=72，snapshot_imports/waits=303317，证明代码实际执行，绝大多数完成等待仍回退 RPC。计数含启动/validation，不能直接等同计分阶段每帧。RPC reply attempts 2940307→2053674（-30.15%），睡前 ARM 7779→2122，但只多 4 分，不能以 RPC/中断降低代替实际提分。未采集逐 RPC 时序，也未采集每次本地轮询退出原因，尚不能断言全部回退都因 100 µs 超时。

## P30：只扩大真实完成页轮询预算（957 分，候选待复测）

**P29 918 → P30 957，+39 / +4.25%；单轮候选。** 在已实际启用的完成页上，将 Client 的短轮询预算 100→1000 µs，测试低命中是否主要受窗口限制；该修改不改变 RMM 通知协议，不改变普通 RPC 轮询参数，也不推迟用户绝对超时。仍在完成、need_resched、signal_pending 或预算到期时退出，错误/无提示继续原 WAIT RPC。CPU 占用/功耗未单独测量，不宣称节电；若只是更多忙等而无有效收益，不保留额外复杂度。

仅 Client 源码一行改变，Proxy、initrd、runner、RMM 及其他源码与 P29 完全相同。Client 构建退出 0，实际重新编译驱动并生成 Image；原实际函数检查按新预算重新运行，ALL/ANY、用户绝对超时裁剪、调度退出及两个负对照通过。冻结包 `build/realm-performance-20261018/completion-poll1000-v30-v29/` 包含完整源码/patch/哈希、独立单行补丁和检查/构建日志；Client Image `39b55e9ca1ce14f851ac16ee0144cb5343025eacde3c513702d32b8a8e251ceb`，其余三份运行哈希沿用 P29。回退单行至 P29 的备份在 `pre-completion-poll1000-v30/`，整体回退至 P25 加独立引用修复使用 `pre-immutable-completion-v29/`。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-completion-poll1000-v30-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/completion-poll1000-v30-v29 \
  --workload glmark --performance --benchmark-only
```

硬件终态见下文。控制日志 `build/realm-performance-20261018/completion-poll1000-v30-glmark.log`，wrapper 与原始证据仍按同 run-id 保存，继续只跑完整 glmark。


### P30 终态：918 → 957，+39 / +4.25%（候选，待复测）

run-id `realm-perf-completion-poll1000-v30-glmark-20261018`，wrapper 与 runner 均退出 0，完整 33 场景 **957 分**；对 P29 为 +39 / +4.25%，30 场景上升、1 持平、2 下降，effect2d laplacian 1158→1238（+6.91%）；两项 buffer 46→45（-2.17%）。相对没有完成页的 P28 914，本组合为 +43 / +4.70%；不能将组合效果都归因于 P29 本身，也没有同期多轮对照，暂保留候选等待复测。

Mali-G610/Panfrost；validation 26 成功 / 1 已知例外 / 6 unknown，意外失败及提交错误 0，GPU_SMOKE_RESULT=PASS；两 Realm 五类受检内核故障标记均未出现，IRQ `[1846472,48371]`，VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载和 loop 遗留。七份原始文件已回收到同 run-id 的 `GPU-SFTP/log/realm-xshm/` 并核对远端 SHA-256；assessment/controller-verification 同目录，wrapper 前后资源和退出码在同 run-id 的 `build/lab-runs/`。

完成页 checks=316152、hits=314836、fallbacks=1316，命中率 **99.58%**（P29 为 1.44%），pages=4；lazy_creates=316293、materialized=72、snapshot_imports/waits=316152。reply attempts=1815269，睡前完成=1814783，睡前 ARM=716，回复 sent=48676 / suppressed=1798957。Client IRQ 比 P29 增多（25515→48371），不能声称所有通知开销都降低，更不能声称节电；未采集逐 RPC 时序与功耗，计数含启动/validation。完成页命中与总分同时改善，支持短窗口限制了原路径，但这仍是单轮证据。距离超过 1000 的目标尚有差距。

## P31：复用完整原生 chain 的较小 timeline 点（无提分，已撤回）

**P30 957 → P31 957；0 / 0.00%，无提分，已撤回。** 原缓存仅复用同一对象、同一 mutation epoch、同一 timeline point 的非阻塞 WAIT_ALL 成功结果；本轮在其余限制不变时，将精确相等改为 `completed_point >= requested_point`。依据是固定内核 `dma_fence_chain_find_seqno()` 和 `dma_fence_chain_signaled()`：某个 chain 点成功完成包含它之前的 fence，且同一对象没有任何同步变更时，较小的正数点也已完成。不是只看最后一个 GPU job 的 seqno，不跨 reset/transfer/提交等 mutation 复用，不用更大点、零点、WAIT_AVAILABLE 或其他 flag 推测完成；未来点与无证明状态仍发原 RPC。

`native-chain-prefix-check.py/.log` 提取实际内核 chain init/walk/find/signaled，覆盖 8 个 job 的所有 pending 组合、递增、空洞、重复和逆序插入/context 变化、GC，4433 个“完成 N 则完成较小正数点”的观测蕴含成立；把完整 chain 完成改成只看最后 contained job 的负对照，在前驱仍 pending 的指定断言失败。`native-prefix-v31-cache-check.py/.log` 提取实际 Client timeline wait 与 mutation 函数，覆盖较小点命中，未来/零点、flags、阻塞等待、多 handle、epoch、在途修改、回绕、迟到 RPC、错误与 handle 重用的回退和引用；去掉 epoch、无上界命中、忽略关闭缓存期间 mutation 的三个负对照均触发指定断言。这些检查对底层 generic fence/ref/RCU/transport/uaccess 使用 stub，不是完整内核并发、DRM 或硬件隔离证明。

审查同时发现原缓存开关的正确性缺口：关闭缓存时不记 mutation，重新开启可能复用关闭前的旧完成凭据。现在即使缓存关闭仍跟踪 epoch，缓存开启的正常性能路径保持原有跟踪；独立修复补丁与基于 P30 的源码位于 `cache-toggle-invalidation-fix/`，没有单独硬件成绩，不宣称该修复带来提分。若 P31 优化撤回，此正确性修复仍单独保留，并在实际回退基线上重建。

只修改 Client 源码，构建退出 0，实际重新编译驱动并生成 Image；`native-prefix-v31-client-build.log`，`git diff --check` 通过。冻结包 `build/realm-performance-20261018/native-prefix-v31-v30/` 保存完整源码/patch/哈希、组件 HEAD、独立增量、局部检查与构建日志。Client Image `b62c5a8c9173c9e92f3e99d9959557e6d0b6be62085bd1f09d059c9c5a261279`；Proxy、initrd、runner 与 P30 一致，RMM 和其他源码哈希不变，无需刷固件。原始 P30 Client 源码回退在 `pre-native-prefix-v31/`，整体 P29/P30 组合回退仍为 `pre-immutable-completion-v29/`，须另保留两项独立引用/缓存正确性修复。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-native-prefix-v31-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/native-prefix-v31-v30 \
  --workload glmark --performance --benchmark-only
```

硬件终态及撤回见下文。控制日志 `build/realm-performance-20261018/native-prefix-v31-glmark.log`，wrapper 和回收原始文件按同 run-id 保存；保持完整 33 场景、测试条件及健康/恢复检查，不扩大硬件矩阵。

### P31 终态与撤回

**P30 957 → P31 957，0 / 0.00%；无提分证据，撤回较小点缓存扩展。**
run-id `realm-perf-native-prefix-v31-glmark-20261018`，上述实际命令的 wrapper 与 runner 均退出 0。
同条件完整 33 场景，10 场景上升、6 持平、17 下降；build 无 VBO +4.56%，terrain -2.38%，
不能用局部上涨替代总分判断。Mali-G610/Panfrost，validation 26 成功 / 1 已知例外 / 6 unknown，
意外失败与提交错误 0，GPU_SMOKE_RESULT=PASS。两 Realm 五类受检内核标记均未出现，
IRQ `[1837093,47887]`，VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，
无实验进程、挂载或 loop 遗留。七份原始文件已回收至同 run-id 的
`GPU-SFTP/log/realm-xshm/` 并逐文件核对远端 SHA-256；assessment/controller-verification 同目录，
wrapper 前后资源及退出码在同 run-id 的 `build/lab-runs/`。

缓存 hits 351415→360835，RPC 尝试 1815269→1795001，但总分不变；
不能由计数改善推断性能获益。完成页 hits/checks 为 314828/316158（99.58%）。
源码已恢复 P30 的精确点比较，独立保留关闭缓存期间仍跟踪 mutation 的正确性修复，
数组引用修复亦保留；没有宣称这两项正确性修复提分。回退后实际 wait/mutation 函数的
ASan/UBSan 检查及三个指定断言负对照通过，日志
`build/realm-performance-20261018/retained-cache-toggle-fix-check.log`。
源码撤回哈希及结论在 `native-prefix-v31-withdrawal.json`；重建后的独立组合尚无硬件成绩，
不能直接沿用 P30 或 P31 的 PASS。冻结 P31 输入和失败/无收益实验的证据保留。

## 构建入口的复现修正（不计提分）

旧 `build-verified-kernels.sh` 直接复制 2026-10-15 发布配置，会关闭 Realm 共享内存、
恢复 32 MiB CMA 并打开不同的 Client 启动自测，不能重建当前测量配置。
新增 `realm` 角色，只构建成套 Client/Proxy，合并 `configs/performance/realm-*.config`，
输出至 Realm 专用目录；原有角色保持原路径。
第一次配置核对发现 Client DEV_QUERY 自测仍开启，保留失败记录后明确关闭这两项，
再次独立合并及 `olddefconfig` 已确认两侧所有配置项与实际测量配置一致。
证据为 `build/realm-performance-20261018/realm-config-reproduction-check.json`、
`config-repro-v2-{client,proxy}/` 和 `native-prefix-v31-build-configs/`。
脚本语法检查通过，新入口实际构建两侧 Image 并安装均成功，退出 0；两侧全部配置项再次核对一致。
命令 `bash scripts/build/build-verified-kernels.sh realm`，日志 `realm-config-entry-retained-build.log`，
哈希和安装核对为 `realm-config-entry-retained-build.json`（均位于上述构建证据目录）。
Client 为撤回 P31、保留独立正确性修复后的源码，尚未单独硬件测量；未改已测冻结输入。
**分数影响：无新增性能测量，不宣称提分；用途仅为可复现构建。**

## 撤回 P31 后的基线复测（957 分）

撤回较小点缓存扩展、保留 F1/F2 正确性修复后，用新的 Realm 构建入口重建两侧内核，
单独复测。标准 runner 的性能模式已同步 P28–P31 实测的 1000 µs 回复轮询参数，
并修正帮助文字；冻结 runner 相对上一轮只有帮助文字差异，实际参数相同。
此轮用来验证实际保留组合，不能把重建或正确性修复算作已获提分。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-retained-v30-r2-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/retained-v30-r2 \
  --workload glmark --performance --benchmark-only
```

冻结 Client `26cb899c7f76495896503f4cf70fb109522613629b7db86bdfa0411ac9fa829b`，
Proxy `b305e202460a92aba4a27dca255eacc1a4230baedfd5cfce167dd9dc3eb891b4`，
initrd `b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`，
runner `feb2f56f2d5ccc2fae9fd3c7c9078cc330df8b176532708c1c3f65ba9b16e934`。
控制输出 `build/realm-performance-20261018/retained-v30-r2-glmark.log`，wrapper 同 run-id。
**结果：完整 33 场景 957 分，对原 P30 957 为 0 / 0.00%；wrapper 与 runner 退出 0。**
Mali-G610/Panfrost，validation 26 成功 / 1 已知例外 / 6 unknown，意外失败和提交错误 0。
五类受检内核标记均未出现，IRQ `[1846327,49532]`，VM 退出 `[0,0]`。
Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载或 loop 遗留。
七份原始证据已回收到同 run-id 的 `GPU-SFTP/log/realm-xshm/` 并核对远端 SHA-256，
assessment 和 controller-verification 同目录；wrapper 前后资源和退出码按同 run-id 保存。
这验证了新构建入口和实际保留组合的完整运行，不能将无分差表述为正确性修复提分。
P30 首轮与此轮均 957，但包含独立正确性修复及重建，不能称为完全相同二进制的重复测试。

### 缓存开关修复的边界补充

后续只读审查确认 `completed_wait_cache` 是 0444 的只读模块参数，当前源码没有运行时赋值者。
因此 P31 局部测试中“关掉、变更、再开启”是直接修改 stub 状态的假设序列，
**并非当前正常接口可触发的安全漏洞**；此前笼统称为当前正确性缺口不准确。
F2 的 epoch 跟踪可抵御该假设序列，但缓存关闭且无法重开时没有实际消费者。
基线/P32 已测及运行中的冻结输入保持不变。控制机源码现已恢复缓存关闭时直接返回的原路径，
删除 F2 的无消费者跟踪与相应注释；F1 数组引用修复继续保留。
实际 wait/mutation helper 的 ASan/UBSan 检查及两个负对照通过，
Client 内核重建退出 0，实际重新编译驱动并生成 Image。
独立前后源码、补丁、检查/构建日志、Image 哈希与状态位于
`build/realm-performance-20261018/readonly-cache-tracking-cleanup/`。
**分数影响：未单独硬件测量，不宣称提分；缓存开启时的对照路径不变。**
本轮 P32 仍使用清理前的冻结输入，后续硬件验证须明确记录清理后的实际组合。
清理后组合已另存 `build/realm-performance-20261018/shadow-binary-v32-clean/`，
Client Image `5781d8738b6831684498fcbd6c80d87703628d6707087744d4a3c0753baa02e0`；其余三份运行输入与 P32 相同，未开始硬件测量。

## P32：以原生 point 快照承载本地 binary 对象（未命中）

**保留基线 957 → P32 955，-2 / -0.21%；新路径未命中，不保留为独立优化。**
固定 Mesa 25.0.7 的 `csf_attach_sync_points()` 在提交后将 VM timeline 的确切点
TRANSFER 到 context binary syncobj，再由后续 fence 导出路径创建第二份快照。
本轮把尚未物化的 binary 对象直接表示为那份不可变快照，导出只增加强引用，
消除“远端 mutable binary → 再次复制导出”的重复 RPC 与原生对象操作。
这延续已存在的本地 import/物化生命周期，不另建完成事件框架，也不修改 Mesa 或 benchmark。
参考 [固定 Mesa 源码](https://gitlab.freedesktop.org/mesa/mesa/-/raw/mesa-25.0.7/src/gallium/drivers/panfrost/pan_csf.c)
及 [Linux DRM syncobj 语义](https://docs.kernel.org/gpu/drm-mm.html#drm-sync-objects)；
实际语义核对以本项目固定内核的 `drm_syncobj_transfer_to_binary()` 为准。

- 新增协商能力 `POINT_SNAPSHOT`：请求包含真实源对象和 timeline point，复用原 Proxy 快照 handler、
  身份校验、源引用、私有对象、watch、槽位取消排空与原生 `drm_syncobj_transfer()`。
  完成页观察的是实际复制的完整 native fence，不能把最后一个 job 或数字序号当作完成。
- 只优化 flags=0、dst_point=0、非 self-transfer、未物化的目标；旧 peer、无完成页、
  已物化对象及其他 flags/目标 timeline 点仍走原路径。GPU 依赖和 WAIT_FOR_SUBMIT
  已绑定远端对象后不改变它的身份。
- Client 在目标 state_lock 下完成请求与原子替换；失败保留旧快照。
  导出在该锁下取得强引用，后续 source/目标复用不改变已经导出的 fence；
  快照没有 file 引用，不引入同文件循环引用。后续设备使用经现有路径先物化原生对象。
- pending、错误、无 watch 槽位均保持原生 fence/WAIT 回退；CPU 共享映射和通知的 RMM 授权路径不变，
  仍不声称 RK 上存在真实 GPT/GPC 保护或恶意 GPU 任务间隔离。

两侧构建均退出 0，日志 `build/realm-performance-20261018/shadow-binary-v32-build.log`。
实际 Client helper 的 ASan/UBSan 检查覆盖替换/导出强引用、错误保留、响应校验、无槽位、
能力/flags/物化回退及并发物化；实际 Proxy handler 检查覆盖源 point、身份拒绝、无效源先于分配、
原生错误清理及旧 wire 格式。四个负对照分别检测缺失导出引用、忽略原生错误、丢失 source point、
绕过 owner 校验。日志为 `shadow-binary-v32-{check,proxy-check}.log`。
底层 RPC/DRM/分配器使用 stub，不是完整驱动或硬件隔离证明。

冻结包 `build/realm-performance-20261018/shadow-binary-v32-v30/` 保存三个文件的独立增量、
58 份源码/哈希、完整组件 diff、HEAD、配置、已部署固件和构建/检查证据。
Client `ab601b54261256eae12b08b51743aa9ccb77724d9e34d0e03505d6fb20ae281b`，
Proxy `3bb0894d5dbb6f9629d1872b9b1b546499e5fa76f1ecb942ba77c9102f7d53c7`；
其余两份运行哈希与基线复测相同。其余源码与 RMM diff 核对不变。
回退三个文件至 `pre-shadow-binary-v32/`，保留 P25/P29/P30 与 F1/F2 正确性修复。
原发布补丁校验检测到已知定制 opencca-build diff；各固定 HEAD、补丁 SHA 与反向应用检查通过，
记录 `current-published-patch-audit.json`。本轮不重置源码、不更换固件，不将定制组合称为原发布组合。

基线终态并回收七份原始证据、确认 Host 恢复后执行以下完整 glmark；终态见下文：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-shadow-binary-v32-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/shadow-binary-v32-v30 \
  --workload glmark --performance --benchmark-only
```

控制输出为 `build/realm-performance-20261018/shadow-binary-v32-glmark.log`，
wrapper 与原始回收目录均按同 run-id 保存。只跑完整 glmark；按总分与正确性/健康/恢复
决定保留或撤回，不以 `shadow_transfers` / `reused_exports` 命中计数代替性能。

### P32 终态：955 分，两项新路径计数均为 0

run-id `realm-perf-shadow-binary-v32-glmark-20261018`，wrapper 与 runner 退出 0；
完整 33 场景 **957→955，-2 / -0.21%**，6 场景上升、6 持平、21 下降，terrain 42→39。
Mali-G610/Panfrost，validation 26 成功 / 1 已知例外 / 6 unknown，意外失败和提交错误 0，
GPU_SMOKE_RESULT=PASS。两 Realm 五类受检内核标记均未出现，IRQ `[1844793,51060]`，
VM 退出 `[0,0]`。Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载或 loop 遗留。
七份原始文件已回收到同 run-id 的 `GPU-SFTP/log/realm-xshm/` 并核对远端 SHA-256，
assessment/controller-verification 同目录，wrapper 前后资源及退出码按同 run-id 保存。

`shadow_transfers=0`、`reused_exports=0`，materialized=72，说明未实际走到新路径；
这轮仅证明旧回退路径能完整运行，**不能写成新 point/shadow 路径已获硬件验证**。
完成页 checks/hits/fallbacks=315592/314271/1321，RPC attempts=1797185；
对照基线为1802494，接近，不能评价未命中设计本身的性能。
P33 随后仍未命中，现已整体撤回 P32–P34 的三个 Guest 文件扩展，
保留真正有效的 F1 数组引用修复与只读参数跟踪清理，见文末撤回记录。

## P33：初始 signaled 对象导出保持本地表示（957 分，未命中，已撤回）

**保留基线957 → P33 957，0 / 0.00%；对 P32 955 为 +2 / +0.21%，未证明收益。**
固定 Mesa 25.0.7 `pan_context.c` 明确用 CREATE_SIGNALED 创建 context syncobj。
前端首次导出任何没有 snapshot 的对象都会物化它；一旦初始导出发生在首次任务前，
context 就永久落入 P32 的已物化回退路径。P33 在 state_lock 下确认
`client_handle=0 && snapshot=NULL && CREATE_SIGNALED` 时，直接导出本地 signaled fence。
这是创建参数确定的当前状态，不是由 job 序号、通知或完成推测而来。
一旦 import/transfer 存入快照、RESET/SIGNAL/设备依赖/WAIT_FOR_SUBMIT 等路径完成物化，
就不能再用 CREATE_SIGNALED 当作当前 fence 的证明，继续原生路径。
这是对 P32 未命中的具体原因假设，须由 `initial_exports` 及两个 shadow 计数实测确认，
不能在未命中前声称已优化实际工作负载。

本次整条导出函数检查还发现 P32 新分支会跳过 `session_id` 初始化，
后续同会话 import 会被拒绝。P32 未命中所以未在硬件暴露；现将初始化移入共用段，
并加入整条 export/cleanup 的检查。初始完成与 pending 快照都必须保留正确 session，
已导出 fence 不受随后替换影响；FD/分配/native capture 失败须释放引用且不形成文件循环。
这些正确性修复和 P33 初始状态改动按组合评价，不单独宣称提分。
另包含上述删除 F2 冗余跟踪，缓存开启的性能路径不变。

本地检查提取实际 helper 与完整 export/cleanup 函数，ASan/UBSan、`-Wall -Wextra -Werror`，
覆盖初始完成、已有 pending 快照、已物化后不复用创建标志、session 身份、并发物化、
失败保留和 FD/对象/文件引用清理；负对照覆盖缺失强引用、忽略 native 错误、
误用已物化对象的创建标志，以及未设置 session。日志为
`build/realm-performance-20261018/initial-binary-v33-{check,export-check}.log`。
底层 native DRM、RPC、workqueue 与 sync_file 用 stub，不是完整 DRM 或硬件隔离证明。
Client 构建退出 0，实际重新编译驱动并生成 Image，日志 `initial-binary-v33-client-build.log`。

冻结包 `build/realm-performance-20261018/initial-binary-v33-v32/`：
Client `8b2e681487af0c13ccf6626bb243f80fe938f1ff880f51777d34e8119f97a847`；
Proxy `3bb0894d5dbb6f9629d1872b9b1b546499e5fa76f1ecb942ba77c9102f7d53c7`，
initrd `b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`，
runner `feb2f56f2d5ccc2fae9fd3c7c9078cc330df8b176532708c1c3f65ba9b16e934`。
其他 57 份源码及 RMM diff/固件核对不变；独立补丁、全部源码/哈希/配置及检查/构建证据随包保存。
单项回退到清理后 P32 使用 `pre-initial-binary-v33/`；整体回退用 `pre-shadow-binary-v32/`，
然后恢复只读参数关闭时直接返回的原逻辑，不能再把无触发场景的 F2 跟踪带回。

已在 P32 终态、七份原始文件核对和 Host 恢复后执行以下命令，wrapper 与 runner 均退出0；完整 33 场景、频率/内存/绑核/诊断及 RMM 通信不变：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-initial-binary-v33-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/initial-binary-v33-v32 \
  --workload glmark --performance --benchmark-only
```

控制输出 `build/realm-performance-20261018/initial-binary-v33-glmark.log`，
wrapper 与原始证据按同 run-id 保存，终态及归因限制见下文。

## P34：只有独占引用时复用私有快照容器（未部署即撤回）

**分数影响：未执行，无有效成绩；P33 与保留参考均为957。P33 新路径未命中，本候选取消部署并撤回。**
P32/P33 的快照对象在每次更新后仍可能需要远端 DESTROY，再分配 native syncobj；
若新路径实际命中，独占引用复用可以进一步减少一次控制 RPC 和 native 对象分配。
当前只在控制机构建和冻结，保持 P33 运行输入不变。P33 若未解锁实际 shadow 路径，
本候选同样不会命中，应先撤回或重新设计，不能为了已有代码再盲测一轮。

- Client 持目标 `state_lock`，且旧快照 refcount 恰为1、对端明确广告 REUSE 能力时才发送旧 handle。
  导出、导入、等待及清理工作持有自己的强引用，任一引用存在均改为新建不可变快照。
  不改变现存导出 fence，也不忽略 flags、self-transfer、已物化及 timeline 目标的原生回退。
- 沿用原 POINT_SNAPSHOT wire 大小，把保留字段定义为可选 `reuse_handle`；
  旧 Client 仍发送0，新 Client 向不广告 REUSE 的 Proxy 也只发送0。
  Proxy 只允许同一认证会话的 private 目标，拒绝源自身、公开对象和无效 ID。
- native TRANSFER 成功后，才取消并排空旧 callback，再分配从不重用的 completion cookie。
  原生失败不提前破坏旧 native fence/watch；watch/槽位分配失败继续 native WAIT。
- **超时不等于远端没执行。** 复用请求超时、错误或响应损坏时，Client 在解锁前清除旧 expected cookie，
  保留该会话原生 handle，用权威 WAIT 观察当前状态；不能用旧成功 cookie 证明新 fence 已完成。
  仅成功且验证通过的同 handle 回复才将 native handle 所有权移给新 wrapper，
  旧 wrapper 清零 handle 后释放；错误清理不能双重销毁该 handle。

这依赖可信 Client 内核的真实引用记账；Proxy 的会话/VMID/私有目标校验约束跨 Realm 授权，
并不声称能替恶意的同一 Realm 内核证明它自己的导出语义。GPU job 已持有的 native fence 引用
不随容器重置而变化。RMM 内存授权、持久事件和可信 IRQ 路径未修改；物理 GPT/GPC 限制仍在。

两侧构建退出0，实际重新编译 Client/Proxy 并生成两个 Image，日志
`build/realm-performance-20261018/exclusive-snapshot-v34-build.log`。
四组实际函数检查及13个指定断言负对照通过：Client 复用/别名/错误/超时与所有权，
Proxy handler 的目标授权和成功后取消，真实 callback 取消排空/槽位复用，完整导出与清理。
源码与日志为 `exclusive-snapshot-v34-{check,proxy-check,callback-check,export-check}.{py,log}`。
其中底层 native DRM、传输、workqueue 或分配器按各组使用 stub，不是全 DRM、硬件隔离或性能证明。

冻结 `build/realm-performance-20261018/exclusive-snapshot-v34-v33/`：
Client `f28746e64c6bab0da36556deaf640e050476bc4b171d8c479b215bd364cc637a`，
Proxy `3294d4ba902be8cb4a231dae105b63073b2ec339fc3a87f80127603771176628`，
initrd `b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`，
runner `feb2f56f2d5ccc2fae9fd3c7c9078cc330df8b176532708c1c3f65ba9b16e934`。
其余55份源码与 RMM diff 不变，完整源码/哈希/HEAD/配置、独立增量、固件清单与检查/构建日志随包保存。
单项回退到 P33 使用 `pre-exclusive-snapshot-v34/`；整体 point/shadow 回退仍用前述三个文件的备份，
同时保留只读参数冗余跟踪的清理，不重新引入 F2。

以下为原拟议命令，因 P33 未命中而取消，**未执行**，保留以说明候选边界：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-exclusive-snapshot-v34-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/exclusive-snapshot-v34-v33 \
  --workload glmark --performance --benchmark-only
```

控制输出计划为 `build/realm-performance-20261018/exclusive-snapshot-v34-glmark.log`，
wrapper 与原始回收目录按同 run-id 保存。实际收益以完整分数、正确性和恢复为准，
不能仅以 `reused_transfers` 命中或 RPC 减少保留无收益代码。


## P33 终态与 P32–P34 整体撤回

P33 run-id `realm-perf-initial-binary-v33-glmark-20261018`，wrapper/runner 退出0，
完整33场景 **957→957，0 / 0.00%**（对保留基线）；12场景上升、4持平、17下降。
对未命中 P32 的955为 +2 / +0.21%，不能认定为新设计带来的收益。
validation 26成功 / 1已知例外 / 6 unknown，提交错误0，GPU_SMOKE_RESULT=PASS；
两 Realm 五类受检内核标记均未出现，IRQ `[1849374,50727]`，VM退出 `[0,0]`。
Host 恢复 pmthor、CPU 0–1、300 MHz，无实验进程、挂载或 loop 遗留。
七份原始文件已回收到同 run-id 的 `GPU-SFTP/log/realm-xshm/`，与远端逐文件 SHA-256 一致；
同目录保存 assessment/controller-verification；wrapper 前后资源与退出码在 `build/lab-runs/` 同 run-id 目录。

`initial_exports=0`、`shadow_transfers=0`、`reused_exports=0`，因此“初始 signaled 导出
导致提前物化”的假设未获本轮支持；不能把旧回退运行成功写成新增路径通过。
completion checks/hits/fallbacks=316354/315045/1309，pages=4，materialized=72；
普通回复 attempts=1803170、睡前完成1802671、ARM859，Proxy回复 sent51003/suppressed1799430。
Mesa 实际为25.0.7-2，Client/Proxy 驱动均 built-in；未采集到早期 OPEN_SESSION 能力日志，
现有日志不能确定未命中的具体原因，需核对真实调用及物化来源，不能继续依靠假设增加协议。

结论：**整体删除 P32–P34 未生效的协议、分支和计数器，P34 不部署。**
三个 Guest 文件从独立备份恢复，并移除无消费者 F2 跟踪；逐文件与已测原始 P30 源码完全相同。
保留原生 fence 完成页、P30等待预算、F1引用修复、P25调度优化及 RMM 授权/可信 IRQ。
撤回审计：`build/realm-performance-20261018/point-shadow-v32-v34-withdrawal.json`，
其中保存前后哈希及 P30 一致性；冻结候选与失败/未执行证据保留在 build，不留无效源码分支。

撤回操作本身没有新增硬件成绩；957是已测保留参考，不能给重新构建的镜像冒用该成绩。
当前距离1000门槛仍差43分，目标尚未达成。

撤回后规范构建 `bash scripts/build/build-verified-kernels.sh realm` 退出0，实际重新编译两侧驱动并安装运行树镜像；
构建日志 `build/realm-performance-20261018/point-shadow-v32-v34-withdrawal-build.log`。
冻结 `build/realm-performance-20261018/retained-clean-v30-after-v34/`，58份源码逐文件与 P30 一致，
已安装运行树镜像与冻结镜像哈希一致。该包尚未硬件测量，不把构建成功写成性能或硬件 PASS。


## 后续定位：P32 假设遗漏 CSF 初始化提交

固定 Mesa25.0.7 `pan_csf.c` 的 context 初始化在 `ctx->csf.is_init=true` 之前，
将 `ctx->syncobj` 用作实际 tiler/异常处理初始化提交的 SIGNAL，并调用 `drmSyncobjWait()`。
源码位置为本地固定参考 `mesa-25.0.7-reference/pan_csf.c:1483` 起，原始来源及 SHA 随参考文件保存。
Client GROUP_SUBMIT 会先物化所有同步对象，因此该 context 对象在常规渲染/首次导出前已物化。
这解释了为何只优化未物化目标的 P32/P33 与真实调用路径不匹配；这是固定源码路径分析，
不是由计数0反推已排除所有可能原因。此前“初始导出提前物化”不是得到硬件确认的根因。

## P35 参数对照：只对已经成功的原生 fence 免建快照

**分数影响：957→928，-29 / -3.03%；不启用该参数。**
不新增协议和运行代码，只开启已有 `panthor_client.completed_snapshot=1`。
Proxy 通过实际 `drm_syncobj_find_fence()` 取得强引用并检查成功状态，成功的 fence 不会重新变为 pending；
pending/错误继续原生快照，不以 job 序号、IRQ 到达或推测代替 fence 完成。
本轮使用撤回后重建的 P30 精确源码，镜像时间戳与此前957轮不同，不能称为相同二进制对照。

冻结 `build/realm-performance-20261018/completed-export-v35-v30/`，
Client `6997244b36a6ecc0d2b56971c642dab42aa9251af13556fba3c71660bcb1fce0`，
Proxy `7ddf53b93ea7ff9ee94edb365ce990dc85871c1ff473978dc233c82a20ddb984`，
initrd保持P30，runner `475e5ff66e3d10e437bb5a02669a693403d137667faf7880296ef531314daa27`。
命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-completed-export-v35-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/completed-export-v35-v30 \
  --workload glmark --performance --benchmark-only
```

控制输出 `build/realm-performance-20261018/completed-export-v35-glmark.log`；
wrapper和原始证据按同run-id保存，终态后回收、核对与统计，不覆盖失败或未执行。

## P36 候选：在真实 TRANSFER 时保留不可变导出快照

**分数影响：待终态；对照保留参考957，不含P35参数。**
该方案支持已经物化的公开目标，目标仍是真正的原生可变 syncobj；不是重新增加未命中的本地 shadow 分支。
目标是将实际 `TRANSFER → SNAPSHOT_WATCH` 两次往返合为一次：

- 只处理不同源/目标、binary目标点0、flags0的实际路径，其他情况和旧对端走原生 TRANSFER。
- Proxy持会话锁，先验证并引用源/目标，拒绝私有目标，再创建不可变私有对象。
  **只捕获一次源的精确 fence**，先把指定源点复制进私有对象，再从私有对象复制至公开目标；
  即使源并发替换，公开目标与返回的快照仍对应同一 fence。不重复读取可变源，也不改通用 DRM 核心。
- 私有分配失败继续普通 TRANSFER，成功回复不附快照；native失败释放私有对象且不提前改变目标。
  槽位不足仍返回不可变原生对象，使用权威 WAIT，不推测完成。
- Client使用既有只读缓存配置下的全局 mutation epoch：记录时必须只有本 TRANSFER 一个修改，
  记录前后epoch相等且未环绕；导出消费时必须无在途修改、epoch仍相等。
  不满足即释放可选证明、按原生导出；所有新修改默认使其失效。
  导出取得不可变引用后，后续 reset/transfer 不影响该旧 fence。证明只消费一次，不保留快照池。
- RPC超时/响应损坏不重试已可能执行的TRANSFER；可选Client包装分配失败不把已成功的TRANSFER改写为失败。
  同会话导入仍保留session身份，公开/私有引用及未导出对象关闭均释放，无DRM文件自引用循环。

能力bit4与独立 `TRANSFER_SNAPSHOT` 请求/回复协商；未修改 RMM 授权、事件和IRQ。
创建helper拆为持锁主体与原有包装，便于整个融合操作内私有对象始终不被并发删除或猜测重用。
原生GPU固件/页表/调度源码不变，当前硬件GPT/GPC限制亦不变。

两侧规范构建退出0，实际重新编译Client/Proxy驱动并生成Image。
两组局部检查提取实际Client TRANSFER、缓存、完整export/cleanup与Proxy服务/handler，
ASan/UBSan及8个负对照通过：源重复读取、提前发布、私有目标、跳过owner校验、epoch/并发失效、
session初始化、未导出快照释放。覆盖已物化目标、同源精确快照、可选分配失败、native错误、
超时不重试、槽位不足、旧对端/timeline回退及FD失败清理；底层DRM/传输/分配等使用stub，
不是完整DRM或硬件隔离证明。证据 `fused-transfer-v36-{client,proxy}-check.{py,log}`，
构建日志 `fused-transfer-v36-build.log`，均位于 `build/realm-performance-20261018/`。

冻结 `build/realm-performance-20261018/fused-transfer-v36-v30/`：
Client `2a4b2c0c2034ac9640a630f37658eb2fc912cff654b750bf3e8a423333621662`，
Proxy `058d4de7af408e1517c97df4df35aeac08828f8cbca02c174978f5e82ad115fa`；
initrd `b2bb563907a832d50251b4e9ad304cdc07acbe6fe38ff4e50c7e01318237ffc7`，
runner `feb2f56f2d5ccc2fae9fd3c7c9078cc330df8b176532708c1c3f65ba9b16e934`。
其余55份源码及RMM diff、固件、配置与P30核对一致；完整源码、独立补丁、哈希与证据随包保存。
回退使用 `pre-fused-transfer-v36/` 三个文件。P35终态并收齐原始证据、确认Host恢复后，
才可运行完整glmark；以实际路径命中、总分、正确性/健康/清理共同判断，未获有效收益即删除扩展。


### P35 终态：928 分，不启用参数

run-id `realm-perf-completed-export-v35-glmark-20261018`，wrapper/runner退出0，
完整33场景 **957→928，-29 / -3.03%**。renderer Mali-G610/Panfrost，validation26/1/6，
提交错误0，GPU_SMOKE_RESULT=PASS；两 Realm五类受检内核标记均无，IRQ `[1920946,47119]`，
VM退出 `[0,0]`。Host恢复pmthor、CPU0–1、300 MHz，无实验进程/挂载/loop遗留。
七份原始文件已回收到同run-id的 `GPU-SFTP/log/realm-xshm/`，远端SHA逐一核对，
assessment/controller-verification随原始证据保存，wrapper前后资源及退出码按同run-id归档。

completed_exports=197，而lazy_discards=306580，绝大多数导出没有避开原生快照；
materialized=269，比参考72增加197：完成导出的后续导入走原生signal路径，也带来额外物化。
RPC attempts=1882577（参考1802494），cache_hits=218976（参考352759），
cache_miss_epoch=160439（参考36535）；这些为时序/调用变化证据，不能认定197次快捷路径是退分的唯一原因。
完成页 checks/hits/fallbacks=306580/305266/1314。未追加逐RPC计时轮，不将计数下降或上升直接换算成总分。
本次只修改冻结runner参数，不提升为规范配置，也不将该参数叠加到P36。

### P36 已启动，保持独立对照

在P35终态、七份原始证据核对及Host恢复后，启动：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-fused-transfer-v36-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/fused-transfer-v36-v30 \
  --workload glmark --performance --benchmark-only
```

控制输出 `build/realm-performance-20261018/fused-transfer-v36-glmark.log`，
wrapper和原始证据按同run-id保存。分数、校验、路径计数及恢复均待本轮终态，不沿用此前PASS。
最终负对照额外校验失败断言位置，`fused-transfer-v36-{client,proxy}-check-final.py` 及
`client-check-final.log`/`proxy-check-final-r2.log`随冻结包保存；一次负对照预期断言文本不匹配
已修正，初次检查日志保留，未改变运行源码或镜像。


IRQ局部性审查（只读，未改变正在运行的P36配置）：Host `/proc/interrupts` 的 GPU job/mmu/gpu
分别为IRQ77/78/79，effective affinity均为CPU0；当前Proxy固定CPU1。
Host `pmthor_automasked_irq_handler()` 经eventfd触发KVM IRQ，存在值得测量的跨核注入可能。
但旧1058配置 `configs/performance/glmark-clientproxy-opp3.env` 同样是Proxy1/Client2，
CPU0放broker；因此**不能把该布局当作新旧差距的已确认根因**。
若后续测试绑核或IRQ局部性，必须单独记录条件变化及分数，不混入P36源码对照。
本次对总表标题/当前摘要的整理未修改运行代码，无新增性能测量。


### P36 终态：951 分，融合路径实际命中但整体撤回

run-id `realm-perf-fused-transfer-v36-glmark-20261018`，wrapper/runner退出0，完整33场景 **957→951，-6 / -0.63%**；
4场景上升、3持平、26下降，terrain42→36（-14.29%）、blur212→192（-9.43%）。
Mali-G610/Panfrost，validation26/1/6，提交错误0，GPU_SMOKE_RESULT=PASS；
两Realm五类受检内核标记均无，IRQ `[1563699,52705]`，VM退出 `[0,0]`。
未见 delayed SYNCOBJ_DESTROY failed 或 transfer snapshot response lost；
Host恢复pmthor、CPU0–1、300 MHz，无实验进程/挂载/loop遗留。
七份原始证据已回收至同run-id的 `GPU-SFTP/log/realm-xshm/`，与远端SHA逐一核对；
assessment/controller-verification与wrapper前后资源按既有目录归档。

`transfer_snapshots=377584`、`transfer_exports=314188`，本次证明实际路径运行，不能再归因于未命中。
但有63396次快照没有直接用于导出：每个batch的TRANSFER不都对应一次export，提前捕获增加了部分
native对象、callback及销毁工作。RPC attempts从1802494降到1516632（-15.86%），
总分却没有提高，说明**减少同步控制往返不能直接换算成吞吐提升**；未收集分段时序，不能把
额外快照或CPU/GPU重叠时序认定为唯一退分原因。
completion checks/hits/fallbacks=314220/312994/1226，materialized仍72；
Proxy回复sent53065/suppressed1512065，任务计划runs377321。

三次只读采样覆盖计时130/160/190秒，Proxy/Client固定CPU1/CPU2，A55频率均1.8GHz、
littlecore温度约53℃，物理GPU IRQ有效CPU0；日志 `fused-transfer-v36-irq-locality-samples.json`。
这些是有限样本，不是全程无瞬态降频的证明。

结论：**不保留新增复杂度，整体撤回P36。** 三个Guest文件从 `pre-fused-transfer-v36/` 恢复，
与P30逐文件完全相同；删除协议、快照缓存/计数器、handler及创建函数拆分。
RMM共享授权/可信IRQ、完成页、P30预算、P25调度和F1修复保留。
撤回审计 `fused-transfer-v36-withdrawal.json`，规范双侧重建退出0，
日志 `fused-transfer-v36-withdrawal-build.log`；重建本身未新增硬件成绩，不冒用957分。

## P37 独立配置对照：Proxy放到物理GPU IRQ所在CPU

**分数影响：957 → 944，-13 / -1.36%；不采用。**
仅将Proxy从CPU1移到CPU0，Client仍CPU2，在线CPU0–3及相同A55核心不变。
不改频率、vCPU数、内存、glmark/场景/验证、不写IRQ affinity，不含P35/P36。
该测试验证中断转发局部性的收益，不能用于声称代码架构的单项因果改进，也不能把旧1058的Proxy误记为CPU0。

冻结 `build/realm-performance-20261018/irq-locality-v37-v30/`：
两侧镜像与P35参数实验所用clean镜像逐位相同，源码58份与P30相同；
initrd保持P30，runner `a9cee4707cf9b80aa6ee81ec0e6b355ad87b98125095e0a8ee505738c5516dd9`。
runner只有绑核表达式的一行差异，已做Python语法检查；未改变规范runner或P36冻结输入。

P36终态、七份原始证据核对及Host恢复之后，已启动：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-irq-locality-v37-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/irq-locality-v37-v30 \
  --workload glmark --performance --benchmark-only
```

控制输出 `build/realm-performance-20261018/irq-locality-v37-glmark.log`，wrapper/原始证据同run-id；
终态：wrapper/runner退出0，33场景944分，validation 26/1/6、意外失败与提交错误0；两侧五类内核故障均无，可信IRQ为1822879/45433，VM退出[0,0]。Host恢复pmthor、CPU0–1、300 MHz，无本轮进程/挂载/loop残留。七份原始文件已回收并逐一核对远端SHA，assessment与wrapper前后检查同run-id归档。
RPC attempts=1796344，completed_before_sleep=1795680；回复sent45751/suppressed1778319。该配置没有提分证据，不改规范runner。

## P38 候选：提交回复附带原生 timeline 精确完成凭据

**分数影响：957 → 962，+5 / +0.52%；未证明稳定收益，暂只作为P39对照。** 不包含P35/P36/P37。

P36说明仅减少重叠阶段的RPC不足以提分；本轮针对CPU首次查询新timeline point仍需RPC的问题。
原生GROUP_SUBMIT在返回前已安装输出fence，Proxy持有该point的完整原生chain引用，通过既有完成页发布唯一cookie。
没有额外创建shadow syncobj，不修改原生输出对象，提交回复协商扩展16字节；旧peer保持原16字节回复。
仅有一个非零timeline SIGNAL时尝试，分配/槽位/捕获失败保持原生提交成功并退回RPC。

Client只允许单对象、精确point、非阻塞WAIT_ALL命中；不是进度水位。
已知TRANSFER/import/reset/signal只使目标凭据失效，未知写入、VM_BIND/GROUP_SUBMIT使全部凭据失效；旧完成查询缓存不放宽。
提交捕获开始和结束都须是唯一写入者，且期间原mutation epoch不变；任一并发写入、wrap、陈旧cookie或错误均回退。
callback沿用原生锁内只读error、成功才发布cookie，重用slot之前必须取消并等待旧callback结束。
RMM授权、可信通知、完成页权限与Host/固件不变。

四份源码回退保存在 `build/realm-performance-20261018/pre-submit-proof-v38/`。
首轮构建失败（调度取消分支残留旧回复字段）保留 `submit-proof-v38-build.log`，修正后重建中；无有效硬件成绩。

P38最终双侧构建退出0，日志 `submit-proof-v38-build-final.log`；本地ASan/UBSan检查
覆盖实际watch/cancel/read、Client timeline wait/失效/记录与plan RPC、Proxy plan execute/handler，
12项负向控制均被对应断言拒绝；实际native与RPC使用桩，不代替硬件/完整内核并发验证。
另外审计了已复制参数和已持有引用上的目标失效调用位置。
首轮测试harness的负向错误检查因unused参数编译失败，修正harness后通过；失败日志保留。

冻结 `build/realm-performance-20261018/submit-proof-v38-v30/`，包含四文件差异、58文件哈希、
两个Image、相同配置、固件清单、local检查与构建日志。54份其他源码和RMM patch均与P30逐位相同。
补丁清单检查仍报已知 `opencca-build: changes differ from the published patch`；未重置自定义工作树，
本轮不刷固件，RMM未改变。
Client Image `ad416f184469783537bdb4707a04eafa7aa12a3b8e0ebeb3e2c3feb60eaa0f5a`，
Proxy Image `9d2ca23d890d68cd34edfee93389af396f3a86f91cd3ec1566e576522791cdd6`。

P37证据归档与Host恢复后启动完整glmark：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-submit-proof-v38-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/submit-proof-v38-v30 \
  --workload glmark --performance --benchmark-only
```

控制日志 `build/realm-performance-20261018/submit-proof-v38-glmark.log`；
wrapper及原始证据同run-id。终态wrapper/runner退出0，33场景962，validation26/1/6、提交错误0；受检五类内核错误均无、IRQ1828277/47550、VM退出[0,0]；Host恢复pmthor、CPU0–1、300MHz，无本轮进程/挂载/loop。七份原始文件已回收并核对远端SHA。

设计依据：Linux [DRM syncobj 文档](https://kernel.org/doc/html/v6.10/gpu/drm-mm.html#drm-sync-objects)
将timeline描述为持有先前chain与当前driver fence的链；TRANSFER按指定point转移fence，binary使用point0。
因此实现保留本项目固定内核的 `drm_syncobj_find_fence(..., point, 0, ...)` 返回引用，
不把最后一个job完成等同于整个point完成，也不自行推导较小point的完成。
[Virtio 1.3 GPU 规范](https://docs.oasis-open.org/virtio/virtio/v1.3/virtio-v1.3.pdf)
同样用fence ID关联请求与完成，说明完成身份需要进入设备协议。
P38采用“提交接受回复 + 此后完成页cookie”两步，保持CPU/GPU异步重叠；cookie只标识一次精确原生fence，
不直接套用Virtio的timeline序号或前缀完成规则。这是成熟同步思想在现有Realm代理路径上的尝试，
单项不宣称论文级新颖性，性能是否有效取决于完整实测。

### 本轮追加的旧1058逐场景差距复核

按历史 `opp3-final-comparison.json` 的完整33场景，与保留组合957重新匹配；
生成 `build/realm-performance-20261018/realm-perf-retained-v30-r2-glmark-20261018-vs-old1058.json`。
refract 161→130（-19.25%，每帧+1.478ms）、shadow 779→633（-18.74%，+0.295ms）、
terrain 51→42（-17.65%，+4.134ms）、blur 256→212（-17.19%，+0.823ms）；
部分短帧条件/循环场景约-12%。分差不是统一的固定毫秒数，但场景的作业数量和同步次数也不同，
不能仅由该表排除RPC或认定GPU本体变慢。旧/新内存、Realm、broker、Host启动差异保留，
此为历史差距描述，不是同期单因素因果试验；本次整理没有新性能成绩。

源码另确认：`realm_xshm.c` 数据池CMA分配当前只要求页对齐，`xshm_rtt.c` 目标共享映射
逐4KiB页安装并失效TLB。大页/批量映射是后续可研究方向，但未测到TLB瓶颈，
且必须保留granule所有权、撤销和权限不变量；本轮没有为此改动任何RMM/映射代码。

P38新增记录384862次、检查54282次、命中54257次，即每条记录对应成功命中约14.10%。
RPC attempts=1786889，相对保留参考1802494只少15605（-0.87%）；
旧完成缓存hits=317071、miss_point=375244、miss_epoch=43890。
原生私有快照完成页命中316591/317910，materialized仍72。
逐场景有升有降：build VBO1406→1505（+7.04%）、无VBO923→990（+7.26%），
terrain42→38（-9.52%）、blur212→207（-2.36%）。不能只凭局部场景或5分总分确认稳定收益。

## P39 候选：完整原生timeline chain的较早点完成证明

**分数影响：P38的962 → 1022，+60 / +6.24%；保留参考957 → 1022，+65 / +6.79%。两轮1022、1022，同输入复测通过。**
只改Client的原生chain完成页判断与新增prefix命中计数；Proxy、RMM、协议、完成页和测试条件不变。
P38只允许请求point等于捕获point；本轮允许正数请求point小于或等于已完成捕获point。
旧的RPC查询缓存仍只允许精确point，不改变P31撤回结论。

该扩展的前提是 `drm_syncobj_find_fence(...,捕获point,...)` 返回的完整native chain已经完成，
且目标未被后续写入。固定内核 `dma-fence-chain.c` 的signaled遍历所有未回收祖先，
walk只回收已完成节点；给定上界的chain完成后，更早有效正point的原生查询也完成。
因此仅使用P38已有的同对象、同proof epoch、无writer、精确cookie、目标写入清空规则，
不使用单job、GPU计数器、全局序号或跨对象水位。未来point仍需RPC。

抽取固定内核实际get/walk/find/signaled函数，覆盖460次可完成捕获中的19855次较早点查询，
以及未完成祖先、序号缺口、context变化、重复point、GC与未来point拒绝；负向控制证明
跳过祖先完成检查会失败。检查日志 `native-prefix-v39-check.log`，顺序RCU/引用桩不代替内核并发验证。
Client实际记录/查询/失效函数检查及5个负向控制通过，日志 `native-prefix-v39-client-check.log`。
代码回退到P38可用 `pre-native-prefix-v39-client.c`；若P38/P39均无实质收益，整体撤回四文件扩展。
构建日志 `native-prefix-v39-build.log`，双侧构建退出0；下文记录首轮硬件终态及复测。

P39双侧规范构建退出0（`native-prefix-v39-build.log`）；冻结时Proxy明确沿用P38原镜像，
从而只替换Client，源码其余57份与P38完全相同，RMM patch逐位相同。
冻结 `build/realm-performance-20261018/native-prefix-v39-v38/`；
Client Image `9124314c7758bce5e1fa96e33c3591f12cc709101d0717d2c27eb1d0666e37ea`。
P38原始证据回收/核验并确认Host恢复后启动：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-native-prefix-v39-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/native-prefix-v39-v38 \
  --workload glmark --performance --benchmark-only
```

控制日志 `build/realm-performance-20261018/native-prefix-v39-glmark.log`；
wrapper/原始证据同run-id。终态wrapper/runner退出0，33场景1022，validation26/1/6、提交错误0，两个Realm五类受检内核标记均无；可信IRQ1570201/54964，VM退出[0,0]。Host恢复pmthor、CPU0–1、300MHz，无本轮进程、挂载或loop。七份原始文件已回收并逐一核对远端SHA。

P39相对保留参考33场景为30升、3平、0降；shadow633→702（+10.90%）、
ideas387→420（+8.53%）、bump normals1493→1615（+8.17%），terrain42→42。
相对P38为30升、2平、1降（build VBO1505→1504，-0.07%），不能把每项小差异视为显著。

新完成凭据records/checks/hits=410046/840487/749915，
prefix命中695483，精确point命中54432；这说明本次扩展实际覆盖了大量较早点查询。
旧精确查询缓存命中20488；两种本地命中和native非阻塞查询分别749915+20488+71308=841711候选。
实际timeline WAIT转发71337（其中单非零point71337），相对P38的419168大幅减少。
RPC attempts从保留参考1802494降到1520394（-15.65%）；
completed_before_sleep1519917、arms830，回复sent55211/suppressed1516197。
私有快照完成页命中336261/337626，materialized仍72。
这是实际完成凭据替代CPU查询的证据，不能由RPC次数直接换算总分或声称所有开销都已消除。

首轮终态与原始证据核验后，已启动同一冻结输入复测，未修改任何运行代码/参数：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-native-prefix-v39-r2-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/native-prefix-v39-v38 \
  --workload glmark --performance --benchmark-only
```

复测控制日志 `build/realm-performance-20261018/native-prefix-v39-r2-glmark.log`；
未重建镜像，使用相同hashes。复测终态完整33场景仍为 **1022分**，
对957为+65/+6.79%，对首轮为0/0.00%。wrapper/runner退出0（00:11:00.732633Z至00:19:44.015777Z），
validation26/1/6、提交错误0；两个Realm五类受检内核标记均无，可信IRQ1576510/56603，VM退出[0,0]。
Host恢复pmthor、CPU0–1、300MHz，无本轮进程/挂载/loop；七份原始文件已回收并校验SHA。
相对957场景29升/1平/3降，相对首轮13升/3平/17降；
总分可重复不等于各场景稳定不降，terrain42→40，两个buffer46→45。
复测RPC attempts1524089（对1802494为-15.45%），before_sleep1523599、arms876；
point_records409099、checks838605、hits754288、prefix_hits699723，
实际timeline WAIT79521，私有快照命中336216/337580、materialized72。
P38+P39作为有效组合保留，不将P38单独的5分归为已证明收益。
相比旧普通VM1058仍差36分/-3.40%，旧新环境差异仍适用，不写成同期单因素结论。
尚未恢复API/计算/多Client/完整回归；先验证本轮成绩的可重复性，并继续缩小与旧1058的差距。


## P40 候选：复用完成回调对象，清理旧接口

**分数影响：1022→1024，+2 / +0.20%；单轮不足以证明稳定且值得增加复杂度的收益，复用逻辑已撤回。只保留无调用者接口清理，该清理不单独宣称提分。**

P39首轮有410046次完成凭据记录。原实现替换同一公开syncobj的watch时，
先排空回调、释放对象和slot，再重新分配；P40在相同会话锁下排空旧回调后，
保留分配对象和slot，重新初始化completion、清空发布值，并生成从不复用的新cookie。
新原生fence获取失败或回调注册失败时释放保留对象，继续正常无凭据路径；
私有快照对象仍按自身生命周期创建/释放，不引入池、开关或额外缓存。
原生回调仍只发布无错误的完整chain完成状态，RMM授权共享内存和可信IRQ路径不变。

同时删除已没有调用者的 `panthor_vmshm_syncobj_fence_get()` 包装函数及声明；
实际使用者都调用支持point的 `_get_at()`，私有快照传point0。
该删除是接口清理，不单独宣称性能收益。

局部检查命令 `python3 build/realm-performance-20261018/watch-reuse-v40-check.py`，退出0；
日志 `build/realm-performance-20261018/watch-reuse-v40-check.log`。
抽取实际回调、排空、注册和Client读取辅助函数，配合native fence/pthread桩及ASan/UBSan，
验证分配被拒绝时同对象/slot仍能复用、旧pending和进行中回调先排空、
失败查找回收、错误fence不发布、旧cookie拒绝、64slot耗尽及原有等待边界。
三个负例分别删除排空、放宽cookie匹配、允许错误状态发布，均触发对应断言。
这些是局部实现证据，不是完整内核并发或硬件隔离证明。
双侧构建已退出0，日志 `build/realm-performance-20261018/watch-reuse-v40-build.log`；
冻结输入 `build/realm-performance-20261018/watch-reuse-v40-v39/`，Client镜像/runner/initrd/配置与P39完全一致，
只替换Proxy镜像（SHA-256 `7418fc6d0bfd9434b3ba981b8142f203524287808294cd5343b8919e28a9964f`）。
55份其余跟踪源码及RMM补丁与P39一致；删除的头文件声明不改变Client执行代码。
Client完成凭据/失效检查与Proxy计划执行/协商局部检查复跑通过（`watch-reuse-v40-{client,proxy}-check.log`）。
补丁清单检查仍为已记录的自定义opencca-build diff，未重置已应用补丁。
硬件部署与完整33场景成绩待记录；无收益则撤回复用逻辑，
仅保留删除无调用者接口的清理，并重新验证最终载荷。


P39复测证据回收与资源恢复核验后，启动P40单一硬件测试：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-watch-reuse-v40-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/watch-reuse-v40-v39 \
  --workload glmark --performance --benchmark-only
```

控制日志 `build/realm-performance-20261018/watch-reuse-v40-glmark.log`，
wrapper与原始证据目录同run-id。终态wrapper/runner退出0，完整33场景1024；validation26/1/6、提交错误0、
两个Realm五类受检内核标记均无，可信IRQ1576916/41503，VM退出[0,0]。
Host恢复pmthor、CPU0–1、300MHz，无本轮进程、挂载或loop；七份原始文件已回收并逐一核对SHA。
未启动其他矩阵或并行硬件测试。回退源码在控制机构建目录 `pre-watch-reuse-v40/`。


## P41 候选：成功同步日志只保留首次 marker

**分数影响：1022→1023，+1 / +0.10%，未证明性能收益。只作为日志清理保留，不把差值归为已验证的提分。直接对照P39两轮1022，不含P40复用，附带无调用者接口清理。**

P39第二轮 live console（只统计以`[time]`开头的行，排除`<N>[time]`的kernel-log副本）中，
Proxy TRANSFER/DESTROY的限流抑制计数累计402092/332268，CREATE另17。
数据在 `build/realm-performance-20261018/native-prefix-v39-r2-rate-suppressed.json`。
这只是触发限流路径的次数下界，不是时间占比证明。固定内核 `include/linux/printk.h`
与`lib/ratelimit.c`显示：`pr_info_ratelimited`即使不打印也调用`__ratelimit`，
尝试获取带irqsave的自旋锁、读jiffies及累计missed，并每窗口打印抑制摘要。

候选将Client DESTROY/TRANSFER和Proxy CREATE/DESTROY/TRANSFER五个成功日志点改为`pr_info_once`，
使用内核已有一次性日志机制，避免逐次限流锁和周期摘要；不引入新开关、计数框架或私有缓存。
原计划用debug日志完全关闭成功输出，但检查发现 `run-vmshm-e2e.sh` 的独立API测试
仍要求这些marker，因此保留每个调用点启动后的首次成功日志，格式不变，未删除测试断言。
Client CREATE原有首次物化日志未改。错误销毁告警不变；Proxy TRANSFER失败改为单独WARN限频，
不消耗首次成功marker，错误errno及响应原样返回；其他校验/提交诊断/内核健康统计不变。
此修改只处理日志路径，不能把减少日志当作GPU或通信提速证据。

初步debug版本构建退出0，但因上述marker消费者不部署；证据
`quiet-sync-v41-build-preliminary.log`保留。最终once版本双侧构建已退出0，日志
`build/realm-performance-20261018/quiet-sync-v41-build.log`；基线、镜像、完整测试命令和分数待终态。
这是日志修改，不新增镜像实现的单元测试；以差异审阅、内核构建、实际marker与完整性能结果验证。


P40相对P39第二轮33场景为24升/4平/5降，build非VBO1008→1018（+0.99%），
terrain40→41（+2.50%），但相对首轮42仍低；ideas421→419（-0.48%），
conditionals vertex-steps5 1367→1353（-1.02%）。总分2分差不足以支撑稳定收益结论。
RPC attempts1541911，高于P39复测1524089；point_records410250/checks840805/hits754713/prefix699768。
私有快照完成页336894/338260命中、materialized72。没有新增分配计数，
局部测试证明了实际复用能力，但不能把它换算成硬件分配次数或节省时间。
回退后callback/watch辅助函数逐字节等于P39，额外disarm/reinit复用分支已删除；
原生/header中无调用者的point0包装接口删除保留，其符号已不在新Proxy vmlinux中。

P41最终基线由P39+上述接口清理构成，再加入五个首次成功日志点；
初次once构建仍包含P40复用，没有部署该中间输入。撤回复用后双侧再次构建退出0，
最终日志 `build/realm-performance-20261018/quiet-sync-v41-build-final.log`。
实际watch辅助函数及Client凭据检查复跑通过，日志`quiet-sync-v41-final-{watch,client}-check.log`；
冻结包`build/realm-performance-20261018/quiet-sync-v41-v39/`保存58份源码哈希、补丁、构建与来源证据。
相对P39只有四个Guest文件不同，其余54份源码、RMM补丁/固件、runner/initrd/配置保持一致。
Client/Proxy镜像SHA-256分别为
`0dfcc89e63205aec00f69ebc81baee13aa61e74e721bb9d775655c11fe01ec57` /
`da7ae1e0adf249fe4f05601ad5e5506f8d97d40b3804c655e4213f343cf6e6d4`。

P40原始证据回收和Host恢复核验后执行：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-quiet-sync-v41-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/quiet-sync-v41-v39 \
  --workload glmark --performance --benchmark-only
```

控制日志`build/realm-performance-20261018/quiet-sync-v41-glmark.log`，
wrapper/原始证据目录同run-id。运行中，成绩、退出码、健康与恢复待终态；
每次启动仍获取单一硬件独占锁，没有与P40重叠。


### P41终态与边界

run-id `realm-perf-quiet-sync-v41-glmark-20261018`，wrapper/runner退出0，
00:29:16.683593Z至00:37:59.262160Z。完整33场景1023，validation26/1/6、提交错误0，
两个Realm五类受检内核标记均无，可信IRQ1578220/54496，VM退出[0,0]。
Host恢复pmthor、CPU0–1、300MHz，无本轮进程、挂载或loop；七份原始文件已回收并核对远端SHA。
RPC attempts1527335、before_sleep1526980、arms792；回复sent54694/suppressed1524547。
相对旧普通VM1058仍低35分/-3.31%，仍只作不同环境的目标差距。

实际live console中的三个旧Proxy限流摘要均消失。原始日志保留Proxy CREATE/DESTROY/TRANSFER
的首次marker（kernel-log副本重复出现），但Client相应INFO marker未留存在最终采集内容；
因此只证明日志抑制摘要消失，不声称已完成独立API marker兼容性硬件回归。
源码首次marker格式保留，专门API矩阵仍暂缓。日志审计在`quiet-sync-v41-log-audit.json`。
保留此改动是移除正常路径的逐次限流检查，不添加新诊断开关/框架；不宣称这1分是其性能收益。

## P42候选：下一次导出顺带回收已退休快照

**分数影响：同镜像两轮1023→1159、1163，+136～140 / +13.29～13.69%；相对P39的1022为+137～141 / +13.41～13.80%。高于旧普通VM1058为+101～105 / +9.55～9.92%，但旧环境不同，不能归因于单一改动。两轮复现，保留P42；当前Realm路径功能验收已通过。**

当前每帧在提交/转移/导出之外还可能单独发送私有快照DESTROY。
P39完成页已使私有等待约99.6%在Client完成，而P15历史试验仍有大量原生WAIT且每提交约8次RPC；
所以当前请求组成已改变，值得独立验证减少销毁往返。
本候选没有恢复P15旧快照对象池，也不叠加P36每次TRANSFER提前创建快照的多余分配。

- 只有私有快照的最后一个Client引用释放后，才把其句柄放入本会话最多8项的待回收队列。
  dup、import别名或等待者仍持引用时不入队；队列满立即走原有DESTROY。
- 队列保存在既有引用计数completion-page**本地包装对象**，不写入共享完成页，也不增加file引用环。
  每次新的快照导出将待回收句柄带入56字节`SNAPSHOT_RETIRE`请求，然后仍创建新的原生快照并捕获完整fence。
- Proxy先按RMM channel身份查找session并保留源对象，再在会话锁下校验整批句柄：
  同会话、private、非零、非源、无重复、数量≤8。所有校验通过后才移除名字并失效相关计划。
  已有原生/任务引用继续持有其fence，不把删除名字等同GPU工作完成。
- 整批校验失败不产生部分回收；但回收成功后新快照创建仍可能失败，**整条RPC不是回滚事务**。
  Client对取出的回收批次不重放；超时或响应失败也不重试快照创建，避免重复执行。
  未收到的回收请求由session关闭清理，仍受既有4096对象限额约束；不声称所有失败下只残留8个对象。
- postclose先关闭队列并逐项flush，再做本地资源释放和CLOSE_SESSION；之后的最后引用释放走直接DESTROY。
  旧peer、无完成页、未启用fused snapshot时保持原路径；使用新feature bit7与独立消息号，不复用已撤回实验的能力位。

`SNAPSHOT_RETIRE_STATS`的queued是Client入队数、sent是取出并尝试随请求发送的句柄数，
不是对端成功确认数；close是关闭时单独flush数，fallback在关闭打印时采样。
Proxy已有TASK_PLAN_STATS新增retired_snapshots，表示通过校验并移除名字的数量，
不表示所有fence已释放。两者和RPC attempts、正确性、清理一起判断是否值得保留。
RMM代码、固件、共享页权限、完成cookie发布/判定及既有GPU fence语义不改。

设计借鉴成熟接口的两个原则：
[Linux DRM同步对象文档](https://kernel.org/doc/html/v6.10/gpu/drm-mm.html)区分可变syncobj和导出时捕获的fence引用；
[Virtio 1.3草案规范](https://docs.oasis-open.org/virtio/virtio/v1.3/virtio-v1.3.pdf)包含批量处理buffer/通知的机制。
这里将批量化用于本项目控制请求中的回收附带，是设计借鉴，不声称实现Virtio或提出独立论文创新。

局部检查执行实际C辅助函数/处理器，native/运输/引用与锁的部分底层使用桩，ASan/UBSan：
`retire-v42-check.py`、`retire-v42-protocol-check.py`、`retire-v42-handler-check.py`。
日志分别`retire-v42-check-final2.log`、`retire-v42-protocol-check.log`、`retire-v42-handler-check-final2.log`，
全部退出0；覆盖实际last-ref put、8项上限/溢出/关闭、enqueue/take并发守恒、整批非法项不修改、
公开对象/跨会话/重复/源句柄拒绝、保留外部引用、16/32字节旧回复与新32字节回复、
原生创建/转移失败、失去响应不重试。七个负例故意提前回收、允许public/重复/源、忽略owner、
跳过回收或重放失去响应的请求，均被检查捕获。此为局部实现证据，不是完整内核并发或硬件隔离证明。

两侧内核最终构建退出0，日志`retire-v42-build-final2.log`；前次构建/修改计数前构建日志也保留。
冻结输入`build/realm-performance-20261018/retire-v42-v41/`，58份跟踪源码中只四个Guest文件改变，
其余54份及RMM补丁不变，initrd/runner/配置/固件与P41相同。
Client/Proxy SHA-256：`bd823f88df688c98140c3d852fc19d84fd6a1523b3dfe34eb00a4ac961d126b1` /
`198ee612bdaa6c7a6000173cb0ad7cf8220ec89b24ee71eb4517724969e703ea`。
回退源在`build/realm-performance-20261018/pre-retire-v42/`，无收益则完整撤回这四个文件的候选增量。

P41证据归档与Host恢复后执行：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-retire-v42-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/retire-v42-v41 \
  --workload glmark --performance --benchmark-only
```

控制日志`build/realm-performance-20261018/retire-v42-glmark.log`，wrapper/原始证据目录同run-id。
首轮已正常结束；以下记录首轮证据与同镜像复测，未并行运行其他硬件测试。


### P42 首轮终态与同镜像复测

`realm-perf-retire-v42-glmark-20261018`：wrapper/runner退出0，VM退出码[0,0]；
Mali-G610 renderer，完整33场景1159，validation为26成功、1已知framebuffer例外、6无判据，
无unexpected failure或submission error；五类受检内核故障均无事件。
相对P41有29个场景上涨、4个持平、0个下降；buffer与refract等仍基本不变，不能声称消除全部瓶颈。

主渲染会话：Client queued=382748、sent=382747、fallback=3、close=1，
Proxy retired_snapshots=382747，与Client尝试发送数一致；未发现回收失败或遗留对象错误日志。
实际计划运行456504次。运输attempts由P41的1527335降至1323132（-204203 / -13.37%）；
因相同时间内帧数更多，不能把两次原始计数之差当作同工作量精确节省。
完成页仍命中381412/382784（约99.64%），point凭据命中844561，prefix命中782760。
计时诊断保持关闭，各操作RPC计时未采集，不虚构单操作延迟结论。
计划运行总数分别409608、456836，运输attempts/plan约3.729→2.896（-22.33%）；
该比值是含资源管理等请求的整轮摊销统计，不是单个PLAN_EXEC处理器的RPC数。
额外审计`build/realm-performance-20261018/retire-v42-first-audit.json`核对原始SHA、
58份当前源码/冻结输入、RMM补丁未变、Client入队=随请求发送+关闭flush、
Proxy已回收数=Client发送数及Host恢复，均通过。
这次总分与广泛场景提升支持回收附带优化有效，但稳定性仍须同输入复测。

原始七份文件已回收并逐份SHA-256一致，证据目录
`GPU-SFTP/log/realm-xshm/realm-perf-retire-v42-glmark-20261018/`，
wrapper目录`build/lab-runs/realm-perf-retire-v42-glmark-20261018/`。
Host恢复pmthor、CPU0-1、userspace300MHz，after.json确认无活动实验进程、实验挂载或loop。
评估与场景比较命令为`assess-realm-evidence.py`、`summarize-run.py --against P41/P39-r2完整run-id`、
`compare-old1058.py`（均位于既有build证据工具目录，退出0）。

同镜像复测命令（未改源代码、二进制、配置或固件）：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-perf-retire-v42-r2-glmark-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/retire-v42-v41 \
  --workload glmark --performance --benchmark-only
```

复测控制日志`build/realm-performance-20261018/retire-v42-r2-glmark.log`；实测终态如下。RMM授权/可信IRQ路径和硬件GPT/GPC能力边界不变。


### P42 同镜像第二轮终态：1163；进入功能验收

`realm-perf-retire-v42-r2-glmark-20261018`，wrapper/runner退出0，VM[0,0]；
全部六个运行输入SHA与首轮一致。完整33场景1163，对首轮1159为+4 / +0.35%，
不将这4分当作另一个改动的收益。validation仍26成功/1已知例外/6无判据，
无submission error，五类受检内核事件均无；Host恢复pmthor、CPU0-1、300MHz，无实验残留进程/挂载/loop。
七份原始文件回收SHA一致，路径`GPU-SFTP/log/realm-xshm/realm-perf-retire-v42-r2-glmark-20261018/`，
wrapper目录同run-id，额外审计`build/realm-performance-20261018/retire-v42-repeat-audit.json`。

主会话Client queued=384222、sent=384221、fallback=0、close=1，
Proxy retired_snapshots=384221；无回收失败或遗留对象错误日志。
运输attempts=1332564，计划总运行457815；completion命中382876/384255（约99.64%），
point命中852283、prefix命中790345，可信IRQ为1383902/53355。
相对首轮仍有terrain42→40、buffer subdata46→45等波动，不宣称每个场景均更快，
也不将两轮结果扩大为长期压力或完整安全证明。

**保留决定：** P42在完整计分中两轮复现显著提升；没有重新启用P40对象复用，
也没有增加P36式推测性原生快照分配。保留四文件增量，暂停新增性能候选，验证当前组合功能。

已启动下列三Realm验收：17类GPU API在两次绑定周期各执行一次、完整glmark、
256MiB每页共享检查、非参与者拒绝、活动对象阻止撤销、重新绑定、提供方更换及可信IRQ归属/合并。
它包含额外Realm和生命周期负载，其分数不能当作双Realm计分条件完全相同的第三轮复测。

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-retire-v42-lifecycle-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/retire-v42-v41 \
  --workload glmark --performance
```

控制日志`build/realm-performance-20261018/retire-v42-lifecycle.log`。本轮终态PASS，详见下节；
双Client计算与当前组合完整32项亦未由两轮glmark证明，不能沿用旧版本PASS。


### 当前保留代码与安全边界复核

对当前源码与冻结输入逐项核对，58份跟踪源码和RMM补丁一致。
Client/Proxy及协议头中不存在已撤回的`reuse_snapshots`、`snapshot_pool`、`SNAPSHOT_REUSE`、
`TRANSFER_SNAPSHOT`、`batch_creates`、`watch_reinit`、`watch_disarm`；
历史失败补丁/日志仅留在忽略的build证据目录，不作为生产分支保留。
这项源码检查不替代功能测试，也不声称静态证明整个内核不存在死代码。

保留机制的可核查入口：

| 机制 | 当前实现入口 | 证据 / 边界 |
| --- | --- | --- |
| Realm身份与共享授权 | RMM `runtime/rsi/xshm.c`、`core/xshm_service.c`、`xshm_memory.c` | 调用者取自REC的RD；挂接/撤销绑定owner与endpoint generation，不信任Host传入VMID |
| 活动共享区生命周期 | RMM `core/xshm_policy.c`、`xshm_rtt.c` | 活动区阻止改变对应RTT/页归属；硬件运行生命周期测试尚在执行 |
| 可信事件 | RMM `xshm_endpoint.c`、`xshm_irq.c`及REC进入路径 | pending/ACK/ARM与IRQ归属受RMM控制；退出Host仅传调度提示，Host可拒绝服务 |
| 计划与精确完成 | Client `panthor_client_plan_completion_record`、Proxy `panthor_proxy_point_watch` | 保留完整原生chain、cookie、epoch和后续写失效；两轮glmark实际命中 |
| 回收附带 | Client last-ref put/take/close、Proxy `panthor_proxy_snapshot_retire` | 仅私有名字、整批校验、上限8、关闭flush；两轮分别回收382747/384221个主会话名字 |

“完成页只读”指Client驱动对象权限与映射，不等于RMM对共享pool内每个对象建立独立硬件只读授权。
RMM在此授权的是参与Realm之间的共享区域；不能由对象描述符推出对恶意Realm内核的页级写保护。
同一Client伪造自己的完成状态也不能成为Proxy绕过原生fence/其他Client授权的理由。
当前没有新增内存映射或放宽任何共享权限；RK3588的GPT/GPC硬件机密性限制仍保留。

逐项进度审计存于`build/realm-performance-20261018/current-completion-audit.json`：
两轮计分、当前源码检查及生命周期/双Client验收已有证据，最终汇总另见`final-performance-goal-audit.json`。
本节为源码复核与文档整理，未改运行代码，无新增性能测量。


### P42 三Realm生命周期终态与双Client验收

`realm-retire-v42-lifecycle-20261018`：wrapper/runner退出0，三台VM均退出0。
两次绑定周期的17类API各通过一次，共34项目标执行；glmark内部还有额外BASIC探针，
不把额外BASIC计为新的API类别。sync-file快照、timeline、Group提交完成、BO映射/绑定/销毁均通过。

- 256MiB共享区共65536页逐页检查、busy时拒绝撤销/关闭/解除映射、重新绑定检查通过。
- 第三Realm的非参与者请求被拒绝，IRQ计数保持0；两次通知只给目标注入一次IRQ，ACK/ARM及过期状态拒绝通过。
- 旧grant撤销后失效；相同目标IPA改由另一提供方授权，首/中/尾数据探针正确，旧提供方不能撤销新grant。
- 完整33场景glmark为1163、validation26成功/1已知例外/6无判据，无提交错误。
  **未改运行代码，无新增代码改动的性能归因**；第三Realm与额外API改变测试条件，单独记录为功能验收成绩。
- 3Realm×5类受检内核故障均无事件；Host恢复pmthor、CPU0-1、userspace300MHz，无实验残留进程/挂载/loop。

原始9份文件回收并逐份SHA一致：
`GPU-SFTP/log/realm-xshm/realm-retire-v42-lifecycle-20261018/`；
wrapper目录`build/lab-runs/realm-retire-v42-lifecycle-20261018/`；
额外核验`build/realm-performance-20261018/retire-v42-lifecycle-audit.json`。
此为当前Realm路径的34次API执行及通信生命周期，不冒充旧普通VM完整32项矩阵。

三Realm验收归档与Host恢复核对完成后，使用同一冻结包串行启动两个Client的真实GPU计算：

```bash
python3 scripts/maintenance/lab-run.py --run-id realm-retire-v42-dual-20261018 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/realm-performance-20261018/retire-v42-v41 \
  --workload compute --performance
```

控制日志`build/realm-performance-20261018/retire-v42-dual.log`，终态PASS，详见下节。
该入口每个Client执行17类API并同时运行实际计算，还检查独立pool和跨Client授权拒绝。
本轮共享区每Client2049页，与256MiB单Client计分不同，不新增glmark性能数字。


## 最终保留组合与验收汇总

**完整双Realm计分1159、1163；对P41的1023为+136～140 / +13.29～13.69%。**
两次同一冻结输入、完整33场景、720p、null-noop、finish、GPU实际594MHz、Proxy1/Client2、
每Realm1vCPU/768MiB、256MiB共享池、诊断计时关闭、shader cache关闭。
旧普通VM1058历史参考下高出+101～105 / +9.55～9.92%；旧内存规模、通信路径与Host启动不同，
不是完全匹配AB，也不宣称全部场景优于旧方案。terrain/refract仍有相对差距。

关键保留设计：长期RMM授权共享区与可信事件 → 可复用执行计划 → 原生fence精确完成凭据，
Client在cookie/epoch有效时本地完成查询 → 私有快照最后引用释放后有界排队，下一次新导出附带回收。
不省略原生fence，不复用旧私有快照，不推测性提前分配新对象；错误不冒充完成，含糊的传输失败不重放执行。
这条路径保留RMM控制面，同时减少常态控制往返。

`realm-retire-v42-dual-20261018`终态：wrapper/runner退出0，VM[0,0,0]；
两个Client的独立共享池同时绑定，跨Client描述/挂接被拒绝，权限自检通过；
每个Client17类API全部通过（34次目标执行），两边真实Mali-G610计算均为
`COMPUTE_CHECK=PASS count=65536 samples=16 ... alu_iters=64`。
IRQ归属与合并检查通过，工作后IRQ为2020/99/73，3Realm×5类受检内核故障无事件。
Host恢复pmthor、CPU0-1、300MHz，无实验进程/挂载/loop；原始9文件回收SHA一致，
证据目录`GPU-SFTP/log/realm-xshm/realm-retire-v42-dual-20261018/`，
wrapper目录同run-id，额外审计`build/realm-performance-20261018/retire-v42-dual-audit.json`。
本计算验收未运行glmark，不制造新计分结果；提供方更换由前一轮单Client生命周期覆盖。

| 验收 | run-id | 结果与证据边界 |
| --- | --- | --- |
| 完整计分首轮 | realm-perf-retire-v42-glmark-20261018 | 1159；原始7文件SHA一致、退出0 |
| 同镜像完整复测 | realm-perf-retire-v42-r2-glmark-20261018 | 1163；原始7文件SHA一致、退出0 |
| 三Realm生命周期/两次绑定API | realm-retire-v42-lifecycle-20261018 | PASS；34次目标API执行、256MiB逐页、撤销/替换/可信IRQ；额外完整glmark1163，条件不同；原始9文件SHA一致、退出0 |
| 双Client实际计算/API | realm-retire-v42-dual-20261018 | PASS；34次目标API执行、两边真实计算及跨Client授权拒绝；原始9文件SHA一致、退出0 |

四轮均有命令、冻结输入哈希、原始日志、wrapper前后资源和VM退出码；
最终核验`build/realm-performance-20261018/final-performance-goal-audit.json`再次读取四轮原始证据，
并确认当前58份跟踪源码仍与部署包一致、RMM补丁未变、局部检查10PASS/7负例。
两轮性能与后续验收期间未改运行代码，无未验证的最后修改。

**可声明：** 已达到本项目完整glmark超过1000、超过旧1058历史记录的性能目标，
RMM授权共享内存、事件/异常调度提示与可信IRQ机制保留，当前Realm通信/API/双Client计算验收通过；
已撤回无收益实验，不为性能绕开授权或改回Host授予memfd的路径。

**不扩大结论：** RK3588/OpenCCA没有真实GPT/GPC拒绝证据，本次验证的是既有CPU授权机制的保留与软件执行，
不声称恶意Host下已证明硬件机密性。GPU shadow隔离、完整远程证明、多vCPU/长期压力、
当前组合旧普通VM完整32项及同条件原生全套性能对照未由本次验收覆盖。
以上边界不是失败项的PASS；后续扩展需独立证据。


## P42 后续 Native 与广泛负载重新测量（2026-10-18）

完整对照见 [Native / 当前 Realm 专项报告](GPU_NATIVE_CURRENT_REALM_PERFORMANCE_20261018.md)。
本次保留 P42 两个 Image 和全部 58 份 GPU/RMM 生产源码，扩展测试入口；没有新的 GPU 性能优化变更。

**分数影响：** 独立干净批次 720p 为 **1154**，相对先前 1159 / 1163 均值 1161 为 **−0.60%**；
本轮新测 Native 为 **1437**，当前分数保留 **80.3%**。不能把批次波动计作入口修改的性能增益或损失。
Compute 四档吞吐保留约 80.5%–92.3%，七个 ML/Attention 算子接近原生，
MobileNet V2/V3 为 97.3% / 98.3%，双 Client 推导吞吐为 84.4%；细粒度 IOCTL case 仍为原生的 2.89–25.43 倍耗时。

扩展测试发现先前 720p 验收没有覆盖的限制：当前 **ResNet50、1080p 不通过**。
ResNet50 的 152 MiB BO 申请需要 buddy order16，超过当前域 max_order15（128 MiB），且发生 GPU translation fault；
1080p 的 BO 分配失败，打印的 939 分不合格。故障批次之后重新新建 Realm，
对可运行项目完成无受检 GPU fault 的独立测量；不将错误后的分数或模型错误时间计入有效对比。
这些结果不改写此前 720p 超过 1000 的事实，也不能扩大为当前组合完整 32/32 通过。

新证据：`current-p42-clean-suite-20261018`（17 原始文件 SHA 一致，退出0、2 Realm健康）、
`current-p42-dual-perf-20261018`（11 文件，退出0、3 Realm健康）、
`native-p42-comparison-20261018`（51 文件，退出0、受控重启恢复）；
两轮失败记录与未执行项完整保留在专项报告。最终机器审计见 `build/native-current-20261018/final-audit.json`。


## P42 后续：大 BO 容量修复与独立性能复核（2026-10-18）

目的为修复 ResNet50、1080p 的 BO 分配失败，保留 RMM 授权、可信 IRQ127、task plan 和 P42 snapshot / retirement 优化。GPU BO 改为按实际页数分配连续 extent；默认共享池仍为 256 MiB，新增显式 512 MiB 大负载配置（每 Realm 1 GiB / CMA576 MiB）。RMM 只调整有界区域上限，身份/映射/撤销、64 页预算及 grant 配额不变。

**分数影响：1154 → 1161，+7 / +0.61%。** `bo-cap512-default720-20261018` 使用原默认资源和完整 33 场景，退出0、两个 Realm 无受检内核错误。单次批次变化不视作稳定加速；目前未见明显性能退化，保留改动。第一候选故障后得到的1157不参与比较。

`bo-cap512-targets-r2-20261018` 在大配置上 ResNet50 **1463.96 ms/次**、完整1080p **901**、17项共同IOCTL和128 MiB Compute通过；131072页校验、detach/revoke及两个Realm健康检查通过，退出0。`bo-cap512-dual-isolation-20261018` 再验2×17 API、两份实际计算、跨Client授权拒绝及IRQ负例/合并，3 Realm健康，退出0。两项旧负载不通过，因此没有有效旧分数可算加速比；未重新执行完整32项。

完整根因、资源成本、失败候选、命令/退出码/日志/输入SHA见 [大 BO 修复报告](../../../shared/GPU_BO_CAPACITY_FIX_20261018.md)。默认256 MiB的实际预算仍不足以运行该ResNet50，应显式选择大配置；不通过隐藏fault、降低判定或放宽隔离边界来实现通过。
