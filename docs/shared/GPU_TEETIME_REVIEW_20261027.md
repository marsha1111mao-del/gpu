# TEEtime：Arm 中断隔离与可信 Proxy 模式精读

日期：2026-10-27。本文用于比较中断保护，不将 TEEtime 误归类为 CCA GPU TEE。

## 1. 论文和阅读范围

**It’s TEEtime: Secure Interrupt Isolation for Normal-world Enclaves on Arm**，Friederike Groschupp、Mark Kuhne、Moritz Schneider、Ivan Puddu、Shweta Shinde、Srdjan Capkun。TCHES 2026(1)，135–160，DOI [10.46586/tches.v2026.i1.135-160](https://doi.org/10.46586/tches.v2026.i1.135-160)。2025-09-15 接收，2026-01-16 出版。

本次取得并阅读 [原文](https://tches.iacr.org/index.php/TCHES/article/download/12670/12360) 的体系、隔离机制、设备共享、安全分析和评估部分，未完成独立源码 artifact 核验。PDF SHA256：`a511657dc83c1cf15624f376ae48a5dc89bd3cbef415f8bcff6834d955f8dc05`。

## 2. 研究问题与威胁模型

TrustZone 传统的单一 Secure world 很难容纳多个相互不信任、又需要直接设备访问的应用。把应用放到 normal-world 隔离域后，内存和 MMIO 保护仍不能自动隔离 GIC：其他域可能观察、伪造、改变路由或确认中断，进而泄露行为或改变可信执行流程。

TEEtime 依赖可信 Secure Monitor、平台访问控制器和 GIC，允许其他 normal-world domain 恶意。支持 temporal（时间上交替运行）和 spatial（不同核同时运行）两类部署。调度域可以阻止应用运行，所以不保证恶意调度下的可用性。

它不是把 normal-world domain 等同于 CCA Realm，也不是为 GPU 构造完整共享驱动；价值在于独立、细粒度的设备中断隔离框架。

## 3. 三个清晰的不变量

| 不变量 | 原文含义 | 对本项目的迁移 |
| --- | --- | --- |
| Rconf | domain 只能访问自己 INTID 的配置 | IRQ 注册、优先级、使能、路由修改需检查实际 owner |
| Rstate | domain 只能观察和改变自己中断的 pending/active/retired 状态 | 不能允许 Host 或其他 Client 清除/伪造受保护通知 |
| Rroute | 满足 enabled/priority 等触发条件的预期中断，在 owner 执行时只送入 owner | 物理 IRQ 正确到 Proxy，逻辑通知正确到对应 Client 实例 |

GIC 某些寄存器在一个字里打包最多 32 个 INTID，因此按 MMIO 页整体开放/关闭权限不够。一个获准访问自己中断的域，不能顺便改同寄存器中别人的位。

## 4. 时间隔离与空间隔离的机制

Temporal 模式将当前 domain 的中断设为 non-secure，其他 domain 的中断设为 secure 且禁用，从而限制非 owner 的配置和接收。切换时保存使能状态，保留 pending 信息，owner 恢复后再处理，不能直接丢掉非活动域事件。

Spatial 模式中，多个域同时运行，单靠 Secure/Non-secure 分类无法区分所有 owner。TEEtime 阻断直接 GIC MMIO，由 EL3 的 GIC Guard 按 INTID/位过滤访问，并限制 affinity 只能指向正确 owner 的核。中断到达正确核后，banked CPU interface 负责该核已收到的中断处理；不必把整个 GIC 虚拟化栈放入可信层。

兼容层可将旧软件 GIC 访问陷入并转交 Guard，减少对 OS 的修改。这仍带来执行开销，尤其不能把 temporal 的调度延迟误认为每次 IRQ 检查的固定成本。

## 5. 设备共享模式中，Proxy 与本项目最接近

原文讨论独占、multiplexing、handover、只读和 proxy 等模式。Proxy 模式保持只有 owner domain 直接访问设备，其他域通过跨域 API 使用功能；物理中断也只到 owner，由 owner 决定向客户暴露什么状态或通知。

原文 §4 明确说明，这要求 owner 实现特定设备 API，客户改用 API；它没有替服务自动完成参数和作业语义的安全证明。因此，“物理 GPU IRQ 属于可信 Proxy”与“某 Client 的 job 已完成”必须是两个检查层次。

对本项目而言，Proxy 本来就有完整驱动，适合在服务层维护每个 Client 的 GPUVM、对象、job/fence 和代际，而不是把物理 IRQ 原样广播给所有 Client。

## 6. 安全与评估结果的边界

评估包括 Arm FVP 及 Purism Librem 5 手机（NXP i.MX）；展示 Signal 应用与不可信系统共存、显示交接、网络和存储代理等，不是 RK3588 GPU 测试。

原文基于 TF-A 2.8，新增 1575 LoC，其中 baseline 1047、内存 39、设备 248、中断 241。新增行数不能当成完整系统或 domain 内 OS/驱动的总 TCB。

定时器用于确定中断触发时间。8.33 MHz 计数器下，调度 tick 到处理的中位差值 baseline 为 8；spatial 基本相近；temporal 的调度域 136、应用域 324，后者受调度与切换影响。另有 10000 次高精度定时器实验。**这些不是共享 GPU 从 job 完成到 Client 唤醒的实测延迟。**

| 应用 | Temporal 开销 | Spatial 开销 |
| --- | --- | --- |
| AES | 12% | 2.1% |
| OTP | 21% | 5.6% |
| LeNet | 15% | 1.8% |
| Memcached | 2.8% | 1.9% |
| Apache | 384% | 37% |
| Nginx | 373% | 29% |

网络负载依赖代理通道，temporal 下额外受到频繁抢占影响；不能仅选低开销计算负载概括整个系统。论文对 Shelter 等系统的对照也保留不同平台与实现条件，本项目不据此作统一排名。

## 7. 与 Devlore 的互补与差别

TEEtime 保护 normal-world domains 对 GIC 配置、状态和路由的访问，重点是隔离不同 owner；Devlore 针对 CCA CVM 保留 Host 虚拟化调度、由 Monitor 记录真实 IRQ 并由 RMM 检查注入。两者都直接否定“只保护内存就足够”，但机制和部署域不同，不能简单视为同一个方案的两个名字。

在本项目中，Devlore 更直接对应 GPU→Proxy 的 CCA 物理事件层；TEEtime 的 Rconf/Rstate/Rroute 很适合用于枚举保护对象和检查漏项。两者均不替代 Proxy 内部作业权限与生命周期证明。

## 8. 设计建议与后续问题

建议将 IRQ owner、物理 INTID、设备实例和可信处理入口明确写入平台接口；对跨 Realm 逻辑通知另定义端点 owner、session、通知代际与 ACK 状态。不共享物理设备的 Client 也不能修改 Proxy 的 IRQ 配置。

当一 IRQ 对应多个完成时，Proxy 从可信状态识别受影响 job，按 Client 分类更新受保护队列，再合并唤醒。Client 不应从“收到一个中断”推导“我的一个 job 成功”；应读取 job 权威状态，重复唤醒可幂等恢复。

后续先审核当前物理 IRQ 与 xshm 通知两条路径的权限边界，再验证错误来源、错误路由、提前/重复 ACK、Client close/reopen 和 device reset。尚未运行这些测试，不新增 PASS。

关联：[聚焦报告](GPU_CCA_TEE_FOCUSED_RESEARCH_20261027.md)、[Devlore 精读](GPU_DEVLORE_DEEP_REVIEW_20261027.md)、[CAEC 精读](GPU_CAEC_DEEP_REVIEW_20261027.md)。

统一记录：TEEtime 原文比较｜项目 glmark 本次未测 → 未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件命令、run-id 或新增 PASS｜保留比较结论，源码与 GPU 服务验证待后续任务。
