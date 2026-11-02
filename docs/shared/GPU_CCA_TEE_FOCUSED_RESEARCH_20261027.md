# Arm CCA / TEE 共享 GPU 保护：聚焦调研与研究定位

日期：2026-10-27。本文是研究分析，不修改当前实现要求或发布状态。

后续补充见 [CCA / TEE 加速器调研续篇](GPU_CCA_TEE_FOLLOWUP_RESEARCH_20261027.md)：新增 ASGARD、TZ-LLM 原文分析，复读 ccAI，补充 MyTEE 及 AvaGPU、LEAP、XpuTEE、BarriCCAde 等候选；已读原文与摘要证据分别标注。下文第 10 节的候选状态保留为本篇形成时的记录，最新状态以续篇为准。

## 1. 调整后的结论

本项目应沿“可信设备访问 → GPU 任务保护 → 共享服务 → 中断与完成语义 → 撤销回收”组织相关工作。PORTAL、CAGE、ACAI 是主干；StrongBox 提供 Arm GPU TEE 的前置路线；Devlore、CAEC、TEEtime 则补足此前清单中最关键的后续研究。

其中最直接影响研究定位的是两个新结果：Devlore 已系统研究 CCA 设备中断真实性与注入规则；CAEC 已实现受保护、可证明身份的跨 Realm 共享内存，但在 §8.3 明确把通知的来源认证、隔离和同步列为开放问题。因此，“可信中断”或“跨 Realm 安全共享内存”单独作为贡献都不够准确。更值得推进的是：**多 Client 共享 GPU 时，证明设备事件、作业状态、Client 通知与资源回收之间的授权和生命周期一致性。**

这里的“值得推进”是基于已读论文的研究判断，尚不是首创性证明，也不是对本项目存在可利用漏洞的判定。

## 2. 项目模型与阅读边界

采用用户确认的平台假设及 [平台假设文档](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)：可信 ProxyRealm 持有完整 GPU 驱动并统一控制 SMMU；RMM 认证实际 Client 身份；平台保护实际页表、root、关键 MMIO 和受保护内存，阻止未授权 CPU/DMA 修改；固件加载及重载可信。

GPU 只使用硬件 Stage-1。可信软件在建立映射时检查 Client、对象、实际 HPA、权限和生命周期，完成 IPA→HPA 翻译并安装直接指向 HPA 的 Stage-1 PTE；执行期由硬件持续限制访问。其他设备可继续使用硬件 Stage-2。**映射时检查替代的是 GPU 的 Stage-2 解析与授权路径，不替代执行期隔离、撤销、TLB/cache 维护及安全回收。**

RK3588/OpenCCA 是模拟与性能验证载体。本报告不因实验板缺少目标硬件能力而否定架构，也不把板端结果当成已证明全部平台假设。

威胁主体包括恶意 Host、恶意 Client，以及可提交任意合法指令和恶意参数的 Client GPU 工作负载。可信 Proxy 的代码可信，不意味着任意 Client 输入、GPU 可写状态或来自 Host 的提示可信。调度公平性、完全消除时序侧信道和物理攻击不自动包含在当前目标中。

## 3. 聚焦文献地图

| 工作 | 体系与核心对象 | 对本项目的价值 | 不能直接推导的结论 |
| --- | --- | --- | --- |
| [StrongBox，CCS 2022](https://fengweiz.github.io/paper/strongbox-ccs22.pdf)；[TDSC 2024 扩展](https://compass.sustech.edu.cn/paper/strongbox-tdsc24.pdf) | TrustZone、Arm GPU 可信执行与动态保护 | GPU 内存、MMIO、启动和清理必须共同受控 | 不能直接证明多 Client GPUVM 并发隔离 |
| [CAGE，NDSS 2024](https://www.ndss-symposium.org/wp-content/uploads/2024-763-paper.pdf) | CCA GPU 扩展；不可信大驱动、可信 Monitor/shadow task | 任务执行区间的冻结、真实映射与清理；缩小驱动 TCB 的另一种取舍 | 不是完整驱动可信 Proxy 模型；任务槽共享不等于恶意 Client 并发共享已证明 |
| [ACAI，USENIX Security 2024](https://www.usenix.org/system/files/usenixsecurity24-sridhara.pdf) | CCA PCIe 加速器；设备身份与 CPU/DMA 映射一致性 | 授权必须落到真实物理页与真实请求主体 | Proxy 可访问 A/B 两方页面，不代表 A 可请求访问 B |
| [PORTAL，IEEE S&P 2025](https://mainarke.github.io/assets/papers/sp25_sang.pdf) | 可信 System Realm 管理设备访问与运行期交接 | 最接近可信 Proxy 服务和统一 SMMU 管理路线 | 设备交接不等于共享 GPU 作业级隔离；虚拟转发不等于中断来源认证 |
| [MOLE，CCS 2025](https://fengweiz.github.io/paper/mole-ccs25.pdf) | GPU 内嵌 MCU 对 GPU TEE 的攻击 | 固件及加载、重载过程必须进入信任链 | 不可信初始化路径的攻击不能直接套成本项目已复现漏洞 |
| [Devlore，RAID 2026 / 扩展版 v3](https://arxiv.org/abs/2408.05835v3) | CCA CVM 的设备中断保护 | 物理中断来源、GIC 配置、顺序/优先级与 ACK 生命周期 | 真实 GPU IRQ 不能独立证明某 Client 作业成功或 DMA 已停止 |
| [CAEC，EuroS&P 2026](https://arxiv.org/abs/2512.01594) | 可证明身份的跨 CVM 机密共享内存 | Client–Proxy 共享控制区及实例身份；通知保护的明确研究缺口 | CPU 共享授权不自动授予 GPU DMA；授权消息发送者仍可能提交恶意语义 |
| [TEEtime，TCHES 2026(1)](https://doi.org/10.46586/tches.v2026.i1.135-160) | TrustZone 下 normal-world domains 的中断隔离 | 配置、状态、路由三类不变量；明确支持 proxy 设备模式 | 不是 CCA GPU 系统；proxy 上层 API 安全仍由服务域承担 |
| [PhantomMap，NDSS 2026](https://www.ndss-symposium.org/wp-content/uploads/2026-f201-paper.pdf) | GPU 辅助内核利用、分配与实际映射脱节 | 最终 PTE 的 HPA、backing 与对象生命周期复核 | 原 Mali 驱动攻击不是 Panthor 已验证漏洞 |

这是一组机制上的互补关系，不能在没有作者证据时称为各论文间直接继承或正式扩展链。Devlore 早期标题为 “Extending Arm CCA to Integrated Devices — A Journey Beyond Memory to Interrupt Isolation”，与当前 “Device Interrupt Protection for Confidential VMs” 属于同一工作，不重复计数。

## 4. PORTAL、CAGE、ACAI 的关键比较

### PORTAL：可信服务是起点，还需要原始 Client 授权

PORTAL 把厂商可信的设备服务放入 System Realm，保护 SMMU 配置与命令路径，以 CPU RMM Stage-2 和设备 SMMU Stage-2 建立细粒度保护。其命令队列是 RMM/System Realm 的受控接口，不能据此把任意 Client 可写队列视为可信命令。

运行期设备交接使用 OCCUPIED、TRANSITION、DETACHED 等状态，先撤旧 MMIO 权限，再切换设备映射，最后授予新 owner；设备分配历史可进入测量。因此 PORTAL 并非“启动后永久独占”。它展示动态时分交接，但没有因此证明本项目这种多 Client 经同一驱动并发提交任务的语义隔离。

本项目可继承可信服务管理思想，同时把检查继续前推到原始 Client：RMM 认证的 Client 实例 → session → 对象 → backing/HPA → GPUVM → 提交作业。只检查“请求来自 ProxyRealm”会把所有 Client 折叠为同一主体。

PORTAL §6.6 描述 SMMU fault IRQ 经 Host 虚拟转发至 System Realm。这解决功能路径，不应被扩写成已完成 Devlore 式物理中断真实性保护。

### CAGE：任务级临界区有价值，但 TCB 选择不同

CAGE 保留不可信 GPU 软件栈，由小型可信组件重建真实数据和映射，使用每 Realm GPU 保护视图。执行前锁定控制面、映射和任务相关状态，确认设备状态后可信启动；完成后清理 cache/TLB。它通过任务槽支持共享，应区别于 StrongBox 更粗的独占区间，也区别于同时运行多个恶意 Client GPUVM 的证明。

本项目已经选择完整驱动可信，没必要为追求小 LoC 复制整个 shadow/stub 架构。应借鉴的是：最终使用的真实页表受保护；启动前的验证到执行之间没有未授权可变输入；完成、撤销和下一次使用有明确屏障。

公开代码需要单独评估。固定提交 `c79106486eae0e55b49c3f98c0d4bb01a3d3a91b` 的 performance prototype 中，`check_code_integrity()` 的失败 ERROR/panic 被注释且返回 0，完整代码缓冲区定位仍有 TODO；相关 HMAC helper 也存在长度/初始化静态问题。它说明不能把论文保护目标或性能原型直接当成已审计的生产实现；本报告未运行该代码，未据此声称论文整体被攻破。

### ACAI：把身份和映射归属变成可检查的不变量

ACAI 强调设备身份不可伪造、独占 owner、CPU/device 的 IPA→PA 一致，以及避免受保护物理页的非法别名或重叠。其 PCIe 身份和链路机制不必照搬到集成 Mali，但一致性原则适用。

迁移到共享 Proxy 时应明确：设备 owner 是 Proxy，数据授权主体仍是各 Client。GPU 页表由 Proxy 安装，只证明安装者可信；还要证明该 PTE 对应的 HPA 在当前对象 generation 下被当前 Client 授权。软件合成 Stage-1 可以执行这些策略，不能只按 GPU VA 或“这是共享池页面”决定合法性。

## 5. 后续工作带来的新定位

### Devlore：不要重复提出已存在的“可信 IRQ 注入”

Devlore 将受保护物理 IRQ 路由到可信 Monitor，记录真实到达事件；Host 继续调度和提出虚拟注入请求，RMM 根据受保护记录检查 vGIC LR。它还保护 GIC 配置、可见状态和 ACK，处理优先级及有限 LR 窗口内的顺序，而不是仅给中断加计数或规定全局严格 FIFO。

在本文威胁模型下，其适合构成 GPU→Proxy 的物理事件可信层。不过 GPU IRQ 可能合并多个事件，也可能包含 fault、idle 或多个 job 完成，不能假设一 IRQ 对一 job。可信物理事件是重新读取可信设备状态的依据，而不是释放任意 Client 页面或发布成功的充分条件。

详见 [Devlore 精读](GPU_DEVLORE_DEEP_REVIEW_20261027.md)。

### CAEC：共享内存安全与共享通知安全存在明确边界

CAEC 使同一 Realm PAS 页面经 RMM 授权映射到多个参与 Realm；RMM 的 APT 记录 Provider/Consumer 关系和权限，以证明绑定的 Realm 标识避免 Host 替换通信对端。撤销涉及 Consumer RTT 与 TLB，不只是删软件记录。

其 §8.3 明确指出 CSM 信号的 strong security、isolation、provenance 尚待研究。这和 Client–Proxy 服务非常契合，但缺口要表述完整：源认证、事件的对象/代际绑定、恶意对端的协议语义，以及撤销后的旧通知不能改变新对象。

作者 artifact 的身份 tag、权限安装和参数检查还存在值得复核的实现差异，不能把论文层新鲜身份承诺直接当成代码已证明；详见 [CAEC 精读与静态审查](GPU_CAEC_DEEP_REVIEW_20261027.md)。

### TEEtime：物理中断隔离之后，服务语义仍属于 Proxy

TEEtime 要求 Rconf（配置归属）、Rstate（pending/active/retired 状态归属）、Rroute（正确路由）。针对共享 GIC 寄存器，它用可信 GIC Guard 做每 INTID/位的检查，不能仅保护整个 MMIO 页。

它明确讨论 proxy access：物理设备中断只到 owner domain，再由 owner 提供 API 与通知。这恰好说明本项目需要分开证明“物理 IRQ 属于 Proxy”和“这条逻辑完成只属于 Client A 的 job J”。详见 [TEEtime 精读](GPU_TEETIME_REVIEW_20261027.md)。

## 6. 建议保留的两个研究部分

### 第一部分：Arm GPU 直通与共享的实现及性能

展示单 Realm 设备接入、可信 Proxy 上的多 Client 提交、GPUVM/对象虚拟化、驱动兼容和生命周期，然后解释 RPC、映射、调度、中断、完成路径的开销及优化。区分功能实现、正确性和性能结果，不以安全方案的存在自动推导安全证明。

性能对照优先使用同频率、同分辨率、同场景集的 Native N 进程对 N 个 Client。当前文档的历史优化基线为 1405，最新完整同频矩阵单 Client 720p 为 1395；不同批次不可替换成论文之间的横向排名。本次没有重测。

### 第二部分：恶意 Client 下的 GPU 任务隔离

主线可称为“内存与异步完成的联合隔离”。内存保证 job 只能使用当前授权页面；异步完成保证只有正确 job 的可信终态才能触发对应通知与后续状态转换；回收保证授权撤销后旧 GPU 执行、cache/TLB、固件队列与旧通知不会影响新 owner。

这样组织优于把“内存隔离”和“中断隔离”写成互不相关的两套开关，因为伪完成或旧完成可能触发提前回收，最终变成内存隔离失效。

## 7. 建议形成的四层机制

| 层次 | 要证明什么 | 可继承的基础 | 本项目需补充的边界 |
| --- | --- | --- | --- |
| GPU→Proxy 物理事件 | IRQ 来源、配置和路由未被 Host/其他域伪造 | Devlore / TEEtime | 明确目标平台物理 IRQ 保护接口；不能只信 Host eventfd |
| Proxy 作业状态 | 当前 job 的状态来自受保护的设备/固件语义和正确对象 | 可信驱动、native fence、任务对象 | 审核恶意 GPU 指令可写的计数器/状态是否能伪造成功 |
| Proxy→Client 逻辑通知 | 源、目标、session、job 与通知代际一致 | RMM xshm 受保护端点、pending/armed/ACK_ARM | 批处理、重复、乱序、关闭与重开时保持幂等与代际拒绝 |
| 撤销与安全回收 | 终态之外还确认无在途访问和旧映射 | 映射 owner/generation、撤销与 TLB/cache 维护 | close/reset/cancel 的统一屏障；旧 completion 不能解锁新对象 |

建议把授权上下文显式关联为：Client 实例、session generation、GPUVM/root、对象及 backing generation、job/fence、device epoch、通知 epoch。字段不必全部进入每条消息，可在可信表内保存强引用并通过不可混淆的句柄查找。核心是生命周期绑定，而不是机械增加 token 或每 RPC 的 MAC。

可信终态可分 SUCCESS、ERROR、CANCELLED 等；终态与 GPU/DMA quiesced、映射已撤销、页面可复用是不同事实。错误或取消必须能完成清理协议，但不能伪装为成功，也不能仅据超时认定设备已停止。

若共享链路已由平台保护且源身份由 RMM 给出，MAC 不应是默认补丁。真正需要核验的是：被认证的发送者是否有权宣称这件事，通知的 job/对象是否仍为同一代，以及接收端能否从权威状态恢复而不是数中断次数。

## 8. 与当前代码衔接：已有基础和待证明问题

| 代码入口 | 已观察到的基础 | 本次研究判断 |
| --- | --- | --- |
| `opencca/tf-rmm/runtime/core/xshm_irq.c` | 拒绝 Host 占用保留 LR、拒绝其他 LR 重复受保护 INTID；可信端注入保留槽 | 已有受保护通知基础，不能写成“当前完全没有中断认证” |
| `opencca/tf-rmm/runtime/core/xshm_endpoint.c` | 可信 pending/armed 序列及 ACK_ARM | 应沿用并明确状态机；追加关闭、代际及合并通知的证明 |
| `Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c` | session 查询使用实际 channel 的 Client VMID | 已有源绑定；需区分 VMID 与不可混淆的 Realm 实例生命周期 |
| `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_sched.c` | 完成路径消费 sync seq/status，存在正常与提前观察完成两条路径 | native fence 对象可信，不自动证明工作负载可写计数不可伪造；需审核权限和固件语义 |

最后一项是静态审计问题，不是已复现攻击。需要先明确哪些计数/状态页可被什么 GPU 地址空间写入、谁更新、固件如何验证，再决定是加强映射权限、采用固件可信状态、增加交叉检查，还是已有机制足以排除。

## 9. 后续验证设计与贡献表述

后续实验应以可观察的不变量为中心，不直接修改本文未验证的机制：

1. Host 伪造、重复、乱序通知或 LR：不能产生未经权威 job 状态确认的 SUCCESS，不能清除其他 Client 的 pending。
2. Client 伪造 owner、job、session、旧 generation：即使句柄数值复用也不能操作新对象。
3. 中断合并、job 批完成、延迟 ACK：允许功能上等价的调度，Client 从状态表恢复全部结果，不依赖一中断一作业。
4. cancel/error/reset 与正常完成竞争：同一 job 只发生一次合法终态转换；清理不误伤其他 Client。
5. unmap/close/reopen/页面复用并发：撤销完成前不能再分配给新 owner；撤销后旧 PTE/TLB/通知无效。
6. 恶意 GPU 写可达同步页：验证伪计数是否被拒绝，或由更可信证据交叉验证；先建立受控复现，不把猜测记成漏洞。

安全度量记录接受/拒绝、状态迁移、页面复用时刻、受害 Client 正确性和恢复结果。性能分别测物理 IRQ 路径、Proxy 作业确认、跨 Realm 通知、撤销屏障及端到端吞吐；同时报告 tail latency、并发数和基线条件。不得把 CAEC 对加密通道的倍数套到现有明文 vmshm，也不得把 Devlore 17 项 glmark2 的 0.06% 直接对照本项目完整 33 场景分数。

可用的研究表述是：“在可信 GPU 服务 Realm 下，建立恶意多 Client 的映射授权、异步完成和回收生命周期的一致性机制，并在合并中断、撤销与复位并发下验证。”暂不使用“首个可信中断”“首次机密跨 Realm 共享”或“完整消除 GPU 侧信道”等表述。

## 10. 证据范围与未完成项

本次重读 PORTAL/CAGE/ACAI 原文核心设计及评估，新增取得 Devlore 当前扩展版、CAEC v5、TEEtime 原文，完成机制与实验边界分析；对 CAEC 作者 artifact 的固定提交做了定向静态审查。并非对所有源文件、证明或所有后续论文的穷尽审计。

`Building Confidential Accelerator Computing Environment for Arm CCA`，DOI [10.1109/TDSC.2025.3615787](https://doi.org/10.1109/TDSC.2025.3615787)，已核正式元数据，卷期为 2026-01；尚未取得全文，因此不声称掌握其相对 CAGE 的新增机制。ASGARD、BarriCCAde 等仅作为后续检索候选，不以标题推导结论。

Devlore 作者入口未确认完整实现仓库；TEEtime 本次未完成独立公开代码核验。CAEC 公开 artifact 与论文身份/权限承诺有需要复核的差异，详见精读。此前 63 条泛 GPU 文献逐篇任务保持暂停，不改变其完成计数。

原始来源、PDF SHA256、固定代码及抓取结果保存在 `build/cca-gpu-focused-study-20261027/`；关键引用为各节原文 URL。原来的综合设计建议见 [安全设计审查](GPU_SECURITY_DESIGN_REVIEW_20261026.md)，本报告补充后续文献和更精确定位，不覆盖既有测试事实。

统一记录：聚焦 CCA/TEE GPU 文献与研究定位｜历史优化基线 1405、最新同频单 Client 1395 → 本次未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件 run-id、无新增运行 PASS；仅文档与静态证据｜保留研究建议，机制实现及攻击验证待后续任务。
