# SHELTER 期刊扩展：设备独占分配、GIC 路由保护与 pending 中断

研读日期：2026-10-27。本文按版本增量解读 SHELTER 的 TDSC 工作，重点是设备与中断隔离；它属于 CCA 可信 I/O 相关工作，不是实现 GPU 共享的论文。已读全部 18 页作者接受稿，比较 USENIX 2023 版本并定向核对公开原型。

## 1. 准确书目信息与来源

| 项目 | 内容 |
| --- | --- |
| 标题 | Complementing Confidential Computing Environment for Applications on Arm CCA |
| 作者 | Yiming Zhang、Yuxin Hu、Zhenyu Ning、Fengwei Zhang、Xiapu Luo、Haoyang Huang、Shoumeng Yan、Zhengyu He |
| 正式发表 | IEEE Transactions on Dependable and Secure Computing，23(1)，97–114，2026 年 1 月 |
| DOI | [10.1109/TDSC.2025.3604008](https://doi.org/10.1109/TDSC.2025.3604008) |
| 原文 | [作者公开接受稿，18 页](https://fengweiz.github.io/paper/shelter-tdsc25.pdf) |
| PDF SHA256 | `ba4bf79a85224188fe5ee21cfe0cfd4898cd676548779e4fdcabc8607be3ceb6` |
| 书目核验 | 作者出版列表与 Crossref 正式卷期；作者页面仍写 TDSC’25，本文区分接受年份与正式出版年份 |
| 公开原型 | [Compass-All/SHELTER](https://github.com/Compass-All/SHELTER) |
| 固定代码 | `adef631e0fecfc20577da61e03d49bf16b1edbc2`，提交时间 2023-07-23；本次 git ls-remote 再核对 HEAD 一致 |

作者 PDF 为尚未最终编辑的接受稿，机制、数值和文字差异均按该版本分析。本报告不转载论文全文。它与 SHELTER: Extending Arm CCA with Isolation in User Space（USENIX Security 2023）使用同一系统主线；单独记录的理由是新增 DA/GIC 设计和评估，不把它当成另一套独立 GPU TEE。

## 2. 研究问题与本版增量

原 SHELTER 解决 CCA 主要面向 Realm VM、缺少用户态隔离的问题：在 Normal EL0 运行 SApp，用 Root EL3 Monitor 切换每核 GPT，实现不信任 OS、Hypervisor、Secure 软件甚至 RMM 的用户态隔离。

本版在这条主线上加入 Device Assignment（DA）：将一个设备独占分配给一个 SApp，保护其 MMIO 和 DMA 可达范围，并把设备 INTID 路由到正在运行该 SApp 的 CPU。新增正文 §4.5、§5 的 DA 实现、§6.3 GIC 攻击情景，以及 §7.5 存储、CPU、内存与碎片评估。

最贴近本项目的是设备归属、CPU 调度和中断投递之间的一致性。不过这里的目标是 SApp 独占设备；不是多个 Client Realm 共享一个 GPU 后的逐 job 完成通知。

## 3. 威胁模型、可信基与排除项

攻击者控制 Normal、Secure、Realm 软件，包括 OS、Hypervisor、可信 OS、SPM、RMM，也可启动恶意 SApp。Monitor 经厂商签名和安全启动加载，硬件/RME 被假设正确。SApp 不主动泄密；安全 I/O 和持久存储所需加密通道被假设可结合既有方案。

DoS、物理攻击和一般侧信道排除。依赖不可信 OS 调度意味着不能保证及时运行或中断处理时限。§6.1 明确没有实现 attestation；本地验证和安全启动不能当作远程用户已确认 SApp、服务实例及实际设备授权。

论文所说 Monitor TCB 是隔离基础设施的统计口径。新增 DA 后，受保护 EL1 edge interface 中的设备驱动也承担处理设备与秘密的职责；分析应用端到端信任链时不能因其不在 Monitor 增量表中而忽略。该取舍与本项目将完整 GPU 驱动放入可信 ProxyRealm 有方法上的联系。

## 4. 多 GPT、物理池与可信生命周期

Host GPT 对全部 SApp 私有页设置 No-access；每个 SApp GPT 只允许当前 SApp 页，其他 SApp 和高权限软件均不可访问。GPT 和根配置由 Monitor 保护，进入/离开 SApp 时按核心切换。即使关闭普通 MMU，GPC 仍需约束物理访问。

Linux CMA 提供连续物理内存，Monitor 验证地址和长度、不与已分配 SApp 重叠后登记；连续池减少逐页 GPT 操作。SApp 页表复制到私有区，OS 的更新经 Monitor 检查物理 backing 是否在本 SApp 池内及是否非法覆盖栈等区域。

创建先建立受保护环境并验证，之后准备上下文和私有页表；使用 shadow GPT 模板降低构造开销。销毁清零全部 SApp 内存、处理 cache/翻译并释放元数据，再交还 OS。新增设备访问后，还需要明确设备停止访问与 CPU 清零之间的顺序，不能从 CPU 生命周期自动推出 DMA 安全回收。

多核管理通过锁串行化 GPT/生命周期修改，用受保护 GPT 根地址识别 SApp。设计包含 TLB 失效、CnP=0、特定 coherency 处理及必要寄存器/cache 清理。这些属于作者多视图方案，不能直接变成项目每次 RPC 必须全局清 cache 的要求。

## 5. DA 的三个核心保证

| 对象 | 论文设计 | 需要维持的一致性 |
| --- | --- | --- |
| CPU→设备 MMIO | 多 GPT 覆盖设备地址，只向获分配 SApp 开放 | 设备 owner 与当前执行 SApp 一致 |
| 设备→内存 DMA | 获分配设备的 SMMU GPC 使用相应 SApp GPT，其他设备使用 Host GPT | 实际 DMA 可达页属于当前授权集合 |
| 设备→CPU IRQ | 可信 Monitor 配置 INTID 及 GIC affinity | 投递核心正在运行正确 SApp |

Monitor 的 DA API 接收设备地址范围和 INTID，记录 SApp 对内存、设备和中断的权限，然后设置 GPT/GIC。设备声明不能仅凭不可信软件的数值自然获得真实性；地址、INTID、设备实例和可分配资源需要来自可信平台描述或经可信策略校验。论文给出维护归属的设计，本次未核验一套完整、可运行的期刊 DA 准入实现。

保护 GIC distributor 的物理 MMIO 被置为 Root PAS，使其他软件及 DMA 不能更改路由。这体现控制平面的重要性：只保护数据页不足以阻止攻击者把真实事件投到别处。

## 6. 调度出去后保留 pending：机制与语义

§4.5 的流程是：Monitor 把已分配 INTID 的 affinity 指向当前运行 SApp 的核心；切换离开 SApp 时禁止该 INTID 转发，但不抹去 pending；SApp 再调度时恢复配置并重新允许投递，GIC 将 pending INTID 交给该 SApp。

这个设计避免 Host 运行期间直接接收属于 SApp 的设备通知，并利用硬件 pending 跨越调度空窗。但 pending 是通知状态，不是完整的任务结果日志。它没有表达 Client/job 身份、成功/错误类型、完成次数或设备 epoch，也没有自动提供有界等待和投递时限。

论文的 affinity 随调度恢复还要求路由、使能与执行上下文保持一致。设备断开/重新分配、旧 pending 清理、迁核时 active 状态和 ACK/EOI 归属等异步交错，正文没有给出完整状态机或 Devlore 式通用虚拟中断分析。不能将“发往正确核心”推广成所有事件语义已经可信，也不能据未展开的情景直接断言可利用漏洞。

## 7. 保护 GIC 与系统兼容性

§5 表示实验中的 Linux 在启动后不再访问相关 GIC 配置，因此在 SApp 创建后保护 distributor MMIO 未产生实验冲突；还提出必要时由 GPF handler 检查并代执行合法访问。

这是特定工作负载的观察，不应当作所有 Linux、CPU 热插拔、IRQ affinity 管理或电源切换都只在启动时访问 GIC 的保证。若使用代执行路径，该入口本身需要限制寄存器、INTID、caller、目标核心及状态，避免形成新的越权控制入口。

接受稿 §5 将“启用中断转发”写成经 `GICD_ICENABLER`，但 ICENABLER 的正常作用是清使能；ISENABLER 才是置使能。固定原型的 GIC helper 也分别提供 `gicd_set_icenabler` 与 `gicd_set_isenabler`。因此这里保留文字/寄存器命名疑点，不能据一句描述确定实际 DA 写寄存器路径正确或错误；需期刊匹配代码才能进一步核实。

## 8. 驱动、系统调用和信号边界

SApp 通过受保护 EL1 edge interface 陷入 Monitor。一般系统调用转给 OS；带指针参数使用共享区，检查前撤回 Host 对共享区访问，再验证长度并拷回。实现覆盖约 50 种此类 syscall；作者明确不是完整 Iago 防御。

DA 的存储实验将 Linux 存储驱动移入 SApp EL1 edge interface，独占磁盘。论文仍描述 syscall 经 EL0→EL1→Monitor→Linux，再回到 Monitor 和 SApp 驱动，因此性能包含多个切换。不能将它概括为所有 I/O 完全绕过 Host，或将驱动移植等同于通用设备模型。

信号仍由 OS 在共享 frame 中构造，Monitor 检查 handler 属于已登记地址，并保护 frame。合法入口和不可变 frame 不独立证明此次信号原因真实；与 Sigy/Heckler/WeSee 比较时，应区分架构与实际触发条件，不把 x86 案例写成 CCA 的已证实攻击。

## 9. 安全评估实际证明了什么

作者调研 45 个 CVE，按威胁模型分析即使高权限软件被攻陷仍受 GPT 隔离；这是缓解分析，不是 45 个原始 exploit 的完整复现。

§6.3 在 FVP 中模拟三类攻击：恶意 Realm manager 访问 SApp 页；test engine 设备 DMA 访问 SApp；CPU MMIO 或恶意 DMA 篡改 GIC distributor。作者报告均被 GPC/GPF 阻断，支持受保护物理访问边界及配置不可篡改。

这些实验没有等同覆盖 pending/active/EOI 全状态、设备重分配后旧 IRQ、逐 job 完成类型、新会话复用对象或多 Client GPU reset 竞争。全文未给出通用 DA 协议形式化证明或上述完整故障注入矩阵。本次未运行 FVP、安全攻击或板端实验。

## 10. 公开代码与期刊设计之间的距离

本次再次确认公开 HEAD 为 2023 年固定提交。README 仍以 USENIX 2023 为引用，介绍 FVP 用户态隔离、静态链接支持及 access_test，并提示复杂程序尤其多进程可能 crash/GPF，syscall 支持不完整。

沿用此前已取得的未截断 root/src、Monitor 4,362 项及 userland 13 项子树，重新定向阅读 `gpt_core.c` 的创建/身份/信号相关结构、`gpt.h`、签名函数、driver/vector，以及本次新取得的 `gicdv3_helpers.c`。旧整仓递归树曾截断，不用于声称完整源码审计。

| 公开代码观察 | 能支持的结论 |
| --- | --- |
| `shelter_verify_sign` 计算 SHA256，与固定 `hash_true` 比较 | 属于摘要白名单，不能称为通用公钥签名协议 |
| 创建调用 `shelter_verify_sign(vector_pa, EXCEPTION_VECTOR_LENGTH)`，长度 `0x1000` | 公开路径验证向量页；未显示完整任意 SApp 镜像验证 |
| 公开向量表将 IRQ/FIQ 等经 SMC 交给 Monitor | 体现会议版基本异常出口；不能替代期刊所述逐设备 SApp driver 分发实现 |
| 已读 GPT/driver 路径未见完整 DA API、设备 INTID 归属和调度路由事务 | 本次没有确认可复现期刊 DA 的匹配公开实现；不是断言整个仓库或作者内部没有实现 |
| GIC helper 有通常的 enable/disable accessor | 仅证明基础库存在，不证明期刊 DA 已按正确顺序调用 |

没有找到可由现有材料完整复现新增 DA 性能、存储驱动移植和攻击实验的发布指南。本次没有执行 `env_fetch.sh`、构建或硬件命令；固定仓库提交也不自动固定该脚本中的全部外部依赖。

## 11. 可信增量、性能平台与比较限制

新增 Monitor 代码 2,425 SLoC：多 GPT 229、内存管理 329、生命周期 1,265、多核管理 249、DA 353。相较会议版的 2,072，增量恰为 353，但表内分类有重组，不能据此称其他实现逐行未变。作者估计可裁剪 Monitor 基础约 4k，因此约 6k 为估算；其参考 TF-A 源码约 310k，均不是实际链接固件的独立完整 TCB 审计。

功能验证用 RME FVP、Linux 5.3、TF-A arm_cca_v0.3。性能用 Juno R2、8 GB、作者描述的 A72 核、1.2 GHz，重复 30 次取平均。GPT 为真实软件结构，用空闲 EL3 寄存器代替 GPC/GPT 根寄存器，用普通 TLB 全失效代替 RME 指令；包含所述微架构维护，但没有真实 GPC 每次访问成本。

VM 对照为同板的 Realm context/GPT analogue 和普通 KVM，2 vCPU、512 MB；不是当前成熟 CCA 的统一性能上界。Sanctuary 使用论文中 HiKey960 数字换算 cycle，并排除其关/开核时间；不是同板重跑，内存配置也不完全可比。

## 12. 实验结果与不能混淆的口径

| 实验 | 作者结果 | 范围 |
| --- | --- | --- |
| 4 MB 分配/释放 | 3,189 / 769 μs | 分配含初始化 |
| 创建/销毁 | 4,925 / 1,054 μs | 最小 SApp、4 MB |
| Exit / Switch | 391 / 3 μs | 两个不同操作，不合并为所有退出只需 3 μs |
| GPT 模板 | 构造成本平均降低 77.5% | 2/4/8/16 GB PAS，非应用总加速 |
| AES、Apache、Memcached、Nginx | 5.2%、15.0%、8.3%、11.8% 开销 | 特定应用及 syscall 模式，未含完整部署成本 |
| UnixBench，SApp 每 1000/100/10 ms 启动 | 平均开销 0.37% / 1.87% / 7.68% | 最密集条件单项 16.9%，不是全部系统最多 15% |
| 三服务均值 | SHELTER 11.7%、Realm 模拟 32.0%、普通 VM 29.8% | 特定虚拟化/I/O 配置 |
| DA 独占存储 Fileio | 随机读平均慢 7.06%，写平均慢 8.4% | 64 KB–16 MB，Linux 基线；不是 GPU 性能 |
| DA 的 SPEC CPU 2017 | 12 项几何平均额外耗时 3.36%，最高 12.8% | CPU/内存实验说明必要时仍由 OS 服务设备 |
| MaxRSS | 正文写 0.868% 几何平均，nab 约 4% | 图 15 与上下文表示额外开销；措辞称 normalized footprint，不能解释为仅用 Linux 的 0.868% 内存 |

内存池以最小 8 MB chunk 对齐；MaxRSS 不能直接代表整个平台所有物理池预留和固件开销。碎片依据运行 SPEC 后 `/proc/buddyinfo` 计算指定阶分配不可用的空闲页比例；作者观察较低碎片，不能推出任意长时间多租户运行都低碎片。

全文没有提供 GPU glmark、逐中断端到端延迟、尾延迟或多 Client 并发公平性的新增数据。本次未重算作者图形原始样本，不把模拟数字迁移为项目硬件预期。

## 13. 与项目及相邻工作的关系

| 相关路线 | 本文提供的内容 | 项目仍需独立说明的内容 |
| --- | --- | --- |
| CAGE | GPT/MMIO、可信执行窗口；本版 DA 更强调 IRQ 路由 | 任务独占、应用独占与并发共享的不同保证 |
| ACAI / PhantomMap | 实际物理访问与归属检查的共同基础 | 原始 Client、真实 backing、权限及生命周期 |
| PORTAL | 与可信驱动服务路线形成 TCB 和接口划分比较 | ProxyRealm 实例与请求准入，不必改为用户态 SApp |
| Devlore | GIC 控制平面和可信事件投递的直接关联 | Realm VM 虚拟中断、Host 调度及 ACK 状态模型 |
| Heckler / Sigy / WeSee | 合法 handler 仍需核实触发原因和副作用授权 | 架构差异、GPU job 语义和可信完成类型 |

本项目已接受 RMM 认证原始 Client、可信 ProxyRealm 控制 SMMU、受保护 PTE/root/MMIO、可信固件及安全回收。无需为了引用 SHELTER 引入另一种 GPT 用户态执行模型，也无需据测试硬件限制否定这些假设。

项目已有 GPUVM、认证队列、persistent IRQ127、私有快照、原生 fence、cookie/epoch。SHELTER 新增 DA 可用于比较路由归属随调度变化的做法，不能写成项目现在没有中断或身份隔离。

## 14. 独立评价与可验证的增量方向

这篇期刊版补上了比会议版更具体的设备地址、DMA 和 IRQ 控制平面，是研究 CCA 中断隔离的直接相关材料。证据最强的部分是访问保护与被保护配置；对事件语义、生命周期异常和期刊匹配 artifact 的证据仍有限。

对项目可建立两层关系：设备或 IRQ 归可信服务；服务观察到真实状态后，仅把当前 job 的授权终态通知其 Client。IRQ 路由、结果发布、ACK/EOI 和内存回收不应共享一个含糊的“完成”条件。具体实现应复用已有真实 fence 和身份记录，只补尚未闭合的不变量。

后续验证可覆盖：SApp/Client 未运行期间事件到达、pending 合并与重复唤醒、迁核及同 INTID 的新 owner、旧 epoch 迟到事件、reset 伴随 active IRQ、错误 fence 与成功状态混淆、ACK 与回收交错。测试既要拒绝越权，也要允许合法乱序和并发；通知丢失的恢复不能让旧事件获得释放新对象的权限。

上述为文献指导的研究设计与验证条件，不是本次已证明当前代码存在漏洞，也没有新实现、硬件复现或性能收益。

未改运行代码，无新增性能测量。项目 glmark 前后均未测，绝对/百分比变化不适用，无新增硬件 run-id 或硬件 PASS。
