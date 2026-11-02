# MyTEE：受控驱动权限提升、DMA 描述符快照与可信 I/O 边界

研读日期：2026-10-27。依据 15 页 NDSS 原文和固定作者仓库的定向静态核验。本篇将其列为可信 I/O 支撑工作，涉及 GPU mailbox/framebuffer，但不将其当作完整可编程 GPU 计算 TEE。

## 1. 书目信息和固定来源

| 项目 | 内容 |
| --- | --- |
| 正式标题 | MyTEE: Own the Trusted Execution Environment on Embedded Devices |
| 作者 | Seungkyun Han、Jinsoo Jang |
| 会议 | NDSS 2023 |
| DOI | [10.14722/ndss.2023.23041](https://doi.org/10.14722/ndss.2023.23041) |
| 原文 | [NDSS PDF](https://www.ndss-symposium.org/wp-content/uploads/2023-41-paper.pdf) |
| PDF SHA256 | `fff112124321a00319700c81bf6818ccb97e6ac2260af10d7187b14c5a017e70` |
| 仓库 | [sssecret2019/mytee](https://github.com/sssecret2019/mytee) |
| 固定提交 | `707c64d602f47eb5e37b432197cda6fb5e05f197` |
| 阅读范围 | 正文 §§I–XI；重点 §§IV–IX、XI；代码只作下述路径核验 |

原文首页、实现章节和仓库 README 对 Linux 版本的表述不同：分别出现 4.15、4.14、README 的 4.2.1。本轮不将其合并为一个已确认版本。需要复现时，应以固定输入、实际源码和构建 release 为准。

## 2. 问题和研究价值

MyTEE 面对缺少完整 TrustZone 内存/外设控制器的嵌入式设备：CPU 有安全状态与虚拟化能力，但没有可直接依赖的 TZASC/TZPC/IOMMU。只装 OP-TEE 不能隔离其内存，普通 OS 和被错误编程的 DMA 仍能读取或修改秘密。

作者试图通过页表约束、关键指令控制及 DMA 控制面仲裁，重建 TEE 所需保护；再给现有驱动植入有限 API，完成安全 I/O。其价值在于把“复杂驱动仍在不可信 OS”和“只有受限访问能碰到秘密”组合，而不是简单搬入全部驱动。

用户已假设目标平台保护真实页表、MMIO 和实际 HPA，本项目无需复制其硬件补偿方案。本文关注可迁移的描述符快照、权限提升边界、事务验证和完成状态。

## 3. 威胁模型与信任基础

攻击者可控制运行中的 REE OS，滥用驱动接口、修改 DMA 描述符和控制流。可信启动保证初始 firmware、bootloader、内核图像完整；CPU 安全状态与虚拟化可信，设备和外设硬件非恶意且物理隔离。物理篡改、冷启动和侧信道被排除。

可信基包含 monitor、受约束 hypervisor、完整性监控和与服务有关的受保护驱动块/TA 逻辑。论文虽讨论驱动块漏洞后仍保护 TEE 的设计，但不能因此把所有受提升代码、日志和地址校验器都视为无须信任的普通输入。

其 DMA 防护假设由 OS 编程的已知控制器行为，不覆盖恶意硬件自行构造任意总线访问。这个边界对解释“DMA filter”尤其重要。

## 4. 架构：两层访问限制与更高层锚点

REE kernel 与 hypervisor 共享页表，使临时提升的驱动代码仍使用原内核 VA；kernel 实际权限还受 Stage-2 约束。TEE 与 hypervisor 秘密区从普通 kernel Stage-2 视图移除，关键代码只读。

共享页表本身也设为只读，更新陷入安全 monitor，由其验证新 PTE 不映射受保护物理对象。系统寄存器的敏感改写用 SMC 仲裁；初始化后不应再使用的 hypervisor 关键指令被移除，以限制提升代码滥用 HTTBR/VTTBR 等能力。

这种组合意在避免“有 hypervisor 权限就能换掉全部页表”的绕过。它仍依赖可执行指令面、映射和仲裁完整，不能单凭页表只读推导任意 privileged exploit 无害。

## 5. DMA filter：校验实际描述符而非只看地址句柄

对外置 DMA controller，MyTEE 封锁 MMIO。OS 写入 control block 地址时触发 Stage-2 fault；可信层遍历 `NEXT_CB` 链，把 CB 复制到安全内存，校验预期的源/目标访问范围，再将**安全副本地址**交给设备。

这一步很关键：只验证 OS 可继续改写的原 CB 会出现检查与使用之间的竞争。可信快照使设备消费的内容与检查内容相同。

CB 校验不是简单判断起始地址。二维传输包含 XLENGTH、YLENGTH、signed stride、source/destination increment 和 width；可信层必须覆盖每次实际可能访问的范围。内核文本、hypervisor、TEE 等不可被任意 DMA 访问；安全缓冲区的使用还要符合安全事务。

对 USB 内置 DMA，地址和长度直接写寄存器，无需 CB 链复制；MyTEE 陷入并校验这些控制写，替换为安全缓冲区。两者都是**控制面提交时的仲裁**，不等于监控任意 GPU 执行指令产生的每一次 DMA。

对本项目，原始 Client 的 handle/offset 不应成为最终授权依据，应从可信对象记录解析 backing/HPA，并确保 GPU 使用的真实控制数据不能在验证后被替换。CB 无环、有界长度、整数溢出和地址别名等仍属于实现必须检查的问题，本轮未对全部 filter 源码完成证明。

## 6. 临时权限提升与 I/O API

API 包括 `mytee_shield_mmio`、`mytee_priv_up/down`、`mytee_verify_memopr` 和 `mytee_log_txn`。需要访问安全对象的驱动块临时在 hypervisor 权限执行；进入时使用安全栈并禁用中断，退出恢复普通 kernel。

地址、长度及间接引用数据在校验前放入安全上下文，限制 TOCTOU；`verify_memopr` 按设备/操作上下文限定 MMIO 与缓冲区范围；日志记录保护建立、配置及事务数据。LR/静态内核文本检查用于限制动态模块直接调用敏感提升入口。

这不是“已认证调用者可以随便访问寄存器”。权限范围和使用方式都要验证，与 BarriCCAde 摘要提出的接口语义约束互补。动态模块和被提升代码合谋的问题，作者仍留下额外可执行映射收缩作为未来加固。

## 7. 事务日志验证：消费前确认结果属于预期请求

TA 不仅接收返回值，还核对 MMIO/缓冲区是否在事务期间受保护、发出的内容是否匹配原请求。TPM 示例有私有 transaction flag：完成后阻止新请求覆盖响应，TA 消费后才清除。

这体现请求、完成和消费的关联。检测日志异常后拒绝消费结果，与防止所有操作事先发生是不同保证；对有不可逆副作用的设备，必须另外约束启动前授权，不能假设事后日志总能撤销已经发生的操作。

对项目的启发不是在每条 RPC 上增加日志，而是明确权威 job 状态和消费边界。旧通知不能覆盖新 job，错误结果不能因收到唤醒而被标为成功，Client ACK 也不能单独授权页面复用。

## 8. 三个应用及 GPU 相关范围

**TPM：** 通过 SPI 传递 TA 命令，受限驱动块访问安全 MMIO，响应写安全内存，TA 校验日志再消费。测试设备为 Infineon SLB9670 TPM 2.0。

**USB keyboard：** 可信标志配合 NUM Lock LED 表示安全输入状态；监控 USB 控制消息和设备地址变化，替换 DMA 目标为安全 buffer，受限驱动块转换 scan code。键盘 IRQ **仍由 REE OS/驱动处理**，TA 后续消费累积输入。它不构成 CCA 物理 IRQ 来源认证或 vGIC 注入保护协议。

**Framebuffer：** 保护 GPU mailbox/display 配置，检查实际 framebuffer 地址和大小，并支持 mmap/write 路径。它防止不可信 OS 改写显示缓冲或配置；没有覆盖通用 shader/kernel、GPUVM 并发和恶意计算任务。因此 SoK 或比较表把它放在 GPU 类目时，需要解释这个较窄含义。

## 9. 原型与一般设计的关键差异

原文 §V 讨论用 watchpoint 阻止已获 hypervisor 写能力的代码改写 DMA controller；但 §VII-C 明确说明：**32 位原型未实现 watchpoint 保护**，原因是对应架构模式不支持所需配置。§VIII 的一般安全讨论仍援引该机制，引用时必须区分设计论证与原型覆盖。

§XI-B 说明原型 kernel/hypervisor 为 32 位，用 long-descriptor/LPAE 实现共享页表；64 位适配的 VA 范围约束另行讨论。README 又说明部分示例 TA 为简化实现采用 PTA，不能从论文概念图推断所有业务逻辑都在低特权用户 TA。

这些差异不因硬件是实验载体就可以忽略：应在目标假设下讨论方案成立条件，同时诚实报告原型验证了哪一部分。它们本身也不是本轮已复现的利用链。

## 10. TCB 与实现规模

Table III 列 monitor 517 C +1492 ASM、hypervisor 1552 ASM、kernel 673 C。安全 I/O 还有 TPM 驱动/TA 159/516 行，USB 96/156，framebuffer 168/201；其中含 TZ-RKP 相关修改。

这些是报告的组件代码量，不包括全部既有 OP-TEE、安全启动及依赖。作者说小块“可形式化验证”，并未给出完整形式化证明；植入遗漏检测留作未来工作，不应改写为已自动验证全部 instrumentation。

## 11. 性能实验与基线

Raspberry Pi 3 / BCM2837、OP-TEE/Raspbian；实际源码版本差异见第 1 节。多数实验 10 次取平均，未提供本轮可据以重算尾延迟的完整原始数据。

| 测量 | 结果 | 解释 |
| --- | --- | --- |
| LMBench | 2%–23% 开销；exit 最大，execve 约15% | paging、关键操作仲裁和切换对短路径影响大 |
| CoreMark-PRO | 多数约1%–2% | 长计算稀释控制开销，不代表所有 I/O 低开销 |
| DMA TD-mode | 增加 CB 数后相对开销约17%→8% | 含准备 CB、copy/verify 和控制 MMIO，非纯传输带宽 |
| TPM | 2-byte random 最高约3.68倍；hash 最高约2.71倍 | 包含日志、安全缓冲和 CA–TA 通信 |
| Keyboard URB | 94.2µs，3.05倍 | 单路径，不代表完整输入应用统一慢三倍 |
| Keyboard IRQ handler | 64.7µs，1.33倍 | 只测成功 URB 分支，不涵盖错误/重试 |
| Keyboard 应用 | 125–1000 次虚拟输入，增加5%–9% | 每次输入带10ms延迟，吞吐不代表无间隔最坏情况 |
| Framebuffer | 1.6MB write慢14%，部分大写/mmap更快 | 提升区禁中断减少 context switch；基线条件改变 |

不能将 framebuffer 最高约47%的改善称为一般安全设计加速，也不能将 CoreMark 低开销用于替代 GPU 共享性能。最有用的评估方法是同时报告微路径和服务端到端成本，并保留调度条件变化。

## 12. 作者代码的实际核验

固定仓库包含 Linux、TF-A、OP-TEE、客户端和示例。根递归 Git tree 返回 `truncated=true`，因此本轮没有把返回清单当作全仓完整目录；只对明确取得的文件作陈述。

已读 README.rst、`linux/arch/arm/kernel/mytee.S`、示例 kernel module、`tpm_tis_core_mytee.c` 与 framebuffer 头。可见 HVC/SMC API、`mytee_up_priv/down_priv` 及 TPM trusted flag 访问，确认这是实际驱动植入，而非只有论文伪代码。没有据此核验完整 DMA verifier、所有 monitor handler、所有 TA 日志校验或漏洞恢复路径。

README 提供工具链/构建和 SD 部署说明，历史源码有备份和生成物，本轮未执行其脚本，也未对本工作区设备部署。仓库 commit 与论文实验使用构建输入的严格同一性尚未证明。

## 13. 与项目及其他论文的关系

MyTEE 与 StrongBox/CAGE 都面对“大驱动不可信或不宜进 TCB”的问题，但采用临时提升和 TA 事务验证。TZ-LLM 将小数据面留在 TEE；ASGARD/PORTAL 更接近完整可信服务栈或 VM。Devlore/TEEtime 关注的物理中断配置和来源则超出 MyTEE 的示例通知方案。

项目已有完整可信 Proxy，无需将内核驱动任意块提升到更高特权。真正可迁移的是：控制数据的可信副本；实际内存范围与生命周期核验；请求/事务/响应的唯一关联；结果消费前验证权威状态。GPU 工作负载可写同步状态的问题仍需按实际 GPUVM 权限另行审查。

## 14. 后续设计和负例验证

优先建立 job 授权快照与私有完成记录，分别表达 terminal、output-visible、quiesced、reusable。限制任务控制对象的可写者，验证后不重新从 Client 指针取回权威字段。以 generation/强引用避免整数句柄复用，通知允许重复且不承担访问授权。

测试应覆盖描述符链被改写/成环、地址和长度溢出、同步页伪计数、伪完成与结果覆盖、Client close/reopen、取消/复位与回收竞争。先形成可复核失败条件，再判断是否需日志或额外机制；不把普通异常直接记为已攻破系统。

本篇未改运行代码，无新增性能测量；无硬件 run-id、无新增硬件 PASS。原型 watchpoint 缺失和代码审计范围均保留，不用独立页面发布掩盖证据限制。
