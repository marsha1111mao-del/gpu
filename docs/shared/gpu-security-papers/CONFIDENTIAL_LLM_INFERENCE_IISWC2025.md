# Confidential LLM Inference（IISWC 2025）：CPU/GPU TEE 性能、成本口径与端到端保护边界

研读日期：2026-10-27。完整阅读作者公开15页正文与91条参考文献、无附录，14页演讲幻灯片文字；核对arXiv版本及正式书目，固定作者明确链接仓库并有界静态读取。本文是机密推理性能/部署研究，不是新的CCA GPU隔离架构。未改运行代码，无新增性能测量。

## 1. 来源、版本与研究范围

题名 Confidential LLM Inference: Performance and Cost Across CPU and GPU TEEs。作者Marcin Chrapek、Marcin Copik、Etienne Mettaz、Torsten Hoefler，ETH Zurich。正式IISWC2025，84–98页，DOI [10.1109/IISWC66894.2025.00017](https://doi.org/10.1109/IISWC66894.2025.00017)，Crossref题名/四作者/页码核对。

实际主读[作者公开PDF](https://spcl.inf.ethz.ch/Publications/.pdf/chrapek-confidential.pdf)，1678405字节，SHA256 `8ad189fe7f6bc0a8f8aaab965be842c007dd353fa2723ed568ac5ea428a20dce`，15页；[arXiv2509.18886v1](https://arxiv.org/abs/2509.18886v1)，2025-09-23，1728467字节，SHA256 `4634077516201e6943a2bf9e5af741d1a137fe0d5f2b7f748e9235ef897a81b6`。去空白及arXiv水印后两份提取文字完全一致，不把它们重复登记两篇。

[作者IISWC演讲稿](https://spcl.inf.ethz.ch/Publications/.pdf/IISWC25_confidential_llms.pdf)共14页，SHA256 `4d92a4f2ae26f69dcf217e72ba08ffbe86ca3a63ebc8a18361112c25a0e3e798`，全文文字已读；论文图表未逐像素渲染或重算，表I图标提取乱码不猜其每格含义，主要采用正文和可辨表格/图注。幻灯片用语与论文、代码不一致时分别标明。

论文明确链接 [spcl/confidential-llms-in-tees](https://github.com/spcl/confidential-llms-in-tees)，固定 `b3b4822440dfd405f96e1bd1bcfd58272a6dba23`，2025-09-30，完整递归树48项，未截断。选取14个blob核验长度/Git hash/SHA256并全文静态读取：README、gitmodules、GPU runner/parser/plotter、CPU runner及4个统计/价格脚本、SGX manifest、RAG compose/runner/parser；另全文静态读取上游vLLM v0.8.5的benchmark_latency脚本，未执行下载代码。

证据集中在 `build/cca-gpu-followup-20261027/` 的cllm、vllm和batch48文件。没有构建容器、下载模型、开云实例、运行GPU、修改实验机、执行攻击或重算完整原始数据。完整树不等于子模块内部审计；论文测量版本与所选公开提交的精确对应也未由原始run记录证明。

## 2. 研究问题和贡献

研究能否把完整LLM推理放入CPU/GPU TEE，以保护prompt、模型权重与运行数据，同时获得可接受的性能、部署复杂度及成本。CPU侧比较同类Intel平台上的SGX进程TEE和TDX VM TEE，GPU侧测Azure H100机密实例；最后把经验用于RAG检索工作负载。

主要贡献是测量与部署经验：AMX/IPEX、NUMA/hugepage、batch/input大小、模型驻留和价格共同决定“机密计算开销”，不能只看单个加密原语。它没有提出新的GPU隔离证明、可信IRQ协议或恶意多Client共享机制，也未证明推理框架被攻陷后仍保持不同用户的信息流隔离。

全文称TEE是当前唯一实用选择，是作者在所选平台/模型/性能需求下的判断，不是对所有MPC/FHE实现的不可能性证明。正文将MPC/HE一概说成不能处理完整性也过宽：纯HE不自动保证正确求值，但恶意安全MPC和可验证密码方案可以提供不同完整性保证，代价与信任前提另论。

## 3. 信任边界和未闭合的部署环节

SGX+Gramine把应用、LibOS及必要库放在可信边界内，TDX把Guest OS/服务也纳入；GPU机密实例还依赖CPU CVM、驱动、固件和GPU安全机制。TEE保护边界外的Host/管理员，并不自动防止可信边界内应用错误、被攻陷LLM框架、prompt注入或模型通过合法输出泄露训练数据。

正文把TDX描述为“hardened hardware-enabled KVM hypervisor”易产生误解：TDX安全边界不能简单等同信任整个Host KVM，受保护VM与TDX模块/硬件及Host职责需分开。SGX也不是所有文件默认获得机密性/完整性，Gramine manifest和密钥配置决定保护范围；TDX里LUKS仅加密磁盘也不自动给出所有存储完整性/防回滚性质。

论文讨论attestation，但没有给出本次所有实验均完成owner验证、测量allowlist、密钥释放、会话nonce、CPU/GPU绑定及远端结果认证的可核验记录。应把“在TEE模式运行”的性能评估，与“实际部署端到端安全协议已闭合”分开。

H100 HBM未加密是其物理攻击面/产品保护范围，不等于任何其他VM都可读显存，逻辑访问控制仍需分别讨论。NVLink/跨GPU通信是否可用且受保护也依具体模式、产品和云服务版本，不能把2025配置视为2026所有平台状态；Blackwell结论在本文属于文档预期而非本文实测。

## 4. CPU平台、框架和计时

| 平台 | 作者配置 |
| --- | --- |
| EMR1 | 双路Xeon Gold6530，每路32核，16×32GiB DDR5-4800，Ubuntu23.10，PyTorch/IPEX2.2.0，transformers4.35.2 |
| EMR2 | 双路Xeon Platinum8580，每路60核，同容量/频率内存，Ubuntu24.04，PyTorch2.3.0，IPEX2.3.100，transformers4.38.1 |
| 四类基线 | 裸机、普通VM、TDX VM、Gramine1.7 SGX；两种datatype为bf16与量化int8 |

初筛在EMR1单路Llama2 7B、输入1024/输出128、beam/batch1，比较HF、vLLM、IPEX及mixed datatype的llama.cpp。IPEX表现最好，论文称vLLM慢约50%、HF慢约100%；这不是相同datatype/所有后续版本下的通用排名，也不是GPU与CPU框架横比。

CPU正文每实验多次生成、至少1000输出token，分别测吞吐及next-token latency；主图吞吐batch6/beam4，延迟batch1/beam1，二者不是同一个SLO点。后续图8/9又分别取单路吞吐、双路延迟，不能把它们拼成同配置同时实现的性能组合。

作者在violin图排除Z-score大于3的约0.64%样本，以减少极端值对显示的影响；这不能证明生产尾延迟无问题，正文将波动归因内存加密也缺少完整因果消融。图12/13的throughput明确包含首token成本，不能与仅decode next-token均值的倒数不加说明地混用。

## 5. CPU主结果：低开销有适用条件

单路SGX约4.80–6.15%，TDX对裸机约5.51–10.68%，TDX对普通VM约3.02–7.01%；普通VM对裸机约1.82–5.38%。虚拟化税与安全增量需按各自分母表达，不能直接相加百分数当精确总差。

int8和bf16吞吐接近，但作者int8 next-token延迟约减半；TDX在低延迟路径上相对开销反而更明显。200ms/word作为人类阅读参照不能当所有token/语言/任务的统一服务SLO，更不能覆盖首token、排队和并发用户响应。

跨双路，正文TDX开销升至12.11–23.81%，图5的70B对绑定NUMA普通VM延迟还有bf16约+33.22%、int8约+25.68%。SGX多路最差可达230%，SNC从约5%升到42%；因此摘要“throughput<10%、latency<20%”不是全部测试点的最大界。

论文报告该时期驱动NUMA binding未正确生效、SGX呈单一NUMA节点，数据跨socket加密及内存放置放大成本；作者关闭SNC，不把这些历史版本限制视为所有未来TDX/SGX架构必然限制。70B容量与1/2 socket配置也必须保留，不能用小模型单路结果代表所有模型。

hugepage比较为普通VM 1GB预分配与2MB透明页；所测TDX没有采用请求的1GB页，造成额外TLB压力，约3.19–5.20%差异。README明确TDX实验用了默认页，正文后面“All VMs henceforth use1GB hugepages”要按普通VM配置及TDX实际行为解释，不能假设TDX已变成1GB映射。

## 6. AMX、层级成本与工作负载饱和

解码块占所测总时长99.9%；layernorm相对开销很高但仅约3%块时间，attention与linear-SiLU对绝对增加更重要。图7的约53.94%小层相对增加不意味着整模型慢53.94%；作者依据数据移动解释内存保护成本，未对每个硬件机制独立测量。

AMX降低所选bf16工作负载代价、总加速最高约2.6倍；int8禁用AMX出现最高约96%吞吐下降和约1700%延迟增加，作者解释为IPEX量化路径缺少对应高效AVX实现。图8所有标签基于AMX VM，不能把无AMX损失直接当TEE安全开销。

TCMalloc、适配OpenMP、batch和input可提高算术强度/减少数据移动；但batch增大同时增加单请求延迟与资源占用。CPU输入增大先摊薄保护代价，再因KV cache/cache/TLB压力转为memory-bound，2048附近并非总是更优；不存在“batch/input越大安全开销一定越小”的一般单调定理。

12条insight的核心可按目标理解：TEE实用性、TDX易部署、IPEX加速、单路小开销、虚拟化税、NUMA限制、hugepage限制、AMX收益、compute-bound较优、GPU小开销、未饱和GPU时CPU可经济、检索工作负载类似。它们是经验归纳，不是12条已形式化安全不变量。

## 7. GPU实验与可信传输边界

Azure机密NCCads_H100_v5与普通NCads_H100_v5，H100 NVL 94GB、40 vCPU AMD EPYC9V84、320GiB RAM、Ubuntu24.04、vLLM0.8.5。租用实例无裸机基线，因此GPU与cGPU比较还包含所选实例组合，不能把所有差值机械归因GPU加密本身，也不等同Intel CPU平台的同机基线。

Llama2 7B，固定128输出；图11输入128、batch1–512，降幅7.45/7.89/6.83/7.12/7.02/4.71/4.91/4.87/5.59/4.36%；固定batch4、输入128/256/512/1024/2048，降幅6.83/6.48/6.53/5.55/5.15%。整体有摊薄趋势但局部不单调，正文“4–8%”合理描述这组数据，不是对所有推理/训练/模型装卸的上界。

本文使用CPU CVM与GPU间经bounce buffer加密认证的命令/数据路径，主要开销是传输和kernel launch。驻留权重的小量输入输出较易摊薄；超显存的host offload、训练和跨GPU通信会改变路径。本项目授权建图及共享内存与此不同，不能将H100百分比套用Arm共享GPU或glmark。

正文谈跨GPU需经Host、缺少RDMA/GPUDirect及3GB/s对40GB/s等，是引用其他研究/云配置的数值，非本次单H100推理实测；IPsec最高90%也来自引用，不计成本主图里已测总差。CPU相对“更安全”须指明物理显存/互连和软件TCB目标，不能简单建立所有攻击下的统一安全排序。

## 8. GPU源码：吞吐与成本的分母不一致

`GPU/benchmark_vllm.sh` 使用真实模型名、bf16、输出128，输入默认仅128/1024/2048、batch1–512，10次测量。上游vLLM v0.8.5脚本默认10次warmup，用随机prompt token IDs、ignore_eos与固定max_tokens，计时包围整批 `llm.generate`，不含LLM实例初始化；包括prefill和decode，不是在线请求排队或每token延迟微基准。

`GPU/plot_GPUs.py` 对每次batch时间计算 `128 * batch / latency` 并取绘图统计，公式对应输出token吞吐。变量名latency_ms实际载入的vLLM值单位为秒，所选公式没有额外按毫秒换算，结果数值不因这个变量名而差1000倍。平均比值也不同于总输出除以总时间，后续需披露聚合方式。

`GPU/parse.py` 却把 `input_len * batch / avg_latency` 作为tokens_per_sec，按固定6.98美元/小时计算cost_per_million。若目标是论文所称“每百万生成token”，正确分子应为固定128输出；输入256/512/1024/2048时，这个脚本成本会分别低估2/4/8/16倍。输入128时数值恰相同，不能由此发现问题。

这是公开公式的静态结论，不是本轮重跑数据。CPU价格绘图里GPU成本以字典硬编码，部分键还有256/512/1024batch等默认runner未生成点；没有完整JSON/生成记录，不能证明每个字典值确由该parser产生，也不能直接宣布图13所有结论已被重算推翻。不过输入越长GPU成本反而下降的对比尤其需要按输出分母重新核验。

默认GPU runner不覆盖图11的256/512输入，plotter固定历史结果目录，而原始结果目录不在取得的48项树中。论文测量可有手动配置，但默认脚本不等于一键复现完整实验矩阵；本轮保留数据缺口，不虚构原始样本。

## 9. CPU成本估算与脚本统计边界

CPU本地EMR2实测吞吐结合GCP us-east1 spot的vCPU/内存单位价格，固定128GB，再与Azure GPU测量及小时价格比较；是跨平台性能/价格估算，不是同一云同日同服务SLO的实际账单。脚本价格没有完整日期/折扣/抢占及网络/持久存储成本记录，不视为当前报价。

CPU价格脚本用 `batch * 128 / time`，单位是生成token；EMR价格按vCPU0.01152和每GB内存0.001309美元/小时，另有SPR吞吐乘0.75的估算路径。硬编码SPR慢25%不是新增SPR测量，单独 `price.py` 的另一组机器标价也不是主图实际使用公式。

图12/13绘图按TDX样本 `cost_emr.min()` 取最低单样本成本来标相对GPU差值，而CPU柱图为样本聚合；“best configuration”与“best individual sample”并不相同。默认过滤还未显式同时约束所有input/batch/NUMA/model字段，parser列名model与plotter期望size不一致，原始CSV生成链需进一步核对。

正文“cGPU贵100%”以CPU为分母，反向CPU约便宜50%，不是CPU便宜100%；幻灯片“CPU TEEs can be100% cheaper”不照抄。batch128附近交叉、input256后CPU优势消失等定量结论受价格、SLO、统计及上节输出分母影响，当前证据足以提示复核，不能给出已修正的统一交叉点。

`CPU/run.sh` 参数网格虽然很大，但在首个成功组合后有 `exit 0`，默认只运行首项；同时run配置字符串仅参与标签，实际命令仍为同类Docker路径，需在对应裸机/VM/TDX环境自行运行。存在runner不等于所有基线和全网格已经执行；不能把其运行成功作为论文全部结果通过的证据。

## 10. SGX manifest与RAG：性能配置不自动是生产保护策略

SGX模板允许Host传argv/env、关闭ASLR、关闭invalid pointer检查，allowed_files覆盖广泛usr/opt/home目录，并映射untrusted_shm。trusted_files主要是入口、LibOS及运行库；未在所选模板看到模型权重/所有输入默认作为加密文件受保护的配置。allowed不等于可信或加密，不能因Gramine存在就宣称所有模型文件存储都被认证。

这些是基准原型的显式配置，不据此声称在作者部署中已发生攻击或所有SGX保证消失；也不执行源码中的安装、权限或容器命令。具体部署仍需测量allowlist、加密认证数据通道、可信文件策略和最小输入面，性能模板不直接作为本项目安全默认值。

RAG实验在TDX内运行Elasticsearch与BEIR的BM25、cross-encoder rerank、SBERT，图14对裸机时间增加分别约6.47%、6.03%、7.33%。这是检索/重排/编码评估时间，未展示检索加生成、网络、用户身份及输出发布整个服务链的完整SLO；“entire RAG pipeline”需按实际覆盖功能限定。

RAG compose设置Elasticsearch7.17.2、端口9200与Host网络/privileged容器，本轮未检查完整数据库认证/加密及部署网络边界；3份小文件不证明生产服务安全，也不推定暴露公网。唯一实际gitlink为BEIR `49d4338c4651eca5a14cf253cd9d6512000f1065`，gitmodules列其他组件分支但树无对应gitlink，不能称所有CPU依赖均已固定取得。

## 11. 对当前CCA GPU项目的具体启示

保持RMM认证原始Client、可信ProxyRealm统一控制SMMU、建图时核验对象归属/实际HPA授权/权限/生命周期并软件IPA→HPA合成受保护GPU Stage-1、其他设备保持硬件Stage-2的假设。硬件只是实验载体，不以H100或x86平台能力否定该模型，也不把它们性能结果当本项目预期成绩。

第一部分“直通/共享与性能”应按驻留、提交粒度、batch、输入/输出大小、缓存与页表策略分析。优化复用已有GPUVM、认证队列及私有plan/snapshot，保持检查时对象版本与实际执行一致；batch摊薄授权/通知成本时仍需Client公平预算，不能只用全局吞吐掩盖排队/饥饿。

第二部分“内存/中断通信隔离”把native fence真实终态、cookie/epoch和目标Client作为完成依据，持久IRQ127仅唤醒核验；TEE模式或低开销不能认证一次完成。区分准入、真实执行、输出发布、引用释放、撤销和回收；epoch拒绝旧通知不等于旧DMA已经停止。

模型权重、prompt、KV cache和输出对象都要有归属及允许共享范围，合法HPA映射不能防止可信框架把A的KV结果写到B的合法输出。复用已有授权队列和私有参数，明确任务/对象版本绑定及输出策略；若框架不在可信边界内，可结合GIFT的信息流研究，但语义标签不代替通用GPUVM隔离。

测量明确输出token、输入token、batch wall time、TTFT、decode latency、用户端延迟和成功/失败数，均保留原始分母。成本先用同一输出工作量和SLO，再考虑资源费；不对已完成样本之外的请求失踪保持沉默。性能图还要区分真实测量、估算和引用结果，本轮不引入新的测试运行。

## 12. 评价及后续引用链

优点是把完整机密推理的可行性、CPU AMX与GPU驻留、内存拓扑和成本结合，给出大量可追踪配置。局限是安全部署协议未验证、跨平台成本估算、部分摘要概括过强、公开原型的输出分母和默认复现链需要复核；这些不等于否认TEE可用，也不以性能基准替代设备隔离研究。

引用链包括SecPerf、Fortify Your Foundations、CLOUD2024 readiness、ISPASS2025 GPU性能剖析、ML with Confidential Computing SoK及CCA设计验证。已有报告不重复计数，未读引用不计完成；更贴近本项目的可信I/O、CCA跨Realm服务、中断安全研究继续推进。

记录：改动目的｜补充机密LLM CPU/GPU性能、输出成本分母与端到端保护边界；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整15页/91参考文献与14页讲稿文字、固定48项树/14 blob及上游vLLM静态全文；run-id、命令、退出码与日志｜无硬件run-id，batch48获取、文字比对和发布核验证据；保留/撤回/待验证｜保留报告，原始数据重算、成本交叉点、完整依赖及安全部署未验证。未改运行代码，无新增性能测量。
