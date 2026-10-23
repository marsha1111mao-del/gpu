# Native 动态调频 glmark 复测

状态：**VERIFIED**。11 个新有效样本加 1 个同条件历史复用样本，范围内无缺失、无 GPU 超时；另有 2 项在计分前取消。独立核验、Pi/RK 资源及 Host 恢复检查均退出 0。

## 测量范围与口径

按用户最新要求，只复测 Native：720p 的 1–4 进程，以及 1080p 的 1、4 进程，
每项采用两次有效测量，共 12 个样本。按用户“已测不要重复”的要求，720p 单进程
采用本次 A 的 1435 与已验收历史动态样本 1428，取消尚未计分的本次 B；其余为本次
A/B。复用样本来自 `native-origin-cpufreq-20261022-a/native-720-1p-schedutil-a`，
已重新核对其原始日志、输入哈希、频率、绑核、正确性、健康及恢复；它不是本次新 B 轮。
1080p 的双、三进程不再复测，保留原固定频率两轮
Native 均分 587.75 / 394.50，并在表内注明历史条件；没有验证其动态调频成绩不变。
Clientproxy 八项均沿用[原固定频率对照](GPU_FAIR_MULTICLIENT_GLMARK_20261021.md)。

每轮先对同组进程分数取算术均值，再取 A/B 均值；仅两轮全部有效才发布新均分及
保留比例。比例使用未四舍五入的同分辨率、同并发数均分计算。GPU 超时整组无效，
失败后只补未执行配置，不重试该失败来替换结果。

本次未修改 GPU 运行代码，未重新构建或部署 Host/Guest/RMM；新增的是 Native
调频测量，不是代码优化提分。两列时段、CPU 策略及 RMM 组合不同，不能称为同期
同频公平比较，也不能从该比例单独推断代理开销。

## 条件与观察方法

| 条件 | 本次 Native | 保留的 Clientproxy |
| --- | --- | --- |
| 平台 / Host | RK3588，6.12.0-opencca-pmthor-opp3 #31 | 同一板、同 Host Image |
| Host 模式 | nVHE，结束恢复 protected | protected hVHE |
| CPU | CPU0–3 在线，policy0 schedutil，1008–1800MHz | 固定 1.8GHz |
| 负载放置 | CPU2 / 3 / 2 / 3 | 相同；Proxy CPU1、VMM I/O CPU0 |
| GPU | 请求 600MHz，观测实际 594MHz | 相同 |
| 工作负载 | 完整 33 场景，null-noop / finish，禁用 shader cache | 同一 glmark/Mesa/rootfs |
| RMM | 通知计时版，2 GiB GPU 租约元数据容量 | timer-v6，1 GiB 容量 |
| 进程同步 | 验证结束后统一放行整套计分；无逐场景屏障 | 相同 |

Native 直接使用 Panthor，不经 Client/Proxy RPC；此次 RMM 组合差异仍披露，
不将它当作代理热路径的单变量对照。Native 每进程独立只读 chroot 和私有 tmpfs。
旧 Clientproxy 的池大小、内存公式及 GPUVM 实现保持其原测试条件。

Host 每两秒记录 governor、频率边界、当前频率、time_in_state、GPU 实际时钟、
线程亲和性和温度。驻留分布采用共同计分窗口内首末计数差，不能用稀疏瞬时采样
均为 1.8GHz 推断整个窗口始终锁频。各组共同计分窗口至少占联合窗口的 90%。

## 结果

Clientproxy 八项分数未重测；720p 单进程含历史复用，1080p 双、三进程 Native 仍为
固定频率历史值。其余 Native 为本次动态调频两轮成绩。

| 分辨率 / 并发数 | Native 分数 | Clientproxy 分数 | 分数保留比例 |
| --- | --- | --- | --- |
| 1280×720（1 Client） | 1431.50（含历史复用） | 1158.00 | 80.89% |
| 1280×720（2 Client 并发） | 813.75 | 768.00 | 94.38% |
| 1280×720（3 Client 并发） | 532.33 | 498.33 | 93.61% |
| 1280×720（4 Client 并发） | 378.13 | 355.50 | 94.02% |
| 1920×1080（1 Client） | 1008.50 | 902.00 | 89.44% |
| 1920×1080（2 Client 并发） | 587.75（固定频率历史值，未复测） | 597.50 | 101.66% |
| 1920×1080（3 Client 并发） | 394.50（固定频率历史值，未复测） | 387.17 | 98.14% |
| 1920×1080（4 Client 并发） | 277.38 | 276.63 | 99.73% |

| Native 配置 | 本次 A 各进程分数 | 本次 B 或注明的历史样本 | 两次均值 |
| --- | --- | --- | --- |
| 720p / 1 | 1435 | 1428（历史动态样本，本次 B 取消） | 1431.50 |
| 720p / 2 | 818 / 814 | 815 / 808 | 813.75 |
| 720p / 3 | 594 / 768 / 239 | 598 / 763 / 232 | 532.33 |
| 720p / 4 | 168 / 446 / 376 / 535 | 421 / 344 / 331 / 404 | 378.13 |
| 1080p / 1 | 1011 | 1006 | 1008.50 |
| 1080p / 4 | 352 / 133 / 223 / 405 | 276 / 312 / 169 / 349 | 277.38 |

有效样本共同计分窗口最低 97.47%；完整 33 场景、真实 Mali renderer、validation
26 成功 / 1 既有数值例外 / 6 无判据、clean、各有效进程退出 0、完整新增内核日志
与 SHA 收集核验通过。进程间仍有明显分差，不将分数之和解释为纯 GPU 总吞吐。

### 相对原固定频率结果

| Native 配置 | 原固定 1.8GHz → 动态调频 | 绝对变化 | 百分比变化 |
| --- | --- | --- | --- |
| 720p / 1 | 1560.50 → 1431.50（含历史复用） | −129.00 | −8.27% |
| 720p / 2 | 812.50 → 813.75 | +1.25 | +0.15% |
| 720p / 3 | 536.67 → 532.33 | −4.33 | −0.81% |
| 720p / 4 | 原 B 超时 → 378.13 | — | — |
| 1080p / 1 | 1130.00 → 1008.50 | −121.50 | −10.75% |
| 1080p / 4 | 原 A/B 均超时 → 277.38 | — | — |

改动目的｜补齐动态调频 Native 分母，复用已验收样本避免重复｜分差见上表｜CPU
策略变化，且与原固定矩阵的时间、顺序及 RMM 组合不同；仅比较这组条件下的成绩，
不作本轮单变量因果归因｜命令、退出码、run-id 和日志见下表及 matrix.json｜保留测量；
未改 GPU 运行代码，不宣称代码提分，也不由本次四进程 PASS 宣称旧 GPU 超时已修复。

| Native 配置 | A 计分窗口 1.8GHz 驻留 | B / 历史样本计分窗口 1.8GHz 驻留 |
| --- | --- | --- |
| 720p / 1 | 70.66% | 70.16%（历史） |
| 720p / 2 | 90.22% | 91.66% |
| 720p / 3 | 92.92% | 92.96% |
| 720p / 4 | 93.78% | 93.57% |
| 1080p / 1 | 51.32% | 49.93% |
| 1080p / 4 | 83.06% | 83.13% |

本次 Native 单进程有明显低频驻留，多进程更接近最高频率。单进程分数与已完成的
[Native 调频反切实验](GPU_NATIVE_SCORE_ORIGIN_20261022.md)一致；该因果实验无需重跑。
单 Client 动态策略仍维持最高频率的证据沿用
[既有 Client 调频对照](GPU_CLIENT_CPU_FREQUENCY_RESPONSE_20261022.md)，本轮未重测代理路径。

## 范围调整与恢复

原 A 批已经启动时，用户取消 1080p 双、三进程复测。控制机冻结原脚本并暂停原
后续编排，待 1080p 单进程 A 完成后，只向该批精确 Native runner PID 发送 SIGINT。
1080p 双进程 A 尚未进入计分，事件中没有 start，原 finally 完成子进程、挂载及
loop 清理。原始摘要如实保留 KeyboardInterrupt 和非零退出码；独立核验将其归类为
范围取消，不列为 GPU 超时。恢复 protected 后，再以独立批次执行 1080p 四进程 A。
B 轮顺序为 1080p 四/单进程、720p 四/三/双/单进程；若失败，恢复后只补后缀。

用户进一步要求复用已测成绩后，B 批末尾的 720p 单进程也在计分前取消，改用历史
1428。两个取消项的事件均没有计分 start，均保留 KeyboardInterrupt、原始摘要及批次
非零退出码。冻结中的 runner 未改动，额外控制器单独记录 SHA。未重跑失败配置，
未重复执行原固定矩阵或 Clientproxy；取消后没有追加硬件计分。

每个批次通过 lab-run 获取独占锁，保留 SD kernel 分区与 extlinux 备份、UART、
Image 哈希和模式恢复证据。没有刷写 Host/RMM 镜像。结束核对 protected、CPU0–1、
pmthor、无本轮残留进程/挂载/loop，以及 Pi/RK 资源。

| run-id | 原始批次退出码 | 采信内容及恢复 |
| --- | --- | --- |
| native-dynamic-a1-20261022 | 255 | 5 项有效；1080p 双进程 A 计分前取消；模式、资源恢复 PASS |
| native-dynamic-a2-20261022 | 0 | 1080p 四进程 A 有效；模式、资源恢复 PASS |
| native-dynamic-b1-20261022 | 255 | 5 项有效；720p 单进程 B 计分前取消；模式、资源恢复 PASS |
| native-origin-cpufreq-20261022-a | 0（历史） | 仅复用 schedutil 的 1428；原固定两项不计入动态矩阵；原验收与恢复 PASS |

两项取消所在批次的外层 FAILED / rc255 如实保留，不改写为退出 0；独立审计
逐项核对有效进程 rc0、健康及取消原因后，将范围内 12 个有效样本判为 VERIFIED。

## 命令与证据

实验目录：`build/native-dynamic-glmark-20261022/`。原始与缩减编排命令及退出码
在 `matrix.json`、`build/lab-runs/<run-id>/{result,native-mode,before,after}.json`；
日志与 SHA 收集清单在 `native/<run-id>/`，观测在 `observations/<run-id>/`。
冻结输入见 `controller-hashes.json`、`reduced-controller-hashes.json` 和
`reuse-controller-hashes.json`；范围取消记录为 `scope-stop.jsonl`、`reuse-stop.jsonl`，
历史复用核验为 `historical-reuse-check.json`，最终资源为 `final-resources.json`。
历史失败仍见原固定频率报告，不被本次 PASS 改写。

```bash
python3 scripts/analysis/summarize-dynamic-native-glmark.py \
  --experiment build/native-dynamic-glmark-20261022 \
  --reference build/fair-glmark-20261021 \
  --output build/native-dynamic-glmark-20261022/analysis
```

仅运行中查看已回收批次时可加 `--allow-incomplete`；正式发布必须缺失项为零。
原始日志不提交，核验摘要为 `analysis/audit.json`，表为 `analysis/table.md`。

[Notion 多Client并行测试结果合集](https://app.notion.com/p/3ff659a3b8cc813bbab7c109be10ad21)
已更新并回读核验全部 36 个表格单元格；历史复用与未复测标注正确，原 ML/NCNN
结果、原因及内存部分逐字不变。最终记录 `final-audit.json` 为 PASS。
