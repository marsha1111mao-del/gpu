# 当前优化版 glmark 固定频率完整对照（2026-10-25）

按用户要求重新执行 Native / Clientproxy、720p / 1080p、1–4 并发的全部 16 个配置，每配置一轮完整测试。
两列全部来自本批新测，没有引用历史 Native 或 Clientproxy 分数。未改生产运行代码，未新增性能优化。

已追加到 [Notion：多Client并行测试结果合集](https://www.notion.so/3ff659a3b8cc813bbab7c109be10ad21)
末尾的“glmark：当前优化版固定频率完整对照”，原有表格与 ML 内容保留。写入成功且无警告，
响应保存在 `build/fixed-glmark-current-20261025/notion-update-response.json`。

## 结果

| 分辨率 / 并发数 | Native 分数 | Clientproxy 分数 | 分数保留比例 |
| --- | --- | --- | --- |
| 1280×720（1 Client） | 1561.00 | 1395.00 | 89.37% |
| 1280×720（2 Client 并发） | 811.00 | 832.00 | 102.59% |
| 1280×720（3 Client 并发） | 535.33 | 537.33 | 100.37% |
| 1280×720（4 Client 并发） | 384.50 | 381.50 | 99.22% |
| 1920×1080（1 Client） | 1129.00 | 1043.00 | 92.38% |
| 1920×1080（2 Client 并发） | 587.50 | 603.00 | 102.64% |
| 1920×1080（3 Client 并发） | 394.00 | 392.67 | 99.66% |
| 1920×1080（4 Client 并发） | 失败（GPU 超时） | 280.00 | — |

Native 的并发数是同一 Host 上的进程数，Clientproxy 是独立 Client Realm 数；分数均为同组各进程 / Client 的算术平均。
比例使用未四舍五入的均分计算；每配置只有一轮，不当作多轮稳定性结论。glmark 是离屏 null-noop / finish，不是屏幕帧率。

## 测试条件

- CPU policy0 的最低 / 最高 / 实际频率均为 1.8 GHz；GPU 请求 600 MHz、实际时钟 594 MHz。
- 两侧任务均按 CPU2 / CPU3 / CPU2 / CPU3 放置；Clientproxy 的 Proxy 在 CPU1，VMM I/O 在 CPU0。
- 使用同一 Host Image `6.12.0-opencca-pmthor-opp3 #31`、实际 SD 固件和 Mesa/glmark rootfs；Native 临时以 nVHE 启动，Clientproxy 使用 protected hVHE，结束后恢复。
- Clientproxy 沿用当前 1405 冻结组合，720p / 1080p 每 Client 池分别为 128 / 192 MiB；紧凑 RAM、round-robin、TRANSFER/telemetry 开启，阶段诊断计时关闭。
- 四 Client 沿用已有 `panthor.max_inflight_jobs=3`；Host Native 驱动没有此参数。这是两种现有实现的差异，不是本轮新增调优。
- 两侧使用相同的外部 Host 观察器，每 2 秒采样。每个有效计分窗口逐样本核验实际 CPU/GPU 频率，并检查共同计分窗口至少占总窗口 90%。
- Native 测试脚本中 glmark 路径与当前 initrd 一致；脚本版本差异只涉及未执行的 ML barrier。输入与观察器摘要保存在结果 JSON。

## 正确性与并发

| 运行方式 | 分辨率 | 并发数 | 各进程 / Client 分数 | 共同计分窗口 | 状态 |
| --- | --- | ---: | --- | --- | --- |
| Clientproxy | 720p | 1 | 1395 | 340.106 s / 100.00% | PASS |
| Native | 720p | 1 | 1561 | 338.840 s / 100.00% | PASS |
| Clientproxy | 720p | 2 | 826 / 838 | 341.250 s / 99.99% | PASS |
| Native | 720p | 2 | 812 / 810 | 338.943 s / 100.00% | PASS |
| Clientproxy | 720p | 3 | 399 / 809 / 404 | 341.631 s / 96.81% | PASS |
| Native | 720p | 3 | 407 / 783 / 416 | 339.077 s / 97.44% | PASS |
| Clientproxy | 720p | 4 | 358 / 396 / 372 / 400 | 350.760 s / 99.75% | PASS |
| Native | 720p | 4 | 521 / 357 / 423 / 237 | 347.451 s / 99.03% | PASS |
| Clientproxy | 1080p | 1 | 1043 | 340.402 s / 100.00% | PASS |
| Native | 1080p | 1 | 1129 | 339.080 s / 100.00% | PASS |
| Clientproxy | 1080p | 2 | 598 / 608 | 342.112 s / 100.00% | PASS |
| Native | 1080p | 2 | 588 / 587 | 339.246 s / 100.00% | PASS |
| Clientproxy | 1080p | 3 | 292 / 592 / 294 | 341.311 s / 96.90% | PASS |
| Native | 1080p | 3 | 340 / 571 / 271 | 339.457 s / 97.11% | PASS |
| Clientproxy | 1080p | 4 | 274 / 283 / 275 / 288 | 352.612 s / 99.73% | PASS |
| Native | 1080p | 4 | — | — | FAIL |

有效成绩均完成 33 场景，validation 为 26 成功 / 1 个已知数值例外 / 6 无判据，真实 Mali-G610 渲染，进程 / VM 退出码为 0。
独立核验日志 SHA、Host/Guest 内核健康、真实提前完成及快速通知路径、SGI 模块卸载、CPU / pmthor / 进程 / 挂载恢复。
本轮共校验 174 份远端采集文件，51 份源码与测试输入未变。

以下失败保留且不计入有效性能，未用历史分数补齐：

- `fixed-current-native-batch1-20261025-a`，native 1080p × 4：GPU 超时，`AssertionError((0, 125))`；2 条内核错误，详见结果 JSON。

Native 1080p 四进程的进程 0 / 2 出现提交错误并退出 125，进程 1 / 3 单项通过；内核记录两次 job timeout。269 / 308 / 238 / 306 是该异常批次输出，全部不作为四进程有效成绩。日志未见 OOM，不能把这次失败归因于内存不足；具体超时根因本轮未修复。

## 与先前结果的关系

720p 单 Client：历史 1405.00 → 本轮 1395.00，-10.00 / -0.71%。 1080p 单 Client：历史 1044.00 → 本轮 1043.00，-1.00 / -0.10%。
本轮加入两侧一致的外部 Host 采样，测试时段及单轮 / 多轮口径也有差异，不把分差归因为代码改变。
原混用动态与固定 CPU 策略的表格仍是历史记录，不能再据其百分比描述当前同频对照。

统一记录：完整重测同频图形对照｜上述历史单 Client → 本轮结果｜绝对 / 百分比分差如上｜
未改生产运行代码，新测全部 16 配置，两侧同频但 Native nVHE / Realm protected hVHE 及四 Client 在途参数差异保留｜
各 run-id、精确命令、退出码及日志如下｜保留当前代码，本轮结果不更新优化的独立收益归因。

## 命令与证据

全部运行经 `lab-run.py` 独占锁串行执行。Native 一个批次包含多个逐项测试；如果批次失败，保留失败项，再仅执行尚未执行的后缀。

### `fixed-current-realm-720-1c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-720-1c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 128 --transfer-capture --profiles glmark-720 --clients 1 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-720-1c-20261025-a/`。

### `fixed-current-native-batch1-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-native-batch1-20261025-a --allow-rk-reboot -- python3 build/fair-glmark-20261021/native-mode-controller-v4.py --round a --cases 720:1 720:2 720:3 720:4 1080:1 1080:2 1080:3 1080:4
```

外层退出码 `1`；状态 `FAIL`；结果及原始日志：`build/fair-glmark-20261021/native/fixed-current-native-batch1-20261025-a/`。

### `fixed-current-realm-720-2c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-720-2c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 128 --transfer-capture --profiles glmark-720 --clients 2 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-720-2c-20261025-a/`。

### `fixed-current-realm-720-3c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-720-3c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 128 --transfer-capture --profiles glmark-720 --clients 3 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-720-3c-20261025-a/`。

### `fixed-current-realm-720-4c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-720-4c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 128 --transfer-capture --profiles glmark-720 --clients 4 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-720-4c-20261025-a/`。

### `fixed-current-realm-1080-1c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-1080-1c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 192 --transfer-capture --profiles glmark-1080 --clients 1 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-1080-1c-20261025-a/`。

### `fixed-current-realm-1080-2c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-1080-2c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 192 --transfer-capture --profiles glmark-1080 --clients 2 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-1080-2c-20261025-a/`。

### `fixed-current-realm-1080-3c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-1080-3c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 192 --transfer-capture --profiles glmark-1080 --clients 3 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-1080-3c-20261025-a/`。

### `fixed-current-realm-1080-4c-20261025-a`

```bash
python3 scripts/maintenance/lab-run.py --run-id fixed-current-realm-1080-4c-20261025-a -- python3 build/fair-glmark-20261021/observe-run.py python3 scripts/run/run-realm-wake-sgi.py --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- python3 scripts/run/run-realm-xshm.py --images build/raw-fence-observation-20261024/candidate --workload glmark --performance --benchmark-only --suite --compact-memory --pool-mib 192 --transfer-capture --profiles glmark-1080 --clients 4 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

外层退出码 `0`；状态 `PASS`；结果及原始日志：`build/fixed-glmark-current-20261025/realm/fixed-current-realm-1080-4c-20261025-a/`。


外部频率原始采样：`build/fair-glmark-20261021/observations/<run-id>/`。
独占锁、前后资源、UART、Native 模式恢复及内核健康：`build/lab-runs/<run-id>/`。
结果、逐进程分数、并发窗口、实际频率、命令、输入和日志 SHA：
[`evidence/fixed-glmark-current-20261025/results.json`](evidence/fixed-glmark-current-20261025/results.json)。
测试控制记录及完整审计：`build/fixed-glmark-current-20261025/{matrix,audit}.json`。

最后以 `fixed-current-finalize-20261025-a` 执行 `restore-and-verify.py`，退出 0；
六项板端输入和实际 SD idbloader/u-boot 摘要与当前冻结组合一致，资源恢复通过。
本轮不新增 ML、长稳/reset 或安全矩阵测试，原有历史失败记录继续保留。
