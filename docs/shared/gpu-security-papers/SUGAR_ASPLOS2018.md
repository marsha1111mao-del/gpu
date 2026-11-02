# TGS-062｜Sugar：每应用虚拟图形栈、共享 GPU 隔离与完成通知边界深读

研读日期：<date start="2026-10-27" />。状态：16 页全文、正式元数据、完整项目指南及固定提交的选定实现路径已阅读。未构建或运行；未改运行代码，无新增性能测量。

## 1. 文献与版本

**Sugar: Secure GPU Acceleration in Web Browsers**，Zhihao Yao、Zongheng Ma、Yingtong Liu、Ardalan Amiri Sani、Aparna Chandramowlishwaran，ASPLOS 2018，519–534。正式会议论文 DOI：[10.1145/3173162.3173186](https://doi.org/10.1145/3173162.3173186)。[作者公开 PDF](https://www.ics.uci.edu/~ardalan/papers/Yao_ASPLOS18.pdf)由作者出版列表及项目 README 链接。

全文 `build/cca-gpu-followup-20261027/sugar.pdf`，SHA256：`47f61ccc7a0a3679d246fd5e8ab77c7c70e66fbbb78545d86cb47355e8b686b4`。原 GitHub 清单使用 `10.1145/3296957.3173186` 链接；本报告采用论文首页与正式会议元数据一致的 DOI，不把链接差异记成两篇新论文。本条完成原库 TGS-062。

## 2. 要解决的问题

传统浏览器把 WebGL 后端集中到 GPU process，但该进程仍调用宿主图形库和内核 GPU 驱动。恶意网页可以攻击这条链路；单独一个 GPU process 不能自动隔离内核驱动中的漏洞。

Sugar 的核心是为每个 Web 应用分配独立 vGPU，把整个图形软件栈，包括 vGPU 驱动，放进该应用进程。驱动即使出现应用可触发的内存错误，也应被应用自己的 CPU/GPU 访问边界约束。它结合用户态驱动复用、GPU 虚拟化和浏览器重构，不只是新增一个进程沙箱。

## 3. 威胁模型

Web 应用及整个 renderer 进程不可信；浏览器核心进程、GPU process、宿主 OS、root 和 GPU 硬件可信。论文明确指出获得 root 或 kernel 权限可以绕过 Sugar，且不覆盖侧信道。

所以这是一种恶意应用隔离系统，不是保护应用抵抗恶意 Host 的 CCA/GPU TEE。其相关工作还明确将自己与能抵抗不可信云的 Haven 区分。引用时不能因为文献库把它归入 TEEs 类别，就改写威胁模型。

## 4. 图形平面架构

每应用的 virtual graphics plane 包含 vGPU、用户态驱动、Mesa/DRM 和 WebGL 后端。trusted primary graphics plane 由窗口管理器和浏览器核心使用，独占真实显示控制器；应用只能把自己的渲染结果交给它合成。

单 GPU 版本让所有平面共享一块 Intel GPU；双 GPU 版本用 Intel GPU 提供应用 vGPU，另一块 Radeon GPU 承担可信主图形平面。双 GPU 有助于隔离前端渲染负载和 UI，但不意味着所有系统资源、异常恢复和侧信道均隔离。

论文不是为每个应用启动一个完整 VM。它让进程直接使用受可信虚拟化层控制的 vGPU，避免为浏览器非图形路径引入完整 VM 重构。

## 5. vGPU 如何附着到进程

| 路径 | 论文机制 | 可信责任 |
| --- | --- | --- |
| MMIO/配置 | 用户 VA 映射寄存器但移除访问权限，异常进入宿主模拟 | 不能让应用直接修改真实设备特权状态 |
| GPU 页表 | 捕获 guest 表修改并生成真实 shadow 表 | 只允许映射应用自己的进程页 |
| 地址解析 | 用户驱动把进程 VA 同时作为其虚拟/物理地址表示，宿主遍历该进程页表得到 PA | 进程地址空间和具体页必须一致 |
| 页驻留 | DMA 可访问页 pin 住 | 页不能在仍可访问时被换出或另作他用 |
| 中断 | 宿主向用户态驱动发送 SIGUSR1，按驱动状态屏蔽/解除屏蔽 | 该机制依赖可信宿主和进程信号实现 |

其中 shadow 翻译与本项目映射建立时软件解析具有比较价值，但 Sugar 的进程 VA→PA 并非 CCA 的已认证 Client IPA→HPA，不能跳过 RMM 身份和授权步骤直接类比。

## 6. 如何复用完整驱动

作者用 User Mode Linux 包装已有约 123,000 行 Intel 驱动，将其构建为共享库。小对象从初始化分配的内存池取得，较大图形缓冲按需申请；图形库的驱动系统调用改为调用这个库。

对单应用 vGPU，原型使用简单 surface manager，把一个 WebGL texture 绘到整个虚拟显示 framebuffer。这个实现缩小了窗口管理复杂度，但也造成每应用只支持一个 WebGL texture 的限制。

这条路线与可信完整驱动 ProxyRealm 不同：Sugar 把每应用驱动置于不可信域，依赖下层虚拟化隔离；本项目把共享驱动放进可信服务域。可以比较安全责任和维护成本，不能未经修改就称本项目获得相同 TCB 缩减。

## 7. 渲染结果与同步

应用 GPU thread 在本进程处理 WebGL，替代向共享 GPU process 提交全部绘图命令。渲染后将 texture 贴到 vDisplay，可信 GPU process 通过虚拟显示 readback 获得图像并合成；双 GPU 场景还通过 dma-buf 跨驱动导出/导入 framebuffer。

原有 compositor sync point 假定 GPU process 知道渲染进度；拆分后应用需通过 IPC 告知对应 sync point 已满足，避免可信进程无限等待。论文提供了图形功能同步流程，没有提供面向恶意 Host 的带 Client/job/epoch 认证的完成协议。

尤其不能将应用发出的“图像已准备好”IPC，或者普通信号的出现，当作某一机密任务正确完成、结果完整或全部 DMA 已停止的证明。将该模式迁移到 Realm 间通信时，必须把功能依赖通知与可信完成状态的依据讲清楚。

## 8. TCB 结果的统计口径

| 论文统计项 | 原架构 | Sugar |
| --- | --- | --- |
| WebGL 暴露的特权图形栈 | 738,000 LoC | 34,400 LoC |
| 主要组成 | 驱动 123k、Mesa 441k、DRM 16k、Chromium GPU process 158k | GPU 虚拟化 28.3k、附着代码 1.5k、KVM 指令解码 4.6k |

这是论文定义的“Web 应用可达的特权图形栈”口径，约减少至 1/21.5，作者概括为约 20 倍缩减。它不是整机 TCB 只有 34,400 行；可信 OS、root、硬件和浏览器核心依然是安全前提。LoC 也不能独立证明新模拟层无漏洞。

## 9. 安全实验和未解决问题

作者详细研究 20 项 WebGL 漏洞报告，在当时平台上直接复现 3 项，移除修复后再复现 3 项。论文对 Sugar 的保护结论大多来自机制分析，只有一个同时符合已复现条件与原型平台的漏洞做了实际防护验证；不能写成 20 个漏洞都在 Sugar 上运行过。

结论是单 GPU 版本可应对其中 17 项、双 GPU 版本 19 项。额外两项是 hang 导致 UI 停顿；剩下一项时间侧信道两者都不解决。路径/用户名泄漏还依赖额外进程沙箱策略，不能只靠将编译器搬入应用修复。

双 GPU 仍可能触发挂起 GPU 的 TDR/reset，原文承认 TDR 实现错误可能造成内核 panic 或显示异常。双 GPU 缓解 UI 同设备竞争，不是完整故障遏制证明；“挂起后不 reset”和“把 TDR 移到用户态”是未来工作。

## 10. 原型平台与实验公平性

Intel Core i7-5775C / Iris Pro 6200、16 GB RAM、Ubuntu 16.04.2，双 GPU 使用 Radeon R9 290。软件基于 KVMGT 2016-Q3、Linux 4.3.0、Mesa 12.0.6、DRM 2.4.70、Chromium 58.0.3023.0。

Sugar 使用 EGL，baseline 默认 GLX；Radeon 和 Sugar 的 GPU process 因兼容性使用 Mesa 17.0.7，而应用 vGPU 库和 Intel baseline 使用 Mesa 12.0.6。论文披露这些差别，因此性能结果包含组合配置影响，不可全部归因于单一隔离机制。两侧均构建 Release 并关闭 `dcheck_always_on`。

五类 WebGL benchmark 为 Blob、Many-Planets、San-Angeles、Cubemap、Animometer，Blob 又改变 blob 数和分辨率。独立 GPU 更强也不能让 WebGL 超过提供 vGPU 的 Intel GPU 能力。

## 11. 性能数字与边界

| 指标 | 原文结果/设置 | 限定 |
| --- | --- | --- |
| 用户可见帧率 | 原本 >60 FPS 的任务在 Sugar 中仍 >60，接近/低于 60 的任务有竞争力 | 浏览器实际封顶 60 不表示最大吞吐无下降 |
| texture post | 默认 Blob 约 0.23 ms | 以 300 FPS 举例约占帧时 7%，不是每种负载独立测得固定比例 |
| 对 SwiftShader | 平均性能增加 375%，最高增加 1216%；CPU 利用率少 74%、每帧 CPU 少 92% | 对照为软件渲染，不能写成相对 native 的提升 |
| 默认 vGPU 内存配置 | aperture 64 MB / 非直接 CPU 可见 128 MB | 基于所测配置选择，非所有应用最优 |
| 并发 Web 应用 | 实测最多 3 个，分别在独立 Chromium session 跑 Blob | 特定 aperture 配置；并非恶意并发攻击覆盖 |

三应用实验还把系统 aperture 从默认保留量减至 32 MB，不能与单应用设置混同。双 GPU 的性能干扰较小，但可信合成与 native OpenGL 仍竞争第二块 GPU；没有严格实时性或服务保证。

## 12. 公开代码的实际核验范围

[文档入口](https://github.com/trusslab/sugar)固定 `9067bd949cfd07c7b890bdeb0ca0d11b32ce92aa`。完整 tree 是 README、网站、漏洞记录、图片和示例产物，不是全部实现；实际实现由 README 指向 Mesa、DRM、kernel、UML 驱动和 Chromium 仓库。

本轮固定 [kernel](https://github.com/trusslab/sugar_igvtg_kernel/tree/e1747bcf4c50e307f2a6c200acef6fb82be8e12e)、[UML](https://github.com/trusslab/sugar_igvtg_uml_driver/tree/06aca2e49ae41705624df1d89db50c945c2f95b0)、[Chromium](https://github.com/trusslab/sugar_chromium/tree/5f1dd3da9f21c65c4f1388f22e10585941f0cbc9) 提交，并读取相关提交文件清单；重点静态阅读 kernel 新增 `local.c` 的进程页解析、MMIO 模拟、pin/unpin 和信号注入，及 UML `main.c` 的进程附着和信号 handler。未完成所有模拟器、页表维护、Chromium 同步、Mesa/DRM 与清理路径审计；部分原始文件获取超时，不冒充完整仓库审计。

可见代码通过 `vgt->local_mm` 遍历特定进程页表，通过 `send_sig_info(SIGUSR1, ..., vgt->local_task)` 通知指定 task，而用户态 handler 再处理设备事件。它证明这条功能路径存在，不证明信号本身具备机密计算完成真实性。

`local.c` 的 pause/shutdown 及 aperture unmap 存在未实现提示；UML 源码静态默认内存为 64/448 MB，与论文实验默认 64/128 MB 不同，复现须核对实际参数。页面生命周期和错误恢复不能仅凭论文概述视作完整实现或已验证安全。

## 13. 构建指南与安全论证的差距

完整指南要求旧工具链、内核与 GPU 配置，并在启动 Chromium 时使用 `--no-sandbox`，还调整控制 sysfs 的访问权限，内核命令行关闭部分既有路径。它提供运行 demo 的方法，不能据此宣称其运行配置已保留论文依赖的全部应用沙箱限制。

本轮没有执行这些命令，也未把“指南存在 no-sandbox”直接升级为已复现逃逸。严谨的复现需要核对进程、设备节点、fd 传递、控制接口和默认允许策略，证明应用只能访问自己的 vGPU，不能接触主图形平面的特权入口。

此外，指南明确硬件只验证一套平台，且依赖手工 card 编号、硬编码 MMIO 地址和部分已失效上游仓库。论文提出的多纹理支持、消除 tearing、原生应用集成和其他 GPU 支持仍需另做实现与评估。

## 14. 与当前 ProxyRealm 项目的关系

保留本项目给定的可信 ProxyRealm、RMM 身份、软件 IPA→HPA 授权翻译、GPU Stage-1 及实际页表/root/MMIO/固件保护假设。Sugar 不要求我们用实验硬件能力否定这些前提；它让两种共享驱动策略的安全职责更清晰。

本项目已有独立 GPUVM、私有请求快照、真实原生 fence、cookie/epoch 与 RMM 持久通知。可继续研究的是：每个执行 context 和映射在提交、完成、取消、reset、回收期间保持同一 Client 归属；中断合并、延迟或重复时，只推进有真实完成依据且身份仍有效的任务。

这应作为既有机制的组合性质去论证，不能把一个全局 IRQ、一项共享计数或任意一条 Client 消息解释成所有相关任务成功。也不能通过忽略错误/取消语义来优化帧率。

## 15. 适合加入论文第二部分的研究问题

第一是共享驱动入口与映射归属的联合约束：即使 Client 提交格式合法的请求，也不能让它引用另一个 Client 的对象或借可信合成、导出接口获得未授权页。第二是任务完成绑定：已有 fence/cookie/epoch 如何在通知乱序、合并、重放和对象复用中保持正确。

第三是共享设备的故障影响范围：一个 Client hang 或 reset 后，其他 Client 的结果、映射、资源回收及错误通知如何处理。Sugar 的双 GPU 方案提供故障域分析参照，本项目仍可在单共享 GPU 假设下明确可保证的安全性、允许的可用性影响和恢复顺序。

这些是论文支持的设计方向；本轮未运行恶意多 Client、reset 压力或通知注入实验，未证明当前项目存在对应漏洞，也不据这篇论文宣称本项目已有完整机密计算安全证明。
