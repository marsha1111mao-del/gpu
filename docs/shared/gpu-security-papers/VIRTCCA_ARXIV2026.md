# virtCCA：可信中断转发、受控单级映射与 CCA GPU 共享的边界

## 1. 论文身份和版本

本次精读《virtCCA: Virtualizing Arm CCA with TrustZone》，[arXiv:2306.11011v3](https://arxiv.org/abs/2306.11011v3)，2026-03-04，完整12页。作者为 Xiangyi Xu、Wenhao Wang、Yongzheng Wu、Chenyu Wang、Huifeng Zhu、Haocheng Ma、Benshan Mei、Zixuan Pang、Rui Hou、Yier Jin。摘要页仍使用《virtCCA: Virtualized Arm Confidential Compute Architecture with TrustZone》且作者列表含 Zhennan Min；PDF列 Benshan Mei。按同一 arXiv 标识记录差异，本文作者以v3 PDF为准，不计为两篇。

v1/v2分别发表于2023-06-19和2024-02-18，本轮没有完整阅读旧版本。未独立核实本篇正式期刊/会议版本。题名检索返回的《Enabling Confidential VMs Across Diverse ARM Platforms by Retrofitting TrustZone》（TDSC2026，DOI10.1109/TDSC.2026.3657770）作者为 Yicong Wang、Zeyu Mi、Haibo Chen，不能归作本篇的正式版或扩展版；它是另一个待核对候选。

## 2. 阅读和证据范围

完整阅读PDF §I–VII和36条参考文献；5幅编号图（Fig.3含软件注入代码，Fig.5含四子图）、6张表，6–11页视觉核对覆盖全部图表。显式v3和不带版本PDF下载字节完全一致，均745635字节，SHA-256为`d70cc37c4283fa1c689a6b3aca7f29cc90be44ce47704a2d3d27b8c4231772b9`。另取得v3 HTML，202557字节、SHA-256为`af91455b4f30912c1f9e1cda4722634358b4d087741e84ad9ba52248900c2ae3`；用于链接/身份检查，没有声称另行逐行阅读全部HTML。

有界查找取得openEuler镜像仓库`virtCCA_sdk`与`virtCCA_driver`，分别固定`0c09e24aab736625a30d424c697a0fbbd65cdc12`（2025-09-17）和`6f8c0a5f3382141999635aea42d80536db374a2e`（2026-01-19），完整递归树477/20项、均未截断。四个选定blob核对长度/Git SHA-1/SHA-256；完整阅读三个README，定向阅读内存观测驱动的声明、符号解析、属性注册与初始化/退出。没有取得并审计论文TMM核心，不把相关生态仓库视为精确实验快照或全实现验证。未执行作者代码、构建、VM、攻击或硬件测试。

## 3. 与本项目的相关性

virtCCA是Arm CVM/CCA接口和可信中断转换的支撑工作，涉及多CVM内存隔离、设备仿真和软件注入，适合与PORTAL/CAGE/ACAI对照。论文提到GPU驱动兼容性，但没有GPU共享、GPUVM、SMMU任务授权或真实GPU实验，不计作新增GPU TEE架构。

项目继续接受可信ProxyRealm管理设备授权、RMM认证原始Client、检查实际HPA归属/权限/生命周期并合成直接HPA的GPU Stage-1映射，以及保护页表/root/MMIO/固件的既定假设。其他设备使用经过授权的硬件Stage-2。论文使用不同硬件路径不构成对项目设计的否定；需要比较的是授权不变量和生命周期，而非测试板是否具备全部目标硬件能力。

## 4. 目标和威胁模型

论文用TrustZone承载CVM，把普通世界KVM/Host移出TCB；可信TMM管理执行状态、访问控制和证明。攻击者可以控制Host/Hypervisor、尝试DMA读取、启动恶意CVM。CPU、DRAM、TrustZone、ATF/TMM、可靠RoT和随机源可信；自身CVM代码漏洞、CVM主动泄密、物理攻击、DoS及侧信道不在保护范围。

§II-D明确把Hypervisor注入中断和恶意设备接口攻击视为正交问题；§IV再次说明不抵抗Host伪造中断。因此“隔离状态经过TMM保存/清理”和“中断所代表的事实真实”是不同目标，不能将本篇引用为完成中断来源认证的证据。

## 5. 两条执行路线

virtCCA-SEL2在S-EL2运行TMM、在S-EL1/0运行CVM，使用受TMM控制的Stage-2隔离不同CVM；普通世界Host仍负责调度和资源请求。virtCCA-EL3在缺少S-EL2的路径把管理逻辑放入EL3，以软件模拟中断/设备虚拟化，CPU地址路径使用受控Stage-1。TEC关联单个vCPU并保存其状态，是跨世界转换的可信上下文。

这体现“资源请求可交给不可信方，访问准入由可信层裁决”的结构，但运行于Secure world并不自动提供每Client设备隔离：同一安全世界内仍要区分CVM/Proxy/设备上下文及实际物理页归属。

## 6. 固定安全内存池

TMM在启动时保留连续安全区域，以TZASC隔离普通世界，并用buddy/slab分配大块CVM内存和TEC等小元数据。Host通过新增的分配/释放和IPA区间映射接口提出请求；NUMA优先本地节点。论文“无限CVM”应理解为不再直接受有限TZASC区间数约束，仍受池容量、元数据和调度资源限制。

固定池能减少动态迁移、委托和失效成本，代价是预留空间及资源弹性；不是取消对象授权的理由。对项目可以复用已授权BO/GPUVM和映射关系，但每次新页、权限变化、Client退出/reset及池复用仍要检查generation与有效租约，不能因来自同一Proxy池而默认属于当前Client。

## 7. 单级映射安全的条件

virtCCA-EL3把IPA与SPA设为一一对应，并将CVM页表设为只读，由TMM审查修改；论文还称移除修改`TTBRx_EL1`/`TCR_EL1`的相关指令。移除指令如何覆盖恶意CVM的新执行页、别名、动态生成代码、其他控制寄存器和并发切换，正文没有给出完整强制机制或源码证据；只修改配合型Guest不能独自证明恶意Guest隔离。

它与项目软件授权后合成GPU Stage-1的共同点，是把安全性落实到最终物理页和受保护配置。区别是项目由可信Proxy持有真实表，不允许不可信Client自行安装表或root。需要证明授权解析、提交和使用之间页归属不变，覆盖所有配置入口和缓存失效，而不能仅用“少一层翻译也能工作”作为安全论证。

## 8. SEL2中断转换

论文Fig.2的链路为：CVM执行时FIQ进入TMM，TMM将退出原因表示为IRQ，经SMC回Host；Host处理物理事件并安排vIRQ，TMM恢复CVM，由Guest处理。目的在于复用普通Linux的IRQ路径，减少Guest改动。它改变了异常传递形式，没有增加设备任务来源证明。

正文对Group1 Non-secure与后续“secure Security state”措辞不完全一致，Fig.2也没有列出全部GIC寄存器值；本轮不据其简图重新断言具体GIC配置。项目设计应明确实际中断组、路由权限、注入方和目标端点，并另外认证事件记录；可信TMM转发一个Host选择的vIRQ不等于认证GPU已完成。

## 9. EL3软件注入

Fig.3示例保存旧PC/PSTATE，根据EL0t、EL1t、EL1h选择`VBAR_EL1`相应IRQ/FIQ向量偏移，设置新的执行状态，把旧状态写入`ELR_EL1`/`SPSR_EL1`后恢复CVM。TEC保存虚拟寄存器/状态，Guest对list register的访问改为SMC。这说明中断交付可由可信软件构造，不需要以某个测试平台缺失硬件注入功能否定研究。

图中代码是入口状态构造示例，不是完整中断协议。它未展示pending/active优先级、屏蔽、嵌套、重复事件、并发ACK/ARM和目标退出等全部行为；不能据图断言实现没有处理，也不能据图证明全部已经正确。向正确异常向量跳转不认证事件归属，更不证明DMA停止或输出正确。

## 10. 设备和DMA边界

SEL2路线把MMIO翻译异常交给TMM封装，再转Host仿真；EL3路线将Guest MMIO替换为SMC，由TMM构造异常信息。原型支持Host virtio仿真，CVM增量包括SWIOTLB bounce buffer；PSCI/timer仅简述。论文没有给出可信GPU直通或多个CVM共享安全设备的完整方案。

§IV的DMA论证是阻止Non-secure设备访问Secure内存，不能自动推出某个获准发起Secure访问的设备只能触及指定CVM。项目必须继续按Client和设备上下文检查实际HPA、权限和生命周期，保护根表/关键MMIO，覆盖共享Proxy可见多个池的混淆代理风险。bounce buffer既不自动加密，也不验证恶意Host写回的长度、内容、顺序或完成状态。

## 11. 度量和证明

BL1/BL2逐级度量固件，RoT保存度量并以IAK签平台token；TMM生成/使用CAK签CVM token，平台度量绑定CAK公钥摘要。CIM覆盖初始代码/数据和TEC配置，激活后不变；可扩展度量槽支持Guest后续度量。远端提供challenge、验证证书/签名/参考值，再通过认证密钥交换注入秘密。

§III-D从IAK改称AIK，且声称即使ATF/TMM被攻破也不能制造假报告；需严格限定：无法提取硬件签名私钥不等于无法提交虚假度量或滥用签名服务。TMM本来就是TCB，运行时被攻破后的测量真实性、CAK使用和旧token有效性仍需单独机制，正文未提供足以移除该信任的证据。

本项目的证明应绑定批准的Proxy代码/固件、实际Realm实例、角色、授权策略及会话/epoch；启动镜像哈希、通道来源身份和任务完成状态不能互相代替。challenge证明报告新鲜性还须与实际会话密钥/接收者绑定，旧报告不应给重建实例或已撤销设备映射授权。

## 12. 公开生态材料能支持什么

[SDK固定版本](https://github.com/openeuler-mirror/virtCCA_sdk/tree/0c09e24aab736625a30d424c697a0fbbd65cdc12)提供远程证明、机密容器和镜像工具说明；README明确TCP示例仅供参考、建议rats-tls。样例README列出证书链、签名、challenge/RIM、事件日志重放与REM/固件参考值比较，并支持根盘密钥释放。这是有价值的部署流程材料，但本轮没有阅读验证器/密钥释放实现，不能把流程图当作实际密码协议已审计。

[Driver固定版本](https://github.com/openeuler-mirror/virtCCA_driver/tree/6f8c0a5f3382141999635aea42d80536db374a2e)README描述国密加速、封印和安全内存查询。已读`tmm_driver.c`选段通过Host内核符号查找调用`tmi_mem_info_show`、`tmi_tmm_info_show`等，并注册sysfs/迁移辅助属性；它是观测/辅助驱动，不是TMM核心。没有据此声称审计了页表准入、跨CVM隔离、IRQ注入、硬件访问权限或论文18测试用例。论文未显式链接这些仓库，生态关联不等于精确artifact对应。

## 13. 兼容性和TCB口径

Table I列19管理、10服务、8 PSCI接口兼容，以及4个新增内存接口不兼容；Table II把中断/设备虚拟化标为不可直接复用，安全内存管理只部分可复用。因此“API兼容”应限定到对应接口/规范版本，不能写成所有CCA功能或安全语义完全等价，也不能用2023年的`latest`链接推导2026年规范覆盖。

Table III总增量20.1K LoC包含两路线TMM、Guest、KVM、QEMU和TEST，不能当成单路线TCB大小；TMM增量分别4.0K/3.2K，还依赖已有ATF等。开头脚注称KVM约1.3K，表格为1.8K，差异保留。“适合形式化验证”不代表完成形式化证明；18个作者接口用例的功能测试也不等于恶意输入和并发全覆盖。

## 14. 实验配置和测量范围

SEL2使用早期Armv8.4服务器、64核2.4GHz/64GB；EL3使用Kunpeng920/256GB。Host Ubuntu22.04、Guest Ubuntu20.04、Linux5.10、QEMU6.2、TF-A2.7；每CVM 2vCPU/512MB，VHE启用。两路线在不同机器上，只能各自对照同机vanilla KVM，不能用绝对时间直接排名架构优劣。

微基准取100万次平均，虚拟IPI是vCPU0请求vCPU1执行callback并等待返回，包含往返/虚拟化成本，不是跨Client GPU中断端到端延迟；I/O是通过virtio-net取MAC地址，不能当作DMA吞吐。应用各5次均值，没有取得原始分布/置信区间。nbench报告平均开销SEL2约1.8%、EL3约0.8%，不包含I/O和syscall密集场景，更不是GPU性能。

| Table VI项目 | 同机vanilla → CVM | 复算变化 |
| --- | --- | --- |
| SEL2 IPI | 1.93 → 3.42 μs | +1.49 μs，+77.20%，1.772倍 |
| EL3 IPI | 2.65 → 7.26 μs | +4.61 μs，+173.96%，2.740倍 |
| SEL2 I/O | 18.72 → 21.34 μs | +2.62 μs，+14.00% |
| EL3 I/O | 22.08 → 39.285 μs | +17.205 μs，+77.92% |

正文统称IPI超过两倍，与SEL2表值1.772倍不一致；如实保留。NUMA FIO实验为libaio、iodepth32、10GB文件、随机4KB/顺序1MB、单线程60秒和15秒ramp，报告约66.7%提升；图轴标MiB/s，但这是所选文件I/O吞吐，不是隔离的DRAM带宽或GPU直通加速比例。

## 15. 应用性能中的冲突

以下按Fig.5图注绝对值复算；吞吐越高越好，Hackbench总耗时越低越好。图中的SEL2若干应用归一化柱及EL3部分柱也与图注/正文不一致，缺原始结果时不选择性替作者修正，也不据此否定其全部实现。

| 应用 | SEL2同机vanilla → CVM | EL3同机vanilla → CVM |
| --- | --- | --- |
| Apache req/s | 18703.14 → 15885.28，−15.07% | 10534.53 → 13236.54，+25.65% |
| Hackbench s | 0.5638 → 0.5848，耗时+3.72% | 0.7811 → 0.9147，耗时+17.10% |
| Memcached Ops/s | 493313.64 → 425533.23，−13.74% | 267982.9 → 450717.4，+68.19% |
| Redis SET req/s | 1157935.94 → 1150683.95，−0.63% | 683599.5 → 784141.9，+14.71% |
| MongoDB Ops/s | 1930.33 → 2257.75，+16.96% | 1195.03 → 903.72，−24.38% |

正文声称SEL2 Apache开销约29.7%、EL3 Memcached开销约33.8%、Hackbench提升64.3%、Redis提升16.3%，与图注不符；尤其Memcached和Hackbench连改善方向也不同。报告不把这些文字结论当作已验证数字。Redis负载-延迟曲线两平台轴单位分别μs/ms，评估是各自同机比较，不跨图用同一绝对量级。

## 16. 对项目中断隔离的直接建议

保留现有IRQ127和RMM认证队列，将其语义写成“本端可能有待检查状态”。权限不从中断号、Host注入成功或收到次数产生；请求身份来自RMM认证的原始Client和端点，事件记录绑定Client/session、任务cookie、对象/设备epoch和合法状态迁移。真实完成继续由匹配的native fence及可信设备状态认定。

pending必须持久到匹配的ACK，ARM之后重查队列/代次，避免并发到达的新事件被旧ACK清除。重复通知幂等处理，迟到/重放/跨Client事件拒绝或忽略，目标销毁和队列重建推进实例代次。普通通知丢失可通过权威状态重查恢复；持续拒绝调度属于DoS边界，但不能让它演变成错误完成或越权回收。

错误、取消、超时和reset应形成可信且精确的任务终态；超时不是GPU完成，fence错误也不自动证明所有设备事务已经静默。区分“可通知”“任务终态”“输出可发布”“DMA静默”“可解除映射/清零/复用”，与现有原生对象引用和回收机制衔接，不另造重复传输框架。

## 17. 对项目内存隔离与证明的建议

Stage-1合成路径的可论证性来自持续不变量：授权对象的真实HPA仍属于原始Client、访问权限不超过批准值、GPU实际root/页表受保护、表修改与失效原子衔接、所有旧引用/DMA终止后才回收。它可以作为内存部分的设计贡献，不必为了形式上出现Stage-2而增加重复翻译层。

撤销顺序应覆盖停止新提交/映射、处理在途任务及实际静默、撤映射/失效、必要同步、清零和复用；证明token/授权租约/任务epoch分别失效。共享Proxy拥有多个Client池的合法CPU映射，仍须按原始Client逐对象授权，不能以Proxy访问合法代替Client访问合法。以上是设计建议，不写作当前代码全部实现的断言。

## 18. 与现有论文的分工和后续引用链

PORTAL提供可信服务Realm管理思路，ACAI强调身份和映射归属一致，PhantomMap检查实际页与生命周期，CAGE/MOLE提醒设备内部配置和固件边界。virtCCA补充“可信上下文转发仍允许不可信语义输入”的具体例子；Heckler/WeSee/Sigy/TEEtime等中断研究需按各自平台和威胁模型交叉使用，不能把x86攻击直接写成Arm已复现漏洞。

新增候选优先为Twinvisor（SOSP2021，Arm硬件隔离CVM）、Hecate（CCS2022，Host接口治理）、VIA（ACSAC2021，受保护VM设备接口分析），以及作者不同的TDSC2026 TrustZone改造工作。它们是CPU/可信I/O支撑，未完成独立全文精读前不计数。GR-T、XpuTEE、FlexClave等直接候选全文缺项继续保留；本轮DICE入口403及猜测作者域名DNS失败均记录，不据此声称无原文。

## 19. 本轮记录

改动目的｜补充CCA兼容CVM、受控单级映射和可信中断转发的边界分析｜对照glmark未测 → 本版未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜12页全文、6页视觉、4blob校验/限定静态阅读、独立算术与Notion全文回读；证据在`build/cca-gpu-followup-20261027/`的`acquisition109*.json`、`virtcca-render109.json`、`virtcca-blobs109.json`、`virtcca-arithmetic109.json`和`batch109-final-audit.json`｜无作者程序、构建、VM、硬件或攻击run-id｜保留研究；核心TMM、正式出版身份、原始性能结果和后续候选待核实。
