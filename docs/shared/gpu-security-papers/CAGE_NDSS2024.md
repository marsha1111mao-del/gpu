# CAGE：Shadow Task、双向保护与任务级独占的安全边界

研读日期：2026-10-27。依据 NDSS 原文和作者公开代码的定向静态检查。本文将论文设计、功能模拟、性能模拟及代码差异分别记录；代码片段审查不等于完整漏洞审计或运行复现。

## 1. 书目信息与版本

| 项目 | 内容 |
| --- | --- |
| 标题 | CAGE: Complementing Arm CCA with GPU Extensions |
| 作者 | Chenxu Wang、Fengwei Zhang、Yunjie Deng、Kevin Leach、Jiannong Cao、Zhenyu Ning、Shoumeng Yan、Zhengyu He |
| 会议 | NDSS 2024 |
| DOI | [10.14722/ndss.2024.24763](https://doi.org/10.14722/ndss.2024.24763) |
| 原文 | [NDSS PDF](https://www.ndss-symposium.org/wp-content/uploads/2024-763-paper.pdf) |
| PDF SHA256 | `8517554d28f352fd05aa608d3903a6e942432f560a485a6a69a6d6944602cfdc` |
| Artifact | [Compass-All/NDSS24-CAGE](https://github.com/Compass-All/NDSS24-CAGE) |
| 已有固定代码记录 | `c79106486eae0e55b49c3f98c0d4bb01a3d3a91b`；下述检查限公开性能原型相关文件 |
| 阅读范围 | 正文 §§I–VIII，重点 §III、§IV-B/C/D、§V、§VI、§VII |

后续同方向 TDSC 工作不能仅凭标题当作本论文完全相同的版本；未取得并比较其全文前，不合并新增机制与实验数字。

## 2. 研究问题与总体选择

CCA 原生保护 CPU Realm，但普通 GPU 既不能直接访问 Realm，也不能让不可信 GPU 驱动直接处理秘密。将完整驱动和 runtime 放进每个 Realm 又增加可信计算基和适配成本。

CAGE 将复杂但不需要秘密的资源分配、任务编排留在 Host。Host 管理空的 stub task；可信 Monitor 根据认证输入构造 real task，在受保护的 GPU 执行窗口内替换真实数据和页表，执行后恢复 Host 视图。

这是“保留不可信大驱动、用小可信组件接管关键窗口”的路线。本项目已经选择完整可信 Proxy 驱动，因此主要借鉴其授权和切换不变量，不必重新实现整个 stub/real 工作流。

## 3. 威胁模型与可信基

攻击者控制 Normal/Secure world 全部软件，包括 GPU 驱动、runtime、OS、Hypervisor、其他 DMA 设备，可提交恶意 GPU 任务、修改元数据、改变调度顺序及返回错误内存映射。保护对象为敏感输入、中间数据和结果；NN 实验还包括权重和偏置。

可信部分为 Root Monitor、安全启动、硬件信任根、GPU 硬件及 CPU/设备 GPC。CPU Realm 隔离由 RMM 或 SHELTER 一类机制提供。Realm OS/RMM 在用户态端点部署场景可不出现，不意味着服务器 Realm VM 可以省去 CPU 隔离。

侧信道和 DoS 排除。论文讨论未来 MPE 保护物理内存，但实际 FVP/性能原型没有据此完成物理加密验证。GPU MCU/固件的可信加载和持续状态也不能只由“信任 GPU 硬件”自动证明；这是之后 MOLE 要求补清的边界。

## 4. Shadow Task：把控制输入与秘密数据分开

用户将任务代码、buffer 描述交给不可信 Host 创建 stub 环境，同时经安全通道将秘密和任务认证值传入 Realm。认证值覆盖代码、描述及 task index，用于防止 Host 替换代码/属性或改变预期顺序。

Host 创建 metadata、code、空数据缓冲和 stub GPU 页表，将 stub 放入原生调度队列。GPU 页表更新被记录并在提交时合批交给 Monitor，而非每次更新都同步跨世界。Monitor 检查重复/非法映射，再构建 real 页表，把数据映射改为 Realm 内真实 buffer。

real task 重用 stub 的 metadata 和代码，但真实数据缓冲、真实页表另建。Monitor 验证描述并按真实属性准备数据，不能只信任不可信驱动提供的指针或页数。

task index 是预期顺序的一部分，不能独立证明跨 session/reset 的新鲜性。迁移到本项目时，应以可信 Client 实例、对象 generation、job/device epoch 绑定生命周期；平台已保护通信来源时也不必机械地给每条 RPC 增加 HMAC。

## 5. 启动顺序：先冻结可变输入，再检查 GPU

论文 §IV-B 的关键顺序是：保护 MMIO、metadata 和 code；替换 TTBR 与 buffer 指针；验证实际代码/描述；重新读取真实 GPU 状态；通过可信 MMIO 启动作业。

Host 被要求停止新提交并等待旧任务，但 Monitor 不信任其报告，会自行核查。保护 MMIO 在读取状态之前发生，防止攻击者在“检查空闲”和“启动秘密任务”之间插入恶意任务。

性能原型读取每个 Midgard job slot 的 `JS_STATUS`，非零表示存在任务，启动写 `JS_COMMAND_NEXT`。这些寄存器语义属于该 GPU 原型；现代 CSF 固件队列和多个 GPUVM 需要重新建立对应权威状态，不能直接复制寄存器判定。

## 6. 双向内存保护与真实映射

一边阻止 Host、Secure world 和其他 DMA 设备访问当前秘密执行环境；另一边限制当前 GPU 只能访问本 Realm 和本任务获准使用的代码/metadata。两边缺一不可。

| 保护对象 | CAGE 机制 | 迁移到项目要保留的性质 |
| --- | --- | --- |
| metadata/code | CPU/其他设备 GPT 临时配置为 Realm，检查不与其他 Realm/Root 重叠 | 验证后的实际控制输入不可被未授权 CPU/DMA 改写 |
| GPU MMIO | 在相应 GPT 配置为 Root | 不可绕过可信启动者替换 root/插入任务 |
| GPU 可访问范围 | 每 Realm GPU GPT，把合法区域设 Normal、其余 Root | 安装者可信之外，实际 HPA 也必须被当前主体授权 |
| CPU Realm 边界 | RMM Stage-2 或用户态隔离机制 | Client 之间 CPU 访问不能借共享服务绕过 |
| 旧访问缓存 | 修改视图后失效 GPC/相关 TLB | 撤销后的旧翻译不能继续有效 |

论文明确指出 GPT descriptor 只表达 PAS，不承载输出地址或读写权限。因此不能将其当作所有细粒度 R/W 权限的充分检查。本项目可以在受保护 Stage-1 PTE 中表达所需权限，同时核验真实 backing 和生命周期。

## 7. “共享”的准确粒度：任务时隙，而非同时执行

§IV-F 明确说 CAGE 实现 **task-level exclusivity**：Realm 独占一个任务时隙，允许不同 Realm/普通任务交替使用同一 GPU；StrongBox 则是更长的应用级独占。

这是真实的共享能力，但不能据 Table II 的“Sharing ✓”推出多个恶意 Realm kernel 同时驻留执行。其安全流程先等待 GPU 旧任务完成，再为当前 Realm 切换 GPU GPT，本质上依赖排他的保护窗口。

本项目若支持多 Client 并行提交/乱序完成，需要额外证明每 GPUVM 的可达内存、队列及固件控制对象独立、完成归属正确，且一个 Client 的错误/reset 不解除其他 Client 的保护。可参考时间独占作为对照方案，不能把它的证明直接当并发证明。

## 8. 完成和恢复：不是任意通知都代表成功

GPU 完成后 Monitor 恢复 MMIO 和 metadata，清理 GPU cache、页表相关 TLB，再恢复 Host 对代码/metadata/MMIO 的访问，结果留在 Realm。性能原型临时把 GPU 普通 IRQ 改为 Monitor IRQ，以便可信层接管恢复。

这不同于完全依赖 Host 注入虚拟 IRQ，但原文没有提供 Devlore 式通用 GIC 配置/优先级/LR/ACK 保护证明，也没有建立本项目多 Client 的 job completion 协议。IRQ 到达还需解释为正确 job 的合法终态，错误/取消不能冒充成功，终态又不能自动等同 DMA 已停止。

对恶意或错误任务，还应明确超时、复位、迟到中断、cache 清理失败时何时可以复用页面。上述是迁移要求，不是本轮已复现 CAGE 的安全漏洞。

## 9. GPT 优化及成立条件

多个 CPU/不可信设备 GPT 共享管理 GPU 专用区域的二级表，更新一次即可同步访问属性。其他区域仍有各自控制要求，不能全局合并 GPT。GPU GPT 从“全部 Root”的模板派生，只开放当前 Realm 和当前重用区，减少初始化成本。

优化只成立于共享表覆盖范围和所有使用者都适用相同属性；粒度混用会破坏边界。因此性能实验用包装 OpenCL API，避免不同 buffer/metadata 共用同一物理页。这是重要的内存布局条件，不能忽略或视作所有实际应用天然满足。

本项目可借鉴“共享模板、批量更新、只处理当前任务工作集”，但缓存命中必须仍验证 owner、generation 和权限；不同 Client 的逻辑归属不能因复用同一物理池被合并。

## 10. 两套原型和总 TCB

功能原型：RME FVP、test engine 模拟 GPU DMA、RME SMMU、Linux 5.3.0、TF-A 2.8；没有真实 Mali 模型。某些非法 GPU 页表场景通过 SMMU Stage-2 近似验证，不能称逐条验证了实际 GPU MMU 行为。

性能原型：Juno R2/Mali-T624、8GB、Midgard 驱动和 OpenCL；用现有 Armv8 寄存器、内存读写和地址翻译 TLB 指令模拟 CCA/GPC 操作。可用于估计保护软件开销，不能确认真实 GPC 每次内存访问的延迟或所有硬件属性。

新增 Monitor 1,301 LoC：shadow task 667、保护350、GPT优化137、其他147；还需已有 Monitor、CPU 隔离软件及可信 task/用户侧输入。Table II 给 Monitor 约0.4M、RMM约26k或 SHELTER约2k。所谓小 TCB主要指可信增量和排除大驱动，不能写为全系统只有1.3k行。

## 11. 评估与基线

| 实验 | 原文结果 | 必须保留的解释 |
| --- | --- | --- |
| 六项 Rodinia | +0.58%–5.31%，摘要平均2.45% | 对照同平台 native；不是全部 NN 上界 |
| LeNet-5 | 332.58→336.70ms，约+1.24% | GPU计算仅约1.30ms，软件栈占主要部分 |
| SqueezeNet | 788.73→812.62ms，约+3.03% | 当前任务工作集替换，非全模型缓冲每次处理 |
| MobileNet-v1 | 898.62→967.30ms，约+7.64% | 超过2.45%摘要平均，不应隐藏 |
| GPT共享二级表，按内存大小 | 更新开销降低87.40%–87.50% | 保护区大小和GPT数量固定条件下 |
| GPT共享二级表，按GPT数量 | 降低50.01%–93.65% | 额外设备仍有TLB维护，不是免费扩展 |
| GPU GPT模板初始化 | 降低84.63%–96.55% | 模拟2/4/8/16GB布局，非应用总延迟 |

Rodinia 包括 KNN、PF、LUD、H3D、LMD、GS，任务数跨度很大。Table V 给 GS 4094 tasks，正文另写4096，引用时保留差异。Table VI 的 GPU/GStack 是执行时间组成，不能全称为相对 native 的新增安全开销。

与 StrongBox 有同平台比较，其他系统多为异平台/无法完整复现，不据其横向表做严格速度排名。本轮未获得足以重算尾延迟、置信区间和全部原始样本的数据，也未进行作者实验。2.45%不能转化成本项目完整720p glmark的预期损失。

## 12. 公开代码：关键校验与论文承诺存在差异

仓库分 functionality-prototype 与 performance-prototype。定向读取性能版 `arm-tf/bl31/shadow_task.c`：提交路径调用 `check_code_integrity()`，但该函数内不匹配分支的 ERROR/panic 被注释，末尾返回0；另有 TODO 说明闭源 OpenCL 的完整 GPU code buffers 定位尚未完成。

同文件 `hmac_sha256()` 中 `k_ipad/k_opad` 未先按标准常量初始化便作异或，密钥复制注释；32字节 `ihash/ohash` 却被以64字节读取/复制。静态上可见这些长度和初始化问题，但本轮没有执行、构造触发或确认编译器/布局下的具体后果。

这支持“公开性能原型不能当作所有完整性检查均已可靠实现”的结论；不能据此宣布所有版本、功能原型或整篇机制均已被攻破。也不能假设测得性能自然包含一个修复后完整认证实现的同等成本。修复后应重新验证正确性与开销，而非沿用旧PASS。

## 13. 与项目及其他工作的关系

相对 StrongBox，CAGE 通过 GPC 排除不可信 Secure world，并从应用独占缩小到任务独占；相对 ACAI，选择 GPC与可信 Monitor 重建任务，而非完整 Realm 驱动及设备映射管理；相对 PORTAL，安全执行点更集中在 Monitor，设备管理通用性较小。

MOLE 要求把 MCU/firmware 纳入信任边界；PhantomMap 要求检查实际页与生命周期；Devlore/TEEtime 说明中断保护需要独立论证。项目适合借鉴 CAGE 的受保护执行快照与冻结顺序，沿用已经选择的完整 Proxy 驱动路线。

## 14. 可研究机制与负例

建议将可信 job 记录作为连接点：认证 Client 实例、session、GPUVM/root、对象 backing generation、执行配置与 device epoch。启动检查只消费可信快照，通知只唤醒读者，权威完成记录决定状态转换；回收另有 quiescence 和映射失效屏障。

负例包括校验后改写、伪owner、重复页/权限扩大、恶意任务藏在旧队列、重复或乱序提交、旧epoch完成、复位中撤销和页面复用。合法并行也必须通过，不能通过强制所有工作串行而误称已证明原并发设计。

未改运行代码，无新增性能测量；无硬件 run-id、无新增硬件 PASS。
