# Hora：可信周期调度、CPU与I/O共同可用性及GPU服务窗口

## 1. 论文身份与结论

《Hora: High Assurance Periodic Availability Guarantee for Life-Critical Applications on Smartphones》，Dylan Zueck、Nathaniel Atallah、Ian Do、Zhihao Yao、Ardalan Amiri Sani；UC Irvine与NJIT。APSys2024，Kyoto，September4–5，115–121页，DOI `10.1145/3678015.3680486`。精确Crossref核对题名、五作者、页码和2024-09-04出版日期，与作者链接7页PDF一致；ACM403，未比对出版方字节。

这是基于split-trust硬件的可信CPU/I/O周期可用性研究，论文明确为ongoing work；不是CCA GPU直通实现，也没有评估GPU任务。它与本项目关联紧密的地方是：身份与内存隔离只限制“谁能访问”，不能自动保证“某Client何时一定得到CPU和设备服务”。可信中断投递也不能独立提供服务时限。

最应吸收的设计是先审批、再承诺周期窗口，并把所需CPU和I/O作为共同资源预留；最应保留的证据边界是Table1五项定理中只有1、2、4标Y，真实时间调用和镜像可用性仍标N。不能把有限调度状态证明写成恶意Host下端到端实时GPU保证。

## 2. 来源与完整阅读范围

[作者出版页](https://www.ics.uci.edu/~ardalan/publications.html)、[作者PDF](https://www.ics.uci.edu/~ardalan/papers/Zueck_APSys24.pdf)、[正式DOI](https://doi.org/10.1145/3678015.3680486)、[论文引用的OctopOS](https://github.com/trusslab/octopos)、[论文引用的硬件库](https://github.com/trusslab/octopos_hardware)。作者主页也记录2024-06-30接收消息，不将接收日期当出版日期。

取得作者PDF 611654字节，SHA256 `116ec094136d52d1cfb4c6167f8007385060dbe6318a4422fb46789c0f4f3807`；完整阅读§1–11、致谢和19条引用，2图1表，全部7页视觉核对。无性能实验表、延迟CDF或已完成真实时间上界可额外引用。

论文只直接列底层OctopOS/hardware仓库，未列Hora专用commit。限定仓库搜索出现无关同名项；作者组织API403限流，GitHub页和所猜Hora路径/README及OctopOS raw获取超时。未取得Hora scheduler、OwnedSlots构造器、Kani harness或证明日志，不声称源码审计、作者artifact验证或源码不存在。未执行作者软件、模型检查、模拟器、FPGA、设备或攻击。

额外定向阅读当前[Kani属性文档](https://model-checking.github.io/kani/reference/attributes.html)的proof harness、unwind和stub部分，帮助理解证明范围；当前文档不是作者2024年固定工具版本，也不补足未取得的harness。

## 3. 需求与威胁模型

动机是生命关键的移动伴随应用需要周期访问TEE CPU及BLE，例如每隔固定时间读取CGM并与胰岛素泵通信。正文给的是系统设计/演示，不是医疗安全认证、临床效果或已实测闭环治疗可靠性的证据。应用正确性和设备协议正确性仍有各自TCB。

攻击者可控制除目标trustlet以外的应用，包括其他TEE/untrusted域，并可破坏其正在使用的I/O域；reset后其控制被清除是硬件/架构前提。Hora scheduler被信任且不能被攻陷，split-trust硬件提供隔离；远程攻击假定由认证安全通道缓解，物理修改/攻击不在范围。

目标是阻止攻击者破坏已接受的周期承诺和目标trustlet。scheduler可以拒绝新请求；不是任何Client随时请求都必须得到资源，也没有证明所有可信应用均能公平接纳。恶意trustlet长久预留和授权撤销需要额外策略，不能只靠排期不重叠解决。

## 4. 基础硬件：会话可用性与周期可用性

split-trust将TEE及I/O置于物理隔离、CPU/内存静态分配的域，用可委派mailbox通信。请求获准后先reset目标域到干净状态，再把相应mailbox独占委派给TEE域，并限定session时长。硬件reset guard阻止scheduler在活跃会话期间重置该域；TPM协议供应用验证域的代码与freshness。

这些机制使“已获资源的会话不中途被拿走”能不依赖scheduler诚实，但原不可信scheduler仍可以拒绝未来执行。Hora将小型scheduler提升进TCB，以补上“未来也按承诺给资源”。这是信任边界变化，不是原来的硬件独占本身已能保证周期活性。

reset guard同时约束攻击者和可信管理器：一旦会话委派，不能任意抢回。由此需要严格准入与最长临时会话限制。项目若采用可抢占GPU队列、全GPU reset或每Client上下文隔离，应分别定义，不能假定等同于独立I/O域的reset语义。

## 5. 请求、预留与可信镜像

trustlet提交运行时长、周期及所需I/O域列表。接受后分配周期执行窗口，在每次窗口开始时reset TEE与所需I/O域、加载并运行trustlet、委派设备mailbox，窗口内给予共同独占资源。资源预留是跨域联合承诺，不是只给CPU时间而让I/O仍被其他任务占住。

trustlet、I/O driver等vital image应放入小型非易失可信存储，避免普通存储被Host删除或拒绝服务。镜像保密/完整性和镜像可用性不同；只签名一个Host保存的文件，不保证窗口开始时能读取它。§9还将trustlet持久密钥分区、低电与关机后恢复列为未来工作。

§3说目前仅trustlet可撤销自己的schedule，用户安全撤销仍在设计；§6的证明模型则明确“不允许移除已批准schedule”。应区分架构叙述与实际被证明的状态空间，不能推断任意动态撤销/重加均受证明保护。

## 6. 固定周期与时间槽

当前所有schedule周期等于SCHEDULE_PERIOD，各域有一份NUM_SLOTS槽表，预留连续槽。图2示例周期2小时、8槽，所以每槽15分钟；不是15分钟GPU时间片实测。§9未来才扩展不同频率、不同阶段获取不同I/O或不同资源时长。

资源委派前需获得相应TEE和I/O域的OwnedSlots。该Rust类型不实现Copy/Clone，借助移动所有权表达独占；Kani补充连续槽性质。无Copy/Clone只保证一个已创建对象不能按那些trait复制，不独立证明“同一数字区间绝不会由两个构造器重复mint”；仍需可信构造/分配入口、隐私封装、全部转换和回滚的不变量。

周期边界是重要验证点：跨末尾的连续区间如何表示、释放后如何复用、计时器回绕、域ID重用、无符号溢出和部分联合分配失败均须查看实际代码。本文没有给足源码证据，本轮不补写或指称这些路径有漏洞。

## 7. 接受后的启动延迟与先前租约

新临时请求不得覆盖已承诺schedule；新schedule之间也不得覆盖。但新批准schedule可以与批准之前的临时会话重叠，因为临时会话可能长期占据设备，若一律拒绝将难以建立周期服务。作者将临时会话最长限制为一整个SCHEDULE_PERIOD，因此称首次执行可在两个周期内启动。

独立算术解释：先前会话残余最多P，等其结束后再等待下一个相位最多接近P，总等待小于或至多约2P，具体端点取决于闭开区间、tick和reset准备时间；图2的P=2小时则设计界为约4小时。它不是“批准后一个15分钟槽内启动”。

Table1定理1写批准后NUM_SLOTS次executor调用内执行，与上段两个周期的冷启动口径需要明确activation时刻、计数起点和临时租约存在条件。没有harness不能确定作者如何连接二者；本轮记录规格澄清点，不把它宣称为已证伪调度器。

## 8. 五项定理逐一审读

| 编号 | 论文性质 | 作者状态 | 本轮如何解释 |
| --- | --- | --- | --- |
| 1 | 接受的schedule在NUM_SLOTS次executor调用内执行 | Y | 调用次数性质，不直接是真实时限；冷启动起点需澄清 |
| 2 | executor动作每NUM_SLOTS次调用重现 | Y | 离散周期重复；不自动证明某次调用按时发生 |
| 3 | executor按P/NUM_SLOTS真实周期调用，允许有界延迟 | N | 实时桥梁尚未证明 |
| 4 | schedule相互不重叠，临时委派不侵犯当前承诺 | Y | 槽所有权/准入；先前临时会话有单独过渡条件 |
| 5 | 已承诺任务与域镜像可用 | N | 存储/恢复保障尚未证明 |

1、2用归纳连接首次执行与重复；必须再接上3的可信时钟/调用频率、4的联合资源不冲突、5的镜像加载才能构成端到端周期可用性。已完成3/5这一数量只描述Table1条目状态，不能解释为系统“60%安全”或对未证明两项给概率保证。

## 9. Kani、Rust与stub的边界

作者称1583行Rust scheduler、976行proof，使用no_std，除模拟器特定代码外无unsafe；TCB还包括安全存储、trustlet、底层split-trust/root of trust、Rust编译器及Kani。1583不是全部系统TCB，也不是所有硬件/驱动经过源码验证的规模。

Kani harness用kani::any探索有效值，assert检查性质及panic路径；对硬件reset/mailbox交互使用stub，并允许硬件任意响应。论文明确这些证明不覆盖实际硬件交互实现，后者需要假定正确。允许响应任意不等于证明任意失败下仍能满足所有服务承诺，需要查看harness对失败、重试和accepted状态的建模。

当前Kani文档说明proof harness是最小验证单元，loop unwind不足会触发unwinding failure，stub在编译时替换函数。没有作者工具版本、harness、约束、unwind和结果日志，不能审计“所有可能状态”是否覆盖真实可达状态，更不能把stub动作视为真实reset完成或设备无DMA。没有运行Kani，本报告不是独立形式验证。

## 10. 真实时间和存储：论文明确未完成的部分

定理3需要有界调度执行、domain reset、程序加载和mailbox传输；作者计划迁移到ZCU102的Cortex-R5F实时处理器估计最坏时间，利用镜像大小有界、独占链路无竞争等条件。论文没有给出可信tick、最大延迟或WCET实测值，不能声称已证实任意Host无法阻止执行。

定理5需要验证安全存储简单文件系统，保证活跃schedule所需镜像完整且可用；非易失性本身不解决断电时状态一致性、回滚、空间耗尽或启动恢复。§9明确还需定义低电/关机和恢复策略，不承诺断电期间继续服务。

共享GPU引入本文没有建模的前任任务排空、不可抢占区间、GPU固件/页表/TLB状态、SMMU队列与其他Client持有引用。CPU执行窗口若不包含这些准备时间，只能保证“管理代码被运行”，不能保证GPU已能为该Client服务。

## 11. 原型与实验能证明什么

原型在split-trust emulator上替换Resource Manager。作者报告trustlet已能周期获得TEE和BLE域，并成功移植AndroidAPS的Omnipod DASH driver；完整闭环CGM读取/决策/泵控制工作流主要作为潜在使用方式描述，不能扩大成真实患者长期运行或可靠性评估。

模拟载体可以验证域委派、排期和接口设计，无需因不是商用硬件否定机制。另一方面论文没有GPU、CCA Realm、SMMU Stage-1合成或多Client图形/计算实验，没有吞吐、调度延迟、能耗或长稳数据；不从图2推导glmark分数或每任务完成界。

## 12. 对项目的可信中断与调度设计建议

项目现有RMM认证Client、可信ProxyRealm及受保护SMMU映射控制主要保证授权与隔离；若要声称有界服务，还需要让Host无法无限期阻止Proxy和目标Client被调度、可信timer触发、物理GPU IRQ处理及最终完成投递。只把虚拟IRQ注入路径移入可信层不能独立消除这些活性依赖。

建议先明确两档目标：基础保证通知不可伪造/错投/跨epoch复用，Host延迟仍允许；可选增强保证已接受Client获得有界CPU与GPU服务窗口。后一档需额外可信调度与资源预留前提，不应默认为已有CCA保密隔离附带的性质。以上是研究设计，不声称全部已经实现。

借鉴Hora的admission：接受前核CPU预算、GPU队列/执行窗口、页授权与内存预算、结果缓冲和必要固件/驱动可用性；所有资源以一次事务承诺，部分失败回滚。接受后不得被新的恶意临时请求挤占；但只预留deadline之前的提交机会不能等同保证GPU完成，需有任务时间上界或违约错误语义。

## 13. 服务窗口必须连接到任务与页面生命周期

可信窗口记录建议绑定RMM Client身份、请求ID、GPU上下文、native fence、cookie/epoch、页generation、时间预算和撤销状态。计时器到期仅意味着预算到期，不能制造成功fence或把所有页引用直接清零；物理IRQ也必须重新核查真实任务状态。

窗口切换前拒绝新提交，处理前任任务终止/排空、实际映射撤销、必要GPU/SMMU失效与访问静默，再转交资源。保留GPUVM/BO、private plan/snapshot及真实引用；无法证明旧DMA不再访问时隔离页面或停止复用。Hora的域reset清洁前提不能代替本项目共享GPU的reset影响范围与静默证明。

调度结束、任务终态、结果可见、应用正确、通知已送达、输出允许发布和物理页安全回收分别记录。周期服务可以改善活性，但不能把一项终态代替其余性质；LLM流式token按期发布也不证明模型计算正确或KV缓存归属安全。

## 14. 多Client可用性、撤销与状态证明

恶意Client可以大量提交长周期预留或故意超时；应设计授权准入、资源上限、用户/管理员可信撤销、最坏失败处理和其他Client最低服务，而不是仅保证“已接受的请求永不重叠”。撤销本身需改变epoch并排空旧状态，不能通过复用旧slot把旧通知变成新任务完成。

可先验证离散不变量：每个物理页/队列/时间槽的有效owner唯一；已接受承诺不被后续请求覆盖；实际HPA与Client一致；旧cookie/epoch不能改变当前任务。再分别验证tick真实性和可达性、handler执行时间、GPU任务/flush/drain上界与镜像可用性，避免用一个小型模型的PASS包装全部硬件行为。

## 15. 后续验证计划与未完成候选

建议负例：Host不调度Proxy、屏蔽/伪造timer、IRQ storm、旧epoch中断延迟到下一窗口、攻击者持有最长临时租约、部分资源申请失败、窗口到期但GPU未静默、reset失败、可信镜像被拒读、断电恢复与schedule撤销竞争。每例区分承诺未接受、正确超时/拒绝、任务失败、受害者服务及安全回收；本轮仅提出计划，没有执行。

与PORTAL/CAGE/ACAI的关系是补充“已授权任务的服务机会”，与Aion比较则应保留Hora对I/O reset/driver隔离、形式证明范围的差别；两者均不自动提供共享GPU全部时限。GR-T正式版、XpuTEE重新尝试作者入口仍失败，保留未完成，不用本篇可信调度支撑论文替代GPU原文精读。

## 16. 证据与统一记录

证据目录 `build/cca-gpu-followup-20261027/`：`acquisition129*.json`保存请求与错误；`hora129-full.txt`全文、`hora-render129.json`图像哈希、`hora-crossrefexact129.data`正式书目；`hora-arithmetic129.json`只含本轮周期/槽位/启动界及证明状态算术，没有运行作者模型或模拟器。

统一记录：7页全文/全图表/七页视觉/正式元数据/Kani文档定向/有限artifact发现/独立算术/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码、Kani、模拟器、攻击、构建、FPGA或硬件run-id与运行PASS｜保留研究，真实时间、存储、共享GPU交接与项目验证待完成，整体active。
