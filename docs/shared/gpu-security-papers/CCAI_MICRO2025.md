# ccAI：PCIe 事务保护、完整可信驱动与单租户边界

研读日期：2026-10-27。依据 14 页作者原文、作者项目资料及公开实现线索核查。本篇聚焦保护接口、任务生命周期、可信基和 LLM 评估，不以论文摘要的兼容性概括替代安全论证。

## 1. 书目信息与来源

| 项目 | 内容 |
| --- | --- |
| 标题 | ccAI: A Compatible and Confidential System for AI Computing |
| 作者 | Chenxu Wang、Danqing Tang、Changxu Ci、Junjie Huang、Yankai Xu、Fengwei Zhang、Jiannong Cao、Jie Song、Shoumeng Yan、Tao Wei、Zhengyu He |
| 会议 | MICRO 2025，2025-10-18 至 10-22，Seoul |
| DOI | [10.1145/3725843.3756104](https://doi.org/10.1145/3725843.3756104) |
| 原文 | [作者 PDF](https://compass.sustech.edu.cn/paper/ccai-micro25.pdf) |
| PDF SHA256 | `6b2952a4c04e499371cf27074178238a5bffb4a702ecb56e983fe42f2b6b622f` |
| 项目入口 | [COMPASS ccAI](https://compass.sustech.edu.cn/ccai/) |
| 研读范围 | 正文 §§1–10、全部评估图表；公开代码线索核查，没有执行实现 |

原文没有可据以完成源码审计的仓库链接；本轮 GitHub 定向检索未发现可确认的公开实现。不能据此断言作者从未发布过代码。本篇保留实现不可独立核验的边界。

## 2. 背景：旧 xPU 与软件兼容性

云端 GPU/NPU 缺少原生机密计算能力时，把应用放入 CPU TVM 仍不能保护普通 PCIe 传输或设备端状态。改变每种设备的驱动、runtime、固件和硬件代价高，TDISP/IDE 等路线也有平台要求。

ccAI 将公共 PCIe 事务作为安全执行点，用额外 Security Controller 保护传输和设备访问，TVM 内使用适配层协作，保留应用和原生驱动接口。这是跨设备兼容的设计取舍：不修改 CPU/xPU 内部逻辑，不代表没有增加可信硬件。

## 3. 威胁模型与 TCB

攻击者控制 Host OS、hypervisor、外围驱动及其他不授权 TVM/设备，可以监听、篡改外部 PCIe，也可尝试物理破坏控制器和连接。可信基包括 CPU TVM 隔离、TVM 内完整应用/驱动/runtime/Adaptor、PCIe-SC、HRoT-Blade、可信 xPU 硬件和无恶意代码的设备固件。

控制器到 xPU 的内部 PCIe 与设备被封装在受监测机箱中；外部链路不可信，内部链路依靠该物理边界。因此它不是把明文送过任意不可信内部链路也能安全的方案。设备厂商真实性、固件签名与可信加载是前提，MOLE 类风险不能只靠外部数据加密消除。

侧信道和 DoS 被排除。TVM 自己的模型框架及作业可信，设备内恶意多租户执行并非其已验证核心模型。

## 4. 架构与数据流

```text
远端用户 ←证明/密钥→ TVM
TVM：应用 + 原生驱动/runtime + Adaptor + trust modules
                  ↓ 不可信外部 PCIe：密文/认证控制事务
PCIe-SC：Packet Filter + Packet Handlers + HRoT-Blade
                  ↓ 受信物理边界内的明文 PCIe
                 xPU
```

Adaptor 查询任务传输元数据，从 TVM 私有数据准备加密 bounce buffer；控制器验证事务、解密 payload，再传给设备。设备结果反向加密传回 TVM。CPU TVM 的原生保护负责 Host 内存隔离，其他恶意设备的 DMA 仍依赖既有 IOMMU 设置；PCIe-SC 不是 CPU 内存隔离的全部替代品。

这条路径与本项目可信完整 GPU 服务栈有可比性，但 PCIe-SC 面向设备边界；本项目需要在服务内部继续保留原始 Client 权限，不能把“来自可信 Proxy”视为所有请求都合法。

## 5. Packet Filter：身份、类型和地址共同决定权限

L1/L2 两级规则按 Format/Type、Requester、Completer、地址空间等字段分类。L1 过滤未授权请求，L2 选择具体保护操作；Mask 指定检查哪些字段。规则动态更新经 Adaptor 和专用配置空间传送，论文要求保护策略本身。

| 操作 | 论文定义 | 适用内容 |
| --- | --- | --- |
| A1 | Prohibited：拒绝 | 未授权或不匹配的请求 |
| A2 | Write-Read Protected：加解密和完整性 | 秘密数据、模型参数、结果 |
| A3 | Write Protected：完整性及安全验证 | 部分代码、命令、MMIO 控制值 |
| A4 | Full Accessible：直接传输 | 一般中断请求、部分非秘密状态读取 |

通用 packet 格式可解析不等于所有设备特定语义自动安全。例如一个 MMIO 值是否合法，仍要知道具体寄存器、root 和运行状态。厂商新增 message 也需要相应策略。论文兼容性是公共接口兼容，不能推导无需任何设备知识的安全证明。

## 6. Packet Handler：认证、重放与运行环境清理

控制面管理加密参数和 authentication tag，将 tag 与对应任务事务配对；硬件完成 AES-GCM-SHA 等处理。原型描述 IV 为 12-byte nonce 与 4-byte counter，tag 16 字节，并在 IV 耗尽前换钥，终止后销毁密钥。

原文安全分析还提出检查 packet 顺序来检测重放、重排和删除。强安全实现仍需明确 nonce/domain 唯一性、计数器生命周期、tag 与任务/方向/地址的认证绑定以及复位后的旧包处理。单凭“IV 随机”不应独立推导全部新鲜性保证。本轮无源码可核这些编码细节，未据此声称存在密码攻击。

Environment guard 在任务结束时清理设备环境：可触发 cold boot reset，或对支持的软件接口发送 cache/TLB reset 等命令。清理范围和是否停止所有 DMA 依赖设备。reset 命令发出、完成确认、输出可见性和物理页回收必须区别，论文没有给出本项目多 Client 共享下的逐对象回收协议。

## 7. 中断边界：A4 不构成可信作业完成证明

§4 将 interrupt requests 明确归为 A4；部分 interrupt status 读取也直接传输。可以确认作者没有在本文给出 Devlore 那种受保护物理事件记录、vGIC 注入顺序与 ACK 协议；不能进一步推导“所有 IRQ 任意伪造”，因为 L1/L2 来源和路由约束仍可能适用。

更重要的是，即便一条 IRQ 确实来自设备，它也不直接回答哪个 Client 的哪个 job 成功、是否有 fault、输出是否已可见、何时可以撤销映射。项目应把物理 IRQ、可信 job 状态和逻辑通知分层，而非把传输完整性当成语义完整性。

## 8. 可信启动、证明与物理封装

HRoT-Blade 对 bitstream/firmware 建立启动测量并记录 PCR；CPU TVM 和控制器分别提供信任证据。远端 challenge 包含 nonce、选择的 PCR 和设备 KeyID，验证签名及期望测量。设备若有自身 HRoT 可协作证明；没有时，论文讨论软件证明或厂商外部接口。

这些路径的安全强度不同，不能把缺乏硬件信任根的旧设备自动等同于原生可证明设备。软件证明的时序/平台前提需另看 SAGE 等工作。封装传感器把物理状态纳入 PCR，可提供检测证据，却不应被扩写成覆盖所有物理探测或具备未报告的即时擦除保证。

## 9. 原型与总可信基

CPU 端为 96 核 Intel server、256GB RAM、Ubuntu 22.04；NVIDIA 路径使用 CUDA 12.1、550.90.07 驱动。控制器实现在 Intel Agilex 7 SoC FPGA。

软件新增 3.1k LoC，包括 Adaptor 2.1k、trust modules 1k；硬件消耗 218.6k ALUT、195.7k registers、630 BRAM。HRoT-Blade 使用 Cortex-A53 HPS，不增加该表列出的 FPGA 逻辑资源，并不代表其固件没有信任成本。

论文使用 TVM 作为安全抽象，所列实验环境本身不能独立证明所有 CPU 隔离和物理保护性质均在该性能原型中完整落实。完整 driver/runtime 和 TVM OS 都在可信计算基，不能只报告 3.1k 行。

## 10. 评估方法与数值审查

核心实验在 A100 上运行 Llama-2-7B-Chat。固定 batch=1 扫 token=64–2048；固定 token=128 扫 batch=1–96，报告 E2E、TPS、TTFT。对照为同设备 vanilla；ShareGPT/Hellaswag 输入有修改。

| 证据 | 原文数值 | 阅读限制 |
| --- | --- | --- |
| Figure 8 E2E | +0.05% 至 +5.67% | 适用于该模型及配置，不是全部指标严格上界 |
| Figure 8(e) TTFT | 包含 +6.13% | 超过正文概括的 5.67%，引用时必须披露 |
| Figure 9 多 LLM | 图中含 +0.02%，最大 +4.76% | 正文写 0.72%–4.76%，遗漏图中较小值；不按概括重写图 |
| Figure 10 多 xPU | 图中 S60 +0.34%；其他如 A100 +0.58%、T4 +2.40% | 正文写 0.58%–2.40%，与图中最小值不完全一致 |
| Figure 11 优化消融 | 图中延迟降低约 87.03%–89.66% | 正文另有 88.7%–89.8% 概括；不当作对 vanilla 的收益 |
| Figure 12 限带宽 | E2E +0.68%、+4.55%、+4.45% | 不能称降低带宽后增量没有变化 |
| KV cache swap | 相对同场景 vanilla 增量低于 2% | 不等于 swapping 本身无代价 |

多设备实验部分换用 OPT-1.3B，不能把设备间绝对耗时用于相同工作负载排名。论文设备清单还写有“RTX4090Ti”，本轮没有取得足够独立硬件证据确认这一型号，保留原文命名疑点，不悄悄改成已核实型号。

与 H100 的性能比较来自外部研究和不同实验条件，不能据此认定 ccAI 在相同负载下普遍优于 H100。论文未提供可独立重算全部结果的公开原始样本，本轮也未复现。

## 11. 关键限制：原型是一个控制器服务一个 TVM 的一个 xPU

§9 明确写：当前每个 PCIe-SC 服务一个 xPU，由一个 TVM 拥有。多个 xPU、多用户/MIG 场景为未来扩展，设想用独立安全通道和 PCIe 标识区分。

这比从表中“supports multi-type xPU”推断“支持安全多租户共享”精确得多。multi-type 指跨不同设备的兼容性，不等于同一设备上多个恶意 Client 的隔离。尤其在项目中，所有 Client 经同一个可信 Proxy 使用同一物理设备，PCIe BDF 不能直接区分原始 Client；需要服务内 job/GPUVM/对象授权。

## 12. 公开实现与可复现程度

已取得原文和作者项目页，未发现可确认的 RTL、Adaptor 源码、固定 build manifest、规则库或完整实验脚本。定向 GitHub 搜索无结果只是本次检索证据，不作为“不存在”的证明。

因此原文可支持架构、规则分类和实验配置分析，不能据其认定源码中 nonce、packet matcher、权限更新和错误恢复均已审计。完整复现还需 FPGA IP/bitstream、适配层、设备策略、固件和信任建立输入；本篇没有构建或硬件实验。

## 13. 与项目及其他论文的关系

与 HIX/HETEE 一样，ccAI 把复杂原生驱动置于可信环境；它通过公共 PCIe packet 降低设备适配成本。与 Graviton 的可信设备内 command processor、CAGE 的小可信监控逻辑、PORTAL 的可信服务 Realm 相比，信任执行点和兼容性代价不同。

本项目应继承“复杂策略与最终安全执行点分离”的思路：Client 提供请求，Proxy 以 RMM 认证身份解释；映射检查最终 HPA 和 backing；可信完成再选择正确通知对象。对集成 Arm GPU，不必为了对齐 ccAI 增加 FPGA 或传输加密；平台假设已覆盖的保护无需重复实现。

## 14. 可研究的增量与验证计划

将规则从“设备接口是否允许访问”扩展为“当前 Client、对象、job 和代际是否允许该状态转移”。保护规则更新时，明确何时对在途作业生效；reset 推进 device epoch，旧通知和旧映射失效；终止后清钥不能替代确认设备停止和清理缓存。

负例可包括伪 owner、旧 job completion、跨会话请求、规则更新与提交竞争、reset 后迟到 IRQ、合并通知、页面重新授权前残留 DMA。分别测策略检查、映射、真实完成确认、跨 Realm 通知和撤销延迟；不将 LLM 的小百分比外推到完整 720p glmark。

本篇未改运行代码，无新增性能测量；无硬件 run-id、无新增硬件 PASS。论文分析已写成，代码取得与复现范围仍按上述事实保留。
