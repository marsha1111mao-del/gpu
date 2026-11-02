# PORTAL：可信服务 Realm、明文设备 I/O 与运行期设备交接

研读日期：2026-10-27。依据 18 页作者版本正文，重点 §§3–6 的威胁模型、配置保护、命令处理、设备交接与实验。本文区分目标平台假设、功能原型与性能原型，不用实验板的硬件能力否定设计，也不把模拟性能当作目标硬件完整安全证明。

## 1. 书目信息与原文

| 项目 | 内容 |
| --- | --- |
| 正式标题 | PORTAL: Fast and Secure Device Access with Arm CCA for Modern Arm Mobile System-on-Chips (SoCs) |
| 作者 | Fan Sang、Jaehyuk Lee、Xiaokuan Zhang、Taesoo Kim |
| 会议 | IEEE Symposium on Security and Privacy 2025，正式页码 4099–4116 |
| DOI | [10.1109/SP61157.2025.00013](https://doi.org/10.1109/SP61157.2025.00013) |
| 作者原文 | [mainarke.github.io PDF](https://mainarke.github.io/assets/papers/sp25_sang.pdf) |
| 固定 PDF SHA256 | `6efeaf10bcc39a46a789363db9affc14f3f229f04f2f3a8f59789e59deb054f0` |
| 阅读范围 | 正文 §§1–7，重点 §§3.2–4.6、5、6；未将所有引用文献当作已读 |

## 2. 研究问题：隔离和传输加密承担不同责任

普通 CCA 的设备不能直接访问受保护 Realm 数据，常见方法使用不可信 bounce buffer 并加密。移动 SoC 的统一内存及频繁 CPU–设备通信会放大额外复制、软件加密和切换开销。

PORTAL 的核心选择是在特定封装与物理威胁假设下，通过严格访问控制保护明文设备通信。它没有证明“所有机密计算都不需要内存加密”，也没有把 CCA 规范本身改写成必须使用某种软件 AES 通道。其软件 AES-GCM 对照只是实验基线。

论文同时解决两个配置问题：普通 SMMU 不知道 Realm 身份；SMMU 页表和控制面原本在不可信 Host。仅把缓冲区标记为 Normal PAS 会暴露数据，因此需要保护 CPU/设备两边的视图、映射和管理逻辑。

## 3. 威胁模型、假设和可信基

攻击者控制 Normal world 和 Secure world，包括 Host OS、VMM、共租 Realm 及不可信设备请求，可伪造资源返回、创建重叠映射或提交恶意设备任务。可信根包括 Root Monitor、RMM、RME/GPC/SMMU 和经证明确认的 System Realm；使用设备的 Realm 内部软件也承担本 Realm 的保护责任。

目标为集成设备与统一内存的 Arm SoC。论文假设封装内通信安全、集成设备身份不可伪造，排除物理探测、Host/Hypervisor DoS、推测与微架构侧信道。它还依赖可信启动建立真实 MMIO/多路复用配置及合适的设备固件状态。对外部 PCIe 讨论 IDE，不能把该条件默认为任意集成 GPU 已有链路加密。

System Realm 由可信厂商提供，其他 Realm 可通过证明核对代码测量。测量证明装载了期望软件，不能单独证明代码没有漏洞，或每次动态请求都符合授权。

## 4. 保护视图：GPC 粗隔离，Stage-2 细隔离

PORTAL region 对授权实体表现为 Normal PAS，以允许明文访问；对未授权实体表现为 Root PAS，从而使其访问在 GPC 被阻断。两种 GPT 视图分别称 P-GPT 和 N-GPT。

| 边界 | 保护机制 | 需要同时满足的条件 |
| --- | --- | --- |
| Realm 与 Host/Secure world | Realm 执行时切 P-GPT，退出切 N-GPT | 视图转换和旧 TLB 必须一致 |
| 不同 Realm | RMM 管理的 CPU Stage-2 | Normal PAS 不意味着任何 Realm 都有合法映射 |
| 不同设备 | 受保护 SMMU Stream Table、I/O Stage-2 | SID/owner 和真实 HPA 不能被替换 |
| SMMU 自身数据 | 表放在 System Realm 保护区；SMMU 可读取 | CPU 与 DMA 都不能修改权威页表 |
| SMMU 控制寄存器 | 仅 System Realm 拥有真实 MMIO | 包括关闭翻译、替换 root 等绕过口 |

GPT 不覆盖的区域必须保持 P/N 两种视图一致；RMI/RSI 更新同步作用于两者，GPT 改动时清理 CPU/SMMU 的相关 TLB。由此可见“已保护 PTE”仍不够，还要保护 root、控制寄存器和失效路径。

本项目的软件 IPA→HPA 翻译并合成 Stage-1 可以替代其设备 Stage-2 解析路径；迁移时应保留实际 HPA、身份、权限、所有权与生命周期不变量，而非机械要求再加一层相同页表。

## 5. System Realm：降低最高特权层的管理复杂度

SMMU 管理逻辑在 System Realm EL1，RMM/Monitor 保留身份、映射及切换锚点。System Realm 申请 SMMU 时，RMM 检查其测量；Host 交还 MMIO 页后，RMM 检查实际 HPA 是否匹配申请的真实设备地址，再建立受保护映射。

这避免 Host 用仿真设备或假的 SMMU MMIO 替换真实设备。真实地址的来源仍需可信，本项目不能直接信任 Host 临时提供的 DT 内容。

论文有“保留核心 TCB”表述，其准确含义是避免把完整 SMMU 管理栈放进 EL2/EL3；它仍实际修改 RMM 和 Monitor。Table 3 给 TF-A 96、RMM 784、System Realm 550、Guest kernel 230，合计新增 1,660 LoC。这个数是新增代码量，不是全系统可信代码总量。System Realm 的错误也可能破坏被其管理的数据保护，即使不直接取得 EL2/EL3 权限。

## 6. 命令队列：源认证和实际映射检查同时成立

每个 Realm 有独立命令队列，Host 提供页面，RMM 建立受保护映射；队列仅供 RMM/System Realm 使用。请求通过可信接口进入 RMM，RMM 保留实际调用 Realm 的 VMID，并将其关联到对应队列。

System Realm 消费请求时检查目标 PORTAL region 的真实 HPA、owner VMID 和请求方一致性；反向映射用于拒绝其他 I/O 页表已占用的非法重叠，然后更新真实 SMMU 表。这里不是“请求来自一个 Realm，所以可以信任请求所有字段”。

原文 §4.4 对“Realm 请求通过 RMI 进入 RMM”的接口命名有不够清楚之处；表中 Realm-facing 接口使用 RSI。没有源码核验前，不据该措辞虚构一条 Realm 直接调用 Host-only RMI 的实际实现路径。安全上关键是 RMM 建立来源绑定，而非使用某个消息字段自报 VMID。

本项目的 Proxy 是多个 Client 共用的设备 owner，因而还需保留原始 Client 实例、session、对象及 backing generation。只验证“Proxy 拥有全部页面”会丢失 Client 间授权边界。PORTAL 的队列来源绑定原则适用，但其 Realm–设备配对不能自动承担服务内部恶意 Client 隔离。

## 7. DMA 建图与按需处理

Realm 以 GPA 列表、长度及设备 ID 请求 DMA 区。RMM 通过自己的 Stage-2 解析 HPA，确认页原本归当前 Realm，再改变相关 GPT 视图；System Realm 检查后建立设备映射。不是让 Host 自报一串 HPA 即直接信任。

为减少设备初始化中暂不使用的 metadata 映射触发切换，论文延迟执行 SMMU 命令，在设备遇到无效 DMA 映射故障时唤醒 System Realm。其性能价值来自合并管理工作，不是放宽授权。

迁移到共享 GPU 时，fault 只能触发对已授权待处理映射的核查。不能仅按故障地址补映射，更不能在对象已撤销后恢复旧映射；fault handler 仍需绑定 GPUVM、owner、generation、权限和当前状态。该段属于项目设计推导，尚未判定 PORTAL 原型有可利用 fault 漏洞。

## 8. 运行期设备交接：状态机和顺序是安全机制

Figure 10：B 请求附加 A 所占设备后，RMM 将 OCCUPIED 改为 TRANSITION 并记录目标；通知 A 执行 detach；A 返回后先撤去 A 的 CPU MMIO Stage-2，状态改 DETACHED；System Realm 切换 Stream Table/I/O root 和 VMID；确认后 RMM 才把设备设 OCCUPIED 并把 MMIO 授予 B。

原文明示一个危险交错：先给设备 B 的映射却让 A 仍能写 MMIO，A 就可能利用 B 的数据访问权限。因此新 DMA 授权与旧启动权限不能交叠。

这支持动态时间共享，但没有因此证明多个恶意 Client 的作业可以同时执行。原文列出的 old-owner detach 通知和软件返回，也不能单独成为设备完全停止、固件队列排空、片上状态清除的充分证据。对于本项目的恶意 Client，可信 Proxy 应依据受保护的驱动/设备状态确认停止；不能相信 Client 的“已停止” ACK。本轮没有复现 PORTAL 的该方向攻击。

## 9. 证明与中断：历史可信不等于完成可信

设备动态附加/分离记录由 RMM 维护并扩展进 REM，远端可核对设备历史。日志完整性有助审计，但不能替代事前拒绝非法映射或停止在途访问。

§6.6 中 SMMU fault IRQ 先由 VMM 处理，再虚拟转发给 System Realm。该描述实现唤醒通路，没有给出 Devlore 对受保护物理到达记录、vGIC LR、优先级及 ACK 的完整认证协议。不能把虚拟转发自动称为可信中断。

即使补上 Devlore，真实 IRQ 也只说明设备事件真实到达，不等于某 Client 的特定 job 成功。项目需要在 Proxy 内再次读取权威终态，再发给正确 Client；合并 IRQ、错误 IRQ 与旧 device epoch 均不可按中断次数直接消费。

## 10. 两套原型与证据边界

功能原型：Arm FVP_Base_RevC-2XAEMvA/RME，Linux 5.1、TF-A 2.10，使用 test engine 模拟 DMA 外设并测试隔离，额外保留约 0.5MB device GPT。不是在 FVP 上真实执行完整 Mali 工作负载。

性能原型：Orange Pi 5 Plus/RK3588、Mali-G610、8GB，Host Ubuntu 24.04/Linux 6.1，Realm 与 System Realm Linux 6.2，禁用 A55，以 Armv8 指令模拟 CCA 操作及上下文。论文称用于周期层性能估计；它无法据此验证目标 GPC 硬件的一切时序或安全实现。

这是合理的研究原型分工，与本项目“硬件作为模拟载体”的原则相容；需要诚实分别报告功能验证、模拟开销和未覆盖的硬件保证。

## 11. 实验：收益针对软件加密基线

Rodinia 六应用运行 10 次平均，Gaussian/LUD/Pathfinder/NW/Hotspot3D/NN 的加密→PORTAL 延迟分别为 904.8→842.9、494.8→370.1、450.1→141.3、154.7→24.1、216.8→23.9、4.4→3.8ms；正文报告加速 1.07–9.07 倍，平均 3.71 倍。数据缓冲约 0.51–40.46MB，计算/数据移动比例不同。

这是同原型上的软件 AES-GCM 通信对照，不是相对原生明文无保护执行的统一加速，也不是相对真实硬件 MPE 的倍率；原文明确承认硬件加密性能会更好。不能把 9.07 倍套到项目已有明文 vmshm 或 glmark。

| 微实验 | 原文结果 | 条件与限制 |
| --- | --- | --- |
| Realm 队列创建 | 早创建无明显额外延迟，末尾创建约 +2% | 初始化可与其他工作重叠 |
| REC_ENTER | 常规增加一个 flag 检查/约5条指令；有事件注入 +6.3% | 不是所有应用持续 +6.3% |
| System Realm 启动 | boot 一次性 +1.5% | 主要是 VM 创建 |
| SMMU fault 唤醒 | 约2µs | 含 VMM 虚拟转发，非可信 IRQ 全协议测量 |
| 队列消费 | 两 Realm 各10条，总20条约1.9–2.4µs | 实验给执行 loop 独立 core；未证明无限扩展 |
| 初始 GPU MMIO 附加 | 512页约46.29µs | 页面数与平台固定 |
| 已占设备重分配 | 约175µs | 多次 Realm 切换；非任意在途任务抢占延迟 |

摘要的“一次性 9.8%”不能当作稳态 GPU 运行开销或所有设备统一值。功率实验对七模型、50ms 采样、5分钟平均，报告平均约1.43倍降低；不等于所有系统整体能耗都同倍率改善，也没有给出本项目可比数据。

## 12. 元数据、扩展性与 artifact

4GB 保护区需要额外 4KB 一级 GPT/SRAM 与约0.5MB二级 GPT/DRAM；每设备状态8字节，每 Realm 命令队列256KB、16字节entry，最多16,384条。后者随 Realm 数增长，不能因设备状态小就称总元数据开销常数。

本轮取得原文并检查作者主页/定向 GitHub 检索，尚未确认与论文相匹配、可固定提交的完整 PORTAL artifact。因此不声称检查过队列并发、反向映射、reset、错误回滚或 TLB 实现。检索未发现不等于全球不存在；论文的开放源码计划也不等于本轮已取得源码。后续应按真实发布入口固定 manifest、子模块及构建输入再审计。

## 13. 与其他论文的差异及项目可迁移性

StrongBox/CAGE 侧重以小监控器保护 GPU 任务，PORTAL 侧重一般集成设备 I/O；ACAI 把 CPU/DMA 一致性和身份变成不变量；PORTAL 把复杂 SMMU 管理交给可信 System Realm，并提供动态设备交接。MOLE 补足设备内部固件边界，Devlore 补足物理中断保护，CAEC 补足跨 Realm 共享身份；不能据此把它们称为一条正式作者继承链。

项目最值得保留三点：RMM 提供真实请求身份；可信服务核验最终物理映射；所有权变化采用不可绕过的状态与顺序。项目应额外建立对象/job 级隔离，因为 Proxy 同时服务不同 Client，并且共享服务权限大于任一 Client 权限。

## 14. 独立评价与可验证后续研究

建议将论文的设备交接不变量细化为：`authorized mapping → validated launch → authoritative terminal state → recipient-bound notification → quiescence → revoke/invalidate → safe reuse`。这是一项研究组织方式，不是已证明首创。

优先负例包括错误源身份、跨 Client backing、延迟 fault 补映射、映射更新与提交竞争、伪完成、reset 后旧通知、A→B→A 多轮切换、关闭重开及 HPA 复用。每个失败应能关联到状态迁移和真实资源，而非仅报告是否崩溃。

性能需分别测请求验证、映射合批、真实终态确认、跨 Realm 通知和撤销屏障，保留吞吐及尾延迟。未改运行代码，无新增性能测量；无硬件 run-id、无新增硬件 PASS。
