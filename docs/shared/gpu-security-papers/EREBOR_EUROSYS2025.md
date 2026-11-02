# Erebor：不可信CVM内沙箱、可信中断边界与输出封装

## 1. 论文身份与证据范围

Chuqi Zhang、Rahul Priolkar、Yuancheng Jiang、Yuan Xiao、Mona Vij、Zhenkai Liang、Adil Ahmad，Erebor: A Drop-In Sandbox Solution for Private Data Processing in Untrusted Confidential Virtual Machines，EuroSys 2025，1210–1228，DOI [10.1145/3689031.3717464](https://doi.org/10.1145/3689031.3717464)。Crossref精确元数据、两位作者出版列表交叉核实。[作者全文](https://chuqiz.com/papers/erebor_paper.pdf)、[作者出版页](https://chuqiz.com/publications)、[公开实现](https://github.com/ASTERISC-Release/Erebor)。ACM直连403；作者托管PDF含ACM下载封面与正式DOI/页码，未与本轮ACM服务器文件逐字节比较。

本轮完整读20个PDF页：封面1页＋正式论文19页，§1–13、97条参考文献、附录A.1–A.5，10图7表1个Listing；PDF第3–14页共12页视觉核对，覆盖所有图表/Listing。PDF3095549字节，SHA256为b185f8c1713eaa7f8077e34338c3f467e1b159f0d28dd7e532306ca853af6029。作者slides已获取，仅作后续材料，不宣称已精读。

代码固定90cb27645860166e93eb08fef44486ee1e224265（2026-02-06，晚于论文），13个选定blob长度/Git SHA1/SHA256核验。递归总树68472项且truncated=true，不能称完整仓库树；补读完整根树8项、kernel第一层及nk完整6项、sva头目录完整13项，固定路径取文件。4个raw超时由Git blob API恢复，失败保留。README、enc/idt/pks、enc头及stack门宏完整读；大mmu、入口汇编、驱动和部分头定向静态读，不是全内核/全部配置/LibOS/启动加载器审计。无构建、作者程序、VM、模型或攻击执行。

## 2. 为什么与CCA/GPU项目有关

Erebor研究“CVM内的服务软件也不可信”：TEE保护整个VM免受Host读取，却不能阻止服务程序主动把Client秘密写出。其贡献是内核内特权分离、双向沙箱边界及由monitor控制的数据出口。它与PORTAL可信服务、VeriSMo共享内存/验证、Tyche可组合域和寄存器可见性互补，但不是Arm GPU直通架构。

论文§3.1明确只支持CPU应用，排除FPGA等异构加速器并把可信I/O列为互补工作；llama.cpp用CPU，不能将13.15%解释为GPU开销。表7列出CCA迁移所需的EL1/VBAR、PXN/PAN、PIE、BTI/GCS等接口，是架构兼容性讨论，非已实现Arm/CCA端到端安全或GPU实验。

项目继续接受RMM认证原始Client、可信ProxyRealm控制SMMU、实际HPA归属/权限/生命周期校验及软件IPA→HPA翻译合成受保护GPU Stage-1、其他设备授权Stage-2、页表/根/MMIO与可信固件保护的假设。硬件用于机制测试/模拟，不因实验平台缺少某项能力否定研究设计；同时明确哪些证据只是功能模拟。

## 3. 威胁模型：主动泄漏与正确结果分别讨论

Client不信服务商、云商和其他Client；服务商控制应用及Guest OS，云商控制Hypervisor，双方可串通。论文称服务商honest-but-curious，提供功能正确服务，但同时允许程序主动利用系统调用、异常或用户中断泄漏秘密。应理解为“业务输出正确性被假设，隔离边界面对主动泄漏行为”，不能直接推广成任意恶意计算仍输出正确结果。

AV1为OS读取内存/寄存器或转共享后DMA窃取；AV2为程序直接文件/网络泄漏；AV3为参数、次数和用户中断编码。数字时序与微架构侧/隐蔽信道、物理信道排除。§4.1还假设CVM硬件无缺陷或已修复，恶意中断注入问题已被防护；信任远程证明、启动固件及存在时的paravisor。不能用该论文声称解决Heckler/WeSee全部攻击。

论文限制部分软件出口并不等于完全无观察信息。异常导致kill、输出是否产生、次数、处理时间、调度、共用缓存等仍需明确公开边界；固定长度也不消除输出时间和消息次数泄漏。§3.2称后文§12讨论缓解，实际讨论段在§11，应按内容阅读而非误认存在额外证明。

## 4. monitor如何约束同为ring0的内核

可信monitor与非可信内核同在ring0，借敏感指令插桩、受保护页表/PKS及CET形成虚拟特权层。控制CR0/3/4、MSR、stac、lidt、tdcall，管理页表、权限、系统调用/异常入口、共享页转换及证明请求。其思路是把敏感操作变成必须校验的入口，而非信任调用者自行遵守协议。

设计采用两阶段启动：先度量固件/monitor，再由monitor扫描内核可执行区中的敏感字节序列，随后加载和重定位；运行时以W⊕X、SMEP和页表保护阻止注入。完整论证需覆盖重定位/动态patch之后的最终可执行字节、跨页指令、别名、入口边界和所有允许的更新；本轮没有读到完整加载器证明，不将文字流程视为形式化验证。

设计可扫描动态模块/eBPF后加载，但论文原型为简化实现禁用二者，text_poke需经过monitor。所谓drop-in指不要求另造Host安全管理机制；评测仍使用支持PKS虚拟化的Intel KVM，官方README要求打PKS虚拟化补丁。不能写成“任意现成Host无需配置即可部署”，也不因补丁需求否定其客体内部机制。

## 5. EMC入口、出口和中断期间的权限

EMC入口保存scratch寄存器，开放本CPU monitor页权限，切到受保护每核栈；出口逆向恢复。CET IBT限制间接跳转只能到endbr64入口，shadow stack限制ret/iret绕入中部。设计要求控制CET与PKRS等配置，且不允许任意其他monitor字节成为合法入口。

关键是中断可能在临时开放权限后发生。论文中断gate先保存寄存器与旧PKRS、撤回monitor访问，再交给OS handler；返回前恢复受保护状态。它保护的是“CPU被打断后，非可信处理者不能继承临时特权”，不是证明该中断来自某个GPU任务。

论文§7明确Linux原型只有前向IBT，省略后向shadow-stack检查。因此依赖完整HW-CFI的C4论证与原型评测必须分开。附录的功能运行不能弥补该差距；作者称后向检查预计开销低，也不是测得完整防护成本或已证无漏洞。

## 6. confined/common内存与共享只读模型

每沙箱对应单Client，程序和LibOS共地址空间；进程转为线程，初始化时确定线程上限、预分配私有内存和文件。confined页独占可写，不映射给其他沙箱/内核，固定页防换出；common模型/数据库/库页在敏感输入到达后对沙箱只读，允许共享以节省内存。SMAP/stac控制限制内核读取当前用户页，设备访问由tdcall共享转换控制。

“对沙箱只读”只证明沙箱不能用内容写回作为出口，未单独证明外部拥有者不能改变common内容、替换模型或操纵计算。因此共享对象需同时声明来源、版本/摘要、所有可写别名及输入到达后的冻结规则；若模型权重也要保密，Erebor的“common不含秘密”假设不能直接沿用。

单映射政策是CPU原型手段。项目可以支持显式共享和多GPUVA别名，但必须按实际HPA集合证明所有CPU/GPU/其他设备权限和生命周期一致。GPU固定Stage-1仅解决地址访问约束，不能靠给对象标readonly省略所有映射和命令访问权检查。

## 7. 数据进入后的出口收敛

设计在接收秘密后禁止普通syscall、同步VM exit及用户中断，非法退出杀死沙箱。LibOS承担私有heap、内存文件系统、预建线程和spinlock同步；cpuid结果预先缓存。网络只能经monitor的专用ioctl传输，不能让应用自行发送任意网络/日志。

这套策略适合自包含请求响应应用，不直接支持任意动态设备驱动和复杂服务依赖。移植GPU场景时应保留必要的可信提交/等待/发布接口，而不是照搬“所有系统调用都禁止”；接口参数、频率和错误字段的可见性需要明确，否则通知队列也可变成出口。

还需解释运行期common页fault与表6持续#VE的类别：论文同时描述秘密进入后同步#VE杀死沙箱，表6却列每秒0.7k–1.7k #VE和confined之外页fault。统计可能包含初始化、非沙箱或不同路径，但没有核实匹配采样脚本前不能替作者统一，也不能仅凭该表宣称禁止退出无效。

## 8. 可信结果发布与远程身份

设计只让monitor请求证明，用度量和认证密钥交换建立Client-monitor通道；非可信Proxy只转密文。monitor将输入送入对应confined页，只把输出加密返回原Client；固定长度padding限制尺寸泄漏。结束后清理页、文件系统及线程上下文。

monitor度量本身不自动绑定某个Client请求、沙箱实例及输出接收者。项目应把认证Client、会话/任务ID、Proxy实例、设备reset epoch、策略/固件度量、fresh nonce以及允许发布端纳入协议；认证消息顺序/防重放与应用结果正确性分别处理。合法输出只能发回原授权Client，不能由应用临时指定其他目的地。

原型与附录明确用不可信明文debugfs模拟通信，未实现上述完整网络通道；因而C5的架构主张不等于artifact已经提供端到端机密传输。只阻止printf不证明没有泄漏，且固定长度不等于固定次数或时间。项目已有可信共享队列是否需要加密，应由实际页可见性决定；即使无需密文也仍需身份、完整性和实例绑定。

## 9. 固定源码：身份与生命周期的实际限制

所读`enc.c`的_assign_enc_id返回g_enc_id，其初值1且函数留有增加值TODO，未递增。由此不能把该文件当作独立多Client身份分配实现；页面encID相等检查若都取同一值，也不足以区分实例。表项按current->pid索引，调用者身份还依赖非可信内核任务元数据，不能迁移为RMM认证Client的替代品。

claim_memory把物理页描述符标为PG_ENC并记encID，原unused页检查被注释；该路径依赖上游准入，需完整调用链才能判断可控范围。exit helper只清enc_id/activate。驱动分配CMA页确有memset初始化，释放函数检查page_count后归还页，但所读函数未见论文所述释放前清除数据、全部映射/上下文和可信引用的完整协议。不据有限路径声称全仓库没有清理，也不把非可信分配器清零当可信安全回收证据。

项目应复用RMM认证队列、BO/GPUVM引用和cookie/epoch，不能以可重用PID或固定encID授权。页转交须停止新提交、等待在途GPU/DMA及映射缓存失效、排空引用、清残余，最后再交给新Client；reset/超时/退出不是静默证明。

## 10. 固定源码：syscall与寄存器保护

`SM_do_syscall`只对特定ioctl魔数处理，其filter段明确为了debug/benchmark不实际过滤已activate沙箱。`entry_64.S`的沙箱入口调用该函数，返回特定值才跳过普通do_syscall_64；因此这不是只凭孤立unused helper推测的差距。但仍未运行匹配配置或构造越权调用，不把静态发现写成复现PASS。

`SM_save_restore_pt_regs`注释称当前不混淆寄存器，实际只memcpy，入口汇编先把寄存器复制到普通OS栈；没有执行注释所述的非参数寄存器屏蔽。设计需要同时保护读取和篡改，拷贝到安全栈只满足其中一部分。该调用链不能作为论文所有中断/系统调用上下文隐私的已实现证明。

IDT wrapper与stack宏存在中断重定向，但所读SECURE_INTERRUPT_REDIRECT没有展示论文完整的“受保护保存PKRS→撤权→OS处理→恢复”流程。TDCALL出口宏还留有debug用or0、注明以后恢复or8；实际构建选项及其他保护未完整审计。普通SECURE_ENTRY已用RDTSCP按核计算栈偏移，因此不能只因文件顶部旧TODO就称完全没有每核栈。

## 11. 固定源码：检查返回值必须包含修改效果

`sm_validate_pt_update`按值接收newVal，在部分encID/非confined分支执行newVal &= ~PG_RW，但只返回状态码；调用者__update_mapping随后使用自己的原val写入。所读函数返回初始状态2，局部清写权未随PTE值返回；另case1的setMappingReadOnly被注释，case0也继续更新。这些路径不足以证明common只读及失败拒绝的设计保证。

PKS页保护实现含2MiB拆成4KiB路径和16MiB静态页表池，说明当前源码已尝试论文列作未来方向的拆分，不能说它永远禁止全部大页。拆分循环的目标索引、并发/远端TLB和容量失败仍需单独核验，不能只看存在函数认定支持完整。MSR helper先写再做部分assert，也说明敏感操作应在生效前完成授权检查。

以上均限定固定公开提交，晚于论文且README标WIP；未核验Zenodo历史快照、全启动链、所有宏开关与部署二进制，不将其归为论文正式实验版本已被证明可利用的漏洞。安全分析C1–C8是设计论证，不是连接到该代码的机器检查定理。

## 12. 性能：CPU、稳态和初始化分开

评测Xeon Platinum8570、56物理核2.1GHz、Host Ubuntu24.04/Linux6.8，CVM8vCPU/24GB/100GB virtio，Guest实现基于Linux6.6。Native、LibOS-only、LibOS-MMU、LibOS-Exit和完整机制比较不同组合；不能把消融均值直接相加或独立归因组合效果。

| 数据 | 原文/本轮算术 | 不能推出 |
| --- | --- | --- |
| 空EMC vs syscall | 1224/684 cycles，约1.79倍 | 不是单次指令或GPU中断延迟 |
| tdcall/vmcall vs EMC | 5276/1224≈4.31倍；4031/1224≈3.29倍 | 正文“多3.3/2.3倍”是额外开销，不当总倍率 |
| PTE更新 | 23→1345cycles，总58.48倍、增加1322cycles | 不等于应用慢58倍，支持批处理但不取消检查 |
| TDREPORT | 126806→128081cycles，约+1.01% | 没有测安全网络输出全链 |
| 真实CPU应用 | 4.5%–13.2%，geomean8.1%；llama.cpp13.15% | 非GPU、非完整后向CFI配置 |
| 初始化 | 表6为13.3%–52.7%，总结另称11.5%–52.7% | 保留原文差异，不能无原始数据统一 |
| 非沙箱背景 | OpenSSH/Nginx平均吞吐降8.2%/5.1% | 微基准pagefault总时延可达3.8倍 |

表5 llama2-7b模型约5GB，表6common4096MB、confined501MB；实现/取整差异未由匹配脚本解决。表6总退出4.4k/s，正文近似4.5k/s；图8 caption为3.6M EMC/s，正文3.5M。不能据近似值计算精确每退出成本。图9没有完整原始数值/置信区间，不臆造统计显著性。

## 13. 共享内存节省的正确计算

用表6的4096MiB common、501MiB confined估算，8份全复制为36776MiB；模型共享后为8104MiB，约少77.96%，对应正文≈36GB→≈8GB。所谓单沙箱最多89.1%是把公共部分摊薄/排除时的边际私有占比：501/(4096+501)≈10.90%；不是整个8Client机器实测减少89.1%。

论文未给完整内存节省图及所有原始分配，不能把“0.15–9.2倍减少”转成每应用确定值，也不把公共页缓存、页表、monitor/LibOS和预留未用池忽略后声称全系统峰值。项目可以共享已认证只读模型，将KV cache、命令、可写BO和完成状态留给各Client；这种节省须在相同Client数、模型与池预算下实际测量。

## 14. 对项目的三项直接建议

第一，明确可信事件的最小公开字段。物理GPU IRQ由可信端接收，IRQ127仅通知重查；Client的native fence终态必须匹配真实任务、cookie/epoch及错误状态。中断前后的寄存器、错误日志和共享队列内容也属于隔离面，不能只检查目标VM编号。

第二，把结果发布列为独立授权转换。GPU完成后先做必要同步/可选应用校验，再把结果只交给原认证Client；多Client共享Proxy禁止用应用自填目的地跨会话发布。完成、发布、通知ACK、DMA静默和页可复用分别判定，不能因一个fence或IRQ就一次性推进全部状态。

第三，沿既有对象体系做小范围状态机验证。授权PTE必须与实际写入PTE一致、错误必须拒绝或原子回滚、Client与epoch不能在复用后混用、IRQ丢失/重复不能虚构完成；检查中断打断临时权限和保存状态时的每个位置。不要求复制PKS/CET架构，也不要求推翻已有private plan/snapshot和原生fence。

## 15. 验证计划、引用链与记录

建议负例：固定/复用Client ID、共享模型可写别名、PTE检查修改未实际提交、部分失败继续映射、请求跨页/整数溢出、临时授权后嵌套中断、错误寄存器拷到普通栈、恶意软件主动触发出口、输出换接收者、迟到IRQ旧epoch、释放后旧DMA、Host改共享payload、输出长度/次数/时间编码。以上尚未执行，不沿用历史PASS。

附录A只宣称代码可访问/可搭建和功能支持，默认普通VM、TDX可选，给出LMBench/helloworld/CPU llama三个实验，并提示原型可能panic需重启。它不证明全部C1–C8或性能可复现。Zenodo14943102作为历史归档入口保留，本轮未获取比对；后续沿Ryoan、Chancel、Veil、NestedSGX、Nested Kernel、Gramine-TDX追踪并与已有文库去重。

证据在build/cca-gpu-followup-20261027：acquisition104–108清单、作者/出版元数据、20页文本、12页render、固定root/nk/sva树和13blob、定向阅读及算术、Notion全文回读和父页保护审计。多个猜测主页404/DNS失败、同名非研究者网页及空搜索均保留，不用作论文结论证据；ACM403不影响作者全文阅读。

统一记录：全文/97引用/10图7表1Listing/附录/12页视觉/13固定blob选读/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者程序、构建、VM、模型、硬件或攻击run-id｜保留研究；完整CFI、端到端输出、当前源码隔离和GPU扩展分别待验证。
