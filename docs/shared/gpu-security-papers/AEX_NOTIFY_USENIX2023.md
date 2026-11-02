# AEX-Notify：机密执行的中断感知、精确单步缓解与可信事件边界

研读日期：2026-10-27。完整阅读19页USENIX正式PDF（封面加会议录4051–4068页）、72条参考文献及A/B/C全部附录，定向静态阅读固定Intel公开SDK的AEX API、handler、解码与预取路径。没有执行SGX-Step、攻击、解码器、分析工具、编译、模拟器或硬件实验。未改运行代码，无新增性能测量。

## 1. 准确书目与取源

- 题名：AEX-Notify: Thwarting Precise Single-Stepping Attacks through Interrupt Awareness for Intel SGX Enclaves。
- 作者：Scott Constable、Jo Van Bulck、Xiang Cheng、Yuan Xiao、Cedric Xing、Ilya Alexandrovich、Taesoo Kim、Frank Piessens、Mona Vij、Mark Silberstein。
- USENIX Security 2023，4051–4068页；ISBN 978-1-939133-37-3。采用官方BibTeX，不补造DOI。
- [正式页面](https://www.usenix.org/conference/usenixsecurity23/presentation/constable)；[所读正式全文](https://www.usenix.org/system/files/usenixsecurity23-constable.pdf)；[Intel公开SDK](https://github.com/intel/confidential-computing.sgx.sdk)。

正式PDF为977572字节，SHA256 0fe86655081c73d091a0bc3287a8b6a413aacb359439ac4886d48cf5ddde5ab6。完整下载超时后逐段核对Content-Range并续传合并，严格解析确认19页与EOF；没有使用78570字节的首次不完整响应。全部页面均有有效正文提取，架构图、表格和附录汇编已随对应页核对。

证据位于build/cca-gpu-followup-20261027：aexnotify-complete-batch25.pdf、分页文本、官方页面与范围响应；batch26文件保存固定公开仓库、完整tree、十项定向文件及SHA。跨批次文件名仅表示取源顺序，不改变正式2023书目。

这篇是SGX机密计算的CPU中断侧信道防御论文，不是GPU TEE、CCA虚拟IRQ路由或GPU完成认证论文。纳入本项目，是为了准确界定“中断可信性”之外还存在何种执行控制与时序隐私问题。

## 2. 动机：数据隔离后为何仍有中断攻击

SGX保护enclave内存和执行状态，但OS仍能安排中断、修改受架构允许的页表属性、观察页访问并控制调度。精确中断把本来嘈杂的整体时间变成逐指令观测：可测单条指令中断延迟、精确计算分支指令数，或在每条指令间探测cache/分支预测器。

SGX-Step利用APIC和页表A-bit实现大量single-step或zero-step，并能过滤没有前进的样本。问题不是OS直接读取私有内存，也不要求伪造一条业务完成消息；攻击者操纵的是受害者何时被打断、每次前进多少以及旁观者可看到什么。

简单按中断频率报警会遇到正常中断风暴与误报；随机延迟若仍能让攻击者判断有无前进，也可能只降低速度。AEX-Notify提出可信中断感知原语，再用受保护软件改变恢复点附近的执行行为，破坏确定性单步所依赖的条件。

## 3. 威胁模型、假设与明确目标

攻击者控制OS/VMM、系统设置、页表允许修改部分、APIC计时和IPI，可反复运行enclave并在其他核或SMT sibling执行。保护目标是阻断确定性、完美逐指令执行控制，而非清除全部侧信道或保证OS给enclave分配CPU时间。

enclave遵守x86-64 System-V ABI，正确使用128-byte red zone，启用后栈位于受保护区域；内存安全、合法指令及并发同步正确。代码/数据页分离，攻击者知道代码页RET字节位置与栈页高位地址。这些条件不是AEX硬件自行证明的性质。

G1是隐藏指令粒度的前进程度、阻断可靠single/zero-step；G2要求缓解自身不比原应用多泄漏；G3保持计算语义；G4要求兼容旧硬件/ABI、低正常开销、不破坏Host接口。安全分析另要求已应用相关microcode/compiler缓解，不能把未修复的transient漏洞一并算入保护。

明确保留4KiB页访问泄漏、部分非确定性微架构侧信道及缓解自身访存的重放。无法完整预取的指令、多内存操作数、指令/数据跨页仍有限制。“攻击者只能得到更粗或更嘈杂信息”与“信息泄漏为零”是不同结论。

## 4. 根因：可被人为放大的恢复首指令

SGX退出/进入会清enclave TLB。OS清除相关页表A-bit后，恢复的第一条应用指令（EARP）触发慢速microcode-assisted page-table walk，用来更新页表属性。原本很短的指令被扩大成数百周期窗口，粗粒度APIC计时器也能较可靠地命中。

作者Ice Lake微测：清A-bit的assist均值666、标准差55 cycles，正常walk为27/30；one-shot到达时间约10957/73 cycles，500-cycle窗口预测命中约99.94%。这些是所测平台下的统计结果，不是Arm或GPU通用中断延迟常数。

A-bit还有观测用途：区分中断落在ERESUME本身还是应用已经执行。因此只加入随机等待，攻击者仍可能丢弃zero-step样本。跨核攻击也可在探测页表访问后发送IPI，绕过只随机化恢复时间的简单设计。

## 5. 硬件ISA：让可信runtime首先看到恢复事件

旧SGX以AEX把状态保存到SSA并增加CSSA，ERESUME减CSSA并恢复原状态。AEX-Notify在TCS总开关之外为各SSA frame提供AEXNOTIFY位：启用的frame被ERESUME恢复时，改走类似EENTER的固定可信入口，不直接恢复被打断的应用状态。

新EDECCSSA指令让enclave内部降低CSSA后继续，不需先EEXIT再ERESUME。它本身不自动恢复SSA全部寄存器；可信软件必须保存和恢复所需状态。AEX发生与退出机制没有变，新增的是恢复后的可信通知路径。

按frame启用很关键：大部分handler仍可像原先一样被中断/恢复，避免处理器反复只重启handler而无法前进；只有短小关键阶段启用可重启语义。论文称该可证明启用的ISA特性已纳入SGX规范，可通过microcode部署到部分既有SGX处理器；不表示所有旧硬件都自动具有能力。

这个原语证明“恢复前可信代码有执行机会”，并不证明中断的业务原因、物理设备身份、某次GPU任务成功或目标Client正确。配置支持位、实际启用位和正确运行的防御软件也需要分别检查。

## 6. 软件流程与恒时解码器

第一阶段handler保留应用状态及red zone以下持久区域，记录并清除应用AEXNOTIFY位，再以EDECCSSA进入第二阶段。第二阶段确定EARP代码页、当前/相邻栈页，以及下一条指令可能访问的数据地址，最后进入短汇编stub预取并跳回原应用。

普通Capstone/Xed解码会用opcode访问表，若此时被single-step，缓解自身就会泄漏原本要隐藏的opcode。作者用约1.4K行C、CMOV和AVX2写CTD，按照恒时访存/控制流规则求操作数地址，不把一个新的查表侧信道引入恢复入口。

CTD要求不报告原应用不会做的访存，允许对不支持指令漏报。漏报时保留代码/栈预取，但不能保证非栈数据操作数也被预取。最多16字节的输入缓冲避免跨代码页取指，防止是否访问相邻页暴露RIP页内位置；这不是声称x86最大指令长度为16字节。

论文附录B明确不支持RIP-relative、全部三字节opcode，以及部分x87/VEX/EVEX等指令。98.0%是所选106个runtime二进制的静态指令覆盖，不能解释为98%的所有秘密路径已证明安全，或所有运行时间的98%已覆盖。

## 7. R/W/X权限和可重启预取

只读页面不能保证后续写入不触发D-bit assist，只读代码也不能验证可执行权限。作者提前对写目标读一个byte再写回相同值，触发正确的写权限/D-bit检查；代码页寻找RET字节并实际CALL/RET，用执行访问验证XD权限。

写回依赖普通内存语义和正确同步；LOCK/XCHG等原子访问不被直接当成普通写预触发。没有RET的页无法按此方式验证，代码/操作数跨页及多个内存操作数仍有预取不足边界。预取并非任意指令或任意MMIO上的无副作用操作。

关键stub启用AEX-Notify后预取工作集。此时若被中断，下一次进入handler会恢复原参数，重新执行这段预取，而非从半完成位置直接继续；“原子”是按重启语义形成的逻辑区域，不是屏蔽了所有中断或硬件事务。

stub按64条cache line预热每个4KiB页，再恢复寄存器跳回EARP；50%概率加入20-cycle小延迟，仅为额外干扰，主机制是去掉慢首指令窗口并隐藏前进程度。随机数在较大C阶段提前准备，避免RDRAND延迟暴露关键阶段行为。

对于GPU，重复写doorbell、重发任务、读清中断状态或写回MMIO“相同值”均可能改变设备状态。因此不能把可重启预取直接迁移为可重复执行GPU提交；要先证明操作幂等或让外部副作用受可信状态机控制。

## 8. 作者安全论证的强度和限制

G2依赖CTD恒时、页粒度访问、只触碰原应用合法地址、已知代码布局，以及不预取enclave外地址。关键阶段页内对齐，恢复/回滚用CMOV，防止攻击者判断中断是否已经越过EARP；这些软件细节与硬件通知同等重要。

G1还依赖攻击者无法把计时器稳定命中极短EARP，以及无法可靠地在预取和EARP之间重新驱逐工作集。作者考虑SMT TLB contention、cache竞争/禁用和更精细计时，给出经验和统计分析；这不是覆盖未来所有微架构、编译器和自适应攻击策略的形式化定理。

连续n条都精确单步的概率用p的n次方建模；正文以p=0.22、n=10得约2.66×10^-7、平均约376万轮，并依赖攻击者不能区分成功轮。将此式当成部署安全界，需要条件独立、对应指令命中概率、重复机会和不可区分前进等前提；一个平台单指令测量不能直接推出任意任务或系统全寿命的统一失败上界。

论文不量化所有高分辨率侧信道的改善，也不保护页粒度controlled channel。对不支持指令的秘密路径，作者“预期罕见”是工作负载判断，不能替代覆盖证明。对机密GPU任务更不能据此宣布完整中断侧信道已解决。

## 9. 平台、实验和定量结果

作者使用支持SGX2/AEX-Notify的Ice Lake和Coffee Lake E服务器，部分实验关闭C-states/SpeedStep以提高攻击计时条件。附录APIC平台为2.4GHz Ice Lake，APIC晶振一tick约320 core cycles。本文未运行这些设置或框架。

| 实验 | 作者结果与正确解释 |
| --- | --- |
| Table1，Coffee Lake E，每种100000次 | 无干扰single-step命中0.042；清A-bit 0.107；L1竞争0.118/0.112；L2竞争0.114/0.126/0.223；L3竞争0.141/0.030/0.104。是一次EARP命中率，不是完整攻击成功率或零泄漏 |
| Ice Lake关闭cache | 10000次、约2小时；single-step 0.08%；恢复与缓解耗时从均值8052/标准差31升至4117125/1063928 cycles。变慢且噪声增加，不意味着防御保证可用性 |
| CTD差分 | 对比Xed v2022.10.11枚举1.6143亿输入组合；忽略非法/SGX不支持指令，不支持的CTD结果要求为无访存，覆盖条件有明确范围 |
| CTD动态恒时 | Dudect运行24小时、超过370万次未发现timing violation；未检出不是一般性恒时证明 |
| CTD静态分析 | 修改输入API并人工增加SIMD语义后，用Pitchfork分析LLVM11的O1/O2/O3/Oz IR；不等于完整runtime、CPU实现及任意编译二进制均已验证 |
| CTD耗时 | Ice Lake冷729.15、热369.00 cycles；热态循环100万次、每项六轮取几何均值 |
| 整体恢复开销 | 约6500→10300 cycles，增加约58%；假设每100万cycle一个中断，摊销低于0.4%，不是实测全部应用均低于0.4% |

Table2按SGX SDK v2.18.1、Gramine v1.3.1、Occlum v0.29.4收集18/53/35个二进制，共475万条静态指令；总覆盖98.0%，其中65.9%可由默认代码/栈预取覆盖、32.0%依赖CTD。默认覆盖与CTD额外贡献分别列出，不能把两者都算成CTD独立覆盖。

附录A每项100000次：one-shot约10957/73、普通syscall设置TSC-deadline约10859/438、自定义IRQ-gate约10918/38 cycles；图7标注对应10956/72、10858/438、10918/37，正文与图有轻微差异，保留口径不强行统一。跨物理核IPI约935/27，同物理核SMT约1772/174 cycles，均不能作为本项目Arm GIC/SGI延迟基线。

论文没有GPU、多Client、CCA Realm或LLM端到端吞吐实验。正常中断频率下的摊销估计不适用于高频GPU完成通知，也不能据计时器精度推导本项目native fence/IRQ127的性能。

## 10. 固定公开代码与版本范围

Intel旧linux-sgx入口现重定向到confidential-computing.sgx。固定顶层commit为3ab6a6bdb97adc76f690c0083c618bb98992fde7（2026-08-12），完整递归tree1162项、未截断；README说明从2.30版开始SDK独立，并以gitlink固定到confidential-computing.sgx.sdk的73ae8ba0140f9295ef62245897c578c76c289341。子仓库完整tree3894项、未截断。

这两个固定版本是后来公开集成证据，不是论文评估版本；没有证明其与论文所有原始脚本、microcode或二进制相同。[固定SDK快照](https://github.com/intel/confidential-computing.sgx.sdk/tree/73ae8ba0140f9295ef62245897c578c76c289341)。没有因完整tree可得就声称全面读取全部源码。

完整读取SampleAEXNotify README、enclave样例/配置、sgx_trts_aex.h、trts_aex.cpp、ctd.h、trts_mitigation.h和关键预取汇编主体；定向读取trts_veh.cpp恢复点选择、CTD调用、地址检查、二阶段分发/切换，ctd.c的CMOV/固定扫描/寄存器选择及ct_decode主体。没有逐项审计全部opcode表、完整汇编入口、loader/证明栈、硬件实现或论文评估脚本。

README要求硬件支持及in-kernel driver至少6.2；样例配置EnableAEXNotify=1且DisableDebug=0并提示正式版关闭debug。样例handler只计数，不提供新的任务来源认证；未执行样例，不能把它当生产机密模式验收。

sgx_set_ssa_aexnotify检查self-report的SGX_FLAGS_AEX_NOTIFY后更新可信SSA；register/unregister临时关闭通知，修改每线程handler链，再恢复开关。API头明确node在注销前必须持续有效。这是可信runtime内部生命周期要求，不是任何外部通知携带handler指针都可接受的接口。

trts_veh.cpp在触发AEX缓解时先执行自定义handler，再进入恒时SGX-Step缓解；注释明确自定义handler阶段不启用AEX-Notify。故“注册了handler”本身不证明handler恒时、不受单步或有可信业务事件来源。目标数据地址还有sgx_is_within_enclave检查，避免普通外部内存预取的额外风险。

## 11. 论文与后来代码的具体差异

当前SDK在代码页找不到C3时，fallback到runtime的__ct_mitigation_ret，不能把此fallback说成已验证原EARP代码页的execute权限。论文也承认无C3时不能以该方法验证；没有构造利用，不宣称这就是一个新的可达漏洞。

当前CTD明确用base==16时返回无数据访存，保留RIP-relative不支持边界；对代码页末16字节输入还使用全1掩码来避免错误地址。不能以98%旧样本覆盖认定这些未支持路径已经补全，亦不把源码中的修复注释当作独立攻击实验。

当前汇编预留区宏为9×8=72字节，论文描述120字节；当前C3调用位于64次line预热循环之前，论文附录C把调用放在循环内。两处都是已经读到的版本差异，没有证明这些变化削弱或增强安全；原论文性能和分析不能不加核验地套到当前代码。

当前C3 cache在汇编中定义为全局4KB表，而正文描述thread-local cache；缓存记录只作候选offset并再次验证字节。本文没有完整并发审计，也不把布局差异直接升级为信息泄漏或任意跳转结论。

这些观察限定于固定后来SDK与实际已读路径。没有运行Pitchfork、Dudect、Xed、编译器或SGX-Step，没有复现论文统计，更没有确认所有入口、重入与寄存器保存不变量。

## 12. 与库内中断/CCA论文如何组合

| 工作 | 能支持的问题 | 不能替代的责任 |
| --- | --- | --- |
| AEX-Notify | 可信恢复钩子、破坏精确执行控制、缓解自身泄漏 | GPU事件来源、job终态、Client路由和撤销 |
| CURE | SM陷入入口、实际物理身份、共享区转权与IPI | 多Client GPU专用完成及reset后在途协议 |
| Devlore | 设备真实IRQ保护与合法注入规则 | 单凭IRQ断言特定GPU结果成功/可见 |
| Heckler/WeSee/Sigy | 恶意异常、注入与handler副作用 | 仅靠中断频率或恢复感知判断业务授权 |
| PORTAL/CAGE/ACAI | 可信设备服务、执行/映射授权边界 | 自动消除任务完成时序和跨Client观测泄漏 |

Sigy只需一次软件事件或正常退出时机的情形，不能指望破坏精确single-step就全部阻断。CURE的trap hook与AEX-Notify同样说明“受保护代码知道发生中断”只是基础；多VM场景仍需说明中断源、目标身份、前态、代次、输出可见和副作用。

本项目保持RMM认证原始Client、可信ProxyRealm统一控制SMMU、建图检查对象/实际页/权限/生命周期、软件IPA→HPA合成受保护直接HPA Stage-1及其他设备硬件Stage-2的假设。未用x86/APIC与RK3588的硬件差异否定研究设计；可迁移的是论证方法和状态约束。

## 13. 对当前GPU项目的设计建议

第一，把“可信完成通知”与“中断观测隐私”分别立项。前者要求已有认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127组成完整身份/状态链；后者需要定义哪些时刻、次数、目标和队列统计可被谁观察，以及希望保护到何种粒度。

第二，保持唤醒与授权分离：IRQ推动读取可信记录；只有绑定原始Client实例、context、job和当前代次的合法终态才可发布成功、解除等待或授权回收。来自可信入口的中断仍可能是错误、重复、共享源或旧代晚到事件，不能按“进入handler”直接改变任务语义。

第三，限制handler本身的副作用和重入。短路径只消费既有可信状态并执行明确状态转换；取消、reset、释放和重试分别约束。对可能重复执行的GPU写寄存器/doorbell，必须论证幂等或去重，不把AEX的回滚预取设计泛化为可以回滚真实设备执行。

第四，若研究时序隐私，可评估按Client安全域聚合发布、限制诊断/计数器可见性、按公开调度窗口处理完成记录等方案，但先声明允许泄漏与延迟目标。随机延迟不能单独证明安全，批处理也不能以延迟降低或吞吐变化代替泄漏评估；本轮没有要求改代码或新增默认策略。

第五，分别设计验证：事件来源/代次/终态的完整性检查；重复中断及handler重入；错误/取消与成功互斥；完成记录发布前的可见性；高频或跨Client中断下的观测相关性和受害者进展。作者APIC命中率不作为GPU IRQ安全阈值，也不沿用旧功能PASS声称这些场景已测。

独立判断：AEX-Notify让项目对“中断安全”的论证更完整，因为它揭示了可信来源之外的执行控制攻击面，也要求缓解代码自身不引入泄漏。最适合迁移的是可信恢复入口、明确泄漏模型和可重复操作的严格条件；它没有替项目解决GPU任务归属、完成认证和撤销后安全复用。

统一记录：正式全文/全部附录/书目、固定后来SDK有界静态阅读及版本比较｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无SGX/SGX-Step/分析器/编译/攻击或硬件run-id及新增PASS｜保留概率模型、未支持指令、作者评估版和当前代码差异。
