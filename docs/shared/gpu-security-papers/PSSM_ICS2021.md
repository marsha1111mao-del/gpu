# TGS-045｜PSSM：GPU 安全内存分区、计数器身份与 MAC 强度取舍

研读日期：<date start="2026-10-27" />。状态：13 页作者公开全文、正式元数据、作者出版条目与有界实现检索已核对。未取得确认匹配的 PSSM 实现，未运行模拟器。未改运行代码，无新增性能测量。

## 1. 文献与证据版本

**PSSM: Achieving Secure Memory for GPUs with Partitioned and Sectored Security Metadata**，Shougang Yuan、Yan Solihin、Huiyang Zhou，ICS 2021，139–151。DOI：[10.1145/3447818.3460374](https://doi.org/10.1145/3447818.3460374)。[作者出版列表](https://hzhou.wordpress.ncsu.edu/publications/)直接提供[全文 PDF](https://hzhou.wordpress.ncsu.edu/files/2022/12/ICS_21.pdf)。首页正式引用为 2021-06-14 至 17 的 virtual event。

本地全文 `build/cca-gpu-followup-20261027/pssm-author.pdf`，SHA256：`1d881e456e5fa5c25e9dd39ef20c64d133592bc055b206cf354e2989dda52744`。这是原库 **TGS-045** 的补全，不重复计作新增论文；同名生物信息学 PSSM/GPU 仓库与本工作无关。

## 2. 研究问题与保护层

把 CPU 的加密计数器、MAC 和完整性树直接搬到 GPU，会消耗本已紧张的显存带宽。GPU 的物理内存又分成多个 partition：同一物理页的各 cacheline 分散到不同 partition，但按物理页组织的 counter block 可能被各 partition 重复获取、存储和更新。

PSSM 用 partition-local address 组织元数据，配合独立完整性树和适合 sectored cache 的计数器布局。它是**GPU 芯片至外部 DRAM 的数据保护架构**，不是完整 GPU TEE，也不提出 Realm 共享设备、中断认证或逐 Client 页授权协议。

## 3. 威胁模型、可信基与假设

论文将 GPU 芯片作为可信物理边界，外部 device memory 不可信，覆盖 bus snooping 和内存篡改/重放。context 隔离、可信管理、密钥管理、远程证明和 PCIe 保护依赖 Graviton/HIX/SGX 等既有工作。侧信道不在范围内。

它明确与把设备内存纳入可信边界的设计比较，特别讨论离散 GDDR 的物理可接近性。这里比较的是威胁模型，不是要求所有 CCA GPU 项目都加入同样的物理攻击目标。对用户给定的平台保护假设，应继续接受其成立，再说明何种扩展威胁才需要外部内存认证。

## 4. 加密、完整性和新鲜度分工

Counter-mode encryption 用地址和计数器生成 OTP，每次写回推进 counter。stateful MAC 关联密文、地址和 counter；Bonsai Merkle Tree（BMT）保护 counter，片上 root 提供可信锚点。

因此密文与 MAC 一起重放不应通过旧 counter；搬到其他位置也应失败。仅有 MAC 而没有可信 freshness state，并不能普遍防重放。论文也说明 counter integrity 对 counter-mode confidentiality 重要，不能笼统宣称“去掉完整性仍抵御相同主动篡改攻击”。

## 5. 分区为什么会产生元数据一致性问题

基线 32 个 partition，每个具有本地 memory controller 和 metadata cache。一个物理地址组织的 128B counter block 可覆盖分散在多个 partition 的 128 个数据块。若复制 counter block，各副本需要协调 major-counter 更新；若只放一份，其他 partition 又要跨分区访问。

把交错粒度扩大到 4 页能让数据及 counter 聚在一起，但会引起 partition camping，且 BMT 高层仍可能跨 partition。论文的无安全保护对照中，单页/四页交错约损失 13%/29% 性能，说明不能为简化元数据忽略原先的带宽分布。

## 6. Partition-local address：局部名称不能丢失真实身份

物理地址经映射得到 `(partition_id, local_address)`，论文要求此变换为双射。元数据和 BMT 按 local address 组织，每个 partition 有自己的片上 root，避免冗余及跨分区 metadata coherence。

**密码 seed 并没有只使用 local address。** 不同 partition 的 local address 可重复，所以 PSSM 加入 partition ID、sector ID 和 counter，避免空间 pad reuse；MAC 也关联位置。省略这些字段会把局部编号误当成全局唯一身份。

这与本项目 Client-local handle 的关系很直接：可用局部编号优化查表，但可信解析必须恢复 Client/session/object generation 和实际 HPA 的完整关系。不是让 Client 提交一个自述的全局身份，而是由 RMM/Proxy 的可信状态确定其命名空间。

## 7. Sectored split-counter 的布局

常规 128B counter block 含一个 128-bit major counter 和 128 个 7-bit minor counter。拆成 4 个 32B sector 后，major 只在首 sector；访问其他 minor 仍需额外取首 sector。

PSSM 的 SC_32 改为每个 32B sector 各含 32-bit major 和 32 个 7-bit minor。minor overflow 重加密范围由 128 个数据块降到 32 个；这也是设计成本的变化，不能只看到 counter cache 命中率。

作者根据正常 workload 写回较少，认为 major overflow 不构成问题。这是经验动机，**不是恶意高写入、多租户长期运行或持久设备状态下不溢出的证明**。若引入本项目，仍需由可信策略规定上界、rekey 和溢出时拒绝/重加密，不能静默复用 seed。

## 8. Sectored metadata 不等于每次只读一个 sector

BMT 的 hash 仍覆盖完整 counter block/node；验证某一 sector 时，需要其他 sector 来计算完整 hash。因此 counter/BMT cache 在验证读入上可能仍像非 sectored cache；其节省主要来自脏 sector 写回。

MAC cache 则可更直接利用 sector 粒度。只有在不需要 BMT 验证的放宽模式，counter sector 才可正常按单 sector 读写。论文名称中的 sectored 不能推导全部元数据读流量都缩为四分之一。

## 9. MAC 粒度、缓存行为与标签长度

每 32B sector 一个 MAC 可以独立验证，但相同容量要保存更多 MAC；每 128B line 一个 MAC 减少 MAC 带宽，却需要整行数据才能验证。PSSM 评估两种方式，后者的 L2 虽仍采用 sectored 结构，在数据取入行为上类似 non-sectored。

论文还检查 MSHR 合并容量：以整行代替 sector 后，若仍只合并 4 个请求，会引起额外 stall，调整到 16 或更多后多数 workload 差距缩小。不能把所有性能变化都归因于密码算法，缓存资源条件也重要。

## 10. 32-bit MAC 的安全条件不能省略

论文评估把 MAC 从 8B 缩为 4B，并以单次猜中概率约 `2^-32`、短 kernel、每次 kernel 新 session key、验证失败即 reboot 等说明可接受。它还用较慢的 RowHammer 改位作为攻击成本例子。

这些条件不能替代完整攻击预算：攻击者若能直接篡改 off-chip memory，不必遵循 RowHammer 的改位速度；重复尝试的总成功概率随次数增加。换 key 会改变每次试验对象，但不自动消除多次独立试验的累计风险。约 `q/2^32` 只能作为理想标签下、相应独立/受限尝试假设中的估算，不是本文给出的完整密码安全证明。

“验证失败即 reboot”有助限制同一运行内继续试探，但还需要可信失败响应、同批多处修改的处理，以及不能继续使用失败数据的规则。论文未完整展开这类状态机。本项目不应为复现性能数字直接缩短认证强度，特别是持续运行、可重连多 Client 和复位恢复条件不同。

每 kernel 更换 session key 是作者安全论证中的前提；跨 kernel 常驻 buffer、共享 LLM 权重或 persistent job 如何保持密钥和数据一致，需要另行说明，不能把当前文中的前提当成已解决的通用持久数据协议。

## 11. 原型与评估配置

GPGPU-Sim v4.0，Volta 风格 GPU：80 SM、1132MHz、L2 6MB、32 个 DRAM partition、868GB/s，保护 4GB 显存。每 partition 的 counter/MAC/BMT cache 各 2KB，总计 192KB，128B line、四 sector；每 partition 一个流水 AES，hash/MAC 延迟 40 cycles。

16 个 benchmark 来自 Rodinia、Parboil、Polybench，每项模拟 400 万周期，按带宽使用率分类；不是全部 kernel 的完整执行时间、真实 V100 测量、并发多租户或实际篡改故障注入。图中指标是相对无安全保护 GPU 的 normalized IPC。

## 12. 结果：最优数字对应哪些取舍

| 完整性配置 | 作者报告平均性能开销 | 需要保留的条件 |
| --- | --- | --- |
| secureMem | 59.22% | Table 4 列物理地址元数据、sectored L2、每 sector 2B MAC |
| PSSM，每 sector 8B MAC | 42.03% | 本地元数据、较大标签，但每次验证元数据流量高 |
| PSSM，每 sector 4B MAC | 31.09% | 同时缩短标签 |
| PSSM，每 line 8B MAC | 19.06% | 整行数据验证行为 |
| PSSM，每 line 4B MAC | 16.84% | 常引用的最好结果，包含 32-bit 标签与整行验证 |

不能把 59.22%→16.84% 表述为“在所有缓存条件和认证强度完全相同下单项优化”。其差为 42.38 个百分点；这里保留作者性能开销术语，不把 IPC 下降未经换算写成整任务时间下降。

动机 §3.1 报告基线平均 slowdown 为 59.66%，后文及摘要为 59.22%；未取得实现配置和原始数据前保留差异，不擅自统一。Table 4 的基线 2B/sector 标签也与正文一般讨论的 8B 标签不同，应按各处具体配置引用。

**仅加密**的放宽目标下，作者报告开销 29.53%→5.18%，差 24.35 个百分点。它不包括完整数据 MAC/BMT 保护，不能拿 5.18% 证明对主动篡改/重放提供与完整配置相同保障。

## 13. 安全论证与公开实现边界

较强的机制论据是双射地址域、显式 pid/sector seed、独立可信 root，以及 counter/BMT 更新关系。主要未闭合的迁移条件包括缩短 MAC 的长期攻击预算、恶意工作负载下计数器寿命、per-kernel rekey 与持久对象、验证失败后的结果可见性和恢复。

作者出版条目提供原文；本轮以 PSSM+GPU 检索公开仓库，只得到题意无关的生物信息学结果，没有取得确认匹配的 PSSM artifact。GPGPU-Sim 上游不是本文修改版，不能冒充实现。本轮未固定论文源代码、未运行模拟器或重现性能，也不声称该论文从未公开代码。

## 14. 与已有工作的关系

| 工作 | 与 PSSM 的关系 | 对项目的比较意义 |
| --- | --- | --- |
| Analyzing Secure Memory Architecture for GPUs，ISPASS 2021 | 作者明确的前序性能研究 | metadata 带宽、cache、MSHR 和流水引擎需一起分析 |
| Common Counters，HPCA 2021 | 压缩相同 counter，作者认为互补 | counter 分组不等于租户授权域；原文相关工作局部引用编号存在错位，按正式题名核验 |
| SHM，HPCA 2022 | 进一步按访问类型/模式调整保护 | 保护模式切换需要清楚的前提和状态一致性 |
| 安全多 GPU 元数据，HPCA 2024 | 链路元数据与批量认证，层次不同 | 通信端点、内存位置、Client 身份不能混用 |
| PORTAL / ACAI / PhantomMap | 可信服务与实际页授权主线 | 显存加密不替代跨 Client 映射权限与安全撤销 |

以上不把相邻工作都算作同一完整 GPU TEE，也不声称所有论文有直接继承关系。

## 15. 本项目可吸收的设计原则

**局部编号保留完整身份**：Client-local BO/GPUVA 需由可信 Client/session/generation 命名空间解释；PSSM 保留 pid/sector 的方法提供类比，但不能以 partition ID 取代 Realm 身份。

**元数据组合有明确安全域**：若合并映射缓存、授权缓存或完成批次，只共享存储和访问成本，不因同页、相邻 HPA 或同 batch 就合并 Client 权限。授权缓存命中必须同时满足对象和映射生命周期，不能只比较地址。

**优化同时记录安全参数**：对每项性能实验列出授权检查、快照条件、真实 fence、结果提交、错误处理和回收屏障。论文最佳结果包含多项配置变化，本项目同样应明确组合归因，不能把牺牲验证条件当作实现优化。

**正常 workload 统计不能成为恶意输入上界**：检查 cookie/epoch、队列序号、引用计数及资源配额的溢出/耗尽行为；已有这些字段不意味着还需重复添加，应核验其生命周期和失败方式。

## 16. 对“两大部分”研究结构的定位

第一部分实现 Arm GPU 直通与共享，可借鉴本文对 bandwidth、metadata cache 和批量化成本的分析方法。第二部分任务隔离，重点仍是既定 ProxyRealm 下的 Client 授权、真实完成和撤销回收一致性。

在用户已假定平台保护实际页表、root/MMIO、固件及回收的条件下，PSSM 不要求重新设计一套 GPU MEE。只有明确纳入片外物理篡改等新威胁时，它才成为直接候选，而不是凭“内存加密更强”无限扩大可信计算项目范围。

## 17. 独立评价与研究记录

PSSM 的贡献具体：利用 GPU 分区和缓存组织减少元数据冗余。对本项目，最有价值的是完整身份不能随局部优化丢失、指标必须连同安全条件引用，以及长寿命和恶意输入下需要明确安全上界。

统一记录：原库 TGS-045 全文、元数据与有界实现检索｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜全文 SHA 与来源保存在本轮 build 证据目录，无模拟器复现、硬件 run-id 或新增硬件 PASS｜保留为原库独立完成，代码不可得和原文数字差异明确保留。
