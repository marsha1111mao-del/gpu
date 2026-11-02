# CCA / GPU TEE 定向续研：新候选与共享任务安全边界

日期：2026-10-28，第123批。本篇是文献检索与专题分析，新增三个待查候选，不增加独立全文精读完成数。研究仍在继续；未改运行代码，无新增性能测量。

## 1. 本轮核验与去重

重新取得用户指定的 [GPU Security Papers](https://github.com/trilateral-gpu-sec/gpu-security-papers) README，并检查 Fengwei Zhang、Yunjie Deng 和上海交大 IPADS 的公开页面。该集合可用于发现 StrongBox、GR-T、GEVisor、HETEE 等工作，但本次取得的 README 未列 PORTAL、CAGE、ACAI；它适合作为入口，不能单独代表 CCA GPU 研究现状。

LÆGIS 引用的 NVIDIA GPU Confidential Computing Demystified（arXiv:2507.02770）已改题为 Blueprint, Bootstrap, and Bridge，并已在本库按 MLSys 2026 正式版研读。重新下载的 PDF SHA256 与既有 v2 一致，不作为新增论文或新架构计数。[既有报告](BLUEPRINT_BOOTSTRAP_BRIDGE_MLSYS2026.md)。

Crossref 的宽泛 CCA/GPU 查询包含大量无关结果，其中一次查询被限流；arXiv 的 CCA/device 查询超时，GPU/confidential/TEE 查询成功但也有无关命中。以下是有来源的有限检索结果，不宣称穷尽，也不由零命中推断论文不存在。

## 2. 三个新候选：先记录来源，不用标题替代全文

| 候选 | 本轮核实的来源与书目 | 与项目的关系及证据限制 |
| --- | --- | --- |
| RS-Infer: A Fast and Secure LLM Inference System for Mobile Devices with Recallable Resource Isolation | [IPADS 出版列表](https://ipads.se.sjtu.edu.cn/pub/publication)。Yinpeng Wu、Yitong Cheng、Lixiang Wang、Jinyu Gu、Zhichao Hua、Yubin Xia；机构列为 ACM SIGOPS ATC 2026，11月。 | 优先级最高：值得检查可撤回资源隔离与当前任务撤销/回收的关系。但截至本次只有机构书目，尚不能确认使用哪类 TEE、是否保护 GPU、攻击者权限和撤销机制；不称 CCA GPU 方案。该会议日期晚于本次调研日期，不写成已经完成会议发表。 |
| HSMEM: Heterogeneous Secure Memory with Scalable and Energy-Efficient Data Transfer | [IPADS 首页](https://ipads.se.sjtu.edu.cn/)与[出版列表](https://ipads.se.sjtu.edu.cn/pub/publication)。Sheng Qiang、Shulin Fan、Jinyu Gu、Zhichao Hua、Yubin Xia；机构列 MICRO 2026。 | 值得追查异构安全内存与传输，但只有机构标题/作者/会议信息，不能确定 GPU/CCA 实现、密码协议或性能。出版列表将“and”写作“an”，保留两页题名差异；不能据题名推断其与 XpuTEE 的继承关系。 |
| CUSAFE: Capturing Memory Corruption on NVIDIA GPUs | [Fengwei Zhang 出版列表](https://fengweiz.github.io/publications.html)。Hongyi Lu、Fengwei Zhang、Zhenkai Zhang、Shuai Wang、Yanan Guo；作者列 USENIX Security 2026。 | 支撑资料：应检查它解决程序级内存破坏还是可信隔离。作者页链接为空；尝试的 USENIX 页面/PDF 返回403，两个猜测作者PDF路径404；未取得全文，不引用机制、检测率或开销。作者页面仍写“To Appear”，本轮未独立确认最终会议版本。 |

HSMEM、RS-Infer 的定向 arXiv 标题查询返回零条；Crossref 模糊检索返回其他论文，没有获得匹配 DOI。它们不计全文完成，也不能把相近搜索结果的 DOI/摘要错误归给候选。后续优先检查正式会议、作者和机构公开全文。

## 3. 最契合项目的文献组合

下面是已有报告的阅读顺序，不把它们重复记作本批新增论文。

| 问题 | 优先论文 | 本项目需要补充的论证 |
| --- | --- | --- |
| 可信 GPU 服务、共享和设备归属 | [PORTAL](PORTAL_SP2025.md)、[CAGE](CAGE_NDSS2024.md)、[ACAI](ACAI_USENIX2024.md)、[CAGE期刊扩展](CAGE_TDSC_EXTENSION_2026.md) | 可信 Proxy 服务每个原始 Client 时，授权必须贯穿实际页、GPUVM、任务、完成与退出。不同系统的独占/共享及可信组件边界分别比较。 |
| 实际页与内部控制器 | [PhantomMap](PHANTOMMAP_NDSS2026.md)、[MOLE](MOLE_CCS2025.md)、[FAARM](FAARM_ARXIV2025.md) | 映射检查覆盖实际 backing；可信固件假设与加载/重载/reset 的设备代际一致。FAARM 的预印本和代码证据强度按其报告单独保留。 |
| 物理中断保护与可信代理 | [Devlore](../GPU_DEVLORE_DEEP_REVIEW_20261027.md)、[TEEtime](../GPU_TEETIME_REVIEW_20261027.md) | 保护 GPU→Proxy 的物理事件来源、配置和确认；再由可信驱动将设备状态对应到具体任务。物理 IRQ 不能直接证明某 Client 成功。 |
| 跨 Realm 通信与组合身份 | [CAEC](../GPU_CAEC_DEEP_REVIEW_20261027.md)、[MICA](MICA_ARXIV2026.md) | 参与者实例、共享授权和通信策略应覆盖通知端点；受保护共享页不使恶意 Client 的请求自动合法。 |
| 商业 GPU CC 控制面与回收证据 | [Blueprint, Bootstrap, and Bridge](BLUEPRINT_BOOTSTRAP_BRIDGE_MLSYS2026.md) | 签名提交、调度确认、真实完成和清零完成分开；未认证共享状态不能成为提前回收依据。论文潜在风险不写成已确认产品漏洞。 |
| 保护条件不变时的性能 | [Dissecting](DISSECT_GPU_CC_ISPASS2025.md)、[LÆGIS](LAEGIS_ISCA2026.md)、[PipeLLM](PIPELLM_ASPLOS2025.md) | 分离启动、提交、迁移、执行与通知开销；预取/预加密须保持源版本、授权与生命周期一致。H100密码传输机制不能直接套为片上可信共享内存的必要开销。 |

## 4. 对当前架构的进一步判断

继续采用用户给定前提：RMM认证原始Client；ProxyRealm统一控制SMMU，GPU仅启用受保护Stage-1，在建图时完成实际HPA授权和软件IPA→HPA翻译；其他设备采用经过授权检查的硬件Stage-2；页表、根、关键MMIO和可信固件加载受平台保护。硬件只是模拟验证载体，不据板端能力否定这些设计假设。

在此前提下，进一步增加地址翻译层不是首要研究任务。更有价值的是证明：映射建立、任务执行、可信终态与资源交接使用同一套身份和生命周期。页级隔离已经成立时，过期任务的合法旧访问仍可能与新所有者冲突；消息代际检查也不能停止设备继续DMA。

建议将项目第二部分具体表述为“共享GPU任务的内存隔离与可信完成通信”，并分别提出三项可检验性质。

第一是任务授权的一致性：原始Client实例、session、GPUVM/root generation、对象/backing generation、权限、device epoch和cookie通过可信对象引用关联。共享描述符复制为私有快照后，设备只使用被持有的授权对象；请求者自填的Client编号不能成为权威身份。这是设计建议，不意味着当前代码缺少全部绑定。

第二是完成状态的真实性：可信驱动依据真实native fence及错误状态推进正确任务的终态，Client通过可信记录确认结果。通知只提示读取状态；重复、合并、迟到或丢失通知不能制造SUCCESS、改变另一个Client的任务或提前放页。GPU多队列合法乱序也必须被允许。

第三是撤销后的安全交接：禁止新引用，处理已有任务和访问者，获得可信设备停止访问依据，完成必要的映射撤销、失效及清理，才允许资源复用。具体顺序由设备停止所需条件决定。device epoch递增只拒绝旧消息，不独立证明DMA静默；reset范围可能影响所有Client，不能默认局部恢复。

必须继续区分通知到达、任务终态、输出可见、应用计算正确、输出允许发布、DMA静默及安全复用。一个真实中断或成功fence都不能单独证明以上全部性质。

## 5. 可以形成贡献的差异与验证

相对Devlore，候选增量是从物理设备事件扩展到多Client任务语义与生命周期；相对CAEC，是共享通路之上的可信通知与消费协议；相对PORTAL/CAGE/ACAI，是共享任务从授权到安全交接的一体化证明。是否已有同等机制仍需逐项比较，不能仅凭组合文献宣布创新。

优先设计四组负例：两个Client使用相同本地cookie；reset后迟到旧fence/通知；共享描述符在校验后变化；取消/撤销与在途DMA重叠。每组检查是否错误成功、跨Client消费、提前回收，以及另一Client是否保留正确错误语义。中断计数、唤醒成功或单次运行通过不足以替代这些检查。

性能分别报告提交、完成通知、吞吐、CPU占用、撤销及恢复成本；保持相同安全配置和负载。LÆGIS的设计加速主要来自模拟，不能当作现成H100部署结果；Dissecting的188.88倍涉及non-UVM/non-CC分母，不能解释为同UVM开启CC的统一增量。具体数值和限制见逐篇报告。

## 6. 下一批的收敛顺序与本轮边界

优先取得RS-Infer可靠全文，确认其是否涉及GPU/TEE和可撤回资源；其次追查XpuTEE、GR-T正式版、LGT4CG及HSMEM。CUSAFE用于补充程序级内存安全边界，优先级低于直接CCA/GPU共享工作。本轮再次确认XpuTEE的OpenAlex记录没有公开PDF入口，ACM返回403；GR-T猜测Apple路径404，不据此断言不存在全文。

已完成独立报告仍为原库53/63、扩展145、合计198，包含支撑论文、版本与技术资料，并非198套CCA GPU架构。本篇是专题更新；三个候选全文尚未取得。来源响应、失败记录和哈希保存在build/cca-gpu-followup-20261027/的123批文件，未运行作者代码、模拟器、攻击或硬件测试。

统一记录：定向检索/版本去重/三个候选登记/跨论文分析｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件run-id与新增性能PASS｜保留研究，整体继续。
