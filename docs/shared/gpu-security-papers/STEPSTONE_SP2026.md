# StepStone：经用户态 GPU 库触及内核驱动的模糊测试与可信 Proxy 边界

研读日期：2026-10-27。完整研读作者公开的 18 页论文，包括 meta-review、附录提示词、JSON schema 与参考文献；核对正式 DOI，并固定公共仓库完整树，定向静态阅读生成器、类型解析、Syzlang 转换、CUDA/OpenCL/Vulkan wrappers 和配置。本文是 GPU 驱动安全支撑研究，不是 CCA GPU TEE。未调用模型、构建、fuzz、复现攻击或操作实验板。未改运行代码，无新增性能测量。

## 1. 书目、全文与代码

| 项目 | 内容 |
| --- | --- |
| 标题 | StepStone: LLM-Based GPU Kernel Driver Fuzzing via User-Space Libraries |
| 作者 | Xiaochen Zou、Juefei Pu、Arrdya Srivastav、Jonathan Cox、Zhengchuan Liang、Yuan Tan、Xingyu Li、Yilin Zhu、Zhiyun Qian |
| 发表 | IEEE Symposium on Security and Privacy 2026，Crossref 页码 1–18 |
| DOI | [10.1109/SP63933.2026.00124](https://doi.org/10.1109/SP63933.2026.00124) |
| 作者入口 | [Zhiyun Qian publications](https://www.cs.ucr.edu/~zhiyunq/publications.html)，S&P 2026 条目链接论文与代码 |
| 实际全文 | [作者 PDF](https://www.cs.ucr.edu/~zhiyunq/pub/oakland26_gpu_fuzzing.pdf)，18 页、414,470 字节 |
| PDF SHA256 | `ecf9cc0d2a97eeb7f4582186a675b83b5afaad4e46041dd12fa12f674c7c84a4` |
| 公开代码 | [seclab-ucr/StepStone](https://github.com/seclab-ucr/StepStone) |
| 固定提交 | `9a2b74f46815d312f3490409964bc23ddb2bcd61`；完整递归树 9,459 项，未截断 |

## 2. 问题与对本项目的直接意义

GPU 驱动用少量 open/ioctl/mmap 等接口承载大量复杂功能，手写 syscall 描述成本高，静态分析又难恢复嵌套类型、函数指针表、对象依赖和值约束。无效输入会很早返回，难以探索驱动深层状态。

StepStone 改从 CUDA、OpenCL、Vulkan、OpenGL ES 的公开 API 文档和头文件生成 fuzzing 描述，经厂商用户态库间接调用驱动。它利用库自身完成一部分复杂编码与状态初始化，同时用内核覆盖率反馈寻找可达路径。

这对可信 ProxyRealm 的启发是：RMM 身份认证、私有请求快照、句柄归属和合法 GPUVM 都有必要，但它们不单独证明可信驱动没有内存错误。合法 API 序列也可能触发驱动漏洞；完整驱动在 TCB 内意味着需要明确其可信假设与可达攻击面，而不是把可信等同于已经验证无漏洞。

本篇不推翻项目既定模型。若驱动被假定正确，论文支持后续实现验证和 TCB 缩减；若希望容忍驱动局部缺陷，则须新增内部权限边界，并另行论证，不能仅靠 SMMU 映射授权声称能够承受 Proxy 被任意攻陷。

## 3. 研究目标与威胁边界

论文目标是更有效地寻找 GPU 内核驱动缺陷，不提供跨 Client 隔离、远程证明或恶意 GPU 程序的沙箱。其覆盖率反馈和 KASAN 报错是测试证据，不是程序安全证明，也不代表每个 warning 都是可利用的权限提升漏洞。

实验的 GPU、用户态库、内核与运行器都在测试环境内；GPU passthrough 用来让测试 VM 访问真实设备及捕捉崩溃，不是论文提出的 confidential passthrough。已知 CVE 被用作动机，不能记成本篇新发现。

## 4. 为什么选择库接口

库 API 将 ioctl 多路复用展开为功能明确的入口，头文件给出类型，文档给出 flags、依赖和参数语义。相较直接向驱动发送随机字节，这有利于走过初始化、创建对象和依赖关系所需的有效前缀。

但厂商库会提前过滤部分非法输入，造成假阴性。作者第 9 节明确将方法定位为 syscall fuzzing 的补充，不能用库接口覆盖高来证明原始 ioctl、mmap、并发错误及 Proxy 自定义协议均已覆盖。

文中将多种 GPU 库实现概括为闭源，适用于其选定厂商栈；Vulkan/OpenCL 是开放标准，也存在开放实现，不能将该概括写成所有实现的固有性质。

## 5. 描述生成流水线

每次只处理一个 API，将结果合入有状态描述表；其余模块尽量无状态，减少长上下文导致的类型遗漏。头文件解析器递归提取嵌套类型，两个辅助 LLM 分别检索 flags 与跨 API 资源依赖，主 LLM 生成中间 JSON，再由程序转换为 Syzlang。

为保持跨请求资源名一致，已有资源名随提示词提供。中间表去重避免反复定义；JSON 转换器处理同一种 flags 在结构字段与 API 参数中的语法差异。自动生成后仍有人工修订，不能将“通过编译”解释为语义完整且完全无人干预。

flags 值尽量采用文档枚举；非 flag 参数若只是范围约束，作者有意允许越界值，以探测错误处理。由此可见，语义有效前缀与恶意边界值应同时保留，严格照文档约束所有参数反而可能漏掉驱动缺陷。

论文采用 o1-preview/其他 o1 表述作为主模型，GPT-4o 作为辅助模型；其模型选择、文件检索和成本判断是作者当时环境，不构成对当前产品能力或价格的核验。

## 6. 库感知执行器与反馈

生成 syz_ 前缀 pseudo-syscalls，wrapper 把参数传给真实库函数，再由库触及驱动；KCOV 提供内核反馈，KASAN 捕捉内存错误。NVIDIA/AMD 实验通过 VFIO 将真实 PCI GPU 交给 QEMU VM，Mali 在 Pixel 6 设备上测试。

这里观察的是内核 basic block 覆盖，不是 GPU 指令、设备固件、GPU shader 或对象授权状态机覆盖。更多 basic blocks 表示探索范围扩大，不能代替权限、新鲜度、真实 fence 与回收状态的不变量。

## 7. 作者平台和实验设置

| 对象 | 配置 |
| --- | --- |
| NVIDIA | RTX 6000 Ada，open-gpu-kernel-modules 560.35.03；CUDA 12.6.1、Vulkan 1.3.239、OpenCL 3.0 |
| AMD | Radeon RX 7900 XT，ROCK-Kernel-Driver rocm-6.2.4；OpenCL、Vulkan |
| Mali | Pixel 6 / Mali-G78 MP20，Android 13、kernel 5.10.157；Vulkan、OpenGL ES 3.2 |
| 硬件资源 | NVIDIA 为 4×EPYC 7543、8 张 GPU；AMD 为 Ryzen 7 5800X、单 GPU；Mali 为手机，不具备跨厂商同资源可比性 |
| 覆盖率对照 | 每组 24 小时，对比可用的 SyzDescribe、KernelGPT、Moneta 描述 |
| 缺陷搜索 | 三家分别进行七天搜索；不是每家都发现新漏洞 |

NVIDIA 上 KernelGPT 无法以合理工作量补齐缺失类型，因此没有该对照结果；AMD 上 SyzDescribe 未能处理 drm_ioctl 的表式分派，因此也未运行。缺失结果不能画成零覆盖的已完成实验。

Moneta 对照只使用其手工描述文件，没有启用完整 snapshot/rehost、record/replay。作者明确称两者互补，不能把图 11 改写为 StepStone 全面击败完整 Moneta 系统。

## 8. 定量结果与书面不一致

作者报告 NVIDIA 覆盖率约为对照数倍，AMD/Mali 约两倍；各图是具体 24 小时轨迹，没有给出足以推导所有 GPU 稳定收益的置信区间。消融中 base 约 15k blocks、加依赖约 20k、完整方案约 25k，flags 恢复在所测 CUDA 环境下贡献大于单独依赖恢复，不能推广为所有库的一般定律。

七天共报告 11 个新缺陷，全部来自 NVIDIA。表 2 分为 CUDA 7、Vulkan 4，其中包括 GPF、NPD、OOB、UAF 和三个 warnings；后文又写 CUDA 相关 8、Vulkan 相关 3，口径是否改变未解释，本文保留差异，不自行统一数字。

库描述质量由四位研究者抽查每库 50 个 API。表中 0.3%、0.87% 等比例不可能直接对应 50 项 API 的整数计数，可能使用参数/字段等不同分母，但正文未充分明确。可引用原表百分比，不能自行解释成每 50 个 API 中恰有某个数量错误。

作者称每约十个 API 有一项语法或语义错误，缺失类型有时改为 void，然后修至可编译再实验。这既说明自动化价值，也表明描述可能失去语义；不能将模型输出未经验证地当成完整接口规范。

生成每 API 约 30 秒至两分钟，每库约两至七小时。约 $1.3/API、总计 $1,200 是作者模型环境下的成本；更换后续模型可降至约 $200 是估算，本文未重新测量或核验定价。

## 9. mmap 生命周期案例的证据强度

案例是 nvidia_mmap_helper 使用已释放的 mmap_context→alloc，先在检查 num_pages 时触发 UAF read；同一失效对象还含用于建立用户映射的物理页信息。它揭示“检查范围时使用的元数据本身已失效”这一关键模式。

正文进一步讨论通过操控释放后对象导致物理页映射被污染的潜在高风险后果；它是作者影响分析，本文没有运行 exploit，也不将每个普通 UAF read 都宣称为已验证任意物理内存访问。论文只说部分缺陷获 CVE，未逐项提供可核对编号，不补造编号或修复状态。

对项目可迁移的是元数据、引用和映射生命周期一起维护：Client 身份正确不能使一个已释放 BO、页列表或 native fence 自动恢复有效；在授权检查到实际使用之间，必须由既有强引用、锁或冻结快照保证对象仍是同一实例。

## 10. 固定公开实现：已确认的路径

仓库分 StepStone-generator 与包含 syzkaller 的 StepStone-fuzzer。定向阅读 library_controller.py、structparser/code_parser.py、syzlang/helper.py 及 aux 类型/API 转换、assistant.py、三个 executor 头、NVIDIA 描述和示例配置；没有对 9,459 项逐文件全面审计。

代码确有按 API 处理、资源提示、类型数据库遍历、JSON 校验/修订、去重及 Syzlang 输出。helper 的去重按名称保留先前定义，没有自动证明同名不同布局一致；它生成的 header 固定 meta arches 为 amd64，不能仅凭 const 文件列出其他 arch 就认定 Arm64 生成流程已验证。

CUDA/OpenCL/Vulkan wrapper 多数直接调用真实库。CUDA 非 NVIDIA 构建宏会生成空函数，OpenCL/Vulkan 部分条件分支也有 EMPTY wrapper；因此接口名被枚举或程序成功运行，不足以证明对应路径实际触及驱动。复现需要同时检查编译宏、库加载、返回码和 KCOV 增量。

生成器要求预配置辅助 assistant 和文档；当前 prepare_assistant_session 明写 gpt-4-turbo，与论文辅助 GPT-4o 表述不同，是否改动模型需在复现时记录。README 示例并不自动提供论文原始 assistant 文档、所有运行历史和成本证据。

## 11. 静态观察到的复现边界

library_controller.py 的 analyze 在 join_syzlang_json 与 refer_syzlang_context 都为 None 时建立空表，却未在该分支初始化随后使用的 parsed_api_hash_table。初始化后调用是否绕过此分支取决于调用配置；这是固定代码的静态条件观察，未运行成 CLI 失败证据。

初始生成重试耗尽后记录 skip，但随后仍继续处理 response；异常路径和 new_object 合并没有提供可据此认定所有失败 API 都被可靠排除的证据。不能因为生成命令返回，就统计全部请求 API 已成功建模。

tutorial/cuda.cfg 为 linux/amd64、单 VM、procs=1、sandbox bypass，并忽略一种递归锁警告；这是公开示例，不能当成论文所有实验的统一配置，也不能直接证明跨线程/多 Client、非特权进程或 reset 竞争已经充分探索。部署脚本可把 assert 转 panic 或忽略，缺陷分类与覆盖可比性需要记录该选择。

本轮只读源码与配置，没有调用模型、安装依赖、构建镜像、启动 VM 或 fuzzer；这些条件不足不等于本篇新发现的驱动漏洞，也不回溯否定作者实验。

## 12. 与项目其他论文的关系

PORTAL/CAGE/ACAI 主要规定可信设备访问与隔离职责，PhantomMap 检查实际页及映射生命周期，StepStone 检查实现这些职责的复杂驱动可能出错的输入路径。它不代替前者，也不是对其安全假设的直接攻击。

AvaGPU 的可用性监测、MOLE 的 GPU 内 MCU/固件边界、StepStone 的 CPU 内核驱动边界是不同问题。签名固件不能证明 CPU 驱动无 UAF；RPC 授权成功不能证明设备固件可信；fuzz 未报错也不能证明任务完成事件真实。

## 13. 适合项目的验证方向

可按真实 Client API→RPC→Proxy 操作→可信驱动入口建立可达关系，再围绕已有对象、GPUVM、private snapshot、native fence、cookie/epoch 与持久 IRQ 的生命周期生成有效前缀和非法后缀。重点包括提交后关闭、并发释放/重映射、旧句柄复用、错误完成、取消/reset 与晚到回调。

测试 oracle 应包含受害 Client 正确性、拒绝跨 Client 引用、停止访问后的回收和可信终态一致性，不能只数 crash 或 block coverage。用户态库测试有助生成复杂合法状态，RPC/原始接口测试负责库会提前过滤的输入；两者覆盖不同边界。

上述是研究建议，没有在本轮实施。可信 ProxyRealm 统一控制 SMMU、RMM 认证原始 Client、建图时完成 IPA→HPA 授权并合成为直接合法 HPA Stage-1 的项目假设保持，不因测试工具的 PCI/VM 设置而改变。

统一记录：StepStone 全文、正式书目与固定实现定向静态研读｜项目 glmark 前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无 fuzzer/模型/硬件 run-id 或新增 PASS；证据位于 build/cca-gpu-followup-20261027｜保留为可信驱动验证支撑，复现边界与作者结果分别记录。
