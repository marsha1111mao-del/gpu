# WeSee｜恶意虚拟化异常、嵌套 handler 与跨信任域检查顺序

研读日期：<date start="2026-10-27" />。状态：18 页作者全文（含附录）、正式书目、作者站点、固定公开代码树及所列关键路径已静态核对。未执行攻击、未构建载荷。未改运行代码，无新增性能测量。

## 1. 文献与版本

**WeSee: Using Malicious #VC Interrupts to Break AMD SEV-SNP**，Benedict Schlüter、Supraja Sridhara、Andrin Bertschi、Shweta Shinde，IEEE S&P 2024，正式页码 4220–4238。DOI：[10.1109/SP54263.2024.00262](https://doi.org/10.1109/SP54263.2024.00262)。[作者项目页](https://ahoi-attacks.github.io/wesee/)、[作者全文](https://ahoi-attacks.github.io/wesee/wesee_oakland24.pdf)、[ETH 出版列表](https://sectrs.ethz.ch/publications/)。所读 PDF 自注为 author’s version，18 页，与正式出版分页分开记录。

本地全文 `build/cca-gpu-followup-20261027/wesee.pdf`，SHA256：`76f177de91d8931856e6d14b99a08d2c3576cb8b543be886078dfc49eb2beb75`。本文是新增相邻机密计算研究，不是 GPU 或 CCA 论文，也不与 Heckler 合并计数。

## 2. 核心问题：验证数据内容仍不足以认证事件原因

SEV-SNP 保护 guest 内存和寄存器，使 Host 无法直接读取它们；但虚拟化仍需 CPUID、时间、MMIO 等服务。guest 的 `#VC` handler 通过 GHCB 共享页选择性交换必要信息，实现不修改应用的兼容路径。

WeSee 发现：Host 可以在非真实原因下触发 handler，并控制所声称的 exit reason。handler 可能按合法协议复制寄存器、写回数据和推进指令指针，却为错误上下文执行这些动作。Iago 式的返回值检查不能单独回答“这次通信是否真的应该发生”。

## 3. 威胁模型与实际前提

Host/hypervisor 不可信，可调度 vCPU、观察/制造其负责的 stage-2 页故障，并通过允许的接口注入事件。硬件和密码算法正确；guest OS、handler、GHCB 使用遵循论文所述规范。攻击不先假定任意 guest 私有内存写能力。

这仍依赖具体 handler 的语义和内核布局：作者分析 Linux 6.7-rc4，并在特定 6.5.0 系列环境展示攻击。论文不需要应用级 gadget 才能攻击内核，但不能推导为无需版本适配、无需定位或任何 guest OS 都有效。

## 4. 正常控制流与敏感副作用

正常情况下，硬件因 guest 的特定指令产生 `#VC`，handler 根据原因取得执行上下文，复制指定字段到 GHCB，退出至 Host；Host 写返回值后，handler 检查并更新 guest 上下文，返回应用。

三个关键副作用是向不可信共享内存输出数据、从不可信共享内存导入数据，以及改变恢复执行位置。只要事件原因、执行现场或操作目标不真实，这些合法动作就可能泄密或改变执行。

## 5. 机制覆盖范围：并非全部事件都用于攻击

作者分析 19 类 instruction-intercept event，其中 10 类导致数据交换；实际攻击主要使用 VMMCALL 与 MMIO read/write。VMMCALL 可交换特定寄存器；MMIO 分支包含指令解码、寻址、页表检查和数据拷贝。

攻击者不能凭一个错误 reason 无条件读写任意位置。WeSee 用多个 handler 效果组合，处理解码、指令推进、指针和检查返回值等约束，才构造更强原语。正文的认证示例用于说明机制，不等于端到端案例攻击某个真实认证应用。

## 6. 原语组合及其证据

论文构造跳过指令、寄存器读写、内核内存读写及代码注入。内存读写每次 8B，依赖 MMIO handler 中可控制的上下文指针和数据搬运；代码注入还需要先改变 guest 自己的页表写权限。

其重要性在于：页表起初并未被 Host 直接修改，而是可信 guest handler 在被诱导的流程中执行了写入。由此不能将“CPU 页表放在受保护内存”单独作为所有控制面安全性的充分论据；同时也不能声称这已绕过了本项目平台假设中的受信授权策略。

## 7. 嵌套与重入为什么重要

WeSee 将连续事件和嵌套事件组合：后一个 handler 改变前一个 handler 正在使用的状态。作者在非关键区至少达到 3 层嵌套，在 GHCB 关键区达到 1 层嵌套。论文没有声称关键区可以无限嵌套。

附录解释了合法嵌套需求：具有两个内存操作数的指令可能需要拆成读/写来识别 MMIO，处理过程中再次引发 `#VC`；Linux 用第二个 GHCB 支持一次关键区嵌套。因此不能用“关中断即可”或“禁止所有嵌套”代替对异常语义和兼容需求的分析。

对 ProxyRealm，更可迁移的是检查可信请求快照、锁、对象引用和状态提交在 IRQ、worker、回调、cancel/reset 交错中是否仍是一致事务。不能把 x86 `#VC` 可嵌套的具体硬件行为直接套到 Arm 上。

## 8. 定位与 KASLR 的实验条件

作者选择跨页调用/返回后的指令，用页故障序列识别执行点，避免依赖指令级 single stepping。位置随机化通过 boot trace、内核固定布局及已有原语取得基地址后处理；不同内核构建可能需要换目标函数或更细粒度定位。

物理 KASLR profiling 中，作者修改自己控制的离线 kernel 来识别固定 early-boot 页；在线攻击使用未作该修改的 victim image。不能把离线插桩说成 Host 已绕过远程证明并在线修改受害 boot image。

## 9. 平台、计量与案例

EPYC 9124，16-core、3.7GHz、192GiB，SEV-SNP Gen 4，microcode `0x0a10113e`；QEMU 8.0.0，Linux 6.5.0 系列，guest Ubuntu 20.04.6、host Ubuntu 23.10。每项报告为 3 次实验平均。

| 指标/案例 | 作者结果 | 边界 |
| --- | --- | --- |
| 单次 `#VC` round trip | 3.19µs | 非完整内存攻击时延 |
| 指令 skip | 216450 次/s | 与内存读写的多事件原语不同 |
| 内存读/写 | 9.25/8.95 次/s，每次 8B | 不能称为高吞吐显存泄漏或直接 DMA |
| kTLS 会话信息 | 5.97s；8 次内存读，288 次 `#VC`，2115 次页故障 | NGINX 1.25.3、OpenSSL 3.2.0，实际解密捕获流量验证 |
| Firewall 绕过 | 4 次读、5 次写，238 次 `#VC` | 修改内核过滤代码，观察被禁止 ICMP 获得回复 |
| Root-shell 案例 | 4 次读、52 次写，2891 次 `#VC` | 原文特定内核布局与代码注入流程 |

Root-shell 案例的权限页走查和代码写入分别约 3.1s/8.1s；它们不是含 boot profiling 的完整总耗时。攻击研究结果不提供 GPU 性能数据或本项目 glmark 的任何变化。

## 10. 防御的关键顺序：检查必须早于信息外流

软件方向包括解码实际指令，并将操作码、操作数、真实 MMIO 区域与 event reason 关联。只检查“属于可拦截指令之一”仍不够，例如 CPUID reason 与 IOIO 指令不能互换；只看到未加密页也不证明它就是合法设备 MMIO。

论文特别讨论其时点的 Linux 修补：若先将寄存器复制到 GHCB，再验证 `#VC` 是否合法，即使最终终止 guest，Host 也已可观察到 8B。**事后 fail-closed 无法收回已经外流的信息。** 这是作者对当时补丁的发现，本轮未独立复现该泄漏，也未将其视为 2026 年所有最新版本仍存在的结论。

同理，对本项目不能先输出结果、推进 Client timeline 或撤销对象引用，再补查 Client/epoch/owner。检查必须位于相关敏感副作用之前，并保证检查所用对象与实际使用对象属于同一生命周期。

## 11. 硬件/可信软件方向及更新时点

论文提出保护 exit reason、防止外部注入 `#VC`，或用 restricted/alternate injection 和可信桥实施过滤；并讨论当时 secure AVIC 的可用信息。修改交付机制必须配合事件授权，不能把一个新 doorbell 名称当成安全策略。

这些是论文 2024 年时点的状态与建议。CVE-2024-25742 的存在不能直接证明所有后续 microcode、Linux、SVSM 和云平台仍受影响；本轮没有做全产品补丁覆盖审计。

## 12. 其他实现的差异及不适用范围

作者发现 Enarx 的单 CPUID handler 检查实际 opcode，所分析版本不受该攻击；Mushroom 在所述 VMPL3 alternate-mode 条件下不受影响。Coconut SVSM 的指令与 error-code 关联缺口被实验展示；Oak 的问题获维护者确认并修补，但作者没有在其内部 hypervisor 上运行同等 exploit。Windows 的实现分析受阻，不能写成已证实易受攻击或已证明安全。

**论文明确结论：WeSee 不适用于其分析的 Intel TDX 和 Arm CCA。** TDX 阻止相应外部 `#VE` 注入，相关参数由可信 TD module 提供；CCA 未发现同类 handler。该事实支持来源/参数由可信层控制的设计，也限制了漏洞迁移的表述。

## 13. 固定公开 artifact 与核对范围

[作者仓库 ahoi-attacks/WeSee](https://github.com/ahoi-attacks/WeSee) 固定提交 `3f504bb199d23d5ce6dbf448287aaeab715313cc`；递归文件树完整，非截断。读取 README、`init.sh`、Dockerfile、host.patch 的所列控制路径、用户态 exploit 的接口/页走查/默认入口；guest config 已取得，但未逐项审计全部配置。

主干可确认：用户程序提交读写意图，Host 补丁设置共享攻击状态、通过 KVM 页事件状态机安排注入，并在 vCPU 运行入口写 VMCB event/error 字段。读取/完成接口在状态未就绪时返回 busy/error。该状态机用于攻击编排，不是受信事件授权设计。

脚本固定了 Linux `ad9c0bf475ecde466a065af44fc94918f109c4c9`、QEMU `94bec6ae7a81872ca0df2655dac18b2dea8c3090`、OVMF `80318fcdf1bccf5d503197825d62a157efd27c4b`，这是比浮动分支更明确的构建输入。但磁盘镜像使用 Debian trixie daily/latest，与论文 Ubuntu guest 不同；容器 apt 依赖也并非完整锁定。不能把当前脚本默认输出当作原论文环境。

公开代码存在内核函数固定 offset、全局攻击编排状态，默认用户入口偏向代码注入案例；没有仅凭它宣称原型覆盖任意内核构建或多 VM 同时攻击。未对全部 patch 行和基础内核做完整审计，也未运行代码、修改设备权限或启动 guest。

## 14. 与 Heckler / CCA / GPU 工作的关系

| 工作 | 关键语义 | 可迁移范围 |
| --- | --- | --- |
| Heckler | 错误时机触发 legacy syscall/异常恢复 handler | 审查事件入口副作用；不能复用其 x86 vector 当 CCA 利用链 |
| WeSee | 伪原因触发跨信任域复制，嵌套组合 handler | 检查事件依据、目标和检查顺序，尤其共享输出前的授权 |
| Devlore / TEEtime | 真实物理事件、配置、路由和注入控制 | 更直接支撑 Arm 设备 IRQ 可信性 |
| CAEC | 已认证 Realm 间共享通信 | 身份和受保护共享区域仍需上层事件状态规则 |
| ASGARD / TZ-LLM | 加速器顺序、可信启动和完成处理 | 将事件真实性与真实任务状态联结 |
| PhantomMap / ACAI | 实际页与身份/映射归属 | 有效地址不等于该事件有权触发该地址上的数据搬运 |

该表是机制比较，不把这些论文混成相同威胁模型或一条未经证实的作者继承链。

## 15. 对当前 ProxyRealm 的具体改进方向

当前已有独立 GPUVM、RMM 认证队列和持久 IRQ127、私有请求快照、原生 fence、cookie/epoch。WeSee 支持在这些基础上进一步核验：可信层是否确定事件原因；通知携带的 job/对象是否仍有权限；输入快照与执行时引用是否一致；所有可见副作用是否在授权后发生。

建议将完成处理写成明确的可信事务：取得稳定的任务引用→验证 Client/session/epoch 和当前状态→观察权威完成/错误条件→恰好一次记录终态与数据可读条件→发布通知。具体锁和屏障应由代码确定，这里不是新增空框架要求。

取消/reset 可先记录 ERROR 或 CANCELLED，但其资源回收仍需旧 GPU 访问停止、翻译失效和必要清理。不能因逻辑终态已存在就提前把页交给新 Client；这也是中断通信隔离与内存隔离相互依赖的原因。

## 16. 可验证的扩展与独立评价

围绕现有协议测试：同一来源发错误事件类型、有效 cookie 配错对象、旧 epoch 配当前地址、检查后对象被撤销、完成回调与 reset 重入、拒绝路径是否已写入另一 Realm 可读区。预期是敏感副作用不发生，且正确任务状态可恢复；不能只以“最终返回错误”验收。

WeSee 的意义是证明“可信 handler + 合法数据格式”仍需事件原因和上下文授权。对本项目，它提供协议审查方法和负面测试依据，**不构成本项目或 Arm GPU 已有同类漏洞的证据**。硬件是满足用户给定可信假设的实验载体，研究重点仍是状态与授权的一致性。

统一记录：机密计算虚拟化异常全文与定向 artifact 静态研读｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜全文 SHA、固定主仓库和选定代码保存在本轮 build 目录，无攻击复现、硬件 run-id 或新增硬件 PASS｜保留为新增独立精读，当前厂商补丁状态与完整复现未核验。
