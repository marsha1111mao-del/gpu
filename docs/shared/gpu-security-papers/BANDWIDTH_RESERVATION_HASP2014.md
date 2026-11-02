# HASP 2014 带宽预留：跨 VM 时序隔离提案、性能证据与未验证的泄露边界

## 1. 文献身份和证据范围

论文：Memory Bandwidth Reservation in the Cloud to Avoid Information Leakage in the Memory Controller；Akhila Gundu、Gita Sreekumar、Ali Shafiee、Seth Pugsley、Hardik Jain、Rajeev Balasubramonian、Mohit Tiwari；HASP 2014，2014-06-15，1–5页，DOI：10.1145/2611765.2611776。

[正式DOI](https://doi.org/10.1145/2611765.2611776)；[Utah作者全文](https://www.cs.utah.edu/~rajeev/pubs/hasp14.pdf)；[Texas作者全文](https://spark.ece.utexas.edu/pubs/HASP-14-memoryctrl.pdf)；[作者出版列表](https://www.cs.utah.edu/~rajeev/pubs.html)。Crossref的题名、七作者、会议、日期与页数相符；两份作者PDF逐字节相同，267872 bytes，SHA256：9786b27dd698b69d1c4fa215ce38cf96f25862706e61bf74690b6c672fde05a7。ACM直接PDF返回403，未与出版方文件作字节比较。

已读全部5页、§1–8及30条参考文献，并视觉复核全部5页，覆盖Figure 1–3与Table 1。来源记录为`acquisition118.json`；图表清单为`reservation-render118.json`，全文为`reservation118-full.txt`，独立复算为`reservation-arithmetic118.json`，均位于`build/cca-gpu-followup-20261027`。

限定GitHub题名关键词检索返回两个MemGuard仓库，描述为性能隔离工具，未建立与本文具体模拟实现的对应关系，不能当作本篇artifact。未取得作者修改后的Simics/USIMM代码、trace和原始数值；未运行通用模拟器或其他项目替代复现。

这是共享CPU内存控制器的早期性能/安全提案，不是Arm CCA GPU、GPU中断协议或完整TEE实现。纳入本项目的理由是它直接讨论跨VM资源竞争，以及QoS带宽保证与保密隔离的区别；其硬件模型用于验证提案，不据现有测试板能力否定研究假设。

## 2. 论文实际解决和尚未解决的问题

攻击者通过自己访存延迟，推测共租户的内存活动强度。竞争来自bank、address/command bus和data bus；缓存隔离只能约束缓存状态，不能阻止另一个租户的cache miss改变共享DRAM队列等待时间。

论文重点是降低Temporal Partitioning（TP）的性能代价，以交错请求的Bandwidth Reservation（BR）替代长时间独占轮次。核心经验是：完全禁止并发会增加请求等待；受控共享可能改善性能，但必须另行说明共享后剩余观察面。

最重要的限制在§5开头和结论：本文主要评价性能，信息泄露分析留作未来工作；“近零泄露”是定性论证。不能用摘要的平均低于1%开销证明已经实测强时序隔离，也不能把题名中的avoid当作形式化保证。

## 3. 信任边界及资源身份

论文以thread/security domain/VM作为共享主体，默认内存控制器能按主体调度、记账与限流。它没有实现RMM认证、Realm身份传递、实际物理页授权或恶意Host下设备控制面的完整保护；这些需由项目现有可信平台提供。

若迁移至项目，可信ProxyRealm使用RMM认证的原始Client标识，不能让Host或Client随意更换计费主体、创建别名绕过配额。控制器配置、N与配额、归属状态及重置规则要受保护，否则固定分配只是一项可被攻击者重编程的性能策略。

作者把页映射到某bank的偏好视为偶然信息，认为价值有限。项目若假设Host恶意，需进一步检查Host能否影响页布局、并发或采样，从而放大这种相关性；不能将论文对观察价值的主观判断当成项目威胁模型下已经排除的攻击。

本篇聚焦read request rate。write queue批量drain、共享LLC/MESI、刷新、地址和bank状态没有被统一证明非干扰，也没有验证密钥提取或应用级攻击成功率；这些边界需要在引用时一并说明。

## 4. Temporal Partitioning 的保护与成本

TP在固定turn内只允许一个域发请求，末尾设置dead time防止操作延伸到下一个域的时隙；严格close-page/autoprecharge防止row-buffer命中状态泄露前一域活动。独占调度不等于自动消除跨轮次残留，必须覆盖仍在途的操作和持久状态。

背景转述先前工作的建议turn96ns、dead约65ns、bank partition后dead约12ns。本文自己的实验选择256个CPU cycle即80ns，dead172cycle即53.75ns；优化TP通过bank partition将dead降到32cycle即10ns。不能混用背景与本次配置计算收益。

独立复算本文未优化turn的dead占67.1875%，可发起操作区间占32.8125%；优化dead占12.5%。这只是调度区间比例，不等于DRAM总利用率或GPU性能损失，因为已发命令、排队和CPU执行可能重叠。

作者用到达其他线程turn的概率(N−1)/N和条件等待(N−1)T/2说明队列等待增长。N=8、T=256时，按其公式为条件896cycle、加权784cycle；这是到达分布简化下的解释，不是全部DRAM请求的严格上界，更不能据此推导GPU中断处理延迟。

## 5. Bandwidth Reservation 机制

BR在Q周期内给每个线程固定1/N的数据总线份额，请求在域之间交错；需求过多则延迟到下一窗口，需求不足则以dummy补足。分配意图是使外界看到固定需求强度，而不必等到自己的长turn才服务。

这里的“预留”不能只保证最低带宽。允许随受害者空闲而偷用额外带宽，攻击者就可能从自己吞吐变化推测受害者活动；论文在related work明确区分普通QoS的按需改变分配、偷用空闲配额，与保密调度目标。

dummy也不是简单地把配额标为已消费：若总线空闲保留旧row-buffer状态，后续攻击者仍可能观察到命中差异。作者指出至少应precharge，即使不激活或传输数据；完整fake事务与只precharge的外部可见性、能量和时序不相同，不能默认它们在任何观察面下等价。

作者承认交错访问可能泄露最近bank访问、row-buffer命中及bank冲突。可选补救包括close-page、固定命中率或每bank再固定分额，但这些性能与泄露的联合评估留待未来；不能把最强组合的安全目标与最弱配置的低开销拼成一个已验证结果。

## 6. 滑动窗口与有限配额的局限

固定不重叠窗口可能让真实请求集中在开头、dummy集中在结尾，窗口总量一样但细节可见。作者提出长度Q、步长S小于Q的滑动窗口，并允许各线程窗口不同步、S从指定范围随机选择，以降低边界对齐和dummy识别机会。

随机窗口或随机延迟不是自动安全：需要定义随机性是否独立于秘密、攻击者能否观察边界、能否重复采样，以及真实/fake是否可区分。论文没有为该随机化提供信息论上界或攻击复测数据。

自构算例A=[1,1,0,0,1,1,0,0]、B=[0,0,1,1,0,0,1,1]，每个连续4格窗口的总数都等于2，包括S=2重叠窗口，但细粒度时序仍可区分。这说明窗口总量约束本身不足以推出完整轨迹相同；它不是对作者未公开实现的攻击复现。

更强安全需要明确哪些观察可用，例如每次请求延迟、完成顺序、row hit、空闲bus、周期计数及域切换。若只保护某一窗口分辨率，应直接写明；不能从大窗口平均相同推导更细观察者看不到秘密。

## 7. 实验方法与复现范围

Simics联接修改的USIMM模拟DDR4；八个3.2GHz乱序UltraSPARC III核心，共享单内存channel、四rank、每rank16bank。ROB64项，最多每周期取/发射/执行/退休4条；私有32KB L1 I/D、共享4MB L2、MESI。它不是八个CCA Realm或八租户GPU的实测。

默认调度优先row hit，没有待命中请求时关row，并用write queue高40/低20水位连续drain写操作。Table 1给出DDR4 timing、refresh等参数；这些设置会影响读延迟，不能只根据数据总线带宽推导全部隔离性质。

九个SPEC2006程序各运行八份rate模式：libquantum、milc、mcf、omnetpp、h264ref、GemsFDTD、leslie3d、gromacs、soplex；另有两个八程序混合。先fast-forward500亿指令，前500万模拟指令作warm-up，遇到100万次memory reads后结束。内存读数限定的模拟窗口不能自动代表完整应用总时长或所有阶段。

所有域等份分配；不均匀配置仅被认为可让TP/BR均受益，未提供完整结果。没有公开仿真commit、随机seed、每项原始IPC、误差条和安全实验，有限图表不足以声称完成独立复现。

## 8. 性能消融与指标解释

Figure 2对照优化FR-FCFS，分别观察Autoprecharge、Dead、Isolate、TP及Optimized-TP。Dead单独加入172/256死区但不隔离线程；Isolate单独按256cycle轮转但不加死区；TP组合三项；Optimized-TP再做bank partition并缩短死区。消融含义不同，不能把它们都当同等安全的部署方案。

正文报告Autoprecharge平均损失2.7%、Dead22%、Isolate64%、TP74%、Optimized-TP61%。图轴为normalized IPC，所谓slowdown需要按这一指标理解，不能直接写成应用运行时间增加相同比例。

例如某个固定指令量case若IPC从1降到0.39，IPC损失61%，时间倍率为1/0.39约2.564，即增加156.41%；若降到0.26则时间倍率约3.846。对平均IPC做倒数又不等于各case时间倍率的平均，因此这里只解释指标，不用该换算制造作者未给出的平均时延。

作者说各项影响roughly additive，但2.7+22+64=88.7%，不等于组合74%。按连续乘因子得到损失72.678%，数值接近74%却不能证明实际采用该算法；原始消融和依赖交互不足，不宣称各因素收益可直接相加。

Figure 3比较BR的Q=128/1024/8192cycle，按3.2GHz换算为40ns/320ns/2.56微秒；Q128平均IPC损失约8%，Q8192平均低于1%。这些是该仿真资源和负载上的结果，不是安全窗口长度通用选择，也不是本项目glmark分数预期。

最关键的可比性限制：§5明确实验取S=Q，即不重叠窗口；需求不足时控制器直接idle。它没有评估前文建议的S小于Q、随机步长、至少precharge dummy及完整row/bank防护。因此“低于1%”只支持此初步BR配置的性能，不能支持最强时序防护的低于1%成本。

## 9. 对项目直通、共享与任务隔离的启示

项目可借鉴受控交错共享降低独占等待，但内存访问授权继续由RMM认证Client、ProxyRealm验证实际HPA归属/权限/生命周期和受保护Stage-1承担。配额是调度状态，不能取代页授权，也不能使dummy访问越过原始Client边界。

共享GPU公平性和时序保密的目标不同。round-robin、在途任务限制或有界提前观察真实fence可以改善吞吐/响应，但若调度会因其他Client空闲而加速，旁观者可能获得活动信息。是否允许泄露需在威胁模型中决定，不能由“调度公平”自动推导隐藏。

中断部分应首先保证真实完成、正确归属、旧cookie/epoch失效和可靠通知，再考虑固定节奏或批处理。即便每窗口给每Client相同中断数量，窗口内顺序、完成页更新和首次/最后一次通知仍可能泄露；固定计数不认证通知，也不证明全部时间信息隐藏。

已有原生fence是任务真实终态依据，通知只唤醒检查。若延后对外发布以整形时序，必须区分内部完成与允许发布时刻，保留错误、取消、依赖链及CPU可见性语义；延迟通知不能用来掩盖缺少DMA静默或提前复用资源。

Client加入/退出、权重调整、reset会改变N和份额。建议将合法调度配置变更绑定可信generation，并定义重新分配的公开边界；变更前旧任务/通知/映射的有效性与资源回收条件仍需独立核对，不能只重置统计计数器。

本篇可以支持第二部分中的“共享资源引入观察通道”的问题定义，尚不足以作为现有项目已达到时序非干扰的依据。第一部分仍可追求性能；若比较时序保护方案，必须同等列出启用哪些保护，而不把隔离目标较弱的配置当成安全等价快路径。

## 10. 后续研究与统一记录

后续优先核对本文的HPCA2014基线Timing Channel Protection for a Shared Memory Controller，以及同作者后续HASP2018的An MLP-Aware Leakage-Free Memory Controller；再与MITTS/Camouflage对照。这里仅建立引用链，未精读的资料不计完成。

统一记录：完整5页/全部图表视觉核对/正式身份与双作者PDF核验/独立算术/Notion同步回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者模拟器/应用/攻击/构建/硬件run-id｜保留研究，整体调研继续。
