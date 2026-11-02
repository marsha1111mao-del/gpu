# Hoss：GPU 私有内存、访问模式隐藏与共享租户边界

研读日期：2026-10-28。完整阅读16页arXiv v1、§1–9、148条参考文献及附录A/B/C，9图3表1算法、4条定理；视觉阅读第1/2/5/6/7/8/9/10/11/16页，覆盖全部图表。结合官方HTML、完整论文TeX源包定向核查定义、证明和实验。匿名artifact返回410 repository_expired，未获得运行源码，未执行作者代码或GPU实验。未改运行代码，无新增性能测量。

## 1. 来源和版本

Hoss: Fast Oblivious Semantic Search with Heterogeneous GPU-CPU-TEE Architecture，Jianzhang Du、Weijie Huang、Chenghong Wang、Nicolas Tsagareli、Yukui Luo、XiaoFeng Wang、Zhongshu Gu，Indiana University、Binghamton University、Nanyang Technological University及IBM Research；前两位共同贡献。[arXiv:2609.04522v1](https://arxiv.org/abs/2609.04522v1)，2026-09-03；[PDF](https://arxiv.org/pdf/2609.04522v1)、[HTML](https://arxiv.org/html/2609.04522v1)。

页眉印CCS’26，但HTML和TeX仍保留DOI XXXXXXX.XXXXXXX、会议rights confirmation占位及2018模板信息；限定Crossref标题前三项也未命中正式条目。本报告按已取得的预印本版本，不由页眉宣称正式录用或已核对会议最终版。

PDF1574866字节、SHA256 `c47b683303100328180520bf89c6f3285cf4b8d9b1fb30968a86371c1af80705`；HTML444284字节、SHA256 `48500d5c80e5436a3567a43d580862b39fc0c8e5ca078d08e48d9a0ab19b8fa7`；完整论文源包784488字节、SHA256 `54d03b09402aa28eb491daac5fc9adb7a23e8a474412982c7e46ba4d8dd20ac4`，27项，含TeX/图等出版资源，不是CUDA实现。证据位于`build/cca-gpu-followup-20261027/`的hoss相关文件。

pypdf提取出现“Exceeded 5000 form XObject invocations”警告，不能视为全部嵌套图形文字成功提取；另以PDFium提取全文并渲染10页读图，关键数学式/图例/表格再核对HTML和TeX。解析警告保留，不把PDF可打开当图表均已正确解析。

## 2. 项目相关性：保护对象和保护访问模式不同

Hoss在CPU/GPU TEE间实现HNSW语义检索，目标不仅是embedding/query内容保密，还要隐藏查询访问哪些节点。它属于建立在GPU TEE之上的应用/ORAM系统，未提出Arm CCA设备分配或多Client GPU隔离架构。

对本项目最重要的提醒是：实际HPA授权、页表保护和GPU任务隔离不自动隐藏访问模式；反过来，ORAM隐藏地址也不建立正确的Client归属或可信完成语义。两类安全目标可以分别定义，再按应用需要组合，不能因已有内存隔离就笼统认为“内存安全已无可研究”。

仍接受项目既定假设：RMM认证原始Client，ProxyRealm控制SMMU；GPU在映射建立时完成IPA→HPA的软件翻译、归属/权限/生命周期授权，合成受保护Stage-1；其他设备保留硬件Stage-2；平台保护实际页表、根配置、关键MMIO并可信加载固件。本文不以H100/Arm硬件差异否定该方案，而讨论其保护目标和共享条件。

## 3. 威胁模型：整卡独占是证明条件

数据owner上传预建HNSW索引，授权analyst查询；Host软件、管理员和同机租户不可信，可被动观察Host DRAM、DMA buffer和PCIe等封装外通路。CPU/GPU TEE及密码原语可信；封装内部探测、主动功耗/电磁攻击、可用性、covert channel和恶意用户输入排除。作者还信任云提供商组织层面的完整性，不能省略后将其描述为无条件对抗任意物理运营者。

GPU完整直通且仅运行Hoss一个程序，同卡共驻恶意程序攻击明确排除。作者据此把封装内HBM视为大容量Pmem，内部数据相关访问不在对手视野；这是一项架构/部署假设，不是“HBM或TEE天然消除所有侧信道”的实测定理。

本项目恰要支持多个互不信任Client共享GPU，因而不能直接继承该Pmem论证。即使HPA不重叠，cache/TLB/调度/故障和完成时序仍可能成为观察面。可以明确暂不保证访问模式隐藏，或另设计时分隔离、状态清理及可见元数据策略；不能只把Client统一放入可信Proxy就认定不存在恶意共驻代码。

## 4. 安全定义的泄漏边界

Definition3.1比较同一数据集上两条查询，要求每层逻辑遍历序列长度相等，此时对手View应不可区分。它不比较不同长度的查询，也没有完整给出包含时刻、批边界、返回量、系统fault与异常的可观察转录格式。

§7明确时间和volume隐藏是未来扩展：可对GPU阶段padding、避免跳过visited节点、固定探索步数。不能把这些建议算当前已实现或已测开销。请求开始/结束、层切换及结果数量仍需泄漏策略；只减少CPU kernel launch次数并不保证查询总时间不可见。

还有比“不同查询总长度泄漏”更细的待证明点：每层总逻辑访问数相等，不保证每次邻居展开的batch形状相等，而CORAM恰按邻居展开合并物理页。若batch边界/每批页数可见，证明应将shape列为允许泄漏、固定/填充shape，或证明其分布与秘密无关。论文未完整覆盖这个转换。

## 5. 存储布局与持久kernel

作者按自顶向下首次出现的顺序重编号节点，使同一节点跨层保持相同ID、每层ID紧凑，地址可由base＋ID×record_size得到，免去指针追逐。GPU上图结构和embedding分开，跨层复用embedding；Host层将neighbor list和embedding合成记录，减少一次节点展开需要的ORAM I/O。

上层留GPU HBM，较大底层留CPU TEE内存。持久kernel在GPU保存query、visited、候选/结果数组和ORAM状态，经init_query、upper_search、layer0_search、result_materialize四阶段处理，减少Host逐步编排。warp协作扫描/归约代替动态优先队列；结果只在最终阶段物化。

“CPU bypass”绕过逐步控制而不是绕过授权。Host仍投递输入、提供内存和接收结果，基线加密/完整性/重放防御与跨TEE安全通道由基础设施假设提供。查询入口、租户认证和输出发布不是因持久kernel自动安全，项目只能在既有可信提交/映射边界内吸收持久化和批处理思路。

## 6. CORAM四步和可信状态

位置表MAP、每bucket stash、entry cache及free-slot/reverse-index均留GPU Pmem；Host存定长含dummy的bucket。一次邻居展开先从MAP查目标物理bucket并去重，批量读；GPU从bucket/stash取记录、计算并移走旧记录；每个访问节点随机重映射后进新bucket的stash；仅将本轮读过的bucket合并对应stash并写回。

stash命中仍发Host页读，避免直接泄漏cache命中；stash将payload和元数据分开，lane0更新小型控制状态，其他lane协同拷贝/填dummy。安全依赖位置表、随机数、stash和回收槽持续可信且一致，不能只保护Host密文。

Algorithm1的M/K混用值得保留：Host块标为1..K，GPU stash和随机重映射却用1..M，而Theorem5.1把M定义为最大邻居数、K为Host块数；正文也有M个块却索引K的写法。可按语义理解应统一bucket数，但未获实现，不能替作者认定运行时没有索引问题。阶段说明引用line12:15，而印刷算法止于12，也不应当作额外隐藏步骤。

## 7. 合并访问的证明条件和一个数学检验

Theorem5.1先证明单次逻辑访问每次重新随机映射产生独立均匀bucket，再以同一邻居列表中节点互异论证可以batch和合并。这个局部推理有价值：它避免同一batch重复同节点却未即时remap造成的明显相关性；跨查询重复/并发则需额外协调，论文也明确未实现一般inter-query并发。

但“每层总长度相等”到“合并后分布相同”需要更强条件。作为协议分布的数学例子，两种batch shape为[2,2]和[1,3]，每层同为4次互异逻辑访问。若K个bucket独立均匀，每批去重后总读数期望分别为4−2/K和4−3/K＋1/K²；两者不同。即使不显式暴露batch标签，总物理读数也可能不同。这说明仅由总长度相等不能完成文中那一步普遍推导。

这不是已构造同一HNSW图上真实query攻击或已执行artifact；若实现总是固定邻居batch大小并安全padding，或定义允许泄漏shape，结论可能收窄成立。需要取得实现和精确View再判断。项目的批量化/中断合并也应采取同样审查：优化后的可见通知分布是否增加本来不允许的秘密依赖，不能只说“合并前每条都安全”。

## 8. Stash上界和失效概率

Theorem5.4假设下一逻辑访问在全部N条记录上均匀，推导stash期望平衡点x*=NK/(N＋K)和尾界。实际HNSW是数据/查询相关的非均匀遍历，位置随机不自动让“逻辑记录均匀选取”。因此不能把该定理直接当任意真实query、恶意输入或无限运行下的内存界。

最大桶负载及stash尾界均写失败概率1/N；这不自动是安全参数λ下的密码学negligible，也不是覆盖任意次数访问的全生命周期失败率。若按单时刻给界，长时运行需说明时间范围/联合界、相关性、overflow恢复及可观察失败。固定16槽如何匹配渐近容量、满槽时是否丢弃/扩容/重建均需代码证据，不能以几轮stress未overflow替代。

§6.1说16槽、K=N/16，同时每bucket仅8 real＋8 dummy；若N是全部real记录，实际需要K=N/8，前者只能容纳N/2条real。若N含dummy则应改定义，与定理/表1的数据点数一致。Theorem中的参数与实验初始化不一致是待澄清项，不据此断言真实实现漏掉一半数据。

## 9. 实验配置与收益分母

作者CUDA C++17约8.1K LoC、CUDA12.9/nvcc12.9.86，双EPYC9124共32核/64线程、256GB RAM、H100 PCIe CC模式直通SNP CVM。8.1K是应用规模，不涵盖CVM OS、driver、GPU firmware及证明栈总TCB。缺完整driver/固件、证明记录、固定源码和复现命令，不把作者配置陈述当本次安全部署认证。

Host存储用cudaMallocManaged并配置不在GPU HBM缓存，目标为压力较大的Host访问；具体driver支持、迁移/fault行为与基础安全通道如何接合还需实现，不能仅凭该API自动断言所有安全数据flow已覆盖。ChaCha20 RNG也需要实际seed、状态和重启域规则，算法名称不是完整协议。

| 数据集 | 节点数/维数 | 0.9 recall对Compass速度比 | Hoss/Compass各自non-private基线时间倍数 |
| --- | --- | --- | --- |
| LAION | 100K/512 | 63× | 5.4× / 148.9× |
| SIFT1M | 1M/128 | 60× | 15.6× / 357.1× |
| TripClick | 1.5M/768 | 99× | 5.0× / 184.6× |
| MSMarco | 8.8M/768 | 89× | 5.1× / 196.0× |

Fig4还比较Hoss0.95/0.98 recall与Compass0.9，最大58×/45×；这不是相同recall下新上限，不能把最高99×当保护开销只有1%。Fig5分别归一到各自CPU/GPU non-private算法，不能完全消除硬件、实现与基线选择影响；5.4×等是时间倍率，不是5.4%开销。

§6.1称两者同一机器，§6.2又称不同hardware，可理解为同一服务器上CPU/GPU执行设备不同，但文本未给完整消歧。本报告保留差异，不断言作者从未重跑Compass。BOLT则明确直接使用其原论文U55C FPGA结果，不同平台；最高101×是ORAM微基准，不是同硬件新算法独立提速，也不是GPU共享性能。

## 10. 合并收益与理论量级需对照

Theorem5.3给每批m次独立均匀访问的期望distinct数K[1−(1−1/K)^m]。按文中N=1M、K=N/16、m=64举例，约63.96775次，只省0.03225页、约0.05038%。这只是印刷参数代入，不是重新运行；若改K=N/8，随机碰撞更少。

Fig8却称coalesced对batch-no-coalesce最高1.8×、对sequential最高2.8×。不由此否定测量，但需要给实际batch大小、bucket数、粒度及时间分解，说明收益是否来自更大batch、实现控制开销/不同数据布局，而非单纯随机bucket碰撞消除。若使用跨邻居展开合并，必须重新证明重复节点和batch泄漏条件；不能为解释性能默默扩大算法范围。

Fig9 SIFT1M从仅L0到all offload，recall0.9为19.5→20.7ms，增加6.15%；0.98为47.8→49.1ms，增加2.72%。它说明特定负载的层拆分成本，不能替代租户切换、清理、取消或通知隔离开销；图7还残留HetCSS图例，按作者Hoss语义理解并保留命名差异。

## 11. 内存占比与TB投影

Fig6在10×data_size访问中记录最大stash分别11378/112434/171248/987528，约为real节点11.38%/11.24%/11.42%/11.22%，支持该测试窗口低于12%，不证明所有访问分布下有界。是否随机stress而非真实query、seed和overflow次数需要原始轨迹。

Table2的GPU占比约5.3–5.6%，按表中position map＋max stash除以总量得到。表自称complete，但未单列上层图/embedding、entry cache、reverse-index/free pool、query上下文、队列及scratch等；无法确认它们都计入哪栏，不应将5.5%宣称完整应用HBM峰值或固定α。2×Host dummy空间也会改变“GPU占总存储比例”的分母。

Table3将40/80/141/288GB HBM外推到347GB/694GB/1.22TB/2.50TB raw数据，作者明确Host RAM有限、没有实际TB压力实验。它还假设固定stash比例并耗尽全部HBM，未给runtime余量；A100的TEE模式与GH200 NVL2组合边界也须独立验证，列出容量不证明对应可信平台已部署。本文不以硬件能力否定抽象设计，但不能把容量算术等同实际安全实验。

## 12. Artifact、版本和后续引用

附录A明确提供[匿名artifact](https://anonymous.4open.science/r/hetcss-7758/)。本次web入口HTTP200只是通用前端，files API HTTP410，内容为repository_expired。因此未获得固定commit、CUDA源码、配置或原始图表数据，不宣称代码审核/复现。论文TeX可确认打印定义、K=N/16及8 real、模板DOI和讨论内容，注释中的旧稿不能当最终已实现机制。

沿reference62发现BOLT: Bandwidth-Optimized Lightning-Fast Oblivious Map powered by Secure HBM Accelerators，[arXiv:2509.01742v2](https://arxiv.org/abs/2509.01742v2)，作者摘要页自述Accepted by CCS2025、原型U55C FPGA。本轮只读摘要与书目信息，作为相邻可信加速器/访问模式研究候选，不计精读；不能把Hoss对BOLT的转述当BOLT原文结论。新取得TEE-certified DP的30页全文亦尚未精读，继续pending。

## 13. 对项目的设计建议

第一部分直通/共享实现：可借鉴受保护长期缓冲、紧凑对象索引、减少不必要指针追逐和批量提交。持久任务队列仍需原始Client/GPUVM/epoch/对象generation绑定，且计入排队、公平性、长kernel阻塞/取消和资源恢复；不能为去掉Host交互绕开Proxy授权。论文单程序intra-query并行不代表恶意多Client安全并发。

第二部分任务隔离：保留实际HPA授权、protected Stage-1和private plan/snapshot，进一步明确映射/任务/通知/回收生命周期。native fence是真实GPU终态依据，cookie/epoch约束迟到或重放，IRQ127/SGI仅唤醒；成功输出、应用正确性和DMA静默/安全复用分别论证。Hoss把跨TEE加密和重放作为假设，不能补足本项目尚需说明的中断归属。

访问模式隐藏可以列为第三层可选目标：先公布哪些元数据允许可见（Client活跃时间、提交数、队列/故障、长度、完成时刻），若目标应用是私有RAG再考虑ORAM、固定batch或有限padding。不要默认引入全局ORAM，也不要将“无越权读写”写成“所有侧信道均隔离”。同卡共享可能需要重新检验Pmem假设，即使内存页授权本身正确。

## 14. 独立评价和本轮范围

Hoss展示大容量不可观测Pmem怎样改变ORAM算法与GPU执行的取舍，属于GPU TEE应用保护的重要补充；其优势不来自打破相同模型下的ORAM下界，而是改变私有内存容量假设。最值得项目吸收的是清楚列出保护内容、可见转录与可信状态，避免将整卡独占结论迁移为多Client共享安全证明。

未解决项包括batch shape与安全定义、HNSW非均匀访问与stash上界、有限时窗失败概率、bucket参数/存储占比及微基准归因。这些是数学论证和证据范围上的具体问题，不是已完成真实攻击或宣称系统整体不安全。统一记录：完整16页/10页视觉/HTML/论文源包/概率与算术核查/Notion回读｜glmark未测→未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜匿名artifact410及PDF提取警告保留，相关设计待验证，研究继续。
