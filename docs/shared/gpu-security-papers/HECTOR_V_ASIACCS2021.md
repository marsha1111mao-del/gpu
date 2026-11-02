# HECTOR-V（ASIA CCS 2021）：可信外设所有权、中断路由与撤销清理的安全边界

研读日期：2026-10-27。完整阅读13页arXiv v3、全部66条参考文献，无附录；正式书目、来源版本及公开artifact线索独立核验。它是RISC-V可信I/O及异构TEE支撑论文，不是Arm CCA或GPU共享系统。未改运行代码，无新增性能测量。

## 1. 书目、版本与研究范围

题名 HECTOR-V: A Heterogeneous CPU Architecture for a Secure RISC-V Execution Environment；作者 Pascal Nasahl、Robert Schilling、Mario Werner、Stefan Mangard。ASIA CCS 2021，187–199，DOI [10.1145/3433210.3453112](https://doi.org/10.1145/3433210.3453112)，作者和页码由Crossref核对。

实际全文是[arXiv:2009.05262v3](https://arxiv.org/abs/2009.05262v3)，2021-03-09修订，13页、1332422字节，SHA256 `cfe0b81a8541f35652867d2be9e3b41514c8f823c05a4775c578d30b0dab31ab`；首页页脚确认v3。未取得最终ACM PDF，不将预印本与正式版逐字节等同；Crossref参考文献计数65与所读全文编号到66分别保留。

完整正文含HECTOR-V、RVSCP、实现、性能/面积、secure boot及trustlet用例、安全讨论、相关工作与结论。证据在 `build/cca-gpu-followup-20261027/hector-*-batch40/42.*`。本轮只做文本、元数据与来源检查，无硬件、构建、模拟、密码攻击或下载代码执行。

## 2. 问题、敌手与可信边界

作者认为共享主处理器的TEE容易暴露缓存/瞬态攻击面，而外置安全元件的SPI等链路慢且易物理探测；提出把独立安全核放入SoC，借共享互连访问外设，用硬件Security Monitor（SM）和外设wrapper管理可信I/O。

威胁模型包含恶意REE应用、OS、hypervisor及trustlet，也考虑软件接口缺陷和非法外设访问。硬件SM、标识传输、wrapper、MPU及RVSCP调度逻辑仍是可信执行基础；“考虑硬件保护缺陷”不等于能在任意恶意互连/任意硬件实现下保持安全。

SM owner负责配置访问许可，正文同时讨论其恶意时的影响限制。必须区分SM硬件与拥有管理权的软件：该owner可撤销设备、控制可配置资源并影响可用性，但不能直接越过不可配置wrapper访问永久绑定的安全存储。不能将“SM owner可能恶意”扩张成所有可配置DDR资源也天然免受恶意管理策略影响。

REE和TEE分离执行流水线、缓存和分支预测器，减少跨核共享微架构攻击；仍共用AXI互连及外部DDR。论文“所有cache/microarchitecture攻击均缓解”属于作者较强表述，本报告不据此宣称共享互连、内存争用、功耗和所有侧信道均消失。TEE内trustlet间共享安全核，作者另要求切换时清理微架构状态，并未给出本轮完整侧信道验证。

## 3. 标识、可信配置与外设所有权

标识包含core ID、process ID和peripheral ID。core ID在接口硬编码；RVSCP的process ID由硬件scheduler按trustlet切换；peripheral ID可承载控制流状态。身份不可伪造性依赖真实来源和可信更新路径，不能只信任请求载荷自报的ID。

原型在16位AXI user信号中传1位core、4位process和10位peripheral ID，文中这三项合计15位，剩余位用途未说明。标识随AXI地址/数据请求传送，外设wrapper检查后才向实际外设转发；失败返回SLVERR，经RRESP/BRESP报告。没有协议额外包不等于面积、时序或所有实现开销严格为零。

数据走AXI4，wrapper配置走独立AXI4-lite；只有SM能配置wrapper。REE/TEE只能经SM请求变更，避免非可信CPU直接重写权限。不可配置wrapper把完整或部分身份固定于设计时，用来保护密钥和安全代码存储；可配置wrapper有claimed/unclaimed状态，未认领时拒绝数据请求。

SM每外设记录状态和允许claim的ID列表；只有SM owner能配置许可和转移owner。普通claim先确认空闲且在许可列表，成功后将身份写入wrapper，形成当前实体的独占访问。release清除该绑定；不能由这里直接推定所有DMA事务、设备内部状态或挂起IRQ已经清除。

第4.1节说process/peripheral字段为0时忽略相应字段，第5.2节简写为process或peripheral为0时只按core检查。两段的精确组合语义需源码确认；这里保留“0会放宽身份匹配”的事实，不凭文字歧义给出具体RTL漏洞结论。

SM所有权可由当前owner转给另一个实体，作者建议先释放全部外设取得干净状态。建议并非强制原子协议；外设列表、未完成请求、IRQ和共享内存的迁移一致性仍需独立规定。当前项目不应照搬把SMMU/授权根配置权转交给非可信Client的策略。

## 4. 中断路由、撤销通知与回收窗口

普通设备IRQ由其wrapper按当前owner的core ID路由到REE或TEE，二者各有专用中断线。它证明硬件当前如何选择目标域，不等于中断包含特定job、trustlet或VM的不可伪造完成凭证；同一TEE内多个trustlet的目标分派、ACK和pending处理没有展开成完整协议。

撤销不是立即改owner。请求可由任意实体发起，普通请求须SM审批，SM owner请求总获准。SM启动预定义timer，并通过每外设专用中断通知旧owner；旧owner的cleanup ISR负责清秘密、停止事务、终止通信并主动release。这里将撤销控制通知与普通外设完成IRQ区分开。

若cleanup未在timeout前释放，SM强制清除wrapper的ID字段。第4.1节明确指出立即改归属会使新owner读取旧请求秘密，但超时强制路径没有给出同等详细的设备清理、DMA排空、结果销毁和IRQ去残留步骤；不能把“旧owner有一次中断清理机会”当作恶意/失效旧owner必然完成清理。

条件性窗口是：旧请求已被设备或互连接受→撤销阻断后续请求→新owner获准→旧结果或IRQ随后到达。仅检查请求进入时身份不能自动排除这一窗口。是否实际可触发取决于wrapper、AXI outstanding状态、具体外设和reset实现；未审计对应RTL，未执行攻击，不宣称确认存在可利用漏洞。

第7.1节还承认恶意SM owner可控制reset，提出reset也“可以”先通知目标，让其清理。该措辞是扩展建议，不是已证明所有reset路径强制等待清理；硬停旧owner后由谁处理其秘密及在途DMA，是迁移到GPU共享时的重要问题。

同理，外设IRQ按当前所有者路由，未必按产生事件时的所有者归属。论文没有完整规定ownership切换与pending IRQ、ACK、边沿/电平、迟到事件之间的原子关系；不能据“有专用线”认定跨代次旧事件复用已解决。

## 5. RVSCP：控制流状态到访问权限

RVSCP基于32位REMUS/Ri5CY，使用SCFP：编译期按控制流加密指令，运行期以密钥和累积状态解密；非法路径使状态错误，后续异常指令以一定概率检测。它不是论文新发明的密码CFI，也不是零失败概率的完整程序语义证明。

硬件round-robin调度四个virtual core，切换保存寄存器/SCFP状态并替换密钥和process ID，免去通用TEE OS。减少软件TCB的代价是增加可信RTL、固定四槽和有限OS服务；不能将没有TEE OS等同零TCB或可无代价运行复杂GPU驱动。

每个trustlet独立key CSR；示例有未加密boot代码，可从网络、二进制或其他来源取得key，然后开始解密执行。VC0代码存于永久绑定存储，VC1–VC3代码由可认领BRAM加载。论文没有完整给出恶意加载者环境下的远程证明、代码准入和安全密钥引导协议，不能把加密指令本身当作用户已经认证了所运行的trustlet。

对敏感外设的操作通过特定access function，合法调用经patch把SCFP置于同一状态；压缩状态进入10位peripheral ID，仅匹配时准许访问。它把控制流位置与I/O授权相连，限制某些非控制数据攻击；仍不证明该函数的地址、长度、对象归属、调用次数和业务语义合法。

10位压缩标识的碰撞、0通配值、攻击尝试次数及状态截断策略需独立论证；它不是1024位密码认证标签，也不能仅以“1/1024”给出完整系统成功率。当前项目应借鉴“特定操作只在合法状态允许”，复用可信执行计划，而不是新增10位权限令牌。

## 6. 原型、启动与性能证据

原型在lowRISC/RV64GC Rocket主核旁放RVSCP/RV32IMXIE安全核，外部DDR3、片上BRAM、AXI4/AXI4-lite；MPU最多16个物理内存region，既可独占也可共享。它是原型访问分区，不是多级页表或GPUVM的实证替代。

secure boot用VC0作为SM owner，先保持REE复位，认领SD/MPU，读取BBL并与安全存储预期hash比较；通过后授予DDR、启动REE，再由修改BBL检查Linux。预期hash更新权和VC0代码更新权同样属于信任链，不能把hash相等自动等同所有未来版本均符合安全策略。

完成启动后可把SM owner转给AP；不可配置存储继续受硬件保护，但AP可影响普通设备和reset。trustlet示例也由AP关停安全核、写VC1代码、配置私有/共享内存再启动。无GPU workload、GPU firmware可信加载、SMMU或CCA测量，不夸大为多Realm共享原型。

| 指标 | 作者结果与解释 |
| --- | --- |
| claim请求并读回状态 | REE发起平均188 cycles；不是GPU IRQ延迟，也不是任务总开销 |
| wrapper过滤 | 拷贝到BRAM时未测出性能影响；不证明所有高并发/时序配置严格无损 |
| DDR延迟 | LMBench `lat_mem_rd 64M 512`平均876ns；是内存延迟，不是TEE调用成本 |
| REE↔TEE消息 | 1MB写入并等待shared-memory ACK平均5498 cycles；只写同等外存5261 cycles，增加237 cycles，约4.50% |
| 消息通知实现 | 阻塞调用和共享状态；中断mailbox是可能扩展，非上述5498 cycles所测路径 |
| SCFP开销 | 引用原SCFP工作宏基准平均9.1%，RVSCP单线程未观察额外变化；不是整套HECTOR-V新测端到端开销 |
| FPGA面积 | Kintex-7综合LUT：lowRISC55443，+Ri5CY63648，+REMUS67024，+FRANKENSTEIN68746；表1开销14.8%、20.89%、23.99% |

表1的63648相对55443，直接按数字计算约14.80%；67024约20.89%，68746约23.99%。这些是FPGA LUT资源比，不是硅片面积、功耗或可信代码LoC；作者称更大AP下相对代价可忽略属于外推，未给同平台测量。

表2以63648 LUT配置为分母：Rocket33341/52.38%、Ri5CY5780/9.08%、SM446/0.7%、单wrapper43/0.07%、AXI4 crossbar3052/4.79%、AXI4-lite crossbar93/0.14%。仅446 LUT的SM不是整个TCB，wrapper/标识/调度/MPU及软件管理策略也在安全链中。

1MB的cycle数字未给足够测量细节去推定完整数据扫描、缓存状态、绝对带宽或GPU速度；本文保留作者定义及差分，不用不同平台频率换算ns。没有多Client公平性、撤销尾时延、IRQ风暴、强制回收或复位安全压力测试结果。

## 7. 公开资料与artifact核验边界

所读全文没有确认的HECTOR-V核心源码链接；其lowRISC、PULPino和SCFP引文是依赖/相关工作，不能替代本文完整实现。初次GitHub `HECTOR-V`宽查询总计227条，只取得首30项，主要是同名无关项目，不能以这次搜索声称不存在源码。

后续 `HECTOR RISC-V`及 `hector org:IAIK`各返回0且未标记incomplete；用户搜索取得名称为Pascal Nasahl的 `nasahlpa`账户，其20个公开仓库含lowrisc-chip与scfi候选。候选账户和依赖仓库尚不足以确认论文artifact；猜测作者/项目域名DNS失败、机构候选记录404如实保留，不把这些候选URL称为论文确认入口。

进一步保存lowrisc-chip的47个公开分支及scfi的单个main分支元数据，未见名为HECTOR-V的分支；分支名本身不足以证明包含或不含相关实现，未继续将依赖候选作为确认artifact。本轮没有确认匹配核心artifact，未审计wrapper RTL、SM命令状态机、撤销timer、AXI事务追踪、IRQ分派、CFI状态压缩或Linux模块源码，也没有复现文中性能。来源缺口与架构分析分开，不能从论文流程描述声称具体实现已通过安全验证。

## 8. 与 PORTAL、CAGE、ACAI 及当前项目的联系

HECTOR-V早于Arm CCA设备TEE主线，提供可信I/O、动态所有权和撤销通知的比较视角。PORTAL的服务Realm、CAGE的任务级设备管理、ACAI的身份/归属约束与它分处不同架构层；本项目通过可信ProxyRealm服务多个Client，需要进一步说明每任务归属，不能直接把REE/TEE二路IRQ选择当多VM协议。

接受既定假设：RMM认证原始Client，ProxyRealm统一控制SMMU；建图时核对对象、实际HPA授权、权限与生命周期，软件IPA→HPA合成受保护合法HPA Stage-1，执行期硬件持续限权，其他设备继续Stage-2。HECTOR-V的硬件身份过滤只作职责比较，不用实验板的硬件差异否定这个模型。

建议把已有逻辑明确为“允许新提交→停止新提交并撤销授权→确认真实终态或隔离失败→处理旧事务/事件→清理→重新授权”。这是本项目拟验证的条件，不是HECTOR-V已经形式化证明的状态机；设备无法证明静默时，应保留隔离和引用，不能只靠超时到期就将页/上下文交给新Client。

普通IRQ127继续作为持久通知入口，可信Proxy按native fence终态、错误状态、输出可见性及cookie/epoch发布完成；通知到达本身不代表成功。ACK只能确认消费对应代次的事件，迟到IRQ和取消任务不能推进新任务状态；复用GPUVM、认证队列和私有快照，不增加另一套身份或每任务硬件中断线。

reset需规定影响域：全设备复位若影响多个Client，其在途任务共同进入错误/取消处置，所有旧epoch完成失效，清理后才恢复授权；递增epoch阻止旧事件被接受，但不等于DMA已经停止。对映射撤销与资源回收要另有完成证据，而非依赖单个IRQ、计时器或配置寄存器写成功。

## 9. 独立评价与后续研究

最值得借鉴的是把不可伪造来源、外设访问检查、受保护配置以及撤销通知放在同一所有权体系中，并将控制流状态纳入敏感I/O准入。主要边界在超时回收、恶意reset、共享互连/TEE内部侧信道、任务级IRQ归属和可信加载准入；全文没有把这些都闭合为端到端协议。

后续引用链优先包括SANCTUARY、Sanctum、Keystone、SCFP及Antikernel；各自需独立全文，不能由本篇引文算已完成。GPU方向继续以PORTAL/CAGE/ACAI及可信中断相关研究为主线，本篇提供所有权迁移的对照，不扩大成任意RISC-V安全论文清单。

记录：改动目的｜补充可信外设所有权、中断路由及强制撤销研究；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜全文/66条参考文献及有界来源核验；run-id、命令、退出码与日志｜无硬件run-id，batch40/42 PDF、提取全文与获取记录保留；保留/撤回/待验证｜保留独立报告，artifact、强制回收与GPU扩展仍待验证。未改运行代码，无新增性能测量。
