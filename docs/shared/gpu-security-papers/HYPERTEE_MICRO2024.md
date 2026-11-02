# HyperTEE：可信管理职责拆分、身份绑定通信与共享设备授权

研读日期：2026-10-27。完整阅读作者公开的16页正式排版论文，包括全部110条参考文献，核对MICRO官方议程、正式DOI、作者出版列表及有界公开实现搜索。仅资料与静态分析，未运行FPGA、GPU、Gemmini、模拟器或攻击。未改运行代码，无新增性能测量。

## 1. 准确书目、版本与来源

- 题名：HyperTEE: A Decoupled TEE Architecture with Secure Enclave Management。
- 作者：Yunkai Bai、Peinan Li、Yubiao Huang、Michael C. Huang、Shijun Zhao、Lutan Zhao、Fengwei Zhang、Dan Meng、Rui Hou。作者网页将Peinan误排为Peinna，本文采用正式论文与DOI元数据拼写。
- MICRO 2024，第57届IEEE/ACM International Symposium on Microarchitecture，105–120页；DOI：10.1109/MICRO61859.2024.00018。
- [正式DOI](https://doi.org/10.1109/MICRO61859.2024.00018)；[官方议程](https://microarch.org/micro57/program/)；[作者出版列表](https://fengweiz.github.io/publications.html)；[研究组列表](https://compass.sustech.edu.cn/publications_en.html)；[作者公开全文](https://fengweiz.github.io/paper/hypertee-micro25.pdf)。

作者链接文件名虽含micro25，PDF首页、DOI、页码及正式书目均为2024，不能据文件名改成MICRO2025。实际全文618416字节、16页，SHA256 043d99d642e0d977c8d463ea5d7ab52d4c79962681f98fe436fa0e0a802e5a47。PDF、逐页文字、Crossref、议程、作者页和获取记录在build/cca-gpu-followup-20261027，文件hypertee-author-batch23.pdf及hypertee-batch23.txt。部分图表字体提取为uni编码，本报告仅采用可核对正文与文本表格数值，不声称完整重建所有图中数据点。

## 2. 背景、问题和贡献

TEE通常隔离应用代码，却仍由与攻击者共享硬件资源的管理软件处理分配、换页、证明和共享。这些管理操作暴露访问模式，证明密钥泄漏还可能影响整个平台信任。

HyperTEE将计算与管理拆成Computing Subsystem（CS）和Enclave Management Subsystem（EMS）：应用仍在高性能CS核运行；管理在有独立核、缓存、私有存储和I/O的EMS运行。可信调用门EMCall与专用mailbox连接两侧，EMS还统一管理私有页、共享页、密钥和设备DMA白名单。

核心创新是管理执行资源与计算资源的物理分离，加上覆盖管理接口和共享对象的授权机制。它是RISC-V通用TEE及相邻可信设备访问工作，不是直接基于Arm CCA的GPU虚拟化系统；“把管理搬到另一侧”也不是它全部安全论证。

## 3. 威胁模型和可信基

攻击者可控制CS OS/Hypervisor，提交恶意enclave，利用受控通道与微架构观测，并进行冷启动读内存。论文排除物理内存重放、拒绝服务、不安全enclave代码和enclave主动泄密；计算侧enclave本身的微架构侧信道保持既有TEE水平，并未全部解决。

其TCB包含整个SoC包及被enclave使用的外设、初始化与安全启动固件、CS侧EMCall、EMS Runtime。EMS可访问CS内存和I/O，CS不能反向访问EMS私有空间；这是一种权限不对称，EMS本身仍必须可信。

3843行Rust是作者声明的EMS Runtime规模，不是全部固件、硬件及设备驱动的总TCB。作者称其规模适合形式验证，但本文未见已完成的形式验证产物；Rust也不能单独证明跨端并发、授权和生命周期逻辑正确。论文将部分已有TEE概括为不防物理重放，是其比较口径，不推广为所有版本平台的通用事实。

## 4. EMCall：从真实调用者建立授权上下文

生命周期、分配/换页、通信、密钥与证明分别有专用primitive。EMCall运行在CS最高特权，安全启动校验并以加密和完整性保护；调用通过非推测模式传递。调用门检查当前特权，并自动封装当前enclaveID，阻止请求方自行冒用另一个enclave身份；EMS进一步检查参数。

EENTER/ERESUME同时涉及EMS控制结构与CS寄存器，论文要求EMCall原子更新上下文，防止不可信中断处理插入半切换状态。异常先进入EMCall，记录cause/PC；页故障、未对齐访问交EMS，timer和非法指令等交CS OS。这里保护的是上下文切换与异常分派，不等于证明所有异常原因真实或每个handler副作用都被应用授权。

对项目，这与RMM认证原始Client而非相信请求载荷里的Client编号一致。现有RMM队列和私有快照应作为基础，重点检查高权限入口到实际资源操作之间是否始终使用同一身份、对象实例和授权状态；不需要重造一套身份机制。

## 5. mailbox与请求响应：身份、完成和唤醒分开

EMCall将请求放入私有Tx ring，硬件transmitter转移到mailbox并向EMS发中断；EMS接收后用多线程处理，再写回response queue。CS侧EMCall用轮询获取响应，以避开不可信CS OS中断处理；两侧队列对普通CS软件不可见。每个请求与响应通过唯一标识独占绑定。

这支持“被保护的队列记录承载语义，通知触发检查”的设计方向，但论文没有展开唯一标识的位宽、回绕、服务重启代次、设备reset后迟到响应和跨VM ACK协议。不能把请求唯一标识直接当作已证明具备持久防重放能力。

作者以随机primitive调度、并发EMS处理、传输不可干预和轮询噪声论证时序攻击难度。物理隔离切断部分共享缓存通道有结构依据；噪声和粗粒度观察并不自动证明零泄漏或无干扰，论文未给出充分的统计攻击测量或形式时序非干扰证明。总线竞争及请求往返延迟仍应按实际可观测面分析。

## 6. 私有页：归属与缓存授权必须一致

EMS预取CS OS页到内存池，动态分配从池中完成，回OS前清零；扩池阈值随机化。每个enclave使用EMS管理且对enclave自身/OS均不可修改的独立页表，切换时由EMCall更新根。换出由EMS选择随机数量和位置，正文强调优先返回池中未使用页，以降低攻击者定向换出正在访问页面的能力；不能将其表述为完整ORAM式隐藏。

CS页表遍历器在非enclave TLB miss后用实际物理页号检查bitmap；命中enclave页则阻断。EMS另用私有page ownership table检查目标页是否属于另一enclave。bitmap变化与上下文切换触发相关TLB刷新；作者还禁用相应TLB共享。只有页表权限而缺陈旧翻译失效，不能实现其所需授权边界。

bitmap只区分是否为enclave页；跨enclave细分由归属表与EMS控制的映射承担。对于本项目，相应义务已由RMM身份、逐对象/物理页授权与GPUVM等基础承接，应继续检查实际HPA及翻译生命周期；不要求把该CPU PTW bitmap照搬为GPU Stage-2。

## 7. 共享对象：成员资格、权限和销毁权

共享区域使用独立于私有页的密钥。EMS按初始sender enclaveID和ShmID导出密钥并将KeyID写入受保护页表与内存加密引擎，CS软件只处理身份与ShmID。接收方先经本地证明和sender批准，sender用ESHMSHR把接收方加入legal connection list；ESHMAT必须验证该名单，猜中ShmID不能直接取得权限。

共享页在归属表中标为shared，不能再被当成私有页映射。sender给出最大权限并协商每个接收者权限；EMS同步名单与PTE。ESHMAT/ESHMDT维护active connection数，只有无活跃连接且调用者是初始sender时，才能用ESHMDES销毁回收。

这是本项目vmshm与GPU对象授权可借鉴的管理模式，但shared KeyID或合法成员不等于消息内容可信：被授权writer仍可提交恶意载荷，reader需要验证对象边界、结构和快照。active connection为零也不自动证明旧DMA已停止，论文没有展开GPU在途命令、页引用、IOTLB完成确认及回收原子事务的完整协议。

## 8. 设备访问与GPU支持的证据边界

driver enclave代表设备申请enclave-peripheral共享内存；硬件DMA whitelist以地址、大小、权限的寄存器对限制每个DMA，只能由EMS配置。原型无IOMMU，主要验证连续DMA区域的Gemmini和NIC场景。

GPU在第IX节讨论：可信driver enclave独占控制路径、bitmap保护共享数据，EMS管理IOMMU寄存器、IOTLB失效和翻译表。VM级TEE的专用primitive、snapshot/restore/migration也列为后续工作。不能把这些讨论计为真实GPU或多CVM共享的完整实现和性能证据。

对本项目保留既定假设：可信ProxyRealm统一控制SMMU，RMM认证原始Client；GPU映射建立时检查对象、物理页授权、权限和生命周期，软件IPA→HPA翻译并合成受保护、直接指向合法HPA的Stage-1；其他设备继续硬件Stage-2。HyperTEE提供管理职责和授权对象的比较依据，不以其原型缺IOMMU或硬件不同否定本项目假设。

## 9. 加密、证明与新鲜度的限制

设计采用每enclave独立KeyID和多密钥内存加密，高16位承载KeyID、低40位承载物理地址；KeyID耗尽可暂停enclave释放，要求先清TLB/cache。正文指定SHA-3的28位MAC，物理重放明确排除，因此不能宣称具备任意主动重放下完整新鲜度保护；也不能将有限标签强度当作128位认证保证。

安全启动校验EMS Runtime、CS固件与EMCall；制造阶段eFuse存EK/SK，EMS负责导出和擦除密钥。远程证明概述基于SIGMA，测量平台/enclave，本地证明基于同平台报告密钥，sealing按测量与设备秘密派生。论文没有给出足以逐字段审核所有challenge/会话/实例绑定的完整报文与证明模型，不能自行补写为已验证协议。

平台与enclave测量通过，仍须另判断当前共享成员、设备归属、任务实例和输出终态。一次启动证明或共享密钥配置不能替代多Client运行期完成记录的新鲜度检查。

## 10. 实验：端到端、微测、模拟和综合分开

作者在Synopsys HAPS-80 S104 FPGA构建BOOM/Rocket原型，EMS有Weak/Medium/Strong核配置，含AES/SHA-256/RSA加速器；Gemmini为16×16 PE、256KB全局buffer、64KB accumulator。RV8和wolfSSL评估enclave，SPEC CPU2017整数评估非enclave，另有MemStream、DNN与NIC通信。

| 作者测量或估算 | 结果及解释 |
| --- | --- |
| EMS Weak/Medium/Strong运行开销 | 平均5.7%/2.0%/1.9%；较强核的收益有限，不是所有工作负载都固定2% |
| primitive时间占Host-Native执行时间 | 无crypto为10.4%，有crypto为2.5%；EMEAS从7.8%降至0.1%，不是总应用加速倍数 |
| 分配微测 | 128KB–2MB、每大小重复1000次，相对普通malloc开销6.3%–49.7%；整体平均小不能掩盖这一高开销路径 |
| 内存加密/完整性微测 | MemStream 4–64MB，平均延迟开销3.1%；wolfSSL全部内存管理平均0.9%，分母和工作负载不同 |
| 非enclave bitmap检查 | SPEC平均1.9%，xalancbmk_r为4.6%；低TLB miss率支持平均小，不能保证所有访存模式 |
| 刷新与切换 | 平均每十亿指令16.72次flush，对SPEC平均低于0.7%；miniz 32MB、400Hz切换的作者开销不超过1.81% |
| 加密共享通信 | 相对需软件加解密的传统路径，ResNet50超过4.0倍、MobileNet超过3.3倍、MLP超过27.7倍、NIC约50倍；不是相对Native端到端GPU性能 |

CS 8–64核与EMS核数的SLO探索采用多进程软件模拟，用FPGA采样延迟校准；并非全部这些核数都在FPGA上直接实现。TSMC 7nm及Synopsys综合/布局布线估算EMS面积开销低于1%，64核配置约0.25%，2.5GHz/750MHz为时序分析最高频率，不能冒充已流片芯片或全部FPGA实验运行频率。

正文将primitive的2.5%与“Figure7 overall overhead (2.5%)”比较，但前文Medium/Strong整体均值为2.0%/1.9%；保留文字口径不一致，不自行修正原始数据。本文不据图形字体乱码重算全部均值，所有性能均为作者结果，不是本项目新测量。

## 11. 公开实现核验与复现限制

核对论文、作者出版列表、研究组页面及GitHub仓库名搜索。HyperTEE搜索仅返回同名服装网站HyperTEEMart，与论文无关；未确认匹配的EMS RTL/固件、Rust Runtime、EMCall、bitmap/whitelist实现和原始实验数据。本文因此没有固定“HyperTEE代码提交”，也不声称代码审计或可复现。

BOOM、Rocket、Gemmini、wolfSSL等是论文依赖，不将它们的上游仓库当作作者新增安全实现。作者致谢提及后续集成XiangShan，也不能推定该集成已公开、通过形式验证或已完成GPU支持。

## 12. 与项目及已有论文的关系

PORTAL/本项目把设备管理放在可信服务Realm，HyperTEE把管理放入物理隔离EMS；两者都要求真实调用者到管理请求的不可冒用绑定，区别在运行位置和观测面，不能仅因代码离开最高权限而删除其TCB责任。ACAI强调身份与映射归属一致，HyperTEE的page ownership与共享成员名单提供相邻实例；PhantomMap的实际页和生命周期检查仍有必要。

ITX管理整个IPU可信作业及认证数据流，HyperTEE更详细讨论CPU enclave共享对象权限；两者都未提供本项目所需完整多RealmGPU虚拟IRQ协议。Devlore/CAEC的中断可信路径，以及Heckler/WeSee/Sigy对异常副作用的分析，仍是另一组必须结合的证据。

本项目已有RMM认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127，本报告不把这些当作尚未设计。可继续论证：请求的原始Client与共享对象实例始终一致；完成记录只能在真实fence及结果可见后发布；IRQ只触发检查已授权记录；ACK不能撤销尚有访问的对象；旧代通知不能使新任务完成；撤销、引用释放、IOTLB失效和实际停止访问共同决定复用条件。

## 13. 独立评价和可验证研究方向

最可迁移的是管理权限、共享对象和请求响应三者的组合。对论文“物理隔离+噪声消除管理侧信道”的强表述应保留证据边界，不能据此给项目作无条件时序安全背书。GPU、VM和迁移的讨论也应作为设计线索，不能当成熟实现。

可围绕当前机制建立有界状态机或后续反例测试：伪造payload ClientID、猜中合法ShmID但不在成员名单、并发权限降级与提交、成员退出时仍有native fence、reset后迟到完成及相同句柄新代复用；预期结果是拒绝越权、受害Client状态不变、合法完成不被旧事件替代。这里只提出验证目标，未执行形式工具、fuzzer或硬件测试。

统一记录：全文/书目/公开材料范围核验与独立解读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件run-id、退出码或新增硬件PASS｜保留GPU/VM未实现范围、图形提取及公开代码缺口，持续研究。
