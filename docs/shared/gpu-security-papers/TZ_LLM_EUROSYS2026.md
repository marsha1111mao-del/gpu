# TZ-LLM：模型恢复流水线、可信任务启动与 TEE–REE 加速器共享

研读日期：2026-10-27。阅读 18 页原文正文与 artifact 附录。实际保护对象为 RK3588 NPU 和端侧 LLM；对本项目的价值在共享协议、启动授权和生命周期，不把它误记为 Arm GPU 或 CCA 的实现。

## 1. 书目信息和版本

| 项目 | 内容 |
| --- | --- |
| 标题 | TZ-LLM: Protecting On-Device Large Language Models with Arm TrustZone |
| 作者 | Xunjie Wang、Jiacheng Shi、Zihan Zhao、Yang Yu、Zhichao Hua、Jinyu Gu；前两位共同一作 |
| 会议 | EuroSys 2026，2026-04-27 至 04-30，Edinburgh |
| DOI | [10.1145/3767295.3769334](https://doi.org/10.1145/3767295.3769334) |
| 原文 | [SJTU/IPADS 作者 PDF](https://ipads.sjtu.edu.cn/zh/publications/eurosys26-wang.pdf) |
| PDF SHA256 | `f35721fa68b07c4685ed7b6c04c0c9892b46fe9eacae0aab4747d3540ba6f4fb` |
| Artifact | [Zenodo 17213486](https://doi.org/10.5281/zenodo.17213486) |
| 公开仓库 | [TZ-LLM/tz-llm-ae](https://github.com/TZ-LLM/tz-llm-ae) |
| 固定主提交 | `3cdbdfb8be6c0c50003b0312f8f95f46144ac3cd` |
| 阅读范围 | 正文 §§1–8、附录 A；重点 §§3–7 的协议、实现、安全与实验 |

本轮 Zenodo API 和页面访问均被拒绝连接，随后取得上述 GitHub artifact。README 明确对应本论文、作者和 Figure 10/11/14，已固定主提交及子模块 gitlink；以下分别说明已读取代码与未完成的核验，不声称完整源码审计或复现。

## 2. 问题：内存效率与首次响应的矛盾

把 LLM 文件加密不能阻止恶意移动 OS 读取推理中的明文参数。把整个推理框架放入 TrustZone 又面对两个问题：静态保留数 GB 安全内存损害普通应用；按需分配、加载、解密则增加 TTFT。CPU-only TEE 还无法充分利用 NPU。

原文用 8-bit Llama-3-8B、512-token prompt 展示 strawman：约 8GB 参数，CMA 分配约 4.2s、加载约 4.1s、解密约 0.9s，合计冷启动约 11.6s；CPU prefill 约 164.6s。这是特定平台示例，不是所有端侧 LLM 的固定成本。

同时在两个世界分别部署完整 NPU 驱动，会增加可信代码和设备 detach/attach 的重复初始化，原文测约 32ms。因此 TZ-LLM 同时优化模型恢复和驱动共享，而不是仅增加一个受保护内存区。

## 3. 威胁模型与保护目标

攻击目标是模型参数，以及可帮助模型窃取的 activation、KV cache 等中间结果。攻击者可控制全部 REE 软件、完整 REE NPU 驱动和非安全设备；其他 TA 与安全设备也不因位于 Secure World 就受信任。

可信基包含 TEE OS、LLM TA/inference framework、TEE NPU 驱动、TrustZone/EL3 和 NPU 硬件，以安全启动建立完整性。物理攻击、侧信道、密码分析和 DoS 不在其主要保证范围。

这不是任意恶意模型代码的验证系统，也没有证明多个互不信任 GPU 地址空间并发执行。模型提供方的输入/输出策略和推理框架本身可信；应与本项目需要隔离恶意 Client GPU 工作负载的目标区分。

## 4. 总体架构与可信边界

LLM 框架运行于 TA，REE CA 发起请求；REE 文件系统、CMA、CPU 线程调度器及 NPU 调度队列继续提供复杂资源服务。TEE 保留数据面和验证逻辑。

```text
REE 文件系统 / CMA / CPU scheduler / 完整 NPU control plane
                  ↓ 提供资源或调度建议
TEE OS：内存映射、TZASC/TZPC、同步与隔离
LLM TA：加载校验、解密、pipeline、可信 NPU data plane
                  ↓ 受保护启动和安全 IRQ
                 NPU
```

§3.2 还复用推理框架的初始状态，避免每次重新完成框架、tokenizer 等初始化。CPU 线程可由 REE 安排，但执行依赖的同步原语必须由 TEE 管理，防止恶意调度破坏程序顺序。

## 5. 恢复流水线和调度算法

模型图通常可预测下一算子需要哪些参数。TZ-LLM 把分配、I/O、解密与计算重叠，参数按图的拓扑顺序恢复；一旦依赖满足即可计算，不必等全模型加载完。

原文分析 I/O、CPU 工作和整体计算三类临界路径。优先执行已就绪的 CPU 计算，否则优先恢复较早将被用到的参数，减少计算被分配/解密阻塞。长分配、解密再拆成微操作，插入可抢占点，以解决操作粒度不齐造成的 pipeline bubble。

这里的抢占是恢复流水线的 CPU 操作调度，不等同于提供任意 NPU/GPU 长任务的安全抢占。作者将实验中最大临界路径耗时作为 TTFT 下界比较；接近该下界不等于对任意动态图证明全局调度最优。

## 6. 部分缓存与动态安全内存

优先缓存早期参数可避免下一次推理起始泡沫；较晚参数可以在计算早期层时继续恢复。系统在推理后按逆拓扑顺序逐步释放参数，使仍缓存的区域连续，并按 REE 内存压力调节缓存量。

参数与 KV/activation/其他数据的布局适配 TZASC 区间约束。参数呈先入后出；KV 随 decoding 增长并在推理结束释放，固定对象放在其前部，避免破坏连续性。

三类接口为：

| 接口 | 状态变化 | 安全作用 |
| --- | --- | --- |
| `extend_allocated` | 先从 REE CMA 取得相邻页面 | TEE 检查连续性；此时可由文件系统直接读入密文 |
| `extend_protected` | 扩展受保护区并映射给 TA | 开始处理明文前阻断非授权访问 |
| `shrink` | 解除 TA 映射、收缩保护区并归还 CMA | 交还前清除秘密，不能仅减少软件计数 |

将 allocated 和 protected 分开可减少 bounce buffer 和复制，却要求**密文加载、保护建立、校验/解密和消费之间的顺序正确**。对一般 GPU 对象，需要重新证明所有权和可写者，不可仅凭 CMA 连续性判定授权。

对于 MoE、early-exit 等不确定图，预取可能包含本次未用参数；作者明确指出可能次优。当前系统 decoding 期间保留参数，结合更激进的参数换入换出留作未来工作。

## 7. Co-driver：保留最小可信数据面

TEE NPU 数据面包含三项闭合职责：创建执行上下文（I/O 页表、寄存器命令、输入输出）；通过 MMIO 启动；处理完成 IRQ。REE 保留初始化、power/frequency 管理和调度。

安全任务向 REE 提交的是执行上下文为空的 shadow job。REE 选择它时经 SMC 交给 TEE，TEE 检查并启动真实作业。因此 REE 能建议何时运行，但不能替换真实安全命令和输入。TEE 驱动运行于用户态，只映射该 NPU MMIO；NPU 仅被授予任务上下文所在区域，不能访问整个 TEE。

原文将数据面从控制面状态独立出来，这是一个需要按设备验证的设计条件。对于 GPU，全驱动状态、固件调度和 GPUVM 可能耦合更深，不能只按函数名称机械拆分。本项目已经选择完整驱动可信，可在同一 Proxy 内采用授权检查，而无需重建整套 co-driver。

## 8. 安全切换与任务重放防护

非安全→安全切换顺序是：先封锁 REE 的 NPU MMIO 并把 IRQ 路由 TEE；再等待正在执行的非安全任务结束；最后授予 NPU 访问受保护内存。

先封启动入口再等待，避免“检查空闲时又启动新任务”；先结束旧任务再授权新内存，避免旧执行利用新权限。对于项目，这可转化为禁止新引用/启动、确认旧状态、安装授权、可信启动的偏序，独立于具体硬件寄存器。

TEE 对 shadow job 回调检查：真实 job 已初始化、尚未发出；其单调序号匹配执行序号。前者阻止任意启动和重复提交，后者阻止 REE 重排。收到安全完成 IRQ 后，TEE 恢复普通模式并通知 REE 释放 shadow job。

**迁移边界：** 单调序号用于该系统的执行约束，不能原样变成本项目的全 GPU 全局 FIFO。GPU 多队列可合法并行和乱序完成，应按 queue/session、依赖关系及 device epoch 检查。安全 IRQ 的来源认证也不能自动证明错误状态、指定 job 的成功和 DMA 停止这三个事实。

## 9. 安全论证及仍需核对的问题

§6 分析直接读取、DMA 和四类 Iago 接口：内存扩展、NPU 调度、模型加载、CPU 线程调度。对应检查为地址关系、安全 job 状态/序号、内容 checksum 以及 TEE 同步。保护其他 TA 还依赖用户态驱动权限与 TZASC DMA 范围限制。

原文称模型加载结果以 checksum 验证；在强恶意 REE 模型下，还需核实期望 digest 的可信来源、与模型版本和参数块的绑定，不能把普通可替换 checksum 当消息认证。此处是 artifact 待核验问题，本轮没有构造绕过或判定漏洞。

分配大小和任务时序对 REE 可见，可能泄漏模型结构。作者将侧信道置于范围外，并提出 dummy load/compute 等方向；没有证明参数永远不能经这些通道泄漏。服务的正确执行也依赖可信框架与硬件，非通用数值结果证明。

## 10. 实现与可信基

原型基于 OpenHarmony 4.1、Linux 5.10、Rockchip NPU driver 0.9.8 和 llama.cpp。已有 TEE OS 约 17k LoC，新增映射 62 行、TZASC/TZPC 50 行；LLM TA 增加约 1.2k pipeline、1k NPU data plane 与 OpenSSL，REE Linux 增加 364 行。

所以“约百行特权修改”不能改写成“整个系统仅百行 TCB”。LLM framework、加密库和 NPU driver 仍在模型保护的信任基础内。安全启动完整性也不自动消除它们的代码漏洞。

## 11. 实验平台、基线与结果

Orange Pi 5 Plus / RK3588，4×A76 2.4GHz、4×A55 1.8GHz，16GB RAM，1TB NVMe，三核 NPU。模型为 8-bit TinyLlama-1.1B、Qwen2.5-3B、Phi-3-3.8B、Llama-3-8B。部分测试用 stress-ng 占用 13/11/10/6GB，分别制造 CMA 迁移压力，且压力线程与 LLM 绑不同核。

三种基线不能混淆：Memory 基线预载全部参数；Flash 基线在 REE 流水化加载、无需解密和 CMA 保护；Strawman 为安全 CPU-only 冷启动方案，没有恢复流水线及 TEE NPU 支持。

| 结果 | 比较对象与条件 | 可支持的结论 |
| --- | --- | --- |
| TTFT 降低 76.1%–90.9% | UltraChat、PersonaChat、DroidTask，相对 Strawman | 组合设计改善特定安全冷启动基线 |
| TTFT 增加 5.2%–28.3% | 同组 workload，相对 REE-LLM-Flash | 仍有保护与恢复成本，非比无保护系统普遍更快 |
| 固定 prompt 实验最高约 55.3% TTFT 开销 | 中等长度 prompt，相对 Flash | 真实开销依赖恢复和计算重叠程度，不能只报平均范围 |
| decoding 提升 0.9%–23.2% | 相对 Strawman | NPU 对单 token 的收益低于 prefill |
| decoding 下降 1.3%–4.9% | 相对 REE | 包含 TEE–REE NPU 协作成本 |
| NN / LLM 额外减速最多 3.8% / 3.0% | YOLOv5/MobileNet 与 Qwen/Llama 时分共享，对照 REE 共享；TEE 参数 100% cached | 安全切换的增量成本；非任意恶意并发保证 |
| 切换成本占 TTFT 1.6%–2.7%、decode 2.3%–5.7% | SMC、TZASC/TZPC、GIC 合计 | 有必要分开报告控制路径和端到端指标 |

Strawman 对比同时改变框架恢复、NPU 可用性和 pipeline，不能将全部收益归因于某一个模块。CMA 对其他 REE 应用造成瞬时干扰，Geekbench 部分比较下降最高 6.7%/5.8%；它不是无外部成本的优化。

## 12. 原文与附录的数值表述差异

§7.1.1 和 Figure 10 将 5.2%–28.3% 对应 **REE-LLM-Flash**；附录 A.4.1 的 Claim C1 却写成 **REE-LLM-Memory**。正文还明确给出相对 Memory 在 UltraChat 中达 2.5–3.7 倍开销，两者不应混用。本报告按正文基线定义和 Figure 10 解释，保留附录不一致的事实。

固定长度 Figure 9 的 strawman 改善范围与真实 benchmark Figure 10 不完全相同，也不要把正文某一最大值拼成所有场景的上界。论文没有提供本项目 GPU glmark 可比测量。

## 13. Artifact 范围与复现限制

附录要求 Orange Pi 5 Plus、Linux 构建机、8GB RAM/100GB 磁盘、Docker、Python 和 OpenHarmony connector。它列出 `scripts/1-end-to-end-prefill.sh`、`2-end-to-end-decoding.sh`、`3-caching.sh` 对应 Figure 10、11、14。

固定 artifact 的子模块包括：TEE OS `86807b2d9aa70f7d3e7434e7aa7a94163207a42a`、llama.cpp `158b3bd6ddd0ff0e2975301e965fcd9f387ddeeb`、Linux `a118249b80dc8a600a87b98f60231a42fea9b648`、tzdriver `80bdd96dc33df17dea4eefca34b9d5d3bb2a0ac2`。已取得 TEE OS 与 llama.cpp 的完整非截断 Git tree，分别定位了 `rknpu-driver.c`、RK3588 firewall/IRQ 代码、`src/pipeline.cpp` 等真实路径。

已读 README、`.gitmodules`、prefill 包装脚本及 TEE libc 的 `npu_interface.c`：可见 `chcore_alloc_dma_mem`、直接初始化 NPU/IOMMU MMIO 和 IRQ、任务提交的 task object/core mask。这仅确认公开实现并非空仓库；任务单调序号、所有权限切换和清零路径尚未完成端到端源码核验。部分原始文件下载超时，不能据未取得内容判定机制缺失。

README 也将 5.2%–28.3% 的基线写作 REE-LLM-Memory，重复了正文与附录的基线不一致；不能视为已解决该差异。其构建依赖预备 Docker 镜像和板端环境，因此公开源码不等于本轮具备完整可复现输入。脚本主要围绕性能主张，不能据其存在推断已提供恶意 IRQ、撤销竞争和跨租户攻击测试。

## 14. 与项目及其他论文的关系

相对 StrongBox/CAGE，TZ-LLM 把模型框架纳入 TEE 并强调大模型内存恢复；相对 ASGARD，选择小可信数据面而非完整 VM 驱动直通。与 PORTAL 的共同点是用可信组件控制最终设备访问，与 CAEC 的共同问题是身份可信之外还要验证请求语义。

对本项目最直接的迁移是：可信启动与完成构成闭合路径；Client/Host 可以提出调度和撤销请求，只有 Proxy 根据可信当前状态提交授权变化。用户已假设平台保护 HPA、实际 PTE 与 MMIO，研究重点应落在授权快照、状态机和生命周期一致性，不复制 TZASC 连续区限制。

## 15. 后续研究和验证问题

可为 job 私有记录绑定 Client 实例、session、GPUVM/root、对象 backing generation、job/fence 与 device epoch。启动前只接受合法状态并固定控制输入；通知允许合并和重放幂等，最终完成必须来自权威状态；撤销必须阻止新启动并确认旧访问结束后再复用页面。

负例包括 shadow/真实任务错配、重复启动、合法并行被错误禁止、旧代 job 回调、保护开放前未排空旧任务、密文块/模型版本替换、clear 与归还竞争。性能按冷/热缓存、内存压力、prompt 长度、并发数分开测，避免用单个 TTFT 倍数解释共享 GPU 性能。

本篇未改运行代码，无新增性能测量；无硬件 run-id、无新增硬件 PASS。公开代码仅完成上述定向静态核验，未执行作者原型。
