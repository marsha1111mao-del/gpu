# GPU 安全服务开发检查点

按用户要求，先提交并推送当前开发代码，再开展GPUVM强化。组件先发布，核对远端SHA后更新父仓库指针；不改写历史，不更新上游版本。

| 组件 | 已发布提交 |
| --- | --- |
| RMM | `46f6ff99780084066929e14d51e46f29b57ac0a2` |
| Guest | `887ac029c87bac0a49975766737f16b4044d371d` |
| Host | `64510307c4ae432447d60a0e3735616dbce4e310` |
| OpenCCA | `2c1dd993b317bbdd881db7d217c874f376ac4f00` |
| Firecracker | `250f1493b5050c88b91c346c7af03e1134d8123f`，未改动 |

本检查点固定统一IOMMU服务、GPU归属与PM生命周期、protected Host集成、GPUVM待同步列表、模拟验收探针及报告。平台保护按用户确认作为已有能力假设；当前简表仍保留9项已实现和5项未实现/部分实现，GPUVM强化尚待后续开发。

## 验证范围

`check-dma-guard.sh`、`check-secure-iommu.sh`、`check-opencca-host-mmio.sh`、`check-opencca-timers.sh`、`check-opencca-vmid.sh`及`check-rmm-xshm-events.sh`均退出0。旧xshm入口首次因漏链接`opencca_gpu.c`失败；补齐当前真实依赖后复验通过，不改运行代码。上游补丁清单与固定runtime校验通过，runtime恢复文件数0。原始检查输出位于忽略目录`build/git-publication-20261020/`。

候选源码和结构化证据经语法、生成文件及凭据检查；不提交原始运行日志、镜像、缓存或设备凭据。U-Boot已应用补丁保留在补丁清单，不另行提交其上游工作树。

本次发布不替换runtime-manifest或原冻结镜像，不把当前源码等同于旧发布二进制。最新既有720p为1159，原冻结1171/1170继续保留；本次未改运行代码，无新增性能测量，不宣称新增硬件回归PASS。当前硬件、已知失败及验证范围见[当前基线](CURRENT_BASELINE.md)。
