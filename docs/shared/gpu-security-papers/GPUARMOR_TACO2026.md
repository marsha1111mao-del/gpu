# GPUArmor：GPU 对象安全、授权元数据缓存与并发释放边界

研读日期：2026-10-27。已完整研读 NVIDIA 官方提供的 25 页作者预印本，包括威胁模型、设计、覆盖分析、全部实验与参考文献，并核对正式 DOI 元数据。没有构建工具链、运行模拟器或 GPU。未改运行代码，无新增性能测量。

## 1. 书目信息与版本

| 项目 | 内容 |
| --- | --- |
| 标题 | GPUArmor: A Hardware-Software Co-design for Efficient and Scalable Memory Safety on GPUs |
| 作者 | Mohamed Tarek Ibn Ziad、Sana Damani、Mark Stephenson、Stephen W. Keckler、Aamer Jaleel |
| 正式发表 | ACM Transactions on Architecture and Code Optimization，23(3)，2026；Crossref 登记在线发表 2026-07-23，1–25 页 |
| DOI | [10.1145/3815783](https://doi.org/10.1145/3815783) |
| 官方入口 | [NVIDIA Research](https://research.nvidia.com/publication/2026-05_gpuarmor-hardware-software-co-design-efficient-and-scalable-memory-safety-gpus) |
| 实际所读版本 | 官方页面链接的 TACO2026_GPUArmor_preprint.pdf，25 页；页脚仍为 Vol.1/No.1/January 占位排版，不用它替代正式卷期 |
| 原文 | [官方作者预印本](https://d1qx31qr3h6wln.cloudfront.net/publications/TACO2026_GPUArmor_preprint.pdf?VersionId=Ob0eQ3K1kRgq3riGLP3adyVyQZxJf6wE) |
| PDF SHA256 | `389bc998a3ea7ba94506f756e4ddb5406a5562be74607af8c1c1f0e42bbca212` |

首页明确说它是 cuCatch（PLDI 2023）的期刊扩展，新增工作负载特征研究、ISA、硬件结构和实验。可单独分析版本增量，但不能把它和 cuCatch 算作两套独立 GPU TEE 架构。GPUArmor 本身也不是 CCA 或完整 TEE。

## 2. 问题与贡献

cuCatch 软件方案的 shadow 路径按数据容量维护元数据，约增加 12.5% 空间；GPUShield 的指针高位直接索引限制可跟踪对象数。GPUArmor 改为每对象一个小元数据记录，通过编译器识别 root pointer，配合专门的加载、边界检查指令和每 SM 缓存，隐藏树遍历成本。

论文的重要观察是：同时存活对象数可以上千，但一个 kernel 某时刻真正访问的对象集合较小。因此底层查询可以较慢，只要热点元数据在缓存中。它把“元数据结构的容量”与“快速路径的工作集”分开，而不是假设全部对象必须放入固定硬件表。

这是作者所研究负载的经验规律，不是所有恶意任务必须满足的约束；论文也给出了大工作集压力测试。

## 3. 威胁模型与可信条件

§4 假设 device-side 应用存在可被输入触发的空间/时间内存错误，攻击者可借此试图任意读写。攻击者不能在首先绕过保护前自行提交 GPU kernel，也不能直接跳转到任意 gadget。默认每进程独立 GPU 代码和虚拟地址空间，GPU 硬件可靠；侧信道、隐蔽信道及 CPU 代码内存错误不在保护范围。

因此，允许恶意 Client 自带 GPU 二进制的 ProxyRealm 项目不能直接照搬该结论。论文信任编译、运行时、分配包装和硬件检查路径；没有提供恶意 Hypervisor 下的证明、SMMU 管理、Realm 身份认证或可信中断协议。

对象元数据区域对 device 为只读。只读可以防止普通 kernel 篡改授权表，但仍须依赖正确的元数据更新者、页保护及检查不可绕过。论文默认的进程隔离不能被当作它新证明的跨租户隔离。

## 4. 负载特征：为何选择对象表与小缓存

主实验使用 28 个工业负载 kernel，覆盖 amber、namd、AMG、FUN3D、Laghos、lammps、Relion、RTM、5G decode、OptiX。表 2 的 live allocation 可达 1184，三个 kernel 超过一千；对象工作集均小于八。中位对象大小跨 256 B–236 MB，最大约 1.7 GB。

作者统计 global/shared 各约占动态指令 6%；主负载没有 local/generic 操作。这个条件支持主实验把硬件重心放在 global/shared，但不能据此断言所有 GPU 程序都不使用栈、generic 或 spilling。追加传统及 ML/graph 负载中存在更大工作集，论文用 16 项缓存改善部分案例。

对项目的可迁移点是先测“授权缓存工作集”及 miss/失效成本，再决定缓存容量；单 Client 图形场景的热点分布不能自动代表多 Client 切换和恶意压力分布。

## 5. 分配生命周期与元数据结构

程序启动保留元数据虚拟地址区。每次分配生成随机 tag，把 16 B 的 tagged base 与 size 保存到结构中，同时将 tag 放入指针高位；57 位地址时通常有 7 位 tag，48 位地址时可有 16 位。检查通过后清除高位再进行实际访问。

论文比较链表、平衡二叉搜索树和不可实现的理想 SoL 表。链表/树每节点 32 B：16 B 记录加两个 8 B 指针；SoL 每项 16 B，依赖 oracle 直接找到对应位置。不能把 SoL 当作可部署硬件成果。

释放保留 base/size，把 tag 设为保留值，如 7 位模式的 0x7F，并使 MLB 缓存失效。新对象重新随机打标；重复地址的 delayed UAF 由 tag 不同检测，存在碰撞。脚注允许超过阈值后回收已删除元数据项，但没有给出任意长执行下完整回收证明；评估中未触发该条件。

## 6. ISA 与检查位置

| 指令 | 作用 | 关键区别 |
| --- | --- | --- |
| LOADMETA | 用编译器识别的 root pointer 搜索元数据，返回元数据地址并填充 MLB | 不把可能过期的 tag 长期保留为寄存器授权；无记录或标签不匹配时返回零 |
| MEMCHECK.G | 按元数据地址取得当前 base/size/tag，做 global 边界和时间检查，返回去标签地址 | 失败触发设备异常；对应实际访存仍是后续独立指令 |
| MEMCHECK.S | 用编译期 shared base/size 检查 | shared 在 kernel 期不可释放，因而不使用相同 temporal tag |

LOADMETA 不立即报错，以避免仅计算坏指针而未解引用时产生误报。编译器在 global/shared 实际访问前插入 MEMCHECK，root 位置才做元数据查找，可减少重复遍历并保留部分指针来源信息。

异常可交给 Host handler 终止，也可报告后继续。研究隔离时必须明确失败是否阻断相应读写以及异常如何影响任务状态，不能仅以“有异常”证明其他 Client 不受影响。

## 7. MLU、MLB 与失效一致性

Metadata Loading Unit 位于访存合并逻辑与 L1 之间，负责虚拟地址空间中的元数据遍历。普通访问可透传；LOADMETA 和 MEMCHECK 使用专门逻辑。

MLB 每项 24 B，保存 base/size/tag 及元数据位置。LOADMETA 按地址区间匹配，MEMCHECK 按元数据地址匹配；miss 分别走结构遍历或直接元数据加载。主设计每 SM 八项，释放时失效。16 项版本约 384 B/SM，另有比较和遍历逻辑。

§8 并发 UAF 分析强调，每次 MEMCHECK 都要取得当前 tag，而不是沿用寄存器里的旧 tag。这比仅初始化时验证提供更明确的新鲜性要求。但论文没有在本文展开跨 SM 失效确认、与并发释放的全局顺序、MEMCHECK 到后续实际访存之间的原子性，也未细化跨进程切换时缓存的身份标记/清空协议。

上述为本次阅读发现的论证范围，不能直接宣称硬件必有漏洞。对项目则可作为检查项：缓存命中必须仍绑定当前 Client、对象代次和设备 epoch；失效完成与旧 DMA 真正停止分别说明。缓存命中不能省掉生命周期授权。

## 8. 编译器分析、二进制模式与兼容路径

root pointer 分析继承 cuCatch 的过程内 reaching definitions。能追踪算术来源时，先取得原对象元数据再检查派生地址；跨过程或指针从内存重新加载时，可能只剩中间地址，退化为概率标签检查。

作者分类的动态 MEMCHECK.G 中，55.5% 可取得真实 base、36% 为部分 base/bounds、8.5% 相当于 memory tagging。不能把“所有访问都有检查指令”写成“所有访问都恢复真实对象来源”。shared/local 经 generic 地址访问时只能做较粗范围检查。

GPUArmor-Binary 不需重编译，由硬件在每次访问触发 LOADMETA/MEMCHECK 功能，但失去来源分析，越到另一 live object 时只能概率检测。运行时分配包装和新硬件仍必要，不能说原有 GPU 直接运行未修改应用即可获得保护。

兼容模式保留 0x0 tag，只有非零 tag 才进行相应查询/检查，以容纳未感知 GPUArmor 的代码。它属于既定应用模型下的兼容条件；若 Client 可构造任意无标签地址或直接发二进制，不能拿这一模式当不可绕过的沙箱。

## 9. 覆盖率、概率与未覆盖项

7 位 tag 中 0 与 0x7F 保留，有效随机颜色 126；标签型路径的理论单次检测率约 1−1/126=99.2%。它依赖标签分布和使用条件，不是任意攻击成功概率上界，也不是完整测试集测得的漏洞覆盖率。

| 错误 | 完整编译模式 | Binary 模式及限制 |
| --- | --- | --- |
| 相邻对象 OOB | 表 4 列为 100% | 要求相邻对象分配不同标签；不是无条件随机就必然不同 |
| 过程内 non-adjacent OOB | 能保留来源时可确定检查 | 主要依赖标签，约 99.2% |
| 跨过程 non-adjacent OOB | 可能退化为标签，约 99.2% | 同样为概率检查 |
| immediate UAF | 删除专用 tag 可确定检查 | 需删除元数据及缓存及时可见 |
| delayed UAF | 新分配 tag 可能碰撞 | 约 99.2%，不等于确定代次授权 |
| 同一分配内字段越界 | 不覆盖 | 不覆盖 |

HMM 是明确的原型缺口：当前只包装 CUDA device-memory API，未覆盖由 CPU malloc/new 后隐式迁移的分配。HMM 会增大对象工作集，且 CPU 需支持相应 tagged pointer；缺少支持时失去部分 temporal coverage。分离树是未来方向，不当作已实现。

## 10. 实验方法与定量结果

作者修改 ptxas，编译优化为 -O3；在 NVIDIA GA100 收集 vanilla/hardened traces，再用 NVIDIA Architectural Simulator（NVAS）模拟 GA100。每 trace 至少四千万动态指令。新指令、缓存和性能结论来自模拟，不是改造商用 GA100 后的实机测试。

| 配置 / 指标 | 作者结果 | 口径 |
| --- | --- | --- |
| 无 MLB 链表 | 图 9 geomean 2.52×，最高约 29× | 遍历可成为主要开销 |
| 无 MLB 二叉树 | 约 16% 平均、最高 96% | SoL 约 7% |
| 八项 MLB + 二叉树 | 图 10 为 1.084×，约 8% 平均 | 与 native vanilla 二进制比较 |
| 八项 MLB + 链表 | 图 10 为 1.147× | 引言约 13% 的概述不替代实际图表数字 |
| cuCatch 同平台比较 | 平均 36%，最高约 2.2× | 不是 2023 原论文不同负载的 19% 口径 |
| Binary，主负载 | 平均 2.2%，最高 18.1% | LAK 比较为 10%/42.1%，均为本次模型 |
| Binary，追加传统负载 | 八项约 6%，16 项低于 4% | 不能只选主负载 2.2% 代表全部程序 |
| shared 检查 | 低于 0.1% | 以增加 shared 访问延迟建模 |

压力测试有 1024 个 live object，每 warp 32 线程各访不同对象：二叉树额外 189%，八项 MLB 降为 65%，32 项为 39%，SoL 仍为 30%。因此平均小工作集不是对抗输入下的最坏性能保证。

作者排除 memory-management wrapper 的性能成本；端到端分配/释放、全系统失效与可信跨域调用不能从这些数字推得。理想编译器实验将插入指令当 NOP 做对照，开销从约 8% 降至 2.3%；它反映代码生成敏感性，不是当前完整可执行实现已经达到 2.3%。

## 11. 空间与能耗结果的解释

作者对主工作负载宣称元数据约 0.0005% 的 footprint。每对象 16 B、链表/树每节点实际 32 B 的区别应保留；大对象是极小百分比的重要条件，小对象、历史释放项和多进程场景需要重新计算。

Binary 小节将 LAK 描述为每 16 B 使用 8 位 tag，同时给出约 3.25% 空间成本；直接按这两个数计算为 6.25%，与正文数字不直接一致，本次不替作者补出隐藏摊销条件。和 Arm MTE 比较时则使用 4 位/16 B，32 KB 分配的 1 KB 对 16 B 是单条记录的比较，不含二叉树指针。

CACTI/标准单元估计 16 项 MLB 约为 128 KB L1 的 0.2% 面积、单次访问能耗约 5%；作者进一步给出全 GPU 功耗影响小于 0.0006%。本文没有完整功耗系统模型和可重算数据，后者作为作者估计保留，不当作板端测量或新硬件综合报告。

## 12. 公开实现与复现边界

已检查官方 NVIDIA 页面和论文提供的资料，取得完整作者 PDF 与 DOI。以 GPUArmor 名称查询 GitHub 公共仓库未得到匹配结果；这不证明不存在其他名称或未来公开版本。尚未确认匹配的 ptxas 扩展、NVAS 修改、MLU/MLB RTL 和完整 workload trace artifact。

没有用公开 CUDA Samples、CACTI 或其他 GPU 模拟器代替未公开的 GPUArmor 工具链。本篇完成论文与元数据分析，未声称固定源码审计、正式 RTL 验证、实验复现或独立检测覆盖测量。

## 13. 与项目及相关工作的关系

| 工作 | 保护目标 | 对项目的作用 |
| --- | --- | --- |
| cuCatch → GPUArmor | 调试插桩扩展为输入触发攻击模型下的硬件检查和对象缓存 | 分析前置边界检查、当前 tag 与缓存失效；保留期刊版本关系 |
| PORTAL / CAGE / ACAI | 可信设备服务、映射及设备归属 | GPUArmor 默认已有的跨进程隔离需要由这类机制和项目授权负责 |
| PhantomMap | 实际物理页及映射生命周期 | 对象范围/颜色不能替代 HPA 所有者与引用检查 |
| Devlore / SHELTER 期刊扩展 | 可信中断来源/路由、设备分配和 pending | GPUArmor 的 memory exception 不能独自承担跨 Realm 完成语义 |

本项目继续以可信 ProxyRealm、RMM 认证 Client、软件 IPA→HPA 授权和受保护 Stage-1 为基础。GPUArmor 的新硬件假设可以作为研究条件，无需因 RK3588 未提供该 ISA 而否定其思想；但也没有必要为了引用它改变现有内存隔离主线。

## 14. 可验证的设计建议与独立评价

项目已有 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和持久 IRQ127。可继续明确：对象授权缓存的 key 包含身份/代次/权限/区间，命中不跳过必要生命周期核对；失效要覆盖所有可能使用旧授权的执行者；task 的失败和异常与跨 Client 路由、结果发布和页回收分别约束。

可增加授权缓存压力和撤销负例作为未来验证计划：多 Client 使用相同 VA/句柄、旧 backing 在新 epoch 被复用、释放与在途访问交错、缓存 thrash，以及错误任务不得产生成功终态。它们是拟验证性质，没有在本次运行。

如果另设“可信 GPU 程序内部对象安全”目标，可研究可选编译检查。对允许任意恶意 kernel 的 Client，随机 tag、tag=0 兼容和过程内分析都不能取代不可绕过的页级权限；需要的新增安全证明也明显不同。

独立评价：GPUArmor 最有价值的是用真实分配工作集解释元数据容量、缓存和检查成本，并主动披露 HMM、概率覆盖和压力退化。对项目，适合借鉴授权缓存及撤销一致性问题，不宜把 8% 平均开销或 99.2% 理论检测率包装成跨 Client 安全保证。

统一记录：全文、正式元数据及公开资料研读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增 PASS｜作者模拟结果、原型边界与项目推断分别保留。
