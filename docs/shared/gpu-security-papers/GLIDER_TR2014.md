# Glider：不可信资源管理、可信隔离与共享GPU中断归属

研读日期：2026-10-28。完整阅读作者公开技术报告13页、§1–8及66条引用，九页架构/接口/实验图表可视核对。核对作者出版列表、arXiv版本和同名代码搜索结果；未取得可确认匹配的实现，没有构建、硬件或攻击执行。本文是GPU驱动隔离支撑研究，不是Arm CCA或GPU TEE架构。

## 1. 书目与证据来源

| 项目 | 内容 |
| --- | --- |
| 标题 | Glider: A GPU Library Driver for Improved System Security |
| 作者 | Ardalan Amiri Sani、Lin Zhong、Dan S. Wallach |
| 发表状态 | Rice University Technical Report 2014-11-14；不写作已核验会议论文 |
| 作者书目 | [publications](https://www.ics.uci.edu/~ardalan/publications.html)，明确列为Technical Report |
| 版本入口 | [arXiv:1411.3777v1](https://arxiv.org/abs/1411.3777v1)，2014-11-14 |
| 全文 | [PDF](https://arxiv.org/pdf/1411.3777v1)，本轮下载入口未显式带v1，但摘要页及PDF水印均确认v1 |
| PDF SHA256 | `cb34a3a2a83a24c096cb499e2c411fa65d13c0956fe48f22255837f6a0acf24a` |

PDF严格解析13页，独立PDFium渲染第3–11页并阅读。提取器提示部分Type1字体缺fontTools，表格/图像直接核对，不把文本提取当逐字符无损。本文所有性能为作者结果，不是本项目新测量；没有因使用Xen GPU直通就把它视为机密虚拟机实验。

## 2. 动机、目标与信任基础

传统GPU内核驱动混合资源管理和资源隔离，接口多、共享状态复杂，一处漏洞可能影响内核与其他应用。Glider把资源管理做成每应用地址空间中的不可信device library，把资源导出、权限与切换留给可信device kernel；这不是只将同一个全局驱动搬到共享用户进程。

作者主要处理恶意应用/库通过驱动或设备跨应用破坏隔离的风险。OS内核、device kernel、必要硬件保护和GPU隔离语义仍可信；没有恶意Host模型、远程证明、Realm身份认证、内存加密或对固件供应链的完整保护。TCB减小是风险降低证据，不等于已证明系统无漏洞。

核心创新是明确“资源管理可以不可信，资源隔离必须可信”，并提出三项所需性质：内存隔离原语、不会改变隔离的设备管理接口、可归属的中断。硬件只是这些性质的实现载体；对本项目应核对可信Proxy能否实现对应约束，而不是按实验板是否支持某项特性否定设计假设。

## 3. 资源管理与隔离如何分离

device kernel负责加载固件、初始化GPU/内存保护/显示和中断，按调度epoch把资源bind给某个库，再revoke。每应用库实现buffer分配与管理、command构建、OpenGL/OpenCL相关接口，拥有自己导出的内存与ring。减少应用与驱动间syscall及拷贝，是性能收益来源之一。

不要混淆其调度epoch与本项目用于防旧请求复用的session epoch：前者首先是某一时间段的资源占有，论文没有因此自动具备认证generation、防重放或跨重启唯一性。现代多上下文设备也不能简单套用“当前占有者就是所有事件来源”。

对单执行上下文，bind允许更新ring位置和触发寄存器；revoke阻止继续触发，等待正在执行的命令结束，保存库所改寄存器，重置command processor并刷新cache，然后切换。其GPU不支持执行抢占，因此revoke会阻塞；报告没有建立恶意长任务或挂死情况下的有界撤销保证。

即使禁止新doorbell，已被设备读取的ring、间接命令和DMA也可能继续执行；等到何种硬件条件才可改根配置和复用资源是安全论证的一部分。本报告提出该核查要求，不声称已在Glider中复现不安全切换。

## 4. 系统内存、设备内存与实际页

系统内存由OS分配，device kernel只允许把当前库获配的页映射到IOMMU，并pin住页。公开API为`iommu_map_page(vaddr, iaddr)`，可信内核根据进程VA解析实际PA；不允许应用直接声称某个物理地址归自己。切换时保存/替换映射，可通过根页表切换降低成本。

Radeon原型使用系统IOMMU；Intel原型使用GPU内置IOMMU并由device kernel控制页表。Radeon本地显存不经过系统IOMMU，另由memory controller分段，每库连续一段；动态ballooning未实现。Intel无独立设备内存，因此相应显存分配接口不实现。两种数据路径必须分别约束，不能仅因有IOMMU就声称所有GPU访问已隔离。

项目中相应原则应提升为RMM认证原Client、对象及实际HPA归属校验，再按权限和生命周期软件合成受保护GPU Stage-1。Glider的可信OS进程VA→PA解析不能替代恶意Host模型下的IPA→HPA授权；其pinning也不能替代撤销、引用归零和安全页回收。

当前库原型启动预分配并映射约20MB，依据基准经验设定；按需映射仅是替代方案。它可以启发对象/计划缓存，但不能据此证明任意负载容量或最小授权。本项目缓存应绑定身份、权限、实际页及generation，旧根/旧计划失效必须可检查。

## 5. 寄存器、指令与显示控制

不可信库只有`access_register(reg, value, is_write)`所允许的寄存器访问。作者采用授权列表，而非直接映射整页，因为一页常含合法和敏感寄存器。初始化、隔离和固件等敏感接口留在可信侧；显示模式涉及电压、时钟、thermal controller和BIOS调用，也保留在device kernel，通过高层set_mode请求访问。

低层接口不天然更安全。列表需要区分读写、位域、访问宽度、间接寄存器窗口、状态依赖与多寄存器操作；一个接口也能表达大量危险动作。论文没有公开足够实现证据让本轮独立确认所有别名和命令处理器旁路都被覆盖。

§7.3尤其值得保留：作者认为Radeon命令只能写processing-unit寄存器，不能改memory controller；但观察到原驱动拒绝过大寄存器编号，因文档未列对应寄存器而推测是正确性检查，故不在可信内核保留。该推测不是所有未文档化行为均无安全影响的证明；库中保留检查也无法约束恶意库。

项目应通过可信private plan/snapshot、命令白名单或明确的设备执行权限边界约束敏感操作。不能仅把高层IOCTL变成“寄存器号+值”并宣称攻击面已缩小；也不能假定CPU MMIO保护自动覆盖GPU内部MCU或固件命令路径。可信固件加载假设需明确列入平台保护。

## 6. 中断归属与共享内存轮询

论文将attributable interrupts列为必要性质。单执行上下文中，作者据“设备此时只属于一个库”把中断归给当前库；多上下文扩展要求接口独立、上下文隔离以及低层DMA可归属。报告没有详细建立跨上下文job身份、迟到中断、共享错误IRQ和reset事件的认证协议。

单占有者简化归属，但切换边界仍需处理：旧任务已经终止而IRQ尚pending、合并IRQ携带多个原因、错误和完成同次发生、通知页留有旧计数。只按handler运行时的current owner转发，不能独立证明事件来源。这里是待验证场景，而非已确认Glider漏洞。

性能实现比较OS signal、syscall polling和共享内存polling。前两者代价较高，最终使用共享内存轮询；Radeon在产生中断外还向内存页写中断信息，库轮询该页。upcall和硬件interrupt remapping为考虑中的替代设计，不是已实现结果。

这个通知页不自动成为可信成功凭据。其CPU/DMA写权限、设备写入来源、slot覆盖、cache/内存顺序、计数回绕及跨绑定生命周期均须定义；不可信库读到任意值不应改变其他Client状态。机密共享GPU还需防Host篡改或重放，Glider没有提供对应Realm协议。

本项目可复用持久IRQ127入口与真实native fence，由可信Proxy先验证具体任务终态，再记录身份/epoch/cookie绑定结果，最后通知Client读取。IRQ到达、任务成功、结果数学正确、DMA静默与安全复用必须分开；ACK只能消费授权通知，不得反过来证明任务成功或授权回收。

## 7. 实现与artifact边界

作者从原Linux驱动拆出device kernel和device library，使用部分User-Mode Linux符号适配，让旧kmalloc等代码运行在用户库中；把约20处libdrm、xf86-video-ati、GalliumCompute调用从syscall改为函数入口。Radeon新增约4kLoC、修改49文件；Intel约2kLoC、修改30文件，两者各新增两文件。复用减少重写，但隔离边界仍需深入了解原驱动。

Radeon作者称完整实现，Intel明确仅proof of concept，且未实现其设备切换测量所需功能。不能把两种GPU统一描述为已验证完整共享方案。32位x86 shared library没有遇到汇编PIC问题，也不能证明Arm驱动可无改动直接搬用UML适配。

本轮GitHub精确主题搜索只返回`xbitlet/Glider`；检查固定`2146023643c0b8c8b935c9cd944e08becb72e7fe`完整树仅`.gitignore`、`LICENSE`、`README.md`三项，README仅标题，创建于2025年且没有作者关联证据。它未被冒充论文artifact。作者书目与本轮全文未给出已成功取得的匹配实现；这不是“代码从未公开”的全局断言。

因此本轮源码结论限于报告中的伪接口和架构描述，不声称审计真实Glider驱动、编译通过、漏洞复现或性能复现。搜索记录与来源保存在证据目录。

## 8. TCB与安全评估的分母

| Table1 | Legacy | Glider | 作者报告降幅 |
| --- | --- | --- | --- |
| Radeon全部文件kLoC | 55 | 36 | 35% |
| Radeon仅源文件kLoC | 34 | 18 | 47% |
| Radeon API数 | 56 | 9 | 84% |
| Intel全部文件kLoC | 39 | 24 | 38% |
| Intel仅源文件kLoC | 30 | 17 | 43% |
| Intel API数 | 68 | 7 | 90% |

表格为四舍五入值，作者百分比不宜拿整数重算后当精确原始数据。正文估计显示相关代码占device kernel约一半，但与表中四舍五入分母不完全对齐，不据此给出更精细比例。比较前人工裁减legacy对其他GPU/音频/debugfs等支持，是条件之一。

API统计含七个应用接口和两个scheduler入口，Intel因无独立显存少两个；不是七/九个等价风险点。36k/24k也不是全系统TCB，未含完整OS、Xen、硬件与可信固件。评估主要为代码量和入口数量，没有系统攻击矩阵、形式化隔离证明或残留泄漏测试。

## 9. 性能、轮询成本与切换测量

作者在i7-3770、禁用HT、2核/2GB、32位PAE Ubuntu12.04/Linux3.2.0下测Radeon。为使用系统IOMMU，Radeon直通到Xen VM；隔离一个CPU、绑核并用最高调度优先级减少干扰。这不是多机密VM并发共享实验，也不是当前Arm软件Stage-1方案的开销测量。

OpenCL方阵阶数1/16/128/256，每次1000迭代、丢弃首轮、不计kernel编译，重复五次。图3小矩阵时间约降至原生0.5–0.6倍，大矩阵近似相同；此处是图像近似读数，没有原始数值表，不宣称精确加速倍数。收益依赖调用密度和固定开销比例，不能扩展到所有GPU计算。

OpenGL茶壶Vertex Array和Display List各测五分钟，每秒采FPS，重复三次，论文称丢弃前五frames。Vertex Array较快、Display List接近，图4展示10/90分位、中位数及最小/最大值；Glider有更低的罕见最小帧率，作者归因OS调度。不要将Vertex Array概括成所有OpenGL immediate mode，关键区别是每帧提交与缓存复用。

| 作者CPU时间占比 | Legacy | 共享内存轮询Glider | 变化 |
| --- | --- | --- | --- |
| Vertex Array | 53.7% | 75.3% | +21.6百分点，相对约+40.22% |
| Display List | 41.7% | 71.6% | +29.9百分点，相对约+71.70% |

syscall polling时CPU占比为54.3%/35.3%，中位FPS为193.3/231.5，低于共享内存轮询。作者尝试给legacy加类似轮询未改善性能，据此支持减少调用开销的解释；没有充分消融排除所有调度/轮询交互因素。FPS竞争力与CPU效率不能合并为“无成本”。

库初始化Radeon为109±7毫秒、Intel为66±0.3毫秒，UML slab预热还带来启动初期性能差异。Radeon切换报告42±5微秒，含保存/恢复寄存器、IOMMU切换、CP reset和cache/TLB刷新；Intel未实现切换。revoke另需等执行结束，文中未给出恶意长任务或积压情况下等待的单独分布，所以42微秒不能作为任意撤销总时延或安全回收时限。

## 10. 与本项目两部分的结合

第一部分“直通/共享实现与性能”可以借鉴把复杂高层管理留在Client、把热路径变成经过授权的直接操作，并缓存可复用计划。当前项目已有GPUVM、private plan/snapshot、原生执行链和通知优化，优先提炼这些边界，不必为重现Glider另搬整套驱动到UML或增加任意MMIO RPC。

第二部分“任务隔离”则把Glider三项前提具体化：内存是原始Client与实际HPA/权限/生命周期；接口是根配置、敏感MMIO、命令/固件控制面的不可绕过约束；事件是任务来源与可信终态记录。PORTAL支持可信服务组织，ACAI/PhantomMap补足身份与实际页生命周期，SeCloak/Viola补充中断控制和通知性质，均不能单篇替代完整协议。

在项目假设下，ProxyRealm集中SMMU授权、软件IPA→HPA合成GPU Stage-1、其他设备硬件Stage-2的结构可以保留。Glider提示应进一步说明：谁能影响已检查命令、缓存计划何时失效、跨Client切换如何阻断旧DMA，以及关键状态由谁最终确认。可信Proxy有完整驱动并不自动实现最小TCB，应明确哪些组件必须可信、哪些仅影响本Client功能。

## 11. 建议的研究增量和验证

可形成“可信资源租约”状态机：申请与认证、准备映射/计划、绑定、提交/运行、可信终态、撤销/排空、失效/清理、释放。租约绑定Client/session、context、map generation和允许命令范围；缓存只能在对应版本和权限仍成立时复用。这里是项目设计建议，不是Glider已有机制或当前运行基线的新增实现。

事件路径独立维护pending任务及权威完成记录，允许IRQ合并和重复唤醒；查询负责恢复丢通知，去重负责避免重复完成。切换时旧epoch的IRQ和ACK不应落到新Client；共享设备错误可以影响多个任务，但要逐个确定结果，不能把全局错误归为当前一个任务的成功。

撤销需区分“停止接收新提交”和“已提交任务不再触碰资源”。对无法确认DMA排空的失败情形保持隔离，不能只改页表根后立刻复用实际页。测试应覆盖恶意长任务、超时/reset、迟到IRQ、旧ring持续运行、映射复用、队列满、共享错误、跨Client ACK和计划变更；本轮没有执行这些测试。

性能验证应同时报告吞吐、延迟分布、CPU占用、通知次数和恢复成本，分开评估真实fence观察、轮询、IRQ合并及缓存效果。不能仅用API数、TCB行数或FPS上升宣称安全/效率整体改善；当前glmark历史成绩保持原有可比条件，不为文献整理产生新的提分归因。

本轮后续引用候选为SUD《Tolerating malicious device drivers in Linux》、Dancing with Giants及可信路径工作；只有拿到全文并独立分析才计完成。与本项目的原创性仍需对照直接CCA/GPU论文及未完成候选，不能因Glider2014未处理Realm身份就直接宣称新颖。

统一记录：GPU驱动分离/中断归属全文与来源核对及Notion回读｜glmark未测→未测｜绝对分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id，来源和回读证据位于`build/cca-gpu-followup-20261027/`｜保留为支撑研究，匹配代码未取得，整体研究继续。
