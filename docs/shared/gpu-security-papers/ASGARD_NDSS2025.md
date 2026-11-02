# ASGARD：安全加速器直通、模型执行计划与中断语义边界

研读日期：2026-10-27。依据 18 页原文、作者 artifact 说明及固定提交的定向静态核验。实际设备是 Rockchip NPU；本文将其作为与 CCA/GPU 项目高度相关的加速器保护研究，不误称为 GPU 或已实现的 CCA 系统。

## 1. 书目信息与证据

| 项目 | 内容 |
| --- | --- |
| 正式标题 | ASGARD: Protecting On-Device Deep Neural Networks with Virtualization-Based Trusted Execution Environments |
| 作者 | Myungsuk Moon、Minhee Kim、Joonkyo Jung、Dokyung Song |
| 发表 | NDSS 2025，DOI 10.14722/ndss.2025.240449 |
| 原文 | [NDSS PDF](https://www.ndss-symposium.org/wp-content/uploads/2025-449-paper.pdf) |
| PDF SHA256 | `2a2bc8533b16ac26d58313727e5dbfc0cad3e2948ddb2893a924aa002f7fcadc` |
| 作者 artifact | [yonsei-sslab/asgard](https://github.com/yonsei-sslab/asgard) |
| 固定提交 | `66287497808231a0ff9e00e6952bf5143455a1df` |
| 阅读范围 | 正文 §§I–VIII；重点 §IV、§V、§VI 与 §VII；相关工作用于比较，不逐一核验全部引用 |

原文中的主张、artifact 的复现说明和本报告的独立推断分别列出。本轮没有构建或运行作者原型。

## 2. 背景：保护完整模型，同时兼容厂商软件

模型只在磁盘上加密不能防止被攻陷的移动 OS 在推理时读取明文。早期方案将模型全部放入 TrustZone，往往只能使用 CPU；分层卸载与混淆允许使用普通世界加速器，却引入频繁的世界切换、混淆和反混淆，且保护范围依赖具体划分。

ASGARD 选择另一条路线：在受保护 VM 内运行可兼容已有二进制的软件栈，把完整加速器直通给该 VM，用小型 EL2 可信监控器保护设备访问。它所回答的是“旧 Arm 平台怎样支持兼容的安全模型执行”，不是“如何验证任意恶意 GPU kernel 的程序行为”。

三项主要技术相互配合：安全直通保证模型执行不越出可信域；TCB 裁剪降低完整 VM 软件栈的信任成本；DNN 执行图重排减少保护域退出。只引用其中的 IOMMU 或 near-zero overhead 都会遗漏其设计条件。

## 3. 威胁模型和信任基础

攻击者可控制 REE 应用、Host OS 和 EL1 REEvisor，操纵资源管理、设备分配请求及中断交付，并通过其他设备尝试 DMA。可信部分包括 EL2 TEEvisor、Secure World、可信启动及 enclave 内核/驱动/runtime/模型服务。

前置条件包括：所有可 DMA 外设都经过受控 IOMMU；真实敏感寄存器与 reset 接口的地址从可信启动信息建立；reset 能将目标设备恢复到约定良性状态。攻击者不能物理篡改总线、设备或 IOMMU，不考虑侧信道、物理模型提取等攻击。

这与 CCA 不同：Secure World 仍在 ASGARD 的信任基础中。论文讨论未来把机制移入 RMM，但不能将其原型记为 CCA Realm 隔离、也不能由论文的未来讨论推导任意 CCA 平台都具备完整内存加密。

## 4. 架构与端到端流程

平台先验证内核/设备树并建立 TEEvisor 对敏感资源的所有权，再启动模型方签名的 VM enclave。平台向 enclave 提供证明和 sealing 所需秘密；模型方经认证通道下发模型，后续可从不可信存储解封。以上是论文的完整操作设计，不能仅由本轮查看的部分代码认定全部已核验。

enclave 申请设备后，由可信层建立其 MMIO 和 DMA 访问。REE 用户提交推理输入，VM 内完整可信软件执行并返回结果。模型服务不返回 confidence score，以减少额外模型信息暴露；这不是对任意黑盒模型提取的全面证明。

核心执行结构为：

```text
REE：资源管理 / crosvm / 调度与中断转发
                   ↓ 受检查请求
EL2 TEEvisor：CPU S2 / 实际 IOMMU / 设备归属 / reset
                   ↓ 受保护 I/O 路径
VM enclave：模型服务 + Linux + 厂商 NPU 软件栈 ↔ NPU
```

## 5. 三项不变量及其落实

| 不变量 | 机制 | 保证边界 |
| --- | --- | --- |
| INV1：敏感接口完整仲裁 | 可信启动定位；CPU Stage-2 保护 IOMMU MMIO、页表及关键配置 | 不能保留绕过可信层的配置写口 |
| INV2：最多一个 enclave 拥有设备 | acquire/release 核验设备许可和当前 owner；切换映射并失效 TLB/IOTLB | 整设备时间独占，不是多个不可信 GPUVM 并发 |
| INV3：切换无残留 | 可信 reset，清除寄存器/设备状态并处理片上存储 | 有效性依赖目标 reset 语义与实际状态覆盖 |

TEEvisor 拥有的页不能像 enclave 页一样被 REE 随意回收。对 reset 接口，设计允许受约束借用，但其可信所有权和访问能力不能丢失。说明“实际页归属”和“管理请求权限”是不同概念。

## 6. DMA 与资源回收的粒度

guest 内的小型 IOMMU 驱动提供 IOVA→GPA 恒等映射；真正由 EL2 控制的 IOMMU 完成 GPA→HPA。ASGARD 不向 enclave 暴露细粒度 map/unmap 接口，而把 enclave 拥有的全部内存授权给其设备。原型在启动时 pin guest 内存，准备映射，仅在获得设备后激活。

这样减少可信接口和管理复杂度，但保护粒度比本项目更粗。设备可访问 enclave 内全部内存的前提是该 enclave 软件整体可信，不能转化为恶意 Client 作业只可访问自己对象的证明。

REE 可强制回收资源，可信层负责清除页面、移除 CPU/IOMMU 映射；回收 MMIO 时强制把设备切回 REE。guest 驱动依靠 watchdog 等机制检测设备丢失并终止推理。这是保密性与可用性分离的设计。

**独立判断：** 文本列出的回收动作还不足以单独证明任意并发 DMA 下的安全复用时刻。迁移到本项目时，应明确禁止新启动、确认旧访问停止、撤销/失效、清零、重新分配的偏序，不能只把 API 返回或 watchdog 超时作为 quiescence 证据。本轮没有证明 ASGARD 存在该方向可利用漏洞。

## 7. TCB 裁剪：兼容性换来的信任成本仍存在

作者把 IOMMU power/clock 管理留在 REE，理由是所测 SoC 的 IOMMU 和对应设备共享电源/时钟域：关掉 IOMMU 时设备也停止，不能绕过映射保护。这是具体集成条件，不是所有平台都可安全采用的通则。

guest 只运行一个可信模型应用，因此去掉对该模型保护没有额外价值的内部用户/内核隔离功能及无用组件，保留必要完整性与硬化功能。不能将其禁用 Seccomp/SELinux 的裁剪选择用于承载多个互不信任应用的 Proxy。

原始 TEEvisor 约 12k LoC，新增 IOMMU 约 2k、分配回收约 200 行。guest kernel 从 17.533MB 到 7.936MB，用户空间从 10.479MB 到 9.503MB，总计 17.439MB。二进制大小、增加的代码量和总安全 TCB 是三种不同度量；完整厂商运行时和 guest 内核仍受信任。

## 8. 性能优化：重排依赖图，减少退出

NPU 不支持的算子需要 CPU fallback，设备中断交付与 EOI 会产生保护域退出。ASGARD 的算法在不违反 DAG 依赖的前提下，交替构造可由 NPU 执行和需 CPU fallback 的子图，使独立 fallback 算子集中处理。子图内部仍可结合其他内存/调度优化。

它减少的是应用计划中本来需要发生的切换，不是丢弃真实中断，也不是把未完成作业提前标记完成。对于无可利用并行分支的模型收益有限。

| 模型 | 默认退出数 | 优化后 | 相对 REE 的推理延迟变化（Figure 8b） |
| --- | --- | --- | --- |
| MobileNetV1 | 1 | 1 | 该图报告默认保护开销 1.39%；不要与另一端到端实验混用 |
| InceptionV3 | 10 | 10 | 默认保护开销 2.62% |
| SSD-MobileNetV1 | 13 | 2 | 默认 +3.47%，优化 −1.36% |
| SSD-InceptionV2 | 18 | 10 | 默认 +2.11%，优化 +0.85% |
| Lite Transformer Encoder | 26 | 16 | 默认 +15.16%，优化 +6.07% |
| Lite Transformer Decoder | 38 | 20 | 默认 +33.88%，优化 +3.26% |

四个受益模型的峰值中间内存未增加；作者依据各算子的权重和 tensor 大小计算内存曲线，不等于对任意模型证明峰值不变。

## 9. 中断安全：作者明确留下的风险

§VI-A 的 rogue NPU interrupt 分析指出，REE 可伪造非预期中断，诱导下一算子过早使用不完整结果；抑制中断则损害可用性。作者讨论特殊中间值可能影响权重保密性，认为完整模型提取仍困难，并提出用 Devlore 类真实性检查降低风险。

这不是本轮复现的攻击，也不是原型已实现的修复。论文其他地方的“安全地扩展 TEE”需要与此限定一起理解。

对项目而言，可信 IRQ 只证明事件来源，仍要将其关联到正确 job、错误状态、GPUVM 与执行代际。设备可以合并 IRQ，一个 IRQ 不必对应一个完成；工作负载可写的计数更不能因其被 CPU 读到而成为可信成功依据。

## 10. 评估配置和可比边界

原型为 RK3588S、Android 13、Linux 5.10、crosvm/pKVM。四个 A76 固定 2.208GHz，禁用 A55，内存控制器 1.560GHz、NPU 1GHz；每 enclave 1vCPU/512MB，绑核，硬件计时器测量。

MobileNet 端到端实验平均 1000 次：ASGARD 相对 REE +2.01%，比模拟 ShadowNet 快 4.333 倍，比不混淆的 ShadowNet 快 1.430 倍。**VSOCK 开销被排除**，不能称完整外部服务调用的总成本。

Host EL1 handler 到 NPU driver 的 IRQ 交付相对 REE 为 3.684 倍，Figure 7 给出 1000 次平均及 95% CI。应用小开销与单路径较高开销并不矛盾，因为调用频率不同。没有原始运行数据或本轮复现，就不把图中测量扩展为长期最坏延迟保证。

## 11. 原型与一般设计的差异

一般方案讨论通过可信 firmware wipe/reload 清除设备状态；Rockchip 原型实际只使用寄存器 reset，并禁用可选 SRAM，明确没有动态固件重载接口。不能记作已验证了 MOLE 所关注的固件加载链。

论文提出未来 CCA 和设备证明路径，不能记作当前原型已经实现；功耗域相同也只是所测平台的安全条件。上述差异不否定机制思想，却决定了可以引用什么实验和安全结论。

## 12. Artifact 核验范围

固定主仓库的完整 Git tree 为 349 个普通文件，另有子模块。README 提供 E1–E6，分别验证厂商二进制/驱动、TEEvisor LoC、VM image 以及模型性能；同时说明厂商驱动附有性能测量修改，不能将“功能不改”解释为所有字节未变。

尤其需要注意：**主仓库 `src/hyp` 是对照用的原始 pKVM，不是修改后的 ASGARD TEEvisor。** 本轮已读取其中 IOMMU、内存保护与 hypercall 文件用于确定这个边界，未将它们的上游逻辑误报为作者新增防护。

实际 Host manifest 子模块固定为 `b11411866c09f636da40a88868491b7efceaa74a`，指向 `yonsei-sslab/asgard-manifest` 的 host-android 分支；其中 kernel 项目 `asgard-linux` 的 revision 却写为可变分支 `host`。因此固定主仓库不等于固定了全部构建输入。本轮把当前解析得到的 Host kernel 固定为 `436d1a7690f3691b9b76414479f7285fb30126ed`，尚未证明它与发表时实验构建完全相同。

定向读取该 kernel 的 `arch/arm64/kvm/hyp/nvhe/iommu.c` 与 `iommu/rockchip-iommu.c`：可见可信 Rockchip IOMMU 注册、撤去 Host 对真实 IOMMU MMIO 的 Stage-2 映射、私有 EL2 映射、受锁保护的页表操作及 unmap 后的 IOTLB shootdown。`rk_iommu_init()` 先复制 Host 可变输入，注释明确说明避免 TOCTOU。这些可以作为真实代码事实；不等于完整 acquire/release/reset 协议已经证明。

还观察到一个与共享验证直接相关的限制：`rk_iommu_enable_hyp()`、`rk_iommu_disable_hyp()` 的 TODO 明确写 **VM #1 → VM #2 → VM #1 推理会失败，链表可能无限遍历**。本轮未执行或定位该问题的可达条件，因此将其记为作者代码中的已标注限制，不把注释当作本轮复现的漏洞。它提示多轮往返、重复分配回收应独立测，单次 A→B 成功不足以证明稳定共享。

此外，IOMMU `FORCE_RESET` 与 NPU/固件完整清理是不同操作，不能因前者存在而宣布后者已审计。完整 Android 构建、约 TB 级复现依赖和未读取的设备分配路径均保留待核验。因此本篇证据等级为：原文和评估已研读；固定 artifact 与少量真实安全路径已静态核对；没有完整代码审计，也没有执行作者代码。

## 13. 与项目和其他论文的关系

相对 StrongBox/CAGE，ASGARD 更看重完整厂商软件兼容；相对 ACAI/PORTAL，设备保护所在层和安全世界信任基础不同；与 Devlore 互补的中断缺口由作者直接指出。与 TZ-LLM 的核心区别是整设备直通到完整 VM，后者选择可信小数据面与不可信调度器协作。

项目已选完整驱动可信 ProxyRealm，可继承其兼容路线和真实 IOMMU 控制思想，但必须保持原始 Client 授权主体。Proxy 可访问 A/B 内存，不代表 A 可以要求映射 B。用户设定的软件 IPA→HPA 授权合成 Stage-1 可以承载这一策略，重点是最终 PTE 的实际页、权限和生命周期。

## 14. 可执行的后续研究

建议写清四条安全性质：启动只能使用已固定的授权快照；IRQ 只触发核验而不能生成成功；reset/cancel 后旧 job 代际不能匹配新对象；只有停止访问并完成映射失效和清理才能复用 HPA。

负例应覆盖 acquire/release 竞争、伪 IRQ、DMA 在途强制回收、reset 后旧 completion、句柄复用以及受害 Client 恢复。性能应分别测直通、共享、完成确认和撤销，不以 NPU 论文结果替代本项目 GPU glmark。

本篇未改运行代码，无新增性能测量；无硬件 run-id、无新增硬件 PASS。来源、代码哈希和发布回读状态由同目录研究进度文件记录。
