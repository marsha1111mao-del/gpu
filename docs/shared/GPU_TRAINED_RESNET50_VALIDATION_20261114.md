# 官方真实权重ResNet50：GPU推理与完整数值校验

本轮成功运行官方训练权重的ResNet50，并在真实Mali-G610/PanVK安全共享路径完成5次预热和100次正式推理。每次GPU输出全部1000项都与同一Client内的CPU参考比较；最大绝对误差约5.72×10⁻⁶，相对L2误差约6.47×10⁻⁷，top-1一致。

这补充了更真实的模型工作负载证据。输入采用固定、可重复的合成张量，验证的是数值执行和运行稳定性，不是ImageNet数据集精度；Vulkan后端及实际GPU发布/IRQ有证据，不声称每个层都必然在GPU执行。此前空权重benchncnn与本轮任务不同，不将两者耗时直接相除作为性能改进。

## 固定来源

| 输入 | 固定值 |
| --- | --- |
| 模型源 | ONNX官方模型库，提交 `c5cae0f1942c8d7727372c7b1f6b485aa39e4421` |
| 路径 | `validated/vision/classification/resnet/model/resnet50-v1-12.onnx` |
| ONNX | 102576593字节；SHA256 `3f03fdef724b22947eed826f1eef1dc5c34151bb4c37d634f1db89dfa2dd1526`，与官方LFS指针一致 |
| 转换工具 | 官方PNNX发布20260526，archive SHA256 `dde08ce2e2e1744a4ddce576910b451a860663af91d2aeed0d21ebee4fa69955` |
| 转换参数 | `inputshape=[1,3,224,224] fp16=0` |
| NCNN权重 | 102122104字节；SHA256 `b51c85fa999e10ada1e4e13995b13ef5d33954d2092f7b87dac4e3b18e9c079c` |
| NCNN图 | SHA256 `6facdd35e4ec0a63bd60fdeae284fef32aca45f5a4b7adb7cf7894183b07c18f`，真实权重加载，不使用空权重模式 |
| NCNN源码 | 固定20260526归档，对应仓库来源提交 `e54f7b1f88434e1d844ea0551b880a1cfb079ce1`，归档与构建清单哈希单独保存 |
| 探针 | `GPU-SFTP/tests/ncnn-bench/trained_model_check.cpp`，链接目标工作负载数学库；ARM64二进制SHA256 `111d4409475a51d66d3b45b8321b5bfb8d715157091ed31cfd74a3c57de9354d` |

来源：[ONNX固定模型](https://github.com/onnx/models/tree/c5cae0f1942c8d7727372c7b1f6b485aa39e4421/validated/vision/classification/resnet)、[PNNX固定发布](https://github.com/pnnx/pnnx/releases/tag/20260526)、[NCNN固定提交](https://github.com/Tencent/ncnn/commit/e54f7b1f88434e1d844ea0551b880a1cfb079ce1)。

## 本轮条件与结果

| 条件 | 实际设置 |
| --- | --- |
| 运行路径 | protected hVHE、Client私有BO/RMM授权、Proxy编排，实际Mali-G610/PanVK |
| 成套代码 | 与已验收第二阶段相同的RMM/Client/Proxy，未因模型任务删除权限、完成或回收条件 |
| 设备 | Mali-G610，driver=panvk，API字段4198705 |
| Client | 1 vCPU、768 MiB RAM、28 MiB CMA，固定控制池2049页；较图形476 MiB是显式的大模型条件差异 |
| GPU | 请求600 MHz，实际594 MHz，结束恢复原策略和300 MHz |
| 数值 | 输入1×3×224×224，固定生成规则；FP32，fp16/bf16/packing关闭，CPU参考单线程 |
| 测量 | 5次预热不计分，100次Client wall-clock完整extract计时，包含该次输入/执行/输出归还及软件等待；模型加载、初始CPU参考不纳入单次GPU延迟 |
| 计时统计 | min 1571.590 ms，median 1599.502 ms，p95 1611.595 ms，max 1619.493 ms，mean 1597.032 ms |
| 完整输出 | 每轮全部1000项有限值；最大绝对误差5.7220459e-6，相对L2 6.47232384e-7，cosine 1.0，top-1=807与CPU一致 |

CPU参考只在Client中作为数值依据，没有作为Host Native性能基准测量或给出新的Native分数。当前是一次100样本运行，支持列出的延迟分布和执行正确性，不声称跨运行/平台统计置信区间。模型格式转换成功本身也不是ONNX与NCNN独立精度等价证明，本轮主要比较同一实际NCNN图的CPU/GPU输出。

## 安全与结束检查

原有实际Group/观察边界、会话预算8、真实物理IRQ/Proxy错误声明拒绝、队列发布、根比较/AS扫描、受保护控制CPU视图等启用门槛通过。没有新增IRQ丢失/溢出，Kernel无新增异常；控制通道解绑/撤销、Realm退出及CPU/驱动/频率/挂载/loop恢复通过。

这些证据覆盖正常真实模型与已有协议路径；不提升MEM05恶意shader/完整命令语义/消费期间一致性或完整物理CPU/DMA/GIC/整设备清理的既有保证。

## 命令与证据

run-id：`gpu-trained-resnet50-r8-20261114`。外层、工作负载、UART及两Realm退出均0，9份远端/本地日志SHA一致。完整命令为 `session-run.py`、`lab-job.py`、`lab-run.py`、`run-with-uart.py`、`research/run-trained-profile-r8.py`，最终调用 `run-realm-xshm.py --workload glmark --performance --benchmark-only --suite --profiles ncnn-trained-resnet50 --clients 1 --session-quota 8 --security-selftests`，使用独立已核验真实权重rootfs。

实际参数、退出码和资源在 `build/lab-runs/gpu-trained-resnet50-r8-20261114/`；收集日志、模型输出和SHA在 `build/gpu-normalization-20261114/runs/gpu-trained-resnet50-r8-20261114/`。权威审计为 `research/trained-resnet50-runtime-audit.json`，模型/工具链为 `research/trained-model-provenance.json`、`resnet50-converted/conversion.json`、`trained-probe-target-library-audit.json`。

专用rootfs实际SHA256 `42b8cacea926474fe28ece4a52a7b1217481b827948e8064f2960640b70b56a0`，原基线rootfs不修改。首次准备中的工具/库依赖问题只保留简短失败账本和原始日志，成功结论仅来自上述通过轮次。后续仍应补充更多大型任务与跨轮结果。

探针源码随后统一排版，C++ token序列及重新链接后的 `.text/.rodata/.data/.data.rel.ro` 均与已测二进制一致；已测原始二进制保持在 `research/trained-probe-source-normalization/validated-binary`，证明在同目录 `source-proof.json`。本项未新增推理成绩，不把源码排版当作另一次硬件运行。

## 从固定SDK重建探针

规范构建入口为 `scripts/build/build-trained-model-check.sh`，CMake定义在 `GPU-SFTP/tests/ncnn-bench/CMakeLists.txt`。它链接目标Guest实际数学库，避免把交叉工具链较新的glibc带入Guest。SDK和工具链须来自上述固定NCNN来源，不下载latest。

```bash
NCNN_CMAKE_DIR="$PWD/build/gpu-normalization-20261114/research/ncnn-trained-sdk/lib/cmake/ncnn" \
NCNN_TOOLCHAIN_FILE="$PWD/build/gpu-normalization-20261114/research/ncnn-trained-source/toolchains/aarch64-linux-gnu.toolchain.cmake" \
TRAINED_PROBE_BUILD_DIR="$PWD/build/gpu-normalization-20261114/research/canonical-trained-probe" \
scripts/build/build-trained-model-check.sh
```

该规范入口的Release构建已成功；硬件结果仍对应上文SHA指定的已测二进制。新构建产物未据此继承硬件PASS或逐字相同结论。要用于新的实机测量，应记录新二进制/SDK/库哈希并重新执行完整数值校验；基础rootfs不替换libc。
