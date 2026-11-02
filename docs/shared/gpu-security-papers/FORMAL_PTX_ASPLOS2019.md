# PTX 形式化分析：同步作用域、编译映射与可信完成的顺序证明

研读日期：2026-10-27。原库 TGS-057。已完整研读官方 14 页论文，并固定公开模型/证明仓库，定向检查 Alloy 模型、映射、Coq 最终定理及转换基础设施。没有运行 Alloy、Coq、GPU 或任何攻击。未改运行代码，无新增性能测量。

## 1. 书目信息与证据

| 项目 | 内容 |
| --- | --- |
| 标题 | A Formal Analysis of the NVIDIA PTX Memory Consistency Model |
| 作者 | Daniel Lustig、Sameer Sahasrabuddhe、Olivier Giroux |
| 正式发表 | ASPLOS 2019，257–270，14 页；会议 2019-04-13 至 17，Crossref 发表日期为 2019-04-04 |
| DOI | [10.1145/3297858.3304043](https://doi.org/10.1145/3297858.3304043) |
| 官方入口 | [NVIDIA Research](https://research.nvidia.com/publication/2019-04_formal-analysis-nvidia-ptx-memory-consistency-model) |
| 所读全文 | [官方 PDF](https://d1qx31qr3h6wln.cloudfront.net/publications/ASPLOS_2019_PTXMemoryModel.pdf) |
| PDF SHA256 | `8681a3a6e6bf3dadb82381dc788f2ae0ed623548ea09190c02bfa1abc699c044` |
| 公开 artifact | [NVlabs/ptxmemorymodel](https://github.com/NVlabs/ptxmemorymodel) |
| 固定提交 | `f0dc6b7f85f34fc19fb76e7495864656276fa002`，git ls-remote 与本地浅克隆 HEAD 一致 |

该文正式分析 PTX 6.0，主要背景为 Volta 及后续架构的同步模型。它不是一份覆盖截至 2026 年全部 PTX 扩展的验证，也不是 CCA GPU TEE 方案。

## 2. 问题与核心贡献

此前 GPU 内存语义常从硬件实验反推，或由自然语言手册解释。2015 年 GPU Concurrency 揭示了文档、编译器和程序假设之间的落差。此文以官方 PTX 6.0 说明为起点，把语义形式化，并证明一个带 scope 的 C++ 风格源模型可正确映射到 PTX。

研究分四层：自然语言→Alloy 关系模型；构造 scoped RC11→PTX 映射；Alloy 有界找反例；将同一模型经 alloqc 转为 Coq，人工证明不受小规模枚举上限约束的性质。

核心是编译映射的条件正确性：合法、无数据竞争的源程序按指定规则编译，目标模型允许的执行可回升为源模型允许的执行。它没有直接证明商用 ptxas 或 GPU RTL 全部符合模型。

## 3. Scope 与 moral strength

PTX 的 .cta、.gpu、.sys 指定参与同步的线程范围，分别覆盖同 CTA、同设备、当前程序中跨设备及 Host 的线程。语义强度 .relaxed/.acquire/.release/.acq_rel 与 scope 是两个维度。

两项操作能否用于跨线程同步，要看双方 scope 是否互相包含对方参与者，并满足 strong、同址等规则。只有单边扩大 scope，另一端仍不覆盖参与方，不能自动成立同步。

论文称这种配对关系为 morally strong。这里的 strong 是内存模型术语，不表示身份可信、请求已授权、属于同一 Client 或数据经过认证。跨 Realm 通信的地址可达性和双方安全身份必须由项目另外定义。

## 4. 三种同步方式与因果顺序

| 机制 | 内存模型中的意义 | 不应推导的额外保证 |
| --- | --- | --- |
| release / acquire 配对 | 经实际 reads-from/observation 建立 synchronizes-with | 只出现同值标志，不代表一定读取了当前发布 |
| CTA barrier | 参加同一 barrier 的线程建立同步，范围相当于 CTA | 不是跨 GPU、跨 VM 通用 barrier |
| fence.sc | 对相关 fence 建立与 causality 一致的顺序，禁止部分 acquire/release 无法排除的弱行为 | 不是设备任务成功或 DMA 已完全停止的证明 |

release/acquire pattern 允许同步操作与实际 signal load/store 分离，但需要满足指定顺序、同址和 scope 条件。observation 可以经 RMW 链传播，以支持 release sequence。

base causality 组合 po 和同步关系，保证 producer→relay→consumer 这类多跳通信可以传递顺序。完整 cause 再纳入部分同址 observation 关系；它不是无条件把全部原子访问排成一个全局序列。

## 5. PTX 的六条主要公理

| 公理 | 限制 |
| --- | --- |
| Coherence | 有因果关系的同址写必须遵循相应 coherence order |
| Fence-SC | sc 顺序不能违背 causality |
| Atomicity | morally strong 的重叠写不能插入 RMW 的读写两部分之间 |
| No-Thin-Air | rf 与指令依赖不能自我循环地产生从未有来源的值 |
| SC-per-Location | 受约束的同址通信不能违背程序顺序 |
| Causality | 读写观察不能与已建立的因果顺序矛盾 |

PTX 的 co 对所有写并非一律全序；scope 外、无因果关系的竞争操作可以更弱。论文也明确，原子 RMW 对 morally weak 的操作未必有通常直觉中的原子保证。

PTX 在其规定范围内给 racy 程序语义，与完全依赖 DRF 的语言模型不同；但本文没有解决 mixed-size data race。不能把“PTX 不禁止全部竞争”扩张成“任意混合宽度竞争都已严格定义”。

## 6. 与历史 PTX 规则的区别

2015 论文的硬件模型依赖 .cg，并展示 .ca 的旧缓存问题。PTX 6.0 把 cache operator 定义为性能提示，不改变内存一致性语义；因此不能把早期针对 L1 的修复当作新模型的通用规则。

论文引用的 .volatile 具有类似 ld.relaxed.sys 的同步语义，仍不等于 acquire。向量访问按多个标量分量、次序未定处理；state space 不把 global/shared 的同步分成两个互不衔接的独立关系。

Volta 的 Independent Thread Scheduling 也使传统“同 warp 隐式逐指令同步”假设失效。这是关于相应架构/编程模型的背景，不是对项目 Arm GPU 行为的新实测结论。

## 7. 源模型为何不是完整标准 CUDA 或 OpenCL

论文指出当时 CUDA 缺少正式认可的语言级模型，而 OpenCL 2.2/C++ 的部分模型和典型编译映射有已知问题。作者基于 Repaired C11（RC11）构造 OpenCL 风格、scope-inclusive 的源模型。

它加入 scope，并排除 RC11 的强 No-Thin-Air 公理 acyclic(sb ∪ rf)，因为该约束禁止所有相应 load→store 重排，既有争议又与当前 GPU 行为冲突。PTX 自身仍保留依赖相关的 No-Thin-Air 规则，不能说两层都完全不约束 thin-air。

因此机器证明覆盖论文定义的 scoped RC11 变体，不等于标准 C++、所有 CUDA/OpenCL 程序或源程序存在竞争时都已安全。将“OpenCL-like”简写成“已证明 OpenCL 全栈”会改变结论范围。

## 8. 编译映射及一个关键反例

非原子读写降为 weak，relaxed 原子用相应 scoped relaxed，acquire/release 用 native 指令。SC 读写/RMW 使用前置 fence.sc 加 acquire/release/acq_rel；SC fence 则直接映射。

最值得迁移的是 §4.2/Figure 12 的案例：SC RMW 已有前置 fence.sc，看起来可以去掉 RMW 的 release 部分，但一个多跳 release-sequence 场景会产生同步缺口。作者是在 Coq 证明过程中发现它，受限事件数的 Alloy 搜索没有找出。

原因是前置 fence 和 RMW 的写部分在不同同步链上起作用，前者不能替代后者的发布关系。这个案例不证明所有同步冗余消除都不安全，而是说明优化必须保留完整协议中每条需要的传递边。

## 9. Alloy 与 Coq：分别证明了什么

Alloy 把关系模型转为 SAT，通过有界实例检查找反例。它能快速检验小例子，但“无反例”只适用于所设 bound；scope 增加后求解成本显著增长。

alloqc 生成 Coq 定义和待证明命题。Coq 用户补上证明，归纳式 transitive closure 不依赖 Alloy 的有限枚举深度。论文的结果主要对应源层 coherence、atomicity、SC 三个性质。

自然语言到模型的忠实性、alloqc 转换正确性、模型假设和 Coq 依赖仍属于证据边界。定理检查不自动验证这些外部来源，也不验证 CPU/GPU 实现。项目若借鉴这种路线，应将协议模型、实现映射和测试结果分别登记。

## 10. 作者测量：验证成本而非 GPU 性能

| 有界分析配置 | Coherence | Atomicity | SC |
| --- | --- | --- | --- |
| scoped，4 events | 41 秒 | 4 秒 | 10 秒 |
| scoped，5 events | 6.4 小时 | 5 秒 | 15 分钟 |
| 去 scope，5 events | 1.8 分钟 | 4 秒 | 21 秒 |
| 去 scope，6 events | 3.1 小时 | 4 秒 | 26 秒 |

这些为作者 Intel Xeon 服务器上的 CPU 求解时间，48 小时超时门槛用于选择可分析 bound。它们不是 GPU kernel 性能，也不是本项目中断或 glmark 开销。

作者报告 Coq 证明约 3100 行、检查约 15 秒。此次固定源码 src11_ptx.v 实际为 3580 个物理行，不同版本/空白口径不能当成作者数字造假或新的运行时间测量。本轮未执行证明检查，15 秒仅为论文结果。

## 11. 固定公开代码核验

固定提交的完整 git 文件树有模型、编译器、Makefile、预生成 Coq 和证明文件；没有以当前 PTX 在线手册替代对应历史模型。已读 README/Makefile、ptx.als、src11.als、compile_src11_ptx.als 及 alloqc.sh；定向查看 Alloqc.java 的转换、alloy.v 的关系/闭包定义和 src11_ptx.v 的三项最终定理及部分支撑引理。

README 要求 Coq 8.4pl6、javac；Makefile 的 all 构建证明，src11_4/src11_5 只分别检查 coherence/atomicity/SC。src11.als 虽仍定义更强 no_thin_air，映射文件也保留相应 assertion，但最终三项定理不能因此被写成已证明全部原始 RC11 公理。

src11_ptx.v 定向检索未发现 Admitted/admit；这不等于做过依赖闭包的完整证明审计。生成文件有用于编码 Alloy facts、类型和模型的 Axiom，不能把公理化输入误称为证明漏洞，也不能宣称完全不依赖假设。

alloy.v 中 cardinality 标注 FIXME/currently incomplete，并给出抽象公理；Alloqc.java 会把部分不支持的 construct 注释输出，含 integers/不支持 builtin 的处理。该工具是论文支持软件，不是已经验证、覆盖任意 Alloy 语言的通用编译器；本次没有独立判定这些分支影响了哪条最终定理。

## 12. 复现证据与明确未执行项

公开仓库固定源码和每文件 SHA256 已保存在本地证据目录，预生成 Coq 文件也已取得。没有运行 make、安装旧 Coq、调用 Alloy jar，或对新系统作性能测量；因此本次不给“证明重检 PASS”“artifact 完整复现”或“代码与英文规范已完全等价”的结论。

全文解释、定向源码核验和作者所述机械证明是三个不同层次。本文对源码范围的说明比单纯列一个 GitHub 链接更具体，但没有冒充全仓库语义审计。

## 13. 与当前项目的关系

项目可信 ProxyRealm、RMM 身份认证、实际 HPA 授权和 Stage-1 限制继续成立；PTX 的 scope/内存顺序不能替代这些安全边界。跨 Client 身份相同与否，不由 morally strong 判定。

已有认证队列、GPUVM、私有快照、真实 fence、cookie/epoch 与 persistent IRQ127 可作为协议状态。值得写清的顺序是：GPU 写入→驱动规定的完成/可见性同步→Proxy 发布可信 completion→Client 获取并验证→读取结果。多跳链中的每一段都需要对应实际平台机制，不能仅引用 PTX theorem 或任意 CPU barrier。

真实中断、正确 Client 路由、正确任务终态、结果可见、DMA quiescence 和页可复用分别是不同性质。该论文帮助论证其中的顺序组合，不独立证明跨 Realm 事件真实性或安全回收。

## 14. 建议与独立评价

可先为已有完成/ACK_ARM/reset 协议建立小型事件图，记录每个事件的 actor、对象、seq、epoch 和 happens-before 要求；对拟议优化，明确删除或合并了哪条顺序边。用有界反例搜索检查旧状态、重复终态和槽位重用，再对关键不变量做独立证明，是与本文方法最直接的衔接。

若做形式化实现，模型必须包含设备/CPU 的真实可见性、错误终态、重启、epoch 和撤销条件。只证明内存序或只枚举三四个任务，不能自动推广到所有资源生命周期。这里是未来验证建议，不表示已建立本项目模型。

独立评价：论文的强点是把规范、可执行关系模型和不受小 bound 限制的证明串起来，并展示小规模测试漏掉的映射错误。局限在于证明对象和前提都很具体；它是可信协议组合方法的重要材料，不能包装成已经证明项目 GPU TEE 的论文。

统一记录：全文及固定模型/证明代码静态研读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜未执行 Coq/Alloy/GPU，无新增 run-id 或硬件 PASS｜作者证明、源码核验与项目推断分开。
