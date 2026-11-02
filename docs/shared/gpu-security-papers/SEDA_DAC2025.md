# SeDA：DNN安全内存的带宽优化、聚合认证与加密构造审视

研读日期：2026-10-27。完整阅读7页作者预印本及全部22条参考文献，核对DAC正式书目，并固定公开实现进行定向静态阅读。以下分别标明作者主张、公开实现证据及独立分析；未运行加密样例、攻击、RTL、SCALE-Sim、Ramulator或硬件。未改运行代码，无新增性能测量。

## 1. 准确书目与版本

- 题名：SeDA: Secure and Efficient DNN Accelerators with Hardware/Software Synergy。
- 作者：Wei Xuan、Zhongrui Wang、Lang Feng、Ning Lin、Zihao Xuan、Rongliang Fu、Tsung-Yi Ho、Yuzhong Jiao、Luhong Liang。
- DAC 2025，会议录1–7页；DOI 10.1109/DAC63849.2025.11133180。正式书目信息由Crossref核对，不能把它标成CCA或GPU TEE实现。
- [正式DOI](https://doi.org/10.1109/DAC63849.2025.11133180)；[作者预印本v1](https://arxiv.org/abs/2508.18924v1)；[所读全文](https://arxiv.org/pdf/2508.18924v1)；[论文指定源码](https://github.com/wayne4s/seda)。

所读PDF为2025-08-26的arXiv v1，7页、526364字节，SHA256 a33e8f5bfac937c8166e1aebd9e2ae27f8c3f6a9d5923d4e3cf83bd0cbf7e9e1，严格解析确认完整页数与trailer。没有声称取得IEEE最终排版版；预印本、源码README及正式题名/作者/会议对应。网页下载有一次尾部未收齐，但arXiv API条目和完整PDF已取得，不能混淆这两种状态。

Crossref相似题名还返回2026年TCAD条目Towards Secure and Efficient DNN Accelerators via Hardware-Software Co-Design，DOI 10.1109/TCAD.2026.3699292。仅取得元数据，未取得全文或确认正式扩展关系，不在本报告中替代DAC版本，也不另计完成。

证据位于build/cca-gpu-followup-20261027，包含seda-main-batch25.pdf、分页文本、Crossref/arXiv响应、固定源码tree和定向文件。GitHub API返回403后改用公开git传输取得固定对象，没有把403响应当作仓库元数据。

## 2. 问题与贡献定位

NPU片外内存不可信，安全机制需要加密、MAC、版本号和完整性树。安全元数据访问占用DRAM带宽；为适配高带宽而并联多个AES引擎又增加面积/功耗。DNN访问存在可预测的layer/tile模式，通用cacheline保护未必具有最佳粒度。

SeDA提出两类优化：硬件上用单个AES输出结合keyExpansion派生值扩展多个128位掩码；软件上选取适合层内重叠与层间tiling的optBlk，并将认证从block聚合到layer甚至model，减少片外MAC访问。

它属于设备内存密码保护机制，不包含恶意Host下的多Client身份认证、GPUVM授权、SMMU所有权或任务完成协议。其低开销数字必须同时审查加密强度、认证延迟和公开原型完整性，不能独立作为完整TEE安全性的证据。

## 3. 威胁模型与可信边界

假定加速器内部状态不可被直接观察/修改，片外内存、外部设备及通信总线不可信，攻击者可通过物理或软件方式读取和篡改。内部密钥、版本状态、加解密/认证逻辑及可信检查结果必须受到保护。

功耗、电磁等物理侧信道和对抗机器学习输入攻击不在范围。论文没有给出远程证明、密钥供应、多租户密钥隔离、服务重启、模型/输入授权、固件完整性或设备重新分配的完整协议；“只有持钥者可解密”也不足以描述这些管理责任。

攻击者能否得到已知/选择明文影响具体保密性分析，论文没有额外排除这类标准密码威胁。DNN数据中常见零值不能被当作密码设计可忽略的特性。访问模式和模型架构的全部隐私也不由片外数据加密自动保证。

## 4. 作者的带宽扩展加密设计

基础CTR使用PA与VN作为唯一输入，在同一密钥下每次写入增加VN，生成128位S。传统做法为每个128位子块分别调用AES；对64B块可需要四路并行AES，或单引擎分时执行。

SeDA Algorithm1先生成一个共享S，再把它分别异或AES keyExpansion产生的128位key_i，形成各子块掩码S_i。作者据“各掩码不同”主张阻断共享OTP下的SECA频率攻击，并减少多AES引擎开销。

正文首先说明一个主密钥的keyExpansion派生值足以用于整个模型；带宽仍不足时又提出用key XOR (PA拼接VN)作为keyExpansion输入。两种变体的派生值是否随块变化不同，必须分别分析，不能把后者的可能性质追溯赋予前一种构造。

## 5. 对固定派生掩码构造的独立分析

针对正文首先描述的固定主密钥、重复使用keyExpansion派生值的构造，设b为大块编号、i/j为其中两个128位子块，R_i/R_j为固定派生值，则C_b,i = P_b,i XOR S_b XOR R_i。异或同块的两个密文后，S_b完全抵消，得到C_b,i XOR C_b,j = P_b,i XOR P_b,j XOR R_i XOR R_j。

若一个参考块的这两段明文已知，就能从该参考块求得D_i,j = R_i XOR R_j；之后任意使用相同派生值的目标块都泄漏P_b,i XOR P_b,j = C_b,i XOR C_b,j XOR D_i,j。即使每个S_b由唯一PA/VN生成、从未重复，这个泄漏依然存在。它破坏标准语义保密性的要求；不同OTP标签或单独的SECA实验不能消除该代数关系。

这是根据论文公式得到的有条件数学反例，不是已运行的密钥恢复攻击，也不意味着无需条件即可恢复全部模型明文。得到两个子块的异或关系与取得AES主密钥是不同结论；本文不混称。

该推导直接适用于跨块固定R_i的版本；对把PA/VN混入keyExpansion输入的变体，固定D_i,j的步骤不直接成立，但它也不是标准CTR构造。key schedule并不自动是独立可用的伪随机扩展器，相关输入、派生值独立性、域分离及安全归约仍需单独证明。没有证据支持将这两种方案直接标记为与标准AES-CTR等强。

因此，对项目不建议迁移这一加密优化。若未来需要密码保护，应先保持经过分析的标准构造及唯一nonce/计数器域，再比较流水、预计算和批处理带来的性能；研究目标不能预设“一个AES输出加若干XOR即可安全扩展任意带宽”。

## 6. optBlk与多级聚合认证

小block增加MAC数量，大block可能重复覆盖层内重叠tile，并在下一层使用不同tiling时浪费认证计算。SeDA借鉴SecureLoop搜索策略选择optBlk，以降低这两类不匹配；其最优性依赖所搜索的模型、硬件和调度空间，不代表所有DNN/GPU访问的全局最优。

认证以keyed hash为基础，将数据块与PA、VN、layerid、fmapidx、blkidx绑定。作者指出只对内容取MAC再无序XOR可能允许重排列，加入位置和版本使不同位置的内容不能直接互换。论文Algorithm2写HASH_Kh，但没有充分给出实际选用的完整MAC构造、截断位数、域编码及安全证明细节。

optBlk MAC可存片外；layer MAC通过XOR聚合该层各optBlk MAC，可减少到可放片上SRAM的数量；model MAC聚合模型weights，检查结果在推理结束才可得。model weights认证与全部动态activation、输入、输出及执行控制流认证不是同一覆盖范围。

XOR-MAC有可证明安全的具体构造，但“引用XOR-MAC论文”不意味着任意XOR归约都满足同一证明。必须确认每个认证项身份唯一、编码无歧义、版本新鲜、项集合/数量受约束，以及重复tile怎样计数。相同项重复两次会抵消这一代数事实说明这些条件需要明确；本报告没有据此宣称已构造针对SeDA完整实现的伪造攻击。

## 7. 延迟认证和结果发布

layer/model级认证结果晚于部分计算产生。若允许未验证数据继续参与后续计算，需要在可信边界内限制所有可观察副作用：输出写入不可信内存、返回成功、持久状态修改及后续任务消费，不能先于所依赖数据的验证成功。

论文解释了何时得到聚合检查结果，但没有完整展开GPU式任意kernel的推测副作用、失败回滚、跨任务污染及异步完成发布。减少片外元数据访问与保证“验证前结果不被使用”是不同责任，不能用接近零流量证明后者。

这与TensorTEE、PipeLLM及安全多GPU元数据中的验证屏障问题相邻。对于项目，真实native fence只证明对应执行路径达到其完成条件；若另引入密码认证，成功终态还必须等待认证结果，不能让IRQ、fence已触发或普通ACK代替检查。

## 8. 模拟配置和实验范围

作者使用SCALE-Sim2获取计算与DRAM trace，再由security simulator加入安全访存，最后交给Ramulator2。Server模型为256×256 systolic阵列、1GHz、24MB SRAM、20GB/s、4通道；Edge为32×32、2.75GHz、480KB SRAM、10GB/s、4通道；数据精度为每元素1字节。

Google TPU v1和Samsung Exynos 990在此是模拟配置标签，不是实物测得保密运行。28nm的AES面积/功耗分析同样是作者模拟，不是已经完成芯片流片或板端测量。

13项工作负载含LeNet、AlexNet、MobileNet、ResNet18、GoogLeNet、DLRM、AlphaGoZero、DeepSpeech2、FasterRCNN、NCF、Sentimental_seqCNN、Transformer_fwd与YOLO_tiny。Transformer条目不能直接称为端到端LLM token生成、KV cache或多租户GPU机密推理实验。

安全对照是无保护baseline及SGX-64B/512B、MGX-64B/512B、SeDA。SGX为加速器安全内存模型，而非实际Intel SGX处理器执行同一NPU任务；其设16GB protected memory、56位VN、64位MAC、16KB VN cache与8KB MAC cache。主比较为公平把SeDA layer MAC存片外，不能将片上MAC优化和该主实验混成完全相同设置。

## 9. 定量结果和解释边界

| 作者报告 | 正确口径 |
| --- | --- |
| SGX-64B访存增量 | Server 30%、Edge 28.29%，相对无保护系统 |
| MGX-64B访存增量 | Server 12.51%、Edge 12.63% |
| SeDA访存增量 | Server 0.12%、Edge 0.03%；是安全额外流量，不是总访存接近零 |
| Server性能 | SGX-64B、MGX-64B、SGX-512B、MGX-512B分别慢22.04%、10.93%、8.49%、4.28%；SeDA低于1% |
| Edge性能 | 四个对照分别慢21.10%、10.95%、5.84%、2.90%；SeDA下降很小，正文未给同样精确均值 |
| 摘要/贡献口径 | 开销降低12.26%/12.29%，未充分明确与正文四组对照的统一换算，不自行解释为端到端加速比或百分点 |
| 面积与功耗 | 图4随带宽需求增加的趋势；缺可离线核对完整逐点表，不从图概述补造精确数字 |

正文SGX-512B“cuts traffic by 7.83%/5.13%”、MGX-512B“reductions of 3.59%/2.39%”的比较分母不充分清楚，图中又以无保护baseline归一；不能直接用这些句子宣布安全保护比无保护减少相同比例的总流量。

论文没有同时提供标准密码强度比较、恶意设备/Host安全实验及多Client回收压力。性能估算成立也不能证明第5节构造的保密性；本轮没有重新生成trace或复算作者全部均值。

## 10. 固定公开实现及实际读取范围

固定仓库提交4d2a071ac02f8ce7319f90566751b42b4fad5534；[固定快照](https://github.com/wayne4s/seda/tree/4d2a071ac02f8ce7319f90566751b42b4fad5534)。本轮用git对象取得完整371文件tree，没有截断；仓库包含SCALE-Sim与Ramulator副本、AES/SHA256示例和secureSim目录。

完整阅读README、两个NPU配置、`run_batch.sh`、`secureSim/merkle_tree.py`、Python CTR/tensor封装与AES-CTR-HMAC文件封装、库CTR样例、Verilog AESEngine及其testbench、SHA256库样例；对全部tree做关键符号查找。AES底层各库、SHA256全部RTL、SCALE-Sim/Ramulator全部内部和所有模型没有全面审计。

两个配置分别与24MB/480KB SRAM、256×256/32×32阵列及20/10 bandwidth字段对应。README称`run_batch.py`，实际提供`run_batch.sh`；脚本引用`topologies/conv_nets/lenet.csv`，固定tree没有该文件。这里是静态依赖缺口，没有执行脚本并伪造运行失败。

secureSim只列`merkle_tree.py`，其内容生成VN/树节点地址与遍历列表，没有实际keyed MAC校验、layer/model聚合认证或完整比较驱动。关键名称未检出不能单独证明功能绝对不存在，但结合完整tree与所读路径，尚不足以确认论文从trace到五个安全方案/图表的完整公开流水线。

所读Verilog顶层只有单个128位AES data_out，Python CTR每16B生成独立counter输入；没有在这些路径确认论文S XOR round-key的多路输出机制。普通AES round key参与AES内部round，不等于实现论文外部OTP扩展。故第5节反例针对正文描述，不冒称已攻击公开RTL里确认存在的B-AES模块。

tensor演示将随机生成的key/nonce覆盖为固定数组并打印；HMAC文件示例固定salt与nonce，每次counter归零，同密码重用会复用密钥流。HMAC验证使用Python assert，优化模式可能移除；这是示例代码在其具体条件下的使用风险，不推定真实设备密钥供应也完全相同。SHA256的Hello World样例是无密钥hash，不是完整消息认证协议。

AES testbench主要输出信号，没有看到自动与已知标准向量比对的assert；提供testbench或能加解密往返不等于密码安全验收。未执行上述样例或修改作者代码。

## 11. 与项目主线的关系

PORTAL、CAGE、ACAI处理可信管理、设备访问与身份/归属，PhantomMap检查实际页及映射生命周期；SeDA研究片外数据密码保护，处于另一保护层。数据即使经过加密，也不能让错误Client引用他人对象或让旧映射继续存活，因此不能替代现有建图授权。

项目既定假设保持：RMM认证原始Client，可信ProxyRealm统一控制SMMU；建立映射时检查对象、实际页、权限及生命周期，软件IPA→HPA合成为受保护直接HPA Stage-1；其他设备继续硬件Stage-2。没有因为SeDA为NPU硬件设计而否定GPU模拟验证假设，也不要求实验Mali增加该加密引擎。

已有认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127继续作为基础。SeDA最相关的增量问题是聚合检查何时完成、完成记录怎样绑定当前任务和对象版本，以及验证失败后如何阻断成功发布与安全回收。

## 12. 独立评价和后续研究

跨层tiling、认证粒度与元数据流量协同是有价值的性能方向；但不能直接接受“不同掩码所以等强”的安全推理，固定派生值版本已有明确的代数泄漏，PA/VN混入keyExpansion的变体仍缺安全论证。公开primitive示例与论文端到端机制应分开评价。

项目可以借鉴认证记录的粒度选择与一次验证多个明确对象的思想，但应以完整身份集合、版本和终态作前提。批量验证/批量完成只能减少开销，不能丢掉每Client/每任务的归属、错误传播、对象代次与去重责任。

可继续验证的方向包括：验证完成前结果是否对外可见；聚合记录是否绑定精确任务/模型/输入实例与计数；相同PA跨Client复用是否改变密钥/版本域；重复/缺失块是否被检测；reset后旧认证结果是否失效；失败是否会被fence/IRQ快路径提前发布为成功。本轮未执行这些测试。

统一记录：SeDA完整7页预印本、正式书目、固定371文件tree与定向源码研读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜文献/代码获取证据及代数推导保留，无GPU/VM/RTL/密码攻击run-id或新增PASS｜保留密码构造疑点、公开流水线缺口及作者模拟结果边界，持续研究。
