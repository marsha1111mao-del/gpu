# GPU 机密计算与安全文献库：核验、去重与资料入口（2026-10-26）

本次逐项处理用户提供的 **5 个综述/索引项及 45 个编号条目，共 50 处列举**。合并 5 组重复后对应 **45 条独立记录**；补充相关论文、官方规范、代码和测试资料后，共 **89 条资料记录**。这里的“资料”包括论文、草稿、演讲、规范、文献索引和工具，不是“89 篇 GPU TEE 论文”。

**未改运行代码，无新增性能测量。** 本文是书目与资料核验，不是逐篇技术精读、安全审计或实验复现。当前实现和冻结版本仍以 [CURRENT_BASELINE](CURRENT_BASELINE.md) 为入口。沿用用户已确定的设计假设：平台保护可信页表、根配置与关键 MMIO；可信 ProxyRealm 管理设备与授权；GPU 的授权与软件地址合成发生在映射建立阶段，执行期受硬件 Stage-1 约束。RK3588 是模拟与测试载体，本次不重新讨论这些假设的硬件可得性。

机器可读版本：[catalog.json](evidence/gpu-literature-20261026/catalog.json)。公开来源、题名候选、下载状态和内容 SHA-256：[source-index.json](evidence/gpu-literature-20261026/source-index.json)。原始网页/PDF/元数据保存在控制机 `build/gpu-security-literature-20261026/`；既有精读材料按来源索引复用。没有把第三方论文全文复制到版本化文档目录。

## 核验方式与阅读深度

优先采用会议/出版方记录、作者 PDF/项目页、官方厂商文档、作者仓库 README；Crossref 用于核对出版方登记的题名、DOI、会议/期刊与日期，OpenAlex 与第三方清单用于发现和交叉核对。搜索结果候选不会自动进入文献主记录。

“出版方元数据”表示核对了书目，不表示读过全文；“既有原文”表示复用了前轮实际取得的论文；“官方入口”可能只是规范首页。正文、摘要、README、规范壳页、HTTP 200 反爬页和访问失败分别记录。公开仓库存在、目录含测试和论文声称形式化验证，也不等于本轮已运行 artifact 或核对证明。

本轮 Crossref 部分请求返回 429，部分网页/PDF超时；有已取得的一手材料时采用该材料，否则保留较低核验等级。Arm DEN0137 返回文档壳页，IGT/Piglit 返回 Anubis 反爬页，都没有记为规范/README正文已取得。

年份优先使用正式会议或期刊卷期年，同时记录预印本/在线年；DOI 字符串中的年份不是卷期年证据。厂商 `latest` 页面按本次检索日归档，后续引用应进一步固定产品、驱动、固件、文档版本和运行模式。

## 原清单中需要纠正或补齐的条目

| 条目 | 核验结果 | 文献库处理 |
| --- | --- | --- |
| HIX、HETEE、MOLE、Telekine、CPU–GPU 综述 | 各被列举两次 | 分别合并为 B02、B04、A06、B03、S01；保留全部原编号映射 |
| Arm GPU 轻量 TEE 期刊论文 | DOI 含 2023，正式卷期为 2024 | A02 按 TDSC 2024 引用，避免只写“2023/2024” |
| Arm CCA 加速器环境期刊论文 | DOI 含 2025，正式卷期为 2026-01 | A07 补齐年份；与 CAGE 的具体扩展关系仍需正文确认 |
| GEVisor | 正式题名为 Building GPU TEEs using CPU Secure Enclaves with GEVisor | B06 替换题名并补作者直接链接的公开代码 |
| XpuTEE | ACM TOCS 2025，DOI 10.1145/3719653 | B10 用正式 DOI 替换 Connected Papers |
| Honeycomb | 正式封面为 Secure and Efficient GPU Executions via Static Validation | B08 保留此题名；SoK 引文中的另一题名不作为独立论文 |
| ccAI | 原文正式 DOI 为 10.1145/3725843.3756104；作者项目页下载按钮指向另一 DOI，本轮查询404 | B11 采用原文首页及 ACM Reference Format，并用出版方元数据交叉核对 |
| GPUReplay 与 GR-T | GPUReplay 是 ASPLOS 2022；GR-T 对应 Safe and Practical GPU Computation in TrustZone，EuroSys 2023 | B12/B13 分别记录；共享相关仓库不等于同一篇论文或相同 artifact 覆盖范围 |
| LAK、Whispering Pixels、GPUArmor | 分别为 ICCD 2022、EuroS&P 2024、TACO 2026；GPUArmor 预印本为2025 | D06/D05/D09 补齐正式出处和日期层次 |
| Vulnerable GPU Memory Management | arXiv 2016；正式 PoPETs 2017 | D02 保留两个版本入口，不把预印本年替代正式出版年 |
| AvaGPU / Secure and Timely GPU Execution | 正式出版为 CCS 2023，第三方列表的 ASPLOS 标签有误 | E02 以出版方元数据为准 |
| Lightning | 已确认原清单题名对应 arXiv:2112.03662；另有不同题名的 TODAES Lightning 工作 | D04 按已核实的预印本记录，不自动嫁接另一篇题名/正式出处 |
| Enclaves as accelerators | 取得副本，作者为 Meni Orenbach、Mark Silberstein；副本仍含模板 DOI 10.1145/1235 | B14 标记正式发表信息待核；模板 DOI 不进入 DOI 字段 |
| 两份 H100 技术资料 | Hopper 演讲封面确认 GTC March 2023；另一份开发者演讲只确认目录文件，正文重取超时 | V01/V02 归入历史演讲；不把题名拼接或猜测的博客 URL 当一手出处 |
| NVIDIA 工具与文档 | 本次 README 标明旧 Python SDK/Local GPU Verifier 已弃用，转向新 C++ SDK/CLI | V09/V10 同时保留迁移关系；旧 H100 资料和现行支持矩阵分别引用 |

## 完整资料目录

“直接”表示与本项目的可信代理、归属/映射、异步完成或隔离设计接近；“背景”不代表无价值。论文的 GPU 架构、攻击能力和防护范围仍应以各自正文为准，不将 x86 异常攻击、NVIDIA 机制或 kbase 漏洞直接套用到 Mali/Panthor/Realm。

### 综述与索引（5）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| S01 / 综述1、论文41 | Confidential Computing on Heterogeneous CPU-GPU Systems: Survey and Future Directions | 2026 / ACM Computing Surveys | [DOI](https://doi.org/10.1145/3793532) | **出版方元数据**。在线2026-02-25；卷期2026-07。已有本地Crossref原始记录。 |
| S02 / 综述2 | SoK: Analysis of Accelerator TEE Designs | 2026 / NDSS | [会议](https://www.ndss-symposium.org/ndss-paper/sok-analysis-of-accelerator-tee-designs/) · [原文](https://www.ndss-symposium.org/wp-content/uploads/2026-f1424-paper.pdf) · [项目](https://compass.sustech.edu.cn/sok-xputee/) | **会议/作者页面**。覆盖加速器TEE；不将其中全部非GPU工作纳入GPU主库。 关联：直接。 |
| S03 / 综述3 | GPU-TEE-Papers | 持续更新 / 第三方GitHub合集 | [仓库](https://github.com/ConfidentialComputing/GPU-TEE-Papers) | **仓库README/目录**。含重复项；目录中的“GPU A100 TEE”不是Graviton的论文平台或年代证明。 |
| S04 / 综述4 | GPU Security Papers | 持续更新 / 第三方GitHub合集 | [仓库](https://github.com/trilateral-gpu-sec/gpu-security-papers) | **仓库README**。可用于发现文献，会议/年份仍需逐项核对；例如其AvaGPU条目的会议标签与正式出版记录不一致。 |
| S05 / 综述5 | Survey of Research on Confidential Computing | 2024 / IET Communications | [DOI](https://doi.org/10.1049/cmu2.12759) | **出版方元数据**。广义机密计算综述。 |

### Arm GPU与CCA（7）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| A01 / 论文1 | StrongBox: A GPU TEE on Arm Endpoints | 2022 / ACM CCS | [原文](https://fengweiz.github.io/paper/strongbox-ccs22.pdf) · [项目](https://compass.sustech.edu.cn/strongbox/) · [代码](https://github.com/Compass-All/CCS22-StrongBox) | **既有原文/代码核验**。TrustZone、GPU可信控制；与A02按同一工作族追踪。 关联：直接。 |
| A02 / 论文2 | Building a Lightweight Trusted Execution Environment for Arm GPUs | 2024 / IEEE TDSC | [DOI](https://doi.org/10.1109/TDSC.2023.3334277) | **出版方元数据**。正式卷期2024；DOI中的2023不能单独作为卷期年份。第三方索引摘要将系统称为StrongBox。 关联：直接。 |
| A03 / 论文3 | CAGE: Complementing Arm CCA with GPU Extensions | 2024 / NDSS | [会议](https://www.ndss-symposium.org/ndss-paper/cage-complementing-arm-cca-with-gpu-extensions/) · [原文](https://www.ndss-symposium.org/wp-content/uploads/2024-763-paper.pdf) · [代码](https://github.com/Compass-All/NDSS24-CAGE) | **既有原文/代码核验**。功能原型、性能原型分别记录；A07为相关期刊条目，扩展关系待正文确认。 关联：直接。 |
| A04 / 论文4 | ACAI: Protecting Accelerator Execution with Arm Confidential Computing Architecture | 2024 / USENIX Security | [会议](https://www.usenix.org/conference/usenixsecurity24/presentation/sridhara) · [原文](https://www.usenix.org/system/files/usenixsecurity24-sridhara.pdf) · [代码](https://github.com/sectrs-acai/acai) | **既有原文/代码核验**。身份、设备绑定、映射归属一致性。 关联：直接。 |
| A05 / 论文5 | PORTAL: Fast and Secure Device Access with Arm CCA for Modern Arm Mobile System-on-Chips (SoCs) | 2025 / IEEE S&P | [DOI](https://doi.org/10.1109/SP61157.2025.00013) · [作者原文](https://mainarke.github.io/assets/papers/sp25_sang.pdf) | **出版方元数据/既有原文**。可信服务Realm、设备管理；本轮未确认独立完整公开实现。 关联：直接。 |
| A06 / 论文6、论文28 | MOLE: Breaking GPU TEE with GPU-Embedded MCU | 2025 / ACM CCS | [DOI](https://doi.org/10.1145/3719027.3744823) | **出版方元数据**。合并重复项；GPU内部MCU/固件攻击面。 关联：直接。 |
| A07 / 论文7 | Building Confidential Accelerator Computing Environment for Arm CCA | 2026 / IEEE TDSC | [DOI](https://doi.org/10.1109/TDSC.2025.3615787) | **出版方元数据**。正式卷期2026-01；DOI标识含2025。与CAGE的扩展关系需进一步由正文确认，不直接计作全新架构。 关联：直接。 |

### GPU TEE系统与运行时（14）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| B01 / 论文8 | Graviton: Trusted Execution Environments on GPUs | 2018 / OSDI | [会议](https://www.usenix.org/conference/osdi18/presentation/volos) | **既有原文**。用正式会议入口替换Connected Papers；本轮页面重取超时不推翻既有原文记录。 关联：直接。 |
| B02 / 论文9、论文38 | Heterogeneous Isolated Execution for Commodity GPUs | 2019 / ASPLOS | [DOI](https://doi.org/10.1145/3297858.3304021) | **出版方元数据**。系统简称HIX；合并重复项。 |
| B03 / 论文10、论文29 | Telekine: Secure Computing with Cloud GPUs | 2020 / NSDI | [会议](https://www.usenix.org/conference/nsdi20/presentation/hunt) · [原文](https://www.usenix.org/system/files/nsdi20-paper-hunt.pdf) | **正式入口/已有引用链**。同时具有系统与时序泄漏研究属性；本轮会议页重取超时，不标成已读全文。 |
| B04 / 论文11、论文39 | Enabling Rack-scale Confidential Computing using Heterogeneous Trusted Execution Environment | 2020 / IEEE S&P | [DOI](https://doi.org/10.1109/SP40000.2020.00054) | **出版方元数据**。系统简称HETEE；合并重复项。 |
| B05 / 论文12 | LITE: A Low-cost Practical Inter-operable GPU TEE | 2022 / ICS | [DOI](https://doi.org/10.1145/3524059.3532361) | **出版方元数据**。补齐会议ICS；Crossref短题名LITE，副题名另字段保存。 |
| B06 / 论文13 | Building GPU TEEs using CPU Secure Enclaves with GEVisor | 2023 / ACM SoCC | [DOI](https://doi.org/10.1145/3620678.3624659) · [作者页面](https://www.s3lab.io/paper/gevisor-socc23) · [代码](https://github.com/purseclab/GEVisor) | **作者页面/出版方元数据/README**。修正原清单的题名顺序；作者页面直接链接代码。 关联：直接。 |
| B07 / 论文14 | SAGE: Software-based Attestation for GPU Execution | 2023 / USENIX ATC | [会议](https://www.usenix.org/conference/atc23/presentation/ivanov) | **索引/正式入口**。用具体论文入口替换整个会议日程；本轮原文未取得。 |
| B08 / 论文15 | Honeycomb: Secure and Efficient GPU Executions via Static Validation | 2023 / OSDI | [会议](https://www.usenix.org/conference/osdi23/presentation/mai) · [代码](https://github.com/Jiacheng/honeycomb-osdi23-ae) | **既有原文/代码核验**。题名按正式PDF封面；SoK参考文献中的不同题名不是另一篇论文。 关联：直接。 |
| B09 / 论文16 | CRONUS: Fault-isolated, Secure and High-performance Heterogeneous Computing for Trusted Execution Environment | 2022 / MICRO | [作者原文](https://i.cs.hku.hk/~heming/papers/micro22-cronus.pdf) · [代码](https://github.com/hku-systems/cronus) | **既有原文/README**。异步协作、服务分域与故障隔离。 关联：直接。 |
| B10 / 论文17 | XpuTEE: A High-Performance and Practical Heterogeneous Trusted Execution Environment for GPUs | 2025 / ACM TOCS | [DOI](https://doi.org/10.1145/3719653) | **出版方元数据**。在线2025-04；卷期2025-05。替换Connected Papers入口。 |
| B11 / 论文18 | ccAI: A Compatible and Confidential System for AI Computing | 2025 / MICRO | [DOI](https://doi.org/10.1145/3725843.3756104) · [作者原文](https://compass.sustech.edu.cn/paper/ccai-micro25.pdf) · [项目](https://compass.sustech.edu.cn/ccai/) | **作者原文/索引**。项目页Download Link指向另一DOI且查询404；本记录使用论文首页与ACM引用格式给出的正式DOI。 关联：直接。 |
| B12 / 论文44 | GPUReplay: A 50-KB GPU Stack for Client ML | 2022 / ASPLOS | [DOI](https://doi.org/10.1145/3503222.3507754) · [预印本](https://arxiv.org/abs/2105.05085) · [代码](https://github.com/bakhi/GPUReplay) | **出版方元数据/作者列表/README**。原条目的“Secure GPU Execution / Replay-Based Protection”不是正式副题名；该文是重放基础系统。 |
| B13 / 论文45 | Safe and Practical GPU Computation in TrustZone | 2023 / EuroSys | [DOI](https://doi.org/10.1145/3552326.3567483) · [早期 CODY 稿件](https://arxiv.org/abs/2111.03065) · [相关代码](https://github.com/bakhi/GPUReplay) | **正式书目、作者列表；正式全文待取得**。系统简称GR-T；与B12为不同论文。2026-10-27续核：arXiv链接为2021年v1，题名为Safe and Practical GPU Acceleration in TrustZone、系统为CODY，不能不核对差异就代替EuroSys2023正式版。仓库README主要描述GPUReplay，未确认覆盖GR-T全部安全组件。关联：直接。 |
| B14 / 论文42 | Enclaves as accelerators: learning lessons from GPU computing for designing efficient runtimes for enclaves | 待核 / 草稿/发表信息待核 | [固定版本PDF副本](https://github.com/ConfidentialComputing/GPU-TEE-Papers/blob/8e367018ffbf209f62184423de9874c544d856c4/Enclaves%20as%20accelerators-%20learning%20lessons%20from%20GPU%20computing%20for%20designing%20efficient%20runtimes%20for%20enclaves.pdf) | **取得PDF，正式书目待核**。作者Meni Orenbach、Mark Silberstein；PDF保留模板DOI 10.1145/1235，不能录为正式DOI。其文内SGXIO原型名也不能与E01视为同一系统。 |

### GPU安全内存架构（8）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| C01 / 论文19 | Plutus: Bandwidth-Efficient Memory Security for GPUs | 2023 / HPCA | [DOI](https://doi.org/10.1109/HPCA56546.2023.10071100) | **索引/SoK交叉核对**。内存认证元数据与带宽；本轮未读取全文。 |
| C02 / 论文20 | Analyzing Secure Memory Architecture for GPUs | 2021 / ISPASS | [DOI](https://doi.org/10.1109/ISPASS51385.2021.00017) | **出版方元数据**。补齐年份与会议。 |
| C03 / 论文22 | Confidential Computing within an AI Accelerator | 2023 / USENIX ATC | [会议](https://www.usenix.org/conference/atc23/presentation/vaswani) · [作者机构](https://www.microsoft.com/en-us/research/publication/confidential-computing-within-an-ai-accelerator/) | **会议页面**。AI加速器背景；不将其直接标为Arm GPU或CUDA GPU系统。 |
| C04 / 论文25 | Adaptive Security Support for Heterogeneous Memory on GPUs | 2022 / HPCA | [DOI](https://doi.org/10.1109/HPCA53966.2022.00024) | **索引/SoK交叉核对**。按内存类型与模式优化保护；本轮未读取全文。 |
| C05 / 论文26 | Common Counters: Compressed Encryption Counters for Secure GPU Memory | 2021 / HPCA | [DOI](https://doi.org/10.1109/HPCA51647.2021.00011) | **索引/SoK交叉核对**。补齐年份与会议。 |
| C06 / 论文27 | PSSM: Achieving Secure Memory for GPUs with Partitioned and Sectored Security Metadata | 2021 / ICS | [DOI](https://doi.org/10.1145/3447818.3460374) | **出版方元数据**。Crossref主标题PSSM，完整副题名见记录与论文索引。 |
| C07 / 补充 | Salus: Efficient Security Support for CXL-Expanded GPU Memory | 2024 / HPCA | [DOI](https://doi.org/10.1109/HPCA57654.2024.00027) | **出版方元数据**。补充；与ASPLOS 2024同名CPU-FPGA TEE不是同一工作。 |
| C08 / 补充 | Supporting Secure Multi-GPU Computing with Dynamic and Batched Metadata Management | 2024 / HPCA | [DOI](https://doi.org/10.1109/HPCA57654.2024.00025) | **出版方元数据**。补充多GPU安全内存管理。 |

### GPU隔离、内存安全与攻击（13）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| D01 / 论文21 | Understanding the Security of Discrete GPUs | 2017 / GPGPU-10 | [DOI](https://doi.org/10.1145/3038228.3038233) | **出版方元数据/PDF**。正式会议2017；本地副本引用格式中的2016不作为会议年份。 |
| D02 / 论文30 | Vulnerable GPU Memory Management: Towards Recovering Raw Data from GPU | 2017 / PoPETs | [DOI](https://doi.org/10.1515/popets-2017-0016) · [预印本](https://arxiv.org/abs/1605.06610) | **出版方元数据**。预印本2016，正式期刊2017。 |
| D03 / 论文31 | Confidentiality Issues on a GPU in a Virtualized Environment | 2014 / Financial Cryptography and Data Security / LNCS | [DOI](https://doi.org/10.1007/978-3-662-45472-5_9) | **出版方元数据**。补齐会议系列与年份。 |
| D04 / 论文32 | Lightning: Striking the Secure Isolation on GPU Clouds with Transient Hardware Faults | 2021 / arXiv预印本 | [预印本](https://arxiv.org/abs/2112.03662) | **作者预印本页面**。暂不强配正式会议；与TODAES论文Lightning: Leveraging DVFS-induced Transient Fault Injection to Attack Deep Learning Accelerator of GPUs分开记录版本/题名。 |
| D05 / 论文33 | Whispering Pixels: Exploiting Uninitialized Register Accesses in Modern GPUs | 2024 / EuroS&P | [DOI](https://doi.org/10.1109/EuroSP60621.2024.00026) · [预印本](https://arxiv.org/abs/2401.08881) | **出版方元数据/预印本**。寄存器残留研究。 |
| D06 / 论文34 | LAK: A Low-Overhead Lock-and-Key Based Schema for GPU Memory Safety | 2022 / ICCD | [DOI](https://doi.org/10.1109/ICCD56317.2022.00108) | **出版方元数据**。GPU程序内存安全机制，非完整GPU TEE。 |
| D07 / 论文35 | Guardian: Safe GPU Sharing in Multi-Tenant Environments | 2024 / Middleware | [DOI](https://doi.org/10.1145/3652892.3700768) · [预印本](https://arxiv.org/abs/2401.09290) | **索引/既有原文**。与独立GPUVM隔离对照；本轮未确认完整作者仓库。 关联：直接。 |
| D08 / 论文36 | Behind Bars: A Side-Channel Attack on NVIDIA MIG Cache Partitioning Using Memory Barriers | 2026 / USENIX Security | [会议](https://www.usenix.org/conference/usenixsecurity26/presentation/gu-cheng) | **既有官方摘要核验**。本轮两次重取超时；沿用此前摘要核验，未取得全文或artifact。 |
| D09 / 论文37 | GPUArmor: A Hardware-Software Co-Design for Efficient and Scalable Memory Safety on GPUs | 2026 / ACM TACO | [DOI](https://doi.org/10.1145/3815783) · [预印本](https://arxiv.org/abs/2502.17780) | **出版方元数据/预印本**。预印本2025；正式卷期2026。索引与Crossref在线日期不同，此处采用Crossref且仅按年引用。 |
| D10 / 补充 | PhantomMap: GPU-Assisted Kernel Exploitation | 2026 / NDSS | [会议](https://www.ndss-symposium.org/ndss-paper/phantommap-gpu-assisted-kernel-exploitation/) · [原文](https://www.ndss-symposium.org/wp-content/uploads/2026-f201-paper.pdf) · [代码](https://github.com/Lotuhu/PhantomMap) | **会议页面/既有原文与代码**。补充：与实际物理页、映射与回收检查直接相关。 关联：直接。 |
| D11 / 补充 | LeftoverLocals | 2024 / 漏洞研究与公开PoC | [作者说明](https://leftoverlocals.com/) · [代码](https://github.com/trailofbits/LeftoverLocalsRelease) | **作者README/既有代码核验**。片上local memory残留；是研究与测试资料，不强配学术会议。 关联：直接。 |
| D12 / 补充 | Securing GPU via Region-based Bounds Checking (GPUShield) | 2022 / ISCA | [DOI](https://doi.org/10.1145/3470496.3527420) · [作者原文](https://hparch.gatech.edu/papers/jaewon_2022_isca.pdf) | **既有作者原文**。补充GPU程序内存安全；GPUShield为机制名。 |
| D13 / 补充 | cuCatch: A Debugging Tool for Efficiently Catching Memory Safety Violations in CUDA Applications | 2023 / PLDI / PACMPL | [DOI](https://doi.org/10.1145/3591225) · [作者机构](https://research.nvidia.com/publication/2023-06_cucatch-debugging-tool-efficiently-catching-memory-safety-violations-cuda) | **既有作者原文**。调试工具研究；论文存在不等于已确认公开完整实现。 |

### 可信I/O、调度与相邻研究（2）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| E01 / 论文40 | SGXIO: Generic Trusted I/O Path for Intel SGX | 2017 / CODASPY | [DOI](https://doi.org/10.1145/3029806.3029822) · [预印本](https://arxiv.org/abs/1701.01061) | **出版方元数据/索引**。可信I/O背景；与B14草稿中的同名原型分开。 |
| E02 / 论文43 | Secure and Timely GPU Execution in Cyber-physical Systems | 2023 / ACM CCS | [DOI](https://doi.org/10.1145/3576915.3623197) | **出版方元数据**。系统简称AvaGPU；第三方索引标为ASPLOS有误，正式出版为CCS。 关联：直接。 |

### 机密计算中断补充（7）

这一组保留前面对跨 Realm 中断/事件可信性的研究线索，属于 CPU TEE 安全背景，不计作 GPU TEE 实现。中断语义完整性、异常重入和精确执行控制是不同研究目标。

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| I01 / 补充 | Heckler: Breaking Confidential VMs with Malicious Interrupts | 2024 / USENIX Security | [作者原文](https://ahoi-attacks.github.io/heckler/heckler_usenix24.pdf) | **前轮作者资料/原文核验**。恶意中断的执行语义；CPU TEE背景。 关联：中断方向。 |
| I02 / 补充 | WeSee: Using Malicious #VC Interrupts to Break AMD SEV-SNP | 2024 / IEEE S&P | [DOI](https://doi.org/10.1109/SP54263.2024.00262) · [预印本](https://arxiv.org/abs/2404.03526) | **前轮作者资料/原文核验**。异常原因与上下文绑定；非Arm漏洞证据。 关联：中断方向。 |
| I03 / 补充 | Sigy: Breaking Intel SGX Enclaves with Malicious Exceptions & Signals | 2025 / AsiaCCS | [DOI](https://doi.org/10.1145/3708821.3710838) · [作者原文](https://ahoi-attacks.github.io/sigy/sigy_asiaccs25.pdf) | **前轮作者资料/原文核验**。可信信号/事件依据；跨可信域通知直接背景。 关联：中断方向。 |
| I04 / 补充 | SmashEx: Smashing SGX Enclaves Using Exceptions | 2021 / CCS | [DOI](https://doi.org/10.1145/3460120.3484821) · [作者项目](https://jasonyu1996.github.io/SmashEx/) | **前轮作者资料/原文核验**。异常重入；此前核对项目说明，未取得全文。 关联：中断方向。 |
| I05 / 补充 | SGX-Step: A Practical Attack Framework for Precise Enclave Execution Control | 2017 / SysTEX | [作者原文](https://jovanbulck.github.io/files/systex17-sgxstep.pdf) | **前轮作者资料/原文核验**。精确执行控制与侧信道。 关联：中断方向。 |
| I06 / 补充 | SEV-Step: A Single-Stepping Framework for AMD-SEV | 2024 / TCHES 2024(1) | [DOI](https://doi.org/10.46586/tches.v2024.i1.180-206) | **前轮作者资料/原文核验**。卷期2024，在线2023；精确执行控制。 关联：中断方向。 |
| I07 / 补充 | AEX-Notify: Thwarting Precise Single-Stepping Attacks through Interrupt Awareness for Intel SGX Enclaves | 2023 / USENIX Security | [会议](https://www.usenix.org/conference/usenixsecurity23/presentation/constable) · [作者原文](https://jovanbulck.github.io/files/usenix23-aexnotify.pdf) | **前轮作者资料/原文核验**。中断感知与可信恢复；不宣称消除全部侧信道。 关联：中断方向。 |

### 厂商历史演讲（2）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| V01 / 论文23 | The Developer’s View to Secure an Application and Data on NVIDIA H100 with Confidential Computing | 待核 / NVIDIA GTC演讲 | [固定版本PDF副本](https://github.com/ConfidentialComputing/GPU-TEE-Papers/tree/8e367018ffbf209f62184423de9874c544d856c4) · [现行官方概览](https://docs.nvidia.com/confidential-computing/) | **目录已确认，PDF重取超时**。目录可确认文件存在；正文未取得，题名/作者/日期未完成封面核验。“Creating the First Confidential GPUs”暂不作为已核实题名组成部分；演讲非同行评审论文。 |
| V02 / 论文24 | Hopper Confidential Computing: How it Works Under the Hood | 2023 / NVIDIA/Microsoft，GTC March 2023 | [固定版本PDF副本](https://github.com/ConfidentialComputing/GPU-TEE-Papers/tree/8e367018ffbf209f62184423de9874c544d856c4) · [官方技术博客](https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/) | **演讲PDF封面**。Phil Rogers、Antoine Delignat-Lavaud；原猜测的同名博客路径404，演讲题名不应据此伪造成博客。 |

### 厂商与可信I/O标准（15）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| V03 / 补充 | NVIDIA Confidential Computing Documentation | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/confidential-computing/) | **官方页面/README**。现行文档入口；各部署模式有独立支持范围。 |
| V04 / 补充 | NVIDIA Confidential Computing Overview | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/confidential-computing/overview) | **官方页面/README**。部署边界、证明、密钥释放；按检索日保存快照。 |
| V05 / 补充 | NVIDIA Confidential Virtual Machines | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/confidential-computing/virtual-machines) | **官方页面/README**。明确区分Hopper、Blackwell、单GPU、多GPU、PPCIe；不从旧H100演讲推导现行支持矩阵。 |
| V06 / 补充 | NVIDIA CVM Trust and Threat Model | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/confidential-computing/virtual-machines/dev/threat-model) | **官方页面/README**。威胁模型正文：可信组件、外部软件与物理/侧信道边界。 |
| V07 / 补充 | NVIDIA CVM Supported Platforms | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/confidential-computing/virtual-machines/dev/supported-platforms) | **官方页面/README**。核对CPU/GPU/驱动/固件与运行模式组合；不以产品名替代支持矩阵。 |
| V08 / 补充 | NVIDIA Attestation Documentation | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/attestation/) | **官方页面/README**。证明格式、NRAS、RIM、SDK与声明验证入口。 |
| V09 / 补充 | NVIDIA Attestation SDK / NVAT | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://github.com/NVIDIA/attestation-sdk) · [固定README](https://github.com/NVIDIA/attestation-sdk/blob/11b2bfeb42a1158aa08744603ecb239ccb3d2265/README.md) | **官方页面/README**。已读README：C++实现，C API、CLI与Rust绑定；部分新验证流程标为experimental。 |
| V10 / 补充 | NVIDIA nvTrust | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://github.com/NVIDIA/nvtrust) · [固定README](https://github.com/NVIDIA/nvtrust/blob/a8090b65872a15bf0fd1f69f3d9b754b1be431b5/README.md) | **官方页面/README**。已读README：Python SDK与Local GPU Verifier标为deprecated，指向新C++ SDK/CLI；按检索日状态记录。 |
| V11 / 补充 | NVIDIA MIG User Guide | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/latest/) | **官方页面/README**。资源分区背景；MIG不自动等于机密计算或无侧信道。 |
| V12 / 补充 | NVML Confidential Computing Definitions / API入口 | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlConfidentialComputingDefs.html) | **官方页面/README**。从现行NVML索引取得的机密计算定义入口；旧猜测路径404，不保留为正文链接。 |
| V13 / 补充 | NVIDIA Open GPU Kernel Modules | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://github.com/NVIDIA/open-gpu-kernel-modules) | **入口重取失败**。公开驱动源码；不将其视为全部GPU固件开源。 本轮README重取超时。 |
| V14 / 补充 | DMTF SPDM | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://www.dmtf.org/standards/spdm) | **官方页面/README**。设备身份、测量与会话协议标准入口。 |
| V15 / 补充 | PCI-SIG TDISP | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://pcisig.com/tee-device-interface-security-protocol-tdisp) | **入口重取失败**。设备接口可信分配协议；页面本轮超时，未取得规范全文。 |
| V16 / 补充 | AMD SEV-TIO Whitepaper | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://www.amd.com/content/dam/amd/en/documents/developer/sev-tio-whitepaper.pdf) | **官方页面/README**。可信I/O架构背景；与GPU厂商实现分开。 |
| V17 / 补充 | Intel TDX Connect Architecture Specification | 检索于2026-10-26 / 官方文档/代码/标准入口 | [官方](https://www.intel.com/content/www/us/en/content-details/773614/intel-tdx-connect-architecture-specification.html) | **官方页面/README**。可信设备分配背景；入口页面不等于规范全文已读。 |

### Arm与内核规范（11）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| K01 / 补充 | Arm RME System Architecture (DEN0129) | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://developer.arm.com/documentation/den0129/latest/) | **入口重取失败**。本轮超时；保留规范编号与官方入口，未取得最新正文。 关联：直接。 |
| K02 / 补充 | Arm RMM Specification (DEN0137) | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://developer.arm.com/documentation/den0137/latest/) | **官方入口，未取得规范正文**。重定向到Arm文档壳页，不能记为规范正文已读。 关联：直接。 |
| K03 / 补充 | Arm SMMU Architecture Specification (IHI0070) | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://developer.arm.com/documentation/ihi0070/latest/) | **入口重取失败**。本轮超时；可信映射/SMMU管理的规范入口。 关联：直接。 |
| K04 / 补充 | Arm GIC Architecture Specification (IHI0069) | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://developer.arm.com/documentation/ihi0069/latest/) | **入口重取失败**。本轮超时；LR、虚拟中断及状态保存恢复的规范入口。 关联：直接。 |
| K05 / 补充 | TF-RMM Documentation | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://tf-rmm.readthedocs.io/en/latest/) | **官方页面/README**。公开实现文档；本项目固定补丁版本另见CURRENT_BASELINE，不更新本地子模块。 关联：直接。 |
| K06 / 补充 | TF-A Realm Management Extension | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://trustedfirmware-a.readthedocs.io/en/latest/components/realm-management-extension.html) | **官方页面/README**。Root/RMM集成与启动链背景。 关联：直接。 |
| K07 / 补充 | Linux DRM Memory Management | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://docs.kernel.org/gpu/drm-mm.html) | **官方页面/README**。GPUVM、对象与映射管理；在线主线文档不替代本地源码版本。 关联：直接。 |
| K08 / 补充 | Linux Asynchronous VM_BIND | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://docs.kernel.org/gpu/drm-vm-bind-async.html) | **官方页面/README**。异步映射与同步规则。 关联：直接。 |
| K09 / 补充 | Linux DMA-BUF and DMA Fence | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://docs.kernel.org/driver-api/dma-buf.html) | **官方页面/README**。共享、同步和完成语义；IRQ到达不等于fence成功。 关联：直接。 |
| K10 / 补充 | Linux IOMMUFD | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://docs.kernel.org/userspace-api/iommufd.html) | **官方页面/README**。IO地址空间、设备绑定与映射生命周期。 关联：直接。 |
| K11 / 补充 | AMDGPU Process Isolation | 检索于2026-10-26 / 规范/官方实现文档 | [官方](https://docs.kernel.org/gpu/amdgpu/process-isolation.html) | **官方页面/README**。进程隔离与状态清理参考；非Mali已实现能力。 关联：直接。 |

### 测试工具（5）

| ID / 原清单编号 | 资料 | 年份 / 出处 | 来源 | 核验与归档备注 |
| --- | --- | --- | --- | --- |
| T01 / 补充 | NVIDIA Compute Sanitizer | 检索于2026-10-26 / 官方测试资料 | [项目](https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html) | **官方页面/README**。CUDA程序访存、初始化、同步等检测；工具通过不是跨租户TEE证明。 |
| T02 / 补充 | Khronos VK-GL-CTS | 检索于2026-10-26 / 官方测试资料 | [项目](https://github.com/KhronosGroup/VK-GL-CTS) | **官方页面/README**。Vulkan/OpenGL/OpenGL ES一致性测试；功能证据。 |
| T03 / 补充 | Khronos OpenCL-CTS | 检索于2026-10-26 / 官方测试资料 | [项目](https://github.com/KhronosGroup/OpenCL-CTS) | **官方页面/README**。OpenCL一致性测试；与恶意任务隔离测试分开。 |
| T04 / 补充 | IGT GPU Tools | 检索于2026-10-26 / 官方测试资料 | [项目](https://gitlab.freedesktop.org/drm/igt-gpu-tools) | **入口存在，返回反爬页面**。DRM驱动测试；平台/驱动支持需按具体子测试确认。 本轮HTTP 200实际为Anubis挑战页，未取得README。 |
| T05 / 补充 | Piglit | 检索于2026-10-26 / 官方测试资料 | [项目](https://gitlab.freedesktop.org/mesa/piglit) | **入口存在，返回反爬页面**。图形栈回归；不等于安全审计。 本轮HTTP 200实际为Anubis挑战页，未取得README。 |

## 公开代码与 artifact 的实际核验范围

本轮没有构建、启动或运行任何论文原型。以下只给出已确认的代码入口和读取范围；未找到完整仓库不等于作者从未发布代码。不同平台的 artifact 不能直接成为本项目的运行依赖。

| 工作 | 已确认入口 | 本次及既有核验范围 |
| --- | --- | --- |
| StrongBox | [作者仓库](https://github.com/Compass-All/CCS22-StrongBox)，既有固定提交 `8b1502ff2dfc9199d64528b5f3fb4478143aee25` | 复用既有关键 TF-A 路径与内容哈希，本轮 README 重取超时 |
| CAGE | [作者仓库](https://github.com/Compass-All/NDSS24-CAGE)，既有固定提交 `c79106486eae0e55b49c3f98c0d4bb01a3d3a91b` | 复用功能/性能原型关键路径；两类证据分开 |
| ACAI | [作者仓库](https://github.com/sectrs-acai/acai) | 复用既有 SMMU/子模块资料；不拉取上游更新 |
| CRONUS | [作者仓库](https://github.com/hku-systems/cronus) | 复用既有论文和 README |
| Honeycomb | [作者 artifact](https://github.com/Jiacheng/honeycomb-osdi23-ae)，既有固定提交 `220df49c17ea9feb51133dd472bc8d6bed46d8ba` | 已有 RDNA2 verifier 关键源码；单独 verifier 的运行不等于完整 TEE 复现 |
| GEVisor | [作者页面直接链接的仓库](https://github.com/purseclab/GEVisor)，本轮 Git 树对象 `f163235d2681ae28137b9b1c21a26a2ed97ef77a` | 已读顶层 README、取得目录；依赖代码中含测试不等于已核对整套安全证明 |
| GPUReplay / GR-T | [相关仓库](https://github.com/bakhi/GPUReplay) | 已读 README：Mali-G71/HiKey960、记录/重放原型；不能据此确认 GR-T 完整安全组件均公开 |
| PhantomMap | [作者仓库](https://github.com/Lotuhu/PhantomMap)，既有固定提交 `4937977a6cb2b717d21747f0b29ce3393e3861f8` | 分析器、驱动 patch 与测试入口；移植到 Panthor 需重新识别路径 |
| LeftoverLocals | [作者仓库](https://github.com/trailofbits/LeftoverLocalsRelease)，既有固定提交 `2e5fc857fd6ef53c30f37c0899c03bad6c7560ef` | 已读 README 和一个 listener kernel；未在本项目运行 |
| NVIDIA nvTrust | [仓库](https://github.com/NVIDIA/nvtrust)，检索提交 `a8090b65872a15bf0fd1f69f3d9b754b1be431b5` | README 的弃用/迁移说明；固定版本内容核验见来源索引 |
| NVIDIA Attestation SDK | [仓库](https://github.com/NVIDIA/attestation-sdk)，检索提交 `11b2bfeb42a1158aa08744603ecb239ccb3d2265` | README 的 C API、CLI、Rust 绑定和 experimental 标记 |
| PORTAL、XpuTEE、ccAI、Guardian、SAGE、MOLE | 采用目录中的正式论文/作者入口 | 本轮未确认独立完整 artifact，不猜测仓库路径或把组织首页当完整实现 |

Git 提交、Git 树对象与文件 SHA-256 是不同标识。对于只取得 README 或网页的条目，来源索引给的是文件内容哈希，不能把它写成 Git 提交号。

## 与当前项目文档和测试资料的对应关系

这一部分仅提供阅读入口，不增加实现要求，也不把文献中的安全能力宣称为当前代码已经具备。

| 研究问题 | 优先资料 | 当前项目入口 |
| --- | --- | --- |
| 可信服务 Realm、设备控制与 CPU/DMA 边界 | PORTAL、CAGE、ACAI、RME/RMM/SMMU 规范 | [平台假设](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)、[当前安全审查](GPU_SECURITY_DESIGN_REVIEW_20261026.md) |
| 对象归属、实际物理页与映射生命周期 | ACAI、PhantomMap、DRM MM、VM_BIND、DMA-BUF | [架构精解](GPU_CLIENTPROXY_ARCHITECTURE_GUIDE_20261022.md)、[既有隔离调研](GPU_ISOLATION_RESEARCH_AND_CODE_MAP_20261018.md) |
| GPU 执行隔离、指令验证与程序内存安全 | Honeycomb、Guardian、GPUShield、LAK、GPUArmor、cuCatch | [GPUVM 隔离测试说明](../../GPU-SFTP/tests/panthor-ioctl-smoke/GPUVM_ISOLATION.md) |
| 固件、MCU 和片上状态 | MOLE、Graviton、Whispering Pixels、LeftoverLocals、AMDGPU Process Isolation | [安全审查](GPU_SECURITY_DESIGN_REVIEW_20261026.md)；测试平台和漏洞适用范围需分别验证 |
| 跨 Realm 事件与真实 GPU 完成 | CRONUS、Sigy、Heckler、WeSee、SmashEx、GIC、DMA fence | [可信通知与架构](GPU_CLIENTPROXY_ARCHITECTURE_GUIDE_20261022.md)、[IRQ 路径](GPU_TARGET_IRQ_RETURN_OPTIMIZATION_20261024.md)、[RMM 事件状态机](../../opencca/tf-rmm/runtime/core/xshm_endpoint.c) |
| 调度可用性与侧信道边界 | AvaGPU、Telekine、Behind Bars；SGX-Step/SEV-Step/AEX-Notify 为 CPU 背景 | [当前基线与未测范围](CURRENT_BASELINE.md)；不从 IRQ 合并推导防单步保证 |
| 测试与结果归档 | 论文 artifact、CTS、IGT、Piglit、Compute Sanitizer | [现有 Realm 测试](../../GPU-SFTP/tests/realm-xshm/README.md)、[GPUVM 测试](../../GPU-SFTP/tests/panthor-ioctl-smoke/GPUVM_ISOLATION.md)、[实验入口](../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md) |

现有 `realm-xshm` 文档列出双 Client API/计算/权限/IRQ检查及实际 GPU 越域访问故障测试；这里只确认测试入口与范围说明，不重跑或沿用历史 PASS 保证当前安全。CTS/Piglit 的功能一致性、Compute Sanitizer 的程序缺陷检测、LeftoverLocals 的残留检测、跨 Realm 授权负例分别提供不同证据，不能互相替代。

## 建议的阅读批次与后续补齐项

| 批次 | 文献与资料 | 本项目用途 |
| --- | --- | --- |
| 第一批 | PORTAL、CAGE、ACAI、PhantomMap；RMM/SMMU/GIC 规范 | 建立与已确定架构直接相关的引用基础 |
| 第二批 | StrongBox、Graviton、MOLE、Honeycomb、Guardian、GR-T、CRONUS | 比较可信边界、执行控制、固件和代理/重放路线 |
| 第三批 | Sigy、Heckler、WeSee、SmashEx；真实 fence 与 GIC 状态规则 | 支撑“事件来源＋原因＋生命周期＋安全恢复”的中断研究 |
| 第四批 | Plutus、Common Counters、PSSM、Adaptive Security、Salus、多GPU元数据管理 | 按需扩展安全内存架构背景；不重复当前映射授权设计 |
| 第五批 | NVIDIA 威胁模型、支持矩阵、证明文档与 SDK；公开测试工具 | 比较可部署产品的声明和验证流程，分别记录版本与测试证据 |

尚需补齐的书目/获取事项：B14 的正式发表信息；V01 的原始演讲入口、封面题名、作者和日期；D04 预印本与不同题名后续工作的正式版本关系；部分工作完整 artifact 的公开范围；Arm 规范正文及固定修订版；Behind Bars 全文/代码。这里保留“未确认”，不把检索失败解释成资料不存在。

本轮形成的是可扩展的书目基线，不声称覆盖截至检索日所有 GPU 安全论文。原清单没有遗漏的编号，后续新增条目可使用相同字段：稳定 ID、完整题名、工作族/版本、正式出处与日期、DOI/作者入口、平台与主题、代码范围、核验深度、检索日期及来源。

结构核验：[validation.json](evidence/gpu-literature-20261026/validation.json)。命令：`python3 build/gpu-security-literature-20261026/validate_catalog.py`；退出码0。核对89条唯一ID、全部50处原编号、来源引用、146份来源文件内容哈希及本地文档链接。这是资料结构/完整性检查，不是硬件安全测试。

统一记录：**文献核验与归档｜对照版本与分数：不适用 → 本版分数：未测｜分差及百分比：不适用｜条件：仅控制机文献/代码只读核验与文档整理｜run-id：不适用，未运行硬件实验；资料目录：`build/gpu-security-literature-20261026/`；结构核验命令与退出码见下述核验记录｜结论：保留文献库，待核项明确标记。**
