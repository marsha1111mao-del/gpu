# SecureInfer：SGX–GPU 的 LLM 分割、跨域掩码与输出保护边界

研读日期：2026-10-28。完整阅读arXiv2510.19979v1共7页，含27条参考文献，无附录；另读取固定摘要页，并以同版本arXiv HTML明确表I的列归属。图仅按标签、图注与正文理解，未逐像素读取曲线。本篇是不可信GPU上的分割LLM推理研究，不是CCA GPU设备隔离方案。未改运行代码，无新增性能测量。

## 1. 作者、版本和证据

题名 SecureInfer: Heterogeneous TEE-GPU Architecture for Privacy-Critical Tensors for Large Language Model Deployment；作者Tushar Nayan、Ruimin Sun来自Florida International University，Ziqi Zhang来自University of Illinois Urbana-Champaign。[实际版本](https://arxiv.org/abs/2510.19979v1)日期2025-10-22，未确认正式发表venue；致谢提及reviewers不作为已录用证据。

[PDF](https://arxiv.org/pdf/2510.19979v1)319813字节，SHA256 `b3622753913becdb69c8e18a8b55238c3b55dd47e8d0e54eb4710ff1cf008ad2`，严格解析7页；原获取URL不带版本，PDF元数据明确v1。[同版本HTML](https://arxiv.org/html/2510.19979v1)用于表格cell结构核对，不当作另一份独立实验证据。

论文、全文提取和获取记录保存在 `build/cca-gpu-followup-20261027/` 的secureinfer及acquisition-batch55/56文件；阅读范围见 `secureinfer-reading-scope-batch56.json`。完整正文与参考文献已读，未取得匹配官方artifact或原始数据，也没有运行模型、SGX或攻击。

## 2. 研究问题及相关路线

作者希望在边缘部署LLM时保护模型和LoRA知识产权，避免全部放入TEE的成本，同时继续使用不可信GPU。与CNN按前后层切割不同，它强调Transformer敏感信息散布于attention、FFN、LoRA、KV及输出，不宜只按深度选少数层。

系统由SGX enclave保存敏感组件，GPU执行选定工作，CPU处理输入输出，并结合外部权重XOR保护、跨域OTP与输出logits扰动。论文引用TEESlice、SOTER、ShadowNet、Slalom等；这些引用不意味着其形式化安全或验证机制自动被SecureInfer继承。

与Portal/CAGE及用户项目相比，它把GPU视为不可信计算域，需要说明离开enclave的数据仍如何保密；项目则依赖RMM身份、可信ProxyRealm及受保护映射/固件来隔离真实设备任务。软件分割可以作为应用替代路线，但不能补上GPU硬件共享或可信IRQ证据。

## 3. 威胁模型及保证范围

§III明确攻击者拥有user-level设备访问和公开API，可收集最终logits/tokens并重复查询，不可直接攻破TEE；同时用grey-box描述查询引发内部变化。背景讨论了更广泛的本地内存和GPU流量观察，但没有将所有Host内核、hypervisor及设备控制权限完整纳入统一攻击模型。

因此不能把该文直接当作对恶意Host、其他Client或任意恶意设备均安全的证明。应分别列API查询者、本地普通用户、不可信GPU和特权Host能观察/修改什么；“敏感张量在SGX”也不自动保护所有外部中间值、缓存或输出。

资产包括模型权重、适配参数、attention激活和中间embeddings。本文未给出完整远程证明、模型/会话供应、授权输入、版本回滚或输出接收者认证协议。安全目标主要是模型提取抗性；输入机密、结果主动篡改检测和通信新鲜性不能未经论证顺带覆盖。

## 4. 实际划分与描述不一致

| 操作 | 正文及HTML表I给出的执行域 |
| --- | --- |
| Embedding | GPU |
| Q/K/V线性投影 | SGX |
| Attention Multiply | SGX |
| FFN线性运算 | SGX |
| LoRA adapters | SGX |
| SiLU/ReLU、Add/Multiply、Identity | GPU |
| Input/Output | CPU |

PDF普通提取把checkmark贴近文字，无法据此判断列；本轮读取同版本HTML的SGX/GPU/CPU三个cell，才建立该表，不按抽象预期猜测。

摘要称non-linear layers等留在SGX，其他线性矩阵乘加密后送GPU；但§IV与表I把SiLU/ReLU放GPU，将QKV和FFN矩阵乘留SGX。两种说法对应不同泄漏和成本，不能任意挑选有利版本拼成完整协议。本报告以具体设计段和表I为主要描述，同时保留冲突。

作者称划分是information-theoretic及threat-informed，但正文没有可计算的泄漏函数、MI测量、优化问题或安全归约；可确认的是按组件风险和成本的设计动机，不能将该形容词当作信息论安全已经证明。

## 5. 权重、跨域数据与内存生命周期

论文以STORE_CHUNK_ELEM限制每次传入enclave的tensor元素数，长序列规模随batch×seq_len×hidden_dim增加；chunk有助于限制单次buffer，却不能自动确保全体权重、KV、恢复参数和并发请求的峰值都不触发EPC paging。

embedding及logits projection等外部tensor用XOR-based encryption，按需在enclave解密并清零；跨GPU/CPU/SGX的中间值另称采用OTP。没有展开密钥生成和认证供应、数值域、mask长度与分布、一次使用管理、失败重试和重放处理；不能将任意XOR等同安全完整的OTP部署。

若同一pad用于不同tensor或会话，密文差分可能消去pad；若只是异或加密且没有认证，内容可被修改。上述是对未给出协议所需条件的分析，不是发现源码确实复用了mask或已执行篡改攻击。

GPU执行SiLU/ReLU需要尤其解释：常见加法mask可在线性运算后移除，但通常 `SiLU(x+r) − SiLU(r)` 不等于 `SiLU(x)`。可能有其他安全非线性协议或将真实输入暴露给GPU，两者安全边界不同；正文没有提供足够恢复算法，不能替作者补齐，也不据此断言所有实现必然不正确。

表I将Embedding放GPU，而正文称外部embedding权重及时在enclave解密。权重最终如何用于GPU查表、是否再mask、哪些结果返回、释放何时完成，缺少完整状态流程。数据清零只有在旧读写与异步访问停止后才具有回收意义，不能只由一次memset或函数返回推出。

## 6. 主动结果完整性与输出保护

所读全文没有展示针对GPU恶意替换、遗漏或重放结果的完整校验器，也未给出request/tensor/chunk的认证绑定及漏检概率。SGX内计算完整性不自动认证GPU产出的值；XOR及数据掩码也不能独自提供计算结果真实性。

输出侧通过response randomization轻度扰动logits以降低提取效果；但没有展开扰动分布、幅度、随机性新鲜性、是否返回tokens或完整logits及多次查询平均的攻击分析。因此不能把其作用视作有隐私预算证明的差分隐私，也不能保证任意查询规模下防模型提取。

图3给不同模式logit分布相近，支持有限的分布观察，却不证明每个输入逐token输出一致；尤其加入有意扰动后，需要独立报告任务质量。保密、防模型提取、输出完整性和诚实运行效用应分别测量。

## 7. 平台和实验配置的证据边界

作者报告Intel Core i9-14900KF、RTX4090 24GB、SGX2及Ubuntu22.04.5；定制LLaMA-2使用32 heads、4层decoder、固定prompt长度300、batch1、最多生成50tokens，每配置10次。还报告长度100–400、不同depth和batch的扩展测量。

本轮未取得匹配驱动/SDK、SGX quote、硬件或模拟模式、完整模型配置及作者代码，故不能独立确认其真实SGX2部署；尝试取得Intel精确规格页返回403，不把未成功获取当验证通过，也不自行指定作者使用了simulation。这是实验依据未核实，不据此否定用户项目给定的目标硬件和协议假设。

文中4层配置与表III的Layer1–31 profiling尚未解释对应关系；表IV层数列为1、2、2、4，不能擅自将第二个2改为3。参考文献标LLaMA-2的[9]实际题名为LLaMA及arXiv2302.13971，模型版本也需artifact进一步确认。

## 8. 时延、吞吐和定量核对

| 序列300、生成50tokens | GPU-only | CPU-only | TEE-only | SecureInfer |
| --- | --- | --- | --- | --- |
| TTFT ms | 57.41 | 469.13 | 563.64 | 122.70 |
| TBT ms | 57.46 | 447.29 | 553.30 | 118.37 |
| tokens/s | 17.40 | 2.23 | 1.81 | 8.44 |
| 平均每token ms | 57.46 | 447.72 | 553.51 | 118.45 |
| 总时间s | 2.87 | 22.39 | 27.68 | 5.92 |

表VIII总时间比为27.68/5.92≈4.68，相对GPU时间为5.92/2.87≈2.06，即约增加106.27%；不要将“2.06× overhead”解释为只增加2.06%或额外增加206%。吞吐比为8.44/1.81≈4.66，结论称3.7倍与表格不符，保留差异而不静默更正。

TTFT比约2.14，不能将整轮2.06直接套用所有指标。表格比值能说明该作者配置的取舍，不能证明一般边缘LLM达到近GPU性能；尤其四层定制模型、单prompt和固定输出长度不代表完整7B/多Client真实服务。

正文称GPU→CPU每tensor0.2–0.3ms、enclave→GPU小于0.01ms，没有完整tensor大小、传输端点、异步同步及计时边界。不同方向不可直接视作同条件安全跨域成本，更不能将enqueue返回当数据已完成可见。

表III嵌入86.77ms、Layer0 attention/FFN为107.26/10.18ms，正文称占27.6%与54.9%；表中Layer1–31的0.44/0.75是否逐层或合计未明确，无法唯一复算其百分比。本文不选择一种聚合替作者补出结论，也不把该profiling强套到4层模型。

## 9. 功率、能耗与规模扩展

作者以psutil、pynvml和Intel PCM测量，10次平均。表IV四行energy/token比约4.64、1.92、1.80、1.82，而正文概括2–6倍，不能据表宣称全部在该范围；重复层号及完整测量条件仍待核实。

表V不同序列下平均功率比约1.10至0.99；功率接近不表示能耗接近，仍需同一轮时长积分。正文/图涉及energy/token、总J、W与runtime，不能混为一个overhead指标。

表VI仅给1层、batch1/2/4/8的总能量：SecureInfer141.3/134.74/133.47/133.72J，GPU60.88/62.68/63.33/59.74J。正文据此声称energy/token和runtime均下降，但表格没有相应token数量和runtime，且总J也非严格单调；不能据该表单独复核全部趋势。

表VII线性层GPU能耗4–5J、非线性低于0.05J、LoRA0.1–0.3J是representative profiling。它可支持成本动机，却不解释表I将哪些重矩阵乘留SGX、哪些实际交GPU，也不证明全部partition的安全和能耗最优。

## 10. 提取攻击与效用证据

无防御表IX采用1000queries，含GPT-2→DistilGPT2的SQuAD与LLaMA2→TinyLlama的PIQA；后者token match0.8258，另有不同BLEU及ROUGE列。表X为BERT分类agreement0.940/0.990。任务、victim和student不同，不能合并成同一LLM统一安全强度。

表XI防御LLaMA2给BLEU1/2/3/4为0.1098/0.1018/0.1126/0.1180，token match0.5643及Cont Div0.2102。作者称与表IX同设置，若按其对应关系，token match下降约26.15个百分点；但BLEU表头不同，不能拿任意两列直接作同指标差分。

引言的“BLEU score degradation under0.12”与后文“攻击BLEU低于0.12”不是一回事：前者像效用损失界，后者是攻击学生得分。论文缺少清晰的partition-only、perturb-only及组合消融，不能分辨黑盒提取抗性改善由哪个机制贡献，也未证明输出质量损失可忽略。

普通黑盒查询者看不到enclave内部，保护内部tensor主要改变额外观察面；仅比较加入输出扰动后的黑盒得分不能单独证明内部划分安全。对多次平均、自适应query、已知公开骨干或灰盒状态的攻击，还需对应实验而非“strong guarantees”措辞。

## 11. artifact 搜索和复现状态

PDF及固定摘要页未给出可确认的作者artifact。GitHub SecureInfer搜索4项，带Nayan附加条件0项；两项明显为其他推理gateway/learning项目，另两项未建立作者关联且README接口均404。没有把同名仓库冒充论文实现，也不声称全网不存在作者代码。

arXiv HTML中的GitHub链接为LaTeXML/反馈工具，并非论文artifact；不能将页面上的通用GitHub按钮当代码发布。作者原始模型、chunk实现、mask管理、enclave模式、测量脚本和攻击配置均未读，本轮不计源码验证或复现PASS。

## 12. 对项目的启发及后续验证

本项目仍按RMM认证原始Client、可信ProxyRealm控制SMMU、建图核对对象/实际HPA/权限/生命周期并合成受保护GPU Stage-1，其他设备使用硬件Stage-2，页表/根配置/MMIO/固件受可信控制。这条目标隔离机制不依赖本篇分割/掩码设计是否完整，硬件作为实验载体的原则也保持。

值得借鉴的是对LLM对象细化：模型版本、LoRA归属、KV cache、tensor chunk、输出和会话状态都应有明确Client及生命周期。跨域buffer分块或缓存复用时，已有GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch及IRQ127可提供现有控制基础，不再新增平行身份框架。

如扩展LLM服务，应分别证明认证输入/模型→合法提交→真实终态→数据同步→正确接收者可见→静止后回收；旧KV、chunk或mask重放不应跨Client或跨epoch生效。逻辑代际失效不等于GPU停止DMA，输出发布也不能由Host握手或一次IRQ替代。

未来实验可覆盖跨Client复用KV/chunk、模型与LoRA版本错配、重复/乱序通知、错误fence、cancel/reset交错及输出重放；若GPU本身不可信，还需额外计算/结果验证。吞吐、TTFT/TBT、功率与总能量分别报告，且将分割和输出扰动独立消融。这些是研究建议，不是已实现功能或已测项目漏洞。

总体上，本篇提供Transformer组件化保护的应用动机和一个性能取舍实例，但划分一致性、掩码协议、主动结果认证、模型/硬件配置和安全消融仍不足。适合作为LLM应用层相关工作，优先级低于项目核心Portal/CAGE/ACAI/Devlore/PhantomMap/MOLE链条。

统一记录：7页v1全文/27条参考文献/同版本HTML表I与有限artifact检索、Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/SGX/构建/训练/推理/攻击run-id｜正式发表、匹配源码、完整密码协议和部署安全未验证。
