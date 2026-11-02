# RealmEye（arXiv 2026）：CCA 内省、可信状态来源与授权输出边界

研读日期：2026-10-27。完整阅读14页 arXiv v1、43条参考文献，无附录；限定静态核对一个同名公开候选仓库。本文是CCA机密VM内省工作，不是GPU共享架构；关联点是RMM权限、可信观测、跨VM通信、快照与生命周期。未改运行代码，无新增性能测量。

## 1. 原文、版本和证据范围

实际阅读题名 RealmEye: Virtual Machine Introspection for Arm CCA Realm VMs，作者Ruofei Qu、Wei Feng、Hongzhan Ma、Menghan Jia、Muyan Shen、Yu Qin，单位中国科学院软件研究所及中国科学院大学。[arXiv:2608.12822v1](https://arxiv.org/abs/2608.12822v1)，2026-08-13；本轮未确认正式会议版本。PDF390982字节，SHA256 `4556ac9f38894002939ac9f9127842e4f0c9a5c091d064353e60cdb107858b77`。

完整文字包括设计、实现、评估、限制与参考文献；未逐像素渲染全部图表，以下数字来自全文文字及表格提取，不声称重算原始实验。原文摘要的“hardware-attested session”等表述需要与实现章节区分，不能直接视作原型已完成的保证。

GitHub搜索找到 [Ankaluoer/realmeye-artifact](https://github.com/Ankaluoer/realmeye-artifact)，固定提交 `2a850dcd7060e6511987644bce3362f301e7b675`，日期2026-08-22，完整递归树37项、21个blob，未截断。选取9个blob逐一核验Git hash、SHA256及长度；仅静态阅读，不执行构建、模块、驱动或测试。

候选README却称论文为“RealmEye: Confidential VM Introspection for Arm CCA under Hypervisor-Rootkit Collusion”，声称§7.2–7.4含RK3588性能/合谋评估；所读v1将OpenCCA移植列为后续工作，章节布局亦不一致。主题和代码高度匹配，但v1没有明确仓库链接，本轮未证实作者身份或取得该README对应修订全文。因此将其标为后续候选原型，不能反向补齐v1的实现与测量，也不把两个标题计成两篇已读论文。

证据集中在 `build/cca-gpu-followup-20261027/` 的realmeye、source-acquisition-batch46和publication相关文件。全文阅读候选README、LibVMI的 `cca.c` / `cca.h` 和3份测试文本；Host patch仅定向读取目标选择、命令传递、返回和ABI定义，两个大RMM文件仅定向读取翻译、加密、命令分发、周期触发及OpenCCA写陷入路径，非全仓安全审计。

## 2. 问题和威胁模型

CCA阻止Host直接读取Realm，也使传统依赖可信hypervisor的VMI失效。租户仍可能因网络/供应链攻击在自己的Realm内获得恶意内核；仅保护Realm不受云侵入，并不能证明Realm内运行的软件一直良性。论文把内省移到RMM，使监控器位于被监控内核之外。

信任RMM、相关硬件/固件及远端owner，不信任Host/hypervisor与Realm内核；针对RMM本身的攻击、物理攻击、侧信道及DoS不在目标内。R-EL2确实可隔离EL1代码，但把解析器、内核语义与密码代码加入RMM会扩大TCB和恶意输入处理面，“没有新增可信主体”不等于“没有增加可信代码”。

与PORTAL/CAGE/ACAI的分工不同：这些工作主要解决设备访问、映射与执行隔离，RealmEye试图判断Realm内部状态。它不提供可信GPU队列、GPU完成认证或设备静默协议，也不证明保护GPU内存后便无需继续考虑运行时完整性。

## 3. 核心机制：复用REC进入路径

Host经debugfs/ioctl设置待处理命令，用 `RMI_REC_ENTER` 的enter.flags bit63指示内省，参数放enter GPR，返回使用exit GPR及扩展密文区。RMM在恢复目标vCPU前、持有对应REC访问保护时执行查询，避免另开与正在运行REC冲突的同步调用；论文主路径不要求新增SMC接口。

保存的TTBR1_EL1用于软件Stage-1页表遍历，得到Realm IPA；然后调用已有 `realm_ipa_to_pa` 查询该Realm的Stage-2，短暂映射实际物理页、读取、解除映射。候选代码印证 `vmi_read_pa(rec, ipa, ...)` 的输入是IPA而非任意机器HPA，`vmi_va_to_pa` 输出也首先是IPA，命名不能替代地址空间判定。

支持L1/L2 block及L3 page描述符。候选walker按48位VA、4KB页粒度和固定掩码解析，没有根据TCR_EL1完整适配所有配置；README也承认此限制。RMM可读到内存只证明访问路径，不证明页表/链表的语义真实、解析完备或输出获owner授权。

进程检查以SP_EL0指向的task_struct和pahole获得的偏移遍历任务链，与Guest用户态视图比较。测试针对Diamorphine的getdents64隐藏，并非证明任意DKOM摘链、伪造任务结构或任意恶意内核都无法隐藏。固定偏移亦需绑定具体内核映像及配置。

syscall定位使用 `stext = VBAR_EL1 - 0x800`，在其后1MB寻找连续8个内核代码指针，再检查getdents64/kill项是否落在预期代码区。能够发现指向模块区的特定hook，但区间检查不能识别所有合法区内错误目标、内联修改；8指针模式也没有一般唯一性证明。

## 4. 关键审查一：寄存器真实不等于内核锚点可信

论文称VBAR_EL1等为CPU维护、Guest内无法伪造，因而可自主恢复可信符号。这里存在需要补充的前提：EL1内核本来可以写VBAR_EL1、TTBR1_EL1和SP_EL0。RMM读到保存的真实架构状态，不代表这些状态由可信策略选择，或者指向不可替换的唯一正确内核数据。

本工作区只读核对 `Linux-Guest-GPU/arch/arm64/mm/proc.S`：第135行 `msr vbar_el1, x9`、第140行附近 `msr sp_el0, x14`，第166行 `msr ttbr1_el1, ...`；HEAD为 `39d95dd028d485ca837bf1b3c5123db2eefbaa75`，工作树有其他修改。该证据是本地Linux的架构使用例，不是候选artifact，也不是执行过的绕过实验。

要把寄存器当安全锚点，需要额外证明可信启动测量、允许运行时切换的规则及必要的上层拦截/约束。否则“拒绝Host传入符号”只是移除一种不可信来源，未消除恶意Guest内核提供错误语义根的可能。本轮没有验证实际绕过，不把欠缺的证明写作已复现漏洞。

## 5. 关键审查二：快照、周期触发和页面监控

暂停目标REC不自动冻结同Realm其他vCPU、共享页写者和GPU/DMA。论文使用8核FVP却未明确给出所有实验的Guest vCPU一致性协议；没有完整全Realm rendezvous、共享写入隔离或设备静默证明，因而“consistent snapshot”需按实际冻结范围限定。

RMM决定是否扫描仍依赖Host触发REC进入。Host可以延迟进入并观察耗时，周期扫描不自动保证时间不可见或按墙钟必达。相同输入字段不能掩盖额外执行时长；论文排除DoS，也不能由此消除所有可观察时序。这里区分扫描决策在RMM与严格时间隐私两个目标。

后续候选OpenCCA代码以全局 `vmi_periodic_enabled` / `remaining` 计进入次数，间隔由 `1000 + ((CNTPCT ^ rec->pc) & 0x7ff)` 产生，不是独立可信定时器或经证明的密码随机调度。全局计数及单页trap变量没有按Realm/REC分区，不能直接扩为多Client隔离；这些是静态范围观察，不是已执行串扰攻击。

v1描述通过Stage-2写保护和TLB维护触发访问事件，但实现/评估未提供完整多核shootdown、写故障恢复与反复重装的证据。候选OpenCCA代码确实有清写权限、`s2tt_invalidate_page`、保存/恢复旧项的路径，并拒绝把block当page修改；README承认one-shot需re-arm。仅取得 `vmi.c` 不足以确认exit hook、全部调用上下文及实际测试均正确。

候选 `f3_target.c` 是对私有vmalloc页写入的验证刺激，`vic.c` 用合法setresuid在信号控制下切换自己的凭据，是受控时机演示而非真实rootkit。存在测试源码不等于论文v1做过这些实验，更不等于本轮运行验证通过。

## 6. 关键审查三：加密、认证和输出范围

v1实现使用硬编码预共享AES-128密钥，约100行实现，将8字节进程计数和8字节状态拼为16字节加密。论文展望由证明建立owner通道，但未给出该原型已实现证明绑定密钥协商的证据。候选FVP代码也保留固定key的单块ECB，无MAC/AEAD、nonce或新鲜性状态；不能由“密文”推出不可篡改和防重放。

候选OpenCCA新增AES-GCM，nonce由4字节固定salt与64位序号组成，AAD绑定版本、方向和序号，序号原子递增、GCM上下文加锁。相较单块ECB，确实增加认证标签等机制；但源码明确警告固定PSK/salt在重启序号归零后会重用nonce，证明根密钥建立和会话生命周期仍待完成。

更关键的是，OpenCCA分发末尾在为命令1–11生成GCM记录后，仍无条件执行 `rec_run->exit.gprs[0] = vmi_result`。Host patch从该GPR读取result_val，READ_PA/READ_VA路径还记录读到的值。加密旁路存在明文副本就不能据此声称对恶意Host隐藏同一结果；日志是否可见需结合实际部署判定，但NS exit区本身就在Host返回通道。

OpenCCA内有方向校验、认证解密和重放序号的诊断分支，但正常 `vmi_handle` 命令仍直接取Host enter GPR，本轮所见主路径没有把每条请求都接入owner认证解密/授权。不能把诊断中PASS字符串当执行结果，或把局部认证函数等同双向端到端安全通道。

AAD也未显式绑定目标Realm、REC、地址/对象、owner授权策略及本项目cookie/epoch；结果明文包含result与cmd但不能单独解决所有目标归属。部署需把授权请求、目标、输出策略、会话新鲜性一起绑定，拒绝未认证命令且避免失败后回退明文。RMM拥有读取能力不等于任意Host都获授权触发读取。

## 7. LibVMI兼容层不等于完整工具链已验证

候选 `cca.c` 中 `get_id_from_name` 固定返回1、`check_id` 接受任意ID、debugfs查找不实际使用传入name；默认512MB与1 vCPU。Host VM ioctl也明确假设同时至多一个Realm，并选择首个Realm的vCPU0。不能把这套定位机制用于证明多VM消息归属。

ABI存在需要进一步核对的接口差异：Host头将命令4定义GET_VCPUREGS、5定义PAUSE_VM，而所选OpenCCA RMM case4/5是SETUP_TRAP/HANDLE_TRAP。候选由多平台片段组成，不能直接假设是可组合的一套一致二进制；本轮不构建，只记录若直接组合会出现语义不一致的证据。

`cca_read_page` 按result_size从result_buf拷贝整页返回，而所见Host同步路径设置result_size=8、返回result_val，未在该路径填整页result_buf。若按这些片段直接对接，不能以API名称证明实际返回完整页。pause/resume及DRAKVUF兼容声明同样需要端到端测例，不由函数指针注册自动成立。

## 8. 作者FVP结果与统计边界

平台为FVP Base RevC 2xAEMvA、Fast Models11.29.42、8核4GB、Armv9.2 RME；TF-RMM v0.1.0、TF-A、Linux6.15-rc1 cca-host/v8与kvmtool。cache_state_modelled=0，未真实建模cache/TLB/pipeline；这是功能与相对模拟成本，不是RK3588或真实CCA硬件性能。

| 项目 | 作者测量/推算 | 边界 |
| --- | --- | --- |
| VA翻译 / IPA读取 / AES | 各1010次弃10次，中位4523 / 1061 / 1930计数 | 每项1000样本，IQR小于60；并非本轮测量 |
| 约50进程扫描 | 55次弃5，中位1161396，IQR13 | 预测1130750，约2.6%差异，固定对象数量 |
| syscall表定位扫描 | 单次192246222，偏移0x40a08 | 33029候选、约1.3次walk/候选；单样本不能证明分布 |
| GET_VCPUREG端到端 | 1000调用，中位502微秒，IQR33微秒 | Host墙钟及FVP运行开销，不是真实硬件延迟下限 |

论文把CNTPCT_EL0差值标cycles；通用计时器计数不自动等同CPU核心周期。本轮保留作者单位并标出来源，不按未经核对的CPU频率换算。线性成本拟合说明固定路径调用数可预测，不证明恶意输入下最坏运行时间、安全性或多租户公平。

## 9. 对当前GPU项目的设计建议

继续接受RMM认证原始Client、可信ProxyRealm统一控制SMMU、建图时检查对象归属/实际HPA授权/权限/生命周期，软件IPA→HPA合成受保护GPU Stage-1、其他设备使用Stage-2的假设。实验硬件是承载机制；本文未给出理由否定该模型，也不把候选后续OpenCCA实现当硬件安全等价证明。

第一，可信状态应来自受保护的GPUVM、认证队列、私有plan/snapshot、对象引用及native fence；Client提供的地址、页表、任务名、IRQ编号或寄存器只作为输入。验证应约束实际执行所用版本，避免把“从可信层读取”误当“内容由可信策略生成”。这是本项目建议，不称RealmEye已有GPU实现。

第二，持久IRQ127只通知检查，不能直接授权完成。接收方依据既有Client身份、queue、cookie/epoch和真实native fence终态核验结果；绑定任务/输出对象版本、成功/错误/取消状态，重复及旧epoch事件幂等拒绝。若消息经过不可信内存/Host，可在既有认证协议绑定这些字段，不另造并行身份框架。

第三，把输出和调试接口纳入隔离：安全结果不能同时在普通返回区、错误回退、跟踪日志或Host可读诊断结构留副本。检查请求授权和结果发布两端，RMM认证原始Client不自动授权Host代它发任意命令；AEAD也必须有正确nonce、重启换代、目标与方向绑定及接收侧防重放。

第四，快照与撤销按真实写者集合定义。CPU暂停/REC锁、epoch变更、消息丢弃和Timer到期都不等于GPU/DMA静默；取消/reset/Client销毁时停止新提交，处理真实在途引用及终态，完成设备与缓存/TLB必要处理后撤销/清零/回收。共享内存上的快照不能只靠冻结一个vCPU。

可评估矩阵应分别覆盖错Client/错GPUVM、错cookie/epoch、重复/乱序/延迟通知、复位后的旧完成、认证失败、明文旁路、并发Client及取消回收，检查“未授权成功不得发布、在途资源不得重用”。这里只提出后续验证目标，未执行硬件、模拟、攻击或新增测试。

## 10. 评价及后续引用链

价值是把CCA隔离后的可观测性问题显式放到RMM信任边界中，并探索复用REC接口和已有内省工具。局限是寄存器语义根、全局快照、时间隐私、owner通道与API兼容尚不能仅凭v1声明闭合；候选源码补充一些机制，同时暴露版本/ABI与明文输出等需核对边界。

继续追踪00SEVen（USENIX Security2024）、BlueGuard（2025）及OpenCCA；参考文献中的Phantom是DNN隐私工作，不是PhantomMap。另有“Trustworthy and Controllable Professional Knowledge Utilization in LLMs with TEE-GPU Execution”（arXiv2512.16238）待获取全文。这里只登记引用线索，不把未读引用算完成。

记录：改动目的｜补充CCA内省、可信观测与授权输出研究；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整14页/43参考文献及后续候选固定树、9 blob、有界静态读取；run-id、命令、退出码与日志｜无硬件run-id，batch46公开获取和发布回读证据；保留/撤回/待验证｜保留独立报告，候选作者身份/对应修订全文、端到端兼容及安全部署未验证。未改运行代码，无新增性能测量。
