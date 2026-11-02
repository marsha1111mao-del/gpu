# LDR（NDSS 2024）：TEE 内驱动运行时、接口隔离与安全中断回调

研读日期：2026-10-27。完整阅读官方18页论文、80条参考文献及附录A–D，核对 DOI 与作者仓库关联，并阅读固定提交 README。它是 Arm TEE 可信 I/O 与驱动隔离工作，当前原型未支持 GPU，不列为完成的 CCA GPU 系统。未改运行代码，无新增性能测量。

## 1. 书目与全文证据

题名 LDR: Secure and Efficient Linux Driver Runtime for Embedded TEE Systems；作者 Huaiyu Yan、Zhen Ling、Haobo Li、Lan Luo、Xinhui Shao、Kai Dong、Ping Jiang、Ming Yang、Junzhou Luo、Xinwen Fu。NDSS2024，DOI [10.14722/ndss.2024.23009](https://doi.org/10.14722/ndss.2024.23009)。[会议页面](https://www.ndss-symposium.org/ndss-paper/ldr-secure-and-efficient-linux-driver-runtime-for-embedded-tee-systems/)提供[完整论文](https://www.ndss-symposium.org/wp-content/uploads/2024-9-paper.pdf)。

PDF1198043字节、18页，SHA256 `70d3df5489d4f84c4cfe09db1a6dd0292baaac95f0585f9e8168c352d1a8d1ca`。论文正文14页内结束，参考文献延续至16页，附录覆盖16–18页；附录B的 FIQ 回调是与中断研究直接相关的内容，没有只读摘要和性能结论。

论文结论直接链接 [SparkYHY/Linux-Driver-Runtime](https://github.com/SparkYHY/Linux-Driver-Runtime)，仓库 README 的标题、作者和 NDSS2024 信息对应。固定提交 `27a78dd11ad7da35711b8a6f6c55fa39ef30ce20`，根 tree `91b2aa90b721568ac4fdf677884ace9ab4ee1183`。本轮取得提交元数据和固定提交 README 网页；tree API403、raw README 超时，未取得并审计核心源文件。不能将仓库入口确认写成已验证运行实现。

## 2. 问题与威胁模型

OP-TEE 等紧凑 TEE OS 缺少丰富设备驱动，直接移植 Linux 驱动及其依赖成本高。LDR 提供编译后 Linux 驱动模块的安全世界运行时：复用 TEE 库函数，必要的 Linux 子系统操作回调普通世界，并把有漏洞的安全世界驱动限制在自己的执行域。

安全 OS 可信，普通世界 Linux 和驱动只在启动阶段可信，用于生成合法初始状态；安全驱动初始化后，普通世界允许被攻陷。安全世界驱动也可能存在内存破坏或 ROP 漏洞。目标同时包括防普通世界破坏安全驱动、防安全驱动攻击 OS 和其他驱动。

设备可通过 TZPC 配置为安全世界独占，DoS、侧信道、总线窥探、DMA攻击和冷启动攻击排除。启动可信及 DMA 排除都是实质边界：本项目若面对从一开始恶意的 Host，不能直接复用其 NW 初始化信任；项目自己的实际页授权、SMMU 和 CPU/DMA 写保护也不能被这篇的排除项替代。

## 3. 双生驱动如何降低移植成本

作者将 Linux 驱动函数分成初始化/配置、直接I/O、中断handler、VFS接口和工具函数。普通世界 NW 驱动协助初始化和子系统调用，安全世界 SW 驱动保留真实I/O、中断和必要计算；删除 SW 副本原来的 Init&Conf/VFS，加入 `sw_init` 与 `sw_probe`。

`sw_init` 向 LDR 注册驱动和状态，`sw_probe` 从已初始化 NW 状态复制子系统对象，并重新建立安全世界寄存器映射等字段。Linux 虚拟地址不能原样作为安全世界设备地址。初始化完成后设备归安全世界，普通世界副本的原 I/O/中断功能不再执行。

自动化利用 GCC 对无外部调用的 static 函数进行消除，但仍需人工识别函数和移除函数指针赋值。不能把“可自动删除”写成无需理解驱动的全自动隔离。设备依赖复杂时，移除 VFS 与 probe 也不保证所有跨域引用、异步任务和资源关系都已简化。

## 4. 库复用、RPC 与状态字段

LDR 使用安全 OS 包装函数替代 Linux 通用库函数，把特有的内核子系统调用转回 NW。原型总计支持74个依赖函数：39个库包装、7个时钟/延时类NW回调、28个新驱动管理函数。CPC 用于普通世界应用访问允许导出的安全驱动能力，普通 RPC 则服务 SW→NW 子系统调用。

作者用“安全 OS 结构通常更小”解释部分库对象空间兼容性，例如 Linux mutex20字节对OP-TEE12字节。空间足够只是条件之一，仍要满足对齐、布局、初始化、对象生命期、锁语义、IRQ上下文和所有可达使用者的约定；不能把几个驱动跑通当成任意 Linux API 语义等价证明。

状态字段分为 SW-exclusive 与 shareable。开发者给专有字段位图，编入驱动独立 section；每次回调只复制 shareable 字段，返回后同步可共享结果，保持安全字段不变。该方法避免直接泄露安全寄存器映射等，但字段可共享不意味着返回值及其引用对象可信。

论文§VII-A明确说返回值清洗“可以扩展”到调用验证机制，不能写成已经实现所有 Iago 防护。原型回调少且集中时钟/延时，作者主要把恶意行为归于排除的 DoS；推广到 GPU 分配、调度、长度、指针和设备配置时，需要重新证明参数、返回值、别名及实际资源归属，不能沿用这一归类。

## 5. IED 与调用门保护什么

每个驱动或相互依赖的一组驱动放入隔离执行域 IED，各有堆与栈。Arm DAC 给安全 OS、TA、IED gate 及各 IED 分配不同域；驱动只访问自己的 IED 和 gate。gate 进入安全 OS 时保存上下文、临时打开访问，返回前关闭；安全 OS 一次只服务一个 IED，避免同时开放多个域。

原生DAC有16域，其中0/1/2保留，3–15用于IED；作者引用 EPK/VDom 讨论扩展数量，没有在本篇评估任意多IED。互相调用的驱动需放进同一个IED，这会扩大同域故障范围。IED隔离单位不是GPUVM、Client或独立GPUjob。

加载器验签驱动，按 section 设置代码只读可执行、数据不可执行，页表位于安全 OS。每个依赖调用重定位到 gate，并保存 `<callsite, callee>`；gate 查表决定可调用目标。附录A以 IED 内 `malloc` 展示切栈与开关域的完整流程。

这是外部依赖调用的前向控制流约束，不是任意驱动内部控制流或全部参数语义证明。合法 callsite 调用合法 callee，仍可能传入错误指针、长度、资源或状态。gate 原子执行、DACR修改指令不可被滥用及驱动二进制中的危险指令处理都是信任条件；作者建议静态扫描，不能省略为“DAC自动解决所有ROP”。

## 6. 中断路径与附录B的关键内容

安全驱动初始化后，设备中断由 SW handler 处理。为防普通世界打断安全处理中断，原型从NW移除第4个核并专门处理安全中断；IPU end-of-frame 通过GIC配置affinity。它保障的是设备事件进入安全处理路径的安排，没有构造跨VM、跨Client的任务完成授权协议。

普通 OP-TEE `thread_rpc_cmd` 不能在中断上下文使用，作者因而提供 FIQ Linux Callback（FLC）。SW handler 的NW回调被hook；FLC保存FIQ寄存器，把callback地址和参数放进共享buffer，经SMC进入monitor。monitor设置FLC flag、保存NW上下文，并异常返回至NW的 `ldr_fiq_callback`。

NW解包并调用目标，结果写回buffer，再SMC返回monitor；monitor清flag、恢复原NW状态，转至 `callback_ret_entry`，FLC恢复FIQ上下文、把返回值放入R0，继续原handler。这个设计展示了“可信中断处理中再次进入不可信世界”的真实控制流，而不是纯SW闭环。

共享buffer及返回值仍是外部输入，callback目标、大小、嵌套层数、返回状态和当前实例都需可信绑定。一次FLC flag只能说明某条返回路径被标记，不能独自证明它属于正确设备/请求或未过期。若NW拒绝返回，这篇排除了DoS；专用核也没有消除这类依赖。

对本项目，需要分开证明物理GPU状态/真实fence、Proxy中的任务归属、结果写回、Client通知、ACK/重装和epoch失效。LDR没有评估这些多Client性质，不能据其“secure IRQ”推断虚拟完成通知不可伪造或不会跨Client投递。

## 7. 作者实验：数字及其条件

实机为NXP IMX6Q SABRE-SD，四核Cortex-A9、1GiB内存，OP-TEE3.10.0。表I列7设备，表III实际转换评估6种驱动：IPU、环境光、磁力计、加速度、气压和片上温度；OV5640 camera驱动留在NW，由SW IPU处理图像路径，不是所有传感链组件都进入SW。

| 作者报告 | 条件与解释 |
| --- | --- |
| TCB增量 | 原275586LoC；改69、增4947、删58，作者口径约1.80% |
| 二进制 | 557.1KB→588.6KB，+5.65%，不含DAC对齐padding |
| 子系统重定向 | 11.14µs；附录分解5.82基础+2.11调用校验+3.21状态同步 |
| CPC | 无参117.78µs，普通值参数140.02µs，指针140.29µs |
| IED对CPC增量 | 附录平均额外39.91µs；不能把它当总调用延迟 |
| MMA8451采样 | 默认800Hz；带IED800.03Hz，不带IED809.61Hz |
| 720p软件视频 | 原24.6FPS/0.9945×，LDR24FPS/0.9703×，速度−2.43% |

NW LMBench大部分指标开销小，OP-TEE xtest做10次取几何均值并报告全部通过。微基准每函数1000次、4轮取平均。视频每轮400帧、10轮，主文启用Neon；720p重复/丢帧指标也改变，不能只引用−2.43%就宣称所有视频质量指标一致。

附录D另外使用480p、关闭Neon，比较4核原驱动、3核原驱动、LDR无IED和带IED。速度0.9788×/0.9770×/0.9771×/0.9747×，带IED对4核基线约−0.42%，对无IED约−0.25%。这些条件不同于主文480p的0.9999×，不能跨表拼接为独立机制收益；文中附录表号指向有笔误，实际数据为表IX。

MyTEE对照是作者自行实现的假设性性能上界：测试板不支持所需虚拟化扩展，省略提权及I/O日志，MMA8451为610.19Hz。不能称为完整MyTEE复现。Driverlets的11%–270%来自所引相关工作，也不是本项目新测。TEEOS-native额外30k/15kLoC为估算，而非两套完整实现的测量。

安全实验构造类似所引CVE的溢出驱动，尝试写安全OS/其他IED、返回到OS或gate非法入口，并报告被阻止。这是有界用例，不代表三个真实CVE均完整复现、驱动内部任意漏洞已消失，或所有攻击/并发路径通过测试。

## 8. GPU扩展与CCA迁移边界

论文明确没有测试GPU/NIC，当前也没有高级workqueue和内核线程支持。作者建议拆GPU驱动，把资源管理等安全模块放SW，用户接口与调度留NW，并引用StrongBox等。该拆分会引入新的信任接口，特别是调度输入、共享对象、异步回调与完成状态，不能直接套用传感器经验。

AArch64不使用原DAC，论文提出debug watchpoint作为替代设想。本轮没有验证该扩展的完整访问覆盖、异常/重入和配置保护，也不把它当作已实现的CCA方案。研究重点是给所选隔离原语明确安全语义；不因RK3588模拟条件否定本项目假定的平台能力。

若保持当前ProxyRealm内驱动可信，LDR主要提供“如何缩小可信服务边界”的选项。若改为不可信驱动，就要由更小可信管理器独占实际页表、根配置、SMMU和关键MMIO，驱动只能提交受约束操作。把驱动放进另一个Realm但仍给它任意设备控制权，不足以得到这种保证。

## 9. 对现有项目的设计建议

继续接受RMM认证原始Client、ProxyRealm统一控制SMMU、建图校验对象/实际HPA/权限/生命周期、软件IPA→HPA合成受保护的直达HPA GPU Stage-1、其他设备保持硬件Stage-2的模型。LDR的DMA排除项不应缩小本项目已经定义的授权责任，也不需要新增重复身份框架。

优先把已有GPUVM、认证队列、私有快照、原生fence、cookie/epoch和持久IRQ127组织成接口不变量：NW输入及异步回调不直接成为地址/完成授权；真实完成属于提交时的Client和对象；结果可见早于对应通知；失败/reset后旧状态不能复活；ACK+ARM和重查保持持久事件。直接复用这些机制比移植传感器FLC更契合项目。

若未来增加驱动内部隔离，先选与页授权、设备配置和完成发布直接相关的少量入口。分别验证合法callsite配恶意参数、嵌套回调、IRQ处理中回到NW、错误返回、状态字段被修改、设备reset及Client销毁时迟到完成。隔离门要保护调用语义和资源归属，不能只限制函数地址。

## 10. Artifact范围与继续引用

固定提交README说明仓库包括U-Boot、NW Linux、LDR OP-TEE、client、CA和双生驱动，构建说明针对Ubuntu16.04/Arm32。HTML页面嵌入的完整rawLines已读，页面明确对应固定提交；因未取得对应tree/blob，README来源只按固定提交网页证据登记，不冒充blob哈希核验。

没有审计LDR核心加载器、IED汇编、FLC monitor和返回值处理实现，也没有构建、刷写、运行设备/攻击。后续可沿引用13 Driverlets（Minimum Viable Device Drivers for Arm TrustZone，EuroSys2022）、17 KSplit（OSDI2022）、38 BOOMERANG（NDSS2017）继续研究接口生成、语义鸿沟及可信I/O；是否已有独立报告仍需先检查库，不能重复计为新工作。

记录：改动目的｜补齐TEE内驱动隔离与FIQ回调的全文分析；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜纯论文/固定README研究；run-id、命令、退出码与日志｜无硬件run-id，PDF、书目、提交和获取失败证据见batch38；保留/撤回/待验证｜保留报告，核心artifact未审计、GPU扩展未验证。未改运行代码，无新增性能测量。
