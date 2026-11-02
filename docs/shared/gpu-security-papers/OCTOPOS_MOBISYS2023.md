# OctopOS：可验证独占I/O、会话可用性与GPU可信交接

## 1. 论文身份与研究位置

《Minimizing a Smartphone’s TCB for Security-Critical Programs with Exclusively-Used, Physically-Isolated, Statically-Partitioned Hardware》，Zhihao Yao、Seyed Mohammadjavad Seyed Talebi、Mingyi Chen、Ardalan Amiri Sani、Thomas Anderson；前两位共同一作，UCI与UW。MobiSys2023，Helsinki，June18–22，233–246页，DOI `10.1145/3581791.3596864`。Crossref精确匹配项核对题名、五作者、页码及2023-06-18日期。

本文提出split-trust硬件与OctopOS，利用物理隔离域、可委派mailbox、reset guard和domain-bound DMA缩减需要抵抗恶意输入的可信计算基。它是可信I/O与TEE的支撑研究，不是CCA GPU保护实现；§11把加速器作为未来增加的I/O域，没有实现GPU共享、SMMU或虚拟GPU中断认证。不能用它替代尚缺全文的GR-T、XpuTEE等直接GPU论文。

对本项目最有价值的是：设备授权必须由实际状态验证，资源交接必须有清洁边界，已授权会话的可用性与未来调度保证应分开。其“独占后弱信任复杂组件”的前提也帮助审查ProxyRealm是否仍接收恶意Client输入；独占一块GPU不自动消除GPU driver与固件的安全责任。

## 2. 来源、全文与artifact证据

[作者出版页](https://www.ics.uci.edu/~ardalan/publications.html)、[作者14页PDF](https://www.ics.uci.edu/~ardalan/papers/Yao_MobiSys23.pdf)、[正式DOI](https://doi.org/10.1145/3581791.3596864)、[软件库](https://github.com/trusslab/octopos)、[硬件库](https://github.com/trusslab/octopos_hardware)、[论文附录artifact DOI](https://doi.org/10.5281/zenodo.7898001)。最后一个是artifact标识，不能当论文DOI。作者页记录Best Artifact Award；获奖不等于本轮已复现。

作者PDF为1068227字节，SHA256 `e0c34983449f3b106260c3c0d97d5dc3b2d115624b7fe28bfd31712e0d87e901`；完整阅读§1–12、致谢、附录、123条引用，3图5表和形式验证示例代码，全部14页视觉核对。未取得出版方PDF进行字节比对。

取得并完整阅读两个当前main README，分别9144与19223字节；软件README标明AE提交 `b332fef5bafb7ff95577d5d0b7eca9656f5f1578`，硬件README标明 `1786e76591987ebf9a07888288daa8fba0dd44c8`。进一步取得固定硬件提交README（19107字节）和固定软件提交的 `applications/socket_client/socket_client.c`（5585字节），分别SHA256 `1a0356145ec411ed6b6b35c3766e553dda121589498c4092940587460fb52311`、`5a205443cb6b4d7c2dadc8acd6b741d68a5ec287eaa223a674d2e1226e2ecdbf`，有限静态阅读；固定README与当前版本仅所标AE提交说明差别。

GitHub API403，未取得完整树或通过Git对象验证commit/blob；固定软件README与TRM请求超时，Zenodo API拒绝连接。固定URL及内容哈希不等同完整仓库审计；未读全部RTL、形式验证harness、runtime socket实现、TPM和驱动。没有运行作者代码、SymbiYosys、模拟器、Vivado、攻击或硬件测试。

## 3. 强信任与弱信任：缩小的究竟是什么

§3定义strong trust为组件要抵抗恶意输入，weak trust为没有恶意输入时正确工作。论文后续简称TCB主要指前者，并假设所有组件没有攻击者植入的恶意后门。因此“CPU、内存或driver不在强TCB”不是这些组件可以随意计算错误、泄密或带后门。

基本原则是使用前reset到干净状态，经过证明的独占使用，使用后再次reset。复杂组件在目标会话中无法被攻击者触达，才可降低信任强度；目标程序仍要消毒外部网络等输入。共享GPU持续处理不同Client的命令时，必须说明谁验证命令、哪些MCU/固件能访问哪些页，不能仅以可信加载和exclusive ownership宣称driver脱离强TCB。

## 4. 静态分区与可验证mailbox

每个TEE、I/O及资源管理域有自己的处理器和内存，不共享内存；I/O寄存器与中断只接本域。隔离不是通过全系统可编程MMU/IOMMU施加，而是静态物理连接。此设计选择适合研究“减少隔离机制TCB”，与本项目复用GPU并用受保护页表实施隔离的选择不同，应比较其安全责任而非以实验板能力否定任一路线。

mailbox一端固定连接某域，另一端由硬件mux在多个域之间委派。资源管理器RM默认占有可委派端，授予目标域后该域独占，直到主动yield或配额耗尽。配额同时含消息数量与时间，任一耗尽即结束；消息数可无限，时间不可无限。活跃会话中RM不能任意抢回。

归属域和固定端可读状态寄存器，核验实际owner及remaining quota；未授权域获得dummy结果以避免披露其他会话。RM返回“成功”只是消息，不足以证明委派。mailbox在delegate、yield或expiry时硬件清空；清空通信队列不同于清理整个设备内部状态或等待在途DMA。

## 5. reset guard、测量与新鲜状态

reset guard阻断对活跃mailbox两端域的reset，避免恶意RM中途切断会话。论文讨论同样保护PMU/DVFS控制，但原型不支持域内DVFS；不能据此声称已评估任意GPU调频、掉电或全GPU reset下的隔离。

每域TPM PCR/locality记录bootloader测量，I/O service处理首个请求时扩展PCR，使Client能区分reset后未使用与已使用状态。程序同时验证mailbox owner、quota、预期测量和freshness，不只检查一个有签名的固件哈希。远端nonce认证还承担证明新鲜度的不同职责。

reset由不可信RM触发，但Client必须验证已发生且之后未被其他域使用。受限I/O存在明确例外：存储在reset后需先接受RM的分区配置，再委派给TEE，所以不能严格声称每次都从完全未接触输入的服务开始；存储策略/通用可用性仍需强信任相应服务。

## 6. domain-bound DMA与中断路线

DMA硬连只读写untrusted域内存；arbiter仅在untrusted域占有I/O时把设备流接DMA，否则接I/O域FIFO。这里没有“任意TEE页先经IOMMU检查”的实现，也没有绕过GPU内部MMU的实验证据。项目应保留RMM认证身份、实际HPA授权、受保护根配置和页表，以及撤销后的TLB失效与DMA静默证据。

原型只有网络使用中断，其他I/O轮询。网络服务TEE时，FIFO中断接网络域Microblaze；服务untrusted时，DMA完成中断接A53。这是物理连接/复用状态控制，不是共享GPU上对每个Client的虚拟IRQ认证，更不是中断天然携带可信job身份。

对项目的推论是可信Proxy先依据设备原始状态和原生fence确定任务事实，再把通知绑定Client、context、job cookie与epoch。Client收到事件只查询受保护终态；SGI/共享队列不得成为成功证据。重复、乱序、延迟及reset前旧IRQ应幂等处理，不允许借通知释放仍在DMA中的页。

## 7. 会话可用性与通用可用性

session availability保护“已获得会话在配额内不被RM撤走”，并假定电量足够；RM仍能拒绝或无限推迟未来请求。general availability还包括周期运行、镜像与持久数据可用，需要额外信任RM和storage。加密只能保护相应数据的机密性/完整性，不阻止Host删除密文或拒绝读取。

2024年的Hora进一步把可信周期scheduler引入TCB，目标与本文不完全相同。项目若只主张跨Client机密性/完整性，可以保留恶意Host拒绝服务边界；若主张限时完成或公平性，则须定义可信准入、预算、计时器和恢复条件。超时本身不能被转换为GPU完成或可回收状态。

## 8. 原型及形式验证范围

ZCU102的A53运行PetaLinux，FPGA实现7个100MHz无MMU/cache的Microblaze：2个TEE、RM及4个I/O域；TPM由外接Raspberry Pi4模拟，另有Microblaze转发。untrusted使用主内存，其余域使用约3.2MB片上ROM/RAM。12个mailbox和11个固定队列；控制消息4×64B，数据消息4×512B。

原型共享时钟源，FPGA域共享电源域，是作者明确的限制；不能据架构目标声称原型已完全分离时钟/电压故障。板上SD可由A53直接编程，不适合作隔离存储，Pmod MicroSD慢；性能评估改用存储域专属DRAM，测得的是该配置的上界，不是实际安全SD吞吐。

软件及模拟器约39000行C，含约5000行修改驱动/crypto。可信硬件约1630行Verilog和800行Python，验证约3000行SystemVerilog。Table1列20项定理及额外lemmas，覆盖mailbox独占、配额、可验证归属、wipe、reset guard、arbiter和ROM不可逆只读；作者用SymbiYosys SMTBMC k-induction，并报告修复过委派逻辑错误。

该证明不覆盖全部OctopOS软件、TPM实现、任意物理reset效果、固件无漏洞或GPU任务正确性。本轮没有harness或证明日志，论文代码中next-cycle断言的含义也不应扩展成任意SoC端到端时序保证。

## 9. 实验数据与独立复算

作者各实验重复5次，报告均值±标准差，不是置信区间。所有下面结果是论文数据及本轮算术，未在本项目测量；实验平台、clock、服务内容与GPU共享不同，不能拿来预测glmark提分。

| 项目 | 原文数据 | 复算与边界 |
| --- | --- | --- |
| 额外硬件估算 | LUT69999×36、FF63188×24、BRAM27061649bit×6 | 合计166406370晶体管，为15B的1.1094%；是FPGA资源到ASIC的粗估，不是流片实测 |
| mailbox | A53–Microblaze7.07MB/s、18.2µs；Microblaze间9.64MB/s、15.26µs | 延迟是64B请求加ACK的RTT，不是单向IRQ延迟 |
| 存储 | best8.13/6.10，TEE4.39/3.93MB/s读/写 | TEE保持约54.00%/64.43%；专属DRAM，非flash |
| 网络 | baseline/untrusted943Mbit/s与0.17ms；TEE0.567Mbit/s与23.92ms | TEE吞吐保留约0.0601%，RTT约140.71倍；“接近原生”不能延伸到TEE路径 |
| boot | 其他域4.03s，untrusted另加8.65s | 均值合计12.68s，不在未知协方差时直接相加标准差 |
| 普通NFS程序 | 3.86±0.03s对3.84±0.04s | 均值多0.5208%，不能仅据此判断统计显著性 |
| 1MB读取/哈希/发送 | TEE1.75s对native0.23s | 约7.61倍；分解0.30+0.22+1.21+0.01=1.74s，0.01s差保留为舍入/未分解 |
| 额外交接成本 | 网络曾被使用后重建4.12±0.96s | 原基准假设无竞争且提前reset，不能当含争用上界 |
| 普通程序受阻 | baseline读100MB24.26s，会话造成2.58s gap | gap约为baseline的10.63%，不是完整测得的总开销百分比 |
| 哈希能量 | TEE2.03J对native0.63J | 约3.22倍；Vivado估计功率乘测得时间，不是仪表整机能耗 |

网络10倍改进是作者对去掉人工延迟的预期，非已测结果；延迟用于规避封闭Ethernet AXI IP疑似问题。普通域943Mbit/s依靠domain-bound DMA，不能反推mailbox也能达到同样性能。作者期待ASIC更快属于设计预测，不是任意平台严格性能下界。

banking482行，列出的58+107+207+93=465；insulin563行，列出的217+200+128=545；分别17/18行未逐项列出，不当作完整分解或学术不端证据。网络driver7217、storage1091、keyboard154、serial165行不含bootloader/mailbox支持。49个runtime API不是已证明49个安全接口。

## 10. 取得源码后的有限发现

固定软件提交的socket client默认调用throughput测试，latency与send_receive入口被注释；ARCH_SEC_HW分支插入多次打印式delay。throughput写5003个256B数据块，注释记录末3包丢失且可能关联mailbox corruption；这是作者保留的诊断文字，不是本轮已复现或确认根因。

三个测试函数有32字节局部buf，却把512作为 `read_from_socket` 长度传入。若runtime遵守常规“最多写入请求长度”语义且对端可返回大数据，会产生潜在栈越界条件；没有取得runtime实现、服务器与可达性证据，不能直接宣称利用成立。独占I/O无法代替应用输入校验，这一点反而与论文强/弱信任区分相呼应。

当前软件README将TEE网络测试称half-duplex并建议吞吐翻倍；论文baseline用iperf、TEE用自写程序，未取得server计时/计数实现，不能擅自改写Table5数值或把两个方向相加称单向性能。README还解释mailbox用毫秒tick、多次重复平均以避免每微秒中断吞噬100MHz处理器；这不构成GPU通知尾延迟或中断攻击验证。

固定硬件README完整阅读内容与当前文件除AE提交说明外一致，提供Vivado2020.1、Ethernet IP许可和TPM外接步骤。文档注明无TPM仍可boot但不能完成PCR attestation，提醒项目区分“服务启动成功”与“可信授权链建立成功”。这些是文档证据，本轮未执行其中安装/构建/设备命令。

## 11. 与PORTAL、CAGE、ACAI和项目的关系

PORTAL的可信服务Realm、ACAI的设备身份/映射归属和CAGE的GPU保护扩展仍是直接主线；OctopOS补充“委派结果可验证、会话中不可抢占、交接可清洁”的组织原则。它不证明把GPU Stage-2前移到建图阶段天然安全，也不要求项目复制静态独立处理器；本项目应在既定硬件假设下证明软件授权与持续Stage-1约束的组合。

建议一：每次授权生成不可由Client改写的lease记录，绑定RMM认证Client、device/context、真实HPA集合、权限、job cookie和epoch；Client提供的ID或RM成功回复只作索引。lease必须由Proxy可信状态校验，不能以共享内存中的自报owner作为归属根。

建议二：把交接写成明确状态机：停止接收旧epoch任务，等待/取消任务并确认设备静默，撤销映射和完成必要缓存/TLB处理，隔离或清洁内部状态，再允许新owner使用。发生超时、reset失败或无法证明DMA静默时进入quarantine。mailbox wipe、fence完成、队列为空与实际页安全重用是不同判据。

建议三：通知使用受保护终态记录加幂等唤醒，明确区分通知到达、任务终态、输出可见、应用正确、完成发布、DMA静默及安全回收。SGI只提示有状态可读；可信Proxy从原生fence/设备错误取得完成事实，按cookie/epoch拒绝旧事件，避免跨Client唤醒导致越权操作。论文物理中断接线仅提供启发，不能当此协议的证明。

建议四：若提供有界服务，联合预留CPU、GPU上下文/时间、页预算与所需可信镜像，并把reset/drain成本计入窗口。若只提供会话隔离，就明确不承诺恶意Host下的未来调度。多Client并发共享会扩大需要抵抗恶意输入的部分，应以TCB职责表而非单一代码行数描述。

## 12. 后续验证与本轮记录

后续设计验证应覆盖伪造委派成功、错误owner、过期epoch、旧IRQ重放、超额消息、配额到期仍有DMA、reset中途失败、跨Client共享页别名、镜像被删除和恶意输入解析；同时保留独立受害Client哨兵。必须分别记录拒绝、任务错误、资源泄漏、可用性和静默内存破坏，不能以进程正常退出代替隔离成功。

本批同时复查XpuTEE作者页，确认其TOCS25条目但没有可用全文链接；GR-T的arXiv v2地址404，已有v1为早期CODY，不当正式GR-T全文。两项继续待查，未因完成OctopOS而计为完成。

统一记录：补充可信I/O独占与GPU交接设计｜glmark未测→未测，分差/百分比不适用｜未改运行代码，无新增性能测量｜论文全文/14页视觉/两份当前README/固定路径两文件有限静态/算术/Notion完整回读；证据位于 `build/cca-gpu-followup-20261027/` 的130批文件｜无作者代码/形式工具/模拟/构建/攻击/硬件run-id｜保留研究结论；安全机制仍属设计建议，整体续研active。
