# SEV-Step：机密虚拟机单步观察、中断信任与 GPU 完成语义

研读日期：2026-10-28。完整阅读正式27页论文、64条书目记录，无附录；定向阅读官方固定版本的管理脚本和用户态事件API。图依据提取标签、图注和正文理解，未逐像素核对。本文研究CPU机密虚拟机的攻击观察面，属于本项目中断安全的支撑研究，不是一种CCA GPU保护架构。未改运行代码，无新增性能测量。

## 1. 原文、版本与证据

题名 SEV-Step: A Single-Stepping Framework for AMD-SEV，作者Luca Wilke、Jan Wichelmann、Anja Rabich、Thomas Eisenbarth，University of Lübeck。正式发表于IACR Transactions on Cryptographic Hardware and Embedded Systems，2024卷1期180–206页，DOI `10.46586/tches.v2024.i1.180-206`；出版日期2023-12-04，收稿2023-07-15、录用2023-09-15，不能把卷期年份误作实际发表日期。

实际阅读[正式PDF](https://tches.iacr.org/index.php/TCHES/article/download/11250/10792)，1049026字节，SHA256 `1f2bd4c2da216c3c768e77b27bf456ce73239eedf2976ffd07434c68628ea991`，严格解析27页。书目64条中Nemesis有BPS18a/BPS18b重复记录，不能据此声称64篇互不重复论文均已独立研读。

论文明确给出[官方meta仓库](https://github.com/sev-step/sev-step)。本轮固定提交 `b7fcefe27d4ef9fff67a36c2fa74cf6a7e7a9bca`，日期2024-02-15；它晚于论文发表，不冒充作者实验的准确提交。完整12条树包含8个blob和4个gitlink；8个blob均获取并核对长度、Git blob与SHA256，技术文件7份全文读，LICENSE仅取得及哈希核对。

用户态子模块固定 `caee10795a661af55ca6f433d33140dcb4fc08b1`，完整树58条，选读README、`post-startup-script.sh`、raw_spinlock.asm、sev_step_api.h、sev_step_api.c五份完整文件。host-kernel固定 `12347789b5e66d058672e3d0af3f91377ee3a44a`，但其源码、匹配KVM UAPI、QEMU、edk2和其他依赖未读；本轮不是全artifact审计。

论文、Crossref、两份树与13个blob获取记录保存在 `build/cca-gpu-followup-20261027/` 的sevstep文件中；阅读范围另见 `sevstep-reading-scope-batch53.json`。不执行仓库中的安装、CPU/MSR配置、构建、启动、清理或攻击脚本。

## 2. 研究问题和威胁模型

SEV保护guest内存和寄存器内容，不代表恶意Host无法观察执行。论文构建交互式框架，让攻击者逐步控制VM的进入与退出，结合页级定位、缓存和指令时延观察，形成更高分辨率侧信道。

攻击者控制Host与hypervisor，可修改Linux/KVM并调节CPU频率、prefetch及定时器；受害者为运行正常软件的SEV-SNP guest。guest拥有密钥不等于信任Host。SMT、debug和CPU特征接受策略需要另行区分，不能将任意能修改Host的实验配置都说成被远程证明自动排除。

物理APIC timer促使处理器VMEXIT；为避免只单步guest的定时器handler，框架在单步期间抑制相应虚拟timer注入。guest屏蔽自身中断，不能阻止属于Host控制面的物理中断导致退出。这与恶意注入业务异常、诱导可信handler执行错误操作是不同机制。

攻击知道某些GPA及其HPA位置，可以组织页跟踪和缓存集合；知道物理位置不等于得到明文读取权限。对本项目同样应区分地址翻译、访问授权、执行观测与数据完整性，不能仅因出现GPA→HPA API就推导内存保护失效。

## 3. 单步与事件控制

一次VM进入后的退出可能是zero-step、single-step或multi-step。攻击需要既能前进又尽量不跳过目标操作。论文借助guest TLB flush拉长进入后首条指令的执行窗口；清accessed bit在所测AMD上没有表现出同等作用，不能直接套用Intel SGX的AEX经验。

retired-instruction性能计数器用于判断步长；核心单步不以明文RIP为必要条件。部分测试使用调试接口确认目标函数或寄存器，应该把这些辅助测量与无需debug的攻击能力分开，不声称所有结果都依赖debug，也不声称全部实验完全不用调试支持。

页跟踪用于粗定位，APIC单步用于细粒度控制，缓存探测用于推测访问内容。一次指令退休并不意味着仅该指令留下微架构痕迹：乱序执行可使后续访问提前影响缓存，因此单步准确率与信息分类准确率不是同一个指标。

框架以ioctl配置低频操作，共享内存传递高频事件；内核等待用户态ACK再继续VMRUN。部分配置要到下一次进入/退出才生效，阻塞事件提供同步点。这些ACK是攻击者框架内部的继续执行握手，完全不构成受害guest或GPU任务成功的可信证明。

## 4. 作者测量及解释边界

平台为Dell PowerEdge R6515、第三代AMD EPYC 7763；guest Ubuntu22.10及Linux5.19.0-26 SNP内核，Host为修改的AMD5.14分支。本轮未复现，以下均为作者测量，不能当作Arm GPU或项目实测性能。

| 表1条件与timer | zero-step | single-step | multi-step |
| --- | --- | --- | --- |
| baseline，0x31 | 6401 | 1534 | 32，平均37条 |
| 清accessed bit，0x31 | 6399 | 1548 | 50，平均34条 |
| TLB flush，0x33 | 1158 | 4000 | 0 |
| TLB flush＋清accessed bit，0x33 | 1116 | 4000 | 0 |

后两行仍有zero-step；“可靠单步”指维持进展时避免multi-step，并非每次事件恰好推进一条。timer值经过平台调节，不是可跨处理器通用的安全阈值，也不是强实时进展保证。

事件处理平均为内核侧1.007ms（标准差0.0054ms）、用户态框架1.616ms（标准差0.01548ms），后者时间增加约60.48%。这是作者攻击框架的事件处理比较，不能解释为机密计算固有开销、GPU完成延迟或本项目通知开销。

缓存实验选择L2 Prime+Probe：L1噪声较大，Flush+Reload受ASID/C-bit关联的缓存标记限制；Load+Reload出现整页相关现象而原因没有完全解释。合成实验插入lfence时分类约94%，连续访问条件降至约13%，即使退休层面仍是single-step，也不能推断访问级观测完美。

## 5. 磁盘密钥恢复案例的完整前提

LUKS2场景依赖可由Host修改、缺乏认证的CAPI算法配置，使guest选择易泄漏实现。作者尝试改为CAST6，虽然解密结果错误，仍在mount失败前发生约66000次解密；这用于说明失败前存在观察窗口，不是最终AES密钥恢复路径。

最终案例还需要正确处理XTS tweak所用AES实现，并通过CPUID策略使guest不使用AES-NI。SNP允许的CPU特征策略不自动等于拥有者认可的执行配置；应由租户核对证明和可接受策略，而不是简单宣称证明失效或SNP任意配置都可被同样攻击。

作者从一次mount操作收集70次XTS解密，其中34次具有已知明文，结合机器学习解释噪声轨迹，再进行约13小时离线密钥恢复。“single trace”不等于一条指令、无需训练或一次观测立即得到密钥。论文离线硬件段称“96-core EPYC7763”，型号与核心数描述存在疑点，本报告不据此归一化算力或推算其他平台耗时。

网络采用三层dense（182/64/16）与两层dropout，使用目标访问前后各8条轨迹；表3不同条件的加密分类约86.10–90.50%，解密约25.45–69.19%。这些条件化结果不能统一替换成合成lfence实验的94%。

作者报告披露后cryptsetup CAPI parser发生修改；本轮未独立读取所链issue809、具体补丁和当前版本，不声称所有现行发行版仍可利用，也不替作者修复方案背书。项目可迁移的要求是配置来源、版本和安全策略具备认证绑定；攻击者能同时改内容与普通校验和时，单独checksum不足以证明配置可信。

## 6. 时延侧信道与防御讨论

Nemesis式指令时延实验对每种指令使用1000条滑窗、重复100次，即100000次测量。作者可区分部分高低延迟操作；相近指令需要多次测量，div的操作数与时延趋势也非简单单调。结果比SGX场景弱，不能写成任意程序控制流或所有输入均可准确重建。

论文讨论guest内禁用中断的aes-fixed-time，但Host物理中断仍能促使VM退出。AEX-Notify预热首条指令与TDX随机化进展、无进展fault限制属于其2023年语境中的防御比较；不是对2026全部平台、部署版本和侧信道的统一保证。

进展保护的核心问题是恶意观察者能否反复将机密执行切成过小片段；完成真实性的问题则是谁能将某个任务置为成功。两者可以同时研究，但防伪造通知不能自动防单步，隐藏部分时序也不能替代任务归属与真实终态校验。

## 7. 官方代码实际确认了什么

meta README说明需要配套SNP软件栈和旧KVM `tdp_mmu=0`，不是任意upstream内核通用工具；其测试Host为Ubuntu22.04.2，与论文guest环境不可混淆。launch脚本默认debug关闭，SNP基础policy为0x30000且允许SMT；allow-debug选项另设bit19。租户应认可具体policy，不能把脚本默认值当作所有产品配置。

用户态README、启动后脚本展示固定频率、core pinning、prefetch MSR和THP等条件，并提醒单QEMU实例。这里仅静态阅读；没有照搬脚本清理进程、修改本机MSR或启动虚拟机。内置示例不意味着论文全部磁盘密钥恢复代码已在该仓库核对。

`usp_poll_event`在共享spinlock内检查have_event，设置本地vm_is_paused，复制事件及附带缓存数组，再释放锁；它本身不清have_event。`usp_ack_event`持锁写event_acked=1、have_event=0并清本地暂停标记。因此poll与ACK语义不同，重复读取不能自动理解为新事件。

header明确vm_is_paused仅为用户态sanity标记，与内核实际暂停状态没有硬绑定；`is_vm_paused`也只是返回该字段。spinlock提供框架内互斥，不是跨恶意主体的身份认证。`usp_new_ctx`将debug_mode作为decrypt_vmsa请求参数，调试寄存器能力与普通事件路径在接口上可区分。

`enable_single_stepping`请求每步TLB flush，ex版本允许显式选择；GPA→HPA函数仅封装KVM ioctl并检查返回非零。`usp_close_ctx`尝试禁用单步、移除页跟踪、关闭poll API，再close/munmap；其中部分清理失败仅打印或忽略，不能从用户态函数调用顺序证明内核或设备已安全静止。

源码还存在未解锁就返回的未知事件错误分支、分配/映射检查不充分等值得审阅的处理；它运行在攻击者控制域，本轮没有验证可利用性或将其报告为项目漏洞。重要的是不将该研究工具的共享标记、拷贝和ACK直接当作跨信任域安全协议。匹配内核实现与全部异常路径仍未阅读。

## 8. 对本项目中断设计的适用边界

维持用户给定模型：RMM认证原始Client；可信ProxyRealm控制SMMU；建图时校验对象、实际HPA、权限及生命周期，软件IPA→HPA合成受保护GPU Stage-1；其他设备使用硬件Stage-2，平台保护页表、根配置、关键MMIO和固件加载。SEV-Step既没有否定该假设，也没有证明Arm Realm或GPU存在同一种APIC攻击。

| 需提供的保证 | 项目现有机制可作为的基础 | SEV-Step提醒的限制 |
| --- | --- | --- |
| 来源与接收端可信 | RMM身份、认证channel、可信IRQ路由 | 不自动隐藏Host可见退出或调度时序 |
| 通知不丢语义 | 持久pending、队列重查、IRQ127唤醒hint | 有通知不等于工作已完成 |
| 正确任务才可成功 | 原始任务归属、native fence、cookie/epoch | 本地标记或ACK不能替代真实终态 |
| 输出与资源可安全复用 | 输出同步、回调引用、撤销与静止回收 | 逻辑epoch失效不等于DMA已停止 |
| 机密执行不被细粒度观测 | 需另列时间/计数器/调度泄漏模型 | 地址与功能隔离不能自动推出非干扰 |

上轮限定代码交叉检查已读取RMM IRQ文件、endpoint305–440及Proxy545–615，本轮未重复审计整个工程。已观察到保留可信LR/INTID、认证端点、pending/ACK_ARM及native fence无error才发布cookie等机制；这些局部观察不足以证明全部reset、cancel、跨核与内存可见性交错均安全。

WeSee重点是伪造异常原因诱导可信handler副作用，Heckler重点是恶意中断handler改变guest数据/控制流，SEV-Step重点是可控退出与观察分辨率。它们共同要求审查控制面，但攻击前提和平台适用性不同，不能合称“中断绕过所有TEE内存保护”。

## 9. 可纳入论文设计的具体内容

建议第二部分“GPU任务隔离”明确两层目标：首先证明跨Client不能借通知改变任务归属、输出或回收；再说明哪些调度、完成时间和工作量信息允许被Host或其他Client观察。若不研究单步/微架构信道，应写清范围，不给可信中断通信追加未经验证的抗侧信道保证。

复用GPUVM、认证队列、私有plan/snapshot、native fence、cookie/epoch和IRQ127，不新造一套身份token。可信私有状态连接认证接收、授权提交、真实终态、输出可见与静止回收；唤醒、队列消费ACK、完成发布和资源释放各有明确依据，不能互相替代。

把安全相关配置纳入可信启动或可验证策略：固件版本、调试开放状态、允许的设备复位/频率控制、后端策略及Client绑定。测量值存在不等于租户接受配置；需要明确哪些配置可动态改变、由谁授权、改变时旧任务和映射如何收束。此处是设计建议，不是声称当前项目已交付完整远程证明策略。

验证建议包括重复/丢失/乱序IRQ、ACK无真实完成、未signal或error fence、旧cookie/epoch、重放旧描述符，以及reset/cancel与回调/回收交错。侧信道方向另测完成时序分辨率、可信服务抢占与观测面，并以成本和可保护泄漏模型评价；无限Host拒绝调度不可能由一次可信通知无条件消除。

## 10. 评价、后续与记录

论文价值是将SEV-SNP细粒度执行控制做成可交互框架，并以缓存和时延案例展示组合攻击；也诚实暴露了zero-step、OOO噪声、平台调节和密钥恢复条件。对项目最直接的启发是区分“完成可信”与“执行不可观察”，以及把配置完整性纳入威胁模型；不是要求重做已经具备的映射身份体系。

Crossref另检出SysTEX2026的StepOverflow: PMC Overflows on AMD SEV，DOI `10.1145/3805690.3805727`，2026-04-26、1–9页。当前只核对元数据，尚未取得和阅读正文，不能从题名断言其具体机制、成功率或对CCA/GPU的影响；列为后续候选，不计精读完成。

未完成项包括匹配Host内核/完整依赖审计、作者原始数据与全部攻击复现、cryptsetup补丁和当代CPU缓解核对、CCA/GPU可迁移性实验，以及本项目完整安全验证。原文阅读和限定artifact阅读已完成，部署安全与攻击复现没有完成。

统一记录：27页正式全文/64条书目、7份meta技术文件与5份用户态文件静态阅读、Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/FVP/模型/攻击run-id｜内核实现、完整artifact、补丁覆盖和GPU可迁移性未验证。
