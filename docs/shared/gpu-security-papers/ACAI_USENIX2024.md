# ACAI：设备身份、CPU–DMA 映射一致性与可信加速器组合

研读日期：2026-10-27。依据 USENIX 正式原文，重点 §§5–10 的不变量、设备生命周期、映射和实验。阅读边界包括公开 artifact 的结构及少量已有源文件；不声称完整源码审计、设备证明复现或恶意共享攻击验证。

## 1. 书目信息和来源

| 项目 | 内容 |
| --- | --- |
| 标题 | ACAI: Protecting Accelerator Execution with Arm Confidential Computing Architecture |
| 作者 | Supraja Sridhara、Andrin Bertschi、Benedict Schlüter、Mark Kuhne、Fabio Aliberti、Shweta Shinde |
| 会议 | USENIX Security 2024，3423–3440 |
| 论文主页 | [USENIX](https://www.usenix.org/conference/usenixsecurity24/presentation/sridhara) |
| 正式原文 | [USENIX PDF](https://www.usenix.org/system/files/usenixsecurity24-sridhara.pdf) |
| PDF SHA256 | `56a6244e47cd7ae90fef945603160ac38d2f13dd974f0989d0099382dc20c1b9` |
| 作者实现 | [sectrs-acai/acai](https://github.com/sectrs-acai/acai) |
| 本轮固定主提交 | `490966daf6f3be8798db2de99e2ecdce4deccd0e` |
| 阅读范围 | 正文 §§1–12，重点 §§5–10；未将扩展版额外实验视为本篇已核验内容 |

## 2. 问题：两个可信端点并不自动构成可信系统

CPU Realm 可以保护 VM，GPU/FPGA 也可以有自己的 TEE，但两端之间仍可能被错误设备身份、Host 改写 SMMU、非法 CPU/DMA 别名或物理 PCIe 攻击破坏。

ACAI 的主要贡献是把 CCA 的 CPU 保护原则扩展为设备侧可检查不变量，再实现身份、归属、映射及证明流程。它主要面向云端“VM加专属设备”的粗粒度分配，而非移动应用频繁共享集成 GPU 的驱动服务模型。

对本项目最重要的是一致性原则；不需要照搬外部 PCIe 加密或硬件 Stage-2 才能采用该原则。用户已设定可信 Proxy 软件解析 IPA→HPA 并合成合法 Stage-1，研究应证明该合成过程和生命周期保持同样的授权语义。

## 3. 威胁模型和可信基

攻击者控制云提供方、Hypervisor、Secure world、恶意共租 VM 和其他设备，可伪造设备标识、篡改 SMMU、插入 PCIe 设备，或物理读取/注入/重放链路数据和探测外部 DRAM。

信任 CPU/设备/PCIe root port 厂商及其安全机制、Monitor、RMM、安全启动与证明。每个 Realm 内完整 guest OS、驱动、runtime、设备侧 kernel/IP 都在其可信计算基。它不是针对本 Realm 内任意恶意 GPU 程序的静态验证系统。

Host/云提供方 DoS 排除，侧信道与推测执行正交。正文声称 Realm 之间不能相互造成 DoS，但没有据此提供共享同一 GPU 下对恶意长任务的有界等待证明；设备独占条件和资源可用性结论必须一起引用。

## 4. 五项不变量及其精确含义

| 不变量 | 原文含义 | 对本项目的迁移 |
| --- | --- | --- |
| INVid | 证明后设备拥有唯一、不可伪造身份 | 平台设备身份与 RMM 认证的 Client 身份分别可信 |
| INVown | 设备只由一个 Realm owner 配置、设钥和使用 | 设备 owner 可为 Proxy；不将其权限扩给每个 Client |
| INVbind | owner Realm 与设备看到相同 GPA→HPA 映射 | 可信解析结果与实际 PTE/HPA 必须一致 |
| INVhost | 同一 HPA 不存在非法的多个 VM级 GPA 映射 | 避免未授权别名，明确允许共享的例外 |
| INVdev | protected region 的 HPA 不被多个设备非法重叠映射 | 设备/GPUVM 的访问必须有明确授权和共享关系 |

原文的后两项是面向其独占模型的强约束。项目存在显式 Client–Proxy 共享，不能机械禁止所有物理页别名；应将其细化为“所有别名均来自同一受保护对象及授权集合，权限和撤销一致”。放宽约束后需要重新论证，不可直接声称继承原证明。

设备 owner 与数据主体不同也很关键。Proxy 可以合法看到 A/B 的对象，不代表 A 的任务可请求 B 的 HPA；原始 Client 身份必须贯穿对象解析、GPUVM 建图和 job 提交。

## 5. 身份：RequesterID 是索引，不能独立作为认证

PCIe packet 的 RequesterID 可由恶意设备伪造。ACAI 将受证明设备的 RID 与 IDE key 绑定，可信 root port 检查/解密后，才把合法 Realm transaction 交给 SMMU，并设置正确的 `world_ext`。

Realm transaction 的 T bit 与 RID 处于 IDE 保护之下；普通事务不能仅自报 T=1 就取得 Realm 访问。密钥及 key mapping 位于 Monitor 可保护的 root port/SRAM，Host 不能重设。

协议在读取设备配置与证明前先完成 IDE key programming，避免证明后设备被替换仍继续获得秘密。设备报告应覆盖固件、配置、debug及其他外部接口状态，远端验证者负责检查期望值。

本项目的集成 GPU 不必通过 PCIe 复现这一过程，但应保留“可路由标识不等于实例认证”的原则。可复用 VMID、channel ID、job number 只有结合可信实例及生命周期，才不会混淆新旧端点。

## 6. 设备附加、证明与分离

Host 先准备设备及其 BAR/配置空间，把相关区域交给 Realm；RMM 验证实际 IPA→HPA、区域完整范围及归属，Monitor 重新扫描真实 PCIe bus、锁定设备身份并获取证明。RMM 把设备配置和报告结合到 Realm 证明。

不能只信 Host 提供的 BAR size、设备 bus 地址或“已reset”状态。原文将一部分配置核对交给远端验证者，附加流程也需要本地 RMM 检查，两个步骤作用不同。

**生命周期限制明确：创建 Realm 时附加，销毁 Realm 时分离。** 论文将动态分配、多租户虚拟设备的安全问题留给未来工作，指出共用翻译表/缓存状态可能形成攻击面。因此 ACAI 不直接提供本项目多 Client 共享协议。

分离删除 Monitor 的设备映射与 SMMU 状态，按 CCA 流程清理和回收 Realm 页。原文把设备清理成本视为与基线共同承担，不能由“无新增删除开销”推导任意 reset、固件擦除或 DMA quiescence 已经免费且验证完整。

## 7. SMMU：统一可信执行点与最小允许配置

Stream Table、实际 I/O Stage-2、请求响应缓冲和关键 MMIO 受 Root 保护。Host 继续承担普通资源管理，但所有 SMMU 改动必须经 Monitor 接口；普通设备映射及非关键字段仅在允许集合内更新。

RMM 检查 HPA 未被其他设备非法映射、IPA 在目标 stream 中没有重复映射，并核对 owner Realm 的 CPU Stage-2 存在相同 IPA→HPA。反向表用于从实际 HPA 查询归属，不能只对比调用参数中的两个地址。

Monitor 集中执行 SMMU 操作，避免 Host/RMM 并发直接编程全局配置产生竞争和重入。论文明确禁用 ATS 等可能让设备直接使用 HPA 绕过预期翻译约束的功能。可迁移原则是关闭或仲裁所有绕过控制口，不是凡加速特性都永远不可用。

本项目可信 Proxy 已成为统一控制点；应同时保护其实际 root、PTE、映射命令、MMIO、缓存和错误回滚，不能仅把 map ioctl 入口认证当作完整仲裁。

## 8. DMA 建立及全内存预映射优化

Realm OS 提供 IPA scatter-gather 列表、长度与设备ID；RMM 通过自身受保护 CPU Stage-2 翻译 HPA，再通知 Monitor 更新设备映射。页面已经属于当前 Realm，还必须显式赋予设备访问。

ACAI OPT 在 Realm 创建时给设备预映射全部 Realm 内存，运行中新增内存也同步，消除每次 DMA 的部分 RSI。代价是更长启动、更多 Root 页表以及更粗授权。

这种优化在整个 Realm 软件和设备程序可信时有意义，不能直接用于恶意 Client 的最小权限任务保护。本项目可缓存已授权映射或合批，但每次重用都要保持当前 owner/generation/permission 条件；单纯“曾经授权过”不足以允许新的 job。

## 9. 保护链路与完成语义的范围

主机 DRAM 由目标平台的 MPE/MEC 保护，PCIe由IDE保护，设备侧明文内存安全依赖设备TEE和集成条件。原型并未完整实现这些硬件链路能力。不能从概念图推导任意外部 GPU DRAM 天然具备不可探测性。

ACAI 核心不变量关注设备身份和内存，不提供 Devlore 式物理 IRQ 记录与注入验证，也未建立共享 Proxy 的“GPU事件→job终态→Client通知”绑定。因此物理设备经过证明、DMA映射一致，不自动使 Host 转发的完成消息可信。

对本项目，job终态、结果可见、DMA停止、映射已撤销、物理页可复用应分别表达；真实IRQ或Client ACK不能把这些事实合成一个布尔完成值。

## 10. 功能原型：FVP escape 是实验桥接

FVP运行RME/Realm，真实GTX460 SE与Xilinx VCU118连接到x86 Host。Realm中stub driver通过FVP进程页fault/escape调用Host真实驱动；GPU软件为Gdev/libdrm/Nouveau，FPGA为XDMA。

**escape绕过FVP的SMMU。** 作者另外记录真实事务并经test engine重放，使SMMU配置得到验证；用CPU/设备两个GPT模拟当时FVP缺少的RME-DA访问视图。这不是每个真实GPU事务都经过同一个实时完整CCA保护链的部署。

设备证明、IDE key programming、MPE不能在此原型完整建模，实际PCIe设备非PCIe5，因此未计一次性IDE成本。性能板另用ZCU102/Cortex-A53模拟EL2/EL3/GPT操作；作者明确说FVP指令计数不等于周期，也不声称结果等于真实CCA CPU。

这些限制与项目以硬件模拟测试的原则相容；应把目标设计成立性和原型覆盖范围分别报告。

## 11. TCB与实现规模

正文给Monitor新增1588、RMM382、guest kernel1734，共3704LoC；Host SMMU适配另有636行，helper模块320行属于实现组件，不能不加区分反复累加。

完整TCB包含既有Monitor/RMM/guest OS及GPU runtime、driver，正文基线约25.9M LoC，GPU附加栈约203k，FPGA相关约6.5k；还说明OpenSSL约835k未计入该比较。原文“25.9K”FPGA总量与前述共同OS组件口径不一致，本报告不把它作为可信的全系统总数。

ACAI明确不以缩小TCB为目标；形式化验证也属未来方向。其强项是可审查的组合原则，不应按“小于400行RMM增量”把完整驱动信任成本隐藏。

## 12. 评估、对照及数字审查

九项Rodinia2.1 CUDA Driver API任务；LUD/heartwall在原生也崩溃而排除，不能称11项全部通过。FPGA使用自编矩阵乘/SVD，工作负载与GPU不同。

六种配置需分清：Bv普通VM原版；Av普通VM加ACAI改动；Br原版Realm；Ae Realm加软件加密bounce buffer；Ap受保护设备内存；Ao全内存预映射优化。Ap对Bv包含CCA与ACAI两部分开销，不能全归因SMMU检查。

| 测量 | 原文结果 | 解释 |
| --- | --- | --- |
| GPU/FPGA总体开销 | 平均43.5%/12.1% | 对无TEE执行；模拟估计，非真实CCA产品测量 |
| 普通VM受影响Av对Bv | 平均3.8%/1.9% | 不等于Realm开销；hotspot约11.8% |
| 系统boot | 一次性+11.42% | SMMU结构转入Root等 |
| Realm创建 | 对Br+5.34% | 与无Realm启动是不同基线 |
| GPU/FPGA上下文切换 | 对Br+103.8%/+62.2% | 内存碎片和RSI频度影响，非统一应用延迟 |
| Ao对Ap | GPU平均26.05%、FPGA3.1%加速 | 伴随扩大设备授权内存与更多页表 |
| A53 kernel→hypervisor / hypervisor→Monitor | 0.89µs/0.77µs | 板端微测，不等于目标CPU恒定成本 |
| Monitor写一页 / 直接Host写 | 2.33µs/1.75µs | 接口切换与处理合计 |
| 经Monitor MMIO / 直接写 | 0.60µs/0.13µs | 不据此线性推算任意GPU服务 |

Ae对Ap的FVP指令倍率很大，GPU平均26.8倍，特定FPGA轮询甚至3271.7倍，反映软件密码学和频繁小传输。Table8板端估计约16–19倍，Graviton估计多数约10倍、个别32.2倍；正文“两数量级”概括与表值并不严格一致，应引用具体表值而非泛称100倍。

原文还将AES-CTR/GCM写为“256-bit block size”，AES实际块长128位，256位通常指密钥；本报告保留术语疑点，不把该措辞当一种新密码模式。模拟、估计和真实微测不可合成对本项目glmark的预期分数。

## 13. 公开artifact与本轮实际核验

主仓库通过子模块组织Host/Realm Linux、TF-A、RMM、kvmtool、Gdev、Rodinia、encrypted CUDA和构建工具。本轮取得固定主提交及非截断Git tree，解析TF-A gitlink为`cb989c41c6bec82f9e422ead53b3d9ca991c591d`，RMM为`affbb867af21baf9284f07bda16b0aa4ffe9a9f0`。Host/Guest Linux分别为`335e6ca6e56864383f5396d57f7c00d456bedbfc`、`1c083c5fc2bf74556f4a993a969b993502f17f76`。这些是本轮固定的公开输入，不代表已证明与发表时所有实验构建完全相同。

已有`.gitmodules`与SMMU源码缓存可辅助定位；本轮没有据此完成所有子模块、完整允许列表或证明协议审计。

尤其不能把普通`smmuv3_security_init()`的默认abort逻辑当作已经核验ACAI全部新增不变量。后续需沿固定gitlink的Realm DMA请求→RMM解析→Monitor检查→真实PTE/失效追踪，再分析失败回滚与销毁。未核实版本的旧缓存仅作定位，不作为本轮固定版本的实现证明。

## 14. 对项目的研究建议

将INVbind从CPU/设备两套页表一致，进一步落到**认证Client实例→可信对象→实际backing/HPA→当前GPUVM映射→job授权快照**。显式共享用授权集合表示，撤销必须更新所有别名及缓存；不因由同一个Proxy安装就跳过原始主体检查。

结合PORTAL的服务Realm和动态交接、CAGE的校验到启动冻结、MOLE的固件边界、PhantomMap的实际页生命周期、Devlore/CAEC的事件与端点保护，形成可验证的多Client任务生命周期。该组合仍需与更多相关工作比较，暂不宣称首创。

测试覆盖伪owner、HPA别名、同IPA重映射、授权缩减与提交竞争、close/reset后的旧事件、撤销未完成即重用页面，以及合法显式共享。性能分映射、提交、完成、通知、撤销测量，不能用全内存预映射掩盖权限粒度变化。

未改运行代码，无新增性能测量；无硬件run-id、无新增硬件PASS。
