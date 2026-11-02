# CCA / GPU TEE 续研：直接相关论文、待补全文与任务隔离设计

更新：2026-10-28，第83批。本文是跨论文专题分析和来源复核，不是新增论文精读；不增加独立精读完成数。既有逐篇报告提供机制依据，本批新核对的书目、摘要和下载失败分别标明。未改运行代码，无新增性能测量。

## 1. 收敛后的研究问题

研究主线保持两部分：第一部分实现 Arm GPU 直通、共享及性能优化；第二部分研究不可信 Host 与互不信任 Client 下的任务内存和中断通信隔离。后续文献应优先回答这两个问题，而不是不断扩展一般 GPU 安全清单。

继续接受项目假设：RMM 认证原始 Client；可信 ProxyRealm 控制 SMMU，在建图时校验对象、实际 HPA、权限及生命周期，以软件 IPA→HPA 翻译合成受保护 GPU Stage-1；其他设备保留硬件 Stage-2。平台保护实际页表、根配置、关键 MMIO 和固件加载。硬件载体不用于否定这些架构假设。

在这些前提下，页表机制可以相对稳定，但安全研究尚未结束。后续问题是：授权对应哪次任务实例，何时生效、何时撤销，设备完成如何与该实例绑定，以及什么条件下允许复用页面。增加重复的页表层次通常不如把这些边界说明清楚有价值。

## 2. 已有全文中最应接着使用的论文

以下是已有逐篇研读的精简阅读路径，不作为本批新增成果计数。不同系统的威胁模型和原型范围须保留。

| 论文 | 可靠入口与已有解读 | 对本项目的下一层问题 |
| --- | --- | --- |
| PORTAL，IEEE S&P 2025 | [DOI](https://doi.org/10.1109/SP61157.2025.00013)；[既有报告](PORTAL_SP2025.md) | 可信设备服务怎样绑定当前 Client、设备和服务实例？服务可信不免除请求授权。 |
| CAGE，NDSS 2024 | [会议页](https://www.ndss-symposium.org/ndss-paper/cage-complementing-arm-cca-with-gpu-extensions/)；[既有报告](CAGE_NDSS2024.md) | 从保护单次真实执行窗口走向互不信任 Client 的共享，需要补哪些身份、调度与退出条件？ |
| ACAI，USENIX Security 2024 | [会议页](https://www.usenix.org/conference/usenixsecurity24/presentation/sridhara)；[既有报告](ACAI_USENIX2024.md) | 将身份与实际映射归属一致性延伸到提交、完成、撤销全过程。 |
| Building Confidential Accelerator Computing Environment for Arm CCA，TDSC 23(1)，2026 | [DOI](https://doi.org/10.1109/TDSC.2025.3615787)；[作者全文](https://fengweiz.github.io/paper/cage-tdsc25.pdf)；[既有报告](CAGE_TDSC_EXTENSION_2026.md) | CAGE 期刊扩展引入 FPGA 工作流，说明授权对象和回收粒度应随设备状态位置调整；不是另一套无关架构，也不证明恶意多 Client 并发。 |
| MOLE，CCS 2025 | [DOI](https://doi.org/10.1145/3719027.3744823)；[作者全文](https://fengweiz.github.io/paper/mole-ccs25.pdf)；[既有报告](MOLE_CCS2025.md) | 固件加载链、MCU 和运行期控制影响隔离与完成来源；在已接受可信固件假设后，仍需说明 reset 和固件重载如何改变设备 epoch。 |
| PhantomMap，NDSS 2026 | [DOI](https://doi.org/10.14722/ndss.2026.240201)；[会议全文](https://www.ndss-symposium.org/wp-content/uploads/2026-f201-paper.pdf)；[既有报告](PHANTOMMAP_NDSS2026.md) | 检查最终实际页和页来源；GPU 页类别本身不等于特定 Client 的授权，导入、别名与复用也须绑定归属。该论文是攻击与缓解研究，不是 GPU TEE 架构。 |
| AutoSecGPU，IFIP SEC 2026 | [DOI](https://doi.org/10.1007/978-3-032-27993-4_33)；[既有报告](AUTOSECGPU_IFIPSEC2026.md) | 合法映射、二进制和顺序之外，参数是否符合模型所有者授权？适用于扩展应用完整性目标，不要求所有图形任务固定离线轨迹。 |
| AvaGPU，CCS 2023 | [既有报告](AVAGPU_CCS2023.md) | 当攻击者提交长任务或大量事件，可信抢占、进度监测及处理预算能否限制干扰？它与单纯内存隔离互补。 |

CAGE 扩展版 DOI 中的 2025 与正式卷期的 2026 不矛盾，引用时应明确版本。AutoSecGPU 的参数验证平均增量不能当作整个 GPU TEE 总开销，也不能转用为本项目性能结果。

## 3. 本批继续补查的直接候选及证据边界

| 候选 | 已核验内容 | 尚未取得与使用限制 |
| --- | --- | --- |
| XpuTEE: A High-Performance and Practical Heterogeneous Trusted Execution Environment for GPUs | [DOI](https://doi.org/10.1145/3719653)。Crossref 核对作者 Shulin Fan、Zhichao Hua、Yubin Xia、Haibo Chen；摘要提出跨 CPU/GPU 的 XpuEnclave，由 CEnclave 和多个 XEnclave 组成，报告常见 AI 应用平均开销 2.48%。 | 本批再次检查 IPADS 出版列表；ACM 全文入口仍返回 403。上述机制与数字只来自摘要，尚不能判断具体威胁模型、零额外复制成立条件、固件信任、多租户能力或中断协议，不计精读完成。 |
| Safe and Practical GPU Computation in TrustZone，GR-T，EuroSys 2023，505–520 | [DOI](https://doi.org/10.1145/3552326.3567483)。OpenAlex 正式条目确认标题、会议页码及出版方 PDF 入口。 | 正式 PDF 本批仍为 403。arXiv 2111.03065v1 是已有早期 CODY 版本，不能据它声称读完 GR-T 正式版；GPUReplay 也不替代本篇。 |
| LGT4CG: Lightweight GPU-TEE for cloud GPUs，Journal of Systems Architecture，2026 | [DOI](https://doi.org/10.1016/j.sysarc.2026.103886)。Crossref 核对正式标题、八名作者以及 Elsevier 文本挖掘入口；第一作者 Fengyuan Yu，作者还包括 Chenlin Huang、Zhichao Hua 等。 | 此前 XML 仅 coredata；本批 text/plain 请求返回 400。尚无正文，不推断机制或性能。与 AutoSecGPU 存在作者交集只用于追踪来源，不证明二者是同一系统或正式扩展关系。 |
| DICE-anchored Realms on Arm CCA | [机构条目](https://iris.polito.it/handle/11583/3006556)。属于需要继续追踪的 CCA 信任链候选。 | 本批条目为 Cloudflare 页面、替代 retrieve 路径为 403；尚无可核验正文，不据标题认定其保护 GPU，也不据此替代已有 ASTER 分析。 |

本批还尝试从用户指定的 GitHub 文献集合读取最新 README，但请求超时；搜索引擎请求网络不可达。没有获得最新完整清单，不能声称该仓库已重新全面检查，或没有其他相关论文。下一次重试应优先新增作者、机构或 artifact 来源，而不是重复相同受阻地址。

AccShield 和 CPU-FPGA Salus 仍是相邻加速器候选；在直接 GPU/CCA 缺项未补齐前，不以它们或一般驱动论文充当新的直接 GPU TEE 成果。AccShield 已固定公共树仅代表取得 artifact 索引，不等于已完成源码安全审计。

## 4. 与中断安全论文怎样衔接

Devlore、CAEC、TEEtime 用于讨论 CCA/Realm 的设备中断、控制权与时间隔离；Heckler、WeSee、Sigy 用于理解不可信宿主注入异常或信号时，处理器件如何产生未经授权的副作用。跨架构论文提供威胁启发，不代表在本项目 Arm 路径已复现同一攻击。

研究时至少分开五个命题：IRQ 到达、某个任务进入终态、输出可见、执行满足应用预期、DMA 已停止。任意一个都不能直接推出其余全部成立。特别是“来自真实 GPU 的 IRQ”不能单独认证具体 Client/job，也不能作为回收全部相关页面的充分条件。

可信边界应包括事件状态、路由与通知接口的副作用，而非只保护一个中断号。Guest 可见的通知负责唤醒；GPU 错误、取消、reset 和真实 native fence 决定可信任务记录如何变化。是否能保证通知及时，还取决于调度和宿主能否阻塞，不应把通知完整性写成无条件可用性。

## 5. 建议形成的设计：任务授权到安全复用的连续协议

以下是组合论文后的研究建议，不是本批已实现机制，也不是已确认的当前代码漏洞。现有 GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch、persistent IRQ127 继续作为承载点，避免再建一套平行身份体系。

第一，建立或核验任务记录中的身份绑定：原始 Client 实例、session、GPUVM/root generation、对象 backing generation、访问权限、job cookie 和 device epoch。字段可引用受保护对象，无须每条消息重复整个结构。身份来自 RMM/可信端上下文，不能来自请求者自填编号。

第二，提交前把对象授权和可变请求落实为私有执行快照；解析器只消费经范围、长度、溢出、权限和类型检查的数据。建立 PTE、提交硬件和完成处理必须引用同一批被持有的对象及 backing，防止检查后更换别名、间接描述符或底层页。参数策略仅在应用授权目标需要时增加。

第三，原生完成事件只允许推进其所属任务的可信终态。终态包括成功、错误、取消等；reset 使旧执行身份失效。通知在输出同步和终态发布之后发出，Client 醒来读取受保护或认证的记录。重复通知应幂等，晚到事件不得完成新任务，不应假设多个队列按提交全序完成。

第四，把“任务终态可消费”和“对象可安全复用”分开。安全复用需要阻止新引用、处理已有访问者、得到可信 DMA 停止依据、撤销相关映射并完成必要失效，最后按保密性目标清理残留状态。具体先后顺序须按设备停止访问所需条件实现；单纯 epoch 递增只能拒绝旧消息，不能停止旧 DMA。

第五，定义干扰边界。每 Client 的在途任务、队列深度、可信处理时间和恢复请求应有明确策略；中断合并、限流或批处理不能丢失权威终态。若需要有界撤销或完成时间，还须给出调度、抢占、硬件响应的前提；没有这些前提时只承诺隔离与可恢复性。

## 6. 可以验证的命题与实验设计

| 命题 | 有区分力的反例或负例 | 观察结果 |
| --- | --- | --- |
| 原始身份与对象权限一致 | 两 Client 使用相同本地 cookie、替换另一方对象 ID、合法 VA 指向越权 HPA | 未授权请求拒绝；不产生越权 PTE 或提交 |
| 检查和使用同一对象实例 | 提交后改共享描述符、导入别名、释放后复用相同 ID、变更 backing | 设备只使用已授权快照，或安全拒绝；对象持有期明确 |
| 完成属于正确任务实例 | 合法跨队列乱序、重复 IRQ、旧 epoch 的迟到 fence/通知、reset 与 Client 重连并发 | 无跨 Client/跨代成功；合法乱序可完成；错误保留 |
| 通知不决定回收授权 | 隐藏、重复、延迟通知；取消与 GPU 实际访问重叠 | 可查询或恢复终态；未静默前不复用页面 |
| 一个 Client 的恢复不突破另一方边界 | 错误洪泛、长任务、重复 reset 请求 | 根据明确策略拒绝、隔离或进入受控全设备恢复；不把所有 reset 都宣称可局部化 |

这些是后续验证计划，本批未执行。性能评价应分别测提交/建图、完成路径、吞吐、CPU 成本及异常恢复，并维持 glmark 正确性和资源恢复检查；没有新数据时不宣称优化收益，也不把不同论文平台的平均开销横向排序。

## 7. 结论与继续顺序

优先取得 XpuTEE、GR-T 正式版及 LGT4CG 的可靠全文，按既有逐篇标准分析；同名、早期稿与正式扩展保持版本关系。已有全文的应用顺序为 CAGE 扩展／MOLE／PhantomMap → 任务授权与快照 → 可信完成通信 → 撤销和安全复用。中断和可用性论文围绕这条任务路径使用。

这支持项目第二部分聚焦“共享 GPU 的任务隔离与可信完成通信”。能否形成论文贡献，要以相对已有工作的明确差异、实现覆盖和负例验证证明，不能仅凭将现有机制串接就认定创新成立。

统一记录：直接 GPU/CCA 候选来源复核及跨论文专题｜精读统计不增加，仍原库53/63、扩展113、合计166（含支撑/版本/资料，非166套 GPU TEE）｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、构建、模型或攻击 run-id；来源失败保留，整体研究继续。
