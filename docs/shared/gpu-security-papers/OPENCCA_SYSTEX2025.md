# OpenCCA（SysTEX 2025）：CCA 实验载体、功能模拟与安全论证分层

研读日期：2026-10-27。完整阅读7页arXiv v1及42条参考文献，无附录；核对正式书目、作者官网与公开仓库入口，限定读取README和manifest。不是新增GPU隔离系统，也不是CCA硬件安全等价实现。未改运行代码，无新增性能测量。

## 1. 来源与版本

OpenCCA: An Open Framework to Enable Arm CCA Research，作者Andrin Bertschi、Shweta Shinde，ETH Zurich。正式发表于EuroS&P Workshops2025中的SysTEX，429–434页，DOI [10.1109/EuroSPW67616.2025.00056](https://doi.org/10.1109/EuroSPW67616.2025.00056)。workshops与主会分开，正式6页书目和实际取得7页作者arXiv稿也分别记录。

实际全文为 [arXiv:2506.05129v1](https://arxiv.org/abs/2506.05129v1)，2025-06-05，PDF2401688字节，SHA256 `9ee8d4ca9c7da7b8705883e697245462eb18855919e5fe6463ac6ab6817bf480`。7页含42条参考文献，未逐像素重绘图或重新运行表中实验。论文指向的extended页面目前是重定向至同一arXiv的HTML，不把它计作另一个已读长版本。

[官方项目站](https://opencca.github.io/)链接 [opencca/opencca](https://github.com/opencca/opencca)。该入口固定 `e80368cdef0a3ae7c4a997fe2cd86a28e41d55d3`（2025-09-10），完整树仅1项README，全文已读且blob/长度/SHA256核验。它是组件索引，不能将读取此仓库写成已审计TF-A/RMM/Linux核心代码。

沿README确认 [opencca-manifest](https://github.com/opencca/opencca-manifest)，固定 `043a44ac57eb95373cdf67fb582bf10a8f8f6bfc`（2026-03-09），完整2项树，2个blob核验并全文读取。`default.xml` 是内容为opencca-devel.xml的符号链接blob；目标XML引用多个可移动分支，固定manifest本身不等于固定所有组件。这里取的是后续公开状态，不保证是论文测量的精确版本。

本工作区 `opencca` 是项目fork，HEAD `8014f360db0c7d4912a6e0cd4f5c5ee18e586435`，包含其他工作与dirty子模块；`manifests/component-revisions.md`记录2026-06-11组件捕获及本地patch说明。这里只读对照，未同步上游或改变子模块；本地fork不冒充论文原始artifact，历史捕获也不自动等同当前运行冻结版。

证据位于 `build/cca-gpu-followup-20261027/` 的opencca前缀及batch47文件。全文和表格提取已读，源码范围限上述入口及manifest，不做运行、部署、刷写、模拟或安全攻击。本轮没有证明当前硬件隔离有效，也没有因缺少RME而否定项目假设。

## 2. 研究问题与贡献边界

论文观察2025年早期CCA研究依赖FVP做功能验证、各自移植旧Arm开发板做性能实验，工作重复且难以比较。其表1是截至2025-02的19篇研究快照：15篇进行移植，4篇未做硬件性能评估；这是历史统计，不推广成当前全部文献数量或今天仍无CCA设备。

目标是让CCA绑定软件尽量原样在Armv8.2板运行，提供真实微架构上的best-effort性能估计与可复用工具链。它模拟缺失的CCA语义，不宣称不可信Host与模拟Realm之间具有真实RME世界隔离；正确研究方法是明确哪些性质由模型假设、协议实现或实验分别支撑。

对当前项目，OpenCCA主要支撑第一部分“GPU直通/共享实现及性能优化”的实验基础，也可承载第二部分“内存/中断通信隔离”的机制测试。一个通知可正确送达，和恶意Host不能伪造有效完成，是两种不同待证性质，不能用功能PASS互相替代。

## 3. 软件世界切换与GPT模拟

真实RME通过SCR_EL3的NS/NSE区分Normal、Secure、Realm。缺少NSE时，OpenCCA把Realm和Normal都置于NS=1，以每CPU世界上下文中的软件位NSE′区分；TF-A在同步SMC与异步中断进入EL3时查软件上下文，保存/恢复相应状态。

两种软件世界复用架构Normal空间，RMM与Host切换需清EL2 TLB以避免旧翻译污染。论文另维护保留ASID范围、减少flush的替代补丁，但明确不在本次评估内；不能把优化补丁的理想收益加入主表结果。软件世界标签也不等同硬件不可伪造的Client身份。

缺失GPTBR_EL3/GPCCR_EL3等使用AFSRx等替代寄存器与预定义值模拟，PAALLOS相关失效用范围更大的完整TLB flush近似。GPT表仍会构造和维护，可估算软件管理工作，但实际GPC硬件检查没有由此出现，替代操作也不是所有目标平台的周期精确模型。

RK3588启动由U-Boot承担早期初始化，没有部署传统TF-A BL2，GPT初始化从BL2移至BL31。这样可纳入启动软件开销；论文中原本属于特定阶段的职责转移，不能未经测量归因到新增隔离策略。

## 4. RMM、页表与缓存适配

RMM用TTBR0映射共享低地址、TTBR1映射每核私有高地址。缺少Small Translation Tables时，把TTBR1空间从2MB调至64MB、使用可支持的base level2。这是RMM自身映射适配，不是GPU虚拟地址或Client授权对象的设计。

缺少FWB时，Stage-2内存属性与显式cache维护需要调整，作者曾遇到启动陈旧数据及不一致崩溃。这个经历对项目有直接价值：权限检查、实际页表可见性及缓存/TLB生命周期必须一起考虑；单纯写入了合法页表，不证明设备后续已经按新表访问。

软件仿真缺失指令可能增加额外flush，缺失GPC/加密可能省掉真实代价，因此结果不能一概当真实CCA的上界或下界。可以比较同一实验载体上固定条件的方案变化，再单独解释目标安全硬件的差异，而非用一个常量把所有测量“换算”为真实CCA。

## 5. Timer与FP：中断转送仍含Host参与

缺少Enhanced Counter Virtualization时，固定Realm生命期CNTPOFF=0。真实RMM在物理timer到来后退出至Host，由Host安排虚拟中断；保持较小RMM TCB不意味着Host通知天然可信。本文解决定时器兼容和执行进展，没有给出GPU中断来源/任务归属认证协议。

缺少RME/ECV相关mask能力时，用CNTP_CTL_EL0等替代屏蔽物理timer，避免恢复Guest立刻再次退出。lazy FP首次使用引起trap并恢复状态，若紧接timer退出则可能反复恢复且无法推进；OpenCCA在上次因FP恢复退出的情况下继续mask以打断循环。

这表明中断路径是调度、寄存器恢复和进展协议的一部分。实验中“减少IRQ或退出次数”既可能是优化，也可能改变了mask/FP路径，需在同样语义下比较；论文timer方案不能直接当Devlore式可信设备IRQ转送，或以它替代本项目native fence与cookie/epoch完成核验。

## 6. 实现规模与启动链

U-Boot的Binman增加RMM组件，把RMM与TF-A一起打包进入固件链。论文保持hypervisor、CVM和kvmtool不变；摘要列出整个软件栈是分析范围，不能据此写成所有组件都已修改。

| 组件 | 论文版本 | 修改规模 | RK3588特定比例 |
| --- | --- | --- | --- |
| TF-A | v2.11 | 940 LoC，约+0.3% | 59% |
| TF-RMM | v0.5.0 | 1440 LoC，约+6% | 16% |
| U-Boot | v2024.01 | 216 LoC，约+0.01% | 0% |
| Linux Host / CVM | v6.12.0 | 基础软件栈不修改 | 不适用 |
| kvmtool | cca/v3 | 基础软件栈不修改 | 不适用 |

TF-A、RMM、U-Boot总代码约309K/25K/1.5M，表中是源码量和移植增量，不能把三者相加当已测量TCB或据少量新增行推导安全。后续PMU评估专用补丁与基本功能修改也要分开记录。

## 7. 性能实验：作者平台、样本和主表

Radxa Rock5b/RK3588，16GB RAM，论文使用64GB eMMC；A55 core2隔离并固定1.8GHz，kvmtool固定核，CVM 1 vCPU、256MB或1GB。TF-A/RMM release，仅ERROR日志，PMU测retired instructions与cycles；为跨EL/世界计数另绕过PMU常规save/restore。以上是作者实验，不是本轮运行条件，论文介质也不改变工作区只允许storage ID2 SD的操作规则。

启动100次，SMC/RMI 500万次；表报告均值和标准差。作者在FVP与RK3588运行相同二进制的CPU工作负载并人工核对结果一致，支持所测功能，不等于穷尽所有并发、中断、异常和对抗行为。

| 基础操作 | 平均指令 / cycles | 标准差指令 / cycles |
| --- | --- | --- |
| 启动256MB CVM | 1900M / 2647M | 6M / 15M |
| 启动1GB CVM | 2015M / 2869M | 8M / 18M |
| Delegate 4KB | 2865 / 7988 | 187 / 365 |
| RMI Version | 994 / 3583 | 120 / 222 |
| 空RMI round trip | 932 / 3370 | 115 / 209 |
| 空SMC round trip | 182 / 421 | 44 / 68 |

空RMI往返与Version查询相差213 cycles，是论文此配置测量；不作为本项目映射授权、GPU提交或IRQ端到端延迟。测量短调用存在微架构噪声，500万调用也不能代替披露批处理/计数覆盖范围或证明生产系统尾延迟。

## 8. Two-GPT与Shadow GPT案例

Two-GPT在现有GPT外引入第二GPT：启动GPT2全部Root，delegation在GPT1标Realm、GPT2标Normal，undelegation反向恢复。作者改7个TF-A文件，加2348行删13行，4 person-hours；这是借鉴已有机制的移植案例，不是完整新GPU系统。

| 操作 | Two-GPT平均指令 / cycles | 与基础值比较 |
| --- | --- | --- |
| 启动256MB | 1928M / 2690M | 对应基础1900M / 2647M |
| 启动1GB | 2039M / 2902M | 作者约+1.19% / +1.15% |
| Delegate 4KB | 3488 / 8654 | 作者约+21.7% / +8.3% |

百分比来自对应表项和作者口径，表中有舍入；不套用到共享GPU帧率，也不由“两张表的软件操作成功”推出硬件GPC确实执行了两个隔离域。

Shadow GPT借鉴Shelter，将预配置GPT模板复制以代替从头构造；改10个TF-A文件，加1398删24行，5 person-hours。创建一次为50.86M指令、34.61M cycles；没有在本轮独立重算，也不把单项创建时间当包含所有后续切换/清理的完整生命周期成本。

4/5人时说明作者可快速重实现所选案例，不保证别的团队/驱动/GPU同样代价。模板复用、安全状态重置、页归属更新及未完成事务处理仍需具体协议；复制对象不天然继承正确Client身份或生命周期。

## 9. 公开入口的可复现边界

官方README明确列出manifest/build/flash/assets/rootfs以及TF-A、TF-RMM、Linux、kvmtool、U-Boot独立仓库。本轮只确认入口关系和三个blob，没有审计核心patch、运行测试或确认每个分支对应论文版本；仓库可获得不等于结果已经复现。

manifest中多个revision为opencca/main，kvmtool为upstream/cca/v3，rkbin为master，buildroot使用2023.08 tag。即使固定XML的Git commit，后续repo同步仍可能取得不同组件；研究需记录组件确切commit、补丁hash、构建配置及运行映像身份。对当前项目继续遵守固定子模块/manifest，不为文献研究更新latest。

工作区组件捕获表包括本地fork与patch记录，与论文基础v0.5.0/6.12等不是一个自动可替换版本矩阵。当前冻结设计以CURRENT_BASELINE为入口，不能用2025论文或历史manifest替代当前基线，亦不能把上游预期patch diff擅自清理为“干净状态”。

## 10. 如何支撑当前项目的两个部分

安全模型层继续采用RMM认证原始Client、可信ProxyRealm统一控制SMMU、建图时核验对象/实际HPA授权/权限/生命周期、软件IPA→HPA合成受保护GPU Stage-1，其余设备用硬件Stage-2。OpenCCA承载实验，不改变这些目标假设；需明确平台保护页表/根配置/MMIO和可信固件加载是模型前提，哪些前提在实验上被模拟。

实现层分别列出直通路径、共享提交路径、GPUVM归属、认证队列/私有plan与快照、native fence、cookie/epoch以及持久IRQ127的调用与状态机。复用已有框架，避免因为论文使用软件世界位就另造Client身份；RMM软件运行正确也不能让Host传来的ID自动变成认证身份。

安全实验层围绕映射建立/更新/撤销、任务准入与真实终态、错误/取消/reset、旧消息和资源回收验证状态机。持久IRQ127是通知，不当作完成证据；拒绝旧epoch只是拒绝旧事件，不证明旧GPU/DMA事务已静默。timer mask正确推进也不证明完成消息目标正确。

性能层固定载体、版本、CPU/GPU频率、日志、缓存/TLB策略、工作负载及计时范围，拆分授权建图、提交、执行、完成核验与通知。全flush、PMU专用补丁和FP/timer路径都可能改变观察结果，不能未经消融归因到共享GPU某一个优化。

论文没有glmark成绩，本轮也没有新增运行；不能以基础SMC/RMI改善预测超过1000分。按仓库规则，未来大改动需要给出改动前后完整720p glmark分数、绝对与百分比变化、可比条件、run-id和失败项，达到门槛后再做API/计算/多Client回归；这里仅解释研究与记录方式，不启动测试。

## 11. 总体评价与后续方向

OpenCCA直接支持“硬件只是模拟测试载体”的研究路线，贡献在统一移植、功能对接与真实微架构的受限性能观测。它不能单独补齐GPU设备授权、可信中断、固件隔离、跨Client共享或安全回收，但也不应因为缺少RME就否定这些在明确目标模型下的设计研究。

继续结合PORTAL的服务Realm、ACAI的归属一致性、CAGE的GPU扩展、PhantomMap的实际页及生命周期、Devlore和机密VM中断攻击研究，把安全命题与实验可观察行为逐一对应。官网出现的后续用户项目只能作为发现入口，未读全文与未审计源码不登记完成；OpenCCA本身也不重复计作一套GPU TEE架构。

记录：改动目的｜补充CCA实验载体与项目安全/性能论证分层；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整7页/42参考文献、正式书目、官方入口和2项manifest有界静态读取；run-id、命令、退出码与日志｜无硬件run-id，batch47来源与发布核验；保留/撤回/待验证｜保留独立报告，核心代码/全组件版本/硬件安全等价与端到端复现未验证。未改运行代码，无新增性能测量。
