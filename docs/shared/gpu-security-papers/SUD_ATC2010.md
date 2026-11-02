# SUD：恶意驱动约束、DMA旁路与中断风暴安全

研读日期：2026-10-28。完整阅读USENIX正式全文14页、§1–7及36条引用，八页图表/关键论证可视核对；作者主页全文与会议版SHA256一致。没有取得匹配源码，没有运行构建、硬件或攻击实验。本文属于可信I/O与不可信驱动支撑研究，不是CCA/GPU TEE架构。

## 1. 书目与来源

| 项目 | 内容 |
| --- | --- |
| 标题 | Tolerating Malicious Device Drivers in Linux |
| 系统名 | SUD；兼容运行环境称SUD-UML |
| 作者 | Silas Boyd-Wickizer、Nickolai Zeldovich，MIT CSAIL |
| 发表 | USENIX ATC2010；作者书目记Boston、June2010 |
| 官方入口 | [USENIX](https://www.usenix.org/conference/usenix-atc-10/tolerating-malicious-device-drivers-linux) |
| 官方全文 | [PDF](https://www.usenix.org/legacy/events/atc10/tech/full_papers/Boyd-Wickizer.pdf) |
| 作者来源 | [作者主页](https://people.csail.mit.edu/nickolai/)明确链接[同版全文](https://people.csail.mit.edu/nickolai/papers/boyd-wickizer-sud.pdf) |
| 两份PDF的SHA256 | `e7c189119e61218f199a33ee6f79a299ef67df7d17b6409e447e0e2e570809a8` |

严格解析14页，独立PDFium渲染并阅读第4、6、7、8、9、10、11、12页，涵盖架构、接口、硬件约束与实验。官网给出作者、年份及会议，不为它补造未核实的DOI。代码查询、失败URL及回读记录单独保留。

## 2. 问题、目标与模型

SUD不满足于容忍普通驱动错误，而假设驱动可执行任意CPU代码、系统调用，指挥设备任意DMA/中断，拒绝回复或无限循环。目标是在可信Linux内核下约束恶意驱动及其设备操作，避免其破坏内核、其他驱动与无关应用；依赖该设备的应用仍可能无法进展。

信任基础包括Linux及SUD可信模块、内存/中断隔离硬件、PCIe规范的正确实现。设备硬件被信任，但驱动不可信。没有恶意Host、CCA Realm身份、远程证明或机密GPU内存保护；它也不保证设备物理状态安全、驱动服务正确或设备所处理数据始终机密。

对项目尤其要区分“能限制驱动破坏范围”和“可以把Client明文安全地交给恶意GPU驱动”。SUD中的驱动仍能读取交给它的缓冲、伪造结果或拒绝服务。项目可信ProxyRealm是更强信任前提，不能把SUD驱动标为不可信就直接推导可将整个Proxy移出可信基。

## 3. 架构与未修改驱动复用

每个驱动在独立Unix UID的用户进程中运行，通过SUD-UML获得kmalloc、jiffies等Linux运行环境。可信侧有按设备类别提供原Linux接口的proxy driver，以及通用safe PCI device access模块；两者分别负责受控RPC和物理设备权限。UML及旧驱动位于不可信侧，不要求它们无漏洞。

kernel→driver称upcall，driver→kernel称downcall，由uchan文件描述符及双向共享ring传输。API含同步send、异步asend、wait/reply和共享缓冲分配/释放。普通驱动函数指针不会被直接拿来作为可信内核执行入口，而是通过消息封送调用。

内核必须审查来自驱动的消息，而非只信任旧API惯例。同步upcall允许被中断并返回错误，异步队列满时检查进展；不可抢占上下文不能等待不可信驱动，部分小功能和必要状态由可信proxy镜像处理。某些类别仍需重构内核，关键timer等设备不适合按此模型完全移出。

作者未对一般高层语义不变量强制检查，理由是测试过的Linux子系统对驱动返回值较健壮；若存在额外依赖，需要proxy维护状态并检查。这是经验范围，不是所有新设备API、尤其GPU fence与对象生命周期接口均可安全沿用的证明。

## 4. 共享缓冲、检查后修改与权威状态

uchan用共享ring减少上下文切换；驱动批量处理消息，只有无消息时select休眠，异步downcall也延迟到wait/send时通知内核。共享数据缓冲还可直接供设备DMA，避免驱动内二次复制。性能优化没有消除信任边界，攻击者仍可随时改写自己可写的CPU/DMA内存。

论文明确给出TOCTOU例子：驱动提交看似允许的packet通过firewall检查后，再修改共享packet去访问被拦截服务。解决方向是在可信内核取得稳定副本，结合checksum时的cache访问摊薄复制成本；不是checksum或加密摘要本身使原共享页不可变。

对本项目，private plan/snapshot要覆盖真正被执行的全部授权字段、间接描述符、对象列表和版本引用；检查后若仍从可变Client ring读取关键值，就没有建立相同快照语义。数据输入若允许Client持续修改，应明确定义为应用自身行为，不能让这种修改改变其他Client的地址、权限或任务归属。

SUD镜像link状态等字段并让更新与RPC顺序一致，但明确可信判断以真实内核中的状态为准。项目可沿用此原则：Client共享完成字段只是发布视图，真正任务结果和资源引用应由可信Proxy持有；不能让Client写done或ACK来决定另一任务的真实结果。

## 5. CPU接口与DMA约束

SUD直接映射获授权设备MMIO，要求范围页对齐且不与其他设备混页；x86 I/O port按TSS权限位控制。敏感PCI配置通过受控系统调用，以免恶意驱动改变地址窗口、冒用源身份或中断配置。它没有为每一种设备寄存器提供精细行为规范，设备状态损坏不属于其完整保证。

IOMMU为每个PCI设备限制DMA，只映射驱动已经可访问的实际页。因此设备不会获得比其驱动更多的主存权限。该关系比盲信驱动提交的PA更明确，但粒度仍是设备/驱动进程；同一驱动处理多个应用的数据并不因此实现应用间保密。

本项目原始Client经RMM认证，对象/实际HPA/权限/生命周期由可信Proxy检查，软件合成GPU直达HPA的Stage-1；其他设备用硬件Stage-2。SUD支持“设备访问不能超过已授权实际资源”的原则，但不替代该认证与翻译链，也不因为SUD采用x86 VT-d而要求改变本项目硬件假设。

SUD强调IOMMU不能单独阻止peer-to-peer DMA：若设备A写设备B寄存器的事务在下游直接路由，根IOMMU没有机会检查。设计使用ACS源验证和请求/完成重定向，要求事务穿过根隔离点。可迁移的是必须覆盖所有路径与master，不能把PCIe ACS本身套到Arm片上GPU互连；片上别名、共享控制器和其他设备同样需要平台隔离证据。

## 6. 中断风暴、MSI与ACK边界

不可信驱动可能不清中断条件或不与共享中断的其他驱动合作。SUD阻止驱动切回共享legacy中断，采用MSI通用控制；收到事件后向所属驱动upcall。首个事件后不立即mask，若驱动尚未声明处理完又来同设备事件，则mask，以免设备无限占用CPU，ACK再请求unmask。

这里的ACK是通知处理进度，不是业务任务成功，更不证明DMA排空。驱动重复ACK、ACK后继续制造事件和持续重新enable等行为仍需可信侧配额/状态约束。论文没有提供按GPU job绑定的cookie/epoch协议，不能从设备级MSI归属推导多Realm完成消息可信。

x86 MSI本身是向特殊物理地址写入。只改设备MSI配置无法阻止驱动利用普通DMA写同一区域来触发中断。SUD设计在Intel上进一步使用interrupt remapping禁用该设备的MSI，或在AMD上移除该设备MSI页映射；这补充了“控制正规通知配置之外，还要控制可等价触发通知的路径”的原则。

重要原型限制：测试机VT-d没有interrupt remapping，MSI范围又有隐式恒等映射，因此作者明确承认该配置仍可被恶意DMA到MSI地址造成活锁。论文随后称测试均安全约束，只能解释为已运行用例，不能覆盖前述承认的攻击。本报告保留这个证据冲突，不把设计机制写成已在原型全验证。

对项目应从可信Proxy接收持久IRQ127、读取真实状态、关联native fence和具体任务开始，阻断不可信CPU/DMA对根配置、关键MMIO和通知状态的等价伪造。无需照搬MSI，但同样要分离事件来源、任务终态、通知消费和可用性控制。

## 7. 恶意不响应、终止与资源回收

SUD的进程模型使kill/restart和内存/CPU配额较易操作；同步请求可中断、异步调用不在spinlock中等待，是对恶意不响应有价值的防护。但“CPU进程已退出”不代表设备已停、已排队DMA消失或先前输出有效。

论文修改DMA接口以提供IOTLB刷新、指定IOVA映射和地址空间垃圾回收，也提及重启驱动，但没有给出覆盖设备全部异步队列、复位失败、迟到通知与实际页再分配的完整安全回收协议。本轮未取得源码，不能从可kill的进程模型补造其具体停机顺序或漏洞结论。

项目建议把取消请求、阻止新提交、真实终止、DMA静默、映射失效、引用归零及必要残留清理分开建模。不能用Client取消、进程退出、IRQ或ACK直接授权页复用；错误或reset也不得自动转为成功终态。

## 8. 实现与artifact范围

原型基于x86-64 Ubuntu Linux2.6.30-5，修改部分DMA接口并增加模块。作者实际运行e1000e、iwlagn5000、ne2k-pci、snd_hda_intel、EHCI/UHCI及部分USB设备驱动，不需修改这些驱动源文件。并未给出完整GPU驱动原型；部分旧graphics driver绕过标准DMA接口会导致失败，而非获得未授权访问。

| Figure5组件 | 新增行数 |
| --- | --- |
| Safe PCI access | 2800 |
| Ethernet proxy | 300 |
| Wireless proxy | 600 |
| Audio proxy | 550 |
| USB host proxy | 0，复用core |
| SUD-UML runtime | 5000，不可信侧 |

“约4000行两个模块”对应通用PCI控制加选定类别proxy，不是所有类别加总，也不是完整Linux/硬件TCB。每进程约3MB RAM不含UML kernel text。superpage减少TLB成本、硬件queued IOTLB invalidation和细粒度设备/队列委派都属于后续方向，不能算已实现优化。

官方会议页与作者主页提供全文/幻灯片，作者全文hash相同；猜测项目URL`pdos.csail.mit.edu/archive/sud/`返回404，限定主题GitHub搜索零结果。本轮没有取得可确认匹配的代码，不把此搜索范围扩展为源码从未公开，也不声称源码审计或复现成功。

## 9. 性能证据与开销口径

作者用Thinkpad X301、1.4GHz双核Centrino跑e1000e，与2.8GHz双核Pentium D机器通过千兆交换机相连；netperf配置目标为99%置信度下5%精度。下面是Figure8原值，CPU数字是占用率，变化的百分点和相对百分比必须区分。

| 测试 | 内核驱动吞吐→SUD | 吞吐变化 | CPU占比→SUD | CPU变化 |
| --- | --- | --- | --- | --- |
| TCP STREAM | 941→941 Mbit/s | 0% | 12%→13% | +1百分点；相对+8.33% |
| UDP STREAM TX | 317→308 Kpacket/s | −2.84% | 35%→39% | +4百分点；相对+11.43% |
| UDP STREAM RX | 238→235 Kpacket/s | −1.26% | 20%→26% | +6百分点；相对+30% |
| UDP RR | 9590→9489 transaction/s | −1.05% | 5%→10% | +5百分点；相对+100% |

TCP receive buffer87380B、send buffer16384B；UDP用64B包。TCP大流量可批处理，短request/response每次睡眠/唤醒代价显著，论文指出唤醒可达4微秒。摘要8–30%的CPU范围不覆盖RR翻倍；“同吞吐”也不是零成本。实验不是GPU吞吐、CVM中断协议或本项目glmark结果。

作者安全评估包括检查实际I/O页表，测试任意DMA、部分interrupt storm与坏upcall行为，并记录USB错DMA触发fault、无线handler未执行而反复unmask的开发故障。没有完整输入矩阵/原始代码让本轮复核全部攻击覆盖；尤其缺interrupt remapping的MSI活锁缺口不得被正常用例PASS覆盖。

## 10. 与Glider和CCA GPU设计的结合

SUD主要将整个驱动隔离在独立进程，保护可信OS免受驱动/设备破坏；Glider进一步拆分资源管理和隔离，让每应用拥有库，减少跨应用共享状态。两者都不等价于机密计算，可信Proxy集中管理仍可能需要整个驱动可信，必须按实际可绕过路径评估TCB。

项目第一部分可借鉴批量异步消息、共享ring及复用原生驱动，但保留可靠唤醒、背压、资源恢复和正确性；短任务应量化CPU/调度成本，不能仅比较吞吐。第二部分将TOCTOU和等价触发路径纳入内存/中断共同威胁模型，而不是分别说“有SMMU”和“中断由Proxy转发”就结束。

结合PORTAL可信服务、ACAI身份与归属、PhantomMap实际页生命周期时，可形成同一事务证据：认证Client提交固定快照，授权实际页与计划，可信执行产生终态，再发布Client绑定记录。中断可以合并或重复，查询恢复遗漏，ACK只推进该Client消费游标；接受成功记录必须能追溯同一job的可信成功终态。

最优先核查四类边界：可变共享命令和间接地址；未经过隔离点的CPU/DMA/固件路径；驱动ACK或事件风暴对其他Client进展的影响；退出/reset后的在途访问与旧generation。这里是由文献提出的验证计划，不声称当前基线存在已证实绕过或本轮已执行攻击。

## 11. 研究判断与后续设计

SUD的价值是把“恶意驱动”从异常崩溃模型提升到主动规避隔离的模型，同时关注设备侧DMA、peer-to-peer和MSI旁路；其原型也显示抽象设计与实际平台保证必须分开报告。对本项目应在既定可信硬件/固件假设内验证这些路径，不纠结载板能力，也不掩盖未验证项。

建议把共享GPU协议写成有界可信处理加可恢复状态：硬IRQ只完成必要采样/屏蔽，进程上下文按Client预算处理队列；终态私有保存后再通知；超时、取消、故障和成功分别记录。公平性、有界延迟需要可信调度/计时假设，不能从内存隔离自动推出，数学计算正确性同样不由IRQ或fence证明。

形式化/状态机检查可覆盖重复/伪造ACK、队列索引越界/回绕、copy后再修改、旧epoch重放、队列满时覆盖、控制面绕过和回收竞态。需要完整实现、测试及与直接CCA/GPU论文的差异比较才能支持原创贡献，本轮只是文献和设计分析。

统一记录：恶意驱动/DMA/中断全文与来源核对及Notion回读｜glmark未测→未测｜绝对分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id，证据位于`build/cca-gpu-followup-20261027/`｜保留为可信I/O支撑研究，匹配源码和本项目验证待完成，整体研究继续。
