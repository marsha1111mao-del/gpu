# TGS-061｜HIX：可信 GPU 服务、硬件 I/O 归属与多用户隔离深读

研读日期：<date start="2026-10-27" />。状态：14 页作者公开全文、正式书目与有界 artifact 检索已完成。未取得已确认匹配的 HIX 实现仓库，未执行原型；未改运行代码，无新增性能测量。

## 1. 文献与证据版本

**Heterogeneous Isolated Execution for Commodity GPUs**，Insu Jang、Adrian Tang、Taehoon Kim、Simha Sethumadhavan、Jaehyuk Huh，ASPLOS 2019，455–468。DOI：[10.1145/3297858.3304021](https://doi.org/10.1145/3297858.3304021)。[作者公开 PDF](https://jaehyuk-huh.github.io/papers/jang_asplos19.pdf)由[作者出版列表](https://jaehyuk-huh.github.io/publications.html)直接链接；第一作者现主页也确认标题、作者及会议。

全文 `build/cca-gpu-followup-20261027/hix-author.pdf`，SHA256：`227ec400ce38757a014f916acace2c354f765f9e4550ca8d84aae2b3e49b0c9d`。Crossref 元数据与论文首页对应。这是原库 TGS-061 的完成，不是新增条目；同名 HIX 缩写和完整标题不重复计数。

## 2. 核心问题与贡献

普通 CPU TEE 保护 enclave 内存，却不自动保护设备驱动、GPU MMIO、I/O 路由和 DMA 传输。恶意 OS/hypervisor 即使读不到 enclave，也可能改 GPU 命令、重定向设备地址或替换输入输出。

HIX 建立专门的 GPU enclave：关键驱动运行于可信域，独占真实 GPU 控制，并向用户 enclave 提供服务。CPU MMU、SGX 元数据和 PCIe root complex 共同保护设备归属与 I/O 路径；跨不可信内存传输使用认证加密。

它不修改 GPU 内部硬件，修改的是 CPU/SGX 与 I/O 互连，并通过 KVM/QEMU 加真实 GPU 模拟评估。这是其明确设计假设与实验方式，不能因实验机原生缺少这些扩展就否定其架构贡献。

## 3. 威胁模型和排除项

攻击者控制 OS、内核驱动和 hypervisor，可以读普通主存、改 CPU 页表、修改 I/O 配置及 IOMMU。CPU 封装、GPU 卡和可信 PCIe 机制正确；GPU 有独立设备内存。

排除物理攻击、侧信道、可信应用或 GPU 代码中的实现缺陷，以及调度拒绝、资源耗尽等可用性攻击。PCIe 物理注入和直接读取 GPU DRAM 均不覆盖；数据在 GPU 内存中可以是明文。这与完整 GPU 显存加密方案的保护范围不同。

设计不支持 GPU P2P/GPUDirect，也未实现 GPU demand paging。多用户请求支持不等于任意多 GPU 互连、多用户硬件并发或完整恶意租户测试证明。

## 4. 可信基与服务角色

可信基包含 CPU/SGX、HIX 硬件元数据及检查、可信 PCIe 路径、GPU 硬件及 BIOS、GPU enclave 内驱动、用户 enclave 的可信 runtime 和 GPU 密码 kernel。普通 OS 只提供非权威资源服务，例如提出 MMIO VA 分配；其返回仍需验证。

GPU enclave 同时承担设备独占管理和用户服务入口。它与本项目可信 ProxyRealm 的组织方式相近，但 SGX enclave、Realm、RMM 的权限和身份来源不同，不能直接互换名称而省略协议。

## 5. 设备与 MMIO 归属元数据

新增 `EGCREATE` 以真实 PCIe Bus/Device/Function 身份注册 GPU enclave，硬件保证同一 GPU 不能同时归属两个 GPU enclave。`EGADD` 注册并验证该 enclave 的 VA 与设备 MMIO PA 范围。

GECS 保存设备身份和所属 GPU enclave；TGMR 保存可信 MMIO 地址映射。这些元数据放在软件不可直接篡改的 SGX 保护区域。于是“某 VA 可访问”之外还要回答“映射到哪块真实设备的哪个区域、属于哪个可信服务”。

这正是本项目地址翻译以外的控制面职责：真实页表合法不自动证明访问了预期设备，设备配置和映射根也必须属于正确的可信服务实例。

## 6. CPU 地址检查与真实路由保护

MMIO TLB miss 时，页表 walker 在填充 TLB 前验证 GPU enclave ID、请求 VA、TGMR VA 和 MMIO PA。恶意 OS 改 PTE 不能让错误映射获得可用 TLB 项。

同时，`EGCREATE` 触发 MMIO lockdown，冻结从 root complex 到 GPU 的相关 MMIO/BAR/路由配置，丢弃未授权修改，且把配置纳入测量。保护 CPU 页表和保护总线路由分别必要：后者阻止同一地址被导向攻击者设备。

论文对 BAR sizing 需写全 1 的兼容问题给出可能的例外处理，属于待细化设计；不能把允许例外当成已证明不会破坏冻结不变量。对本项目则应明确平台保护的真实 root 配置、设备身份、关键 MMIO 及所有可重配置入口。

## 7. 初始化、测量与设备真实性

GPU enclave 验证 GPU BIOS，并 reset 设备以移除此前可能留下的程序/状态；可信 root complex 提供真实设备属性，路由保护防止宿主把真实设备换成软件模拟端点。用户还可验证 GPU enclave 代码的 SGX 证明。

这是组合信任链：可信服务代码、BIOS/初始化、真实设备属性和受保护路由相互配合。它不是现代 SPDM/设备持钥远程证明协议；不能把读取 BIOS hash 单独表述为任意 GPU 固件、MCU、全部运行状态均已密码学证明。

结合 MOLE，当前项目应把已假定可信加载的固件与其生命周期写进信任链，说明测量哪些组件、由谁校验，以及 reset/更新后如何保持策略，不必据此凭空否认可信固件假设。

## 8. 用户身份、会话与共享内存

用户 enclave 与 GPU enclave 先进行 SGX local attestation，随后建立会话密钥；设计还让 GPU 参与密钥建立。不同用户 enclave 使用不同密钥，可信服务维护每用户 GPU context。

通信分为 message queue 和共享内存：队列负责唤醒与协调，共享内存承载加密请求和数据。HIX 使用 OCB-AES-128，并在安全分析中明确使用递增 nonce 防重放；不能说它完全没有新鲜度设计。

但论文没有像完整协议规格那样逐字段给出 Client、session、context、job、buffer generation、cancel/reset epoch 与每条消息的关联，也没有给出覆盖这些转换的形式化证明。对项目的推论是继续明确这些绑定和失效规则，不是认定 HIX 已被某个重放攻击攻破。

## 9. DMA 保护及一次输入传输

不可信主存和可能恶意的 IOMMU 仍可改变 DMA 路径。HIX 依靠端点认证加密保护传输内容，而非声称 IOMMU 已可信：只有密文进入普通缓冲，接收端认证失败则终止。

以 HtoD 为例，服务验证请求元数据后，用户 enclave 加密输入并写共享内存；GPU enclave 控制 MMIO 或 DMA 将密文直接搬入 GPU，再启动 GPU 解密 kernel，完成后回复。输出则先在 GPU 加密再传回用户 enclave。

单次搬运避免“用户密文先在 GPU enclave 解密再加密”的额外拷贝。大块传输还按 chunk 流水化密码运算与搬运。这里的安全前提是认证验证成功后才允许数据被计算或发布；MAC 不能单独证明 DMA 目的地址、任务归属、事务停止或共享对象生命周期均合法。

## 10. 多用户共享与状态清理

HIX 为每个用户创建独立 GPU context 和独立密钥，以区别旧代 MPS 把不同用户 kernel 合入同一 GPU 地址空间的做法。原型通过 context switch 共享设备，不是同时恶意执行所有 context 的硬件隔离证明。

论文明确指出 context switch 和 global/shared memory 重用可能泄漏，要求 runtime 清理释放的 global memory 和共享状态。它没有给出覆盖所有片上状态、错误路径与恶意写竞争的完整清理验证。

对当前项目，应直接使用已有独立 GPUVM，并将“撤销后安全回收”展开为旧访问失效、未完成事务处理、内容清理和再次授权的顺序。TGS-042 的残留实验证据与这里的清理责任相互呼应，不能只看地址空间分离。

## 11. 服务终止与恢复策略

若 OS 强制杀死 GPU enclave，HIX 保留硬件中的旧所有权，所有其他软件以及新 GPU enclave 都不能接管设备，直到断电重启并清除 GPU 状态。它以牺牲可用性维持失败后的保密边界。

正常终止则由可信服务中止 GPU 执行、清理数据、交还设备，并通知用户不再信任原服务。两条路径不同，不能把进程死亡等同完成清理，也不能依据退出通知直接把资源授给下一用户。

项目无需照搬整机重启策略。更有研究价值的是：在既定可信平台与回收假设下，哪些受信状态允许局部恢复，哪些失败必须隔离资源；cookie/epoch 可拒绝旧通知，但不能单独替代停止旧 DMA 或清除残留。

## 12. 原型与中断研究边界

平台为 Core i7-6700 3.40 GHz、GTX 580 1.5 GB，host Ubuntu 16.04.4 / Linux 4.14.28，guest Ubuntu 16.04.5 / Linux 4.13.0，SGX SDK 2.0。GPU 通过真实设备承载运算，HIX 指令/元数据由 KVM VM-exit handler 实现，lockdown 由 QEMU IOH3420 模拟，MMIO 检查由 EPT violation 模拟。

驱动来自改造的开源 Gdev。原文明确说 Gdev 与 GPU 的同步采用 **MMIO polling，不用 interrupts**。所以 HIX 是可信服务和 I/O 归属的重要前序工作，却不能作为“已解决可信 GPU 中断与 Realm 通知”的证据。

这为项目的第二部分提供明确切入点：在已有 RMM 认证通知、持久 IRQ、真实 fence 和 epoch 上，论证如何从设备完成状态到正确 Client 的任务状态转换，覆盖合并、延迟、重复、取消和 reset。通知路由正确与任务成功之间仍需要可信状态判定。

## 13. 实验与准确数字

每项实验运行 5 次取平均；基线为原始非安全 Gdev。论文不与本项目 Mali 图形栈或当前 CCA 实现做同条件比较。

| 指标 | 原文报告 | 适用边界 |
| --- | --- | --- |
| 9 个选定 Rodinia 应用 | 正文平均慢 26.8%；摘要约 26% | 并非每个应用固定开销 |
| BP / NW / PF | 开销分别约 81.5% / 70.1% / 154% | 传输较重负载开销大 |
| 最大矩阵乘法 | 11264×11264，慢约 6.34% | 高计算/传输比；设备内存限制约 1.5 GB |
| 矩阵加法 | 论文概括约 2.5 倍执行时间 | 低计算/传输比，不适用于全部矩阵配置 |
| 2 用户并行请求 | 比 Gdev parallel 慢约 45.2% | 同时发请求，GPU context 切换共享 |
| 4 用户并行请求 | 比 Gdev parallel 慢约 39.7% | 多次密码 kernel、切换和小任务利用率影响 |

HS、LUD、NN 等小任务还受 HIX 初始化较快影响，不可一律归因于更低 GPU 执行成本。多用户图使用 Gdev 单用户时间归一化，不能将图中的串行、并行比例混成单用户安全开销；未来 Volta 并发改善是作者预期，不是原型实测。

## 14. 安全论证与公开 artifact

论文以可信硬件和 SGX 隔离为两个基础公理，逐类分析数据/代码、MMIO 翻译、DMA、路由修改、服务终止与设备模拟攻击。它提供机制层论证，没有展示完整形式化验证或大规模恶意多租户回归；性能运行成功不能代替这些安全证据。

本轮检查作者出版列表、第一作者公开仓库列表及准确标题的 GitHub repository 检索，没有取得确认匹配的 HIX 发布仓库。这是有界检索结果，不宣称作者从未公开代码。论文引用的原始 Gdev、Intel KVM-SGX/QEMU-SGX 是依赖，不是已验证包含 HIX 改动的 artifact，不能用它们冒充完整复现。

因此本报告没有固定 HIX 源码提交、声称审核其 nonce/清理实现，或执行论文数字。全文已经取得并精读，代码可得性及验证范围独立登记。

## 15. 与 PORTAL / ACAI / 本项目的关系

HIX 提供可信设备服务的前序结构；PORTAL 将可信服务组织带入 CCA Realm；ACAI 强调设备/Realm 身份与映射归属的一致性；PhantomMap 让审查进一步落到实际物理页。它们可以支撑项目的设计脉络，但各自不覆盖全部职责。

本项目给定模型是可信完整驱动 ProxyRealm 控制 SMMU，RMM 认证原 Client，在映射时检查对象/HPA/权限/生命周期并合成直达 HPA 的 GPU Stage-1，平台保护实际 PTE/root/MMIO 和固件，其他设备保留 Stage-2。HIX 的 MMIO 保护不能替代逐 Client 的 HPA 授权；它的认证加密也不意味着项目在已有受保护路径上必须再复制同一套密码层。

对项目最贴切的研究增量是把三条已有链路联合起来：可信请求身份与对象归属；原生执行 context、页授权及真实 fence；跨 Realm 通知与取消/reset 后的生命周期。每条状态转换都应说明可信依据，而不是只列“有 SMMU、有 IRQ、有 epoch”。

## 16. 后续验证建议

重点覆盖服务启动/重启期间设备归属是否连续、失败时是否错误放开 MMIO、旧会话消息是否能推进新任务、reset 后 context 与对象是否仍属于同一 Client，以及回收前是否确已阻断旧访问。认证失败或状态不匹配应拒绝请求并保留资源隔离。

这是在用户认可的保护假设下细化协议，不用 GTX/RK 的实验差异否定架构，也不凭文献推断当前实现已存在漏洞。本轮仅静态研究，未运行硬件回归、通知注入、reset 压力或跨 Client 攻击测试。
