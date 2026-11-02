# MC Mutants：GPU 内存一致性测试能力与统计边界精读

研读日期：<date start="2026-10-27" />。原库编号 TGS-058。已读 16 页作者全文及 artifact 附录，核对固定分析代码，并独立重算三组作者公开数据的相关系数。本文是验证方法文献，**不是 TEE 或 CCA 防护系统**。未改运行代码，无新增性能测量。

## 1. 书目信息与版本

Reese Levine、Tianhao Guo、Mingun Cho、Alan Baker、Raph Levien、David Neto、Andrew Quinn、Tyler Sorensen，MC Mutants: Evaluating and Improving Testing for Memory Consistency Specifications，ASPLOS 2023 Volume 2，473–488，DOI `10.1145/3575693.3575750`。

来源：[正式 DOI](https://doi.org/10.1145/3575693.3575750)、[作者全文](https://reeselevine.github.io/assets/mc_mutants-C82aLggY.pdf)、[数据/分析仓库](https://github.com/reeselevine/mc-mutants-artifact)、[归档 DOI](https://doi.org/10.5281/zenodo.7196061)。全文 1,105,733 字节、16 页，SHA256 `31d673290924cdcfe723f0398e87787a20d3340536c3318682431e086144423d`。

PDF 文本提取有 CFF 字体/xref 警告，正文可读取；本文使用可核对的代码、表格与文字重述模型，不把提取异常的排版当额外公式含义。

## 2. 问题：如何衡量一次“没有失败”的测试

真实内存一致性违规很少出现，不能靠真实漏洞数量直接调优测试环境。即使运行大量 litmus tests，未出现禁止结果，也无法区分实现正确、错误罕见或压力环境无效。

MC Mutants 将原本被规范禁止的候选执行作小幅变异，使相关行为变成允许，再衡量测试环境能否观察到它。**这里 kill mutant 指观察到新允许的行为，不是在生产编译器中注入漏洞，也不等于已经发现真实漏洞**。

贡献由三部分组成：系统化生成 mutants；GPU Parallel Testing Environment（PTE）；按时间预算和复现目标选压力配置。它关注测试环境能力，和传统白盒源码 mutation score 的对象不同。

## 3. 模型、前提与范围

研究当时 WebGPU 仍在演进，论文给出的是 pragmatic subset，作者明确不是官方完整形式模型。测试主要为跨 workgroup、全 atomic 的 trivially data-race-free 程序，避免测试主体因数据竞争而没有定义行为。

候选执行包含 program-order、reads-from、coherence、from-read 等关系；禁止执行可用所选模型中的顺序环解释。mutator 改动与语法有关的边，例如操作顺序、地址相同与否、同步 fence，确保能够生成可运行的黑盒测试。

两个必要条件：变异行为在被测实现上可观察；观察变异行为与真实违规具有足够关系。规范允许不代表实现必然出现该行为；若实现比规范强，低 mutation score 未必说明测试差，应根据明确的实现模型裁剪不可能 mutants，而不是任意删掉难测项提高分数。

本论文没有恶意 hypervisor、Client 身份、设备固件或密钥 TCB，也未证明不同 VM 的共享队列正确。其统计方法需要结合项目自己的协议与内存语义重新定义。

## 4. 三个 mutator

| 变异方式 | 原约束与改动 | Conformance / mutants |
| --- | --- | --- |
| 三事件 reversing po-loc | 对同一位置的两次操作交换程序顺序 | 8 / 8 |
| 四事件 weakening po-loc | 把一部分操作改到另一个地址，使单位置约束变弱 | 6 / 6 |
| 四事件 weakening sw | 删除 release/acquire 中一个或两个 fence | 6 / 18 |
| 合计 | 特定模板中的组合 | 20 / 32 |

例如 CoRR 原测试检查同一线程读到新值后又读旧值的违规；变异让另一个线程的写可以合法插在两次读取之间，以测量细粒度交错是否被压力触发。普通 MP 移除同步后允许观察 flag 新而 data 旧，它可成为相关同步违规的调参代理。

“模板内完整组合”不是对任意程序、任意 MCS 缺陷的完备性证明。RMW 的替换也按是否保留目标关系选择，部分仅选最多替换的变体，不能将数量解释为全部可能实例。

## 5. PTE 怎样并行而不污染测试

每个线程执行两个不同实例的一部分，通过互素乘法置换 `v*P mod N` 分配另一半，保证全局一一对应，同时避免简单邻接、分支发散和重复配对。每实例有独立位置，通过地址置换、workgroup striping 和压力线程增加多样交错。

由此把 GPU 线程用于大量并行小实验，替代每轮只跑一个实例。单实例环境 SITE 是 PTE 配置空间的子集，因此“PTE 理论上包含更好配置”不意味着有限随机搜索一定找到它；论文中 Intel 的 mutation score 就出现 SITE 高于当次 PTE 搜索的情况。

这不是将项目中的 Client/job 简单扩大并发就能复制的收益。项目任务有真实资源和恢复副作用，压力隔离、对象归属及回收条件必须保留。

## 6. 统计复现分数的含义

论文沿用近似：若同等预算中预计观察次数为 x，下一轮至少看到一次的概率为 `1-exp(-x)`；用每秒 mutant death rate λ 和预算 t 可写为 `1-exp(-λt)`。选择时间预算与目标 r 时，要求速率至少约 `ceil(-ln(1-r))/t`。

这是依赖过去观测代表未来、事件发生过程近似稳定的**模型复现分数**。它不是“实现正确的概率”，不是所有未知漏洞的检出率，也不是对恶意调度下零风险的密码学保证；设备压力、温度和不同执行阶段可能破坏稳定性。

每个测试 95% 不等于全套 95%。在独立性近似下，20 项同时复现约 `0.95^20=35.8%`；每项 99.999% 则约 99.98%。正文不同段落出现 35.8%/36.5% 的近似表述，本文以明确公式说明，不为项目给出无模型依据的精确保证。

## 7. 跨设备选配置

先在多台设备上运行同样随机配置；对每个测试，选择达到目标阈值的设备数最多的环境；平手时选最小非零 death rate 更大的配置。它提供每测试一套可携带配置，而不是为已知每台设备各自过拟合。

忽略零速率在平手规则中用于比较可触发设备，不意味着零观测已经合格；最终合格数量仍按阈值逐项统计。未达到阈值的项必须保留，不能和可复现项合并称“所有设备通过”。

## 8. 实验平台、预算与基线

四设备：GeForce RTX2080、Radeon Pro5500M、Intel Iris Plus、Apple M1，覆盖四厂商和集成/独立 GPU；另用旧 Kepler 重现既有问题。论文时 WebGPU 尚未支持移动端，不是 Mali 或本项目 RK 平台实测。

使用 Chrome、每类 150 个随机压力环境；SITE 每环境 300 iterations，PTE 100 iterations、平均约 125k 测试实例。全设备调参总时长 PTE 9.27h、SITE 16.38h。另有无压力的 SITE/PTE baseline，避免把并行效果与所有压力策略混为一谈。

## 9. 定量结果与容易误读的数字

| 测量 | 论文结果 | 正确解释 |
| --- | --- | --- |
| mutation score | SITE 46.1%，PTE 83.6% | 128 个 device/mutant 组合的观察，增加 37.5 个百分点，相对约 81.4% |
| 无压力 baseline | SITE 6.3%，PTE 72.7% | 压力与并行贡献都要保留；正文一处 PTE 写 83.5% 是近似差异 |
| 平均 death rate | PTE 约 35k/s，约 SITE 2731 倍 | mutant 观察吞吐，不是应用或 GPU 安全系统加速 |
| 64s / test、99.999% 目标 | PTE mutation score 约 82%，SITE 约 43% | 不是 100% 测试/设备达到该复现目标 |
| 达到约 43% 的预算 | PTE 约 1/64s，对比 SITE 64s | 此操作点预算比为 4096 倍，不是任意覆盖目标都相同 |
| AMD MP-relacq 违规 | PTE 约 10.4 次/s | 特定缺陷/平台，不是所有漏洞触发率 |

每测试 64 秒与官方 CTS 最终选择约一分钟整套测试，是不同覆盖目标/配置的结果；不能将论文摘要的 64s/test 改写为全部 20 项只需 64s，或反过来说官方 CTS 固定需要 20×64s。

## 10. 真实问题、规范变更与采用情况

论文发现 Apple 平台 Intel GPU 上 Chrome→Metal 的 CoRR 违规，报告时等待确认解决；另发现 AMD Vulkan 路径 MP-relacq 问题，带来驱动修复和 WebGPU 规范变更。WebGPU 原先给跨 workgroup barrier 的承诺过强，之后减弱为该范围的 SC-per-location；**修复实现与修订规范不是同一件事**。

作者用两项新问题和一个重现的 NVIDIA Kepler 既有问题检验代理有效性，150 组配置的 PCC 为 Intel 0.996、AMD 0.967、NVIDIA 0.893。三个案例分别涉及三个 mutator，有助于支持方法，但仍是有限案例，不是普遍数学等价。

论文报告 PTE 被 WebGPU CTS 采纳，并至少有一个测试进入 Vulkan CTS。证据入口：[WebGPU CTS PR1330](https://github.com/gpuweb/cts/pull/1330)、[Vulkan CTS 固定提交](https://github.com/KhronosGroup/VK-GL-CTS/commit/0f0473342f80ab4ddcdd3588c034fc41b285e6ca)、[WGSL 规范修改 PR2297](https://github.com/gpuweb/gpuweb/pull/2297)。本次以论文和引用登记，没有重新审计现代 CTS 的全部相关提交。

## 11. 固定 artifact 与实际复核

数据/分析仓库固定 `3bdc5cc82d7d2e070fd8e0b968b0fc82878dba1e`，完整树 31 项、未截断。已读 README、`analysis.py`、`mk_figure6.py`、`mk_table4.py`，并取得 `mk_figure5.py`；后者本次未完整审计。已读取三份 `correlation_analysis` 原始 JSON，不声称读完或复现全部 PTE/SITE 数据。

`analysis.py` 按各环境最大观察速率统计 mutant，按目标速率合并配置；`mk_figure6.py` 分母明确为 128；`mk_table4.py` 选择的 mutant/test 配对与表 4 对应。CLI 的 `--rep 99.999` 会除以 100，内部使用概率 0.99999，移植时不能混用百分数和概率。

本次用独立 Python 标准库公式对三份作者数据做**离线复算**，每份 150 个配置，得到 Intel `0.996489131573927`、AMD `0.9671407023397377`、NVIDIA `0.8925262004687364`，与论文三位小数一致。记录位于本地 `mcmutants-correlation-offline-verification.json`，这是已给数据的分析核验，**不是重新在 GPU 上触发漏洞**。

论文托管站本次连接超时；README 指向可变化的在线界面及独立 `webgpu-litmus` 仓库，分析仓库固定不等于浏览器、驱动、网页生成器和所有依赖都已固定。没有运行作者 shader、安装其依赖或采集新 GPU 数据。读旧版规范时也不能直接用今天的浏览器判据而不记录版本差异。

## 12. 与 GPUHarbor、CCA/GPU 防护主线的关系

GPUHarbor 将此方法扩展到更多设备与便于参与的入口；MC Mutants 提供为什么压力配置应当有效的定量依据。PORTAL/CAGE/ACAI/PhantomMap 则提供可信设备访问和归属/生命周期设计，两条线可以结合，但各自不代替另一条的安全证明。

本项目信任完整驱动 ProxyRealm 控制 SMMU，并假设保护实际页表、根和 MMIO；软件授权翻译后由 GPU Stage-1 持续限访。这些前提不因本文使用不同 GPU 后端而改变。需要新增论证的空间在于身份和访问规则**在并发时序中仍被正确观察和执行**。

## 13. 对已有协议的具体迁移建议

项目已有 GPUVM、认证队列、私有快照、真实 native fence、cookie/epoch 和 IRQ127，不应重复提出这些功能。可将既有不变量转成具有明确对照的 mutation campaign：移除一个发布/消费屏障、跳过一次 epoch 检查、错绑 Client/job、提前释放引用、把错误事件改为成功，观察验证环境是否能稳定发现对应禁止状态。

此类协议 mutation 是本项目研究建议，**不是论文已经提供的通用 GPU TEE 验证器**。协议缺陷不一定能像弱内存模板那样通过改测试转为合法行为；某些 mutation 必须在离线模型或隔离测试实现中完成，不能混称原论文黑盒方法。

对每项分别报告 mutation 是否实际可触发、触发次数/预算、合法路径误报和未覆盖状态；对无法触发的 mutation，调查调度/压力覆盖，而不是直接宣称当前实现正确。共享 IRQ 丢失或延迟是可用性事件，伪造完成导致提前回收是完整性事件，应使用不同判据。

## 14. 独立评价与研究价值

本文最有价值的是给“没有失败”增加可审查的测试能力依据，并保留实现比规范强时的不可观察限制。其统计分数仍依赖代理相关性和实验分布，不能变成机密计算的绝对安全概率。

可据此增强项目第二部分的实验论证：身份/页授权不变量，加上事件状态机与回收条件，再加能触发故意错误对照的并发验证。性能只衡量保留正确条件后的成本；越权拒绝、重复完成、旧任务污染和恢复边界才是隔离目标的直接指标。

统一记录：原库 TGS-058 全文、固定代码及作者数据离线相关性复算｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增硬件 PASS｜论文及限定分析已完成，未复现 GPU 实验。
