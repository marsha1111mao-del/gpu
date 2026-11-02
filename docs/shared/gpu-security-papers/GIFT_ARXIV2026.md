# GIFT（2026 预印本）：不可信 LLM 框架下的 GPU 数据归属、流跟踪与异步一致性

研读日期：2026-10-27。完整阅读17页arXiv v1、120条参考文献，无附录；核对书目、版本与公开artifact线索。本文直接研究GPU多用户数据隔离，GIFT-CC结合CPU/GPU TEE，但不是Arm CCA原型。未改运行代码，无新增性能测量。

## 1. 书目、来源与发表状态

题名 Here is a GIFT: Enforcing User Data Isolation in LLM Serving via GPU Information Flow Tracking。作者 Jiacheng Shi、Xunjie Wang、Cheng Tan、Jinyu Gu；作者单位为上海交通大学IPADS与Northeastern University。实际阅读[arXiv:2608.25431v1](https://arxiv.org/abs/2608.25431v1)，2026-08-26发布，首页及arXiv元数据相互核对。

PDF17页、884280字节，SHA256 `ce19e82c81e0c41a7690d96d7ccb10996aeb00657caa47e4ac93dc7db0d8c11a`；DOI [10.48550/arXiv.2608.25431](https://doi.org/10.48550/arXiv.2608.25431)是预印本标识。本轮未确认正式会议/期刊，arXiv页无journal reference，不把它写成已录用系统安全论文。

正文到第13页结论，参考文献延续至第17页；取得完整PDF并严格解析，全文文字已读，未逐像素重建所有图形曲线。证据在 `build/cca-gpu-followup-20261027/` 的gift与batch43文件；没有安装依赖、执行下载代码、启动LLM/GPU或复现攻击。

## 2. 核心问题：合法 kernel 也能成为跨用户代理

普通GPU TEE保护服务免受Host窥探，未必保护服务内部不同用户。若vLLM被利用，攻击者可让本来合法的attention kernel使用另一个请求的KV cache，随后把结果返回给攻击者；每次访问可能都落在该服务获准访问的GPU地址空间内，页隔离未必看得见用户级语义混淆。

作者示例利用vLLM的RCE条件替换 `get_block_table`，令后续请求都返回第一个请求的KV blocks；Alice/Bob输入各自姓名，Bob也收到Alice的内容。这里是作者演示，不是本轮重现；具体CVE可利用性、框架版本和部署条件没有由本报告重新验证。

GIFT将大而持续变化的serving框架视为不可信控制面，让小型可信monitor独占GPU，CPU框架只组织密文token、调度和发送API请求；monitor负责解密、GPU内数据归属、kernel准入和按正确用户密钥加密输出。保护边界移到语义化GPU服务，而非信任所有框架代码。

## 3. 两种威胁模型及TCB

普通GIFT信任OS/hypervisor的VM隔离，不信任框架；monitor与GPU在受保护域，框架在外。GIFT-CC进一步不信任Host OS/VMM/管理员，将monitor放进CVM并使用支持机密计算的GPU，保护CPU私有内存和CPU–GPU传输。

两者均信任monitor、所接受kernel及其IFT规则、实际GPU执行保护和隔离配置。side channel、DoS和推理结果完整性明确排除；作者假定用户能发现严重错误结果，不能据此给出计算正确性保证。隐私隔离通过也不代表每条请求都会正确/及时完成。

GIFT-CC正文TCB包括约1M LoC裁剪Linux、未知规模CUDA runtime、1.4M LoC CUDA driver及5.6K LoC Rust monitor，另有CPU/GPU TEE硬件与固件信任。5.6K是新增monitor，不是整个TCB；普通GIFT还纳入hypervisor/KVM。

排除vLLM及其约3.6M LoC依赖有意义，但“组件稳定、接口仅32个、过去无公开CVE”等自述不等于内存安全或无漏洞证明。CUDA不同组件和CVE统计范围不能混用，本轮未独立核查作者的历史漏洞计数，不将其当作安全性结论。

GIFT-CC依赖远程证明建立用户到monitor的安全信道。论文介绍确认CC启用，没有给出完整证书/测量allowlist、挑战新鲜度、monitor版本和设备实例绑定协议或实现审计；部署时应核对这些条件，不能只依赖CC-ready状态。

## 4. 端到端流程和密文边界

初始化时monitor登记允许的GPU kernels及其规则，加载模型参数并标记为parameter-owned，同时持有用户密钥。用户端先tokenize，再按用户密钥加密；不可信框架可batch/chunk/schedule，但不能直接读取token、KV或明文输出。

框架提交密文、owner metadata及kernel参数；monitor选择密钥解密，记录GPU输入归属，按IFT规则检查是否发生不允许的跨用户混合，再提交允许kernel。结果返回外部前，monitor按其可信归属选择用户密钥，而非服从框架指定“把这块内容加密给谁”。

作者声称错误owner metadata只导致解密失败。第4.5节给出的具体token机制是64位token加64位随机nonce，经128位block cipher加密，解密后移除nonce；正文未说明附加MAC/AEAD或独立来源认证。随机化分组加密本身不自动产生认证失败信号，因此这一强表述仍需协议/代码证据；本轮没有据此构造跨用户泄漏攻击。

每token独立加密使框架能够追加、拆分序列；随机nonce避免相同token始终相同密文，EOS使用可识别的特殊密文以告知停止。长度、batch结构、时序和终止仍可见，不能把“密文与明文对框架等效操作”写成长度隐藏或全部元数据保密。

重放、重新排序、截断或同用户跨会话替换对输出正确性的影响，不能由随机nonce或“结果完整性排除”推定已经防住。若要保证本项目任务/完成语义，应复用现有seq/cookie/epoch与认证队列，不以token加密代替控制消息认证。

## 5. GPU 归属记录和静态流规则

归属按连续数据segment记录，避免每字节/每指令taint。两级索引先将GPU base address映射到tensor记录，再按ownership-related维度的下标映射到owner；记录包括shape、元素大小和决定归属的维度。parameter是可与某个用户计算结合的特殊公共身份。

例如B×H输入按行属于B个用户，仅需B条归属；相应bias+activation例的跟踪操作由作者所列7BH简化为2B+1。KV cache可按多维tensor中的block切片记录。收益依赖同owner数据聚集及已知布局，不自动适用于任意scatter/gather、用户自定义指针追踪或图形工作负载。

未被ownership覆盖的GPU内存禁止读取，释放tensor时清除归属记录，防止新用途直接读旧数据。逻辑不可读可替代某些立即清零需求，但前提是所有读/导出均经过可信检查；释放记录不能自动停止旧kernel或取消已排队的读写，物理页重新分配仍需处理在途引用。

静态分析先人工建立Information Flow Graph（IFG），将CUDA kernel转为C++并用KLEE验证实现不产生IFG之外的流，再生成规则。运行期核对base/shape、访问区域及允许alias，验证parameter标签，遍历source的owner一致后向destination传播；“合法kernel”不等于“任意参数组合都合法”。

目前是半自动流程：29个kernel families的规则库，需要人工IFG与CUDA→C++辅助脚本。完整CUDA symbolic executor或语义保持的通用transpiler尚无，原型没有完全自动化；KLEE验证结果依赖翻译准确性、模型边界、参数覆盖和GPU并发语义，不能直接称为原始GPU二进制的端到端形式化证明。

第6节明确：源码受限时可以用黑盒采样近似规则，但可能牺牲soundness。因此“完整静态规则且翻译可信”和“黑盒近似规则”应采用不同准入承诺；采样没见泄漏不能作为恶意参数下的非干扰证明。模型、kernel二进制/JIT版本及布局变化也要保持与规则的绑定。

## 6. 异步跟踪、多 stream 与可信完成

单stream先做IFT检查和归属更新，再launch kernel；CPU可继续处理下一条IFT，不等前一kernel结束。这里不是把同一kernel的授权检查放在其执行后，而是让之后的检查与之前的GPU计算重叠，保持逻辑状态O_i和实际内存M_i在相同顺序点对应。

GPU结果对外导出前明确等待device-to-host copy，使选择加密密钥时的归属状态与实际输出一致。这一发布屏障非常关键：提前更新标签可以隐藏开销，但不能让未完成、错误或其他代次数据按新标签被导出。

多stream时每stream一个CPU线程，归属记录增加last writer及last readers集合，以stream ID和sequence number标识kernel；每stream记录last completed。跨stream读取需前一个writer已完成，跨stream写入需先前readers已完成，write/write同理，阻止逻辑标签来自A而实际数据被B覆盖。

论文把同步操作前的kernel标记为completed，例举cudaMemcpy/cudaStreamSynchronize。安全实现需要同步成功返回、scope确实覆盖目标stream及真实依赖；仅发起同步、仅有launch顺序或收到一个IRQ都不足以证明完成。错误、取消、异步copy和设备reset如何更新last-completed，正文没有完整状态机及代码证据。

collective operation允许多个GPU通过通信buffer协作，依据传输发生在相应writer完成后、下一个writer之前，接受特定合法并发顺序；不能因此允许任意交错。CPU归属锁、分配/释放原子性、私有参数快照、GPU index-table副本与真实内容一致性，均是实现保持该推理前提所需的检查。

KV swap放在monitor私有CPU内存，避免把大KV明文交框架和反复加密；swap-in/out同样传播owner。缓存GPU index table副本以避免每次D2H等待，但可信副本必须与kernel实际使用的表同一版本，不能在检查后被其他线程/设备写改。论文未给出完整cache一致性和撤销协议。

## 7. 原型和性能：分别看平台与基线

monitor为Rust、32个接口；两框架各修改少于120行，用共享内存API remoting。29个kernel families覆盖列出的Qwen2.5、OPT及其他模型；这不是所有CUDA程序都可直接运行。论文第6节将Llama-3与参考100的Llama2023版本相连，书目存在命名不完全对应，未据此扩张实测模型。

非CC平台是8×A800/NVLink与Xeon Platinum3.4GHz；CC平台只有1×H100与Xeon Gold3.5GHz。vLLM用Qwen2.5-14/32/72B，DistServe用OPT13/30/66B，工作负载ShareGPT/HumanEval/LongBench，开启batch、paged attention及tensor/pipeline相关优化。

H100只有一张卡，DistServe的prefill/decoding放同一GPU，大模型66/72B未测CC；A800多GPU功能与H100单GPU机密计算不能合并成“多GPU CC已经验证”。正文提到NVLink保护属于硬件能力依赖，本轮没有对应多GPU CC实测。

| 范围与指标 | 作者结果及可比条件 |
| --- | --- |
| A800 GIFT vs native framework | 相同latency SLO下最大请求率损失至多约5%；高负载吞吐DistServe至多2.3%、vLLM至多4.1% |
| H100 GIFT-CC vs native | 相同SLO最大请求率损失约7%；吞吐DistServe至多6.7%、vLLM至多3.2% |
| H100 GIFT-CC vs baseline-TEE | 最大请求率约4%损失；吞吐额外损失DistServe至多2.4%、vLLM至多1.7% |
| speculative decoding | GIFT-CC vs native至多10.7%吞吐损失；vs baseline-TEE至多2.1%，不是10.7%全归因IFT |
| CPU / metadata内存 | 所测配置额外CPU低于124%即1.24核，额外记录内存低于130MB；不等于包含全部私有KV swap或完整CVM占用 |
| concurrency消融 | DistServe/ShareGPT/OPT13B/A800配置，细粒度并发较naive blocking吞吐提高12% |
| secure swap消融 | 不启用时对baseline吞吐损失11%，启用后1.9%；是损失率减少9.1个百分点，不是直接12%提速 |
| index cache消融 | 较不缓存提高50%吞吐；不是本项目通用GPU或glmark收益 |

图12为不同kernel聚合的execution/IFT时间，Y轴为log；作者说IFT可隐藏。第7.2.2节同时说明DecodingStageAttention在parameter size小于2048时IFT会超过kernel时间，多线程IFT仍是future work；不能写成每个kernel、所有形状下零开销。

token加密占请求时间低于1%、API redirection低于0.5%是这些配置下的作者测量，不能相加替代端到端吞吐损失。latency曲线接近及固定SLO最大请求率下降，与“所有负载零延迟增量”不是相同结论；论文未给每点原始重复数据、误差区间或本项目测试结果。

## 8. Artifact、验证强度与未闭合事项

arXiv页、完整PDF及其链接未给确认的核心artifact入口；参考vLLM/DistServe是框架依赖，不当作GIFT实现。GitHub精确短语 `"GPU Information Flow"`及组合 `GIFT GPU isolation`各0条、incomplete=false。候选作者主页404，不据此声称全网无代码；本轮未确认匹配公开仓库，因而无固定核心commit、源码安全审计或性能复现声明。

定向CCA/GPU OpenAlex查询出现read timeout，宽查询主要噪声，失败保留。仅从可靠全文中分析GIFT，不把检索结果里的其他题名/摘要计作完成。后续核验仍需取得monitor的所有准入路径、规则库、翻译验证产物、密钥注册、同步失败和生命周期代码。

安全章节为机制性讨论，没有给出完整非干扰定理或多stream精化证明；强结论需覆盖所有CUDA入口、动态加载、别名/越界、私有快照、参数共享、copy/collective、release/reset及输出路径。Rust降低部分内存风险，不能自动证明FFI/驱动和逻辑策略正确。

## 9. 与当前 CCA GPU 项目的结合

与PORTAL的可信服务模式最贴近：框架在外，可信服务独占控制GPU。但GIFT主要是同一服务内部的用户语义隔离，当前项目首先保障不同Client Realm/GPUVM边界；不能把UserID直接等同RMM认证的Client，也不应凭框架自报owner改变映射授权。

继续接受RMM认证原始Client、可信ProxyRealm统一控制SMMU，以及建图时验证对象/实际HPA/权限/生命周期、软件IPA→HPA合成受保护GPU Stage-1、其他设备Stage-2的假设。GIFT提示：物理页访问已授权之后，共享服务中的对象/任务及输出归属仍需保持，内存授权并不是所有数据隐私问题的终点。

对通用GPU共享，优先沿已有GPUVM、认证队列、私有执行计划和对象权限做归属检查；不要求把所有shader实现LLM式静态IFT。若未来Proxy内再共享LLM模型/KV pool，可将模型标记为公共只读、用户KV和激活绑定已有Client/会话，给少量允许算子增加规则，作为单独受约束扩展。

最直接可用的是异步一致性要求：可信计划与真实GPU执行使用同一参数/对象版本；跨队列依赖以native fence和实际访问冲突为依据；真实终态、错误和输出可见性确认后，才按cookie/epoch发布完成。持续IRQ127仅唤醒检查，不从通知本身推导标签、任务或结果正确。

释放路径要等所有在途reader/writer与copy结束，清理归属和映射后才重新授权。reset/取消同时废弃对应代次的逻辑元数据和未发布结果，不能只增epoch却让旧DMA继续写新对象。本轮是设计分析，不声称当前代码已实现GIFT规则或完整跨stream安全证明。

## 10. 评价与引用链

贡献是把“保护GPU服务免受Host”推进到“保护用户免受被攻陷服务框架”，以可分析kernel、segment归属和可信导出降低IFT成本。边界是较大CUDA/guest TCB、人工规则/翻译、黑盒近似的soundness损失、token认证描述不足和运行期失败/撤销状态未展开；这些需分别验证，不能用端到端小开销替代安全证据。

引用链直接连StrongBox、CAGE、ACAI、HIX、GEVisor、Honeycomb和PipeLLM；新增候选GPU Taint Tracking（ATC2017）、GPUVerify、GKLEE及CPU–GPU CC readiness可沿原文另行研读。不把本篇120条参考文献自动算作已读或已发布论文。

记录：改动目的｜补充GPU用户语义隔离、静态流规则与异步发布研究；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整17页预印本及120条参考文献/有界来源核验；run-id、命令、退出码与日志｜无硬件run-id，batch43全文和获取记录保留；保留/撤回/待验证｜保留独立报告，核心artifact、翻译soundness和失败/回收路径待验证。未改运行代码，无新增性能测量。
