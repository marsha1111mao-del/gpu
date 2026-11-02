# GPU-Fuzz：DL算子参数边界测试、GPU内存错误与项目隔离验证

## 1. 论文身份、版本与定位

《GPU-Fuzz: Finding Memory Errors in Deep Learning Frameworks》，Zihao Li、Hongyi Lu、Yanan Guo、Zhenkai Zhang、Shuai Wang、Fengwei Zhang；前两位共同一作，Fengwei Zhang 通讯。作者PDF标注 DAC2026、July26–29、Long Beach、7页及 DOI 10.1145/3770743.3804266；作者主页列相同题名/六作者/DAC2026，但月份写 June、且保留 To Appear。Crossref精确DOI本轮404、ACM403，未独立确认正式出版日期、页码或出版方版本，不能将PDF自带书目当已核正式元数据。

它是 GPU / AI 安全测试工作，不是 CCA 或 TEE 架构。对本项目的直接价值在于：从合法高层算子参数中产生真实低层内存错误，再检验恶意/故障Client的访问是否被可信映射、任务生命周期和恢复机制限制。发现同进程算子越界不等于证明跨Client隔离失效，测试通过也不等于完整安全证明。

## 2. 原文、证据与研读范围

[作者出版页](https://fengweiz.github.io/publications.html)、[作者7页PDF](https://fengweiz.github.io/paper/gpufuzz-dac26.pdf)、[论文标注的DOI入口](https://doi.org/10.1145/3770743.3804266)。取得PDF 1013501字节，SHA256 `e06d159d5544a009b4b81866dc048924d505a7fcd60d12c7ddd5adf62e9274b0`；全文§1–9、致谢、26条引用、9图4表均完整阅读，7页全部视觉核对。没有附录或artifact完整说明可补充。

限定GitHub仓库搜索GPU-Fuzz / 精确名称，共返回25/24条索引；没有已确认作者链接。候选 mashnoor/gpu-fuzz 的元数据和head取得、README404，未确认其与论文的关系，不能称作者artifact。未把NVlabs/cuFuzz或同名个人仓库替代本论文实现，未下载运行作者测试、Z3、framework、CUDA或攻击。

为核查案例说明，额外取得PyTorch上游v2.3.1的三个文件并核Git blob SHA1/SHA256：`NaiveConvolutionTranspose2d.cu`、im2col.cuh、KernelUtils.h；tag解析到commit `63d5e9221bedd1546b7d364b5ce4171547db12a9`。完整读im2col与KernelUtils，定向读transpose前向分派；这是上游代码的有限静态核查，不是GPU-Fuzz源码审计或论文二进制复现。

## 3. 目标问题：从算子参数到设备错误

传统模型/图级fuzzing偏重编译器转换与数值差异；GPU-Fuzz将形状、stride、padding、dilation、groups等作为测试对象。即使API语义允许，设备kernel的索引类型、grid计算或边界检查仍可能出错。论文同时介绍global代码篡改与local返回地址攻击作为动机；这些是引用既有工作，不是本轮13个问题均已完成ROP、代码注入或机密数据窃取的证据。

“GPU不支持W⊕X”的背景概括不能直接泛化到本项目Arm GPU、不同厂商或所有未来硬件。项目应按实际Stage-1权限、固件、代码页映射与可信加载策略论证；本研究接受模拟载体，但模拟需要明确实现了哪些访问语义。

## 4. 三阶段设计

第一阶段人工建模：按算子族创建统一抽象和符号变量，从文档提取参数/输出形状/整除等约束。作者称两人约一个月独立提取后交叉检查，13个operator、45条约束；每族后续约100–150LOC。人工专业检查有助质量，但不是形式化证明文档与全部实现一致。

第二阶段用Z3求满足约束的参数；迭代随机挑一个维度，累计排除当前值及其hash结果，生成新模型。第三阶段将模型转为PyTorch、TensorFlow、PaddlePaddle API调用，通过compute-sanitizer观察内存错误并归档日志；实现总计2628行Python。跨framework在这里主要是参数实体化与执行，正文未声称已经实现完整数值差分oracle。

Table1实际列7个大类：Convolution、Pooling、Padding、Unary、Binary、Matrix、Concat；其中列出大量1d/2d/3d变体及省略号。正文“13 operators”不能简单当恰好13个API或完整列出的API覆盖数，需artifact的精确模型清单才能消除口径歧义。

## 5. 约束语义的审查

图4/5卷积输出公式没有显式floor；若编码为非负整数Z3除法，可以表达常见floor语义；若编码为实数等式或交叉相乘，则可能排除合法输入。例如Hin=8、K=3、S=2、P=0、D=1，通常输出为3，而实数表达式是3.5。代码未取得，不能判定实际Z3 sort或声称已确认建模错误。

图中Hin>K、P>0、P<Hin等条件仅覆盖某些参数子集；普通卷积可以K=Hin，也允许P=0。图7本身还使用padding=0。应区分“选择用于搜索的限制”和“完整API必要条件”，并分别安排语义有效测试与非法输入鲁棒性测试。

## 6. 搜索策略、hash和覆盖边界

对单维累计x≠a会连带排除所有x=a的组合：从(0,0)加x≠0后，(0,1)也被排除。因此它是探索启发式，不能称穷尽所有不同元组。有限参数域终会UNSAT，正文未完整说明重启、约束回收、seed或超时调度；无artifact不能补写实现。

hash混合的“不同hash避免相似区域”需要额外论证：hash距离不等于语义距离。若固定宽度上的右移XOR与奇数乘法构成双射，则h(x)≠h(a)与x≠a等价，不增加排除范围；若hash非单射，则会排除碰撞的其他值，可能降低覆盖。正文没有给出全部常数/位宽/独立消融，本轮只给条件分析，不声称实际hash必然无效或求解更慢。

## 7. 测试环境与oracle

Table2：双Intel Xeon Silver4510、H100 PCIe、Ubuntu24.04.2、driver580.82.07、CUDA runtime12.8.93、Python3.11.13；PyTorch2.3.1+cu121 / cuDNN8.9.2.26、TensorFlow2.20 / cuDNN9.13.0.50、Paddle2.6.1。各framework独立Conda，硬件/OS/driver相同。系统CUDA与wheel绑定CUDA不能混为一个版本；缺少完整镜像、构建配置与dispatch证据，不能保证当前安装复制出同一执行路径。

作者主oracle为compute-sanitizer；§6明确不覆盖静默数值错误和性能回归，CPU参考差分是未来方向。当前NVIDIA文档获取超时，本轮没有核完整工具版本行为。sanitizer能检测给定执行中的错误，不等于生产设备会在副作用前阻断，也不替代Arm设备的硬件授权边界；对未初始化、竞态、对象内跨张量或未插桩路径的覆盖须另核。

## 8. 13个发现的完整分类

| ID | Framework / 算子 | 作者表中问题 | 失败模式 / 状态 |
| --- | --- | --- | --- |
| 1 | PyTorch conv_transpose2d | OOB global write / grid计算 | GPU异常，Confirmed |
| 2 | PyTorch bmm_sparse | misaligned global write / CUSPARSE指针 | 静默内存破坏，Reported |
| 3 | PyTorch adaptive_avg_pool2d | OOB global write / 边界 | 静默内存破坏，Confirmed |
| 4 | PyTorch replication_pad2d | OOB global write / grid | 静默内存破坏，Confirmed |
| 5 | PyTorch adaptive_max_pool2d | OOB global write / 边界 | 静默内存破坏，Confirmed |
| 6 | PyTorch conv_transpose3d | OOB shared read / 索引 | 静默内存破坏，Fixed |
| 7 | PyTorch reflection_pad1d | invalid launch / torch.compile symint溢出 | GPU异常，Confirmed |
| 8 | TensorFlow Conv2D | OOB global read / 索引 | silent read / downstream crash，Confirmed |
| 9 | TensorFlow Conv2D | launch整数溢出 | CPU assert，Confirmed |
| 10 | Paddle conv2d_transpose | 维度溢出 / precondition | CPU assert，Confirmed |
| 11 | Paddle conv3d_transpose | cuDNN非法参数 / illegal instruction | GPU异常，Confirmed |
| 12 | Paddle conv2d_transpose | cuDNN参数组合 | GPU异常，Confirmed |
| 13 | Paddle conv2d_transpose | grid/block计算 | GPU异常，Confirmed |

按Table3共7项内存访问违规，5项标静默内存破坏、5项GPU异常、2项CPU assert、1项silent read/downstream crash；状态11 Confirmed、1 Fixed、1 Reported。表中OOB shared read也归入静默破坏是作者分类，不应改写为已证实写坏global数据。结论“most ... silent memory errors”比表内5/13更宽泛，报告保留准确分母。

Responsible Disclosure称均提交官方issue，但全文没有给出13个issue链接或全部修复commit；本轮没有独立核维护者状态。作者的Confirmed/Fixed不是本轮重新确认，更不是获得13个CVE。错误类型、可利用性、跨Client后果和补丁状态应独立记录。

## 9. 与NNSmith比较：数量与分母

两工具各五次独立四小时PyTorch测试。Table4为均值±标准差：NNSmith19063±360 cases、296±19 findings，293±19 inconsistencies和3±1 exceptions；GPU-Fuzz51860±1559 cases、106±8 findings，其中26±5 memory errors、80±7 configuration errors，排除OOM。

复算case数量为2.72045倍，平均约1.32382与3.60139 cases/s；每工具总20 GPU-hours，两工具共40。GPU-Fuzz内存错误占其finding约24.53%，配置约75.47%。不能把26±5解释为26个独立新漏洞，或将106与Table3的13相加；正文没有充分交代去重、unique root cause与重复trigger口径。

NNSmith的总finding更多但目标不同，不能仅用总数宣称谁安全性更高。表中memory=0仅限作者给定配置/时长；论文未完整披露两者是否同等包裹sanitizer、相同有效算子集与tensor预算、所有seed及原始运行记录。均值标准差不是置信区间，不能由这些聚合数推出统计显著性或所有GPU平台同等加速。

## 10. ConvTranspose2d案例的尺寸与因果审查

图8输入(C,H,W)=(10,40000,2)，输出通道2，kernel1×1、stride200、默认padding/output_padding=0、dilation1。按标准转置卷积公式，输出为(2,7999801,201)，共3215920002元素；float32仅输出约12863680008B，即11.98024GiB，另有临时buffer。它超过有符号32位上界，但不能把这一例直接放进项目128MiB池而把OOM当访问隔离失败。

论文示意代码将n_elements_64强转int，并将“undersized grid”解释为导致64位索引越界。但不足grid单独通常解释漏算，不能单独推出超出已分配buffer；图9还称越界地址位于最近allocation之前。需要实际索引类型、溢出位置、分配大小和kernel分派共同解释，不能只复述示意图就认为根因已完整确认。

上游v2.3.1所读slow transpose路径的输出尺寸和col2im num_kernels为int64_t；GET_BLOCKS接收int64_t、检查block数后返回int，并未出现图8那段明确的主机端元素总数int截断。但CUDA_KERNEL_LOOP展开为int64_t隐藏计数器加int可见index，随后传给int64_t参数的col2im_device，故可见index的窄化是另一条需核路径。

条件算术：若执行该512线程slow路径，所需block数6281094；图9 block4194446的首线程线性index为2147556352，已超过INT_MAX，按常见32位补码窄化为−2147410944。该条件与“allocation之前”方向一致，提示设备循环index是比简化主机截断更具体的核查点。没有执行CUDA、检查实际二进制或确认cudnn/slow分派，因此它是有源码支撑的条件解释，非已完成根因复现或新增漏洞声明。

图2另给AdaptiveAvgPool输出宽67108607的例子；正文只有示意，不应把两个不同算子、不同bug和两套触发参数混为同一案例。图8/9对Bug1异常与静默错误的表述也有差异，需原始日志才能确定各次运行的最终错误传播。

## 11. 对本项目内存隔离的意义

高层operator“参数合法”不能替代实际HPA授权。即使Client自带framework有bug或恶意kernel，RMM认证原始Client、ProxyRealm对象/页归属/权限/generation授权、受保护直接HPA Stage-1仍应约束其访问。其他设备硬件Stage-2也必须经过可信建图检查；不因工作负载来自知名framework而减弱授权。

跨页保护不能发现同一合法页内所有对象越界。若两个不同Client的敏感对象被放进同一设备可读页，页权限无法分离它们；应避免此类混放或增加独立对象级机制。同Client内张量损坏与跨Client隔离破坏应分别统计，不将sanitizer发现自动等同于CCA边界失效。

生成器需同时约束tensor尺寸、分段BO、alignment、stride索引上界和临时工作区预算，并专门检查host整数宽度与GPU index宽度。资源限制下可构造受控小buffer/索引测试，但修改夹具后必须注明，不能称原13个framework问题在Arm GPU上原样复现。

## 12. 对中断、任务终态与恢复的意义

5项GPU异常、2项CPU assert和静默错误说明“提交成功/没有Python异常/收到了IRQ”都不能表示任务正确。CPU launch前失败应走未启动状态；实际GPU fault应绑定当前队列、原生fence、cookie和epoch；异常或reset后的旧中断不得替新slot完成，也不得释放仍可能被访问的页。

sanitizer日志、GPU fault、native fence错误、完成通知和受害者结果是不同观察面。可信IRQ只提供事件真实性和路由，不能独立证明数学正确、输出已可见或DMA已静默；silent corruption还可能在正常终态下发生。需要应用正确性时加入可信参考或验证协议，不能要求IRQ承担此保证。

出错Client的终止/重置与页面撤销应保留真实任务引用、GPUVM/BO和private plan/snapshot；确认TLB/IOTLB失效及设备静默后才回收。共享GPU整体reset的影响范围和受害者恢复需测量，不将“攻击者被杀掉”直接当其他Client不受影响。

## 13. 建议的项目验证矩阵

建议分为：语义合法参数的算子测试、故意非法参数的接口测试、直接GPU访问边界测试、生命周期/旧通知竞态测试。每例绑定完整输入、seed、源码/镜像版本、Client ID、BO/generation、预期终态和允许副作用；将有意注入的错误kernel与真实framework原漏洞区别记录。

独立判据包括攻击者实际写/读是否越权、受害Client哨兵/结果是否改变、native fence错误是否正确传播、旧epoch IRQ是否被拒绝、任务引用是否保留到静默、退出后资源是否恢复。结果至少区分SETUP_FAIL、OOM、未触发、正确拒绝、同Client错误、跨Client越权、超时与恢复失败，不能用一个rc0覆盖全部状态。

先把受控边界测试放在模拟环境检验协议，再按平台验证真实访存/错误fence/IRQ及reset；模拟不是缺陷，但只观察提交结构不能证明设备副作用已被阻断。本轮仅提出设计和测试计划，没有运行上述工作负载，也不改变现有硬件回归顺序。

## 14. 与主线论文的关系、未完成项

PORTAL / CAGE / ACAI约束可信GPU访问与隔离边界，PhantomMap / DMGuard补充实际页、映射和旧引用生命周期，GPUShield等补充对象边界机制；GPU-Fuzz可作为工作负载产生与负向验证手段。它们的证据不能互相替代：测试工具不是生产TEE，内存错误检测不是可信中断协议，真实任务终态也不是应用数学正确性。

本轮重新检查CUSAFE、Let-Me-In、HSMEM、RS-Infer：CUSAFE作者链接仍为空、USENIX目录超时；Let-Me-In正式元数据确认但IEEE418、另一作者路径404；HSMEM/RS-Infer仅机构列表，无全文。仍保留待办，不计精读完成。尤其HSMEM CPU-GPU安全传输和RS-Infer TrustZone/NPU应在取得全文后独立分析，不用GPU-Fuzz替代原目标。

## 15. 证据与统一记录

证据目录 `build/cca-gpu-followup-20261027/`：`acquisition128*.json`保留请求、错误、字节和哈希；`gpufuzz128-full.txt`、`gpufuzz-render128.json`、`gpufuzz-arithmetic128.json`；`pytorch128-selected-blobs.json`记录上游三个文件的不可变blob。仓库搜索是有限发现，不能证明作者代码不存在；未取得GPU-Fuzz代码、原始五轮记录或13条issue，不声称源码审计/复现。

统一记录：7页全文/全图表/全页视觉/上游三文件有限静态/独立算术/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无framework、模型、作者代码、攻击、CUDA、构建或硬件run-id及运行PASS｜保留研究，完整artifact和项目验证待完成，整体active。
