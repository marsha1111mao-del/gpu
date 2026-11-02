# GPU Security Papers：逐篇精读与扩展计划

**本轮已按用户要求收尾（2026-10-28）。** [收尾文档](RESEARCH_CLOSEOUT_20261028.md) / [Notion](https://app.notion.com/p/407659a3b8cc8128bf63ca63ae9c2245)。停止全部剩余待办，覆盖下方历史active与后续计划；未完成项不计为精读完成。最终原库53/63、扩展154份、合计207份，含版本/支撑/资料。未改运行代码，无新增性能测量。

第134批加速收敛：[剩余核心论文与新交付标准](FAST_TRACK_SCOPE_20261028.md)，[Notion](https://app.notion.com/p/407659a3b8cc819384c3e6d840833b98)。按用户要求停止开放式扩展，将27项待办收敛为10项核心，17项移出本轮必做范围；本条覆盖下方历史扩展计划。省略默认全页截图及外围代码追踪，保留全文关键机制/评估核对与独立报告正文回读。此专题不计独立论文精读，扩展154、合计207及原库53/63不变。

10项：XpuTEE、GR-T、LGT4CG、HSMEM、RS-Infer、ZeroKernel、SEGIVE、GINN、AccShield、SCALE。SCALE新取得作者SCALE-tuner明确关联README与固定完整树，未取得论文全文，不以建模artifact替代原文。未改运行代码，无新增性能测量；10篇核心尚未完成，goal维持active。

第132批新增：[CounterSEVeillance](COUNTERSEVEILLANCE_NDSS2025.md)，NDSS2025正式全文与作者版16页、105引用、6图4Listing、全16页视觉；DOI10.14722/ndss.2025.241038及四作者核对，两版提取文本仅会议日期空格不同。[Notion独立报告](https://app.notion.com/p/407659a3b8cc811085d3cb4d3cc3e6d7)48条非空正文完整回读PASS；续研172/172，扩展154、合计207，含支撑/版本/资料，非207套CCA GPU架构。

CPU机密VM中断控制与PMU泄漏支撑，不是GPU/CCA实现。335事件集合独立复算，图1未展示9个VM独有事件及正文“6事件/5名称”口径保留。RSA window1的10/10、TOTP50/50、长期key74/86与HQC398/400 oracle分别记录；HQC不是本文端到端密钥恢复实测，RSA428.9秒是记录时间。AMD-SB-3013核对，历史fully patched不推广到2026所有平台。

未取得匹配作者artifact/trace，不称源码审计或攻击复现；已有SEV-Step不能替代本文完整实现。项目保留RMM/HPA/native fence/cookie/epoch/可信IRQ，补通知归属与语义、干扰和统计暴露的分离。XpuTEE正式PDF仍403，LGT4CG只有匹配OA索引而无全文，不计完成。统一记录：全文/视觉/正式书目/双版文本比对/AMD公告/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码、攻击、模拟、构建或硬件run-id｜整体active。

第131批新增：[TEEcorrelate](TEECORRELATE_USENIX2025.md)，作者USENIX Security2025全文18页、82引用、11图4表1算法、全18页视觉；作者页核对八作者/Seattle/Aug13–15，正式出版页/PDF超时，artifact概念DOI与论文标识分开。[Notion独立报告](https://app.notion.com/p/407659a3b8cc818cbcb6cbef7d868b67)61条非空正文回读PASS；续研171/171，扩展153、合计206，含支撑/版本/资料，非206套CCA GPU架构。

CPU机密VM的PMU信息泄漏防御支撑，不是GPU/CCA实现。按实际进度聚合、Host注入时扩展窗口、数值去相关与证明绑定配置；不覆盖cross-core计数器或任意大事件差，低开销为假设硬件估算。十组样本数独立算术上整吻合；PDF负方差符号、离散CDF、算法字面边界/均值与HQC量纲/尾概率待查，摘要/引言/正文不同数字保留，不宣称已确认实现漏洞。

Zenodo403及版本网络失败，DataCite核对八作者和三版本，未获作者代码/trace，不称复现。项目建议列明PMU/overflow IRQ/profiling/队列/时间戳出口，精确可信内部状态与受限外部统计分别管理；保留RMM/HPA/native fence/cookie/epoch/可信IRQ及DMA静默判据。GR-T/XpuTEE/HSMEM/ZeroKernel正式全文仍待查。统一记录：全文/视觉/元数据/独立算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/模拟/形式工具/攻击/构建/硬件run-id｜整体active。

第130批新增：[OctopOS / split-trust](OCTOPOS_MOBISYS2023.md)，MobiSys2023作者14页全文、123引用、3图5表及验证示例、全14页视觉；正式DOI10.1145/3581791.3596864、五作者、233–246及June18元数据核对。[Notion独立报告](https://app.notion.com/p/407659a3b8cc816c9c49dd7e41b65c11)62条非空正文回读PASS；续研170/170，扩展152、合计205，含支撑/版本/资料，非205套CCA GPU架构。

可信I/O支撑研究，不是GPU/CCA实现。区分strong/weak trust、会话与未来可用性；硬件mailbox owner/quota验证、reset guard及domain-bound DMA不能直接替代共享GPU的任务身份和撤销静默证明。网络TEE0.567Mbit/s不同于普通域943Mbit/s；DRAM存储上界、TPM模拟、TLS/存储crypto未实现等限制保留。

两份当前README及AE固定路径硬件README、socket client有限静态读，未获完整树/Git对象、RTL/harness/runtime实现；32B缓冲区配512读取上限按条件记录，非确认漏洞。建议保留RMM身份/实际HPA/private plan/native fence/cookie/epoch/可信IRQ，以可信lease、交接状态机和quarantine连接授权与安全回收。GR-T/XpuTEE仍缺正式全文。统一记录：全文/视觉/有限静态/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/形式工具/模拟/攻击/构建/硬件run-id｜整体active。

第129批新增：[Hora](HORA_APSYS2024.md)，APSys2024作者七页全文、19引用、2图1表、全七页视觉；正式DOI10.1145/3678015.3680486、五作者、115–121及Sep4元数据核对，ACM403未比对字节。[Notion独立报告](https://app.notion.com/p/407659a3b8cc813a9b92e353564656c0)65条非空正文回读PASS；续研169/169，扩展151、合计204，含支撑/版本/资料，非204套CCA GPU架构。

TEE CPU/I/O周期可用性支撑研究，不是CCA GPU实现。明确Table1仅定理1/2/4已证明，3的真实时间调用和5的镜像可用性尚未完成，硬件交互使用stub。OwnedSlots无Copy/Clone不能单独证明构造器唯一mint；首次执行NUM_SLOTS调用与既有临时租约两周期等待需区分起点，不称已证实实现漏洞。作者artifact未取得，无源码/证明执行。

项目保留RMM身份/实际HPA/private plan/native fence/cookie/epoch/可信IRQ，区分通知认证与有界服务；可选可信窗口需联合CPU/GPU/页/镜像准入与撤销静默，时间到期不能制造任务成功或安全回收。GR-T/XpuTEE新作者入口仍未获全文。统一记录：全文/全图表/正式书目/Kani文档定向/有限发现/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/Kani/模拟/攻击/硬件run-id｜整体active。

第128批新增：[GPU-Fuzz](GPU_FUZZ_DAC2026.md)，作者DAC2026七页全文、26引用、9图4表、七页完整视觉核对；PDF标注DOI/July与主页June差别、Crossref404/ACM403保留，不称正式书目已核。[Notion独立报告](https://app.notion.com/p/407659a3b8cc81b1bbc4d6dc84b980d2)68条非空正文回读PASS；续研168/168，扩展150、合计203，含支撑/版本/资料，非203套CCA GPU架构。

算子参数fuzzing补充项目隔离验证，区分13个新问题、7项内存访问违规、5项静默破坏和比较实验26±5的finding口径；2.72045倍case数量不是安全架构提分。作者artifact未确认；PyTorch固定v2.3.1提交63d5e9221bedd1546b7d364b5ce4171547db12a9三个上游blob有限静态核查，发现64位总数/32位设备可见index的条件路径，图9block算术支持继续查因，不称CUDA复现。

项目保留实际HPA授权、private plan/native fence/cookie/epoch/可信IRQ链，加入独立受害者哨兵与任务错误/恢复判据；正常API返回或IRQ不证明无静默错误。CUSAFE/Let-Me-In/HSMEM/RS-Infer重新获取仍缺全文，继续待办。统一记录：全文/全图表/有限上游静态/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/模型/攻击/CUDA/构建/硬件run-id｜整体active。

第127批新增：[DMGuard](DMGUARD_USENIX2026.md)，作者标注USENIX Security2026，19页全文、95引用、9图9表、Appendix A.1及12页视觉核对；官方页面/PDF超时、Zenodo API拒绝，artifact DOI不当论文DOI。独立[Notion报告](https://app.notion.com/p/407659a3b8cc8112806ced18f0240b6a)73条非空正文完整回读PASS，续研167/167；扩展149、合计202，含支撑/版本/资料，非202套CCA GPU架构。

固定作者artifact 41980cb5df8651ffd0da904d1756c7f217c7a4f8、112项完整树、10个验证blob有限静态阅读。区分24总案例、15项实证、9项理论与公开10项；ARM认为新dangling PTE问题不可利用的结论保留。论文full barrier与补丁atomic/smp_wmb、CPU随机标签和Mali递减顺序差异按条件记录，不称已验证攻击；未取得LKMM litmus不称完整证明。

核心：实际页多别名与旧引用必须同时检查，pool return也是生命周期边界；TLB残留明确未覆盖。项目保留RMM身份/实际HPA授权/private plan/native fence/cookie/epoch/可信IRQ，映射数归零、任务终态、通知与DMA静默分开；建议可信generation、事务建图及quarantine撤销回收。统一记录：全文/图表/有限静态/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/攻击/模拟/构建/硬件run-id｜整体active。

第126批新增：[GHost / SHELL](GHOST_SHELL_SP2026.md)，S&P2026作者16页全文、48引用、11图4表、Appendix A及12页视觉核对；正式DOI/六作者/日期/456–471页匹配。Notion79条非空正文完整回读PASS，续研166/166；扩展148、合计201，含支撑/版本/资料，非201套CCA GPU架构。

作者新出版页和默认master分支解决旧路径/错误分支获取失败；固定artifact e0412643c0b8861f77c8e3ae91e6c3084399f6f8、299项完整树、16blob验证并有限静态阅读。明确PyTorch为嵌入漏洞kernel，Chrome为新增CUDA入口；不称原版WebGPU已攻破。主端到端LLVM17/libshell路径与LLVM19旧ioctl路径分别分析，不混为同一配置。

核心：CPU可访问不等于GPU获授权；进程共享池不是每job精确访问集，删除白名单不独立撤销驻留映射。记录PID碰撞递归、64KiB范围取整、清理索引和计时退出码等静态问题，保留条件/未执行边界；Table1复算约0.9972%与原称0.9%差别保留。项目实际HPA授权、任务错误/通知/终态/静默交接继续分开。统一记录：全文/图表/有限代码/HMM定向/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/攻击/模拟/编译/硬件run-id｜整体active。

第125批新增：[GPUShield](GPUSHIELD_ISCA2022.md)，ISCA2022作者15页全文、79引用、19图6表、12页视觉核对。Notion73条非空正文完整回读PASS，续研165/165；扩展147、合计200，含支撑/版本/资料，非200套CCA GPU架构。

核心：对象边界检查补充页级保护，可信driver/binary模型不直接覆盖恶意Host/Client。短ID、静态global ID上界与heap合并保留条件分析，不称已确认漏洞；原作者artifact未取得。第三方Vortex固定87888f85a6f4411da8ccda416b8160afd3644a34、1931项树、六blob有限静态核查，所读路径日志检查未守卫真实访存，不能充当原论文的副作用阻断证据。保留实际HPA授权、可信任务错误与DMA静默的区分。

后续候选Let-Me-In（HPCA2025，10.1109/HPCA61900.2025.00122）及GHost in the Shell（S&P2026，10.1109/SP63933.2026.00047）仅核正式元数据，全文未取得，不计完成。统一记录：全文/图表/有限第三方静态/规范定向/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者/第三方执行、攻击或硬件run-id｜整体active。

第124批新增：[GMSBench](GMSBENCH_ARXIV2026.md)，arXiv2609.08871v1，完整5页、10引用、1图2表1Listing、五页视觉核对；明确版与无版本PDF字节一致。Notion66条非空正文回读PASS，续研164/164；扩展146、合计199，含支撑/版本/资料，非199套CCA GPU架构。

149项是程序内存错误测试，不能当跨Realm隔离测试；18/144是memcheck给定配置覆盖，不能泛化为全部GPU漏洞检测率。12成员出版源包逐成员哈希、2个TeX文件完整静态读、32行表格独立复算；实现仓库404、限定搜索零条，未取得149项CUDA实现，不称代码审计或复现。项目借鉴delayed/alias UAF、SETUP_FAIL与独立哨兵判据，保留真实任务终态和DMA静默要求。

直接候选进展：作者页确认RS-Infer为TrustZone/Flex-NPU、HSMEM为CPU-GPU机密内存传输；仍缺全文。CuSafe取得匹配HKUST/Figshare索引但正文受阻，GMSBench的引用不替代其独立研读。统一记录：全文/图表/有限出版源/算术/Notion回读｜glmark未测→未测｜未改运行代码，无新增性能测量｜无作者代码/攻击/硬件run-id｜整体active。

第123批定向更新：[CCA / GPU TEE新候选与任务隔离](CCA_GPU_TARGETED_UPDATE_20261028.md)。新增RS-Infer、HSMEM、CUSAFE三个待查候选，明确机构/作者书目与全文未取得的边界；Demystified与Blueprint去重。专题Notion38条非空正文回读PASS，不计独立精读；扩展145、合计198不变。保留物理IRQ、任务终态与安全交接的区分，未改运行代码，无新增性能测量。

第122批新增：[LÆGIS](LAEGIS_ISCA2026.md)，ISCA2026，17页完整精读、145引用、16图2表1Listing、十三页视觉覆盖；正式DOI/两作者/六月/465–481页核对，IEEE502未比对。Notion72条非空正文回读PASS，续研163/163；新增145、合计198，原库53/63，含支撑/版本/资料，不是198套CCA GPU架构。

直接相关GPU CC UVM预加密与IV Bank：真实H100测量加模拟设计评估，2.22/2.74倍不宣称现成H100部署实测。固定artifact 6af67279ad0ec5a0507b3586ecfead42a1206077，1975项完整树、8个验证blob有限静态阅读；README明确Fig12/13/14/16的专用实现未公开，不称完整复现或协议审计。

安全边界：显式IV存储不自动解决源页改写、部分迁移重复nonce、旧密文重放、ID复用与reset。条件反例/CTR终态只用于协议覆盖问题，不称已确认漏洞；NIST SP800-38D定向核对109bit MAC非标准tag长度。8MiB/1TiB命名空间、位数/单位/性能分母独立算术，2.74含积极预取，对pBaseline约2.25倍。

项目保留RMM身份/实际HPA授权/private plan/native fence/cookie/epoch/可信IRQ链；候选准备与提交授权分开，fault服务/真实完成/发布和静默回收分开。统一记录：全文/图表/有限artifact/标准定向引用/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者代码/模拟/攻击/硬件run-id｜整体active。证据见batch122-final-audit.json。

第121批新增：[Dissecting GPU CC](DISSECT_GPU_CC_ISPASS2025.md)，ISPASS2025，16页完整精读、132引用、14图1表2Listing/Appendix A–G、十二页视觉覆盖；正式DOI/三作者/日期/1–16页核对，IEEE502未比对。Notion66条非空正文回读PASS，续研162/162；新增144、合计197，原库53/63，含支撑/版本/资料，不是197套CCA GPU架构。

直接相关GPU CC性能：TDX+H100，CC-devtools测量不直接宣称生产CC-on等价；启动、排队、迁移、执行分别分析。固定artifact 0e1360ff6a03aeda30c2655b7416ee17fd68a00a，3344项完整树、8个验证blob有限静态阅读；自写标准库从28行KET/256行LLM处理数据复算。188.88倍相对nonCC-nonUVM，同UVM增量约35.66倍；LLM热图5–8倍是backend/量化基线，不是CC开启的加速。

项目借鉴关键路径/冷稳态/同条件比较，保留RMM身份、实际HPA授权、private plan/native fence/cookie/epoch及可信IRQ；减少启动等待不改变真实完成/错误/DMA静默。保留处理数据非原始全链、CDF截尾、图号错位/绝对路径、缺全体置信区间等边界。

新取得ISCA2026 LÆGIS作者17页全文、身份初核，未完成精读不计完成；GR-T/AccShield/LGT4CG等新获取失败保留，不用摘要替代全文。统一记录：全文/图表/有限artifact/处理数据算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者代码/模型/攻击/硬件run-id｜整体active。证据见batch121-final-audit.json。

第120批新增：[Fixed Service Policies](FIXED_SERVICE_MICRO2015.md)，MICRO2015正式DOI/五作者/日期/89–101页核对，作者13页完整精读、48引用、10图1表、九页视觉覆盖；ACM403未比对。Notion57条非空正文回读PASS，续研161/161；新增143、合计196，原库53/63，含支撑/版本/资料，不是196套CCA GPU架构。

核心：固定服务须同时约束结果返回；SLA改变须排空控制器状态。可信OS假设不能直接套不可信Host，实际HPA授权与dummy/预取授权仍必须保留。256/512 bank算术、概览0.74/正文0.73及能耗聚合差异原样记录，不制造精确原始结果。

项目继续区分native fence真实完成、数据可见、可发布、通知与DMA静默/安全复用；优先认证及任务/epoch绑定，时序整形须明确观察面与泄露目标。HPCA2017 Secure Dynamic Memory Scheduling只核元数据，不计完成；后续优先回到CCA/GPU/可信I/O直接相关工作。

统一记录：只读全文/图表/来源/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者模拟器/攻击/硬件run-id｜保留研究、整体active。来源及父页保全见batch120-final-audit.json。

第119批新增：[MLP-Aware Memory Controller](MLP_LEAKAGEFREE_HASP2018.md)，HASP2018正式DOI/四作者/日期核对，作者8页完整精读、19引用、10图2表、八页视觉覆盖；Crossref1–7与PDF8页差异保留，ACM403未比对。Notion58条非空正文全文回读PASS，续研160/160；新增142、合计195，原库53/63，含支撑/版本/资料，不是195套CCA GPU架构。

核心：安全调度仍需控制返回时序，真实完成与外部发布分开；RTA低CPU MLP动机不能直接套GPU。保留起点间隔43而slot到slot可36的条件反例，要求核完整bank/slot约束、不称已攻破实现；modulo/gcd覆盖条件影响多VM活性。14%是相对安全基线提升，最佳0.552仍相对非安全基线；源码/攻击容量/全实现证明未取得。

保留15/21cycle、DDR3/DDR4引用、Crossref页数及舍入性能差异。项目继续用RMM身份/实际HPA授权/private plan/native fence/cookie/epoch/可信IRQ链，固定turn不当真实终态或DMA静默证明。新取得MICRO2015 Fixed Service Policies十三页作者PDF，仅首页初核不计完成。

统一记录：只读全文/全部图表/来源/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者模拟器/攻击/模型/硬件run-id｜保留研究、整体active。来源及父页保全见batch119-final-audit.json。

第118批新增：[HASP2014带宽预留](BANDWIDTH_RESERVATION_HASP2014.md)，正式DOI/七作者/日期/1–5页匹配；完整5页、30引用、3图1表、五页视觉覆盖，双作者PDF字节一致，ACM403未逐字比较。独立页52条非空正文Notion回读PASS，续研159/159；新增141、合计194，原库53/63，包含支撑/版本/资料，不是194套CCA GPU架构。

核心：性能实验S=Q、空闲直接idle，不是提案S小于Q/随机窗口/dummy precharge/完整row-bank保护。信息泄露评估明确未来工作，不将低于1%开销与强非干扰声明拼接。公平配额/固定通知数量不保证时序隐私；同窗口总量异细粒度轨迹自构算例不是实现攻击。IPC与runtime分开，消融非直接相加。

项目保留RMM原始Client/实际HPA授权、native fence/cookie/epoch/可信通知与DMA静默；按需共享和通知批处理需独立定义允许泄露项。已取得同作者HASP2018 An MLP-Aware Leakage-Free Memory Controller八页PDF及正式元数据，仅首页初核、不计完成；HPCA2014基线身份已核、作者猜测路径404不当不存在。

统一记录：只读全文/全部图表/双来源/身份/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者模拟器/攻击/硬件run-id｜保留研究、整体active。来源与父页保全见batch118-final-audit.json。

第117批新增：[Bandwidth Utilization Side-Channel](BANDWIDTH_SIDECHANNEL_ARXIV2021.md)，arXiv2110.07157v1/SPSL2021作者记录；完整5页、23引用、4图3表、五页视觉覆盖。明确v1/无版本/作者arXiv/workshop版PDF字节一致；25成员TeX哈希、有限方法/分类/防护源段静态阅读，不是实现审计。独立页60条非空正文Notion全文回读PASS，续研158/158；新增140、合计193，原库53/63，含支撑/版本/资料，不是193套CCA GPU架构。

核心：数据/地址保护不隐藏活动节奏；250kHz计数器PoC与无特权竞争观察分析分开，完美边界下95.3%条件分类不当端到端恢复率。保留73.9%聚合与执行时长weighted行差异、NA阈值/overall精确率聚合缺项、软件防护1.6×与配置median1.2×不同口径。本篇与SESAME结果重叠，不重复当独立平台证据。

项目分别论证通知真实性/路由/重放与时序隐私；native fence/Client/cookie/epoch及可信通知链保留。可研究通知批处理，但需检视完成页轮询、VM exit/RPC/调度等旁路，保留错误/取消/迟到事件和DMA静默。新取得HASP2014带宽预留论文，仅首页面记录，未完整精读不计完成。

统一记录：全文/全部图表/有限TeX静态阅读/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者代码/模型/训练/攻击/硬件run-id｜研究保留、整体active。来源及父页保全见batch117-final-audit.json。

第116批新增：[SESAME](SESAME_ARXIV2020.md)，arXiv2007.06751v2完整13页、70引用、10图5表、十页视觉核对；明确v2与无版本PDF一致。49成员TeX哈希及有限主入口/编译/实现/评估静态阅读，不是实验实现审计；58条非空正文Notion回读PASS，续研157/157；新增139、合计192，原库53/63，包含支撑/版本/资料，不是192套CCA GPU架构。

核心：依赖队列和执行控制隔离独立于页级访存授权；论文只轮询配置寄存器，未解决跨VM中断认证。项目复用RMM原始Client、private plan/native fence/cookie/epoch/IRQ127，分别证明通知、任务终态、输出发布、DMA静默和安全回收。保留Table3/4攻击条件、摘要/正文性能范围与Table5资源数字冲突；密码仅延迟模拟，MAC/地址隐私未实现；源包注释草稿不视作已实现保证。

统一记录：只读研究/文档同步｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者程序/模型/攻击/构建/硬件run-id｜保留研究、整体active。带宽侧信道明确v1 PDF已取得，未完整精读不计完成。来源/父页保全见batch116-final-audit.json。

第115批新增：[Obsidian](OBSIDIAN_ARXIV2024.md)，arXiv2409.02817v1，作者/明确v1/无版本PDF哈希一致；14页、69引用、8图1表2算法3公式、九页视觉覆盖；94成员TeX源包逐成员hash，定向核主入口/算法/评估，不是实验代码。Notion60条非空正文全文回读PASS，续研156/156；新增138、合计191，原库53/63，含支撑/版本/技术资料，不是191套CCA GPU架构。

核心：整轮固定流量节奏下合法预取与可信片内转发；逐层租户切换时关闭跨层预取改为主动清零，不无条件叠加收益。22.8%/11.2%仅为提前清理体积比例，不能替代任务终态/在途DMA排空/剩余秘密清理/旧epoch撤销。与项目RMM身份、实际HPA授权、private plan/native fence/cookie/epoch配合，通知和清零入队不当完成证明。

保留EDP层和代理目标的反序例子、伪代码初始化/Cost更新缺项、parallel/pipelined叙述、edge解析能耗19%/8.4%冲突。阶段20.5+9.1=29.6等仅为加法；分母不清不当作独立复现。限定Crossref/两GitHub查询无精确结果，不证明无正式版/artifact；未拿通用模拟器上游替代。SESAME13页全文与版本记录新取得但仅初步核对，带宽利用率侧信道仅记录，均待精读不计完成。

统一记录：全文/九页视觉/TeX有限静态阅读/独立算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者代码/LaTeX/构建/模型/攻击/硬件run-id｜研究保留、整体active。来源/父页保全见batch115-final-audit.json。

第114批新增：[SecureLoop](SECURELOOP_MICRO2023.md)，MICRO2023作者15页全文、53引用、附录A.1–A.8、16图2表1算法/四公式、十二页视觉覆盖；正式DOI/四作者/194–208匹配。固定commit c1e4fae457d696cbb844ce0ffbf97576cb7ad4eb、163项完整树、13选取blob长度/GitSHA1/SHA256通过；有限静态阅读，无作者代码执行。Notion60条非空正文全文回读PASS，续研155/155；新增137、合计190，原库53/63，包含支撑/版本/技术资料，不是190套CCA GPU架构。

核心：安全成本从最初loopnest搜索就计入，统一生产/消费认证布局以减少冗余读/rehash；mapping是算子数据流而非SMMU映射。保留客户端/实际HPA授权、可信原生任务终态、撤销/reset后epoch失效及DMA静默，不能把AuthBlock复用推广成永久授权。论文不是跨VM中断认证协议。

独立核对：印刷Eq4的min在u=1下与前文条件600/900不等价；固定源码使用单独余数范围，不称已复现实现错误。14.77→9.86为时延下降33.24%、吞吐增加49.80%；局部微调4.73%与原始基准3.32个百分点分开。README9.83与PDF9.86/运行区间差异、serial335/336配置差异保留；Zenodo拒绝连接未获归档包。Obsidian仍待完整精读/版本核对，不计完成。

统一记录：全文/十二页视觉/固定源码有限静态阅读/独立算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者程序/容器/构建/模型/攻击/硬件run-id｜研究保留、整体active。来源及父页正文/子页保全见batch114-final-audit.json。

第113批新增：[Triton](TRITON_HASP2023.md)，HASP2023作者9页全文、60引用、4图1表1Listing、六页视觉覆盖；正式DOI/四作者核对，Crossref19–28与作者9页差异保留，ACM403未对照。Notion50条非空正文全文回读PASS，续研154/154；新增136、合计189，原库53/63，包含支撑/版本/技术资料，不是189套CCA GPU架构。

核心：不可关闭的Client/HPA/任务终态/回收隔离，与经授权选择的加密/完整性/流量隐藏分开；策略绑定可信plan/epoch。标签传播未形式化覆盖全部动态依赖，公开权重不使私有激活公开；资源清零不证明DMA静默，Triton也未定义跨VM GPU完成认证。保留引言与正文62/64%范围反转、Table1空间总计算单元仅时间模式25%的可比性问题；不同保护组合64→6%不是同安全目标90.625%运行时间收益。

新取得SecureLoop作者15页与Obsidian作者14页全文，待完整精读及版本核对、不计完成。统一记录：只读全文/六页视觉/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者代码/构建/模型/攻击/硬件run-id｜保留研究、整体active。证据与父页保全见batch113-final-audit.json。

第112批新增：[vTZ](VTZ_USENIX2017.md)，USENIX Security2017正式开放17页（含封面、论文541–556），六作者/ISBN/直接PDF核对；§1–11/68引用/4尾注/9图2表/九页视觉覆盖全部图表，官方34页slides取得但字体文本乱码，仅五页视觉补核。限定GitHub仓库检索零结果、猜测机构页404，未获匹配artifact/源码，不拿上游Xen替代。Notion69条非空正文全文回读通过，续研153/153；新增135、合计188，原库53/63，含支撑/版本/技术资料，不是188套CCA GPU架构。

核心：SMM/CFLock/SWS/CIEE把实际映射、异常入口、当前Guest身份和功能代码能力分别约束；CIEE被排除于跨Guest隔离TCB不等于当前Guest服务语义不需信任。trusted vGIC路由不能替代GPU原生任务终态/cookie/epoch；关CPU中断不能终止异步GPU DMA。快照encrypt+hash细节不足以证明防重放/分叉和GPU静默。摘要Xen4.8与§6/slides4.4冲突保留；表2cycle独立复算，不把约3%应用开销套用所有切换或GPU性能。

同轮Hecate恢复精确DOI10.1145/3548606.3560592/三作者/微软研究摘要，SNP-VMPL单nestedVM策略方案，ACM403且未取得全文，不计完成；GR-T作者页仍链早期CODY，不当作正式版；HypSec仅猜测PDF404候选。统一记录：正式全文/九页视觉/五页slides视觉/算术/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码、构建、VM、攻击或硬件run-id｜保留研究，整体active。父页正文/子页保护与来源审计见batch112-final-audit.json。

第111批新增：[VIA](VIA_ACSAC2021.md)，ACSAC2021正式DOI/五作者/273–284页核对，实际精读12页arXivv1，64引用/6图6表/六页视觉覆盖全部图表，显式v1与无版本PDF一致；ACM403未逐字比对正式版。引用仓库API限流403、只读bare clone连接超时退出128，未获固定实现；固定Linux修复仅取得头文件，未冒充完整diff或源码审计。Notion54条非空正文全文回读通过，续研152/152；新增134、合计187，原库53/63，含支撑/版本/技术资料，不是187套CCA GPU架构。

核心：共享buffer授权不认证共享长度/指针/错误状态；IRQ定向注入提升状态可达性，不是来源或GPU完成认证。SEV-ES/Linux5.10.8/KASLR关闭演示与SNP/TDX模型分析分开。表4总和之比与均值倍率、表5极端值/中位数、表6补丁及不稳定目标分别核对，不把2706倍fuzz吞吐当GPU收益。限定复核当前Proxywatch/publish/unwatch、Clientcookie匹配和RMMIRQ127；cookie本身不是MAC，仍需完成页写权限/身份/原生链/错误回滚/迟到回调/DMA静默等联合不变量，不重复创建认证框架。

统一记录：12页全文/六页视觉/来源/独立算术/限定现有路径阅读/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码、fuzzer、攻击、VM或硬件run-id｜保留研究，整体active；Hecate及GR-T/XpuTEE等全文缺项继续待完成。父页正文/子页保护与来源审计见batch111-final-audit.json。

第110批新增：[TwinVisor](TWINVISOR_SOSP2021.md)，SOSP2021精确DOI/作者/638–654页核对，机构托管17页ACM格式全文、86引用、7图5表、8页视觉覆盖全部图表。ACM直连403，未字节比较；宽泛题名返回的无关结果未混用。固定主仓库f4d96b527a29655070bd6dabefa1e3cb1c615c1d及其S-visor gitlink e25e1a826f1c64363c4a3029ed149fedc65eb0c8，14项根树/11gitlink/141文件S-visor完整树、14blob校验/限定静态阅读；API树限流后以bare Git恢复。公开FVP功能原型不是未公开Kirin性能原型，2022提交不称2021精确快照。Notion75条非空正文全文回读通过，续研151/151；新增133、合计186，原库53/63，含支撑/版本/资料，不是186套CCA GPU架构。

重点：H-Trap的检查后进入与项目预先授权合成映射相近，但CPU重入检查不自动覆盖异步GPU DMA；shadow I/O复制/可信转发也不认证Host完成语义。私有快照、真实页归属、权限、撤销失效、实际静默和回收仍是贡献空间。固定功能原型的共享请求/vCPU边界、映射安装与归属检查顺序、MD5部分比较、cache位图移位、回收及shadow descriptor可信性分别记录，未执行攻击或推断未公开部署。性能常规低于5%、混合低于6%、迁移最坏6.84%范围分开；微基准/bitmap/分配摊销独立复算。项目复用RMM原始身份/GPUVM/private snapshot/native fence/cookie/epoch/IRQ127，不因引用新论文增设重复框架。

统一记录：17页全文/8页视觉/14blob核验和限定静态阅读/算术/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者程序、构建、VM、硬件或攻击run-id｜保留研究、整体active；原始实验源码/统计、未审计固件和其余子模块及Hecate/VIA候选继续待完成。父页正文/子页保护与来源审计见batch110-final-audit.json。

第109批新增：[virtCCA](VIRTCCA_ARXIV2026.md)，arXiv2306.11011v3（2026-03-04）完整12页、36引用、5编号图/6表、6页视觉覆盖全部图表；显式v3与无版本PDF字节一致，正式出版身份未独立核实，摘要页/PDF题名及作者差异保留。同题检索所得TDSC2026改造TrustZone论文作者不同，未混作正式版。openEuler相关SDK/Driver固定版本、477/20完整树、4blob校验，3README全文和观测驱动部分路径静态阅读；未取得核心TMM，非精确实验artifact。Notion70条非空正文全文回读通过，续研150/150；新增132、合计185，原库53/63，含支撑/版本/资料，不是185套CCA GPU架构。

核心发现：可信TMM保存/清理上下文并转发vIRQ，不保证事件来源；Host伪中断与恶意设备接口在论文明确排除范围，不能当作本项目中断隔离已被覆盖。CPU受控单级映射提供机制对照，但恶意Guest指令覆盖、设备Secure侧按CVM授权和安全回收仍需独立论证。性能正文/图/图注多处不一致，按绝对值保留独立复算，不引用未核实的29.7%摘要结论来评价项目GPU性能。项目复用RMM原始身份/实际HPA授权/GPUVM/private snapshot/native fence/cookie/epoch/IRQ127，明确通知、任务终态、输出发布、DMA静默和安全复用。

统一记录：全文/6页视觉/4blob校验与限定静态阅读/独立算术/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码、构建、VM、硬件或攻击run-id｜保留研究、整体active；Twinvisor/Hecate/VIA及作者不同的TDSC2026论文为后续候选，未精读不计完成，直接CCA/GPU旧缺全文项继续保留。父页正文/子页保护及来源审计见batch109-final-audit.json。

第108批新增：[Erebor](EREBOR_EUROSYS2025.md)，EuroSys2025正式DOI/1210–1228页核对，作者托管ACM格式20页（含封面）全文、97引用、10图7表1Listing、附录A.1–A.5及12页视觉；ACM直连403，未字节比对。CPU CVM沙箱/中断状态/输出封装支撑，非CCA/GPU原型。固定90cb27645860166e93eb08fef44486ee1e224265（2026-02-06），总递归树截断明确保留，完整根/nk/sva子树及13blob长度/Git SHA1/SHA256核对，4raw超时由API恢复；限定静态阅读无执行。Notion67条非空正文回读通过，续研149/149；新增131、合计184，原库53/63，含支撑/版本/资料，不是184套CCA GPU架构。第104–107批为获取与证据发现，未重复计完成。

重点：设计借中断gate撤临时特权并屏蔽上下文，不能认证GPU完成；完整后向CFI在原型省略、网络输出明文debugfs模拟、时序排除。固定WIP源码的固定encID、syscall放宽、pt_regs纯复制、局部PTE清写权未传回、debugPKRS与回收范围分别记录，不宣称已复现正式部署攻击。只读common不是外部不可篡改证明；8容器36GB→8GB约78%节省，不能套用单沙箱89.1%。项目复用RMM身份、实际HPA授权、private plan/snapshot、native fence/cookie/epoch和IRQ127，结果发布/通知/DMA静默/安全回收分判。统一记录：全文/12页视觉/13blob选读/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者程序、构建、VM、模型、硬件或攻击run-id｜研究active，原库余项和直接CCA/GPU候选继续待完成。

第103批新增：[VeriSMo](VERISMO_OSDI2024.md)，OSDI2024可信CVM模块验证支撑，非直接Arm/GPU架构。作者16页全文、40引用、5图2表13Listing、6页视觉覆盖全部图表；USENIX403，未比对出版方PDF。固定2026-09-18提交6bc6dd326d8b9ca30ffec57a544b13b5fadf3cb3、完整427项树及13blob校验/限定静态阅读，另核对AMD历史页验证修复。Notion53条非空正文全文回读通过，续研148/148；新增130、合计183，原库53/63，含支撑/版本/资料，不是183套CCA GPU架构。第100–102批为发现/原文获取，未重复计完成。

重点：锁不能稳定恶意对端可写共享页；复制后仍须整体校验；GPA历史标签不能认证重新接收的实际SPA/内容，私有页初始化须在授权前且GPU旧访问终止后。restricted中断只限制入口，IRQ提示与native fence完成、结果发布、DMA静默分开。当前代码确认清零再授予权限，不被旧TODO误导；报告去分类assume、external_body、异常stub与未核实nonce/doorbell调用链保留边界。README2026刷新/CI数字不作为本轮验证成功。Erebor仅完成DOI/官方README发现，普通VM功能模拟与TDX模型、明文debugfs演示输出局限待全文核实，不计完成。统一记录：全文/6页视觉/13blob选读/AMD修复/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无作者程序、Verus、构建、硬件或攻击run-id｜整体active。

第99批新增：[Tyche](TYCHE_EUROSP2026.md)，EuroS&P2026元数据核实、arXiv17页v2全文，110引用/12图4表/12页视觉、48成员TeX定向核对。可组合SD/物理区间能力/中断策略/证明支撑，x86/RISC-V实现和CPU LLM案例，不是CCA/GPU直通架构。正式PDF418，未逐字比对。固定公开562424d56799479c0dba7cb5af8c4b8ab7d62d6e（2025-09-19，早于v2），1283项完整树/3gitlink、29blob校验及限定静态阅读。Notion全文非空行回读通过，续研147/147；新增129、合计182，原库53/63，含支撑/版本/资料，不是182套CCA GPU架构。

重点：Deliver/Report/Not report及寄存器可见性应进入可信策略，但不证明GPU完成真实性或时序隐藏；alias/carve/send按实际物理页追踪，hash/clean/vital不替代DMA静默。旧公开代码中的Management转移、禁用VITAL、send部分失败、IOPT权限/统一context/IOTLB TODO、清零RAM准入和旧证明helper/default固定seed分别记录，不归为正式部署已证漏洞。论文CPU LLM约2%、SGX94MB对照、10次取最好9次、Redis配置差异、平均元数据外推边界保留。项目复用RMM身份/实际HPA/GPUVM/private snapshot/native fence/cookie/epoch/IRQ127，撤销前后保留权威状态与实际失效/静默证据。

统一记录：全文/视觉/源包/固定源码选读/独立算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无构建/硬件/模型/作者代码/fuzzer/攻击run-id｜保留研究，整体active；来源与父页原文/子页保护见batch99-final-audit.json。直接CCA/GPU缺全文项与Erebor/VeriSMo等引用链继续待办，未取得和精读前不计完成。

第98批新增：[IOValve](IOVALVE_CCS2025.md)，CCS2025可信DPU网络沙箱，GPU分布式计算的I/O与隐蔽通道支撑，不是CCA GPU直通架构。官方15页全文、142引用、6图1表4算法，9页视觉核对覆盖全部图表/算法；Crossref匹配作者/venue/4454–4468页，未与出版方PDF逐字比对。未取得匹配源码，限定名称查询只返回无关HomeKit项目，不据此断言无代码。Notion全文非空行回读通过，续研146/146；新增128、合计181，原库53/63，含支撑/版本/资料，并非181套CCA GPU架构。

重点区分整机单租户/物理分离DPU与多Client共享Proxy，固定大小/节奏/dummy/ACK/持久连接与单纯加密/可信IRQ；lazy双计数仅为同步，不能替代恶意Client认证/索引校验。拥塞RTT与条件KS近似不证明零通道容量，也未证明成功泄漏；低应用开销不能掩盖高网络/小消息开销。论文排除完整性/可用性，未提供GPU任务完成、中断认证或DMA静默机制。项目继续复用RMM认证、实际HPA授权、private plan/native fence/cookie/epoch/IRQ127，流量隐藏单列可选目标。

Tyche arXiv2507.12364v2摘要核对、全文取得，尚未精读或计完成；旧直接CCA/GPU缺全文项保留。首次pypdf模块缺失后用既有PDFium恢复。统一记录：全文/9页视觉/官方身份核对/独立算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无构建/硬件/模型/作者代码/攻击run-id｜保留研究，整体active；来源与父页原文/子页保护见batch98-final-audit.json。

第97批新增：[MICA](MICA_ARXIV2026.md)，直接Arm CCA/RMM跨Realm内存与控制通道策略、组证明支撑，不是GPU直通或完成中断架构。完整17页v4、72引用/附录A–B、8图2表、13页视觉，HTML与36项TeX源包定向核对。四组件固定提交和完整树23/767/32/51项、27blob长度/Git SHA-1/SHA-256校验及限定静态阅读。Notion全文非空行回读通过，续研145/145；新增127、合计180，原库53/63，包含支撑/版本/技术资料，并非180套CCA GPU架构。论文自述SIGOPS ATC2026，精确DOI Crossref404，正式出版身份未独立核实，不因404否定工作。

核心区分拓扑许可与内容去分类、控制出口与GPU完成真实性、组签名与持续新鲜性。固定公开代码中的显式BLOCK-only SMC、局部owner索引、自报32位标签、选择性清理、并发及组快照边界分别记录，未执行攻击，不扩展为全仓漏洞结论。论文2.5–14.5倍通信延迟比含所选OpenSSL/进程/I/O/PBKDF2成本，不当作所有AEAD不可避免代价。项目保留RMM原始Client认证、实际HPA授权、GPUVM/private plan/native fence/cookie/epoch/IRQ127；组证明、任务完成、发布和DMA静默分别论证。

沿引用链发现IOValve官方论文页及Tyche arXiv候选，未精读前不计完成；GR-T/XpuTEE/FlexClave等缺全文项继续保留。API限流、raw超时与初始PIL渲染失败均保留，渲染改用PDFium恢复。统一记录：全文/视觉/源包/固定源码选读/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无构建/硬件/模型/作者程序/Alloy/攻击运行run-id｜保留研究，整体active；父页保护及来源审计见batch97-final-audit.json。

第96批新增：[AFTUNE](AFTUNE_ARXIV2026.md)，CPU TEE抽查式训练/推理审计支撑，不是CCA GPU设备隔离架构。完整20页v2的HTML、§1–8/附录A–J、11图5表1算法和15页视觉阅读；35项论文源包定向阅读，v1另存未精读不重复计数。固定作者仓库c0b56e93e6836f487a0e1eb2c5ece87a1b48480d，181项完整树、9blob长度/Git SHA-1/SHA-256校验及限定静态阅读。Notion69条非空正文全文回读通过，续研144/144；新增126、合计179，原库53/63，含支撑/版本/资料，不是179套CCA GPU架构。

核心区分承诺不可变与计算正确、偏离轨迹与局部可拒绝块数k；输入定向抽查实际采用全体块预算，脚本136步与2048/batch16=128及floor/ceil/round差异保留。PGD找到的可行扰动不是认证攻击下界；公开默认验证仅输出L2、局部输出比较/本地hash锚和weights_only=False反序列化均记为静态观察，无攻击执行。Zenodo超时、猜测USENIX页面403，正式venue未核实，不凭徽章定会。项目保留实际HPA授权、GPUVM/private snapshot/native fence/cookie/epoch/IRQ127，分别认定设备完成、应用审计、发布和安全回收。

定向CCA新检索25项保存，已知EnclaveX/CCX/CAEC/NANOZONE/CCAegis等去重。新发现MICA《Sharing is caring》，取得arXiv2603.03403当前v4的17页PDF与摘要，首页正式题名变为《Attestable and Trusted Cloud Pipelines out of Distrustful Components》，自述SIGOPS ATC2026/DOI10.1145/3828523.3857024，尚未独立核对正式出版元数据。首两页和控制通道关键词定位显示直接基于Arm CCA/RMM/CAEC，研究内存共享与控制流通道策略及组证明；尚未完整精读或计完成，不能提前据摘要断言中断时序泄漏被解决。后续优先级高于泛化应用审计；旧GR-T/XpuTEE/FlexClave等缺全文项继续保留。

统一记录：全文/视觉/源包/固定artifact选读/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜保留研究，整体active；来源及父页保护审计见batch96-final-audit.json。

第95批新增：[BOLT](BOLT_CCS2025.md)，CCS2025安全HBM/FPGA oblivious map，可信I/O支撑而非CCA GPU共享架构。完整18页arXivv2及HTML、131引用/附录A–C、11图3表1算法和全部claims，12页视觉、48项论文源包定向静态阅读；正式DOI及2594–2608页码核对，不冒充正式15页逐字比对。Zenodo API连接被拒后record页成功，固定作者链接仓库96580b02918a97962c3e771e17781f47d333b2bf，142项完整树、7个blob校验，三raw超时经API恢复；完整读所选sim.cpp/Host.cpp及5README，无HLS源码审计/二进制执行，未下载424MB Zenodo zip或声称逐字匹配。Notion92条非空行回读通过，首次路径通配符被渲染为斜体后移除歧义路径片段再通过；续研143/143，新增125、合计178（含支撑/版本/资料），原库53/63。

重点：单租户/HUM假设不覆盖恶意多Client共享；实验TEE关闭，doubly-oblivious算法与真实端到端配置分开。C.1递推按原值增长而非衰减，C.2非全局超鞅、依赖负载/动态工作负载条件待补；仿真stash简化和最终scan覆盖峰值使经验支持受限，不宣称真实攻击。α=0 stash文字冲突、基线DEBUG/不同N/slowdown分母、命令同步计时排除等保留。项目复用RMM身份/实际HPA授权/native fence/cookie/epoch/IRQ127，自治控制与响应/写回/静默/复用各自论证，访问模式隐藏为可选目标。统一记录：全文/12页视觉/源包/有限源码/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/作者代码/攻击run-id｜整体active。GINN本批OpenAlex仍closed；AFTUNE核对摘要未精读，直接CCA缺全文项继续保留。

第94批新增：[TEE-certified DP](TEE_CERTIFIED_DP_ARXIV2026.md)，CPU TEE概率验证不可信GPU训练预印本，作为任务完成/认证的应用层支撑，非CCA GPU隔离架构。完整30页、49引用和附录A–G（含E.1–E.5），5图9表3算法1定理，16页视觉核对，官方HTML/论文TeX定向静态阅读。未确认匹配运行artifact；限定arXiv编号仓库查询零结果，不宣称作者无代码。Notion70条非空正文回读通过，续研142/142；新增124、合计177，原库53/63，包含支撑/版本/技术资料，不是177套CCA GPU架构。

重点：数据交给不可信GPU，DP不等于训练数据机密性；完整偏离概率检测与稀疏攻击经验结论分开，容差联合接受事件界不是条件/确定/DP保证。校准误中止上界限于轨迹条件，固定数量性能抽样与Bernoulli协议不同，全TEE基线为少步外推、CIFAR按warm-step比较。后台校验全部排空后方可签证书，暂定输出、重试防回滚和不可变快照各有边界。项目保留实际HPA授权/native fence/cookie/epoch/IRQ127，分别判定设备完成、可选应用验证、结果发布与安全回收，不以10%抽查替代基础授权。统一记录：全文/16页视觉/源包/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜研究active。直接CCA缺全文项与BOLT等继续待办；旧批次TEE-certified DP“未精读”是历史状态。

第93批新增：[Hoss](HOSS_ARXIV2026.md)，GPU/CPU TEE语义检索和CORAM预印本。完整16页v1、148引用及附录A/B/C、9图3表1算法4定理，10页视觉核对，HTML/27项论文源包定向阅读；pypdf嵌套XObject限制警告通过独立PDFium/HTML/TeX补核。匿名artifact API410 repository_expired，未获运行源码。Notion62条非空正文回读通过（首次比对发现Notion对x*转义，核对正文相同后补标准Markdown转义归一）；续研141/141，新增123、合计176，原库53/63，含支撑/版本/资料，不是176套CCA GPU架构。

重点区分整卡独占Pmem与恶意多Client共享，按层总访问数相等与batch shape可见的证明缺口，HNSW非均匀逻辑访问与stash上界条件、1/N与生命周期失败概率；K=N/16和8real＋8dummy初始化不一致、理论稀疏碰撞收益与1.8倍消融需分解、5.5%内存占比和TB投影不当作完整峰值/实测。页眉CCS26有占位DOI，按预印本，不宣称正式版；没有实际HNSW查询攻击。项目维持实际HPA授权及native fence/cookie/epoch/IRQ127，访问模式隐藏单独列可选目标。新增BOLT摘要候选，未精读不计完成；TEE-certified DP全文取得待读。新CCA检索两题名为已有CCAegis/Fasco去重。统一记录：全文/10页视觉/源包/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜研究active。

第92批新增：[Blueprint, Bootstrap, and Bridge](BLUEPRINT_BOOTSTRAP_BRIDGE_MLSYS2026.md)，MLSys2026正式版，早期题名NVIDIA GPU Confidential Computing Demystified与本篇去重。完整23页v2、§1–9、62引用及附录、7图2表；正式版逐页文本去空白/水印后相同，12页预印本＋4页正式版视觉核对。固定匹配NVIDIA570.86.15 commit 54d69484da940413ba6017df9cf43bed8b75da46，4192项完整树、11个选取blob长度/GitSHA1/SHA256通过，六项raw超时经API恢复。区分完整读与定向读，未执行代码。Notion75条非空正文回读通过，续研140/140；新增122、合计175，原库53/63，含支撑/版本/技术资料，不是175套CCA GPU架构。

重点：共享明文不等于无认证，RPC私有seq/AAD/tag限制重放；SEC2签名清零命令不等于认证共享完成值，slot复用/整页清零/DMA静默各有条件。六路径暴露表不代表六个成功攻击，驱动内部时间不自动成为Host侧信道；缺最终回收调用者及闭源固件证据，不宣称残留数据攻击。项目保留RMM身份、Proxy实际HPA授权及受保护Stage-1，复用private plan/native fence/cookie/epoch/IRQ127明确权威终态、可恢复通知和安全交接。统一记录：全文/16页视觉/正式版对照/有限厂商源码/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜研究active。Hoss、TEE-certified DP及直接CCA全文缺项继续待办。

第91批新增：[Fastrack](FASTRACK_ARXIV2024.md)，直接GPU TEE可信I/O预印本。完整12页v1、§1–8、29引用、12图2表、10页视觉核对，完整论文源包定向静态阅读，GCM标准相关条款核对；未获匹配运行源码、无代码执行。Notion全文非空行回读通过，续研139/139；新增121、合计174，原库53/63，含版本/支撑资料，不是174套CCA GPU架构。

重点是密文直接转交、分块认证和推测流水的安全条件：DH需认证/Client密钥隔离，GHASH并非数学上不可并行，链序号不自动绑定完整消息，IV唯一性和认证前副作用需独立证明。训练丢弃梯度不涵盖完整状态回滚，推理tentative输出不可事后撤回。性能最大84.6%对自实现baseline，非厂商内部修改收益；表列GraphSAGE推理增加803.88%而非903.9%，训练通信占83.25%而非91.93%，Fig12 CC on/off文字冲突保留。项目复用既有实际HPA授权、private plan/native fence/cookie/epoch/IRQ127明确可信提交、输出发布与回收，不默认增加重复加密或投机完成。统一记录：全文/10页视觉/源包/GCM标准/算术/Notion回读｜glmark未测→未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。Blueprint等候选和原缺全文项继续待办，旧Fastrack“未精读”为历史状态。

第90批新增：[Fasco](FASCO_ARXIV2026.md)，CCA可信System Realm／独立Container Realm与异常服务预印本，作为ProxyRealm/Client的直接支撑，非GPU架构。完整12页v1、§1–8、18引用、8图1表、9页视觉核对、官方HTML及完整论文TeX源包；注释artifact地址HTTP401，未获运行源码。Notion全文非空行回读通过，续研138/138；新增120、合计173，原库53/63，包含版本/支撑资料，不是173套架构。

重点区分页表节点独立与实际HPA独占、上下文保护与事件来源认证；eret/异常EL路由、RTT叶项clone筛选、System Realm的TCB遗漏及共享signal/Iago语义均列待补证据。复核start对Kata减少79.10%但对RunC增加39.76%、kill对Docker慢30.65%，保留图文单位/容器数与线程数差异。项目接受既定软件授权Stage-1与可信平台前提，复用native fence/cookie/epoch/IRQ127完善事件到任务终态与回收的论证。统一记录：全文/源包/图表/算术/Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。第89批Fasco“未精读”是历史状态，本批已完成；Fastrack等仍待完成。

第89批新增：[FAARM](FAARM_ARXIV2025.md)，直接Mali MCU固件认证/安全装载预印本，非完整CCA GPU共享架构。完整10页v1与HTML、§I–VI、28引用、8图5表1算法及内嵌伪代码；10页渲染、8页视觉阅读，七张HTML原图直接读、图3经PDF页核对，八图文件hash通过。Notion59条非空正文回读通过，续研137/137；新增119、合计172，原库53/63，含支撑/版本/资料，不是172套CCA GPU架构。

本批区分Colab合成固件仿真与真实Mali部署，未找到匹配Colab仓库；分析验签快照/实际装载一致、原子写与持续保护、软件重验局限、严格版本递增导致同版本重载冲突、持久counter和恢复事务。表列完整1.56ms而结论1.34ms、TOCTOU定量行缺失、分布图错误指向Fig1、Fig8为示意及引用21–26不匹配均保留。项目在接受可信固件/root/MMIO保护前提下，优先把固件/配置/device epoch与实际HPA授权及native fence/cookie/epoch/IRQ127连贯绑定，不以签名替代任务归属、静默或安全回收。建议不等于运行实现。统一记录：全文/图像/伪代码/Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。

定向发现并登记五篇后续：Fasco（CCA System/Container Realm）、Fastrack（GPU TEE I/O）、Blueprint/Bootstrap/Bridge（GPU CC安全分析）、Hoss（CPU/GPU TEE语义检索）、TEE-certified DP（可信训练检查）。前两篇12页PDF已取得但未精读，不计完成。EnclaveX重复下载与已存hash相同，不新增；猜测XpuTEE PDF404、猜测CSDL路径仅SPA/搜索404不作取得全文。原未获全文的FlexClave/XpuTEE/GR-T等继续待办，不以本批相关预印本替代。

第88批新增：[H100／TDX机密推理基准](H100_TDX_INFERENCE_ARXIV2026.md)，直接GPU机密计算性能预印本，非CCA/GPU TEE隔离架构。完整11页v1、§1–9、9引用、附录A/B、5图4表及8页视觉核对；58条非空正文Notion回读通过，续研136/136；新增118、合计171，原库53/63，含支撑/版本/技术资料，不是171套CCA GPU架构。作者源码/结果artifact尚未确认，两个限定仓库搜索零结果；Google官方配置页网络失败，arXiv标识与来源提交月份异常保留，不据此猜测真伪。

本批明确以CC为分母的吞吐gap与Non-CC基线下降不同，全局实际下降约15.04%/17.46%；Qwen并发32 TTFT约增加624.51%，表称725% higher混淆了比值与增量。固定率秒/闭环毫秒、trial-p50均值、稀疏饱和拐点、Secure Boot关闭和缺证明/底层剖析均分别界定。项目吸收分Client可信任务阶段计时、吞吐/排队/公平性联合评估，不用性能数据替代实际HPA授权、native fence/cookie/epoch/IRQ127或安全回收验证。建议不等于运行实现。统一记录：全文/图表/算术/Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。旧批次H100“待全文”为历史状态，本批已完成。

第87批新增：[CloakLM](CLOAKLM_ARXIV2026.md)，GPU模型权重布局混淆预印本，非CCA/GPU TEE隔离架构。完整15页v1、§1–7、39引用、9图2表及8页视觉核对；NVIDIA VMM正文/规格、TunneLs书目摘要与Hermes会议摘要交叉检查，后两者不计新全文精读。arXiv源码入口HTTP200实际返回相同PDF，无已确认运行artifact；CUDA参考请求超时和ACM403保留。Notion正文全行回读通过，续研135/135；新增117、合计170，原库53/63，含支撑/版本/技术资料，不是170套CCA GPU架构。

可信服务侧OS/driver边界与本项目不同，布局混淆不代替实际HPA授权。运行期backing重排须保留数据并验证DMA静默、映射失效及旧页安全回收；仅交换PTE不自动保持tensor内容。指定重建器失败不证明重建成本高于训练，Hermes实验是软件仿真；初始化拥塞相对图中原生增加约72.77%/40.92%/41.50%，与稳态分别评价。本项目优先绑定backing generation、可信提交快照和native fence/cookie/epoch/IRQ127，不默认引入周期重排或全链路拥塞。统一记录：文献/API/图表及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。第86批中CloakLM“未完成”为当时状态，本批已完成；H100/TDX全文仍待精读。

第86批新增：[Unprivileged Topology Certificates](TOPOLOGY_CERTIFICATES_ARXIV2026.md)，直接GPU测量指纹/证明边界预印本，非CCA/GPU TEE隔离架构。完整12页v1、§1–13、27引用、2图4表、8页视觉阅读；完整arXiv源包取得并定向静态阅读。35个SQLite/LZMA证据文件总76372647字节的长度/哈希独立核对通过；包内清单69/70项匹配，main.bbl缺失、HTTP ETag不匹配及首次下载/断言失败保留。没有执行作者代码、网络探测或GPU。Notion59条非空正文回读通过，续研134/134；新增116、合计169，原库53/63。

本批区分观测一致性、统计判定与可信来源/新鲜性：公开hash不认证当前GPU，指纹与网络hash拼接不自动防中继；验证器缺schema必填、稳定性证书字段不匹配、sourcehash未核验，均为静态观察。358分类样本是两张不同型号卡的SM向量，不是358张独立卡；稳定性load与采样在默认stream串行，未证明恶意并发抗扰。两种相关系数对应不同归约，未错误归为数据矛盾。项目保持可信RMM/Proxy实际HPA授权和native fence/cookie/epoch/IRQ127，建议严格证据schema及会话/设备租约绑定。另取得CloakLM15页和H100/TDX基准11页PDF，未完成全文研读，不计完成；FlexClave作者ORCID仅提供DOI，合作者旧出版页无匹配全文。统一记录：文献/字节完整性与Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。

第85批新增：[The Serialized Bridge](SERIALIZED_BRIDGE_ARXIV2026.md)，直接Blackwell GPU机密计算性能与Fabric部署研究，非Arm CCA隔离架构。完整17页v2、§1–12、19引用、6图及10页视觉核对，HTML/摘要交叉检查；未建立匹配artifact关联，不以2024年Hopper仓库替代。Notion62条非空正文回读通过，续研133/133；新增115、合计168，原库53/63。B300单次与qualified worker结果、Fabric未执行项保留。92%为gold吞吐保留率，原差距恢复约49.5%；34倍加载仅warm窗口，跨平台每阶段5%表述不完全符合表格。FlexClave取得元数据和两个候选固定仓库README，但全文未取得，不计完成。

项目建议保留可信RMM/Proxy实际HPA授权及GPUVM/private snapshot/native fence/cookie/epoch/IRQ127，吸收同Client持久池、批量化、权威终态与安全复用分离、当前控制面配置证明绑定；建议不等于运行实现。统一记录：全文/图表算术及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。

第84批新增：[CCX](CCX_ARXIV2026.md)，直接Arm CCA运行时/SGX源码兼容研究，非GPU TEE架构。完整17页v1、§I–X、97引用、附录、6图8表1listing及10页视觉核对；固定两个作者仓库，根树和服务子树完整，递归全树截断明确保留。9个API blob及4个raw文件校验、可信服务定向静态阅读，未审计完整SDK或性能原型。Notion82条非空正文回读通过，续研132/132；新增114、合计167，原库53/63。新增FlexClave正式书目，未取得全文，不计完成；TwinShield/PKUS按arXiv标识去重。

本批区分无需改应用源码与仍需重编译、局部GPT物理隔离与SGX线性地址/权限语义、可信异常恢复与GPU任务完成；约1%开销排除了两个高开销项目，4462行是新增而非总TCB，远程证明未完成。源码fail-closed分派、EPCM界限、固定容量/回滚、密钥来源和AEX恢复对称性作为静态观察/待核验项，不宣称攻击复现。项目保留可信RMM/Proxy及既有GPUVM/private snapshot/native fence/cookie/epoch/IRQ127。统一记录：文献/静态源码及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/QEMU/模型/攻击run-id｜整体active。

第83批为[CCA / GPU TEE 定向续研专题](CCA_GPU_FOCUSED_CONTINUATION_20261028.md)，非新增论文精读。重新核对 XpuTEE、GR-T 正式版、LGT4CG 和 DICE-anchored Realms 的来源；书目/摘要与未取得全文严格分开，下载和检索失败保留。专题结合已有直接相关全文，提出任务身份、私有快照、权威终态、通知及安全复用的连续协议与负例计划；建议不等于已实现。Notion 专题48条非空正文回读通过，独立精读统计仍为原库53/63、扩展113、合计166，历史131篇续研回读统计不因专题增加。未改运行代码，无新增性能测量，整体研究继续。

第82批新增：[SUD](SUD_ATC2010.md)，USENIX ATC2010可信I/O/恶意驱动支撑研究，非CCA/GPU TEE架构。完整14页、§1–7、36引用，八页图表/关键论证核对；作者明确链接全文与会议版SHA相同。匹配代码未取得，猜测项目404和限定搜索零结果不作全局无源码断言。Notion71条非空正文回读通过后，新增 **113** 篇独立解读，合计 **166** 篇，原库53/63；含支撑/版本/技术资料，不是166套CCA GPU架构。

本批分析共享缓冲TOCTOU、内核权威状态、P2P绕过IOMMU和DMA等价触发MSI，明确测试机缺interrupt remapping仍有活锁缺口，不以部分攻击用例覆盖。吞吐接近不等于无CPU成本，RR占比5%→10%；kill进程不证明DMA静默。项目保留可信Proxy实际HPA/权限/生命周期授权及private plan/native fence/cookie/epoch/IRQ127，提出稳定快照、可恢复通知与安全回收分层验证，建议不等于当前实现。统一记录：全文/来源及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。

第81批新增：[Glider](GLIDER_TR2014.md)，Rice2014技术报告/arXivv1，GPU驱动隔离支撑研究，非CCA/GPU TEE架构。完整13页、§1–8及66引用，九页图表阅读；作者书目/版本核验。同名GitHub固定树仅三项基础文件且无作者关联，未当匹配artifact。Notion71条非空正文回读通过后，新增 **112** 篇独立解读，合计 **165** 篇，原库53/63；含支撑/版本/技术资料，不是165套CCA GPU架构。

本批连接资源管理不可信、隔离可信和可归属中断三项前提，指出当前owner不自动认证迟到IRQ来源、revoke需等待不支持抢占的执行结束，42±5微秒切换不能泛化为任意撤销总延迟。共享内存轮询两项CPU成本增加21.6/29.9百分点；TCB/API数量只是代理指标，Intel仅概念验证且无切换实现。项目建议形成身份/映射generation绑定租约、可信终态与安全复用状态机，保留当前GPUVM/private plan/native fence/cookie/epoch/IRQ127；建议不等于已实现。统一记录：全文/来源及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。

第80批新增：[Viola](VIOLA_MOBISYS2016.md)，MobiSys2016可信通知/形式化I/O支撑研究，非CCA/GPU TEE架构。完整14页、§1–11、58引用及八页图表阅读；固定b31a1bc21895ed320b4171a58775ed82de58a922的20项树/17blob完整性通过，规范/编译器静态阅读、证明假设与最终定理定向核对。Notion62条非空正文回读通过后，新增 **111** 篇独立解读，合计 **164** 篇，原库53/63；含支撑/版本/技术资料，不是164套CCA GPU架构。

本批明确单向持续指示不保证任务归属/完成结果；双向策略编译为skip、Xen原型未降权dom0、部分供电/共享内存/DMA接口未支持均按原文与固定代码界定。源码全称公理范围过强是静态发现，未执行Coq或声称重放证明成功。项目建议分离身份绑定权威终态、可恢复通知和安全复用，保留既有GPUVM/private plan/native fence/cookie/epoch/IRQ127；建议不等于当前基线已实现。TMC扩展版未读，不重复计数。统一记录：全文/检查器静态研究及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜整体active。

第79批新增：[SeCloak](SECLOAK_MOBISYS2018.md)，MobiSys2018可信外设/I/O支撑研究，非GPU TEE架构。完整13页、§1–7、69引用；作者会议版与arXiv正文相同，水印/引用排版差异已核对，八页预印本和两页作者版图像阅读。固定e008daa89b5df3f8b6b00d406336a15aa2fa8c2b完整430项树/383blob含symlink语义校验；关键SMC/仿真/共享GPIO中断静态核查。Notion全文回读通过后，新增 **110** 篇独立解读，合计 **163** 篇，原库53/63；合计含支撑/版本/资料，不是163套CCA GPU架构。

本批把中断可信性扩展到status/mask/ack控制、可信事件状态与受控转发；MMIO访问阻断不等于设备物理关闭或DMA停止，论文明确普通驱动PM失败可使设备继续高功耗活动。framebuffer仅完整性、普通OS可读；重启默认解除策略须明确边界。公开GPIO_PSR过滤注释、GET参数寄存器和失败unlock等作为静态边界，不声称攻击复现。项目维持实际HPA/权限授权及IRQ127/native fence/cookie/epoch，分别验证任务终态与安全复用。Queue原条目新试Queue/CACM入口均拦截，仍未计完成；XpuTEE/AccShield等缺项保留。统一记录：全文/固定源码静态研究及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id｜整体active。

第78批新增：[GPUReplay](GPUREPLAY_ASPLOS2022.md)，ASPLOS2022、作者arXivv4完整14页、§1–9、109引用、八页图像核对。固定accce5d2bcbe5794b895156997f50a6fda86a87c完整429项树/368blob哈希验证，关键重放/等待/验证/IRQ路径静态阅读。Notion全文回读通过后，新增 **109** 篇独立解读，合计 **162** 篇，原库53/63；含支撑/版本/资料，不是162套CCA GPU架构。

论文直接连接小型GPU栈与TrustZone执行，但整卡独占/串行，主要性能来自用户态Mali与内核态v3d。50KB排除录制且不是所有部署总TCB。公开代码的int0.05导致零毫秒poll、循环无总期限、调试验证不匹配仍返回1及不带身份的IRQ计数逐项限定为静态发现，不声称复现攻击。项目优先绑定缓存计划、实际HPA授权及权威任务状态，保留GPUVM/private plan/native fence/cookie/epoch/IRQ127；不能以录制签名或reset替代隔离与安全复用。正式GR-T新试Apple猜测入口为404，作者页面仍指向早期CODY，不计正式全文完成。统一记录：文献/固定源码静态研究及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id｜整体active。

第77批新增：[3LegRace / AsymML](THREE_LEG_RACE_POPETS2022.md)，PoPETs2022正式21页、§1–8、53引用及附录A–E完整阅读，15页图像核对；官方/Crossref核验，未取得匹配代码。Notion全文回读通过后，新增 **108** 篇独立解读，合计 **161** 篇，原库53/63；含支撑/版本/技术资料，不是161套CCA GPU架构。

本批区分不可信GPU上的低秩/带噪残差外包和CCA受保护设备执行。报告给出Theorem2精确输出界的代数反例，同时保留精确截断rank-R输入下常规秩界成立的条件；核对最坏敏感度、完整训练隐私组合、梯度联合发布及攻击实验范围。最高7.6倍针对TEE-only，训练pass仍约慢于GPU-only15–17倍，不与原生或glmark混比。项目优先保持实际页授权、可信任务终态和回收隔离，可另加activation/梯度/KV/日志发布权限；本文不提供跨VM中断认证。GR-T正式版、XpuTEE、AccShield等继续pending，整体active。统一记录：全文/来源、数学分析及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id｜继续研究。

第76批新增：[GPU Travelling](GPU_TRAVELLING_CCS2025.md)，CCS2025正式排版15页、§§1–10、59引用、九页图像核对；作者主页全文、IBM/Crossref书目核验。作者明确公开Zenodo16899384，三个入口连接超时，尚未取得归档或审计代码。Notion全文回读通过后，新增 **107** 篇独立解读，合计 **160** 篇，原库53/63；含支撑/版本/技术资料，不是160套CCA GPU架构。

本批直接讨论机密GPU跨CVM交接：持久IRQ handler、eventfd/bypass与DMA切换，密钥/IV及CE/WLC/LCIC/GSP状态迁移，清理与撤销屏障。原文承认数据持有方拥有整卡访问，不能等同于逐对象最小授权或可信job通知。512MiB网络传输4.53–1103倍与llm.c总时间计算倍率1.0035–1.905分别列出；约300ms管理切换不是所有数据传输总时间常数。3LegRace完整21页新取得但仅开始阅读，仍待独立分析；ZeroKernel/SEGIVE/GR-T正式版/XpuTEE/AccShield等待办保留，整体active。统一记录：全文/来源及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id｜继续研究。

第75批新增：[GPU Taint Tracking](GPU_TAINT_TRACKING_ATC2017.md)，USENIX ATC2017。取得此前缺失的完整正式全文（13个文件页，含封面、正式209–220页），读完§§1–7及30条引用，六页算法/图表可视核对。核对官方入口；同名2026 CUDA13/NVBit仓库未被冒充为2017作者artifact。Notion独立页面全文回读通过后，新增 **106** 篇独立解读，合计 **159** 篇；原库53/63不变，合计含支撑/版本/技术资料，不是159套CCA GPU架构。

本批回到GPU数据保护机制，区分正常数据流sink、片上残留、安全擦除和异常恢复。5–20倍是相对朴素污点跟踪优化，完整跟踪平均仍是原生3倍时间；Table2清理开销不能当作整个系统开销。对项目优先建议验证停止访问、撤销失效、清理与允许新Client使用之间的状态约束，分别绑定job完成与资源可复用通知；不把指令级污点跟踪列为必需主线。GR-T正式版、XpuTEE、AccShield及原库剩余项继续pending，整体active。统一记录：完整文献/来源核验及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id｜继续研究。

第74批新增：[Proof-of-Learning is Currently More Broken Than You Think](BROKEN_PROOF_OF_LEARNING_EUROSP2023.md)，EuroS&P2023，完整20页arXivv2、23引用、13图3表、附录A–E、6Lemma/Corollary1，14页可视核对。固定15f7df4121596885ae09ea8d388fbd3d488d0b09的7文件全部blob验证，README/requirements和5个Python文件完整静态阅读；raw失败与同blob API恢复证据保留。独立Notion全文回读通过后计入新增105、总158（含支撑/版本/技术资料，不是158套CCA GPU架构）。

本批区分无效轨迹骗过检查和廉价有效同终点轨迹；固定容差与top-Q漏洞分别分析，相对阈值不能修复未抽中坏区间。明确公开库缺完整验证器、微小学习率元数据及完整实验链；记录Figure4阈值图注差异、成本步数符号、Lemma5偏差符号及单点梯度不能推出任意batch结果等边界。接受RMM身份/可信ProxyRealm授权GPU Stage-1合成假设，设备完成、应用验证、IRQ提示、DMA静默分别定义。原库剩余10项及GR-T正式版、XpuTEE、AccShield等继续pending，整体active。统一记录：完整文献/静态源码与Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/训练/攻击/构建run-id｜研究继续。

第73批新增：[Proof-of-Learning: Definitions and Practice](PROOF_OF_LEARNING_SP2021.md)，IEEE S&P2021，完整18页arXivv1、90引用、附录A–E、15图5表2算法及10页可视阅读；固定提交c286c7c0d2b45d80b4b6a7b0c2995690034927ff，7项树、6blob哈希验证，README与全部4个Python文件静态读完。Notion独立页面全文回读通过后登记，当前新增104、总157；不是157套CCA GPU架构。全文版本明确为预印本，不声称核对IEEE最终排版。

本批重点：top-Q和δ为启发式，原文承认较大合法更新可掩盖伪造；完整轨迹反序联合熵不变、熵与计算难度须区分；源码缺完整签名/时间戳/来源链，验证失败主要打印，数据hash漏绑标签/增强，cos分母和单距离top-Q存在静态问题。未复现攻击，不据此否定作者全部实验。项目保持设备终态、应用验证、IRQ提示及DMA静默分别定义。Proof-of-Learning攻击论文、GR-T正式版、XpuTEE、AccShield等仍pending；整体active。统一记录：文献与文档研究｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/训练/攻击/构建run-id｜继续研究。

日期：2026-10-27。用户重新授权持续推进逐篇研读，范围包括 GPU、Arm CCA、TEE、机密计算、可信 I/O 与 LLM 系统中和本项目有关的工作。本文是持续任务记录，不以单批页面代替全部目标。

Notion 目标库：[GPU Security Papers](https://app.notion.com/p/405659a3b8cc81f4b05efbca2a78dfe6)。开始时从 Notion 回读确认，原 63 条清单中有 35 篇完成、2 篇暂定页面，其余未完成；不因已有概述或本文登记而增加精读完成数。

## 精读规格

每篇独立页面至少覆盖：准确书目信息与原文版本；背景和问题；威胁模型、可信基与排除项；架构、关键数据和控制流程；安全不变量与论证依据；相对已有工作的增量；原型与论文设计差异；实验配置、基线、指标和定量结果；公开代码的固定版本、实际核验范围和复现限制；与其他论文及当前项目的关系；独立评价和可验证的后续设计。

原文描述、原型实现、作者自述和本项目研究推断分别标明。不把 LoC 增量当总 TCB，不把单任务/整设备独占当恶意多 Client 并发证明，不把真实 IRQ 当作特定 job 成功或 DMA quiescence 的充分证据。硬件是目标假设及实验载体，避免用 RK3588 的模拟限制替代协议分析。

仅摘要、索引或论文占位不算完成；全文或 artifact 受阻时，记录已经取得的证据和未核验事项。创建 Notion 页面后必须回读比对主要内容、段落、表格和来源；创建成功响应本身不算内容核验。

## 优先顺序与范围

| 批次 | 工作 | 任务 |
| --- | --- | --- |
| 新取得原文 | ASGARD、TZ-LLM、ccAI、MyTEE | 各写一篇，补充 artifact 范围与原型限制 |
| CCA 主干 | PORTAL、CAGE、ACAI、MOLE、PhantomMap | 现有总览拆成独立研究文档；原文和代码重新核对 |
| 通信与中断 | Devlore、CAEC、TEEtime | 核验已有精读页面，并纳入目标库入口，避免无意义重复 |
| GPU 候选 | AvaGPU、LEAP、XpuTEE、BarriCCAde | 取得全文、核对代码和评估后逐篇分析 |
| 新预印本 | FlexServe、WarpGuard | 确认版本与发表状态，全文分析；同名版本不重复计数 |
| 相邻扩展 | GuardAIn、CryptoMMU、H100 原始文章 | TensorTEE 与 Hopper 技术资料专题已完成；CryptoMMU 已固定作者仓库，继续取得全文；Hopper 专题不代替原库 TGS-001 |
| 原库待研读 | 原 63 条清单剩余论文，包括 ZeroKernel、PSSM、内存一致性等 | GEVisor（TGS-050）和 HIX（TGS-061）等已完成；保留其他未完成任务，优先直接相关内容 |

此前泛文献任务的暂停记录为历史状态。当前用户指令已重新授权相关条目的持续研读；不再将历史暂停当作不继续研究的理由。

## 当前产物与状态

最新核验进度：原库完成 **53/63**，新增 **119** 篇独立解读，合计 **172** 篇（其中一篇是 Hopper 技术资料专题；CAGE、SHELTER 期刊版分别为同一架构的版本增量解读；GPUArmor 是 cuCatch 的硬软协同期刊扩展；含异构数据中心 2022 早期稿及 ACSAC2024 正式对应全文的两个版本报告，不视为两套独立架构；含加速器 TEE 系统综述及 CPU/CCA 隔离、内存模型、中断与性能计数器攻击、训练验证和 GPU 驱动验证等支撑文献）。下文批次数量保留为历史记录，实际逐篇状态以 `progress.json` 为准。整体任务仍为 active，未完成条目不因已取得元数据或全文而计为完成。

实际逐篇状态和发布回读信息以同目录 `progress.json` 为准。尚无独立文档的条目维持 pending；原库历史状态取自 `build/gpu-security-deep-study-20261027/manifest.json`，新增状态单独记录，防止重复计数或覆盖未核验事实。

本轮新增已完成 ccAI、MyTEE、ASGARD、TZ-LLM、PORTAL、CAGE、ACAI、MOLE、PhantomMap、LEAP、WarpGuard、FlexServe、sNPU、sIOPMP、SGXIO、PipeLLM、TensorTEE 和 Hopper 技术资料专题，共 18 篇独立解读及 Notion 全文回读，其中 Hopper 是技术资料解读而非学术论文；另外完成原库 GEVisor（TGS-050）、Stealing Webpages（TGS-042）、Milkomeda（TGS-048）、Sugar（TGS-062）和 HIX（TGS-061），原库完成数由 35 增为 40，合计 58 篇独立解读。这五篇计入原库，不重复算新增论文；Hopper 专题不计作原库 TGS-001 的完成。发布核验及哈希见 `progress.json`。Devlore、CAEC、TEEtime 的已有页面正文已比对，并在目标库建立原生引用入口，不重复计数。整体研究继续，未取得全文的候选及原清单未完成项保持待研读状态。

最近七篇的直接入口与迁移范围：

| 独立解读 | 对项目的补充 |
| --- | --- |
| [GEVisor](GEVISOR_SOCC2023.md) | GPU MMIO/DMA、上下文归属和异步控制；形式化模型与公开单 enclave 路径的范围分别记录 |
| [sNPU](SNPU_ISCA2024.md) | 主存映射外的片上状态、内部通信与可信加载；两硬件域不能等同多 Client 身份 |
| [sIOPMP](SIOPMP_ASPLOS2024.md) | 表项/设备身份原子修改、实际 PA 授权与翻译分离；旧事务及页复用仍需说明 |
| [SGXIO](SGXIO_CODASPY2017.md) | 可信服务代码测量、实例身份、平台证明和真实设备绑定的区别 |
| [PipeLLM](PIPELLM_ASPLOS2025.md) | 私有推测结果、内容/IV 验证和异步数据可读边界；公开原型未闭合的验证证据 |
| [TensorTEE](TENSORTEE_ASPLOS2024.md) | 张量元数据一致性、poison/验证屏障和可信结果发布；NPU 延迟验证条件不能不加论证地推广至通用 GPU |
| [Hopper 技术资料](HOPPER_CC_TECHNICAL_REVIEW.md) | 完整 28 页演讲及官方威胁模型、固定 NVAT 路径；ready 位不等于策略成功，MIG 设计介绍与当前支持范围分开 |

本批没有以其他设备硬件能力否定 ProxyRealm 假设；设计建议围绕已有身份、GPUVM、真实 fence、epoch 和回收机制补充不变量与测试范围。未改运行代码，无新增性能测量。

接续补全原库三篇，均已全文解读及 Notion 非空行比对：

| 独立解读 | 与主线的关系 |
| --- | --- |
| [Stealing Webpages / TGS-042](STEALING_WEBPAGES_SP2014.md) | 2014 年实际 GPU 的重分配残留与片上状态，展开安全回收的内容安全条件；公开 PoC 范围及作者版本差异分开登记，不认定现代 Mali 已存在同样漏洞 |
| [Milkomeda / TGS-048](MILKOMEDA_CCS2018.md) | 信任内核的移动 API 加固，不是恶意 Host 下的 TEE；检查器状态与输入快照、可信入口相关，公开实现的阶段激活与生命周期缺口保留 |
| [Sugar / TGS-062](SUGAR_ASPLOS2018.md) | 信任宿主的每应用 vGPU 图形栈；映射、信号/IPC、显示合成和 reset 故障域，与 ProxyRealm 的完成绑定和恢复协议比较；no-sandbox 指南不当成完整安全验收 |

这三篇是原库补全及相邻隔离工作，不冒充新增 CCA GPU 论文。它们共同支持继续研究已有机制的组合性质：恶意请求如何受约束、真实完成如何绑定原任务、异常后资源何时可再次授权。ZeroKernel 和部分直接 CCA 候选仍待取得原文；不以元数据或索引页代替完成。

随后沿第一作者与 Jaehyuk Huh 新主页的真实链接取得并精读 [HIX / TGS-061](HIX_ASPLOS2019.md)，已单独发布及完整回读。它直接补充可信 GPU 服务、真实设备/MMIO 归属、每用户 context/密钥、nonce 新鲜度和服务异常终止。原型明确使用 MMIO polling，不用 interrupts，不能作为可信中断已解决的证据。它的 CPU/I/O 扩展用 KVM/QEMU 模拟，真实 GPU 执行工作负载；不以模拟方式否定论文假设。

同一作者列表另取得 **Supporting Secure Multi-GPU Computing with Dynamic and Batched Metadata Management**（HPCA 2024，204–217，DOI `10.1109/HPCA57654.2024.00025`）作者全文，SHA256 `15215d6bc078c7ef2382266837fab0868837a2037eba5948337ef0c3de7e9153`。取得时尚未完成独立精读，不计入当时的 58 篇；随后已完成全文研读、独立文档及 Notion 全文回读，见下批记录。它研究多 GPU 可信通信的 OTP 与元数据开销，不能代替跨 Realm 中断研究。

接续四篇均完成独立文档与 Notion 全文非空行回读，本批将原库推进至 41/63、新增至 21、合计 62：

| 独立解读 | 与项目的关联及证据边界 |
| --- | --- |
| [安全多 GPU 元数据，HPCA 2024](SECURE_MULTIGPU_HPCA2024.md) | 动态 OTP 与批量 MAC/ACK；允许验证前执行，需另论证外部输出屏障；未取得确认匹配的公开实现，模拟性能不当作实机结果 |
| [Heckler，USENIX Security 2024](HECKLER_USENIX2024.md) | 恶意中断诱导可信 handler 副作用；固定 artifact 定向静态核验；论文的 TDX 示例依赖插入 busy loop，CCA 测试未发现同类显式副作用 handler |
| [PSSM / TGS-045，ICS 2021](PSSM_ICS2021.md) | 分区/扇区完整身份、计数器生命周期和 MAC 强度；最佳数字含缩短标签等组合变化，不能迁移为常驻多 Client 安全证明 |
| [WeSee，IEEE S&P 2024](WESEE_SP2024.md) | 事件原因与嵌套 handler、检查早于外部副作用；固定 artifact 和依赖核验；论文明确不适用于所分析的 TDX、CCA，不能写成 CCA 已受同一漏洞影响 |

本批原文和代码仅按各文声明的范围静态研读，未运行攻击或复现模拟。对已有认证队列、GPUVM、私有快照、真实 fence 与 cookie/epoch，继续研究通知真实性与状态转换授权的区别，以及发布结果和撤销回收的不同条件。未改运行代码，无新增性能测量。

继续完成两篇，当前合计 64 篇独立解读；本批为扩展条目，原库完成数仍为 41/63：

| 独立解读 | 全文与代码证据 | 对项目的用途 |
| --- | --- | --- |
| [ASTER，MobiSys 2026](ASTER_MOBISYS2026.md) | 16 页正式作者全文、Crossref、固定根仓库与指南树、README 和两份 AOSP manifest；其余三份 blob 获取受配额限制；指南缺 scripts/部分组件及 TODO 保留 | CCA 与 AVF 的准入、证明、双向访问限制及重启连续性；区分相同服务镜像、真实服务实例和当前设备授权 |
| [Sigy，ASIA CCS 2025](SIGY_ASIACCS2025.md) | 16 页全文与附录、固定完整 PoC 树及各框架定向源码、Gramine 修补 diff；公开案例的 busy loop、合成 handler、浮动依赖分别记录 | 硬件异常原因、软件发送者与副作用授权分开；论文明确不适用于所分析的 CCA，不能冒充 CCA 漏洞证据 |

ASTER 使用软件代替硬件 RoT，内存加密只有结构/接口而未强制实施，板端性能平台以 Linux/OpenCCA 重现 AVF 主要流程，和完整 Android 的 QEMU 功能原型分开。本批不把 2.20% 应用整体口径当作所有应用均同等开销，不把启动时间排除后仍称端到端成本。Sigy 不把 Node.js/Nginx 的部署条件和 JSAT/MLP 的原型简化隐藏为任意应用的稳定攻击。

两篇均已创建 Notion 独立页面并逐非空行核对。与前批合计，当前续研的 29 篇页面回读比对通过；这不代替原库其他页面的历史核验。主线进一步明确为：运行期完成、错误、取消、ACK、reset 各自只能执行被授权的状态变化；服务重启、设备重新分配和持久状态更新不能让旧会话恢复对新任务的权力。已有机制的组合性质仍需单独验证，epoch 不自动等于 DMA 已停止。未改运行代码，无新增性能测量。

扩展中需要保留的三条关键证据：LEAP 的多 CPU 沙箱并行不等于 GPU 并发共享；WarpGuard 的 CPU 验证和调用点策略自动检查尚未在原型完成；FlexServe 的 97.2% 普通应用性能来自与安全推理交替运行的条件，不能写成同时运行下的结果。PhantomMap 的 GPU 页类别也不能替代逐 Client 授权。

接续五篇研读完成的记录如下；本批将原库推进至 43/63、新增至 26、合计 69 篇，五篇均已发布独立 Notion 页面并逐非空行回读核验：

| 独立解读 | 关键证据与本项目关系 |
| --- | --- |
| [RContainer，NDSS 2025](RCONTAINER_NDSS2025.md) | 可信 Normal EL1 miniOS 与不可信 conshim；130 LoC 只是 EL3 增量；AES-ECB IPC 不提供真实性/新鲜性，安全启动与实例授权分别分析 |
| [SHELTER，USENIX Security 2023](SHELTER_USENIX2023.md) | 18 页全文与固定源码；公开创建路径为 vector SHA256 白名单而非通用整镜像签名验证；可信 handler 注册不等于事件原因授权 |
| [GPUHarbor / TGS-051，ISSTA 2023](GPUHARBOR_ISSTA2023.md) | 全文与固定生成器；106 条设备记录与至少 58 个型号分开；合法弱内存结果不能当作隔离漏洞，原始托管 artifact 获取受阻 |
| [MC Mutants / TGS-058，ASPLOS 2023](MC_MUTANTS_ASPLOS2023.md) | 全文、固定代码及三组作者数据离线重算 PCC；属于统计再分析，无新增 GPU 运行；复现分数不是结果正确概率 |
| [CAGE 期刊扩展，TDSC 2026](CAGE_TDSC_EXTENSION_2026.md) | 2025 接受稿与 2026 正式卷期区分；新增可信 XDMA 描述符与 buffer-channel 绑定；FPGA 应用独占不同于 GPU 任务独占，不当成并发共享证明 |

CAGE 扩展的公开仓库确有 FPGA XDMA/CAGE 控制入口与 Monitor MMIO 模拟，README 同时注明 FPGA 基准应用待发布。未将不完整材料误写为完整复现；公开 GPU 性能原型的完整性检查差异仍保留，不能直接推广成所有期刊实现的漏洞。新增机制重点为设备状态生命周期与执行对象授权，没有用模拟平台能力否定项目假设。

此时 34 篇续研发布页面的本地全文非空行比对均通过；这不代替原库其余页面的历史核验。未改运行代码，无新增性能测量。MC Mutants 的离线数据再分析不计作硬件实验。取得 SHELTER 的 TDSC 扩展全文时，尚未完成版本比较，未在该阶段登记完成。

随后全文研读 [SHELTER 期刊扩展，TDSC 2026](SHELTER_TDSC_EXTENSION_2026.md)，单独发布并逐行回读，使新增解读增至 27、总计 70。正式标题为 Complementing Confidential Computing Environment for Applications on Arm CCA，DOI 为 2025 年，正式卷期为 2026 年 23(1):97–114；新增 DA 的设备独占分配、GIC distributor 保护、affinity 与 pending 保留是本项目中断主线的直接相关材料。

期刊版将 Monitor 增量列为 2,425 SLoC，其中 DA 353；没有把新增行数当作完整系统 TCB。已核对公开 HEAD 仍为 2023 年提交；其基本向量/GPT 路径不能代替期刊新增 DA 的完整匹配实现。作者 FVP 的 GIC 篡改阻断实验、模拟性能、无 attestation、ICENABLER 文字疑点、MaxRSS 额外开销口径及 pending 与逐 job 完成语义的区别均在独立报告保留。当前续研页面校验累计 35/35 通过；本批共新增六篇解读，包括两个期刊版本增量，没有新增硬件实验。

当前仍待全文核验的直接候选包括 AvaGPU、XpuTEE、BarriCCAde。CAGE 的 TDSC 扩展已经完成独立版本解读，不再列为全文缺失。GitHub 原始清单的 AvaGPU 会议标签为 ASPLOS’23，与 DOI 正式 CCS 2023 元数据不符，沿引用追踪时采用核实后的正式信息。FlexServe 两个同标题索引记录按同一候选组处理，本轮实际研读 arXiv:2603.09046v3；未取得的另一个编号不另计新论文。

继续完成四篇，均已发布独立 Notion 文档并逐非空行回读比对，本批使原库增至 46/63、扩展至 28、合计 74 篇：

| 独立解读 | 证据与项目关联 |
| --- | --- |
| [cuCatch / TGS-059，PLDI 2023](CUCATCH_PLDI2023.md) | 24 页官方全文和正式元数据；调试无主动攻击者假设、最后访问前才做时间检查、概率 UAF 和未计入的分配维护成本保留；不能直接作为恶意 Client 的沙箱 |
| [GPUArmor，TACO 2026](GPUARMOR_TACO2026.md) | 25 页官方作者稿、正式 23(3) 元数据；cuCatch 期刊扩展。新增 ISA/MLU/MLB，缓存失效和当前 tag 的并发语义；保留 tag=0 兼容、HMM 缺口、压力退化及无匹配公开工具链的边界 |
| [GPU Concurrency / TGS-052，ASPLOS 2015](GPU_CONCURRENCY_ASPLOS2015.md) | 15 页主文、4 页技术附录与部分作者结果页面；原子/volatile 不自动等于同步，optcheck 保证测试没有被编译改变；旧 .cg/RMO 模型不能替代现代 GPU 或 CPU/VM/DMA 语义 |
| [PTX 形式化 / TGS-057，ASPLOS 2019](FORMAL_PTX_ASPLOS2019.md) | 14 页全文、固定完整仓库树和定向模型/证明核验；scope-inclusive、release sequence 和小 bound 搜索遗漏；三项 Coq 定理不等于标准 CUDA/OpenCL、真实编译器或 RTL 已验证 |

本批四篇为对象安全与可信通信顺序的支撑工作，没有包装成四套新 CCA GPU TEE。与前批累计 39/39 篇续研页面全文回读通过；保留原库其他页面的历史核验范围。所有定量数字为作者结果，本轮未运行 CUDA、Coq、Alloy、模拟器或硬件测试。未改运行代码，无新增性能测量。

对当前设计的具体启发：授权缓存的命中仍须绑定 Client/对象代次/权限/epoch；释放失效与在途 DMA 停止分别论证；结果写入、可信 completion 发布、通知投递、Client 验证读取构成显式顺序链。已有 RMM 身份、GPUVM、认证队列、私有快照、真实 fence、cookie/epoch、persistent IRQ127 保留为分析基础，没有把它们当作缺失机制。

直接候选仍在追踪。AvaGPU 新确认两个同名公共仓库：WUSTL-CSPL 入口当前提交 `a418506211d1fe719dfcb807ddbb08060e8f50c3` 的根树只有 LICENSE；J1nwenWang 入口当前提交 `b1f4b09cfbef79aa98f5e211622c846e1bfef723` 的根树为两个 Rodinia 目录。本轮仅查看根树，未认定为完整 AvaGPU 可信实现，也未取得匹配全文。BarriCCAde 已追到 FAU 官方论文清单及 CRIS 条目，仍只有 DOI 等元数据、没有可确认的全文入口。XpuTEE 的 IPADS 列表/成员页仍未取得全文。搜索引擎此次返回与精确题名不符的结果，不作为论文证据。

另外已经取得但尚未完成独立精读的原文包括 Automatically Comparing Memory Consistency Models（POPL 2017）、The Semantics of Shared Memory in Intel CPU/FPGA Systems（OOPSLA 2021）及 Specifying and Testing GPU Workgroup Progress Models（OOPSLA 2021），均不计入 74 篇。GPUArmor 2026 作者稿首页的卷期/月仍为占位，正式信息按 Crossref 核对；原库 CPU/FPGA 条目旧会议标签与作者信息的差异留待该篇独立报告解释。

跨论文总结见 [聚焦报告](../GPU_CCA_TEE_FOCUSED_RESEARCH_20261027.md) 和 [续篇](../GPU_CCA_TEE_FOLLOWUP_RESEARCH_20261027.md)。它们不能代替本任务的逐篇交付。

## 接续精读：异构完成语义与端到端 CPU/GPU 证明

本批新增三篇，均已完成全文、独立本地文档、Notion 发布和全部非空行回读。原库新增两篇，扩展新增一篇：原库 48/63、新增 29、合计 77；原库还剩 15 条。续研全文回读累计 42/42 通过，不替代其余历史页面的核验。

| 独立报告 | 新增证据与项目关联 |
| --- | --- |
| [Memalloy / TGS-054，POPL 2017](MEMALLOY_POPL2017.md) | 15 页全文、正式 DOI、作者数据及 2016 固定模型；deadness、提升算法不完整性、小 bound 漏检与历史 PTX 跨 scope 累积；用于比较协议优化的可观察行为 |
| [CPU/FPGA Shared Memory / TGS-056，OOPSLA 2021](CPU_FPGA_SHAREDMEM_OOPSLA2021.md) | 28 页全文、固定 harpy 仓库及模型/队列路径；写响应、通道完成和全局可见性分开；纠正原 CCS 标签，保留 34 项交叉检查跳过、stress 子集、公开代码规则及运行器分类差异 |
| [EnclaveX，arXiv 2026](ENCLAVEX_ARXIV2026.md) | 8 页 v1，近期 CPU/GPU 联合证明与按策略发密钥；实际 TDX/H200/SIM 路径，CCA 兼容仅为主张；跳过 QvL 和未知 GPU 测量、人工预置密钥及最小应用基准完整披露 |

三篇分别支持协议验证、异构数据顺序与远程信任建立，没有包装成三套 CCA GPU 保护架构。对项目，已有认证队列、GPUVM、私有快照、native fence、cookie/epoch 和 persistent IRQ127 继续作为基础；“实际完成→输出可见→可信记录发布→目标唤醒→Client 验证”的每条边应明确现有机制依据。启动证明和合法映射也不能替代逐任务终态与撤销条件。

本轮直接检索还发现 NanoZone（CCA root monitor 下进程内隔离）和 CCAegis（CCA 函数/敏感数据隔离）。NanoZone 已取得 arXiv:2506.07034v2 的 17 页全文，SHA256 `f3390a4eca36449ca5a3e1d2547ccc3cb657d1fbbb6267eb72b03ecdd6bb8450`，只检查首页及索引摘要，尚未完整研读或计数。CCAegis 当前只有索引摘要/DOI 和候选 arXiv 入口，仍须核对全文、代码及与 NanoZone 的关系。两者是 CPU/CCA 隔离支撑，不能仅因标题含 CCA 就称为 GPU TEE。

AvaGPU、XpuTEE、BarriCCAde、GuardAIn 的既有全文状态保留；本轮 XpuTEE/GuardAIn 的仓库搜索未确认匹配公开实现，没有把无关同名结果当证据。GPU workgroup progress 已取得但未精读；其 DOI 与原库 CONCUR 2018 调度论文不同。整体任务维持 active，没有把单批交付当作全部目标完成。

统一记录：逐篇论文与代码静态研读｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增硬件 PASS｜持续推进，按原文、artifact 与 Notion 回读证据登记。

## 接续精读：可信服务内部边界与 CCA 细粒度隔离

本批独立完成 [NanoZone](NANOZONE_TDSC2026.md) 和 [CCAegis](CCAEGIS_TIFS2025.md)，两篇均全文研读、写入 Notion 并逐非空行核对，分别检查 73/90 行，续研累计 44/44 页面通过。原库维持 48/63，扩展增至 31、合计 79。两篇为 CPU/CCA 支撑工作，不是两套新 GPU TEE；原库剩余 15 条及直接候选的受阻状态保留。

NanoZone 取得 17 页 arXiv v2，并核对正式 TDSC 2026 DOI；POE/PIE/GPC3、GCS/PIM、异常上下文及本地化分配分别分析。没有确认匹配公开实现；同类型目标复用、缺远程证明、物理连续窗口、模拟性能与数据口径差异保留。其“约 95% 吞吐”是相对 SHELTER，不是相对 Native。

CCAegis 取得 16 页 arXiv v1，核对正式 TIFS 2025 卷 20、12507–12522；2026 为作者稿上传日期。固定论文指定仓库提交 `0f93d9a292b3caaf1534c7a39abb0cb5660fd5bc`，根树截断已披露，另取得 scoped src/driver 和完整 pass/analyzer 子树。定向核验 Monitor、异常向量、调用门、复制/销毁及插桩相关代码，记录签名/敏感 I/O TODO、随机值日志、完整四态配对门未确认、切换任务锁和特殊函数分支。这些是有界静态观察，不是已运行的攻击或所有版本漏洞结论。

CCAegis 每个 CCApp 仅有单一 crypto domain，多域是扩展设想；没有把多线程独立栈当成多 Client 域隔离。两篇没有明确正式扩展关系，共同作者不足以认定。公开实现、论文提出的防护和实际作者测量分别登记；所有性能数字均来自作者，没有新硬件测试。

项目启发是：可信 Proxy 的敏感映射/完成/回收权限可以进一步分界，合法调用入口仍须检查原始 Client、对象代次、权限和当前状态。已有 RMM 身份、GPUVM、私有快照、认证队列、native fence、cookie/epoch 和 persistent IRQ127 继续作为基础；异常上下文保护不等于 GPU job 完成真实性。采用可信 Proxy 统一控制 SMMU、软件合成合法 HPA Stage-1 的研究假设保持成立，不能把两篇 Normal-world CPU 隔离安排直接当成 Realm 内 GPU 方案。

新增待研读线索：HiveTEE，正式 TIFS 2026、21:2300–2312，DOI `10.1109/TIFS.2026.3660599`；已沿作者 publication 页面取得 13 页全文，SHA256 `4fb643a0ea38586cb1bbb425f5d28a8f0c95c0bf332d8869e4007dd635b6e416`，尚未精读，不计完成。另一候选 Confidential Computing with Heterogeneous Devices at Cloud-Scale，ACSAC 2024、102–116，DOI `10.1109/ACSAC63791.2024.00025`，已核对正式书目和索引摘要；其可信控制器代理异构设备方向值得跟进，但全文和 artifact 未取得，不将摘要性能数字当作已验证证据。

统一记录：两篇全文与书目核验、CCAegis 固定实现定向静态研读、Notion 全文回读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增 PASS｜整体 active，待研读项继续保留。

## 接续精读：共享服务权限、任务认证与进展条件

本批独立完成三篇：HiveTEE、GuardAIn 和原库 TGS-055 GPU Schedulers。三篇均已全文研读、独立写入本地与 Notion、逐非空行回读，分别检查 68/91/64 行。当前原库 49/63、扩展 33、合计 82；续研累计 47/47 页面全文核验通过。原库仍有 14 条未完成，整体任务 active。

| 独立报告 | 证据与项目用途 |
| --- | --- |
| [HiveTEE，TIFS 2026](HIVETEE_TIFS2026.md) | 13 页全文，Realm-world RME+MTE 域隔离；SDom0 共享标签管理、x18/插桩、DTT 与域入口。保留同 GPT 控制流风险、公开代码未确认、选择性保护 <3% 的口径；属于 CPU/CCA 支撑工作 |
| [GuardAIn，IEEE S&P 2025](GUARDAIN_SP2025.md) | 18 页作者 camera-ready、准确 DOI 及 meta-review；整 NPU 单租户，可信锁定 ACK、输出加密 CQ、PC_START/二进制序列绑定；任务参数/新鲜度未充分展开与闭源限制保留；属于直接相邻加速器 TEE |
| [GPU Schedulers / TGS-055，CONCUR 2018](GPU_SCHEDULERS_CONCUR2018.md) | 17 页官方全文，LTS/TFC、HSA/OBE/LOBE 与发现协议；workgroup 语义和 SC/终止前提保留，没有新硬件性能实验；公平性不等于有界延迟，不能替代 Client 调度或可信完成协议 |

GuardAIn 此前全文受阻，本批沿第一作者 publications 页面取得真正全文后才完成解读。附录明确源码不会公开，不将同名 GitHub 项目冒充实现；少于 0.1% 的 Llama 推理成本与显著 setup、小模型短输入 16.03% 的结果分别记录。内存 API 完成、旧访问停止和异常 reset 回收不自动合并为同一条件。

对项目继续保持可信 ProxyRealm、RMM 原始 Client 认证、受保护直接 HPA Stage-1 的假设，保留既有 GPUVM、认证队列、私有快照、native fence、cookie/epoch 与 persistent IRQ127。可深入的增量是完整执行契约、事件可授权的状态转换、真实完成与安全回收的条件，以及四层进展假设；无需重做已有基础机制。

Confidential Computing with Heterogeneous Devices at Cloud-Scale 已追到作者提供的 PDF 地址和 ACSAC 官方演讲稿，取得 PPTX；PDF 连接仍超时，演讲稿也未完整研读，不计完成。AvaGPU、XpuTEE、BarriCCAde 保持待取得全文；OOPSLA 2021 GPU workgroup progress 已取得但未精读，不与 CONCUR 2018 本篇重复计数。

统一记录：三篇全文、书目与 artifact 公开范围研读、Notion 全文回读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无模型检查器/硬件 run-id 或新增 PASS｜作者结果、材料缺口和项目建议分别保留。

## 接续精读：组合证明、断开生命周期与 GPU 进展

本批完成 [Composite Enclaves](COMPOSITE_ENCLAVES_TCHES2022.md) 和 [GPU Workgroup Progress](GPU_WORKGROUP_PROGRESS_OOPSLA2021.md)，两篇均完成全文、独立报告、Notion 发布和全部非空行回读，分别 79/83 行；续研累计 49/49 页面核验通过。原库保持 49/63、14 条未完成，扩展增至 35、合计 84；两篇不重复计入原库 CONCUR2018 调度工作。

Composite Enclaves 完整研读 27 页 arXiv v3，并核对 TCHES2022 正式元数据。固定五项完整仓库树，定向读取 Keystone/Eyrie 补丁；公开实现的断开通知、ownership transfer TODO、错误返回锁路径、映射特化和动态连接证明缺口均保留。论文为 RISC-V/Keystone 异构 TEE，最贴近项目的是可信驱动服务、连接实例证明与异步/同步断开；原型只评估 polling，不能作为多 Realm IRQ 安全的完整先例。

GPU Workgroup Progress 完整研读 30 页作者稿，固定 16659 项未截断仓库树并定向检查模型、生成器和 runner。对五配置正式表及 A12/A14/Mali 三设备表作离线重算：483 个测试、122 个 weak LOBE conformance；A12/Mali 均有同一组 11 个 RR 违反，A12 CSV 分母 21 与正文常规 20 次不同；A14 系统表为零，非系统复跑观察单列。stdout 无失败即 PASS 的运行器限制明确披露，未运行 GPU 或模型检查器。

项目建议围绕现有 RMM 身份、GPUVM、私有快照、native fence、cookie/epoch 和 persistent IRQ127，检查连接、任务、完成、撤销与设备重启是否绑定同一实例。可信通知不能替代真实完成，合法映射不能保证工作组进展，Client 轮转提交不等于 GPU workgroup 公平性。既定 ProxyRealm/SMMU 与授权合成 Stage-1 假设保持成立。

统一记录：两篇全文、固定代码静态检查及作者 CSV 离线复算、Notion 全文回读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜CSV 解析退出码 0，非硬件复现；无新增硬件 PASS｜整体 active，直接 GPU TEE/CCA 候选及原库未完成项继续保留。

本批继续沿作者主页取得并完整研读 [Empowering Data Centers for Next Generation Trusted Computing](HETERO_DATACENTER_ARXIV2022.md)，arXiv:2211.00306v1，2022-11-01，23 页。Notion 全文回读 86 行通过，续研累计 50/50；扩展 36、合计 85，原库仍为 49/63。这是作者在 ACSAC2024 条目下链接的早期版本，标题、长度、软件/硬件 SC 与 912/2236 节点结果不同，正式版 PDF 仍受阻，不计为正式版完成或第二套独立架构。

新增解读重点为 ERT 的 job 归属、非 TEE 节点整节点独占、静态资源与可信配置、PCR/密钥关系、回收流程及中断语义。2022 原文用加密 DMA 说明伪造中断不会泄露明文，但没有给出多 Client 任务完成真实性、结果可见与 IRQ 目标关联的完整证明。对本项目，这是已有身份/映射/完成/IRQ 机制组合论证的支持；没有把它包装为多 Client 共享 GPU 已解决的先例。

公开实现搜索未确认匹配 artifact，基础模拟器不当作作者新增实现；GPU trace 估算、AI/SSD 模拟及 SC 软件微测分开记录，表格比例与面积单位差异保留。未改运行代码，无新增性能测量，未执行 GPU、FPGA、模拟器、形式工具或攻击。

## 接续精读：GPU TEE 可用性、完成顺序与共享观测

本批完成原库三篇，均全文研读、独立写入本地与 Notion，并回读比对全部非空行：AvaGPU 67 行、弱内存错误 58 行、GPU 侧信道期刊扩展 60 行。原库推进至 52/63、剩余 11 条；扩展仍为 36、合计 88。续研页面全文回读累计 53/53 通过，不替代其他历史页面核验。整体 active。

| 独立报告 | 新证据与项目意义 |
| --- | --- |
| [AvaGPU / TGS-063，CCS 2023](AVAGPU_CCS2023.md) | 从作者实验室 publication.html 取得真实 15 页全文，纠正原清单 ASPLOS 标签。CPU/GPU 优先级耦合、签名插桩、可信进度点、channel reset 与 REE IRQ 处理预算；明确 WCET/可信编译条件、公式未独立展开的恢复成本、基本/互不信任任务扩展、原型虚拟 DMA 与通用物理 DMA monitor 的差别 |
| [Weak Memory Errors / TGS-053，PLDI 2016](WEAK_MEMORY_ERRORS_PLDI2016.md) | 15 页仓储 accepted manuscript；55/70 反例组合、压力调参成本、经验式 fence 的非完备性、算法文字/伪码差异、过关样本性能筛选与异常值。用于完成记录顺序论证，不当作新 TEE 或删除屏障的证明 |
| [GPU Side Channels / TGS-060，TDSC](GPU_SIDE_CHANNELS_TDSC2021.md) | 12 页 accepted manuscript；early access 2019 与 2021 卷记录区别，CCS2018 扩展关系、窗口分类增量、全局显存/自身计数器与竞争信号、限速/降精度残余。没有将按键时序当作已恢复任意密码，或将输入层大小分类当作完整模型恢复 |

AvaGPU 是与项目直接相关的 GPU TEE，本批另两篇是顺序与侧信道支撑，不包装成三套新的 CCA GPU 架构。官方固定仓库完整树仅 LICENSE；作者同名仓库完整递归树为两个 Rodinia 根、3,264 项，没有将其当作完整可信实现或执行复现。其进度监测和 IRQ 预算值得借鉴，但不替代多 Client 完成身份、新鲜度与安全回收协议。

项目建议继续建立在已有 RMM 认证身份/队列、GPUVM、私有快照、native fence、cookie/epoch、persistent IRQ127 上：真实完成→输出可见→可信记录发布→目标唤醒→Client 验证；另明确每 Client 干扰预算及终止后停止访问的证据。终态、及时性、回收和观测隐私是不同义务，定向 IRQ 不能独自全部保证。采用可信 ProxyRealm/SMMU 与建图软件授权合成合法 HPA Stage-1 的假设保持。

另沿作者主页取得 StepStone: LLM-Based GPU Kernel Driver Fuzzing via User-Space Libraries，18 页 PDF，SHA256 `ecf9cc0d2a97eeb7f4582186a675b83b5afaad4e46041dd12fa12f674c7c84a4`，代码入口 seclab-ucr/StepStone。尚未全文研读、核验正式书目和固定实现，不计入 88；其方向是 GPU 驱动攻击面，不能仅因相关而称为 CCA GPU TEE。

XpuTEE、BarriCCAde、ACSAC2024 异构数据中心正式版及原库剩余项继续保留。Notion 目录只更新当前总数并追加本批入口，历史批次与子页面保留。统一记录：三篇全文、书目与公共材料范围核验、Notion 全文回读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无新增硬件/攻击 run-id 或 PASS｜继续研究，材料受阻和未执行项明确登记。

## 接续精读：可信 GPU 驱动的输入与深层状态验证

本批完成 [StepStone（IEEE S&P 2026）](STEPSTONE_SP2026.md) 和 [Moneta（NDSS 2025）](MONETA_NDSS2025.md)：18/17 页全文、固定公开实现、独立本地报告及 Notion 全部非空行回读，分别核对70/64行。续研累计55/55页面通过；原库仍为52/63、剩余11条，扩展38、合计90。两篇属于GPU驱动验证支撑，不包装为新的CCA GPU TEE架构。

StepStone 从用户库API生成输入，检查库感知wrapper、类型/依赖描述与驱动反馈；完整固定树9459项。保留amd64生成头、部分EMPTY wrapper、模型/配置差异、初始化/重试分支及论文表述不一致。其Moneta对照仅用描述文件，不能视为完整SnR/RnR系统对比；11个缺陷全部来自NVIDIA，未执行/失败对照不当作零覆盖。

Moneta 通过真实VM快照、后续记录、fd上下文保留和设备I/O规则重宿深层状态；Mali实验使用RK3588S/G610，但只有计算快照，未跑通Guest图形。固定根递归树截断，另取完整根树和executor/host/scripts子树；定向检查agent、executor、覆盖反馈和配置。论文Algorithm1交集条件与文字有疑点，实际代码使用新增signal差集并另检查重执行稳定性，不将书面疑点当作代码漏洞。NVIDIA深状态触发与Mali的RnR可发现缺陷分别记录。

对项目保留既定ProxyRealm/SMMU与授权合成合法HPA Stage-1假设，以及已有RMM认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127。增量是围绕这些机制组织有效前缀与非法后缀，验证跨Client对象引用、撤销/reset后的晚到完成、对象同值句柄的新代实例和安全回收。覆盖/crash只是反馈，oracle还应核对受害Client结果、可信终态及实际停止访问；测试快照回滚不等于生产安全代次可回滚。

原库GINN继续缺可核对正式全文：新核对DOI/作者及相关SGX-ADL仓库，但未确认其是匹配GINN的artifact，不用同作者代码替代原文。XpuTEE、BarriCCAde、ACSAC2024正式版和原库剩余条目继续保留，整体active。

本批追加核查：XpuTEE出版方PDF入口返回403 HTML而非PDF；BarriCCAde的IEEE全文入口超时，FAU官方列表再次核对；ZeroKernel共同作者Jaehyuk Huh的新publication页面只有IEEE链接，未提供作者PDF；SEGIVE重新核对DOI及作者，索引仍无公开PDF位置。证据见batch21-direct-candidates-acquisition.json和batch21-author-source-followup.json，没有把这些访问结果登记为全文或精读完成。同步纠正source_constraints内GuardAIn的历史“全文待取得”记录，以已完成的独立报告为准。

统一记录：两篇全文、固定实现定向静态研读、Notion全文回读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无模型调用、VM、fuzzer、攻击或硬件run-id及新增PASS｜作者结果、静态观察和项目建议分别记录。

## 接续精读：加速器 TEE 设计空间与设备可信生命周期

本批完成 [SoK: Analysis of Accelerator TEE Designs（NDSS 2026）](ACCELERATOR_TEE_SOK_NDSS2026.md) 和 [ITX（USENIX ATC 2023）](ITX_ATC2023.md)。两篇均完整阅读18页全文，分别核对官方PDF/作者链接全文及正式书目，独立写入本地与Notion并回读全部非空行。续研累计57/57页面核验通过；原库52/63、剩余11条，扩展40、合计92。SoK是综述，ITX是IPU可信扩展，不将两篇包装为新的CCA GPU架构。

SoK整理51项研究并以Host-type/Acc.-type/Mix-type归类，检查全部167条参考文献；搜索前200项后引文追踪不等于穷尽领域。最高特权代码减少不等于服务移出TCB，缺少TPM不等于无法证明，访问控制/AEAD/启动证明也不等于任务完成及DMA停止。LLM实验正文称9个模型、图列10个，SCALE-Sim加密估算与cloc增量不能当成本项目实机成本或完整驱动TCB；图形表格提取限制保留。

ITX完整解读设备可信模式、CCU的DICE式身份与密钥层级、manifest/参与方/流/epoch绑定、SXP认证数据流、软件expected-IV检查和退出流程。原生reset不清tile内存，ITX额外执行quiesce、scrub、停用密钥后才恢复Host访问。原型整IPU单作业独占，并额外信任ICU和未加密板级链路；安全恢复、完整二进制测量及A.4加固启动尚未实现。作者实测开销3–58%，摘要低于5%不能覆盖所有模型；13–17倍CPU SNP对比含硬件及batch差异。未确认匹配公开实现，不声称代码审计或硬件复现。

本批纠正GR-T引用：正式题名Safe and Practical GPU Computation in TrustZone，EuroSys2023、505–520，DOI 10.1145/3552326.3567483；目录旧链arXiv:2111.03065v1实际为2021年CODY早期稿Safe and Practical GPU Acceleration in TrustZone，原库TGS-004已读。正式GR-T全文仍未取得，不能把CODY再算一次或将GPUReplay代码当作完整GR-T实现。作者主页、会议录、完整GitHub树及获取记录已保存。

项目保持可信ProxyRealm统一控制SMMU、RMM认证原始Client、建图阶段授权与软件IPA→HPA合成受保护Stage-1，以及既有认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127。可继续研究连接证明与当前资源授权的绑定、任务终态到输出可见的顺序，以及撤销后真正停止访问与清理后复用；专用异常引脚或认证数据流都不是多Realm虚拟IRQ路由/ACK/去重协议的替代品。

新增线索HyperTEE、AccShield、Salus-GPU和SeDA仅由SoK引文发现，尚未全文研读，不计完成。GR-T、XpuTEE、BarriCCAde及ACSAC2024正式版等待取得全文状态保留，整体active。

统一记录：两篇全文、正式书目与公开材料范围核验、GR-T/CODY版本纠正及Notion全文回读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、模型、模拟器、攻击run-id或新增PASS｜继续研究，证据缺口与原型未实现项明确保留。

## 接续精读：HyperTEE的管理边界与共享对象授权

继续完成 [HyperTEE（MICRO2024）](HYPERTEE_MICRO2024.md)，16页正式全文及110条参考文献、DOI、官方议程与作者链接核对，独立Notion页面62行回读通过。续研累计58/58页面通过；原库52/63、扩展41、合计93。作者文件名micro25不改变正式2024书目，未确认匹配公开实现，同名服装网站不作artifact。

重点解读CS/EMS物理职责拆分、EMCall真实enclaveID与特权检查、私有mailbox请求响应一一绑定、共享成员名单/权限/销毁权、物理页归属及TLB刷新、EMS控制的DMA白名单。管理侧的身份与映射组合直接支持ProxyRealm研究；其CS返回路径采用polling，GPU及VM支持主要位于讨论章节，原型实际为Gemmini和NIC，不能称已验证多Realm共享GPU或完整虚拟IRQ协议。

保留28位MAC和物理重放排除项、噪声不等于无泄漏证明、3843行仅EMS Runtime及未完成形式验证、部分图形字体提取限制。2.0%/1.9%整体开销与6.3%–49.7%分配微测分开，最高50倍是对软件加解密通信路径；多核SLO是软件模拟，7nm面积/最高频率是综合分析，全部为作者结果。正文2.5%整体口径与前文2.0%/1.9%不一致，不自行修改数据。

对项目仍保持既定ProxyRealm/SMMU和软件授权合成合法HPA Stage-1假设，已有RMM认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127继续作为基础。研究增量可围绕请求原始身份、共享对象实例、真实完成与输出可见、ACK/撤销及旧代事件复用建立组合不变量，而不是重新发明已有机制。

继续取得Salus-GPU的16页作者全文，SHA256 9e090b064ba2875cdf5a15c3d99aabc6d701ef2d4f3964599d9bc09070975999，尚未全文研读；与同名CPU-FPGA Salus区分。AccShield正式DOI和作者条目核对，固定匹配仓库ef56ec15a42193bd8f988fef62a5653c7f5037a8，完整591项树及root/hw/sw README只作公开范围检查，全文仍待取得，未审计安全源码。两项均不计完成，候选状态见progress.json。

统一记录：HyperTEE全文/书目/公开材料核验与Notion回读，后续候选取源｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、综合、模型、模拟器或攻击执行及新增PASS｜整体active，原库11项和直接候选未完成状态保留。

## 接续精读：共享访问权交接与GPU内存身份生命周期

本批完成[Salus-GPU（HPCA2024）](SALUS_GPU_HPCA2024.md)和[Elasticlave（USENIX Security2022）](ELASTICLAVE_USENIX2022.md)，均独立写入Notion并逐非空行回读，分别66/78行。续研页面累计60/60通过；原库52/63、扩展43、合计95。两篇分别为GPU安全内存机制和相邻TEE共享内存模型，不包装为两套新CCA GPU架构。

Salus-GPU完整阅读16页作者稿、67条参考文献和artifact附录，核对正式DOI、作者出版页及Crossref/OpenAlex。分析稳定CXL身份与显存位置缓存、split/collapsed counter、tag/dirty状态及mapping cache失效；脏chunk逐出仍需重加密。保留29.94/29.4、剩余47.79/47.97和35%footprint下34.48/29.94的原文差异；56位MAC不当成128位安全。Google Drive目录与嵌入入口均超时，未取得匹配源码，附录Publicly available No与作者Artifact available标签不强行合并；同名CPU-FPGA Salus不混用。

Elasticlave正式19页PDF（含封面）、65条参考文献与独立3页artifact完整阅读；固定评估提交29aab3993f2c4c28b4c59053ecd1fb44a448012f，完整820项树和Monitor定向静态路径。重点是owner/当前独占权分离、固定上限、自身动态权限、原子transfer、PMP/IPI同步和事件。PMP更新宏确有sfence.vma；IPI处理ACK不等于应用消费、GPU完成或DMA停止。评估源码L位先赋值后比较、区域槽位uid复用及transfer与正文设计差异保留；未运行利用，未将错误分支直接称为可达攻击。

Elasticlave的FireSim性能与QEMU功能模式区分，SPLASH-2对照缺少加解密、web/KV仅profiling推算、CPU time与wall-clock差异、6814 LoC统计范围分别说明。两篇作者模拟结果不能迁移成本项目glmark或LLM实测。

项目保留可信ProxyRealm/SMMU、RMM认证原始Client、建图授权软件IPA→HPA合成受保护Stage-1假设，已有GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127继续作为基础。研究增量是共享对象在提交、消费、发布、撤销及复用各阶段的访问权、通知语义和可信终态；结果可发布与旧访问能力已终止分别建立证据，不以超时或普通ACK授权回收。

AccShield继续核对IBM、DAC官方条目、作者GitHub及固定591项树，IEEE返回HTML或超时，正式全文未取得；不以摘要/README充作完成。GR-T、XpuTEE、BarriCCAde、ACSAC2024正式版及原库11项保持未完成。整体active，历史候选状态由最新登记覆盖。

统一记录：两篇全文、artifact及有界静态路径研读、Notion全文回读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无GPU/VM/模拟器/攻击run-id或新增性能PASS｜保留材料缺口、数字差异与未测异常路径。

## 接续精读：可信设备身份、陷入入口与安全内存构造

本批完成[SeDA（DAC2025）](SEDA_DAC2025.md)和[CURE（USENIX Security2021）](CURE_USENIX2021.md)，分别69/90个非空行全文回读通过；续研页面累计62/62核验通过，原库52/63、扩展45、合计97。SeDA是NPU内存机制，CURE是通用RISC-V TEE及可信I/O支撑，均不包装为新CCA GPU实现。

SeDA阅读7页匹配DAC书目的作者v1及22条参考文献，固定公开371文件tree并定向阅读。针对论文先描述的固定keyExpansion掩码给出有条件代数保密性反例，与PA/VN混入keyExpansion变体和实际公开代码严格区分；没有执行攻击、恢复密钥或确认公开实现包含同样multi-output B-AES。聚合认证的项身份、重复计数、版本新鲜度和验证前副作用屏障分别展开。secureSim地址遍历并非完整MAC验证，示例固定密钥/nonce、assert及输入缺失均限定范围。TCAD2026相似题名只作候选元数据，不计第二篇完成。

CURE阅读19页正式PDF及107条参考文献，六个整页图片提取/校正方向后补读，避免文本抽取遗漏关键页。重点是SM与普通最高特权固件隔离、eid实际PA/PTW/MMIO路径、清L1先于提升身份、DMA独占窗口、共享region转权后IPI通知，以及user/kernel中断delegation的区别。eid销毁后明确可复用；VM只为设计能力，原型未实现hypervisor扩展；SM可形式验证不等于已验证。FPGA面积、服务TCB、模拟cache与普通进程基线分别说明。未确认匹配公开实现，不宣称源码安全审计。

项目继续保留可信ProxyRealm/SMMU、RMM原始Client身份、建图授权软件IPA→HPA合成受保护Stage-1，以及已有GPUVM、认证队列、私有快照、native fence、cookie/epoch和persistent IRQ127。值得继续证明的是原始身份到任务/映射/完成/目标唤醒的一致性、旧访问停止和清理后重授权的顺序，以及通知能授权的终态和回收副作用；已有字段不等于这些组合性质已经证明。

GR-T、AccShield、XpuTEE、BarriCCAde、ACSAC2024正式版及原库11项保留未完成；AEX-Notify从Sigy/Heckler的正式引用继续取源，尚未计入完成。整体任务active。

统一记录：两篇全文、图片页/固定代码有界静态阅读、书目与Notion全文核对｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无GPU/VM/RTL/模拟器/攻击run-id或新增PASS｜保留安全构造、公开实现和版本关系的证据边界。

## 接续精读：机密计算中断感知与时序隐私

完成[AEX-Notify（USENIX Security2023）](AEX_NOTIFY_USENIX2023.md)，19页正式PDF、72条参考文献及全部A/B/C附录；独立Notion页面86行全文回读通过，续研累计63/63页面通过。原库52/63、扩展46、合计98。它是SGX中断侧信道支撑，不能作为新的CCA GPU实现或GPU事件认证协议。

解读AEXNOTIFY/ERESUME/EDECCSSA恢复入口、CTD恒时解码、R/W/X预触发、可重启原子stub和隐藏指令进展。明确仅阻断确定性精确single-step，仍保留页粒度/嘈杂侧信道及未支持指令；98%为106个二进制静态覆盖，0.4%为假定中断频率的摊销估计，p的n次方不是任意部署的完整攻击上界。

固定后来Intel顶层3ab6a6bdb97adc76f690c0083c618bb98992fde7及SDK gitlink73ae8ba0140f9295ef62245897c578c76c289341，完整1162/3894项tree、十项定向文件；阅读AEX API/handler链、exception分发、CTD主体/选定helper和预取汇编。与论文的72/120-byte预留区、C3调用位置、cache布局差异分开记录，fallback不当作原代码页执行权限已验证；未执行或认定新漏洞，没有把2026集成版当论文2023评估提交。

项目在已有native fence、cookie/epoch、GPUVM、认证队列和persistent IRQ127上，分别论证事件来源/目标/终态/回收以及时序观测隐私。可重启内存预取不能照搬为可重复GPU doorbell或任务提交；随机延迟、handler计数或可信入口本身不等于业务完成认证。可信ProxyRealm/SMMU与授权合成合法HPA Stage-1假设保持。

统一记录：正式全文/附录、固定后来SDK有界静态阅读和版本核对、Notion全文回读｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无SGX-Step/分析器/编译/攻击/硬件run-id或新增PASS｜原库11条及直接GPU/CCA候选未完成项保留，整体active。

## 接续精读：异构配置证明与中断时序机密性（第 27 批）

本批新增 [T-Edge（ACSAC 2024）](TEDGE_ACSAC2024.md) 与 [Nemesis（CCS 2018）](NEMESIS_CCS2018.md)，均已全文研读、独立本地文档、Notion 发布及全部非空行回读，分别核对 66/67 行。原库维持 52/63，新增独立解读增至 48，合计 100；续研全文比对累计 65/65 页面通过。合计包含技术资料、版本增量与相邻支撑工作，不是 100 套 CCA GPU TEE 架构。

T-Edge 沿 NUS 作者出版清单取得 13 页接受稿，核对 37 条参考文献、正式 DOI/作者/131–143 页。固定完整 144 项 artifact 树，12 份文件下载，11 份全文静态读取及 block-design 定向读取。单租户 TrustZone/FPGA 设备配置与信任建立，不能替代多 Client GPU 任务隔离；公开演示的单分区测量、派生种子与 nonce-bitstream 签名不冒充论文概念的整启动报告、临时密钥和 DH 通道。ProVerif 为作者声称，公开稿/完整树未取得可审查模型、查询或验证输出；签名前准备内容与已生效配置分别分析，敏感 debug 日志保留实际启用条件。

Nemesis 沿论文 artifact 的真实作者链接取得 18 页全文，核对 80 条参考文献与附录 A/B/C。固定完整 159 项树和 SGX-Step gitlink，13 份文件静态研读。CPU IRQ 延迟和可中断次数的泄漏，保留重构旧 BSL、复制 Zigzagger 片段、重复 SGX 输入和校准条件；noiseless single-step 不等于计时无噪声。公开 debug 标签、PMD/PTE 差异、Host ACCESSED 日志与历史 parser、场景宏差异及裁剪图示均限定范围，没有执行攻击或确认 CCA/GPU 漏洞。

对项目的增量是关联现有可信服务身份、设备配置代次、任务终态和安全回收，并分别定义中断完整性与时序允许泄漏。已有 RMM 身份、GPUVM、认证队列、私有快照、native fence、cookie/epoch、persistent IRQ127 保留为基础；签名/真实 fence/ACK/epoch 各自语义不同，不自动等于设备已停止旧访问。

GR-T、XpuTEE、BarriCCAde、AccShield 和异构设备 ACSAC 2024 正式版等未完成项继续保留；元数据、相关旧稿和 artifact README 不计正式版全文完成。原库 11 条仍待研读，整体任务 active。

统一记录：论文全文/固定代码静态研读及 Notion 全文回读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件/ProVerif/攻击 run-id 或新增 PASS｜两篇保留，后续设计待实现验证。

## 接续精读：可信 ATS、服务预算与版本新鲜性（第 28 批）

本批完成 [MOAT](MOAT_ACSAC2026.md)、[Aion（CCS 2021）](AION_CCS2021.md) 和 [MGX（ISCA 2022）](MGX_ISCA2022.md)，各有独立 Notion 文档与完整非空行比对，分别 67/70/59 行。原库仍为 52/63，新增独立解读增至 51，合计 103；续研全文核对累计 68/68 页面通过。MOAT 直接关联 CCA/可信 I/O，Aion 与 MGX 分别为可信调度及加速器内存支撑，不能把三篇都计成新 CCA GPU 架构。

MOAT 沿 Shweta Shinde 主页取得 13 页作者稿和 48 条参考文献。主页标为 ACSAC 2026，PDFExpress 元数据为 2026-10-22；截至研读日会议尚未来，未取得正式 DOI/页码，不冒充已核对最终 proceedings。重点是 IOMMU 授权与 ATS 访问的等价参照、每设备/PASID 密钥、完整范围检查、AAC 续发与撤销切换、受保护故障原因。论文域内设备/OS 可信前提不能用于删除本项目跨 Client 权限检查；密钥失效不等于旧 DMA 排空。公开 org/user repo API 均为空，未取得匹配实现，refresh 并发/晚到响应/新旧 AAC 使用等仍需补证，不声称新漏洞。

Aion 阅读 16 页作者全文、41 条参考文献及附录 A/B，固定 main 提交 13a990b3278e5363a4a3ebdc0f6eecd92d84823c、完整 753 项树和 14 份定向文件。硬件有限原子期、可信 timer/IVT、pending IRQ 先于恢复、有限准入与 scheduler WCET 支撑 CPU 激活上界；6920 cycles 属第一任务，15 个同期限任务中最坏最后任务为 46,750 cycles。评估安全关闭选项、周期入口中注释掉的 scheduler caller 检查、返回 IRQ TODO 与时间溢出限制分别记录；未执行模拟或攻击，未把 CPU 服务保证当 GPU 任务进展。

MGX 阅读 17 页 arXiv v2、96 条参考文献及准确 ISCA DOI。可信片上 VN 与粗粒度 MAC 是组合优化，依赖每次同地址写入 counter 唯一及读取端当前 VN 权威；重启换钥、状态回退与物理地址复用不能省略。SCALE-Sim 没有模拟训练 weight update，GACT 仅 tile 子集/VN-only、H.264 仅功能、CHaiDNN 成本预期均保留。未取得确认匹配源码；不得把作者模拟成本当项目 GPU/glmark 实测。

对项目仍保持 RMM 认证原 Client、可信 ProxyRealm/SMMU、建图授权软件 IPA→HPA 合成受保护 Stage-1，以及 GPUVM、私有快照、native fence、cookie/epoch 与 persistent IRQ127。可继续形成三项组合论证：优化映射受当前授权持续约束；中断与错误处理成本纳入服务预算；撤销完成、DMA 静止和页再授权按顺序分别建立证据。现有字段不自动证明组合性质，也不需要重复构建新 token 框架。

CSF 2020 可中断 enclave 形式化隔离、TNPU（HPCA 2022）及 GuardNN（DAC 2022，已核 arXiv 元数据、未取得全文）列为后续引用链，不计完成。GR-T、XpuTEE、BarriCCAde、AccShield、异构设备 ACSAC 2024 正式版和原库 11 项继续保留未完成；整体 active。

统一记录：三篇全文/固定定向代码或公开材料研读及 Notion 全文回读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件/模拟器/RTL/攻击 run-id 或新增 PASS｜保留版本、信任前提和未核验并发路径。

## 接续精读：受限设备接口与持续配置保护（第 29 批）

本批完成 [GuardNN（DAC2022）](GUARDNN_DAC2022.md) 和 [Confidential Computing with Heterogeneous Devices at Cloud-Scale（ACSAC2024）](HETERO_CLOUD_SCALE_ACSAC2024.md)，均独立写入本地和 Notion，并逐非空行回读比对，分别 59/68 行。续研累计 70/70 页面全文比对通过；原库维持 52/63，新增解读 53，合计 105。数量包含技术资料、版本增量和支撑文献，不是 105 套 CCA GPU TEE；原库仍有 11 条未完成，整体 active。

GuardNN 完整阅读 7 页 arXiv v2 及 34 条参考文献，核对正式 DAC2022 DOI。其受限 ISA 将机密性和完整性分开，Host 提供读 VN 不等于当前版本权威，SignOutput 需要与预期任务比较。FPGA 主要实现 GuardNN_C，缺所需安全 bitstream 证明；CI 性能另由模拟评估。正文 1.05%/1.07% 与归一化倍率口径差异、单 AES/多 AES 资源及会话建立/签名成本分别保留，未确认匹配公开 artifact。

Cloud-Scale 正式对应作者 PDF 此前受阻，本批沿原始链接完成分段下载，完整研读 15 页及 90 条参考文献。它与已有 2022 早期稿为同一架构的版本沿革；硬件数据面、FPGA 控制面和应用评估不能与旧软件 SC 数字混用。本批正式条目已完成，不再维持“正式全文未取得”的最新状态；此前阶段记录作为历史保留。

Cloud-Scale 的非 TEE 设备仍整设备独占，不能代替项目多 Client GPUVM 隔离。重点是实际 job 归属、启动后配置持续安全和复位后再分配。认证加密不能直接推出 IRQ 原因/目标/任务终态可信；1024 项 ERT、2236 NPU 带宽估算和部分表格算术差异，以及真实应用、trace/模拟、综合和 SW-TPM 功能证明的范围均明确登记。

项目继续保持 RMM 认证原始 Client、可信 ProxyRealm/SMMU、建图授权软件 IPA→HPA 合成受保护 GPU Stage-1，以及已有 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和 persistent IRQ127。进一步论证持续配置授权、合法提交到实际执行的关联、真实终态到输出可见再到完成发布的顺序，以及超时/断连/reset 后旧访问终止与页再授权条件；不新增重复 token 框架，也不把验证义务说成已确认代码漏洞。

后续已经取得 CSF2020 的 arXiv:2001.10881v1 扩展全文，2020-01-29，49 页，1,222,696 字节，SHA256 99d304288f71f66e6ebdc42d5322c5784e85d522462ff4ee6f26cefdbd3f2ba1。只核对首页、版本和全文提取，尚未顺序完成技术正文与证明附录研读，不计完成。15 页会议版、49 页 extended version 与后续 77 页期刊扩展严格区分；后者也未计完成。

GR-T、XpuTEE、BarriCCAde、AccShield、TNPU 及原库未完成项继续保留。统一记录：两篇全文/书目/公开材料静态研读及 Notion 全文回读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件/FPGA/RTL/模拟器/攻击 run-id 或新增 PASS｜材料及证据范围保留，整体研究继续。

## 接续精读：可中断隔离的形式化参照与证明边界（第 30 批）

完成 [CSF2020 可中断 enclave 隔离](INTERRUPTIBLE_ISOLATION_CSF2020.md)，完整阅读 arXiv:2001.10881v1 的 49 页、45 条参考文献及附录 I/II/III 全部规则、引理和反向翻译算法。独立 Notion 文档 73 个非空行回读通过，续研累计 71/71 页面全文核对通过；原库仍为 52/63，扩展 54，合计 106。它是 CPU 中断机密性支撑，不计为新增 CCA GPU 架构；15 页会议排版与后续 77 页期刊扩展没有冒充已读材料。

论文用全抽象性保存无中断基准的上下文等价，而不消除基准已有的端到端时间泄漏。双重 padding 同时约束进入与恢复，还需保护备份、禁止受保护执行改变 GIE、限制非保护内存/I/O 和再入。每完整中断片段额外 17 cycles 不含 ISR；shadow 与 padding 总面积增加约 20.98% registers / 5.24% LUT，均为作者小型 FPGA 原型口径，不推算本项目性能。

固定晚于论文的 nemesis 提交 7c7d7fa9360439360d1eff0d26135c3d93a4b846，完整 1489 项 tree、16 文件 blob/长度核验，11 份完整和 5 份定向静态阅读。IRQ 聚合边沿与其他异常源、padding 周期记账、busy 备份生命周期、GIE/非保护访问/再入约束、多模块与调试范围作为证明到 RTL 的待核对项；没有运行仿真、攻击或声称发现可利用漏洞。手写证明不当成已机器验证 RTL，最终定理引理编号方向差异保留为编辑问题。

项目继续保持可信 ProxyRealm/SMMU、RMM 原始 Client 身份与建图授权合成合法 HPA Stage-1，以及 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和 persistent IRQ127。研究增量是明确完成时间/通知次数的允许观察，并把任务身份、真实终态、输出可见、可信发布和安全回收写成有阶段区分的规范；折叠 fence/批量唤醒等优化相对该规范检查，不增设重复 token 框架。透明中断定理不替代 GPU 完成认证、公平性或 DMA 静止证明。

GuardNN 候选元数据中遗留的“正式书目及全文待完成”说明已修正，与第 29 批实际完成状态一致；历史批次正文继续保留。GR-T、XpuTEE、BarriCCAde、AccShield、TNPU 及原库 11 项仍待完成，整体 active。

统一记录：49 页完整论文/证明附录、固定代码有界静态研读与 Notion 全文回读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件、RTL、模拟器、攻击 run-id 或新增性能 PASS｜论文保留，证明到实现和项目迁移待验证。

## 接续精读：NPU 数据版本与按上下文保护优化（第 31 批）

本批完成 [TNPU（HPCA2022）](TNPU_HPCA2022.md) 与 [Tunable Memory Protection（ICCD2022 短文）](TUNABLE_NPU_ICCD2022.md)，各自形成独立本地与 Notion 报告，全文非空行回读分别核对 64/49 行，续研累计 73/73 页面通过。原库仍为 52/63，新增解读 56，合计 108；两篇是相邻 NPU TEE 架构/内存机制，不包装为两套 CCA GPU 共享实现。

TNPU 取得作者出版页直接链接的 15 页全文，全部 60 条参考文献及 22 页报告幻灯片完整阅读，正式 DOI/作者/229–243 页核对。EEPCM 的实际物理页归属校验与可信 tensor/tile VN 内容新鲜性分开，128MB 元数据区域仍有完整性树；XTS 与 64-bit MAC 不与 CTR 或 128-bit 认证强度混用。Tile merge 条件、CPU 不可缓存接口、版本/重启/页复用和发布屏障缺口明确记录，未确认为漏洞。

TNPU 的 SCALE-Sim 内部扩展、Gemmini 交互模型和商业参数参考不当成真实安全硬件实现；单 NPU、同模型多 NPU、端到端模拟及面积功耗估计分开。Small 端到端聚合均值不能直接复算正文 8.2% 的限制保留，无逐 workload 原始数据，不擅自修正。幻灯片 0.14KB 的 tensor-only 版本与实际 tile 管理 1.3KB 也分开。

ICCD 短文 4 页及全部 10 条参考文献完整阅读，正式 DOI/不同作者顺序/105–108 页核对。它保留硬件树，采用 protected PT、每 context 虚拟完整性树、整体 chunk counter、只读 CTR1 和 2KB SRAM 通道，不是 TNPU 无树版本的简单改名。数据 PA 分散与 counter 区连续、每 context 固定粒度与未来逐页扩展分别说明；13.5% 是相对安全基线的执行时间减少，不是精确 1.135× speedup。

GitHub TNPU 查询 38 项、短文精确短语查询零项、casys-kaist 60 项公开 repo 列表无下一页，未确认匹配安全扩展 artifact；同组 mNPUsim2023 和通用 SCALE-Sim/Gemmini 不代替本文实现。无源码审计、仿真、构建、攻击或硬件运行声明。

项目保持可信 ProxyRealm/SMMU、RMM 原始 Client、建图授权软件 IPA→HPA 合成合法受保护 Stage-1，以及 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和 persistent IRQ127。增量是明确只读/批处理/映射复用优化的必要条件，并把当前授权、输入内容、真实终态、输出可见和撤销后复用关联起来；VN 与协议 epoch 不等价，不为静态 DNN 条件另建通用 GPU 版本框架。

GR-T、XpuTEE、BarriCCAde、AccShield、CPU–FPGA Salus 及原库 11 项继续待完成；TNPU 的历史待研读状态由本批覆盖。整体 active。统一记录：两篇完整论文/参考文献、作者幻灯片及书目/公开实现线索研读、Notion 全文核对｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件、模拟器、攻击 run-id 或新增性能 PASS｜材料与迁移边界保留。

## 接续精读：自动版本与 XOR 聚合完整性的边界（第 32 批）

完成 [Securator（HPCA2023）](SECURATOR_HPCA2023.md)，从作者 IIT Delhi 官方出版页取得 13 页完整 PDF，全部 49 条参考文献、附录 Tables VIII/IX/X 完整阅读，核对正式 DOI/作者/1127–1139 页。独立 Notion 报告 73 个非空行回读通过；续研累计 74/74 页面全文比对通过，原库仍为 52/63、新增 57、合计 109。它是 NPU TEE/内存支撑，不计为新增 CCA GPU 共享实现。

分析三元组描述的自动 VN 与层级 XOR MAC：版本表被 FSM/参数/执行进展约束替代，安全状态没有消失。对正文只读重复读取规则，合法 [x,x,x] 与 [x,y,y] 的 MACIR 相同、首次 MACFR 也正确；这是固定身份/VN、反复读不可信内容且无额外逐读检查等条件下的代数反例，不需要 hash 碰撞或恢复密钥。没有匹配实现，没有执行攻击，不写成已确认漏洞。被引用 Bellare XOR MAC 原始论文未在本轮完整阅读，不把引用当成本构造的归约证明。

跨层多输出/skip 的状态保留、最终 sink 的认证端点、验证前副作用及结果发布屏障分开分析。Secret-prefix SHA256 不误称为 HMAC，也不以固定长度输入直接宣称通用长度扩展可利用；密钥拼接、CTR lane/溢出等保留实现规范边界。与现有私有快照、native fence、cookie/epoch 和 IRQ127 的联系是“每次使用什么内容”和“哪个可信终态可授权发布/回收”，不叠加重复 token 框架。

内部模拟、CHaiDNN/ZCU102 PoC 和 28nm 综合再缩放 8nm 分开；PoC 明确没有安全异常告警。20.56% 吞吐/overhead 表述差异、四 AES 与面积汇总对应单 AES 的条件性算术差异、GuardNN 75%/64% 的不同位置数字保留。Layer widening 只作性能扩展实验，不宣称 MEA 泄漏被证明消除。背景 TNPU128KB 与原文128MB 等差异不传播到已有报告。

官方软件页无 Securator 条目；名称查询 total4/incomplete、实际仅1个旧空仓库，不能说全部四项审查完；组合精确查询返回0且完整，未确认匹配源码。通用 CHaiDNN 不替代安全扩展。原库 GPU 论文的两个 Northeastern 作者站点本轮 DNS 失败，Google 搜索网络不可达；不重试相同失败代替独立进展，相关条目仍未完成。

项目继续保持 RMM 原始 Client 认证、可信 ProxyRealm/SMMU、建图授权软件 IPA→HPA 合成受保护 GPU Stage-1，以及 GPUVM、认证队列、私有快照、native fence、cookie/epoch、persistent IRQ127。聚合优化需要定义集合/次数/顺序/每次使用内容分别要证明什么，并把结果检查与发布、撤销与旧访问静止的顺序写清楚。

统一记录：13 页完整论文/49 条参考文献/附录、正式书目与公开代码线索研读、Notion 全文核对｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件、模拟器、RTL、攻击 run-id 或新增性能 PASS｜条件性反例、材料缺口与迁移边界保留，整体 active。

## 接续精读：不可信 GPU 的结果验证与一次性输入保护（第 33 批）

完成 [Slalom（ICLR2019）](SLALOM_ICLR2019.md)，19 页 arXiv:1806.03287v2、参考文献及附录 A–H 全部阅读，作者出版清单确认 oral。独立 Notion 报告 61 个非空行回读通过；续研累计 75/75 页面核验通过。原库仍为 52/63，新增 58，合计 110；不将包含资料、版本报告和支撑工作的总数称为独立 CCA GPU 架构数量。

CPU TEE 验证不可信 GPU 的线性层，非线性留在可信端；秘密检查向量与一次性盲化材料分开。模型隐私、数值语义、联合/条件错误概率、长期尝试预算，以及原文减号误差项分别分析，不宣称据文字问题推翻整套协议。该路线直接关联 GPU/TEE，但不同于项目可信 ProxyRealm 控制下的通用设备隔离。

固定后来 2021 公开提交，完整 768 项树、17 文件长度/blob 核验，并做有界静态阅读。作者明确性能 PoC：零密钥/种子、外送 r、外部计算 z、公开固定检查向量、MAC 失败只打印及部分检查 TODO；这些不能继承协议证明，不当作新生产漏洞发现。两种模数、ResNet 隐私缺正确解盲因子、未训练模型、fused 结构变化、图文数字、在线/离线成本与加权能效估计保留。

项目保持 RMM 原始 Client 认证、可信 ProxyRealm/SMMU、建图授权合成受保护合法 HPA Stage-1，以及 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和 persistent IRQ127。区分访问授权、真实任务终态和计算结果正确性，可选结果检查在发布成功前完成，验证失败进入错误终态；不因算法路线新增重复 token 框架。

发布最终审计确认父页旧正文/111 个子页面完整保留，新增后 112 个子页面，没有截断、未知块或缺失内容。原库 11 项及 GR-T、XpuTEE、BarriCCAde、AccShield 等候选仍未完成，整体 active。

统一记录：完整论文/附录、固定性能代码有界静态研读与 Notion 全文回读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、攻击、编译或模拟 run-id/新增性能 PASS｜Slalom 保留，原型与迁移边界明确。

## 接续精读：不可信 GPU 的模型隐私与 CCA 部署边界（第 34 批）

完成 [ShadowNet（IEEE S&P2023）](SHADOWNET_SP2023.md) 和 [GuaranTEE（EuroMLSys2024）](GUARANTEE_EUROMLSYS2024.md)，独立 Notion 报告分别 53/46 个非空行回读通过，续研累计 77/77 页面全文核对通过；原库 52/63，新增 60，合计 112。ShadowNet 是 GPU/TEE 协作，GuaranTEE 是 CCA ML 部署支撑，不把二者都计作 CCA GPU 隔离架构。

ShadowNet 完整阅读 17 页 arXiv v4、75 条参考文献及附录 A/B，核对正式 DOI/页码；固定官方后续提交、完整 161 项树及 8 份文本。它保护模型隐私，明确不保证推理完整性。候选集/后验等概率的条件、黑盒安全猜想、depthwise 缩放与排列的不变量、一次性 mask 及量化正确性分别分析，没有执行攻击或宣称推翻整套设计。官方仓库说明 RAID 损坏导致核心源码丢失，部分镜像/TA/AAR 不能当作完整安全源码审计；GPU 增益、额外成本、mask 加载和累计 TA 优化不混算。

GuaranTEE 完整阅读 9 页 arXiv v1 及 55 条参考文献，固定官方部署提交、完整 57 项树和配套 TFlite-CCA 根级树及 6 份文本全文。PDF DOI/ISBN 占位，最终出版方书目未核实；HES/远程证明、TLS 模型供应与可信 GPU 均未在 CPU FVP 原型实现。共享 9p 信号/文件/输出没有建立恶意多 Client 通信保证；公开模型预置不等于秘密供应协议。1.6274 是指令倍率、增加约62.74%，模拟墙钟不是真实 Arm 延迟；镜像大小与 RAM 同时变化不能单因果归因。

两篇与项目的联系在于明确三个层次：模型/服务镜像受到保护，Client 设备访问得到授权，以及一次任务的输入、实际执行、结果与完成可信关联。继续沿已有 RMM 身份、ProxyRealm/SMMU、授权合成合法 HPA Stage-1，以及 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和 persistent IRQ127 建立连续状态规范，不另造重复 token 框架。真实 IRQ 不自动验证数值结果，启动证明也不自动证明单次推理或撤销完成。

继续追踪 TEESlice、SOTER、DarkneTZ 等直接引用；未取得全文、未独立精读/发布核对前不计完成。原库 11 项和 GR-T、XpuTEE、BarriCCAde、AccShield 等继续保留待完成，整体 active。

统一记录：两篇全文/固定公开文本静态研读及 Notion 全文回读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、FVP、攻击或编译 run-id/新增性能 PASS｜保留版本、猜想、缺失源码及未实现证明/可信 I/O 边界。

## 接续 batch35：SOTER 与 TEESlice 的模型层保护和结果发布

完成 [SOTER（ATC2022）](SOTER_ATC2022.md) 与 [TEESlice（S&P2024）](TEESLICE_SP2024.md)，独立 Notion 页面分别 54/55 个非空行回读通过；续研累计 79/79 页面比对通过。原库仍为 52/63，新增 62、合计 114。这是独立报告数量，含技术资料、版本增量和支撑论文，不是 114 套 CCA GPU 架构。

SOTER 完整阅读官方 16 个物理页（含封面）及 72 条参考文献，固定官方后续提交、完整 8787 项树和 8 份选定文本。区分缩放齐次性与组合指纹需要的可加性、模型参数变形与语义加密、随机扰动检测与任意恶意逐次结果保证。所选 VGG 路径的常量尺度、GPU 参考输出、固定挑战、单元素比较和仅打印失败是有限静态核对事实，没有执行攻击，也没有扩展成所有版本的漏洞结论；Table3/4 算术差异保留。

TEESlice 正式标题、作者、DOI 和 3327–3345 页码核对；实际完整阅读官方 arXiv v1 HTML、115 条参考文献及附录 A–L。975335 字节原文 SHA256 固定，同 ETag 首尾恢复；PDF 跨 ETag 不一致被拒绝，完整 GET 超时的部分响应也不冒充完整 PDF。固定后续 artifact、完整 3217 项树和 17 份选定文本，明确 insecure 性能 PoC、种子/密钥/拒绝语义等未闭合证据，不把文件名当成 Freivalds 完成证明。

TEESlice 的公开骨干冻结与私有训练增量原则可用于思考模型/adapter 对象来源；black-box 比较、MIA、精度与统计显著性分开。其 ShadowNet 所选无 λ 攻击与部分行 shuffle 不等于完整 v4 构造，不能沿用约95%恢复率宣称通用攻破。BART/GLUE 不是多租户自回归 LLM serving。相关结果均为作者实验，未作项目性能迁移。

两篇把主线进一步明确为：完成通知、实际任务终态、结果可消费和设备页可复用分别建立条件。继续接受既定 RMM/ProxyRealm/SMMU 与合成 Stage-1 假设，复用 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和持久 IRQ127；不增设重复身份框架。它们是“不可信 GPU 上模型保护”的补充相关工作，不能代替 PORTAL/CAGE/ACAI 或可信中断研究。

原库剩余 11 项及 GR-T、XpuTEE、BarriCCAde、AccShield、CPU–FPGA Salus 等未完成项继续保留，整体 active。统一记录：全文/定向静态研究及发布核验｜glmark 未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、构建、攻击或模拟 run-id｜保留完整 HTML 与 PDF 获取失败、原型及版本边界。

## 接续 batch36：Arm TEE 模型入口与多 enclave GPU 流水线

完成 [DarkneTZ（MobiSys2020）](DARKNETZ_MOBISYS2020.md) 和 [Serdab（CCGrid2020）](SERDAB_CCGRID2020.md)，独立 Notion 页面分别 53/56 个非空行回读通过，续研累计 81/81 页面全文比对通过。原库 52/63、新增 64、合计 116 篇独立解读；含资料、版本与支撑工作，不是 116 套 CCA GPU 架构。

DarkneTZ 全文 13 页及 68 条参考文献，正式书目核对；官方后续代码完整 193 项树、14 份选定文本长度/blob 核验。性能原型明确只用 CPU；MIA 经验结果、可见 logits 的条件性重算、原始导出/训练/权重命令的可信策略及加密版本差异分开记录。末层小开销、训练开销和一次性多层推理最高约 10 倍不能混成统一结论。完整单响应 PDF 与六段相同，但远端 ETag 不等于实得 SHA256；保留真实获取边界。

Serdab 全文 10 页及 29 条参考文献，正式书目核对；未确认编排核心 artifact。固定论文引用的 TF Trusted 依赖，完整 37 项树、7 份文本全文和 blob 核验，不归为 Serdab 核心实现。全 enclave 加密流水线与明文低分辨率特征交 GPU 有不同隐私条件；人工不可辨识不等于机器不可恢复。最高 4.7 倍来自增加资源后的 10800 帧整批完成时间，不能写成单帧或项目收益；诚实结果假设、重分割在途状态与依赖信道配置的证据限制保留。

两篇补充相关工作和可信入口分析，不替代 PORTAL/CAGE/ACAI 的设备保护或可信中断研究。继续接受既定 RMM/ProxyRealm/SMMU 与合成 Stage-1 假设，复用 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和持久 IRQ127；后续核验所有可信入口的允许操作、阶段完成与原任务的绑定，以及取消/reset 后旧结果与旧页的终止条件。

原库 11 项及 GR-T、XpuTEE、BarriCCAde、AccShield、CPU–FPGA Salus 等仍未完成，整体 active。统一记录：全文/定向静态阅读及发布回读｜glmark 未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、编译、攻击或模拟 run-id｜保留原型、依赖范围、性能与隐私假设边界。

## 接续 batch37：补齐 BarriCCAde 与可信 I/O 条件可用性

完成 [BarriCCAde（SysTEX2024）](BARRICCADE_SYSTEX2024.md) 与 [Conditional Network Availability（SysTEX2024）](CONDITIONAL_NETWORK_AVAILABILITY_SYSTEX2024.md)，独立 Notion 报告分别49/57个非空行回读通过，续研累计83/83页面全文比对通过。原库仍为52/63，新增66，合计118篇独立解读；含技术资料、版本及支撑工作，不是118套CCA GPU架构。

本轮沿BarriCCAde作者官方页面追到SysTEX2024新官方站点及日程，取得此前一直缺失的BarriCCAde全文。7页正文及25条参考文献完整阅读，配套42页演讲的全部提取文字已读。RMM同步/过滤、ELF/DWARF语义、异常中介和eBPF策略分别分析：已演示dummy driver，真实驱动及性能仍TBD；2195新增SLOC中1722为既有验证VM，473行仍属新增可信代码。65%–99%Native是相关LVD结果，不是本篇实测。未确认匹配核心artifact，不把CCX或TrustLeech当成BarriCCAde。上文“BarriCCAde全文待取得”均为历史状态，现已完成本轮独立解读和发布核验。

CNA完整阅读官方9页及44条参考文献，固定作者明确链接的2026后续提交。整库递归树66527项且截断，如实保留；另取完整4项根树及85项src子树，20份核心文本长度/blob核验并全文静态阅读。首次raw下载失败保留，改用内容寻址blob接口补齐。条件可用性不等于公平份额、截止期、包认证或可信IRQ转发；SW安全timer轮询、NW NIC IRQ、队列满时双方丢弃和boot/reset连续保护分别说明。RAM范围相交/包含差异、MMIO选择性环控制TODO、固定IPv4/端口分类和启动接管限制均为有界静态证据，没有执行攻击或认定全版本漏洞。

项目继续使用既定RMM原始Client身份、ProxyRealm/SMMU和授权软件IPA→HPA合成受保护GPU Stage-1，并复用GPUVM、认证队列、私有快照、native fence、cookie/epoch和持久IRQ127。两篇增量支持可信入口的操作/状态约束，以及“可伪造性、目标归属、新鲜度、条件进展、公平性”的分别论证，不另造身份token框架，也不以测试硬件否定目标假设。

直接候选追踪同时取得SEGIVE正式DOI/书目，但未得全文；ZeroKernel作者网站完整206项树和同名仓库查询未得匹配全文；Cinch官方长GET退出28、仅78675字节，range探测也超时，部分文件明确改标partial。没有把这些条目计完成。原库11项及GR-T、XpuTEE、AccShield、CPU–FPGA Salus等仍待完成，Cinch为新增待取得全文的可信I/O候选，整体active。

统一记录：两篇官方全文/演讲及定向静态代码研究和Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、构建、下载代码执行、攻击或模拟run-id｜保留全文获取失败、递归树截断、原型与可用性前提。

## 接续 batch38：可信服务管理、TEE 驱动隔离与 FIQ 回调

完成 [duet（SysTEX2024）](DUET_SYSTEX2024.md) 与 [LDR（NDSS2024）](LDR_NDSS2024.md)，独立Notion报告分别49/55个非空行回读通过，续研累计85/85页面比对通过。原库52/63、新增68、合计120篇独立解读；含技术资料、版本和支撑工作，不是120套CCA GPU架构。

duet完整阅读会议官方9页稿及52条参考文献，正式IEEE页码436–442与公开稿排版差异明确。固定作者仓库提交及完整36项树，11份选定文本长度/blob核验并全文静态阅读；API403与raw超时保留，codeload固定归档恢复3份文件。控制器独占SSH、管理日志、rootfs/HCL/MAA信任、模式转换和证明/信道绑定分别分析。清理TODO、预期MRENCLAVE检查注释、证明失败只warning、默认HTTP、状态返回/退出码/并发和JWT仅解码打印等均是限定文件范围的静态事实，未执行攻击，也不声称完成云依赖或最终manifest审计。论文没有GPU实验或性能测量。

LDR完整官方18页、80条参考文献和附录A–D，重点展开附录B中SW FIQ→monitor→NW callback→monitor→SW恢复的完整路径。区分专用安全核、gate/callsite CFI、参数授权和多Client完成归属；NW启动可信、DMA/DoS排除及返回值清洗尚属扩展条件均保留。6驱动/7设备、OV5640留NW、RPC/CPC总时延和IED增量、Neon主文与无Neon附录、MyTEE假设性性能上界分开。论文确认作者仓库，固定提交及83行README网页读取；treeAPI403和raw超时，核心源码未审计。GPU支持、AArch64 watchpoint隔离均未在当前原型验证。

两篇支撑管理权限与异步跨域调用的边界，不能替代PORTAL/CAGE/ACAI的设备保护。继续使用RMM原始Client身份、ProxyRealm/SMMU、授权建图合成GPU Stage-1和其他设备Stage-2，并复用GPUVM、认证队列、私有快照、native fence、cookie/epoch与持久IRQ127。研究配置更新时旧任务/映射撤销，以及可信中断处理中外部回调不改变任务归属；不引入重复身份框架，不以模拟硬件限制否定目标假设。

Cinch从Walfish作者论文列表定位新的完整PDF来源，取得18页、279726字节，SHA256 `0b1842d0efb01433896254e89a94623058952a3bb8294c851d7f2f53c8463a26`。仅验证解析及首页身份，尚未全文精读/发布，不计完成；上批“仅部分PDF”为已被新获取事实更新的历史状态，原失败仍保留。原库11项及GR-T、XpuTEE、AccShield、CPU–FPGA Salus等继续待完成，整体active。

统一记录：两篇官方全文与限定静态材料研读及Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、构建、云部署、攻击或模拟run-id｜保留获取失败、未审计核心实现、原型/管理及中断信任边界。

## 接续 batch39：恶意外设中介、TrustZone 最小驱动与受约束中断等待

完成 [Cinch（USENIX Security2016）](CINCH_USENIX2016.md) 与 [Driverlets（EuroSys2022）](DRIVERLETS_EUROSYS2022.md)，独立Notion报告分别60/63个非空行完整回读通过；续研累计87/87通过。原库52/63、新增70、合计122篇独立解读，含技术资料、版本与支撑工作，不是122套CCA GPU架构。

Cinch完整阅读作者18页稿及155条参考文献，无附录，会议内嵌BibTeX核对作者/页码；保留此前partial PDF和失败请求。展开red/Gateway/blue、控制器DMA/中断隔离、策略状态机、TLS适配器身份与固件信任的区别。首次16/18含12项已知CVE assertion、随机10k并未攻陷baseline、第三轮19/23 rematch及4项剩余多态攻击、人工植入bug和VFAT误报均保留；USB吞吐/资源和ping RTT不当作GPU中断成本。没有确认匹配核心artifact，未声称实现已审计。

Driverlets完整阅读作者明确链接的arXiv v2共17页及81条参考文献，无附录；正式EuroSys书目/DOI/300–316页另行核对，不冒充最终ACM PDF。分析独占设备、可信录制/gold driver/固件、状态变化序列的条件性论证、关闭IRQ合并/并发/runtimePM、逐模板复位与重试；transaction不扩展为外部写回滚或DMA静默证明。MMC/USB/camera的覆盖、native/native-sync与宏/微基准、FPS/秒及Figure7单位差异分别解释。

两个作者关联早期候选仓库固定提交及完整46/2435项树，6份文件长度/blob核验并全文静态阅读。打印而未拒绝的分歧检查、被注释的reset、无限轮询、公共poll计数未初始化、DMA channel8与论文channel15不同，均限定为候选代码事实；未确认其最终论文对应关系，也未执行源码。没有完成S2E记录器、签名或完整IRQ实现审计。

两篇补充可信I/O与驱动边界，不能替代PORTAL/CAGE/ACAI。保持当前RMM原始Client身份、ProxyRealm/SMMU和授权建图假设；复用GPUVM、认证队列、私有快照、native fence、cookie/epoch及持久IRQ127。研究重点是不可变执行计划的授权连续性、IRQ到真实完成的检查、reset影响域、重复外部副作用和最后DMA到页回收的衔接。PLAN_REGISTER/PLAN_EXEC不是MMIO轨迹重放，不引入重复身份框架。

Cinch此前仅取得全文的历史状态由本批完成记录更新；原库11项及GR-T正式版、XpuTEE、AccShield、CPU–FPGA Salus等继续待完成，整体active。统一记录：完整论文与6份候选代码静态研读及Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、构建、下载代码执行、攻击或模拟run-id｜保留获取失败、artifact对应限制和设备独占/复位前提。

## 接续 batch40：补全原库 GPU 两方安全计算与依赖并行化

完成 [TGS-043｜GPU/CPU两方安全计算（ACSAC2013）](GPU_GARBLING_ACSAC2013.md)，作者明确链接的10页全文及25条参考文献完整阅读，无附录；作者页内嵌BibTeX、四位作者、DOI和169–178页核对。独立Notion报告70个非空行回读通过，续研累计88/88通过。原库由52增至53/63，新增保持70，合计123篇独立解读；不是新增123套CCA GPU架构。

分析HbC、每次容许一位谓词泄漏的1BM与完整恶意安全的差异；该论文是GPU加速密码协议，不是恶意Host下GPU TEE。展开PRF虚拟标签、全局R、XOR gate的V/P偏移、额外通信与不采用GRR的交换；整电路生成可并行，求值仍受层依赖、内存合并和传输制约。SHA1历史优化不作为现代部署建议，未给出新协议或实现精化证明。

约7500万gate/s对35万约214倍，与正文“三个数量级”不强行一致化；2.3倍/3倍GPU表述、不同电路/架构、引用CPU对照、100/50轮、单GPU、EC2 Xen未测开销、关闭分块及未完成PCF流水分别标明。通信/OT/完整协议未做端到端评价，生成吞吐不能替代求值或GPU完成通知性能。

没有确认匹配本文的公开artifact：作者页和PDF无明确核心代码链接，精确短语仓库查询命中无关图像编辑项目，gpuyao为0，候选账户查询422保留；不把JtR/PCF/SCAPI当本文实现，也不声称全网无源代码。本轮没有下载代码执行、编译或硬件访问。

同时取得并严格解析ShEF arXiv2103.03500v2（16页、1192704字节）与HECTOR-V arXiv2009.05262v3（13页、1332422字节），正式DOI/作者/页码核对，固定PDF哈希并登记pending。只检查身份和来源，尚未完整研读或发布，不计完成。原库TGS-047取得正式DOI与作者出版列表确认，但没有原文；TGS-006仍无独立公开全文新来源，均保持未完成。

当前原库余10项，GR-T正式版、XpuTEE、AccShield、CPU–FPGA Salus及新取得两篇继续推进，整体active。维持RMM原始Client身份、可信ProxyRealm/SMMU、授权建图和GPU Stage-1合成假设，复用GPUVM、认证队列、快照、native fence、cookie/epoch与持久IRQ127；区分设备完成、协议验证和双方输出一致性。统一记录：纯文献/来源研究与Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件或攻击run-id｜保留artifact缺口、部分图形提取限制和基准可比性边界。

## 接续 batch41：ShEF 的独立加速器 TEE、证明策略与运行期边界

完成 [ShEF（ASPLOS 2022）](SHEF_ASPLOS2022.md)，完整16页arXiv v2、105条参考文献及artifact附录A.1–A.8，正式书目核对。独立Notion报告全文非空行回读通过，续研累计89/89；原库53/63、新增71、合计124篇解读，含技术材料、版本与支撑研究，不是124套CCA GPU架构。

不可信Shell与制造商/供应商信任、设备/Kernel/bitstream/数据密钥分别论证；nonce证明新鲜度不等于运行期任务和reset后数据新鲜度。可修改region需可信计数，只有MAC不足以防重放。Ultra96完整启动证明与F1仅Shield实验分开，摘要122%、正文2.31倍及附录配置差异保留。

固定论文明确链接的2021-11-24提交，完整1659项树和10份blob核验；8文件全文、2文件定向片段，不把cache tag当MAC。验证器Kernel哈希allowlist TODO、报告缺bitstream哈希、调试密钥、局部加载边界与运行期认证调用链未闭合均限定为静态事实，未执行攻击。Zenodo元数据连接拒绝，不声称归档与GitHub对应性。

复用已有RMM身份、ProxyRealm/SMMU、GPUVM、认证队列、私有快照、native fence、cookie/epoch及持久IRQ127，补充证明到真实实例、结果发布及撤销后安全复用的连续条件。ShEF没有解决恶意多VM GPU完成中断归属。HECTOR-V仅取得全文的状态保持pending；原库余10项与直接候选继续推进，整体active。

统一记录：完整论文/附录及限定公开源码静态研读和Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件、下载代码执行、构建、云部署或攻击run-id｜保留协议/原型和性能可比性边界。

## 接续 batch42：HECTOR-V 的外设所有权、中断与撤销边界

完成 [HECTOR-V（ASIA CCS 2021）](HECTOR_V_ASIACCS2021.md)，完整13页arXiv v3和66条参考文献，无附录；正式DOI、作者和187–199页核对。独立Notion报告59个非空行回读通过，续研累计90/90；原库53/63、新增72、合计125篇解读，含支撑论文，不是125套CCA GPU架构。

分开分析普通设备IRQ按owner路由、专用withdraw中断清理和共享内存阻塞ACK；中断mailbox只是扩展建议。timeout清除ID不自动证明旧事务、秘密、pending IRQ和DMA已排空，reset提前通知也仅为可能扩展；这些是协议分析边界，不是源码漏洞或执行攻击。SM与SM owner、不可配置存储与可配置DDR、CFI状态/10位压缩ID/0通配、可信加载与密钥引导分别论证。

188cycles的claim、5498对5261cycles的1MB ACK、876ns内存和继承SCFP9.1%分开；SM446LUT不是整个TCB。未确认匹配artifact；宽搜索227项只取首30，精确组合0，候选作者20个仓库/lowrisc47分支/scfi1分支仅元数据，不当安全源码审计，DNS/404失败保留。

项目继续接受RMM身份、可信ProxyRealm/SMMU及授权Stage-1合成模型，复用GPUVM、认证队列、私有快照、native fence、cookie/epoch及持久IRQ127；补足停止提交、真实终态、旧事务处置、清理和重新授权之间的条件，epoch不代替DMA静默。HECTOR-V此前pending状态由本批更新；原库余10项及直接候选继续，整体active。

统一记录：完整论文/引用和有界来源研读、Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模拟/构建/攻击run-id｜未确认核心artifact及强制撤销保证保留。

## 接续 batch43：GIFT 的 GPU 用户归属、语义隔离与异步一致性

完成 [GIFT（2026预印本）](GIFT_ARXIV2026.md)，完整17页arXiv2608.25431v1及120条参考文献，无附录；四作者、日期和版本相互核对，未确认正式venue。独立Notion报告全文非空行回读通过，续研累计91/91；原库53/63、新增73、合计126篇解读，包含资料、版本和支撑研究，不是126套CCA GPU架构。

本文直接研究不可信LLM框架使用合法kernel读取错误用户KV的confused deputy，GIFT信任OS/VMM、GIFT-CC使用CPU/GPU TEE。5.6K Rust monitor是增量而非含Linux/CUDA的整个TCB；所有者segment、parameter标签、人工IFG、CUDA→C++/KLEE、29类规则及黑盒近似soundness限制分别分析。

先IFT检查再launch与后续IFT重叠既有GPU执行分开；导出前D2H等待、跨stream last-writer/readers和同步成功/scope、index-table副本与实际对象一致性是重点。token随机化加密不自动提供认证，错误owner只解密失败的强表述需更多证据；结果完整性、side channel、DoS排除。保留A800多GPU/H100单GPUCC、native/baseline-TEE、speculative10.7%/2.1%、IFT超过短kernel等条件，不将小开销当通用证明。

未确认核心artifact；两次GitHub组合查询0且未截断，候选作者404、定向OpenAlex超时保留，无源码审计/执行。项目继续接受RMM身份和可信ProxyRealm授权Stage-1合成模型，复用GPUVM、认证队列、私有快照、native fence、cookie/epoch及持久IRQ127；可选LLM规则用于共享服务内部用户语义，不强制任意shader静态IFT。页授权之后仍需保持对象、真实任务、输出和回收的归属连续。

原库余10项及GR-T正式版、XpuTEE、AccShield、CPU–FPGA Salus继续pending，整体active。统一记录：全文/120引用及有界来源研读、Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模拟/构建/攻击run-id｜保留预印本状态、规则soundness与失败/回收路径缺口。

## 接续 batch44：Hopper 性能指标与限定源码核验

完成 [Hopper GPU机密计算性能研究](HOPPER_CC_PERFORMANCE_ARXIV2024.md)，完整7页arXiv v4与17条参考文献，固定匹配仓库230项完整树及16份选定文本长度/blob核验和全文阅读；仓库PDF与本地PDF的Git blob hash相同。7幅嵌入栅格图已观察，图1b矢量未独立重建。独立报告55个非空行回读通过，续研累计92/92；原库53/63、新增74、合计127篇解读，非127套CCA GPU架构。

代码显示mean_itl实际是累计输出时长均值，TPS为每请求比值的均值；H200 QPS对应离线结果，非固定SLO在线容量证据。8B选定在线和离线命令有dummy权重/单CPU核，70B为bitsandbytes，1core/24core默认、过滤后的组间样本、非单调长度趋势和正文6TPS差异分别保留。不把统计问题扩写成所有数据无效，也不从低开销推出完整安全保证。

Performance of Confidential Computing GPUs已取得6页全文，CLOUD2024 readiness取得正式书目与IBM官方页但无足够全文，两者尚未完成独立发布，不计完成；GPU Taint Tracking获取超时及原库余10项、直接候选继续保留。接受RMM身份、可信ProxyRealm授权Stage-1合成假设，复用GPUVM/认证队列/快照/native fence/cookie/epoch/IRQ127，区分映射、执行、可信完成和通知代价。整体active。

统一记录：全文/有界公开源码/Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/攻击run-id｜SLO、逐请求完整重算及安全部署未验证。

## 接续 batch45：机密GPU多模型装卸、调度与完成语义

完成 [Performance of Confidential Computing GPUs（ICDCSW2025）](CONFIDENTIAL_GPU_SCHEDULING_ICDCSW2025.md)，完整6页arXiv v1、22条参考文献、无附录，正式DOI/五作者/237–242页核对；workshops不冒充主会。论文明确链接SINCERE，固定论文日期前2025-04-02提交，完整2756项树；14份blob长度/hash核验，6份源码/文档和2份CSV全文阅读，notebook77cell仅15/17/24定向，不执行；API403/raw超时后CDN按原Git blob核验，失败保留。

独立页面61个非空行完整回读通过，续研累计93/93；原库53/63、新增75、合计128篇解读，含资料、版本和相邻支撑工作，不是128套CCA GPU架构。模型常驻与频繁装卸区别、No-CC吞吐高45–70%反向不等于CC损失45–70%、SLA百分点、推理时间占比与硬件利用率分别分析。

原型入队ACK不等于完成，60秒客户端timeout与80秒SLA并存，Stop不排空、测量窗口及已完成CSV分母、队列搬移在GPU执行锁之外、预测Timer与最近batch取整均有边界；固定CSV的模型大小/卸载值与论文不一致，单列而不猜测原因。局部静态观察不扩写成已复现丢请求/攻击，也不据性能代价否定CC安全假设。

保持RMM原始Client、可信ProxyRealm/SMMU授权Stage-1合成假设，复用GPUVM/认证队列/私有快照/native fence/cookie/epoch/持久IRQ127。驻留优化服从对象归属和版本、在途引用与公平预算；入队、真实终态、输出发布、撤销和安全回收分别定义，epoch/Timer不代替DMA静默。原库余10项、GR-T正式版/XpuTEE/AccShield/CPU–FPGA Salus、readiness等仍待完成，整体active。

统一记录：全文/限定静态artifact/Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型运行/攻击run-id｜完整图点/原始数据重算/安全启动证明未验证。

## 接续 batch46：RealmEye 的 CCA 内省与可信输出边界

完成 [RealmEye独立报告](REALMEYE_ARXIV2026.md)，完整14页arXiv2608.12822v1、43条参考文献，无附录；尚无确认正式venue。公开后续候选仓库固定提交、37项完整树及9个blob核验；README使用不同副标题和章节，OpenCCA原型与v1未来工作不同，作者身份和对应修订全文未证实，不将其冒充v1原始artifact。全文读取6个较小文本，大RMM文件/Host patch仅定向静态阅读，无构建或执行。

报告56个非空行完整回读通过，续研累计94/94；原库53/63、新增76、合计129篇解读，含资料、版本和支撑研究，不是129套CCA GPU架构。Notion父页面原有130个子页完整保留，现131个；旧正文逐行保留，计数和新增段落核验通过。证据为batch46-final-audit.json，整体active。

区分真实寄存器与可信语义根、单REC暂停与全VM/DMA快照、周期扫描与时序隐私、加密与认证会话。候选OpenCCA GCM后仍明文写exit.gprs[0]，固定PSK/salt重启nonce、未接入正常请求的认证诊断、全局周期/trap状态、单Realm/首vCPU选择、命令ABI与8字节结果/整页缓冲差异分别记录，均为限定静态观察，不声称复现攻击。

继续采用RMM原始Client、可信ProxyRealm/SMMU授权Stage-1合成，复用GPUVM/认证队列/私有快照/native fence/cookie/epoch/IRQ127。输出普通返回区与诊断旁路也须服从隔离，epoch或暂停一个REC不等于GPU/DMA静默。OpenCCA完整7页全文及正式书目已读，官方站点确认源码opencca/opencca，独立报告/原型核对仍待完成；Confidential LLM Inference已获取15页arXiv及作者正式稿/幻灯片但未全文研读，均不计完成。

原库余10项及GR-T正式版/XpuTEE/AccShield/CPU–FPGA Salus继续保留。统一记录：全文/候选限定静态源码/Notion完整回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模拟/攻击run-id｜候选身份及端到端安全部署未验证。

## 接续 batch47：OpenCCA 实验载体与安全论证分层

完成 [OpenCCA独立报告](OPENCCA_SYSTEX2025.md)，完整7页arXiv2506.05129v1、42条参考文献，无附录；正式EuroS&P Workshops/SysTEX、DOI和429–434页书目核对。作者官网明确链接官方源码入口；固定入口1项README树及后续manifest2项树，3个blob长度/Git hash/SHA256核验并全文读取。入口不是核心代码，manifest使用可移动分支，不称已锁定所有组件；本地项目fork与历史捕获独立说明。

独立页面68个非空行完整回读通过，续研累计95/95；原库53/63、新增77、合计130篇解读，含技术资料、版本和支撑工作，不是130套CCA GPU架构。父页面旧131个子页和原正文逐行保留，现132子页，新增段落和计数核验通过，最终证据batch47-final-audit.json。整体active。

软件世界位、GPT/TLB近似、TTST/FWB/缓存、ECV/timer/FP循环、启动链和PMU评估专用补丁分别分析。作者100次启动/500万次SMC-RMI与Two-GPT/Shadow GPT是特定载体的性能观测，不写成真实RME安全等价；载体缺少RME也不否定目标安全假设。timer转送不替代GPU完成认证，保留RMM原始Client/ProxyRealm/SMMU、GPUVM/认证队列/私有快照/native fence/cookie/epoch/IRQ127。

Confidential LLM Inference的arXiv/作者稿/幻灯片仍未完整研读发布，不计完成；原库余10项及直接候选保持待办。统一记录：全文/官方入口及manifest有界静态读取/Notion完整回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/刷写/模拟/攻击run-id｜全组件核心审计、端到端复现及目标硬件安全验证未执行。

## 接续 batch48：机密LLM CPU/GPU推理、成本分母与端到端边界

完成 [Confidential LLM Inference独立报告](CONFIDENTIAL_LLM_INFERENCE_IISWC2025.md)，完整作者15页/91参考文献、无附录及14页讲稿文字；arXiv v1去空白/水印后提取文字与作者稿完全相同，正式IISWC2025 DOI/84–98页/四作者核对，两个PDF不重复计数。作者明确链接的SPCL仓库固定2025-09-30提交，48项完整树、14个blob核验并全文静态读取；另读上游vLLM v0.8.5 batch latency代码。

独立页面67个非空行完整回读通过，续研累计96/96；原库53/63、新增78、合计131篇解读，含资料、版本和相邻支撑工作，不是131套CCA GPU架构。父页原132子页及旧正文逐行保留，现133子页，新增段落和计数核验通过，batch48-final-audit.json保留证据；整体active。

单/多路CPU、裸机/VM/TDX分母、NUMA/hugepage/AMX与量化路径分别解读；摘要低开销不是全部测点上界。Azure GPU实测、本地CPU与GCP spot价格估算分开，GPU绘图以固定128输出算吞吐、成本parser却用input_len，长输入按每百万输出口径会低估2/4/8/16倍。硬编码成本字典未有完整原始生成链，不称全部图已重算或得出修正交叉点；CPU标注用单样本min、runner首项exit、默认矩阵/CSV列名、SGX策略与RAG检索覆盖范围均保留。

继续保持RMM原始Client、可信ProxyRealm/SMMU授权Stage-1合成模型，复用GPUVM/认证队列/私有plan/snapshot/native fence/cookie/epoch/IRQ127。驻留/batch摊薄成本仍受Client、KV cache和输出对象归属约束；TEE模式与低开销不代替可信完成，epoch不代替旧DMA静默。原库余10项及GR-T正式版/XpuTEE/AccShield/CPU–FPGA Salus等继续待办。

统一记录：完整论文/讲稿文字/有界静态源码/Notion完整回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/构建/云实例/容器/攻击run-id｜原始数据重算、成本交叉点、完整依赖及部署安全未验证。

后续发现batch49：沿RealmEye引用17取得PKUS完整15页arXiv PDF并严格解析，后续全文与候选原型研读结果见下节。00SEVen/BlueGuard宽关键词OpenAlex未正确直接命中；按RealmEye书目直接获取两个USENIX PDF均终态read timeout，保留失败，不计完成，不重启相同获取路线。

## 接续 batch49：PKUS 的知识授权、线性响应和在途撤销

完成 [PKUS独立报告](PKUS_ARXIV2025.md)，完整15页arXiv2512.16238v2、56条参考文献，无附录；没有确认正式venue。匹配候选pkusoslab/pkus固定2026-04-16后续提交，21项完整树（16blob/5子树）和11个blob核验并全文静态读取；未确认作者身份和论文测量版本，不冒充正式artifact。五个其余blob未取得全文，start_vm不在本次审计范围。

论文权重保密与条件性线性函数恢复、聚合器可信位置、非可信GPU的最终执行完整性、MAC与加密、quote与全副本新鲜撤销分别分析。候选Host明文上传LoRA、推理未接独立TDX模块、32worker复算同模型、msg_id固定、quote绑定/初始化/AEAD/分帧缺口均限定静态观察，无攻击复现。8.1–11.9倍来自表5特定消融；表2TEE/PKUS六项约4.87–11.49倍，PKUS对原生GPU约增加45.59–97.26%延迟，不跨表泛化。

独立页面87个非空行完整回读通过，续研97/97；原库53/63、新增79、合计132篇解读，含技术资料/版本/支撑研究，不是132套CCA GPU架构。父页原133子页及旧正文逐行保留，现134子页，新增段落及计数核验通过，batch49-final-audit.json保留PDF、树/blob与发布证据，整体active。

保留RMM原始Client/可信ProxyRealm/SMMU授权Stage-1合成模型，复用GPUVM、认证队列、私有plan/snapshot、native fence、cookie/epoch/IRQ127。研究建议聚焦输出归属、在途撤销、真实完成与安全回收；不把epoch失效当设备DMA静默。原库余10项及GR-T正式版/XpuTEE/AccShield/CPU–FPGA Salus仍待办。

统一记录：完整论文/有界候选源码/Notion完整回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/模拟/攻击run-id｜候选身份及测量对应、完整协议和端到端部署安全未验证。

接续发现batch50（2026-10-28）：四路OpenAlex补充搜索，通用GPU TEE查询成功，CCA/GR-T正式题名/XpuTEE查询均终态read timeout，证据discovery-acquisition-batch50.json，不重启相同请求。发现《Benchmarking Confidential Computing Performance on NVIDIA Blackwell GPUs》，索引arXiv2608.26575/2026-08-27；只读索引元数据，原始摘要/PDF及artifact未取得，不计完成或发布独立结论。其余返回主要为已读工作、泛TEE/非GPU材料，没有把关键词命中都视为新的CCA GPU论文。当前最近已完成发布仍batch49，132篇解读/97续研回读，任务active。

## 接续 batch50 完成：Blackwell CC 的性能与异步完成语义

完成 [Blackwell CC Benchmark独立报告](BLACKWELL_CC_BENCHMARK_ARXIV2026.md)，完整23页arXiv2608.26575v2、7条参考文献，无附录；全文读取引用NVIDIA博客正文。作者cc_probe/harness、精确cc-fixes版本与原始样本未确认。白皮书SSL握手超时保留，论文不是安全审计或新增CCA GPU架构。

关联NVIDIA博客明确链接的SGLang28251/FlashInfer3638固定head和19/2项完整文件元数据；限定全文读10/2份diff，3个完整blob hash核验，两个文档raw超时后从完整added-file patch重建且Git hash一致。未读SGLang其余9diff或全框架，后继31447/3870只读元数据/body：前者仍open，后者已merged，不把旧PR缺口当当前合入版本事实。

报告区分提交与NVLE两轴、吞吐损失与时间增加、功率与能耗；FP8训练实际增加24%，不能概括全部10–13%。跨模型/拓扑比较与固定12us精确预测的证据限制保留。旧worker在异常后仍done.set而所读消费者只等待，提醒本项目明确真实终态、失败状态、输出发布、取消与回收；未执行漏洞/模型/硬件复现。

独立页面86个非空行完整回读通过，续研98/98；原库53/63、新增80、合计133篇解读（含资料/版本/支撑研究，不是133套CCA GPU架构）。父页原134子页和正文逐行保留，现135子页，batch50-final-audit.json核验通过。RMM原始Client、可信ProxyRealm/SMMU授权Stage-1合成、GPUVM/认证队列/私有plan/snapshot/native fence/cookie/epoch/IRQ127保持主线，任务active。

统一记录：完整23页/厂商博客/限定PR源码/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/攻击run-id｜作者版本及原始数据、完整框架/后继源码、安全部署未验证。

## 接续 batch51：CCA 模型保护、共享输入与完成事件

完成 [SysTEX2025 CCA模型保护独立报告](CCA_MODEL_PROTECTION_SYSTEX2025.md)，10页arXiv2504.08508v1正文、54条参考文献、附录A–C全部阅读；正式EuroSPW DOI及页码核对。它扩展GuaranTEE的模型/指令统计和MIA评估，GPU接入仍为展望，不计作新的CCA GPU架构。

官方CCA-Evaluation固定b88d76d提交，README和3份完整源码静态读。完整树API403、归档超过15MB获取上限、marker路径404均保留；没有声称完整artifact/全部8类模型/MIA仓库/证明供应协议已审计。所读脚本FVP11.27与论文11.25版本差异、trace配对完整性和原始/去异常统计分别记录，不执行任何安装、构建、FVP或攻击。

报告区分17–22%指令开销与真实时延、平均8.3个百分点MIA改善与逐条件安全；保留表3的算术疑点和启动正文21902%/表格1902%冲突。结合当前GPUVM、认证队列、私有plan/snapshot、native fence、cookie/epoch及IRQ127，将通知来源、任务代际、真实终态、输出可见和静止后回收连为同一生命周期，保持用户给定ProxyRealm/SMMU授权Stage-1合成模型。

本篇60个非空行完整Notion回读通过，续研99/99，原库53/63、新增81、合计134篇解读；父页旧135子页与正文逐行保留，现136子页，batch51-final-audit.json通过。父页首次回读503，保存错误后一次只读重试成功，不重复创建或追加；整体active。

CPU–GPU综述arXiv2408.11601v3已取得39页、核对CSUR2026 DOI，但未全文读；DICE-anchored Realms机构PDF403。MirageNet、TEE-X、BiShield-TEE仅OpenAlex元数据候选，原文和相关性待核，全部不计完成。GR-T正式版和XpuTEE全文HTML403、相关仓库检索未建立新匹配artifact，继续待办，不用CODY早期稿替代。

统一记录：10页全文/54条参考文献/附录A–C、固定README及3份源码/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/FVP/模型/攻击run-id｜原始数据、完整artifact、证明协议和GPU实现未验证。

## 接续 batch52：CPU–GPU 机密计算综述与保护分类

完成 [CPU–GPU综述独立报告](CPU_GPU_CC_SURVEY_CSUR2026.md)，arXiv2408.11601v3完整39页、194条参考文献及附录A；正式CSUR DOI10.1145/3793532记录35页/163条参考文献，最终出版全文未读，不混同版本。图采用标签/图注/正文、符号丢失的表格单元不猜测，不冒充逐像素核验。

报告比较11行异构TEE方案（其中TNPU是NPU），区分访问控制、物理加密、共享资源侧信道、可信I/O和任务完成；保留Hopper加密/MIG支持、跨章节SGX概括、EM/MMIO术语、带宽单位和TCB计量问题。所读预印本没有直接覆盖Portal、ACAI、Devlore等后续主线，不把2026版本日期等同最新文献穷尽。

重新全文读取2026-10-26保存的NVIDIA官方威胁模型，定向读取当前RMM xshm_irq完整文件、endpoint305–440和Proxy545–615；输入全文哈希只作定位，不声称全文件审计。保持用户给定RMM身份/ProxyRealm/SMMU授权Stage-1合成模型，复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch、IRQ127，将接收、真实终态、输出可见和静止回收统一分析。

本篇74个非空行完整Notion回读通过，续研100/100；原库53/63、新增82、合计135篇解读，含资料/版本/支撑研究，不是135套CCA GPU架构。父页旧136子页及正文逐行保留，现137子页；batch52-final-audit.json核对PDF、采集哈希、阅读范围和发布。Notion创建/追加/回读遇503，先确认是否已落地再重试，未重复创建或追加。

后续取得MirageNet arXiv2601.13826v1完整13页、TEE-X arXiv2608.22716v1完整14页，严格解析和首页身份核对；正文未读，不计完成。SEV-Step正式TCHES27页PDF取得，DOI10.46586/tches.v2024.i1.180-206、2024卷期/2023-12-04发表区分，仅读1–4页，后续继续全文及artifact。所有获取进程已终态，不启动模型、攻击或硬件测试，整体任务active。

统一记录：39页全文/194条参考文献/附录A、厂商快照及定向源码/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/FVP/攻击run-id｜最终出版全文、全部引用原文和完整部署安全未验证。

## 接续 batch53：SEV-Step 与可信中断的保证范围

完成 [SEV-Step独立报告](SEV_STEP_TCHES2024.md)，正式27页全文、64条书目记录，无附录；2023发表日期与2024卷期区分。官方meta固定b7fcefe提交，12条完整树、8个blob获取验证、7份技术文件全文读；LICENSE只获取验证。userland固定caee1079提交，58条完整树、5份选定文件完整阅读；匹配内核、QEMU、edk2及完整依赖未审计，不执行攻击或配置脚本。

报告区分Host物理timer驱动退出、虚拟中断注入、框架ACK和GPU真实完成，保留zero-step、OOO缓存噪声、未认证算法配置及AES-NI策略条件。native fence、cookie/epoch和可信IRQ127约束功能完成，不能自动证明抗单步、时序非干扰或DMA静止；不将AMD攻击外推为CCA/GPU已有漏洞。

本篇64个非空行Notion全文回读通过，续研101/101；原库53/63、新增83、合计136篇解读，含资料/版本/支撑研究，不是136套CCA GPU架构。父页旧137子页与正文逐行保留，现138子页，batch53-final-audit.json通过。自动链接误把脚本名识别为域名，定向改为代码格式后重新全文回读，未降低校验要求。

StepOverflow（SysTEX2026）仅元数据候选，未读不计完成；MirageNet13页已全文阅读，报告和发布继续，尚未计数。TEE-X等保留待办，整体active。统一记录：论文/限定源码/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/FVP/攻击run-id｜完整artifact、当前补丁和GPU迁移未验证。

## 接续 batch54：MirageNet 的模型混淆及其保证边界

完成 [MirageNet/ConvShatter独立报告](MIRAGENET_ARXIV2026.md)，arXiv2601.13826v1完整13页、40条参考文献、伦理及开放科学声明。固定摘要页的Li Cheng与PDF的Cheng Li顺序差异、稿件系统命名和占位语均保留；未确认正式venue或匹配官方artifact，三组GitHub仓库搜索不作为全网不存在代码的证明。

分析共享系数时kernel差分不变量，mask预计算与每输入新mask的一致性，以及诚实恢复准确率与恶意GPU结果检测的区别；均为静态限定推导，没有执行攻击，不标为已证实漏洞。blackbox回退、主动篡改验证、可信恢复与CUDA执行位置有待补证；表4保留吞吐73.48%/69.04%和均值0.7126对表格0.72差异，不混同比例与时延。

本篇60个非空行Notion全文回读通过，续研102/102；原库53/63、新增84、合计137篇解读，含技术资料、版本和支撑研究，不是137套CCA GPU架构。父页旧138子页和正文逐行保留，现139子页；batch54-final-audit.json核验论文提取、获取哈希、阅读范围、计数与发布，全部通过，任务active。

项目继续采用RMM认证原始Client、可信ProxyRealm/SMMU及授权Stage-1合成假设，复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch和IRQ127。模型混淆仅作替代路线比较，优先任务归属、真实终态、输出可见和撤销静止；TEE-X正文、StepOverflow全文及原库余项仍待完成。

统一记录：13页全文/40条参考文献/有限artifact检索/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/模型/FVP/攻击run-id｜正式发表、匹配源码、原始数据和安全部署未验证。

## 接续 batch55：TEE-X 的模型压缩、CPU SIMD 与共享输入边界

完成 [TEE-X独立报告](TEE_X_ARXIV2026.md)，arXiv2608.22716v1完整14页、65条参考文献，无附录。其全部推理在TrustZone CPU，GPU仅性能基线；模型变换/压缩与运行时SIMD共同提速，不视为CCA GPU架构。四组有限GitHub搜索未确认匹配官方artifact，不声称完整350项宽泛结果已全部检查。

分析rank预算和训练近似、encoded权重与认证供应的区别、共享输入/输出和SIMD上下文边界；保留CIFAR时延约+5.90%至−6.38%、ImageNet准确率下降3.28–3.93个百分点及消融80%/77%文字算术差异。GPU基线、模型改变、batch1条件和TEE侧信道排除不能省略。

本篇63个非空行Notion全文回读通过，续研103/103；原库53/63、新增85、合计138篇解读，含资料/版本/支撑研究，不是138套CCA GPU架构。父页旧139子页和正文逐行保留，现140子页，batch55-final-audit.json通过。PDF数学提取含3个CR，文件read_text转换为LF；核验记录仅正规化通用换行后逐字一致，没有忽略内容差异。

SecureInfer7页全文及27条参考文献已读，独立报告继续，未计完成；StepOverflow出版入口403、Intel精确规格页403等获取失败保留，不使用摘要或猜测填充。项目维持RMM原始Client、可信ProxyRealm/SMMU授权Stage-1合成，以及GPUVM/认证队列/private plan/snapshot/native fence/cookie/epoch/IRQ127；无新模型框架或重复身份体系，整体active。

统一记录：14页全文/65条参考文献/有限artifact检索/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/构建/训练/推理/攻击run-id｜正式发表、匹配源码、权重供应链和安全部署未验证。

## 接续 batch56：SecureInfer 的 LLM 分割与跨域状态

完成 [SecureInfer独立报告](SECUREINFER_ARXIV2025.md)，arXiv2510.19979v1完整7页、27条参考文献，无附录；固定摘要页与同版本HTML表I核对。PDF普通提取无法判断checkmark列，使用HTML cell明确Embedding/SiLU等GPU归属，不靠预期猜测。没有确认匹配官方artifact，两项未知同名仓库README404，Intel精确规格页403保留；没有作者源码、真实SGX/模拟模式或攻击复现确认。

报告分析摘要与具体划分冲突、XOR/OTP认证及新鲜性、GPU非线性恢复和主动结果校验、输出扰动与效用的区别。表VIII得到约4.68倍时延加速/4.66倍吞吐，与结论3.7倍不同；2.06倍GPU时长为约增加106%，功率比不等于能耗比。四层/32层profiling、重复depth标记及BLEU表头差异保留，不据文档缺口宣称造假或已证实漏洞。

本篇70个非空行Notion全文回读通过，续研104/104；原库53/63、新增86、合计139篇解读，含资料/版本/支撑研究，不是139套CCA GPU架构。父页旧140子页和正文逐行保留，现141子页，batch56-final-audit.json核验论文、HTML表格、获取哈希、发布与计数，全部通过。引用编号在Notion转义为反斜线方括号，校验只正规化Markdown转义，不忽略文字。

另取得BiShield-TEE arXiv2610.21565v2共31页，PDF SHA256及首页身份核对、全文提取完成，正文尚未读，未计完成。首页标NeurIPS2026并列出laduiw/BiShield-TEE仓库；正式录用及artifact尚未独立核验，不将首页声明作为已验证发表。整体任务active，原库剩余条目及StepOverflow等继续待办，无运行中的获取进程。

对项目继续维持RMM身份、可信ProxyRealm/SMMU及授权Stage-1合成假设；模型/LoRA/KV/chunk/输出若进入服务，应复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch、IRQ127串联真实终态和静止回收。统一记录：7页全文/27条参考文献/同版本HTML表I/有限artifact检索/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/SGX/构建/模型/攻击run-id｜正式发表、匹配源码及完整密码/部署协议未验证。

## 接续 batch57：BiShield-TEE 的完整协议与计时路径边界

完成 [BiShield-TEE独立报告](BISHIELD_TEE_ARXIV2026.md)：arXiv2610.21565v2完整31页、53条参考文献、附录A–H及checklist。作者/arXiv称NeurIPS2026录用，正式会刊未独立核验；固定作者仓库commit `182362e34694b0144a69daae3821d0a7b984f957`，完整85项tree，12份选定文件全文静态阅读及Git blob/SHA256验证，没有执行论文或仓库程序。

报告分析公开骨干攻击的秩及条件数前提、双侧多解不等于功能不可恢复、低秩mask及Freivalds边界。所读合成设备计时路径复用预处理state、输出恢复后Q/K/V、以诚实数值基线代替运行时恶意结果验证，不能用它证明完整隐私协议或逐轮刷新成本；README明确benchmark及生产供应边界，未据此直接宣称生产漏洞或论文实验失实。

66个非空行全文回读通过，续研105/105；原库53/63、新增87、合计140篇独立解读，含资料/版本/支撑研究，不是140套CCA GPU架构。Notion将部分裸文件名自动转换为HTTP链接，已将四段文件名改成inline code并重新完整回读，未扩大校验忽略范围。父页原141子页及正文保留，现142子页；`batch57-final-audit.json`核验论文提取、12份源文件、发布和计数通过。

项目建议沿既有GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch和IRQ127绑定真实任务终态、缓存同步、正确接收者及静止回收；单独一个中断不能充当任务成功证据。原库余项及XpuTEE、GR-T正式版等仍待全文核验，整体active。

统一记录：31页全文/53条参考文献/附录A–H/checklist/12文件静态阅读/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/SGX/构建/推理/攻击run-id｜正式会刊、全部攻击代码、生产部署和漏洞复现未验证。

## 接续 batch58：TransLinkGuard 的模型授权与执行边界

完成 [TransLinkGuard独立报告](TRANSLINKGUARD_MM2024.md)：官方arXiv2404.11121v2 HTML全文、§1–7、算法1、公式1–9、五表及65条参考文献。Crossref正式MM2024书目九作者与实际预印本七作者/顺序差别保留；PDF仅362227/1421541字节下载超时，不当完整原文。本轮通过完整闭合的官方HTML研读，不以正式10页排版冒充已逐页读取。

表2汇总1.01倍复算为准确率求和之比1.01308，不是逐任务比值平均。表3授权模拟攻击LLaMA2/GSM8k为5.29%对1.04%，与严格黑盒等价不同；低于0.1%是TEE在线FLOPs，§5明确真实时延未测。记录表4部分算术不一致、公开骨干/结构匹配可能性、OTP协议与主动完整性、输入/KV隐私及请求主体认证的边界。精确GitHub检索0，无确认artifact或源码审计。

75个非空行全文回读通过，续研106/106；原库53/63、新增88、合计141篇解读，含资料、版本和支撑研究，不是141套CCA GPU架构。父页原142子页和全部旧正文保留，现143子页；`batch58-final-audit.json`核验原文哈希、获取文件、参考文献、书目/汇总比值、发布及计数通过。

直接缺项获取继续：GR-T出版方403，XpuTEE试探项目页404。GPU Taint Tracking完整下载超时，严格校验Content-Range的分段取得11/17段，余6段超时，不组装残缺PDF或计为完成；下一轮仅重试缺段。GroupCover正式PMLR索引及摘要页已取得，当前链接PDF获取失败；尚未研读。新发现KV leakage arXiv2409.04040、obfuscation security boundary arXiv2609.10117、SPOILER arXiv2603.06263与LoRO正式元数据，仅列候选，不宣称其机制或增加完成数。

项目建议继续绑定Client/对象/模型版本/输入输出与cookie/epoch，以真实native fence、数据同步及受保护终态发布驱动IRQ127；不以feature shuffle、FLOPs或单个通知替代隔离和完成证据。整体active。统一记录：官方v2 HTML全文/65参考文献/五表/有限artifact检索/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/TEE/构建/推理/攻击run-id｜出版方排版、匹配源码和真实部署未验证。

## 接续 batch59：KV-Shield、片上残留和持久会话状态

完成 [KV-Shield独立报告](KV_SHIELD_MOBIARCH2024.md)，实际题名A First Look At Efficient And Secure On-Device LLM Inference Against KV Leakage。官方arXiv2409.04040v1 HTML全文、§1–6、公式1–6、五表、致谢及22参考文献；四图全部视觉核对，其中图3/4原始SVG用已有librsvg/cairo渲染，无依赖安装。Crossref确认MobiArch2024、13–18页及五作者，初始候选键中的EDGE只是历史标识，不作为venue。PDF超时未计成功。

分析区分持久KV和kernel片上副本、受限local-memory攻击者与更强Host、作者手机复现陈述与独立证据。图4行重排示意与公式右乘列置换差异保留；单头等价不能直接覆盖多头/RoPE/GQA。固定置换保留范数/元素集合/Gram等信息，不自动提供语义安全。缓存容量随seq_len线性增长，HTML上标2为脚注；QEMU单层结果置换0.9–4.3秒不代表硬件TEE固有成本，没有完整实时防御原型或安全恢复率实验。

75个非空行Notion全文回读通过，续研107/107；原库53/63、新增89、合计142篇解读，含资料/版本/支撑研究，不是142套CCA GPU架构。父页原143子页及旧正文保留，现144子页；`batch59-final-audit.json`校验原文/图/书目/获取哈希、发布及计数通过。有限GitHub检索1与9项均未建立作者artifact关联，无源码审计/漏洞执行。

## 接续 batch60：LeftoverLocals 与可信资源移交

完成 [LeftoverLocals 独立报告](LEFTOVERLOCALS_ARXIV2024.md)，官方arXiv2401.16603v1 HTML全文§1–9、致谢、八参考文献、五表、六编号图（含两段代码和图5八子图）全部阅读。作者仓库固定2024历史commit，完整429项树，14文件获取并校验Git blob；13完整阅读、一个大型文件定向阅读。未执行攻击、模型、构建或GPU测试。

LLM演示修改受害端GEMV，将4096个FP32元素即16KiB隐藏向量留在local memory，结合公开输出权重重算token；不是完整KV恢复，也不是未经修改的任意llama.cpp攻击。实际listener使用启发式、argmax并抑制连续重复token，没有完整token准确率实验。Arm非零读取未建立跨进程canary证据，不外推跨VM/Realm漏洞或2026修补状态。

对项目的增量是跨Client可信资源移交：保护片上状态及抢占保存区，计算后另排清理kernel不能留下可插入攻击任务的空窗。既有native fence计算完成语义与资源可移交条件应分别规定；复用GPUVM、认证队列、private plan/snapshot、cookie/epoch及IRQ127绑定真实终态、静止和必要清理，不新增身份体系。

[Notion报告](https://app.notion.com/p/406659a3b8cc812b900cefb37483f522)53个非空行全文回读通过，续研108/108；原库53/63、新增90、合计143篇解读。父页原144子页与旧正文保留，现145子页；`batch60-final-audit.json`通过。未改运行代码，无新增性能测量；glmark未测→未测，分差/百分比不适用，无硬件run-id及新增PASS。XpuTEE、正式GR-T等全文受阻条目仍不计完成。

## 接续 batch61：GroupCover、统计模型恢复与实现对应

完成 [GroupCover独立报告](GROUPCOVER_ICML2024.md)，ICML2024/PMLR235:59992–60003，官方12页PDF从PMLR原链接对应GitHub API取得，blob/长度/hash验证。全文§1–6、26参考文献、附录A–D、七表、两算法、公式1和八图全部阅读，十页图表/算法渲染视觉核对。PDF直链作者仓库固定2025后续提交，完整473项树及12个选定文件全文静态读取，无模型/攻击/RPC/构建/硬件执行。

报告区分功能精度恢复与权重恢复；表3的1.03是准确率总和比，p=0.10不证明安全等价，分组可逆混合仍保留线性结构。19%是相对Slalom的吞吐损失，实际GroupCover保留29.3–40.0%原生GPU吞吐。正文算法g%2、布局/bias、掩码供应和Freivalds论证与源码分开：所读RPC路径复用mask、发送model且未见完整校验，Transformer示例两样本按512计吞吐；不把后续示例直接归因到论文正式CNN表5。

[Notion报告](https://app.notion.com/p/406659a3b8cc81338c12cedb227353dd)68个非空行逐行回读通过，续研109/109；原库53/63、新增91、合计144篇解读，含资料、版本和支撑研究，不是144套CCA GPU架构。父页原145子页及旧正文保留，现146子页，`batch61-final-audit.json`通过。LeftoverLocals候选别名旧未读状态已纠正，无重复计数。

GR-T/DICE再次获取分别403，XpuTEE/AccShield/CPU–FPGA Salus仅最新元数据；GPU Taint Tracking六个缺失range再次读超时，保留11/17成功分片，未组装或计全文完成。后续优先直接相关未完成论文和可取得全文的新候选，任务active。项目继续RMM身份、可信ProxyRealm/SMMU授权Stage-1合成，复用GPUVM/认证队列/私有plan/snapshot/native fence/cookie/epoch/IRQ127，分别论证归属、真实完成、数学正确性及安全回收。

统一记录：官方PDF全文/图表视觉核对、固定artifact12文件完整静态研读及Notion核验｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/构建/攻击run-id或新增PASS｜保留研究，原始测量链及完整安全部署待验证。

项目新增研究点为GPU私有片上状态切换隔离，以及KV对象对Client/模型/会话/布局/token区间/epoch的归属。复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch及IRQ127，真实终态与同步后发布不能被一次IRQ替代；撤销需静止在途访问并处理片上/后备页残留。尚未改运行实现或宣称漏洞。

沿引用链取得LeftoverLocals arXiv2401.16603官方HTML与摘要页，哈希登记，但全文尚未精读或独立发布，不计完成。此前GR-T/XpuTEE/AccShield等缺项与GPU Taint Tracking缺段保留，整体active，无存活获取会话。

统一记录：官方v1 HTML全文/22参考文献/五表/四图视觉核对/Crossref/有限artifact检索/全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/TEE/构建/推理/攻击run-id｜出版方排版、匹配源码、真实部署和攻击复现未验证。

## 接续 batch62：StepOverflow 与真实事件中断的观测边界

完成 [StepOverflow独立报告](STEPOVERFLOW_SYSTEX2026.md)。原ACM PDF返回403，经官方SysTEX2026议程实际引用的program-data.js取得会议九页PDF，全文§1–10、25参考文献、附录A/B、三代码清单和一表全部阅读，四页渲染视觉核对。作者artifact固定309f4c0e56fc8f810233fbe49c451a53eb25ee72，完整16项树及全部12文件Git blob、长度、SHA256核验并完整静态读取，无攻击、VM、构建或硬件执行。

报告区分真实PMC overflow中断与事件配置/观测授权。单台Zen3实测skid不足以单步，但仍可有条件推断SEV-SNP控制流；TinyCrypt案例关闭masking、插入105条DIV标记并使用受控Guest绑核，nonce连续低位零数量低估0–5位，长期ECDSA私钥恢复不在本文范围。公开README使用allow-debug，既不能写成已独立验证非debug复现，也不能仅据此否定其不依赖GuestIP的PMC原语。

定向核对当前RMM的PMU上下文、overflow状态对NS暴露、ENABLE_OPENCCA_PERF分支与IRQ127保留slot规则；没有完整Arm PMU、GPU计数器或板端编译值审计，不宣称现成漏洞。项目建议复用既有Client/GPUVM/认证队列/private plan/snapshot/native fence/cookie/epoch框架，为CPU/GPU profiling、trace/debug、overflow配置与样本规定归属、允许泄漏及跨Client切换清理；可信IRQ来源与真实任务完成、观测保密分别论证。

[Notion报告](https://app.notion.com/p/406659a3b8cc818fb9ecc52bc3f82f50)63个非空行逐行回读通过，续研110/110；原库53/63、新增92、合计145篇解读，含资料、版本和支撑论文，不是145套CCA GPU架构。父页原146子页与旧正文保留，现147子页；`batch62-final-audit.json`通过。整体active，未改运行代码，无新增性能测量。

SPOILER官方arXiv2603.06263v1 HTML和PDF已获取，正文§1–7、两表、四公式及43参考文献已读，图/所指补充材料及独立报告仍待完成；LLM obfuscation security boundary arXiv2609.10117v1官方HTML已获取，只读身份/摘要。两条均不增加完成数；GR-T、XpuTEE、GPU Taint Tracking缺段等旧待办保留。

统一记录：会议全文/25参考文献/三清单/一表、固定artifact全部12文件、项目PMU/IRQ定向只读核对及Notion全文回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/VM/构建/攻击run-id｜保留研究，非debug复现、长期密钥恢复、Arm迁移及防御有效性待验证。

## 接续 batch63：SPOILER 与并行模型保护的评价边界

完成 [SPOILER独立报告](SPOILER_ARXIV2026.md)。官方arXiv2603.06263v1、2026-03-06、17页预印本，全文§1–7、43参考文献、两表、四显示公式和八幅图全部阅读，十页渲染视觉核对。完整论文TeX源包716121字节、23文件清单及哈希核验，main/background/method/experiments四TeX完整静态读取；主文引用的补充A/B不在PDF或完整源包，未确认官方可执行模型/OP-TEE/GPU实现，不把论文TeX当运行代码。

报告分析NAS选择TEE分支及self-poisoning降低特定外泄权重初始化攻击效果，区分模型功能保护与多Client设备任务隔离。攻击者可忽略poisoned参数选择同条件黑盒策略，因此所测攻击低于Black-box不表示最优攻击能力低于黑盒。高交叉熵也不证明特征无私有信息，重置分类头等自适应策略尚待实测。

表1的SPOILER0.08×按九项倍率均值约0.10771、按准确率总和比约0.12221，源包直接写常量而无生成公式；GroupCover0.37×也无法用这两种口径复算。保留原表/逐项数值与复算差异；表2九项效用变化均值+0.89个百分点，不把训练、蒸馏、容量与NAS组合归因单一机制。图6早返回叙述与包含完整GPU尾段的g模型需统一计时边界，图8功耗模式不直接泛化不同设备。

项目建议仍采用RMM身份、可信ProxyRealm/SMMU授权Stage-1合成，复用GPUVM/认证队列/private plan/snapshot/native fence/cookie/epoch/IRQ127；分别规定结果就绪、真实GPU终态及资源可回收，早返回不能提前释放BO/映射/快照，也不能以模型准确率替代归属、结果验证或完成证明。

[Notion报告](https://app.notion.com/p/406659a3b8cc81e9bf16fdfa21fa002d)71个非空行全文回读通过，续研111/111；原库53/63、新增93、合计146篇解读，包含资料、版本和支撑研究，不是146套CCA GPU架构。父页原147子页与全部旧正文保留，现148子页；追加首请求300秒超时后，回读确认未保存，分段追加并核验只有一份，`batch63-final-audit.json`通过。

LLM obfuscation security boundary全文已取得但仍待研读，其他正式GR-T/XpuTEE等旧缺项与GPU Taint Tracking缺段保留。整体任务active，未执行模型/攻击/构建/VM/硬件。

统一记录：官方17页PDF/HTML全文、43参考文献/两表/四显示公式/八图、完整源包与四TeX研读、有限artifact检索及Notion核验｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/构建/攻击run-id｜保留研究，缺失补充/运行实现、自适应安全评价及完整异步生命周期待验证。

## 接续 batch64：Obfuscation Boundary / Collapse

完成 [独立报告](OBFUSCATION_BOUNDARY_ARXIV2026.md)，官方arXiv2609.10117v1全文17页、§1–10、50参考文献、附录A–G、九表和三图，十一页渲染核对。作者摘要注释称CCS2026 Cycle B接收，本轮未核验正式ACM出版；已知v2存在，但未研读，不假定本轮问题仍适用于v2。

取得九文件论文源包，官方Collapse仓库固定提交 `b8e940b8835d08034502c5275351ab565b3c3d3f`，完整35树项、29文件全部下载并经Git blob/SHA256校验。完整阅读八个说明/实现文件，定向阅读攻击、样本预算、RPC与阶段计时路径，未声称全仓审计。发现ArrowCloak部分路径借真实置换对齐或筛选；Oprior代码为(WD+L+S)Π而主文为(W+L+S)DΠ，跨轮静态S关系不同；主要实验mask rank override为1，CIFAR默认2000训练样本为4%。需原始日志和无oracle辅助复现解释，不能把这些发现扩张为全部Collapse依赖秘密密钥。

报告区分原语规范形、带完整交互模拟前提的组合安全与所测非自适应Oext防御。表7平均准确率差27.44个百分点、相对黑盒均值约1.00，不表示每任务均无泄漏。表8Oext903.33ms比Oprior855.82ms增加47.51ms（5.55%），比ArrowCloak922.81ms减少19.48ms（2.11%）；均为作者限定微基准。RPC直接pickle.loads和外部gpu_ms只适用诚实微基准，不构成恶意Host输入边界或完成证明。

项目仍采用RMM原始Client身份、可信ProxyRealm/SMMU建图授权、受保护GPU Stage-1合成；复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch和IRQ127。区分模型功能提取、任务完成与资源回收；epoch防重放不消除已暴露视图，也不撤销在途DMA，不能据模型混淆研究改变可信设备路线。

[Notion报告](https://app.notion.com/p/406659a3b8cc81ee8b52ca6c26c7eb28)65个非空行全文回读通过，续研112/112；原库53/63、新增94、合计147篇解读，含资料、版本和支撑文献，并非147套CCA GPU架构。父页原148子页及旧正文全部保留，现149子页，`batch64-final-audit.json`通过。整体active，正式GR-T/XpuTEE等旧缺项及本篇v2继续待研读。

统一记录：v1全文/附录A–G、50参考文献、九表三图、十一页视觉核验，固定artifact完整下载与限定路径静态阅读、算术复核及Notion全文回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id｜保留研究，v2/正式版、无oracle复现、数据预算与恶意通信边界待验证。

## 接续 batch65：LoRO、接口授权及 Collapse 版本跟进

完成 [LoRO独立报告](LORO_NEURIPS2025.md)，NeurIPS2025正式25页全文、60参考文献、附录A–E/checklist、5图12表2算法，11页视觉核对。固定官方提交 `e268c587aaeaebbb9e95b51328f67444e21f9949`，完整311项树，选定34文件中26个Git blob/SHA256验证取得、8个网络失败保留，限定路径静态研读，无执行。它是CPU TEE模型保护对照路线，不冒充CCA GPU设备架构。

复算表1倍率均值0.94406、十二项归一化延迟均值1.4875；记录任务间增益、表6占比及表1/3原模型精度差异。公开精度代码在cuda保留秘密及恢复，性能采用独立阶段和理想重叠；RoBERTa覆盖MHA计时，Qwen输出段未纳入已记录out_tee。后续MNIST调试TA使用可预测因子，provisioning先导出后锁定，运行接口向REE返回correction并在REE恢复中间激活。任意选择输入时可形成识别有效遮罩的线性oracle，这是公开示例的条件性静态推断，未执行攻击，不扩张为论文全部实验已被攻破。

[Collapse报告增补](OBFUSCATION_BOUNDARY_ARXIV2026.md)定向核查v2范围和新官方TEE-Obfuscation固定提交 `55b6db58d1de523751cb84dd1bda0bcc265c500b`：完整29路径仅README改变，28程序文件相同。新README明确GEMM微基准非端到端，排除非线性和离线预计算，未附Occlum镜像。保留v1精读与v2定向核查的区别，不把部分差异阅读重复计作新论文或完整v2研读。

[LoRO Notion](https://app.notion.com/p/406659a3b8cc81efb115e8d8c2c1e1ab)57个非空行、更新Collapse71行全文回读通过，续研113/113；原库53/63、新增95、合计148篇解读，含资料/版本/支撑研究，不是148套CCA GPU架构。父页原149子页与旧正文保留，现150子页，`batch65-final-audit.json`通过。正式GR-T/XpuTEE等全文缺项继续待办，整体active。

项目研究主线仍优先PORTAL/CAGE/ACAI、Devlore以及MOLE/PhantomMap/LeftoverLocals。沿用RMM原始Client身份、可信ProxyRealm/SMMU授权Stage-1合成，以及GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch、IRQ127，明确操作授权、允许输出、真实终态、内容发布和安全回收的不同条件。

统一记录：正式全文/附录/checklist、图表、固定artifact限定静态研读、算术复核与Notion核验｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增PASS｜保留研究，缺失源码、端到端复现、完整v2差异与接口加固待验证。

## 接续 batch66：Ascend-CC 与完成授权的内存状态转换

完成 [Ascend-CC独立报告](ASCEND_CC_ARXIV2024.md)，官方arXiv2407.11888v1、16页全文、§1–10、74参考文献、14图1表，10页渲染视觉核对。模型/数据两类所有者分别与设备建立密钥，Host完全不可信；设备端撤权→认证/解密→执行→加密输出→清理/重新开放的顺序和CQ成功确认连接为生命周期协议。它使用离散NPU、整设备单租户，multi-residence不等于跨Client并发；不能据大模型占用否定本项目共享路线。

报告重点列出完整参数/别名授权、在途DMA/TLB失效、会话nonce/重放、异常reset和KV/workspace回收等尚需论证的边界。PC_START和二进制顺序认证不自动等于完整任务描述授权；KV存储通常随token数线性增长，不沿用正文二次增长说法。未确认作者匹配artifact，两同名/近名仓库README实际与论文无关，无源码审计或执行。

图10纵轴为2的幂，4KB map/unmap2.47µs，1124KB约485.52/485.26µs；GPT-Neo加载49.6–71.0%、推理0.91–16.03%，Llama图14共48单元约0.00272–0.06856%。这些是作者限定测量，保留冷启动、13B长输入OOM、极小开销的统计证据不足和GPT-Neo/ImageNet文字差异，不用于本项目提分归因。

[Notion报告](https://app.notion.com/p/406659a3b8cc8103847af24c67f4fcc3)64个非空行全文回读通过，续研114/114；原库53/63、新增96、合计149篇解读，含资料/版本/支撑论文，不是149套CCA GPU架构。父页原150子页及旧正文保留，现151子页，`batch66-final-audit.json`通过，整体active。

正式GR-T/XpuTEE/CPU–FPGA Salus出版入口本轮仍403，保留缺项。新取得AutoSecGPU正式15页PDF及DDP GPU TEE开销论文v3的11页PDF/HTML，仅首页身份/摘要核对，全文研读和独立报告待完成；v1也取得但不替代v3。LGT4CG仅正式元数据，API200 XML无正文、ScienceDirect403错误页、PDF接口406，不计全文。下一篇优先AutoSecGPU的自动任务证据和参数完整性分析。

项目继续RMM原始Client身份、可信ProxyRealm/SMMU授权Stage-1合成；复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch、IRQ127，将操作授权、可信完成、内容发布和安全回收分别证明，不新增平行身份或未经论证的加密层。

统一记录：官方16页全文/74参考文献/14图1表/10页视觉核验、算术复核、有界artifact核查及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增PASS｜保留研究，匹配源码、对抗复现、多Client扩展与新候选全文研读待验证。

## 接续 batch67：AutoSecGPU 与任务参数证据

完整阅读AutoSecGPU正式15页、§1–8、19条参考文献、2图5表，8页渲染视觉核对；[独立报告](AUTOSECGPU_IFIPSEC2026.md)。自动提取二进制、顺序和参数规则适合补充轻量GPU TEE，但不替代实际HPA归属、跨Client权限、检查到使用窗口、可信完成与回收。固定一次batch轨迹的覆盖边界及动态指针识别必须另行论证。

作者报告在线训练平均7.1%、推理10.8%总开销，参数验证增量分别约0.63/0.49%；不可混为同一指标。核对训练离线Table3实际最大57.15倍，与正文51.75倍不同；Table1准确率下降应写百分点。CAGE引用会议误写也已标注，不沿用到文献库。

[Notion报告](https://app.notion.com/p/406659a3b8cc81a2a75af1e45b79541b)48个非空行全文回读通过，续研115/115；原库53/63、新增97、合计150篇解读，含资料、版本与支撑文献，不是150套CCA GPU架构。父页原151子页与正文保留，现152子页；审计见 `batch67-final-audit.json`。未找到作者确认的专用公开实现，未宣称源码审计或攻击复现。

项目优先复用GPUVM、认证队列、private plan/snapshot，把任务规则关联对象授权与实际执行快照；应用完整性策略按需启用，跨Client授权始终检查。复用native fence、cookie/epoch、IRQ127；通知只触发权威终态检查，不授权提前回收。DDP训练开销v3仍待全文精读，LGT4CG仍仅元数据，旧GR-T/XpuTEE等缺项保留，整体active。

统一记录：正式15页全文/19参考文献/2图5表/8页视觉核验、算术复核、有界artifact检索及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增PASS｜保留研究，匹配源码、动态任务与多Client对抗验证待完成。

## 接续 batch68：多GPU TEE分布式训练与安全通信粒度

完整阅读Characterization of GPU TEE Overheads in Distributed Data Parallel ML Training官方v3的11页PDF/HTML、§1–8、36参考文献、12图2表，8页渲染视觉核验；[独立报告](GPU_TEE_DDP_CHARACTERIZATION_ARXIV2025.md)。官方论文源包首次仅取得部分，后4段严格验证Content-Range并合并，通过gzip CRC与tar解析；44个普通文件清单及方法/评估目标源文静态核查，没有作者CUDA密码核、训练脚本或原始数值数据。

多GPU结果来自自定义密码核模拟，真实H100用于单GPU校准；四GPU8.68倍与几何平均吻合，算术平均16.71。图表最大值、校准误差、Table2数据量和优化前后对照链存在未解释差异，报告逐项区分，未将模拟数字描述成商用多GPU CC实测或本项目预期收益。

[Notion报告](https://app.notion.com/p/406659a3b8cc8153a9a2d903c022af0b)58个非空行全文回读通过，续研116/116；原库53/63、新增98、合计151篇解读，含资料、版本及支撑文献，不是151套CCA GPU架构。父页原152子页与正文全部保留，当前153子页；审计见 `batch68-final-audit.json`，整体任务active。

新取得LightGuard正式17页PDF及SpliTEE新版v3完整35页PDF/831000字节HTML、早期44页v1PDF，仅首页身份/摘要核对，尚未精读/发布。LightGuard为ICONIP2025，PDF版权2026、Crossref发布日期2025-11-16，后续明确区分；SpliTEE的v3PDF首次仅928693/1031013字节，经严格206/Content-Range尾段恢复并完成PDF严格解析，标题与v1不同，禁止静默混用；v1HTML部分超时不当全文。LGT4CG和正式GR-T/XpuTEE等旧缺项保留。

项目继续既定RMM/ProxyRealm/SMMU与实际页授权；可研究有界批量和通知合并，但每任务认证归属、private plan/snapshot、native fence、cookie/epoch、IRQ127及错误/取消/回收条件保持可核验。无需照搬不可信NVLink的密码搬运层或400MB常数。

统一记录：官方v3完整11页/36参考文献/12图2表/8页视觉核验、论文源包44文件清单及目标源文静态检查、算术复核和Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增PASS｜保留研究，密码实现、原始数据、项目批量和新候选全文研读待完成。

## 接续 batch69：LightGuard与异步训练验证的提交边界

完整阅读LightGuard正式17页、§1–7、30参考文献、3图4表1算法，10页渲染视觉核验；[独立报告](LIGHTGUARD_ICONIP2025.md)。明确CPU TEE抽查不可信GPU训练与GPU TEE隔离的区别；概率样本界依赖固定攻击比例与有效随机挑战，不自动给出单epoch1%保证；期望检出延迟不等于硬期限。

Algorithm1按字面先以∞最佳值检查候选可行性，分配r公式又在f_f/f_c上与成本项不同，均在原版图像确认；记录为伪代码/证明边界，不据此声称攻击了未取得的运行实现。核查完整状态、非确定性容差与直接hash比较、旧任务重放及异步验证提交/回收。Table4四模型LightGuard标注均值13%，ViT的TEE时间推算28.21%而表标19%；不把摘要12%当通用上限。

[Notion报告](https://app.notion.com/p/406659a3b8cc817288f3cf9df78c59cf)61个非空行全文回读通过，续研117/117；原库53/63、新增99、合计152篇解读，含资料/版本/支撑文献，不是152套CCA GPU架构。原153子页和正文全部保留，现154子页；审计见 `batch69-final-audit.json`，整体active。Gramine脚注是第三方训练变慢issue1253，不是作者实现，有界检索未确认匹配artifact。

沿引用链取得PoL官方18页v1、PoL攻击研究官方20页v2、Optimistic Verifiable Training官方23页v3，仅首页/水印/元数据核对，全文精读待完成；原始PoL初次仅608391/1156735字节，严格解析失败保留，后3段严格206/Content-Range恢复并完成PDF严格解析。SpliTEE新版35页及完整HTML继续待精读，LGT4CG与正式GR-T/XpuTEE等旧缺项保留，均不因取得原文计为完成。

项目复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch和IRQ127，把设备完成、应用验证通过、发布与回收分别授权。训练抽查可以是可选上层服务，不替代实际HPA/权限/归属/生命周期检查或强制中断隔离；验证积压、超时、取消/reset与迟到结果同样要终态和安全清理。

统一记录：正式17页/30参考文献/3图4表1算法/10页视觉核验、公式与算术复核、来源检索及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增PASS｜保留研究，匹配实现、完整状态、概率/期限证明和新候选研读待完成。

## 接续精读：SpliTEE与端到端观察组合（第70批）

完成[SpliTEE v3](SPLITEE_ARXIV2026.md)，完整35页/§1–9、54参考文献、5图7表及作者6页补充材料，14页视觉核对。固定提交ae865e62fdca81a1d84ecd1d51a0d8edfdd394ae的完整27项树、19blob校验，3份README和Host Worker完整阅读，Guest通信、噪声预计算/消费与计时路径定向静态核查。独立Notion页面61个非空行回读通过，续研118/118；原库53/63、新增100、合计153篇解读，含支撑资料与版本，不是153套CCA GPU架构。

主要边界是诚实但好奇GPU、未验证外包计算、完整transcript预算未组合，以及数值界约9.25%–10.03%实测元素越界。公开代码中的固定种子、近似谱范数、进程内一次消费/文件可重载及Guest pickle解析分别列明证据和假设，不声称攻击复现。性能是预计算/加载之外的批平均时间；最大约43.27%速度比提升对应30.20%时间下降，不把分母混用。

重新核对trilateral-gpu-sec文献库固定c2b493b4a2520bfefa19377977a5e09a60d33434、完整README112205字节。GR-T arXiv仍只有CODY早期v1，正式ACM epdf403；新试作者路径404如实保留，不声称论文不存在。沿引用链登记TwinShield官方v2（PDF860597/2203651字节部分下载，未完整阅读）和Depth Gives a False Sense of Privacy的USENIX官方入口；两篇未计完成。原PoL三篇、LGT4CG、正式GR-T/XpuTEE等缺项继续保留，整体active。

项目继续保持可信ProxyRealm强制映射授权，复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch和IRQ127；可吸收分组传输/缓冲复用/局部完成等待，但不得以Host事件替代可信任务终态，或把DP外包与受保护GPU执行混为同等安全。

统一记录：35页v3/6页补充/14页视觉核验、固定artifact定向静态核查及Notion回读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或新增运行PASS｜保留研究，整体任务继续。

## 接续 batch71：隐藏状态发布与GPU计算验证

完成[Depth隐藏状态反演](DEPTH_INTERNAL_STATES_INVERSION_USENIX2025.md)正式21页（含封面）、§1–9、68参考文献、附录A/B、20图10表和Algorithm1，15页视觉核对。攻击对象是被授权接收完整隐藏状态的参与方，不是突破CCA隔离。区分4112token案例、不同设置高F1与长Llama全部EM0；原版Laplace尺度、敏感度和完整transcript预算存在未核实事项，不称为破坏严格DP。Zenodo连接超时，没有匹配源码审计或攻击执行。

完成[TwinShield v2](TWINSHIELD_ARXIV2025.md)完整15页PDF/HTML、§I–VIII、59参考文献、附录、8图6表和10页视觉核对；严格206范围恢复PDF并严格解析。按Fig2/5一致公式，GPU整体同比例返回会同时缩放结果与校验行，等式仍成立；报告给出代数反例及其适用条件，不声称已攻击未取得的作者实现。记录有限域与实数指数、全零/NaN、相关校验输出、离线成本及性能分母的边界。

两篇Notion全文分别41/51个非空行回读通过：[Depth](https://app.notion.com/p/406659a3b8cc81beb351d4c4c27d3fca)、[TwinShield](https://app.notion.com/p/406659a3b8cc812b88a8ff79566a881b)。续研120/120；原库53/63、新增102、合计155篇解读，含版本与支撑资料，不是155套CCA GPU架构。原155子页及正文保留，现157子页，审计见 `batch71-final-audit.json`。

项目继续RMM原始Client与可信ProxyRealm/SMMU授权Stage-1合成，复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch、IRQ127；建议明确activation/KV/日志/输出发布权限，独立证明任务终态、可选应用验证与安全回收。同一不可信方提供的相关结果不能互相认证，物理IRQ也不自动证明数学正确或DMA停止。PoL三篇、LGT4CG、正式GR-T/XpuTEE等未完成任务继续保留，整体active。

统一记录：两篇全文、图表/25页视觉核对、代数/算术审查、有界artifact发现和Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件/模型/攻击/构建run-id或运行PASS｜保留研究，匹配实现和本项目设计验证待完成。

## 接续 batch72：跨GPU确定性与训练审计

完成[Optimistic Verifiable Training](OPTIMISTIC_VERIFIABLE_TRAINING_NEURIPS2024.md)的arXiv v3完整23页、§1–9、参考文献、附录A–J/checklist、5图6表4算法，12页视觉核对；另取得正式23页NeurIPS2024全文，比较所有文本差异、视觉核对4页。固定作者提交cea761a613251a8571d135e8d4d5dd14afdde0b6完整12项树/11blob核验，README和全部9Python文件全文静态阅读，语料仅完整性校验，无模型/训练/攻击/硬件/构建执行。

报告区分跨GPU可重复性、Merkle承诺和训练正确性。公开源码中未见完整交互裁决，GPT终态root绑定、固定阈值、dropout和标签移位语义、日志输入及命令入口等边界分别记录；没有把静态发现当运行攻击。Table5训练者开销16.67%/37.50%，加一次完整审计的累计计算时间为原训练2.46/3.06倍，与并行墙钟和本项目glmark无关。

[独立Notion报告](https://app.notion.com/p/406659a3b8cc81a8a62dd2c17f3c4841)53个非空行全文回读通过，续研121/121；原库53/63、新增103、合计156篇解读，含版本、资料和支撑文献，不是156套CCA GPU架构。父页原157子页及正文保留，现158子页，审计见 `batch72-final-audit.json`；整体active。

项目维持RMM/ProxyRealm/SMMU实际页和权限授权，复用GPUVM、认证队列、private plan/snapshot、native fence、cookie/epoch及IRQ127；应用验证按需加入，绑定完整规范和最终输出，不替代设备终态或安全回收。PoL原文与攻击研究、LGT4CG、正式GR-T/XpuTEE等待办继续保留。

统一记录：23页v3/正式版差异/16页视觉核对、固定artifact全文静态阅读、算术复核及Notion回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无模型/训练/攻击/硬件/构建run-id或运行PASS｜保留研究，完整协议和项目验证待完成。
