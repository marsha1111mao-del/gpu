# GPU Travelling：机密 GPU 的跨 CVM 交接、密钥撤销与最小授权边界

研读日期：2026-10-28。完整阅读作者公开的正式排版 15 页 PDF，§§1–10、59 条参考文献，另对文件页 3、4、6、7、9、10、11、12、13 的架构、时序、安全论证和表格进行图像核对。本文区分论文提出的机制、实测、外推、未取得的 artifact，以及面向本项目的建议。论文使用 NVIDIA/TDX，并非 Arm CCA 系统，但与多 VM GPU 共享和设备交接直接相关。

## 1. 书目信息和证据范围

| 项目 | 内容 |
| --- | --- |
| 正式标题 | GPU Travelling: Efficient Confidential Collaborative Training with TEE-Enabled GPUs |
| 作者 | Shixuan Zhao、Zhongshu Gu、Salman Ahmed、Enriquillo Valdez、Hani Jamjoom、Zhiqiang Lin |
| 会议及页码 | ACM CCS 2025，2653–2667 |
| DOI | [10.1145/3719027.3765029](https://doi.org/10.1145/3719027.3765029) |
| 作者主页全文 | [CCS25b.pdf](https://zhiqlin.github.io/file/CCS25b.pdf) |
| 作者机构页面 | [IBM Research](https://research.ibm.com/publications/gpu-travelling-efficient-confidential-collaborative-training-with-tee-enabled-gpus) |
| 作者明确提供的 artifact | [Zenodo 16899384](https://zenodo.org/records/16899384) |
| 本地固定全文 | `build/cca-gpu-followup-20261027/travelling-author76.pdf` |
| PDF SHA256 | `d46e315d10da14649113aaffd7ca26a8b778e60962550a48d45ad63a475cd5d9` |

作者主页直接将 GPU Travelling 链接到该 PDF，全文首页标题/作者/DOI及正式页码匹配。IBM 页面使用 Md Salman Ahmed、Ray Valdez 等名字形式，本报告以论文首页姓名为准。会议日期为 2025-10-13–17；Crossref 分别给出印刷/在线登记 2025-11-19/22，不把元数据日期差异误写为不同论文。

论文 §5 明确给出了 Zenodo artifact，不能称作者未公开实现。本轮 Zenodo API、记录页及带尾斜线 API 请求均连接超时，尚未取得文件清单、归档或固定代码版本。GitHub 精确题名检索未返回仓库；这不是 artifact 不存在的证据。因此以下实现细节来自全文，不声称完成源码审计或复现实验。

## 2. 研究问题：共享计算资源，而非经慢网络搬运大量数据

多个相互不信任的数据持有方希望共同训练模型。常规集中训练需把数据经加密网络发送给可信计算节点；联邦训练则往往需要每个参与方有足够计算资源，并交换模型/更新。论文提出保留 GPU 上的模型，将 GPU 的访问连接临时交给数据持有方，由其直接通过 PCIe 把数据装入受保护 GPU，再把连接交还可信 orchestrator 训练。

“Travelling”不是拆下显卡物理搬运；原型是在同一 Host 内切换设备的 VM 路由和密码上下文。数据仍通过 PCIe 传输，密钥/上下文仍通过加密网络传输。被消除的是大数据经其较慢网络基线传输的路径，不能宣传为没有数据移动或无需 CPU–GPU 加解密。

原型要绕过传统 confidential GPU 在重新绑定 CVM 时 reset 并丢失内容的行为，同时保持 GPU CC 模式和模型状态。该问题对共享 GPU 有直接价值：正确的连接切换既需要功能上下文连续，也需要旧使用者能力撤销。

## 3. 威胁模型与可信基

§3.1 包含恶意数据持有方、控制 Host/Hypervisor/PCIe MUX 的恶意平台，以及两者串谋；CVM 和 GPU TEE 是安全根。各数据持有方互不信任，唯一全局信任的软件组件是自主运行的 orchestrator CVM，连同 GPU 固件及底层 TEE 平台构成必要可信基础。

orchestrator 包含训练程序、CVM OS、驱动以及使用的运行栈，参与方先检查期望代码，再用 CVM 证明确认部署。证明测量不自动验证代码无漏洞或训练逻辑没有外传数据。GPU 由 orchestrator 证明，数据持有方通过信任经过证明的 orchestrator 间接接受该 GPU；需要受保护会话把实际设备和当前交接绑定。

论文排除 DoS、侧信道、硬件攻击，并把通过模型差异反推数据视为正交问题。其直接保护目标是原始数据集机密性，不是对恶意参与方的模型完整性、模型保密和任意执行状态的全面隔离。不能因题名有 confidential collaborative training 就认定每个参与方只获得输入缓冲区访问权。

## 4. 两层交接：物理路由与通信能力

物理层是 Host 内的 PCIe MUX，切换中断目的地与 IOMMU DMA 映射；安全层则迁移 GPU 驱动状态、通信密钥和 IV。只有接上 PCIe 而没有当前有效密码上下文的 CVM，按论文的 GPU CC 假设不能正常读写 GPU。Host 因而可在可信基之外，但仍能拒绝服务。

这与明文可信管理的 PORTAL/本项目不同：论文主要靠 GPU 内部的密码通道验证对端，允许 Host 操纵物理路由；本项目假设可信 ProxyRealm 控制真实 SMMU、页表、root 和关键 MMIO，由可信身份与实际 HPA 授权约束 GPU。迁移时应保留“连接不等于授权”的原则，而不机械复制 NVIDIA 密钥导出方案。

## 5. 启动、角色和静态地址

§4.1 先依次启动数据持有方 CVM，各自初始化驱动、IRQ、BAR 和 bounce-buffer 等设施；后启动的 CVM 会令先前 GPU 上下文失效，因此 orchestrator 必须最后启动，建立最终有效 GPU 上下文。

orchestrator 持有完整 CUDA 与驱动上下文，分配 GPU dataset buffer。数据持有方不能迁移闭源 CUDA 用户态上下文，所以只持有支持复制的驱动侧上下文，通过新增 UVM ioctl 把自己的数据写入指定 GPU 地址；“没有用户态 CUDA 上下文”不等于恶意方不能绕过这个友好 API，安全权限仍由实际持有的设备能力决定。

GPU 固件预先记住多处 bounce-buffer 地址，而论文不修改闭源固件，因此每个 CVM 都预留相同地址布局，用专用 slot allocator 放置对应缓冲。这里相同的是 GPU 可见的 IOVA/对应 guest 地址，不应解释为不同 CVM 必须共享同一个 Host HPA；IOMMU 切换负责让相同 IOVA 解析到各自页面。正文在 physical address 一词上跨视图使用，项目必须明确 VA、IPA/IOVA、HPA 和 backing generation。

## 6. VFIO MUX 与持久中断入口

§5.1 改造 VFIO，允许为多个 VM 保存同一设备的配置，切换时覆盖当前目标。IRQ 保留 Host 侧 handler，替换目标 VM 的 eventfd 与 KVM bypass endpoint；DMA 则撤下旧 VM 映射并重放新 VM 映射。GPU BAR 对应区域在各 VM 间相同，原型保留它以降低切换成本。

这和项目持久 IRQ127 入口、改变逻辑接收者有功能层面的相似性，但安全保证不同。论文 §6.2 把错配 IRQ/DMA 导致的故障、意外中断及崩溃归为范围外 DoS，没有提供保护物理到达记录、待处理中断、ACK/EOI及虚拟注入的完整协议，也没有把每个 IRQ 绑定特定训练任务。

持久 handler 是优化选择；它不自动解决切换前已排队 IRQ、重复 eventfd、旧 epoch 通知和跨 VM 伪完成。若项目研究目标包括可信中断通信，就应继续采用权威终态检查和 Client/job/epoch 绑定，而不是直接沿用“错中断只会 DoS”的结论。

## 7. 为什么迁移远不止复制密钥

§5.2/§5.3 罗列 CE、CPU–GPU copy、WLC、LCIC 和 GSP RPC 的状态。CE 同一组通道使用相关密钥而各通道维护自己的 IV；copy channel 需要 tracking semaphore，WLC 需要 Work Submission Token、GPFIFO offset 与 tracking semaphore，LCIC 需要其 tracking semaphore，GSP RPC 需要 Tx/Rx sequence numbers。基础 NVIDIA 模块与 UVM 模块都要导出/导入状态。

这个清单对项目很有价值：保留 GPU 上下文或复用驱动路径时，要明确哪些状态随 Client、GPUVM、device epoch 和 job generation 改变。只迁移地址或只保存一个完成计数器不能保证请求和回复语义连续。

密码上下文复制还有独立要求：同一 AES-GCM key 下的 nonce 不可重复，不能接受陈旧或回滚的 IV、sequence 或 semaphore snapshot。功能同步不足以证明恶意方提交的迁移状态真实；论文未提供完整状态机形式化证明，本轮也未取得源码来验证拒绝重复导入和错误回滚的实现。

## 8. 正常交接工作流与撤销屏障

Figure 3 的流程是：清理旧 dataset buffer；orchestrator 导出上下文并切换 PCIe；经安全通道发送上下文给数据持有方；后者导入并复制数据；导出更新状态并把 GPU 切回；orchestrator 导入状态、立即轮换密钥，然后训练。各参与方之间再次交接时还要清理旧数据。

密钥一旦被数据持有方获知，就不能假设其导出后忘记了旧 key/IV。论文明确承认，它可保留这些信息、解密或伪装通信；安全依赖 GPU 端完成密钥轮换，使旧能力失效。Figure 3 中应用“Key Invalid”的软件标记不能独自证明恶意方已失去能力。

§6.3 解释轮换命令被 Host 丢弃时 orchestrator 等不到完成，因而不会继续。这体现失败时停止推进的原则，但还需要完成记录不可伪造或重放，并确实表示设备端生效。一个 IRQ 或普通共享页 ACK 不足以证明该密码撤销屏障完成。项目即使不迁移密钥，也有映射/queue/launch 能力的等价撤销问题。

## 9. 最关键的授权边界：数据持有方拥有整卡能力

§6.1 原文明示，数据持有方在持有 GPU 时“has access and control to the entire GPU”，可 dump GPU memory，读取模型，也可修改模型。论文通过先清 dataset buffer 保护前一方原始数据，并把模型推断/模型改写引发的相关风险置于范围外。§9 把“限制 CE 仅访问 dataset buffer”列为需改固件的未来工作。

因此它不是多个恶意 VM 在 GPU 上各自独立任务的细粒度隔离设计。对本项目，不能给 Client 一个通用设备能力，再相信其只会使用约定 ioctl 写入自己的缓冲；需要由可信 Proxy 按真实对象、HPA、权限、GPUVM及生命周期实施最小授权。

模型修改还可能改变后续数据处理，不能将一切主动改写都简单归为被动模型推断。本轮未复现攻击，但论文的“每次重新载入 kernel，所以不能植入 gadget”不足以单独排除跨交接仍在运行的旧任务、持久队列、被改写的数据结构或影响后续计算的状态。它给出安全讨论而非任意恶意设备状态的完整证明。

## 10. 清理范围与状态连续性的张力

保持模型和 GPU 状态的性能目标，与消除上一 Client 的敏感影响之间存在边界：需要明确哪些内容允许共同保留，哪些内容属于应撤销/清理的私有状态。清空 dataset buffer 不自动擦掉 optimizer state、梯度、workspace、寄存器、spill/context、固件队列中可能残留的派生信息；模型本身承载训练信息又被论文排除在部分机密性目标之外。

不能据此断言所有这些缓冲都在原型中泄漏。准确结论是论文没有逐类提供隔离/清理证据，本轮也没有取得 artifact 验证。项目可以借鉴上一批 GPU Taint Tracking 的生命周期视角，但应先建立明确的保留/销毁契约，再选择整域清理、可信 reset 或可验证的选择性清理。

## 11. 实现与实验条件

§5：NVIDIA open driver 560.35.03，Host Linux 6.12.0-rc1，TDX patch `2024-11-08-build-442`；作者报告修改 4,746 LoC。这是改动量，不是完整可信软件大小。§7：双 Xeon Silver 4516Y+（2.2 GHz、每颗24核）、256 GiB RAM、H100；CVM 各4核/8 GiB，Linux 6.8.12 加地址解析修复，virtio-net-pci，OpenSSL 网络对照。原文写 Ubuntu 24.0.1 LTS，本报告保留其版本写法而不自行补写一个已经核实的系统 release。

性能采用4、20、100、500 Mbps和 uncapped 网络，后者实测约1 Gbps；合成传输每组10次取平均。不是100 Gbps/RDMA/GPUDirect 网络实测，也不是 Arm GPU 或当前 vmshm 项目性能。对真实 GPU TEE 的平台测量很有参考意义，但不能据其功能原型对未测试平台作完整安全证明。

## 12. 固定成本与数据复制成本必须分别看

Table 1：单程 MUX 切换约143–148 ms，往返约290–300 ms；密钥/上下文约16 KiB，网络通信约33–49 ms。512 MiB 一次请求：清理0.533 ms、导出0.206 ms、切出147.968 ms、导入0.322 ms、读数据288.922 ms、GPU写349.278 ms、导出0.131 ms、SSL44.112 ms、切回147.727 ms、导入0.303 ms，总978.969 ms。

上述约0.34秒管理/清理/上下文开销和约0.64秒数据读取/写入不能都称为常数。4 MiB 的总时间333.673 ms，512 MiB 为978.969 ms；随数据量基本不变的是管理部分，不是完整请求延迟。GPU写入约349 ms也不能当作 H100 原生 PCIe 理论带宽，路径包含机密复制等软件工作。

Figure 5/Table 1 没单列 Figure 3 中的 key rotation 项；不能从总数自行确认轮换被计入哪一栏，也不能声称它必然遗漏。本轮应保留这一计量待核项，待 artifact 中具体计时边界可用时验证。

## 13. 合成传输结果：倍率取决于基线网络

Figure 6 中512 MiB：4 Mbps 为1,115,958→约1,012 ms（1103.15倍）；uncapped 为4,435→约980 ms（4.53倍）。小缓冲并不总有收益：4 MiB/500 Mbps 为273→339 ms（0.81倍），uncapped 为202→339 ms（0.59倍）。不能只引用最大倍率并称所有数据复制都加速。

§7.4 对10 Gbps网络的约2倍收益是用假设40%密码开销及1 GiB缓冲外推，不是直接测量。论文将 TDISP 描述为协议级加密时，也应区分接口安全管理协议和实际链路/内存保护机制；本篇没有实现或验证 TDISP，也不据未来工作文字推导任意设备已经具有相应隔离能力。

## 14. llm.c：传输提速不等于整个训练同倍率提速

作者修改 llm.c 的 dataset loader，用预训练 GPT-2 做训练逻辑相同的微调，数据缓冲512 MiB，训练本身约1230秒。Table 2 的 Tx percentage 是传输占训练加传输总时间。以下总时间/倍率为本报告据表中两列相加计算，非本轮新测量。

| 网络 | 原方案训练+传输（秒） | Travelling训练+传输（秒） | 总时间倍率 | 总时间减少 |
| --- | --- | --- | --- | --- |
| 4 Mbps | 2345.88 | 1231.27 | 1.905倍 | 47.51% |
| 20 Mbps | 1462.23 | 1230.42 | 1.188倍 | 15.85% |
| 100 Mbps | 1291.53 | 1231.59 | 1.049倍 | 4.64% |
| 500 Mbps | 1246.59 | 1230.65 | 1.013倍 | 1.28% |
| uncapped | 1236.70 | 1232.44 | 1.0035倍 | 0.34% |

uncapped 单看传输7.34→0.98秒，节约6.36秒；考虑训练列差异后，合计节约4.26秒。不能把1103倍或4.53倍直接作为 llm.c 训练提速。本文也没有将相同计算路径视为模型质量、逐位一致性或恶意参与方下训练完整性的独立验证。

## 15. 与项目相关论文的差别

| 工作 | 可借鉴机制 | 不能直接继承的保证 |
| --- | --- | --- |
| PORTAL | 可信管理、设备交接顺序 | 一般设备交接不自动提供服务内任务隔离 |
| ACAI / PhantomMap | 身份、真实页、映射生命周期一致性 | 密钥有效不能代替逐对象物理页授权 |
| CAGE / StrongBox | GPU执行与管理边界 | 不因设备已可信就默认所有共享Client彼此隔离 |
| GPU Travelling | 连通性与授权分层、上下文清单、撤销屏障 | 原型把整卡控制交给数据方，不是最小权限共享 |
| Devlore / 中断安全研究 | 真实到达及虚拟注入约束 | 本文eventfd切换未实现同等中断可信性 |
| GPU Taint Tracking / MOLE | 残留/传播和固件内安全边界 | 清dataset buffer不独自证明所有派生状态已清 |

本篇对项目两大部分均有用：第一部分参考持久handler、保存状态、合批降低切换成本；第二部分明确较强研究问题——在恶意Client之间，保留高性能共享的同时，严格绑定启动能力、合法映射、真实终态、完成接收者和安全复用。

## 16. 项目设计推导：固定可信设备 owner，收窄 Client 能力

维持既定假设：RMM认证原始Client，可信ProxyRealm统一控制SMMU，映射期核查对象/真实HPA/权限/生命周期，软件IPA→HPA合成受保护GPU Stage-1，其他设备保留硬件Stage-2。Proxy可作为固定设备owner，Client经认证队列提交授权对象与任务，不必获得通用GPU密钥、root控制或整卡MMIO。

对每次提交，复用GPUVM、private plan/snapshot、native fence和cookie/epoch，确保最终启动的命令与已授权快照一致。上下文包含的不只是GPU地址，还包括队列、序列、semaphore、fault和reset代际；缓存命中或旧上下文恢复不能跳过所有权/生命周期验证。以上是项目设计建议，不声称已实现。

撤销必须使旧启动能力失效，确认在途工作达到受控终态并完成所需失效/清理，再允许新授权。异常时无法证明撤销或清理完成，就隔离相关资源；不能仅用旧Client返回“已移交”、Host路由已改或一次IRQ作为屏障成功的证据。

## 17. 中断通信与可验证负例

将物理IRQ作为检查触发，Proxy读取权威设备/驱动终态后，向绑定的Client实例/session/job/device epoch发布逻辑通知。资源清理及可复用状态单独维护。对映射撤销、reset和A→B→A切换，旧fence/旧IRQ/迟到ACK不能推进新代任务，也不能释放新对象。

优先负例包括：有通信能力却访问非授权对象；提交后更改命令页；移交前排入延迟GPU任务；旧上下文/nonce/semaphore重放；撤销失败但仍给新Client授权；IRQ路由与DMA归属错配；只清dataset却复用含派生秘密的workspace；reset后的旧通知。需要逐项给出阻断点和状态证据，论文未做的验证不能从性能图中推断通过。

## 18. 尚未完成的材料与统一记录

作者Zenodo artifact真实入口已确认，但本轮连接超时，未取得代码/归档清单，因此不对4,746行修改的锁、nonce、DMA静默、清理覆盖和迁移状态验证作已审计结论。后续取得固定归档后再增加源码分析，不把NVIDIA上游源码替代作者修改。单Host原型已实测；跨Host PCIe fabric、多GPU、CUDA上下文迁移、orchestrator冗余均属论文未来工作。

本轮另取得3LegRace（PoPETs2022）完整21页PDF，已开始阅读但未完成独立分析和发布，不计完成；其TEE与不可信GPU的数据分解路线与本篇不同，后续单独研读。ZeroKernel、SEGIVE等仍缺足够全文，继续保留待办。

统一记录：15页全文、九页图像、正式书目及artifact入口核验｜glmark改动前未测→本版未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜研究批次batch76；无硬件/模型/攻击/构建run-id，无新增运行PASS｜保留论文机制与证据边界，项目建议待实现验证。
