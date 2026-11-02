# CCX：Arm CCA 的 SGX 语义兼容、GPT 归属与可信异常恢复

研读日期：2026-10-28。完整阅读17页 arXiv v1、§I–X、97条参考文献与附录，核对6图、8表和1段汇编，10页渲染视觉阅读；固定两个作者仓库并定向静态阅读可信服务源码。本文是直接 CCA 运行时研究，非 GPU TEE 或 GPU 多 Client 共享实现。未改运行代码，无新增性能测量。

## 1. 文献身份、版本与证据

CCX: Enabling Unmodified Intel SGX Applications on Arm CCA。Matti Schulze、Thorsten Holz、Felix Freiling，FAU Erlangen-Nürnberg 与 Max Planck Institute for Security and Privacy。[arXiv:2605.07548v1](https://arxiv.org/abs/2605.07548v1)，2026-05-08；[全文](https://arxiv.org/pdf/2605.07548v1)。本次未确认正式会议发表，不补造会议或正式出版 DOI。

取得PDF为514756字节，严格解析17页，SHA256为 `0885f09fb567de98bff8abdbfe585a8fbfd61f19047c02346373a278f55b0056`；摘要页确认唯一所列v1与日期，PDF水印同为v1。全文、逐页文字、摘要页、10页渲染及源码清单位于 `build/cca-gpu-followup-20261027/` 的ccx batch84文件。

论文明确提供[功能原型](https://github.com/ma-schulze/ccx)和[性能原型](https://github.com/ma-schulze/ccx_nitrogen8m)。分别固定 `17a641bd0cd72ae0f25314513c49ae4ab550ccf0` 和 `e5ed3d1f6ac33f92a8ecd966a7bd71e96c72ccf9`，均为2026-05-07公开提交。它们有论文明确关联，不依赖同名搜索猜测。

## 2. 背景、问题和新增贡献

SGX应用通常拆成同一进程内的不可信U-App与可信T-App，通过ECALL/OCALL交互，依赖SDK、线程控制、页状态、密钥与证明语义。CCA以机密VM为基本抽象，直接把整套应用装进Realm既扩大软件信任范围，也不能自动保留SGX的细粒度接口。

CCX的增量是将SGX微程序语义在Arm固件中重新实现，并移植SDK、内核驱动及编译器，使既有SGX应用源码可以重新编译运行。它借用SHELTER式多GPT实现隔离，但研究重点是已有生态兼容，而非首次提出GPT隔离。

“Unmodified”指所测应用源码无需修改，仍须交叉编译；不是直接运行x86二进制，也不是SDK、内核、GCC或TF-A不修改。依赖x86汇编或复杂LibOS的应用不能仅凭本文标题推定兼容；作者把Gramine/Occlum移植留作后续工程。

## 3. 威胁模型、可信基与排除项

攻击者可以控制Normal、Secure、Realm中的软件，包括Host OS、Hypervisor、其他enclave以及RMM。CCX只依赖可信EL3 Monitor及正确硬件来强制隔离；目标enclave自身无漏洞是论文前提。它不保证可用性，不全面缓解侧信道，排除硬件级攻击。

这是对CCA硬件原语的自定义使用，不应将“RMM不可信”说成所有标准CCA部署的默认威胁模型。常规Realm保护依赖可信RMM，而本项目明确由RMM认证原始Client。CCX的取舍可用于比较，不构成要求本项目也移除RMM信任的理由。

“只信任Monitor”描述软件边界，不表示可信实现只有CCX新增的4462行。Monitor依赖TF-A上下文、GPT管理、密码库与平台固件；可信enclave/runtime本身也要满足各自的安全假设。更高权限位置易于控制入口，同时使新增解析器错误影响更广。

## 4. 架构与调用路径

U-App、OS和SGX驱动留在Normal；T-App在Realm EL0执行；CCX-Service在EL3，包含SMC-Handler、Trap-Handler、CPUID-Handler、CCX-Core及CCA-Backend。Core实现SGX页管理、初始化、进入退出、密钥及报告语义，Backend负责Arm上下文和GPT切换。

内核态ENCLS由SMC代替。EL0不能直接执行SMC进入EL3，作者以访问 `PMCCNTR_EL0` 的异常作为ENCLU/CPUID调用门，并配置PMU陷入寄存器。工具链生成gadget，寄存器携带函数编号和参数，EL3解码并执行微程序。

设计§IV要求调用门不被其他EL拦截；实现§V随后承认Normal侧低EL可以拦截访问，视为与OS阻断SGX执行相同的可用性行为。Realm侧则在进入前清理相关EL2陷入控制，要求RMM不能运行期插入。两侧边界应分别理解，不能统一概括为任何环境下EL0→EL3都不可阻断。

PMU寄存器复用会影响真实用户态PMU使用，属于兼容性代价。正文先描述x0–x3映射，Listing1实际以x0传SMC标识、x1传leaf、x2–x4传参数；固定实现的handler也是后一种布局。实现协议应以完整ABI定义为准，而非照搬含糊寄存器概述。

## 5. 内存归属、就地委派与多GPT

EPC页放在Realm物理内存，EPCM元数据放在Root，记录所属SECS、页类型、线性地址、权限和状态。与固定EPC容量下频繁换页不同，CCX通过GPT动态接纳原有物理页；SDK/内核双重映射同一PA模拟SGX复制后新VA的行为，从而减少复制。

每个enclave拥有enclGPT，另有供系统及RMM使用的sysGPT。某页被接纳后，仅其所属enclave的GPT将该页设为Realm可访问，其他GPT将它设为不可访问。进入时切换当前核心GPT，退出时恢复；这防止“所有enclave同处Realm就天然相互可访问”的问题。

正确性条件不仅是存在多份GPT：必须保证页归属更新覆盖所有视图及未来新建视图，授权失败可回滚，切换与缓存失效一致，多核不会看到失效前的旧授权。EL3不被低EL中断只提供局部执行属性，不能单独证明多核共享状态、远端缓存和设备访问已同步。

与SGX的Page Miss Handler比较还需区分PA隔离和VA/权限完整性。SGX的运行期检查包含enclave线性地址与权限；多GPT主要提供物理域可达性。CCX源码在若干微程序里检查EPCM线性地址，但本次尚未找到足以证明普通每次load/store也等价约束Host可变页表的完整论证。应继续核验页表修改、同一enclave内页替换及权限提升的约束，不能由域间PA隔离直接宣称全部SGX访问语义等价。

这一点对项目是支持既有假设：受保护的实际GPU页表、root和HPA授权本来就是必要条件。CPU的每核GPT不能替代GPU/SMMU对其他访问主体的授权，也不能直接用于证明GPU并发隔离。

## 6. 中断、同步异常与恢复

外部中断通过 `SCR_EL3` 路由到可信EL3，CCX执行AEX并将执行交回Normal OS。同步异常通常不能直接这样路由，所以enclave文本包含异常trampoline，进入时配置 `VBAR_EL1`，由它再陷入CCX；不可信OS处理后经ERESUME恢复。

线程的TCS、SSA及按核心保存的active enclave上下文，决定保存和恢复哪一个执行实例；这比仅记录当前线程编号更完整。不过安全路由不是事件来源认证，也不证明OS传来的异常原因可信，更不回答哪个GPU job成功。项目仍须用native fence及可信job记录关联任务，IRQ127只作为通知。

论文实现AEX-Notify，并用SDK样例测试。作者提出进一步禁用某些中断或随机延迟转发作为未来防御，没有声称已经实现。AEX-Notify是抗精确单步的组件，不应推广为消除所有时序泄漏、任意异常注入或多VM干扰。

本次看到 `ccx_aex` 对内部异常与外部中断走不同分支；内部路径调用恢复GPT的backend，外部路径在所读函数末尾未直接调用相同函数。是否由完整异常返回路径补偿尚未核验，因而记为恢复对称性的待查项，不据局部阅读宣称已经构造隔离突破。其SSA地址计算还明确假设frame size为1，不能据普通样例推广到任意嵌套配置。

## 7. 密钥、证明和版本兼容

CCX移植EGETKEY和EREPORT，用于sealing、local attestation等。论文描述两个enclave互相验证报告后建立安全通道；远程证明没有完成，CPAK→Provisioning Key→Attestation Key及PvE/QE流程只是拟议集成路径。

远程证明未完成是原型证据边界，并非以载体缺少某能力否定其设计。即使接入真实证明，仍需绑定服务配置、会话、当前实例与设备授权；相同测量值不代表同一个Proxy实例，也不代表持有当前GPU。

密钥保护与防回滚也不同。sealing可保护密文机密性和完整性，不自动记录哪个版本最新；本项目运行期cookie/epoch与跨重启状态连续性应分别定义，没有持久承诺时不为每个job强加持久存储。

## 8. 原型与功能验证

功能平台为QEMU9.2.3、TF-A2.10.0、RMM0.4.0、Linux6.2.0。五个SDK样例覆盖SampleEnclave、CXX17SGXDemo、LocalAttestation、SealUnseal和SampleAEXNotify；五个真实应用是SGX-kmeans、TaLoS、SGX SQLite、TrustFL及secure-analytics-sgx。TaLoS进一步用于nginx TLS库。

作者报告这些应用重新编译后运行结果与SGX一致，支持所测工作负载的功能可行性。未给出足够覆盖任意恶意输入、异常交错或所有SGX指令状态组合的完备测试，因此不将“selected subset覆盖功能”理解为语义等价证明。此处TrustFL为CPU enclave应用测试，不是GPU机密联邦学习的设备隔离实验。

性能平台为Nitrogen8M、四核Cortex-A53 1.5GHz、2GB RAM、TF-A2.2、Linux6.1.22。用相同GPT结构及debug寄存器访问代替缺失RME操作；QEMU验证功能，板端估计性能。该方法作为原型合理，但没有测得真实MPE加密/完整性和全部GPC缓存代价。没有因此否定项目采用OpenCCA载体的研究方法。

## 9. 微基准结果与成本解释

作者每项执行100次取均值，称方差可忽略而省略；ENCLS用内核ktime，ENCLU用 `clock_gettime` 实时时钟。下表从附录TableVIII换算，不是本次复现数据。

| 操作 | 原文纳秒 | 换算及含义 |
| --- | --- | --- |
| ECREATE | 15281521 | 15.281521ms，主要成本为从头创建GPT |
| EINIT | 1898520 | 1.898520ms，含初始化密码检查 |
| EADD / EAUG | 18840 / 29040 | 18.840 / 29.040μs，动态页操作 |
| EWB / ELDU或ELDB | 910200 / 843360 | 910.200 / 843.360μs，换页加解密路径 |
| EENTER / EEXIT | 15153 / 2334 | 合计17.487μs，是所列微程序均值之和 |
| ERESUME | 13664 | 13.664μs，不等于完整中断服务及恢复延迟 |
| EREPORT / EGETKEY | 114639 / 53440 | 114.639 / 53.440μs，不包含远程证明服务 |

动态EPC减少受容量限制的换页需求，不等于内存无限或所有压力下都不需回收。创建只发生一次也不能保证代价普遍可忽略：大量短生命周期实例或频繁创建时，15ms级成本仍需计入。17.487μs不能外推为一次OCALL、完整ECALL往返或GPU完成链端到端成本。

## 10. NBench、比较口径和TCB

NBench在Arm板端分别比较原生与CCX版本；另一组在Xeon Silver4509Y、128GB上分别比较原生与SGX版本。两侧各自归一化，不是同一CPU上的跨系统直接速度比较。论文拒绝跨CPU微基准缩放是合理的，其后跨论文总体开销排序也应保留平台、负载与统计差异。

作者的“约1%开销”明确排除了BITFIELD和FOURIER两个高开销项目，归因于SGX SDK内数学库不够优化。不能将它写成完整10项平均、每项上界或包含创建/密码操作的总开销。Fig6纵轴写Normalized Runtime，但图注及性能解释又以性能归一化描述，低柱与正文变慢对应；没有原始数据时，本报告不把低柱直接倒算成精确耗时增长百分比。

TableIV新增4462 SLOC，其中Core2341、Backend337、CPUID120、SMC/Trap149、EPC28、EPCM56、Crypto48、Multi-GPT106、Utils366、Headers911。约6000行SDK及650行内核改动另计；4462不是整个可信系统的总TCB。

作者以TF-A源码约593k、其中mbedtls143k作比较，新增比例约0.75%，故称低于1%。源码仓库包含多平台内容，不能把该数字当单一构建实际可达TCB精确大小；复用已有密码库不使密码实现从信任基础消失。TableV的其他系统SLOC口径与采样版本也不同，不由新增行数小推出安全性更强。

## 11. 固定源码核验范围

两个仓库根树分别10项和7项，完整且未截断；初始递归查询分别68447/55239项均明确truncated，故没有声称完整取得整仓。另单独取得功能原型CCX服务子树29项、未截断。README说明功能树含TF-A、RMM、QEMU、SDK、Linux、GCC和样例；构建指南提示并行构建可能存在race，建议失败时串行，这不等于运行期隔离漏洞。

9个关键blob通过GitHub API取得，逐项核对长度与Git blob SHA，并记录SHA256；另取得功能README及 `ccx_svc.c`。完整读了service handler、multi-GPT、EPCM/EPC、encryption、指令编号头和backend；对107083字节微程序文件重点读EADD、ECREATE、EREMOVE、ETRACK、EGETKEY/EREPORT、ERESUME校验和AEX，未宣称每条指令及整个SDK已审计。结构体头取得但只定向核对布局。

原始raw下载16项仅4项成功，其他超时或网络不可达；上述9项通过固定blob API补取，不以下载失败表示文件不存在。性能原型本批只核对仓库、提交和目录，README及三份定向源码raw获取失败，未声称已比较两套完整实现。所有失败保留在获取清单中。

静态观察一：SMC与trap handler对无效func_id只调用ERROR后继续索引指令表，表中还存在NULL保留槽。该层未见完整fail-closed分派检查；仍需核对上游入口、构建配置及实际可达性，不在本报告执行异常调用或宣称已利用。移植到可信Proxy接口时，未知操作必须在任何副作用之前拒绝。

静态观察二： `get_epcm_entry_for_page` 直接以PA右移索引EPCM，本函数未见与curr_epcm_size比较；page source的对齐、地址转换成功和非空检查不能单独证明索引合法。需要核验所有入口的物理范围约束，不将该观察直接宣告为所有调用均可越界。

静态观察三：multi-GPT使用10项gpts_bases数组，含系统视图；页cache索引递增处未见容量检查，委派/撤销辅助路径也未逐项传播底层返回码。失败容量、资源回滚和远端视图失效需单独验证，不能从“动态EPC”推定任意扩展。EADD等路径还存在取锁后错误直接return的分支，需检查错误清理；可用性排除不免除共享可信组件的状态一致性要求。

静态观察四：加密模块将CR_BASE_PK与MASTER_DERIVATION_KEY初始化为零，所读EWB、EGETKEY和EREPORT路径使用这些变量，所读setup未见真实RoT注入。本文未核验全部启动写入路径，因而不声称全仓永远没有替换；这些材料至少不足以把样例local attestation成功当作生产密钥来源已验证。ETRACK实现直接返回OK也表明状态机名义接口与完整语义须分别核验。

这些是公开原型的证据与待查点，未执行编译、QEMU、硬件、fuzzer或攻击。没有通过私自修补论文原型再把结果归于作者，也没有将这些问题归于本项目代码。

## 12. 安全论证的强度和局限

论文按EPC访问、TOCTOU、跨enclave、单步、缓存、分支预测与推测执行分类论证；主要是机制分析及正常应用实验证据，形式验证留作未来。其物理内存加密等陈述应按目标架构要求和实现选择逐项核实，不能推广为任意模拟平台已实现真实机密性/新鲜性引擎。

先保护内存再验证内容可以缩小TOCTOU，但微程序参数中的共享结构、间接指针、其他核心和设备写入也须纳入保护。对同一物理页的CPU/SMMU/GPU别名，安全来自所有访问路径都受相同授权约束，不能仅靠EL3当前线程“原子执行”。

论文最有说服力的是跨ISA重建成熟API并运行一组真实应用的工程可行性。对“完整SGX兼容”和“相当安全性”的宽泛主张，仍需更多负例、并发状态机和运行期VA/权限约束证据。它没有实现GPU直通、DMA授权、跨Client完成路由或reset后的安全复用。

## 13. 与库内论文和当前项目的关系

| 相关工作 | 与CCX的区别或互补 | 项目可使用的结论 |
| --- | --- | --- |
| SHELTER / NanoZone / HiveTEE / CCAegis | 同为CCA细粒度隔离，CCX强调SGX兼容 | 访问主体、视图、对象归属和权限须一致；自定义GPT不是完整任务授权 |
| PORTAL / CAGE / ACAI | 设备服务与加速器路径；CCX无设备保护原型 | 保留可信ProxyRealm、RMM认证及实际HPA授权，不把全部GPU逻辑搬入EL3 |
| AEX-Notify / TEEtime / Devlore | 事件处理与控制权的不同问题 | 可信保存/恢复、事件路由、通知语义和执行及时性分别论证 |
| PhantomMap | 实际页与中间元数据检查 | 将EPCM类物理来源约束落实到每个GPU映射sink及对象generation |
| ASTER / CAEC | 服务准入、身份/共享通信与生命周期 | 兼容调用API或证明某镜像，仍须绑定当前服务实例和会话 |

项目第一部分可借鉴兼容层与安全执行层分离的工程方法，分别记录API覆盖和过界成本；第二部分应继续使用已有GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch与persistent IRQ127。CCX没有理由替换这些机制，也没有证明它们已覆盖全部异常交错。

## 14. 可继续验证的设计命题

建议一：对每个可信请求明确检查输入全集、当前调用者身份和合法状态，再产生副作用；拒绝未知opcode、空处理器、范围溢出及不属于当前Client的对象。失败路径必须恢复锁、引用、页归属及部分安装状态。这是接口状态机要求，不必新增另一套Client编号。

建议二：把进入执行和退出/恢复做成对称的受保护事务：原始Client实例、session、GPUVM/root generation、backing generation、权限、cookie与device epoch关联同一记录。合法乱序完成可推进各自任务；旧epoch事件不能推进新任务。CPU异常恢复的正确上下文不等于GPU输出正确，IRQ也不等于某任务成功。

建议三：将任务终态、通知和对象复用分层；重复或缺失通知可以查询/恢复，ERROR/CANCEL不能冒充SUCCESS。回收还需真实DMA静默、映射撤销/失效和必要清理；仅恢复CPU GPT、增加epoch或正常执行ERESUME都不能证明设备已停止访问。

验证负例应包含：非法操作/保留槽、越界物理页、GPT/对象容量耗尽、部分映射失败、多核退出与撤销交错、异常嵌套、旧上下文复用、同Client两个任务使用相同本地标识、跨Client同cookie，以及reset后迟到完成。分别观察拒绝越权、失败原子性、合法任务可完成和未静默前不复用。以上均为后续计划，本批未执行。

## 15. 后续文献和统一记录

参考文献新增发现FlexClave: An Extensible and Secure Trusted Execution Environment Framework；Crossref核对为IEEE Transactions on Computers，DOI `10.1109/TC.2026.3654947`。当前只取得书目，未读全文，不计完成。TwinShield与PKUS再次以完整题名命中，但均已在库内完成，按arXiv标识去重，不作为新研究成果。

统一记录：CCX完整17页v1、§I–X/97引用/附录、10页图表及固定原型定向静态阅读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无构建、模型、QEMU、攻击或硬件run-id；Notion回读后登记，来源及未核验边界保留｜继续研究直接GPU/CCA全文及相邻机制。
