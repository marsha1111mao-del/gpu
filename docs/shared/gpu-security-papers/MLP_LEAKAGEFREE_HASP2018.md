# MLP-Aware Memory Controller：固定服务、延迟发布与跨 VM 时序隔离精读

## 1. 身份、版本与阅读范围

论文：An MLP-Aware Leakage-Free Memory Controller；Andrew Vuong、Ali Shafiee、Meysam Taassori、Rajeev Balasubramonian；HASP 2018，2018-06-02；DOI：10.1145/3214292.3214296。

[正式DOI](https://doi.org/10.1145/3214292.3214296)；[作者全文](https://www.cs.utah.edu/~rajeev/pubs/hasp18.pdf)；[作者出版列表](https://www.cs.utah.edu/~rajeev/pubs.html)。取得的作者PDF为544055 bytes，SHA256：c569aff555a0df90406d826734e8e6462ec91192b43140389e9fcdb2e2996c99。Crossref题名、四作者和日期匹配，但元数据page为1–7，作者PDF实际8页，ACM引用格式也写8 pages；保留长度差异。ACM直接PDF403，未逐字节比较正式版。

已完整阅读作者版8页、§1–6、致谢及19条参考文献；全部8页视觉核对，覆盖Figure 1–10和Table 1–2。证据目录：`build/cca-gpu-followup-20261027`；全文为`mlp119-full.txt`，视觉清单为`mlp-render119.json`，来源为`acquisition119.json`，独立复算为`mlp-arithmetic119.json`。

限定GitHub检索MLP-Aware返回两个MLP cache replacement学生项目，与本文内存控制器实现不符，未拿它们替代artifact。未取得作者修改的Simics/USIMM、实验trace或完整实现；所有分析为静态阅读与自构算术，没有作者代码、模拟、工作负载、攻击、构建或硬件执行。

这是一篇CPU共享内存控制器调度论文，MLP指memory-level parallelism，不是神经网络multilayer perceptron。它为项目的多Client资源共享与通知时序提供机制对照，不计作新的Arm CCA GPU架构。

## 2. 问题定义与先前工作的关系

威胁是同socket互不信任的VM通过周期访存及平均延迟，推断其他VM的访存强度，或两个合作的恶意VM用高/低访存传输秘密。攻击不要求攻陷OS或物理接触；本文不是以恶意Host重编程控制器为主要场景。

作者明确缓存、分支预测器、总线地址等侧信道需要分别防护；这里的leakage-free限定为其内存控制器时序模型，不等于整台机器、GPU、应用或所有物理观察面都不泄露。

研究链为HPCA2014的Temporal Partitioning（TP）、MICRO2015的Fixed Service/Bank Triple Alternation（BTA）、HPCA2017的SecMC-NI，再到本篇Rank Triple Alternation（RTA）和rank subsetting/RPA。HASP2014的带宽预留属于相邻探索，不能将其未评估的近零泄露声明当本篇证明前提。

论文认为SecMC-NI长turn预留的六个issue slot常用不满，典型CPU负载MLP低，缩短turn可以减少等待。这个动机不同于简单提高总带宽：安全时隙需要与真实并行度匹配，空出的理论能力未必能被应用利用。

## 3. 固定服务和返回时刻的安全作用

§2.2在特定DRAM配置下使用跨rank7、同rank异bank15、同bank43个memory cycle的安全间隔，覆盖其先前分析的读写组合。这是所选时序参数下的规则，不是跨硬件通用常数；转换到GPU应重新定义共享状态和冲突，不机械复制这些cycle。

TP使用43cycle dead time保证前一VM的访问不跨入下一VM的turn。BTA按bank-id modulo3轮转，仅允许当前bank类别，减少连续turn访问同bank的机会，使dead time降到15cycle。这里的“清洁边界”来自受控资源冲突条件，而非仅仅换了VM身份。

SecMC-NI（本文称3R/2B）给每VM43cycle turn，最多访问三个rank、每rank两个不同bank，共六slot；通过重新安排rank/bank顺序满足前后turn的冲突间隔。某个rank被前VM访问后，当前VM访问它的slot可能被推迟。

即使本turn可以安排全部允许的请求，slot早晚仍会透露前VM活动。§2.4因此指出需要等到固定边界集中返回请求结果，使VM不能看到内部重排。本篇明确解释该原则；它没有给出涵盖所有异常、响应队列和实现信号的机器检查证明。

对项目的类比是“真实GPU终态”与“向Client/Host暴露该状态的时刻”可以不同。延迟发布若用于时序保护，必须先由native fence确认真实完成，保留错误/取消、数据可见性和依赖顺序；固定时间到达不能反过来当任务真实完成或DMA静默的证据。

## 4. MLP观察与RTA机制

Figure 3显示最常见场景约45%的turn仅发一个请求、队列无剩余，近90%的turn待处理请求少于两个；作者称82%的六slot未使用。按该比例仅复算平均填充约1.08 slot/turn，不能把空slot数直接等同物理bus空闲率，因为真实请求仍跨周期执行。

Table 2列SPEC2006 MPKI从dealII0.236到mcf30.505。MPKI和outstanding数量相关但不是同一指标，不能从某个miss率直接推出GPU的并行内存需求。作者用CPU窗口小于200项解释低MLP，未验证大量GPU wavefront下也同样成立。

RTA使用14cycle turn，每turn最多两个请求，rank-id modulo3等于turn-id modulo3；每三个turn加入一cycle bubble。论文认为这能把同rank类别再次出现的起始间隔拉到43cycle，并减少单VM等待。

RTA还允许两个同rank异bank请求，只要二者同为read或同为write。这个例外利用更具体的时序条件，不能用它否定前述针对任意读写组合的保守间隔，也不能把它扩展成任意bank/读写均可连续发起。

所有调度器使用XOR地址映射以分散rank。映射是物理地址到DRAM资源的布置方式，不是本项目IPA→HPA授权翻译；XOR不认证页归属，也不能取代RMM身份和SMMU权限检查。

## 5. 需要补全的调度不变量

RTA每三个14cycle turn加一bubble得到43，但这只是同类别turn起点间隔。自构例子：前turn第二slot在t=7访问某bank，下一次同类别turn第一slot在t=43访问同bank，间隔只有36，低于论文同bank43规则。仅给出turn/rank类别条件不足以排除这种安排。

这不是已复现漏洞：真实实现可能另有bank/slot重排、准入和保留状态，正如SecMC-NI需要调度约束。本报告的结论是短篇公开规则尚不足以独立证明所有允许请求组合安全；应取得完整调度算法和实现后核对，而不声称已攻破系统。

对项目的对应要求是把安全约束落实到每个在途任务、真实页、slot及跨epoch事件，不能只验证一个宏观调度周期。安全间隔应从最后一次可能冲突的实际访问算起，不能一律从上一轮开始时间计算。

轮转的活性还有整除条件。N个VM round-robin时，同一VM每次turn编号增加N；按modulo m分类，它能覆盖m/gcd(N,m)种类别。RTA的m=3要求N不是3的倍数，论文明确可加入dummy VM或用quad alternation补救。

对RPA的m=5和RA的m=7，同样算术提示N为5或7的倍数时会有类别覆盖问题；这是对给定轮转规则的推导，不是论文已评估的全部N场景。本文主要使用N=8。动态加入/退出VM不能只变N而不重新核对公平性与活性。

论文多次称不增加OS支持，但同时在RTA整除例外中要求OS插dummy VM或换调度方案；应理解为不需OS进行bank/rank物理页分区，不宜扩大成任意VM数量下完全没有可信配置配合。

## 6. Rank subsetting与RPA

2-way rank subsetting把rank拆成更多、更窄的独立资源，增加并行度，但burst由4变8cycle，安全间隔也增长：跨rank10、异bank25、同bank47cycle；对应3R/2B turn变60。论文此处括号把先前异bank间隔写21，而§2.2写15；21也曾用于3R/2B示例slot间隔，原文没有充分解释口径差异，保留而不静默修正。

RPA按rank-id modulo5轮转，turn10cycle、一个请求，五turn后再次触及同类别，起点间隔50大于同bank47。与RTA的两slot情况相比，这个单slot算术更直接，但仍需其他时序、刷新、空队列和返回规则配合，不能单靠50大于47证明完整实现非干扰。

4-way subsetting下正文给同rank18、同bank55cycle，采用18cycle RTA turn。三个turn仅54cycle，若沿用一bubble才达55；该变体的bubble及完整slot规则未在评估段详述，不把缺少细节自动当实现错误，也不自行补完后宣称已验证。

rank subsetting需要custom DIMM并偏离标准DDR组织，作者用于研究并行度与安全代价的关系。按项目约定，这不是否定方案的理由；实际可迁移的贡献是资源拓扑改变后要重新推导安全条件，并在相同资源/保护口径下比较性能。

## 7. 实验方法与证据覆盖

Simics联接USIMM做cycle-accurate模拟；八核3.2GHz UltraSPARC III、ROB128、每周期最多4条取/发/执行/退休，私有32KB L1 I/D、共享4MB L2；单channel、8rank/channel、8bank/rank。正文称DDR3，Table 1引用[7]却是JEDEC DDR4标准，保留标注差异，不借此断言真实模拟器必错。

SPEC2006 rate模式每程序八份，fast-forward500亿指令，100万次memory reads后停止；Mix1为libquantum/bwaves各四份，Mix2为mcf/astar/bwaves/sjeng各两份，Mix3为xalancbmk/tonto/sjeng/hmmer各两份。该窗口不等于整应用或真实VM端到端运行。

评估图主要是performance、queueing delay和slot利用率；本篇没有提供完整攻击分类器、信道容量、互信息、错误率/置信区间或全实现形式化验证。其安全依据是构造式调度和引用前作的时序分析，不能把题名leakage-free改写成已穷尽实测所有侧信道。

威胁模型假设无需攻陷OS即可攻击，但不是恶意Host下完整控制面设计。迁移到项目仍依赖保护真实页表、root、MMIO、固件及可信调度状态，并认证RMM原始Client；否则攻击者修改规则就越过了论文讨论的调度前提。

## 8. 性能结果与独立复算

Figure 5报告RA较3R/2B改善约5%、RTA约11%；允许同rank同类型双请求贡献约1%平均收益。RTA在hmmer上不如3R/2B，作者解释其bank冲突较多，说明短turn加约束并非对所有负载单调有利。

Figure 6显示多数case排队延迟减少，但公开图没有完整精确数表，不能从柱高制造逐case纳秒结论；图中的cycle还需确认与memory/core时钟的对应关系，不能把Table 1 CPU3.2GHz直接套在所有DRAM turn上。

Figure 10直接标SecMC-NI0.481、RTA0.536、RPA-Subset2 0.552、BankFS0.573、RankFS0.793，均相对非安全基线。RTA与RPA仍只达到该非安全基线约53.6%/55.2%，不是只有11%/14%的安全开销。

按图中舍入数独立复算，RTA较0.481增加11.43%，RPA较0.481增加14.76%，RPA较RTA增加2.99%；归一化绝对差分别0.055/0.071，即5.5/7.1个百分点。正文11%/14%可能来自其他聚合或舍入，原始样本不足以精确重建，不擅自改为作者已报告14.76%。

“先11%再3%”不能直接相加为精确14%；不同分母下连续因子约1.11×1.03=1.1433。对平均归一化throughput取倒数也不等于平均运行时间，本报告不以0.552的倒数制造应用平均时延或GPU glmark预期。

2-way subsetting对长turn的3R/2B反而更差，对适配的RPA才比RTA增加约3%；4-way因传输时间和turn更长，反而不如无subsetting RTA。它支持联合调整资源拓扑和策略，不能只以rank更多就推导收益。

可作容量量级检查：3R/2B的6/43与RTA计bubble后的6/43最大slot密度相同，约0.1395请求/memory-cycle；RTA收益主要来自减少低MLP下等待和未使用slot，不是理论请求密度必然提高。RPA单slot10cycle密度0.1，但资源并行和冲突条件也改变，不能单用该值判断应用吞吐。

## 9. 对项目的设计建议

优先复用现有private plan、GPUVM/BO、native fence、cookie/epoch和可信IRQ链，补全资源访问与完成发布的联合不变量。论文并不提供GPU任务认证协议，不应为了时序研究另建一套不相容的身份体系。

将内部真实终态、输出可见性、对外完成记录和通知时刻分别定义。需要隐藏时序时可以研究有界延迟/固定批次发布，但绝不能只等待一个固定turn就宣称GPU成功；未完成任务应保留pending或真实失败语义，不能提前发布输出。

slot复用与Client退出/reset必须失效旧epoch、保护回调引用并确认在途访问静默。RTA宏观起点间隔不足以代表最后访问间隔的例子提示：回收依据应是实际在途对象的终态，不是“这个Client已离开调度表”。

不同Client的队列和共享完成页不能让对方通过读写索引、条件唤醒或错误路径绕过通知整形点。若Host能观察VM exit、完成页轮询或RPC边界，应把这些明确列入允许泄露项或同时约束；固定中断节奏不能隐藏所有旁路。

性能部分可借鉴按真实在途并行度选择有界工作量，而非一律扩大batch。GPU与CPU MLP分布不同，需要在保留图形正确性、错误fence和资源恢复条件下实测；论文的14%不是项目可预期提分，也不能替代当前glmark/ML基线。

多Client调度规则需要覆盖不同N、空闲域、加入/退出和权重变更，并保证安全与活性。dummy域只是占调度资源，不自动拥有任何Client页或权限；所有dummy访问仍必须经实际物理页授权和生命周期检查。

## 10. 后续引用链与记录

下一步可精读MICRO2015的Avoiding Information Leakage in the Memory Controller with Fixed Service Policies，以及HPCA2017的Secure Dynamic Memory Scheduling Against Timing Channel Attacks，补足BTA、SecMC-NI和响应延迟的完整条件。本文只完成当前作者版，不把未读前作或通用USIMM当已审计实现。

统一记录：完整8页/全部图表视觉核对/正式身份与版本差异/独立算术/Notion同步回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者代码/模拟器/攻击/模型/构建/硬件run-id｜保留研究，整体调研继续。
