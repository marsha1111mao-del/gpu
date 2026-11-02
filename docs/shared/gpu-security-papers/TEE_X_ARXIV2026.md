# TEE-X：TrustZone 内完整模型推理、敏感度压缩与 SIMD 状态隔离

研读日期：2026-10-28。完整阅读arXiv2608.22716v1共14页，正文1–9、参考文献10–14共65条，无附录。图按提取标签、图注和正文理解，未逐像素核验。本篇在TEE的CPU上执行压缩后的完整模型，GPU仅为性能基线，不是CCA GPU直通或共享保护架构。未改运行代码，无新增性能测量。

## 1. 文献信息、版本与证据

题名 TEE-X: TEE-aware Acceleration Framework for Large Vision Models at the Edge。作者Kurt M Wilson、Mohaiminul Al Nahian、Abeer Matar A. Almalky、Sadat Shahriyar、Souvik Kundu、Zhishan Guo、Abdullah Al Arafat、Adnan Siraj Rakin；前四位共同贡献，机构包括Binghamton University、North Carolina State University、Florida International University及Intel。

[实际所读版本](https://arxiv.org/abs/2608.22716v1)日期2026-08-24，未确认正式会议/期刊发表。[PDF](https://arxiv.org/pdf/2608.22716v1)751066字节，SHA256 `25578413d00ccd16640653a484d9f77a9b6ba20f9bc63f6b15365b1e11a41c28`；原始取得URL未带版本，PDF首页与元数据核对为v1，另取得固定v1摘要页。

证据位于 `build/cca-gpu-followup-20261027/` 的teex文件、acquisition-batch55及acquisition-followup-batch55记录；阅读范围见 `teex-reading-scope-batch55.json`。没有找到与作者及论文明确对应的公开artifact，本轮没有代码审计、训练、推理或攻击复现。

## 2. 问题、目标和路线

作者希望在有限可信内存及CPU算力下运行Vision Transformer，避免模型分割把部分权重或中间值暴露给不可信Host/GPU。其路线是改变模型表示并压缩计算，在OP-TEE的CPU执行全部推理，而非让GPU参与受保护执行。

两项核心机制是按层敏感度分配低秩计算预算，以及用Arm Neon SIMD优化可信应用中的矩阵乘、残差、bias和LayerNorm。GPU-level latency指特定单batch条件下接近作者测得GPU基线；它不表示Neon具备GPU规模并行，也不是保护GPU共享所需的SMMU或中断机制。

与Portal/CAGE的直接区别是信任边界：它通过让机密计算不去GPU来减少外部可见状态；本项目则在用户给定可信ProxyRealm、平台保护与授权映射假设下，让设备确实执行Client任务。两者适合比较设计选择，不能把该文计为另一套CCA GPU架构。

## 3. 威胁模型与安全主张

论文假设TEE为不可信Host中的安全enclave，GPU也不可信；TEE内模型、数据和计算视为安全，明确排除TEE侧信道。其保密和执行完整性来自既有TEE假设，不是论文另行证明了TrustZone、固件或底层实现不存在漏洞。

把模型从白盒变成较接近黑盒，意味着减少权重、梯度和中间状态的直接可见性；不等于消除对抗样本、查询提取、输入篡改、重放或拒绝服务。论文自己的黑盒对抗攻击ASR仍为60%，不能概括成黑盒攻击均失效。

可信基至少包括OP-TEE、TA的模型加载与解码、算子、内存管理、SIMD上下文支持及模型供应策略。模型文件从82MB缩小到几MB是参数/存储变化，不是可信代码行数或整体TCB相应减少的证明。

## 4. 敏感度分组与预算分配

对层i，作者生成与权重同形状的Gaussian噪声，归一化使扰动范数为原权重Frobenius范数的ε倍，单独替换该层并测准确率。敏感度 `Si = Aw − Awi`，即原模型与该层扰动后的准确率差；敏感层分配更多中间维度。

矩阵 `Wi` 以 `Ai Bi` 形式表示，Ai形状为ni×hi、Bi为hi×no。输入乘法从ni×no投影变为两步ni×hi和hi×no。hi控制近似容量和计算量；当原矩阵rank大于hi时，不能将论文记号中的等号理解为对任意权重均严格无损分解。

理论问题是在总预算下最大化准确率，但作者没有求解全局最优，而采用按module敏感度之和比例分配的规则：每module的总预算再除以其层数。公式2在连续值且分母有效时满足预算和，实际还需整数化、rank上下界及零/负敏感度处理；这些细节在所读文字中未充分展开，不冒充已核对的实现。

按FLOPs估算单层on-par预算为 `hi = ni·no/(ni+no) · Tgpu/TTEE`，总C为各层hi之和。这忽略数据布局、内存流量和非线性等成本；而不同层实际两步计算还乘以各自ni+no，简单rank总和不自动构成严格全模型时延上界。表格中的C=0.2/0.4/0.5又作为计算缩减设置，需区分归一化因子与公式里的总预算含义。

## 5. 学习变换与部署模型

训练联合使用标签cross-entropy、teacher输出的知识蒸馏KL，以及层输出MSE对齐。变换网络T生成低维Ai，同时学习Bi；推理只存生成后的Ai和对应Bi，不需要每次在线运行生成网络。因此优化包含离线训练与部署模型改变，不能归因于TEE切换或SIMD单一因素。

实验K=3，12个Transformer blocks分为3/4/5组，分别训练attn_qkv、attn_proj、mlp_fc1和mlp_fc2的变换；首尾层及LayerNorm不做同类变换。T为两层linear MLP带前后affine，B为单linear；变换网络参数QAT至4bit、首尾8bit。

CIFAR-10训练500 epochs，small/base学习率分别1e−4/5e−5、batch256；ImageNet300 epochs、batch1024、学习率2e−4。λKD分别10/1000、λMSE为1，最重训练可用48GB A6000。这里是作者实验条件，不是本项目运行要求或已进行的模型训练。

“完整模型在TEE内”指部署后的压缩模型，而非原始全精度模型逐运算等价。其安全收益可以覆盖部署模型计算位置，但原始模型效用、部署模型精度与机密边界应分别评价。

## 6. Neon 与可信上下文状态

TA使用128bit Neon寄存器一次处理4个float32，broadcast一个A标量、加载B的连续4项、以vfmaq_f32累加；内层对4个独立accumulator展开，每轮推进16列以降低依赖。残差、bias和LayerNorm也采用向量处理。

论文说明OP-TEE需启用CFG_WITH_VFP，以支持context switch保存/恢复Neon寄存器；首次使用时触发记录，之后切换保存状态。作者将首次事件称为interrupt，本报告不将它等同外部设备IRQ或GPU完成通知；本轮没有核对匹配OP-TEE版本的底层陷阱及全部恢复源码。

这里对项目的直接启发是上下文隔离范围不限于页表和BO：CPU可信服务使用的SIMD寄存器、GPU上下文和固件暂存状态都需有明确归属及切换规则。是否在目标平台形成真实泄漏需要设备状态模型及证据，不能仅凭论文提到VFP就宣称当前工程存在缺陷。

作者承认batch>1时GPU可处理多输入，CPU SIMD的列级并行不足以保持同样差距。故不能将batch1接近GPU扩展为任意batch、模型、频率或GPU代际都on-par。

## 7. 共享内存供应与接口边界

Host把encoded weights及输入放在普通内存，以TEEC_RegisterSharedMemory注册后将指针交给TA；压缩权重最终驻留TA内，连续layers的中间tensor留在secure memory，用到才分配、最后一次读取后释放。输出放入共享内存交给Host，这是论文描述的显式可见出口。

encoded不能自动解释为经过认证加密。所读全文没有展开权重密文格式、密钥供应、远程证明、版本/模型身份绑定、认证解码和回滚防护，因此只能确认作者描述的内存位置与接口，不能据此证明恶意Host看不到加载阶段模型或无法替换权重。也不能在无源码时断言所有encoded数据必然是明文。

共享内存注册只解决可访问性，不赋予内容来源真实性。应明确可信端复制/校验顺序、长度和形状、输入/权重快照、异步修改及TA命令顺序；图5把中间数据留在TEE内，有助于减少输出面，但不能替代边界输入验证。

最终输出允许Host读，意味着论文没有通过这条路径保证输出只给认证远端用户。若未来加入本项目机密模型服务，模型归属、输入来源、结果接收者与请求代际仍需明确定义；把一次指针传递当作授权证明是不充分的。

## 8. 平台、性能和准确率

作者平台Jetson AGX Xavier，8核Armv8.2 CPU、集成Volta GPU，固定CPU2.2GHz、推理进程绑单核，基于NVIDIA默认Linux文件系统加OP-TEE。未给出完整OP-TEE/Linux/编译器和GPU框架版本、GPU时钟、所有timer及测量区间、误差分布，不能由型号补出这些配置。

| DeiT-Small / CIFAR-10 | 模型MB | 准确率% | 总时延ms | 峰值内存MB |
| --- | --- | --- | --- | --- |
| Host GPU原模型 | 82.66 | 97.29 | 1022.35 | 154.78 |
| TEE-X C=0.5 | 3.48 | 96.48 | 1082.67 | 21.91 |
| TEE-X C=0.4 | 2.93 | 96.40 | 1006.74 | 18.14 |
| TEE-X C=0.2 | 1.75 | 94.64 | 957.13 | 10.13 |

相对该GPU基线，总时延分别增加约5.90%、减少1.53%、减少6.38%；准确率分别下降0.81、0.89、2.65个百分点。正文“below1%”宜明确是表中不到1个百分点差，不能把这些配置统称零精度损失或严格时延相同。

表1平均layer时间为82.62、58.24、51.76、48.02ms，标注1.42/1.60/1.72倍来自GPU原模型layer时间与改变后TEE模型的比值，不是单纯启用TEE或Neon的因果收益。总时延与layer时间的剩余差值未细分，不能自行归因全部是通信或安全开销。

ImageNet DeiT-Small原模型79.72%，C=0.66/0.5为76.44%/75.79%，下降3.28/3.93个百分点；模型84.11MB降至4.63/3.81MB。DeiT-Base CIFAR-10在C=0.5/0.4/0.2分别从97.55%降至97.22/97.04/95.57。不能将CIFAR上的不到1个百分点外推为所有数据和压缩等级。

表3将ImageNet模型与pruning及2bit quantization比较，给TEE operation support勾叉，但未以同一完整实现、训练预算和算子配置证明全部同类方法均不可用于TEE。4bit参数与float32 SIMD如何在部署内存和解码中对应，还需artifact，而非由模型文件大小自动推出。

## 9. 对照、消融与算术核对

表2将全部方案应用vectorization：naive full TEE1792.42ms、model partition1463.80ms、operation-aware3127.73ms、TEE-X1082.67ms，对应时延减少约39.60%、26.04%、65.38%。类别行合并引用多套系统，缺少逐系统复现配置；不能把一行代表所有论文的统一实测排名。

表7未优化naive full TEE4.43s，只有vectorization/无modularization为1.80s，只有modularization/无vectorization为1.77s，两者组合1.08s，GPU1.02s。表2约1.79s的naive已经向量化，而表7的4.43s未启用，二者标签相近但条件不同，不能直接当作同基线冲突或混用加速比。

正文称去modularization慢80%、去vectorization慢77%；按表7相对1.08s应分别增加66.67%、63.89%。80/77可能源自绝对0.80/0.77s差值，但本轮不替作者断言成因，只保留算术不一致。组合相对4.43s约4.10倍，属于模型变换与执行优化共同效果。

表8的敏感度分配对uniform预算在C=0.2为94.64%对91.27%、C=0.4为96.40%对93.55%，分别增加3.37与2.85个百分点；它支持所测压缩策略优于该均匀策略，不能证明式1全局最优或所有模型泛化。

## 10. 安全实验的证明范围

表4对DeiT-B列WB/BB对抗攻击ASR99.40%/60.00%，bit-flip100%/0%；本轮没有找到与这些数字对应的完整攻击预算、所有输入条件和逐部署测量说明。不同攻击和访问能力下ASR差异说明信息暴露重要，不能独自验证权重供应、共享内存和TEE完整性。

黑盒模型仍可能有查询攻击和迁移攻击；0%某类bit-flip结果不证明TrustZone物理DRAM、故障注入或Rowhammer全被排除。参考文献包含GPUHammer及GPUBreach，也不意味着作者在该Xavier/OP-TEE系统复现或防住了对应攻击。

本文没有设备任务的中断归属、恶意通知、cancel/reset交错或多Client公平性实验；无法支持“完整模型在TEE内，因此GPU共享中断也可信”的结论。相反，它减少的是GPU参与，不能提供本项目所需GPU任务完成链证据。

## 11. artifact 状态与独立评价

PDF及固定v1摘要页未给出可确认的作者代码链接。GitHub宽泛TEE-X搜索350项、仅返回前30项，多为Teensy/Teeth等无关项目；TEE-aware搜索2项无关，追加TEE-X＋vision及TEE-X＋Wilson均0项。该检索只说明本轮未确认匹配artifact，不保证350项已全部检查或全网没有代码。

没有源码，因此不声称已核验rank分配/量化实现、shared-memory认证、模型测量值或Neon上下文隔离。源码不可得不否定其论文机制，但降低对部署细节和安全主张的确认程度；实验数字均为作者报告，本轮没有测量。

优点是把算力预算、模型近似和可信运行时优化连接起来，明确承认batch限制；局限是改模型与执行环境对照不能隔离安全成本，模型加载安全未展开，黑盒安全评价和完整部署证明存在距离。摘要的首次vectorization措辞未作全部先行工作的历史优先权核对，不复述为已确认首次。

## 12. 对本项目的具体启发

项目维持RMM认证原始Client、可信ProxyRealm管理SMMU、建图期核对对象/实际HPA/权限/生命周期并合成受保护GPU Stage-1，其他设备硬件Stage-2及受保护固件/MMIO假设。本文不要求改回CPU-only，也不能因单板硬件差异否定用户设定的可信设备模型。

可迁移的是离线准备与在线路径分离、减少不必要跨域往返、私有中间状态的最短必要寿命，以及将SIMD/设备上下文纳入切换清理范围。敏感度压缩会改变应用结果，适合独立模型服务实验，不能当作透明GPU虚拟化优化加入通用IOCTL/图形/计算路径。

继续复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch和IRQ127：共享输入只是待核验数据，真实终态、输出可见、接收者归属与静止回收仍要连贯。对模型服务另绑定模型版本、输入和部署配置，不新增与现有RMM身份并行的通用token系统。

后续可比较同一压缩模型在Host CPU、TEE CPU和GPU上的单batch/多batch结果，分开报告模型效用、执行优化和信任边界成本；同时检查输入后改、权重替换、旧模型/结果重放、SIMD切换残留和失败回收。此为未来验证建议，不是本轮已运行结果。

统一记录：14页v1全文/65条参考文献/固定摘要页与有限artifact检索、Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/训练/推理/攻击run-id｜正式发表、匹配源码、模型供应链及安全部署未验证。
