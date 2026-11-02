# GPU Workgroup Progress：形式化进展模型、Mali 反例与完成通知的边界

研读日期：2026-10-27。完整研读 30 页作者稿和参考文献，核对正式 DOI；静态检查固定 artifact 的说明、Alloy、LNT/MCL、Vulkan 生成与运行器，并离线重新统计已公开 CSV。未执行 GPU、CADP、Alloy、SwiftShader 或攻击。未改运行代码，无新增性能测量。

## 1. 书目与范围

| 项目 | 核验信息 |
| --- | --- |
| 标题 | Specifying and Testing GPU Workgroup Progress Models |
| 作者 | Tyler Sorensen、Lucas F. Salvador、Harmit Raval、Hugues Evrard、John Wickerson、Margaret Martonosi、Alastair F. Donaldson |
| 发表 | Proceedings of the ACM on Programming Languages，5，OOPSLA，Article 131，2021，30 页 |
| DOI | [10.1145/3485508](https://doi.org/10.1145/3485508) |
| 作者全文 | [作者 PDF](https://johnwickerson.github.io/papers/gpu_progress_OOPSLA21.pdf)，本地 `gpu-progress-author.pdf`，30 页；同题 arXiv 入口 [2109.06132](https://arxiv.org/abs/2109.06132) |
| 实际阅读 PDF SHA256 | `a5dff85acf02ae376335c1bcca7040bde662e6dba7787dc953fb7c6c2af93211` |
| 正式 artifact | [Zenodo 10.5281/zenodo.5501522](https://doi.org/10.5281/zenodo.5501522) |
| 作者代码 | [tyler-utah/AlloyForwardProgress](https://github.com/tyler-utah/AlloyForwardProgress)，固定提交 `d9c779129f5ff9f678b31d9b7ccb29c184ddb097` |

已从 `batch14-fulltexts.json` 恢复作者稿最初下载 URL，HTTP 200、PDF magic 与上述 SHA256 均有记录；不声称它与 arXiv 扩展版本逐字一致。Zenodo API 本次连接受阻，实际源码核验依据作者 GitHub 固定提交。

这是 GPU 调度语义与测试方法论文，既不是 TEE 架构，也不是 Arm CCA 保护实现。它与已经独立研读的 CONCUR 2018《GPU Schedulers: How Fair Is Fair Enough?》不同，不能合并标题、数据或重复计入原库条目。

## 2. 问题：访问合法不意味着任务能够结束

跨 workgroup 自旋锁、生产消费和全局 barrier 依赖其他组最终运行。如果 GPU 只让占用资源的等待者执行，而生产者一直得不到调度，即使所有内存访问合法且原子操作正确，程序仍可能永不结束。

论文将这种进展假设写成形式模型，再自动生成可区分模型的小程序，并在多厂商 GPU 上运行。它要回答哪些调度承诺足以让程序终止、硬件观察是否违反某个模型，而非证明任务数据的机密性或完成消息的真实性。

对项目，GPUVM 和映射授权解决访问边界，native fence/cookie 解决完成归属，但不能仅靠“允许提交”保证恶意或错误 kernel 的进展。可信中断可传递真实状态，却不能让没有完成的任务变为成功。

## 3. 抽象语言 AXB 与状态空间

AXB 将原子读、可选交换和条件分支组合为一条指令。线程只有 PC 形式的本地状态，共享位置取有限值；模型采用原子状态转换，避免先陷入真实 ISA 和完整 GPU 内存模型的复杂性。

Alloy 合成有界程序和状态图，再转换成 LNT/CADP 模型，使用 MCL 检查终止性质和模型间差异。公开模型限定共享值 ZERO/ONE，并通过 `minimal_states`、读写关联、分支可达等谓词削减冗余候选。

这种最小化是有界合成中的约束，不是所有 GPU 程序语义等价或全局最小性的证明。程序范围、状态/动作上限、时间限制和搜索约束共同决定可发现的反例。

尤其作者发现：一个只有两线程、每线程四条指令的常见 mutex 例子，仍需有针对性的约束才能合成出来。不能因为已搜到大量小程序，就把某一类未出现的死锁当作不存在。

## 4. 进展模型与公平性

解释器维护获得进展保证的线程集合 F，调度 Step 根据具体模型更新 F，Terminate 删除已结束线程。OBE 根据已经开始执行的线程建立承诺；LOBE 加入 ID 顺序相关限制；HSA 采用另一套 ID 及执行进展约束。它们不能仅凭名称被等同为普通轮转调度。

论文讨论 unfair、fair、HSA、OBE、LOBE、HSA+OBE 等家族及强弱形式，共称 11 个模型；HSA+OBE 没有进入后续详细实验分析，strong OBE 没有得到可区分测试。因此不能把“11 个模型”写成“11 套均被完整实测并识别的调度器”。

弱/强的区别不只是每个线程是否得到时间片，还涉及循环中退出转换能否最终发生。MCL 检查根据模型判断是否存在无限非终止执行；强公平性不能仅靠一次轮转或有限次数让步推导。

公开弱公平公式利用 F 在成员终止之前只增不减的结构，使循环内保证集合稳定。项目若加入取消、撤销、暂停或关闭会话，使活线程从保证集合移除，必须重新论证公式适用性，不能原样套用为 reset/撤销协议的证明。

## 5. 合成规模和正式检查结果

作者使用 20 核 Xeon Gold 6230、1 TB RAM，对五种配置分别运行七天，总计超过一个月。仅最小配置完成搜索，其他受时间限制；没有完整性保证。

| 配置 | 合成测试数 | weak LOBE conformance 测试数 |
| --- | --- | --- |
| 2 线程 × 2 指令 | 8 | 3 |
| 2 线程 × 3 指令 | 176 | 50 |
| 2 线程 × 4 指令 | 173 | 32 |
| 3 线程 × 3 指令 | 21 | 7 |
| 3 线程 × 4 指令 | 105 | 30 |
| 合计 | 483 | 122 |

后列来自本轮对作者正式 CSV 的离线重新统计，与全文的 122 一致。没有重新执行合成或模型检查。

正文 Table 4 区分 distinguishing/conformance：weak HSA 为 90/90，strong HSA 94/94，weak OBE 12/12，strong OBE 0/0，weak LOBE 20/122，strong LOBE 16/110，weak full 201/323，strong full 50/160。不同模型集合有交叠，不能相加视作独立测试总数。

Formal PASS 表示该有限测试在指定模型及解释语义下被保证终止；empirical PASS 表示运行器在其观察窗口内记录通过。这是两个不同的判断，不应互换。

## 6. 真实 GPU 测试设置

系统性实验覆盖 8 款 GPU、5 家厂商，包括 NVIDIA 940M/Quadro RTX4000/Tegra X1、Apple A12/A14、Intel HD620、Adreno620、Mali-G77 MP11。后者来自 Exynos Galaxy S20、Vulkan 1.1、Android 11；论文说明由于实验记录失误没有 Mali 驱动版本。

NVIDIA CUDA 配置分别含 CUDA9.1/11.2；Vulkan/Metal 设备软件栈和平台不同，不能当作同一编译器和驱动的受控对比。Intel 平台表格和正文存在发行版描述差异，不能据此补全不存在的精确环境。AMD 路径因不可恢复失败/硬重启未进入最终矩阵，不是验证通过的平台。

每个测试映射成 plain、round-robin saturation 和 chunked saturation 三种变体，最多 65532 workgroups、每组一个 invocation，复制实例使用不相交内存。round-robin 指复制程序与 workgroup ID 的排列，不是本项目 Client 调度的 round-robin 策略。

正文常规设置称每项 20 次；CUDA 超时约 20 秒、Vulkan 外层约 5 秒，Metal 依赖约 1–2 秒系统 watchdog/观察。不同 timeout 的失败不能直接量化为硬件公平程度差异，timeout 也不是观察到数学意义的无限执行。

后端采用 `atomicAdd(...,0)` 和 `atomicExchange` 等实现读写，多数测试为单位置；为可移植性没有启用完整 Vulkan memory-scope 扩展。作者对意外结果进行人工检查，但这不构成所有编译器 lowering、原子语义和抽象模型的一致性证明。

## 7. 核心结果与不能外推的范围

122 个 weak LOBE conformance 测试中，A12 和 Mali-G77 各出现 11 个违反观察，均在 round-robin saturation 变体。Mali 的这些失败具有概率性，A12 大多稳定复现。

正文同时提及 A14 的额外非系统性观测：少量重跑出现罕见 LOBE 违反，另有 CAS mutex 例子提示 Apple 平台 OBE 问题。这些不属于同一份全套自动合成矩阵。不能把它们写成 A14 在该公开矩阵也有 11 个失败。

在合成套件上未观察到 weak HSA/OBE 违反，不代表实现普遍满足这两种模型；有界集合、运行次数及 runner 都限制证据强度。CUDA cooperative launch 和 independent thread scheduling 的结果也仅适用于受测配置，不能推广成恶意多租户下的可用性或隔离保证。

chunked 对 full 与 LOBE 区分测试中的 251 个检测出 246 个失败，其余 5 个与排列有关；作者提出 hybrid mapping 等后续方向。这再次表明具体测试变体影响可观察性。

文中图应用 306 个配置、57% 有显著改进、20% 超过两倍等是对先前 2019 年应用研究的引用，不是本篇新增应用性能测量。论文价值主要是语义规范、测试合成与反例，而非新的通用应用提速。

## 8. 本轮独立离线核对：公开数据与正文的细节差异

固定仓库递归树有 16659 项且未截断；本轮下载并核验选定模型、运行器、全部五配置正式 LOBE 表及 A12/A14/Mali 三设备对应表。离线脚本按显式 test ID 合并，选择正式结果中至少一个变体保证通过的测试，仅比较前三个 workgroup 变体，避免把 Mali 表中的其他 subgroup 列混入。

| 对象 | 本轮从作者 CSV 重算 | 与原文的关系 |
| --- | --- | --- |
| 全套/选定测试 | 483 / 122 | 一致 |
| A12 | 11 个；全部 RR，10 个为 21/21、另一个 19/21 | 测试身份与大多数稳定失败一致，但 CSV 分母是 21，不能改写成公开数据为 20 |
| Mali-G77 | 11 个；全部 RR，失败次数依次 19、16、17、16、18、13、17、18、16、16、17，分母均 20 | 全部超过半数且没有全部 20 次失败，与正文定性吻合 |
| A14 | 0 个 | 该公开矩阵没有系统性失败，不否定正文另外的非系统性复跑观察 |

A12 与 Mali 的 11 个测试 ID 相同：3×3 配置的 7/16，以及 3×4 配置的 34/46/48/52/55/56/61/64/66。两设备均只有 RR 列标 F，plain/chunked 为 P。

这是对既有数据标签的复算，不能绕过原始运行记录缺失去重新证明每一次成功或失败。尤其公开 CSV 未提供足以区分所有 timeout、driver error、设备丢失和真实不进展的逐次证据。

离线脚本 `build/cca-gpu-followup-20261027/reanalyze_gpu_progress.py` 和结果 `gpu-progress-offline-reanalysis.json` 保存了每项结果和输入 SHA256，没有启动任何 GPU 或形式工具。

## 9. 固定代码中的实际测量分类限制

`artifact/.../empirical_testing/test_amber/amber_test_driver.py` 调用外部 `timeout -k 1 5`，但没有使用 `os.system` 返回状态；统计 stdout 中的 `1 fail` / `1 pass`，当 failure_count 为零就记 P。虽然计算 pass_count，却没有强制它等于请求迭代数。

因此该版本运行器在空输出、工具错误或部分外层 timeout 等情况下存在将缺少失败文本记为 P 的可能性。这是静态可见的分类条件，未运行触发，也不能据此断言已发布的某个具体 P 一定错误。它会降低对“全部通过”作为普遍保证的信心，不能据此抹去已记录的 F 反例。

后端 shader 的有限循环/timeout、Amber 层检查和外层进程 timeout 是不同层次；项目后续验证应分别记录提交成功、编译/加载错误、工具退出码、GPU 超时/reset、输出检查结果和完整迭代数，禁止把没有报错文本当作任务成功。

作者 conformance 汇总脚本按行号索引 test ID，并依赖特定 header/footer 格式。本轮离线复算改用显式 ID 对齐并检查键集合；这只是整理公开数据，不改变作者结果，也没有写入运行代码。

## 10. artifact 可复现性

artifact 提供 Ubuntu18.04 Docker 流程，CADP2020-l 需要个人许可证且未包含。完整合成耗时很长，作者建议先运行最小 8 个测试；SwiftShader 的一次示范只验证流程，不能验证某家真实 GPU 的调度语义。

CUDA 容器路径有未测试说明，Metal 需要 Apple 设备和工具链。即使成功启动 Docker，也不能声称复制了 8 设备/5 厂商矩阵。本轮仅静态研读和离线数据解析，不报告 artifact execution PASS。

## 11. 与 GPU TEE、CCA 和中断安全的关系

PORTAL/CAGE/ACAI 等为设备执行建立可信边界；本篇补充进展属性。可访问性、数据顺序、最终调度、完成归属和可信唤醒各有独立义务：合法映射并不保证进展，进展也不证明完成属于当前请求，收到中断更不证明结果成功且可见。

现有 RMM 认证队列、私有快照、GPUVM、native fence、cookie/epoch 和 persistent IRQ127 均继续使用。研究重点应是把这些已有机制连接成可检查的条件链：真实 job 终态 → 数据满足可见条件 → 可信完成记录发布 → 正确目标唤醒 → Client 在当前代次验证。

恶意 GPU kernel 不终止属于 availability/fault containment 问题；若论文威胁模型排除 DoS，就不能借本篇悄悄扩大为保证所有任务最终完成。可以研究可控故障传播、有限恢复及错误完成真实性，但需明确哪些进展由可信调度器/固件提供，哪些只是假设。

本项目可信 ProxyRealm 控制 SMMU、软件授权 IPA→HPA 并合成受保护 Stage-1 的既定假设保持成立。本篇没有证明该内存设计不足，也不要求因当前实验硬件能力更换架构；它说明不同安全属性需要不同证据。

## 12. 对项目建议：将进展和完成状态纳入契约

第一，明确 admission、submitted、running、success、error、canceled、reset 等状态，以及每种状态能否发布完成记录和释放引用。Client 超时只能触发查询/取消/恢复流程，不能伪造 GPU 成功或提前回收仍被 DMA 使用的对象。

第二，区分 host/Proxy 的公平服务与 GPU 内部 workgroup 的进展。给 Client 轮转提交并不能消除单个 kernel 内部的占用死锁，也不等于硬件实现 LOBE；跨组同步若被允许，需要明确可依赖的设备进展模型。

第三，复用 cookie/epoch 检验 reset 后完成隔离：旧 job 的迟到 IRQ、旧 fence 观察或旧队列记录不能唤醒为新 job 成功。错误终态也需要绑定同一任务和实例，避免将“必须有响应”实现为无条件成功。

第四，后续测试应分层记录有限时间内的活性观测和安全结果：无错误成功、无提前释放、故障隔离/恢复、进展假设下最终响应。模型的 fairness 假设、撤销动作和硬件证据分别列明；不能以有限次数无超时宣称所有交错均有界完成。

本轮没有新增这些硬件回归。论文是共享 GPU 的语义支撑，仍应以直接 GPU TEE、CCA 可信设备管理和中断注入安全论文为研究主干。

## 13. 证据与统一记录

材料位于 `build/cca-gpu-followup-20261027/`：`gpu-progress-author.pdf/.txt`、`gpu-progress-crossref.json`、`gpu-progress-fixed-tree.json`、两份 code acquisition 清单、`gpu-progress-fixed/`、离线脚本及结果 JSON。下载范围不等于完整审计 16659 项文件。

统一记录：GPU 进展语义、模型、固定 artifact 与公开数据复算｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜离线 CSV 解析退出码 0，非 GPU 实验；无硬件 run-id、无新增硬件 PASS｜保留为隔离/完成协议的语义支撑，不作为新增 TEE 架构或实测安全保证。
