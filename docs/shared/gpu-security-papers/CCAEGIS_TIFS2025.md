# CCAegis：CCA 函数级隔离、敏感数据分析与公开原型边界

研读日期：2026-10-27。完整研读 16 页作者公开稿、核对 Crossref 正式书目，固定论文指定仓库提交，并定向阅读 Monitor/GPT、向量、LLVM 插桩、分析器及驱动相关路径。未编译、运行 FVP、执行攻击或进行板端实验。未改运行代码，无新增性能测量。

## 1. 书目、全文与固定实现

| 项目 | 内容 |
| --- | --- |
| 标题 | More Granular, Less Trust: Enforcing Intra-Process Isolation With Arm CCA in an Untrusted Management Environment |
| 系统 | CCAegis |
| 作者 | Shiqi Liu、Zhouqi Jiang、Jie Wang、Wei Zhou、Kun Sun、Zhaohui Chen、Yulai Xie |
| 正式发表 | IEEE TIFS，2025，20:12507–12522 |
| 正式 DOI | [10.1109/TIFS.2025.3634981](https://doi.org/10.1109/TIFS.2025.3634981) |
| 实际全文 | [arXiv:2608.20584v1](https://arxiv.org/pdf/2608.20584)，2026-08-20，16 页 |
| PDF SHA256 | `ae8966b9eca81cfbf459c66d55a872cb5f1593af5e720f39ea578d590222149d` |
| 论文指定代码 | [erhade/CCAegis](https://github.com/erhade/CCAegis) |
| 固定提交 | `0f93d9a292b3caaf1534c7a39abb0cb5660fd5bc` |

2026 是本次公开 arXiv 稿的上传年份，正式期刊年份为 2025；不能按 arXiv 编号把它改称 2026 新架构。本次未取得 IEEE 排版稿进行逐字差异比较，机制和实验分析以所读稿为准。

它保护 Normal-world CPU 应用的敏感函数，不是 GPU TEE。与 PORTAL/CAGE/ACAI 的联系在于缩小可信服务边界、保护原始授权状态及处理异常上下文，不能代替设备映射或 GPU job 隔离。

## 2. 研究动机与基本方法

CVM 隔离仍将 Guest OS 纳入应用信任范围；SHELTER 将 OS 排除，却把应用整体作为保护单元。CCAegis 进一步区分同一进程中的敏感函数和普通逻辑，以减少应用内存漏洞触及密钥的机会。

开发者标记 taint source 和 sink，编译器通过上下文敏感 points-to/taint 分析识别密钥及派生数据，自动安排敏感内存和权限切换。Root Monitor 管理 GPT 和关键状态，OS 负责调度、分配与普通服务；不可信驱动提供虚实地址语义，由 Monitor 检查。

核心贡献是自动分区与可信运行期配合：它既不要求整个 Guest OS 可信，也不只把“敏感”标签当作约定。其正确性仍依赖初始标签、分析与插桩覆盖、实际装载代码和运行期检查相互一致。

## 3. 威胁模型、信任与排除项

考虑进程内越界和控制流劫持、恶意 OS/Hypervisor、Secure/Realm 软件、DMA、异常寄存器窥探、伪造映射和部分内存类 Iago 攻击。敏感函数内部漏洞和主动泄密、物理攻击、微架构侧信道及 DoS 排除。

运行期信任 Root Monitor 和正确实现 CCA/RME 的硬件；离线标签、构建及分析的正确性也构成实际保护前提。论文称分析离线而不受运行期攻击，不能进一步推导分析工具错误不会影响安全。

§VII-B 明确既有 TF-A 2.9.0 约 479K LoC，新增可信改动 1803：内存隔离 990、异常拦截 483、敏感 I/O/随机数 154、其他 176。1803 是增量而非完整 TCB。编译器约 2K、驱动约 1K 的规模与运行期可信代码分开。

## 4. 静态分析与自动分区

Taint IR 定义 alloc/load/store/index/merge/call/return，并用字节区间跟踪结构体和数组成员；调用点生成上下文，source 开始传播，erase/sink 停止传播。涉及敏感地址的 load/store 使包含它们的函数进入敏感集合。

敏感变量从普通堆、栈和全局区搬到 crypto buffer，内部再分 crypto stack/heap/data；GPT 最小 4KB 粒度。普通全局输入复制到 crypto stack 后使用，不能由“复制”自动推出语义校验已经充分，接口值和长度仍需验证。

相同函数在敏感和普通上下文都可能被调用，论文通过上下文区分和版本化避免普通路径复用内部重新授权入口。对 key-related malloc/free、I/O 和随机数生成安排可信替代服务。

作者在 §VI 描述无法解析的 tainted call 采用保守敏感处理，但 §VIII 明确不声称消除全部 false negative：间接/隐式控制流、汇编、遗漏 source/erase 标签仍是风险。不能引用中段“不会遗漏真正 crypto 函数”的宽泛措辞，掩盖最后给出的限制。

## 5. 三类 GPT 和实际映射检查

Host GPT 供 OS/普通应用使用；每个 CCApp 有 Crypto GPT 与 Non-Crypto GPT。每核按当前上下文切换 GPT，因此其他核运行 OS 时不应获得敏感核的访问权限。

Host 视图中只有 normal 内存可委托；所有 GPT 更新需同步，防止陈旧视图造成重叠。其他 Client/世界得到内存后，应同步从已有 CCApp 视图排除。

委托页表先阻断 OS 修改，再检查实际映射，防止检查期间 TOCTOU。检查敏感 code/buffer 唯一映射、页表和向量不可被应用恶意别名写入、代码只读可执行且其他区域不可执行。运行期 OS 更新影子页表，由 Monitor 核验并同步到受保护实际页表。

这和项目“软件 IPA→HPA 授权后合成 Stage-1”的研究假设相容：重要的是控制实际翻译与实际物理页，以及保持校验结果到执行期间的有效性。CCAegis 的 CPU GPT 安排本身不能充当 GPU Stage-1 页表已经安全的证明。

## 6. 调用门状态与异常处理

四种门为 GPERM、RPERM、INRPERM、INGPERM：进入敏感函数授权，离开撤销；调用普通函数前临时撤销，返回后再授权。论文提出按状态机约束转换，并核对内部重新授权地址与之前撤销点配对。

门使用 svc 的立即数编码服务类型，经过受保护向量再 smc 进入 EL3，避免单凭可修改的普通寄存器决定服务。Monitor 用当前 GPT 识别执行主体，管理敏感栈，离开时清理寄存器。

普通异常也先进入 Monitor，保存敏感上下文、切换 Host GPT 后才交给 OS；返回时恢复对应线程的 GPT、寄存器、异常返回地址和向量。每线程有独立敏感栈，普通 futex 放在非敏感区。

这些机制保护中断时上下文的机密性和恢复完整性。它们不认证某个 GPU job 已完成，也未提供跨 Realm completion 与 Client/cookie/epoch 的绑定；可信 handler 和真实事件原因仍须分别论证。

## 7. 敏感 I/O、熵与销毁

论文设计将封装 key 从 OS buffer 复制进 Monitor，校验文件签名属于当前 CCApp后解密，再写入合法 crypto buffer；Host memory 和 crypto memory 两端均检查边界，以防解密 oracle 和跨世界复制。随机数由硬件 RNG 提供，销毁时清理 buffer、cache 与寄存器后归还内存。

内容签名归属检查不自动提供新鲜性；旧合法 key 文件、实例克隆、策略撤销和回滚需要额外生命周期定义。论文也未给出完整的远程 attestation 与密钥释放 transcript。

对 GPU 项目，内容清零应发生在最后可能访问该页的设备事务结束之后；CPU 函数返回、GPT 切换、epoch 改变都不能独立证明在途 GPU/DMA 已停止。论文的 CPU 清理不能直接代替设备 revoke/drain/invalidate/scrub 协议。

## 8. 实验平台与安全证据

功能原型在 FVP 验证 RME/RNG 语义；性能原型在 RK3399/Rock Pi 4B 使用替代 EL3 寄存器和完整 TLB flush，固定 A72 1.8GHz、关闭 A53。RNG 性能替代由 SP/LR/计数器构造，不是安全随机数实现。

静态分析用 LLVM 10.0.1、-O2，运行于 96 核 Kunpeng-920/256GB；Guest 相关修改基于 Linux 6.6-rc6，Root 使用 TF-A 2.9.0。接受模拟硬件研究方法，但功能安全验证与板端性能路径分开记录。

Table IV 主要是攻击类别与设计防护的对应，没有提供每类攻击的完整复现输入、次数、成功率和原始结果。不能把该表等同所有攻击均已系统重现并阻断，也不能把论文式安全讨论当形式化证明。

## 9. 实验数字和需要保留的口径

| 项目 | 作者报告与限制 |
| --- | --- |
| 敏感代码比例 | 四个密码库 10.57%–35.26%；不是剩余所有程序状态都不需信任 |
| 标签人工耗时 | 1.72–5.48 小时，5 名研究生；少量标签不等于无需语义理解 |
| 编译耗时 | wolfSSL 34.41→103.06s；ccrypt 2.52→15.84s |
| 创建/销毁 | 空应用 10000 次；额外 16.99/1.90ms，启动成本不能因一次性就从端到端预算消失 |
| GPERM/RPERM | 1211/1269 cycles，100 万次；不是当前项目 RPC 或 GPU 切换成本 |
| Nginx | ≤80 Client 时下降 <10%；350 Client 最大吞吐下降 42.72%，更高并发出现连接失败 |
| wolfSSH | 建连平均增加 25.35%，约 27.2ms；不等于长连接所有流量均有同一比例开销 |
| ccrypt 加/解密 | 5.10%/4.35%，10MB 数据，各 1000 次 |
| libhydrogen 加/解密、libxcrypt | 0.61%/0.31%、0.84%，同样是特定测试 |
| wolfSSL AES-GCM 压力 | 2048B 输入，最高 75.80% 开销；超出摘要约 1.01–1.43 倍的概括 |

Nginx 1.21.4、wolfSSL 5.1.0、指定 TLS cipher、32KB 文件、10000 请求，启用 keep-alive，基线未插桩且不经过 loader。42.72% 是吞吐损失，不能改称完成时间只增加 42.72%，更不能与 glmark 直接比较。

SHELTER 对照由作者将功能原型移植到该板，并非原论文开放的性能版本。相对 SHELTER，密码库额外 <0.83%、wolfSSH 7.43%、Nginx 最大 16.92%；它不是与 Native 相同口径。

wolfSSL false positive 表中 46 个与 1.91% 的分母不直观，正文也承认无完整 ground truth，不能把它解释成所有真实秘密流遗漏率为零。公开单一 RESULTS 片段不构成论文完整原始数据。

## 10. 固定公开实现的结构和审计范围

固定仓库包含 TF-A/Linux 源树、driver、loader、LLVM pass、Rust taint-analyzer、结果合并及 shell compiler wrapper。根 recursive tree 返回 65346 项且 truncated，因此本次不声称取得完整根树；另外取得 src 目录、driver 列表和未截断的 pass/analyzer 子树。

定向阅读范围包括 README、compiler wrapper、Monitor 的委托/切换/复制/销毁、向量汇编、driver、插桩 pass 的相关函数、Rust 分析器的数据结构及测试结果片段。没有逐行审核整个 Linux/TF-A，也没有执行仓库构建脚本。

源码中的 CrypCCA 命名不影响它是论文明确指定的 CCAegis artifact；但“匹配仓库”不意味着公开 HEAD 与所读论文所有防护完全一致。

## 11. 公开代码与论文设计的具体差异

以下均针对固定提交的定向静态事实，不是已执行的漏洞利用或所有版本结论：

1. TF-A 的 `lib/gpt_rme/gpt_rme.c` 中，委托路径约 2091 行的 signature segment 检查仍是 TODO，不能据此认定已验证租户指定程序内容。
2. `crypcca_read`/`crypcca_write` 约 2807/2886 行分别保留解密/加密 TODO；所读路径直接复制数据，没有实现论文提出的完整封装 key 签名验证和加解密链。
3. `crypcca_set_key` 约 2434 行读取 RNDRRS 后有 NOTICE 输出随机值。是否暴露依赖实际编译日志级别和输出可见性，但不能未经配置核验就作为安全密钥生成部署。
4. `crypcca_exit_enclave` 和 open/close helpers 可看到 GPT 身份、线程查找、svc 解码及指针/栈范围检查；未在这些所读路径确认论文图 7 的完整四态门及 INRPERM/INGPERM 配对返回地址验证。已有 `protect_regs` 布尔值不能自动等同完整状态机。
5. `crypcca_exit_enclave` 在任务查找时使用全局 tasks_lock；论文称切换热路径跨核无锁，公开该路径需要额外解释，不能直接用论文断言替代源码事实。
6. 插桩 pass 存在按密码函数名称跳过处理的特殊分支，并有特殊循环路径；迁移至其他程序前须确认其假设和调用者，不能当作任意输入的完全通用分析器。

相比只按 README 复述设计，这些差异更有助于项目区分“安全目标、可信执行不变量、公开原型覆盖、已测证据”。本次没有确定这些差异的攻击可达性、完整影响或是否已被作者其他版本解决。

## 12. 单敏感域和 NanoZone 的关系

§VIII 明确当前每个 CCApp 只支持单一 crypto domain，多域是扩展设想；不能称其已经完成同进程多 Client 独立密钥域。多线程独立栈和多核切换也不等于每个租户有独立访问域。

NanoZone 则以 POE/PIE/GPC3 组合实现更多域和大多数用户态切换，并增加 GCS/PIM 保护；但保留同类型目标复用。两篇可按“函数敏感区→多域容量/切换效率”比较，不能仅凭共同作者就断言正式扩展关系。

两者主要是 CPU 保护；CAGE/ACAI 研究设备访问与实际页归属，PORTAL 研究可信设备服务。应在文献图谱中分清职责，避免把 CCA 相关工作的数量当作 GPU 隔离方案的数量。

## 13. 对项目的具体设计启发

当前已有 RMM 原始 Client 认证、GPUVM、私有描述符快照、认证队列、真实 fence、cookie/epoch 和 persistent IRQ127。值得补充的是它们的组合约束及证据，不是重新宣称需要添加这些基础机制。

| 研究方向 | 建议写明或进一步研究的内容 |
| --- | --- |
| 服务最小权限 | 区分解析/调度与实际映射、完成发布、回收的权限；若拆分 Proxy，明确谁仍可改 SMMU 和任务私有状态 |
| 实际对象授权 | 每次敏感操作绑定 RMM Client、对象代次、权限、会话和当前任务状态；合法服务入口不等于合法操作 |
| 异常和通知 | IRQ 仅唤醒，可信状态判断才推进真实任务；保护 ACK、错误、取消、reset 和迟到事件路径 |
| 回收 | 在途访问停止、翻译失效、私有元数据失效和实际内容清理分别给出依据 |
| 构建与证明 | 租户认可的镜像内容、工具链/策略摘要与当前服务实例绑定，不能以固件安全启动代替全部应用证明 |

这些是以既有设计为基础的研究建议，是否已有充分实现证据应继续按代码和测试逐项判断。不能根据其他论文的 TODO 直接推断当前项目存在同样缺陷。

## 14. 研究定位与独立评价

CCAegis 的价值是让“更小保护单元、较小在线 TCB、自动分区”形成具体流程，并详细描述映射委托、异常上下文和敏感 I/O 的边界。其限制是单敏感域、分析/标签覆盖依赖、快速小函数压力开销，以及公开实现与完整论文安全机制之间的差距。

对项目最合适的用法是支撑可信 Proxy 的内部安全边界与敏感操作状态机；GPU 内存和中断任务隔离仍应以 CAGE/ACAI/PORTAL/PhantomMap、可信 I/O 与中断攻击文献为主。论文没有要求将现有 ProxyRealm 改为 Normal-world 进程，也没有否定受保护 Stage-1 软件合成的研究假设。

统一记录：16 页作者全文、正式元数据与固定公开实现定向审计｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无 FVP/硬件 run-id 或新增 PASS｜CPU/CCA 细粒度隔离支撑，不计作新增 GPU TEE 架构。
