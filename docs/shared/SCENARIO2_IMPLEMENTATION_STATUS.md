# 场景二实现状态

## 已实现（必须保留）

当前按硬件行为模拟与总体设计一致验收。假设目标平台已保护RMM/可信Proxy的页表与控制内存、IOMMU关键配置及工作态任务MMIO，并阻止未授权CPU/DMA访问；这些能力不列为本工程待开发项。Host保留板级供电、时钟和合法OPP管理权；RMM负责资源归属与授权，不引入EL2接管普通VM页表。

| 条目 | 当前实现 |
| --- | --- |
| Client Realm / RMM 通信 | RMM校验端点与授权范围，建立共享队列、BO池与可信IRQ通知；Client通过对象句柄和计划引用提交。 |
| 可信 Proxy / Panthor | 按session校验资源与对象引用，创建GPUVM，复用执行计划，通过原生调度与真实fence确认完成。 |
| GPU 内置 MMU / GPUVM | 真实GPU页表将GPU VA映射到授权HPA；GPU数据路径不依赖外置SMMU S2。 |
| GPUVM 安全强化 | 独立GPUVM构成信任域；隔离标志强制一个生命周期只允许一个Group。BO绑定真实根，检查owner/generation、类型/权限和用户VA，延迟清零复用；双Client、真实GPU同VA读写及越域VA故障/受害Group恢复专项通过。普通Mesa同GPUVM内Group仍共享地址空间。 |
| Host 标准 IOMMU 映射准入 | 普通页/SG映射与回滚接入RMM检查，拒绝映射GPU/Realm受保护物理页。 |
| managed-IOMMU 寄存器访问时钟 | 绑定期间持有IOMMU时钟/PM引用，失败时回滚，解绑/parking后释放。 |
| Guest RSI managed-IOMMU 路径 | Guest经RSI执行domain创建、映射、查询、撤销和设备绑定；授权与供电检查先于硬件访问。 |
| PM owner 生命周期 | GPU owner绑定pmthor session；退出前协调撤销、可信复位和backing回收，保持引用与释放顺序。 |
| 统一安全 IOMMU 服务 | Host RMI、Guest RSI共用owner/generation/物理页互斥检查；RMM持有真实表/root，管理parking、撤销/IOTLB及设备授权/供电生命周期；当前范围验收完成。 |
| Host 与其他 IOMMU 设备 | 标准及managed直接驱动入口统一转RMM，控制真实表/root/parking/IOTLB与时钟生命周期；托管设备范围验收完成。 |

详细依据见[当前基线](CURRENT_BASELINE.md)、[GPUVM验收](GPUVM_ISOLATION_VALIDATION_20261020.md)及[平台假设](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)。本页保留10项已实现、4项未实现/部分实现，原14个条目均保留；历史证据在原报告。Notion最新状态迁移因连接需重新认证而待同步，远端已精简两区仍保留9/5项。

## 未实现 / 部分实现（必须保留）

| 条目 | 剩余工作与范围 |
| --- | --- |
| GPU MMIO 独占与受限 PM | 单Proxy归属、claim/reset、合法OPP、撤销与回收及空闲电源循环已实现并验证；镜像身份认证和活跃任务异常恢复扩展尚未完成。硬件封堵归为平台假设。 |
| 保护模型仿真验收 | 选定模拟主流程已通过；更完整的模型覆盖属于可选扩展，不要求在当前板卡重现平台硬件保护能力。 |
| 跨 Client 攻击与长期稳定性 | 双Client各18项API、实际计算、会话句柄/owner检查及独立GPUVM故障专项已通过；跨Client原始恶意RPC全矩阵、共享状态竞态和长期压力仍作为扩展验证跟踪。 |
| 最终发布与冻结基线替换 | GPUVM开发源码已发布，开发冻结包已通过选定验收；正式新二进制发布包、runtime-manifest更新及原冻结基线替换仍待完成。 |

平台已有能力不重复列为实现缺口，扩展验证不阻塞当前模拟范围验收。本次GPUVM开发含运行代码变更；最终完整720p1159，对同Host/RMM既有1159为0分/0%，命令、退出码、run-id与日志见GPUVM验收报告。
