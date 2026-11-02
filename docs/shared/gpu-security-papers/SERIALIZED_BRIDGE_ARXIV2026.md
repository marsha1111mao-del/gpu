# The Serialized Bridge：GPU 机密计算的传输调度与可信 Fabric 边界

研读日期：2026-10-28。完整阅读 arXiv v2 的17页、§1–12及19条参考文献，核对6幅图及正文表格，视觉阅读10页。本篇属于直接 GPU 机密计算性能与部署研究，非 Arm CCA 架构、GPU 页授权或跨 VM 中断认证方案。未改运行代码，无新增性能测量。

## 1. 文献与证据身份

The Serialized Bridge: Understanding and Recovering LLM Serving Performance under Blackwell GPU Confidential Computing。Hang Yin、Kevin Wang，作者使用 Phala 邮箱。[arXiv:2606.23969v2](https://arxiv.org/abs/2606.23969v2)，v1于2026-06-22提交，v2于2026-07-09提交；[全文](https://arxiv.org/pdf/2606.23969v2)。PDF内部标题日期为May2026，不代替版本发布日期。本次未确认正式会议或期刊发表。

PDF为543004字节、17页，SHA256为 `f4657b923dcef2bc7dad386cad09fe40d2afdfe300f616526dd7ddd940c9aeb9`。取得完整HTML及摘要页交叉核对，逐页文字与10页渲染保存在 `build/cca-gpu-followup-20261027/` 的bridge batch85文件中。本报告是文献复核，表中均为作者测量而非本项目复现。

正文多次声称仓库README、补丁与原始日志可用，但本次PDF链接注释及HTML未找到匹配artifact链接。限定GitHub检索未建立新仓库对应关系；同组织 `hopper-llm-benchmark` 最后推送于2024年，不能当作这篇2026年Blackwell论文的匹配实现。因此没有源码审计、补丁正确性或原始日志重算的声明，也不声称全网不存在artifact。

## 2. 核心问题与结论范围

GPU CC开销不是一个固定百分比。GPU内持续计算、CPU与GPU之间受保护传输、框架调度以及多GPU Fabric有不同成本。作者观察到，在所测驱动/平台中，跨CVM—GPU的受保护通道按CUDA context出现串行瓶颈；普通框架依赖多stream重叠的策略可能反而增加关键路径等待。

本文价值在于把GPU CC中的“传输跨越”作为需要显式调度的资源，并通过同步调度、worker线程、持久context池和KV复用策略减少浪费。它没有证明所有GPU、驱动、所有CUDA异步API均必然相同，也没有通过驱动或copy-engine trace证明内部唯一实现机制。

## 3. 系统与威胁边界

系统是Intel TDX CVM加NVIDIA GPU CC。CPU TEE与GPU可信，Host承担设备分配、启动和Fabric管理；NVSwitch Fabric Manager（FM）与NVLSM仍在Host侧，其二进制、配置与当前路由不在租户已有证明链中。作者明确将这个缺口作为未解决问题，而非已实现的可信Fabric。

两类Blackwell载体分别为双RTX Pro6000 Server Edition（每卡96GB GDDR7、PCIe Gen5、无NVLink）和八卡B300 HGX（SXM6、每卡288GB HBM3e，观察到267GiB可用，两台QM3 NVSwitch，经CX7管理）。单GPU B300关闭guest NVLink探测以绕开Fabric gate，多GPU实验使用Fabric路径，两种配置不能混成相同实验。

B300记录Ubuntu25.10、kernel6.14.0-1008-intel、dstack0.5.9、driver595.58.03；Pro主机为双Xeon6730P、512GB内存，B300为双Xeon6787P、3072GB。B300为SM100支持使用较新的vLLM镜像，因此跨平台结果是机制背景，不能归因为只更换GPU硬件。

B300是有限借用窗口内保留的单次测量点，硬件已经归还；不是有独立重复及置信区间的统计结果。Pro有更长重复/扫描记录，H200补充实验在同一物理GPU做CC/TDX与普通KVM配对，但不能反向验证B300全部效果幅度。

## 4. 计算与传输分开量化

| B300微基准 | CC-off | CC-on | 解释 |
| --- | --- | --- | --- |
| BF16 8192方阵 | 1573.70 TFLOPS | 1569.81 TFLOPS | 约0.998倍，所测计算基本保持 |
| 单CUDA graph的96000次matmul | 7029.49 ms | 7037.80 ms | 时间约1.0012倍，非完整框架吞吐 |
| 1GiB HBM测试 | 3156.06 GB/s | 2879.09 GB/s | 约0.912倍，不能说所有GPU内操作零开销 |
| 单进程H2D / D2H | 55.48 / 57.38 GB/s | 11.26 / 12.08 GB/s | 约0.203 / 0.211倍 |
| 多进程H2D / D2H | 55.55 / 57.38 GB/s | 34.18 / 39.98 GB/s | 更多context改善聚合带宽，仍非原生等价 |

Pro单context多stream约4.9–5GB/s，增加stream不显著提升；24个context可接近35GB/s。32字节D2H的1到16 stream扫描中，CC约40→39μs，非CC约17→13μs。这支持所测路径缺少期望的重叠收益，不是GPU所有并发机制失效的证明。

作者在所测PyTorch pinned `non_blocking=True` 路径看到CPU仍阻塞，推断存在每次跨越的setup成本，约330μs来自guest计时与profile归因而非内部trace。禁用AESNI/PCLMUL使双向带宽40.4→5.5GB/s；仅禁用VAES/VPCLMUL下降约3.4%，说明密码运算存在但更宽向量并非该配置主要瓶颈，不能推广为加解密无成本。

## 5. 服务负载、profile与因果边界

作者的负载矩阵中，GPT-OSS120B约1193→1180tok/s（−1.1%），Qwen3.6-27B FP8约3302→2873（−13%），Gemma4-31B约2357→2022（−14.2%）；MoE的Qwen35B-A3B与Gemma26B-A4B分别约−24.7%和−27.6%。KV churn的Qwen2.5-3B warm TTFT为405.4→935.2ms（+131%）。这些不是同一负载的互相替换数字。

另一个128请求、并发128、输入输出各1k token的profile配置为5070→3729tok/s，约−26%；它与矩阵中的−13%不是矛盾的同条件重复。`aten::_to_copy` 的1138次调用均值31.7→1389μs，约44倍；均值差乘次数约1.545秒，接近作者报告1.561秒额外profile时间。合计事件耗时可能重叠，未经关键路径核查不能自动等同全部wall time的因果解释。

预分配copy的2628次调用仅约25.1→31μs，attention和辅助操作变化也小；每步六次新鲜pinned小传输成为重点。批量传输、持久buffer、删stream和graph等补丁单独只减少约毫秒量级，仍约30–31ms；因此不能用一项微优化解释完整恢复。

## 6. 调度恢复：必须固定比较基线

| 同一张调度比较表 | 吞吐tok/s | TPOT |
| --- | --- | --- |
| CC-off async | 4522 | 23.64ms |
| CC-on async | 3550 | 31.10ms |
| CC-off sync | 4153 | 26.56ms |
| CC-on sync | 4104 | 26.92ms |

CC-on由async改sync提高15.61%；以非CC async为gold，恢复差距 `(4104-3550)/(4522-3550)` 约57.0%。以相同sync策略比较，CC残余吞吐损失约1.18%、TPOT增加约1.36%。§5.4把dense写为“~100% async-mode penalty recovered”使用了不同反事实口径，不能省略baseline后直接写无开销。

MoE由3981→4296tok/s约+7.91%，作者归纳剩余约5%；KV TTFT由约935→413ms，相对405.4ms约剩1.9%。同步策略不是所有CC平台通用优化：补充H200中非CC async3497、sync3174，而CC async3106、sync3133，仅近似打平。

worker-thread drain把阻塞等待移出引擎主线程，使主线程可准备下一步。B300并发128时vanilla3629、sync3856、v10c3942、gold4653；并发512时5026、5004、5518、6020tok/s；并发256缺少vanilla与实测gold，不能填成完整配对结果。

重要算术不一致：摘要、§5.5 recovery hierarchy及limitations使用“恢复最高92%差距”，但并发512表格支持 `5518/6020=91.66%` 的gold吞吐保留率；以vanilla为起点，差距恢复率是 `(5518-5026)/(6020-5026)=49.50%`，以sync为起点约50.59%。“达到约92%基线”不等于“恢复约92%原差距”。图4本身标注距gold仍−8.3%，与前一种解释一致。

作者承认B300 v10c只有一次sweep、无独立复跑，称qualified；H200移植改善6–7%支持worker机制，但不验证B300幅度。论文另称qualified结果不作为headline，然而摘要仍有92%描述，因此保留两项限制：重复性与指标定义，不能用qualified标签消解算术口径问题。

## 7. 模型加载与生命周期摊销

GPT-OSS120B权重约59GiB、15 shards。B300 baseline287.09s，8线程56.82s，fastsafetensors36.34s，8 worker持久context池19.99s，预热加异步销毁后的最佳warm窗口8.36s。Pro对应287.41、66.79、36.83、20.46、8.80s。每shard临时建context的朴素变体仍253.66s。

八worker生命周期约创建5.2s、销毁3.9s、pinned分配0.3s，合计9.4s；将其移出测量关键窗口解释warm路径提升。287.09/8.36约34.34倍，但8.36s不包含完整预热与异步销毁，不能写成完整冷启动端到端快34倍，也不能把异步销毁当作资源已经安全归还。

图5附近“每个优化阶段跨平台都在5%内”超出表中数据：8线程66.79/56.82约慢17.55%，最佳warm8.80/8.36约慢5.26%；其他阶段约0.11%、1.35%、2.35%。总体机制可迁移与每阶段均在5%内是不同强度的结论。

## 8. KV策略与额外授权语义

Pro的reuse-aware offload以 `store_threshold=2` 只外溢被观察复用至少两次的块，报告spill从2.3GiB降至2.3MB、warm TTFT1615→544ms，约2.97倍。GiB与MB不是同一单位，不直接宣称精确1000倍；效果依赖所测复用分布，不证明阈值2普遍最优。

减少复制可以降低成本，却改变KV在CPU、GPU和缓存池中的驻留时长。项目若借用这一路线，仍需区分KV内容归属、prefix共享许可、租户切换清理与元数据泄漏；性能复用并不授予跨Client复用权限。这是本项目建议，不是本文已实现的CCA隔离机制。

## 9. 多GPU Fabric能力与未证明项

FM枚举15种partition定义：1个8卡、2个4卡、4个2卡、8个1卡形状，不是任意GPU子集，也不是15个可同时激活租户。激活/撤销约10–20秒。n=2中双向P2P成功、NV18健康、NVLink encryption mode，带宽约510.4GB/s；没有对应CC-off NVLink对照，不能算Fabric安全开销。

n=4有健康拓扑但CUDA负载受container-toolkit问题阻塞；早期两个并发n=4可证明/启动，未完成CUDA验证。两个并发n=2各只枚举自己的两卡且不暴露Host管理NIC，支持枚举与基本运行隔离，但不构成恶意DMA、路由篡改、reset与残留访问的完整隔离证明。n=8负载因FM缓存状态问题受阻，n=2/4 NCCL未测，失败和未执行均不能用健康拓扑替代。

论文称510GB/s比CVM—GPU桥高“两数量级”，按11.26GB/s约45倍，按多进程35GB/s约15倍；路径/方向不同，不据此建立精确加速比较。NVLink关闭时NCCL退化TCP约10MB/s是失败路径观测，不是正常路径的配对CC税。

租户可验证CVM与GPU证明、CC状态及guest可见拓扑，却不能绑定Host FM/NVLSM二进制、当前配置与路由。可信服务VM、签名路由和TDISP是作者的后续方向，非本文已完成。服务镜像可证明也不自动证明当前设备、partition/root与实际生效配置属于该服务。

## 10. 与 PORTAL / CAGE / ACAI 及项目的关系

本篇不替代PORTAL的可信服务Realm、CAGE的CCA GPU扩展、ACAI的身份/映射归属，也不提供PhantomMap式实际页生命周期检查。它补充第一部分“直通与共享性能”：跨可信域通知、提交、复制和等待应单独建模，不能假设增加线程/stream自然改善受保护路径。

项目仍以前提中的可信RMM认证原始Client、ProxyRealm控制SMMU、检查实际HPA/权限/生命周期并保护Stage-1表及root为基础；不能因为NVIDIA传输瓶颈要求项目改成其硬件结构，也不能因载体不具备Blackwell能力否定设计。可以借鉴测量分层和生命周期摊销，不能移植作者绝对吞吐或百分比。

对第二部分“内存与中断通信隔离”，本篇主要启发是把服务当前配置与授权身份绑定，而不是仅测量服务镜像。每个复用context/plan应绑定Client、设备实例与generation；跨Client复用前须完成撤销、可信终态、DMA静默和必要清理。context池效率不等于它可以跨身份共享。

## 11. 推荐新增设计与验证次序

第一，延续现有GPUVM、private plan/snapshot、native fence、cookie/epoch与IRQ127，围绕身份—映射generation—任务—权威终态—安全复用建立统一记录。保留IRQ作为可重复/可延迟通知，读取可信任务记录判定完成；本篇没有提供中断来源认证协议，不能用worker线程或async API替代它。

第二，在可信Proxy内允许批量提交、同Client持久对象和通知合并，同时分别定义提交被接受、设备完成、输出可见、DMA静默及资源可复用的状态。worker异步销毁只能移动等待位置；不满足静默条件的页、root、queue和context继续隔离，失败不得重新分配。

第三，把证明和会话绑定扩展到实际生效的设备租约、SMMU root/配置generation与必要固件身份。若未来涉及Fabric，再纳入partition/路由控制面；当前单GPU实现不预建没有调用者的Fabric框架。以上为研究设计建议，不宣称本次已经加入运行代码。

第四，性能实验应固定负载、版本、频率、并发与测量窗口，分别记录GPU执行、Proxy排队、CPU阻塞、复制、完成通知、资源回收及CPU占用。冷启动、稳态和预热context池分开；同调度策略比较安全税，再报告各自最优策略比较，避免“保留率/差距恢复率”混淆。

负例计划应覆盖旧epoch完成、重复/丢失通知、超时后迟到fence、Client退出、池容量耗尽和撤销期间重用；先定义安全预期，再在授权实验中验证。本次只提出计划，没有执行模型、攻击、VM、构建或硬件测试。

## 12. 结论和统一记录

本文直接支持“可信GPU路径需要按跨越、调度和生命周期优化”，但不证明Arm CCA映射授权或跨VM中断安全。项目最值得吸收的是保留授权边界的批量化/持久化、权威终态与安全回收分离，以及当前控制面配置的证明绑定；不是照抄禁用async，也不是把92%写成已恢复的安全性能差距。

改动目的：文献精读/算术及证据范围核对｜对照版本与glmark未测→本版未测｜分差及百分比不适用｜纯文档，未改运行代码，无新增性能测量｜证据：bridge85全文/HTML/10页渲染、publication-bridge回读及batch85审计，无硬件run-id｜保留；B300单次/qualified、匹配源码缺失、Fabric未执行项和FlexClave全文pending明确保留。
