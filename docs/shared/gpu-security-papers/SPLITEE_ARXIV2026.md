# SpliTEE：差分隐私GPU外包、完整观察组合与跨边界协议

研读日期：2026-10-28。完整阅读arXiv v3的35页、§1–9、54条参考文献、5图7表，以及固定作者仓库中的6页补充材料；主文14页渲染视觉核对。固定公开实现并定向静态核对通信、噪声生成/消费及计时路径，没有运行推理、模型、攻击或硬件。未改运行代码，无新增性能测量。

## 1. 身份、版本与证据

SpliTEE: Fast and Private LLM Inference by Coupling GPU-Assisted Trusted Execution Environments with Differential Privacy。Shashie Dilhara Batan Arachchige、Robin Carpentier、Hassan Jameel Asghar、Dali Kaafar；Macquarie University。本轮研究[arXiv:2609.15039v3](https://arxiv.org/abs/2609.15039v3)，2026-10-06；[PDF](https://arxiv.org/pdf/2609.15039v3)、[HTML](https://arxiv.org/html/2609.15039v3)。页面和补充材料标为投稿/under review，没有核实正式接收，不把“Manuscript submitted to ACM”当作已发表。

v1题为Improving LLM Inference on Trusted Hardware with Differentially Private GPU Outsourcing，44页；本轮以改题后的35页v3为准，不混合版本或重复计作两套系统。完整v3 PDF为1031013字节，SHA256 `ffe338ddf1b244f257693db08184b806e5f41c46c8128ad7b2713f2a14c50931`；HTML为831000字节。先前部分下载及严格206范围恢复记录保留，本轮不以不完整文件充当全文。

[作者仓库](https://github.com/DPVault/SpliTEE)固定提交 `ae865e62fdca81a1d84ecd1d51a0d8edfdd394ae`，2026-10-22；完整27项递归树未截断，19个blob全部取得并核对Git blob SHA1与SHA256。补充PDF203857字节、6页，SHA256 `52abaeea7db702f682b19db22e7bf0acf76f18372e5bdc7fb090d154bd909dd4`。仓库在v3之后更新，不能默认为生成v3图表的确切实验提交。

证据在 `build/cca-gpu-followup-20261027/` 的splitee batch68/70文件：主文、HTML、补充全文、14页渲染、完整固定artifact、获取清单及算术核查。树完整不等于逐行审计所有代码；本轮完整读3份README和`Host/Worker.py`，定向阅读`Runtime_Noise.py`、`Precompute_Noise.py`的相关路径，其他攻击文件仅取得和检索，不宣称已全面审计。

## 2. 问题与路线

目标是保护远程LLM用户的prompt，同时利用没有可信执行能力的GPU加速CPU TEE。整个模型在TDX内运行较慢；作者沿Slalom的线性运算外包路线，把输入x加Gaussian噪声η后发送GPU，GPU计算W(x+η)，TDX减去预先计算的Wη。实数域等式恢复Wx，浮点实现会产生误差。

外包Q/K/V、O、Gate/Up及LM head；tokenization、embedding、RMSNorm、attention/softmax、SiLU、Down及其余操作保留TDX。QKV共用一次输入和一份mask，对应三份correction；Gate/Up同理。这样分组不是在不同秘密输入间重用mask，但跨请求重用同一mask会暴露输入差，必须另外禁止。

相对Slalom，贡献主要是保持浮点域的DP遮蔽、各输入来源的全局敏感度估计、噪声消去误差分析，以及LLM拆分推理/重建攻击实验。它没有建立CCA GPU TEE，也没有把GPU直通、硬件共享、SMMU授权或可信中断作为贡献。

## 3. 威胁模型与可信基

CPU TEE和用户到TEE的通信可信；服务商知道模型结构与全部权重，可观察所有GPU输入、输出和计算，但被限定为诚实而好奇，按协议执行。明确不验证GPU计算完整性，并排除TEE侧信道、模型窃取等攻击。服务商自有模型本来对服务商公开，“模型IP保护”主要是用户只能查询API，不是保护权重不被Host看到。

TCB包含TDX及Guest OS、Python/PyTorch/Transformers、模型执行和分词、随机生成器、noise bank及其存储、RPC解析、共享内存复制等；论文未给完整TCB或LoC。用TDX隔离不自动意味着已实现证明绑定的安全输入通道、受保护磁盘和抗回滚，需检查具体配置及代码。

因此不能把本文的安全性直接迁移到恶意Host、恶意GPU固件或恶意多Client。本项目在用户既定假设下由可信ProxyRealm与RMM执行强制授权，目标比本文的诚实GPU外包更强；不能为获得其性能而静默削弱威胁模型。

## 4. 运行与数据流

TDX私有内存保存原始输入、mask和correction。IVSHMEM只传遮蔽张量及遮蔽结果；TCP传projection名、layer、offset、shape、dtype与nbytes。Guest写共享输入，发请求；Host复制到pinned缓冲并送GPU，完成GEMM和D2H后写共享输出，发响应；Guest复制到私有缓冲并消去correction。

固定Worker把QKV/Gate-Up权重融合，复用pinned和GPU缓冲，使用独立CUDA stream，并在写共享输出前等待该stream上的event。这可减少分配、传输与全设备同步成本，但CUDA event在不可信Host内，由诚实执行假设赋予含义；它不是恶意Host下可直接信任的任务完成证明。

Worker顺序处理连接和请求，监听一次连接后在handle_client内循环，共用固定8GiB共享区；Guest输入offset0、输出从1GiB开始分段。没有多租户归属、每Client独立授权或可信中断路由证明，不能把batch15推理称为15个恶意Client隔离。

## 5. 敏感度与GDP的准确含义

论文采用Gaussian differential privacy，记其参数为ε；为避免与通常(ε,δ)-DP混淆，本报告称μ=ε_GDP。单次机制为f(X)+N(0,(Δf/μ)^2 I)。μ越大噪声越小、隐私越弱；μ-GDP不是“以μ概率不泄漏”，也不是默认相同参数的纯DP。

Thm1给RMSNorm/LayerNorm的直径界Δ_LN≤2√d·||α||4；Thm2给attention输出界Δ_att≤2√d·||W_val||2·||α||4，利用softmax概率和为1；Thm3给激活输出界2√d·(√d·||α||4+||β||2)^2·||W_up||2·||W_gate||2。它们是最坏范围界，存在较松空间，但用来减少噪声必须仍证明有效的全局/平滑敏感度，不能只以样本小或重建失败为依据。

实际矩阵通常不是d×d：补充材料明确Llama-3B有28层、hidden3072、intermediate8192、Q24头/KV8头，K/V输出1024；Qwen-4B有36层、hidden2560、intermediate9728，Q输出4096。主文中的500维示例与简化等维表达不能作为真实模型配置，需按矩形投影和多头拼接重新匹配敏感度维度。

## 6. 完整观察组合是主要证明缺口

§5.4明确承认：一次prompt会因多个算子、各层及每个生成token重复外包，完整保证应该组合全部实例；因为所需噪声过大，论文仍使用单次操作的√n·μ甚至固定μ，并诉诸重建攻击失败。它没有给出完整会话transcript的目标μ，更不能直接把EPN称为整个推理过程1-GDP。

对独立条件机制，顺序组合参数按sqrt(sum μ_i²)增长；需要定义邻接prompt、每次发布受影响的行数、跨层/生成的条件敏感度及实际观察集合。不同prompt可以在条件满足时用并行组合；同一prompt的重复暴露不能因共享内存或mask每次更新而免除预算。

说明性保守算术：100token的单次张量外包若按作者逐行组合为μ=10，Llama28层各QKV/O/Gate-Up三组加LM head共85组，一次完整prefill的通用顺序组合界为sqrt(85×100)≈92.20，而不是10。此例只说明把局部预算当全局预算不成立；它不是最紧界、不是测得泄漏，也不证明存在达到该界的攻击。实际decode/KV cache及多会话还需单独核算。

论文的邻接是替换一个token，并不直接提供整段prompt任意替换下相同预算的保证。公开模型、长度、算子顺序和计时也属于观察边界；数据依赖的GPU调用形状和控制元数据不能用张量上加噪声自动覆盖。

## 7. 误差界与数值可用性

Thm4在无underflow/overflow、标准浮点模型下分析噪声加减与dot product误差，主要项为γ_d·<|w|,|x|+|x+η|+|η|>+u·<|w|,|x|>，u=2^-p。更强隐私导致更大mask，消去时更易丢有效位。Down敏感度和张量较大，因此留TEE；FP64虽减误差，也增存储、传输和计算成本。

实验实际使用Eq26的pairwise-summation估计γ_(ceil(log2d)+1)，而不是对所有GPU库内核严格证明的Thm4执行模型。Table4报告约9.25%–10.03%的输出元素超过所算界；平均界约为平均误差4.27–4.35倍，并不能将“平均更大”当逐元素保证。正文也承认库内优化可能不符合其简化dot-product模型。

Theorem4表达式把x+η作为dot product输入，对实际先执行fl(x+η)、FMA/TF32、不同归约树及混合精度的覆盖还需明确；O(du²)的常数依赖数据，不能不加条件忽略。离散浮点Gaussian采样是否保留目标GDP保证也未专门证明。最终token由logit间距决定，小平均误差不等于所有生成轨迹相同。

## 8. 作者实验与量化结果

补充材料报告Xeon Silver4514Y、16物理核、约117GB主存；TDX Guest32vCPU/约93GB；RTX PRO4500 Blackwell/约32GB；Ubuntu24.04。仓库列Python3.10.20、PyTorch2.7.1+cu128、CUDA12.8、Transformers5.12.1等软件。此处按作者材料记录，没有在本项目或对应硬件复测，也不以该硬件条件否定目标设计。

性能使用Dolly45prompts、平均约100输入token、batch15共3批，每配置执行一次，输出上限100/200/400/800。Fig4的平均每prompt时间是批时间分摊，不等于单用户请求端到端延迟，也没有重复轮次、置信区间、TTFT/尾延迟或恶意并发评估。

| 模型/输出token | 全TDX秒 | EP1秒 | 裸GPU秒 | Slalom适配秒 | 全TDX/EP1 |
| --- | --- | --- | --- | --- | --- |
| Llama3B/100 | 4.10 | 2.46 | 0.34 | 3.32 | 1.667× |
| Llama3B/800 | 53.28 | 23.90 | 3.09 | 28.45 | 2.229× |
| Qwen4B/100 | 5.95 | 3.49 | 0.39 | 5.00 | 1.705× |
| Qwen4B/800 | 82.78 | 35.29 | 4.37 | 50.38 | 2.346× |

按图上舍入值复算，EP1相对Slalom适配版的最大速度比提升约43.27%，对应时间下降约30.20%，不是时间下降43%；这是不同分母。对裸GPU仍慢约7.24–8.95倍。Slalom基线去掉Freivalds验证，以q=10485767及8bit量化适配同一组LLM算子，不能泛化成本文胜过所有Slalom实现及同等恶意完整性方案。

Table2在100条prompt、200输出token的greedy生成下，EP1精确整句匹配84%、token匹配91.49%、语义99.67%；EPN为10%、42.55%、95.56%；EP10/15在这批样本100%匹配，不构成任意输入的零误差证明。ε=.5时正文说33%tokens diverge，实际33%对应整句不匹配，token不匹配为14.57%。语义相似度也不保证敏感数字/事实正确或任务效用不变。

Table4的169个投影实例×1000次=169000个输出元素/ε，EP1平均误差1.13e-4、界4.83e-4、约9.89%越界；Table5另在完整生成中受控缩放误差，EP1平均2.06e-4/语义99.20%。两表实验不同，不能混成同一统计；以1e-4作为“超过就一定降质”的硬阈值超出实验支持。

## 9. 攻击实验说明什么

重建器用Llama3B、投影网络和LoRA，2000条Pile分1800/200训练验证，5epochs；在500条Dolly/100–300token评估。单QKV、LM head及同层QKV+O+Gate-Up组合，噪声未知/已知分别训练。noise-free QKV语义79.87%、F1 70.30%；组合语义82.19%；EP1 noise-aware组合语义5.23%、F1 15.30%。摘要的“80%准确率”主要对应语义相似度，不能等同80%token逐字恢复。

EP1000组合语义6.55%，EP2500升至78.41%；GPT-5.4文本修复使无噪QKV语义升89.54%，对EP1无明显改善。这支持已测攻击下mask有效；不证明所有攻击、跨层/跨轮联合估计、重复查询或已知随机种子下都安全。补充材料只组合Layer0三组输入，理由是更深层增训练复杂度；这不是完整transcript最强攻击者的穷尽分析。

500prompt两两124750对平均token precision/recall22.02%、F1 20.71%，用于说明常见词重叠；这个经验背景值不能替代形式化区分优势界。模型可能暴露属性而难以整段重建，不能以重建失败排除所有prompt信息泄漏。

## 10. 固定artifact的四个关键边界

第一，`Precompute_Noise.py`公开GLOBAL_SEED=1234，main及分块分别以GLOBAL_SEED和GLOBAL_SEED+chunk_index×1000003设torch种子，再用`torch.randn`产生mask，并在元数据保存global_seed。公开权重、配置和相同随机调用轨迹下不能把这些实验mask视作对观察者不可预测；TEE中运行不使公开固定种子变成秘密。这里是静态证据，没有执行恢复攻击，也没有据此宣称论文理论Gaussian机制本身失效。

第二，谱范数默认30轮power iteration，返回||Wv||2；有限迭代一般只是近似/下界，不是敏感度校准需要的认证上界。代码虽提供exact选项，默认没有误差包络或安全裕量证明，不能把估计量直接当Thm2的最坏保证。需用有证明的范数上界或带误差界的数值方法，并处理多头维度。

第三，LoadedBank按shape保存deque、popleft消费，空bank报错且禁runtime refill，支持一次运行中的一次消费。但文件用`torch.save`保存、重启可`torch.load`同一文件；未见持久已用计数、密封会话绑定、抗回滚或已消费文件销毁协议。TDX本地磁盘也不天然属于私有内存保护；生产部署要保护静态mask文件且阻止重载复用，不能只依据“写在Guest中”推出安全存储。

第四，Guest recv_msg对Host TCP响应直接`pickle.loads`，没有认证报文或有限结构解码；响应长度、offset/shape等也缺完整有界策略，尽管nbytes一致性及部分shape会被检查。恶意响应不属于作者诚实GPU模型，但若扩成恶意Host/多Client，反序列化本身就不能跨该信任边界。本轮没有执行载荷或声称实际攻破TDX；应区分现有假设和更强部署目标。

此外，当前默认配置为30prompts、CAP100、batch15，不等于主文45prompts和四种cap；README给Guest PCI地址00:02.0，代码为00:03.0，需要实际配置一致。预计算和每批bank加载都在run_one_batch的generate计时之前；在线数字没有覆盖预计算/加载、bank安全存储、远程证明或服务冷启动，持续服务还要核算补库成本和容量。

## 11. 与本项目两条主线的关系

本项目继续采用RMM认证原Client、可信ProxyRealm控制SMMU；建图时校验对象、实际HPA、权限与生命周期，软件IPA→HPA合成受保护GPU Stage-1，其他设备保留硬件Stage-2；平台保护实际页表、根配置、MMIO及可信固件。本文的DP遮蔽不能代替这些跨Client强制内存隔离，也不能授权裸HPA访问。

对“直通与共享/性能”部分，可借鉴分组传输、复用已授权私有缓冲、一次完整请求后的局部完成等待，但要用现有GPUVM、认证队列和private plan/snapshot证明复用期间归属与生命周期不变。不能把Host event的信任假设照搬；合并QKV等应用语义优化也不应变成通用GPU共享协议的必要条件。

对“任务内存与中断通信隔离”部分，保留native fence、cookie/epoch和IRQ127；通知只能促使Client读取已绑定Client/session/job的权威状态，不凭响应ok、TCP到达或普通CUDA event发布SUCCESS。任务成功、CPU可见性、旧DMA排空、撤权完成和安全回收需要分别建立条件；异常/超时/reset不得重用旧结果或旧资源代次。

若可选增加不可信外包模式，应在应用层明确区分“受保护GPU执行”和“DP遮蔽外包”，对后者补完整transcript预算、可信随机源、一次性bank与持久抗回滚、安全解析、结果完整性策略及数值效用契约。复用既有身份/epoch，不另建平行token体系；未补完前不能给后者与强隔离相同的安全声明。

## 12. 后续证据与研究判断

值得吸收的是按算子边界定义暴露面、显式分离在线和预处理成本，以及把数值正确性纳入安全协议。最直接的研究启发是“局部保护必须组合成端到端保证”：单页授权不自动证明整个地址生命周期安全，真实中断不自动证明该Client该任务完成，单次DP发布也不自动保护完整推理。

沿§2/参考文献继续TwinShield（arXiv:2507.03278）和Depth Gives a False Sense of Privacy（USENIX Security2025），分别核查恶意计算验证和隐藏状态暴露；本轮仅新取源，不计独立完成。GR-T正式EuroSys版仍受全文获取限制，arXiv:2111.03065v1仍是早期CODY；XpuTEE/AccShield等缺项保留。用户提供的GPU文献库已重新固定树和README，用作发现入口，不用清单标题代替全文证据。

统一记录：35页v3/54参考文献/5图7表、6页补充材料、14页视觉核验、固定27项树及19blob校验、定向源码静态核查｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增运行PASS｜保留研究，完整隐私组合及安全部署补全属于建议，整体调研继续。
