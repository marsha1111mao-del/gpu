# Blackwell CC Benchmark：提交与通信成本、异步完成语义及性能证据边界

研读日期：2026-10-28。完整阅读23页arXiv v2及7条参考文献，无附录；两幅图采用图注和对应表格，未逐像素核对。补充全文读取NVIDIA引用博客正文，核对关联公开PR、限定静态读取diff及3个完整blob。本文属于机密GPU性能研究，不是新的CCA隔离架构。未改运行代码，无新增性能测量。

## 1. 来源、版本和实际核验范围

题名 Benchmarking Confidential Computing Performance on NVIDIA Blackwell GPUs，作者Amean Asad、Ansgar Grunseid，`Confidential.ai`。实际主读[arXiv2608.26575v2](https://arxiv.org/abs/2608.26575v2)，首次提交2026-08-27、v2为2026-09-01；PDF扉页写June2026，是稿件内日期，不代替版本日期。未确认正式会议、期刊或出版DOI。

[完整PDF](https://arxiv.org/pdf/2608.26575)为439825字节，SHA256 `6507d0d86503e17d94b1c4e71f3f386c451744716426ed2c79d7a6882a91719d`，严格解析23页，元数据和水印明确v2。摘要页原始HTML41491字节，版本历史与PDF核对；23页全部提取文字已读，不以摘要的1–3%代替完整实验曲面。

全文没有给出作者cc_probe、实验harness、原始逐次样本或cc-fixes精确commit。GitHub题名查询2项均为论文汇总；编号查询18项仅返回前10项，未确认作者artifact，不宣称穷尽搜索或没有任何公开代码。引用4只是SGLang论文，不是实际cc-fixes版本链接。

沿引用6取得并全文读[NVIDIA技术博客](https://developer.nvidia.com/blog/hardware-rooted-ai-security-that-wont-slow-you-down/)正文，HTML267777字节，SHA256 `64186ff61583a97da09e2549c61ca34f7dcda3b201df25cd78b18685586a4f80`。博客明确链接SGLang PR28251和FlashInfer PR3638；本轮取得完整19/2个文件的PR列表（无分页），固定head，读取下文列明的diff；这属于关联上游候选实现核对，不能证明是作者B200测量版本。

证据在 `build/cca-gpu-followup-20261027/` 的blackwell及batch50文件。本轮没有安装依赖、构建、加载模型、运行CUDA/测试/云实例/攻击、修改硬件或重算原始样本；只对论文表内数字进行算术复核。引用的NVIDIA安全白皮书新下载SSL握手超时，保留失败，不称已在本轮阅读全文。

## 2. 问题、贡献和安全边界

研究用同一物理Host、同一磁盘/模型和GPU的CC on/off对照，解释机密LLM推理为何有时只损失几个百分点、有时损失30–40%。贡献是把固定每次Host操作成本与按跨GPU通信量变化的NVLink加密成本分开，再用graph、异步读回和并行拓扑降低成本。

论文§1.3明确不审计任何安全属性，接受CPU/GPU TEE保证为前提；attestation和CVM启动成本不测，跨节点/RDMA与prefill-decode解耦不测。因此不能用这些结果证明恶意Host、多个恶意Client共享GPU、固件攻击或可信完成协议已经安全，也不能把稳态吞吐写成端到端入驻成本。

CPU TDX、GPU保护区、设备固件/驱动和受保护互连构成其假设环境。正文笼统写GPU内存也始终加密，但未提供独立显存物理保护核验；应区分受保护显存访问控制、CPU内存保护、PCIe认证加密和NVLink加密，不能由CC名称推出全部HBM片外都采用通用加密。具体物理攻击覆盖范围需另核官方威胁模型，本文不是证据。

同理，CPU quote和GPU attestation report都有效，不自动证明二者属于同一实际服务会话、客户端接受其版本或输出来自正确任务。论文描述GPU在证明成功后释放会话密钥，是背景机制叙述，没有提供本次所有测量的证明、密钥释放、CPU/GPU绑定或debug策略验收记录。

## 3. 实验平台与对照范围

| 项目 | 作者报告 |
| --- | --- |
| Host/GPU | 双路Xeon6767P、8块B200、NVLink fabric |
| 系统 | Ubuntu24.04.3、kernel7.0.9、QEMU11.0.0、OVMF2025.02、TDX SEAM2.0.14 |
| Guest GPU驱动 | NVIDIA595.71.05 open |
| 推理 | `SGLang0.5.13.post1`及未固定cc-fixes、vLLM0.21/0.22 |
| 训练 | Megatron-core0.19、`TransformerEngine2.18.0.dev0` |
| 模型 | Qwen3.5-0.8B/9B、Nemotron120B、Qwen3-8B、Qwen2.5-72B、MiniMax228.7B/6B、Qwen3.5-397B/17B及内部训练模型 |

CC on同时改变GPU CC模式和VM的TDX guest object，所以测得的是这组CPU/GPU机密模式的联合增量，不能自动拆成纯GPU硬件单因素。表内每一对尽量控制配置，但跨行框架、模型和量化随数周实验变化，作者也明确跨行比较只是方向性。

多GPU测量顺序为all-eight CC-on后CC-off，没有随机交错。作者每次clean boot，指出旧CUDA context可能形成100%利用率、低吞吐/高功率的stale状态，曾把实际约2%误测成16%。这一状态是测量条件，不能不经核验就把所有异常样本排为安全模式无关噪声，也不能把reboot解释成已证明设备安全清理。

CUDA event elapsed time在其CC路径可出现负数；Nsight/CUPTI内核追踪受限，作者使用Host syscall、wall time或globaltimer。提交级追踪另用debug模式，作者明确不能作为吞吐锚点。性能归因可使用诊断模式，但它的安全策略、计时与生产模式不同；“存在globaltimer”也不证明所有时间侧信道消除。

## 4. 两条成本轴及其适用性

PCIe批量数据由驱动共享bounce buffer加AES-GCM处理，作者用SWIOTLB trace与OpenSSL probe定位：8.25GiB D2H中17505次decrypt、合计8.44GiB，约517KB/次。每GPU安全会话当前CPU侧约单线程加密，不能仅增加Host线程线性扩展吞吐。这是所测软件栈观察，不是SPDM协议必然要求单线程。

命令提交经加密GSP-RPC路径，作者将额外Host launch延迟归于它；多GPU还增加NVLE通信代价。cuMulticast路径在其CC环境不可用，框架若把安全模式等同禁用整个融合kernel，会损失可用的multicast-free实现。作者用低libcrypto CPU占比支持“bulk crypto不是decode主因”，但没有取得所有固件内部逐阶段成本，不能仅凭Host ioctl把全部延迟唯一定位到一个硬件子模块。

可使用工作负载相关模型：额外时间由Host提交/读回关键路径、暴露的加密通信和其他残余成本构成。两项并非对所有异步系统严格独立相加：overlap、负载、并行拓扑和缓存会改变暴露比例。更不能把带宽下降百分比直接作为相同数值的通信时间增加上界；带宽下降d时固定数据量的时间增加是 `1/(1-d)-1`。

## 5. PCIe与提交微基准

传输4KB/64KB/256KB/1MB/16MB/64MB时吞吐0.13/1.86/4.93/7.21/9.41/9.64GB/s，表3 crypto ns/byte约0.767/0.057/0.068/0.081/0.095/0.096。该ns/byte不等于整条路径吞吐倒数，例如0.13GB/s对应约7.69ns/byte总时间，不能混用CPU crypto成本与传输wall time。小传输固定setup约3–6us，bulk约0.1ns/byte。

1/4/8/16个Host线程的H2D为10.2/10.2/7.8/5.4GB/s，D2H10.7/10.9/10.0/9.8。正文另处给CC H2D3.5对nonCC51.6GB/s，与这组约10GB/s条件未充分对齐，不能把不同测量拼成同一通用PCIe比率。权重/KV驻留可减少热路径传输，但offload、streaming和输入输出仍会触发它。

表5 kernel submission从3.45增到15.7us，绝对增加12.25us；总时长比为4.55倍，新增量是基线的3.55倍。表内“3.5×”若不区分两者会误读。sync-only1.62→1.67us，说明该微基准空同步增量很小，不意味着所有依赖复制的同步都免费。8GPU partition的launch另报告约31us，12us只能作为其单GPU情形估计。

cc_probe构造36层、每层5 GEMM加LM head、D2H sample，约181次launch/step。eager2644→6358us，graph2500→2589us，分别2.40/1.036倍；明显支持减少提交能降低开销。但eager增量3714us，并不等于181×12us=2172us，所给简单模型没有解释全部增量，不能称严格从第一原理精确预测全部成本。

vLLM0.22、Qwen3.5-9B、batch8，cudagraph1772→1179输出tok/s，eager246→127。由两项graph吞吐反算每step约4.51→6.79ms，增量约2.271ms；按12us/launch约189次，按12.25us约185次。论文用约2.28ms和约12us称“exactly185”，精度依赖舍入，也缺独立提交日志；可作为量级吻合，不能作为精确计数证明。吞吐下降约33.47%对应step时间增加约50.30%，两种百分比必须保留分母。

## 6. NVLink表格与通信结论

| 测量 | CC | 非CC | 表内或计算解释 |
| --- | --- | --- | --- |
| D2D CE单向read | 8070GB/s | 9170GB/s | 约下降12.0% |
| D2D CE单向write | 8278 | 9292 | 约下降10.9% |
| D2D CE双向write | 16411 | 18471 | 约下降11.2% |
| D2D SM单向read/write | 7693/7017 | 9388/8591 | 约下降18.1/18.3% |
| NCCL all_reduce | 156 | 185 | 数值下降15.68%，原表标约10% |
| NCCL all_to_all | 130 | 149 | 数值下降12.75%，原表标约10% |
| 短P2P write中位延迟 | 14.5us | 3.7us | 约3.92倍 |

作者说四块同NUMA B200，但未充分交代上述D2D多TB/s是哪些路径/方向聚合与计数方式，不能当单条NVLink链路速率。NCCL带宽是busbw还是algbw、消息大小/重复次数/同步条件也不足以完整复现；表头GB/s原样保留，不自行修正单位。

NVLE通信量和暴露通信比例是合理解释；但“所有成本都来自这两轴”“EP/DP基本免费”是比给出的样本更强的归纳。expert dispatch本身还有约4倍小消息延迟，不能从没有attention all-reduce推导没有跨GPU成本。可信多Client共享还涉及隔离、队列和公平性，本实验没有测。

## 7. 单GPU结果：不能跨模型声称严格消融

Nemotron120B Mamba hybrid强制关闭overlap且decode已graph，concurrency16/32/64时nonCC吞吐1195/1930/2637、CC1161/1884/2592，下降约2.8/2.4/1.7%。开启prefill piecewise graph显著降低TTFT，c16非CC1058→355ms、CC1114→380ms；收益两边都有，不是CC专属。piecewise还换了FP4 MoE backend，作者承认不是完全单因素。

Qwen3-8B bf16在未修补SGLang overlap-on条件下，吞吐3828/6931/11137→2513/4534/6805，下降34.4/34.6/38.9%；c64 TPOT5.48→8.28ms、TTFT259→409ms。作者解释CC复制在issue时阻塞scheduler，利用率74→57%，破坏compute/copy overlap。

修补后的表14却使用Qwen2.5-72B AWQ，c1–32固定1024in/256out开销−0.2至+0.6%，十种shape中位1.2%、最差6.5%。它支持该模型/栈能接近普通模式，但没有提供同一Qwen3-8B修补前后的完整控制表，因此“同一工作负载从39%变成小于1%”不是所展示数据直接证明的严格消融。表13的2%对39%也同时改变模型和强制overlap条件。

单GPU“残余硬件floor2%”不应成为通用常数：正文用11us/22ms解释约1.7%残余，前者只约0.05%，尚不足以解释全部。§7.3另引用TPOT8.68→5.63ms，和表12的8.28/5.48不同，应视为另一测点，不能直接拼接。

## 8. 多GPU、并行拓扑和统计

MiniMax-M2.7 228.7B/6B active采用NVFP4，production-default保留overlap及piecewise，并启用QK-norm融合、MoE runner和AR融合。表17固定1024in/2048out，concurrency1/8/16/32/64/128开销−2.4/−0.4/3.4/4.8/5.4/5.4%；这是吞吐下降曲面，不是所有并发固定约3%。

表18 c32的512/512、1024/1024、2048/2048、4096/1024分别7.4/5.2/4.3/3.9%；表20固定1024输入、c32，只变输出256/512/1024/2048得到14.4/10.1/7.0/1.1%。后者更接近输出长度的单变量对照，表18多项同时变不能独立归因输入长度。32k输入、2048输出、c16为−0.4%，仅说明该点差异落在噪声范围。

多数点只是随机数据单pass，作者给约正负2个百分点波动；同一1024/2048/c32在表17为4.8%、表20为1.1%，不能精确混用。canonical点每侧5次，两session中位2586→2493和2582→2510，对应3.6/2.8%，每侧标准差小于2%。重复数量有限且无原始样本/置信区间，不能据小负开销宣称CC会提速。

TP4 canonical中位2458→2420约1.55%，作者称约1.5%。随后94% TP8吞吐的例子却用2428/2571，来自另一测点，不能与中位2420和2493/2510不加区分地拼成同一配对。就同类中位CC吞吐比较，2420/2493或2510约97.1/96.4%，是否可比仍受session条件限制；不据此宣布“94%”错误或重算出通用更优值。

拓扑比较中MiniMax TP2/EP4/DP2四GPU、c32/256out，4k/8k/16k/32k输入开销9/12.6/11.4/14.5%；Qwen397B无attention TP、八GPU DP/EP对应11.1/8.3/2.2/1.9%。它们同时换模型、量化和GPU数量，不是“仅拓扑不同”的受控实验。减少TP可能减少all-reduce，但这两组表只能支持机制相关趋势，不能把全部反向变化唯一归因拓扑。

## 9. 训练、显存与能耗结论

表21 dense41B bf16 TP8每step13.95→15.8秒，增加13.26%；内部约43B MoE EP8为2.16→2.40秒，增加11.11%；dense delayed-FP8为14.5→18秒，增加24.14%。所以“八GPU训练10–13%”只适用于所选bf16/MoE点，不是全表上界，FP8的24%不能从概括中消失。

同一表FP8非CC14.5秒也比bf16的13.95秒慢，不支持简单的“非CC FP8缩短计算后显露更多通信”定量解释；可能配置不同或训练实现因素，但原始计时缺失，不能补造原因。无法只从利用率相同推出额外时间全部是NVLE，仍需更细分的通信/计算测量。

显存报告总可用约183GB，两种模式按整GB读数相同，CC却固定保留700MB做protected framebuffer分配。其结论应为固定较小容量成本，不能说容量完全无损；按可用容量比例分配KV时，cache size可不同，需要在容量临界点对照。

功率下降不等于能耗下降。以表12 c64的Qwen3-8B为例，687→543W下降20.96%，吞吐11137→6805下降38.90%；若这些平均功率和吞吐同期稳定，单位输出token能耗估算反而增加约29.35%。训练bf16的920W×15.8秒对960W×13.95秒约增加8.54%。这只是表内条件性估算，不是读取能量计的新增实测，却足以说明“energy unaffected”不能由瓦数推出；GPU功率也不是整机能耗。

## 10. 公开PR版本和限定代码范围

[SGLang PR28251](https://github.com/sgl-project/sglang/pull/28251)固定head `c5bee9bc1ba0b91f074414193bd78a9195b1c0f9`，19文件，841新增/91删除；[FlashInfer PR3638](https://github.com/flashinfer-ai/flashinfer/pull/3638)固定head `a1ed50b694ba39f58566ead2dbd227f2fee43465`，2文件、133新增。二者是NVIDIA博客所列旧PR，当前均closed但merged_at为空，分别指向后继31447/3870，不将merge_commit_sha非空误读为已合入。

本轮完整读SGLang的10份diff：CC_FIXES、overlap worker、scheduler、output processor、GenerationBatchResult utils、common检测、worker测试、comm fusion、server_args和model_runner；FlashInfer两份diff全文已读。未读SGLang其余9份diff或整个框架源码，未取得完整Git树，不声称安全审计完整或完整依赖已锁定。

3个新文件完整内容核验Git blob hash和SHA256：worker3461字节，blob `61de921a9f4d1e8253ce72790f088f7dc742442a`；CC_FIXES3717字节，blob `3c3c0010e78999e8080bbaef733f903d1e997c63`；CC_AUTOTUNER_FIX2536字节，blob `298d1ce401df14fb4c22948528f17e7792ee9792`。worker直接下载；两个文档raw下载超时，改从完整added-file API patch还原，Git hash精确相等，没有重启相同下载。

另外只读取后继PR元数据及body：SGLang31447仍open、head `58689da1137a53ff800ee150b9b36b5bd389f423`；FlashInfer3870已于2026-07-16 merged、head `1e55fda78f29d9c6b60ce9278118db8b5c0c03d1`。后者机制和控制值已有变化，未读其diff/完整代码；旧PR发现不能未经检查归咎于当前合并版本。旧worker测试含异常后done仍置位，测试存在不等于CI运行成功，本轮没有执行。

## 11. 关联代码：完成与成功必须分离

旧AsyncD2HCopyWorker接收src_ready event、copy_fn与done；先等producer event，在专用stream复制，再stream synchronize，最后设置done。这支持将阻塞移出scheduler，但并未把底层复制变成无需同步；实际消费者仍应等可信结果就绪，不能提前读CPU输出。

关键静态观察：worker捕获任意Exception只写日志，finally无条件done.set；output processor只等待copy_ready_cpu，没有在所读diff里读取独立error/status。于是done表示worker已结束尝试，不能一概当复制成功。全框架其他异常处理未审计，不宣称已证明可利用的跨Client泄漏，但这个局部接口确实没有把错误结果显式传回消费者。

队列无显式上界，shutdown排入None并限时join2秒，不保证超时后后台复制已停止；scheduler随后把worker引用设None。正常稳态可以工作，但取消、重启、异常和旧buffer复用要另定义drain/cancel/generation。其unit test验证顺序读回、shutdown和异常不挂住，没有覆盖所有失败后的输出发布或恶意多租户隔离。

CC检测是NVML ccFeature加env override，检测异常返回False，common注释还包含devtools；它用于性能路径选择，不能当远程证明或生产安全准入。文档“fail-safe”在这里至多表示退回普通性能路径，不证明配置或安全模式被验证；不能把环境变量1作为可信设备状态证据。

IPC融合patch显式绑定device/cpu group和comm_backend，避免与错误peer交换handle，是身份/资源组一致性的有用例子；但这仍不是CCA授权。低层融合默认oneshot针对decode-sized消息，分配参数/token上界/cleanup有单独路径，不能由kernel parity文字推导所有prefill/组切换均安全等价。

FlashInfer旧patch用JIT stamp kernel读globaltimer，event和CPU同步后计算差值；检测失败或JIT失败回退CUDA event。若event计时在目标CC环境本就不可靠，这种回退需暴露为未可信计时/禁用调优，不能继续把缓存视为已可靠选择。此为性能可靠性建议，不是证明计时器本身打破TEE机密性；后继3870只查元数据，不推定旧代码原样保留。

## 12. 厂商博客和TDISP展望的边界

NVIDIA博客使用HGX B300、Qwen397B FP8、SGLang0.5.12加所列PR，Host Ubuntu25.10/kernel6.17、Guest24.04.4/kernel6.8、driver595.71.05、CUDA13.2。与本文B200不同，属于相关厂商证据，不是独立复现作者数据。

博客表给1024/1024吞吐变化约−2.0至−7.5%、8192/1024约−1.0至−3.6%，c4–256；其TPOT也按negative delta列，但文本称最小开销，符号/相对性能约定不宜直接当真实延迟缩短。采集指标提TTFT而该结果表未展示TTFT数值，“up to98%”不是每个点都98%，不能用博客为所有1–3%结果背书。

论文把TDISP展望为GPU/NIC可直接安全分配并恢复GPUDirect。应分别看TDISP设备接口分配/状态管理、SPDM证明与会话、PCIe IDE链路保护、平台/IOMMU私有页DMA授权和peer访问支持；TDISP本身不自动给所有DMA端到端加密，也不保证RDMA或pinned buffer在所有TEE实现可用。作者明确未测跨节点，相关叙述保持为方向性假设。

## 13. 与当前CCA GPU项目的结合

保持RMM认证原始Client、可信ProxyRealm统一控制SMMU，建图时验证对象归属、实际HPA授权、权限和生命周期，软件IPA→HPA合成受保护GPU Stage-1，其他设备维持硬件Stage-2；页表、根配置、MMIO、固件和撤销回收按目标假设受保护。B200/x86不是用来否定Arm实验载体，而是提供可比较的边界成本与异步语义经验。

第一部分直通/共享及性能可研究每任务可信边界调用数、提交粒度、缓存/映射驻留、复制和通知暴露比例。复用GPUVM、认证队列和私有plan/snapshot做已授权batch，不因使用graph或驻留就跳过实际对象/页生命周期检查；避免多项一起变却只归因“中断优化”。本轮没有跑glmark，不将1–3%或12us迁移为项目预期。

第二部分内存/中断通信隔离应把“有通知”“处理结束”“执行成功”“允许发布结果”“允许复用内存”分开。native fence及可信status记录真实终态，cookie/epoch匹配原始Client、上下文与输出对象；持久IRQ127只唤醒消费该状态。复制或GPU异常也必须产生可验证失败状态，不能通过无条件done/ACK变成成功完成。

优化异步pipeline时保留私有任务描述和输出引用，直到producer执行、必要数据复制/验证及发布条件满足。撤销/取消/reset先停止准入并明确旧任务发布规则，再确认native fence或可信reset真正完成、旧DMA停止，最后撤图/清理/释放；更新epoch或join超时不等于quiescence。共享驻留对象还应防旧buffer、KV和context泄漏给下一Client。

测量分开吞吐下降、step时间增加、TTFT/TPOT、绝对延迟、成功/失败数和能量/输出。运行代码若以后做大幅性能变化，继续完整720p glmark门槛及项目记录格式、正确性/健康/资源恢复要求；这篇外部LLM基准不能代替本项目硬件回归。

## 14. 总体评价及后续工作

优点是强调同机配对、把框架调度与加密通信分开，并给出广泛shape和重复测量点；graph与异步读回路径有可追踪上游代码支撑。局限是作者artifact与原始数据缺失、多个强因果表述跨模型/拓扑、表内算术和能耗口径不一致、训练24%点被10–13%概括遗漏、安全协议与多Client隔离不在验证范围。

下一步若取得作者cc_probe/harness及精确commit，可核对模型实际launch计数、计时区间、误差分布和功率时间积分。SGLang后继PR和FlashInfer已合入版本应按独立版本继续核对；仅元数据不算源码完成，也不新增一篇论文计数。本文与Hopper性能、PipeLLM及Confidential LLM Inference形成性能与边界比较，不能替代PORTAL/CAGE/ACAI及可信中断主线。

记录：改动目的｜补充Blackwell CC性能机制、异步错误完成语义和证据分母审查；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整23页/7参考文献、厂商博客正文、10+2份旧PR diff、3完整blob及后继元数据；run-id、命令、退出码与日志｜无硬件run-id，batch50获取/hash/表内算术/发布核验记录；保留/撤回/待验证｜保留报告，作者测量版本、原始样本/能耗、完整框架与后继源码、安全部署未验证。未改运行代码，无新增性能测量。
