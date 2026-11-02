# cuCatch：GPU 对象边界、时间安全与调试检查的安全边界

研读日期：2026-10-27。原库 TGS-059。已读 NVIDIA 官方提供的 24 页正式论文，包括设计、实现、完整检测表、实验和局限；没有运行 CUDA、修改驱动或复现攻击。未改运行代码，无新增性能测量。

## 1. 书目信息与原文证据

| 项目 | 内容 |
| --- | --- |
| 标题 | cuCatch: A Debugging Tool for Efficiently Catching Memory Safety Violations in CUDA Applications |
| 作者 | Mohamed Tarek Ibn Ziad、Sana Damani、Aamer Jaleel、Stephen W. Keckler、Mark Stephenson |
| 正式发表 | Proceedings of the ACM on Programming Languages 7，PLDI，Article 111，2023 年 6 月，24 页；卷内页 124–147 |
| DOI | [10.1145/3591225](https://doi.org/10.1145/3591225) |
| 官方入口 | [NVIDIA Research](https://research.nvidia.com/publication/2023-06_cucatch-debugging-tool-efficiently-catching-memory-safety-violations-cuda) |
| 原文 | [官方页面链接的正式 PDF](https://d1qx31qr3h6wln.cloudfront.net/publications/PLDI_2023_cuCatch_2.pdf) |
| PDF SHA256 | `857158ac5af827f791f431f3b57231fc61d9777c8e267eded315b32ec169e770` |
| 阅读范围 | 全文 §§1–9、图表及参考文献；重点 §§2.3、3、4.6.4、5、6、7 |

题目是调试工具，不是 GPU TEE。本文把它纳入研究库，是为区分跨 Client 页隔离与 Client 内部对象内存安全，并研究检查的执行位置和对象生命周期。

## 2. 问题：页可访问不等于对象访问合法

GPU 程序通常使用 CUDA/C++ 一类不安全语言；一个可访问页内可能有多个对象，指针也可能在对象释放后继续使用。GPUVM/SMMU 限制可达页，仍不能独立发现页内越界、同 Client 内错对象访问、栈生命周期错误。

GPU 又包含不同内存空间：global、线程私有 local、线程块共享 shared，以及可能指向不同空间的 generic pointer。三种空间的寻址、分配和可见范围不同，不能把 CPU 的一种 shadow-memory 检查原样套用。

cuCatch 结合后端编译器插桩、base pointer 数据流分析及驱动维护的元数据，以较低运行成本发现空间和时间错误。它填补的是开发阶段检测覆盖与性能的空档。

## 3. 安全目标、可信条件及明确非目标

§2.3 要求可取得 PTX，允许编译器分析和插桩设备代码。目标是尽量多检测错误并降低成本。CPU 侧内存错误、未初始化读取、不兼容类型转换和同步/并发错误不由当前原型处理。

§3.3 明确采用调试目标，假设没有主动攻击者故意让越界指针逃逸到内存再重新加载。这一点限制了其作为安全沙箱的用途。编译器、驱动、元数据及所有访问点的插桩正确性是机制成立条件；论文没有提供恶意 Host/Hypervisor 下的 TEE 信任模型、设备证明或受保护 MMIO 协议。

未经插桩的二进制、内核内 malloc/free、CUDA Dynamic Parallelism 和部分自定义 allocator 均有实现边界。不能把“支持生成 PTX 的语言”写成任意现有 CUDA 二进制都已受保护。

## 4. Shadow Tagged Base & Bounds

核心数据结构为 Base and Size Table（BST）。每个分配记录 base、size 和 tag。编译器在真正访存前使用该对象的元数据检查地址边界与时间标签，异常后 trap/结束程序或输出诊断。

| 路径 | 元数据定位 | 目的与限制 |
| --- | --- | --- |
| 直接索引 | 指针高位存 BST index | 快速保留对象身份，但受高位容量限制 |
| shadow map | 指针高位存小标签，地址值查两级表取得 BST index | 扩展分配数量；重新查表可能丢失原对象来源 |
| unified/host 可达内存 | 不改 CPU 不支持的高位，经 shadow map 查元数据 | 避免破坏 CPU 指针语义；失去部分延迟 UAF 检测 |

原型假设可用高位 x=8：0 留给 host 侧分配，1–15 为 shadow 路径的非零四位标签，16–255 为直接索引，因此前 240 个相应分配可走快速路径。超过容量后仍可用 shadow map，不能把 240 当作全部受保护分配的硬上限。

shadow map 用每 32 字节区域的 32 位 index 标识 BST 项。它按指针数值而非指针存放位置索引，避免每次 memcpy 指针数组时都要维护另一份位置元数据；代价是指针来源和重新加载场景需要额外分析。

## 5. 分配、释放与代次

驱动拦截 cudaMalloc/cudaFree 等：建立 BST 项和标签；释放时把 tag 置零，并使 shadow 项指向非法零号 BST。新对象取得新的 BST 项及相应随机标签，区分同一地址的不同时期。

直接索引且 index 未复用时，旧指针仍指向旧 BST 项，重分配后的使用可确定检出。经 shadow map 的路径会按当前位置找到新对象，需以小随机标签发现旧指针，因此为概率检测。统一内存路径不能携带该高位标签时，延迟到重分配之后的 UAF 可能漏检。

正文 §5.3 的脚注也保留 BST index 再利用会使保证变化。不能把“新分配使用 fresh 项”理解成无限执行、索引溢出和回收均已形式化解决。项目的对象 generation/device epoch 需要的是受保护的授权语义，不能简单替换成可碰撞的短随机颜色。

## 6. Base pointer 分析：避免越界后才查询错误对象

编译器从内存操作追踪可达 base pointer。load、函数调用返回值或含多个来源的计算可能构成 destructive redefinition，分析在这些位置重新建立来源。先读取来源对象元数据，再沿派生地址传播，可避免循环指针越界后碰巧落入另一个合法对象，因重新查询当前位置而被错误放行。

READMETADATA 取得元数据；OOBCHECK 检查边界；TAGCHECK 检查时间标签；SAFETYCHECK 结合两者并去除指针标签。它们是编译器 IR 扩展，由普通指令实现，不是新 GPU ISA 硬件支持。

该分析是过程内的。函数参数/返回和指针经内存保存再加载等情况可能只看到已偏移的指针，导致查到另一对象的边界；四位随机标签只能概率补救。对主动构造指针的恶意程序，不能据此证明指针来源完整性。

## 7. 不同内存空间的具体实现

shared memory 主要由编译期已知 base/size 检查，没有 BST 和时间标签；块内 shared 在 kernel 期间不能像 heap 一样释放。动态 shared 子缓冲合并为一个区，原型不能识别其内部全部对象边界。

local memory 使用每线程 31 项 BST，保存函数 frame 和 alloca 的范围；24 位 local 地址剩余高位拆为 5 位 index 与 3 位时间 tag。进入函数建立项，返回弹出；跨 frame 时间错误可检查。超过预留深度则回退为普通栈范围检查，后端缺少 frame 内对象布局，不能检测全部 frame 内越界。

三位标签的单线程延迟 UAS 检测概率为 7/8。作者按不同线程独立随机标签推导多活跃线程时更高概率，不能据此写成对主动攻击或相关标签必然检测。generic pointer 先区分 global/local/shared，再执行各自检查；地址空间转换时也需保留相应标签。

## 8. 优化与“检测到”不同于“事前阻断”

作者对同对象连续访问合并最小/最大地址的边界检查，对循环不变量外提检查，或预先验证整个循环跨度。它们减少分支和元数据访存，但合并检查失败时诊断位置不再精确到单条访问。

§4.6.4 明确说 global 对象可能在 kernel 执行期释放，因此仅外提空间边界不能同时外提全部时间检查。作者进一步允许只在对象最后一次访问前检查时间标签，以便最终发现 UAF。

**最后一次检查成功或失败，不能追溯性地阻止先前访问已经产生的外部副作用。** 这是本项目迁移时最关键的边界：可以作为调试检测优化，不能未经新证明就用作恶意 Client 的持续访问控制。已有受保护 Stage-1 检查、对象引用和安全撤销仍应独立成立。

## 9. 驱动维护与元数据可见性

BST 每 CUDA context 一份，默认支持 2^20 个 live allocation。驱动修改 BST 后要求 GPU flush cache，再返回调用者；统一内存 shadow 的维护成本随分配大小增长。shared 的总范围通过 constant bank 提供，local BST 空间在启动前预留。

这些维护步骤展示了元数据更新必须对实际执行者可见。它们不构成本项目跨 Realm、多个 DMA 设备与 reset 全生命周期的证明。特别是已缓存的元数据何时可复用、释放与在途访问如何同步，需要结合 API 和执行语义另行说明。

## 10. 检测覆盖：按具体测试计数

作者自建 56 项测试，包括空间、时间、无效释放和 double-free。它是特定测试集覆盖率，不是实际漏洞世界的检测概率。

| 类别 | 总测试 | cuCatch 检出 |
| --- | --- | --- |
| global OOB | 8 | 8 |
| local OOB | 16 | 12 |
| shared OOB | 12 | 10 |
| allocation 内部字段 OOB | 8 | 0 |
| UAF | 4 | 2 |
| UAS | 4 | 4 |
| invalid-free | 2 | 2 |
| double-free | 2 | 2 |
| 合计 | 56 | 40，71.4% |

表内 Compute Sanitizer 为 35.7%，GMOD 14.2%，GPUShield 42.8%。作者实际运行 baseline、Compute Sanitizer 和 cuCatch；GMOD、GPUShield 根据论文描述估计，因为 GMOD 与测试编译不匹配、GPUShield 需要其硬件改动，不能把四工具比较全部描述成同平台实测。

invalid/double-free 由底层 allocator 本身报错，baseline 同样能检出，不能全归功于新标签算法。所有工具均漏过整个分配内部的字段越界；local 同 frame、多个动态 shared 子对象和无标签 unified delayed-UAF 也分别保留。

## 11. 性能、内存及排除成本

平台为 GeForce RTX 2080 Ti、GPU 锁定 1710 MHz、生产 DRAM 频率，Host 为 Core i7-5930K。原文称“12-core”，该 CPU 通常规格为 6 核/12 线程，引用时保留该措辞疑点，不静默改写作者实验配置。

共 176 项工作负载，含 87 个 standalone kernel、PolyBench-ACC 和部分 CUDA Samples。排除 in-kernel malloc、Dynamic Parallelism 和仅含预编译库的样例。只有 5 项达到至少 240 个 live allocation，主性能结果主要覆盖直接索引占优势的分布。

| 项目 | 作者结果 | 必须保留的口径 |
| --- | --- | --- |
| Shadow TBB | 几何平均 1.19×，约 19% 额外时间 | 部分 workload 超过 2×；不是所有应用最多 19% |
| 全部走 shadow 的变体 | 几何平均 1.25×，最高 3.22× | 更接近缺少指针高位快速路径的条件 |
| 编译优化 | 相对未优化版平均改善 4%，个别 app5 改善 80% | 不等于相对 native 提升 80% |
| 对 Compute Sanitizer | 平均快 63× | 两者检测内容和插桩技术不同 |
| compulsory 元数据 | BST 32 MB + shadow 一级表 128 MB | 小应用相对开销显著，不能只引用百分比 |
| shadow 二级表 | 每 32 B 数据需 4 B，约 12.5% | 在需要 shadow 的分配上按需增加 |

CUDA Samples/PolyBench 用应用自带墙钟，standalone 用 Nsight 的 GPU-only 时间、不含 kernel launch。作者还排除了拦截内存分配和 BST/shadow 更新的成本。即使认为这些通常可忽略，也不能将 19% 称为完整端到端成本，尤其统一内存维护随大小增长。

14/176 项出现 occupancy 降低，其中 11 项减速；23 项 spill 增加，说明插桩寄存器与并行度的变化也影响结果。少数加速来自资源使用改变，作者通过给 baseline 增加寄存器做对照。将元数据迁移到 unified memory 以扩容是未来工作，不当作已测结果。

## 12. Artifact 与复现证据

NVIDIA 官方页面提供正式稿，但本次未确认与论文匹配的公开 cuCatch ptxas fork、修改驱动、完整 56 项测试和 176 项性能输入发布。论文没有可直接运行的 artifact 附录。公开 CUDA Samples、Compute Sanitizer 或 NVBit 不是 cuCatch 实现，不能用它们代替缺失的工具链源码。

因此本篇完成全文和官方元数据研读，没有声称源码审计、固定 cuCatch 实现提交、检测覆盖重算或新 GPU 复现。结果均为作者报告，公开实现缺口限制了独立检查优化顺序、元数据更新并发和误报行为的能力。

## 13. 与其他论文及本项目的关系

| 工作 | 与 cuCatch 的关系 | 对项目的边界 |
| --- | --- | --- |
| GMOD / clARMOR | canary 检测部分越界写，难覆盖 OOB 读和跨越 canary 的访问 | 检测到错误不等于租户隔离 |
| GPUShield | tagged base/bounds 硬件方案 | index 容量、空间与时间安全分开分析 |
| GPUArmor | 后续硬软协同内存安全工作，需另读其原文 | 不凭标题认定完全覆盖 cuCatch 局限 |
| ACAI / PhantomMap | 设备归属、实际物理页及映射生命周期 | Client 内对象检查不能替代跨 Client HPA 授权 |
| PORTAL / CAGE | 可信设备服务、真实映射和执行环境 | TEE 外部隔离与可信应用内存安全可互补 |

本项目已接受可信 ProxyRealm、RMM 认证原始 Client、软件 IPA→HPA 授权及受保护 GPU Stage-1。cuCatch 不构成推翻这些假设的理由，也不要求因 NVIDIA 指针格式不同而改写 Arm GPU 设计。

它说明“页级隔离足够”需要限定目标：若只要求恶意 Client 不能访问别人的页，现有授权方向合适；若还要保护同一 Client 中多个对象或避免可信 GPU 代码被输入触发越界，就属于另一项明确安全目标，需要更细对象语义。

## 14. 可迁移的设计与独立判断

项目已有 GPUVM、认证队列、私有快照、真实 fence 和 cookie/epoch。可借鉴的是让每次提交使用的对象身份、backing generation、合法子区间和权限保持一致，并说明缓存授权或合并检查为何仍适用于当前生命周期；没有必要仅为引用论文新增短随机 tag。

若研究可信任务内部内存安全，可增加可选编译期检查和对象级负例，用于发现页内 OOB/UAF；要把它提升为恶意代码隔离，就必须额外保护检查不可绕过、元数据不可伪造、无标签路径不可滥用，并在有副作用的访问前完成授权。本文原型并未证明这些要求。

独立评价：cuCatch 对分层对象边界、快速/慢速元数据路径及调试优化有清晰贡献，覆盖和成本也披露具体限制。对本项目最有用的结论，是区分跨 Client 内存授权、Client 内部对象安全以及错误报告三个不同目标，再为每项选择可验证机制。

统一记录：GPU 对象内存安全全文研读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无新增硬件 run-id 或 PASS｜作者报告、实现限制与项目推断分开保留。
