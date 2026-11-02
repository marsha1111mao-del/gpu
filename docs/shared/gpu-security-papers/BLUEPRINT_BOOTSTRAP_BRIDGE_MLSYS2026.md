# Blueprint, Bootstrap, and Bridge：GPU 可信启动、通信元数据与完成通知的安全边界

研读日期：2026-10-28。完整阅读23页arXiv v2、§1–9、62条参考文献及附录A.1–A.6/B.1–B.2/C，覆盖7图2表；视觉阅读12页预印本及4页正式版，覆盖全部图表。取得MLSys正式版并逐页提取比较，去除空白、分页标记和arXiv水印后文本一致。结合论文TeX与匹配570.86.15厂商驱动的有限静态核查；未执行作者代码、驱动、GPU工作负载或攻击。未改运行代码，无新增性能测量。

## 1. 来源、正式版本与去重

Zhongshu Gu、Enriquillo Valdez、Salman Ahmed、Julian James Stephen、Michael V. Le、Hani Jamjoom、Shixuan Zhao、Zhiqiang Lin，IBM Research及Ohio State University。Blueprint, Bootstrap, and Bridge: A Security Look at NVIDIA GPU Confidential Computing，MLSys 2026，Proceedings of Machine Learning and Systems，第8卷，1546–1568页，正式页面发布日期2026-05-18。

[正式摘要](https://proceedings.mlsys.org/paper_files/paper/2026/hash/906419cd502575b617cc489a1a696a67-Abstract-Conference.html)、[正式PDF](https://proceedings.mlsys.org/paper_files/paper/2026/file/906419cd502575b617cc489a1a696a67-Paper-Conference.pdf)、[arXiv v2](https://arxiv.org/abs/2507.02770v2)、[HTML](https://arxiv.org/html/2507.02770v2)。v2日期2026-04-17；2025-07-03的v1题名为NVIDIA GPU Confidential Computing Demystified，是同一论文的早期版本，不另计一篇新架构。

正式PDF SHA256为`dce150122867959d9a5b3228f695cc8e0e8fc1563f4e83f9d2ce7951744ec902`；v2 PDF为`d89c613094067bbce45e02561a340cc1e5bc762614a5403c6d1bc7226fc9d158`；HTML为`f666c42650e2f3be9230c0649222154b6a981b0ecbcb85df17a5c0c2fe3c04df`；论文源包为`d386ca23e67f78b8d47746456e2a9752f5b4c3b08d80ecbf0397687bb00d7488`。源包是TeX/图片等出版材料，不是运行实现。

请求、全文、源包清单、文本差异、16页渲染、驱动固定树/选取blob及算术证据保存在`build/cca-gpu-followup-20261027/`的blueprint相关文件。论文和正式页面未给已确认的仪器化实现及4394次传输原始轨迹，限定GitHub检索也未命中匹配artifact；不由此断言不存在公开实现。作者称已向NVIDIA PSIRT披露，但本文未取得具体CVE、厂商确认或修复公告，不把潜在暴露写成已确认产品漏洞。

## 2. 与项目最直接的联系

论文拆解CPU CVM与GPU TEE之间的可信启动、证明和六类通信路径，重点在数据面之外的控制元数据。它不是Arm CCA论文，也没有实现恶意多Client共享GPU隔离，但能检查Portal/CAGE式可信GPU服务的一个共同问题：数据受到保护时，提交、故障、调度及清零完成证据是否仍可被不可信层影响。

对本项目应延续已接受的假设：RMM认证原始Client；ProxyRealm统一管理SMMU；GPU使用软件IPA→HPA授权翻译后合成受保护的直接HPA Stage-1；其他设备保留硬件Stage-2；平台保护页表、根配置和关键MMIO，固件可信加载。本文不以H100硬件与模拟平台差异否定该方案，而检查原始身份、实际页归属、映射生命周期和权威完成证据能否贯穿全链。

核心判断是：签名命令不自动认证执行结果；真实中断不自动认证任务归属；“清零完成”更不自动证明旧DMA停止或资源可以交给另一个Client。项目的内存隔离与中断通信隔离应在资源交接处共同论证。

## 3. 威胁模型与可信基

作者允许攻击者控制Host boot/SMM/OS/HV、外设及互连，能够操作VBIOS flash、设备detach/reset/reassign。CPU/GPU package及封装内HBM可信；封装内部物理攻击与可用性不在目标内。CVM内kernel、driver和应用可信，驱动内部取到密钥不是Host绕过TEE。

因此论文不是“不信任整个驱动仍隔离任意租户”的证明。若多个互不信任Client共享一个Proxy，Client身份与授权必须由Proxy分别保留，不能把一个CVM内engine/channel的密码域误当不同Client的隔离域。元数据泄漏也须说明秘密策略：RPC大小和调度活动可见，不等于模型参数或明文内容已恢复。

## 4. 方法与实验边界

平台为双EPYC9634、每颗84核、8张H100 SXM5 80GB，实际一次仅将一张GPU直通SNP CVM，guest RAM 64GB。Host Ubuntu22.04.5/kernel5.19；guest分别为RHEL9.4/kernel6.1.91/driver550.54.15/CUDA12.4及Ubuntu22.04/kernel6.8/driver570.86.15/CUDA12.8，板卡VBIOS96.00.61.00.01。八卡机不等于八卡机密计算实验，也不是多租户并发研究。

方法包括公开文档/专利交叉推理、开源驱动仪器化、CUDA及OpenSSL拦截。闭源固件和用户态CUDA仍不透明，专利描述不能自动当作每张产品卡的实测实现。尤其CUDA内部五类资产的数据流，有明确推测成分；不把所有黄色推测框改述成已验证保护。

本研究是架构与通信安全剖析，没有给本项目glmark、LLM或恶意共享负载结果。论文的驱动内部计时也不自动等于Host攻击者可稳定观察的时间信号，需另做观测模型和攻击验证。

## 5. 可信启动：FSP、GSP、SEC2与CE

作者将FSP视为安全启动根，认证GSP首阶段与RM；GSP承担控制面、SPDM、RPC和DMA管理；SEC2负责签名method、解密、工作启动及scrub；CE执行大块AES数据通路。作者同时指出公开资料对FSP/SEC2职责有不一致，不能在闭源处补造确定实现。

可信固件加载至少要把已认证镜像实际字节、版本策略、装载目标、配置和执行入口联系起来。验签正确不意味着运行无缺陷，重置或更新也不能沿用失效的设备租约。本项目可接受固件可信前提，同时把固件/配置generation与device epoch纳入会话和任务绑定；这与MOLE/FAARM所关注的MCU信任链互补，不意味着本轮复现了其攻击。

作者统计GSP6、SEC2 6、CE32共44个派生key。它们按引擎、方向、用户/内核等用途分离，不是44个相互隔离Client。一个logical CE的channels可共用key；跨channel必须有唯一IV域及安全的轮换/重启规则，不能只凭每channel有递增计数就证明同key下全局IV不重复。

## 6. MMIO firewall实验不能等同保护覆盖率

作者按4字节扫描16MiB BAR0，共4194304次读取。CC模式下约99.78%返回0、1042项非零约0.0248432%（论文四舍五入0.02%）、0.19%错误；non-CC约7.94%非零、80.25%错误。可以观察接口暴露形态变化，不能将“99.78%读零”改述为99.78%寄存器已通过安全验证。

零值可能来自合法零、屏蔽或未映射；非零也不等于可利用。该扫描没有覆盖所有写语义、别名、复位、配置及状态转换，不能独立证明页表根或中断控制不可改。项目应在既定平台保护假设下列明真正影响SMMU/GPUVM/root/IRQ路由的控制面，论证整个租约周期保持保护，而不是要求模拟板复现Hopper firewall。

## 7. 远程证明：设备真实不等于会话归属完整

论文描述五级设备证书链、四级RIM链、64项measurement记录、信任根、OCSP、RIM签名及golden值验证，成功后进入READY。64项measurement不必然对应64个独立组件；通过测量也不是无漏洞证明。

需要区分GPU quote验证与CPU CVM、可信Proxy、原始Client、实际传输端点、当前配置和epoch的组合绑定。单独一份真实GPU证据不能阻止把Client接到另一个会话、旧设备租约或不同Proxy。应由可信端基于新鲜挑战及策略决定READY，不接受Host单独提供的“已就绪”标志。

作者建议替换driver内root以应对root被改，但其主威胁模型又信任CVM driver。保护trust anchor只能解决根来源；若整个verifier已被攻陷，仅更换root不能恢复判定可信性。项目可将设备证明和Proxy服务身份一起纳入可信会话上下文，既不夸大论文已实现组合证明，也不把证明取代映射和任务授权。

## 8. 六类路径的发现强度

下表对应论文Table2：●为作者确认存在暴露，◐为潜在低风险，○为未观察到问题，?为未知；它们不是六次端到端攻击成功，也不是形式化无漏洞结论。

| 通路 | 机密性 | 完整性 | 应如何理解 |
| --- | --- | --- | --- |
| RPC | ● | ◐ | 共享队列元数据可见；操纵游标的有效后果仍受序号/认证限制 |
| CPU–GSP DMA | ◐ | ○ | 长度及计时观察，未证明秘密恢复或完整性突破 |
| Fault | ◐ | ○ | PUT等故障活动可见，实际记录经受保护通路传递 |
| UVM | ● | ◐ | SEC2队列/信号存在共享明文，method本身签名 |
| Scrub | ● | ◐ | 清零命令与完成值需分开分析，潜在提前回收链待实证 |
| CUDA内部 | ? | ? | 闭源数据流部分只能推断，不能当已验证安全 |

## 9. RPC：明文头、AAD、游标与重放

通信物理表共129项：self、命令header、63个命令entry、状态header、63个状态entry。Fig5的KVM dump显示共享header/tag/AAD/seq/elemCount/checksum等元数据可见而payload加密。self指针可辅助扫描候选，但唯一定位还需范围、格式和一致性验证；guest/system PA不自动就是Host HPA，攻击者若掌握stage映射才可转换。

公开长度和元素数可能泄露命令活动；论文没有展示恢复模型权重。明文元数据可能同时作为AAD认证，不能由“没有加密”推出“没有完整性”。XOR checksum不是MAC，但MAC还可能在另一层验证。

论文讨论篡改read/write指针以改变顺序、重复或丢弃消息。静态核对匹配驱动后，应收窄解释：队列库保存私有几何与接收游标、检查共享游标范围；GSP接收还检查私有预期序号、AAD和tag，认证失败进入fatal state。因此游标可干扰不自动意味着旧RPC被可信端接受，可能只导致拒绝服务。仍需核查不受认证长度的解析顺序、buffer容量及闭源GSP对端，不能把这次定向阅读升级为完整队列安全审计。

## 10. DMA：定量观察与侧信道证明的距离

作者记录4394次传输，453读、3941写，包含8–256B小传输和4096B大传输。Fig6时间轴标为Execution Time(ns)，带1e6量级，图中约2–5ms；不能误写成几秒或几微秒。小传输自身有约2.2/3.3ms的双峰，大传输也有多峰，不能概括为所有大包都慢于小包或仅长度决定耗时。

论文将长度/时间差列为潜在线索，但没有提供秘密恢复准确率、误报率、攻击者实际观测稳定性或跨模型分类实验。驱动内部测量不是自动成立的Host时间侧信道；噪声可平均也不等于攻击已证实。是否padding或恒定时间需依据元数据保密策略与成本决定，不能给项目无条件加入全通路填充。

## 11. Fault：认证故障记录与可信中断不同

hardware fault buffer位于保护区域，GSP将记录加密到两个共享shadow buffer，包含authTag及作为AAD的valid，MMU_FAULT_QUEUED RPC触发ISR处理。BAR0的PUT暴露故障活动，作者以故障不频繁判断低风险，但频率取决于负载及攻击者是否能诱导故障，不是普遍机密性结论。

实际故障packet认证不等于中断向正确Client投递，更不表示job成功。项目应按GPUVM、原始Client、cookie、epoch、访问地址/类型处理可信故障，故障应进入明确失败/重试策略；Host提供的故障地址不得直接成为新HPA授权依据。可以借鉴WeSee/HECKLER对恶意事件语义的警惕，但不能把AMD异常向量攻击条件直接当Arm GPU漏洞。

## 12. UVM：签名启动、LCIC确认和CE完成

作者分析16对WLC/LCIC：WLC有静态decrypt_push和可变run_push，LCIC推进WLC GPPUT两项，run推进LCIC一项。WLC/LCIC及CE命令处于保护域，可变push密文传递、tracking semaphore受保护；SEC2自己的GPFIFO、GPPUT和semaphore处于不受保护共享内存，method签名限制其内容。

这允许识别调度活动与潜在干扰面，不能直接推导攻击者可生成任意SEC2命令或在GPU执行任意代码。还需证明签名覆盖的地址/长度/context、新鲜性与重放约束。LCIC“已推进队列”只是调度确认，不是CE数据处理结束，也不是全部DMA静默。

对项目最有价值的是区分提交接受、调度确认、真实native fence终态和可回收条件。既有private plan/snapshot和native fence应保持权威，避免另设Host可写的“已处理计数”作为成功依据。

## 13. Scrub：清零命令可信，回收证据仍需检查

SEC2按块执行签名memset，chunk信号允许auth-tag slot复用，最后完成信号及cache flush覆盖整个block。auth-tag slot可复用与整页清零完成是不同事件；整页清零完成与旧设备访问已全撤销也不同。

论文指出SEC2返回semaphore没有加密保护，提出潜在完整性后果。准确说法还应区分机密性与完整性：引擎不能加密不意味着原则上不能生成MAC；签名semaphore-release命令也只认证写入动作的命令，不能认证Host后来读到的共享值。需要直接检查实际存储位置、认证与调用者，而非仅以明文下结论。

匹配代码的scrub slot及进度消费表明这是一条值得审查的链：共享完成值影响auth-tag buffer复用，32位硬件值用于重建64位完成号。但本次没有完整追踪最终物理页分配、超时/重置与闭源固件行为，更没有端到端残留数据攻击；不能写成“已证明H100能跨租户读旧数据”。

项目建议将撤销后的资源隔离为不可分配状态，直到可信终态、撤销/失效完成、在途DMA停止及所需清理全部满足。若中止或reset不能证明停机，应隔离失败资源而不是仅因超时就复用。该状态应绑定既有cookie/epoch和资源generation，避免额外一套不一致完成协议。

## 14. 厂商固定代码的独立复核

选择论文实际使用的[NVIDIA open-gpu-kernel-modules 570.86.15](https://github.com/NVIDIA/open-gpu-kernel-modules/tree/570.86.15)，annotated tag为`d31ffcb04e529dc0d516e1511fe1e6c373556666`，对应实际commit `54d69484da940413ba6017df9cf43bed8b75da46`。不是作者instrumentation artifact，也不是上游latest。完整树4192项、未截断；选取11个blob的长度、Git blob SHA1及SHA256均核对，raw六项超时保留，经GitHub blob API恢复成功。

`src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c`的GspMsgQueueSendCommand及ReceiveStatus定向阅读，后者约595–780行：共享entry先复制工作区，检查checksum和私有rxSeqNum，旧序号仅尝试消费以恢复而非作为当前响应接受，随后ccslDecryptWithRotationChecks验证AAD/tag，失败置错误状态，成功再推进序号。`message_queue_priv.h`完整读，`src/common/shared/msgq/msgq.c`约315–510及600–690行核对私有几何、游标与范围检查。没有把所有未认证长度/分配边界证明完，也未核查GSP闭源接收端。

`kernel-open/nvidia-uvm/uvm_hopper_sec2.c`完整读：semaphore_release生成签名命令，decrypt签名包含源/目标/长度等；不认证输出共享值。`uvm_channel.c`约705–780及1029–1058行显示SEC2 push使用unprotected sysmem，tracking semaphore的额外加密shadow仅对CE通道启用，且保留系统membar。不能把CE保护推到所有SEC2信号。

`src/nvidia/src/kernel/gpu/mem_mgr/sec2_utils.c`约80–210、390–665行定向阅读：auth-tag buffers配置为unprotected系统内存；_sec2utilsGetNextAuthTagSlot读取完成槽游标并等待；sec2utilsMemset检查memdesc设备/空间、offset和length，按连续区/页边界分块；sec2utilsUpdateProgress读取32位semaphore并推断wrap重建64位完成号。是否能伪造某个具体业务的安全回收仍需最终调用者和硬件通路证据。

`uvm_conf_computing.c`约397–592、617–735行显示channel CSL锁、明确IV记录/key version、fault valid的AAD认证，以及轮换前等待在途push；该版本明确因UVM无法idle RM所属SEC2 channel而关闭UVM SEC2 pool的key rotation。不能泛称所有key永不轮换；这条注释反映共享控制权给安全轮换带来的同步约束。`conf_compute_keystore_gh100.c`约275–380、390–467行还显示key slot和channel计数、IV mask及域用途处理，故不能认定实现仅有互不协调的裸channel计数；本轮没有完成密码库/重启域唯一性证明。

`uvm_hopper_fault_buffer.c`完整读，但它主要解析engine/client/subcontext，不实现整个fault认证链，认证入口另见uvm_conf_computing_fault_decrypt。README只读版本/装载约束前105行，未把支持型号清单算完整研读；msgq.h仅取得未完整读。11个blob取得和校验不等于11个文件完整审计，更不等于整个驱动通过安全验证。

## 15. CUDA内部与未来Trusted I/O

作者通过CVM内GetKMB/OpenSSL拦截分析userdata、kernel code、args、QMD和queues五类资产。CVM本来可信，不能写成Host从TEE外直接抽取密钥。其用户态和固件仍闭源，五条完整数据路径的保护部分属于推断；开源kernel模块不意味着CUDA和固件全部可审计。

附录讨论Protected PCIe、NVLink/NVSwitch及TDX Connect/SEV-TIO、SPDM、TDISP、IDE。Protected PCIe支持条件举VBIOS96.00.BC.00.01/driver570/CUDA12.8，与实际板卡96.00.61.00.01不同；这些内容不能充当本次已测Trusted I/O或多GPU结果。文中某些模式的NVLink物理信任也必须按具体版本/部署解读，不能由论文时间点推断2026-10所有产品仍相同。

可信总线和设备证明减少通路攻击面，却不替代对象归属、权限、映射生命周期或完成语义。即使底层未来提供完全可信I/O，Proxy仍要防合法设备以错误Client/旧epoch身份访问或报告完成。

## 16. 对项目两部分的具体改进建议

直通/共享与性能部分：按控制RPC、DMA、fault、调度、清零和任务完成分类计量，分离提交接受、GPU执行和通知延迟；持久buffer及批量化可减少开销，但保持相同安全条件。不要因论文使用PCIe密文就给可信共享内存重复加密，也不要把元数据隐藏默认列为性能主线。本轮没有项目性能变化。

内存与中断隔离部分：形成贯穿原始Client、GPUVM、对象版本/权限、实际HPA授权、device epoch、cookie/native fence的同一权威上下文。IRQ127/SGI等用于唤醒，Host的目标或计数不能决定归属或成功；Client读取可信终态恢复被合并/丢失通知，迟到旧epoch事件不改变新任务。通知重放可导致额外唤醒，但不应导致再次消费结果或提前放页。

优先验证设备reset后迟到完成、换Client后共享IRQ、跨Client同cookie、重复/缺失/合并通知、故障与成功竞态、slot wrap、清零chunk假完成、最终清零未完成、认证失败及撤销后旧DMA。可信任务完成、输出可见、应用数学正确性和安全复用分别列条件，不能只凭一次job IRQ或fence就一并宣称。

可把创新点收敛为“身份与生命周期绑定的GPU任务隔离协议”：前端映射授权加后端权威终态和安全交接，而不是另造一套平行计数器或仅给中断消息附MAC。论文的六路径拆解提供审计方法，Portal/CAGE/ACAI/PhantomMap提供服务与映射约束，两者在任务生命周期处结合；这是本项目研究建议，尚非实现或验证结果。

## 17. 本轮评价与证据边界

本篇的价值在于把商业GPU CC中不透明的启动和控制通信拆开，并发现数据加密之外值得核查的元数据/完成信号。局限是固件闭源、多个CUDA流程推测、没有恶意多Client共享实验，也没有把潜在低风险观察全部证明为端到端完整性攻击。定向厂商源码说明必须继续检查私有状态与实际认证，避免仅由共享明文推断攻击成立。

统一记录：完整23页/源包/正式版差异/16页视觉/固定厂商源码定向阅读/Notion全文回读｜glmark未测→未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id；原始请求超时及API恢复均保留于build证据｜保留设计建议，未覆盖最终回收调用者、闭源固件和完整密码状态，不宣称部署或攻击复现。
