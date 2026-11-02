# 新旧设计 baseline 分支归档（2026-11-02）

按用户要求，最后一次优化FX完整720p为972→980，+8／+0.82%，未达预设982保留线与1000门槛。已撤回并核验实际FU SD2固件及四Guest输入，停止追加优化实验。FX负例、失败回退与实际恢复见GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md的FX节。

| 分支 | 设计 | 已测720p |
| --- | --- | --- |
| [baseline/legacy-proxy-allocated-1158-20261102](https://github.com/marsha1111mao-del/gpu/tree/baseline/legacy-proxy-allocated-1158-20261102) | Proxy分配Client的GPU数据页，Client共享使用 | 1158／1158；用户指定Native参考1431.50、80.89% |
| [baseline/rmm-private-fu-ft-20261102](https://github.com/marsha1111mao-del/gpu/tree/baseline/rmm-private-fu-ft-20261102) | Client私有数据页、RMM真实GPU映射与安全控制、Proxy驱动服务 | 保留971／971，最新原版972；FX980撤回 |

旧分支从已发布9127c47分出，增加**精确1158分冻结镜像及固件**、SHA清单和可用实验源码补丁；旧源码为后续清理后的同设计正式版本。当时两份计量辅助源码已删除，仅存哈希，不声称能逐字节重建1158分二进制。已确认的7个主要驱动文件与当时源码哈希一致。此前保存的baseline/legacy-proxy-shared-20261102只是9127c47检查点，不作为指定1158载荷的入口。

新分支组件先推送，再由主仓库固定；旧main及其历史不改写。TF-A没有向上游推送，本地修改通过固定base／SHA的补丁manifest恢复。旧设计与新设计的CPU固定／自动频率、内存配置及安全功能不同，不能把1158与972相减归因于单一机制。

| 新设计组件 | 提交 |
| --- | --- |
| Linux-Guest-GPU | `8460fb93cdfc5f3d51723fa48cf6db45c165d2e5` |
| Linux-Host-GPU | `e3861585c7a2e2d72599905c24f817275761390f` |
| opencca/tf-rmm | `581fb1dc2505849e3eb1a3d148264e4acbc9bdb9` |
| opencca | `cdbc09c7e7b91cef8f3be675f1b4d2cb3ba6fff1` |

新恢复入口：[baselines/rmm-private-fu-ft-20261102/README.md](../../baselines/rmm-private-fu-ft-20261102/README.md)。旧恢复入口位于旧分支的baselines/legacy-proxy-allocated-1158-20261102/README.md。各自独立manifest恢复：新17份文件、旧11份文件逐项SHA验证；不把旧公共runtime-manifest误当成新FU包。实际部署仍遵循环境手册与lab-run独占、仅SD2、匹配Host release等要求。

版本归档未改运行代码，无新增性能测量。当前33场景validation26/1/6，健康／恢复通过，1000未达到；ML／完整API／多Client未扩展。原始日志、凭据和编译缓存不提交，仅提交冻结运行载荷、源码、哈希与脱敏结论。

归档检查见新baseline的checks.json：选定manifest的checkout检查rc0（94个脚本）、新17／旧11份载荷恢复及SHA校验、固定补丁检查通过。默认旧manifest与控制机历史缓存不一致的失败保留，使用明确manifest／目标目录验证新基线；不覆盖已有缓存，也不将未重跑的rootfs全量校验写成PASS。TF-A工作树的预期差异由新manifest补丁覆盖。
