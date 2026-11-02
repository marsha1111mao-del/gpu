# Tunable NPU（ICCD 2022）：按上下文保护、虚拟完整性树与可信片上通信

## 研读结论与书目

这篇短文与同组 TNPU 不同：它保留硬件 counter tree，通过只覆盖当前 NPU TEE 的虚拟区、选择较大 counter 粒度、只读页固定 counter，以及片上通信降低开销。对项目的启发是让优化依赖明确的授权域、访问单位与生命周期，而不是把“减少元数据访问”本身当成安全保证。

论文：Sunho Lee、Seonjin Na、Jungwoo Kim、Jongse Park、Jaehyuk Huh，Tunable Memory Protection for Secure Neural Processing Units，IEEE ICCD 2022，105–108 页，DOI：[10.1109/ICCD56317.2022.00025](https://doi.org/10.1109/ICCD56317.2022.00025)。[作者出版页](https://jaehyuk-huh.github.io/publications.html)将其列为 Short Paper；[完整作者 PDF](https://jaehyuk-huh.github.io/papers/lee_iccd22_tunable.pdf)。作者顺序与 TNPU 略不同，不能复制后一篇书目。

完整阅读 4 页全文、图表文字和全部 10 条参考文献，核对 Crossref 的题名、作者、DOI、页码。PDF 为 `build/cca-gpu-followup-20261027/tnpu-tunable-author-batch31.pdf`，234,545 字节，SHA256：`cc6792e5050abcf0a701e617f51251ec42ddd2b9625af42498e69ba995ad18c3`。未取得出版方独立文件作逐字版本比较。

它是相邻 NPU TEE 内存优化研究，不是 Arm CCA、GPU 多 Client 系统或可信中断协议；作为与 TNPU 不同机制的独立短文解读，不把它包装成另一套已实现的 CCA GPU 架构。

## 1. 威胁模型、可信基与基线差异

目标是 CPU/NPU 集成 SoC，共享片外内存。系统软件可被攻破，片外物理攻击可发生；SoC 和 NPU 可信上下文中的软件可信。侧信道、可用性与算法对抗攻击不在范围，论文没有声称解决恶意调度造成的饥饿。

架构沿用先前 NPU TEE 的控制基础，但本文明确采用隔离于 OS 的 protected page table，并保护页表根等元数据，只有 security monitor/MMU 能访问。TNPU 主文采用 OS 维护页表再由 EEPCM 校验；两者不能混写为完全相同的页表信任模型。

CPU 小型 protected region 保存 CPU TEE 及 NPU context 元数据；NPU 数据的物理页可分散分配。专用 counter base register 表示当前被调度 NPU TEE 的计数器区域，protected PTE 携带 read-only 与 granularity 属性。

可信驱动、monitor、页表/根和内存引擎共同决定权限及解密解释。论文是架构方案与模拟评估，没有给出这些组件的完整可审查部署实现，也没有实现级证明其全部更新路径原子一致。

## 2. 虚拟完整性树：减少覆盖范围

传统树按实际物理地址覆盖整个 DRAM。本设计为每个 NPU TEE 建立 virtual integrity tree，覆盖该 TEE 连续的受保护虚拟地址区；数据物理页可任意分散，counter 和内部节点则放在连续物理区域，起点 counter base 保存在受保护 context。

访问虚拟地址、受保护虚拟区起点与 counter base 共同确定 counter 位置，再定位父/子节点。物理页分散不要求整个真实数据区域物理连续，不能把 counter 区连续误写为数据页也必须连续。

按 VA 建树的前提是攻击者不能任意改写可信映射或把不一致别名作为合法解释。迁移时仍须说明每个实际 HPA 当前归属、合法别名/共享策略、VA/PA 改变时的 tree 和缓存同步；受保护页表减少攻击面，不自动免除实际页检查。

正文给出的 4GB、64B 块、64-arity 全树高度为 `1 + ceil(log64(4GB/64B)) = 6`；选择性保护的平均树高减少 40.9%。这依赖实际 context footprint 和树布局，不是任意 GPU 场景都减少同样百分比。

## 3. 多粒度 counter：安全条件比字段更重要

counter 单位可从 64B 改为 128/256/512B chunk，而底层传输仍是 64B。比如一个 512B chunk 的八个 64B 子块共用 counter，但不同块地址参与 OTP 生成，避免在同一 chunk 内对不同地址直接重复使用同一个 pad。

论文的关键约束是一个 chunk 始终整体搬运于 SPM 与外存之间。它不能直接推广为“任意八个独立可写 cacheline 永久共用 counter”；部分写入、同地址再次写入或并发写入仍必须保证同 key/地址下不会复用旧加密种子，并维护一致的版本解释。

每个模型的 chunk size 由初始化前 profiling 试出最佳值并交给可信驱动。虽然 PTE 中保留 granularity 位，本文实际让同一 NPU TEE 固定使用一个粒度；逐页动态粒度是未来扩展，不是已评估能力。

14 个模型的选择为：goo/mob 256B、yt 256B、alex 512B、rcnn/df/res 128B、med/tx/agz/ds2 512B、sent/tf 64B、ncf 256B。内存密集模型仍可能选择 64B，说明粗粒度不是无条件更快；预处理 profiling 成本没有作为每个在线请求的同一开销纳入。

## 4. 只读优化与初始化新鲜性

上下文初始化重置 counters，read-only 页使用固定初始值 1，后续读取可以跳过 counter cache；可信 PTE 的 read-only 属性决定是否适用。这种优化来自“该页在当前生命周期内不会被改写”，不是来自数据名称叫模型参数。

要成立，CPU、DMA、别名映射及其他设备都不能绕过只读限制；从只读变可写、换模型、迁移、复用物理页时应重新建立合适 counter/key 状态。仅固定值 1 不能认证该页属于哪个模型、哪个 Client 或哪次初始化。

正文没有规定完整的跨 context 密钥与 counter 复用协议。在同 key、同地址、相同初始 counter 下重新写入不同内容，会触及 CTR pad 复用条件；是否通过独立密钥或其他措施排除，需要额外证据。本报告只指出该条件，未取得实现或执行攻击，不声称已发现可利用漏洞。

## 5. 2KB 片上通信通道

设计新增 2KB SRAM channel buffer，CPU/NPU 在可信片上边界内传输数据，减少经外存通信的加密成本。只有 NPU driver TEE 控制 channel buffer，用户 TEE 创建关联 NPU TEE 时请求分配该通道。

作者以 workload 中 30% 层的 footprint 小于 2KB、访问具有流式特征说明容量选择。这不是说 2KB 能一次存放所有层数据，通道容量不等于模型总内存，也不自动等于多 Client 独立队列数。

正文称基线共享内存通信在两侧用软件加密，这与本文其他数据由硬件安全内存引擎保护的路径应分开。1.1% 通信收益不能任意解释为所有 CPU/NPU 数据都免除了相同加密成本。

可信片上位置能保护内容和部分访问路径，但论文未展开 sender/receiver 绑定、残留清理、槽位复用、完成原因与 ACK 协议。buffer 可访问权限、数据已消费、GPU 完成和旧 DMA 已停止是不同语义，不能从“channel buffer 属于可信驱动”一并推出。

## 6. 模拟方法与结果

使用内部 cycle-accurate simulator，扩展 SCALE-Sim，模拟 CTR 和 64-arity Bonsai Merkle tree。NPU 配置为 1GHz、16×16 systolic array、192KB SPM、8-channel 5GB/s 带宽，以及 512B counter cache、2KB hash cache；它与 TNPU 的 Small/Large 两套配置不同，数值不能跨论文直接相减归因。

14 个模型来自 MLPerf/DeepBench 覆盖的应用域，作者给出各模型粒度。没有真实 NVDLA/CPU TEE 全系统执行、GPU workload、LLM KV cache 或恶意多 Client 的实测；“参考 NVDLA”不是已经在 NVDLA 验证安全扩展。

相对无安全保护，基线执行时间开销为 21.5%，四项组合后为 5.1%。按正文均值算，安全开销降低 16.4 个百分点；相对安全基线的时间减少约 `(1.215−1.051)/1.215 = 13.50%`，对应固定工作量倍率约 1.156。摘要的 13.5% 不应再称为精确的 1.135× speedup。

作者按串行加入的方案报告 virtual tree 8.9%、granularity 3.5%、read-only 0.5%、communication 1.1% 的执行时间减少。它们是特定顺序和配置下的增量，不能直接相加成总体百分比，也不是每项都相对同一个原始基线的独立收益。

组合后 counter cache miss 减少 67.4%，virtual tree 的 hash cache miss 减少 27.4%。动机实验中的 512B 粒度使 miss 剩余 21.8%，属于不同配置比较，不能与组合方案的 67.4% 当成同一个指标矛盾或同一项收益。

多 NPU 实验增加到 1–3 个，counter cache 均分给各 NPU；它与 TNPU 主文共享同一 counter/hash cache 的配置不同。每个 NPU 数量使用自己的安全基线归一化，不能据图推出三 NPU 总吞吐的绝对倍率；作者以 metadata 压力下降和 memory controller 竞争平衡解释相近收益。

本文没有完整面积、功耗、TCB 大小和 profiling/创建/销毁成本评估；新增 2KB SRAM、寄存器和 PTE 位不等于整体开销已经穷尽。四项同时改变时，只对论文组合效果作结论，不用它推算项目 glmark 或 GPU 共享性能。

## 7. 公开代码、证据范围与局限

作者条目仅链接论文与幻灯片，本轮 GitHub 精确题名短语查询无结果；casys-kaist 公开组织列表 60 项，无下一页链接，未确认匹配本文安全扩展的仓库。未取得对应 artifact 或固定评估提交，因此没有源码路径审计或图表复现声明。

TNPU 名称查询的 38 项结果也没有确认匹配；同组织 mNPUsim 为另一项 IISWC 2023 研究，通用 SCALE-Sim/Gemmini 不代替本文 virtual tree、counter 管理和可信通道实现。搜索范围有限，“未确认匹配”不是断言不存在任何作者私有或其他公开实现。

没有形式化安全证明、完整撤销协议或异常路径实验。尤其是 counter base/root/context 更新、受保护 PTE 与缓存一致性、未完成写回、共享 counter 的完整更新、只读转权及 channel buffer 复用，需要后续实现说明；不把这些缺口直接说成已确认漏洞。

本轮仅阅读论文与书目/仓库线索，没有执行模拟器、构建、下载研究 artifact、硬件或攻击，也没有增加验证实现行为的测试。论文提供的性能数据属于作者模拟结果。

## 8. 对项目的可迁移设计

保持本项目 RMM 认证原始 Client、可信 ProxyRealm 统一控制 SMMU、建图验证对象/实际页/权限/生命周期并软件 IPA→HPA 合成受保护 GPU Stage-1，其他设备保留硬件 Stage-2；实际页表、根配置和关键 MMIO 受平台保护。这些是假设与架构基础，不因本文使用不同 CPU TEE 被否定。

可借鉴的是优化的条件：映射或检查结果复用，应绑定当前对象实例、实际页集合和权限；只读快速路径要由全访问路径的只读不变量支撑；批处理应定义一个完整授权/更新单位，不能因数据相邻就视为同一 Client 或同一生命周期。

不必给项目直接加入 virtual integrity tree、XTS 或 SRAM 通道。项目已有 GPUVM、认证队列、私有快照及共享通信机制，应先说明已有路径的安全条件；只有实际威胁模型需要片外密码保护或语义版本时，才评估额外机制。

对 native fence、cookie/epoch、persistent IRQ127，重点仍是 context/请求/目标身份一致，结果和错误终态真实，完成发布与输出可见有序，以及撤销后停止旧访问再复用。本文可信通道的概念不证明通知原因或任务完成，也不消除共享 GPU 的时序泄漏。

与 TNPU 对照后，项目可形成一个设计选择论证：通用 GPU 的任意动态访问更适合以对象、实际页与可信生命周期约束为基础；若某类计算有可证明的只读或整体更新语义，再采用有范围的优化。不要把 DNN 的静态数据流前提扩大为所有 GPU 应用的默认事实。

统一记录：4 页短文/全部 10 条参考文献、正式书目与公开 artifact 线索研读，独立本地文档与 Notion 全文回读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件、模拟器、攻击 run-id 或新增性能 PASS｜论文保留，缺少匹配实现及动态生命周期证据。
