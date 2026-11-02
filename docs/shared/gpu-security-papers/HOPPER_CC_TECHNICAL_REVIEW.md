# Hopper GPU 机密计算：可信启动、组合证明与安全交接的技术资料深读

研读日期：<date start="2026-10-27" />。状态：完整阅读 28 页 Hopper 演讲稿，核对 NVIDIA 官方威胁模型与证明流程，定向静态阅读固定版本 NVAT 源码。本文是技术资料专题，不冒充学术论文，也不替代尚未取得全文的原库 TGS-001。未改运行代码，无新增性能测量。

## 1. 来源、时间与版本边界

主材料是 **Hopper Confidential Computing: How it Works Under the Hood**，Phil Rogers（NVIDIA）、Antoine Delignat-Lavaud（Microsoft），GTC，2023 年 3 月，28 页。采用 [GPU-TEE-Papers 固定提交中的演讲稿](https://github.com/ConfidentialComputing/GPU-TEE-Papers/blob/8e367018ffbf209f62184423de9874c544d856c4/Hopper%20Confidential%20Computing-%20How%20it%20Works%20Under%20the%20Hood.pdf)，PDF SHA256：`4d7e3adc0664c1ea19771f6c0424209c412b37ad3a05b6e39823480f6a048d67`。镜像仓库不是作者 artifact，但演讲稿首页标明作者和会议，内容与官方材料交叉核对。

| 官方资料 | 本次用途 |
| --- | --- |
| [Confidential Computing Overview](https://docs.nvidia.com/confidential-computing/overview) | 部署模式及可信边界 |
| [CVM Trust and Threat Model，Dev](https://docs.nvidia.com/confidential-computing/virtual-machines/dev/threat-model) | 当前保护对象、信任依赖、互连模式和排除项 |
| [Attesting the GPU，Dev](https://docs.nvidia.com/confidential-computing/virtual-machines/dev/deployment-guide/attest) | GPU 证明、ready 状态及实际使用顺序 |
| [NVAT](https://github.com/NVIDIA/attestation-sdk/tree/11b2bfeb42a1158aa08744603ecb239ccb3d2265) | C++ 证明 SDK 的固定源码 |
| [nvTrust](https://github.com/NVIDIA/nvtrust/tree/a8090b65872a15bf0fd1f69f3d9b754b1be431b5) | Python 工具、Host 配置和迁移关系 |

官方网页采用 2026-10-26 留存快照；Dev 文档会继续变化，结论只对应该快照，不能回填为 2023 年全部已交付能力。NVAT 固定提交 `11b2bfeb42a1158aa08744603ecb239ccb3d2265`，nvTrust 固定提交 `a8090b65872a15bf0fd1f69f3d9b754b1be431b5`；两棵公开 tree 均未截断。

ACM Queue 的 **Creating the First Confidential GPUs**，DOI `10.1145/3623393.3623391`，本轮出版方与 Queue 全文入口均返回 403。该文章仍保持待精读，不将本专题重复计作原库 TGS-001 的完成。

## 2. 研究问题与项目定位

Hopper 将 CPU CVM 与 GPU TEE 组合，使不可信 Host 无法读取/篡改受保护工作负载，应用继续使用 CUDA。它同时说明内存访问限制、安全固件、可信命令提交、证明和设备交接必须形成完整生命周期。

本项目选择 Arm CCA 上的可信 ProxyRealm 共享服务，硬件仅作实验载体。Hopper 整 GPU 分配的支持范围不否定共享方案；比较价值在于明确共享方案需要新增哪些逐 Client 绑定和状态转换证据，不能直接继承整设备独占的论证。

## 3. 威胁模型与 TCB

当前 CVM 文档将 Host OS、hypervisor、VMM、其他租户排除在运行期可信边界外。可信依赖包括 CPU TEE 硬件/安全模块、guest 固件/内核/驱动/CUDA/应用、GPU 硬件与签名固件、验证服务和密钥释放策略。guest 管理员和 tenant 软件仍可接触保护域内数据。

因此这类 TEE 保护 tenant 免受基础设施管理员访问，不自动保护服务终端用户免受 tenant 或其模型软件访问。代码被测量、签名或批准，也不证明代码没有漏洞。

可用性、侵入式封装探测和故障注入等不在当前 GPU 威胁模型保证内，CPU 侧信道范围由 CPU TEE 定义；网络、存储和其他设备要独立保护。2023 演讲列举硬件故障注入对策，不等于当前对外威胁模型承诺抵抗所有物理故障攻击。

## 4. 关键区别：GPU 明文受硬件访问控制保护

CPU CVM 私有内存由 CPU TEE 保护；共享 bounce buffer 则存放经 guest 驱动认证加密的数据。GPU 的 Compute Protected Region（CPR）通过硬件访问控制阻断不可信入口，受保护显存内部可以保存明文。

当前官方威胁模型明确说 GPU memory encryption 不是其保护机制。不能把“Confidential GPU”写成所有 HBM 内容都在片外进行通用内存加密；应分别说明显存访问控制、CPU 私有内存保护和互连认证加密。

对本项目，同样应按实际威胁说明合法 HPA 的访问控制，而不是把缺少离散 GPU 式加密通道误判为隔离设计不成立。是否需要总线加密取决于共享内存是否暴露给威胁模型中的攻击者。

## 5. 入站、出站和命令路径

2023 演讲 §10–12 将绝大部分显存配置为 CPR，少量非保护区存放加密命令和 bounce buffer。PCIe firewall 阻断 CPU 对 CPR 及大部分寄存器的访问，NVLink firewall 限制 peer GPU 直接访问；DMA engine 跨保护区边界时走加密路径，计算引擎不能随意读写非 CPR 区。

HtoD 时可信 guest 驱动把私有明文加密到共享区，GPU DMA 读取并解密到 CPR；DtoH 方向相反。命令和 kernel 也经 Secure Work Launch 路径保护。数据加密并不能替代命令及执行配置完整性，否则合法数据仍可能被错误程序消费。

对 ProxyRealm，相关不变量是实际页表/根配置、关键 MMIO、提交命令及固件同时处于可信控制下；这些已包含在用户给定假设中。本轮不以 Hopper 硬件功能要求推翻该假设。

## 6. 模式配置：Host 可以选择，tenant 必须核验

演讲区分 Off、On、DevTools：Host/BMC 可写下一次启动使用的模式，reset 后才生效；运行中的 GPU 不能直接切换。证明报告包含模式，tenant 据此判断 Host 是否建立了可接受环境。

DevTools 允许性能分析，不能因其采用类似 CC 数据路径就按生产保护对待。当前威胁模型要求依赖严格调试限制的生产策略排除 DevTools；On 模式禁用 JTAG 和性能计数器，仅暴露有限健康管理信息。

可观察接口的减少可以缩小攻击面，但不是所有时序、资源争用和功耗侧信道都得到消除。对项目，应分别陈述访问隔离和观察信息的保护目标。

## 7. 启动与回收的先后次序

演讲 §14–15 给出的顺序是：配置模式→reset→固件清除内存、状态和秘密→建立 firewall→开放 PCIe→驱动建立 SPDM 会话并取得报告→验证→允许 CUDA 工作。退出 VM/驱动后设备锁定到下一次 reset；该演讲路径使用 persistence mode，并规定一次 GPU boot 只允许一次驱动加载。

演讲明确说清除完成前 PCIe BAR 被阻断，不论前后 CC 模式如何。这解释了安全回收为何不只是“停止发新任务”或“清空页表”：旧硬件状态必须无法继续影响下一任租户。

这些是 2023 路径的设计描述；不能凭它声称已经审计全部闭源固件，也不能把每项早期驱动限制当作所有当前版本的永久规则。当前官方文档仍要求使用受支持的 reset/reassignment 生命周期，停止工作负载不能替代该流程。

## 8. GPU 证明验证什么

演讲列出硬件身份与 fuse、安全配置、VBIOS/固件、驱动加载的 microcode、firewall 和 debug 初始化、运行模式等。验证器核对设备证书链、签名报告和 Golden RIM，证书状态还涉及 OCSP。

安全启动仅说明固件签名被接受；证明和 tenant 策略进一步决定版本是否可接受。有效签名不意味着没有被撤销的安全风险，也不意味着 tenant 接受其 debug 模式。

“可信依赖”与“本次测量覆盖”不同。guest 软件属于 TCB，不代表 GPU 报告已经测量了整个 guest 内核、应用和模型；部署者还需认证启动与工作负载加载路径。

## 9. CPU 与 GPU 组合证明

演讲的 Azure 路径把 AMD SEV-SNP、HCL、虚拟 TPM、UEFI 测量与 GPU 证明组合。guest agent 可把 GPU 证据测量扩展到 TPM PCR，远端通过 CPU 证明支持的 TPM 根和相关证据判断 CVM+GPU 环境。

当前官方文档要求核对 CPU 证据、每块分配 GPU 的身份/固件/模式/证书及批准的软件接收者，再向该接收者释放秘密。GPU 证明成功不验证 CPU TEE；CPU 证明也不能独自说明 GPU 状态。

对本项目，可借鉴的组合关系是 RMM 认证的 Client、ProxyRealm 实例、其当前设备租约、映射策略和固件状态应属于同一个受批准会话。这里提出的是项目绑定条件，不声称原演讲已提供 CCA Proxy–Client 协议或已排除所有证明转发攻击。

## 10. Ready 位不是授权证据

官方部署流程明确：证明成功不会自动设置 GPU ready；需要 CVM 用户显式设置，GPU 才接受工作。威胁模型又明确提醒 ready 状态本身不是 tenant 释放策略已满足的证据。

这区分了三个事实：设备报告可被验证、验证结果符合接收者策略、当前会话已获准运行。项目不应让不可信 Client 的 ready/claimed-owner 标记或共享队列状态代替 RMM 与 Proxy 私有授权记录。

同理，真实 IRQ 表明某个硬件事件发生，不自动证明特定 Client 的 job 成功。合法任务、原生完成、错误终态和输出可见性要依据可信记录关联，而非由可写状态位反推。

## 11. 互连模式和 MIG：不能混用不同年代的承诺

2023 演讲 §18 描述多 GPU NVLink 的加密 bounce-buffer 路径，§19 介绍 CVM、机密 MIG 分区、SR-IOV VF 的组合设计。这些内容是当时的架构介绍，不足以证明所有功能在任何 H100 软件栈均受支持。

当前所读 CVM 威胁模型给出的配置则是：

| 配置 | CPU–GPU | GPU–GPU |
| --- | --- | --- |
| 单 GPU CC，Hopper/Blackwell | 加密 | 不适用 |
| 多 GPU CC，Blackwell | 加密 | NVLink 加密 |
| 多 GPU Protected PCIe，Hopper | 加密 | NVLink 明文，需要评估 fabric/物理保护 |

同一文档限定每块 GPU 整体分给一个 CVM，并指出所述 CC 配置不支持 MIG、MPS、GPUDirect RDMA。不能将 2023 年机密 MIG 示意图作为当前已支持的恶意多租户共享证据；也不能把 Hopper PPCIe 的明文 NVLink 和演讲中的加密方案说成同一条路径。

对共享 GPU 研究，正确比较对象应是论文/演讲的设计能力和特定版本产品支持能力，各自标明，而不是以任一版本支持表限制研究可行性。

## 12. 公开工具与实际阅读范围

NVAT 是新的 C++ SDK，可经 C API、CLI、Rust 使用；固定 README 将其列为 nvTrust Python guest tools 的后继，并标注 CoRIM verifier 仍为实验性。nvTrust 固定 README 也明确 Python SDK/独立 local verifier 已弃用，包含 Host 模式配置及 PPCIe 工具。

本轮取得完整文件树，并定向阅读 NVAT 的 `gpu/evidence.cpp`、`gpu/verify.cpp`、`claims_evaluator.cpp` 及 CLI `attest.cpp` 中的关键流程，没有把树存在等同完整审计。静态核对结果包括：

- 报告构造验证签名，解析 SPDM 请求/响应；nonce 长度或内容不匹配返回错误。由文件导入证据时也检查调用者 nonce。
- local verifier 核对 driver/VBIOS 对应 RIM 版本，生成测量匹配、证书/OCSP 与模式等 claims；远端路径验证返回 token 并检查 nonce。
- claims evaluator 以 Rego 处理证据；默认 overall policy 要求非空设备集合及相应测量、证书状态等条件。另可加载 relying-party policy，体现基础校验与使用者接受策略的区别。
- CLI 即使返回 `RP_POLICY_MISMATCH` 或 `OVERALL_RESULT_FALSE` 也可保留 claims 供诊断，但最终仍保留失败码；“拿到 JSON/claims”不能当作证明成功。

某些旧版 opaque data 不含显式 GPU mode claim，代码会省略该字段。因此使用方需说明缺失字段和版本兼容策略；本次没有据此证明模式绕过漏洞，也没有追踪全部 RIM 内容、默认策略和实际设备组合。

没有运行 NVAT、签名伪造、nonce 重放或策略负例；GPU 固件、硬件 firewall 和驱动数据面不由这些用户态验证工具的公开代码完整覆盖。文件哈希与定向源码保存在 `build/cca-gpu-followup-20261027/nvat-code/`。

## 13. 性能与证据强度

本演讲提供架构、生命周期和云集成流程，没有受控 benchmark 表、完整基线或可复现安全攻击矩阵。关于 GPU 相对 CPU 的宣传性性能表述不作为本项目比较数据；本次也没有新增项目 glmark 或模型性能测量。

当前官方文档用于确定支持范围和保护承诺，公开 SDK 用于核对证明处理的具体路径。三种证据不能互相替代：SDK 能拒绝错误 nonce，不证明每条 DMA 都受保护；产品声明整设备隔离，不证明多 Client GPUVM 并发；受支持 reset 流程不证明项目自己的回收实现已通过验证。

## 14. 与现有文献的联系

相对 Graviton 的架构研究，Hopper 展示生产栈如何加入根身份、安全固件、可信提交和证明服务；相对 MOLE，它说明内部控制固件必须纳入可信链；相对 SGXIO，它再次强调真实实例/设备与证明接收者的绑定；相对 PipeLLM，它给出 CPU–GPU 传输性能优化所依赖的基础保护路径。

与 CAGE、PORTAL、ACAI 的比较应落在信任分工：可信驱动在哪里运行，谁能修改映射与 MMIO，设备身份如何归属，何时允许运行和复用。本项目已假定完整驱动在 ProxyRealm，因而应分析服务共享的授权与异步状态，而不是为缩小 TCB 强行改成影子驱动。

## 15. 对项目的具体建议与验证问题

第一，将已有 RMM 身份、设备租约、Proxy 实例、固件版本和隔离配置写成统一的会话准入条件。需要远程证明时再决定哪些可认证进证据；本地身份认证与远程证明的作用分别说明。reset、Proxy 重启或策略变化后，旧准入记录不得直接继承。

第二，明确两个相互关联的生命周期：任务的提交/执行/终态，以及设备与映射的授权/撤销/回收。当前已有真实 GPUVM、私有请求快照、原生 fence、cookie/epoch 和 RMM 持久通知；后续应证明这些记录在取消、reset、乱序通知和对象复用时仍指向同一会话，避免重复提出已有机制。

第三，规定结果发布和回收各自的充分条件。可信任务终态不自动说明全部旧事务已停止；设备停止后也要完成所需翻译失效与残留处理，才能把实际页交给另一 Client。Hopper 的整设备 scrub 可作为职责参照，不能据此要求每个共享 job 都全局 reset。

第四，围绕负例设计验证：有效签名但策略不接受的版本、DevTools、缺失 mode claim、旧会话证明或 cookie、复位期间迟到 IRQ/fence、证明失败但 ready 已被设置、撤销后未完成事务与新租户重用。它们是后续验证项目，不在本轮记为已测或已发现漏洞。

这些材料支持把第二部分进一步写成“GPU 内存授权与异步任务生命周期隔离”，其中中断是唤醒和事件传递环节，任务归属、完成判据与安全回收共同构成要论证的安全性质。
