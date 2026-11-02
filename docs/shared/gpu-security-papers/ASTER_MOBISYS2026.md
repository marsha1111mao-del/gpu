# ASTER｜Android AVF 与 CCA 的安全模型衔接、服务准入和状态连续性

研读日期：<date start="2026-10-27" />。状态：16 页 MobiSys 作者全文（含完整附录）、项目主页、固定根仓库与构建指南文件树、指南正文及两份 AOSP manifest 已核对。未构建 Android、未运行板端测试。未改运行代码，无新增性能测量。

## 1. 文献、版本与研究位置

**Bringing Confidential Computing to Android**，Mark Kuhne、Supraja Sridhara、Andrin Bertschi、Nicolas Dutly、Fabio Aliberti、Srdjan Capkun、Shweta Shinde，ACM MobiSys 2026，Cambridge，会议日期 2026-06-21 至 25，正式页码 979–994，16 页；Crossref 出版日期为 2026-06-20。系统名 **Aster / ASTER**。DOI：[10.1145/3745756.3809250](https://doi.org/10.1145/3745756.3809250)。[项目主页](https://aster-cca.github.io/)、[所读作者全文](https://www.shwetashinde.com/publications/aster_mobisys26.pdf)、[项目入口](https://github.com/aster-cca/aster-cca)、[构建指南](https://github.com/aster-cca/instructions)。

本地全文 `build/cca-gpu-followup-20261027/aster-mobisys2026.pdf`，SHA256：`d8db78a6d2ba2b0f4dbf43c4fe27cd011cfb63c5ad6b1f475152049455e243fd`。以本篇正式 MobiSys 作者版本分析，不将较早 arXiv 索引另计一篇。本文直接研究 CCA，但不是 GPU TEE 或 GPU 中断实现；适合与 PORTAL、CAGE、ACAI 联合分析可信服务的完整生命周期。

## 2. 为什么有 pVM 隔离仍需要新设计

Android Virtualization Framework（AVF）使用可信 hypervisor 和 Stage-2 保护 pVM。作者关注的不是再增加一层映射，而是把 AVF 的应用、启动、存储和准入语义迁移到 CCA：CCA 可以证明 Realm 初始状态，却不自动实现 Android 规定的所有启动策略、可运行镜像限制、DICE 证书交付和持久防回滚协议。

论文将 Android 15 CDD 中 18 项要求分为兼容性、功能、策略、证明、内存数据安全、权限过大、防回滚七类。这里的“18 项满足”是作者对所选规范的设计映射，不是形式化证明，也不是所有 CCA 安全性质的枚举。CDD 有一项为 strongly recommended，不能将整张表统一称作 18 项强制安全定理。

## 3. 威胁模型与可信基

Android、normal-world hypervisor 及其他 normal-world 软件不可信；pVM 相互不信任。信任 Arm 隔离、加密及完整性硬件，信任 firmware、RMM、partition manager 和 secure-world 软件按规范实现。攻击者可进行 cold boot、总线嗅探或物理篡改；侧信道和微架构攻击明确不在保护范围。

全文采用支持完整性与 temporal freshness 的 Memory Protection Engine 作为假设。应按这一假设理解其物理保护结论；不能把它改写为所有 CCA 平台天然具有相同可选能力。本项目同样按既定 ProxyRealm 与受保护 SMMU/页表/MMIO 假设评估协议，不以模拟硬件缺少能力否定架构。

作者“AVF 不是 TEE”的表述使用其强调的威胁模型和物理保护标准。它不等同于证明可信 pKVM 的 Stage-2 隔离没有安全价值；两者的可信计算基和保护目标不同。

## 4. 四种放置方案

| 方案 | Android / pVM 所在世界 | 主要工程与安全取舍 |
| --- | --- | --- |
| O1 | Realm / Normal | 需要 normal 管理组件转发 Android 的生命周期操作；pVM 仍需 normal 内部隔离 |
| O2 | Realm / Secure | 双向世界隔离较直接，但要桥接两个世界的动态生命周期、通信和存储服务 |
| O3 | Normal / Secure | 保留 Android 放置；需扩展 secure partition 管理、动态证明及准入 |
| O4 | Normal / Realm | 可复用 CCA 的动态 Realm 生命周期；仍缺 AVF 特定策略、DICE 及防回滚接口 |

作者选择 O4，再形成 ASTER。未扩展 O4 的 18 项中，6 项原样满足、6 项需小修改、6 项需架构修改；选择并非“把 VM 放进 Realm 就全部解决”，也不是对所有使用场景普遍最优的硬件定理。

## 5. 双 GPT 与共享内存

正常世界执行使用原 GPT；Realm 执行使用第二 GPT，将不应访问的 normal 内存标为不可访问，只保留显式共享区域。它限制高信任域对低信任域的过大访问权，避免只保护 Realm 而完全忽略反向边界。论文沿用可信 firmware 的同步更新、锁和跨核 GPC 缓存失效机制来讨论 split view。

这属于 world/domain 视图的隔离；没有实现本项目逐 Client 的 GPUVM、GPU context、job 和 HPA 授权。**共享页得到双方同意不代表页内内容可信**：正文称 pVM 知道共享数据不可信，不能单凭这个意识就证明所有配置和数据都已正确验证。项目仍需已有的可信身份、私有请求快照、对象归属和使用时一致性。

## 6. 每 pVM 加密上下文与安全回收

RMM 登记 pVM 与可用 keyslot，为私有内存分配唯一 primary key；secondary key 使用 normal-world 固定上下文，使 pVM 能访问与 Android 通信的共享页。论文描述最多 `2^16` 个 keyslot/pVM 的模型；它是设计中的标识容量，不是实验已同时运行 65536 个 VM。

销毁时释放并清理 keyslot、清理对应内存，再允许归还和复用。独立上下文提供的身份不是 GPU Client/job 身份；相同 normal-world secondary key 也不提供共享消息发送者认证。项目不能用“内存已加密”替代 RMM 的原始 Client 认证和当前映射授权。

## 7. 启动准入与证明的不同作用

ASTER 的受保护 registry 存储被允许的 pVM 镜像策略；启动前由 RMM 检查刚建立的初始内存与许可签名/哈希是否匹配。registry 由设备制造或 firmware 更新路径管理。随后通过 DICE 延伸 boot certificate chain，向 pVM 提供证书和 sealing key，由 pVM bootloader 继续验证 OS、runtime 和 payload。

准入回答“该工作负载是否被允许启动”，证明回答“实际启动了什么”。两者均不能独立回答“这个服务实例当前是否持有设备、是否与该 Client 的会话绑定”。后者需项目自己的运行期设备绑定与身份协议；也不能因两个 Proxy 镜像哈希相同，就允许 Host 任意替换当前服务实例。

制造商 allowlist 是面向 Android 的政策选择，不是 CCA 的普遍要求。本项目若只需受认可的 Proxy 服务，可把策略限定于 Proxy 代码、配置和 firmware，不必照搬为禁止所有用户自行创建 Client Realm。

## 8. 防回滚、文件系统与强制退出

设计复用 secure-world SecretKeeper，登记持久状态哈希和版本。启动时，bootloader 通过 VirtIO 取得密文文件系统镜像，先复制到 Host 不能修改的私有内存，再核对可信持久最新哈希、所属 pVM 签名，成功后解密并本地挂载。运行期间明文不写回不可信存储。

关机时，pVM 卸载、加密、计算并签名新状态，更新可信存储，再把镜像交还 Host 持久化。强制销毁会留下标志，供下次启动采取恢复行为。**仅签名不能防回滚，最新可信状态记录才提供版本锚点**；内容快照同样防止核验与使用之间被 Host 改写。

论文未完整展开可信存储更新和 Host 文件写入间的 crash consistency、断电重试及并发多实例提交协议。若更新可信哈希后 Host 丢失新密文，拒绝旧镜像可维持防回滚但损害可用性；不能据此声称已构造越权攻击，也不能把强制退出标志等同完整恢复事务。

对项目，现有 cookie/epoch 保护运行期消息新鲜性；若跨 Proxy/平台重启的持久状态属于安全目标，还需明确实例 generation 的来源和重置条件。没有持久跨重启承诺时，不必为每个普通 job 强加持久写入。

## 9. 论文设计与原型必须区分

| 机制 | 论文实现披露 | 结论边界 |
| --- | --- | --- |
| DICE 与 boot chain | firmware/RMM 中实现 mbedtls 证书与密钥逻辑 | 平台没有硬件 RoT，第一阶段使用软件代替；是原型验证条件 |
| pVM 启动 | RMM 嵌入 bootloader，检查并测量初始状态 | 是可信启动路径，未据此证明所有制造商策略更新情形 |
| Encryption-Context | 约 206 LoC 的数据结构、选择和寄存器接口 | 作者明确没有实现可实际强制加密的硬件；实验不含真实内存加密/完整性代价 |
| 防回滚与恢复 | 正文给出 SecretKeeper 和文件系统协议 | 实现节未单列完整 LoC/负面实验；公开材料未取得完整后端，不能称已独立核验 |
| GPU 访问 / IRQ | 相关工作提出可结合 PORTAL、ACAI、CAGE | 本文没有 GPU 驱动、SMMU 共享或可信 job 完成实现 |

实现节给出的 2554 LoC CCA kernel 移植、469 LoC crosvm 修改、543 LoC bootloader 修改等是不同位置的增量，不是 ASTER 的完整 TCB 大小。论文明确把形式化验证留作后续工作。

## 10. 两套实验平台

功能平台使用 QEMU v8.2.0-rc4 上的完整 AOSP，x86 控制主机为 Gen5 Xeon、32 cores/64 threads、184GB。Android 约 20 分钟启动；QEMU RV8 指标为指令数，不能直接等同执行时间或真实处理器开销。

性能平台为 Radxa Rock 5B、16GB、OpenCCA。在 Linux v6.12 上用 Kotlin app、virtualization service、VM 管理工具和 pVM launch manager 重现主要 AVF 流程，**没有在该板运行论文要求版本的完整 Android**。正文把大核写作 Cortex-A74，应与真实 RK3588 的 A76 信息区分；本次未运行硬件识别来替作者更正实验记录。

软件基于 Linaro RMM v1.0-eac5、TF-A v2.10、CCA Linux v6.7-rc4 移植和 Android kernel 15-6.6；正文 AOSP 为 v13.0.0_r12，公开指南初始化写 r2，二者不一致。硬件模拟是合理研究方法，关键是按其实际实现与测量范围解释数字。

## 11. 基线与性能结果

四组：BN 为原生 normal pVM；AN 为存在 ASTER 改动但 pVM 仍在 normal；BR 为朴素 CCA Realm 移植；AR 为完整 ASTER。全部 pVM 为 1 core、1GB。BN→AR 是整体改动，BR→AR 才是 Realm 内追加 ASTER 的比较。

| 测量 | 作者报告 | 解释 |
| --- | --- | --- |
| 平台启动 BN→AR | 11.79s→12.64s，增加约 0.85s | 一次性 boot，包含新增 RMM、DICE 与 GPT/context 初始化 |
| 平台启动 BR→AR | 增加约 0.36s | 已有 RMM 的基线上继续增加 ASTER |
| pVM 启动 BN→AR | 正文报总计增加约 7.6s | 含 granule 转移、guest kernel/OS 与证明，不是应用稳态开销 |
| RV8，BN→AR | 平均 2.70% | CPU/内存 benchmark，未包含未实现的实际加密引擎 |
| LMbench，BN→AR | bandwidth 约 1.5%、latency 约 1.8% | 20 项系统/I/O 负载；同一世界前后约 ±1% |
| 四应用，BN→AR | 作者整体口径 2.20% | 不等于每项应用都只增加 2.20% |
| 四应用，BR→AR | 作者整体口径 0.98% | 不是包含启动的端到端成本 |

表 4 的 raw runtime 为 BN：11.33 / 9686.81 / 4068.60 / 2903.32，AR：7.45 / 9765.28 / 3994.49 / 3270.59，分别是 Microdroid test、PubKeyGen、OTP、Compiler。该表标题没有明确单位，本次不自行转换为 ms/μs。作者 2.20% 与表中平均 raw time 的比值一致，不等于四项归一化开销的简单平均；Compiler 单项约增加 12.65%，不能被总体均值隐藏。

OTP 示例初始化采用 trust-on-first-use，正文将基于 attestation 的预共享密钥/安全通道作为可替代方案；不能把后者写成该案例已实现。pVM 启动细分数字和语句的归因口径并不完全清楚，本次保留表 5 和正文总量，未重建原始分项统计，也没有复现任何性能结果。

## 12. 安全分析的证据与边界

论文论证双 GPT、可信 RMM 与 firmware 更新、初始测量、secure storage 和完整性引擎如何共同阻止所列攻击；主要是设计级分析。没有提供全面恶意 pVM/Host fuzzing、GPU DMA 故障注入、跨 Client 中断攻击或 crash consistency 的实验矩阵。

“本地证明发现恶意配置”取决于配置是否实际进入测量及准入检查；“共享映射已同意”也不替代数据校验。对项目应具体列出测量字段、绑定字段及检查点，不能借用这两句话将任意设备配置或共享内容默认视为已验证。

## 13. 公开 artifact 固定版本与复现限制

入口 `aster-cca/aster-cca` 固定 `8fbfef8e70ec24b5376cca92e6d499a5802d5fed`，完整树只有一份 README，是导航入口。指南 `aster-cca/instructions` 固定 `72cc282d2c2419ff2d1cd480cd3a3e7cb2d85a0b`，完整树 7 项，包含 README 和 5 份 manifest，**没有指南反复引用的 scripts 目录**。

本次阅读两份 README、`manifests/aosp.xml` 与 `aosp-missing.xml`。另外三份 manifest 的 blob 获取遇 GitHub 匿名 API 配额限制，未读取内容。AOSP manifest 内有固定依赖，但指南随后以浮动 `origin/vanilla`、`origin/aster` 分支替换多项仓库；不能据根提交就宣称所有组件均已固定。

作者账号的公开仓库列表包含 crosvm、Virtualization、Android kernel 等组件，但指南引用的 Linaro TF-A/RMM、Microdroid kernel、QEMU 和 u-boot 仓库未在该次公开列表中出现；不据此断言它们永久不存在。指南明确留有 edk2 下载 `<TODO>`、virtual-device 同步 TODO 和若干路径差异，并说明慢启动可能导致 payload timeout。这些是复现材料状态，不能改写为论文安全机制已被攻破。

未取得并核对完整可信 RMM/firmware 加密、双 GPT、DICE 和 SecretKeeper 修改。因此本次是全文与公开复现入口审计，不是完整代码审计；没有执行指南中的任何构建、删除、安装或设备命令。

## 14. 与本项目及 CCA/GPU 文献的关系

| 工作 | 与 ASTER 的关系 | 本项目可使用的部分 |
| --- | --- | --- |
| PORTAL | ASTER 明确引用设备服务工作，应用层 AVF 集成与设备服务互补 | ProxyRealm 的准入、启动链与当前设备授权实例绑定 |
| ACAI | ASTER 明确引用加速器 CCA 工作 | Client/设备/映射身份一致性仍由实际访问路径维持 |
| CAGE | ASTER 明确引用 GPU 扩展 | ASTER 未实现 GPU 并发共享，不能替代任务隔离设计 |
| PhantomMap | 实际页与映射生命周期的互补比较 | 启动时测量不代替每次真实 HPA 授权 |
| Sigy / WeSee / Heckler | 自定义服务接口与异步事件的相邻比较 | 证明正确服务后仍要授权每个副作用；不是 ASTER 展示过这些攻击 |
| Devlore / CAEC / TEEtime | 可信中断路径与控制权的互补比较 | ASTER 未回答 GPU IRQ 如何安全绑定原任务 |

本项目已有独立 GPUVM、RMM 认证队列与持久 IRQ127、私有请求快照、真实 fence、cookie/epoch。ASTER 对项目的增量启发是**跨启动、服务替换和持久状态边界如何保留这些身份与授权含义**，无需重新声称项目缺少基础隔离机制。

## 15. 可形成的设计和验证问题

服务准入：将 Proxy 的测量值、允许配置、GPU firmware/设备标识与会话准入策略关联；验证实际实例持有当前设备授权后，才接受 Client 请求。多个相同镜像实例需区分各自 session/generation 与设备所有权，防止正确代码被错误实例代答。

恢复协议：明确 Proxy 正常退出、强制终止、GPU reset、Client 撤销和平台重启分别如何终止旧任务。旧 epoch 的通知不能推进新 timeline；真实旧 DMA 停止、映射撤销/失效和页清理满足后才能复用。持久防回滚仅在项目承诺跨重启状态连续性时引入，与普通运行期 epoch 分层。

可信验证计划包括：相同镜像的错误 Proxy 实例、旧会话证明、策略更新后旧 Proxy 重连、reset 中 Client 重连、状态记录更新后 Host 丢失新文件、同一 Client 多实例并发恢复。分别观察拒绝越权、旧结果不可冒充新结果，以及中断丢失或存储丢失导致的可用性边界。以上为研究建议，尚未实现或验证，也不声称当前代码存在相应漏洞。

## 16. 独立评价与记录

ASTER 最有价值的是把体系结构隔离、启动政策、证明和生命周期衔接起来。它与用户“直通和共享实现／任务内存及中断通信隔离”的结构兼容：第一部分借鉴真实软件栈接入与成本分解；第二部分使用其身份和恢复思路，结合 GPU 完成及回收协议补足事件语义。

统一记录：CCA/AVF 论文全文、固定公开入口/指南与部分 manifest 静态研读｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件 run-id、新增硬件 PASS 或性能复现｜保留为直接 CCA 扩展精读，完整 Android/板端差异、加密未实施及 artifact 缺项明确保留。
