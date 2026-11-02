# Heckler｜机密虚拟机恶意中断、可信 handler 副作用与 GPU 完成语义

研读日期：<date start="2026-10-27" />。状态：18 页作者全文、作者项目页、固定公开代码树和所列关键路径静态核对完成。未运行攻击、未修改或构建项目运行代码；未改运行代码，无新增性能测量。

## 1. 文献与证据版本

**Heckler: Breaking Confidential VMs with Malicious Interrupts**，Benedict Schlüter、Supraja Sridhara、Mark Kuhne、Andrin Bertschi、Shweta Shinde，USENIX Security 2024。来源：[作者项目页](https://ahoi-attacks.github.io/heckler/)、[项目页论文](https://ahoi-attacks.github.io/heckler/heckler_usenix24.pdf)、[本轮取得的作者 PDF](https://www.shwetashinde.com/publications/heckler_usenix24.pdf)、[ETH 研究组出版列表](https://sectrs.ethz.ch/publications/)。正式题名、作者和会议与全文对应，不为没有核验的 DOI 或页码补值。

本地全文 `build/cca-gpu-followup-20261027/heckler-author.pdf`，SHA256：`c7c893270d0804e84b926f440fac9e572a6e38e984a93e52962718549e631a5f`。全文仍链接早期 disrupt-interrupts 项目地址；本轮核对的是当前 Ahoi 作者站点及其直接链接的仓库。Ahoi 是一组恶意通知研究的总称，不另计作一篇已精读论文。

## 2. 核心发现：事件接口可以改变受保护的架构状态

CVM 的内存和寄存器可以受硬件保护，但 hypervisor 仍负责调度及部分中断注入。可信 guest 会运行对应 handler；某些 handler 并非只保存/恢复现场，而会写寄存器、触发 syscall，或转为应用异常并进入恢复逻辑。

Heckler 利用的是**错误来源、错误时机的事件触发了本身合法的可信处理程序**。无需直接篡改 CVM 内存，就可能改变后续控制流和数据流。这区别于只利用 timer 中断观察缓存行为的侧信道，但攻击定位阶段仍可依赖页访问观测，不能说整个攻击完全不使用受控通道。

## 3. 威胁模型与实际前提

攻击者控制不可信 hypervisor，可按平台允许的接口注入虚拟事件、调度 vCPU；可信基包括 CVM 内 guest OS、应用、硬件及 TEE 模块。攻击不预设已能读写 CVM 私有页或直接改受保护寄存器。

攻击还需要找到受害代码的合适执行点和 vCPU。SEV-SNP 原型用受控页故障和离线同镜像 profiling 定位；sudo 场景需要非 root shell。不同案例的前提不同，不能将“恶意 Host”简写为任意应用、任意构建、任意时刻都能稳定利用。

## 4. 分析方法：允许的状态转换和 handler 的显式效果

论文把正常执行写成程序状态 trace，区分只恢复现场的中断与产生显式效果的 handler。注入事件插入额外状态转换，使输出或控制分支偏离正常语义。这个 trace 分析是组织论证的方法，不是对所有中断或所有 CVM 完成的形式化证明。

本项目可以采用相同审查单位：列出一个 GPU 完成/错误/取消通知能修改哪些可信字段、这些修改需要哪些权威前提。这样比只检查 INTID 是否位于允许范围更接近任务完整性目标。

## 5. 两类机制及各自边界

第一类是 x86 Linux 的 `int 0x80`。正常含义是应用主动执行 legacy syscall 指令，handler 使用当时寄存器并写回返回值；外部注入同 vector 时，guest 可能误把普通应用现场当 syscall 输入，从而改变应用状态。

第二类是异常经内核转为用户态信号，运行时再转换为语言异常。某些应用 handler 会忽略输入、采用旧值或设置默认输出并继续执行。伪造异常因此能影响结果，不必使 guest 崩溃。没有这种恢复 handler 的应用可能直接终止，不能假定所有 SIGFPE 都产生攻击者可选的结果。

论文中的任意 syscall/内存泄漏讨论还要求当时寄存器恰好满足对应参数，作者明确指出寻找这类点很难。实际主要展示较弱但有影响的“零值变非零”与异常恢复效果，不是已经证明任意寄存器写原语。

## 6. 平台差异与 CCA 的明确结论

所测 SEV-SNP 配置接收全部枚举 vector，其中 11 类转换为用户态信号，另有 `0x80` 具有可见效果。TDX 丢弃大部分低 vector，仍允许特定 NMI 及 `0x80`；后者成为攻击入口。枚举结果属于论文测试版本，不是所有后续系统的永恒行为。

**论文 §11 专门测试 Arm CCA：RMM v0.3.0 只允许其所述 IRQ/FIQ 注入，过滤其余类别；作者未观察到同类 explicit-effect handler，Arm 也没有 x86 的 syscall interrupt。** 因此不能用 Heckler 声称 CCA 已存在 `int 0x80` 漏洞，或虚构 Mali 的同构利用链。

这一结果不等于 GPU 物理 IRQ、跨 Realm 服务通知和 job 归属都已解决。CCA 中需要另外研究的是受信设备状态、路由和服务状态转换；Devlore 与 TEEtime 提供更直接的 Arm 证据。

## 7. 定位、注入与确认是不同阶段

SEV-SNP 方案先离线多次运行相同镜像，区分 boot/user/application 页；在线识别目标页转换，再经 event injection 在恢复执行前交付事件。它不要求一开始知道所有 GPA，但依赖构建及访问模式，若目标函数同页还可能需要更细粒度手段。

对 TDX，作者因访问条件限制，在目标函数加入 busy loop，展示注入产生的效果，未完成与 SNP 同等的自动定位。Java/Julia 案例也用了 busy loop；C MLP 的 SIGFPE handler 由作者手动加入。这些条件必须与真实应用、未经修改的攻击目标分开。

## 8. 原型平台

SEV-SNP：EPYC 9124、Zen 4、16 cores、192GB RAM，SEV-Step 修改的 Host/KVM、QEMU 6.1.50，guest Linux 5.19.0。TDX：2023 年预生产 Xeon Platinum、112 cores、256GiB，host/guest Linux 5.19.17 和修改的 QEMU 7.0.50；2024 年又在生产 Xeon Gold 6526Y 确认 `0x80` 注入行为。

确认生产平台的 vector 可注入，不自动等于在那里重复了全部端到端案例。本文是 CPU CVM 接口攻击研究，不含 GPU 性能实验、Mali 原型或本项目多 Client 回归。

## 9. 实验结果与正确口径

| 案例 | 论文结果 | 关键条件 |
| --- | --- | --- |
| SEV-SNP / OpenSSH | 单次注入平均成功概率约 44.71% | 392 次 VM boot 离线 profiling，页序列候选定位；特定版本与构建 |
| SEV-SNP / sudo | 作者报告单次注入总能成功 | 已有非 root shell，利用 PAM 共享库 profiling |
| TDX / OpenSSH、sudo | 作者报告实验总能成功 | 目标函数加入 busy loop，不能表述为无修改通用端到端成功率 |
| SEV-SNP / C MLP | 平均成功概率约 41.6% | 手工加入恢复 handler，特定页序列与训练配置 |
| JSAT / TextAnalysis.jl | 结果被异常恢复逻辑改变 | busy loop；分别需要 240 次/2 次注入，非一个 IRQ 即改变所有输出 |

OpenSSH 的 page-trace 窗口为 773.9ms，对无追踪 14.2ms 增加约 5332%；boot 增加约 14%。不能将这些追踪开销误写为受保护应用的正常运行开销，也不能在测得显著延迟时笼统宣称攻击无可观察效果。

TDX 的注入和之后 APIC reset 分别约 1835/3092 cycles。reset 用于恢复注入后阻塞低优先级中断的 APIC 状态；guest 内 reset 模块是在取得 root 后加载，不是攻击前就假定拥有 guest root。

## 10. 防御：改变交付入口不等于限制事件授权

SEV-SNP restricted injection 用 `#HV` doorbell 提示队列事件，alternate injection 可由 VMPL0 可信组件转发给较低 VMPL。论文指出：若可信桥只是从 Host 可控队列取出 vector 再转发，没有过滤规则，搬迁交付路径不能消除问题。

但作者未完成两模式全部软件组合的原型防御实验。因此应写成对当时规范和可用实现的分析，不能声称已实测攻破此后所有 SVSM/secure AVIC 版本。

这与项目尤其相关：RMM 认证 doorbell 来源是已有安全基础，还应说明可信发送者有权宣称哪种事件、通知关联哪个 Client/job/epoch，以及接收端是否独立查询可信终态。来源认证和业务授权分别必要。

## 11. 软件修补及其适用范围

TDX 的 APIC 检查补丁约 14 LoC，真实 legacy syscall 额外开销约 460 cycles，论文验证该入口攻击被阻止。SEV-SNP 同类 APIC 检查不能覆盖 VMCB injection；回看指令也涉及 x86 变长指令与来源判定的局限。

禁用 IA32 emulation 可关闭 `0x80` 路线，但影响兼容性，并不能处理所有异常转换问题。选择性过滤比无差别丢弃中断更可行，必须覆盖全部注入入口及策略变更、嵌套/重入。上述数字不是 GPU IRQ handler 应承受的参考预算。

论文在 2024-03-06 附近的披露状态涉及 CVE-2024-25744 和 CVE-2024-25743。该时间点“未缓解”不直接等于 2026 年当前仍未修复；本轮没有对所有厂商最新版本做补丁覆盖审计。

## 12. 公开代码：固定版本与实际核对

作者直接链接的 [ahoi-attacks/heckler](https://github.com/ahoi-attacks/heckler) 固定为 `2a2c85a2e08f55bc8ac635d11d07473190f452eb`，递归树完整且未截断。本轮读取 README、`build.sh`、stable-commits、SSH/sudo 的选定注入段、CPython binding、SEV-Step API 的注入/ACK 路径及 sshd.diff。

可确认的链路是页事件模式匹配→Python binding→`inject_interrupt`→KVM ioctl；ACK 路径在锁内更新共享事件状态。这里的 ACK 是攻击工具与 KVM 的事件协调，不是被攻击 guest 的中断真实性证明。没有核验全部 companion kernel 后端或 TDX 实现，也没有运行测试。

`stable-commits` 实际列出 kernel/QEMU/OVMF 的仓库和分支名，不是把所有依赖固定为不可变 SHA；固定主仓库并不足以重建完全相同的运行环境。公开树主要为 SNP 工作流，不能由 README 的论文标题推导完整覆盖论文全部平台。

公开 `sshd.diff` 包含页地址辅助代码、主动 touch/logging 及移除 authentication minimum-time delay。由此应区分论文主张、profiling 辅助和 artifact 默认配置，不把“源码存在”写成未经辅助、无修改服务的完整复现证据。

## 13. 与相关工作的关系

| 工作 | 保护/攻击对象 | 需要保留的区别 |
| --- | --- | --- |
| Heckler | Host 注入事件触发 guest handler 的架构副作用 | CPU CVM；CCA 测试未发现同类 handler 效果 |
| WeSee | SEV-SNP `#VC` handler 与虚拟化通信 | 不同事件语义和攻击链；本轮取得全文，需单独解读 |
| Sigy | SGX 异常/信号转发接口 | enclave runtime 层；不能当成 GPU IRQ 漏洞 |
| Devlore | CCA 物理事件记录、受控虚拟注入和 ACK | 更直接支持 Arm 设备中断真实性设计 |
| TEEtime | 中断配置、状态和路由隔离，含 proxy 模式 | owner 收到真实 IRQ 后，服务协议仍要决定 Client 事件 |
| ASGARD / TZ-LLM | 加速器任务顺序、可信启动与完成处理 | 用加速器论文补上应用语义，避免只研究 CPU vector |

表中的关系是分析比较，不声称所有后续作者都直接继承 Heckler。

## 14. 迁移到本项目的四条不变量

**合法入口**：平台/RMM 限制受保护 INTID 及注入配置，不能由 Host 选择任意入口让 Proxy/Client 执行敏感 handler。已有 IRQ127 保留和 Host LR 检查应作为基础。

**事件权限**：可信 Proxy 向 Client 发通知时，Client/session/job/epoch 应来自可信状态；Client 自己的请求只能表达操作意图，不能声明另一个 Client 的硬件执行已完成。已有 RMM 身份和私有请求快照支持这一点。

**状态转换**：接收 doorbell 后从权威队列或状态表读取结果；仅有中断到达不构成 SUCCESS。真实原生 fence、错误及取消信息应共同决定合法终态，重复或合并通知不得导致重复转换。

**后果约束**：超时、错误/取消 fence、session 关闭、旧 epoch 被拒绝，不单独构成设备停止访问的证明。可以先记录失败，但页面撤销、事务排空和安全回收需要各自条件。这连接中断通信隔离与内存隔离。

## 15. 可验证的研究扩展

在已有机制上增加状态转换验证：注入无对应 job 的通知、重复完成、错误 Client、reset 后旧 epoch、完成与 cancel 并发，以及真实 IRQ 已到但 GPU 状态尚不满足任务成功的情况。验收应检查结果、权限、资源持有和受害 Client 是否保持正确，不仅统计 ISR 次数。

另对可信 handler 做副作用清单：哪些写法只提示调度，哪些推进 timeline，哪些 signal fence，哪些释放对象或改变映射。每项副作用绑定权威前提和恰好一次的状态更新；多次通知仍可合法存在，不需要一 IRQ 对应一 job。

这些是项目建议，尚未实施，也不是已经证明当前代码存在可利用漏洞。若将可用性纳入目标，还需调度与资源上界；本论文不能为 GPU deadline 保证背书。

## 16. 独立评价与记录

Heckler 提供了“内存完整性不足以推出执行完整性”的实际案例，其研究价值在于事件来源和 handler 状态效果的组合。对本项目，最合适的用法是支撑可信异步完成协议的必要性，并用 Devlore/TEEtime 和 GPU 任务论文落实 Arm 场景。

统一记录：机密 VM 中断安全全文与定向 artifact 静态研读｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜固定主仓库、全文 SHA 和选定文件保存在本轮 build 证据目录，无攻击复现、硬件 run-id 或新增硬件 PASS｜新增独立解读，完整环境复现与最新补丁覆盖未执行。
