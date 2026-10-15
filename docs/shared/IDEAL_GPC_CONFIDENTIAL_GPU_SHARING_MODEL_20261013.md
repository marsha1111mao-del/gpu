# Ideal-GPC 多 VM 机密 GPU 共享模型：论文假设、系统优化与创新点

整理日期：<mention-date start="2026-10-13"/>。

分析对象是 `/home/mzh/RK3588/gpu` 当前工作树。本文不重复上一篇文章的威胁模型清单，而是在一个更明确的研究目标上展开：

> **在显式假设条件下构建安全的共享 GPU 模型，并用当前 vmshm / Panthor proxy / OpenCCA 原型验证模型、优化路线和创新点。**

换言之，本文关心的不是“RK3588 当前是否已经安全”，而是：

1. CAGE 和 ACAI 分别把哪些能力当作前提；
2. 我们的模型可以设计哪些最小且可组合的假设；
3. 当前代码中哪些结构可以保留、哪些必须重构；
4. 相比论文路线，我们的场景能做哪些优化；
5. 这个设计有哪些可能的优势、创新点和实验价值。

<table_of_contents/>

## 核心结论

**建议把系统定义为一个分层假设模型：用 CAGE 的 trusted owner / shadow task 思想控制 GPU 生命周期；用 ACAI 的 identity / binding / translation / crypto invariant 定义设备赋值目标；用当前 per-session Panthor VM 和 vmshm object 层实现可实验的 GPUContext / Grant 原型；再用 ideal-GPC oracle 模拟最终硬件强制访问控制。**

推荐的安全根是：

```text
Trusted RMM / EL3 policy authority
  + ideal GPC for CPU/GPU/DMA access control
  + trusted GPU address-space root / ASID binding
  + per-Realm key context or explicit shared domain
  + explicit object grant / revoke lifecycle
  -> confidential GPU sharing model
```

当前 RK3588 代码不能直接承担这个安全声明：

| 当前结构 | 可复用的价值 | 需要升级的安全根 |
| --- | --- | --- |
| `vmshm-broker` | fd / memfd / eventfd 数据面和拓扑编排 | Host normal-world 进程不能作为 policy authority |
| shared `memfd` | 大 BO zero-copy 数据面 | whole-window mapping 必须变成 per-client domain 或 subrange grant |
| `proxy_vmshm_manager` | object handle、owner、generation、span 翻译 | permissions 和 revoke 目前不完整，需要进入可信 policy 层 |
| `panthor-proxy` session | GPUContext 雏形，隔离 API namespace | Proxy Linux 不能成为恶意 Host 下的 TCB |
| per-session native Panthor VM | GPU VA address-space 隔离雏形 | page-table root、ASID、queue state 必须由可信 owner 控制 |
| OpenCCA RMM GPA-to-HPA lease | 可信地址验证入口 | 当前是软件 bookkeeping，不是 GPU/DMA hardware enforcement |
| simulated GPT/GPC check | 模型层 denial 实验 | 不能替代真实硬件 GPC 证明 |

最重要的设计边界是：

> **假设 GPC 可以，但必须把 GPC 定义成 ideal security primitive，并让所有 CPU、GPU、DMA、MMIO、reset、page reuse 路径都经过它。不能只把 GPC 当成现有 Host broker 里的一个普通函数。**

## 1. 论文前提的重新拆解

### 1.1 CAGE 提供的可复用假设

CAGE: *Complementing Arm CCA with GPU Extensions*, NDSS 2024，DOI `10.14722/ndss.2024.24763`。

CAGE 的核心不是某个具体 driver API，而是把集成 GPU 纳入 Arm CCA 的安全状态机：

1. **trusted monitor 控制 GPU ownership**
   - GPU MMIO、page-table base、queue doorbell、firmware 状态不能由 normal world 随意修改；
   - Realm task 运行前建立受控 GPU 环境。
2. **shadow task**
   - 可信主体接管或重建 GPU task 所需状态；
   - 不信任 Host 提交的原始 task metadata。
3. **多 GPT/GPC 视图**
   - CPU、GPU、untrusted peripheral 看到不同授权；
   - GPU 不能成为绕过 CPU GPT 的 DMA oracle。
4. **生命周期控制**
   - submit、quiesce、invalidate、scrub、reclaim 顺序是安全的一部分。

CAGE 的隐含前提可以抽象为：

```text
CAGE-1: trusted monitor / secure software exists;
CAGE-2: GPC/GPT can enforce per-world or per-context memory access;
CAGE-3: GPU control state can be locked by trusted owner;
CAGE-4: in-flight work can be quiesced and invalidated;
CAGE-5: physical attacks are handled by CCA memory encryption or excluded;
CAGE-6: side-channel and DoS are out of scope.
```

对本项目的直接启发是：

- 单安全视图时，安全共享应该设计成 **owner-epoch serial execution**；
- GPUContext 的 page-table root、ASID、queue、doorbell 必须是受控状态；
- revoke 不是删除软件 handle，而是 stop → drain → invalidate → scrub → reuse 的完整生命周期。

### 1.2 ACAI 提供的可复用假设

ACAI: *Protecting Accelerator Execution with Arm Confidential Computing Architecture*, USENIX Security 2024 / arXiv:2305.15986。

ACAI 面向 PCIe accelerator，核心贡献是把设备赋值拆成稳定不变量：

1. **Identity**
   - accelerator / stream / device interface 有不可伪造身份；
   - remote attestation 后才能绑定 VM。
2. **Binding**
   - 一个安全设备接口同一时间只绑定一个 owner；
   - 绑定关系由可信 monitor 管理。
3. **Translation consistency**
   - device-side translation 与 Realm IPA-to-PA 映射一致；
   - 不能出现 CPU、SMMU、device 三套互相矛盾的映射。
4. **DMA deny**
   - 未授权 VM、Host、设备访问 protected region 必须失败。
5. **Crypto**
   - MEC/MPE 或 IDE 保护 DRAM / link；
   - per-Realm key 不应默认退化成全局同一把 key。
6. **Lifecycle**
   - attach、detach、TLB invalidation、page reuse 必须可验证。

ACAI 的隐含前提可以抽象为：

```text
ACAI-1: device has attestable identity;
ACAI-2: RME-DA / SMMU can enforce per-device assignment;
ACAI-3: accelerator can protect its internal execution state;
ACAI-4: MEC/MPE/IDE protects memory or link;
ACAI-5: one security endpoint maps to one owner at a time.
```

对本项目的直接启发是：

- Grant、GPUContext、endpoint、key context 都需要不可伪造 identity；
- 多 VM 并行必须以多个独立安全 endpoint 为前提；
- 共享页要有显式 shared domain，不能伪装成两个 Realm 的 exclusive private page。

### 1.3 论文假设与本场景的关系

| 能力 | CAGE | ACAI | 本项目可用方式 |
| --- | --- | --- | --- |
| 集成 GPU / 共享 DRAM | 强相关 | 非核心 | Mali-G610 场景，适合借鉴 CAGE |
| GPU GPT / GPC view | 核心假设 | 通过 SMMU/RME-DA 表达 | 用 ideal-GPC oracle 和模型检查模拟 |
| shadow task | 核心机制 | 不完全对应 | 改造成 RMM-managed GPUContext lifecycle |
| 设备 identity | 较弱 | 核心假设 | 先用 VMID/session/object generation 建模，长期映射 TDI/VF/StreamID |
| 设备 TEE / IDE | 可选或排除 | 核心假设 | 基线排除物理攻击，长期再引入 |
| per-Realm crypto | 依赖 CCA/MEC | 明确要求 | 基线显式排除物理攻击，或引入 shared authenticated crypto |
| 多 VM 并行 | 单安全视图受限 | 多 endpoint 时可行 | 先串行 owner-epoch，再扩展 per-endpoint view |

因此，本文不采用“二选一”：

```text
CAGE = 集成 GPU 的生命周期与安全视图模型
ACAI = 设备赋值的安全不变量与长期硬件接口模型
当前代码 = 可实验的 API、object、GPU address-space 原型
```

## 2. 设计 A0–A4 假设阶梯

建议把假设分成五个层级，避免把“功能性共享”“模拟安全”“真实机密计算”混在一个声明里。

| 层级 | 名称 | 核心假设 | 能证明的目标 | 不能证明的目标 |
| --- | --- | --- | --- | --- |
| A0 | functional prototype | Host、Proxy、firmware、配置可信 | API、性能、调度、数据面闭环 | 恶意 Host / co-tenant 安全 |
| A1 | ideal-GPC serial model | ideal GPC；RMM 可信；单全局 GPU 安全视图 | 单 Realm 或串行多 Realm 的安全共享模型 | 并行互不信任 Realm 安全 |
| A2 | ideal-GPC + trusted ASID | A1 + GPU MMU root/ASID/doorbell 不可被 Host/Proxy/task 修改 | 可探索多 address-space 并行隔离 | firmware 漏洞、硬件 bug、物理攻击 |
| A3 | RME-DA / multi-endpoint model | 多 VF/TDI/StreamID，每个 endpoint 独立 GPC view | 多 VM 并行设备赋值模型 | 设备内部隔离仍需 attestation 证明 |
| A4 | device TEE / physical model | A3 + firmware attestation、MEC/IDE、reset scrub | 恶意固件和物理/链路攻击下的更强模型 | 侧信道仍需单独建模 |

### 2.1 A1：ideal-GPC serial model

A1 是最应该先实现的模型。

它假设：

1. RMM/EL3 和 policy engine 可信；
2. Host 可以恶意控制 normal world、KVM、Firecracker、memfd、调度；
3. 其他 Realm CPU 和 GPU task 可以恶意提交任意访问；
4. ideal GPC 能按 endpoint/page/permission 拒绝未授权 CPU/GPU/DMA 访问；
5. GPU 一次只有一个全局安全视图；
6. GPU firmware 可信；
7. 物理攻击、侧信道、强 DoS 排除。

因此 A1 的调度单位不是 queue，而是 **owner epoch**：

```text
epoch A:
  install GPC view A
  bind GPUContext A
  run / drain / abort A
  invalidate TLB
  scrub reusable state
  revoke grants

epoch B:
  install GPC view B
  ...
```

A1 的安全命题：

> 在 epoch A 中，任何由 Realm A GPU task 发起的内存访问只能命中 A 的 private/shared grant；Host、Realm B、其他 DMA endpoint 对 A private page 的访问均失败。

这个模型牺牲并行性，换取清晰的证明边界。

### 2.2 A2：trusted ASID parallel model

A2 在 A1 之上增加：

1. 每个 GPUContext 有独立 page-table root；
2. GPU task 只能通过被绑定的 ASID 发起地址翻译；
3. page-table pages 位于 protected memory；
4. Host / Proxy / guest task 不能修改 ASID binding、page-table root、doorbell、queue state；
5. GPU MMU 正确性可信。

于是每个 task 的访问被限制为：

```text
GPU task A -> ASID A -> page table A -> only A-granted pages
GPU task B -> ASID B -> page table B -> only B-granted pages
```

但必须注意：如果 GPC 只有一个全局 view，而该 view 放行 A/B 页并集，那么安全性就转移到 GPU MMU/ASID 的可信性上。A2 的假设比 A1 更强。

A2 适合作为当前 `panthor-proxy` per-session native VM 的目标模型：

```text
proxy session
  -> protected GPUContext
  -> native Panthor VM
  -> protected page-table root
  -> ASID binding
  -> ideal GPC
```

### 2.3 A3：multi-endpoint model

A3 假设物理 GPU 暴露多个独立安全接口：

- SR-IOV VF；
- TDI；
- StreamID；
- MIG slice；
多个物理 GPU。

每个 endpoint 可以安装独立 GPC view，并绑定一个 Realm：

```text
Realm A -> VF/TDI/StreamID A -> view A -> key context A
Realm B -> VF/TDI/StreamID B -> view B -> key context B
```

这是长期并行多 VM 机密共享的正确模型。单个不可安全划分的 Function / TDI 不能仅凭 driver 层 Queue/Group 自动安全并行。

### 2.4 A4：device TEE / physical model

A4 在 A3 之上处理：

1. GPU firmware 度量和 attestation；
2. firmware / queue / scheduler 内部状态隔离；
3. reset 后跨 owner scrub；
4. MEC / MPE / IDE；
5. link 和物理攻击；
6. fault / rebalance 时的数据残留。

如果 A4 不成立，文档必须明确：

> GPU firmware 属于 TCB；物理攻击和恶意固件不在当前防护范围。

## 3. 本项目的基础抽象

### 3.1 GPUContext

当前 `panthor-proxy` session 可以升级为 GPUContext：

```text
GPUContext = {
  context_id,
  owner_realm,
  endpoint_id,
  asid,
  page_table_root,
  key_context,
  queue_state,
  allowed_object_set,
  epoch,
  state
}
```

与当前代码的对应：

| 模型字段 | 当前雏形 |
| --- | --- |
| `owner_realm` | `client_vmid` / `owner_vmid` |
| `context_id` | proxy session handle |
| `native VM` | `panthor_proxy_session_vm_create()` 创建的 real Panthor VM |
| `queue_state` | session-local group/syncobj/queue objects |
| `allowed_object_set` | session-local BO handles |
| `epoch` | object generation / mapping lease 的扩展 |
| `endpoint_id` | 当前缺失，A1 可先由 owner epoch 模拟 |

当前函数锚点：

- `Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c`
  - `panthor_proxy_handle_open_session()`
  - `panthor_proxy_session_vm_create()`
  - `panthor_proxy_session_group_create()`
  - `panthor_proxy_session_group_submit()`
- `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c`
  - `panthor_vm_prepare_map_op_ctx()`
  - `panthor_vm_map_vmshm_spans()`

### 3.2 ObjectGrant

当前 `proxy_vmshm_manager` 的 owner/generation/span 机制可以升级为显式 ObjectGrant：

```text
ObjectGrant = {
  object_id,
  page_span,
  owner,
  participants,
  permissions,
  confidentiality_domain,
  epoch,
  pin_count,
  gpu_users,
  revoke_state
}
```

权限建议拆成：

```text
CPU_READ / CPU_WRITE
GPU_READ / GPU_WRITE
COMMAND_FETCH
DMA_READ / DMA_WRITE
MMIO
SHARE_TRANSITION
```

当前 `proxy_vmshm_lookup_pin()` 已有 owner 检查，但 `required_perms` 被忽略：

```c
(void)required_perms;
```

因此 A1 模型必须先修复：

1. request 权限与 grant 权限匹配；
2. page span 检查，而不是只查 object handle；
3. epoch / generation 检查；
4. GPU in-flight 使用计数；
5. revoke 状态机。

### 3.3 ConfidentialityDomain

每个页必须明确属于一个 domain：

```text
PrivateDomain(Realm A)
PrivateDomain(Realm B)
SharedDomain(A,B)
ControlDomain
FirmwareDomain
MetadataDomain
```

规则：

1. private domain 只允许 owner 和其 GPUContext；
2. shared domain 必须显式记录 participants；
3. control/metadata domain 只允许 RMM/trusted owner；
4. firmware domain 是否可信由假设层级决定；
5. domain 变化必须先 quiesce 相关访问。

### 3.4 Ideal GPC oracle

A1/A2 实验中可以把 GPC 抽象成：

```text
gpc_check(endpoint, physical_page, operation, security_state)
  -> allow / deny / fault
```

策略输入：

```text
endpoint_id
realm_id
context_id
page_owner
participants
permission
epoch
key_context
task_state
gpu_inflight_state
```

关键要求：

1. oracle 位于 Host 不可控的 simulator / RMM 层；
2. CPU load/store、GPU translated access、DMA、MMIO、reset、page reuse 都要调用；
3. 所有拒绝路径必须可观测；
4. 策略变化和访问检查要有相同 epoch；
5. 不能让 Client 或 Host 直接调用 grant/revoke。

## 4. 与当前代码的映射和优化路线

### 4.1 vmshm object 层优化

当前问题：

- `vmshm-object` 是一个大 shared window；
- 每个 Client 的 GPA window 都能覆盖同一 domain 的其他 offset；
- software object table 隔离不等于 physical mapping isolation。

短期 A0 优化：

1. **per-client object domain**
   - 每个 Client 一个 object memfd；
   - Proxy 分别映射；
   - 跨 Client 共享必须新建 explicit shared domain。
2. **subrange KVM slot**
   - Firecracker 只映射被授权 object span；
   - slot 生命周期与 grant 绑定。
3. **permission enforcement**
   - 实现 `required_perms` 检查；
   - 避免 `(void)required_perms`。
4. **epoch grant**
   - grant 变化递增 epoch；
   - stale ioctl / mapping / completion 不能引用旧页。
5. **sparse span 保持**
   - 继续使用 payload span 翻译，不假设连续 GPA 对应连续 HPA。

相关代码：

- `firecracker/vmshm-broker/src/broker.rs`
  - `DomainRuntime::new()`
  - `handle_connection()`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/vmshm.rs`
  - `register_region()`
  - `validate_region()`
  - `register_notify()`
- `Linux-Guest-GPU/drivers/char/proxy_vmshm_manager/proxy_vmshm_manager.c`
  - `proxy_vmshm_alloc_ext()`
  - `proxy_vmshm_lookup_pin()`
  - `proxy_vmshm_obj_translate()`

### 4.2 broker / monitor 优化

CAGE 的 trusted owner 不应该由当前 Host broker 直接承担。推荐拆分：

```text
Host broker:
  topology, fd transport, performance dataplane

Trusted RMM policy authority:
  identity, grant, endpoint binding, epoch, revoke, key context
```

短期工程加固：

1. `SO_PEERCRED` / SCM_CREDENTIALS；
2. launch manifest 绑定 VM、pid namespace、uid、socket、domain、role；
3. role 唯一 active participant；
4. socket directory `0700`；
5. memfd/eventfd `CLOEXEC` 和 seals；
6. eventfd / irqfd rate limit；
7. broker seccomp / namespace / 最小 capability；
8. 所有拒绝路径审计。

在 A1/A2 中，这些措施仍不构成恶意 Host 安全根；真正的 grant 判定必须移入 ideal-GPC oracle / RMM。

### 4.3 GPUContext 优化

当前 per-session native VM 是正确方向，但需要升级：

1. **把 session 变成最小状态机**

```text
CREATED
 -> BOUND
 -> MAPPED
 -> RUNNABLE
 -> RUNNING
 -> DRAINING
 -> INVALIDATING
 -> SCRUBBING
 -> REVOKED
 -> DESTROYED
```

2. **保护 page-table root**
   - page table pages 转入 protected memory；
   - Client 和 Host 不能直接写；
   - Proxy 只提交语义请求，不拥有最终映射权。
3. **绑定 ASID / endpoint**
   - GPU task 不能切换 root；
   - group/queue 必须继承 context binding；
   - doorbell 写不能改变 address-space owner。
4. **session-local command metadata**
   - handle、syncobj、BO、heap 必须继续 namespace 隔离；
   - submit 时翻译成 context-local authorized spans。
5. **fault 隔离**
   - 恶意 shader 访问未映射 GPU VA 只能 fault；
   - fault 触发 context drain / invalidate，不允许整机回退到共享 GPU VA。

### 4.4 共享 BO 优化

共享页必须显式降级：

```text
PrivateDomain(A)
  -> quiesce A access
  -> convert to SharedDomain(A,B)
  -> install explicit grant
  -> run shared protocol
```

三种共享方式：

| 方式 | 性能 | 安全 | 适用 |
| --- | --- | --- | --- |
| 明文 shared domain | 最快 | 保密性降级，完整性需协议保护 | 显式互信或非敏感数据 |
| authenticated encryption | 中等 | 防 Host / 共享通道读改 | 跨 Realm 敏感协作 |
| copy-in / copy-out | 较低 | 验证简单，TOCTOU 少 | 控制 metadata、小对象 |

推荐混合策略：

1. command / ioctl metadata 使用 copy-in/copy-out；
2. 大数据 BO 使用 per-client private domain；
3. 显式协作数据使用 authenticated encryption shared domain；
4. Host 可见 transport page 不承载明文 secret；
5. sequence number / epoch 防 replay。

### 4.5 RMM lease 优化

当前 OpenCCA 已有实验入口：

- `SMC_RSI_OPENCCA_GPA_TO_HPA`
- `SMC_RSI_OPENCCA_GPU_REVOKE`

当前含义是 RMM 校验 Realm GPA 并记录 mapping lease；`GPU_REVOKE` 释放软件记录，不是硬件权限撤销。

A1 中可以把它优化成：

```text
gpu_grant_validate(realm, gpa_span, purpose)
gpu_context_bind(realm, context, endpoint, asid, key_context)
gpu_submit_enter(epoch)
gpu_quiesce(context)
gpu_invalidate(context)
gpu_scrub(reusable_span)
gpu_grant_revoke(realm, gpa_span)
```

关键优化：

1. span 粒度，而不是单个 BO 粗粒度；
2. lease 与 ObjectGrant / GPUContext 使用同一 epoch；
3. submit 前校验 in-flight 计数；
4. revoke 前强制 drain；
5. page reuse 前完成 invalidate + scrub；
6. RMM 记录 endpoint / ASID / key context，而不只是 GPA-to-HPA。

相关路径：

- `opencca/tf-rmm/runtime/rsi/opencca_gpu.c`
- `opencca/tf-rmm/runtime/core/exit.c`
- `opencca/tf-rmm/runtime/rmi/realm.c`

### 4.6 调度优化

A1 只能串行 protected owner，但仍可以优化吞吐：

1. **batched owner epoch**
   - 同一 Realm 的多个 queue/group 合并进一个 epoch；
   - 减少 GPC view switch 和 TLB invalidation 次数。
2. **lazy invalidation inside epoch**
   - 同 owner 内部 mapping 更新可以批量 invalidate；
   - 跨 owner 前必须强制全局 drain。
3. **shared-domain parallel slot**
   - 多个 Realm 显式共享的页可在 shared domain 中并行访问；
   - private page 仍不跨 owner。
4. **preemptible fence**
   - submit 时声明可中断点；
   - 切换 owner 前等待/ abort in-flight。
5. **admission control**
   - queue 数、BO size、doorbell rate、runtime quota；
   - 防止一个 owner 无限占住 epoch。
6. **优先级策略**
   - latency-sensitive小任务与 throughput batch 分开；
   - 但不能为了调度绕过 revoke 状态机。

### 4.7 eventfd / irqfd 优化

eventfd / ioeventfd / irqfd 只能作为通知，不承载安全授权。

需要保证：

1. notify 不能映射或授权内存；
2. doorbell 只触发固定 GPUContext；
3. eventfd storm 有限流；
4. IRQ 注入有 quota；
5. peer dead / close 触发 teardown；
6. revoke 时同步拆除 ioeventfd/irqfd；
7. notification 与 object epoch 绑定，防止 stale completion 唤醒旧任务。

## 5. 相比论文路线的优化点

### 5.1 相比 CAGE 的优化

CAGE 强调 trusted monitor 重建 GPU task 状态。本设计可以减少完全重建带来的语义成本：

1. **复用 Panthor native VM 作为 GPUContext**
   - 不需要 Proxy 解析全部 shader；
   - 安全边界放在 page-table root / ASID / GPC 授权；
   - Proxy 只保留兼容 API，不承担最终权限判定。
2. **object-level grant 与 page-level enforcement 分层**
   - 上层保留 BO / syncobj / group 语义；
   - 下层 ideal GPC 按 page/permission 强制；
   - 避免 GPU 语义解析进入 TCB。
3. **payload span 翻译**
   - 当前 `panthor_mmu.c` 已按 span 处理 vmshm-backed BO；
   - 可继续支持非连续 HPA，不要求大块连续物理内存。
4. **owner-epoch batching**
   - CAGE 单安全视图限制保留为安全前提；
   - 通过批量调度减少切换成本。
5. **攻击路径显式化**
   - 把 CPU、GPU、DMA、MMIO、reset、page reuse 全部接入 ideal-GPC oracle；
   - 不只验证 Host CPU denial。

### 5.2 相比 ACAI 的优化

ACAI 依赖较完整设备 TEE / RME-DA / IDE。本设计可以先构造中间层模型：

1. **A1 不要求 PCIe 设备 TEE**
   - 先研究集成 GPU 的授权一致性与生命周期；
   - physical attack 显式排除。
2. **A2 利用 GPU address-space 结构**
   - 在可信 page-table root 假设下探索并行；
   - 不等待完整 RME-DA 硬件。
3. **A3 明确升级接口**
   - 当 VF/TDI/StreamID 存在时，把 session 映射到 endpoint；
   - 保持同一 ObjectGrant / GPUContext ABI。
4. **软件 policy 先行**
   - 当前 vmshm / proxy 代码可以先验证 API、对象生命周期和调度；
   - 之后把 policy authority 迁入 RMM，而不是推翻系统。
5. **攻击 oracle 可复用**
   - 同一 ideal-GPC oracle 可以从 A1 迁移到 A2/A3；
   - 便于比较各假设层级的收益和安全边界。

### 5.3 当前场景特有的优势

1. **已有真实 API 兼容路径**
   - Client 使用 Panthor-compatible frontend；
   - Proxy 调 real DRM_PANTHOR；
   - 不是纯理论 scheduler。
2. **已有共享数据面**
   - memfd + eventfd / irqfd 支持低拷贝 RPC 和大 BO；
   - 可以实测授权粒度对性能的影响。
3. **已有 per-session GPU VM**
   - 可作为 GPUContext / ASID 实验基础。
4. **已有 RMM GPA-to-HPA lease**
   - 可扩展成 grant/revoke 生命周期实验。
5. **已有模型检查与板级 caveat**
   - `check-opencca-gpt-design-denial.sh` 能明确区分 model check 与硬件 enforcement。

## 6. 可能的创新点

### 6.1 Policy authority 与 compatibility proxy 分离

传统共享 GPU 容易把 Proxy 放入 TCB。本设计的创新点是拆成：

```text
RMM policy authority:
  owns identity, grant, translation authority, revoke

Compatibility proxy:
  owns API emulation, object namespace, scheduling hints

GPU hardware abstractions:
  GPC + ASID + endpoint + key context enforce final access
```

这使 Proxy 从安全判定者降级为语义适配层，TCB 更小。

### 6.2 Owner-epoch scheduling

针对单安全视图限制，提出显式 owner epoch：

```text
view install
  -> context bind
  -> task run
  -> drain
  -> invalidate
  -> scrub
  -> revoke
  -> next owner
```

创新价值：

1. 把 CAGE 的安全视图限制转成可调度的状态机；
2. 把性能优化集中在 epoch 切换次数；
3. 让 A1 单视图模型可实验、可比较；
4. 为 A3 多 endpoint 模型保留相同 ABI。

### 6.3 GPUContext = proxy session + native VM + endpoint + key context

把当前工程中的 per-session native VM 抽象为安全对象：

```text
session
  + protected page-table root
  + ASID binding
  + endpoint identity
  + key context
  + object grant set
  + lifecycle epoch
```

这个抽象可以同时表达：

- A1 串行 owner；
- A2 trusted ASID 并行；
- A3 multi-endpoint 并行。

### 6.4 Explicit confidentiality domain transition

把 private/shared 转换变成一等生命周期，而不是简单 mmap：

```text
Private(A)
  -> quiesce
  -> transition
  -> Shared(A,B,permissions,epoch)
  -> revoke
  -> scrub
```

这直接回应恶意共享 buffer 参与者问题，也避免同一明文页同时声称属于两个互斥 private domain。

### 6.5 Layered assumption evaluation

同一系统在 A1/A2/A3 下运行，可以量化：

1. ideal GPC 带来的检查开销；
2. per-client domain / subrange slot 的映射开销；
3. owner epoch 切换开销；
4. trusted ASID 并行带来的吞吐收益；
5. 多 endpoint 模型的调度收益；
6. revoke/scrub 的尾延迟。

这比只给出一个最终系统更能说明：**每个安全假设分别买了什么性能或安全能力。**

### 6.6 Attack-replay security validation

把历史攻击场景变成可重复 oracle 测试：

| 攻击 | 期待结果 |
| --- | --- |
| Host 读 private page | ideal GPC deny |
| Realm A CPU 访问 B page | stage-2 / GPC deny |
| Realm A GPU VA 访问 B BO | page table 未映射 / GPC deny |
| A GPU task 伪造 handle | grant permission deny |
| B 篡改 shared command | integrity check 或隔离失败 |
| revoke 后复用 page | epoch mismatch / scrub 后才 allow |
| stale TLB access | invalidate 后 deny |
| Host 改 page-table root | trusted state protect / deny |
| Host 改 GPC view | only RMM 可配置 |
| other DMA endpoint access | endpoint policy deny |
| GPU reset residue | scrub/rebind deny |

这可以把“模型安全”转化为可执行验收。

## 7. 推荐的安全不变量

模型必须维护以下不变量：

1. **唯一 authority**
   - 只有 RMM/EL3 policy authority 能修改 grant、GPC view、ASID binding、key context。
2. **唯一 confidentiality domain**
   - 每个 page 同一时间只有一个 private 或 shared domain。
3. **授权一致性**
   - CPU、GPU MMU、GPC、RMM grant 对同一 page 的判断一致。
4. **endpoint confinement**
   - GPU 访问必须携带 context/endpoint/ASID identity。
5. **ASID root immutability**
   - Host / Client / Proxy 不能修改 page-table root。
6. **显式共享**
   - shared page 必须显式 grant 并降级或加密。
7. **生命周期一致**
   - revoke 前 stop、drain、invalidate、scrub。
8. **epoch freshness**
   - stale task、completion、mapping、notification 不能操作旧 page。
9. **device interface 单 owner**
   - 一个安全 endpoint 同一时间只绑定一个 Realm，除非硬件证明可并行划分。
10. **failure containment**
   - fault/reset 不能把一个 owner 的数据或固件残留交给下一个 owner。

## 8. 实验设计

### 8.1 实现 ideal-GPC oracle

建议实现三层：

1. **policy builder**
   - 输入 Realm、GPUContext、ObjectGrant、page span、permission、epoch；
   - 输出 GPC view。
2. **access checker**
   - 拦截 CPU、GPU、DMA、MMIO、reset、page reuse；
   - 返回 allow/deny 并记录 reason。
3. **state machine checker**
   - 检查 bind/run/revoke 顺序；
   - 拒绝 stale epoch 或非法状态迁移。

注意：oracle 不能放在可被恶意 Host 绕过的 Host userspace。实验上可以放在：

- simulator memory system；
- QEMU/KVM instrumentation；
- RMM model checker；
- kernel test harness；
- 独立 reference monitor。

### 8.2 安全测试

最小测试集：

1. Host read/write private page；
2. cross-Realm CPU access；
3. cross-Realm GPU VA access；
4. forged handle / permission；
5. write-only page read；
6. command fetch from data-only page；
7. stale handle after revoke；
8. page reuse before scrub；
9. shared buffer replay / tamper；
10. endpoint mismatch；
11. ASID root tamper；
12. reset residue。

### 8.3 性能指标

需要区分安全检查开销和调度策略开销：

| 指标 | 说明 |
| --- | --- |
| RPC latency | Client 到 Proxy ioctl 转发延迟 |
| map/unmap latency | grant 建立和撤销开销 |
| GPU submit latency | submit 到 GPU 接收 |
| owner switch latency | drain + invalidate + scrub + view switch |
| epoch throughput | 每 epoch 完成任务数 |
| GPU utilization | 排除纯软件开销后的 GPU 使用率 |
| fault recovery time | 恶意 task fault 后恢复时间 |
| shared transfer throughput | 明文 / 加密 / copy 模式 |
| tail latency | revoke、scrub、reset 造成的尾延迟 |

### 8.4 对照组

建议至少四组：

1. A0 当前 whole-window proxy；
2. A0 + per-client domain；
3. A1 ideal-GPC serial；
4. A2 trusted-ASID parallel。

如果未来有多 VF/TDI 平台，再增加 A3。

## 9. 论文式表述建议

### 9.1 不应写

> We implement secure multi-VM GPU sharing on RK3588.

原因是：

- RK3588/OpenCCA 当前没有真实 GPC enforcement；
- Host probe 曾读成功；
- GPU firmware / physical attack 未防护；
- `RMM_CCA_DA` 是 experimental 且默认 OFF。

### 9.2 应该写

> We design and evaluate a layered confidential GPU sharing model under explicit ideal-GPC assumptions. We reuse a real Panthor proxy datapath and per-session native GPU VMs as the implementation substrate, and use an ideal-GPC oracle to evaluate whether the object grant, GPUContext, ASID binding, and revoke lifecycle preserve cross-Realm isolation.

中文表述：

> 我们在显式 ideal-GPC 假设下设计分层机密 GPU 共享模型，并基于真实 Panthor proxy 数据面和 per-session native GPU VM 构建实验原型；通过攻击回放验证对象授权、GPUContext、ASID 绑定和 revoke 生命周期是否能维持跨 Realm 隔离。

## 10. 结论

这个项目的核心不是等待真实 GPC 出现后再做系统，而是先把安全模型工程化：

```text
CAGE:
  trusted owner + shadow task + security view + lifecycle

ACAI:
  identity + binding + translation + crypto + device assignment

Our model:
  RMM policy authority
  + GPUContext
  + ObjectGrant
  + ConfidentialityDomain
  + ideal GPC oracle
  + owner-epoch / multi-endpoint scheduling
```

短期最有价值的路线：

1. A0 修复 per-client memfd domain 和 permission check；
2. A1 实现 ideal-GPC serial owner-epoch 模型和攻击回放；
3. A2 把 per-session Panthor VM 升级为 trusted page-table root / ASID binding；
4. A3 等待或模拟多个 VF/TDI/StreamID endpoint；
5. A4 再引入 firmware attestation、MEC/IDE 和物理攻击模型。

最核心的创新不是“比 CAGE/ACAI 更强”，而是：

> **把两者的安全不变量拆成可组合假设，在一个真实 Panthor 共享数据面上逐步验证授权、调度和生命周期设计，从而明确每个假设层级分别换来什么安全能力和性能成本。**

## 参考

1. Chenxu Wang et al., *CAGE: Complementing Arm CCA with GPU Extensions*, NDSS 2024. DOI: `10.14722/ndss.24763`.
2. Supraja Sridhara et al., *ACAI: Protecting Accelerator Execution with Arm Confidential Computing Architecture*, USENIX Security 2024; arXiv:2305.15986.
3. Arm, *Arm and Confidential Computing* — RME 2022 extensions: MEC and Device Assignment. URL: `https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/arm-and-confidential-computing`
4. Arm, *Realm Device Assignment* / RME System Architecture DEN0125 相关规格入口。
5. PCI-SIG TDISP / libspdm industry header: `pci_tdisp.h`, including `pci_tdisp_interface_id_t.function_id` and TDI state machine.
6. 本仓库：
   - `docs/shared/CCA_CAGE_ACAI_RME_DA_GPU_SHARING_ANALYSIS_20261013.md`
   - `docs/shared/CCA_TRUSTED_GPU_REALM_DIRECT_ACCESS_IMPLEMENTATION_REPORT.md`
   - `docs/shared/CCA_CONFIDENTIAL_GPU_SHARING_DESIGN.md`
   - `docs/shared/GPU_VIRTUALIZATION_DRIVER_ANALYSIS.md`
