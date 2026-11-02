# TGS-048｜Milkomeda：移动 GPU 调用检查、可信入口和共享驱动攻击面深读

研读日期：<date start="2026-10-27" />。状态：15 页论文全文、作者构建指南、固定版本核心补丁与选定用户态代码已阅读。未构建、刷写或运行攻击；未改运行代码，无新增性能测量。

## 1. 论文与来源

**Milkomeda: Safeguarding the Mobile GPU Interface Using WebGL Security Checks**，Zhihao Yao、Saeed Mirzamohammadi、Ardalan Amiri Sani、Mathias Payer，ACM CCS 2018。正式 DOI：[10.1145/3243734.3243772](https://doi.org/10.1145/3243734.3243772)。[作者研究组公开 PDF](https://hexhive.epfl.ch/publications/files/18CCS2.pdf)由 HexHive 出版列表明确链接；另有 UCI 作者出版记录交叉确认。

全文存于 `build/cca-gpu-followup-20261027/milkomeda.pdf`，SHA256：`d0eeb1e9f44eb6d043d30b67e50c3431761409eec207c9c1619acdac19cf5c55`。本条是原库 TGS-048 的完成，不重复算新增论文。

## 2. 问题定位

Android 应用既可以调用 OpenGL ES，也可以直接接触 GPU 驱动的 ioctl/mmap 等入口。驱动规模大、状态复杂，一项合法应用权限可能让攻击者向高权限内核提交复杂输入。只隔离 CPU 应用地址空间，并不能消除这个入口。

浏览器 WebGL 已积累参数、状态和 shader 检查，但普通移动图形调用没有自动获得同样保护。Milkomeda 的贡献是复用这些检查，并用进程内受保护 shield 执行它们，避免每次 OpenGL 调用都跨进程通信。

它解决的是“恶意应用如何攻击可信系统的 GPU 接口”。它不是 CCA Realm 设计，也不声称保护应用免受恶意宿主内核读取。

## 3. 威胁模型与可信基

攻击者完全控制应用进程中 shield 之外的 Java/native 代码及普通库，可使用 JNI、直接系统调用或 OpenGL ES。系统内核可信，负责创建 shield、控制 CPU 页表和驱动入口；启动时应在不可信应用代码执行前正确建立保护。

可信基包含整个相关内核、shield 内检查器、图形库及它们依赖的库，不能把新增约 500 行内核代码当成总 TCB。可信库或检查器本身被攻破，也不在“任意驱动漏洞均可安全容忍”的证明之内。

论文没有建立远程证明、RMM Client 身份认证、物理设备绑定或多 Realm 机密计算协议。移植其思路时必须重新说明这些职责由谁承担。

## 4. 四类检查

| 检查类别 | 论文机制 | 能说明什么 |
| --- | --- | --- |
| 数值 | 枚举、尺寸、非负值、安全算术和缓冲范围 | 阻止部分非法参数与溢出组合 |
| API 状态 | 按 graphics context 记录对象创建、绑定和调用历史 | 不能只按单次参数判断合法性 |
| shader | 复用 ANGLE 的源码验证与转换，禁用绕过验证的 shader binary 入口 | 是受限接口的加固，不是通用 GPU 二进制完整验证 |
| 平台规避 | 为 GPU/OS 已知缺陷启用特定 workaround | 依赖检查版本和平台匹配 |

例如纹理上传不仅检查 width/height，还检查对象是否存在、目标类型、层级和格式是否匹配，并在实际执行时更新可信状态。这个状态必须属于正确的 graphics context，且不能由调用方任意修改。

## 5. 检查本身需要保护

把检查函数与恶意应用放在普通进程内，攻击者可跳过函数、修改其状态或直接调用驱动。论文因此要求：驱动仅接受 shield 内线程；只能从固定 call gate 进入；shield 代码、全局数据、栈和堆不能被外部篡改。

shield 采用同进程的两套 CPU 页表根。普通根中保留一段不可访问 VA，可信根可访问该段，其余地址基本一致。原型保留 1 GB 虚拟空间，实际后备页按需分配；这不是每个应用必占 1 GB 物理内存。

## 6. 一次调用的控制流程

普通 stub 将 API 编号和参数交给进入 syscall。可信内核保存寄存器、选择独立安全栈、设置固定 PC、标记线程处于 shield 并切换页表。call gate 执行对应检查，通过后才调用真实图形库及驱动；退出 syscall 恢复普通页表、TLB、线程状态和寄存器。

驱动的 open、ioctl、mmap 等入口检查内核维护的线程状态。线程调度也必须选择正确页表并在需要时清除 TLB，不能只在首次进入时设置一次权限。多个线程进入 shield 时使用不同栈，检查器状态的并发语义仍取决于具体图形 context 和实现。

论文还禁用 `glDebugMessageCallback`，避免攻击者注册回调在 shield 权限下执行，并要求 shield 执行期间不交付信号。这里讲的是 CPU 进程内的异步控制流安全，不能直接等同可信 GPU job 完成通知。

## 7. 指针、快照与检查使用一致性

对于安全敏感指针内容，论文沿用 WebGL 的 shadow copy：复制后对同一副本检查并执行，防止其他线程在检查之后修改输入。其优化是只复制安全敏感内容，例如纯纹理像素在论文假设下只改变图像，所以可不复制。

这个豁免不能直接用于 ProxyRealm 的任意共享缓冲。如果一个 payload 含 GPU 指令、地址、句柄、描述符或会被固件解析的控制字段，它可能改变权限或控制流，必须重新分类。当前项目已有私有请求快照，研究重点应是它覆盖了哪些间接输入和执行时读取，而不是再次建议“新增一个快照”。

## 8. CheckGen 与兼容性

Chromium 检查分散于反序列化层和检查主体。CheckGen 利用 OpenGL ES 接口定义和模式匹配移除 IPC 解包代码，将其改造成接收普通 API 参数的检查层，并用 Chromium component build 输出共享库。

WebGL 与 OpenGL ES 不是完全相同的接口。原型为兼容应用重新允许 client-side vertex arrays，并接受 `GL_FIXED`；论文认为这些调整不造成安全问题，但没有给出覆盖所有驱动的形式化证明。移植或升级检查器应记录删改规则及其依据，不能把“自动生成”当成语义完整性证明。

## 9. 论文原型

平台为 Nexus 5X、2 GB RAM、4 个 Cortex-A53 加 2 个 Cortex-A57、Adreno 418，Android 7.1.2 / LineageOS 14.1。为隔离可信依赖，shield 内加载独立图形库、检查器和 LibC 实例；需要在不可信库之前初始化，原型绕过 Zygote 重新启动应用。

这些依赖副本会增加内存与代码 cache 压力。论文的未来工作包括共享只读库代码、优化启动及支持更广框架；不能把设想的次级 Zygote、OpenCL/CUDA 支持当成当前已完成。

## 10. 安全实验的证据等级

作者整理 64 个 GPU 驱动 CVE：47 个权限提升、13 个未授权访问、3 个内存破坏和 1 个 DoS。其中 45 个有足够材料供分析；作者认为其直接驱动入口被 Milkomeda 阻断。实际取得并运行的 PoC 为 3 个，即 CVE-2016-2503、CVE-2016-2504 和 CVE-2016-2468，在未保护路径触发内核崩溃。

因此不能写成“运行了 45 个 exploit 全部防住”，也不能把入口阻断当成所有合法 OpenGL 调用组合均安全。论文明确定位为 mitigation：已知检查和状态约束可以阻止部分未知攻击，但可能漏掉零日漏洞。

## 11. 性能结果及适用范围

| 项目 | 原文结果或条件 | 正确解释 |
| --- | --- | --- |
| 五个图形 benchmark | 各运行 6 次，去掉每次最初 100 帧；B5 从 27 个 cube 增为 64,000 个 | 负载规模和预热条件不能省略 |
| 图形 FPS | 原本达 60 FPS 的负载仍达 60，较重负载接近 native | 受显示上限影响，不证明零开销 |
| CPU 利用率均值 | 15% → 26% | 增加 11 个百分点，按原值约增加 73.3% |
| 多进程对照 | 仅实现约 30 个 API，比较若干调用，3 次运行 | 不是完整替代系统的端到端对照 |
| 该对照 API 延迟 | 比 Milkomeda 平均增加 440% | 约为 5.4 倍调用延迟，不是整个应用慢 5.4 倍 |

检查、两次 syscall、寄存器/页表切换及 TLB 操作都有成本。论文比较了无保护检查配置以拆分来源；这有分析价值，但无保护配置不能被当成同等安全基线。本轮未重测，也不将这些数值换算成本项目 glmark 提分。

## 12. 公开 artifact 与固定版本

[总入口](https://github.com/trusslab/milkomeda)固定 `a9c2485f7320054b65d35aae74639844afd237b3`，完整 tree 只有 README、网站配置和库清单，属于构建文档，不是完整实现仓库。实际实现分布在多个 Android/Chromium 仓库。

本轮固定并核验：[kernel](https://github.com/trusslab/milkomeda_bullhead_kernel/tree/cb8ea7a35b2c6187a0a827cd7e94ae25bca377a9) 的完整 tree 与核心新增补丁；[frameworks/base](https://github.com/trusslab/milkomeda_bullhead_base/tree/3632418edacc876dece18ec8afad3e4202525e6c) 的完整 tree、`shield.cpp`/`shield.h`；[CheckGen](https://github.com/trusslab/milkomeda_checkgen/tree/72284244dac0c2ddd2766dbcf3d89208ef096af8) 的固定提交与 `gles_patcher.py`。未审计所有 bionic、native、jemalloc、固件和闭源图形库，未构建或运行。

内核可见 `secure_pgd_mode`、独立栈分配、固定 entry/寄存器保存恢复、驱动入口拒绝和页表/TLB 切换，支持论文主要机制的实现存在。驱动过滤条件限于已启用 secure PGD 的进程，不能泛化为系统上所有进程均自动受控。`destroydom` 仍是 TODO，初始化与 teardown 有待检查注释，不能由这组静态阅读宣称完整生命周期已验证。

`shield.cpp` 还存在先加载库、首次 GL 路径直接调用，再进入 bottom-half 激活 domain 的阶段性初始化；这与论文“在不可信应用执行前保护已建立”的安全表述需要进一步核对实际启动顺序。本轮只报告观察到的差异，不凭局部文件直接认定可利用绕过。CheckGen 使用 Python 2 语法、硬编码开发路径、符号匹配和手工例外；作者也明确称其尚未生产可用。

构建指南要求旧 Ubuntu、Nexus 5X、大量存储、预编译库及手工修改库依赖；README 链接的 Chromium 仓库本轮 API 返回 404。指南还要求 SELinux permissive、每次运行后重启，并承认扩展及平台专属 API 检查未移植、启动偶发失败。这些是复现及安全集成限制，不否定论文问题的重要性，也不等于本轮已证实系统漏洞。

## 13. 与 CCA / GPU TEE 主线的关系

PORTAL/CAGE/ACAI 主要回答高权限宿主之外如何建立可信 GPU 访问；Milkomeda 补充可信服务如何处理恶意调用者。一个 ProxyRealm 可以受到 CCA 保护，却仍需要正确解析和约束 Client 输入。

PhantomMap 检查最终实际物理页；Milkomeda 检查 API 参数与状态。两者保护的层次不同，合法 HPA 映射不能自动保证驱动解析器安全，API 参数合法也不能证明最终物理页确属该 Client。MOLE 进一步提醒，可信 CPU 检查层还不能代替设备固件边界。

## 14. 对本项目的具体研究建议

保持既定假设：可信完整驱动运行于 ProxyRealm，RMM 认证原始 Client，可信映射阶段验证归属/HPA/权限/生命周期，运行时保护实际页表、root、MMIO 和固件。硬件是实验载体，不据旧手机能力否定该模型。

在这个模型下，值得补充一张覆盖实际 RPC/ioctl 的入口表：每个命令接收哪些间接输入，依赖哪个 Client/context 状态，在何时完成授权、快照和状态更新，以及失败是否回滚。已有 RMM 身份、独立 GPUVM、私有请求快照、真实 fence 和 cookie/epoch 应直接进入这张论证表。

完整驱动既然属于 TCB，本文不建议未经论证地把它拆出 TCB；更实际的增量是减少可达入口、检查跨 Client 句柄组合和取消/reset 竞争，并把调试、兼容、导入导出与错误恢复入口纳入同一策略。对不可信输入可以拒绝，但拒绝路径不能意外建立映射或发布成功完成。

## 15. 可以验收的性质

在正常请求和并发恶意请求混合时，检查和执行应使用同一组可信输入及对象引用；另一个 Client 的合法句柄不能在错误 context 中生效；对象关闭与取消不能令状态验证跳过；调试或兼容入口不能绕过 RMM 绑定的 Client 身份。

这些是由论文引出的项目研究条件，本轮未做硬件测试，未证明当前存在相应漏洞，也未证明已经覆盖全部入口。实验应同时记录拒绝原因、受害者正确性和恢复状态，不能只统计攻击请求返回错误。
