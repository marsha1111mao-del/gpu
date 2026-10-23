# 近期性能改动复核：关闭诊断后完整720p为1159分

按用户补充要求，先验证关闭诊断能否恢复成绩，保留已有实现。本轮使用最新完成回传candidate-c的原冻结输入，仅关闭RPC统计、通知采样及完成回传采样，完整720p **1159分**；同一candidate-c此前开启诊断为1144分，增加15分 / 1.31%。相对原1158参考值为+1分 / +0.086%，已经回到原有成绩水平。

这支持1140多分与诊断开启有关，当前没有据此删除运行代码的理由。两轮分属不同时段，本次仅新增一轮，不能将15分全部精确归因于某一个计时功能，也不据此宣称新优化提分。原1158的Guest/RMM组合不同，仅作历史参考；1144与本轮1159的全部runner、VMM、Client/Proxy Image、initrd及rootfs输入哈希相同。

## 已有结果与本轮对照

以下旧结果重新检查了原始33场景、回收SHA、启动参数、退出码、健康与租约记录，没有重跑旧矩阵。RPC、通知和完成诊断均为显式开关；完成诊断同时启用通知采样。

| 版本 / 条件 | 完整720p | run-id |
| --- | ---: | --- |
| TRANSFER候选，预捕获关闭，诊断关闭 | 1158 | `transfer-capture-off-720-20261022-a` |
| 同TRANSFER候选，预捕获开启，诊断关闭 | 1156 | `transfer-capture-on-720-20261022-a` |
| 同TRANSFER候选，预捕获开启，RPC统计开启 | 1149 | `transfer-capture-rpc-720-20261022-a` |
| 通知候选，诊断关闭 | 1152 | `notify-kernel-gate-720-20261022-a` |
| 同通知候选，RPC/通知诊断及Host探针开启 | 1141 | `notify-breakdown-720-20261022-a` |
| 完成回传candidate-b，诊断关闭 | 1159 | `completion-kernel-gate-720-20261022-a` |
| 同candidate-b，RPC/通知/完成诊断开启 | 1146 | `completion-breakdown-720-20261022-a` |
| 补齐RPC确认的candidate-c，RPC/通知/完成诊断开启 | 1144 | `completion-breakdown-720-20261022-b` |
| **同candidate-c，三个诊断均关闭，本轮新增** | **1159** | `completion-diagnostics-off-720-20261022-a` |

本轮保留`--transfer-capture`，与1144轮保持相同优化路径，避免把撤回优化与关闭诊断混在一起。正式默认路径仍不自动启用该实验开关。旧同镜像1158→1156尚未证明TRANSFER预捕获提分，本轮也没有新增其开关收益对照。

## 代码检查与保留决定

检查范围包括Guest提交`206c612af`相对`29fc19336`的九个文件、其后工作区的五个完成计时文件、RMM通知计时提交`15c7ee14a`，以及runner、init和Host诊断工具。

| 内容 | 实际作用 / 证据 | 决定 |
| --- | --- | --- |
| RPC阶段计时 | 显式`--rpc-stats`才执行统计；频繁读时钟、累计计数 | 保留，正式计分关闭 |
| 通知拆分与RMM计时ABI | 显式`--notify-trace`才分配Guest采样缓冲并使用计时通知；普通NOTIFY不读取新增RMM时间戳 | 保留，正式计分关闭；不加载Host通知探针 |
| 完整fence至Client确认计时 | 显式`--completion-trace`才执行计时锁、计数器及元数据采样；本轮首次观察/采样等六项诊断计数均0 | 保留，正式计分关闭 |
| TRANSFER预捕获 | 已验证减少独立快照RPC；旧无计时对照1158→1156，尚无FPS收益 | 按用户补充要求保留，维持独立、默认关闭的实验开关 |
| 分段BO与共享旧目标后备回收 | 前者支持小池负载；后者单Client实测903.26→519.33 MiB | 保留，不因本轮诊断分差撤回内存功能 |
| 四Client在途准入、阶段内存准入及2 GiB租约容量 | 已补齐七项四Client算子和三/四Client ResNet50；四模型GPU租约峰值1355.64 MiB | 保留；这些改动解决可运行性和容量问题，不按单Client提分衡量 |

内存及多Client结论引用[后备回收报告](GPU_SHARED_MEMORY_RECLAIM_20261022.md)与[ML补测报告](GPU_ML_COMPLETION_20261022.md)，本轮没有重测模型或多Client。保留失败与未执行证据，不将诊断工具称为已验证的提分优化。

## 如何关闭及为何影响成绩

正式性能命令不传`--rpc-stats`、`--notify-trace`、`--completion-trace`，即可同时关闭对应的Guest启动参数。三个开关默认关闭，`--performance`不自动打开它们；无需重编内核或刷写固件。`--completion-trace`会连带打开通知采样，单独去掉`--notify-trace`不足以关闭该组合。

RPC统计会在数十万次同步请求中读时钟和累计阶段数据；通知诊断会读物理计数器、调用RMM计时入口并写采样记录；完成诊断还会串行化首次cookie观察、读取元数据并记录时间戳。它们在Client/Proxy的高频路径执行，会增加测量成本。关闭后仍执行原来的真实fence、精确cookie和权限检查。

本轮保留每两秒一次的原Host观测及`--telemetry`，与1144轮一致；关闭的是上述高频计时组合。Host通知kprobe未加载。独立审计确认summary中三个开关均为false、两侧启动参数没有对应启用项、六项Client完成诊断计数全部为0，且没有通知trace或完成计时输出文件。

## 命令与验收证据

本轮唯一新硬件测量，未改运行代码。冻结包为`build/completion-latency-20261022/candidate-c/`；当前五项未提交Guest源码SHA与该包构建记录一致。完整实际命令如下，凭据仅由会话环境提供：

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id completion-diagnostics-off-720-20261022-a -- \
  python3 build/completion-latency-20261022/observe-run.py \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/completion-latency-20261022/candidate-c \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720 \
  --clients 1 --compact-memory --pool-mib 128 \
  --client-cpu-layout round-robin --cpu-frequency-khz 1800000 \
  --telemetry --transfer-capture
```

该run-id已使用，重跑必须换新ID。Host #31/protected、相同通知计时版RMM/2 GiB租约、单Client/128 MiB池、CPU固定1.8 GHz，Proxy CPU1、Client CPU2、VMM I/O CPU0；GPU请求600 MHz/实际594 MHz，null-noop/finish、完整33场景。Host两秒观测验证落核与频率。

外层、runner、采集、常规审计及本轮独立审计均退出0。validation沿用26成功/1既有数值例外/6无判据，clean、Mali renderer、Host/Guest内核健康、两个Realm退出0、GPU/DMA租约归零及资源恢复通过。11份运行证据逐文件SHA核验通过；Pi/RK最终资源无门槛问题，RK恢复CPU0–1、pmthor，无实验VM、loop或测试挂载。

- 本轮原始日志与输入：`build/completion-latency-20261022/runs/completion-diagnostics-off-720-20261022-a/`。
- 完整命令、退出码、前后资源、Host日志与租约：`build/lab-runs/completion-diagnostics-off-720-20261022-a/`。
- Host频率/落核观测：`build/completion-latency-20261022/observations/completion-diagnostics-off-720-20261022-a/`。
- 常规审计：`build/completion-latency-20261022/completion-diagnostics-off-720-20261022-a-audit.json`。
- 九轮历史/当前交叉核验、计时关闭证据及Pi/RK终检：`build/performance-diagnostics-off-20261022/{audit.json,live-state-a.json,final-resources.json}`。

改动目的｜核验1158→1140多分是否由诊断引起｜同candidate-c诊断开启1144 → 关闭1159；历史1158 → 本轮1159｜+15/+1.31%；对历史+1/+0.086%｜当前对照输入相同，仅关闭三个高频计时开关，分属不同时段；历史1158的Guest/RMM组合不同｜上述run-id、完整命令、退出码0及原始日志｜保留运行实现和诊断工具，正式计分默认关闭诊断；不宣称TRANSFER提分，未重测Native/1080p/模型/多Client。
