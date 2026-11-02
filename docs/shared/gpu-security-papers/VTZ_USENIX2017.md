# vTZ：多 Guest TEE、可信设备模拟与中断分派精读

## 1. 论文身份、材料与阅读范围

Zhichao Hua、Jinyu Gu、Yubin Xia、Haibo Chen、Binyu Zang、Haibing Guan，**vTZ: Virtualizing ARM TrustZone**，26th USENIX Security Symposium，2017，541–556，ISBN 978-1-931971-40-9。[正式论文页](https://www.usenix.org/conference/usenixsecurity17/technical-sessions/presentation/hua)与其直接链接的[开放 PDF](https://www.usenix.org/system/files/conference/usenixsecurity17/sec17-hua.pdf)已取得，题名、六作者、会议、页码及 PDF 长度交叉核对；不凭 Crossref 宽泛标题搜索结果附加未经核实的 DOI。

正式 PDF 为 17 页，含 1 页 USENIX 封面与 16 页论文，574,452 字节，SHA-256 `55fd309bb3c332d2c0cbb8b7bc9860b4d0a4f433b69b5968509a3b56a67ac957`。完整阅读 §1–11、68 条引用及 4 条尾注，抽取正文 78,871 字符；视觉核对 PDF 第 3、5、6、7、8、10、11、12、13 页，覆盖全部 9 个编号图和 2 张表，无独立编号算法或附录。

另取得官方页面链接的 34 页演示稿，SHA-256 `eadab8ec97945b94bc92c20bbe384f94b10d4ce38b2a7fa4af05274d5aa0fe09`。文本抽取存在字体编码乱码，因此只把 PDF 物理页 11、25、26、29、30 的视觉核对用于威胁模型、CIEE 条件、Xen 版本与兼容性补核；未声称逐页读完演示稿或观看报告视频。

vTZ 是 **Arm TrustZone 多 Guest TEE 虚拟化**工作，不是 CCA、GPU TEE 或 GPU 多租户共享实现。与项目相关的是可信管理层和复杂功能层的权限划分、设备模拟的可信边界、跨 Guest 上下文绑定与中断分派。它是 Portal/CAGE 等较新架构之外的前置机制支撑，不能计作又一套 CCA GPU 系统。

## 2. 问题、目标与假设

§1–3：物理 TrustZone 只有一套 Secure world。多个 VM 共享一个 TEE 内核，会共享信任与故障边界；全部在普通 Hypervisor 模拟则要信任庞大的 Hypervisor。vTZ 为每个 Guest 建立一对 normal VM 与 secure VM，后者承载自己的 TEE 内核；两者实际都由 Normal world 的虚拟化机制承载，物理 Secure world 留给可信保护模块。

§3.3 假设 TrustZone/虚拟化硬件正确，**包括 Normal world Hypervisor 在内的系统启动阶段可信并正确初始化**，之后 Hypervisor 可以被攻陷。Guest normal VM、Guest TEE 均可能恶意；本 Guest TEE 的内部漏洞不由 vTZ 修复，但应限制在相应 Guest。物理攻击、侧信道与拒绝服务排除，不能把它描述为从恶意启动固件到运行期都无需信任的体系。

表 1 明确列出 12 项属性：启动顺序/镜像校验/不可替换，world 目标/切换状态/TEE 状态，内存访问与分区权限，secure IRQ 目标、设备访问、设备可信和设备/中断分区权限。它是一张设计属性表，**不是机器检查证明，也不是 12 项攻击实验全部通过的清单**。

“保持物理 TrustZone 同等属性”是当时论文的目标，不表示增加了应用正确性、远程证明新鲜性、GPU 输出完整性或实时性。论文关于仅 Normal world 有 hyp、当时 Arm 缺少 SGX/SEV 类机制等描述应放回 2017 年语境，不据此描述当前 S-EL2、RME/CCA 平台。

## 3. 四个核心机制与不可绕过的保护路径

| 机制 | 论文位置与作用 | 对本项目可迁移的原则 |
| --- | --- | --- |
| SMM：Secured Memory Mapping | §4.1，物理 Secure world 独占 Hypervisor 自身页表和 Guest Stage-2 的加载/修改，并检查映射策略 | 所有实际映射入口必须服从授权；仅保护一份元数据表不够 |
| CFLock：Control Flow Locking | §4.2，保护异常向量根与表项，在异常入口固定转入指定处理逻辑 | IRQ/异常必须先经过可信分派，Host 不能提供替代入口 |
| SWS：Secured World Switching | §4.3、§5.1–5.2，保存/恢复受保护 CPU 状态并检查 Guest world 配对 | 身份来自可信执行上下文，不能根据对端自报的目的 VMID 授权 |
| CIEE：Constrained Isolated Execution Environment | §4.4，每个模拟器具有独立页表、栈、对象与受限能力 | 隔离功能代码的权限与状态，尤其限制跨 Client 访问 |

SMM 依赖对 Hypervisor 指令与映射的约束：移除加载页表根/禁用翻译等直接指令，页表只读，代码只读，禁止启动后新增可执行页；也要覆盖不同 ISA、别名映射、return-to-guest 和可重用特权指令。CFLock 同样保护向量基址与表项；SWS 还替换可退出 hyp 的指令，形成受控出口。这些共同构成其同特权级隔离假设，**单独“页表只读”不能推出完整不可绕过性**。

启动注册时，Hypervisor 提供 VM 镜像和分配结果；SWS/SMM 先撤掉 Guest 页对 Hypervisor 的映射，再检查 TEE 镜像，绑定 normal/secure VMID，建立受保护上下文和 Stage-2；TEE 应先于 normal VM 执行。可信组件必须验证分配与绑定结果，不能把 Host 选出的 VM 或页天然当作可信身份与授权。

对项目而言，RMM 认证原始 Client、ProxyRealm 检查实际 HPA 归属/权限/生命周期、保护真实 GPU 页表与 SMMU/MMIO 的假设仍保留。vTZ 的 CPU 两阶段映射不能直接证明软件合成 GPU Stage-1 安全，但支持其共同前提：**合法性检查必须约束实际生效的翻译结构、根配置和所有替代修改路径**，执行期保护持续存在。

## 4. CIEE：隔离能力与服务语义必须分开

§4.4、图 4：CIEE 有五项条件——单入口、运行至完成、不依赖 Hypervisor 可篡改数据、不向 Hypervisor 暴露私有状态、向 Secure world 不可冒充。代码加载到固定地址、只读且默认不可执行；首尾 smc 进入可信模块，按受保护陷入地址识别 CIEE，执行时只在当前核映射代码/栈，结束后恢复不可执行并清理栈。中断在进入前关闭。

固定代码地址能作为身份，是因为代码来源、根映射、陷入状态和入口过程已经被保护；不是“知道一个地址就能认证调用者”。本项目原始 Client 身份应继续从 RMM 已认证执行上下文传递，不能把消息中的 PID、VMID、会话号或共享指针当作替代身份。

CIEE 的对象由 SMM 维护，按 CIEE 和当前 Guest 双重分隔；对象在 hyp 侧只读，写入需经可信模块授权。每个 CIEE 一次服务一个调用 Guest，当前 Guest 由 SWS 认定。它还可向 Hypervisor 输出结果，例如加密快照；“不暴露私有状态”不表示禁止有意输出，也不自动验证该输出的业务正确性。

作者据此把 CIEE 排除在跨 Guest 隔离的系统 TCB 外，并在 §7.2 明确说 **未形式化验证 CIEE**。需要按属性理解这个 TCB 口径：约束模拟器只能损害被授权的 Guest，可缩小跨 Guest 隔离的信任依赖；但当前 Guest 若要求设备响应正确、无泄漏或不错误授权，其使用的模拟器语义仍可能属于相应服务的信任依赖。不能把“跨 Guest 能力受限”写成“所有 CIEE 有 bug 也不影响任何安全属性”。

这对统一 ProxyRealm 尤其重要：如果 Proxy 内核或驱动有权访问所有 Client 的 BO 和页表，只做进程内的私有结构划分，不等于获得 CIEE 式故障隔离。现有架构信任 Proxy 的前提应明确；若将来要减少这项信任，应先证明每个功能模块的实际能力边界。本文不据文献提出未经实现的分舱已完成声明。

CIEE 的短 CPU 代码关中断运行，不适合直接套到异步 GPU shader、长任务或全局驱动临界区。GPU 在 CPU 被中断或退出可信代码后仍会 DMA，故不能通过“提交函数不可中断”推导任务执行期间没有越权访问。项目应保留映射保护、任务状态及撤销回收约束。

## 5. 设备与中断：可信分派解决了什么

§5.3：vTZ 为每个 Guest 提供 vTZASC、vTZPC 与 vGIC，配置寄存器写入通过 Stage-2 只读陷入；CFLock 将陷入送至 CIEE，先判断调用来自该 Guest 的 secure VM，再修改该 Guest 的分区状态。虚拟 secure 设备模拟器也在 CIEE 内，其私有设备状态逐 Guest 保存；secure 设备拒绝本 Guest normal VM 访问。

论文实现举例包括 TZASC/TZPC/GIC/UART/RTIC，并非完整 GPU 驱动或任意物理设备直通。§7.1 明确规定 Guest TEE **只信任 vTZ 提供的虚拟设备，其他设备必须视为不可信**；所以“Guest 在 TEE 中运行”并不会自动认证 Host 提供的网络盘、随机源或其返回字段。这与 VIA 的设备输入安全结论可衔接。

中断到达后，受 CFLock 保护的 secure dispatcher 查询 trusted vGIC 管理的虚拟中断分区表，secure IRQ 送至 Guest TEE，normal IRQ 才交普通 Hypervisor。它保护的是 **谁能配置路由、谁处理分派以及分派到哪个 world**。原文没有给出覆盖 GPU job/队列/代际的完成凭据，也没有完整展开恶意虚拟中断的去重、迟到 ACK/EOI、路由切换与设备 reset 并发协议。

因此应分四层论证：配置来源合法、事件进入可信分派、目标 Client/当前生命周期匹配、任务结果确实达到可信终态。前三层也不能只凭一个“secure interrupt”属性位互相替代。vTZ 的受控分派不自动证明每次通知都来自一次真实 GPU 完成。

§7.3 同时说 Host 可以不调度 Guest TEE，但不能忽略 Guest 已执行的 smc world-switch 请求。合理的范围是对已进入受控路径的切换约束与调度可用性分开，不能从前者推出 Host 无法阻止进展、IRQ 有最坏时延上界或 GPU 任务一定完成。

项目已有 RMM pending/ack/armed 与保留 IRQ127、可信通道身份，以及 Proxy 原生 fence、Client 私有 cookie/epoch 匹配；应将它们分别对应到路由权限、通知状态和任务完成语义。cookie 本身不是 MAC，完成记录的真实写权限仍是必要条件。这里根据当前基线及已完成的 VIA 限定路径复核建立对应，不声称本轮重新审计全部 RMM/GIC/驱动。

| 本项目应明确的场景 | vTZ 能提供的启示 | 仍须由项目证明的条件 |
| --- | --- | --- |
| Host 或 Client 请求通知另一个 Client | 可信分派保存路由权，不信任普通 HV 的目标选择 | RMM 原始端点身份、通道授权和目标绑定 |
| IRQ 合并、重复、提前或没有对应记录 | 可信入口不能被绕过 | IRQ 只触发检查；无匹配任务终态不得 signal 成功 |
| Client 退出后 slot/通道重用 | 每 Guest 独立受保护状态 | 在途回调排空、cookie/epoch 与端点新生命周期隔离 |
| reset/撤销后迟到 GPU 中断 | 分区配置受可信模块控制 | 设备状态排空、旧 IRQ/完成记录无效、新任务不被旧事件完成 |
| completion 已发布但旧 DMA 仍可能发生 | 可信分派与内存保护是不同机制 | 输出同步、映射撤销、实际静默及清零/复用条件分别满足 |

## 6. DMA、挂起恢复与未被覆盖的生命周期

§7.2 的 DMA 防线是把 SMMU 控制寄存器仅映射给 Secure world，并拒绝 DMA 访问 Guest secure 内存、Hypervisor 代码与 CIEE 内存。它没有给出完整按设备 stream、实际页表归属、热重配、IOTLB 失效与旧 DMA 排空的协议。论文原则可用于支持本项目独占可信 SMMU 管理，但不能替代当前实际页表、根配置和其他 DMA 别名路径的论证。

§5.4、图 6：挂起 CIEE 请求 SWS 加密并 hash CPU 状态、内存/中断/设备分区等元数据，再由 SMM 加密并 hash Guest secure 页，交 Hypervisor 保存；恢复时由 Secure world 解密和检查，再注册 VM。正文交替使用 checksum/signature/encrypt+hash 表述，未展开可独立审查的完整密钥、认证绑定及 nonce 协议；不能将它擅自补写为已实现 AEAD。

即使快照完整性已成立，**旧快照重放、分叉恢复、VMID 重用与跨会话替换**仍需要可信新鲜性与身份绑定；只验证 hash 不证明“这是最新可接受状态”。文本没有足够细节证明这些属性，也没有 GPU 在途执行的迁移/静默方案。此处标为设计说明不足，未执行重放攻击或宣称存在已验证漏洞。

项目未来若支持 Proxy/Client 挂起或迁移，应把 BO 授权、设备上下文、在途原生 fence、cookie/epoch、pending/ack、页表代际一起考虑。只保存 CPU/队列字段不能保留异步 GPU 安全状态。本轮不扩展实现范围，不改当前冻结运行代码。

## 7. 性能、兼容性与证据强度

环境：Hikey ARMv8，8 核 1.2GHz、2GB；Exynos ARMv7，启用 1 核 1.7GHz、1GB。摘要与引言写 **Xen 4.8**，§6 及官方演示稿物理页 29 写 **Xen 4.4**，两者不一致，保留而不自行选一个认作已核实精确版本。Guest normal 与 Dom0 Linux 4.1，Guest TEE 为移植的 OP-TEE/seL4；多 Guest 实验通常每 Guest/Dom0 单 vCPU，Hikey 绑物理核，服务器实验改为 Guest 8 vCPU，不能混为同一配置。

兼容性并非零修改：§6 要求添加 multiboot header、描述虚拟硬件地址空间，并移除原 TEE 内核上下文切换逻辑。演示稿的兼容性页只强调描述文件，不能覆盖正式论文列出的其他改动。未复核具体补丁、改动行数或 seL4 既有形式证明在本移植上的适用性。

表 2 为单次操作 **cycle 成本**，不是图形分数、吞吐或中断递送延迟。独立复算如下；ARMv8 原生 memory/device partition 因厂商未公开寄存器映射列为 n/a，不能补算相对开销。不同平台频率/架构/核数不同，也不能直接按 cycle 大小认定某平台端到端更快。

| 操作 | Native → vTZ cycles | 绝对增加 | 相对增加 |
| --- | --- | --- | --- |
| ARMv7 world switch | 17,840 → 34,164 | 16,324 | 91.50% |
| ARMv8 world switch | 1,294 → 6,837 | 5,543 | 428.36% |
| ARMv7 memory partition | 5,798 → 10,341 | 4,543 | 78.35% |
| ARMv7 device partition | 1,886 → 10,395 | 8,509 | 451.17% |
| ARMv7 interrupt partition | 1,073 → 4,031 | 2,958 | 275.68% |
| ARMv8 interrupt partition | 755 → 2,903 | 2,148 | 284.50% |

论文以切换与配置不频繁解释应用成本小；这适用于其测量的 CPU TEE 工作负载，不能无测量地推广到高频 GPU RPC/IRQ。摘要/引言约 3% 对 Xen、并发 ARMv8 GoHttp 约 5% 对 Xen和小于 30% 对 native、Apache 小于 5% 都是不同范围，不应合并成“所有操作仅 3% 开销”。

图 7 是归一化执行时间、越低越好，轴标题带百分号但刻度约 1；不能把柱高 1.04 当 1.04% 总耗时。作者报 RTIC SHA1 模拟 0.3–4% 开销，图中只有五个 size 标签，文本“1K–128K”未提供完整原始统计；SHA1 hashing 性能不是现代强认证协议的开销证明。

图 8 比较 native、物理 TrustZone、Xen、vTZ 的多 GoHttp 并发吞吐。ARMv7 图实际只有 1/2/4，ARMv8 有 1/2/4/6，不能按总图注写 ARMv7 也测了 6 Guest。客户端和服务端同 Guest/本机以排除网络开销，20MB 请求与 Xen 30ms 时间片会受调度影响；图 9 的 MongoDB insert/Apache 100MB HTTPS 同样是本地客户端条件，不能解释为完整远程可信 I/O 吞吐。

没有取得逐次测量、运行次数、置信区间、图 7–9 源数据或统计脚本，故只独立复算表 2，图形保留定性与作者限定结论，不从柱高捏造精确数值。§7 是安全推理及局限分析，并非完整攻击回放、负例矩阵或机器验证；引用已有 CVE 说明动机，不等于复现全部攻击。

“Secure 模块小于 2k LoC”没有逐模块复算依据，结论还包含系统 bootloader；CIEE 的跨 Guest 隔离与服务语义又有不同 TCB 范围。不能拿这个增量口径直接和项目 RMM、Proxy 驱动、固件和整个 Linux 栈比较并声称本项目 TCB 减少多少。

## 8. 公开实现与同轮获取记录

正式论文/官方展示页未提供本次可确认的匹配运行 artifact；限定 GitHub repository 查询 `vtz trustzone` 返回 0、`incomplete_results=false`，猜测的机构项目页及 PDF 路径为 404。这些是有限获取结果，**不能证明作者从未发布代码**；本轮没有匹配固定提交、源码树、驱动 patch 或测试数据，不声称完成源码审计或实验复现。未拿上游 Xen/OP-TEE/seL4 仓库代替 vTZ artifact。

本轮还核实 Hecate：正式 DOI `10.1145/3548606.3560592`、三作者、CCS2022 及微软研究院正文摘要相符；它利用 SEV-SNP VMPL 实现 CVM 内单个 nested VM 与策略执行。Hecate 的 Crossref 主标题和副标题分开，最初长题搜索漏检，短名+年份查询恢复；未取得全文，ACM403、作者路径猜测404及 arXiv 标题搜索仅得无关工作，仍不计完成，也不称其为 Arm/GPU 原型。

GR-T 本轮作者实验室页面仍将正式题名链接到早期 CODY arXiv，不能据此把早期版本当 EuroSys2023 全文；当前正式全文待办保留。HypSec 的单个猜测作者 PDF 路径404，仅作后续候选，不计完成。这些失败不影响已取得的 vTZ 正式全文，但应保留获取范围，避免用摘要充满精读数量。

## 9. 对项目的结论与统一记录

最值得借鉴的不是把 CIEE 原样搬到 GPU，而是把 **实际映射权限、调用者身份、功能代码能力和事件路由权**分别交给可信机制约束。当前方案可继续采用可信 ProxyRealm 统一 SMMU、RMM 原始身份、GPUVM/BO、private plan/snapshot、native fence/cookie/epoch 与 IRQ127；无需为每篇新参考文献增设重复框架。

论文写作应把第二部分从单纯“内存页隔离+中断转发”深化为“任务与控制通道隔离”：映射合法、事件来源/目标合法、任务终态可信、撤销后旧状态不可复用。输出同步、任务完成、应用算法正确、DMA 静默和安全回收仍分别证明；vTZ 的虚拟 interrupt partition 无法单独替代这些 GPU 条件。

证据目录 `build/cca-gpu-followup-20261027/`：`vtz112.pdf`、`vtz112.txt`、`vtz112-usenix.html`、`vtz-render112.json`、`vtz112-slides.pdf`、`vtz-slides-render112.json`、`vtz-arithmetic112.json` 与 `acquisition112*.json`，保留成功来源哈希及所有失败记录。未运行作者程序、Hypervisor、VM、攻击、模型、GPU workload 或硬件测试。

统一记录：补充多 Guest TEE 权限隔离、可信虚拟设备与中断路由证据｜glmark 未测 → 未测｜分差及百分比不适用｜**未改运行代码，无新增性能测量**｜正式 17 页含封面/68 引用/九页图表视觉/五页 slides 视觉/表 2 独立算术/Notion 全文回读｜无作者代码、构建、VM、攻击或硬件 run-id｜保留研究；未获 artifact/原始统计、Xen4.8/4.4 冲突保留，Hecate/GR-T 等继续待办，整体 active。
