# Sigy｜可信异常来源、跨域信号授权与 GPU 事件副作用

研读日期：<date start="2026-10-27" />。状态：16 页公开作者全文（含附录）、作者项目、固定 PoC 文件树、下列源文件及 Gramine 修补提交已静态核对。未执行攻击，未构建 SGX 环境。未改运行代码，无新增性能测量。

## 1. 文献、版本与定位

**Sigy: Breaking Intel SGX Enclaves with Malicious Exceptions & Signals**，Supraja Sridhara、Andrin Bertschi、Benedict Schlüter、Shweta Shinde，ACM ASIA CCS 2025，Hanoi，2025-08-25 至 29，16 页。DOI：[10.1145/3708821.3710838](https://doi.org/10.1145/3708821.3710838)。[作者项目](https://ahoi-attacks.github.io/sigy/)、[所读全文](https://ahoi-attacks.github.io/sigy/sigy_asiaccs25.pdf)、[公开 PoC](https://github.com/ahoi-attacks/sigy)。

本地全文 `build/cca-gpu-followup-20261027/sigy.pdf`，SHA256：`151bb920d097bcfda60ff250f827aa47310a54d728e23f32a3b3cc8f0e040e7e`。这是新增的相邻机密计算论文，不是 GPU TEE 或 CCA 实现论文；与 Heckler、WeSee 各自独立计数。

## 2. 研究问题与贡献

异常与信号原本帮助程序恢复执行、协调线程、更新配置。迁入 enclave 后，应用仍希望保留这些功能，但 OS 已经从可信事件管理者变成攻击者。受保护的 handler 即使没有内存破坏缺陷，也可能在错误时刻执行正确代码，改变全局状态。

Sigy 研究两个问题：不可信 OS 能伪造哪些事件，以及这些事件会不会触发具有显式副作用的 enclave handler。它分析 8 个 SDK/语言 runtime 和 6 个 LibOS，报告其中 7 个存在相应通道；9 种语言中 8 种提供相关 handler/异常处理能力。后一个数字不能解释为这些语言的所有 enclave 程序均可攻击。

## 3. 威胁模型与重要例外

硬件、enclave 代码、可信 runtime/LibOS 按论文模型可信且无实现缺陷；OS、不可信 runtime 和 enclave 外进程可恶意。攻击者复用已有 handler，不能先修改 enclave 加入攻击 gadget。特定应用还需相应信号路径、可利用副作用及必要的定位或外部资源权限。

**Occlum 是例外模型**：论文考察同一 enclave 中互不信任的进程，攻击者是共驻进程；外部 OS 注入并不能获得同样的自定义 handler 效果。不能把这项结果写成与其余 SDK 完全相同的 OS→enclave 攻击。

## 4. 正常路径与信任边界

硬件异常路径：enclave 指令出错 → 异步退出并保存受保护状态 → OS/不可信 runtime 转发事件 → 可信 runtime 验证硬件保存的原因 → 应用 handler → 恢复执行。

软件信号路径：可信线程请求通知另一线程 → OCALL/OS 传送 → ECALL 进入目标 → handler。由于软件信号本来就不一定对应目标线程的硬件异常，单纯验证硬件 exit 信息不能认证此类消息是谁授权发送的。

Sigy 的核心是：SDK 可以正确保护第一条路径，又因兼容性增加第二条宽松入口，使攻击者从另一入口获得相同 handler 效果。保护是否完整要覆盖所有可达入口，不能只审查名为 IRQ 或 exception 的那个函数。

## 5. 各框架的区别

| 框架 / 路径 | 论文观察 | 不能过度推导的地方 |
| --- | --- | --- |
| Intel SGX SDK，论文 SGX 2 条件 | 核对受保护 SSA 的 EXITINFO，拒绝伪造硬件异常 | 正文另讨论 SGX 1 的差异，不能抹平版本条件 |
| Open Enclave、Teaclave、Asylo | 正常硬件异常接口有检查，新增软件信号入口可能绕过其来源保证 | 不是所有信号均支持；各入口不能合并成同一策略 |
| Gramine | 论文旧版同步异常转发缺少充分交叉核对；进程间软件信号已有可信消息通路 | 不能声称 Gramine 的所有进程信号都未经认证 |
| Scone、EnclaveOS | 黑盒测试显示可触发相应 handler | 闭源实现不能当作已完成内部源码审计 |
| Occlum | 共驻不可信进程可触发另一进程 handler | 与恶意 Host 注入模型不同 |
| 无信号支持或内部互信的其他系统 | 缺少该通道，或其模型排除恶意发送者 | 不代表其免疫所有异步攻击 |

论文第 5.1 节关于 Open Enclave 信号集合的文字与附录表 8、`SIGUSR1` 示例并不完全一致。本次不把该处文字当作精确完整的支持列表；涉及具体信号时，以明确示例、表格和已核对源码分别说明。

## 6. 定量案例及真实前提

| 案例 | 论文报告 | 适用条件 / 原型限制 |
| --- | --- | --- |
| Nginx 配置 / 二进制回退 | 恶意信号使服务重新读取旧文件，恢复旧状态 | Scone PoC 关闭加密文件系统；作者为兼容性移除不支持 syscall 等，并非证明启用完整防回滚文件系统仍失效 |
| Node.js TLS 服务 | `SIGUSR1` 启动调试端口，调试器可提取 RSA 私钥 | Node.js v10.14.1、Scone v5.8.0，未启用阻断该通道的网络策略；不是所有现代 Node.js/部署默认均同样暴露 |
| Java JSAT 分类器 | 240 次注入使错误率由近 0% 升至 66%；额外约 3.4s，论文报 3.34× | 实验让目标函数等待 ArithmeticException，简化定位，不能当成未改应用下的任意时刻稳定攻击 |
| C MLP 合成例 | 准确率 97.09%→59.27%；额外约 970s，论文报 53.7× | 作者专门加入溢出恢复 handler；3 隐层、每层最多 6 单元，2000 epochs、1096 个 Banknote 样本，不是原生应用已有漏洞的证据 |

论文摘要/引言称最坏例需要约 186 billion 次注入；正文的注入计数排版与约 `10^8` 次函数调用描述不易直接对应。没有原始测量明细，本次不据此重建注入吞吐量或宣称其计数已独立核实。上述倍数沿用作者口径，不额外推算基线耗时。

## 7. 实验平台和证据强度

两套 Intel SGX 环境：i7-10875H、8 cores、32GB、Ubuntu 20.04/kernel 5.10.2；Xeon Gold 6346、32 cores、378GB、Ubuntu 20.04/kernel 5.19.0。SDK v2.16，分别使用外部 2.11.0 或 in-tree driver；均支持保存论文使用的受保护退出信息。语言调查的 Node.js 版本 v21.6.1，与端到端 Node.js 案例 v10.14.1 分开。

基础通道证据来自手写 handler 测试，端到端案例及高频注入框架进一步展示影响。240 次注入和 MLP 耗时是应用结果，不是 GPU fence、中断投递延迟或本项目多 Client 开销数据。论文没有提供 CCA GPU、Mali 并发共享或本项目代码的漏洞证明。

## 8. 防御：证明事件原因，认证软件请求

硬件异常要将不可信软件描述与受保护硬件原因交叉核对，不能只检查信号号合法。软件信号要由可信发送者先登记目标和事件，再由目标验证；跨 enclave 则需可信身份建立的消息通道。把每个外部信号全部丢弃可以减少攻击面，却会改变外部管理功能；有业务需求时，应重新定义显式授权的控制协议。

论文称需要接受任意不可信外部信号的原接口无法获得相同保证。这不等于任何外部管理员操作都无法安全实现：本项目可以在 RMM 已认证身份基础上规定谁有权取消哪个 job、切换哪个 session 或请求什么 reset。后者是项目推论，不是论文已实现的防御。

防回滚文件系统或端口策略可阻断特定 Nginx/Node.js 攻击链，但不消除所有直接修改 enclave 状态的信号。AEX-Notify 针对精确单步，不会自动认证软件事件；只需一次信号或利用正常退出时机的情况仍需事件授权。

## 9. Gramine 修补的实际证据

已读取作者引用的 [修补提交 a390e33e16ed374a40de2344562a937f289be2e1](https://github.com/gramineproject/gramine/commit/a390e33e16ed374a40de2344562a937f289be2e1) 中三份文件 diff：入口汇编将可信 EXITINFO 与不可信 external event 分别传入，C handler 交叉核对异常向量和软件事件，失败退出。代码还处理 benign page fault 与 quit/interrupted 的特殊组合，明确接受其中可导致 DoS 的情形，因为该模型不保护可用性。

这支持区分安全完整性与可用性的边界；不能把“接受 quit”直接写成任意伪造状态更新漏洞。所核验的是固定修补 diff，不是 2026 年所有发行版的部署审计或完整 Gramine 安全证明。

## 10. 公开 artifact 固定版本与范围

`ahoi-attacks/sigy` 固定 `7763f4135841a553ccfecc16e1c63cd441af1028`，递归树 62 项且未截断。已读取根 README，Gramine C/Java PoC、README、安装脚本和 Makefile，Open Enclave README/`td_state.patch`，Occlum README/子进程示例，Asylo handler 源文件及 Scone 内核注入模块。

关键核对结果：Gramine C/Java 与 Asylo 示例都有显式 busy loop；Open Enclave patch 以等待替代正常信号请求，并删除部分原测试路径；Occlum 示例由共驻父进程发送信号，README 明示用 busy loop 简化时机。Scone 模块构造 `SIGFPE`/`FPE_INTDIV` 并查找内核发送函数，符合论文“恶意内核可伪造来源元数据”的能力。

Gramine 安装脚本从包仓库安装未锁版本的软件，Makefile 克隆浮动 examples；不保证得到论文使用的 `211ec447ee69f16139520fc3a17c561c36a00943`。指南要求 Java 11，而论文实验表是 OpenJDK 17，需区分。完整文件树没有据此证实四个端到端案例和高频 sgx-step 实验均可一键重建；本次没有读取所有框架上游源码，也没有运行任何安装或攻击命令。

## 11. 对 Arm CCA 的明确适用边界

**论文明确认为 Sigy 不适用于其分析的 Arm CCA 和 TrustZone。** CCA guest OS 在可信边界内，不直接接受不可信 hypervisor 提供的同类用户异常/信号；论文引用的体系结构差异也限制了 Heckler 路线。不能把“通道设计值得借鉴”改写成“CCA 已受到 Sigy 攻击”。

本项目新增 ProxyRealm 服务与 Client 协议后，应独立分析自己引入的事件语义：即使基础 CCA 阻断 x86 攻击路径，自定义的取消、错误、reset 或完成请求仍需要其自己的授权规则。这是新增协议的审查要求，不是断言当前实现已经存在绕过。

## 12. 与已有研究及项目的关系

| 工作 | 与 Sigy 的互补点 | 对项目的用途 |
| --- | --- | --- |
| Heckler / WeSee | CVM 中断与异常 handler；Sigy 转向用户 enclave 软件信号 | 区分硬件原因、转发参数和 handler 副作用 |
| PORTAL / ACAI | 可信服务、Client/设备身份和访问授权 | 身份正确还应检查该身份是否有权触发此事件 |
| CAGE / StrongBox | GPU 执行保护、切换和完成路径 | 不把触发 handler 等同任务已经成功 |
| Devlore / TEEtime | 中断路由、真实性与控制权 | 路由正确后继续检查 job 归属及允许的状态变化 |
| PhantomMap | 实际页授权与生命周期 | 错误/取消事件不能提前释放 GPU 仍访问的页 |

以上为机制比较，不宣称所有论文存在直接引用关系。本项目已有 RMM 认证队列/持久 IRQ127、独立 GPUVM、私有请求快照、真实原生 fence 和 cookie/epoch；这里无需重复提出给消息添加身份。

## 13. 可以直接形成的项目研究

把通知视为“重新读取可信状态的机会”，让任务终态只由已绑定的可信完成/错误事实推进；外部 wakeup 不携带自动授予 SUCCESS、取消受害者或全局 reset 的权力。若接口确实允许取消或 reset，分别检查请求者、目标、scope、session/epoch 和当前状态。

进一步建立“事件—副作用”表：完成是否发布结果，错误是否推进 timeline，取消是否只阻止未来提交，ACK 是否只释放通知状态，reset 是否影响其他 Client。对每个具有不可逆副作用的入口，验证与实际使用保持同一对象生命周期，错误/取消也不能伪装为成功。

建议验证重复/伪造 wakeup、另一 Client 的取消、合法发送者的越权目标、旧 epoch 的错误、嵌套/乱序完成、关闭过程中事件到达，以及重复 ACK。可接受结果是目标状态不被越权改变、合法终态幂等、未停止的 DMA 对象仍保留引用；是否承诺通知延迟或抗淹没，另列可用性假设，不由认证机制自动保证。

## 14. 独立评价与记录

Sigy 的价值是展示“代码完整、handler 无 bug”仍需可信事件原因与软件发送授权。它适合支撑本项目第二部分的中断通信隔离论证，尤其是多租户服务新增控制接口；它没有实现 CCA GPU 共享，也不能单独支持项目的新颖性或完整安全性结论。

统一记录：SGX 异步事件论文全文及固定 PoC/修补定向静态研读｜项目 glmark 前后均未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件 run-id、新增硬件 PASS 或攻击复现日志｜保留为新增相邻精读，版本、合成案例、busy loop 与部署条件均保留。
