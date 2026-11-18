# 当前发布基线

完整 720p glmark2 实测 **1170 分**，run-id 为 gpu-normalize2-720-r1-20261114。使用 RK3588、Mali-G610、Mesa 25.0.7、GPU 实际 594 MHz 和匹配的 Client/Proxy/RMM。Host 为 6.12.0-opencca-pmthor-opp3 protected hVHE。完整 33 场景的 validation 为 26 成功、1 项既有失败、6 项未知。[完整验收与复验命令](../design/05-results.md)

## 源码与固定载荷

- Guest 和 OpenCCA 以本提交的子模块指针为准。OpenCCA 再固定 tf-rmm 与上游补丁清单。Host、Firecracker 和第三方依赖沿用固定提交。
- [发布清单](../../baselines/gpu-1170-20261114/manifest.json)记录实测 Client/Proxy Image、图形 initrd、图形 runner、RMM、Monitor 和 FIT。按[复验步骤](../design/05-results.md#复验发布载荷)恢复独立目录。常规 bootstrap 提供历史参考、用户态及 rootfs。
- [源码哈希](../../baselines/gpu-1170-20261114/source-hashes.json)保留原验收的 38 项。[Client 配置](../../baselines/gpu-1170-20261114/client.config)和 [Proxy 配置](../../baselines/gpu-1170-20261114/proxy.config)来自实测 Image。编译器为 GCC 15.2.0，实测内置 release 为 6.12.0-g8460fb93cdfc-dirty。重新构建的 SCM 后缀与时间戳可变化，以清单核对实测镜像。
- 按[环境与测试手册](../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)确认板端 FIT、Host 内核及模块匹配。板端操作走统一独占入口。

## 证据范围

匹配构建通过双 Client DRM、计算及 eventfd。原离线验收累计 63 项，含补跑汇总项，仍有 4 项物理结论待验证。PL330 DMA 旁路、raw-CSF 故障影响其他 Client 后续可用性以及历史 Group fence 超时的记录仍有效。本次发布无新增硬件性能测量。[安全与证据](../design/03-security.md)

[设计与实验目录](../design/README.md) · [优化决策](../design/04-optimization.md) · [历史 FU/FT 冻结](../../baselines/rmm-private-fu-ft-20261102/README.md)
