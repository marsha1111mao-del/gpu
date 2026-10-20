# GPUVM 隔离强化 v1

目标：恶意Client的GPU任务不能经映射、Group绑定或物理页复用进入另一个隔离域。RMM、可信Proxy/Panthor和GPU固件仍在TCB内；页表、控制内存、关键配置及任务MMIO的物理保护沿用[平台能力假设](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)，不引入GPU外置SMMU S2或EL2接管普通VM页表。

## 依据与取舍

| 论文 | 采用的机制 | 本工程的实现位置 |
| --- | --- | --- |
| [StrongBox，CCS 2022](https://compass.sustech.edu.cn/strongbox/) | 检查实际映射并保护页表/控制面，不能只检查API句柄 | 可信Panthor生成真实GPU页表，Client无PTE/root替换接口 |
| [CAGE，NDSS 2024](https://www.ndss-symposium.org/wp-content/uploads/2024-763-paper.pdf)，§IV-B | 重建映射时检查非法/重复映射，避免逐条GPU访存陷入monitor | 直接约束Proxy已有真实GPUVM；无须额外制造Client影子PTE |
| [ACAI，Security 2024](https://www.usenix.org/system/files/usenixsecurity24-sridhara.pdf)，§5 | 唯一归属、一致映射与安全交接 | session归属、不可变GPUVM根引用、撤销后延迟复用 |
| [PhantomMap，NDSS 2026](https://www.ndss-symposium.org/ndss-paper/phantommap-gpu-assisted-kernel-exploitation/) | 分配、别名与最终映射检查必须一致 | 检查payload类型/权限/存续状态，并在Panthor映射处约束根身份 |
| [Honeycomb，OSDI 2023](https://www.usenix.org/conference/osdi23/presentation/mai) / [Guardian，Middleware 2024](https://arxiv.org/abs/2401.09290) | 同地址空间隔离需要完整指令验证或插桩 | v1选独立GPUVM，不移植AMD/PTX验证器，不把句柄检查称为Mali指令验证 |

原文和固定提交的代码已在`build/gpu-isolation-research-20261018/`核对；完整代码图见[调研](GPU_ISOLATION_RESEARCH_AND_CODE_MAP_20261018.md)。CAGE的独占模型不作为并发隔离证明，PhantomMap的kbase漏洞不直接套用到Panthor。

## 隔离单位和ABI约束

一个GPUVM构成一个GPU任务信任域。一个Group可以有多个队列/提交，域内任务可共享数据；需要相互隔离的任务必须创建不同GPUVM和Group，并在Realm Client的VM_CREATE中设置`DRM_PANTHOR_VM_CREATE_ISOLATED`。可信Proxy将这个不可变策略保存在私有VM记录中，拒绝该GPUVM生命周期中的第二个Group，包括销毁旧Group后重建。这样旧异步任务不会与新Group共享根；重建隔离Group须同时新建GPUVM。

未设置此标志时保留原生Mesa语义：一个GPUVM内可以有多个相互信任的Group，它们共享地址空间，不能宣称相互隔离。Mesa当前按device共享VM并反复创建EGL Context/Group；将一Group限制无条件施加到旧ABI会破坏glmark。显式隔离标志由Client转发并由可信Proxy强制执行，调用方不能通过修改已注册的共享请求切换策略；普通原生Panthor不支持该扩展时返回错误。跨GPUVM的BO根绑定检查对两种模式都生效。该版本不自动改写Mesa的地址空间管理。

每个vmshm BO在首次MAP准备时绑定真实GPUVM根，持有该根GEM引用直至BO最终释放。普通/只读/NOEXEC别名均不能跨根；同根内合法别名仍允许。首次MAP后续失败也不清除归属，调用方可销毁BO重试；不在失败路径尝试重新授权。既有exclusive VM限制继续生效。此限制有意缩减共享ABI，当前不提供跨域共享BO，不能用“只读”绕过；应用需要共享时须另行设计显式授权接口。

Proxy在session锁内拒绝仍有Group/heap的VM销毁，避免公开VM编号复用替换活动配置。原生Group仍持有实际VM引用；Group销毁使已有计划失效。根的引用身份独立于可回收的整数句柄，因此旧BO不能借VM编号复用映射进新根。

## 映射和回收

1. 请求身份来自可信RMM通道，VM/BO/Group从当前session私有表解析。BO所属Client与payload句柄必须一致。
2. 在Panthor MAP准备处检查payload仍有效、是GPU数据/命令对象，GPU权限覆盖实际PTE请求；控制环、完成页等类型不能作为工作负载BO安装。
3. BO→根绑定在`gpuva_list_lock`内完成。真正PTE仍由原生Panthor生成；VA、长度、offset、READONLY/NOEXEC和回滚沿用原生检查。Client不能提交HPA、页表页或TTBR。
4. BO关闭先撤销公开lookup；已接受任务、VMA及GEM pin保留原backing。直到原生fence/调度与unmap/TLB完成路径释放最后引用后，allocator才清零并复用。撤销不等于立即杀死已接受任务；不得跳过排空直接重用物理页。

Client的MAP和UNMAP都限制在该VM公开的user VA范围，使用减法检查避免端点溢出；可信驱动内部使用的kernel VA不开放给Client重配置。sync-file worker通过内部`PANTHOR_VMSHM_SYNCOBJ_WAIT_FENCE_STATUS`标志读取不可变私有snapshot的真实fence状态，将GPU错误传到导出的sync-file；普通DRM SYNCOBJ_WAIT维持原生“等待完成”的语义。成功cookie只用于原生完整fence成功的情况，故障不会发布成功凭据。

普通双Client功能入口未启用融合snapshot，使用CREATE+TRANSFER；性能入口启用融合snapshot。两条路径都有实际调用者，均保留并读取同一原生fence状态。非融合snapshot由Client私有持有，但不具有Proxy的`private_snapshot`标记；状态读取只要求当前会话中的单个有效对象，不以该标记拒绝兼容路径。

应保持：`MappedPages(domain) ⊆ AuthorizedPages(owner, object)`；`PTE权限 ⊆ 对象GPU权限`；`ControlPages ∩ WorkloadPages = ∅`；`Reuse(page) ⇒ 旧GPU引用归零且翻译失效`。平台保护不代替这些软件检查。

## 性能与验收计划

新增检查限于Group创建、BO/MAP准备和资源销毁；正常计划执行不遍历页表、不增加RMM调用或每条指令检查，不串行化不同GPUVM的GPU执行。

先构建并运行完整720p33场景，对照当前Host #31/RMM timer v6的既有1159；相同默认256MiB、GPU请求600/实际594MHz、null-noop/finish，记录正确性、Host/Guest健康及资源恢复。达到1000门槛后，执行双Client API/计算和新增映射/Group/根复用负例；实际GPU恶意访存与恢复须独立记录，不能用拒绝ioctl代替GPU访存证据。

本设计已实现并完成选定硬件验收：最终完整720p1159，对同Host/RMM的1159为0分/0%；双Client API、计算、GPUVM负例、实际GPU越域VA故障与受害Group恢复通过，见[验收报告](GPUVM_ISOLATION_VALIDATION_20261020.md)。原冻结1171/1170和历史失败保留；不向Notion追加历史流水。侧信道、GPU片上残留、TCB漏洞与长期可用性不属于本版地址空间隔离证明。
