# PORTAL、CAGE、ACAI 核心思想与本项目研究方向

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-15。基于三篇论文原文、当前固定代码及既有实验；本次未运行硬件测试。本文件为研究设计分析，不宣称候选机制已实现或已确认首创。

## 1. 阅读结论

三篇文章提供三种互补方法：CAGE 教我们把复杂 GPU 管理与少量安全操作分开；PORTAL 教我们按平台威胁模型选择保护方式并隔离管理服务；ACAI 教我们先定义必须保持的安全不变量，再设计跨 CPU/设备的授权链。

本项目最合适的研究问题是：**当物理 GPU 长期由可信服务持有时，怎样让多个 Client Realm 按对象和 GPU context 使用它，并在异步执行、服务崩溃和页重用期间保持授权一致性？**

这与单纯设备直通或整设备交接不同；但 Proxy、共享内存、批量提交、reset、capability 或可信 VM 本身都不是新概念。

## 2. 三篇论文的关键思想

| 论文 | 解决的问题 | 核心机制 | 可借鉴的方法 |
| --- | --- | --- | --- |
| CAGE，NDSS 2024 | 不信任 GPU 软件栈时如何执行 Realm 的 GPU 工作 | shadow task；Monitor 检查/切换；GPC 保护 GPU 环境 | 复用复杂管理，可信层只控制安全状态转换 |
| PORTAL，S&P 2025 | 集成 SoC 上安全 I/O 的复制、加密和设备管理成本 | 受保护明文区；System Realm 管 SMMU；动态设备交接 | 小型根信任层与可证明管理服务分工 |
| ACAI，USENIX Security 2024 | CPU Realm 与 PCIe 加速器 TEE 怎样安全组合 | 身份/独占归属/映射绑定不变量；可信 SMMU 更新；设备证明与链路保护 | 从攻击路径推导可执行的不变量 |

原文：[CAGE](https://www.ndss-symposium.org/wp-content/uploads/2024-763-paper.pdf)、[PORTAL](https://mainarke.github.io/assets/papers/sp25_sang.pdf)、[ACAI](https://www.usenix.org/system/files/usenixsecurity24-sridhara.pdf)。

### 2.1 CAGE：管理与数据访问不必属于同一个信任域

CAGE 复用不可信 GPU 栈准备影子任务，由可信 Monitor 在执行前验证并切换到真实任务，保护相关元数据、代码、MMIO 和内存视图，执行后恢复环境。CPU、GPU 和外设访问必须一起考虑；仅阻止 Host CPU 直接读页还不够。依据 CAGE §IV-B/C。

对本项目的启发是：先列出哪些操作真的需要可信，而不是将所有 GPU 管理代码直接塞进 RMM。当前 Proxy 的对象分配、策略统计可以与授权安装、特权映射、撤权确认分层。

但不能据此把现有 Proxy 直接称为 CAGE 式小 TCB：它仍控制真实 Panthor、GPU 页表与租户数据。若要移除其信任，必须控制特权指令、验证后修改和 GPU 页表/MMIO 写入，尤其适配 Mali-G610/CSF，不能把旧 GPU 的任务描述机制原样迁移。

### 2.2 PORTAL：保护明文的关键是访问控制闭合

PORTAL 在排除相应物理攻击的平台假设下，以严格隔离支持明文设备 I/O；System Realm 管理 SMMU，RMM/Monitor 协作保护访问。论文还讨论动态设备归属与运行时记录。依据 PORTAL §3.2、§4。

可借鉴的不是简单“不开加密”，而是先证明非参与者不存在 CPU、DMA、配置寄存器等访问旁路。普通 Host memfd 明文共享没有这种性质。

架构上，Proxy Realm 可负责复杂 GPU 服务，RMM 保持较小授权接口，Root/硬件保护不能绕过的配置。现有 eventfd 仍可作为不可信唤醒提示，但不能成为完成或身份的证明；即使通知可篡改，受保护请求本身也应拒绝伪造和重放。

System Realm、ring、动态归属和度量不是相对 PORTAL 的新贡献。可研究的是把整设备管理推进到持久 GPU 服务内部的对象授权，而不声称 PORTAL 原则上不能扩展。

### 2.3 ACAI：安全组合必须覆盖身份、配置和所有地址视图

ACAI §5.1 给出五项不变量：INVid 为证明后的不可伪造身份；INVown 为设备独占归属；INVbind 为 owner 与设备映射一致；INVhost 约束受保护页的 VM 映射；INVdev 约束设备映射重叠。设计还覆盖 PCIe 设备与链路信任，不能直接套用到 Mali。其原设计在 Realm 创建/销毁时 attach/detach。依据 ACAI §5–7。

最有用的是推理方式：不能分别证明 CPU 映射正确、GPU 映射正确就认为系统安全；它们必须指向同一授权对象，且变化过程不能出现攻击者可利用的 split view。

本项目的路径比 ACAI 的两侧映射更多：Client IPA、Proxy 窗口、Host backing、GPU VA、最终 HPA。必须证明它们在同一代次内代表同一授权范围；返回一个合法 HPA 不代表设备只会使用该 HPA。

特别需要区分：ACAI 的设备身份、独占控制和密钥/链路模型，不能用 FDT VMID、session_id、Group 或软件 generation 代替；也不应把 ACAI 简化为后续标准 TDISP 的一个实现。

## 3. 将三篇思想映射到现有代码

| 当前事实 | 能复用的基础 | 必须补上的机制 |
| --- | --- | --- |
| Proxy 按 channel 校验 owner_vmid | session 归属和句柄命名空间 | 将 channel 绑定到 RMM 确认的 Realm 实例 |
| manager 有 generation、grant、pin | 对象生命周期框架 | required_perms 检查、可信范围授权、硬件权限对应 |
| RMM 解析当前 Realm 的 IPA | 页归属验证入口 | 所有者显式授权给服务；不能随意解析他 Realm |
| GPU_REVOKE 只删 lease | 软件登记/清理入口 | GPU 停止、映射失效、缓存/TLB、回收确认 |
| pmthor reset 失败保留 PFN | fail-closed 思路 | 与 Realm 授权、服务实例和跨租户页重用联动 |
| Proxy session RR | 服务接纳控制点 | owner 级预算；不能冒充 GPU 时间公平 |
| Host memfd 和 eventfd | 普通虚拟化功能数据面 | 敏感页保护、端点认证、事件重放/丢失处理 |

代码入口：[Proxy](../../../../Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c)、[对象 manager](../../../../Linux-Guest-GPU/drivers/char/proxy_vmshm_manager/proxy_vmshm_manager.c)、[RMM](../../../../opencca/tf-rmm/runtime/rsi/opencca_gpu.c)、[Host pmthor](../../../../Linux-Host-GPU/drivers/pmthor/pmthor_drv.c)。具体检查见[前次源码分析](GPU_TRUSTED_BROKER_PORTAL_CAGE_ANALYSIS_20261015.md)。

## 4. 核心候选贡献：从独占归属到受控参与者集合

ACAI 的独占设备模型不能直接复制到多租户服务。一个可研究的转换是：**物理设备只有一个可信控制者；数据对象的访问者可以是显式授权的 Client、服务及其 GPU context 集合。**

建议为本项目定义以下不变量。它们是设计目标，不是现有实现证明。

| 项目不变量 | 内容 | 实际执行点 |
| --- | --- | --- |
| Control | 只有已确认服务实例可更改 GPU 特权状态、页表和授权配置 | 设备 MMIO/页表保护，可信控制器 |
| Authority | 只有数据 owner 能授权范围、权限、接收者和有效代次 | RMM 身份与归属检查 |
| View | 每个 GPU context 可达页集不超过其当前授权页集；所有地址转换指向同一对象 | 授权安装、GPU 页表、可用 DMA 控制 |
| Freshness | 旧 session、旧服务实例、旧设备 epoch 不能重新激活授权 | 受保护通道和引用检查 |
| Reuse | 页仍可能被旧 GPU 工作访问时不得交给非授权新 owner | 完成/终止、撤权屏障、回收控制 |

“可达页”还要考虑共享 firmware 与设备级执行，不能仅由 Group 或 shader core mask 推断。如果可信 GPU 控制和 firmware 假设不成立，应限制为串行安全模式，而不是宣称多 context 自然实现安全并行。

授权可表示为 `(owner instance, service instance, object, range, rights, context, epoch)`。RMM 维护权威状态，服务拿受保护引用；普通 generation 只能帮助识别陈旧对象，不能自行提供抗恶意 Host 的认证。

与 CAEC、Honeycomb 等已有方向的差异需要落在 GPU 对象/context 的实际授权执行与异步生命周期上，而不是泛称 protected sharing 或 small TCB。

## 5. 最有希望形成主贡献：异步撤权的可证明回收点

提出授权撤销的完成语义：撤销请求进入后拒绝新工作；只有旧工作已终止或排空、映射与必要 alias 失效、权限及缓存/TLB 更新完成，才返回“可以重用”。

```text
ACTIVE -> REVOKING -> DRAINING -> INVALIDATED -> RECLAIMABLE
                         |
                         +-- 无法确认停止 --> QUARANTINED
```

需要区别“撤销开始”和“撤销完成”。前者可以立刻阻止新提交，后者才允许不再授权的数据接收者取得页面。reset 失败保留页面，以内存占用换取不错误重用；设备级 reset 必须报告对所有租户的影响。

已有工作已涉及清理、解除绑定和设备状态转换，所以创新不能叫“首次考虑撤权”。应该证明新的细粒度协议能处理：一个租户部分对象撤销、其他租户仍运行、Proxy 崩溃、不同时间到达的 fence、reset 后旧引用重放，以及 owner 销毁和 GPU completion 的竞争。

本轮原生 unbind Oops 为该研究提供真实动机，但不证明发生了泄露，也不能据此认定其他论文缺乏故障处理。

## 6. 性能贡献必须与安全协议相连

当前小负载性能较差，适合研究“授权一次、重复使用”的提交路径：慢路径安装授权，热路径只引用仍有效对象；批量通知和提交减少切换，epoch 变化立即使缓存失效。

重要的问题是：缓存哪些验证结果仍然安全，如何处理并发撤权，批次部分失败怎样保持 fence 和错误语义。必须做安全与性能消融，不能仅说用了 batch 或 zero-copy。

本轮 Compute 时间比随规模从 14.206× 降至 1.404× 只能作为动机。它不能证明 Host broker 是瓶颈，更不能与论文安全开销作直接排名。测量需分开 Client 排队、通知、Proxy 接纳、Panthor submit、GPU/fence 完成及读回。

## 7. 哪些想法不宜单独称创新

- 将 Broker 放入 Realm：PORTAL 已有 System Realm。
- 用 shadow/stub 接口复用 GPU 栈：CAGE 等已有。
- 为设备增加 attestation 或建立可信 SMMU 更新：ACAI 等已有。
- 使用共享内存、ring、零拷贝、批量提交：通用机制，当前系统也已有部分实现。
- 用 Group/core mask 充当安全硬件分区：未得到本项目证据支持。
- 把软件 lease 表称为硬件 GPU grant：硬件不消费该表就没有访问强制效果。
- 单次功能 32/32、某个模型更快：测试结果不是安全证明或独立机制贡献。

## 8. 实验与论证计划

| 问题 | 对照与实验 | 输出证据 |
| --- | --- | --- |
| 授权是否真实执行 | 错身份、跨对象、越界、只读转写、描述符检查后篡改 | 拒绝点、实际 CPU/GPU/DMA fault 或受控错误 |
| 撤权后能否再访问 | 延迟 job、旧 PTE/doorbell、旧 epoch、页重新分配 | 撤权完成后无旧访问，失败时不错误回收 |
| 服务故障是否隔离 | Proxy kill、reset timeout、owner destroy 并发 | quarantine、其他租户影响和恢复条件 |
| 性能收益从何而来 | 原共享、可信中介、授权缓存、批量路径逐项消融 | p50/p95/p99、吞吐、CPU、grant/revoke 时延 |
| 是否可扩展 | 多 Client、多 session、短长混合、映射容量压力 | owner 级进展、尾延迟、内存和公平性 |

现有 RK3588/OpenCCA 无真实 GPC denial 证据；这块板适合功能和性能原型。安全拒绝应在真正执行相应访问检查的 FVP 模型或硬件上独立验证，且注明模型设备不等于实物 Mali firmware。

第一版建议明确信任 Proxy Realm 的相关软件栈与 GPU firmware；不可信服务的版本需要额外的验证与隔离机制，不能通过重新命名 TCB 得到。

## 9. 推荐论文叙事

研究问题：**传统独占设备绑定无法直接表达持久 GPU 服务中的租户级授权，软件对象关闭也无法说明异步设备访问已经结束。**

候选贡献组织为：

1. 面向服务中介的对象/context 授权模型和安全不变量。
2. 授权、GPU 工作与页重用一致的故障安全生命周期协议。
3. 在上述协议下可证明失效的授权缓存与快速提交，以及跨模型/实板的分离验证。

主线以第 2 项为中心，第 1 项提供模型，第 3 项证明实用性。下一步应先修复本项目权限和稳定性缺口，再做最小协议原型；候选新颖性仍需扩展检索和具体机制对比。

## 10. 文献与证据边界

论文中的性能数字来自不同硬件、负载、保护目标和基线：CAGE NDSS 2024 的平均 2.45%、PORTAL 的一次性 9.8%、ACAI GPU/FPGA 的 43.5%/12.1%不能放入同一列当作优劣排名。ACAI 的 FVP 实现也明确未完整建模设备证明、IDE key programming 和 MPE；设计依赖与实验实际覆盖必须区分。

本文件没有宣称论文未考虑任何撤销、错误或清理，也没有将所有候选能力归于原作者。第 4–9 节是本项目推导与建议。

- [PORTAL 原文](https://mainarke.github.io/assets/papers/sp25_sang.pdf)：§3–5。
- [CAGE NDSS 2024 原文](https://www.ndss-symposium.org/wp-content/uploads/2024-763-paper.pdf)：§IV–V。
- [ACAI USENIX Security 2024 原文](https://www.usenix.org/system/files/usenixsecurity24-sridhara.pdf)：§5–7、§9。
- [CAEC](https://caec-paper.github.io/)：受保护跨 CVM 共享已有相关工作。
- [Honeycomb](https://www.usenix.org/conference/osdi23/presentation/mai)：GPU 验证和缩小 TCB 已有相关工作。
- [本项目实现分析](GPU_TRUSTED_BROKER_PORTAL_CAGE_ANALYSIS_20261015.md)。
- [本项目完整实验报告](../history/GPU_COMPREHENSIVE_EXPERIMENT_REPORT_20261015.md)。
