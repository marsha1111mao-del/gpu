# GEVisor：CPU enclave 辅助的 GPU TEE、异步调用与形式化边界深读

研读日期：<date start="2026-10-27" />。原清单编号：**TGS-050**。状态：核心全文、评估及固定提交中选定安全路径已研读；未构建或运行。未改运行代码，无新增性能测量。

## 1. 书目信息与全文

**Building GPU TEEs using CPU Secure Enclaves with GEVisor**，Xiaolong Wu、Dave (Jing) Tian、Chung Hwan Kim，ACM SoCC 2023，249–264。DOI：[10.1145/3620678.3624659](https://doi.org/10.1145/3620678.3624659)。[作者论文页](https://www.s3lab.io/paper/gevisor-socc23)，[作者 PDF](https://www.s3lab.io/download?uid=203)，[公开仓库](https://github.com/purseclab/GEVisor)。

本次 PDF SHA256 为 `57d3a3ea190d6e4b30f4b6bcf9758c1443f37aecfd01ab41c99b7f35edd9b0c3`。源码固定于 `f163235d2681ae28137b9b1c21a26a2ed97ef77a`；本次查询 main 指向该提交。完整 Git tree 未截断。正文 §9 指定 GTX TITAN Black，而摘要称 Pascal GPU，二者不一致；平台分析以具体实验配置为准。

## 2. 研究问题与定位

SGX enclave 保护 CPU 中的应用，但 GPU runtime 需要通过 enclave 外的 MMIO、主存 DMA buffer 和设备上下文访问 GPU；这些对象可能被恶意 OS 或驱动窥探、改写和重映射。GEVisor 用可信 VMX-root monitor 配合 enclave runtime，保护这些外部对象，目标是在不修改 CPU/GPU 硬件的条件下建立 GPU TEE。

与 Graviton 的 GPU 硬件扩展、HIX 的 CPU/I/O 扩展相比，它把参考监控器放在可信虚拟化层；与本项目相比，其 GPU 驱动不可信、enclave runtime 可信，而本项目明确将完整驱动和服务放入可信 ProxyRealm。两者的 TCB 划分不同，不能只比较“新增 monitor 行数”。

## 3. 威胁模型、TCB 与排除项

攻击者可控制 OS、GPU 驱动、guest VM 和普通云 hypervisor，并尝试读写 I/O 缓冲、注入命令、创建别名 GPU 上下文。可信基础包括 CPU/GPU、CPU microcode、GPU firmware、Intel TXT、TPM、系统固件（ME、UEFI、SMM）及 GEVisor / enclave runtime。

论文信任 GPU 设备内存，理由包括封装中访问的难度；排除物理攻击、DoS、SGX/GPU 侧信道。这个信任并不等同于设备显存已具备完整的加密与完整性验证。论文讨论合作云运营方部署服务，但安全模型仍允许其普通系统软件被控制。

“不信任普通 hypervisor”与“信任 GEVisor”并不矛盾：后者另经受信启动取得 VMX-root 控制。若没有可信启动与排他的控制权，仅在普通 OS 中加载一个模块不足以建立这一信任边界。

## 4. 三类保护对象

**DMA buffer** 是主存中 CPU 与 GPU 交换数据的区域；**MMIO** 是提交和控制路径；**GPU context** 包括上下文关联的内存与映射。论文分别维护 MRtable（I/O 区域）和 OM（ownership metadata），把 enclave ID、context ID、VA、PA 和长度关联起来。

软件页表遍历用于得到实际 PA，但“软件遍历”本身不自动证明 OS 提供的映射合法。安全还依赖遍历时映射稳定、物理页不属于其他对象、最终访问路径受保护、之后不能重映射绕过。对本项目应按 ACAI / PhantomMap 的实际归属和生命周期要求独立检查，而不把“算出 HPA”当成授权完成。

## 5. GEVisor 的隔离及 measured launch

启动链为 CPU→SINIT ACM→TBoot/MLE→GEVisor，使用 TXT 与 TPM 测量并建立信任。运行时建立接近一一映射的基础 EPT，只对 enclave、GPU MMIO/DMA 和通信区等敏感子集额外保护，以降低普通访问开销。

Monitor 为需要保护的 enclave 核配置相应访问权；其他并发 CPU 核不能读取敏感缓冲。enclave 因 OCALL、AEX 或终止停止执行时，权限必须及时撤销，避免随后的非 enclave 软件沿同一核继承访问权。这是“执行状态变化触发授权变化”，不是只在程序创建时检查一次。

论文另用 IOMMU 阻止其他恶意外设 DMA 重叠，监控 PCI 配置与 BAR。EPT 是 CPU 访问边界，不能单独限制所有外设 DMA；代码是否启用这些保护还需单独检查。

## 6. 异步 hypercall 及通信区

同步调用原本需要 enclave 退出、VM exit、VM entry 和 enclave 恢复。GEVisor 将小参数调用写入受保护通信区，以 cache-line 大小的条目保存 hypercall ID、状态、参数个数与负载，批量交给专用 I/O 核处理；IPI 唤醒远端处理器，批次处理后从 busy 变为 free。

此处异步化针对无需返回值的监控请求，不能据此让授权尚未完成的 GPU 任务先执行。批处理必须保持安全配置先于敏感访问的依赖关系。论文环形队列的无竞争说明依赖单线程请求/执行和循环递增顺序，不是任意多生产者队列的并发正确性证明。

通信区位于 enclave 外，由 GEVisor 通过 EPT 保护。仅 CR3 无法区分 enclave 与其同进程 host，因此设计跟踪 enclave 执行状态。§8 又明确 ENCLU 不能像 ENCLS 那样直接 trap，原型通过 runtime 插桩及执行页保护等路径协助观察；应区分高层描述的逻辑事件和实际拦截机制。

## 7. 远程证明

linear remote attestation 把 SGX enclave 与 TPM 测量的 hypervisor 关联，使用 TPM AIK 对 enclave 证明相关密钥建立证书链，向验证方说明两部分位于相应可信平台环境。测量身份、密钥关系、平台控制权是这一设计的核心。

启动/平台证明不自动证明每个 GPU job 的结果正确，也不提供每个完成事件的防重放语义。项目若增加证明，应区分 Proxy 镜像、RMM/固件、设备状态和本次任务会话绑定，而不是把一份启动证明当作永久任务授权。

## 8. GPU 上下文与多用户支持

论文利用统一地址空间与对应主存页的关联，由 OM 管理 context / enclave 对象；多 enclave 分配各自通信区与 MRtable，每个 enclave 可拥有多个 GPU context。GPU 通过上下文切换执行，而不是证明所有 enclave 的 kernel 同时在硬件上并行运行。

§9 的两个 enclave 实验支持性能层面的共享证据，但没有等同于对所有恶意并发交错、退出、reset、对象快速复用的全面攻击验证。当前公开源码中可见的单 enclave 假设见下文，不能把论文的共享设计直接当作可复现实现结论。

## 9. 形式化验证究竟证明什么

论文构造异构 HPL 内存模型，抽象 CPU DMA buffer、共享内存、GPU global memory、fence 和 sync；用 Dafny/Z3 验证 MRtable / OM 不变量和 handler 前后的 confidentiality、integrity、context isolation 非干扰关系。

证明聚焦 GPU I/O 开始和结束的状态，而非完整任意执行轨迹；页表遍历没有完整建模实际虚拟内存状态转移，而以有效地址简化。实现层通过 self-composition 将两次执行关系转成断言，用 CBMC 检查有界路径；不能由 CBMC 自动处理的遍历循环另做人工审计。

因此可以称其为针对所建模型与选定实现路径的形式化工作，不能称整个 GPU 软件/硬件栈、地址翻译、固件、时序泄漏、任务通知和撤销过程全部获得端到端证明。本轮未取得并运行相应证明脚本，论文报告的验证与独立复核分开记录。

## 10. 实验平台与对照

Intel i7-8700K、六核、4.7GHz、32GB RAM、SGX SDK 2.0、TPM 1.2、GTX TITAN Black（2880 CUDA 核、6GB GDDR5），Ubuntu 18.04.4 / Linux 4.15。实现基于 Bareflank 与 Gdev；Darknet 使用 128MB EPC。

主要对照有未保护 Gdev、enclave runtime 但无 GEVisor 的 Enclave-GPU，以及 4KB EPT、2MB EPT 和使用 3MB DMA buffer 的 Async。论文对 Gdev 的表述存在位置差异，不能据“所有系统运行 enclave”的一句概括抹去其未保护基线；百分比应按对应段落指定的 Enclave-GPU 对照理解。与其他论文的表格比较来自各自论文，不是同平台直接复现。

## 11. 关键结果与量化口径

| 测量 | 原文结果 | 可用于什么结论 |
| --- | --- | --- |
| Rodinia 九项 | Async 相对 Enclave-GPU 平均约 18% 开销 | GPU I/O 保护增量；不是相对所有原生栈的统一损失 |
| Darknet 九模型 | 相对 Enclave-GPU 平均约 13.1% 开销 | 特定平台/模型，不可直接对比本项目 glmark |
| 两 enclave 并行 | 相对并行未保护 Gdev 报告约 52% 性能退化 | 多用户上下文保护有明显成本，不能只引用单 enclave 数字 |
| 4MB HtoD | 5→10ms | 这一路径时间翻倍，但不是整体应用开销翻倍 |
| 4MB DtoH | 30→60ms | 作者将其与设备页监控联系 |
| kernel execute | 301→301ms | 此微测未观测计算阶段增量，不代表全生命周期零开销 |
| Init | 171→180ms | 包括初始化路径变化 |
| 异步批处理交点 | 同核约 10 条，跨核约 23 条开始优于同步 | 小消息量未必受益，需考虑 IPI 与批次等待 |
| SGX / TPM Quote | 10.99 / 197.34ms | 各步骤的微测平均，不能当作完整任务证明成本 |

小 kernel 不能充分摊销跨核通知成本，作者也观察到退化；专用 I/O 核占用的资源机会成本应与执行时间一并考虑。3.8K LoC 是 GEVisor 新增实现规模，不包含所有固件、库、enclave runtime 与硬件可信基础。

## 12. 公开代码的实际范围

固定提交完整树和构建文件表明，安装脚本把 Bareflank、extended APIs 与 gevisor extension 结合，`gevisor/vmm/CMakeLists.txt` 将 `vcpu_factory_hook.cpp` 作为目标源码，并设置 `-O0`。本轮只读取相关脚本，没有执行安装、卸载或依赖下载。

在该核心文件可确认：全局 `current_enclave_cr3`、`enclave_vcpuid`、`channel_paddr`，以及明确注释 `assuming only one enclave at a time.`；统一的 GPU buffer 数组；外部中断时读取通信区和重设 enclave 执行页保护；通信按 `e/m/n/i/d` 等字符分支处理。这些材料不足以复现论文所述每 enclave MRtable / OM 和完整异步 ring 的多用户设计。

已读 EPT 读写 handler 可见直接开启对应权限的测试性路径，不能将其宣称为已核对的完整 enclave ID / VA / PA 参考监控器。PCI I/O handler 注册位于禁用分支，虽有 PCI 配置查询，也不能据此声称论文所有 BAR 防护在该构建中启用。上述是源码与论文的对应范围记录，尚未构建、复现绕过或证明漏洞可利用性。

另外读取 `paging_utils.h` 的 CR3 软件遍历、`encls_utils.h` 的叶操作封装、`lapic_utils.h` 及开发笔记。完整树中没有找到以 Dafny/CBMC 命名的对应证明目录或 `.dfy` 文件；这不排除作者另行发布材料。不能因为仓库有常规 Bareflank 测试就称论文形式化证据已独立复现。

## 13. 对本项目的具体启示

第一，保留完整可信 Proxy 驱动是合理的 TCB 选择，但应说明额外信任换来的职责：最终 HPA 映射授权、GPUVM 归属、真实 fence 关联、可信固件和 MMIO 控制。不要为追求较小新增行数，把实际依赖移出统计后宣称同等保护。

第二，身份、地址及状态必须一起检查。RMM 认证原始 Client；Proxy 依据私有会话和对象状态解析请求；映射建立和实际生命周期保持一致。当前基线已记录共享描述符私有快照及对象校验，下一步应核对尚未覆盖的竞态，而非重新增加一个可自填 Client ID。

第三，异步通知可以与安全结合，但 IPI/IRQ 只负责唤醒；完成记录须来自可信提交关联的真实 fence，包含足以排除旧任务/旧会话命中的身份与代次。GEVisor 的 busy/free 表示监控调用槽是否可用，不是 GPU job 成功完成的证明。

第四，验证范围要精确。可先针对“请求快照→授权→原生提交→终态→通知→撤销→复用”建立小型状态机，明确不变量和错误/reset 分支；不能把状态机或有界检查的成功扩写为全部驱动获得形式化安全证明。

## 14. 后续可验证问题

构造 AEX/退出类比路径：Client VM 退出后旧完成抵达、Proxy worker 与撤销并发、同物理页和句柄快速复用、重复/合并/延迟唤醒、一个 Client 的任务错误影响另一个 Client。分别检查地址访问权限、完成对象匹配、错误传播和资源回收，不能仅以 IRQ 数量正确判断任务语义正确。

性能方面比较短任务与长任务、单 Client 与多 Client、批量与同步通知，报告专用 CPU 资源、队列等待和尾延迟。相较 PORTAL / CAGE / ACAI，本论文补充了执行状态与权限联动、异步控制开销和证明边界；设备 IRQ 的来源保护仍应结合 Devlore 等资料独立分析。
