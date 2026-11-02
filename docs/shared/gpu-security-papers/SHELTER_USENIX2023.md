# SHELTER：CCA 用户态隔离、异常边界与公开原型精读

研读日期：<date start="2026-10-27" />。定位：CCA 基础隔离扩展，**不是 GPU 共享系统**。已读 18 页作者全文及附录，并定向检查固定版本公开代码。未改运行代码，无新增性能测量。

## 1. 书目信息与证据版本

Yiming Zhang、Yuxin Hu、Zhenyu Ning、Fengwei Zhang、Xiapu Luo、Haoyang Huang、Shoumeng Yan、Zhengyu He，SHELTER: Extending Arm CCA with Isolation in User Space，USENIX Security 2023，6257–6274。

来源：[正式会议页面及 BibTeX](https://www.usenix.org/conference/usenixsecurity23/presentation/zhang-yiming)、[作者全文](https://fengweiz.github.io/paper/shelter-usenix23.pdf)、[项目页面](https://compass.sustech.edu.cn/shelter/)、[公开仓库](https://github.com/Compass-All/SHELTER)。作者全文 535,559 字节、18 页，SHA256 `45fd3ec7c712918111431655fbd74a52cc3a38ff58baa275bd95a52ad4c47481`。

官方 PDF 下载不完整后沿作者真实链接取得完整文件；没有将部分文件当全文。另已取得 2025 年 TDSC 的 Complementing Confidential Computing Environment for Applications on Arm CCA，尚未逐节比较扩展内容，本篇不将其算作另一篇已完成解读，也不把两版本的机制混写。

## 2. 研究问题与关键取舍

标准 Realm VM 面向虚拟机隔离；论文希望第三方以用户态程序方式使用 TEE，同时不信任 Host OS、hypervisor、Secure 软件和 RMM。其方法是 Normal EL0 的 SApp 配合 Root EL3 的 Monitor，复用 RME 的 GPC/GPT，按当前核心运行的 SApp 选择不同 GPT。

这是 CCA 原语之上的用户态 enclave 方案，不能说 SApp 就是 Realm VM。为减少中间切换，论文把 GPT 和调用检查直接放在 EL3；RContainer 后续将更多功能移到隔离的 EL1 mini-OS，恰好形成最高权限代码预算的对照。

## 3. 威胁模型与可信基

硬件/RME、可信启动和签名加载的 Monitor 被信任；攻击者可控制 OS、hypervisor、Secure 特权软件或 RMM，也可启动恶意 SApp。目标包含双向隔离：恶意 SApp 同样不能读取其他域。

物理攻击、一般 DoS、侧信道和主动泄密不在目标内。持久存储与 I/O 的加密信道、远程证明被假设可以结合既有方案，未在本原型完整提供。普通 OS 负责调度和实际 syscall/interrupt 服务，因此应用可用性仍依赖外部软件。

表 3 的 2072 SLoC 是新增 Monitor 代码：GPT 229、内存管理 329、生命周期 364、syscall handler 901、其他 249。既有 TF-A 约 310k 行也在相应信任链上，不能把“新增 2k”写成平台全部 TCB。附录比较的 TF-RMM v0.2.0 9.1k 行、去证明后 8.2k 行也是特定历史版本口径。

## 4. 多 GPT 与每核执行域

Host GPT 将 SApp 私有内存标为 No-access；每个 SApp GPT 只允许自身内存，其他域不可访问；GPT 自身位于 Root 保护区。Monitor 控制 GPTBR_EL3 等寄存器，在进入 SApp 前选其视图，离开前恢复 Host 视图。即使关闭普通 MMU，GPC 仍适用。

实际安全对象是物理页、当前核心的域身份和切换路径，而非单个虚拟地址。页表根和 GPT 切换必须由可信层控制；不能允许不可信 OS 使用相同 Normal PAS 就取得 SApp 页访问权。

多核管理用锁保护 GPT 和生命周期修改；用 GPT 根地址作 SHELTER ID，记录调用归属。设计说明在切换和更新时失效包含 GPT 信息的 TLB，清理相关 cache，设置 CnP=0，并包含禁用 SMP coherency 的处理。它们属于论文特定多视图策略；不应不加分析地照搬为本项目每次 RPC 都清整个 cache。

## 5. 物理池、页表与小对象

不可信 Linux 通过 CMA 提供连续物理内存，Monitor 验证基址、长度和 SApp 间不重叠，再登记和修改 GPT。连续内存将多次逐页申请变成批量操作，减少切换。可信检查决定授权，CMA 自身没有因被使用而变可信。

运行页表复制到 SApp 私有区，OS 更新经 Monitor 验证：物理页必须位于该 SApp 池内、不能非法重叠栈等区域，再同步受保护表。用户态 SLib 以虚拟地址别名和页内 offset 放置小对象，避免一对象一页的浪费；这是分配优化，不是额外的逐对象硬件访问隔离。

对本项目，实际 HPA 授权、对象归属和映射生命周期比“返回一个范围看起来合法的 IPA”更关键。项目既定的 RMM 原始 Client 认证、ProxyRealm 软件 IPA→HPA 授权翻译和受保护 GPU Stage-1 设计可继续成立，不必用另一套域视图替换。

## 6. 创建、进入和销毁

设计创建流程为：隔离将使用的区域，验证已加载环境，建立私有上下文与页表，基于 shadow GPT 模板构造新 GPT。进入时只能经 Monitor，切换到本 SApp 的 GPT；中断、异常和系统调用退出也经 Monitor，保存上下文、清理必要寄存器，再恢复 Host GPT。

销毁先清零内存、清理缓存、释放 GPT 和元数据，再允许 OS 回收。CPU 页已清理是一个条件；若未来允许 GPU/DMA 使用，还需先保证设备不再访问该页。本文没有 GPU job、native fence、设备 reset 或多 Client DMA drain 的实现，不能据其销毁流程宣称项目回收条件已全被证明。

## 7. 系统调用及 TOCTOU

带指针参数通过共享缓冲区传递，约 50 类相关 syscall 覆盖实验应用。返回检查前 Monitor 将该物理缓冲区在 Host GPT 中改为不可访问，再检查返回长度并复制回私有内存。附录明确用地址翻译指令取得物理地址再更新 GPT。

这展示了检查时稳定内容的重要性。不过，屏蔽 Host CPU 写入不自动涵盖所有设备别名和 DMA 写入者；要与设备访问策略一起成立。长度检查也只覆盖部分 Iago 问题，论文明确承认其他语义攻击未全部处理。

项目已有私有快照，不宜再把“加入快照”列为新设计。可继续核验的是嵌套对象是否也被冻结、受保护身份是否贯穿到实际使用，以及错误/取消路径是否会跳过授权。

## 8. 异步中断和信号的可信程度

异步中断经 Monitor 转交 OS；OS 负责服务，返回时 Monitor 检查恢复目标。对信号，Monitor 记录 rt_sigaction 注册的 handler，OS 在共享 signal frame 中构造上下文，进入 handler 前检查地址已注册并撤回 Host 对 frame 的访问；sigreturn 路径再处理恢复。

**合法入口地址和不可变 frame，不等于事件原因可信**。注册 handler 只说明该代码被允许作为 handler，不能独立证明此次 SIGUSR/SIGFPE 等原因和应用副作用得到授权。这里与 Sigy/Heckler 的问题形成比较，但本次没有重现 SHELTER 攻击，也没有宣称已有论文证明它可被相同漏洞利用。

对 GPU 通知应分清：物理 IRQ 或 doorbell 触发处理；可信状态决定哪个 job 已完成以及允许何种副作用。已有 IRQ127、认证队列和真实 fence 应围绕身份、类型和生命周期一起论证，不能把“通知来了”作为释放页或切换 Client 的依据。

## 9. 固定代码的定向核验与设计差异

仓库固定 `adef631e0fecfc20577da61e03d49bf16b1edbc2`。根递归树被 GitHub 截断，后改为读取根、src，以及 Monitor 子树 4362 项、userland 子树 13 项，后三者未截断；未把截断的整仓树称为完整代码审计。

实际读了固定 README、环境获取脚本、启动脚本、Linux 的 shelter syscall 文件，以及 Monitor GPT 文件中创建、进入、返回复制、信号登记/检查等相关函数、哈希校验函数和部分驱动接口。关键代码文件经 Git blob API 取得，避免仅靠失败的 raw 下载。

| 位置 | 实际观察 | 结论范围 |
| --- | --- | --- |
| `lib/gpt/enc_sign.c` 的 `shelter_verify_sign` | 对输入计算 SHA256，与编译进固件的 `hash_true` 比较 | 固定摘要白名单；不是函数名所暗示的通用公钥签名协议 |
| `gpt_core.c` 的 `shelter_creation` | 可见调用核验 vector 的 `EXCEPTION_VECTOR_LENGTH` | 该路径未显示任意完整 SApp 镜像签名验证；不能用正文概括补足实现 |
| `shelter_syscall_result_handle` | 先撤回共享区权限；部分读返回仅在长度为正且不超过已记长度时复制 | 可验证的返回边界，未穷尽全部嵌套字段 |
| `signal_handler_addr_record` / `shelter_enter` | 登记 handler 地址；返回 PC 改变时检查地址集合，保护 signal stack | 体现控制流白名单，未见逐次可信原因认证；存在 PC+4 的特殊处理，需单独说明使用条件 |
| README | 当前仅静态链接程序；复杂程序尤其多进程可能 crash/GPF，syscall 尚未全处理 | 不能写成完整兼容普通 Linux 应用的成熟发布版 |

上述是定向静态观察，不是完整漏洞审计。创建路径核验顺序和所有并发写入者之间的关系仍需进一步审计，未仅凭局部函数宣布可利用 TOCTOU。

`scripts/env_fetch.sh` 使用 19.10 分支的 `pinned-latest.xml` 和外部下载，固定项目提交不等于自动固定全部外部依赖。本次只阅读脚本，没有执行其中 apt、删除、安装或设备命令。

## 10. DMA 与证明的范围

论文提出使用具备 GPC 的 SMMU，让设备沿受控 GPT 检查 DMA。正文有架构级设计，但没有给出本项目需要的 GPU 客户授权、固件信任、上下文并发和完成路由协议；本次也未核实完整 SMMU 实现。

远程证明被假设可加入，附录明确原型没有 attestation；内存加密也未实现。实验中的“验证”主要是本地检查最小 SApp/向量表，不能称远程用户已验证了服务镜像、实例和真实设备授权。

## 11. 平台与比较方法

功能原型：RME FVP、Linux v5.3、TF-A arm_cca_v0.3。性能原型：Juno R2、8GB、A72 固定 1.2GHz，关闭 A53，重复 30 次。以 ACTLR_EL3/AFSR0_EL3 替代 GPT 寄存器，普通 TLB 全失效模拟 GPC 缓存维护，包含论文要求的微架构维护。

这是模拟管理成本，缺少真实 GPC 和硬件内存加密的代价。方法可以验证协议与估算软件开销，不能把数字写成真实 Armv9 原生结果，也不应因此否定设计。

Realm VM 对照是作者在同一 Armv8 板上实现的基本 RMM/Realm context 模拟；Realm VM 和普通 KVM VM 均 2 vCPU、512MB。它不是后续成熟 CCA 软件栈的统一性能结论。Sanctuary 对照来自其论文的另一块 HiKey960，不是同板重跑，作者也称 best-effort qualitative comparison。

## 12. 主要实验数字

| 项目 | 论文结果 | 条件与限制 |
| --- | --- | --- |
| 4MB 分配/释放 | 3189 / 769μs | CMA、含分配初始化 |
| 创建/销毁 | 4925 / 1054μs | 4MB 最小应用，不代表大型镜像完整部署 |
| Exit / Switch | 391 / 3μs | 两个不同测量项；不能合并为所有退出只需 3μs |
| 创建细分 | GPT 2953、transition 9、verification 1566、setup 7、clean 390μs | 总计 4925μs |
| shadow GPT 优化 | GPT 构造平均下降 77.5% | 不同总物理地址空间规模，不是总应用时间下降 |
| AES / Apache / Memcached / Nginx | 5.2% / 15.0% / 8.3% / 11.8% 开销 | 指定计算和网络基准；OTP/LeNet 稳态无 syscall 时近零开销 |
| Normal UnixBench 平均开销 | 1000/100/10ms 启动间隔下 0.37% / 1.87% / 7.68% | 最密集条件单项最高 16.9% |
| 小对象内存优化 | Numeration 98.5%；Apache 17.6%、Nginx 68.6%、Memcached 34.8% | 相对一对象一页模型，不是相对优化过的普通 malloc |
| 三服务的平均开销 | SHELTER 11.7%；Realm 模拟 32.0%；普通 VM 29.8% | 同一篇中的特定基线，未含证明和实际内存加密 |

销毁清理随内存增长：4MB clean 1050μs，256MB clean 66986μs；transition 只占少量，不能用快速改权限掩盖实际清理成本。

## 13. 安全评估的证据

45 个 CVE 是按威胁模型进行缓解分析，不是 45 个未经修改 exploit 都在 FVP 重现。论文另外模拟恶意 RMM/特权软件访问 SApp 页，出现 GPF；公开 access_test 也演示 OS 非法访问受到阻断。

这些是物理页隔离的有用证据，未覆盖共享缓冲区全部 Iago 语义、恶意多核调度、信号原因、GPU DMA 撤销或恢复竞争。本次没有运行任何攻击、功能/性能复现，因此不新增实验 PASS。

## 14. 与本项目的关系及后续设计

SHELTER 有助于解释受保护页表、根配置、调用上下文和检查时稳定数据为何必须一起成立；PORTAL/ACAI/PhantomMap 将这些问题推进到可信设备服务、身份映射和实际页生命周期。它们共同支持项目现有 ProxyRealm 假设，但没有自动覆盖 GPU 完成通知到任务状态变化的授权链。

项目已有 GPUVM、认证队列、私有快照、native fence、cookie/epoch 和持久 IRQ127。建议进一步建立“可信域—当前会话—GPU context—job—事件类型—允许状态转换”的受保护记录，明确每项检查发生在任何不可回滚副作用之前；可信通知不能让旧 job 触发新对象释放。

性能部分可以借鉴批量更新、缓存模板和减少切换，但需要在原有身份/引用/失效规则下优化。每次减少一次 copy、TLB 操作或等待，都应给出被省略操作不再必要的前置条件及失败回退，不能仅展示 glmark 提分。

独立评价：本文对 CCA 用户态隔离的贡献清楚，多核视图和受保护执行入口具有直接方法价值；其证明、安全 I/O、全 syscall 支持和 GPU 生命周期仍有明确边界。下一步可优先验证已有协议的非法状态转换拒绝与恢复后旧身份失效，再决定是否需要新的机制。

统一记录：CCA 用户态隔离全文与固定代码定向研读｜项目 glmark 前后均未测｜分差与百分比不适用｜未改运行代码，无新增性能测量｜无硬件 run-id 或新增硬件 PASS｜保留设计、公开原型及模拟测量的边界。
