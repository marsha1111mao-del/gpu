# CAGE 期刊扩展：Arm CCA 机密加速、FPGA 描述符与独占生命周期

研读日期：2026-10-27。全文、正式书目信息及固定公开原型定向核验。本文是 NDSS 2024 CAGE 的版本增量解读，新增 FPGA 部分具有独立分析价值；不把同一架构的期刊扩展当作另一套无关系统。

## 1. 原文、发表年份与阅读范围

| 项目 | 内容 |
| --- | --- |
| 标题 | Building Confidential Accelerator Computing Environment for Arm CCA |
| 作者 | Chenxu Wang、Kun Lu、Fengwei Zhang、Yunjie Deng、Kevin Leach、Jiannong Cao、Zhenyu Ning、Shoumeng Yan、Tao Wei、Zhengyu He |
| 正式出版 | IEEE Transactions on Dependable and Secure Computing，23(1)，1308–1325，2026 年 1 月 |
| DOI | [10.1109/TDSC.2025.3615787](https://doi.org/10.1109/TDSC.2025.3615787) |
| 本次原文 | [作者公开接受稿，18 页](https://fengweiz.github.io/paper/cage-tdsc25.pdf) |
| PDF SHA256 | `36fdda1c13a06d7ee48ebcbf4083dfc2eede277ca41fb9fb48a9b4b9e3627e73` |
| 版本关系 | 正文 §1 明确为 NDSS 2024 CAGE 扩展；DOI/接受稿为 2025 年，正式卷期为 2026 年 |
| Artifact | [Compass-All/NDSS24-CAGE](https://github.com/Compass-All/NDSS24-CAGE) |
| 固定提交 | `c79106486eae0e55b49c3f98c0d4bb01a3d3a91b` |
| 阅读范围 | 全文 18 页，含 §§1–10、实验表格、参考文献及作者信息；重点比较 §§4、5、7、8 |

接受稿注明未经最终编辑，故具体内容以该 PDF 为证据；卷期页码由 Crossref 元数据确认。不能把接受稿年份和正式出版年份混写，也不能将 GPU 与 FPGA 两组开销混合引用。

## 2. 核心问题与相对会议版的增量

CAGE 要在不信任 Host OS、Hypervisor、Secure world 和大型加速器软件栈的前提下，允许 CPU Realm 使用 GPU 等加速器。其主线仍是 shadow task：不可信软件管理 stub，可信 Root Monitor 构造、验证并保护真正的执行环境。

期刊版的主要增量是从统一内存 Arm GPU 扩展到带独立内存的 PCIe FPGA。它新增 buffer 与传输通道绑定、可信 XDMA 描述符重建、FPGA MMIO 控制及整个机密应用期间的独占，并给出六项 FPGA 工作负载与对应安全分析。

它没有把 GPU 任务独占改造成恶意 Realm 的并发 GPU 执行，也没有新增完整的跨 Realm 中断通信协议。对本项目最有价值的变化是：同一种保护框架因设备状态保存位置不同，必须采用不同的授权对象和回收粒度。

## 3. 威胁模型与可信计算基

攻击者控制 Normal/Secure world 软件、大型驱动和 runtime、非机密应用及其他不可信外设，可以篡改任务描述、代码、映射、调度顺序和设备控制输入。目标是保护机密任务的数据机密性和完整性，并限制任务不能访问未授权的主存区域。

可信部分包括 Root Monitor、硬件信任根、安全启动，以及作者明确假设不恶意且无相关缺陷的加速器硬件和固件。CPU Realm 隔离仍依赖 RMM 或相应可信隔离机制。服务器 Realm VM 需要可信 RMM；只有特定端点用户态隔离部署才讨论可选 Realm OS/RMM。

侧信道、DoS 及所排除的物理攻击不在已证明范围内。第三方 FPGA 的硬件/固件真实性需要额外 RoT 与证明支持；固定 MMIO 地址只能约束软件访问路径，不能单独证明接入板卡或 bitstream 的身份。安全启动、远程证明和安全通道作为集成基础讨论，不等于本原型展示了完整生产级端到端部署。

MOLE 之后尤其应保留这一边界：CAGE 假设固件可信，不能用主存隔离自动推出设备 MCU 无恶意行为。本项目已接受可信固件加载假设，可以在该假设下讨论协议，无需将模拟硬件限制当作设计反例。

## 4. 共同执行流程：冻结、验证、限制与启动

用户把非秘密代码和 buffer 属性交给 Host 创建 stub，并通过受保护路径向 Realm 提供秘密和认证值。认证内容覆盖代码、buffer 描述及预期任务次序；Host 仅负责调度占位任务，Monitor 在提交窗口准备真实 buffer 和页表。

安全顺序为：先保护关键 MMIO、metadata/code；准备真实映射并替换任务引用；验证代码与描述；在可信层读取实际设备状态；最后通过可信 MMIO 启动。只要求不可信驱动声明“已经空闲”不足够；先读状态后允许 Host 继续写 MMIO 会破坏检查与使用之间的一致性。

GPU 原型检查 job slot 状态及地址空间配置，包括 `JS_STATUS`、任务头和 `AS_TRANSTAB/TRANSCFG`。这些寄存器属于 Midgard 原型，迁移到 CSF GPU 应重新定义固件队列与真实执行状态的对应关系，不能机械复用旧寄存器判断。

任务 index 保护次序，但不是跨会话、重启和设备重分配的新鲜性证明。正文提到可借鉴 TNPU 加入版本号防回滚，这是可集成方案，不能写成已实现并验证了持久新鲜性协议。

## 5. 双向访问保护及与软件 Stage-2 的关系

CPU 与其他设备的 GPT 阻止其访问当前秘密环境；当前加速器的 GPT 只开放当前 Realm 数据及复用的代码/metadata 区域。真实页表、MMIO 和控制数据必须受到保护，避免认证后被攻击者改写。

GPT 表达 PAS，不携带输出地址或全部细粒度读写权限。因此，CAGE 的 GPC 视图不能替代本项目对实际 HPA、Client 归属和 PTE 权限的验证。可以接受本项目的既定路线：ProxyRealm 根据 RMM 认证身份执行 IPA→HPA 软件翻译和授权，再生成受保护的直接 HPA Stage-1 映射，由执行期 Stage-1 持续约束访问。

期刊 §8 还指出，一个 SMMU 的 GPC/GPT 根配置可能为其所连接的 PCIe 流共享，而传统翻译表可由 StreamID 区分。作者提出结合 Stage-2，或未来增加每流 GPC 选择能力。这说明保护域划分必须与设备流的实际可达集合相符；它是需要明确的设计条件，不能据此否定用户给定的受保护 SMMU 与平台假设。

## 6. FPGA 新设计：认证 buffer-channel 关系并重建真实描述符

性能平台连接 Xilinx Virtex UltraScale+ VCU118，采用 XDMA IP 和驱动。H2C 通道把主存数据送入卡，C2H 通道把结果送回主存。仅认证 buffer 地址不足以阻止把合法数据送入错误通道或错误传输步骤。

§7.1 在 buffer 描述中使用 32 位 buffer ID 与 32 位 H2C/C2H channel ID，并将这种关系纳入认证；描述还包括传输 index 和目标通道。Monitor 先核查 Channel Status 的真实空闲状态，再根据认证描述建立真实数据与传输关系。

真实 buffer 可能大于 stub，不能只替换一个指针。Monitor 按 XDMA 格式在 Realm 中建立描述符链：H2C 更新 `Src_adr`，C2H 更新 `Dst_adr`，设置 `Nxt_adr` 串联多个描述符。论文给出的板端单描述符传输上限例子为 `0x1000`，不是所有 XDMA 系统的统一上限。之后设置 Channel Control 的运行位，计算后清除相应位。

与 GPU 复用部分不透明 metadata 相比，FPGA 公开描述符格式允许可信层直接构造真实传输对象。这是明确的机制增量。迁移到本项目时，值得借鉴的是认证“对象—操作—执行通道”的关系，而不是照搬 FPGA 驱动或假设清除运行位已经证明所有 DMA 事务均结束。

## 7. 两类设备的独占生命周期不同

| 项目 | 统一内存 Mali GPU | 独立内存 FPGA |
| --- | --- | --- |
| 受保护数据主要位置 | 可由主存 GPC 约束的共享主存 | 主存及卡上独立内存 |
| 分配粒度 | 单个机密任务的执行窗口 | 整个机密应用的生命周期 |
| 普通任务交错 | 两个机密任务之间可释放设备 | 应用中途不允许恶意任务进入 |
| 额外回收要求 | cache、翻译与控制状态恢复 | 还需清理独立内存后再交还设备 |

FPGA 卡上秘密不能单靠主存 GPT 隔离。若在应用两个任务之间释放控制，攻击者可能插入任务导出卡上状态。因此期刊版保持整个应用的 MMIO 控制权，结束后重置/清理专用内存。

GPU 的 task-level exclusivity 是分时共享；FPGA 的 application-level exclusivity 更粗。两者都不能作为多个恶意 Client 同时执行的隔离证明。对本项目，并发 GPUVM、固件对象和错误/reset 故障域需要单独论证；已有 GPUVM 和对象归属机制是分析起点。

## 8. 中断、完成和恢复：本文覆盖到哪里

GPU 仍采用临时将普通 GPU 中断交给 Monitor 的路径，完成后恢复 MMIO/metadata、处理 cache 与翻译状态，并让秘密结果继续留在 Realm。它减少了完全依赖 Host 虚拟通知的风险，但没有给出 Devlore 式 GIC 配置、虚拟中断 LR、优先级和 ACK 全链模型。

FPGA 清除通道运行位和可信描述符提供了控制基础，却没有完整展开本项目所需的 Client/session/context/job/epoch 完成授权、迟到中断、reset 后事件归属和页复用协议。论文 §§6.2、7.3 主要是设计层攻击情景分析，不能改写成对这些异步交错做过全面故障注入。

对本项目，persistent IRQ127、认证队列、私有快照、原生 fence 和 cookie/epoch 已经存在。后续价值在证明这些机制怎样组合：真实 IRQ 只触发观察；当前任务的权威状态才授权成功、错误或取消；映射撤销和物理页复用还需要 DMA 停止、翻译失效与清理条件。不能把这些已有机制重新列为缺失项。

## 9. 原型、可信增量与性能口径

功能原型运行于 RME FVP，Linux 5.3、TF-A 2.8，用 test engine 发起 DMA，没有真实 Mali 模型。性能原型使用 Juno R2、Mali-T624、8 GB 与 Midgard/OpenCL；FPGA 通过 PCIe 连接同一板端。真实加速器执行工作负载，CCA/GPC 操作采用 Armv8 指令、MMIO 与 TLB 操作模拟，因此不能称作实际 RME/GPC 硬件的端到端成本实测。

GPU Monitor 增量 1,301 LoC：shadow task 667、环境保护 350、GPT 优化 137、其他 147；FPGA 再增加作者报告的 140 LoC。1,441 是这些模块增量之和，不是整个平台总 TCB；既有 Monitor、RMM 或 SHELTER 等仍需计入。FPGA 140 LoC 的完整实现和逐行归属本次没有独立确认。

OpenCL 包装使数据与 metadata 按页对齐、避免共享同一物理页。这是保护粒度成立条件。GPT 共享二级表和模板减少初始化/更新，但需要所有共享表使用者适用相同属性；不能跨 Client 合并有不同归属或权限的逻辑对象。

| 实验 | 原文结果 | 解释 |
| --- | --- | --- |
| 六项 Rodinia GPU | 额外开销 0.58%–5.31% | 不能用 FPGA 开销范围代替 |
| LeNet-5 | 332.58→336.70 ms，约 +1.24% | 包含 GPU 软件栈，不是纯 kernel 时间 |
| SqueezeNet | 788.73→812.62 ms，约 +3.03% | 每任务处理当前工作集 |
| MobileNet-v1 | 898.62→967.30 ms，约 +7.64% | 不在 Rodinia 上界之内 |
| GPT 同步，改变保护区大小 | 降低 87.40%–87.50% | 是维护操作降幅，非应用加速比 |
| GPT 同步，改变 GPT 数量 | 降低 50.01%–93.65% | 仍有其他设备的维护成本 |
| GPU GPT 初始化 | 降低 84.63%–96.55% | 通常一次初始化，对总程序影响有限 |
| 六项手写 FPGA FFT/MM | 额外开销 9.61%–16.30% | 独立于 GPU 结果，不能称通用 GPU 平均 |
| FPGA MM-384 / MM-512 | 额外开销 11.59% / 9.61% | 保留作者任务标签，不静默修正规模 |

Table 5 存在名称与 size 列不一致：MM-256 标为 128×128，MM-384 标为 256×256，MM-512 标为 512×512，对应内存 0.75/1.69/3.00 MB。不能自行据内存数推断真正测试规模。FFT 为 1024/2048/4096 节点及 16.01/32.01/64.01 KB。GPU GS 任务数的表格 4094 与正文 4096 差异也保留。

没有据原始样本重新计算置信区间或尾延迟，也没有新的多 Client 并发、公平性与 reset 压力数据。本项目 glmark 分数不能由这些 OpenCL/FPGA 数字推算。

## 10. 公开 artifact：已有 FPGA 组件，但复现材料仍不完整

本次重新核对 HEAD 与固定提交一致。先前整个仓库递归树被截断，不能据其关键词搜索判断源代码不存在；本次改为读取未截断的根、一级目录及 performance 子树。`arm-tf` 递归树 3,033 项、`test` 30 项、`xdma-driver` 54 项，均未截断；没有声称完整审计 Linux 或全仓库。

固定 README 明确列出 Mali 与 VCU118 性能原型、`xdma-driver`，同时说明当前只公开 GPU Rodinia 测试，FPGA 应用将来发布。因此“没有公开任何 FPGA 代码”不成立，“已经具备完整 FPGA 性能复现材料”同样不成立。

已定向阅读 `xdma/cdev_cage.c`、`xdma_cdev.c`、`libxdma.c` 的 CAGE 控制路径，以及 Monitor 的 `gpu_protect.c`、`shadow_task.c` 相关部分：

- `cdev_cage.c` 提供保护开关 ioctl，以 `0xc700000a` SMC 通知 Monitor，并维护 `stop_submit`；`appid` 局部变量本身没有实现完整 Client 身份认证。
- `libxdma.c` 在受保护路径将描述符物理地址、H2C/C2H 方向经 `0xc7000007` 提交；停止路径经 `0xc700000b` 请求 Monitor 控制 MMIO。这里证实存在 FPGA 集成路径，不能由入口代码单独推出可信侧已完成全部授权检查。
- `gpu_protect.c` 含 FPGA MMIO 保护/恢复模拟与 TLB 操作；函数名 enable/disable 与注释容易混淆，应以实际写入 `CCAEXT_ROOT/CCAEXT_ALL` 判读。它们体现性能模拟，不是实际平台 GPC 验证。
- GPU `check_code_integrity()` 的 mismatch ERROR/panic 仍被注释并返回 0，且保留完整闭源 OpenCL code buffer 定位 TODO。`hmac_sha256()` 的 pad 未正确初始化、密钥复制注释、32 字节 hash 以 64 字节读取/复制的问题仍可静态看到。

上述完整性差异属于公开性能原型的具体代码证据，不等于已运行攻击，也不能直接宣布期刊所有内部实现或功能原型失效。修复后完整检查的开销不能自动沿用旧结果。FPGA 完整可信描述符重建、认证和清零路径尚未全部核验；补查部分平台 SMC 文件遇到 GitHub API 403，未将未取得材料写成已核验。无构建、无 FPGA/GPU 执行、无攻击复现。

## 11. 与相关论文及项目路线的比较

| 工作 | 主要关系 | 对本项目的迁移边界 |
| --- | --- | --- |
| StrongBox / CAGE NDSS | 可信 GPU 窗口、stub/real、从应用独占缩小到 GPU 任务独占 | 不能推出恶意并发共享已解决 |
| ACAI | CCA 下设备归属、地址映射与 CPU/设备一致性 | 继续绑定原始 Client、真实物理页和权限 |
| PORTAL | 可信设备服务与 Realm 管理，减少高权限 Monitor 职责 | 完整 Proxy 驱动是本项目已选 TCB 权衡 |
| MOLE | GPU MCU/固件信任基础 | 保留已接受的可信加载、运行状态与撤销条件 |
| PhantomMap | 实际 backing、页类别和映射生命周期 | 安装 PTE 之前验证，回收时使旧授权失效 |
| Devlore / Heckler / Sigy / WeSee | 中断路由、事件来源、handler 副作用与授权 | 区分架构，不把 x86 攻击冒充 CCA 已知漏洞 |

期刊 §8 也讨论将 GPT 等保护操作移到 Realm/RMM，降低 Monitor 权限和复杂度，并引用 PORTAL。因此本项目的可信 ProxyRealm 不必沿用 CAGE 把所有设备特定逻辑放在 EL3 的实现。可信服务仍要正确约束恶意 Client 的合法格式请求，不能由“服务可信”省略请求授权。

代码机密性在 CAGE §8 明确不属于核心保护目标；代码完整性仍需要。若本项目希望保护 Client 的 GPU 程序或模型结构，应另行声明安全目标，不把 CAGE 的数据保护自动扩展为所有代码也保密。

## 12. 独立判断与可验证的研究方向

CAGE 期刊版最明确的贡献是把“保护真实执行环境”推广到新的设备工作流，并展示独立内存会改变独占与回收边界。证据支持原型可行性和部分工作负载开销；尚不能支持任意恶意多 Client 并发、全面异常恢复或完整事件语义保证。

在用户既定假设和项目现有实现上，可继续围绕一个可信 job 记录建立不变量：原始 Client 实例、session、GPUVM/root、对象 backing generation、操作类型、权限、job cookie 与 device epoch 在提交和完成时一致；将成功/错误/取消、ACK、reset 和回收分别限定为被当前记录授权的转换。

研究性验证应包含：合法跨队列乱序完成、不同 Client 恰有相同本地 cookie、重复/迟到 IRQ、ACK 早于结果发布、reset 与撤销并发、旧 buffer ID/generation 复用、片上状态清理失败，以及攻击者控制其他设备流的访问。映射不可达、结果可消费与物理页可再次分配是不同结论，需要分别给出证据。

项目既有认证队列、GPUVM、私有快照、原生 fence 和 epoch 可以承载这些约束。是否已经完全满足，应依据当前代码逐路径核验；本文提出的是组合性质与后续验证范围，没有将文献推断宣称为当前代码漏洞或已完成设计。

未改运行代码，无新增性能测量。项目 glmark 前后均未测，分差及百分比不适用，无新增硬件 run-id 或硬件 PASS。
