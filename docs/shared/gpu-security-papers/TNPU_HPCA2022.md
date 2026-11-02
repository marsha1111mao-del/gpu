# TNPU（HPCA 2022）：可信 NPU、物理页归属与 tensor 版本新鲜性

## 研读结论与来源

TNPU 将两个问题分别处理：CPU/NPU 访问某个实际物理页是否有权限，以及该页中的数据是否是可信计算当前需要的版本。前者通过受保护的物理页反向归属表校验，后者通过可信 CPU 软件维护 tensor/tile 版本、逐块 MAC 和内存加密实现。其研究价值不只是减少完整性树开销，而是展示了把安全检查交给可信软件时，数据流约束与版本状态本身会进入可信基。

论文：Sunho Lee、Jungwoo Kim、Seonjin Na、Jongse Park、Jaehyuk Huh，TNPU: Supporting Trusted Execution with Tree-less Integrity Protection for Neural Processing Unit，IEEE HPCA 2022，229–243 页，DOI：[10.1109/HPCA53966.2022.00025](https://doi.org/10.1109/HPCA53966.2022.00025)。[作者出版页](https://jaehyuk-huh.github.io/publications.html)；[作者完整 PDF](https://jaehyuk-huh.github.io/papers/lee_hpca22_tnpu.pdf)；[22 页报告幻灯片](https://jaehyuk-huh.github.io/slides/2022_04_HPCA_TNPU_slide.pdf)。

本轮完整阅读作者 PDF 的 15 页、全部 60 条参考文献及 22 页幻灯片，核对 Crossref 的题名、作者顺序、DOI 和页码。PDF 为 `build/cca-gpu-followup-20261027/tnpu-author-batch31.pdf`，336,563 字节，SHA256：`0a005f607218dd347e8dfd2ac62ecc194bf625acde3e45330f167776ce8e046c`。没有取得独立出版方文件作逐字版本比较，不把作者稿哈希冒充出版方文件哈希。

这是集成 CPU–NPU TEE 架构和安全内存论文，不是 Arm CCA GPU 共享实现。研究使用模拟硬件，本报告不因当前实验板能力而否定设计；同时区分论文设计、作者模拟、公开材料和本项目推断。

## 1. 研究问题与威胁模型

集成 NPU 与 CPU 共用片外 DRAM，不能依赖离散 GPU 独立显存来隔离敏感数据。即使 OS 无法直接读受保护页面，片外总线窃听、篡改和旧数据重放仍需要内存加密与完整性机制处理。

可信基包括 CPU/NPU 所在的 SoC 与 TEE 中运行的应用代码；OS 和 hypervisor 可以恶意，片外 DRAM 内容也可被物理攻击者修改。传感器数据生成与到 CPU TEE 的安全传输被假定已解决，不是本文实现和证明的完整端到端链路。

侧信道、模型结构的地址轨迹泄漏、算法层的模型反演/投毒/对抗样本，以及可用性不在保护范围。OS 仍控制 CPU/NPU 调度，因此可信计算支持不等于有限时间完成，也不保证公平共享。

正文以传感器校验和、hash 等背景资料说明数据采集，但后续实际依赖的是受保护、可认证的输入传输假设。无密钥 MD5/SHA 校验不能独立认证恶意攻击者修改的数据，本报告不把背景举例当成已实现的可信输入协议。

## 2. 为什么需要两类内存保护

传统安全内存为每个 64B 块维护 counter，配合 counter-mode encryption、逐块 MAC 和 counter tree。counter 不仅参与加密，也表达当前数据版本；根保留在片上，验证树防止攻击者同时回放数据、MAC 与旧 counter。

NPU 的 tensor 流式访问导致 counter cache 时间局部性不足，即使 miss rate 不大，每次 miss 的递归树验证也可能昂贵。论文的初始评估中，传统保护相对无保护 NPU 平均增加 21.1%/17.3% 执行时间，分别对应 Small/Large 配置。

TNPU 保留 128MB CPU fully protected region，用传统加密和完整性树保护 enclave 代码、EEPCM、版本表等安全元数据；NPU 大数据放在另一个区域，使用 AES-XTS 和携带软件版本的逐块 MAC。这里的 tree-less 只针对 tensor 数据区域，不是系统完全没有树或可信根。

MAC 存储在另一个保留区域，MAC 自身可以放在不可信内存中，因为读取方要用可信当前版本重新计算并比较。攻击者替换 MAC 可造成验证失败；它不应因此能够把旧版本变成当前版本。

## 3. 驱动 enclave、NPU context 与实际页归属

NPU driver 运行在 CPU driver enclave，OS 通过请求驱动控制设备；用户 CPU enclave 获得一个 NPU context 后，共享其 non-EPC tensor 内存并发出 mvin、mvout、compute 等操作。driver enclave 的安全、设备控制权限与用户 enclave 的版本管理都在可信链内。

论文明确需要扩展当时 SGX 的 MMIO 支持，不能将它说成无需硬件/接口变化的现成 SGX 方案。集成 SoC 与 CPU TEE 为安全控制提供基础，远程证明还需覆盖 driver enclave。

EEPCM（Extended Enclave Page Cache Map）是按实际物理页索引的反向表，包含 owner enclave ID、虚拟页、权限等元数据，存放在 fully protected region。OS 可以修改普通页表，但 CPU MMU 与 NPU IOMMU 在 TLB miss 时必须用 EEPCM 校验翻译与访问权限。

NPU context 初始化时设定受保护虚拟区 NELRANGE，添加物理页时同步记录归属。目标不变量是 TLB 只能包含已验证的翻译，而不是“页表由 OS 提供，因此天然可信”。其思想与 ACAI 的身份/映射归属原则及本项目最终实际页授权检查相通。

不过，本文没有给出完整的并发撤销、TLB/设备缓存失效、context ID 复用、在途访问排空协议。只有 miss 时检查，仍需保证既有缓存翻译不会在授权变化后继续有效；这是迁移和实现时要补齐的条件，不是本轮确认的可利用漏洞。

## 4. 软件版本如何提供重放保护

CPU enclave 为 tensor 或 tile 保存当前版本。mvout 前更新该版本，并把新值传给 NPU MAC generator；mvin 则传入可信表中的预期版本。每个 64B 块的 MAC 覆盖内容、块地址和版本，输出标签为 8B。

同一 tensor/tile 内的多个块可共用一个版本，因为地址仍参与 MAC，交换不同地址的块不能仅靠共用版本通过校验。预期版本来自 fully protected region，不能由不可信 Host 随意选择“能让旧数据通过的版本”。

该机制成立的关键不是版本字段存在，而是可信软件正确描述哪些块构成更新单位、何时更新、哪些版本可读取。若只写了一部分数据却把整个 tensor 版本推进，未更新块如何读取就需要另一种规则；论文通过明确的 tile 数据流处理这种细粒度问题。

论文示例将 A×B=C 分解为 tile 计算，分别维护输出 tile 的版本；在该示例中，各 tile 最终经历相同数量的更新，版本相等后可 merge 回一个 tensor 版本。expand/merge 不能无条件推广到更新次数不同、稀疏写入、并发原子操作或任意 GPU kernel。

版本表以 tensor ID/tile ID 索引；作者分析的平均空间为 1.3KB，最大约 7.5KB（Transformer）。幻灯片先给只考虑 tensor 的 0.14KB，再说明实际 tile 管理为 1.3KB，不能把前者当成完整方案开销。

## 5. CPU 与 NPU 共享数据的接口成本

NPU 通过 mvin 将 DRAM 数据搬入 SPM，通过 compute 运算，再以 mvout 写回；传入的版本随每次 DMA 操作用于逐块验证或生成 MAC。静态可分析的数据流是低开销管理的来源，编译器和库需要增加版本追踪代码。

CPU 初始化和取回 tensor 也必须遵循同样的加密与版本规则。论文新增 ts_read_block、ts_write_block、ts_read_byte、ts_write_byte 等指令，每核设置 64B read buffer 和 64B write buffer。

tensor 区域采用不可缓存访问，避免 CPU cache 不保存版本而绕开或混淆版本验证。新增指令、uncacheable 语义、缓存和 DMA 的一致性都属于架构代价，不能只统计 NPU 新增一个 version 参数。

图示验证失败会 Abort，但论文未给出覆盖部分 mvin、多个并发操作和外部副作用的完整发布状态机。本报告不据此断言“所有未验证数据都必然先执行”，也不声称已证明整个 job 的输出只有在全部相关检查成功后才能对外发布。

## 6. 加密、MAC 与跨生命周期边界

AES-XTS 的作用是片外内容机密性；重放防护依靠 MAC 中的可信版本，不是依靠 XTS tweak。XTS 不具备每次重写都产生新 nonce 的随机化语义，同地址的重复内容可能保持相同密文，因此不把作者“相同保护水平”的概述扩张为完全相同的可观察泄漏模型。

8B MAC 为 64-bit 标签，不因 AES 密钥较长就具有 128-bit 的盲伪造安全界。若底层 MAC 安全且其他条件满足，单次独立猜测的尺度约为 2^-64；部署还需考虑尝试次数、失败处理和所需安全预算，不能把它表述为无概率的绝对检测。

图 12 标出 4B 版本与地址字段；全文没有完整规定版本溢出、持久恢复、reset 后 key/版本重建或物理页回收后的域分离。不能从这张图推出已实现的任意大地址空间和无上限版本新鲜性。

MAC 的展示输入没有单独列出 enclave ID。稳定归属期间地址检查可以阻断越权访问，但如果同一 HPA 被重新分配，旧数据在同 key、同地址、同版本条件下可能重新满足相同认证表达式。是否通过每 context 密钥、初始化、代次绑定或其他方式排除，需要实现证据；本文没有给出可核对的完整协议，本报告只提出条件性生命周期义务。

页授权、当前版本权威、实际数据写入和业务完成应分别成立。更新可信版本表后发生中断、取消或 DMA 失败，可能需要显式失败终态或恢复策略；“版本表位于 enclave”并不自动解决这些事务顺序。

## 7. 初始化与证明的范围

每个安全 NPU 执行关联一个 CPU enclave，由其初始化 CPU EPC 与 NPU non-EPC 页面。正文称无须依赖安全的系统启动，是利用 CPU TEE 的动态 enclave 创建，不等于可以省略 CPU/SoC 根信任或任意恶意固件都不影响安全。

远程证明依赖 processor-wide CPU TEE 证明覆盖集成 NPU，再证明包含 NPU 指令的应用 enclave 与 driver enclave。它与离散设备的独立固件身份、链路认证和热插拔证明不同；论文没有构建 CCA Client/ProxyRealm 间的实例认证协议。

本文主要给出架构设计与安全机理解释，没有机器检查的形式化证明，也没有通过完整真实 CPU TEE/NPU 系统实现来验证全部授权、异常和恢复路径。不能把“使用 enclave attestation”写成作者已实测完成了所有这些步骤。

## 8. 作者实验与结果口径

作者使用基于 SCALE-Sim 扩展的内部 cycle-level simulator，增加跨层连接，采用简化带宽模型与 100-cycle DRAM latency。它不是实机 NPU、RTL 周期仿真或完整 CCA 软件栈的测量；Gemmini 用于交互模型，不能因此宣称安全扩展已进入其公开硬件。

Small 配置参考 Exynos 990：32×32 PE、480KB SPM、11GB/s、四通道、2.75GHz；Large 参考 Ethos N77：45×45 PE、1MB SPM、22GB/s、四通道、1GHz；均为 Float16。参考商业参数的模拟配置不能直接当成对这些商业芯片进行的安全测试。

传统基准使用 64-arity SC-64、4KB counter cache、4KB hash cache、8KB MAC cache；TNPU 也有 8KB MAC cache，并保留 128MB 元数据保护区。基准 CTR 的 OTP 为 10-cycle 加 1-cycle XOR，TNPU XTS 模拟为 13 cycles；版本表访问成本另建模。

14 个模型覆盖视觉、语音、文本、推荐等，数据 footprint 为约 2.2–75.6MB。Transformer 是当时的具体 benchmark，不能当成现代长上下文 LLM、动态 KV cache 或训练任务已验证；正文没有给出对任意动态 GPU 数据流的性能保证。

单 NPU：作者称相对传统保护，Small/Large 平均改善 10.0%/7.5%；相对无保护，传统为 21.1%/17.3% 执行时间开销，TNPU 为 9.0%/8.6%。这些是不同分母；按已四舍五入 Small 均值重算，时间减少约 9.99%，吞吐倍率约 1.111，不能将“10%”再说成同时是精确 speedup 和精确时间减少。

Small 的额外内存流量从无保护之上的 23.3% 降到 12.3%；每 64B 数据的 8B 标签本身为 12.5% 容量比例，MAC cache、读写与访问模式会改变实际流量，不能把两者机械等同。减少 counter tree 流量没有消除 MAC 流量。

多 NPU 实验让 1–3 个 NPU 各运行同一个模型，共享 memory controller/security engine/metadata caches，各有 IOMMU。三 NPU 相对相同三 NPU 无保护基准归一化，作者给出 Small/Large 相对传统保护改善 13.3%/8.7%；这不是单 NPU 变三 NPU 的绝对扩展倍率，也不是恶意多租户隔离实验。

CPU–NPU 端到端模拟从传感器传输完成计到输出返回 CPU，单请求包含模型参数初始化，不包含此前传感器安全采集等全流程。基准平均开销为 14.1%/12.6%，TNPU 为 6.4%/5.6%，正文另报告相对基准改善 8.2%/6.2%。Small 的几个均值不能直接重算出 8.2%；缺逐 workload 原始数据，保留原文与聚合口径限制，不擅自修成同一数字。

面积/功耗估计涉及三 AES engines、512B tweak/中间值存储及 8KB MAC cache；给出 0.03632mm²、相对 Exynos 990 约 0.035%、最高性能点 17.73mW，依据 CACTI 和引用 AES 组件。它不是作者完成整个 CPU/NPU TEE 综合、流片和功耗实测；EEPCM、指令、全部可信软件等不能由此判定为零成本。

## 9. 公开实现与复现限制

作者出版条目链接论文和幻灯片，没有对应 source/artifact 链接。本轮查询 GitHub TNPU，38 项结果未确认匹配本文；精确 Tunable Memory Protection 搜索为零，casys-kaist 公开组织列表取得 60 项且无下一页链接，未确认匹配两篇安全扩展的实现。

同组织 mNPUsim 是 IISWC 2023 的另一项多核 NPU 模拟研究，不能用它替代 TNPU 的安全版本管理、EEPCM、MAC 或本文评估提交。通用 SCALE-Sim/Gemmini 也不当成已取得 TNPU artifact。

本轮没有取得可确认匹配的源码，因而没有固定 TNPU 安全实现提交、审计代码或复现图表。没有运行任何下载研究 artifact、编译器、模拟器、硬件或攻击；图表只使用作者明文数字与清楚标明的算术复核，不从图形目测补造精确原始数据。

## 10. 与已有研究及本项目的关系

相对 HIX，TNPU 将 CPU enclave 驱动思路用于集成 NPU，并增加覆盖共享 DRAM 的反向授权；相对 Graviton，设备控制边界与 CPU/NPU 共享内存布局不同。GuardNN、MGX 同样利用可信软件与数据流降低版本管理成本，但加密方式、版本权威和标签粒度不同，不能互相替代安全证明。

与 PORTAL/CAGE/ACAI 的直接联系是“设备控制由谁负责、当前请求归谁、最终页是否授权”；与 PhantomMap 的联系是不能仅凭逻辑页或对象名就信任实际 HPA。TNPU 还补充了“权限正确不代表内容为当前版本”的第二层目标。

本项目保持 RMM 认证原始 Client、可信 ProxyRealm 统一控制 SMMU、建图检查对象/实际页/权限/生命周期并软件 IPA→HPA 合成为受保护 GPU Stage-1，其他设备保留硬件 Stage-2。TNPU 不要求推翻这套设计，也不意味着本项目一定需要增加内存加密硬件。

对已有 GPUVM、认证队列、私有快照，可明确“授权对象的当前实例与检查时固定的输入内容”是什么。仅在确有跨提交复用且内容新鲜性属于目标时，再考虑可信软件如何管理版本；GPU 任意写入不能直接共用 tensor 版本，不能为了引用 TNPU 新增无使用者的版本框架。

对已有 native fence、cookie/epoch、persistent IRQ127，应继续关联原始 Client、实际 context、当前任务及真实终态。tensor VN 是内容新鲜性，cookie/epoch 是协议身份/代次，两者不等价；收到可信 fence 不必然意味着全部数据校验成功或旧访问已静止。

值得形成的组合规范是：授权与固定输入先于执行；当前任务所需数据检查成功与输出可见先于可信发布；失败/取消有明确终态；撤销、排空和清理先于 HPA/槽位重新授权。TNPU 对其中内存版本部分提供启发，不负责证明完整跨 Realm 通知链。

统一记录：15 页论文/60 条参考文献、22 页作者幻灯片及书目/公开 artifact 线索研读，独立本地文档与 Notion 全文回读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件、模拟器、攻击 run-id 或新增性能 PASS｜论文保留，匹配实现缺失与迁移条件保留。
