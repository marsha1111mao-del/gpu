# DMGuard：CPU / GPU / IOMMU 实际物理页生命周期保护与项目启示

## 1. 定位与结论

《DMGuard: Safeguarding Kernels from Physical-Page Use-After-Free Vulnerabilities》，Juhee Kim、Jaeyoung Chung、Dae R. Jeong、Byoungyoung Lee，首尔大学；前两位共同一作，后两位通讯作者。作者出版页及代码仓库标为 USENIX Security 2026。正式会场页面本轮超时，未核正式页码、论文 DOI 或出版日期；Zenodo DOI 是 artifact 标识，不能冒充论文 DOI。

它研究集成 GPU 系统中 CPU、GPU、IOMMU 页表对实际物理页的悬空引用，直接补充 PORTAL / CAGE / ACAI 的隔离设计。它本身不是 CCA GPU TEE 架构，也没有解决恶意 Host 下的 Client 身份认证。最值得本项目吸收的是：必须同时拒绝“仍有映射就释放”和“用旧页引用重新映射”，而且分配器内部页池的归还也属于生命周期边界。

最重要的未覆盖边界：论文 §7 明确把 dangling TLB 留作后续工作。因此 MapCount 归零不独立证明 GPU 已停止 DMA，也不独立证明页面可以跨 Client 安全复用。中断通知、任务终态、输出可见、应用正确、结果发布、DMA 静默和安全回收仍须分别论证。

## 2. 来源、版本与阅读范围

[作者出版页](https://compsec.snu.ac.kr/publications)、[作者全文](https://compsec.snu.ac.kr/papers/dmguard.pdf?download=1)、[作者代码](https://github.com/compsec-snu/dmguard)、[官方会场入口](https://www.usenix.org/conference/usenixsecurity26/presentation/kim-juhee-dmguard)、[artifact DOI](https://doi.org/10.5281/zenodo.17970502)。本轮官方 PDF 请求超时、Zenodo API 连接拒绝；保留失败，不以无关 Crossref 搜索结果补充论文书目。

取得作者 19 页全文，635022 字节，SHA256 `b77386d4042704c11e11e250614563b94ce902eca5b44e923d48febebebd7202`。完整阅读 §1–9、伦理与开放科学声明、95 条参考文献及 Appendix A.1；9 图、9 表均覆盖，视觉核对第 2、3、4、5、6、7、8、9、11、12、13、14 页。未与出版方字节比对。

作者仓库默认 master，固定提交 `41980cb5df8651ffd0da904d1756c7f217c7a4f8`，取得不截断的 112 项树。选择 10 个 blob 核对 Git SHA1 与 SHA256；完整读 README、安全 runner、性能 runner、三个结果分析脚本及 synthetic 补丁，定向读 r52p0 核心补丁、Mali 补丁和构建脚本。不是完整内核、所有驱动版本或全部 exploit 审计。未执行作者安装、攻击、构建、QEMU 或硬件测试。

## 3. 威胁模型与可信边界

攻击者是本地不可信进程，可以发起系统调用和 GPU kernel，利用内核或驱动的物理页管理错误。CPU、MMU、GPU 以及防护插桩和元数据本身被信任；允许被插桩内核路径存在生命周期漏洞，不等于容忍 Host 任意修改所有防护状态。

重点追踪提供用户态访问的映射；不是对全部 kernel direct map、任意 copy_page 路径或所有物理内存访问实施能力检查。PageJack 式页复制、绕过受监控接口的直接 PTE 改写、页元数据破坏、TLB 残留与离散 GPU VRAM 扩展，分别有范围限制。不能将这些限制隐藏在“覆盖 CPU/GPU/IOMMU”这一总称里。

项目的 RMM 原始 Client 认证、可信 ProxyRealm、页表/根配置/MMIO 保护仍是更外层必要条件。把 DMGuard 元数据放在不可信 Host 可写内存中，不会获得同等跨 Realm 安全保证。

## 4. 漏洞对象：两个不同的时间错误

Free-Before-Unmap：真实物理页还被某个 CPU/GPU/IOMMU 页表引用，却已被归还给分配器。页重新分给另一个用途后，旧 VA 可访问新所有者内容。只检查待建立映射的页归属，不能发现已经保留的旧别名。

Map-After-Free：映射数可能已为零，但驱动还持有过期 struct page 指针或 PFN；页面释放、再次分配后，旧引用又被用于建图。普通引用计数无法区分“当前有效引用”和“数值相同的旧引用”。这正是本项目 handle / cookie / BO / 实际页 generation 必须绑定的原因。

CVE-2025-0072 示例说明 CPU/GPU 分配器与页表交叉后，仅检查某一种 VA 不够：两个映射关系及延迟 fault/unmap 的组合，可让释放逻辑与仍存在的另一映射脱节。安全记录应按实际页归并别名，不能仅按 Client 自报 IPA、某个 BO 句柄或某个地址空间单独计数。

## 5. 状态机、计数与标签

页面状态由 allocated/unallocated 与 mapped/unmapped 两个维度组成。MapCount 汇总 CPU anonymous、CPU file 和 device 映射计数；device 涵盖 GPU/IOMMU。PageTag 存在实际页元数据中，RefTag 随 struct page 指针及 tagged PFN 传播。

分配/释放改变 PageTag；建图比较 RefTag 与 PageTag；释放要求所有映射数为零。RefTag 的价值是保留引用产生时的生命周期信息，而不是每次使用旧 PFN 都重新读取当前 PageTag——后者会把旧引用重新合法化。

论文图 8 的顺序是 MapCountInc → full_memory_barrier → tag check → Map；Free 是 TagUpdate / atomic_xchg → full_memory_barrier → count check → Free；Unmap 是实际 Unmap → MapCountDec，并检查计数下溢。它避免粗粒度锁，但仍依赖原子操作和正确的内存顺序。

作者称使用 LKMM litmus 检查 Map-Free、Alloc-Map、Free-Unmap。已取得的 112 项仓库树未见对应 litmus 文件，本轮未运行 herd 或取得完整证明。应标为作者验证声明，不能称本次独立复核了完整并发证明。

## 6. 实现覆盖与标签编码

实现复用 Linux page_table_check，扩展 device 计数与 tag；CPU 接入 set_pte_at、ptep_get_and_clear/full、post_alloc_hook、free_pages_prepare，Mali 接入 entry_set_ate / entry_set_pte、entries_invalidate、pool alloc/free 及部分页释放，Adreno 接入 arm_lpae / kgsl pool 等路径，具体列表见 Appendix A.1。

GPU pool 位于 buddy 分配器之上：归还 pool 即可能进入下一次 GPU 分配生命周期，不可等最终归还 buddy 才检查。大页按每个 4KiB 页更新；迁移有专项讨论，但不构成任意迁移/别名/回滚组合的完整证明。作者约 400 核心 LOC、560 PFN 宏、90 Mali / 80 Adreno LOC，不等于全部集成、移植和维护成本。

指针利用 top byte 携带 8 位 tag；PFN 使用 tagged_pfn_t 并显式剥离。§4.2.2 将 default 写为 0，§5 写随机 0x00–0xFE、default 0xFF；代码 pfn_tag 还出现 XOR 0xFF，说明指针和 PFN 编码存在转换。应逐路径核编码，而不是把两个默认值直接视为可利用漏洞。

## 7. 概率标签不能替代授权身份

作者给跨分配检测率 254/255，约 99.6%；排除紧邻旧 tag 时，即时释放后的旧引用必不匹配。该结论依赖实际实现真的执行排除、保留原始 RefTag，并且没有默认标签绕过。

本轮自写算术在“255 个可用值，均匀抽取且每次排除前一个值”的条件模型中得到 p0=1、p1=0、pn=(1−p(n−1))/254，p2=1/254，长期极限 1/255。不能把一次碰撞概率当任意生命周期的密码学新鲜性保证，也不能在没有独立性前提时套用多次攻击成功公式。

项目宜使用可信宽 generation、活跃对象记录及严格禁止旧引用复活的状态转换；不能拿 8 位随机 tag 充当 RMM Client 身份、MAC、跨 Client 权限或 reset epoch。generation 回绕也须定义拒绝或安全停机策略，不能默认永不发生。

## 8. 公开补丁与论文抽象的差异

固定提交的 r52p0_dmguard.patch 中，dev_page_table_check_set 和 CPU set 路径是 atomic_inc_return 后 smp_wmb 再读 tag；device free 使用 atomic_xchg 后 smp_wmb；CPU free 则调用使用 atomic_set / get_page_random_tag 的 helper，再 smp_wmb 检查计数。该 helper 没有显式排除上一 tag，不能把论文 RandomExclude / atomic_xchg 的全部性质直接赋给 CPU 路径。

smp_wmb 本身不是论文写出的 full_memory_barrier，但 atomic_inc_return / atomic_xchg 的内存顺序也必须计入分析；不能仅因宏名不同就断言存在竞态。下一步需要在确切内核配置、实际展开代码和完整调用链上验证，特别是 CPU free 的普通随机重置及 Map/Free 并发。本轮只记录静态差异，未构造或执行攻击。

Mali entries_invalidate 的所选代码先 dev_page_table_check_clear，再 page_table_entry_set(INVAL)，顺序与图 8 的 Unmap 后递减不同；dev clear 也未见图示的显式负计数 BUG。外围锁、调用者、页表可达性和 GPU flush 可能影响是否形成实际危险，不能凭片段宣称已证实漏洞；对本项目则应明确要求“可访问性确实撤销后才允许释放计数”。

部分 PMD/PUD 与 page-table entry 路径使用 0xFF 默认标签跳过比较；CPU anon 双 writable mapping 的原 ptcheck 限制在所选补丁被注释以支持别名。这些是兼容/语义选择，需要单独验证覆盖，不能据此声称所有引用都完成了 generation 授权。

## 9. 评估规模：24、15、10不能混用

| 层级 | 样本 | 作者报告 | 能支持的结论 |
| --- | --- | --- | --- |
| 全文合计 | 19 真实漏洞 + 5 synthetic = 24 | 覆盖两类生命周期错误 | 包含理论分析，不是 24 次实机验证 |
| Table 2 实证 | 10 真实 + 5 synthetic = 15 | DMGuard 15/15，ptcheck 5/15 | 给定配置下作者检测结果 |
| Table 3 理论 | 9 真实漏洞 | DMGuard 9/9，ptcheck 0 | 作者机制分析，非成功复现 |
| 公开安全 runner | 5 真实 + 5 synthetic = 10 | README 为 DMGuard 10、ptcheck 2 | 公开可运行子集，不等于完整 Table 2 |

作者实证中 Pixel 8 覆盖 CVE-2025-0072 / CVE-2023-6241，Pixel 3 XL 覆盖 CVE-2023-33107，其余 12 项在 QEMU。Adreno 33107 的驱动为便于触发做修改，保持语义是作者说明，不能称未经改动产品的同等复现。

公开 QEMU 使用 MALI_NO_MALI dummy GPU。模拟是合理研究载体，可检验插桩、状态变化及错误路径；这些结果不自动证明真实 GPU DMA 停止、硬件 TLB 清空或恶意 Host 下的 CCA 归属保护。本项目同样应按被验证的性质解释模拟，而非因硬件类型否定设计。

## 10. 未知问题、模糊测试与可用性

作者发现驱动退出时遗留 GPU PTE，ARM 确认问题但认为不可利用，因为使用该页表的 GPU 任务已经全部结束。不能把它写成已证实的新可利用 CVE；它反而说明 dangling PTE、页表仍可达、任务仍运行三个条件不能混为一谈。

syzkaller 覆盖增量约 15%、VTS 十轮无失败，是有界测试证据，不是全部生命周期安全证明。防护以 BUG fail-stop 阻断危险操作，能防继续利用，但不提供每 Client 故障隔离或多租户可用性保证。项目应优先隔离涉事队列/Client，只有不能证明 DMA 静默时才扩大 reset 范围并禁止回收。

## 11. 安全 runner 的结果语义

完整静态阅读 `ae/scripts/run-security-eval.sh`：返回码 3 且检测到 page_table_check 字样才映射为 Detected；普通 panic 的 0 与无 crash 的 2 都映射为 Vulnerable，1 为 Error。因此并没有简单把任意 crash 记作防护成功。

但 prompt 返回、超时或无 panic 直接标 Vulnerable，也不独立证明 exploit 获得越权访问；页面错误字符串匹配不足以证明正确拒绝且受害者保持健康。脚本主流程生成汇总后正常结束，没有逐项不通过就整体非零的断言，故 runner rc0 不是所有案例安全 PASS。项目应保留 SETUP_FAIL、未触发、明确拦截、越权哨兵和受害者恢复等独立判据。

构建脚本区分 Linux 6.6 / Mali r38p0、r47p0、r52p0、synthetic / baseline / ptcheck / DMGuard；patch 失败与已应用被合并输出 skip，说明复现必须另核实际源码与配置。synthetic 补丁主动增加危险测试 ioctl，并对 SLOWME 注入延迟，属于夹具，不能部署为生产安全路径。脚本含广泛 pkill 清理，本轮未运行，项目仍遵循独占锁与精确资源归属。

## 12. 性能与内存算术复核

| 作者论文数据，Pixel 8、11 次平均 | DMGuard 结果 | 本轮复核 |
| --- | --- | --- |
| LMBench 12 项 | 几何平均 +2.96% | 按表内百分比复算 +2.9590%，ptcheck +1.9869% |
| Geekbench single / multi / OpenCL | 1622.27 / 4545.73 / 7674.18 | 对基线分数降低约 0.4406% / 1.2890% / 0.2234%，不是耗时增长 |
| Phoronix 8 行 | 几何平均 +1.26% | 复算 +1.2629%，ptcheck +0.6591% |
| boot | 0.510 → 0.528 秒 | +3.5294%；ptcheck 为 +1.1765% |
| 十个 app cold launch | 几何平均 +3.10% | 复算 +3.1029%，最大绝对增量 12.55ms |

Table 9 的 MemTotal 为 7,739,468 KiB，baseline / ptcheck / DMGuard 的 MemFree 为 4,841,540 / 4,801,772 / 4,791,660 KiB；额外占用 39,768 / 49,880 KiB。相对 MemTotal 是 0.5138% / 0.6445%，相对 baseline MemFree 是 0.8214% / 1.0303%，均不精确匹配论文印出的 0.84% / 1.05%，分母或原始统计未取得。

论文称额外 8B × 1,934,867 页约 15,478KB；精确为 15,478,936B = 15,116.1484KiB = 15,478.936 十进制KB。DMGuard 与 ptcheck 实测差为 10,112KiB，并不等于此元数据计算。每 4KiB 页额外 8B 为 0.1953125%，完整 16B 为 0.390625%；启动后 MemFree 差还含其他分配，不能只归因 PageMD。

artifact 使用 QEMU、11 次中位数：README boot 0.699 / 0.716 / 0.744 秒，LMBench 3.14% / 7.60%，内存 0.21% / 0.41%。已读分析脚本以 MemTotal 为内存开销分母。它们与论文 Pixel 8 平均数不是同一实验，不能互相代替。未取得论文全体原始 11 轮记录，不推导置信区间或本项目性能。

## 13. 对项目内存隔离设计的具体补充

建议可信 ProxyRealm 为每个实际 HPA 保存 owner Client、allocation generation、允许权限、CPU/GPU/IOMMU 别名数、in-flight job 引用、撤销状态和清理状态；RMM 认证原始 Client 后才允许生成或使用映射引用。以上是设计建议，不声称当前所有字段已经实现。

GPU 软件 IPA→HPA 翻译及直接 HPA Stage-1 合成必须持有稳定的页授权和 generation，在校验到安装之间阻止释放/改归属。事务失败须回滚计数与引用；重复 unmap、部分建图、错误 fence、Client 退出和 reset 均走可核查状态转换。其他设备硬件 Stage-2 同样不能绕开实际页生命周期。

页池只是一种 allocator，不是安全边界：BO 销毁、pool return、pool shrink、buddy free、跨 Client 转交分别审查。允许显式共享时，owner / share grant / rights 要独立表达，计数大于零不能被解释为任意 Client 都有权限。

## 14. 对中断通信与安全回收的具体补充

保留可信物理 IRQ → Proxy 原生任务 / fence → Client cookie / epoch 的验证链；中断只驱动重新观察真实状态。伪造、重复、合并、延迟或旧 epoch 通知不得改变物理页 owner，不得直接把 in-flight 归零，也不得直接释放 BO。合法旧 IRQ 也可能已经与当前复用 slot 无关。

推荐撤销协议为：禁止新提交与新建图 → 固定撤销 generation → 终止或排空真实任务 → 撤销全部可达映射 → 等待 GPU MMU / SMMU / CPU 必要失效完成 → 确认设备不再持有旧访问 → 必要缓存同步/清理 → 更新归属并允许复用。具体 flush 与 drain 次序须按平台协议确定，不把该列表当任意设备可直接照抄的硬件序列。

MapCount=0、fence 已 signal、IRQ 已 ACK 各自都不是完整静默证明。错误/取消/reset 后若仍无法证明旧事务不会访问，应隔离页面继续 quarantine，而非为了内存恢复立即分配给另一个 Client。这是本项目可独立展开的“任务完成与物理页撤销一致性”研究点。

## 15. 与已有论文的关系及验证计划

PORTAL 提供可信服务/Realm 设备管理启发，CAGE / ACAI 约束 GPU 访问及身份与映射归属，PhantomMap 强调实际页与映射检查，DMGuard 进一步提供 CPU/GPU/IOMMU 共同生命周期与旧引用拒绝的机制材料。它们可以组合，但不能把彼此未证明的 TLB、固件内部访问、IRQ 身份或 DMA 静默默认为已覆盖。

建议后续验证：同 HPA 多别名后 free；pool 内重复分配；CPU/GPU/IOMMU 交叉；stale PFN 在新 generation 建图；map/free/unmap 并发；大页/部分失败回滚；reset 时旧 IRQ 与旧 fence；PTE 已删但 TLB 未完成；DMA drain 未确认时回收。每项检查攻击者实际访问与受害者哨兵，区分测试夹具失败、机制拒绝、任务错误及恢复成功。本轮仅提出计划，未执行。

## 16. 证据与统一记录

证据目录 `build/cca-gpu-followup-20261027/`：`acquisition127*.json` 保留成功/失败，`dmguard127-full.txt` 全文，`dmguard-render127.json` 图像哈希，`dmguard127-selected-blobs.json` 固定代码来源与哈希，`dmguard-arithmetic127.json` 为本轮自写标准库算术结果；算术不是作者程序或硬件复现。

统一记录：19 页全文 / 全图表 / 12 页视觉核对 / 固定 artifact 有限静态阅读 / 算术 / Notion 全文回读｜glmark 未测 → 未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码、攻击、模拟、构建、硬件 run-id 或运行 PASS｜保留研究，项目实现与并发/撤销性质待验证。
