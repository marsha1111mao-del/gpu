# Dissecting GPU CC：启动、排队、迁移与执行开销的证据化拆分

## 1. 身份、版本和阅读范围

论文：Dissecting Performance Overheads of Confidential Computing on GPU-based Systems；Yang Yang、Mohammad Sonji、Adwait Jog；ISPASS 2025，Ghent，2025-05-11起；DOI：10.1109/ISPASS64960.2025.00020，Crossref 1–16页。

[正式DOI](https://doi.org/10.1109/ISPASS64960.2025.00020)；[作者全文](https://adwaitjog.github.io/docs/pdf/dissectcc-ispass25.pdf)；[作者主页](https://adwaitjog.github.io/)；[artifact](https://github.com/insight-cal-uva/hcc-ispass25-artifact)。作者PDF为1472564 bytes、16页，SHA256：a935deafbf8755105b15b89e07e04eb8f7987c97241f923c6bbf9394e5c630b2；题名、三作者、日期和页数与正式元数据匹配。作者版首页仍写will appear，未将其称为已逐字比对的出版PDF；IEEE入口502。

已完整阅读16页、§I–IX、132条参考文献与Appendix A–G；视觉核对第1–11页及第15页，覆盖全部14图、Table I、两个Listing和artifact清单。渲染16页，视觉阅读12页；全文为`dissect121-full.txt`，图像清单为`dissect-render121.json`，证据根目录为`build/cca-gpu-followup-20261027`。

artifact固定commit为0e1360ff6a03aeda30c2655b7416ee17fd68a00a；完整递归树3344项、未截断，head和tree身份一致。取得8个选定blob并核对Git blob SHA1与SHA256；范围为root README、common、fig7/fig10/fig14的选定脚本及两份处理数据，不是整个仓库或GPU驱动的安全审计。

只静态阅读上述材料，并用自写标准库脚本解析CSV/TSV、复算比例；没有import或运行作者脚本、模型、工作负载、攻击、构建和硬件测试。Zenodo DOI 10.5281/zenodo.15226687由附录给出，API连接拒绝，本轮没有取得或验证归档字节。

本文是直接相关的GPU机密计算性能研究，不提出新的CCA隔离架构或中断认证协议。它主要服务项目的“Arm GPU直通和共享实现／性能优化”部分，也帮助第二部分明确哪些优化不能改变授权、完成和回收语义。

## 2. 系统边界与安全假设

研究系统为Intel TDX CPU TEE加NVIDIA H100 CC；CPU/GPU封装、TDX module、两侧固件和TD内可信驱动属于TCB，Host/hypervisor、外部CPU内存及PCIe链路不可信。图中GPU由某一个TD或普通VM独占，不是本项目多个Client经可信ProxyRealm共享GPU。

CPU私有页不能被该配置下GPU直接DMA，故使用Host可管理的shared bounce buffer存放AES-GCM密文，再由GPU解密进入HBM；SPDM用于设备认证/会话建立。不能把SPDM、链路数据保护、实际页授权和任务完成认证当作同一件事。

论文把HBM纳入物理可信假设，因此不对HBM进行相同的外部内存加密；这是一项系统信任假设，不是实验证明所有封装、故障攻击或后续硬件都绝对安全。文中“尚无HBM Rowhammer报告”是论文写作时的陈述，不转写成当前普遍事实。

原文将TD私有内存的机密性/完整性与TME-MK AES-XTS一并叙述。分析时须拆开：AES-XTS本身不是认证加密，不能从XTS算法直接推出完整性或防重放；TDX的映射归属、可信模块及其他平台机制须分别说明，本论文不是这些机制的独立安全证明。

原文用#VE/hypercall概括GPU命令相关切换，并给出单次launch调用栈。该栈支持存在TDX bounce-buffer和转换成本，不能据此推断任意平台所有MMIO、所有GPU命令都会遵循相同退出路径。Arm项目应观察自身RMM/RPC/Proxy/native提交链。

依照项目既定假设，RMM认证原始Client，ProxyRealm控制SMMU并做实际HPA归属/权限/生命周期授权，GPU运行期由受保护的直接HPA Stage-1限制访问。无需为了复刻NVIDIA bounce buffer而改变这条主线；可迁移的是成本拆分与实验方法。

## 3. 实验条件与模式限制

双Xeon Gold 6530，每socket32核、2.1GHz；1TB DDR5-4800，四NUMA节点，H100 NVL 94GB HBM3、PCIe5×16。Ubuntu22.04.5，TDX补丁Linux6.2/QEMU7.2，TDX1.5工具tag2023ww15，CUDA12.4、驱动550.127.05。

默认VM/TD为64GB内存，绑定GPU所在NUMA0的16核；关闭hyperthreading、CPU auto-boost、NUMA balancing，固定CPU2.1GHz。CC在TD中、非CC在普通VM中运行，没有使用Host native作为该组基线，不能把结果写成TD对裸机开销。

§IV脚注5明确为访问计数器把GPU设为CC-devtools。它与面向生产的严格CC-on在调试/观察能力上有区别，本轮没有做等价性验证；不把这套结果直接宣称为生产安全配置下完全相同的性能，也不把作者的性能研究当作安全部署认证。

统计来自Nsight Systems和软件计时；不同实验重复策略并非统一给出，LLM明确三次运行中位数。没有全套逐case置信区间或系统扰动消融；不能从若干CC优于non-CC点推出保护本身必然提高硬件速度。

## 4. 性能模型与关键路径

模型写为P=(1−α)Tmem+Σ(KLO+LQT)+Σ[(1−βi)(KET+KQT)]+Tother。P实际代表执行时间；α表示数据搬运被覆盖部分，βi表示某kernel执行/排队被其他活动覆盖部分，均在0–1；不是吞吐量越大越好的P。

KLO是CPU launch调用成本，LQT是相邻launch间等待，KQT是kernel入队到真正运行的等待，KET是GPU执行事件持续时间；Tother含分配、释放及未与执行重叠的同步。把这些事件全部直接相加会重复计入重叠部分。

该模型是解释时间线的分解，不是已用独立测试集校准误差的通用预测器。α/β依赖依赖图、运行时、队列及工作负载；任意流水线须按实际关键路径处理，不能从各项平均比例直接重建全部应用端到端慢速比。

GPU事件KET也不是纯算术时间：UVM缺页及迁移可发生在kernel事件范围内并拉长该事件。若将KET增长全归因为GPU算力下降，就错过了fault服务、页迁移和CPU侧软件加密的成本。

项目可按Client打包/RPC、Proxy准入与授权、native提交/排队、真实执行、cache同步、可信完成记录、IRQ与Client观察拆分。跨VM时钟与异步事件需要关联ID和可比时基；不能把已有单段耗时或glmark总分当成所有阶段的分解证据。

## 5. 搬运、加密与分配

Figure4显示该配置最大CC pinned H2D约3.03GB/s，单核AES-GCM约3.36GB/s，独立复算前者约为后者90.18%。这与加密瓶颈相容，但差额还可能有copy、页转换和上下文成本，不是仅凭接近关系就完成因果消融。

非CC pinned和pageable带宽存在明显差别，CC下接近；作者结合Managed事件和驱动背景推断CC pinned依赖UVM分页机制。应保留“在该驱动/模式下的观察与解释”，不外推所有GPU TEE的pin操作都失去意义。

copy操作平均5.80倍、最大19.69倍，最小cnn约1.17倍；5.80倍时间对应增加480%，不是增加580%，也不是应用整体慢5.80倍。Nsight在某些CC场景将原本H2D/D2H路径标为D2D Managed，分类标签变化不能当作额外独立传输凭空出现的证据。

GHASH可有更高吞吐，但认证不等于加密，单独GHASH也不能直接替代完整安全通道协议。论文讨论不同crypto选择时，项目应固定所需机密性、完整性和新鲜性目标后比较，不能靠删去保护来声称同等安全加速。

cudaMalloc/cudaMallocHost/cudaFree平均分别约5.67/5.72/10.54倍；Managed分配约5.43、Managed free约3.35倍。文中另把CC-UVM与nonCC-nonUVM比较得1.01/18.20倍，是不同分母，不与前述倍率混用。

项目可研究合法对象持久驻留、减少重复拷贝/映射和在途复用，但缓存授权必须绑定Client、真实页、权限和epoch；持久缓存不允许在撤销后继续使用旧映射，也不能用复用收益证明无需清理或TLB失效。

## 6. 启动、排队与执行的差别

作者报告平均KLO1.42倍、LQT1.43倍、KQT2.32倍；dwt2d KLO最高约5.31倍。简化栈从约37到52层、含dma_direct_alloc/set_memory_decrypted/tdx_hypercall，是路径证据而非每层耗时的定量归因。

2mm等基线KQT极小、launch数又少，归一化后容易被放大；少数应用LQT反而下降或波动。应同时给绝对耗时、事件数及端到端占比，不能把一个很大的排队倍率直接排序为最值得优化的项目热点。

非UVM KET平均仅增加约0.48%。长kernel可覆盖额外launch成本；streamcluster/3dconv等大量短kernel则被KLO+LQT主导。KLR=KET/(KLO+LQT)帮助理解谁遮蔽谁，但不是安全隔离强度或设备访问权限指标。

Figure10为清晰排除最长事件，Figure11的launch CDF去掉最慢5个点但均值仍用全体；其X轴省略具体刻度。不能从截尾可视化推导尾延迟已消除，或读取图上并不存在的精确百分位数。

## 7. UVM结果与独立数据复算

固定artifact中`fig10/fig10.py`实际绘制论文Figure9的KET比值，目录/README图号有历史错位，且写死作者本机绝对路径。按内容和CSV列匹配，不能仅凭文件夹号就宣称复现了对应论文图。

自写脚本解析28行`sum-kern_sum_nog.csv`，以nor-nor为分母，几何平均cc-nor=1.004811、nor-uvm=5.295894、cc-uvm=188.877876；最大CC-UVM比值164030.65533，最小1.078058，与正文舍入值一致。

关键分母：188.88倍包含启用UVM本身及CC迁移的组合影响。逐case计算CC-UVM/nonCC-UVM的几何平均约35.664964倍；不能把188.88写成“在同样UVM配置上开启CC的纯增量”。这是处理数据复算，不是重跑GPU实验。

聚合采用几何平均，不能用最坏164030倍代表全部负载，也不能把这些kernel事件倍率直接当端到端倍率。CSV为已处理数据，本轮未重新解析全部原始Nsight报告或核验应用输入、正确性和每次计时来源。

对Arm统一物理内存/映射合成方案，CUDA Managed分页与离散GPU跨PCIe迁移并不自动存在。可迁移问题是fault服务、页授权、驻留与同步成本是否进入执行关键路径；不能把H100的188.88倍数字套用到本项目。

## 8. Fusion与Overlap的收益及限制

作者用PTX nanosleep微基准控制KET与循环展开，分别研究launch次数、首次新kernel启动和64 streams下512MB/1GB传输。它用于解释机制，没有真实计算依赖，不能证明任意神经网络或图形任务都有同等重叠空间。

减少launch能降低累计KLO/LQT，但首次启动与代码体积等开销会变，完全融合不一定最好。cudaGraph还需权衡建图/实例化成本；文中将CC下最佳fusion程度留为后续问题，不宣称已交付自动全局最优融合器。

提高compute-to-IO ratio、增加streams可覆盖更多搬运/加密，但CC和短kernel更难重叠。这里的“提高KET”是改变工作量组合以研究比率，不代表无端延长GPU工作就会提高应用效率；应比较完成相同有效任务的总时间。

项目可研究有界批量提交和复用private plan，仍须保存每任务完成/错误、内存依赖和公平性。不能为减少RPC或IRQ把多个Client授权合并成一个身份，或以batch到时替代native fence真实完成。

## 9. CNN与LLM：避免错误比较

CNN使用CIFAR100、六模型、200epochs，batch64时CC throughput平均下降24%、训练时间增加31%；这两个平均分别聚合，不能严格互取倒数。1/0.76约1.3158只说明量级相容，不是重新构造每模型训练时间。

batch1024降低开销；小batch AMP可因cast等额外工作变差，大batch AMP/FP16可改善。原文部分收益相对nonCC AMP、部分图中time相对nonCC FP32，必须逐项指明基线。未报告完整accuracy/收敛等价审计，不把量化速度提升当相同数值语义下的透明系统优化。

LLM为Llama3-8B、HF/vLLM、BF16与AWQ4bit，三次运行中位数。Figure14全部相对同batch/input length的HF非量化CC-off；热图5–8倍主要是backend/量化组合比较，不是CC本身让模型快5–8倍，也不是多VM共享GPU收益。

对256行处理TSV及绘图脚本核对，实际绘制`real`字段，并按HF nonquant/off做归一化；backend vLLM pivot默认均值、baseline pivot中位数。本表每配置是处理后的代表行，本轮未核验三次原始日志如何生成这些行或`real`的完整端到端定义。

独立例子：BF16 batch1/input128，vLLM nonCC/HF为5.8513、CC/HF为5.1886，同backend CC/nonCC约0.88674，即吞吐下降11.33%；AWQ相同配置约下降14.48%。直接用5.1886判断“CC开销很小”会混入backend效应。

BF16 batch8/input128，CC/nonCC约1.04886，确有约4.89%提高的样本；batch128/input1024则约0.98784、下降1.22%。这些处理数据没有提供足够方差和消融来证明正向样本由CC机制导致；论文“通常下降”与局部例外应同时保留。

量化和backend选择改变执行计划、通信量及可能的输出质量；项目若扩展LLM实验，除吞吐还需区分TTFT、逐token延迟、模型加载、冷启动和共享公平性。GPU任务隔离不能直接当应用结果正确、模型保密或端到端LLM服务全栈安全证明。

## 10. Artifact与证据局限

8个blob的Git身份已核，但只静态读了与本报告相关的README、图表处理及数据。fig7按位置对齐两CSV并移除首行，若数据顺序变化须先按App验证；这是再现性检查点，不是已证实作者结果错误。本轮未取得该两CSV作全面重建。

root README/附录说生成Figure3–13，而作者PDF实际有14图，部分脚本路径与内容另有错位；fig14 README还引用nonquant文件名，树中为noquant。不能把逐条原样执行说明等同于现成无修改可运行，更不能宣称全部图表已独立复现。

论文明确只做性能评估、不发现新安全漏洞；没有多Client恶意抢占、共享队列越权、中断伪造、重放、撤销/reset隔离等攻击实验。性能观测不能作为这些安全目标已被证明的证据。

## 11. 对项目两个部分的具体价值

第一部分建议建立相同负载/保护口径的关键路径分解：直通与共享分别比较，区分冷启动和稳态、单Client与多Client，记录真实GPU工作量、API/RPC次数与CPU占用。优先减少重复准入/搬运/唤醒及不必要等待，收益用端到端同条件测量确认。

第二部分保留RMM身份、实际页授权、受保护Stage-1、private plan/native fence/cookie/epoch和可信通知；优化不能把“接纳成功”“launch返回”“IRQ到达”升级成任务成功，也不能把执行终态升级成DMA静默或对象安全复用。

发布批处理可以减少开销，也可能改变Client可见时序；真实性/防重放与时序隐私须分别论证。本文没有证明固定通知窗口隐藏全部Host观察面，亦没有给共享GPU故障域隔离方案，应与Heckler/WeSee/可信I/O及生命周期研究交叉比较。

下一篇已取得ISCA2026 LÆGIS作者17页全文，DOI 10.1109/ISCA66397.2026.00046，SHA256：3918a617a33bc0576ec7e33f6208f296a405dd03236b9be6c46ba7e6ce453021；只完成摘要和身份初核，尚未精读，不计完成。其作者为Yang Yang、Adwait Jog，不与本篇三作者和实验结果混并。

统一记录：改动目的为GPU CC关键路径与再现性精读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无作者工作负载/模型/攻击/构建/硬件run-id或测试退出码｜静态阅读与自写算术复算保留，来源和发布回读单独核验，整体调研继续。
