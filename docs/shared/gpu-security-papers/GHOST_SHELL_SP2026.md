# GHost / SHELL：统一地址空间中的GPU到Host访问边界

研读日期：2026-10-28。完整阅读作者16页PDF、§1–10、48条参考文献与Appendix A；核对11图4表，视觉阅读12页。固定作者artifact commit并取得16个验证blob，分别完整或定向静态阅读；定向核对Linux HMM失效同步文档，独立复算四组表内数据。未执行作者安装脚本、攻击、编译或模拟；未改运行代码，无新增性能测量。

## 1. 文献信息与来源强度

Sihyun Roh、Woohyuk Choi、Jaeyoung Chung、Yoochan Lee、Suhwan Song、Byoungyoung Lee，GHost in the Shell: A GPU-to-Host Memory Attack and its Mitigation，IEEE S&P 2026，456–471，DOI [10.1109/SP63933.2026.00047](https://doi.org/10.1109/SP63933.2026.00047)。六作者均署Seoul National University；Crossref发布日期2026-05-18，机构库与作者出版页匹配会议及题名。

[作者出版页](https://compsec.snu.ac.kr/publications)明确链接[16页PDF](https://compsec.snu.ac.kr/papers/ghostintheshell.pdf)及[代码仓库](https://github.com/compsec-snu/ghost-in-the-shell)。PDF为534184字节，SHA256 `9f09aee425f9fb738c8ff0852f70bb85cf74a99ffacd88e2a2c78b207587c84f`；含最后一页会议Meta-Review。未取得出版方PDF作逐字比较，不能用作者文件替代出版方字节一致性证明。

此前检索使用旧publications.html及错误main分支，不能据失败断言全文/代码不存在。本轮从可访问根页转到/publications，确认默认分支master并固定`e0412643c0b8861f77c8e3ae91e6c3084399f6f8`。README仍写submitted/TO BE APPEAR，正式出版身份采用已核出版元数据，不将README历史措辞当论文尚未发表。

证据位于build/cca-gpu-followup-20261027/的ghost126、acquisition126及相关文件；保留获取失败。全文提取、16页渲染和各项hash是来源证据，不是实验复现。论文、攻击GHOST-ATTACK与防御SHELL为同一篇报告，不拆为三项独立成果。

## 2. 核心问题：共享地址不应意味着共享全部权限

HMM使GPU能用普通CPU指针访问malloc/new、栈或文件映射等数据，减少显式cudaMalloc/cudaMemcpy。问题是：若驱动把“CPU进程可访问”直接解释为“该GPU kernel也可访问”，不可信GPU程序便可能读取CPU私有运行时元数据，或者改写CPU控制流数据。

它研究同一用户进程内GPU与CPU之间的权限边界。这里的Host首先指CPU侧应用进程，不等同本项目的非可信Host虚拟化管理层；突破该进程不自动等于突破CCA Realm、RMM、内核或任意其他VM。可信CPU程序、编译器与驱动负责SHELL策略，论文没有把它们移出TCB。

对本项目的直接启示是：Client对某段内存拥有CPU权限，不代表GPU应自动得到同等权限；ProxyRealm能够读取自己的CPU私有数据，也不意味着其GPUVM应映射这些数据。RMM身份、实际HPA归属与任务设备访问集必须分别落实，不能靠统一VA或按需缺页建立隐含信任。

## 3. 传统显式内存、Managed Memory与HMM

论文区分传统GPU专用分配及显式复制、cudaMallocManaged式共享，以及普通CPU分配也可被GPU使用的HMM。其列出的CUDA12.2+、开源驱动r535+和若干Linux版本，是论文引用的支持条件，不应改写成任意NVIDIA设备/驱动均默认暴露全部CPU物理内存。

HMM是Linux的共享地址空间、迁移与同步框架，不是一条天然绕过IOMMU或CCA的指令。具体设备如何建图、哪些CPU区域可迁移、VMA权限及失效如何执行，取决于平台与驱动。本文实验针对NVIDIA迁移路径；AMD、集成GPU shader以及其他HMM实现的攻击适用性仍需另证。

论文用“UVM”特指cudaMallocManaged的显式共享方式，但开源驱动的nvidia-uvm模块同样承载HMM。模块名叫uvm不能证明HMM未开启，禁用HMM也不能自动证明剩余所有映射、生命周期和共享对象安全。

## 4. 攻击模型与攻击链的可推广边界

两类入口是GPU kernel有内存安全错误，或CPU应用允许执行不可信GPU kernel。作者先取得GPU侧读写/执行能力，再利用过度开放的HMM访问CPU运行时和控制数据。CPU应用本身初始可信，攻击不要求先控制CPU内核或设备固件。

论文的攻击链为：GPU可访问CPU私有区域→利用CUDA运行时泄露布局→定位可写控制数据→GPU改写后由CPU消费。这说明随机化不等于访问授权。报告仅讨论机制与防御边界，不提供运行攻击步骤；本轮也未执行PoC。

§3.1依赖特定运行时的固定映射、内部指针及布局数据；不同版本和不同链接方式不能直接沿用。Fig3的固定地址与Fig4/正文存在一个十六进制零的差别；正文在libcuda-rt与libcuda命名间也不总一致。应以实际版本和代码确认目标，不把图中常量当跨版本ABI。

返回地址与GOT是作者演示的两个CPU控制目标。GOT可写依赖partial RELRO等条件，完整RELRO/CPU控制流保护会改变具体利用路径；它们仍不能代替GPU对CPU私有数据的访问限制。进一步获得内核权限或读取其他租户数据，还需相应漏洞、进程共驻与权限条件，不能作为已完成的跨VM突破。

## 5. 真实应用演示：必须保留改造条件

§6实验平台为Ubuntu22.04、Linux6.8.0、i7-14700K、RTX4060、开源NVIDIA驱动570、CUDA12.8、Python3.12及Chrome138.0.7191。README另列A30测试，不据README补成正文完整双平台性能矩阵。

PyTorch演示嵌入了作者编写的漏洞kernel，模拟已知GPU溢出类型；不是拿未经改动的发布版PyTorch证明存在同一个新增漏洞。固定artifact的PyTorch-v2补丁新增native/vuln_op及对应注册，明确向16B局部缓冲区复制24B；这也不同于Fig11按外部len循环的简化图。二者支持“有GPU内存错误后的跨CPU边界后果”，不独立证明任意输入可破坏原版算子。

Chrome原生WebGPU不提供本文所需的CUDA kernel入口。作者修改GPU进程，把CUDA攻击库接到WebGPU路径中，模拟未来/扩展API。所读chrome.patch在RequestAdapterImpl中调用CudaHook，并提前return；不能称为原版WebGPU shader直接穿透浏览器，也不能据此声称标准WebGPU完整渲染行为保持。

SHELL的Chrome防御同样针对专用GPU启动模块；论文明确完整集成仍为开放问题。“所有变体被阻断”是其已构造的两类场景，不是覆盖全部现有/未来GPU接口的证明。作者报告CPU控制流劫持成功，本轮没有独立攻击成功率、稳定性或端到端复现结果。

## 6. SHELL设计：编译识别共享数据，驱动执行授权

SHELL将数据分为Host-only、GPU-only和Shared。可信编译器从Host代码的GPU提交参数追踪分配来源，将需要共享的数据放入专用区域；运行时把区域登记给驱动。GPU发生需要HMM服务的缺页时，驱动先查SHELL白名单，再决定是否允许创建/迁移和映射。

§4.2说按kernel维护whitelist，§5.2与实际driver patch则是按进程/CPU地址空间相关身份维护。不能把文字中的per-kernel升级为已经实现独立每job访问集。若同进程有互不信任kernel A/B，进程共享池的并集可能对二者都可见，不能等同项目不同Client、GPUVM或任务间的精确授权。

论文主要把cudaLaunchKernel参数当共享地址入口，源码则识别device_stub并反向找指针来源。指针嵌套、device globals、Driver API、图提交、JIT、闭源CPU库和复杂间接调用，需要分别建立覆盖条件；未识别合法来源可能导致拒绝执行，过宽来源则可能扩大共享。不能由一个启动API推导全部CUDA用法都兼容。

## 7. 64KiB隔离：防共享与私有混放，不等于逐对象边界

作者发现其路径按64KiB处理GPU fault/迁移；仅检查fault地址时，Host-only与Shared同处一个授权单元会产生暴露。因此全局共享数据进入独立section，堆使用jemalloc共享arena，原共享栈对象改为堆分配，确保共享与Host-only隔开。

这属于按安全类别分配，不是给每个对象单独64KiB，也不是GPUShield式逐访问bounds检查。共享池内A越界到B、同一对象内敏感字段、只读/只写任务权限和temporal safety，并没有由“专用arena”自动解决。不同Client更不能复用同一个无身份区分的共享权限池。

64KiB是本文实现条件：一个64KiB单元可含16个4KiB CPU页；项目须按实际GPU映射、SMMU和可能的合并/预取粒度检查完整覆盖。不能因为请求的第一个CPU页被授权，就把更大块中的其余实际HPA也作为合法副作用范围。

## 8. 固定artifact的静态核查范围

作者仓库完整递归树299项、未截断，包含7个子模块声明及额外第三方状态文件；不是299个文件都通过审计。选取16个blob，逐个核Git blob SHA1、SHA256与固定树一致。未下载大型数据分块，也没有同步、构建或运行上游子模块。

完整阅读README、apply-mitigation.sh、libshell.c/h、driver mitigation/baseline补丁、chrome.patch、两份平均脚本、Makefile和.gitmodules。LLVM19-v4完整静态读；LLVM17-v4只读BackendUtil接入和CodeGen主pass约1–430行，其后重复/备用Custom段未完整审计。init.sh仅定向读固定版本、补丁选择与构建段，PyTorch-v2仅定向读新增算子/漏洞kernel，weather_app-SHELL仅读main及清理/计时段。

init.sh确实选择LLVM17和LLVM19的两个v4补丁，driver基底为`8ec351aeb96a93a4bb69ccc12a542bf8a8df2b6f`，PyTorch基底为`1eba9b3aa3c43f86f4a2c807ac8e12c4a7767340`；端到端Makefile使用修改后的LLVM17、-O0、sm_89、CUDA12.8及libshell/jemalloc。因此LLVM19里的旧ioctl2048/2049路径不能混为实际端到端LLVM17+libshell2050/2051协议，更不能凭两文件不同就断言报告配置不能运行。

LLVM17主pass将识别到的malloc替换为instru_malloc，mmap加MAP_HMM，共享global设section和65536对齐；stack转为堆，在所见首个ReturnInst前插free后直接return。所读路径未构成全控制流/异常清理及复杂指针来源的证明。LLVM19路径与主pass明显不同，完整兼容性需各构建配置分别验证。

## 9. Driver白名单：身份、容量与生命周期待核

driver patch全局保存64个slot、每slot256个base/end/valid区域；访问检查从mm->owner->pid查表，登记用current->pid。不是RMM认证的原始Client身份，也不是由GPUVM/root或对象generation建立的归属证明。针对恶意Host，不能直接信任登记方传入的CPU虚拟范围。

get_hmm_entry的冲突递归把原pid换成idx+1，而非保留原身份并只推进slot。条件例：pid1000的slot40被pid936占用时，下一次参数为41；后续查找与登记还会重新处理task_struct/pid。这是明确需要复核的静态身份传播问题，不是已实测跨进程攻击。所读新增路径也未看到持有task引用、退出清表、锁和多线程pid/tgid一致性协议；完整上游上下文未审计，不据此给出无条件可利用结论。

表满时set函数可走到循环末仍返回NV_OK；新登记区域是否真正插入需要显式失败语义。删除允许条目也不等同已经取消GPU页表中的旧映射：只在新缺页时检查，无法自动撤销已驻留、无缺页的访问。普通munmap可能触发上游HMM失效，但额外策略撤销、pool内部free/复用及并发更新仍须单独论证。

驱动条目仅base/end，未增加Client、任务、读写权限、对象代际及device epoch。已有VMA权限检查可能继续约束访问，但不能把上游CPU权限当成更窄的任务权限。SHELL在可信CPU进程模型下允许用户态登记，不能据此证明不可信Client自报的区域都合法。

## 10. libshell范围处理与细粒度证明的缺口

libshell的mmap先执行原SYS_mmap，再把返回地址向下64KiB对齐、length向上64KiB对齐后登记；所读wrapper本身没有先保留空间再强制64KiB对齐映射。独立条件算例：ret=0x11000、length=0x10000时，原映射为[0x11000,0x21000)，登记为[0x10000,0x20000)。前方多登记4KiB、尾部漏4KiB，说明“分配已隔离”必须有额外前提。

这只是允许4KiB而非64KiB对齐返回时的静态范围反例，未证明作者实际数据集恰好落入该布局，也不是已复现泄露。正确保护必须同时证明真实分配覆盖、页内安全类别、范围取整、失败处理及撤销一致；只改白名单数字不足以阻止同块Host-only暴露。

instru_free使用指针高32bit与arena0_msb比较来选择分配器，不是逐分配来源跟踪；init_arena还登记p到p+4MiB，extent hook登记整段extent。共享arena及同高位假设、部分映射失败、ioctl返回与线程并发需另核。其安全粒度是共享池/extent，不能宣称每次malloc和每job都有精确授权生命周期。

libshell的用户参数只含begin/end，而driver UVM_SET_HMM_PARAMS还含rmStatus，二者需要核ABI与上游路由的copy-in/out行为。当前仅确认所见定义不相同，未取得完整基底宏实现，不把差异直接宣称为可利用内核漏洞。

## 11. 论文性能与独立复算

作者称每项重复100次取平均；没有本轮可核的100次原始日志、方差和置信区间。端到端只选NVIDIA HMM示例ERA5，并以jemalloc版本为基线，不是广泛LLM/浏览器/多租户工作负载验证，也不应把allocator改变的收益单独归于访问授权。

| 指标 | 原文值 | 用表内数字复算及边界 |
| --- | --- | --- |
| ERA5端到端 | 3.1088s→3.1398s，称0.9%、100.9% | +0.031s，约+0.9972%；常规一位小数约1.0%/101.0%，保留印刷数字与声称不一致 |
| mmap与登记 | Table3为5.512µs→6.106µs，称10.7% | +0.594µs，约10.7765%；正文另写6.104µs，对应10.7402%，二者不拼成统一精确值 |
| fault处理 | 97.02µs→108.75µs，称12.1% | +11.73µs，约12.0903%，与一位小数一致；实际代码测service_fault_batch，非必然单页单fault成本 |
| 分配次数 | mmap3次、malloc1440次 | 合计1443，约0.2079%/99.7921%；低mmap比例解释部分端到端摊薄，不说明大工作负载都如此 |
| GPU内存 | 两侧nvidia-smi均5824MiB | 不能由GPU分配总量推导Host共享arena、虚拟保留、峰值驻留或所有输入均无额外碎片 |

两个driver补丁都在service_fault_batch周围测时并pr_info；需要区分batch大小、迁移量及日志扰动。Makefile使用-O0，不能将约1%的端到端结果直接外推优化编译、生产LLM、多GPU或本项目720p glmark。论文未给这些配置的结果。

## 12. 性能artifact的计时与结果判据

两份avg脚本切换不同driver，然后运行程序并解析内部Total time；不是直接解析论文所述perf的进程总elapsed。程序内部从main开始测，到清理末尾结束，不含进入main前动态加载/构造等。两种边界可能接近，但不是已证明相同的测量口径。

脚本用“命令失败也继续”的方式捕获输出，再按能否解析时间计成功，未独立保存和检查子进程退出码。即使能解析时间，也不能单独证明计算正确、防护启用或资源恢复。未来复现必须把执行失败与解析失败区分，保留实际结果及被测代码/driver身份。

所读weather main固定months_per_year=2、days_per_leap_year=60，而脚本参数为2025到2025；这不是全年ERA5或广泛年份处理测试。1440次分配恰好对应60×24循环。清理用k<argc而不是file_sizes.size()：通常argc=4、文件向量2项时会访问第三项。这是固定源码中的条件越界，不据此断言作者100次原始实验都失败或原文性能必然造假。

主程序未提供独立数值reference验证；基准源段还保留示例/替代计算流程。完整数据内容、最终二进制、编译日志及100次原始输出未核，不将artifact可下载写成已复现有效性能。研究结论限定为论文报告和本轮静态证据。

## 13. 与PORTAL、CAGE、ACAI及既有保护的关系

PORTAL/CAGE/ACAI的重点是可信GPU服务、执行与设备/内存归属；GHost强调CPU可见空间不能自动成为GPU授权集合，SHELL提供一类可信编译+fault-time白名单方案。它不能替代CCA身份、实际HPA授权、SMMU保护与固件信任；反过来，Client页归属也不自动证明所有CPU私有页都应交给其GPU程序。

GPUShield、cuCatch与SHELL分属对象越界检测/保护、程序调试与CPU/GPU访问域隔离，不应仅按名称比较谁覆盖全部。SHELL允许某个共享池后，不自动限制池内每个对象；对象bounds正确，也不自动证明该对象属于原始Client或未被撤销。

论文及Meta-Review的“first GPU-to-host”应限定为本文特定HMM用户kernel模型；库内更早Understanding the Security of Discrete GPUs讨论过受控驱动/固件条件下的CPU内存风险。历史设备DMA攻击与本文低权限用户kernel切入不同，不用广义首次口号抹去前作，也不据前作否定本论文HMM分析的增量。

## 14. 对本项目的设计建议：授权实际访问集

继续采用用户给定假设：RMM认证原始Client，可信ProxyRealm统一控制SMMU；GPU在建图时完成受检IPA→HPA软件翻译，合成为受保护直接HPA Stage-1；其他设备受检Stage-2；真实页表、root、MMIO和可信固件加载受保护。硬件作为模拟验证载体，不以RK是否支持NVIDIA HMM否定这些原则。

把授权集合区分为Client拥有的CPU页、该GPUVM可访问的页、本次任务有权使用的对象和Proxy自身私有控制页。至少保护Proxy的private plan/snapshot、真实fence状态、cookie/epoch映射、授权元数据和可信通知记录，避免被无差别GPU映射。是否需要同Client逐任务精确访问集，应作为额外安全目标说明，不把现有Client隔离虚构成已经保证全部子对象保护。

若未来引入按需建图/缺页，fault携带的VA/上下文只作为查找线索，必须重新关联RMM认证Client及真实GPUVM、对象/backing generation、权限和device epoch。必须阻断“因CPU页存在而自动放行”、合并页扩大权限、旧授权表复用与授权失效后继续使用缓存映射。

编译分析结果可辅助发现共享需求或性能优化，但不能作为恶意Host/Client可以任意修改的最终授权。若编译器要成为可信准入者，需绑定受验证binary、metadata和提交身份；若仍允许任意shader，就依靠受保护实际映射持续限制访问，不允许自报免检或自行扩大范围。

## 15. 中断、缺页与安全交接

GPU fault通知只说明有待服务事件，既不是合法共享请求，也不是任务完成。可信Proxy应根据实际设备状态、上下文及授权记录决定允许、拒绝或终止；设备错误须进入所属任务的可信终态，不能把通知已ACK或native fence到达一概解释为应用成功。

完成链继续区分通知、native fence任务终态、输出可见、应用正确、输出发布、DMA静默和安全复用。删除白名单、递增device epoch或让Client看到失败，只能解决其中部分性质；在途访问、已驻留映射、TLB/缓存、fault重放和迟到事件仍需可信停止/失效依据。

定向阅读[Linux HMM文档](https://docs.kernel.org/mm/hmm.html)的地址空间镜像/失效段：invalidate回调须在返回前完成设备侧更新，并处理建图与失效竞争。这是当前文档快照的通用同步要求，不是本轮审计了整份规范或证明作者NVIDIA基底全部调用正确；其余HMM API和版本演化不在本次范围内。

## 16. 优先补充的负例与研究定位

可先构造四类设计级负例：Client合法CPU页但未授权给GPU；GPU授权块混入Proxy私有实际页；撤销后命中旧GPU映射而不再fault；不同Client/任务使用相同VA、cookie或复用对象地址。分别观察实际受害页是否改变、可信任务是否报错、另一Client是否受影响，以及是否提前回收；本轮未执行。

若进一步研究细粒度保护，再检查共享arena内对象A→B、嵌套指针、复杂分配来源、跨线程登记、slot冲突、白名单容量满与部分解除映射。拒绝攻击并不要求所有不支持程序都能继续运行，但SETUP_FAIL必须与真实策略拒绝区分，不能通过测试未建立有效映射来制造安全PASS。

本篇对项目第二部分“GPU任务内存隔离与可信完成通信”有直接帮助：统一地址空间只是编程接口，真正要证明的是GPU真实访问、授权元数据、异常终态和资源交接的一致性。该方向与PORTAL/CAGE/ACAI的组合是否构成新贡献，仍须逐项对照，不能凭本篇报告宣布创新。

统一记录：16页全文/48引用/11图4表/Appendix A/12页视觉/16blob有限静态/HMM定向核对/自写算术/Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码/攻击/模拟/编译/硬件run-id｜保留研究，整体继续。
