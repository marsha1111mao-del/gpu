# ITX：设备内可信控制、认证数据流与安全退出生命周期

研读日期：2026-10-27。完整阅读微软研究院链接的18页作者全文，包括安全分析、制造/固件更新、证明、checkpoint及训练场景附录，核对USENIX正式书目。只作资料和静态分析，未运行IPU、GPU、编译器、训练、攻击或硬件实验。未改运行代码，无新增性能测量。

## 1. 准确书目与全文来源

- 题名：Confidential Computing within an AI Accelerator；系统：IPU Trusted Extensions（ITX）。
- 作者：Kapil Vaswani、Stavros Volos、Cédric Fournet、Antonio Nino Diaz、Ken Gordon、Balaji Vembu、Sam Webster、David Chisnall、Saurabh Kulkarni、Graham Cunningham、Richard Osborne、Daniel Wilkinson。
- USENIX ATC 2023，501–518页；官方BibTeX提供ISBN 978-1-939133-35-9，本文不补造DOI。
- [会议页](https://www.usenix.org/conference/atc23/presentation/vaswani)；[微软研究院条目](https://www.microsoft.com/en-us/research/publication/confidential-computing-within-an-ai-accelerator/)；[作者全文](https://www.microsoft.com/en-us/research/wp-content/uploads/2023/05/Confidential-Computing-within-AI-Accelerators.pdf)。

本轮USENIX PDF下载超时，但会议页经apex域取得；微软条目明确链接上述全文，实际PDF为3438870字节、18页，SHA256 4a813d85d7445998eaebe46daa1e0d8bb8a108a3cdb7247fba3fd5a018097a2b。作者稿页码1–18，不将其哈希冒充未取得的USENIX排版PDF。文件itx-msr-batch22.pdf及逐页文字、会议页、作者页和获取记录在build/cca-gpu-followup-20261027。

## 2. 背景、目标与创新

CPU TEE不能自然保护外部AI加速器上的代码、输入、权重与结果。ITX希望在完全不信任Host CPU软件的情况下，把模型与数据联合训练放入设备内TEE，并让多个参与方在验证作业及环境后才交出密钥。

它扩展Graphcore GC200 IPU，而不是Arm GPU或CCA。主要创新是设备可信执行模式、板级硬件根CCU、可编程片上AES-GCM数据路径、带明确IV语义的应用级数据流，以及制造、证明、密钥和退出的一套生命周期协议。其不依赖CPU TEE的离线模式与H100常见的CPU CVM+GPU组合形成对照。

对本项目的意义是设备侧控制方案如何绑定作业、数据流、参与方和回收状态；不是要求将IPU的静态程序模型搬到Mali，也不以硬件差异否定可信ProxyRealm的软件授权合成Stage-1设计。

## 3. IPU架构和适用前提

GC200有1472个tile、约900MB片上SRAM，每tile最多6个静态调度线程。计算、内存分配和数据交换由可信编译器事先规划；BSP模型在同步屏障、交换和计算阶段之间循环，执行期间无需Host逐条安排每个算子。

Host通过PCI BAR访问配置、片上页表和tile内存；Host Sync Proxy（HSP）处理Host/IPU同步。ICU是板上的设备初始化/环境管理MCU，经JTAG连接IPU。ITX新增CCU管理可信状态，并在PCIe与内部交换路径之间加入Secure Exchange Pipes（SXP）。

这种“整个设备交给一个作业”的静态模型有利于限定攻击面。它既不是多个互不信任作业同时共享IPU的原型，也不能把一个作业内的多个数据提供者称为独立租户上下文隔离。多参与方认证与多Client GPU共享是不同问题。

## 4. 威胁模型、可信基与排除项

攻击者控制Host OS、Hypervisor、Host内存和PCIe流量，可替换、重放、重排代码/数据，也可尝试经MMIO、BAR或页表重定向访问。论文还考虑tapeout之后制造与组装环节的不可信性，但信任芯片设计者、设备制造方的认证基础设施、IPU和HRoT封装内部状态。

当前原型额外信任ICU固件、CCU↔ICU↔IPU物理链路，以及IPU↔IPU链路；这些链路未加密，物理攻击可提取密钥或修改测量。将CCU集成到IPU、保护IPU间链路是后续硬件方向，不是该原型已经提供的能力。

ML脚本、配置、框架和编译器承担计算完整性信任。多方可审核脚本并核对本地编译出的同一manifest/二进制。诚实数据方必须用新鲜密钥正确加密输入，验证证明后才放密钥；TEE并不判断恶意参与方提供的数据是否真实或具有正确标签。

一般功耗、执行时间和封装探测侧信道不在完整防护范围；静态调度、片上固定延迟和设备独占减少部分观测，并非证明任意模型都数据无关。Host仍能中断或拒绝服务，ITX不提供作业最终完成或有界延迟保证。

## 5. 可信模式与控制权

进入trusted mode后，Host不能修改关键配置寄存器或访问tile明文；只有CCU/ICU可访问相关安全状态。可信模式寄存器及安全配置被测量进入证明，退出必须经过reset与清理。机密模式下的异常由专用引脚交给CCU，防止Host自行把认证失败解释成成功继续执行。

CCU、ICU和IPU reset在硬件上耦合，不能让攻击者仅复位安全控制器却保留另一部分的旧敏感状态。要区分原生reset和ITX协议：原生SBR/Newmanry reset不清tile内存；ITX在安全退出或恢复Host链路之前额外清除密钥和tile内存。

这与项目关键MMIO/页表根保护的研究目的相同，但不等于项目需要相同芯片。应说明谁有权启动、终止、改变根或复位，以及任何异常路径是否绕过既有Client/对象授权。

## 6. CCU身份、启动与固件更新

CCU采用STM32H753，主启动器置于一次性可编程区域。首次启动在设备内部生成UDS并限制其暴露；以后从UDS派生稳定设备标识HDI和绑定次级启动器测量的CDI，再派生Card Identity Key（CIK）、Platform Identity Key（PIK）及绑定CCE固件的Attestation Key（AK）。它使用DICE式分层身份，没有要求一定使用TPM/PCR。

CIK保持板卡身份，PIK随次级启动器变化，AK再随可信计算引擎变化。制造方证书、设备自签发证书和固件更新证书一起供远端检查。固件可更新不等于旧版本始终可接受；验证方还须检查更新测量、授权链和撤销信息。

附录A.4承认：若次级启动器持有CIK私钥，恶意但获授权的固件可能用它伪造另一版本PIK的背书。加固方案把CIK/PIK生成及PIK endorsement移到主启动器，并擦除CIK私钥；作者明确该加固协议未在原型CCU实现，不能把讨论中的完整防护计为已测功能。

制造SFI加密固件只直接保护固件包机密性，不自动防替换CCU器件。作者另提出批次秘密、启动器manifest签名和挑战nonce协议，以认证实际器件及初始固件。附录把它作为若进入生产可采用的流程，不将全套生产认证部署当作已完成事实。

## 7. 作业证明、密钥与参与方绑定

可信clean room先编译模型，生成二进制和manifest，加密代码/初始权重；各数据方独立加密输入、生成签名keyshare并上传包。Host只负责搬运、创建TEE、转发证明与密钥消息，在本篇离线模式中不被信任。

CCU证明包括配置、bootloader测量、manifest测量及本次运行属性：CCU新鲜keyshare、各方证书指纹、输入stream归属、结果接收者和恢复epoch/checkpoint。密钥包装KDF的salt还绑定双方公钥与manifest M。远端要验证完整链、撤销、固件更新和作业属性，不能只检查签名可验。

CCU分别与参与方做ECDH并解包输入密钥，结合各方nonce生成checkpoint和最终模型密钥。只要至少一方诚实提供新鲜nonce，当前运行派生密钥就具有相应新鲜性；结果密钥只向列入证明策略的接收者释放。这建立的是策略限定的多方作业，不是允许每一方任意提交同设备独立任务。

## 8. 认证帧与“内容正确”和“位置正确”的分工

代码和数据被切成最大1KB、总长度为128B倍数的帧，每帧含128位IV、密文和128位tag。硬件AES256-GCM使用空AAD；编译器将stream类型、stream ID、tile/IPU ID和frame index等结构编码进IV。同key下IV不可重复是明确安全前提。

SXP负责AEAD真实性，软件必须另核对“收到的IV等于当前位置期望的IV”。否则合法但属于其他位置的帧仍可能被重放或重排。bootloader按预期代码stream/tile/index检查，checkpoint读取亦如此。不能仅凭GCM tag通过就宣称任务序列、对象归属和新鲜度全部成立。

每SXP有16个physical key context，硬件约束同一context同时处理一帧；编译器负责tile/exchange block映射、同步和key schedule。4个SXP、每个16GB/s单向，在作者路径中支持32GB/s双向PCIe Gen4。key context是密码数据流资源，不等于16个已实现隔离租户。

请求上的KEY_INDEX/AES由可信片上状态保存，读completion返回时由PCI complex重新填入，不让Host任意选择解密上下文。该“在可信侧记录请求归属，接收响应时按记录解释”的方法与项目完成记录绑定有关；本项目仍需要使用已有native fence和cookie/epoch，而非相信Host随附的Client编号。

## 9. 生命周期、异常和安全退出

TEE初始化先quiesce，确认Host/IPU之间没有在途读写，然后进入可信模式、清tile内存、测配置并建立证明。启动时CCU部署受测量bootloader及密钥；代码装载经历帧认证、期望IV检查，并在完整设计中累积二进制hash与manifest比较。

正常终止或认证失败终止都需要quiesce、清tile内存、禁用所有SXP keys，最后通过Newmanry reset退出可信模式。硬reset清CCU状态后，ICU必须先擦掉旧tile秘密，再开放Host links。通知异常、发出reset请求和完成安全回收不是同一事件。

HSP通知与安全异常引脚不是多Realm虚拟IRQ协议。本篇没有描述Client目标路由、共享IRQ合并、ACK/重入或每job通知去重。Host虽可要求终止，但不能以“Host说结束”作为成功证据；可信最终结果仍由受保护执行及结果流给出。

## 10. Checkpoint：正确实例与最新版本的区别

checkpoint通过认证stream保存权重和各数据stream offset，IV编码epoch、checkpoint ID、IPU/tile和frame index。每次恢复切换epoch密钥，多方须同意恢复的epoch/checkpoint及先前/当前nonce，因此可以绑定所选恢复实例。

作者明确“不保证一定从最新checkpoint恢复”；这需要可信持久状态，超出论文范围。epoch并非天然防止所有rollback：攻击者若能诱使参与方同意旧版本，计数器格式本身不会提供全球最新性。此外安全恢复尚未在原型实现，不能将附录A.7写成通过硬件实验的恢复协议。

对项目已有cookie/epoch同样应明确范围：防止旧完成被新任务接纳，不自动提供跨Proxy/Client重建的持久最新性。Client重连、reset和测试快照回滚中的实例边界需要分别定义。

## 11. 原型与完整设计的差距

作者在2020年tapeout、TSMC7nm GC200开发板实现实验扩展，逻辑面积少于芯片1%，有固件和TensorFlow/编译器/runtime原型；不是量产ITX服务的部署证据。

论文§8明确四项原型缺口：仅单IPU；编译器只用一个logical key region；安全resumption未实现；tile bootloader解密后没有测量完整IPU binary。附录安全表也把防二进制可塑性路径标为Not implemented；这直接限制原型关于manifest与实际执行二进制一致性的证据强度。

单key region仍为每帧分配唯一IV，但不能据此声称验证了完整多方独立key区域管理。板上明文控制链路、IPU间链路和未实现的启动加固分别保留，不能因部分硬件已tapeout就视作所有设计主张都已实现。

## 12. 实验平台、负载与量化结果

| 对照 | 作者配置 |
| --- | --- |
| CPU | AMD EPYC7763上的48核VM、SEV-SNP；单线程核，作者称超线程不改善向量负载 |
| IPU | 单GC200@900MHz、Intel Xeon8168 Host，开发板降低频率 |
| 工作负载 | TensorFlow，CIFAR-10、ResNet20/56/110；训练50000、测试10000张 |
| CPU batch | 1534/768/384，分别训练32/32/64 epoch |
| IPU batch | 64/32/16，分别32/32/64 epoch，按各平台吞吐优化 |
| 正确性 | 作者核对clear/confidential模式训练所得模型预测准确率相同；不等于逐bit参数比较的报告 |

CPU与IPU batch不同，13–17倍机密模式吞吐优势混合了硬件、实现和调参效果，不能视为安全机制单独使IPU提速。clear模式作者称12–20倍。不同batch还可能影响优化路径与收敛，不能直接推定两平台训练过程逐bit一致。

SEV-SNP开销8%–14%；ITX端到端开销3%–58%。摘要的低于5%对应较大训练任务，不能推广到全部三模型。ResNet110为1123对1089秒、64epoch，约3%；小模型58%由设置成本摊薄不足导致。

作者把ITX总开销分为初始化/证明40%、启动与SXP设置43%、退出/scrub13%、运行时加密4%。这里4%是“开销内部的占比”，不是相对非机密运行时间额外4个百分点。预计两IPU满频还能改善约3.5倍为预测，非本文已测结果；本轮也没有重新测量。

## 13. 公开实现、复现材料与证据边界

正式会议页和微软作者页提供论文/演讲材料，没有发现链接的完整CCU固件、ITX RTL、编译器补丁或原始训练数据。精确ITX机密计算仓库检索返回0，属于有界搜索，不证明不存在任何公开实现。没有把通用Poplar/Graphcore软件或基础STM32库当作本文安全扩展artifact。

本报告的实现分析来自正文、原型缺口、安全表、manifest结构、key表和附录bootloader伪码；没有固定可审计的作者安全实现提交，因此不宣称完成RTL/驱动源审计或重现作者结果。形式化证明、完整攻击注入集合和统计置信区间也未由本轮材料核实。

## 14. 与现有文献和项目的关系

ITX与Graviton/H100都把信任延伸进设备，但其静态离线模式不需要Host CPU TEE；与HETEE/ccAI的外部安全控制器不同，主要执行/密码路径位于设备芯片，并借板级CCU建立根。与GuardAIn相似，它强调受保护的完整作业及多方身份，而不是只加密任意命令。

PORTAL/CAGE/ACAI适合本项目可信服务、页归属和设备访问边界；ITX补充请求/响应归属、实际执行与manifest绑定、异常由可信控制器处理，以及quiesce→scrub/key revoke→重新开放的顺序。它的整设备独占和静态编译前提不构成本项目共享GPU隔离的既有完整解法。

项目已有RMM认证身份/队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127。可增量明确：一个可信执行契约绑定Client、任务实例、对象代次、设备/Proxy代次及允许输出；完成路径核对可信请求状态；reset后晚到回调不能转入新实例；实际停止访问和数据清理分别作为回收条件。

保持既定假设：ProxyRealm统一控制SMMU，RMM认证原始Client，建图阶段完成实际页授权和IPA→HPA软件翻译并生成受保护的合法HPA Stage-1映射，其他设备继续使用硬件Stage-2。ITX的软件IV检查启发的是对象/任务语义绑定，不是要求在项目IRQ路径上额外套一个与威胁模型无关的加密层。

统一记录：18页作者全文、正式书目、原型安全差距和公开材料范围研读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无IPU/GPU、训练、攻击或硬件run-id和新增PASS；证据位于build/cca-gpu-followup-20261027｜保留为设备侧可信控制与生命周期的直接相邻研究，设计、原型和作者测量分别记录。
