# Performance of Confidential Computing GPUs（ICDCSW 2025）：多模型驻留、调度与可信完成边界

研读日期：2026-10-27。完整阅读6页arXiv v1、22条参考文献，无附录，核对正式书目及论文明确链接的SINCERE仓库；只做公开资料和限定源码静态研究。本文属于GPU机密计算性能/调度工作，不是Arm CCA隔离架构。未改运行代码，无新增性能测量。

## 1. 来源、版本与研究位置

题名 Performance of Confidential Computing GPUs。作者 Antonio Martínez Ibarra、Julian James Stephen、Aurora González Vidal、K. R. Jayaram、Antonio Fernando Skarmeta Gómez，单位University of Murcia和IBM Research。正式发表在2025 IEEE 45th International Conference on Distributed Computing Systems Workshops（ICDCSW），237–242页，DOI [10.1109/ICDCSW63273.2025.00046](https://doi.org/10.1109/ICDCSW63273.2025.00046)；是workshops论文，不写作ICDCS主会论文。

实际阅读[arXiv:2505.16501v1](https://arxiv.org/abs/2505.16501v1)，2025-05-22；PDF754926字节，SHA256 `64d6022c6dd00d4cffc3530664a0a52bb7c9bfe85a01289195385b77b948fdcb`。完整正文与参考文献文字已读，架构图1栅格已提取观察；图2–7为矢量Form，本轮没有逐像素渲染或重算所有图点，定量结论以正文和所选源数据分别说明。

论文明确链接[Antonio-MI/sincere](https://github.com/Antonio-MI/sincere)，README全称SINCERE: Scheduling Inference batches in Confidential Environments for Relaxed Executions。HEAD已到2026-07-23，不直接冒充论文版本；另查询论文日期前提交，固定2025-04-02的 `285e5b73f49aee146b0499c37efb55e7645de1eb`，取得完整2756项递归树，未截断。这是论文时期公开版本，不保证作者所有实验均恰由此提交生成。

证据位于 `build/cca-gpu-followup-20261027/` 的ccgpu、sincere及batch45文件；GitHub blob API遇限流，raw备用路由超时，改用按同一commit寻址的CDN并用原始Git blob hash和长度核对。已下载的资料与实际全文阅读的文件分开记录，不将树完整等同源码安全审计，也不执行仓库的模型下载、部署或实验脚本。

## 2. 问题：常驻模型的低开销不覆盖频繁换入换出

研究单VM、单H100、同一时刻仅一个模型驻留，多个模型的请求排队并触发加载/卸载。不同模型需要频繁交换时，CPU–GPU安全传输不再只是少量输入输出，也包括大规模模型参数；作者评估调度如何在装卸代价、batch填充时间和SLA之间取舍。

它直接延续前一篇Hopper性能报告：前者主要比较已加载模型下的推理，本文把model swapping纳入服务运行。两篇不同百分比不应简单当作互相推翻；需要固定驻留、量化、请求到达、模型组合和统计口径后比较。更长计算可摊薄传输，并不意味着频繁切换模型时也只有个位数损失。

README早期目标是用户、云服务方、模型开发者三方之间保密，最终目标明确退回性能评估；论文与当前代码没有给出已闭合的三方安全协议。不能把最初问题陈述当成已经实现的用户—模型—调度器隔离方案。

## 3. 威胁模型和TCB：采用CC平台而非提出隔离证明

背景把Host/hypervisor作为潜在不可信观察者，使用CPU CVM和H100 CC保护运行数据及传输；图1把CVM里的NVIDIA driver和GPU画在保护路径内。正文称需要“Secure Hypervisor with CC support”，应理解为虚拟化支持/正确配置需求；不能据这一短语自行断定论文把整个hypervisor纳入可信基，也不能据图证明全部管理权限已安全撤销。

没有明确完整TCB规模、CPU型号/TEE选择、证明测量allowlist、nonce/证书/设备绑定和密钥释放协议；论文侧重性能，不提供恶意请求、DMA/MMIO篡改、IRQ伪造或跨租户泄漏的安全评估。所用Flask、PyTorch、transformers、guest OS、驱动、固件等的信任范围需部署另行定义。

观察的是多模型共享一个VM/GPU，不是多个恶意VM/Realm互相隔离。模型队列没有天然等同Client身份，SLA达标也不是恶意Host下可用性定理；调度策略优于另一策略不能证明资源公平、抗饥饿或硬实时截止期。

## 4. 工作流程、参数与四种调度

请求由InstructLab生成prompt后转为JSON，指定模型；先profiling加载/卸载时间和不同batch的推理性能，再由Flask维护每模型队列，Bash组合流量、SLA、调度策略，记录请求和系统指标。每次实验20分钟，单VM单GPU，输出设置max_new_tokens50；代码是生成上界，不应无条件称每请求实际恰好50个输出token。

流量为Gamma、bursty与ramp，目标同平均请求率。客户端固定NumPy/Python seed42，模型选择概率0.1/0.3/0.6，对应granite/gemma/llama的传入顺序；Gamma实现shape1，即该配置下是指数间隔，不代表测试了所有Gamma形状。真实到达取决于协程、连接和运行开销，固定种子不能替代相同到达轨迹验证。

| 调度组成/策略 | 论文意图及条件 |
| --- | --- |
| Best Batch | 等待profiling得到最大吞吐的OBS；不是全局最优调度证明 |
| Best Batch + Timer | 尽量填满OBS，同时以预估装卸/处理成本提前触发 |
| Select Batch + Timer | 根据历史到达率和剩余延迟预算动态选batch，倾向降低等待 |
| Best Batch + Partial Batch + Timer | 对当前驻留模型先处理部分batch，试图减少切换 |

SLA为40/60/80秒，面向relaxed inference。OBS通过增大batch直到OOM、比较吞吐确定；源码固定granite48、gemma64、llama64，Select候选8/16/32/64。Partial含驻留至少10秒及超过OBS四分之一的阈值，Timer使用手工估计处理时间，参数取值对结果有直接影响。

论文在“batch accumulation time ≤ arrival rate”处存在量纲不一致，前文正确关系应把累积时间与可用延迟比较，随后batch≤arrival_rate×desired_latency在量纲上成立。不能按印刷的不变量实现，也不能由预测到达率给出确定性截止期保证。

源码 `get_optimal_batch_size` 取最接近目标的候选值，而不是保证不超过预算的最大候选，可能向上取整；其desired_latency写为SLA减adjusted_time_limit，后者是已减装卸/处理成本的等待预算，语义应与论文公式另外核对。因此它是启发式实现，不是公式不等式的机械保证。

## 5. 平台和作者主要结果

H100 80GB HBM3，Driver550.54.14，CUDA12.4，PyTorch2.4.0+cu121，Ubuntu22.04-amd64，正文Python3.10.12。README系统段写Python3.12.4、安装建议又为3.10.12，不能假定完全一致；CPU/具体CVM模式及整套启动配置未充分展开。

模型为Llama3.1-8B、gemma7B和granite7B-base；表2大小16.07GB、17.07GB、26.98GB。框架初始化不计入loading时间，但tokenizer、模型参数初始化、GPU分配/I/O计入。正文称卸载约0.004–0.01秒；公开CSV存在不同数值，下一节单列，不静默合并。

| 指标 | 作者正文结果 | 正确解读 |
| --- | --- | --- |
| 请求latency | No-CC比CC低20–30% | 以CC为分母；反向CC比No-CC高约25–42.9%，不是同样20–30% |
| SLA40达标 | CC50%，No-CC70% | 差20个百分点；不是同一分母下只增20% |
| SLA60达标 | CC70%，No-CC85% | 差15个百分点；两者SLA80均超过90% |
| overall throughput | No-CC比CC高45–70% | 反向CC比No-CC低约31.0–41.2%；不是“CC损失45–70%” |
| GPU utilization | No-CC约高50%，两者均低于50% | 论文定义为推理时间占运行时间，不自动等于硬件SM活动率 |

SelectBatch+Timer的延迟/SLA最好，但含BestBatch的三种策略吞吐相近且较高；Partial组合没有得到最高吞吐，作者归因为参数难以全部配置最优。bursty通常延迟更高、达标更差，吞吐略低；策略目标存在取舍，不能选择一项最优就宣称全方面提升。

推理阶段处理率相近，装卸之外的整体吞吐差异明显，支持作者把换入成本作为重要瓶颈。没有对CPU CVM、磁盘cache、参数反序列化、H2D加密及调度分别做完整因果隔离，因而不把整个差值确定归因某个加密引擎。正文对No-CC切换“稍多”“相近”和结论“相同”措辞也不完全一致。

## 6. 所选源码揭示的完成与计时语义

完整静态阅读README、客户端 `api_calls.py` 和服务端 `api_scheduler_experiments.py`。客户端对本机HTTP发送异步请求；服务端允许的model列表属于应用输入过滤，并非RMM认证Client、对象所有者或任务授权。服务端绑定0.0.0.0，所选路由没有TLS/调用者认证；这不等于实际部署必然暴露公网，只说明性能原型不提供完整安全通信协议。

普通未填满batch的响应是“Request queued with ID”；触发batch的请求返回完成ID列表，真实生成文本主要保留在服务端临时responses。HTTP200并非每个原请求都已完成并正确收到结果，服务端随机UUID前8字符也不是可信Client身份或带代次的GPU完成标识。该原型不用于证明端到端输出归属。

客户端每次请求timeout60秒，而论文SLA包含80秒；create_task的未完成请求没有统一gather/drain，结束时发送Stop并退出session。服务端Stop等待剩余队列的代码被注释，直接用last_batch_processed_time-first_request_time记录total_time并置END，不阻止之后所有在途工作。需要区分已发、已入队、已处理、已返回与测量窗口后的剩余请求。

服务端在推理后为batch每个请求记CSV，latency从服务端收到请求到推理结束计时，不包括客户端到达前网络与完整响应回传；这与论文“用户发送到服务器发回”的端到端措辞不完全相同。overall运行时间从首个请求到最后一次已记batch，和固定1200秒生成窗口也不同，不能未经说明互换分母。

`process_batch` 用全局锁串行执行模型装载和推理，但请求/后台Timer等路径在获取该锁之前就可能替换running队列、搬移请求，内部还直接清空Queue的底层queue。锁保护GPU执行不等于所有队列转换原子；未在本轮执行竞争或证明丢请求，只记录需要覆盖的同步范围。

模型切换删除旧引用并调用 `torch.cuda.empty_cache()`，这是应用资源释放，不是页清零、固件状态清理、旧DMA静默或跨Client安全回收证明。模型alias允许列表和“仅一个模型加载”也不能提供相互不信任租户的内存隔离。

Timer默认读取noncc profiling文件，README要求人工换到对应文件；处理时间写死8秒，考虑均值加1标准差并至少保留5秒等待。到达/执行分布没有给出可用于硬截止期的界；不能把这套Timer当作可信超时即可安全重分配资源的机制。

## 7. Artifact范围、数据差异和可复现限制

原始blob API成功核验8份根目录文本，CDN另核验6份，共14份不同文件。全文静态阅读6份：README、客户端、主调度服务、模型profiling、batch profiling服务、实验runner；另全文读取两份loading CSV。notebook共77个cell，仅定向阅读15/17/24的日志解析与CC/No-CC统计，其他源段和嵌入输出没有完整审计；剩余已获取文件不冒充已读。没有运行下载代码、执行notebook、触发模型推理或验证GPU CC开关/证明策略。

两份公开profiling CSV分别给granite/gemma/llama的CC loading为8.9661/12.0832/11.0054秒、No-CC为3.5534/4.6755/4.1446秒，约2.52/2.58/2.66倍。两批记录来自不同日期，不能由固定提交推定所有运行条件严格相同；这些是artifact数据，不把它们自动等同图3逐点原值。

同一CSV的model_size字段为50.21/63.63/59.84GB，与论文表2的26.98/17.07/16.07GB不同；gemma卸载CC0.0392秒、No-CC0.0317秒也超出正文0.004–0.01秒。没有完整模型dtype、checkpoint和统计链证据，本轮不确定是哪一步差异所致，不静默选择较有利数字。

所取profiling脚本默认模型列表是小GPT系列，大模型列表留注释；run脚本默认traffic_mean12、SLA60，正文全参数网格需自行改配置。README说明和文件名也有 `run_experiments.py` / `.sh`、processing/process_results的差异；不以默认一键执行等同复现全部论文曲线。profiling的device是torch.device对象，卸载处却与字符串cuda比较；batch profiling和正式运行的pipeline dtype参数也不同，不能假定两个路径完全一致。

定向notebook源码明确以 `df.shape[0]` 即已有CSV行数作SLA分母，计算 `latency<SLA` 的比例；没有在该公式中纳入已发但未处理/未记CSV的请求。overall/inference吞吐也用该行数分别除以日志total_time/total_inference_time，并把每run汇总值写回每请求行；后续按行聚合可能形成请求数加权，不能未经核对称等权独立重复。这里只核查统计公式，未执行notebook、重算全库或确认论文每幅图使用的全部cell。

论文称测CPU interrupts/context switches等系统信息，但未分析IRQ来源认证、GPU job完成归属、错误/重复通知或VM间中断传递。该论文补充性能取舍，不能代替Devlore、Heckler、WeSee、Sigy等中断/异常安全工作，也不能据CPU中断计数推断完成正确。

## 8. 对当前CCA GPU项目的具体启示

接受RMM认证原始Client、可信ProxyRealm统一控制SMMU、建图时核验对象/实际HPA授权/权限/生命周期并合成受保护GPU Stage-1、其他设备保持Stage-2的架构假设。本文的CVM加密H2D和单VM多模型与本项目共享映射及多Client不同，不用H100代价否定目标设计，也不套用其百分比预测glmark。

第一部分“GPU直通/共享及性能优化”可以明确驻留策略的安全约束：仅在相同GPUVM、Client归属、对象版本/权限仍有效且真实在途引用受控时复用已授权对象或私有计划；按Client公平预算和等待时间限制批处理，避免仅为减少切换而无限拖延其他Client。这里是项目建议，不宣称本文实现或当前代码已具备全部策略。

第二部分“内存与中断通信隔离”优先收敛到同一生命周期：提交准入→队列持有→真实执行→终态/错误确认→输出发布→引用释放→撤销与再授权。复用已有GPUVM、认证队列、私有快照、native fence和cookie/epoch；持久IRQ127只唤醒检查，入队ACK、Timer到期和Stop响应都不能直接触发可信成功或物理页复用。

性能驻留/批处理必须保持检查过的对象版本和实际执行参数一致；Client销毁、取消或reset时先停止新提交，处理旧任务/事件和DMA，再撤销及回收。增加epoch能拒绝旧完成通知，不能停止旧访问；部分batch的完成也不能把尚未执行的整个Client队列一起标记成功。

测量时分别保留发出、准入、终态、结果发布、失败/取消、剩余请求数，以及相同窗口下的吞吐、等待/完成延迟和公平性。不只对已成功记录的请求计算漂亮的SLA比例；若部分项未运行或失败必须保留。本轮仅分析，不引入硬件测试、身份框架或新增性能主张。

## 9. 评价和引用链

价值在于把CC性能研究从单模型稳态推进到多模型装卸和服务调度，显示“模型驻留程度”是重要实验维度。边界是6页短文、具体平台和启发式参数、完整可信部署描述不足，以及公开原型的测量窗口/异步响应/队列同步需要进一步核验；不把原型不足表述成已执行的攻击或普遍推翻CC。

直接引用CLOUD2024 readiness、前述Hopper报告、ML with Confidential Computing SoK、AlpaServe和Clipper等。前述Hopper v4已经独立完成；CLOUD2024仍只有正式元数据与IBM官方页，不重复计完成。后续更贴近项目的CCA GPU及可信I/O候选仍按完整原文和固定artifact标准推进。

记录：改动目的｜补充机密GPU多模型装卸、调度与可信完成语义；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整6页/22参考文献、论文时期固定树及限定源码静态阅读；run-id、命令、退出码与日志｜无硬件run-id，batch45获取/限流/超时和发布核验保留；保留/撤回/待验证｜保留独立报告，原始图点、完整数据重算及安全部署未验证。未改运行代码，无新增性能测量。
