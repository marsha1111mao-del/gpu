# 场景二实现状态

## 已实现（必须保留）

当前按硬件行为模拟与总体设计一致验收。假设目标平台已保护RMM/可信Proxy的页表与控制内存、IOMMU关键配置及工作态任务MMIO，并阻止未授权CPU/DMA访问；这些能力不列为本工程待开发项。Host保留板级供电、时钟和合法OPP管理权；RMM负责资源归属与授权，不引入EL2接管普通VM页表。

| 条目 | 当前实现 |
| --- | --- |
| Client Realm / RMM 通信 | RMM校验端点与授权范围，建立共享队列、BO池与可信IRQ通知；Client通过对象句柄和计划引用提交。 |
| 可信 Proxy / Panthor | 按session校验资源与对象引用，创建GPUVM，复用执行计划，通过原生调度与真实fence确认完成。 |
| GPU 内置 MMU / GPUVM | 真实GPU页表将GPU VA映射到授权HPA；GPU数据路径不依赖外置SMMU S2。 |
| Host 标准 IOMMU 映射准入 | 普通页/SG映射与回滚接入RMM检查，拒绝映射GPU/Realm受保护物理页。 |
| managed-IOMMU 寄存器访问时钟 | 绑定期间持有IOMMU时钟/PM引用，失败时回滚，解绑/parking后释放。 |
| Guest RSI managed-IOMMU 路径 | Guest经RSI执行domain创建、映射、查询、撤销和设备绑定；授权与供电检查先于硬件访问。 |
| PM owner 生命周期 | GPU owner绑定pmthor session；退出前协调撤销、可信复位和backing回收，保持引用与释放顺序。 |
| 统一安全 IOMMU 服务 | Host RMI、Guest RSI共用owner/generation/物理页互斥检查；RMM持有真实表/root，管理parking、撤销/IOTLB及设备授权/供电生命周期；当前范围验收完成。 |
| Host 与其他 IOMMU 设备 | 标准及managed直接驱动入口统一转RMM，控制真实表/root/parking/IOTLB与时钟生命周期；托管设备范围验收完成。 |

详细实现与验证依据见[当前基线](CURRENT_BASELINE.md)及[平台假设](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)。本页与Notion仅维护当前9项已实现、5项未实现/部分实现；历史证据在原报告保留。

## 未实现 / 部分实现（必须保留）

| 条目 | 剩余工作与范围 |
| --- | --- |
| GPUVM 安全强化 | 真实GPUVM及基本对象检查已实现；跨Client授权、Group/GPUVM绑定和撤销后页复用的软件约束仍缺完整专项覆盖。 |
| GPU MMIO 独占与受限 PM | 单Proxy归属、claim/reset、合法OPP、撤销与回收及空闲电源循环已实现并验证；镜像身份认证和活跃任务异常恢复扩展尚未完成。硬件封堵归为平台假设。 |
| 保护模型仿真验收 | 选定模拟主流程已通过；更完整的模型覆盖属于可选扩展，不要求在当前板卡重现平台硬件保护能力。 |
| 跨 Client 攻击与长期稳定性 | 双Client功能/API/计算检查已通过；恶意任务、共享状态竞态和长期压力的完整专项尚未完成，作为扩展验证跟踪。 |
| 最终发布与冻结基线替换 | 当前开发组合已完成选定模拟验收，尚未完成新发布包、manifest/组件版本整理及冻结基线替换；按已确认模拟范围执行发布检查。 |

平台已有能力不重复列为实现缺口，扩展验证不阻塞当前模拟范围验收。本次纯文档整理，未改运行代码，无新增性能测量。
