# 当前版本 ML：Native 与 Clientproxy 同频对照

Notion 已同步：[多Client并行测试结果合集](https://www.notion.so/3ff659a3b8cc813bbab7c109be10ad21)与[优化全解第 15 节](https://www.notion.so/404659a3b8cc81c3ad40d50169107942)。两页定向更新均成功，原有 10 张图保留。

2026-10-26，使用产生完整 glmark 同频矩阵的同一 **1405 冻结组合**：720p 单 Client 1395，1080p 单 Client 1043。重新比较同任务、同并发数的 Native 与 Clientproxy，不复用历史 Native 分母。

未改生产运行代码，无新增 GLMark 测量，也不将本轮 ML 对照作为某项优化的消融实验。

## 测量条件

- Native N 个进程，对照 N 个独立 Client Realm，共享同一 GPU。
- 两侧 CPU 固定 1.8 GHz；GPU 请求 600 MHz，实际 594 MHz。工作负载按 CPU2/3/2/3 绑定；Native NCNN 额外使用 cpuset 强制约束，防止其库重设线程亲和性。Clientproxy 另有 CPU1 上的 Proxy，VMM I/O 在 CPU0。
- 同一只读 rootfs、Mesa、模型、算子程序及当前 initrd 中提取的测试脚本。Native 使用同一 Host Image 的 nVHE 模式，Realm 使用 protected hVHE 模式；结束后恢复原启动配置。
- 主表每个配置使用一轮独立验收结果；无效和异常批次另行保留，不混入均值。主表为每参与者迭代平均耗时的算术平均；耗时越低越好，性能保留比例为 `Native 平均耗时 / Clientproxy 平均耗时 × 100%`，使用未舍入值计算。
- GLES 算子通常 100 次、5 次预热；Attention-320 为 10 次、2 次预热。计时包括 dispatch、barrier、glFinish 和结果 map/unmap，不是纯 GPU 时间。预热后统一释放计时屏障，并检查共同执行窗口。
- GLES 均为 FP32：GEMM 512，卷积 64×64×32 / 3×3，深度卷积 128×128×128 / 3×3，Reduction 32 MiB，Softmax 16384×256，Attention 256/320×64。三个 NCNN 模型输入均为 224×224×3。
- NCNN 为 100 次、2 线程、panvk-direct，必须通过 Vulkan 后端资格检查。随机输入与空权重用于性能测量，不验证模型精度。并发屏障位于工作负载入口，共同窗口包含资格检查和加载，不将其描述为精确的推理迭代并发吞吐。
- 常规项目每 Client 128 MiB 共享池；ResNet50 的 1–3 Client 为 384 MiB，4 Client 为 336 MiB，启用目标后备页回收。四 Client 保留现行 `panthor.max_inflight_jobs=3`，Native 无对应限制。
- 关闭阶段诊断计时与 ML telemetry，保留 TRANSFER_CAPTURE。两侧均每 2 秒采样频率；观察器实现不同。短于采样周期的窗口用前后最近样本核对，不能宣称窗口内连续采样。

单轮结果不能证明统计显著性；超过 100% 不表示 GPU 算力增加，也不说明所有 Client 的公平性相同。

## 测试结果

| 任务 / 并发数 | Native 耗时（ms） | Clientproxy 耗时（ms） | 性能保留比例 |
| --- | ---: | ---: | ---: |
| GEMM / 1 | 28.96 | 29.28 | 98.89% |
| GEMM / 2 | 57.80 | 57.73 | 100.12% |
| GEMM / 3 | 失败（GPU 超时） | 76.37 | — |
| GEMM / 4 | 失败（GPU 超时） | 109.91 | — |
| 卷积 / 1 | 33.43 | 33.84 | 98.79% |
| 卷积 / 2 | 66.68 | 65.95 | 101.09% |
| 卷积 / 3 | 77.69 | 87.06 | 89.23% |
| 卷积 / 4 | 失败（GPU 超时） | 132.03 | — |
| 深度卷积 / 1 | 21.41 | 24.05 | 89.04% |
| 深度卷积 / 2 | 43.21 | 43.05 | 100.36% |
| 深度卷积 / 3 | 51.56 | 56.63 | 91.04% |
| 深度卷积 / 4 | 65.35 | 79.85 | 81.85% |
| Reduction / 1 | 10.25 | 10.62 | 96.55% |
| Reduction / 2 | 19.44 | 19.27 | 100.89% |
| Reduction / 3 | 23.29 | 26.26 | 88.70% |
| Reduction / 4 | 28.79 | 35.01 | 82.23% |
| Softmax / 1 | 19.20 | 19.92 | 96.38% |
| Softmax / 2 | 38.35 | 38.34 | 100.02% |
| Softmax / 3 | 45.26 | 49.62 | 91.21% |
| Softmax / 4 | 57.47 | 62.60 | 91.80% |
| Attention-256 / 1 | 776.73 | 776.99 | 99.97% |
| Attention-256 / 2 | 1544.29 | 1552.70 | 99.46% |
| Attention-256 / 3 | 失败（GPU 超时） | 2178.50 | — |
| Attention-256 / 4 | 失败（GPU 超时） | 失败（GPU 超时） | — |
| Attention-320 / 1 | 1224.24 | 1223.13 | 100.09% |
| Attention-320 / 2 | 2392.02 | 2387.08 | 100.21% |
| Attention-320 / 3 | 失败（GPU 超时） | 3338.76 | — |
| Attention-320 / 4 | 失败（GPU 超时） | 失败（GPU 超时） | — |
| MobileNetV2 / 1 | 29.87 | 31.36 | 95.25% |
| MobileNetV2 / 2 | 59.74 | 60.30 | 99.07% |
| MobileNetV2 / 3 | 50.04 | 54.76 | 91.38% |
| MobileNetV2 / 4 | 94.32 | 115.52 | 81.64% |
| MobileNetV3 / 1 | 26.57 | 28.06 | 94.69% |
| MobileNetV3 / 2 | 54.14 | 53.92 | 100.42% |
| MobileNetV3 / 3 | 45.89 | 46.81 | 98.05% |
| MobileNetV3 / 4 | 90.92 | 失败（GPU 超时） | — |
| ResNet50 / 1 | 1148.49 | 1529.83 | 75.07% |
| ResNet50 / 2 | 1249.76 | 2771.58 | 45.09% |
| ResNet50 / 3 | 1872.09 | 3135.51 | 59.71% |
| ResNet50 / 4 | 2131.85 | 5598.40 | 38.08% |

两侧各 40 个配置均已尝试。Native **33/40** 通过，Clientproxy **37/40** 通过，**32 行**可计算比例。逐参与者耗时、共同窗口、频率样本及状态见[机器摘要](evidence/native-ml-current-20261026/results.json)。失败项没有有效性能比例；通过项目仅证明本轮配置，不推广为长稳保证。

ResNet50 的有效对照为：1 并发 75.07%、2 并发 45.09%、3 并发 59.71%、4 并发 38.08%。当前 glmark 接近原生的结果不能推广到所有 ML 工作负载；本轮没有 RPC、CPU 或 GPU busy 的新增分项计时，不能由总耗时确定该模型的唯一瓶颈。

### 失败与排除

| 路径 | 任务 / 并发数 | 失败原因 | run-id |
| --- | --- | --- | --- |
| Native | GEMM / 3 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Native | GEMM / 4 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Native | 卷积 / 4 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Native | Attention-256 / 3 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Native | Attention-256 / 4 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Clientproxy | Attention-256 / 4 | GPU 超时及提交异常 | `ml-current-realm-4c-common-20261026-a` |
| Native | Attention-320 / 3 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Native | Attention-320 / 4 | GPU 超时及提交异常 | `ml-current-native-batch1-20261026-a` |
| Clientproxy | Attention-320 / 4 | GPU 超时及提交异常 | `ml-current-realm-4c-isolated-attention-320-20261026-a` |
| Clientproxy | MobileNetV3 / 4 | GPU 超时及提交异常 | `ml-current-realm-4c-clean-common-20261026-a` |

GPU 超时后的异常耗时不采信，恢复驱动后其他项目独立验收。首批 Native NCNN 的 12 项因库扩大 CPU 范围全部排除，最终使用 cpuset 补测。原批次和所有失败证据保留；不将失败后的低耗时、CPU 回退或未形成共同窗口的输出作为成绩。

四 Client ResNet50 首次在启动前被内存准入拒绝：需要 2808 MiB 加 Host 预留 256 MiB，共 3064 MiB，当时可用 3060.56 MiB，差约 3.44 MiB；没有创建 VM 或执行 GPU 任务。该次记录为 NOT_RUN_MEMORY，保留在机器摘要的 unexecuted_attempts。Native 补测恢复 protected 模式后的干净启动仅再尝试一次相同配置，不减少共享池、Host 预留或迭代数；主表采用随后独立验收的状态，不能用它覆盖首次拒绝记录。

四 Client ResNet50 复查的初始可用内存为 3082.60 MiB，运行期间 Host MemAvailable 最低采样为 **165.20 MiB**。配置中的 256 MiB 是启动准入估算的预留，实际可用内存可能低于该值；本轮存在明显内存压力，不将该配置描述成内存宽裕。

### 平均耗时与整批完成时间

主表衡量参与者平均迭代耗时。固定迭代次数时，一些参与者提前完成、其余继续运行，可能降低平均耗时，却没有同比缩短完成整批任务的时间。以预热后首个计时开始至最后一个计时结束的窗口作补充，窗口比例同样为 Native÷Clientproxy；同任务数与迭代数下，它更接近这批 GLES 工作的吞吐保留。

| 任务 / 并发数 | Native 整批窗口 s | Clientproxy 整批窗口 s | 窗口比例 | 主表比例 |
| --- | ---: | ---: | ---: | ---: |
| 卷积 / 3 | 10.010 | 10.076 | 99.35% | 89.23% |
| 深度卷积 / 3 | 6.570 | 6.599 | 99.56% | 91.04% |
| 深度卷积 / 4 | 8.733 | 8.908 | 98.03% | 81.85% |
| Reduction / 3 | 2.878 | 3.666 | 78.50% | 88.70% |
| Reduction / 4 | 3.802 | 4.156 | 91.49% | 82.23% |
| Softmax / 3 | 5.822 | 5.824 | 99.97% | 91.21% |
| Softmax / 4 | 7.720 | 7.849 | 98.36% | 91.80% |

不能把平均耗时比例下降全部归因于 RPC 或 Proxy CPU；需要同时看逐参与者分布和整批窗口。本轮没有新的 RPC、GPU busy 或 CPU 分项计时，不能据此确定唯一瓶颈。NCNN 的公共窗口含初始化和加载，不将它等同于精确的推理迭代吞吐。

## 证据与恢复

首批 Native NCNN 会自行修改线程亲和性，实测部分线程可访问 CPU0–3，因此该批 NCNN 耗时全部不进入最终表。补测使用独立 systemd scope 的 `AllowedCPUs`，在启动屏障检查 `cpuset.cpus.effective`，并采样实际线程亲和性；原始批次保留为无效对照证据。GLES 不受这一 NCNN 库行为影响，不为此重复有效 GLES 项目。

执行矩阵：原始计划为 `build/ml-native-current-20261026/matrix.json`，失败后续跑为同目录的 `resumed-matrix.json`。每项准确命令、退出码、run-id 与日志目录在这些文件及 `build/lab-runs/<run-id>/` 中。

Native 原始证据：`build/ml-native-current-20261026/native/<run-id>/`；Clientproxy 原始证据：`build/ml-native-current-20261026/realm/<run-id>/`。采集时核对远端与本地 SHA-256。失败、无效批次与未执行项分别保留，不用新 PASS 覆盖。

首批四 Client 常规批次先出现 Reduction 无共同计时窗口，随后 Attention-256 出现 GPU job timeout，整批性能作废。一次 SIGINT 落在 runner 的 grant 回收阶段，导致回收中断；按准确 PID/配置清理本次五个 Realm 后，在实验室锁内重启同一 SD 系统恢复。原始 summary 保持不变，另存 `audit-summary.json`，不将中断批次伪装成正常退出。恢复运行 `ml-current-reset-after-failure-20261026-a` rc0；该异常和补测安排见 `audit-notes.json`。

Client Image、Proxy Image 与 initrd 同原始冻结包逐字节一致。测试副本仅放开既有 ML 路径的固定频率与 round-robin 参数校验，未改 GPU 或 RPC 实现。原 runner 会在结束后恢复；最终需核对六项板端输入、实际 SD 固件、CPU 集合、驱动、进程、挂载及源码哈希。

### 完成审计

| run-id | 路径 | 外层退出码 | workload 状态 | 已核验文件 |
| --- | --- | ---: | --- | ---: |
| `ml-current-realm-1c-common-20261026-a` | clientproxy | 0 | PASS | 17 |
| `ml-current-native-batch1-20261026-a` | native | 1 | VERIFIED_WITH_FAILURES | 284 |
| `ml-current-realm-2c-common-20261026-a` | clientproxy | 0 | PASS | 28 |
| `ml-current-realm-3c-common-20261026-a` | clientproxy | 0 | PASS | 39 |
| `ml-current-realm-4c-common-20261026-a` | clientproxy | 1 | FAIL | 43 |
| `ml-current-realm-4c-clean-common-20261026-a` | clientproxy | 1 | FAIL | 40 |
| `ml-current-realm-4c-isolated-ml-gemm-20261026-a` | clientproxy | 0 | PASS | 18 |
| `ml-current-realm-4c-isolated-ml-conv-20261026-a` | clientproxy | 0 | PASS | 18 |
| `ml-current-realm-4c-isolated-ml-depthwise-20261026-a` | clientproxy | 0 | PASS | 18 |
| `ml-current-realm-4c-isolated-ml-softmax-20261026-a` | clientproxy | 0 | PASS | 18 |
| `ml-current-realm-4c-isolated-ncnn-mobilenet-v2-20261026-a` | clientproxy | 0 | PASS | 18 |
| `ml-current-realm-4c-isolated-reduction-window-20261026-a` | clientproxy | 0 | PASS | 18 |
| `ml-current-realm-4c-isolated-attention-320-20261026-a` | clientproxy | 1 | FAIL | 21 |
| `ml-current-realm-1c-resnet-20261026-a` | clientproxy | 0 | PASS | 9 |
| `ml-current-realm-2c-resnet-20261026-a` | clientproxy | 0 | PASS | 12 |
| `ml-current-realm-3c-resnet-20261026-a` | clientproxy | 0 | PASS | 15 |
| `ml-current-realm-4c-resnet-20261026-a` | clientproxy | 1 | FAIL | 3 |
| `ml-current-native-cpuset-batch1-20261026-a` | native | 0 | PASS | 88 |
| `ml-current-realm-4c-resnet-freshboot-20261026-b` | clientproxy | 0 | PASS | 18 |

上述共 **725 份**采集文件核对 SHA-256；其中首批 Native NCNN 的无效记录仅作证据保留，不进入主表。**51 份**源码/测试输入保持原样，测试前后六项板端输入和实际 SD 固件核验通过；Host 恢复原 protected 配置、CPU0–1、pmthor，无本次遗留 VM、挂载或 loop。最终恢复记录为 `ml-current-admission-finalize-20261026-b`，退出码 0。

统一记录：验证当前版本同并发 ML 性能｜相同任务 Native → Clientproxy，完整数据见主表｜按耗时计算保留比例，不作优化消融归因｜CPU1.8GHz/GPU594MHz；Native nVHE/Realm protected、四Client在途限制及NCNN屏障口径差异保留｜准确 argv、run-id、退出码与日志见矩阵和上述目录｜保留结果与失败证据；未改生产运行代码，无新增 GLMark 测量。
