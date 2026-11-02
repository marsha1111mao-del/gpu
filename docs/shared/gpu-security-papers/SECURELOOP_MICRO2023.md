# SecureLoop：可信加速器认证块、跨层调度与安全开销优化精读

## 1. 文献身份与证据范围

论文：SecureLoop: Design Space Exploration of Secure DNN Accelerators；Kyungmi Lee、Mengjia Yan、Joel S. Emer、Anantha P. Chandrakasan；MICRO 2023，Toronto，2023-10-28，194–208；DOI：10.1145/3613424.3614273。

[出版入口](https://doi.org/10.1145/3613424.3614273)；[Crossref元数据](https://api.crossref.org/works/10.1145/3613424.3614273)；[MIT作者公开全文](https://people.csail.mit.edu/mengjia/data/2023.MICRO.SecureLoop.pdf)；[论文附录明确提供的artifact](https://github.com/kyungmi-lee/SecureLoop-MICRO2023Artifact)。标题、四作者、DOI与15页长度核对；未取得ACM正文做逐字比较。

已读作者PDF全部15页、§1–7、53条引用、附录A.1–A.8；视觉复核第1/3/4/5/6/7/8/9/10/11/14/15页，覆盖全部16图、2表、Algorithm 1、四条公式和artifact说明。PDF为1234877 bytes；SHA256：de57c240c4986cf8327b3d2219eb5ad48b822d4489b26ae5a52ab1a2bd4f3e31。

证据目录：build/cca-gpu-followup-20261027；原全文与正式元数据沿用113批采集，新增acquisition114至114e.json、secureloop-render114.json、secureloop-source-audit114.json、secureloop-arithmetic114.json。来源失败与恢复路径保留，不用一次网络失败推断资料不存在。

这是一篇安全DNN ASIC设计空间与调度工具论文。其“mapping”主要指算子计算及数据复用的loopnest映射，不是SMMU的IPA→HPA地址映射；不是Arm CCA管理器、GPU直通系统或跨VM中断协议。它补充项目性能与安全成本分析，不能计为新增一套CCA GPU架构。

## 2. 问题：认证会改变最优数据流

常规加速器调度以PE利用率、片上容量、DRAM流量为主要约束。安全加速器每次片外读取还需解密、取得认证tag并验证；只取计算需要的元素不够，通常必须取其所属完整AuthBlock及tag。片外写入也需按块计算新tag。

作者把额外流量分为tag读取、认证块跨越所需数据边界造成的冗余读取，以及改变认证布局时的rehash流量。最小化普通DRAM读取的tile不一定最小化这些安全成本；认证引擎也可能比DRAM带宽更早成为瓶颈。

跨层问题：某层ofmap成为下一层ifmap，而生产者和消费者tile形状可能不同。按生产tile直接分配AuthBlock能减少本层tag，却可能让消费者每次读取额外整块数据。Figure 4给出此类错位，不等于未授权访问；多读仍须在同一合法安全对象范围内。

卷积halo也造成重叠。直接让每个tile成为一个AuthBlock，可能重复加密与存储halo，或为了认证而反复读入无用元素；im2col消除tile重叠的同时会扩张和复制输入，不能把其成本视为零。

优化目标是保留机密性/完整性要求并改变合法调度与认证布局，减少额外工作；不同于通过将秘密标成公开、关闭认证来降开销。安全条件仍需由实际系统落实，工具本身不证明端到端TEE安全。

## 3. 威胁模型、信任基础与新鲜性

§2.2假定片上结构可信、片外DRAM不可信。权重、输入、输出及中间partial sums在片上明文计算，跨片外边界使用AES-GCM类认证加密；攻击者可以观察或篡改片外内容。本文没有建立对恶意片上固件、同设备恶意租户或任意CPU驱动的完整隔离模型。

加密seed包含counter、数据地址与随机IV；counter在数据生成新版本时递增。作者借鉴MGX/GuardNN/TNPU，根据显式且可预测的数据流，从片上结构或可信CPU计算版本，假设取得counter无需复杂片外访问。

该假设是消除Merkle tree成本的前提，不是单凭AES-GCM就获得抗重放。部署必须保证expected counter来自可信状态，且同一密钥下nonce不复用；地址复用、重启/reset、分支执行、取消重试、counter回绕及快照回滚均须定义新鲜性域。

论文未给出RMM认证租户、密钥派生/撤销、设备证明、CPU与设备身份绑定、跨Client页授权和故障恢复协议。不能把“片上可信”扩大为现有Host和GPU所有固件都自动可信，也不能把模拟器使用的认证成本参数当作已部署的密码边界。

认证完整性是对给定密钥、nonce及认证域的数据篡改检测，不自动证明计算语义、当前请求身份或输出属于本次任务。认证失败后的错误fence、输出禁止发布、DMA停止与资源回收不在本文实现范围中。

## 4. 三步调度方法

第一步：用有效片外带宽min(DRAM带宽,密码引擎带宽)及额外能耗修正常规scheduler，再为各层生成top-k loopnest。本文基于Timeloop并扩展top-k输出；不是仅把无保护的最快schedule拿来加密码引擎。

该建模假设不同模块适当流水化、启动和排空成本较小，可通过双缓冲等重叠。它适合比较稳定数据流；短任务、突发请求、认证失败、队列阻塞、跨Client切换或GPU执行时序不因此得到精确预测。

第二步：给定tile及跨层/halo依赖，枚举AuthBlock方向和大小，最小化tag与冗余读取。细块减少多读但增加tag；大块减少tag却可能跨tile边界。Figure 7的不同方向说明最优块不是简单选最大块或固定缓存行。

作者把块与重叠tile相交计数转化成线性同余，利用扩展Euclid求解，避免逐元素仿真。高维情况沿选定维度展平再切分；其最优性限于枚举的认证块形态、给定tile、合法候选与当前成本模型，不是所有内存布局的全局最优。

第三步：跨层loopnest组合为k的层数次方，使用模拟退火联合调整。每次改一层候选，重新评估其认证依赖；允许按温度接受较差状态，随后降温。默认k=6、1000次迭代，是搜索成本折衷，不是全局最优性证明。

简单BN/ReLU/zero padding可在作者模型内伴随ofmap生成；pooling和残差合并需独立步骤及rehash，因此按边界把DNN分段再搜索。“不需rehash”的结论只适用于统一布局能沿合法依赖复用的段，并非删除所有层间认证。

## 5. 印刷公式的独立核对

§4.2 Eq.(1)–(3)给出左右端落在重叠区或跨行包围重叠区的条件；Eq.(4)印刷为u×k模wi落在min(wi−wj−u+1,0)到wi−1的余数范围。PDF视觉与文本提取均确认是min，不能静默替作者修为其他表达式。

独立边界核对：沿用示例h=30、wi=30、wj=20，取u=1。单元素块应只覆盖600个相交元素；Eq.(1)–(3)计数600，而按印刷Eq.(4)的min(10,0)=0范围计数900。这里发现的是印刷推导在此输入下不等价，不等于已复现artifact运行错误。

对照固定源码，compute_redundant_reads的right分支用min_r=x−(u−1)、max_r=w−1，并单独处理left/both、h=1及u≥w；它没有直接使用印刷Eq.(4)的min截断。因此不能把上述反例推广为作者全部性能结果失效。未执行该函数，也未证明其所有边界正确。

## 6. 评估条件与独立算术

基础设计为row-stationary、14×12 PE、约131kB片上global buffer；片外LPDDR4为64B/cycle；加密引擎按weight/ifmap/ofmap各配一个。Timeloop/Accelergy估算周期、能耗与面积，使用其支持的40/45nm模型和文献密码引擎参数，不是板卡实测。

工作负载为AlexNet前五个卷积层、ResNet18、MobileNetV2；artifact示例batch=1、3×224×224输入、16bit整数，PyTorch模型pretrained=False用于形状/依赖建模。不能说已经对完整AlexNet精度、真实加密推理结果或现代LLM/KV cache正确性做了验证。

Table 1三种schedule都crypt-aware：Crypt-Tile-Single使用tile-as-AuthBlock，无跨层微调；Crypt-Opt-Single增加最优块选择；Crypt-Opt-Cross再联合搜索。因此Figure 11不是“安全加速器比无安全加速器快33.2%”，而是不同安全调度之间的比较。

Figure 11的归一化时延分别为AlexNet 1.44→1.40→1.39、ResNet18 2.37→2.28→2.25、MobileNetV2 14.77→10.35→9.86。基准均为相应无保护设计；这些数字是总时延倍率，不能当成额外开销百分比。

按印刷舍入数复算，MobileNetV2从14.77到9.86的时延下降33.24%，吞吐倍率1.498、增加49.80%。论文称“33.2% speedup/faster”数值对应前者，报告应明确指标；该结果仍比无保护时延约慢9.86倍，不能解读成近零安全开销。

第一步认证布局10.35相对14.77时延下降29.93%；再到9.86，相对10.35局部下降4.73%，相对原14.77再下降3.32个百分点。正文“additional 3.3%”与后者一致，不宜当成相对前一步下降3.3%。AlexNet、ResNet18总时延下降约3.47%、5.06%。

作者称EDP最多改善50.2%、额外片外流量减少37–94%。这些指标不等于应用时延或总DRAM流量的同幅改善；没有独立完整原始测量，本报告保留为作者结果，不据柱高伪造精确流量和能耗复现。

正文五次退火给MobileNetV2 9.76–9.99、标准差0.08、图中均值9.86；附录A.6写9.70–9.99。当前固定README又写论文9.83、运行9.70–9.90，数值不同全部保留，不拼成一个统一复现区间。

Table 2三类AES/GFMult成本：pipelined 1/1 cycle、78.8/60.1kGates；parallel 11/8、9.2/9.7；serial 336/128、3.0/3.3。独立复算三套pipelined合计416.7kGates，与§3.1一致；30套serial为189kGates，是1套parallel 18.9kGates的10倍。cycle栏反映模型吞吐/每块处理口径，不能直接当所有请求的固定端到端延迟。

Figure 13–16说明PE更多或DRAM更快未必缓解密码吞吐瓶颈，片上buffer与密码引擎要联合配比；Pareto前沿主要针对所选AlexNet、成本模型与候选设计。不据此推导所有GPU应该缩SRAM增密码单元，更不能直接套用本项目glmark提分比例。

§5.2认为同一模型服务多次请求可摊薄TEE进入时的权重传输，但未完整测量本项目每次跨Realm RPC、IRQ、页授权、取消和回收成本。模型驻留可摊薄初始化不等于常态安全检查可以移除。

## 7. Artifact固定与静态源码观察

固定作者仓库commit：c1e4fae457d696cbb844ce0ffbf97576cb7ad4eb，提交日期2023-10-19；完整递归tree 163项且truncated=false。13个选取文件分别核对Git blob SHA1、长度和SHA256；四项raw下载失败经Git blob API恢复，tile工具同样通过API取得。不是全仓库逐行审计。

全文读README、短fig11脚本和架构/能量配置；定向读认证块搜索、同余计数、scheduler退火、cost与summary、绘图归一化及notebook若干配置/汇总cell。未完整逐行读全部13文件；未读或执行依赖Timeloop/Accelergy的实现，未拉容器或运行notebook。

源码cost模型以max(Timeloop周期,密码处理周期,内存周期)估算层时延，rehash另计，再汇总层与依赖成本。可见其流水重叠假设，不包含逐条真实GPU内存请求、安全异常、中断与设备静默处理。

退火实现优化energy×latency，维护best_state与final状态并取最佳结果；不是只优化latency或仅返回最后状态。ResNet18因残差依赖的partial-update问题显式关闭局部更新；这说明模型相关处理要核对，不能推广为任意动态计算图已受支持。

额外静态不一致：`generate_arch.py`的serial参数写335，而get_latency_energy_info仅对336配置serial profile；按当前所见直接生成/消费这一路径存在参数不匹配，未执行确认。Figure 11默认parallel=11不经过该分支，不能借此否定其全部基线结果，也未修改作者代码。

认证块搜索辅助函数默认word_size=16、tag_size=64，是已见成本参数；未完成全部调用链的密码安全配置审计，不能据此断言所有硬件采用何种tag长度或已具某个伪造安全级别。工具统计密码action与tag流量不等于实际执行AES-GCM或验证nonce唯一性。

附录给Zenodo DOI10.5281/zenodo.8329657，本轮API连接拒绝，未获得归档包对照。固定Git提交可复核当前阅读范围，但不能声称其与归档发布字节一致。作者提供复现入口、Docker和预计时长，不等于本报告已经复现实验。

## 8. 与本项目的联系及可借鉴设计

当前实现以`CURRENT_BASELINE.md`为入口。本文不替代Portal/ACAI式身份与归属检查，也不替代本项目假设的RMM认证原Client、ProxyRealm校验实际HPA并合成受保护GPU Stage-1映射；地址授权和认证块优化解决不同问题。

最有价值的借鉴是“把安全成本纳入最初的资源/批次选择”：分析数据量、跨域转换、页/对象粒度检查、metadata与通知成本如何耦合，而非只优化GPU执行时间后再补安全步骤。应逐项区分setup、稳态、故障/取消及回收成本，并保留统一可比条件。

若将来引入批量授权或验证缓存，复用只限同一认证Client、对象/实际页授权、权限、当前epoch和映射生命周期；对象变更、页撤销、reset或新会话必须使旧证明失效。不能因跨层可复用AuthBlock就让已验证一次的旧页映射永久有效。

授权粒度、GPU页粒度、缓存一致性粒度与密码AuthBlock粒度必须区分：为了认证多读整块不能越过Client授权范围，跨对象拼块还需要明确认证域与合法填充。本文的性能最优块大小不授予额外访问权限。

布局/认证域变更必须绑定可信plan并协调生产者终态和消费者启动；只有来源、新鲜性和数据依赖均成立时才省掉重复转换。通知到达仍不等于原生fence完成、输出已发布或DMA已静默，安全回收仍保留cookie/epoch及reset约束。

中断隔离方面本文没有直接协议贡献。它适合作为性能建模支撑，与现有私有plan/snapshot、原生fence和可信通知分派配合；不能用静态DNN依赖推导Host注入IRQ就可信，也不把shape分析模型套作任意恶意Client任务验证器。

论文不应推动当前通用GPU RPC立即增加密码块框架；更适合形成后续研究问题：在相同安全不变量下，哪些检查和数据转换可以安全合并，以及何时必须重新验证。硬件作为模拟测试载体，不因特定板卡缺密码引擎就否定这个研究问题。

## 9. 后续阅读与记录

沿引用链与本库MGX、GuardNN、TNPU对照counter可计算性及可信域；与上一批Triton比较强制安全目标和可选策略的区别。下一篇Obsidian已获14页全文，但尚未完成版本核对、完整精读和独立发布，仍不计完成。

统一记录：研究目的为认证布局与同等安全目标优化｜对照glmark未测→本版未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜只读采集、PDF提取/渲染、固定源码静态检查、独立算术和Notion全文回读；无作者代码/构建/模型/攻击/硬件run-id｜保留研究结论与版本/公式/参数缺项，整体调研active。
