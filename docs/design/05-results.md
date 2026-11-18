# 实验结果

## 1170 发布验收

| 项目 | 实测与范围 | 证据 |
| --- | --- | --- |
| 完整单 Client 720p | 1170，33 场景，validation 26 成功、1 项既有失败、6 项未知 | gpu-normalize2-720-r1-20261114，外层、负载、UART、两 Realm 均退出 0，9 份日志哈希通过 |
| 双 Client 功能 | 每端 4 × 65536 值，真实 DRM，binary/timeline eventfd，IRQ 与端点负例通过 | gpu-normalize2-compute-r1-20261114，均退出 0，10 份日志哈希通过 |
| 离线检查 | 常规 62 项通过，另复验汇总检查后累计 63 项 | gpu-normalize2-full-offline-r5-20261114 常规项通过、汇总失败；gpu-normalize2-aggregate-r6-20261114 汇总退出 0 |
| 四 Client 1080p | 256 / 234 / 252 / 233，各 33 场景，计分重叠 99.63% | 冻结包后续专门实测，一轮 |
| 真实 ResNet50 | 官方 ONNX 权重，FP32，5 次预热 + 100 次，均值 1597.032 ms，全部 1000 输出逐轮与 CPU 比较 | gpu-trained-resnet50-r8-20261114；单次长运行，非数据集准确率测试 |

发布计分为 RK3588 / Mali-G610、Mesa 25.0.7、实际 GPU 594 MHz、固定 720p 负载，配额为 8。关键场景为模糊 211、terrain 38、refract 137。对第一阶段 1163 增加 7 分（0.60%），仅计入匹配 RMM、Client 和 Proxy 的成套变化。保留原始失败与验证未知。[详细验收](../shared/GPU_CODE_NORMALIZATION_AND_CLEANUP_20261114.md)

## 共享、分时直通和 virtio 对照

正式扩展共 174 个独立审计批次、1044 行 Client 工作负载。此表图形是单用户普通完整 33 场景，直通成绩只统计设备在手期间。模型为单应用线程，每方案三独立批，FP32 固定权重、逐项校验。

| 指标 | 本项目共享 | Realm 分时直通 | virtio |
| --- | ---: | ---: | ---: |
| 360p glmark | 1435 | 464 | 171 |
| 720p glmark | 1158 | 207 | 79 |
| 1080p glmark | 914 | 91 | 78 |
| ResNet50，ms/extract | 1699.605 | 1898.390 | 964.474 |
| MobileNetV2，ms/extract | 46.280 | 51.164 | 49.863 |

图形 virtio 使用 virgl，模型使用通过实际硬件资格检查的 Venus。共享与直通为 protected hVHE，virtio 对照为独立 nVHE，Host 运行后端。正式图形对照固定 CPU 1.8 GHz、GPU 实际 594 MHz。GLES 版本、深度格式、Host 后端预算和直通排队仍有差异。1158 属于该批次，1170 属于发布验收。真实模型平均延迟按独立批计，不能把批内多个输出当成独立启动。Native 数据来自 2026-10-18 的历史驱动与共享池配置，本次未重跑。[扩展实验全文](../shared/GPU_COMPREHENSIVE_EXPERIMENT_RESULTS_20261114.md) · [全项目性能汇总](../shared/GPU_PERFORMANCE_EXPERIMENT_SUMMARY_20261118.md)

## 复验发布载荷

~~~sh
python3 scripts/artifacts/restore-runtime.py \
  --manifest baselines/gpu-1170-20261114/manifest.json \
  --dest build/gpu-1170-20261114
python3 scripts/artifacts/restore-runtime.py \
  --manifest baselines/gpu-1170-20261114/manifest.json \
  --dest build/gpu-1170-20261114 --check
~~~

在板端身份、匹配 Host、FIT、rootfs 和资源核对通过后，测试走独占入口。复验用新的 run-id，验收的原始记录保留在控制机的 build/lab-runs/gpu-normalize2-720-r1-20261114。

~~~sh
python3 scripts/maintenance/lab-run.py --run-id gpu1170-reproduction-720-r1 -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/gpu-1170-20261114/graphics-runtime \
  --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-720 --session-quota 8 --security-selftests
~~~

发布分支复核原验收源文件、配置和成套载荷。整理文档与发布校验均无新增硬件性能测量。[匹配环境及来源](../shared/CURRENT_BASELINE.md)

## 发布检出复核

| 记录 | 结果与范围 | 证据位置 |
| --- | --- | --- |
| 载荷恢复与源码对账 | 恢复命令和复验命令均退出 0。11 项载荷和 38 份验收源码的哈希匹配，OpenCCA 补丁复核、固件布局和 FIT 核对通过 | 发布清单及源码哈希 |
| gpu1170-release-scoped-20261118 | 队列完整性、回复重放、迟到 waiter、RPC 工作预算、本地 IRQ-work、C 源码提取、资源恢复契约，退出 0 | build/security-runs/gpu1170-release-scoped-20261118 |
| gpu1170-release-offline-20261118 | 全量检查 57 项通过、6 项失败，退出 1。定位到源码提取、历史测试替身与测试依赖的版本不匹配 | build/security-runs/gpu1170-release-offline-20261118 |
| gpu1170-release-offline-fix-20261118 | 复验中的 RSI 边界、任务桥、内存链、Realm 生命周期和任务恢复均通过。汇总项发现缺失 Group 状态测试源码，整轮退出 1 | build/security-runs/gpu1170-release-offline-fix-20261118 |
| gpu1170-release-aggregate-20261118 与 gpu1170-release-aggregate-r2-20261118 | 补齐依赖后 Group 状态 31 项通过，汇总随后遇到域归还夹具的版本差异，两轮均退出 1。匹配版域归还 4 项、runner 52 项和 eventfd 25 项定点复验通过 | build/security-runs/ 下对应 run-id，定点记录在 build/checker-trial |

离线检查入口为 python3 scripts/run/run-gpu-security-offline.py --verify-runtime --include-aggregate；定点检查通过 --only 选择。复核修订限打包和测试夹具。原始失败和历史验收分别保留。
