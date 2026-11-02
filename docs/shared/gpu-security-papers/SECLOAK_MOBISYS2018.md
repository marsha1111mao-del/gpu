# SeCloak：可信外设控制、共享中断转发与撤销边界

研读日期：2026-10-28。完整阅读13页作者公开全文、§1–7和69条引用，八页arXiv图像及两页作者会议版图像核对；固定代码的383个Git blob完整性校验，关键入口/仿真/中断路径静态分析。无硬件、构建或攻击执行。本文是Arm可信I/O支撑研究，不计作GPU TEE架构。

## 1. 书目与来源

| 项目 | 内容 |
| --- | --- |
| 全文标题 | SeCloak: ARM Trustzone-based Mobile Peripheral Control |
| 作者 | Matthew Lentz、Rijurekha Sen、Peter Druschel、Bobby Bhattacharjee |
| 发表 | MobiSys 2018，会议日期2018-06-10–15，13页；Crossref页码1–13 |
| DOI | [10.1145/3210240.3210334](https://doi.org/10.1145/3210240.3210334)，Crossref短标题为SeCloak |
| 作者项目页 | [UMD secureio](https://www.cs.umd.edu/projects/secureio/) |
| 作者会议版全文 | [secloak_mobisys2018.pdf](https://www.cs.umd.edu/projects/secureio/secloak_mobisys2018.pdf) |
| 作者会议版SHA256 | `9abc1a53dc0b9a5f1a9bee5d76786f46dde53cca4e82b3579de0fab63da14918` |
| arXiv版本 | [2001.08840v1](https://arxiv.org/abs/2001.08840v1)，2020-01-23上传，不误写为2020年首次发表 |
| arXiv PDF SHA256 | `db4ed4690ae0d11b2a071da4313c32434fefc147f1357a9eb450b3c971ce0521` |
| 作者明确链接代码 | [mattlentz/secloak-kernel](https://github.com/mattlentz/secloak-kernel/tree/e008daa89b5df3f8b6b00d406336a15aa2fa8c2b) |

arXiv初次下载仅1075528/1383651字节且缺EOF，未当完整全文；按HTTP206/Content-Range恢复后严格解析全部13页。随后从论文明确给出的项目页取得作者会议版1285202字节，逐项比较全文提取差异：正文相同，主要差异为arXiv水印及引用URL换行/排版。作者会议版有重复ToUnicode字典键，pypdf严格模式拒绝；非严格模式及独立PDFium均可读取13页，两个关键页面渲染核对，不宣称严格解析通过或文件损坏。

正式项目页直接指向同名GitHub仓库；固定提交 `e008daa89b5df3f8b6b00d406336a15aa2fa8c2b` 的430项树无截断，383个blob校验通过，其中一个符号链接按链接目标文本校验，不能按被链接文件内容计算Git hash。归档SHA256为 `3b92d6bbb29caf86c542e9bd483b39d6aa4a736b17bb83abaa27b429dcb708ed`。以下源码结论限定固定版本，非作者全部实验版本。

## 2. 研究问题、目标与可信基

目标是在Android、Linux和应用可能被攻破时，让用户可靠控制摄像头、麦克风、无线电等外设的可用性，同时尽量保持系统可用和可信代码小。其核心是二元访问控制，不是对仍运行的GPU任务建立机密执行、数学正确性或多租户共享保证。

作者信任硬件、Boot ROM、bootloader和s-kernel，并要求设备树准确、完整且由可信源签名。攻击者可控制普通世界OS、模块、框架与应用。设备树不是普通枚举提示：遗漏的总线master、外设或保护依赖可能破坏整个访问控制。原文“verifiably”指用户可由可信指示确认状态，明确不指形式化证明。

安全启动链以硬件信任根验证bootloader，再验证s-kernel和设备树。论文描述该部署假设，不等于公开启动脚本已实现所有密钥熔断、签名和防回滚；本轮未对整条启动供应链做完整审计。物理攻击、恶意硬件与外围固件的独立恶意行为没有被一般性验证。

## 3. 架构与控制路径

s-kernel运行于TrustZone安全世界，基于大幅裁减的OP-TEE；配置SCR异常/中断路由、TZASC内存权限和`i.MX6` CSU外设权限。普通世界继续运行主要驱动，安全侧仅保留GIC、GPIO/按键、framebuffer等必要驱动。

设备树增加class和protect属性：前者把底层资源映射到camera/wifi等用户可理解的类别，后者指定硬件保护配置。若设备本身无法独立隔离，则沿父总线寻找保护点，再用MMIO仿真保留同组其他设备的访问。共享保护粒度、依赖关系和别名是授权的一部分，不能只检查一个外设节点。

不可信Android界面提交设置bitvector，经JNI、内核模块和SMC进入s-kernel。可信侧独占framebuffer和硬件按键，重新显示收到的设置，点亮普通世界无法控制的LED，等待用户确认，再应用策略。这样授权依据是可信界面中实际确认的内容，不是最初普通世界请求里的声明。

framebuffer的安全目标是显示完整性。为让配置为non-secure的IPU DMA读取显示缓冲，论文将该区域配置为普通世界可读、安全世界可读写，明确允许普通OS看到确认画面。不能称其具备屏幕内容机密性；对于含秘密的GPU输出，不能直接沿用该放宽方式。

## 4. 中断所有权与普通世界转发

s-kernel控制GIC的enable、priority、CPU mask和security group。GPIO等共享外设的真实中断由可信侧接收；普通世界设备树使用另一条原本未使用的中断线。可信侧决定某事件应转发时，将对应普通世界中断置pending。

共享GPIO寄存器也受仿真：可信按键事件可被安全handler消费，其他事件可转给普通世界。只改中断号而不隔离status/mask/ack寄存器会留下旁路，因此论文把中断重投递与MMIO视图过滤结合；这是比“物理IRQ转给哪个VM”更完整的设计视角。

固定源码中，GPIO handler维护secure_mask与passed_irq_mask。ITRR_HANDLED事件在可信侧ack；ITRR_HANDLED_PASS及允许转发事件记录到passed_irq_mask、暂时mask，再irq_raise普通世界线路。普通世界对ISR的允许ack触发清除转发位并重新使能；GIC raise最终写ISPENDR。该流程可作为分离真实IRQ、授权转发和ack职责的参考。

但SeCloak没有GPU job身份、原始Client认证、cookie/epoch、每任务native fence或跨VM终态协议。pending位本质是通知状态，可以合并多个事件；不能据它保证逐事件计数、顺序、恰好一次消费或任务成功。普通OS也可能延迟/丢弃转发，论文没有提供完整公平性或有界送达证明。

## 5. DMA、访问撤销和实际关闭的区别

作者将DMA master设为non-secure，阻止其读写s-kernel内存；IPU显示读取采用上面的有限放宽。CPU MMIO拦截与DMA数据路径保护分别实施，不能认为拦住CPU对寄存器的访问就已经撤销所有设备DMA能力。

§5.1明确说明：如果先由硬件防火墙拒绝设备访问，普通驱动的电源管理可能失败，设备可继续处在高功耗活动状态。为保持稳定，Android app先调用系统服务正常禁用设备，再应用安全策略；重新启用时反序操作。良性OS配合提升可用性，但在恶意OS模型下不能把它当硬件停机证明。

因此论文的“off”首先是被保护资源不可再由普通世界访问，不自动证明无线电已停止发射、预排队DMA已结束或先前获得的设备数据已擦除。对于本项目，撤销后回收必须另证停止执行、DMA静默、TLB/cache失效及残留清理；这不是否定其明确的访问控制目标。

重启策略同样是安全设计：只要有外设受保护，普通世界不能通过PSCI重启解除限制；用户可用可信硬件按键序列重启，但新启动默认无保护，策略不持久。必须覆盖其他reset/watchdog/power路径才能建立完整保证；本轮未完成该平台全部复位源审计，不把论文PSCI论述扩展为所有故障模型的证明。

## 6. MMIO陷入仿真与公开实现边界

硬件保护使普通世界MMIO产生external abort，SCR路由到monitor。可信侧读取保存的寄存器、把普通世界指令地址和数据地址转为物理地址，检查指令来自非安全RAM、数据属于设备区，再解码load/store，按策略拒绝、执行或修改值，最后更新普通世界寄存器并返回。

Linux需要把设备映射改为strongly-ordered以获得精确fault，论文称一处代码/单字节修改；另需SMC模块及Android服务调用。因此“完全不改现有软件”是设计方向而非原型事实。不配合的恶意OS仍被硬件隔离，但不保证正确仿真与可用性。

本轮完整读取README、`core/arch/arm/secloak/entry.c`和`emulation.c`；定向读取GPIO状态过滤、IRQ处理、GIC安全组/pending、SMC入口声明与平台分发及PSCI通用路径。全部blob哈希验证不是全部源文件安全审计；GPIO/GIC其他路径、汇编decoder上下文、bootloader和Linux补丁尚未全部审计。

固定代码`emu_check`默认allowed=true，只与匹配region策略相与，范围判断为base≤address≤base+size，且策略不接收访问宽度。需要核对未知地址默认策略、区间末端、加法溢出、跨边界/非对齐访问和多种MMIO宽度，不能把“地址落在大MMIO区域”当逐寄存器授权。

GPIO策略对若干寄存器按精确offset处理，其他offset默认允许；GPIO_PSR读取隐藏安全位的代码因兼容性FIXME而被注释。这与论文“不泄漏被保护GPIO信息”的一般性描述之间存在公开实现边界。是否能观察某个实际敏感引脚还取决于硬件连线、状态及可达路径，本轮没有攻击复现。

入口还有三处静态可核对问题：GET分支比较a1而头文件约定函数ID在a0；trylock失败后也走unlock标签；非法group值会panic。它们需要接口、并发和拒绝服务验证，不能因参数仅为bitvector就忽略不可信输入。本文不声称这些静态问题已导致端到端安全绕过。

源码采用“先启用所有class，再禁用所选class”处理一个设备属于多个class的顺序问题。该设计提示应定义多策略合并为拒绝优先并保证更新原子性；多核下临时开放窗口是否可利用需检查实际锁、硬件配置时序与其他CPU执行，本轮未给出运行结论。

## 7. 实验、TCB与性能分母

作者平台为Nitrogen6Q、`i.MX6`四核Cortex-A9，Android7.1.1/Linux4.1.15。Table1总14975 LOC/7671 statements，其中core6981、drivers2193、libraries5801；仅新增CSU驱动54行或GPIO577行不是全部TCB。Boot ROM/bootloader/硬件和其他可信固件不包含在该s-kernel代码表内。

| Table2，每条32位WiFi寄存器访问 | Load微秒 | Store微秒 |
| --- | --- | --- |
| Linux原基线 | 0.11 | 0.29 |
| Linux+strongly-ordered | 0.27 | 0.33 |
| 安全侧陷入仿真 | 1.14 | 1.19 |

每类指令执行一百万次、五次试验取平均。strong ordering相对原基线约2.45/1.14倍；仿真相对已强序基线约4.22/3.61倍，而相对原始Linux则约10.36/4.10倍，不能混淆分母。增量分别约1.03/0.90微秒，并非“没有单次访问开销”。

Figure5为10MB WiFi上传/下载、每条CDF各25次，图中分布近似，作者认为吞吐影响不明显，归因DMA占主要数据搬运。没有给出足够统计检验支持普遍零开销；该网络负载不能预测GPU频繁MMIO/短任务/高IRQ频率的代价。论文也未测本项目glmark、多Client GPU吞吐或中断可信协议。

安全论证依赖硬件访问阻断、最小驱动、确认路径及完整设备描述；实验主要是TCB与性能，没有系统列出的恶意OS攻击矩阵、故障注入、形式化非干扰证明或全生命周期残留验证。不能把正常功能演示等同于所有安全不变量已测。

## 8. 与本项目两部分的结合

第一部分的直通/共享实现可借鉴“复杂普通驱动保留、关键控制由小型可信层约束”，但不建议为共享GPU照搬通用load/store解码器。优先复用既有GPUVM、private plan/snapshot和已定义RPC，减少不可信方可表达的任意MMIO动作，缓存计划时保留身份、权限和版本绑定。

第二部分可将共享中断研究写成独立贡献：可信Proxy接收持久IRQ127后检查真正设备/fence状态，记录权威终态，再向认证Client发布含cookie/epoch的完成记录；虚拟IRQ仅提示读取。ack只消费通知，不能改变已记录的任务结果、提升权限或授权回收。上述是项目建议，不是SeCloak已有协议。

与PORTAL可信服务管理、ACAI身份/映射归属和PhantomMap实际页生命周期结合时，应把资源描述扩展到根配置、MMIO、IRQ、DMA master及reset/clock依赖，并在可信启动/配置时核验。设备描述签名只能证明来源，不能自行证明描述完整；对别名、共享保护组及硬件依赖仍需检查。

既定架构假设保持：RMM认证原始Client，可信ProxyRealm统一管SMMU，建立GPU direct-HPA Stage-1前完成软件IPA→HPA及实际页/对象/权限/生命周期授权，其他设备继续硬件Stage-2；实际页表、根、关键MMIO和固件受保护。硬件作为模拟载体，不用具体`i.MX/RK`能力否定该假设；当前实现以CURRENT_BASELINE为准。

应明确跨层状态顺序：停止新提交，确认运行任务终态/停止访问，撤销并完成失效，清理后才允许下一Client复用；IRQ晚到、重复/合并、reset期间和Client销毁后的通知都不能绕过该顺序。真实IRQ、业务成功、数学正确、DMA停止及安全回收分别建立证据。

## 9. 评价与记录

SeCloak的主要价值是把“可信外设控制”落实为共享硬件依赖、MMIO策略、真实中断接收与受控转发的整体方案；其可用性折衷、可读确认framebuffer、非持久策略和原型代码边界同样值得保留。它为本项目中断/控制面隔离提供支撑，不替代GPU内存与任务生命周期协议。

统一记录：13页全文、两版本文本差异、十页图像、作者项目/固定artifact来源与383blob完整性、关键路径静态分析及Notion回读另见审计｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或运行PASS｜保留研究；完整启动、固件/复位、并发和项目设计待验证。
