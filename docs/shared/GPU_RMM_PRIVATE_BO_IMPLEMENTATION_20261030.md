# RMM 管理的 Client 私有 BO 与 GPU 页表

目标：控制页继续由 Proxy 分配并通过 RMM 授权共享；业务 BO 在 Client 内分配和写入，只登记 GPU 使用授权，不建立到 Proxy 的 CPU 映射。Proxy 保留 DRM/驱动服务、资源描述与调度建议；RMM 维护真实对象归属、受保护 GPU 页表及实际执行权限。

本文是实施记录，不是已实现保证。既有完整 Proxy 可信基线仍见 [CURRENT_BASELINE.md](CURRENT_BASELINE.md)。保护域与设备视图沿用目标平台假设，软件模拟结果不视作真实硬件 GPC 证明。

**当前保留版本：DA RMM＋ED Client＋原DX runner，最新纯对照933，整体目标未完成。** 最新FP仅做完成观察分段诊断，完整720p933→诊断936（+3／+0.32%），已撤下并核验恢复DA／ED；没有新增保留提速。1000门槛FAIL，多Client和攻击验收仍缺，当前状态以[基线入口](CURRENT_BASELINE.md)及本文末节为准；下文保留各历史阶段当时的结论。

当前可运行路径如下；后面的早期阶段记录保留当时状态，不应把其中“正常提交尚未接通”等描述当作当前实现：

1. **控制共享**：Proxy提供控制池，经RMM认证通道及授权后共享给Client；RPC传递IOCTL参数和不透明对象句柄。
2. **私有数据**：Client本地BO分配器分配、初始化和映射数据页；RMM从真实调用Realm及RTT解析页面，不接受自报HPA，阻止通过共享接口增加Proxy CPU别名。NC/驻留优化仍由RMM约束实际属性和生命周期。
3. **真实页表**：Client授权精确VM_BIND范围，Proxy驱动处理对象与GPUVA元数据并转发授权；RMM消费授权、创建实际GPU页表并控制真实根。Proxy导入对象不持有Client数据backing或CPU映射。
4. **受控启动**：Client处理输入副本和本地依赖，Proxy接纳精确任务；RMM执行就绪检查、缓存交接、受保护命令发布及启动。Proxy原始GPU MMIO已经交权，不能通过根配置或门铃绕过可信管理器。
5. **可信完成**：RMM检查真实设备/固件状态，完成必要的挂起或停止、AS禁用、缓存归还与退休后，Client才完成本地fence；Proxy回复、中断或等待时长均不能代替此判定。

这些机制已有单Client计算/图形运行和源码模型证据；恶意Proxy/Client、并发销毁及多Client硬件验收仍缺失。Realm间CPU页归属依赖受保护RTT/Stage-2，不能把GPT的Realm PAS误写成每Client独立权限；实验平台运行也不证明实体GPT/GPC保护已得到完整验证。

## 必须同时完成的边界

| 要求 | 实现位置与验收依据 | 当前状态 |
| --- | --- | --- |
| 控制页继续共享，数据页由 Client 分配 | Client BO 分配/mmap、协议、Proxy 无数据 backing | 正常私有DRM BO/mmap/元数据导入和共享控制已实际跑通计算与图形；私密性攻击验证待完成 |
| Client 私有页面登记，不接受自报 HPA | RMM 用实际调用 RD/RTT 解析、固定 backing；拒绝共享页 | 已实现并经正常私有工作负载使用；模型覆盖归属/共享拒绝，实体越权攻击待完成 |
| RMM 创建硬件格式的 64 位 Stage-1 PT | RMM 自有表池、身份/范围/权限检查、实际描述符检查 | 实际GPU已使用该路径完成计算与完整图形校验；双Client根/PTE有模型，实体多Client与攻击待完成 |
| Proxy 不能扩大 Client 的映射或提交权限 | Client 精确映射授权、Proxy 句柄转发；保护真实根和启动 | 精确授权、MMIO交权、可信固件/任务及元数据服务已实现，正常GROUP_SUBMIT已实际运行；拒绝绕过有源码模型，不能替代恶意Proxy实体攻击 |
| 数据不可通过控制页或其他设备旁路导出 | GPUVM 内部映射、固件接口、MMIO 与其他 DMA 审计 | 受保护arena/ring、Client/context分区及旁路拒绝已实现并有模型；正常任务运行不证明所有导出攻击被阻断，实体攻击仍未验收 |
| 撤销与退出不产生旧映射复用 | 引用、可信失效/停止、RMI teardown gate、清理顺序 | 停止/缓存归还/退休/死亡Realm回收已接线；BS及CA正常退出VM0/0、日志回收、解绑和资源恢复通过；恶意中止、并发销毁和旧映射实体攻击待验收 |
| 功能、性能和攻击负例 | RMM单元/构建、Guest构建、720p后扩展硬件回归 | 当前保留DA＋ED、最新纯对照933，FP诊断已撤下，最新测试见末节；单Client计算预热/完整33场景及CPU SIGNAL/eventfd/basic已有实际证据。validation含已知数值失败，1000门槛未通过；真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API、多Client及实体攻击未验收 |

## 设计约束

- RMM 对象中的 owner 必须来自执行 REC 的 RD；服务端来自已建立的可信 xshm channel，不接受 payload 自报的 Client ID。
- Client 物理页不进入 Proxy RTT。知道 HPA 不构成 CPU 访问权。GPT 的 Realm PAS 不表达每 Client owner；CPU Realm 间隔离仍依赖受保护 Stage-2。
- 不复用旧“Proxy IPA 翻译即可代表原 Client 授权”的逻辑。RMM 私有 BO 记录持有原始 Client 的页与授权。
- GPU PT 使用与当前 Panthor Stage-1 相符的 4 KiB、64 位描述符；不是已有 RK v2 外设 IOMMU 的 32 位 DT/PT。
- 修改后生效的真实表、root、固件上下文与启动门铃不能让不可信 Proxy 任意改写。只迁移建表不构成完整实现。
- 已登记数据页禁止再经 xshm 建立 CPU 共享别名。数据注册、RTT 变更与共享操作使用同一 policy gate。
- 页面被 GPU 使用期间拒绝源页 teardown。失效或停止失败时保留引用并隔离，不能依赖 Proxy 的完成声明释放数据。
- 初始接口不接受寄存器脚本、服务回调、任意 HPA 或任意页表根。需要设备操作时由可信固定后端执行。
- 激活接口只接收上下文句柄和非零 AS 槽位，不返回根 HPA。根只交给可信后端；槽位不能被另一个上下文直接覆盖。当前后端要求已交权且 MCU/GPU 停止；安装失败的上下文隔离并保留引用。执行能力位仍为零。
- 内部控制 BO 与业务 BO 分开；内部可写同步页不能未经验证就成为权威完成/回收依据。

## 当前证据与工作区保护

2026-10-30 开始前已读取环境手册、产物管理、当前基线与共享测试 skill。`apply-local-patches.py --check` 退出 0；各上游补丁状态均为 APPLIED。已有 Guest/RMM 未提交修改的初始 diff 已保存在控制机忽略目录 `build/rmm-client-bo-20261030/original/`，本任务不回退或覆盖这些修改。

旧共享模式的 RMM `handle_rsi_opencca_gpa_to_hpa()` 为调用 Realm 翻译并取得 lease，真实 GPU PT 仍由 Guest `io-pgtable-arm.c` 创建；新私有模式使用下述 RMM 自有表池。已有 `opencca_iommu` 服务处理 RK v2 外设页表，不能直接当作 Mali GPU PT 使用。

## 已落地的代码

以下按实施阶段保留接口演进，早期“未接通/未部署”描述属于当时快照；当前范围以上方进展表及末节实体证据为准。

- [RMM 私有 BO/PT 核心](../../opencca/tf-rmm/runtime/core/opencca_gpu_private.c)：按实际 owner/service 保存注册页、保护权限与映射生命周期；使用 RMM 自有表池建立四级页表；预检失败时回滚未激活上下文的新空表，避免失败请求持续吃掉表池。
- [RSI 入口](../../opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c)：调用 REC 的 RD 作为 owner，从已认证 channel 解析 GPU service；私下复制 IPA 列表并查 RTT，拒绝共享页、重复登记和已有 GPU/其他 DMA 引用；不接受 Client 自报 HPA。Proxy 的 INSPECT/SERVICE_MAP/UNMAP 同样从实际调用者和 channel 解析 Client，且要求已完成控制交权。私有接口 ABI 为 2，VERSION 声明登记、建表、服务映射、精确映射授权、控制交权、停机 PT 安装、固件快照封存、运行映射、MCU 启动、可信全局配置、受保护控制内存、Client 组资源、组导入校验、受保护 ring、任务暂存、停止态硬件任务准备、Client 就绪/数据缓存交接、受控启动、可信停止、CPU 缓存归还、任务退休和可信完成观察、映射核验、多队列批次暂存、按 BO 原子回收、逐成员进度、Client前缀发布和动态堆事件/扩容、可信CPU隐藏驻留与清零后恢复能力（536870907 | 536870912 = 1073741819），Client 任务执行能力位 4 保持清零。
- [Client 内核私有分配器](../../Linux-Guest-GPU/drivers/char/realm_gpu.c)：零初始化分散页、分批登记、WB 用户映射，禁止 COW/执行/越界映射；通过 fd 和 VMA 持有 backing。只有 RMM 完成对象撤销后才清零并释放；在用对象保留，并在后续诊断操作时有界重试。诊断 BO_DESTROY/BO_APPEND 不能绕过内核管理的对象生命周期。
- [Guest UAPI](../../Linux-Guest-GPU/include/uapi/linux/realm_gpu.h)：`REALM_GPU_ALLOC` 返回 Client 本地 fd 与 opaque BO handle；`REALM_GPU_CALL` 是特权诊断入口。CPU backing mmap 不是 dma-buf，不会自动分享给 Proxy。内核消费者可复用 [内核接口](../../Linux-Guest-GPU/include/linux/realm_gpu.h)。
- [Guest 运行探针](../../GPU-SFTP/tests/realm-xshm/realm-gpu-private.c)：默认 513 页，覆盖零初始化、多批登记、mmap 范围和权限、授权保留 context/取消后旧句柄拒绝、真实 RMM MAP/UNMAP、关闭 fd/VMA 后保留 backing；`drm-selftest` 经过真实 DRM ioctl/RPC/native VM_BIND，检查 mmap、分批绑定、局部重映射、8 操作批量绑定及非零 BO 偏移、GEM/VMA 生命周期。**两种探针都只编译通过，尚未在 Realm 执行。**

## 原生驱动接线与实际边界

Client 的只读启动参数 `panthor_client.rmm_private_data=1` 选择私有数据模式，默认关闭。启用后，打开 DRM 会话要求本地 RMM 的六项非执行能力及 Proxy 的 `RMM_MEMORY` 协商能力；缺失时失败，不回退共享 payload。RMM 还要求服务实际完成 MMIO 交权，才接受 BO/context 创建；只有版本能力而服务仍拥有原始 MMIO 时，返回 STATE/EBUSY。不能以“暂不执行任务”为由绕过此边界。

| 正常 ioctl | 私有模式实际代码路径 |
| --- | --- |
| VM_CREATE | Client 创建 RMM context，VM_IMPORT 只转发句柄；Proxy 以实际通道检查归属，原生 GPUVM 不分配自己的硬件页表 |
| BO_CREATE | Client 分配零初始化分散页并向 RMM 登记；BO_IMPORT 仅转发句柄、大小和标志 |
| Proxy 导入 BO | 原生 GEM 只保存元数据；不分配共享 payload，不 pin/映射 Client backing；拒绝 mmap、vmap、SG、pin 和 dma-buf export |
| mmap | Client 直接映射自己的 WB 数据页；禁止 COW、执行和越界；VMA 独立持有 backing |
| VM_BIND | Client 先取得精确 MAP 授权；保留原生 GPUVA、依赖和对象引用，在实际执行绑定时按最多 512 页批次由 RMM 消耗授权并建表；UNMAP 同样进入 RMM |
| GROUP/实际启动 | 正常 DRM GROUP_CREATE/DESTROY 已接 RMM 预留资源和 Proxy 元数据导入；RMM 核验实际 Client、context 和 stream 数。私有组拒绝走原生提交/状态查询路径；ring 分配/映射及 RMM 私有任务 wrapper 暂存已完成；已增加诊断用的停止态 AS/CSG/CS 与 ring 准备，诊断可信 START 已接，正常 DRM 提交仍未接通。私有 GPUVM 拒绝普通 Proxy BO，激活返回 EOPNOTSUPP，不能执行 GPU 工作负载 |
| CLOSE_SESSION | 原生清理后退休 Client context，再有界重试已关闭私有 BO 的可信撤销；未确认安全的 backing 继续保留 |

入口为 [Client 前端](../../Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c)、[Proxy 后端](../../Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c)、[原生 GEM](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.c)、[原生 MMU](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c) 与 [RPC 协议](../../Linux-Guest-GPU/include/linux/panthor_vmshm.h)。原共享模式用于已有基线和回归，不作为私有模式的成功回退。

## Client 精确映射授权

登记 BO 不再直接赋予 Proxy 服务映射权。每次私有 VM_BIND 的 MAP 操作，Client 在共享请求发送前，通过自己的 RSI 调用取得一次性授权，绑定实际 owner、context、BO、BO 偏移、GPUVA、页数与读写/执行/缓存属性。Proxy 只能转发授权句柄，不传入 HPA；RMM 按授权内保存的 BO 查 backing，并要求后续批次严格连续且参数一致。已经消费的前缀和完整授权均不能重放。

授权先持有 BO/context 引用，再交给原生绑定操作。同步绑定返回后释放未使用授权；当前私有同步/异步 VM_BIND 共用 Client 本地有序 worker：先等待本地依赖，再申请授权，以单操作同步 RPC 调用原生绑定；不向 Proxy 转发本地 syncobj 句柄，也不使用远端异步依赖路径。RPC 返回成功后还要由原 Client 核验实际映射，才能成功完成本地 fence。请求失败时 Client 取消已经发出的授权；此前实际建立的映射继续持有 backing，不因取消而释放。每个 context 最多 32 个待处理授权，全局最多 128 个；可信整设备 RELEASE 同时退休这些授权。

原生 DRM GPUVA 的拆分/重映射流程已核对：旧映射清理之后，`__drm_gpuvm_sm_map()` 对请求的完整新范围执行一次 MAP 回调，因此可以按原请求顺序分批消费授权。实际 Realm 并发、异步和重映射运行仍待验证。服务 UNMAP 尚仅约束真实 Client/context，恶意服务仍可破坏其可用性；映射授权不证明任务、依赖或完成事件完整性。

RPC ABI 升为 3，两端须配套。为保持 476 字节槽位及原有 8 操作/8 同步上限，将线上 BO 偏移编码为 32 位 4 KiB 页编号，并将同步索引/数量编码为 16 位；操作仍为 40 字节，整个绑定请求为 472 字节。Client 拒绝未对齐或不可编码的偏移，Proxy 恢复成 64 位字节偏移；可表示的 BO 偏移小于 16 TiB，高于当前 512 MiB BO 上限。旧版会话因 ABI 不符而拒绝。

同时修正 Proxy 的私有 BO 校验：私有对象没有共享 payload，不再经过旧 payload owner/handle 解引用；仍要求 BO 和 VM 的私有模式匹配。共享 BO 保留原 payload 归属检查。

## 可信控制交权与停机页表安装

新增 `SERVICE_ISOLATE`（操作 17，全零输入）。只有实际指定并已 claim 的 GPU service RD 可以调用；调用者不能自报另一个 Realm 的身份。RMM 先关闭新 MMIO 授权/claim，再撤销并失效服务的完整 GPU MMIO Stage-2 alias，随后运行既有可信复位后端、检查复位完成。成功后释放旧 GPU lease、退休旧私有上下文，进入 `MEDIATED` 状态；原服务身份继续用于经认证 channel 的对象管理，但不能获取原始 MMIO。

交权失败时保留引用，并保留禁止原始权限恢复的标志：普通 Host RESET、服务 claim、MMIO grant 都不能恢复原始访问。必须重新完成可信撤销和复位才能进入 MEDIATED；完整 RELEASE/owner teardown 才结束此服务实例。重复成功交权不重复复位，也不撤销交权后新建的上下文。RMM 用这一实际状态约束私有登记和服务映射，不仅检查 Proxy 的声明。

交权入口见 [设备状态核心](../../opencca/tf-rmm/runtime/core/opencca_gpu.c)和[受锁适配器](../../opencca/tf-rmm/runtime/rsi/opencca_gpu.c)。它是显式 bring-up/验证接口，不会由旧原生驱动自动调用；调用前必须停止并解绑旧 GPU 驱动，否则后续原始 MMIO 访问会产生 fault。当前尚未把原生驱动改成在交权后通过完整的受限接口提供 GPU 服务。因此，新私有 DRM 路径仍不能端到端运行；旧共享默认模式不自动切换。

页表安装由 [RK 固定后端](../../opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c)实现：只接受 RMM 内部传来的根，不提供任意寄存器脚本或 HPA 输入的 RSI。检查非零 AS、硬件存在位、48 位 VA/至少 40 位 PA 格式、根对齐/范围、MCU 关闭和 GPU 非活动；AS 0 留给未来可信固件。固定执行全范围 LOCK/FLUSH_MEM、写根/内存属性/翻译配置、UPDATE 和配置回读。映射变更按受保护根找到唯一硬件槽，再执行 LOCK/FLUSH_PT；操作有界超时，不能由 Proxy 自报完成。

当前只设置 RMM PTE 使用的 NC/WB 属性，其余索引设为 fault；不启用 MCU、不写门铃、不启动命令流。安装失败即使已经写入部分寄存器，也由核心隔离上下文并保留所有 backing，直到可信整设备撤销；逐上下文诊断停止已接后文 TASK_QUIESCE，安装失败的隔离状态仍要求整设备复位。RMM 自有表池的真实设备可达性、PAS/硬件访问约束和 GPU 真正取表均未在板端验证。

**尚未兑现的关键保证：** 新交权路径已经能撤销 Proxy 原始 MMIO，可信固件运行映射和启动已接入本地模型，但交权后的原生驱动服务、正常 DRM 队列发布、任务依赖/完成与可写输出验证还没有完成；Client 授权的暂存记录已接后文诊断 PREPARE/START/QUIESCE/RETURN/RETIRE。页表安装或 MCU 启动不代表可信 Client GPU 执行。当前代码只是实施阶段，不是已完成的机密 GPU 数据路径。

## RMM 固件核验与私有快照封存

页表受到保护之后，还必须保证 GPU MCU 不执行由恶意 Proxy 替换的固件。新增 [固件核心](../../opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c)及 RSI 操作 18–21：`FW_BEGIN`、`FW_WRITE`、`FW_SEAL`、`FW_INSPECT`。入口只接受已交权的实际 service RD；不接受调用者自报身份、可信摘要、固件 HPA 或区段地址。

Guest 将每批最多 4096 字节先复制到私有内核页，RMM 再复制到自己的 274432 字节快照。上传必须从零开始连续推进，拒绝跳段、重放和越界；未完整上传不能封存。RMM 使用 Mbed TLS SHA-256 核验自己的完整副本，摘要固定为 `43c3c36b914c031d88ae152fd89019d8f99ad41d9879fb5ab7496ed13f7b378b`，对应仓库原有 `GPU-SFTP/panthor_fw/mali_csffw.bin`。更新这一信任锚需要审查和重建 RMM，不能由 Proxy 请求替换。这是固定镜像准入，不是新增厂商签名认证、设备证明或完整供应链保证。

摘要成功后才解析该私有副本的 CSF 元数据，检查头部、条目长度、源数据范围、VA 对齐/重叠、权限和共享区；沿用原生驱动的保护模式区段排除策略。当前镜像得到 7 个可用区段、总映射容量 720896 字节，后续由 FW_PREPARE 建立运行副本和 MCU 页表。封存后同一服务也不能通过 BEGIN/WRITE 修改副本；失败核验清除未可信内容。可信交权/整设备撤销的成功适配器同时退休固件快照，重复成功交权不会清除之后封存的镜像。

`FW_INSPECT` 仅返回状态、已接收字节、区段数和映射总量；没有 RSI 返回快照地址或区段内容。可信准备直接消费封存副本，不重新读取 Proxy 缓冲区。[诊断工具](../../GPU-SFTP/tests/realm-xshm/realm-gpu-private.c)的 `firmware-snapshot FILE` 已接入实际 ioctl；目前仅在控制机构建，尚未在 Realm 执行。

**单独封存不启用 MCU，也不赋予任务启动权限。** 后续启动路径见下节；尚不能宣称固件已在实体 GPU 可信执行。

## RMM 固件运行页、MCU 页表和固定启动

新增全零输入的服务操作 22 `FW_PREPARE` 与 23 `FW_BOOT`。PREPARE 从封存副本复制 7 个固件区段到 RMM 私有的 176 个运行页，清零剩余内容；固件区段需要 9 个 4 KiB 表页建立四级 MCU Stage-1 页表，当前表池已为控制 arena 扩至 17 页。代码页保持只读可执行，数据页不可执行，缓存属性遵循原生区段类型；保护模式区段不映射。运行页、页表、区段地址和根均不返回给 Proxy，也不进入 Proxy 的 CPU 映射。

为同时容纳镜像快照和运行副本，Client PT 静态池从 512 调整为 448 页，固件使用独立表池（启动阶段 9 页，当前 17 页），保留原 38 MiB RMM 预留。页表不足继续明确拒绝，没有 Guest 表回退。此容量变化未经性能测试；新 ELF 的完整 BSS/栈和 U-Boot 布局已独立检查，不以文件大小推断可启动。

BOOT 仅将准备好的内部根交给可信平台后端：检查固定 arch10.8、AS0、页表格式/根/属性和停止状态，先上电首个 L2，再安装 MCU 根；屏蔽中断投递并清除旧启动位，设置固定非一致性协议，启用 MCU。RMM 有界观察真实 JOB RAWSTAT 启动位、MCU 状态、根和故障状态，随后失效 CPU 缓存并检查固件写入的版本、Group 几何及完整输入/输出范围。既不依赖 Hypervisor 的中断投递，也不接受 Proxy 自报完成。该初始化不配置 Group/Stream，不写任务门铃，任务执行能力位仍清零。

安装可能部分完成、MCU 启动超时或接口检查失败时进入 QUARANTINED，保留真实运行页和表；BEGIN/PREPARE/BOOT 均不能绕过该状态重建或重试。可信整设备复位/撤销后才清除。成功状态为 BOOTED，重复 BOOT 不重新启用 MCU；它记录已观察到的启动结果，不替代后续每任务状态验证。

同时修正已交权设备的 RMI RESET 适配：原始 MMIO 已撤销且 RMM 验证复位成功后，退休所有旧私有上下文、映射授权和固件状态，避免硬件根已清空而软件仍报告旧固件 BOOTED。原始服务 RESET、失败 RESET 和 Host 自报完成仍不能释放 backing。

本地测试已从真实固定镜像生成运行页/PTE，并从实际平台后端写入寄存器模型的 AS0 根遍历它们，覆盖启动状态、部分写失败与 RESET/RELEASE 退休。**没有实体 GPU 执行证据；GPU 对这些 RMM 页的取表/取指能力及目标 PAS 保护仍待验证。** Client 原生驱动交权后的接口、tiler 管理与正常 DRM 依赖/完成仍未接通；Client AS、可信启动和中止后缓存归还已有后文诊断路径；停止态 AS/队列准备、受保护 ring 与任务授权暂存见后文；suspend/队列 I/O 内存的可信预留见后续组资源章节。

## 受保护固件接口与可信全局配置

在 MCU 启动之后新增操作 24 `FW_CONFIGURE` 与 25 `FW_PROPERTIES`。两者仍只允许已交权的实际 service RD 调用；Proxy 不能提交寄存器地址、页表根、shader mask、计时器或固件接口指针。

BOOT 现在检查全部 global/group/stream 描述符：数量、步长乘法、完整输入/输出范围、描述符区域别名、跨 group/stream 重叠、同类槽位属性一致性以及 suspend 大小上限。输入与输出还必须分属完整的 64 字节缓存行，避免 CPU clean/invalidate 覆盖 MCU 所有的状态。检查在受保护运行页上完成；之后缓存需要的全局偏移与属性，不在执行配置时重新追随可变指针。校验最多 2049 个区间的临时空间放在 RMM 静态区，避免耗尽 REC 栈；新布局检查仍通过，Client PT 池保持 448 页。

`FW_PROPERTIES` 只返回两组属性：记录 0 为版本、global features、group 数、instrumentation features；记录 1 为每 group 的 stream 数、stream features、普通及保护模式 suspend 字节数。它们不包含 GPU VA、HPA 或 CPU 指针。只有 BOOTED/CONFIGURED 状态可查询，隔离后拒绝；属性描述固件能力，不代表已授权使用计数器或保护模式。

CONFIGURE 从可信硬件读取 shader mask，以可信计数器频率换算固定定时器，向 RMM 私有 global input 写入固定配置并完成缓存清理，再由可信后端写唯一的 global doorbell。该操作不启用 Client group/stream、性能计数器、调试/追踪指针或中断投递。RMM 根据原 ACK 翻转配置请求位，直接失效并读取真实 output ACK，最多等待 100 ms；匹配后再次检查 MCU、根、属性和硬件故障状态，才进入新增状态 7 CONFIGURED。Proxy 的 RPC 返回或 Hypervisor 注入中断不参与成功判定。

写入后门铃失败、ACK 超时或硬件状态不符均进入 QUARANTINED，保留运行页和表，只有可信复位/撤销后才能重新准备。配置前的只读硬件预检失败不发布请求；成功的重复 CONFIGURE/BOOT 不重写配置或再次启动 MCU。完整任务执行依然未实现，能力位 4 清零。

本地核心测试覆盖 12 类元数据负例、后续指针变化、跨缓存行约束、非零旧 ACK、超时/门铃失败、ACK 后故障、计数器回绕、重复调用和可信复位。寄存器模型执行实际平台代码及真实 RMM 页表，连接了固定 global doorbell 到模型 MCU 的 ACK；模型中的 suspend/stream features 是显式构造的测试结果，不能当作实体 GPU 的能力或固件运行证据。新固件、两种完整 Guest Image 和工具包均构建通过，仍未部署。

## 受保护内部控制页与 MCU arena

这部分内存不同于双方可访问的 RPC 控制页。RPC 控制页仍由 Proxy 分配并授权共享；GPU 内部 ring、队列接口和 suspend 状态可能包含 Client 数据，不能让 Proxy 保留 CPU 访问。当前已有受保护 backing，并在下节实现按 Client/context 预留的 suspend 和队列 I/O 分区；停止态硬件准备见后文，任务执行仍未接通。

操作 26–29 分别为 `CONTROL_CREATE`、`CONTROL_APPEND`、`CONTROL_DESTROY` 和 `FW_CONTROL_BIND`。只有已完成交权的实际 GPU service 可以创建、追加和绑定自己捐赠的页面。它们是独立对象类型，不能通过普通 BO 接口导入 Client GPUVM、映射或销毁；上限为全局 32 个对象、预留总量 4096 页（16 MiB）。RSI 检查原始 RTT、共享/私有登记、托管 IOMMU 及旧 GPU/DMA 引用，不接受任意 HPA。

每批最多 512 页。RMM 先保存整批页面的生命周期记录，再将原 CPU Stage-2 叶子从 assigned RAM 改为 assigned empty，并完成 TLBI，随后通过可信临时映射清零。PA、DATA granule 状态和 RTT 引用保持；RIPAS、RTT 折叠、DATA/Realm 销毁等入口继续受同一 policy gate 约束。部分接管失败后保留记录，禁止原地重试；销毁按有界批次清理，已隐藏页先清零再恢复原 CPU 映射，任何失败继续保留 backing。

`FW_CONTROL_BIND` 只允许在 PREPARED、MCU 尚未启动时消费一个完整接管的对象。初版 RMM 在固定 MCU VA `0x08000000` 建立 RW/XN/NC 映射（实机发现该地址超出原生 MCU 共享窗口，后续候选改为 `0x05000000`，见文末），扩充的 8 个 L3 表覆盖最多 16 MiB；调用者不能指定 VA、PA、root 或映射属性，返回值只有容量和页数。绑定持有对象直到可信整设备复位；安装、启动或 ACK 失败不解除持有。复位本身也不恢复 CPU 权限，后续销毁仍须清零；再次绑定则重新清零旧状态。前置建表失败只有在根从未暴露给 MCU 时才回滚。

Guest `REALM_GPU_CONTROL_ALLOC` 使用本地分散页并逐批捐赠，返回生命周期 fd，拒绝 mmap/read/write；关闭 fd 不会提前恢复固件持有的页面。诊断工具新增 `firmware-control BYTES`。这些机制已有真实 RTT/policy 源码模型、四级 PTE 和实际平台 AS0 寄存器模型证据，未在 Realm 或实体 GPU 运行，不证明硬件 GPC。**下节的组资源只预留内部内存，不创建硬件队列、ring 或 GPU 任务。**

## Client 授权的受保护组资源

操作 30–32 为 `GROUP_CREATE`、`GROUP_DESTROY`、`GROUP_INSPECT`，对应新增能力位 4096；当前加入后续组导入校验能力后的总能力为 16379，执行位 4 仍清零。CREATE 从实际 Client RD 和已认证 channel 取得服务身份，要求该 context 确实属于这个 Client 和服务；Proxy 不能替其他 Client 创建组。调用要求固件已 CONFIGURED，实际可信后端仍确认受保护根和 MCU 状态，且已绑定完整捐赠 arena。

RMM 根据已验证的固件 suspend 大小和 Client 请求的 stream 数，从 arena 中预留连续的 MCU VA 区间。普通 suspend 区按页取整，每个 stream 使用独立的 4 KiB input/output 页，与原生 Panthor 的接口分离方式一致。它们只在 MCU 地址空间映射，Proxy 和其他 Client 不获得 CPU 映射；创建和查询只返回 opaque 句柄、状态、数量和容量。后续已补 ring 分配与软件 PT 映射（见下节）；保护模式 suspend 尚未实现；诊断 CSG 槽绑定及任务门铃见后文 PREPARE/START，不能将内存预留解释为启动授权。

每个逻辑组持有真实 context 引用，阻止组尚在时销毁或复用上下文；全局最多 32 个，每个实际 Client（跨其全部 context）最多 8 个，关闭和隔离中的组也计数。组句柄使用跨复位保留的单调代数，禁止旧句柄指向新实例。创建前重新清零，清零失败返回隔离的清理句柄并保留全部区间和引用；DESTROY 每次最多清理 512 页，清理失败或未完成时继续保留，全部清零后才释放区间与 context 引用。组回收不会恢复捐赠者的 CPU 权限。

尚未进行 TASK_PREPARE 的资源可按预留资源清理；一旦准备到硬件，当前便拒绝直接销毁，必须由可信整设备复位退休。未来逐组回收必须先可信停止/排空，不能直接沿用预留资源销毁路径。可信整设备复位当前可同时退休所有组和 context 引用，但不释放尚未清零的捐赠 backing。正常 DRM GROUP_CREATE/DESTROY 的元数据接线见下一节；Proxy 原生驱动受限服务和任务提交尚未接入；`realm-gpu-private group-selftest CHANNEL [STREAMS]` 已编译用于验证实际 RSI 的创建、身份、引用及旧句柄拒绝，尚未在 Realm 运行。

## 正常 DRM 组创建与受保护资源接线

私有模式的 GROUP_CREATE 先由 Client 内核使用本文件的私有 VM/context 向 RMM 创建组；Client 持有受管理的组对象，将不透明句柄随 RPC 交给 Proxy。Proxy 记录 VM 对应的 RMM context，通过新增操作 33 `GROUP_VALIDATE` 从实际调用者和通道取得 Client，要求组、context、stream 数完全一致且仍处于可用预留状态；同 Client 的另一个 context 也不能替换。重复导入被拒绝，普通 VM 与私有组句柄不能混用。Proxy 仅建立会话元数据，不调用原生 GROUP_CREATE，不取得 suspend/I/O 页或真实硬件组句柄。

组引用最后释放时，Client 删除远端元数据并通过 RMM 清零/销毁真实预留；远端失败不构成资源释放授权。RMM 清零失败或通信失败时保留清理对象；创建失败若返回隔离清理句柄，也纳入同一回收队列。每个对象回收有界，组先于 context 和 backing 清理；RMM 对组持有 context 引用。原始诊断接口禁止销毁内核托管的组。VM_DESTROY 擦除本地 context 的操作与 GROUP_CREATE 取指针使用同一文件锁，避免并发释放指针。

组导入阶段新增能力位 8192（该阶段总能力 16379；当前含 ring/任务暂存/停止态准备/数据就绪/启动接纳/可信停止/归还/退休为 8388603，执行位仍清零）。GROUP_CREATE 请求结构增加 64 位组句柄，因此 RPC ABI 从 3 升为 **4**，拒绝旧端协商；私有 RSI ABI 保持 2，两端同时要求组内存和校验能力。**组预留不是执行授权**：当前仍拒绝将私有组翻译为原生执行句柄，GROUP_SUBMIT、计划注册及原生组状态查询返回 EOPNOTSUPP；没有伪造完成或可执行状态。队列 ring 大小/优先级现由 Client 通过 GROUP_CONFIGURE 直接授权给 RMM，Proxy 导入时逐队列核对；任务暂存仍未接正常 DRM GROUP_SUBMIT。

本地新增 `python3 scripts/check/check-gpu-group-bridge.py`，从当前真实 Guest 源码提取组生命周期辅助函数和 Proxy 创建/销毁/翻译函数，使用内核/RSI 测试替身运行 ASan/UBSan，覆盖清零/通信失败保留、创建失败的隔离句柄、context 释放顺序、分批退休、复位后旧对象、拒绝原生回退/重复导入/参数替换、普通原生创建回滚及无内存泄漏。它没有运行真实 Linux 并发、Realm RSI 或硬件；实际 RMM 归属校验另外由核心和平台后端模型测试覆盖。

## 受保护 ring 与 Client 授权的任务暂存

操作 34 `GROUP_CONFIGURE` 由实际 Client 调用，RMM 私下复制最多 32 个队列参数，要求数量等于组预留的 stream 数、ring 为 4–64 KiB 的 2 次幂、优先级为 0–15。首次配置后不可替换；完全相同的重试可幂等返回。RMM 从已隐藏 CPU 映射的 arena 分配全部 ring 和一页 completion，先清零，再通过可信内部接口映射到对应 Client GPUVM：ring 为 RO/XN/NC，completion 为 RW/XN/NC。48 位 GPU VA 的最后 16 MiB 留给内部映射，普通 MAP、MAP_AUTHORIZE、UNMAP 连跨界前缀都不能修改。实际 RSI 不返回这些 GPU VA 或物理地址。

配置清零或建表失败会隔离组，保留已分配区间、已成功映射的前缀及 context 引用。退休先移除全部 Client GPU alias，再有界清零并允许复用；上下文已激活时拒绝回收。正常 DRM GROUP_CREATE 已调用此配置；Proxy 导入逐队列通过操作 33 核对不可变参数。新增能力位 16384，ring 阶段总能力 32763，执行位仍清零。

在此基础上增加操作 35 `TASK_STAGE`、36 `TASK_CANCEL`、37 `TASK_VALIDATE`，能力位 32768，暂存阶段总能力 **65531**（当前含准备/就绪/启动/停止/归还/退休能力为 8388603）；私有 ABI 仍为 2，RPC 为 4。

- STAGE 由实际 Client 通过认证通道指定 group、queue、命令流 GPU VA/长度和 latest_flush。RMM 遍历真实页表和私有对象标签，检查非空且 8 字节对齐的完整命令流范围属于该 Client、不是内部控制页，并要求对应组/上下文可用。每次最多检查 512 页；旧单条 STAGE 不接受零长度；新增批次接口支持 fence-only，见后文。更大命令流仍需后续有界验证设计。
- 检查成功后 RMM 持有 context 的任务引用，冻结该 context 的 MAP/UNMAP（包含服务精确授权路径与内部映射）。RMM 根据已验证固件的寄存器/scoreboard 属性及固定 completion 位置，生成 16 条、128 字节的原生格式 CALL/cache-flush/wait/sync/error-barrier wrapper，保存在 RMM 私有记录中。最多全局 128 个、每 Client 32 个，也受本队列 ring 容量限制；令牌代数跨复位保留。
- Proxy 只能用自己的真实 RD 和认证通道校验 token、精确 context 和 group，得到队列、长度和 latest_flush 元数据；不能替 Client 创建/取消任务，不取得指令、页表根或数据地址。VALIDATE 是只读检查，不消费或启动任务。
- CANCEL 只允许原 Client 取消未启动记录；解除任务引用后映射方可变化。存在待处理任务时不能销毁组。上下文已激活或隔离时拒绝取消并保留引用；可信整设备复位同时退休真实映射、组/任务记录及引用，旧 token 不能指向新任务。

**TASK_STAGE 仅暂存；新增 TASK_PREPARE 可写入受保护 ring 并配置停止态硬件，但均不是任务启动或可信完成。** 当前仅保护 RMM 生成的提交 wrapper 和映射关系；Client 自己的命令流/描述符仍由该 Client 持有，不宣称做了完整 shader 验证或封存全部 Client 数据。正常 DRM GROUP_SUBMIT、同步依赖、AS 运行切换/退休及可信完成/撤销仍须接通；诊断队列 START 和单次启动状态已接下节接口。GPU 可写的 completion 页本身不具有完成或释放内存的权威性。

Guest 的新操作目前用于特权 bring-up；原始 TASK_STAGE 不能操作内核托管组，通用内核 private_call 也不能绕过未来的 typed 任务生命周期。`realm-gpu-private group-selftest` 已增加真实分配/建表、跨页命令流暂存、映射冻结、Client 冒充服务拒绝、取消和旧 token 检查，当前只编译，未在 Realm 运行。

## 由 RMM 准备停止态硬件任务

操作 38 `TASK_PREPARE` 由实际隔离服务调用，使用已认证 channel 查找 Client，再核对精确 context、group 与 Client 暂存的 token。只返回组状态 4 PREPARED 和队列编号，不返回页表根、AS、CSG、GPU VA 或物理页地址。新增能力 65536，准备阶段总能力 **131067**（当前含就绪/启动/停止/归还/退休能力为 8388603）；执行能力位 4 仍清零，ABI 2/RPC 4 不变。

- RMM 在软件空闲的 AS1–15 和真实固件声明的空闲 CSG 中选择位置；首次安装要求硬件根为零，保持已认证 MCU/AS0 运行。槽位、root 和 backing 在可能部分写入前即被持有。已有 context 重试必须匹配先前的非零根与固定属性；根丢失或属性改变时拒绝，不能通过重试重新安装。
- 固件启动时一次性验证并缓存全部 CSG/CS 接口偏移；准备阶段不重新追随可变描述符中的指针。复核 CSG 及全部 stream 请求/ACK 为 TERMINATE/STOP 后，RMM 复制已授权的 128 字节 wrapper 到 CPU 隐藏的 ring，设置选中队列 insert=128、其他队列 insert=0，并写受保护 CS/CSG 输入。根、ring、suspend、队列 I/O 和 shader/tiler 配置均来自可信记录或硬件，Proxy 无权提供实际地址。
- 该路径限定于已固定的 arch10.8 后端、真实单 tiler0 拓扑；instrumentation、IRQ mask、CS/CSG doorbell 和 START 请求保持零。它配置启动所需资源，但尚未执行 Client 命令；已通过下节 TASK_READY 实现启动前 CPU 数据缓存交接；当前 START 要求它完成。
- 完全相同 token 的重试只检查根和设备状态，不重写 ring、接口或门铃。开始准备后即阻止取消/销毁；AS 安装、ring 或队列 I/O 写入等发生部分失败时，保留任务、组、槽位和 backing，直到可信整设备复位。诊断逐上下文 STOP/TERMINATE 与 AS 禁用已接后文接口；中止后 CPU 缓存归还、任务退休及复用已接后文 TASK_RETURN/RETIRE，正常 DRM 接线仍未完成。

这一步使 RMM 能在固件运行后安装 Client AS，补上原安装接口仅能停机使用的限制。普通 DRM GROUP_SUBMIT 尚未消费此接口；交权后的受限元数据服务已加入，但任务执行链路仍未接通，不能据此宣称应用工作负载已运行。

## Client 就绪确认与启动前数据缓存交接

操作 39 `TASK_READY` 由实际 Client 调用，handle 为此前的任务 token，args 为 `[channel, 0, 0, 0, 0]`。它要求服务已完成该 token 的停止态 TASK_PREPARE；Client 负责在CPU写入全部结束后调用，并在 GPU 使用期间停止相关 CPU 写入。非延迟诊断路径还要求全部依赖满足；下述DEFERRED路径把各成员的设备依赖就绪确认推迟到各自TASK_PUBLISH之前。涉及CPU回调在运行期间准备新输入的依赖仍不受当前整context缓存租约支持。**这只是认证 Client 的就绪声明，不是 RMM 已独立验证 DRM 依赖。** 新增能力 131072，就绪阶段总能力 **262139**（当前含启动/停止/归还/退休能力为 8388603），执行位仍为零，ABI 2/RPC 4 不变。

RMM 在核对真实 MCU/Client 根后，沿自己的表归属和 leaf-object 标签检查冻结的整个 GPUVM，每次最多检查 512 个表项；跳过其他 context 的整张表，也跳过内部 ring/completion 等控制页。对于实际 Client 的普通数据页，通过临时可信 WB 映射执行整页 `flush_dcache_range`（clean+invalidate 到 PoC）和完成屏障，不建立 Proxy CPU 映射，也不返回数据或物理地址。这样既覆盖命令流，也覆盖任务可能访问的其他已映射输入/输出 BO。

游标、当前 token 和累计页数保存在 RMM；调用者不能提交游标跳过页面。返回 `[ready, queue, 累计数据页数, 0]`，状态 4 INCOMPLETE 表示同一 Client/token 继续调用，全部完成后才返回 ready=1。相同 token 再次 READY 仍检查根和设备状态，但不会重新同步数据。Proxy 和其他 Client 无权使该 token 就绪；通用内核 private_call 也暂不允许绕过未来 typed 任务生命周期调用 READY。

同一 context 只允许一个 token 持有此次缓存交接；普通 BO 还记录交接所属 context，拒绝另一 context 对同一 BO 执行 CPU 缓存操作。同步部分失败隔离 context/组并保留任务、映射、页及交接记录；可信整设备复位退休这些记录，之后仍按原归属清零/释放 backing。中止后的 GPU 到 CPU 缓存归还、交接记录解除与连续任务复用已接后文 TASK_RETURN/RETIRE；成功完成驱动的生命周期尚未接通，不能用 READY 代替完成证明或释放依据。

当前实现以整 GPUVM 同步保证第一条执行路径的覆盖范围，尚未做脏页/实际使用集合优化。该操作不写 START、门铃或新的 ring 参数；普通 DRM GROUP_SUBMIT 尚未调用它，也没有真实缓存一致性或 GPU 执行测量。

## 由 RMM 发布并核验任务启动

操作 40 `TASK_START` 由实际隔离服务调用，handle 为任务 token，args 为 `[channel, context, group, 0, 0]`。RMM 从认证通道解析实际 Client，核对其 context/group/token，并要求该 token 已完成 PREPARE 和原 Client 的全部 READY 缓存交接。返回 `[5 STARTED, queue, 0, 0]`，不返回页表根、AS、CSG 或数据地址。新增能力 262144，启动阶段总能力 **524283**（当前含停止/归还/退休能力为 8388603）；完整执行能力位 4 仍为零，私有 ABI 2/RPC 4 不变。

RMM 在发布前核对真实 MCU 状态、Client 的非零 AS 根及属性、缓存的接口位置、CSG 的 AS 绑定、全局配置 ACK、父/子门铃和全部 stream 的 STOP 状态及故障字段。按原生 CSF 顺序发布选中 CS 的 START、CSG 的 START/endpoint/子门铃、全局父门铃；每层完成可信 cache clean，再由固定后端写全局 MMIO 门铃。Proxy 不能提交寄存器脚本、页表根或替换硬件槽位。

在第一次 CS 输入写入之前，记录 start_attempted 并将组置为隔离状态，因为 MCU 可能在 MMIO 门铃之前已读取共享输入。通过可信计时器有界观察父/子门铃 ACK、CSG 的完整三位状态及 endpoint ACK、选中 CS 的 START ACK，随后再次核对 MCU 和 Client 根，才转为 STARTED。准确重试只重新检查硬件状态，不重复发布请求、写 ring、同步数据或通知；不完整 ACK、错误根、故障和门铃失败均保留资源，不能重试为新任务，须可信整设备复位后退休。

**STARTED 仅表示固件已接纳启动请求，不表示 GPU 工作完成。** 此接口尚未被正常 DRM GROUP_SUBMIT 消费；诊断逐上下文停止与 AS 禁用已接下节；依赖接线与真实成功完成/错误仍未接通；中止后的缓存归还、任务退休与连续复用见后文 TASK_RETURN/RETIRE。CPU 隐藏控制内存和关键 MMIO 的保护沿用目标平台假设；寄存器模型不会证明实体 GPU、缓存一致性或恶意 Proxy 的物理访问隔离。

## 可信停止与 Client 地址空间禁用

操作 41 `TASK_QUIESCE` 由实际隔离服务调用，handle 为已 STARTED 的 token，args 为 `[channel, context, group, 0, 0]`。RMM 认证实际 Client 及精确任务，核对运行根、固件/CSG/全部 stream 状态，然后按 CS STOP → CSG TERMINATE → global doorbell 顺序发布受保护请求。首次写入前记录 stop_attempted 并隔离组；以可信时限等待实际父/子门铃、完整 CSG 状态/endpoint 和选中 CS 的 STOP ACK。未确认停止时不进入 AS 禁用，也不把调用当作成功。

ACK 成功后，可信内存核心仍按自己的记录选取该 context 的 root/AS。固定平台后端先检查精确非零根、属性和同根跨 AS 别名，再执行全地址范围 LOCK/FLUSH_MEM，清零 64 位根和 MEMATTR，将 TRANSCFG 置为 Mali 的 UNMAPPED=1，完成 UPDATE 并核验；不是把 TRANSCFG 写零，也不停止 MCU 或其他 Client。返回 `[6 QUIESCED, queue, 0, 0]`，新增能力 524288，停止阶段总能力 **1048571**（当前含归还/退休为 **8388603**），完整执行位 4 仍为零。

**QUIESCED 是停止/中止证明，不是任务成功完成，也不允许直接释放页面。** 此操作不读取 GPU 可写的 completion 计数作为授权依据。RMM 保留 task、group、映射、AS 槽位和缓存交接引用，阻止再启动或通过 PREPARE 重装旧根；旧 CONTEXT_ACTIVATE 入口也在调用激活后端之前显式拒绝 QUIESCED context。仅 QUIESCE 不释放引用；还须完成下述 Client TASK_RETURN 和 TASK_RETIRE，才能解除本次任务的映射冻结和恢复资源复用。失败或不确定状态仍要求可信整设备复位。重复 QUIESCE 只核对停止态与 AS 已禁用状态，不重复门铃或寄存器写入；部分 STOP/门铃/FLUSH/UPDATE 失败保留资源且不重试发布。

一个 GPUVM 当前只允许一个已发布组，直到它完成可信退役；第二组在 PREPARE 前即被拒绝，原组保持可停止。停止路径还检查没有其他已发布组引用同一 context。该约束与现有每 context 单个缓存交接 token 一致；不同 Client/context 可并行运行。跨组联合停止和普通 DRM 的完成/取消调用尚未接通；中止/可信完成后的诊断任务连续复用已由下述退休路径验证，不将此阶段约束称为最终调度方案。

## Client 缓存归还与任务退休

操作 42 `TASK_RETURN` 由实际 Client 调用，handle=token，args=`[channel, 0, 0, 0, 0]`。RMM 依据自己的任务记录解析 context/group，每批开始和结束都核验真实固件 STOP/TERMINATE ACK、全局配置及已禁用的 Client AS，不能用 Proxy 的通知或 GPU 可写 completion 计数代替。只有此前完整 READY 且成功 QUIESCE 的同一 token 才可归还。

归还与启动前同步共用冻结页表/对象标签检查，但各自持有独立的私有游标。每次最多检查 512 个表项，仅遍历该 context 的普通数据页，跳过内部控制页。RSI 后端通过 RMM 临时 DATA granule 映射执行整页 `inv_dcache_range` 和 DSB，不将过时 CPU 缓存清回 GPU 结果，也不向 Proxy 建立数据映射。返回 `[returned(0/1), queue, 累计数据页数, 0]`；INCOMPLETE 必须继续同一调用，完整成功前 Client 不得访问相关数据。精确重试重新核验硬件但不重复数据失效；成功只归还 CPU 缓存使用权，保留映射、任务、BO 缓存租约及 AS/CSG 槽位，不证明任务成功。

操作 43 `TASK_RETIRE` 同样只接受原 Client 和相同输入，且要求已完整 RETURN。RMM 每批前后再次核验停止/禁用状态，最多清零 512 页该组 suspend、队列 I/O、ring 和 completion backing；游标不能由 Client 或 Proxy 指定。全部清零后移除旧 CS/CSG 输入中的地址，解除精确任务、AS/CSG 槽位和 BO 缓存租约，将组恢复 RESERVED。BO 映射和其他暂存任务的引用继续保留；最后一个任务退休或取消后，才允许正常 UNMAP。返回 `[retired(0/1), queue, 累计清零页数, 0]`；成功使旧 token 永久失效，丢失回复不能作为重放任务的授权。组可继续使用，也可显式销毁；不需要先做整设备复位。

新增能力分别为 1048576、2097152，总能力 **8388603**；私有 ABI 2/RPC 4 不变，完整执行位 4 仍清零。实际平台源模型新增 18 个场景 48–65：双 Client、513 页跨批、身份/旧 token、无停止或无完整归还拒绝、缓存/清零失败、操作中或重试时根/故障/状态变化、零重复同步、清零后旧 token 拒绝、AS/CSG/组连续复用与显式销毁、另一个暂存任务引用保持。正常场景每组核验 71 页全部清零，部分失败保持隔离与引用。缓存指令、GPU 任务执行和 Linux 并发尚未在实体平台验证。

这两项当前用于**中止或下述 TASK_COMPLETE 成功后的诊断生命周期**。操作 44 已有控制机可信完成模型，但尚未接入正常 DRM GROUP_SUBMIT、依赖和 fence 通知；不能把它描述成私有应用已可运行。

## Client 可信完成观察与安全排空

新增操作 44 `TASK_COMPLETE`，只允许原 Client 通过实际调用 RD 和已认证 channel 查询自己的精确 token；Proxy 不能替它生成完成。新增能力 4194304，当前总能力 **8388603**，ABI 2/RPC 4 不变，完整执行位 4 仍清零。

RMM 对已 STARTED、READY 的精确任务发起新的 CSG STATUS_UPDATE，并经 global 门铃要求固件刷新状态。有界等待匹配的父门铃与完整 CSG 状态/endpoint/status ACK，随后从受保护 arena 中按 RMM 自有分区记录读取队列输入、输出与同步记录，不使用调用者或固件提供的任意物理地址。RSI 适配器锁定 DATA granule，通过 RMM 临时映射失效缓存、复制所需范围，再解除映射。检查 ring 的 insert/extract、零 scoreboard、未阻塞状态、单条任务精确序号 1（新批次为该队列成员数）及零错误，并前后核验真实根、固件配置和全部 stream 状态。**单独把 completion 计数写成 1 不能证明任务完成。**

合法但未完成的快照返回 INCOMPLETE、`[0, queue, 0, 0]`，下次查询重新请求新状态。出现已有待 ACK 的 STATUS 请求时不重复发布，待其稳定后才发起自己的新观察。发布前记录不确定状态；门铃、ACK、读取、根或设备故障保留隔离状态和所有引用，不能通过重试掩盖。

观察到完成后，还必须执行可信 CS STOP/CSG TERMINATE、核验 ACK、排空缓存并禁用精确 Client AS，再重新读取同步记录及复查停止/禁用状态，最后返回 SUCCESS、`[1, queue, 0, 0]`。显式中止的任务不能升级为成功；已完成 token 的重复查询只核验停止/禁用硬件，不再发 STATUS 或读取数据。CPU 访问仍须完整 TASK_RETURN，资源复用仍须完整 TASK_RETIRE，不能因为 COMPLETE 返回成功直接释放 backing。

实际平台源模型新增 **28 个场景 66–93**，覆盖双 Client、未 START 拒绝、旧/缺失 ACK、门铃失败、busy scoreboard、阻塞、未消费完 ring、序号未到/伪造/错误、输入损坏、读取失败、MMU/根/其他 stream 故障、显式中止拒绝升级、重复查询破坏、STOP/FLUSH 失败和回调缺失。正常场景继续 RETURN/RETIRE 并复用组/槽位。模型不证明真实 GPU 执行、ARM 缓存一致性或 Linux 并发；正常 DRM 提交和可信本地 fence 接线仍未完成。

## Client 本地同步对象与正常提交边界

私有模式下，SYNCOBJ CREATE/DESTROY、二进制和时间线 WAIT/SIGNAL、RESET/QUERY/TRANSFER、sync_file 导入导出及 eventfd 都交给 Client DRM 核心处理，句柄保存在本地 DRM file 的 syncobj 表中。旧版较小 WAIT 结构由 DRM 核心补零兼容；文件关闭由核心释放对象。私有会话不附着共享完成页，也不使用原有远端完成证明缓存。此处 CPU SIGNAL 是 Client 用户的显式操作，不代表 RMM 已确认 GPU 完成。

正常私有 GROUP_SUBMIT 暂在 Client 入口返回 EOPNOTSUPP，避免本地句柄误入 Proxy PLAN_EXEC 命名空间。私有同步和异步 VM_BIND 已接本地依赖/fence worker，并在原生 GPUVA/RMM 建表后检查实际映射，见下节。旧共享默认模式不变，不能把它作为私有模式的成功回退。这个限制是实施阶段缺口，不是最终 API 设计或性能方案。

`drm-selftest` 增加真实 ioctl 的本地同步探针：未信号等待超时、CPU 信号后等待、二进制/时间线和旧版 WAIT、sync_file 导入导出与源 RESET 后快照保持、QUERY 和 TRANSFER。工具和完整两端内核已构建，**探针尚未在 Realm 执行**；它也不验证 GPU 完成。下一步仍须让正常任务的本地依赖满足后进入 RMM STAGE/PREPARE/READY/START，并且只有 COMPLETE/RETURN 成功后才能发布本地任务 fence，再以 RETIRE 结束引用。

## 私有 VM_BIND 本地依赖与实际映射核验（操作 45）

同步和异步私有 VM_BIND 共用每 DRM file 的有序 worker，输入参数和依赖在接纳时复制并持有 BO/fence 引用。同批等待引用此前操作的输出，重复输出点发布最后一个操作的 fence；完成全部分配和校验后才发布输出并排队。worker 在依赖满足前不申请 MAP 授权，SYNC_ONLY 完全留在 Client。发送给 Proxy 的是单操作同步请求，不包含本地同步句柄。同步调用者被信号中断后，worker 仍持有 backing；VM_DESTROY 排空已有工作再销毁，postclose 先标记关闭并排空再释放上下文。

Proxy 回复成功不能直接成为绑定完成证明。新增原 Client 操作 45 `MAPPING_CHECK`，handle=context，args=`[BO, byte_offset, GPUVA, page_count, protection]`；BO/offset/protection 全零表示核验 UNMAP。RMM 检查真实页表描述符、私有对象标签、backing 和全部访问/缓存属性，拒绝损坏的非叶子描述符、撤销或隔离的上下文。每批最多 512 页，只返回 `[verified_bytes, mapping_epoch, 0, 0]`。映射变化增加不回绕的 epoch；Client 要求各批 epoch 相同，拒绝跨批变化及 ABA。新增能力 8388608，当前总能力 **16777211**，ABI 2/RPC 4，完整执行位 4 仍清零。

只有核验成功才成功 signal 本地操作 fence。依赖错误、RPC/核验失败向后续操作传播，前面已成功的操作保持成功；错误和传输不确定时取消剩余授权，但实际映射继续持有 backing。时间线链的外层不自动传播当前点的错误，因此完整依赖 signal 后同时检查该点的 contained fence；不声称恢复已经被链回收的历史错误。每 file 最多 128 个待处理批次，依赖等待及映射核验各有 60 秒截止，依赖等待约每 100ms 检查关闭；这些是实施限制，不是性能结论。

**MAPPING_CHECK 只是某一 epoch 的映射快照，不是映射租约或 GPU 完成证明。** 后续任务仍须由 Client 授权并经 RMM 冻结映射、核验实际上下文及完成状态，不能将此 fence 当作任务成功。

控制机 `check-gpu-private-bind.py` 提取实际 Client 参数复制、规划和 worker 函数，在 ASan/UBSan 与内核/DRM/RPC/RSI 替身下验证 **25 个场景**。覆盖二进制/时间线及同批依赖、时间线当前点错误、假 MAP/UNMAP 成功、513 页跨批 epoch 变化、RPC/核验/授权失败、超时/关闭取消、输入快照、分配失败、配额、前序成功保持、同步等待中断和引用释放。替身测试不证明 Linux 并发或实际原生服务可用。`drm-selftest` 新增 MAP→UNMAP→SYNC_ONLY 异步链，检查时间线并导出 UNMAP 的 sync_file，要求实际文件状态为成功，避免 WAIT 只证明 signal 的歧义；探针仅构建，Realm 运行 **NOT_RUN**。

## 交权后保留的受限原生驱动服务

新增启动参数 `panthor.rmm_service=1`，默认关闭。该模式只允许 Realm：先 claim 设备并读取一次静态 GPU 能力，再调用 RMM SERVICE_ISOLATE 撤销 CPU MMIO/复位，随后释放内核 I/O 映射并置空指针，才初始化软件 MMU/GPUVA 管理并注册 DRM 服务。没有先运行再解绑原生驱动的窗口；不初始化 GPU IRQ、原生固件、任务调度器、复位 worker 或运行时 PM，软件 MMU 初始化也不请求 MMU IRQ。初始化失败不会退回普通驱动或重新取得 MMIO。初始能力快照仅供兼容性查询，RMM 独立检查执行参数，不以 Proxy 的快照授予权限。

Proxy 仍可通过原有内核 bridge 建立会话，导入私有 context/BO，并使用原生 GPUVA 逻辑向 RMM 建表；它不能打开本地 DRM 文件，也不能创建普通 GPUVM、共享 payload BO、原生 group/任务或原生 tiler heap。私有 group 继续使用 Proxy 已有的 RMM 元数据路径。CSIF 数据查询读取已 CONFIGURED 的 RMM 固件属性，不映射固件接口；每次使用局部结果，不改共享缓存或让并发查询互相覆盖。普通共享模式的原生 IRQ/查询路径保留。服务卸载只撤销 DRM 服务可见性，不访问已撤销 MMIO，也不将卸载视为任务完成或 RMM 资源可回收证明；挂起、恢复和原生 reset 调度均跳过硬件路径。

新增 `realm-gpu-private service-bootstrap FILE`，在已有 MMIO 交权后串联 firmware-snapshot → FW_PREPARE → 16 MiB 控制 arena 捐赠/绑定 → FW_BOOT → FW_CONFIGURE。只从空固件实例开始，已配置实例仅查询返回；中间失败保留状态，不重置设备、不自动重启部分实例。它不接纳 Client 任务，也不声明真实执行成功。待硬件验证时的顺序为：

1. Proxy 使用 `panthor.rmm_service=1` 启动，检查受限服务注册日志。
2. 在 Proxy 执行 `realm-gpu-private service-bootstrap /path/to/mali_csffw.bin`，使用 RMM 固定允许的固件。
3. Client 使用 `panthor_client.rmm_private_data=1`，再执行私有 DRM 绑定探针。

上述顺序**仅已构建，Realm/真实 GPU 未执行**；当前 runner 尚未自动串联它。正常 GROUP_SUBMIT、本地任务完成 fence、Client 私有 tiler heap 仍未完成；RMM 多队列批次生命周期已接，见下节，不能用该模式运行 glmark 或声称完整私有应用已可用。该模式解决的是“不依赖解绑也可保留驱动元数据服务”的源码接线，不是硬件验证结果。

`check-gpu-rmm-service.py` 提取实际设备初始化、MMU 初始化和属性查询函数，ASan/UBSan 与内核/RSI 替身下 **26 个场景**通过：非 Realm、映射/claim/交权失败、异常回复、MMU/DRM 注册失败、交权前读取和交权后不再访问 MMIO、服务模式实际 MMU 初始化不申请 IRQ、未配置/非法固件属性拒绝、局部查询结果、普通模式 IRQ 和查询保留。不能替代完整 Linux probe/unplug、并发或真实 RSI 验证。

## Client 授权的多队列提交批次

新增操作 **46 TASK_STAGE_BATCH**、能力位 16777216；当前总能力 **33554427**，ABI 2/RPC 4 不变，完整执行位 4 仍清零。普通 GROUP_SUBMIT 一次最多包含六个队列提交，可能跨队列相互等待；把它拆成逐条启动并等完成会造成死锁。新 token 将整个批次绑定到同一 Client/context/group，由 RMM 一起准备和启动，不逐队列等待。

- 实际 Client 提供最多六个 24 字节描述，包含命令 GPU VA、长度、queue 和 latest_flush；无 HPA。诊断 ioctl 先复制到私有内核页，RSI 再复制到每 CPU 的私有快照。非空命令要求起始地址 64 字节、长度 8 字节对齐；起始地址和长度都为零表示 fence-only。任一描述非法则整个批次拒绝，不留下映射引用。
- 所有成员合计最多检查 512 个命令页，重复访问的页也计入预算，防止在 RMM 锁内放大页表遍历。每批只取得一份 context 引用和一份缓存租约。更多或更大的命令仍是当前限制，尚不支持完整任意 DRM 工作负载。
- 同队列成员按输入顺序追加到受保护 ring；独立队列各自得到最终序号。fence-only wrapper 不 CALL 私有命令，但仍保留同步与错误屏障。RMM 只紧凑保存额外成员描述，在 PREPARE 时生成 wrapper，不扩大固定 RMM 预留或缩减既有对象/表池配额。
- START 先发布所有参与 CS，再发布 CSG 和 global；只有全部参与 CS 的真实 ACK 正确，且其他 stream 仍停止，才返回接纳。重试不重发。QUIESCE 同样停止全部参与队列并核验 ACK，之后才禁用 AS。
- COMPLETE 使用新的 STATUS_UPDATE，检查每条参与队列的实际 ring 进度、scoreboard/阻塞、最终序号和错误。某条队列未完成时仍核验其他队列，不能掩盖另一队列的损坏。有效未完成可重新发起新的观察；任意不确定失败保留引用。全部完成后执行 STOP/禁用 AS，重新读取所有队列同步记录，再允许后续 RETURN/RETIRE。不会因首条队列或一个计数器完成就提前归还数据。

新增批次 admission 单元测试和 **18 个实际平台源代码/寄存器模型场景**：同队列重复成员、全 fence-only、六成员批次、部分队列完成后的重试、第二队列的缺 ACK/错误/伪造序号/读取失败、错误 ring 输入、第一队列忙但第二队列损坏、无状态 ACK 时伪造计数、STOP 部分 ACK、停止后的第二队列再次检查及单份引用回收。保留旧单条诊断接口及既有双 Client 回归。模型只模拟 ACK/进度，不执行 GPU 命令，不能当作真实跨队列依赖执行证明。

`realm-gpu-private group-selftest CHANNEL [STREAMS]` 已追加批次探针，验证真实 ioctl 的输入快照、后续坏成员整体拒绝、冻结和取消；仅编译、未运行。**正常 DRM GROUP_SUBMIT、跨 VM 调度消费、本地可信任务 fence、Client 私有 tiler heap 和 runner 仍未接通。** 此改动是正常提交的前置能力，不表示完整应用可用。

## Client 内核任务托管与 Proxy 受限控制 RPC

Client 新增 typed task API：复制批次描述后再校验并调用操作 46，托管返回 token、原通道和首队列。只有原 Client 可通过该对象执行 READY、COMPLETE、RETURN、RETIRE；成功退休前一直保护 token。诊断 ioctl 不能修改内核托管任务或重新配置/销毁托管组，通用内核调用也不能绕过 typed Client 接口。返回的零 token、重复托管 token、错误数量/队列掩码及保留位均拒绝；重复 token 不会取消已有任务。

新增 24 字节请求/回复和会话特性位 `RMM_TASK_CONTROL`，保持 RPC ABI 4。Proxy 只接收 session、Client group 句柄、token 与 PREPARE/START/QUIESCE 三种动作；实际 channel/context/private group 来自既有通道和私有会话元数据。RMM 再独立检查实际服务身份、Client、context、group 和 token。接口没有 root、HPA、寄存器脚本或命令地址字段。队列范围和 typed 状态回复均检查；响应丢失不重放，不自动 READY 或退休。

完成观察和缓存归还仍由 Client 调用 RMM，Proxy 的 START 回复只证明接纳。调用者必须串行操作同一个内核任务对象；put 后不再访问。放弃对象仅尝试 CANCEL 未准备任务，已准备/状态不确定的任务保留在私有清理列表；只有可信复位后 RMM 确认 token 已消失才清除，不把关闭文件或超时当作完成。

这是正常提交的前置接线，**Client 正常 GROUP_SUBMIT 尚未消费这些任务接口**。DRM 每个 queue-submit 有独立的等待/信号语义；不能把所有依赖先等完、一次性启动全批并统一发布输出 fence，批内依赖可能因此死锁。当前 RMM 的“每组一个 prepared token、每 context 一个已发布组”也限制跨提交命令流并行，仍需实现逐 job 依赖、进度与完成及缓存租约安排，才可启用普通私有提交。现阶段维持 EOPNOTSUPP；批次模型通过不代表这些语义已实现。

## Client 私有初始 tiler heap 与本地地址预留

正常私有 `TILER_HEAP_CREATE/DESTROY` 已接本地实现，不再向 Proxy 请求 heap backing 或接受 Proxy 返回的 heap 地址。Client 的 VM 创建路径将经检查的 `user_va_range` 固定在内核 context；普通私有 VM_BIND 只能操作该用户范围，包含跨界前缀的 MAP/UNMAP 也在授权/RPC 前拒绝。初始 heap 从用户范围之后、RMM 顶部 16 MiB 内部区域之前选择不重叠的 GPU VA；地址预留由 Client 私有链表维护，包含尚未成功回收的对象，每 context 最多 128 个。这个地址划分是 Client 内核对象管理，真实映射/身份/物理页与活跃任务生命周期仍由 RMM 判定。

每个初始 heap 使用一个普通 Client 私有 BO：一页容纳零初始化、对齐的 32 字节 GPU heap context，之后是 `initial_chunk_count` 个 chunk，chunk_size 保持原生 128 KiB–8 MiB/页对齐约束。每个 chunk 的 64 字节 header 除 next 外全零；next 为前一个 chunk 的 GPU VA 与大小页数的组合，最后初始化的 chunk 成为 first。业务页由 Client 分配，Proxy 没有 CPU 共享别名；返回应用的只有本文件 heap handle、context GPU VA 和 first-chunk GPU VA，不返回 HPA/页表根。

Client 内核使用既有 RMM MAP，每批最多 512 页建立 RW/XN/WB 硬件格式叶子。RPC 控制页仍保持原共享路径；这些 GPU heap 页属于数据页。CPU 只在新 BO 尚未交给 GPU 时初始化，后续依然必须通过 TASK_READY/RETURN 完成实际缓存所有权交接，创建成功不构成执行授权或缓存一致性证明。初始总 backing 当前受单 BO 512 MiB 限制，包含 context 页；没有扩大 RMM 保留；后述回收修正新增能力，ABI 版本保持 2。

销毁先通过 RMM 分批 UNMAP_BO 精确回收，再交由现有 BO_DESTROY 权威检查和清零释放。建表前记录本批尝试上界，响应异常/部分同步可能留下的映射不会因创建失败而被遗忘。回收失败保留 backing、确切 unmap 游标和 VA 预留；普通后续分配不得复用它。RMM task hold 阻止活跃映射修改，只有实际撤销后查询确认 revoked、mapped=0、activated=0，才能采用整设备撤销的清理依据。仍持有 heap 的 context 包装对象不能先行销毁。DRM heap handle 或 VM/file 关闭只移交清理责任，不把 Proxy 回复作为释放证明。

**这实现的是初始存储的正常 DRM 创建/销毁，不是完整 tiler heap 执行服务。** `max_chunks`/`target_in_flight` 当前保存为 Client heap 元数据；固件 OOM 事件、受信增长授权、活跃映射更新及新增 chunk 回填尚未实现，不能宣称已执行相应增长策略。正常私有 GROUP_SUBMIT、逐 job fence/缓存和 runner 也仍未接通；不能用初始 heap 或模型 PASS 宣称私有 glmark 可运行。

新增 `check-gpu-private-heap.py` 将提取的实际 Client/内核 heap 函数直接连接实际 RMM 私有页表核心，52 个 ASan/UBSan 场景通过：原生 chunk 链/零上下文、真实多级 RW/XN 叶子、两个模型 Client 的相同 GPU VA/不同 backing、跨批建表、配额/地址空间不足、真实 task hold 的回收拒绝、部分 unmap 游标/VA 不复用、同步失败隔离与可信撤销后清理、typed 回复、诊断映射限制及实际前端本地创建/VM/file 释放。内存分配、RTT/RSI、锁与 DRM 容器仍是控制机替身，不证明实际 GPC、Linux 并发或 GPU 使用。既有 bind 测试增至 27 个，补用户/内核 VA 边界与跨界拒绝；组/任务的独立测试不创建 heap，其新 heap 查询/回收依赖使用空状态替身，heap 本身由新联合测试覆盖。

`drm-selftest` 新增真实 TILER_HEAP_CREATE/DESTROY 探针：8 MiB 初始 chunk 跨 RMM 建表批次，检查用户 VM_BIND 不能 UNMAP heap VA、重复销毁拒绝和非法零 chunk。工具和 initrd 已构建，Realm/GPU 运行仍为 NOT_RUN。

## 初始 heap 的原子精确回收修正

代码审查发现：heap VA 预留只在 Client 本地，不能证明该地址此前没有诊断映射或尚未消费的 MAP 授权。实际 RMM MAP 遇到已有叶子会拒绝；旧 heap 清理却按整段 VA 执行普通 UNMAP，可能误删既有其他 BO 映射。不能用先 MAPPING_CHECK 再 UNMAP 修复，因为 Proxy 可在两次 RSI 调用之间消耗旧授权或替换映射。

新增操作 **47 UNMAP_BO**：实际 Client 输入 context、BO、BO 字节偏移、GPU VA、页数，RMM 在同一 `xshm_policy_lock` 内完整预检再删除。仅选择对象标签及真实 PTE 物理页均对应预期 BO/页偏移的叶子；不存在或属于其他 BO 的叶子保留。匹配 BO 的错误偏移、异常非叶子/标签、引用计数不足、活跃/任务持有/隔离/撤销上下文都会拒绝且不删除前缀。每批最多512页，成功返回已处理范围字节数而非实际删除数量，支持不确定回复后的幂等重试；不会申请新的页表。原普通 UNMAP/控制页撤销语义保留。RMM 增加约1 KiB有界栈快照，没有扩大页表池或固件保留。

heap 正常销毁与失败回滚改用该操作，跨批游标、VA 保留、可信撤销与 BO_DESTROY 判定继续有效。操作不取消旧授权，也不是 RMM 的永久 VA 预留：即使同 BO 另有授权在 wrapper 销毁后才被消费，授权/映射引用仍阻止 backing 释放；直到实际授权取消/消费且映射撤销才能回收。Proxy 可拒绝服务或破坏本 Client 任务可用性，这些测试不证明公平性或活跃映射更新。

Client 私有模式握手增加能力位33554432要求；当前能力 **67108859**，ABI2/RPC4、完整执行位4仍清零。通用内核/诊断入口对 UNMAP_BO 也应用 heap VA 重叠拒绝，heap 私有回收在持有本地锁时调用实际 RSI。新接口只认证实际 owner，不能由 Proxy 代替 Client 调用。

实际前端/内核函数连接真实 RMM PT/ref 核心的联合测试扩展至 **75 个**，包含首批/后续批次冲突保留、预授权映射在回收前/后被 Proxy 消耗、同 BO 未消费授权保留 backing、错误偏移晚出现时不删前缀、跨 owner/服务拒绝、损坏非叶子/异 context 页表拒绝、实际任务 hold 和既有异常/游标测试。锁、RSI、RTT与内存分配仍为控制机替身，没有实际 Linux 并发或 GPU 运行证明。将备份中的旧 `heap_unmap_locked` 接入相同新冲突测试，断言失败并退出−6，证明新测试可检出原缺陷；该预期失败单独保存，不伪装为产品 PASS。

真实自测工具还增加错偏移拒绝、幂等精确撤销、实际映射计数及重建探针；已编译打包，运行 **NOT_RUN**。正常 DRM 私有任务提交、逐 job 依赖/信号、动态 heap 增长、死亡 Realm 清理、runner 与实机验收仍未完成。

## 为正常逐任务提交补充可信成员进度

每个DRM queue-submit有独立依赖和信号，数组顺序不等于不同队列的完成顺序。把整个批次统一等待依赖、统一发布完成，可能让本应由批内成员产生的依赖永远无法满足。此次补充观察基础，**尚未启用正常私有GROUP_SUBMIT**。

新增操作 **48 TASK_PROGRESS**：RMM认证原Client和channel，读取已就绪/开始的精确token，与TASK_COMPLETE共用实际`task_observe()`。先重查根、固件和流状态，发自己的STATUS_UPDATE并核验fresh ACK；再检查全部参与队列的固定insert、合法extract和错误/完成字段。成员位只有在该成员所属队列的sequence与wrapper消费前缀都达到其ordinal时才置位。全部队列及根再次通过后才发布；后续队列失败不能泄露前面已算出的成功位。RMM保存已观察位图，进度倒退使组隔离，不使用旧位图冒充新观察。

例如数组为“队列1的A、队列0的B、队列1的C”，只完成队列0的第1个成员时位图为010；队列1第1个成员也达到sequence和消费前缀后为011，C仍未完成。六成员交错队列也按各自顺序计算。

SUCCESS返回`[成员位图, 成员数, 参与队列位图, 0]`，可以合法返回零位图。INCOMPLETE表示没有fresh观察，成员位图必须为零。已由COMPLETE确认停机的精确token，先复查实际停机/禁用状态后可返回全满位图，不再发STATUS。取消、退休、复位失效和跨Client/service token均不能成功；超时或部分观察失败保留引用，不反复重发不确定STATUS。

**进度不代表CPU可读完成。** PROGRESS不发布新任务、不STOP、不排空/禁用AS、不做CPU数据归还、不释放任务或映射引用。即使位图全满，仍可能不满足idle/endpoint条件；必须走原COMPLETE的全部结束条件、可信STOP/排空/AS禁用及停机后完成记录复查，再RETURN/RETIRE。进度自身不能成功信号DRM fence、授权CPU读取或回收页面。原COMPLETE结果布局不变，复用观察器后仍执行全部结束条件。

Client typed任务对象保存原count/queue_mask，检查回复中的成员数/队列集合、范围外位和保留字段；INCOMPLETE不能携带旧成功位图。全满位图也不修改token或触发释放。诊断/通用入口不能对托管token代执行有状态观察。Proxy没有新增观察权限，RPC仍只有PREPARE/START/QUIESCE。私有DRM握手要求能力67108864；该进度阶段总能力 **134217723**，ABI2/RPC4不变，完整执行位清零。实际ARM64链接仍符合38MiB预留。

新增18个真实平台源码/MCU-MMIO替身联合场景：跨队列、重复队列、六成员部分前缀，sequence与extract互相领先或字节不足，旧ACK、后续队列错误/不可读/异常计数、错误根、倒退、失败重试无新通知、无效身份和旧token。即使全满，RETURN/UNMAP仍拒绝，必须先实际完成和停机。接口场景由54增至64，检查回复形状、范围外位、诊断限制和全满位图不释放。仍是模型，不证明实际GPU命令执行、Linux并发或CPU缓存一致性。

逐job依赖就绪后的可信发布、活跃组跨提交ring追加、逐job错误/fence及缓存所有权仍需实现。当前每组一个prepared token、每context一个发布组的限制仍在；TASK_PROGRESS没有解决这些限制，普通GROUP_SUBMIT继续EOPNOTSUPP。动态tiler增长、死亡Realm清理、runner和实机验证也未完成。

## Client 逐队列前缀发布：任务暂存与可执行范围分离

新增操作 **49 TASK_PUBLISH**，能力134217728；当前总能力 **268435451**，ABI2/RPC4不变，完整执行位仍清零。该操作只接受原Client及认证channel，输入为token和原数组的累积成员位图，不接受ring地址、INSERT值、硬件槽位或寄存器脚本。Proxy RPC权限仍只有PREPARE/START/QUIESCE。

`TASK_STAGE_BATCH`增加标志`TASK_DEFERRED=1`。Client内核typed暂存固定使用该标志：RMM保留原始成员数组顺序，PREPARE构造全部wrapper，但所有队列INSERT保持零。Proxy即使调用START，也只能启动没有可见任务的空队列。标志0保留原诊断整批路径；Proxy不能冒充Client调用暂存或选择该标志，正常typed消费者不能退回整批发布。

Client完成所有CPU数据准备并经READY交出整context缓存使用权后，可在某个成员的设备依赖满足时调用`realm_gpu_task_publish()`。RMM只允许每条队列自己的前缀增长，不要求不同队列按数组顺序同时增长。例如原数组为`[q1:A, q0:B, q1:C]`：

| 累积位图 | 可执行内容 | 判定 |
| --- | --- | --- |
| 010 | 仅q0的B | 允许，B不必等待q1的A |
| 011 | q0的B、q1的A | 允许 |
| 111 | 再加入q1的C | 允许 |
| 100 | q1的C越过A | 拒绝 |
| 011之后改为010 | 撤回已经发布的A | 拒绝 |

发布前逐队列核对受保护输入的旧INSERT、保留字段、真实根和固件状态，全部通过才写新前缀。启动前发布不发门铃；启动后更新固定I/O页，再按CSG子门铃→全局父门铃顺序clean和通知，观察实际ACK并重新核对根及所有stream状态。精确重试检查硬件和旧游标，不重写INSERT或再次通知。MCU可能在MMIO之前消费INSERT，因此首次写入前就记录目标并隔离组；部分写入、通知失败或ACK不确定均保留任务/缓存/页/槽位引用，后续调用不重放。

PROGRESS改按各队列已发布数量检查sequence和消费位置，不能观察出未发布成员的完成；COMPLETE仍要求全部原始成员完成，不能把“当前已发布前缀全部结束”升级为整批成功。发布回复仅为`[累积位图, 原成员数, 原队列集合, 0]`，不是DRM fence、CPU缓存归还或释放授权。Client typed接口严格检查回复和位图范围，通用/诊断入口不能操作托管token。

这一步提供**同一暂存批次内**的逐成员发布，不是完整的正常DRM调度器。当前仍有每context一个缓存租约/发布组、每group一个prepared token的限制，未实现跨提交ring追加；CPU回调在执行期间继续写入BO、逐job可读结果/fence、依赖错误传播和私有tiler动态增长仍需完成。普通私有GROUP_SUBMIT继续返回EOPNOTSUPP，不能靠整批等依赖或整批signal伪装兼容。

## 可信整设备撤销

RMI `GPU_RELEASE` 已由原设备服务在 RMM 内完成“撤销 Proxy MMIO alias → 实际 GPU 复位 → 检查复位完成”。这一操作成功后，[适配器](../../opencca/tf-rmm/runtime/rsi/opencca_gpu.c)调用私有 PT 和固件撤销入口；已经交权、原始 MMIO 已撤销的设备也可在 RMM 验证 RESET 成功后退休。原始服务的普通 RESET、失败 RELEASE/RESET 和 Host 自报完成均不能解除引用。

该入口清空旧页表中的实际描述符、解除全部映射引用及 AS 槽位占用，并将旧 context 永久标记 revoked；旧句柄不可再次映射/启动。它处理未激活、已激活与隔离中的上下文，重复 RELEASE 幂等。Client CPU backing 仍由原 BO/fd/VMA 持有，只有后续 owner BO_DESTROY 才允许分配器清零释放。此路径已有核心单元与 ARM64 链接证据，未在板端验证；不等于正常 DRM 逐任务成功完成或死亡 Realm 自动回收；诊断完成、缓存归还和任务退休另见上节。

## 后续必须接通的路径

1. 在 Realm 内验证已接入的 BO/context 导入及 VM_BIND 路径，补齐并发、错误批次与拆分/重映射语义；当前只有编译和 RMM 核心测试，不能据此视为端到端通过。
2. 在已实现的 Client 任务授权暂存上接通正常 DRM 提交、同步依赖和可信状态机；当前 MAP 授权或 TASK_STAGE 均不代表任务实际执行。
3. 在已实现的交权、停机 MMU 后端、固件启动/全局配置、受保护 arena 和 Client/context 组资源预留之上，在已接的正常 DRM 组创建/销毁元数据路径上，验证新受限驱动服务，并接通正常 DRM 的 Client AS/多队列批次和任务门铃。已有 ring 分配/建表、停止态 AS/CSG/CS 准备与预发布退休；诊断可信 START 已接，诊断可信完成已接，尚需正常 DRM 消费与完成处理；中止后诊断退休已接；不能重新使用 Proxy 可读写的普通 BO。只保护根寄存器不够：Proxy 仍能改命令或队列时，可以让合法上下文执行未授权复制。
4. 将已暂存的 Client 授权入口/context/实例绑定到硬件单次启动，补齐依赖、可信完成及可写输出边界；诊断单次 START 已接，启动前缓存交接已接 TASK_READY，但诊断成功完成已接操作 44，普通 DRM 的调用时机、本地可信 fence 与归还/退休接口的接线仍需接通；WB mmap 本身不承担 CPU/GPU 一致性保证。
5. 在已实现的逐上下文可信 STOP/TERMINATE、AS 缓存排空与禁用之上，已接诊断缓存归还和任务租约退休/复用；继续接入正常完成和异常退出清理；全设备 RELEASE 的新撤销路径须验证。当前拒绝回收的路径会保留内存，属于实施阶段的安全失败行为，不是完整恢复机制。按 Client 限制 RMM 全局对象/页表资源也尚未完成。
6. 板端先完成完整 720p glmark 门槛与正确性/内核健康/资源恢复，再扩展私有 BO 探针、真实 GPU 计算、多 Client 与攻击负例。控制机尚无可用设备 SSH 凭据，未部署新固件/内核。

## 本地验证与证据边界

控制机 run-id：`rmm-client-bo-20261030`；产物及日志位于 `build/rmm-client-bo-20261030/`，不加入源码提交。

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| RMM 私有 PT + 精确授权 + 失败资源回滚 + Guest/RMM ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-control-isolate.log` | ASan/UBSan；既有 PT/归属/撤销检查；精确地址/权限/缓存属性、513 页分批、前缀与终态重放拒绝、取消/服务释放、待授权引用、配额与部分取消；8 页表池连续 64 次失败不消耗授权、不泄漏空表；操作与能力 ABI 一致 |
| 原共享通道和 GPU 控制回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-control-isolate-initial.log` | 身份、共享内存、GPU lease/可信复位/撤销策略和 IRQ 核心测试；新增交权身份、撤销先于复位、失败标志不可被 RESET/claim 绕过、引用保留、幂等和 owner teardown；不代表板端成功 |
| DMA/真实后端代码及集成 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-control-isolate-integration.log` | ASan/UBSan；寄存器模型执行实际平台后端代码，验证固定安装/失效顺序、根高位、属性、停机/格式/槽位检查和超时；从写入的根遍历两个 Client 的真实 RMM PTE，验证精确授权、失效、部分写失败隔离、复位退休。MMIO/RTT 撤销仍有模型边界，不是实体证明 |
| RMM ARM64 构建 | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，rc=0；`rmm-control-gated.log` | 交权、登记准入、真实 MMU 后端与 RSI/RELEASE 适配器完整链接；原有 build-id discarded 提示保留 |
| 固件内存布局 | `python3 opencca/scripts/check-firmware-layout.py --rmm build/rmm-client-bo-20261030/rmm-build-arm64/Debug/rmm.elf --uboot opencca/u-boot/u-boot`，rc=0；`layout-control-isolate.log` | 新 BSS/表池仍符合现有 RMM 预留，不与 U-Boot 冲突；不代表实体启动通过 |
| 完整 Client Image | `make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`，rc=0；`guest-client-control-gated.log` | 含 Client 私有 BO/context、精确 MAP 授权与错误取消、六项非执行能力协商及 ABI 3；未部署 |
| 完整 Proxy Image | 上述 make 命令将输出目录改为 `guest-proxy`，rc=0；`guest-proxy-control-gated.log` | 含 Proxy 私有 BO 校验、能力协商、原生同步/异步授权转发及 job 清理；未部署；本次增量无编译器告警 |
| ARM64 静态诊断工具 | `REALM_XSHM_BUILD_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/tools bash scripts/build/build-realm-xshm.sh`，rc=0；`tools-control-isolate.log` | 生成原始 RSI 和真实 DRM ioctl 两种探针及既有工具；未执行 Guest ioctl |
| 初始化包 | `python3 scripts/build/build-realm-xshm-initrd.py --tools-dir build/rmm-client-bo-20261030/tools --gpu-private build/rmm-client-bo-20261030/tools/realm-gpu-private --output build/rmm-client-bo-20261030/tools/initrd.cpio`，rc=0；`initrd-control-isolate.log`、`initrd-validation-control-isolate.json` | 逐项解析 newc，核验打包内容等于当前 AArch64 二进制、整体 4 KiB 对齐；未启动 |

固件封存新增验证均为控制机检查，run-id 不变：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心、ABI 与固件快照 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-firmware-snapshot.log` | 原有检查与 4 个新操作/能力 ABI；实际固定固件及 Mbed TLS SHA-256；身份、乱序/重放/越界、完整性、源缓冲区修改、封存不可变、7 区段/容量、可信退休和摘要计算失败；ASan/UBSan |
| 共享与实际 MMU 后端回归 | `bash scripts/check/check-rmm-xshm-events.sh`、`bash scripts/check/check-dma-guard.sh`，各 rc=0；`xshm-firmware-snapshot.log`、`dma-firmware-snapshot.log` | 受本次头文件/接口变化影响的既有核心回归；不是 GPU 实机执行 |
| RMM 与布局 | 上表同一 RMM 构建及布局命令，各 rc=0；`rmm-firmware-snapshot.log`、`layout-firmware-snapshot.log` | 新 SHA/封存核心与 RSI 完整链接；增加的快照仍符合既有 RMM 预留及 U-Boot 布局。链接器的 RWX LOAD segment 与 build-id discarded 提示仍保留，未声称解决 |
| 两种完整 Guest Image | 上表同一 Client/Proxy make 命令，各 rc=0；`guest-client-firmware-snapshot.log`、`guest-proxy-firmware-snapshot.log` | FW_WRITE 私有内核页复制、新 UAPI；没有编译器告警；未部署 |
| 工具与 initrd | 上表同一工具及打包命令，各 rc=0；`tools-firmware-snapshot-final.log`、`initrd-firmware-snapshot.log`、`initrd-validation-firmware-snapshot.json` | 实际上传 ioctl 工具编译及独立 newc 内容/ARM64/权限/对齐核验；未在 Guest 执行 |

固件运行映射与启动的最新验证同样只在控制机执行：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心、ABI、固件运行页 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-firmware-boot-final.log` | 原有检查及操作 22/23、能力 256/512；从固定镜像核对 176 页内容与零尾、真实 MCU 描述符、只读/执行权限、保护区排除、准备/启动状态、重复调用、完整接口范围、失败保留和复位清除；ASan/UBSan |
| 真实平台后端模型集成 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-firmware-boot-final.log` | 原 DMA/Client PT 回归；固定 arch10.8/AS0、L2 上电/超时、根和属性核对、旧启动位清除、MCU 状态与超时；从实际安装根访问真实 RMM 固件页/PTE，部分安装失败隔离，已交权 RESET/RELEASE 退休模型。没有实体中断或 GPU 执行证据 |
| 共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-firmware-boot.log` | 既有身份/事件/共享与设备交权核心；不等于端到端 GPU 通过 |
| RMM 与布局 | 上表同一 RMM/布局命令，各 rc=0；`rmm-firmware-boot-complete.log`、`layout-firmware-boot-final.log` | 运行页/表、固定启动、可信 RESET 退休适配完整 ARM64 链接与 38 MiB 预留/BL33 布局核验；既有 RWX/build-id 提示保留 |
| 完整两种 Guest 与工具包 | 上表同一 make、工具构建、initrd 命令，各 rc=0；`guest-client-firmware-boot-final.log`、`guest-proxy-firmware-boot-final.log`、`tools-firmware-boot-final.log`、`initrd-firmware-boot-final.log`、`initrd-validation-firmware-boot.json` | 新 UAPI 和诊断入口，配套 ARM64 Image/工具，独立解析 initrd 内容/权限/对齐；未部署或运行 Guest ioctl |

可信全局配置的最新检查仍使用同一 run-id，全部为控制机证据：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心、接口及配置 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-firmware-config-final.log` | ASan/UBSan；既有 BO/PT/授权回归、完整 group/stream 与缓存行范围、12 类元数据拒绝、固定配置与真实 ACK 观察核心、回绕/失败隔离、ABI 对齐 |
| 实际平台代码集成 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-firmware-config-final.log` | 固定 shader/可信计时器、仅 global doorbell、根/MCU/故障拒绝；固定镜像→实际 RMM 页表→AS0→模型 MCU ACK；ACK 缺失与部分安装失败保留、RESET/RELEASE 退休 |
| 原共享核心 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-firmware-config.log` | 既有端点/事件/共享/交权回归；不是板端执行 |
| RMM 与布局 | 上表相同构建及布局命令，各 rc=0；`rmm-firmware-config-final.log`、`layout-firmware-config-final.log` | 完整 ARM64 链接和现有预留/U-Boot 布局；既有 RWX/build-id 提示仍保留 |
| 两种完整 Guest Image | 上表相同 Client/Proxy make 命令，各 rc=0；`guest-client-firmware-config.log`、`guest-proxy-firmware-config.log` | 新操作/能力 UAPI 和调用边界，完整 Image；无编译器告警，未部署 |
| 工具与 initrd | 上表相同工具/打包命令，各 rc=0；`tools-firmware-config.log`、`initrd-firmware-config.log`、`initrd-validation-firmware-config.json` | 更新的操作说明与静态 AArch64 工具；独立解析 newc，核验当前二进制、权限及零填充；未运行 Realm ioctl |

受保护内部控制内存的阶段验证（同一 run-id，控制机执行，均未部署）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心、实际 RTT/policy、固件 arena 与 ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-control-memory-final.log` | ASan/UBSan；513 页分批接管、类型/身份/重放/配额、部分 hide/clear/restore 失败保留、有界销毁、实际 RTT 叶子及 TLBI/回收 gate 模型；16 MiB arena 的全部 4096 个真实 MCU PTE/权限、启动前约束、复位和清零后恢复 |
| 实际平台后端集成 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-control-memory-integration-final.log` | 从实际后端写入的 AS0 根遍历 513 个捐赠页，跨 2 MiB 表边界；核对 RW/XN/NC 和 CPU 隐藏；启动、ACK 超时、部分安装失败均持有 backing；RESET/RELEASE 后有界清零恢复。CPU 权限和设备均为模型 |
| 原共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-control-memory.log` | 端点、共享、事件及交权策略；不等于私有任务执行 |
| RMM 与完整内存布局 | 前表同一构建和布局命令，各 rc=0；`rmm-control-memory-final.log`、`layout-control-memory-final.log` | 新核心、RSI、真实 RTT 后端完整 ARM64 链接，17 页 MCU 表池符合现有预留且不重叠 U-Boot；既有 RWX/build-id 警告保留 |
| 两种完整 Guest Image | 前表同一 Client/Proxy make 命令，各 rc=0；`guest-client-control-memory.log`、`guest-proxy-control-memory.log` | 控制内存 fd/禁止 mmap/typed cleanup、新 ioctl 和能力；未运行 Guest |
| 工具与 initrd | 前表同一工具和打包命令，各 rc=0；`tools-control-memory.log`、`initrd-control-memory.log`、`initrd-validation-control-memory.json` | 新诊断入口；独立 newc 解析核对当前三个 AArch64 二进制、目录/设备权限、名称和零填充，整体 4 KiB 对齐 |

Client 组资源的最新验证（同一 run-id；实际 RSI 和 GPU 均未运行）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心、组资源与 ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-group-memory-final.log` | ASan/UBSan；实际 Client/context/service 归属与引用、不同 Client 的 suspend/I/O 区间和真实 MCU PTE、每 Client 8 组/全局 32 组及 arena 耗尽、失败不覆盖在用区间、旧句柄代数、创建/销毁清零失败保留；2 MiB 以上 suspend 验证 512 页有界退休，复位后引用解除 |
| 实际平台后端集成 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-group-memory.log` | 实际后端 AS0 根上的两个 Client 组资源/页面，独立 context 引用、CPU 隐藏、旧句柄及 RESET 退休；确认组预留没有新增 MMIO 写入/任务门铃。设备和 CPU 权限仍为模型 |
| 共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-group-memory.log` | 原端点、共享、事件、交权和设备生命周期回归；不代表端到端 GPU 通过 |
| RMM 与布局 | 前表同一构建和布局命令，各 rc=0；`rmm-group-memory-final.log`、`layout-group-memory-final.log` | 新核心、context 引用和实际 REC/channel RSI 适配完整链接，38 MiB 预留/U-Boot 布局通过；既有 RWX/build-id 提示保留 |
| 两种完整 Guest Image | 前表同一 Client/Proxy make 命令，各 rc=0；`guest-client-group-memory.log`、`guest-proxy-group-memory.log` | 操作 30–32、能力 4096、诊断分派上限；未部署或执行 Guest ioctl |
| 工具与 initrd | 前表同一工具及打包命令，各 rc=0；`tools-group-memory.log`、`initrd-group-memory.log`、`initrd-validation-group-memory.json` | 新 group-selftest 编译，独立 newc 核验当前 AArch64 二进制、权限、名称与零填充；实际 RSI 探针未运行 |

正常 DRM 组接线的本轮检查（同一 run-id，全部控制机执行，尚未部署）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| RMM 核心与 ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-group-bridge-final.log` | 新操作 33/能力 8192；跨实际 Client、同 Client 不同 context、stream 替换、关闭/隔离组和旧代数拒绝，保留全部既有回归；ASan/UBSan |
| 实际 Guest 组函数 | `python3 scripts/check/check-gpu-group-bridge.py`，rc=0；`driver-group-bridge-final.log` | 当前真实辅助函数/Proxy 路径配测试替身；错误保留与清理顺序、不进入原生创建/销毁/执行、参数替换/重复拒绝、原生回滚；不是实际 RSI/GPU 证明 |
| 真实平台代码与共享回归 | `bash scripts/check/check-dma-guard.sh`、`bash scripts/check/check-rmm-xshm-events.sh`，各 rc=0；`dma-group-bridge.log`、`xshm-group-bridge.log` | 新组校验与实际 AS0 模型共用真实核心，确认校验不新增 MMIO 写入；既有共享/设备生命周期回归 |
| RMM 与布局 | 前述相同构建和布局命令，各 rc=0；`rmm-group-bridge.log`、`layout-group-bridge.log` | 新 RSI 完整 ARM64 链接与预留/U-Boot 布局；既有 RWX/build-id 提示保留 |
| 完整 Client/Proxy Image | 前述相同 make 命令，各 rc=0；`guest-client-group-bridge.log`、`guest-proxy-group-bridge-final.log` | 正常 DRM 私有组元数据接线、托管生命周期、RPC ABI 4 和能力协商；无编译器告警，未执行 Guest ioctl |
| 工具与 initrd | 前述相同工具和打包命令，各 rc=0；`tools-group-bridge.log`、`initrd-group-bridge.log`、`initrd-validation-group-bridge.json` | 服务专用 GROUP_VALIDATE 的 Client 拒绝探针已编译；独立 newc/当前 AArch64 二进制/权限/填充核验，实际探针未运行 |
| 补丁与空白检查 | `python3 opencca/scripts/setup/apply-local-patches.py --check`、三个组件 `git diff --check`，各 rc=0；`patches-group-bridge.log`、`diff-group-bridge.log` | 固定上游补丁仍全部 APPLIED；不是功能执行证据 |

受保护 ring 阶段的检查同样未部署：`unit-group-rings-complete.log`、`dma-group-rings-final.log`、`xshm-group-rings.log`、`rmm-group-rings-final.log`、两端 `guest-*-group-rings.log`、`tools-group-rings.log`、`layout-group-rings.log`、`patches-group-rings.log` 和 `initrd-group-rings.log` 均 rc=0；`initrd-validation-group-rings.json` 为当时包的独立解析记录。这些历史包的工具/镜像随后已更新，当前输入以任务就绪阶段清单为准。保留 `unit-group-rings-config.log` 的 rc=1：新逐队列校验使测试替身从 1 次变为 3 次，修正夹具预期后通过，未放宽产品校验。

任务暂存阶段的最新完整本地验证（同一 run-id，均未部署）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心、固件、ABI 及真实 Guest 函数模型 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-stage-final.log` | ASan/UBSan；完整跨页映射检查、缺页失败不占引用、跨 Client/service/group/context 替换拒绝、wrapper 指令与队列 sync 地址、受保护副本、映射冻结、失败不消费 MAP grant、每 Client 配额、取消/旧 token、已激活 context 拒绝取消及可信复位退休；保留全部既有 ring/PT/RTT/固件/Guest 模型回归 |
| 实际平台后端和共享回归 | `bash scripts/check/check-dma-guard.sh`、`bash scripts/check/check-rmm-xshm-events.sh`，各 rc=0；`dma-task-stage.log`、`xshm-task-stage.log` | 既有实际 AS0/Client PTE/CPU 隐藏/RESET/RELEASE 寄存器模型及共享身份/事件回归；新任务暂存本身由上一行核心验证，尚未在 GPU 发布 |
| RMM 和布局 | 前表同一构建/布局命令，各 rc=0；`rmm-task-stage.log`、`layout-task-stage.log` | 新 RSI 和任务池完整 ARM64 链接，38 MiB 预留和 U-Boot 布局通过；既有 RWX LOAD/build-id 提示仍保留 |
| 完整 Client/Proxy Image | 前表相同 make 命令，各 rc=0；`guest-client-task-stage.log`、`guest-proxy-task-stage.log` | 新 UAPI/诊断上限、禁止绕过内核托管组的调用边界；无编译器告警，未执行 Realm ioctl |
| 工具和 initrd | 前表相同工具/打包命令，各 rc=0；`tools-task-stage.log`、`initrd-task-stage.log`；`python3 build/rmm-client-bo-20261030/validate-task-stage-initrd.py`，rc=0，`initrd-validation-task-stage.json` | 已扩展 group-selftest 的 ARM64 二进制；独立 newc 解析核对当前文件、权限、AArch64 与零填充；实际任务探针未运行 |
| 补丁和空白检查 | `python3 opencca/scripts/setup/apply-local-patches.py --check`、三个组件 `git diff --check`，各 rc=0；新增源文件的 `git diff --no-index --check` 无空白错误（原始 rc=1 表示内容有差异）；`patches-task-stage.log`、`diff-task-stage.log` | 固定补丁仍全部 APPLIED；不代替 GPU 执行证据 |

停止态任务准备的当前检查（同一 run-id，控制机执行，未部署）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心及 ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-prepare-initial.log` | 新操作 38/能力 65536 的 Guest/RMM ABI 对齐；保留 PT/授权/RTT/固件/任务暂存和真实 Guest 函数 ASan/UBSan 回归 |
| 停止态准备与实际平台代码 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-prepare-lifetime.log` | 双 Client 各自根/PTE、受保护 ring 原始指令和 insert/extract、CS/CSG/AS/suspend 绑定、启动后描述符指针变化不被跟随、跨身份/context/group/token 拒绝、精确重试零写入、丢根/属性/不存在 AS/拓扑拒绝、部分 UPDATE/ring/I/O 失败持有、旧 token 与复位后清零恢复；全部为模型，无真实 GPU 执行 |
| 原共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-prepare.log` | 端点、共享、事件、交权及生命周期；不证明私有工作负载运行 |
| RMM 与布局 | 前表同一构建/布局命令，各 rc=0；`rmm-task-prepare.log`、`layout-task-prepare.log` | 完整 ARM64 RMM 和 38 MiB 预留/U-Boot 布局；既有 RWX/build-id 提示保留 |
| 两种完整 Guest Image | 前表相同 make 命令，各 rc=0；`guest-client-task-prepare.log`、`guest-proxy-task-prepare.log` | 新 UAPI 完整链接；未执行 Realm ioctl |
| 工具与 initrd | 前表同一工具/打包命令，各 rc=0；`tools-task-prepare.log`、`initrd-task-prepare.log`；独立解析 `validate-task-prepare-initrd.py`，rc=0，`initrd-validation-task-prepare.json` | 当前 AArch64 二进制、newc 权限/名称/填充与整体 4 KiB 对齐；实际探针未运行 |
| 补丁与空白检查 | `python3 opencca/scripts/setup/apply-local-patches.py --check`、三个组件及新增文件 diff 检查，各 rc=0；`patches-task-prepare.log`、`diff-task-prepare.log` | 固定补丁保持 APPLIED，不代替运行验证 |

保留 `dma-task-prepare-initial.log` 和 `dma-task-prepare-retry.log` 的 rc=134：新增循环在 RELEASE 后继续使用已结束服务，随后夹具又沿用上一个场景的控制写计数。调整 RELEASE 场景为最后，并按场景重置模型计数/故障开关后，最终通过；没有放宽产品授权或失败持有条件。

Client 就绪与启动前缓存交接的当前检查（同一 run-id，全部控制机执行）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心及 ABI/真实 Guest 函数 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-ready-final.log` | 新操作 39/能力 131072 的 Guest/RMM 对齐，保留全部 PT/RTT/授权/固件/暂存和 Guest 生命周期 ASan/UBSan 模型回归 |
| 实际平台与数据交接模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-ready-final.log` | 双 Client 精确物理页回调；513 页 9 次有界调用、另一 Client 2 页 8 次调用；内部 ring/completion 排除、未准备/服务冒充/跨 Client 拒绝、重复 READY 零同步、同 context 换 token 拒绝、同 Client 的 BO 别名 context 在同步前拒绝且原就绪保留、旧 READY token 拒绝、第二数据页同步失败及同步中出现 MMU 故障后的隔离与复位回收；无新增 MMIO/任务门铃。缓存指令及 GPU 均未在实体运行 |
| 共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-ready.log` | 既有端点、共享、事件与交权策略，不等于私有 GPU 任务运行 |
| RMM 与布局 | 前表相同构建/布局命令，各 rc=0；`rmm-task-ready-final.log`、`layout-task-ready.log` | 新 RSI 缓存后端及状态字段完整 ARM64 链接，38 MiB 预留/U-Boot 布局；既有 RWX/build-id 提示保留 |
| 完整 Client/Proxy Image | 前表相同 make 命令，各 rc=0；`guest-client-task-ready.log`、`guest-proxy-task-ready.log` | 新 UAPI 和内核调用边界；未部署或执行 Realm ioctl |
| 工具与 initrd | 前表相同工具/打包命令，各 rc=0；`tools-task-ready.log`、`initrd-task-ready.log`；独立 `validate-task-ready-initrd.py`，rc=0，`initrd-validation-task-ready.json` | 当前 AArch64 二进制、newc 权限/名称/填充、4 KiB 对齐；探针未运行 |
| 补丁与空白检查 | 前表同一检查，各 rc=0；`patches-task-ready.log`、`diff-task-ready.log` | 固定补丁和当前源码空白检查，不代替硬件验证 |

保留 `dma-task-ready-initial.log`、`dma-task-ready-retry.log` 的 rc=134：新增夹具先将映射缓存属性误传为 BO 访问权限，随后在 513 页 BO 尚未全部登记时尝试映射首批页。修正为 BO 仅声明访问权、全部登记后再分批映射，最终检查通过；未放宽产品的权限或完整登记要求。

可信任务 START 的当前检查（同一 run-id，全部控制机执行）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心及独立 Guest/RMM ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-start-final.log` | 新操作 40/能力 262144、既有私有 PT/RTT/精确授权/固件/Guest 组生命周期回归；ASan/UBSan |
| 实际平台后端与启动模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-start-final.log` | 保留全部 STOP/READY 回归；新增场景 13–32：双 Client 不同根/AS/CSG、身份/context/group/token 拒绝、未 READY/部分 READY 拒绝、CS→CSG→global clean→实际 MMIO 顺序、门铃位保留、精确 ACK/只读重试、无 ACK/缺 CS ACK/门铃失败/CSG 错状态、发布前后根与 MMU 故障、halt/pending doorbell/global ACK/AS 绑定/stream 故障、重试根丢失及引用保留。仅模拟 MCU ACK，不证明真实任务执行 |
| 共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-start.log` | 既有通道、事件及控制交权策略；不是私有应用回归 |
| RMM 构建与布局 | 前表同一构建/布局命令，各 rc=0；`rmm-task-start-final.log`、`layout-task-start.log` | 完整 ARM64 链接、38 MiB 预留与 U-Boot 布局；既有链接器提示保留 |
| 完整 Client/Proxy Image | 前表同一 make 命令，各 rc=0；`guest-client-task-start.log`、`guest-proxy-task-start.log` | 配套操作 40 UAPI，未部署或执行 Realm ioctl |
| 工具与 initrd | 前表同一构建/打包命令，各 rc=0；`tools-task-start.log`、`initrd-task-start.log`；独立 `validate-task-start-initrd.py`，rc=0，`initrd-validation-task-start.json` | 当前 AArch64 工具与 newc 内容/权限/零填充/4 KiB 对齐，未启动 |
| 固定补丁与空白检查 | 前表同一检查，各 rc=0；`patches-task-start.log`、`diff-task-start.log` | 预期上游补丁与当前修改范围；不替代硬件检查 |

可信 STOP/TERMINATE 与 AS 禁用的当前检查（同一 run-id，全部控制机执行）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心及独立 ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-quiesce-activation-guard.log` | 新操作 41/能力 524288，保留私有 PT/RTT/授权/固件和真实 Guest 组函数生命周期模型；ASan/UBSan |
| 实际平台后端与停止集成模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-quiesce-activation-guard.log` | 新增场景 33–47：双 Client 同时运行后单独停止且保留另一根/CSG；精确身份；STOP/TERMINATE ACK 在 FLUSH/UPDATE 前；伪造 completion=UINT64_MAX 不越过 ACK；ACK 缺失/错误、门铃失败、FLUSH/UPDATE 部分失败、停止前后 MMU/根异常、AS busy、重试根恢复/CSG 状态变化、同 context 第二组发布拒绝；全部引用保持。独立实际 MMIO 源模型验证 AS0/槽位/格式/根/别名拒绝、64 位根清零、UNMAPPED=1 和只读重试。真实 GPU 未运行 |
| 共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-quiesce.log` | 既有通道、事件及 MMIO 交权策略；不是私有应用回归 |
| RMM 与布局 | 前表同一构建/布局命令，各 rc=0；`rmm-task-quiesce-activation-guard.log`、`layout-task-quiesce-activation-guard.log` | 可信停止、AS 禁用与 RSI 完整 ARM64 链接及 38 MiB/U-Boot 布局核对；既有链接提示保留 |
| 完整 Client/Proxy Image | 前表同一 make 命令，各 rc=0；`guest-client-task-quiesce.log`、`guest-proxy-task-quiesce.log` | 配套 UAPI/诊断范围，未部署或执行 Realm ioctl |
| 工具/initrd/补丁/空白 | 前表同一命令，各 rc=0；`tools-task-quiesce.log`、`initrd-task-quiesce.log`、`patches-task-quiesce.log`、`diff-task-quiesce.log`；独立 `validate-task-quiesce-initrd.py`，rc=0 | AArch64 工具/newc 内容、权限、零填充与对齐；固定上游补丁；新增修改空白检查。硬件 NOT_RUN |

保留三个 rc=134 夹具失败：`dma-task-quiesce-initial.log` 在场景 44 只恢复根的低 32 位，而该根低位恰为零，未实际制造损坏；改成完整 64 位根。`dma-task-quiesce-retry.log` 和 `dma-task-quiesce-final.log` 在场景 47 已暂存任务、冻结映射后才配置第二组 ring；改成先配置全部组，再暂存任务。先由 `dma-task-quiesce-registration.log` rc=0 验证；最终复核补上旧 CONTEXT_ACTIVATE 的 QUIESCED 拒绝，并用禁止进入后端的断言验证，`dma-task-quiesce-activation-guard.log` rc=0。没有放宽根核验或映射冻结。

缓存归还与中止任务退休的当前检查（同一 run-id，全部控制机执行）：

| 检查 | 命令/退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 私有核心及独立 ABI | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-retire-final.log` | 新操作 42/43、能力 1048576/2097152；保留私有 PT/RTT/授权/固件及真实 Guest 组函数回归，ASan/UBSan |
| 实际平台与生命周期模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-retire-final.log` | 保留原场景 0–47，新增 48–65；完整 RETURN 后才清零/释放，清零后 AS/CSG/组再次使用与显式销毁、其他暂存 hold 保持，身份/重放/故障/失败引用保留。模型不执行 ARM 缓存指令或真实 GPU |
| 共享回归 | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-retire.log` | 既有通道、事件与控制交权，不替代私有应用测试 |
| RMM 与布局 | 前表同一命令，各 rc=0；`rmm-task-retire.log`、`layout-task-retire.log` | 实际 RSI 缓存失效后端、私有游标及退休逻辑完整 ARM64 链接，38 MiB/U-Boot 布局；既有 RWX/build-id 链接提示保留 |
| 完整 Client/Proxy Image | 前表同一 make 命令，分别 `-j4`，各 rc=0；`guest-client-task-retire-final.log`、`guest-proxy-task-retire-final.log` | 配套 UAPI 与内核类型边界；无新增编译器告警，未部署 |
| 工具与 initrd | 前表同一构建/打包命令，各 rc=0；`tools-task-retire-final.log`、`initrd-task-retire-final.log`；独立 `validate-task-retire-initrd.py`，rc=0 | 当前 AArch64 工具、新操作诊断范围、newc 内容/权限/填充/4 KiB 对齐；未启动 |
| 补丁与空白 | 前表同一检查，各 rc=0；`patches-task-retire.log`、`diff-task-retire.log` | 固定补丁仍 APPLIED；仅本轮 diff 空白与源码哈希核验 |

保留 `dma-task-retire-initial.log`、`dma-task-retire-retry.log` 的 rc=134：前者的 MCU 测试模型把首次 endpoint ACK 翻转值硬编码为 1，不支持复用后的反向翻转；改为检查相对旧 ACK 的翻转与 STOP 的保持语义。后者的 16 项 AS 命令记录数组不足以记录双 Client 的第二次生命周期，扩为 64 项。未放宽产品状态机或硬件 ACK 核验。`dma-task-retire-second-retry.log` 先通过，增加另一个暂存任务 hold 保持场景后由 `dma-task-retire-final.log` 通过。板端部署、720p 与私有任务执行仍为 NOT_RUN；无新增性能测量。

源码、两种配置、RMM ELF、Client/Proxy Image 与工具包的 SHA-256 已记录到 `build/rmm-client-bo-20261030/local-artifacts.json`，同时记录三个组件提交及 dirty 状态。Guest 实际 Image release 为 `6.12.0-g39d95dd028d4-dirty`，交叉 GCC 15.2；不是冻结运行组合的替换声明。

保留的失败证据包括 `guest-char-initial.log`（旧缓存 API）、`guest-private-objects.log`（头文件与旧 llseek）、`rmm-configure.log`（工具链前缀传递错误）、`rmm-build-arm64.log`（映射指针 const 类型）、`rmm-build-arm64-retry.log`（原 1024 页表池超预留）及 `tools-native-integration.log`（直接使用源树 DRM UAPI 时缺少 sparse 的 __user 注解定义）。该阶段修正为 512 页表池；当前为容纳固件运行副本再调整为 448 页，并重新完整构建、检查内存布局。失败日志没有被后续 PASS 覆盖。

`guest-client-image-map-auth.log` / `guest-proxy-image-map-auth.log` 保留授权字段直接扩展导致请求超出槽位的编译失败；紧凑页偏移编码修正后，两端完整 Image 的重试构建均 rc=0，未增大传输槽位或缩减批量操作上限。

`tools-firmware-snapshot.log` 与 `tools-firmware-snapshot-retry.log` 保留诊断工具读取循环的 GCC `stringop-overflow` 编译失败；改成每次最多读取完整固定缓冲区、按实际读取长度顺序上传后，最终构建 rc=0，没有屏蔽编译告警。

`dma-firmware-boot.log` 保留集成测试初次编译失败：设备回调结构原先只在旧测试函数内可见。改为由两个真实使用者共用的文件私有结构后，重试及最终检查均 rc=0。

`dma-firmware-config.log` 保留新增第三种集成场景首次运行的 rc=134：夹具在 RELEASE 已结束服务后又尝试下一次启动，身份断言正确拒绝。调整为先验证成功与 ACK 超时/RESET，再最后验证部分安装失败/RELEASE；同时去除之前跨场景累积启动计数造成的歧义。重试及最终检查 rc=0，没有放宽产品代码的服务身份或状态检查。

`dma-control-memory-integration.log` 保留控制内存阶段集成测试首次运行 rc=134：新增持有检查覆盖了保存启动结果的变量，导致失败分支检查错误。改为单独保存启动结果后，最终集成 rc=0；未放宽产品代码或失败持有策略。

硬件 glmark、Guest 探针（含控制内存和 group-selftest）、私有页 CPU 隔离、GPU 执行、恶意 Proxy/GPU 旁路、真实 GPC、板端 RELEASE 和异常退出回收均为 **NOT_RUN / 未完成**。主机单元测试不会证明真实硬件保护。

此前只读连接 `ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes root@192.168.31.18 'uname -r; test -e /dev/pmthor'` 的 rc=255 认证失败仍保存在 `hardware-access-control-isolate.log`。固件启动这一轮核对本机共享测试 skill 和进程环境后，Pi/RK 均没有已配置凭据；未发起新的密码登录，也没有部署或运行板端 GPU 测试。状态见 `hardware-access-firmware-boot-config.json`。

## 测量记录

改动目的｜实现 RMM 权威映射与 Client 私有数据页。

对照版本与分数 → 本版分数｜历史完整 720p 基线均值 1405；本版未测。

分差及百分比｜未测，不归因提分。

测试条件差异｜新架构尚在实施；不得继承旧硬件 PASS。

run-id、命令、退出码与日志｜见上表；补丁清单校验 rc=0。首次 Guest 对象构建发现缓存维护 API 不存在，后续发现头文件/旧 llseek 接口问题，均修正并保留失败日志。已改源码，未部署运行载荷，无新增性能测量。

保留/撤回/待验证｜待验证；实现范围与未完成项逐项更新。

## 本轮可信完成与本地同步接线验证（2026-10-30）

改动目的｜新增 RMM 可信完成观察，隔离私有同步对象的完成来源｜对照版本与分数 → 本版分数：上一阶段 43 项操作/4194299 能力 → 当前 44 项操作/8388603 能力；两版 glmark 均未测｜分差及百分比：N/A｜测试条件：仅控制机构建与模型，未部署、无新增性能测量｜run-id：`rmm-client-bo-20261030`｜保留，正常 DRM 提交、异步绑定与实体 GPU 验证待完成。

| 检查 | 命令与退出码 | 日志（均在上述 run-id 目录） |
| --- | --- | --- |
| 私有 PT/固件/ABI/实际组桥接 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0 | `unit-task-complete.log` |
| 实际平台源 MMIO/任务生命周期模型 | `bash scripts/check/check-dma-guard.sh`，rc=0 | `dma-task-complete-final.log`；新增 66–93 场景全部通过，首轮 `dma-task-complete-initial.log` 亦 rc=0 |
| RMM ARM64 | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，rc=0 | `rmm-task-complete.log`；既有 RWX LOAD/build-id 链接告警保留 |
| 完整 Client/Proxy Image | 上文完整 make 命令，分别 `O=.../guest-client`、`O=.../guest-proxy`、`-j4`，均 rc=0 | `guest-client-task-complete-local-sync.log`、`guest-proxy-task-complete-local-sync.log` |
| 原共享回归/布局/补丁 | 上文对应脚本，均 rc=0 | `xshm-task-complete.log`、`layout-task-complete.log`、`patches-task-complete.log` |
| 静态工具与 initrd | 上文 build-realm-xshm 和 build-realm-xshm-initrd 命令，均 rc=0 | `tools-task-complete-local-sync.log`、`initrd-task-complete-local-sync.log`；独立 newc 校验 `initrd-validation-task-complete.json` |
| 阶段差异与哈希清单 | `python3 build/rmm-client-bo-20261030/refresh-task-complete-evidence.py`，rc=0 | `task-complete-review/files.json`、`manifest-validation-task-complete.json`；保留旧失败/旧阶段记录 |
| Realm/真实 GPU/720p/攻击负例 | NOT_RUN | 尚未部署；不能继承历史 1405 或旧 PASS |

## 私有绑定 worker 阶段验证

改动目的｜接通私有同步/异步 VM_BIND 本地依赖与实际 PTE 核验，并修复时间线当前点错误丢失｜对照版本与分数 → 本版分数：44 项操作/8388603 能力 → 45 项操作/16777211 能力；两版 glmark 均未测｜分差及百分比：N/A｜测试条件差异：仅控制机构建和模型，未部署、无新增性能测量｜run-id：`rmm-client-bo-20261030`｜保留；普通 GROUP_SUBMIT、受限驱动服务和真实 GPU 验证待完成。

以下日志均位于 `build/rmm-client-bo-20261030/`；各已执行项退出码为 0，旧失败证据原样保留。

| 检查 | 命令／日志 | 范围 |
| --- | --- | --- |
| RMM 核心与实际 Client 函数 | `bash scripts/check/check-rmm-gpu-private.sh`；`unit-private-bind-chain-final.log` | RMM45 实际 PTE/epoch/权限与损坏表检查；25 项实际 Client 函数 ASan/UBSan 替身场景；不证明 Linux 并发 |
| 平台后端模型 | `bash scripts/check/check-dma-guard.sh`；`dma-private-bind-final.log` | 实际平台源代码与既有启动/停止/完成/归还/退休场景；模型不等于 GPU 运行 |
| 共享路径与补丁 | `bash scripts/check/check-rmm-xshm-events.sh`；`xshm-private-bind-final.log`；`python3 opencca/scripts/setup/apply-local-patches.py --check`；`patches-private-bind.log` | 共享回归及固定上游补丁状态 |
| RMM 和完整两端 Image | 前述完整构建命令，Guest `-j4`；`rmm-private-bind-final.log`、`guest-client-private-bind-chain-final.log`、`guest-proxy-private-bind-chain-final.log` | 完整链接；Guest 无新增编译警告；RMM 初次构建的 RWX LOAD/build-id 丢弃提示保留于 `rmm-private-bind.log` |
| 工具／固件布局／initrd | `tools-private-bind-final.log`、`layout-private-bind-final.log`、`initrd-private-bind-final.log`；`python3 build/rmm-client-bo-20261030/validate-private-bind-initrd.py` | 新运行探针已编译；独立 newc 解析核验当前 AArch64 二进制、权限和填充；Realm 探针 NOT_RUN |
| 源码与产物清单 | `private-bind-review/`、`local-artifacts.json`、`requirements-audit.json`、`manifest-validation-private-bind.json` | 相对 `before-private-bind/` 逐文件审查及独立 SHA 核验；deployed/goal_complete 均为 false |

## 受限原生服务阶段验证

改动目的｜交权后保留私有对象/GPUVA 驱动服务并移除原生硬件入口｜对照版本与分数 → 本版分数：私有绑定 worker → 受限服务候选；两版 glmark 均未测｜分差及百分比：N/A｜测试条件差异：仅控制机构建/模型，未部署、无新增性能测量｜run-id：`rmm-client-bo-20261030`｜保留；完整私有应用未完成。

- `bash scripts/check/check-rmm-gpu-private.sh`，rc=0，`unit-restricted-service-mmu-final.log`：含 RMM 核心、25 个绑定和 26 个受限服务源码替身场景。
- 完整两端 Image、静态工具、initrd 构建 rc=0，日志 `guest-client-restricted-service-final.log`、`guest-proxy-restricted-service-initial.log`、`tools-restricted-service-final.log`、`initrd-restricted-service-final.log`；Guest/工具无新增编译警告。RMM 本阶段未改，使用上一阶段已核验产物。
- 独立 initrd 校验 `python3 build/rmm-client-bo-20261030/validate-restricted-service-initrd.py`，rc=0；源码审查和 SHA 记录见 `restricted-service-review/`、`manifest-validation-restricted-service.json`。硬件/720p/私有应用均 NOT_RUN。
- 保留 `rmm-service-unit-initial.log` rc=1（替身编译遗漏 `__user` 定义）和 `rmm-service-unit-mmu-final.log` rc=1（提取器误匹配函数文档）；修正测试编译参数与定义匹配，不放宽产品权限或编译检查。

## 多队列批次阶段验证

改动目的｜将可信任务生命周期扩展到完整多队列批次，避免跨队列依赖被串行等待阻塞｜对照版本与分数 → 本版分数：受限服务候选/操作 45 → 批次候选/操作 46；两版 glmark 均未测，历史 1405 仅作旧共享架构参考｜分差及百分比：N/A｜测试条件差异：控制机 ASan/UBSan、实际平台源寄存器模型及 ARM64 构建，未部署、无新增性能测量｜run-id：`rmm-client-bo-20261030`｜保留，正常 DRM/私有应用与硬件验收待完成。

| 检查 | 命令、退出码与日志（均在 run-id 目录） | 实际覆盖 |
| --- | --- | --- |
| 私有核心/固件/ABI/Guest 替身 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-batch-final-reviewed.log` | 批次 admission 与总页数限制、原 PT/RTT/ring 回归，以及 25 个 bind/26 个 service 场景 |
| 实际平台源代码模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-batch-final.log` | 新增 18 个批次场景，保留已有单条及双 Client 生命周期；不是 GPU 执行 |
| RMM、布局、共享、补丁 | 既有对应命令，各 rc=0；`rmm-task-batch-final.log`、`layout-task-batch.log`、`xshm-task-batch.log`、`patches-task-batch.log` | 固定预留内完整链接、U-Boot 不重叠、原共享和固定补丁；既有 RWX/build-id 提示保留 |
| 完整 Client/Proxy Image | 前述完整 make 命令，各 rc=0；`guest-client-task-batch.log`、`guest-proxy-task-batch.log` | 新操作/私有输入数组复制及生命周期限制；无新增编译警告 |
| 静态工具和 initrd | 前述工具/打包命令，各 rc=0；`tools-task-batch.log`、`initrd-task-batch.log`；独立校验 `initrd-validation-task-batch.json` | 批次运行探针已构建；独立核对包内 AArch64 二进制、权限和填充；Realm 运行 NOT_RUN |
| 差异与证据 | `task-batch-review/files.json`、`local-artifacts.json`、`requirements-audit.json`、`manifest-validation-task-batch.json` | 相对 before-task-batch 的逐文件差异，当前源码/产物 SHA；deployed/goal_complete=false |
| 硬件/攻击负例/720p/完整私有应用 | NOT_RUN | 不继承历史成绩或旧 PASS |

保留失败：`rmm-task-batch-initial.log` rc=2，完整保存额外 wrapper 超出现有 RMM 预留；改为紧凑描述和生成时展开后完整链接通过。`dma-task-batch-second.log`、`dma-task-batch-debug.log` rc=134，新增测试只检查了 64 位根的低 32 位，而模型合法根为 0x100000000；修正测试检查完整根，产品权限未放宽。旧日志不覆盖或删除。

## 内核任务托管与 Proxy 控制阶段验证

run-id 仍为 `rmm-client-bo-20261030`，仅控制机检查，未部署。RMM 私有 ABI 2、总能力 33554427、完整执行位清零；RPC ABI 4 保持不变，新增会话特性位只表达受限控制接口可用。

| 检查 | 命令、退出码与日志 | 实际覆盖 |
| --- | --- | --- |
| 真实任务 API/Proxy RPC/诊断 ioctl | `python3 scripts/check/check-gpu-task-bridge.py`，rc=0；`unit-task-bridge-third.log` | 54 个 ASan/UBSan 内核、RSI、传输替身场景：输入快照、分配失败、零/重复 token、typed 回复、分批就绪/退休、诊断接口权限、会话/通道/私有 VM、失联不重放、准备后放弃保留；未执行真实 Linux 并发/RSI/DRM 调度/GPU |
| 完整私有回归 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-bridge-final.log` | 新增任务测试纳入主入口，保留组桥接、25 个私有 bind、26 个受限 service 场景及核心/固件/ABI |
| 实际平台后端与共享回归 | `bash scripts/check/check-dma-guard.sh`、`bash scripts/check/check-rmm-xshm-events.sh`，各 rc=0；`dma-task-bridge.log`、`xshm-task-bridge.log` | 原单/多队列及双 Client 模型、共享授权和 IRQ 核心回归；不是硬件执行 |
| 完整 Client/Proxy Image | 前述完整 make 命令，使用 `-j4`，各 rc=0；`guest-client-task-bridge-final.log`、`guest-proxy-task-bridge-final.log` | 任务 API、协议、实际 Proxy 分发均完整链接；未部署 |
| 固定补丁与差异/证据 | 补丁清单校验 rc=0，`patches-task-bridge.log`；`task-bridge-review/files.json`、`manifest-validation-task-bridge.json` | 相对 before-task-bridge 保存逐文件差异、当前源码与构建 SHA；RMM/工具/initrd 本阶段未改，按既有 SHA 重新核对；完整目标仍 INCOMPLETE |

首次任务测试 `unit-task-bridge-initial.log` rc=1：新测试将计数器命名为 C 标准库函数 puts，编译冲突；已重命名并保留失败证据。`unit-task-bridge-second.log` rc=0/41 场景，随后扩展诊断 ioctl、零/重复 token 到 54 场景，第三轮及主入口通过。

性能记录：改动目的为 Client 托管任务与受限 Proxy 控制接线；历史完整720p均值1405 → 本版未测，绝对/百分比变化未测。实现与历史共享路径不同，不继承旧 PASS，不归因提分；状态为待验证。普通私有 GROUP_SUBMIT/任务 fence、私有 tiler heap、runner 与真实 Realm/GPU 验收均未完成。

## 初始私有 heap 阶段验证

改动目的｜将初始 tiler heap 数据分配与地址管理迁至 Client，真实 PT/释放仍经 RMM｜对照版本与分数 → 本版分数：任务托管/受限 RPC 候选 → 初始私有 heap 候选，两版完整720p均未测；旧共享架构1405仅历史参考｜绝对/百分比变化：未测｜条件差异：源码、控制机联合核心模型与 ARM64 构建，未部署｜run-id：`rmm-client-bo-20261030`｜保留；动态增长、完整提交和实体硬件验收待完成。

| 检查 | 命令、退出码、日志（run-id 目录） | 范围 |
| --- | --- | --- |
| 初始 heap 联合核心检查 | `python3 scripts/check/check-gpu-private-heap.py`，rc=0；`heap-unit-va-final.log` | 52 个实际前端/内核函数与真实 RMM PT/ref 核心场景，平台/内核为替身；无 GPU 执行 |
| 私有绑定边界 | `python3 scripts/check/check-gpu-private-bind.py`，rc=0；`bind-private-heap-va-final.log` | 27 个实际 worker/planner/check 场景，补用户范围边界与跨界操作在授权/RPC 前拒绝 |
| 完整私有主入口 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-private-heap-va-final.log` | 新 heap 测试已接主入口；保留任务54、服务26及组/核心/固件/ABI 回归 |
| 两端完整 Image | 前述完整 make 命令 `-j4`，各 rc=0；`guest-client-private-heap-final.log`、`guest-proxy-private-heap-final.log` | Client 本地创建/销毁、VA 边界、私有清理链与 CONFIG 头文件；无新增编译警告，未部署 |
| 工具与 initrd | 既有工具/打包命令，各 rc=0；`tools-private-heap.log`、`initrd-private-heap.log`、`initrd-validation-private-heap.json` | 新真实 DRM 初始 heap 探针编译/打包；独立核对 newc、AArch64、权限和填充；运行 NOT_RUN |
| 固定补丁、差异及输入 | 补丁清单校验 rc=0；`patches-private-heap.log`；`private-heap-review/`、`manifest-validation-private-heap.json` | before-private-heap 的逐文件差异、当前 SHA 与完整性；RMM 源码/ELF、DMA/共享核心本阶段未改，核对既有 SHA，未重复硬件测试 |

保留失败：`heap-unit-initial.log` rc=1（提取器匹配到声明）；`heap-unit-second.log` rc=1（测试类型/宏/函数命名冲突和缩进）；`heap-unit-third.log` rc=1（fixture 误以为未激活 context 建表会调用硬件同步）；`heap-unit-fourth.log` rc=1（任务 hold 测试漏先获取真实 group 引用）。后两项通过实际核心 activate/context_hold 路径修正测试前提，没有放宽产品权限。`group-private-heap-initial.log` rc=1（空 heap 状态替身未标记未使用参数）；`bind-private-heap-va.log` rc=1（新增测试误写输入数组变量名）；后续主入口通过，旧失败不覆盖。

整体状态仍 INCOMPLETE。任务逐 job 依赖/信号与跨提交进度、完整私有 tiler OOM 增长、runner/死亡 Realm 清理，以及真实 Realm/GPU/缓存/攻击负例和720p门槛均未完成或未验证。


## 初始 heap 与精确回收的本地验证（未部署）

run-id：`rmm-client-bo-20261030`；日志与产物根目录：`build/rmm-client-bo-20261030/`。前一阶段初始heap的52个场景为历史记录，本阶段最终75个；RMM/Guest真实源码已经改变，旧723项证据清单不继续作为当前状态使用。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 完整私有回归 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-private-heap-exact-unmap-final.log` | heap75、bind27、task54、service26及实际核心/固件/ABI检查 |
| 原缺陷复现 | `python3 build/rmm-client-bo-20261030/regression-private-heap-exact-unmap.py`，wrapper rc=0；`heap-exact-unmap-regression.log` | 备份的旧回收函数在新冲突测试退出−6；预期失败保存于`private-heap-exact-unmap-regression/expected-failure.log` |
| DMA/平台模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-private-heap-exact-unmap.log` | 含18个多队列真实平台源模型，不是实机 |
| 共享/可信IRQ | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-private-heap-exact-unmap.log` | 共享、设备租约、服务隔离与IRQ策略回归 |
| RMM ARM64 | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，rc=0；`rmm-private-heap-exact-unmap.log` | 新核心和RSI适配器实际链接；保留已有RWX/build-id链接器警告 |
| 两端Image | 既有完整make命令，角色`guest-client`/`guest-proxy`、`-j4`，各rc=0；`guest-client-private-heap-exact-unmap-final.log`、`guest-proxy-private-heap-exact-unmap-final.log` | 私有能力握手和精确回收；Proxy最终增量已是最新，无需重复编译 |
| 工具/initrd | 既有工具/打包命令，各rc=0；`tools-private-heap-exact-unmap.log`、`initrd-private-heap-exact-unmap.log` | 新RSI探针仅编译、未执行 |
| 独立initrd核对 | `python3 build/rmm-client-bo-20261030/validate-private-heap-exact-unmap-initrd.py`，rc=0；`initrd-validation-private-heap-exact-unmap.json` | newc、当前AArch64二进制、权限及零填充 |
| 布局/补丁 | 既有固件布局及固定补丁检查，各rc=0；`layout-private-heap-exact-unmap.log`、`patches-private-heap-exact-unmap.log` | 仍符合38MiB RMM保留，不改固定上游补丁 |
| 源码/证据 | 差异和SHA清单；`private-heap-review/`、`manifest-validation-private-heap.json` | 当前与两阶段备份对照；独立核验见`independent-private-heap-final.json` |
| Realm/GPU/性能 | **NOT_RUN** | 未登录硬件、未部署；不将模型/构建视为GPU私有执行 |

统一记录：修复初始heap及不确定MAP回收归属｜历史共享1405分（不同架构，仅参考）→本版未测｜分差/百分比N/A｜控制机源码/模型/构建，未部署｜上述run-id、命令、rc与日志｜**保留源码，完整私有执行待验证**。本阶段改动运行代码，但无新增性能测量，不宣称提分。

## 逐成员进度阶段验证（控制机，未部署）

run-id：`rmm-client-bo-20261030`，证据根目录：`build/rmm-client-bo-20261030/`。旧845项清单保存在before-task-progress，不代表修改后的源码。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 真实平台源模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-progress-final.log` | 原多队列18项+新增进度18项，共36项；原单/双Client生命周期模型保留 |
| 完整私有检查 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-progress-final.log` | 任务桥64、heap75、bind27、service26及核心/固件/RTT/ABI |
| 共享/IRQ | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-progress.log` | 端点、共享、交权和事件策略 |
| RMM/布局 | 既有cmake及固件布局命令，各rc=0；`rmm-task-progress.log`、`layout-task-progress.log` | ARM64核心/RSI链接，保持38MiB预留；已有RWX/build-id提示保留 |
| 两端Image | 既有完整make命令，`guest-client`/`guest-proxy`、`-j4`，各rc=0；`guest-client-task-progress-final.log`、`guest-proxy-task-progress-final.log` | 最终无编译告警；引用计数结果用于触发有界BO回收，仍必须经过RMM销毁授权 |
| 工具/initrd | 既有工具/打包命令，各rc=0；`tools-task-progress.log`、`initrd-task-progress.log` | 未启动/取消token的进度负例探针仅编译、未运行 |
| 独立initrd | `python3 build/rmm-client-bo-20261030/validate-task-progress-initrd.py`，rc=0；`initrd-validation-task-progress.json` | 实际newc、当前AArch64二进制、权限及零填充 |
| 补丁/差异/证据 | 补丁和组件差异检查rc=0；`patches-task-progress.log`、`task-progress-review/`、`manifest-validation-task-progress.json`；独立核验`independent-task-progress-final.json` | 与备份逐文件diff及当前SHA核对 |
| Realm/GPU/性能 | **NOT_RUN** | 未登录硬件、未部署，正常私有GROUP_SUBMIT仍未接通 |

保留`task-progress-backend-initial.log`，rc=134：测试矩阵扩展后未将RELEASE末例移到新末尾，后续用例因服务身份已释放触发断言；修正矩阵次序后通过，未放宽产品校验。两端`guest-*-task-progress.log`虽rc=0，但暴露旧heap丢弃must-check引用计数结果的告警；改为最后引用触发有界可信BO回收后，完整私有回归及最终两端Image重新通过。接口初始64项及后台第二轮成功记录也保留，不覆盖中间失败/告警。

统一记录：逐成员可信执行进度，为正常逐job依赖/fence提供观察基础｜历史共享1405分（不同架构，仅参考）→本版未测｜分差及百分比N/A｜控制机模型/构建，未部署｜上述run-id、命令、rc与日志｜**保留源码，完整私有执行待完成和验证**。本阶段修改运行代码，无新增性能测量，不宣称提分。

## 逐队列前缀发布阶段验证（控制机，未部署）

run-id：`rmm-client-bo-20261030`，证据根目录：`build/rmm-client-bo-20261030/`。上一阶段900项哈希清单与源码已保存至`before-task-publication/`；该清单不代表本阶段修改后的输入。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 真实平台源模型 | `bash scripts/check/check-dma-guard.sh`，rc=0；`dma-task-publication-final.log` | 多队列54项，其中成员进度18项、前缀发布18项；空START、跨队列独立前缀、禁止同队列越序/撤回、身份/范围/未READY拒绝、旧INSERT、读写失败、部分发布、通知失败/ACK超时、根/选中及未选中CS错误、精确重试仍核验pending状态ACK、六成员完成/退休；单/双Client既有模型保留 |
| 完整私有检查 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-task-publication-reviewed.log` | 任务桥74、heap75、bind27、service26及实际核心/固件/RTT/ABI；typed暂存固定DEFERRED，发布回复/诊断边界检查 |
| 共享/IRQ | `bash scripts/check/check-rmm-xshm-events.sh`，rc=0；`xshm-task-publication.log` | 端点、共享、交权与事件策略；不是正常私有应用验收 |
| RMM/布局 | 既有cmake及布局命令，各rc=0；`rmm-task-publication-reviewed.log`、`layout-task-publication-reviewed.log` | ARM64完整链接，38MiB预留不变；已有RWX LOAD/build-id链接提示保留 |
| 完整两端Image | 既有make命令，Client/Proxy各rc=0；`guest-client-task-publication-final.log`、`guest-proxy-task-publication-final.log` | 最终无编译器告警/错误；未部署或执行Realm ioctl |
| 工具/initrd/独立解析 | 既有工具/打包命令和新`validate-task-publication-initrd.py`，各rc=0；`tools-task-publication-final.log`、`initrd-task-publication-final.log`、`initrd-independent-task-publication-final.log`、`initrd-validation-task-publication.json` | 发布前置条件拒绝、DEFERRED暂存探针仅编译；实际newc、当前AArch64工具、权限、零填充和对齐核对 |
| 固定补丁与差异 | 补丁清单、组件diff及逐文件no-index检查rc=0；`patches-task-publication.log`、`task-publication-review/` | 原始备份及精确源差异；不将整工作树既有修改归于本阶段 |
| 证据独立核验 | `refresh-task-publication-evidence.py`、`verify-task-publication-final.py`，rc=0；`manifest-validation-task-publication.json`、`independent-task-publication-final.json` | 当前源/二进制/日志全部SHA核对，能力由实际头文件和RSI表达式计算，完整执行位清零及goal未完成状态检查 |
| Realm/GPU/完整720p | **NOT_RUN** | 未登录硬件、未部署；正常私有GROUP_SUBMIT仍返回EOPNOTSUPP |

保留失败：`unit-task-publication-initial.log`，rc=1，新发布函数提前使用后文的read_control导致隐式声明，移动同一辅助函数后通过；`dma-task-publication-initial.log`，rc=134，失败通知夹具误将首次START也拒绝，修正为只在发布阶段注入失败后通过。`dma-task-publication-second.log`及最初成功构建亦保留，最终复核将精确重试的ACK检查放到成功返回之前，并强化相应模型断言；未放宽产品校验。

统一记录：将同批成员的执行可见范围交由实际Client/RMM控制，避免依赖未满足时被整批启动｜历史共享1405分（不同架构，仅参考）→本版未测｜绝对/百分比变化N/A｜控制机模型/完整构建，未部署｜上述run-id、命令、退出码与日志｜**保留源码，完整私有执行仍待完成和验证**。本阶段修改运行代码，无新增性能测量，不宣称提分。


## 正常私有提交与就绪切片（控制机，未部署）

上一轮仅回答页表地址与访问权限的区别，没有改变代码或验证状态，分类为NO_PROGRESS。本阶段先独立核对上一候选970项SHA及能力268435451，再保存`before-private-submit/`输入，继续实现普通提交路径；本阶段分类PROGRESS，整体goal仍未完成。

### 任务与依赖如何接入

私有模式的标准`GROUP_SUBMIT`转至Client本地planner。用户提交、sync操作和任务入口仅复制一次；先取得全部输出syncobj与原始point fence，再按job数组顺序解析wait和更新局部signal，全部成功后一次发布。每个job有独立的本地dma_fence，同队列通过前一fence跨IOCTL保持FIFO；提交失败不会更新公开输出或队列尾。保留原先共享模式的PLAN_EXEC路径，其完成cookie不进入私有执行依据。

GPU worker独立于VM_BIND的有序worker，不在等待外部依赖时阻塞线程。它扫描整个待运行列表，可绕过等待中的队列、Group或后续提交；同Group最多选六个独立就绪队列头，共用一个RMM token。不会把存在未完成依赖的成员也一起启动，因此同IOCTL的前后依赖仍能推进。已就绪队列的后续job在前一slice退休后再进入下一slice。

每片依次执行`STAGE → Proxy PREPARE → Client READY → Client PUBLISH → Proxy START → Client COMPLETE → Client RETURN → Client RETIRE`。Proxy RPC只含会话、Group和opaque token，不包含数据HPA、页表根或命令地址；可信typed接口继续验证RMM回复。只有COMPLETE、全部缓存RETURN和RETIRE都成功，才signal本片各job成功fence。各成员本来相互独立，因此共享这一归还点不引入片内依赖死锁；跨片仍保留各job独立输出。

成功阶段之间不强制定时等待；外部依赖及可信INCOMPLETE观察通过延迟work有界轮询。没有增加任意MMIO或Proxy完成权限。PREPARE/START的错误、畸形回复或丢失不重放，最多申请一次QUIESCE；即便QUIESCE成功也不把中止当作完成。typed task_put继续保留未退休RMM任务/backing，file停止接纳后续任务，已排队任务取消。关闭时先取消GPU工作/fence再排空VM_BIND worker，避免bind等待GPU任务导致关闭卡住；有待处理/运行GPU任务的VM不能销毁并复用其ID。Group销毁通过job引用延迟实际RPC和私有资源释放。

### 当前证据及尚未完成的部分

run-id：`rmm-client-bo-20261030`，证据根目录：`build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 新提交调度 | `python3 scripts/check/check-gpu-private-submit.py`，rc=0；`submit-unit-expanded.log` | 58个实际Client planner/worker/Group回收函数场景；binary/timeline、同队列FIFO、跨队列/Group/VM与跨提交就绪、最大依赖、私有快照、分阶段成功门槛、超时/关闭/畸形回复和丢失响应不重放；锁、Linux fence、typed RMM与GPU为替身 |
| 完整私有检查 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-private-submit-expanded.log` | 新submit58、task74、heap75、bind27、service26及原核心/固件/RTT/ABI；不宣称真实Linux并发通过 |
| 完整两端Image | 前述make命令，Client/Proxy各rc=0；`guest-client-private-submit-final.log`、`guest-proxy-private-submit-final.log` | 当前真实ARM64源码和初始化/销毁调用链完整编译链接，无新增编译告警；未部署 |
| 静态工具及initrd | 前述build-realm-xshm与打包命令，各rc=0；`tools-private-submit.log`、`initrd-private-submit.log` | 新`drm-submit-selftest`要求私有模式，经正常IOCTL运行两队列/跨提交依赖，检查三个精确job的sync_file状态；零长度用户流仍执行受保护wrapper，不验证shader计算；运行NOT_RUN |
| 独立initrd | `python3 build/rmm-client-bo-20261030/validate-private-submit-initrd.py`，rc=0；`initrd-independent-private-submit.log`、`initrd-validation-private-submit.json` | 实际newc内容、当前AArch64二进制、权限及零填充 |
| 固定补丁、差异与输入 | `python3 opencca/scripts/setup/apply-local-patches.py --check`，rc=0；`patches-private-submit.log`、`private-submit-review/`、`manifest-validation-private-submit.json` | RMM/平台生产源码未改，保留并核对上一阶段DMA/IRQ/RMM构建/布局证据；当前Guest差异与SHA单列 |
| 真正Realm/GPU/缓存/攻击与完整720p | **NOT_RUN** | 未登录或部署硬件；不据模型或新探针编译宣称应用可运行或隔离成立 |

保留失败：`submit-unit-initial.log` rc=1，提取器先于宏定义引入Group结构、测试缩进及产品pending/count比较的有符号告警；修正宏顺序/缩进，并显式按非负有界pending计数比较。`submit-unit-second.log` rc=1，关闭测试将已退休的第七次tick也当成运行中任务，错误期待取消；只覆盖七个仍未完成的关闭位置后通过。`submit-unit-third.log`、`submit-unit-reviewed.log`保留早期54项成功，最终扩展为58项；没有用最终通过覆盖中间失败。

**范围仍不完整：** 原生VM_BIND／BO reservation的隐式同步兼容尚未完整接入，活跃lease与映射并发可能返回EBUSY；不能声称任意Mesa使用方式都已兼容。每个file当前同一时间仅有一个slice，仍对整个GPUVM交接CPU/GPU缓存；运行中跨批追加、细粒度交接与性能需要继续实现/评估。私有tiler动态OOM扩容、runner私有启动/服务bootstrap参数、死亡Realm回收、真实Client/Proxy故障攻击、真实缓存正确性和GPU计算/图形验收均未完成。ABI2/RPC4及能力268435451不变，完整执行能力位仍清零；整体goal保持active。

统一记录：接通私有正常提交的逐job依赖/fence和可信执行生命周期｜上一发布候选未测，旧共享1405仅历史参考 → 本版未测｜绝对及百分比变化N/A｜控制机源码替身与ARM64完整构建，未部署｜上述run-id、命令、rc与日志｜保留源码，隐式同步兼容和完整硬件验收待完成。本阶段修改运行代码，无新增性能测量，不宣称提分。


## 映射与执行互斥（控制机，未部署）

上一阶段为PROGRESS：正常私有GROUP_SUBMIT、逐任务fence与就绪切片源码已接入，58项替身与完整构建通过。本阶段开始前独立重核其1017项SHA、ABI2/RPC4和能力268435451，再保留`before-private-mapping-gate/`输入；本阶段继续为PROGRESS，整体goal仍未完成。

### 为什么不直接等待所有reservation

重新核对实际原生源码：`panthor_vm_bind_job_update_resvs()`明确注明“Explicit sync”，VM/BO使用`DMA_RESV_USAGE_BOOKKEEP`；`panthor_job_update_resvs()`同样登记BOOKKEEP。任务依赖由`panthor_submit_ctx_add_sync_deps_to_job()`按显式syncobj建立。因此前一阶段将问题概括为“隐式同步未接入”不准确：直接让bind等待全部排队GPU任务会凭空引入依赖，可能使等待本次bind的GPU任务与bind互相阻塞。这里保留原生显式依赖，解决当前整GPUVM租约下的执行互斥和生命周期。

### 当前实现

- MAP/UNMAP执行前以及正常私有TILER_HEAP_CREATE/DESTROY前，调用`panthor_client_private_mapping_lock()`。它在`private_gpu_lock`下核对实际本地run的VM，只等待已经选中的同VM任务；不等待尚未启动的排队任务。选中到STAGE之间也受同一锁保护，没有“检查完未运行，另一线程立即冻结context”的窗口。
- 等待时释放GPU锁，暂存精确job fence强引用；GPU worker可继续COMPLETE、完整RETURN和RETIRE。唤醒后重新核对run身份、关闭和file失败状态，fence自身不是映射权限。失败不把不确定租约改成可用；RMM任务/backing仍独立保留。
- 栈上等待票据登记VM。就绪picker跳过该VM的新片，防止源源不断的GPU提交让映射一直饿死；不同VM仍可被选择。多个等待者各有票据，直到各自取得临界区或失败才删除，临界区由同一mutex串行。
- 成功返回时GPU锁继续持有，覆盖精确Client授权、Proxy VM_BIND RPC、未消费grant取消和真实PTE/epoch检查，结束后释放；heap的真实RMM建表/撤销也在该临界区。该锁只协调Client本地正常路径，RMM仍验证真实身份、对象、权限和冻结状态。
- SYNC_ONLY不编辑映射，只完成既有显式依赖，不申请映射锁。同步VM_BIND现在在排队/输出发布前拒绝显式sync对象，与原生同步接口一致。

当前slice中的job相互独立，并在同一GPU锁内发布完成/清理，等待其中第一个job后仍重新取得锁核对整run，因而不会在其余成员退休前进入映射临界区。正常bind与heap变更不再因为本file同VM活跃slice而直接撞上RMM冻结状态；不意味着其他错误/配额/授权拒绝也能被忽略。跨GPUVM缓存别名、运行中跨批追加与动态OOM增长仍需各自的可信处理，不能借本地锁放宽RMM检查。

### 验证与证据

run-id：`rmm-client-bo-20261030`；日志根目录：`build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 实际提交/互斥函数 | `python3 scripts/check/check-gpu-private-submit.py`，rc=0；`submit-mapping-gate-expanded.log` | 76项，新增18项：等待整片可信退休、待依赖job不成为假依赖、另一VM不必等待、超时/关闭/故障清理、同VM不能抢先且另一VM继续、嵌套等待票据、实际heap IOCTL临界区/错误解锁/普通模式保留；HOST_DOUBLES_ONLY |
| 实际VM_BIND函数 | `python3 scripts/check/check-gpu-private-bind.py`，rc=0；`bind-mapping-gate-expanded.log` | 32项，新增5项；守卫拒绝先于授权、SYNC_ONLY不取锁、同步sync拒绝。现有MAP/UNMAP场景额外断言grant/RPC/check/cancel均持有锁；守卫本身由上一行真实函数测试，binder为守卫替身 |
| 完整私有入口 | `bash scripts/check/check-rmm-gpu-private.sh`，rc=0；`unit-mapping-gate-final.log` | submit76、bind32、task74、heap75、service26及核心/固件/RTT/ABI；仍不证明Linux并发或GPU |
| 完整两端Image | 前述make命令，Client/Proxy各rc=0；`guest-client-mapping-gate-final.log`、`guest-proxy-mapping-gate-final.log` | 当前ARM64源码完整链接，无新增编译告警；`guest-client-mapping-gate-initial.log`也rc0保留 |
| 旧实现预期失败 | `python3 build/rmm-client-bo-20261030/regression-mapping-gate.py`，wrapper rc=0；`mapping-gate-regression.log`、`mapping-gate-regression/expected-failure.log` | 仅将备份的旧picker替换进当前实际源码夹具；编译rc0，旧picker执行−6，在同VM抢先/另一VM继续断言失败；不是实机复现 |
| 固定补丁与差异 | `python3 opencca/scripts/setup/apply-local-patches.py --check`，rc=0；`patches-mapping-gate.log`、`mapping-gate-review/` | 备份输入、逐文件差异和空白检查；RMM/平台/工具/initrd未改，核对上一阶段SHA及适用范围 |
| 当前输入与需求审计 | `manifest-validation-mapping-gate.json`、`independent-mapping-gate-final.json` | 当前源、Guest Image、日志及复用证据SHA核对；不把已完成的本地互斥扩大为真实应用/隔离保证 |
| Realm/GPU/真实缓存/攻击与完整720p | **NOT_RUN** | 未登录或部署硬件，无新增性能测量 |

本阶段初始bind/submit检查也分别rc0，保留`bind-mapping-gate-initial.log`、`submit-mapping-gate-initial.log`。旧picker预期失败保留，不用当前76项PASS覆盖；无新增产品构建失败。原始dirty工作保留，不将其他阶段的改动归入本阶段。

当前自有私有BO路径已有本地显式依赖和映射/执行互斥，并由RMM独立保持对象/页表/实际执行授权。真实Linux并发、正常Mesa/API/计算/图形与CPU/GPU缓存一致性尚未验证；运行中跨批追加、细粒度缓存租约、动态tiler OOM增长、runner私有bootstrap、死亡Realm清理和攻击负例尚未完成。ABI2/RPC4、能力268435451和完整执行位清零不变，整体goal继续active。

统一记录：解决同VM的映射变更与整context执行租约冲突，同时保留显式依赖语义｜前一就绪切片候选未测，旧共享1405仅历史参考 → 本版未测｜绝对/百分比变化N/A｜控制机源码替身与完整ARM64构建，未部署｜上述run-id、命令、rc与日志｜保留源码，完整应用与硬件验收待完成。本阶段修改运行代码，无新增性能测量，不宣称提分。

## 私有启动与可信服务bootstrap集成（控制机，未部署）

上一goal轮只作概念解释，分类为NO_PROGRESS。本阶段先补齐上一候选的独立核验：`verify-mapping-gate-final.py`，rc0，核对1056项SHA、76/32项检查、实际ABI/能力、两端Image和旧picker预期失败，记录为`independent-mapping-gate-final.json`。其初版函数定位误取前向声明/调用点，修正为只匹配C函数定义后通过，未修改产品校验。随后保存`before-private-runner/`的12项原始输入，继续推进启动集成；本阶段为PROGRESS，整体goal仍未完成。

### 正常路径与失败边界

1. [控制机入口](../../scripts/run/run-realm-xshm.py)和[冻结runner](../../GPU-SFTP/tests/realm-xshm/run-realms.py)新增显式`--private-gpu`。Proxy的受限原生驱动交权模式和Client的私有BO模式由启动参数选择，默认共享模式保留原路径。
2. [PID1](../../GPU-SFTP/tests/realm-xshm/init.c)识别`gpu-private`命令。[静态工具](../../GPU-SFTP/tests/realm-xshm/realm-gpu-private.c)通过`mode-check client|proxy`读取实际只读参数，避免旧内核忽略参数。原有两个DRM探针复用同一检查函数；这只是防错误载荷，RMM仍独立验证真实交权、身份和固件。
3. 所有Realm启动后先核验模式，再由Proxy执行`service-bootstrap /mali_csffw.bin`，配置成功才建立控制通道和GPU会话。部分初始化失败保留现场，不自动reset/retry；私有失败不降级到共享数据路径。
4. [打包器](../../scripts/build/build-realm-xshm-initrd.py)增加固定固件与可选ML二进制；固件先读为私有副本，校验RMM固定允许的274432字节及SHA后直接打包该副本。控制机在上传前检查newc、重复条目、长度/权限/架构、当前init分派、工具mode-check能力和工作负载脚本；缺少固件、旧init/工具或错误架构均拒绝。
5. 私有默认2049页共享控制池，不用它承载Client业务BO。`realm_memory()`分开计算CMA控制池与普通页预算，Proxy普通预算另含arena；默认Client普通预算448MiB，显式ResNet50为576MiB，未绑定旁观Realm使用256MiB总配置。只是准入预算，不是运行期配额或容量保证。旧共享池性能配置/cookie跟踪/共享BO故障探针拒绝与私有模式混用。
6. 私有benchmark-only使用完整glmark/显式ML工作负载，不运行额外API探针；完整720p同时保留1000分门槛。普通私有测试串联正常DRM资源/提交探针及实际计算命令；共享BO自测和PLAN_EXEC计数不作为私有路径成功依据。控制池撤销成功仍明确记录整设备回收`NOT_VERIFIED`，不能推导GPU/arena可安全复用。

glmark挂载不再无条件要求`ioctl-perf`，只有真正的`ioctl` profile才挂载它；完整720p包不需要携带无关计时程序。ML算子还需打包匹配的`gles-ml-smoke`。当前冻结开发包包含完整720p所需脚本，不冒充ML完整载荷。

### 检查与复验产物

run-id：`rmm-client-bo-20261030`；证据根目录：`build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 实际runner/打包/模式检查 | `python3 scripts/check/check-gpu-private-runner.py`，rc0；`runner-unit-final.log` | 31项；实际CLI、启动顺序/失败不重试、双Client控制流程/探针、720p低分拒绝、newc/固件/旧工具拒绝和工作负载依赖；含真实C模式函数的8个文件I/O替身场景，串口/Realm/工作负载为替身 |
| 完整私有入口 | `bash scripts/check/check-rmm-gpu-private.sh`，rc0；`unit-private-runner-final.log` | submit76、bind32、task74、heap75、service26、runner31及核心/固件/RTT/ABI；不证明Linux并发或GPU |
| 静态AArch64工具 | README中的`REALM_XSHM_BUILD_OUT=.../runner-tools bash scripts/build/build-realm-xshm.sh`，rc0；`tools-private-runner-final.log` | 当前init、realm-xshm、realm-gpu-private；无需重建未改的两端内核 |
| 完整720p用initrd及开发包 | README中的打包命令，rc0；`initrd-private-runner-final.log`、`initrd-validation-private-runner.json` | 固定固件/实际当前工具/完整脚本；`private-runner-candidate/{client-Image,proxy-Image,initrd.cpio,runner.py,hashes.json}`，不包含已部署固件的声明 |
| 固定补丁/差异/当前输入 | 补丁清单校验rc0，`patches-private-runner.log`；`private-runner-review/`、`manifest-validation-private-runner.json`、`independent-private-runner-final.json` | 相对备份的实际差异与当前SHA；RMM/平台/两端Image未改，复核上一阶段证据，不重复构建后冒充新GPU验证 |
| Realm/GPU/缓存/攻击/完整720p | **NOT_RUN** | 未登录硬件、未部署；新开发包不是已验证基线 |

保留`runner-unit-initial.log`，rc1：旧工具拒绝测试的预期错误字符串写成`mode-checking`，实际为`driver-mode checking`；仅修正测试匹配后通过。28项中间成功记录及初次工具/initrd日志保留；最终扩展为31项。没有放宽私有模式或固件检查。

**仍需完成：** 动态tiler OOM增长、活跃跨批追加/细粒度缓存交接、死亡Realm与捐赠arena安全回收；正常Mesa/API/计算/图形、真实Linux并发、缓存一致性、恶意Client/Proxy攻击及硬件完整720p门槛均未验证。服务arena在可信整设备撤销后仍需清零/恢复与对象退休，不能以控制池解绑替代；当前开发包的正常退出也未获实机证明。ABI2/RPC4、能力268435451不变，完整执行位仍清零，整体goal保持active。

统一记录：接通显式私有启动、服务bootstrap、控制池/数据内存预算和真实工作负载入口｜上一候选未测，历史共享1405分仅参考 → 本版未测｜绝对/百分比变化N/A｜控制机离线检查与静态构建，未部署｜上述run-id、命令、退出码与日志｜保留源码和开发候选，完整应用与硬件验收待完成。本阶段修改运行代码，无新增性能测量，不宣称提分。

## 死亡 Realm 与捐赠 arena 的可信回收（控制机，未部署）

上一 goal 轮为概念解释，分类为 NO_PROGRESS。本轮重新读取运行手册、产物规范和当前基线，执行 `verify-private-runner-final.py` 及固定补丁清单检查，各 rc0；日志 `reverify-private-runner-before-reclaim-current.log`、`patches-before-reclaim-current.log`。保存14项原始输入及旧 RMM ELF 到 `build/rmm-client-bo-20261030/before-dead-owner-reclaim/`。补充修改的 RTT 测试原文从差异反推恢复，并与前一冻结清单 SHA 完全核对，未以当前文件冒充备份。

### 权限与清理次序

- [RMM GPU_PM](../../opencca/tf-rmm/runtime/rsi/opencca_gpu.c)新增操作7 `PRIVATE_RECLAIM`，仅接收 RD 地址，不接收 HPA、BO、页表根或 Host 自报的停止标志；`x0`为RMI调用状态，`x2`为私有状态，INCOMPLETE表示需要续作。没有私有对象的普通 Realm 直接成功，不触发设备复位。
- [私有适配器](../../opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c)在策略锁内读取实际 RD 引用计数；必须没有任何 REC，且 RD 为 ACTIVE/SYSTEM_OFF。`rec_count`是创建索引，不能用作存活 REC 数。解 RD 锁后调用清理，恢复映射仍遵守 RD→RTT→DATA 锁序；策略锁和非NEW状态阻止途中重新创建REC。
- [私有核心](../../opencca/tf-rmm/runtime/core/opencca_gpu_private.c)先检查全部相关 context 已获可信撤销标记，且映射、任务、授权及缓存引用归零，再清理本 owner 的 context 和每调用最多一个512页 BO 批次。捐赠控制页先清零，再恢复原始 CPU RTT，失败保留登记；普通数据仍保持 delegated，由正常 RMI_DATA_DESTROY 清零和释放。REVOKED，以及旧 service 已销毁后的 UNOWNED/OFF 可进入检查；设备状态枚举本身不能替代核心撤销/引用检查。
- 死亡 Proxy 的指针从其他 Client 的已撤销 BO/context 中解除，避免 RD 地址重用时新 Proxy 继承旧对象权限；这些 Client 的数据、登记和上下文不会被代删。只要仍有私有对象，实际 MMIO grant 入口就拒绝新原始授权。此检查针对仍登记的私有 GPU 对象，不应扩大成任意平台 DMA/GPT 机密性证明。
- [Host Realm 析构](../../Linux-Host-GPU/arch/arm64/kvm/rme.c)在全部 vCPU 销毁后请求回收；有设备状态阻碍时最多发起一次可信 RELEASE，失败保留资源；最多2049次续作并让出CPU。成功后重试早期 MMU teardown 保留的 RTT 项，最后才销毁 RD。早期通知器遇到受保护项仍可能报错/保留，真实退出路径与重试必须实机验证。

整设备撤销可能中止其他 Client 的任务。只保留其对象不代表任务成功，也不保证它们继续执行；旧完成记录不能替代新的可信完成检查。本阶段没有实现透明恢复。新 Host 需要配套支持 GPU_PM 操作7 的 RMM；不能单独替换旧冻结运行包中的 Host，或将先前 private-runner-candidate 称为已包含新回收的部署包。

### 验证记录

run-id：`rmm-client-bo-20261030`；日志及产物根：`build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 证据范围 |
| --- | --- | --- |
| 实际核心/RSI/PM/Host helper | `python3 scripts/check/check-gpu-private-reclaim.py`，rc0；`reclaim-unit-raw-grant.log` | 30项；真实函数提取并链接实际私有/设备/lease核心；存活REC/NEW/错误RD拒绝、复位失败、513页续作、部分clear/restore失败、双Client保留、service指针解除/旧句柄拒绝、原始MMIO再授权拒绝、Host一次撤销和2049次上限。RD/RTT/GPU/调度为替身 |
| 完整私有入口与实际RTT | `bash scripts/check/check-rmm-gpu-private.sh`，rc0；`unit-dead-owner-reclaim-reviewed.log` | submit76、bind32、task74、heap75、service26、runner31、reclaim30及既有核心/固件/ABI；实际RTT模型增加死亡owner核心回收，验证清零、恢复、TLBI及DATA/RD策略解除；不证明Linux并发或硬件 |
| 实际平台后端模型 | `bash scripts/check/check-dma-guard.sh`，rc0；`dma-dead-owner-reclaim.log` | 真实平台源、任务/固件/设备回归；不是真实 GPU |
| RMM ARM64与布局 | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，rc0；`rmm-dead-owner-reclaim-final.log`；固定布局检查rc0，`layout-dead-owner-reclaim-final.log` | 当前适配器/核心完整链接；既有RWX LOAD及build-id丢弃提示保留，不代表启动通过 |
| Host ARM64对象 | `make -C Linux-Host-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/host-reclaim ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-pmthor-opp3 -j8 arch/arm64/kvm/rme.o`，rc0；`host-reclaim-object.log` | 新独立构建树复制匹配Host配置，显式LOCALVERSION；对象编译无告警，不覆盖既有运行树 |
| Host完整Image | 同上参数，目标`Image`，rc0；`host-reclaim-image.log`、`host-reclaim-image-validation.json` | 完整链接；实际Image内置release为`6.12.0-opencca-pmthor-opp3`，与构建release一致；344条编译警告保留（ACPI等源码/GCC15诊断），新rme对象无告警。未部署，板端模块匹配与实际启动未验证 |
| 实际Realm/GPU/恶意行为/完整720p | **NOT_RUN** | 无新性能测量，无整设备回收成功声明 |

保留`reclaim-unit-initial.log`，rc1：测试替身把头文件已有外部声明的平台函数定义为static；改为匹配声明后通过，未放宽产品检查。23项、28项中间检查及最终30项记录均保留；初次及最终RMM/完整私有日志也分别保存。

**剩余工作：** 验证 Host/RMM 实际生命周期、正常Mesa/计算/图形、私有数据缓存一致性与隔离攻击；动态tiler OOM增长、跨批运行中追加和细粒度缓存交接仍未完成。完整720p门槛尚未执行，ABI2/RPC4、能力268435451及完整执行位清零不变，整体goal仍active。

统一记录：把死亡Guest不能继续执行的GPU清理交回RMM，并接通Host退出路径｜前一私有启动候选未测，历史共享1405仅参考 → 本版未测｜绝对/百分比变化N/A｜控制机源模型与ARM64构建，未部署｜上述run-id、命令、rc与日志｜保留源码，真实回收与完整功能待验证。本阶段修改运行代码，无新增性能测量，不宣称提分。

## 首次私有固件组装与部署输入检查（控制机，未部署）

本轮先运行前一阶段独立核验，1163项SHA及真实核心/适配器/Host helper来源一致，完整执行能力位仍清零；固定上游补丁清单也均为APPLIED。上一概念解释本身为NO_PROGRESS，本阶段完成实际固件组装和部署检查接线，为PROGRESS，整体goal仍未完成。

### 候选与当前阻塞

- 固件目录：`build/rmm-client-bo-20261030/firmware-private-first/`，含`idbloader.img`、`u-boot.itb`、`u-boot`、`tf-rmm.elf`、固定BL31/DDR、配置与SHA清单。使用固定U-Boot提交`a515a10c2a36772161b5653961bc25247a9b6c32`，当前源码归档和fragment核对通过；原工作源码、板端载荷与回退包保持原样。
- 配套Host/两端/runner/initrd仍为`private-reclaim-candidate/`，RMM SHA与其`rmm.elf`及当前完整构建产物一致。新固件不是单独的功能验收，也不能继承历史共享1405分。
- 首次U-Boot构建因系统SWIG4.4生成接口与旧libfdt不兼容失败。控制机Python缺少ensurepip，venv尝试也失败；最终直接下载固定SWIG4.2.1 wheel，核对SHA后在忽略的工具目录解包，通过私有PATH使用，不改系统工具或U-Boot源码。来源、命令和失败均单独保留。最终构建退出0，既有编译警告和缺少可选OP-TEE提示保留。
- 只读SSH复核中，Pi和RK均返回255、`Permission denied (publickey,password)`。当前环境无认证变量，可用SSH密钥也未获授权；已请求本机认证配置路径。没有部署、刷写、重启或运行候选，不把网络可连接视为设备角色/资源核验成功。

### 实际刷入内容必须与检查对象一致

旧部署入口只对目录里的RMM ELF运行布局检查，不能证明`u-boot.itb`打包的是这份RMM。新增[检查器](../../scripts/check/check-rmm-firmware.py)，用真实`fdtget`读取FIT，并与AArch64 ELF的文件支持LOAD段逐字节比较：

1. 检查每个RMM段的实际内容、加载地址、架构、类型、无压缩属性与SHA256；入口必须与ELF一致，不能缺段、重复段或使用含糊的数据位置。
2. 同时检查所有FIT配置，要求每个配置实际选择全部RMM段；支持当前外置数据及内联数据，不仅检查镜像名称或旁边的哈希文件。
3. [部署入口](../../scripts/run/deploy-rmm-firmware.py)在板端资源查询、备份和刷写之前执行检查。错配组合返回FAIL；该检查只约束部署输入，不是固件认证、启动证明或GPU隔离证明。控制机依赖既有`device-tree-compiler`中的`fdtget`。

### 本阶段证据

run-id：`rmm-client-bo-20261030`；根目录：`build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 范围 |
| --- | --- | --- |
| 前一候选独立核验/固定补丁 | `python3 build/rmm-client-bo-20261030/verify-dead-owner-reclaim-final.py`及`python3 opencca/scripts/setup/apply-local-patches.py --check`，各rc0；结果重新保存在本阶段证据中 | 1163项SHA、配套Host/RMM及未变Guest输入；不扩大已有模型结论 |
| 固定U-Boot完整构建 | 精确命令见`uboot-private-first-build-compatible-command.json`，rc0；`uboot-private-first-build-compatible.log` | 固定BL31/DDR/当前RMM和SWIG4.2.1；独立目录构建，不证明实体启动 |
| FIT与实际RMM | `python3 scripts/check/check-rmm-firmware.py --fit build/rmm-client-bo-20261030/firmware-private-first/u-boot.itb --rmm build/rmm-client-bo-20261030/firmware-private-first/tf-rmm.elf`，rc0；`firmware-fit-final.json` | 两段、入口、配置与摘要一致；另有真实`dumpimage -l`记录`firmware-private-dumpimage.log` |
| 布局/SD槽位 | `python3 opencca/scripts/check-firmware-layout.py --rmm build/rmm-client-bo-20261030/firmware-private-first/tf-rmm.elf --uboot build/rmm-client-bo-20261030/firmware-private-first/u-boot`，rc0；`firmware-private-layout.json` | 包含BSS；IDB为266240字节、FIT为1791488字节，分别低于现有SD槽位上限；未核验板端实际分区 |
| 真实工具与部署失败路径 | `python3 scripts/check/check-rmm-firmware-tests.py`，rc0；`firmware-fit-tests-expanded.log` | 20项，真实dtc/fdtget及子进程；内联/外置位置、错ELF/地址/入口/摘要、缺段、缺配置引用、截断、压缩等；真实部署脚本的错配拒绝在临时仓库执行，未访问硬件 |
| 认证复核 | `hardware-preflight-resume-20261030.json` | Pi/RK SSH各rc255；资源/角色核验未完成，硬件测试NOT_RUN |
| 板端启动/实际GPU/完整720p/退出回收 | **NOT_RUN** | 认证阻塞；无新性能分数或机密隔离保证 |

保留失败：`uboot-private-first-build-initial.log`（构建rc2，SWIG接口不兼容）；`firmware-fit-first.log`（检查rc1，最初错误地按双位十六进制解析fdtget的单字节输出，改为逐字节整数转换）；`firmware-fit-tests-initial.log`（测试rc1，新增备用配置夹具把属性放到子节点之后，修正DTS顺序）。最终20项通过不覆盖这些失败，未放宽产品检查。

### 认证恢复后的下一步（尚未执行）

先运行`python3 scripts/maintenance/lab-resources.py --check`确认设备角色、空闲与资源；之后按既有入口依次部署固件和配套Host，每次使用独立run-id及`lab-run.py --allow-rk-reboot`。固件仅允许SD storage ID2，部署器实际核对布局并备份。Host必须核对Image内置release、运行配置和模块兼容；任一步失败保留现场，不直接重跑或进入GPU负载。

部署/健康检查成功后，第一项性能负载为完整720p：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-first-720-<唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/rmm-client-bo-20261030/private-reclaim-candidate \
  --private-gpu --workload glmark --performance --benchmark-only \
  --suite --profiles glmark-720
```

上述命令是后续入口，**本阶段未执行**。完整720p需满足1000分门槛并保留正确性、内核健康和资源恢复；通过后才扩展API、计算、多Client与攻击负例。私有动态tiler增长、运行中跨批追加、实际缓存一致性、权限隔离及退出回收仍需实现或运行验证，不能以固件已打包替代完整目标。

统一记录：准备真实部署所需的固定固件组合，防止新ELF配旧FIT｜历史共享1405仅参考 → 本版未测｜绝对/百分比变化N/A｜控制机固件构建与20项打包检查，SSH认证失败未部署｜上述命令、rc、日志与输入SHA｜保留部署工具和候选，完整功能及硬件验收待完成。本阶段仅修改部署检查工具，未改GPU/Host/Guest运行代码，无新增性能测量，不宣称提分。

## 多 Client 私有任务准入等待（控制机，未部署）

上一 goal 轮仅解释页表根地址与访问权限的区别，为 NO_PROGRESS。本轮先重新核对前一清单的1206项SHA并保存11项输入到`before-private-admission/`，再修改实际提交路径，为 PROGRESS。Pi/RK只读SSH复核仍各rc255、认证失败，没有进行部署或硬件测试。

### 权限边界与实际问题

私有模式现有`panthor_device_init_rmm_service()`先通过RMM交出原始GPU MMIO，再解除Proxy内核映射；`TASK_PREPARE/START`由RMM安装真实根、绑定上下文及授权wrapper并执行关键寄存器操作。Proxy通过受限任务RPC请求执行，不能因为知道地址就获得读页表或启动任意命令的权限。CPU页面归属、真实GPU访问与平台物理保护仍需实机攻击验收；本轮没有新增硬件隔离保证，也未把GPT当作不同Realm之间的独立身份权限表。

实际RMM的`gpu_firmware_task_prepare()`找不到空闲CSG时返回FULL，发生在预留slot、标记preparing和任何硬件/控制写入之前；一旦预留或开始部分准备，现有`TASK_CANCEL`就拒绝取消。原Client worker把这个临时FULL直接变为错误fence和file永久失败，正常的多Client争用也可能因此丢失服务。

### 实现及失败语义

- 新增内核typed接口`realm_gpu_task_cancel_unprepared()`：在`gpu_lock`下核对仍托管、非abandoned的精确任务，调用既有RMM CANCEL；仅接受SUCCESS及四个结果字全零，才移出托管列表、清空token。调用方仍需put包装对象。传输、状态或格式错误保留原对象/token；INPUT也不是重试授权。没有新增RSI操作、RPC协议或能力位。
- 暂存阶段遇到ENOSPC，保留当前slice、依赖及输出fence，沿用既有有界延迟重调度。PREPARE遇到ENOSPC，必须先由实际Client直接获得上述可信取消成功，才释放旧包装、清除exposed并在下一次暂存新token。Proxy虚报FULL但实际准备已发生时，RMM拒绝取消，仍走原故障/保留路径。
- 所有等待保留原绝对截止时间，不因重试延长；截止/关闭正常终止尚未暴露的等待任务。已准备、START、丢失回复、畸形回复和普通EAGAIN没有重放许可。成功fence仍要求可信COMPLETE、完整RETURN和RETIRE，未提前释放映射或缓存引用。

### 验证与冻结候选

run-id：`rmm-client-bo-20261030`；所有日志位于`build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 证明范围 |
| --- | --- | --- |
| 实际typed任务接口 | `python3 scripts/check/check-gpu-task-bridge.py`，rc0；`task-admission-initial.log` | 85项，新增11项取消成功/失效/abandoned/非托管/传输失败/四种畸形结果/准备后拒绝；HOST_DOUBLES_ONLY |
| 实际Client worker | `python3 scripts/check/check-gpu-private-submit.py`，rc0；`submit-admission-initial.log`、`submit-admission-reviewed.log` | 88项，新增12项容量恢复、原deadline、关闭、FIFO及后继fence、取消拒绝/不确定、START不重试；内核/传输/RSI为替身 |
| 完整私有回归 | `bash scripts/check/check-rmm-gpu-private.sh`，rc0；`unit-admission-reviewed.log` | submit88、task85及既有bind32/heap75/service26/runner31/reclaim30、实际核心/固件/RTT/ABI；不是Linux或GPU执行 |
| 实际核心与平台模型 | `bash scripts/check/check-dma-guard.sh`，rc0；`dma-admission-reviewed.log` | 新增两个争用场景：三个独立GPUVM占满三个CSG，含最后一个slot部分准备失败；另一Client重复FULL时寄存器/捐赠控制内存逐字节不变，无新增MMIO/控制写、同步或门铃；外来身份/旧token拒绝、未准备取消后新token、准备/不确定持有者不可取消。保留原有148个固件阶段，当前共150阶段；MODEL_ONLY |
| 两端完整Image | `make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j4 Image`，rc0；Proxy改为`guest-proxy`同样rc0；`guest-client-admission.log`、`guest-proxy-admission.log` | 当前ARM64完整链接，无新增编译器告警；未部署 |
| 旧worker预期失败 | `python3 build/rmm-client-bo-20261030/check-admission-old-worker.py`，脚本rc1、旧二进制SIGABRT；`admission-old-worker-reviewed-failure.log` | 实际旧worker配当前新测试，在“FULL后run/fence仍应等待”断言失败；不是真实GPU复现 |
| 固定补丁/空白/输入核验 | `admission-validation.json`、`manifest-validation-admission.json` | 原输入备份、精确源码差异、构建及配套候选SHA；固件/RMM/Host运行代码本轮未改 |
| 真实Realm/GPU、恶意Proxy/Client、缓存与完整720p | **NOT_RUN** | SSH认证阻塞；无新性能测量 |

保留失败：`dma-admission-initial.log`，rc134，最初的单CSG夹具触发现有接口至少三个CSG的校验；改成三个独立GPUVM占满合法三槽位。`dma-admission-final.log`，rc134，夹具误把属性记录1的stream数当成group数；改为在记录0核验group数，保留记录1原有stream检查。生产RMM校验未放宽。初次旧worker回归`admission-old-worker-expected-failure.log`，脚本rc1，夹具在旧worker已结束run后解引用空指针；补上明确状态断言后，reviewed版本在该断言SIGABRT，原失败保留。

新候选`private-admission-candidate/`独立复制上一`private-reclaim-candidate/`，只替换已构建两端Image；沿用相同Host、RMM、initrd、runner与`firmware-private-first/`。原候选和首次固件不覆盖。当前最新manifest记录新候选；此前验证脚本如硬编码旧清单状态属于历史证据，不作为当前验证器。

剩余：真实Host/RMM启动与模块核对、正常Mesa图形/计算与私有数据缓存、恶意Client/Proxy隔离、退出回收，以及动态tiler增长、跨批运行中追加/细粒度交接。完整720p仍须首先达到1000分并通过正确性、内核健康及资源恢复后，才扩展API/计算/多Client。ABI2/RPC4、能力268435451及完整执行位清零不变，整体goal继续active。

统一记录：避免多Client暂时资源争用被误判为永久故障，同时保留不确定执行的引用｜上一私有候选未测，历史共享1405仅参考 → 本版未测｜绝对/百分比变化N/A｜控制机实际源码替身、平台模型与ARM64构建，未部署｜上述run-id、命令、rc和日志｜保留源码，真实功能与安全验收待完成。本阶段修改Guest运行代码，无新增性能测量，不宣称提分。

## 私有任务运行期间的受限页表扩展基础（控制机，未接通动态扩容）

上一 goal 轮只有设计解释，为 NO_PROGRESS。本阶段完成内部建表基础及验证，为 PROGRESS；整体目标仍未完成。原生 Panthor 在 tiler OOM 后分配新 chunk，向固件发布 heap_start/heap_end 并 ACK、通知恢复；当前私有固件路径仍把 OOM 位26归为错误，Client 私有 heap 也只有初始 chunk。因此本节不能视为已支持动态扩容，更没有通过真实 GPU 执行。

### 内部能力与权限边界

- `gpu_private_task_extend()` 仅供后续可信固件 OOM 消费者使用，没有新增 RSI、Proxy RPC、Guest 调用或能力位。它本身不认证 OOM，也不 ACK 或启动任务；后续消费者必须先认证实际固件状态、所属 task/queue/heap，再选择此入口，不能直接暴露为 Proxy 的运行中 MAP 权限。
- 要求原 Client、服务、context、已完成 READY 的精确 task、原 AS 和固件根一致；BO 为完整注册的新私有对象，具有 RW 权限、32–2048页、未映射且没有 pending/cache 租约。先检查整个目标 VA 为空且不进入内部控制区，再进行缓存操作。仅添加新叶子，普通 MAP/UNMAP 的 task 冻结规则保留。
- 每次最多512页，先通过可信缓存回调交出新页，再发布固定 RW/XN/WB PTE。跨批保留精确 BO/VA 和游标，不允许换任务、对象或范围。映射及缓存计数先于可能失败的硬件刷新更新；成功后纳入原任务的 RETURN/RETIRE 回收范围，不重同步既有数据页。
- 平台新增 live-AS 刷新入口：运行中真实 Client 根、固件根、属性、状态和其他 AS 的同根别名在刷新前后均需匹配；只执行原 AS 的 LOCK、FLUSH_PT，不写根/属性、MCU、任务门铃。RSI 适配层继续要求 MEDIATED 状态并持有映射锁。
- 缓存同步、建表或刷新失败后隔离 context，保留新 BO、已发布叶子和可能已被 PTW 看到的空表；部分扩展期间拒绝 quiesce、RETURN、RETIRE 和对象销毁。只有可信设备撤销/复位才能释放未完成扩展的 pending 持有，不能凭 Proxy 声明回收。

### 本地验证与载荷边界

run-id：`rmm-client-bo-20261030`；日志均在 `build/rmm-client-bo-20261030/`。变更前12项输入和原 manifest/audit 备份于 `before-private-heap-extension/`，不覆盖上一冻结候选。

| 检查 | 命令、退出码与日志 | 证明范围 |
| --- | --- | --- |
| 完整私有回归与扩展核心 | `bash scripts/check/check-rmm-gpu-private.sh`，rc0；`unit-extension-initial.log`、补充耗尽后的 `unit-extension-exhaustion.log` | 35个常规扩展场景加1个8表池耗尽场景；真实 PT 核心、合成 RTT/缓存/AS。覆盖32/513/2048页、先同步后PTE、固定权限、整段预检、身份/生命周期、跨批替换拒绝、同步/刷新失败保留、完整 RETURN 和复位回收。其余 task85、submit88、bind32、heap75 等既有检查通过；HOST_BACKEND_DOUBLES_ONLY |
| 平台与固件模型回归 | `bash scripts/check/check-dma-guard.sh`，rc0；`dma-extension-initial.log` | 实际平台源码成功刷新只改LOCKADDR/COMMAND；11类前置拒绝无MMIO写；LOCK/FLUSH超时以及7类刷新后状态变化拒绝，含后来出现的同根别名；原150个固件阶段保留。MODEL_ONLY，不证明实际 GPU/PTW/缓存行为 |
| ARM64 RMM | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，rc0；`rmm-extension-build-initial.log` | 实际源码完整链接；原有RWX LOAD及build-id丢弃链接提示保留，无新增编译器告警 |
| 含BSS布局 | `python3 opencca/scripts/check-firmware-layout.py --rmm build/rmm-client-bo-20261030/rmm-build-arm64/Debug/rmm.elf --uboot build/rmm-client-bo-20261030/firmware-private-first/u-boot`，rc0；`extension-layout.json` | 原38MiB预留内存未扩大、无U-Boot交叠；新ELF尚未组装入FIT，不代表固件可部署 |
| 固定补丁/空白/输入核验 | `python3 opencca/scripts/setup/apply-local-patches.py --check`、父仓库及RMM的`git diff --check`，各rc0；`patches-extension.log`、`extension-validation.json`、`manifest-validation-extension.json` | 原冻结候选及配套固件不变，ABI2/RPC4、能力268435451及完整执行位清零保留 |
| 完整OOM流程、真实Realm/GPU、隔离攻击、720p性能与资源恢复 | **NOT_RUN / INCOMPLETE** | 尚无固件OOM认证/Client分配/ACK恢复消费者，也未部署；此前SSH认证阻塞未被本地构建消除 |

当前扩展函数只有明确的本地验证调用者，保留是为了接通后续私有 tiler 动态增长，不作为已开放的 Guest 功能。新构建 ELF/img 与旧 `private-admission-candidate/`、`firmware-private-first/` 不同；后续必须组装并检查新的配套 FIT，不能只替换目录旁边的 ELF。该阶段未修改 Guest/Host 源码，无需重复构建两端 Image；也没有继承旧镜像的真实 GPU PASS。

下一步仍是完整消费者：读取并认证实际 OOM/heap/计数，绑定待处理扩容事件，让原 Client 分配并注册新 chunk，经上述可信建表后发布固件 heap 指针并 ACK 恢复，接通失败/退出回收；之后还需正常 Mesa、跨批追加、实际缓存与攻击验证，以及先完整720p≥1000的硬件门槛。

统一记录：为 Client 私有数据提供任务运行期间的受限增量建表基础｜上一私有路径未测，历史共享1405仅参考 → 本版未测｜分差及百分比N/A｜控制机源码替身、实际平台模型和ARM64构建，动态OOM流程未接通、未部署｜上述run-id、命令、rc和日志｜保留内部实现供后续接线，功能与硬件安全验收待完成。本阶段修改RMM运行源码，无新增性能测量，不宣称提分。

## 私有 tiler OOM 可信处理核心（控制机，Guest 尚未接线）

上一 goal 轮完成受限页表扩展基础，为 PROGRESS。本轮继续实现并验证 RMM 内部事件与扩容处理，为 PROGRESS；整体 goal 仍 active，未完成真实 GPU 功能或安全验收。变更前1276项清单SHA重新核验，7项源码/文档/manifest输入备份于 `build/rmm-client-bo-20261030/before-private-heap-events/`。

### 实际改动与授权边界

- 原生 Panthor 用 CS req/ACK 的第26位差异表示 tiler OOM。原私有路径把 ACK 的该位直接归入错误，即使事件已经处理、该位仍为1也会拒绝任务。本轮将它从 fatal/protected-mode 错误中分离；真正待处理的 OOM 仍阻止成功完成，保留其他错误、身份、队列、上下文与硬件状态检查。
- 内部 `gpu_firmware_task_heap_event()` 通过已启动任务的只读重验，核对真实 AS、固件根、CS/CSG/全局握手及错误，再从启动时保存的 MCU 接口位置读取实际事件。拒绝非参与队列、控制VA、未对齐heap及不满足 `frag_end <= vt_end < vt_start` 的状态。记录不回绕、不随设备复位复用的事件ID，绑定原任务、队列、heap地址、事件边沿和VT起始批次；后续观察可报告实际推进后的fragment计数。只返回该 Client 的heap GPUVA与计数，不返回HPA、页表根或固件指针，也不写MMIO。
- 内部 `gpu_firmware_task_heap_grow()` 只消费上述精确事件，检查原owner的新BO与地址范围，通过上一节的可信增量建表实现每次≤512页、缓存先于PTE；跨批固定BO/VA。建表后再次验证事件，编码原生 `GPUVA | chunk_pages`，由RMM依次发布CS heap_start/heap_end及事件ACK、CSG子门铃、global父门铃，并有界核验实际ACK及根/状态。允许原生ENOMEM回退 `object=VA=0`，不修改页表。
- 发布前先保存不确定状态。部分通知、ACK超时或变化的硬件/事件状态隔离并持有引用，不重发；成功精确重试只检查实际运行状态和原对象，不重复同步、建表或通知。待处理事件不能成为完成证明；正常完成仍须原有真实COMPLETE、STOP/AS禁用、全部数据RETURN及RETIRE。
- PREPARE在STOP状态继承各CS的已确认OOM位，并以真实CSG子门铃ACK为基准；START保留该事件位。所有硬件CS（含新组不使用的旧槽位）都清除旧地址并对齐已确认的事件状态，避免同组复用或从两队列组切到单队列组后产生伪事件/未完成握手。未新增原始MMIO权限。

这两个入口目前只有明确的内部验证调用者；没有新增 RSI/RPC、Guest 调用、能力位或完整执行声明。其参数中的owner由未来RSI适配层从实际RD取得，不能让Proxy从消息中指定。当前Guest worker仍不能分配/登记新chunk或消费这些事件，不能将本节描述为已支持实际应用的动态扩容。

### 本阶段证据

run-id：`rmm-client-bo-20261030`；以下日志位于 `build/rmm-client-bo-20261030/`。

| 检查 | 命令、退出码与日志 | 证明范围 |
| --- | --- | --- |
| 实际核心/固件/平台模型 | `bash scripts/check/check-dma-guard.sh`，rc0；最终 `dma-heap-event-final.log` | 原150个阶段加26个heap场景，总176阶段。新32/513页chunk、两种事件边沿、无事件、ENOMEM回退、身份/旧ID/外来BO/占用VA、分批替换拒绝、计数合法推进、连续事件、同步/刷新/通知/ACK失败保留；成功后实际COMPLETE/RETURN/RETIRE包含新增页；原Client组及较少队列的新组复用通过。另一Client的AS/组输入逐字节不变，不证明真实并发执行或物理隔离 |
| 完整私有本地回归 | `bash scripts/check/check-rmm-gpu-private.sh`，rc0；`unit-heap-event-compact.log` | 实际核心/固件/RTT、36个扩展场景及原task85/submit88/heap75等；CPU、Linux/RSI、固件与设备的替身边界保留，不是GPU运行 |
| ARM64 RMM完整构建 | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，rc0；`rmm-heap-event-compact.log` | 实际源码链接，保留既有RWX LOAD和build-id链接提示，无新增编译器告警 |
| 固件内存布局 | `python3 opencca/scripts/check-firmware-layout.py --rmm build/rmm-client-bo-20261030/rmm-build-arm64/Debug/rmm.elf --uboot build/rmm-client-bo-20261030/firmware-private-first/u-boot`，rc0；`heap-event-layout-compact.json` | 包括BSS和栈，未扩大38MiB预留、未与U-Boot交叠；当前尾地址恰到既有预留上界，后续修改必须继续检查。压缩事件记录移除冗余旧计数，任务记录少1024字节，但受对齐影响，布局上界未下降，不宣称预留内存节省 |
| 旧错误位机制负对照 | `python3 build/rmm-client-bo-20261030/check-heap-old-error-mask.py`，脚本rc0、负对照二进制rc−6（预期SIGABRT）；`heap-old-error-mask/{compile.log,run.log,result.json}` | 仅在临时固件核心副本恢复旧的raw OOM错误位处理，首个事件快照断言失败；原代码不覆盖。使用紧凑计数改动前的同阶段模型，不是物理GPU复现 |
| 固定补丁/空白/输入 | 固定补丁校验、父仓库及RMM `git diff --check`，各rc0；`patches-heap-event.log`、`heap-event-validation.json`、`manifest-validation-heap-event.json` | 旧配套bundle/FIT保持不变，ABI2/RPC4、能力268435451与完整执行位清零保留；新ELF未打入FIT |
| RSI、Client heap/worker、新配套FIT、真实GPU/缓存/攻击/完整720p | **INCOMPLETE / NOT_RUN** | 未接入Guest消费；未部署，既有SSH认证阻塞未消除，无新增性能或实机安全结论 |

保留三次夹具失败：`dma-heap-event-initial.log` rc134，测试误在STARTED状态查询仅允许RESERVED/PREPARED的任务资源，删除此非法测试查询；`dma-heap-event-second.log` rc134，新完成夹具漏开既有launch清理追踪，STOP计数断言失败，修正夹具；`dma-heap-event-reuse.log` rc134，旧固件双端模型把START req硬编码为0x511，未容纳已确认OOM位，改为同时核对启动位和原ACK位。`dma-heap-event-third.log`、`dma-heap-event-reviewed.log`、`dma-heap-event-mixed-reuse.log`、`dma-heap-event-compact.log`分别保留各阶段成功，不覆盖失败，也不全部算最终版本重复验收。

后续接线保持原目标：由实际Client的RSI身份消费事件，在Client heap中匹配上下文和heap地址，按target/max策略分配并登记私有chunk、保留VA和生命周期，交给RMM可信扩容并恢复；不经Proxy读取数据或写真实根/heap指针。之后组装新匹配FIT，再进行实际Realm/GPU、缓存及攻击验收；完整720p≥1000及正确性/健康/恢复仍是首个性能门槛。

统一记录：实现私有tiler事件和可信扩容核心，修复旧ACK位误判及槽位复用｜上一私有候选未测，历史共享1405仅参考 → 本版未测｜分差及百分比N/A｜控制机实际核心/固件/平台模型、ARM64链接，Guest未接线、未部署｜上述run-id、命令、rc和日志｜保留RMM内部实现，整体功能和硬件验收待完成。本阶段修改RMM运行源码，无新增性能测量，不宣称提分。


## 原 Client 私有 tiler 动态扩容接线与新配套载荷（控制机，未部署）

上一概念问答没有改变实现，按NO_PROGRESS记录；恢复时先完成上一阶段证据进程，独立重核1319项SHA、26个固件堆场景及旧配套包，再继续实际缺口。本阶段为PROGRESS，完整goal仍active。16项变更前源码/文档/清单输入保存于`build/rmm-client-bo-20261030/before-private-heap-client/`。

### 功能与权限

- 新增RSI操作50 `TASK_HEAP_EVENT`、51 `TASK_HEAP_GROW`，共用能力`268435456`。适配器从实际REC取得RD，再由认证channel解析已隔离服务；不接受消息中的身份，不允许Proxy代替Client处理。EVENT只返回原任务的事件ID、heap GPUVA、计数和队列；GROW仅传原事件、新私有BO与GPUVA，或原生ENOMEM回退的零BO/VA。两者都不返回HPA、页表根或固件地址，不授予原始MMIO。
- 正常托管group/task记录context。Client内核新增`realm_gpu_task_heap_service()`，按task/context/channel及精确heap地址查找自己的heap；检查回复队列与参与集合、事件计数和字段。按原生`in_flight > target`或已达`max_chunks`时给固件零chunk，让其等待/回收；内存/VA不足同样回退，身份、传输和协议错误不能冒充内存不足。
- 正常扩容在Client分配、登记零初始化的RW私有BO。分配期间释放全局锁，但预留chunk VA并固定heap，销毁只能标记待回收；分配返回后再接入。RMM仍负责真实缓存交接、固定RW/XN/WB建表和事件/ACK/门铃。每调用≤512页；task保留精确事件、BO、VA和累计页数，继续调用不重新分配或更换地址。
- 动态chunk纳入heap的VA冲突保护、分配搜索和精确BO清理，初始页与新增页都必须经真实UNMAP_BO/可信撤销后释放。失败保留完整不确定范围，不能释放BO或复用VA。task只保存标识符，不保存可被回收chunk的指针；继续操作前重新查找，拒绝复位/退休后已经回收的记录。
- Client worker只在真实COMPLETE返回未完成时调用上述处理；处理成功仍回到COMPLETE等待，原绝对截止时间不更新，START不重放。任务成功fence仍要求真实COMPLETE、全部RETURN和RETIRE；扩容或ENOMEM回退的ACK不是完成证明。诊断ioctl和普通导出接口不能代改内核托管任务的堆状态。

### 构建与证据

run-id：`rmm-client-bo-20261030`；以下日志均在`build/rmm-client-bo-20261030/`。

| 验证 | 命令、退出码与日志 | 证明范围 |
| --- | --- | --- |
| 完整私有回归 | `bash scripts/check/check-rmm-gpu-private.sh`，rc0；`unit-heap-client-final.log` | 堆107项（新增31个扩容场景及NULL输入）、适配器13项、任务桥87项、提交91项及原有登记/建表/缓存/runner/回收场景通过。CPU分配、REC、通道、固件事件及Linux并发仍有替身边界 |
| 堆与真实PT核心 | `python3 scripts/check/check-gpu-private-heap.py`，rc0；`heap-client-rsi-reviewed.log` | Client实际分配/保留/回收函数连接真实RMM扩展、PTE/引用、quiesce/return/retire核心；128KiB/8MiB、多批、连续事件、target/max/分配/VA回退、未知/异context/channel/已销毁heap、坏计数/队列/回复、同步失败/回复丢失、复位后继续、分配期间销毁。独立RSI替身检查实际RD和通道解析及零参数约束 |
| 实际固件/平台后端 | `bash scripts/check/check-dma-guard.sh`，rc0；`dma-heap-client-final.log` | 保留176个固件阶段，含26个真实核心/固件/平台源码堆场景和第二Client配置保持；这是模型，非物理GPU/并发隔离证明 |
| worker语义 | `python3 scripts/check/check-gpu-private-submit.py`，rc0；`heap-submit-reviewed.log` | 91项；新增扩容继续时不改变COMPLETE/截止时间，不重复START/提前signal，I/O及坏回复失败保留。原worker负对照脚本`check-heap-old-worker.py`退出0表示预期SIGABRT（被测程序rc−6），失败于缺少真实堆消费者；证据`heap-old-worker/{compile.log,run.log,result.json}`，不是真实GPU复现 |
| RMM/Client/Proxy完整构建 | `cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`及既有两端`make ... -j4 Image`，各rc0 | `rmm-heap-client-reviewed.log`、`client-heap-initial.log`、`proxy-heap-initial.log`；两端无编译器告警，RMM保留既有RWX LOAD/build-id两条链接提示。精确命令进入清单 |
| 新固件组装与匹配 | `python3 build/rmm-client-bo-20261030/build-heap-firmware.py`，rc0；`uboot-heap-{commands.json,configure.log,build.log}` | 独立解包已校验固定U-Boot归档，复用已校验BL31/DDR、相同config和SWIG4.2.1；六条U-Boot既有警告与前版相同。`check-rmm-firmware.py --fit .../firmware-private-heap/u-boot.itb --rmm .../firmware-private-heap/tf-rmm.elf`，rc0；`heap-client-fit.json`核对实际段、入口与摘要 |
| 布局/冻结 | `check-firmware-layout.py --rmm .../firmware-private-heap/tf-rmm.elf --uboot .../firmware-private-heap/u-boot`、`freeze-heap-candidate.py`，各rc0 | `heap-client-layout-final.json`、`heap-candidate-validation.json`；含BSS尾仍为0x2800000，预留未扩大、无U-Boot交叠、满足SD槽位上限。新候选与新FIT的RMM完全一致；旧包保持原SHA |
| 固定补丁/空白 | `python3 opencca/scripts/setup/apply-local-patches.py --check`及父仓库/Guest/RMM的`git diff --check`，各rc0 | `patches-heap-client-initial.log`及最终清单；不更新固定上游，不覆盖原回退固件 |
| SSH与硬件 | Pi/RK只读`ssh -o BatchMode=yes -o ConnectTimeout=5 ... 'uname -n'`各rc255，`heap-client-{pi,rk}-ssh.log` | 两者仍Permission denied；未部署、未启动Realm/GPU、未跑完整720p/正常Mesa/缓存/隔离攻击/退出回收；不继承历史共享1405分 |

新冻结包`private-heap-candidate/`更新两端Image和RMM ELF/img，配套`firmware-private-heap/`；保留ABI兼容的既有Host、initrd及runner，哈希逐项核对。ABI2/RPC4，总能力536870907，完整执行位4保持清零。不能将新Guest/ELF与旧FIT组合使用；固件一致性检查不等于可信启动或实体安全证明。

整体仍需正常Mesa和真实GPU验证、Client/Proxy读写与DMA绕过攻击、缓存正确性、恶意故障和退出回收；实际Host模块与启动组合也待核对。跨批运行中追加及细粒度缓存交接尚未实现。硬件可用后首先经独占入口运行完整720p≥1000及正确性、内核健康和资源恢复，再扩大API/计算/多Client。

统一记录：接通原Client动态tiler扩容与可信建表/恢复，组装新配套包｜上一私有路径未测，历史共享1405仅参考 → 本版未测｜分差及百分比N/A｜控制机实际函数/PT核心、固件/平台模型、ARM64构建与FIT检查，未部署｜上述run-id、命令、rc和日志｜保留，真实功能与安全验收待完成。本阶段修改运行代码，无新增性能测量，不宣称提分。


## 认证恢复、私有载荷部署与首次实机失败（2026-10-30）

前面“SSH认证失败/未部署”均为当时阶段事实；本节更新最新状态，不覆盖原证据。用户提供的凭据只用于会话内存，未写入文件。按设备标记确认Pi与RK角色，资源检查无阻塞，串行执行以下部署与测试：

| run-id | 操作与退出码 | 结果及证据 |
| --- | --- | --- |
| `private-heap-host-20261030-a` | `lab-run.py --allow-rk-reboot ... deploy-host-image.py ...`，rc0 | SD2内核更新，Image内置release与板端模块均为`6.12.0-opencca-pmthor-opp3`；重启恢复与CPU/驱动检查通过。实际命令见`build/lab-runs/<run-id>/result.json`；原内核分区备份`build/host-runs/<run-id>/sd-kernel-before.img` |
| `private-heap-rmm-20261030-a` | `lab-run.py --allow-rk-reboot ... deploy-rmm-firmware.py ...`，rc0 | 已核验的`firmware-private-heap/`仅写SD2，Host恢复，Realm能力1。FIT/ELF一致且RMM预留未扩大。实际命令与健康记录见`build/lab-runs/<run-id>/`，原启动区备份`build/firmware-runs/<run-id>/sd-boot-before.bin` |
| `private-heap-720-20261030-a` | `lab-run.py --run-id private-heap-720-20261030-a -- python3 scripts/run/run-realm-xshm.py --images build/rmm-client-bo-20261030/private-heap-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，rc1 | **FAIL**：两个VMM退出−6，FDT断言`memory_size must be 2MB-aligned`；旧预算Proxy265MiB、Client473MiB。Realm/GPU bootstrap未执行，无性能分数；Host健康PASS，资源/频率恢复。失败包和日志保留 |

### 只修正runner预算，不降低VMM约束

私有路径只为共享控制池预算CMA，数据页仍使用普通私有内存。将CMA预算向上4MiB对齐，再把总Realm内存向上2MiB对齐；原普通内存预算不减少。一Client为Proxy268MiB/CMA28、Client476MiB/CMA28；两Client时Proxy308MiB/CMA36；ResNet50 Client604MiB/CMA28；未绑定outsider仍256/16。目标内核的CMA按4KiB页配置，VMM的2MiB断言保持原样。

`python3 scripts/check/check-gpu-private-runner.py`，rc0，32项；日志`build/rmm-client-bo-20261030/private-runner-alignment.log`。新合同测试涵盖1–4Client、控制池边界/非整MiB页数、默认/720p/ResNet50及outsider，对总内存与CMA对齐、控制池最低需求和普通预算检查。对照旧runner执行该测试预期失败，114个subtest失败且无测试异常，见`private-runner-old-memory.{log,json}`。这是离线模型检查，不能替代VMM启动或GPU实测。

保留失败的`private-heap-candidate/`，新建`private-heap-aligned-candidate/`，仅runner变化，其他Image/initrd/Host/RMM逐字节相同。冻结脚本`freeze-heap-aligned-candidate.py`及`heap-aligned-candidate-validation.json`记录SHA和输入差异。动态堆元数据改为`NOT_VERIFIED`，表示源码已实现但未有实体GPU扩容证据。`private-heap-720-20261030-b`已启动，使用同一已部署固件，无重复刷写；结果待记录。

统一记录：修正私有runner内存对齐以通过VMM准入｜上一私有a启动FAIL、无分数 → 新b待验证｜分差及百分比N/A｜仅runner预算/元数据变化、Host/RMM/两端Image/initrd相同｜上述run-id、完整命令、rc和日志｜保留修正，真实GPU/缓存/隔离/退出回收和完整720p≥1000仍待完成。未改GPU/Host/Guest运行代码，无新增性能测量；goal保持active。


## 实机启动定位：CSF完成位与死亡Realm回收顺序（2026-10-30，实施中）

`private-heap-720-20261030-b`最终rc1：两个Realm启动、两端私有模式检查通过；固件固定摘要/封存/运行页准备及4096页控制arena移交成功，FW_BOOT操作23返回状态2。Host退出出现13条DATA/RTT相关WARNING，健康FAIL；CPU/频率/驱动恢复不抵消健康失败。a、b完整板端日志已拉回控制机并逐文件SHA核对，见各自`build/lab-runs/<run-id>/realm-evidence/`及`evidence-transfer.json`。没有glmark分数，动态堆/隔离攻击仍未执行。

另发现Proxy含33个Panthor请求类型，加上管理/测试服务超过通信层32槽位；其TILER_HEAP_DESTROY注册返回ENOSPC并触发注册回退。通信层容量改为64，保持请求边界与身份校验；重建Proxy Image。`firmware-private-bootdiag/`只增加可信固定寄存器诊断，不打印页表根/Client地址；实际平台后端176阶段模型及ARM64构建/布局/FIT校验通过。SD2部署`private-heap-rmm-20261030-b`恢复成功rc0；原配套包均保留。

`private-heap-720-20261030-c` rc1，使用`private-heap-bootdiag-candidate/`。串口记录`GPU FW install complete`，随后`boot-status: mcu=2/1 gpu=0 irq=600/80000000/10000 l2=1 as0=0 fault=0`：MCU处于enabled，真实boot指示已置位，失败来自把MMU raw的0x10000当成故障。对照原生`panthor_mmu_fault_mask()`：CSF MMU低16位才是fault，高16位为AS REQ_COMPLETE。RMM原来要求整个寄存器为0，误拒绝正常AS0 UPDATE完成；BOOT与持续running检查现均只检查低16位，真实fault/root/属性/MCU检查保留。模型的实际AS UPDATE现在产生对应高位，完整176阶段通过；临时恢复旧判断时相同模型预期SIGABRT，见`old-csf-fault-mask/`。这不是简单忽略设备故障，而是按该架构区分完成位和故障位。c退出仍使用旧Host，有同类回收WARNING，健康FAIL；后端注册容量问题在该轮已消失。

### 回收顺序修正

真实调用栈显示guest_memfd失效先于REC销毁。RMM拒绝仍登记的GPU/捐赠数据页是预期保护；Host旧代码将拒绝当作异常，随后仍折叠/销毁RTT。即使后面的RMM私有回收成功，也没有先重试这些DATA，导致最终RTT仍含有效项。

Host现在对RMI_DATA_DESTROY的INPUT拒绝保留页面，不采用错误输出的PA/next值；逐页推进并记录范围未完全清空，跳过该范围折叠。未死亡Realm的PGD终结不抢先清理RTT；在REC销毁和可信私有回收后，明确重试完整受保护DATA，再拆RTT和销毁RD。最终仍有任何拒绝便阻止RD释放，不把拒绝当作销毁成功。删除不再调用的`kvm_realm_destroy_rtts()`及声明。新增实际Host函数替身测试9项，包括恶意错误next值、拒绝页与正常页混合、无早期undelegate/put_page、之后重试/折叠、最终持续拒绝与真正错误；日志`teardown-order-unit-reviewed.log`。首次夹具缺u64别名的编译失败保留于`teardown-order-unit.log`。原30项回收测试、完整私有回归、显式LOCALVERSION的ARM64 Host Image构建通过，无新增编译告警；实体退出验证仍待新轮次。

新组合`private-heap-csf-candidate/`配`firmware-private-csf/`，保存原两端Image、initrd、对齐runner，更新CSF修正RMM和回收顺序Host。含BSS布局仍以0x2800000为上界，未增加预留。新Host部署与新私有轮次结果待补充；完整执行能力位仍清零，goal保持active。

统一记录：修正CSF完成位误报、Proxy注册容量与Host回收重试顺序｜私有a/b/c均FAIL、无分数 → 新组合待验证｜分差及百分比N/A｜运行代码有变化，历史共享1405不可作私有对照｜各run-id与`build/rmm-client-bo-20261030/`的构建、模型、FIT、布局、失败对照日志｜保留修正，真实工作负载/缓存/隔离/回收仍待验收，无新增性能测量。


## 实机d：可信固件配置成功、Host回收健康通过；Client heap句柄修正

`private-heap-host-20261030-b`新Host及`private-heap-rmm-20261030-c`新CSF固件均SD2部署恢复rc0，内核/模块release一致；启动区与内核分区备份分别保留于`build/firmware-runs/`、`build/host-runs/`同run-id目录。配套包`private-heap-csf-candidate/`的FIT/ELF和RMM预留布局校验通过。

`private-heap-720-20261030-d`最终rc1，**负载FAIL但Host健康PASS**：实体MCU启动和全局可信配置成功，`GPU_RMM_SERVICE_BOOTSTRAP=CONFIGURED`；两端RMM事件/身份通道、2049页共享控制池建立成功，真实Client OPEN_SESSION、VM_CREATE、私有BO_CREATE/mmap及GROUP_CREATE已执行。计算预热在TILER_HEAP_CREATE失败，没有进入glmark barrier，无有效性能分数。Client产生`__xa_alloc`告警，而本轮Host dmesg无新增错误、两Realm正常退出，资源/频率/CPU和驱动恢复；新Host修正已通过该失败场景的实机退出检查，但这不证明活跃GPU任务或任意死亡时序的完整回收。

Client私有heap使用`xa_alloc()`分配句柄，需要`XA_FLAGS_ALLOC`空闲槽位跟踪；原open路径对heaps只用`xa_init()`，内核会WARN并返回EINVAL。修正为`xa_init_flags(..., XA_FLAGS_ALLOC)`。补充heap模型：从实际`panthor_client_open()`提取五个xarray初始化调用，替身分配器检查alloc前提，再运行真实frontend heap创建/销毁。`python3 scripts/check/check-gpu-private-heap.py` rc0，heap108项、RSI13项，日志`heap-xarray-unit.log`。仅临时恢复旧初始化时同模型预期SIGABRT，日志`old-heap-xarray.log`，未修改运行源；Client Image重建rc0，无新增编译告警。该测试仍是Host替身，不是Linux xarray或GPU实测。

保留d输入，新`private-heap-xarray-candidate/`仅改变Client Image，沿用已部署Host与`firmware-private-csf/`、原Proxy/initrd/对齐runner；无需重复刷写。e轮`private-heap-720-20261030-e`已启动，结果待记录。

统一记录：修正Client私有tiler heap句柄分配前提｜d计算预热FAIL、无glmark分数 → e待验证｜分差及百分比N/A｜仅Client Image变化，同Host/RMM/Proxy/initrd/runner｜上述run-id、命令、rc及日志｜保留修正，完整720p与真实任务/缓存/多Client隔离仍待验收。无新增性能测量，不将固件CONFIGURED或Host健康PASS当作完整私有GPU成功，执行能力位保持清零。


## 实机e/f：heap初始化推进，定位到START握手失败

`private-heap-720-20261030-e` rc1，Client xarray告警消失、Mesa进入ES3.1初始化和私有heap/BO创建，但计算预热报告VM_BIND errno5，未进入完整glmark。新增两端`realm_gpu_private_call_checked()`失败操作/状态日志和Client任务失败阶段日志，只记录操作/状态/阶段，不打印HPA、页表根或命令内容；两端Image构建及91项提交模型通过。新冻结`private-failure-trace-candidate/`仅改变两端Image，其余输入与e相同。

`private-heap-720-20261030-f` rc1：最先出现`private task failed phase=3 members=1 exposed=1 error=-16`，Proxy对应操作40 TASK_START、状态2；随后操作41 QUIESCE同样拒绝。说明VM_BIND EIO是已暴露任务失败后阻断会话的后续现象，不能通过绕过映射/完成检查解决。PREPARE/READY/PUBLISH已推进，但尚无真实任务START成功或完成证明。增加RMM启动握手分阶段诊断以区分配置、根检查、发布和ACK/设备错误；仅输出固定协议位和低8位异常类型，不输出地址或异常数据。

e/f的`host-kernel-health.json`均PASS、两Realm正常退出0，CPU/频率/驱动和资源恢复。每轮证据已拉回控制机逐文件SHA核验，位于`build/lab-runs/<run-id>/realm-evidence/`、`evidence-transfer.json`；原始失败保留。Proxy失败清理中的GPUVA解除警告尚待处理，Host健康PASS不代表Guest内核健康通过。可选IOCTL探针的SYNCOBJ_EVENTFD预期errno与私有本地syncobj行为不符也保留，尚未修正或宣称通过。

统一记录：定位私有GPU START失败，保留Client失败后隔离｜e/f均计算预热FAIL、无glmark分数 → 新RMM握手诊断待实测｜分差及百分比N/A｜f仅新增两端诊断，Host/RMM/runner/initrd不变｜上述run-id、实际命令/rc/日志见各`result.json`｜保留，整体goal active，完整执行位保持清零。本阶段无有效性能测量。


## 实机g：已发布到MCU，stream握手检查未通过

诊断固件`firmware-private-starttrace/`经含BSS布局及真实FIT/ELF一致性检查通过，`private-heap-rmm-20261030-d`仅写SD2，Host/Realm能力恢复rc0。新`private-starttrace-candidate/`仅替换配套RMM ELF，Guest/Host/initrd/runner与f相同。新增诊断改动的ARM64构建、176阶段固件后端模型和完整私有回归均rc0，分别见`rmm-task-start-trace.log`、`dma-task-start-trace.log`、`unit-task-start-trace.log`；RMM保留既有两条链接提示，无新增编译器告警。

`private-heap-720-20261030-g`负载rc1，UART实际记录START step10（发布后等待），全局门铃1/1、CSG req/ack 0x11/0x11、halt=0，表明MCU接受了父层请求；尚不足以证明stream启动。串口丢字使后续CS状态/异常类型不完整，不能据此判断是CS故障还是ACK超时。Host健康PASS、Realm退出0和资源恢复；Proxy失败清理中的两条WARN保留。g完整日志已拉回并逐文件SHA核对。

为提高诊断可读性，将失败CS ACK/低8位fault/fatal类型前置到短日志行，修正原日志这两个类型的名称顺序；不改变启动/授权/回收规则、失败回复字段或能力位。新`firmware-private-compacttrace/`及`private-compacttrace-candidate/`独立保存，原g输入不覆盖。固件后端模型、RMM构建和FIT/布局检查通过；部署与下一轮结果另记。

统一记录：定位父层ACK已接收、stream检查失败，缩短串口诊断｜f/g预热FAIL、无分数 → 下一轮待验证｜分差及百分比N/A｜仅诊断RMM变化，Guest/Host/runner/initrd保持相同｜以上run-id、rc及各实验目录日志｜保留原失败，不将START发布/父层ACK当作成功完成。整体goal active，无新增有效性能测量。


## 实机h与批量完成计数语义修正

`private-heap-rmm-20261030-e`已将短日志固件部署SD2并恢复，rc0；`private-heap-720-20261030-h`负载rc1，无glmark成绩，Host健康PASS、两Realm退出0和资源恢复。短日志确认发布后step10等待未通过、最后观察的CS ACK/fault/fatal均零；这只是最后一个硬件stream的快照，不能据此断定活动stream状态。继续增加精确未确认stream位图、参与队列ACK及父/子握手差异的失败日志，不修改授权或成功判定。h日志已拉回并逐文件SHA核验。

代码审阅另发现独立问题：任务wrapper沿用原生opcode51 `SYNC_ADD64`，但第二/第三个同队列成员的MOV48加数错误地设为序号2/3，使完成计数变为1、3、6，和检查所需的1、2、3冲突。现在每个wrapper固定加1，删除已无用途的ordinal参数；成员序号仍由真实队列计数与受保护ring顺序解释。后端模型不再仅检查编码中的序号，改为解码MOV48/SYNC_ADD64操作数并逐次累加，检查每个消费前缀的实际算术值，覆盖同队列重复成员和fence-only。`dma-sync-add.log`及`unit-sync-add.log`均rc0；新模型配旧实际wrapper预期SIGABRT（binary rc−6），失败点`sync_value == j + 1U`，见`old-sync-add/{compile.log,run.log,result.json}`。这是指令语义模型，不是GPU执行；该缺陷也不解释当前单成员START失败。

Guest失败日志补上NULL参数保护。Proxy Image构建通过；Client首次重建因未传既有`CONFIG_EXTRA_FIRMWARE_DIR`、找不到固定固件而失败rc2，保留`client-trace-nullguard.log`；显式指向已核验固件目录后重建rc0，见`client-trace-nullguard-reviewed.log`。未下载或更新固件。新增握手位图诊断及计数修正的RMM ARM64构建、176阶段后端模型、FIT/含BSS布局检查通过，见`rmm-syncdiag.log`、`dma-syncdiag.log`、`syncdiag-{fit,layout}.json`；RMM预留仍不扩大。

新`private-syncdiag-candidate/`配`firmware-private-syncdiag/`，保留h输入，仅更新两端诊断NULL保护Image和RMM（计数/失败诊断），initrd/runner/Host不变。下一轮部署/运行结果另记；整体goal active，完整执行位仍清零。

统一记录：修正批量SYNC_ADD64完成前缀算术并细化START超时诊断｜h预热FAIL、无分数 → 新组合待实测｜分差及百分比N/A｜新计数与诊断组合，不归因性能效果｜以上run-id、构建/负对照日志和冻结哈希｜保留；真实GPU任务/缓存/攻击/完整720p仍未通过，无新增有效性能测量。


## 2026-10-30 i 轮定位与 START 后状态刷新

i 轮 `private-heap-720-20261030-i` 退出1，UART明确记录 `GPU START wait cs=1 child=0 csg=0 active=0`：活动CS0仍为STOP，其余握手差异为0。Host独立健康检查PASS，VM退出码0/0、CPU/频率及资源恢复；证据已回收且10份文件SHA与板端一致。失败没有有效glmark分数。f固件部署 `private-heap-rmm-20261030-f` 退出0，只证明SD2更新/启动恢复，不代表负载成功。

原生 `panthor_sched.c` 注明队列状态在组挂起或 STATUS_UPDATE 时刷新。新RMM路径先严格等待START/endpoint及父子门铃ACK，再单独切换STATUS_UPDATE、清理CSG/global输入并通知；总等待仍有界，只有新的STATUS及门铃ACK、每条CS真实状态与错误检查、真实根和context复核全部通过才返回START成功。停止槽位重用时继承已确认status toggle，避免清零输入意外发布旧请求。任何部分发布/超时仍保留任务与页引用，重试不重复启动。不接受Proxy自报完成，不削弱错误/映射检查。

后端模型在START时刻意保留旧CS快照，只有后续STATUS请求才更新；新增父门铃ACK缺失、STATUS ACK缺失、CS状态缺失三个场景，共179阶段通过。旧START代码在同一模型的正常启动用例预期断言失败，见 `old-start-status/{run.log,result.json}`；仅说明模型覆盖缺失刷新，尚非实体GPU根因证明。完整私有测试通过；首次适配模型期间的失败日志均保留为 `dma-start-status*.log`。RMM ARM64构建、FIT/ELF一致性及含BSS布局通过，实际末址仍0x2800000，预留零余量。平台增加仅故障位图的失败日志，不打印页表根/数据地址。

改动目的｜补充START后的新鲜状态观察并保留严格确认｜对照i轮无有效私有分数 → 本版尚未实测｜绝对/百分比变化不可计算｜Client/Proxy/Host/initrd/runner保持i轮输入，RMM改变｜本地命令 `bash scripts/check/check-dma-guard.sh`、`bash scripts/check/check-rmm-gpu-private.sh`、`cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8` 均退出0；日志 `dma-start-status-final.log`、`unit-start-status.log`、`rmm-start-status.log`；`start-status-{fit,layout}.json`通过｜待硬件验证，执行能力位不变。


### j 轮：状态刷新候选仍失败，揭示固件 AS0 故障

`private-heap-rmm-20261030-g` SD2固件部署退出0、Host恢复；`private-heap-720-20261030-j` 完整720p入口退出1，未进入有效glmark。UART新增明确 `GPU FW fault mmu=1 gpu=0`，说明AS0固件地址空间发生MMU fault；同时状态刷新握手差异bit5仍未确认，活动CS仍STOP。故不能认定缺失STATUS_UPDATE是实机根因，也不能通过放宽CS检查规避故障。后续应解码固定fault类型/访问种类，定位可信固件所需映射。部署FIT SHA `801f93d900803d434e74d3374086a54429895a1578eb2de364c70da263669cca`，RMM SHA `783ed4d1eaa5c6d5e5af292ff986c718c915ea6995e2b71ac419403605332271`；Host/Guest/initrd/runner与i轮相同。

Host独立健康PASS，无新增BUG/WARN/OOM，VM0/0、CPU0-1及频率恢复，无遗留VM/挂载；10份远端证据已回收并SHA核对。改动目的｜补充新鲜启动状态观察与故障诊断｜i无有效分数 → j无有效分数｜分差/百分比不可计算｜仅RMM变化｜上述两个run-id、命令和退出码见 `build/lab-runs/`，实际故障见j的 `gpu-uart.log`，负载/恢复见 `realm-evidence/summary.json`｜保留诊断与失败，不宣称任务、安全或性能PASS；goal active、完整执行位清零。


### AS0 故障分类诊断与独立启动恢复

新增固定AS0故障寄存器诊断，仅记录exception低8位、访问类型、source ID和粗粒度区域类别（空页/固件低地址/共享接口/可信MCU arena/Client受保护控制区/其他），不记录故障VA、根、PTE或Client内容。不修改任何映射/权限/启动成功判据。`dma-as0diag.log` 179阶段后端回归、`rmm-as0diag.log` ARM64构建、`as0diag-{fit,layout}.json`均通过，末址仍0x2800000；新冻结 `private-as0diag-candidate/` 与 `firmware-private-as0diag/` 只更新RMM，SHA `595ecae8e234b3719c343091c12e0af7202c0ddd0e659e557a7c406e0a3589ad`。

部署 `private-heap-rmm-20261030-h` 写入SD2后，Host未在期限内恢复，入口退出1，UART与实际启动区备份均保留；未运行GPU负载。这一失败不改写为部署PASS。独占离线恢复 `private-heap-recover-20261030-a` 仅重启同一板、未刷任何存储，原诊断固件正常启动；KVM Realm能力1、Host release与CPU0-1核验，wrapper退出0。恢复前Host状态不可取得，before/after可比检查记NOT_RUN。恢复脚本初版将KVM能力stdout误记到kernel元数据字段，原记录保留，`recovery-correction.json`依据独立after.json纠正版本并注明来源；脚本在运行结束后修正。

随后完整720p入口 `private-heap-720-20261030-k` 退出1，仍无有效分数。AS0明确报告 `type=c3 access=2 source=7cd0 region=2`：固件低VA区域的读访问L3 translation fault，而非写保护错误；需定位缺失虚拟页。Host独立健康PASS，VM0/0及资源恢复。所有这些诊断/启动恢复不构成GPU任务成功、性能或实体隔离证明；故障类型和后续分析待本轮结束记录。


k轮10份日志已回收并SHA核对，完整执行能力位仍清零。下一阶段拟将AS0低地址故障的固件虚拟页号与固定镜像布局对照；不输出物理地址、页表根或Client内容。


### l 轮：AS0 故障页定位与 MCU 共享窗口修正候选

`private-heap-rmm-20261030-i` 仅将页号诊断固件部署至 SD2，退出0；配套 `private-as0page-candidate/` 与 `firmware-private-as0page/`，RMM SHA `3fe456e0d3dcf7da5243d3354e1237986b5570b05ee59d68956e802a17b09fca`。诊断仅在 AS0 低固件地址区域打印虚拟页号，不打印物理地址、根、PTE或Client内容。`dma-as0page.log`、`rmm-as0page.log`及FIT/布局检查通过，179阶段模型、预留末址0x2800000保持。

完整720p入口 `private-heap-720-20261030-l` 退出1；UART明确 `GPU MCU image fault page=7`，即读访问L3缺页位于 `0x7000` 页。固定镜像在低VA仅映射零页，不存在该页。Host健康PASS、VM0/0、CPU/频率/驱动和资源恢复，10份板端证据已回收并SHA核对；仍无首个成功私有GPU任务或有效glmark分数。不能通过为未知页补映射或放宽故障检查来解决。

对照固定工作树原生 `panthor_fw.c`：`CSF_MCU_SHARED_REGION_START=0x04000000`、`SIZE=0x04000000`；`panthor_fw_init()` 将 MCU 运行时自动分配区限制在该窗口，suspend及ring-I/O均从中分配。原RMM arena恰从窗口上界 `0x08000000` 开始；即使软件PTE有效，也未遵循这一路径的MCU地址窗口约束。新候选将完整16MiB arena放到 `0x05000000..0x06000000`，避开固定镜像共享接口 `0x04000000..0x0400c000`；映射冲突拒绝、CPU隐藏、RW/XN/NC、对象和任务授权及真实硬件成功判定均保留。诊断类别先判断arena再判断共享窗口，避免新布局被误归类。尚未证明该窗口差异就是实体故障根因，不宣称硬件存在某种已确认的地址截断。

新增编译期完整arena窗口约束及模型中实际suspend/I/O地址范围检查；旧header/核心配新模型在窗口断言预期SIGABRT，见 `old-mcu-window/{compile.log,run.log,result.json}`。179阶段后端、完整私有回归、ARM64 RMM构建、固定上游补丁清单校验、FIT/含BSS布局均退出0；分别见 `dma-mcu-window.log`、`unit-mcu-window.log`、`rmm-mcu-window.log`、`patches-mcu-window.log`及 `mcu-window-{fit,layout}.json`。仍使用17张MCU页表、预留末址0x2800000，没有扩大可信内存。

新 `private-mcu-window-candidate/` 与 `firmware-private-mcu-window/` 仅更新RMM；RMM SHA `b47ab25956d89c338de8644cdebe6d7762688106b73fb9ab0c9230bf770d82d8`。两端Image、Host、initrd及runner与l轮逐字节一致。SD2部署 `private-heap-rmm-20261030-j` 及后续负载结果待补充。

统一记录：核对并修正MCU运行时地址窗口｜l轮FAIL、无有效私有分数 → 新候选待实体验证｜绝对/百分比变化N/A｜仅RMM窗口及约束/诊断分类变化，其他运行输入相同｜上述run-id、命令/退出码/日志及冻结SHA｜保留候选待验证，完整执行位清零、goal active；无新增有效性能测量，历史共享1405不可继承。


窗口候选SD2部署 `private-heap-rmm-20261030-j` 退出0、Host恢复。`private-heap-720-20261030-m` 退出1，Client在phase2 TASK_PUBLISH返回STATE（−EBUSY），尚未执行START；没有可用于判断原AS0故障是否消除的启动样本，不能把UART未见原缺页当作修复证明。固件bootstrap仍CONFIGURED；Host健康PASS、VM0/0及资源恢复，10份证据已回收并SHA核对。当前下一步是定位发布阶段的具体失败条件，仍无有效私有分数；分差/百分比N/A，goal active、执行能力位清零。


### 发布失败检查点诊断（m轮后）

为定位TASK_PUBLISH拒绝，RMM仅在失败时记录context复核状态、控制页游标不匹配位图、global/parent/child/CSG握手差异与检查阶段；不记录游标值、数据、VA或PA，不改变授权/发布/成功条件。诊断位图的首版控制机编译触发有符号/无符号条件表达式警告并按Werror失败，保留 `dma-publishdiag.log`；显式uint32_t转换后 `dma-publishdiag-reviewed.log` 179阶段与 `rmm-publishdiag-reviewed.log` ARM64构建退出0。早于修正组装的 `firmware-private-publishdiag/` 未部署，不能与当前ELF混用。

实际配套包 `private-publishdiag-candidate/` 与 `firmware-private-publishdiag-reviewed/`，RMM SHA `fbf7b505eefb1a040b75b5dbb47dce813846afb4c913d47c47892acd4bd47fed`，FIT/含BSS布局通过、预留不变；SD2部署 `private-heap-rmm-20261030-k` 退出0，Host恢复。仅RMM改变，Host/Guest/initrd/runner与m轮一致。n轮完整720p入口已启动，结果待补充；仍无有效私有性能成绩，执行能力位清零。


n轮 `private-heap-720-20261030-n` 退出1，失败检查点明确 `GPU PUBLISH ack glb=0 parent=0 child=0 csg=10 halt=0`、`step=3`：唯一差异是CSG endpoint配置toggle bit4。PREPARE只继承STATUS bit5并清零bit4，而停止槽位固件ACK可保留bit4=1；PUBLISH因此看到伪造的待确认配置请求。下一步在停止槽位准备时同时继承已确认endpoint/status位，START仍从真实ACK显式切换endpoint以请求本次配置；不放宽发布握手。n未执行START，不能判断原AS0故障是否已消除。Host健康PASS、VM0/0、资源恢复及10份日志SHA通过，仍无有效私有分数。


### 停止槽位 endpoint toggle 继承修正

PREPARE现从同一停止槽位的受保护ACK同时继承bit4 endpoint与bit5 status，低三位仍STOP；不发门铃，也不发新配置。START仍依据最新真实ACK反转endpoint，必须经过原有父/子、新状态ACK、CS及实际根/context检查。这是消除准备阶段意外制造的请求，不是忽略待确认请求。

后端的现有deferred发布场景36/37补充停止槽位ACK=0x10及0x30两种起始组合，检查准备时无门铃、无新增endpoint/status请求，并继续原发布/START/完成验证。全部179阶段通过；旧核心配新模型在0x30掩码一致性断言预期SIGABRT，见 `old-endpoint-toggle/`。完整私有回归、ARM64 RMM、FIT/含BSS布局通过，分别见 `dma-endpoint-toggle.log`、`unit-endpoint-toggle.log`、`rmm-endpoint-toggle.log`和 `endpoint-toggle-{fit,layout}.json`。

新 `private-endpoint-toggle-candidate/` 与 `firmware-private-endpoint-toggle/` 仅改变RMM，SHA `298fc3013664ec4d0a932ddbcd5ba655e033cabc1ed47460a18544bd7f055906`；其他载荷与n轮逐字节一致，MCU arena仍在新共享窗口，预留末址0x2800000。SD2部署 `private-heap-rmm-20261030-l` 及后续负载待补充。统一记录：修正停止槽位继承｜n发布FAIL、无分数 → 新候选待实测｜分差/百分比N/A｜仅RMM改变｜上述模型、构建、旧代码负对照与配套SHA｜待实体GPU验证，goal active、执行能力位清零，无新增有效性能测量。


### o轮：首个私有计算成功，图形校验仍失败

SD2部署 `private-heap-rmm-20261030-l` 退出0，Host正常恢复；实际配套为上述 endpoint-toggle 候选。`private-heap-720-20261030-o` 完整720p入口退出1，但计算预热已在 Mali-G610 (Panfrost) 上得到 `COMPUTE_CHECK=PASS count=1 samples=1 formula=x*3+7+alu_mix alu_iters=1`。计算走正常私有任务、真实 COMPLETE/RETURN/RETIRE 和本地成功 fence 路径，是首个实体私有计算校验成功；并非完整缓存覆盖、图形或隔离验收。

随后 glmark validation 的 `[build] use-vbo=false` 报 VM_BIND err=5、进程退出139，成功/失败/未知统计均0，不能提取有效分数。UART记录 `GPU START fail step=6 cs=40000011 fault=0 fatal=49`，异常为 CS_INSTR_INVALID。START函数也被完成查询作为只读复核调用，Client主错误发生在phase4 COMPLETE；不能据此写成首次START从未成功。本轮没有先前AS0缺页日志，且计算实际完成，但窗口与endpoint修正组合不能用于分别归因。

Host独立健康PASS；VM退出码 **[0,−15]**，Client在失败清理期间被终止。after.json确认CPU0–1、pmthor、频率恢复、无残留实验进程或挂载。`build/lab-runs/private-heap-720-20261030-o/` 保存 result.json、gpu-uart.log、host-kernel-health.json、realm-evidence 与10份文件SHA一致的 evidence-transfer.json。可选 SYNCOBJ_EVENTFD 的errno2和Proxy失败清理GPUVA WARN仍保留，不用Host健康PASS覆盖Guest问题。

统一记录：继承停止槽位真实endpoint ACK并验证私有GPU执行｜n发布FAIL、无分数 → o计算预热PASS、图形校验FAIL、无分数｜绝对/百分比变化N/A｜仅RMM变化，Host/Guest/initrd/runner与n相同；包含之前窗口修正｜命令 `python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-o -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-endpoint-toggle-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，退出1；部署命令及退出0见对应run的result.json｜保留，继续定位图形命令异常。无新增有效性能测量，执行能力位清零、goal active；隔离及后续完整回归未验收。


### 连续提交的原生 CS 状态保留候选（o轮后）

对照固定 Mesa 25.0.7 的 `csf_init_context()`（本地参考 `build/realm-performance-20261018/mesa-25.0.7-reference/pan_csf.c:1450`）：创建上下文后，先单独提交 HEAP_SET 与 tiler OOM exception handler 初始化，等待后释放临时命令 BO；后续绘制仍依赖该组的 CS 状态。原 RMM 每批 COMPLETE 后直接 TERMINATE，RETIRE 又清零整组 suspend/I/O/ring/sync，未实现原生跨提交状态语义。此差异能解释计算成功而绘制异常，但仍须实机验证，不能仅凭源码宣布0x49根因已确认。

候选改为：仅在 fresh STATUS、真实消费前缀、完成sequence及所有已启用队列空闲/无错误成立后，先请求 SUSPEND 并等待真实组/门铃ACK，将原生状态保存在该组受保护 suspend buffer，再沿用 TERMINATE/CS STOP、FLUSH_MEM、禁用AS、Client缓存RETURN。成功RETIRE保留同owner/generation组的控制页并退休精确任务token，下一批用 RESUME；显式中止仍全量清理，组销毁时先解除GPU别名再清零全部保留页。挂起/回收不确定时隔离并保留引用，不能升级成成功。

ring改用64位持续递增的INSERT/EXTRACT及完成序号；存储位置按ring大小环绕，128字节wrapper不会跨页。可信基准放在MCU input页64字节偏移，独立于16字节硬件I/O ABI；该页没有Client GPU别名或Proxy CPU映射，不信任可写sync页提供历史。提交发布、成员进度及最终完成均相对该基准核对；成功退休提交历史，部分写失败不释放。恢复和停机覆盖该组此前启用过的队列，即使本批仅提交其他队列。

新增9类实际核心/平台后端模型，含38轮连续提交/ring环绕、受保护状态保存与RESUME、旧token/计数拒绝、通知/组ACK/父ACK失败、根变化、坏历史、部分退休历史写入、单队列续提交与旧队列停机；原179阶段保留，共188阶段通过。旧核心配新模型在正常完成后误清保留页的断言预期SIGABRT，见 `old-persistent-csg/{compile.log,run.log,result.json}`。初期夹具对read尺寸、清零、资源查询时机及缺失flags参数的失败均保留为 `dma-persistent-csg-{initial,model1,model2,extra1}.log`；不隐藏失败或将模型当作GPU执行。

`bash scripts/check/check-dma-guard.sh`、`bash scripts/check/check-rmm-gpu-private.sh`、ARM64 RMM构建及固定上游补丁校验均退出0，日志为 `dma-persistent-csg-reviewed.log`、`unit-persistent-csg-reviewed.log`、`rmm-persistent-csg-reviewed.log`、`patches-persistent-csg.log`。独立FIT/ELF与含BSS布局检查通过，末址仍0x2800000、无预留扩张。初次 `firmware-private-persistent-csg/` 早于“停止所有已启用队列”修正，仅保存未部署输入。实际配套为 `private-persistent-csg-candidate/` 与 `firmware-private-persistent-csg-reviewed/`，RMM SHA `809297955557c87ae9e3c79bd0df9cf09a13ae07d52e264693f94209d45151b0`；Host/Guest/initrd/runner与o轮逐字节相同。

统一记录：保留原生CS跨提交状态并避免旧ring重放｜o计算PASS/图形FAIL、无有效分数 → 新候选待实机｜分差/百分比N/A｜仅RMM改变，保留真实完成/错误/根/缓存/停止判据｜以上命令、退出码、负对照与冻结SHA；SD2部署 `private-heap-rmm-20261030-m` 及负载结果待补充｜待验证，完整执行位清零、goal active；无新增有效性能测量，不继承历史共享1405。


状态保留候选 SD2部署 `private-heap-rmm-20261030-m` 退出0，Host/Realm能力恢复。`private-heap-720-20261030-p` 入口退出1，在计算预热的Mesa初始化任务phase4 COMPLETE返回−EBUSY；glBufferData随后VM_BIND err=5，renderer qualification失败，未出现COMPUTE_CHECK=PASS，也没有进入glmark validation或取得分数。这比o轮更早失败，不能认定状态保留实现已修复图形异常。UART没有START/AS0故障诊断，仍需定位完成观察、SUSPEND或后续终止握手。Host健康PASS、VM0/0，CPU/频率/驱动与资源恢复；10份证据已回收并SHA核验，见p轮 `result.json`、`gpu-uart.log`、`host-kernel-health.json`、`realm-evidence/` 和 `evidence-transfer.json`。

统一记录：状态保留首次实机｜o计算PASS/图形FAIL、无分数 → p计算预热FAIL/无分数｜分差/百分比N/A｜仅RMM改变｜命令与o相同结构，候选改为private-persistent-csg-candidate、run-id改为private-heap-720-20261030-p；负载rc1、部署m rc0｜保留失败及输入，追加挂起/终止/观察阶段失败诊断，不放宽ACK或完成判据。goal active、执行能力位清零，无新增有效性能测量。


## 2026-10-30 q轮诊断与原生SUSPEND静止边界修正

诊断固件 `firmware-private-quiesce-diag/` 与 `private-quiesce-diag-candidate/` 的 RMM SHA为 `5fc98fc27f828d7bc2ec7f78aa62d9094536253fb2744fce43c7cf679c1df3da`。SD2部署n退出0；q轮完整720p入口退出1，UART为 `GPU QUIESCE fail step=6 preserve=1`、`csg=10/30000012 parent=0 child=1 streams=0`：真实SUSPEND已经确认，额外TERMINATE/child握手未确认。没有COMPUTE_CHECK=PASS、有效glmark分数或隔离验收。Host健康PASS、VM0/0，CPU/频率/驱动/资源恢复，10份证据回收SHA通过。日志为 `build/lab-runs/private-heap-720-20261030-q/`。这定位了p/q初始化回归，不证明o图形0x49的唯一根因。

固定原生 `panthor_sched.c` 的 `csg_slot_sync_state_locked()` 在SUSPEND ACK后仅通过 `cs_slot_reset_locked()` 重置CS输入；代码明确不等待CS ACK、不再发门铃，后续START/RESUME时才重新使用。新候选成功COMPLETE以已确认SUSPEND为非执行边界，核验parent/child/CSG/status及错误，再局部重置CS请求、实际FLUSH_MEM/禁用AS、复核真实sequence，之后才允许Client缓存返回。中止路径继续要求真实STOP/TERMINATE ACK。退休保留已确认SUSPEND及门铃/状态toggle，清除地址；PREPARE只接受已确认TERMINATE或SUSPEND，后者允许旧CS START快照，但新启动必须取得独立新STATUS_UPDATE ACK及全部当前队列状态，不能把旧状态当完成。

193个实际固件/平台模型通过，包括38轮ring环绕、连续RESUME、跨Client身份、无SUSPEND/parent ACK、根异常、挂起后CS错误/child变化及复用前CSG/CS损坏；完整本地私有回归、ARM64、上游补丁清单、实际FIT与含BSS布局检查通过。旧q核心在聚焦的原生成功路径模型中预期失败，额外TERMINATE发布违反SUSPEND后的clean轨迹；早期模型夹具失败日志保留。预留末址仍0x2800000、无余量。

新冻结包 `private-suspend-barrier-candidate/` 只配套 `firmware-private-suspend-barrier/`，RMM SHA `36e4723c0c15bfa9ab3a063cf4c27a0d3540ac301712f076807e318c237a1d5e`。Host/两端Image/initrd/runner与q相同，仅RMM改变。SD2部署o与完整720p的r轮结果待记录。统一记录：原生挂起静止边界｜p/q初始化FAIL、无分数 → 新候选待实机｜分差/百分比N/A｜仅RMM变化｜命令/rc/日志按run-id保存｜待验证。无新增有效性能测量；完整执行位保持清零，goal active。


SD2部署o退出0，Host恢复；r轮完整720p入口退出1。相较p/q，真实COMPLETE和CPU RETURN已通过，Client在phase6 RETIRE返回−EPROTO；未出现QUIESCE/START/OBSERVE故障日志。检查发现 `realm_gpu.c:task_call()` 仍把RETIRE的scrubbed-pages==0一律视为坏回复，而成功SUSPEND路径保留原生状态，合法退休确实清理0页。这是Guest协议适配遗漏，不能把r称为计算或图形PASS。无COMPUTE_CHECK=PASS/有效分数，Host健康PASS、VM0/0、资源/CPU/频率/驱动恢复，10份证据回收SHA核验。修复前保留r输入和日志；后续仅允许成功退休返回0页，INCOMPLETE仍不得返回0进度，并继续核验完整标志、队列、保留字段及上界。


## 2026-10-30 成功保留上下文的零清理页退休回复

`realm_gpu.c:task_call()` 已支持成功RETIRE的scrubbed-pages==0；仍要求成功标志为1、精确原队列、保留字段零与页数上界，INCOMPLETE必须为完成标志0且正清理进度。RMM仍独立完成SUSPEND、AS禁用、CPU RETURN与真实退休，Guest不会据页数自行断言任务完成。新增7项实际解析函数测试覆盖合法零页、完成标志/队列/保留字段/过大页数/INCOMPLETE零进度或伪完成；任务桥共94项、完整私有本地回归、Client Image构建通过。旧解析器编译成功但在合法零页测试预期失败，证据 `old-retire-zero/`；r失败与上一检查点2667项哈希/独立核验保留。

新冻结 `private-retire-zero-candidate/` 配已部署的 `firmware-private-suspend-barrier/`，仅Client Image从 `be00618a...` 变为 `975e8c9320c80b23cf59011f7e54e1fbefcf06497f45695a66f2c2864783bb15`，Host/Proxy/initrd/runner/RMM均同r，无需重刷。s轮完整720p入口待记录。统一记录：支持保留状态的合法退休回复｜r phase6 −EPROTO、无分数 → s待验｜分差/百分比N/A｜仅Client变化｜命令/rc/日志按run-id保存｜待验证。无新增有效性能测量，执行能力位保持清零。


s轮完整入口退出1：私有GLES计算PASS、glmark validation为26成功/1预期失败/6未知，额外失败0，33个计分场景全部执行，原始总分 **0**。普通场景帧时442–1017ms，terrain约59096ms；这是性能失败，不能作为通过成绩，也不据此宣称达到1000门槛。GLMARK_CLEAN_RESULT=PASS、BO/export/VM_BIND/submission错误均0，预期framebuffer错误1、额外0；无新GPU START/QUIESCE/OBSERVE故障。Host健康PASS、VM0/0、CPU/频率/驱动及资源恢复，11份板端证据回收SHA核验（以evidence-transfer实际数量为准）。日志 `build/lab-runs/private-heap-720-20261030-s/`。多Client、隔离攻击、动态堆扩容覆盖仍未验收，完整执行位清零，goal active。

统一记录：成功保留状态的Guest退休回复｜r退休协议FAIL、无成绩 → s计算/图形验证PASS、完整33场景原始0分/性能FAIL｜绝对/百分比变化N/A（r无分数）｜仅Client Image变化，RMM/Host/Proxy/initrd/runner相同，历史共享1405不可比｜s命令/rc1/result/realm-evidence/evidence-transfer及Host健康日志｜保留功能修正，性能待优化。当前READY/RETURN按512项有界续处理，而Client每次INCOMPLETE都等待一个tick；将先诊断并优化CPU处理分片等待，不能放宽GPU完成和安全回收判定。


## 2026-10-30 有界缓存续处理调度优化与阶段计时（s轮后）

READY/RETURN每次最多检查512项，空项和非叶子项同样消耗检查预算；RMM仍核验Client/对象/页表权限并对私有数据逐页执行必要同步。旧Client把这些纯CPU游标的INCOMPLETE也当作设备等待，每次额外延迟一个tick。现改为READY/RETURN/RETIRE立即排入下一个独立work item，每批结束释放锁，保持原截止时间；GPU COMPLETE/OOM、准入和未满足依赖继续原有等待。真实GPU完成、SUSPEND、AS禁用、CPU RETURN及精确退休条件不变。

新增四类真实worker模型覆盖立即续跑/设备等待、单次有界调用、锁释放、原截止时间与禁止提前fence；提交模型95项、完整私有回归、Client ARM64 Image构建通过。旧worker在新增调度断言中预期失败（编译rc0、运行SIGABRT），见`old-cache-continuation/`。日志`submit-cache-continuation.log`、`unit-cache-continuation.log`、`client-cache-continuation.log`均rc0。本地替身不证明真实并发或GPU执行。

冻结`private-cache-continuation-candidate/`仅替换Client Image（SHA `b33106b56bc517e38548aafbcf949282b09369c486d5aaa360ff92deda3401bc`），仍配已部署`firmware-private-suspend-barrier/`，无需刷写固件。t轮完整720p已启动，私有计算预热和图形validation通过，最终成绩/退出/健康/恢复待记录，不能由进行中结果宣称性能通过。统一记录：取消纯CPU处理片间tick等待｜s完整33场景原始0分/性能FAIL → t待测完｜绝对/百分比变化待定，0分对照不可计算百分比提升｜仅Client调度变化，Host/Proxy/RMM/initrd/runner相同｜命令及状态见`t`的result.json｜待验证，完整执行能力位保持清零。

另冻结`private-phase-profile-candidate/`（Client SHA `e059b8d2d4c099f8af5d6e9fdc78466e26e01f8ce6e51d66cadc3838b19f2467`），在上述调度基础上加入按文件累计的只读诊断：0 PREPARE、1 READY、2 PUBLISH、3 START、4 COMPLETE、5 RETURN、6 RETIRE分别统计calls、INCOMPLETE次数、操作墙钟op_ns及下次work item运行前gap_ns，worker排空后统一输出。没有逐页/逐任务日志，不改变安全判据或RMM ABI。`submit-private-phase-profile.log`、`unit-private-phase-profile.log`及`client-private-phase-profile.log`均rc0；新增计时断言与原95项行为模型通过。计时覆盖RPC/RMM/设备状态观察，不等于纯GPU执行时间；不包含未选中队列排队、STAGE及BO分配。此诊断候选未部署，无新增性能测量。


t轮最终入口rc1，完整33场景为 **36分**，较s原始0分增加36分；0分对照的百分比提升不定义。私有计算与validation26/1/6、额外失败0通过，BO/export/VM_BIND/submission错误均0；build(use-vbo=false)帧时442.174→20.295ms（−421.879ms、−95.41%），terrain59095.878→2424.235ms（−56671.643ms、−95.90%），refract13238.023→526.484ms（−12711.539ms、−96.02%）。仅Client的CPU续处理调度变化，可将本次组合的改善归因于该调度策略，但不能据此分解READY/RETURN各自占比，也不能据帧时比值宣称整体glmark百分比提分。36仍未达到1000分门槛，保持性能FAIL。

Host健康PASS、VM退出0/0；after确认CPU0–1、pmthor、无残留实验进程/loop，频率及资源恢复。失败后读取Proxy kernel-log出现`timeout waiting for XSHM_COMMAND_EXIT`，保留failure_log_errors，不称所有Guest日志采集/健康通过。10份板端证据已回收SHA核验，位置`build/lab-runs/private-heap-720-20261030-t/`，s/t逐场景对照为`cache-continuation-scene-comparison.json`。统一记录：取消CPU有界续处理的定时等待｜s0分→t36分｜+36分，百分比N/A；上述代表帧时差值｜仅Client Image变化，其余条件同s｜t/result.json命令、rc1，realm-evidence与evidence-transfer.json｜保留优化，性能/隔离/多Client验收仍未通过，完整执行位清零、goal active。

u轮使用`private-phase-profile-candidate/`启动同一完整720p测试，预期只增加阶段诊断，结果待补充。不能将未完成计时数据作为瓶颈归因或性能通过依据。


u轮完整33场景仍36分，t→u差0分/0%；私有计算与validation26/1/6、额外失败0、各BO/export/VM_BIND/submission错误0，完整入口因1000门槛rc1。Host健康PASS、VM0/0、CPU/频率/驱动和资源恢复；本轮两端kernel-log回收完成，无t轮同类failure_log_errors，11份证据SHA核验。计时数据来自实际Client关闭benchmark文件时输出的七条累计记录，提取报告`private-phases-u.json`；readout去重内核日志重复记录，不把相同消息重复计入。

13796个任务切片中，READY与RETURN各605041次有界调用、591245次INCOMPLETE，平均每任务约43.9次调用。READY操作108.453s、worker gap0.700s，占已统计阶段墙钟32.84%；RETURN操作124.873s、gap0.545s，占37.73%；COMPLETE操作4.135s、gap80.456s，占25.45%。PREPARE1.363s（0.41%）、PUBLISH0.266s（0.08%）、START3.541s（1.07%）、RETIRE8.010s（2.41%）；其他gap很小。总计约332.38s，覆盖有选中任务的操作和阶段间worker间隔；不含应用CPU、BO分配、STAGE及未选中队列等，因此这些比例不是完整应用时间或纯GPU时间分解。数据支持先优化整上下文缓存交接，再优化完成重试等待；不支持把Proxy RPC作为当前主要瓶颈。缓存同步如何减少仍须保持真实所有权/映射授权、CPU/GPU可见性、退休和错误语义，不能单凭这些比例删除必要维护。

统一记录：阶段只读计时｜t36分→u36分｜0分/0%；计时不宣称提分｜仅Client诊断增加，其他冻结输入不变｜`private-heap-720-20261030-u/result.json`完整命令、rc1，realm-evidence/host-kernel-health/evidence-transfer及`private-phases-u.json`｜保留诊断与t优化，整体性能仍FAIL，隔离/多Client等NOT_VALIDATED，执行位清零、goal active。


## 2026-10-30 有界短时COMPLETE重查候选（u轮后）

u轮实际观测表明COMPLETE的worker间隔累计80.456s；现在仅对已START的真实COMPLETE INCOMPLETE前8次采用`usleep_range(50,100)`后重排独立work item，休眠前释放private_gpu_lock、之后重新取得锁并核验关闭状态。随后仍未完成则恢复原tick等待，避免长任务持续高频查询。原绝对截止时间不延长，START不重放，READY/RETURN/RETIRE及真实设备状态/ACK/根/错误检查不变。关闭路径先同步取消worker，保证休眠期间pcfile仍存活；故障或中止不升级为成功fence。

提交模型共98项，新增有界8次短重查后退避、休眠期间关闭、休眠期间原deadline到期，保留单次真实调用、无锁休眠及禁止提前完成检查。完整私有回归、Client ARM64构建及whitespace检查rc0，日志`unit-private-complete-poll.log`、`client-private-complete-poll.log`；旧u worker配新检查编译rc0、预期SIGABRT，见`old-private-complete-poll/`。早期`submit-private-complete-poll.log`只含96项（后续两个关闭/到期场景加入前），最终以完整回归98项为准，保留早期证据不覆盖。

新冻结`private-complete-poll-candidate/`仅改变Client Image（SHA `fa1b8863f1725df7b7ac5ec43d49c7ea14179f51f39166e38513ebf26c9623b5`），仍配已部署`firmware-private-suspend-barrier/`。v轮完整720p已启动，计算与图形validation通过，最终分数、退出、健康、资源恢复及计时归因待记录。统一记录：有界短时完成重查｜u36分→v待测｜绝对/百分比变化待测｜仅Client完成等待策略改变，RMM/Host/Proxy/initrd/runner相同｜v/result.json记录完整命令｜待验证，goal active、执行位清零；不将进行中校验当作性能/隔离验收。


v轮最终完整33场景 **46分**，对照u36分增加10分（+27.78%）；入口仍因1000门槛rc1。计算、图形validation26/1/6、额外失败0、BO/export/VM_BIND/submission错误均0，GLMARK_CLEAN_RESULT=PASS。Host健康PASS、VM退出0/0、CPU0–1/pmthor/频率/资源恢复、无实验进程或loop残留，两端kernel-log回收无failure_log_errors；11份证据SHA核验，见`build/lab-runs/private-heap-720-20261030-v/`。

阶段诊断显示v共17417任务切片（u13796），每任务COMPLETE gap约5.83→0.92ms，绝对累计80.456→15.967s；调用次数增加是更快重查及执行更多任务的共同结果，不能用不同任务数的累计操作时间直接比较单任务成本。READY/RETURN每任务操作约7.86/9.05→7.80/8.99ms，基本未变，二者含gap合计占v已统计阶段约88.3%；COMPLETE约6.7%。计时报告`private-phases-v.json`，CPU/GPU可见性同步仍逐页执行，RMM/固件/根/错误与完成判据均未改变。该证据支持短时重查在实体Realm环境有效，但不能把请求的50–100us直接当作实际唤醒延迟保证。

逐场景对照`private-complete-poll-scene-comparison.json`：build(use-vbo=false)20.583→16.253ms（−4.330ms、−21.04%），build(use-vbo=true)20.133→15.388ms（−4.745ms、−23.57%），terrain2288.666→2048.273ms（−240.393ms、−10.50%）。**末尾loop fragment-uniform=true场景24.153→73.195ms（+49.042ms、+203.05%）异常变慢**，原因未定，保留待查；不得称所有场景改善、不能删该场景或沿用旧PASS。累计计时不能定位该单场景根因，可能需要按场景取得页数/阶段诊断，不能用猜测归因。

统一记录：有界短时完成重查｜u36分→v46分｜+10分/+27.78%，上述代表帧时及末尾异常完整保留｜仅Client完成等待策略改变，其他冻结输入相同，同完整720p/performance/单Client条件｜v/result.json完整命令、rc1及回收日志/SHA｜保留优化，末尾异常和整体性能待解决；多Client/隔离攻击/动态堆事件覆盖仍未验收，完整执行位清零、goal active。下一步优先精确量化READY/RETURN的实际同步页数、空项/非叶子遍历与每批固定检查成本，再设计保持授权及CPU/GPU可见性的优化；不直接跳过页维护。


## 2026-10-30 缓存交接页次与分段诊断候选（v轮后）

仅增加Client只读诊断：从实际READY/RETURN回复的累计页进度取得同步页次差，记录无页进度调用数及其操作墙钟；计数回退只记诊断，不影响任务授权/完成判据。同步页次可能重复覆盖同一物理页，不能冒充唯一页数或总BO大小。每128个真正成功RETIRE的切片输出一条带内核时间戳的累积PRIVATE_WINDOW，供比较后半段场景的页次/调用/操作和完成等待成本；不会把RETIRE分批调用当作多个任务。不改变缓存操作、批次上限、RMM检查、ABI或短时完成等待策略。

首版完整本地回归/Client构建rc0；分离成功退休数与RETIRE调用数后，再执行完整98项提交/32项runner等本地回归及Client构建，`unit-private-cache-profile-reviewed.log`、`client-private-cache-profile-reviewed.log`均rc0，保留首版日志。源/构建输入在各自构建完成前未改动，第二次构建验证实际最终源；diff whitespace通过。`analyze-private-cache.py`解析现有阶段记录及新增字段/区间，按时间戳去重，明确不在未对齐时间的情况下将区间当作单个场景。

冻结`private-cache-profile-candidate/`仅改变Client Image（SHA `57f4d02fd5891813fdcbecc0a065b6509894d026ecb203e4b0f0e851c8cf4348`），其他输入与v相同，继续配已部署`firmware-private-suspend-barrier/`。w轮同一完整720p已启动，最终分数/正确性/退出/健康/恢复及缓存诊断待记录。统一记录：缓存交接读数与后段采样｜v46分→w待测｜分差/百分比待测，诊断不宣称提分｜仅Client诊断增加｜w/result.json完整命令｜待验证，完整执行位仍清零、goal active。


w轮完整33场景仍 **46分**，v→w差0分/0%，入口rc1、性能FAIL。私有计算与validation26/1/6、额外失败0及BO/export/VM_BIND/submission错误0，GLMARK_CLEAN_RESULT=PASS；Host健康PASS、VM0/0、CPU/频率/pmthor/资源恢复，无实验进程/loop残留。失败后Proxy kernel-log再次超时，failure_log_errors保留；Client日志回收正常，10份证据SHA核验。末尾loop uniform=true从v73.195ms恢复至17.832ms，但conditionals(vertex-steps=5)从18.132ms升至1817.898ms；累计COMPLETE gap达67.527s（v15.967s）。这些变化提示仍有间歇性长等待，但尚不能归因于某个中断、timer或Host调度问题，不把不同任务数的累计差简单等同于单次卡顿。

新计数：17167任务；READY/RETURN各740156调用、170092572同步页次，平均每任务每方向9908.11页次（38.70MiB等价操作量，并非唯一页数）。无页进度各361905次，占调用48.90%，READY零进度耗时4.900s/总133.094s，RETURN零进度15.780s/总153.811s；两方向零进度合计仅占缓存阶段操作约7.21%。因此空表跳过可减少调用，但主要成本仍在有页进度的批次；非空批平均操作338.9/364.9us，包含检查、页维护及RMM调用，不能进一步等同为纯cache指令耗时。无报告进度回退。报告`private-cache-w.json`、`private-phases-w.json`与逐场景`private-cache-profile-scene-comparison.json`。

PRIVATE_WINDOW只回收到5条（tasks16640起，而非预期第一条128），早期历史被128KiB Guest内核环形日志覆盖。直接证据是相邻采样间密集的BO_MMAP_OFFSET INFO（每帧两次），不能把仅剩末尾的样本用于定位更早conditionals异常。解析器把首条可见记录作为基线，不伪造缺失区间；`history_incomplete=true`，仅4个完整相邻区间。后续将例行成功mmap-offset日志改为DEBUG以保留诊断历史，不隐藏错误或健康告警；更细的异常归因与缓存维护优化尚待实现/验证。

统一记录：缓存页次/零进度与分段诊断｜v46分→w46分｜0分/0%，诊断不宣称提分；保留conditionals长延迟与loop恢复｜仅Client诊断变化、其余冻结输入相同｜w/result.json完整命令/rc1、Host健康、realm-evidence与evidence-transfer｜保留，性能/隔离/多Client仍未验收，执行位清零、goal active。

## 2026-10-30 保留完整缓存/完成窗口历史（x轮）

仅把成功BO_MMAP_OFFSET日志从`pr_info`改为`pr_debug`，保留错误和警告。未改任务调度、RMM授权、真实完成/ACK/根检查、缓存交接、退休或任何能力位。Client ARM64 Image构建rc0，日志`build/rmm-client-bo-20261030/client-private-log-quiet.log`；单条日志级别改动未新增本地测试，先前98项提交及完整私有回归是保留证据，不冒充本轮重跑。变更前源码保存在`before-private-log-quiet/`。

冻结包`build/rmm-client-bo-20261030/private-log-quiet-candidate/`中Client SHA为`42b05a3756e4424509f72d03b6028eb524c2a523abf57b13d49921d48e301c1b`。相对w仅替换Client，Host/RMM/Proxy/initrd/runner保持原哈希；继续使用已部署`firmware-private-suspend-barrier/`，没有再次刷写固件。实际命令：

```text
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-x -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-log-quiet-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

x轮入口rc1，完整33场景 **46分**，相对w46分为 **0分/0%**；性能门槛仍FAIL，不宣称日志调整提分。私有计算预热PASS，validation成功26/预期失败1/未知6、额外失败0；BO/export/VM_BIND/submission错误0，GLMARK_CLEAN_RESULT=PASS。Host内核健康PASS、dmesg未环绕、无新增报告错误；VM退出0/0，CPU/频率/pmthor恢复，无实验进程、挂载或loop残留。两端失败诊断日志均成功取得，本轮11份文件回收并与板端SHA逐一核验；w轮Proxy日志读取超时仍保留为历史失败。

日志采样目标已达到：135条PRIVATE_WINDOW的任务号严格为128、256……17280，完整保留benchmark的每128任务样本，末尾17338任务另有最终阶段计数；`history_incomplete=false`。另保留validation进程的独立最终阶段统计，不能与benchmark相加当作同一文件/任务序列。未报告页进度回退。

benchmark的READY/RETURN各760387次调用、172351775同步页次；平均每任务每方向9940.70页次，约38.83MiB等价操作量，仍不是唯一物理页数。READY操作134.873s、RETURN155.936s，两者占已统计阶段总墙钟330.856s的87.90%。零页进度各365290次（48.04%调用），两方向合计20.900s，仅占缓存阶段操作7.19%；非空批平均操作328.8/354.4us。其余阶段包含：COMPLETE操作6.259s及gap15.822s、RETIRE操作10.136s。不能将操作墙钟等同于纯GPU时间或纯cache指令耗时，分母仍不含应用CPU、BO分配、STAGE及未选中队列等。

连续窗口将一次长等待缩小到Guest内核时间131.773749–145.714282s的128任务区间：COMPLETE累计gap10.973s，占该阶段总gap约69.4%；相邻普通窗口该值约几十毫秒。但gap从上次操作排队时刻计到下次worker执行，包含短sleep及调度，不是单个中断/任务延迟，不能据此断言GPU、timer、Host调度或中断丢失是根因。w的conditionals(vertex-steps=5)1817.898ms本轮恢复18.020ms，而shading/cel从15.947ms升至101.042ms；benchmark观察墙钟414.225→366.103s。异常位置变化，不把单轮恢复解释成修复，也不把墙钟差全部归因于日志降级。

证据目录`build/lab-runs/private-heap-720-20261030-x/`包含完整命令/退出码/资源前后记录、`host-kernel-health.json`、`realm-evidence/`与`evidence-transfer.json`。分析为`private-phases-x.json`、`private-cache-x.json`、`private-log-quiet-scene-comparison.json`；清单更新器与独立核验保存本轮和原w检查点。下一步需区分异常gap内的sleep与排队时间，并评估保持所有页授权、锁、临时映射回收及可见性屏障的批量缓存维护；本轮只读核查了这些代码，没有实现或声称其收益。不能用整cache set/way刷新替代跨核逐页可见性，也不能把WB私有页直接切为与现有线性别名冲突的WC属性。

统一记录：降低成功日志级别以保留完整诊断历史｜w46分→x46分｜0分/0%，只确认采样覆盖改善｜仅Client成功日志INFO→DEBUG，其余冻结输入及完整720p/performance/单Client条件相同｜上述命令、x/result.json、rc1、11文件SHA及健康/恢复证据｜保留日志改动；性能1000门槛、异常延迟根因、多Client/隔离攻击/动态堆事件覆盖仍未验收，完整执行位清零、goal active。

## 2026-10-30 RMM 32页缓存窗口批处理（y轮，已撤回）

依据x的实际计数，READY/RETURN操作占已统计阶段时间87.90%，零进度仅占两者操作7.19%；因此本轮优化实际页面维护的批次组织。PT核心继续逐项核对冻结页表的对象归属、权限和cache_context，只把至多32个合法数据页PA传给内部适配器。512项RSI检查预算、固件调用前后真实状态/根核验及任务READY/RETURN/RETIRE语义保持。内部控制页仍不走普通数据页同步；不存在Proxy自报HPA或跳过必要cache操作的接口。可选内部批回调保留既有小型模型后端的逐页实现，不是共享数据回退，也没有新增ABI/能力位。

适配器先按PA排序去重，再锁定不同DATA页，映射到专用连续WB虚拟窗口；实际物理页不要求连续。设备方向对整个已映射范围执行clean+invalidate，CPU方向只invalidate，已有范围汇编以DSB SY结束；屏障完成前不移除映射、不释放锁。成功后反向解除所有临时映射，再释放锁；中途取锁/映射失败也清理已取得的前缀，PT核心隔离上下文、保留所有backing，不将部分维护解释为成功。别名去重仅在一个批次内合并物理维护，累计页次仍按已检查叶子数量计数，READY/RETURN进度保持一致。

专用窗口将OpenCCA每CPU虚拟slot从42增至75（32个cache槽及1个结束空槽），复用现有L3表的空闲描述符，不增加物理页表或扩大38MiB RMM预留。空槽确保范围结束地址不回绕至0；编译期断言和实际头文件提取测试检查这一边界。现有映射建立/逐页TLBI收尾仍保留，本轮主要减少缓存维护内部逐页等待DSB SY的次数；不能把理论32倍批次等同于32倍性能。

上游默认只允许同时锁定单个DATA。新增局部锁规则见`lib/granule/include/granule_types.h`及`docs/design/locking.rst`：仅已冻结授权BO、已持有xshm_policy_lock、无DATA锁入口，按严格递增PA取得至多32个不同DATA锁；期间不再取得外部/RTT/REC_AUX或策略锁，不修改页归属，不引入DATA引用。RMI归属变更同样先取得策略锁；地址序避免批处理之间的锁环，单DATA路径不会等待第二个DATA，适配器不等待其他锁类。RSI真实入口READY/RETURN分支受同一策略锁覆盖已由检查脚本核对。该规则不放宽其他路径的锁约束；源码模型不构成真实并发证明。

新增`check-gpu-private-cache.py`直接编译实际PT核心与提取的适配器：8类核心场景覆盖1/32/33/513页、别名、双Client、错误身份、过早RETURN、精确重试与READY/RETURN失败隔离；适配器2178组覆盖两方向、1–32页及每个取锁/映射失败位置、逆序/重复PA，另有4种无效输入。ASan/UBSan通过；旧核心负对照预期失败（忽略批回调而进入禁止的逐页替身）。最初两次夹具失败（513页未登记完便尝试映射、U宏模拟错误）及一次入口片段截取失败均保留，没有删去负例。

完整本地私有回归rc0（含98项提交、32项runner、固件/页表/生命周期模型），最终适配器/真实入口检查rc0，RMM ARM64构建rc0；固定补丁及whitespace检查通过。原型`firmware-private-cache-batch/`未部署；补齐锁约束后的最终配套为`private-cache-batch-candidate/`与`firmware-private-cache-batch-reviewed/`，RMM SHA `6d6704507bdfb0589f2eb2dadc7c11577988d45a102a2c1be1515c0e340591f8`，FIT SHA `6da0aaae7633035f858f0f36a2133baae5a43336dbd89ff5b3b419228fe8279b`。FIT两段/配置引用、含BSS/栈布局检查PASS，预留末址仍0x2800000。仅RMM变化，Host/Client/Proxy/initrd/runner与x逐项哈希相同。

独占入口SD2部署`private-heap-rmm-20261030-p`退出0，备份实际SD启动区、Host上线与RME capability=1、CPU/驱动/资源恢复；未写eMMC。y轮完整720p正在执行。冷启动先读取校验约1.6GiB固定输入，进程曾等待SD块I/O，随后正常启动Realm；这段准备时间不计入benchmark分差，也未因暂时无日志而重启。完整命令为：

```text
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-y -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-cache-batch-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

本轮构建/模型/原型失败/最终部署证据位于`build/rmm-client-bo-20261030/*cache-batch*`，实际部署见`build/{lab-runs,firmware-runs}/private-heap-rmm-20261030-p/`，工作负载见`build/lab-runs/private-heap-720-20261030-y/`。统一记录：RMM私有缓存32页窗口批处理｜x46分→y待测｜分差及百分比待测｜仅RMM缓存批次/虚拟slot及局部锁规则变化，其余冻结输入及完整720p/performance/单Client条件相同；重启后的输入校验不属benchmark｜上述命令/本地rc0、部署p rc0，y结果待回收｜待验证；执行位清零、goal active，不能据本地测试宣称性能或实体多Client隔离已通过。

y轮现已结束，完整33场景仍 **46分**，相对x为 **0分/0%**，入口rc1、1000分门槛FAIL。计算预热及validation26/1/6、额外失败0通过；BO/export/VM_BIND/submission错误0，GLMARK_CLEAN_RESULT=PASS。Host健康PASS、VM0/0、CPU/频率/pmthor和资源恢复，无实验进程/loop残留；11份证据SHA核验通过。DMA/固件平台后端的额外模型回归`dma-private-cache-batch.log`也rc0，保留原生SUSPEND、真实完成、缓存归还、不确定状态及批量任务/环绕等检查；这些模型不能替代实体多Client/攻击验证。

**实测不支持保留。** x17338任务→y17117任务，READY/RETURN合计操作每任务16.77297→17.50755ms，**+0.73458ms/+4.38%**；每页次每方向平均843.65→878.83ns，**+4.17%**。READY每任务7.77906→8.11516ms，RETURN8.99391→9.39239ms。逐场景帧时变化中位数 **+4.04%**；build(use-vbo=true)15.356→16.676ms（+8.60%）、bump(normals)18.024→19.533ms（+8.37%）。仅就当前实现/平台拒绝该组合，不能进一步断言排序、锁、slot检查或TLB压力中的某一项是已确认根因。

COMPLETE gap15.822→4.869s，x的shading/cel101.042ms异常本轮未在同场景复现；benchmark墙钟366.103→365.489s（约−0.17%）。这不证明异常等待已被修复，也不能掩盖单位任务缓存和普通场景的回退。y日志共有134窗口，其中首个属于validation文件（tasks256，第一条丢失），随后计数重置，benchmark本身有133条完整窗口tasks128至17024；通用解析器的`history_incomplete=true`描述合并日志的开头，不能误称benchmark早期采样缺失。最终17117任务有独立完整阶段计数。分析见`private-phases-y.json`、`private-cache-y.json`与`private-cache-batch-scene-comparison.json`。

已归档候选全部8个修改文件及3个新增文件至`build/rmm-client-bo-20261030/withdrawn-private-cache-batch/`；活动源码逐字节恢复`before-private-cache-batch/`的原内容，移除新测试/检查器及其调用，不留下未使用批回调、额外slot或DATA锁例外。源回退检查为`private-cache-batch-source-rollback.json`。回退后的完整私有/DMA模型及RMM构建再次rc0；注意copy2恢复旧mtime会令第一次增量构建跳过编译，该次日志另存`rmm-private-cache-batch-rollback-no-recompile.log`，显式更新时间后已真实重编译成功。重建rmm.img与冻结x镜像等长，仅构建时间字符串6字节不同，完整其他字节相同，比较证据`private-cache-batch-rollback-image-comparison.json`；该重建物未部署。

实际恢复经独占入口`private-heap-rmm-20261030-q`重新部署原冻结`firmware-private-suspend-barrier/`（RMM SHA `36e4723c0c15bfa9ab3a063cf4c27a0d3540ac301712f076807e318c237a1d5e`、FIT SHA `e7717c71e4794d5740f8184bc0536828b82496fe0367c72124559d33bd943900`），退出0，Host与RME能力及资源恢复正常。当前运行输入恢复为x的`private-log-quiet-candidate/`组合；没有追加GPU测试，不将原x成绩冒充回退后新测量。候选包/FIT/失败证据保留，不覆盖它们。

统一记录（最终）：32页RMM缓存窗口/局部锁批处理｜x46分→y46分｜0分/0%，单位任务缓存操作+4.38%、逐场景帧时变化中位数+4.04%｜仅RMM组合变化，原固定Host/Client/Proxy/initrd/runner及720p/performance/单Client设置；重启后的输入校验不计benchmark｜y/result.json完整命令/rc1、11份SHA/健康/恢复及上述本地日志；恢复q rc0｜**撤回**；当前x源码/冻结输入，整体性能、异常等待、多Client与隔离攻击验收仍未完成，执行位清零、goal active。后续优先评估有可信CPU/GPU所有权依据的驻留与细粒度缓存交接，不能跳过必要同步或仅凭Client自报dirty集合放宽安全边界。


## 2026-10-30 Client tiler 内存的可信 GPU 驻留（z轮候选）

上一轮32页缓存窗口批处理已完整撤回。本轮改为减少必要同步的页次：Client仍分配、初始化私有tiler context/chunk，随后通过新增操作52 `BO_SEAL` 交给RMM。RMM只接受实际Client自己的已完整登记、不可执行、未映射且无授权/缓存引用的BO；以512页为预算，把原RTT叶改为保留原PA/DATA归属的assigned-empty，完成全局TLBI后才clean/invalidate该页。初始化内容保留，Proxy得不到CPU别名或HPA。RMM记录永久驻留和隐藏前缀，只有全部成功后才允许GPU映射；这不同于Client自报dirty/GPU-only标志。

READY/RETURN仍逐叶核对真实私有页表、owner/service、对象生命周期与context缓存租约；仅对RMM已完成CPU隐藏的BO省去重复cache维护。普通数据BO继续原同步，驻留BO不在任务退休或设备复位时恢复CPU访问。动态OOM新chunk在发布GPU PTE前也先完成相同交接，事件/根/任务/实际ACK检查保留。成功SEAL重试只读元数据，不重新维护可能由GPU使用的数据。任何hide/flush失败都关闭BO并保留精确前缀，不自动降级共享或把部分成功当完成。

新增操作53 `BO_RELEASE`在真实映射/授权/设备引用释放后分批清零隐藏页，再恢复原CPU RTT；旧BO_DESTROY不能直接释放驻留对象。Client在第一次SEAL前记录必须走安全release路径，传输失败或坏回复也不能释放隐藏页；内核托管对象的诊断接口和mmap拒绝绕过。死亡Realm回收复用同一清零/恢复逻辑。CPU别名撤销由实际Realm RTT和现有RMI/xshm/IOMMU生命周期门禁共同保证；不据此宣称RK的模拟GPT/GPC已成为实体硬件隔离证明。

ABI仍为2、RPC仍为4；新增驻留能力bit29，报告能力1073741819，完整执行位4仍清零。新Client私有模式强制要求驻留能力，禁止与旧RMM混用。固定RMM预留末址仍0x2800000，未扩容。核心19个场景覆盖513页跨批、隐藏/同步/清零/恢复失败、错身份/旧handle、预存映射/授权、缺回调、普通与驻留混用、连续任务、动态扩展和死亡owner回收；实际RTT/policy模型补充内容保留及清零后恢复检查。完整本地私有回归（98提交、32 runner等）与DMA/固件平台后端通过；去掉驻留免重复同步分支的负对照按预期失败。模型没有验证真实并发或实体隔离。

RMM及两端ARM64 Image构建通过。首轮两端内核构建漏传固定firmware目录，失败rc2保留；补齐已校验SHA的`CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware`后均rc0，无编译警告。配套`build/rmm-client-bo-20261030/private-resident-candidate/`和`firmware-private-resident/`，RMM SHA `b831cd785d6a7a86629592db43e2789516cc550c3217384173c6ec6ae9ed06c7`，Client SHA `08dbafc5fbde2a0e46ff6e8a5e8584572ee3f48f74094670b14b935f58afccad`，Proxy SHA `f457b3e48c1551897ff177d08140fdfa9f0a7b80da31663058f473c7c0484d0e`。Host/initrd/runner与x相同；仅RMM与两端内核组合变化，不把后续性能差单独归给某个子改动。FIT/ELF和含BSS布局检查通过。

资源预检通过，SD2独占部署`private-heap-rmm-20261030-r`退出0，Host上线、RME capability=1、CPU/驱动和资源恢复。本轮z真实GLES计算与图形validation已过，完整benchmark进行中，最终分数/退出/健康待记录。统一记录：可信CPU隐藏的tiler驻留，避免重复同步｜x46分→z待测｜绝对/百分比变化待测｜上述RMM/两端内核组合变更，其余输入与完整720p/performance/单Client条件相同｜本地日志`unit-private-resident-{first,reviewed,mixed}.log`、`dma-private-resident.log`、`{rmm,client,proxy}-private-resident*.log`，部署/负载见各run-id目录｜待验证，goal active；性能1000门槛、多Client、攻击及真实动态OOM事件覆盖仍未验收。


补充Client坏回复/诊断保护回归：9组真实SEAL后的返回丢失、零/超界进度、额外字段、不一致SUCCESS/INCOMPLETE及2项托管接口拒绝，结合引用回收共使heap联合场景增至129，`unit-private-resident-client-faults-reviewed.log`退出0。首版和诊断版失败是旧夹具把`managed_handle()`固定为false，已删除该替身、改提取实际函数；两个失败日志均保留，生产代码及已冻结镜像不因此变化。19个RMM核心场景另确认混合普通数据页仍逐次同步，驻留页保持CPU不可见，动态扩展不重复同步；两者共存时完成页计数与退休门禁一致。


z轮完整33场景得 **58分**，对照x46分为 **+12分/+26.09%**；入口因1000门槛rc1。GLES计算PASS、validation26/1/6、BO/export/VM_BIND/submission错误0、GLMARK_CLEAN_RESULT=PASS，Host健康PASS、VM0/0及CPU/频率/pmthor恢复，无残留进程/loop；10份文件已回收并逐项SHA核验。失败诊断的Client kernel-log在15秒预算内未排空，随后pool-unbind回复错位，`failure_log_errors`与`transport_cleanup_errors`均保留。原始realm-1.log最终出现完整XSHM_KERNEL_LOG_END和pool-unbind的status0/result0/exit0，但不能用迟到回复覆盖runner异常或宣称该清理步骤已正常验收。

benchmark最终21657任务；同步页次每任务每方向9940.70→7306.23（−2634.47/−26.50%，约38.83→28.54MiB等价维护量，并非唯一页数）。READY/RETURN操作每任务16.77297→13.31589ms（−3.45708/−20.61%），分别7.77906→6.06067、8.99391→7.25521ms。调用次数每任务每方向43.8567→43.3396，仅−1.18%；空进度占比48.04%→61.74%，说明省掉缓存维护后仍有大量原有页表检查和每批固件检查，不能把减少的页次直接当作等比例整体加速。完整169条窗口自128起、无进度回退；Client kernel日志虽未单独保存，但串口原始日志保留完整阶段统计。分析`private-phases-z.json`、`private-cache-z.json`、`private-resident-comparison.json`。

逐场景帧时变化中位数−18.39%；**jellyfish由19.668→51.454ms（+161.61%）异常变慢**，其他32场景本轮改善。COMPLETE gap15.822→22.377s，benchmark观察墙钟366.103→376.549s（+2.85%）；不能把总墙钟解释为纯吞吐，也不能称长等待已解决。需要保留异常并进一步定位，不能把其改善/恶化归给驻留机制的某条指令。

已定位并只修正runner失败诊断的日志预算：15秒改为正常命令已用的120秒，未改GPU运行代码或工作负载。32项离线runner检查rc0。新冻结`private-resident-log-drain-candidate/`仅runner SHA变为`1d735b82b682f66953449d3f66ebc0076bbf55e14d1c49b4c678e394e86f0f79`；RMM/Client/Proxy/Host/initrd与z逐字节相同，无再次刷写。完整720p复测`private-heap-720-20261030-aa`已启动，目标是验证诊断排空及正常解绑，最终分数/退出/健康待记录。z所有失败保留，不以复跑抵消。统一记录（z）：可信tiler驻留｜x46→z58｜+12/+26.09%，单位任务缓存操作−20.61%，jellyfish异常保留｜仅RMM/两端内核组合变化，其余固定条件相同｜z/result.json完整命令、rc1、10份SHA与上述诊断｜保留为有收益候选，日志与退出复测待验证；性能/多Client/攻击验收仍未完成，执行位清零、goal active。


### aa复测最终结果与当前保留版本

`private-heap-720-20261030-aa`已结束，完整33场景 **55分**，对照x46为 **+9分/+19.57%**。入口退出1，唯一性能门槛错误为`private full-720p score below 1000`；不能记为整套PASS。GLES计算预热、GPU smoke及图形validation26/1/6通过，额外失败和BO/export/VM_BIND/submission错误均0，`GLMARK_CLEAN_RESULT=PASS`。两端kernel-log命令退出0，pool-unbind退出0/result0，没有`failure_log_errors`或`transport_cleanup_errors`。VM退出0/0，Host健康PASS、dmesg未环绕且无新增错误；CPU0–1、userspace/300MHz与实际频率及pmthor恢复，无本次进程或loop残留。11份证据已回收并逐项SHA核验，位置为`build/lab-runs/private-heap-720-20261030-aa/`，z的10份证据与诊断失败继续保留。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-aa -- \
  python3 build/rmm-client-bo-20261030/run-private-with-uart.py \
  --images build/rmm-client-bo-20261030/private-resident-log-drain-candidate \
  --private-gpu --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-720 --clients 1
```

| 指标 | 对照x | 驻留复测aa | 变化 |
| --- | ---: | ---: | ---: |
| 完整720p得分 | 46 | 55 | +9 / +19.57% |
| READY+RETURN缓存操作/任务 | 16.77297ms | 13.29768ms | −3.47529ms / −20.72% |
| 每方向同步页次/任务 | 9940.70 | 7308.54 | −26.48% |
| 每方向调用/任务 | 43.8567 | 43.7263 | −0.30% |
| COMPLETE累计gap | 15.822s | 38.493s | 尚未解决 |
| benchmark观察墙钟 | 366.103s | 384.151s | +4.93% |

READY与RETURN分别为6.02767、7.27001ms/任务。每方向页次约38.83→28.55MiB等价维护量，**不是唯一页面容量**。任务数17338→21041，不同场景任务构成会影响归一统计；减少缓存成本的结论不能推出所有场景、总墙钟或每批固定开销都改善。164个完整窗口从任务128覆盖至20992，最终任务21041，无历史缺口；分析文件为`private-phases-aa.json`、`private-cache-aa.json`与`private-resident-aa-comparison.json`。

逐场景帧时变化中位数−18.73%，但texture linear由15.955→33.811ms（+111.91%），loop fragment-loop=false由18.034→40.513ms（+124.65%）；首轮z的jellyfish异常也保留。aa三个较大128任务窗口的COMPLETE gap为15.5401s、10.5187s、6.5081s，这些间隔含睡眠/重调度，不能直接认定为GPU执行或IRQ延迟。

当前冻结包为`build/rmm-client-bo-20261030/private-resident-log-drain-candidate/`，配套已部署的`firmware-private-resident/`；RMM ELF SHA为`b831cd785d6a7a86629592db43e2789516cc550c3217384173c6ec6ae9ed06c7`。相对x是RMM与两端内核的组合优化，Host/initrd及完整720p/performance/单Client设置相同；相对z仅runner的失败后日志超时15→120秒，GPU镜像未变、无再次刷写。不能单独归因于某一条指令。性能复测和日志修正证据不替代多Client或恶意驱动/设备攻击验收。

统一记录（当前）：可信CPU隐藏tiler驻留与安全回收｜x46分→aa55分（首轮z58分）｜+9/+19.57%（首轮+12/+26.09%），单位任务缓存成本−20.72%，异常场景和长等待保留｜RMM/两端内核组合变化；aa仅额外更改失败后日志读取预算，其他固定条件如上｜上述命令、aa/result.json、rc1、11份SHA/健康/恢复证据；部署r rc0，本地检查命令/日志见前段与local-artifacts.json｜**保留有收益优化，整体未验收**。1000分门槛仍FAIL，广泛API/计算性能/多Client/实体攻击均未扩展，动态tiler OOM实体覆盖NOT_VERIFIED，完整执行位仍清零、goal active。本次收尾只整理文档与证据，未改运行代码，无新增性能测量。


## 2026-10-30 RMM 私有页表的稀疏缓存扫描候选（ab）

aa的READY/RETURN每任务每方向仍约43.73次调用，约61.92%的READY调用没有实际同步页次。不能据此跳过普通数据同步；本轮只减少空页表和空区段的扫描/RSI次数。在RMM私有元数据中，每张表增加16位摘要，每位对应32个PTE，448张表共896字节。摘要由同一策略锁内的真实映射/撤图更新，分配、销毁和可信设备撤销时重置；不接收Client或Proxy的摘要。扫描只跳过摘要证明为空的区段，所有有效叶仍核验实际PTE、owner/service、对象及缓存租约，驻留/普通数据规则不变。空表/空组各消耗一个预算单位，有效组每项消耗一个，每次仍最多512次检查/页维护。两种UNMAP删除最后叶时清除摘要位，删除邻居不隐藏剩余叶；动态扩容复用建图路径。

新增六个实际PT核心/合成AS和缓存回调用例，覆盖稀疏/32项边界/511末项、多表、513页预算、两种撤图/重映射、跨Client及表槽复用、坏PTE和同步失败；核对实际收到的全部PA序列及不确定状态引用保留。稀疏用例READY/RETURN各2次，旧核心在新增上限中预期失败；这是本地结构性证据，不是GPU提分证明。完整私有回归退出0（含19驻留、129堆、98提交与32 runner场景），日志`unit-private-sparse-scan-final.log`；首两版新用例分别误将稀疏占用组也视作零预算、以及假定513页BO一次销毁完成，夹具失败保留在`unit-private-sparse-scan{,-reviewed}.log`，生产逻辑未因此调整。

DMA/固件后端回归最终退出0，日志`dma-private-sparse-scan-abort-reviewed.log`，原有失败日志全部保留。修正旧夹具的两个“只要有数据就必须多次调用”断言，改为页数决定的调用下限且保留每次512页上限；CS故障在最后数据回调之后注入，保证单次RETURN也能验证后置硬件检查。显式中止场景81预先设置实际数据期望，不再假定第一次RETURN只遍历非叶子；中止可以安全归还缓存但仍不能变为成功COMPLETE，旧token/组/backing拒绝检查保留。首次、第二次、第三次后端夹具失败分别保存在`dma-private-sparse-scan.log`、`dma-private-sparse-scan-reviewed.log`、`dma-private-sparse-scan-final.log`。

RMM ARM64构建退出0，日志`rmm-private-sparse-scan.log`，仅保留原有RWX LOAD/build-id链接警告；固定补丁清单、FIT与含BSS/栈布局检查通过，预留末址0x2800000不变。冻结包`private-sparse-scan-candidate/`配`firmware-private-sparse-scan/`，RMM ELF SHA `2c874ac6c4954bf0ba43ab5190e1fb6ef973deb2cf6f91003aef45f48255cd78`；只替换RMM ELF/img，Host/两端Image/initrd/runner与aa逐项哈希相同，ABI2/RPC4、能力1073741819、完整执行位清零。构建固件基于原固定U-Boot源码归档/配置/BL31/DDR及固定SWIG，不跟随上游latest。

统一记录（候选）：RMM可信稀疏摘要，降低空项RSI开销｜aa55分→ab待测｜分差及百分比待测，本地调用数不作实体提分归因｜仅RMM变化，其余冻结输入及完整720p/performance/单Client条件相同｜部署`private-heap-rmm-20261030-s`，后续负载`private-heap-720-20261030-ab`；本地命令为`bash scripts/check/check-rmm-gpu-private.sh`、`bash scripts/check/check-dma-guard.sh`、`cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`，日志如上｜待验证；goal active，1000分性能门槛、多Client/实体攻击及动态OOM覆盖仍未验收。


### ab实体结果：保留稀疏扫描优化，1000分门槛仍FAIL

SD2部署`private-heap-rmm-20261030-s`退出0，Host上线、RME capability=1及资源恢复。完整720p负载`private-heap-720-20261030-ab`最终 **62分**，对照aa55分为 **+7分/+12.73%**；相对早期x46累计+16/+34.78%。入口rc1，唯一性能门槛错误`private full-720p score below 1000`，不能写为整套性能PASS。私有GLES计算、GPU smoke、完整33场景和validation26/1/6通过，额外失败和BO/export/VM_BIND/submission错误0，`GLMARK_CLEAN_RESULT=PASS`。两端kernel-log退出0，pool-unbind的status0/result0/退出0，未发生诊断超时或回复错位。VM0/0、Host健康PASS、dmesg未环绕且无新增错误；CPU0–1、userspace/选择与实际300MHz及pmthor恢复，无本次进程/loop残留。11份文件已回收并逐项SHA核验。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ab -- \
  python3 build/rmm-client-bo-20261030/run-private-with-uart.py \
  --images build/rmm-client-bo-20261030/private-sparse-scan-candidate \
  --private-gpu --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-720 --clients 1
```

| 指标 | 驻留aa | 稀疏扫描ab | 变化 |
| --- | ---: | ---: | ---: |
| 完整720p得分 | 55 | 62 | +7 / +12.73% |
| READY/RETURN每任务每方向调用 | 43.7263 | 20.1819 | −53.85% |
| READY无同步进度调用占比 | 61.92% | 19.82% | −42.10个百分点 |
| READY+RETURN缓存操作/任务 | 13.29768ms | 11.98653ms | −1.31115ms / −9.86% |
| 每方向同步页次/任务 | 7308.54 | 7275.48 | −0.45% |
| COMPLETE累计gap | 38.493s | 27.365s | −28.91%，仍有异常 |
| benchmark观察墙钟 | 384.151s | 371.726s | −3.23% |

实际同步页次基本相当，符合“主要减少空项扫描和调用，并未去掉普通数据维护”的设计。READY与RETURN分别6.02767→5.73808、7.27001→6.24845ms/任务；任务数21041→23035、构成不同，归一统计的少量页次差不能当作跳过了某类页面，也不等于唯一内存容量。179个完整窗口从128任务覆盖至22912，最终23035任务，无历史缺口；分析见`private-phases-ab.json`、`private-cache-ab.json`及`private-sparse-scan-comparison.json`。

逐场景帧时变化中位数−4.91%，本轮31个场景改善，但**ideas 14.501→24.677ms（+70.17%）**、**loop fragment-uniform=false 14.253→115.255ms（+708.64%）**异常保留。COMPLETE间隔包含睡眠和重调度，累计下降不证明长等待已修复，也不能把这些异常归因于某个GPU中断。性能只按本轮同条件观测描述，不宣称重复测量的稳定区间。

负载结束后另经独占只读输入核验`private-sparse-scan-sd-20261030-a`读取实际`/dev/mmcblk1` SD2的idbloader与FIT对应字节，SHA均与冻结固件一致，退出0；记录`private-sparse-scan-sd-readback.json`。未在benchmark中读取SD进行额外比对；启动前冷输入哈希不计benchmark墙钟。本轮仅RMM运行代码改变，Host/Client/Proxy/initrd/runner及完整720p/performance/单Client条件与aa逐项哈希相同。

统一记录（最终）：可信稀疏摘要降低空项扫描与RSI次数｜aa55分→ab62分｜+7/+12.73%，单位任务每方向调用−53.85%、缓存阶段−9.86%，上述两个异常场景保留｜仅RMM变化，其他冻结输入/条件相同｜上述命令、ab/result.json、rc1、realm-evidence及11份SHA、Host健康/恢复；部署s rc0，SD字节核验a rc0；本地命令/日志如前段｜**保留有收益优化，整体未验收**。性能1000门槛、间歇长等待、多Client/实体攻击和动态tiler OOM实体覆盖仍未完成，完整执行位清零、goal active。本次文档与证据收尾未改运行代码，无新增性能测量。


### RMM强制非缓存普通BO：将重复缓存交接前移到创建和回收

上一版ab的READY+RETURN平均为11.98653ms/任务，每个方向约7275.48同步页次。tiler已CPU隐藏驻留，但普通Client BO仍需逐任务维护整个上下文。本轮由RMM转换普通BO的**Client CPU Stage-2 RTT属性**；这不是给GPU重新打开硬件Stage-2，GPU仍使用RMM构造的实际HPA页表。

- 新操作54 `BO_UNCACHED`、bit30能力。只接受实际原Client及完整登记、未映射、无grant/缓存租约的普通BO。每调用最多512页：assigned-RAM→assigned-empty，全局TLBI完成后通过可信临时WB映射flush到PoC，解除该临时映射，再恢复为MemAttr=0101的Normal NC。初始化内容保留；Client的用户态和内核线性别名均受实际Stage-2约束，不依赖Guest自报的S1属性。
- RMM以私有`uncached`状态与转换进度为依据，只有全对象转换成功才能映射/授权并省去READY/RETURN数据缓存指令。逐有效PTE、owner/service、对象生命周期、context缓存租约检查仍执行；涉及NC叶子的每个批次使用可信`dsb(sy)`屏障。普通WB BO继续原维护，tiler继续原CPU隐藏驻留，protected控制页继续原规则。GPU自身WB缓存及真实SUSPEND/ACK、FLUSH_MEM/AS disable、RETURN/RETIRE成功条件未放松。
- Client在前端BO_CREATE的私有分配之后、向Proxy导入/向Mesa发布之前转换；只针对普通前端BO，不在底层alloc中全局转换tiler。Client在首次RSI前登记释放意图；错误或回复不确定时仍持有页面。RMM转换失败关闭对象并记录精确NC前缀及一个可能CPU隐藏的页面；旧BO_DESTROY拒绝绕过。BO_RELEASE在映射/任务持有结束后逐页隐藏、清零、恢复默认WB，再允许Client释放；清零/恢复失败保留引用和隐藏状态。可信reset本身不把NC数据页提前退还。

RMM复用`hidden`的低31位保存NC前缀，高位表示该前缀之后恰有一页处于隐藏转换中；resident/control语义独立且互斥。一个bool利用原结构填充，不增加每BO结构大小，不扩大末址0x2800000的既有预留。MemAttr=0101同时适用于FWB/非FWB；实现清除完整四位，避免从OpenCCA默认1111转换时残留高位。

这是一项内存策略取舍：省去全上下文反复维护，代价是BO首次转换/最终回收及CPU非缓存读写。不能由glmark结果推断CPU读密集型ML负载也更快；后续若比较WB暂存批量复制或选择性策略，仍须由RMM证明真实属性和完整生命周期，不能只设Guest标志就跳过同步。

本地验证：24类实际PT核心模型（含513页预算、部分隐藏/flush/NC恢复失败、部分转换后回收失败、释放失败重试、错误Client/Proxy、缺失回调、grant/映射期间拒绝、执行期间完成重放、reset/死亡owner、坏PTE、屏障失败、NC动态扩展、NC/WB混合及unmap/remap保持属性）；真实RTT/policy源代码检查两种默认WB编码、0101结果、DATA/PA/refcount、TLBI顺序与RIPAS/fold/DATA销毁拒绝。Client实际函数与RMM核心联合检查151项，覆盖RSI回复丢失/坏进度/脏附加字段及释放意图；完整私有及固件后端模型、ARM64 RMM/两端Image、固定补丁、FIT/ELF与含BSS布局均通过。以上CPU缓存/属性回调仍是模型，实体结果另列。

保留失败：`unit-private-uncached.log`、`unit-private-uncached-reviewed.log`，均为新夹具错误：动态扩展前未映射BO本可合法释放、以及使用3页低于既有32页扩展下限；修正测试条件，未放宽生产准入/释放规则。成功中间记录`unit-private-uncached-extension-reviewed.log`与最终`unit-private-uncached-final.log`均保留；后者包含NC unmap/remap覆盖。DMA日志`dma-private-uncached.log`，构建`rmm-private-uncached.log`、`client-private-uncached.log`、`proxy-private-uncached.log`；RMM原有RWX LOAD/build-id两条链接提示保留。


### ac实体结果：178分实验候选，缓存维护显著减少，长等待退化仍待解决

SD2部署`private-heap-rmm-20261030-t`退出0，Host正常上线、RME capability=1。新包`private-uncached-candidate/`只与`firmware-private-uncached/`配套；RMM ELF SHA `e6893196527dfb8b1f5b6d5e617b910c169742fce5351f02ed567b6249c9b549`，Client `990abfb34051b954848c6bcc4a310ee5147daee1fcd452ec54905c356d844b79`，Proxy `e94532a13a5a3c8cd2c31159561d85cba08cfeb271dd2e457e74a7c69b537358`。相对ab改变RMM和两端Image；Host/initrd/runner逐项SHA相同，完整720p、单Client/performance、频率和CPU布局条件相同，只将性能差归于组合变化。ABI2/RPC4、总能力2147483643，完整执行位仍清零。

完整负载`private-heap-720-20261030-ac`得分 **178**，对ab62分 **+116分/+187.10%**。完整33场景、私有GLES计算、GPU smoke、validation26/1/6通过，glmark错误列表为空，`GLMARK_CLEAN_RESULT=PASS`；两端kernel-log退出0、两次pool-unbind均status0/退出0、VM退出[0,0]、Host健康PASS、CPU0–1/300MHz/pmthor及资源恢复、无本次进程/loop。11份证据已回收并逐项SHA核验。入口仍rc1，错误为`private full-720p score below 1000`，不是完整性能验收PASS。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ac -- \
  python3 build/rmm-client-bo-20261030/run-private-with-uart.py \
  --images build/rmm-client-bo-20261030/private-uncached-candidate \
  --private-gpu --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-720 --clients 1
```

| 指标 | 稀疏扫描ab | 强制NC的ac | 变化 |
| --- | ---: | ---: | ---: |
| 完整720p得分 | 62 | 178 | +116 / +187.10% |
| READY+RETURN操作/任务 | 11.98653ms | 2.43074ms | −79.72% |
| READY操作/任务 | 5.73808ms | 0.91221ms | −84.10% |
| RETURN操作/任务 | 6.24845ms | 1.51853ms | −75.70% |
| 每任务每方向调用 | 20.18185 | 20.43053 | +1.23%，尚未减少扫描次数 |
| 每任务每方向普通数据同步页次 | 7275.48 | 0 | 不含首次转换、最终回收及PT/控制页维护 |
| COMPLETE累计worker gap | 27.365s | 135.103s | +107.738s，长等待加重 |
| benchmark观察墙钟 | 371.726s | 436.560s | +64.834s / +17.44% |

30/33场景帧时改善，变化中位数 **−70.34%**；以下退化必须保留：

| 场景 | ab帧时 | ac帧时 | 变化 |
| --- | ---: | ---: | ---: |
| pulsar light=false | 11.871ms | 13.673ms | +15.18% |
| buffer interleave=true / map | 22.156ms | 13473.613ms | +60712.48% |
| function medium | 11.830ms | 51.484ms | +335.20% |

因此当前处置为**保留实验候选用于后续定位，不视为全部场景改善或整体性能验收通过**。135.103s是COMPLETE阶段工作项之间的累计间隔，包含睡眠/重调度；不能直接认定为GPU执行或中断时长，不能仅凭同步减少把异常归因于CPU NC读写。需要继续区分完成观察、调度唤醒与CPU数据访问的影响。尚未对这一候选重复测量，不能宣称稳定收益区间。

任务数23035→71512，任务构成不同，归一统计不等于相同任务的微基准。ac最终累计phase计数仍覆盖71512个退休任务，但263个保留窗口仅从37888覆盖至71424；**Guest早期窗口历史缺失**，不能用于前半程逐事件归因或证明早期内核无异常。`PRIVATE_CACHE_REGRESSIONS`未报告进度倒退。NC使所有READY调用的同步页次为0，它们仍在核验有效叶子及执行屏障，不能把原`empty_calls`字段解释成全部无用调用。统计及范围见`private-cache-ac.json`、`private-phases-ac.json`、`private-uncached-comparison.json`。

负载结束后，经独占只读核验`private-uncached-sd-20261030-a`读取实际SD2上对应idbloader/FIT字节，SHA与冻结固件一致，退出0，结果`private-uncached-sd-readback.json`。核验不与benchmark并行。

统一记录：RMM强制NC，减少普通BO逐任务缓存维护｜ab62分→ac178分｜+116/+187.10%，READY+RETURN每任务−79.72%，总墙钟反增17.44%及三个退化场景如上｜RMM/两端Image组合变化，Host/initrd/runner和测试配置相同｜上述命令、ac/result.json、rc1、11份SHA、Host健康/退出/资源恢复；部署t rc0，SD字节核验a rc0；本地命令见候选验证JSON与上述日志｜**实验保留/待验证，goal active**。1000分门槛、多Client/实体CPU-DMA攻击与别名隔离、动态tiler OOM实体覆盖尚未验收；长等待、Guest日志历史缺口及CPU读密集负载的NC代价仍需处理。历史共享1405不构成本路径成绩。

## 完成等待分段诊断：ad178分，定位短睡眠超长等待

改动目的｜将原COMPLETE gap分成短睡眠、睡眠后抢锁、零延迟队列、延迟队列及worker入口抢锁，保留原gap作对照；窗口128→1024，减少日志覆盖。对照ac178→ad178｜0分/0%。两次单Client、完整720p、performance、相同RMM/Host/Proxy/initrd/runner；只有Client计时与日志频率变化。改进的是定位能力，不据单轮墙钟差宣称提分。

`private-heap-720-20261030-ad`通过`lab-run.py`执行同一`run-private-with-uart.py --images build/rmm-client-bo-20261030/private-completion-profile-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，退出1，唯一入口失败为1000分门槛。计算/33场景/validation26-1-6/clean通过，两端kernel-log及pool-unbind rc0、状态0，VM0/0、Host健康PASS，CPU0-1/GPU300MHz/pmthor及资源恢复；11份原始证据回收SHA核验。日志在`build/lab-runs/private-heap-720-20261030-ad/`；解析与对照为`private-cache-ad.json`、`private-phases-ad.json`、`private-completion-comparison-ac-ad.json`。

| 指标 | ac | ad | 解释 |
| --- | ---: | ---: | --- |
| 完整720p分数 | 178 | 178 | 0/0%，未验收 |
| 已退休任务 | 71512 | 68483 | 工作量不同 |
| READY+RETURN操作/任务 | 2.43074ms | 2.47384ms | +1.77% |
| COMPLETE累计gap | 135.103s | 104.284s | −22.81%，仍有长等待 |
| benchmark观察墙钟 | 436.560s | 405.139s | −7.20%，单轮差，不归因某条优化 |
| 保留窗口 | 263，首37888任务 | 66，首1024任务 | ad历史完整，末67584，最终68483 |

ad的短睡眠109542次，累计103.739646s，占COMPLETE gap的99.4782%；最长一次27.060706s，有16次≥10ms。睡眠后抢锁总14.909ms，最长62.416us；零延迟queue→entry累计268.304ms，最长1.473ms，无≥10ms；延迟队列29次共199.230ms，最长7.891ms；入口抢锁共25.006ms，最长163.042us。五项合计104.247095s，与旧gap差36.702ms，为计时边界/额外记账等未分类开销。`kind=0/1/2/3/4`依次对应上述五项，延迟队列包含请求的timer等待。诊断无权推进任务、发布fence或改变期限。

最重1024任务窗口334.169459–365.747733s中，gap27.373s、短睡眠27.368s。该数据将异常缩小到释放锁后的`usleep_range(50,100)`区间；其中仍可能包含Guest唤醒、线程/Host调度及vCPU暂停，不能据此证明具体中断或定时器故障。buffer interleaved/map从13473.613→18.905ms，但function low从3.468→76.765ms、conditionals fragment5从8.575→66.554ms等退化，异常会移动。

本地99项实际提交worker测试、完整私有模型回归、ARM64 Client构建/Proxy增量检查、补丁清单和解析器兼容/丢窗检查退出0。新增测试注入独立20ms睡眠、30ms队列及40ms延迟队列，确认计时互不混淆，deadline/fence/不重放START不受影响；这些替身不证明实体并发隔离。保留`before-private-active-pause/`中的诊断源码和独立冻结包。初版冻结器错误要求Proxy增量日志出现Image字样，断言失败保留于候选验证记录；仅修正验收条件，Proxy镜像SHA未变。

处置：保留诊断基线；后续主动观察间隔独立冻结与实测，尚不能视为修复或完整goal验收。原NC固件与此前SD字节核验不变，本轮未刷写。

## 主动间隔ae实验：打印215分无效，正确性失败后撤回

改动目的｜用最多8次、每次按单调时钟约50us的`cpu_relax()`主动间隔，替代原50–100us短睡眠；之后仍回普通延迟轮询。对照ad有效178分→ae打印215分｜表面+37/+20.79%，**因正确性失败不作为有效提分，最近有效成绩仍178**。只改Client镜像；RMM/Host/Proxy/initrd/runner、原始deadline与真实COMPLETE/堆事件/RETURN/RETIRE判据相同。不使用可能进入WFE/WFxT的arm64 udelay，不持有file/mapping锁，vCPU被Host暂停仍可能超过请求时长。

`private-heap-720-20261030-ae`使用相同`lab-run.py`/完整720p命令，只将`--images`改为`build/rmm-client-bo-20261030/private-active-pause-candidate`，退出1。计算与内层图形marker为PASS，输出33场景、validation26/1/6及215分，但validation refract输出`MESA: error: DRM_IOCTL_PANTHOR_VM_BIND failed (err=16)`；冻结runner的严格解析拒绝该错误，`concurrent_glmark`不接受score。不能用内层`GLMARK_CLEAN_RESULT=PASS`覆盖validation错误，也不能将本轮唯一失败写成1000门槛。

诊断任务68483→79010，COMPLETE累计gap104.283797→11.974042s（−88.52%），短等待累计103.739646→10.117934s，最长27.060706s→10.952666ms；仍有2次主动间隔≥10ms。COMPLETE调用178054→276287、操作24.619→34.310s，READY+RETURN/任务约2.47384→2.47267ms；任务数量和调用量不同，主动间隔增加CPU工作，不能只看gap推断整体收益。ae窗口77条、首1024、末78848、最终79010，历史完整。严格解析在写benchmark overlap前停止，未取得同口径墙钟统计，不从场景帧时拼装该值。

两端kernel-log和pool-unbind rc0/状态0、VM0/0、Host健康PASS、CPU0-1/GPU300MHz/pmthor与资源恢复、11份证据回收SHA通过。这些清理结果不使工作负载成为正确性PASS。原日志、`private-cache-ae.json`、`private-phases-ae.json`、`private-active-pause-rejected-output.json`及`private-active-pause-hardware-validation.json`均保留。

本地99项实际worker测试和完整私有模型、ARM64构建已通过，另测无锁约50us间隔、8次后回普通tick、关闭/超时、不重放START和独立计时；模型未预测此次实体绑定错误。源码检查显示Client bind入口在关闭、无worker或128个在途batch时可返回EBUSY，授权/RPC/实际PTE检查也可能返回错误；现有日志不能确定本次来源，不能直接加大容量或盲目重试映射。

处置：撤回主动间隔实现并恢复ad诊断源码；`withdrawn-private-active-pause/`保存撤回前源码，原候选镜像不覆盖。板端运行输入通过独占恢复入口换回冻结ad Client镜像，未修改Host/固件；恢复后本地模型/重编译通过，不追加GPU工作负载，不把ad178冒充回退后的新测量。多Client、攻击和1000分验收仍未完成，完整执行位清零。后续应先加入有界错误来源诊断，定位合法VM_BIND的EBUSY。

回退构建补充：首次`client-private-completion-restored.log`为增量无动作，不能证明已重编译撤回对象。恢复复制保留了旧mtime，已显式刷新该源文件时间并实际重编译Client，后续`client-private-completion-restored-rebuilt.log`包含panthor_client_drv.o的CC及Image生成。板端恢复始终使用原冻结ad镜像及其SHA，不使用该本地重编译镜像；无新增GPU测量。

## 绑定失败来源诊断与主动间隔af：216分，既有EBUSY仍未解决

改动目的｜使同一EBUSY可区分为Client admission/关闭/无worker、依赖、映射锁、RMM授权、RPC传输、Proxy绑定、回复字段或实际PTE核验失败；只在错误后通过rate-limited日志输出逻辑session/VM、stage、ret、在途计数和flags，不输出HPA或页面内容，不允许不确定映射重试。明确实验候选复用ae的有界主动间隔，cap128/期限/授权取消/根与PTE/实际完成条件均不变。

对照ad178→af216｜+38/+21.35%。都是单Client、完整720p、相同performance条件与NC RMM/Host/Proxy/initrd/runner；只Client镜像变化，主动间隔与错误诊断一起测量，不将差值分配给单个修改。ae的215分无效，不作为有效性能对照，也不因af通过而改写ae失败。逐场景帧时变化中位数−1.30%，refract从81.326→90.933ms（+11.81%）退化保留；单轮数据不构成稳定收益区间。

`private-heap-720-20261030-af`命令为`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-af -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-bind-diagnostics-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，退出1，唯一入口失败为1000门槛。计算预热、33场景/validation26/1/6/clean和严格解析通过，Mali-G610/Panfrost renderer；两端kernel-log及pool-unbind rc0/状态0，VM0/0，Host健康PASS，CPU0-1/GPU300MHz/pmthor和资源恢复。11份原始证据SHA核验，目录`build/lab-runs/private-heap-720-20261030-af/`；候选Client SHA `e32bf20ca55db40b4797ff7337b4656fe7f574cb71dd543f7648432498f4ce7e`。

| 指标 | ad诊断178 | af主动间隔+错误诊断216 | 边界 |
| --- | ---: | ---: | --- |
| 已退休任务 | 68483 | 79445 | +16.01%，工作量不同 |
| COMPLETE累计gap | 104.283797s | 12.047430s | −88.45%，不是纯GPU时间 |
| 短等待累计 | 103.739646s | 10.187560s | af主动间隔，198013次 |
| 最长短等待 | 27.060706s | 12.891083ms | af仍有2次≥10ms，不能保证50us唤醒 |
| COMPLETE操作 | 24.619288s | 34.513606s | +40.19%，轮询次数增加 |
| COMPLETE调用 | 178054 | 277700 | 与工作量/重查频率共同变化 |
| READY+RETURN/任务 | 2.47384ms | 2.44259ms | −1.26%，仍为主要成本 |
| benchmark观察墙钟 | 405.139143s | 359.752841s | −11.20%，不能全部归因于单条代码 |

af零延迟queue→entry累计311.156ms、最长4.385ms；延迟队列242次共1.460808s、最长7.9275ms；睡眠后/主动间隔后抢锁累计0.710ms、worker入口抢锁46.201ms。77条1024任务窗口从1024至78848，最终79445，历史完整；不同于ac早期窗口缺失。分析文件`private-cache-af.json`、`private-phases-af.json`、`private-completion-comparison-ad-af.json`及`private-bind-diagnostics-af-hardware.json`。

本地完整私有模型/ASan/UBSan回归通过，实际绑定函数测试增至41类（新增9类同errno来源），实际提交worker99类，ARM64 Client Image和固定补丁清单退出0。新增模型确认授权/传输/Proxy/PTE/映射锁/依赖/admission/关闭/无worker的失败来源和原返回值一致；授权已建立时仍执行原取消，失败不重放RPC，也不发布成功fence。本地替身不证明Linux并发或实体隔离。

本轮日志没有PRIVATE_BIND_ERROR、validation/benchmark绑定错误，但**不能据单轮未复现宣布ae EBUSY已定位或修复**。错误诊断仅保证下一次实际失败能缩小来源；现有限流/授权行为未改。保留为实验候选，先继续完整720p性能与已知错误定位；1000门槛未达到，API/ML/多Client/实体攻击未追加，完整执行位仍清零，无新固件刷写，goal active。


## RMM元数据扫描和物理维护双预算（ag）

af中普通数据BO已由RMM转换CPU Stage-2 Normal NC，tiler继续CPU隐藏驻留，因此逐任务数据缓存维护已接近零，但READY/RETURN仍按每512项可信页表检查退出RMM。每次续处理都重复认证、配置/根/静止状态检查和跨层切换。元数据检查与实际物理页维护的代价不同，共用一个预算放大了前者的调用成本。

本轮只修改`opencca_gpu_private.c::task_cache()`：本上下文表项/区段检查最多4096项，实际物理页维护仍最多512页，任一预算耗尽就保留游标和租约并返回INCOMPLETE。继续逐一检查实际PTE、对象service/owner、关闭状态、context租约及resident/NC完整转换；NC仍执行可信屏障，RETURN仍核对维护页数，失败隔离并保留引用。跳过其他上下文时仍检查固定448项表池的owner，未把4096解释成全部内存读取次数。无新共享缓存、Client提示或硬件状态复用，无新增静态内存，未扩大RMM末址0x2800000；其他BO转换/登记/映射/释放批量上限仍为512。

11组新增测试执行实际PT核心，覆盖8193个NC/驻留页、NC与513个WB页混合、后续批PTE损坏/owner错误/未完成转换/屏障失败/真实维护失败、RETURN损坏PTE、重复任务退休租约及8193个普通WB页。纯NC/驻留每方向3次、混合4次、纯WB17次；每次物理维护均≤512。旧核心在新进度检查中预期失败；这是模型检查，不是物理机密性证明。前三份中间日志保留测试夹具对表池游标、混合预算调用数及513页分批销毁的错误预期，修正夹具后完整回归通过，没有放宽生产拒绝条件。

改动目的｜减少不必要的RMM续调用｜对照af216 → 本版ag270｜+54/+25.00%｜只改RMM运行代码、重组固件；两端Image/Host/initrd/runner/私有内存配置/33场景/null-noop/finish及GPU请求600实际594MHz相同，CPU未锁恒频｜下列run/命令/退出码和日志｜保留作实验候选，整体验收待完成。

| 指标 | af | ag |
| --- | ---: | ---: |
| 完整720p分数 | 216 | 270 |
| 成功退休任务数 | 79445 | 99235 |
| READY调用/任务 | 20.364151 | 3.147891 |
| RETURN调用/任务 | 20.364151 | 3.147901 |
| READY+RETURN ms/任务 | 2.442587 | 1.705022 |
| COMPLETE操作累计秒 | 34.513606 | 43.084019 |
| COMPLETE间隔累计秒 | 12.047430 | 14.766531 |
| benchmark墙钟秒 | 359.752841 | 357.262780 |

逐场景帧时变化中位数-19.88%；完整场景差异见`private-completion-comparison-af-ag.json`，其中退化项保留。任务数与任务组合不同，累计秒数不能直接当单位任务收益；单轮分数不证明长期稳定性，1000门槛及安全验收单列。

- 本地：`bash scripts/check/check-rmm-gpu-private.sh`退出0（`unit-private-cache-budget-complete.log`，含绑定41/提交99）；`bash scripts/check/check-dma-guard.sh`退出0（`dma-private-cache-budget.log`）；`cmake --build build/rmm-client-bo-20261030/rmm-build-arm64 -j8`退出0（`rmm-private-cache-budget.log`）；固定补丁检查退出0（`patch-private-cache-budget.log`）；FIT/布局PASS。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-u --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-cache-budget --run-id private-heap-rmm-20261030-u`退出0，实际启动区备份、UART、Realm能力1/CPU0–1恢复；独占字节核验`private-cache-budget-readback-20261030-a`退出0。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ag -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-cache-budget-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，退出1。计算、33场景、validation26/1/6与严格解析通过；两端kernel-log和pool-unbind各2项rc0，VM0/0，Host健康PASS、CPU0–1/GPU300MHz/pmthor及资源恢复，11份证据SHA通过。当前性能门槛FAIL。
- 原始证据：`build/lab-runs/private-heap-720-20261030-ag/`；分析：`private-cache-budget-ag-hardware.json`、`private-cache-ag.json`、`private-phases-ag.json`、`private-completion-comparison-af-ag.json`；固定镜像/源码见新候选`hashes.json`与`private-cache-budget-source-hashes.json`。

ag没有绑定错误，不能由一次未复现关闭ae的EBUSY。恶意Proxy CPU/DMA旁路、双/多Client、广泛API、真实动态OOM与并发销毁仍未执行；完整执行能力位继续清零、goal未完成。历史共享1405不可继承为私有路径成绩。


## RMM Debug O2 构建对照（ah）

ag的READY/RETURN虽然每任务仅约3次调用，仍需逐页读取实际PTE和对象元数据；原固件为Debug `-Og`。本轮不改运行源码，建立独立`rmm-build-debug-o2/`，仅把全部22个C目标的优化改为`-O2`，保留`CMAKE_BUILD_TYPE=Debug`、`DEBUG`、断言、调试信息和帧指针。全部23个目标参数文件经构建路径归一化后逐项比较，除C_FLAGS的优化和空格外，定义/头文件路径/ASM参数均相同；原`rmm-build-arm64/`不变。实际ELF保留断言符号。固定RMM末址仍为0x2800000，不增加预留。

改动目的｜减少可信逐页检查的编译执行开销｜ag270 → ah339｜+69/+25.56%｜仅RMM C编译优化变化；运行源码、Client/Proxy/Host/initrd/runner、私有内存配置、完整33场景/null-noop/finish及GPU请求600实际594MHz相同，CPU未锁恒频｜下列run/命令/退出码与日志｜保留为实验候选，1000门槛FAIL、隔离验收待完成。

| 指标 | ag / Debug Og | ah / Debug O2 |
| --- | ---: | ---: |
| 完整720p分数 | 270 | 339 |
| 成功退休任务数 | 99235 | 125451 |
| READY调用/任务 | 3.147891 | 3.161553 |
| RETURN调用/任务 | 3.147901 | 3.161553 |
| READY+RETURN ms/任务 | 1.705022 | 1.091899 |
| COMPLETE操作累计秒 | 43.084019 | 54.013327 |
| COMPLETE间隔累计秒 | 14.766531 | 19.664369 |
| benchmark墙钟秒 | 357.262780 | 356.749163 |

逐场景帧时变化中位数-20.61%；全部差异及退化见`private-completion-comparison-ag-ah.json`。总任务数和任务组合有变化，累计COMPLETE秒数不能直接解释为单位任务成本。这是单轮构建配置对照，不作为新算法创新或稳定提分证明；保留原Og组合与全部失败证据。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-debug-o2 bash scripts/check/check-rmm-gpu-private.sh`退出0（`unit-private-debug-o2.log`，绑定41/提交99/预算11组）；同一HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0（`dma-private-debug-o2.log`）。模型保留原ASan/UBSan与断言，不代替物理隔离证明。
- 构建：`build-private-debug-o2.py`、`build-private-debug-o2-firmware.py`、`freeze-private-debug-o2.py`各成功执行一次；详细命令/参数见`private-debug-o2-build-validation.json`、`private-debug-o2-all-flags.json`，ARM64/FIT/含BSS布局及补丁清单PASS。首次配置漏传显式交叉编译器、误选Host gcc的失败目录/日志保留为`rmm-build-debug-o2-configure-failed/`、`configure-private-debug-o2.log-configure-failed`、`private-debug-o2-build-commands.json-configure-failed`；随后明确指定C和ASM交叉编译器构建成功。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-v --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-debug-o2 --run-id private-heap-rmm-20261030-v`退出0，Realm能力1、Host恢复；`python3 scripts/maintenance/lab-run.py --run-id private-debug-o2-readback-20261030-a -- python3 build/rmm-client-bo-20261030/verify-private-debug-o2-sd.py`退出0，实际SD两段字节SHA匹配。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ah -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-debug-o2-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。33场景、计算、validation26/1/6及严格解析通过；两端kernel-log和pool-unbind各2项rc0，VM0/0、Host健康PASS、CPU0–1/GPU300MHz/pmthor与资源恢复，11份证据SHA通过。性能门槛FAIL。
- 证据：`build/lab-runs/private-heap-720-20261030-ah/`；`private-debug-o2-ah-hardware.json`、`private-cache-ah.json`、`private-phases-ah.json`、`private-completion-comparison-ag-ah.json`；冻结输入及源码SHA在`private-debug-o2-candidate/hashes.json`和`private-debug-o2-source-hashes.json`。

本轮无绑定错误，ae的validation EBUSY仍未定位或关闭；不继承历史共享1405或旧多Client PASS。API/ML/多Client、恶意Proxy CPU/DMA旁路、真实动态OOM、并发销毁及完整隔离验收未执行。完整执行能力位继续清零，goal active。


## RMM调用内NC/驻留BO检查复用（ai）

ah中READY/RETURN仍逐页读取同一BO的归属、service、关闭/隐藏状态和context租约。RSI分发全程持有`xshm_policy_lock`，BO元数据与受保护PT不会被其他Client、Proxy或另一RMM调用并发修改；NC/驻留叶子不调用逐页物理缓存维护。因此这些BO字段在本次调用内是稳定的，而实际PTE仍需逐页检查。

本轮`task_cache()`增加一个局部`checked_nc_tag`：首先检查当前tag范围和真实PTE的有效/AF/USER位，再完整认证新BO及其租约和完整NC/隐藏状态；后续相同tag可复用本次检查。无tag页/空表跳过不产生回调；遇不同BO则重新检查，普通WB物理维护前清除复用状态。局部变量不跨RSI续调用，最终NC屏障之后不再读取下一页；每次续调用重新认证，失败照常隔离并保留引用。没有共享提示、持久验证缓存或新的失效协议，没有取消真实PTE检查，也不把已检查BO当成任务完成证明。READY和RETURN共用此路径。

新增10组实际PT核心负例，预算测试共21组，覆盖同一NC BO的后续PTE/非法tag、下一BO的owner/service/hidden/closing/cache-context错误、续调用前关闭、RETURN的同调用PTE损坏，以及WB维护回调改变旧NC BO后再次遇到它。原11组仍覆盖多批、纯NC/驻留/混合WB、屏障失败、真实维护失败和任务租约复用。新旧实际核心均运行同一21组断言，输出与调用数一致；断言覆盖预算、错误状态及回收，并非所有可能状态的等价性证明，更不是物理隔离证明。两个隔离副本分别故意把PTE检查移到复用命中之后、让复用跨过WB回调，新增用例11/20均以断言失败拒绝；生产源码未改。最终完整回归、ASan/UBSan及DMA回归通过。原预算夹具在扩展前已恢复到备份并核对SHA；两份中间回归日志保留，最终记录以`unit-private-scan-runs-final.log`为准。

改动目的｜减少持锁扫描中的重复BO元数据检查｜ah339 → ai451｜+112/+33.04%｜仅RMM运行源码和对应测试变化，O2 Debug/断言、两端Image/Host/initrd/runner/内存配置/完整33场景/null-noop/finish及GPU请求600实际594MHz相同，CPU未锁恒频｜下列run/命令/退出码/日志｜保留实验候选，隔离和整体性能验收未完成。

| 指标 | ah | ai |
| --- | ---: | ---: |
| 完整720p分数 | 339 | 451 |
| 成功退休任务数 | 125451 | 168595 |
| READY+RETURN ms/任务 | 1.091899 | 0.481654 |
| COMPLETE操作累计秒 | 54.013327 | 71.922275 |
| COMPLETE间隔累计秒 | 19.664369 | 27.194837 |
| benchmark墙钟秒 | 356.749163 | 353.937395 |

逐场景帧时变化中位数-24.73%，全部差异/退化见`private-completion-comparison-ah-ai.json`。不同任务数/组合下的累计秒数不能作为单位任务收益；单轮对照不证明长期稳定收益。1000门槛FAIL，不继承共享1405或旧多Client成绩。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-scan-runs bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`unit-private-scan-runs-final.log`；同一HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，`dma-private-scan-runs.log`。`compare-private-scan-runs-core.py`退出0，`private-scan-runs-differential.json`及`scan-runs-differential/`保留双方输出。固定补丁清单检查退出0，`patch-private-scan-runs.log`。
- 构建：`build-private-scan-runs.py`退出0，23个目标参数文件与ah归一化后相同，保留O2/DEBUG/断言；独立`rmm-build-scan-runs/`不覆盖ah构建。`build-private-scan-runs-firmware.py`及`freeze-private-scan-runs.py`各成功一次，FIT/含BSS布局PASS，RMM末址0x2800000不扩大，无新增静态内存。源码和冻结输入SHA在`private-scan-runs-source-hashes.json`及新候选`hashes.json`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-w --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-scan-runs --run-id private-heap-rmm-20261030-w`退出0，Host恢复/Realm能力1；`private-scan-runs-readback-20261030-a`通过独占入口运行`verify-private-scan-runs-sd.py`退出0，SD两段字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ai -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-scan-runs-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。计算/33场景/validation26-1-6及严格解析通过，两端kernel-log与pool-unbind各2项rc0、VM0/0、Host健康/CPU0–1/GPU300MHz/pmthor及资源恢复，11份证据SHA通过。原始证据`build/lab-runs/private-heap-720-20261030-ai/`，分析`private-scan-runs-ai-hardware.json`、`private-cache-ai.json`、`private-phases-ai.json`与上述对照。

本轮没有绑定错误，ae的validation EBUSY仍未定位。多Client/实体CPU与DMA攻击、广泛API/ML、动态OOM及并发销毁未完成，完整执行能力位继续清零，goal active。

归档脚本首次把新增模型的21组计数误用为证据文件数，实际回收11份，断言在修改manifest前失败；两个manifest仍与改动前备份SHA一致。修正仅归档断言后重新执行，失败记录保留于`checkpoint-private-scan-runs-failed.json`，不改变负载成绩或正确性标准。


## RMM完整归还后的纯状态重查（aj）

ai的RETIRE在清理前后两次调用完整RETURN；后者为真实缓存维护设置前后两次quiesce检查。已成功RETURN时，核心游标已结束、不会再维护数据页，但嵌套调用仍每个边界重复两次硬件检查，RETIRE共四次。此阶段ai约0.286ms/任务，和实际数据归还分开计时。

新增内部`gpu_private_task_returned()`仅检查RMM私有元数据：原service/Client/context/task、完整READY与RETURN游标、页数一致、静止/已激活状态、无隔离/撤销/待完成映射或扩容、任务引用及精确AS租约。它不访问数据页、不调用ops、不修改状态。固件RETURN仅在私有`task->cpu_returned`已置位时调用该函数，并在调用前仍核验真实STOP/SUSPEND ACK、父子状态、错误和已禁用AS；检查成功后直接封装回复。首次/部分RETURN继续逐PTE扫描、维护真实缓存并在前后检查硬件；未完成返回不能进入纯状态路径。无新RSI、共享提示、能力位或Proxy完成授权。

RETIRE仍在清理前后分别调用RETURN，两个边界都核验真实硬件状态，只取消边界内没有物理回调/设备写入时的第二次重复观察。RETIRE后续原有指针清理、序号保存和租约释放顺序不变；第一次RETURN仍必须成功后才能退休，错误/不确定时仍隔离并保留引用。这不改变真实COMPLETE/SUSPEND/AS flush-disable条件，不把纯元数据检查当作设备完成证明。

23组新增实际PT核心用例覆盖513页的READY前/未静止/部分RETURN拒绝、正确重复查询、跨service/Client/context/token、未完成游标、页数不符、pending/扩容、引用/标志、AS槽位及owner不符，检查无元数据修改和无额外物理回调，退休后旧token失效。现有193阶段实际平台/固件模型中20次可接受RETURN重查均要求两次configuration读取（一次完整quiesce的起止），旧固件在该计数断言中预期失败；原设备根/错误/退休清理回调故障负例继续通过。三个隔离副本分别去掉RETURN游标、页数一致性和AS归属检查，新用例均以断言失败拒绝。全部为模型，不能代替物理隔离验收。

改动目的｜减少完整归还后重复的硬件重查｜ai451 → aj459｜+8/+1.77%｜只改RMM私有核心/固件核心及内部头文件，测试同步增加；两端Image/Host/initrd/runner、O2 Debug/断言/预算、私有内存配置、完整33场景/null-noop/finish及GPU请求600实际594MHz相同，CPU未锁恒频｜下列run/命令/退出码/日志｜保留实验候选，性能和隔离整体验收待完成。

| 指标 | ai | aj |
| --- | ---: | ---: |
| 完整720p分数 | 451 | 459 |
| 成功退休任务数 | 168595 | 171419 |
| READY+RETURN ms/任务 | 0.481654 | 0.483720 |
| RETIRE ms/任务 | 0.286144 | 0.250074 |
| COMPLETE操作累计秒 | 71.922275 | 73.523913 |
| COMPLETE间隔累计秒 | 27.194837 | 27.807294 |
| benchmark墙钟秒 | 353.937395 | 353.632243 |

RETIRE单位任务耗时变化-12.61%。逐场景帧时变化中位数-1.66%；全部退化和差异见`private-completion-comparison-ai-aj.json`。任务数/组合不同，累计秒数不能直接作为单位任务收益；单轮对照不证明长期稳定提分。1000门槛FAIL，不继承历史共享1405或旧多Client PASS。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-return-replay bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`unit-private-return-replay-final.log`；同一HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，`dma-private-return-replay-final.log`。中间原测试回归日志另保留，未用其代替新增测试的最终结果。`check-private-return-replay-models.py`退出0，四项预期拒绝记录于`private-return-replay-model-negatives.json`和`return-replay-negative-tests/`；固定补丁清单退出0，`patch-private-return-replay.log`。
- 构建：`build-private-return-replay.py`退出0，23目标参数文件与ai归一化后相同，独立`rmm-build-return-replay/`不覆盖ai。`build-private-return-replay-firmware.py`及`freeze-private-return-replay.py`各成功一次，FIT/含BSS布局PASS；无新静态数据，RMM末址0x2800000不扩大。输入/源码SHA见新候选`hashes.json`及`private-return-replay-source-hashes.json`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-x --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-return-replay --run-id private-heap-rmm-20261030-x`退出0，Host/Realm能力1恢复；独占入口`private-return-replay-readback-20261030-a`运行`verify-private-return-replay-sd.py`退出0，实际SD两段字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-aj -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-return-replay-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。计算/33场景/validation26-1-6及严格解析通过；两端kernel-log与pool-unbind各2项rc0、VM0/0、Host健康/CPU0–1/GPU300MHz/pmthor及资源恢复，11份SHA核验通过。原始证据`build/lab-runs/private-heap-720-20261030-aj/`，分析`private-return-replay-aj-hardware.json`、`private-cache-aj.json`、`private-phases-aj.json`和上述对照。

本轮无绑定错误，不据此关闭ae validation EBUSY。多Client/实体Proxy CPU-DMA攻击、广泛API/ML、真实动态OOM及并发销毁未完成，完整执行能力位清零，goal active。


## 撤回：控制页快照按范围失效缓存（ak）

此实验将RSI `read_page()`的失效参数由整页改为`memory + offset, bytes`，其他边界/实际DATA granule/锁/私有映射/失效后屏障/复制/释放顺序不变。AArch64 helper按缓存行覆盖起止；模型中8/16字节短读从64条缓存行操作降为1条，跨行2条、整页64条。每次读取仍获取新设备状态，没有复用旧快照；真实PTE、对象归属、生命周期、完成和清理保护均未改变。它仅影响已CPU隐藏的内部控制页读取，不是普通Client数据页缓存策略。

新旧实际helper均通过21组读取结果/范围/顺序/边界/重复读取用例，四个隔离副本（偏移错误、跳过失效、无屏障、无末端检查）均被运行时断言拒绝。完整私有/DMA模型、ASan/UBSan、ARM64 O2 Debug/全部断言、23目标编译参数、固定补丁、FIT/含BSS布局通过，末址0x2800000不扩大，无新静态内存。模型不代替物理机密性或缓存一致性证明。

改动目的｜减少短状态读取的整页缓存失效｜aj459 → ak458｜−1/−0.22%｜只改RMM RSI读取helper及测试，两端Image/Host/initrd/runner、O2 Debug/断言/4096元数据与512物理维护预算、私有内存配置/完整720p33场景/null-noop/finish及GPU请求600实际594MHz相同，CPU未锁恒频｜下列run/命令/退出码/日志｜撤回；有效运行但无可测收益，不解释为已证明退化。

| 指标 | aj | ak |
| --- | ---: | ---: |
| 完整720p分数 | 459 | 458 |
| 已退休任务 | 171419 | 171366 |
| READY+RETURN ms/任务 | 0.483720 | 0.483609 |
| COMPLETE ms/任务 | 0.428913 | 0.428666 |
| RETIRE ms/任务 | 0.250074 | 0.250613 |
| benchmark观察墙钟秒 | 353.632243 | 355.390264 |

逐场景帧时变化中位数+0.14%，完整差异见`private-completion-comparison-aj-ak.json`。本轮不能以缓存行数下降宣称整机提分，也不能由一轮−0.22%证明稳定退化；不追加重复测量掩盖无收益结果。1000门槛FAIL，入口退出1；广泛API/ML、多Client、实体CPU/DMA攻击、动态OOM与并发销毁未执行。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-control-read bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-control-read.log`含新增21组/预算21组/RETURN重查23组/绑定41/提交99；相同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，`dma-private-control-read.log`含20次RETURN重查。`check-private-control-read-models.py`退出0，双方21组及四项预期拒绝见`private-control-read-models.json`与`control-read-differential/`。
- 构建：`build-private-control-read.py`、`build-private-control-read-firmware.py`、`freeze-private-control-read.py`各成功一次，固定候选`private-control-read-candidate/`、固件`firmware-private-control-read/`；RMM SHA `0547ea1bd5faa0843e577d7f7ef75f27cc457d5099b832ab17fba9a118fd128b`，源码SHA `private-control-read-source-hashes.json`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-y --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-control-read --run-id private-heap-rmm-20261030-y`退出0；`private-control-read-readback-20261030-a`运行`verify-private-control-read-sd.py`退出0，Host/Realm能力1与SD字节SHA核验通过。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ak -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-control-read-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，仅1000门槛失败。计算、33场景/validation26-1-6及严格解析通过，两端kernel-log和pool-unbind各2项rc0/状态0，VM0/0、Host健康/CPU0–1/GPU300MHz/pmthor和资源恢复通过，11份证据SHA核验。目录`build/lab-runs/private-heap-720-20261030-ak/`；分析`private-control-read-ak-hardware.json`、`private-cache-ak.json`、`private-phases-ak.json`及上述对照。
- 撤回：实际RSI与私有测试入口恢复到`before-private-control-read/`的aj字节，完整24项aj源码SHA一致。仅本实验新增的测试源和checker从运行源码移除，和本实验RSI/入口副本一并保存在`control-read-withdrawn-sources/`并记录SHA，不留无调用测试分支。候选/构建/本地与硬件证据继续保留。预备的保留型文档/manifest脚本未执行。
- SD2恢复：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-z --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-return-replay --run-id private-heap-rmm-20261030-z`退出0；`private-control-read-readback-rollback-20261030-a`运行`verify-private-control-read-rollback-sd.py`退出0，实际SD恢复为aj固件并回读一致，Host/Realm能力1/资源恢复。恢复后GPU未新增测量，不能将原aj459称为本次恢复后的实测。

后续优先研究RETIRE的全BO扫描：当前每个BO记录600字节，两次遍历全1024项，即使任务只使用少量对象。已通过实际结构布局工具确认，尚未新增索引或改变归属/租约检查。未复现绑定错误不能关闭ae EBUSY；完整执行能力位继续清零，goal active。


## RMM私有租约分组索引（al）

原`gpu_private_task_retire()`每任务两次扫描全部1024个BO，第一遍预检租约归属，第二遍释放租约。每个BO记录600字节，访问跨越约600KiB元数据，即使任务只用少量BO。新实现利用每上下文尾部2字节填充保存16位`cache_groups`，默认每位对应64个对象；可配置对象数使用向上取整的分组宽度，末组裁剪至实际数组末端。没有新的静态表，上下文仍112字节、BO仍600字节，实际AArch64 ELF中的两数组地址和大小均与aj一致。

位图仅由RMM在同一policy锁内维护。普通READY/RETURN扫描首次检查某BO时与动态heap扩展首次获得租约时，都通过`cache_lease_acquire()`设置其组位并建立`cache_context`；位图不能来自Client提示或Proxy请求。回调失败/部分扩展保留租约和组位，直到可信reset。退休只跳过没有位的组，选中组内仍逐个检查真实租约归属及owner/service/control；所有组预检完成后，才执行第二遍释放，随后清空位图。无租约的控制页不加入索引，其他上下文即使位于同组也不受影响。上下文创建/销毁和可信设备撤销清空摘要。实际PTE扫描、物理缓存维护、任务游标/AS租约校验和RETIRE硬件清理前后两个边界均未减少。

新增26组实际核心测试覆盖16组末端/63与64边界/1023末对象、多组租约、后组owner/service/control错误时不释放前组、同组其他上下文租约不受影响、READY同步失败保留、重复任务重新索引、成功/失败的动态扩展与空任务。对象数1000、1031各26组检查非整分组边界；五个隔离副本分别漏记普通路径、漏记扩展路径、漏扫末组、删除control检查、在预检全部结束前提前释放，均被运行时断言拒绝。模型不代表物理隔离证明。

改动目的｜减少退休阶段对无关BO的全表扫描｜aj459 → al464｜+5/+1.09%｜仅RMM运行核心变化，Client/Proxy/Host/initrd/runner、O2 Debug/断言/4096元数据与512物理维护预算、私有内存配置/完整720p33场景/null-noop/finish及GPU请求600实际594MHz相同，CPU未锁恒频｜下列run/命令/退出码/日志｜保留实验候选，整体验收待完成。

| 指标 | aj | al |
| --- | ---: | ---: |
| 完整720p分数 | 459 | 464 |
| 已退休任务 | 171419 | 173181 |
| READY+RETURN ms/任务 | 0.483720 | 0.484666 |
| COMPLETE ms/任务 | 0.428913 | 0.427692 |
| RETIRE ms/任务 | 0.250074 | 0.229801 |
| benchmark观察墙钟秒 | 353.632243 | 355.377097 |

逐场景帧时变化中位数-1.00%，完整差异和退化保留在`private-completion-comparison-aj-al.json`。任务组合不同，累计耗时需按退休任务数归一化；单轮对照不证明稳定收益。1000门槛FAIL，不能继承共享模式或旧多Client结果。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-lease-groups bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`unit-private-lease-groups.log`含新增26组、缓存预算21组、RETURN重查23组、绑定41/提交99；相同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，日志`dma-private-lease-groups.log`含20次RETURN重查。`check-private-lease-groups-models.py`退出0，52组配置与五项预期拒绝见`private-lease-groups-models.json`；补丁清单退出0。
- 构建：`build-private-lease-groups.py`成功一次，23目标参数文件与aj归一化相同。首个打包脚本误保留旧RMM输入目录，在字节SHA核验时拒用，未部署；原产物及`lease-groups-packaging-rejection.json`保留。修正版`build-private-lease-groups-firmware-reviewed.py`使用独立输出目录成功一次；FIT/含BSS布局PASS，末址0x2800000不扩大。冻结输入SHA见`private-lease-groups-candidate/hashes.json`，源码见`private-lease-groups-source-hashes.json`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-aa --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-lease-groups-reviewed --run-id private-heap-rmm-20261030-aa`退出0，仅SD2固件，Host/Realm能力1恢复。`private-lease-groups-readback-20261030-a`独占运行`verify-private-lease-groups-sd.py`退出0，实际SD两段SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-al -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-lease-groups-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，仅1000门槛失败。完整33场景/计算/validation26-1-6、两端日志/解绑、VM0/0、Host健康/CPU0–1/pmthor/资源恢复及11份证据SHA通过。目录`build/lab-runs/private-heap-720-20261030-al/`，分析`private-lease-groups-al-hardware.json`、`private-cache-al.json`、`private-phases-al.json`及上述对照。

ae validation VM_BIND EBUSY仍未定位，本轮未记录不等于修复。多Client/实体CPU-DMA攻击、广泛API/ML、真实动态OOM及并发销毁未完成，完整执行能力位清零，goal active。


## RMM元数据扫描窗口（am）

al中READY和RETURN各551363次，平均每退休任务3.184次，所有调用均报告零普通物理同步页。元数据仍需逐项检查，但4096项一批导致多次RSI、worker交接以及每批前后的真实配置/AS/停止状态检查。本轮只把`CACHE_SCAN_BATCH`由`8 * GPU_PRIVATE_BATCH`提高为`32 * GPU_PRIVATE_BATCH`，即4096→16384。实际物理缓存维护`sync_budget`仍为512；逐一实际PTE、对象归属/关闭/控制属性、NC/驻留状态、缓存租约、延续游标和最终计数检查不变。每批仍执行原来的硬件前后检查，真实完成和回收条件不变，没有新增ABI/权限/静态内存。这是有界窗口参数优化，不是新的授权算法。

窗口扩大意味着单次RMM调用可能更长。16384项仍是确定的数量上限，不能从它推出实时延迟保证；多Client下的等待长尾、公平性和更广泛负载仍待验收。本轮没有减少实际检查，也未缓存跨调用的PTE/归属证明。

本地原21组边界用例的密集映射扩大为`2 * CACHE_SCAN_BATCH + 1`，使新旧实现均真实跨越两次完整元数据窗口并保留尾部；跨调用损坏PTE、owner、关闭状态、缓存状态和回调失败仍受检查。新8组固定负载分别在实际新旧核心上运行：8193页NC的READY/RETURN各3→1次，32769页NC各9→3次，8193页NC+513页WB各4→2次；513页WB仍各2次，8193页WB仍各17次，物理维护上限不变；坏PTE、NC屏障失败、物理维护失败均拒绝且保留不确定状态。四个隔离副本分别去掉元数据预算递减、扩大物理预算、去掉实际PTE检查或NC屏障，都被运行时断言拒绝。它们是实际源码模型，不是实体隔离证明。

改动目的｜减少READY/RETURN元数据续调用与重复硬件重查｜al464 → am492｜+28/+6.03%｜仅RMM运行常量变化；Client/Proxy/Host/initrd/runner、O2 Debug/全部断言、512页物理维护、私有内存配置/完整720p33场景/null-noop/finish、GPU请求600实际594MHz相同；CPU未锁恒频｜下列run/命令/退出码/日志｜保留实验候选，整体验收待完成。

| 指标 | al | am |
| --- | ---: | ---: |
| 完整720p分数 | 464 | 492 |
| 已退休任务 | 173181 | 184404 |
| READY调用/任务 | 3.183738 | 1.060102 |
| RETURN调用/任务 | 3.183738 | 1.060102 |
| READY单次操作平均us | 61.311 | 169.327 |
| RETURN单次操作平均us | 90.920 | 197.937 |
| READY+RETURN ms/任务 | 0.484666 | 0.389337 |
| COMPLETE ms/任务 | 0.427692 | 0.426856 |
| RETIRE ms/任务 | 0.229801 | 0.225145 |
| benchmark观察墙钟秒 | 355.377097 | 354.844345 |

逐场景帧时变化中位数-5.81%，完整差异和退化见`private-completion-comparison-al-am.json`。操作计时包括Guest/RMM路径，不是纯RMM耗时或GPU执行时间；单次平均操作变长，调用减少后每任务总操作耗时仍下降。任务组合不同，累计秒数需按退休任务归一化；单轮对照不证明稳定收益，也不代表多Client吞吐/公平性。1000门槛FAIL，未沿用共享模式或旧多Client结果。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-scan-window bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-scan-window.log`含新8组、边界21组、租约26组、RETURN重查23组、绑定41/提交99。相同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，日志`dma-private-scan-window.log`含20次RETURN重查。`check-private-scan-window-models.py`退出0，新旧各21+8组及四项预期拒绝见`private-scan-window-models.json`与`scan-window-models/`。补丁清单退出0。
- 构建：`build-private-scan-window.py`、`build-private-scan-window-firmware.py`、`freeze-private-scan-window.py`各成功一次，RMM SHA如上。23目标参数文件与al归一化相同，DEBUG/全部断言保留；上下文和BO静态数组地址/大小一致，含BSS布局/FIT检查通过，末址0x2800000不扩大。源码和冻结输入SHA见`private-scan-window-source-hashes.json`及新候选`hashes.json`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-ab --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-scan-window --run-id private-heap-rmm-20261030-ab`退出0，仅SD2固件，Host/Realm能力1恢复。`private-scan-window-readback-20261030-a`独占运行`verify-private-scan-window-sd.py`退出0，实际SD字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-am -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-scan-window-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，仅1000门槛失败。计算、完整33场景/validation26-1-6、两端日志/解绑、VM0/0、Host健康/CPU0–1/pmthor/资源恢复及11份SHA通过。目录`build/lab-runs/private-heap-720-20261030-am/`，分析`private-scan-window-am-hardware.json`、`private-cache-am.json`、`private-phases-am.json`与上述对照。

ae validation VM_BIND EBUSY仍未定位，本轮未记录不等于修复。多Client/实体CPU-DMA攻击、广泛API/ML、真实动态OOM、并发销毁和更长RMM窗口的多Client长尾未完成，完整执行位保持清零，goal active。


## RMM组内连续页表扫描（an）

上一候选已将READY/RETURN平均调用压到每任务约1.06次；继续提高窗口的收益有限。本轮改为减少同一批内的重复定位：先认证RMM私有表归属和32项分组，再直接迭代该组。每项仍扣元数据预算、读取真实对象tag和硬件PTE并检查有效属性；不同BO仍检查归属、关闭状态、NC/驻留完整交接及缓存租约。最近已认证NC BO的复用范围与原实现相同。遇物理缓存回调即退出组内循环，下一项重新检查表和分组；未把跨回调或跨RSI的状态当作可信缓存。空组/空表消耗及所有失败游标、隔离与回收条件保持不变。

元数据预算仍16384、物理维护仍512，每批真实配置/根/停止状态前后检查不变；没有更改固件生命周期、权限、ABI、Client/Proxy驱动或静态内存。上下文数组3584字节、BO数组614400字节，实际ELF地址/大小与am相同，RMM末址仍0x2800000。该改动是扫描循环优化，不是新的授权机制。

本地实际新旧核心各通过21组跨续调用边界和8组固定负载。额外在0、31、32、63、64、511、512、8192、16383项分别破坏PTE，READY和RETURN共36组均拒绝；六项隔离副本分别去掉元数据预算、扩大物理预算、去掉PTE检查、去掉NC屏障、跨物理回调复用旧证明、跳过分组末项，均被运行时断言拒绝。它们是源码模型，不证明实体攻击防护。控制机微基准为8193页NC扫描2万次、新旧交替各7轮，中位数0.258635→0.213136秒（−17.59%）；这不是RK/GPU成绩，不用于推断整体收益。

改动目的｜减少READY/RETURN同组内重复表定位｜am492 → an535｜+43/+8.74%｜仅RMM扫描循环变化；Client/Proxy/Host/initrd/runner、O2 Debug/全部断言、16384/512预算、私有内存配置、完整720p33场景/null-noop/finish、GPU请求600实际594MHz相同；CPU未锁恒频｜下列run/命令/退出码/日志｜保留实验候选，整体验收待完成。

| 指标 | am | an |
| --- | ---: | ---: |
| 完整720p分数 | 492 | 535 |
| 已退休任务 | 184404 | 201510 |
| READY ms/任务 | 0.179504 | 0.112744 |
| RETURN ms/任务 | 0.209833 | 0.143526 |
| READY+RETURN ms/任务 | 0.389337 | 0.256270 |
| COMPLETE ms/任务 | 0.426856 | 0.427831 |
| RETIRE ms/任务 | 0.225145 | 0.219579 |

操作时间含Guest/RMM路径，不是纯RMM或GPU时间；单轮结果不证明长期稳定提分，也不覆盖多Client公平性。逐场景帧时变化中位数-7.88%，完整差异和退化保留于`private-completion-comparison-am-an.json`。没有由微基准外推分数。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-group-walk bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`unit-private-group-walk.log`；相同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，日志`dma-private-group-walk.log`。`check-private-group-walk-models.py`和`check-private-group-boundaries.py`退出0，证据`private-group-walk-models.json`、`private-group-walk-boundaries.json`；补丁清单退出0。
- 构建：`build-private-group-walk.py`、`build-private-group-walk-firmware.py`、`freeze-private-group-walk.py`各成功一次；RMM SHA如上，23个目标参数文件与am一致，DEBUG/全部断言保留，FIT和含BSS布局通过。源码及冻结输入哈希在`private-group-walk-source-hashes.json`和候选`hashes.json`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-ac --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-group-walk --run-id private-heap-rmm-20261030-ac`退出0，仅SD2固件，Host/Realm能力1恢复。`private-group-walk-readback-20261030-a`独占执行`verify-private-group-walk-sd.py`退出0，实际SD两段SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-an -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-group-walk-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL。计算、完整33场景/validation26-1-6、两端日志/解绑、VM0/0、Host健康/CPU0–1/pmthor/资源恢复及11份SHA通过。目录`build/lab-runs/private-heap-720-20261030-an/`，分析`private-group-walk-an-hardware.json`、`private-cache-an.json`、`private-phases-an.json`与上述对照。

README另补当前/历史开发记录边界，说明正常私有提交已接通、实际能力值与两种预算；该文档整理未改运行代码，无新增性能测量，不据此宣称提分。ae validation VM_BIND EBUSY仍未定位，本轮未记录不等于修复。多Client/实体CPU-DMA攻击、广泛API/ML、真实动态OOM、并发销毁及长尾公平性仍未完成，执行能力位清零，goal active。

## 撤回：只读 MMIO 快照屏障合并（AO）

实验仅改变 RK3588 `firmware_running()` 的只读寄存器检查：将部分逐次强读替换为入口、出口 `DSB SY` 包围的 relaxed 32 位读取，仍使用 Device-nGnRE 映射。正常配置的实际 19 次寄存器读取、短路判断、根配置比较、最终 MMU/GPU 故障重读均保留；其他强读、写操作、轮询、真实 PTE/对象归属/生命周期、缓存交接及可信完成检查不变。正常路径模型的屏障数从 38 降为 10，属于局部指令优化尝试。

改动目的｜减少只读硬件状态检查中的重复屏障｜AN535 → AO533｜−2/−0.37%｜仅 RMM MMIO 快照与测试变化；Client/Proxy/Host/initrd/runner、O2 Debug/全部断言、16384 元数据/512 物理维护预算、私有内存配置、完整 720p 33 场景/null-noop/finish、GPU 请求 600 实际 594MHz 相同，CPU 未锁恒频｜下列 run-id、命令、退出码与日志｜撤回，无测得整体收益；不据单轮差异判定稳定退化。

| 阶段/指标 | AN | AO |
| --- | ---: | ---: |
| 完整 720p 分数 | 535 | 533 |
| 已退休任务 | 201510 | 200780 |
| PREPARE ms/任务 | 0.070956 | 0.071108 |
| READY ms/任务 | 0.112744 | 0.113003 |
| PUBLISH ms/任务 | 0.018601 | 0.018536 |
| START ms/任务 | 0.224613 | 0.227632 |
| COMPLETE ms/任务 | 0.427831 | 0.426241 |
| RETURN ms/任务 | 0.143526 | 0.143592 |
| RETIRE ms/任务 | 0.219579 | 0.221110 |
| READY+RETURN ms/任务 | 0.256270 | 0.256594 |
| benchmark 观察墙钟秒 | 352.391254 | 356.310720 |

逐场景帧时变化中位数约 +0.14%，单位任务 READY+RETURN 约 +0.13%，屏障减少未反映为关键路径收益。完整对照见 `build/rmm-client-bo-20261030/private-completion-comparison-an-ao.json`。阶段计时包含 Guest/RMM 路径，不是纯 RMM 或 GPU 执行时间；采样历史不完整和单轮对照限制继续保留。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-mmio-snapshot bash scripts/check/check-rmm-gpu-private.sh` 退出 0，日志 `unit-private-mmio-snapshot.log`；相同 HOST_CC 的 `bash scripts/check/check-dma-guard.sh` 退出 0，日志 `dma-private-mmio-snapshot.log`，含新增 27 组真实平台快照用例。新旧实现各 27 场景读取偏移序列及判定一致；五项错误副本分别去掉入口屏障、出口屏障、最终 MMU 读取、最终 GPU 读取或根比较，均被断言拒绝。首次差分脚本误解析 NULL 配置的空读取序列而失败，日志 `private-mmio-snapshot-models.log` 及目录 `mmio-snapshot-models/` 保留；修正解析后通过，见 `private-mmio-snapshot-models-reviewed.log` 与 `mmio-snapshot-models-reviewed/`。没有将解析失败计为通过。
- 构建：`build-private-mmio-snapshot.py`、`build-private-mmio-snapshot-firmware.py`、`freeze-private-mmio-snapshot.py` 各成功一次；23 个目标编译参数与 AN 一致，Debug/断言保留，AArch64 反汇编、静态数组地址/大小、FIT/含 BSS 布局检查通过，RMM 预留末址仍为 `0x2800000`。RMM ELF SHA 为 `6d60b874728c343ad1ce59cee79e6a0900683b4b931da8c22585c0d396006ea9`，输入见 `private-mmio-snapshot-candidate/hashes.json`。模型与反汇编不能证明实体隔离或完整硬件排序安全。
- SD2 部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-ad --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-mmio-snapshot --run-id private-heap-rmm-20261030-ad` 退出 0；`private-mmio-snapshot-readback-20261030-a` 独占运行 `verify-private-mmio-snapshot-sd.py`，退出 0，实际 SD 字节 SHA 一致。
- 完整 720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ao -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-mmio-snapshot-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1` 退出 1，仅 1000 分门槛失败；计算、完整 33 场景/validation 26/1/6、两端 kernel-log 与 pool-unbind、VM 0/0、Host 健康/资源恢复及 11 份回收证据 SHA 通过。日志目录 `build/lab-runs/private-heap-720-20261030-ao/`。原分析文件误沿用 `private-mmio-snapshot-an-hardware.json` 文件名，但其内部 run-id 为 AO；保留原件并增加正确命名的 AO 副本，未重新执行一次性分析脚本。
- 撤回：五份修改的运行源码逐字节恢复 `before-private-mmio-snapshot/` 的 AN 版本，新增快照测试从源码树移除；六份实验源保存在 `mmio-snapshot-withdrawn-sources/` 并记录 SHA。未保留新 relaxed accessor 或无调用测试分支。预备的保留型文档/checkpoint 脚本未执行，候选、构建与失败门槛证据保留。
- SD2 恢复：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-ae --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-group-walk --run-id private-heap-rmm-20261030-ae` 退出 0；随后 `python3 scripts/maintenance/lab-run.py --run-id private-mmio-snapshot-readback-rollback-20261030-a -- python3 build/rmm-client-bo-20261030/verify-private-mmio-snapshot-rollback-sd.py` 退出 0。两段 SD 实际字节与 AN 固件一致，Host `6.12.0-opencca-pmthor-opp3`、Realm 能力 1、CPU 0–1/pmthor 与资源恢复检查通过。恢复后 GPU 为 NOT_RUN，535 分引用原 AN 测量。

此次文档整理没有新增性能测量。当前仍保留 `private-group-walk-candidate/` 与 `firmware-private-group-walk/`。1000 分门槛 FAIL，AE validation VM_BIND EBUSY 仍未定位；多 Client、实体 CPU/DMA 攻击、广泛 API/ML、真实动态 OOM、并发销毁和长尾公平性仍未完成，完整执行能力位保持清零，goal active。


## 完成等待的有界计数探测（AP）

AN中COMPLETE平均每任务调用3.569次，累计操作约0.428ms/任务。每次完整观察都会向MCU发布STATUS_UPDATE并等待新ACK。本实验保留首次完整观察；只有它确认仍有未完成工作后，RMM才设置四次探测预算。探测读取由RMM私有组记录定位的受保护队列历史与序列计数；只要仍有计数落后就返回INCOMPLETE，不发布完成、不释放引用、不归还CPU缓存。计数达到目标也不能直接成功，必须继续原完整状态握手和所有完成检查；四次预算耗尽同样强制完整观察，避免陈旧内存计数永久阻断刷新。PROGRESS使用原完整观察路径，新的实际INSERT和完整观察结果都会清除旧预算。

每次探测前后仍重查实际配置、AS根、全局/子队列握手与所有stream错误；读失败或回调期间发生根/固件/stream损坏时隔离并保留数据。真实PTE、owner、生命周期、缓存交接、SUSPEND/AS禁用与最终计数重读、RETURN/RETIRE均保留。探测字节使用任务结构体填充，AArch64 ELF中的contexts/objects/groups/tasks数组地址和大小与AN完全一致；不扩大0x2800000预留。ABI2/RPC4及完整执行能力位清零不变。

改动目的｜减少已确认等待阶段的重复MCU状态握手｜AN535 → AP524｜-11/-2.06%｜仅RMM固件任务观察及测试变化；Client/Proxy/Host/initrd/runner、O2 Debug/全部断言、16384/512预算、私有内存配置、完整720p33场景/null-noop/finish、GPU请求600实际594MHz相同，CPU未锁恒频｜下列run-id、命令、退出码与日志｜撤回；本轮未测得收益，AN535仍为当前候选。

| 指标 | AN | AP |
| --- | ---: | ---: |
| 完整720p分数 | 535 | 524 |
| 已退休任务 | 201510 | 197750 |
| PREPARE ms/任务 | 0.070956 | 0.071342 |
| READY ms/任务 | 0.112744 | 0.113150 |
| PUBLISH ms/任务 | 0.018601 | 0.018655 |
| START ms/任务 | 0.224613 | 0.225945 |
| COMPLETE ms/任务 | 0.427831 | 0.400714 |
| RETURN ms/任务 | 0.143526 | 0.144826 |
| RETIRE ms/任务 | 0.219579 | 0.220723 |
| COMPLETE调用/任务 | 3.569322 | 3.800121 |
| COMPLETE间隔 ms/任务 | 0.157491 | 0.208233 |

逐场景帧时变化中位数-0.21%，完整差异及退化保留在`private-completion-comparison-an-ap.json`。阶段计时包含Guest/RMM路径，不是纯RMM或GPU时间；任务组合及采样历史不完整的限制仍保留。单轮对照不证明稳定收益、多Client公平性或实体隔离，也没有把模型中的握手减少直接换算为硬件提分。

本轮COMPLETE操作从0.427831降为0.400714ms/任务（−6.34%），但观察次数3.569→3.800（+6.47%），间隔从0.157491增为0.208233ms/任务（+32.22%）。操作与间隔合计0.585322→0.608946ms/任务（+4.04%），局部操作节省被更多等待抵消。间隔含固定短暂停顿与调度时间，没有实测MCU通知计数，不能据此证明设备刷新或Host调度的具体因果；详见`private-pending-probe-cost-analysis.json`。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-pending-probe bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`unit-private-pending-probe.log`；相同HOST_CC的`bash scripts/check/check-dma-guard.sh`最终退出0，日志`dma-private-pending-probe-final.log`。实际后端203阶段覆盖原有193阶段及新增10类探测场景，包含陈旧计数强制刷新、就绪计数仍需真实ACK/idle、伪造大计数、错误ACK、读取失败、回调内根/固件/其他stream损坏、错误Client/token及多队列等待。模型不证明实体机密隔离。
- 失败记录：首次本地回归在分段发布场景失败，随后补齐完整PROGRESS和新INSERT对旧探测预算的失效；日志`dma-private-pending-probe.log`保留。第二次在新增测试中发现“根低32位非零”的错误假设，修正为核对完整64位根；日志`dma-private-pending-probe-reviewed.log`保留。两次失败不计PASS，也未部署对应中间版本。
- 差分/保护检查：`python3 build/rmm-client-bo-20261030/check-private-pending-probe-models.py`退出0。实际AN核心/原夹具193阶段和新核心/新夹具203阶段分别通过；四项独立错误副本去掉预算递减、把未完成计数当成功、去掉回调后根检查、把就绪计数当成功，均被断言拒绝。证据`private-pending-probe-models.json`与`pending-probe-models/`。
- 构建：`build-private-pending-probe.py`、`build-private-pending-probe-firmware.py`、`freeze-private-pending-probe.py`各成功一次；23目标编译参数、Debug/断言、静态数组、FIT及含BSS布局检查通过。RMM ELF SHA `7e09192693edee3f4b118bcb48c7362a61819cc69e5471dfbe43682386014d4d`，源码/冻结输入见`private-pending-probe-source-hashes.json`和候选`hashes.json`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-af --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-pending-probe --run-id private-heap-rmm-20261030-af`退出0，仅SD2固件；`python3 scripts/maintenance/lab-run.py --run-id private-pending-probe-readback-20261030-a -- python3 build/rmm-client-bo-20261030/verify-private-pending-probe-sd.py`退出0，实际SD两段SHA一致，Host/Realm能力1恢复。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ap -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-pending-probe-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1；1000门槛FAIL。计算、完整33场景/validation26-1-6、两端kernel-log/pool-unbind、VM0/0、Host健康/CPU0–1/pmthor/资源恢复及11份证据SHA通过。目录`build/lab-runs/private-heap-720-20261030-ap/`，分析`private-pending-probe-ap-hardware.json`、`private-cache-ap.json`及`private-phases-ap.json`。

撤回：运行源码恢复到`before-private-pending-probe/`的AN字节，实验源保存在`pending-probe-withdrawn-sources/`并记录SHA。SD2恢复run-id `private-heap-rmm-20261030-ag`退出0；`private-pending-probe-readback-rollback-20261030-a`实际字节回读通过。恢复后GPU未新增测量，AN535为原测量，不冒充恢复后复测。

此次文档整理未新增性能测量。AE validation VM_BIND EBUSY未定位；多Client、实体CPU/DMA攻击、广泛API/ML、真实动态OOM、并发销毁和长尾公平性仍未完成，完整执行位清零，goal active。


## 队列单调历史移入 RMM（AQ）

原实现将只有RMM更新的队列历史放在受保护MCU输入页的偏移64处。虽然该页没有Client GPU别名、没有Proxy CPU映射，准备/发布/完成观察/退休仍会重复获取页、建立临时映射和失效缓存，以读取这个CPU私有游标。AQ把历史直接放到RMM私有数组，GPU可写的实际INSERT/EXTRACT/sequence及错误字段仍按原路径读取并核验，不从这些设备字段推导可信历史，也不减少STATUS_UPDATE/SUSPEND/禁用AS等完成条件。

队列基址保持128字节对齐，并为整批任务保留64位递增余量。退休先检查所有队列，之后调用实际私有任务/缓存租约退休；成功后才无回调地统一推进所有历史，失败时全组历史不变。中止已清理的环形队列同时清零历史；新group代际创建和可信reset也清零，旧token不能变成新工作的身份。物理页/PTE授权、归属、缓存维护窗口16384/512及内核依赖/fence语义均未变化。

历史需要8192字节，复用启动发现期的16392字节接口区间校验缓冲区。两者组成union：只有INSTALLED可执行发现，成功发现后整块清零；只有CONFIGURED可使用历史，且group只能在CONFIGURED创建。不会把运行中历史再次当作发现区间。实际AArch64中contexts/objects/groups/tasks以及复用存储的地址/大小、BSS末址和栈完全相同，RMM预留仍止于0x2800000，未通过扩大内存解决链接问题。

改动目的｜消除CPU私有队列历史的重复控制页映射与缓存访问｜AN535 → AQ536｜+1/+0.19%｜仅RMM固件运行核心变化；Client/Proxy/Host/initrd/runner、O2 Debug/全部断言、私有内存配置、完整720p33场景/null-noop/finish、GPU请求600实际594MHz相同，CPU未锁恒频｜下列run-id、命令、退出码与日志｜保留实验候选，整体验收未完成。

| 指标 | AN | AQ |
| --- | ---: | ---: |
| 完整720p分数 | 535 | 536 |
| 已退休任务 | 201510 | 202035 |
| PREPARE ms/任务 | 0.070956 | 0.070021 |
| READY ms/任务 | 0.112744 | 0.112900 |
| PUBLISH ms/任务 | 0.018601 | 0.016975 |
| START ms/任务 | 0.224613 | 0.224333 |
| COMPLETE ms/任务 | 0.427831 | 0.426049 |
| RETURN ms/任务 | 0.143526 | 0.144251 |
| RETIRE ms/任务 | 0.219579 | 0.216403 |
| COMPLETE调用/任务 | 3.569322 | 3.589967 |

本轮PUBLISH单位任务计时变化-8.74%，RETIRE变化-1.45%；这些局部变化占比很小，总分仅高1分，没有稳定整体提速证据。保留依据是将CPU私有可信历史归入RMM并消除可部分失败的逐页历史写回，不将536与535的单轮差异称为实质性能突破。

逐场景帧时变化中位数-0.26%，全部差异和退化见`private-completion-comparison-an-aq.json`。各阶段为Guest/RMM路径计时，不等于纯RMM耗时；单轮比较、任务组合差异及不完整采样历史限制保留。未用模型中减少的访问次数直接推算实体收益；多Client公平性、物理隔离和长期稳定性尚无本轮实测。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-queue-history-final bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-queue-history-final.log`；同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，`dma-private-queue-history-reviewed.log`。新增18项真实helper测试覆盖全队列预检、晚队列错误、租约退休失败、中止清零、64位末端/下一任务拒绝、不同group隔离、发现/运行相位和reset。原193阶段后端模型继续通过，包含38轮真实环形游标复用。新增夹具禁止再读偏移64；旧偏移内容损坏不再影响历史，退休也不再向该偏移写入。模型不证明实体隔离。
- 差分：`python3 build/rmm-client-bo-20261030/check-private-queue-history-models-final.py`退出0，AN原核心/原夹具与AQ核心/新夹具各193阶段通过；四项错误副本漏检后续队列、忽略租约退休失败、不清理中止历史、用覆盖代替累加均被断言拒绝。证据`private-queue-history-models-final.json`和`queue-history-models-final/`。
- 失败保留：首次直接给group增加8192字节，ARM64链接末址0x2601000超出现有0x25ff000链接上限（物理预留末址0x2800000），未部署；日志`rmm-private-queue-history.log`、源码`queue-history-initial-failed-layout/`保留。改为复用启动缓冲区后`resume-private-queue-history-build.py`退出0。第二版新增测试夹具宏与局部变量重名导致编译失败，`unit-private-queue-history-reviewed.log`和`private-queue-history-models-reviewed.log`保留，改成显式指针后通过；不影响运行核心。首次freeze脚本漏列已修改的check入口，核验主动拒绝，补齐清单后成功一次。失败不计PASS。
- 构建：最终RMM、U-Boot、freeze各成功一次；23项编译参数与AN一致，O2 Debug/断言保留，固定补丁/FIT/含BSS布局通过。数组/union布局见`private-queue-history-static-layout.json`；RMM ELF SHA `c8d4518def038669addd526794227b0adb1888165279e32bc929e7bd2ca16077`。候选`private-queue-history-candidate/`，固件`firmware-private-queue-history/`，源码SHA见`private-queue-history-source-hashes.json`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-ah --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-queue-history --run-id private-heap-rmm-20261030-ah`退出0，Host/Realm能力1恢复；`python3 scripts/maintenance/lab-run.py --run-id private-queue-history-readback-20261030-a -- python3 build/rmm-client-bo-20261030/verify-private-queue-history-sd.py`退出0，两段SD字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-aq -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-queue-history-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL。计算、33场景/validation26-1-6、两端kernel-log与pool-unbind、VM0/0、Host健康/CPU0–1/pmthor及资源恢复通过；原始证据`build/lab-runs/private-heap-720-20261030-aq/`，11份回收文件SHA一致。分析`private-queue-history-aq-hardware.json`、`private-phases-aq.json`与`private-cache-aq.json`。

本节整理本轮RMM改动与已完成的AQ硬件测量，没有额外复测，不继承旧PASS。AE validation VM_BIND EBUSY未定位；多Client、实体CPU/DMA攻击、广泛API/ML、动态OOM、并发销毁和长尾公平性仍未完成，完整执行位清零，goal active。


## 已停止任务的固件配置校验合并（AR）

原已停止任务重查会在固件核心两次读取完整配置，随后页表后端两次读取固件运行状态。AR只对RMM已记录quiesced、匹配精确Client/group/token且完成真实STOP/SUSPEND的任务，将完整配置检查集中到detach后端：AS检查前后各校验固件根/属性、MCU及故障状态、shader/tiler拓扑和可信计数频率。上层仍读取真实的全局/组/所有stream ACK和错误字段。后端不接受调用者提供的成功证明，不跨调用缓存配置，也不凭AS禁用单独证明固件停止。

首次停止仍保留原配置检查及START重查、真实SUSPEND/TERMINATE握手、FLUSH_MEM/UNMAPPED/UPDATE。RETURN每批物理缓存操作前后、RETIRE清零回收前后仍执行新的硬件重查。页表/PTE、物理归属、任务生命周期与租约、元数据/物理预算16384/512未改变；Client/Proxy/Host/initrd/runner逐字节沿用AQ，ABI2/RPC4、能力2147483643、完整执行位清零。

改动目的｜减少已停止任务重查的重复MMIO读取｜AQ536 → AR541｜+5/+0.93%｜仅RMM固件核心及RK后端变化；两端Image/Host/initrd/runner、O2 Debug/全部断言、私有内存配置、完整720p33场景/null-noop/finish、GPU请求600实际594MHz相同，CPU未锁恒频｜下列run-id、命令、退出码与日志｜保留实验候选；整体验收未完成。

| 指标 | AQ | AR |
| --- | ---: | ---: |
| 完整720p分数 | 536 | 541 |
| 已退休任务 | 202035 | 203809 |
| PREPARE ms/任务 | 0.070021 | 0.070271 |
| READY ms/任务 | 0.112900 | 0.113205 |
| PUBLISH ms/任务 | 0.016975 | 0.016995 |
| START ms/任务 | 0.224333 | 0.226126 |
| COMPLETE ms/任务 | 0.426049 | 0.423244 |
| RETURN ms/任务 | 0.144251 | 0.138519 |
| RETIRE ms/任务 | 0.216403 | 0.210000 |

RETURN单位任务变化-3.97%，RETIRE变化-2.96%。逐场景帧时变化中位数-0.81%，全部差异/退化保留在`private-completion-comparison-aq-ar.json`。这些计时涵盖Guest/RMM路径，不等于纯MMIO或GPU执行时间；单轮及任务组合差异不证明稳定收益。模型中一次有效重查105→75次MMIO读取（−28.57%）仅为代码路径证据。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-detach-validation bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-detach-validation.log`；同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，`dma-private-detach-validation-reviewed.log`。原193阶段后端继续通过，新增23类MMIO场景包括计数频率、shader/tiler、固件根/MCU/故障、缺失/别名AS、禁用root/属性/模式，以及检查中途篡改；有效RETURN重查计数确认后端执行两次完整配置检查，无MMIO写入或物理缓存回调。模型不证明实体隔离。
- 差分：`python3 build/rmm-client-bo-20261030/check-private-detach-validation-models.py`最终退出0，`private-detach-validation-models-final.log`。实际AQ核心/平台和AR核心/平台分别通过；删除完整前检查、完整后检查、别名检查、禁用root检查的四个独立错误副本均被断言拒绝。后续恢复报告复用已验证日志，未重复执行成功测试，见`private-detach-validation-models.json`及`detach-validation-models/`。
- 失败保留：新增模型首次把AS_STATUS偏移误写为AS+0x10，修正为生产定义AS+0x28后通过；日志`dma-private-detach-validation.log`。错误副本脚本文本定位重叠、旧路径读次数预期误写107而实测105，分别在报告阶段拒绝，修正后仅恢复未完成步骤；两个失败日志保留在`private-detach-validation-models*.log`。详见`private-detach-validation-failures.json`，中间失败版本均未部署。
- 构建：`build-private-detach-validation.py`、`build-private-detach-validation-firmware.py`及`freeze-private-detach-validation.py`各成功一次；23目标编译参数与AQ相同，Debug/断言、5个实际数组地址/大小、固定补丁/FIT/含BSS布局通过，RMM预留末址仍0x2800000。RMM ELF SHA `5f53ee89868ae1f91f6159801930d169dccd11200b24305cb1a7d1ea9b37bb35`，源码清单`private-detach-validation-source-hashes.json`，候选`private-detach-validation-candidate/`，固件`firmware-private-detach-validation/`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-ai --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-detach-validation --run-id private-heap-rmm-20261030-ai`退出0，Host/Realm能力1恢复。`python3 scripts/maintenance/lab-run.py --run-id private-detach-validation-readback-20261030-a -- python3 build/rmm-client-bo-20261030/verify-private-detach-validation-sd.py`退出0，两段SD字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-ar -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-detach-validation-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL。计算、33场景/validation26-1-6、两端kernel-log/pool-unbind、VM0/0、Host健康/CPU0–1/pmthor及资源恢复通过，11份证据SHA一致。证据`build/lab-runs/private-heap-720-20261030-ar/`；分析`private-detach-validation-ar-hardware.json`、`private-phases-ar.json`与`private-cache-ar.json`。

本节整理本轮改动和AR硬件测量，无额外复测，不继承旧PASS。AE validation VM_BIND EBUSY未定位；多Client、实体CPU/DMA攻击、广泛API/ML、动态OOM、并发销毁和长尾公平性仍未完成，完整执行位清零，goal active。


## 完整观察后的一次性无堆事件提示（AS）

Client在COMPLETE返回仍执行后立即调用HEAP_EVENT；旧路径重复核验实际固件/AS/stream并扫描堆状态。AS在RMM私有task中增加一次性提示：仅完整STATUS握手、所有stream错误/状态观察、队列与完成前缀、最终实际START重查都通过，且仍有工作、全部stream无OOM时设置。下一次相同已认证Client/service/token的HEAP_EVENT仍检查任务/上下文归属和生命周期，仅在无未决扩容时消费提示，返回全零无事件结果。第二次独立查询恢复实际硬件检查。

提示只减少一次无事件轮询，不是新鲜硬件证明。晚到OOM或MMU故障允许延后这一次查询报告；OOM保持未处理状态，下一次完整COMPLETE或独立查询检查它。不能据此扩容、完成任务、发布fence、访问数据、释放引用或回收页面。PROGRESS/COMPLETE在开始时失效旧提示，PUBLISH/QUIESCE/有效HEAP_GROW也清除；reset及任务清零删除提示。观察到OOM、未决映射或不确定发布时不能使用快捷路径。实际根/PTE/归属、真实完成条件和缓存交接/回收检查保留；没有引入AP已撤回的跨COMPLETE负探测预算。

改动目的｜避免紧随完整COMPLETE的无事件重复硬件扫描｜AR541 → AS536｜-5/-0.92%｜只替换RMM固件核心，Client/Proxy/Host/initrd/runner、O2 Debug/全部断言、私有内存预算、完整720p33场景/null-noop/finish及GPU请求600/实际594MHz一致，CPU未锁恒频｜下列run-id/命令/退出码/日志｜已撤回，源码与SD2恢复AR541。

| 指标 | AR | AS |
| --- | ---: | ---: |
| 完整720p分数 | 541 | 536 |
| 已退休任务 | 203809 | 202314 |
| PREPARE ms/任务 | 0.070271 | 0.070044 |
| READY ms/任务 | 0.113205 | 0.113015 |
| PUBLISH ms/任务 | 0.016995 | 0.017199 |
| START ms/任务 | 0.226126 | 0.226234 |
| COMPLETE ms/任务 | 0.423244 | 0.385900 |
| RETURN ms/任务 | 0.138519 | 0.139124 |
| RETIRE ms/任务 | 0.210000 | 0.209405 |

COMPLETE单位任务耗时变化-8.82%；该Guest计时包含随后堆服务，不能当作纯RMM或GPU耗时。逐场景帧时变化中位数-0.64%，完整差异见`private-completion-comparison-ar-as.json`。单轮和任务组合差异不证明稳定提分，也不从模型零MMIO直接推算硬件收益。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-heap-negative bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-heap-negative.log`。同HOST_CC的`bash scripts/check/check-dma-guard.sh`退出0，`dma-private-heap-negative-third.log`。204个实际核心/平台后端阶段通过，其中新增11项覆盖一次性消费、晚到OOM、晚到MMU故障、错误Client/service/旧token、PROGRESS/失败观察/PUBLISH/QUIESCE失效和已知OOM。命中只返回零，验证无MMIO读写/固件缓存失效/数据交接/控制页写入；后续查询读实际硬件。模型不证明实体隔离。
- 错误版本：`python3 build/rmm-client-bo-20261030/check-private-heap-negative-models.py`退出0；不消费提示、缺少PROGRESS失效、缺少PUBLISH失效、为已知OOM设置提示四个版本均以断言退出-6，见`private-heap-negative-models.json`和`heap-negative-models/`。正常旧193阶段继续通过，没有改写成功条件。
- 失败证据：前两次本地测试均退出134，分别因新增用例排在服务RELEASE后、PUBLISH误用仅适配COMPLETE读序列的夹具。修正测试编排和读回调后通过；失败源码/日志保存在`heap-negative-first-failure/`、`heap-negative-second-failure/`及`private-heap-negative-failures.json`，未部署失败版本。
- 构建：`build-private-heap-negative.py`、`build-private-heap-negative-firmware.py`、`freeze-private-heap-negative.py`各退出0。与AR的23份编译参数相同，保留Debug/全部断言；五个主要静态数组地址和大小相同，新增bool使用既有padding；固定补丁、FIT和含BSS布局检查通过，RMM预留末址仍0x2800000。元数据/物理预算16384/512、ABI2/RPC4、能力2147483643及完整执行位清零不变。候选`private-heap-negative-candidate/`，固件`firmware-private-heap-negative/`，源码29项`private-heap-negative-source-hashes.json`，RMM SHA `b9e3fcc2c31013b0044697f597a7ac2b74e20a51c9bfd26362d6c20a06805c8a`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-heap-rmm-20261030-aj --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-heap-negative --run-id private-heap-rmm-20261030-aj`退出0，Host/Realm能力1恢复。`python3 scripts/maintenance/lab-run.py --run-id private-heap-negative-readback-20261030-a -- python3 build/rmm-client-bo-20261030/verify-private-heap-negative-sd.py`退出0，两段实际SD字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-as -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-heap-negative-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL。计算、33场景/validation26-1-6、两端日志/解绑、VM0/0、Host健康/CPU0–1/pmthor和资源恢复通过，11份证据SHA一致。证据`build/lab-runs/private-heap-720-20261030-as/`；分析`private-heap-negative-as-hardware.json`、`private-phases-as.json`及`private-cache-as.json`。

本轮另一个观察：COMPLETE累计操作时间86.261→78.073秒，但调用间隙32.387→41.966秒；其中delayed worker队列等待766次/3.962秒→2059次/11.953秒，COMPLETE每任务调用3.613→3.768。5×5 effect2d场景帧时1.991→7.984ms，而全部场景帧时变化中位数为−0.639%。这些累计计数不能把额外等待唯一归因于该场景，也不能凭一轮区分GPU执行波动、轮询节奏和vCPU调度。局部调用变快没有形成整体收益，当前选择撤回；不宣称算法必然退化。

撤回：三个改动源码按`before-private-heap-negative/`恢复AR字节，实验源保存在`heap-negative-withdrawn-sources/`。SD2恢复run-id `private-heap-rmm-20261030-ak`和回读`private-heap-negative-readback-rollback-20261030-a`均退出0；恢复后未新增GPU测量。

本节记录本轮代码与AS测量，无额外复测，不继承旧PASS。历史AE的validation VM_BIND EBUSY仍未定位；多Client、实体CPU/DMA攻击、广泛API/ML、真实动态OOM、并发销毁及公平性仍未完成，goal active。


## 同队列有界前缀合批（AT）

RMM已支持一个token中同队列多个受保护wrapper按顺序执行，但Client原先只选择每队列一个就绪头。同队列自动FIFO尾fence使后续命令必须等前一批完成CPU归还/退休，重复支付PREPARE RPC、全上下文缓存/授权扫描、START RPC、COMPLETE和清理。AT让同队列的有界连续前缀共用一次任务生命周期，减少重复边界。

依赖检查只在unsignaled fence恰好等于本次已选成员的done，且group对象和queue均相同、原等待期限未过时，允许把它视作GPU内部顺序边。RMM原wrapper在CALL后等待全部scoreboard，再更新受保护sequence；同queue下一wrapper仍受此顺序约束。Client不提前signal任何done，不把PROGRESS/Proxy回复当CPU完成证明。外部fence、跨队列边、不同group和timeline chain继续执行原等待/错误检查，禁止unwrap未完成chain来跳过其历史；保持用户输入快照、强引用、6成员上限、mapping ticket、可信取消和不重放START。两个job的fence对象仍各自独立，但同批CPU完成可在退休后一起可见；任一可信阶段失败不会产生成功fence。

改动目的｜同队列命令共用RMM任务生命周期｜AR541 → AT540｜-1/-0.18%｜仅Client Image变化；RMM/Proxy/Host/initrd/runner、私有内存配置、完整720p33场景/null-noop/finish、GPU请求600/实际594MHz相同，CPU未锁恒频｜下列run-id/命令/退出码/日志｜已撤回，源码和板端Client Image恢复AR541。

| 指标 | AR | AT |
| --- | ---: | ---: |
| 完整720p分数 | 541 | 540 |
| 完成RMM批次 | 203809 | 203750 |
| PREPARE ms/RMM批次 | 0.070271 | 0.069916 |
| READY ms/RMM批次 | 0.113205 | 0.113357 |
| PUBLISH ms/RMM批次 | 0.016995 | 0.017077 |
| START ms/RMM批次 | 0.226126 | 0.226501 |
| COMPLETE ms/RMM批次 | 0.423244 | 0.423638 |
| RETURN ms/RMM批次 | 0.138519 | 0.138785 |
| RETIRE ms/RMM批次 | 0.210000 | 0.210181 |

AT计分期完成203764个Client成员，平均1.000069成员/批，分布（批次大小:次数）`{'1': 203743, '2': 3, '3': 2, '4': 1, '5': 1}`。AR没有成员大小直方图，不能把每批次的耗时下降当作每Client job的下降；RMM批次数也受实际渲染吞吐影响。上表时长包含Guest/RMM/RPC路径，不是纯GPU执行时间。单轮不证明稳定收益。

实测仅7/203750批合入多个成员，说明本次同队列前缀机制在该负载下几乎没有触发，因此没有形成足以减少任务生命周期次数的合批规模。现有计数不能区分外部/跨队列依赖、未完成timeline chain与生产者/worker时序等原因；后续应先记录选择失败的具体条件及队列可用性，再决定是否设计跨队列依赖批次或收集窗口，不能直接归因为某一种依赖，也不应据此放松完成或映射检查。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-private-submit.py`退出0，`unit-private-queue-prefix-reviewed.log`，113项（增加14项）覆盖6成员/7成员边界、混合队列、外部等待阻断整个后缀、含精确producer的pending/error chain不得绕过、期限、group/queue身份、分阶段不提前signal、失败/取消/引用和mapping ticket。原有用例保留其安全目的，相关阶段次数改为合批后的真实预期；mapping/排队取消用例继续在选中当前批次后加入后继，保留原竞争场景。这里只使用内核/RMM调用替身，不证明Linux并发或GPU语义。
- 完整私有回归：同HOST_CC、`GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-queue-prefix bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-queue-prefix-full.log`；原RMM核心、固件及Client/Proxy桥回归通过，RMM实现没有变更。`check-private-queue-prefix-models.py`退出0，五个独立错误版本（接受跨queue、跨group、unwrap pending chain、忽略外部wait、取消wait期限）均因断言被拒绝，见`private-queue-prefix-models.json`及`queue-prefix-models/`。
- 首次扩展夹具编译失败退出1：同一行的while/后续assert触发misleading-indentation。修正夹具格式；复核时同时把不连续enum范围改为显式COMPLETE/RETURN/RETIRE列表，并显式注入chain错误。失败及原夹具保存在`queue-prefix-first-failure/`、`unit-private-queue-prefix-expanded.log`和`private-queue-prefix-failures.json`。没有部署失败版本。
- 构建：`make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j4 Image`退出0，`client-private-queue-prefix.log`；新旧Image内置release均`6.12.0-g39d95dd028d4-dirty`，固定补丁清单通过。`freeze-private-queue-prefix.py`退出0，仅client-Image SHA变化；Client SHA `53d20ded3339ebb731bca733257fa5681394afb182c63c0f479d0927e8d8e171`。RMM沿用AR固件/O2 Debug/全部断言，预留末址0x2800000，ABI2/RPC4、能力2147483643、完整执行位清零。新增6个u64批大小计数共48字节/Client file，仅诊断，不参与授权。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-at -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-queue-prefix-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL。计算/完整33场景/validation26-1-6、两端kernel-log/pool-unbind、VM0/0、Host健康/CPU0–1/pmthor和资源恢复通过，11份证据SHA一致。证据`build/lab-runs/private-heap-720-20261030-at/`，分析`private-queue-prefix-at-hardware.json`、`private-phases-at.json`、`private-cache-at.json`和`private-completion-comparison-ar-at.json`。RMM/Host固件未重新刷写。

撤回：两个改动源码按`before-private-queue-prefix/`恢复AR，实验源在`queue-prefix-withdrawn-sources/`。`python3 scripts/maintenance/lab-run.py --run-id private-queue-prefix-restore-20261030-a -- python3 build/rmm-client-bo-20261030/restore-private-queue-prefix-runtime.py`退出0，仅恢复板端Client Image，并核验Client/Proxy/initrd/runner四项AR输入SHA；未改固件、Host或rootfs。恢复后GPU未新增测量，541为原AR实测。

本轮记录代码与AT测量，无额外复测，不继承旧PASS。AE validation VM_BIND EBUSY仍未定位；多Client、实体CPU/DMA攻击、广泛API/ML、真实动态OOM、并发销毁和公平性未验收，goal active。


## 提交与合批机会诊断（AU）

AT中只有7批发生同队列合并，尚不足以归因于哪类依赖。AU仅增加汇总观测：成功提交时记录成员数和当前run阶段，picker记录扫描深度/选中数，阻塞时记录实际readiness检查遇到的首个未完成fence。精确指针匹配最多检查6个已选成员；只识别chain类型，不unwrap、不等待、不把诊断值用于任何分支。所有计数在原private_gpu_lock下更新，关闭文件且worker排空后输出。新增37个u64（296字节/Client file）；没有逐任务日志。

改动目的｜定位同队列合批几乎不触发的原因｜AR541 → AU539｜-2/-0.37%｜仅Client诊断Image变化，完整720p33场景/null-noop/finish、私有内存配置、GPU请求600实际594MHz和其他输入相同；CPU未锁恒频，诊断本身可扰动时序｜下列命令/run-id/退出码/日志｜仅诊断，已撤回恢复AR，不宣称提分。

| 观测项 | 桶 | 次数 |
| --- | --- | ---: |
| 每次成功ioctl提交成员数 | 1 | 203154 |
| 提交时活跃run阶段，7=无活跃run | 1 | 23 |
| 提交时活跃run阶段，7=无活跃run | 2 | 36 |
| 提交时活跃run阶段，7=无活跃run | 3 | 6 |
| 提交时活跃run阶段，7=无活跃run | 4 | 6884 |
| 提交时活跃run阶段，7=无活跃run | 5 | 802 |
| 提交时活跃run阶段，7=无活跃run | 6 | 1066 |
| 提交时活跃run阶段，7=无活跃run | 7 | 194337 |
| picker选中成员数 | 0 | 15 |
| picker选中成员数 | 1 | 203154 |
| picker扫描候选数，6=至少6 | 1 | 182193 |
| picker扫描候选数，6=至少6 | 2 | 5281 |
| picker扫描候选数，6=至少6 | 3 | 1307 |
| picker扫描候选数，6=至少6 | 4 | 1313 |
| picker扫描候选数，6=至少6 | 5 | 1305 |
| picker扫描候选数，6=至少6 | 6 | 11770 |
| 首个阻断条件 | mapping_waiter | 11 |
| 首个阻断条件 | pending_selected_same_queue | 20964 |
| 首个阻断条件 | pending_chain | 4 |
| 首个阻断条件 | pending_other | 195697 |

成功提交成员203154，选中RMM批次203154，平均1.000000成员/批；提交成员加权和等于选中成员加权和，非空选中次数等于成功RETIRE次数，提交大小次数等于阶段次数，深度次数等于选中次数。阻断计数是重复访问次数，每个候选只记录本轮检查遇到的第一个未完成依赖，不代表唯一任务数、全部依赖数或时间占比；它不能单独证明消除该条件就能得到相同比例的性能收益。

本轮所有203154次ioctl均只有1个成员，194337/203154（95.66%）提交时无活跃run；182193/203169（89.68%）picker只扫描到1个候选。因此多数观察时点没有现成任务可合批，单纯增大批容量或仅接受更多依赖类型，无法在这些时点摊薄启动/回收边界。首个未完成依赖中有195697次不能精确匹配本次已选成员，它们可能对应尚未选中的前驱或外部fence，现有诊断不追踪其生产者，不能据此称为跨队列依赖。

后续重点应转向单任务完整生命周期：先分解START、COMPLETE与RETIRE内部握手/硬件检查的成本，再评估上下文驻留、发布与启动合并等方案是否能降低固定开销；这些只是待验证方向。若探索上下文驻留，必须把单任务完成可见性与页表/缓存租约的安全回收明确分开，保留真实完成、错误和撤销检查，不能直接把现有PROGRESS升级为CPU fence成功。

- 本地：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-private-submit.py`退出0，原99项不变；仅同步测试替身的计数字段，未以新测试重复实现诊断。日志`unit-private-pick-profile.log`。模型不证明Linux并发或物理GPU隔离。
- 构建：`make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j4 Image`退出0，`client-private-pick-profile.log`；release与AR均为`6.12.0-g39d95dd028d4-dirty`。固定补丁检查退出0，`patch-private-pick-profile.log`；冻结`private-pick-profile-candidate/`仅client-Image变化。
- 硬件：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261030-au -- python3 build/rmm-client-bo-20261030/run-private-with-uart.py --images build/rmm-client-bo-20261030/private-pick-profile-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL。完整33场景/计算/validation26-1-6、两端日志/解绑、VM0/0、Host健康及CPU0–1/pmthor/资源恢复通过，11份原始证据SHA一致。目录`build/lab-runs/private-heap-720-20261030-au/`；解析`private-pick-profile-au-hardware.json`、`private-phases-au.json`、`private-cache-au.json`。
- 恢复：源码按`before-private-pick-profile/`恢复并核对全部28项；诊断源保存于`pick-profile-withdrawn-sources/`。`python3 scripts/maintenance/lab-run.py --run-id private-pick-profile-restore-20261030-a -- python3 build/rmm-client-bo-20261030/restore-private-pick-profile-runtime.py`退出0，仅恢复Client Image，并核验板端Client/Proxy/initrd/runner四项AR输入；固件、Host与rootfs未改，恢复后GPU未测。

本节记录已有AU诊断测量，没有额外性能复测，不据此宣称提分。RMM保持O2 Debug/全部断言、元数据16384/物理512预算及0x2800000预留末址；ABI2/RPC4、能力2147483643、完整执行位清零。AE validation VM_BIND EBUSY、多Client/实体CPU-DMA攻击、广泛API/ML、动态OOM、并发销毁及公平性仍未验收，goal active。


## 无清零 RETIRE 的检查边界合并（AV）

AU显示多数提交时没有现成任务可合批，因此本轮先降低单任务的固定退休开销。原RETIRE无条件执行完整RETURN重查，按需清零控制页后，再做相同重查。成功任务保留组状态时，`preserve`使待清零页数为0，两个检查之间没有物理页回调、共享状态发布或引用释放。AV只在这个分支合并检查边界：仍在清理CS/CSG输入及退休历史/缓存租约前执行一次新鲜完整检查；有清零及续调用的路径仍在回调前后各检查。没有复用跨调用硬件快照，也没有把PROGRESS当作CPU完成。

改动目的｜减少无清零任务的重复退休检查｜AR541 → AV546｜+5/+0.92%｜仅RMM固件不同，Client/Proxy/Host/initrd/runner哈希一致；完整720p33场景/null-noop/finish、私有内存预算、GPU请求600实际594MHz相同，CPU未锁恒频｜下列命令/run-id/退出码/日志｜保留实验候选；单次测量不证明稳定收益。

| 测量 | AR | AV | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE操作ms/成功RMM批次 | 0.070271 | 0.069836 | -0.62% |
| READY操作ms/成功RMM批次 | 0.113205 | 0.112729 | -0.42% |
| PUBLISH操作ms/成功RMM批次 | 0.016995 | 0.017047 | +0.30% |
| START操作ms/成功RMM批次 | 0.226126 | 0.226466 | +0.15% |
| COMPLETE操作ms/成功RMM批次 | 0.423244 | 0.420662 | -0.61% |
| RETURN操作ms/成功RMM批次 | 0.138519 | 0.138723 | +0.15% |
| RETIRE操作ms/成功RMM批次 | 0.210000 | 0.197415 | -5.99% |

正式计分窗口成功退休批次：AR203809、AV205816。计时包含Guest调用、RPC/RMM与硬件响应，不是纯MMIO或纯GPU耗时；工作混合随帧数变化。窗口之前的早期历史可能不完整，不能把此表当成全程CPU占用分解。详见`private-completion-comparison-ar-av.json`，不能由模型读取减半推导帧率翻倍。

本地验证与失败记录：

- `HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-retire-boundary bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-retire-boundary.log`。完整DMA/固件模型最终命令`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`dma-private-retire-boundary-complete.log`。
- `python3 build/rmm-client-bo-20261030/check-private-retire-boundary-models.py`退出0；旧AR核心和AV核心各通过215阶段及22类×2 Client新增故障检查。保留任务的有效RETIRE读取150→75、配置检查4→2。禁用AS根/MEMATTR/TRANSCFG、固件根、shader拓扑、全局及组/子stream ACK和错误、AS别名、错误service/Client/token均被拒绝；拒绝前无清零、输入发布、MMIO写、数据维护或引用释放。移除无清零末检、移除真实清零前检、忽略末检失败三种错误副本均因语义断言退出−6；错误副本只关闭正向成本计数断言，未关闭故障语义断言。证据`retire-boundary-models/`及`private-retire-boundary-models.json`。这仍是模型证据，不证明实体隔离。
- 扩展夹具的五次失败（rc134）保留于`retire-boundary-{first,second,diagnostic,offset,shader}-failure/`及对应日志。前三次是第二Client复用全局状态时，夹具把另一个已挂起组误当成本次全局握手；后两次分别是TRANSCFG测试寄存器偏移错误和只清空shader低位。仅修正夹具：全局跳过须有该组pending位、TRANSCFG改为0x2430、shader高低位同时置零；生产改动仍仅RETIRE分支。初始trace标志猜测已在失败记录中撤回。
- `python3 build/rmm-client-bo-20261030/build-private-retire-boundary.py`及`build-private-retire-boundary-firmware.py`均退出0；23个编译参数文件与AR一致，O2 Debug/全部断言；关键静态数组地址及大小一致，末址0x2800000未扩大。固定补丁检查、ARM64/FIT/布局检查退出0。冻结`private-retire-boundary-candidate/`仅rmm.elf/rmm.img变化，RMM SHA `bccda90b51aa33e870bb7d4c0a7f61922dd05d1a64f7f71b35df6a32803819c2`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-retire-boundary-20261031-av --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-retire-boundary --run-id firmware-private-retire-boundary-20261031-av`退出0，仅SD2固件，Host/rootfs未改；`private-retire-boundary-readback-20261031-av`独占回读run退出0，实际SD字节SHA一致。证据分别在`build/firmware-runs/firmware-private-retire-boundary-20261031-av/`和对应`build/lab-runs/`。
- 硬件：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-av -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-retire-boundary-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL；完整33场景、计算、validation26-1-6、两端日志/解绑、VM0/0、Host健康、CPU0–1/pmthor及资源恢复通过，11份证据SHA一致。原始目录`build/lab-runs/private-heap-720-20261031-av/`；严格解析`private-retire-boundary-av-hardware.json`。

ABI2/RPC4、能力2147483643、完整执行位仍清零。AE validation VM_BIND EBUSY、多Client/实体CPU-DMA攻击、广泛API/ML、动态OOM、并发销毁及公平性仍未验收，goal active。本节记录已有测量，没有为文档另跑性能。


## 同次完成观察与首次停止的检查合并（AW）

AV之后，COMPLETE仍是主要固定开销之一。原流程在新STATUS ACK后读取受保护队列I/O及完成记录，再完整重查START以验证真实固件、Client根、CSG/所有stream与错误；随后成功COMPLETE立即调用首次停止函数，停止函数又获取完整配置并重做相同START重查。两次验证之间只有本地成员掩码/队列状态判断和`preserve`赋值，没有物理回调、共享输入发布或解锁。

AW将首次停止实现提取为私有`task_quiesce()`；只有COMPLETE在上述读后完整START重查成功后，才能传入本次调用栈上的固件根和可信超时配置。内部路径直接进入原有的全局/组状态复核及真实SUSPEND流程。对外`gpu_firmware_task_quiesce()`始终传入空证明，不能由RSI、Proxy或Client请求选择跳过检查。配置只复用本次已认证超时值，不将旧硬件状态保存为跨调用成功。首个SUSPEND ACK、全stream错误检查、AS FLUSH_MEM/UNMAPPED/UPDATE及实际回读、停止后完成记录复读/重查、RETURN和RETIRE均保留。

改动目的｜合并相邻COMPLETE/首次停止验证边界｜AV546 → AW553｜+7/+1.28%｜只换RMM固件；Client/Proxy/Host/initrd/runner一致，完整720p33场景/null-noop/finish、私有内存预算和GPU请求600实际594MHz相同，CPU未锁恒频｜下列run-id/命令/退出码/日志｜保留实验候选；单轮不证明稳定收益。

| 操作ms/成功RMM批次 | AV | AW | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.069836 | 0.069326 | -0.73% |
| READY | 0.112729 | 0.112752 | +0.02% |
| PUBLISH | 0.017047 | 0.017184 | +0.80% |
| START | 0.226466 | 0.226611 | +0.06% |
| COMPLETE | 0.420662 | 0.407654 | -3.09% |
| RETURN | 0.138723 | 0.138172 | -0.40% |
| RETIRE | 0.197415 | 0.195263 | -1.09% |

计分窗口退休批次：AV205816、AW208261。操作计时包括Guest/RPC/RMM和设备响应，工作混合随帧数变化；不是纯MMIO、纯GPU或完整应用CPU占比分解。早期窗口历史可能不完整。逐场景与等待比较见`private-completion-comparison-av-aw.json`；模型减少61次读取不能直接换算为帧率收益。

验证与证据：

- `HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-complete-stop bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`unit-private-complete-stop.log`。`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`dma-private-complete-stop.log`；随后补强两处外部停止/读后故障断言，最终夹具由下述旧/新核心对照再次完整覆盖。
- `python3 build/rmm-client-bo-20261030/check-private-complete-stop-models.py`退出0；AV与AW各230个阶段，新增15类×2 Client读后故障检查，原22类×2 Client RETIRE故障仍在。新故障包括Client根/属性/配置、固件根/属性、MMU/MCU状态、shader拓扑、全局配置/停止、父/子ACK、CSG归属、活跃请求与非活跃stream故障；均在发布SUSPEND/修改AS之前拒绝，且无数据缓存归还或引用释放。外部停止的MMU/根故障仍在首次发布之前拒绝。有效成功COMPLETE的读取414→353，配置检查8→6。去掉读后START证明、跳过实体AS禁用、去掉停止后复读检查三个错误副本均因语义断言退出−6。证据`complete-stop-models/`及`private-complete-stop-models.json`；模型不证明实体隔离。
- `python3 build/rmm-client-bo-20261030/build-private-complete-stop.py`和`build-private-complete-stop-firmware.py`退出0；23份编译参数与AV一致，Debug/O2/全部断言保留；固定补丁、ARM64/FIT/布局检查退出0，关键静态数组地址/大小一致，RMM末址仍0x2800000。冻结`private-complete-stop-candidate/`仅rmm.elf/rmm.img变化，RMM SHA `52caf4ccc032dd406a0c4dc10dab81482ecc03e385bcda12e60c3e7108156aea`。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-complete-stop-20261031-aw --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-complete-stop --run-id firmware-private-complete-stop-20261031-aw`退出0；独立回读run `private-complete-stop-readback-20261031-aw`退出0，两段实际SD字节SHA一致，Host内核/rootfs未改。证据`build/firmware-runs/firmware-private-complete-stop-20261031-aw/`及对应`build/lab-runs/`。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-aw -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-complete-stop-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL；计算/33场景/validation26成功、1既有数值例外、6无判据，日志回收/解绑、VM0/0、Host健康及CPU0–1/pmthor/资源恢复通过，11份证据SHA一致。严格判定`private-complete-stop-aw-hardware.json`，原始`build/lab-runs/private-heap-720-20261031-aw/`。

本轮继续标记progress，未将goal缩减为单Client跑通或局部提分。ABI2/RPC4、能力2147483643和完整执行位清零不变。AE validation VM_BIND EBUSY、多Client/实体CPU-DMA攻击、广泛API/ML、动态OOM、并发销毁与公平性仍未验收，goal active。本文记录已有测量，没有为文档另跑性能。


## 单次RMM有界归还与任务退休（AX）

AW仍由Client分别调用RETURN和RETIRE。RETURN按预算扫描真实映射、检查归属/缓存租约，在物理维护前后核验停止状态和禁用AS；返回Guest后，RETIRE再次进入RMM，重复完整硬件和已归还元数据验证。AX将成功执行后的这两个操作合为Client专用`TASK_RECLAIM`（55）：必须已有可信COMPLETE和保留原生状态标记；每次最多执行一次有界RETURN，未完整归还时只返回INCOMPLETE并持有全部引用，完整归还后才退休。

仅内部`task_retire(..., returned_checked=true)`可复用同次RETURN末尾的新鲜完整验证，期间只有私有元数据判断，不经过回调、共享输入发布或解锁。独立RETIRE总传false；真实abort清零仍使用独立RETURN/RETIRE及全部清零前后边界，新操作拒绝abort。公开ABI2/RPC4不变，增加bit31能力，完整执行位4仍清零；候选能力4294967291，Client握手强制要求新能力，缺失时拒绝，无共享数据回退。Proxy不能以自己的身份执行Client清理，也不接收新HPA、根或数据地址。

Client在真实COMPLETE后直接进入组合清理；只有typed响应精确成功才删除内核托管token并允许本地任务fence成功。错误、部分归还、超时或关闭仍保留/隔离引用，映射互斥等待到完整清理。原独立接口仍用于特权诊断及abort验证；托管任务诊断拒绝列表同步覆盖新操作。未增加跨VM RPC协议或Proxy权限。

改动目的｜减少成功完成后的RMM重入与相邻重复验证｜AW553 → AX559｜+6/+1.08%｜RMM与Client组合变化；Proxy/Host/initrd/runner、完整720p33场景/null-noop/finish、私有预算和GPU请求600/实际594MHz相同，CPU未锁恒频｜下列run-id/命令/退出码/日志｜保留实验候选；单轮不证明稳定收益。

| 操作ms/成功RMM批次 | AW | AX | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.069326 | 0.069669 | +0.49% |
| READY | 0.112752 | 0.112719 | -0.03% |
| PUBLISH | 0.017184 | 0.017229 | +0.26% |
| START | 0.226611 | 0.225705 | -0.40% |
| COMPLETE | 0.407654 | 0.408848 | +0.29% |
| RETURN + RETIRE | 0.333434 | 0.314560 | -5.66% |

计分窗口退休批次AW208261、AX210487；AX的遥测phase5保留为历史索引、没有调用且不输出该行，phase6计入整个RETURN+RETIRE，不能把phase5零值表述成没有数据归还或与旧RETIRE单独比速。计时包含Guest/RMM/硬件响应，工作混合随帧数变化，早期窗口历史可能不完整，不代表纯MMIO或CPU占比分解。旧窗口解析器的cache_operation_ms_per_task仍只加READY与旧RETURN字段，AX下遗漏组合清理，不能跨版本比较；本表按完整phase6修正。逐场景与等待见`private-completion-comparison-aw-ax.json`。

验证与证据：

- `HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-reclaim-call bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-reclaim-call.log`，含ABI一致性、105项task桥、96项submit及其余私有/RTT/heap/teardown检查。submit项数随两个CPU阶段合并而减少不可达阶段用例，仍覆盖全部可达阶段的继续/失败/关闭和映射等待；新增typed清理含前置拒绝、成功/未完成、四种损坏回复和诊断拒绝。
- `HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`最终退出0，`dma-private-reclaim-call-third.log`。新增21类×2 Client、总251阶段；2页和513页实际有界缓存回调、错误owner/service/token、完成前拒绝、旧token失效、组复用、每次未完成仍保留组/BO和故障拒绝通过。15类停止/根/配置/全stream异常在物理归还或退休之前拒绝；物理回调失败及回调后MMU/AS/stream错误不退休。
- `python3 build/rmm-client-bo-20261030/check-private-reclaim-call-models.py`退出0：旧AW+独立RETURN/RETIRE参考适配和当前各通过251阶段；普通清理读取225→150、配置验证6→4；513页375→300，调用仍为2。去掉物理缓存末检、强行把失败/部分归还改成功、允许abort进入组合清理三个错误副本均因语义断言退出−6。旧30项完成边界、44项退休故障检查仍保留。模型不证明实体隔离。
- 失败夹具保留：`dma-private-reclaim-call-first.log`（rc134：SUSPEND允许CS ACK=1，原错误注入OR1无效，改为真实fault字段）、`dma-private-reclaim-call-second.log`（rc134：误将RMM内部低层元数据退休函数视为固件硬件门禁，改为公开固件退休拒绝验证）；`submit-reclaim-call-first.log`（rc1，夹具仍按已移除的第七次worker步数测关闭，改为六步，未放宽关闭语义）。三个修正均仅夹具；生产改动的同次复用守卫同时要求completed/preserve。首次错误副本生成去掉检查后留下unused变量而编译失败，保留`reclaim-call-models-first.log`及`*-compile-failure/`，修复仅显式忽略该测试变量；已成功旧/新对照未重跑。首次硬件比较脚本仍要求七个非零阶段，但新phase5没有调用且不输出；修正仅按可达阶段断言并按RETURN+RETIRE之和比较，原始日志未改，记录`private-reclaim-call-comparison-first-failure.json`。首次freeze比较的旧28项清单缺新覆盖文件，失败发生于冻结目录创建前，改为与完整改前备份SHA比较，记录`private-reclaim-call-freeze-first-failure.json`。
- 最终ARM64 RMM构建`python3 build/rmm-client-bo-20261030/build-private-reclaim-call.py`退出0，23份编译参数与AW一致，O2 Debug/全部断言；Client `make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j4 Image`退出0，`client-private-reclaim-call.log`。固定补丁、FIT/含BSS布局、关键静态数组地址/大小检查通过，末址0x2800000不扩大。冻结`private-reclaim-call-candidate/`仅client-Image/rmm.elf/rmm.img变化，RMM SHA `8179c200a1b37ba108e961f11fc70c36623ac17842c02add26cee680cd94b7e3`。
- SD2部署`python3 scripts/maintenance/lab-run.py --run-id firmware-private-reclaim-call-20261031-ax --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-reclaim-call --run-id firmware-private-reclaim-call-20261031-ax`退出0；独立回读run `private-reclaim-call-readback-20261031-ax`退出0，实际SD两个区段SHA一致；Host内核/rootfs未改。证据`build/firmware-runs/firmware-private-reclaim-call-20261031-ax/`及对应`build/lab-runs/`。
- 完整720p `python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ax -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-reclaim-call-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL；计算/33场景/validation26成功、1既有数值例外、6无判据、两端日志/解绑、VM0/0、Host健康与CPU0–1/pmthor/资源恢复通过，11份证据SHA一致。严格判定`private-reclaim-call-ax-hardware.json`；原始`build/lab-runs/private-heap-720-20261031-ax/`。

本轮为progress；AE validation VM_BIND EBUSY、多Client、实体CPU/DMA攻击、广泛API/ML、动态OOM和并发销毁/公平性仍未验收，不由正常单Client任务通过推导机密性。goal active，本文记录已有测量，没有为文档另跑性能。


## RMM内部阶段与底层回调耗时诊断（AY / AZ，已恢复AX）

本轮只回答“单任务时间花在RMM哪一层”，没有实现新的性能优化。临时修改RSI适配器`runtime/rsi/opencca_gpu_private.c`，按PREPARE、READY、PUBLISH、START、COMPLETE、HEAP、RECLAIM及OTHER累计调用次数、总ticks和最大ticks；底层分别计时CONFIG、NOTIFY、PREPARE_AS、DETACH_AS、READ_CONTROL、WRITE_CONTROL、CLEAN和INVALIDATE。总时间在取得policy lock后开始、输出报告前结束，不含锁等待、完整SMC切换和诊断日志输出；包含计数本身的扰动。使用24MHz架构计数器，每32768次成功退休输出累计快照，新增静态计数约1740字节。任务授权、真实PTE/根/全部stream检查、物理缓存交接与完成/回收条件未改。

改动目的｜定位RMM阶段和回调耗时｜AX559 → AY560 / AZ558｜分别+1/+0.18%、−1/−0.18%｜仅RMM临时诊断固件变化，Client/Proxy/Host/initrd/runner与AX相同；完整720p33场景/null-noop/finish、私有预算和GPU请求600/实际594MHz相同，CPU未锁恒频。AZ额外在每条统计输出前等待2ms以缓解串口突发丢字，影响Client延迟且不计入阶段时间；两轮均不能作为性能优化候选｜下列命令、run-id、退出码和日志｜诊断源已移出运行路径，源码和板端SD2恢复AX559。

AY完整工作负载通过，但连续输出发生缺字和拼接，数值完整性校验拒绝其计时结果，保留`private-rmm-profile-ay-analysis-failure.json`及原UART，不使用其数值。AZ改用短行`RGPC phase metric calls ticks max`和间隔输出。解析器对每条计时记录做整行匹配，逐快照检查唯一性、必要指标、总量/子项、累计单调性以及退休次数；任何损坏导致整份快照拒绝，不从邻近快照补值。

AZ共有六个累计快照：32768、65536、98304、131072、163840、196608。前四个各42条，第五个44条（发生HEAP扩容，新增NOTIFY/CLEAN非零指标），均完整。最后快照有两条OTHER记录拼接，整份排除，不能使用其截断最大值，也不采用其中仍完整的其他阶段。以下采用第五个累计快照，覆盖初始化至163840次成功退休，包含该范围内预热及其他操作，不代表完整计分窗口或纯应用CPU占比。

| RMM阶段 | 调用次数 | 平均μs/调用 | 累计μs/退休批次 | 已计时回调占该阶段 |
| --- | ---: | ---: | ---: | ---: |
| PREPARE | 163840 | 23.317 | 23.317 | 67.70% |
| READY | 177648 | 103.901 | 112.657 | 5.84% |
| PUBLISH | 163840 | 15.831 | 15.831 | 76.74% |
| START | 163840 | 178.530 | 178.530 | 17.28% |
| COMPLETE | 567467 | 98.584 | 341.449 | 33.61% |
| HEAP | 403628 | 19.736 | 48.622 | 26.47% |
| RECLAIM | 177648 | 131.840 | 142.951 | 11.96% |
| OTHER | 505219 | 43.410 | 133.860 | 0.24% |

COMPLETE会反复查询，故98.584μs/调用与341.449μs/退休批次是不同量；READY和RECLAIM也可能分多次完成。RECLAIM包含真实RETURN与RETIRE，不能与旧版单独RETIRE直接比较。OTHER混合注册、映射等不同操作，摊到退休批次仅描述本次累计工作量。

这轮证据支持的结论：READY/RECLAIM的大部分耗时不在这八类回调中，START与COMPLETE亦有明显未分类时间。未分类部分还包括核心循环、对象定位、PTE读取、状态检查和固件等待等，不能全部称为授权扫描、页表遍历或纯MMIO。也不能将Client phase6与RMM RECLAIM相减后称为SMC开销：Client阶段还包含run_finish/fence发布及可能的调度，两者统计范围不同。后续可进一步分段定位，再评估同锁连续PTE检查的批量处理和固定生命周期边界；本轮没有实施这些候选，也不宣称新增提速。

验证、命令与证据（本节文件名未加目录者均位于`build/rmm-client-bo-20261030/`）：

- 本地私有回归：`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-rmm-profile bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-rmm-profile.log`；DMA/固件模型`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`dma-private-rmm-profile.log`，保留251阶段及42个TASK_RECLAIM检查。固定补丁检查`python3 opencca/scripts/setup/apply-local-patches.py --check`退出0，`patch-private-rmm-profile.log`。AZ只改变报告格式及间隔，复用AY的策略回归，没有重复运行。模型通过不证明实体隔离。
- 构建：`python3 build/rmm-client-bo-20261030/build-private-rmm-profile.py`、`build-private-rmm-profile-firmware.py`以及对应`build-private-rmm-profile-paced.py`、`build-private-rmm-profile-paced-firmware.py`均退出0，命令和日志见`private-rmm-profile{,-paced}-build-validation.json`、`uboot-rmm-profile{,-paced}-commands.json`；两版23份编译参数与AX一致，O2 Debug/全部断言保留，FIT/含BSS布局检查通过，RMM预留末址仍0x2800000。AY RMM SHA `5b0d096db8bb6fbcfbd8506c7ff9ddafc5d31f9273861b1b654c9f1c92d720e8`，AZ `661298c8061699f03b6941d1b5556dc2e6448fbcfbd2e4d3b03ac7e2b81bc7ff`；冻结目录分别`private-rmm-profile-candidate/`与`private-rmm-profile-paced-candidate/`。
- 部署均用`python3 scripts/maintenance/lab-run.py --run-id <部署ID> --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware <固件目录> --run-id <部署ID>`。AY部署ID `firmware-private-rmm-profile-20261031-ay`，固件`build/rmm-client-bo-20261030/firmware-private-rmm-profile`；AZ为`firmware-private-rmm-profile-paced-20261031-az`及`firmware-private-rmm-profile-paced`。两次退出0，实际SD2独立回读run分别`private-rmm-profile-readback-20261031-ay`、`private-rmm-profile-paced-readback-20261031-az`，退出0。证据位于对应`build/firmware-runs/`与`build/lab-runs/`，不更新健康Host内核/rootfs。
- 完整720p均用`python3 scripts/maintenance/lab-run.py --run-id <测量ID> -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images <冻结目录> --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。AY测量ID `private-heap-720-20261031-ay`，AZ `private-heap-720-20261031-az`；各自`result.json`保存精确展开命令。两轮外层退出1，原因均为1000门槛FAIL；工作负载退出0，计算/完整33场景/validation26-1-6、两端日志/解绑、VM0/0、Host健康与CPU0–1/pmthor/资源恢复通过，每轮11份原始证据SHA一致。完整原始日志位于对应`build/lab-runs/<测量ID>/`。
- 分析：AY首次`python3 build/rmm-client-bo-20261030/analyze-private-rmm-profile.py ay`退出1，因UART数值损坏保留拒绝；没有重跑AY。修正逐快照拒绝后，`python3 build/rmm-client-bo-20261030/analyze-private-rmm-profile.py az`退出0，`private-rmm-profile-az-analysis.log`；工作负载判定、原始六快照、五份接受记录、拒绝原因与回调明细分别保存在`private-rmm-profile-{ay,az}-workload.json`和`private-rmm-profile-az-hardware.json`。
- 恢复：`python3 build/rmm-client-bo-20261030/restore-private-rmm-profile-source.py`退出0，核对AX全部32项源码SHA；两份诊断源码保存在`rmm-profile-first-sources/`、`rmm-profile-diagnostic-sources/`。使用上述部署入口、AX固件`build/rmm-client-bo-20261030/firmware-private-reclaim-call`，恢复ID `firmware-private-rmm-profile-restore-20261031-ax`，退出0；`python3 scripts/maintenance/lab-run.py --run-id private-rmm-profile-restore-readback-20261031-ax -- python3 build/rmm-client-bo-20261030/verify-private-rmm-profile-restored.py`退出0，核验实际SD2两个区段与板端Client/Proxy/initrd/runner，记录`private-rmm-profile-restored-readback.json`和`private-rmm-profile-source-restored.json`。恢复后GPU未新增测量，保留559为原AX实测。

首次封存脚本误将AX源码清单项数写为33，实际为32，断言在写入manifest和状态前失败；仅修正项数，保留`private-rmm-profile-checkpoint-first-failure.json`，不重跑硬件或模型。生成的本地backend测试程序因本轮重新编译而改变SHA，作为模型产物单独登记，不代表Host/Guest运行镜像变化。当前仍使用AX冻结输入与RMM，ABI2/RPC4、能力4294967291及完整执行位清零不变。本轮有上述两次诊断测量；之后仅整理文档和证据，未改运行代码，无新增性能测量。1000门槛、AE validation VM_BIND EBUSY、多Client、实体CPU/DMA攻击、广泛API/ML、动态OOM和并发销毁/公平性仍未验收，goal active。



## 同锁连续实际叶项的四项批量检查（BA）

AY/AZ提示READY/RECLAIM的大部分时间尚未细分，并不能直接证明哪一个循环是瓶颈。本轮选取不改变检查语义的局部试验：当上一项已经核验了NC/驻留BO的归属、生命周期与缓存租约，且后续没有物理回调时，在同一policy lock内一次读取四个真实leaf tag和PTE。只有四个tag均等于已核验BO、四个实际PTE均包含原本要求的描述符/AF/USER位，才一次推进四项。用四个PTE的按位AND合并必需位判定，不缓存PTE、不依赖Client提示，也不将摘要代替真实页表。

任一tag或PTE不匹配时回到原逐项处理，保留第一个错误的准确cursor、错误状态与隔离引用；control/WB页沿用原路径。批次不跨32项可信叶组边界，也不超过剩余元数据预算；每项仍扣除一个扫描单位。物理缓存回调清除已核验BO标记，下一项重新检查表/组和BO。真实页表/归属检查、NC最终屏障、512页物理维护预算、16384项元数据预算、硬件根/全部stream前后检查及完成/回收条件保留。没有新增静态索引或数组，没有跨调用复用检查成功。

改动目的｜减少连续NC/驻留页逐项循环开销｜AX559 → BA586｜+27/+4.83%｜仅RMM固件变化，Client/Proxy/Host/initrd/runner哈希与AX相同；完整720p33场景/null-noop/finish、私有预算及GPU请求600/实际594MHz相同，CPU未锁恒频｜下列命令、run-id、退出码与日志｜保留实验候选，单轮不证明稳定收益。

| 操作ms/成功RMM批次 | AX | BA | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.069669 | 0.069231 | -0.63% |
| READY | 0.112719 | 0.079460 | -29.51% |
| PUBLISH | 0.017229 | 0.017078 | -0.87% |
| START | 0.225705 | 0.225718 | +0.01% |
| COMPLETE | 0.408848 | 0.406738 | -0.52% |
| RETURN + RETIRE | 0.314560 | 0.278655 | -11.41% |

计分窗口退休批次AX210487、BA221264。phase6包括完整RETURN+RETIRE，phase5保留不用，不能将新phase6与旧单独RETIRE比速。这里是Client调用的累计墙钟时间，包含Guest/RMM/硬件响应，不是纯扫描或CPU占比；工作混合随帧数变化，早期窗口历史可能不完整。本轮没有启用AY/AZ临时RMM计时器或串口间隔输出；不将不同统计范围相减后解释为SMC成本。

验证与证据（本节未加目录的文件均位于`build/rmm-client-bo-20261030/`）：

- `HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/unit-leaf-batch bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-private-leaf-batch.log`，原私有/RTT/heap/submit/teardown检查及新增320组检查通过。`HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`dma-private-leaf-batch.log`，保留251阶段和42组TASK_RECLAIM检查。固定补丁检查退出0，`patch-private-leaf-batch.log`。
- `python3 build/rmm-client-bo-20261030/check-private-leaf-batch-models.py`退出0，`leaf-batch-models.log`：真实AX与BA核心各21组预算/回调边界、8组固定负载、320组精确首错cursor检查，共698次正向运行。新检查在READY/RETURN两方向覆盖连续32个位置，分别损坏AF、USER、描述符位、tag范围或换为已关闭BO；跨批内四个位置及32项组边界。遗漏第三个PTE、遗漏第四个tag、漏扣批量预算和让BO证明跨物理回调复用的四个错误副本均因语义断言退出−6。证据`leaf-batch-models/`、`private-leaf-batch-models.json`。这些是模型结果，不能证明实体隔离。
- `python3 build/rmm-client-bo-20261030/build-private-leaf-batch.py`和`build-private-leaf-batch-firmware.py`退出0；23份编译参数与AX一致，O2 Debug/全部断言保留。ARM64反汇编`private-leaf-batch-arm64.disassembly`保留实际四个PTE读取和标量回退。FIT/含BSS布局通过，预留末址0x2800000不扩大。14个关键静态数组实例的地址及大小与AX一致，见`private-leaf-batch-static-layout.json`。初次布局夹具误要求nm同名local符号唯一，两个翻译单元均有tables/table_owner，断言失败；freeze因缺布局记录在创建冻结目录前拒绝。修正为比较全部实例，未放宽布局条件，失败保留`private-leaf-batch-layout-first-failure.json`。
- 冻结`private-leaf-batch-candidate/`只变rmm.elf/rmm.img，RMM SHA `1aa389816644b184e6398a6f64a82595c5d452b42f315a08c2b7a3e2a13ce9c5`；固件`firmware-private-leaf-batch/`。部署`python3 scripts/maintenance/lab-run.py --run-id firmware-private-leaf-batch-20261031-ba --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-leaf-batch --run-id firmware-private-leaf-batch-20261031-ba`退出0。独立SD2回读run `private-leaf-batch-readback-20261031-ba`退出0，实际字节SHA一致，记录`private-leaf-batch-sd-readback.json`；健康Host内核/rootfs未改。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ba -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-leaf-batch-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL；完整33场景、计算、validation26成功/1既有数值例外/6无判据、两端日志/解绑、VM0/0、Host健康与CPU0–1/pmthor/资源恢复通过，11份原始证据SHA一致。原始`build/lab-runs/private-heap-720-20261031-ba/`；严格分析`private-leaf-batch-ba-hardware.json`，阶段/逐场景比较`private-completion-comparison-ax-ba.json`。

封存首次因未分类的生成产物漂移拒绝继续，保留`private-leaf-batch-checkpoint-first-failure.json`。完整漂移审计确认仅有本轮核心/测试入口、两份文档，以及全套回归重新编译的heap-test、reclaim-test和backend三个模型程序；后者不是Host/Guest运行镜像，逐项登记新SHA，见`private-leaf-batch-precheckpoint-drift.json`。没有重跑已通过的模型或硬件。

本轮为progress，完整目标未完成。ABI2/RPC4、能力4294967291与完整执行位清零不变。AE validation VM_BIND EBUSY、多Client、实体CPU/DMA攻击、广泛API/ML、动态OOM及并发销毁/公平性仍未验收。本文记录上述测量，之后仅整理证据和文档，无额外GPU性能测量。


## 一次RMM调用完成有界READY与首次PUBLISH（BB）

本轮把Client原来的两个相邻工作阶段合为一次RMM调用：页面准备完成后，在同一policy lock内调用原首次PUBLISH逻辑。新增Client专用`TASK_READY_PUBLISH=56`，能力bit32（`4294967296ULL`）；Client能力要求改为u64，必须协商该位。ABI2/RPC4不变，完整执行能力位4仍清零。正常流程为Proxy PREPARE → Client READY_PUBLISH → Proxy START → Client真实COMPLETE → RETURN+RETIRE；每个任务仍经过Proxy。

只允许初次尚未发布的deferred任务：实际Client/token/服务认证、成员数、尚无START/STOP尝试、未完成/未归还等条件全部检查。每次最多原本一批READY准备；INCOMPLETE不改任何INSERT，不启动GPU，也不延长原截止时间。完全就绪后，由RMM私有成员数生成完整mask，继续原PUBLISH的真实配置/AS/队列cursor/ACK检查及发布后的重查。任意失败都不能沿用READY成功；部分发布仍隔离保留，成功后禁止重放组合操作。后续START仍由Proxy请求并由RMM检查，发布本身不证明完成或允许回收。

保留独立READY/PUBLISH用于显式依赖前缀及诊断验证；普通Client worker不再走旧PUBLISH阶段。遥测phase1现在包括READY+PUBLISH，phase2保留编号且不产生记录；phase6仍包含RETURN+RETIRE。没有减少真实PTE/归属扫描、物理缓存维护、实际根/全部stream、可信完成或安全回收检查，没有新增静态表或跨调用授权证明。

改动目的｜省去一次RMM往返及一次Client worker交接｜BA586 → BB587｜+1/+0.17%｜RMM固件与Client Image变化，Proxy/Host/initrd/runner哈希相同；同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz，CPU未锁恒频；元数据16384/物理512预算保留｜下列run-id、命令、退出码及日志｜保留实验候选，单轮不证明稳定收益。

| 操作ms/成功RMM批次 | BA | BB | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.069231 | 0.069552 | +0.46% |
| READY + 首次PUBLISH | 0.096538 | 0.095454 | -1.12% |
| START | 0.225718 | 0.225055 | -0.29% |
| COMPLETE | 0.406738 | 0.407268 | +0.13% |
| RETURN + RETIRE | 0.278655 | 0.279536 | +0.32% |

BA phase1+phase2与BB phase1合并比较，不能把BB没有phase2直接当作该阶段全部开销消失。退休批次BA221264、BB221489；累计墙钟时间包含Guest/RMM/硬件响应，工作混合随帧数变化且早期窗口可能缺失，不能解释为纯SMC成本或稳定收益。逐场景比较保留在`private-completion-comparison-ba-bb.json`。

验证与证据（省略目录的文件均在`build/rmm-client-bo-20261030/`）：

- `HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/unit-ready-publish bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-ready-publish.log`；包含ABI对齐、typed接口、submit/heap/回收/teardown等。`HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`修正测试夹具后退出0，`dma-ready-publish-second.log`，后端269阶段及原42组RECLAIM保留。
- `python3 build/rmm-client-bo-20261030/check-private-ready-publish-models.py`退出0，`ready-publish-models.log`。BA原READY→PUBLISH顺序参考与BB的18组结果一致，覆盖3/6成员、513页两次有界准备、未PREPARE、错误服务/Client/token、legacy及部分已发布任务、缓存/根/ACK/cursor/第一或第二INSERT写入失败、启动后及成功后拒绝重放。提前发布未完整准备、只发布首成员、吞掉发布失败、允许成功重放四个错误副本均断言退出−6。复用已成功的精确BB后端结果，未重复执行。模型通过不能证明实体隔离。
- 夹具失败保留：首轮typed测试使用旧数组下标分界，新增op后把任务当组句柄；后端夹具在BO完整登记前尝试MAP，被产品正确拒绝。另一次新夹具错误要求累计页面遥测增量也必须触发协议错误；该数值不构成完成授权。修正夹具后通过，未放宽产品授权。全部命令/退出码/日志见`private-ready-publish-local-checks.json`。 封存首次因审计白名单使用绝对路径、manifest使用相对路径而拒绝已登记的Client构建产物；统一路径后重新封存，首次失败保留`private-ready-publish-checkpoint-first-failure.json`，未重跑GPU。 独立审计又捕获封存程序将自身尚未结束的stdout日志按空文件登记；待命令结束后修正该日志哈希并重新完整审计，运行代码与测试结果均未变化，记录`private-ready-publish-self-log-failure.json`。
- `build-private-ready-publish.py`、`build-private-ready-publish-firmware.py`与Client Image构建退出0；23份flags与BA一致，O2 Debug/全部断言、14个静态数组实例地址/大小及RMM末址0x2800000不变。FIT/含BSS布局与固定补丁检查通过。11份源码差异见`private-ready-publish-review/`；冻结包`private-ready-publish-candidate/`配`firmware-private-ready-publish/`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-ready-publish-20261031-bb --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-ready-publish --run-id firmware-private-ready-publish-20261031-bb`退出0，只写SD2固件，未刷Host内核/rootfs。`private-ready-publish-readback-20261031-bb`通过同一wrapper执行`verify-private-ready-publish-sd.py`，退出0，实际两段启动字节SHA一致。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bb -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-ready-publish-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，日志`build/lab-runs/private-heap-720-20261031-bb/`。完整33场景、COMPUTE_CHECK、validation26/1/6、两端日志/解绑、VM0/0、Host健康与资源恢复、11份证据SHA通过；1000门槛FAIL。实际结果见`private-ready-publish-bb-hardware.json`。

当前保留587分。AE VM_BIND EBUSY、多Client、实体越权/恶意Proxy、动态OOM与并发销毁/公平性等仍未验收；本轮不继承历史PASS，整体goal未完成。


## 按实际字段读取stream状态（BC）

START、停止/重查和完成观察原先在每条stream上反复复制216字节输出，而实际只使用ACK、scoreboard、blocked reason、fault、fatal五个32位字段。BC将七处整块复制替换为每次新鲜读取的局部状态结构，最多读取20字节；使用固定大小`__builtin_memcpy`避免freestanding环境的额外函数调用，并不假定源地址对齐。实际ARM64反汇编确认七处216字节memcpy均消除。固定ARM64配置下helper以`stream_status.isra.0`存在，因严格对齐采用20次字节读取/写入，不应误称为五条32位加载。

每处仍先对完整216字节执行原invalidate，不缩小缓存维护，不缓存跨调用状态；真实根/全部stream/ACK/OOM/错误、等待状态、队列位置与序号、STATUS_UPDATE与SUSPEND握手、AS禁用及安全回收检查保留。heap输出需要其他字段，仍走原完整快照。没有新增静态数组或授权证明。

改动目的｜减少CPU读取和栈上复制｜BB587 → BC591｜+4/+0.68%｜仅RMM固件变化，Client/Proxy/Host/initrd/runner哈希相同；完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频，元数据16384/物理512预算不变｜下列命令、run-id和日志｜保留实验候选，单轮不证明稳定收益。

| 操作ms/成功RMM批次 | BB | BC | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.069552 | 0.069617 | +0.09% |
| READY + 首次PUBLISH | 0.095454 | 0.096032 | +0.61% |
| START | 0.225055 | 0.217646 | -3.29% |
| COMPLETE | 0.407268 | 0.373181 | -8.37% |
| RETURN + RETIRE | 0.279536 | 0.272499 | -2.52% |

成功退休批次BB221489、BC223181。两轮phase1均为READY+PUBLISH、没有phase2，phase6均为RETURN+RETIRE；墙钟包括Guest/RMM/硬件响应，不能解释为纯CPU或SMC成本。早期计数窗口可能缺失，帧数使工作混合不同，单轮分差不能证明稳定提速。逐场景结果见`private-completion-comparison-bb-bc.json`。

验证与证据（文件默认位于`build/rmm-client-bo-20261030/`）：

- `HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/unit-stream-status bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-stream-status.log`；完整私有内存/接口/heap/回收/teardown模型。`HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`dma-stream-status.log`。
- `python3 build/rmm-client-bo-20261030/check-private-stream-status-models.py`退出0，`stream-status-models.log`；BB原实现与BC同一270阶段后端的PASS结果逐项一致，保留18组READY_PUBLISH、42组RECLAIM，新补仅fatal异常时拒绝START。分别漏读五字段及缩小invalidate到局部结构的六个错误副本都被断言拒绝（−6）。这是模型证据，不是实体隔离证明。
- O2 Debug/全部断言和23份flags与BB一致，14个关键静态数组实例地址/大小一致，FIT与含BSS布局检查通过，RMM预留末址仍0x2800000。`private-stream-status-assembly.json`记录七处复制消除，`private-stream-status-review/`保存两份源码差异。能力8589934587、ABI2/RPC4、完整执行位清零不变。
- 固件部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-stream-status-20261031-bc --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-stream-status --run-id firmware-private-stream-status-20261031-bc`退出0，仅SD2固件。`private-stream-status-readback-20261031-bc`由同一wrapper执行`verify-private-stream-status-sd.py`退出0，两段实际SD启动字节SHA一致。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bc -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-stream-status-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，日志`build/lab-runs/private-heap-720-20261031-bc/`。完整33场景、COMPUTE_CHECK、validation26/1/6、两端日志/解绑、VM0/0、Host健康、资源恢复及11份证据SHA通过；1000门槛FAIL。

当前保留591分，AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM与并发销毁/公平性仍未验收，整体goal未完成。


## 利用已验证对齐读取完整固件接口快照（BD）

固件接口启动发现时，`iface_range()`已经验证每个接口从64字节缓存行边界开始，私有`runtime_pages`本身按4096字节对齐；发现完成后只保留RMM私有接口偏移，任务路径不跟随Proxy提供的实时指针。BD把由此已成立的4字节对齐事实传给编译器：START、STOP/重查和完成观察的28处固定完整快照以32位字循环复制，stream状态五个字段使用五次32位读取，替代BC的20次字节读取。使用逐字`__builtin_memcpy`保留按字节对象表示复制的语义，不依赖把字符数组强制转换为整数数组的别名假设。

所有原字节范围仍完整复制；原invalidate/clean范围、屏障和调用顺序均不变。配置/根/全部stream/ACK/错误、STATUS_UPDATE、SUSPEND、实际PTE/物理缓存及归还/回收检查保留；没有跨调用快照复用。只优化已认证接口的私有读取，通用libc、发现解析、共享写入、heap完整输出和RSI整页读取路径均不改。编译器优化只改变访问宽度，不替代边界、对齐或归属检查。

改动目的｜降低可信固件接口快照的逐字节复制开销｜BC591 → BD592｜+1/+0.17%｜仅RMM固件变化，Client/Proxy/Host/initrd/runner哈希相同；同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频、元数据16384/物理512预算｜下列run-id/命令/退出码/日志｜保留实验候选，单轮不证明稳定收益。

| 操作ms/成功RMM批次 | BC | BD | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.069617 | 0.069905 | +0.41% |
| READY + 首次PUBLISH | 0.096032 | 0.095842 | -0.20% |
| START | 0.217646 | 0.214097 | -1.63% |
| COMPLETE | 0.373181 | 0.357907 | -4.09% |
| RETURN + RETIRE | 0.272499 | 0.269044 | -1.27% |

退休批次BC223181、BD223528。两轮phase1均为READY+PUBLISH、phase6均为RETURN+RETIRE，计时包括Guest/RMM/硬件响应；早期窗口可能缺失，工作混合随帧数不同。不能将单轮墙钟变化解释为纯CPU收益或稳定提升，逐场景对照保留在`private-completion-comparison-bc-bd.json`。

结果限制：COMPLETE操作时间虽然降低，重试/轮询间隔增加；操作与间隔之和为0.568737→0.575351 ms/退休批次（+1.16%），不能表述成完成端到端延迟下降。COMPLETE调用数/退休批次为3.731→3.938。33场景帧时变化中位数为-0.87%，最明显变慢的`[effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;:`为4.310→7.986 ms（+85.29%）。该场景退化原因未定位；总分微小差异不抵消这一局限，也不证明28处复制优化有稳定整体收益。

验证与证据（文件默认位于`build/rmm-client-bo-20261030/`）：

- 最终源码：`HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/unit-aligned-snapshot-final bash scripts/check/check-rmm-gpu-private.sh`退出0，`unit-aligned-snapshot-final.log`；`HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`dma-aligned-snapshot-final.log`。新旧核心同270阶段后端PASS逐项一致，18组READY_PUBLISH及42组RECLAIM保留。新增全局/组/stream输入输出共六种地址错一字节，全部在配置前拒绝；原BC也通过同一新夹具。
- `check-private-aligned-snapshot-models.py`退出0，`aligned-snapshot-models.log`：轮转接口快照中的字、放行未对齐接口两个错误副本断言拒绝（−6）。局部模型通过不证明实体恶意Proxy隔离。
- 首版对齐builtin仍将9处大快照交给通用memcpy，反汇编期望28处消除的检查退出1；在部署前改为逐字固定大小builtin，最终实际消除28次调用。首版源码/ELF/日志、未部署固件与原因保存在`aligned-snapshot-first-build/`、`firmware-private-aligned-snapshot-first/`；不是硬件测量或额外收益。最终汇编证据`private-aligned-snapshot-assembly.json`，五次32位状态读取及完整216字节invalidate均已检查。
- 最终O2 Debug/全部断言、23份flags与BC相同，14个关键静态数组地址/大小相同；FIT/含BSS布局通过，预留末址仍0x2800000。能力8589934587、ABI2/RPC4、完整执行位清零不变。两份源码差异见`private-aligned-snapshot-review/`。
- 固件：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-aligned-snapshot-20261031-bd --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-aligned-snapshot --run-id firmware-private-aligned-snapshot-20261031-bd`退出0，仅SD2；`private-aligned-snapshot-readback-20261031-bd`经同一wrapper执行`verify-private-aligned-snapshot-sd.py`退出0，实际SD启动字节SHA一致。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bd -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-aligned-snapshot-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，日志`build/lab-runs/private-heap-720-20261031-bd/`。完整33场景、COMPUTE_CHECK、validation26/1/6、两端日志/解绑、VM0/0、Host健康/资源恢复及11份证据SHA通过，1000门槛FAIL。

当前保留592分。AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM和并发销毁/公平性仍未验收，整体goal未完成。


## Proxy 一次性选择与 Client 就绪启动合并（BE）

原来每批任务需要两次 Client→Proxy RPC：先由 Proxy 请求 RMM 准备硬件上下文，Client 完成缓存交接及首次发布后，再找 Proxy 请求 START。BE 将启动决定前移到第一次 RPC：Proxy 通过 `PREPARE_LAUNCH` 选择精确的 Client/context/group/token，RMM 完成原有 PREPARE 后保存一次性启动许可。Client 随后调用 `READY_LAUNCH`，只有全部缓存交接完成且完整 PUBLISH 检查成功，RMM 才消费许可并执行原有完整 START。无需第二次 START RPC，也省去对应的一次 Client worker 阶段。

许可是 RMM 私有任务状态，复用结构原有填充空间。Proxy 不能凭许可读取业务数据；Client 不能自行授予、扩大或重放许可。INCOMPLETE 只推进有界缓存游标，不发布或启动；异常结果取消许可，START 失败或状态不确定不重放，backing 继续保留。服务显式中止尚未启动任务时撤销许可并隔离组，不把中止当成已停止或可回收。配置/真实根/全 stream/ACK/错误、完成观察、SUSPEND、实际 PTE、缓存归还和退休检查均保留。诊断用显式 PREPARE/PUBLISH/START 仍有实际测试调用者；普通 Client 路径不再进入独立 PUBLISH/START 阶段。

改动目的｜减少每批任务一次跨 VM 启动请求与 worker 交接｜BD592 → BE611｜+19/+3.21%｜RMM 与 Client/Proxy Image 同时变化，只归因组合效果；Host/initrd/runner 相同，同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频，元数据16384/物理512预算｜下列命令/run-id/退出码/日志｜保留实验候选，单轮不证明稳定收益。

| 操作 ms/成功退休批次 | BD | BE | 变化 |
| --- | ---: | ---: | ---: |
| Proxy PREPARE | 0.069905 | 0.070921 | +1.45% |
| READY + PUBLISH + START | 0.309940 | 0.266351 | -14.06% |
| COMPLETE | 0.357907 | 0.356858 | -0.29% |
| RETURN + RETIRE | 0.269044 | 0.268145 | -0.33% |

BD 的 phase1（READY+PUBLISH）与 phase3（START）合并后，才与 BE 的 phase1（READY_LAUNCH）比较，不能把移入 READY 的 START 时间当成消失。计时包括 Guest/RMM/硬件响应，工作混合和退休批次数可不同，部分早期计数历史可能缺失，不能解释为纯 CPU 时间或稳定单任务延迟。完整逐场景结果见 `private-completion-comparison-bd-be.json`。

验证和证据（相对 `build/rmm-client-bo-20261030/`）：

- `HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/unit-ready-launch bash scripts/check/check-rmm-gpu-private.sh` 退出0，`unit-ready-launch.log`；`HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh` 最终退出0，`dma-ready-launch-final3.log`。Client 提交模型91项、跨 VM 任务桥接及完整私有/DMA模型通过。原270阶段后端用例保持一致，新增24项 READY_LAUNCH（总294阶段），覆盖身份/上下文/token、513页续调用、ACK/根/缓存错误、重复启动、中止及完整完成回收。
- `python3 build/rmm-client-bo-20261030/check-private-ready-launch-models.py` 退出0，`ready-launch-models.log`。四个错误副本分别绕过许可、在INCOMPLETE启动、忽略START失败、忽略服务中止，均由断言拒绝（−6），不代表实体攻击隔离已验收。早期夹具未适配新增action、ACK和缓存计数及成功回收后状态，失败版本与退出134记录保留于 `ready-launch-*-model-failure/`；生产授权/完成条件未为通过夹具而削弱。
- RMM 和两端内核构建退出0（`rmm-private-ready-launch.log`、`client-private-ready-launch-final.log`、`proxy-private-ready-launch-final.log`）；O2 Debug/全部断言与BD相同，23份flags、14个静态数组地址/大小及0x2800000预留不变，FIT/布局通过。新增op57/58、能力bit33，经u64协商；ABI2/RPC4，完整执行能力位仍清零。新Client要求Proxy广告独立READY_LAUNCH特性，不静默降级。
- 固件部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-ready-launch-20261031-be --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-ready-launch --run-id firmware-private-ready-launch-20261031-be` 退出0，仅SD2；`private-ready-launch-readback-20261031-be` 经同一wrapper运行 `verify-private-ready-launch-sd.py` 退出0，实际启动区字节一致。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-be -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-ready-launch-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1` 退出1，`build/lab-runs/private-heap-720-20261031-be/`。计算、完整33场景、validation26/1/6（含已知失败）、VM0/0、两端日志/解绑、Host健康/资源及11份SHA检查通过；1000门槛FAIL。启动前可选IOCTL冒烟的SYNCOBJ_EVENTFD返回ENOENT而非预期EOPNOTSUPP，记录optional rc=1；本轮不能称全部API通过。

当前保留611分，仍属实验候选。AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性尚未验收，整体目标未完成。


## Client 完成检查、CPU 归还与退休合并（BF）

BE中，GPU任务结束后Client先调用COMPLETE确认真实完成，再经另一个worker阶段调用RECLAIM做CPU缓存归还和退休。BF新增Client独占的`TASK_FINISH`（op59、能力bit34），在同一个RMM策略锁内完成这三步，省去独立RECLAIM入口和worker交接。首次RETURN仅复用紧邻COMPLETE末尾已经成功的完整停止检查，中间只有私有元数据操作，没有回调、共享发布或解锁；归还后仍完整检查实际停止/全stream/根/禁用AS。后续批次重新进入RMM时必须独立检查，不保留跨调用的硬件状态证明。

返回值区分两种INCOMPLETE：`[0,queue,0,0]`表示GPU仍未完成，Client继续原有堆事件服务和有界观察；`[0,queue,0,1]`表示GPU已完成但有界CPU归还未结束，Client立即安排下一份工作，释放mutex并保留原绝对期限。只有`[1,queue,0,0]`才代表精确token已经退休，typed接口删除本地托管token后才signal应用fence。Proxy回复、计时或中间完成状态均不构成成功证明。缓存回调失败直接隔离并保留引用；成功及INCOMPLETE缓存工作之后保留完整硬件末检。显式COMPLETE/RETURN/RECLAIM/RETIRE保留实际诊断、中止测试调用者。旧阶段枚举只保留日志编号含义，正常路径不再进入独立RETURN/RETIRE。

改动目的｜减少任务结束时一次RMM入口、worker交接和紧邻的重复停止检查｜BE611 → BF620｜+9/+1.47%｜RMM和两端Guest Image同时变化，只归因组合效果；Host/initrd/runner不变，同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频、元数据16384/物理512预算｜下列命令/run-id/退出码/日志｜保留实验候选，单轮不证明稳定收益。

| 操作 ms/成功退休批次 | BE | BF | 变化 |
| --- | ---: | ---: | ---: |
| Proxy PREPARE | 0.070921 | 0.070563 | -0.51% |
| READY + PUBLISH + START | 0.266351 | 0.265402 | -0.36% |
| COMPLETE + RETURN + RETIRE | 0.625002 | 0.610810 | -2.27% |

BE的phase4与phase6必须相加后再和BF的phase4比较，不能把转入FINISH的归还/回收时间视作消失。BF的phase4调用同时包含真实GPU等待和CPU归还续调用。计时为Guest/RMM/硬件响应墙钟，工作混合与计数历史可能不同，不能解释为纯CPU耗时或稳定单任务延迟。完整场景和阶段比较见`private-completion-comparison-be-bf.json`。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- `bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-finish-unit.log`；`bash scripts/check/check-dma-guard.sh`退出0，`private-finish-dma.log`。实际Client提交/worker模型90项（原COMPLETE与RECLAIM错误入口合并，避免重复断言）、任务桥142项、完整私有内存/heap/回收/teardown和335阶段后端通过。新增41类FINISH场景共80条标记，覆盖双Client身份、513页跨批、真实GPU pending、中止拒绝、回调故障、归还后故障、跨调用硬件篡改、已完成/已归还入口及旧token失效。控制机模型不证明实体机密隔离。
- `python3 build/rmm-client-bo-20261030/check-private-finish-models.py`退出0，`private-finish-models.log`。当前核心运行BE原294阶段夹具，PASS标记逐项一致；跳过缓存末检、跨调用沿用停止证明、跳过公开RETURN首次检查的三个错误副本均断言拒绝（−6）。初始夹具和构建失败见`private-finish-local-failures.json`；其中前三次夹具失败完整日志被后续运行覆盖，仅保留观察到的断言及修正说明，不伪称拥有原始日志。
- RMM与两端Image构建退出0，`rmm-private-finish.log`、`client-private-finish-final.log`、`proxy-private-finish-final.log`。首轮Guest构建遗漏固定固件目录退出2，原日志保留；正确命令显式传入`CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware`，未更新上游或改变固件。23份RMM flags、O2 Debug/全部断言、14个静态数组实例地址/大小及0x2800000预留与BE相同，FIT/布局通过。能力34359738363、ABI2/RPC4，完整执行能力位仍清零。11份源码差异保存在`private-finish-review/`。
- 固件部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-finish-20261031-bf --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-finish --run-id firmware-private-finish-20261031-bf`退出0，仅SD2；`private-finish-readback-20261031-bf`经同一wrapper执行`verify-private-finish-sd.py`退出0，实际两段启动区字节SHA一致。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bf -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-finish-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，日志`build/lab-runs/private-heap-720-20261031-bf/`。完整33场景、COMPUTE_CHECK、validation26/1/6（含已知失败）、VM0/0、两端日志/解绑、Host健康/资源恢复及11份证据SHA通过；1000门槛FAIL。可选IOCTL冒烟中的eventfd失败独立保留，不称全部API通过。

当前保留620分，仍是实验候选。AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性等未验收，整体目标未完成。


## 控制页按读取范围维护缓存实验（BG，已撤回）

BF的RSI `read_page()`即使只读取8或16字节GPU控制状态，也会invalidate整张4096字节控制页。BG试验改为`memory + offset, bytes`，由原有DC IVAC汇编按架构缓存行向外取整，RK3588的对齐8字节小读取从64条缓存行操作变为1条；未读位置在后续读取前仍须invalidate。此变化仅用于可信记录解析出的CPU隐藏捐赠控制页，保留边界、锁/映射/DSB/私有副本顺序，以及完整GPU状态/根/stream/停止/退休检查。Client私有数据的两种缓存交接始终整页，没有缩小数据同步范围。

改动目的｜减少小控制快照的无关缓存行维护｜BF620 → BG620｜0分/0%｜仅RMM固件变化，两端Guest/Host/initrd/runner逐字节相同；同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频、元数据16384/物理512预算｜下面的命令/run-id/退出码/日志｜未测得整体收益，撤回生产修改，恢复BF源码与SD2固件。

| 操作 ms/成功退休批次 | BF | BG | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE | 0.070563 | 0.070405 | -0.22% |
| READY + PUBLISH + START | 0.265402 | 0.266771 | +0.52% |
| FINISH | 0.610810 | 0.608798 | -0.33% |

场景帧时变化中位数−0.089%，FINISH墙钟变化约−0.33%；都是单轮小幅变化，不能据此声称稳定收益。阶段计时含Guest/RMM/硬件响应和GPU等待，工作混合与计数历史也可变化；缓存行操作64→1不等于整机提速64倍，本轮也不能由微小分差认定控制页维护一定不重要。当前保留620分仍是原BF实测，恢复后没有新增GPU测量。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- 新增`python3 scripts/check/check-gpu-control-cache.py`，直接提取实际RSI读取及两种数据同步回调，以非一致CPU/GPU内存与粒度/映射模型覆盖32,376次读取、每个页内起点、跨行/页尾/整页、非法范围/溢出/空指针、粒度查询失败、GPU更新后再次读取，以及锁→映射→invalidate→DSB→复制→解除映射→解锁顺序；确认两种私有数据交接始终整页。该测试纳入完整私有套件，支持当前整页基线与实验范围版本。恢复BF后实际回调测试退出0，`private-control-range-restored-callback.log`。模型不执行实体DC IVAC，不证明物理隔离。
- `python3 build/rmm-client-bo-20261030/check-private-control-range-models.py`退出0，`private-control-range-models.log`。BG和BF原回调各32,376次读取通过；跳过invalidate、错误起点、截短范围、跳过DSB的四个错误副本均预期断言拒绝（−6）。`bash scripts/check/check-rmm-gpu-private.sh`和`bash scripts/check/check-dma-guard.sh`退出0，`private-control-range-unit.log`、`private-control-range-dma.log`。除新增测试外，578/2013条PASS标记与BF分别逐项相同，包含335阶段后端、80条FINISH标记、90项Client worker和142项任务桥。
- RMM O2 Debug/全部断言、23份flags、14个关键静态数组实例地址/大小、0x2800000预留与BF相同；补丁、FIT/布局校验退出0。能力34359738363、ABI2/RPC4、完整执行能力位仍清零。8个可再生成的控制机模型程序被显式O2构建替换，具体旧/新SHA列于`private-control-range-prior-manifest-review.json`；原BF源码哈希、结果日志、固件及两端Guest保留。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-control-range-20261031-bg --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-control-range --run-id firmware-private-control-range-20261031-bg`退出0；`private-control-range-readback-20261031-bg`经同一独占入口运行`verify-private-control-range-sd.py`退出0，两段SD2启动区实际SHA一致。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bg -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-control-range-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。完整33场景/计算、validation26/1/6（含已知数值失败）、VM0/0、解绑/两端日志、Host健康与资源恢复、11份证据SHA通过；1000门槛FAIL。可选eventfd冒烟仍为errno2而非95、optional rc1，单独保留，不能称全部API通过。
- 恢复：`firmware-private-control-range-restore-bf-20261031-bg`独占/允许重启，使用上述部署入口将`firmware-private-finish`写回SD2；`private-control-range-restore-readback-20261031-bg`独占执行`verify-private-control-range-restore-sd.py`。两者退出0，实际SD字节与BF固件匹配，Host/Realm能力与资源恢复通过。生产RSI源码逐字节恢复BF，仅保留新增控制机回调回归测试。实验源码快照为`private-control-range-source/`，配套实验镜像/固件、比较及失败证据保留。

当前仍保留BF620，整体目标未完成。1000门槛、AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性未验收；GPT/GPC平台模拟边界不变。


## FINISH结果分类诊断（BH，已恢复BF）

为区分“GPU尚未完成”和“CPU归还需要续传”，BH仅在Client现有FINISH调用外增加分类计时，并单独计时GPU pending之后的既有heap-service调用。没有改变调用次数、调度、重试、缓存交接、授权或完成判据；RMM、Proxy、Host、initrd、runner和SD2固件与BF逐字节相同。临时诊断源码已归档并恢复，当前仍保留BF620。

改动目的｜定位FINISH重复查询的原因｜BF620 → BH620｜0分/0%｜仅Client Image增加观测；同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频、元数据16384/物理512预算｜下列run-id、命令、退出码与日志｜诊断完成，撤除临时计数，未新增性能优化，整体目标未完成。

实际日志严格对账得到234949个成功退休批次、939315次FINISH调用、704366次未完成；无typed FINISH错误。每批次平均如下：

| 分类 | 次数/批次 | 调用墙钟 ms/批次 |
| --- | ---: | ---: |
| FINISH成功 | 1.000000 | 0.243785 |
| GPU pending | 2.933066 | 0.134212 |
| CPU归还续传 | 0.064886 | 0.018943 |
| heap service（独立计时） | 2.933066 | 0.046183 |
| phase4内其余未归因时间 | — | 0.165796 |
| phase4 worker间隔（不包含在上列内） | — | 0.212275 |

重复调用主要由GPU pending构成，增加CPU归还扫描预算不直接解决这部分。phase4内尚有约0.166ms/批未归入typed FINISH和heap调用，可能涉及其余分支、任务清理、fence发布或调度干扰；目前不能将它直接解释为纯CPU成本、RMM开销或特定函数耗时。后续应细分该区间和worker间隔，再选择优化。所有统计均为完整file生命周期累计，含设置、验证及预热，不等同正式计分区间；调用墙钟包含Guest、RMM、硬件响应及调度等待，不能求和推出加速上限。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- `python3 scripts/check/check-gpu-private-submit.py`退出0，90项，`private-finish-class-submit.log`；`HOST_CC=.../cc-debug-o2 GPU_PRIVATE_TEST_OUT=.../finish-class-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-finish-class-unit.log`。578条原核心PASS标记一致；只排除BG实验的range/已恢复full-reference模式差异，不掩盖其他变化。初次标记比较因此触发AssertionError，后纠正比较范围，具体限制保留于`private-finish-class-local-validation.json`。
- `python3 opencca/scripts/setup/apply-local-patches.py --check`及Client `make ... Image`均退出0，`private-finish-class-patches.log`、`client-private-finish-class.log`；构建命令详见`private-finish-class-candidate-validation.json`。分类解析器两项有效样本通过、六项损坏样本被拒绝，`private-finish-class-parser.json`。模型不证明实体隔离。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bh -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-finish-class-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，日志`build/lab-runs/private-heap-720-20261031-bh/`。完整33场景/计算、validation26/1/6（含已知数值失败）、VM0/0、Host健康、资源恢复及11份证据SHA通过；外层因620低于1000门槛FAIL。可选eventfd仍errno2而非95、optional rc1，不能称全部API通过。分类及BF/BH比较见`private-finish-class-bh.json`和`private-finish-class-comparison-bf-bh.json`。
- 恢复：38份诊断源码归档于`private-finish-class-source/`并逐项SHA核对，恢复Client驱动和submit模型两个源码，刷新mtime保证下次增量编译会重新构建；38份当前源码与BG撤回后的BF加保留回归完全一致。`private-finish-class-restore-20261031-bh`经独占wrapper执行`restore-private-finish-class.py`退出0，原子恢复冻结BF Client，验证板端四项运行输入；读取实际SD2两段启动区字节与BF固件完全一致，无刷写或重启。记录为`private-finish-class-source-restoration.json`、`private-finish-class-runtime-restoration.json`、`private-finish-class-sd-readback.json`和`private-finish-class-restoration.log`。
- `guest-client/arch/arm64/boot/Image`仍是BH诊断构建产物，未将BF Image冒充该构建树的输出；实际运行输入来自冻结`private-finish-candidate/`。另有三个可再生成的模型产物因诊断/O2构建改变，旧/新SHA记录在`private-finish-class-prior-manifest-review.json`。原BF冻结源码、镜像与测量证据保留。

当前保留620为原BF实测，恢复后无新增GPU测量。能力34359738363、ABI2/RPC4、完整执行能力位仍清零，O2 Debug/全部断言与0x2800000预留不变。1000门槛、可选eventfd、AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性仍未验收，GPT/GPC平台模拟边界不变。


## 完成清理分段诊断（BI，已恢复BF）

BI沿用BH的FINISH分类观测，仅对成功退休后的清理增加四组嵌套墙钟计时：完整run释放、typed task释放、fence发布、依赖与job释放，并记录采样期间当前Guest线程的自愿/非自愿切换次数。没有改变调度、重试、完成、缓存或授权策略；仅Client Image变化，RMM/Proxy/Host/initrd/runner及SD2固件均BF。全部临时源码已归档并恢复。

改动目的｜定位BH未归因的phase4约0.166ms/批｜BF620 → BI619｜−1分/−0.16%｜完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频，元数据16384/物理512预算；仅Client观测变化｜下列run-id、命令、退出码与日志｜诊断结束并恢复BF，单轮1分差异不证明稳定退化，无新增性能优化。

234453个成功退休批次的计数与FINISH/phase4全部对账一致，每批均一个job；阶段4仍有688341次GPU pending及16010次CPU归还续传。清理细分为：

| 成功清理区间 | ms/批 | 区间发生Guest线程切换的调用比例 |
| --- | ---: | ---: |
| 完整run释放（包含下列三段） | 0.166325 | 72.72% |
| task释放 | 0.000391 | 0.009% |
| fence发布 | 0.164526 | 72.71% |
| 依赖、group引用及job释放 | 0.000801 | 0.024% |

FINISH、heap-service及完整run释放均扣除后，phase4剩余仅0.001077ms/批；run释放内部扣除三段后剩余0.000607ms/批。因此BH的约0.166ms主要位于fence发布区间，既非task释放，也非依赖释放。该区间最长13.267917ms，170475/234453次调用发生线程切换。源码中的`dma_fence_signal()`会执行回调、唤醒等待者，解锁/恢复中断后还可能调度；在私有GPU互斥锁内发布，会让被唤醒的提交/映射路径立即竞争这把锁。

这些观测只能定位墙钟区间，不能证明0.164526ms全部是可消除的fence自身CPU成本。切换计数不测量off-CPU时长，也不识别Host未调度vCPU或IRQ执行时间，唤醒后还可能已执行有用的应用工作；不能按该数值推算提分。统计含设置/验证/预热和file完整生命周期，不等同正式计分区间。下一候选据此尝试在精确RMM退休成功后锁内移除run、锁外递交fence，实际收益须另跑完整720p验证。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- `python3 scripts/check/check-gpu-private-submit.py`退出0、90项；`HOST_CC=.../cc-debug-o2 GPU_PRIVATE_TEST_OUT=.../cleanup-profile-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，579条PASS标记与BH逐条一致，包含32,376次实际控制页读取回归。补丁检查与Client Image构建退出0。日志`private-cleanup-profile-submit.log`、`private-cleanup-profile-unit.log`、`private-cleanup-profile-patches.log`、`client-private-cleanup-profile.log`；完整命令/范围见`private-cleanup-profile-candidate-validation.json`及`private-cleanup-profile-local-validation.json`。
- `python3 build/rmm-client-bo-20261030/check-private-cleanup-profile-parser.py`退出0，两项有效输入通过、八项损坏输入拒绝，覆盖缺失子项、错误batch/job次数、子项超过父项/phase4、切换次数及最大值矛盾和重复kind，`private-cleanup-profile-parser.json`。实际解析输出`private-cleanup-profile-bi.json`，解析错误日志为空；对账不证明Linux并发或实体隔离。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bi -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-cleanup-profile-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，`build/lab-runs/private-heap-720-20261031-bi/`。完整33场景/计算、validation26/1/6、VM0/0、Host健康/资源恢复及11份证据SHA通过；619低于1000门槛FAIL。可选eventfd仍errno2而非95、optional rc1，不能称全部API通过。硬件记录`private-cleanup-profile-bi-hardware.json`、BF对比`private-cleanup-profile-comparison-bf-bi.json`。
- 恢复：38份诊断源码逐项SHA归档`private-cleanup-profile-source/`；两个生产/模型源码恢复并刷新mtime，38份当前源码与BF加保留回归完全一致。`private-cleanup-profile-restore-20261031-bi`经独占wrapper执行`restore-private-cleanup-profile.py`退出0，原子恢复BF Client，四项板端输入和实际SD2两段固件SHA一致，无刷写/重启。记录`private-cleanup-profile-source-restoration.json`、`private-cleanup-profile-runtime-restoration.json`、`private-cleanup-profile-sd-readback.json`、`private-cleanup-profile-restoration.log`。此恢复后未新增GPU测量，BF620仍指原BF结果；之后BJ候选独立记录。

能力34359738363、ABI2/RPC4、完整执行位清零。RMM O2 Debug/全部断言、23份flags、14静态数组、0x2800000预留和GPT/GPC模拟边界不变。1000门槛、可选eventfd、AE EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性仍未验收，整体目标未完成。


## 成功完成后的锁外fence发布（BJ，已撤回并恢复BF）

根据BI的计时，BJ只改Client：RMM FINISH精确退休成功后，在`private_gpu_lock`内移除已不再执行的`private_run`，由当前ordered worker持有本地run/job/group引用，在锁外发布fence和释放引用，然后重新取得锁继续工作。postclose仍先排空worker，错误/停止/放弃路径仍在原锁内处理。Mapping guard以RMM已退休及当前run身份为依据，不把fence通知作为授权。RMM所有页归属、真实映射、缓存交接、硬件完成与退休检查均保留，未改变GPU轮询、任务合批、协议或预算。

改动目的｜减少fence唤醒后提交/映射立即竞争私有GPU锁的机会｜BF620 → BJ622｜+2分/+0.32%｜同完整720p33场景/null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频、元数据16384/物理512预算；仅Client Image变化，RMM/Proxy/Host/initrd/runner和固件均BF｜下列run-id、命令、退出码与日志｜单轮小幅差异不足以证明稳定收益，撤回并发交付改动和相应实验模型，恢复BF620。

235275个成功退休批次，phase4调用4.030836次/批，对照BF为4.017751；PREPARE墙钟0.070563→0.070488ms/批、READY_LAUNCH为0.265402→0.265262ms/批、FINISH及其余phase4工作为0.610810→0.690380ms/批（+13.03%），phase4 worker间隔0.213019→0.213302ms/批。场景帧时变化中位数−0.236%。整体分数小幅上升而phase4墙钟增加，进一步说明phase4不是纯CPU工作量或可直接消除的关键路径时间；锁外期间Client可能已经执行下一轮有用工作，重新加锁也可能等待映射。单轮没有细分这些成分，不能把+13.03%解释为整机变慢，也不能将BI的0.164526ms宣称为可节约时间。当前保留620仍指原BF测量，恢复后未新增GPU测量。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- 实际Client planner/worker模型90→96项，新六项覆盖成功fence交付时同VM映射、同队列再次提交、关闭、Group销毁、再次提交后关闭，以及真实FINISH错误仍在锁内保留失败路径；核对本地run已移除、任务精确退休且job/group引用存活。`python3 scripts/check/check-gpu-private-submit.py`退出0，`private-unlocked-completion-submit.log`。模型只模拟并发交错，不证明Linux真实并发、实体隔离或长期稳定性。 恢复后使用候选源码快照和冻结的实际worker输入重放，参考96项及两个错误副本结果一致，`private-unlocked-completion-models-replay.json`；未改生产源码。
- `python3 build/rmm-client-bo-20261030/check-private-unlocked-completion-models.py`退出0，参考96项通过，遗漏解锁/遗漏移除run两个实际worker错误副本均断言拒绝（−6），`private-unlocked-completion-models.json`。`HOST_CC=.../cc-debug-o2 GPU_PRIVATE_TEST_OUT=.../unlocked-completion-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，579条PASS标记中除上述测试项由90变96，其他578条逐条一致，`private-unlocked-completion-unit.log`。补丁检查和Client Image构建退出0，命令见`private-unlocked-completion-candidate-validation.json`，日志`private-unlocked-completion-patches.log`、`client-private-unlocked-completion.log`。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bj -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-unlocked-completion-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，`build/lab-runs/private-heap-720-20261031-bj/`。完整33场景/计算、validation26/1/6、VM0/0、两端解绑/日志、Host健康/资源恢复及11份SHA通过；622低于1000门槛FAIL。可选eventfd仍errno2而非95、optional rc1，不能称全部API通过。对比和硬件结果见`private-unlocked-completion-comparison-bf-bj.json`、`private-unlocked-completion-bj-hardware.json`。
- 恢复：38份候选源码逐项SHA归档`private-unlocked-completion-source/`，代码/模型差异保存在`unlocked-completion-review/`。恢复两个生产/模型源码并刷新mtime，38项源码与BF加保留回归完全一致，实验helper/分支和新增回调模型均不留在生产源码。`private-unlocked-completion-restore-20261031-bj`经独占wrapper运行`restore-private-unlocked-completion.py`退出0，原子恢复BF Client，板端四项运行输入及实际SD2两段固件SHA一致，无刷写/重启。记录`private-unlocked-completion-source-restoration.json`、`private-unlocked-completion-runtime-restoration.json`、`private-unlocked-completion-sd-readback.json`、`private-unlocked-completion-restoration.log`。

`guest-client/arch/arm64/boot/Image`仍是BJ构建产物，与相应vmlinux/objects一致；板端实际运行输入来自冻结BF包，未将其覆盖伪装为该构建树输出。已刷新恢复源码mtime，下次构建会重新编译。BF原镜像/固件和BI/BJ测量、候选快照、模型与失败证据均保留。RMM O2 Debug/全部断言、23份flags、14静态数组和0x2800000预留不变；能力34359738363、ABI2/RPC4、完整执行位清零，GPT/GPC模拟边界不变。

本轮完成了未归因开销定位，排除了“直接删去fence区间墙钟即可获得相同比例加速”的解释；后续应优先区分真实GPU等待、可信生命周期操作与应用唤醒的关键路径，而非继续优化已证实很小的task/job释放。1000门槛、可选eventfd、AE EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性仍未验收，整体目标未完成。

封存补充：首次封存脚本误用了BH旧轮的`realm-evidence/collection.json`路径，在写入总清单前触发FileNotFoundError；已改为本轮采集器实际生成的`evidence-transfer.json`并逐文件校验。失败日志保留为`private-cleanup-unlocked-checkpoint-attempt1.log`，修正说明见`private-cleanup-unlocked-sealing-correction.json`；不是GPU运行失败，不覆盖两轮1000分门槛失败。


## 队列首次完成查询预测（BK/BL，保留实验候选）

BH诊断显示每批约2.93次GPU pending，BI/BJ又说明fence发布的墙钟不能直接视为可节约CPU成本。本轮仅改变Client查询时机：每个group/queue维护一个等待提示，成功READY_LAUNCH后先进行至多200µs的请求等待，再执行原来的真实FINISH。一次FINISH返回typed GPU pending时记录该次查询起点相对启动后的间隔；只有该任务精确完成并退休成功，才用`(3×旧提示+截断至200µs的样本)/4`更新下一次提示。首次查询已完成则样本为零、提示衰减；CPU归还续传和失败任务不提供GPU等待样本，多成员批次不使用或训练预测。没有使用Proxy通知作为完成证明。

提示和计时只影响性能。真实FINISH、heap事件处理、物理缓存、页归属、完成/停止/回收、错误与不确定任务保留全部原检查；等待释放Client GPU互斥锁，并保留关闭判断与原绝对期限。原后续八次50µs及延迟轮询不变，最多额外200µs、每批请求主动等待合计至多600µs。请求上限不等于墙钟上限，Guest/Host抢占可能使实际等待更长。RMM/Proxy/Host/initrd/runner和SD2固件均BF，仅Client Image变化。

改动目的｜减少启动后过早的FINISH/heap查询｜BF620 → BK/BL 637/636，均值636.5｜+16.5分/+2.66%｜完整720p33场景/null-noop/finish、单Client、GPU请求600/实际594MHz、CPU未锁恒频，元数据16384/物理512预算；只改变Client｜下列命令、run-id、退出码与日志｜保留实验候选；未达到1000门槛，不宣称跨负载稳定收益。

| 版本 | 成功退休批次 | FINISH调用/批 | phase4操作ms/批 | phase4间隔ms/批 | 首次预测等待墙钟ms/批 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BF | 234685 | 4.017751 | 0.610810 | 0.213019 | 0 |
| BK | 240479 | 2.551716 | 0.533733 | 0.259939 | 0.158789 |
| BL | 240330 | 2.553206 | 0.533457 | 0.261547 | 0.160025 |

BK的FINISH调用/批减少36.49%，首次等待为0.158789ms/批，全部短等待墙钟反而0.150131→0.234697ms/批；phase4操作减少12.62%，但间隔增加。省下查询并不等于按相同比例加速，phase4间隔包含主动等待和调度，不能将其与CPU成本混为一谈。FINISH的EAGAIN还包含CPU归还续传，不能把所有重复调用都称为GPU pending。统计是file完整生命周期累计，含设置/验证/预热；早期history窗口可能缺失，最终总计完整，不等同正式计分区间。

提分主要集中于5×3核的effect2d卷积滤镜：BF 8.003ms，BK 1.731ms、BL 1.731ms；各场景帧时变化中位数为-0.201%/-0.271%。先前BF/BG/BH/BI/BJ该滤镜均约8ms，本候选两次改善，提示查询/调度时机与特定负载交互。没有独立设备时间戳证明具体硬件原因，不能断言一定是某一次timer tick，更不能把2.74%的首轮总提分推广为每个场景相同收益。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- `python3 scripts/check/check-gpu-private-submit.py`退出0，90→101项，覆盖学习后减少过早查询、首查完成衰减、CPU-return排除、过大提示、错误不训练、多成员绕过、关闭/期限、不同队列及长时间失调度样本截断；`private-poll-predict-submit.log`。`HOST_CC=.../cc-debug-o2 GPU_PRIVATE_TEST_OUT=.../poll-predict-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，579条PASS标记中除Client测试数外其余578条一致，`private-poll-predict-unit.log`。补丁检查和ARM64 Client构建退出0，`private-poll-predict-patches.log`、`client-private-poll-predict.log`；完整命令与哈希见`private-poll-predict-candidate-validation.json`。
- `python3 build/rmm-client-bo-20261030/check-private-poll-predict-models.py`及带`poll-predict-models-replay`的冻结输入重放均退出0，参考101项通过，超额400µs、CPU-return误作GPU pending、失败任务训练、跳过真实FINISH四个实际worker错误副本均断言拒绝（−6）；`private-poll-predict-models.json`、`private-poll-predict-models-replay.json`。模型不证明Linux真实并发或实体隔离。
- 两轮命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-<bk或bl> -- python3 build/rmm-client-bo-20261030/run-private-with-uart-20261031.py --images build/rmm-client-bo-20261030/private-poll-predict-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，两次退出1。证据分别在`build/lab-runs/private-heap-720-20261031-bk/`及`...-bl/`，stdout为`private-poll-predict-run.log`和`private-poll-predict-repeat-run.log`。33场景/计算、validation26/1/6（含既有数值失败）、VM0/0、两端解绑/日志、Host健康/资源恢复及各11份采集SHA通过；外层因低于1000而FAIL。可选eventfd仍errno2而非95、optional rc1，不能称全部API通过。
- 两轮分别用严格硬件分析及BF对比脚本核对，结果`private-poll-predict-bk-hardware.json`、`private-poll-predict-bl-hardware.json`和`private-poll-predict-comparison-bf-bk.json`、`...-bf-bl.json`。预测训练数与各自实际成功退休批次完全一致；首次等待次数不超过批次，不能把该计数当作授权或完成证明。
- 38份候选源码逐项SHA冻结于`private-poll-predict-source/`，当前源码与`private-poll-predict-retained-source-hashes.json`一致；两个改动源码差异见`poll-predict-review/`。当前冻结包为`private-poll-predict-candidate/`，Client SHA `7389969e4a5751554d15c299d5a0f6a262118d4fa48a630a2745f78b6a8c2b29`，与构建树实际Image一致。BF620冻结包及源码仍保留回退。
- `private-poll-predict-verify-20261031-bk`与`private-poll-predict-final-verify-20261031-bl`经独占wrapper执行只读核验，退出0，板端四项运行输入与候选一致，实际SD2两段启动区字节仍完全匹配BF固件，无刷写/重启。两组`private-poll-predict[-final]-runtime-verification.json`和`...-sd-readback.json`保留独立结果；最终核验后无新增GPU测量。

RMM O2 Debug/全部断言、23份flags、14静态数组和0x2800000预留不变；能力34359738363、ABI2/RPC4、完整执行位清零，GPT/GPC模拟边界不变。1000门槛、可选eventfd、AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性仍未验收，整体目标未完成。

证据处理补充：BL日志传输尚未退出时提前调用硬件分析，先后因summary/cache尚不存在退出1；已保留`private-poll-predict-repeat-hardware-attempt1.log`、`private-poll-predict-repeat-comparison-attempt1.log`及`private-poll-predict-analysis-sequencing-correction.json`。等待采集器退出0、11份远端/本地SHA一致后，两项分析重新退出0；不是GPU运行失败，不覆盖两轮1000门槛与可选eventfd失败。


## 对齐读取实际页表归属标签（BM，保留实验候选）

上一轮BK/BL保留的私有路径得分为637/636、均值636.5，仍未达到1000门槛。本轮保持该Client预测和全部生命周期机制，只改变RMM `task_cache()` 中四项批量检查的归属标签读取：原四个16位读取与逐项异或比较，改为一个8字节对齐的64位读取，与四次重复的已检查BO标签比较。`leaf_object`明确8字节对齐，每行512项；仅`index % 4 == 0`且组内/预算至少还有四项时进入，其他位置沿用逐项路径。使用固定长度builtin memcpy和已证明的对齐提示，避免通过不兼容指针类型访问数组；增加16位标签宽度的编译期断言。

四个真实PTE仍分别读取、检查原描述符/AF/USER位；任一标签或必需位不匹配时回退逐项检查，失败游标仍停在原来的第一处错误。已检查BO只在同一次policy lock、无物理回调的区间内复用，不缓存跨调用证明，不跳过实际页表、归属、租约或缓存操作。原16384项元数据/512项物理预算、NC barrier、真实完成、停止、归还及退休条件均保留。仅RMM固件变化，Client/Proxy/Host/initrd/runner和ABI/能力与BK/BL相同。

改动目的｜降低逐页授权检查中的归属标签读取和比较成本｜BK/BL637/636、均值636.5 → BM645｜+8.5分/+1.34%；对BL636为+9/+1.42%｜完整720p33场景/null-noop/finish、单Client、GPU请求600/实际594MHz，CPU未锁恒频；BM在固件部署重启后运行，与无需重启的BK/BL有准备状态差异｜下列命令、run-id、退出码与日志｜保留实验候选，单轮不证明稳定或跨负载收益，未达到1000分门槛。

| 每批墙钟或调用 | BL636 | BM645 | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE ms | 0.069989 | 0.070380 | +0.56% |
| READY_LAUNCH ms | 0.265957 | 0.259540 | −2.41% |
| FINISH及phase4其余工作 ms | 0.533457 | 0.523667 | −1.84% |

BM成功退休244080批，首次预测等待244045次，训练次数与退休数相同；原预测请求上限200µs不变。场景帧时变化中位数−1.27%，先前受预测影响的effect2d滤镜1.731→1.713ms，未出现上一轮那样的大幅单场景变化。逐项退化和原始计数保留在`private-packed-tags-comparison-bl-bm.json`；操作是file生命周期墙钟，包含设置/验证/预热、RMM/硬件响应及调度，不是纯CPU或正式计分窗口。FINISH的重复调用含GPU等待和CPU归还续传，不能全部称为GPU pending。

ARM64实际反汇编确认标签快路径改为一个64位LDR和整字比较，但`task_cache`文本从0x714（1812）增至0x7c8（1992）字节；局部访存减少伴随额外对齐判断和寄存器压力，不能只按源代码读取次数推算提分。两份反汇编为`task-cache-before-packed-tags.dis`和`task-cache-after-packed-tags.dis`。没有改变编译优化等级、断言或数据区布局来取得分数。

验证与证据（默认相对`build/rmm-client-bo-20261030/`）：

- `HOST_CC=.../cc-debug-o2 GPU_PRIVATE_TEST_OUT=.../packed-tags-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，579条PASS标记与BK/BL逐条一致；`private-packed-tags-unit.log`、`private-packed-tags-local-validation.json`。补丁清单检查`python3 opencca/scripts/setup/apply-local-patches.py --check`退出0，`private-packed-tags-patches.log`。
- `python3 build/rmm-client-bo-20261030/check-private-packed-tags-models.py`退出0，原版/候选各320项实际核心测试结果一致，覆盖四项各位置、32项组边界、READY/RETURN、必需PTE位、越界/异对象标签与精确失败游标。只比较第一项标签、遗漏USER位、允许未对齐整字、错误推进第五项四个错误副本均在运行断言中拒绝（−6）；`private-packed-tags-models.json`。另以冻结核心输入执行`...check-private-packed-tags-models.py packed-tags-models-replay`退出0，结果一致，`private-packed-tags-models-replay.json`。模型不证明实体隔离或Linux真实并发。
- 初次模型驱动在构造“仅第一项标签”错误副本时，使预期标签整字变量无用而被`-Werror`拒绝；该次退出1，不计为运行时拒绝。修正错误副本同时截断两侧比较后再完成上述运行检查，生产源码未变。原失败保留在`private-packed-tags-models-attempt1.log`、`packed-tags-models-attempt1/`及`private-packed-tags-model-correction.json`。
- `python3 build/rmm-client-bo-20261030/build-private-packed-tags.py`和`build-private-packed-tags-firmware.py`退出0，23份参数与BF一致，保持O2 Debug/全部断言；FIT和含BSS布局检查退出0，RMM预留末址0x2800000，14个关键静态数组地址/大小完全相同。见`private-packed-tags-build-validation.json`、`private-packed-tags-static-layout.json`、`private-packed-tags-fit.json`及`private-packed-tags-layout.json`。新RMM ELF SHA `c4ad70255432ef3df92320fcd0bb686635c1f9bbde2c95a3f1c3130add08b15c`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-packed-tags-20261031-bm --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-packed-tags --run-id firmware-private-packed-tags-20261031-bm`退出0，只写SD2固件；备份实际启动区、UART、Host恢复及Realm能力1保存在`build/firmware-runs/firmware-private-packed-tags-20261031-bm/`，Host内核/rootfs未改。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bm -- python3 build/rmm-client-bo-20261030/run-private-packed-tags-with-uart.py --images build/rmm-client-bo-20261030/private-packed-tags-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。运行前实际SD2回读匹配新固件，记录`private-packed-tags-sd-readback.json`；完整33场景/计算、validation26/1/6（含已知数值失败）、VM0/0、两端解绑/日志、Host健康/资源恢复及11份证据SHA核验通过。外层因645低于1000而FAIL；可选eventfd仍errno2而非95、optional rc1，不能称全部API通过。原始证据在`build/lab-runs/private-heap-720-20261031-bm/`，stdout `private-packed-tags-run.log`，严格分析`private-packed-tags-bm-hardware.json`。
- 38份候选源码逐项SHA冻结于`private-packed-tags-source/`，当前源码匹配`private-packed-tags-source-hashes.json`；运行包`private-packed-tags-candidate/`只替换rmm.elf/rmm.img，四项Guest运行载荷与BK/BL相同。配套固件`firmware-private-packed-tags/`。独占只读核验`private-packed-tags-final-verify-20261031-bm`退出0，板端四项运行输入和实际SD2两段固件一致，记录`private-packed-tags-final-verification.json`；最终核验后无新增GPU测量。BK/BL636.5和BF620冻结输入、源码与实测证据仍保留回退。

本轮只保留标签读取的局部实现优化；能力34359738363、ABI2/RPC4、完整执行位清零和GPT/GPC模拟边界不变。1000门槛、可选eventfd、AE VM_BIND EBUSY、多Client、实体恶意Proxy/越权、动态OOM及并发销毁/公平性仍未验收，整体目标未完成。

封存补充：首次封存因两个既有模型可执行文件SHA改变而拒绝，在写总清单前退出1。已核对`private-heap-unit/heap-test`直接包含实际RMM核心、`reclaim-unit/reclaim-test`链接该核心，均由本轮完整私有套件重新生成且通过；其余漂移仅生产核心和两份文档。明确列入这两项允许变更并保留旧/新SHA，见`private-packed-tags-prior-manifest-review.json`；失败及修正保留于`private-packed-tags-checkpoint-attempt1.log`、`private-packed-tags-sealing-correction.json`，不是GPU运行失败。


## BN：固件状态缓存范围实验，643分，撤回至BM645（2026-10-31）

**统一记录：** 减少可信固件状态观察的缓存维护｜BM645 → BN643｜−2分/−0.31%｜仅RMM固件改变，Client/Proxy/Host/initrd/runner相同，两轮均在部署固件重启后运行，CPU未锁恒频｜测量`private-heap-720-20261031-bn`退出1（1000分门槛失败），完整日志`build/lab-runs/private-heap-720-20261031-bn/`、`realm-evidence/summary.json`及`evidence-transfer.json`｜**撤回运行代码/固件，保留测试与证据；整体目标未完成。**

START、完成观察和停止重查的`stream_status()`实际读取ACK、scoreboards、blocked reason、fault、fatal五个32位字段，最后一项结束于字节136。实验将此前216字节的整体invalidate缩到136字节：已验证的64字节对齐接口由4条缓存行减少到3条；仍在全部读取前完成一次invalidate及原有屏障，不跨调用复用状态，不减少stream/error/root检查。堆扩展继续读取完整输出。真实ARM64反汇编确认136字节回调先于五次32位读取，含132偏移的fatal；见`private-stream-window-assembly.{txt,json}`。这只是缓存维护范围实验，没有引入新的隔离保证。

**实测未显示收益。** 相对BM，PREPARE墙钟每批0.070380→0.070401ms（+0.03%），READY/PUBLISH/START为0.259540→0.259949ms（+0.16%），FINISH为0.523667→0.525463ms（+0.34%）；33场景帧时变化中位数+0.25%。这些是单轮混合负载墙钟，不能当作纯CPU成本或稳定回退证明。结果出来前已保存`private-stream-window-decision-rule.json`，实验保留要求至少652分；643未达到，所以撤回。下一轮不应仅凭“少一条缓存行”推断端到端收益。

证据根目录为`build/rmm-client-bo-20261030/`：

- 本地：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/stream-window-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-stream-window-local.log`；原579个PASS标记逐项一致，另加1个新模型。新模型用独立device/cached字节数组模拟不一致缓存，只有实际invalidate才刷新，候选及原版各640次观察均读取到五个字段的新值；四个错误变体（遗漏invalidate、范围截断fatal、先读后invalidate、遗漏scoreboards）均被断言拒绝。`check-private-stream-window-models.py`退出0，`private-stream-window-models.json`。`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-stream-window-backend.log`包含2013个PASS标记；标记数不是独立测试数量。模型不代替实体攻击验收。
- 保留失败：首版错误变体生成器误将回调语句同时插入结构体和函数尾，编译器拒绝该无效变体；原脚本及`stream-window-models/late-invalidate/build.log`保留。修正为只插入函数尾后完成四项拒绝，见`private-stream-window-model-correction.json`；生产代码未因该修正变化，不计作GPU运行失败。
- 构建：`build-private-stream-window.py`、`build-private-stream-window-firmware.py`退出0；23份O2 Debug/断言参数与原版相同，14个关键静态数组地址/大小相同，预留末址0x2800000不变，FIT/含BSS布局通过。冻结运行包`private-stream-window-candidate/`、40份源码`private-stream-window-source/`；RMM ELF SHA `f3563e83c9bf066b8b204f273907b9e7620250a2d8aec65e8257df7b0af6301e`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-stream-window-20261031-bn --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-stream-window --run-id firmware-private-stream-window-20261031-bn`退出0，仅SD2。测量前`verify-private-stream-window-sd.py`在同一测试租约内核验SD实际启动字节，SHA一致。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bn -- python3 build/rmm-client-bo-20261030/run-private-stream-window-with-uart.py --images build/rmm-client-bo-20261030/private-stream-window-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。全部33场景与COMPUTE_CHECK、两端日志/解绑、VM0/0、Host内核健康和资源恢复检查通过，11份回收证据SHA一致；validation26/1/6仍含已知数值失败，不能写成全项正确性通过。可选eventfd仍以errno2失败；1000分门槛FAIL，AE EBUSY与广泛API/多Client/实体攻击仍未验收。
- 恢复：生产`opencca_gpu_firmware.c`和后端夹具逐字节恢复BM，mtime刷新；保留能够校验BM完整范围及候选范围的新鲜度测试并接入统一检查，恢复后的640次模型退出0（4条缓存行）。`firmware-private-stream-window-restore-20261031-bn`经同一独占部署入口、选择`firmware-private-packed-tags/`退出0。随后`private-stream-window-final-verify-20261031-bn`通过wrapper执行`verify-private-stream-window-final.py`退出0，核验BM实际SD2两段固件及板端四项运行输入。当前恢复`private-packed-tags-candidate/`与`firmware-private-packed-tags/`，**恢复后未新增GPU测量，645分引用原BM实测**。新增测试只证明缓存读取契约，无新增性能测量；实现报告首页过期BE611文字已改为BM645，不据此宣称提分。

能力34359738363、ABI2/RPC4、完整执行位清零和GPT/GPC模拟边界不变。最终源码、输入、实验失败、恢复与证据由`private-stream-window-checkpoint-record.json`、`manifest-validation-private-stream-window.json`和`independent-private-stream-window-checkpoint.json`封存；1000门槛、恶意Proxy/Client、动态OOM、并发销毁与公平性尚待完成。


## BO：批量完成stream输出缓存维护，648分，撤回至BM645（2026-10-31）

改动目的｜减少可信固件反复观察stream时的完成屏障｜BM645 → BO648｜+3分/+0.47%｜仅RMM固件改变，Client/Proxy/Host/initrd/runner相同；两轮均在固件重启后运行，CPU未锁恒频｜`private-heap-720-20261031-bo`退出1，`build/lab-runs/private-heap-720-20261031-bo/`保存日志/命令/资源与`realm-evidence/summary.json`、`evidence-transfer.json`｜**撤回至BM645，单轮不证明稳定收益，整体目标未完成。**

原路径为每个stream分别invalidate216字节并完成DSB。候选先由可信核心构造至多32个实际输出地址，逐个执行相同范围的DC IVAC，最后完成一次DSB，再读取ACK、scoreboards、blocked reason、fault、fatal五个字段。只合并屏障，不减少缓存行，不跨越输出间隙失效，也不将快照保存到下一次回调。实际ARM64反汇编确认CTR推导行长、DC IVAC循环、一个末尾DSB和之后的五次32位读取。START预检/ACK轮询、已停止复查、STOP ACK轮询及完成STATUS ACK轮询五处使用批量；SUSPEND输入重置及活跃queue逐项观察两处保留原路径。错误、根、停止、缓存归还与退休检查均保留。

| 每批墙钟ms | BM645 | BO648 | 变化 |
| --- | ---: | ---: | ---: |
| prepare | 0.070380 | 0.069989 | -0.56% |
| ready_publish_start | 0.259540 | 0.257066 | -0.95% |
| complete_return_retire | 0.523667 | 0.511540 | -2.32% |

33场景帧时变化中位数-0.38%。以上是混合工作负载墙钟，包含硬件响应、调度及非计分阶段，不是纯CPU成本。测量前`private-stream-batch-decision-rule.json`规定至少652分才保留实验候选，1000分仍是扩大硬件回归门槛；不按局部指令减少推算收益。

证据根目录`build/rmm-client-bo-20261030/`：

- 本地：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/stream-batch-final-unit bash scripts/check/check-rmm-gpu-private.sh`退出0（`private-stream-batch-final-local.log`），581个PASS标记。原580个标记除BN撤回后的实际行数3→4外等价，新增批量模型1项。`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0（`private-stream-batch-final-backend.log`），2013个标记与上一轮一致；标记数不是独立测试数量。
- 缓存模型：`python3 build/rmm-client-bo-20261030/check-private-stream-batch-models.py`退出0，`private-stream-batch-models.json`。实际核心和RSI函数提取，DC只排队、DSB才刷新缓存；count1–32、五字段模式及32/64/128/256字节行长共640组，对比scalar/vector并独立检查期望值。遗漏最后范围、遗漏屏障、读后失效、遗漏fatal、错误步长及跨间隙合并六个错误副本均被运行断言拒绝。仅模型，不证明实体隔离。
- 构建：最终`build-private-stream-batch-retry.py`、`build-private-stream-batch-firmware.py`退出0，23份O2 Debug/断言参数与BF相同；`private-stream-batch-build-validation.json`、`private-stream-batch-fit.json`、`private-stream-batch-layout.json`。RMM预留末址0x2800000不变。14个数组实例大小相同，13个地址相同，仅RK v2 IOMMU符号寻址的8KiB `table_owner`平移16字节，GPU页表地址不变。首次“所有地址相同”的分析断言失败已保留，最终按实际差异审查，见`private-stream-batch-static-layout-observed.json`和`private-stream-batch-static-layout.json`。不宣称布局完全相同。
- 栈/汇编：`private-stream-batch-stack.json`、`private-stream-batch-assembly.txt`。批量helper栈304字节，START/quiesce/observe分别1376/1344/1360字节；部署参数不添加stack-usage，仅分析对象使用。未证明完整调用图上界。中间版本字段helper未内联，在strict-align下产生逐字节访问，保留`stream-batch-before-inline/`；最终内联恢复五次32位加载，ELF SHA `e6d85720fdb68488dba67bb65aa06e2d4bac3e87cbe8060303b46d6dde3e9271`。
- 保留构建失败：第一次接线脚本范围判断过宽提前退出，helper未调用被严格编译拒绝；第二次失败分支诊断值可能未初始化，被编译器拒绝。分别保留`stream-batch-first-build/`、`stream-batch-second-build/`；修正调用点与诊断零初始化后构建成功。都未部署，不把编译拒绝当成GPU故障或通过。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-stream-batch-20261031-bo --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-stream-batch --run-id firmware-private-stream-batch-20261031-bo`退出0；只写SD2，记录原启动区备份/UART及Host/Realm恢复。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bo -- python3 build/rmm-client-bo-20261030/run-private-stream-batch-with-uart.py --images build/rmm-client-bo-20261030/private-stream-batch-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。同租约先回读实际SD2启动字节；33场景/计算、两端日志/解绑、VM0/0、Host健康/资源和11份证据SHA通过，validation26/1/6含已知数值失败。可选eventfd仍errno2失败，1000门槛FAIL；不称完整API或安全验收通过。
- 最终状态：运行源码/header/两项模型provider与统一测试入口逐字节恢复BM，mtime刷新；批量专用helper/测试/入口从工作源码移除，完整42份候选与错误变体保存在冻结目录。恢复租约`firmware-private-stream-batch-restore-20261031-bo`退出0，只写SD2的BM固件。最终核验后无新增GPU测量，当前645引用原BM实测。 `private-stream-batch-final-verify-20261031-bo`通过独占只读核验退出0，`private-stream-batch-final-verification.json`确认实际SD2与四项运行输入。冻结包`private-stream-batch-candidate/`及42份源码`private-stream-batch-source/`保存试验，最终源码见`private-stream-batch-final-source-hashes.json`。

封存漂移审查：除运行源码和文档外，本轮重新生成的后端模型、状态模型及heap RSI模型二进制SHA会改变；heap RSI模型直接包含新增回调后的firmware-ops头，私有套件已运行通过。候选源码和头均冻结，生成二进制不是板端运行输入；恢复状态模型重建后重新确认原4条缓存行。旧/新SHA与具体来源记录于`private-stream-batch-prior-manifest-review.json`，不以批量放行未知漂移替代审查。

ABI2/RPC4、能力34359738363、完整执行位清零和GPT/GPC模拟边界保持；AE EBUSY、可选eventfd、广泛API、多Client、恶意Proxy/Client实体攻击、动态OOM、并发销毁与公平性仍未验收。最终`private-stream-batch-checkpoint-record.json`及独立封存校验记录保留这些缺口。

BO封存补充：首次封存将stdout重定向到清单覆盖的日志，末尾输出使该日志在哈希后改变；在独立验收前已发现并保留首版清单/审计与日志到`stream-batch-seal-first-attempt/`。恢复前一清单后改用无重定向命令重新封存，记录`private-stream-batch-sealing-correction.json`；没有改动运行源码或板端，不算GPU运行失败。


## BP：Client有界连续推进，645分，撤回至BM645（2026-10-31）

改动目的｜减少立即可运行私有任务阶段的workqueue交接｜BM645 → BP645｜+0分/+0.00%｜仅Client Image变化，RMM/Proxy/Host/initrd/runner及BM的实际SD2不变，无刷写/重启；CPU未锁恒频，BM在固件部署后测量、BP直接使用恢复后的Host｜`private-heap-720-20261031-bp`退出1，日志`build/lab-runs/private-heap-720-20261031-bp/`及`realm-evidence/summary.json`、`evidence-transfer.json`｜**撤回至BM645；单轮不证明稳定或跨负载收益，整体目标未完成。**

原GPU worker每次阶段结束后重新排队，包括READY续传、启动后的首次观察、短GPU等待和CPU归还续传。候选同一次worker至多推进四个阶段，仍在每步释放`private_gpu_lock`、允许调度，重新入锁后检查关闭和原任务期限；1ms预算和调度请求在让出前及恢复后都检查。预算按阶段边界执行，不能抢占正在执行的慢RPC/RMM调用，也不保证Host不会把VM挂起更久。真实GPU pending仍使用原200µs预测上限及八次50µs短等，之后恢复延迟轮询；原始deadline不延长。真正排队时才记录queue等待，连续推进仍计入原有各阶段及gap统计。

没有增加信任Client/Proxy结果的快速完成：每次FINISH仍进入RMM，完整硬件状态、错误、停止、缓存归还及精确退休不变；返回续传不会变成GPU等待或完成，fence只在RMM退休成功后发布。映射等待票据继续阻止同VM后续任务插队，worker中途收到另一排队事件也不会重复启动任务。实测`PRIVATE_INLINE`连续推进796982次、让出116002次，配置为最多4阶段/1000000ns。

| 每批墙钟ms | BM645 | BP645 | 变化 |
| --- | ---: | ---: | ---: |
| prepare | 0.070380 | 0.070542 | +0.23% |
| ready_publish_start | 0.259540 | 0.260207 | +0.26% |
| complete_return_retire | 0.523667 | 0.525052 | +0.26% |

33场景帧时变化中位数+0.09%。阶段/gap含GPU等待、Guest/Host调度和非正式计分阶段，不是纯CPU成本；所有逐场景和原始计数保留在`private-inline-worker-comparison-bm-bp.json`。实验保留条件在测量前写为至少652分，整体1000分仍为扩大硬件回归的门槛。

| 完成等待，每成功退休批次µs | BM645 | BP645 |
| --- | ---: | ---: |
| short_pause | 234.981 | 235.549 |
| relock | 0.008 | 0.013 |
| queue_immediate | 3.109 | 0.853 |
| queue_delayed | 21.316 | 21.234 |
| entry_lock | 0.317 | 0.045 |

BM的立即workqueue等待累计仅0.758844秒（622649次，约1.22µs/次、3.11µs/成功退休批次）；COMPLETE阶段间隔63.571682秒中包含短暂停顿57.354130秒及延迟排队5.202759秒。不能把整个约0.26ms/批的间隔归因于立即排队成本。连续推进也可能改变硬件观察时机和Host调度；以上计数支持成本拆分，不能单独证明因果。下一步应优先测量实际RMM调用、页表/归属扫描和启动/停止握手成本，避免继续按总gap推算worker优化收益。

证据根目录`build/rmm-client-bo-20261030/`：

- 构建：`make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`退出0，最终日志`client-private-inline-worker-post-yield.log`；冻结Image SHA `e8dbee101aba3480891f5ae3f481e5ef5cbc0230d3a4321895e71f5de8e0a9fa`。运行包`private-inline-worker-candidate/`仅替换Client Image，40份源码冻结于`private-inline-worker-source/`；RMM仍使用BM O2 Debug/断言固件，没有改变固件构建或权限。
- 本地：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/inline-worker-post-yield-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-inline-worker-post-yield-local.log`含581条PASS标记。原580项除submit101→113场景和BN撤回后缓存行3→4外等价，另加一条INLINE标记；标记数不是独立测试数量。原101项在调度器要求让出的路径运行，12个新场景实际启用连续推进，验证步数/时间/调度让出、锁释放、步间关闭/过期、真实FINISH与CPU归还、重复排队和映射优先级。模型不证明Linux真实并发或实体隔离。
- 错误变体：`python3 build/rmm-client-bo-20261030/check-private-inline-worker-models.py`退出0，`private-inline-worker-models.json`；候选113项通过，遗漏步数限制、扩大时间上限、持锁让出、忽略关闭及跳过真实FINISH五个变体均在运行断言中拒绝（−6）。
- 保留失败/修正：首次夹具重复定义cond_resched，编译拒绝；隔离公共调度double后修正。新增一次worker入口时钟读取令旧队列时间期望多1ns，旧精确断言拒绝后按实际双读修正，未改授权条件。初版无步数限制变体提前完成并释放run，夹具在断言前解引用空run，触发ASan；增加显式存活断言后才完成上述五项拒绝，不把ASan当预期断言通过。见`private-inline-worker-submit-first.log`、`private-inline-worker-submit-second.log`、`inline-worker-models-first-attempt/`及`private-inline-worker-model-correction.json`。Image冻结初次把版本格式字符串也计入唯一性判断而拒绝；改为只匹配实际带构建编号的启动版本，部分冻结包以`-first-freeze`保留，见`private-inline-worker-freeze-correction.json`。所有失败都在部署前，不算GPU失败。
- 离线分析脚本复查：比较脚本模板把工作目录误写成不存在的`build/rmm-client-bp-20261030`，在正式分析前改回`build/rmm-client-bo-20261030`；`private-inline-worker-analysis-correction.json`记录此修正。未改变正在运行的runner或冻结输入。
- 硬件：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bp -- python3 build/rmm-client-bo-20261030/run-private-inline-worker-with-uart.py --images build/rmm-client-bo-20261030/private-inline-worker-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，stdout `private-inline-worker-run.log`。同一租约先回读BM实际SD2字节，wrapper只上传变化的Client Image。完整33场景、COMPUTE_CHECK、VM0/0、两端日志/解绑、Host健康/资源及11份证据SHA通过；validation26/1/6含已知数值失败，可选eventfd仍errno2失败，1000门槛FAIL，不宣称完整API通过。
- 最终状态：Client生产源码和测试夹具逐字节恢复BM，mtime刷新；独占`private-inline-worker-restore-20261031-bp`只原子恢复Client Image，退出0。未刷写或重启，候选及测试在冻结目录保留。 `private-inline-worker-final-verify-20261031-bp`独占只读核验退出0，`private-inline-worker-final-verification.json`确认四项板端运行输入与实际SD2一致；最终核验后无新增GPU测量，恢复后645仍引用原BM实测。`private-inline-worker-final-source-hashes.json`记录最终源码。

本轮总清单漂移除两项源码/文档和Client构建Image外，含重新生成的submit实际函数片段/可执行文件及heap RSI模型；后者重新使用恢复的BM firmware-ops头，RMM生产源码没有变化。逐项旧/新SHA与来源记录于`private-inline-worker-prior-manifest-review.json`；候选生成模型有冻结输入，不冒充恢复后重新运行的结果。

ABI2/RPC4、能力34359738363、完整执行位清零和GPT/GPC模拟边界保持。广泛API、多Client、实体恶意Proxy/Client、动态OOM、并发销毁/公平性、可选eventfd及AE VM_BIND EBUSY仍未验收；整体目标未完成。


## BQ：实际缓存扫描与固件握手的分段计时（2026-10-31，诊断后恢复BM）

改动目的｜区分RMM页表/租约扫描、GPU固件ACK等待和其他控制成本｜BM645 → BQ642｜-3分/-0.47%｜仅RMM临时诊断变化，Client/Proxy/Host/initrd/runner相同；两轮均在固件重启后运行，GPU请求600/实际594MHz，CPU未锁恒频。组销毁后串口报告每行等2ms，统计本身及布局变化会扰动执行，不能作为性能优化候选｜`private-heap-720-20261031-bq`退出1，日志`build/lab-runs/private-heap-720-20261031-bq/`及`realm-evidence/summary.json`、`gpu-uart.log`、`evidence-transfer.json`｜**诊断完成，生产源码和SD2恢复BM645；整体目标未完成。** 恢复后未新增GPU测量，645引用原BM实测。

上一轮BP已证明立即排队等待从3.109→0.853µs/批，但645分未变；因此不再按COMPLETE总gap推算worker收益。BQ在现有策略锁内使用独立架构计数回调，仅累计calls/ticks/max，不参与授权、timeout或结果判定。`task_cache`分别记录设备交接和CPU归还；固件分别记录PREPARE_LAUNCH、READY_LAUNCH、START、START ACK循环、完成观察、STATUS ACK循环、QUIESCE及其SUSPEND/STOP ACK循环、FINISH。START/观察/QUIESCE的整函数计时是含子操作的；SUSPEND循环计时不包含之后的CS请求重置和AS detach，STOP循环亦在detach前结束；异常退出也记录已进入的等待。

没有增加RSI操作、Guest ioctl或跨VM查询接口。RMM在成功GROUP_DESTROY后打印累计快照，11项指标与BEGIN/END序号、退休数和24MHz频率绑定，每行间隔2ms缓解UART突发丢字。报告位于函数计时之后，但会改变整个程序的调度/缓存时序，不能宣称诊断完全无扰动。所有命令指针、页地址和客户数据不输出；临时内部header回调与读取函数在测量结束后一起移除，不留下无人使用的框架。

解析结果：52份完整快照接受，17份拒绝；选取第59份，累计164216次成功退休，少于当前Client文件的243042批，**完整统计覆盖FAIL**。末尾UART快照虽有BEGIN/END，内容仍存在拼接和缺字，不能恢复或补齐；不使用损坏记录中的完整局部指标来填充最终数据。首次要求完整覆盖的分析退出1，原输出和判定保留在`private-deep-profile-cost-first-attempt.json`及`private-deep-profile-profile-coverage-failure.json`。这里只讨论选定较早累计区间，不宣称最终全负载比例。只使用完整11项、序号匹配、频率正确、计数单调且子项不大于父项的快照；损坏快照整体排除，不拼接邻近片段。原始快照、排除原因和结果见`private-deep-profile-cost.json`。累计统计包括设置、预热、validation和此前group，不等于正式计分窗口或纯CPU时间。

| 含子调用的RMM计时 | 次数 | µs/调用 | µs/退休批次 |
| --- | ---: | ---: | ---: |
| cache_device | 173104 | 58.197 | 61.347 |
| cache_cpu | 173104 | 57.488 | 60.600 |
| prepare_launch | 164216 | 22.113 | 22.113 |
| ready_launch | 173104 | 238.129 | 251.017 |
| start_full | 1264952 | 28.377 | 218.586 |
| start_wait | 164216 | 150.707 | 150.707 |
| observe_full | 421650 | 93.769 | 240.766 |
| observe_wait | 421650 | 19.479 | 50.015 |
| quiesce_full | 510424 | 44.232 | 137.483 |
| quiesce_wait | 164216 | 88.806 | 88.806 |
| finish_full | 430538 | 121.339 | 318.123 |

以下各项相互不重叠，但只是已计时的部分，不能代表全部任务成本：

| 已计时的独立部分 | µs/退休批次 |
| --- | ---: |
| cache_device | 61.347 |
| cache_cpu | 60.600 |
| start_wait | 150.707 |
| observe_wait | 50.015 |
| quiesce_wait | 88.806 |

在选定部分累计区间内，PREPARE_LAUNCH+READY_LAUNCH+FINISH合计591.253µs/退休批次。不要再把START/OBSERVE/QUIESCE与包含它们的READY/FINISH相加。缓存扫描含实际叶项/BO归属/生命周期/租约检查、必要barrier和可能的页维护；固件等待含循环内缓存失效、读取和校验，不等于纯MMIO或GPU计算时长；计数器为墙钟，不能把未分类差额直接称作某一函数或SMC切换。

解析器另通过18项独立用例，覆盖完整记录、主机日志前缀、缺项、重复、错序、损坏数值、截断、回退计数、错误频率及子项超过父项；每次整体拒绝坏快照，保留上一份完整记录，不跨快照补值。命令`python3 build/rmm-client-bo-20261030/check-private-deep-profile-parser.py`退出0，`private-deep-profile-parser-tests.json`。

选定区间内，两向扫描合计约121.947µs/批，三种ACK轮询合计约289.528µs/批，分别占已计时PREPARE/READY/FINISH约20.63%和48.97%；这些比例只适用于这份部分累计区间，不是全应用占比或可直接实现的提分预测。下一步优先评估“可信待完成预检查”：仅对精确token和保护的完成记录给出提前INCOMPLETE，保留所有成功完成/错误/停止/缓存/退休检查，仍处理heap事件和原始期限。更大的候选是有界持久执行域，跨批保留AS/页引用，映射变化、CPU归还、销毁和故障时才完成可信停止；需要新的生命周期证明，不能据当前idle读数直接跳过SUSPEND。两项均未实现，记录`private-deep-profile-bottleneck-assessment.json`，不把研究方向冒充已完成优化。

本轮证据与验证（默认目录`build/rmm-client-bo-20261030/`）：

- 函数等价：`freeze-private-deep-profile.py`检查七项被包裹函数，移除明确的统计语句后与BM原函数语句相同，`private-deep-profile-policy-equivalence.json`；原580/2013条本地标记保持。两个命令分别为`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/deep-profile-unit bash scripts/check/check-rmm-gpu-private.sh`、`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`，退出0，日志`private-deep-profile-local.log`、`private-deep-profile-backend.log`。仅模型，不证明实体隔离或Linux并发安全。
- 启用计时模型：`python3 build/rmm-client-bo-20261030/check-private-deep-profile.py`退出0，实际335阶段平台/固件后端启用独立profile时钟，原timeout时钟不变；覆盖全部11项、计数器回绕、越界读取清零及原有任务正负例。遗漏CPU缓存计数、START/观察/停止等待记录四个实际核心错误副本均断言退出−6，`private-deep-profile-models.json`。首次误选只装载镜像/arena而不执行任务的夹具，零计数被新增断言拒绝；该次候选−6不算预期错误变体成功，保留`deep-profile-model-first-attempt/`及`private-deep-profile-model-correction.json`，更换完整任务夹具后才完成验证。冻结脚本曾误读资源schema的status字段、并把START首个调用误作函数定义，各自提前退出1后按实际schema/定义锚点修正；未改变生产检查或部署输入，见`private-deep-profile-freeze-corrections.json`。
- 构建：`build-private-deep-profile.py`和`build-private-deep-profile-firmware.py`退出0；23份O2 Debug/断言参数与原BF/BM相同，FIT和含BSS布局通过，RMM预留末址仍0x2800000。14个关键数组大小相同，地址逐项记录于`private-deep-profile-static-layout.json`，不假定位置全不变。RMM ELF SHA `d92fe3bdff073ac39fe95ceba5257c3490694b338d0520bb151555405c7f5e77`；40份输入源码冻结`private-deep-profile-source/`，运行包`private-deep-profile-candidate/`仅RMM ELF变化。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-deep-profile-20261031-bq --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-deep-profile --run-id firmware-private-deep-profile-20261031-bq`退出0，只写SD2，原启动区备份、UART、Host与Realm能力1恢复保存在对应`build/firmware-runs/`。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bq -- python3 build/rmm-client-bo-20261030/run-private-deep-profile-with-uart.py --images build/rmm-client-bo-20261030/private-deep-profile-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1；同租约实际SD2字节读回与候选一致，四项Guest/runner输入均未上传变更。完整33场景、COMPUTE_CHECK、VM0/0、两端解绑/日志、Host健康/CPU0–1/pmthor/资源和11份采集SHA通过；validation26/1/6仍含既有数值失败，可选eventfd仍errno2失败，1000门槛FAIL，不称完整API或隔离验收通过。
- 恢复：`restore-private-deep-profile-source.py`把五个源/header逐字节恢复BM，40份最终源码SHA全部一致；独占部署`firmware-private-deep-profile-restore-20261031-bq`只将SD2恢复`firmware-private-packed-tags/`，退出0。恢复后的私有/后端模型再次退出0，`private-deep-profile-restored-local.log`、`private-deep-profile-restored-backend.log`；计时专用夹具和错误变体只保留在冻结证据目录。独占只读`private-deep-profile-final-verify-20261031-bq`退出0，`private-deep-profile-final-verification.json`确认实际SD2与四项板端运行输入为BM；恢复后没有新GPU测量。

既有eventfd失败的追加源码分析：私有模式会在共享模式的unsupported分支之前转发给本地DRM core，后者在传入handle不存在时返回ENOENT；旧可选冒烟用零初始化handle并要求unsupported式错误，存在预期不匹配。`private-deep-profile-eventfd-followup.json`记录三份实际源码SHA及后续所需的有效syncobj/eventfd、timeline、异常与真实fence测试。本轮没有修改驱动/测试，不改变既有FAIL，不能凭此宣称eventfd硬件能力已通过，也不通过简单放宽errno掩盖未验证路径。

源码恢复脚本首次在已经完成40份BM恢复后因重复status键生成元数据失败；修正为显式合并，且重入仅接受完整诊断源码或精确BM状态，重新验证后继续。该失败及原状态记录`private-deep-profile-source-restore-correction.json`，不是GPU运行失败。

实际清单漂移逐项审查见`private-deep-profile-prior-manifest-review.json`。重新生成的测试程序、包含实际函数的片段及header依赖模型与源码输入对应，不能将诊断期间的生成二进制冒充恢复后的代码验证。能力34359738363、ABI2/RPC4、完整执行位清零和GPT/GPC模拟边界保持；AE EBUSY、可选eventfd、广泛API、多Client、实体攻击、动态OOM和并发销毁/公平性仍未验收。


## BR：FINISH可信待完成预检查（2026-10-31）

改动目的｜减少GPU仍在执行时的重复STATUS请求/ACK等待｜BM645 → BR634｜-11分/-1.71%｜仅RMM变化，Client/Proxy/Host/initrd/runner相同；两轮固件重启后运行，GPU请求600/实际594MHz、CPU未锁恒频。任务结构每项增加8字节/合计1024字节，布局变化和功能变化为组合效果，不分别归因｜`private-heap-720-20261031-br`退出1，日志`build/lab-runs/private-heap-720-20261031-br/realm-evidence/`、`gpu-uart.log`｜**撤回并恢复BM645；整体目标未完成。** 实验保留线652、整体1000门槛在部署前记录于`private-pending-precheck-plan.json`。

BQ的部分累计区间表明，固件握手比继续微调Guest worker更值得验证；并不能由该部分区间预测本轮提分。本轮没有新增深度计时接口或UART统计，不继承BQ不完整的全负载计时覆盖。

本轮候选修改`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c`，现已撤回，源码保留于`private-pending-precheck-source/`。仅Client专用FINISH启用可选待完成提示，公开COMPLETE和PROGRESS仍请求完整新鲜STATUS。入口先认证实际Client/service、精确token、组归属及运行状态，再调用原START重放，检查实际root/AS、全stream错误和父/子请求状态。只有完整发布的任务才尝试提示；完成页地址由RMM组记录和受保护控制对象解析，不接受Proxy/Client提供页地址。读取当前队列的64位完成序号，以CPU私有history确定起始基数。序号在本任务合法区间内但落后于目标时，只返回`INCOMPLETE=[0,queue,0,0]`。提示不发布成员完成掩码，不改变完成/停止状态，不归还CPU缓存、不退休、不释放BO/AS引用或发布fence。

每连续四次提示后强制走原完整STATUS路径；计数已到达、超前/旧计数、不可读或部分发布都不获得提示权限。此限制使长期停滞的任务仍周期性刷新各stream状态，而不是无限信任旧状态。完整路径仍保留新STATUS ACK、全部队列idle/error/消费位置/序号、后置root检查、SUSPEND、AS flush/disable、CPU归还和精确退休。CPU/GPU可能并发更新计数，撕裂或过时值最多影响等待提示，不能授权成功。Client原有每次pending后的heap服务及原始绝对期限保持；在下一次提示前也重新执行完整START重放。不将上述模型证明扩大为实际恶意GPU、CPU并发或硬件GPC隔离证明。

本轮累计FINISH阶段每批墙钟523.667→484.388µs（−7.50%），但effect2d 5×5卷积场景帧时1.713→8.018ms、terrain62.389→73.999ms，全部场景帧时变化中位数−0.136%。累计窗口含设置/预热/validation与调度，不是正式计分窗口或纯RMM时间；没有提示命中计数，不能将变化归因为精确次数、额外页读取或任务布局，也不能把单轮异常认定为稳定退化。结果只证明本轮未达到预先记录的整体保留条件，不证明该思路在所有负载都无收益。见`private-pending-precheck-comparison.json`。

所有新增状态均为RMM私有；增加一个字节计数后因结构对齐使128个task合计增长1024字节，其他13个关键数组大小相同，14项实际地址/大小记录`private-pending-precheck-static-layout.json`。RMM预留末址仍0x2800000，FIT/含BSS布局PASS；23份编译选项与原BF相同，O2 Debug/断言保留。ABI2/RPC4、能力34359738363及完整执行位清零不变。原完整observer除可选提示分支和私有参数外逐字节相同，FINISH其余语句不变，见`private-pending-precheck-policy-equivalence.json`。

验证与证据（默认目录`build/rmm-client-bo-20261030/`）：

- 本地私有回归：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/pending-precheck-final-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-pending-precheck-final-local.log`含595条PASS标记，其中原580条逐项保持；新增实际helper的15项模型覆盖多队列、q31、私有历史基数、旧/未来/最大值、未完整发布、读失败和边界。标记数不等于独立测试数量。
- 实际后端：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-pending-precheck-backend.log`含2165条PASS标记，原2013条顺序/内容保持；两份Client模型各执行19项新增场景，检查完整身份校验、四次提示上限和重新计数、到达/无效计数不能跳过完成检查、读取失败回退、旧ACK拒绝、提示前后root/stream/global故障、引用保持、公开COMPLETE/PROGRESS仍新鲜及真实CPU归还/退休。仅模型，不替代硬件多Client。
- 错误变体：`check-private-pending-precheck-models.py`分别运行`unbounded`、`early_success`、`complete_uses_hint`和`skip_start_check`，四项构建退出0、运行均断言退出−6，`private-pending-precheck-models.json`；冻结41项源码`private-pending-precheck-source/`。首次错误变体构建遗漏公共header搜索路径，四项均编译退出1，没有执行；补充公共include回退后才得到上述运行拒绝。原目录`pending-precheck-model-first-attempt/`及`private-pending-precheck-model-correction.json`保留，编译失败不计作预期拒绝。
- 新后端夹具首轮对失败后保留的AS root只检查低32位；合法root低32位可为0，使新断言失败，退出134。修正为已有64位words64读取后整套重新通过，生产检查未修改；原日志`private-pending-precheck-backend-first.log`及`private-pending-precheck-backend-correction.json`保留。
- 构建/部署：`build-private-pending-precheck.py`、`build-private-pending-precheck-firmware.py`退出0；候选RMM SHA `61c90d8dae7bd8c1f3ee5ea7f0edf25adfdba87a89f52411c224fa5d83f0c61b`。`python3 scripts/maintenance/lab-run.py --run-id firmware-private-pending-precheck-20261031-br --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-pending-precheck --run-id firmware-private-pending-precheck-20261031-br`退出0，只写SD2，Host/Realm能力1恢复。
- 测量：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-br -- python3 build/rmm-client-bo-20261030/run-private-pending-precheck-with-uart.py --images build/rmm-client-bo-20261030/private-pending-precheck-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。同一租约先回读候选SD2实际字节；完整33场景、计算、VM0/0、两端解绑/日志、Host健康/CPU0–1/pmthor/资源、11份采集文件SHA通过。validation26/1/6含已知数值例外，可选eventfd失败保留；1000门槛FAIL。不宣称完整正确性/广泛API/实体隔离验收通过。
- 最终状态：撤回并恢复BM645，实际板端四项运行输入及SD2逐字节核验`private-pending-precheck-final-verify-20261031-br`退出0，`private-pending-precheck-final-verification.json`。四项源码/header/测试脚本恢复BM，新增helper夹具从活动源码移除、只在冻结证据目录保留；恢复后的本地/后端模型重新通过，恢复后没有新增GPU性能测量，645引用原BM实测。

总体目标仍未完成。1000性能门槛失败，因此未扩展广泛API、多Client和隔离硬件矩阵。 AE VM_BIND EBUSY、eventfd、实体恶意Proxy/Client、动态OOM实体覆盖和并发销毁/公平性问题保留，GPT/GPC仍按实验平台模拟边界描述。


## BS：受保护映射集合复用（2026-10-31）

改动目的｜减少相同映射上的重复逐叶页表扫描｜BM645 → BS706｜+61分/+9.46%｜仅RMM固件变化，Client/Proxy/Host/initrd/runner与BM一致；两轮均在固件重启后，GPU请求600/实际594MHz、CPU未锁恒频，单轮。缓存元数据和代码布局同时变化，不单独归因｜`private-heap-720-20261031-bs`退出1，日志`build/lab-runs/private-heap-720-20261031-bs/realm-evidence/`和`gpu-uart.log`｜**保留BS706实验候选；整体目标未完成。** 预先记录的实验保留线652，整体性能门槛1000，`private-mapping-summary-plan.json`。

### 机制与成立条件

RMM在第一次完整READY扫描后记住“这个context当前映射了哪些BO”。该记录仅由实际受保护的leaf tag/PTE扫描生成，包含完整context handle、非回绕mapping epoch和BO位图，不接受Proxy提供对象集合。接下来的READY/RETURN只有在context代数、epoch完全一致时才复用；对记录中的每个BO重新检查实际owner/service、closing、mapped/控制页引用、NC/驻留类型、完整隐藏前缀和本批缓存租约。先完整预检，再在同一策略锁内获取租约；不能借旧记录绕过另一个context正在占用同一BO的限制。NC交接仍执行真实顺序屏障，驻留页保持CPU隐藏，WB混合上下文始终执行原逐页物理缓存维护。

该优化建立在既有平台假设上：真实GPU PT、leaf tag和RMM元数据受保护，只能由RMM在策略锁下修改。所有MAP/UNMAP、控制映射与运行中heap扩容在修改leaf前推进非回绕epoch；失败/部分变更也不会继续使用旧记录。实际映射的引用阻止BO槽位回收复用。context采用完整代数handle，不能仅凭相同槽位复用旧记录。它不提供任意RMM内存损坏检测；原路径也信任table_owner、leaf_groups等私有索引。内部`protected_mapping_summary`只由可信适配器静态启用，没有新增RSI/Proxy接口；不具备该保证的后端和对照模型使用原扫描。

记录是4项有界关联缓存，新增记录与替换游标合计612字节，原14个关键数组容量、32个context/1024个BO/448张Client表及0x2800000预留保持。记录被替换仅损失优化；分批扫描中途被替换，后续扫完尾部也不能发布完整记录，必须下一次从cursor零开始。可信整体reset清空所有记录。首次32份记录方案增加4864字节并超过当前RMM链接大小限制，构建失败未部署；修正为4项后，23份O2 Debug编译选项与BF一致，全部断言保留，ARM64链接、FIT/ELF一致性和含BSS布局通过。

本轮没有保留运行中的CSG/AS，没有更改完成通知、原始截止时间或fence发布时机。`opencca_gpu_firmware.c`与实际平台`rk3588_gpu.c`、任务退休和映射变更代码与BM逐字节一致：fresh STATUS/ACK、全部stream错误/scoreboard/队列进度、真实SUSPEND、FLUSH_MEM、AS禁用和CPU归还仍由原链路执行。复用记录既不是GPU完成证明，也不是缓存一致性证明。

### 实测与边界

READY/PUBLISH/START累计每批墙钟259.540→200.275µs（-22.83%）；FINISH/RETURN/RETIRE 523.667→455.729µs（-12.97%）；33场景帧时变化中位数-8.391%。这些是含设置、预热、validation和调度的累计窗口，非纯RMM/CPU成本，也非正式计分窗口内的精确开销。没有新增记录命中计数，不据此宣称确定的命中率、可节约时间或稳定提分。完整场景与阶段数据见`private-mapping-summary-comparison.json`。

- 本地：`GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/mapping-summary-bounded-unit GPU_CACHE_SET_OUT=build/rmm-client-bo-20261030/mapping-summary-bounded-suite-models bash scripts/check/check-rmm-gpu-private.sh`退出0，581条PASS标记，原580条逐项一致；`bash scripts/check/check-dma-guard.sh`退出0，2013条原标记保持，后端启用新内部策略。标记数不等于独立场景数。日志`private-mapping-summary-bounded-unit.log`和`private-mapping-summary-bounded-dma.log`。
- 编译条件复核：首轮本地模型使用系统cc默认优化，随后用前轮相同`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2`重跑完整私有/后端套件，退出均0、581/2013条标记逐项保持；新28组模型始终显式O2。日志`private-mapping-summary-o2-unit.log`、`private-mapping-summary-o2-dma.log`。初次封存因固定路径模型可执行文件哈希改变被保护检查拒绝，未改canonical manifest；O2重跑后仅实际受核心/header变更影响的heap/reclaim/RSI/backend可执行文件仍不同，已逐项核对编译来源，`private-mapping-summary-inherited-differences-o2.json`。
- 新模型：`GPU_CACHE_SET_OUT=build/rmm-client-bo-20261030/mapping-summary-final-models python3 scripts/check/check-gpu-cache-set.py`退出0。实际核心源码的28组场景分别运行参考/复用路径，涵盖NC/驻留/WB混合、同Client别名租约、双owner独立页、错身份/token、未停止CPU归还、映射epoch、context槽位复用、reset、16500页分批、控制页映射/撤销、NC/WB heap扩容及缓存替换。直接修改closing/hidden等项属于白盒故障注入，不是实体恶意Client攻击。6个错误变体构建退出0、运行均断言−6：epoch、lease、barrier、closing、early_valid、hidden。证据`mapping-summary-final-models/result.json`，仅模型，不构成实体隔离证明。
- 失败保留：驻留BO夹具误请求EXEC、heap扩容夹具误用低于32页的对象、首个lease变体未消费for_cpu导致编译失败、单独去掉WB eligible检查因第二重页数条件仍安全而未被拒绝，以及首个RMM链接超限，分别保留原日志和源码副本。编译失败、等价变体不计作运行拒绝；修正说明`private-mapping-summary-corrections.json`。
- 构建/部署：`build-private-mapping-summary.py`首次链接失败；`cmake --build build/rmm-client-bo-20261030/rmm-build-mapping-summary -j8`修正后退出0，`build-private-mapping-summary-firmware.py`退出0。候选ELF SHA `841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`。`python3 scripts/maintenance/lab-run.py --run-id firmware-private-mapping-summary-20261031-bs --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-mapping-summary --run-id firmware-private-mapping-summary-20261031-bs`退出0，仅写SD2，Realm能力恢复为1。
- 硬件：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bs -- python3 build/rmm-client-bo-20261030/run-private-mapping-summary-with-uart.py --images build/rmm-client-bo-20261030/private-mapping-summary-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1。完整33场景、实际计算、VM0/0、两端unbind/日志、Host健康/pmthor/CPU0–1/资源及11份采集SHA通过；validation26/1/6仍含已知数值失败，可选eventfd仍FAIL。1000门槛FAIL。AE VM_BIND EBUSY尚未被证明解决。
- 最终：保留BS706实验候选，运行包`build/rmm-client-bo-20261030/private-mapping-summary-candidate`，配套`build/rmm-client-bo-20261030/firmware-private-mapping-summary`。42项候选源码冻结于`private-mapping-summary-source/`；当前源码清单`private-mapping-summary-final-source-hashes.json`。板端四项运行输入及实际SD2回读`private-mapping-summary-final-verify-20261031-bs`退出0，`private-mapping-summary-final-verification.json`。ABI2/RPC4、能力34359738363、完整执行位仍清零。保留实验组合，不将其称为完整安全冻结基线。

整体目标仍未完成。性能门槛失败，本轮未扩展广泛API、多Client和实体攻击矩阵。 GPT/GPC按实验平台模拟边界描述，不声称RK硬件已提供完整CCA隔离。下一步优先依据整体负载证据判断启动/停止与映射失效频率的成本，不能用删除真实停止条件换取分数。


## BT：同次调用内启动配置传递实验，706→707，撤回

改动目的｜减少完成观察前重复的可信配置读取｜BS706 → BT707｜+1/+0.14%｜仅RMM候选变化，Client/Proxy/Host/initrd/runner相同、CPU未锁恒频，两轮均在固件重启后执行｜`private-heap-720-20261031-bt`，退出1，日志`build/lab-runs/private-heap-720-20261031-bt/realm-evidence/`｜未达到预设714保留线，撤回并恢复BS706；1000门槛FAIL，整体目标未完成。

候选把原START实现封装为文件内的`task_start_checked()`，仅在完整检查成功后，向当前调用栈输出同一次验证的根地址和配置。`task_observe()`立即使用该结果，省去一次根地址获取和一次重复配置读取；没有跨调用缓存，也没有Proxy可传入的“检查证明”。原START函数体除成功出口的栈输出外逐字节保持，公开接口、身份与任务绑定、fresh STATUS/ACK、全部stream错误检查、队列读取后的完整复查，以及停止/AS禁用/缓存归还/退休保持。最初考虑的START/STATUS合并没有实施：START确认不会刷新CS快照，不能据此删除后续独立STATUS确认。

后端模型中的成功完成路径由353次MMIO读取、6次配置检查降到334次、5次。已有私有内存套件581条、后端套件2013条`=PASS`标记保持；后端155行仅统计值变化，逐行核对为每减少一次配置检查对应19次读取，其他语义字段保持。标记数不是独立场景数。这些是模型成本，不能直接换算为实体CPU耗时。实际累计FINISH/RETURN/RETIRE每批455.729→453.354µs（-0.52%），READY/PUBLISH/START 200.275→200.095µs（-0.09%），33场景帧时变化中位数-0.10%。统计包含设置、预热和validation，且单轮未锁CPU频率，不证明稳定收益或具体场景的因果关系。

- 本地最终源码：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/checked-config-final-unit GPU_CACHE_SET_OUT=build/rmm-client-bo-20261030/checked-config-final-cache-models bash scripts/check/check-rmm-gpu-private.sh`退出0；同一`HOST_CC`运行`bash scripts/check/check-dma-guard.sh`退出0。日志`private-checked-config-final-unit.log`、`private-checked-config-final-dma.log`。首轮中间实现随后改为同时输出root/config，最终两套测试和ARM64构建使用冻结后的最终源码，不能用首轮结果代替。
- 构建：`python3 build/rmm-client-bo-20261030/build-private-checked-config.py`、`python3 build/rmm-client-bo-20261030/build-private-checked-config-firmware.py`退出均0。23份编译选项文件与BS相同，O2 Debug/断言及0x2800000预留保持；ELF text/data/bss尺寸分别266896/358800/37730452字节，与BS相同。FIT/ELF一致性和含BSS布局检查退出均0。候选ELF SHA `8fea256aedfd480c2e8a2e3b0013f239e3b9ff5bbd2a87abdb6d6633f0be6326`。
- 部署：`python3 scripts/maintenance/lab-run.py --run-id firmware-private-checked-config-20261031-bt --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-checked-config --run-id firmware-private-checked-config-20261031-bt`退出0，仅写SD2；实际回读匹配。
- 硬件：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bt -- python3 build/rmm-client-bo-20261030/run-private-checked-config-with-uart.py --images build/rmm-client-bo-20261030/private-checked-config-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，原因是完整720p低于1000。33场景结束、计算预热、VM0/0、两端解绑与日志回收、Host健康/pmthor/CPU0–1/资源恢复及11份证据SHA通过；validation26/1/6包含已知数值失败，可选eventfd仍FAIL，不能写作完整正确性全部通过。AE VM_BIND EBUSY未证明解决，多Client/实体攻击NOT_RUN。
- 撤回：`python3 build/rmm-client-bo-20261030/restore-private-checked-config-source.py`退出0，42份源码哈希恢复BS；重新以O2执行后端套件，2013条标记与BS逐字节一致，日志`private-checked-config-restored-backend.log`。恢复后未重跑整个私有套件：源码与已测BS完全相同；这一点不扩大实体测试保证。固件恢复run-id `firmware-private-checked-config-restore-20261031-bt`，相同部署入口使用`firmware-private-mapping-summary`，退出0。最终只读核验run-id `private-checked-config-final-verify-20261031-bt`，板端四项运行输入和实际SD2匹配，退出0；回退后没有新增GPU测量，706为原BS实测。

初次比较脚本把普通PASS文字计入标记，并遗漏FINISH的预期统计字段变化，比较断言失败；修正为精确`=PASS`标记并核对每项读取/检查差值后通过，不能把比较器错误记为GPU或安全模型失败。候选源码、镜像、测试与失败门槛证据保存在`build/rmm-client-bo-20261030/`中的`*checked-config*`记录；最终生产源码已删除候选helper并恢复BS。最新检查点为`private-checked-config-checkpoint-record.json`和`independent-private-checked-config-checkpoint.json`。

这一轮说明该处重复MMIO读取不是足够大的整机瓶颈，后续应优先评估启动/停止和任务生命周期的整体成本。持续执行需要独立的受保护执行租约及新的生命周期、映射变更和并发证明，尚未实现；不能直接删去真实停止、缓存归还或安全回收条件。ABI2/RPC4、能力34359738363、完整执行位清零及平台GPT/GPC模拟边界保持。


## BU：依赖任务切片合并，完整720p707，撤回并恢复BS706（2026-10-31）

本轮尝试把已排队、CPU输入已准备好的同组依赖任务合成至多6个成员的切片，减少反复缓存交接、启动、停止和退休。只改Client；使用已有RMM `READY / PUBLISH / START / PROGRESS / FINISH`，RMM、Proxy、ABI2/RPC4与固件不变，能力仍为34359738363，完整执行位4清零。

**结果：BS706 → BU707，+1分/+0.14%，低于测量前设定的714分保留线；已撤回，当前继续使用BS706。** 场景帧时变化中位数−0.174%；READY/发布/启动墙钟每批200.275→199.634µs，完成/归还/退休455.729→455.447µs，均不能据单轮宣称稳定加速。两次同一完整720p配置，只有Client Image改变，RMM/Proxy/Host/initrd/runner相同；BU没有刷写或重启，BS在固件部署后测量，CPU均未锁恒频。恢复后未新增GPU测量，保留706引用原BS结果。

实际退休269365批中，269358批为单成员；仅7个依赖批次包含20个成员，发生34次进度查询、20次累计发布。依赖批次只占0.00260%。本轮证明这条路径能实际运行，但可合并机会太少，不能证明其有整体加速作用；也不能据此断言它对其他依赖密集负载无效。下一步应针对实测的单成员关键路径，不继续扩大没有工作负载依据的批处理框架。

候选中的保护与语义边界：

- 仅把“精确直接fence等于同组已选前驱done”的依赖纳入切片；无法识别的timeline链、数组及未完成外部输入继续等待。整批成员在READY前冻结，运行中不追加任务。
- 初次发布无内部依赖的成员；后续必须得到新鲜、成功的RMM PROGRESS，再发布满足依赖的累计队列前缀。进度回退或声称完成未发布成员会失败；进度不代表CPU可见完成或安全回收。
- 保留真实FINISH中的停止、AS禁用、缓存归还和退休；整批退休后才发布独立输出fence成功。后继或最终退休失败时，已观察GPU完成的前驱也保守返回错误；不宣称原生逐任务错误定位完全相同。
- 不确定的PREPARE、START或发布响应不重放；仅RMM确认未准备任务已取消后，才允许用新token重试容量准入。保留最早成员的绝对期限、最多6成员、映射等待票据和关闭后的引用保护。

验证与保留证据：

| 项目 | 本轮结果 / 证据 |
| --- | --- |
| 完整本地模型 | `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/deferred-slice-unit bash scripts/check/check-rmm-gpu-private.sh`，退出0，581条精确`=PASS`标记；原标记仅提交场景数101→134 |
| 新增提交场景 | 33项，覆盖同/跨队列链、菱形依赖、部分进度、不透明timeline、外部输入、错误/丢回复、进度回退、OOM等待、关闭、容量上限及期限；ASan/UBSan/断言保留，仅Host doubles，不代表Linux并发完整证明 |
| 错误变体 | 6个均编译成功并运行拒绝：提前发布、把已发布当完成、忽略发布错误、拆开不透明chain、忽略进度完整性、提前发布外部fence |
| ARM64构建 | `make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`，退出0；补丁清单检查退出0 |
| 完整720p | run-id `private-heap-720-20261031-bu`，退出1仅因1000门槛；33场景/计算预热、VM0/0、两端解绑/日志、Host健康及资源恢复通过，11份回收文件SHA一致 |
| 已知失败 | validation为26成功/1个已知数值失败/6未知；可选eventfd仍FAIL。AE VM_BIND EBUSY未解决，广泛API、多Client与实体隔离攻击NOT_RUN |
| 恢复 | `private-deferred-slice-restore-20261031-bu`，退出0，无刷写/重启；板端四项输入及实际SD2字节哈希为BS；源码42项与BS相同，恢复后提交模型101项通过 |

完整硬件命令（凭据只由环境变量提供）：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bu -- \
  python3 build/rmm-client-bo-20261030/run-private-deferred-slice-with-uart.py \
  --images build/rmm-client-bo-20261030/private-deferred-slice-candidate \
  --private-gpu --workload glmark --performance --benchmark-only \
  --suite --profiles glmark-720 --clients 1
```

候选Client SHA `423b48a1286485f924358592c018118063c08488e0bd378220b6e0fbcec44830`，只作证据，不是当前载荷。当前Client仍为`7389969e4a5751554d15c299d5a0f6a262118d4fa48a630a2745f78b6a8c2b29`，RMM为`841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`。候选42项源码位于`build/rmm-client-bo-20261030/private-deferred-slice-source/`；生产代码及测试夹具已撤回，不保留未使用分支。

日志：`build/rmm-client-bo-20261030/private-deferred-slice-{unit,submit-final,hardware,restore,restored-submit}.log`、`client-private-deferred-slice-final.log`及`build/lab-runs/private-heap-720-20261031-bu/`。严格分析、对比、设计审查、错误变体、恢复和检查点分别为该目录下`private-deferred-slice-{bu-hardware,comparison,design-review,mutants,runtime-restored,checkpoint-record}.json`。

统一记录：依赖任务在完整RMM租约内分批发布｜BS706→BU707｜+1/+0.14%｜只有Client变化、CPU未锁恒频、BU无重启，单轮不证明稳定收益｜上述run-id/命令/退出码/日志｜未达714保留线，撤回恢复BS706；1000门槛FAIL，整体目标未完成。


## BV：队列资格诊断，完整720p707，撤回并恢复BS706（2026-10-31）

BU只命中7个依赖切片，不能直接推出“没有足够的排队任务”。本轮只增加Client文件生命周期内的聚合计数，区分picker入口待处理深度、首个未完成依赖的形态、与已选同组前驱的精确匹配，以及成功提交的成员数/提交时是否已有run。没有增加fence状态查询、chain遍历、执行授权或提前完成；worker和run_finish与BS逐字一致，RMM/Proxy/ABI/完成与回收检查保持。

**测量：BS706 → BV707，+1分/+0.14%；这是诊断运行，始终撤回，不据此宣称优化收益。** 同一完整33场景720p、单Client配置，仅Client Image改变，RMM/Proxy/Host/initrd/runner相同，无刷写/重启，CPU未锁恒频；单轮不能证明稳定变化。恢复后未新增GPU测量，当前706引用原BS。

| 观察项 | 结果 | 正确解释 |
| --- | ---: | --- |
| 成功IOCTL提交 | 269359次，全部1成员 | 上层没有使用一次IOCTL提交多个成员；不代表跨IOCTL无法合批 |
| picker入口 | 269377次；深度1为240370次（89.23%），深度≥2为29007次（10.77%） | 多数观察只有一个待处理任务，但积压确实存在；不是时间加权占比 |
| 首个阻塞依赖 | direct343685次、chain6次 | 每个job仅看首个未完成依赖，同一job可能反复计数；后续chain/数组/外部依赖未观察 |
| 首阻塞匹配已选同组前驱 | direct28992次、contained-chain0次 | 只说明一个依赖匹配，其他依赖仍可能阻止合批，不能当作28992个可合批任务 |
| 提交时已有run | 11896次（4.42%） | run可能处于准备或退休阶段，不是GPU同时执行率 |
| 映射等待阻塞 | 12次 | 仅统计原有ready判断已成功之后的映射等待条件 |

这组数据没有证明“timeline限制不重要”，也没有证明“没有批处理空间”：代码首先加入同队列tail，再加入显式同步依赖，前一个direct阻塞可能遮住后续chain。因此不应根据首个依赖的6次chain直接实现解链优化，也不应把28992次匹配当成可实现的收益。下一次若继续这一方向，应先观察完整依赖集合或重放不可变依赖快照，明确阻塞原因；不能仅凭`dma_fence_chain_contained()`就放行整条链。其他单任务关键路径优化同样须有实测依据。

验证与证据：

- 本地：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/eligibility-unit bash scripts/check/check-rmm-gpu-private.sh`，退出0，581条精确`=PASS`标记列表与BS一致；实际源码提交模型101项通过。Host doubles不证明Linux并发或实际隔离。
- 构建：`make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`，退出0；补丁清单检查退出0。
- 硬件：run-id `private-heap-720-20261031-bv`，退出1，错误为`private full-720p score below 1000`；完整33场景、计算预热、VM0/0、两端解绑/日志、Host健康与资源恢复通过，11份回收文件SHA一致。validation26/1/6含既有数值失败，可选eventfd仍FAIL；AE VM_BIND EBUSY未解决，广泛API、多Client/实体隔离攻击NOT_RUN。
- 撤回：`private-eligibility-restore-20261031-bv`，退出0；42项源码与BS一致，板端四项输入及实际SD2字节哈希核验通过，无刷写/重启；恢复后提交模型101项通过，无新增GPU测量。增量构建目录Image仍是归档诊断输出，运行基线使用冻结BS载荷，不把两者混用。

完整硬件命令（凭据仅在环境变量）：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bv -- \
  python3 build/rmm-client-bo-20261030/run-private-eligibility-with-uart.py \
  --images build/rmm-client-bo-20261030/private-eligibility-candidate \
  --private-gpu --workload glmark --performance --benchmark-only \
  --suite --profiles glmark-720 --clients 1
```

诊断Client SHA `a26655d01863884405b6aaf0227645bfe7757e8f6df95ebeb0ff7f385950d711`；当前BS Client仍为`7389969e4a5751554d15c299d5a0f6a262118d4fa48a630a2745f78b6a8c2b29`，RMM为`841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`。诊断源码/载荷分别保留于`private-eligibility-source/`和`private-eligibility-candidate/`，生产代码中不保留诊断分支。

证据根目录`build/rmm-client-bo-20261030/`：`private-eligibility-{plan,design-review,candidate-validation,bv-hardware,runtime-restored,checkpoint-record}.json`，`private-eligibility-{unit,submit,hardware,restore,restored-submit}.log`，`client-private-eligibility.log`及`build/lab-runs/private-heap-720-20261031-bv/`。ABI2/RPC4、能力34359738363和完整执行位4清零保持。

统一记录：定位依赖合批的真实资格｜BS706→诊断707｜+1/+0.14%｜仅Client计数变化、CPU未锁恒频、无重启，不作提分归因｜上述run-id/命令/退出码/日志｜诊断已撤回，恢复BS706；1000门槛FAIL，整体目标未完成。


## BW：完整待满足依赖形态诊断，720p708，撤回并恢复BS706（2026-10-31）

BV只观察首个未完成依赖，而实际代码先加入队列tail，再加入显式同步，存在遮挡。本轮保留原始ready返回决定，在其发现第一个pending依赖后，顺序探测该job的全部依赖，记录内部直接fence、未完成chain和其他未完成非chain对象。只用contained指针分类，不遍历或放行chain。额外`dma_fence_get_status()`可能推进已完成fence的信号状态，诊断因此可能改变后续观察时机；不能声称完全没有测量干扰。worker和run_finish与BS逐字一致，RMM、Proxy、ABI及所有完成/停止/回收检查不变。

**BS706 → 诊断BW708，+2分/+0.28%；始终撤回，不作为性能优化收益。** 同一单Client完整720p、33场景配置；仅Client诊断镜像变化，RMM/Proxy/Host/initrd/runner相同，无刷写/重启，CPU未锁恒频，单轮不证明稳定变化。恢复后没有新增GPU测量，当前分数仍引用BS706。

| 统计项 | 次数 | 含义 |
| --- | ---: | --- |
| 首个依赖阻塞触发全依赖探测 | 342176 | 同一job可反复观察，不是342176个任务 |
| 被探测的依赖 | 684352 | 顺序探测，不是同一时刻不可变快照 |
| 首阻塞chain | 7 | 重现BV的观测盲点 |
| 全部探测中的pending chain | 342125 | 前面的direct依赖遮住了后续chain |
| job存在内部直接匹配 | 28762 | 等待的一个direct fence等于已选同组成员done |
| 内部匹配且同时有pending chain | 28748（99.95%） | 仅识别直接fence仍无法合批的主要依赖形态 |
| 全部pending依赖仅为内部direct | 14 | 不是14个唯一可合批任务；仍受容量、期限和映射等待约束 |
| pending chain的contained恰为已选成员 | 28751 | 只证明当前点匹配，不证明链中所有前驱满足 |
| 内部匹配且另有pending非chain外部对象 | 0 | 此条观察路径中未见该类附加阻塞；不代表全工作负载无外部依赖 |

结果支持将下一项修改收敛到**有界的整链依赖闭包检查**。BU的直接fence匹配方案无法覆盖上述广泛存在的第二个timeline依赖，先前“没有合批任务”的推断不成立。但本轮未检查chain所有前驱，无法据此给出可合批任务数或预测收益，更不能只看contained点就放行。

拟验证路径尚未实现：逐节点持有RCU安全引用，设置固定额外遍历预算；每个未完成叶子都须精确匹配已选同组的较早任务，未识别对象、pending数组/嵌套结构及预算耗尽继续等待，错误和原始期限保留。整批在READY前冻结，继续用RMM的新鲜PROGRESS和累计PUBLISH控制GPU依赖，外部fence仍只在真实FINISH完成停止、AS禁用、CPU归还与退休之后成功；不把进度当作安全回收证明。需要覆盖旧前驱、未知输入、错误、预算边界、引用释放及错误变体，再测完整720p。

验证与证据：

- 实际源码模型：110项提交场景，新增9项验证隐藏chain、未完成旧前驱、contained非当前点、外部输入、错误及跨组/无选中run；原始ready结果、任务/期限与引用计数保持。`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-private-submit.py`退出0。
- 完整本地检查：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/dependency-shape-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，581条精确`=PASS`标记；除提交场景数101→110外原标记一致。模型使用Host doubles，不证明Linux并发、RMI实体隔离或GPU恶意命令防护。
- ARM64 Image构建退出0，补丁清单`python3 opencca/scripts/setup/apply-local-patches.py --check`退出0。镜像构建命令为`make -C Linux-Guest-GPU O=/home/mzh/gpu/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`。
- 硬件run-id `private-heap-720-20261031-bw`，退出1仅因1000门槛；完整33场景、计算预热、VM0/0、两端解绑/日志、Host健康与资源恢复通过，11份日志SHA一致。validation26/1/6含既有数值失败，可选eventfd仍FAIL；AE VM_BIND EBUSY未解决，广泛API、多Client/实体隔离攻击NOT_RUN。
- 恢复run-id `private-dependency-shape-restore-20261031-bw`退出0：42项源码与BS相同，板端四项输入和实际SD2字节SHA核验通过，无刷写/重启；恢复后提交模型101项通过，无新增GPU测量。增量开发Image仍为诊断输出，不能替代冻结BS运行载荷。

硬件命令（凭据仅在环境变量）：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bw -- \
  python3 build/rmm-client-bo-20261030/run-private-dependency-shape-with-uart.py \
  --images build/rmm-client-bo-20261030/private-dependency-shape-candidate \
  --private-gpu --workload glmark --performance --benchmark-only \
  --suite --profiles glmark-720 --clients 1
```

诊断Client SHA `d3e07f406937adfe195182fc4b0b960d8461181156d17009bf567c4323dfc08d`；当前BS Client仍为`7389969e4a5751554d15c299d5a0f6a262118d4fa48a630a2745f78b6a8c2b29`，RMM仍为`841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`。ABI2/RPC4、能力34359738363及完整执行位4清零保持。

证据根目录`build/rmm-client-bo-20261030/`：`private-dependency-shape-{plan,design-review,candidate-validation,bw-hardware,runtime-restored,checkpoint-record}.json`，`private-dependency-shape-{unit,submit,hardware,restore,restored-submit}.log`，`client-private-dependency-shape.log`，冻结42项源码/镜像分别位于`private-dependency-shape-source/`和`private-dependency-shape-candidate/`，硬件日志位于`build/lab-runs/private-heap-720-20261031-bw/`。

统一记录：发现被首个队列tail遮挡的显式依赖｜BS706→诊断708｜+2/+0.28%｜仅Client诊断探测变化、CPU未锁恒频、无重启，不作提分归因｜上述run-id/命令/退出码/日志｜诊断已撤回恢复BS706；有界整链检查待实现，1000门槛FAIL，整体目标未完成。

## BX：整链依赖闭包，720p706，无整体收益，撤回恢复BS706（2026-10-31）

BW确认第二个timeline依赖被首个队列tail遮住。本轮在BU的依赖任务执行骨架上实现整链检查，**不是仅比较chain当前contained点**：持有当前节点引用，RCU临界区内通过`dma_fence_get_rcu_safe()`取得prev引用；检查每个contained叶子及末尾非chain前驱。每个job的全部pending依赖共享64次额外节点访问预算，只有所有未完成叶子精确匹配已选同组前驱done fence时才合并掩码。未知pending对象、嵌套chain/array、错误、预算耗尽或缺少run均回退原等待，退出时平衡引用。不宣称限制了原生get_status内部遍历或RCU重试的全部成本。

历史已失败前驱不一定由原生timeline向后传播，因此错误不能被改写成新增的提前失败；保留原始ready对整体完成和当前点错误的规则。最多6个成员在READY前冻结，先发布根任务，RMM新鲜PROGRESS才能解锁累计的队列PUBLISH；任何不确定启动/发布都不重放。对外fence仍须等整批真实FINISH完成停止/挂起、AS禁用、CPU归还及退休，内部进度不是回收证明。worker与BU相同，run_finish与BS相同，RMM/Proxy/ABI/固件未改。

**BS706→BX706，0分/0%，低于预设714保留线，已撤回。** 同一单Client、完整720p/33场景、GPU与池配置；只有Client Image变化，RMM/Proxy/Host/initrd/runner保持，无刷写或重启，CPU未锁恒频。单轮结果不证明稳定性，恢复后未新测GPU，当前706引用原BS实测。

| 观测 | BS或前轮对照 | BX | 解释 |
| --- | ---: | ---: | --- |
| 完整720p得分 | BS706 | 706 | 无整体收益，1000门槛FAIL |
| 实际依赖切片/成员 | BU 7/20 | 5847/20275 | 整链检查覆盖了此前无法合批的任务，BU是历史机制对照 |
| 经整链闭包纳入合批的任务 | BU无此检查 | 14416 | 不是观察次数或GPU完成证明 |
| PROGRESS/PUBLISH调用 | BU 34/20 | 40266/20275 | 发布后继需要额外可信进度检查 |
| PREPARE累计操作时间 | BS18.713s | 16.874s | 两轮动态帧数/任务数不同，不能直接当每任务收益 |
| READY累计操作时间 | BS53.885s | 47.198s | 实际减少重复切片工作，但未转为总分收益 |
| COMPLETE累计操作时间 | BS122.617s | 118.238s | 含查询/RPC/结束处理，不是纯GPU时间 |
| COMPLETE累计间隔 | BS72.227s | 85.774s | 增加13.547s；不能仅凭汇总断言具体timer或调度根因 |
| 所列阶段操作与间隔合计 | BS267.999s | 269.891s | 排除分配和未选队列等待，不等于完整benchmark墙钟 |

总分相同掩盖了场景差异：desktop blur（`blur-radius=5:effect=blur:passes=1:separable=true:windows=4`）从117→38 FPS（−79/−67.52%），terrain从21→10 FPS（−11/−52.38%），shadow从457→503 FPS（+46/+10.07%）。完整33项对照保存在`private-chain-closure-scene-comparison.json`。这是单轮实测差异，CPU未锁恒频，不能断言稳定比例或唯一根因；同样不能把706→706解释成各场景性能不变。候选已撤回，不保留这些退化。

结论是**依赖识别已生效，收益却没有落到端到端性能**，不是“没有可合批任务”。上述统计来自各自文件生命周期，原生帧数随性能变化；下一步需要把阶段、场景、成员推进及等待预算对齐，区分新PROGRESS开销、后继发布延迟和整体fence延迟，不能直接扩大批次或提前发布CPU可见完成。尤其需要审视整个切片共享的短轮询预算是否过早耗尽；这只是代码路径假设，未做新实验。

验证与边界：

- 完整本地私有检查退出0，581条精确`=PASS`标记；提交模型166项，对BS101项新增65项（含BU已有33项与本轮整链32项）。覆盖隐藏旧前驱、末尾非chain、历史/当前/base错误、未知/嵌套对象、跨组、64节点边界和共享预算、RCU GC替换及引用平衡，以及跨独立IOCTL的1/2/6队列timeline序列。Host doubles不证明Linux真实RCU并发或GPU实体隔离。
- 9项错误变体均可编译且被模型拒绝：跳过旧前驱、忽略节点预算、逐依赖重置预算、泄漏阻塞引用、忽略pending chain错误、忽略组归属、提前后继、忽略进度完整性、提前外部fence。
- ARM64 Image、补丁清单均退出0，O2 Debug/断言、RMM预留、ABI2/RPC4与能力34359738363保持，完整执行位4仍清零。构建Image内置release为`6.12.0-g39d95dd028d4-dirty #79`。
- 硬件run-id `private-heap-720-20261031-bx`退出1，仅因完整720p低于1000；完整33场景、计算预热、validation26/1/6、VM0/0、两端日志与解绑、Host健康和资源恢复核验，11份日志SHA一致。本轮没有新VM_BIND错误；AE旧EBUSY仍未解决，可选eventfd仍FAIL；广泛API、多Client/实体攻击NOT_RUN。
- 恢复run-id `private-chain-closure-restore-20261031-bx`退出0：42项源码与BS相同，板端Client/Proxy/initrd/runner四项输入以及实际SD2固件字节SHA核验通过，未刷写/重启。恢复后提交模型101项退出0，没有新增GPU测量。增量开发Image仍为BX候选构建产物，不能用它替代冻结BS运行包。

命令（凭据仅在环境变量）：

```bash
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
  GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/chain-closure-unit \
  bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
  python3 scripts/check/check-gpu-private-submit.py
python3 build/rmm-client-bo-20261030/check-private-chain-closure-mutants.py
make -C Linux-Guest-GPU O=$PWD/build/rmm-client-bo-20261030/guest-client \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image
python3 opencca/scripts/setup/apply-local-patches.py --check
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bx -- \
  python3 build/rmm-client-bo-20261030/run-private-chain-closure-with-uart.py \
  --images build/rmm-client-bo-20261030/private-chain-closure-candidate \
  --private-gpu --workload glmark --performance --benchmark-only \
  --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-chain-closure-restore-20261031-bx -- \
  python3 build/rmm-client-bo-20261030/verify-or-restore-private-chain-closure-runtime.py
python3 scripts/check/check-gpu-private-submit.py
```

候选Client SHA `4a65033af26a2841ea6a0b30bd7c4b96e896d05e6293d6206aee5e5fb846d71d`；已恢复BS Client SHA `7389969e4a5751554d15c299d5a0f6a262118d4fa48a630a2745f78b6a8c2b29`，RMM保持`841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`。

证据根目录`build/rmm-client-bo-20261030/`：`private-chain-closure-{plan,design-review,candidate-validation,bx-hardware,phase-comparison,mutants,runtime-restored,checkpoint-record}.json`；`private-chain-closure-{unit,submit-final,hardware,analysis,restore,restored-submit}.log`，`client-private-chain-closure.log`。42项冻结源码与候选包分别为`private-chain-closure-source/`和`private-chain-closure-candidate/`；硬件及恢复证据见上述run-id对应的`build/lab-runs/`目录。

统一记录：有界整链检查扩展同组依赖合批｜BS706→BX706｜0/0%｜仅Client变化、CPU未锁恒频、无重启；阶段累计任务数不同，不作单项因果归因｜上述命令、run-id、退出码与日志｜未达714保留线，已撤回并恢复BS706；1000门槛FAIL，整体目标未完成。

## BY：按成功发布的后继补充有界短轮询，720p710，撤回恢复BS706（2026-10-31）

BX合批扩大但blur/terrain退化。代码检查发现`completion_polls`由整批共享，成功发布新的后继后不重置：前驱耗尽8次短等待后，后继可能直接使用普通延迟查询。本轮保留BX完整整链依赖检查，只在**新成员累计PUBLISH成功**后把计数归零，重复进度、未解锁新成员、失败和CPU-return续调用均不重置。不改RMM/Proxy/固件/ABI，不改真实完成或CPU归还/退休条件；对外fence仍等整批完整FINISH。

预算不会无限补充：一个冻结切片至多6个成员，新成员只会增加，初次发布后至多5次补充，每波最多8次请求50us短等待，总计最多48次/请求2.4ms。该上界不包括RMM调用、worker切换和Host剥夺CPU的时间；绝对超时不延长。单成员原有最多200us的首次预测等待保持，没有因新波次重复执行预测等待。超过每波预算后仍回到普通延迟查询，不因重复观察一直忙等。

**BS706→BY710，+4分/+0.57%，未达到预设714保留线，已撤回。** 场景保护预先要求desktop blur至少106FPS、terrain至少19FPS（相对BS117/21约10%退化边界）；实测165/30，检查通过。与BS比较同时加入BX整链合批和本轮预算重置，是组合效果；与BX比较是历史相邻单轮，不是同一时刻严格单变量实验。RMM/Proxy/Host/initrd/runner、池及GPU配置相同，无刷写/重启，CPU未锁恒频，不宣称稳定提升或唯一根因。恢复后未新测GPU，当前706引用原BS测量。

| 场景/计数 | BS | BX | BY | 说明 |
| --- | ---: | ---: | ---: | --- |
| 完整720p总分 | 706 | 706 | 710 | 相对BS+4/+0.57%；1000门槛FAIL |
| desktop blur FPS | 117 | 38 | 165 | 对BS+48/+41.03%，对BX+127/+334.21% |
| terrain FPS | 21 | 10 | 30 | 对BS+9/+42.86%，对BX+20/+200.00% |
| refract FPS | 42 | 41 | 50 | 对BS+8/+19.05%，对BX+9/+21.95% |
| shadow FPS | 457 | 503 | 497 | 对BS+40/+8.75%，对BX−6/−1.19%，保留全部33项差异 |
| 依赖切片/成员 | 无依赖合批 | 5847/20275 | 10103/43743 | 动态场景帧数和任务数不同，不能直接当固定工作量收益 |
| 经整链闭包纳入合批的任务 | 无 | 14416 | 33630 | 仍需所有未完成叶子匹配已选同组前驱 |
| PROGRESS/PUBLISH调用 | 无该路径 | 40266/20275 | 94567/43743 | 后继推进增加可信调用，需与重复READY节省综合衡量 |
| 成功后继发布后的预算重置 | 无 | 无 | 33640 | 恰为成员43743−切片10103，符合单调成员上界 |
| 重置前计数已达8次 | 未记录 | 未记录 | 340（1.01%） | 不等于发生慢定时器的次数，也不能逐次归因到某个场景 |
| READY累计操作时间 | 53.885s | 47.198s | 47.474s | 原始阶段累计，不是单位任务或纯缓存维护成本 |
| COMPLETE累计操作时间 | 122.617s | 118.238s | 124.404s | 含可信查询/RPC/结束处理，不是GPU执行时间 |
| COMPLETE累计间隔 | 72.227s | 85.774s | 75.166s | 比BX减少10.608s，但任务数不同，不能视为单项因果收益 |

结果支持继续研究按新发布任务补充观察预算，而不是把BX退化解释成依赖合批天然无效。同时，BY仍有237399个单成员切片，约占281142个执行成员的84.44%，新路径无法改善这一多数路径；本轮有限总分收益不足以满足保留线。下一步应分析单成员READY/FINISH的固定开销，不能仅扩大轮询预算或放松授权、实际PTE和真实停止/回收检查。模型与单轮性能证据均不替代多Client隔离验收。

验证与证据：

- 提交模型181项，比BX166项新增15项：1/2/6队列、旧预算0/7/8、每波连续pending与第9次延迟回退、新发布重置、最后一波仍有界、重复观察不补充、发布/进度失败、原始期限到达以及外部fence待完整FINISH。完整私有套件581条精确`=PASS`标记，除场景数外原标记一致；ASan/UBSan及O2 Debug检查退出0。Host doubles不证明Linux真实RCU并发、GPU恶意命令或实体隔离。
- 12个变体全部编译并被拒绝：原9项依赖/生命周期/进度/外部fence破坏，加上遗漏预算重置、无新进度也重置、移除每波上限。变体脚本首次误读不存在的`submit-final.log`，在编译前退出1；修正日志名后完整12项退出0，初始失败日志保留，不能当成功变体证据。
- ARM64 Image构建与9项补丁清单校验退出0；Image内置release `6.12.0-g39d95dd028d4-dirty #80`。RMM O2 Debug/断言、16384元数据/512物理维护预算、0x2800000预留、ABI2/RPC4、能力34359738363及完整执行位4清零保持。
- 硬件run-id `private-heap-720-20261031-by`退出1，严格错误仅为完整720p低于1000。完整33场景、计算预热、validation26/1/6、VM0/0、两端解绑/日志、Host健康与资源恢复核验；11份文件SHA与板端一致。无新VM_BIND错误；AE旧EBUSY仍未解决，可选eventfd仍FAIL，广泛API、多Client/实体攻击NOT_RUN。
- 恢复run-id `private-wave-poll-restore-20261031-by`退出0：42项源码与BS相同，板端Client/Proxy/initrd/runner四项输入及实际SD2固件字节SHA核验通过，无刷写/重启。恢复后提交模型101项退出0，无新GPU测量；开发增量Image保留为BY构建证据，不能代替冻结BS运行包。

执行命令（凭据仅在环境变量）：

```bash
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
  GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/wave-poll-unit \
  bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
  python3 scripts/check/check-gpu-private-submit.py
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
  python3 build/rmm-client-bo-20261030/check-private-wave-poll-mutants.py
make -C Linux-Guest-GPU O=$PWD/build/rmm-client-bo-20261030/guest-client \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image
python3 opencca/scripts/setup/apply-local-patches.py --check
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-by -- \
  python3 build/rmm-client-bo-20261030/run-private-wave-poll-with-uart.py \
  --images build/rmm-client-bo-20261030/private-wave-poll-candidate \
  --private-gpu --workload glmark --performance --benchmark-only \
  --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-wave-poll-restore-20261031-by -- \
  python3 build/rmm-client-bo-20261030/verify-or-restore-private-wave-poll-runtime.py
python3 scripts/check/check-gpu-private-submit.py
```

候选Client SHA `7c263a949469ea8b0e3adf4233c5476c13fb0ab2236aaeee82281511a835254a`；已恢复BS Client SHA `7389969e4a5751554d15c299d5a0f6a262118d4fa48a630a2745f78b6a8c2b29`，RMM SHA保持`841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`。

证据根目录`build/rmm-client-bo-20261030/`：`private-wave-poll-{plan,design-review,candidate-validation,by-hardware,scene-comparison,phase-comparison,mutants,runtime-restored,checkpoint-record}.json`；`private-wave-poll-{unit,submit,mutants,hardware,analysis,restore,restored-submit}.log`，初始脚本错误见`private-wave-poll-mutants-initial-missing-log.log`，构建见`client-private-wave-poll.log`。冻结42项源码/候选包分别为`private-wave-poll-source/`和`private-wave-poll-candidate/`；硬件与恢复证据位于上述run-id对应`build/lab-runs/`目录。

统一记录：对成功发布的后继补充有界查询预算｜BS706→BY710｜+4/+0.57%｜Client组合变化、CPU未锁恒频、无重启；BX历史对照706，不能作稳定单变量归因｜上述run-id/命令/退出码/日志｜场景保护通过，但低于预设714保留线，已撤回恢复BS706；1000门槛FAIL，整体目标未完成。


## BZ：省去完整完成观察后的重复堆事件查询（已撤回，恢复BS706）

目标：单成员切片仍占多数，FINISH 已检查GPU状态及OOM，Client随后的HEAP_EVENT又进行一次设备检查。本轮尝试只省去这次重复查询，不缓存“没有事件”的长期结论，不省略真实完成、停止或页面回收检查。

接口采用可选能力位35和追加的TASK_FINISH_HINT，ABI2/RPC4及原有操作编号不变。Client仅根据RMM VERSION启用；未支持则仍用旧FINISH。新接口只有在新鲜STATUS ACK、全部活跃队列的控制/序列检查、全stream START重验、实际root/配置及进度单调性检查通过后，才在GPU仍忙时返回INCOMPLETE kind2。它只允许省略紧随其后的一次HEAP_EVENT；下次FINISH仍重新观察。保留中的堆增长、OOM或先前STATUS ACK不确定仍返回kind0，未使用stream的OOM由既有START检查隔离；CPU归还继续为kind1，真正退休成功仍为[1,queue,0,0]。提示不释放任何引用，也不允许发布fence。

RMM的task_return/task_retire源码与BS逐字节相同。Guest类型桥拒绝旧FINISH的kind2、成功回复携带kind2、未知kind3、错误queue/页数及对托管token的原始ioctl绕过。关闭、错误、超时及下一次出现OOM的处理继续执行，绝对期限保持。

| 指标 | BS | BZ | 解释 |
| --- | ---: | ---: | --- |
| 完整720p | 706 | 713 | +7/+0.99%，低于预设714保留线；整体1000门槛FAIL |
| desktop blur | 117FPS | 119FPS | 通过106FPS场景保护线 |
| terrain | 21FPS | 18FPS | −3/−14.29%，低于19FPS场景保护线 |
| refract | 42FPS | 50FPS | +8/+19.05%，单场景观测 |
| 实际退休批次 | 269056 | 270738 | 任务数不同，累计时间不能直接作单项归因 |
| COMPLETE墙钟/批 | 0.455729ms | 0.439235ms | −3.62%，含RMM/设备观察和结束工作，不是纯CPU时间 |
| COMPLETE worker间隔/批 | 0.268448ms | 0.281209ms | +4.75%，抵消部分观察成本下降 |

候选记录429661次省略、1次实际堆查询，说明快速路径确实被使用；但总体收益小且terrain退化，不满足预设保留条件。Client与RMM同时变化，候选在刷固件重启后运行，CPU未锁恒频，不能证明稳定收益或唯一因果。结果不支持继续仅凭减少调用次数推断性能改善。

验证：完整私有套件581条精确PASS标记，Client实际提交worker114项（原101项加13项），类型桥164项，旧接口335阶段及新接口336阶段后端各80项FINISH检查，另有1项未使用stream新OOM隔离、21项活动堆事件必须服务检查。8个故意破坏条件的变体均编译成功后被断言拒绝。23份编译flags保持O2 Debug及断言，RMM预留末端0x2800000保持，FIT与ELF/BSS布局通过。模型不证明Linux真实并发或实体GPT保护。

首次测试错误地期待未使用stream的OOM返回pending，实际既有START策略将其隔离；最终增加独立阶段检查失败保留。首次flags比较因新目录包含旧目录前缀导致归一化错误，最终先替换长路径后23份一致；首次缺失提示变体因未使用参数未能编译，修正后8项均在运行断言中被拒绝。原始失败日志均保留。

硬件run-id `private-heap-720-20261031-bz`退出1，严格错误为完整720p低于1000。33场景、计算预热、VM0/0、两端解绑/日志、Host健康与资源恢复核验，11份证据SHA与板端一致；validation仍为26成功/1已知数值失败/6无判据，可选eventfd仍FAIL。无新增VM_BIND错误，AE历史EBUSY未解决；广泛API、多Client和实体攻击NOT_RUN。

源码42项已恢复BS。SD2固件恢复run-id `private-finish-heap-hint-firmware-restore-20261031-bz`和最终四项运行输入/实际SD2核验`private-finish-heap-hint-runtime-20261031-bz`均退出0；恢复后提交模型101项通过，无新GPU测量。当前仍引用BS原测706分，运行包`private-mapping-summary-candidate/`，固件`firmware-private-mapping-summary/`，能力34359738363，完整执行位4清零。候选能力68719476731与RMM/Client只保留为实验材料，开发增量Image仍是BZ，不能当作恢复后的运行输入。

执行命令（凭据仅通过环境变量）：

```bash
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
  GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/finish-heap-hint-unit \
  bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh
build/dma-guard-20261018/unit/opencca_gpu_backend GPU-SFTP/panthor_fw/mali_csffw.bin --finish-hint
python3 build/rmm-client-bo-20261030/check-private-finish-heap-hint-mutants-final.py
python3 scripts/maintenance/lab-run.py --run-id private-finish-heap-hint-deploy-20261031-bz --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-finish-heap-hint --run-id private-finish-heap-hint-deploy-20261031-bz
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-bz -- \
  python3 build/rmm-client-bo-20261030/run-private-finish-heap-hint-with-uart.py \
  --images build/rmm-client-bo-20261030/private-finish-heap-hint-candidate \
  --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-finish-heap-hint-firmware-restore-20261031-bz --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-mapping-summary --run-id private-finish-heap-hint-firmware-restore-20261031-bz
python3 scripts/maintenance/lab-run.py --run-id private-finish-heap-hint-runtime-20261031-bz -- \
  python3 build/rmm-client-bo-20261030/verify-private-finish-heap-hint-final-runtime.py
```

证据根目录`build/rmm-client-bo-20261030/`：`private-finish-heap-hint-{plan,design-review,candidate-validation,bz-hardware,scene-comparison,phase-comparison,mutants,source-restored,final-runtime,final-sd,checkpoint-record}.json`；日志按`private-finish-heap-hint-*`、`client-private-finish-heap-hint.log`保存。冻结源码/包/固件为`private-finish-heap-hint-source/`、`private-finish-heap-hint-candidate/`和`firmware-private-finish-heap-hint/`；设备运行和固件证据分别在上述run-id对应`build/lab-runs/`和`build/firmware-runs/`。原BS RMM SHA `841f06840edc5c2217e05e758fa04001e471e26c0c563053eb313936e3c587b2`；BZ RMM `51531498730f55dbe41ff8e388936552312755777a0c931d9993e80c1b0dcd92`，Client `d980793a49902fa8eb31a4da225d8aec8d029b2e4b156712bfc69bdff575bfa8`。

统一记录：减少完成观察后的重复堆事件查询｜BS706→BZ713｜+7/+0.99%｜RMM与Client组合变化、固件重启、CPU未锁恒频｜上述run-id/命令/退出码/日志｜低于714保留线且terrain场景保护FAIL，撤回恢复BS706；1000门槛FAIL，整体目标未完成。


## CA：恢复启动的接纳快速路径，完整720p718，保留CA718实验候选（2026-10-31）

此前启动每批任务时，既等待新START/RESUME与父子门铃ACK，又额外执行一次STATUS。随后COMPLETE/PROGRESS本身还会请求独立新鲜STATUS，之后才能检查实际队列进度、错误和完成条件。源码调查没有发现当前页表/句柄定位的大量hash瓶颈：相关定位已经为常数时间；历史短控制页缓存范围实验也没有整机提分，因此本轮改测固件握手，而非再次缩小读取范围。

本轮仅在Client复合READY_LAUNCH中启用内部`accept_resume`。必须是RMM先前通过真实完成、SUSPEND和退休保存的组，当前所有CS状态精确匹配，且本次RESUME、CSG和父子门铃ACK均匹配；所有流错误、真实固件/AS根和配置的前后检查保留。满足后只返回“启动已接纳”，省去启动阶段的额外STATUS；任何旧STOP快照继续完整握手。普通公开START的首次启动逻辑保留，调用者不能输入这个内部模式。未新增RSI、共享提示、完成权限或能力位，ABI2/RPC4、能力34359738363、完整执行位4清零。

这一变化不能当作完成证明。`task_observe`、`task_quiesce`、`task_return`及`task_retire`与BS逐字相同：首次及后续完成观察仍有自己的新鲜STATUS、全流/根重查、真实SUSPEND、FLUSH_MEM/AS禁用、最终序号复核、缓存归还和退休；失败或不确定时继续隔离并保留引用。没有采用“暂停就算完成”或仅信可写完成计数的方案。诊断fast/fallback只用于统计，不参与授权或成功判定。

新增16项实际后端场景：38轮恢复及ring回绕、旧STOP回退、公开START完整握手、完成忙态继续持有、STATUS超时、根/队列错误、未来/损坏/陈旧序号、SUSPEND超时、detach后根错误、错误Client、重复调用，以及未使用流的OOM/故障。首次启动即使输出恰好匹配也仍要求STATUS。6个故意删除流ACK、暂停来源、公开路径约束、忙态、未使用流OOM或新鲜STATUS的隔离变体均构建成功并被运行时断言拒绝。模型不证明实体GPT或恶意Proxy隔离。

统一记录：减少恢复启动上的重复固件STATUS｜BS706→CA718｜+12/+1.70%｜仅RMM运行代码变化、原Client/Proxy/Host/initrd/runner不变；固件重启后测试，GPU实际594MHz、CPU未锁恒频，单轮不证明稳定提分或唯一因果｜下列run-id、命令、退出码与日志｜保留CA718实验候选；1000门槛FAIL，整体目标未完成。

| 指标 | BS | CA |
| --- | ---: | ---: |
| 完整720p分数 | 706 | 718 |
| 已退休批次 | 269056 | 274218 |
| READY墙钟ms/批 | 0.200275 | 0.117757 |
| COMPLETE墙钟ms/批 | 0.455729 | 0.475269 |
| COMPLETE worker间隔ms/批 | 0.268448 | 0.311003 |
| desktop blur FPS | 117 | 118 |
| terrain FPS | 21 | 21 |

统计：fast=274481、fallback=0。其覆盖范围为`AGGREGATE_COUNTERS_ONLY_NOT_PER_SCENE_OR_CYCLE_TIMING`，不是逐场景收益或周期级计时；RMM计数覆盖服务全程含预热/其他DRM文件，末次worker统计为单文件，274481次快速接纳与274218个退休批次不是同一总体。worker数据包含RMM/设备等待及调度影响，任务数也不同，不能把墙钟变化解释为纯CPU收益；全部33场景差异保留在`private-resume-accept-scene-comparison.json`。

- 本地私有路径：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/resume-accept-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，日志`private-resume-accept-unit.log`，581条精确标记。相同HOST_CC运行`bash scripts/check/check-dma-guard.sh`退出0，日志`private-resume-accept-dma-initial.log`，351阶段含16项新场景；`check-private-resume-accept-mutants.py`退出0，6项编译变体拒绝见`private-resume-accept-mutants.json`。固定补丁清单校验退出0。
- 构建及封存：`build-private-resume-accept.py`、`build-private-resume-accept-firmware.py`、`freeze-private-resume-accept.py`均退出0，23份编译参数与保留O2 Debug一致，全部断言保留，FIT/含BSS布局PASS。候选`private-resume-accept-candidate/`、固件`firmware-private-resume-accept/`及42份源码快照`private-resume-accept-source/`；只有固件核心和后端测试两份源码变化。
- SD2部署：`python3 scripts/maintenance/lab-run.py --run-id private-resume-accept-deploy-20261031-ca --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-resume-accept --run-id private-resume-accept-deploy-20261031-ca`退出0。Host/Realm能力1及CPU0–1恢复，随后测试独占入口执行`verify-private-resume-accept-sd.py`，实际SD两段字节与候选SHA一致。4项运行输入uploaded均false。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ca -- python3 build/rmm-client-bo-20261030/run-private-resume-accept-with-uart.py --images build/rmm-client-bo-20261030/private-resume-accept-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，严格1000门槛FAIL。计算检查通过、完整33场景，validation仍26/1/6，既有数值失败和可选eventfd失败继续保留；VM0/0、两端kernel-log/pool-unbind、Host健康、资源恢复和11份SHA核验通过。证据`build/lab-runs/private-heap-720-20261031-ca/`、日志`private-resume-accept-hardware.log`及分析`private-resume-accept-ca-hardware.json`。
- 最终读回：独占入口`private-resume-accept-runtime-20261031-ca`执行`verify-private-resume-accept-final-runtime.py`退出0；42项当前源码、板端四项输入及实际SD2与当前保留包一致，见`private-resume-accept-final-runtime.json`和`private-resume-accept-final-sd.json`。

AE VM_BIND EBUSY未定位；本轮没有对应错误不等于问题关闭。更广泛API、ML、多Client、真实并发销毁与实体CPU/DMA攻击仍NOT_RUN；硬件GPT/GPC模拟边界保持。

证据回收更正：初次分析在独立回收日志前执行，因本地summary缺失而失败；traceback保留于`private-resume-accept-analysis-initial-missing-transfer.log`。随后通过独占入口`private-resume-accept-evidence-20261031-ca`回收11份固定普通文件并逐项校验SHA，退出0，独立重跑分析退出0；没有重跑GPU或改变评分门槛。详见`private-resume-accept-analysis-correction.json`。

后续定位：READY每批墙钟0.200275→0.117757ms，但COMPLETE查询/退休批次2.496911→2.898697、COMPLETE墙钟0.455729→0.475269ms、worker间隔0.268448→0.311003ms，启动节省被后续观察与调度部分抵消。下一步可针对更早的启动接纳时点重新评估初次等待和有界重试；只是待验证假设，不能据此删除任何完成/堆事件/停止/回收检查，或扩展原绝对期限。详见`private-resume-accept-followup-assessment.json`。


## CB：首次等待与后续重试共用预算，完整720p702，已撤回并恢复CA718（2026-10-31）

CA省去恢复启动的一次STATUS后，完成查询/退休批次从BS2.50升至CA2.90；CA首次等待墙钟约186µs，接近200µs上限。本轮只改Client：首次预测上限提高到400µs，同时为每个运行切片累计请求主动等待量；后续最多八次50µs短等消耗剩余预算，不足50µs时截断，600µs耗尽后使用普通延迟tick。原路径最多200+8×50=600µs，新路径没有提高总请求上限；只是改变等待分配。该上限不含可信调用、worker排队与Guest/Host抢占，不保证墙钟时间。

预算在锁内扣除、锁外等待，CPU-return续传不补充预算；预测只在精确成功退休后训练。没有改变真实FINISH、heap服务、页归属/真实映射、完成/停止/AS禁用/缓存归还/退休、错误保留与原始deadline。RMM、Proxy、Host、initrd、runner及SD2均保持CA；没有刷写或重启。新增模型涵盖六种初始提示、耗尽/超额/不足50µs、CPU归还、超时及关闭。113项实际Client提交模型比CA新增12项，完整私有套件581条精确PASS；8个故意扩大预算、遗漏扣除/截断、补充预算、错误训练或跳过真实FINISH的变体全部编译并被断言拒绝。模型不证明Linux真实并发或实体GPT/GPC。

统一记录：重新分配有限完成等待预算｜CA718→CB702｜-16/-2.23%｜仅Client变化、无重启、GPU实际594MHz、CPU未锁恒频，单轮不证明稳定收益或唯一因果｜下列命令/run-id/退出码/日志｜已撤回并恢复CA718；整体目标未完成。

| 指标 | CA | CB |
| --- | ---: | ---: |
| 完整720p分数 | 718 | 702 |
| 退休批次 | 274218 | 268569 |
| FINISH查询/退休批次 | 2.898697 | 2.141450 |
| READY墙钟ms/批 | 0.117757 | 0.117065 |
| COMPLETE墙钟ms/批 | 0.475269 | 0.438835 |
| COMPLETE worker间隔ms/批 | 0.311003 | 0.368621 |
| 首次等待墙钟ms/批 | 0.186287 | 0.253074 |
| desktop blur FPS | 118 | 118 |
| terrain FPS | 21 | 22 |

实验保留条件在测量前固定为726分、blur≥107FPS、terrain≥19FPS，结果总分条件未通过、场景保护通过；全部33场景变化保留于`private-wait-budget-scene-comparison.json`。阶段统计为每文件累计墙钟，包含可信调用/设备响应/CPU归还与调度；任务数与场景帧数不同，不能把累计减少或查询减少直接当稳定端到端提分。

命令与证据（根目录`build/rmm-client-bo-20261030/`）：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/wait-budget-unit bash scripts/check/check-rmm-gpu-private.sh`退出0：`private-wait-budget-unit.log`，581条标记/113项提交；`python3 build/rmm-client-bo-20261030/check-private-wait-budget-mutants.py`退出0：8个错误变体退出−6，`private-wait-budget-mutants.json`。
- `make -C Linux-Guest-GPU O=$PWD/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image`退出0：`client-private-wait-budget.log`。固定上游补丁清单检查退出0，`private-wait-budget-patches.log`；RMM O2 Debug/断言、ABI2/RPC4、能力34359738363及完整执行位清零保持。
- `python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cb -- python3 build/rmm-client-bo-20261030/run-private-wait-budget-with-uart.py --images build/rmm-client-bo-20261030/private-wait-budget-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，1000门槛FAIL；`private-wait-budget-hardware.log`和`build/lab-runs/private-heap-720-20261031-cb/`。完整33场景/计算预热、VM0/0、两端日志/解绑、Host健康与资源恢复核验；validation仍26/1/6，已知数值失败、可选eventfd失败和AE旧EBUSY保留，广泛API/ML、多Client及实体攻击NOT_RUN。
- 独占回收`private-wait-budget-evidence-20261031-cb`退出0：11份固定普通文件逐项SHA一致，`private-wait-budget-evidence.log`；独立分析退出0，`private-wait-budget-analysis.log`。最终读回/按决策恢复`private-wait-budget-runtime-20261031-cb`退出0：42项源码、四项板端输入和实际SD2与当前冻结包一致，`private-wait-budget-runtime.log`、`private-wait-budget-final-runtime.json`。恢复后无新GPU测量，当前分数引用原CA718。

候选冻结包`private-wait-budget-candidate/`、42份源码`private-wait-budget-source/`和`before-private-wait-budget/`保留，候选Client SHA `afefe12ae1f3f11e40fae9974d05af72c298ea66da596e90d1c695666bc59a22`；当前包`build/rmm-client-bo-20261030/private-resume-accept-candidate`，固件`firmware-private-resume-accept/`。生产源码与CA的42项全部恢复一致，未保留新预算字段或兼容分支；增量构建Image仍为CB，只作为构建证据，不能替代CA冻结运行输入。

CB补充结论：FINISH查询/批2.898697→2.141450（−26.12%），但COMPLETE操作+间隔0.786272→0.807457ms（+2.69%），不构成完成端到端加速。5×5 effect2d从620→126FPS（−79.68%）的明显退化保留；单轮不能确定根因。源码显示400µs首次等待后仅余四次50µs短等，随后更早回到普通延迟tick；同时减少可信调用也缩短了快速窗口覆盖的实际时间。后续可评估将有限查询次数与CPU等待预算分离：等待预算耗尽后，在原最多八次查询额度内使用零延迟work排队而不增加主动等待。此项尚未实现，需重新模型和实体测量；不能删除heap/错误处理、真实FINISH或延长期限。见`private-wait-budget-followup-assessment.json`。

## CC：修正私有Client的eventfd测试预期，真实通知通过（2026-10-31）

此前反复出现的`SYNCOBJ_EVENTFD_UNSUPPORTED ... errno=2`来自测试预期过时：私有Client的syncobj保存在本地DRM表，EVENTFD已经交给标准DRM核心；旧测试使用handle=0并期待“不支持”，实际得到合法的ENOENT。此次没有放宽该错误的接受范围，而是创建真实syncobj和eventfd，检查binary/timeline通知、较早点不提前通知、一次性触发、非法handle/fd/flags和销毁待通知对象。旧共享路径继续要求拒绝EVENTFD。

init将冻结initrd中的探针绑定到只读工作负载根，避免继续运行rootfs中的旧副本。只更新initrd；Client/Proxy Image、RMM、Host、runner及GPU授权/完成/缓存归还路径与CA相同。真实探针的通知由CPU SIGNAL触发，**不能当作GPU任务完成eventfd或可信GPU完成的证明**。

统一记录：修正私有DRM通知接口测试｜CA718→CC717｜-1/-0.14%｜仅测试initrd变化、无刷写/重启、GPU实际594MHz、CPU未锁恒频；单轮不宣称性能收益｜下列命令、退出码和日志｜保留测试修正；整体目标未完成。

- 本地：`python3 scripts/check/check-panthor-eventfd-smoke.py`退出0，25项测试使用真实Linux eventfd和DRM替身；ASan/UBSan覆盖正确路径及错误通知/错误返回值变体。首次直接包含未导出UAPI导致编译失败，日志`build/rmm-client-bo-20261030/private-eventfd-probe-model.log`保留；改用目标Guest的`headers_install`后通过，见`private-eventfd-probe-model-retry.log`。init和探针ARM64静态编译退出0，见`private-eventfd-probe-build.log`。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cc -- python3 build/rmm-client-bo-20261030/run-private-eventfd-probe-with-uart.py --images build/rmm-client-bo-20261030/private-eventfd-probe-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，明确错误为`private full-720p score below 1000`。真实Client输出`PANTHOR_SYNCOBJ_EVENTFD_SMOKE=PASS`、`PANTHOR_BASIC_SMOKE=PASS`及`PANTHOR_IOCTL_SMOKE=BASIC_PASS`，计算预热通过；33场景完成，validation仍26成功/1已知数值失败/6无判据，VM退出码0/0。日志`private-eventfd-probe-hardware.log`及`build/lab-runs/private-heap-720-20261031-cc/`。
- 独占回收/读回：run-id `private-eventfd-probe-evidence-20261031-cc`执行`pull-private-eventfd-probe-evidence.py`及`verify-private-eventfd-probe-runtime.py`，退出0；11份固定证据SHA、四项板端输入、46项相关源码与实际SD2固件核验通过，Host内核健康、pmthor/CPU0–1、无遗留VM/loop和资源恢复检查通过。证据见`realm-evidence/`、`evidence-transfer.json`、`private-eventfd-probe-final-runtime.json`及`private-eventfd-probe-sd-readback.json`。
- 独立分析：`python3 build/rmm-client-bo-20261030/analyze-private-eventfd-probe.py`退出0，见`private-eventfd-probe-analysis.log`和`private-eventfd-probe-hardware.json`。保留包`private-eventfd-probe-candidate/`只有initrd不同于CA；本轮未改生产GPU源码、未消除AE历史EBUSY，广泛API/ML、多Client和实体隔离攻击NOT_RUN，物理GPT/GPC隔离未因此得到验证。

## CD：取消后续50µs主动等待，完整720p710，已撤回恢复CC717（2026-10-31）

CC每文件累计主动等待约77秒，立即重排worker累计不足1秒。本轮检验真实FINISH/heap查询本身是否已经提供足够查询间隔：保留首次自适应等待≤200µs，后续最多8次立即重排，不再逐次空转50µs，超过额度仍回普通延迟tick。RMM、Proxy、Host、initrd、runner、真实完成/停止/AS禁用/缓存归还/退休和绝对超时均不变；只改变Client查询节奏。

统一记录：取消后续主动等待｜CC717→CD710｜-7/-0.98%｜仅Client变化，无刷写/重启，GPU实际594MHz、CPU未锁恒频，单轮不证明稳定比例或唯一因果｜下列命令、退出码及日志｜未达预设725分，且场景保护失败，已撤回恢复CC717；整体目标未完成。

| 指标 | CC | CD |
| --- | ---: | ---: |
| 退休批次 | 273822 | 269047 |
| FINISH查询/退休批次 | 2.898777 | 3.603188 |
| 主动等待墙钟ms/批 | 0.282185 | 0.191117 |
| COMPLETE操作墙钟ms/批 | 0.476744 | 0.532271 |
| COMPLETE worker间隔ms/批 | 0.310026 | 0.274490 |
| COMPLETE操作+间隔ms/批 | 0.786770 | 0.806761 |
| desktop blur FPS | 117 | 121 |
| terrain FPS | 21 | 16 |
| 5×5 effect2d FPS | 622 | 125 |

主动等待减少约0.091ms/批，但查询增加，COMPLETE操作+间隔增加2.54%；不能把省下的空转直接当作端到端加速。预设blur≥107、terrain≥19及5×5 effect2d≥550FPS，仅blur通过。所有33场景差异见`private-no-spin-scene-comparison.json`，阶段墙钟见`private-no-spin-phase-comparison.json`。阶段计时包含可信调用、设备响应和调度，任务数不同，不是纯CPU周期或GPU执行时间。

命令及证据均在`build/rmm-client-bo-20261030/`，除显式日志目录外：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/no-spin-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-no-spin-unit.log`含582条PASS标记；实际Client提交模型112项，比CC新增11项，覆盖初次提示边界、8次额度、CPU归还不补充额度、超时/关闭和错误。定时GPU替身独立推进模拟设备时间，不把CPU空转当作设备进展；不能替代实体并发或设备证明。
- `python3 build/rmm-client-bo-20261030/check-private-no-spin-mutants.py`退出0，7个错误变体均编译成功后被断言拒绝，见`private-no-spin-mutants.log/json`。Client构建`make -C Linux-Guest-GPU O=$PWD/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image`退出0，见`client-private-no-spin.log`。固定上游补丁清单校验退出0，见`private-no-spin-patches.log`。
- 完整720p命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cd -- python3 build/rmm-client-bo-20261030/run-private-no-spin-with-uart.py --images build/rmm-client-bo-20261030/private-no-spin-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，错误为`private full-720p score below 1000`；完整33场景、计算预热、eventfd/basic、VM0/0、Host健康和资源恢复检查通过。validation仍26成功/1已知数值失败/6无判据，不能称完整数值正确性通过。日志`private-no-spin-hardware.log`和`build/lab-runs/private-heap-720-20261031-cd/`。
- 独占回收`private-no-spin-evidence-20261031-cd`执行`pull-private-no-spin-evidence.py`退出0，11份固定文件SHA与板端一致；`python3 build/rmm-client-bo-20261030/analyze-private-no-spin-hardware.py`退出0，见`private-no-spin-analysis.log`和`private-no-spin-hardware.json`。
- 独占恢复`private-no-spin-runtime-20261031-cd`执行`verify-or-restore-private-no-spin-runtime.py`退出0：46项源码、四项运行输入及实际SD2核验，恢复CC的Client Image及两项改动源码，无固件写入或重启，见`private-no-spin-final-runtime.json`。恢复后提交模型101项再次通过，见`private-no-spin-restored-submit.log`；未重测GPU，当前717引用原CC。失败候选、源码快照和变更前备份分别保留于`private-no-spin-candidate/`、`private-no-spin-source/`和`before-private-no-spin/`。

本轮形成的后续假设：固定“8次”不能保证快速观察窗口覆盖相同的实际时间；取消空转也让它更早进入普通延迟tick，可能放大特定场景尾延迟。下一步如继续优化，应验证同时限制查询次数和实际观察窗口的策略，而不是单纯删除等待或只统计调用减少。此假设未实现，不能据此增加无界轮询、延长绝对超时或删除任何可信检查。AE历史EBUSY、广泛API/ML、多Client和实体攻击仍NOT_RUN；物理GPT/GPC隔离未因此验证。


## CE：快速重查同时受次数与观察窗口约束，完整720p718，已撤回恢复CC717（2026-10-31）

CD取消50µs等待后，固定8次快速重查更早耗尽，特定场景显著退化。本轮保留首次自适应等待≤200µs、前8次50µs短等待，允许在启动后2ms内最多再立即重排8次真实FINISH/heap查询；快速重排同时受16次总额度和2ms观察窗口约束。CPU归还续传不补充额度，超过窗口回普通延迟tick。2ms约束的是决定是否快速重排的时间，不能保证含Host抢占、RMM调用和已请求等待在内的墙钟执行时间≤2ms。

仅Client变化，RMM、Proxy、Host、initrd和runner不变；没有增加主动等待量、延长任务绝对超时或改变可信完成、停止/AS禁用、缓存归还和退休条件。新增一次性汇总计数记录“额外重排决定”；8454不等于独立任务数，也不证明每次重排后来都执行了查询。

统一记录：完成观察次数与时间联合约束｜CC717→CE718｜+1/+0.14%｜仅Client变化、无刷写/重启、GPU实际594MHz、CPU未锁恒频，单轮不证明稳定收益或唯一因果｜下列命令、run-id和退出码/日志｜未达预设725保留线，已撤回恢复CC717；整体目标未完成。

| 指标 | CC | CE |
| --- | ---: | ---: |
| 退休批次 | 273822 | 277631 |
| FINISH查询/退休批次 | 2.898777 | 2.917221 |
| READY墙钟ms/批 | 0.118435 | 0.117778 |
| COMPLETE操作墙钟ms/批 | 0.476744 | 0.478899 |
| COMPLETE worker间隔ms/批 | 0.310026 | 0.294591 |
| 主动等待墙钟ms/批 | 0.282185 | 0.282277 |
| desktop blur FPS | 117 | 117 |
| terrain FPS | 21 | 21 |
| 5×5 effect2d FPS | 622 | 621 |

预设blur≥107、terrain≥19及5×5 effect2d≥550FPS均通过；全部33场景差异与阶段墙钟分别保留于`private-fast-window-scene-comparison.json`及`private-fast-window-phase-comparison.json`。统计包含可信调用、设备响应和Guest/Host调度，任务数不同，不是纯CPU周期、GPU时间或稳定因果证据。

命令和证据（默认位于`build/rmm-client-bo-20261030/`）：

- 本地完整检查：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/fast-window-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，最终日志`private-fast-window-unit-final.log`含582条PASS标记；实际Client提交模型129项，比CC新增28项，覆盖次数与时间边界、CPU归还不补充额度、关闭/超时/错误及不提前完成。模型不证明Linux并发、真实调度时延或硬件隔离。
- 错误变体：`python3 build/rmm-client-bo-20261030/check-private-fast-window-mutants.py`最终退出0，9个错误变体均编译成功后由断言拒绝，见`private-fast-window-mutants-retry.log`和`private-fast-window-mutants.json`。首次跳过真实FINISH的变体导致测试空指针退出，未计为有效断言拒绝，失败日志`private-fast-window-mutants.log`保留；补上提前完成断言后重新验证全部变体。复用报告模板的新增场景/变体数量标签在部署前更正为28/9，原输出和更正均保留。
- Client构建：`make -C Linux-Guest-GPU O=$PWD/build/rmm-client-bo-20261030/guest-client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image`退出0，`client-private-fast-window.log`；固定上游补丁校验退出0，`private-fast-window-patches.log`。
- 完整720p：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ce -- python3 build/rmm-client-bo-20261030/run-private-fast-window-with-uart.py --images build/rmm-client-bo-20261030/private-fast-window-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`退出1，错误为`private full-720p score below 1000`。完整33场景、计算预热、eventfd/basic、VM0/0、Host健康及资源恢复核验；validation仍26成功/1已知数值失败/6无判据。日志`private-fast-window-hardware.log`和`build/lab-runs/private-heap-720-20261031-ce/`。
- 独占回收`private-fast-window-evidence-20261031-ce`执行`pull-private-fast-window-evidence.py`退出0，11份固定文件SHA与板端一致；独立`python3 build/rmm-client-bo-20261030/analyze-private-fast-window-hardware.py`退出0，见`private-fast-window-analysis.log`和`private-fast-window-hardware.json`。
- 独占恢复`private-fast-window-runtime-20261031-ce`执行`verify-or-restore-private-fast-window-runtime.py`退出0，46项源码、四项运行输入与实际SD2核验，恢复CC Client及两项修改源码，无刷写/重启，见`private-fast-window-final-runtime.json`。恢复后101项提交模型通过，`private-fast-window-restored-submit.log`；未新增GPU测量，当前717引用原CC。候选、源码快照和变更前备份保留于`private-fast-window-candidate/`、`private-fast-window-source/`、`before-private-fast-window/`。

本轮只能证明新调度分支被触发，未证明足够的整体加速。后续可评估首次等待预算与有限快速观察窗口联合调整，避免CB中等待预算耗尽后过早进入普通tick；必须重新验证有限查询、主动等待总量、原始超时和全部可信检查。此组合尚未实现。AE历史EBUSY、广泛API/ML、多Client、恶意Proxy/Client和实体攻击仍未验收；不能将本轮eventfd CPU SIGNAL测试当作GPU完成通知或GPT/GPC保护证明。


## CF：联合等待预算与快速观察窗口，完整720p716（2026-10-31）

统一记录：减少过早完成查询且避免预算耗尽后过早退回定时tick｜CC717→CF716｜-1分/-0.14%｜仅Client worker变化，Proxy/RMM/Host/initrd/runner与CC相同，GPU请求600/实际594MHz，CPU未锁恒频，无刷写或重启｜`private-heap-720-20261031-cf`退出1，命令及日志如下｜未通过预设保留条件，已撤回恢复CC717；1000门槛FAIL，整体目标未完成。

本轮组合验证CB和CE未覆盖的情况：首次预测等待上限由200增至400µs；首次与后续等待共用600µs的**请求主动等待预算**，在锁内扣账后解锁等待，最后一次允许小于50µs。最多前8次重查可以主动等待；预算耗尽继续使用剩余的无空转快速重排，总次数≤16且决定重排时距离可信READY成功不足2ms。CPU缓存归还游标始终立即推进，但不重置时间、次数或主动预算。Host抢占可能使实际墙钟等待超过请求预算，已排入的work也可能在2ms以后执行；这些限制只控制调度，不是实时性承诺或完成凭据。

每次完成查询仍调用真实FINISH，pending继续处理heap事件；只有完整停止/AS禁用/缓存归还/退休成功才发布本地fence。绝对任务期限、错误/关闭处理及启动不重放保持。冻结检查确认run_finish、task_rpc、job_ready和mapping_lock四个函数逐字未变，46份跟踪源码中仅Client worker文件与实际源码提交测试变化。

| 指标 | CC | CF |
| --- | ---: | ---: |
| 完整720p分数 | 717 | 716 |
| desktop blur FPS | 117 | 118 |
| terrain FPS | 21 | 22 |
| 5×5 effect2d FPS | 622 | 630 |
| 完成查询/退休批次 | 2.898777 | 2.280140 |
| READY墙钟ms/批 | 0.118435 | 0.117623 |
| COMPLETE操作墙钟ms/批 | 0.476744 | 0.444768 |
| COMPLETE worker间隔ms/批 | 0.310026 | 0.327484 |
| 实际主动等待墙钟ms/批 | 0.282185 | 0.318095 |

预先声明保留线725、blur≥107FPS、terrain≥19FPS、5×5 effect2d≥550FPS；场景保护通过。本轮单个DRM文件记录18222次无空转快速重排决定，包含预算耗尽或原8次以后的决定；这不是独立任务数，也不证明排入的查询全部执行。退休批次数273822→277222不同，累计墙钟含预热/validation等；单轮、CPU未恒频，不据此宣称稳定收益、纯CPU节约或唯一因果。

验证与证据均位于`build/rmm-client-bo-20261030/`及`build/lab-runs/<run-id>/`：

- 本地完整私有套件退出0、582条PASS标记，实际Client提交测试141场景（对CC新增40），ASan/UBSan；覆盖独立时间/次数限制、主动预算耗尽后继续快速查询、最后部分预算、CPU归还不补预算、超时、关闭、heap和真实退休。12个故意破坏预算/时间/次数/期限/真实FINISH等条件的变体均编译成功后断言退出−6；候选退出0。模型不证明Linux真实并发或实体隔离。日志`private-joint-poll-unit-final.log`、`private-joint-poll-mutants-final.log`及JSON。最初生成辅助脚本时元数据替换顺序检查提前退出1，未生成或执行变体；修正为明确字段后最终12项运行拒绝，不将生成失败计作拒绝。
- Client ARM64构建退出0，`client-private-joint-poll.log`。上游9项补丁均APPLIED、资源预检无issues；候选冻结`private-joint-poll-candidate/`及46份源码`private-joint-poll-source/`。仅Client Image变化，保留包四项SHA与真实SD2固件字节读回通过。
- 硬件完整33场景、计算预热、CPU SIGNAL/eventfd及basic冒烟、VM退出[0,0]、两端解绑/日志、Host内核健康/CPU0–1/pmthor/loop及进程恢复和11份采集SHA通过。validation仍26成功/1既有数值失败/6无判据，整体退出1由1000门槛触发。CPU SIGNAL/eventfd不等于GPU完成eventfd；AE历史EBUSY未解决，未扩展广泛API、多Client和实体恶意Proxy/Client、并发销毁等硬件矩阵。
- 最终处理`private-joint-poll-runtime-20261031-cf`退出0，按测量决定只恢复本轮改动的两份源码与Client Image；46项源码、四项运行输入与实际SD2均核验。最终提交模型101项退出0，日志`private-joint-poll-final-submit.log`。最终核验后无新GPU测量，当前717引用原CC测量，增量构建Image仍是已撤回CF，后续运行须使用冻结CC包。

执行命令（凭据仅经交互读取并传入环境）：

```bash
HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/private-joint-poll-unit \
 bash scripts/check/check-rmm-gpu-private.sh
python3 build/rmm-client-bo-20261030/check-private-joint-poll-mutants.py
make -C Linux-Guest-GPU O=$PWD/build/rmm-client-bo-20261030/guest-client \
 ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
 CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cf -- \
 python3 build/rmm-client-bo-20261030/run-private-joint-poll-with-uart.py \
 --images build/rmm-client-bo-20261030/private-joint-poll-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-joint-poll-evidence-20261031-cf -- \
 python3 build/rmm-client-bo-20261030/pull-private-joint-poll-evidence.py
python3 build/rmm-client-bo-20261030/analyze-private-joint-poll-hardware.py
python3 scripts/maintenance/lab-run.py --run-id private-joint-poll-runtime-20261031-cf -- \
 python3 build/rmm-client-bo-20261030/verify-or-restore-private-joint-poll-runtime.py
```

记录：`private-joint-poll-{plan,candidate-validation,mutants,hardware,phase-comparison,scene-comparison,final-runtime,sd-readback,followup-assessment,checkpoint-record}.json`；完整命令/退出码/前后资源与原始日志见三个上述run-id。物理GPT/GPC不由本轮证明，整体目标继续保持未完成。


## CG：SUSPEND兼作完成观察，完整720p728（2026-10-31）

统一记录：减少完成路径中的重复固件快照握手｜CC717→CG728｜+11分/+1.53%｜只改RMM实现，Client/Proxy/Host/initrd/runner同CC，GPU请求600/实际594MHz，CPU未锁恒频；固件更新需Host重启，单轮不证明稳定收益｜`private-heap-720-20261031-cg`退出1，原因仍为1000门槛｜通过预设725保留线与场景保护，保留实验候选；整体目标未完成。

候选仅调整RMM内部FINISH。原生Panthor说明队列快照在STATUS_UPDATE或组SUSPEND时刷新；此前完成路径分别请求STATUS与SUSPEND。本轮先读取受保护input/extract/terminal sequence，所有活跃队列精确匹配才尝试用真实SUSPEND同时获取新快照及停止凭据；提示不满足则回退原COMPLETE。停止后核验完整队列值、scoreboard/blocked、全部stream的OOM ACK边沿，再完整重查停止/根/配置/AS，之后沿用原CPU归还与退休。尝试停止后失败隔离并保留引用，不回退、不制造完成。

原COMPLETE、PROGRESS、task_quiesce、公开quiesce、task_return及task_retire逐字与CC相同；Guest/Host/ABI不变。源码清单仅固件实现和后端测试两项变化。模型覆盖真实SUSPEND、AS禁用、计数回退、过期/超前序号、scoreboard/blocked、根和inactive流异常、缺失ACK、页读回调后配置变化及不提前归还；24项新增、375后端阶段、80项既有FINISH场景及582条私有PASS标记。8种故意移除守卫的变体均成功编译后断言退出-6。模型不证明Linux并发、真实设备时序或实体GPT/GPC隔离。

失败证据全部保留：初期模型缺少原生SUSPEND快照刷新/fixture复位和注入作用域，修正后重验；case21发现inactive流OOM检查缺失，补入生产代码并重建；case23原先反复翻转ACK抵消了注入，改为确定性不匹配。首次错误变体运行遇case23失败、第二次遇删条件后的unused变量编译错误，均不算变体拒绝。最终编译成功并运行拒绝的8项单独记录于mutants JSON与compiled日志。早期固件包含修正前RMM，未部署；最终重新从固定归档独立构建final目录，FIT实际嵌入最终8264fc149f118307c6d931a337bd25a8bf43e82ec7f0ba91bd02d63bf3373f05。

最终RMM保留O2 Debug及断言，23项编译flags与保留构建一致，0x2800000预留和ELF/BSS布局校验通过。上游9项补丁APPLIED。独占部署只刷SD2固件，保存实际启动区备份；Host重启后Realm capability=1、CPU0-1、pmthor恢复。四项Guest运行载荷不变且无需上传。

| 指标 | CC | CG |
| --- | ---: | ---: |
| 完整720p分数 | 717 | 728 |
| desktop blur FPS | 117 | 120 |
| terrain FPS | 21 | 22 |
| 5×5 effect2d FPS | 622 | 633 |
| 完成查询/退休批次 | 2.898777 | 2.841385 |
| READY墙钟ms/批 | 0.118435 | 0.117652 |
| COMPLETE操作墙钟ms/批 | 0.476744 | 0.463495 |
| COMPLETE worker间隔ms/批 | 0.310026 | 0.305628 |
| 主动等待墙钟ms/批 | 0.282185 | 0.278046 |

33个场景、计算预热、CPU SIGNAL/eventfd和basic、两端解绑/日志、VM退出[0,0]、Host健康与CPU0–1/pmthor/进程/loop恢复核验通过。validation仍26成功/1既有数值失败/6无判据，完整基准无意外BO/VM_BIND/提交错误。退休批次数273822→278423不同；累计阶段墙钟包含可信调用、设备响应、调度和预热/validation，不当作纯CPU周期或稳定因果证据。

**快速路径硬件命中次数未得到可靠记录。** UART中的`GPU_SUSPEND_OBSERVE fa...`被Host teardown输出交错覆盖，fast/fallback数值不可恢复；不拼接或推算。正常测试和计时统计可用，不因此宣称该分支确已命中或达到某个命中率。分析器明确标记`UNAVAILABLE_UART_LINE_INTERLEAVED`及`fast_path_hit_proven=false`；候选仅按预先声明的总分/场景规则保留。后续先改进低开销可信诊断，确认旧extract快照导致的回退比例，再决定是否值得继续此方向。此诊断改进尚未实现。

证据默认位于`build/rmm-client-bo-20261030/`，硬件包装记录位于`build/lab-runs/<run-id>/`：

- 本地：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-suspend-observe-backend-accepted.log`；完整私有检查加`GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/suspend-observe-unit-final`执行`bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-suspend-observe-unit-final.log`。成功编译后运行错误变体：`python3 build/rmm-client-bo-20261030/check-private-suspend-observe-mutants-compiled.py`退出0，`private-suspend-observe-mutants-compiled.log`及JSON。
- RMM最终构建：`cmake --build build/rmm-client-bo-20261030/rmm-build-suspend-observe -j8`退出0，`rmm-private-suspend-observe-final.log`；最终固定U-Boot/FIT构建`python3 build/rmm-client-bo-20261030/build-private-suspend-observe-firmware-final.py`退出0，`private-suspend-observe-firmware-final.log`、`uboot-suspend-observe-final-commands.json`。内嵌RMM/布局检查分别见`private-suspend-observe-fit.json`、`private-suspend-observe-layout.json`；上游校验见`private-suspend-observe-patches.log`。
- 独占部署`firmware-private-suspend-observe-20261031-cg`通过`lab-run.py --allow-rk-reboot`执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-suspend-observe-final --run-id firmware-private-suspend-observe-20261031-cg`退出0；实际SD备份、UART、写入和能力见`build/firmware-runs/firmware-private-suspend-observe-20261031-cg/`。
- 完整720p执行下列命令退出1；日志`private-suspend-observe-hardware.log`和本run目录。独占回收`private-suspend-observe-evidence-20261031-cg`执行`pull-private-suspend-observe-evidence.py`退出0，11份文件SHA与板端相同；离线`analyze-private-suspend-observe-hardware.py`退出0，`private-suspend-observe-{hardware,scene-comparison,phase-comparison}.json`。
- 最终独占核验`private-suspend-observe-runtime-20261031-cg`执行`verify-private-suspend-observe-runtime.py`：核对46项源码、四项Guest运行载荷及实际SD2，保留CG，不再次刷写。当前冻结包`private-suspend-observe-candidate/`，RMM固件`firmware-private-suspend-observe-final/`，源码快照`private-suspend-observe-source/`，CC回退源码`before-private-suspend-observe/`、运行包`private-eventfd-probe-candidate/`、固件`firmware-private-resume-accept/`继续保留。最终核验不新增GPU测量。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cg -- \
 python3 build/rmm-client-bo-20261030/run-private-suspend-observe-with-uart.py \
 --images build/rmm-client-bo-20261030/private-suspend-observe-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

1000门槛仍FAIL，按流程未扩展广泛API/ML、多Client及恶意Proxy/Client、并发销毁/旧映射硬件矩阵。AE历史EBUSY未解决，CPU SIGNAL/eventfd不证明真实GPU完成eventfd，GPT/GPC和跨Realm实体隔离不由本轮证明。`requirements-audit.json`、`private-suspend-observe-followup-assessment.json`及checkpoint继续标记整体未完成。


## CH：完成路径低频诊断，完整720p728并恢复CG（2026-10-31）

统一记录：补齐CG缺失的实际路径计数｜CG728→CH728｜0分/0%｜临时RMM计数及每65536批一次摘要，其他四项Guest输入、Host、GPU请求600/实际594MHz、工作负载与CG相同；CPU未锁恒频，固件部署需要重启｜`private-heap-720-20261031-ch`退出1，原因仍为1000门槛；完整命令见下｜诊断用途，不宣称提分；源码与固件恢复CG728，整体目标未完成。

临时计数不参与授权、完成、进度或回收。只在已成功退休的FINISH之后按65536批输出累计摘要，避免每任务串口开销；原公开COMPLETE/PROGRESS、START、quiesce、RETURN及RETIRE逐函数与CG相同。FINISH提示条件拆成同序短路判断，以区分状态、读页、输入、extract、terminal sequence及错误字段。375阶段后端输出与CG的460847字节日志完全相同，24项SUSPEND及80项既有FINISH标记通过；完整私有套件582条PASS，模型不证明实体隔离。

**已证明CG路径在硬件任务中被调用。** UART仍有丢字：没有一行q/e/z全部完整，因此不拼接行、不补齐或推算缺失字段。四个独立记录中下表必需前缀完整，编号递增；状态/页读/输入不匹配计数均为0。每行extract计数恰好等于该行总回退数，说明记录范围内回退的第一处失败判断为extract；检查按顺序短路，这不说明terminal sequence已完成或未完成，也不能据此取消新鲜完成检查。

| 累计退休批数 | 快路径成功计数 | 回退计数 | extract首错计数 |
| ---: | ---: | ---: | ---: |
| 65536 | 48565 | 97209 | 97209 |
| 131072 | 90664 | 267361 | 267361 |
| 196608 | 145406 | 405545 | 405545 |
| 262144 | 210052 | 533961 | 533961 |

最后前缀内快路径成功计数/退休批数为80.13%，回退计数/退休批数为2.0369；这是截至262144批的累计比值，不是完整本轮每场景比例、API调用命中率或独立任务延迟分布，不外推至后续批次。最终Client累计退休277889批，与上述截点和CG278423批均不同。COMPLETE墙钟0.463495→0.464713ms/批、worker间隔0.305628→0.304893ms/批、完成查询2.841385→2.845726次/批；差值不证明性能收益或退化。完整33场景、计算预热、CPU SIGNAL/eventfd/basic、VM0/0、Host健康/资源及11份证据SHA通过；validation仍26成功/1既有数值失败/6无判据，blur120→120、terrain22→22、5×5 effect2d633→632FPS。1000门槛FAIL，未扩展广泛API/ML、多Client和实体攻击矩阵。

下一项待实施方案是仅优化**否定完成的观察**：若所有保护页/队列的合法边界与错误字段通过、至少一条受保护终止序号仍未到目标，并且读页之后原始START重查确认实际根/配置/所有流未异常，则只返回INCOMPLETE、保留全部引用，减少一次无效STATUS；任何成功完成仍保留新鲜状态、真实SUSPEND/AS禁用、CPU归还与退休。未知、损坏、过期/超前/回退前缀必须回到原完整观察或失败；不能让一条未完成队列掩盖另一条错误，不能跳过heap处理或延长期限。设计在`private-negative-observation-design.md`，**尚未实现或验证**。本轮只补充实际执行证据，不把提案当作优化完成。

证据默认位于`build/rmm-client-bo-20261030/`：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-suspend-diagnostic-backend.log`；完整私有检查加`GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/suspend-diagnostic-unit`执行`bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-suspend-diagnostic-unit.log`。与CG输出逐字一致记录于`private-suspend-diagnostic-model-comparison.json`，未新增安全模型或错误变体。
- `python3 build/rmm-client-bo-20261030/build-private-suspend-diagnostic.py`、`build-private-suspend-diagnostic-firmware.py`均退出0；RMM为O2 Debug/断言，23项flags与保留构建一致，预留0x2800000不变。FIT实际嵌入RMM `5a3f257ed263a6eb1edfc8af7eedf0c4039295b821b81446d249a46b7189f9d8`及ELF/BSS布局通过；固定9项上游补丁均APPLIED。`private-suspend-diagnostic-{build-validation,candidate-validation,fit,layout,patches}.json/log`及原始命令日志保留。
- 独占SD2部署`firmware-private-suspend-diagnostic-20261031-ch`执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-suspend-diagnostic --run-id firmware-private-suspend-diagnostic-20261031-ch`退出0；Realm能力1及CPU/pmthor恢复。原SD启动区备份、写入/UART/FIT证据见`build/firmware-runs/<run-id>/`。
- 完整720p命令如下，退出1；`private-suspend-diagnostic-hardware.log`与`build/lab-runs/private-heap-720-20261031-ch/`保留。四项Guest输入全部SHA命中、没有上传。独占回收`private-suspend-diagnostic-evidence-20261031-ch`执行`pull-private-suspend-diagnostic-evidence.py`退出0、11份固定文件SHA一致；离线分析`analyze-private-suspend-diagnostic-hardware.py`退出0，`private-suspend-diagnostic-{hardware,scene-comparison,phase-comparison}.json`明确区分完整前缀和受损尾部，没有完整十字段快照。
- `restore-private-suspend-diagnostic-source.py`退出0，仅恢复本轮改动的一份固件源码，46项哈希匹配原CG。独占`firmware-private-suspend-diagnostic-restore-20261031-ch`按同入口刷回CG的`firmware-private-suspend-observe-final/`；随后`private-suspend-diagnostic-runtime-20261031-ch`执行`verify-private-suspend-diagnostic-restored.py`，核验46项源码、四项Guest输入及实际SD2。回退记录见`private-suspend-diagnostic-{restore.log,final-runtime.json}`，恢复后没有新增GPU测量，当前728引用原CG结果。临时包、源码及变更前备份分别保留于`private-suspend-diagnostic-candidate/`、`private-suspend-diagnostic-source/`、`before-private-suspend-diagnostic/`。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ch -- \
 python3 build/rmm-client-bo-20261030/run-private-suspend-diagnostic-with-uart.py \
 --images build/rmm-client-bo-20261030/private-suspend-diagnostic-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

本轮未修复既有数值例外、AE VM_BIND EBUSY，也未验证GPU完成eventfd、多Client/恶意Client与Proxy、并发销毁或旧映射实体攻击。GPT/GPC不由本轮证明。原整体目标继续未完成。

## CI：合法未完成观察实验，728→718，撤回恢复CG（2026-10-31）

统一记录：对合法未完成终止序号省去一次STATUS｜CG728→CI718｜−10分/−1.37%｜只改RMM内部FINISH，四项Guest载荷、Host、完整33场景与CG相同，GPU请求600/实际594MHz，CPU未锁恒频；固件更新需要重启，单轮不证明稳定因果｜`private-heap-720-20261031-ci`退出1，原因仍为1000门槛｜未达预设736保留线，且5×5 effect2d低于550FPS场景保护，撤回候选并恢复CG728；整体目标未完成。

该候选对每条活跃队列检查保护页中的input、extract范围、终止序号范围、错误字段及既有观察前缀；至少一条终止序号合法未完成时，在全部页读回调后重放原START，核验真实根/AS配置、全局和全部stream状态，只返回INCOMPLETE，保留任务、Group和映射引用。不发布进度、不归还CPU访问、不退休；异常/不可读/前缀回退继续原完整观察。终止序号全到但extract过期仍回原STATUS，精确提示继续CG真实SUSPEND快照及完整停止后检查。公开COMPLETE/PROGRESS、原START/quiesce/RETURN/RETIRE等12个函数逐字与CG相同，Client的堆事件处理、重试预算及原始绝对期限未变。

**该优化实际被频繁使用，但端到端未受益。** 完整UART短行`GPU_PENDING_ONLY n=621285`证明否定观察命中；另一条fast/fallback行受损，不恢复或推算缺失字段。下表使用Client累计阶段墙钟和退休批次数归一化；各统计可能重叠，不相加，不当作纯CPU成本或按场景因果证据。更快返回未完成可能改变固定重试预算与调度节奏，但本轮没有足够的场景级时间线证明这一机制。

| 指标 | CG | CI |
| --- | ---: | ---: |
| 完整720p分数 | 728 | 718 |
| desktop blur FPS | 120 | 121 |
| terrain FPS | 22 | 19 |
| 5×5 effect2d FPS | 633 | 125 |
| 退休批次数 | 278423 | 273606 |
| 完成查询/退休批 | 2.841385 | 3.268890 |
| READY墙钟ms/批 | 0.117652 | 0.117380 |
| COMPLETE操作墙钟ms/批 | 0.463495 | 0.413815 |
| COMPLETE worker间隔ms/批 | 0.305628 | 0.373426 |
| 主动等待墙钟ms/批 | 0.278046 | 0.307308 |

本地398阶段后端通过，含23个新增场景、24个既有SUSPEND场景和80个既有FINISH标记；新增覆盖多队列未完成、不掩盖其他队列异常、读页后根/AS/全局/active与inactive流变化、既有进度回退、堆事件可发现、错误身份/服务/旧token及保留全部引用。582条完整私有检查标记通过；7个故意移除全队列/范围/错误/前缀/读后重查或误报成功的变体均成功编译后断言退出−6。早期五份失败日志保留：旧case2需要改成先INCOMPLETE再模拟GPU推进；input异常须先STATUS后失败；故障注入曾误放到其他回调、AS配置偏移曾选错寄存器，已修正后重验，不把未触发的注入当作通过。模型不证明实体GPT/GPC隔离或Linux并发。

RMM独立构建保留O2 Debug与断言，23项flags与保留构建一致，预留末址0x2800000；固定9项上游补丁、FIT实际嵌入RMM及ELF/BSS布局通过。CI RMM ELF为`b5110a72d269f74dfaab28aebe39ace9150f6d14ec05cb8c197e73193ff8a37d`。只通过独占入口写SD2固件，保存实际启动区备份，Host内核/rootfs不变；四项Guest输入SHA命中且无上传。完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端解绑、VM退出[0,0]、Host健康及CPU0–1/pmthor/进程/loop恢复通过；validation仍26成功/1既有数值失败/6无判据。11份证据SHA一致。1000门槛仍FAIL，未扩展API/ML、多Client或攻击矩阵。

证据默认位于`build/rmm-client-bo-20261030/`，包装证据在`build/lab-runs/<run-id>/`：

- 后端：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-pending-observe-backend-sixth.log`；完整私有检查加`GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/pending-observe-unit`执行`bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-pending-observe-unit.log`。`check-private-pending-observe-mutants.py`退出0及对应JSON/日志；前五轮失败日志原样保留。命令和SHA见`private-pending-observe-local-checks.json`。
- 构建：`build-private-pending-observe.py`、`build-private-pending-observe-firmware.py`退出0；命令、flags、FIT、布局和补丁分别见`private-pending-observe-{build-commands,build-validation,fit,layout}.json`、`private-pending-observe-patches.log`及`uboot-pending-observe-commands.json`。
- 独占SD2部署`firmware-private-pending-observe-20261031-ci`，执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-pending-observe --run-id firmware-private-pending-observe-20261031-ci`退出0；实际备份/UART在`build/firmware-runs/<run-id>/`。完整720p命令如下，退出1；`private-pending-observe-hardware.log`及run目录保存。独占回收`private-pending-observe-evidence-20261031-ci`执行`pull-private-pending-observe-evidence.py`退出0；离线分析`analyze-private-pending-observe-hardware.py`退出0，`private-pending-observe-{hardware,scene-comparison,phase-comparison}.json`。
- 撤回：`restore-private-pending-observe-source.py`退出0，仅恢复本轮两份源码并核对46项；独占`firmware-private-pending-observe-restore-20261031-ci`通过同部署入口刷回`firmware-private-suspend-observe-final/`退出0。最终独占`private-pending-observe-runtime-20261031-ci`执行`verify-private-pending-observe-runtime.py`退出0，核验46项源码、四项Guest输入和实际SD2；记录`private-pending-observe-final-runtime.json`、restore/runtime日志。当前源码、运行包和固件为CG，恢复后没有新增GPU测量，728引用原CG成绩。撤回候选/源码/变更前备份仍保留于`private-pending-observe-candidate/`、`private-pending-observe-source/`、`before-private-pending-observe/`。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ci -- \
 python3 build/rmm-client-bo-20261030/run-private-pending-observe-with-uart.py \
 --images build/rmm-client-bo-20261030/private-pending-observe-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

后续可评估“终止序号精确、extract合法但过期时直接选择真实SUSPEND刷新快照”，保留全部停止后检查与回收边界，尽量不改变未完成重试节奏；**CI结束时尚未实现或验证，随后在CJ实验并撤回，见下节**。本轮没有修复既有数值例外、AE VM_BIND EBUSY，未证明GPU完成eventfd、多Client/恶意Proxy与Client、并发销毁或旧映射实体攻击；`requirements-audit.json`和CI checkpoint继续标记整体未完成。

## CJ：终止序号辅助真实SUSPEND，728→729，撤回恢复CG（2026-10-31）

统一记录：扩大可用真实SUSPEND刷新完成快照的范围｜CG728→CJ729｜+1分/+0.14%｜仅RMM内部FINISH变化，四项Guest载荷、Host及完整33场景与CG相同，GPU请求600/实际594MHz，CPU未锁恒频；固件更新需要重启，单轮不证明稳定因果｜`private-heap-720-20261031-cj`退出1，原因仍为1000门槛｜低于预设736保留线，撤回候选并核验恢复CG728；整体目标未完成。

原CG要求保护页中的extract精确等于本批end，才选择真实SUSPEND作为完成快照与停止屏障。原生Panthor的`panthor_sched.c`说明队列快照会在SUSPEND或STATUS_UPDATE时刷新；CJ允许所有活跃队列的input/base与终止序号仍精确匹配、extract位于合法区间[base,end]但可能过期时，也选择真实SUSPEND。读保护页之后完整重放原START，核验真实根、AS配置、全局与全部stream状态；实际SUSPEND、AS flush/disable之后仍执行新鲜队列、scoreboard、blocked和OOM检查，最终quiesce、CPU归还与退休保持。不可读、损坏或未完成提示仍走原完整COMPLETE与重试节奏，不用终止序号单独证明完成。

**新路径实际命中，但端到端收益不足。** 完整短行`GPU_STALE_SUSPEND n=17086`证明新增选择路径在硬件中使用；范围包含预热和validation，不是逐场景独立任务数。另一条fast/fallback串口行受损，不补齐或推算缺失字段。下表按Client累计退休批数归一化；统计覆盖区间包括预热、validation且可能重叠，两轮任务数不同，不相加、不当作纯CPU成本或稳定因果收益。

| 指标 | CG | CJ |
| --- | ---: | ---: |
| 完整720p分数 | 728 | 729 |
| desktop blur FPS | 120 | 120 |
| terrain FPS | 22 | 22 |
| 5×5 effect2d FPS | 633 | 632 |
| 退休批次数 | 278423 | 278625 |
| 完成查询/退休批 | 2.841385 | 2.845674 |
| READY墙钟ms/批 | 0.117652 | 0.118236 |
| COMPLETE操作墙钟ms/批 | 0.463495 | 0.461599 |
| COMPLETE worker间隔ms/批 | 0.305628 | 0.305674 |
| 主动等待墙钟ms/批 | 0.278046 | 0.278186 |

本地401阶段后端通过，含50项SUSPEND场景（26项新增）及80项既有FINISH标记；完整私有套件582条PASS。11个故意破坏队列/边界/序号/读后配置重查或停止后条件的变体均成功编译后断言退出−6。首次后端失败来自case50的测试推进只更新两条队列中的一条；修正为精确终止序号后通过，原失败日志保留。模型不证明Linux并发或实体GPT/GPC隔离。

RMM保持O2 Debug与断言，23项flags与保留构建一致，预留末址0x2800000不变；固定9项上游补丁、FIT实际嵌入RMM及ELF/BSS布局检查通过。CJ RMM ELF为`fb28fe3cfc938487f8cde6b0e45f916a37b5016df46da8b7bd4756606351323e`。通过独占入口仅写SD2固件并备份启动区，Host内核/rootfs不变；四项Guest输入SHA命中且无上传。完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端解绑、VM退出[0,0]、Host健康与CPU0–1/pmthor/进程/loop恢复通过，11份回收证据SHA一致。validation仍26成功/1既有数值失败/6无判据，不能表述为完整正确性通过。

证据默认位于`build/rmm-client-bo-20261030/`，独占包装记录在`build/lab-runs/<run-id>/`：

- 后端：`HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-terminal-suspend-backend-second.log`；完整套件加`GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/terminal-suspend-unit`执行`bash scripts/check/check-rmm-gpu-private.sh`退出0，`private-terminal-suspend-unit.log`；`check-private-terminal-suspend-mutants.py`退出0，对应JSON/日志及失败点记录保留。首次失败在`private-terminal-suspend-backend-first.log`，汇总见`private-terminal-suspend-local-checks.json`。
- 构建：`build-private-terminal-suspend.py`、`build-private-terminal-suspend-firmware.py`退出0；`private-terminal-suspend-{build-commands,build-validation,candidate-validation,fit,layout}.json`、`private-terminal-suspend-patches.log`和`uboot-terminal-suspend-commands.json`记录准确命令与输入。
- 部署：独占`firmware-private-terminal-suspend-20261031-cj`执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-terminal-suspend --run-id firmware-private-terminal-suspend-20261031-cj`退出0；实际启动区备份/UART见`build/firmware-runs/<run-id>/`。720p命令如下，退出1，`private-terminal-suspend-hardware.log`保留。独占`private-terminal-suspend-evidence-20261031-cj`执行`pull-private-terminal-suspend-evidence.py`退出0；`analyze-private-terminal-suspend-hardware.py`退出0，输出`private-terminal-suspend-{hardware,scene-comparison,phase-comparison}.json`。
- 撤回：`restore-private-terminal-suspend-source.py`退出0，只恢复本轮两份源码并核对46项哈希。独占`firmware-private-terminal-suspend-restore-20261031-cj`按同入口刷回`firmware-private-suspend-observe-final/`退出0；独占`private-terminal-suspend-runtime-20261031-cj`执行`verify-private-terminal-suspend-runtime.py`退出0，46项源码、四项实际Guest输入及SD2实际固件读回均通过。`private-terminal-suspend-final-runtime.json`为`PASS_CG728_RESTORED`，restore/runtime日志及`private-suspend-observe-sd-readback.json`保留。恢复后没有新GPU测量，当前728引用原CG成绩；撤回候选、源码及变更前备份继续保留，未删除失败证据。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cj -- \
 python3 build/rmm-client-bo-20261030/run-private-terminal-suspend-with-uart.py \
 --images build/rmm-client-bo-20261030/private-terminal-suspend-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

CI省去否定观察STATUS虽缩短操作墙钟，却增加查询与调度间隔；CJ扩大SUSPEND适用范围实际命中17086次，总分仅+1。两轮结果不支持继续把该选择判断作为主要提分方向。后续应重新测量当前关键路径，或审视任务生命周期中的反复启动/停止与所有权交接；旧BQ部分区间的诊断不能直接当作当前CG成本比例。持久执行域等更大改动仍需映射、缓存、撤销、并发与公平性论证，尚未实现或验证，不能直接删除真实停止或CPU归还条件。

1000门槛仍FAIL，按流程未扩展广泛API/ML、多Client及恶意Proxy/Client、并发销毁或旧映射硬件矩阵；既有数值例外、AE VM_BIND EBUSY及真实GPU完成eventfd仍待解决，实体GPT/GPC隔离仍未证明。`requirements-audit.json`、CJ followup与checkpoint继续标记整体目标未完成。

## CK：当前基线分段计时，727分，诊断后恢复CG（2026-10-31）

统一记录：补测当前RMM缓存交接、固件握手与完成路径｜CG728→CK727｜−1分/−0.14%｜仅临时RMM计时，四项Guest输入、Host、完整33场景、GPU请求600/实际594MHz与CG相同，CPU未锁恒频；固件更新需要重启，诊断改变调用与静态布局，group销毁后每份报告按行等待5ms并独立输出三份｜`private-heap-720-20261031-ck`退出1，仍为1000门槛｜只用于诊断，不作性能候选保留；五份诊断源码与SD2固件均撤下，恢复并核验CG728，整体目标未完成。

旧BQ来自BM阶段且未覆盖最终Client文件，不能直接用于当前优化排序。本轮将独立计时回调放在既有策略锁内，保持原timeout时钟；记录两向`task_cache`、PREPARE_LAUNCH、READY_LAUNCH、内部`task_start`及其真实ACK循环、完成观察及STATUS循环、QUIESCE及SUSPEND/STOP循环、FINISH。当前内部启动函数同时服务首次启动与后续只读重查，计时覆盖READY_LAUNCH的实际启动，不只包裹公开START入口。7个函数移除明确计时语句后与CG原语句一致，没有新RSI操作或Guest ABI，计数不参与授权、超时、完成或回收。

**207份快照全部完整，未拒绝任何一份。** 采用序号207，累计RMM成功退休278177次；最终Client文件277845次，总数覆盖判据通过。差额332属于累计范围中的其他任务；完整报告中也存在退休数332的快照，但不据此把某个快照直接指定为正式计分起点。该检查不是逐token审计，不证明逐场景或纯benchmark窗口对应关系。全部指标来自同一完整快照，不跨报告填补。累计包含预热、validation、此前group及最后Client；RMM计数、Client计数采用各自分母，不混算。

| RMM计时（整函数包含子调用） | 次数 | µs/调用 | µs/累计退休批 |
| --- | ---: | ---: | ---: |
| cache_device | 278273 | 4.812 | 4.814 |
| cache_cpu | 278178 | 4.053 | 4.053 |
| prepare_launch | 278177 | 22.181 | 22.181 |
| ready_launch | 278273 | 112.897 | 112.936 |
| start_full | 2142760 | 18.077 | 139.241 |
| start_wait | 278177 | 69.768 | 69.768 |
| observe_full | 563014 | 60.207 | 121.855 |
| observe_wait | 563014 | 22.497 | 45.532 |
| quiesce_full | 834533 | 46.298 | 138.895 |
| quiesce_wait | 278177 | 92.729 | 92.729 |
| finish_full | 789873 | 94.019 | 266.963 |

相互独立的已测缓存交接合计8.867µs/累计批，三个ACK循环合计208.029µs/累计批。外层PREPARE_LAUNCH+READY_LAUNCH+FINISH合计402.080µs/累计批；前两项分别约占该已测外层总和2.21%与51.74%。它们不是整个应用的CPU比例或可兑现的提分预测；等待循环包含设备响应、缓存读取与检查，也不是GPU任务运行时间。START/OBSERVE/QUIESCE整函数嵌套于READY/FINISH，不再与外层相加。设备/CPU缓存交接也包含BO归属与租约检查，不等于纯缓存指令时间。

当前映射集合复用已使缓存扫描成本较小，继续优化页表定位或缩小控制页失效范围缺少优先级依据。更值得研究的是反复启动/停止握手及同一任务的重复状态检查。Client本轮READY、COMPLETE操作墙钟为118.190、465.663µs/Client退休批，COMPLETE间隔304.428µs/批，其中主动等待276.953µs/批；这些与RMM的累计范围不同，Client COMPLETE还包含堆查询等操作，差额不能直接归因于SMC、RPC或某个函数。

后续可以审查有界受保护执行域：在同Client、同context和冻结映射epoch内摊薄多批启动/停止；映射变更、CPU所有权归还、撤销、故障或Client切换时执行可信停止与失效。它需要独立证明每批真实完成、缓存可见性、跨批资源持有、旧token拒绝、恶意命令和公平性，**尚未实现或验证**。不能直接删除当前SUSPEND、AS disable或RETURN条件，也不能把GPU写入的单一序号当作成功证明。

本轮验证与证据默认在`build/rmm-client-bo-20261030/`：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，375阶段/2197条PASS标记，`private-current-cost-backend.log`与CG派生对照`private-suspend-diagnostic-backend.log`的460847字节完全一致。完整私有套件以`GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/current-cost-unit`执行`bash scripts/check/check-rmm-gpu-private.sh`退出0、582标记，`private-current-cost-unit.log`。`check-private-current-cost.py`退出0，启用独立计时回调、计数回绕/边界及全部11项；四个遗漏CPU缓存或START/STATUS/STOP计时的变体均编译成功后断言退出−6。`check-private-current-cost-parser.py`退出0，18项解析检查拒绝整份损坏报告、不拼接补值。模型不证明实体隔离。
- `build-private-current-cost.py`、`build-private-current-cost-firmware.py`退出0，23项O2 Debug/断言flags与保留构建一致，预留末址0x2800000不变；9项上游补丁APPLIED，FIT和实际ELF/BSS布局检查通过。诊断RMM ELF SHA为`7308ad43bd5f1992fbdc77ba08b93ff79e9a5f87513cee095abd90aecf33f804`，46项源码冻结于`private-current-cost-source/`，运行包`private-current-cost-candidate/`仅rmm.elf不同。`private-current-cost-{local-checks,policy-equivalence,candidate-validation,build-validation,fit,layout}.json`及补丁/构建命令日志保留。
- 独占SD2部署`firmware-private-current-cost-20261031-ck`执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-current-cost --run-id firmware-private-current-cost-20261031-ck`退出0，实际备份/UART见`build/firmware-runs/<run-id>/`；未改Host内核/rootfs。完整720p命令如下，退出1。四项Guest输入SHA一致且无上传；33场景、计算预热、CPU SIGNAL/eventfd/basic、VM0/0、Host健康与CPU0–1/pmthor/进程/loop恢复通过，validation26成功/1既有数值失败/6无判据。blur120→120、terrain22→22、5×5 effect2d633→631FPS。独占`private-current-cost-evidence-20261031-ck`执行`pull-private-current-cost-evidence.py`退出0，11份回收证据SHA一致。`analyze-private-current-cost-hardware.py`与`analyze-private-current-cost.py`退出0，输出硬件、场景、阶段及`private-current-cost-cost.json`完整快照和覆盖范围。
- 初次准备脚本沿用BQ的公开START锚点，被当前内部`task_start`结构断言拒绝；恢复已写入的三份文件后，改为只匹配实际函数定义再重做。首次成本分析发现派生脚本仍引用CJ阶段文件，正确拒绝缺失的CK文件；修正tag后重新分析。两次失败及原输出分别在`private-current-cost-preparation-first-failure.json`、`private-current-cost-analysis-first-failure.json`和first日志中，不属于GPU运行失败，不修改验收条件。
- 撤下：`restore-private-current-cost-source.py`退出0，只恢复五份诊断源码，46项CG源码哈希一致。独占`firmware-private-current-cost-restore-20261031-ck`按同部署入口刷回`firmware-private-suspend-observe-final/`退出0；独占`private-current-cost-runtime-20261031-ck`执行`verify-private-current-cost-runtime.py`退出0，核验46项源码、四项实际Guest输入与实际SD2，`private-current-cost-final-runtime.json`为`PASS_CG728_RESTORED`。恢复后没有新GPU测量，当前728引用原CG成绩；诊断包、源码与变更前备份继续保留。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ck -- \
 python3 build/rmm-client-bo-20261030/run-private-current-cost-with-uart.py \
 --images build/rmm-client-bo-20261030/private-current-cost-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

1000门槛仍FAIL，既有数值例外、AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client及恶意Proxy/Client、并发销毁或旧映射硬件矩阵仍未验收；实体GPT/GPC保护仍不由实验平台证明。`requirements-audit.json`、CK followup和checkpoint继续标记整体目标未完成。

## CL：保留映射的可信内存刷新原语，源码候选未部署（2026-10-31）

统一记录：为后续连续任务复用建立可信内存刷新边界，并加固现有停止路径的刷新后检查｜板端保留CG728→本版未测｜绝对/百分比分差均N/A｜修改运行源码但未部署，未跑完整720p，不将历史728当作新源码成绩｜本地run-id `private-live-flush-20261031-cl`，命令、退出码和证据如下｜保留本地源码候选，板端运行组合保持CG；整体目标未完成。

CK实测表明重复START/STATUS/SUSPEND等待值得优先研究，但当前`FINISH`同时承担真实完成判定、停止、AS禁用、CPU缓存归还和资源退休。退休还会清除队列输入并释放AS/CSG与缓存租约，因此不能仅省去SUSPEND或看到终止序号就复用上下文。原wrapper在CALL前执行`FLUSH_CACHE2`，任务后的WAIT与受保护序号不能单独当作输出缓存可见性的证明；也不直接沿用`latest_flush`作为无条件输出刷新指令。

本轮增加内部平台函数`plat_opencca_gpu_pt_flush_live()`，由实际`plat_opencca_gpu_pt_detach()`调用，替代其原来直接执行的刷新步骤。这个函数有真实生产调用者；保持CSG运行时的调用仅用于明确的后端模型验证，尚未向RSI或Guest开放。

1. 验证非零Client AS、精确64位根、固定内存/转换属性、AS0固件根与运行状态，检查shader/tiler和可信计时配置，遍历全部非零AS拒绝同根别名。AS已处于忙状态时先等待，超时不写寄存器。
2. 对同一AS的完整48位VA范围发出`LOCK → FLUSH_MEM`，有界等待命令完成。只写锁范围和AS命令寄存器，不写根、属性、UPDATE、CS/CSG输入或门铃。
3. 刷新后重新检查上述根、属性、别名和配置，并比较刷新前后的shader、定时配置及原始计数器频率；不会接受舍入后相同但实际改变的频率。失败不尝试重装、修复或清空AS。
4. 实际detach仍要求固件消费者先证明所有相关CS/CSG停止，之后才执行该原语、禁用AS并检查结果。内存核心仍在可能部分执行的硬件回调前设置隔离状态；刷新失败不清隔离、不归还CPU缓存、不退休或释放backing。

这个原语的职责只是完成一次内存刷新。它**不证明任务完成、不阻止之后的GPU写入、不赋予CPU所有权、不允许回收页面**。普通WB数据仍必须满足现有停止/禁用和CPU缓存失效条件。即使以后用于NC数据，也必须由可信消费者证明对应批次结束、没有再发布后继工作，并保持映射与生命周期租约；不能把本轮原语直接当成可发布成功fence的新操作。

本轮源码只变化3项：`plat/rk3588/src/rk3588_gpu.c`、`runtime/include/opencca_gpu.h`、`runtime/tests/opencca_gpu_backend_test.c`。RSI授权入口、私有内存核心、任务固件核心、两端Guest及Host均保持CG原源码。现有映射锁与MEDIATED授权仍覆盖实际detach调用；没有新RSI、Guest ABI、服务自报完成位或任意HPA/寄存器接口。

首次detach的根/别名检查统一由新原语执行，避免外层重复一遍；已经禁用AS的只读重试保留原来的独立检查。初稿与去重后的最终版本分别保留源码、构建和测试证据，最终版本再次执行后端与全部错误变体验证。

本地验证（以下路径默认位于`build/rmm-client-bo-20261030/`）：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，`private-live-flush-backend-final.log`：405个固件后端阶段，包含原375阶段与新增30阶段，共2538条PASS标记。直接MMIO模型覆盖活动GPU/精确重试、8类非法参数、27类只读前置拒绝、LOCK/FLUSH超时和29类刷新后变化；成功只写4次寄存器、没有UPDATE或门铃。它模拟命令完成，不证明真实GPU缓存已经完成清理。
- 新增双Client生命周期阶段：成功刷新后，实际内存/固件RETURN、RETIRE、RECLAIM及BO/group销毁仍被拒绝，没有CPU归还或控制页清除；随后原来的真实完成路径可以成功。29类故障在实际FINISH的刷新回调内注入，均进入失败保持状态，禁止后续成功完成/归还/释放；错误重试无新MMIO写入。测试仅移除MMIO替身中的注入故障以检查另一Client，未清除失败context的可信隔离和引用，不把这种替身恢复当作生产恢复机制。
- `GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/live-flush-unit HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-rmm-gpu-private.sh`退出0，582条PASS标记，`private-live-flush-unit.log`。
- `python3 build/rmm-client-bo-20261030/check-private-live-flush-final.py`退出0，候选及10个错误变体均编译成功，候选执行0、错误变体全部断言退出−6。覆盖错误刷新类型、遗漏后检查/别名/最后AS/忙状态/稳定配置检查、错误禁用、错误AS/范围，以及detach绕过新检查。证据为`private-live-flush-models.json`、`private-live-flush-mutations-final.log`和`live-flush-model-final/`；编译失败不计作拒绝通过。
- `python3 opencca/scripts/setup/apply-local-patches.py --check`退出0，9项APPLIED，`private-live-flush-patches.log`。`build-private-live-flush.py`退出0，独立O2 Debug构建的23份flags与保留构建一致，保留断言；RMM ELF SHA为`d08e9aae14c7d55e7aff2f2028af464ad9ca58a3aedc89d532573fc8c5599df1`，构建命令/退出码见`private-live-flush-build-validation.json`。`check-firmware-layout.py --rmm build/rmm-client-bo-20261030/rmm-build-live-flush/Debug/rmm.elf --uboot build/rmm-client-bo-20261030/firmware-private-suspend-observe-final/u-boot`退出0，ELF/BSS无重叠，预留末址仍为0x2800000，`private-live-flush-layout.json`；没有重新打包FIT或部署固件。
- 修改前备份`before-private-live-flush/`保留52份文件；`private-live-flush-source/`冻结48份源码与校验输入，`private-live-flush-source-changes.json`及`private-live-flush-delta.patch`保存相对CG的准确3文件差异。没有覆盖其他未提交改动，未操作板端运行树、SD或设备进程。
- `python3 build/rmm-client-bo-20261030/refresh-private-live-flush-evidence.py`退出0，核验当前/冻结源码、最终变体使用的平台SHA、实际ELF与布局SHA、23份flags和本地四项CG载荷，更新审计、产物清单及`private-live-flush-checkpoint-record.json`。首次证据收集因布局工具保留相对路径、收集器假设绝对SHA键而退出1，发生在元数据写入前；按规范化路径唯一匹配后通过。原失败见`private-live-flush-evidence-first-failure.{json,log}`，不属于GPU运行失败。没有把本地载荷校验写成新的板端/SD读回。

后续持久执行域需要一起实现的条件（本轮均未实现，不计作当前保证）：

| 边界 | 必须实现的行为 |
| --- | --- |
| 单批真实完成与结果可见 | 重新检查根/全部队列/受保护进度/scoreboard/错误/OOM，确认本批授权工作结束；在没有新发布的边界刷新GPU内存。NC数据的可见完成与整个执行域可回收必须分开；WB先保留停止路径。 |
| 同Client跨批复用 | RMM保留内部执行域、AS/CSG、缓存和映射引用，只为同owner/context/冻结epoch接纳下一批。新Client授权和Proxy接纳仍必要；旧外部token失效，不能把已完成token留作域权限。 |
| 队列与原生上下文 | 按受保护单调history追加wrapper，正确处理ring回绕、未发布前缀及所有队列；运行时不照搬当前每批重写`extract_init`的方法。 |
| 映射修改与退出 | MAP/UNMAP、BO/group销毁、CPU所有权变化和Client切换，必须协调执行域让出并完成可信停止/失效；检查等待票据，避免映射变更与新批次互相抢先。 |
| 有界调度与撤销 | 对驻留域/时间/批次数设置上限，在AS/CSG不足时可信驱逐空闲域；恶意超时或异常状态保留资源，只有可信停止/复位后才能回收，不能靠Proxy报告释放。 |

目前仍是每批停止/禁用/归还/退休。新增检查也可能增加该路径成本，本轮没有给出性能改善预测；待跨批机制与生命周期完整接通后，再按完整720p→1000门槛→更广回归的顺序验证。当前CG728的1000门槛FAIL及既有数值例外不变，AE EBUSY、真实GPU完成eventfd、广泛API/ML、多Client和实体攻击矩阵仍未验收；RK的GPT/GPC模拟不构成实体CPU拒读证明。

## CM：可信排空检查与保留租约交接基础，源码候选未部署（2026-10-31）

统一记录：为同 Client 后续任务保留受控 AS、映射和缓存租约，补齐运行状态下的排空证明｜板端CG728→本版未测｜绝对/百分比分差均N/A｜修改运行源码但未部署，无新增完整720p或硬件测量，不将历史728视为候选成绩｜本地run-id `private-live-drain-20261031-cm`，命令、退出码和证据如下｜保留本地候选，板端仍为CG；整体目标未完成。

CL提供了保留映射的内存刷新原语，本轮补充它的可信消费者和内存核心交接条件。这里的“排空”是：当前已授权、已发布的工作结束，队列及执行状态经过可信检查，数据访问租约继续保留。它与现有对外成功fence、CPU缓存归还、页面回收是不同边界。**本轮没有取消现有每批FINISH，没有新增RSI/Guest ABI或执行能力位，也没有把排空结果接入Client fence。**

实现分成三个部分：

1. 内存核心仅允许冻结映射、NC/常驻页面的保留交接。`gpu_private_task_live_eligible()`检查原service/Client/context/token、AS槽位归属、有效映射代次与受保护BO摘要，确认本批设备缓存交接扫描完成且没有普通WB页维护量；拒绝待映射、页表扩展、CPU归还、撤销和隔离状态。再次检查全部相关BO的owner/service、隐藏或NC转换完成状态、映射引用与缓存租约。普通WB页面继续使用原停止/归还路径。
2. `gpu_firmware_task_drain()`只供可信内部消费者或验证调用。先丢弃旧排空证明，再通过原PROGRESS路径发起新的STATUS并核验ACK与受保护进度；完成位图满后，还检查每个活动队列的INSERT、EXTRACT_INIT、extract、sequence/error、scoreboard、blocked/OOM及全部已发布前缀。检查完整START状态后执行CL的实际AS `LOCK/FLUSH_MEM`；刷新和NC屏障后重读队列，并再次复核完整START/页表根/配置，全部通过才记录排空。刷新前的正常未完成返回INCOMPLETE；刷新后的不一致或部分失败隔离并保持引用。缺回调的失败尝试也清除旧证明，不能用上一次排空绕过新检查。
3. `hold_live/put_live/handoff_live`提供内存元数据交接：只有已排空、同owner/context/epoch的任务才能为下一批验证命令范围并添加引用；取消暂存至少保留一个anchor引用；交接消耗旧任务引用、替换缓存token并清除设备交接游标，AS、根、映射代次和BO租约保持不变。交接本身无硬件回调或队列发布，后继仍须通过新的READY；旧token不能恢复权限。普通HOLD/PUT继续拒绝活动context。`drained`使用原结构体padding，AArch64断言确认context仍为112字节，slot/cache_groups偏移仍为104/110。

真实刷新适配器`opencca_gpu_private_pt_flush_live()`仍在GPU映射锁下检查MEDIATED状态，再调用CL的平台原语；`memory_ops.flush_as`在实际RSI适配器中接线。新DRAIN/租约接口没有不可信dispatch入口，现有COMPLETE/RETURN/RETIRE/FINISH语义保持原实现。新接口目前仅有明确验证调用者；**持久域生产路径尚未接通**，不能把ARM64构建成功说成已运行跨批复用。

本地验证（路径默认在`build/rmm-client-bo-20261030/`）：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0；`private-live-drain-backend-final-result.json`保存准确命令和环境，日志`private-live-drain-backend-final.log`。466个固件后端阶段，3026条PASS标记；新增61组双Client场景/122个DRAIN结果。覆盖成功与新STATUS重验、普通WB拒绝、满位图但scoreboard/blocked仍忙、未完成或非法sequence、过期ACK、MMU故障、缺flush回调、刷新/屏障失败、29类平台刷新后变化、18类受保护队列/配置变化、刷新后读失败，以及后续观察未完成/缺回调时旧证明失效。成功排空不允许RETURN/RETIRE/RECLAIM或BO/group销毁；后续真实FINISH仍可停止、禁用AS和退休。故障场景只移除测试替身的注入项以验证另一Client，未解除失败context/group的可信隔离或引用。
- `GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/live-drain-unit-final HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-rmm-gpu-private.sh`退出0，613条PASS标记，`private-live-drain-unit-final-{result.json,complete.log}`。永久检查入口新增31个实际内存核心场景，覆盖连续32次NC与常驻租约交接、旧token/错误身份、命令页范围、epoch/BO/AS归属、失败保持、取消anchor保护和可信复位。ASan/UBSan和断言保留。
- `python3 build/rmm-client-bo-20261030/check-private-live-drain.py`退出0，`private-live-drain-mutations.json`、`private-live-drain-mutations.log`、`live-drain-mutations-final/`。两个候选均编译/执行0；11个错误变体均成功编译后被断言拒绝（−6），覆盖忽略epoch/token/BO归属、复用旧token、错误释放anchor、遗漏屏障、忽略刷新前忙状态、遗漏刷新后队列/最终根检查、复用旧排空证明和跳过GPU内存刷新。首轮“忽略cache token”变体存活，说明原测试在新token尚未READY时被其他条件挡住，不能证明token检查有效；补充READY状态下直接错误token的断言后重验全部通过。原记录、脚本与日志保留为`*-first.*`及`live-drain-mutations/`。
- `python3 build/rmm-client-bo-20261030/build-private-live-drain.py`退出0，独立O2 Debug构建，23份flags与保留构建一致、断言保留；RMM ELF SHA为`fdfc74f273f21151ed818b164e7155e2ee59a4fca71e4714b6525c3baf49c8ee`，命令/退出码见`private-live-drain-build-validation.json`。`python3 opencca/scripts/check-firmware-layout.py --rmm build/rmm-client-bo-20261030/rmm-build-live-drain/Debug/rmm.elf --uboot build/rmm-client-bo-20261030/firmware-private-suspend-observe-final/u-boot`退出0，`private-live-drain-layout.json`；ELF/BSS无交叠，预留末址仍为0x2800000。首次传入工具不支持的`--output`被argparse拒绝（2），随后用stdout保存结果，失败留在`private-live-drain-layout-first-failure.json`。没有打包FIT或部署。
- 补丁清单校验退出0，9项APPLIED，`private-live-drain-patches-{result.json,log}`。49项最终源码/校验输入冻结在`private-live-drain-source/`，相对CL变化10项，见`private-live-drain-source-changes.json`、`private-live-drain-delta.patch`；改动前52项备份`before-private-live-drain/`保留。两端Guest、Host和CL平台源码没有变化。后端首次失败是旧夹具将NC BO交给不带回调的DESTROY并假定STATE；改为真实的受限RELEASE验证。第二次失败是模拟忙队列未再报告空闲就尝试FINISH；增加真实STATUS观察后通过。两个退出134的记录与日志均保留，不作为候选PASS。

`python3 build/rmm-client-bo-20261030/refresh-private-live-drain-evidence.py`退出0，核验49项当前/冻结源码、准确差异、最终模型与变体、23份构建flags、ELF/BSS、AArch64结构体断言及本地四项CG载荷；审计与产物清单已更新，最终摘要和哈希见`private-live-drain-local-checks.json`、`private-live-drain-checkpoint-record.json`。本地载荷核验不等于新的设备或SD读回。

所有以上结果都是控制机的实际核心/平台模型或构建检查，不执行真实GPU缓存指令，也不证明实体GPT/GPC CPU拒读。板端没有操作、无新增性能或隔离测量，最后设备验证仍为CK恢复CG的记录。完整720p的1000门槛仍未满足，既有数值例外、AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client和实体攻击矩阵均未补验。

下一步必须把这些基础一起接入受限持久执行域：按原生ring/history追加wrapper且不运行时重写EXTRACT_INIT；同Client后继任务完成READY与授权；同步提交GPU队列、缓存token与内部域元数据；旧外部token失效但保留域引用；MAP/UNMAP、Client切换、撤销与公平调度要求可信让出/停止。单独调用DRAIN或内存handoff不能完成这些条件，也不得提前向Client发布成功fence。全部连通后才有适合部署并跑完整720p的候选。

## CN：受限连续执行域与实际 RSI 接线（2026-10-31，硬件验收中）

统一记录：减少同 Client 连续任务的停止、AS 禁用和重新启动，同时保持真实完成与内存授权｜板端对照 CG728→本版尚未测完｜分差/百分比 N/A｜仅 RMM 运行代码变化，Client、Proxy、Host、initrd 与冻结 runner 保持 CG；GPU/CPU/内存条件由原性能入口控制｜本地 run-id `private-live-domain-20261031-cn`；部署 run-id `private-live-domain-fw-20261031-cn`，完整720p计划 run-id `private-heap-720-20261031-cn`｜本地候选已冻结，最终保留判断待硬件结果；整体目标未完成。

本轮把 CM 的排空与内存租约交接接入现有 FINISH、暂存、Proxy 选择、Client READY/PUBLISH，以及映射/销毁路径。没有新增 Guest 操作号、能力位或由 Proxy 提供的执行证明。

- 对 NC/常驻、受保护映射代次不变的任务，实际 FINISH 经新鲜 STATUS、全部活动队列、精确序号、错误/scoreboard、页表根与配置检查，并完成真实 AS 内存刷新与屏障后，才使旧公开 token 失效并返回现有完成字段。RMM 保留一个不可由公开任务接口访问的内部 anchor，继续持有 AS、CSG、映射和 BO/cache 租约。普通 WB、每第八批，以及不满足资格的任务仍真实停止、禁用 AS、归还并退休。成功完成可见性和资源释放分开；没有仅凭计数器或中断提示发布完成。
- 后继必须属于同 Client/context，只能有一个暂存后继，且连续追加只使用已活动队列。暂存验证新的命令页范围并添加独立 hold；取消尚未准备的后继只消耗该 hold。Proxy 的 PREPARE_LAUNCH 在旧生产者已排空的边界写入新 wrapper，不修改 INSERT 或运行中的 EXTRACT_INIT；写入前隔离，写入前后各完整排空检查，再无回调地提交 history、cache token 与任务归属。部分写入、根/配置变化或交接失败保留两个引用并隔离。
- `origin` 保存最近一次冷启动的 EXTRACT_INIT，`history` 保存本批起点；连续批次只推进 history。两张数组共16384字节，仍装入既有16392字节的发现 scratch。后继仍须实际 Client READY，原 PUBLISH 才能改变 INSERT 并通知已运行的队列；Proxy 单独选择、重放旧句柄或未 READY 的 START 都不能发布。连续40批的模型验证了 ring 回绕、每八批强制停止及冷启动重新选取真实 CSG/AS。
- 新队列、非延迟批次与旧单任务暂存先可信让出。实际 RSI 在 MAP、UNMAP、UNMAP_BO、CONTEXT_DESTROY、GROUP_DESTROY 前让出；暂存/已准备后继阻止假定“域空闲”。冷启动接纳先退休其他 Client 的空闲内部域，保留正在执行、准备或不确定状态的任务。批次数上限不是墙钟公平性或恶意长任务可抢占的证明。

本地最终验证（以下相对 `build/rmm-client-bo-20261030/`）：

- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，准确命令/环境见 `private-live-domain-backend-complete-result.json`，日志 `private-live-domain-backend-complete.log`，3444条PASS。包含486个直接后端阶段，以及由新永久入口 `scripts/check/check-gpu-domain-dispatch.py` 编译运行的21个实际 RSI 阶段。RSI测试直接提取并编译未改写的生产 dispatcher、使用实际固件/内存/平台核心；REC、通道查找、输入复制、策略锁和设备为模型。两个入口各有双Client40批连续运行和19类对抗/生命周期场景，共4条连续运行、76条对抗结果。检查17个公开旧token接口、错误身份/命令/通道、输入复制失败、重复暂存、部分ring/INSERT写入、写回调中根/游标/队列变化、未READY、Proxy选择重放、新队列冷恢复、非延迟回退、真实映射/销毁分发和跨Client空闲域让出。锁检查不替代真实多核并发验证。
- `GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/live-domain-unit-final HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-rmm-gpu-private.sh`退出0，613条PASS；`private-live-domain-unit-final-result.json`、`private-live-domain-unit-final.log`。保留断言与ASan/UBSan，内存租约核心未在CN修改。
- 2个候选编译执行0，13个错误变体均成功编译后被断言拒绝（−6），见 `private-live-domain-mutations.json`、`private-live-domain-mutations.log`、`private-live-domain-mutations-retry.log`、`live-domain-mutations/`。覆盖内部token暴露、无批次上限、遗漏history、运行origin跟随history、遗漏handoff、遗漏写后排空、部分写未隔离、新队列直接追加、遗漏空闲域让出、跳过READY，以及实际RSI遗漏MAP让出、仍调用旧FINISH、遗漏策略锁。首次脚本语法错误没有执行变体；首次“去掉锁调用”因替身函数未使用而编译失败，不计为拒绝；保留原证据后改成运行时不调用、成功编译并由锁断言拒绝，未重复已通过的其他变体。可重验脚本 `check-private-live-domain.py` 同时校验既有成功编译/拒绝证据。
- `python3 build/rmm-client-bo-20261030/build-private-live-domain.py`完成独立O2 Debug ARM64构建，23份flags与原保留构建一致、断言保留。ELF SHA `599059ac043328ca222e93a3dc196a27c48ca52e04d26d6e5049a6dc46a5dea0`，命令/退出码 `private-live-domain-build-validation.json`；`private-live-domain-layout.json`与`private-live-domain-fit.json`均PASS，ELF/BSS末址仍0x2800000。固定补丁检查9项APPLIED，未更新上游版本。固件打包入口 `build-private-live-domain-firmware.py`，产物 `firmware-private-live-domain/`；八项输入冻结于 `private-live-domain-candidate/`。
- 51项源码冻结 `private-live-domain-source/hashes.json`，相对CM改变7项（含2个新测试文件），差异 `private-live-domain-source-changes.json`、`private-live-domain-delta.patch`，改动前53项备份 `before-private-live-domain/`保留。`private-live-domain-local-checks.json`校验当前/冻结输入、变体、构建、ABI和未改Guest载荷。早期两次40批失败及后续新队列/空闲域让出失败均为设备夹具仍假定Client编号等于CSG；改为从实际映射/AS识别，保留全部失败记录。不得把模型通过称为硬件通过。

当前实现为正确性优先，live PREPARE 在 FINISH 已排空后仍进行两次新 STATUS/刷新；省去重复停止的硬件收益尚未测量，也不能从减少握手数量直接推导提分。未证明实体 GPT/GPC 拒读、DMA隔离或实机并发安全；既有数值例外、AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client与实体攻击验收仍保留。硬件结果与最终保留判断在本节后续补充。

CN硬件验收结果：部署wrapper退出0、SD2实际读回两项SHA匹配、RME能力1；完整720p入口退出1，renderer资格阶段已失败，未到benchmark barrier、无33场景成绩和有效score，分差/百分比均N/A。Client首次真实任务后出现`PRIVATE_BIND_ERROR stage=proxy-bind ret=-16`，Proxy记录`checked operation=12 status=2`并在`panthor_gpuva_sm_step_unmap`触发WARN_ON。Host健康PASS，两个VM退出0/0，CPU0-1/pmthor/GPU300MHz及内存资源恢复，无残留实验进程。独占取证run-id `private-live-domain-evidence-20261031-cn`退出0，10份普通文件SHA校验通过，证据`build/lab-runs/private-heap-720-20261031-cn/realm-evidence/`；物理UART保留，不能补齐交错受损文本。新只读tail尝试因尚无realm-1.log退出1，未修改设备。

发现实际VM_BIND是Client MAP_AUTHORIZE产生授权、Proxy SERVICE_MAP消费授权；CN仅为直接MAP等入口让出，未覆盖这条路径。新增pending授权后，保留域的原停止/归还也被原pending约束拒绝，故不能只在SERVICE_MAP末端补停止；须在Client创建授权前可信让出，并补齐service unmap与group控制映射消费者。后续CO将先用实际RSI模型复现，再修复，不放松pending/映射/任务租约检查。当前CN固件不保留为有效运行基线；板端健康，等待修正候选或CG恢复，整体目标未完成。


## CO：授权映射前让出连续执行域，758分保留候选（2026-10-31）

统一记录：修复CN首次任务后实际VM_BIND授权路径与保留执行域的互斥｜有效对照CG728；CN资格失败无有效分数→CO758｜+30分/+4.12%｜仅RMM固件改变，Client/Proxy/Host/initrd/runner保持原组合，GPU请求600/实际594MHz，CPU未锁恒频｜部署`private-live-map-yield-fw-20261031-co`退出0；测试`private-heap-720-20261031-co`退出1（低于1000门槛）｜保留CO758实验候选，整体目标未完成。

CN遗漏了实际的`MAP_AUTHORIZE → SERVICE_MAP`路径：Client先创建pending授权，Proxy随后消费授权建图。如果在创建授权之后才尝试停止空闲域，原有pending检查会阻止停止和退休。本轮在**创建授权之前**执行可信context yield，成功后才创建授权，未放宽pending或引用检查。SERVICE_MAP/SERVICE_UNMAP按RMM认证的实际Client定位context并让出；GROUP_CREATE与GROUP_CONFIGURE补齐相同的控制映射边界，configure仍先复制输入到私有内存。MAP_RELEASE仅释放授权元数据，保持原语义。

实际RSI回归先在CN源码上复现断言失败，修正后覆盖授权→service map、service unmap、group create/configure，以及后继暂存时让出失败不得留下新授权。直接后端490阶段加实际RSI25阶段共3508条PASS标记；7个遗漏让出、错误顺序、忽略失败或使用错误Client身份的变体，均成功编译后被断言拒绝。完整私有套件613标记引用CN既有结果，**未作为CO新测量重复计数**。

证据默认在`build/rmm-client-bo-20261030/`：`private-live-map-yield-local-checks.json`、`private-live-map-yield-backend-final-{result.json,log}`、`private-live-map-yield-mutations.{json,log}`；冻结51份源码，相对CN只变更dispatcher与后端测试两份文件，见`private-live-map-yield-source/hashes.json`及`private-live-map-yield-delta.patch`。O2 Debug ARM64保留断言，23份flags匹配既有配置，实际ELF/BSS与FIT检查通过，预留末址仍0x2800000；ELF SHA为`3f659534b5d53d184429e1fb08195f18c49c4aa3ebcf342403cdc8a706888181`。

固件只写SD2，部署备份、UART及Host恢复记录见`build/firmware-runs/private-live-map-yield-fw-20261031-co/`；Realm能力1，测试前实际SD字节回读一致。完整720p命令如下，实际输出758分；33场景、计算预热、CPU SIGNAL/eventfd/basic、VM退出0/0、两端日志及解绑、Host健康与CPU0–1/pmthor/loop/进程恢复通过。validation为26成功/1既有数值例外/6无判据；无新增VM_BIND、提交或fence错误。blur120→127、terrain22→22、5×5 effect2d633→658FPS，达到736保留线及三个场景下限。单轮且CPU未锁恒频，不能把+4.12%当作稳定因果收益。1000门槛仍FAIL，因此未扩展API/ML/多Client或实体攻击测试。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-co -- \
 python3 build/rmm-client-bo-20261030/run-private-live-map-yield-with-uart.py \
 --images build/rmm-client-bo-20261030/private-live-map-yield-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

独占证据回收`private-live-map-yield-evidence-20261031-co`执行`pull-private-live-map-yield-evidence.py`退出0，11份文件SHA一致，见`build/lab-runs/private-heap-720-20261031-co/{evidence-transfer.json,realm-evidence/}`。`analyze-private-live-map-yield-hardware.py`退出0，输出`private-live-map-yield-{hardware,scene-comparison,phase-comparison}.json`。实际Client阶段统计如下，按各自最终退休批数归一化；两轮任务数不同，累计包含计分之外的预热/校验，不作为纯CPU、GPU时间或单项因果收益。

| Client阶段 | CG728 | CO758 |
| --- | ---: | ---: |
| 退休批数 | 278423 | 289281 |
| READY操作墙钟 µs/批 | 117.652 | 58.556 |
| COMPLETE操作墙钟 µs/批 | 463.495 | 368.126 |
| COMPLETE工作间隔 µs/批 | 305.628 | 280.259 |
| 完成查询次数/批 | 2.841 | 2.530 |

CO PREPARE累计58.170s，约201.085µs/批；当前`task_prepare_live()`为保护写wrapper前后仍执行两次真实排空/STATUS/内存刷新。后续可以审查在冻结生产者、没有新发布的同一边界中复用排空不变量，但**尚未省略这两次检查**；不能将硬件实际完成、回调后根/全部队列检查或NC可见性要求一并删除。

CN的历史资格失败与CO修正前实际RSI红测保留；不能因此将历史AE EBUSY或所有并发映射问题标记已解决。真实GPU完成eventfd、广泛API/ML、多Client及恶意Proxy/Client、撤销/并发销毁/旧映射矩阵仍NOT_RUN，RK GPT/GPC模拟不构成实体隔离证明，整体目标保持未完成。


## CP：同次PREPARE内复用新鲜排空边界，803分保留候选（2026-10-31）

统一记录：减少连续域准备阶段一次重复STATUS和AS内存刷新｜CO758→CP803｜+45分/+5.94%｜仅RMM固件变化，Client/Proxy/Host/initrd/runner不变，GPU请求600/实际594MHz、CPU未锁恒频｜本地run-id`private-live-handoff-check-20261031-cp`，部署`private-live-handoff-check-fw-20261031-cp`退出0；完整720p`private-heap-720-20261031-cp`退出1（1000门槛）｜保留CP803实验候选，CO758回退保留，整体目标未完成。

CO的Client PREPARE墙钟约201µs/批，`task_prepare_live()`在同一策略锁内执行“真实排空→写未发布wrapper→再次真实排空”。CP保留第一次完整STATUS/全部队列检查/真实AS刷新和NC屏障；写入只落到受保护命令环，INSERT、EXTRACT_INIT、CS/CSG输入和门铃均不改变，因此这段边界没有新GPU工作可排空。第二次排空改为读取前后的完整START/真实根/配置检查，以及全部活动队列的输入、extract、sequence/error、scoreboard、blocked/OOM检查。仍验证内存核心的owner/context/冻结映射epoch/BO及缓存租约后才能无回调提交交接。

这个证明只在**同一次持锁PREPARE**内使用，不跨调用复用，不跨Client READY或producer发布。每批FINISH仍走新鲜STATUS和实际刷新，普通WB、冷启动、每8批让出、映射变更、撤销与失败保持条件不变。部分写入/读取失败或根、队列不一致仍隔离group并保留两份任务和backing引用；没有新增RSI、Guest ABI、任意页表或MMIO权限。

本地最终检查：直接后端511阶段及实际RSI46阶段，共3844条PASS标记；私有套件613条，均退出0。新增21种场景分别对两个Client执行，覆盖写wrapper后改变游标/序号/error/scoreboard/blocked/OOM/配置/未使用队列，以及最后一次snapshot复制后改变Client根、固件根或halt状态；检查故障注入必须实际发生。连续40批包含ring回绕和每8批完整停止，断言每次热PREPARE只执行一次AS刷新，旧token、READY门控、错误引用保持继续覆盖。7个变体均成功编译后断言拒绝：缺第一次drain、缺snapshot、忽略pending、缺读取后START、错误后检token、缺租约交接、重复第二次drain（性能次数保护，非安全增强）。

最终冻结`private-live-handoff-check-source-final/`共51份源码，较CO只改变固件核心与后端测试两份；`private-live-handoff-check-delta-final.patch`保存准确差异。O2 Debug ARM64构建保留断言，23份flags匹配，实际ELF/BSS与FIT检查通过，预留仍0x2800000；ELF SHA为`e8ced9d78b189d1d8ae5d274ab7d169bbbfcd50f7c8b42d947690b9a54cce954`。构建后只修正了不链接进固件的测试fixture，运行核心SHA未变；最终后端和变体使用最终测试。证据默认在`build/rmm-client-bo-20261030/`，见`private-live-handoff-check-{local-checks,backend-result,private-result,mutations,build-validation,layout,fit}.json`及同名日志，候选包`private-live-handoff-check-candidate/`。

保留两次验证失败：首个省略snapshot的错误变体因括号告警未编译成功，不计拒绝；随后忽略pending变体存活，查明新增case25..45误入旧`scenario>=15`控制yield分支，未到预期注入点。将旧分支限制为15..19并增加注入消耗断言后，候选及全部变体重新通过。诊断/早期源码和日志保留，未通过删用例或放宽生产检查消除失败。

预先设定保留线766分，场景下限blur114、terrain20、5×5 effect2d592FPS；仍需完整33场景、正确性、两端日志/退出、Host健康和资源恢复。该实验保留线不替代1000分门槛，门槛前不扩展API/ML/多Client验收。

CP完整720p实测803分，对照CO758为+45/+5.94%，对CG728累计+75/+10.30%；这是连续域及同次PREPARE检查复用的组合观测，单轮CPU未锁恒频，不宣称稳定因果收益。完整33场景、计算预热、CPU SIGNAL/eventfd/basic、VM退出0/0、两端内核日志/解绑、Host健康与CPU0–1/pmthor/loop/进程恢复通过；validation仍26/1/6。blur127→136、terrain22→24、5×5 effect2d658→682FPS，满足766和三个场景下限。严格runner因低于1000而退出1，不将其写为完整验收PASS。

独占证据回收`private-live-handoff-check-evidence-20261031-cp`执行`pull-private-live-handoff-check-evidence.py`退出0，11份远端文件SHA一致；`analyze-private-live-handoff-check-hardware.py`退出0，记录`private-live-handoff-check-{hardware,scene-comparison,phase-comparison}.json`。命令为`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cp -- python3 build/rmm-client-bo-20261030/run-private-live-handoff-check-with-uart.py --images build/rmm-client-bo-20261030/private-live-handoff-check-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，日志见`build/lab-runs/private-heap-720-20261031-cp/realm-evidence/`，UART单独保留。

| Client累计阶段统计，按各自退休批归一化 | CO758 | CP803 |
| --- | ---: | ---: |
| 退休批数 | 289281 | 306327 |
| PREPARE操作墙钟 µs/批 | 201.085 | 146.694 |
| READY操作墙钟 µs/批 | 58.556 | 59.043 |
| COMPLETE操作墙钟 µs/批 | 368.126 | 363.103 |
| COMPLETE间隔 µs/批 | 280.259 | 280.373 |
| 完成查询次数/批 | 2.530 | 2.532 |

PREPARE下降约54.391µs/批（27.05%），与减少重复排空的方向一致；其他阶段接近，不把包含预热/校验、RPC/RMM/设备等待的累计墙钟当成纯CPU或单独GPU时间。仍保留首次PREPARE和每批FINISH的新鲜STATUS/实际内存刷新；没有实现跨调用排空证明复用。

最终只读核验以独占`private-live-handoff-check-runtime-20261031-cp`执行`verify-private-live-handoff-check-runtime.py`，检查51项当前源码、四项实际Guest/runner载荷及实际SD2。未新增GPU测量；最终运行状态及证据封存见`private-live-handoff-check-final-runtime.json`和`private-live-handoff-check-checkpoint-record.json`。整体目标仍未完成，1000门槛、既有数值例外、历史AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML/多Client与实体攻击矩阵保留。


## CQ：隐藏空闲anchor排空证明重验，848分保留候选（2026-10-31）

改动目的｜减少连续执行域在FINISH后、下次PREPARE前没有新增GPU工作时的重复排空握手。对照CP803 → CQ848｜+45/+5.60%｜同Client/Proxy/Host/initrd/runner，GPU实际594MHz、CPU未锁恒频，两者均固件重启后单轮完整720p；仅RMM改变。保留CQ实验候选，1000门槛仍FAIL，目标未完成；不能把单轮差异认定为稳定收益。

**实现与保护边界：**

- FINISH仍执行真实STATUS、全部活动队列的extract/sequence/错误/idle检查、AS FLUSH_MEM及NC屏障和回调后的根/配置检查；成功后旧公开token才转为隐藏anchor。
- 新的内部`gpu_private_task_is_drained()`查询复用现有`ctx.drained`；同时重新校验真实身份、精确缓存token、AS slot归属、映射epoch、无pending/扩展及全部NC/常驻租约。没有新增Guest ABI、RSI操作或内存预留。
- `task_revalidate_idle()`只接受隐藏且已启动、已READY、未停止、未完成、无pending STATUS的anchor。PREPARE写入前和未发布wrapper写入后各检查一次：真实根/配置与所有流状态 → 全活动队列控制页快照 → 真实根/配置与所有流状态 → 证书有效性。复用的是受保护生产者保持不变的空闲状态，不能拿普通运行任务的旧STATUS作为新完成证明。
- handoff原子切换缓存token/历史并消耗drained证明；新任务仍由Client READY发布INSERT。映射授权、建表/撤销、组配置/销毁、Client切换及新活动队列继续完整让出，每第8批仍停止/禁用AS/归还/退休。失败或部分写入清除证明、隔离并保留所有引用。
- FINISH、READY、发布、START、停止、RETURN、RETIRE、stage/yield等11个关键函数与CP逐字相同；结构核对只提供变更边界证据。物理页表/MMIO保护仍是平台前提，RK GPT/GPC模拟不证明Proxy CPU/DMA物理访问已被硬件拒绝。

**本地与构建：** `bash scripts/check/check-dma-guard.sh`、`bash scripts/check/check-rmm-gpu-private.sh`由`check-private-idle-revalidate-local.py backend|private`记录，均退出0；HOST_CC使用现有O2断言编译器。533直接后端+68实际RSI阶段输出4196条PASS，私有套件613条。新增22种场景对两个Client覆盖PREPARE前损坏、最后一次读回调后的根/全局故障、清除旧证明；验证失败前不写新wrapper、不执行额外flush，旧公开token无法使用。40轮正常序列保持真实READY和周期让出。

`python3 build/rmm-client-bo-20261030/check-private-idle-revalidate.py`退出0：9个变体均成功编译后被断言拒绝，覆盖省略写前/写后重验、证书检查、队列快照、pending检查、读后START、租约交接、失败失效及重新引入重复排空。它们使用实际生产dispatcher/核心和设备替身，不是实体攻击隔离证明。51项源码冻结、相对CP4项变化，O2 Debug断言及23份编译flags保持；ELF/BSS/FIT通过，预留上界仍`0x2800000`。固件RMM SHA为`cfc3fa2220c008b4a2f7bf14b209696247557a30ff8774d9fbac144a641a05db`。

**实体测量与证据：**

- `private-idle-revalidate-before-20261031-cq`：只读核验原CP实际SD2，退出0。
- `private-idle-revalidate-fw-20261031-cq`：`lab-run.py --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-idle-revalidate --run-id <同ID>`；退出0，SD2备份/刷写及Host/Realm恢复通过。
- `private-heap-720-20261031-cq`：`lab-run.py --run-id <同ID> -- python3 build/rmm-client-bo-20261030/run-private-idle-revalidate-with-uart.py --images build/rmm-client-bo-20261030/private-idle-revalidate-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`；退出1，唯一runner错误为`private full-720p score below 1000`。33场景完成、Mali-G610、计算预热、CPU SIGNAL/eventfd/basic通过；VM0/0，两端kernel-log与pool-unbind、Host健康和资源恢复通过。validation仍26成功/1既有数值例外/6未知，不将其写成全部正确性通过。
- `private-idle-revalidate-evidence-20261031-cq`退出0，11份日志SHA核验；最终`private-idle-revalidate-runtime-20261031-cq`只读核对51项当前源码、四项实际Guest/runner载荷和实际SD2，退出0。最终核验后未新增GPU测量。

所有上述命令均由交互凭据helper进入统一lab wrapper，不记录密码；日志在`build/lab-runs/<run-id>/`，完整工作负载副本在`private-heap-720-20261031-cq/realm-evidence/`，固件UART/备份在`build/firmware-runs/private-idle-revalidate-fw-20261031-cq/`。

| 指标 | CP803 | CQ848 |
| --- | ---: | ---: |
| 完整720p score | 803 | 848 |
| blur FPS | 136 | 148 |
| terrain FPS | 24 | 26 |
| 5×5 effect2d FPS | 682 | 707 |
| PREPARE累计墙钟µs/批 | 146.694 | 94.821 |
| READY累计墙钟µs/批 | 59.043 | 59.743 |
| COMPLETE累计墙钟µs/批 | 363.103 | 358.727 |
| COMPLETE间隔累计µs/批 | 280.373 | 279.084 |
| 完成查询/批 | 2.532 | 2.528 |

预设保留条件为至少812分及blur≥122、terrain≥22、5×5 effect2d≥614FPS，均满足。计数包含预热/校验且任务数不同，不能视为纯CPU/GPU时间或逐token执行证明。当前使用`private-idle-revalidate-candidate/`和`firmware-private-idle-revalidate/`，CP803源码/固件回退保留。证据索引为`private-idle-revalidate-{local-checks,hardware,proof-audit,unchanged-boundaries,final-runtime,checkpoint-record}.json`、`private-idle-revalidate-source/hashes.json`及`private-idle-revalidate-delta.patch`，均位于`build/rmm-client-bo-20261030/`。

真实GPU完成eventfd、广泛API/ML/多Client、恶意Proxy/Client并发销毁、旧映射复用与撤销矩阵仍NOT_RUN；历史AE VM_BIND EBUSY和数值例外保留，CO只修复了CN的授权前让出问题。下一步可优先针对完成观察及等待开销，但不能减少真实完成、错误、归属与资源生命周期检查。


## CR：首次预测等待上限200→100µs，852分撤回恢复CQ（2026-10-31）

统一记录：减少Client首次FINISH查询前的预测等待｜CQ848→CR852｜+4分/+0.47%｜只变更Client内核，RMM/Proxy/Host/initrd/runner不变，GPU实际594MHz、CPU未锁恒频，无固件刷写或重启｜完整720p run-id `private-heap-720-20261031-cr`，退出1（低于1000门槛）；证据回收和恢复核验各退出0｜未达到预设857保留线，撤回CR并恢复CQ848，整体目标未完成。

本轮只将`PANTHOR_CLIENT_PRIVATE_POLL_DELAY_MAX_NS`从200000改为100000，连同首次等待及成功后的预测训练上限一起调整；后续最多8次50µs短等待、原始超时、真实FINISH、heap处理、错误传播、CPU归还及资源退休均保持。没有修改RMM的完成判定。候选与准确两文件差异保存在`build/rmm-client-bo-20261030/private-first-wait-cap-{source,candidate,delta.patch}`。

本地验证：Client ARM64 Image构建完成（`client-private-first-wait-cap.log`，内置release `6.12.0-g39d95dd028d4-dirty`，#86）；固定上游补丁清单9项APPLIED；`bash scripts/check/check-rmm-gpu-private.sh`输出608条PASS标记，见`private-first-wait-cap-private.log`。随后用O2、ASan/UBSan执行`python3 scripts/check/check-gpu-private-submit.py`退出0，101项提交用例通过，见`private-first-wait-cap-submit-final.log`。前两次提交测试分别停在旧上限对应的150000和50000数值断言；按100µs上限修正为75000和25000后通过，首轮及重试失败日志保留，不属于GPU运行失败。未扩展用例数量，也未重新运行未变化的RMM后端变体矩阵。

完整720p命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cr -- \
 python3 build/rmm-client-bo-20261030/run-private-first-wait-cap-with-uart.py \
 --images build/rmm-client-bo-20261030/private-first-wait-cap-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

唯一runner错误为`private full-720p score below 1000`。33场景、Mali-G610 renderer、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log及pool-unbind通过；两个VM退出0/0，Host健康及CPU0–1/pmthor/loop/进程恢复通过。validation仍26成功/1既有数值例外/6无判据，不能称全部数值正确性通过。预设场景下限为blur≥133、terrain≥24、5×5 effect2d≥636FPS，三项均通过：

| 指标 | CQ848 | CR852 |
| --- | ---: | ---: |
| blur FPS | 148 | 144 |
| terrain FPS | 26 | 25 |
| 5×5 effect2d FPS | 707 | 695 |
| 首次预测等待µs/累计退休批 | 174.213 | 97.161 |
| 全部主动等待µs/累计退休批 | 252.182 | 209.576 |
| 完成查询次数/累计退休批 | 2.528 | 3.201 |
| COMPLETE操作墙钟µs/累计退休批 | 358.727 | 397.008 |
| COMPLETE间隔µs/累计退休批 | 279.084 | 237.762 |
| COMPLETE操作+间隔µs/累计退休批 | 637.810 | 634.771 |

首次等待约减少77.052µs/批，但更早查询带来约26.65%的查询次数增加，COMPLETE操作墙钟增加约38.282µs/批；后续短等待也抵消了部分首次等待节省。完成操作与间隔合计只减少3.040µs/批（约0.48%），与整体弱收益方向一致。这是包含预热/校验、RPC/RMM/设备等待的每文件累计统计，两轮退休批数分别323997和324314，不是纯CPU/GPU时间、计分窗口内逐任务证明或稳定因果结论。不能把减少主动等待直接等同于减少应用耗时。

证据：`private-first-wait-cap-evidence-20261031-cr`通过统一lab wrapper运行`pull-private-first-wait-cap-evidence.py`退出0，11份日志SHA核验通过，位于`build/lab-runs/private-heap-720-20261031-cr/realm-evidence/`；`analyze-private-first-wait-cap-hardware.py`退出0，生成`private-first-wait-cap-{hardware,scene-comparison,phase-comparison}.json`。UART与Host健康结果保存在同一run目录，完整控制机日志为`private-first-wait-cap-hardware.log`。

恢复：`private-first-wait-cap-runtime-20261031-cr`通过统一wrapper运行`verify-or-restore-private-first-wait-cap-runtime.py`退出0，恢复Client源码、测试中两处旧参数预期及板端Client Image；51项源码、四项实际运行输入、实际SD2固件核验通过，见`private-first-wait-cap-final-runtime.json`。当前仍使用`private-idle-revalidate-candidate/`和`firmware-private-idle-revalidate/`；CR候选和失败证据保留，恢复后没有新增GPU测量，不能把848写成恢复后的重测分数。

1000分门槛仍FAIL；真实GPU完成eventfd、广泛API/ML/多Client及实体攻击NOT_RUN，既有数值例外和历史AE EBUSY保留。后续若继续优化应针对一次真实完成查询的成本或有效查询时机，而不是单独继续缩短首次空转；尚未实施新策略。本次文档记录已完成的CR测量，文档编辑及恢复后核验没有新增性能测量。


## CS：同次DRAIN复用新鲜观察，856分撤回恢复CQ（2026-10-31）

统一记录：减少RMM连续执行域完成观察中的重复队列快照与配置重查｜CQ848→CS856｜+8分/+0.94%｜仅RMM固件改变，同Client/Proxy/Host/initrd/runner，GPU实际594MHz、CPU未锁恒频，CQ与CS均为固件重启后单轮完整720p｜部署`private-drain-observation-fw-20261031-cs`退出0，测试`private-heap-720-20261031-cs`退出1（低于1000门槛），恢复与最终核验退出0｜未达预设857保留线，撤回CS并恢复CQ848，整体目标未完成。

**机制及边界：** 原DRAIN先由`task_observe()`执行新鲜STATUS握手、全活动队列快照及读后完整START检查，随后又执行一次`task_idle_snapshot()`和START检查才调用真实AS刷新。本轮让前一个观察通过调用栈私有的`bool *idle`返回排空候选：初始化为false，只有全部队列的extract、sequence/error、scoreboard、blocked/OOM及真实根/配置通过新鲜检查，且全部成员已发布、heap状态允许时才设置。DRAIN仍检查完整观察掩码，再立即执行原来的真实`FLUSH_MEM`与缓存屏障；刷新后的全部队列快照、完整START与租约检查保持。地址换算使用原有可信地址辅助函数；不在这个复用边界增加控制页读写、发布或策略锁释放。

该值不进入Guest ABI，不保存为跨调用凭据，也不代替CQ的隐藏anchor证书；PROGRESS/COMPLETE的公开包装传NULL。已完成重放、失败和未完成观察不能生成新的idle许可。没有删除真实STATUS、GPU内存刷新、停止/禁用AS、CPU归还或退休条件。九个关键函数与CQ逐字一致，包括START、QUIESCE、READY_LAUNCH、SUSPEND完成、隐藏anchor重验、连续PREPARE、RETURN/RETIRE及FINISH_DOMAIN；普通完成路径只增加NULL参数。正常单队列DRAIN的控制读取由9降至6，性能次数断言不作为隔离能力证明。

**本地验证：** 51份最终源码冻结在`build/rmm-client-bo-20261030/private-drain-observation-source/`，只改变固件核心和后端测试两份；准确差异`private-drain-observation-delta.patch`。新增6个故障阶段，在刷新前或刷新后最后一次控制页复制结束时改变Client根、固件根或全局故障状态，断言注入实际发生、刷新前故障不得进入flush、刷新后故障不能释放或复用引用。正常和异常均检查真实RMM私有核心及平台后端，设备/REC/页访问是替身，不证明实体GPT/GPC阻断。

- 最终直接后端：`check-private-drain-observation.py`的candidate使用O2、ASan/UBSan编译并执行实际后端，539阶段、3608条PASS标记，退出0；命令在`private-drain-observation-mutations.json`，日志`drain-observation-mutations/candidate/{build,run}.log`。
- 最终RSI：`HOST_CC=<实验目录>/cc-debug-o2 python3 scripts/check/check-gpu-domain-dispatch.py --out build/rmm-client-bo-20261030/drain-observation-rsi-final`退出0，74阶段、682条PASS标记，`private-drain-observation-rsi-final.log`。首轮完整DMA入口也退出0；最终两个新增次数断言由上述最终直接/RSI执行覆盖。
- 完整私有套件：`HOST_CC=<同上> GPU_PRIVATE_TEST_OUT=<实验目录>/drain-observation-unit bash scripts/check/check-rmm-gpu-private.sh`退出0，613条PASS标记，`private-drain-observation-private.log`。补丁清单9项APPLIED，退出0。
- 7个错误变体全部成功编译后被断言拒绝（−6），分别遗漏idle字段、观察读后START、idle消费、刷新后快照、刷新后START、真实flush，或重新引入重复快照。最后一个检查性能次数，其他检查完成/隔离边界。证据`private-drain-observation-mutations.{json,log}`及对应子目录。
- 独立O2 Debug构建、23份编译flags与保留基线一致，断言保留；ELF/BSS及FIT实际嵌入检查退出0，预留仍0x2800000。RMM ELF SHA `f3143201d47d17124956a435115fe5dfbecce125a1c45d92fe3916dc9829bc75`，见`private-drain-observation-{build-validation,local-checks}.json`、`private-drain-observation-{layout,fit}.log`。候选包只改变rmm.elf/rmm.img；测试两端的四项运行输入未上传变化。

**硬件测量：** 先通过统一wrapper与`deploy-rmm-firmware.py`仅刷SD2，保留启动区备份、UART并核验Host和Realm能力；实际SD回读两项SHA通过。完整720p命令为：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cs -- \
 python3 build/rmm-client-bo-20261030/run-private-drain-observation-with-uart.py \
 --images build/rmm-client-bo-20261030/private-drain-observation-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

唯一runner错误为`private full-720p score below 1000`。33场景、Mali-G610、计算预热、CPU SIGNAL/eventfd/basic、两个VM退出0/0、两端kernel-log/pool-unbind及Host健康/CPU0–1/pmthor/loop/进程恢复检查通过。validation仍26成功/1既有数值例外/6无判据；CPU SIGNAL冒烟不是实际GPU完成eventfd证明。`private-drain-observation-evidence-20261031-cs`通过wrapper执行`pull-private-drain-observation-evidence.py`退出0，11份日志SHA核验通过；`analyze-private-drain-observation-hardware.py`退出0。证据位于`build/lab-runs/private-heap-720-20261031-cs/realm-evidence/`，控制机总日志`private-drain-observation-hardware.log`。

| 指标 | CQ848 | CS856 |
| --- | ---: | ---: |
| blur FPS | 148 | 149 |
| terrain FPS | 26 | 26 |
| 5×5 effect2d FPS | 707 | 710 |
| PREPARE累计墙钟µs/退休批 | 94.821 | 94.937 |
| READY累计墙钟µs/退休批 | 59.743 | 60.000 |
| COMPLETE累计墙钟µs/退休批 | 358.727 | 349.718 |
| COMPLETE间隔累计µs/退休批 | 279.084 | 279.748 |
| 完成查询次数/退休批 | 2.528 | 2.522 |

COMPLETE操作约减少9.009µs/批（2.51%），与消除一次重复读取的方向一致；操作+间隔约637.810→629.466µs/批（−1.31%）。统计覆盖每文件累计，退休批数323997与326897不同且包含预热/校验，操作含RPC/RMM/设备等待；不是纯CPU/GPU时间或逐任务因果证明。三个场景通过预设133/24/636FPS下限，但856低于857，不能在结果出来后降低保留线，也不宣称稳定提分。

**恢复与现状：** `private-drain-observation-restore-20261031-cs`通过wrapper部署CQ固件，退出0；`private-drain-observation-runtime-20261031-cs`执行`verify-or-restore-private-drain-observation-runtime.py`退出0，恢复两份实验源码，核对51项CQ源码、四项运行输入及实际SD2哈希，见`private-drain-observation-final-runtime.json`。当前仍为`private-idle-revalidate-candidate/`与`firmware-private-idle-revalidate/`；CS源码/构建/固件保留供复验，板端两次部署snapshot均登记为本轮证据。恢复后无新增GPU测量，848为CQ原测分数。

1000门槛FAIL，既有数值例外、历史AE EBUSY、真实GPU完成eventfd、广泛API/ML/多Client及恶意并发/撤销/旧映射矩阵未验收。RK模拟不证明实体CPU/DMA拒绝。后续应优先评估更大的任务生命周期开销，而非单独继续压缩这次重复读取；尚未实施新策略。此次文档补记及恢复后核验没有新增性能测量。

## CT：按可信竞争状态选择保留周期，867分保留（2026-10-31）

统一记录：摊薄连续任务的完整停止/恢复成本，同时在真实等待者出现时让出资源｜CQ848→CT867｜+19分/+2.24%｜仅RMM固件改变，同Client/Proxy/Host/initrd/runner，GPU实际594MHz、CPU未锁恒频，均为固件重启后单轮完整720p｜部署`private-domain-policy-fw-20261031-ct`退出0；测试`private-heap-720-20261031-ct`退出1，唯一runner错误为低于1000分｜达到预设857保留线及场景保护条件，保留实验候选，整体目标未完成。

**机制：** CQ每8批完整停止、禁用AS并退休。CT新增私有`task_domain_quantum()`，只读取RMM已经接纳的任务记录：没有其他公开组任务时最多保留32批；有其他组活动任务时沿用8批；有未启动、未准备、组状态为RESERVED的真实等待任务时，在当前任务下一个真实完成边界完整停止。不同Client和同Client不同组都能触发让出。已分配但没有任务的空组、无效身份或参数导致被拒的请求不算竞争者，Proxy不能用一个提示位控制周期。

已经准备的组已占有自己的AS/CSG，不需要当前组退出才能READY；隔离中或关闭中的组不能直接消费释放的资源，仍保留引用并保守采用8批，不靠调度修复失败状态。最初将这些状态误当等待者，已有对抗用例分别暴露问题；两次失败日志保留在`private-domain-policy-backend-first.log`和`private-domain-policy-backend.log`，最终回归通过。

这里改变的是上下文保留周期，不是批次完成标准。每批仍执行真实STATUS/全部队列观察、AS刷新、Client就绪和映射/缓存租约检查，旧token仍不可使用。完成、刷新、启动、停止、隐藏anchor重验、连续PREPARE、RETURN和RETIRE等10个函数与CQ逐字相同，没有新增RSI或Guest ABI。32/8/1是任务批数边界，不是时间配额，不保证恶意长任务下的响应时间、严格轮转或抗拒绝服务；多Client实体公平性尚未测量。

**本地验证：** 51项源码冻结在`build/rmm-client-bo-20261030/private-domain-policy-source/`，仅固件核心和后端测试两项改变，差异见其中`change.patch`。正常双Client模型扩展至96轮：其他Client仍活跃时84次保留/12次完整让出，另一Client退休后93次保留/3次完整让出；随后接纳另一个真实任务，检查下次完成即清根/禁用AS并拒绝旧token。该等待任务在模型中取消，没有据此宣称实体调度成功或时延上界。

- `HOST_CC=<实验目录>/cc-debug-o2 bash scripts/check/check-dma-guard.sh`退出0，覆盖实际平台/私有核心的533个直接阶段及68个实际RSI阶段；日志`private-domain-policy-backend-final.log`、结果`private-domain-policy-backend-final-result.json`。
- 同编译器执行`bash scripts/check/check-rmm-gpu-private.sh`退出0，613条PASS标记，日志`private-domain-policy-private-final.log`。固定补丁清单检查退出0。
- `python3 build/rmm-client-bo-20261030/check-private-domain-policy-final.py`退出0，7个错误变体均成功编译后由断言拒绝：独占仍固定8批、无限延长独占周期、共享32批、忽略等待者、忽略同owner不同组等待者、误把已准备或隔离任务视作可运行等待者。见`private-domain-policy-mutations-final.json`及`domain-policy-mutations-final/`。初版测试误把仅移除冗余`!preparing`检查也预期为失败，但RESERVED条件已排除该状态；该存活变体及测试预期失败保留，未当作被拒变体计数。
- 独立O2 Debug RMM构建、23份flags对照、断言保留及ELF/BSS/FIT检查通过，预留末址仍为0x2800000。RMM ELF SHA `3f433e0d62e0355ce58f0bf3602e328bac04a09ddc234e7c1108f270010a2a9c`。仅候选包的rmm.elf/rmm.img不同；汇总`private-domain-policy-{build-validation,local-checks,candidate-validation}.json`。这些模型使用设备/REC/页访问替身，不证明实体GPT/GPC阻断。

**硬件测量：** 通过统一wrapper仅刷SD2，保留真实启动区备份、UART、Host恢复与RME能力检查，实际SD两项固件SHA回读匹配。完整720p命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-ct -- \
 python3 build/rmm-client-bo-20261030/run-private-domain-policy-with-uart.py \
 --images build/rmm-client-bo-20261030/private-domain-policy-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

33场景、Mali-G610/Panfrost、计算预热及CPU SIGNAL/eventfd/basic均完成，VM退出0/0，两端日志/控制池解绑、Host健康、pmthor/CPU集合及资源恢复检查通过。validation仍为26/1/6，保留既有数值例外，不能称全部正确性PASS。11份证据拉回并逐项SHA核验；记录`build/lab-runs/private-heap-720-20261031-ct/{result,host-kernel-health,after,evidence-transfer}.json`及`realm-evidence/`。CPU SIGNAL/eventfd探针不等于真实GPU完成eventfd验证。

| 指标 | CQ | CT |
| --- | ---: | ---: |
| 完整720p分数 | 848 | 867 |
| blur FPS | 148 | 152 |
| terrain FPS | 26 | 26 |
| 5×5 effect2d FPS | 707 | 711 |
| COMPLETE查询/累计退休批 | 2.528 | 2.474 |
| PREPARE操作µs/累计退休批 | 94.821 | 97.123 |
| READY操作µs/累计退休批 | 59.743 | 53.660 |
| COMPLETE操作µs/累计退休批 | 358.727 | 347.499 |
| COMPLETE间隔µs/累计退休批 | 279.084 | 272.670 |

三个场景通过预设133/24/636FPS下限，867超过857保留线。COMPLETE操作减少11.227µs/批，操作与间隔合计637.810→620.169µs/批（−2.77%）；PREPARE并未下降。累计退休批323997→330910，窗口包含预热/校验且含RPC/RMM/设备等待；没有独立统计实体完整让出次数，不能由此精确归因停止/恢复节省，更不能把单轮2.24%视为稳定收益。分析见`private-domain-policy-{hardware,scene-comparison,phase-comparison}.json`。

**保留及限制：** 当前包为`private-domain-policy-candidate/`，固件为`firmware-private-domain-policy/`；CQ848匹配源码及固件保留回退。1000分门槛FAIL，广泛API/ML、多Client实体调度及隔离攻击、真实GPU完成eventfd均未追加；历史AE EBUSY及数值例外保留。RK平台模拟不证明物理CPU/DMA拒绝。此次新增一次完整720p测量；文档整理和最终运行输入核验没有新增性能测量。

最终核验：`private-domain-policy-runtime-20261031-ct`经统一wrapper运行`verify-or-restore-private-domain-policy-runtime.py`退出0，51项源码、四项板端运行输入及实际SD2固件SHA均匹配CT，状态`PASS_CT_RETAINED`，见`private-domain-policy-final-runtime.json`。没有再次刷写或在核验后新增GPU测量。

## CU：有界轻量序号提示，866分撤回恢复CT（2026-10-31）

统一记录：用非授权的轻量序号提示减少GPU忙时完整STATUS/heap查询｜CT867→CU866｜-1分/-0.12%｜RMM与Client改变，同CT Proxy/Host/initrd/runner，GPU实际594MHz、CPU未锁恒频，均为重启后单轮完整720p｜部署`private-sequence-probe-fw-20261031-cu`退出0，测试`private-heap-720-20261031-cu`退出1，证据及最终核验退出0｜预设保留线876、场景下限137/24/640FPS，撤回CU并核验恢复CT867，整体目标未完成。

**机制与安全边界：** 原Client每次COMPLETE worker都进入完整FINISH。新增可选`TASK_POLL`，RMM根据认证通道/实际Client身份和公开token找到私有任务记录，只对已完整发布并启动、没有待处理heap/停止/STATUS状态的任务新鲜读取16字节完成记录。合法范围内尚未达到目标且无错误时返回busy提示；已达目标、序号越界、读失败或状态不确定均返回“执行原FINISH”。它不做完整根/MMIO检查或STATUS握手，也不发布完成证明、不变更任务状态、不归还CPU所有权或退休引用，所以不能当作GPU完成或隔离认证。

Client仅对单成员任务使用，每连续3次busy提示后第4步强制完整FINISH，未完成时继续heap事件服务；ready/不确定提示在同次worker立即执行完整FINISH。原始截止时间、后续8次短等待、首次最多200µs预测和错误保留路径保持。旧RMM没有bit35时使用原路径；ABI2/RPC4、旧操作号及完整执行能力位不变。桥接层严格核验返回队列、布尔值与保留字段，两种提示都保留token，禁止raw ioctl操作内核托管任务。

**本地验证：** 51项最终源码及12项差异冻结于`private-sequence-probe-source/`。`check-gpu-private-submit.py`109项、`check-gpu-task-bridge.py`156项通过；完整私有套件与DMA入口退出0，直接后端533阶段/实际RSI68阶段。完整套件早于最后的测试夹具增强，最终直接/RSI候选及worker/bridge候选覆盖最终测试源码，生产逻辑没有后改。最终直接后端6个、Client/bridge5个错误变体均成功编译后被断言拒绝，覆盖无界提示、跳过强制heap、把提示当完成、提前退休、错误队列、身份/旧token/序号/错误码检查。最初RSI变体测试因独立认证层拒绝了坏通道，使删除核心认证的变体存活；该期望失败单独保留，未计为拒绝。早期后端夹具失败及首次错误firmware目录的Client构建失败同样保留。

独立RMM O2 Debug构建、23份flags一致、断言及预留末址0x2800000保持，ELF/BSS/FIT检查与正确固件目录下Client Image构建退出0。RMM ELF SHA `c1c169e53dc6b1d352ff63d7e1314d1a58a209e68f17314ea9def1ae5abb3d6b`；候选包只改变Client Image与RMM两项载荷，Proxy不重建。证据`private-sequence-probe-{candidate-validation,local-checks,mutations-final,client-mutations}.json`及关联日志；模型使用设备/REC/物理页替身。

**硬件与开销：** 全部板端操作经lab wrapper，部署仅SD2并备份实际启动区、保留UART、验证Realm能力和实际SD回读SHA。完整命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cu -- \
 python3 build/rmm-client-bo-20261030/run-private-sequence-probe-with-uart.py \
 --images build/rmm-client-bo-20261030/private-sequence-probe-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

33场景完成，Mali-G610/Panfrost、计算预热、CPU SIGNAL/eventfd/basic、两VM退出0/0，两端kernel-log/pool-unbind、Host内核健康及CPU0–1/pmthor/loop/进程恢复检查通过；validation仍26成功/1既有数值例外/6无判据，不能称全部正确性PASS。CPU SIGNAL冒烟不是实际GPU完成eventfd验证。blur/terrain/5×5 effect2d为155/20/125FPS，场景保护未通过；唯一runner错误为低于1000分。

| 指标 | CT867 | CU866 |
| --- | ---: | ---: |
| COMPLETE worker调用/累计退休批 | 2.474 | 3.392 |
| 估计完整FINISH调用/累计退休批 | 2.474 | 1.116 |
| PREPARE操作µs/累计退休批 | 97.123 | 97.064 |
| READY操作µs/累计退休批 | 53.660 | 53.771 |
| COMPLETE操作µs/累计退休批 | 347.499 | 255.599 |
| COMPLETE间隔µs/累计退休批 | 272.670 | 370.579 |

CU累计轻量查询927269次，其中busy提示745166次、强制完整检查183105次。估计完整FINISH调用数用COMPLETE worker次数减busy提示计算，仅在无提示错误时成立，包含CPU归还续调用；ready提示与FINISH发生在同次worker，不能把全部worker次数都写成完整设备查询。统计为每文件累计，含预热/校验及RPC/RMM/设备等待，非纯CPU时间或计分窗口内逐任务因果证明；两轮任务数不同、CPU未锁恒频，单轮不证明稳定收益。

**结果解释：** 完整FINISH估计次数约下降54.91%，COMPLETE操作墙钟347.499→255.599µs/批（−26.45%），但worker调用2.474→3.392次/批（+37.09%），间隔272.670→370.579µs/批（+35.91%）；两者合计620.169→626.179µs/批，省掉的操作被更频繁的等待抵消。5×5 effect2d下降82.42%、terrain下降23.08%，不能由总分近似持平掩盖。这轮结果不支持将“尚未看到终止序号”普遍用作延后完整设备/heap进展检查的依据；缺少逐场景握手、heap和队列时序，尚不能确定具体退化来自哪一项，不把推测写成根因。

**最终状态：** `private-sequence-probe-evidence-20261031-cu`拉回11份日志并逐项SHA核验，分析记录`private-sequence-probe-{hardware,scene-comparison,phase-comparison}.json`；原始证据`build/lab-runs/private-heap-720-20261031-cu/realm-evidence/`，控制机总日志`private-sequence-probe-hardware.log`。`private-sequence-probe-runtime-20261031-cu`最终核验51项源码、四项板端运行输入与实际SD2，状态`PASS_CT867_RESTORED`；当前包`private-domain-policy-candidate/`、固件`firmware-private-domain-policy/`。撤回前先通过SD2恢复CT固件，随后恢复12项源码与板端Client Image；恢复后无新增GPU测量，867仍为CT原测分数。

1000分门槛FAIL；真实GPU完成eventfd、广泛API/ML/多Client及恶意并发/撤销/旧映射矩阵未新增验收，历史AE EBUSY和数值例外保留，RK模拟不证明物理CPU/DMA拒绝。此次新增一次完整720p测量；文档整理与最终运行输入核验没有新增性能测量。

## CV：无OOM先读ACK，866分撤回恢复CT（2026-10-31）

统一记录：减少RMM无OOM扫描中的未使用输出复制｜CT867→CV866｜-1分/-0.12%｜仅RMM固件变化，Client/Proxy/Host/initrd/runner相同，GPU实际594MHz、CPU未锁恒频，均为固件重启后单轮完整720p｜部署`private-heap-header-fw-20261031-cv`退出0；完整测试`private-heap-720-20261031-cv`退出1，证据与最终核验退出0｜保留线876、场景下限137/24/640FPS，撤回CV并核验恢复CT867，整体目标未完成。

**实现：** Client在每次FINISH仍pending后调用HEAP_EVENT；原`heap_output()`对每个stream失效216字节缓存、逐字节复制全部输出，再用request/ACK判断是否有OOM。CV保留完整缓存失效与原扫描范围，先用已验证对齐的32位读取加载ACK和request。无OOM直接返回，输出数组不被消费。检测到OOM后再次失效完整216字节，按32位复制完整快照、重新读request并复查OOM位，之后执行原任务队列归属、非零/对齐/控制区地址边界及计数顺序校验。事件消失不能使用第一次读取的旧ACK，事件字段变化采用第二次完整快照。所有调用者仅在返回true时消费完整输出，已经逐处核对。

Client代码、GPU完成/STATUS/heap服务频率、根及配置、停止/刷新/归还/退休均不改变。其他固件函数与CT逐字一致；无新RSI/ABI/能力位，仍ABI2/RPC4、能力34359738363，完整执行位清零。实际O2反汇编确认：无事件分支两个32位字段读取后跳过完整复制；不是只由模型读取次数推断。原快照复制的216字节减少为4字节ACK，另有共同的4字节request；完整缓存维护范围不减少。

**验证：** 53项源码冻结在`private-heap-header-source/`，较CT仅固件核心、私有套件入口及新helper测试/提取脚本4项改变。`check-gpu-heap-header.py`编译实际生产helper，77场景覆盖32队列、两种OOM极性、事件消失/请求更新、新快照地址、非法队列/地址/计数及无事件输出不可消费。完整私有套件614条PASS标记、533直接后端及68实际RSI阶段退出0，原OOM增长/撤销/错误矩阵继续执行。6个错误变体全部成功编译后断言拒绝：遗漏首次失效、遗漏实际事件的新鲜失效、漏复查事件位、队列归属、控制地址上界或计数顺序。日志`private-heap-header-{private,backend,mutants}.log`与对应JSON；模型不证明实体GPT/GPC拒绝。

保留两项开发失败：初始测试arena8192不足容纳最后队列输出，修正为12288后77项通过，生产代码未因此改变；首次去掉队列检查的变体因未使用参数未编译，加入显式(void)task后才计入最终6个成功编译后的拒绝。没有把编译失败当成安全检查通过。

RMM独立O2 Debug、23份flags和全部断言保持，预留末址0x2800000；固定U-Boot/BL31/DDR构建及ELF/BSS/FIT检查退出0。RMM ELF SHA `7ebf85d9842fa1aa8a4c685cb2ffc4f69033a5587757497325a237880b8aac53`。冻结包只改变rmm.elf/rmm.img；本轮不重建或上传Client/Proxy。汇总`private-heap-header-{candidate-validation,local-checks,build-validation}.json`、反汇编`private-heap-header-disassembly.log`。

**硬件：** 统一wrapper下仅刷SD2，备份实际启动区、保存UART并核验Host恢复/Realm能力/实际SD固件SHA。命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cv -- \
 python3 build/rmm-client-bo-20261030/run-private-heap-header-with-uart.py \
 --images build/rmm-client-bo-20261030/private-heap-header-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

33场景、计算预热、CPU SIGNAL/eventfd/basic、VM退出0/0、两端kernel-log/pool-unbind及Host健康/资源恢复检查通过。validation仍26/1/6，含既有数值例外；不能称全部正确性PASS。CPU SIGNAL探针不证明实际GPU完成eventfd。11份日志拉回并SHA核验；原始`build/lab-runs/private-heap-720-20261031-cv/realm-evidence/`，分析`private-heap-header-{hardware,scene-comparison,phase-comparison}.json`；唯一runner错误为低于1000分。blur/terrain/5×5 effect2d为153/26/722FPS，场景保护通过。

| 指标 | CT867 | CV866 |
| --- | ---: | ---: |
| COMPLETE worker/累计退休批 | 2.474 | 2.513 |
| PREPARE操作µs/累计退休批 | 97.123 | 97.260 |
| READY操作µs/累计退休批 | 53.660 | 53.680 |
| COMPLETE操作µs/累计退休批 | 347.499 | 344.387 |
| COMPLETE间隔µs/累计退休批 | 272.670 | 276.067 |

COMPLETE操作347.499→344.387µs/批约减少3.112µs，但间隔272.670→276.067µs/批约增加3.398µs，合计620.169→620.455µs/批基本持平；逐场景FPS变化中位数为0%。源码和反汇编确认少读发生，不等于可测的整体收益。本轮没有出现CU的terrain/5×5 effect2d大幅退化，但仍未达保留线。以上是每文件累计、含预热/校验、RPC/RMM/设备等待和不同任务数的墙钟统计，非纯CPU时间或稳定因果证明。真实OOM路径增加了一次完整invalidate且完整复制改为按字读取；只能将测得变化归于这组实现，不能将全部变化归于ACK少读。

**最终状态：** `private-heap-header-runtime-20261031-cv`核验最终源码、四项实际Guest输入及SD2固件，状态`PASS_CT867_RESTORED`，当前包`private-domain-policy-candidate/`与固件`firmware-private-domain-policy/`。先通过SD2恢复CT固件，再恢复修改源码并移除候选新增测试入口/文件；恢复后无新增GPU测量，867仍引用CT原测分数。

1000门槛FAIL；真实GPU完成eventfd、广泛API/ML/多Client及恶意并发销毁/撤销/旧映射未追加验收，历史AE EBUSY和数值例外保留，RK模拟不证明物理CPU/DMA拒绝，整体目标仍未完成。后续优先评估由RMM持有的有界上下文授权能否合并每批重复STAGE/PREPARE往返，而不是继续微调无事件复制；该新接线尚未实现，不计入本轮成果。此次新增一次完整720p测量；文档整理及最终核验没有新增性能测量。

## CW：同次FINISH执行真实堆事件查询，867分撤回恢复CT（2026-10-31）

统一记录：减少GPU未完成后的重复Client→RMM调用｜CT867→CW867｜+0分/+0.00%｜Client与RMM组合变化，Proxy/Host/initrd/runner相同；GPU实际594MHz、CPU未锁恒频，均为固件重启后单轮完整720p｜部署`private-finish-service-fw-20261031-cw`退出0；测试`private-heap-720-20261031-cw`退出1；证据拉回及最终运行态核验退出0｜保留线876、场景下限137/24/640FPS，撤回CW并核验恢复CT867，整体目标未完成。

**实现与边界。** 原路径每次FINISH返回GPU-pending后，由Client另发HEAP_EVENT，再决定等待或服务OOM。CW新增可选能力bit35与TASK_FINISH_SERVICE；RMM在同一个policy锁内先调用原`gpu_firmware_task_finish_domain()`，只有精确的INCOMPLETE/未完成/零页数/kind0才继续调用原`gpu_firmware_task_heap_event()`。所有既有固件函数逐字保持，完整heap_live、全stream真实输出扫描、根/配置/任务归属及生命周期检查不减。HEAP_EVENT成功且四个结果全零时，原pending结果只增加kind2；发现真实OOM时保留kind0，Client进入既有heap服务并重新核验事件；堆检查错误原样传播、引用保持。完成成功、失败及CPU归还kind1不会额外查堆。没有从FINISH推断“应该没有OOM”，也未合并或复用两消费者内部的新鲜硬件检查。

Client协商该能力后使用新操作，kind2只跳过紧接的一次重复HEAP_EVENT RSI；仍保持-EAGAIN、原截止时间、下一次完整FINISH，不能完成fence或退休。未协商时使用原路径。typed helper严格区分新/旧操作与pending种类，成功必须kind0/精确queue/零页数；通用private_call和raw ioctl不能操作内核托管的新token路径。Proxy逐任务session/channel/group/context及一次性启动授权保持，未以优化理由绕过Proxy。ABI2/RPC4保持、能力68719476731，完整执行能力位仍清零。

**验证。** 冻结53项源码，其中15项相对CT变化，包含两个新测试文件。实际生产wrapper提取编译后的420组组合验证调用顺序、精确pending条件、全零无事件和每个非零事件字段、错误传播及CPU归还不查堆。实际Client worker 114项与typed/raw bridge 164项覆盖fence依赖、后续OOM/增长continuation、错误、退出、超时和禁止伪完成。原私有套件614条PASS标记；原DMA/533直接后端及68实际RSI阶段通过，新增compound版本另执行533直接和68 RSI阶段，并在21个真实后端OOM案例中确认事件不被当作无事件或完成。

9个错误变体均成功编译后由断言拒绝：不执行真实HEAP_EVENT、把非零事件当无事件、吞堆错误、CPU归还误查堆、无事件伪完成、Client一概跳堆、kind2伪完成fence、旧FINISH接受kind2、raw ioctl绕过。开发时的两次失败保留在local-checks：历史差分插入上下文不唯一，扩大匹配上下文后从CT备份重做；首次私有套件与backend共用helper输出目录导致ETXTBSY，改用各自目录后通过，未归因为产品故障。以上为模型证据，不证明真实硬件拒绝或Linux并发无缺陷。

独立O2 Debug/23份flags和断言、Client ARM64 Image、固定U-Boot/BL31/DDR、ELF/BSS/FIT及上游补丁清单核验退出0；RMM预留末址0x2800000不扩展。RMM ELF SHA `d58375125d3e755a1ccac1281edbe4a8d1298b35442780c9dc03cc6453deb905`。冻结输入仅client-Image/rmm.elf/rmm.img变化；硬件只上传Client Image并通过统一wrapper仅刷SD2，保存实际启动区备份、UART、Host恢复与实际固件字节SHA。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cw -- \
 python3 build/rmm-client-bo-20261030/run-private-finish-service-with-uart.py \
 --images build/rmm-client-bo-20261030/private-finish-service-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景与计算预热、CPU SIGNAL/eventfd/basic、VM退出0/0、两端kernel-log/pool-unbind、Host健康及资源恢复通过；validation26/1/6保留已知数值例外，不能写全部正确性PASS。CPU SIGNAL探针不代表GPU完成eventfd。11份证据拉回并SHA核验；原始日志`build/lab-runs/private-heap-720-20261031-cw/realm-evidence/`，汇总`private-finish-service-{hardware,scene-comparison,phase-comparison,local-checks,candidate-validation}.json`。

| 指标 | CT867 | CW867 |
| --- | ---: | ---: |
| COMPLETE worker/累计退休批 | 2.474 | 2.485 |
| PREPARE操作µs/累计退休批 | 97.123 | 97.747 |
| READY操作µs/累计退休批 | 53.660 | 53.518 |
| COMPLETE操作µs/累计退休批 | 347.499 | 346.893 |
| COMPLETE间隔µs/累计退休批 | 272.670 | 273.211 |

COMPLETE操作与间隔之和为620.169→620.104µs/累计退休批。实际协商enabled=1，省去的重复HEAP_EVENT RSI为491510次，仍需独立堆服务1次。该计数证明路径使用，不证明稳定整体提分；实际堆扫描并未省去。操作耗时为含RMM/RPC/设备等待、预热/校验和不同任务数的累计墙钟，不能当纯CPU成本。Client和RMM同时改变，只归因组合效果。

**最终状态。** `private-finish-service-runtime-20261031-cw`退出0，`PASS_CT867_RESTORED`：51项最终源码、四项实际Guest输入与实际SD2固件核验；当前包`private-domain-policy-candidate/`、固件`firmware-private-domain-policy/`。候选已撤回：先恢复CT固件，再仅还原本轮改变的源码/Client Image并删除两个新增测试文件；候选源码、镜像、失败门槛及全部证据保留在忽略的build目录。

最终核验后无新增GPU测量，867仍引用CT原实测。1000门槛FAIL；AE EBUSY、真实GPU完成eventfd、广泛API/ML、多Client与恶意Client/Proxy实体攻击未追加验收，物理GPT/GPC拒绝仍未证明，整体目标未完成。文档同时修正开头遗留的CG728状态，使其与当前保留版本一致；这项文档整理无运行代码变化、无额外性能测量。

## CX：Client明确授权的单任务合并启动，881分保留（2026-10-31）

统一记录：消除Proxy接纳回复到Client READY之间的一次独立阶段交接，并允许GPU执行与RPC回程重叠｜CT867→CX881｜+14分/+1.61%｜Client、Proxy、RMM组合变化，Host/initrd/runner相同；GPU实际594MHz、CPU未锁恒频，最终cx2为重启后单轮完整720p｜最终测试`private-heap-720-20261031-cx2`退出1，部署、证据与最终运行态核验退出0｜预设保留线876与场景下限137/24/640FPS，保留CX实验候选，整体目标未完成。

**设计。** 旧路径是Client处理依赖并暂存任务，Proxy经RMM PREPARE_LAUNCH选定该token，RPC返回后Client再以独立work item进入RMM完成READY/PUBLISH/START。新路径仍逐任务通过Proxy：原Client在STAGE_BATCH时额外设置DELEGATE，此授权保存在RMM私有任务记录中，绑定真实Client及其context/group/token；Proxy不能自填Client身份、物理页、根、命令指针或就绪断言。Proxy接纳后请求TASK_DISPATCH，实际RSI从调用Realm和已认证通道解析Client，检查独立服务身份及精确任务归属。RMM在尝试准备前消耗授权，随后调用原PREPARE_LAUNCH及一个原READY_LAUNCH切片，保留所有根/映射/租约/缓存/发布/START检查。

若缓存交接未完成，DISPATCH只返回合法PREPARED `[4,queue,0,0]`，不启动、不循环，由原Client READY有界继续；全部完成才返回STARTED `[5,queue,0,0]`，Client省去独立READY阶段。启动成功、部分失败、回复丢失均不允许Proxy重发；容量不足仅在RMM证明尚未准备并取消原token后，允许Client以新token重新暂存。此方案无需Proxy缓存continuation协议，也不将Client数据映射给Proxy。Client提前解决依赖是授予启动权的前置条件，不是来自Proxy的保证。

Proxy回复只影响下一次Client工作阶段，任何回复都不能完成fence或释放backing；原FINISH继续检查真实GPU完成并执行刷新、CPU归还及退休。伪造STARTED至多导致Client后续可信调用失败并保持引用，不能成为成功执行证明。新能力bit35、STAGE flag2与RPC feature bit13可选协商，必须RMM和Proxy同时支持；旧peer继续使用旧路径。ABI2/RPC4保持、能力68719476731，完整执行能力位清零，RMM预留末址0x2800000不扩展。

**验证与开发失败。** 545直接后端和80实际RSI阶段各含12类新增场景，覆盖无授权、错误服务/Client/context/group/token、重复请求、真实513页缓存有界交接、提前准备、缓存/控制写失败和START ACK缺失；实际RSI也覆盖STAGE授权来源。两个Client的96轮执行域模型交替采用原READY和显式授权DISPATCH，检查相同量子/让出、单调ring和旧token拒绝。实际Client worker113项、typed/Proxy桥接151项、私有套件613条PASS标记，分别测试依赖、PREPARED continuation、丢失/畸形回复、错误、退出与fence引用保持。

6个成功编译后被断言拒绝的错误变体包括：无Client同意也接受、略去READY/START、缓存pending谎称STARTED、把错误改成接纳、Client跳过未完成READY、Proxy忽略返回状态。初轮部署后人工复查发现合并成功使`run->phase`提前变为READY，统计分支因此读取了RPC没有填写的局部`result`；修正为依据进入时的`profile_phase`读取统计。额外以123页陈旧元数据初始化统计scratch的实际worker模型通过，恢复错误判断的第7个编译变体被断言拒绝。该读数不参与授权/完成判断，但初轮CX883仅作诊断，不作为保留依据；原源码/镜像/日志均保留，修正后新建fixed冻结包，以cx2完整复测。

其余开发失败保留：新操作占用了旧测试的非法action=5，改用6；桥接新场景最初放在group teardown后，修正夹具生命周期；组合调用包含PREPARE控制写，MCU夹具改为观察真实START后才启用原顺序跟踪；实际RSI的固定read adapter转到相同的多队列模型；编译缩进警告修正；冻结助手首次误将已有相对仓库路径再拼一次build前缀，修正后核验。以上均保存失败日志，不将夹具失败归因为GPU故障。源码模型不是Linux并发或实体GPC保护证明。

独立O2 Debug/23份flags和断言、两端ARM64 Image、固定U-Boot/BL31/DDR、ELF/BSS/FIT、补丁清单及冻结51项源码核验通过。RMM ELF SHA `fc105d7657acb81edff286e89b8f48689874dff962967c9818548114dea2f7eb`。相对CT仅client-Image/proxy-Image/rmm.elf/rmm.img变化。首次上传两端Image；修正后RMM/Proxy相同，仅上传Client，最终测试前再次仅向SD2部署同一固件以恢复重启条件，保存启动区备份、UART与实际SD固件SHA核验。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cx2 -- \
 python3 build/rmm-client-bo-20261030/run-private-delegated-dispatch-fixed-with-uart.py \
 --images build/rmm-client-bo-20261030/private-delegated-dispatch-fixed-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

完整33场景/计算预热、CPU SIGNAL/eventfd/basic、VM退出0/0、两端kernel-log/pool-unbind、Host健康、资源恢复及11份证据SHA核验；validation26/1/6含既有数值例外，不能写全部正确性PASS。CPU SIGNAL探针不代表真实GPU完成eventfd。原始证据`build/lab-runs/private-heap-720-20261031-cx2/realm-evidence/`，分析`private-delegated-dispatch-fixed-{hardware,scene-comparison,phase-comparison}.json`。

| 指标 | CT867 | CX881 |
| --- | ---: | ---: |
| PREPARE操作µs/累计退休批 | 97.123 | 145.389 |
| 独立READY操作µs/累计退休批 | 53.660 | 0.038 |
| COMPLETE操作µs/累计退休批 | 347.499 | 346.934 |
| COMPLETE间隔µs/累计退休批 | 272.670 | 264.187 |

Client独立READY调用显著少于退休批数，结合冻结源码中仅协商成功才可省去READY的分支，确认合并路径实际使用；会话打开时的enabled日志可能被环形缓冲覆盖。新路径的合并READY工作计入PREPARE，独立READY只包含未完成缓存交接的后续切片，因此不能单独以READY时间下降宣称省去同等工作。上述数值为混合预热/校验与不同任务数的累计墙钟，包含RPC/RMM/设备等待；单轮未锁CPU频率不证明稳定因果收益，三组件同时改变只归因组合效果。

最终`private-delegated-dispatch-runtime-20261031-cx2`退出0，状态`PASS_CX_RETAINED`：51项当前源码、四项板端输入和实际SD2固件核验。当前包`build/rmm-client-bo-20261030/private-delegated-dispatch-fixed-candidate`，固件`firmware-private-delegated-dispatch`，保留CX并留存CT867回退。最终核验后无新增GPU测量，当前保留成绩仍取对应实测。1000门槛FAIL，AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client与恶意Client/Proxy实体攻击未在本轮追加验收；物理CPU/DMA拒绝未证明，整体目标未完成。

## CY：按STATUS应答边界扫描stream，877分撤回恢复CX（2026-10-31）

统一记录：减少等待同一STATUS应答时的重复全stream读取与缓存失效｜CX881→CY877｜-4分/-0.45%｜仅RMM运行输入变化，两端Guest/Host/initrd/runner相同，GPU实际594MHz、CPU未锁恒频，两轮均重启后单Client完整720p｜部署`private-status-poll-fw-20261031-cy`退出0；测试`private-heap-720-20261031-cy`退出1；证据与最终运行态核验退出0｜保留线890，场景下限139/25/643FPS，撤回CY并核验恢复CX881，1000门槛FAIL。

**设计及安全边界。** 原完成观察在每次等待父门铃与CSG的STATUS_UPDATE ACK时扫描全部stream。CY只把该完整扫描移到两个ACK到齐之后、清除status_pending和读取控制页之前。仍对全部stream（包含非活跃stream）执行原216字节失效和错误字段检查；之后保留所有实际队列、终止序号、根/配置、真实AS刷新、CPU归还和退休检查。没有缓存历史状态或更改完成标准。缺少父/CSG应答仍在原100ms上限失败，保留引用；若stream错误伴随应答卡住，错误检测可能推迟到超时，日志不保证保留原stream诊断。这不是中断保护或设备容错的新保证。

**本地验证。** 冻结52项源码，相对CX仅固件核心、DMA测试入口和新增`check-gpu-status-poll.py`改变；两端Guest不重建。实际545阶段后端矩阵加入延迟ACK适配器，96次请求在第四次group输出失效时才返回ACK；断言pending期间不扫描stream、不读队列，ACK后全部stream必须在第一次队列读取前接受检查。原缺失ACK、非活跃stream故障、读后根/配置变化、停止/刷新失败及引用保留用例继续执行。四个变体均编译成功再由断言拒绝：删除完整stream检查、忽略父ACK、忽略STATUS ACK、恢复每次轮询扫描。80阶段实际RSI模型、私有套件、上游补丁清单通过。模型采用REC/RTT/物理页与设备替身，不证明真实并发或硬件拒绝。

保留两项开发失败：首次删除扫描的变体因后续START检查仍能拒绝已有错误而存活，补上“首次队列读取前必须检查全部stream”的顺序断言后重新执行四个变体；第一次增强适配器因缩进警告未编译，补花括号后成功。均为测试夹具问题，未为通过测试放宽生产检查。证据`status-poll-cy/`、`status-poll-cy-final/`和最终`status-poll-cy-verified/result.json`；编译失败不计为拒绝成功。

独立RMM O2 Debug、23份flags与原候选一致，全部断言及0x2800000预留末址保持；固定U-Boot/BL31/DDR、ELF/BSS/FIT通过。RMM ELF SHA `953e211b707b13f16f321a9c390124cc7dc2547bb6ed006fd9dcf63a8b2ad2c9`。SD2部署备份实际启动区并保存UART/Host恢复；测试前按实际SD字节核验，Guest四项输入SHA均沿用CX。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cy -- \
 python3 build/rmm-client-bo-20261030/run-private-status-poll-with-uart.py \
 --images build/rmm-client-bo-20261030/private-status-poll-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景与计算预热、CPU SIGNAL/eventfd/basic、VM退出0/0、两端kernel-log/pool-unbind、Host健康、CPU0–1/pmthor/loop/进程恢复及11份证据SHA核验通过。validation26成功/1既有数值例外/6无判据；CPU SIGNAL探针不代表真实GPU完成eventfd。blur154→153、terrain27→27、5×5 effect2d714→718FPS，场景保护通过。唯一runner错误为低于1000分。原始证据`build/lab-runs/private-heap-720-20261031-cy/realm-evidence/`，命令/退出码在该目录父层`result.json`；控制机总日志`private-status-poll-hardware.log`。

| 指标 | CX881 | CY877 |
| --- | ---: | ---: |
| PREPARE操作µs/累计退休批 | 145.389 | 145.741 |
| 独立READY操作µs/累计退休批 | 0.038 | 0.033 |
| COMPLETE操作µs/累计退休批 | 346.934 | 346.429 |
| COMPLETE间隔µs/累计退休批 | 264.187 | 267.085 |

COMPLETE操作346.934→346.429µs/批，约减少0.505µs；其间隔264.187→267.085µs/批，约增加2.898µs，合计611.121→613.514µs/批。当前证据不支持将该等待循环内的重复stream扫描视为主要可消除开销；单轮小幅变化也不证明稳定退化。

累计墙钟包含预热/验证、RPC/RMM/设备等待，退休任务数不同且CPU未锁恒频；不能用该表证明纯CPU成本或稳定因果收益。没有硬件内层轮询次数计数，模型四次ACK轮询不等于实机每次都省去四次扫描。

**最终状态。** `private-status-poll-runtime-20261031-cy`退出0，`PASS_CX881_RESTORED`，核验51项当前源码、四项板端输入与实际SD2固件。当前包`build/rmm-client-bo-20261030/private-delegated-dispatch-fixed-candidate`与`firmware-private-delegated-dispatch`；已通过SD2恢复CX固件，并恢复两项原源码、移除本轮测试入口与新增脚本；CY源码/镜像/证据保留于build。最终核验后无新增GPU测量，保留分数881引用对应原实测。

1000门槛仍FAIL；既有数值例外、AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client、恶意Client/Proxy、并发撤销及旧映射负例未在本轮追加验收。RK平台不证明物理GPT/GPC拒绝，系统设计仍按目标平台保护假设评估；这些正常单Client结果不能替代越权负例验证。整体目标保持未完成。

## CZ：覆盖当前执行域的RMM计时，诊断881分并恢复CX（2026-10-31）

统一记录：定位CX完成路径主要成本｜CX881→CZ诊断881｜0分/0%｜只改RMM计时；两端Guest、Host、initrd、runner相同，GPU实际594MHz、CPU未锁恒频，两轮均重启后单Client完整720p｜部署`private-domain-cost-fw-20261031-cz`退出0；测试`private-heap-720-20261031-cz`退出1，原因低于1000分；证据、分析和最终恢复核验退出0｜诊断不保留，当前仍为CX881；不从单轮同分推断计时无扰动。

**为何重新测量。** 旧CK计时早于当前执行域保留、live drain与Proxy授权合并启动。现有正常RSI FINISH走`gpu_firmware_task_finish_domain()`，旧工具仅观察公开`gpu_firmware_task_finish()`会漏掉主要路径。本轮沿用原定时器超时和全部生产语句，加入独立计时时钟，覆盖DISPATCH、PREPARE/READY、START及只读重放、STATUS观察、停止、实际live刷新、drain、fallback和执行域FINISH，并按成功/等待/错误拆分后者。计时只读取可信计数器和写本地统计，不向调用者新增权限或完成证明。原有无回调提交边界在诊断中增加的也是计数器读取；诊断结果不作为生产配置。

**本地验证及失败保留。** 对11个实际函数去掉计时行后比较原始语句，除缩进外完全相同。545阶段实际后端模型和80阶段实际RSI模型、完整私有路径套件、补丁清单通过。独立17-tick时钟覆盖无符号回绕，与原超时时钟分离；新增GPU尚未完成的设备替身场景，验证成功/等待/错误的calls与ticks精确相加等于FINISH总计。5个成功编译后被断言拒绝的变体包括CPU缓存漏计、START等待漏计、STATUS等待漏计、live刷新漏计和完成分区计时错误。严格解析器20类检查拒绝丢行、重复、串行号错误、回退和分区不守恒；不会跨帧拼凑。

初始测试要求每项计数非零，实际原模型没有FINISH域INCOMPLETE覆盖，因而失败；新增pending适配器首次匹配了较早的同名赋值，新增断言失败，改为只作用于`model_domain_ack`后通过。原函数文本检查最初遇到计时插入造成的缩进变化，最终比较保留全部原语句的空白分隔词。失败日志保留于`domain-cost-model/`、`domain-cost-model-verified/`、`domain-cost-model-final/`，最终通过证据为`domain-cost-model-checked/`。这些是夹具开发失败，未放宽生产成功条件。

独立O2 Debug构建保持23份编译flags、断言和0x2800000预留末址；固定U-Boot/BL31/DDR、ELF/BSS/FIT检查通过。诊断RMM ELF SHA `756c2dd5b17d8919339a3b53fe89d57757bb03bb2d873cdb3708447e0694245a`。冻结包相对CX仅rmm.elf/rmm.img变化。先核验实际SD2固件字节，再运行完整720p，没有替换Guest、Host或rootfs。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-cz -- \
 python3 build/rmm-client-bo-20261030/run-private-domain-cost-with-uart.py \
 --images build/rmm-client-bo-20261030/private-domain-cost-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**硬件结果。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康、CPU0–1/pmthor/loop/进程恢复及11份证据SHA核验通过；validation26成功/1既有数值例外/6无判据。CPU SIGNAL探针不是GPU完成eventfd证明。blur154→153、terrain27→27、5×5 effect2d714→711FPS；各场景下限检查通过。score881与旧CX相同，但1000门槛仍失败，外层退出1，未以工作负载marker改写失败状态。

**可信采样覆盖。** 每次成功GROUP_DESTROY之后发送三份独立完整帧，各行间隔5ms，输出不在被计时操作内。共207份完整帧，0拒绝、0孤立记录；最终序号207累计退休336530批，覆盖Client文件336198批。多出的332批来自累计范围中的其他已结束工作；不要把RMM全局与Client文件的分母当作完全相同。报告含初始化、预热、校验及对应组的工作，测量墙钟包含硬件握手、缓存与MMIO，不是纯CPU时间或GPU执行时间。代码布置、额外时钟读取和组销毁报告也可能扰动性能。

| 当前路径 | µs/累计退休批 | 说明 |
| --- | ---: | --- |
| DISPATCH | 95.043 | 包含PREPARE和一次有界READY/START |
| FINISH域总计 | 172.926 | 819422次，约2.435次/批 |
| 其中成功 | 89.820 | 336530次，89.820µs/次 |
| 其中仍在等待 | 83.106 | 482892次，57.917µs/次，占FINISH域48.06% |
| 其中错误 | 0 | 本轮正常工作负载未进入；不是攻击拒绝证明 |
| live drain | 156.911 | 与FINISH域、STATUS和START重放嵌套 |
| 真实live刷新 | 18.934 | 与drain嵌套，单次19.540µs |
| STATUS观察 | 115.694 | 含其等待和重放，跨live与fallback调用 |
| 其中STATUS等待 | 48.883 | 单次20.285µs，包含实际轮询/缓存读取 |
| START及只读重放 | 119.024 | 约15.026次/批，混合多条调用路径 |
| 其中实际START握手等待 | 2.249 | 冷启动/恢复已被执行域摊薄 |
| 停止握手等待 | 3.023 | 已被执行域量子摊薄 |
| 数据交给设备的缓存路径 | 3.773 | 包含检查、回调和屏障 |
| CPU归还缓存路径 | 0.184 | NC/驻留路径下调用较少 |

只有FINISH域成功/等待/错误三行是互斥分区，可相加；其余父子行互相嵌套，不能汇总成总耗时。START平均15次/批也包含重放检查，不能写成每批重新启动GPU15次；全局数据尚未区分每个调用者的占比。Client累计COMPLETE操作346.934→347.579µs/批、间隔264.187→263.344µs/批；Client与RMM范围及分母略有差异，不通过相减声称得到纯跨域切换成本。

**下一步优先级。** FINISH域等待分支占48.06%表明该区域值得深入归因，却不能证明这些工作可以省略。历史CU已有关键反证：终止序号轻量查询降低完整FINISH次数，却令worker次数和间隔增加，terrain及5×5 effect2d明显退化。不能把本轮数据当作再次部署同类轻量轮询的充分依据。下一步应保持当前STATUS/heap推进及Client等待策略，先区分pending中真正推动设备和发现异常的工作，以及同一调用内重复的身份/根/状态验证。

仅在后续证明不会妨碍推进之后，才考虑内部轻量否定检查：受保护队列/终止提示若还不满足，只允许返回INCOMPLETE；任何成功仍须经过新鲜STATUS、全队列/终止值/错误、真实根/配置、物理刷新、刷新后复查及精确退休。陈旧提示只能推迟处理，不能产生成功、越权发布或释放引用；需保留超时/异常处理的可见性和上界。该候选尚未实现，不预测分数。

更适合先分析的候选是在已经证明没有物理回调、共享输入变化或解锁的内部区域复用当次根/状态检查，减少只读START重放；不能跨真实刷新/缓存回调复用旧证明。需要补充每个调用者的归因，不能仅凭15次全局计数删除检查。继续微调缓存扫描或只增大独占量子的收益空间较低：前者只占数微秒，后者目前停止等待仅约3µs/批，还要保留竞争Client的让出机制。两项候选均未实现，安全与性能收益仍待验证。

**最终状态。** 已通过SD2恢复CX固件，临时计时源码单独归档后恢复；`private-domain-cost-runtime-20261031-cz`退出0，`PASS_CX881_RESTORED`，核验51项源码、四项板端运行输入和实际SD字节。当前包`build/rmm-client-bo-20261030/private-delegated-dispatch-fixed-candidate/`、固件`firmware-private-delegated-dispatch/`。恢复之后没有新增GPU测量；保留分数881引用CX原实测。CZ仅为诊断，不作为新增性能优化。

证据入口：`build/lab-runs/private-heap-720-20261031-cz/`（命令/退出/前后资源/串口/健康），其`realm-evidence/`为11份SHA核验的原始日志；`private-domain-cost-{hardware,cost,phase-comparison,scene-comparison,local-checks,followup,final-runtime}.json`记录分析与最终状态。实际恢复与核验分别为`private-domain-cost-restore-20261031-cz`和`private-domain-cost-runtime-20261031-cz`。

1000门槛仍FAIL；AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client、恶意Client/Proxy、并发撤销及旧映射负例未在本轮追加验收。RK不证明物理GPT/GPC拒绝，设计继续依赖目标平台保护假设；本轮无错误分支不替代攻击验证。整体目标未完成。

## DA：合并同次运行AS和固件检查，893分保留（2026-10-31）

统一记录：减少只读START重查的重复MMIO验证｜CX881→DA893｜+12分/+1.36%｜仅RMM运行输入变化，两端Guest、Host、initrd、runner保持CX，GPU实际594MHz、CPU未锁恒频，两轮均重启后单Client完整720p｜部署`private-running-check-fw-20261031-da`退出0；测试`private-heap-720-20261031-da`退出1；证据与最终运行态核验退出0｜保留线890，场景下限139/25/643FPS，保留DA实验候选，1000门槛FAIL。单轮不证明稳定因果收益。

**依据及区别。** CZ计时发现每累计退休批约15.026次START/只读重放，包含119.024µs。原先每次先调firmware configuration，再调既有Client AS prepare；两个平台入口分别检查MCU固定根、属性和运行状态。本轮只在START及其launch_checked复查中使用合并入口，与BT只去掉一次OBSERVE配置调用、CS合并DRAIN控制快照、CY改变STATUS循环扫描位置不同。没有重做CU的轻量轮询，也没有据pending占比减少设备推进。

**实现及边界。** 可信元数据层先核验service/owner/context、任务引用、无pending修改、activated/live_prepared状态及精确AS slot归属，真实页表根由RMM内部对象给出。平台层在mapping锁内执行一次完整固件配置检查，加上真实Client根和全部属性；Client AS读取后重新检查可信频率、MCU control/status和MMU/GPU故障。静态配置写入受原有策略/mapping锁与目标平台权限保护。没有跨调用证明缓存，没有新Guest RSI权限或可选成功标准，不编程AS、不写队列、不发布任务、不响门铃。失败隔离context并保留任务及物理页引用。未提供合并回调的可信模型适配器继续执行原有分离检查，实际RSI适配器使用新入口。

**验证。** 实际平台模型正常一次MMIO读取42→31（减少11次/26.19%），忙/闲GPU均有效，配置输出逐字段相同。30个静态/参数拒绝，5个在Client AS读取后发生的MCU/故障/频率变化均被拒绝；没有寄存器写入、AS命令或门铃增加。真实核心545阶段和实际RSI 80阶段在启用合并回调后通过，分别调用新后端8043/3378次；另检查8类身份/接口输入、10类context状态和硬件失败后的隔离/引用保留。删除动态MCU、故障、频率或service身份检查的四个变体均成功编译后被断言拒绝。模型采用REC/RTT和设备替身，不证明真实并发或物理拒绝。

首次RSI夹具缺少runtime/tests头文件搜索路径，编译失败；补充路径并使用独立rsi-test二进制名后通过，失败保留于`running-check-model/`，后续成功于`running-check-model-fixed/`，加强元数据测试后的最终证据为`running-check-model-final/`。编译失败不计为安全拒绝。完整私有BO套件、固定上游补丁清单通过；RMM O2 Debug、23份flags一致，保留全部断言和0x2800000预留末址，ELF/BSS/FIT检查通过。RMM ELF SHA `adc768a3745c66fcb9306782e361653eb1db005ea38e1341c57aa6f261b1cad4`，相对CX冻结包仅rmm.elf/rmm.img变化。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-da -- \
 python3 build/rmm-client-bo-20261030/run-private-running-check-with-uart.py \
 --images build/rmm-client-bo-20261030/private-running-check-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康、CPU0–1/pmthor/loop/进程恢复及11份原始日志SHA核验通过；validation26成功/1既有数值例外/6无判据，CPU SIGNAL探针不是GPU完成eventfd证明。blur154→156、terrain27→27、5×5 effect2d714→731FPS，场景下限通过。1000门槛FAIL，保留线通过。

| 指标 | CX881 | DA893 |
| --- | ---: | ---: |
| PREPARE操作µs/累计退休批 | 145.389 | 138.808 |
| 独立READY操作µs/累计退休批 | 0.038 | 0.037 |
| COMPLETE操作µs/累计退休批 | 346.934 | 338.073 |
| COMPLETE间隔µs/累计退休批 | 264.187 | 267.623 |

上述是Client累计阶段墙钟，包含初始化/预热/校验、RPC/RMM和设备等待，退休批数不同且CPU未锁恒频；不能当作纯CPU成本或直接归因于11次读取。CZ的15次重查是另一轮全局统计，DA没有新增硬件内层计数，不能直接相乘声称本轮节省的总时间。

**最终状态。** `private-running-check-runtime-20261031-da`退出0，`PASS_DA893_RETAINED`，核验53项源码、四项板端输入和实际SD2固件字节。当前包`build/rmm-client-bo-20261030/private-running-check-candidate`与`firmware-private-running-check`；保留DA源码和固件，CX881继续作为回退。最终核验后没有新增GPU测量；当前保留分数893引用相应实测。

证据入口：`build/lab-runs/private-heap-720-20261031-da/`保存命令/退出/前后资源、串口和健康检查，其`realm-evidence/`保存11份SHA核验日志。`private-running-check-{hardware,local-checks,phase-comparison,scene-comparison,final-runtime,checkpoint}.json`保存决策与最终状态，`running-check-model-final/`保存实际核心、RSI和变体编译/运行日志。

整体目标仍未完成；AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client、恶意Client/Proxy、并发撤销与旧映射负例未在本轮追加验收。RK不证明物理GPT/GPC拒绝，设计按目标平台权限保护假设评估；单Client正常运行不能替代隔离负例。1000门槛仍FAIL，继续遵循先完整720p再扩展硬件矩阵的顺序。

## DB：同次RSI控制页临时映射复用，898分撤回恢复DA（2026-10-31）

统一记录：减少同次可信调用中对相同内部控制页反复建立/解除CPU临时映射｜DA893→DB898｜+5分/+0.56%｜仅RMM运行输入变化，Client/Proxy/Host/initrd/runner相同，GPU实际594MHz、CPU未锁恒频；组合包含临时映射复用和High VA槽位扩容，两轮均重启后单Client完整720p｜部署`private-read-mapping-fw-20261031-db`退出0；测试`private-heap-720-20261031-db`退出1；证据及最终运行态核验退出0｜保留线902、场景下限141/25/658FPS，撤回DB并核验恢复DA893，1000门槛FAIL。单轮不证明稳定因果收益。

**机制与作用域。** 同一个FINISH/排空流程会多次读取相同queue input/output和completion页。原RSI适配器每次为16字节等少量数据执行find_lock、map、整页失效/DSB、copy、unmap、unlock。本轮只在handle_rsi_opencca_gpu_private持有全局policy锁的这一次调用内，为至多8页保留独立CPU本地临时映射；命中仍先经真实控制对象记录解析，再取得并检查DATA锁，随后完整失效4096字节、DSB及新复制。超出8页使用原SLOT_RSI_CALL逐次map/unmap，没有替换/逐出策略。锁作用域结束前解除所有缓存别名并清零记录，之后才policy unlock和返回Realm。非RSI清理调用不启用scope，沿用原瞬时路径。

这不是缓存控制页快照，更不是缓存Client授权；真正的GPU页表、对象归属、真实设备状态、STATUS/heap推进、完成判定、数据所有权和引用管理不变。read_page唯一生产调用者仍为read_control；它从CPU隐藏且已由固件绑定的控制arena获取PA，arena的mapped引用和policy gate固定backing生命周期。未改变DATA粒度原生refcount必须为0的规则。缓存只为RMM建别名，不增加Proxy/Client CPU映射，不读取Client业务数据页。与BG只缩小失效范围不同，本轮保留每次整页维护。

**配套槽位。** 在原槽位末尾追加8个GPU读槽，保持所有既有枚举值；High VA槽位预算42→50，仍与每CPU栈共用原有单张L3表，页数/间隙和容量断言保留。slot虚拟区及栈虚拟地址随预算调整，物理栈大小和RMM预留末址不变。此项配套变化包含在整轮组合观测中，不能只把分数差归因于map次数。原有RMM进出时check_cpu_slots_empty断言继续覆盖新增槽位。

**验证及失败记录。** 实际RSI读函数/作用域代码提取到独立非一致性内存模型：9次读取仅map3次，每次保留DATA检查、完整失效和完成屏障；超过8页回退、读取后设备改值、状态失效命中、空指针/大小/越界/错误PA、调用结束清空、CPU分离、非scope回退以及1024次确定种子随机读取通过。删除失效、删除屏障、错误页命中或遗漏解除映射的4个变体均成功编译后被断言拒绝。实际生产RSI分派80阶段加入begin/end位于policy锁内并配对的断言；完整545阶段后端、DA运行检查4个变体、完整私有BO及既有穷举缓存范围/数据所有权套件通过。合计8个成功编译后拒绝的变体，模型不证明物理GPC或真实Linux并发。

两次开发失败均发生在部署前：旧缓存夹具只提取read_page而缺少scope定义，补入实际定义并保留原穷举fallback检查；初始ARM64编译因新增槽超出42项预算而被容量断言拒绝，扩容至50后重建。没有移除或放宽断言，未计为预期攻击拒绝。日志`private-read-mapping-private.log`、`private-read-mapping-build.log`、`rmm-private-read-mapping.log`保留；最终通过为`private-read-mapping-private-final.log`、`private-read-mapping-build-retry.log`。源码冻结56项，相对DA六项修改及一个新增测试脚本。

O2 Debug、23份编译flags与原保留配置一致，断言保留；RMM ELF/BSS预留末址0x2800000、FIT及固定U-Boot/BL31/DDR检查通过。RMM ELF SHA `c2d557bfb68ea9a0eae4d6362ab0169f2a8aeb34c88463c66eb376a50aebef95`；冻结运行包相对DA仅rmm.elf/rmm.img改变。实际SD2字节在测试前读回匹配。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261031-db -- \
 python3 build/rmm-client-bo-20261030/run-private-read-mapping-with-uart.py \
 --images build/rmm-client-bo-20261030/private-read-mapping-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康、CPU0–1/pmthor/loop/进程恢复及11份日志SHA核验通过。validation26成功/1既有数值例外/6无判据；CPU SIGNAL不是实际GPU完成eventfd证据。blur156→157、terrain27→27、5×5 effect2d731→729FPS，场景下限通过。

| 指标 | DA893 | DB898 |
| --- | ---: | ---: |
| PREPARE操作µs/累计退休批 | 138.808 | 137.479 |
| 独立READY操作µs/累计退休批 | 0.037 | 0.028 |
| COMPLETE操作µs/累计退休批 | 338.073 | 335.715 |
| COMPLETE间隔µs/累计退休批 | 267.623 | 267.613 |

累计墙钟包含初始化/预热/校验、RPC/RMM/设备等待及调度，两个运行的退休批数不同。没有新增硬件内部map命中/耗时计数，模型map次数下降不能直接证明本轮省时，也不能将Client阶段差当作纯映射成本。

**最终状态。** `private-read-mapping-runtime-20261031-db`退出0，`PASS_DA893_RESTORED`，核验55项源码、四项板端输入和实际SD2固件字节。当前包`build/rmm-client-bo-20261030/private-running-check-candidate`与`firmware-private-running-check`；归档DB六项修改和新脚本后完整恢复DA源码、原槽位预算和SD2固件，新测试入口已移出源码。最终核验后无新增GPU测量，保留分数893引用相应已测版本。收尾文档和哈希核验未新增性能测量。

证据：`build/lab-runs/private-heap-720-20261031-db/`及其`realm-evidence/`，`private-read-mapping-{local-checks,hardware,phase-comparison,scene-comparison,final-runtime,checkpoint}.json`；`read-mapping-model/`为实际读代码/4个变体，`read-mapping-backend/`为后端、实际RSI和DA运行检查4个变体，均保存编译/退出/原日志。

整体目标仍未完成；1000门槛FAIL，真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射负例本轮未追加验收。RK不证明物理GPT/GPC拒绝，设计继续按目标平台保护假设评估；单Client正常结果不能替代隔离负例。

## DC：相同源码以LTO跨文件优化，889分撤回恢复DA（2026-11-01）

统一记录：通过跨文件常量传播、内联和死代码消除减少RMM调用开销｜DA893→DC889｜-4分/-0.45%｜55项冻结源码相同，仅RMM构建方式变化；相同Client/Proxy/Host/initrd/runner、GPU实际594MHz、CPU未锁恒频，两轮均重启后单Client完整720p｜部署`private-lto-fw-20261101-dc`退出0，测试`private-heap-720-20261101-dc`退出1，证据及最终核验退出0｜预设保留线902、场景下限141/25/658FPS，撤回DC并核验恢复DA893，1000门槛FAIL。单轮不证明稳定因果收益。

**机制与边界。** RMM的私有对象检查、固件控制与平台MMIO实现分散在不同编译单元。原O2以单文件为边界；本轮只开启CMake `CMAKE_INTERPROCEDURAL_OPTIMIZATION=ON`，使编译器在最终链接时跨文件优化。保持Debug、`-O2 -fno-omit-frame-pointer -g`、全部断言、原ABI、保护检查及启动/完成/撤销语义，不修改Client等待或GPU推进策略。相对DA，冻结包只有rmm.elf/rmm.img变化；源码55项哈希全部一致。编译器仍为固定aarch64 GCC15.2.0，23份flags剔除IPO的`-flto=auto -fno-fat-lto-objects`后与DA一致。

**构建失败及修正。** 首次LTO链接失败：优化后的代码生成memcpy调用，但freestanding实现已经被删除，出现undefined reference。失败构建保留在`rmm-build-lto/`与`private-lto-build.log`。独立目录`rmm-build-lto-fixed/`重建，链接器显式保留`memcpy/memmove/memset/memcmp`（`-Wl,-u,memcpy,-u,memmove,-u,memset,-u,memcmp`）；未改生产源码或移除断言。准确命令见`private-lto-fixed-build-commands.json`和`build-private-lto-retry.py`。这是部署前开发失败，不算攻击拒绝。

**本地检查。** LTO下完整私有BO套件613条PASS标记；实际平台/核心后端545阶段及实际RSI80阶段通过，4个错误变体均成功编译后被断言拒绝。固定补丁清单通过。本地命令、退出码及日志SHA见`private-lto-local-checks.json`；这些模型不替代真实Linux并发、恶意Proxy/Client或硬件GPC验收。

固件ELF/BSS布局与FIT逐字节检查通过，实际RMM末址0x27ff000低于原0x2800000预留，未扩容；沿用固定U-Boot/BL31/DDR来源和U-Boot配置。U-Boot/SPL重新构建，二进制因时间戳、调试路径等存在差异；U-Boot实际装载二进制等长且仅10个时间戳字节不同，不称固件整体逐字节相同；比较记录见`private-lto-boot-artifact-comparison.json`。RMM ELF SHA `f14d4856992e02511ed1dff3ee1edac7d8c0f96fd99203363b4720d55a17b06d`。text283328→258056字节（−8.92%）；代码体积不等于性能收益。为检查LTO后的栈帧，独立重链接加`-fstack-usage -save-temps`，raw镜像与候选逐字节一致；414个函数均为静态帧，最大8704字节、GPU路径最大1904字节，每CPU栈20480字节。这仅为单帧审计，不是完整调用链或并发栈证明。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-dc -- \
 python3 build/rmm-client-bo-20261030/run-private-lto-with-uart.py \
 --images build/rmm-client-bo-20261030/private-lto-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康、CPU0–1/pmthor/loop/进程恢复及11份日志SHA核验通过。validation26成功/1既有数值例外/6无判据；CPU SIGNAL不是实际GPU完成eventfd证据。blur156→153、terrain27→27、5×5 effect2d731→712FPS，场景下限通过。

| 指标 | DA893 | DC889 |
| --- | ---: | ---: |
| PREPARE操作µs/累计退休批 | 138.808 | 143.329 |
| 独立READY操作µs/累计退休批 | 0.037 | 0.032 |
| COMPLETE操作µs/累计退休批 | 338.073 | 346.978 |
| COMPLETE间隔µs/累计退休批 | 267.623 | 259.058 |

累计墙钟包含预热/校验、RPC/RMM/设备等待及调度，两轮退休批数不同。阶段耗时不能直接当作纯CPU成本；本轮未量化具体内联点的独立贡献。综合分数及场景变化只归因于LTO构建组合，仍需后续可比重复实验验证稳定性。

**最终状态。** `private-lto-runtime-20261101-dc`退出0，`PASS_DA893_RESTORED`，核验55项源码、四项板端输入和实际SD2固件字节。当前包`build/rmm-client-bo-20261030/private-running-check-candidate`与`firmware-private-running-check`；生产源码始终为DA，SD2固件已恢复DA，LTO构建仅留作实验归档。最终核验后无新增GPU测量，保留分数893引用对应已测版本；收尾文档未改运行代码，无新增性能测量。

证据：`build/lab-runs/private-heap-720-20261101-dc/realm-evidence/`及wrapper记录；`build/firmware-runs/private-lto-fw-20261101-dc/`；`private-lto-{plan,local-checks,build-validation,stack,layout,fit,candidate-validation,hardware,phase-comparison,scene-comparison,final-runtime,checkpoint}.json`。首次失败、重建命令和所有测试日志均保留于同一实验根目录。

整体目标未完成；真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射实机负例仍待验收。RK不证明物理GPT/GPC拒绝，设计按目标平台保护假设评估；正常单Client结果不能替代隔离负例。

## DD：实际RSI跨Client越权与拒绝后状态不变验证（2026-11-01）

统一记录：加强Client私有数据/RMM权限边界验证｜当前运行候选DA893，未新增对照测量｜分差及百分比不适用｜未改运行代码，无新增性能测量；仅新增本地模型测试并接入私有套件｜完整套件及补丁清单退出0，只读核验`private-rsi-boundary-runtime-20261101-dd`退出0｜保留测试，运行版本仍为DA，1000门槛仍FAIL，整体目标未完成。

**测试对象。** 新增`opencca_gpu_rsi_boundary_test.h`与`check-gpu-rsi-boundary.py`，由`check-rmm-gpu-private.sh`调用。执行实际RSI分派、私有BO/页表核心、固件任务核心与RK平台代码；在复制出的核心文件末尾追加测试专用状态快照函数，不替换生产语句。相对DC核验的55项输入，只有测试入口脚本变化；新增测试与补充依赖纳入本轮64项输入清单。RMM、Client/Proxy运行源码及镜像未变，未重建或部署固件。

**攻击矩阵。** 针对两个Client的有效运行中任务，以及循环0、31、32、95的已暂存后继任务，共10组矩阵。每组139次请求：26种Client操作分别由其他Client、Proxy及陌生调用者执行（78次）；5次服务端对象检查/解除映射替换Client通道；6种任务服务操作分别替换通道、冒充服务角色、污染两个保留参数（24次）；32次修改任务token的generation位。合计1390次均返回`GPU_PRIVATE_INPUT`且四个输出值为0。这里是确定性的攻击排列，不是随机fuzzing。

每次拒绝后，逐字节比较实际对象、上下文、映射授权、页表、缓存摘要、backing归属、任务/组、固件状态及内部锚点；寄存器内容、MMIO读写、控制页读写、doorbell、AS命令、数据同步和CPU归还计数保持不变。输入复制临时区与策略锁诊断计数不属于该状态快照。既有域/分派测试继续运行；最终完整私有套件613条`=PASS`标记通过，使用ASan/UBSan。

**测试能否发现检查退化。** 四个变体均成功编译后由指定边界断言拒绝：BO_INSPECT错误解析为固定Client通道会暴露对象元数据；任务服务错误解析通道、忽略保留参数d、忽略保留参数e三个变体将预期INPUT错误变为STATE错误。这后三项证明测试能发现错误分类/授权边界退化，不能表述成已成功越权启动任务。各变体保留编译日志、运行日志及退出码-6。

```bash
HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/rsi-boundary-private-final \
 bash scripts/check/check-rmm-gpu-private.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
python3 scripts/maintenance/lab-run.py --run-id private-rsi-boundary-runtime-20261101-dd -- \
 python3 build/rmm-client-bo-20261030/verify-private-rsi-boundary-runtime.py
```

最终套件日志为`build/rmm-client-bo-20261030/private-rsi-boundary-private-final.log`，模型明细位于`rsi-boundary-private-final/rsi-boundary-1611484/`。初次通过日志和补上MMIO读取计数断言前的结果继续保留，最终结论使用上述重跑结果。命令、退出码、源码及日志SHA见`private-rsi-boundary-{source-manifest,local-checks,checkpoint}.json`；补丁检查日志为`private-rsi-boundary-patches.log`。

**板端状态与边界。** 独占只读核验确认64项本地输入未变化、冻结包完整、Client/Proxy Image、initrd、runner四项板端输入匹配，实际SD2固件字节匹配`firmware-private-running-check`。前后Host内核、CPU0–1及pmthor绑定一致，无VM/loop残留；记录位于`build/lab-runs/private-rsi-boundary-runtime-20261101-dd/`和`private-rsi-boundary-{sd-readback,final-runtime}.json`。本轮没有新增GPU工作负载或性能结果，893引用DA历史实测，不能推断性能提升。

本轮未发现需要修改运行代码的新漏洞。REC/通道解析、输入复制及设备原语是替身，未执行真实`copy_page_input`/`xshm_endpoint_peer`；模型无法证明实际RMM入口身份机制、真实Linux并发或物理GPT/GPC拒绝。服务端仍可能拒绝为自身服务的Client工作，本轮不声称防止全部DoS。恶意Client/Proxy、多Client实机、并发撤销、旧映射复用、真实GPU完成eventfd及广泛API/ML验收仍为NOT_RUN；AE VM_BIND EBUSY仍未解决，整体目标未完成。

## DE：同轮多队列完成页快照，892分，撤回DE并核验恢复DA893（2026-11-01）

统一记录：减少多个队列重复映射/失效同一张完成页｜DA893→DE892｜-1分/-0.11%｜仅RMM运行输入变化，相同Client/Proxy/Host/initrd/runner，GPU实际594MHz、CPU未锁恒频，两轮均重启后单Client完整720p｜部署`private-completion-snapshot-fw-20261101-de`退出0，测试`private-heap-720-20261101-de`退出1，证据回收和最终核验退出0｜预设保留线902及场景下限141/25/658FPS，撤回DE并核验恢复DA893；1000门槛FAIL。单轮不证明稳定因果收益。

**机制与边界。** 每组所有队列的16字节终止计数/错误槽位于同一张RMM保护的sync页。原OBSERVE和两次idle检查逐队列调用read_page，每次都建临时映射并完整失效4096字节。候选在每次检查的栈上建立独立快照：第一次需要完成字时复制该组全部槽位，后续队列只索引本次私有副本。两个活动队列的完成页读取2→1，八队列8→1；仍保留每队列两次独立输入/输出读取。单队列沿用原16字节读取及回调顺序。刷新后新调用idle检查，强制取得新副本；不跨STATUS检查、FLUSH_MEM或RSI调用缓存。较早的槽位快照可能推迟可见进度，不能单独生成成功。

完整新鲜STATUS、所有队列的insert/extract/scoreboard/blocked/OOM/序号与错误、根/配置、真实设备刷新、刷新后重查、精确退休和Client等待策略不变；未改变数据页归属、CPU可见性、Proxy逐任务接纳或GPU PT权限。与DB临时映射复用不同，本轮合并同一物理完成页的一次内容读取；DB仍逐次失效并复制。本轮未加入设备内部命中计数，模型读取次数下降不能直接作为实机命中率或省时测量。

**本地验证。** 1至8个stream的所有非空活动掩码，共1004轮前/后快照，覆盖稀疏队列、最后一行、下一轮错误字段变化、读取失败不发布快照、单队列再次读取及无效几何；四个错误变体（错用队列0、跳过复制、取消批量复用、遗漏错误字）均成功编译后断言拒绝。实际平台/私有核心/固件后端及实际RSI模型、完整私有套件通过；DA运行检查4个变体与DD跨Client边界4个变体继续通过，共12个编译变体拒绝。REC/通道/输入/设备原语仍为替身，模型不证明真实Linux并发或实体GPC。

保留开发失败：首版提前读取全部完成字，破坏了单队列夹具的固定读取顺序，后改为首次需要完成字时读取，并保留单队列原路径；多队列/执行域夹具原先只允许16字节，现仅允许sync页的对齐批量读取，其他输入/输出仍16字节，原故障注入继续执行。初版“删除queue上界”变体存活，因为活动掩码边界与位检查仍能独立拒绝，不算攻击拒绝或已发现漏洞；生产冗余检查保留，将该变体替换为遗漏错误字。失败源码、日志及首轮模型保留，最终本地证据为`private-completion-snapshot-backend-verified.log`、`private-completion-snapshot-private.log`、`private-completion-snapshot-running.log`及`completion-snapshot-model-final/`。

66项输入冻结；相对DD只修改生产固件核心、后端夹具和测试入口，新增快照模型与checker。23份O2 Debug flags与DA一致，断言、0x2800000预留末址保持；固定U-Boot/BL31/DDR来源、ELF/BSS/FIT检查通过。RMM ELF SHA `6b727f33cadf611b662bbe2f0a3e4da156dc2e8b9b0cd3ec6e0e2c5c39c8a083`，冻结包只有rmm.elf/rmm.img变化。U-Boot重新构建，不声明整份固件逐字节相同。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-de -- \
 python3 build/rmm-client-bo-20261030/run-private-completion-snapshot-with-uart.py \
 --images build/rmm-client-bo-20261030/private-completion-snapshot-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康和资源恢复、11份证据SHA核验通过。validation仍26成功/1既有数值例外/6无判据；CPU SIGNAL不证明真实GPU完成eventfd。blur156→156、terrain27→27、5×5 effect2d731→728FPS，场景下限通过。

| 指标 | DA893 | DE892 |
| --- | ---: | ---: |
| PREPARE操作µs/累计退休批 | 138.808 | 138.314 |
| 独立READY操作µs/累计退休批 | 0.037 | 0.039 |
| COMPLETE操作µs/累计退休批 | 338.073 | 339.090 |
| COMPLETE间隔µs/累计退休批 | 267.623 | 268.004 |

累计墙钟包含预热/校验、RPC/RMM/设备等待及调度，两轮退休批数不同；不能将阶段耗时当作纯页读取成本或把分数差归因到单个调用。快照结构和代码布局也随候选改变；收益只按组合观测解释。

**最终状态。** `private-completion-snapshot-runtime-20261101-de`退出0，`PASS_DA893_RESTORED`，核验64项当前输入、四项板端输入及实际SD2字节。当前包`build/rmm-client-bo-20261030/private-running-check-candidate`与`firmware-private-running-check`，保留分数893引用对应历史实测。候选源码已归档后撤下，恢复DA运行源码与DD测试，固件已恢复DA。最终核验后无新增GPU测量。

证据：`build/lab-runs/private-heap-720-20261101-de/realm-evidence/`及wrapper前后资源，`build/firmware-runs/private-completion-snapshot-fw-20261101-de/`，`private-completion-snapshot-{plan,source,local-checks,build-validation,layout,fit,candidate-validation,hardware,phase-comparison,scene-comparison,final-runtime,checkpoint}.json`。所有失败与未执行项继续保留。

整体目标未完成；AE VM_BIND EBUSY、真实GPU完成eventfd、广泛API/ML、多Client、恶意Client/Proxy、并发撤销与旧映射实机负例仍待验收。RK不能证明物理GPT/GPC拒绝，设计按目标平台保护假设评估，正常单Client测试不能代替隔离负例。

## DF：实际输入复制、IPA翻译与通道身份验证；补记撤回DE的32队列缺陷（2026-11-01）

统一记录：补齐私有数据入口的函数级验证缺口｜对照DA893（历史测量）→本轮未测｜分差及百分比不适用｜未改运行代码，无新增性能测量；仅新增本地测试与套件入口｜本地run-id `input-identity-private-df`，完整私有套件退出0、615条`=PASS`标记，补丁清单退出0｜保留测试；运行包未部署或替换，1000门槛仍FAIL，整体目标未完成。

**新增覆盖。** `opencca_gpu_input_identity_test.c`和`check-gpu-input-identity.py`直接提取未修改的生产`copy_page_input`、`realm_ipa_to_pa`，并编译完整生产`xshm_endpoint.c`；接入`check-rmm-gpu-private.sh`。相对DE恢复核验的64项输入，只有测试入口脚本变化；补充源码、依赖和测试后共冻结72项输入，本地冻结包8项哈希仍匹配。未重新构建、部署固件或运行GPU负载，不据此宣称性能改善或新的板端状态核验。

输入复制共8222个用例：两个REC在相同IPA使用不同私有页，覆盖1–4096字节全部合法长度；检查缓存失效先于唯一一次复制、临时映射与RTT锁释放、目标首尾边界不变、源页后续更改不改变私有副本；另覆盖合成各级描述符的块偏移、RAM/EMPTY/DESTROYED及翻译失败动作，无效长度、未对齐IPA和PAR边界拒绝。描述符与REC布局是模型，不能将合成描述符组合解释成真实硬件合法配置；也不保证恶意并发写入时得到原子应用层快照，后续必须继续验证私有副本内容。

通道验证运行96轮关闭/释放/重建，执行实际端点注册、offer、accept、close、release和peer解析：未accept、非成员、未注册调用者、空身份和无效通道均拒绝且peer输出清零；Proxy两条通道返回对应Client；重用内部槽位与owner存储后，旧端点/通道ID仍不能取得新实例身份。此处测试实际解析函数，原DD端到端分派模型的通道和输入替身保持不变；不能声称已把真实REC入口、真实RTT实现与整条GPU提交链同时集成验证。

**退化检测。** 8个变体均成功编译后由断言拒绝：同时去掉复制/翻译两层对齐守卫、同时去掉两层PAR守卫、跳过缓存失效、遗漏RTT解锁、遗漏块偏移、允许未accept通道、遗漏peer输出清零、允许非成员解析。两个地址守卫各有双层冗余，只删除外层并不构成绕过，测试不把冗余保护算成失败。首轮PAR变体因静态函数未使用而编译失败，日志保留；仅修正变体的语法引用后重跑，通过编译后才计入拒绝。原DD四个编译变体继续通过；这些是模型退化检测，不是8个已利用的生产漏洞。

```bash
HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/input-identity-private-df \
 bash scripts/check/check-rmm-gpu-private.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
```

命令、退出码、日志与源码SHA见`build/rmm-client-bo-20261030/private-input-identity-{source-manifest,local-checks,checkpoint}.json`。套件日志为`private-input-identity-private.log`，本轮函数模型明细为`input-identity-private-df/input-identity-1628834/`，原DD重跑明细为同目录`rsi-boundary-1628834/`。使用O2、断言、ASan/UBSan；8个变体均由断言捕获，不将普通崩溃或编译失败算作测试成功。

**撤回DE的额外缺陷。** 生产头文件`GPU_FIRMWARE_STREAMS`上限为32，DE独立模型却硬编码8，只覆盖1–8队列。在未修改的DE归档helper中，`active_queues >> group->streams`在streams=32时对32位unsigned执行右移32位。使用真实32队列头文件、队列31及活动掩码`0x80000001`，UBSan退出1并报告`shift exponent 32 is too large`；临时构建对照增加`streams < 32`守卫后退出0。复现源码、命令、退出码及日志在`completion-snapshot-32-audit-df/summary.json`。

DE此前已因892分撤回，此helper不在当前DA生产源码中；本轮未发现该问题存在于当前运行代码。归档和旧证据不改写，临时修正不合回生产。后续若重用该优化，须先修复位移并覆盖真实32队列上限，不能把原1004轮测试解释为完整上限验证。该缺陷不改变DE实测与撤回结论。

**边界与待验收。** REC、S2描述符、页表遍历原语、锁、slot与缓存仍为合成模型，未执行实际AArch64缓存指令、真实Linux并发或物理GPC。整体目标保持未完成：完整720p仍需达到1000；真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射实机负例继续保留。RK模拟不证明物理GPT/GPC拒绝，平台保护仍按目标平台假设评估。

## DG：同次RSI内有界完整FINISH观察，894分，撤回并恢复DA893（2026-11-01）

统一记录：减少完成等待中重复跨越RSI边界｜DA893→DG894｜+1分/+0.11%｜仅RMM运行输入变化，相同Client/Proxy/Host/initrd/runner、O2 Debug/断言、GPU实际594MHz、CPU未锁恒频，单Client完整720p｜部署`private-finish-window-fw-20261101-dg`退出0，测试`private-heap-720-20261101-dg`退出1，证据回收、恢复和最终核验均退出0｜预设保留线902及场景下限141/25/658FPS，撤回DG并核验恢复DA893；1000门槛FAIL。单轮不证明稳定因果收益。

**机制。** 原先完整FINISH返回INCOMPLETE后，Client经过等待再发下一次RSI。本轮在RMM加入`gpu_firmware_task_finish_window`：每次调用最多执行3次原有完整`gpu_firmware_task_finish_domain`，每次都重新执行原检查。使用RMM自身`read_cntfrq_el0()`和计数器计算100µs窗口，首轮耗时计入；仅在前次尚未完成、未进入CPU归还分段且窗口尚有余额时继续。成功、错误、携带非零`value[3]`的CPU归还游标立即原样返回。原8个完成/观察/退休相关函数逐字节不变，RSI仅改FINISH路由；无新ABI，不用缓存证明替代真实设备检查。

100µs是是否允许开始下一次观察的条件，**不是整次调用的墙钟上限**：已开始的设备操作沿用原超时，Host抢占也可能拉长调用。尚未登记的heap hint可能延后至本次有界调用返回。未改变Proxy接纳权限、数据页归属、GPU PT或CPU返回规则。

**本地验证。** 新增38类边界模型，覆盖终态原样返回、CPU归还边界、次数/时间约束、计数器回绕及频率/空时钟退路。5个错误变体均成功编译后被断言拒绝。实际RSI/私有核心/平台模型由独立MCU夹具延迟一轮或两轮scoreboard idle，验证同一次真实RSI分派内分别执行2次/3次完整观察，并完成真实代码中的flush/退休。标准后端、实际RSI、完整私有套件616条`=PASS`标记及固定补丁清单通过。模型仍含REC/设备原语替身，不替代实机并发与隔离验收。

保留两次开发失败：首版模型引用不存在的`GPU_PRIVATE_LIMIT`，修正为`GPU_PRIVATE_FULL`；首版MCU延迟夹具产生陈旧/非单调producer历史，被生产step5拒绝，修正夹具为仅延迟scoreboard idle并保持sequence/extract，不放宽生产检查。原失败日志为`private-finish-window-model.log`和`private-finish-window-window-backend.log`；最终通过日志分别加`-fixed`。完整套件日志`private-finish-window-private.log`，后端日志`private-finish-window-backend.log`，补丁日志`private-finish-window-patches.log`。准确构建参数、退出码及哈希见`private-finish-window-{local-checks,build-validation,review}.json`；套件以`HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2`、独立`GPU_PRIVATE_TEST_OUT`运行`bash scripts/check/check-rmm-gpu-private.sh`。

候选冻结75项输入，相对DF修改4项、新增3项；归档为`private-finish-window-source/`。独立RMM构建保留23份相同flags及原0x2800000预留末址，ELF/BSS/FIT通过；候选RMM ELF SHA `05798d5af2e24ee79f5314b8320975f23be39195793a584db81d7448d02285d2`。Guest/Host/initrd/runner未改，U-Boot按固定来源重新构建，不声称整份固件逐字节相同。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-dg -- \
 python3 build/rmm-client-bo-20261030/run-private-finish-window-with-uart.py \
 --images build/rmm-client-bo-20261030/private-finish-window-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

**实测。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康、CPU0–1/pmthor/loop/进程恢复及11份日志SHA核验通过。validation为26成功/1既有数值例外/6无判据，不能写成全部校验通过；CPU SIGNAL不证明实际GPU完成eventfd。blur156→156、terrain27→28、5×5 effect2d731→733FPS，场景下限通过。入口退出1的原因是894仍低于1000门槛。

| 指标 | DA893 | DG894 |
| --- | ---: | ---: |
| Client COMPLETE调用/累计退休批 | 2.462 | 2.063 |
| PREPARE操作µs/累计退休批 | 138.808 | 138.238 |
| COMPLETE操作µs/累计退休批 | 338.073 | 402.098 |
| COMPLETE间隔µs/累计退休批 | 267.623 | 184.773 |
| 主动短等待µs/累计退休批 | 239.989 | 175.862 |

Client完成调用减少16.22%、间隔减少30.96%，但调用内耗时增加18.94%，综合分数基本不变。阶段墙钟包含RPC/RMM/设备等待和调度，退休批数不同；短等待是间隔中的子项，不应重复相加。这支持“部分等待移入调用内”的解释，不能视为纯RSI切换成本测量。未增加实机内部重试计数，不能声称测得2次/3次路径的硬件命中率。

**回退与当前状态。** 归档75项候选哈希后，恢复4项修改并删除3项DG专用测试/checker，逐项匹配DF的72项输入。`private-finish-window-restore-20261101-dg`通过独占重启入口恢复`firmware-private-running-check`至SD2，退出0；`private-finish-window-runtime-20261101-dg`以只读独占入口核验72项源码、本地冻结包、四项板端输入和实际SD2固件字节，退出0、`PASS_DA893_RESTORED`。当前包为`private-running-check-candidate/`，配`firmware-private-running-check/`。893引用DA历史实测，回退后无新增GPU测量；本节收尾未改运行代码，无新增性能测量。

部署/恢复使用`python3 scripts/maintenance/lab-run.py --run-id <对应ID> --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware <对应固件目录> --run-id <对应ID>`；最终核验使用`python3 scripts/maintenance/lab-run.py --run-id private-finish-window-runtime-20261101-dg -- python3 build/rmm-client-bo-20261030/finalize-private-finish-window.py`。证据回收run-id为`private-finish-window-evidence-20261101-dg`、退出0；运行`pull-private-finish-window-evidence.py`，随后本地`analyze-private-finish-window-hardware.py`退出0。

证据保留于`build/lab-runs/<上述run-id>/`、`build/firmware-runs/<部署或恢复run-id>/`及`build/rmm-client-bo-20261030/`；关键索引为`private-finish-window-{hardware,phase-comparison,scene-comparison,final-runtime,checkpoint}.json`。所有失败、候选源码和测量保留。整体目标未完成：1000门槛FAIL；真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射实机负例未追加验收。RK不证明物理GPT/GPC拒绝，目标平台保护仍是设计假设。

## DH：真实通道、输入复制与IPA翻译接入同一RSI边界模型（2026-11-01）

统一记录：验证Client身份、私有输入和RMM对象授权的组合边界｜对照DA893（历史实测）→本轮未测｜分差及百分比不适用｜未改运行代码，无新增性能测量；仅修改本地边界checker并新增测试｜本地run-id `rsi-identity-private-dh`，完整私有套件退出0、615条`=PASS`标记，补丁清单退出0｜保留测试；本轮无部署、硬件测试或板端状态复核，运行包仍引用DA候选，1000门槛FAIL，整体目标未完成。

**填补什么缺口。** DD把实际RSI分派、私有GPU核心和RK平台代码连起来，但通道解析及输入复制仍是替身；DF分别验证了真实辅助函数，却没有把它们接到同一条提交链。本轮重构`check-gpu-rsi-boundary.py`，去掉这个checker中的两类旧替身：链接完整生产`xshm_endpoint.c`，从生产文件原样提取`copy_page_input`、`realm_ipa_to_pa`，与实际RSI分派一起编译。原普通后端仍保留独立适配器，继续承担设备状态/完成语义验证；没有新运行接口或权限。

新头文件`opencca_gpu_rsi_identity_test.h`提供合成REC/S2、锁/slot/cache原语；`opencca_gpu_rsi_identity_boundary_test.h`提供组合攻击矩阵。通道不再凭固定数字返回Client，而是通过真实register/offer/accept建立，使用实际返回ID；断开和重新连接调用真实close并取得新ID。原正常生命周期场景仍必须通过。输入型正常请求由测试适配器把C数组放入对应调用者的模拟IPA页，再进入真实复制/翻译函数；复制后立即改变模拟源页，后续生产代码必须继续使用私有副本。每个编译变体独立保存fixture、生成头文件及辅助函数，避免引号include误选公共基线。

**新增10组矩阵。** 两个Client各在运行中、后继任务已暂存的循环0/31/32/95执行一次。每组41个拒绝请求：三个攻击角色（另一Client、Proxy、陌生调用者）各12个输入请求，共36个；另有5个通道请求。原1390次跨Client请求继续执行，新增410次，合计1800次均拒绝且输出值清零。此计数是确定性的排列，不是fuzzing次数或发现的生产漏洞数。

输入请求使用相同IPA和四个不同REC映射，覆盖1项/512项输入列表、未对齐IPA、PAR外地址、缺失映射、EMPTY、UNASSIGNED_RAM、DESTROYED、零/过大计数及保留字段。60次合法输入复制精确核验所属调用者、缓存失效先于唯一复制、4096字节上限、源页变化后副本不变，以及锁/临时映射释放；其后的外来BO归属检查仍拒绝。失败输入不发生复制，区分返回Realm和报告Stage-2翻译异常，并核验故障层级。这里不保证恶意并发写入下的原子应用层快照。

通道请求覆盖其他Client的已建立通道、非成员、未accept、close后旧ID、端点释放并在相同owner存储重注册后的旧通道。BO_CREATE使用合法页对齐大小和权限，使请求不能仅靠无关参数检查被拒绝。每组还有一次accept后的实际BO_INSPECT成功对照，证明合法通道仍定位对应Client。所有拒绝后比较实际对象、页表、授权、任务和固件元数据字节，并检查MMIO、控制页、doorbell、AS命令、数据同步和CPU归还计数不变。

**测试能否发现退化。** 9个变体都成功编译后被指定断言捕获：原来的BO检查错通道、任务服务错通道、忽略保留参数d/e四项；新增跳过缓存失效、遗漏RTT解锁、错误固定为Client A的输入页表、允许未accept通道、允许非成员解析五项。断言要求同时验证退出码和预定oracle；编译失败、普通崩溃或sanitizer报错不算成功。以O2、断言、ASan/UBSan运行，新增checker对未定义行为禁用恢复。DF的8222个独立复制用例、96轮端点生命周期和8个编译变体继续通过；它们与本节九项分别计数。

**保留的开发失败。** 首版模型误要求失败RTT遍历解除临时表映射时仍持锁，与真实helper先解锁再unmap的顺序不符；修正模型。第二版把陌生调用者角色编号用作仅两项的Client通道数组索引，ASan捕获模型越界；改为对非Client选择无效通道。第三版“允许未accept”变体存活：攻击请求BO大小误用1字节，被核心独立的页对齐检查拒绝；修正为4096字节后，九个变体均被捕获。失败源码及日志保留于`rsi-identity-{first,second,third}-dh/`和`private-rsi-identity-{first,second,third}.log`，第三版失败时的额外源码位于`source-at-failure/`。没有修改生产检查以迁就夹具。

```bash
HOST_CC=/home/mzh/gpu/build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=/home/mzh/gpu/build/rmm-client-bo-20261030/rsi-identity-private-dh \
 bash scripts/check/check-rmm-gpu-private.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
```

最终套件日志为`build/rmm-client-bo-20261030/private-rsi-identity-private.log`，组合矩阵及九个变体明细位于`rsi-identity-private-dh/rsi-boundary-1645755/`；补丁日志`private-rsi-identity-patches.log`。套件stdout仍为615条PASS：组合矩阵明细保存在子测试日志中，不能用stdout标记数量代替覆盖统计。命令、退出码、哈希和失败索引见`private-rsi-identity-{plan,local-checks,checkpoint}.json`。相对DG恢复后的72项输入仅修改边界checker，新增两个测试头文件，共74项冻结于`private-rsi-identity-source/`，全部运行源码及冻结包哈希保持。

**范围边界。** 本轮已把真实辅助函数与RSI分派集成，但REC身份来源、S2描述符布局/遍历原语、锁、缓存与设备仍是主机模型；RSI内存操作表仍使用`donated_ops`适配器，未执行真实REC/RTT和实际缓存指令，也未测试Linux并发。不能据此宣称物理Proxy拒读或DMA隔离已验收。未重建/部署运行镜像，893仍引用DA历史结果；最新板端核验仍为上一节DG回退后的记录。完整720p达1000、真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射实机负例仍待完成，整体目标保持active。

## DI：真实live刷新前后复用组合运行检查，896分，撤回并恢复DA893（2026-11-01）

统一记录：减少真实live刷新前后重复的固件MMIO读取｜DA893→DI896｜+3分/+0.34%｜仅RMM运行输入改变，Client/Proxy/Host/initrd/runner相同，O2 Debug/断言保留，GPU实际594MHz、CPU未锁恒频，单Client完整720p｜部署`private-flush-running-check-fw-20261101-di`退出0，测试`private-heap-720-20261101-di`退出1，证据回收及最终核验退出0｜未达预设902分保留线，撤回DI并核验恢复DA893；1000门槛FAIL，整体目标未完成。单轮不证明稳定因果收益。

**改动。** `plat_opencca_gpu_pt_flush_live()`原来在刷新前后分别执行`pt_prepare(existing=true)`和`firmware_configuration()`，重复读取固件根与配置。本轮在每一侧独立调用已有的`plat_opencca_gpu_pt_check_running()`，共享该侧的新鲜检查；动态MCU/故障/计数器仍在Client AS读取后复查。两轮检查、真实LOCK/FLUSH_MEM、全部其他AS根别名检查、AS_ACTIVE轮询及跨刷新频率/配置一致性全部保留。结果不跨硬件命令或RSI调用复用，不改完成条件、页归属、租约、缓存归还及退休，无新ABI。

**本地验证与构建。** 扩展`check-gpu-running-check.py`，在测试专用平台副本中编译原刷新函数；其函数体与冻结前生产版本按去除注释/空白后的比较一致。正常模型MMIO读取146→124（减少15.07%），LOCK/FLUSH_MEM命令、写次数及最终寄存器一致；这是模型计数，不是硬件提速比例。原有29类刷新前后破坏、刷新失败与保留状态检查继续执行。实际平台/核心和实际RSI两组模型通过；原4个加新增3个错误变体均成功编译后由断言拒绝，新增项分别省略真实刷新、第二轮检查和别名检查。普通崩溃、编译失败、ASan/UBSan错误不计成功。

完整私有套件退出0、615条`=PASS`，DH组合身份边界与DF输入复制/端点模型继续通过；补丁清单和资源预检退出0。仅平台文件与该checker两项输入改变，共74项候选输入已归档。独立RMM构建与DA `rmm-build-running-check`的23份flags相同，原0x2800000预留末址和断言保留；构建JSON沿用`flags_identical_to_bf`字段名，实际比较对象是DA，不能误称重新比较BF。ELF/BSS/固件布局与FIT检查通过，RMM ELF SHA为`2a3ce1f0ada1dcd652509084d38aeb8ca7791c280d5598e8f42df3e794e466ff`。U-Boot按固定源码/配置重新构建，不声称整份固件逐字节相同。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 python3 scripts/check/check-gpu-running-check.py \
 --out build/rmm-client-bo-20261030/flush-running-check-model-di
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/flush-running-check-private-di \
 bash scripts/check/check-rmm-gpu-private.sh
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-di -- \
 python3 build/rmm-client-bo-20261030/run-private-flush-running-check-with-uart.py \
 --images build/rmm-client-bo-20261030/private-flush-running-check-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

以上为候选存在时实际执行的命令；当前两项修改已撤回，本地模型复验须先恢复`private-flush-running-check-source/`中对应的冻结输入，不能直接把当前DA代码当作DI候选运行。

**板端结果。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic、两端kernel-log/pool-unbind、VM退出0/0、Host健康、CPU0–1/pmthor/loop/进程恢复及11份证据SHA核验通过。validation为26成功/1既有数值例外/6无判据，不能表述为全部数值校验通过；CPU SIGNAL不证明实际GPU完成eventfd。blur156→156、terrain27→27、5×5 effect2d731→730FPS，预设下限141/25/658FPS通过。入口退出1是因为总分仍低于1000。

| 指标 | DA893 | DI896 |
| --- | ---: | ---: |
| Client COMPLETE调用/累计退休批 | 2.462 | 2.464 |
| PREPARE操作µs/累计退休批 | 138.808 | 138.148 |
| COMPLETE操作µs/累计退休批 | 338.073 | 335.521 |
| COMPLETE间隔µs/累计退休批 | 267.623 | 267.417 |

累计阶段墙钟包含RPC/RMM、设备等待和调度，退休批数也不同；不能将分差直接归为某22次MMIO读取的成本，更不能从模型读取比例推算整体提分。没有新增实机live刷新分段计时。

**最终状态。** 恢复平台文件和checker两项修改，逐项匹配DH的74项输入；通过独占重启入口将`firmware-private-running-check/`恢复至SD2，恢复run-id `private-flush-running-check-restore-20261101-di`退出0。当前包仍为`private-running-check-candidate/`，配`firmware-private-running-check/`；893引用DA历史实测，回退后无新增GPU测量。`private-flush-running-check-runtime-20261101-di`退出0，核验74项源码、本地冻结包、四项板端输入及实际SD2固件字节。收尾文档整理未改运行代码，无新增性能测量。候选源码、失败门槛、测量和回退证据全部保留。

部署使用`lab-run.py --run-id private-flush-running-check-fw-20261101-di --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-flush-running-check --run-id private-flush-running-check-fw-20261101-di`。证据回收run-id为`private-flush-running-check-evidence-20261101-di`，最终核验为`private-flush-running-check-runtime-20261101-di`，分别通过同一独占入口运行`pull-private-flush-running-check-evidence.py`与`finalize-private-flush-running-check.py`；本地分析`analyze-private-flush-running-check-hardware.py`退出0。完整命令、退出码、前后资源、日志及SHA见`build/lab-runs/<run-id>/`、`build/firmware-runs/<部署或恢复run-id>/`及`build/rmm-client-bo-20261030/private-flush-running-check-{local-checks,review,build-validation,candidate-validation,hardware,phase-comparison,scene-comparison,final-runtime,checkpoint}.json`。

整体目标保持未完成：完整720p达1000、真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射实机负例仍待验收。RK模拟不证明物理GPT/GPC拒绝，平台保护仍是目标平台假设。

## DJ：实际BO来源检查及物理内存回调模型（2026-11-01）

统一记录：补齐Client私有BO来源登记和物理内存操作的函数级证据｜对照DA893（历史实测）→本轮未测｜分差及百分比不适用｜未改运行代码，无新增性能测量；仅新增测试并修改套件入口｜本地run-id `memory-ops-private-dj`，完整私有套件退出0、616条`=PASS`，补丁清单退出0｜保留测试；无构建部署或硬件测试，1000门槛仍FAIL，整体目标未完成。

**检查什么。** 新增`opencca_gpu_memory_ops_test.c`及`check-gpu-memory-ops.py`，原样提取生产RSI文件的七个函数：`source_page`、`clear_page`、`write_page`、`read_page`、`sync_page_for_device`、`sync_page_for_cpu`和`cache_barrier`；链接完整生产`xshm_rtt.c`与`opencca_gpu_private.c`。函数体不修改，主机模型提供RD/RTT、granule锁、临时映射、S2描述符、缓存效果及外部busy探针。物理回调的PA在真实调用链中来自可信对象记录，本测试直接调用这些内部函数，不能据此声称其本身认证了调用者。

计数共8227个确定性场景，不是fuzzing次数：22个来源场景中，两个Client在相同IPA分别解析到各自HPA；共享范围、IOMMU范围和物理页探针分别报告冲突时拒绝，另一Client保持可用；未对齐、PAR外、非RAM描述符及非DATA物理页拒绝；通过实际BO创建/append登记后，同一IPA在RTT查询之前即被真实`gpu_private_range_busy`拒绝，销毁未封存对象后才可重用。外部共享/IOMMU/物理busy探针是可控替身，未验证这些探针的真实区域表或并发行为。

8205个物理操作场景包括：1–4096字节全部长度的页尾写入和读回，共8192例，检查实际字节、新鲜设备数据、输出两侧保护字节及另一Client页面不变；另外覆盖零长度、跨页、SIZE_MAX、空缓冲区、缺失/非DATA页、整页清零、CPU→GPU交接、GPU→CPU归还及独立屏障。无效请求不得建立映射；成功与失败后锁和映射均须平衡。缓存替身以独立CPU/设备数组检查数据方向和动作顺序，不模拟真实cache line、AArch64缓存指令、TLBI或并发访问。

**退化检测。** 11个变体均成功编译后被预期断言拒绝：去掉共享、私有登记、IOMMU和物理页四类来源守卫；去掉读前invalidate、写后clean或整页清零；将CPU归还错误改成flush、将设备交接错误改成invalidate；遗漏读屏障或DATA解锁。检查要求退出-6、指定`GPU_MEMORY_OPS_REJECT`及Assertion，ASan/UBSan报错、普通崩溃和编译失败不计成功。首次“设备交接改invalidate”变体因`flush_dcache_range`不再被引用而编译失败；仅给变体增加void函数引用后重新执行，未修改生产实现。原失败、当时测试源码及日志保留于`memory-ops-first-dj/`、`private-memory-ops-first.log`。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 python3 scripts/check/check-gpu-memory-ops.py \
 --out build/rmm-client-bo-20261030/memory-ops-fixed-dj
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/memory-ops-private-dj \
 bash scripts/check/check-rmm-gpu-private.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
```

使用O2、断言、ASan/UBSan；完整套件及补丁清单退出0。DH的10组普通/10组集成边界矩阵及9个编译变体、DF的8222个输入复制用例/96轮端点生命周期及8个编译变体继续通过，分别计数。新模型为独立函数/核心模型，**没有把实际物理回调接回DH的同一RSI链**；该链的`donated_ops`适配器仍保留。没有增加实机完成eventfd或恶意Client/Proxy验收证据。

相对DI恢复后的74项输入，仅套件脚本变化，新增两个测试文件；另补录七项依赖，共83项冻结于`private-memory-ops-source/`，编译器报告的仓库内依赖已核对。DA冻结包八项哈希不变；本轮不重新检查板端，最新运行状态仍引用DI回退后的独占核验，不能将83项本地冻结冒充板端核验。命令、退出码及日志见`build/rmm-client-bo-20261030/private-memory-ops-{plan,source,local-checks,checkpoint}.json`；完整日志为`private-memory-ops-private.log`，模型明细位于`memory-ops-private-dj/memory-ops-1662952/`。

整体目标保持未完成：完整720p达1000、真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、多Client、恶意Client/Proxy、并发撤销和旧映射实机负例继续待验收。物理GPT/GPC保护仍按目标平台假设评估，模型不证明Proxy在真实硬件上无法读取Client数据。

## DK：控制页缓存范围候选查重后撤回，无新增GPU测量（2026-11-01）

统一记录：尝试缩小捐赠控制页读取前的缓存失效范围，随后发现重复实验｜对照DA历史893分 → 本轮未测｜分差及百分比不适用｜仅候选RMM变化、O2 Debug及断言保持，未启动GPU workload｜候选部署、恢复及最终核验三个run均退出0，路径如下｜撤回全部三项候选源码修改，恢复DA893匹配运行包；整体目标未完成。

本轮将`read_page()`的整页失效改为`memory + offset, bytes`，并增强DJ模型的缓存行边界检查。候选通过28,598个模型场景及15个编译后由断言拒绝的错误变体（其中整页回退变体只检查性能范围约束），完整私有套件616条PASS；实际平台/核心/RSI检查及4个运行检查变体、固定补丁清单通过。独立ARM64 O2 Debug构建23份flags与DA相同，FIT和含BSS布局通过，预留末址仍为0x2800000。模型和汇编证明请求范围内的新鲜读取及操作数变化，不证明端到端性能或实体GPC。

**重复判断及撤回原因。** 候选部署开始后补查审计索引，发现AK459→458和BG620→620已采用同一机制并撤回；本轮没有新的当前路径归因足以支持重测。此前没有查全历史记录，导致重复构建和一次不必要的部署。未继续执行完整720p、计算、多Client或攻击测试，也未把模型操作数或旧成绩当成本轮收益。候选源码及模型保存在`private-read-range-source/`、`read-range-model-dk/`、`read-range-private-dk/`和`read-range-running-dk/`，不进入保留运行版本。

执行命令与证据（目录默认相对`build/rmm-client-bo-20261030/`）：

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/read-range-private-dk \
 bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 python3 scripts/check/check-gpu-running-check.py \
 --out build/rmm-client-bo-20261030/read-range-running-dk
python3 opencca/scripts/setup/apply-local-patches.py --check
python3 scripts/maintenance/lab-run.py --run-id private-read-range-fw-20261101-dk \
 --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py \
 --firmware build/rmm-client-bo-20261030/firmware-private-read-range \
 --run-id private-read-range-fw-20261101-dk
python3 scripts/maintenance/lab-run.py --run-id private-read-range-restore-20261101-dk \
 --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py \
 --firmware build/rmm-client-bo-20261030/firmware-private-running-check \
 --run-id private-read-range-restore-20261101-dk
python3 scripts/maintenance/lab-run.py --run-id private-read-range-runtime-20261101-dk \
 -- python3 build/rmm-client-bo-20261030/finalize-private-read-range.py
```

以上均退出0。模型日志为`private-read-range-{private,running,patches}.log`；构建、打包命令见`private-read-range-build-commands.json`和`uboot-read-range-commands.json`。板端日志为三个run各自的`build/lab-runs/<run-id>/result.json`，刷写/UART/实际启动区备份位于`build/firmware-runs/<部署或恢复run-id>/`。正常刷写只使用SD storage ID 2，Host内核和rootfs未更新；两次刷写后Host与Realm能力恢复，最终CPU0–1、pmthor及资源检查通过。

最终逐项核验恢复了86项本地输入（DJ83项加三项未修改架构缓存依赖），四项板端运行输入及实际SD2固件字节；状态`PASS_DA893_RESTORED`，见`private-read-range-final-runtime.json`及`private-read-range-restored-sd-readback.json`。当前仍为`private-running-check-candidate/`与`firmware-private-running-check/`，RMM ELF SHA仍是`adc768a3745c66fcb9306782e361653eb1db005ea38e1341c57aa6f261b1cad4`。恢复后没有新增GPU测量；保留893仍来自DA历史run。

新增[性能候选与已有实验索引](GPU_PRIVATE_OPTIMIZATION_DECISION_INDEX.md)，覆盖本次漏查机制和其他已撤回候选；文档整理未改运行代码，无新增性能测量。本轮没有实现进展或新增实体隔离验收证据。1000门槛、真实GPU完成eventfd、AE EBUSY、广泛API/ML/多Client、恶意并发/撤销/旧映射及物理保护边界等未完成项保持。

## DL：同一RSI链贯通身份、页归属和实际内存回调（2026-11-01）

统一记录：补齐DH身份边界模型与DJ物理回调模型之间的调用链缺口｜对照DA893（历史实测）→本轮未测｜分差及百分比不适用｜未改运行代码，无新增性能测量；仅新增测试及套件入口｜本地run-id `rsi-memory-chain-private-dl`，完整私有套件退出0、617条`=PASS`，补丁清单退出0｜保留测试；无固件/内核构建、部署或硬件测试，1000门槛及整体目标未完成。

新增`opencca_gpu_rsi_memory_chain_test.c`和`check-gpu-rsi-memory-chain.py`，原样提取实际RSI分发、`task_heap_call`、输入复制、IPA翻译、物理busy包装函数及七个内存回调，链接实际端点、私有页表核心、`xshm_rtt`、GPU租约/DMA映射表、固件核心与RK平台后端。沿用既有后端夹具提供平台符号，新的场景使用独立的四个RD模型对象；并未把DH原有任务生命周期夹具的全部适配器替换掉。

**同链检查。** 共61次RSI请求，包括两个Client在相同IPA上注册各自页面；输入页CPU副本故意保持陈旧，复制后立即篡改客体输入，后续登记仍须使用RMM私有快照。Client创建精确映射授权，Proxy通过真实通道消费授权；错误Client通道、未隔离发送者、错误GPU VA、授权重放及跨Client查询/释放必须拒绝。独立遍历实际生成的硬件格式GPU页表，逐页检查叶子指向对应Client的HPA；QUERY仅返回计数，不作为地址正确性证据。错误请求后的合法映射仍须成功，完成后解除映射并销毁对象。

真实`source_page`在重复登记、共享范围/IOMMU范围冲突、实际DMA物理映射冲突时拒绝；后两类范围探针仍为替身，DMA映射表及物理busy判断使用实际代码。真实GPU旧租约只能由仍拥有原始MMIO的运行态服务获取，服务隔离会清理旧租约，因此旧租约冲突在隔离前用单独的内部回调探针验证，**不计作隔离后RSI负例**。未接受及已关闭通道不得新建BO，非所属Client的BO append同样拒绝。

驻留BO交接执行实际RTT隐藏与逐页flush；NC交接执行实际隐藏、flush及强制NC恢复，检查S2描述符与设备可见字节。释放时逐字节检查清零，RTT写入模型另在WB映射恢复的瞬间核验清零已对设备可见，避免只看最终状态。控制对象通过RSI分两批捐赠513页，检查CPU页隐藏和清零；分批销毁的第一次只归还512页，剩余一页保持隐藏，第二次才完全归还。每次RSI结束检查锁及临时映射平衡、未使用返回寄存器为零。

**辅助内部调用的边界。** 在真实控制对象登记后，可信消费者持策略锁获取对象、由可信记录解析第0/512页PA，调用实际`write_page`、`read_page`和`sync_page_for_cpu`，检查新鲜字节、输出保护区及设备结果不被CPU旧内容覆盖；另一Client不能解析该控制对象。它们是独立辅助探针，不是客体可调用的任意PA读写RSI，也不能将七个回调全部描述成由上述61次RSI直接执行。

12个错误变体均成功编译后，由指定`GPU_RSI_MEMORY_CHAIN_REJECT`断言拒绝：遗漏输入invalidate、物理busy检查、共享/IOMMU/私有登记守卫、清零、交接flush、输入RTT解锁或控制写clean；将Client来源错误地按服务身份翻译；允许未接受通道；把NC恢复为WB。要求退出-6及Assertion，编译失败、普通崩溃和ASan/UBSan错误不计成功。正常路径保留O2、断言和ASan/UBSan。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/rsi-memory-chain-private-dl \
 bash scripts/check/check-rmm-gpu-private.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
```

均退出0。日志为`build/rmm-client-bo-20261030/private-rsi-memory-chain-{suite,patches}.log`，新增模型明细位于`rsi-memory-chain-private-dl/rsi-memory-chain-1680724/`，命令、断言及退出码见`private-rsi-memory-chain-local-checks.json`。已有DH/DF/DJ测试继续通过，分别计数；617为完整套件PASS标记数，61为新增模型RSI请求数，均不是fuzzing次数。

保留前三次夹具失败：`rsi-memory-chain-first-dl/`为缺少架构宏/原型及误用不存在根查询接口的编译错误；`second-dl/`为漏接实际物理busy包装函数的链接错误；`third-dl/`为隔离后尝试申请旧GPU租约的错误前提。修正均限于测试，日志保留。中间`fourth-dl/`的61次请求及7个变体通过，最终完整套件扩展到12个变体；不把两轮请求累加成独立覆盖量。

编译器预处理依赖与DK86项输入合并后，共113项本地输入冻结于`private-rsi-memory-chain-source/`；原86项中只有套件脚本变化，新增两个测试文件，其余新增项为补录依赖。八项冻结运行包与七项固件输出哈希保持不变。本轮不访问板端，最新板端/SD2证据仍是DK核验，不能把本地113项冻结冒充板端验证。

仍需验收：真实GPU完成eventfd、AE VM_BIND EBUSY、完整720p达到1000、广泛API/ML/多Client，以及恶意Client/Proxy、并发REC/撤销、旧映射实机负例。新模型只贯通登记/映射/内存生命周期链，未贯通GPU任务启动和真实完成的全部物理回调。REC/RTT布局、granule锁、S2描述符编码、TLBI、缓存、页表物理寻址与MMIO仍为主机模型，不证明实体GPT/GPC或Proxy在真实平台上无法读取Client数据。

## DM：GPU完成eventfd探针与冻结载荷接线，待实机执行（2026-11-01）

统一记录：补齐现有CPU SIGNAL探针未覆盖的真实GPU fence→eventfd验证入口｜对照DA893（历史实测）→本轮未测｜分差及百分比不适用｜仅测试用户态、init/runner与打包接线变化，RMM/内核数据路径不变，未部署｜本地run-id `completion-eventfd-dm`；完整私有套件退出0、618条`=PASS`，ARM64构建、独立候选打包与补丁清单退出0｜保留工具；真实GPU完成eventfd仍NOT_RUN，1000门槛及整体目标未完成。

**探针执行的检查。** `gles_compute_smoke.c --gpu-eventfd`在非空GLES dispatch与memory barrier后建立EGL native fence，glFlush提交，再导出sync_file。检查前不CPU SIGNAL、不glFinish、不阻塞映射结果。新`gpu_completion_eventfd.h`要求底层1–32个fence均来自`panthor-client-private`；将借用的sync_file导入本地binary syncobj，再TRANSFER至新timeline point 7，分别注册flags=0的完成eventfd。每个eventfd有界等待、要求读取值恰好1且立即再次读取为空；最后重新查询整体及逐fence成功状态，避免错误fence仅因发出通知而通过。所有已创建的syncobj/eventfd均尝试回收，清理失败也使探针失败，借用的sync_file由调用方关闭。

通知成功后，以零超时检查EGL sync已完成，再读取结果。每轮输入混入不同迭代值，对全部65536元素检查，防止相同输入掩盖上一轮残留；常规性能模式仍使用原输入。`--gpu-eventfd`与`--perf`互斥，完整720p评分分支不运行此探针。这是计算结果与通知接线检查，不是以driver名称证明任务来源：fence可能在注册前已经完成，阻塞结果映射也不能作为pending回调证据。尚不证明中断真实性、任务绑定、恶意Proxy隔离、跨Client安全或物理GPT/GPC。

**载荷与runner。** init新增`compute-eventfd`命令，将独立initrd内的匹配GLES工具绑定到只读workload root；打包器增加`--gles-compute`并要求`--glmark-env`。私有compute runner同时派发各Client，只有全部计算标记、精确eventfd标记与Mali renderer通过后才写PASS；失败保持ATTEMPTED。上传前检查拒绝缺失工具、旧init命令、旧工具模式或错误架构，属于包装/版本检查而非attestation。普通共享compute不切换新命令。

**本地证据。** `check-gpu-completion-eventfd.py`编译实际header及原样提取的EGL桥接函数，使用真实Linux eventfd和DRM/EGL替身：38个探针场景覆盖注册前已完成/注册后模型完成、驱动身份/数量/错误状态、导入/转换/注册失败、缺失/重复通知、poll EINTR/期限、创建与清理失败；16个EGL检查覆盖扩展词边界、函数缺失、创建/导出/flush/等待/销毁失败。runner共36项检查，新增两Client探针失败不得PASS及打包拒绝场景。ASan/UBSan、Wall/Wextra/Werror保留。没有把这些模型计为真实GPU执行。

命令与日志（默认相对`build/rmm-client-bo-20261030/completion-eventfd-dm/`）：

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/completion-eventfd-dm/private-suite \
 bash scripts/check/check-rmm-gpu-private.sh
python3 scripts/check/check-gpu-completion-eventfd.py \
 --out build/rmm-client-bo-20261030/completion-eventfd-dm/model-final
python3 scripts/check/check-gpu-private-runner.py
REALM_XSHM_BUILD_OUT=build/rmm-client-bo-20261030/completion-eventfd-dm/tools \
 bash scripts/build/build-realm-xshm.sh
python3 build/rmm-client-bo-20261030/completion-eventfd-dm/package-candidate.py
python3 opencca/scripts/setup/apply-local-patches.py --check
```

上述均退出0。完整日志`private-suite.log`，独立探针`model-final.log`及`model-final/{results,build,stdout,stderr}.*`，最终runner为`runner-final.log`；ARM64 GLES完整命令/退出码在`gles-build-final-command.json`，工具为`tools-build.log`；打包命令与六个必需输入哈希在`package-validation.json`，补丁清单为`patches.log`。构建曾两次因目标sysroot中的libm/libc链接脚本绝对路径失败，日志`gles-build.log`、`gles-build-crosslib.log`保留；将交叉工具链自身lib目录置于搜索顺序前端后成功，未安装或更新依赖。最终增加每轮输入区分后重新ARM64编译并复核探针模型；补齐未选eventfd的NOT_RUN初始化后复核36项runner检查，没有重复计数完整套件。

独立候选位于`completion-eventfd-dm/candidate/`，仅替换副本的initrd/runner；内核和RMM继承DA冻结包。新initrd SHA-256为`19243542efa0cc172f54fbe4064225983cd6cc3ac4622ceb863090e255a503e7`，`hashes.json`逐文件登记。当前运行候选仍是`private-running-check-candidate/`与`firmware-private-running-check/`，RMM ELF SHA仍为`adc768a3745c66fcb9306782e361653eb1db005ea38e1341c57aa6f261b1cad4`。本轮无板端连接、部署或性能测量，DK板端核验与DA893仅继承历史证据；先满足完整720p≥1000再进行compute/API/多Client硬件扩展。AE VM_BIND EBUSY、恶意并发/撤销/旧映射以及物理保护边界等未完成项保持。最终源码和候选哈希冻结见`private-gpu-completion-eventfd-checkpoint.json`。


## DN：实际RSI内存回调贯通到双Client任务生命周期（2026-11-01）

统一记录：补齐DL登记/映射链尚未覆盖任务启动与完成的验证缺口｜对照DA893（历史实测）→本轮未测｜分差及百分比不适用｜仅修改测试与套件入口，未改运行代码，无新增性能测量｜本地run-id `task-memory-chain-dn`，完整私有套件退出0、621条`=PASS`，补丁清单退出0｜保留验证；无部署或板端访问，1000门槛及整体目标未完成。

新增`opencca_gpu_rsi_task_chain_test.c`，通过条件编译复用DL夹具，并接入实际平台AS prepare/extend/check/flush/detach及固件安装、启动、配置函数。实际RSI分发、端点、私有输入复制、IPA翻译、GPU页表/任务核心、`xshm_rtt`和七个物理内存回调在同一条调用链中执行；底层REC/RTT、granule锁、临时映射、缓存效果和MMIO仍为主机模型。设备可见字节与CPU字节分开存储，硬件格式PTE指向设备字节数组，MCU替身遍历实际PTE并推进wrapper完成记录，**不解释或执行Client shader**。

**正常链。** 沿用DL检查后，由Proxy身份通过实际RSI复制路径逐块加载固定固件、捐赠513页控制内存，再启动和配置MCU模型。独立遍历控制页及两个Client的GPU页表，核验实际后备地址与CPU隐藏状态。两个Client分别创建可执行BO、上下文和双队列group，配置/任务参数复制后立即篡改客体输入；可信操作必须继续使用私有快照。Proxy消费Client委托，通过`TASK_DISPATCH`进入真实内存回调，要求恰好flush该Client的两页数据，控制页始终CPU隐藏，Proxy无原始MMIO授权。

设备输出由测试显式写入独立的设备字节数组，随后Client通过实际`TASK_FINISH`完成观察、CPU归还和退休。每次数据invalidate发生时，测试同时核验对应AS已禁用、group挂起已应答；每个Client必须恰好归还两页，逐字节核验全部结果。错误通道dispatch、其他Client FINISH、提前RETURN/RETIRE和已退休token重放均拒绝；正常路径最终销毁group、解除映射并销毁上下文和BO。

**故障检查。** 两个附加场景在FINISH读取受保护控制页之后，分别篡改Client根寄存器或对应stream错误状态，要求状态失败、没有CPU数据归还、没有任务退休，并保留BO引用。隔离后的FINISH/RETURN/RETIRE重放不得继续接触设备或内存，group/BO不能提前销毁。测试仅恢复注入的模型寄存器，让另一Client完成；失败任务的受保护隔离状态和引用仍保留到显式可信reset，之后再回收。该模型不证明共享GPU故障下的硬件连续可用性。

三个场景分别为177、179、179次RSI请求，包含重复执行的DL准备检查，不累加成独立覆盖规模。12个既有错误变体和三个任务阶段专用变体均成功编译后被指定断言拒绝；后三项仅在任务运行阶段故意省略Client输入flush、CPU结果invalidate或控制页读取invalidate，分别触发精确页数/完成期限检查。检查器要求退出-6、Assertion及匹配的拒绝原因，编译失败、普通崩溃或ASan/UBSan错误不计成功。正常代码保留O2、断言和ASan/UBSan。

```bash
python3 scripts/check/check-gpu-rsi-memory-chain.py --task-chain \
 --out build/rmm-client-bo-20261030/task-memory-chain-dn/targeted
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 \
 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/task-memory-chain-dn/private-suite \
 bash scripts/check/check-rmm-gpu-private.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
```

以上均退出0。最终完整套件使用指定拒绝原因的检查器，621为这一轮的PASS标记数；不与独立验证或历史套件累加。日志位于`build/rmm-client-bo-20261030/task-memory-chain-dn/{targeted,private-suite,patches}.log`，两个chain检查器的实际编译命令、调用参数、退出码、正常场景及错误断言保存在`private-suite/rsi-{memory,task}-chain-1689900/`。Python语法、shell语法和父仓库/嵌套RMM的diff检查通过。

保留夹具失败：`initial/`和`diagnostic/`中任务BO未授EXEC，实际MAP_AUTHORIZE正确拒绝，已修正测试权限；`exec-access/`记录早期正常链与12个变体；`fault-cases/`因测试仍在编译时修改共享夹具而主动停止（退出130），不作为最终稳定输入结果。固定源码后，`targeted/`与最终完整套件均重新验证。控制机未安装gdb，改用RSI操作/身份/返回状态诊断，没有安装额外依赖。

最终源码、未变运行载荷与本轮证据哈希见`private-rsi-task-chain-checkpoint.json`，源码快照为`private-rsi-task-chain-source/`；本地需求审计已追加DN。当前运行包仍为`private-running-check-candidate/`与`firmware-private-running-check/`，RMM ELF SHA仍为`adc768a3745c66fcb9306782e361653eb1db005ea38e1341c57aa6f261b1cad4`。最新板端核验继承DK，893分继承DA历史run，本轮没有重新核验板端或测量GPU。

DN补齐了完整任务RSI链的主机模型覆盖。真实GPU完成eventfd、AE VM_BIND EBUSY、完整720p≥1000、广泛API/ML/多Client、恶意Client/Proxy/并发REC/撤销/旧映射实机负例仍未验收，实体GPT/GPC与平台保护边界也未由本模型证明。

## DO：DA运行路径的START调用位置诊断，889分，恢复DA893（2026-11-01）

统一记录：定位重复START检查的实际调用者及累计成本｜DA历史893→DO诊断889｜-4分/-0.45%｜仅RMM增加诊断，Client/Proxy/Host/initrd/runner与DA冻结输入一致，O2 Debug及断言保留，单Client完整720p、GPU实际594MHz、CPU未锁恒频｜部署`private-start-sites-fw-20261101-do`退出0，完整测试`private-heap-720-20261101-do`退出1，日志回收与DA恢复核验退出0｜诊断不作为优化保留；1000门槛FAIL，整体目标未完成。单轮分差不证明提速或计时无扰动。

**实现与验证。** 在原有10个`task_start()`调用位置外包独立物理计数器计时，统计次数、累计/最大耗时及成功/未完成/错误分类。原`task_start()`函数体保持逐字一致，计数不参与授权、设备推进或完成判断。报告在成功销毁group后输出，含预热与校验；每份累计快照输出三次，由严格解析器要求至少两份完整独立记录一致，不从破损行拼接统计。报告有额外串口与间隔成本。

诊断关闭/开启后的既有后端模型输出与原基线逐字一致；独立模型时钟及回绕、全部10个调用位置和分类检查通过，4个成功编译的错误变体由指定断言拒绝。实际RSI报告出口及16项解析检查通过。本轮没有因诊断再扩展完整私有模型套件，也不把已有621条PASS写成重新运行。构建首轮失败、重试、全部命令与日志保留于`start-sites-do/`，最终ELF/BSS/布局/FIT及补丁清单检查通过。

**测量结果。** 完整33场景、计算预热、VM退出0/0、Host健康、资源恢复及11份日志SHA核验通过；validation为26成功/1既有数值例外/6无判据。CPU SIGNAL/eventfd冒烟不证明真实GPU完成eventfd。最终接受207份完整帧、69组重复一致快照，拒绝记录数0；最后累计退休339853批，START共5134256次，约15.107次/累计退休批、103.372µs/累计退休批，错误分类0次。

| START调用位置 | 次数/累计退休批 | 包含等待的µs/累计退休批 | START计时占比 |
| --- | ---: | ---: | ---: |
| 3：`gpu_firmware_task_start` | 3.398 | 21.957 | 21.24% |
| 5：`task_observe` | 2.437 | 19.428 | 18.79% |
| 6：`task_observe` | 2.437 | 16.746 | 16.20% |
| 0：`task_revalidate_idle` | 1.936 | 13.225 | 12.79% |
| 1：`task_revalidate_idle` | 1.936 | 11.847 | 11.46% |
| 2：`gpu_firmware_task_ready_launch` | 1.000 | 8.365 | 8.09% |
| 8：`gpu_firmware_task_drain` | 0.969 | 5.831 | 5.64% |
| 7：`gpu_firmware_task_drain` | 0.969 | 5.801 | 5.61% |
| 9：`task_finish_by_suspend` | 0.027 | 0.171 | 0.17% |
| 4：`task_quiesce` | 0.000 | 0.000 | 0.00% |

按函数合并，`task_observe`两侧约占START计时34.99%，`task_revalidate_idle`两侧约占24.25%，公开`gpu_firmware_task_start`包装器约占21.24%，DRAIN两侧约占11.25%，实际READY启动约占8.09%。因此，大多数START调用是在重验已经启动的任务，不是再次启动GPU。包装器也由`heap_live()`及发布路径内部调用，不能把该行3.398次/退休批全部算作跨Realm RSI；若继续细分，需要区分这些直接调用者。`task_quiesce`位置本轮未命中，只说明该工作负载采用已有预检查传递路径，不证明该位置可以删除。

这些是累计、包含子调用和设备等待的墙钟计时。不能与其他FINISH/刷新阶段直接相加，也不能当作纯CPU成本；累计退休批包含预热/校验，不能直接当作33场景的帧数或某个任务的延迟。计时位置改变代码布局且报告增加开销，单轮分数不能证明计时中性。完整分场景与Client阶段对照见`scene-comparison.json`和`phase-comparison.json`。

**下一步边界。** 先根据高占比调用者区分设备推进等待、配置/根检查与stream扫描，再确定能够保持新鲜性和全部错误条件的复用边界。本轮仅提供调用位置证据，没有证明某次重验可以删除；已撤回的轮询、快照、同次RSI缓存等实验仍需按[实验索引](GPU_PRIVATE_OPTIMIZATION_DECISION_INDEX.md)查重。

**恢复与证据。** 恢复前核验143项诊断输入未被更改，仅撤回3项临时生产源码修改，逐项匹配143项DN后本地输入。通过独占重启入口将`firmware-private-running-check/`写回实际SD2，随后读取两段固件实际字节及四项Guest输入校验SHA，恢复run-id为`private-start-sites-restore-20261101-do`、退出0。当前运行包仍为`private-running-check-candidate/`与DA固件；893引用DA历史测量，恢复后未新增GPU测量。收尾文档整理未改运行代码，无新增性能测量。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-do -- \
 python3 build/rmm-client-bo-20261030/start-sites-do/run-with-uart.py \
 --images build/rmm-client-bo-20261030/private-running-check-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-start-sites-evidence-20261101-do -- \
 python3 build/rmm-client-bo-20261030/start-sites-do/pull-evidence.py
python3 scripts/maintenance/lab-run.py --run-id private-start-sites-restore-20261101-do --allow-rk-reboot -- \
 python3 build/rmm-client-bo-20261030/start-sites-do/restore-checked.py
```

证据位于`build/lab-runs/<上述run-id>/`、`build/firmware-runs/<部署或恢复run-id>/`及`build/rmm-client-bo-20261030/start-sites-do/`。关键文件为`candidate-inputs.json`、`model-summary.json`、`parser-checks.json`、`hardware.json`、`parsed-profile.json`、`profile-summary.json`、`final-runtime.json`和`checkpoint.json`。原目标中的多Client实体隔离、真实GPU完成eventfd、AE VM_BIND EBUSY、广泛API/ML、恶意并发/撤销/旧映射等未完成项保留；RK模拟不证明实体GPT/GPC拒绝。

## DP：START重试仅读取实际检查的输入，895分，撤回并恢复DA893（2026-11-01）

统一记录：减少已启动任务START重验中的无用输入复制｜DA历史893→DP895｜+2分/+0.22%｜仅RMM运行输入变化，同Client/Proxy/Host/initrd/runner，O2 Debug及断言保留，单Client完整720p、GPU实际594MHz、CPU未锁恒频｜部署`private-replay-input-fw-20261101-dp`退出0，完整测试`private-heap-720-20261101-dp`退出1，日志回收与DA恢复核验退出0｜未达预设902保留线，撤回运行优化、保留测试；1000门槛FAIL，整体目标未完成。单轮与历史对照不足以证明稳定收益。

**候选与查重。** DO测得START约15.107次/累计退休批，多数用于已启动任务重验。DP不删除START或缓存检查结论，只在`task->start_attempted`时读取当前实际使用的五个输入字：global[0/2]、CSG[0/2/20]，代替完整global 136字节和CSG 88字节快照。首次启动仍完整读取、更新并发布输入；重试仍不再次发布。输出失效与读取、实际配置/根、全部stream、ACK/错误、归属、停止与退休检查不变。全文件对照确认这是唯一生产修改，无ABI变化。此前BT在OBSERVE内复用配置/根证明，706→707后撤回；DP保留每次新鲜检查，仅精简输入拷贝，边界不同。

**本地验证。** 新checker链接实际平台、私有核心和固件，以既有后端模型54次注入、每次56项检查，合计3024项；逐个破坏五个有效输入要求拒绝与隔离，逐个修改其余51个字要求保持接受、无重新发布、任务/组不变。每个拒绝后只在模型中恢复故障，不能当作生产隔离恢复机制。DA参考与候选完整输出逐字一致；五个删除检查的变体全部成功编译后，由指定断言拒绝（退出-6），不把编译错误或sanitizer故障算拒绝。实际平台/核心/RSI运行检查退出0，完整私有套件退出0、622条PASS标记。这些是主机模型，不证明真实并发或实体GPT/GPC。

RMM O2 Debug构建及断言、23份编译flags、ELF/BSS/布局/FIT与补丁清单检查通过。实际AArch64反汇编确认重试跳过两段复制循环，仅读取五个输入字并存入栈，首次34字和22字复制循环保留。这证明生成代码减少操作数，不证明端到端性能收益。开发中两次checker失败分别涉及变体替换范围和预期注入次数，均已修正；`models.log`、`models-reviewed.log`原样保留，最终验证见`models-final.log`与其summary。

**实测与判定。** 完整33场景、计算预热、VM退出0/0、Host健康、资源恢复及11份日志SHA核验通过；validation为26成功/1既有数值例外/6无判据。blur157≥141、terrain27≥25、5×5 effect2d733≥658，场景门槛通过；895低于预设902保留线和整体1000门槛。CPU SIGNAL/eventfd冒烟不证明真实GPU完成eventfd。累计退休批341576，COMPLETE worker约2.469次/退休批，对照约2.462；PREPARE和COMPLETE累计墙钟均略减，但包含等待、预热/校验且退休批不同，不能直接归因为复制开销。完整场景与阶段数据保存在`scene-comparison.json`、`phase-comparison.json`。

**撤回与当前状态。** 先核验145项冻结输入，仅将生产`opencca_gpu_firmware.c`恢复DA参考；新增测试头、checker及套件入口保留，DA参考已通过同一新检查。通过独占重启入口写回`firmware-private-running-check/`，读取实际SD2两段固件字节、核验四项Guest输入并检查Host恢复，退出0。运行包仍为`private-running-check-candidate/`；893引用DA历史结果，回退后无新增GPU测量。收尾文档整理未改运行代码，无新增性能测量。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/replay-input-dp/private bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-replay-input.py --out build/rmm-client-bo-20261030/replay-input-dp/models-final --reference build/rmm-client-bo-20261030/replay-input-dp/before/opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c --mutants
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-dp -- \
 python3 build/rmm-client-bo-20261030/replay-input-dp/run-with-uart.py \
 --images build/rmm-client-bo-20261030/private-replay-input-dp-candidate \
 --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-replay-input-evidence-20261101-dp -- python3 build/rmm-client-bo-20261030/replay-input-dp/pull-evidence.py
python3 scripts/maintenance/lab-run.py --run-id private-replay-input-restore-20261101-dp --allow-rk-reboot -- python3 build/rmm-client-bo-20261030/replay-input-dp/restore-checked.py
```

证据位于`build/rmm-client-bo-20261030/replay-input-dp/`、`build/lab-runs/<上述run-id>/`及`build/firmware-runs/<部署或恢复run-id>/`。主要文件为`plan.json`、`candidate-inputs.json`、`local-checks.json`、`equivalence.json`、`assembly.json`、`hardware.json`、`final-runtime.json`与`checkpoint.json`；构建验证位于父目录`private-replay-input-dp-build-validation.json`。AE VM_BIND EBUSY、真实GPU完成eventfd、完整720p≥1000、广泛API/ML/多Client、恶意Client/Proxy与并发撤销/旧映射等实机验收继续未完成，RK模拟不证明实体GPT/GPC。

## DQ：实际RMI控制/撤销接入双Client任务内存链（2026-11-01）

统一记录：验证复位结果与私有任务/页表撤销之间的实际接线｜当前运行DA历史893→本轮未测｜分差/百分比未测｜只改任务链、内存链fixture与checker三个验证文件，未改运行代码，无新增性能测量，无部署或板端操作｜完整私有套件命令见下，退出0，624条PASS，证据`rmi-revocation-dq/private-final.log`｜保留验证；1000门槛及整体目标未完成，不能继承为实体安全通过。

**补齐的边界。** DN任务链在复位时直接调用底层设备控制和两个撤销函数，没有经过实际RMI GPU PM适配器。DQ原样提取生产`smc_opencca_gpu_pm()`、`handle_rsi_opencca_gpu_control()`和`opencca_gpu_private_device_revoked()`，在既有RSI/端点/输入副本/IPA翻译/私有PT/xshm_rtt/七项实际内存回调的同一链中执行。适配器使用实际GPU控制状态机、平台复位代码和私有/固件撤销实现；物理寄存器、复位完成信号、REC/RTT、锁、缓存及TLBI仍为模型。外层RMI dispatcher未链接，公共policy gate由fixture模拟，不宣称验证其锁范围或真实并发。Host PRIVATE_RECLAIM在此为显式陷阱替身、没有执行，不将它计为覆盖；既有独立回收checker继续运行。

**五个场景。** 原有成功及完成读取后根/stream故障三场景，改为经过实际PM适配器复位，私有RSI请求仍分别177/179/179次，额外各执行1次RMI。新增场景3以两个Client已启动任务为起点：Client0、Client1与隔离Proxy通过旧GPU_CONTROL RSI请求RESET均拒绝；Host的非零参数/错误值不引起MMIO或缓存副作用。软、硬复位都失败后设备隔离，两个context与BO不能销毁，真实PTE保留，控制arena不能回收，Client数据不归还、Proxy不恢复原始MMIO。随后硬件复位恢复成功，QUARANTINED状态仍不开放服务，最后通过既有RELEASE完成撤销；179次私有RSI、5次RMI及3次RESET RSI全部执行。

场景4验证MEDIATED状态下成功RESET：实际适配器撤销私有映射、任务与固件状态，旧GROUP_INSPECT与TASK_VALIDATE拒绝，两个context与BO随后才能释放。513页控制arena按512+1预算清零后恢复WB；重新加载固定固件，在同一批物理页上为两个Client新建context/group/task并重建实际GPU PT。旧token配新context、新token配旧context/group、旧完成请求及旧映射请求均拒绝，且不产生MMIO、clean或invalidate副作用；新任务仍能启动、得到正确归属的输出并完成清理。此场景289次私有RSI、4次RMI、3次RESET RSI。它验证顺序撤销/复用，不证明并发REC或实际shader执行。

**错误变体与完整验证。** 原15项变体继续通过；新增5项分别移除私有撤销、移除固件状态清理、在复位失败时错误撤销、忽略Host error字段、将Realm RESET当作Host请求。20个变体均成功编译，再由指定断言拒绝（退出-6）；编译错误、超时和sanitizer故障不计为拒绝。完整套件退出0，624条PASS；终端任务链summary共25条执行记录（5成功场景+20错误变体）。场景覆盖和命令/退出码见`verification.json`，编译及逐场景日志见`private-final/rsi-task-chain-*/`。首轮扩展失败发生在第二次固件配置：fixture仍启用队列domain ACK模型，已修正为先执行MCU启动配置模型，生产实现未改；`actual-first.log`和失败场景日志保留，修正后快速五场景通过。首轮完整套件在skip-firmware变体被另一个断言拒绝时退出1，已增加不依赖private context的GROUP_INSPECT断言，捕获未撤销的固件group；原private.log保留，重新冻结后完整套件通过。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/rmi-revocation-dq/private-final bash scripts/check/check-rmm-gpu-private.sh
# 调试时可只运行实际源码场景；此选项不执行错误变体，不能代替完整套件。
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-rsi-memory-chain.py --task-chain --actual-only --out <新的证据目录>
```

**保留状态与未完成项。** 冻结并核验145项输入，三个验证文件发生变化，实际运行包和DA固件逐字节保持；本轮未连接Pi/RK进行新测量，不把上一轮恢复证据写成本轮硬件验收。证据目录`build/rmm-client-bo-20261030/rmi-revocation-dq/`，包括`plan.json`、`candidate-inputs.json`、三个diff、`verification.json`与`checkpoint.json`。当前运行仍为`private-running-check-candidate/`、`firmware-private-running-check/`，893仅为DA历史结果。实体GPT/GPC、实际GPU完成eventfd、AE VM_BIND EBUSY、完整720p≥1000、广泛API/ML/多Client、恶意Proxy/Client以及真实并发撤销/旧映射攻击验收仍未完成。

## DR：实际Host PRIVATE_RECLAIM接入双Client任务内存链（2026-11-01）

统一记录：补测任务已启动后死亡Realm的真实回收入口｜当前DA历史893→本轮未测｜分差/百分比未测｜仅改三个验证文件，未改运行代码，无新增性能测量，无部署或板端操作｜完整私有套件退出0，626条PASS，命令/逐场景退出码见`dead-owner-chain-dr/verification.json`｜保留验证；1000门槛、实体隔离及整体目标仍未完成。

DQ的同链验证将PRIVATE_RECLAIM设为陷阱替身。DR改为原样提取生产`opencca_gpu_private_reclaim()`，由实际`smc_opencca_gpu_pm()`调用，继续贯通实际私有核心、RSI、端点、输入复制、IPA翻译、GPU页表及七项内存回调。fixture新增明确的RD物理地址查找与RD状态/REC计数模型；没有修改生产代码，也没有链接完整RMI dispatcher、真实REC创建/销毁或并发锁实现。

在原五场景之外，新增场景5/6都从两个Client已启动任务开始，分别模拟Client0或Proxy停止并销毁最后一个REC。先拒绝未对齐RD、DATA地址冒充RD、Host非零error、仍有REC、零REC但NEW状态、未撤销设备及失败RELEASE后的回收；拒绝不改变MMIO、缓存操作数、TLBI或实际RTT描述符。失败RELEASE后实际GPU Client PTE仍保留。随后可信RELEASE成功，在REVOKED状态下重新独立检查REC计数与NEW状态，避免另一个拒绝条件掩盖失效检查。

- 场景5：ACTIVE且零REC的Client0才允许回收；销毁它的实际context/BO并拒绝旧FINISH，保留存活Client1的注册与DATA归属，随后通过存活Client的正常接口清理其对象。168次私有RSI、12次RMI，其中10次回收请求。
- 场景6：SYSTEM_OFF且零REC的Proxy回收513页控制arena，先处理512页并返回INCOMPLETE，最后一页保持隐藏，下一次完成清零及CPU映射恢复。逐字节核验device backing为零；两个存活Client的BO注册保留。额外直接调用实际核心检查旧服务RD指针不能再inspect它们的BO/context，独立于外层设备状态拒绝；这不是完整RD销毁/重建实验。167次私有RSI、13次RMI，其中11次回收请求。

两场景都没有FINISH成功或CPU数据归还，普通Client数据仍保持提交前CPU内容，不把撤销当作任务成功。控制页的RTT恢复与清零使用实际函数；DATA granule refcount不是此BO注册机制的引用来源，存活注册通过实际private BO范围查询和DATA状态验证，不能表述成新增物理页pin证明。

新增五个成功编译的错误变体：忽略REC计数、允许NEW状态回收、不清理BO服务身份、不清理context服务身份、任务启动后跳过控制页清零。全部由指定断言拒绝（退出-6），而非编译错误、超时或sanitizer错误。加上原20变体，共25个；7个正常模型场景通过，完整私有套件626条PASS。原首轮快速验证错误地假定DATA refs=1，已根据实际代码修正为注册保留/DATA状态检查；失败`actual-first.log`保留。首轮完整套件在未清理BO服务身份变体被整体回收完成断言提前捕获时退出1；已将BO/context身份探针前移到最终回收状态判定之前，防止另一个保护条件掩盖身份检查，保留`private.log`后重新冻结并重跑完整套件，`private-final.log`退出0。随后加强REC/NEW变体的独立性：撤销前只要求拒绝且无副作用，不按错误码差异提前捕获，让变体确实进入撤销后的身份检查；最终重新冻结并完整重跑，`private-terminal.log`退出0。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/dead-owner-chain-dr/private-terminal bash scripts/check/check-rmm-gpu-private.sh
```

补丁清单与主/组件`git diff --check`退出0。证据目录`build/rmm-client-bo-20261030/dead-owner-chain-dr/`保存前后源码、冻结输入、失败日志、完整套件及变体日志、`verification.json`与`checkpoint.json`。本轮未连接Pi/RK；运行包`private-running-check-candidate/`及`firmware-private-running-check/`的17项文件与DQ冻结哈希一致，不据此新增板端恢复证明。实际GPU完成eventfd、AE VM_BIND EBUSY、完整720p≥1000、API/ML/多Client、恶意Proxy/Client实机攻击、并发撤销/旧映射及实体GPT/GPC验收仍未完成。

## DS：START内部阶段诊断，891分，恢复DA893（2026-11-01）

统一记录：定位当前START重验的内部成本｜DA历史893→DS诊断891｜-2分/-0.22%｜仅RMM增加临时计时，Client/Proxy/Host/initrd/runner与DA冻结输入一致，O2 Debug及断言保留，单Client完整720p、GPU实际594MHz、CPU未锁恒频｜部署`private-start-phases-fw-20261101-ds`退出0，测试`private-heap-720-20261101-ds`退出1，日志回收及恢复退出0｜诊断不作为优化保留；1000门槛FAIL，整体目标未完成。单轮分差不证明稳定性能变化或计时无扰动。

DO已定位START的调用者，DS进一步在同一个`task_start()`内划分五个不重叠区间，并以进入函数时的`task->start_attempted`把首次启动与已启动token重验分为两组；它不是每个退休批必有一次的新硬件START。各段分别覆盖前置查找/身份/状态、真实AS及固件配置、global/CSG快照、global/CSG条件及全部stream扫描、最后接受分支或首次发布/应答等待。首次启动的最后一段含MCU等待，不能当CPU成本。阶段统计只记录走到检查点的区间；若函数中途失败，可能留下部分区间，`success`字段表示区间已记录，不是任务成功。各段也包含计数器和时钟的额外成本，边界不能解释成纯函数CPU计时。

三个文件去除明确记录的计时变换后，逐字还原当前基线；既有后端在基线、诊断关闭、诊断开启下的原输出逐字相同。独立时钟及回绕、十个区间与首次/重验分类通过；漏计次数、错误tick、错误分类及区间分类四个成功编译变体被断言拒绝。实际RSI报告出口及16项解析检查通过，共8次模型执行。未因临时诊断扩展完整私有套件，不把DR的626条PASS计作本轮重跑。23份构建flags与基线一致，布局/BSS/FIT及补丁清单通过。

完整33场景、计算预热、validation26成功/1既有数值例外/6无判据、VM退出0/0、Host健康及资源恢复通过，11份日志SHA核验。CPU SIGNAL/eventfd冒烟不证明真实GPU完成eventfd。UART接受207份完整帧、69组至少两份独立完整记录一致的快照，拒绝记录0；最后累计退休340235批，首次启动接受10933次、已启动重验接受5124187次，区间计数平衡=True。该统计包括预热和校验，不是单一benchmark区间或每任务时延。

| 已启动token重验的区间 | 区间次数/累计退休批 | µs/区间调用 | µs/累计退休批 | 重验区间时间占比 |
| --- | ---: | ---: | ---: | ---: |
| 真实运行AS、根与固件配置检查 | 15.061 | 3.117 | 46.950 | 45.87% |
| global/CSG条件与所有stream检查 | 15.061 | 2.653 | 39.962 | 39.05% |
| global/CSG缓存维护与快照复制 | 15.061 | 0.833 | 12.552 | 12.26% |
| 对象查找、身份与状态前置检查 | 15.061 | 0.136 | 2.045 | 2.00% |
| 重验接受分支及返回前处理 | 15.061 | 0.056 | 0.836 | 0.82% |

已启动重验区间累计102.345µs/退休批，首次启动五段累计2.694µs/退休批。不能与DO或CZ的不同运行直接相加，也不能据此宣称等量优化收益。下一步优先细分运行AS/配置检查中的平台MMIO与私有核心成本，研究同一可信事务内的检查边界；不能直接缓存跨调用的根证明或省略动态故障检查，BT/DI已有撤回记录。完整首启/重验十行及逐场景变化见`profile-summary.json`、`scene-comparison.json`；没有新增可保留的运行优化。

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ds -- python3 build/rmm-client-bo-20261030/start-phases-ds/run-with-uart.py --images build/rmm-client-bo-20261030/private-running-check-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-start-phases-restore-20261101-ds --allow-rk-reboot -- python3 build/rmm-client-bo-20261030/start-phases-ds/restore-checked.py
```

诊断源码与固件保存在`build/rmm-client-bo-20261030/start-phases-ds/`及`firmware-private-start-phases-ds/`。恢复核验145项原输入、四项板端Guest输入及实际SD2固件字节；当前仍为`private-running-check-candidate/`、`firmware-private-running-check/`。893仅引用DA历史成绩，没有恢复后新GPU测量。多Client、API/ML、GPU完成eventfd、AE绑定错误、恶意Proxy/Client与真实并发/旧映射攻击及实体GPT/GPC验收未完成。

## DT：缓存包装函数去除重复DSB，895分，撤回恢复DA893（2026-11-01）

统一记录：减少RMM缓存维护包装函数的重复屏障及返回开销｜DA历史893→DT895｜+2分/+0.22%｜仅RMM的两个包装函数变化，Client/Proxy/Host/initrd/runner保持DA冻结输入，O2 Debug/全部断言保留，单Client完整720p、GPU请求600/实际594MHz，CPU未锁恒频｜部署`private-cache-wrapper-fw-20261101-dt`退出0，测试`private-heap-720-20261101-dt`退出1，回收`private-cache-wrapper-evidence-20261101-dt`及恢复`private-cache-wrapper-restore-20261101-dt`均退出0；准确命令及日志见`build/rmm-client-bo-20261030/cache-wrapper-dt/*-command.json`、`*-exit.json`、`*.log`｜**未满足预设保留条件，撤回；1000门槛FAIL，整体目标未完成。** 单轮分差不证明稳定因果收益或退化。

**改了什么。** `runtime/rsi/opencca_gpu_private.c`的`clean()`、`invalidate()`原先在调用缓存范围维护函数后再执行`DSB SY`，而实际`cache_helpers.S`对非零范围已在末尾执行同等屏障。DT对非零范围直接调用原函数，零长度仍单独执行屏障。保持原缓存范围、所有调用顺序和新鲜读取；没有缓存跨调用结果，没有减少根、AS、配置、全部stream、错误、真实完成或资源释放检查。与BO的多stream维护合批不同，本轮无地址数组、无合批边界，局部编译结果允许尾调用；与AO不同，本轮不改MMIO或寄存器读取排序。

**本地证据。** 实际新旧包装函数各执行18,440个非一致性缓存模型场景，覆盖32/64/128/256字节缓存行、全部256种行内起点、1–4096字节选定长度及NULL/零长度屏障。缓存动作先排队、完成屏障才生效，独立检查修改范围及范围外数据；零长度调用必须提交此前无关待完成操作。六个错误变体均成功编译后被指定断言拒绝：遗漏clean、遗漏invalidate、缩短范围、遗漏零长度clean/invalidate屏障、底层函数丢失完成屏障。模型不模拟物理cache、TLBI、GPC或并发。

实际AArch64目标文件与链接镜像核查：非零范围由两次完成屏障降为一次，零长度保持一次；两个包装函数尾调用原缓存函数。实际两个底层函数的代码段各60字节与DA逐字一致，入口CBZ、全部DC循环及末尾DSB保留。初次校验误比较包含构建目录调试信息的整个目标文件，第二次误选空`.text`节，均记录失败；改为比较实际`.text.asm.*`代码段后通过，没有将校验脚本失败计为PASS。

完整私有套件本轮重跑退出0，626条PASS；后端守卫退出0，4288条PASS标记，不能将标记数量解释为同等数量独立安全场景。23份flags与原基线一致，Debug/断言、FIT和含BSS布局及上游补丁清单通过。候选RMM ELF SHA为`dc56fbf88d83e38fba0b0d383216ff35bfb249b9d44b4649c3dc12e8a32cbc48`。

**实测及回退。** 完整33场景、计算预热、validation26成功/1既有数值例外/6无判据、VM退出0/0、Host健康/资源恢复及11份日志SHA通过。场景保护为blur≥141、terrain≥25、5×5 effect2d≥658，本轮分别156/27/729FPS，保护判定True；预设分数保留线902，未事后降低。局部指令减少没有形成满足保留线的整机结果。逐场景及阶段数据分别见`scene-comparison.json`、`phase-comparison.json`，阶段含Guest/RMM及等待，不是纯CPU profile。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/cache-wrapper-dt/private-terminal bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-dt -- python3 build/rmm-client-bo-20261030/cache-wrapper-dt/run-with-uart.py --images build/rmm-client-bo-20261030/private-running-check-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-cache-wrapper-restore-20261101-dt --allow-rk-reboot -- python3 build/rmm-client-bo-20261030/cache-wrapper-dt/restore-checked.py
```

只恢复本轮两处包装函数，候选源码、模型、固件和失败门槛证据保留于`cache-wrapper-dt/`、`firmware-private-cache-wrapper-dt/`。恢复145项原输入、四项板端Guest哈希及实际SD2字节，Host为`6.12.0-opencca-pmthor-opp3`、CPU0–1/pmthor，无本轮进程或loop残留。提前两次只读tail因日志尚未生成失败，后续完整取证成功，未作为workload失败或PASS证据。

产物管理：在独占run `private-cache-wrapper-cleanup-20261101-dt`再次核验DA实际SD2与Guest输入后，只移除Pi上本轮部署/回退的两个重复目录、四个固件文件。逐项校验控制机副本SHA、大小、mtime及无进程占用，精确删除清单与结果见`pi-cleanup.json`；控制机候选、失败证据、回退与部署前启动区备份保留。

当前仍为`private-running-check-candidate/`与`firmware-private-running-check/`；893引用DA历史实测，没有恢复后新GPU测量。CPU SIGNAL/eventfd冒烟不证明真实GPU完成eventfd。AE VM_BIND EBUSY、多Client、API/ML、恶意Proxy/Client、并发撤销、旧映射复用及实体隔离仍未验收。下一步应重新审视可信事务中的重复观察/调度路径，以当前分段证据评估机制变化；不再仅凭屏障或操作数减少重复AO/BO/DT。

## DU：真实RMI销毁策略与Realm销毁链，630条PASS（2026-11-01）

统一记录：补齐私有GPU回收后RD销毁和身份地址复用的跨模块验证｜对照DA历史893→本版未测、分差及百分比N/A｜只改验证代码，Host/Client/Proxy/RMM运行代码和冻结载荷不变，未改运行代码，无新增性能测量｜下面完整私有套件退出0，日志`build/rmm-client-bo-20261030/realm-lifecycle-du/private-final.log`；无硬件run-id，本轮未连接Pi/RK｜保留验证，整体目标未完成，1000门槛仍未通过。

DR已连通实际PRIVATE_RECLAIM，但其RD/REC状态由夹具提供，未执行真正的`smc_realm_destroy()`。DU增加独立`--realm-lifecycle`模式，在原双Client任务/实际内存回调链上，原样提取并执行`xshm_rmi_allowed()`、`smc_realm_destroy()`、`total_root_rtt_refcount()`、`free_sl_rtts()`、GPU PM销毁检查/映射释放及`opencca_xshm_release_realm()`；事件端点、通道和GPU对象仍链接实际核心。独立模式由完整套件显式调用，旧七种任务链场景继续运行，没有替换既有覆盖。

两个新场景分别销毁Client和Proxy。每个先完成实际RSI固件/控制页/Client私有页表及两Client任务启动，再执行可信设备撤销和死主体回收，最后调用实际RMI策略和销毁体。Client路径169次RSI、2次PM/回收；Proxy路径169次RSI、3次PM/回收，513页控制内存仍按512+1回收。

| 独立检查 | 通过条件 |
| --- | --- |
| 私有登记还存在、或控制页只回收部分 | REALM_DESTROY策略拒绝，不触碰granule、VMID、设备或端点；不靠REC/RTT后续拒绝掩盖缺失守卫 |
| 私有登记已清除 | 共享/IOMMU归属守卫仍分别生效；现存REC在遍历RTT前拒绝，非空根RTT在释放VMID前拒绝 |
| 销毁成功 | 释放正确VMID，调用RD/三个根RTT的清零原语后才能转为DELEGATED，旧GPU owner和事件端点解除 |
| 旧事件与通道 | 预先绑定IRQ、置入真实端点核心的pending事件；销毁后旧端点、IRQ状态和旧通道查询/通知权限失效 |
| 相同RD地址的新身份 | 模型重新分配RD/REC，实际端点注册获得递增ID；显式建立新通道仍不能恢复旧BO/任务权限，不继承旧IRQ状态 |
| 无关Client | 保留其端点、数据登记；Client死亡路径中，另一Client的原通道继续可查询；不伪造GPU成功完成 |

八个错误变体均成功编译后由指定断言拒绝：删私有登记策略、绕过unused-RD/REC检查、忽略根RTT引用、删事件端点释放、删GPU归属释放、漏RD清零、漏根RTT清零、保留旧通道。编译失败、ASan/UBSan错误、普通崩溃不计为检出。初步变体集通过后，加入无关Client通道仍可用的断言，再执行完整套件；最终630条PASS标记（原626加两个场景各两条），不是630个独立安全场景。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/realm-lifecycle-du/private-final bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-rsi-memory-chain.py --realm-lifecycle --out <新的证据目录>
```

保留两次夹具失败：首次静态函数与公开声明冲突，第二次把REGISTER的ABI版本返回位误当endpoint ID；修正夹具而未放宽生产检查，`actual-first/`、`actual-second/`及日志保留。最终来源与准确编译/执行参数在`private-final/realm-lifecycle-*/summary.json`；五个验证文件的准确差异在`change.patch`，完整验证结论在`verification.json`。补丁清单、主仓库/组件diff空白检查通过。

边界：这不是实机RD销毁/重建。外层RMI dispatcher与策略锁仍为模型；执行了实际销毁函数和策略，但RD重新分配未运行`smc_realm_create()`。REC引用、Host RTT拆除、RD/RTT布局、清零原语、cache/TLBI、设备MMIO和并发仍由夹具模拟，不证明实体GPT/GPC或实际中断注入。当前运行包/固件的17项SHA与DT最终核验相同，本轮未连接板端、部署或进行新GPU测量，不继承一次新的硬件PASS。

当前仍为`private-running-check-candidate/`与`firmware-private-running-check/`，893仅为DA历史成绩。真实GPU完成eventfd、AE VM_BIND EBUSY、完整720p≥1000、API/ML/多Client、恶意Proxy/Client、真实并发撤销/旧映射及实体隔离验收仍未完成；整体目标保持active。

## DV：运行AS检查细分诊断，891分，已恢复DA893（2026-11-01）

统一记录：定位RMM可信路径的运行AS检查成本｜DA历史893→DV诊断891｜-2分/-0.22%｜只在RMM四个文件增加临时计时/聚合报告，构建仅额外定义GPU_RUNNING_PROFILE；O2 Debug及断言保留，Client/Proxy/Host/initrd/runner与DA相同，GPU实际594MHz、CPU未锁恒频｜部署`private-running-cost-fw-20261101-dv`退出0，完整720p `private-heap-720-20261101-dv`退出1，证据回收和恢复退出0｜仅诊断，全部临时源码和实际SD2固件已恢复DA，不能作为优化保留；1000门槛FAIL，整体未完成。

DS将START重验划分为五段，但“运行AS/配置”仍混合了内部元数据和真实平台访问。DV进一步对实际`gpu_private_context_check_running()`及`plat_opencca_gpu_pt_check_running()`计时，所有身份/归属、真实根/属性、固件/拓扑和末尾动态故障检查保持原顺序。计数不参与授权、完成或回收；仅成功走完的区段计入，失败调用可能只贡献部分区段。统计覆盖所有调用者，并非仅START重试，不与DS不同运行的区间直接相减。

| 完成区段 | µs/次 | µs/累计退休批 | 五段计时占比 |
| --- | ---: | ---: | ---: |
| RMM上下文/归属元数据前检 | 0.090 | 1.369 | 2.96% |
| 固件运行根、配置及拓扑 | 1.800 | 27.245 | 58.95% |
| Client实际AS根及属性 | 0.740 | 11.206 | 24.25% |
| 动态MCU、MMU/GPU故障及计时器末检 | 0.397 | 6.015 | 13.02% |
| RMM内部结果写回 | 0.025 | 0.379 | 0.82% |

完整快照207份、重复一致快照组69组；最终一致序号[205, 206, 207]，RMM累计退休340520，覆盖Client最终340188批。各区段调用计数一致：True。聚合区段合计46.215µs/累计退休批；排除mapping锁包装、回调派发和计时点之间的空隙，包含计时扰动及潜在设备等待，且含预热/validation。它不是纯CPU时间、逐任务审计，也不证明诊断无扰动或单轮分差是稳定性能变化。

完整33场景、validation26/1/6、VM0/0、计算预热正确性、CPU SIGNAL/eventfd/basic、内核健康与资源恢复检查通过；1000门槛单独判定。11份运行证据SHA全部核验。真实GPU完成eventfd未执行。源码/硬件证据目录`build/rmm-client-bo-20261030/running-cost-dv/`，命令、退出码分别在`*-command.json`和`*-exit.json`；模型/测量/解析结论分别为`validation.json`、`hardware.json`、`profile-summary.json`。

```bash
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/running-cost-dv/private-terminal bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 python3 build/rmm-client-bo-20261030/running-cost-dv/check-models.py --out <新的证据目录>
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-dv -- python3 build/rmm-client-bo-20261030/running-cost-dv/run-with-uart.py --images build/rmm-client-bo-20261030/private-running-check-candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

本地完整私有套件630条PASS标记、后端检查和补丁清单通过；启用诊断的实际平台/核心及RSI模型正向通过，四个成功编译的安全错误变体均由断言拒绝；15项UART完整性检查通过。前三次模型夹具编译失败保留，分别为缺报告定义、缺INFO声明、空INFO宏导致未使用变量；只修正夹具接线，没有放宽生产检查。只读监控早期缺文件及板端无rg也保留，不算GPU负载失败或PASS证据。

恢复核验149项原输入、四项Guest输入及实际SD2字节；17项运行包/固件哈希仍与DU相同。Host CPU0–1/pmthor，无本轮进程或loop残留。Pi本轮部署/回退的两个重复上传目录在独占清理run中按SHA、大小、mtime和占用检查精确删除，控制机诊断源码、固件、启动区备份及失败证据保留。当前运行仍为`private-running-check-candidate/`和`firmware-private-running-check/`；893仅引用DA历史成绩，恢复后无新GPU测量。

后续优先研究为什么同一任务生命周期反复进入配置/AS验证，以及可由可信写入边界约束的事务合并；不据这份局部计时直接删除真实根、动态故障或读后重验，不重做BT/DI已撤回机制。完整720p≥1000、AE VM_BIND EBUSY、真实GPU完成eventfd、API/ML/多Client、恶意Proxy/Client、并发撤销/旧映射与实体GPT/GPC验收仍未完成。

## DW：真实RMI外层分发与授权执行锁范围验证（2026-11-01）

统一记录：补齐授权检查到RMI执行之间的串行化验证｜当前DA历史893→本轮未测｜分差及百分比不适用｜只新增主机验证代码及完整套件入口，运行代码与冻结载荷不变｜run-id `rmi-dispatch-dw`；完整私有套件退出0、633条PASS，DMA/后端检查及固定补丁校验退出0；命令、退出码与日志位于`build/rmm-client-bo-20261030/rmi-dispatch-dw/`｜保留测试；未连接板端、部署或进行性能测试，1000门槛与整体目标仍未完成。

DU执行了真实授权策略和Realm销毁体，但在测试中手动拼接锁与分发，不能验证生产入口的锁范围。DW新增`runtime/tests/opencca_gpu_rmi_dispatch_test.c`及`scripts/check/check-gpu-rmi-dispatch.py`：原样提取生产分发表、日志逻辑和完整`handle_ns_smc()`，编译完整`xshm_policy.c`，直接使用生产SMC/FID、处理函数原型与状态头文件。28个叶子处理函数为明确的测试替身，用于检查分发表选中对象、所有参数位置及返回值；不将替身执行记作真实Realm或GPU操作。

FPU开/关两种配置各196项检查，均通过ASan/UBSan与全部断言：

- 所有28个已实现入口分别携带和不携带SVE hint调用；检查FID归一化、参数顺序、结果寄存器及SIMD保存/恢复配对。实际表内空洞和范围外FID返回UNKNOWN，不进入处理函数或取得策略锁。
- 对Realm销毁、DATA创建/销毁、RTT折叠/销毁和RIPAS变更，分别以共享内存、私有GPU与IOMMU占用作为唯一拒绝原因。拒绝不进入叶子，所有输出寄存器清零；另一个Client及同Client不相交的页面仍可操作。
- 生产授权查询与叶子执行必须处于同一次、未中断的持锁区间；正常返回、策略拒绝和叶子报错都释放锁。REC_ENTER在锁外执行，其测试替身可重新取得策略锁，避免把任意Realm执行包进全局gate。
- 每种FPU配置执行32次确定性双线程交错：首线程进入叶子后暂停，第二线程真实竞争同一主机互斥锁；确认其尚未进入叶子，再让首线程提交占用或释放。竞争线程随后必须按提交后的状态拒绝或放行。覆盖三类占用建立及释放，每类8次，不依赖sleep或仅检查最终计数。

12个生产代码错误变体均成功编译并被指定检查拒绝：去掉锁、忽略授权结果、只清状态寄存器、漏解锁、错误锁住REC_ENTER、授权与执行间解锁再加锁、错选RD、去掉私有owner或range守卫、交换叶子参数、不清SVE hint、漏恢复SIMD。最后一项由生产函数末尾的SIMD断言直接拒绝。完整套件再次执行同组正向及变体验证，633是套件PASS标记数，不能当作独立实体测试数量。

```bash
python3 scripts/check/check-gpu-rmi-dispatch.py --out build/rmm-client-bo-20261030/rmi-dispatch-dw/models-final
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/rmi-dispatch-dw/private-terminal bash scripts/check/check-rmm-gpu-private.sh
HOST_CC=build/rmm-client-bo-20261030/cc-debug-o2 bash scripts/check/check-dma-guard.sh
python3 opencca/scripts/setup/apply-local-patches.py --check
```

前三次夹具未完成运行的证据保留：首次因生产头文件需要GNU C方言及GRANULE_SHIFT定义而编译失败；第二次错误变体先被更早的授权连续性检查拒绝，预设错误字符串不匹配；第三次SIMD变体由生产断言拒绝，预设自定义错误字符串不匹配。修正编译接线与指定错误判据后使用新目录重跑，没有放宽生产策略或将编译失败计作安全负例通过。

边界：执行了真实外层分发和策略锁包装函数，但Arm锁原语替换为有检查的pthread互斥锁；RD/页占用判定与叶子处理、SIMD操作仍为替身。本轮与DU的真实销毁体回归分别执行，没有把两者拼成真实RD创建/销毁/重建并发证明，也没有覆盖并发REC、实际GPU任务或物理GPT/GPC。17项本地冻结运行包/固件SHA与前轮相同；未进行新的板端状态或SD回读核验。未改运行代码，无新增性能测量；893仍仅引用DA历史结果。


## DX：CPU频率策略对照，891→888，保留受控测试能力（2026-11-01）

统一记录：检查CPU自动调频是否限制私有GPU路径性能｜同轮DA运行代码，自动策略891 → 固定1.8GHz 888｜-3分/-0.34%｜同一Client/Proxy/Host/RMM/initrd、CPU绑定、完整720p和GPU实际594MHz，仅Host CPU policy0策略不同；无固件写入或重启｜run-id `private-heap-720-20261101-dx-auto`、`private-heap-720-20261101-dx-fixed`，两轮计分runner各退出1（低于1000门槛）；固定组外层还遇到收尾回执文件名冲突，独立只读补核验退出0；最终分析及日志SHA核验退出0｜保留runner受控锁频入口，运行策略恢复原值，未形成满足预设9分幅度的调优结果，不宣称代码提速或稳定因果收益。

**改动与条件。** 将runner的频率校验与CPU布局/telemetry校验分开，允许private模式完整720p/1080p性能计分使用已有`--cpu-frequency-khz`设置和恢复流程；仍拒绝非正数、ML、非performance/benchmark-only组合，私有模式仍不开放布局/telemetry。实际parser及既有runner检查共37项通过，日志`cpu-policy-dx/runner-check.log`。没有修改RMM、内核、GPU执行或完成判断。相对DA冻结包，runner还带有此前DM的未选compute-eventfd接线及NOT_RUN记录；本轮未传compute_rootfs，未执行该分支。两轮启动前均验证173项冻结输入，结束后再次核验；四项实际Guest输入和实际SD2字节各轮核对，原DA固件保持。

| 指标 | 自动策略 | 固定1.8GHz |
| --- | ---: | ---: |
| 完整720p分数 | 891 | 888 |
| 正式计分频率采样数 | 349 | 351 |
| 采到1.8GHz次数 | 349 | 351 |
| 正式计分采样最高温度℃ | 53.615 | 55.461 |
| COMPLETE调用/累计退休批 | 2.467 | 2.468 |
| PREPARE累计墙钟µs/批 | 138.584 | 138.277 |
| COMPLETE累计墙钟µs/批 | 339.169 | 339.274 |
| COMPLETE间隔µs/批 | 267.802 | 269.466 |

频率为约1秒一次的瞬时采样，使用Host墙钟/单调时钟校准以及正式GO到输出结束区间，两侧排除2秒；不能证明间隙内从不降频。阶段统计包含预热、validation、RPC/RMM和等待，不能当作正式计分纯CPU/GPU时间。固定组原始收尾核验因前后均使用candidate、同run-id文件名而拒绝覆盖；保留原始失败、缺失的benchmark-exit.json及采样进程退出码未记录状态。实际GPU runner退出码由host-kernel-health.json独立记录。随后独占`private-cpu-policy-final-20261101-dx`只读重核实际SD2/Guest输入和原CPU策略，退出0；没有重跑GPU或改写原失败。两轮完整33场景，validation均26成功/1既有数值例外/6无判据；两端VM均0/0，控制池解绑、两端日志、Host健康和CPU0–1/pmthor/loop/进程及频率策略恢复通过。各11份远端证据SHA一致。CPU SIGNAL/eventfd冒烟不代表真实GPU完成eventfd验收。

**命令与证据。** 通过一次交互凭据会话运行两次独占`lab-run.py --run-id <上述ID> -- python3 build/rmm-client-bo-20261030/cpu-policy-dx/run.py auto|fixed`；子命令为`python3 scripts/run/run-realm-xshm.py --images build/rmm-client-bo-20261030/cpu-policy-dx/candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，固定组另加`--cpu-frequency-khz 1800000`。准确argv和退出码保存于`cpu-policy-dx/{auto,fixed}-command.json`及各`build/lab-runs/<run-id>/benchmark-command.json`、`result.json`；自动组另有`benchmark-exit.json`，固定组缺失，补充说明见`fixed-postcheck-receipt.json`。日志为各运行目录的`realm-evidence/`、`cpu-samples.log`和UART；配对分析为`cpu-policy-dx/hardware.json`、`scene-comparison.json`，冻结与最终封存见同目录。

**结论与后续。** 当前保留DA数据路径及DX测试入口；DA历史893，本轮同代码自动策略为891，两者不是优化前后对照。现有结果不支持把锁频作为主要提分方向。下一阶段优先定位一次提交到可信完成期间的串行握手和等待结构，并用逐场景证据选择实质不同的候选，避免重复既有等待常数、MMIO屏障或临时映射缓存实验。1000门槛未通过，API/ML/多Client扩展、真实GPU完成eventfd与隔离攻击本轮NOT_RUN，历史AE EBUSY和物理GPT/GPC边界保持。只读监视曾读取不存在的日志路径退出1，属于观察命令失败，保留在failed-and-not-run，不记为GPU失败；测试未因观察失败重启。


## DY：Client首次/后续FINISH查询分类，892分诊断后恢复（2026-11-01）

统一记录：定位当前DA路径完成侧重复查询的来源｜同条件DX自动891→DY诊断892｜+1分/+0.11%｜仅Client镜像增加临时计数与计时，RMM/Proxy/Host/initrd/runner、绑定及GPU实际594MHz不变，CPU为原schedutil；无固件写入或重启｜`private-heap-720-20261101-dy`退出1（低于1000）；分析、恢复及日志核验退出0｜诊断已撤下，恢复DA Client及DX runner；不将1分变化视为优化或稳定收益。

**新增观测。** 按首次/后续查询以及可信FINISH成功、GPU pending、CPU归还续传、错误分组，记录调用数、调用墙钟与从Client接纳启动到查询起点的间隔，并使用16µs起始的指数直方图。统计只在typed FINISH返回后写入，不参与调度、授权、页表、完成或回收。起点不是GPU实际启动时刻；调用墙钟包含RMM/设备交互和Guest/Host抢占。不存在纯CPU/GPU时间或实际完成瞬间测量。

843,036次FINISH对账340,588批成功退休：340,588次成功、502,447次GPU pending、1次CPU归还续传、0次错误。首次查询321,183次返回GPU pending（94.30%），19,405次成功（5.70%），首次无CPU归还续传。

| 查询类别 | 次数 | 平均查询起点间隔µs | 平均typed调用墙钟µs |
| --- | ---: | ---: | ---: |
| 首次成功 | 19,405 | 124.663 | 108.101 |
| 首次GPU pending | 321,183 | 168.904 | 65.217 |
| 后续成功 | 321,183 | 393.332 | 87.134 |
| 后续GPU pending | 181,264 | 412.094 | 47.366 |
| 后续CPU归还续传 | 1 | 50484.584 | 294.291 |

首次pending的查询起点中位数/90%分位均落在[128,256)µs桶；后续成功的两项均落在[256,512)µs桶。这是粗分桶，不是精确分位数。每类age/call桶合计与调用数、首次总数与退休数、成功/pending/续传与阶段统计独立对账。数据为file累计，包含预热/validation，不等同正式计分窗口。CPU归还续传几乎不是本轮重复查询来源；但不能据此把pending查询全部认定为可省，它们也可能推进STATUS和堆事件处理。

**验证及实测。** 原有实际Client提交/worker模型在诊断版和恢复版各113项通过；固定补丁清单及ARM64 Client构建退出0。解析器1个有效样本和相同重复日志通过，8类计数/桶界/冲突/缺失损坏输入被拒。未重新跑未改变的整套RMM私有回归，DW633只保留为历史。完整33场景、计算预热、CPU SIGNAL/eventfd/basic、VM0/0、两端kernel-log/pool-unbind、Host健康与资源恢复通过；validation26成功/1既有数值例外/6无判据。各11份远端证据SHA一致。正式计分351次瞬时频率采样均1.8GHz，不能证明采样间隙内恒频；GPU完成eventfd仍NOT_RUN。

**运行与恢复。** 准确argv见`completion-shape-dy/measure-command.json`及`build/lab-runs/private-heap-720-20261101-dy/benchmark-command.json`。外层为`lab-run.py --run-id private-heap-720-20261101-dy -- python3 build/rmm-client-bo-20261030/completion-shape-dy/run.py measure`；内层`run-realm-xshm.py --images build/rmm-client-bo-20261030/completion-shape-dy/candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。只有Client Image上传，RMM未构建或部署。源与载荷188项冻结，运行后核验无变化。

随后`private-completion-shape-restore-20261101-dy`独占执行`run.py restore`退出0，原子恢复冻结Client镜像，四项板端输入及实际SD2字节核验匹配；恢复两份临时源码并核验157项原输入。当前仍为DA数据路径及DX runner，参考分数为DX自动891，DA893为历史；恢复后无新GPU测量。增量构建树的Image/vmlinux仍是诊断产物，未用冻结镜像覆盖伪装；恢复源码已刷新mtime供后续重编译。诊断与数据保留在忽略的build目录，源码不残留诊断字段/分支。

证据根为`build/rmm-client-bo-20261030/completion-shape-dy/`：`hardware.json`、`query-shape.json`、`scene-comparison.json`、`local-checks.json`、`runtime-restoration.json`、`source-restoration.json`、`checkpoint.json`；板端日志/命令/退出码及11份副本在上述run-id的`build/lab-runs/`。保留首次编辑脚本的worker名称匹配失败（写源码前退出）及只读监视Python转义错误，详见`failed-and-not-run.json`；均未触发负载重启。前后SD回执加入pre/post后缀，本轮无DX的回执重名失败。

**下一步。** 新证据支持研究按队列、结合查询结果/成本反馈的首查预测，并把后续有界快速重查额度与首查等待分开评估。与CB/CF的共享600µs预算和CR的单纯常数调整区分，仍需先设计模型和新的完整720p实测；本轮未实现新预测器、预算变化或省略任何真实检查。不要将约65µs墙钟乘以pending比例推算应用收益。1000门槛、AE EBUSY、API/ML/多Client、真实GPU完成eventfd和恶意Client/Proxy隔离实机验收仍未完成，RK物理GPT/GPC限制保持。

## DZ：结合pending调用成本预测首查，881分撤回并恢复DA（2026-11-01）

统一记录：减少过早FINISH而保留后续快速重查｜同条件DX自动891→DZ881｜−10分/−1.12%｜仅Client预测器变化，Proxy/RMM/Host/initrd/DX runner、绑定及GPU实际594MHz不变，CPU保持原schedutil；无刷写或重启｜`private-heap-720-20261101-dz`退出1（低于1000），分析与恢复退出0｜未达预设902保留线，已撤回；当前仍为DA数据路径及DX runner。891为DX最新同条件对照，893为DA历史成绩；恢复后没有新增GPU测量。

**候选与旧实验的区别。** 基于DY首次94.30%返回pending的证据，将单队列预测目标从“最后一次pending查询的起点”改为“起点加该次typed FINISH调用耗时”；调用耗时样本最多100µs，目标和首查等待最多400µs，仍以四分之一权重平滑，首次成功使旧提示衰减。只在精确可信成功退休后训练；成功FINISH、CPU归还游标、heap服务与失败不提供成本样本。后续八次50µs快速等待独立保留，不像CB/CF那样因首查等待消耗共享预算。最大请求主动等待由600增至800µs，不含可信调用或抢占，不能保证墙钟上限；所有真实FINISH、heap、错误、归属、根、停止/归还/退休检查及绝对deadline保持。

| 指标 | DX自动对照 | DZ |
| --- | ---: | ---: |
| 完整720p分数 | 891 | 881 |
| FINISH查询/退休批 | 2.467424 | 1.950414 |
| COMPLETE调用墙钟µs/批 | 339.169 | 304.983 |
| COMPLETE worker间隔µs/批 | 267.802 | 314.355 |
| 调用与间隔合计µs/批 | 606.972 | 619.338 |
| 首次主动等待墙钟µs/批 | 165.326 | 237.502 |

查询减少20.95%，调用墙钟减少10.08%，但间隔增加17.38%，合计增加2.04%，没有端到端收益。统计为每文件累计，包含预热、validation、设备交互及Guest/Host抢占；不同退休批数分别归一，不是纯CPU成本、精确GPU执行时间或逐任务应用延迟。只能归因预测器、成本样本与上限的组合结果，不宣称单个改动因果或稳定回退幅度。预先固定总分≥902、blur≥141、terrain≥25、5×5 effect2d≥658；实测场景155/27/730，场景保护通过，总分不通过。

**验证与硬件。** `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 python3 scripts/check/check-gpu-private-submit.py`候选118项实际worker模型退出0；`python3 build/rmm-client-bo-20261030/poll-feedback-dz/check-mutants.py`退出0，7个成功编译的破坏成本上限/首查上限/重查次数/归还分类/失败训练/真实完成的变体被断言拒绝。ARM64 Client Image构建及固定上游补丁校验退出0。模型使用fence/时钟/设备替身，不证明Linux并发或实体隔离；未重跑未变化的完整RMM套件。

完整33场景、计算预热、CPU SIGNAL/eventfd及basic冒烟、VM退出0/0、两端kernel-log/pool-unbind、Host健康与CPU0–1/pmthor/无遗留loop及进程恢复通过；validation仍26成功/1既有数值例外/6无判据，不称全正确性PASS。正式计分348次瞬时CPU频率采样均1.8GHz，不证明间隙恒频。11份远端证据SHA一致，外层退出1仅由1000门槛触发。广泛API/ML/多Client及真实GPU完成eventfd未执行，AE EBUSY与历史Group submit超时仍未闭环。

准确命令与退出码在`poll-feedback-dz/{measure-command,measure-exit}.json`及`build/lab-runs/private-heap-720-20261101-dz/benchmark-command.json`：外层`lab-run.py --run-id private-heap-720-20261101-dz -- python3 build/rmm-client-bo-20261030/poll-feedback-dz/run.py measure`；内层`run-realm-xshm.py --images build/rmm-client-bo-20261030/poll-feedback-dz/candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。Client构建使用现有`guest-client`输出目录、`ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=$PWD/build/verified-kernels/firmware -j8 Image`。

**回退与证据。** 独占`private-poll-feedback-restore-20261101-dz`执行`run.py restore`退出0，原子恢复DA Client；四项板端输入与实际SD2固件字节核验。246项冻结输入在运行及恢复前一致；仅恢复两份本轮源码后137项原来源/输入核验，恢复版113项worker模型退出0。增量构建Image/vmlinux仍是DZ证据，未用冻结镜像冒充构建结果；恢复源码刷新mtime。凭据会话和只读监视已退出，无运行中的负载。

证据根`build/rmm-client-bo-20261030/poll-feedback-dz/`保留`plan.json`、`hardware.json`、`assessment.json`、`scene-comparison.json`、`mutants.json`、`frozen-input-verification.json`、`runtime-restoration.json`、`source-restoration.json`与`checkpoint.json`；测试日志、argv和退出码见上述run-id。首次准备因DY清单包含已更新的requirements-audit而断言退出1，发生在改源码/启动硬件前；随后限定源码/运行输入并通过，失败未删除。当前不保留候选字段、分支或只适配它的生产测试。

下一步不再仅凭查询次数调首查常数；先定位首次查询是否推进设备状态、以及设备实际完成到worker可见之间的等待，再决定是否修改唤醒/观察机制。1000门槛和整体目标未完成，RK平台的实体GPT/GPC限制保持。


## EA／EB：覆盖实际保留域的完成状态诊断，892／893分，已恢复DA（2026-11-01）

统一记录：区分完成查询未满足条件的实际原因｜DX自动策略891 → EA892／EB893｜分别+1/+0.11%、+2/+0.22%｜仅RMM临时统计改变，O2 Debug与断言、Client/Proxy/Host/initrd/DX runner及GPU实际594MHz保持；CPU原schedutil，候选经固件重启、DX对照未重启，统计输出及代码布局存在扰动｜部署、恢复、清理各退出0；`private-heap-720-20261101-ea`与`private-heap-720-20261101-eb`均退出1，仅因1000门槛未通过｜均为诊断，不保留为优化，三份临时生产源码与实际SD2固件已恢复DA；整体目标未完成。

**先保留失败边界。** EA仅在普通`task_finish()`统计首次/后续结果，但生产`gpu_firmware_task_finish_domain()`大多直接进入DRAIN，绕过该入口。EA实际覆盖界限检查失败，不能据其普通FINISH统计推断全部Client。EA完整720p892分仍有效，但只作为带不完整诊断的运行结果；没有把漏接路径解释成GPU未完成。启用统计的旧模型虽有320次普通FINISH，却没有要求覆盖保留域；这一不足已明确记录。

EB在普通FINISH和保留域FINISH两处建立同一首次/后续上下文，补充DRAIN返回阶段分类；仅记录原有新鲜STATUS、队列读数及结果，不增加GPU寄存器或队列读取、不改变检查或完成条件。每个任务记录首次观测标志，任务数组仍为52224字节；计数、输出和代码布局有开销，不宣称诊断无扰动。全局policy锁内输出，每次成功组销毁打印三份30行计数，计数自RMM启动累计，含预热、validation及内部yield；不是逐Client计分窗口或实际GPU完成时刻。

**本地验证。** EA完整私有套件633条PASS标记、启用统计的普通后端320次调用及9类解析负例通过，但不抵消上述实际路径漏接。EB启用统计的实际平台/核心模型强制执行保留域：356次FINISH结果（328首次、28后续），其中311次保留域，首次/后续结果、提示与DRAIN阶段守恒通过；同一模型明确要求保留域非零，成功拒绝EA漏接实现。EB实际RSI分发与实际GPU核心定向回归退出0，原严格解析器10类损坏输入检查通过；未重跑未变更的整套633套件，633只引用EA历史。两版独立O2 Debug、断言、固定上游补丁、FIT嵌入与ELF/BSS布局检查通过。模型设备、REC/RTT和物理页访问仍为替身，不证明实体隔离或并发。

**两轮硬件。** 均为完整33场景、validation26成功/1既有数值例外/6无判据；计算预热、CPU SIGNAL/eventfd/basic冒烟、VM退出0/0、两端pool-unbind/kernel-log、Host内核健康与CPU0–1/pmthor/无遗留loop及本轮进程恢复检查通过，每轮11份证据SHA一致。EA正式计分355次、EB358次瞬时采样均1.8GHz，不代表采样间隙恒频。两轮均无Guest运行输入上传，只有诊断固件改变；真实GPU完成eventfd、广泛API/ML/多Client未执行。

**串口损坏与后处理。** EB原严格整帧解析器拒绝退休计数回退：帧177头中的231191丢失数字2，变为31191。原解析器、失败日志、原始UART及冻结178项输入均保留，没有修改运行时的统计或事后补数字。另加仅用于事后分析的行表多数一致解析：每个原三份报告内，至少两份不同序号的完整30行表须逐项一致，并保留全部类别守恒及跨报告计数单调检查；不满足的报告拒绝。退休头单独要求至少两份一致，不能由行表反推或补齐。最终205/206/207三份行表完全一致，但仅205退休头完整，因此终点退休头标记UNAVAILABLE（单份原始头340996只作旁证），不宣称三份完整整帧。68组报告、203份行表副本合格；终点首次/成功计数独立覆盖Client最终340664批退休。新解析器4个正向场景、8类指定损坏拒绝通过。该验证用于测量数据完整性，不是安全授权或完成证明。

| EB累计计数 | 首次 | 后续 |
| --- | ---: | ---: |
| FINISH成功 | 18232 | 323139 |
| GPU pending | 322764 | 175154 |
| CPU归还续传 | 0 | 1 |
| FINISH错误 | 0 | 0 |
| 保留域FINISH | 330410 | 482652 |
| DRAIN成员进度未满 | 312780 | 169872 |
| DRAIN进度已满但idle仍pending | 0 | 0 |
| DRAIN成功 | 17630 | 312779 |
| OBSERVE早返回pending | 0 | 1 |

RMM共340996次首次、498294次后续FINISH，首次94.65% pending；96.875%的FINISH调用进入保留域。保留域482653次pending中，482652次由成员进度未满返回，另1次为堆事件边沿；没有观察到idle阶段pending或保留域错误。新鲜读数中extract/sequence/scoreboard/blocked可同时未满足，不能将四类相加。统计含内部yield，因此成功计数341371不等同Client退休340664，不强行逐任务一一对应。

EB的Client完成查询/退休批2.460606，PREPARE累计墙钟138.499µs/批，COMPLETE调用339.641µs/批、间隔266.814µs/批；含设备交互、调度、预热和validation，不是纯CPU成本，也不证明首次查询推进或阻碍了GPU。该结果不支持把全部pending归因于重复idle检查、CPU归还或旧STATUS未确认，更不支持仅按减少查询数继续增加首查等待。

**命令、恢复与证据。** 两轮准确argv/退出码在`finish-state-ea/`、`finish-state-eb/`的`{deploy,measure,restore,cleanup}-command.json`及`*-exit.json`；板端运行证据在对应`build/lab-runs/private-heap-720-20261101-ea|eb/`。外层均经`lab-run.py`独占；测量内层为：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-eb -- python3 build/rmm-client-bo-20261030/finish-state-eb/run.py measure
# run.py执行：
python3 scripts/run/run-realm-xshm.py --images build/rmm-client-bo-20261030/finish-state-eb/candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
```

部署／恢复ID分别为`private-finish-state-fw-20261101-ea|eb`／`private-finish-state-restore-20261101-ea|eb`，明确只写SD2并保留启动区备份。恢复后各137份原来源、四项板端Guest输入及实际SD2字节通过，178项冻结输入按恢复后来源核验通过；本轮Pi两份部署/恢复上传目录各按SHA、大小、mtime及占用核查后精确清理。诊断源码、构建树、固件及失败证据保留在忽略的build目录，生产源码不残留统计分支，恢复mtime已刷新。凭据和只读监视会话已退出，恢复后无新GPU测量，当前仍为DA数据路径及DX runner、同条件参考DX891（DA893为历史）。

EB证据入口为`hardware.json`、`parsed-shape.json`、`assessment.json`、`hardware-analysis-original.log`、`quorum-parser-checks.json`、`frozen-input-verification.json`、`final-input-verification.json`、`final-runtime.json`、`pi-cleanup.json`、`failed-and-not-run.json`及`checkpoint.json`；EA同目录保留其覆盖不足及夹具失败。下一阶段优先研究将STATUS请求与后续观察分开、或使用设备完成事件作为调度提示，并验证其相对当前轮询的收益；尚未实现，不能据累计pending比例推算可省时间。原有可信新鲜检查、真正排空、缓存可见性和精确退休保持。不要重复仅调等待常数、单纯worker内联或CS重复快照实验。1000门槛、AE VM_BIND EBUSY、历史Group submit超时、真实GPU完成eventfd及实体GPT/GPC边界仍未闭环。


## EC：STATUS 请求与应答检查分阶段执行，819分，撤回恢复DA（2026-11-01）

统一记录：避免在 RMM 内等待尚未到达的设备 STATUS ACK｜DX 自动策略 891 → EC819｜−72分/−8.08%｜仅 RMM 一个核心文件变化，DA Guest/Proxy/Host/initrd 与 DX runner 不变；同 O2 Debug 与断言、GPU 实际594MHz、CPU未锁恒频，候选固件重启而DX参考未重启｜部署 private-async-status-fw-20261101-ec 退出0，完整720p private-heap-720-20261101-ec 退出1（仅1000分门槛）｜未满足902保留线和三个场景保护，撤回；1000门槛与整体目标未完成。

保留域 FINISH 发出一次 STATUS，读到尚未确认即返回 INCOMPLETE；后续调用继续同一个请求，不重复敲门铃、不更新原确认期限、不返回旧队列位图。状态绑定任务、Group、硬件CSG、真实根和原请求/父门铃位。每次恢复重新检查实际运行AS/固件和全部stream错误；ACK到齐后仍执行新鲜队列进度、根、真正排空、flush、读后重验及精确退休。等待期间堆事件查询仅返回未完成，不能分配/确认堆；显式取消使续传不可再用，超时和异常保留所有引用。普通非保留域接口沿用原流程。

初始每任务记录使BSS增加4096字节并越过当前链接上限，构建失败保留。将续传信息放到每Group后，任务数组仍52224字节，Group数组11008→12032字节，共增加1024字节；原RMM_MAX_SIZE、23份编译flags、预留区、断言与布局检查保持。此内存变化不能作为GPU提速证据。

布局精简前完整私有套件633条PASS；精简后实际后端回归4288条PASS标记（不是等量独立安全场景）、实际RSI延迟应答模型28个Client场景及6个成功编译的错误变体断言拒绝通过。模型覆盖两Client、多个重查、原请求单发、只到达部分ACK、过期后才ACK、时钟回绕、Client/固件根改变、错误/堆通知及显式取消；底层REC/RTT/设备/锁仍为模型，不证明实体并发、GPU执行或GPC。

完整证据在 build/rmm-client-bo-20261030/async-status-ec/；冻结174项输入。失败及未执行项独立保留，早期构建、夹具与mutation验证失败不计作PASS。

**硬件结果与取舍。** 完整33场景、计算预热、CPU SIGNAL/eventfd/basic冒烟、VM退出0/0、两端pool-unbind/kernel-log、Host健康与CPU0–1/pmthor/无遗留进程及loop检查通过，11份远端证据SHA一致。validation仍26成功/1既有数值例外/6无判据，不称全部正确性通过。350个计分区间瞬时采样为1.8GHz；仅一份Host时钟偏移校准，不能证明连续恒频。无Guest输入上传，只换RMM固件。各项均是本轮证据，不继承历史Group submit PASS。

| 指标 | DX自动对照 | EC |
| --- | ---: | ---: |
| 完整720p分数 | 891 | 819 |
| FINISH查询/退休批 | 2.467424 | 3.655104 |
| COMPLETE调用墙钟µs/批 | 339.169 | 303.395 |
| COMPLETE worker间隔µs/批 | 267.802 | 412.603 |
| 调用与间隔合计µs/批 | 606.972 | 715.998 |
| blur FPS | 156 | 137 |
| terrain FPS | 27 | 15 |
| 5×5 effect2d FPS | 730 | 43 |

查询增加48.13%，调用墙钟减少10.55%，worker间隔增加54.07%，两者合计增加17.96%。blur/terrain/effect2d保护线141/25/658均未通过。数据为含预热、validation、设备等待和Guest/Host抢占的累计量，按各轮退休批数归一，不是纯CPU成本、GPU执行时间或逐任务因果追踪；单轮分差不证明稳定退化幅度。可以支持撤回，不能据此定量归因某一个分支、堆事件或timer。先前EA/EB的pending比例不等于可省成本，本轮实测进一步否定“单独退出ACK忙等自然会更快”。

准确命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ec -- python3 build/rmm-client-bo-20261030/async-status-ec/run.py measure
# 内层：
python3 scripts/run/run-realm-xshm.py --images build/rmm-client-bo-20261030/async-status-ec/candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1
python3 scripts/maintenance/lab-run.py --run-id private-async-status-restore-20261101-ec --allow-rk-reboot -- python3 build/rmm-client-bo-20261030/async-status-ec/restore-checked.py
```

后续方向应同时考虑设备ACK与任务执行pending的调度区别、首次/重查到timer回退的完整路径，或经验证的设备事件唤醒。需要新的逐场景证据和可信状态机，不能只重复本轮拆分、减少SMC计数、加长首查或换轮询常数。未达到1000，不扩展API/ML/多Client；真实GPU完成eventfd、AE EBUSY、历史Group submit超时、恶意并发及实体GPT/GPC仍未完成。

**回退核验。** 独占恢复 `private-async-status-restore-20261101-ec` 退出0，恢复137项原来源、四项板端Guest输入及实际SD2固件字节。只恢复本轮一个核心文件，刷新源码mtime，增量构建目录保留候选证据。当前仍是DA数据路径与DX runner，参考DX891、DA893均为历史结果，回退后未新增GPU测量。Pi本轮部署/恢复的两份重复上传按SHA、大小、mtime与占用核查后精确清理，控制机保留候选、回退、实际启动区备份及全部失败证据。

证据入口：`async-status-ec/{plan,validation,hardware,phase-comparison,timed-frequency,mutants,frozen-input-verification,final-runtime,source-restoration,failed-and-not-run,checkpoint}.json`；日志和各stage准确argv/退出码见`{deploy,measure,restore,cleanup}-command.json`、`*-exit.json`、`*.log`及`build/lab-runs/<run-id>/`。候选生产字段/分支已撤回，不在生产源码保留废弃框架。整体目标未完成。


## ED：Client GPU 推进 worker 使用高优先级，931／934 分，保留（2026-11-01）

统一记录：减少 GPU 推进 worker 与 Client 应用的调度竞争｜DX 普通优先级历史891；本轮紧邻普通优先级892 → 同一候选镜像931／934｜相对本轮对照+39／+42分，+4.37%／+4.71%｜单Client、完整1280×720／33场景，GPU实际594MHz，CPU未固定频率；Host、RMM、Proxy、initrd与DX runner相同，无刷写／重启｜下列run-id、命令及日志｜两轮均超过事先902保留线且三个场景保护通过，保留ED；1000门槛仍FAIL，整体未完成。

只把`panthor_client_open()`中私有GPU有序工作队列的标志由0改为`WQ_HIGHPRI`。Linux将它放入nice=-20的独立高优先级worker池，保持同一文件内有序执行；没有使用实时调度策略。首次自适应等待、八次快速重查、普通延迟回退、真实FINISH／heap查询、原绝对期限及fence退休条件均未改变。RMM源文件与实际SD2固件保持原DA版本。

| 同序硬件运行 | 版本／分数 | blur | terrain | 5×5 effect2d | 外层退出码 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `private-heap-720-20261101-ed` | ED 931 | 151 | 28 | 745 | 1 |
| `private-heap-720-20261101-ed-control` | 普通优先级892 | 156 | 27 | 729 | 1 |
| `private-heap-720-20261101-ed-repeat` | 原ED镜像934 | 153 | 28 | 744 | 1 |

三轮均完整33场景、validation为26成功／1既有数值异常／6无判据、VM退出0／0、计算预热及CPU SIGNAL eventfd/basic冒烟、两端pool解绑、Host内核健康及资源恢复检查通过。不能称全部数值验证通过或真实GPU完成eventfd已验收。外层退出1的原因为完整720p不足1000，不掩盖此失败。每轮11份板端证据均拉回并核验SHA；普通对照没有上传新载荷，候选和复测只上传Client Image。

Client提交／生命周期模型113项、ARM64 Image构建、上游补丁清单检查均退出0。仅一个运行源码标志变化，没有为此重复整套RMM模型或扩大硬件矩阵。为核查旧冻结二进制与当前构建是否可比，另重建普通优先级Image：可执行代码段与旧基线逐字节相同，全Image仅44字节差异，位于构建版本／时间和build-id；见`normal-rebuild-comparison.json`。该重建本身没有新增GPU测量。

累计COMPLETE调用／退休批次由普通对照338.824µs降至ED首轮199.583µs、复测199.440µs；对应worker间隔267.850→266.410／263.794µs，查询／批次2.46813→2.46118／2.46361。阶段墙钟含Guest／Host调度、设备响应及预热／validation；不等于纯RMM指令成本、GPU时间或可直接相加的稳定因果收益。各轮中间快照和最终计数单调一致性检查通过。只读等待拆分另显示普通基线立即排队平均1.31µs，慢速排队约6.30ms；不能仅按队列等待比例预测优先级的整机效果。

所有路径均在`build/rmm-client-bo-20261030/`下：`worker-priority-ed/`保存计划、源码前后快照、单行patch、113项模型日志、构建／补丁日志、候选、`hardware.json`、`decision.json`、阶段／等待比较与构建字节核对；`worker-priority-control-ed/`和`worker-priority-repeat-ed/`保存紧邻对照及原镜像复测。独占证据在`build/lab-runs/<run-id>/`，含原命令、退出码、11份SHA核验日志和前后资源报告。冻结运行包为`worker-priority-ed/candidate/`，固件仍`firmware-private-running-check/`。137项当前输入、四项Guest和实际SD2核验通过；原普通优先级包保留作回退。

测量命令分别为：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ed -- python3 build/rmm-client-bo-20261030/worker-priority-ed/run.py measure
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ed-control -- python3 build/rmm-client-bo-20261030/worker-priority-control-ed/run.py measure
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ed-repeat -- python3 build/rmm-client-bo-20261030/worker-priority-repeat-ed/run.py measure
```

中间恢复普通镜像以做对照的独占run-id为`private-worker-priority-restore-20261101-ed`，退出0；之后重新部署同一ED镜像。该恢复不是撤回最终保留的ED。两轮候选支持当前720p改善的观察，不构成统计显著性、ML／多Client或公平性验收。1000门槛、AE历史VM_BIND EBUSY、Group submit额外超时及实体GPT／GPC与恶意多Client验收仍未完成。EE仅准备过普通优先级上的高精度睡眠源码及119项模型，未写入运行源码、未构建或上板；后续EF改以确认后的ED为对照，另行评估，不能把其预期收益计入ED。


## EF：慢速完成等待改用高精度睡眠，937分，撤回恢复ED（2026-11-01）

统一记录：减少八次快速重查耗尽后的jiffy粒度等待｜确认后的ED934 → EF937｜+3分／+0.32%｜仅Client worker慢速回退与配套第六计数桶变化，继承ED高优先级；同Host／RMM／Proxy／initrd／DX runner、单Client完整720p、GPU实际594MHz、CPU未固定，无刷写或重启｜`private-heap-720-20261101-ef`退出1，命令／日志见下｜未达事先944保留线，撤回EF并恢复ED；整体1000门槛未完成。

保持首次≤200µs预测、八次50µs主动等待、原始任务期限及全部真实FINISH／heap／退休条件。仅在真正GPU pending且八次额度耗尽后，释放私有GPU锁，调用`usleep_range(1000,1200)`，重取锁再立即排入下一次真实观察；CPU归还续传和资源接纳回退不走该睡眠。`CONFIG_HZ=250`、`CONFIG_HIGH_RES_TIMERS=y`。关闭期间由同步取消worker保持对象生存；睡眠和Host抢占均不能提供完成证明或延长期限。新增第六计数桶区分高精度睡眠；本轮分数差异只能归因于整个候选组合。

| 指标 | ED确认版 | EF候选 |
| --- | ---: | ---: |
| 完整720p | 934 | 937 |
| blur／terrain／5×5 effect2d | 153／28／744 | 152／28／745 |
| 查询／退休批 | 2.463612 | 2.470265 |
| COMPLETE调用µs／批 | 199.440 | 199.553 |
| COMPLETE worker间隔µs／批 | 263.794 | 251.474 |
| 慢速等待次数 | 1268 | 2449 |
| 慢速等待平均µs | 6337.34 | 1326.13 |
| 慢速等待µs／退休批 | 22.679 | 8.983 |

慢速排队和worker内睡眠的计时边界不同，以上为含预热／validation和调度的累计墙钟，不是纯定时器成本、GPU时长或可直接外推的模型加速。等待缩短得到实测支持，但整机只提高0.32%，不能据局部改进降低944保留线。预设三个场景保护141／26／670均通过；完整33场景、validation26成功／1既有数值异常／6无判据、VM0／0、预热、CPU SIGNAL eventfd/basic冒烟、两端解绑、Host内核健康与资源恢复检查通过，11份证据SHA核验。外层退出1为低于1000；数值异常及未执行项保留。

实际Client worker／planner模型119项、ARM64 Image构建、上游补丁清单退出0。六个新增场景覆盖锁外睡眠、关闭、过期、Host过度延迟、heap报错与CPU归还续传；内核锁、定时器、typed RMM调用和设备为替身，不证明Linux真实并发或实体隔离。RMM没有修改，因此未重复其完整模型套件。普通优先级上的EE只做了独立源码／119项模型，未部署；EF以确认的ED为基线，避免混合优先级和睡眠的归因。

命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ef -- python3 build/rmm-client-bo-20261030/timer-fallback-ef/run.py measure`。证据在`build/lab-runs/private-heap-720-20261101-ef/`；计划、944保留线、两个源码的前后快照／patch、119项日志、构建／补丁日志、170项冻结输入及`hardware.json`、`sleep-comparison.json`、`decision.json`在`build/rmm-client-bo-20261030/timer-fallback-ef/`。首次冻结辅助脚本在候选和manifest写完后的最终打印因重复`status`关键字退出1；保留失败记录，修正并完整重核验后才部署，不能算成功运行。

恢复通过`private-timer-fallback-restore-20261101-ef`的独占入口进行：仅恢复原ED Client Image及本轮两个源码，保留`WQ_HIGHPRI`；核验137项输入、四项Guest和实际SD2。恢复后没有新增GPU测量，934引用ED此前的确认运行，不能称重新测得934。增量构建目录仍可能保存已撤回EF的Image；下一轮使用冻结ED包，或在已touch的恢复源码上重新构建，不能将构建缓存当成当前运行版本。AE VM_BIND EBUSY、额外Group submit超时、真实GPU完成eventfd、广泛API／ML／多Client及实体隔离仍未验收。


## EG：Client VM_BIND 有序队列使用高优先级，935分，撤回恢复ED（2026-11-01）

统一记录：检查映射生产者与GPU推进队列的调度竞争｜ED确认轮934 → EG935｜+1分／+0.11%｜同一单Client完整1280×720／33场景、GPU实际594MHz、CPU未固定；RMM／Proxy／Host／initrd／DX runner不变，仅Client映射队列使用`WQ_HIGHPRI`，无刷写或重启｜下述run-id、命令、退出码及日志｜未达到事先944保留线，撤回EG；1000门槛仍FAIL，整体未完成。

ED只提高GPU推进队列优先级。EG检查另一条有实际调用者的路径：`panthor_client_private_vm_bind()`把映射操作交给`private_wq`，GPU接纳可能等待这些操作完成。本轮只把该有序队列标志从0改为`WQ_HIGHPRI`；保留顺序、依赖、锁、对象引用、原始期限、授权／映射检查及完成条件，没有修改接收队列、等待时间或RMM检查边界。完整测量不足以支持该路径存在显著的调度瓶颈，不能把ED结果推广到所有worker。

| 指标 | ED确认轮 | EG |
| --- | ---: | ---: |
| 完整720p分数 | 934 | 935 |
| blur／terrain／5×5 effect2d | 153／28／744 | 152／28／744 |
| PREPARE累计调用µs／退休批 | 约138 | 138.357 |
| COMPLETE累计调用µs／退休批 | 199.440 | 198.729 |
| COMPLETE worker间隔µs／退休批 | 263.794 | 265.524 |
| COMPLETE查询／退休批 | 2.463612 | 2.455613 |

阶段累计值包含预热／validation、调度和设备交互，不是纯CPU profile；不同运行的退休批次不同。不得把微小分差或某一段变化当作稳定收益。blur／terrain／5×5的预设保护141／26／670均通过，但不降低944保留线。

本地实际Client映射模型41项、提交／生命周期模型113项和补丁清单退出0。首次增量构建漏传`CONFIG_EXTRA_FIRMWARE_DIR`，因找不到内置固件退出2；失败命令与日志保留。核对固定固件SHA与`GPU-SFTP/panthor_fw/mali_csffw.bin`一致后，使用显式目录重建ARM64 Image，退出0。只改变Client镜像，不为该队列标志变更重复完整RMM模型；模型仍不证明Linux真实调度／并发或实体隔离。

硬件命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-eg -- python3 build/rmm-client-bo-20261030/bind-priority-eg/run.py measure`，外层退出1，原因是完整720p不足1000。33场景完成、validation26成功／1既有数值异常／6无判据、VM退出0／0、计算预热、CPU SIGNAL/eventfd及basic冒烟、两端pool解绑和kernel-log检查、Host健康与资源恢复均完成；11份板端证据回收并逐项SHA核验。CPU SIGNAL冒烟不代表真实GPU完成eventfd验收。

证据目录`build/rmm-client-bo-20261030/bind-priority-eg/`包含`plan.json`、137项`before.json`、前后源码、单行patch、各构建／检查命令与退出码、169项冻结输入、候选包、`hardware.json`、`scene-comparison.json`、`decision.json`及失败／未执行项；独占记录位于`build/lab-runs/private-heap-720-20261101-eg/`。恢复命令使用同一入口的`restore`模式，run-id为`private-bind-priority-restore-20261101-eg`，退出0；精确恢复冻结ED Client镜像，核验四项Guest输入和实际SD2固件，再恢复本轮唯一修改的源码，137项原输入哈希一致。恢复辅助脚本沿用的状态名称含`DA_CLIENT`，实际核验哈希与来源均为`worker-priority-ed/candidate/`，不得据旧状态名称误判为普通优先级版本。

恢复后没有新增GPU计分，934为原ED确认轮成绩。构建缓存仍可能是已撤回EG镜像，后续必须使用冻结ED包或重建。API／ML／多Client硬件矩阵、真实GPU完成eventfd、AE历史VM_BIND EBUSY、额外Group submit超时及恶意并发／撤销／实体隔离仍未验收。后续优先利用当前RPC分布与分段计时定位串行开销，不继续仅凭某个worker的历史收益逐个提高其他队列优先级。


## EH：当前私有路径的RPC开销分布，931分诊断，保留ED（2026-11-01）

统一记录：定位当前Client–Proxy请求的实际开销｜ED确认轮934 → 开启已有RPC计时的EH931｜−3分／−0.32%，仅诊断，不计为优化收益或稳定退化｜原ED全部冻结输入、单Client完整720p、GPU实际594MHz、CPU未固定；只增加已有`--rpc-stats`开关，没有运行源码／构建变化，无载荷上传／固件刷写／重启｜`private-heap-720-20261101-eh`，命令与退出码见下｜保留ED，1000门槛仍FAIL，整体未完成。

本轮使用已有Client通信和Proxy handler累计计时，覆盖预热／validation／计分及清理；并非单纯计分窗口。解析最终完整统计表，按实际wire头文件把Client标记为`UNKNOWN`的`0x50547c52`识别为`RMM_TASK`，未改标签源码或数字。Client有12类、Proxy有11类记录；SELFTEST不经过该Proxy handler统计表，最后一次CLOSE_SESSION的Proxy快照也先于该handler自身计数。RMM_TASK两端均353713次，计数一致；其最终行分别与独立保存的两端kernel-log副本逐字一致。解析检查键集、平均值整除关系、最大值、重复类型及错误／超时边界，不拼补损坏数字。

| 请求 | Client次数 | Client平均墙钟 | Proxy handler平均墙钟 | 占Client累计RPC墙钟 |
| --- | ---: | ---: | ---: | ---: |
| RMM_TASK | 353713 | 138.172µs | 93.491µs | 99.426% |
| VM_BIND | 1044 | 133.732µs | 82.329µs | 0.284% |
| BO_IMPORT | 522 | 171.325µs | 39.519µs | 0.182% |
| BO_DESTROY | 522 | 66.595µs | 14.992µs | 0.071% |

RMM_TASK的Client发送平均5.090µs，其中通知4.397µs；回复轮询131.970µs，最终completion等待调用0.180µs，RPC锁等待为0。记录中该类请求传输错误、超时及旧轮询回退的`poll_sleeps`均为0。这里`poll_sleeps=0`是旧轮询计数器，不能单独证明新回复路径没睡眠：还核对实际新路径的`completion_wait_ns`写入位置，极短均值支持几乎全部回复已就绪后立即返回，但聚合表没有暴露新路径`realm_sleep_arms`及每次completion是否阻塞，**不把它写成逐请求零睡眠证明**。

发送、通知、回复轮询、Proxy handler之间有包含和并行关系；Proxy handler包括回复发布，两个均值之差不能命名为纯通信成本。Client累计RPC墙钟约49.156秒，也不能直接当作GPU应用墙钟的某个互斥比例。FINISH／heap等Client直接RSI操作不经过这张RPC表，99.426%只描述RPC内部构成，不是整个GPU生命周期的瓶颈占比。计时扰动、Guest／Host调度、设备等待及不同文件范围均保留；不据此推算可获得的分数或ML／多Client收益。

本轮支持后续优先细分实际`TASK_DISPATCH`的准备／接纳／启动路径，研究相同可信事务内能合并的工作，并检查能否与已有任务执行重叠；重叠机会尚未证明。VM_BIND在RPC中占比很小，与EG提高其worker优先级未形成整机收益的观察一致，但未测量映射worker的独立排队成本，不能宣称其不存在。也不优先继续压缩RMM_TASK的睡眠唤醒：当前聚合等待很短，仍需实际分支计数才能给出逐请求结论。未减少任何身份、实际根、动态错误、真正完成或生命周期检查。

另查到旧共享路径的Proxy主动忙等与请求通知抑制已两次撤回：P5的318→296、后续8µs的1167→1125。本轮未实现或部署新接收轮询，仅补入候选查重索引；不能把缩短窗口或加`need_resched()`当作新的充分依据。它与当前保留的Client回复轮询以及RMM驻留SGI通知机制不同。

执行命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-eh -- python3 build/rmm-client-bo-20261030/rpc-profile-eh/run.py measure`，退出1，原因是完整720p931低于1000。33场景完成、validation26成功／1既有数值异常／6无判据、VM0／0、预热、CPU SIGNAL/eventfd及basic冒烟、两端解绑／kernel-log、Host健康与资源恢复通过，11份证据SHA核验。blur／terrain／5×5为152／28／745；不是新的性能候选或真实GPU完成eventfd验收。

证据目录`build/rmm-client-bo-20261030/rpc-profile-eh/`包含计划、冻结输入、运行命令／退出码、`hardware.json`、`rpc-breakdown.json`、严格解析器、`decision.json`、`final-input-verification.json`及未执行项；完整日志和资源报告在`build/lab-runs/private-heap-720-20261101-eh/`。结束后核验137项源码、154项冻结输入、8项ED保留包内容、四项实际Guest输入和SD2固件，均匹配；Host恢复CPU0–1／pmthor，无本次遗留VM或loop。诊断开关仅存在于已退出VM的本次启动参数，无需回刷或新建恢复运行。当前成绩仍引用ED此前934，硬件诊断931不得替换为新的生产成绩。1000门槛、API／ML／多Client及安全整体验收继续未完成。


## EI：DISPATCH 分段诊断，932 分，恢复 ED934（2026-11-01）

统一记录：定位实际任务提交内部开销｜DA RMM＋ED Client／DX runner确认轮934 → 临时计时932｜−2分／−0.21%｜同一完整720p／33场景、GPU实际594MHz、CPU自动；三个RMM文件仅增加独立计时和销毁后的UART报告，Guest／Host／用户态不变｜下述run-id、命令、退出码和日志｜仅诊断，全部撤下；当前保留ED934，1000门槛和整体目标未完成。

已有EH证据只表明TASK占RPC累计墙钟99.426%；本轮进一步计时实际DISPATCH，包括任务准备、READY缓存交接、PUBLISH、START及隐藏anchor重验。外层DISPATCH入口区分冷启动与保留域，公共独立READY／START不计入；各区间有嵌套，不能相加成总CPU时间。异常／INCOMPLETE也计数，不能用函数结束代替GPU完成。

UART记录207份完整14行帧、69组至少两份独立完整帧逐字段相同的快照，最终三份序号[205, 206, 207]，无拒绝帧。最终累计退休354047批；Client计数353715批，两者范围差332批，保留预热／校验／清理差异。冷启动11353次、保留域342694次；冷READY有109次INCOMPLETE，计数守恒，未出现诊断中的错误结果。

| 保留域DISPATCH区间 | µs／该类调用 | 占该类DISPATCH时间 |
| --- | ---: | ---: |
| DISPATCH总计 | 86.541 | 100% |
| 准备prepare_launch | 44.218 | 51.10% |
| READY缓存及配置 | 9.816 | 11.34% |
| PUBLISH | 25.861 | 29.88% |
| START检查，包含于上述阶段及末尾 | 6.260／次，共7次 | 50.64% |

准备内部包含两次anchor重验，每次19.935µs；该数又包含START检查，不能再与准备／START相加。总DISPATCH约88.064µs／累计退休批，包含计时扰动、Guest／Host调度和设备交互，不是纯CPU profile，也不能与EH不同运行的handler均值直接相减。

本地验证：三个文件的计时变换逆向后与137项源码对照完全一致；原后端／关闭计时／开启计时输出一致，独立17tick时钟及溢出、冷／保留模式、状态分类、独立调用排除和失败后的上下文恢复通过，5个成功编译的错误变体被指定断言拒绝。私有套件633个PASS标记及DMA通过；既有RSI提取测试不包含新增UART辅助函数，因此套件使用原RSI适配器、保留计时core/header；准确计时适配器另由实际RSI模型和ARM64构建验证。首次缩进编译错误、辅助函数提取失败和不适合作为断言变体的泄漏上下文ASan结果保留于`decision.json`，不算通过。O2 Debug／23份flags、断言、0x2800000预留、ELF/BSS及FIT检查保持。

硬件命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ei -- python3 build/rmm-client-bo-20261030/dispatch-cost-ei/run.py measure`，退出1，仅因932低于1000。完整33场景、validation26成功／1既有数值例外／6无判据、VM0／0、计算预热、CPU SIGNAL/eventfd和basic冒烟、解绑及两端kernel-log、Host健康和资源恢复通过；11份日志SHA核验。blur／terrain／5×5为152／28／744，保护线通过。CPU SIGNAL不证明真实GPU完成eventfd。

部署`private-dispatch-cost-fw-20261101-ei`、恢复`private-dispatch-cost-restore-20261101-ei`均经独占重启租约，退出0，仅SD2固件；最终137项源码、四项Guest输入、实际SD2均匹配DA RMM＋ED Client，Host恢复CPU0–1／pmthor，无遗留VM或loop。恢复后没有新增GPU测量；934引用此前确认轮。

本轮新增的可测试方向是PUBLISH已经在实际硬件ACK后完成完整START重验，READY_LAUNCH紧接着又做一次相同检查；可通过仅在当前调用内返回成功结果，避免最后一次重复检查。该结果不得越过回调、硬件写入、解锁或RSI边界；冷启动、重放、未完成及失败必须保留原处理。EJ副本已做初步后端验证，尚不能据检查次数减少宣称提分。与BT的OBSERVE根证明复用、DI的FLUSH检查合并区分；真实根、动态错误及所有回调两侧检查继续保留。

证据：`build/rmm-client-bo-20261030/dispatch-cost-ei/`的计划、输入、模型、`hardware.json`、`profile-summary.json`、`decision.json`和`final-runtime.json`；完整日志在`build/lab-runs/private-heap-720-20261101-ei/`。API／ML／多Client、真实GPU完成eventfd和实体隔离未执行，不沿用历史PASS。


## EJ：同调用复用发布接纳结果，935 分，撤回恢复ED934（2026-11-01）

统一记录：减少DISPATCH中紧邻的重复START检查｜DA RMM＋ED Client确认轮934 → EJ935｜+1分／+0.11%｜相同完整720p／33场景、GPU实际594MHz、CPU自动；只改一个RMM core文件，不含EI计时；Client／Proxy／Host／initrd／DX runner不变｜下述run-id、命令、退出码和日志｜未达到944保留线，撤回并恢复ED934，1000门槛FAIL，整体目标未完成。

EI实测每次保留域DISPATCH有7次START重验。PUBLISH在实际parent／child ACK后已经执行完整START，返回READY_LAUNCH后紧接着又检查一次，中间只有私有结果／元数据写入，没有回调、硬件写入、解锁或重入RSI。本候选通过私有布尔输出把这次成功结果传给同调用的READY_LAUNCH，消除末尾重复检查。结果在每次入口默认false，只有实际发生非空发布、ACK成功且其后的完整START成功才置true；冷启动、未完成、发布失败、精确重放及公开独立API继续使用原检查。不跨任务／回调／锁／RSI保存根证明，与BT／DI原候选不同。

复杂公开函数拆为内部`task_publish`／`task_ready_publish`和保留原调用者的公开包装；没有新Guest ABI、缓存根配置或提前成功fence。每个任务的授权、READY缓存交接、控制页回调前后检查、真实根／配置／动态错误、硬件ACK、FINISH排空、CPU归还和资源退休保持。模型成功的保留域提交START从7→6，冷及错误路径的现有语义一致；检查数量减少不等于应用同比提分。

本地：新旧实际后端完整输出逐字相同，精确检查计数及三个成功编译后由断言拒绝的错误变体通过；私有套件633个PASS标记、DMA和实际RSI回归、补丁清单校验通过，命令／退出见`local-exits.json`和各模型结果。第一次把外层局部accepted初值改为true的变体没有改变行为，因为深层入口仍覆盖为false；该变体未被计入三个拒绝，原日志保留，改为在两个深层入口错误置true后由冷启动语义断言拒绝。O2 Debug／23份编译flags／断言、0x2800000预留、ELF/BSS和FIT布局保持。

硬件命令：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ej -- python3 build/rmm-client-bo-20261030/publish-accept-ej/run.py measure`，退出1。完整33场景、validation26成功／1既有数值例外／6无判据、VM0／0、计算预热／CPU SIGNAL-eventfd／basic冒烟、解绑和两端kernel-log、Host健康与资源恢复通过；11份证据SHA核验。blur／terrain／5×5为153／28／745，保护线通过。CPU SIGNAL不代表真实GPU完成eventfd验收。CPU未固定，单轮不能证明稳定因果收益或ML／多Client收益；前后分数只归因于整个候选组合。

阶段累计PREPARE 132.241µs／退休批、COMPLETE 200.936µs／批、COMPLETE间隔269.009µs／批；包括预热／校验、RPC、调度和设备等待，不是纯CPU时间，不把间隔全部归因于workqueue或宣称减少完整设备执行时间。逐场景见`scene-comparison.json`。与原ED未启用额外计时的确认轮相比，PREPARE 138.752→132.241µs（−6.512／−4.69%），但COMPLETE及gap合计463.234→469.945µs（+6.711）；三项累计合计601.987→602.186µs／批，不能当作互斥应用耗时或因果分解。局部提交缩短未形成端到端保留收益，下一步优先研究可信设备完成通知与任务推进协作，不能只按重复检查数继续削减。见`phase-comparison.json`。

部署`private-publish-accept-fw-20261101-ej`退出0；恢复`private-publish-accept-restore-20261101-ej`退出0。均经Pi／RK独占与重启租约、只写SD2固件，Host内核未刷写。最终`private-publish-accept-finalize-20261101-ej`退出0，137项运行源码、冻结脚本／固件／包内容、四项实际Guest输入及SD2字节匹配；Host恢复CPU0–1／pmthor，无遗留VM或loop。Pi按准确路径、SHA、inode／mtime与fd占用检查清理已归档的冗余上传固件8361984字节，日志和控制机回退镜像保留。

当前冻结包`build/rmm-client-bo-20261030/worker-priority-ed/candidate/`，固件`build/rmm-client-bo-20261030/firmware-private-running-check/`；当前934分引用此前ED确认轮，恢复后没有新增GPU测量。API／ML／多Client、AE VM_BIND EBUSY、历史Group submit超时、真实GPU完成eventfd和实体隔离仍未验收，不能沿用旧PASS。下一步应继续按完整720p确定实际瓶颈，避免仅凭少一次检查或更小等待参数推算收益。

证据：`build/rmm-client-bo-20261030/publish-accept-ej/`的计划、模型、冻结输入、构建、`hardware.json`、`decision.json`、`final-verification.json`和`pi-cleanup.json`；完整日志`build/lab-runs/private-heap-720-20261101-ej/`。本轮未更改Host/Guest数据路径；诊断EI及已撤回候选均不替换当前成绩。


## EK：Proxy 接收 worker 高优先级，931分，撤回恢复ED934（2026-11-01）

统一记录：检查提交接纳路径的调度竞争｜DA RMM＋ED Client确认轮934 → EK931｜-3分／-0.32%｜相同单Client完整720p／33场景、GPU实际594MHz、CPU自动，只有Proxy内核变化；Client／RMM／Host／initrd／DX runner相同，无固件写入或Host重启｜下述命令、退出码与日志｜未达944保留线，撤回并恢复ED934，1000门槛FAIL，整体未完成。

EH显示RMM_TASK往返均值138.172µs、handler93.491µs，但区间重叠，不能将差额直接视作调度开销。ED的Client GPU高优先级worker已有收益，EG映射队列没有满足保留线；本轮独立检查Proxy接纳侧，将`proxy_comm_vmshm_queue_rx()`唯一的`schedule_work()`改为`queue_work(system_highpri_wq, ...)`。这是按事件触发的worker优先级变化，不增加RX忙等，也不改RMM身份、根／映射检查或GPU完成条件。同一个work对象的串行执行、取消等待、排空和ACK／ARM后重查保留；完整结果不能据ED或局部代码推定。

先重建普通Proxy，可执行代码18,546,688字节与冻结Proxy逐字相同；完整Image只相差44字节，位于两处构建版本文字和build-id。候选实际ARM64编译退出0，反汇编重定位确认使用`system_highpri_wq`。本地补丁清单校验退出0；未修改RMM，未重复运行其633标记模型套件，也没有为单行排队变化新增复述实现的测试。相关证据为`proxy-rx-priority-ek/{normal-rebuild-comparison-details,build-validation}.json`及构建命令／退出记录。冻结包只有`proxy-Image`变化，正常重建Image用于离线对照，未部署。

硬件命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ek -- \
 python3 build/rmm-client-bo-20261030/proxy-rx-priority-ek/run.py measure
```

其内部执行`run-realm-xshm.py --images build/rmm-client-bo-20261030/proxy-rx-priority-ek/candidate --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`，外层退出1。全部33场景完成，validation仍26成功／1既有数值例外／6无判据；VM退出0／0，预热计算／基本IOCTL及CPU SIGNAL eventfd冒烟、两端解绑／内核日志、Host健康和资源恢复检查通过。该eventfd冒烟不证明真实GPU完成eventfd。blur／terrain／5×5 effect2d为152／28／745FPS，预设下限141／26／670，场景保护通过。11份日志均已拉回并核验SHA；分段墙钟与逐场景对照见`{hardware,phases,scene-comparison}.json`，不能当作纯CPU成本或逐任务GPU时间。

恢复独占运行`private-proxy-rx-priority-restore-20261101-ek`退出0，只恢复原冻结Proxy Image；随后恢复本轮唯一源码并刷新mtime。最终核验138项源码、四项实际Guest输入和SD2原DA固件字节，板端恢复CPU0–1／pmthor，无VM与loop遗留。证据`{decision,final-verification,runtime-restoration}.json`；恢复后无新增GPU测量，当前引用934分仍是ED此前实测。Proxy增量构建目录仍可能保存本轮Image，下一轮须用冻结包或重新构建，不能直接沿用缓存。

另完成设备事件路径审查：私有固件boot将GPU／MMU／JOB IRQ mask全部置零，stream／group准备也不启用ACK IRQ mask；当前Client由FINISH轮询和RMM真实完成检查推进。现有xshm IRQ127是通信唤醒，不能直接当作GPU完成事件。事件辅助优化需要建立设备事件到Client worker的调度路径，并保留丢通知回退、OOM处理、绝对期限与完整FINISH；本轮未实现或测量该方向。索引补入CI728→718的同次FINISH否定观察失败，避免与CU轻量提示混淆后重复尝试。

本轮只新增一次完整720p性能测量。广泛API／ML／多Client、实际GPU完成eventfd、恶意并发／撤销与旧映射验收均NOT_RUN；历史AE VM_BIND EBUSY、额外Group submit超时及数值例外保留，不由本轮PASS覆盖。整体目标继续未完成。


## EL：补齐选任务与STAGE准入计时，936分诊断，恢复ED934（2026-11-01）

统一记录：定位现有阶段统计遗漏的准入区间｜ED确认轮934 → 临时计时EL936｜+2分／+0.21%，只作诊断，不是优化收益｜同一单Client完整720p／33场景、GPU实际594MHz、CPU自动，只有Client Image增加计时；RMM／Proxy／Host／initrd／DX runner不变，无固件写入或Host重启｜下述run-id、命令、退出码与日志｜临时实现全部撤下，保留ED934；1000门槛FAIL，整体未完成。

EH／EI分别测量RPC与DISPATCH内部，已有PRIVATE_PHASE明确不包含任务选择和STAGE。本轮在实际Client worker增加两个独立只读计时桶：PICK覆盖`private_pick()`；STAGE覆盖命令数组准备和`realm_gpu_task_stage()`，包含私有快照、内存分配、锁、进入RMM及映射／对象授权。计时和计数不参与任务选择、启动、完成或权限决策；只在workqueue排空销毁后逐文件输出，未增加逐任务打印。

| 区间 | 次数 | 累计墙钟 | µs／退休批 |
| --- | ---: | ---: | ---: |
| PICK | 355078，其中11次未选中 | 0.330s | 0.929 |
| STAGE | 355067，错误0 | 5.234s | 14.742 |
| PREPARE，原有统计 | 355067 | — | 137.496 |
| COMPLETE，原有统计 | 355067批退休，查询／批2.461 | — | 198.954 |
| COMPLETE间隔，原有统计 | — | — | 265.789 |

独立解析器按时间戳及完整字段去重，本次没有重复行；只有同一文件最终两个桶，紧邻唯一PRIVATE_PHASE组。成功PICK数、成功STAGE数、PREPARE数与COMPLETE calls−again均为355067，一致；最大单次PICK126.292µs、STAGE2867.083µs。未选中计数不代表准入失败。统计覆盖预热／validation／计分和清理，包含抢占、锁及设备交互，不能当作纯CPU profile、相互独立的应用耗时占比或可全部消除的延迟。COMPLETE本来已包括归还／退休和run_finish／fence释放，不能再重复计入；EH／EI异轮数据也不能直接相减。

结果不支持优先重写picker，或仅因整页快照／分配操作存在就优先做准入流水线。STAGE约14.74µs，明显小于提交及完成路径；预先STAGE还涉及冻结映射、任务容量、依赖与撤销，不可把时间搬到另一处便宣称加速。源码审查另确认Client的`gpu_call_locked()`对小命令快照仍clean整张4KiB页；本轮未单独计时其成本，未实现缩小范围或快照复用，不能据此预测收益。下一步优先围绕实际PREPARE和FINISH／worker协作做有证据的结构优化；设备事件唤醒尚未实现，现有通信IRQ不能冒充GPU完成。

本地命令`python3 scripts/check/check-gpu-private-submit.py`退出0，实际Client planner／worker113项通过，包含独立单tick时钟的PICK／STAGE次数、累计／最大耗时与失败计数断言；模型不证明Linux并发或GPU执行。补丁清单检查及Client ARM64 `make ... Image`均退出0，实际命令／日志见`{submit,patches,client-build}-command.json`、对应exit与log。正常重建Client的18,415,616字节可执行段与ED冻结Image逐字相同，完整Image的32个差异字节仅为构建版本／build-id。候选包只有Client Image变化，冻结179项输入。首次apply空行匹配失败、随后误启动的未改基线构建和记录脚本命名错误分别保留于`failed-and-not-run.json`，未作为候选部署或通过证据。

硬件命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-el -- \
 python3 build/rmm-client-bo-20261030/admission-cost-el/run.py measure
```

外层退出1，原因是936低于1000；33场景完成，validation26成功／1既有数值例外／6无判据，VM0／0。预热计算、基本IOCTL与CPU SIGNAL eventfd冒烟、两端解绑／内核日志、Host健康和资源恢复通过，11份证据SHA核验；此eventfd不证明真实GPU完成通知。blur／terrain／5×5 effect2d为152／28／744FPS，下限141／26／670通过。整轮CPU瞬时采样464次为1.8GHz、另外各1次为1.416／1.608／1.2GHz，未固定CPU，不能将单轮+2分归因于计时改动。

恢复运行`private-admission-cost-restore-20261101-el`退出0，只恢复原冻结ED Client Image；随后恢复本轮两个源码并刷新mtime。最终138项源码、四项实际Guest输入与原DA固件SD2字节匹配，Host恢复CPU0–1／pmthor，无VM或loop遗留。恢复后没有新增GPU测量，当前934仍引用ED此前确认轮；Client构建缓存仍可能保存诊断Image，下一轮须重新构建或使用冻结包。证据`admission-cost-el/{hardware,admission-summary,decision,final-verification,runtime-restoration}.json`；完整日志`build/lab-runs/private-heap-720-20261101-el/`。

广泛API／ML／多Client、真实GPU完成eventfd、恶意并发／撤销／旧映射隔离均NOT_RUN；AE VM_BIND EBUSY、历史Group submit超时和既有数值例外继续保留。未因此沿用旧PASS或宣称整体完成。


## EM：硬件能力快照缓存被现有拒绝语义否定，未部署（2026-11-01）

统一记录：减少运行配置检查中的重复硬件能力读取｜ED934 → 本轮未测｜分差／百分比不适用｜只在独立副本编译候选，生产运行源码／冻结包未改，无板端连接、固件构建或部署｜下述命令、退出码与日志｜本地拒绝候选，当前保留DA RMM＋ED Client＋DX runner／历史934分；1000门槛与整体目标仍未完成。**未改运行代码，无新增性能测量，不据此宣称提分。**

DV显示运行AS检查中firmware configuration约占该计时区间58.95%，EL进一步排除任务选择／STAGE为优先瓶颈。本轮建立`device-caps-em/candidate-platform.c`隔离副本：由RMM在成功固件安装后验证并保存GPU_ID、MMU格式、AS可用位图、shader／tiler几何，每次install或reset先失效，包括失败复位；页表根、内存属性、MCU状态、coherency、动态故障及计数器仍逐调用读取。假设来自硬件只读发现寄存器，未缓存根／运行证明，也未重试BT／DI／EJ的检查结果复用。这个假设不足以满足当前项目已建立的全部故障拒绝条件，因此没有进入主源码。

先用实际平台＋固件／私有PT后端编译并运行前后对照：基线编译／运行均0；候选编译0、运行−6，首先在`prepare_mmio()`中“安装后AS可用位变化，配置前必须拒绝且不能写寄存器”的断言失败。原回归不作修改，没有为了让缓存通过而删除断言。独立的34项平台模型覆盖初始化、全部可变根／属性／动态故障、成功与失败reset、install失效，前后均通过，模型每次running检查MMIO读取31→23；**这仅说明该较窄模型未覆盖后安装的能力故障，不能把它当作候选整体通过或真实性能数据**。

随后补齐独立公开API对照，在安装成功后分别改变设备型号、MMU格式、AS可用位、全零shader mask、tiler数量和高位mask六类输入：基线6/6拒绝，候选6/6接受；两者都没有在这些只读检查中写MMIO。此结果确认缓存改变了现有运行期能力／故障拒绝语义。真实硬件只读寄存器不由Client正常写入，不能把主机模型中改寄存器的结果直接表述为实体Client攻击；但在当前设计与回归边界下，不能以“只读能力可视作常量”为由弱化这些检查。本候选整个撤下，不继续缩小常数或重复部署测试。

执行与证据（所有命令从仓库根目录）：

- `python3 build/rmm-client-bo-20261030/device-caps-em/check-backend.py`记录前后完整编译／运行命令；脚本本身退出0只表示记录完成，内部候选运行−6是产品回归失败。见`backend-results.json`和`{baseline,candidate}-backend-{build,run}.log`。
- `python3 build/rmm-client-bo-20261030/device-caps-em/check-caps.py`退出0，两个平台模型均34项通过；scope限MMIO／clock／reset替身。见`caps-results.json`及对应日志。
- `python3 build/rmm-client-bo-20261030/device-caps-em/check-late-discovery.py`退出0，含义是独立确认候选六项拒绝语义退化，不是候选通过。见`late-discovery-results.json`和对应源码／日志。
- `python3 build/rmm-client-bo-20261030/device-caps-em/finalize.py`退出0，138项生产源码和ED保留包SHA仍匹配，保存`decision.json`、`final-verification.json`、候选patch、失败证据和37项产物清单。没有板端接触，本轮不声称重新读回物理Guest／SD；前次EL的恢复读回证据保留。

ARM64 RMM／FIT构建、固件部署、完整720p及API／ML／多Client均NOT_RUN，不把有限平台模型代替整体验收。初步事件路径审查确认：原pmthor irqfd已经由VMM连接到Proxy，但当前隔离Proxy不注册原生GPU IRQ handler，RMM也将三类设备IRQ mask置零。后续若做事件辅助完成推进，需同时接通RMM事件清除／重查、Proxy到Client通知和Client有界唤醒／丢通知回退，并保留完整FINISH作为完成／归还／退休权威；仅打开IRQ mask不能形成优化。该事件路径本轮未实现。


## EN：设备事件辅助完成的可信确认原型通过离线验证，尚未接通 Guest（2026-11-01）

统一记录：为减少重复完成查询，验证设备事件确认的前置机制｜ED934 → 本轮未测｜分差／百分比不适用｜只在`build/rmm-client-bo-20261030/device-events-en/`生成隔离候选，未改运行代码，无新增性能测量，不据此宣称提分｜下述命令、退出码及日志｜仅保留为离线原型；运行仍为DA RMM＋ED Client＋DX runner／历史934分，1000门槛与整体目标未完成。

EB表明绝大多数pending观察是成员进度未满；EL给出COMPLETE198.954µs和相邻调用间隔265.789µs／累计退休批。它们包含设备交互、调度和计时扰动，不能等同于可消除的CPU成本。本轮不重复EC的分阶段STATUS或CU的额外序号查询，而是在真实JOB IRQ已有Host/VMM转发的前提下，先验证RMM事件确认是否能够保持原完成／归还／退休语义。

隔离候选给firmware ops增加固定JOB事件回调：ARM必须在FW_CONFIGURED且没有已准备硬件组时调用；DRAIN先屏蔽并清除初始中断位，再扫描实际RMM Group/Task绑定的CSG接口，最后重新启用时不清除新位。这样确认期间到达的新事件可以保留到下一次处理。只确认CSG异步事件和`cs_irq_ack`；子CS的OOM/FAULT/FATAL及完整FINISH处理不被替代。CSG input/output[3]分别为cs_irq_ack/cs_irq_req，[2]为doorbell，不能混用。31组／32队列的位移边界、重复／伪造／过期绑定、确认期间新事件和动态故障都有专门用例。

平台回调只允许JOB_INT_MASK/JOB_INT_CLEAR写入，排除boot/global位，不清除GPU/MMU故障；在两侧新鲜检查实际固件根、属性、MCU、coherency、shader/tiler与故障。事件核心只返回调度提示，不修改任务完成字、缓存归还、AS配置或资源生命周期。实际后端的活跃双Client插入事件后，原取消／BO释放仍被拒绝，OOM仍待原heap路径处理；sync提示后原完整completion／return／retirement继续运行。**这些是CPU/MMIO/MCU替身结果，不证明物理IRQ、Linux并发、真实GPU执行或加速。**

执行与证据：

- `python3 build/rmm-client-bo-20261030/device-events-en/check.py`：原始生产后端与未臂候选后端编译／运行均0，初版61项事件模型通过；最终版本由下述命令重验为62项。完整命令及退出码见`model-results.json`。
- `python3 build/rmm-client-bo-20261030/device-events-en/check-platform.py`退出0，平台事件模型23项通过；见`platform-results.json`和`platform-event-{build,run}.log`。
- `python3 build/rmm-client-bo-20261030/device-events-en/check-armed.py`：初版因原模型仍要求CS/CSG IRQ mask为0而运行−6；失败证据保留在`armed-backend-run-initial.log`。独立armed变体只将4处精确掩码期望更新为CS=0xcc000000、CSG=0xb0000000，global仍0，其他归属／故障拒绝／完成／生命周期断言保留；随后编译／运行0/0。原始生产后端测试源码未改。
- `python3 build/rmm-client-bo-20261030/device-events-en/check-final.py`退出0：固定输入SHA，最终事件模型62项、实际后端启用掩码并注入运行期事件的完整变体均编译／运行0/0。后者279条`EN_RUNNING_EVENTS=PASS`是不同生命周期运行中的模型标记，不是279次独立硬件测试。命令／退出码见`final-check-results.json`及`running-event-backend-results.json`，原失败和前版本日志均保留。
- `python3 build/rmm-client-bo-20261030/device-events-en/finalize.py`退出0：138项生产源码和8项ED保留包内容SHA不变，生成候选patch、决策、输入／产物清单与checkpoint。没有板端连接，本轮未重新读回物理Guest或SD，EL的恢复读回证据保留。

当前尚未实现RSI事件ABI、Proxy threaded IRQ接收、跨VM提示及Client唤醒／回调生命周期。它们必须一起接通，不能只部署掩码候选；详细接口、锁顺序、ARM时机和重复bootstrap注意事项见隔离目录`integration-next.md`。通知只能打断现有等待或提前排队原FINISH，保留绝对deadline、轮询回退、OOM服务和所有真实完成检查。ARM64 RMM/FIT/Guest构建、固件部署、完整720p以及API／ML／多Client硬件均NOT_RUN；也尚未证明GPU terminal sync确实产生预期IRQ。完整连接后按ED934同条件对照，预设候选保留线944、总门槛1000及既有场景保护，未测量前不称为保留优化。


## EO：事件确认、Proxy通知与Client唤醒完整接通，878分撤回并恢复ED（2026-11-01）

统一记录：通过真实设备事件提前执行既有完成检查｜ED历史934 → EO878｜−56／−6.00%｜同完整720p、33场景、null-noop／finish、Host opp3、GPU请求600MHz／实际594MHz、CPU0–3／Proxy1／Client2，CPU未锁恒频；RMM、双Guest及bootstrap工具组合变化，本轮刷写SD2并重启，对照来自此前ED确认轮，不能归因为单项或统计稳定收益｜`private-heap-720-20261101-eo`，外层退出1，日志`build/rmm-client-bo-20261030/event-wake-eo/measure.log`及`build/lab-runs/private-heap-720-20261101-eo/realm-evidence/`｜未达预设944保留线及1000门槛，已撤回并核验恢复DA RMM＋ED Client＋DX runner。**当前934仍引用历史实测，回退后没有新增GPU测量；整体目标未完成。**

本轮将EN隔离原型接成完整候选：新增仅认证隔离service可调用的FW_EVENTS能力／RSI，保留参数必须为0，重复ARM只在已经启用时幂等返回，不能改写活动掩码；metadata服务在解除MMIO映射后注册独立JOB threaded IRQ，handler就绪且FW_CONFIGURE完成后才ARM。RMM确认受保护CSG事件后释放Guest GPU API锁，再由Proxy按引用存活的会话发送提示，每次最多轮转32个会话、每会话一次发送，满队列不循环等待。Client用私有接收副本处理reply_to=0消息，不消费RPC栈waiter；核验类型／长度／保留位和session，只原子合并提示并唤醒原worker，回调不取得GPU mutex或递归RPC。解绑先同步移除回调再停止workqueue。原50µs／200µs／八次短等、绝对deadline、轮询回退、完整FINISH／OOM处理／CPU归还／退休条件均保留；未设置全设备机密执行能力位。

实机确认`GPU_RMM_EVENTS=ARMED`，Client会话4接受33958条提示，说明这轮实际贯通通知路径；它们可能来自sync／idle／子事件，不能逐条等同于任务完成或认证设备来源的证明。完整33场景、validation26成功／1已知数值例外／6无判据、两VM退出0/0、内核健康、资源恢复及11份日志SHA核验完成。外层退出1的原因是分数低于1000，不能记为整体验收PASS。

| 指标 | ED此前确认轮 | EO | 说明 |
| --- | ---: | ---: | --- |
| glmark总分 | 934 | 878 | −56／−6.00%，未达944保留线 |
| FINISH查询／累计退休批 | 2.4636 | 2.5529 | +3.62%，事件未减少查询 |
| COMPLETE调用墙钟／退休批 | 199.440µs | 206.875µs | +3.73% |
| COMPLETE相邻worker观察间隔／退休批 | 263.794µs | 247.531µs | −6.17%，局部下降没有变成整体收益 |
| PREPARE调用墙钟／退休批 | 138.752µs | 138.544µs | 基本不变 |
| blur／terrain／5×5 effect2d FPS | 153／28／744 | 140／26／721 | 预设保护线141／26／670；blur失败 |

阶段指标是包含预热／校验及调度影响的累计墙钟，不是纯CPU成本或GPU完成到fence可见的实测延迟。多数高帧率场景退化，例如build/VBO 1415→1278、nearest texture 1414→1287；refract 50→92的局部改善不足以抵消整套退化。两轮CPU均未锁恒频，本轮全程样本还含重启后的冷输入读取与启动，不能直接以整程频率样本占比解释场景性能，也不能将本轮差值精确分摊给RMM检查、物理IRQ或跨VM通知。后续重试须先证明事件来源／触发时机、合并和额外处理成本，不能因间隔变短就保留，或仅换等待常数重做。

执行和证据均在`build/rmm-client-bo-20261030/event-wake-eo/`：

- `build-rmm.py`、`build-guest.py client`、`build-guest.py proxy`、`build-firmware.py`均退出0；O2 Debug断言及23份RMM构建flags与原配置保持，Guest和FIT／ELF布局、补丁清单检查通过。`freeze.py`退出0，固定149项源码、167项运行／构建输入；initrd仅替换bootstrap工具，runner、Host和其他用户态不变。源码候选及精确diff保存在`candidate-source/`、`diff/`，不作为当前实现。
- `bash scripts/check/check-rmm-gpu-private.sh`最终退出0，642条PASS标记；其中事件63项、平台23项、实际Client worker124项、metadata服务28项及Proxy任务桥151项。`check-armed.py --inject`编译／运行0/0，保留原后端全部完成／故障拒绝／生命周期条件。初次套件因新增字段未补齐测试替身而编译失败，证据保存在`private-suite-initial.log`；修正替身后重跑完整套件，不隐藏该失败。模型不证明Linux并发或实体隔离。
- 候选部署：`lab-run.py --run-id private-event-wake-deploy-20261101-eo --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-event-wake-eo --run-id private-event-wake-deploy-20261101-eo`，退出0。只写SD2固件；Host内核及模块未改。
- 测量：`lab-run.py --run-id private-heap-720-20261101-eo -- python3 build/rmm-client-bo-20261030/event-wake-eo/run.py measure`，退出1；内部为冻结候选的`run-realm-xshm.py --private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。完整命令／退出码见`measure-command.json`、`measure-exit.json`和`benchmark-command.json`，结果见`hardware.json`、`scene-comparison.json`、`phases.json`。
- 回退：`restore-source.py`退出0，31项候选改动精确撤回、145项原源码SHA匹配；恢复后的submit／service／补丁检查均退出0。原固件经run-id `private-event-wake-restore-fw-20261101-eo`刷回SD2并启动，退出0；原四项Guest输入经`private-event-wake-restore-guest-20261101-eo`恢复，退出0。实际SD范围和四项Guest哈希、8项本地ED冻结内容、Host CPU0–1／pmthor／无VM及loop均已核验。见`runtime-restoration.json`、`source-restoration.json`、`restored-checks.json`及`final-verification.json`。

API、ML、多Client硬件均NOT_RUN，遵守1000门槛。当前没有保留EO新运行代码；EN原型和本轮失败实现／日志仅为后续研究证据，不能沿用为已完成的事件优化或安全保证。

## EP：双 vCPU Client 并发配置在首个计算检查停滞，撤回（2026-11-01）

统一记录：尝试让 Client 应用与 GPU 推进 worker 并行｜ED 历史934 → EP无分数｜分差及百分比不适用，glmark与validation均NOT_RUN｜同DA RMM、ED双Guest、initrd、Host opp3与GPU请求600MHz／实际594MHz；只改冻结runner，Client vCPU由1增至2、Host允许CPU2扩至2–3，并将双VM的非vCPU线程移至CPU0；不能视为等CPU资源的算法对照｜`private-heap-720-20261101-ep`，外层退出1，日志`build/rmm-client-bo-20261030/client-smp-ep/measure.log`与`build/lab-runs/private-heap-720-20261101-ep/realm-evidence/`｜候选否决，已恢复ED输入并重启清除失败运行状态；整体目标未完成。

**目的与变更范围。** ED已证明单vCPU中高优先级GPU worker有收益，本轮进一步检查增加可并行执行的Client CPU是否有用。候选仅保存在`client-smp-ep/candidate/`，原生产runner、Client／Proxy／RMM源码不改；相对ED八项冻结输入只有`runner.py`变化。实际vCPU线程记录确认Proxy一个vCPU允许Host CPU1、Client两个vCPU允许Host CPU2–3，VMM非vCPU线程均在CPU0。该配置不能单独分离vCPU数量、CPU位置和I/O线程分离的效果。

**本地验证与实机失败。** 原生产runner离线37项检查退出0；直接提取候选`isolate_vmm_io()`，以临时task目录和affinity替身验证1／2个vCPU均保留原允许CPU集合、只有非vCPU线程移至CPU0。这不是多核硬件正确性证明。实际双REC启动、可信GPU服务配置、控制池与基础DRM／CPU_SIGNAL eventfd探针完成；随后renderer qualification中的`gles-compute-smoke --count 1 --iterations 1 --warmup 0`持续无结果，尚未进入glmark计分。Client日志最后一次变化后约239.82秒，核对准确PID和本run命令行后仅向本runner发送SIGINT，让其保存诊断；Client诊断命令亦超时，再仅终止本run的Client Firecracker，未使用全局kill。

**清理失败必须保留。** VM退出0／−15，Client kernel-log超时，pool-unbind和mem-revoke出现EBUSY；Host新增两条`kvm_destroy_realm()`中`realm_unmap_range()`失败的WARNING，内核健康FAIL。虽无残留VM／loop且CPU集合恢复0–1，不能据此称完整回收成功。9份远端证据已逐项SHA验证。没有Client内核转储，不能把停滞归因于某个驱动锁、通知机制、RMM或物理CPU；也不能将已有REC0绑定约束解除作为性能修复。

**恢复与复测。** `private-client-smp-restore-20261101-ep`退出0，四项Guest输入与原DA固件实际SD2范围读回一致。鉴于RTT teardown失败，另通过`lab-run.py --allow-rk-reboot`执行`private-client-smp-recover-20261101-ep`，退出0：只重启，不写固件／内核，保存前后dmesg与UART，启动ID变化，RME capability=1、pmthor及CPU0–1恢复，启动后无WARNING／BUG；实际SD2与原ED输入再次核验。随后用未修改ED包启动完整720p恢复对照`private-heap-720-20261101-ep-control`；其最终分数及健康判定见后续EQ节与`control-hardware.json`，不能从恢复命令退出0提前继承GPU测试PASS。

部署前第一次认证harness仍引用旧ED证据目录，被“拒绝覆盖已有证据”断言阻止，未执行板端操作；已修正实验路径，保留`development-failures.json`。本轮没有修改生产运行代码；新增硬件失败证据不构成提分。API／ML／多Client硬件仍NOT_RUN，1000门槛未通过，AE EBUSY与实体隔离验收未完成。

## EQ：单 vCPU 下分离 VMM I/O 线程，929→928分，撤回（2026-11-01）

统一记录：减少VMM I/O与Realm vCPU的CPU竞争｜刚完成的ED929 → EQ928｜−1／−0.11%｜完整720p、33场景、null-noop／finish、同Host opp3、DA RMM、ED双Guest与initrd，Proxy与Client各一个vCPU且分别保持Host CPU1／CPU2，GPU请求600MHz／实际594MHz；只把非vCPU线程移到CPU0，两轮之间无重启，CPU未锁恒频｜对照`private-heap-720-20261101-ep-control`、候选`private-heap-720-20261101-eq`均外层退出1，分别见`build/rmm-client-bo-20261030/client-smp-ep/control.log`、`eq-measure.log`及各run的`realm-evidence/`｜未达预先944分保留线及1000门槛，撤回EQ，保留ED；整体目标未完成。

**先完成恢复对照。** EP失败后的同固件重启完成后，用未修改ED冻结包跑完整720p，得到929分。与该包此前934分相比−5／−0.54%，两轮代码相同，不能归因为优化或某次重启的确定影响。33场景、VM退出0／0、Host及Guest健康／完整资源回收、11份日志SHA通过；validation仍为26／1／6，不是全部图像正确性PASS。该轮重新验证了单vCPU路径能够完成首个真实计算及整套工作负载，也保留EP的多核停滞与回收失败，不能认为后者已修复。

**候选为何不同于EP。** 复用runner已有的`isolate_vmm_io()`，仅在并行／顺序启动后的两个调用条件中纳入private模式。原函数、vCPU数量、vCPU允许CPU集合、RMM／Guest／Host数据路径与安全检查全部不改。实际线程记录确认Proxy vCPU在CPU1、Client vCPU在CPU2，两VM的其他线程在CPU0；这单独检查I/O线程竞争，不再引入多REC并发。候选在独立`vmm-io-eq/candidate/`冻结，相对ED八项输入只有runner变化；未改生产运行源码。

**预先保留条件。** 总分至少`max(944, ceil(本轮ED对照×1.01))`，并保留blur≥141、terrain≥26、5×5 effect2d≥670；随后才看1000门槛。条件在EQ上板前冻结于`plan.json`，未按结果降低。将实际候选runner接入现有离线检查，37项退出0，日志`vmm-io-eq/runner-check.log`；它们使用串口／设备替身，不证明实际GPU正确性。

**实机结果。** EQ完整33场景，928分；blur152、terrain28、5×5 effect2d744，保护线通过。VM退出0／0、内核健康、资源回收及11份证据SHA核验通过；validation26／1／6保留，外层退出1因为总分低于1000。没有测得满足保留条件的整体收益，不从−0.11%单轮变化推断稳定退化。

| 累计指标，按各自退休批归一化 | ED对照929 | EQ928 | 变化 |
| --- | ---: | ---: | ---: |
| FINISH查询次数／批 | 2.467254 | 2.460692 | −0.27% |
| PREPARE墙钟／批 | 138.088µs | 137.154µs | −0.68% |
| COMPLETE调用墙钟／批 | 199.516µs | 199.819µs | +0.15% |
| COMPLETE观察间隔／批 | 266.565µs | 267.522µs | +0.36% |

这些累计值包含预热／校验、RMM／RPC／设备交互及调度，不能当作纯CPU时间、GPU执行时间或可直接相减的通信开销。全程频率采样含不同的冷输入读取／启动阶段，不根据采样占比解释提分；正式配置为相同自动策略，未锁CPU恒频。本轮没有重测Native，不能更新Native性能保留率。

**恢复与证据。** `private-vmm-io-restore-20261101-eq`退出0，仅同步变化的ED runner，并读回核验四项Guest输入与实际SD2固件；最终再次核验145项生产输入、各18项EP／EQ冻结输入及8项ED包，无残留VM／loop，Host为CPU0–1／pmthor。最终状态以`vmm-io-eq/runtime-restoration.json`、`final-verification.json`、`decision.json`为准。候选及完整失败／计分证据留在忽略的build目录，生产源码保持ED。回退后未新增GPU测量；当前保留版本最新实测929，934为此前确认轮。API／ML／多Client完整硬件矩阵仍NOT_RUN，1000门槛FAIL，AE EBUSY、多Client与实体隔离等验收未完成。

## ER：完成等待按窗口对账，排队仅3.23µs／批，无新增GPU测量（2026-11-01）

统一记录：避免把整个COMPLETE观察间隔误认为线程切换开销｜当前ED最新929分（历史934）→ 本轮未测｜分差及百分比不适用｜只分析已采集日志，未改运行代码，无新增性能测量，不据此宣称提分｜下述四份原run、分析命令及退出码见`build/rmm-client-bo-20261030/completion-accounting-er/commands.json`｜保留分析工具与证据；DA RMM＋ED Client／Proxy＋原DX runner保持，1000门槛与整体安全验收未完成。

新增`scripts/analysis/analyze-private-gpu-windows.py`：先核对采集清单中Client日志与summary的SHA，再要求完整33场景、无工作负载错误及VM退出0／0；保留原validation和低于1000的失败，不要求把原run改为PASS。对同一私有文件的最终阶段／等待统计与每1024批窗口进行对账，重复记录只在内容与时间完全相同时去重；计数回退、缺字段、冲突副本、最终计数不符或等待分量超过间隔时拒绝。日志环覆盖前缀和末尾不足1024批的尾段明确标记，不补造窗口。不同文件的统计若有差异则拒绝，无法从这些无文件ID的记录认证多个完全相同的独立文件。

| 原run／分数 | COMPLETE间隔µs／退休批 | 主动暂停µs／批 | 普通延迟重排µs／批 | 立即排队µs／批 | 立即排队占已统计阶段墙钟 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ED确认轮／934 | 263.794 | 236.881 | 22.679 | 3.145 | 0.522% |
| EP恢复后的ED／929 | 266.565 | 239.489 | 22.753 | 3.232 | 0.535% |
| EQ线程分离／928，已撤回 | 267.522 | 240.411 | 22.833 | 3.249 | 0.538% |
| EO事件唤醒／878，已撤回 | 247.531 | 237.206 | 5.944 | 3.174 | 0.535% |

ED929的间隔中，主动暂停89.843%、普通延迟重排8.536%、立即排队1.212%、入口取锁0.136%、重取锁0.004%，剩余0.269%是未细分的调度／记账区间，不能强行归到某个组件。PREPARE为138.088µs／退休批、COMPLETE调用199.516µs／批、查询2.467次／批。主动暂停内包含首次观察前164.619µs／批及后续74.871µs／批；字段名`sleep_ns`在这条基线上实际测量`cpu_relax()`主动等待，不是睡眠时间。以上含预热／validation、RPC／RMM、设备交互和抢占，不是纯CPU成本，也不是计分窗口内的逐任务设备执行时间。

**新的定位依据。** 约267µs的COMPLETE间隔主要不在workqueue排队；立即排队只占已选任务阶段墙钟约0.535%，因此不能把整个间隔当作内联调度可消除的收益。这是观测组成，既不是Amdahl应用加速上界，也不证明其他负载中排队不重要。主动暂停与延迟重排又可能覆盖GPU实际执行，不能直接删除。EO的观察间隔更短但整套分数更低，也说明间隔下降本身不构成提分。

ED929保存225份窗口，首份已累计122880批、末份352256批，最终352459批；因此没有前122880批的窗口细分，末尾203批只有最终总账。已保存窗口中，延迟重排最重的10个区间合计6.728秒，占全文件8.019秒的83.892%。其中最重的五个连续区间位于Guest内核时钟约300.253–308.137秒，分别约972–983µs／批，远高于全文件22.753µs／批；这些是每1024批区间平均值，不是单任务延迟分位数。它们支持后续先定位局部慢路径，而非全局调整所有队列等待常数。**现有glmark进度消息没有同一Guest内核时钟，只含粗粒度elapsed与最后完成的场景名；不能可靠映射到某个具体场景，更不能声称这几个区间属于ResNet50。** 下一次诊断需要先补同一时钟的场景边界，再检查局部pending、ACK等待与timer回退。

验证与边界：

- 四份历史run：`private-heap-720-20261101-ed-repeat`、`private-heap-720-20261101-ep-control`、`private-heap-720-20261101-eq`、`private-heap-720-20261101-eo`，分析命令分别退出0，共核验953份窗口，输出`ed934.json`、`ed929.json`、`eq928.json`和`eo878.json`。这四轮原计分外层均因1000门槛退出1，validation均26／1／6；不是本轮新增运行，也不消除EP多核失败。
- `python3 build/rmm-client-bo-20261030/completion-accounting-er/check.py`退出0，17项解析／对账检查通过，包含实际CLI拒绝哈希不符、冲突副本、回退、缺字段、缺窗口显式报告及多worker差异拒绝；见`checks.json`。仅证明解析器处理这些输入，不证明GPU或机密隔离。
- EF937格式包含第六类高精度等待桶，且没有输出未使用的普通延迟桶，当前五类解析器明确拒绝，不静默遗漏等待。原分析退出1和重现日志保留于`failed-and-not-run.json`、`ef937-rejected.log`；没有为EF生成报告，不据此否定原EF硬件结果。
- 145项原生产输入与8项ED冻结包最终SHA核验一致；新增内容只有离线分析工具和文档。未连接板端、未部署或运行新GPU测试；API／ML／多Client、恶意并发／撤销、真实GPU完成eventfd与实体隔离等未验收项保持。证据见`decision.json`、`final-verification.json`与`checkpoint.json`。


## ES：场景快照诊断933分，发现并保留时钟域缺口（2026-11-01）

统一记录：为ER慢窗口补充场景位置｜ED最新929 → ES933｜+4分／+0.43%｜完整720p、同DA RMM／ED双Guest／Host opp3／DX runner，GPU请求600MHz／实际594MHz，CPU自动频率；只在initrd加入只读静态场景快照工具，沿用5秒采样，无固件写入或重启｜测量`private-heap-720-20261101-es`退出1，恢复`private-vmm-io-restore-20261101-es`退出0，命令与日志见`build/rmm-client-bo-20261030/scene-clock-es/`及对应`build/lab-runs/`｜诊断始终撤下，分数变化不作为优化收益；1000门槛与整体目标未完成。

工具在Guest内用CLOCK_MONOTONIC夹住对glmark原始输出的读取，记录已完成场景数、未完成场景前缀、文件device／inode及长度；最多读取128KiB，失败不改变工作负载结果。只有两个快照的场景前缀精确匹配、完成计数相同且文件身份连续时，才允许形成保守场景区间，转场和不完整前缀不插值。7组helper检查覆盖99个场景样本；离线关联器补充19项检查，包括时钟回退、缺字段、文件替换、截断、窗口身份不匹配及缺显式单调时间的拒绝。

**本轮场景归属不成立。** 复查发现内核printk前缀来自local_clock()，而helper使用CLOCK_MONOTONIC；不能因二者看似都是开机时间便直接拼接。`scripts/analysis/analyze-private-gpu-scenes.py`已要求PRIVATE_WINDOW显式提供ktime_get_ns()的mono_ns，禁止估算时差；ES实测日志因此按预期拒绝，`scenes-analysis-exit.json`为1，没有生成场景关联报告。原计划中的“同钟”意图不等于实测证据，这个失败与最初后处理对不存在thread_affinity字段的错误假设均保留于`failed-and-not-run.json`。下一轮ET只增加显式统计时钟，不改变执行策略。

ES完整33场景、VM0／0、预热／basic／CPU SIGNAL-eventfd冒烟、两端解绑及kernel-log、Host健康与资源恢复通过；validation仍26通过／1既有异常／6无判据，不能称所有图像正确性通过。外层因933低于1000退出1。11份采集文件SHA核验完成；ER方式的总账／窗口分析退出0：COMPLETE间隔265.822µs／退休批，其中主动暂停238.811、普通延迟重排22.708、立即排队3.190µs；这些含GPU执行重叠与调度，不能当成纯CPU或全可省开销，也不能据无认证时钟给窗口指定场景。

恢复只上传原ED initrd，随后核验四项板端Guest及实际SD2两段固件；145项生产输入、25项ES执行输入与8项ED包内容一致，Host恢复CPU0–1／pmthor，无VM／loop。保留离线分析器，未保留新的运行优化；ED最新纯基线仍929、历史确认934，API／ML／多Client未扩展。证据`{hardware,decision,final-verification,runtime-restoration,scene-checks-mono}.json`；恢复后未新增GPU测量。ET另行记录，不能按相同任务编号或Guest时刻从ES跨run补场景。


## ET：显式单调时钟贯通，933分诊断，定位局部完成等待（2026-11-01）

统一记录：修正ES场景归属的时钟域缺口｜ED最新929 → ET933｜+4分／+0.43%｜完整720p、同DA RMM／ED Proxy／Host opp3／DX runner、GPU请求600MHz／实际594MHz、CPU自动频率及原单vCPU布局；仅Client每1024批的PRIVATE_WINDOW日志增加ktime_get_ns()的mono_ns，并使用ES只读场景采样initrd，无固件写入或重启｜测量`private-heap-720-20261101-et`退出1，恢复`private-vmm-io-restore-20261101-et`退出0；下述命令及证据｜诊断已撤下，未保留新运行优化，不据933宣称提分，1000门槛与整体目标未完成。

实际Client planner／worker模型113项、固定补丁清单校验、ARM64 Image构建均退出0；显式时钟关联器19项检查通过，特意让模拟printk时间与mono_ns不一致，证明关联只使用明确单调端点。缺mono_ns、时钟回退、窗口计数／任务身份不一致均拒绝。生产驱动只增加一个日志参数，没有改调度、启动、授权、完成或回收条件；冻结Client Image后即恢复该源码并刷新mtime，诊断仅保存在独立候选目录。

硬件命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-et -- \
  python3 build/rmm-client-bo-20261030/scene-mono-et/run.py measure
python3 scripts/maintenance/lab-run.py --run-id private-vmm-io-restore-20261101-et -- \
  python3 build/rmm-client-bo-20261030/scene-mono-et/restore.py
python3 build/rmm-client-bo-20261030/scene-mono-et/analyze.py
```

测量退出1仅因933低于1000；33场景、预热／basic／CPU SIGNAL-eventfd冒烟、VM0／0、两端解绑／kernel-log、Host健康和资源恢复检查完成，validation仍26通过／1既有异常／6无判据。11份采集文件SHA一致，windows及scenes分析均退出0。CPU SIGNAL不代表真实GPU完成eventfd验收；没有扩大API／ML／多Client矩阵。

**首次有明确同钟的局部场景证据。** 70个场景快照形成33个保守稳定区间；保存222份内核窗口，共226304批窗口增量，其中96256批完整落入稳定区间，覆盖全文件354005批的27.19%，涉及19个场景。场景切换／读快照边界等130048批增量未分配，日志环覆盖的前126976批和尾部725批也不补造；下表不是完整场景平均值或33场景全覆盖profile。大卷积effect2d对应原始kernel的5列×3行（旧记录常简称5×5），仍按精确场景字符串关联。

| 场景（仅完整落入稳定区间的窗口） | 窗口数 | 查询／退休批 | COMPLETE调用µs／批 | COMPLETE间隔µs／批 | 普通延迟重排µs／批 |
| --- | ---: | ---: | ---: | ---: | ---: |
| bump normals | 5 | 1.982 | 155.62 | 171.46 | 0 |
| 大卷积effect2d | 3 | 7.912 | 438.18 | 574.45 | 0 |
| desktop blur | 7 | 2.000 | 154.44 | 158.69 | 0 |
| terrain | 6 | 2.205 | 199.90 | 219.89 | 112.99 |
| refract | 2 | 2.871 | 232.57 | 1127.16 | 975.98 |
| conditionals，fragment／vertex均0 | 6 | 2.099 | 203.05 | 253.07 | 0 |

最慢的两个**已归属**延迟窗口属于refract，约968.6／983.3µs每批；terrain已覆盖窗口也有延迟回退。另有更慢但未完整落入稳定区间的窗口，仍保留未知，不能直接把本轮全部8.011秒延迟等待都归给这两个场景，更不能把这个run的标签填入ES／ER旧日志。大卷积effect2d已覆盖区间查询密度高达7.912，但未进入普通延迟回退，说明它与refract的调度形态不同；全局缩短慢速timer不能解决这类快速查询密集路径。

全文件PREPARE137.673µs／批，COMPLETE调用198.704、间隔265.587µs／批；主动暂停238.655、普通延迟重排22.629、立即排队3.172µs／批，立即排队占已统计阶段0.527%。这些墙钟含GPU执行、RPC／RMM、抢占和有用应用工作，不能作为可直接删去的CPU成本或加速上界。EF已将慢等待从约6.34降至1.33ms，却只934→937且未达保留线；本轮新定位不构成重新只调全局常数的理由。后续须分别验证高查询密度队列的等待策略和长GPU任务的回退时机，并保留真实完成、原期限及错误语义；本轮没有将这些后续设想实现或计为收益。buffer场景本轮没有可关联窗口，不据此解释WC读改写或ML性能。

恢复只上传原ED Client Image和initrd，四项板端Guest及实际SD2固件回读匹配；145项生产输入、28项ET冻结执行输入、8项ED包内容一致，Host为CPU0–1／pmthor，无VM或loop。保留离线分析工具与诊断证据，当前生产仍DA＋ED＋原DX，最新纯基线929／历史934；增量构建目录仍有诊断Image，后续从源码重新构建或使用冻结包，不能冒充ED。证据`build/rmm-client-bo-20261030/scene-mono-et/{hardware,findings,scenes,windows,decision,final-verification}.json`，完整命令／退出码及日志见该目录、`scene-clock-es/et{measure,restore}-*.json`和上述两份lab-run目录。恢复后未新增GPU测量。


## EU：空闲依赖重试由新提交提前调度，933分，撤回恢复ED（2026-11-01）

统一记录：避免独立新任务继承旧依赖重试timer｜本轮紧邻原ED936 → EU933｜−3分／−0.32%｜完整1280×720、33场景、null-noop／finish、单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz，CPU自动频率；仅候选Client Image变化，DA RMM、ED Proxy／initrd、原DX runner及Host opp3相同，无刷写或重启｜对照`private-heap-720-20261101-eu-control`与候选`private-heap-720-20261101-eu`均退出1，恢复`private-vmm-io-restore-20261101-eu`退出0，命令／退出码／日志见`build/rmm-client-bo-20261030/idle-kick-eu/`｜未达预先规则算出的946分保留线，撤回；1000门槛与整体目标未完成。

**候选与边界。** 原GROUP_SUBMIT使用`queue_delayed_work(..., 0)`，无法提前已经挂起的依赖重试timer。本轮仅在没有`private_run`且`timer_pending()`时改用`mod_delayed_work(..., 0)`；其他情况保持原排队方式。它检查新提交能否减少无关依赖造成的准入等待，不修改正在执行任务的八次短查询预算、预测等待、绝对deadline或真实完成条件。与ED优先级、BP连续worker、EO设备事件及EF高精度慢等待不同。真实FINISH、heap处理、错误及fence／对象生命周期不变；六个关键函数与ED逐字节核对一致，见`unchanged-critical-functions.json`。

预先冻结规则为总分≥`max(944, ceil(紧邻ED对照×1.01))`，且blur≥141、terrain≥26、大卷积effect2d≥670。对照936使保留线成为946，没有按结果降低。候选blur152、terrain28、effect2d744，场景保护通过，但总分933不通过。两轮均完整33场景、VM退出0／0、计算预热及basic／CPU SIGNAL-eventfd冒烟、两端解绑／kernel-log、内核健康与资源恢复检查完成，各11份采集文件SHA一致；validation仍26成功／1既有异常／6无判据，不能称全部图像正确性PASS。两轮外层退出1仅因低于1000；没有扩大API／ML／多Client矩阵。

新增计数在候选日志中观测到去重后的每文件值17；日志没有可认证的文件身份，不能把重复值相加成总数，更不能把它等同于任务就绪、避免17次完整timer或节省某个延迟。按各自退休批归一化：PREPARE137.260→137.706µs，COMPLETE调用199.474→199.516µs，间隔266.655→266.514µs，查询2.465407→2.465847次；没有体现主要路径工作量下降。累计值含预热／校验、设备交互及Guest／Host调度，不是纯CPU成本或计分窗口逐任务因果证据，单轮分差也不证明稳定退化。

**本地验证与保留失败。** 实际Client planner／worker模型117项退出0，比原113项增加独立队列提前唤醒、同队列FIFO依赖、活动长任务预算／deadline保持、依赖错误发布四项。原ED代码配新测试按预期拒绝旧timer行为；删除“无活动run”条件的变体被活动预算断言拒绝。模型的workqueue、fence、锁与GPU是替身，不证明Linux真实并发。初次测试因while与assert同一行触发`-Werror=misleading-indentation`，保留`submit-initial-failed.log`，修正格式后通过。最终ARM64 Image构建与固定上游补丁校验退出0；最终包来自加入`timer_pending`条件后的第二次构建，不能用初次构建替代。

实际执行命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-eu-control -- \
  python3 build/rmm-client-bo-20261030/idle-kick-eu/run.py control
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-eu -- \
  python3 build/rmm-client-bo-20261030/idle-kick-eu/run.py measure
python3 scripts/maintenance/lab-run.py --run-id private-vmm-io-restore-20261101-eu -- \
  python3 build/rmm-client-bo-20261030/idle-kick-eu/restore.py
python3 build/rmm-client-bo-20261030/idle-kick-eu/analyze.py candidate
python3 build/rmm-client-bo-20261030/idle-kick-eu/finalize-withdrawn.py
```

分析与finalizer均退出0。恢复仅上传原ED Client Image，核验四项板端Guest与实际SD2 DA固件；finalizer先核验184项冻结候选输入及6项控制脚本，再精确恢复本轮两个源码并刷新mtime，145项原生产输入、两个8项冻结包核验一致，恢复版113项Client模型通过。Host空闲CPU0–1／pmthor，无本次VM或loop。证据入口为`{hardware-control,hardware-candidate,decision,runtime-restoration,final-verification}.json`、`windows-{control,candidate}.json`与各run的`build/lab-runs/<run-id>/`；原失败与未执行项保留。

当前保留版本仍DA＋ED＋原DX，最新纯基线936是本轮对照实测，不是新优化收益；历史929／934保留。恢复后未新增GPU测量；增量构建Image仍是EU候选，后续必须使用冻结ED包或重新构建。1000门槛未通过，AE EBUSY、额外Group submit超时、真实GPU完成eventfd、广泛API／ML／多Client及恶意并发／实体隔离验收仍未完成。后续不重复空闲timer微调；全抢占Client内核中单纯加入`cond_resched()`也缺少额外调度收益依据，未实现或上板。


## EV：复用最后完成检查中的无OOM信息，938分，撤回恢复DA／ED（2026-11-01）

统一记录：减少FINISH未完成后紧接着的HEAP_EVENT重复检查｜本轮紧邻原ED934 → EV938｜+4分／+0.43%｜完整1280×720、33场景、null-noop／finish、单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz，CPU自动频率；RMM和Client一起变化，Host opp3、Proxy、initrd和原DX runner相同，部署候选经过SD2固件写入和Host重启，只归因组合｜对照`private-heap-720-20261101-ev-control`及候选`private-heap-720-20261101-ev`均退出1，部署／恢复及分析退出0；完整命令、退出码与日志见`build/rmm-client-bo-20261030/completion-heap-hint-ev/`及对应lab-run目录｜未达到预先冻结的946分保留线，撤回；1000门槛未通过，整体未完成。

**机制与CW的区别。** CW只合并RSI入口，仍执行完整堆查询，历史867→867。EV不重跑同一方案：FINISH最后一次完整START重验本来就读取所有stream的request／ACK，从中派生“本次没有未处理OOM”的单次调度提示。可选`TASK_FINISH_HINT`以能力位协商，旧FINISH仍只允许kind0／1；新接口仅在live domain成员mask尚未全到、最后复查成功且此后没有回调时，允许INCOMPLETE的kind2。Client只跳过紧接的一次HEAP_EVENT，下一次FINISH仍完整新鲜检查；不将提示当作完成、CPU归还或退休证明，不改变deadline与查询预算。完整mask后的idle／flush、冷任务、已有未完成heap事务、错误、CPU归还及成功完成路径不提供提示。本轮确认heap入口没有独立末尾完整重验，未直接删除该入口检查。

**本地与实机效果。** 原545 phase后端的baseline／隔离候选输出逐字节相同，3607条PASS标记并非3607个独立用例。18场景×两个Client共36条新提示场景通过，涵盖初始／读后根与固件变化、新OOM、inactive stream故障、fallback、缺回调、错误服务身份和后续OOM可发现性；五个成功编译的错误变体均被指定断言拒绝。接入当前实际combined running-AS回调后，同一模型中的MMIO读取142→111、失效调用53→35、失效字节9380→5864；旧legacy适配器的175→133不能混用。这些是模型操作数，不是实机延迟或分数。另有32个场景经过实际新RSI分派、4个修改回调的场景仍直接调用核心，10个RSI身份／通道／参数负例通过。实际Client planner／worker117项、typed token／回复173项通过；完整私有套件633及原RSI套件681条PASS标记、固定补丁校验、ARM64 Client／RMM构建、固件布局／FIT检查退出0，23项RMM编译flags在仅归一化构建目录后相同。模型不证明Linux真实并发或实体隔离。

两轮均完成33场景、validation26成功／1既有异常／6无判据、VM退出0／0、所选预热／basic／CPU SIGNAL-eventfd冒烟、两端解绑、内核健康与资源恢复检查，各11份证据SHA核验；不能称全部图像正确性PASS。候选blur156、terrain27、大卷积effect2d690，均高于预设141／26／670；对照分别153／28／744，大卷积约−7.26%，不能只看总分。两轮CPU均schedutil、上下界1008000／1800000kHz，峰值温度均53615mC；实际频率分布有变化，未固定CPU恒频。完整720p退出1仅因总分低于1000；没有扩展API／ML／多Client。

候选主日志观测到每文件去重值`skipped_queries=534623`，不把重复日志相加。按各自退休批归一化：COMPLETE调用199.718→185.900µs（−6.92%），查询2.46307→2.54756次（+3.43%），完成间隔266.528→277.038µs（+3.94%），PREPARE137.546→136.172µs。调用工作减少没有等额变成端到端收益；调用加间隔约466.245→462.939µs，约−0.71%。这些累计墙钟值包含预热／校验、设备等待与调度，不是纯CPU成本、计分窗口逐任务轨迹或单变量因果证据。后续若重试，须同时给出查询次数／等待间隔的改善依据，不单独重复合并入口、缩短扫描或全局等待常数。

**执行与恢复。** 对照／候选均通过下列独占入口执行：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ev-control -- \
  python3 build/rmm-client-bo-20261030/completion-heap-hint-ev/run.py control
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ev -- \
  python3 build/rmm-client-bo-20261030/completion-heap-hint-ev/run.py measure
```

部署／恢复run-id分别为`private-finish-hint-fw-20261101-ev`和`private-finish-hint-fw-restore-20261101-ev`，均以`lab-run.py --allow-rk-reboot`包住`deploy-rmm-firmware.py --firmware <本轮firmware或原firmware-private-running-check> --run-id <对应ID>`，实际SD2回读匹配，Host内核未更换。Guest恢复run-id为`private-finish-hint-runtime-restore-20261101-ev`，调用本轮`restore-runtime.py`，只上传原ED Client。候选`runtime-candidate/`的rmm.elf／img仍是继承ED的未部署元数据；实测RMM以单独`firmware/`及实际SD2回读为准，不能单靠该Guest包恢复候选固件。

最终先核验172项冻结输入及16项控制脚本，再归档候选10项源码、精确恢复原10项并刷新mtime；145项原生产输入、两个8项冻结包、四项板端Guest及实际SD2均匹配。恢复后的Client113项及typed bridge模型退出0，Host空闲CPU0–1／pmthor，无VM／loop。开发期生成器匹配错误、fixture清理错误、ABI上界漏更新、输出目录冲突、构建路径比较以及只读监控字符串错误均保留于`development-failures.json`及相关日志，不计产品攻击拒绝。主证据为`{local-validation,build-validation,hardware-control,hardware-candidate,phase-comparison,decision,runtime-restoration,final-verification}.json`、`variants-retry1/`和`hint-rsi/`。

当前保留仍DA RMM＋ED Client＋原DX runner，最新原ED对照934，EU的936作为历史轮次保留；本轮938未保留为生产提分。恢复后未新增GPU测量，增量构建目录仍是EV Image，须使用冻结ED包或重建。AE EBUSY、额外Group submit超时、真实GPU完成eventfd及广泛API／ML／多Client、恶意并发和实体隔离验收仍未完成。

## EW：量化 RMM 租约元数据重复扫描，完整720p929分，诊断撤下并恢复ED（2026-11-01）

改动目的｜定位`live_eligible`与BO集合复核成本，决定是否值得建立稳定租约摘要｜最近纯DA＋ED对照934 → 临时计时版929｜−5分／−0.54%｜均为单Client／单vCPU、完整720p33场景、GPU请求600MHz／实际594MHz、CPU schedutil自动、相同Host／Proxy／Client／initrd／原DX runner；本轮只增加RMM计时与组销毁聚合输出，部署固件重启Host，计时、额外基数统计和串口输出会扰动结果，分差仅为诊断组合观测，不计提分｜`private-heap-720-20261101-ew`，退出1仅因1000门槛，详见下列命令和日志｜诊断已撤下，保留DA＋ED；新摘要优化尚未实现和实测。

### 测什么，为什么先不把轮询移到Proxy

EV减少单次FINISH中的工作仍未保留提分。本轮先检查另一种分工：Proxy所在CPU观察真实完成，Client保留可信最终确认。现有服务侧`gpu_firmware_task_drain()`并非廉价只读提示：成功时还执行idle快照、START重验、真实AS_FLUSH_MEM及drained证明。直接拿它作提示会与Client FINISH重复工作；把整个FINISH搬过去又涉及公共token退休及Client受管引用的交接。当前缺少更便宜、生命周期独立且覆盖OOM的观察接口，未实现、未上板，也不宣称这一方向已被性能否定。

新发现的可量化路径是：一次GPU完成查询会多次调用`gpu_private_task_live_eligible()`；其中`cache_set_check()`逐BO复核service、owner、closing、resident／uncached、hidden、mapped和cache_context。它是RMM私有元数据扫描，和MMIO／固件运行根检查是不同成本。本轮增加可选构建计时包装，不改变原谓词、回调顺序、GPU完成、缓存操作、页归还或任务退休语义；Guest接口与四项运行输入不变。

### 实测数据与证据范围

最终第69号报告的三个计数器行，在三份副本中逐字段完整一致。下表是累计调用区间，含预热／校验；扫描计时还包括临时位图基数统计，不能解释为纯CPU成本或可实现的加速幅度。

| 区间 | 调用次数 | 平均每次 | 累计区间 | 说明 |
| --- | ---: | ---: | ---: | --- |
| live_eligible整体 | 4,747,053 | 2.039µs | 9.679s | 4,747,051成功、2次拒绝；包含其中的BO扫描 |
| cache_set_check | 5,474,141 | 1.845µs | 10.102s | 平均位图引用42.458个BO；有live_eligible以外的调用者，不是实际访问对象数保证 |
| context_check_running整体 | 5,325,149 | 3.060µs | 16.296s | 私有前置检查＋实际运行AS／配置检查，保留全部物理检查 |

**以上区间相互嵌套，不能相加。** 不能由9.679s直接推算glmark能增加多少分。原Client累计指标为COMPLETE调用200.737µs／批、观察间隔265.020µs／批、PREPARE139.874µs／批；分母是该Client日志退休352302批，与RMM全局预热／校验范围不同，不混用分母。

原预设解析规则要求至少两份完整帧（含头、三行和尾）一致。串口丢字后，只认证14个完整报告，最新第39号／37222次可信FINISH成功；该前段live_eligible为12.570次／退休批、16.292µs／批，cache_set_check为14.632次／批、16.054µs／批，context_check_running为13.732次／批、42.006µs／批。此范围不代表完整33场景的逐任务profile。

**没有放宽原规则补齐最终帧。** 观察丢字后另加计数器三行的独立次级分析：各副本保留精确报告ID／copy／site，要求三个site齐全、逐字段两份以上一致、calls=ok+bad及全局单调；最终三份全部一致。次级分析不重建帧头／尾，也不提供最终退休分母。因此上表只给每次和累计值，不用仅存一份的最终帧头做每批归一化。原解析器11项检查、次级解析器13项检查通过，重复同一copy不能充当独立副本；完整帧覆盖不足仍记PARTIAL。下次采集应在帧头与帧尾也留串口发送间隔。

### 测试、失败和恢复

实际平台／私有核心／RSI模型退出0；私有完整套件退出0，639条PASS标记行不是639个独立用例。模型运行不等于实际shader、GPC或并发安全验收。23份编译flags对照仅多`GPU_METADATA_PROFILE`，保留O2 Debug及assert；固定补丁、RMM／U-Boot构建、ELF布局和FIT检查通过。运行包中的rmm.elf／rmm.img与本轮实际固件匹配，未沿用旧固件元数据。

首次RMM链接因freestanding缺`__popcountdi2`失败，改为显式整数SWAR；首次RSI模型提取遗漏诊断静态报告声明导致编译失败，补入实际报告函数后通过。失败构建日志与开发失败清单保留，未上板失败版本。

硬件33场景完成、VM退出0／0，validation仍26成功／1既有例外／6无判据；Host／Guest健康、pool-unbind、内存CPU／GPU频率恢复通过。11份证据SHA逐项核验。blur153→150、terrain28→27、大卷积effect2d744→747；不把局部变化当作收益。1000门槛未通过，API／ML／多Client扩展矩阵NOT_RUN。

固件恢复、板端核验均退出0；实际SD2范围与DA固件匹配，四项Guest输入与ED匹配。归档诊断源码后恢复4个原文件；145项生产输入、8项ED包以及恢复前162项冻结输入／16项控制脚本核验，Host CPU0–1／pmthor，无VM或loop。恢复后未新增GPU测量，当前纯基线仍引用934。

| run-id／动作 | 命令 | 退出码与证据 |
| --- | --- | --- |
| 私有离线套件 | `GPU_PRIVATE_TEST_OUT=build/rmm-client-bo-20261030/metadata-cost-ew/private-unit bash scripts/check/check-rmm-gpu-private.sh` | 0；`build/rmm-client-bo-20261030/metadata-cost-ew/private-suite.log` |
| 部署 `private-metadata-fw-20261101-ew` | `python3 scripts/maintenance/lab-run.py --run-id private-metadata-fw-20261101-ew --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/metadata-cost-ew/firmware --run-id private-metadata-fw-20261101-ew` | 0；`build/firmware-runs/private-metadata-fw-20261101-ew/` |
| 完整720p `private-heap-720-20261101-ew` | `python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ew -- python3 build/rmm-client-bo-20261030/metadata-cost-ew/run.py measure` | 1，仅低于1000；`build/lab-runs/private-heap-720-20261101-ew/`、实验目录`measure.log` |
| 恢复 `private-metadata-fw-restore-20261101-ew` | `python3 scripts/maintenance/lab-run.py --run-id private-metadata-fw-restore-20261101-ew --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check --run-id private-metadata-fw-restore-20261101-ew` | 0；同名`build/firmware-runs/`及实验目录`restore-firmware.log` |
| 恢复核验 `private-metadata-restore-verify-20261101-ew` | `python3 scripts/maintenance/lab-run.py --run-id private-metadata-restore-verify-20261101-ew -- python3 build/rmm-client-bo-20261030/metadata-cost-ew/verify-sd.py baseline post` | 0；同名`build/lab-runs/`及实验目录`restore-verify.log` |

### 下一候选的边界

优先研究**GPU保持租约期间的BO状态摘要**：在真实完整扫描／租约取得后，用RMM独占维护的状态及代次避免反复逐BO扫描；实际GPU根、AS、固件、错误和真实完成检查继续保留。这不是已经实现的优化，也不能只加一个“已检查”标志。必须先审计BO closing／mapped／hidden／cache_context、控制引用、映射epoch、heap扩容、租约归还／reset／reclaim／槽位复用的所有合法变更点，证明旧摘要不会越过失效边界；别名与其他context租约改变也必须覆盖。需要实际核心的恶意交错／失效负例和变体检测，再做完整720p对照。若这些不变量不能成立就放弃缓存，不能删掉原拒绝用例来保留候选。新的保留线至少max(946, ceil(紧邻对照×1.01))及既有场景保护线；1000仍是扩大回归的门槛。

权威证据：`build/rmm-client-bo-20261030/metadata-cost-ew/{plan,predeployment,offline-exits,hardware-candidate,profile-primary,profile-summary,development-failures,final-verification}.json`。无保留的新运行优化；整体实现与安全验收继续INCOMPLETE。

## EX：集中 BO 热字段，完整720p932分，撤回恢复DA／ED（2026-11-01）

统一记录：减少RMM对BO租约元数据复核时触及的缓存行｜紧邻原ED935 → EX932｜−3分／−0.32%｜完整1280×720、33场景、null-noop／finish、单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz，CPU原schedutil自动；仅RMM内部BO字段顺序变化，Client／Proxy／initrd／原DX runner和Host相同，部署固件需要Host重启，单对照只记录组合观测｜对照`private-heap-720-20261101-ex-control`与候选`private-heap-720-20261101-ex`退出1，仅因低于1000；部署／恢复及核验退出0，命令和日志见下｜未达到预先冻结的946分保留线，撤回；1000门槛与整体目标未完成。

**候选及查重。** EW定位到BO集合复核平均1.845µs／次，但该计时含诊断与基数统计，不能直接推算可省时间。EX先尝试不引入缓存摘要或失效协议的布局优化：把owner／service／handle、cache_context、页数／映射数／隐藏数及控制／resident／uncached等热字段放到512字节backing块索引之前。所有谓词仍读取真实当前字段，函数体、回调、实际根／设备状态、完成条件和生命周期不变。与BS的映射集合缓存以及EW建议的跨调用稳定租约摘要不同。

`private_bo`仍600字节，1024个BO占614400字节；RMM实际ELF的objects起址和总text／data／BSS大小与对照一致。基于实际数组起址和64字节缓存行，全部检查字段的静态覆盖从平均3.125行降至1.75行；这不是硬件cache miss计数，也不是延迟或性能收益。数据／控制分支读取的字段不同，不能声称每次实际都省1.375行。O2 Debug、assert、23项编译flags、保留区和容量保持，FIT嵌入与ELF/BSS布局检查通过。

**本地验证。** 精确结构体替换证明只有字段顺序改变；原版和候选实际核心56组cache_set路径、31组live_lease路径输出逐字节相同，ASan／UBSan无错误；原有六个cache-set错误变体均拒绝。实际combined后端／RSI回归、宿主与freestanding AArch64 offsetof／sizeof断言通过。完整639条私有套件为EW历史引用，本轮未重跑，也不据模型宣称实体隔离或真实并发通过。`lease-mutation-audit.json`登记BO身份、关闭／转换、控制引用、映射、租约取得／归还、撤销及owner回收等变更点；它只是后续摘要设计的审计清单，不是摘要正确性证明。

**实机结果。** 两轮33场景、VM退出0／0、预热计算和basic／CPU SIGNAL-eventfd冒烟、两端pool-unbind及kernel-log检查完成，Host／Guest健康和资源恢复通过，各11份证据SHA一致。validation仍26成功／1既有异常／6无判据，不能称全部图像正确性PASS；CPU SIGNAL-eventfd不等于真实GPU完成eventfd验收。三个场景保护线通过：blur152→153、terrain28→28、大卷积effect2d744→744；总分935→932未过946，不能按局部指标保留。

按各自累计退休批归一化：PREPARE137.968→137.319µs（−0.47%），COMPLETE调用198.322→199.490µs（+0.59%），COMPLETE间隔265.273→266.907µs（+0.62%），查询2.452952→2.467917次（+0.61%）。这些墙钟含预热／校验、设备等待及Guest／Host调度，不能相加为纯CPU成本或证明稳定退化。候选没有新的BO扫描专用实机计时，因此既不能断言扫描本身没有变快，也不能把字段集中直接算成端到端收益。

执行命令与证据：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ex-control -- \
  python3 build/rmm-client-bo-20261030/bo-layout-ex/run.py control
python3 scripts/maintenance/lab-run.py --run-id private-bo-layout-fw-20261101-ex --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/bo-layout-ex/firmware \
  --run-id private-bo-layout-fw-20261101-ex
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ex -- \
  python3 build/rmm-client-bo-20261030/bo-layout-ex/run.py measure
python3 build/rmm-client-bo-20261030/bo-layout-ex/analyze.py candidate
python3 build/rmm-client-bo-20261030/bo-layout-ex/compare.py
python3 scripts/maintenance/lab-run.py --run-id private-bo-layout-fw-restore-20261101-ex --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check \
  --run-id private-bo-layout-fw-restore-20261101-ex
python3 scripts/maintenance/lab-run.py --run-id private-bo-layout-verify-restore-20261101-ex -- \
  python3 build/rmm-client-bo-20261030/bo-layout-ex/verify-sd.py baseline post
python3 build/rmm-client-bo-20261030/bo-layout-ex/finalize-withdrawn.py
```

本地构建与定向验证命令／退出见`{build,local}-commands.json`及相应日志；计分命令／退出见`{control,measure}-{command,exit}.json`、`{control,measure}.log`和对应`build/lab-runs/<run-id>/`；部署／恢复证据见同名`build/firmware-runs/`及实验目录日志。分析及finalizer退出0，全部冻结输入和控制脚本在恢复前核验。归档候选core后只恢复一个源码并刷新mtime；145项原生产输入、162项冻结输入、8项控制脚本、两个各8项运行包、四项板端Guest及实际SD2 DA固件核验一致。Host空闲CPU0–1／pmthor，无VM或loop。

当前仍DA RMM＋ED Client＋原DX runner，最新纯对照935；932未保留，历史934等不删除。恢复后未新增GPU测量，EX构建树仍保留候选固件供证据复核；后续必须使用冻结DA／ED或从已恢复源码重新构建。1000未过，不扩展API／ML／多Client，历史AE EBUSY／Group submit超时、真实GPU完成eventfd和恶意并发／实体隔离验收继续未完成。后续优先研究有完整变更／别名／失败失效边界的稳定租约元数据摘要；不能因本轮布局失败而省略BO检查、缓存真实硬件根或提前发布完成。摘要尚未实现或测量。

## EY：稳定租约BO元数据摘要，完整720p944分，撤回恢复DA／ED（2026-11-01）

统一记录：减少GPU保持租约期间重复BO元数据扫描｜紧邻原ED931 → EY944｜+13分／+1.40%｜完整1280×720、33场景、null-noop／finish、单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz，CPU原schedutil自动；仅RMM核心元数据检查实现变化，Client／Proxy／initrd／原DX runner和Host相同，部署固件需要Host重启，单对照不证明稳定收益｜对照`private-heap-720-20261101-ey-control`、候选`private-heap-720-20261101-ey`退出1，仅因低于1000；部署／恢复及核验退出0，命令和日志见下｜未达到预先冻结的`max(946, ceil(紧邻对照×1.01))`＝946分保留线，撤回；1000门槛与整体目标未完成。

### 候选机制和验证边界

EW量化重复BO扫描，EX只改变字段布局。本轮实际实现另一条路径：成功完整执行`gpu_private_task_live_eligible()`中的BO集合检查后，缓存检查结果及受保护的`cache_metadata_epoch`；代次相同才跳过后续相同BO谓词扫描。context身份／service／task token、mapping epoch、活动／关闭／撤销等生命周期条件和AS槽位归属每次读取新鲜状态；实际硬件根、AS、固件配置、故障、真实完成及CPU归还检查不缓存。原`cache_set_check()`函数体及取得／归还租约的扫描保持原样。

对影响BO谓词的36处实际写边界进行审计：35处写操作前立即失效，另一个`cache_lease_acquire()`只在租约值实际改变时失效。不仅在函数入口处理，还覆盖实际MAP `.clean`回调后继续更新引用的情形；别名、控制引用、映射／关闭、heap扩容、销毁／回收／撤销和槽位复用均不能沿用旧摘要。全局代次溢出到0后永久禁用复用，回退完整检查，防止回绕碰撞。新增四组集合状态32字节和全局代次8字节，BO／任务／页表容量不变。这依赖RMM私有元数据受保护，不声称容忍任意RMM私有内存损坏。

逆向去掉明确新增代码后，core与原版逐字节相同；145项原生产输入中仅core和套件入口两项变化，另加摘要测试及checker两份文件。原cache-set 56组场景／6个编译错误变体拒绝；新增19组真实核心摘要场景／7个编译错误变体拒绝，包含回调暖摘要后引用变化、跨context、失败、撤销、复用和溢出边界。实际平台／核心／RSI组合验证退出0。私有完整套件退出0、634条`=PASS`标记不是634个独立用例；完整套件运行时包含前18组新场景，随后最终19组／7变体单独验证。模型不证明真实Linux并发、GPC或实体隔离。

固定补丁清单9项APPLIED、RMM／U-Boot构建、ELF/BSS布局和FIT嵌入检查通过；23份编译flags与对照一致，保留O2 Debug及assert。开发中保留两次测试工具失败：victim淘汰用例假设初始槽位错误，改为两轮完整轮转；变体生成器匹配缩进错误，修正精确匹配。它们不是GPU运行失败，失败日志没有删除。

### 完整720p及分段结果

两轮均完整33场景、VM退出0／0，预热计算、basic／CPU SIGNAL-eventfd冒烟通过；两端pool-unbind及kernel-log检查退出0，Host／Guest健康和资源恢复通过，各11份证据SHA核验一致。validation仍26成功／1既有异常／6无判据，不能称全部图像正确性PASS；CPU SIGNAL-eventfd不等于真实GPU完成eventfd验收。场景保护通过：blur152→156、terrain28→30、大卷积effect2d744→756（原始kernel为5列×3行）。总分944未达946，不事后降低规则或将单轮上升作为稳定收益。

| 累计统计，按各自退休批归一 | 原ED931 | EY944 | 变化 |
| --- | ---: | ---: | ---: |
| PREPARE调用墙钟µs／批 | 137.419 | 130.256 | −5.21% |
| COMPLETE调用墙钟µs／批 | 199.385 | 190.280 | −4.57% |
| COMPLETE调用间隔µs／批 | 266.405 | 269.367 | +1.11% |
| 查询次数／批 | 2.461109 | 2.488543 | +1.11% |

这些是累计file统计，含预热／校验、设备等待及Guest／Host调度，不是纯CPU耗时、精确GPU执行时间或逐场景全覆盖profile，不能将百分比相加推导端到端收益。全程温度快照约45–54°C，CPU均为schedutil并观察到多个瞬时频点；并未建立同相位连续驻留或热因果证据。`compare.py`的scope沿用EX“仅BO布局变化”旧文案，**不适用于EY**；其数值来自本轮日志，准确实验范围见`analysis-notes.json`和本节。

### 执行、撤回和证据

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ey-control -- \
  python3 build/rmm-client-bo-20261030/lease-summary-ey/run.py control
python3 scripts/maintenance/lab-run.py --run-id private-live-summary-fw-20261101-ey --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/lease-summary-ey/firmware \
  --run-id private-live-summary-fw-20261101-ey
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ey -- \
  python3 build/rmm-client-bo-20261030/lease-summary-ey/run.py measure
python3 build/rmm-client-bo-20261030/lease-summary-ey/analyze.py candidate
python3 build/rmm-client-bo-20261030/lease-summary-ey/compare.py
python3 scripts/maintenance/lab-run.py --run-id private-live-summary-fw-restore-20261101-ey --allow-rk-reboot -- \
  python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check \
  --run-id private-live-summary-fw-restore-20261101-ey
python3 scripts/maintenance/lab-run.py --run-id private-live-summary-verify-restore-20261101-ey -- \
  python3 build/rmm-client-bo-20261030/lease-summary-ey/verify-sd.py baseline post
python3 build/rmm-client-bo-20261030/lease-summary-ey/finalize-withdrawn.py
```

本地命令／退出／日志见实验目录`{local,build}-commands.json`、`local-validation.json`、`warm-summary-final2/result.json`、`private-suite.log`及`development-failures.json`；完整计分见`{control,measure}-{command,exit}.json`和相应日志，各run-id证据在`build/lab-runs/`，固件部署／恢复证据在`build/firmware-runs/`。分析及finalizer退出0；`decision.json`和`final-verification.json`为最终结论。

撤回前164项实验冻结输入和11项控制脚本哈希一致。归档候选四份源码／checker后，恢复两个原文件、移除两份仅服务撤回候选的新文件；145项生产输入逐项一致。两个各8项运行包、四项板端Guest及实际SD2 DA固件读回一致，Host CPU0–1／pmthor，无VM或loop。当前仍DA RMM＋ED Client＋原DX runner，最新纯对照931；944仅为撤回候选，历史935／934等各轮结果保留。回退后未新增GPU测量，后续使用冻结DA／ED包；不能从仍保留EY构建树的候选固件继续测试而冒称当前基线。

1000未过，API／ML／多Client扩展矩阵NOT_RUN；历史AE EBUSY／Group submit超时、真实GPU完成eventfd及恶意并发／实体隔离验收继续未完成。下一步应围绕设备推进／STATUS交互与Client观察时机的协作提出新证据和不同机制，不能只因调用墙钟下降就反复换缓存字段、等待常数或降低保留线；所有映射归属、根／故障和真实完成语义继续保留。整体目标仍INCOMPLETE。

## EZ：STATUS ACK循环计数诊断936分，串口统计失败，已恢复DA／ED（2026-11-01）

统一记录：量化真实STATUS握手的循环次数、stream扫描数和延迟分布｜此前EY纯对照931 → EZ诊断936｜+5分／+0.54%｜完整1280×720、33场景、null-noop／finish，单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz、CPU自动策略；Client／Proxy／initrd／DX runner／Host不变，仅临时RMM统计及报告，部署重启Host，未重跑新纯对照，因此不作优化因果归因｜`private-heap-720-20261101-ez`退出1，仅未达1000；部署／恢复及核验退出0｜诊断一律撤回，当前仍DA＋ED＋原DX，纯对照仍引用931。

计数位于真实`task_observe()`的STATUS轮询内，分别记录成功／失败握手、循环与stream检查总数及直方图；独立`profile_clock`不替换原超时时钟，原检查、超时、完成和回收顺序不变。计时开始于notify之后、轮询之前，因此也不是完整GPU响应延迟或GPU执行时间。三份带编号完整行在GROUP_DESTROY后输出，仅用于诊断。

实际原后端与禁用／启用模型的非报告输出一致；实际core＋RSI报告路径、六个成功编译的计数错误变体拒绝、600个累加器边界和21个严格解析用例通过，模型原报告两组通过相同副本规则。完整私有套件退出0、633条`=PASS`标记不等于独立用例；平台／核心／RSI running checker通过。23份编译flags仅加入`GPU_ACK_PROFILE`，保留O2 Debug／assert；固定补丁9项APPLIED、RMM／U-Boot、布局及FIT构建通过。开发期编译缩进／负例夹具错误保留于`development-failures.json`，未部署失败版本。

实机33场景完整，validation26成功／1既有例外／6无判据、VM退出0／0、预热计算及basic／CPU SIGNAL-eventfd、pool-unbind和kernel-log检查完成；Host／Guest健康、内存／频率与资源恢复通过，11份日志逐项SHA核验。blur153、terrain28、大卷积effect2d744均过预设场景线；总分936仍未过1000，API／ML／多Client未执行。

**报告采集FAIL。** 最终UART含147条包含`EZ_ACK`的物理行，但多行截断、合并或丢失数字，严格解析器以`Insufficient independent complete row quorums`退出1。不得从碎片补值、重组缺失数字、放宽副本门槛或发布硬件计时分布。完整33场景与健康检查通过不抵消诊断目标未达。现有Client累计PREPARE137.419→137.319µs／退休批、COMPLETE调用199.385→199.418µs，都是含预热／校验、调度和设备等待的墙钟，也不能据此推断STATUS循环成本。

执行入口与退出码：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-status-ack-fw-20261101-ez --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/status-ack-ez/firmware --run-id private-status-ack-fw-20261101-ez
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-ez -- python3 build/rmm-client-bo-20261030/status-ack-ez/run.py measure
python3 build/rmm-client-bo-20261030/status-ack-ez/analyze-hardware.py candidate
python3 build/rmm-client-bo-20261030/status-ack-ez/compare.py
python3 build/rmm-client-bo-20261030/status-ack-ez/analyze-profile.py build/lab-runs/private-heap-720-20261101-ez/gpu-uart.log build/rmm-client-bo-20261030/status-ack-ez/profile-hardware.json
python3 scripts/maintenance/lab-run.py --run-id private-status-ack-fw-restore-20261101-ez --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check --run-id private-status-ack-fw-restore-20261101-ez
python3 scripts/maintenance/lab-run.py --run-id private-status-ack-verify-restore-20261101-ez -- python3 build/rmm-client-bo-20261030/status-ack-ez/verify-sd.py baseline post
python3 build/rmm-client-bo-20261030/status-ack-ez/finalize.py
```

上述部署0、测量1、硬件分析0、对比0、profile解析1、恢复0、核验0、finalize0；确切命令／退出在实验目录`*-command.json`／`*-exit.json`及相应日志，恢复核验在`verify-restore.log`。本地命令见`local-commands.json`／`build-commands.json`；实机全证据见对应`build/lab-runs/`，部署与恢复见`build/firmware-runs/`。

恢复后实际SD2读回与DA固件匹配，四项Guest与ED匹配；归档三项诊断源码并恢复原文，145项生产输入、163项冻结输入、17项控制脚本和两个各8项运行包核验一致。Host空闲CPU0–1／pmthor，无VM或loop。当前纯基线931来自EY对照，恢复后未新增GPU测量。下一步FA仅改变UART报告为三段短行，每段有完整序号／copy／row／part，先保证同一copy三段齐全再执行原完整行数值与至少两份独立copy一致规则；不混拼不同副本，不修数字。该重采尚未形成硬件结果或新优化。1000及整体目标继续未完成，历史失败项不删除。

## FA：短行STATUS诊断935分，取得有效统计前缀，恢复DA／ED（2026-11-01）

统一记录：修复EZ长行UART报告无法可靠采集的问题｜此前EY纯对照931 → FA诊断935｜+4分／+0.43%｜完整1280×720、33场景、null-noop／finish，单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz，CPU原自动策略；与EZ相同计数／原检查／超时顺序，只有报告拆为三段，Client／Proxy／initrd／DX runner／Host不变；部署重启Host，未新增纯对照，不计作优化收益｜`private-heap-720-20261101-fa`退出1，仅低于1000；部署／恢复与核验退出0，见下｜诊断一律撤回，当前仍DA＋ED＋原DX，纯对照931继续保留；1000门槛和整体目标未完成。

### 统计取得了什么

每份copy／row拆为带相同seq的三个part，只有该copy三段完整才能进入原EZ数值／守恒／单调检查，之后每row仍需至少两份不同编号copy的全部指标相同。不得用另一copy的part补齐当前copy，也不修数字。完整日志仍至少两组报告，逐组历史复核不改变每row的两份copy门槛。

本轮38组通过，其中最后有效组67的成功行由seq202／203一致认证，计数终点为343527次成功FINISH调用；该前缀内830805次成功STATUS握手、失败握手0次，平均6.368次轮询、50.947次stream检查，轮询区间平均20.431µs、最大99.167µs，累计16.974秒。86.633%的握手为3–8次轮询，未见1／2次轮询。这包括预热、校验和内部调用，而且计时起点在notify之后，并非设备端实际完成时间或纯CPU成本。

**有效前缀不是全程终点。** 最后一组68没有足够完整副本，90条part损坏、91个copy／row不完整；全部原样保留并拒绝。不能称“全程零失败握手”，不能用这个前缀除以Client全程354449次退休批计算每批耗时或阶段占比，也不能把16.974秒当作可直接删除的开销。当前证据见`profile-hardware.json`、`accepted-report-history.json`、`assessment.json`和原`gpu-uart.log`；没有补齐未认证后缀。

Client全程独立对账：PREPARE137.419→136.949µs／退休批、COMPLETE调用199.385→199.404µs、观察间隔266.405→265.306µs、查询2.461109→2.459093次；这些累计墙钟包含调度／设备等待和预热／校验，不是纯CPU归因。完整33场景、validation26成功／1既有例外／6无判据、VM0／0、预热计算及basic／CPU SIGNAL-eventfd完成；Host／Guest健康、pool-unbind、频率／CPU／资源恢复及11份证据SHA核验通过。blur152、terrain27、大卷积effect2d745均过场景保护线。1000未过，API／ML／多Client扩展NOT_RUN。

### 本地验证和失败保留

核心／头与EZ逐字节相同，逆向去掉诊断变换后原三份源码逐字节可恢复。重用EZ六个成功编译的错误变体拒绝、600个累加器边界及633条完整私有套件标记作为不变核心的历史验证，本轮没有声称重跑该完整套件。新三段解析13用例通过；实际RSI提取／原后端夹具在ASan／UBSan下编译与执行退出0，两组短行报告的计数与EZ一致，非报告输出一致。该模型最长46字节只代表模型值，不能保证硬件大计数行长度或无丢字节，实际后缀缺失明确保留。

23份RMM编译flags与EZ相同，对原DA仅有诊断define差异，O2 Debug／assert保持；固定补丁9项APPLIED、RMM／U-Boot构建、布局和FIT嵌入通过。开发失败包括首次检查器用重叠前缀替换误改夹具路径导致编译失败，以及统计历史工具的Python tuple／JSON array比较、首组枚举门槛错误；分别保留原脚本／日志并修正分析工具，未改硬件数值或原解析器规则，详见`development-failures.json`。

硬件入口：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-status-ack-fw-20261101-fa --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/status-ack-compact-fa/firmware --run-id private-status-ack-fw-20261101-fa
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-fa -- python3 build/rmm-client-bo-20261030/status-ack-compact-fa/run.py measure
python3 build/rmm-client-bo-20261030/status-ack-compact-fa/analyze-hardware.py candidate
python3 build/rmm-client-bo-20261030/status-ack-compact-fa/compare.py
python3 build/rmm-client-bo-20261030/status-ack-compact-fa/analyze-profile.py build/lab-runs/private-heap-720-20261101-fa/gpu-uart.log build/rmm-client-bo-20261030/status-ack-compact-fa/profile-hardware.json
python3 build/rmm-client-bo-20261030/status-ack-compact-fa/assess.py
python3 scripts/maintenance/lab-run.py --run-id private-status-ack-fw-restore-20261101-fa --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check --run-id private-status-ack-fw-restore-20261101-fa
python3 scripts/maintenance/lab-run.py --run-id private-status-ack-verify-restore-20261101-fa -- python3 build/rmm-client-bo-20261030/status-ack-compact-fa/verify-sd.py baseline post
python3 build/rmm-client-bo-20261030/status-ack-compact-fa/finalize.py
```

最终依次退出0／1／0／0／0／0／0／0／0。本地与硬件命令索引在`status-ack-compact-fa/commands-index.json`，构建在`build-commands.json`；复用驻留认证executor，执行记录与日志位于`status-ack-ez/fa-*-command.json`、`fa-*-exit.json`、`fa-*.log`，没有保存凭据。完整运行证据在`build/lab-runs/<run-id>/`，部署／恢复在`build/firmware-runs/<run-id>/`。分析工具最终退出0，开发中非零日志保留。

恢复核验后，实际SD2两段固件与DA匹配，四项Guest仍与ED匹配；归档诊断源码后恢复原三份，145项原生产输入、163项诊断冻结输入、17项冻结执行脚本和两个各8项运行包核验一致。Host空闲CPU0–1／pmthor，无VM或loop。恢复后未新增GPU测量，935与EZ936均是已撤下的诊断分数，不能覆盖当前纯对照931。

### 下一步取舍

现有证据支持继续研究**任务准入与完成观察之间的整体流水线，以及有明确可信事务边界的重复工作消除**。不能从约20µs握手推导跨VM分阶段一定更快：CY延后stream扫描已经881→877撤回，EC将STATUS拆跨RSI已经891→819撤回，EO事件唤醒934→878撤回；这些失败不能因本轮取得计数而抹去。普通worker交接只占较小时间，VM_BIND在此前EH的累计RPC占比也仅0.284%，暂不把页表hash或worker交接当作主要端到端瓶颈。新候选须给出区别于旧实验的具体机制、失效／依赖／错误语义及可测收益，再冻结输入做完整720p对照；不能仅调整常数、删除真实检查或在结果出来后降低保留线。当前没有新增保留优化，历史AE EBUSY／Group submit超时、真实GPU完成eventfd、多Client／实体隔离验收继续未完成。


## FB：Cortex-A55 编译调优，929→937，撤回恢复DA／ED（2026-11-01）

统一记录：降低RMM提交／完成检查的CPU执行成本｜紧邻原ED929 → 候选937｜+8分／+0.86%｜完整1280×720、33场景、null-noop／finish、单Client且每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz，CPU原schedutil自动；Client／Proxy／initrd／DX runner／Host相同，仅RMM编译调度选项变化，候选部署需要Host重启｜下述run-id、命令、退出码和日志｜未达预先`max(946, ceil(紧邻对照×1.01))`＝946保留线，撤回；1000门槛与整体目标未完成。

本轮先审查同队列依赖闭包一次发布，未实现：当前`panthor_client_private_job_ready()`会在依赖错误时阻止后继，而原生wrapper中的ERROR_BARRIER允许在任务边界恢复，单凭同队列执行顺序不能保证等价。与BX逐成员PROGRESS／PUBLISH不同的设想，仍须先证明错误传播、timeline旧前驱和完整归还语义，不能提前发布来换取分数。审查证据`cpu-tune-fb/same-queue-review.json`，没有新运行代码或相关性能测量。

实际候选为RMM增加`-mtune=cortex-a55`。板端CPU part 0xd05已核实；23份flags与DA构建逐份归一化核对，唯一差异是该选项，原O2、Debug、断言、ISA及`-mgeneral-regs-only`保持。没有生产源码／ABI／超时／权限检查变化，但生成的RMM机器码确实改变，不能将本轮写成纯文档整理。ELF text统计283328→275136字节，data／BSS相同；静态代码尺寸或屏障条数不是执行成本或安全证明。源码与固定U-Boot来源、构建命令、FIT／BSS布局检查均保存于`cpu-tune-fb/`。

| 指标 | 原ED对照 | FB候选 | 判定 |
| --- | ---: | ---: | --- |
| 完整720p分数 | 929 | 937 | +0.86%，不足946保留线／1000扩展线 |
| desktop blur FPS | 152 | 153 | 高于预设141 |
| terrain FPS | 28 | 28 | 高于预设26 |
| 大卷积effect2d FPS | 744 | 744 | 高于预设670 |
| validation：成功／既有例外／无判据 | 26／1／6 | 26／1／6 | 不称全部图像正确性通过 |
| VM退出码 | 0／0 | 0／0 | 两端解绑／内核健康／资源恢复通过 |
| 回收证据SHA核验 | 11份 | 11份 | 各文件逐项一致 |

两轮CPU未锁恒频，整会话1Hz采样分别561／560条，1.8GHz采样427／426条，峰值温度均53615mC；这些不是计分窗口的连续频率驻留证明。按各轮退休批归一化，PREPARE调用墙钟约−0.81%、COMPLETE调用约−0.98%、COMPLETE间隔约−0.17%；包含预热／validation、设备交互与调度，不作纯CPU归因。单对照加固件重启不足以证明稳定提速，未因937高于929便降低保留线。

执行与证据（根目录`build/rmm-client-bo-20261030/cpu-tune-fb/`）：

- `python3 .../cpu-tune-fb/build.py`退出0：RMM、固定来源U-Boot、FIT及布局通过；`build-commands.json`、`build-verification.json`保存实际参数与23份flags核对。
- `HOST_CC=$PWD/build/rmm-client-bo-20261030/cc-debug-o2 GPU_PRIVATE_TEST_OUT=$PWD/build/rmm-client-bo-20261030/cpu-tune-fb/unit bash scripts/check/check-rmm-gpu-private.sh`退出0，633条精确PASS标记；补丁清单9项APPLIED，退出0。Host doubles／ASan／UBSan检查不运行A55生成代码，不证明实体GPT/GPC；实体负载另见下面两轮。
- 对照`private-heap-720-20261101-fb-control`、候选`private-heap-720-20261101-fb`，均经`lab-run.py --run-id <ID> -- python3 .../cpu-tune-fb/run.py control|measure`；外层均退出1，仅因低于1000。完整命令见`commands-index.json`及各`build/lab-runs/<ID>/benchmark-command.json`；原始GPU、Guest、频率、健康和11份SHA核验日志保留。
- SD2部署`private-cpu-tune-fw-20261101-fb`、恢复`private-cpu-tune-fw-restore-20261101-fb`，使用`lab-run.py --allow-rk-reboot -- ... deploy-rmm-firmware.py`，均退出0，只写storage ID 2，Host内核／rootfs未改。
- 独占恢复核验`private-cpu-tune-verify-20261101-fb`退出0；`python3 .../cpu-tune-fb/finalize.py`退出0：145项生产输入、162项冻结输入、14项执行脚本内容未变，四项板端Guest与实际SD2匹配，Host为CPU0–1／pmthor，无VM或loop遗留。恢复后没有新增GPU测量，当前纯对照929来自本轮对照，不将937保留为当前性能。

后处理的初次阶段比较早于候选窗口生成，FileNotFoundError保留于`phase-comparison.log`；随后顺序完成候选分析和比较，均退出0。向忙碌executor预送的分析／核验请求被继承stdin的子进程消费，没有实际执行；在对应子进程结束后显式重发，最终回执与日志核对，不把未执行请求算PASS。只读监视时板端缺少rg，进程列表未取得、日志tail成功，也保留于`development-notes.json`。这些工具问题没有改动执行路径或放宽GPU判据。

最终决策与逐项命令见`{decision,final-verification,commands-index,conditions,phase-comparison}.json`。运行仍为DA RMM＋ED Client＋原DX runner；广泛API／ML／多Client及实体隔离攻击NOT_RUN，AE EBUSY、Group submit超时、真实GPU完成eventfd继续未完成。本轮筛除了CPU编译调度作为主要提分方向；后续重点仍是有明确可信边界的任务准入／完成协作及重复工作消除。


## FC：通用 memcpy 宽字复制，完整720p 935→934，撤回恢复DA／ED（2026-11-01）

改动目的｜降低RMM任务、控制数据和输入复制的逐字节开销｜紧邻原版935 → FC934｜−1／−0.11%｜只改RMM通用libc memcpy；Guest／Proxy／Host／initrd／原DX runner／ABI／权限与完成检查不变，同完整720p33场景、GPU实际594MHz、CPU未锁恒频；候选固件部署包含Host重启，不能证明稳定因果收益｜下面命令、run-id、退出码及日志｜未达到预先946保留线，已撤回；1000扩展门槛仍未通过。

**查重与实现。** BD只优化已认证固件接口的读取，明确保留通用libc及共享写入路径；本轮首次改通用`lib/libc/src/memcpy.c`。原实际ARM64函数使用ldrb／strb逐字节循环；候选仅在源、目标对齐相容时，先复制字节前缀，再用自然对齐64位标量循环，最后复制字节尾部；不同对齐保持字节路径。GNU may_alias保留任意对象内容的别名访问语义，不读取或写入请求范围外字节，不扩展memcpy到重叠范围，也不用于MMIO。所有真实根、映射归属、缓存维护、STATUS／错误／fence、生命周期与回收检查保持。不是跨调用证明缓存，也不是删检查提速。

实际反汇编确认标量ldr／str、无SIMD或递归调用；函数36→188字节，完整ELF text／data／BSS统计不变，不把静态尺寸或访问宽度解释为性能收益。RMM23份flags与DA逐项一致，保留O2／Debug／断言／ISA／严格对齐；固定U-Boot、BL31、DDR来源、FIT嵌入和BSS布局通过。构建及候选源归档位于`build/rmm-client-bo-20261030/memcpy-fc/`，候选RMM ELF SHA `1fcc71dcd8579e476732a9de14f374fd32ec2e5531eb9e25137001e6c81e49a8`。

**本地验证。** 原版／候选各1057282组精确复制对照，包括256种源目标对齐组合、0–4097字节范围、前后保护字节及两端guard page；ASan／UBSan检查通过。完整私有套件命令以`HOST_CC=.../memcpy-fc/cc-with-copy GPU_PRIVATE_TEST_OUT=.../memcpy-fc/unit bash scripts/check/check-rmm-gpu-private.sh`运行，退出0、633条精确PASS标记；`HOST_CC=.../memcpy-fc/cc-with-copy bash scripts/check/check-dma-guard.sh`退出0、4288条PASS标记，并非4288个独立用例。编译wrapper把遵循HOST_CC的源文件直接memcpy调用链接到候选；宿主运行库内部和编译器内联复制未替换。wrapper对象未加sanitizer，独立边界测试对候选复制函数加了sanitizer。上述模型不证明实体GPU／GPC或真实并发。固定上游补丁清单9项APPLIED，退出0。开发分析器误匹配机器码、提前解析未结束套件的中间状态均更正并保留；部署使用的是进程退出0后的最终结果，见`development-notes.json`。

| 指标 | 原版对照 | FC候选 | 判定 |
| --- | ---: | ---: | --- |
| 完整720p | 935 | 934 | −1／−0.11%，未达946／1000 |
| desktop blur FPS | 153 | 153 | 高于141保护线 |
| terrain FPS | 28 | 28 | 高于26保护线 |
| 大卷积effect2d FPS | 744 | 749 | 高于670保护线，不能单场景归因 |
| validation成功／既有例外／无判据 | 26／1／6 | 26／1／6 | 不称全部图像正确性通过 |
| 两端VM退出码 | 0／0 | 0／0 | 内核健康与资源恢复通过 |
| 回收日志SHA | 11份 | 11份 | 两轮分别核验 |

按各轮累计退休批归一化：PREPARE137.836→135.600µs（−1.62%），COMPLETE操作199.218→196.906µs（−1.16%），但COMPLETE间隔265.921→269.160µs（+1.22%）、查询／批2.459→2.491（+1.30%）。这些墙钟含预热／验证、设备交互和调度，不能相加为纯CPU节省，也不足以归因复制函数的真实执行成本。两轮全会话各562条1Hz频率点，1.8GHz点426／428，峰温均53615mC；不是计分窗口连续驻留证明。局部下降没有形成端到端提分，不重复仅按宽字／展开常数继续试探。

执行与证据：

- 对照`private-heap-720-20261101-fc-control`、候选`private-heap-720-20261101-fc`：`python3 scripts/maintenance/lab-run.py --run-id <ID> -- python3 build/rmm-client-bo-20261030/memcpy-fc/run.py control|measure`，均退出1，唯一门槛错误为完整720p低于1000。内层冻结Realm runner采用`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`；每轮完整命令和11份SHA核验日志在`build/lab-runs/<ID>/`，模型／预热不能替代广泛API或实际GPU完成eventfd验收。
- 候选部署`private-memcpy-fw-20261101-fc`、原版恢复`private-memcpy-fw-restore-20261101-fc`：统一`lab-run.py --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware <固定固件目录> --run-id <ID>`，均退出0；备份实际启动区并只写SD2，未刷Host内核／rootfs或eMMC。
- 恢复核验`private-memcpy-verify-20261101-fc`：`lab-run.py --run-id <ID> -- python3 .../memcpy-fc/verify-final.py baseline`退出0，146项生产输入与43项冻结输入匹配，四项板端Guest及实际SD2原DA固件逐项SHA核验，Host恢复CPU0–1／pmthor，无VM或loop遗留。

最终决策、命令与分段比较在`{decision,final-verification,commands-index,conditions,phase-comparison}.json`。唯一生产改动已恢复，候选源码及失败证据只保存在build实验目录；构建缓存仍含候选，下一轮不可误当原版。当前仍DA RMM＋ED Client＋原DX runner，最新纯对照935来自本轮对照；**恢复后无新增GPU测量**。广泛API／ML／多Client与实体隔离攻击NOT_RUN，AE EBUSY、Group submit超时及真实GPU完成eventfd继续未完成，整体目标保持未完成。


## FD：主动等待的Guest就绪竞争诊断（2026-11-01）

**FE解释更正：** 本节的nr_running>1端点计数可能包含EEVDF延迟出队的睡眠实体，不能直接称为真实可运行任务竞争；原始计数保留，任务状态与身份的进一步核验见后续FE节。

改动目的｜判断完成观察的主动暂停是否挤占其他Guest就绪任务｜FC纯对照935 → FD诊断932｜-3／-0.32%｜仅Client增加只读端点统计；同单vCPU、完整720p33场景、GPU实际594MHz、CPU自动频率，RMM／Proxy／Host／initrd／原DX runner不变；无固件写入或Host重启｜下述run-id、命令、退出码及日志｜诊断始终撤下，无保留性能优化；1000门槛未通过。

**假设与方法。** FC原版完成间隔约265.921µs／退休批，其中主动暂停约238.990µs；这些等待可能与GPU执行重叠，不能直接当作可消除的CPU成本。本轮在每次暂停的起点、终点各调用一次`nr_running()`，按首次预测／后续重试及solo→solo、solo→busy、busy→solo、busy→busy建立2×4桶；每桶只累计次数、原有计时区间和最大值。在worker同步停止后统一打印8条短行。没有额外ktime读取、循环内采样、逐次日志，也没有修改等待预算、排队、绝对deadline、真实FINISH、heap服务、fence或回收判断。每文件额外统计192字节。

**本地验证。** Client正常重建与冻结ED的18415616字节可执行前缀逐字节相同后才修改；候选只改变包内client-Image。实际Client worker的ASan／UBSan模型121场景通过（原113＋首次／重试的8种端点组合），已有取消、超时、错误、真实完成与回收路径保持；模型不代表Linux并发或硬件隔离。Guest Image构建和OpenCCA补丁清单检查退出0。分析器2组有效／去重输入通过，8组缺行、冲突、截断、计数／时间错误负例拒绝。

**实机结果。** 完整720p 932分，33场景，validation26／1／6、VM0／0、内核健康／资源恢复及11份日志SHA核验通过；验证例外仍保留。外层退出1，门槛错误为低于1000。仅上传Client Image；首次与后续暂停的总次数、总时长、最大值同已有PRIVATE_COMPLETION统计精确一致，首次次数／时长同PRIVATE_POLL_PREDICT一致。

| 暂停类别 | 次数 | 任一端点其他就绪线程次数 | 次数比例 | 这些区间占本类累计暂停时长 |
| --- | ---: | ---: | ---: | ---: |
| 首次预测 | 353295 | 351270 | 99.4268% | 99.8778% |
| 后续重试 | 516301 | 511165 | 99.0052% | 99.0223% |

共869596次暂停、84.775283s累计墙钟、239.911µs／退休批；任一端点采到其他就绪线程共862435次（99.1765%），这些区间累计时长比例99.6114%。原始8桶与各项精确对账见`wait-contention-fd/runnable-summary.json`。

**证据边界与决策。** `nr_running()`是无锁瞬时近似统计；实际Client配置单vCPU，仅说明采样点存在其他Guest就绪任务，不能识别其为应用或内核线程。端点均solo不能排除区间内有竞争，端点busy不能证明整个区间都忙；区间时长含Host抢占，非纯CPU执行时间，也不能把加权比例当作可恢复分数。统计覆盖会话预热／验证，不等同计分窗口。当前证据支持继续定位Guest就绪竞争，下一步先识别就绪线程及其延迟，再评估有界协作等待；尚不能确定竞争者是应用，不直接重复短睡眠、全局常数或worker优先级微调。新增诊断分数不计为优化收益，当前纯对照仍935。

执行与证据：

- `private-heap-720-20261101-fd`：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-fd -- python3 build/rmm-client-bo-20261030/wait-contention-fd/run.py measure`，退出1；实际冻结runner参数`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。完整命令、资源、频率／UART与11份已核验日志在`build/lab-runs/private-heap-720-20261101-fd/`。
- `private-wait-contention-restore-20261101-fd`：同lab-run入口执行`python3 .../wait-contention-fd/run.py restore`，退出0；仅原子恢复精确ED Client Image，核验四项Guest及实际SD2仍DA。Host恢复CPU0–1／pmthor，无本次VM或loop遗留。
- 本地`python3 scripts/check/check-gpu-private-submit.py`退出0（121场景）；构建命令／退出码／日志见实验目录`client-build-*`，恢复后模型退出0（113场景）。`analyze.py`及`analyze-runnable.py`退出0；`final-verification.json`核验146项生产输入、182项冻结输入与5项额外调度器／runner依赖。

仅撤回本轮两个源码文件，候选／补丁／日志保存在build目录；构建缓存仍可能包含候选，不可误作ED。恢复后无新增GPU测量，**当前仍DA RMM＋ED Client＋原DX runner**。广泛API／ML／多Client、真实GPU完成eventfd与实体隔离攻击NOT_RUN；AE EBUSY、历史Group submit超时及既有validation例外未解决，整体目标保持未完成。


## FE：稀疏任务身份与EEVDF延迟出队核验（2026-11-01）

改动目的｜辨别FD的nr_running是否表示真实CPU竞争，以及竞争者是谁｜FC纯对照935 → FE诊断932｜-3／-0.32%｜仅Client新增稀疏只读任务快照；同完整720p33场景、单vCPU、GPU实际594MHz、CPU自动频率、DA RMM／Proxy／Host／initrd／原DX runner；没有固件写入或Host重启｜下面run-id、命令、退出码及日志｜诊断始终撤下，无保留性能优化；1000门槛未通过。

**先修正假设。** FD的869596次暂停中99.1765%在至少一个端点观测到nr_running>1，这是准确的计数，不等于99.1765%的暂停存在可运行应用竞争。当前内核`kernel/sched/features.h`默认启用DELAY_DEQUEUE；`fair.c`的dequeue_entity可将睡眠实体设为sched_delayed后返回false，直到稍后真正出队才sub_nr_running。`core.c`的nr_running只累计rq计数，而`include/linux/sched.h`的task_is_runnable明确排除sched_delayed。因此上一轮将“存在其他就绪线程”直接作为优化线索的解释过强，本轮改为验证任务身份与状态，不基于该总数直接加入yield或短睡眠。

**实现与边界。** 每4096次主动暂停后采一次（包含第0次），在原有after时间戳之后、重新获取private_gpu_lock之前执行有界RCU遍历，最多128个线程、32个身份槽位。忽略当前worker及on_rq不为1的实体，按sched_delayed／TASK_RUNNING区分延迟出队、可运行及队列过渡状态；每个身份使用PID＋start_time＋类别，不持有跨RCU的task指针。记录进程名、内核线程标志、首次／重试命中数及首次／末次累计执行／run-delay。8个类别组合mask记录每个快照，缺省空桶也打印。扫描上限、表满和空快照独立计数，不静默丢失。所有输出在同步cancel及destroy_workqueue之后统一打印；授权、映射、启动、FINISH、heap、fence、deadline和回收判断不变。诊断自身有遍历／短临界区开销，不能视为零扰动。

**本地验证。** 修改前正常重建与冻结ED的18415616字节可执行前缀逐字节一致。实际提交worker的113个ASan／UBSan模型场景通过，在每次退出检查采样调用数与原暂停计数相同；实际观察函数另有15个ASan／UBSan模型场景，覆盖3类的8种组合、排除非queued任务、4096步长、PID复用、同身份不同类别、完整表／128线程截断及既有身份查找。它们只模拟task／RCU，不证明真实Linux并发。严格解析器2组有效／重复输入通过，12组缺行、冲突、状态／计数／时间错误拒绝。Client Image构建与补丁清单检查退出0，冻结包只有client-Image改变。

**实机结果。** 完整720p 932分，33场景、validation26／1／6、VM0／0、健康／资源及11份日志SHA核验通过。外层退出1，错误为低于1000；既有validation数值例外保留。采样会话累计872500次暂停、214次稀疏快照（首次77／重试137），与每4096次步长和原PRIVATE_COMPLETION次数精确对账；扫描截断0、表满丢失0、空快照1。

| 类别 | 含该类别的快照 | 快照比例 | 任务命中总数 |
| --- | ---: | ---: | ---: |
| 真正可运行快照 | 211 | 98.598% | 219 |
| EEVDF延迟出队 | 3 | 1.402% | 3 |
| 队列中但非运行状态 | 0 | 0.000% | 0 |

| PID | comm | 类别 | 内核线程 | 首次／重试命中 | 首末累计执行差ms | 首末累计run-delay差ms |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 15 | ksoftirqd/0 | 真正可运行快照 | 1 | 0／2 | 66.777 | 1258.567 |
| 16 | rcu_preempt | 真正可运行快照 | 1 | 3／4 | 175.670 | 4270.651 |
| 202 | glmark2-es2-nul | 真正可运行快照 | 0 | 73／134 | 130786.219 | 211230.339 |
| 1306 | sh | 真正可运行快照 | 0 | 0／1 | 0.000 | 0.000 |
| 1320 | grep | 真正可运行快照 | 0 | 0／1 | 0.000 | 0.000 |
| 1799 | tee | 真正可运行快照 | 0 | 0／1 | 0.000 | 0.000 |
| 202 | glmark2-es2-nul | EEVDF延迟出队 | 0 | 2／1 | 23993.497 | 60941.749 |

类别可同快照重叠、一个快照可有多个同类任务，比例和命中数不可相加为时间占比。累计执行／run-delay的差值覆盖该身份首次至末次被采到之间的所有活动，含非暂停区间；同一任务跨类别的区间也可能重叠，不能相加或称作等待造成的CPU开销。字段读取未锁定runqueue，不是原子调度快照；确定性稀疏采样会受任务节奏偏差影响，不能外推FD全程869596次等待的精确类别，更不能推导可恢复的分数。

**行动变化。** 实际快照进一步把竞争者定位为glmark主线程：它在214个快照中207次处于可运行类别，少量样本为RCU／softirq等内核线程；EEVDF延迟出队只出现在3个快照。该结果支持继续验证应用与高优先级GPU worker的协作，不支持将FD总计数全部归为假阳性，也不能把累计run-delay都归因忙等。下一候选是只在首次预测等待中使用绝对截止的零slack高精度timer让出CPU，后续八次50µs快查保持主动观察；它与历史所有短等待都改usleep_range(50,100)的方案不同，仍须完整720p和长尾／语义验证。FD的总计数不再单独作为“应用被worker忙等压制”的证据；以本轮可运行实体与延迟出队实体的分离结果决定后续采样或机制设计。暂不直接重复短usleep、降低worker优先级或只换等待常数；没有删减RMM安全检查，也没有用新调度计数代替真实完成证明。下一性能候选须说明减少的是哪段实际工作及依赖／错误／撤销语义为何保持，不能将GPU执行期间的等待统一当作CPU成本。

执行与证据：

- `private-heap-720-20261101-fe`：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-fe -- python3 build/rmm-client-bo-20261030/runnable-identity-fe/run.py measure`，退出1。冻结runner参数`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`；完整命令、频率／UART、前后资源和11份已核验日志在`build/lab-runs/private-heap-720-20261101-fe/`。
- `private-runnable-identity-restore-20261101-fe`：同lab-run入口执行`python3 .../runnable-identity-fe/run.py restore`，退出0。仅原子恢复冻结ED Client Image，四项板端Guest与实际SD2原DA固件逐项SHA核验；CPU0–1／pmthor、无VM或loop遗留。
- `python3 scripts/check/check-gpu-private-submit.py`退出0（113场景）；`python3 .../check-observer.py`退出0（15场景）；源码／构建／解析／恢复的命令及退出码在实验目录。恢复后原113场景再次退出0。`final-verification.json`核验146项生产输入、187项冻结输入和7项额外调度器／runner依赖，`peer-summary.json`保存全部身份、mask与守恒检查。

唯一临时源码变化已撤回，候选／模型／失败证据保存在build目录；构建缓存仍可能含诊断镜像，不可误作ED。当前仍DA RMM＋ED Client＋原DX runner，纯对照935；恢复后无新增GPU测量。1000门槛、API／ML／多Client扩展、真实GPU完成eventfd与实体隔离验收仍未完成；AE EBUSY、历史Group submit超时和validation例外保留，整体goal不标记完成。


## FF：首次预测等待使用绝对高精度timer（2026-11-01）

改动目的｜利用GPU执行期间的首次预测区间，让实际处于可运行状态的glmark主线程获得CPU｜紧邻原版934 → FF566｜-368／-39.40%｜仅Client首次等待方式变化；完整720p33场景、GPU实际594MHz、CPU自动频率、单vCPU、DA RMM／Proxy／Host／initrd／原DX runner相同；无固件写入或Host重启｜下述run-id、命令、退出码及日志｜未满足预先保留规则，已撤回；1000门槛未通过。

**新增依据与改动。** FE的214个稀疏快照中207次出现可运行glmark主线程，因而本轮检验真实任务协作，不重复编译选项、memcpy或BO布局微调。在首次预测暂停已经成立、锁已经释放之后，只执行一次`set_current_state(TASK_UNINTERRUPTIBLE)`和`schedule_hrtimeout(..., HRTIMER_MODE_ABS)`；目标是原before＋既有complete_pause_ns、零timer slack，上限仍200µs。若显式提前唤醒，继续原来按elapsed计时的剩余主动间隔，不重新申请相对睡眠；若进入timer前目标已过期，不另加一个区间。后续最多8次50µs主动重试、普通tick回退、训练规则和任务绝对deadline不变，timer返回值从不作为完成证明，仍须真实FINISH、错误传播和退休。

这与AD在所有短重试中调用相对`usleep_range(50,100)`（曾出现27s长尾）以及EF只改变8次重试后的1ms慢等待不同。保留高优先级ordered worker。请求的绝对到期时间不保证真实唤醒延迟，Guest／Host调度仍可使暂停超时；本轮预先要求分数≥max(946, ceil(紧邻对照×1.01))、blur≥141／terrain≥26／大卷积≥670，同时暂停最大值≤max(10ms,对照×2)、≥10ms次数≤max(5,对照×2)。以新对照计算为分数946、最大暂停21.180ms、长等待次数5。没有降低1000扩展门槛。

**本地验证。** 修改前正常重建与ED的18415616字节可执行前缀逐字节一致。实际Client planner／worker的ASan／UBSan模型118场景通过（原113＋正常到期、早醒、20ms调度超时、进入timer前已过期及独立8次快查共5项），包含既有取消／错误／依赖／fence／不重放START条件；它不证明真实timer、Linux并发或GPU隔离。ARM64 Image与补丁清单检查退出0，包内仅client-Image改变。开发期新测试对假时钟的精确边界断言少计了读时钟开销、首次构建漏写头文件结束括号，均被本地检查拒绝并修正，失败日志保留；不作为硬件失败或测试PASS覆盖。最终源码只增加首次timer调用及头文件，不改RMM或Proxy。

| 指标 | 原版 | FF | 说明 |
| --- | ---: | ---: | --- |
| 完整720p | 934 | 566 | -368／-39.40%，保留线946 |
| blur | 152 | 168 | +16 |
| terrain | 28 | 29 | +1 |
| effect2d_5x5 | 744 | 97 | -647 |
| 首次暂停均值µs | 164.286 | 902.243 | 包括Guest／Host调度，非纯CPU时间 |
| 所有短暂停最大ms | 10.590 | 15692.637 | 请求上限不等于真实唤醒保证 |
| ≥10ms短暂停次数 | 1 | 14 | 长尾保护False |
| FINISH查询／退休批 | 2.457 | 2.003 | 操作次数，非GPU执行次数 |
| PREPARE操作µs／退休批 | 138.181 | 135.967 | 累计会话墙钟 |
| COMPLETE操作µs／退休批 | 198.506 | 195.188 | 累计会话墙钟 |
| COMPLETE间隔µs／退休批 | 265.501 | 987.728 | 含暂停、排队与调度 |

本轮查询／批减少18.47%，但首次暂停均值增加449.19%，COMPLETE间隔增加272.02%；最大暂停从10.590ms扩大至15.693s，≥10ms次数1→14。blur152→168／terrain28→29的局部改善没有抵消大卷积744→97等退化，总分934→566（−39.40%）。这使“只要应用可运行，短timer让出CPU就能提速”的假设被端到端结果否定；在当前DA／ED下，绝对到期、零slack及高优先级worker仍未消除严重睡眠／唤醒长尾。后续先区分Guest timer实际到期、唤醒到运行、Host vCPU失去执行三段，不再换短睡眠常数重试。当前墙钟不能确定具体根因，也不能将某一次15s异常直接归到某个场景。

两轮均33场景、validation26／1／6、VM0／0，健康／资源及各11份日志SHA核验通过；既有数值validation例外保留。场景保护False、长尾保护False，综合保留规则未通过；没有新保留运行优化。日志原有active_pause=1表示仍保留主动快查路径，本候选首次区间含timer睡眠，不能把该桶直接当作CPU忙等时间。各项会话统计含预热／验证且工作量不同，不能相加为纯CPU成本或按比例推算可恢复分数。glmark可运行只是必要线索，并不证明让出CPU能与足够多应用工作重叠；不只改slack、sleep时长或worker优先级重复测量。

执行与证据：

- 对照`private-heap-720-20261101-ff-control`、候选`private-heap-720-20261101-ff`：`python3 scripts/maintenance/lab-run.py --run-id <ID> -- python3 build/rmm-client-bo-20261030/first-cooperate-ff/run.py control|measure`，退出1／1；错误为低于1000。冻结runner参数`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`；每轮完整命令、频率／UART、前后资源及11份已核验日志在`build/lab-runs/<ID>/`。对照仅使用原ED冻结包；候选源码／构建与远端原版对照可独立进行，执行镜像和runner保持不可变。
- 恢复`private-first-cooperate-restore-20261101-ff`：同lab-run入口执行`python3 .../first-cooperate-ff/run.py restore`退出0，原子恢复ED Client Image，四项Guest和实际SD2原DA固件SHA核验。CPU0–1／pmthor，无本次VM或loop遗留。
- 本地`python3 scripts/check/check-gpu-private-submit.py`退出0（118项）；模型／构建／补丁检查命令、退出码和失败日志在实验目录。恢复后113项原模型退出0。`final-verification.json`核验146项生产输入、187项冻结输入及5项timer／runner依赖；精确对账和分段数据见`hardware-*.json`、`phases-*.json`和`scene-comparison-*.json`。

仅撤回本轮两个源码文件，候选及失败证据保存在build目录；构建缓存仍可能含候选，不可误作ED。当前仍DA RMM＋ED Client＋原DX runner，最新纯对照934；恢复后无新GPU测量。1000门槛未通过，API／ML／多Client扩展、真实GPU完成eventfd、实体隔离验收NOT_RUN；AE EBUSY、历史Group submit超时、validation例外及整体goal继续未完成。


## FG：定时器触发、唤醒与恢复分段诊断（2026-11-01）

改动目的｜定位FF首次timer等待15秒长尾发生在触发前还是线程恢复阶段｜最近纯ED对照934 → FG诊断639｜-295／-31.58%｜同DA RMM／Proxy／Host／initrd／原DX runner、GPU实际594MHz、CPU自动频率、单vCPU；仅Client在FF首次等待机制上加分段观测；原对照来自FF控制轮，本轮未新跑紧邻对照｜run-id、命令、退出码与日志见下｜诊断预定总是撤下，已恢复DA／ED；无保留性能收益，1000未过。

本轮将“定时器已到期但worker未运行”的泛化说法拆为可核验的时间点：原before、绝对target、入timer前、开始schedule前、回调进入、wake_up_process返回、schedule返回、cancel返回。局部栈sleeper沿用当前非PREEMPT_RT内核的schedule_hrtimeout生命周期：CLOCK_MONOTONIC、绝对到期、零slack；回调先清空task再唤醒；cancel等待回调结束才销毁栈对象。回调只写局部样本，不访问pcfile；worker汇总计数，stop在队列排空后输出6条短统计和最大事件的9个字段。没有修改通用hrtimer／调度器／Host／RMM，也没有逐事件printk。原预测上限200µs、早醒后的剩余主动等待、后续8次50µs、绝对任务期限和真实FINISH／fence／回收条件保持。

**定位结果。** 共281762次首次睡眠均观测到回调，0次外部提前唤醒，5次到检查点时已触发而跳过schedule；0次取消阶段才触发回调。总等待与回调晚到各有13次≥10ms，回调到恢复和取消均没有≥10ms。以下均为Guest累计会话墙钟，包含预热／校验及Guest／Host抢占，不是纯CPU成本；各指标存在包含关系，不相加。

| 分段 | 均值µs | 最大值µs | ≥10ms次数 |
| --- | ---: | ---: | ---: |
| 首次timer辅助函数总等待 | 679.210 | 15239841.465 | 13 |
| 入timer前已晚于target的部分 | 0.000457 | 54.691 | 0 |
| target到回调进入的晚到部分 | 493.473 | 15239570.013 | 13 |
| 回调进入到worker恢复 | 29.061 | 7481.542 | 0 |
| wake_up_process及其前后计时 | 3.280 | 11.375 | 0 |
| 恢复后取消timer | 0.122 | 72.916 | 0 |

最大事件id149985的原始共同CLOCK_MONOTONIC时间如下，单位ns：

| 字段 | 值 |
| --- | ---: |
| before | 262279966791 |
| target | 262280046910 |
| arm | 262279967082 |
| schedule前 | 262279967957 |
| callback | 277519616923 |
| wake结束 | 277519626256 |
| worker恢复 | 277519807965 |
| cancel结束 | 277519808256 |

该事件实际请求80.119µs，timer总等待15.239841465秒；target→callback晚到15.239570013秒，占总暂停约99.9982%；callback→worker恢复191.042µs，cancel0.291µs。**最大的已复现异常主要在回调之前，不能解释为回调已经唤醒worker后，worker等了15秒才获得CPU。** 平均回调到恢复29.061µs、最大7.482ms，仍有优化空间，但不是本次15秒异常的主要位置。

这并不直接证明Host、RMM或架构timer有缺陷：尚可能包含Guest IRQ交付／屏蔽／处理延迟、hrtimer队列处理、Host vCPU未获执行或中断路由等待。本轮没有IRQ入口与Host vCPU共钟链，不能在这些可能性中直接归因。两个≥10ms桶计数相等不替其余事件补逐项配对；只有最大事件有完整关联记录。也不能把这个最大事件按printk的local_clock对齐到某个glmark场景，既有ES／ET的时钟约束继续适用。

**性能与验证。** 33场景全部执行，诊断总分639，相对最近纯ED934为−295／−31.58%；退出1的runner错误为低于1000。blur152→168、terrain28→29、大卷积effect2d744→733；shadow575→111、cel1158→237等退化也保留。FF的大卷积97与本轮733不同，不将FG639对FF566说成提速：机制和计时扰动不同，异常落点也可能变化，不能据单轮场景分数关联某一次15秒暂停。

实际Client planner／worker ASan／UBSan模型122场景通过（原113＋8项timer分段情形＋初次timer与后续8次主动重试独立共9项）；覆盖15秒回调延迟、20ms恢复延迟、提前唤醒、取消回调竞态、目标已过期、慢取消、进入schedule前已触发等。它验证实际辅助函数的归类／生命周期流程，不证明Linux并发或真实IRQ。严格报告解析器接受完整样本，拒绝缺字段、冲突副本、非法状态和计数不守恒4种输入。ARM64构建／上游补丁manifest检查退出0；仅Client Image变化。realm-1.log与failure-kernel-1.log的完整16行报告逐项一致，11份回收证据SHA通过；151项生产／timer配置输入、188项冻结输入、6项timer依赖、7项分析依赖均核验。

硬件validation仍26 PASS／1已知数值FAIL／6 SKIP，VM退出0／0，两端解绑／内核日志、Host内核健康及资源恢复通过。CPU信号源的SYNCOBJ_EVENTFD冒烟PASS不等于真实GPU完成eventfd通过；真实GPU完成eventfd和广泛API／ML／多Client／实体隔离本轮NOT_RUN。AE VM_BIND EBUSY、历史Group submit超时及已知数值例外继续保留。

执行与证据：

- `private-heap-720-20261101-fg`：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261101-fg -- python3 build/rmm-client-bo-20261030/timer-stages-fg/run.py measure`，退出1；冻结参数`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。完整命令、前后资源／频率／UART、健康与11份SHA证据在`build/lab-runs/private-heap-720-20261101-fg/`。
- `private-timer-stages-restore-20261101-fg`：同lab入口执行`python3 build/rmm-client-bo-20261030/timer-stages-fg/run.py restore`，退出0；原子恢复ED Image并核验四项Guest与实际SD2 DA固件，CPU0–1／pmthor，无VM或loop遗留，无固件刷写或Host重启。
- 本地模型命令`python3 scripts/check/check-gpu-private-submit.py`退出0（122项）；ARM64构建、补丁清单、解析器与分析脚本／退出码保存在实验目录。撤下后原113项模型再次退出0，151项生产输入全部恢复原哈希。`hardware.json`、`timer-report.json`、`assessment.json`和`final-verification.json`保存结论及边界。

下一步优先沿Guest架构timer IRQ入口→hrtimer回调和Host vCPU／timer交付继续定位；先确认哪一段未及时获得执行，再选择修复或减少对该定时路径依赖的优化。不要只换slack、睡眠常数或worker优先级。当前仍DA RMM＋ED Client＋原DX runner，最新纯对照934；恢复后没有新增GPU分数测量。构建缓存可能仍含FG诊断Image，部署以冻结ED包为准；整体goal未完成。


## FH：架构timer中断入口分段诊断（2026-11-02）

改动目的｜进一步分解FG回调前长暂停｜最近纯ED934 → FH诊断655｜−279／−29.87%｜与FG相同的首次绝对零slacktimer机制、后续8次50µs主动观察；增加可嵌套每CPU架构timer／hrtimer实时作用域，DA RMM／Proxy／Host／initrd／原DX runner保持；GPU实际594MHz、CPU自动频率、单vCPU；对照来自FF，非紧邻，本轮不计优化收益｜下列run-id、命令、退出码及日志｜预定总是撤下，已恢复DA／ED，1000未过。

**机制与结论。** 在架构`timer_handler`入口、交接clockevent、`hrtimer_interrupt`入口及目标sleeper回调记录同一CLOCK_MONOTONIC。只接受回调内仍活跃、顺序合法的架构与hrtimer作用域，嵌套退出恢复旧作用域，避免把过去一次IRQ当成当前来源。移除新增诊断语句后的原通用timer语句与基线一致。共279727次回调全部获得有效链，外部早醒0、已触发跳过schedule4、取消后触发0、其他／过期／非法样本0。总暂停、回调晚到及架构入口晚到各14次≥10ms，其后各IRQ处理阶段均无≥10ms。

| 区间 | 均值µs | 最大值µs |
| --- | ---: | ---: |
| target→架构handler入口晚到 | 552.522 | 16061677.929 |
| handler→clockevent交接 | 0.169 | 2.625 |
| 交接→hrtimer入口 | 0.123 | 1.167 |
| hrtimer入口→目标回调 | 0.661 | 16.042 |

最大事件id93119：before133568417938、target133568617725、arm133568418230、schedule前133568419105、IRQ149630295654、dispatch149630295946、hrtimer149630295946、callback149630308779、wake结束149630315487、resumed149630440612、cancel149630440904（均ns）。总暂停16.062022966秒，架构handler入口晚16.061677929秒，占99.99785%；入口到回调13.125µs，回调到恢复131.833µs，cancel0.292µs。access=1、control=5表明该样本使用虚拟timer且读取时使能／未屏蔽／已到期。

这是**架构timer处理函数入口**，不是CPU异常向量入口；之前仍包含Guest IRQ屏蔽与通用分发、物理路由和使能、Host vCPU未执行等可能性。内部区间也可能包含Host抢占。没有Host／Guest共同时间线或逐场景关联，不把墙钟视为纯CPU成本，也不由最大样本替其他事件配对或归因。

**进一步实际检查。** 只读`/dev/mem`读取空闲Host的GICR_TYPER与ISENABLER0，CPU0–1的PPI27／30均启用；CPU2–3离线且位为0。临时程序上传SHA核验、只读映射、执行后删除，无MMIO写。这不是长暂停期间的每REC保存状态，不能证明使能遗漏已触发。Host tracefs具备sched／IRQ／KVM timer事件，未改变事件或tracing开关；没有新增Host内核。

实际RMM平台逻辑在Realm运行期间仍使用`saved_host_enables & ~mask`，当保存位为0而Realm timer尚未assert时，不会使能其未来中断。隔离副本将其改为`TIMER_MASK & ~mask`；保持assert输出屏蔽与有界HPPIR退休，退出精确恢复Host位，其他中断位不动。原模型131072转换／66退休通过，但新增Realm运行期使能属性拒绝原逻辑，隔离候选通过。此时生产RMM未改／未部署，尚不能宣称它是16秒暂停根因或可提高分数。

**验证。** 实际Client planner／worker ASan／UBSan130场景（113＋FG9＋FH8）、实际架构handler替身3场景（handled／no-pending／嵌套恢复）、严格解析2接受／7拒绝、ARM64构建和补丁manifest核验通过。完整33场景、validation26 PASS／1已知数值FAIL／6 SKIP、VM0/0；健康与资源恢复、11份证据SHA通过。152项生产输入、213项冻结输入、9项timer依赖、11项分析输入核验，五项临时源码均恢复，原113场景再次通过。缓存仍可能含FH Image，不可代替冻结ED。

执行与证据（均控制机仓库根目录）：

- `private-heap-720-20261102-fh`：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261102-fh -- python3 build/rmm-client-bo-20261030/irq-stages-fh/run.py measure`，退出1，仅因低于1000。完整参数、前后资源／频率／UART和11份核验日志在`build/lab-runs/private-heap-720-20261102-fh/`。
- `private-irq-stages-restore-20261102-fh`：同lab入口执行`python3 .../irq-stages-fh/run.py restore`，退出0；四项Guest及实际SD2原DA固件核验，CPU0–1／pmthor、无VM／loop遗留。
- `private-timer-probe-20261102-fh`、`private-timer-ppi-20261102-fh`：同lab入口执行实验目录的`probe-host-tracing.py`、`probe-ppi.py`，均退出0，只读能力／实际使能位核验，详见`host-trace-capabilities.json`和`ppi-probe.json`。
- `python3 .../irq-stages-fh/review-timer-enable.py`退出0；三组原版／新属性拒绝／隔离候选的编译、预期失败与退出码在`timer-enable-review/review.json`。`python3 .../irq-stages-fh/finalize-withdraw.py`退出0，精确恢复及原113模型日志见`final-verification.json`与`restored-submit.log`。

当前DA RMM＋ED Client＋原DX runner，最新纯对照934，本轮无保留提速，恢复后无新GPU测量。下一步只针对上述新使能反例做实际因果对照，不重复slack／worker优先级调参。1000、API／ML／多Client、真实GPU完成eventfd及实体隔离NOT_RUN／未完成；AE EBUSY、历史Group submit超时与数值例外保留，整体goal未完成。


## FI：独立使能Realm定时器PPI的实际因果对照（2026-11-02）

改动目的｜检验FH新增Host保存位为0的使能反例能否解释实机长暂停｜同FH Client＋DA固件579 → 同FH Client＋FI固件609｜+30／+5.18%｜两轮均是首次绝对零slacktimer＋FH活跃IRQ作用域诊断，其他Guest／Host／原DX／GPU实际594MHz／CPU自动频率／单vCPU保持，候选需要固件重建与重启；不与纯ED934计算提速｜run-id、命令、退出码与日志见下｜未消除长尾，撤回两项RMM源码并恢复DA固件／ED Client，1000未过。

**实际改动与本地边界。** 仅在`plat_opencca_timers_mask`把`timer_enables[cpu] & ~mask`替换为`TIMER_MASK & ~mask`，未来未assert的Realm timer PPI不再依赖Host保存使能位；已assert输出仍屏蔽，核心64次HPPIR有界退休、退出精确恢复Host位和非timer位保持。实际测试补充运行期使能属性，131072状态转换／66退休检查通过，原版被该新属性拒绝的隔离证据沿用FH。完整私有套件退出0、633条PASS标记；标记不等于633项独立硬件测试。固定构建选项／U-Boot源码归档、布局和FIT核验通过；只有RMM运行源码一项与对应测试一项变化。初次补丁校验命令误用了不存在的`opencca/scripts/apply-patches.py`，退出2，修正为`opencca/scripts/setup/apply-local-patches.py --check`退出0，错误记录保留；没有将错误命令记为PASS。

两轮都保留真实GPU完成、权限、deadline、错误和资源回收，timer返回与IRQ只作为调度／观测，不作为完成证明。新的因果筛选在候选完成前冻结：入口最大晚到≤100ms且≥10ms样本≤7；通过才值得追加正式性能候选对照，诊断本身总是撤下。未事后更改1000门槛。

| 指标 | 新对照DA | FI候选 |
| --- | ---: | ---: |
| 完整720p诊断分数 | 579 | 609 |
| 首次睡眠／有效IRQ链 | 253411／253411 | 252790／252790 |
| 非法链 | 0 | 0 |
| 首次总等待均值µs | 861.093 | 918.661 |
| 首次总等待最大s | 15.984058716 | 15.879637091 |
| 架构入口晚到均值µs | 677.122 | 729.086 |
| 架构入口晚到最大s | 15.983047302 | 15.878619037 |
| 入口晚到≥10ms次数 | 14 | 18 |

**结论。** 新反例在模型上成立，但实机长暂停没有消失，因此没有证据把它认定为已观测问题的根因或修复。也未读取异常期间每REC保存的使能位，不能断言此分支是否实际触发。单对照还包含重启／固件布局等差异；不由分数变动宣称稳定收益或与纯ED比较。下一步优先建立Host运行／IRQ／REC返回与Guest架构handler的共同时间线，区分Host未执行、物理通知未交付、RMM返回、虚拟注入与Guest屏蔽／分发，尚未实现该链。不再以相同使能反例、slack或优先级常数重试。

**执行与证据。** 以下命令均从控制机仓库根目录执行，硬件命令使用独占lab wrapper：

- `private-heap-720-20261102-fi-control`／`private-heap-720-20261102-fi`：`python3 scripts/maintenance/lab-run.py --run-id <ID> -- python3 build/rmm-client-bo-20261030/timer-enable-fi/run.py control|measure`，退出1／1，仅因未达1000。两轮完整33场景、validation26／1／6、VM0／0、两端解绑、内核健康／资源恢复及各11份证据SHA通过；日志位于`build/lab-runs/<ID>/`。
- `private-timer-enable-fw-20261102-fi`／`private-timer-enable-fw-restore-20261102-fi`：`python3 scripts/maintenance/lab-run.py --run-id <ID> --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware <FI firmware|firmware-private-running-check> --run-id <ID>`，均退出0。实际启动区备份、SD2镜像SHA、串口与Realm能力记录在`build/firmware-runs/<ID>/`；不写Host内核、rootfs或eMMC。
- `private-timer-enable-restore-20261102-fi`：同lab wrapper执行`python3 .../timer-enable-fi/restore.py`，退出0；只原子恢复ED Client，四项Guest及实际SD2 DA哈希核验；CPU0–1／pmthor、无VM或loop遗留。
- 本地`bash scripts/check/check-opencca-timers.sh`、`bash scripts/check/check-rmm-gpu-private.sh`、正确补丁清单、构建／布局／FIT均退出0。两组`python3 .../timer-enable-fi/analyze.py control|candidate`及`assess.py`退出0；最大事件完整原始字段、各分段／场景表分别保存在`timer-report-*.json`、`phases-*.json`和`scene-comparison-*.json`。`finalize.py`退出0，154项生产输入／215项冻结输入／5项分析输入核验后精确恢复两项RMM源码，原timer131072／66及Client113模型再次通过。完整命令／退出码见`commands-index.json`。

本轮保留失败与未执行项目，候选／诊断镜像和固件仅供复验，不误用构建缓存。当前DA RMM＋ED Client＋原DX，保留成绩仍引用此前纯对照934，恢复后未新增GPU测量。未保留新运行优化；1000、广泛API／ML／多Client、真实GPU完成eventfd、实体隔离均未完成；AE EBUSY、历史Group submit超时与validation数值例外保留，整体goal仍active。


## FJ：Host／Guest共同计数器时间线与CPU2局部对账（2026-11-02）

改动目的｜区分FH／FI的Guest timer入口长暂停是否主要来自Host未调度vCPU｜最近纯ED934 → FJ诊断391｜−543／−58.14%｜沿用已撤回的FH首次绝对零slack睡眠与活跃IRQ作用域，增加前后计数器锚点及Host tracing；DA RMM、Proxy、Host、initrd与原DX runner不变，GPU实际594MHz、CPU自动频率、单vCPU；对照来自此前FF纯ED，非紧邻对照，组合诊断扰动不作优化收益｜下列run-id、命令、退出码与日志｜预定总是撤下，已恢复DA／ED934，1000未过。

**机制。** Guest在首次睡眠前与实际回调内分别取得`mono_lo／CNTVCT／CNTPCT／CNTVCT／mono_hi／CNTFRQ`，最大样本用12条短行报告；真实完成、权限、原deadline、错误及生命周期判断均不依赖这些诊断时钟。Host使用独立tracefs实例、`mono_raw`时钟，记录调度／IRQ／KVM timer，以及`kvm_rec_enter`入口和返回kprobe，读取线程固定CPU0，流式回收到控制机。每CPU缓冲512KiB，追踪CPU0–3。32组运行前与32组运行后的Host原始时钟／计数器校准取共同界；确认Guest虚拟／物理计数器位于有序包围中、频率24MHz且单调时钟斜率一致。身份取自本次实际进程命令行和线程亲和性：Proxy tgid1318／vCPU1324在CPU1，Client tgid1319／vCPU1325在CPU2，不借用历史PID或printk local_clock估算。

**先保留全局失败，再单独限定可用范围。** Host追踪共27424070行，CPU0 overrun31401、其余损失计数为0；CPU1／2／3的overrun、commit overrun、dropped均0。原全局分析`analyze-timeline-v2.py`因CPU0 overrun退出1，结论保持FAIL。随后另行冻结`cpu2-scope.json`与`analyze-cpu2.py`，仅对实际固定Client CPU2做局部分析，完全不使用CPU0事件来计算运行区间。要求CPU2无丢失、调度链连续、入口／返回配对完整，kprobe入口与返回各1369400次、miss均0。该局部检查通过不能升级为全Host无损追踪或跨CPU因果证明。

初版解析器误以为本内核的kprobe profile包含组名，实际只有事件名；保留原文件与版本化修订，修订要求初始全局probe注册表为空、恰好两个预期事件且命中为正／miss为0，避免从同名记录中选择。两次trace冒烟因Python追加打开tracefs时尝试seek而失败，均退出1并保留日志；改用`os.open(O_WRONLY|O_APPEND)`和`os.write`后第三次退出0，未截断注册表。每次清理只移除本run实例与probe，并恢复原全局tracing／probe状态。

**实际结果。** 191910次首次睡眠全部有匹配的活跃IRQ链，非法链0；架构入口晚到≥10ms共30次。最大完整等待11.299316005秒，以下是同一样本id120298的分段，不替其他样本补配关系：

| 区间 | 实测 |
| --- | ---: |
| target→Guest架构timer handler入口 | 11.299061947秒 |
| handler入口→目标回调 | 22.750µs |
| 回调→worker恢复 | 223.417µs |
| Host映射区间长度 | 11.299061943秒 |
| Host将Client vCPU换出 | 14µs |
| Client在Host调度中、且处于REC调用内 | 11.298975943秒 |
| 单次最大REC调用与目标区间重合 | 99.99903067% |

Guest原始字段：before367228338757、target367228346357、arm367228339340、schedule367228339924、IRQ378527408304、dispatch378527408596、hrtimer378527408887、callback378527431054、wake_end378527442429、resume378527654471、cancel378527654762，单位ns；access=1、control=5，arch／hrtimer作用域均有效。

两个锚点分别为`[367228339049,39170378894,39170378894,39170378894,367228339049,24000000]`和`[378527431346,39441557109,39441557109,39441557109,378527431346,24000000]`。Host校准偏移共同界为[11588887478,11588891138]ns，计入显式2µs容差及追踪文本1µs分辨率后，映射不确定度约4.83µs。Guest单调时钟与计数器差分漂移5ns；两个独立Guest日志副本一致。Host目标区间[1620510238582,1631809300525]ns，最大单次REC从1620509906000到1631809191000ns。约11.299秒期间没有Host换出足以解释该长尾；Host timer IRQ与IPI出现在REC返回后附近。

原`timeline-cpu2.json`的`counter_anchors`报告字段错误：后续区间循环覆盖了局部变量a、b，使最终输出写入两个整数；端点换算在覆盖前已完成。保留原分析器、哈希与原报告，独立`review-counter-report.py`从两份原始Guest日志和64组Host校准重算，偏移界、目标端点与4.83µs界限逐项一致，另存`counter-report-review.json`与`timeline-reviewed.json`，只纠正报告锚点字段，不声称重新解析整份trace。原全局FAIL也保持。

**结论和下一步边界。** 该最大样本主要不是Host调度饥饿。但`kvm_rec_enter`在途可能包含Guest运行、Guest WFI、RMM内部循环／锁／服务，以及monitor执行；被Host视为正在调度不等于持续执行Guest指令。当前没有区分这些阶段，也没有记录长暂停期间的实际PPI使能位、timer重装或LR／maintenance状态，不能据此宣称已经定位RMM缺陷或证明所有ED性能差距都由该现象造成。

源码核查显示，RMM每次内部循环检查timer输出与GICR屏蔽；Host按软件level IRQ填入LR.EOI，RMM允许该位，Firecracker的timer DT为level-high。因此预期EOI维护路径在源码中存在，不能直接说“缺少EOI通知”。Realm的`kvm_timer_enable`在普通硬件映射前返回，随意把`timer->enabled`置位会启用其他普通timer保存／恢复路径，不是已有证据支持的修复。下一诊断应以共同计数器分开`run_realm`、`handle_realm_exit`与timer检查，并有界保存对应timer／GIC状态；短行聚合或最大样本报告避免每次IRQ打印。该内部诊断尚未实现／部署，记录在`gic-rearm-source-review.json`。不重复仅换slack、优先级或FI使能常数，也不省略真实完成／错误检查。

**性能与恢复。** 完整33场景执行，391分，退出1仅因低于1000；validation仍26 PASS／1已知数值FAIL／6 SKIP，VM0／0，两端解绑／内核日志、Host健康与资源恢复及11份回收证据SHA核验通过。实际Client130模型、时钟／区间检查及ARM64构建／补丁manifest退出0；时钟检查拒绝4种计数器、频率、包围或校准不一致输入，只验证离线检查器，不证明Linux并发或实体隔离。未刷固件或重启Host，部署只改变Client Image，撤下后原子恢复ED。159项生产输入、222项原冻结输入、分析与版本化scope清单核验；五项本地源码精确恢复，原113项提交模型再次退出0，四项板端Guest与实际DA SD2核验。最终CPU0–1／pmthor，无VM／loop遗留，tracing实例移除且全局状态恢复；恢复后没有新增GPU测量。构建缓存可能仍含FJ Image，不能作为ED部署。

执行与证据（控制机仓库根目录；硬件命令均持独占lab租约）：

- `private-host-timeline-probe-20261102-fj`：`python3 scripts/maintenance/lab-run.py --run-id private-host-timeline-probe-20261102-fj -- python3 build/rmm-client-bo-20261030/host-timeline-fj/probe.py`，退出0。
- `private-host-trace-smoke-20261102-fj`、`private-host-trace-smoke2-20261102-fj`、`private-host-trace-smoke3-20261102-fj`：同lab wrapper执行`python3 .../host-timeline-fj/trace-smoke.py`，退出1／1／0；实际完整命令及日志见`commands-index.json`，失败未覆盖。
- `private-heap-720-20261102-fj`：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261102-fj -- python3 build/rmm-client-bo-20261030/host-timeline-fj/run.py measure`，退出1；冻结参数`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。完整日志、Host trace／校准／身份／损失计数和前后资源在`build/lab-runs/private-heap-720-20261102-fj/`。
- `private-host-timeline-restore-20261102-fj`：同lab wrapper执行`python3 .../host-timeline-fj/restore.py`，退出0；Guest与SD2／健康恢复见`runtime-restoration.json`。
- `python3 .../host-timeline-fj/analyze-hardware.py`、`check-timeline.py`、`analyze-cpu2.py`、`review-counter-report.py`及`finalize.py`退出0；全局`analyze-timeline-v2.py`退出1。逐命令／退出码索引与`assessment.json`、`final-verification.json`保存在实验目录；`artifact-hashes.json`保留诊断、失败和恢复证据摘要。

当前仍DA RMM＋ED Client＋原DX runner，保留纯成绩934；本轮无新增保留优化。1000门槛、广泛API／ML／多Client、真实GPU完成eventfd及实体隔离仍未完成／NOT_RUN；AE VM_BIND EBUSY、历史Group submit fence超时与validation数值例外保留，整体goal仍active。


## FK：RMM内部阶段诊断与报告完整性失败（2026-11-02）

改动目的｜沿FJ继续区分Guest运行和RMM内部处理的长暂停｜最近纯ED934 → FK诊断190｜−744／−79.66%｜复用已冻结FJ Client Image及睡眠／计数器机制，仅RMM增加内部阶段记录，不开启Host ftrace；Proxy、Host、initrd与原DX保持，GPU实际594MHz、CPU自动频率、单vCPU，候选固件需要重启；非紧邻纯ED对照，组合诊断与代码布局扰动不能隔离归因｜下列run-id、命令、退出码和日志｜预定总是撤下，已恢复DA／ED，1000未过，无保留提速。

**实际机制。** 在`rec_run_loop`分别包围timer检查、`run_realm`（含PAuth保存／恢复）和`handle_realm_exit`，以物理计数器记录调用次数／累计区间／最大值，保存每阶段最慢6个≥10ms区间。只对冻结runner固定在CPU2的Client启用记录，不能据此分析Proxy。保留区间包含起止计数、异常／继续状态、前后timer CTL／CVAL与PSTATE、结束时ESR／MISR／HPPIR／ICH_HCR／私有LR和只读GICR使能快照；边界状态不是连续IRQ状态证据。每REC owner变化重置；仅在PSCI SYSTEM_OFF输出两份短行副本，不在每次IRQ或RSI中打印。

诊断不参与身份、映射、GPU完成、错误、deadline或生命周期判定；PAuth Realm key生效期间的原语句区间逐字一致，原平台timer屏蔽／恢复函数逐字保留，仅追加只读观察函数。没有新生产ABI或Client修改／重建。现有FJ Image的源码、构建和模型证据仍是其来源，不把当前本地ED源码称为FJ运行源码。

初版为16个CPU各保存top8，RMM链接时`.stack`末端达到0x260c000，超过原0x25ff000边界，退出2；没有部署该产物，也没有增大内存／栈或缩减GPU对象容量。保留`run-initial-overflow.c`、`build-initial-commands.json`与`rmm-build-initial.log`，只将诊断范围收缩为本轮Client CPU2／top6后重建，布局与FIT通过，`rmm_end`仍为原0x25ff000。实际top6辅助函数经ASan／UBSan检查递增／递减输入、阈值、相等值、不合法计数与累计溢出；普通timer131072转换／66退休、完整私有套件639条PASS标记、上游补丁manifest通过。标记不是639项独立硬件用例。

**实机执行及失败边界。** 完整720p33场景完成，glmark进程退出0、分数190，wrapper退出1仅因低于1000；validation26 PASS／1已知数值FAIL／6 SKIP，VM退出0／0，BO创建／导出／VM_BIND／OOM进度计数未见新增错误。两端解绑／内核日志、Host内核健康、资源恢复及11份回收证据SHA核验通过。只上传Client Image；RMM在独立SD2固件部署中更新，不刷Host内核、rootfs或eMMC。

**RMM阶段证据没有通过。** UART中的`FK_SUM`／`FK_SLOT`行存在丢字段与拼接，例如`FK_SUM cpu=2 copy=0 p=0 f=0 vv=0`。冻结的`parse-phases.py`要求两份完整、字段唯一且一致的报告，实际`analyze-overlap.py`退出1，未生成有效阶段对齐结论。离线1份合法样本／7种损坏拒绝通过不替代实机报告完整性。保留完整原始UART与失败日志；不修补缺字段，不从零散的CTL、EOI、异常码或时间数字推定主因，也不把没有完整观察到某个阶段当作该阶段没有停顿。

**Client文件报告单独核验。** `realm-1.log`与独立`failure-kernel-1.log`各含两组`FH_TIMER`报告：262次和106218次睡眠。原FJ单报告分析器将其判为冲突，`analysis-hardware.log`退出1并保留。版本化`parse-client-reports.py`按每个完整FH_TIMER头分组，分别严格检查阶段计数、最大样本、12个本组时钟字段，再要求两份日志解析结果逐项一致；不混合两组的分母、tail或锚点。两组均通过，另以4种缺尾／错ID／错计数／错字段输入验证拒绝。`analyze-hardware-v2.py`在保留原失败的前提下验证完整硬件运行，退出0。它没有恢复RMM UART阶段证据。

第二组包含两组中最大的完整等待：样本id106217，总等待16.405234424秒，target到架构timer入口晚16.404909886秒，入口到回调2.333µs，回调到worker恢复122.208µs。原始CLOCK_MONOTONIC（ns）：before504995832865、target504996032862、arm504995833448、schedule504995834031、IRQ521400942748、dispatch521400943039、hrtimer521400943331、callback521400945081、wake_end521400950039、resume521401067289、cancel521401067289。该组106218次睡眠全部回调；只将这一完整样本作为仍有回调前长尾的证据，不替其他样本补逐事件关联。第一组最大完整等待1.149750ms。两组明细分别保存在`client-reports.json`，`timer-report.json`明确标注选择规则和report_index。

**结论。** 本轮复现长尾，但因RMM阶段报告失败，仍不能区分Guest／WFI／monitor执行与RMM内部服务／锁。FJ的CPU2局部共钟结论仍只属于FJ样本，不能移植为本轮Host换出时间。934→190的退化也不能单独归因某条计时指令、关机打印或某个硬件握手；没有紧邻生产对照，未据此宣称优化或修复。

下一步应将有界诊断记录通过显式读取取回，带运行代次／记录数／字段完整性检查，并继续保留受保护元数据和原完成判断。先取得完整区间，再匹配Guest样本；不能仅提高UART副本数或凭损坏记录调整EOI／PPI／睡眠常数。该读取机制尚未实现／部署，内部阶段归因仍未完成。

**撤回与证据。** 以下硬件命令均经独占lab wrapper，控制机仓库根目录执行：

- `private-realm-phases-fw-20261102-fk`：`python3 scripts/maintenance/lab-run.py --run-id private-realm-phases-fw-20261102-fk --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/realm-phases-fk/firmware --run-id private-realm-phases-fw-20261102-fk`，退出0。布局、FIT、SD2备份／回读、串口和Realm能力核验见`build/firmware-runs/<ID>/`。
- `private-heap-720-20261102-fk`：`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261102-fk -- python3 build/rmm-client-bo-20261030/realm-phases-fk/run.py measure`，退出1。完整参数`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`；完整33场景、前后资源／频率／UART／独立日志在`build/lab-runs/<ID>/`。
- `private-realm-phases-fw-restore-20261102-fk`：同固件lab wrapper以`firmware-private-running-check`恢复原DA，退出0；仅SD2，恢复后Realm能力为1。
- `private-realm-phases-restore-20261102-fk`：同lab wrapper执行`python3 .../realm-phases-fk/restore.py`，退出0；原子恢复ED Client，四项Guest与实际DA SD2哈希一致。最终CPU0–1／pmthor，无VM或loop遗留。
- 本地`build.py`初次退出1（其rmm-build退出2）；`build-v2.py`退出0，全部新日志与失败均保留。`analyze-hardware.py`／`analyze-overlap.py`退出1／1，`analyze-hardware-v2.py`退出0，不能互相覆盖状态。`finalize.py`退出0，核验225项冻结输入及分析清单后恢复三项RMM源码，161项生产输入逐项恢复原哈希；原timer131072／66及Client113模型再次退出0。完整命令／退出码见`commands-index.json`，结论／边界见`assessment.json`，恢复见`final-verification.json`，产物摘要见`artifact-hashes.json`。

当前仍DA RMM＋ED Client＋原DX runner，最新纯对照934；恢复后没有新增GPU测量，无保留运行优化。FK镜像／固件只作失败诊断与复验材料，构建缓存不可代替冻结基线。1000门槛、广泛API／ML／多Client、真实GPU完成eventfd与实体隔离均未完成／NOT_RUN；AE VM_BIND EBUSY、历史Group submit超时和已知数值例外继续保留，整体goal仍active。

## FL：冻结阶段快照与长等待归因（2026-11-02）

**本轮完成可核验的RMM阶段读取，将最大长等待定位到Realm执行区间；没有新保留提速，已恢复DA／ED934。** FK的UART阶段报告损坏，不能直接据此修改timer／EOI。FL复用冻结FJ Client和CPU2／top6采集，改用固定字段的只读查询取回统计；不使用FK碎片补值，也没有重建Client。

统一记录：**解决阶段报告丢失并核对长等待位置｜最近纯ED对照934 → FL诊断341｜−593／−63.4904%｜同完整1280×720、null-noop／finish、33场景、GPU请求600MHz／实际594MHz、Proxy CPU1／Client CPU2；对照非紧邻，诊断首次睡眠、计数器和RMM采集及固件重启同时不同，只归因组合效果｜`private-heap-720-20261102-fl`，退出1，仅未达1000｜诊断撤下，DA／ED恢复；根因及提速待验证。** 不能将341或与FK190的差值称作生产优化收益。

### 读取设计与本地检查

- 保留原RMI FID范围，在已有GPU_PM入口使用临时诊断操作；独立wrapper分流，原PM函数与权限／回收路径保留。只允许索引读取334个标量，含版本、CPU、频率、字段数及代次，不接受地址或写入请求，不返回REC指针。
- CPU2关机时冻结统计，专用自旋锁提供发布与读取的acquire／release顺序。新REC或冻结后的再次进入先失效、递增代次并清表；不解引用已释放的owner。读取只在冻结时成功，不与正在变化的表并发取值。
- 外部读取模块匹配`6.12.0-opencca-pmthor-opp3`，显式使用同一LOCALVERSION构建。先取两份完整SMC快照，再读取两次0400文件并比较；实际验证越界索引及旧代次拒绝，结束卸载模块。运行中不读表，不依赖UART文本。
- 实际334字段查询的ASan／UBSan边界与代次检查、top6选择检查通过；解析器接受完整报告，拒绝10种字段／顺序／版本／代次／跨度错误。原timer模型131072转换／66有界退休及完整私有套件639条PASS标记通过；这些不是独立硬件用例数。RMM构建、原固定BSS／栈布局、FIT和补丁manifest检查通过，未扩大预留区或容量。
- 初次直接在PM函数中插入诊断分支，使抽取该函数的回收模型缺少声明而编译失败；保留`private-initial.log`，改为独立wrapper后完整套件通过。初次查询测试模板误替换标记字符串，保留`query-test-initial-failed.c`，修正分隔标记后通过。均发生在部署前，没有覆盖失败记录。

### 实机结果与归因边界

完整33场景，validation为26 PASS／1已知数值FAIL／6 SKIP，VM退出0／0；预热计算、basic／eventfd冒烟通过。当前依旧不能把CPU SIGNAL的eventfd冒烟当作真实GPU完成eventfd验收。Host健康、频率／资源恢复通过，读取模块卸载后的整次boot日志无BUG／Oops／WARNING。共12份文件SHA核验，含本轮读取模块；硬件分析V2按这个真实集合校验，冻结V1的11文件旧预期未冒充已执行通过。

新接口实际取回完整334字段，冻结代次1，两个SMC副本及两次文件读取一致。Client文件中的两组独立报告分别校验（264／158265次睡眠），并与独立failure-kernel文件一致；不合并计数或锚点。最大样本来自第二组：

| 核对项 | 本次测量 | 可以说明什么 |
| --- | ---: | --- |
| 等待目标到架构timer入口 | 15.470060469秒 | 长尾主要发生在处理函数入口前 |
| 回调到worker恢复 | 814.917µs | 不能解释上述秒级入口晚到 |
| 与实际保留`run_realm`＋PAuth区间重合 | 99.999434% | 该样本主要在Realm执行边界内 |
| timer检查最大区间 | 1.458µs | 本次未见该检查本身的秒级停滞 |
| `handle_realm_exit`最大区间 | 127.701ms | 已保留的退出处理长区间未与最大样本重合 |
| 计数器桥接不确定度／两锚点漂移 | 约2.042µs／8ns | 支持本次样本的跨层区间核对 |

`run_realm`计时包含PAuth保存／恢复，仍可能包含Guest运行、空闲等待和monitor路径，**不是纯Guest CPU剖析，也没有证明具体WFI或timer缺陷**。只保留每阶段最慢6个≥10ms区间，不能用其缺失证明其余阶段在整个样本内完全未执行，或把阶段累计墙钟当作可节省CPU成本。本轮未重新采集Host调度trace，不将FJ另一轮的14µs直接移植到此轮。

六个保留的最长run区间，入口／出口CNTV_CTL均为5（启用、到期、未屏蔽），CVAL未变，均以IRQ异常退出；退出处物理PPI27关闭。**RMM对已到期PPI的屏蔽属于原机制，单看此值不能认定bug。** 已记录的private LR是事件IRQ127，不是timer IRQ27，不能据此推断timer LR为空或EOI丢失。最大样本两端PSTATE.I为1，也不证明整个区间持续关中断。

下一轮应检查**实际timer IRQ27的LR状态、HCR／ELR及前序退出的timer输出变化**，区分快速返回Realm期间的中断交付／空闲等待与Guest关中断执行。取得这些证据后再决定修改点；不重试仅换slack、worker优先级或PPI使能，也不取消真实FINISH、绝对deadline、错误和生命周期检查。

### 命令、证据与恢复

本轮目录为`build/rmm-client-bo-20261030/realm-phases-fl/`。完整命令、退出码与日志见`commands-index.json`；原始硬件证据在`build/lab-runs/private-heap-720-20261102-fl/`。

- `private-realm-phases-fw-20261102-fl`：lab wrapper加`--allow-rk-reboot`，执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/realm-phases-fl/firmware --run-id private-realm-phases-fw-20261102-fl`，退出0；仅SD2，Realm能力1。
- `private-heap-720-20261102-fl`：lab wrapper执行`python3 build/rmm-client-bo-20261030/realm-phases-fl/run.py measure`，退出1；子命令使用冻结`runtime-candidate`、`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`。`phase-retrieval.json`、`phase-report.json`及`timeline-overlap.json`通过完整性／共钟检查。
- `private-realm-phases-fw-restore-20261102-fl`：reboot wrapper执行`pre-restore.py`，先保存读取模块后的健康证据，再以`firmware-private-running-check`恢复DA，退出0。
- `private-realm-phases-restore-20261102-fl`：lab wrapper执行`restore.py`，退出0；恢复ED Client，核验四项Guest及实际DA SD2。最终CPU0–1／pmthor，无VM或loop残留。
- `analyze-hardware-v2.py`／`analyze-overlap.py`退出0／0；`finalize.py`退出0，核验271项冻结输入后恢复七项临时RMM源码，163项生产输入逐项恢复原哈希，原timer131072／66及Client113模型复测退出0。恢复后没有新增GPU测量。

最终结论见`assessment.json`，边界解码见`boundary-review.json`，恢复见`final-verification.json`。当前仍DA＋ED＋原DX、纯对照934；1000门槛未过，广泛API／ML／多Client、真实GPU完成eventfd与实体隔离为NOT_RUN／未验收；AE VM_BIND EBUSY、历史Group submit超时和validation例外继续保留。整体goal仍active。本轮文档仅整理上述测量，文档修改本身不产生性能收益。

## FM：实际定时器 LR、Guest 空闲位置与退出快照竞态反例（2026-11-02）

改动目的｜在FL共同计数器归因后，核对真实IRQ27、Guest PC及前序状态，确定长暂停的下一验证方向｜最近纯ED934 → FM诊断314｜−620／−66.38%｜非紧邻对照；沿用FJ首次绝对睡眠／计数诊断，增加临时RMM采集并重启固件，Host／Proxy／原DX／GPU实际594MHz／CPU自动频率／单vCPU保持；仅归因组合诊断效果，不当作提速｜下列run-id、命令、退出码与日志｜诊断总是撤下，已恢复DA／ED；1000门槛未过，无新增保留优化。

**采集与完整性。** 固定CPU2、三阶段摘要和六个最长≥10ms的`run_realm`区间；每区间44字段，共292字段。除timer寄存器外，扫描全部四个实际LR，分别记录IRQ27匹配槽、pending／active状态及EOI；增加ELR／VBAR／HCR／ICH_HCR、退出MISR／HPPIR及同次外层循环的前序handler状态。inactive条目绝不作为pending；重新进入外层循环只清前序valid，**无效条目的剩余载荷为旧值，全部排除，不据此连接两个外层调用**。冻结代次／锁及两次SMC读取、两次文件读取一致；越界和旧代次拒绝。临时只读接口不允许指定任意地址或修改状态，现已撤下。

本地实际采集／查询源码检查覆盖1105个LR组合、292字段查询／冻结和边界，解析器拒绝17种非法输入；timer131072转换／66有界退休、Client113模型和补丁清单退出0。固件、FIT及布局通过，`rmm_end=0x25ff000`、栈起点`0x259f000`和原预留不变。**本轮未重跑完整639套件，不继承FL的PASS为新检查。** 没有修改timer屏蔽、注入、权限、真实完成、deadline或回收决策。

| 实测 | 结果 | 可支持的判断 |
| --- | ---: | --- |
| 完整720p | 314，33场景 | 诊断版低于1000；validation仍26 PASS／1已知数值FAIL／6 SKIP |
| 最大timer架构入口晚到 | 15.842801秒 | 与该样本的`run_realm`＋PAuth重合99.999582% |
| 计数器桥接不确定度／漂移 | 约2.042µs／8ns | 支持该样本跨层区间核对 |
| timer检查最大区间 | 1.750µs | 不支持这次长尾主要花在timer检查函数中 |
| 退出handler最大区间 | 130.276ms | 不是同一大样本的连续执行证明 |
| 六个最长run区间 | 13.538–15.843秒 | 全部IRQ退出，退出PC均为`cpu_do_idle+0x8` |

**新的硬件边界证据。** 用与冻结FJ Client逐字节匹配的Image及其`vmlinux`／`System.map`核验；检查普通vectors、BHB和映射trampoline基址候选及2MiB重定位约束，本轮唯一匹配普通vectors、偏移0。反汇编显示`cpu_do_idle+0x4`为WFI、`+0x8`为RET，因此退出位置明确在WFI之后。入口PC分别落在IRQ处理／返回代码，但端点位置不能证明整个13–16秒持续空闲或持续关中断。

六区间入口／出口CNTV_CTL均为5（启用、到期、未屏蔽），CVAL及保存基线未变；**全部LR中均没有IRQ27匹配项**，不是把inactive当作未完成，亦不是沿用FL的事件LR127。退出MISR为0、HPPIR为1；Host保存的PPI27使能为1，实际退出处为0，后者仍是到期屏蔽的原设计，不是单独的缺陷证明。三个有效同循环前序handler均为sync／resume1、CTL5→5、CVAL不变，耗时0.583–3.208µs；本轮未观察到此前假设的“前序handler内未到期→到期且CVAL已换”模式。下一步应核对到期状态的报告／保存与Host虚拟中断交付，而非直接修EOI、改PPI使能或取消等待。

**实际源码的退出快照竞态反例。** 当前`rec_run_loop`先`report_timer_state_to_ns(rec_exit)`，随后`save_realm_state(rec, rec_exit)`；二者各自读取硬件timer。若timer在其间到期，Host报告可能为CTL1、REC保存基线为CTL5；下次进入时实际CTL5与保存基线5一致，RMM可能屏蔽物理timer而没有要求Host更新虚拟IRQ。FM的“已到期但无IRQ27 LR、随后停在WFI”与此相容，**但没有采集前一次实际Host报告，不能把该竞态认定为这六段的已证实根因**。

隔离检查抽取当前实际report函数和save的timer寄存器块，以3600个有限时序／使能／屏蔽组合重放，发现850个上述不一致组合；其中物理300、虚拟600，可重叠，**不是发生概率**。隔离候选在保存后从同一REC快照报告CTL／CVAL／offset，3600组合保持一致；ASan／UBSan退出0。v2新增按timer拆分时手算预期计数错误，断言失败，源码／二进制／日志保留；v3按实际report先虚拟后物理的读取顺序输出300／600／850，通过，原v1总数850不受影响。证据在`exit-snapshot-review/{review.json,review-v3.json,run-v2.log,run-v3.log}`。这只是有限模型反例，候选**尚未进入运行源码或部署**，没有新增性能测量。

下一步优先实现共同退出timer快照，验证物理／虚拟字段、offset和下一次实时检查的衔接；必须保留原版拒绝反例和实际源码检查，再用完整720p检验长尾及原ED对照性能。若未改善，不以模型PASS保留候选。不能顺带启用全部普通KVM timer路径、跨调用缓存硬件根或省略真实FINISH。

**命令、证据与恢复。** 目录`build/rmm-client-bo-20261030/timer-delivery-fm/`；完整命令／退出码／日志在`commands-index.json`，结论在`assessment.json`。

- `private-realm-phases-fw-20261102-fm`：独占lab wrapper加`--allow-rk-reboot`，执行`deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/timer-delivery-fm/firmware --run-id <同ID>`，退出0；只写SD2固件，Realm能力1。
- `private-heap-720-20261102-fm`：lab wrapper执行`python3 .../timer-delivery-fm/run.py measure`，退出1，仅因314低于1000；冻结`runtime-candidate`完整720p、单Client，VM0／0，两端解绑、内核健康／资源恢复、12份证据SHA及实际SD2核验通过。原始日志在`build/lab-runs/<ID>/`。
- `analyze-hardware-v2.py`／`analyze-overlap.py`／`symbolize-v1.py`／`review-boundary-v1.py`退出均0；独立符号／边界分析不修改冻结runner，自己的脚本哈希另存。
- `private-realm-phases-fw-restore-20261102-fm`：reboot wrapper执行`pre-restore.py`，保存读取模块后的dmesg并恢复DA固件，退出0；模块移除、boot健康通过。
- `private-realm-phases-restore-20261102-fm`：lab wrapper执行`restore.py`，退出0；原子恢复ED Client，四项Guest与实际DA SD2核验。最终CPU0–1／pmthor，无VM或loop残留。
- `finalize.py`退出0；270项冻结输入核验后恢复七项RMM源码，163项生产输入恢复原SHA，timer131072／66与Client113模型复测退出0；恢复后未新增GPU测量。

当前仍DA RMM＋ED Client＋原DX、纯对照934；1000、广泛API／ML／多Client、真实GPU完成eventfd及实体隔离未完成／NOT_RUN。AE VM_BIND EBUSY、历史Group submit fence超时与validation例外继续保留，整体goal仍active。文档仅整理本轮测量与离线反例，本身不产生性能收益。


## FN：共同保存的定时器退出快照与两组完整720p对照（2026-11-02）

统一记录：检查RMM退出报告和下一次进入所用timer基线的一致性｜原ED纯对照933 → FN固件＋原ED932｜−1分／−0.11%｜完整1280×720、33场景、null-noop／finish、GPU实际594MHz、CPU自动频率、各VM单vCPU、同Host／Proxy／Client／initrd／runner；先候选再恢复DA测对照，固件变更包含重启，只是一组对照，不证明稳定差异｜下述run-id、命令、退出码及日志｜未达预设944保留线，撤回并恢复DA／ED；1000及整体目标未完成。

**机制与新证据。** 原实现先实时读取timer寄存器报告Host，再保存REC；若到期恰好跨过两次读取，Host收到的输出状态和下一次进入比较的REC基线可能不同。FN先保存Realm状态，再从同一份REC快照生成退出报告，虚拟／物理timer的CTL、CVAL及offset对应保存字段；不改变PPI使能、EOI、虚拟IRQ、GPU完成判据或任务deadline。本地模型使用实际保存／报告／下一次进入代码，覆盖14400组合、4800进入边沿，拒绝五个编译错误变体；原实现编译成功但语义检查拒绝。原timer模型131072转换／66有界退休、完整私有套件633条PASS标记及固定构建／布局／FIT检查通过。模型不等于实体隔离证明。

先以同一冻结FJ睡眠诊断Client比较DA和FN固件，完整720p分别478→891（+413／+86.40%）；最大架构timer入口晚到15.659913秒→7.497169毫秒，≥10ms从19次→0次，满足上板前冻结的≤100ms且次数≤7的诊断门槛。两轮均无RMM临时采集器；这只支持快照一致性修改改善该诊断组合的长尾，未直接捕获此前实机Host／REC错配，不能将其称为ED全部性能差距的根因，也不能把诊断提分外推到生产版本。

因此补跑原始ED Client：FN固件932分，恢复DA后新对照933分，三个保护场景完全相同（blur152、terrain28、5×5 effect2d744），未达到预定`max(944, ceil(对照×1.01))`保留线。四轮均完整33场景、validation26成功／1既有数值例外／6无判据、VM0／0、内核健康、解绑和资源恢复通过；每轮11份证据文件SHA核验。外层退出1是低于1000门槛，不代表GPU工作负载退出失败，也不把validation例外写成全项正确性PASS。CPU SIGNAL/eventfd冒烟不等于真实GPU完成eventfd验收。

| 用途 | run-id | 外层退出码 | 日志 |
| --- | --- | --- | --- |
| 同FJ诊断Client／DA对照 | `private-heap-720-20261102-fn-control` | 1 | `build/rmm-client-bo-20261030/timer-snapshot-fn/control.log` |
| 同FJ诊断Client／FN候选 | `private-heap-720-20261102-fn` | 1 | 同目录`measure.log` |
| 原ED／FN固件 | `private-heap-720-20261102-fn-pure` | 1 | 同目录`pure.log` |
| 原ED／DA新对照 | `private-heap-720-20261102-fn-pure-control` | 1 | 同目录`purecontrol.log` |
| 最终四项Guest／实际SD2／启动健康核验 | `private-realm-phases-restore-20261102-fn` | 0 | 同目录`finalrestore.log` |

四轮都经`python3 scripts/maintenance/lab-run.py --run-id <上述ID> -- python3 build/rmm-client-bo-20261030/timer-snapshot-fn/<run.py或pure-run-v1.py> <control或measure>`执行；完整参数保存在各`*-command.json`，实际benchmark命令见对应`build/lab-runs/<ID>/benchmark-command.json`。部署与回退分别为`private-realm-phases-fw-20261102-fn`、`private-realm-phases-fw-restore-20261102-fn`，均以独占重启租约仅写SD2固件并退出0，未改Host内核或rootfs。

首次解析器、缺失fixture、未完整覆盖源文件的初次冻结，以及在wrapper结束前过早运行分析器的拒绝均保留；修正版通过后才部署／引用结果，不把准备失败计为有效语义反例。关键证据在`timer-snapshot-fn/{local-validation,assessment,pure-assessment,final-verification}.json`。结束时165项生产输入、270项冻结输入、17项纯对照输入、四项板端Guest与实际DA SD2核验；恢复后的timer131072／66和Client113通过。FN候选及新checker保留在隔离证据中，生产源码已撤回，构建缓存不能冒充ED。当前纯对照933，广泛API／ML／多Client、真实GPU完成eventfd和实体隔离未扩展；历史Group submit超时、AE VM_BIND EBUSY及validation例外继续保留。


## FO：一致timer快照基础上的全短等待协作（2026-11-02）

统一记录：让Client应用利用GPU查询之间的原有短等待区间｜紧邻DA／ED完整720p 933 → FN固件＋协作等待Client 855｜-78分／-8.36%｜完整1280×720、33场景、null-noop／finish、GPU实际594MHz、CPU自动频率、单vCPU、同Host／Proxy／initrd／原DX runner；RMM与Client组合变化且包含固件重启，只归因组合效果｜`private-heap-720-20261102-fo`，外层退出1，`build/rmm-client-bo-20261030/cooperative-wait-fo/measure.log`及对应lab-run目录｜未达预定944保留线，已撤回恢复DA／ED；1000与整体目标未完成。

**区别于旧AD／FF。** FN已经在同一睡眠诊断Client中将最大timer入口晚到15.660s降至7.497ms；本轮以此新证据检验过去睡眠试验缺失的一致退出快照前提。复用FN确切固件，不再调整timer使能、IRQ路由或编译参数。Client将原来首次最多200µs及后续八次各50µs的GPU等待改为绝对截止、零slack的hrtimer睡眠，早醒仅主动等待剩余区间；保留每次真实FINISH／heap检查、原deadline、CPU游标即时续传及原延迟回退。睡眠返回不能证明完成；关闭和超时继续按原路径保留／回收任务。

**验证。** 补丁清单、timer131072转换／66有界退休、实际快照模型14400组合／4800边沿及五个错误变体拒绝通过；Client ASan／UBSan模型122场景，包括重复早／晚醒、第三次重试关闭／过期、依赖和真实完成后发布fence等。ARM64构建退出0。此前诊断公共头文件恢复导致大范围重编译，故又独立构建未优化版：18415616字节可执行前缀与已测ED逐字节相同，镜像105字节差异仅版本／时间字符串和GNU build-id。候选冻结输入没有被普通重建覆盖；构建缓存不能作为本轮候选或冻结ED的替代。

实机完整33场景、validation26成功／1既有数值例外／6无判据、VM0／0、计算预热及CPU SIGNAL/eventfd/basic冒烟、解绑、两端内核日志、Host健康和资源恢复通过；11份证据SHA核验。外层退出1仅因低于1000，GPU负载本身退出0；不称全部图像validation通过。关键保护场景为[effect2d] 744→737；[desktop] 152→170；[terrain] 28→29，保护判定True。

| 已验证的全会话统计 | DA／ED | FO | 含义 |
| --- | --- | --- | --- |
| FINISH查询／退休批 | 2.457 | 1.994 | 查询数量必须结合整机分数判断 |
| COMPLETE操作µs／退休批 | 199.202 | 200.140 | 含RMM、设备交互及调度，不是纯CPU时间 |
| COMPLETE间隔µs／退休批 | 265.817 | 322.847 | 可能与设备执行重叠，不能直接换算可节省时间 |
| 首查暂停µs／退休批 | 164.683 | 212.853 | 候选包含sleep，旧`active_pause=1`字段只沿用格式 |
| 后续短暂停µs／退休批 | 74.226 | 97.976 | 不能由此宣称CPU利用率改善百分比 |

本轮gouraud shading为1290→1124（−12.87%），use-vbo build为1410→1239（−12.13%），而blur为152→170（+11.84%）；这些是同配置场景分数差异，不是已定位到具体CPU／GPU阶段的因果证明。计数包含预热／validation，各轮退休分母不同；没有同钟逐场景归因或独立CPU利用率测量。结果不支持仅将所有短等待改为睡眠作为保留优化；后续不只更换等待常数或重试本组合，应先区分实时设备进展、查询成本和应用可重叠工作。

硬件命令为`python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261102-fo -- python3 build/rmm-client-bo-20261030/cooperative-wait-fo/run.py measure`，完整benchmark参数保存在对应`benchmark-command.json`。部署`private-cooperative-fw-20261102-fo`与回退`private-cooperative-fw-restore-20261102-fo`均为独占重启租约、仅SD2固件、退出0；最后`private-cooperative-restore-20261102-fo`核验／恢复原ED Client、四项Guest和实际DA SD2，退出0。所有保留规则来自部署前的`plan.json`；初次旧主动等待fixture断言失败、记录文件改名与冻结清单竞争造成的文件缺失拒绝均在`preparation-failures.json`保留，修正后才计入有效验证，未修改冻结清单来掩盖差异。

恢复后165项生产输入、221项冻结输入、四项板端Guest与实际SD2核验，timer131072／66和Client113复测通过。证据为`cooperative-wait-fo/{plan-frozen,hardware,assessment,wait-comparison,normal-rebuild-comparison,final-verification}.json`及各命令／退出码／日志。新运行未保留提速代码；当前仍DA＋ED＋原DX，最新纯对照933。ML／更多API／多Client未扩展，真实GPU完成eventfd、实体隔离及整体目标仍未完成；既有超时／EBUSY／validation例外保留。

## FP：完整完成观察分段与冻结快照（2026-11-02）

统一记录：定位当前完成路径的固定开销，避免继续盲调等待常数｜FN最新纯对照933 → FP诊断936｜+3分／+0.32%｜完整1280×720、33场景、null-noop／frame-end finish，单Client、每VM一个vCPU，Proxy CPU1／Client CPU2，GPU请求600MHz／实际594MHz、CPU自动策略；Client／Proxy／initrd／原DX runner及Host均未变化，仅临时RMM计数与冻结查询接口。对照非紧邻且重新部署重启，诊断分数不作提速归因｜`private-heap-720-20261102-fp`退出1；部署、快照读取、恢复和核验退出0，详见下方命令及本轮证据｜诊断一律撤下，保留DA＋ED＋原DX、纯对照仍933；1000门槛与整体目标未完成。

### 测到了什么

在实际`task_observe()`中按原语句顺序计时：入口、前置START、配置及输入发布、通知、ACK循环、队列证据、后置START、末尾分支；另包裹`read_control()`记录嵌套成本。计数位于原策略锁内，独立计数器不替换授权、完成或原超时时钟。去除诊断包装／语句后，整个固件核心原文（忽略空白）与本轮前基线一致，原`read_control`／`task_observe`函数逐字一致。

成功GROUP_DESTROY后，在同一策略锁内发布固定70字段快照；新的观察使旧快照失效，代次不匹配、未冻结及越界读取均拒绝。Host通过临时GPU_PM只读操作按字段读取两次，内核模块比对后导出文件，再读取文件两次校验。没有指针、任意地址或写操作；接口、计数与模块都不保留在生产运行中。读写共用原RMI／RSI策略锁，未向热路径增加新锁。

实机两次SMC扫描及两次文件读取一致，解析全部70字段，代次69、可信计数器24000000Hz、累计成功FINISH调用355317次。阶段表如下：

| 阶段 | 次数 | 每次µs | 每成功FINISH调用µs | 占完整观察累计时间 |
| --- | ---: | ---: | ---: | ---: |
| 完整观察 | 860412 | 46.537 | 112.691 | 100.00% |
| 入口与参数检查 | 860412 | 0.200 | 0.483 | 0.43% |
| 观察前START重验 | 860412 | 8.004 | 19.382 | 17.20% |
| STATUS配置／输入发布 | 860412 | 3.570 | 8.645 | 7.67% |
| 固定硬件通知 | 860412 | 2.940 | 7.119 | 6.32% |
| STATUS ACK循环 | 860412 | 20.426 | 49.463 | 43.89% |
| 全部队列证据读取 | 860412 | 3.767 | 9.121 | 8.09% |
| 观察后START重验 | 860411 | 6.929 | 16.778 | 14.89% |
| 末尾判定／完整停止分支 | 860411 | 0.434 | 1.050 | 0.93% |
| 控制页读取（嵌套） | 2583555 | 0.996 | 7.241 | 6.43% |

阶段1–8合计覆盖完整观察计时的99.42%；剩余主要是计数器读取和记录边界，不能当作未计设备工作。控制页行嵌套于上层阶段，**不能叠加**。所有数值含预热、validation、合法pending、设备交互及诊断扰动；不是纯CPU时间、计分帧的逐任务剖析或可直接节省的时间。SUCCESS表示这次观察合法，不等于GPU任务已经完成。本表只覆盖`task_observe()`：外层DRAIN的live eligibility、重复idle快照与flush、绕过本函数的suspend完成快速路径、CPU归还／退休等不在完整观察行内，不能将其冒充整个COMPLETE耗时。分母为RMM自身累计成功FINISH RPC调用，并非Client文件计数或评分帧数；没有混用其他运行分母。

### 优化优先级

在本次观察函数内，STATUS ACK循环为43.89%，前后START重验合计32.09%，嵌套控制页读取为6.43%。因此优先研究设备推进／状态请求的协作关系和有明确无回调边界的证明流；本表不支持把控制页映射、hash或拷贝作为当前首要优化对象，也不能据此省去根、配置、错误或完成检查。EC的分阶段STATUS、EO的朴素事件唤醒、CI／CU的提前pending提示和多轮等待常数已有撤回结果，不能只因为该比例较高就直接重做。

同轮Client独立累计统计为354985批：PREPARE138.085µs／批、COMPLETE200.200µs／批、观察间隔264.501µs／批，868435次COMPLETE调用。它们的覆盖和分母与RMM快照不同，不能相减得到“剩余CPU开销”。细表在`client-phases.json`和`priority.json`；本轮取得了成本证据，没有新保留优化。

### 验证与可复验输入

本地完整私有套件退出0、633条PASS标记（并非独立实体硬件用例）；实际固定后端的原始输出在禁用／启用独立计时后相同，覆盖10个阶段和成功／pending／错误路径、无符号时钟回绕；3个成功编译的错误计数变体被拒绝。实际快照helper的70字段、边界与旧代次检查通过；严格解析器1个有效／22个无效输入检查通过。23份编译flags只增加临时`GPU_OBSERVE_PROFILE`，保留O2 Debug／断言；固定补丁清单、ARM64构建、ELF/BSS布局及FIT校验通过。临时Host模块显式使用`LOCALVERSION=-opencca-pmthor-opp3`，加载前核对板端release和vermagic。

开发期两次夹具编译失败与模型查询实参数量错误保留于`development-failures.json`及原日志：临时RMI查询改为独立编译开关隔离、RSI hook加入规范缩进／大括号、修正新模型的五参数调用；没有删除或放宽原功能断言，失败版本未部署。

完整33场景、validation26成功／1既有数值例外／6无判据，GPU命令退出0、VM0／0；预热计算与既有basic／CPU SIGNAL-eventfd、pool-unbind、Host／Guest内核健康、频率与资源恢复检查通过，12份证据逐项SHA核验。CPU SIGNAL-eventfd不代表真实GPU完成eventfd已验收。1000未达，API／ML／多Client／实体攻击扩展矩阵NOT_RUN；历史Group submit超时、EBUSY及其他未验收项继续保留。

主要入口（准确argv／退出码见实验目录`*-command.json`／`*-exit.json`）：

```bash
python3 build/rmm-client-bo-20261030/completion-phases-fp/local.py
python3 build/rmm-client-bo-20261030/completion-phases-fp/check-models.py
python3 build/rmm-client-bo-20261030/completion-phases-fp/freeze.py
python3 scripts/maintenance/lab-run.py --run-id private-completion-phases-fw-20261102-fp --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/completion-phases-fp/firmware --run-id private-completion-phases-fw-20261102-fp
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261102-fp -- python3 build/rmm-client-bo-20261030/completion-phases-fp/run.py measure
python3 build/rmm-client-bo-20261030/completion-phases-fp/analyze.py
python3 scripts/maintenance/lab-run.py --run-id private-completion-phases-fw-restore-20261102-fp --allow-rk-reboot -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check --run-id private-completion-phases-fw-restore-20261102-fp
python3 scripts/maintenance/lab-run.py --run-id private-completion-phases-verify-restore-20261102-fp -- python3 build/rmm-client-bo-20261030/completion-phases-fp/verify-sd.py restored
python3 build/rmm-client-bo-20261030/completion-phases-fp/finalize.py
```

本轮证据：`build/rmm-client-bo-20261030/completion-phases-fp/{plan,local-validation,model-validation,profile,hardware,assessment,final-verification}.json`；测量全证据在`build/lab-runs/private-heap-720-20261102-fp/`，部署／恢复在`build/firmware-runs/<run-id>/`。撤下前205份冻结输入一致，恢复165份生产输入；实际SD2与DA一致、四项Guest与ED一致，Host CPU0–1／pmthor，无本run VM或loop。原timer131072转换／66有界退休和Client113模型在恢复后复测通过；恢复后没有新增GPU测量。纯文档入口和旧表的当前版本文字同步为933，未据此宣称提分。

## FQ：本地完成提示的准入反例与原版对照（2026-11-02）

统一记录：探索不经过RSI的本地完成提示，减少无效STATUS观察｜此前纯对照933 → 本轮原版934；候选NOT_RUN｜原版+1／+0.1072%，候选分差N/A｜同DA RMM、ED Client／Proxy、initrd、原DX runner及Host，完整1280×720、33场景、null-noop／finish、GPU实际594MHz、各VM单vCPU、Proxy CPU1／Client CPU2、CPU自动频率；原版复测未改运行代码，无新增优化性能测量｜下述命令／退出码／日志｜候选上板前否决，三项源码已恢复；1000及整体目标未完成。

候选为每个组建立Client可读的NC提示页，用嵌套CALL执行原始命令，再写入本地提示；Client最多跳过八次查询，仍以原FINISH证明完成、归还和退休。虽然模型覆盖了提示伪造、错误传播和页引用清理，复查发现它将暂存请求中的原始start／bytes替换为跳板范围，RMM不再在原暂存时机检查原始命令范围。保持原FINISH并不能弥补该准入变化。

补充`review-admission.py`直接连接实际RMM PT／task-hold核心及实际候选Client helper：原始GPU VA未映射时，`gpu_private_task_hold`拒绝；跳板建立后，改写的范围却被接纳。两种组先销毁／任务先销毁的生命周期次序均复现。该控制机反例证明准入检查边界变化，不证明跨Client实体访问或硬件攻击。初版检查脚本有字符串语法错误，保留`admission-review.log`；修正后的`admission-review-v2.log`退出0，含两条`FQ_ADMISSION_COUNTEREXAMPLE=CONFIRMED`。候选不部署，不能将早期局部模型PASS解释为安全或提速。

原版对照`private-heap-720-20261102-fq-control`由以下独占命令完成：

```bash
python3 scripts/maintenance/lab-run.py --run-id private-heap-720-20261102-fq-control -- python3 build/rmm-client-bo-20261030/local-progress-fq/run.py control
python3 build/rmm-client-bo-20261030/local-progress-fq/analyze.py control
```

前一命令退出1，仅因934低于1000；GPU工作负载和两端VM均退出0，33场景齐全，validation26成功／1既有数值例外／6无判据，计算预热与既有basic／CPU SIGNAL-eventfd冒烟通过。真实GPU完成eventfd仍未验收。两端解绑、内核日志、Host健康和资源恢复通过，11份独立回收证据SHA逐项核验；未上传新的Guest输入，前后四项Guest及实际DA SD2固件匹配。日志在`build/lab-runs/<run-id>/`，对照总结`local-progress-fq/hardware-control.json`。

三项Client源码从本轮前副本逐字节恢复；原193项冻结输入中三项用原候选副本核验，其余原位核验，165项生产输入全部恢复原SHA。恢复后`check-gpu-private-submit.py`和`check-gpu-private-heap.py`退出0，分别113／151个模型场景；allocator／RSI／CPU映射及并发仍为替身，不替代Linux并发或实体隔离验收。首次整理误期待153个heap场景而被证据断言拒绝，核对实际原版151后纠正，未修改产品或测试断言。

最终证据为`local-progress-fq/{hardware-control,source-restoration,final-verification}.json`。当前保留DA＋ED＋原DX，最新纯对照934；没有新增保留优化。下一步提示方案必须保留可信侧原始命令准入，不能只在可恶意的Client增加检查。ML／API／多Client仍NOT_RUN，既有Group submit超时、AE VM_BIND EBUSY及validation例外保留。

## FR：RMM O3编译候选，完整720p934→934，撤回（2026-11-02）

统一记录：检验提高RMM编译等级能否减少重复任务检查与状态观察成本｜紧邻原版FQ对照934 → FR候选934｜0分／0.00%｜运行源码、Debug、断言、ISA、ED Client／Proxy、Host、initrd及原DX runner相同，仅RMM C编译从O2改为O3，候选固件部署包含重启；同完整1280×720、33场景、null-noop／finish、单Client、各VM单vCPU、Proxy CPU1／Client CPU2、GPU实际594MHz、CPU自动频率｜下表命令／退出码／日志｜未达预设944保留线，已撤回恢复DA／ED，无新增保留提速，1000与整体目标未完成。

**候选依据及边界。** FP实测完整观察中的STATUS ACK等待和START检查占比较高，但这些墙钟包含设备交互，不能视为纯CPU时间。FR只检验编译器循环变换、内联等是否能改善当前执行路径；没有取消检查、修改轮询预算、睡眠／timer、共享协议或页表策略。与FB的Cortex-A55调优、DC的LTO不同，本轮不改目标微架构，不启用跨文件优化。23份实际编译参数在仅归一化构建目录及O3→O2后与DA相同，未启用NDEBUG、fast-math或新指令集。固定源码／子模块／U-Boot归档重建，未更新上游。

ARM64代码段283328→344768字节，增加61440字节／21.69%；BSS保持37730404字节，原最大预留／栈／对象容量不变，ELF/BSS交叠和FIT检查通过。代码体积变化不能作为提速证据。首次参数比较因绝对构建目录不同而被拒绝，随后只归一化该路径前缀重新核验；记录在`preparation-failures.json`，未放宽编译选项核对。

**结果。** 两轮均完整33场景、GPU命令退出0、VM退出0／0；候选外层退出1仅因低于1000。既有26成功／1数值例外／6无判据之外，额外比较了33个场景的名称和validation状态，逐项完全一致，避免仅凭汇总计数相同遗漏失败迁移。三个保护场景大卷积effect2d744→744、blur152→152、terrain28→28，均通过；全场景最差变化为buffer subdata46→45（−2.17%），最好为mipmap1399→1405（+0.43%），不支持稳定提速。两端解绑／内核日志、Host健康与资源恢复通过，11份独立回收证据SHA一致，四项Guest未重新上传，测试前后实际SD2均匹配候选固件。

| 全会话Client遥测 | 原版934 | FR934 |
| --- | ---: | ---: |
| PREPARE µs／退休批 | 137.843 | 136.388 |
| COMPLETE µs／退休批 | 198.609 | 198.238 |
| COMPLETE查询／退休批 | 2.4626 | 2.4657 |
| COMPLETE观察间隔 µs／退休批 | 265.867 | 266.680 |

退休批354417／354570；计数含预热和validation，墙钟含设备等待／抢占，不是纯CPU或可直接节省时间，不与FP异轮嵌套阶段相减。局部PREPARE下降没有形成总分提升，也不从本轮推断所有编译优化或所有负载均无效。详细数据为`optimization-o3-fr/{hardware-candidate,scenes-candidate,validation-scenes,completion-comparison,code-size-comparison}.json`。

**本地验证。** 私有套件退出0、633条PASS标记，实际平台后端退出0、4288条PASS标记；标记不是独立硬件用例数。保留ASan／UBSan和断言。`HOST_CC`默认O3，部分模型脚本有后置显式O2，不能统称全部模型均按O3；直接组合平台、firmware、PT核心的后端及timer实际使用O3，无后置O2。`check-opencca-timers.sh`退出0，131072状态转换／66有界退休；补丁manifest、固定构建／布局／FIT及资源检查通过。本轮没有用模型代替实体隔离证明。

| 操作 | run-id | 命令关键部分 | 退出码 |
| --- | --- | --- | ---: |
| 原版对照 | `private-heap-720-20261102-fq-control` | `local-progress-fq/run.py control` | 1（低于1000） |
| SD2部署 | `private-o3-fw-20261102-fr` | `deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/optimization-o3-fr/firmware` | 0 |
| 完整720p候选 | `private-heap-720-20261102-fr` | `optimization-o3-fr/run.py measure` | 1（低于1000） |
| SD2回退 | `private-o3-fw-restore-20261102-fr` | `deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check` | 0 |
| 实际固件／Guest／资源终检 | `private-o3-verify-20261102-fr` | `optimization-o3-fr/verify-final.py` | 0 |

硬件命令均从仓库根目录执行，由`python3 scripts/maintenance/lab-run.py --run-id <ID> [--allow-rk-reboot] -- python3 <上表脚本和参数>`独占运行；仅部署／回退带重启选项及同ID的`--run-id`。完整argv／环境选项／退出码见`optimization-o3-fr/commands-index.json`，本地构建记录见`build-commands.json`，硬件日志见`build/lab-runs/<ID>/`及固件记录`build/firmware-runs/<ID>/`，未刷Host内核、rootfs或eMMC。

**恢复与产物。** 165项生产输入和198项原冻结输入核验相同；补充控制脚本另行冻结，未修改正在执行的runner。四项板端Guest和实际SD2回读匹配DA／ED；最终CPU0–1、pmthor、无本run VM／loop。仅删除本轮两个Pi临时上传目录内的四个已核对大小／mtime／SHA的固件副本，控制机准确副本与失败证据保留，删除清单见`pi-snapshot-cleanup.json`。最终判定`final-verification.json`为`PASS_O3_WITHDRAWN_DA_ED_RESTORED`，恢复后没有新增GPU测量。

当前保留DA＋ED＋原DX，最新纯对照934；FR无新增保留优化。1000未达，不扩展ML／API／多Client；真实GPU完成eventfd、实体隔离及原Group submit超时／AE VM_BIND EBUSY继续保持既有边界。文档更新本身未改运行代码，无新增性能测量，本文分数均来自上述实际运行。

## FS：可信侧生成进度提示，完整720p934→936，撤回（2026-11-02）

统一记录：减少尚未完成任务的重复FINISH／设备状态查询｜原版FQ纯对照934 → FS候选936｜+2分／+0.2141%｜完整1280×720、33场景、null-noop／frame-end finish，单Client、每VM一个vCPU、Proxy CPU1／Client CPU2、GPU实际594MHz、CPU自动频率；Host、Proxy、initrd及原DX runner不变，RMM和Client同时变化且部署重启，只归因组合效果；对照并非本轮紧邻重测，单轮不能证明稳定收益｜下表run-id、命令、退出码及日志｜未达部署前944保留线，已撤回恢复DA＋ED＋原DX；当前纯对照仍934，1000及整体目标未完成。

**机制及准入边界。** 新增显式协商的TASK_STAGE_HINT能力及操作，原始commands的start／bytes不变。RMM先保留原始命令映射／引用检查，再检查提示页属于同Client、服务和上下文，真实PTE与物理backing一致、RW／XN／NC、CPU侧NC转换完成，且不属于control／resident／closing／pending／revoked状态。每个组使用独立提示BO，任务另持其引用；仅单成员任务启用，其他路径沿用原版。

受保护16指令wrapper前10条保持原样，原CALL、WAIT(all)和受保护SYNC_ADD64不变；在原错误屏障前加入对提示页的GPU写回，原ERROR_BARRIER移到index12，未增加结构体／BSS。Client最多跳过8次查询，随后强制原FINISH、OOM及deadline路径。提示不能signal fence、释放映射或证明真实完成。与FQ的区别是原始命令范围没有被Client跳板替换；可信侧负责生成提示并保留原准入。提示仍是可被Client修改的调度建议，不能视作可信完成记录。

**实机结果。** 提示setup返回0，实际任务358215、跳过查询2127971，机制确实启用。33场景逐项名称及validation状态与对照一致：26 Success／1既有Failure／6 Unknown；两VM和GPU命令退出0，GPU_SMOKE／PERFORMANCE_CASE通过。effect2d大卷积744→744、blur152→153、terrain28→28。内核健康、解绑、资源恢复及11份回收证据SHA核验通过；外层退出1仅因936低于1000。只上传变化的Client Image，Proxy等Guest输入未替换。

| 全会话累计指标 | 原版934 | FS936 |
| --- | ---: | ---: |
| 退休批 | 354417 | 359420 |
| FINISH查询／退休批 | 2.4626 | 1.1384 |
| COMPLETE调用µs／退休批 | 198.609 | 106.656 |
| COMPLETE观察间隔µs／退休批 | 265.867 | 339.845 |
| 主动暂停µs／退休批 | 238.827 | 322.711 |
| PREPARE调用µs／退休批 | 137.843 | 136.717 |
| 首次暂停µs／退休批 | 164.221 | 11.795 |
| 后续暂停µs／退休批 | 74.606 | 310.916 |

查询次数下降与后续暂停增加同时出现，端到端收益不足；不能把减少的查询墙钟直接计作收益。统计含预热、validation、设备交互及调度，各轮分母不同，不是纯CPU或计分帧逐任务剖析；该表不能证明全部增量来自固定等待过冲。后续需有新的设备推进时序依据，不只调整等待／提示常数。详见`trusted-progress-fs/{hardware-candidate,scenes-candidate,validation-scenes,completion-comparison}.json`。

**本地验证。** 完整私有套件退出0、633条PASS标记；固定后端退出0、4288条PASS标记，均非独立硬件用例数。新worker116、heap155及RSI13场景通过；实际firmware核心组合覆盖多轮生命周期、原始未映射命令拒绝、提示权限、冻结与清理。四个实际RMM错误变体均编译成功并被断言拒绝：绕过提示授权、替换原始命令范围、删除受保护同步、删除错误屏障。保留ASan／UBSan及断言；allocator、CPU映射与并发替身不能替代实体隔离或Linux并发验收。

ARM64 Client与固定RMM／U-Boot构建、补丁manifest、ELF/BSS布局、FIT通过；23份编译参数只归一化构建路径后与DA一致，仍为O2／Debug／断言。BSS保持37730404字节；text／data页对齐后大小未变，但新符号及rmm.img哈希已核对，候选确实编入。开发期ABI最大操作号断言、错误测试double、旧group夹具缺提示helper、首个范围变体unused参数编译失败均保留。初始自动修改误删普通allocator允许掩码的EXEC，在源码diff检查时发现，部署前恢复并重新构建最终Client；错误Image未上板。

| 操作 | run-id | 命令关键部分 | 退出码 |
| --- | --- | --- | ---: |
| 原版对照（已有本轮前证据） | `private-heap-720-20261102-fq-control` | `local-progress-fq/run.py control` | 1（低于1000） |
| SD2候选部署 | `private-hint-fw-20261102-fs` | `trusted-progress-fs/deploy.py` | 0 |
| 完整720p候选 | `private-heap-720-20261102-fs` | `trusted-progress-fs/run.py measure` | 1（低于1000） |
| SD2回退 | `private-hint-fw-restore-20261102-fs` | `deploy-rmm-firmware.py --firmware build/rmm-client-bo-20261030/firmware-private-running-check` | 0 |
| 首次恢复终检 | `private-hint-verify-20261102-fs` | `trusted-progress-fs/verify-final.py` | 1（远程Python缩进错误） |
| 修正后实际固件／Guest终检 | `private-hint-verify-v3-20261102-fs` | `trusted-progress-fs/verify-final-v3.py` | 0 |

准确argv以`trusted-progress-fs/commands-index.json`及各`*-command.json`为准。所有硬件操作均由`python3 scripts/maintenance/lab-run.py --run-id <ID> [--allow-rk-reboot] -- <命令>`独占执行；仅部署／回退使用允许重启模式。日志在`build/lab-runs/<ID>/`、`build/firmware-runs/<ID>/`及本轮`*.log`，未刷Host、rootfs或eMMC。初版终检的远程脚本编译即失败，未完成Client上传；v2本地语法检查失败、未执行。v3独立重写并检查本地／远程语法后执行，失败脚本和日志全部保留。

**恢复与保留。** 15项源码／测试逐字恢复，166项生产输入与原SHA一致；201项候选冻结输入对修改项使用候选源码副本核验，其余原位核验，没有把恢复后的原源码冒充候选。恢复后Client113、heap151／RSI13模型通过。最后实际SD2字节匹配DA，板端四Guest匹配ED／原DX，CPU0–1／pmthor，无遗留VM或loop。仅删除本轮两个Pi临时上传目录内四个经大小／mtime／SHA／占用核查的固件副本，控制机候选、回退及全部失败证据保留。Guest增量编译缓存中的Image仍为候选；复测原版必须使用冻结ED包。最终判定为`trusted-progress-fs/final-verification.json`的`PASS_HINT_WITHDRAWN_DA_ED_RESTORED`。

未保留新增提速代码，恢复后没有新增GPU测量。1000未达，ML／更多API／多Client为NOT_RUN；真实GPU完成eventfd、实体隔离、原Group submit超时／AE VM_BIND EBUSY及既有validation例外继续保留。文档整理本身未改运行代码，无新增性能测量。

## FT：提示到达时提前结束有界等待，两轮958／956保留（2026-11-02）

统一记录：将FS已有GPU进度提示用于等待中的提前返回，减少等待粒度带来的完成可见延迟｜原版DA／ED对照934 → FT958／956，均值957；上一轮FS936｜+24／+22分（+2.57%／+2.36%），均值+23分／+2.46%；相对FS为+22／+20分｜同完整1280×720、33场景、null-noop／frame-end finish、单Client、每VM一个vCPU、Proxy CPU1／Client CPU2、GPU实际594MHz、CPU自动频率。FT使用与FS逐字节相同的RMM固件，Proxy／initrd／原DX runner／Host不变；相对DA／ED是RMM与Client组合变化，不拆分归因。对照不是本轮紧邻重测，候选首次部署重启、复测同一Host启动不重刷，两个样本不能证明一般负载或统计显著收益｜下表命令／退出码／日志｜两轮均超过预设944保留线及三个场景保护线，保留FS RMM＋FT Client＋原DX；1000及整体目标仍未完成。

**从证据到改动。** FS将查询／退休批从2.463降至1.138，但后续主动暂停从74.606增至310.916µs，整轮只934→936。代码核对发现，FS只在worker入口检查提示，进入短等待后仍等满该次时间。因此FT不修改等待常数：在已有最多200µs的首查预测等待、50µs的后续短等待中观察已建立的NC提示；一旦提示不再pending，提前结束该次等待，然后重新进入worker的原始FINISH／错误／OOM路径。该改动检验等待粒度影响，并不先验认定FS全部等待增量均由过冲造成。

Client新增`realm_gpu_task_has_hint()`区分没有提示页与提示已经到达。没有提示的任务仍按原等待执行；提示可被Client伪造，只能改变查询时机，不能完成fence或释放映射。原8次提示跳过、8次真实pending快速重试、绝对deadline、原始命令准入及受保护完成序列不变。实际改变位置为`panthor_client_drv.c`的短等待段；`realm_gpu.c`只新增提示可用性查询，RMM源文件及二进制均与FS一致，没有新的固件构建或编译参数变化。

**等待期间的生命周期。** 指针在`private_gpu_lock`内取出；当前work item独占任务操作与put，`postclose`先设置closing，再`cancel_delayed_work_sync()`，排空后才执行run_finish和组销毁。任务另持BO引用，使提示页在释放该锁的等待期间仍有效；reaper只释放abandoned任务，当前worker尚未put的任务不属于此集合。复查run_finish只有worker及同步排空后的stop两类调用者。源码审查和关闭／错误模型支持这个所有权边界，不代替真实Linux并发压力验收。

**两轮结果。** 两轮33场景名称及validation状态均逐项匹配原版：26 Success／1既有Failure／6 Unknown；三个保护场景均为effect2d745、blur158、terrain29（原版744／152／28）。GPU命令、两端VM均退出0，GPU_SMOKE／PERFORMANCE_CASE、解绑、内核健康与资源恢复通过。每轮11份回收证据逐项SHA一致。外层退出1仅因958／956仍低于1000，不表示扩展性能门槛通过。

| 累计遥测，按各轮退休批归一化 | 原版934 | FS936 | FT958 | FT复测956 |
| --- | ---: | ---: | ---: | ---: |
| 退休批 | 354417 | 359420 | 367734 | 367091 |
| FINISH查询／批 | 2.4626 | 1.1384 | 1.1400 | 1.1411 |
| COMPLETE调用µs／批 | 198.609 | 106.656 | 113.933 | 114.093 |
| COMPLETE观察间隔µs／批 | 265.867 | 339.845 | 314.424 | 312.823 |
| 主动暂停µs／批 | 238.827 | 322.711 | 294.433 | 293.663 |
| PREPARE调用µs／批 | 137.843 | 136.717 | 137.165 | 137.925 |

FT两轮等待观察2290556／2280658次，提前结束341214／339897次，约14.9%；读取提示273716135／273366533次。读取本身有CPU与NC内存代价，不能将读次数视作收益。相对FS，暂停和观察间隔下降，查询数量接近，但真实COMPLETE调用墙钟略增加；局部变化不可简单相加。所有统计含预热、validation、设备交互和调度，各轮退休批不同，不是纯CPU或计分帧逐任务剖析。结果支持保留该组合继续优化，不支持宣称已经达到1000或解决所有完成路径瓶颈。详细数据见`comparison-two-runs.json`。

**本地验证。** ARM64 Client构建退出0；130个实际planner／worker模型场景通过，覆盖无提示、到达前／等待中到达、永不到达、伪造提示、FINISH错误、OOM错误、deadline、关闭时任务与页面存活、依赖与退休语义。三个实际worker错误变体均编译成功后被断言拒绝：等待中忽略提示、不启用提示观察、凭提示绕过FINISH。完整私有套件退出0、633条PASS标记，标记不是独立实体硬件用例数；保留ASan／UBSan及断言。FS原样固件的布局／FIT、固定补丁manifest和资源检查通过；RMM准入／提示授权／wrapper正确性沿用原样FS二进制及其已有实测证据，本轮没有冒充重新构建RMM或重跑独立4288后端套件。

| 操作 | run-id | 命令关键部分 | 退出码 |
| --- | --- | --- | ---: |
| SD2部署原样FS固件 | `private-hint-fw-20261102-ft` | `hint-wait-ft/deploy.py` | 0 |
| 第一轮完整720p | `private-heap-720-20261102-ft` | `hint-wait-ft/run.py measure` | 1（958低于1000） |
| 相同输入完整复测 | `private-heap-720-20261102-ft-repeat` | `hint-wait-ft/repeat-run.py measure` | 1（956低于1000） |
| 保留输入／资源终检 | `private-hint-retained-verify-20261102-ft` | `hint-wait-ft/verify-retained.py` | 0 |

硬件命令均通过`python3 scripts/maintenance/lab-run.py --run-id <ID> [--allow-rk-reboot] -- python3 build/rmm-client-bo-20261030/<上表命令>`独占运行，仅固件部署允许重启。准确argv／退出码见`commands-index.json`；完整日志在`build/lab-runs/<ID>/`、部署记录`build/firmware-runs/private-hint-fw-20261102-ft/`及实验目录`*.log`。第一轮只上传Client Image，第二轮无新增上传；未改正在执行的runner，复测使用独立控制脚本并追加哈希记录，没有放宽原冻结输入核验。未刷Host内核、rootfs或eMMC。

**当前保留与后续边界。** 候选包含15项相对原DA／ED的源码／测试差异，均保存原版、候选副本和独立patch；其中FT相对FS只改Client实现、声明和相关模型提取／夹具，共5项。193项原冻结输入核验一致，补充控制脚本单独登记；最后实际SD2及四项Guest与候选匹配，CPU0–1／pmthor、无遗留VM或loop。保留包为`build/rmm-client-bo-20261030/hint-wait-ft/runtime-candidate/`，固件为`hint-wait-ft/firmware/`，旧`worker-priority-ed/candidate/`和`firmware-private-running-check/`作为DA／ED回退保留。本轮保留而非回退，未执行DA恢复。Pi只删除本轮部署目录内两个经SHA／大小／mtime／占用核对的临时固件副本，控制机准确副本及全部原始证据保留。最终判定`final-verification.json`为`PASS_HINT_WAIT_RETAINED`；终检后没有新增GPU测量。

1000未达，ML／更多API／多Client、实体隔离与真实GPU完成eventfd扩展验收为NOT_RUN或沿用既有未完成状态；原Group submit超时／AE VM_BIND EBUSY及validation例外保留。整体实现目标仍未完成。文档整理本身未改运行代码，无新增性能测量。


## FU：稳定租约元数据摘要与FT提示观察组合（2026-11-02）

**改动目的｜同期FS／FT对照957 → FU971／971（均值971）｜+14分／+1.46%｜保留。** 在FT提示感知的完成观察机制上，复用稳定租约内已经通过的BO元数据检查，减少重复集合扫描。两轮均超过预设`max(967, ceil(对照×1.01))=967`保留线。相同完整33场景、720p、null-noop／finish、GPU请求600／实际594MHz、单Client／每VM一vCPU；Client、Proxy、initrd和DX runner逐字节相同，没有新上传Guest。CPU仍自动频率，候选首轮在固件重启后运行，复测未重启；没有同期Native，不能将两次结果视作跨负载或统计显著证明。**1000未达，扩展矩阵未运行。**

**机制与边界。** 在`gpu_private_task_live_eligible()`完整BO集合检查成功后，保存可信元数据代次和是否需要NC屏障的结果；同代次只复用这些谓词。context／service／owner／task、映射代次、生命周期、槽位及回调能力仍每次新鲜检查；硬件根、配置、故障、真实完成、CPU归还、租约取得／归还扫描均不缓存。35处写入前失效，租约取得仅值实际变化时失效，共36处受审计写边界；溢出为0后永久禁用复用。四集合增加32字节、全局代次8字节，BO／PT容量和原预留不变；ELF布局和FIT通过，23份编译参数与FS一致，保持O2／Debug／断言。仅RMM运行源码改变，新增相应测试和测试入口。

EY旧候选在原ED上曾931→944、未达946而撤回。本轮具有FT改变查询与等待协作的新运行组合，不降低旧门槛；重新审计并验证FS提示页路径。20个实际核心暖摘要场景、7个编译成功的错误变体拒绝通过；新增场景包含已纳入租约集合的真实提示BO、错误端点和实际PTE篡改，确认提示验证不复用摘要。源变换反向还原后与FT核心逐字节一致，保留FS代码。完整私有套件退出0、634条PASS标记（非独立硬件用例数），原cache-set差分／错误变体及实际平台／核心／RSI检查通过；不冒称新增实体GPC、Linux并发或完整4288后端专项验收。详见`local-verification.json`。

| 累计遥测，按各轮退休批归一化 | FT对照957 | FU971 | FU复测971 |
| --- | ---: | ---: | ---: |
| 退休批 | 367423 | 374100 | 373694 |
| FINISH查询／批 | 1.1417 | 1.1406 | 1.1400 |
| PREPARE调用µs／批 | 137.305 | 132.134 | 131.704 |
| COMPLETE调用µs／批 | 114.078 | 108.181 | 108.594 |
| COMPLETE观察间隔µs／批 | 312.625 | 313.923 | 316.619 |

准备与真实查询调用墙钟下降，但观察间隔没有下降；统计包含预热、validation、设备等待和调度，不能相加当作纯CPU收益。首轮28场景提高／3持平／2下降，复测29提高／3持平／1下降；折射`refract`为86→82／79 FPS（−4.65%／−8.14%），该回退保留观察，不能声称所有场景提速。三项原定保护场景：effect2d745→756／756，blur157→161／162，terrain29→32／32，均通过。

三轮场景名称与validation逐项一致：26 Success／1既有Failure／6 Unknown；GPU命令和两端VM均退出0，预热计算／基础同步探针、解绑、内核健康及资源恢复通过，每轮11份回收证据SHA一致。三轮外层均退出1，原因仅为分数低于1000，不能写成性能门槛PASS。重复分析曾在证据尚未传回时得到FileNotFoundError，保存`premature-repeat-analysis.json`为NOT_READY；等待外层结束后用原分析器重跑通过，没有修改判据。

| 操作 | run-id | 实验目录内命令 | 退出码 |
| --- | --- | --- | ---: |
| 同期FT完整720p | `private-heap-720-20261102-fu-control` | `run.py control` | 1（957<1000） |
| SD2候选部署 | `private-summary-fw-20261102-fu` | `deploy.py candidate` | 0 |
| FU完整720p | `private-heap-720-20261102-fu` | `run.py measure` | 1（971<1000） |
| 相同输入复测 | `private-heap-720-20261102-fu-repeat` | `repeat-run.py measure` | 1（971<1000） |
| 保留与资源终检 | `private-summary-final-verify-20261102-fu` | `verify-final.py candidate` | 0 |

上述命令均通过`python3 scripts/maintenance/lab-run.py --run-id <ID> [--allow-rk-reboot] -- python3 build/rmm-client-bo-20261030/lease-summary-fu/<命令>`独占执行，仅部署允许重启。准确argv、退出码和日志见`commands-index.json`；原始证据位于`build/lab-runs/<ID>/`，固件记录位于`build/firmware-runs/private-summary-fw-20261102-fu/`。本轮没有改Host内核、rootfs、eMMC或正在运行的runner。

**当前保留：FU RMM＋FT Client＋原DX。** 包为`build/rmm-client-bo-20261030/lease-summary-fu/runtime-candidate/`，固件为同目录`firmware/`；FT的包和固件完整保留回退，未执行回退。219项冻结输入、补充控制输入、四项源码副本、实际SD2／四Guest终检通过，CPU0–1／pmthor且无遗留VM或loop。Pi仅删除本轮两个经SHA／大小／mtime／占用核对的临时固件上传，准确控制机副本及全部失败／未执行记录保留。最终状态见`final-verification.json`；终检后无新增GPU测量。

下一步优先定位仍占主导的完成观察间隔及`refract`延迟重排／推进时序，避免仅重复等待常数或约6µs立即重排优化。1000尚差29分；ML／完整API／多Client、实体隔离、真实GPU完成eventfd扩展为NOT_RUN或原有未完成状态。历史Group submit超时、AE EBUSY和validation例外仍保留，整体实现目标不标完成。


## FV：提示未到达反馈训练首查预测（2026-11-02）

**改动目的｜同期FU对照972 → FV974｜+2分／+0.21%｜未达982保留线，撤回并恢复FU。** 延续用户先优化性能的优先级，研究FT提示观察使原预测器缺少样本的问题：原版只记录真实FINISH的pending，很多任务先通过提示等待、首次FINISH即成功，随后按零样本训练。FV为单任务记录`last_hint_pending_ns`，仅在真实FINISH最终成功后，以提示／真实pending中较大的观察时间训练本队列首查预测；无样本继续衰减。不把提示当完成证明；原200µs上限、八次提示跳过、八次真实pending快速重试、50µs等待、deadline、OOM／错误与生命周期检查均不变。仅Client驱动及实际worker夹具改变，RMM、Proxy、DX runner、initrd、Host和rootfs原样；不重建／刷写固件，无Pi上传。

与DZ按pending调用成本增加首查等待不同，本轮没有增加等待常数，而是使用FS／FT新增提示观察产生的既有样本。源变换反向还原后与FU驱动逐字节一致；238项候选输入冻结。136个实际planner／worker模型通过，新增覆盖提示先等待、首次真实FINISH成功时训练，跨任务收敛／队列独立、永不到达／伪造提示、错误／heap失败／deadline和异常时间钳制。三个编译成功的错误变体被断言拒绝：忽略提示反馈、移除目标上限、凭提示绕过FINISH。ARM64 Client构建退出0；完整私有套件退出0、634条PASS标记（非实体用例数）。模型使用内核／GPU替身，不作Linux并发或物理GPC证明。

| 累计遥测，按退休批归一化 | FU972 | FV974 |
| --- | ---: | ---: |
| 退休批 | 374087 | 376220 |
| 提示跳过／批 | 5.9230 | 2.7227 |
| 有首次预测等待的批占比 | 16.77% | 99.99% |
| FINISH查询／批 | 1.1398 | 1.1182 |
| PREPARE调用µs／批 | 131.316 | 131.146 |
| COMPLETE调用µs／批 | 108.409 | 107.243 |
| COMPLETE观察间隔µs／批 | 315.617 | 314.621 |
| 主动暂停µs／批 | 293.803 | 300.226 |
| 立即排队µs／批 | 5.962 | 3.704 |
| 延迟排队µs／批 | 13.070 | 9.005 |

反馈机制确实生效，提示跳过及排队开销下降，但主动暂停增加，完整计分只增加0.21%。局部指标包含预热、validation、调度和设备等待，不是纯CPU或可直接相加的节省量。**当前数据不支持仅调整提示预测器就取得足够端到端收益；后续不只换反馈权重、等待常数或跳过上限重试。** 原立即排队占比很小，本轮进一步量化了减少切换的实际收益上限；后续候选需有不同执行／应用／完成观察协作及相应实证。

两轮完整33场景及逐项validation与对照一致：26 Success／1既有Failure／6 Unknown；GPU命令0、两端VM0/0，三项保护场景均为effect2d756／blur161／terrain32，健康／解绑／资源恢复通过，各11份回收证据SHA一致。两轮外层均退出1，仅因<1000；不能称扩展性能门槛PASS。相同720p、null-noop／finish、GPU请求600／实际594MHz、单Client／每VM一vCPU，CPU自动频率；只有候选首次上传Client Image，无固件重启或其他载荷变化，没有同期Native。候选复测为NOT_RUN：首轮已不满足预先`max(981, ceil(对照×1.01))=982`保留条件，不用重复试验或降低门槛保留。

| 操作 | run-id | 实验目录内命令 | 退出码 |
| --- | --- | --- | ---: |
| FU同期完整720p | `private-heap-720-20261102-fv-control` | `run.py control` | 1（972<1000） |
| FV完整720p | `private-heap-720-20261102-fv` | `run.py measure` | 1（974<1000） |
| 恢复FU Client Image | `private-hint-feedback-restore-20261102-fv` | `restore.py` | 0 |
| 源码／SD2／Guest／资源终检 | `private-hint-feedback-final-verify-20261102-fv` | `verify-final.py baseline` | 0 |

硬件均通过`python3 scripts/maintenance/lab-run.py --run-id <ID> -- python3 build/rmm-client-bo-20261030/hint-feedback-fv/<命令>`独占执行，不允许重启。准确argv／退出码／日志见`commands-index.json`，本地构建和模型见`local-verification.json`；原始证据位于`build/lab-runs/<ID>/`。两项源码均从逐字节保存的FU原版恢复，新夹具分支随候选撤回；恢复后的130场景实际worker模型退出0，没有留下无人调用的实现。219项FU冻结输入、实际FU SD2及四Guest核验通过，CPU0–1／pmthor且无遗留VM或loop。候选、patch、模型、构建和全部测量／撤回证据留在实验目录；Guest增量构建缓存为FV产物，不是当前运行输入，下一次使用前必须按已恢复源码重建。

当前仍保留`lease-summary-fu/runtime-candidate/`与`lease-summary-fu/firmware/`，此前独立971／971、新纯对照972；不能把974记为当前保留性能，也不能把未改代码的1分波动记作新提速。最终状态`final-verification.json`为`PASS_FV_WITHDRAWN_FU_RESTORED`；终检后无新增GPU测量。1000、ML／完整API／多Client及整体目标仍未完成，既有Group fence超时、AE EBUSY、validation例外和物理边界保留。


## FW：FU 当前路径分段成本与冻结快照（2026-11-02）

统一记录：为下一项结构性性能优化建立当前成本依据｜近期未修改FU对照972 → 临时诊断969｜−3分／−0.31%｜同一完整720p／33场景、GPU实际594MHz、CPU自动；FU＋FT Client／Proxy／initrd／原DX不变，只在RMM增加计时；对照非紧邻且本轮重启固件，不能据此建立性能因果｜下表run-id、命令、退出码与日志｜仅诊断，已撤下并恢复FU；没有新增保留提速，1000及整体目标未完成。

**为什么做本轮。** FV减少提示跳过和worker排队只得到972→974，未达保留线；旧FP来自DA／ED，不能作为当前FU的精确成本。本轮复用FP的完整完成观察分段，并增加保留域准备、空闲重验、控制页写、DRAIN、DISPATCH、READY、PUBLISH、START、空闲快照和FINISH的包含子调用计时。没有修改原始准入、授权、真实根／故障／完成／回收、等待上限或timeout时钟。未修改Client、Proxy、Host或runner，不开展仅改32批保留上限的候选。

**可信取回。** 共20项计数、130个标量；策略锁内冻结计数视图与80字节头，任何新计数写使视图失效。临时Host模块两遍SMC取回、两遍proc文件读取一致，边界／旧代次拒绝通过；最终generation69、24MHz、RMM累计退休373773批。Client文件统计373441批，相差332来自累计范围，不能混用分母。模块取回后已卸载，计时与查询代码最终从运行源码撤回。

| 当前FU诊断阶段 | 调用／RMM退休批 | µs／调用 | µs／RMM退休批 |
| --- | ---: | ---: | ---: |
| DISPATCH整体 | 1.0000 | 82.698 | 82.698 |
| 保留域准备，包含下面的空闲重验 | 0.9680 | 36.018 | 34.864 |
| 空闲anchor重验，含真实START与队列读取 | 1.9359 | 16.642 | 32.218 |
| READY，含缓存交接与配置 | 1.0004 | 11.513 | 11.517 |
| PUBLISH | 1.0000 | 25.968 | 25.968 |
| FINISH整体，包含DRAIN／观察／归还等 | 1.1412 | 88.463 | 100.955 |
| DRAIN整体 | 1.1061 | 84.102 | 93.028 |
| 完整完成观察 | 1.1112 | 52.621 | 58.471 |
| 其中STATUS ACK等待 | 1.1112 | 26.836 | 29.819 |
| 其中控制页读取，嵌套于观察 | 3.3344 | 1.076 | 3.587 |
| 全部START首次／重放，嵌套于多个父阶段 | 11.1405 | 6.628 | 73.835 |
| 全部空闲快照，嵌套于准备和DRAIN | 3.8740 | 3.161 | 12.245 |
| 全部控制页写，嵌套于准备等 | 2.0320 | 0.881 | 1.790 |

这些是含设备等待、预热／validation和计时扰动的累计墙钟；包含子调用的行互相重叠，不能相加为CPU成本或可删除开销。START同时包含真实启动与只读重查，6.628µs不是每次首次启动成本。观察内8段占该观察总墙钟99.416%；STATUS ACK占观察50.998%、占整个FINISH约29.537%，不能把观察内部的51%称为全部完成路径占比。

**排序结论。** 两次空闲重验合计占保留域准备的92.410%，写控制页远小于重验；优先研究保持回调边界检查的事务组织与提交／完成协作，实际优化尚未实现。相邻批次的排空证明、后继授权及准备能否在同一可信事务内组织，需先证明调用／锁／物理回调边界及错误保持条件，不能跨RSI缓存硬件证明。完成侧约29.819µs／批用于STATUS ACK；重做异步ACK必须解释EC增加查询和worker间隔的退化，不能仅将忙等搬到下一次调用。控制读取这次只量到观察内3.587µs／批，不是所有读取成本，也未拆分map／失效／copy；不足以把DB临时映射缓存再次列为首要优化。

Client原有遥测：PREPARE133.339µs／Client退休批、COMPLETE调用109.981µs、观察间隔313.085µs，其中主动暂停293.055µs、立即排队5.965µs、延迟排队11.170µs。主动暂停与GPU执行重叠，不是可全部消除的开销；不把与RMM计数的差值直接归因通信。场景日志缺少共同精确时钟，本轮未将累计窗口强配给refract。

**本地检查及边界。** 12个计时函数反向去除诊断后，原生产核心文本一致；实际平台／私有核心／固件后端在原版、关闭计时、独立17tick计时三个构建中的原有输出一致，覆盖时钟回绕和20项计数。原后端3607条PASS标记不是独立硬件用例。3个错误计数变体均成功编译并被断言拒绝，查询视图失效／旧代次／边界及解析器22个坏输入拒绝通过。保持23份编译参数、O2／Debug／断言／ISA，仅增加临时查询宏；固定RMM预留和BO／PT／栈容量不变，布局／FIT通过。本轮未另跑完整634条私有套件，使用上述实际完整后端、ARM64构建和硬件读取验证；ML／完整API／多Client及实体隔离扩展为NOT_RUN。

两次构建失败均在部署前：新增RSI计时块缩进告警，以及重复快照使BSS对齐后多4096字节越过固定链接上限。前者修正花括号／缩进，后者改为策略锁内冻结计数视图，未扩大预留或削减业务容量。初次日志、修正脚本和`development-failures.json`保留，不计通过或攻击拒绝。

**完整720p与恢复。** 33场景完成，逐项validation与FU纯对照一致（26 Success／1既有Failure／6 Unknown）；GPU命令退出0、VM0／0，预热计算／基础同步探针、两端解绑／kernel-log、Host健康和资源恢复通过；12份回收文件SHA核验。分数969低于1000，外层退出1，不能写成性能门槛通过。CPU保持原自动策略，559次全程采样有425次1.8GHz、131次1.008GHz、3次其他频率；包含启动阶段，最高采样53.615°C，不能据全程频率占比解释计分场景差异。

| 操作 | run-id | 实验目录内命令 | 退出码 |
| --- | --- | --- | ---: |
| SD2诊断固件部署 | `private-current-cost-fw-20261102-candidate` | `deploy.py candidate` | 0 |
| 完整720p＋冻结计数取回 | `private-heap-720-20261102-fw` | `run.py measure` | 1（969<1000） |
| 恢复FU固件 | `private-current-cost-fw-20261102-rollback` | `deploy.py rollback` | 0 |
| 源码／实际SD2／四Guest／资源终检 | `private-current-cost-final-verify-20261102-fw` | `verify-final.py` | 0 |

命令均为`python3 scripts/maintenance/lab-run.py --run-id <ID> [--allow-rk-reboot] -- python3 build/rmm-client-bo-20261030/current-cost-fw/<表中命令>`；仅两次固件部署允许重启，均只刷SD storage ID2，未刷Host内核、rootfs或eMMC。准确argv／退出码／日志见`commands-index.json`；测量证据在`build/lab-runs/<ID>/`，刷写备份／UART在`build/firmware-runs/<部署ID>/`。

**当前仍为FU RMM＋FT Client＋原DX，保留971／971，近期纯对照972。** 257项诊断冻结输入在部署／测试／回退前核验；四项临时生产源码恢复后219项FU基线输入全部匹配，实际FU SD2及四项Guest终检一致。CPU0–1／pmthor，无遗留VM／loop／诊断模块；两次Pi临时上传按精确路径、SHA、大小、mtime和占用核对后删除，控制机保留固件、源码、全部模型与失败证据。`final-verification.json`为`PASS_FW_DIAGNOSTIC_WITHDRAWN_FU_RESTORED`；恢复后无新增GPU测量。Guest增量构建缓存仍是此前已撤回FV的Image，下次使用须按现源码重建。1000门槛、既有Group fence超时／AE EBUSY／validation例外及整体目标仍未完成。

## FX：READY/RETURN 复用已持有租约摘要（2026-11-02）

**结果：972 → 980，+8分／+0.82%，未达预设982，已撤回恢复FU RMM＋FT Client＋原DX。** 1000门槛未过；原保留971／971，最新纯对照972。没有新增保留优化，不扩展ML／API／多Client。

- **改动目的：** FW指出当前READY约11.517µs／退休批；这是包含子调用的整段成本，不能全部视作BO扫描。原READY／RETURN仍对受保护BO集合做预检及租约获取两遍扫描。FX仅在FU已有live_epoch与非零全局元数据代次一致时，复用“本context已持有全部租约”的证明；不新增摘要状态或容量。未命中仍走原双遍扫描；映射／context／task／生命周期检查、NC真实屏障、硬件根／错误／完成验证保持。
- **比较条件：** 同一FT Client、Proxy、initrd、原DX、Host、单Client、默认池、完整720p与33场景；GPU实际594MHz，CPU schedutil自动频率。先测原FU，再仅替换RMM固件并重启；重启及自动频率是条件差异，单轮不证明一般负载稳定收益。
- **本地验证：** ASAN／UBSAN实际核心42组基线／候选差分，成功／错误与屏障输出一致；暖路径扫描2→0、冷路径2遍。覆盖live handoff、NC／resident、控制页、错误身份／task／pending／撤销、代次失效及永久零、barrier失败／回调内失效、RETURN；3个错误变体拒绝。完整私有回归rc0、640条PASS标记行（不是独立实体用例数），原live-summary失效审计与实际平台／核心／RSI检查通过。初版测试误用cold hold API的fixture失败保留，改用真实mark-drained／hold-live后通过，未改变候选运行代码。
- **构建：** 与FU的23份flags一致，O2／Debug／断言／ISA及固定子模块、固件来源、RMM预留与BO/PT容量保持；布局／FIT通过。没有重建或使用已撤回FV的Guest缓存。
- **硬件与恢复：** 两轮GPU workload退出0、VM0/0，逐场景validation完全一致（26成功、1既有失败、6Unknown），不能称所有场景正确。各11份证据SHA、内核健康、pool-unbind及资源恢复通过。外层均rc1仅因分数<1000。候选撤回后219项FU冻结输入、实际SD2／四Guest终检；246项候选冻结输入以封存源码验证；首次回退因源码已恢复而与候选冻结检查不符，在刷写前退出；更正为验证原版及封存候选后重试成功，失败run-id及rc1保留。本次Pi临时上传按准确路径／SHA／大小／mtime／占用核对后删除。未在终检后新增GPU测量。

| Client累计指标 | FU原版 | FX候选 | 变化 |
| --- | ---: | ---: | ---: |
| prepare_operation_us_per_retired | 131.523 | 124.962 | -4.99% |
| complete_operation_us_per_retired | 108.351 | 107.926 | -0.39% |
| complete_gap_us_per_retired | 315.245 | 315.390 | +0.05% |
| queries_per_retired | 1.140 | 1.139 | -0.06% |

上述单位为µs／Client退休批，queries_per_retired为次数／批；不同运行累计任务集合略有差异。墙钟含设备等待与调度，不能相加当纯CPU节省，不能将聚合变化强配给某场景。READY真实局部分段未另加诊断，42组模型的扫描减少不等于实机提分证明。

| 操作 | run-id | 外层退出码 | 日志 |
| --- | --- | ---: | --- |
| candidate | `private-heap-720-20261102-fx ` | 1 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/candidate.log` |
| control | `private-heap-720-20261102-fx-control ` | 1 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/control.log` |
| deploy | `private-ready-lease-fx-20261102 ` | 0 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/deploy.log` |
| final | `private-ready-lease-fx-final-20261102 ` | 0 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/final.log` |
| resources | `非硬件 ` | 0 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/resources.log` |
| rollback | `private-ready-lease-fx-20261102-rollback ` | 1 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/rollback.log` |
| rollbackretry | `private-ready-lease-fx-20261102-rollback-retry ` | 0 | `/home/mzh/gpu/build/rmm-client-bo-20261030/ready-lease-fx/rollbackretry.log` |

统一记录：减少稳定租约READY／RETURN重复扫描｜FU 972 → FX 980｜+8／+0.82%｜仅RMM＋固件重启，CPU自动频率｜命令与退出码见上表及`build/rmm-client-bo-20261030/ready-lease-fx/commands-index.json`｜**撤回**。候选与失败证据留在`build/rmm-client-bo-20261030/ready-lease-fx/`；生产源码未保留本轮改动。后续不只改摘要标志或重复微调扫描，优先研究提交／完成事务中可重组的物理往返，并保持回调两侧真实检查。
