# CURE：可信设备绑定、物理访问身份与中断入口隔离

研读日期：2026-10-27。完整阅读USENIX正式PDF的19页（封面加会议录1073–1090页）及107条参考文献，其中第5、8、9、10、11、15页为整页图片，已单独提取并按PDF显示方向补读。没有执行硬件、模拟器、攻击或benchmarks，没有取得可确认匹配的公开实现。未改运行代码，无新增性能测量。

## 1. 书目与原文证据

- 题名：CURE: A Security Architecture with CUstomizable and Resilient Enclaves。
- 作者：Raad Bahmani、Ferdinand Brasser、Ghada Dessouky、Patrick Jauernig、Matthias Klimmek、Ahmad-Reza Sadeghi、Emmanuel Stapf。
- 第30届USENIX Security Symposium，2021，1073–1090页；ISBN 978-1-939133-24-3。页码来自官方BibTeX，不补造DOI。
- [正式论文页面](https://www.usenix.org/conference/usenixsecurity21/presentation/bahmani)；[实际研读正式PDF](https://www.usenix.org/system/files/sec21-bahmani.pdf)；[早期arXiv记录](https://arxiv.org/abs/2010.15866)。

正式PDF为6498597字节，SHA256 7641f2ee18a4dd071cca98d7ed369177cfaa94d2e7a62da119d24a31b97d3cb5。完整响应受网络影响后，逐段核对HTTP Content-Range并合并，严格解析确认19页；未使用只有540546字节的早先不完整下载。证据为build/cca-gpu-followup-20261027/cure-complete-batch25.pdf、分页文本、范围响应及图片提取记录。

六个图片页原始分辨率均为6120×7920、RGB、FlateDecode/PNG predictor；保留原始像素流，解码后纵向翻转恢复PDF显示方向，输出2040×2640阅读图。文本提取器在这些页只有页脚，因此不能把提取文本本身当成全文阅读证据；架构、原型及图7/表4均已通过图片补读。

CURE是RISC-V原型的通用TEE及可信设备访问工作，不是CCA GPU实现。其直接价值在于可信服务边界、实际物理访问控制、设备绑定、共享内存交接和中断入口；没有将它计作另一套已经实现多Realm GPU共享的系统。

## 2. 背景与贡献

仅保护user-space的enclave难以把未加密敏感数据安全交给设备，因为驱动和设备管理仍在不可信OS。把整个内核装入enclave虽然能运行驱动，却增加服务TCB，并可能把全部最高特权固件纳入信任。与此同时，固定按核或全局分配cache难以满足不同服务的隔离需求。

CURE提供user-space、kernel-space和sub-space三类边界：前者复用不可信OS服务；第二类包含内核runtime/驱动并可占用多个核；第三类只保护同一特权级中的部分代码，尤其用于把Security Monitor（SM）与其他m-mode固件分开。

核心是可信eid贯穿CPU访存、页表遍历、系统总线及共享cache，再由SM管理实际物理区域、MMIO、DMA窗口与cache ways。它不是仅靠软件约定“不修改别人的页表”，也不是仅靠数字加密保护设备数据。

## 3. 威胁模型和可信基础

攻击者可控制OS、hypervisor、任意其他enclave，以及通过软件攻陷的DMA外设；可调用SM接口创建恶意enclave，也可能利用普通固件内存破坏。安全启动保证固件初始完整性，不等于普通固件运行期无漏洞，所以sub-space隔离有独立意义。

硬件正确且可信；硬件漏洞、物理接触、故障注入和物理侧信道排除。DoS排除；enclave内部应用漏洞不由CURE修复。攻击者控制OS时可关闭系统，不应从安全隔离结论推导有界调度或服务可用性。

可信基础包括SM及密码库、eid/陷入寄存器保护、总线访问控制、cache访问和清理机制、安全启动、持久状态的完整性/回滚保护，以及具体服务自身runtime/驱动。通用Monitor很小并不能使kernel-space服务中的Linux或GPU驱动自动移出TCB。

设备内部状态可由SM清理是设计前提。论文没有把被绑定设备的计算语义、固件执行正确性和所有内部MCU的行为证明为硬件访问窗口的推论；应用应明确哪些设备内部组件可信。

## 4. 身份、证明和生命周期

服务提供方签名enclave二进制与配置，配置含资源需求、版本和全局label；设备持有独立身份密钥/证书，SM验证服务签名并产生完整性报告。原型使用Ed25519、X.509及AES-GCM，简化证书链为两把Ed25519公钥；复杂远程证明与服务后台密钥交换不在实现范围内。

label是部署身份，eid是本次载入的运行身份。第5.3.1节明确：eid仅在enclave驻留期间有效，销毁后释放并可分配给下一enclave；不能将其描述成永不复用的实例编号。OS、SM及普通固件使用固定身份，其余eid只要求同时活跃实例之间唯一。

setup顺序包括：先配置实际内存隔离；在受控区域验证二进制/配置；分配其他资源与eid；解密并验证持久状态及计数器；最后跳转入口。teardown保存状态并递增计数器，清除敏感内存/cache，再重新配置资源。数据/状态AES-GCM不能替代启动配置、物理资源或当前身份检查。

持久状态抗回滚依赖可信NVM/RPMB/eFuse等平台机制以及正确更新；正文给出架构假设，不是对断电原子性、设备reset及GPU任务日志的完整证明。服务自己创建的密钥轮换、撤销和恢复另属服务提供方责任。

## 5. 三组硬件原语

| 原语 | 实施内容 | 与安全边界的关系 |
| --- | --- | --- |
| SP1：每核eid | SM设置，访存与PTW携带当前身份；陷入SM时硬件切换为SM身份 | 普通软件不能通过填写请求参数冒充当前可信身份 |
| SP2：总线访问控制 | 主存arbiter按实际PA与eid检查；外设arbiter按MMIO权限位图；每DMA入口限制地址窗口 | 翻译、CPU实际访问、MMIO编程和设备DMA分别受约束 |
| SP3：共享cache控制 | 每line记录eid，按需独占ways并限制命中和逐出 | 主存访问过滤还需覆盖缓存命中与残留 |

原型扩展TileLink的A/C请求通道4位eid，其他通道未同样扩展。违规事务被重定向到预留零初始化区域，数据置零，同时触发SM处理的异常中断。不能只把“发出中断”当作阻止非法访存的机制，实际阻断由硬件路径完成。

切入SM前先以旧身份清理L1，再切换eid，避免恶意enclave预置dirty cache line后借SM身份写回。这是非常具体的顺序要求：有清理步骤仍需证明清理使用哪个身份，何时可授予更高权限。

SM保护自己的eid和mtvec控制权：只有SM身份允许写这些关键寄存器，trap硬件进入SM身份；安全原语的MMIO也只授权SM。相同特权级的普通固件不能随意改根入口或访问授权配置。

## 6. 设备绑定与DMA：比“页已隔离”多什么

设备MMIO可以按权限位图分给一个或多个实体；但第6.2.2节明确，DMA设备在同一时刻仅独占分配给一个enclave。该设备入口窗口允许访问指定物理region，默认不能访问其他外设；P2P或多窗口支持需要额外配置。

绑定同时要求：只有目标enclave能编程设备MMIO；设备DMA只能访问已授权物理区域；CPU侧其他实体也不能读写该区域。可信片上总线和访问控制假设下，这条私有通道无需额外加密/MAC，不表示任意不可信物理链路或共享队列都可省略认证。

设计在设备重新分配前由SM清理设备内部内存。它没有展开GPU context/command queue的完整drain、IOTLB失效完成、固件在途访存、reset后晚到完成及失败清理协议。不能把“flush internal memory”或卸载不可信OS驱动当作这些条件已经全部成立。

kernel enclave原型先让普通OS卸载设备驱动，再由SM执行关键授权和验证；保留核通过Linux hotplug脱离普通OS并启动受保护Linux runtime。OS配合步骤便于管理，不构成抵抗恶意OS的最终访问控制根，真正安全边界仍是SM和硬件原语。

## 7. 页表、共享内存和中断

user enclave页表在setup时由OS准备，SM验证其合法性及satp根位于enclave内，再放入受保护区域；预映射代码/数据避免执行期间受OS按页故障观察。动态分配的新PTE还需SM验证和写入，恶意enclave的PTW实际访存仍受eid/PA检查。

共享内存在原型中通过SM交接访问权。kernel enclave发送方完成写入后，SM把共享区域转给接收方，再通过IPI告知有新数据。访问权交接与通知存在明确关联，但论文没有给出面向GPU job的Client/context/job/epoch完成记录、通知去重、应用ACK和重传状态机。

需要区分中断类型：通用管理描述SM控制出入；user enclave通过清除异常/中断delegation使出口经过SM，可注册trap hook，在转给OS前观察可疑中断行为。kernel enclave原型只把外部中断trap到SM，本核触发的中断由受保护runtime处理。不能将两种enclave概括为“所有中断一律按同一路径处理”。

SM执行期间只禁用当前核中断，其他核继续响应。可信入口/handler hook可帮助发现基于中断的侧信道，但不自动认证一条软件signal的业务原因；真实设备IRQ也不证明特定GPU任务成功、输出已可见或DMA已经停止。

Iago返回值与OS元数据泄漏仍需user enclave自身检查；对kernel enclave的减轻依赖它自己提供服务的假设。VM保护是设计能力，RISC-V原型没有hypervisor扩展，不能声称完成了多VM设备共享和虚拟中断验证。

## 8. Cache与侧信道的准确范围

CP-BASIC要求tag和line-eid同时匹配才命中，但允许逐出其他非独占ways的line，不能作为阻断全部cache竞争时序信号的证明。CP-STRICT独占一个或多个ways，其他实体不能在这些ways中命中、占用或逐出；当前配置和资源上限由SM维护。

切换清理L1、TLB、BTB，禁用SMT或把整个物理核的线程交给同一enclave，配合受保护页表和trap hook构成作者侧信道方案。文中“已知transient攻击”的结论是2021年所列攻击与其硬件模型下的论证，不是对所有现代CPU/GPU微架构攻击的普遍定理。

CPU L2 ways隔离不覆盖GPU内部cache、MCU、共享内存总线、调度和Client可见完成时间。可借鉴“直接数据访问”和“资源竞争泄漏”分开管理，但不能把CPU cache实验直接写成GPU共享无侧信道。

## 9. 原型与可信基规模

原型基于多核in-order Rocket、每核独立MMU/TLB/BTB/L1，共享L2与一个DMA设备；Linux LTS 4.19及BusyBox 1.29.3。4位eid中0为OS、0xF为SM、0xE为固件，余13个用于活跃enclave。原型每enclave一段连续物理内存，设计允许多段；容量是原型选择，不用于否定本项目假设。

表1为SM管理544行、密码库2586行，合计3130行；Linux修改375行及模块200行不可信，普通固件3286行通过sub-space隔离移出SM可信基。文中“可形式验证”没有伴随完成的形式验证证明；不将其表述为已经验证。

user enclave约10KB库；kernel enclave加入约3MB Linux runtime。这些是服务二进制大小，与3130行Monitor代码不是同一个度量。可信驱动/应用、平台硬件及安全启动仍须纳入相应安全论证。

## 10. 性能、面积与比较条件

作者使用FPGA原型及cycle-accurate模拟，每项实验10轮；综合目标为Virtex UltraScale，LUT/寄存器是FPGA面积口径。未提供可直接复用为本项目GPU分数的测量；以下均为作者结果。

| 表2组件 | LUT / registers增量 | 正确比较基线 |
| --- | --- | --- |
| 双Rocket基线 | 61097 / 28012 | 不含L2 |
| TileLink身份扩展 | +211 / +110 | 双核基线约0.4% / 0.4% |
| 主存访问控制 | +5276 / +1055 | 双核基线8.6% / 3.8% |
| 每MMIO外设 | +248 / +107 | 双核基线约0.4% / 0.4% |
| 每DMA设备 | +112 / +72 | 双核基线约0.2% / 0.3% |
| 加入基础L2 | +30232 / +11549 | 基础L2本身成本 |
| L2 partition扩展 | +516 / +214 | 相对基础L2为1.7% / 1.8% |

不能挑选“每外设低于0.5%”代表全部安全架构面积。主存控制8.6% LUT和基础L2成本分别列出，cache增量分母又不同；正文“整个SoC约0.5%”应作为作者概述保留，不用它替换表中逐项值。

| 表3微测，毫秒 | 普通进程 | user enclave | kernel enclave |
| --- | --- | --- | --- |
| setup | 0.741 | 23.918 | 413.726 |
| 其中二进制验证 | 不适用 | 21.824 | 218.975 |
| teardown | 0.065 | 23.531 | 103.517 |
| 其中内存清理 | 不适用 | 9.384 | 50.206 |
| 切到OS | 0.008 | 0.025 | 53.308 |
| 从OS切回 | 0.078 | 0.084 | 194.747 |
| 动态分配 | 0.003 | 0.020 | 0.005 |
| 共享内存OS通信 | 未列 | 0.020 | 0.049 |

setup验证占user/kernel时间的91.3%/52.1%；清零占teardown的39.9%/45.7%。微测使用32KB、8-way L1和32-entry TLB；清TLB/L1分别28/3141 cycles。kernel runtime没有suspend，因此切到OS用“teardown但不清内存”、切回用“setup但不验证”近似，不能称原生快速VM切换延迟。

图7以普通user进程为基准，rv8/CoreMark几何均值开销为user enclave 19.70%、kernel enclave 15.33%。摘要15.33%只覆盖后者，不能作为所有enclave类型统一均值。aes/norx/qsort大量syscall及动态PTE验证导致user模式较高开销，不应把图上的全部差异归因cache flush。

表4为stress-ng双核/单核秒数及各load配置，几何均值开销0.9%，单项包括−1.29%到+4.23%，不是GPU并发或可信IRQ吞吐。并行CoreMark的OS减速分别1.56%和4.23%，后者还涉及只剩一个OS核和模拟suspend条件。

表5另外使用64KB、8-way L1及2MB、16-way L2的cycle-accurate配置，比较独占1/16 ways与独占全部16/16的单工作负载：几何均值3.09%，primes约0.18%、bigint约9.1%。这是不同cache配置和基线下的单enclave容量影响，不证明恶意多租户争用下GPU任务隔离或有界进展。

## 11. 公开实现与未完成核验

正式论文与USENIX页面没有提供已确认匹配的源码入口；有界GitHub查询CURE加enclave返回0项。尝试作者机构publication入口也未确认可用artifact。没有据此断言作者从未公开代码，更没有把同名仓库或上游Rocket/Keystone当作CURE完整实现。

因此，本报告没有固定可确认的CURE实现commit，也没有完成源码级trap、DMA、cache或并发路径审计。理论设计、原型描述与作者性能表已分别核对；reset后停止访问、eid复用清理和IPI事件队列仍只能依正文分析，不能声称已从代码证明。

## 12. 与现有文献及项目的关系

CURE和PORTAL都支持把设备服务放入受保护的特权执行环境，但CURE依赖新总线身份原语，PORTAL利用CCA服务Realm；不能混称两者相同硬件机制。相对ACAI，CURE强调实际PA访问过滤及设备绑定；ACAI的CPU/DMA映射归属一致性仍需在具体翻译系统中成立。

CAGE/StrongBox的GPU任务保护还要处理设备上下文、控制寄存器、提交及完成；CURE未完成这些GPU专用协议。PhantomMap关注实际页与映射生命周期，进一步支持把“配置表面合法”与“最终页当前获授权”分开。MOLE说明设备内部MCU/固件的可信假设也不能被片外DMA窗口自动替代。

与Elasticlave相比，CURE共享region由SM切换访问权并IPI通知；Elasticlave明确区分owner、权限上限与独占权转交。两者均提示通知和访问权有关，但都不能直接替代多Realm GPU job终态、ACK、错误恢复及安全回收证明。Heckler/WeSee/Sigy提醒可信handler仍需限制输入来源和可授权副作用；CURE的trap hook主要针对中断观测与侧信道。

本项目继续采用既定假设：RMM认证原始Client，可信ProxyRealm统一控制SMMU，在映射建立阶段检查对象/实际页/权限/生命周期，软件IPA→HPA合成为受保护直接HPA Stage-1；其他设备保持硬件Stage-2。没有以RK3588原型能力否定该研究模型。

当前认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127作为已有基础。CURE带来的增量不是再加一个身份字段或换一条中断线，而是明确现有字段和控制操作在跨组件组合时的安全责任。

## 13. 可迁移的研究问题与验证提案

第一，写出身份闭合不变量：原始Client实例、GPUVM/context、受保护页表根、提交任务、可信完成记录和目标唤醒必须一致。请求携带的Client号不能覆盖RMM认证身份；eid可复用的教训应落实到现有cookie/epoch在Client重建、Proxy重启和device reset后的有效域。

第二，写出顺序不变量：以原身份排空/失效旧访问能力，确认不会再写旧页，再清理敏感状态，最后才重新授权；配置已更新、IRQ已收到、普通ACK、native job终态和设备全局quiescence分别说明可证明范围。缓存写回借用更高身份的CURE例子说明“清理存在”不足以证明“顺序正确”。

第三，写出事件副作用不变量：persistent IRQ127只推动接收方读取可信状态；只有匹配本Client/任务/代次且处于合法前态的完成记录，才能发布成功、解除等待或进入回收。重复/乱序/晚到通知不能造成重复释放或把cancel/error改成success；应用消费ACK也不能代替DMA停止证据。

第四，围绕已有实现做后续验证设计：双Client各自任务完成与受害者数据不变；Client销毁重建后的旧cookie；reset前后的晚到IRQ/fence；共享对象撤销中仍在途的访问；错误完成与成功发布互斥。当前仅提出验证要求，没有新增测试PASS，更不因旧功能/性能回归通过就宣布恶意事件路径已覆盖。

综合判断：CURE是“可信服务边界＋实际访问身份＋设备控制面”很好的支撑论文，尤其有助于解释为何内存隔离仍需生命周期和中断状态机组合。它不能填补共享GPU任务完成与安全回收的全部证据；这些恰好可成为本项目第二部分的独立研究内容。

统一记录：CURE全文/图片页/书目及有界artifact取源分析｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无GPU/VM/模拟器/攻击run-id、退出码或硬件日志及新增PASS｜保留公开实现、VM原型与GPU在途协议的未核验范围。
