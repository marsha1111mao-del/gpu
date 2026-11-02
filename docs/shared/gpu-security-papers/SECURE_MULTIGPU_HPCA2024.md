# HPCA 2024｜安全多 GPU 通信：动态 OTP、批量认证与结果提交边界

研读日期：<date start="2026-10-27" />。状态：14 页作者公开全文、正式元数据和有界公开实现检索已核对；未取得确认匹配的论文实现，未运行模拟器。未改运行代码，无新增性能测量。

## 1. 文献与版本

**Supporting Secure Multi-GPU Computing with Dynamic and Batched Metadata Management**，Seonjin Na、Jungwoo Kim、Sunho Lee、Jaehyuk Huh，HPCA 2024，204–217。DOI：[10.1109/HPCA57654.2024.00025](https://doi.org/10.1109/HPCA57654.2024.00025)。[作者 PDF](https://jaehyuk-huh.github.io/papers/Na_hpca2024.pdf)由[共同作者出版列表](https://jaehyuk-huh.github.io/publications.html)明确链接。

本地全文：`build/cca-gpu-followup-20261027/secure-multigpu-hpca2024.pdf`；SHA256：`15215d6bc078c7ef2382266837fab0868837a2037eba5948337ef0c3de7e9153`。这是原 63 条清单之外的新增论文；不是 HIX 或 Common Counters 的另一版本。

## 2. 问题：可信端点之间仍有不可信链路

单 GPU TEE 保护计算 context，并不自动保护多 GPU 间的通信。本文考虑统一地址空间：CPU 与 GPU 之间、GPU 与 GPU 之间既能迁移整页，也能按 cacheline 直接访问远端内存。通信发生在 kernel 执行期间，不能只在 kernel 启动和结束时加密一次。

问题有两个成本来源：认证加密需要生成一次性 pad；MsgCTR、MsgMAC、发送者 ID 和 ACK 占用额外带宽。GPU 通信突发性强，固定平均分配 pad 经常浪费空间，却仍在热点方向缺 pad。本文贡献是动态分配 OTP 缓冲与合并认证元数据，基础 TEE 和页表授权是前提。

## 3. 威胁模型、可信基与排除项

攻击者控制 OS/hypervisor，并可物理观察或篡改 CPU 外部 DRAM、PCIe 和 GPU 互连。可信基包括 CPU/GPU 芯片、TEE 内 GPU 软件和管理页表等资源的 secure monitor。

**GPU HBM 被论文假定处于可信物理边界内。** 这是一项模型假设，不能推广为所有 HBM 天然不可物理攻击。CPU 外部内存则需另外的内存保护机制；通信加密不替代主存保护。

侧信道、瞬态执行、GPU 可用性和 DoS 不在覆盖范围。论文未研究跨 Realm 中断认证、恶意 Client GPU kernel 的完整并发隔离，或多租户任务调度证明。

## 4. 地址翻译与授权是已有可信基础

CPU-side secure monitor 检查 GPU context 相关 MMU/IOMMU 页表，GPU trusted command processor 负责 context 内存隔离；远程证明检查 CPU/GPU TEE 及应用二进制。图 17 的逆向页映射和访问控制属于所依赖的基础。

本文假设 GPU 获得正确的 IOMMU 翻译，而非提出一套替代 ACAI 的页归属协议。统一地址空间表示参与同一程序的可信端点可共享数据，不表示不同租户可以互读全部 GPU 内存。

与本项目的关系是：接受可信 ProxyRealm 完成身份、实际 HPA、权限和生命周期授权的假设后，仍可独立研究通信元数据、完成状态和提交时机；无需以实验硬件能力否定该前提。

## 5. 基础通信流程

系统启动时 CPU 与 GPU 交换通信密钥。每条消息用 MsgCTR 和端点 ID 构造 seed，生成加解密与认证所需的不同 pad。接收端验证完整性，返回包含 MsgCTR 或 MsgMAC 的 ACK；发送端保留对应值直到 ACK，用于检查新鲜性。

图 4 同时画出地址、发送/接收 ID、EIV/AIV 和 GHASH；正文对不同 Private/Shared 策略的 seed 组成分别描述。Shared 使用共同发送计数器，不需要接收者 ID 来生成 seed。不能把某一策略的字段组合当成所有模式均相同的完整线上协议。

论文没有完整列出密钥认证建立、receiver replay window、ACK 认证、计数器溢出、重启后的密钥/计数器更新及租户会话切换规则。这里保留规格边界，不据此声称已构造成功的重放攻击。端点 ID 也不能直接当作 Client、job 或对象 generation。

## 6. Private、Shared 和 Cached 的取舍

| 机制 | 缓冲组织 | 关键代价 |
| --- | --- | --- |
| Private | 每个发送/接收端点对单独维护计数器和预生成 pad | 容量随端点对数增长；突发热点容易耗尽固定份额 |
| Shared | 发送端共享 MsgCTR/缓冲 | 小容量，但接收端难准确预生成下一条消息的 pad |
| Cached | 缓存部分端点对的状态，LRU 淘汰；miss 用 Shared 方式 | 命中和容量之间折中 |

在相同 pad 总容量的 4-GPU OTP 4× 配置中，Private、Shared、Cached 的平均执行时间开销分别为 19.5%、166.3%、16.3%。这些是模拟基线，不能称为实际 GPU 固有的加密开销。

## 7. 动态 OTP 分配算法

每隔 T 统计发送/接收请求数，先按 EWMA 调整发送与接收方向的份额，再按各远端 CPU/GPU 的流量分配对应份额。初始按 Private 平均分配；参数为 α=0.9、β=0.5、T=1000，表 III 的系统时间以周期建模。

它动态移动的是**预生成 pad 的容量预算**，不是为了性能改变访问授权。未命中应回到正常生成认证材料的路径，而不能跳过认证。论文未详细展开零流量区间的除零处理、整数取整、最小份额、重分配时旧 pad 与 in-flight 消息的状态转换；实现复现时需要这些规则。

这对 ProxyRealm 的启发是把缓存和批处理预算做成可调的性能状态，把 Client 身份、对象权限、epoch 与完成判定保留为独立安全状态。预算被恶意流量扰动，最多应影响性能，不应改变授权含义。

## 8. 元数据批处理保留了什么

普通模式每个 64B 数据块携带 8B MsgCTR、8B MsgMAC、4B sender ID，并获得 8B ACK。批处理只合并 MsgMAC 和 ACK；**每块数据仍传递计数器和 sender ID**，首块另带 1B 批长度。直接访问通常 16 块一批，整页迁移对应 64 块。

论文图 19 及正文把 4KB/64B 情形写成 512 次普通传输；按其给出的单位应是 64 次，存在明确的算术/标注不一致。这里不复述 512 作为正确计算，也不据此重算全部模拟数据。

公式 (5) 用 Concat 描述各块 MAC 构造 Batched MsgMAC，正文/图又把最终 MsgMAC 标为 8B。全文未完整展开如何由拼接输入生成该固定宽度认证标签；不能把它解释为任意简单拼接或 XOR 都安全，也不据此宣称其密码构造已被攻破。

## 9. 乱序、验证延迟和最重要的安全边界

接收端为各块 MAC 保存位置；收到整批后按正确顺序生成并核验 Batched MsgMAC，再返回 ACK。4-GPU 模型中每 GPU 为各对端保存最多 64 个 8B MAC，合计约 2KB。

**论文明确允许解密后继续执行，延迟 MAC 验证。** 作者引用 lazy integrity verification 并主张保持原安全保证，但本文没有完整展开通用 GPU 的 poison 传播、可信外部输出屏障、错误依赖回滚和验证失败后状态销毁协议。应区分作者的安全主张与本文实际提供的细节。

与 TensorTEE 一样，关键问题不是“能否晚检查”，而是“验证前的依赖能否产生不可撤销的外部影响”。对 ProxyRealm，真实 GPU fence、结果可读、SUCCESS 发布和内存可回收不是同一事实。若未来引入推测执行或延迟验证，应另设提交条件，不能把当前已有的真实 fence 自动解释成数据认证成功。

## 10. 硬件与模拟器范围

CPU/GPU 端增加 AES-GCM 引擎、动态 allocator 与 batching controller；4-GPU 配置每 GPU 有 8 个 64-bit 流量计数器，共 512bit。OTP 表项含 valid、512-bit 加密 pad、128-bit 认证 pad 和 64-bit counter。这里的 pad 是预生成密码材料，不是软件常说的“临时验证码”。

评估使用扩展 MGPUSim，GPU 模型为 AMD R9 Nano；不是现有 NVIDIA 多卡产品实装，也不是 Arm CCA 或 Mali 原型。不能把模拟验证简单否定为无效，也不能把它写成已在真实 16-GPU 集群完成部署。

## 11. 实验条件

基准 4 GPU，每 GPU 64 CU、1GHz、64 work-items/wavefront，HBM 512GB/s、共享 L2 2MB。CPU–GPU 链路 32GB/s，GPU–GPU 链路 50GB/s；AES-GCM 默认 40 cycles，并做 10–40 cycles 敏感性分析。页迁移基于访问计数策略。

17 项 workload 来自 Polybench、AMD APP SDK、Hetero-Mark、SHOC 和 DNNMark，按远程访问请求/千指令分类。8/16-GPU 扩展使用与 4 GPU 相同输入规模；每 GPU pad 数分别为 64/128，对比 4 GPU 的 32。扩展结果不是固定每 GPU 工作量、固定总 pad 容量或真实故障注入实验。

## 12. 数字及百分比口径

| 配置 | Private 执行时间开销 | Cached 开销 | 本文组合开销 |
| --- | --- | --- | --- |
| 4 GPU | 19.5% | 16.3% | 7.9% |
| 8 GPU | 29.3% | 21.4% | 12.2% |
| 16 GPU | 32.1% | 27.8% | 14.6% |

各行都相对同 GPU 数的无通信保护系统。4 GPU 只加 Dynamic 为 14.7%；把 Private 容量增至 OTP 16× 为 14.0%，仍高于组合的 7.9%，原因是加 pad 不能消除元数据带宽。

论文称相比 Private 改善 11.6%/17.1%/17.5%，对应上表归一化执行时间开销之差，宜表述为 **11.6/17.1/17.5 个百分点**；不能直接当作相对 Private 的 speedup。以已报告的均值归一化时间作算术换算，4 GPU 的 1.195→1.079 约为时间缩短 9.71%，该换算也不等于逐 workload speedup 的算术平均。

4 GPU 通信流量相比 Private/Cached 分别减少约 20.2%/20.0%；把 AES 延迟从 40 降至 10 cycles，组合开销从 7.9% 降为 5.6%。这些共同说明带宽和元数据访问同样重要，不能只比较密码引擎延迟。

## 13. 证据强度与复现边界

全文对控制算法、性能模型、负载和敏感性分析提供了明确证据；没有给出跨 Client 任务状态机、中断真实性证明或完整密码协议形式化验证。有界检索检查作者出版条目与准确标题的 GitHub 仓库搜索，未取得确认匹配的公开实现；不宣称作者从未发布代码。

原始 MGPUSim 是基础模拟器，不能冒充本文 Dynamic/Batching 实现。本轮未执行模拟器、没有重现论文数字，也没有把全文阅读当成公开源码审计。

## 14. 与 CCA / GPU TEE 主干的关系

| 工作 | 本文依赖或比较的关系 | 对项目的用途 |
| --- | --- | --- |
| HIX、Graviton | 提供 GPU TEE、可信控制和 context 隔离的参照 | 明确本研究在可信 GPU 端点成立后优化链路 |
| Common Counters、PSSM、SHM | GPU 安全内存元数据优化的相邻工作 | 机制服务的保护层不同，不能都等同映射隔离 |
| PORTAL、ACAI、PhantomMap | 本文没有提供其 Realm/实际页授权协议 | 本项目继续保留可信身份、真实 HPA 与生命周期授权 |
| TensorTEE | 都涉及粗粒度/延迟验证，但设备和提交条件不同 | 审查验证前可见性，不能不加论证照搬 |
| Devlore、TEEtime | 本文没有覆盖物理中断保护 | 通信加密或 ACK 不能替代受信 IRQ 路由及任务归属 |

以上是机制比较，不声称论文之间存在未经证实的直接继承关系。

## 15. 对本项目可以增加的具体研究

本项目已有独立 GPUVM、RMM 认证队列和持久 IRQ127、私有请求快照、原生 fence 以及 cookie/epoch。可继续研究的是这些机制在批量化、取消和 reset 并发下如何保持同一套授权含义，不是重新提出“给消息加一个 ID”。

建议把批次键约束为可信端确定的 Client/session/epoch 与许可的作业集合；跨 Client 即便共用底层队列，也分别保存授权和终态。通知可以合并，但 Client 必须从可信状态表恢复逐作业结果，不能让一条 ACK 或一次 IRQ 自动完成整批不相关任务。

若做批量完成优化，验证计划应包括：混入另一 Client 的 job、重复/缺失成员、乱序到达、批形成期间撤销、reset 后旧批完成、部分任务 ERROR，以及小流量无法凑满批次。预期是拒绝错误成员、保持剩余任务状态且不提前释放仍被 GPU 引用的页。

若没有延迟数据认证的实际需求，不必额外添加密码流水线。当前更直接的机制是保留真实完成观察，明确 `结果可发布` 与 `设备已停止旧访问、允许回收` 的不同条件；epoch 可拒绝旧消息，仍不能单独证明 DMA quiescence。

## 16. 独立评价与研究记录

这篇论文适合补充“安全 GPU 的优化对象包括安全元数据与异步验证时机”，与当前 ProxyRealm 的核心路线相邻。其最值得深究的边界是 lazy verification 下的外部可见性，而非把多 GPU 链路加密直接移植为单 GPU 跨 Realm 中断方案。

统一记录：安全多 GPU 通信论文全文与元数据静态研读｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜来源为上述 PDF、正式 DOI 和有界检索，无硬件 run-id、新增硬件 PASS 或复现日志｜保留为新增独立精读，密码协议/实现未核验项明确保留。
