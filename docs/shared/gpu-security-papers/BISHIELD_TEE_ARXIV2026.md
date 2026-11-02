# BiShield-TEE：公开预训练权重下的模型混淆攻击与 TEE–GPU 分割边界

研读日期：2026-10-28。完整阅读 arXiv2610.21565v2 共31页，含53条参考文献、附录A–H及NeurIPS checklist；另核对固定摘要页和作者仓库固定commit的12份完整文件。图按文字、标签和图注理解，未逐像素读取曲线。本篇研究不可信GPU上的模型保护，与CCA设备隔离属于不同保护路线。未改运行代码，无新增性能测量。

## 1. 身份、版本与可追溯证据

题名 BiShield-TEE: On the (In-)Security of Unilateral Weight Obfuscation in On-Device TEE-Shielded LLM Partition；作者 Zhiyuan Wang、Yuezhi Zhou、Ziqi Zhang、Zhu Zhang、Zhixing Tan、Yongheng Deng，单位包括清华大学、中关村实验室及UIUC。

[固定摘要页](https://arxiv.org/abs/2610.21565v2)列v1为2026-10-15、v2为2026-10-16，并称Accepted at NeurIPS2026；PDF首页亦标NeurIPS2026。本轮没有独立核对正式proceedings/OpenReview，因此录用信息按作者及arXiv声明记录，不将预印本排版当作正式会刊验证。

[PDF](https://arxiv.org/pdf/2610.21565v2)共1114221字节，SHA256 `90ff76196bc40e63a39fb8963fb797f36a970498d92646b3f01cd251661d3fc2`。论文及全文提取位于 `build/cca-gpu-followup-20261027/bishield-paper-batch56.pdf` 和 `bishield-fulltext-batch56.txt`；获取、阅读范围和源码校验记录为同目录bishield相关batch57文件。

[作者代码](https://github.com/laduiw/BiShield-TEE)固定commit `182362e34694b0144a69daae3821d0a7b984f957`，提交日期2026-10-14；完整递归tree含85项、未截断。选读12份文件均校验Git blob及SHA256，首次失败7项经固定blob API重新取得，失败记录保留。没有执行仓库代码、模型、SGX、攻击、构建或硬件测试。

## 2. 它解决什么问题，与本项目是什么关系

论文关注：模型由公开预训练骨干微调而来时，将权重乘上秘密矩阵并交给不可信GPU，是否足以隐藏微调模型？攻击者通常已经拥有公开骨干，微调权重与骨干的接近关系可能成为恢复秘密变换的强先验。

GroupCover使用分组变换，ArrowCloak使用缩放、置换及共享秩一项；本文提出针对这些单侧混淆的恢复攻击，并设计左右两侧同时混淆的BiShield-TEE。不能把攻击这些特定软件构造等同攻破GPU TEE、CCA Realm或受保护的SMMU映射。

Portal/CAGE/ACAI及本项目的主线是让设备访问处于可信控制和Client隔离之下；本文的主线是GPU不可信时仍保护模型。两条路线可以作相关工作比较，但不能用混淆实验替代本项目真实任务归属、完成认证或撤销证明。

## 3. 威胁模型和攻击资产

攻击者是控制设备及TEE外GPU/软件的恶意用户，知道保护算法及公开预训练权重，希望恢复微调模型功能；TEE及其内部密钥可信。论文排除TEE侧信道，未验证Arm TrustZone部署，INT4/INT8量化和动态模型更新不在已验证范围。

权重恢复本身不需要victim查询，但ViT/GPT分类器的任务头适配使用少量训练查询，不能把完整攻击称为绝对零查询。Llama从公开base恢复Instruct模型的设置不额外训练任务头。论文只混淆中间Transformer层，Llama embedding和输出projection保持未保护，不能据此声称全部模型参数均被隐藏。

API黑盒基线主要是公开预训练模型替代并按允许条件适配任务头；它不是所有可能黑盒提取攻击的最优上界。论文中的RelBlack接近1，应解释为接近该实验基线，而非已经证明与任意纯黑盒访问等价。

## 4. 单侧变换攻击：成立条件比公式更重要

采用论文矩阵方向，`W_obf = W_vic T`、`W_vic = W_pre + Δ`。正文Eq.1以伪逆估计 `T_hat = W_pre† W_obf`，在相应满列秩条件下得到近似 `(I + W_pre†Δ)T`。对宽矩阵不能直接令 `W_pre†W_pre = I`，不同矩阵形状须分别说明可识别的子空间。

微调差分相对权重较小，并不单独保证 `W_pre†Δ` 很小；还取决于预训练矩阵的条件数及最小奇异值。将“微调接近公开模型”直接当作所有层的统一攻击保证，会忽略病态矩阵和秩不足情形。

对GroupCover，作者使用row/column能量归一化、top候选共支持关系、贪心分组和局部最小二乘/余弦匹配，实验group size为4。附录B局部推导需要组内矩阵满列秩；一阶误差为投影后的微调差分，再加高阶项。

附录的 `s/d` 对应一般位置或各向同性扰动下的平方Frobenius能量比例，不是任意方向扰动的最坏情况界，也不是范数比例。例4/768约0.52%是能量口径，不能写成恢复误差范数必然仅0.52%。

对ArrowCloak，结构为 `T = (diag(p) + kqᵀ)Π`，混淆列中共享方向为 `W_vic k`。攻击先中心化并用SVD/PCA提取主方向，去除共享项，再用Hungarian匹配和逐列参数拟合恢复。附录选定诊断报告主方向余弦大于99.99%，但依赖共享分量支配方差，不能对任意mask强度和权重分布泛化。

Hungarian匹配最坏复杂度包含立方项，PCA也可能成为实测瓶颈；不宜只引用某一步矩阵计算的成本，把完整攻击统一描述为二次复杂度。

## 5. 双侧设计与attention的配套约束

BiShield以Householder反射及对角缩放构造 `T_l = H_l D_l`、`T_r = D_r H_r`，发布 `W_obf = T_l W_vic T_r`。Householder矩阵为 `H = I − 2vvᵀ`，单位向量v使其逆等于自身；利用秩一结构应用反射，避免显式稠密矩阵乘。

论文每轮另引入 `T_m = H_m D_m`，将输入变为 `X′ = T_m X T_l⁻¹`，GPU算 `Y′ = X′W_obf`，TEE恢复 `Y = T_m⁻¹Y′T_r⁻¹`。该恒等式说明诚实线性计算可恢复，不自动给出恶意GPU结果真实性。

attention不能随意给Q/K/V独立变换后直接调用普通attention。论文对Q/K右密钥施加 `(T_rK)ᵀ = (T_rQ)⁻¹` 等耦合，TEE恢复score并执行softmax，再安排probability、V和输出层的相容变换。这是完整跨算子协议的重要部分，不能只保留单层Linear的可恢复性便宣称实现了全部隐私流程。

## 6. 形式化论证能证明什么

附录D限制对角缩放在有界区间内。反射向量v与−v、左右缩放相互补偿等会造成不同密钥表示；作者明确承认，这些表示仍可能对应同一恢复权重，所以密钥不唯一不能单独推出模型不可恢复。

作者进一步连续改变一个对角缩放分量，构造不同的候选微调权重。要全部落入原容差ε以内，需要真实差分范数严格小于ε而留有正余量；若恰在边界，只能给出放宽到ε加任意小量等条件结论，不能静默忽略。

该论证支持“仅凭公开混淆权重与距离约束存在多解”，并未建立计算困难性、语义安全、对所有自适应攻击的黑盒归约，或功能恢复不可能性。任意接近的不同权重可能功能相同；额外执行trace、查询、训练先验及层间约束也可能缩小解空间。

附录G说明纯Householder变换仍保留范数/奇异值等结构，并讨论高维下平均相对位移减弱；H-only实测mean RelBlack约1.34、最大2.37，完整方案约1.00。它支持缩放对该构造的重要性，不能将“更强混淆”直接升级为密码学不可区分性。

## 7. 输入mask与主动完整性需要独立审查

附录H.1描述Freivalds随机验证及错误时拒绝/终止，H.2讨论加性mask及低秩更新。对线性f可使用 `f(X+R) − f(R)`；对任意非线性f没有这个普遍恒等式。应逐算子说明哪里恢复、哪里进入TEE、哪里验证。

低秩mask `R ≈ UVᵀ` 降低预计算和刷新成本，但不等于全空间均匀的一次一密；实数浮点上的随机遮蔽也不能直接套用有限域OTP证明。即使每轮刷新，仍应说明剩余结构泄漏及多轮相关性。检查输入机密、权重机密、计算完整性和重放新鲜性，必须使用分别匹配的论证。

## 8. 安全实验和统计口径

实验覆盖ViT Base/Large、GPT2 Base、Llama3.2 1B/3B，共13个模型/数据集设置。表2中对GroupCover/ArrowCloak攻击的平均RelBlack为2.44、RelWhite为2.49；各设置变化很大，均值是比值平均，不能当成同一任务的统一绝对准确率提升。

BiShield比较input-only、output-only、joint及公开骨干substitution等有限攻击；joint采用固定5轮交替优化。表3均值四舍五入约1.00，但如CIFAR10的63.6对63.4、Llama1B GSM的7.0对6.7仍有差异，不能写成每个设置严格等于黑盒。

checklist称安全取5次实验的最佳攻击、时延取10次均值与标准差。最佳攻击有助于避免低估已测试方法，但不是置信区间；更多迭代拟合公开骨干的解释也不构成所有攻击都失败的证明。

任务头适配查询量如CIFAR10为20/50000、CIFAR100为200/50000，其他设置约占训练集少部分。公开骨干相关性消融通过放大特定Δ观察攻击和效用，不能覆盖所有微调策略、骨干版本或重参数化方法。

## 9. 作者性能结果与可比范围

作者训练平台为A800 80GB、PyTorch2.7.1/CUDA12.8；设备实验使用Xeon W1250、SGX1、93.5MiB EPC、RTX5060Ti和Gramine。ViT使用batch1、长度197，GPT/Llama使用batch2、长度64；warmup后测10次完整forward。它不是自回归长KV缓存服务的tokens/s测量。

| 作者表6时延ms | ViT Base | ViT Large | GPT2 Base | Llama1B | Llama3B |
| --- | --- | --- | --- | --- | --- |
| GroupCover | 1667.97 | 4770.45 | 1028.13 | 3995.28 | 9848.23 |
| ArrowCloak | 1427.14 | 4234.46 | 853.99 | 3386.38 | 8441.53 |
| BiShield | 1073.74 | 2918.47 | 624.04 | 2272.86 | 5148.10 |

逐模型加速比算术平均约为对GroupCover1.701倍、对ArrowCloak1.456倍；不要与总耗时比或native GPU overhead混用。论文表6没有统一原生GPU/全CPU-TEE对照，不能补出作者未给出的近原生结论。

表10密钥占用分别约2.06、5.39、2.00、6.33、14.03MiB。作者明确key footprint不是enclave总内存，不能据此推导所有模型不触发EPC paging。表5授权任务准确率匹配，支持所测诚实效用，不等于验证全部中间浮点值或主动篡改下安全。

## 10. 公开artifact：实际读取范围

完整读取root README、Llama/README，以及BiShield-Device下README、Makefile、`runtime.py`、`householder.py`、`python.manifest.template`、`schemes.py`、`gpu_worker.py`、`model.py`、`offline_preprocess.py`、`benchmark.py`，共12份。未读取完整攻击和真实模型质量流水线，未审计Gramine内部、全部shell启动脚本和所有供应链依赖；tree完整不等于全仓审计。

Device README明确它是使用确定性合成权重/输入的时延和数值恢复工具；`model.py`按固定seed生成浮点权重。Llama README另述真实模型攻击/质量实验，两者不能混成同一已核验执行路径。此处源码观察只约束固定commit所读路径，不能直接反证作者所有论文实验。

离线预处理生成密钥、mask及恢复cache，保存为shared目录下的preprocessed_state.pkl；setup、缓存建立和权重加载不计在线时延。README明确共享state为benchmark用途，生产应通过可信通道或sealed storage供应私有状态，故不能把debug harness中的共享密钥直接定性为论文生产协议的秘密泄漏漏洞。

## 11. 代码与论文安全协议的四处关键差异

第一，`schemes.py`在init_linear生成行变换、输入/输出密钥及rank4加性mask。`benchmark.py`只加载一次states并构造一次ProtectedLinear，之后warmup及多次forward复用该对象；所读blind/recover及循环没有逐轮刷新路径。因而这个计时路径不能验证论文“每forward刷新”的安全及在线刷新成本。

第二，论文attention描述有耦合混淆，但`benchmark.py`先从protected.many取得恢复后的q、k、value，再通过attention_scores把q/k送给worker；attention_context发送probabilities/value。Llama gate还通过plain_device接收normalized输入。对该路径不能宣称所有TEE外激活保持隐私，也不能将它的计时直接归于论文完整私密attention协议。

第三，误差检查将一次recovered输出与worker诚实baseline比较，默认relative-L∞阈值0.005；通过后重复计时。所读路径未实现逐算子Freivalds随机挑战及拒绝流程，worker的ok字段只表示执行状态。数值正确性检查不是恶意GPU计算完整性验证，文件响应到达也不是认证完成。

第四，Gramine manifest启用debug，shared/results允许访问，部分Python环境为allowed files；file IPC采用signal、JSON和NumPy文件，没有所读路径可见的会话认证/序号绑定。共享pickle及配置仅有格式/形状检查，不构成对恶意Host的认证供应。README已声明生产加固需求，因此这些是artifact测量边界及缺失验证，尚非已执行漏洞利用或对整个方案的完整安全审计。

另外，代码对角缩放采用正数log-uniform采样，与论文附录E.4的随机符号描述不同；不在未经实验时推断差异的安全影响。GPU worker同步CUDA并读写文件，其开销不可直接代表本项目共享内存、原生fence及中断通知路径。

## 12. 对当前项目应加入的设计

仍接受项目目标假设：RMM认证原始Client；可信ProxyRealm控制SMMU；建图核对对象归属、实际HPA、权限和生命周期，软件IPA→HPA合成受保护GPU Stage-1；其他设备硬件Stage-2，页表、根配置、MMIO及固件受可信保护。实验硬件是验证载体，不以缺少某硬件特性否定该模型。

本篇最有价值的启示是把“保护对象存在”与“完整执行路径真的覆盖它”分别验证。建议沿现有GPUVM、认证队列、private plan/snapshot、native fence和cookie/epoch记录任务与对象的绑定，不新增平行身份系统；模型、LoRA、KV cache、输入/输出和恢复状态均须明确归属及撤销边界。

可信完成链应是：认证Client提交→固定授权plan与对象代际→真实GPU任务/fence终态→核对错误及取消→必要缓存同步→将终态只发布给对应Client→通知唤醒。既有IRQ127可以唤醒读取受保护完成记录，单独一个中断、文件信号或Host提供的ok不得成为成功依据；通知合并不应丢失终态，重复/乱序通知不得重放旧任务。

撤销还需要停止旧GPU访问并排空在途操作，随后失效旧映射/通知并安全回收；cookie/epoch变化本身不代表DMA已停止。reset/cancel与成功竞争时，应定义唯一终态及发布顺序。这些是项目设计建议，不是本轮已证实的实现漏洞或已完成的改动。

若未来明确把GPU固件/计算单元也纳入恶意攻击者，Stage-1访问隔离仍不能验证算术结果，此时才考虑Freivalds等按算子验证机制，并绑定模型版本、输入、任务和输出；若GPU及可信固件属于TCB，则优先完成跨Client隔离、真实完成与回收证明，无需为引用本文默认增加混淆计算层。

## 13. 可验证研究问题与后续文献

适合项目的实验包括错误Client通知、旧cookie/epoch重放、完成提前、合并/重复/乱序IRQ、cancel/reset竞争、结果未同步即发布，以及对象回收后旧DMA/旧完成污染新任务。分别报告拒绝行为、受害Client正确性、错误传播、恢复及性能，而不是仅看平均时延或收到中断。

文献后续可沿GroupCover、ArrowCloak、AMULET、LoRO、TSQP及TransLinkGuard追踪原文；本轮没有独立精读和注册这些条目，不以本文转述冒充其已证实结论。对本项目优先级而言，它们是应用层补充，核心比较仍应围绕Portal/CAGE/ACAI、PhantomMap、MOLE及可信中断工作。

统一记录：31页v2全文/53条参考文献/附录A–H/checklist、固定commit的12份完整文件静态阅读、Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/SGX/构建/推理/攻击run-id｜正式会刊、全部攻击源码、真实部署和生产安全协议尚未验证。
