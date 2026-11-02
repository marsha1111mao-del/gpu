# EnclaveX：CPU/GPU TEE 联合证明、应用密钥释放与评估边界

研读日期：2026-10-27。完整研读 8 页 arXiv v1，包括设计、威胁模型、全部实验和参考文献；核对 PDF 元数据并搜索匹配公开实现。未运行 SCONE、Trustee、TDX、H200 或任何攻击实验。未改运行代码，无新增性能测量。

## 1. 书目信息与实际版本

| 项目 | 内容 |
| --- | --- |
| 标题 | EnclaveX: End-to-End Confidential AI with CPU/GPU TEEs |
| 作者 | Robert Schambach、Quoc Do Le、Sergei Arnautov、Christof Fetzer |
| 实际所读 | arXiv:2606.31408v1，2026-06-30，8 页；没有确认正式会议录版本 |
| 原文 | [arXiv PDF](https://arxiv.org/pdf/2606.31408v1) |
| 入口 | [arXiv 摘要页](https://arxiv.org/abs/2606.31408) |
| DOI | [10.48550/arXiv.2606.31408](https://doi.org/10.48550/arXiv.2606.31408) |
| PDF SHA256 | `4a6f4ca0e0c3569c922e379c055289c76c6b2bf2e5797bd4b718d005bf268a6a` |

这是一篇实际联合 CPU/GPU TEE 的系统预印本，比通用 GPU 内存安全文献更贴近本项目端到端可信设备服务。它不是 CCA GPU 直通方案；Arm CCA 在文中是声称可兼容的平台，实际原型与测量为 Intel TDX 和 NVIDIA H200。

## 2. 研究问题：CVM 可信不自动等于应用受保护

把应用放入 CVM 可以阻止外部 Host 直接读内存，但仍需处理管理入口。作者关注拥有 Kubernetes 管理权限的管理员可以调用 `kubectl exec`，进入 VM/容器的管理路径，进而触及应用数据。

EnclaveX 将保护重心扩展到应用度量、策略及密钥按需释放：用户先验证 CAS，CAS 再检查 CVM、GPU 和应用证据，只有符合策略才向对应应用发放配置和解密密钥。Guest 内的内核模块负责应用证明，并关闭 Guest 的内存转储能力。

这类问题与本项目直接相关：RMM 认证 Client、设备固件可信和合法 HPA 映射是运行期基础，远程数据拥有者还需要知道“哪些实际组件、版本与策略正在执行这些保证”。

## 3. 威胁模型、可信组件及需澄清之处

§3.1 描述攻击者控制系统软件、OS 和 Hypervisor，拥有 K8s API 权限，并可操控网络和探测内存。侧信道、拒绝服务排除；文中还引用 SCONE 的 Iago 与部分侧信道防护，但没有逐项证明这些防护在本文 TDX SIM 路径均已部署。

实际设计依赖已度量 Guest kernel、应用证明内核模块、Guest GPU driver、SCONE runtime、CAS/策略以及 CPU/GPU 固件。CAS 在独立 TEE 中运行，由用户直接验证。

必须区分两个攻击者：拥有管理 API 和部分 Guest 管理权限的人；能够任意替换/控制已启动 Guest kernel 的攻击者。前者可通过禁用危险接口、策略和受约束内核得到防护；后者通常不能只靠同权限的一个模块及关闭 dump 来隔离应用。

论文没有展开对任意恶意 Guest kernel 的独立硬件隔离机制。其实际评估把内存管理交给 kernel，因而不能仅凭“process-based TEE”名称就认定 Guest OS 已被移出 TCB。这里是威胁范围与实现证据需要对齐，不是宣称已经构造绕过攻击。

## 4. 设计组件与证明链

| 组件 | 职责 | 依赖 |
| --- | --- | --- |
| CAS | 验证证据、保存策略、发放配置与秘密 | 自身 TEE、用户对 CAS 的证明与策略信任 |
| CVM 证明 | 验证启动环境、Guest kernel 和模块 | CPU 硬件证据、参考测量与验证链 |
| GPU 证明 | 验证设备及固件/CC 状态 | GPU 证书、nonce、OCSP、RIM 等 |
| Guest 内核模块 | 度量应用、使用获准签名密钥生成 quote | 模块和 Guest kernel 的完整性、运行期控制 |
| SCONE runtime | 应用配置、证明接口及秘密使用 | 应用/运行时身份与受保护执行环境 |

用户验证 CAS 并提交策略；CVM 启动时形成硬件到 Guest 的度量链；模块通过 driver 取得 GPU 证明，把 VM/GPU 证据提交 CAS。CAS 按策略发放应用 quote 签名密钥，随后应用测量被签名并送审，最后发放数据密钥。

作者用 VM ID 的策略扩展关联 CVM，并引用 SinClave 说明 singleton 性质。本文未完整展开多实例竞争、回滚、密钥撤销、克隆和崩溃恢复协议；不能只因存在 VM ID 就推出任意重放和并发复制均已排除。

## 5. 联合证明与运行期安全不是同一性质

GPU 使用 nonce 挑战、设备证书链、撤销检查和参考完整性清单；TDX quote 使用平台证明链。论文提出把这些证据统一交给 CAS，但没有给出完整、可检查的跨证据 transcript 定义。

对项目可借鉴的要求是：不仅分别验证“某个 Realm 合法”和“某个 GPU 合法”，还要验证所用设备实例、可信 Proxy 服务、Client 身份、会话公钥及配置确实属于同一次授权会话。否则两个分别正确的证明不能单凭并列出现建立关系。

这些是协议应说明的绑定条件，不是本文已发现的 relay 漏洞。设备建立安全通道、RMM 身份认证和项目实际所有权机制也可能承担部分绑定责任，需据具体实现分析。

启动证明还不能替代执行期页归属、GPUVM、映射撤销和中断完成检查。本文没有提出恶意 GPU kernel 的内存沙箱、多 Client GPU 页授权或逐 job completion 协议。

## 6. 原型与性能实验条件

作者使用 SCONE 与 Trustee；内核证明模块在论文中表示“将开源”。实际硬件是 Supermicro SYS-322GA-NR、双 Xeon 6900 系列、约 755G 内存、H200 NVL 141GB HBM3e、PCIe 5.0。

Host 为 Ubuntu 25.04，Guest 为 Ubuntu 24.04.1 LTS，QEMU 9.2.1；Guest 100G RAM、32 vCPU。推理使用 Llama-3.1-8B-Instruct FP8、Triton 25.01/2.54.0、TensorRT-LLM 0.17.0、GenAI-Perf，权重及 KV cache 用 FP8，动态 batching，KV 可用显存比例 0.95。

比较三个配置：普通 VM/GPU 非 CC；TDX CVM/GPU CC；加入 EnclaveX 的 TDX/GPU CC。TPS/TBT 测试输入输出均 128 tokens、batch 1–64；TTFT 固定 batch 1/输出 128，输入 32–1024。每配置请求数为 500×batch。

## 7. 性能数字的正确比较对象

| 比较 | 作者报告 | 应保留的条件 |
| --- | --- | --- |
| EnclaveX 对已有 TDX+GPU CC | 推理无显著额外开销 | 是应用证明层的增量，不是完整机密计算相对普通 VM 零开销 |
| TDX+GPU CC 对普通 VM/GPU 非 CC | TPS 约 35.0%–62.8% 差异 | 作者称 overhead，保留原百分比口径，不推算本项目保留率 |
| 同上，TBT | 35.2%–73.9% overhead | 小 batch 成本更明显 |
| 同上，TTFT | 11.2%–38.3% overhead | 输入变长后相对开销下降 |

无显著增量的关键条件是 SCONE runtime 使用 SIM 模式，依赖 CVM 的内存保护，不再加密应用内存；syscall 同步执行、不复制参数，内存管理交给 kernel。它不能与面对恶意 Guest kernel 的 SGX 隔离能力直接画等号。

作者把较大 CC 成本归因于 CVM↔GPU bounce buffer 的加解密和额外复制。该归因具有机制依据，但本文同时改变 CPU TEE 和 GPU CC 模式，缺少逐组件消融，不能把全部百分比严格分配给 GPU I/O。

这些是作者对一个模型、单一部署平台的结果；不是 GPU 共享、多 Client 并发或 Arm CCA 结果，也不能与本项目 glmark 分数直接比较。

## 8. 证明实验的关键删减

§5.2 的实际实验与前文“完整证明链、production-grade reliability”措辞之间存在重要距离：

1. 服务器使用 pre-production TDX 证据，Intel 根公钥不同，因此跳过 QvL 中显式验证 quote 的函数。
2. Trustee 未完全支持 H200 测量，未知测量项被跳过，只核对已知项。
3. 应用签名私钥按设计应在 VM 通过证明后由服务发放，但实验为人工预置。
4. 应用证明 benchmark 使用仅返回零的最小程序，未把完整 LLM 应用的度量成本包含进去。
5. Verifier、QGS、PCCS 与 CVM 位于同一 Host，证书材料预缓存，以排除外部网络延迟。

因此这组数据可用于观察特定实验路径的延迟，不能证明生产验证策略已全部通过，也不能当成“从未信任到取得 LLM 密钥”的完整首启耗时。

## 9. 证明延迟及统计疑点

每类证明重复 100 次。作者报告基础 TDX+cGPU 证明均值 1.1611 秒、标准差 0.0313 秒；应用证明均值 0.0147 秒、标准差 0.1508 秒；相加总计 1.1758 秒，增量约 1.27%。

均值相加在算术上成立，但应用阶段给出的标准差比均值大十倍以上。若这两个数来自同一组 100 个非负时长样本，其标准差上界也需要与样本数量相符；论文未提供原始数据，本次保留为应核对的数值/统计口径问题。

不能以约 1% 的均值增量忽略尾延迟，也不能把独立阶段均值之和当成已经直接测过的完整端到端分布。本文没有给出可复核的分位数、失败率和原始数据集。

## 10. 公开实现与复现状态

已确认完整 arXiv v1 和作者身份；正文引用 Trustee 0.17.0、SCONE、DCAP、Triton 等依赖，未给出完整 EnclaveX 源码、内核模块固定提交、CAS 策略样本及原始测量 artifact。

GitHub 按 EnclaveX 及 SCONE kernel attestation 检索，未确认匹配论文的公开实现；同名项目包含无关应用及协议，不能据名称相同认定对应系统。该结果也不证明不存在其他名称或后续发布。

本轮没有用通用 SCONE、Trustee 或 NVIDIA attestation 仓库替代未确认的 EnclaveX 修改，也没有声称审计了实际模块、quote 密钥生命周期、关闭 dump 的覆盖或 CAS 验证策略。

## 11. 与 PORTAL/CAGE/ACAI 的分工

| 工作 | 主要问题 | 对项目的作用 |
| --- | --- | --- |
| PORTAL | 可信 Realm 设备服务及管理 | 可信 ProxyRealm 的服务边界 |
| CAGE/ACAI | 加速器访问与 CPU/设备归属 | 实际页、身份及映射授权 |
| PhantomMap | 物理页和映射生命周期 | 撤销、复用与实际 backing 核验 |
| Devlore/SHELTER/中断攻击工作 | 中断来源、路由、管理状态 | 可信通知与任务终态之间的条件 |
| EnclaveX | 应用/VM/GPU 证明及按策略发密钥 | 数据拥有者如何验证整条运行环境和服务关系 |

本项目无需因原型使用模拟 CCA 就放弃这条主线；可信硬件、受保护页表/MMIO 和可信固件可继续作为设计假设。EnclaveX 的贡献侧重证明与部署策略，不能据 NVIDIA 安全通道代替项目 SMMU/Stage-1 授权论证。

## 12. 可加入项目的设计：服务证明与受约束密钥释放

已有的 RMM Client 身份、GPUVM、认证队列、私有快照、真实 fence、cookie/epoch 与 persistent IRQ127 保持为运行期基础。若项目扩展到远程数据拥有者，可增加一个明确的证明策略：允许哪些 RMM/Proxy/Client/固件版本、哪些设备/配置、何种调试状态以及何种授权接口。

建议会话证据绑定：Client 与 Proxy 的身份和测量、设备身份/固件、会话公钥、策略摘要、随机挑战及当前服务代次。密钥只向获准会话释放；重新启动、固件替换或服务代次改变后，旧证明与密钥权限如何处理应有定义。

这不要求每个 job 都重新证明或远程验签。可以按服务生命周期建立可信会话，再由已有映射和任务状态机持续执行授权；proof/attestation 与逐任务 completion 各自有明确职责。

## 13. 与中断和共享任务安全结合

EnclaveX 排除 DoS，且不提供逐 job 中断保护。项目不应把“CAS 接受 GPU 启动证明”解释为后续每次中断都来自当前任务。

仍需保持：可信 Proxy 依据真实 GPU 状态推进该 Client/该 cookie/该 epoch 的终态；通知只用于唤醒；Client 验证对应记录，结果可见后才能使用；reset/取消/撤销不能产生成功完成或污染复用对象。

如果论文需要一个新增安全设计点，联合证明与授权会话绑定可以作为任务隔离之外的系统扩展；若篇幅聚焦内存和中断，先把它写成信任建立前提与后续工作，不必为了覆盖文献增加完整控制服务。

## 14. 独立评价

值得借鉴的是明确指出管理 API 可以穿过 CVM 的部署边界，并把应用测量、GPU 证据和密钥释放联系起来。其弱点是威胁模型和可信 Guest 实现边界描述不足，实际证明实验有所删减，性能只验证了特定 TDX/H200/SIM 路径。

适合用作“端到端机密 GPU 服务需要哪些证明与策略”的近期材料。不能据它宣称 CCA GPU 保护已经实现、Guest OS 完全不可信已被处理，或完整证明链开销只有 1.27%。

统一记录：8 页预印本全文、PDF 元数据及公开入口核验｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增 PASS｜设计主张、删减实验、原型范围和项目建议分别保留。
