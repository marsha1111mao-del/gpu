# StepOverflow：性能计数器溢出中断与机密 GPU 服务的观测边界

研读日期：2026-10-28。完整阅读会议官方九页PDF、§1–10、25条参考文献、附录A/B、三个代码清单和唯一表格；第4/5/6/9页渲染视觉核对。作者artifact固定提交、完整16项树及全部12个文件逐一校验Git blob/长度/SHA256并完整静态阅读。未执行论文代码、攻击、VM、构建或硬件测试。未改运行代码，无新增性能测量。

## 1. 文献身份与来源

StepOverflow: PMC Overflows on AMD SEV，Anja Rabich、Jonah Heller、Florian Sieck、Thomas Eisenbarth，University of Luebeck，SysTEX2026，九页，DOI [10.1145/3805690.3805727](https://doi.org/10.1145/3805690.3805727)。Crossref登记2026-04-26；论文会议页眉为April27–30，会议议程安排4月27日，不把出版日期与报告日期混为一谈。

ACM PDF返回403后，经[官方会议议程](https://systex-workshop.github.io/2026/program.html)实际引用的[议程数据](https://systex-workshop.github.io/2026/program-data.js)找到[官方PDF](https://systex-workshop.github.io/2026/papers/systex26-paper16.pdf)。数据同时直接链接作者artifact并列出Available/Reusable徽章；徽章不等于本轮完成攻击复现。

PDF保存为 `build/cca-gpu-followup-20261027/stepoverflow-paper-batch62.pdf`，484502字节，SHA256 `dea98bf68fd4919ce3d3487ccfac9b56a94a7e3e517a04a636d9d79cf08e6c68`。吕贝克研究组出版页及两作者主页均确认题名/作者/会议；全文结论以会议PDF为依据。

本文是机密VM的CPU中断与侧信道研究，不是GPU TEE架构，也未直接攻击Arm CCA。它适合补足Portal/CAGE/ACAI设备授权之外的观测面，与既有SEV-Step、WeSee、HECKLER形成不同攻击机制的对照。

## 2. 问题与可信基

攻击者控制Host OS和hypervisor，可编程PMCs和硬件中断，并假设可操纵嵌套页表项实施粗粒度controlled-channel；CPU安全机制可信，Guest私有内存/寄存器不直接可读。论文针对AMD Zen1–4允许Host访问SEV Guest计数器的条件，实测只有Zen3一台机器。

该文要回答：PMC溢出能否达到指令级中断；是否适用于SEV-SNP；能否据此恢复机密控制流。它不依赖先读出Guest明文数据；利用的是受保护执行发生了多少特定事件，以及何时将控制权交回Host。

作者背景中“TEEs encrypt memory”“仅CPU可信”属于概括，不能无条件套到所有TrustZone/CCA实现、全部I/O或本项目目标TCB。本项目还明确信任RMM、ProxyRealm及受保护设备控制链，应分别列出。

## 3. 原语：用事件决定中断时机

Host选择taken branch、conditional branch、retired instruction、return等事件，将计数器设在接近溢出的位置并打开溢出中断。溢出后Host的NMI handler读取多组计数，重置计数器并重新启用，得到按事件分段的执行轨迹。它用PMC overflow作为中断源，与SEV-Step的APIC timer逐指令打断不同。

中断在这里可能完全真实，问题仍在于不可信方能否选择秘密相关采样事件、阈值和观测粒度。仅证明中断源没有伪造，不能证明其配置授权、信息流或采样行为安全。

## 4. Skid：计数与中断不是同一时刻

Skid是事件发生到中断处理观察位置之间的延迟/指令偏移。乱序执行和处理延迟使返回IP落在触发事件之后；多个溢出还可能合并，不能把一次事件、一次通知和一次精确停止对应起来。

Listing1用两条vpxor分别触发边界，中间放大量测试指令，Host实验由IP差与div计数交叉校验。作者观测到PMC记录的执行计数可用，但溢出无法提供指令级停止。其“deterministic”用语不能解释为每次固定相同skid；附录范围相当宽。

| 测试指令 | skid平均执行条数 | 最小—最大 |
| --- | --- | --- |
| ADD reg,reg | 2043 | 1025–6689 |
| DIV reg | 105 | 53–341 |
| DIV mem | 105 | 53–332 |
| DIV mem，预先flush | 64 | 10–297 |
| LSL reg | 19 | 10–60 |
| IMUL reg | 682 | 341–2229 |

这是特定指令slide内多执行的条数，不是CPU cycles、GPU IRQ延迟或任务完成延迟。预先flush使DIV均值105→64，少41条、约39.05%，不能换算为攻击成功率或GPU性能提升。静态ADD slide另报2039±4，正文单项2043与该概括分别保留。

## 5. 从Host实验迁移到SEV-SNP

Guest IP正常不可见；论文用可由Host观察的Div Op Count校准Guest skid，而非把Host NMI的返回地址直接当作Guest RIP。实测在该机器未见与Host明显差异，不代表所有CPU或任意负载完全一致。

Listing2用秘密数组决定if分支，并插入padding以跨过skid；clflush标记入口、return事件标记结束。作者能区分数组元素，但轨迹混有Guest kernel和其他用户进程。用户/内核分别计数有助识别噪声；不自动提供目标进程身份或干净的跨VM任务归属。

## 6. TinyCrypt案例实际恢复了什么

作者直接调用TinyCrypt的 `uECC_vli_modInv()`，不是完整生产ECDSA服务。非恒定时间二进制求逆的最初连续偶数分支对应nonce k的低位连续零；较长分支出现时，轨迹偏离预先构造的“持续第一分支”lookup。攻击不需要恢复完整控制流。

目标仅包含相关代码并压缩到一个代码页，用-Os构建；关闭原有nonce masking。为模拟真实程序可见的跨页函数入口，在库内增加105条div标记，还在Host中断处理时flush TLB/cache。Guest内隔离并绑核有助获得干净轨迹，作者承认这不属于通常Host攻击者可直接保证的能力。

每个nonce只观察一次轨迹；模型和lookup由可控参考执行配合gdb逐指令建立，不是攻击时Host读出受害Guest RIP。作者报告连续零位数量存在0–5位低估，由遗漏溢出引起；没有给完整逐nonce数据、误差分布、召回率或长期密钥恢复结果。

论文引用既有hidden-number/lattice方法说明多条含部分nonce信息的签名可能用于密钥恢复，但明确把恢复长期ECDSA私钥排除在本文之外。不能将“有条件泄漏nonce低位”写成“破解SEV-SNP全部加密”或已完成端到端ECDSA私钥提取。

低估仍可能给出低位至少若干位为零的保守信息，但是否可用取决于样本选择、噪声和模型假设；本文没有实测后续恢复成功率。作者认为事件采样中断少于逐指令单步，可能更快，却未给足以计算倍数的完整吞吐对照。

## 7. 固定artifact与调试条件

官方议程直接链接 [UzL-ITS/StepOverflow](https://github.com/UzL-ITS/StepOverflow)，固定 `309f4c0e56fc8f810233fbe49c451a53eb25ee72`，2026-05-13，晚于会议。完整树16项含四个目录、12个文件；本轮全部获取并完整静态读取，没有把后续HEAD冒充作者测量时提交。

README配置EPYC7763、Ubuntu22.04.4、Linux6.16、QEMU10；AMDSEV依赖固定 `69a015ff07263bc83627df2508e9c7063ea8035f`，TinyCrypt脚本固定 `cf24c907a61c01bc2c4e1ee0ae24457c27a840a2`。本轮未获取和审计这些依赖全文；源码只读，不执行README中的系统修改或实验命令。

README启动示例均用 `-allow-debug`；launch脚本对SNP policy增加0x80000并开启VMCB dump。因此公开配方确实允许debug，不可称本轮已验证非debug复现。不过论文Guest分析明确使用PMC而非GuestIP，概念原语不能仅凭这个开关就断言必须依赖debug。需要关闭debug的独立复现才能补全证据链。

`perf_mod.c`默认针对Guest用户态，另一个retired-instruction计数器专门计Guest内核态；第0计数器启用overflow/NMI。handler按顺序读取并printk各计数，再mask、禁用/复位、重启，flush可选。不能将多组读数视作硬件原子快照，也不能把所有日志RIP解释成秘密GuestIP。

停止路径注销handler并unmask LVT，没有完整保存/恢复原MSR配置；注册失败后的软件enable状态回滚也需单独检查。这是研究工具的生命周期边界，不是可直接用于可信服务的中断管理实现。目标CPU之外返回NMI_DONE，但目标CPU的handler没有完整证明每次NMI均来自所编程事件。

## 8. 原文、源码和分析器的差异

正文Listing2是8元素数组及4000条ADD padding；当前 `dummy_target/main.c`是16元素、205条DIV padding，-O0构建。两者都是人为放慢的分支实验，不能默认为同一个被精确复现的测量配置。

正文称105条DIV插在Listing3第13/14行之间，实际 `tinycrypt.patch`放在while循环之前，与入口标记目的相符。补丁还增加LTO、缩小构建和手动输入/打印k的测试程序；打印k用于已知输入验证，不作为攻击者已读到受害秘密的证据。

`count_instructions.py`用固定页内偏移0x393识别loop，按反汇编mnemonic近似分类，并用gdb逐步形成lookup；编译器、LTO或布局变化都可能使硬编码失效。`parse_logs.py`固定减105条DIV、取前五个样本作修正、对retired instructions减1、循环尾丢200样本，以三类事件差值是否相符检测偏离。这些经验常数尚无跨构建通用性证明。

所读树未提供对应论文全部原始轨迹和完整统计输出，不能从代码可下载推导论文的0–5位误差已获独立验证。完整12文件阅读也不等于审计AMDSEV、QEMU、TinyCrypt依赖或验证硬件架构手册。

## 9. 与已有中断论文的关系

SEV-Step用timer单步并借助计数确认进度；CounterSEVeillance扩展PMC事件；StepOverflow把PMC溢出本身作为事件驱动打断源。WeSee/HECKLER强调伪造/误用异常中断带来的Guest语义破坏；本文强调真实事件中断与可观测计数泄漏。两类都说明安全边界应覆盖“谁能配置、观察、注入，以及接收方据此做什么”。

论文讨论Zen5的Guest计数访问限制与PMC virtualization、constant-time、TEEcorrelate的窗口聚合及PMC噪声防御。它没有在本文实测这些方案完整阻断攻击；AMD控制位也不能直接作为Arm CCA的实现方案。

## 10. 对当前项目代码的定向核对

本轮只读核对 `opencca/tf-rmm/runtime/core/run.c` 的PMU保存/恢复片段、`runtime/rmi/rec.c` 的MDCR配置片段、`lib/arch/src/pmu.c` 全文、`runtime/core/xshm_irq.c` 全文及RK3588配置入口；准确文件SHA另存本轮源码证据。没有完成整条Arm PMU/EL3/Host/Guest/GPU驱动审计，不据此宣称已存在可利用漏洞。

当前代码确有按Realm PMU启用状态保存恢复、以MDCR控制Guest寄存器trap的路径； `pmu_update_rec_exit()`向NS公开受使能条件约束的overflow状态。是否允许这种状态及其时间序列成为公开信息，需要在威胁模型中说明，不能只因PMU上下文已保存就声称没有观测泄漏。

`run.c`的 `ENABLE_OPENCCA_PERF` 分支跳过PMCR保存/恢复，并选择NS PMU缓冲区替代Realm私有PMU缓冲区；默认RK3588配置设0。实验观测模式必须与安全配置分开核验，但本轮未检查所有实际冻结固件的编译值，也不宣布该分支已在当前板端运行。

`xshm_irq_host_valid()`拒绝Host在一般LR中构造处于有效状态的保留IRQ，并要求最后保留slot为空；可信注入函数保留Active并添加Pending。这是IRQ127来源约束的一部分，不证明CPU PMU/GPU计数器或其他IRQ均已隔离，也不使IRQ127自身成为GPU完成证据。

## 11. 建议纳入项目的设计：观测与通知分开授权

继续接受目标假设：RMM认证原始Client，可信ProxyRealm统一控制SMMU，建图时核对对象/实际HPA/权限/生命周期，软件IPA→HPA合成受保护的GPU Stage-1；其他设备硬件Stage-2，实际页表/根配置/MMIO/固件受保护。StepOverflow不否定这些内存保证，而是指出映射授权无法单独约束PMU和事件轨迹。

建议把CPU PMU、GPU性能计数器、trace/debug、overflow使能与pending状态纳入可信配置和切换策略。默认拒绝不可信Host/其他Client对保护任务进行任意高分辨率采样；确需profiling时，按已有Client/会话授权配置允许事件、采样粒度和可公开字段。可聚合指标不等于任意事件都适合公开。

复用GPUVM、认证队列、private plan/snapshot、native fence及cookie/epoch，避免建立平行身份体系。IRQ127只触发检查受保护队列；完成必须来自绑定正确任务的真实原生fence、成功/错误终态及必要数据同步。PMU overflow、设备IRQ计数、已执行若干指令或某次Host退出均不能代替上述证明。

Client切换/reset/撤销时，要定义计数器配置与样本的归属、旧overflow处理及下一Client可见状态。状态清理应在可信控制下完成，并防止旧epoch事件作为新任务通知；与页表撤销、静止在途DMA、片上状态清理一起规定资源可移交条件。CPU上下文切换与GPU调度切换分别覆盖，不能相互代替。

## 12. 评价与后续验证

第一部分“Arm GPU直通/共享及性能”可保留可信profiling，但需分别度量采样、跨域通知、真实GPU执行和调度开销。第二部分“任务隔离”建议再拆为内存授权、完成通信完整性、观测面控制和安全资源移交四条不变量；这仍服务于原有两大部分，不必新增泛化研究主线。

建议负例包括：Host预置计数器再进入Realm；溢出恰逢退出/重入；ClientA残留overflow到ClientB；reset后旧cookie/epoch事件；关闭profiling后的旧样本读取；并发CPU PMU与GPU计数器访问；通知合并/重复/丢失时终态不误判。先审查配置/所有权，再以可控工作负载验证泄漏与开销；本轮均未执行。

若Host仍控制调度，不能仅靠可信完成协议承诺无拒绝服务、无时间侧信道或固定响应时间。应明确保证通知/结果不被伪造与跨Client错误消费，另行声明允许泄漏、可用性假设及可检测的异常范围。把“保密性仍可能通过观测失守”与“结果身份完整性”分别论证。

本篇最直接的价值，是让中断安全从“阻止虚假完成”扩展到“限制真实事件的恶意配置与观测”；其证据仍局限于单台Zen3及改造密码案例。不能把它宣传为已证明Arm GPU/CCA存在同一漏洞，也不能因平台不同忽略其协议层启示。

统一记录：会议九页全文/25参考文献/附录A/B/三清单/一表，固定artifact全部12文件静态研读、项目PMU/IRQ定向只读核对及Notion全文回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/VM/构建/攻击run-id｜保留研究结论，非debug复现、完整密钥恢复、Arm迁移及防御有效性待验证。
