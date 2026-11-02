# Devlore：CCA 设备中断保护精读与共享 GPU 启示

日期：2026-10-27。阅读对象是当前扩展原文，不是仅依据早期摘要。

## 1. 文献信息与版本

**Devlore: Device Interrupt Protection for Confidential VMs**，Andrin Bertschi、Supraja Sridhara、Mark Kuhne、Benedict Schlüter、Friederike Groschupp、Clément Thorens、Nicolas Dutly、Srdjan Capkun、Shweta Shinde。作者页面及原文标注 RAID 2026；本次使用扩展版 [arXiv:2408.05835v3](https://arxiv.org/abs/2408.05835v3)，2026-08-11。

来源：[完整 HTML](https://arxiv.org/html/2408.05835v3)、[作者项目](https://sectrs-devlore.github.io/)。2024 年首版标题 “Devlore: Extending Arm CCA to Integrated Devices — A Journey Beyond Memory to Interrupt Isolation” 与此为同一工作，不应按标题变化重复列为两篇独立方案。

本地完整 `devlore.pdf` SHA256 为 `4fd64876e9f0c197158c085fd3bbee49ee7517331068a27fd61dae0d1b6a88e0`。目录中的 `devlore-v3.pdf` 是失败的部分下载，不能用作阅读或引用副本；完整 PDF 和官方 v3 HTML 已另行取得。

## 2. 为什么内存隔离之后仍要保护中断

中断会推动可信驱动状态机。攻击者即使不能写设备寄存器或受保护内存，也可能通过伪造中断让驱动错误地认定初始化、收包或设备操作已经完成。原文使用简单 `interrupt_cnt` 驱动说明：若每次 IRQ 都直接增加可信计数，伪造中断本身就能改变结果。

原文还讨论 Qualcomm WCNSS 的 ready IRQ 调用 `complete(start_done)`；错误的 ready 时机会改变后续初始化流程。因此中断不仅是性能提示，也可能成为可信状态转移的输入。对于 GPU，风险问题是“错误事件是否能推动完成、取消、回收”，而不是笼统说“中断越多越不安全”。

## 3. 威胁模型与前置条件

可信部分为 CCA 硬件、GIC、平台集成、Monitor 和 RMM；Normal 与 Secure world 都可恶意，不同 CVM 相互不信任。每个受害 CVM 信任自己的 OS、驱动与应用，这和本项目“可信 Proxy 内完整驱动”的选择相近。

设备有可信的 MMIO 与中断线关联，不能自行伪装成其他设备的物理中断源。设计建立在设备身份、干净初始化/证明、受保护内存以及安全分离/清理等先验保证上；Devlore 并不是让任意恶意设备或任意固件变得可信。

保护重点为设备中断。CPU 异常、timer/IPI 单步攻击、完整时间隐藏以及调度拒绝服务不自动包含在其保证中。攻击者仍可拖延 CVM 调度；论文要求受保护的中断行为等价于某种良性调度，不承诺有限等待时间或公平性。

## 4. 机制：从真实到达到受检虚拟注入

### 4.1 保护整个 GIC 访问面

将 GIC MMIO 置于 Root 保护下，Host 访问陷入 Monitor，再由检查接口决定允许操作哪些 INTID 的哪些字段。不能只保护路由寄存器而让攻击者写 set-pending，也不能提供任意 Root MMIO 读写 SMC 作为绕过口。

### 4.2 建立设备、物理 IRQ、Guest IRQ 的可信绑定

受信流程根据设备标识与功能确定物理 INTID，RMM 验证该 CVM 的设备归属；记录其 guest virtual INTID 与优先级等信息，并将绑定纳入证明。由 Host 随意提交一个 INTID 并不构成设备来源认证。

### 4.3 Monitor 记录真实事件，Host 保留调度权

受保护物理 IRQ 路由为 Group 0，由 EL3 Monitor 首先接收并记录顺序；RMM 可见受保护记录。Host 可见的镜像只用于提示和调度，不是权威记录。Monitor 通过 IPI 通知 Host；Host 仍负责运行 CVM 并提出 vGIC LR 注入。

因此它不是把整个 VMM 搬入 TCB。设计把“调度/建议注入”留给不可信 Host，把“该建议是否与真实设备事件一致”交给可信层。

### 4.4 不止计数，还检查顺序窗口和优先级

只限制中断总数仍允许交换事件；只检查 INTID 是否在真实记录里也允许错误顺序。RMM 检查注入集合、有限 LR 槽窗口中的顺序及最高优先级 pending 事件。窗口与可用的不同 vGIC 槽数有关，不能概括为所有设备中断的全局严格 FIFO。

这也提示本项目：应证明驱动可见序列满足其语义，不能为了方便把设备允许的合并和并发错误禁止。

### 4.5 ACK/EOI 是安全协议的一部分

物理 IRQ 不能一律在到达后立即 ACK。某些电平触发设备若事件仍未清除，提前 ACK 会重触发甚至形成风暴。Devlore 区分可提前确认的 IRQ 和需等 guest EOI 再经 RMM→Monitor 确认的 IRQ。GIC 的 pending/active、设备状态清除和 guest 完成处理必须相容。

## 5. 创新边界

相对仅保护 DMA 与 MMIO 的 CCA 设备工作，核心增量是把物理设备来源、GIC 访问、虚拟注入顺序/优先级和 ACK 连接为受检协议。相对完全可信 hypervisor，Host 仍可负责调度与建议注入。

对共享 GPU 来说，该机制证明的是“真实设备事件确实发生、注入序列符合规则”。它不独立证明“Client A 的 job J 成功”“job 输出内容正确”“GPU 已停止访问所有关联页面”。这些语义依赖可信驱动、设备/固件状态及作业对象。

## 6. 实现、实验和数值的正确读法

| 项目 | 原文结果 | 解释限制 |
| --- | --- | --- |
| FVP 功能原型 | TF-A 2.8 增 3054 LoC、RMM 0.2 增 1188、Linux 6.2 增 2706（guest 60 / host 2646）、VMM 590 | 总改动约 7538 行；Host/VMM 改动不等于可信 TCB 增量 |
| 功能设备 | NoMali GPU、UART、PS/2 鼠标/键盘、LED/按键等 | NoMali 模拟 MMIO/IRQ，不能运行真实 GPU 计算；LED/按键例子不都涉及中断 |
| 伪造测试 | 1 万次虚拟 IRQ、1 万次 GIC set-pending 物理写被拒绝；另有 MMIO/DMA 拒绝测试 | 是原文特定攻击覆盖，不证明全部 GPU 协议正确 |
| 性能平台 | OpenCCA，Rock 5B / RK3588、16 GB、Mali-G610；4 个 A55 1.8 GHz；TF-A 2.11、RMM 0.5、Linux 6.12 | 性能路径与早期 FVP 版本不同；不等于真实 CCA 硅片完整证明 |
| 1000 个 GPU IRQ | 669 ticks / 27.9 µs → 703 ticks / 29.3 µs，约 5% | 单路径中断开销，不是应用统一慢 5% |
| 持续 IRQ 压力 | GPU/UART 实验开销至多约 1%，标准差小于均值 1.2% | 实验负载与配置限定 |
| glmark2 | 17 项 workload，几何平均 slowdown 0.06%，约 2500–32000 次 IRQ | 不等于本项目完整 33 场景 glmark 分数的可比差异 |
| 启动 | 8.9 → 9.1 秒，增加 221 ms / 2.4%；其中 SMMU 177.7 ms | 不应把所有启动差异都归因 IRQ 检查 |

单路径测量的 ±0.2 µs 量级统计与应用结果均来自原文，本次未复现；不同基线、频率、核类型和 workload 的论文数值不用于横向排名。

## 7. 代码可获得性与核验程度

作者项目页面可找到论文、演示和报告资料。本次检查作者 GitHub 组织入口只确认网站及 `.github` 等公开仓库，没有定位完整实现 artifact，故不声称完成源码审计，也不推断作者从未公开过代码。原文设计可借鉴，但落到本项目仍需独立实现与验证。

## 8. 结合当前项目的具体建议

把物理 IRQ 与跨 Realm 通知分开建模。GPU 的 JOB/MMU/GPU 等物理事件进入可信 Proxy，由其读取可信状态并识别一个或多个 job 的状态变化，再通过 RMM 端点通知各自 Client。合并中断或一 IRQ 多 job 是正常情形，不需要建立机械的一一对应。

Client 收到中断后应读取受保护的完成队列或权威状态。中断是“有状态需要处理”的通知，不应单凭 IRQ 次数生成成功、释放对象或改变授权。重复中断可幂等处理；旧 session 或旧 device epoch 的通知不能影响新对象。

当前 `xshm_irq.c` 已有保留 LR 与拒绝 Host 重复注入的基础，`xshm_endpoint.c` 有 pending/armed/ACK_ARM。它们主要面向 Proxy→Client 的受保护通知，不能自动证明 GPU→Proxy 的物理 IRQ 已有完整 Devlore 保证；也不能反向写成项目完全没有通知保护。

值得推进的增量是：物理事件与具体 job/fence 的可信绑定；恶意 workload 不能通过可写计数伪造完成；cancel/reset 下旧事件被 epoch 隔离；终态、DMA quiescence 和页面回收屏障分离。上述内容需要结合设备语义与代码证明，目前是研究设计建议。

## 9. 后续验证问题

优先明确物理 IRQ 的注册 owner、可信接收位置、Host 可修改的 GIC/LR 字段，以及电平 IRQ 的清状态/EOI 责任。然后验证伪造、重放、乱序、合并、ACK 延迟、设备 reset 和 Client close/reopen。测试结果应同时记录是否出现错误 SUCCESS、是否提前回收、其他 Client 是否受影响，而不只记“IRQ 到达”。

关联：[聚焦报告](GPU_CCA_TEE_FOCUSED_RESEARCH_20261027.md)、[CAEC 精读](GPU_CAEC_DEEP_REVIEW_20261027.md)、[TEEtime 精读](GPU_TEETIME_REVIEW_20261027.md)。

统一记录：Devlore 原文精读与研究映射｜项目 glmark 本次未测 → 未测｜分差不适用｜未改运行代码，无新增性能测量｜没有硬件命令、run-id 或新增 PASS｜保留研究结论，源码与本项目机制验证待后续任务。
