# Obsidian：安全加速器联合搜索、可信预取与主动清零精读

## 1. 身份、版本与阅读范围

论文：Obsidian: Cooperative State-Space Exploration for Performant Inference on Secure ML Accelerators；Sarbartha Banerjee、Shijia Wei、Prakash Ramrakhyani、Mohit Tiwari；arXiv:2409.02817v1，2024-09-04。

[arXiv记录](https://arxiv.org/abs/2409.02817)；[明确v1全文](https://arxiv.org/pdf/2409.02817v1)；[作者公开全文](https://spark.ece.utexas.edu/pubs/ARXIV-24-obsidian.pdf)；[作者实验室](https://spark.ece.utexas.edu/)；[v1 TeX源包](https://arxiv.org/src/2409.02817v1)。作者版、明确v1和当前无版本PDF逐字节SHA相同，892692 bytes；SHA256：cd9083c20a100c1f10a3e7b84433d7667351dbc8f396ac35c6e23c2f20e8b7af。

已读全部14页、§1–8及69条引用；视觉复核第1/3/5/6/7/8/9/10/11页，覆盖全部8图、Table 1、Algorithm 1–2及Eq.(1)–(3)。arXiv记录仅列v1，无journal reference；限定Crossref题名查询前五项未匹配，不能据此断言没有后续正式版，本报告仅认定上述预印本。

TeX源包4631062 bytes，SHA256：4f3b94b7287e811737e36da64c1bb0679ae4b39deeb548eedd21fe709bb7f2af；94个普通文件逐成员记录长度和SHA256。定向读主入口、算法/公式及评估对应源段，未执行LaTeX/Makefile，未将模板或未启用草稿章节当作已发表证据。

证据目录：build/cca-gpu-followup-20261027；acquisition115/115b.json、obsidian-identity115.json、obsidian-render115.json、obsidian-source-manifest115.json及obsidian-arithmetic115.json。实验室明确链接全文；两次限定GitHub仓库查询零结果，不等于artifact不存在。未取得匹配实验实现，不用MAESTRO/GAMMA/SCALE-Sim通用上游代替。

本篇是安全ML ASIC的设计空间/编译优化模拟研究，不是Arm CCA管理器、GPU直通实现或中断认证协议。mapping指tensor tiling、loop order和dataflow，而不是IPA→HPA映射；计入项目的安全性能研究支撑材料。

## 2. 相对于Triton、SecureLoop的研究问题

GuardNN/MGX类方案提供片外加密与完整性，Sesame增加固定流量整形和上下文切换清零。Obsidian尝试在这些保护机制保留时优化成本，联合考虑crypto、shaper、zeroizer，而非只对算力或普通内存带宽搜索。

解析模型能搜索较大空间，但难精确捕获有限队列、scratchpad占用、跨层预取和清零端口竞争；逐周期模拟能看到瓶颈，却不能遍历巨大空间。因此先由解析模型筛选，再对小候选集合做编译profiling。

与SecureLoop相比，它进一步建模流量隐藏和清零，并用数据复用减少fake事务；与Triton的可选安全策略不同，本篇评估意图是保留既定保护来优化合法调度。实际跨租户隔离、安全策略认证和密码新鲜性仍是部署前提，不能单凭成本模型推导完成。

## 3. 威胁模型与信任边界

§3.4允许攻击者观察、篡改片外内存与总线数据，观察读写总线利用率以推断输入大小/模型结构，并在受害租户执行前后读scratchpad。假定安全启动、无硬件木马、租户通过远程证明验设备后传入模型/输入，且每租户密钥有受保护存储。

片内计算、固件/配置加载、编译器依赖分析、可信counter状态和保护机制均落入信任基础。本文关注accelerator runtime，未实现RMM认证Client、页归属控制、完整证明/密钥交换、GPU固件验证、Host注入中断防护或设备reset恢复协议。

完整性counter借鉴MGX在设备内生成，避免Merkle tree遍历；仍需保证可信预期版本和密钥/nonce生命周期。只读权重可省动态写版本维护，不等于无需认证、无需区分模型版本或可以接受旧会话重放。

shaper针对总线利用率观察；close-row策略针对DRAM row-buffer时序。二者没有自动覆盖访问地址、控制器排队、功耗、整体执行时间、调度/通知频率及所有共享资源侧信道，本文也没有给出这些面的端到端不可区分证明。

## 4. 解析搜索：把安全成本纳入候选生成

第一阶段用GAMMA遗传搜索与MAESTRO成本模型，生成各层top-k tiling/loop-order映射。采用output-stationary、32bit数据；片外有效吞吐按crypto限制。去掉比最佳映射开销高10%以上的候选，k随层复杂度从2到16变化，是剪枝启发式而非保留全局最优的保证。

认证块候选为64/128/256/512/1024/2048/4096B。内存trace区分demand、redundant和integrity；原本为认证而多读的数据，若可在scratchpad保存到下一次使用，则替代后续demand读取。复用依赖相同数据版本、容量、合法地址和没有提前驱逐，不能仅凭地址相同重用旧数据。

shaper带宽按memory-bound或compute-bound映射估算，再在整个模型范围寻找统一常量，权衡stall和fake事务能量。§4.1.4明确为安全不能在各层执行时随需求改变整形带宽；不能把逐层候选带宽直接部署成暴露层结构的动态模式。

随后用模拟退火从各层候选组合筛到m=40个模型候选，1000次迭代、m个不同初态的搜索；在Transformer上观察profiling收益趋平后选40。多次启发式运行不能证明返回严格全局top-40、候选互异或所有复杂模型已收敛。

多租户场景还把scratchpad清零成本纳入每层估算。Eq.(3)用占用bit数除以a再乘写周期，但正文将a称为“地址的bit数”；若确为地址宽度，量纲不足以表示每次可清零的数据量。应明确写入粒度/端口吞吐，不能静默把含义改成word宽度后宣称公式已验证。

## 5. 编译profiling：合法预取、片内转发与主动清零

liveness分析追踪数据消费及复用距离，释放不需继续保留的位置；dependency分析只提前读取已准备好的数据。模型权重只读但仍须通过正确模型/版本的认证；ifmap依赖上一层ofmap实际产生，不能仅因profile中的时间已到就认定当前执行也准备好。

固定节奏的总线时隙内，将原fake事务换成后续合法需求预取，减少未来stall。它不是任意增加可见传输率：保持整形外部观察条件、真实/伪事务不可区分及预取不越过租户权限，是保持安全目标的前提。

store-to-load forwarding把新ofmap从output scratchpad送入input scratchpad，可避免不必要的片外往返与crypto延迟。依据是数据始终停留在可信片内且生产者/消费者版本对应，不是绕过所有来源验证；跨Client、跨epoch或离开可信边界时不能直接套用。

在预定层边界切换租户时，禁用后续层预取，改为对已消费且可重载的数据提前清零，与计算重叠。§6.3显式关闭cross-layer load promotion，因为中间会执行其他租户；不能将最强跨层预取收益与逐层切换清零收益无条件相加。

算法所称“复用距离大于容量”主要说明现在不值得保留，不等于该值永远不再使用。清零必须保证未来可从正确版本合法重载，并覆盖别名、并发消费者、尚未完成的读/写和依赖队列。静态DNN数据流证据不自动适用于任意恶意GPU命令流。

零化硬件与主数据路径共享写端口，主路径优先；zeroize有独立队列，模型每周期清256B。已提交清零命令不等于实际写完；低优先级队列在高负载下可能延后，可信切换仍需等待完成并清理剩余秘密，不能用“已经主动清过部分”代替交接条件。

预加载integrity hash到专用buffer被作者留作未来工作，不算已评估优化。liveness、标签、counter、命令队列、密钥及设备其他状态的清理覆盖也需分别证明，不能由scratchpad清零比例推导整个GPU没有残留。

## 6. 模拟实现与评估边界

Table 1云配置为256×256计算阵列、800MHz、DDR4@2400MHz、crypto6.4GB/s，输入/权重/输出scratchpad为6144/6144/2048KB；edge为32×32、100MHz、DDR3@1066MHz、800MB/s与512/512/192KB。按十进制吞吐复算两者crypto均8B/cycle，不能把不同规模平台当相同资源对照。

§5.1先说parallel AES-GCM，后又说使用1-cycle encryption/1-cycle integrity的pipelined实例；配置叙述存在歧义，未获实现核对。SCALE-Sim加入指令/需求队列、shaper和zeroizer，Ramulator模拟DRAM，crypto用固定延迟建模，能量来自文献活动计数与DRAMPower，不是密码硬件或GPU板卡实测。

模型包含AlexNet、ResNet50、FasterRCNN、DLRM、AlphaGoZero、Translate的LSTM编码层及基础Transformer。引用GPT或包含Transformer不等于完整现代自回归LLM、KV cache、多GPU训练或真实推理输出验证。

baseline是在一代GAMMA搜索后选出的top mapping、64B认证粒度及用户设定整形带宽。它是未充分优化的安全baseline，不是已知最优安全实现；收益包含一般tiling/loop-order搜索的贡献，不全来自安全硬件新增优化。

部分大层在1000代仍未收敛而被截断，作者承认映射有较大性能变化。Figure 3展示20个组合候选的分布，不等于20次独立真实系统实验。Figure 5也含EDP大于1的候选，不能说每个所谓top-m候选都优于参照。

## 7. 性能、能耗与清零比例的核对

摘要/引言：解析阶段云/edge时延下降20.5%/8.4%，能耗下降24%/19%；profiling再下降时延9.1%/12.2%、能耗13.8%/13.1%。但§6.2.1将edge解析能耗写8.4%，与摘要19%冲突；TeX对应段也如此，非文本提取错误。

正文总结果写云/edge“speedup”29.6%/20.6%，能耗改善37.8%/21.5%，恰好是正文阶段百分比直接相加。若第二阶段的“再下降”是相对前一阶段，云/edge时延组合应为27.7345%/19.5752%，云能耗34.488%、按正文edge能耗20.3996%；按摘要19%则edge能耗29.611%。

这些独立算术用于揭示分母/聚合口径不足，不能替作者选一个值作为真实纠正结果：原始逐负载数据、阶段分母与平均方式未公开核实。如果阶段收益本是对同一初始baseline的百分点贡献，可以相加，但需要明确；本报告不宣称复现29.6%或以某个替代值证明作者实验错误。

Figure 6是相对无保护baseline的总时延与能耗；noOpt、AmOpt与Obsidian三者均是安全配置的不同优化阶段，最终柱仍高于1。不能把安全配置之间的改善说成比无保护更快，或把speedup百分比、时延下降和吞吐提升混用。

认证块优化后作者报memory traffic下降29.1%/31.2%，其统计包括需求、冗余与hash请求；不是所有硬件事务、输出质量或信息泄漏降低同比例。fake事务变少也不单独证明安全增强，重点是外部观察的形状是否仍满足既定限制。

Figure 7正文说有cloud/edge“两图”，实际可见一个AM/Profile堆叠图，未从中恢复独立edge数值。Figure 8清零比例22.8%/11.2%指秘密数据中在层执行期间提前清掉的体积；不是总清零量减少、上下文切换时间同幅下降，更不是22.8%的内存无需保护。

## 8. 解析目标与伪代码的可复核缺项

§4.1.4把模型EDP定义成各层EDP相加，而通常串行模型总EDP为(sum E)×(sum T)，含交叉项。两者可作为不同目标，但不保证排序相同。独立示例：A两层E=(1,100)、T=(100,1)，层EDP和200、整体10201；B的E=T=(20,20)，层和800、整体1600，排名反转。

因此其层EDP和应视为代理目标，不能未经说明证明整模型总能耗×总时延全局最优。§4.1.4还说memory-bound时延为事务数乘shaper bandwidth；若bandwidth单位是事务/时间，应该检查量纲，不能把该文字直接当作可执行成本模型。

Algorithm 1将memTraffic初始化0却仅在当前值大于非负traffic时更新，按字面正流量永不更新；GenerateMemTrace参数写h而非循环候选j，dist/spad的使用范围也不充分。Algorithm 2接受新mapping后未显式更新Cost，随机索引范围也混用迭代n。视觉与TeX均核到这些缺项。

上述是论文伪代码/定义的可复核问题，缺匹配实现时不能将它们宣称为已运行的实现漏洞。源包只有论文、图与模板，不是搜索/编译/模拟程序；未执行算法、模型、攻击、构建或容器，未声称独立复现性能。

主TeX入口实际启用eval而非evaluation，并将独立Security_analysis和threat_model输入注释。不能把源包中未编入此PDF的安全分析草稿拿来填补当前正文的保证，也未把其ACM模板当作正式会议录用信息。

## 9. 与项目的联系及设计建议

以`CURRENT_BASELINE.md`为当前实现入口；本篇在RMM认证原Client、ProxyRealm检查实际HPA授权并建立受保护GPU Stage-1的设计假设下分析，不把研究假设全部写成当前已实现。保留GPUVM/BO、私有plan/snapshot、原生fence/cookie/epoch及可信通知链。

可借鉴固定安全约束内的后台工作安排：只对当前Client、对象/页授权、权限、任务plan与epoch均有效的请求预取；只在可信生产者数据已经完成、版本明确时转发；把不再需要的秘密清理提前，与合法计算重叠。每一步仍需失败/取消/reset下的撤销规则。

预取和转发不能延长已撤销映射，也不能把profile预测当实际完成。用户授权页范围与AuthBlock、缓存行或tile大小不同；多读为认证服务仍不可跨Client对象，真实HPA授权继续是独立不变量。

提前清零只是清理进度，安全交接应等待旧任务权威终态、在途设备访问排空、剩余秘密清除及旧epoch引用失效；随后才可授予下一Client。CPU中断到达、清零入队、fence通知和DMA静默是不同事件。

若将来增加完成事件，应分别表示任务完成、输出发布和可安全复用资源，防止一个“完成”通知提前触发页/BO/队列重分配。通知可丢失/重复/乱序，最终仍以Proxy可信状态和原生fence身份判断，不能借静态DNN调度免除中断通信认证。

流量隐藏若进入研究范围，需先明确允许公开的整形带宽、执行起止、任务长度及调度边界。按秘密模型选出的带宽虽整轮恒定，参数本身是否泄漏模型属性仍需策略说明；论文未证明跨会话参数选择完全无泄漏。

不建议为引入本文立即添加通用RPC预取/清零框架。优先用它完善性能拆分与生命周期证明：同等安全约束下减少了什么工作、复用了什么证据、哪些撤销条件会迫使重新验证。硬件是模拟测试载体，不以板卡缺具体模块否定研究机制。

## 10. 后续链与执行记录

沿同组工作取得SESAME arXiv:2007.06751当前13页全文与版本记录，仅初步核对标题/摘要，待完整精读和独立发布；另取得Bandwidth Utilization Side-Channel on ML Inference Accelerators（arXiv:2110.07157）记录，尚未全文精读，均不计完成。

统一记录：研究目的为安全机制联合优化与可信交接边界｜对照glmark未测→本版未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜只读来源采集、PDF/TeX阅读与渲染、独立算术及Notion全文回读，无作者程序/构建/模型/攻击/硬件run-id｜保留研究与指标/伪代码/实现缺项，整体调研继续active。
