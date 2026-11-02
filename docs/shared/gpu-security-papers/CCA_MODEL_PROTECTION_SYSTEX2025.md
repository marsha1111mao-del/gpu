# SysTEX 2025 CCA 模型保护：完整模型部署、共享 I/O 与可信完成边界

研读日期：2026-10-28。完整阅读10页arXiv v1正文、54条参考文献及附录A/B/C；图示按图注与正文理解，未逐像素核对。核对作者官方仓库固定提交的README及3份文本源码，未执行。本文是GuaranTEE后续的CCA模型部署与评估研究，GPU设备接入属于展望。未改运行代码，无新增性能测量。

## 1. 书目、版本和来源

完整标题 An Early Experience with Confidential Computing Architecture for On-Device Model Protection。作者 Sina Abdollahi、Mohammad Maheri、Sandra Siby、Marios Kogias、Hamed Haddadi；Imperial College London及NYU Abu Dhabi。论文页首标记accepted to SysTEX 2025，Crossref核对正式DOI `10.1109/EuroSPW67616.2025.00052`、页码401–410、出版日期2025-06-30。

实际阅读[arXiv2504.08508v1](https://arxiv.org/abs/2504.08508v1)，2025-04-11；[PDF](https://arxiv.org/pdf/2504.08508v1)1070184字节，SHA256 `44a3e09b0d42004c8400f42170daff8b2a330f592fc80c67befb1308d4de5fee`。完整10页含全部附录，不冒称阅读了出版方最终排版或用摘要代替正文。

论文脚注指定[官方CCA-Evaluation](https://github.com/comet-cc/CCA-Evaluation)，固定提交 `b88d76d7725ef4d787a5c6f2d8eafce3beb41573`，提交日期2025-06-05。取得仓库元数据与commit；递归树API限流403，codeload超过15MB获取上限而终止，均保留失败。没有取得完整树，不声称遍历或审计整个artifact。

固定提交README全文核对：SHA256 `3641a3b9b583e672d8772728fe6d2015711587250ac830c774332be3597d337f`；全文静态读 `tracing-scripts/count_pattern.py`、`scripts/download-source.sh`、`overlay/mobilenet/hypervisor_overlay_mobilenet/root/create_realm_VM_100.sh`。README链接的marker源码路径返回404，MIA独立仓库本轮未读；3份源码记录字节数、SHA256和计算出的Git blob SHA1，但未取得树内blob作独立比对。

## 2. 为什么与本项目相关

它直接回答CCA能否容纳完整边缘模型、如何取得模型、如何与Normal World交换推理请求，以及怎样分解Realm运行成本。相对GuaranTEE 2024，扩展为8类模型配置、分阶段指令统计及成员推断评估，不能把同一研究路线的后续版本计为另一套GPU隔离架构。

它与Portal/CAGE/ACAI的关系是上层可信应用与底层设备保护的互补：本论文把完整模型放入Realm；设备论文进一步解决Realm怎样安全使用GPU或其他设备。本文没有建立多Client GPUVM隔离、SMMU授权映射、可信GPU中断或native fence完成证明。

论文中的Client是边缘终端一方，本项目的Client是经RMM认证的请求Realm。两者同名但身份粒度不同；不能把“终端通过证明”直接当作“某个Client拥有某张物理页或某次GPU任务”。

## 3. 威胁模型与真实可信基

模型提供者和终端互不信任，但共同信任第三方提供的Realm镜像。Normal World用户程序、OS及hypervisor均可恶意；Root Monitor、RMM、硬件以及Realm内部OS、库和模型服务需要可信。论文以RMM代码体积和既有验证研究支持可信假设，不等于所有后续固件版本、Realm Linux及服务代码都已形式化验证。

物理攻击和侧信道不在范围内；假定hypervisor提供足够CPU时间和内存。隔离能阻止Normal World直接读取或改写私有模型，不保证服务可用性、时限、公平调度或所有黑盒查询安全。模型所有者信任整个Realm镜像也意味着Realm内恶意组件不由本文解决。

GPC按PAS及访问者安全状态检查，不单独区分不同Realm的所有者；Realm间隔离还依赖RMM管理的地址转换与归属。本文“激活后hypervisor不能填入新内容”应理解为不能任意向已保护地址注入内容，不能扩展为Realm运行后完全不存在合法增页或按需delegation；附录A明确描述后者。

## 4. 部署、证明及服务生命周期

框架8步：取得可信镜像；创建并激活Realm；Realm与模型提供者建立TLS；取得并传递证明；提供者验证后发送模型；宣布可接受请求；接收输入并推理、交付输出；检查服务条件和模型更新。推理请求和响应通过virtio-9p共享文件系统交换。

该流程建立模型下发的设计位置，但所读3份源码集中在构建来源、VM启动和trace分析，不能据此验证完整TLS、quote验证、模型供应或更新实现。正文也没有给出可直接审计的完整会话协议、挑战格式和密钥派生过程。

可信部署应把证明的新鲜挑战、Realm测量、服务策略及TLS会话密钥绑定；还应明确模型版本、更新签名和防回滚依据。这是本项目可采纳的协议要求，不是论文已证明具备的全部属性。启动测量也不直接证明后续每次输入、GPU执行和输出都正确。

论文建议镜像中实现使用期限或最大推理次数，达限后请求hypervisor终止。但恶意调度、重启旧镜像、恢复旧计数或时间来源不可信时，限额与期限还需要在线授权或受保护的新鲜状态。本文没有建立持久计数/可信时间/跨重启防回滚的完整保证；不能由“Realm会主动退出”推导不可重复使用。

## 5. 性能指标：17–22%是什么

作者使用FVP Base RevC2xAEMvA 11.25_15、TF-A2.11、tf-rmm0.5.0、linux-cca及Buildroot；FVP模拟2簇、每簇4核、Armv9.2-A、4GB内存。主机Ryzen7 PRO3700、16GB、Ubuntu22.04.4。这属于作者实验配置，不是本轮运行结果。

FVP不是周期精确模型；论文明确不把指令计数当实际CCA硬件时延。最高22%是每次推理服务指令数增加，不是GPU延迟、GPU吞吐损失或本项目glmark变化。本文讨论模拟指标的适用范围，不以实验硬件缺少某能力否定本项目的设计假设。

8个配置涵盖AlexNet、MobileNet、ResNet18、Inception、VGG、GPT2、GPT2-large及TinyLlama；VM内存300–3650MB，所列模型约9–1169MB。每种配置5个VM、每VM5次推理，共25次。作者称各项标准差低于10%而省略；表3标题提标准差但数据没有逐项列出，不补造置信区间。

| 配置 | Realm/NW总指令数（百万） | 表中开销 |
| --- | --- | --- |
| AlexNet | 105.9 / 87.8 | 20% |
| MobileNet | 351.8 / 289.3 | 21% |
| ResNet18 | 442.8 / 363.2 | 20% |
| Inception | 8717.2 / 7201.1 | 21% |
| VGG | 6713.2 / 5717.9 | 17% |
| GPT2 | 13144.9 / 10726.3 | 22% |
| GPT2-large | 76412.3 / 62156.4 | 22% |
| TinyLlama | 97433.3 / 81905.6 | 18% |

四阶段为初始化、读输入、推理计算和写输出；表内总数不能简单认为等于四个可见子项之和。例如MobileNet四项Realm合计342.5M，而总计351.8M；正文没有完整解释所有差额。不能据此编造额外隐藏成本的精确来源。

表3也有内部算术疑点：MobileNet读输入4.7/1.1M却标100%，按可见数计算增加约327.3%；GPT2写输出0.11/0.04M标75%，按可见数约175%。较小数的取整会影响百分比，但不足以统一解释这些差异；引用总量和子项时应分别保留原值，原始样本未重算。

附录B单次MobileNet推理统计Realm侧EL0/EL1/RMM/Monitor及Normal World支持代码。Realm实验总328.01M，对NW278.83M，增加约17.64%；这是另一实验，不能代替表3的351.8/289.3M。RMM41.18M支持减少异常路径的动机，但没有证明GPU中断是本项目开销主因。

附录C启动表的可见开销867%、1902%、1832%、1665%，终止644%、2405%、3521%、1421%。正文写启动最高21,902%，与表6最大1902%及24960.7/1246.6M不一致；保留为文本/表格冲突，不沿用21,902%作可靠测量。所有数仍是指令数，不是启动秒数。

作者在主实验前分配并填充VM可用用户内存，将首次按需delegation成本前置；用isolcpus/taskset隔离trace核，并以HLT和MOV标记分段。温态推理和启动/初触页分开测量是合理方法，但不能把17–22%套用到包含创建、模型下载、证明及冷页的端到端服务。

## 6. 成员推断收益的边界

MIA评估固定训练集、改变shadow/train比例为1、1/4、1/8；对AlexNet和ResNet18、CIFAR10/100及配置32类的CelebA比较NW白盒与Realm黑盒label-only接口。论文表4平均差额分别12.4和4.2，总平均8.3。

这里应解释为所测攻击成功率平均下降约8.3个百分点，而不是普遍相对下降8.3%，更不是彻底防住成员推断。AlexNet的某些条件差额为−0.9、−10.6个百分点；ResNet18也有−2.5。即使不暴露权重，某些黑盒条件仍有较高攻击成功率，平均数不构成逐模型、逐数据集保证。

白盒→label-only黑盒同时改变攻击者可用信息；结果说明所选接口和攻击设置下的收益，不能外推为任意输出API。若服务暴露完整logits、梯度、调试信息或无限制查询，需重新定义允许泄漏与测量。本文也没有对LLM给出同样MIA收益。

MIA在另一台双Xeon Gold6136、251GiB、Quadro GV100机器执行。GV100用于攻击实验加速，不在FVP Realm推理保护链内，不能把该GPU列作本文已经实现CCA GPU安全执行的证据。

## 7. 官方artifact的有界静态核对

README提供base、mobilenet和gpt2三类复现入口，链接独立 `CCA-Membership-Inference` 的SysTEX25分支；页面展示available/functional/reusable徽章，但本轮没有重做artifact评估，也没核对MIA仓库或全部8类模型对应源码。

固定提交下载脚本使用FVP11.27_19和FastModels11.27说明，与论文11.25_15不同；linux/kvmtool依赖按branch取得，Buildroot2023.08，llama.cpp固定 `e02b597be3702174e7b47b44cd03e1da1553284b`。因此固定artifact提交可用于精确静态观察，但不自动等同于论文全部测量输入或完全锁定依赖的manifest。

MobileNet启动脚本将marker和lkvm绑定CPU1，lkvm使用nice−20、1vCPU、400MB、GICv3-ITS、禁SVE、9p共享及realm选项。这支持论文的trace与共享I/O方法，不能证明安全中断注入或认证文件信号已经实现。

trace脚本按 `INST_COUNT` 和MOV模式逐行找标记，以同类标记相邻两次为一对计算差值；按实验标记分段。它会报告少于两个标记，但没有强制完整起止集合；奇数末尾标记不形成配对，split过程异常捕获后仅打印。它同时输出原始统计和IQR去异常统计，所绘原始分布并非一律丢弃异常样本。

因此若复用统计方法，应先校验标记成对、分段完整、预期25次样本和trace未截断，再报告成本；“成功打印均值”不是完整采样证明。上述是离线测量可靠性观察，不是生产TEE漏洞或对作者结果的复现否定。没有执行脚本、sudo安装、构建、FVP、模型或攻击。

## 8. 对本项目内存与中断隔离的设计启发

保留目标模型：RMM认证原始Client，可信ProxyRealm统一控制SMMU；映射建立时检查对象归属、实际HPA授权、权限和生命周期，软件IPA→HPA合成直接HPA的受保护GPU Stage-1，执行期由硬件Stage-1限制访问；其他设备继续硬件Stage-2。本文不要求替换该模型，也不证明GPU Stage-1单独具备所有授权语义。

第一部分“直通/共享实现与性能”可借鉴冷热阶段分测：Realm创建和首触、对象注册与映射、驻留计划首次执行、稳态任务、完成回传、撤销回收分别计量。减少跨Realm调用、合并通知和复用计划，必须保持同一Client授权与真实终态，不把降低通知次数直接当提分证据。

第二部分“任务隔离”应把内存与通信写成同一生命周期：RMM身份→认证队列接收→私有输入快照和授权→真实GPU提交→native fence终态→缓存同步及输出可见→按cookie/epoch发布成功或错误→设备静止后回收。复用现有GPUVM、plan/snapshot和持久IRQ127；不另造平行身份或token体系。

与本论文共享9p信号不同，本项目通知来自RMM保护的pending/ack/armed通道；但即使通知来源可信，IRQ本身仍只表示“应检查状态”。另一Client、旧epoch、重复/乱序事件、共享描述符修改都不得制造成功fence、改变输出归属或触发提前释放。任务完成必须来自正确原生fence的终态，失败和取消不能落成成功。

建议将中断研究的可验证属性写清：来源及目标Client正确；会话/对象/任务代际匹配；重复通知不重复执行或完成；丢失通知后持久状态仍可恢复；错误/取消/reset有明确终态；旧DMA停止并同步后才能复用页。由不可信Host拒绝调度导致的无限延迟应与错误路由、伪造成功分开，不能宣称CCA提供无条件可用性。

远程证明如加入，应覆盖服务镜像、关键保护策略、固件版本及Client–Proxy会话绑定；一次quote不升级为每次GPU执行证明。模型/输入/输出真实性与使用配额可以作为应用层扩展，项目主线仍是直通共享、GPUVM内存隔离和可信任务完成通信。

## 9. 后续引用链与保留项

直接延续Portal/CAGE/ACAI/Devlore及其版本研究；本文引用的GuaranTEE、TEE分割攻击和CCA验证研究用于补充模型部署及可信基边界。下一篇已取得39页预印本的CPU–GPU机密计算综述 `arXiv2408.11601v3`、正式CSUR DOI `10.1145/3793532`，尚未全文阅读，不能登记完成。

GR-T正式全文和XpuTEE全文HTML本轮均403；不以CODY早期稿、GPUReplay或摘要补位。DICE-anchored Realms的机构PDF403也仅列待办。新检索出现MirageNet、TEE-X、BiShield-TEE等元数据候选，须进一步核对原文、版本与项目相关性，再决定是否独立精读。

证据：`build/cca-gpu-followup-20261027/` 中early、cca-model-early及batch51获取记录；全文按页提取、固定commit和所读文本可追溯。没有取得完整树/匹配全部测量版本/验证全部供应协议，不报告为已完成这些工作。

统一记录：10页全文/54条参考文献/附录A–C、固定README及3份源码静态阅读、Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/FVP/模型/攻击run-id｜保留论文与方法，原始数据、完整artifact、证明供应协议及GPU实现未验证。
