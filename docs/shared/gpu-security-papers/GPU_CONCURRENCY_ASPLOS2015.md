# GPU Concurrency：弱内存行为、完成发布顺序与测试可信性

研读日期：2026-10-27。原库 TGS-052。已完整研读作者提供的 15 页主文、4 页技术附录，并核对官方 DOI 元数据、作者补充站及部分实验结果页面。本文没有执行 litmus、构建测试工具或运行 GPU。未改运行代码，无新增性能测量。

## 1. 书目信息与版本证据

| 项目 | 内容 |
| --- | --- |
| 标题 | GPU Concurrency: Weak Behaviours and Programming Assumptions |
| 作者 | Jade Alglave、Mark Batty、Alastair F. Donaldson、Ganesh Gopalakrishnan、Jeroen Ketema、Daniel Poetzl、Tyler Sorensen、John Wickerson |
| 正式发表 | ASPLOS 2015，577–591；2015-03-14 |
| DOI | [10.1145/2694344.2694391](https://doi.org/10.1145/2694344.2694391) |
| 所读主文 | [作者主页实际链接的 PDF](https://johnwickerson.github.io/papers/gpuconcurrency.pdf)，15 页 |
| 主文 SHA256 | `85d0885848f723df856cc0da5ab817e2475b565f6c786450e3444023a2dd468b` |
| 补充入口 | [Imperial GPU litmus 项目页](https://multicore.doc.ic.ac.uk/gpu-litmus/) |
| 技术附录 | [4 页 PDF](https://multicore.doc.ic.ac.uk/gpu-litmus/paper-appendix.pdf)；SHA256 `dce896b0cdc0c4b8f26b835457e84300db041dd11ec482972bb2c11cc0797d28` |

另有 SIGPLAN Notices 重刊 DOI `10.1145/2775054.2694391`，不重复计作一篇。所读作者 PDF 首页 DOI 仍为排版占位，书目信息采用正式元数据。补充站称其链接主文为 12 页 preprint，本文实际研读的是作者主页 15 页版本，不能把两个入口的页数静默混用。

## 2. 问题：同步语法看起来正确，实际读到什么

早期 GPU 编程材料常假定不会出现弱内存结果、原子操作天然提供同步，或只在解锁后放屏障即可。论文通过短并发程序揭示这些假设不成立，并构建与实测行为相容的形式化模型。

该论文不提出 TEE，也不针对恶意 Hypervisor；它研究可信并发协议依赖的基础语义。它与本项目的联系在于：身份认证和内存访问许可解决“谁能读写”，内存模型解决“观察到状态后哪些数据已经可见”。两类性质都需要，但不能互相代替。

## 3. 范围、平台与排除项

表 1 列八种芯片：NVIDIA GTX 280、GTX 540m、Tesla C2075、GTX 660、Titan、GTX 750，以及 AMD HD6570、HD7970。GTX 280 未观察到弱行为，后续主要结果表不再列它，贡献概述的七种 GPU 因而不能与表 1 八种初始候选混淆。

主测试覆盖同 CTA 不同 warp、同 grid 不同 CTA；没有测试同 warp 线程间、不同 kernel grid、不同 GPU 或 CPU–GPU 相互作用。内存涉及 global/shared，忽略只读 constant/texture。

NVIDIA 使用 PTX 经 ptxas 编译为 SASS，再检查访存没有被重排/删去；AMD 经 OpenCL 编译后人工核查 ISA。CUDA SDK 5.0/5.5/6.0、旧驱动与 Windows 7/Ubuntu 12.04 的配置是作者结果的适用条件，不直接代表现代 Arm Mali、现代 PTX 或项目代码。

## 4. 关键发现一：原子性、volatile、缓存和顺序是不同性质

coRR 测试中，一线程写 x=1，另一线程先读到 1 再读到初始 0。作者在 Fermi/Kepler 观察到该结果，GTX540m 为 11642/100000。论文把它与 RMO 的允许行为相比较，没有把所有非 SC 行为统一当作硬件漏洞。

shared memory 的 volatile message passing 也可出现“标志为新、数据为旧”。因此 volatile 的“执行访问/限制编译优化”含义不能自行扩张成 acquire/release 或完整顺序保证。

在 Tesla C2075 使用 .ca 的 L1 路径时，message passing 即使插入 membar.sys 仍出现弱结果，表 3 为 162/100000；改 .cg 配合相应 fence 才在该配置实验中消除。这是特定历史 PTX/缓存规则的结论，不应直接要求项目或现代 PTX 都强制绕过 L1。

## 5. 关键发现二：队列发布可能丢任务

论文分析 GPU work-stealing deque：生产者先写 tasks，再推进 tail；消费者先看 tail，再取 task。若同步不足，消费者可看到新 tail 和旧 task，造成漏任务/读错任务。

另一路 load-buffering 场景涉及消费者先读 task 再 CAS head，与生产者 pop/reuse 交错；弱顺序使某次 steal 看起来取得了后来才写入的任务。这里不只是读旧数据，槽位重用与状态推进一起构成错误。

作者在相关生产/消费位置增加 fence，并把不合适的普通 store 改为原子 exchange，实验不再观察到目标结果。原文以“forbids”解释模型/修复意图；独立评价仍需区分具体实验未观察到、模型中禁止与所有未来硬件均正确三种证据。

对项目，提交队列、完成队列及对象复用均应明确 payload、序号、所有权与通知之间的发布顺序。已有认证队列和私有快照是基础，不代表它们有已证实的顺序缺陷。

## 6. 关键发现三：锁的 CAS 不自动保护临界区

CUDA by Example 的自旋锁使用 atomicCAS 获取、atomicExch 释放，却缺少临界区边界同步。cas-sl 中，在成功获得锁后仍读到旧数据；作者在 GTX Titan 报告 512/100000，并在 AMD 两种平台观察到同类现象。补上进入和退出临界区的相应 fence 后不再观察到该结果。

只在 unlock 之后放 fence 不能阻止临界区访问越过释放动作。论文另给 sl-future：前一个临界区甚至可读到后一个临界区写入的值。修复还需避免普通 store 与原子 CAS 对同一锁地址混用而破坏当时 PTX 所规定的原子保证。

NVIDIA 后来为被分析教材示例公布勘误。这个外部确认支持论文发现的具体性，但不能推出所有原子 API 都没有顺序，也不能忽略现代 API 的 memory-order 参数。

## 7. Litmus 生成与压力触发方法

作者扩展 diy：用候选执行中的关系环自动生成测试，增加 scope tree、内存区域和寄存器声明。每个线程执行短序列，Host 收集最终寄存器/内存状态直方图；测试用位置与压力访问位置分开。

四类 incantation 分别是：额外线程制造内存压力、同 warp 非测试线程制造 bank conflict、随机布局测试线程、在开始前同步测试线程。它们提高特定弱结果的出现机会，但组合效果不是单调的，例如 bank conflict 会降低部分 inter-CTA 案例的触发率。

开始屏障本身还必须考虑跨 CTA 和 warp 的进度限制，避免测试 harness 死锁。作者明确说，正确性关心弱行为是否可能，不是它在通常负载下是否足够少。

## 8. 测试编译结果必须可信

-O0 仍不保证逐条保持预期机器指令，且插入的额外指令会改变触发机会；-O3 又可能重排访问。作者用 optcheck 将测试预期访存顺序编码到额外 xor 指令的常量中，再用 cuobjdump 的 SASS 反查是否一致。

测试 false dependency 时，普通 xor(x,x) 会被优化掉。论文采用对编译器未知、但在测试取值条件下恒为零的高位掩码构造地址依赖，并检查机器代码保留关系。

AMD 没有同样自动检查器，使用位标记、位掩码和运行期 zero 参数辅助人工区分访问，部分编译器自动插入 fence 还使某些测试无法忠实构造。附录完整说明这些转换；因此 AMD 的受控测试范围比 NVIDIA 更窄。

## 9. 形式模型：按 scope 构造 RMO

模型采用事件图，基本关系为 po、rf、co、fr，以及地址/数据/控制依赖和 fence。scope 关系表示同 CTA、同 grid 及 system 可通信范围。

作者先从 SPARC RMO 提取三类规则：放松 read-read 的单位置一致性、依赖与 rf 不得形成 thin-air 环，以及依赖/fence/通信的一致性。再为 CTA、GPU 和 system 三个层次分别施加约束，允许更强 fence 同时满足更小 scope 的要求。

herd 按模型枚举允许执行；10930 个自动生成测试用于比较硬件结果。作者称 experimentally sound，即已观察的硬件行为均被模型允许。它不是任意大小程序的机械证明，不证明所有模型允许行为都可在硬件出现，也不是对 RTL 的形式化验证。

## 10. 模型与实验的重要限制

形式模型仅处理论文列出的访存、算术、跳转、谓词和 fence 子集，并假定访存使用 .cg。尽管前文用 atomics 和 volatile 发现了编程问题，模型没有把它们完整纳入，不能拿这份 .cat 模型直接证明前面所有锁和队列。

模型含 system scope 定义，但实验没有涵盖 Host/DMA 设备/跨 Realm 路径，不能把定义存在当作这些通信已经测过。它描述的是特定编译配置下未经意外优化的程序行为，不是 CUDA/OpenCL 语言级完整语义。

论文还指出先前基于文档推导的 operational model 禁止了硬件实际出现的一个 lb+membar.cta 结果：Titan 586/100000、GTX660 19/100000。这支持“检查模型与实现的一致性”的方法，而不是给所有文档一概判错。

## 11. 公开材料核验与复现限制

已取得项目站、技术附录、[distilled PTX 结果](https://multicore.doc.ic.ac.uk/gpu-litmus/distilled-ptx.html) 及 [positive-results 索引](https://multicore.doc.ic.ac.uk/gpu-litmus/flat-pos.html)。网页明确：表中 dash 可能是 optcheck 失败或设备资源不足，不能解释成零次观察。

结果快照 SHA256：distilled PTX 为 `8a2a543042c4224efa2c296dfb1cf89be1fd17e55655b4072efdde5720d866c7`，positive 索引为 `5d0eee4cc114869e06b95d901114138b31aeef1529c111aac1784f4227e33c04`。已定向查看入口、表格头、测试记录和链接结构，没有下载全部逐芯片日志、重算所有直方图或执行工具。

当前索引含部分 50K/100K 不同计数口径，体积也不同于入口旧说明。不能假定所抓页面与主文每项最终实验完全同版本，再无条件复算主文 100K 结论。本文逐项数字均按主文/附录引用，网页作为公开补充证据单独保留。

本次未固定与 2015 论文匹配的 diy/herd GPU 扩展源码版本，也未审计 optcheck 实现；模型结构来自完整论文，代码核验不足不隐藏为已复现。

## 12. 与后续研究及 CCA 项目的关系

| 工作 | 本文与其关系 | 迁移边界 |
| --- | --- | --- |
| PTX formal analysis，ASPLOS 2019 | 后来对官方 PTX 6.0 与编译映射的形式化工作 | 不把旧 .cg/RMO 模型当现代 PTX 标准 |
| GPUHarbor / MC Mutants | 后续跨平台测试、压力配置及测试能力评估 | 观测数量/相关系数不等于安全证明 |
| PORTAL / CAGE / ACAI | 可信服务、设备和页归属 | 身份正确之外还需通信顺序正确 |
| Devlore / SHELTER 期刊版 | 中断来源、路由和 pending | 正确投递中断不自动建立所有数据的可见性顺序 |

本项目已有 GPUVM、RMM 认证会话、私有快照、真实 fence、cookie/epoch 和持久 IRQ127。对“真实 fence”的分析应同时保留它确实代表哪项 GPU 工作结束、其结果通过哪种同步对 CPU/Client 可见，以及发生错误时允许推进什么状态。

## 13. 对项目可验证的协议性质

建议为已有提交通知和完成通知分别写明顺序链：先准备可信快照/结果，再以合适内存域语义发布队列条目；接收者获取该发布后验证身份、seq、epoch 和任务状态，再读取数据。中断作为提醒接收者检查受保护记录的触发，不凭中断到达独立推导数据已就绪。

CPU release/acquire、CPU–GPU fence、DMA cache maintenance、MMIO doorbell 和 RMM/GIC 投递各有适用范围。应按项目实际 coherent 属性和驱动 API 说明它们如何衔接，不把一个 smp 屏障或内联汇编 memory clobber 宣称为全部设备完成屏障。

未来负例可以覆盖 producer 发布、consumer 读取、ACK_ARM、槽位重用和 reset 的交错；固定编译结果及观测断言，分别检验旧数据读取、重复终态和旧 epoch 事件。以上是拟验证项，不表示本轮已有新测试 PASS 或已发现项目漏洞。

## 14. 独立评价

该论文最强之处是把模糊编程习惯变成可观测反例，同时认真检查测试工具链是否改变问题。它的 RMO 模型、旧硬件缓存结论和测试规模都有明确边界。

对项目，它补充的是认证通信和完成状态的顺序论证方法。应结合现代平台语义和原生驱动同步建立本项目证明，避免照抄 2015 CUDA 修复指令，也避免把相邻一致性论文冒充新的 CCA GPU TEE。

统一记录：主文、附录与部分作者结果页静态研读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增 PASS｜公开历史实测、模型范围与项目推断分开登记。
