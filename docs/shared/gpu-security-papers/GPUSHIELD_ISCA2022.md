# GPUShield：对象边界检查、可信元数据与GPU共享隔离的区别

研读日期：2026-10-28。完整阅读作者15页全文、§1–9及79条参考文献；核对19图6表，视觉阅读12页。另核对正式书目、第三方Vortex实现的六个固定版本blob并有限静态阅读，定向阅读Khronos工作项函数规范。未执行作者/第三方代码、模拟器、编译或攻击；未改运行代码，无新增性能测量。

## 1. 文献信息与来源

Jaewon Lee、Yonghae Kim、Jiashen Cao、Euna Kim、Jaekyu Lee、Hyesoon Kim，Securing GPU via Region-based Bounds Checking，ISCA 2022，27–41页，DOI [10.1145/3470496.3527420](https://doi.org/10.1145/3470496.3527420)。前四人与Hyesoon Kim来自Georgia Tech，Jaekyu Lee来自Arm Research。GPUShield是方案名，不是另一个独立论文标题。

[作者实验室出版页](https://sites.gatech.edu/hparch/publication/)链接的[作者PDF](https://hparch.gatech.edu/papers/jaewon_2022_isca.pdf)为1170336字节，SHA256为`977864ae84edd0abe7993d86e592437ee7889993cd06fc7a80a558eafc4b6e4f`。Crossref确认六作者、题名、DOI和页码；元数据发布日期2022-06-11，PDF标会议时间2022-06-18至22，两者不混为同一日期。ACM PDF本轮403，未逐字比对出版方副本。

完整文本、15页渲染、获取失败、第三方树/blob及自写算术脚本保存在build/cca-gpu-followup-20261027/的gpushield、vortex和125批文件。作者源码与原始模拟结果尚未取得；本报告不宣称复现。

## 2. 研究问题与项目关联

GPU共享内存和CPU/GPU统一地址空间使buffer overflow不再只是GPU局部结果错误。canary通常只检查边界字节被写，可能漏读越界和跳过canary的定点越界；逐指令软件检测又容易增加寄存器、访存和指令成本。论文希望用硬件协助的对象边界检查减少这类开销。

它研究对象空间安全，不是CCA、完整GPU TEE或恶意Host下的设备分配协议。页表检查最终地址是否合法，对象检查原指针是否越过所属buffer，两者互补：越界到同一已授权页里的另一个对象，可能完全不触发MMU；反过来，一个对象内地址也不能越过Client的实际HPA授权边界。

对项目的价值在于明确“内存还有什么可做”：若目标只是Client间页隔离，不必追加完整对象级机制；若要保护同Client内不可信kernel或细粒度BO子对象，应明确新增目标、TCB、实现与成本，不能沿用GPUVM隔离结论直接声称覆盖。

## 3. 威胁模型与不覆盖范围

攻击者通过恶意输入触发受害kernel的overflow，可能作用于共享GPU上的多个job。受害二进制属于受害者，禁止攻击者伪造原生binary；GPU driver和硬件可信，硬件竞争/功耗侧信道不在范围内。论文以模块签名辅助说明driver可信，但签名本身不证明driver无漏洞，更不能防恶意OS改运行期状态。

这与项目允许恶意Host及Client提交自己的程序不同。不能让Client自报“已静态验证、可跳过检查”，也不能将任意合法加载的恶意shader视作论文已覆盖对象。可信编译、binary/BAT绑定、提交授权和真实页归属仍需单独建立。

## 4. 先验观察及其证据边界

Fig1统计145个benchmark、13个suite，平均6.5个buffer、最多34个，55.9%少于5个。这是小RCache的经验动机，不是所有未来LLM、bindless、间接指针、device globals或动态分配程序的硬上限；也不能把该统计样本与性能评估的88 CUDA+17 OpenCL直接当同一集合。

Fig4在CUDA Managed Memory下展示64B对象和512B对齐，分别访问偏移64B、512B及2MiB：作者观察第一种无可见副作用、第二种overflow、第三种kernel abort，并推测2MiB粒度保护。没有可见副作用不独立证明访问被硬件阻断，2MiB规则也不能泛化为所有GPU/驱动页大小或隔离保证。本文不是一次CCA防护突破实验。

## 5. 总体设计：BAT、RBT和BCU

编译器通过LLVM分析访问对象和索引，把可静态确认的结果写入Bounds-Analysis Table（BAT）并附于binary。可信driver在kernel launch时为对象分配随机唯一ID、准备Region Bounds Table（RBT）、修改指针metadata；GPU在Load/Store Unit旁加入Bounds-Checking Unit（BCU）。

RBT按kernel维护，16384项，由14bit ID直接索引。每条含48bit虚拟base、32bit size，以及嵌入base高位的valid/readonly。BCU保留RBT物理位置，专用访问绕过普通地址翻译；正常GPU请求不能映射这些元数据页。将RBT放在global memory并不意味着任意kernel可改写它。

这种“可信控制元数据与普通数据访问分开”的原则可借鉴到Proxy。但RBT里的虚拟bounds不是HPA归属证明；绕过翻译的元数据路径反而要求根配置、物理页、上下文切换与撤销在可信控制下，不能成为越权DMA旁路。

## 6. 保护粒度：全局buffer、local变量与整段heap

host分配并作为kernel参数传入的buffer分别维护bounds；local变量作为独立region处理。动态heap为控制元数据规模，只给整个heap chunk一条RBT，而不是为每个kernel内malloc对象逐项跟踪。heap内部A越界到B可能仍在同一大region中，不能据“bounds checking”就宣称细粒度动态对象安全。

Table4写host buffer逐对象、local线程间、heap kernel间隔离；正文又描述local逐变量和heap按context持久存在。这些说法需要实际上下文/RBT设置约束才能完整衔接，不应把表中简述提升为跨任意线程、kernel、应用和Client的全部隔离证明。shared、子字段和temporal safety也没有相同覆盖保证。

§6.3建议ID不足时合并相邻buffer的bounds。这会降低二者之间的隔离：若原buffer A和B合并，同一region内的A→B访问不能再靠该边界区分。不能只写成容量提升而省略安全粒度变化；本项目不同Client的授权对象不得为省元数据而合并为共同访问域。

## 7. 指针类型、短ID与伪造问题

64bit指针的高16bit包含2bit类型和14bit metadata：Type1（C=0）跳过检查，Type2（C=1）携带加密buffer ID，Type3（C=2）携带log2 size以优化base+offset寻址。Type1来自可信静态分析结果，不能等同任意请求可自选的“免检”权限。

论文用每launch新key加密随机ID，意在防攻击者从kernel参数顺序猜对象。加密隐藏ID与不可伪造授权不是同一性质：输出空间仍只有16384种；在均匀且攻击者可试tag等条件下，命中特定有效ID的单次概率为1/16384，任意34有效项为34/16384。若另满足1024次独立尝试和相同接受条件，前者累计约6.06%。这些只是条件算术，不是实测攻击成功率；fault终止、权限、目标bounds和重试策略都会影响实际后果。

论文未给明确cipher、认证绑定、尝试预算或失败恢复协议，不能以key长度代替14bit可见标签空间的论证。若攻击者能改完整指针，还需解释为何不能改C=0跳过检查、复制已观察到的有效tag，或通过低48bit运算进位影响metadata。受害binary不可修改不自动回答运行期数据指针可被破坏的问题；本轮没有作者实现，因此不把这些覆盖问题写成已证实漏洞。

## 8. 静态分析与省略检查的正确条件

LLVM从GEP构造依赖树，根据host参数及已知上界反向求值；可证明的访问设Type1，不确定则保留动态检查。图遍历等间接索引难以完全静态处理，因此不能只靠编译期过滤保证全部安全。

§5.3.2把get_global_id最大值与CL_DEVICE_MAX_WORK_GROUP_SIZE联系起来，需特别校正：Khronos将global ID定义为整个NDRange的工作项身份，local size才涉及一个work-group。即使设备最大work-group为256，两个256项group且offset=0时，global ID仍可到511。非零global offset、多维展开、访问字节宽度和整数溢出也必须纳入证明。

本轮定向阅读[Khronos OpenCL C源规范](https://github.com/KhronosGroup/OpenCL-Docs/blob/main/OpenCL_C.txt)的工作项函数段，取得副本SHA256为`718025da30a9919c275ccf172e67ecea7303a7465a980299a4c264b0552a6e13`；不是整份规范精读。上述是对论文文字上界的条件反例，尚未取得实际分析器，不能断言其实现必然使用错误上界或已被攻破。

Type3将对象round到2的幂以编码size，可能加入padding；4097B扩至8192B，额外4095B约99.95%。padding内越界不再由原始精确size边界立即识别，作者建议canary在kernel结束后查写；这不能补齐非法读或提供同等即时阻断。性能与粒度权衡应一起报告。

## 9. BCU缓存、合并访问与失败语义

默认每core有4项FIFO L1 RCache和64项全相联L2 RCache；tag存14bit ID，data存48bit base、32bit size、readonly及12bit kernel ID。BCU计算一次sub-workgroup访问地址的min/max，尽量与LSU、D-TLB和cache访问并行。kernel结束或context switch刷新RCache。

合并检查应按相同授权对象/上下文分组，并只纳入active lanes，覆盖完整字节区间及读写权限。只比较起始地址不够：最后一个合法字节处的4B写仍会越界。论文未给足逐lane多对象、masked lane、atomic、溢出及kernel ID复用的实现细节，不能由min/max示意图替代全覆盖证明。

Fig12的Type1与文中Type1/Type2编号需要按C值和实际路径核对，避免把图上简写当独立权限定义。若有precise exception可立刻fault，否则作者设计为记录错误、load返回0、store丢弃，最后或经SVM报告。论文明确的“丢弃非法store”要求阻断真实副作用，而不仅是打印一条告警。

这种失败处理与项目完成通信有关：kernel跑到末尾或native fence终态不代表应用正确；BCU错误必须可靠传入所属任务，输出发布策略不能忽略。Host可写SVM日志在论文可信driver模型下也不能直接迁移为恶意Host下的权威错误记录。

## 10. 硬件与元数据开销复算

Table3用45nm FreePDK、Synopsys及OpenRAM，在1GHz估算新增逻辑和SRAM；这不是Mali或现成NVIDIA芯片的功耗实测。L1每项107bit×4为53.5B，L2 tag为112B，data为744B，共909.5B/core；16/24core分别约14.21/21.32KiB，核对文中14.2/21.3KB。

表内面积合计0.0858mm²、leakage799.75µW、dynamic203.36mW，属于给定综合模型。该909.5B不包括每kernel的全量RBT：若按12B存储字段为192KiB/表，若常见64bit ABI将struct补齐到16B则256KiB/表；实际布局未取得，两者仅示例，不能当作者已测占用。

size字段32bit最多表示2^32−1字节，超大buffer需要额外约定或分段；128个参数也不是实际页/间接资源数量的普遍上限。模型所省寄存器与metadata流量有价值，但不能省掉可信授权与实际生命周期信息。

## 11. 评估方法与结果

GPUShield主要使用MacSim cycle-level模拟：NVIDIA模型16SM、1.6GHz、1024threads/SM、256KB register/SM、16KB L1；Intel模型24core、1GHz、每core7硬件线程、32KB L1。共享2MB L2和16 memory channels，Intel trace用GT-Pin取得。真实SVM overflow观察、硬件综合和性能模拟是三类不同证据。

| 评估 | 原文结果 | 使用限制 |
| --- | --- | --- |
| 88 CUDA、17 OpenCL | 默认4项/1cycle L1及64项/3cycle L2，多数接近100% RCache命中、性能损失接近零 | 为模拟负载和默认时序，不是现成GPU部署零开销 |
| RCache敏感性 | L1 1–16项；更长L1/L2 latency时streamcluster最敏感 | 命中率接近100%不独立代表整个提交/初始化成本为零 |
| 静态过滤 | 编译分析数十毫秒；部分简单访问可完全省runtime检查 | 间接访问仍需动态检查；未给完整真实应用/JIT部署成本 |
| 双kernel共享 | Intel模型21种配对，平均开销低于0.3%，最差bfs+nn inter-core约6.2% | 同应用多kernel性能不是互不信任多Realm安全验证，平均值不代表最坏保证 |
| 9个Rodinia工具对照 | CUDA-MEMCHECK、clArmor、GMOD报告平均归一化72.3×、3.1×、1.5×，GPUShield约0.8% slowdown | 比较旧工具、不同机制覆盖及模拟方案，不能直接外推当代Compute Sanitizer或本项目开销 |

图19streamcluster的CUDA-MEMCHECK为224×、GMOD109.2×；1000次launch及软件构造/析构会显著影响结果。默认大样本“接近零”和该小子集0.8%应保留各自条件，不能拼为统一精确总开销。没有原始逐benchmark数值、完整重复统计和生产driver初始化测量，不从柱状图制造更多精确小数。

§6.4提出替换已有软件if检查，但明确未实现。即便未来可用返回0/丢store替代越界访问，if分支可能还控制其他副作用，不能无条件删除程序语义检查。文中“最高76%软件检查成本”不等于本方案已经获得76%提速。

## 12. Artifact来源核查：原方案、基础模拟器和第三方不能混同

论文引用[gthparch/macsim](https://github.com/gthparch/macsim)作为基础模拟器。本轮确认仓库元数据可访问，但未取得与论文匹配的GPUShield patch、BAT分析器、加密ID实现或原始trace；基础模拟器存在不等于作者完整artifact公开，也不据检索未命中断言从未公开。

限定GPUShield仓库检索返回[cwang360/vortex-gpushield](https://github.com/cwang360/vortex-gpushield)，描述为修改Vortex SimX来模拟BCU，不能当论文作者的MacSim实现。固定commit为`87888f85a6f4411da8ccda416b8160afd3644a34`，完整1931项树未截断；选取README、bcu.h/cpp、core.cpp、execute.cpp和bounds_test/main.cpp六个blob，逐个验证Git SHA1与SHA256。

完整静态阅读README、bcu.h、bcu.cpp和小测试；core.cpp仅定向阅读BCU投递与dcache读写，execute.cpp仅定向阅读load/store执行段。六个blob取得不等于六文件全部审计，更不等于1931项代码通过验证；未构建或运行该项目。

第三方bcu.h硬编码地址→ID和RBT示例；bcu.cpp只读取mem_addrs首项，计算起始地址和readonly结果，通过日志打印valid/invalid，然后仍发送Output。其core.cpp把同一trace并行投递LSU和BCU；execute.cpp的普通load/store调用dcache_read/write，后者进入实际模拟内存读写。本次选定路径没有用BCU evaluation守卫这些副作用，不能将该实现视为论文要求的“非法读返回0/非法写丢弃”的证据。

小测试含d[-1]、a[10]及10B数组写13B等错误，末尾仍可能打印Success；它主要验证常规结果和输出地址，不独立证明越界被阻断。这里是对第三方固定代码路径的静态判断，不是论文漏洞、真实硬件攻击或本项目失败。其cache配置也不同于论文默认4/64项，不能用该工程替代原性能复现。

## 13. 与CCA GPU及库内论文的关系

GPUShield、cuCatch、GPUArmor、GMSBench讨论程序对象级内存安全；PORTAL/CAGE/ACAI讨论可信设备服务、执行和归属；PhantomMap强调实际页与映射生命周期；MOLE强调内部MCU/固件信任。前者不能替代后者，后者也不自动防同一授权域内全部对象错误。

GMSBench提供delayed/alias UAF、cross-space及sub-object等负例，而GPUShield主要为spatial设计，不能预期它完成全部149项。Let-Me-In是后续指针元数据工作，正式HPCA2025 DOI已核但本轮全文未取得，不以其题名推断已解决上述全部问题。

## 14. 对项目的具体设计建议

继续接受RMM认证Client、ProxyRealm受检软件IPA→HPA翻译后合成GPU直接HPA Stage-1、其他设备受检Stage-2，以及实际页表/root/MMIO/固件保护假设。硬件作为模拟载体；本文的BCU硬件扩展并非否定项目现有设计的理由。

当前优先将已实现GPUVM、BO、private plan/snapshot、native fence、cookie/epoch和RMM可信通知连接成同一授权生命周期。相同VA、BO ID或cookie不表示同一对象实例；页复用前须有可信停止访问与失效依据，不能用短ID或epoch本身代替DMA静默。

性能优化可借鉴“把可证明稳定的检查前移、缓存授权结果”，但cache必须绑定Client实例、GPUVM/root generation、对象/backing generation、权限与device epoch；任一变化就失效。不同Client的对象不能为减少RBT压力合并成共同权限，Client提交的免检标志也不能直接生效。

若开展细粒度BO/子对象研究，应先明确是否信任Client binary与编译器，并为pointer type、metadata、间接指针和异常提供闭合授权规则。只在映射时证明页面属于Client，无法推导任意运行时索引仍在某子对象内；除非限制程序访问行为，否则需持续对象级执行约束。

## 15. 对中断和模拟验证的启示

可信物理IRQ仅说明设备有事件；BCU告警、真实native fence、任务错误和Client终态必须关联到正确任务与代际。重复、迟到、合并通知不得把越界任务变成SUCCESS，也不能释放尚有设备访问的页面。应用结果正确、输出可发布、DMA静默和安全复用分别列证据。

模拟测试必须实现所声称的状态转移和副作用阻断：非法请求只打印日志而仍改变受害者内存，只能支持检测/时序模型，不能支持隔离成立。应检查实际受害页哨兵、任务错误、真实执行探针和另一Client恢复，而非仅看“BCU检查被调用”或Success字符串。

这不要求换真实CCA硅片；在用户接受的模拟假设下同样可以构造有区分力的反例。优先覆盖同页跨对象、跨Client实际HPA、撤销后旧引用、不同lane不同对象、末尾跨字节写、静态上界变化和reset后旧事件；本轮仅提出设计，未执行。

## 16. 评价与继续方向

贡献是结合GPU少量buffer、SIMT和寻址模式降低对象bounds检查开销，及将编译器、driver和BCU连起来。证据不足处是对象/Client模型差异、heap粒度、短标签授权、免检与静态分析可靠性、完整错误传播和原artifact不可得；这些需要补协议或实现证据，而不是仅比较平均性能。

下一步继续获取Let-Me-In和GHost正式全文，对照细粒度metadata、跨GPU/Host边界和可信控制面；原始GPUShield实现若取得，再补静态复核。第三方Vortex可作为模拟语义审查例子，不能作为原方案性能、安全或作者代码证据。

统一记录：15页全文/19图6表/79引用/12页视觉/六blob有限静态/规范定向核查/自写算术/Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者或第三方执行、攻击、模拟、硬件run-id｜保留支撑研究，整体继续。
