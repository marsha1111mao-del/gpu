# Moneta：GPU 驱动状态回溯、Mali 直通与生命周期验证

研读日期：2026-10-27。完整阅读 NDSS 官方 17 页全文，包括参考文献和附录触发步骤；固定公开代码并定向静态检查，没有执行驱动、fuzzer、攻击、VM 或硬件实验。未改运行代码，无新增性能测量。

## 1. 准确书目与来源

- 题名：Moneta: Ex-Vivo GPU Driver Fuzzing by Recalling In-Vivo Execution States。
- 作者：Joonkyo Jung、Jisoo Jang、Yongwan Jo、Jonas Vinck、Alexios Voulimeneas、Stijn Volckaert、Dokyung Song；前两位共同第一作者。
- 会议：NDSS 2025；DOI：10.14722/ndss.2025.230218。
- [官方论文页](https://www.ndss-symposium.org/ndss-paper/moneta-ex-vivo-gpu-driver-fuzzing-by-recalling-in-vivo-execution-states/)；[官方全文](https://www.ndss-symposium.org/wp-content/uploads/2025-218-paper.pdf)。
- [论文指定实现](https://github.com/yonsei-sslab/moneta)，固定提交 e00dc48901da0e68fad5663c13cbdf1b48624952，默认分支 master。

PDF 本地文件 build/cca-gpu-followup-20261027/moneta-official.pdf，595103 字节，SHA256 fddd0e597d2292f6ba84d0a8afe311efc571eb0c10f7cf0779d44a35c80781a3。官方网页、正文、根树、scoped 子树与定向源码快照保存在同目录，源文件位于 moneta-static-batch21/。

## 2. 研究问题与项目相关性

复杂 GPU 驱动有状态很深的 ioctl 路径。重放相同调用序列时，ASLR、内部句柄、异步活动和设备交互可能改变后续状态；每次从初始化开始生成随机调用又很难抵达真正重要的对象关系。真实 GPU 数量也限制并行测试。

Moneta 先在连接真实 GPU 的虚拟机中执行正常工作负载，取得完整 VM 快照和快照之后的系统调用/设备 I/O 记录，再把快照迁到不连接 GPU 的 x86 测试机，从这些状态继续变异。创新是 snapshot-and-restore（SnR）与 record-and-replay（RnR）结合，并保留执行器植入所需的用户态上下文。

它不是 CCA GPU TEE、GPU shader 安全执行环境或内存授权架构。与本项目的直接关系是：可信 Proxy 中的驱动仍会处理复杂状态，测试要覆盖已授权对象在提交、取消、释放和重用后的变化；GPU 页隔离本身不能证明驱动所有状态转换都正确。

## 3. 威胁模型与覆盖范围

目标是 Linux CPU 侧内核 GPU 驱动，攻击输入来自其用户态可达系统调用接口。KASAN/KUBSAN 用于发现内存和未定义行为错误，KCOV 用于反馈；所测实现需要源码和编译期插桩。用户态库可以闭源。

设备侧恶意固件/伪装 PCIe 设备是讨论中的未来攻击面，本篇没有对其进行完整 fuzz。WebGL/WebGPU/视频解码可间接触及驱动，但沙箱可能限制触发低层缺陷的能力；发现 ioctl 缺陷不等于已经完成远程浏览器逃逸链。

Moneta 信任采集和测试基础设施，目标不是保护恶意 Host 下的机密数据。其快照、设备模拟和调试 hypercall 不能原样成为生产 Realm 安全边界。

## 4. 真实执行采集与无设备重宿

观察阶段在 KVM 虚拟机中运行真实 GPU 工作负载，采集内核、用户态、CPU/平台状态和设备交互。测试阶段用 QEMU 重宿快照，以录制的 MMIO/IRQ 规则模拟必要的设备响应，不执行完整 GPU 渲染/计算硬件模型。

重宿需要避免让驱动认为设备先移除再重新插入，否则 remove/probe 会破坏深层状态。论文通过虚拟化安排保持同一总线地址及驱动实例。对于 Arm→x86，使用仿真 Arm CPU，并在观察阶段限制 PMU、PAN、UAO、ITS 等难以兼容的特性；这是测试快照可迁移的工程处理，不应据此否定项目的硬件研究假设。

I/O 模拟并不完全精确。快照可越过一些难模拟的交互，但快照之后仍可能偏离真实执行。因此作者把发现的最小触发输入放回真实 GPU 环境确认；作者实验未遇到假缺陷，不构成任意后续模型都无误报的保证。

## 5. Mali 直通：软件翻译的功能与安全边界

论文针对 Mali 内置 MMU 做半虚拟化：Guest 请求 GPA→HPA 转换，Host 固定实际页，Guest 驱动向 GPU 页表填入 HPA。作者在 RK3588S/Mali-G610 上用于采集真实驱动状态。

这与项目“在建图阶段进行软件翻译，硬件一级映射直接指向 HPA”的地址路径有功能上的相近处。但本文的 Guest 驱动/测试平台不承担恶意 Client 下的可信授权证明，不能把其翻译 hypercall 直接视作 ACAI 式归属一致性机制。

项目仍采用既定假设：可信 ProxyRealm 统一控制 SMMU；RMM 认证原始 Client；根据对象归属、实际物理页、权限和生命周期完成 IPA→HPA 授权；根、实际页表和关键 MMIO 受保护。Moneta 可提供测试方法，不能替代这些条件。其他设备硬件 Stage-2 的设计也不受本文改变。

## 6. 用户态上下文与记录的结合

快照后直接替换 GPU 应用会关闭 fd 或丢失与内核对象关联的用户态上下文，导致测试只触及无效句柄错误路径。Moneta 用 Guest Agent 在执行器植入前保留文件描述符关系，再通过 exec 或进程上下文保留方式继续测试。

每个快照另带后续系统调用记录，重放一小段有效前缀后再变异，可取得比快照本身更细的状态。作者每份记录保存 200 个调用，但通常少于十二个能继续增加覆盖，之后便因非确定性偏离；不能把 200 项记录长度当成可靠重放深度。

快照保存的是具体执行状态，记录提供继续推进的合法路径。对项目，这提示测试种子应记录当前 Client、对象实例、GPUVM、native fence 和代次，不能仅保存一条孤立 RPC 或复用上一会话的整数句柄。

## 7. 平台、负载与对照

| 项目 | 作者配置与范围 |
| --- | --- |
| NVIDIA | open-gpu-kernel-modules 530.41.03；GTX1650 Super、RTX3060、RTX4060 Ti，三代架构用于覆盖硬件特化路径 |
| AMD | 上游 Linux6.8 amdgpu；Radeon RX580 |
| Arm Mali | 下游 g11p0-01eac0 / DDK r25p0-01eac0；RK3588S/G610 MP4，用户态 g15p0 libmali |
| 观察负载 | Chromium WebGL aquarium 与 OpenCL fractal；Mali 的 Chromium 图形路径未在 Guest 中跑通，只有计算快照 |
| 快照 | NVIDIA/AMD 各128份，包含两类负载；不能自动把相同覆盖配置推广到 Mali 图形 |
| 测试资源 | 两颗各64线程 Xeon8358、共128线程、1TB RAM；每配置128实例，每实例对应快照；每配置24小时，三次运行 |

No Snapshot 仍有设备 probe 后状态、RnR 和 Arm 重宿能力；No Snapshot/Replay 进一步移除录制输入语料。它们是同一框架的强消融对照，不等于原始 syzkaller 完全没有支持。正文另有 BSOD、fd 保留和 I/O 模拟的对比。

## 8. 定量结果及解释边界

| GPU 驱动 | Full覆盖 | No Snapshot覆盖 | No Snapshot/Replay覆盖 | Full 24小时总输入 |
| --- | --- | --- | --- | --- |
| NVIDIA | 17115 | 7591 | 7198 | 50781942 |
| AMD | 3879 | 3613 | 3259 | 28726479 |
| Mali | 1748 | 1518 | 1363 | 3358603 |

覆盖取图6三次运行的几何平均；表VI的若干值有轻微差别，如 NVIDIA No Snapshot 为7588、AMD为3612/3258，本文保留图表口径，不擅自合并。137.8% 是相对 NVIDIA 较弱7198对照的增加，不是相对所有基线的统一收益。

总输入是128实例合计，不能当作每实例吞吐。Full的Mali吞吐低于两个消融，但覆盖更高；AMD Full高于No Snapshot、低于No Snapshot/Replay，正文“低于两者”的概括与表VI不完全一致。跨厂商覆盖绝对数受驱动体量、采集负载和支持范围影响，不是安全排名。

## 9. 缺陷与状态依赖证据

作者报告10个厂商确认缺陷：NVIDIA5、AMD3、Mali2，包括越界读写、UAF、空指针和移位越界。表列 CVE-2024-0090、CVE-2024-0075、CVE-2024-26656、CVE-2024-27400、CVE-2024-26657；部分与厂商或其他研究者并行发现，不能全部宣称独家漏洞。

四个NVIDIA缺陷只有SnR找到。附录中339或9441个系统调用后的快照，再接两个操作就能触发缺陷；最后两步很短，不意味着无状态。另两项NVIDIA依赖341调用状态。Mali两个缺陷RnR也能找到，其价值在于重宿后可并行发现，不能用来证明所有缺陷都必须有SnR。

论文附录明确在真实GPU上确认所有触发序列。本文仅阅读，不运行这些步骤、不将作者触发结果当作本项目漏洞证据，也不把KUBSAN报告直接等同可利用越权。

## 10. 固定实现：已检查与未检查

公开库包含修改的QEMU、Host补丁、Guest Linux/strace agent、syzkaller、executor、libagamotto和配置。固定根递归树返回63020项且truncated=true，不能宣称完整仓库已枚举。另取得完整根树，以及未截断的executor/host/scripts子树；agent根树亦单独取得。未逐项审核QEMU、Linux和所有设备模拟路径。

定向阅读README、agent的moneta.c/h和agamotto.h、executor.c/moneta.h、fuzzer的proc.go及部分fuzzer.go、signal.go、Mali/NVIDIA配置和Host补丁片段。agent通过pidfd_getfd复制fd，清除FD_CLOEXEC并写出映射；snapshot分支通过SAVEVM/CHKCHKPT区分采集与恢复，然后植入执行器。与论文描述的上下文保留有实际对应实现。

agent的exec植入假设环境字符串连续，不满足时明确终止；若干工具失败路径使用exit(0)，executor最终也可能在exec失败后返回0。因而不能单看退出码宣称快照和测试已经成功，应同时验证阶段、trace、执行器启动、目标调用与覆盖反馈。这是工具静态观察，未运行复现失败。

## 11. 伪代码疑点与实际反馈路径

论文Algorithm1在Cov初始为空时用NewCov与Cov交集非空作为收录条件，若按字面执行不会接纳第一份新覆盖，和“收录新增覆盖”的文字不一致。

公开proc.go先调用corpusSignalDiff，再对空newSignal直接返回；fuzzer.go转入corpusSignal.Diff，signal.go的Diff遍历输入信号并保留已有集合中缺失或优先级更高的项。后续Intersection用于检查重执行稳定性。所读实现区分“新增”和“稳定”，不能把书面交集条件直接报告为实现缺陷。

Mali公开配置为linux/arm64、procs=1、单vCPU、sandbox=none、reproduce=false；syz-fuzzer路径是linux_amd64，而Guest kernel是arm64，属于重宿架构的组件组合，不能只据目录名认定配置错误。配置并未证明多Client并发、低权限环境或自动真实GPU复核全部覆盖。README详列的搭建流程主要是x86/NVIDIA，对Arm/Mali全流程的公开说明仍需逐组件补足。

## 12. 与保护论文及项目的关系

PORTAL/CAGE/ACAI规定设备访问的信任边界；PhantomMap强调实际物理页和映射生命周期；Moneta帮助检查实现这些职责的驱动在深层状态中是否出错。StepStone通过用户库API改善输入生成，Moneta通过快照/记录改善状态到达，两者互补。StepStone使用Moneta描述文件的对照不等于启用了本文完整系统。

项目已有RMM认证身份/队列、私有快照、GPUVM、native fence、cookie/epoch和persistent IRQ127。建议围绕这些现有机制构建“有效前缀＋非法状态后缀”：提交后关闭、撤销与完成并发、reset后晚到回调、Client重连后旧cookie、同值句柄的新代对象、旧页映射与回收竞争。

测试oracle应判断拒绝跨Client引用、受害Client输出正确、终态单调、实际停止访问后才回收，以及真实完成→结果可见→可信记录→目标通知→Client验证的顺序。中断到达只触发检查，不能自行证明任务成功；覆盖增加和无crash也不能证明上述隔离性质。

## 13. 独立判断与研究建议

本篇最值得借鉴的是保留深层对象关系、将有效前缀与恶意变异组合、并把无设备发现放回真实环境确认的方法。状态库可按授权、提交、完成、取消和回收阶段分层，以已有Client身份和代次为索引；快照回滚必须仅用于隔离测试环境，不能回滚生产安全代次来接纳旧消息。

机密快照本身可能包含明文和密钥。论文的实验采集不自动满足CCA机密性，项目若实现类似工具，需要在受控研究环境使用合成数据，或另设计可信采集与安全存储。这是采用该方法时的具体设计条件，不是本轮新增实现。

统一记录：Moneta官方全文、固定实现定向静态研读及与现有隔离协议比较｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无GPU/fuzzer/攻击run-id或新增硬件PASS；证据位于build/cca-gpu-followup-20261027｜保留为可信驱动与生命周期验证支撑，作者结果、静态观察与项目建议分别记录。
