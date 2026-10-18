# GPU 部署、完整回归与 Native / Clientproxy 性能综合报告

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-15；时间均按北京时间说明，证据中的原始 UTC 时间保留。

本报告汇总已经完成的部署、两轮正式 32 项回归及后续性能专项。本次整理未重新运行硬件测试、未更改固定驱动或测试载荷。文末附完整 32 项结果、性能覆盖映射、所有计时表、66 组 glmark 场景对比和阶段证据台账。

## 1. 核心结论

1. **部署与正式功能回归成立。** 固定载荷已接入既有健康 RK Host；上次和本轮正式回归各 32/32 通过。本轮所有项目退出码均为 0，没有未执行项。两轮合计 64 次执行通过，但仍然是同一组 32 项重复执行。
2. **后续性能专项不能判定为全部通过。** 所有 32 项均建立覆盖映射，其中 4 项环境/PFN 检查没有 Native 对等性能指标。17 项原 IOCTL profile 只有 15 项取得有效成对样本；BO mmap 和 Group submit 的补充 profile 单列，不替代原失败。
3. **性能差异依赖负载，不能给出一个统一损耗百分比。** 单流 Compute 的 Clientproxy/Native 时间比从 4 MiB 的 14.206× 降到 128 MiB 的 1.404×；六个 ML 算子为 1.047–3.761×，另一个 320×64 Attention 为 2.896×；MobileNet 为 6.052–6.391×。glmark 总分仅保留 Native 的 3.88%–5.00%。
4. **ResNet50 是反向观测，尚未解释。** 两次均观察到 Clientproxy 平均时间低于 Native，但两轮幅度从 -36.27% 变成 -13.95%。执行顺序、缓存、调频及复位状态没有严格控制，不能据此宣称 Clientproxy 普遍更快。
5. **最严重的新问题是原生 Panthor 卸载 Oops。** 128 MiB clean 计算与校验完成后，unbind 触发内核异常并阻塞；设备经过两次复位后恢复严格健康状态。恢复成功不等于驱动缺陷已修复。
6. **证据检查通过不等于测试全通过。** 独立核对保留了失败、截断及退出码缺失；性能证据验证程序退出码 0，只证明证据与异常统计一致。

## 2. 环境、部署与运行台账

控制机 Ubuntu 26.04.1 / x86_64，仓库 `/home/mzh/gpu`，commit `799c37431c36a922927d76a8dc1dd0afa16d9901`；六个第一层子模块均匹配固定指针。RK 为 `root@192.168.31.18`、`6.12.0-opencca-pmthor #10`；正常共享模式 GPU 绑定 pmthor、CPU 0-1，直通需要的两种模块 ABI 均匹配。Pi `mzh@192.168.31.189` 本轮未用于刷写。

使用固定 manifest 的 175 个运行载荷文件、两个固定 Guest 镜像；开始前 `python3 scripts/check/check-checkout.py` exit 0，`CHECKOUT_RESULT=PASS scripts_checked=42`。首项重新同步基线镜像；没有重新编译内核、VMM、测试探针或刷新固件。

统一入口为 `python3 scripts/run/run-regression.py --passthrough --run-id acceptance-20261015-1610-full`，未使用 `--quick` 或 `--remote-prepared`。本地审计包装器 `build/regression-audit/run_full.py` 调用该入口，只记录实际命令、开始/结束 UTC 时间、墙钟耗时，并为单/双 Client 追加 `--no-clean-remote-procs`；探针构建 hook 使用 `/usr/bin/true` 复用已核验的固定探针。正式负载和判定阈值不变。凭据只在进程环境中使用，未写入文档。

北京时间 16:09:40 → 16:38:00，完整入口耗时约 28 分 20 秒。UTC 起止：2026-10-15T08:09:40.440303+00:00 → 2026-10-15T08:38:00.341301+00:00；各项命令墙钟耗时合计 1699.8 秒。首项包含同步，其他项也包含 VM 启停、注入和日志收集；这些耗时不是 GPU 内核执行时间。

正式参数：4/16 MiB Compute 各 100 次、64/128 MiB 各 20 次，预热均为 5、排除 CPU prepare；ML 六算子各 100+5、GEMM 512；Attention 320×64 为 10+2；NCNN 三模型各 100 次；glmark 720p/1080p 全场景、null-noop、finish、未跳过 validate；双 Client 各 4 MiB、100+5；Host/直通按默认 4/16/64 MiB 比较，100/100/20 次、预热 5、同 rootfs 用户态且排除 CPU prepare。Compute correctness 是循环结束后均匀抽查 16 个输出元素，不是每次循环全量逐元素校验；ML_CHECK 的 samples 是测量循环数，CPU reference 在最后一次循环校验。

| 运行 | 范围 | 结果 | 证据 |
| --- | --- | --- | --- |
| publication-20261015-full | 上次正式 32 项 | 32 PASS / 0 FAIL | [保存摘要](../../../shared/evidence/publication-20261015/full-summary.json)、[发布记录](GPU_REPOSITORY_PUBLICATION_20261015.md)；原始日志不在当前 checkout |
| fresh-clone-20261015-quick | 两轮完整测试之间的额外短回归 | 16 PASS / 1 FAIL 后停止 | [保存摘要](../../../shared/evidence/publication-20261015/fresh-quick-summary.json)；group-submit-syncpoint exit 1，两个 session 的 fence wait 超时；原始日志未随仓库提供 |
| onboard-20261015-* | 本控制机部署冒烟 | VM 创建 / 4 MiB Compute / Group submit 3 项 PASS，exit 0 | [部署报告](../../../../GPU-SFTP/log/deployment/onboard-20261015/REPORT.md)；Compute 5+2，独立于正式矩阵 |
| acceptance-20261015-1610-full | 本轮正式 32 项 | 32 PASS / 0 FAIL / 0 未执行 | [逐项摘要](../../../shared/evidence/acceptance-20261015-1610-full/full-summary.json)、[实际命令与耗时](../../../shared/evidence/acceptance-20261015-1610-full/commands.json) |

性能专项 `native-clientproxy-20261015-165201` 于 16:52:01–17:46:27 执行，约 54.4 分钟，包含异常处理、复位和补充测量。该专项独立于 16:09:40–16:38:00 的正式 32 项回归。前述“未重新编译测试探针”描述正式矩阵；性能专项另编译了新 IOCTL 计时探针，没有替换固定正式载荷。

## 3. 正式回归的完整统计

| 分组 | 项数 | 上次 PASS | 本轮 PASS / FAIL / 未执行 |
| --- | ---: | ---: | --- |
| 前后环境检查 | 2 | 2 | 2 / 0 / 0 |
| IOCTL | 17 | 17 | 17 / 0 / 0 |
| PFN 程序及日志检查 | 2 | 2 | 2 / 0 / 0 |
| GLES Compute | 4 | 4 | 4 / 0 / 0 |
| ML / Attention | 2 | 2 | 2 / 0 / 0 |
| NCNN Vulkan | 1 | 1 | 1 / 0 / 0 |
| glmark2 | 2 | 2 | 2 / 0 / 0 |
| 双 Client | 1 | 1 | 1 / 0 / 0 |
| Host vs passthrough | 1 | 1 | 1 / 0 / 0 |

32 项包含 17 项 IOCTL、2 项 PFN 程序/日志检查、2 项前后环境检查，以及 11 项负载/对比；不能将它们描述成 32 种独立 GPU 算法，也不能把部署冒烟或额外短回归并入两轮正式矩阵的成功率。

| # | 用例 | 上次退出码 | 本轮退出码 | 本轮结果证据 | 本轮墙钟秒 | 本轮日志 |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | preflight | 0 | 0 | PASS | 0.342 | [preflight.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/preflight.log) |
| 2 | ioctl | 0 | 0 | PASS | 196.776 | [ioctl.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/ioctl.log) |
| 3 | vm-create | 0 | 0 | PASS | 8.649 | [vm-create.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/vm-create.log) |
| 4 | bo-create | 0 | 0 | PASS | 9.732 | [bo-create.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/bo-create.log) |
| 5 | bo-lifecycle | 0 | 0 | PASS | 9.691 | [bo-lifecycle.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/bo-lifecycle.log) |
| 6 | bo-mmap | 0 | 0 | PASS | 8.675 | [bo-mmap.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/bo-mmap.log) |
| 7 | vm-bind | 0 | 0 | PASS | 8.728 | [vm-bind.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/vm-bind.log) |
| 8 | vm-bind-async-sync | 0 | 0 | PASS | 9.746 | [vm-bind-async-sync.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/vm-bind-async-sync.log) |
| 9 | vm-state-flush | 0 | 0 | PASS | 9.753 | [vm-state-flush.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/vm-state-flush.log) |
| 10 | syncobj-lifecycle | 0 | 0 | PASS | 8.734 | [syncobj-lifecycle.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/syncobj-lifecycle.log) |
| 11 | syncobj-wait | 0 | 0 | PASS | 9.667 | [syncobj-wait.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/syncobj-wait.log) |
| 12 | syncobj-transfer | 0 | 0 | PASS | 9.711 | [syncobj-transfer.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/syncobj-transfer.log) |
| 13 | syncobj-timeline-wait | 0 | 0 | PASS | 8.775 | [syncobj-timeline-wait.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/syncobj-timeline-wait.log) |
| 14 | syncobj-signal-query | 0 | 0 | PASS | 9.761 | [syncobj-signal-query.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/syncobj-signal-query.log) |
| 15 | sync-file-snapshot | 0 | 0 | PASS | 10.71 | [sync-file-snapshot.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/sync-file-snapshot.log) |
| 16 | group-lifecycle | 0 | 0 | PASS | 8.761 | [group-lifecycle.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/group-lifecycle.log) |
| 17 | group-submit-syncpoint | 0 | 0 | PASS | 8.732 | [group-submit-syncpoint.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/group-submit-syncpoint.log) |
| 18 | tiler-heap-lifecycle | 0 | 0 | PASS | 8.709 | [tiler-heap-lifecycle.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/tiler-heap-lifecycle.log) |
| 19 | pfn-lifetime | 0 | 0 | PASS | 0.507 | [pfn-lifetime.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/pfn-lifetime.log) |
| 20 | pfn-log-check | 0 | 0 | PASS | 0.03 | [pfn-log-check.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/pfn-log-check.log) |
| 21 | compute-4mib | 0 | 0 | PASS | 12.884 | [compute-4mib.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/compute-4mib.log) |
| 22 | compute-16mib | 0 | 0 | PASS | 12.957 | [compute-16mib.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/compute-16mib.log) |
| 23 | compute-64mib | 0 | 0 | PASS | 11.714 | [compute-64mib.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/compute-64mib.log) |
| 24 | compute-128mib | 0 | 0 | PASS | 13.789 | [compute-128mib.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/compute-128mib.log) |
| 25 | ml-all | 0 | 0 | PASS | 207.758 | [ml-all.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/ml-all.log) |
| 26 | attention320 | 0 | 0 | PASS | 40.348 | [attention320.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/attention320.log) |
| 27 | ncnn | 0 | 0 | PASS | 212.555 | [ncnn.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/ncnn.log) |
| 28 | glmark-1280x720 | 0 | 0 | PASS | 385.384 | [glmark-1280x720.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/glmark-1280x720.log) |
| 29 | glmark-1920x1080 | 0 | 0 | PASS | 381.305 | [glmark-1920x1080.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/glmark-1920x1080.log) |
| 30 | two-client | 0 | 0 | PASS | 15.245 | [two-client.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/two-client.log) |
| 31 | passthrough | 0 | 0 | PASS | 59.326 | [passthrough.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/passthrough.log) |
| 32 | idle-after | 0 | 0 | PASS | 0.387 | [idle-after.log](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full/idle-after.log) |

## 4. 性能结果的解释与可信边界

时间比统一采用 Clientproxy / Native，越大表示应用可见耗时越长；glmark 使用分数保留比例，越高越好。启动 VM、注入、取日志等控制阶段墙钟时间与应用内计时分开，不能互换。

- **短操作开销明显。** 原 profile 的有效 IOCTL 成对时间比为 14.546–590.278×。这些是 open、公共检查、用例主体、close 的组合耗时，某些用例包含等待；Native 的微秒级小分母也会放大比例。不能称为单次 ioctl 或纯 RPC 延迟。
- **Compute 存在随工作量增大而摊薄额外开销的趋势。** 4 MiB 额外约 18.624 ms，128 MiB 额外约 18.175 ms，但仅有四种规模和单组运行，不能据此拟合固定开销模型或认定根因。
- **ML 没有统一趋势。** 256×64 Attention 只增加 4.72%，320×64 却增加 189.60%；需要独立分析提交、同步、内存和实际执行路径，不能把“长负载接近原生”当成普遍结论。
- **NCNN 结论限于测试图执行。** 使用随机输入、空/零权重，GPU probe 与模型执行证据保留；这不是训练模型精度或真实业务端到端质量评估。
- **图形评分偏低且存在验证例外。** 两种分辨率各完整采集 33 场景，两侧验证均为 26 成功、1 失败、6 未知；PASS 来自既有兼容阈值，不能描述为所有场景逐像素一致。null-noop 离屏分数也不是显示器 FPS。
- **并发与直通单独解释。** 双流结果为每流延迟，没有证明完整测量窗口完全重叠，不能从倒数相加推算总吞吐；passthrough 是第三条路径，其原生分母来自独立配对，不能混用计算三路径精确相对损耗。

本轮比较两套实际部署的应用可见性能，CPU 调度与资源配额不完全相同。未锁定频率、未随机交替执行，多数工作负载只有一组成对运行；循环样本不能代替独立运行重复。报告不给出统计显著性、跨设备推广结论或生产性能承诺。

## 5. 异常、失败与恢复的完整说明

| 事项 | 实际观测与状态 | 统计处理 |
| --- | --- | --- |
| 历史 Group fence 超时 | 额外短回归 16 PASS / 1 FAIL 后停止，未解决 | 不纳入两轮正式矩阵成功率，不由后续 PASS 覆盖 |
| 首次 IOCTL 采集截断 | 旧 BASIC_PASS 让新批量包装器提前取结果，外层 rc=0 但无矩阵结束标记 | 判未完成；修正等待条件后单独补采，不把截断当 PASS |
| Native BO mmap 原断言 | NO_MMAP 对象的偏移查询成功，冒烟预期该查询失败，rc=1 | 原 profile 无有效成对值；普通 BO 正向映射另列 |
| Clientproxy Group submit 原期限 | 固定绝对时间 1 秒已过期，预热 Timer expired，样本数 0 | 保留失败；“当前时间+1秒”补充 profile 两侧各 20 样本，独立报告 |
| Native glmark 720p 清理 | 负载完成，但 bind/rootfs 卸载 busy，阶段 rc=90，随后健康门禁 rc=1 | 分数保留，整体阶段不算通过；普通卸载及驱动恢复完成，未重跑挑分 |
| 首次 128 MiB 数据受干扰 | 编译窗口与运行重叠 | 原始数据保留，最终采用 clean 补采 |
| Native 128 MiB clean 卸载 | 计算正确性通过后 unbind Oops，线程阻塞 flush_workqueue，最终 SSH rc=255 | 时间作为已完成负载观测值；整个阶段失败，驱动缺陷未修复 |
| 追加 ResNet50 共享侧 | 远端模型 rc=0、NCNN_RESULT=PASS；停止本地协调器后外层退出码缺失 | 外层 rc 保留 null，不补造 0；性能结果附此限制 |
| 最终计划复位 | SSH 等待 rc=124；新 boot-id 与最终健康检查证明复位完成 | 属恢复控制阶段，不当作 GPU 负载失败或负载 PASS |

NO_MMAP 查询返回偏移不代表 Native 允许实际映射 NO_MMAP 对象：内核实际 mmap 路径另有拒绝检查。补充普通映射测试没有覆盖该策略断言。Group 的过期绝对期限能解释本次探针的即时超时风险，但不能据此宣布历史所有 fence 超时已经定位或修复；固定正式源码与载荷尚未应用该修正。

故障恢复保留了内核与线程栈。常规 reboot 在 device_shutdown 阻塞后使用 SysRq 复位；最后的原生补测保持 Panthor 绑定，保存并同步数据后再次复位，避免重走已失败的卸载路径。未使用 Pi 刷写、未写任何存储分区。

性能台账共 70 个记录阶段，包含准备、健康检查与恢复，并不是 70 个 GPU 用例；其中 8 个记录保留为失败、未完成、退出码缺失或复位例外，不能称为 8 个独立 GPU 功能失败。

## 6. Host 审计与最终状态

跨 3 个 boot-id 共检查 2060 行内核日志；匹配到 2 行故障文本，属于同一次原生卸载 Oops。19 次 session 关闭和释放记录逐序列匹配，关闭/释放引用数合计均为 455182。引用计数不是唯一物理页数量，也不能证明不存在所有类型的内存问题。

最终严格健康检查退出码 0：GPU 绑定 pmthor、在线 CPU 0-1，没有 VM、broker 或 loop 残留。最终健康只证明设备恢复到可继续测试的状态，不抹除本轮异常，也不代表同一次启动全程无错误。详见 [Host 审计](../../../shared/evidence/native-clientproxy-20261015-165201/host-audit.json) 和 [恢复台账](../../../shared/evidence/native-clientproxy-20261015-165201/recovery.json)。

## 7. 后续工作的建议顺序

以下为建议，尚未执行或宣称完成：

1. 优先修复并独立复现验证 Panthor unbind / process_fw_events_work 的生命周期缺陷，覆盖多次 bind/unbind、负载结束后卸载和正常重启。
2. 在正式源码修正 Group 等待绝对期限，严格检查完整结束标记与逐项结果；重新构建固定探针、更新 manifest 后重跑完整 32 项，并专门覆盖较长 VM uptime 与延迟 fence。
3. 将 NO_MMAP 的“查询偏移”和“实际映射禁止”拆开验证，保留 Native/Clientproxy 能力差异，避免用正向子集代替策略用例。
4. 稳定性问题处理后，统一 CPU 配额、频率、预热和日志配置，按随机/交替顺序做多轮独立测量；优先分析小粒度 IOCTL、图形提交与同步、320×64 Attention 及 ResNet50 反向结果。
5. 增加真实权重 NCNN 业务、长期并发、内存压力及可靠的窗口重叠/吞吐测量，才能评估生产适用性。

本报告不覆盖空白 SD 刷写、完整固件重建、Realm/GPT 机密隔离证明、PRIME 完整互操作或 ONNX GPU 测试。现有结果适用于本报告固定软硬件与参数组合。

## 8. 证据入口与复核

- [正式回归原报告](GPU_REGRESSION_COMPARISON_20261015.md)：上次摘要、本轮每项命令、rc、耗时和原始日志链接；上次完整原始日志不在当前 checkout。
- [性能专项原报告](GPU_NATIVE_CLIENTPROXY_PERFORMANCE_20261015.md)：测量配置、全部负载数据、异常和阶段台账。
- [正式矩阵实际命令](../../../shared/evidence/acceptance-20261015-1610-full/commands.json)、[正式矩阵摘要](../../../shared/evidence/acceptance-20261015-1610-full/full-summary.json)。
- [性能实际命令](../../../shared/evidence/native-clientproxy-20261015-165201/commands.json)、[性能数值与样本](../../../shared/evidence/native-clientproxy-20261015-165201/metrics.json)、[逐阶段 marker 复核](../../../shared/evidence/native-clientproxy-20261015-165201/checks.json)。
- [性能证据验证结果](../../../shared/evidence/native-clientproxy-20261015-165201/verification.json)：`python3 build/native-clientproxy/verify.py`，rc=0，`PERFORMANCE_EVIDENCE_VERIFY=PASS`；含义为证据与异常记录一致。

下列附录直接汇编既有性能专项内容，保留各项命令、rc、run-id 和日志入口，避免只提供摘要而丢失不利结果。

## 附录 1：覆盖与方法

本次对上轮 32 个通过项逐项建立映射。17 项 IOCTL 采集用例级耗时；4 项 Compute、ML/Attention、NCNN、两种 glmark 分辨率和双 Client 做新一轮成对测量；直通对比作为独立的第三路径补充。preflight、idle-after、PFN 程序及日志检查共 4 项没有原生对等性能指标，标为不适用，不制造耗时比。

硬件为同一 RK3588，Host `6.12.0-opencca-pmthor #10`。开始前固定 manifest 与 checkout 检查通过；内核、VMM、GLES/ML、NCNN/glmark 使用固定载荷，仅新增 IOCTL 计时探针。未刷写设备或更新上游。单负载 Host 在线 CPU 0-1；Client/Proxy 各 1 vCPU（内存 512/384 MiB），默认调度；原生进程可在 Host 两个 CPU 上调度，未套用 Guest 的内存上限，NCNN 两线程也受此调度差异影响。双 Client 按既有脚本用 CPU 0/1/2/3 分配 broker/Proxy/Client0/Client1；原生两进程也在线 CPU 0-3，分别绑定 CPU 2/3。一次只运行一套 GPU 测试，以 pmthor、CPU 0-1、无 VM/broker/loop 残留作为阶段间门禁；720p 原生清理例外及恢复见下文。

每个共享负载结束并确认 VM/broker/loop 均无残留后，临时切换 Host 到 Panthor，挂载同一已注入负载的 rootfs，在 chroot 内运行相同 gpu-smoke.sh、二进制和库，再卸载并恢复驱动。比较的是这两套部署路径的应用可见耗时，包含 CPU 调度、RPC、内存属性、驱动和同步等差异；不能称为纯 RPC 或纯 GPU 开销。原生有 PRIME 等额外能力，具体路径可由 Mesa 自行选择。保留固定内核默认日志输出开销，未使用 strace/ftrace/perf-record。频率策略未锁定，温度/频率快照保存在原始 native 日志；除 ResNet50 针对性追加一组成对验证外，各负载只有一组成对运行，没有随机交替或置信区间。本轮采用新采集的两侧数据，不沿用上轮共享测量作为本轮分母或成功保证。

Compute 4/16 MiB 为 100+5，64/128 MiB 为 20+5，均 --perf --exclude-cpu-prepare；ML 六算子 100+5，Attention 320×64 为 10+2；NCNN 三模型各 100 次，线程数 2、PanVK GPU probe、随机输入/空权重；glmark 两种分辨率均 null-noop+finish 全 33 场景，保留 validate。双进程每个 4 MiB、100+5，新增 --perf，包含 CPU prepare，与单 Client Compute 分开比较。

IOCTL 探针从原冒烟 C 源码生成，移除两侧不对等的 PRIME/外部 FD“不支持”断言；两侧运行同一个静态二进制。每个用例 3 次预热、20 次测量，CLOCK_MONOTONIC，边界为 open → 公共 basic checks → 用例主体 → close，不包括 VM 启停。测量循环中 stdout 重定向 /dev/null，仍包含相同的字符串格式化成本；首轮预热输出完整语义结果。每项是组合操作耗时，不是单次 ioctl 延迟；等待/超时用例包含其设计等待。原正式冒烟没有被改写，原有 PASS 与能力边界不因此扩大。

首次 128 MiB 成对采集期间有补充探针编译与其执行窗口交叠，作为受干扰样本保留；最终表使用编译完成、硬件空闲后追加的 `compute-128mib-clean` 成对测量。追加是为了消除已知测量干扰，不是失败后重复到通过。

时间比定义为 Clientproxy / Native，>1 表示 Clientproxy 更慢；额外时间为 (Clientproxy/Native−1)×100%。glmark 分数与场景 FPS 是离屏评分，越高越好，单独计算保留比例。

## 附录 2：IOCTL 用例级性能

完整 common profile 的结果见下表。首次 Clientproxy 采集因预热阶段的旧 PASS 标记触发提前收集而截断；该阶段退出码虽为 0，但没有矩阵结束标记，独立证据复核判定未完成，不用作完整数据。修正等待条件后，追加 proxy-ioctl-matrix-complete 完整采集并单独保存；这是修正采集边界，不是硬件失败后重复到通过。原生为 16/17 成功；Clientproxy 完整采集为 16/17 成功（Group submit 失败）。原生 bo-mmap 的 NO_MMAP 对象查询偏移返回成功，与该冒烟的预期失败断言不符；保留原生退出码 1，不计算原用例比值。另加两侧相同的普通 BO mmap→CPU 写/读回→munmap→释放正向子集，明确不是原 NO_MMAP 策略断言通过。

| 用例 | Native 平均 µs | Clientproxy 平均 µs | 时间比 | 额外时间 |
| --- | ---: | ---: | ---: | ---: |
| basic | 23.436 | 6527.471 | 278.523× | +27752.33% |
| vm-create | 179.746 | 9346.852 | 52.000× | +5100.03% |
| bo-create | 77.396 | 12005.642 | 155.120× | +15411.97% |
| bo-lifecycle | 122.607 | 14017.267 | 114.327× | +11332.68% |
| bo-mmap（原断言） | FAIL rc=1，无有效样本 | 14175.933 | — | — |
| vm-bind | 2476.806 | 36028.708 | 14.546× | +1354.64% |
| vm-bind-async-sync | 222.243 | 29576.998 | 133.084× | +13208.40% |
| vm-state-flush | 64.840 | 11610.010 | 179.056× | +17805.63% |
| syncobj-lifecycle | 42.351 | 12007.392 | 283.521× | +28252.09% |
| syncobj-wait | 52.910 | 15051.619 | 284.476× | +28347.59% |
| syncobj-transfer | 44.452 | 13680.056 | 307.749× | +30674.89% |
| syncobj-timeline-wait | 85.899 | 23732.012 | 276.278× | +27527.81% |
| syncobj-signal-query | 82.778 | 21893.258 | 264.482× | +26348.16% |
| sync-file-snapshot | 1779.624 | 1050472.398 | 590.278× | +58927.77% |
| group-lifecycle | 297.409 | 19368.533 | 65.124× | +6412.42% |
| group-submit-syncpoint（原断言） | 379.108 | FAIL rc=1，无有效样本 | — | — |
| tiler-heap-lifecycle | 346.921 | 13727.627 | 39.570× | +3856.99% |
| bo-mmap（普通映射正向子集） | 118.606 | 13776.044 | 116.150× | +11514.96% |
| group-submit（有效绝对期限） | 332.775 | 26830.635 | 80.627× | +7962.70% |

原 profile 的 group-submit-syncpoint 在 Clientproxy 预热阶段返回 Timer expired，samples=0，矩阵 failures=1；本地批量计时包装脚本仍可能因预热中的早期 BASIC_PASS 返回 0，所以以矩阵和逐项证据判失败。源码将 DRM_SYNCOBJ_WAIT 的 absolute timeout 固定为 1000000000 ns（启动后第 1 秒），本次调用时早已过期；这会把未立即就绪的 fence 当作超时。补充计时探针仅将两侧这一处改为 abs_timeout_after_ns(1000000000LL)，仍要求 fence 完成且不改返回值或判据。补充结果属于修正等待期限的 profile，不覆盖原失败，也没有将该变更应用到固定基线或宣称历史问题已修复。

## 附录 3：Compute、ML 与 NCNN

| 负载 | Native 平均 ms | Clientproxy 平均 ms | 时间比 | 额外时间 |
| --- | ---: | ---: | ---: | ---: |
| compute-4mib | 1.410 | 20.034 | 14.206× | +1320.64% |
| compute-16mib | 5.428 | 24.234 | 4.465× | +346.49% |
| compute-64mib | 22.731 | 40.258 | 1.771× | +77.11% |
| compute-128mib | 44.939 | 63.114 | 1.404× | +40.44% |
| gemm_512_fp32 | 20.713 | 39.932 | 1.928× | +92.79% |
| conv2d_64x64x32_3x3_fp32 | 24.007 | 43.796 | 1.824× | +82.43% |
| depthwise_conv_128x128x128_3x3_fp32 | 17.158 | 35.625 | 2.076× | +107.63% |
| block_reduction_32mib_fp32 | 8.133 | 30.587 | 3.761× | +276.08% |
| row_softmax_16384x256_fp32 | 14.744 | 34.567 | 2.344× | +134.44% |
| single_head_attention_256x64_fp32 | 543.535 | 569.178 | 1.047× | +4.72% |
| single_head_attention_320x64_fp32 | 854.477 | 2474.534 | 2.896× | +189.60% |
| NCNN mobilenet_v2 | 24.390 | 147.600 | 6.052× | +505.17% |
| NCNN mobilenet_v3 | 23.270 | 148.730 | 6.391× | +539.15% |
| NCNN resnet50 | 1265.920 | 806.710 | 0.637× | -36.27% |

ResNet50 的首次结果方向与 MobileNet 相反，因此额外做一次仅选择 ResNet50、其余线程/GPU/循环参数相同的成对测量。两组都保留，不挑选最好结果；模型执行顺序和缓存状态未固定，不能将差异直接归因于驱动优化。

| ResNet50 轮次 | Native 平均 ms | Clientproxy 平均 ms | 时间比 | 额外时间 |
| --- | ---: | ---: | ---: | ---: |
| 首次（三模型序列） | 1265.920 | 806.710 | 0.637× | -36.27% |
| 追加（单模型） | 1268.480 | 1091.530 | 0.861× | -13.95% |

以上均为应用侧墙钟统计，不是 GPU 硬件 timer。Compute 最后抽查 16 个元素，ML 最后一次循环做 CPU reference 校验；NCNN 不证明训练模型精度。完整 min/avg/max、correctness 与 renderer 在 metrics.json 中；IOCTL 另保存全部样本与 p50/p95，避免只看平均值忽略尾部波动。

## 附录 4：glmark 总分与验证

| 分辨率 | Native score | Clientproxy score | Clientproxy / Native 分数 | Native 验证 S/F/U | Clientproxy 验证 S/F/U |
| --- | ---: | ---: | ---: | --- | --- |
| glmark-1280x720 | 1496 | 58 | 3.88% | 26 FAILURE=1 UNKNOWN=6 | 26 FAILURE=1 UNKNOWN=6 |
| glmark-1920x1080 | 1161 | 58 | 5.00% | 26 FAILURE=1 UNKNOWN=6 | 26 FAILURE=1 UNKNOWN=6 |

原生 720p 的负载与验证已完成（GPU_SMOKE_RESULT=PASS，NATIVE_COMMAND_RC=0），但初版本地辅助脚本清理时 /dev bind 与 rootfs 卸载 busy，阶段退出码 90，紧随的严格健康检查退出码 1，因此整体阶段不能记 PASS。测试自动停止后，核对无本次残留进程，以普通 umount 卸载这两个确属本次的挂载并恢复 pmthor，恢复命令退出码 0；保留 [恢复日志](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-720-cleanup-recovery.log)。后续辅助脚本只增加有界的普通卸载重试，未用 force/lazy 卸载或全局 kill；没有为了清理失败重跑 720p 分数。该清理瞬态的占用来源未证实。评分不等于屏幕 FPS。validate 的 PASS 是既有兼容性阈值判定，并非所有场景逐像素相等；known medium function checksum 差异和 null winsys framebuffer 错误分别列出。

| 分辨率 / 路径 | 精确 checksum 失败场景 | 已知 framebuffer | 意外 framebuffer | BO / export / VM_BIND 错误 |
| --- | --- | ---: | ---: | --- |
| glmark-1280x720 / native | [function] fragment-complexity=medium:fragment-steps=5: Validation: Failure | 1 | 0 | 0 / 0 / 0 |
| glmark-1280x720 / proxy | [function] fragment-complexity=medium:fragment-steps=5: Validation: Failure | 1 | 0 | 0 / 0 / 0 |
| glmark-1920x1080 / native | [function] fragment-complexity=medium:fragment-steps=5: Validation: Failure | 1 | 0 | 0 / 0 / 0 |
| glmark-1920x1080 / proxy | [function] fragment-complexity=medium:fragment-steps=5: Validation: Failure | 1 | 0 | 0 / 0 / 0 |

## 附录 5：双进程 / 双 Client

| 执行流 | Native 两进程 平均 ms/次 | 双 Clientproxy 平均 ms/次 | 时间比 | 额外时间 |
| --- | ---: | ---: | ---: | ---: |
| process / client 0 | 3.378 | 24.454 | 7.240× | +624.01% |
| process / client 1 | 3.380 | 24.767 | 7.328× | +632.76% |

原生启动两个独立进程访问同一 GPU，并绑定 CPU 2/3；共享侧两个 Client 分别绑定 CPU 2/3，Proxy 与 broker 另占 CPU 1/0。原生两进程从控制脚本连续启动，共享脚本采用既有延迟对齐机制，未证明整个测量窗口完全重叠，因此不把每流平均时间简单换算为系统总吞吐。两侧 CPU prepare 均包含在计时内。

## 附录 6：直通第三路径补充

| 大小 | Native 平均 ms | passthrough VM 平均 ms | VM / Native | 额外时间 |
| --- | ---: | ---: | ---: | ---: |
| 4 MiB | 1.575 | 13.034 | 8.273× | +727.34% |
| 16 MiB | 5.384 | 9.717 | 1.805× | +80.47% |
| 64 MiB | 22.483 | 24.271 | 1.080× | +7.96% |

此表来自单独的 Host/passthrough 脚本、同 rootfs 用户态、排除 CPU prepare；这里的 Native 与前面 Clientproxy 成对测试是不同执行阶段，不混用其分母推断三条路径的精确相对损耗。

## 附录 7：原生驱动卸载 Oops 与恢复

128 MiB clean 补采已打印 COMPUTE_CHECK=PASS、GPU_SMOKE_RESULT=PASS，平均时间为负载完成前采集的观测值；随后在原生 Panthor unbind 阶段发生 Unable to handle kernel paging request / Internal error: Oops，process_fw_events_work+0xa8/0x124，卸载线程阻塞在 flush_workqueue。SSH 最终返回 255，不能将这一阶段记为 PASS，也不能据计算校验推断清理安全。原始证据见 [内核与进程栈](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/host-native-unbind-oops.log)。

先保存故障证据；sync 后普通 reboot -f 又阻塞在 device_shutdown，之后使用 SysRq b 恢复。未刷写内核、固件或任何存储分区。恢复后独立负载继续完成；最后原生测量保持 Panthor 绑定，避免重走已失败的 unbind 路径，保存结果并同步后用 SysRq 再次复位，最终严格检查 pmthor、CPU 0-1、无 VM/broker/loop 残留。这里只恢复设备，未修复驱动卸载问题。

ResNet50 追加共享侧在第一次恢复后由已启动的远端子任务继续完成；本地协调器当时已停止，故外层退出码不可得，明确保留 null，不填造 0；远端原始模型退出码 NCNN_MODEL_RC=0、NCNN_RESULT=PASS 与性能输出另行验证。两次复位前后 boot-id 不同，不能声称同一次启动全程无内核错误。

## 附录 8：上轮 32 项逐项覆盖

| # | 上轮通过项 | 本次性能比较处理 |
| ---: | --- | --- |
| 1 | preflight | 不适用：环境健康门禁；本次各阶段独立检查 |
| 2 | ioctl | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 3 | vm-create | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 4 | bo-create | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 5 | bo-lifecycle | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 6 | bo-mmap | 原生策略断言 FAIL；另有普通映射正向子集成对计时 |
| 7 | vm-bind | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 8 | vm-bind-async-sync | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 9 | vm-state-flush | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 10 | syncobj-lifecycle | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 11 | syncobj-wait | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 12 | syncobj-transfer | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 13 | syncobj-timeline-wait | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 14 | syncobj-signal-query | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 15 | sync-file-snapshot | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 16 | group-lifecycle | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 17 | group-submit-syncpoint | 原期限 profile 在 Clientproxy 失败，无有效样本；另采当前时间 + 1 秒的有效绝对期限 profile |
| 18 | tiler-heap-lifecycle | IOCTL common profile：3 预热 + 20 次测量，两侧相同二进制 |
| 19 | pfn-lifetime | 不适用：pmthor / VM 专属引用生命周期与日志判定，无原生对等操作；本次保留 Host 引用释放审计 |
| 20 | pfn-log-check | 不适用：pmthor / VM 专属引用生命周期与日志判定，无原生对等操作；本次保留 Host 引用释放审计 |
| 21 | compute-4mib | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 22 | compute-16mib | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 23 | compute-64mib | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 24 | compute-128mib | 成对计算校验与计时完成；原生补采随后 unbind Oops，阶段失败 |
| 25 | ml-all | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 26 | attention320 | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 27 | ncnn | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 28 | glmark-1280x720 | 两侧 33 场景及验证完成；原生清理失败，阶段退出码 90 |
| 29 | glmark-1920x1080 | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 30 | two-client | 新一轮 Native / Clientproxy 对等负载，见上表与原始证据 |
| 31 | passthrough | 单独复测 Native / passthrough；Clientproxy 的同类 Compute 另行成对测量 |
| 32 | idle-after | 不适用：环境健康门禁；本次各阶段独立检查 |

## 附录 9：证据与结束状态

命令与退出码：[commands.json](../../../shared/evidence/native-clientproxy-20261015-165201/commands.json)；全部性能数值：[metrics.json](../../../shared/evidence/native-clientproxy-20261015-165201/metrics.json)；关键 marker 复核：[checks.json](../../../shared/evidence/native-clientproxy-20261015-165201/checks.json)；Host 增量审计：[host-audit.json](../../../shared/evidence/native-clientproxy-20261015-165201/host-audit.json)。原始日志：`GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/`，共享 Client 原始输出另在 `GPU-SFTP/log/shared/vmshm-1client/native-clientproxy-20261015-165201-proxy-<case>/client.log`，双 Client 在对应 vmshm-2client 目录。

| 阶段 | 退出码 | marker 复核 | 墙钟秒（含准备/清理） | 日志 |
| --- | ---: | --- | ---: | --- |
| preflight | 0 | PASS | 1.17 | [preflight.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/preflight.log) |
| proxy-ioctl-matrix | 0 | 采集截断；未完成 | 9.274 | [proxy-ioctl-matrix.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-ioctl-matrix.log) |
| native-ioctl-matrix | 1 | FAIL / 未完成 | 0.797 | [native-ioctl-matrix.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-ioctl-matrix.log) |
| proxy-compute-4mib | 0 | PASS | 12.015 | [proxy-compute-4mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-compute-4mib.log) |
| native-compute-4mib | 0 | PASS | 2.235 | [native-compute-4mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-compute-4mib.log) |
| proxy-compute-16mib | 0 | PASS | 13.088 | [proxy-compute-16mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-compute-16mib.log) |
| native-compute-16mib | 0 | PASS | 2.817 | [native-compute-16mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-compute-16mib.log) |
| proxy-compute-64mib | 0 | PASS | 12.712 | [proxy-compute-64mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-compute-64mib.log) |
| native-compute-64mib | 0 | PASS | 2.857 | [native-compute-64mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-compute-64mib.log) |
| proxy-compute-128mib | 0 | PASS | 13.123 | [proxy-compute-128mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-compute-128mib.log) |
| native-compute-128mib | 0 | PASS | 4.881 | [native-compute-128mib.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-compute-128mib.log) |
| proxy-ml-all | 0 | PASS | 90.181 | [proxy-ml-all.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-ml-all.log) |
| native-ml-all | 0 | PASS | 67.985 | [native-ml-all.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-ml-all.log) |
| proxy-attention320 | 0 | PASS | 39.183 | [proxy-attention320.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-attention320.log) |
| native-attention320 | 0 | PASS | 11.818 | [native-attention320.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-attention320.log) |
| proxy-ncnn | 0 | PASS | 208.023 | [proxy-ncnn.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-ncnn.log) |
| native-ncnn | 0 | PASS | 212.229 | [native-ncnn.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-ncnn.log) |
| proxy-glmark-1280x720 | 0 | PASS | 383.686 | [proxy-glmark-1280x720.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-glmark-1280x720.log) |
| native-glmark-1280x720 | 90 | FAIL / 未完成 | 354.491 | [native-glmark-1280x720.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-glmark-1280x720.log) |
| proxy-glmark-1920x1080 | 0 | PASS | 383.31 | [proxy-glmark-1920x1080.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-glmark-1920x1080.log) |
| native-glmark-1920x1080 | 0 | PASS | 354.504 | [native-glmark-1920x1080.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-glmark-1920x1080.log) |
| proxy-two-client | 0 | PASS | 15.116 | [proxy-two-client.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-two-client.log) |
| native-two-client | 0 | PASS | 1.926 | [native-two-client.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-two-client.log) |
| passthrough | 0 | PASS | 58.452 | [passthrough.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/passthrough.log) |
| idle-after | 0 | PASS | 0.401 | [idle-after.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/idle-after.log) |
| proxy-ioctl-matrix-complete | 0 | FAIL：矩阵 failures=1 | 40.41 | [proxy-ioctl-matrix-complete.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-ioctl-matrix-complete.log) |
| proxy-mmap-positive | 0 | PASS | 9.711 | [proxy-mmap-positive.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-mmap-positive.log) |
| native-mmap-positive | 0 | PASS | 0.62 | [native-mmap-positive.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-mmap-positive.log) |
| proxy-compute-128mib-clean | 0 | PASS | 13.973 | [proxy-compute-128mib-clean.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-compute-128mib-clean.log) |
| native-compute-128mib-clean | 255 | FAIL / 未完成 | 333.235 | [native-compute-128mib-clean.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-compute-128mib-clean.log) |
| proxy-ncnn-resnet-repeat | None | 外层退出码缺失；模型 rc=0 | — | [proxy-ncnn-resnet-repeat.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-ncnn-resnet-repeat.log) |
| prepare-group-deadline | 0 | PASS | 7.616 | [prepare-group-deadline.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/prepare-group-deadline.log) |
| proxy-group-valid-deadline | 0 | PASS | 10.033 | [proxy-group-valid-deadline.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/proxy-group-valid-deadline.log) |
| native-ncnn-resnet-repeat | 0 | PASS | 200.178 | [native-ncnn-resnet-repeat.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-ncnn-resnet-repeat.log) |
| native-group-valid-deadline | 0 | PASS | 0.307 | [native-group-valid-deadline.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-group-valid-deadline.log) |
| native-final-state | 0 | PASS | 0.363 | [native-final-state.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/native-final-state.log) |
| payload-hashes | 0 | PASS | 0.513 | [payload-hashes.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/payload-hashes.log) |
| planned-final-reboot | 124 | 复位已确认；SSH 等待超时 | 12.03 | [planned-final-reboot.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/planned-final-reboot.log) |
| final-health | 0 | PASS | 0.489 | [final-health.log](../../../../GPU-SFTP/log/native-clientproxy/native-clientproxy-20261015-165201/final-health.log) |

Host dmesg 按不同 boot 分段保存的本轮增量 2060 行，列明故障模式命中 2 行；closed / release 记录 19 / 19，累计引用 455182 / 455182，按各 boot 分别校验序列匹配 True。这些是指定模式与引用计数审计，不证明任意错误都不存在，也不是唯一物理页数。最终严格健康检查：PASS。

历史额外短回归的 Group submit fence 超时仍为未解决记录；本次计时通过不等于根因已修复。原生 NO_MMAP 偏移查询差异也作为本次新观察保留；源码显示原生在实际 mmap 时拒绝该 flag（panthor_gem.c），查询偏移的 ioctl 并不检查该 flag（panthor_drv.c），所以不能据此次断言失败宣称原生允许实际映射 NO_MMAP BO。未提交或推送凭据、运行日志、镜像、缓存或代码。计时探针修改见同目录 ioctl-perf.patch、mmap-positive.patch 与 group-valid-deadline.patch；本地执行辅助脚本在 build/native-clientproxy/（被 Git 忽略），记录其 SHA-256 于 local-helper-hashes.json；精确实际命令见 commands.json。

## 附录 10：glmark 逐场景性能

### glmark-1280x720

| 场景 | Native FPS | Clientproxy FPS | 分数保留比例 | Native 帧时间 ms | Clientproxy 帧时间 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| [build] use-vbo=false: | 1108.0 | 64.0 | 5.78% | 0.903 | 15.677 |
| [build] use-vbo=true: | 2254.0 | 76.0 | 3.37% | 0.444 | 13.216 |
| [texture] texture-filter=nearest: | 2229.0 | 74.0 | 3.32% | 0.449 | 13.592 |
| [texture] texture-filter=linear: | 2234.0 | 75.0 | 3.36% | 0.448 | 13.396 |
| [texture] texture-filter=mipmap: | 2208.0 | 74.0 | 3.35% | 0.453 | 13.537 |
| [shading] shading=gouraud: | 1965.0 | 75.0 | 3.82% | 0.509 | 13.367 |
| [shading] shading=blinn-phong-inf: | 1948.0 | 75.0 | 3.85% | 0.513 | 13.463 |
| [shading] shading=phong: | 1835.0 | 75.0 | 4.09% | 0.545 | 13.407 |
| [shading] shading=cel: | 1846.0 | 75.0 | 4.06% | 0.542 | 13.508 |
| [bump] bump-render=high-poly: | 1337.0 | 74.0 | 5.53% | 0.748 | 13.693 |
| [bump] bump-render=normals: | 2495.0 | 73.0 | 2.93% | 0.401 | 13.809 |
| [bump] bump-render=height: | 2413.0 | 71.0 | 2.94% | 0.414 | 14.143 |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0;: | 2045.0 | 75.0 | 3.67% | 0.489 | 13.481 |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;: | 1175.0 | 70.0 | 5.96% | 0.851 | 14.473 |
| [pulsar] light=false:quads=5:texture=false: | 1747.0 | 71.0 | 4.06% | 0.573 | 14.166 |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4: | 366.0 | 9.0 | 2.46% | 2.739 | 116.142 |
| [desktop] effect=shadow:windows=4: | 939.0 | 40.0 | 4.26% | 1.066 | 25.322 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 46.0 | 22.0 | 47.83% | 21.788 | 46.316 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata: | 46.0 | 22.0 | 47.83% | 21.854 | 45.687 |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 64.0 | 32.0 | 50.00% | 15.691 | 32.198 |
| [ideas] speed=duration: | 474.0 | 49.0 | 10.34% | 2.114 | 20.489 |
| [jellyfish] <default>: | 1487.0 | 72.0 | 4.84% | 0.673 | 14.011 |
| [terrain] <default>: | 80.0 | 2.0 | 2.50% | 12.545 | 551.373 |
| [shadow] <default>: | 1036.0 | 38.0 | 3.67% | 0.966 | 26.39 |
| [refract] <default>: | 204.0 | 7.0 | 3.43% | 4.905 | 151.169 |
| [conditionals] fragment-steps=0:vertex-steps=0: | 2026.0 | 71.0 | 3.50% | 0.494 | 14.267 |
| [conditionals] fragment-steps=5:vertex-steps=0: | 1959.0 | 73.0 | 3.73% | 0.511 | 13.858 |
| [conditionals] fragment-steps=0:vertex-steps=5: | 2023.0 | 71.0 | 3.51% | 0.495 | 14.264 |
| [function] fragment-complexity=low:fragment-steps=5: | 2017.0 | 71.0 | 3.52% | 0.496 | 14.279 |
| [function] fragment-complexity=medium:fragment-steps=5: | 1887.0 | 69.0 | 3.66% | 0.53 | 14.625 |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5: | 2015.0 | 68.0 | 3.37% | 0.496 | 14.743 |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5: | 2014.0 | 69.0 | 3.43% | 0.497 | 14.593 |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5: | 1883.0 | 71.0 | 3.77% | 0.531 | 14.163 |

### glmark-1920x1080

| 场景 | Native FPS | Clientproxy FPS | 分数保留比例 | Native 帧时间 ms | Clientproxy 帧时间 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| [build] use-vbo=false: | 1023.0 | 64.0 | 6.26% | 0.978 | 15.828 |
| [build] use-vbo=true: | 1916.0 | 76.0 | 3.97% | 0.522 | 13.17 |
| [texture] texture-filter=nearest: | 1691.0 | 77.0 | 4.55% | 0.591 | 13.062 |
| [texture] texture-filter=linear: | 1698.0 | 76.0 | 4.48% | 0.589 | 13.205 |
| [texture] texture-filter=mipmap: | 1699.0 | 77.0 | 4.53% | 0.589 | 13.135 |
| [shading] shading=gouraud: | 1682.0 | 77.0 | 4.58% | 0.595 | 13.14 |
| [shading] shading=blinn-phong-inf: | 1664.0 | 76.0 | 4.57% | 0.601 | 13.162 |
| [shading] shading=phong: | 1521.0 | 76.0 | 5.00% | 0.658 | 13.159 |
| [shading] shading=cel: | 1514.0 | 75.0 | 4.95% | 0.661 | 13.405 |
| [bump] bump-render=high-poly: | 1194.0 | 73.0 | 6.11% | 0.838 | 13.862 |
| [bump] bump-render=normals: | 1961.0 | 75.0 | 3.82% | 0.51 | 13.376 |
| [bump] bump-render=height: | 1848.0 | 76.0 | 4.11% | 0.541 | 13.328 |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0;: | 1299.0 | 70.0 | 5.39% | 0.77 | 14.489 |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;: | 588.0 | 70.0 | 11.90% | 1.703 | 14.382 |
| [pulsar] light=false:quads=5:texture=false: | 1389.0 | 75.0 | 5.40% | 0.72 | 13.442 |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4: | 276.0 | 9.0 | 3.26% | 3.625 | 114.283 |
| [desktop] effect=shadow:windows=4: | 743.0 | 40.0 | 5.38% | 1.346 | 25.027 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 46.0 | 22.0 | 47.83% | 22.035 | 45.69 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata: | 46.0 | 23.0 | 50.00% | 22.07 | 45.159 |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 64.0 | 32.0 | 50.00% | 15.864 | 31.97 |
| [ideas] speed=duration: | 444.0 | 50.0 | 11.26% | 2.253 | 20.262 |
| [jellyfish] <default>: | 1027.0 | 67.0 | 6.52% | 0.974 | 14.932 |
| [terrain] <default>: | 65.0 | 2.0 | 3.08% | 15.469 | 538.81 |
| [shadow] <default>: | 803.0 | 39.0 | 4.86% | 1.246 | 25.759 |
| [refract] <default>: | 162.0 | 7.0 | 4.32% | 6.191 | 146.432 |
| [conditionals] fragment-steps=0:vertex-steps=0: | 1535.0 | 72.0 | 4.69% | 0.652 | 13.947 |
| [conditionals] fragment-steps=5:vertex-steps=0: | 1493.0 | 73.0 | 4.89% | 0.67 | 13.779 |
| [conditionals] fragment-steps=0:vertex-steps=5: | 1535.0 | 72.0 | 4.69% | 0.652 | 13.906 |
| [function] fragment-complexity=low:fragment-steps=5: | 1527.0 | 71.0 | 4.65% | 0.655 | 14.149 |
| [function] fragment-complexity=medium:fragment-steps=5: | 1427.0 | 71.0 | 4.98% | 0.701 | 14.199 |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5: | 1525.0 | 72.0 | 4.72% | 0.656 | 13.921 |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5: | 1524.0 | 71.0 | 4.66% | 0.656 | 14.178 |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5: | 1419.0 | 72.0 | 5.07% | 0.705 | 13.942 |
