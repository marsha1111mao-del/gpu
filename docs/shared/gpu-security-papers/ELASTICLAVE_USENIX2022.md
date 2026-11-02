# Elasticlave：互不信任TEE之间的共享权限、原子转交与可信通知

研读日期：2026-10-27。完整阅读USENIX正式PDF的19页（封面加会议录4111–4128页）、65条参考文献，以及单独发布的3页artifact材料（封面加附录269–270页）；定向静态阅读作者评估提交中的Monitor权限、区域、PMP、IPI与SBI路径。未执行源码、模拟器、攻击或硬件实验。未改运行代码，无新增性能测量。

## 1. 书目、版本和证据来源

- 题名：Elasticlave: An Efficient Memory Model for Enclaves。
- 作者：Jason Zhijingcheng Yu、Shweta Shinde、Trevor E. Carlson、Prateek Saxena。
- 第31届USENIX Security Symposium，2022年，4111–4128页；ISBN 978-1-939133-31-1。使用会议官方书目信息，不补造DOI。
- [正式论文页面](https://www.usenix.org/conference/usenixsecurity22/presentation/yu-jason)；[正式全文](https://www.usenix.org/system/files/sec22-yu-jason.pdf)；[单独artifact附录](https://www.usenix.org/system/files/usenixsecurity22-yu-jason.pdf)；[公开实现](https://github.com/jasonyu1996/elasticlave)。

正式全文1308350字节，SHA256 c3454bc62902573df22dad9d1d3bfba632ab4fbead6195e716845e83dfaf9195。下载多次超时后按HTTP Content-Range验证分段续传，合并后严格解析确认19页、有效trailer和EOF；不是把只有PDF文件头的部分响应当作全文。artifact附录327236字节，SHA256 38d889a61231196f23b86a544e88e14956accd39f1c7ac81809051860977d8b9。原文、分页文本、范围响应及获取记录保存在build/cca-gpu-followup-20261027。

作者主页还链接作者稿，arXiv:2010.08440v1为2020年早期版本；本报告实际研读正式2022年全文，不把预印本与正式版重复计数。两个官方PDF文件名仅前缀不同，内容分别是主论文和artifact，不能互相替代。

这篇是支持研究的TEE共享内存论文，原型基于RISC-V，并非CCA GPU实现。直接价值是互不信任参与方之间的访问权与状态交接，不应将其列成又一篇已经实现安全GPU共享的系统。

## 2. 背景：为什么共享页不等于安全交互

传统spatial isolation把内存分为enclave私有与OS可访问的公共区域。两个enclave需要共享时，往往通过加密、复制与可信协调者维护通信状态；客户端、服务端和代理流水线的数据量越大，额外复制和加解密越重。

简单放宽权限有四类问题：静态共享RW允许观察或篡改处理中间态；转交所有权可能允许恶意接收者重新授权他人；owner随时改其他参与方权限会破坏后者已检查的权限视图；组合所有权转交与动态权限仍可能出现检查后权限改变。

Elasticlave将“谁能授权参与者”“各参与者最大能做什么”“当前谁能访问”分开。共享数据可以原地处理，但访问权变化必须由可信实现执行，而不是由恶意OS维护的页表或普通共享锁单独保证。

## 3. 威胁模型、TCB与安全目标

OS可以任意恶意，应用被拆分为多个enclave，任意子集可在运行中被攻陷。TEE硬件和可信软件被假定无漏洞，开发者正确把应用安全策略表达为权限；对手不能修改可信权限元数据与执行机制。

目标一是bounded escalation：没有owner明确授权的参与者不能取得对应权限。目标二是enforceable serialization of non-faulty enclaves：正确参与者预先指定的访问序列得到执行，或者安全中止；不是保证任意恶意参与者都按业务语义计算正确结果。

DoS、微架构缺陷和侧信道排除，物理RAM/总线攻击防御属正交问题。系统不能判断接收者是否可信，也不能阻止有权读取明文的恶意参与者泄露已经得到的数据。安全回收不能收回对方此前合法获得的信息。

可信边界包括m-mode Monitor、PMP强制执行、区域/权限/身份元数据及各正确enclave必要runtime。原文6814 LoC是其列出的3085行privileged实现加3729行runtime口径，不等于所有应用、依赖、密码库和平台硬件的完整TCB；引言“约7000行Monitor”的概括也应按详细表4收窄。

## 4. 三个关键抽象

每个region对应不重叠的实际物理内存，有全局uid，可以映射到各参与者的不同VA。region在其生命周期内只有一个owner，owner本人也是accessor；只有owner可以增加accessor或销毁region。

每个accessor有独立的static maximum和dynamic permissions，包含R/W/X/L。owner授权时固定该accessor的上限；其后accessor只能调整自己的动态权限，且必须满足dynamic是maximum的子集。owner不能原地改写既有上限，需要销毁整个region才能结束这些授权。

L是可信实施的独占访问位，不是共享内存中可被其他写者覆盖的普通mutex变量。有lock holder时，其他参与者包括owner都不能访问该region；没有holder时，各accessor按自己的动态权限访问。L本身不扩大R/W/X上限。

transfer把当前独占权原子交给指定且已获授权的下一accessor，不转移owner身份。它避免“先释放、下一方再抢锁”的间隙被第三方截获。形式设计要求目标已有映射；指定目标不代表重新授权此前无权的实体。

## 5. 七个接口和生命周期

| 接口 | 可信职责 |
| --- | --- |
| create(size) | 创建实际区域及uid，确立owner与权限记录 |
| map / unmap | 建立或移除调用者VA映射，可有多个alias；同一region权限作用于全部alias |
| share(uid,eid,P) | owner给目标固定权限上限，非owner不能再次转授权 |
| change(uid,P) | 调用者只改变自己的动态权限，检查上限及独占条件 |
| transfer(uid,eid) | 当前holder向合法目标原子交接L，保持owner及其他权限定义 |
| destroy(uid) | owner终止region生命周期，撤销权限、通知访问者并安全回收 |

每次接口检查资源存在和调用者权限，每次实际访问还由硬件验证当前物理权限，且要同时通过常规分页权限。API的身份检查与运行期访问强制执行互补；有uid不等于有权映射或读取。

接口设计使用不重复的eid/uid表示实例；身份可通过证明和安全通道交换，但论文没有给出覆盖GPU、驱动、固件和服务重启的完整远程证明协议。论文将所有非enclave代码视为一个实体，不能照搬为多个不可信VM之间的隔离身份。

## 6. RISC-V原型：PMP、IPI和失效完成

Monitor在m-mode保护元数据，为每个物理region配置PMP；上下文切换按当前身份装载权限。PMP位于分页后的实际PA检查点；页表VA→region、region→PA与权限元数据共同决定访问，OS单改页表不能绕过PMP。

多核权限变化可能需要同步更新其他核的PMP。设计规定发起方等待受影响核处理IPI并完成权限调整后才恢复。RocketChip会在TLB缓存PMP结果，因此更新还执行sfence.vma；所读pmp.h的PMP_SET/PMP_UNSET宏确有该指令。不能把“元数据已改”直接写成“所有核旧权限已消失”。

OS分配实际内存，Monitor验证并设置保护；释放前Monitor清零并将base/size归还OS。每region至少一个PMP entry，评估默认每核16项；每enclave一私有一共享region的示例容量为(N−2)/2。这个限制用于理解作者原型，不作为否定项目CCA/SMMU假设的理由。

主论文第8节明确尚不支持shared memory swapping：换页要同步实际页权限和所有accessor映射。CPU间访问控制、GPU页表、SMMU/IOTLB及在途DMA具有不同实现责任，PMP同步不能自动覆盖后几者。

## 7. 通知安全：哪一种确认可以证明什么

设计区分权限异常与region异步signals：销毁通知仍有映射的访问者；锁变更用于监控；transfer通知新holder。可信通知路径不依赖恶意OS决定原因，目的是让enclave知道可访问状态变化。

评估提交的IPI_TYPE_PMP处理实际权限调整，IPI_TYPE_REGION只调用region_ipi_update/dispatch_events_unlocked设置SSIP；send_encl_ipis(sync=1)等待目标mailbox的pending清零。这个ACK表明对应Monitor IPI处理已结束，不证明应用handler已消费记录，不证明业务结果正确，也不证明GPU job成功或DMA已经quiescent。

region_events_add按uid合并事件，已有同uid记录会被新type覆盖。它是区域状态变化通知，不是每次transfer都保留的不可丢失事务日志。不能从一次signal推导准确完成了多少job，或把通知次数作为exactly-once完成证据。

对本项目，persistent IRQ127及既有认证队列可继续承担唤醒和传输基础；实际完成、错误、取消、ACK与reset分别读取可信状态、匹配Client/对象/任务/epoch后执行相应状态转换。通知路径可信与通知能够授权何种副作用，是两个需要分别论证的性质。

## 8. 固定artifact和实际核验范围

artifact附录指定评估提交29aab39，已解析并固定为29aab3993f2c4c28b4c59053ecd1fb44a448012f；[评估快照](https://github.com/jasonyu1996/elasticlave/tree/29aab3993f2c4c28b4c59053ecd1fb44a448012f)。完整递归tree有820条且未截断。另查到HEAD 196d8e343ebdf167bcf3990aa3062093ecf6e1a0，未用HEAD替代评估版本。

完整阅读perm.c/h、region.c/h、ipi.c、cpu.c、consts.h及.gitmodules；定向阅读enclave.c的创建、切换、销毁、change/map/unmap/share/transfer及事件路径，sm-sbi.c对应入口、pmp.c的global更新/IPI处理，pmp.h失效宏与enclave.h身份/事件定义。SDK/runtime、密码实现、所有benchmarks及子模块源码没有全面审计。

作者要求FireSim/AWS EC2 F1取得cycle-accurate性能；QEMU只用于功能验证。附录列约20GB磁盘、约1小时准备和约30小时实验。本文未启动Docker、AWS、QEMU、RTL模拟或benchmarks，不能声明复现了性能或安全验收。

## 9. 设计与公开评估源码的关键差异

第一，perm.c/change_dyn_perm先执行pconf->dyn_perm = dyn_perm，再比较lock与pconf->dyn_perm的L位。两者此时来自同一新值，该条件不能识别L变化。因此该helper中更新lock_holder并返回2的路径不会因正常位值触发；其实际调用者elasticlave_change_unlocked在返回1时只更新本核权限，返回2才执行锁事件与global PMP调整。get_perm又依赖lock_holder强制独占。这是已核对调用路径的静态不一致，不能以“有L位”或论文描述认定该快照已完整实施独占协议；没有运行攻击验证影响。

第二，_elasticlave_create使用region_id + 1作为uid，get_region_index寻找空region slot，destroy/remove_region又把slot标为INVALID。故该创建路径会复用槽位uid，与正文“不重复uid”实例语义有差异；eid另有单调递增计数器，不能把二者混为一谈。旧uid是否可造成实际越权还取决于权限重置、事件消费与调用者状态，本文没有执行利用；它已经足以说明复用整数不能单独证明旧事件不会关联新对象。

第三，所读elasticlave_transfer检查当前holder、目标存在和目标L上限，更新两方L位、发送REGION事件后设置lock_holder；该函数未见正文要求的目标maps>0检查，也未见直接global PMP更新。需要结合完整runtime、调用约束及并发路径继续核验，不能把REGION IPI的pending ACK当作硬件权限切换证据。

第四，elasticlave_unmap在持锁后的无效eid分支直接return，没有释放encl_lock。不过SBI入口从可信CPU当前身份取eid，是否能到达此分支取决于有效身份与销毁并发条件；没有构造可达路径，故仅记为错误路径核验项，不宣称任意Host调用可死锁。

这些观察针对固定公开评估快照及已读文件，不是完整安全审计、不是项目已存在的同类缺陷，也不能外推为所有Elasticlave实现都被攻破。artifact评估、功能运行和权限不变量正确性需要不同证据。

## 10. 实验平台、基线和数字

性能使用FireSim FPGA加速的RocketChip cycle-accurate模拟：四RV64GC核、每核16KB指令/数据cache、默认16 PMP项、共享4MB L2。硬件综合用22nm工艺、Synopsys Design Compiler L-2016.03-SP5-2，成功目标800MHz；1GHz用于寻找时序瓶颈，不是成功运行1GHz的证据。

| 作者报告 | 适用口径与限制 |
| --- | --- |
| 数据共享synthetic | 512B–64KB；正文观察称512B约60倍、64KB约600倍于spatial；不含应用计算，不是通用端到端加速 |
| 与Native比较 | 若干工作负载约10%开销，Native为普通Linux进程；不是每个程序/任意并发都固定10% |
| IOZone | record超过约16KB后显现优势，大record写带宽最高约多40%、读约多50%；对照此处因OS是参与者，不需secure public memory加密 |
| SPLASH-2 | 七个工作负载、两个enclave，共享16MB；spatial的load/store陷入runtime并转RPC，且因libsodium未能运行而未加入加解密；作者仍报告2–3数量级差距 |
| 锁同步 | futex相比spinlock CPU time最高约好1.5倍，wall-clock没有可观察优势；不能把CPU节省写成端到端延迟改善 |
| ML inference | 四个Torch图像分类模型、每模型单enclave线程，最少共享，三种设置相近；是CPU实验，不是GPU/LLM推理结果 |
| 上下文切换 | 所测无主动退出工作负载，1个region约0.1%、4个约0.15%周期开销；不是所有change/transfer的总成本 |
| 面积/关键路径 | 相对无PMP每增加8项约多1%总面积，约等于L1 D-cache面积的2.3%；8/16/32项所测配置PMP不是全核关键路径，不保证无限增加仍无影响 |

Lighttpd+Nginx+Python与Memcached是原生应用profiling和预期成本估算，没有完整移植到Elasticlave后测端到端。作者估计其数据共享部分约两数量级改善，原生共享时间占比分别9.2%/23.1%；不能据此宣称整体web/KV吞吐也提高100倍。

原文称常数开销主要是相对数据量不随L线性增长的额外权限操作；它不消除数据本身计算/缓存成本、受影响核心数量、区域数量、TLB失效和异常处理。未取得可离线复算的全部原始数值，本轮不冒充重跑图表或重算全部均值。

## 11. 与PORTAL、CAGE、ACAI及项目的关系

PORTAL强调可信服务Realm，CAGE/ACAI处理设备访问与实际页/身份约束；Elasticlave补充互不信任共享者在不同阶段对同一对象的权限视图。PhantomMap关注真实物理页及生命周期，两者共同提醒：授权建图是必要条件，之后的交接、撤销与对象复用仍须有明确规则。

项目假设继续成立：RMM认证原始Client，可信ProxyRealm统一控制SMMU；映射建立时检查对象、实际页授权、权限及生命周期，软件IPA→HPA后合成为受保护的直接HPA Stage-1，其他设备保持硬件Stage-2。Elasticlave不要求改用CPU PMP，也不以当前实验板能力否定此设计。

项目已有认证队列、GPUVM、私有快照、native fence、cookie/epoch及persistent IRQ127；本报告不把它们重新包装为尚未实现的发明。适合补充的是这些机制组合后的不变量：提交快照/输入在GPU消费期间谁可修改，返回结果何时可读，取消后何时可重新授权，以及reset后旧记录能触发哪些操作。

Elasticlave保护不受其他enclave干扰的处理中间态，但并非让恶意GPU kernel变成可信程序。需要分别说明受信任Proxy/固件如何把Client任务、GPUVM、实际页和真实完成绑定，以及合法Client自身程序可以拥有多大访问范围。

## 12. 可以继续发展的设计点

优先审查“访问权交接与完成记录”的统一状态机，而不是为每个IRQ额外做一次签名：用既有可信身份和cookie/epoch绑定共享对象实例、授权范围、当前阶段、任务及设备epoch；中断只唤醒，可信记录决定当前允许的状态转换。owner、当前CPU写者与设备在途使用者应可区分，不能用一个owner字段承担全部含义。

需要保护正在消费的输入时，可比较既有私有快照与阶段性撤写两条实际路径：快照避免全局权限频繁变更，撤写适合较大不可复制对象，但后者需要覆盖全部CPU alias及DMA入口并确认失效完成。是否新增机制应先核对现有BO/GPUVM语义，不假设所有缓冲区都应强制独占。

缓冲区归还应分别证明结果/错误可发布与旧访问能力已终止。真实fence可支持前一类结论，但撤销、IOTLB、在途事务、reset及清零/重新授权仍需相应证据；超时只能导致失败或隔离，不能直接当作安全回收许可。

后续验证可针对：错误Client/eid不能转授权；超过static maximum被拒；独占期所有alias及非授权DMA不能访问；transfer间隙无抢占授权窗口；同值句柄复用不接受旧通知；合并/重复/迟到事件不重复完成任务；销毁/reset与提交并发不使旧映射复活。本轮只提出验证目标，没有执行这些测试。

论文的主要价值是把共享权限协议变成明确可分析的接口；主要边界是正确策略与无漏洞TEE的假设、未实现shared swapping、性能对照的特殊成本，以及公开评估路径中需要进一步解释的静态不一致。它为项目的内存和中断通信隔离提供分析工具，不能替代GPU执行生命周期本身的安全论证。

统一记录：Elasticlave正式全文、artifact附录及固定评估源码定向研读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜文献/源码获取证据保留，无GPU/VM/模拟器run-id或新增性能PASS｜保留静态差异、未核验依赖和未测异常路径，持续研究。
