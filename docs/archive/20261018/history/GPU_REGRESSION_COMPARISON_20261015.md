# GPU 环境部署与两轮完整回归对比（2026-10-15）

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

本轮 `acceptance-20261015-1610-full`：计划 32 项，已执行 32 项，通过 32，失败 0，未执行 0；启动器退出码 0。

上次 `publication-20261015-full` 的保存摘要为 32/32 通过、各项退出码均为 0。本轮结果独立统计；两次通过记录不代表历史 fence 超时问题已修复。

仅这两轮正式矩阵合计计划 64 个执行项：已执行 64，通过 64，失败 0，未执行 0。这是同一固定组合的重复执行记录，不是 64 个独立功能，也没有纳入额外短回归的历史失败。

## 运行台账与证据边界

| 运行 | 范围 | 结果 | 证据 |
| --- | --- | --- | --- |
| publication-20261015-full | 上次正式 32 项 | 32 PASS / 0 FAIL | [保存摘要](../../../shared/evidence/publication-20261015/full-summary.json)、[发布记录](GPU_REPOSITORY_PUBLICATION_20261015.md)；原始日志不在当前 checkout |
| fresh-clone-20261015-quick | 两轮完整测试之间的额外短回归 | 16 PASS / 1 FAIL 后停止 | [保存摘要](../../../shared/evidence/publication-20261015/fresh-quick-summary.json)；group-submit-syncpoint exit 1，两个 session 的 fence wait 超时；原始日志未随仓库提供 |
| onboard-20261015-* | 本控制机部署冒烟 | VM 创建 / 4 MiB Compute / Group submit 3 项 PASS，exit 0 | [部署报告](../../../../GPU-SFTP/log/deployment/onboard-20261015/REPORT.md)；Compute 5+2，独立于正式矩阵 |
| acceptance-20261015-1610-full | 本轮正式 32 项 | 32 PASS / 0 FAIL / 0 未执行 | [逐项摘要](../../../shared/evidence/acceptance-20261015-1610-full/full-summary.json)、[实际命令与耗时](../../../shared/evidence/acceptance-20261015-1610-full/commands.json) |

## 环境与执行方法

控制机 Ubuntu 26.04.1 / x86_64，仓库 `/home/mzh/gpu`，commit `799c37431c36a922927d76a8dc1dd0afa16d9901`；六个第一层子模块均匹配固定指针。RK 为 `root@192.168.31.18`、`6.12.0-opencca-pmthor #10`；正常共享模式 GPU 绑定 pmthor、CPU 0-1，直通需要的两种模块 ABI 均匹配。Pi `mzh@192.168.31.189` 本轮未用于刷写。

使用固定 manifest 的 175 个运行载荷文件、两个固定 Guest 镜像；开始前 `python3 scripts/check/check-checkout.py` exit 0，`CHECKOUT_RESULT=PASS scripts_checked=42`。首项重新同步基线镜像；没有重新编译内核、VMM、测试探针或刷新固件。

统一入口为 `python3 scripts/run/run-regression.py --passthrough --run-id acceptance-20261015-1610-full`，未使用 `--quick` 或 `--remote-prepared`。本地审计包装器 `build/regression-audit/run_full.py` 调用该入口，只记录实际命令、开始/结束 UTC 时间、墙钟耗时，并为单/双 Client 追加 `--no-clean-remote-procs`；探针构建 hook 使用 `/usr/bin/true` 复用已核验的固定探针。正式负载和判定阈值不变。凭据只在进程环境中使用，未写入文档。

北京时间 16:09:40 → 16:38:00，完整入口耗时约 28 分 20 秒。UTC 起止：2026-10-15T08:09:40.440303+00:00 → 2026-10-15T08:38:00.341301+00:00；各项命令墙钟耗时合计 1699.8 秒。首项包含同步，其他项也包含 VM 启停、注入和日志收集；这些耗时不是 GPU 内核执行时间。

正式参数：4/16 MiB Compute 各 100 次、64/128 MiB 各 20 次，预热均为 5、排除 CPU prepare；ML 六算子各 100+5、GEMM 512；Attention 320×64 为 10+2；NCNN 三模型各 100 次；glmark 720p/1080p 全场景、null-noop、finish、未跳过 validate；双 Client 各 4 MiB、100+5；Host/直通按默认 4/16/64 MiB 比较，100/100/20 次、预热 5、同 rootfs 用户态且排除 CPU prepare。Compute correctness 是循环结束后均匀抽查 16 个输出元素，不是每次循环全量逐元素校验；ML_CHECK 的 samples 是测量循环数，CPU reference 在最后一次循环校验。

## 分组结果对比

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

## 两轮逐项结果

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

## 数值结果与统计口径

负载时间来自本轮原始 Client/Host 日志，单位明确区分微秒和毫秒；具体 min/avg/max、renderer、correctness、validation 计数见 [metrics.json](../../../shared/evidence/acceptance-20261015-1610-full/metrics.json)。Compute 和 ML 的时间包含 API 提交、同步和读回等开销，不是 GPU 硬件计时器测得的纯 shader 时间。上次正式 32 项摘要没有保存各负载原始 timing，不能计算可靠的跨轮加速比。

| 共享 Compute | 测量次数 | 平均 ms/次 | 最小 ms | 最大 ms |
| --- | ---: | ---: | ---: | ---: |
| compute-4mib | 100 | 19.951 | 18.624 | 31.677 |
| compute-16mib | 100 | 23.605 | 21.255 | 36.770 |
| compute-64mib | 20 | 40.173 | 34.343 | 42.975 |
| compute-128mib | 20 | 63.133 | 57.560 | 71.956 |

| ML kernel | 平均 ms/次 | 校验 |
| --- | ---: | --- |
| gemm_512_fp32 | 75.329 | PASS samples=100 warmup=5 |
| conv2d_64x64x32_3x3_fp32 | 90.476 | PASS samples=100 warmup=5 |
| depthwise_conv_128x128x128_3x3_fp32 | 61.684 | PASS samples=100 warmup=5 |
| block_reduction_32mib_fp32 | 39.597 | PASS samples=100 warmup=5 |
| row_softmax_16384x256_fp32 | 55.617 | PASS samples=100 warmup=5 |
| single_head_attention_256x64_fp32 | 1561.357 | PASS samples=100 warmup=5 |
| single_head_attention_320x64_fp32 | 2489.343 | PASS samples=10 warmup=2 |

| NCNN 模型 | min ms | avg ms | max ms | 结果 |
| --- | ---: | ---: | ---: | --- |
| mobilenet_v2 | 138.98 | 149.47 | 180.24 | PASS |
| mobilenet_v3 | 136.19 | 147.42 | 174.72 | PASS |
| resnet50 | 767.38 | 809.83 | 991.46 | PASS |

NCNN 使用完整 param、随机输入与空/零权重；这里只证明 Vulkan GPU 路径和图执行，不证明模型精度。

| glmark | score | 场景数 | validation success/failure/unknown | 已知/意外 framebuffer 错误 |
| --- | ---: | ---: | --- | --- |
| glmark-1280x720 | 58 | 33 | 26 FAILURE=1 UNKNOWN=6 | 1 / 0 |
| glmark-1920x1080 | 58 | 33 | 26 FAILURE=1 UNKNOWN=6 | 1 / 0 |

上次正式矩阵发布记录保存了 720p score 59，本轮为 58，观测差值 -1（-1.69%）。只有单轮评分，未控制全部频率/温度条件，不能认定性能回退或提升。上次正式矩阵的 1080p 分数未保存在其摘要中；相关修复报告另一个 run-id 的 58 分不挪作该矩阵的原始数据。

glmark 分数是 null-noop + finish 下的离屏评分，不能称为屏幕 FPS。validate 是源码已有的兼容性判定：成功场景至少 20、精确 checksum 失败最多 4，并保留每个场景结果；它不等于全部场景逐像素一致。known medium function 数值差异与 null winsys 的 incomplete framebuffer 分开统计；不能把二者都写成“无错误”。

- glmark-1280x720 精确 checksum 失败原文：[function] fragment-complexity=medium:fragment-steps=5: Validation: Failure
- glmark-1920x1080 精确 checksum 失败原文：[function] fragment-complexity=medium:fragment-steps=5: Validation: Failure

| 双 Client | 平均 ms/次 | correctness / workload |
| --- | ---: | --- |
| client0 | 未启用 --perf，未输出 | PASS count=1048576 samples=16 formula=x*3+7+alu_mix alu_iters=1 / PASS |
| client1 | 未启用 --perf，未输出 | PASS count=1048576 samples=16 formula=x*3+7+alu_mix alu_iters=1 / PASS |

| Host vs passthrough | Host avg ms | VM avg ms | Host/VM 时间比 | VM 相对 Host 时间开销 |
| --- | ---: | ---: | ---: | ---: |
| 4 MiB | 1.397 | 13.564 | 0.1030 | 870.98% |
| 16 MiB | 5.426 | 10.259 | 0.5288 | 89.09% |
| 64 MiB | 22.201 | 22.470 | 0.9880 | 1.21% |

本轮功能全通过不等于各容量性能接近原生：4 MiB 直通 VM 平均时间约为 Host 的 9.71 倍，16 MiB 约 1.89 倍，64 MiB 约 1.012 倍。统一脚本没有为这些时间比设置性能失败阈值，因此前两项明显开销没有转为功能 FAIL。此处如实记录观测，未通过额外复测或 profiling 定位原因。六份 Host/VM 子负载摘要中的 status/timeout_status 均为 0。

Host/VM 时间比定义为 Host elapsed / VM elapsed，越接近 1 越接近；时间开销为 (VM/Host−1)×100%。双 Client 传入了 100 次循环、5 次预热，但没有 --perf，故日志不输出耗时，不能补造平均延迟或吞吐。它也未排除 CPU prepare，而共享单 Client 与 Host/直通命令排除了 CPU prepare；CPU 配置不同，不能直接把这些路径的平均值相除当作隔离后的虚拟化损耗。样本是同一次运行内的循环，没有多轮独立重复或置信区间，不能据此宣称统计显著的性能提升。

## 已知问题、结束状态与未覆盖项

历史 `fresh-clone-20261015-quick` 的 Group submit fence 超时仍为未解决记录。部署冒烟、本轮正常通过与历史失败同时保留，不以成功覆盖失败；本轮未做根因修复或重复运行到通过。

本轮单项原始日志位于 `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`、`shared/vmshm-2client/<run-id>/`、`passthrough/perf/<run-id>/`；逐项 run-id 是主 run-id 加用例名。实际命令、UTC 时间、退出码见审计 JSON。程序返回值与关键 marker 复核见 [evidence-check.json](../../../shared/evidence/acceptance-20261015-1610-full/evidence-check.json)。

最终独立严格状态检查退出码 0：无 firecracker/vmshm-broker、无 loop 挂载残留，GPU driver 为 pmthor、CPU 为 0-1；前后 boot-id 相同，中间没有重启。详见 [Host 审计摘要](../../../shared/evidence/acceptance-20261015-1610-full/host-audit.json)、[原始状态日志](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full-audit/host-after.log)与[本轮 dmesg 增量](../../../../GPU-SFTP/log/regression/acceptance-20261015-1610-full-audit/host-dmesg-delta.log)。

本轮 Host dmesg 增量 482 行；GPU reset failed、Kernel panic、WARNING: CPU、Unable to handle kernel、BUG、job timeout、GPU fault 这些列明模式命中 0 行。这是指定模式扫描结果，不是任意内核错误的完备证明。32 条 session closed 与 32 条最终引用释放记录的数量序列一致，关闭记录合计 334174，最终释放合计 334174。这是按会话累加的引用计数，不能解释为整个运行期间互不重复的物理页数。独立 PFN checker 也已通过两种关闭顺序校验。

MemAvailable：3204328 → 3104308 KiB，变化 -97.68 MiB；Shmem：1340 → 1332 KiB。可用内存快照下降不能仅凭一次前后对比判定为泄漏；本轮引用计数匹配。历史报告有 PCP 导致类似快照变化的证据，但本轮没有测量 PCP 或追踪这部分差值，不沿用历史原因作为已证实解释。

本次没有测试空白 SD 整盘刷写、重建全部固件/第三方依赖、Realm/GPT 硬件机密隔离、PRIME 或 ONNX GPU Provider，也没有追加 rsync 性能验证。未推送或提交代码、凭据、原始运行日志、镜像和缓存。

## 后续原生驱动与 Clientproxy 性能专项


后续运行 `native-clientproxy-20261015-165201` 已对上述 32 个通过项逐项建立性能比较映射，完整表格、逐场景数据、命令、退出码与故障证据见 [原生 Panthor / Clientproxy 专项报告](GPU_NATIVE_CLIENTPROXY_PERFORMANCE_20261015.md)。专项结果独立于前述两轮 32/32，不能并入 64 项正式执行的通过统计。

| Compute | Native 平均 ms | Clientproxy 平均 ms | Clientproxy / Native |
| --- | ---: | ---: | ---: |
| compute-4mib | 1.410 | 20.034 | 14.206× |
| compute-16mib | 5.428 | 24.234 | 4.465× |
| compute-64mib | 22.731 | 40.258 | 1.771× |
| compute-128mib | 44.939 | 63.114 | 1.404× |

720p / 1080p glmark 的原生 score 分别为 1496 / 1161，Clientproxy 均为 58；这些是 null-noop + finish 离屏评分。ML、NCNN、双 Client、17 项 IOCTL 及直通第三路径详见专项报告。

专项保留如下例外：4 个环境/PFN 项没有原生对等性能指标；原生 BO_NO_MMAP 偏移查询不满足原断言，另测普通映射子集；原 Group submit 在预热中超时，另测有效绝对期限 profile；128 MiB 补采虽完成计算校验，但随后原生驱动 unbind 发生内核 Oops，不能记为阶段 PASS。还保留一次采集截断、720p 清理失败及 ResNet50 追加共享侧外层退出码缺失。两次复位后严格健康检查通过，未修复内核卸载问题，也未修改固定基线以覆盖旧失败。
