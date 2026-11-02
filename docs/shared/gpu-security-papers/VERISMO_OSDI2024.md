# VeriSMo：不可信调度下的内存状态、共享通信与证明边界

## 1. 身份、来源与阅读范围

论文：Ziqiao Zhou、Anjali、Weiteng Chen、Sishuai Gong、Chris Hawblitzel、Weidong Cui，VeriSMo: A Verified Security Module for Confidential VMs，OSDI 2024，599–614。作者公开PDF：[全文](https://ziqiaozhou.github.io/papers/verismo-osdi24.pdf)；[Microsoft Research页面](https://www.microsoft.com/en-us/research/publication/verismo-a-verified-security-module-for-confidential-vms/)；[公开实现](https://github.com/microsoft/verismo)。USENIX页面和两种PDF路径本轮返回403，不能据此判断论文不可公开获取；作者版未与USENIX文件做字节比较。

本轮完整读16页、§1–10、40条引用、5图2表13个Listing；视觉核对PDF第1、4、5、10、12、13页，覆盖全部图表。论文没有另列附录。作者PDF464442字节，SHA256为db14397c3188012bdaa82ac709a9245494183c842537acafd423dcb814c902f9。

源码固定到6bc6dd326d8b9ca30ffec57a544b13b5fadf3cb3，2026-09-18，晚于论文；完整树427项且未截断，13个选取blob均核对长度、Git SHA1、SHA256。README、security/mod、PCR、异常入口和RMP原语/权限重置等小文件完整读；monitor、内存管理、VMSA、RMP包装和SNP内存路径定向静态读。不是全部证明、工具链、启动及所有调用链审计；未运行编译、Verus、作者测试或攻击。

## 2. 与本项目的关系

这是AMD SEV-SNP/VMPL的可信服务模块与验证论文，属于CCA/GPU设计的支撑工作，没有实现Arm GPU直通、GPU TEE或GPU任务完成验证。它补充PORTAL的可信服务思路、ACAI的身份/映射归属一致性以及PhantomMap的实际页生命周期视角：可信组件即便位于TEE内，仍需证明其API、共享页处理及授权转换正确。

继续接受项目假设：RMM认证原始Client，可信ProxyRealm控制SMMU；在映射建立时按实际HPA、归属、权限和生命周期执行IPA→HPA授权翻译并生成受保护GPU Stage-1，其他设备使用授权Stage-2；页表、根、MMIO及固件可信。硬件只承担测试/模拟角色，不把AMD特性或当前实验板能力作为否定架构的依据。

## 3. 架构、接口与信任边界

VeriSMo位于每个CVM内部VMPL0，Guest OS在VMPL3，二者共享VM加密密钥但受RMP权限隔离。模块先启动、保留私有内存、唤醒AP，再通过Hyper-V中介切换到Guest。每CPU存在模块与Guest共享但Hypervisor不可访问的通信页；这页仍不可信于模块，因为Guest也可能恶意。

接口包括AP唤醒、私有/共享页转换、只允许一次的LockKernel、ExtendPCR/Attest，以及密钥派生/加解密。LockKernel移除内核代码写权并移除其他页的supervisor执行权，不证明合法代码没有漏洞。Guest追加的度量是受保护记录，不等于模块验证了每个自报事件的真实性；由度量派生密钥也不证明当前应用语义可信。

CPU/硬件与相关固件语义可信，Hypervisor和Guest OS不可信；Hypervisor可抢占、改NPT/RMP及拒绝调度。DoS与物理攻击不在保证范围。安全定理允许访问失败，因此“读到原内容或失败”不能改写成服务必定继续运行，也不能由功能/信息流证明推出所有共享微架构侧信道已解决。

## 4. 两层验证为何适合Proxy设计

机器模型层描述内存、寄存器、NPT/页表、RMP、TLB及恶意实体允许的操作，证明每次转换保持机密性和完整性。实现层用Rust ownership及Verus tracked权限表达资源唯一性、并发访问和锁不变量。机器原语的前后置条件连接两层，硬件原语的实际语义、初始正确状态、类型/字节转换公理、密码库、验证器和编译器仍在信任基础中。

这不是“用了Rust所以安全”。也不是所有assembly由定理自动覆盖：论文明确将低层primitive的后置条件作为可信规格。项目可先验证小范围授权状态机：身份与页集合检查、权限缩减、提交/完成/撤销和失败回滚；不必先把Linux驱动及GPU模型整体重写为Verus。

## 5. 实际页绑定与重新验证

核心引理要求：已验证的私有GPA绑定同一SPA，恶意Hypervisor后续操作只能保持该绑定或令访问失败；可信模块不能在已有绑定仍成立时重复验证同一GPA。VMPL0私有页不能向低VMPL授予访问，页表内存也必须私有，页表更新保持规定映射关系。

论文为简化实现证明要求VMPL0的GVA→SPA一一映射，并信任正确初始页表。这是该设计的证明条件，不能升级为“所有GPU系统必须完全禁止别名”。项目允许显式共享/合法别名时，应定义同HPA授权集合及一致权限、生命周期和失效规则，再证明不受地址别名绕过。

机密性与完整性不能只看一个validated位：论文指出Hypervisor能令其失效，而加密位约束仍对机密性重要。迁移到项目应把软件授权记录、受保护映射、设备缓存和执行状态分别建模，避免把某个软件valid标记当作持续硬件保证。

## 6. 最直接的安全案例：检查GPA仍可能泄漏秘密

§8.4.1中，恶意Guest请求将自己的页转共享；Hypervisor随后把原本存有VMPL0秘密的SPA重新绑定到该Guest的另一个GPA。模块若仅凭“这个GPA属于Guest且原来是共享页”，执行验证后立即给Guest权限，便可能发布实际SPA中的旧秘密。原GPA之后访问失败并不能挽回泄漏。

作者修复要求在成功验证后、授权低VMPL前清零新接收页。本轮独立读AMD历史修复0de111e9b85a340203759a3ab217a3e2f2be4b0b的说明和patch，确认相同攻击链及清零次序；patch另有只读BIOS/ROM区间处理，不能把任意物理区间都当普通RAM写零。没有执行该攻击，也不把历史问题归为当前全部SVSM实现漏洞。

项目对应规则：对象/IPA历史标签不足以授权当前HPA；页重新接收时必须确认当前实际归属、实例generation及内容处理规则。新分配/跨所有者复用页需要安全初始化；已有Client输入页应保持其有效内容并经授权交接，不能照搬“所有映射一律清零”。清零前仍须确保旧DMA和其他引用终止，CPU侧验证/清零本身不证明GPU静默。

## 7. 共享页：锁不能约束不可信写者

论文图4区分私有内存与非私有内存。对模块私有页，锁能建立本组件CPU间不变量；对Guest/Hypervisor共享页，即使本组件持锁，外部对端仍可写。其权限只允许复制/写入，不允许直接借用为稳定引用；要做依赖内容不变的处理，先复制到私有内存，或真正撤销外部访问使页私有。

复制也不自动提供跨字段一致快照：对端可在复制期间修改字段。安全条件是把取得的全部字节视作任意输入，对私有副本整体重新校验，之后只使用副本；若协议要求发送方一致版本，还需序号/提交语义及重试规则。项目已有private plan/snapshot可直接承接，不需要再增一套并行请求框架。

可信队列的身份认证仅约束谁能发布消息，不能省掉长度、范围、句柄归属、实际页、整数溢出和生命周期检查。完成元数据若由不可信CPU/Client可改，不能因其位于共享内存或已持锁就成为可信终态。

## 8. 安全中断：限制入口与认证完成是两个问题

SNP restricted injection使Hypervisor只能注入#HV，Guest从共享doorbell读取待处理类型；alternative injection由更高VMPL控制低VMPL中断。论文两VMPL均用restricted模式，绕开任意#VC等注入路径；未预期异常按设计终止。恶意Hypervisor仍可发提示、篡改其可写doorbell或拒绝投递，故restricted模式不认证真实设备完成，也不保证及时到达。

项目适合对应为：IRQ127只唤醒Client重查可信队列，不能直接推进任务完成、输出发布或页回收；终态由原生native fence及匹配Client/任务cookie/epoch确定。通知重复、延迟、丢失、合并都不能创建额外完成事件，旧epoch不得作用于新实例。doorbell类型和payload应只进入经校验分派路径，不能允许Host选择任意敏感处理入口。

信息流部分还要求秘密不得决定未授权可见分支或地址。项目可以将完成时间/次数是否公开写入威胁模型；仅有可信路由不能声称隐藏GPU执行时间。该论文未证明Arm GIC/Realm注入路径，也未证明GPU DMA结束或中断与原生fence的关联。

## 9. 当前固定源码：能够支持与不能支持的结论

所读VMSA AP初始化明确设置restrict_inj=1、alternate_inj=0、VMPL0。RMP primitive注释明确指出pvalidate后实际SPA可能变化，软件旧值不能保留。pvalidate范围包装检查返回码和CF，失败调用vc_terminate；不是忽略失败后继续授权。

monitor的私有/共享处理检查页号/长度有效性，在OSMEM锁下取得授权范围、拆分后处理并归并；注释说明当前共享转换依赖Hypervisor的rmpupdate失效，再验证时拒绝重复验证。`mem.rs`的osmem_adjust私有分支执行mk_private、mem_set_zeros2，再设置低VMPL权限；虽然旁有“TODO: zero all pages”旧注释，实际已有清零调用，不能据注释宣称未清零。

README称2026刷新删除过旧Verus workaround/不健全证明，同时声明近期未验证Hyper-V运行步骤，可能ABI不兼容。该声明不表示本轮验证成功，也不能概括为“源码不存在任何assume”：所读handle_attest仍以显式assume将报告标为对Guest公开，旁有information-flow declassification TODO；rmp_reset_vmpl_perm、硬件原语及IDT helper有external_body。它们扩大可信假设/去分类边界，不凭静态关键词判定可利用漏洞或整篇定理无效。

异常小文件中IDT默认填同一dummy入口；dummy执行调试输出，assembly调用后保留iretq，注释称不应返回。所读文件不足以独立确认所有未预期异常均走论文所述不可恢复终止，也没有核对完整#HV doorbell与Guest链路；不能将若干入口文件当作完整可信GPU中断实现。

PCR文件在锁内取得度量快照，再调用attest；所读上层接口没有展示论文描述的调用者nonce绑定全过程。未继续审计`secret.rs`和完整接收者验证流程，不作“已证重放漏洞”判断。项目应独立明确fresh nonce、Client/Proxy实例、固件/策略及device reset epoch绑定。

## 10. 实验与证明成本的准确口径

论文使用EPYC7543P、Hyper-V、32核机器，8核留给Host、24核给VM。微基准每接口100次取平均；Switch涵盖VMPL3→Hypervisor→VMPL0→Hypervisor→VMPL3整个往返，不是单次CPU指令或GPU中断开销。UnixBench比较的C-sm/Linux-sm只实现部分接口，不能当完整同功能安全系统等价对照。

| 项目 | 论文数据/本轮算术 | 适用边界 |
| --- | --- | --- |
| Switch / ExtendPCR | 12μs / 13μs，STD各2μs | 指定Hyper-V服务往返 |
| SetPageShared / Private | 27μs / 29μs，后者约+7.41% | 不是GPU映射或共享吞吐结果 |
| AttestPCR | 6.298ms，STD4.270ms，STD/均值约67.80% | 波动显著，不能写为恒定低延迟 |
| LockKernel 4GiB / 8GiB | 786ms / 1522ms，约1.94倍 | 每VM一次、扫描/改权限；不是稳态开销 |
| 论文验证时间 | 32核约6分钟、Z3 4.11.2 | 与README的不同年代CI时间不直接比速 |
| Table2列求和 | Exec8821、Spec6545、Proof13345、Axiom1068、Trusted262 | 包含Macro2093执行行，非整个硬件/固件/密码库TCB大小 |

论文所谓31行unsafe硬件操作不等于整个TCB31行；32个unsafe block也不同于LOC。HACL库内部、Verus/Rust编译器、规格与公理仍须可信。UnixBench近零开销不是任意工作负载保证；没有GPU、多Client攻击或Arm性能测量。当前README的验证结果数字/约3分钟/约10倍均为作者描述，本轮未执行确认，且不能与论文6分钟不加条件直接相除。

## 11. 建议落实为三个可检查不变量

第一，授权对象从RMM认证Client和受保护的实际页记录派生，动态操作只能取得本实例授权范围，失败不能留下部分新权限。第二，共享消息仅提供输入：复制后校验、私有计划提交，通知仅触发查验，完成/发布/释放分别受可信状态约束。第三，页所有权交接必须在旧任务/DMA/映射缓存与引用失效后再初始化和交给新所有者；缺少静默证据时保持隔离，不用超时或ACK替代。

优先验证负例：复制期间篡改范围/数量、锁内恶意改共享页、同GPA换HPA、验证/清零/授权次序错误、重复接收页、范围处理部分失败、旧cookie/epoch迟到、伪造doorbell类型、只有IRQ没有native fence完成、取消后仍在途DMA、证明重放及报告去分类过宽。这些是建议测试，尚未运行；不沿用历史PASS。

## 12. 证据与待办

证据目录为build/cca-gpu-followup-20261027：acquisition-batch101及后续获取清单、作者PDF与16页文本、6页render与哈希、固定commit/完整tree/13blob清单、AMD历史修复和独立算术、Notion全文回读及父页保护审计。OpenAlex本轮宽泛搜索未返回准确VeriSMo结果，不将不相关命中计为论文证据。

Erebor已核实EuroSys2025 DOI10.1145/3689031.3717464及官方ASTERISC-Release/Erebor仓库README，但尚未精读论文，不计完成。README明确区分普通VM功能模拟与TDX完整模型，公开I/O通道用明文debugfs模拟且完整代理输出待实现；这只是后续核实线索，不能替代论文安全分析。

统一记录：VeriSMo全文/40引用/5图2表13Listing/6页视觉/13固定blob限定静态阅读/AMD修复/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无构建、Verus、作者测试、模型、硬件或攻击run-id｜保留研究；当前artifact不等同论文实验快照，完整中断/证明/设备链待核验。
