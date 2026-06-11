# GPU 共享虚拟化驱动实现分析

本文档重写于 2026-06-05，目标是从整体架构、驱动实现、内存模型、
IOCTL 虚拟化、调度策略、测试结论和剩余风险几个层次，系统解释当前
GPU 共享虚拟化方案。

这不是单个模块的代码清单，而是一份帮助理解设计边界的工程文档。读完
后应该能回答这些问题：

- 为什么需要 Proxy VM 和 Client VM 的拆分。
- 两个 vmshm memslot 分别承担什么职责。
- 一个 client VM 的 Panthor IOCTL 如何被翻译成 proxy VM 的真实 Panthor
  操作。
- BO/mmap/VM_BIND 如何保证 client CPU、proxy driver 和物理 GPU 看到同一份
  数据。
- 多 client 并发时当前调度点在哪里，哪些调度方案已经被放弃。
- Proxy VM 为什么不能被当成普通 bare-metal host，因为它本身依赖自研 GPU
  passthrough 技术访问物理 GPU。

相关细节文档：

- `docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md`
- `docs/shared/PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md`
- `docs/shared/GPU_SFTP_ARTIFACT_LAYOUT.md`
- `docs/shared/PANTHOR_GLES_COMPUTE_SMOKE_BASELINE_ANALYSIS.md`
- `docs/passthrough/GPU_PASSTHROUGH_IMPLEMENTATION_ANALYSIS.md`
- `docs/passthrough/GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md`

## 1. 总体目标

当前实现是一套面向 Mali/Panthor GPU 的 split GPU virtualization 原型。
核心目标是让一个或多个 Client VM 中的普通 Mesa/Panfrost userspace 继续
看到一个 Panthor-compatible DRM 设备，但实际 GPU 资源由 Proxy VM 统一
持有和调度。

总体路径是：

```text
Client VM userspace
  -> /dev/dri/card* or /dev/dri/renderD*
  -> panthor-client DRM frontend
  -> client_vmshm_comm
  -> vmshm-broker / Firecracker eventfd relay
  -> proxy_vmshm_comm
  -> panthor-proxy
  -> real DRM_PANTHOR in Proxy VM
  -> physical Mali/Panthor GPU through custom passthrough
```

这个方案要虚拟化的不是一个简单的 ioctl number 转发层。Panthor userspace
依赖 GEM/BO、mmap、GPU VA、VM_BIND、syncobj/timeline、group/queue submit、
tiler heap 和 fence completion。它们都具有明确的 per-file namespace、
user pointer、CPU/GPU 共享内存和异步完成语义。因此当前设计采用：

```text
控制面：翻译 IOCTL、handle、数组、返回值和错误码
数据面：用 vmshm-object 承载 client 和 proxy/GPU 共同访问的 BO payload
提交面：在 proxy 内部做 GROUP_SUBMIT 前调度，再进入真实 Panthor scheduler
完成面：以 proxy 真实 syncobj/fence 为权威，client wait/query 通过 RPC 观察
```

当前已经实现并通过测试的主路径包括：

- `OPEN_SESSION` / `CLOSE_SESSION`
- `DRM_IOCTL_VERSION` / `DRM_IOCTL_GET_CAP`
- `DRM_IOCTL_PANTHOR_DEV_QUERY`
- `DRM_IOCTL_PANTHOR_VM_CREATE` / `VM_DESTROY` / `VM_GET_STATE`
- `DRM_IOCTL_PANTHOR_BO_CREATE` / `BO_MMAP_OFFSET` / client `.mmap`
- `DRM_IOCTL_PANTHOR_VM_BIND`，包括同步 MAP/UNMAP、async MAP/UNMAP、
  `SYNC_ONLY` 和 sync arrays
- `DRM_IOCTL_SYNCOBJ_CREATE` / `DESTROY` / `WAIT` / `TRANSFER` /
  `TIMELINE_WAIT` / `RESET` / `SIGNAL` / `TIMELINE_SIGNAL` / `QUERY`
- `DRM_IOCTL_PANTHOR_GROUP_CREATE` / `GROUP_DESTROY` / `GROUP_GET_STATE`
- `DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE` / `TILER_HEAP_DESTROY`
- `DRM_IOCTL_PANTHOR_GROUP_SUBMIT`
- client close 后的 session resource cleanup

当前已经通过一客户端 IOCTL sweep 和真实 Mesa/Panfrost GLES compute smoke。
两 client 并发 GLES smoke 也已经跑通，并且当前 32 MiB baseline 使用
`panthor-proxy` 内部 submit scheduler。

仍然没有完全解决或长期证明的范围包括：

- 多 client 的强隔离、恶意 client 防护和 channel/session 绑定。
- reset recovery，以及 proxy GPU reset 后 client session 如何恢复。
- PRIME/dma-buf/sync-file/eventfd 跨 VM 传递。
- 长时间压力运行下的泄漏自由。
- 更多 client、混合 workload 和真实配额/优先级/期限调度。
- 更系统的 cache maintenance 和 coherency 策略。

## 2. 架构角色

### 2.1 Host / Firecracker / Broker

Host 负责启动 VM、提供 vmshm memslot、运行 Firecracker 和 broker，并在
passthrough 路径中承担物理 GPU 的 host-side 管理。

共享虚拟化里 Host 不是 GPU API 的直接调用者；它提供运行环境：

- Firecracker 配置 Proxy VM 和 Client VM。
- vmshm memslot 在多个 VM 之间提供共享物理窗口。
- vmshm-broker 负责 eventfd/doorbell relay。
- host `pmthor` 和 KVM 扩展负责 Proxy VM 的 GPU passthrough。

Host 侧 CPU placement 对性能很关键。两 client 性能测试中，broker/proxy
和 client VM 的 Firecracker 进程 placement 会直接影响 buffer upload、
RPC latency 和 completion latency。

### 2.2 Proxy VM

Proxy VM 是共享 GPU 的可信 GPU owner。

Proxy VM 中运行：

- `proxy_vmshm_comm`：控制面共享内存 transport 的 proxy 端。
- `proxy_vmshm_manager`：数据面对象 memslot 的可信对象管理器。
- `panthor-proxy`：Panthor IOCTL RPC handler 和 handle translation 层。
- real `DRM_PANTHOR`：真实 Panthor driver，真正创建 VM/BO/group、
  执行 VM_BIND 和 GROUP_SUBMIT。

Proxy VM 看起来像一个拥有真实 GPU 的 VM，但它不是 bare-metal Linux。
它访问物理 GPU 依赖本项目的自研 passthrough：

```text
GPU MMIO      -> host KVM stage-2 device mapping
GPU page table -> guest Panthor GPA_TO_HPA hypercall, PTE/TTBR 写 HPA
GPU IRQ       -> host pmthor IRQ -> eventfd -> KVM irqfd -> proxy guest IRQ
EOI/unmask    -> KVM resamplefd -> host pmthor unmask
```

这意味着 shared path 的完成延迟、VM_BIND 正确性和 GPU fault 行为都不能
只按 native host Panthor 来理解。

### 2.3 Client VM

Client VM 不拥有真实 GPU MMIO，也不加载 real `DRM_PANTHOR`。

Client VM 中运行：

- `client_vmshm_comm`：控制面共享内存 transport 的 client 端。
- `client_vmshm_manager`：向 proxy 查询 payload object descriptor，并把
  offset 翻译为 client VM 本地 GPA/KVA。
- `panthor-client`：对 userspace 暴露名为 `panthor` 的 DRM frontend。

Client userspace 看到的是普通 Panthor DRM 设备，因此 Mesa/Panfrost 可以按
正常路径执行：

```text
open DRM node
  -> DRM_VERSION / GET_CAP / PANTHOR_DEV_QUERY
  -> VM_CREATE
  -> BO_CREATE / BO_MMAP_OFFSET / mmap
  -> VM_BIND
  -> SYNCOBJ_CREATE
  -> GROUP_CREATE / TILER_HEAP_CREATE
  -> GROUP_SUBMIT
  -> SYNCOBJ_TRANSFER / SYNCOBJ_TIMELINE_WAIT
  -> CPU mmap readback
  -> cleanup
```

区别在于这些 ioctl 大多不会在 client VM 本地创建真实 GPU 对象，而是被
拆解、校验、翻译并转发给 Proxy VM。

## 3. 代码地图

主要代码位于 `Linux-Guest-GPU`：

| 层次 | 文件 | 职责 |
| --- | --- | --- |
| 控制面 ABI | `include/linux/vmshm_comm.h` | 通用 request/response envelope、seq/reply_to、handler API |
| Panthor RPC ABI | `include/linux/panthor_vmshm.h` | Panthor 虚拟化消息 ID 和 request/response struct |
| 对象管理 ABI | `include/linux/vmshm_manager.h` | GET_OBJECT request/response 和 object descriptor |
| Proxy 对象 API | `include/linux/proxy_vmshm.h` | proxy 侧 object alloc/lookup/pin/grant/translate API |
| Client 对象 API | `include/linux/client_vmshm.h` | client 侧 descriptor lookup 和 offset->GPA/KVA API |
| Proxy 控制面 | `drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c` | 初始化控制面 layout，接收 client 请求，分发 handler |
| Client 控制面 | `drivers/char/client_vmshm_comm/client_comm_vmshm.c` | attach proxy layout，提供同步 RPC helper |
| Proxy 对象管理 | `drivers/char/proxy_vmshm_manager/proxy_vmshm_manager.c` | payload allocator、object/grant metadata、GET_OBJECT handler |
| Client 对象管理 | `drivers/char/client_vmshm_manager/client_vmshm_manager.c` | 查询 object descriptor，生成 client 侧映射视图 |
| Client DRM frontend | `drivers/gpu/drm/panthor-client/panthor_client_drv.c` | 对 client userspace 暴露 Panthor-compatible DRM device |
| Proxy Panthor bridge | `drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c` | Panthor RPC handler、session/handle translation、submit scheduler |
| Real Panthor hooks | `drivers/gpu/drm/panthor/panthor_drv.c` | `panthor_vmshm_*` helper，复用真实 Panthor 逻辑 |
| Real Panthor GEM | `drivers/gpu/drm/panthor/panthor_gem.c` | vmshm-backed GEM BO 创建和释放 |
| Real Panthor MMU | `drivers/gpu/drm/panthor/panthor_mmu.c` | VM_BIND 时将 vmshm payload span 映射进 GPU page table |
| Real Panthor scheduler | `drivers/gpu/drm/panthor/panthor_sched.c` | Panthor CSF/drm scheduler 相关逻辑和诊断参数 |
| DRM syncobj 修改 | `drivers/gpu/drm/drm_syncobj.c` | 本项目 syncobj/timeline 相关兼容修正 |

Kconfig 角色拆分：

| VM 角色 | 关键配置 |
| --- | --- |
| Proxy VM kernel | `PROXY_VMSHM_COMM`, `PROXY_VMSHM_MANAGER`, `DRM_PANTHOR`, `DRM_PANTHOR_PROXY` |
| Client VM kernel | `CLIENT_VMSHM_COMM`, `CLIENT_VMSHM_MANAGER`, `DRM_PANTHOR_CLIENT`, real `DRM_PANTHOR=n` |
| Passthrough guest kernel | real `DRM_PANTHOR`，不启用 client/proxy split frontend |

`DRM_PANTHOR_CLIENT` 显式依赖 `DRM_PANTHOR = n`，这是为了避免 Client VM 同时
暴露真实 Panthor driver 和虚拟 frontend。

## 4. 两个 vmshm memslot 的核心设计

共享虚拟化路径最重要的设计边界是两个 memslot：

```text
vmshm-comm:
  控制面。小消息、RPC envelope、ioctl metadata、flattened arrays、handle、
  return code、错误码、状态和调试请求。

vmshm-object:
  数据面。BO payload、未来可能的 submit/event/fence/transfer shared object，
  以及所有 client 或 GPU 需要直接访问的共享内存对象。
```

这个边界非常重要。不是所有“比较大”的结构都应该放进 object memslot。判断
标准不是大小，而是语义：

- 如果它只是一次 ioctl 的参数、数组、handle 或返回值，应留在
  `vmshm-comm`。
- 如果 client userspace、proxy driver 或物理 GPU 需要在 ioctl 之外持续访问
  同一份 backing，才应放进 `vmshm-object`。

当前放在 `vmshm-comm` 的典型内容：

- `VM_BIND ops[]`
- `VM_BIND syncs[]`
- `SYNCOBJ_WAIT handles[]`
- `SYNCOBJ_TIMELINE_WAIT handles[]/points[]`
- `SYNCOBJ_RESET/SIGNAL handles[]`
- `SYNCOBJ_TIMELINE_SIGNAL/QUERY handles[]/points[]`
- `GROUP_CREATE queues[]`
- `GROUP_SUBMIT jobs[]/syncs[]`
- request/response envelope 和 status

当前放在 `vmshm-object` 的典型内容：

- shader/code BO
- command stream BO
- descriptor/state BO
- SSBO/UBO/storage BO
- Mesa/Panthor queue 和 context backing BO
- tiler/context 相关 BO backing
- 后续可能需要 client/proxy/GPU 共同访问的 fence/event/transfer object

明确禁止的方向：

```text
不要把 VM_BIND/GROUP_SUBMIT/SYNCOBJ 等 transient ioctl arrays 放入
vmshm-object 作为通用 scratchpad。
```

原因是这些数组没有共享 payload 语义，不需要 mmap，也不该绕过
`vmshm-comm` 的 bounded message、权限、生命周期和 handler 校验。

## 5. 控制面：vmshm_comm

### 5.1 基本协议

`vmshm_comm` 是 client/proxy 之间的小消息 RPC transport。它不理解 GPU 语义，
只负责传输 request 和 response。

通用 envelope：

```text
type      message type，例如 PANTHOR_VMSHM_MSG_VM_BIND_REQ
flags     message flags
seq       request sequence number
reply_to  response 对应的 request seq
status    transport/handler status
payload   bounded payload
len       payload length
```

`seq` 和 `reply_to` 让 client 可以在共享队列上实现同步 RPC：

```text
client send req(seq=N)
proxy handle req
proxy send rsp(reply_to=N)
client waiter matches reply_to=N and rsp type
```

### 5.2 Proxy 侧

`proxy_vmshm_comm` 是 layout owner。它在 probe 时构建共享内存 layout：

- header
- object table
- queue 0: client -> proxy
- queue 1: proxy -> client
- descriptor table
- avail ring
- used ring
- message pool

每个 queue 的 message slot 当前是固定大小，适合 bounded control payload。
这也是为什么 Panthor RPC ABI 对 `VM_BIND` ops、sync arrays、GROUP_SUBMIT jobs
等设置了上限。

Proxy 侧 dispatch 做三件事：

1. 从 client->proxy queue 取消息。
2. 按 message type 找到注册 handler。
3. 把 `vmshm_comm_rx` 交给 handler，handler 再发送 response。

当前 `proxy_comm_vmshm` 的 handler registry 使用 `rwsem`：

```text
dispatch path:        down_read()
register/unregister: down_write()
```

这个锁形状很关键。旧的“执行 handler 时持有全局 mutex”会让多个 client
channel 的 handler 隐式串行化，即使两个 channel 都已经有请求进入 proxy VM。
`rwsem` 仍然保护 handler 生命周期，但允许不同 client channel 同时进入已注册
handler。

### 5.3 Client 侧

`client_vmshm_comm` 不创建 layout，只 attach proxy 已发布的 layout，并校验：

- magic/version
- queue count
- object table range
- queue object range
- descriptor/ring/message pool range

RPC helper `client_comm_vmshm_call()` 当前是同步接口。它支持两种完成方式：

- 有 IRQ/doorbell 时：发送后注册 waiter，等待 response completion。
- 无 IRQ/doorbell 时：发送后轮询 proxy->client queue。

Client 侧仍有 `rpc_lock`，所以同一个 client VM 的同步 RPC 调用会串行化。
这与“同一 DRM fd/session 的顺序语义”基本一致，但未来如果要提高一个 client
内部的并发，需要重新设计 request queue 和 waiter 模型。

### 5.4 vmshm_comm 不负责 GPU 调度

当前设计已经放弃 transport 层调度策略：

- 旧的 `global_dispatch`
- 旧的 `dispatch_budget`
- 旧的 `highpri_work`
- 旧的 `dispatch_stats`

这些策略把公平性放在 channel drain 层，但该层看不到 Panthor session、
group、submit、syncobj、VM_BIND 语义，因此不适合作为长期 GPU scheduler。

现在的原则是：

```text
proxy_comm_vmshm 尽快把请求送入 proxy VM；
GPU 相关调度放在 panthor-proxy 的 GROUP_SUBMIT 进入真实 Panthor 之前。
```

## 6. 数据面：vmshm_manager

### 6.1 Proxy 是可信 object metadata owner

`proxy_vmshm_manager` 管理 `vmshm-object` memslot。它把可共享 payload 内存
切分成对象，并把对象 metadata 保存在 proxy 私有内核内存中，而不是暴露给
client 随意修改。

每个 object 包含：

- id
- generation
- external handle = `(generation << 32) | id`
- owner_vmid
- object type
- perms
- offset / size / alloc_size
- backing kind
- pin_count
- grants
- state

generation 是抗 ABA 的。id 可以复用，但旧 handle 的 generation 不匹配时必须
lookup 失败。

当前 object 类型包括：

- `PROXY_VMSHM_OBJ_GENERIC`
- `PROXY_VMSHM_OBJ_GPU_BO`
- `PROXY_VMSHM_OBJ_COMMAND_BO`
- `PROXY_VMSHM_OBJ_SUBMIT_RING`
- `PROXY_VMSHM_OBJ_EVENT_RING`
- `PROXY_VMSHM_OBJ_FENCE_PAGE`
- `PROXY_VMSHM_OBJ_TRANSFER_BUFFER`

Panthor BO 当前使用 `PROXY_VMSHM_OBJ_GPU_BO`。

### 6.2 Allocator

Proxy manager 内部使用私有 allocator 从 payload memslot 切分 backing：

- 小对象可以走 slab。
- 普通连续对象走 buddy。
- 如果允许 SG，可走分段 backing。

当前 Panthor BO 创建使用：

```text
type  = PROXY_VMSHM_OBJ_GPU_BO
flags = PROXY_VMSHM_F_CONTIG
perms = CPU_READ | CPU_WRITE | MMAP | GPU_READ | GPU_WRITE
align = PAGE_SIZE
owner = PANTHOR_VMSHM_POC_CLIENT_VMID
```

也就是说当前 BO payload 是连续 object。代码中已经有 SG backing 和 span
translation 的支持，但 client 侧 descriptor 当前要求 contiguous object：

```text
VMSHM_MANAGER_DESC_F_CONTIG
nr_segments == 1
```

未来如果要支持大 BO 的 SG object，需要扩展 client descriptor 和 mmap 逻辑，
不能只在 proxy 侧打开 `PROXY_VMSHM_F_ALLOW_SG`。

### 6.3 Lookup 和权限

Client 不直接信任 handle。Client 通过 `client_vmshm_manager_get()` 发起：

```text
VMSHM_MANAGER_MSG_GET_OBJECT_REQ
  handle or grant_id
  lookup mode
  requester_vmid
  required_perms
```

Proxy manager handler 做：

```text
handle/generation 校验
owner 或 grant 校验
required_perms 校验
object state 校验
pin object
fill descriptor
unpin object
send descriptor response
```

Client 收到 descriptor 后再次校验：

- object 必须 contiguous。
- `size <= alloc_size`。
- offset/alloc_size 必须落在 client 本地 payload memslot 范围内。
- local GPA = client payload memslot base GPA + descriptor offset。
- local KVA = client mapped payload base KVA + descriptor offset。

这就是 client `.mmap` BO 时能把 payload pages remap 给 userspace 的依据。

### 6.4 Lifetime

Proxy object 支持普通 ref 和 pin。pin 的语义更强：它保护底层 backing 在
in-flight 使用期间不能归还给 allocator。

典型 BO 生命周期：

```text
panthor-proxy BO_CREATE
  -> proxy_vmshm_alloc_ext()
  -> panthor_vmshm_bo_create_from_payload()
  -> real Panthor GEM object pins payload
  -> client GET_OBJECT obtains descriptor
  -> client mmap maps payload GPA

GEM_CLOSE / session cleanup
  -> panthor_vmshm_bo_destroy()
  -> real Panthor GEM release unpins payload
  -> proxy_vmshm_free()
  -> backing zero/free after last pin releases
```

## 7. Panthor Client DRM Frontend

`panthor-client` 的目标是让 client userspace 看到一个足够兼容 Panthor 的 DRM
设备。它的 driver name 是 `panthor`，而不是 `panthor-client`，因为 Mesa loader
依赖 driver name 选择 Panfrost/Panthor userspace 路径。

每次 client userspace `open()` DRM node：

```text
panthor_client_open()
  -> allocate panthor_client_file
  -> init xarrays: bos, syncobjs, groups, heaps
  -> OPEN_SESSION RPC
  -> store session_id in file->driver_priv
```

每次 `postclose()`：

```text
release groups
release heaps
release BOs
release syncobjs
CLOSE_SESSION RPC
free panthor_client_file
```

Client frontend 维护的主要虚拟状态：

| Client 状态 | Proxy 状态 |
| --- | --- |
| `session_id` | `panthor_proxy_session` / real `panthor_vmshm_session` |
| client BO handle | proxy GEM handle + vmshm payload object |
| client VM id | proxy VM id |
| client syncobj handle | proxy syncobj handle |
| client group handle | proxy group handle |
| client tiler heap handle | proxy tiler heap handle |
| client fake mmap offset | vmshm payload descriptor offset |

Client-visible handle 不会被当作 proxy handle 使用。每次 RPC 都需要 proxy 在
对应 session 的 xarray 中重新翻译。

Client frontend 拦截的核心 DRM ioctl 包括：

- `DRM_IOCTL_GET_CAP`
- `DRM_IOCTL_GEM_CLOSE`
- `DRM_IOCTL_SYNCOBJ_*`
- `DRM_IOCTL_PRIME_*`
- `DRM_IOCTL_SYNCOBJ_EVENTFD`

PRIME 和 fd/eventfd 相关 ioctl 当前显式返回 `-EOPNOTSUPP`，且 `DRM_CAP_PRIME`
返回 `0`。这是正确行为，因为 fd number 是 VM/process local 的，不能裸转发。

明确禁止的方向：

```text
不要把 dma-buf fd、sync-file fd、eventfd 或 PRIME handle 对应的整数值
直接跨 VM 转发。
```

跨 VM fd 传递需要独立协议来传递被引用的 kernel object、权限、生命周期、
poll/event 语义和安全上下文。当前没有该协议。

## 8. Panthor Proxy Bridge

`panthor-proxy` 是 Panthor-specific RPC handler。它运行在 Proxy VM 中，
负责：

- 注册 Panthor message handler。
- 为每个 client open 创建 `panthor_proxy_session`。
- 为 session 打开 real `panthor_vmshm_session`。
- 维护 VM/BO/syncobj/group/heap xarray。
- 翻译 client handle 到 proxy real handle。
- 调用 real Panthor `panthor_vmshm_*` helper。
- 把 response 发回对应 proxy comm channel。

Proxy session 结构上的关键点：

```text
session_id
real_session
session lock
vms xarray
bos xarray
syncobjs xarray
groups xarray
heaps xarray
submit_queue
sched_node
closing/refcnt
```

`session->lock` 保护该 session 内的 handle map 和对象状态。不同 session
不会因为一个全局 Panthor-proxy mutex 而被强制串行化。真实 Panthor driver
内部仍会按自己的锁和 scheduler 规则处理资源。

当前已经强化的隔离点：

```text
Firecracker 为每个 client 注入 client_vmid。
proxy_comm_vmshm 将接收 channel 绑定到 client_vmid。
panthor_proxy_session 记录 owner_vmid。
proxy_vmshm_manager 按 owner_vmid 分 domain/object lookup。
跨 VM lookup 会返回 -EACCES，即使 client spoof requester_vmid。
panthor-proxy 所有 session 操作按 channel VMID lookup，不信任 raw RPC body。
跨 VM raw DEV_QUERY/CLOSE_SESSION 会记录 SESSION_ACCESS_DENIED。
```

2026-06-12 live-BO probe 已验证：client0 持有 32 MiB vmshm-backed BO
payload `0x100000001` 时，client1 以 spoofed `requester_vmid=1` 查询该
handle，`/dev/client_vmshm_manager` 返回 `EACCES`，随后 client1 仍能完成自己的
Panfrost GLES compute smoke。

同日 raw vmshm RPC probe 进一步验证：client1 直接写
`/dev/client_comm_vmshm`，用 client0 的 `session=2` 发送 forged
`DEV_QUERY` 和 `CLOSE_SESSION`。proxy 消费了两条消息，但分别输出：

```text
SESSION_ACCESS_DENIED op=lookup session=2 owner_vmid=1 requester_vmid=2
SESSION_ACCESS_DENIED op=destroy session=2 owner_vmid=1 requester_vmid=2
```

client0 的 60 秒 BO holder 继续完成 `PANTHOR_BO_HOLD_SMOKE=PASS`，client1
继续完成 `VMSHM_ISOLATION_RESULT=PASS` 和 Mali-G610/Panfrost GLES compute
smoke。因此当前跨 VM session 攻击面不是由 client 可控的 session id 决定，
而是由 proxy comm channel 的 VMID 决定。

## 9. Real Panthor 集成

`panthor-proxy` 不重新实现一个 GPU driver。它调用 real Panthor 中新增的
`panthor_vmshm_*` helper，让大部分真实语义仍由 real Panthor driver 负责。

### 9.1 vmshm session

`panthor_vmshm_session_open()` 在 real Panthor driver 内创建一个等价的
proxy-side Panthor session：

- 获取当前 real Panthor device。
- 初始化 `struct drm_file` 中需要的 GEM handle idr。
- 初始化 syncobj idr。
- 创建 `panthor_file`。
- 创建 VM pool 和 group pool。
- 将 `file.driver_priv` 指向 `panthor_file`。

这相当于给每个 client open 在 Proxy VM 内创建一个 real Panthor file/session。
不是通过真正的 proxy userspace 打开 `/dev/dri`，但保留了 per-file namespace
和 real driver resource ownership。

### 9.2 vmshm-backed GEM BO

普通 passthrough 单 VM 路径仍可以走 Panthor 原来的 shmem GEM 分配：

```text
panthor_gem_create_with_handle()
  -> drm_gem_shmem_create()
  -> drm_gem_handle_create()
```

Shared path 则走：

```text
panthor-proxy BO_CREATE
  -> proxy_vmshm_alloc_ext(PROXY_VMSHM_OBJ_GPU_BO)
  -> panthor_vmshm_bo_create_from_payload()
  -> panthor_gem_create_vmshm_with_handle()
  -> GEM object records bo->vmshm_payload
```

这里仍创建一个 `drm_gem_shmem_object` wrapper，但关键区别是
`panthor_gem_object` 记录了 `vmshm_payload`。VM_BIND 看到该 BO 时，不再用
shmem object 的 ordinary sg table 作为 GPU page table backing，而是把
`vmshm_payload` 翻译成 payload spans。

这就是 shared 和 passthrough 的内存路径区分：

```text
ordinary passthrough:
  userspace BO -> drm_gem_shmem pages -> GPU VM_BIND maps those pages

shared virtualization:
  client BO -> proxy vmshm payload object -> real Panthor GEM wrapper
            -> VM_BIND maps vmshm payload spans
            -> client mmap and GPU see same payload backing
```

### 9.3 VM_BIND 映射 payload spans

`panthor_mmu.c` 中 VM_BIND map path 会判断 BO 是否 vmshm-backed：

```text
if bo->vmshm_payload:
  max_spans = proxy_vmshm_obj_nr_segments(payload)
  proxy_vmshm_obj_translate(payload, bo_offset, size, spans)
  panthor_vm_map_vmshm_spans(vm, iova, prot, spans, ...)
else:
  drm_gem_shmem_pin()
  drm_gem_shmem_get_pages_sgt()
  panthor_vm_map_pages()
```

对 vmshm-backed BO，GPU page table map 的物理地址来自 payload span 的 GPA。
在 Proxy VM passthrough 环境下，后续 custom io-pgtable 仍必须把这些 GPA
转换成 HPA 后写进 GPU PTE。

因此正确的数据链是：

```text
client mmap payload GPA
  -> client CPU writes command/data
  -> proxy VM_BIND obtains same payload offset/GPA
  -> proxy Panthor passthrough io-pgtable writes HPA into GPU PTE
  -> physical GPU reads/writes payload
  -> client CPU reads same payload mapping
```

### 9.4 GROUP_SUBMIT

`panthor_vmshm_group_submit()` 复用真实 Panthor submit context：

- 创建 Panthor jobs。
- 为每个 job 添加 kernel-copied sync ops。
- collect signal ops。
- prepare mapped BO reservations。
- add dependencies and arm jobs。
- push jobs into real scheduler。
- cleanup submit context。

这意味着 Proxy VM 内真实 Panthor scheduler 看到的是普通-looking jobs。不同
client session 最终会作为不同 real Panthor file/session 的 group/job 进入
真实 scheduler。

## 10. IOCTL 虚拟化路径

### 10.1 Discovery 和 capability

`DRM_IOCTL_VERSION` 本地返回 Panthor-compatible driver identity：

```text
name = panthor
```

`DRM_IOCTL_GET_CAP` 关键返回：

```text
DRM_CAP_SYNCOBJ = 1
DRM_CAP_SYNCOBJ_TIMELINE = 1
DRM_CAP_PRIME = 0
```

`DRM_IOCTL_PANTHOR_DEV_QUERY` 通过 RPC 转发给 proxy，由 real Panthor 读取
真实 GPU info 和 CSIF info 后返回。当前 client 看到真实 Mali-G610/Panthor
能力信息。未来如果要做资源切分，可在这里裁剪 core mask、CSG/CS slot 等
能力。

### 10.2 VM lifecycle

`VM_CREATE`：

```text
client copies drm_panthor_vm_create
  -> VM_CREATE_REQ(session_id, flags, user_va_range)
  -> proxy creates real Panthor VM
  -> proxy allocates client_vm_id
  -> stores client_vm_id -> proxy_vm_id
  -> returns client_vm_id and user_va_range
```

`VM_DESTROY`：

```text
client sends client_vm_id
  -> proxy translates to proxy_vm_id
  -> real panthor_vmshm_vm_destroy()
  -> erase VM map
```

`VM_GET_STATE`：

```text
client_vm_id -> proxy_vm_id -> real VM state
```

### 10.3 BO_CREATE / BO_MMAP_OFFSET / mmap

`BO_CREATE`：

```text
client BO_CREATE(size, flags, exclusive_vm_id)
  -> BO_CREATE_REQ
  -> proxy translates exclusive_vm_id if present
  -> proxy allocates vmshm payload object
  -> proxy creates real Panthor GEM wrapper from payload
  -> proxy allocates client_bo_handle
  -> response includes client_bo_handle, proxy_bo_handle, payload handle/offset/size
  -> client GET_OBJECT(payload_handle)
  -> client records descriptor in BO table
```

`BO_MMAP_OFFSET`：

```text
client looks up BO
  -> verifies !NO_MMAP
  -> allocates client-local fake mmap offset
  -> returns fake offset to userspace
```

Client does not receive proxy real DRM fake mmap offset. That offset belongs to
the proxy DRM file namespace and is meaningless in Client VM.

Client `.mmap`：

```text
mmap(fd, offset=client_fake_offset)
  -> panthor_client_mmap()
  -> lookup BO by fake offset
  -> verify requested range within BO and payload alloc_size
  -> gpa = client_vmshm_object_gpa(payload_obj) + bo_offset
  -> remap_pfn_range() payload GPA into userspace VMA
```

Default mapping is write-combine unless `panthor_client.bo_mmap_cached=1` is
used as an experiment.

### 10.4 Flush-id mmap

Panthor userspace may mmap `DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET` to observe
flush id behavior. Client frontend provides a local flush-id page instead of
mapping real GPU MMIO. This mmap is not a BO mmap and does not use
`vmshm-object` payload allocation.

### 10.5 VM_BIND

Client side:

- Copies `drm_panthor_vm_bind_op[]` from userspace.
- For async bind, copies nested sync arrays.
- Validates stride, count, flags and operation type.
- For MAP, translates local BO handle to client BO handle.
- For sync ops, translates local syncobj handle to client syncobj handle.
- Sends bounded flattened request through `vmshm-comm`.

Proxy side:

- Translates client VM id to proxy VM id.
- For MAP, translates client BO handle to proxy GEM handle.
- For UNMAP, rejects BO handle and BO offset.
- For SYNC_ONLY, requires async flag and sync ops.
- Translates syncobj handles to proxy syncobj handles.
- Calls `panthor_vmshm_vm_bind()`.
- Returns failed-op index when real VM_BIND reports partial failure.

Key rule:

```text
VM_BIND maps GPU VA to proxy real BO handle, but for shared BO that real BO
is backed by vmshm payload spans. Therefore GPU VA ultimately points at the
same payload pages mapped by client userspace.
```

### 10.6 Syncobj and timeline

Client syncobj handles are virtual. Proxy syncobj handles are authoritative.

`SYNCOBJ_CREATE`：

```text
client intercepts DRM_IOCTL_SYNCOBJ_CREATE
  -> proxy creates real syncobj in real session
  -> proxy allocates client_syncobj_handle
  -> client records client/proxy handle pair
  -> userspace receives client_syncobj_handle
```

Wait/transfer/reset/signal/query all follow the same pattern：

```text
client copies user arrays
  -> validates handle count and flags
  -> translates local handles to client handles
  -> proxy translates client handles to proxy handles
  -> real drm syncobj operation in proxy session
  -> return status/result to client
```

Timeouts are handled carefully. Client and Proxy VM monotonic clocks are not
guaranteed identical, so client frontend converts absolute timeout/deadline
inputs into relative timeout values before sending where needed.

Short timeline wait timeout in Mesa polling path is not automatically an error.
Final correctness requires later fence completion and compute readback pass.

### 10.7 GROUP_CREATE / TILER_HEAP_CREATE

`GROUP_CREATE`：

```text
client copies queue_create array
  -> validates count/stride/priority
  -> sends flattened queues and core masks
  -> proxy translates VM id
  -> optional diagnostic core partitioning
  -> real panthor group create
  -> proxy allocates client_group_handle
```

`TILER_HEAP_CREATE`：

```text
client sends client_vm_id and heap parameters
  -> proxy translates VM id
  -> real panthor heap create
  -> proxy records proxy heap handle and returned GPU VAs
  -> client receives client heap handle plus GPU VA values
```

Heap handle must also be virtualized. Real Panthor heap handle may encode VM
state, so it must not be used as the client-visible handle.

### 10.8 GROUP_SUBMIT

Client side:

- Copies `drm_panthor_queue_submit[]`.
- Copies nested sync arrays.
- Validates stream fields and sync flags.
- Looks up client group.
- Translates syncobj handles.
- Sends flattened `GROUP_SUBMIT_REQ` through `vmshm-comm`.

Proxy side:

- Accepts request through proxy comm.
- Queues it into `panthor-proxy` submit scheduler.
- Scheduler selects a session/request.
- Translates client group handle to proxy group handle.
- Translates syncobj handles.
- Preserves `stream_addr` as GPU VA.
- Calls `panthor_vmshm_group_submit()`.

`stream_addr` is not a user pointer and not a vmshm offset. It is GPU virtual
address. It should remain the value Mesa produced after VM_BIND.

Submit return semantics:

```text
GROUP_SUBMIT ret=0 means job was accepted/queued by real Panthor path.
It does not mean GPU execution is complete.
Completion is observed through proxy real syncobj/fence and client wait/query.
```

The real proof of data correctness is:

```text
GROUP_SUBMIT nonzero command stream
  -> syncobj/timeline wait succeeds
  -> client CPU mmap readback sees GPU-written SSBO data
  -> COMPUTE_CHECK=PASS
```

### 10.9 Cleanup

Cleanup is part of the supported design, not a best-effort afterthought.

Explicit cleanup paths:

- `GEM_CLOSE` -> `BO_DESTROY`
- `SYNCOBJ_DESTROY`
- `GROUP_DESTROY`
- `TILER_HEAP_DESTROY`
- `VM_DESTROY`
- `CLOSE_SESSION`

Session close also releases leftover resources if userspace exits without
destroying everything explicitly. Proxy logs include leftover counters such as
BOs, syncobjs, VMs, groups and heaps.

## 11. 调度架构

这里的调度不解释 CSF firmware 内部。固件闭源，不能可靠分析。当前能控制和
分析的是三层：

```text
1. Host/Firecracker placement
2. Proxy transport and panthor-proxy submit scheduling
3. Proxy VM real Panthor driver scheduler
```

### 11.1 Host/Firecracker placement

多 client 测试中，Host 调度会影响：

- client CPU upload 到 BO mmap 的速度。
- proxy VM vCPU 是否及时处理 RPC、VM_BIND、submit 和 IRQ thread。
- broker/eventfd relay 是否被延迟。
- Firecracker 进程是否互相抢占。

当前 32 MiB 两 client baseline 的推荐 placement：

```text
host CPUs online:        0-3
broker/proxy placement: broker 0-1, proxy Firecracker 0-1
client placement:       client0 CPU 2, client1 CPU 3
proxy vCPUs:            2
client vCPUs:           1 each
proxy memory:           at least 184 MiB
client memory:          128 MiB for 32 MiB smoke
stats:                  off for formal timing
metric:                 PERF_ITER_US with --exclude-cpu-prepare
```

### 11.2 proxy_comm_vmshm transport

`proxy_comm_vmshm` 当前定位为 fast transport：

```text
client channel request enters proxy VM as quickly as possible
no channel-level GPU fairness policy
no old global_dispatch/dispatch_budget/highpri_work knobs
```

保留的关键并发改动是 handler registry `rwsem`。它避免不同 client channel 在
handler registry 上被无意义地串行化。

### 11.3 panthor-proxy submit scheduler

当前真正的 GPU 共享调度点位于：

```text
proxy comm receive
  -> panthor-proxy handler
  -> per-session GROUP_SUBMIT FIFO queue
  -> global runnable-session round-robin worker
  -> panthor_vmshm_group_submit()
  -> real Panthor scheduler
```

第一版策略：

- 每个 session 有 FIFO submit queue。
- 全局 runnable session list 做 round-robin。
- 每次从一个 runnable session 取一个 `GROUP_SUBMIT`。
- 如果该 session 还有 submit，重新排到 runnable list 尾部。
- 全局 submit queue 深度有限，超限返回 `-EBUSY`。
- session closing 时 fail pending submits。

这个调度点比 channel drain 层更合理，因为它已经知道 session identity、
group handle、sync handles 和 submit 语义，但还没把 job 推入 real Panthor
scheduler。未来的 weighted fair queueing、per-client inflight limit、
priority/deadline 都应该在这里扩展。

### 11.4 Real Panthor scheduler

`panthor_vmshm_group_submit()` 最终创建真实 Panthor scheduler jobs。之后：

- drm scheduler
- Panthor group priority
- CSG/CS slot availability
- Panthor scheduler tick
- IRQ completion work
- CSF firmware

共同决定实际执行顺序。

当前 real Panthor scheduler 有诊断参数：

```text
panthor.sched_tick_ms=N
panthor.sched_highpri_wq=1
```

它们是实验/诊断开关，不是当前 formal baseline 的默认优化。

`panthor_proxy.group_core_partitions=N` 也是诊断开关。32 MiB 两 client 测试中
`N=2` 会把 shader core mask 按 session 拆分，但性能变差，主要体现在
`map_wait` 增大。因此它不是当前默认策略。

## 12. Proxy VM 的 passthrough 约束

共享虚拟化文档必须一直记住：Proxy VM 的 real Panthor driver 不是在 native
host 上直接操作 GPU，而是在 passthrough guest 内操作物理 GPU。

关键约束：

### 12.1 GPU page table 必须写 HPA

物理 GPU 的 page walker 不理解 KVM stage-2 翻译。GPU PTE 中如果写 GPA，
GPU 会把它当 host physical address 使用，导致错误内存访问、MMU fault 或
job timeout。

因此 passthrough Panthor 路径要求：

```text
TTBR/root table descriptor -> HPA
non-leaf table descriptor  -> HPA
leaf PTE for BO pages      -> HPA
```

Guest Panthor 通过私有 SMCCC `GPA_TO_HPA` hypercall 批量把 GPA 转为 HPA。
map/unmap 必须保持 4K 粒度正确性，不能把连续 GPA 假设为连续 HPA。

### 12.2 IRQ completion 不等同 native host

真实 GPU 完成路径：

```text
physical GPU IRQ
  -> host pmthor IRQ handler
  -> eventfd
  -> KVM irqfd
  -> proxy guest IRQ
  -> guest Panthor IRQ/threaded handler
  -> scheduler completion
  -> KVM resamplefd/EOI
  -> host pmthor unmask
```

如果这条链路延迟或失效，表现可能是：

- `GROUP_SUBMIT` 返回 0，但 wait 超时。
- timeline fence 不 signal。
- final readback 没有 GPU 写入结果。
- client 看到 `COMPUTE_CHECK` 失败。

因此测试不能只看 submit 成功，必须看 fence wait 和 readback。

### 12.3 Shared BO 和 passthrough BO 内存路径不同

单 VM passthrough 的 userspace 仍可以走普通 Panthor GEM/shmem BO。

Shared virtualization 的 client-visible BO 则来自 vmshm-object memslot。proxy
创建 real Panthor GEM wrapper 后，VM_BIND 使用 vmshm payload spans。

这解释了性能分析中 shared 和 passthrough 的差异：shared 并不是“同一个内核
shmem 分配路径再多一层 RPC”，它的数据面有专用 payload memslot 和对象管理器。
但 proxy VM 最终提交 GPU 任务仍会经过 passthrough 的 GPA->HPA 和 IRQ 路径。

## 13. 测试和当前结论

### 13.1 一 client correctness

一客户端路径已经完成从 discovery-only 到真实 compute workload 的跨越。

已通过的 IOCTL smoke surface 包括：

| 模式 | 结论 |
| --- | --- |
| basic / DEV_QUERY | PASS |
| VM_CREATE / VM_DESTROY | PASS |
| BO_CREATE | PASS |
| BO lifecycle / session cleanup | PASS |
| BO_MMAP_OFFSET / client mmap | PASS |
| VM_BIND sync map/unmap | PASS |
| VM_BIND async sync arrays / SYNC_ONLY | PASS |
| VM_GET_STATE / flush-id mmap | PASS |
| SYNCOBJ lifecycle | PASS |
| SYNCOBJ wait / transfer / timeline wait | PASS |
| SYNCOBJ reset/signal/timeline signal/query | PASS |
| GROUP lifecycle | PASS |
| GROUP_SUBMIT syncpoint | PASS |
| TILER_HEAP lifecycle | PASS |

真实 GLES compute smoke 也已经通过，关键证据是：

```text
GL_RENDERER=Mali-G610 (Panfrost)
COMPUTE_CHECK=PASS
GPU_SMOKE_RESULT=PASS
RESULT=PASS
```

这证明：

- Mesa/Panfrost 能在 Client VM 中识别虚拟 Panthor 设备。
- Client BO mmap 写入的数据能被 proxy GPU path 读取。
- VM_BIND 能把 shared payload backing 映射到真实 GPU VA。
- 非零 GROUP_SUBMIT 能执行。
- Proxy syncobj/timeline wait 能传回完成状态。
- Client CPU readback 能看到 GPU 写回结果。

### 13.2 不支持 fd/PRIME

当前已明确拒绝：

- `DRM_IOCTL_PRIME_HANDLE_TO_FD`
- `DRM_IOCTL_PRIME_FD_TO_HANDLE`
- `DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD`
- `DRM_IOCTL_SYNCOBJ_FD_TO_HANDLE`
- `DRM_IOCTL_SYNCOBJ_EVENTFD`

这是设计正确性的一部分，不是缺陷绕过。未来要支持这些 ioctl，需要新增跨 VM
fd/object/event 协议。

### 13.3 性能测试口径

当前 host/passthrough/shared 性能对比使用：

```text
PERF_ITER_US / iter_total
--exclude-cpu-prepare
metadata = buffer_upload
```

也就是说 CPU 侧填充 input[] 的时间不计入 formal iter_total，但仍会打印为
`cpu_prepare` 供参考。这样 host、passthrough 和 shared 对比更可信。

一 client CPU-prepare-excluded 结果显示，shared 的主要固定差距来自 submit/RPC
和同步路径，而不是随 buffer size 线性增长的数据面开销。64 MiB 时 host/shared
已经明显接近，说明 vmshm-backed BO 数据面本身是健康的。

### 13.4 两 client 32 MiB baseline

当前两 client 调度优化以 32 MiB GLES smoke 为 baseline，因为 4 MiB/16 MiB
更容易被固定开销支配。

当前最新 clean-memory proxy-submit-scheduler 32 MiB smoke：

```text
run id: vmshm-2client-gles-32m-cleanmem-20260605-165531
policy: panthor-proxy per-session submit scheduler before real Panthor submit
result: RESULT: GLES_PASS
metric: PERF_ITER_US, --exclude-cpu-prepare
host direct baseline: gpu-perf-host-direct-32m-current-20260605-152347
```

| Workload | Host direct | Client0 shared | Client1 shared | Shared avg | Host/client0 | Host/client1 | Host/shared avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 MiB | 11058.75 us | 13207.50 us | 13146.20 us | 13176.85 us | 0.837 | 0.841 | 0.839 |

Phase detail:

| Client | buffer_upload avg | dispatch_call avg | map_wait avg | iter_total avg/max |
| --- | ---: | ---: | ---: | ---: |
| client0 | 7118.70 us | 1777.20 us | 4230.65 us | 13207.50 / 15442 us |
| client1 | 6732.75 us | 1866.40 us | 4450.20 us | 13146.20 / 17939 us |

For comparison, the first proxy-submit-scheduler sample was:

```text
run id: vmshm-2client-gles-32m-proxy-submit-sched-20260605-162753
client0/client1/shared avg: 14668.00 / 13232.45 / 13950.23 us
```

Clean-memory 结果优于早期 32 MiB transport-layer baseline `15519.33 us`，也优于
第一次 proxy-submit-scheduler 样本 `13950.23 us`。这说明把调度点从 proxy comm
channel 层移动到 `panthor-proxy` submit 前是正确方向。当前 host/shared 平均比值
是 `0.839`，即 shared 两 client 平均时间比 host direct 高约 `19.2%`。下一步应在
`panthor-proxy` 内增加 per-client inflight、priority、deadline 或更详细的
scheduler diagnostics，以继续压低 `dispatch_call` 和 `map_wait` tail。

## 14. 当前瓶颈

按现有测试和诊断，瓶颈排序大致是：

### 14.1 固定 RPC/submit/sync overhead

Shared path 每次 submit 不只是 real Panthor ioctl：

```text
client ioctl
  -> client RPC lock/send
  -> vmshm queue
  -> broker/doorbell/IRQ
  -> proxy comm dispatch
  -> panthor-proxy handler
  -> submit scheduler
  -> real Panthor submit
  -> response
```

这部分在小/中 workload 中占比明显。优化重点不是 memcpy 大 buffer，而是减少
serialized round trips、缩短 wait path、降低 proxy setup tail。

### 14.2 VM_BIND 和 setup RPC tail

历史 stats run 显示 `VM_BIND`、`TILER_HEAP_CREATE` 可能出现很大 tail。它们不是
每次 shader 执行时间，但会显著影响短 workload 和首次 submit。

可优化方向：

- DEV_QUERY 缓存。
- VM_BIND batching。
- 减少小 bind fragment 的 request/response 次数。
- 对常见 BO/heap wrapper 做安全池化。

### 14.3 Client BO upload

Shared BO upload 写的是 Client VM 中的 vmshm payload mapping。它与 host direct
ordinary userspace mapping 和 passthrough ordinary shmem GEM mapping 都不同。

当前数据面是可用的，但仍可能受：

- client VM vCPU placement
- mapping attribute WC/WB
- cache maintenance
- host memory pressure
- Firecracker scheduling

影响。

`panthor_client.bo_mmap_cached=1` 是实验开关，不是默认结论。

### 14.4 Proxy VM 内存压力

Proxy VM 内存不足会在 real Panthor GEM wrapper、VM_BIND metadata 或 stats run
中触发 OOM。当前两 client 64 MiB/32 MiB formal run 应保持 proxy memory 至少
184 MiB，并记录 memory guard。

### 14.5 GPU core hard partition 不适合当前 32 MiB baseline

`panthor_proxy.group_core_partitions=2` 能把两个 session 的 shader core mask
拆分，但 32 MiB 两 client 测试性能变差，主要是 `map_wait` 变大。当前结论是：

```text
不要把 core partition 作为默认调度策略。
让 real Panthor scheduler/FW 使用完整可用 core，proxy 侧主要做 submit
fairness 和 inflight 控制。
```

## 15. 设计不变量和禁止方向

这些规则是当前实现的安全边界：

1. `vmshm-comm` 承载 transient ioctl metadata；`vmshm-object` 承载真正需要共享
   的 payload object。
2. Client-visible handle 永远不能直接当作 proxy real handle 使用。
3. Proxy real handle 永远不应作为 client handle 裸返回。
4. Client `.mmap` 使用 client fake mmap offset，不使用 proxy DRM fake mmap
   offset。
5. PRIME/dma-buf/sync-file/eventfd integer fd 不允许裸转发。
6. Proxy VM passthrough GPU page table 必须写 HPA，不能写 GPA。
7. `GROUP_SUBMIT ret=0` 不等于 GPU 完成；必须用 syncobj/fence/readback 判断。
8. Transport 层不做长期 GPU fairness；GPU work scheduling 放在
   `panthor-proxy` submit-before-real-DRM 边界。
9. Stats/diagnostic knob 不能混入 formal baseline。
10. Core partition 是实验，不是当前默认策略。

## 16. 剩余设计工作

### 16.1 多 client 隔离

基础 VMID 隔离已经落地：`panthor_proxy_session` 绑定到创建它的
channel/client identity，`vmshm-object` payload object 按 owner VMID 分域，
跨 VM descriptor lookup 被拒绝。当前 live-BO 负向 probe 覆盖了 BO payload
descriptor 泄漏风险；raw vmshm RPC 负向 probe 覆盖了绕过 `panthor-client`
前端、直接向 comm ring 伪造 cross-session `DEV_QUERY`/`CLOSE_SESSION` 的攻击
路径。

还需要继续扩展的系统验证：

- 更多 per-object 操作的恶意矩阵：client0 不能使用 client1 的
  VM/BO/syncobj/group/heap handle。
- stale handle generation 检查覆盖所有 object。
- close/session cleanup 不影响其他 client；当前 raw `CLOSE_SESSION` 负向
  probe 已覆盖 live-session cross-VM close 攻击。
- proxy reset/error path 不泄漏对象。

### 16.2 调度策略完善

当前 submit scheduler 只是第一版：

```text
per-session FIFO + global runnable-session round-robin
```

后续可加：

- per-client inflight limit。
- weighted fair queueing。
- priority class。
- deadline/latency-sensitive queue。
- setup RPC 和 submit RPC 分离统计。
- 按 group/queue 类型识别 compute/fragment/tiler workload。
- backpressure：当某 client pending 过深时让 client 侧更早感知。

### 16.3 RPC 和 setup 优化

可优化项：

- DEV_QUERY 缓存，避免 Mesa setup 中大量重复 discovery RPC。
- VM_BIND batching。
- TILER_HEAP/BO wrapper pool。
- 合并 cleanup/unmap 请求。
- 减少同步 RPC 的全局 `rpc_lock` 影响。

### 16.4 Cache/coherency 策略

当前 smoke 能通过，但长期设计应明确：

- client CPU write -> GPU read 前的 flush 策略。
- GPU write -> client CPU read 前的 invalidate 策略。
- WC/WB mapping 的默认选择。
- 哪些 BO 被 GPU writeable。
- fence completion 与 cache maintenance 的顺序关系。

目前不能只依赖“测试刚好通过”作为正式 coherency 设计。

### 16.5 fd/dma-buf/eventfd 协议

如果未来要支持 PRIME 或 syncobj fd/eventfd，需要新协议描述：

- cross-VM object export/import。
- fd 所指对象的生命周期。
- 权限和 revoke。
- poll/eventfd notification。
- dma-buf attachment 和 cache ownership。

在此之前继续返回 `-EOPNOTSUPP`。

### 16.6 Reset recovery

需要定义：

- real Panthor reset 时 proxy session 状态如何变化。
- client wait 返回什么错误。
- BO/VM/group 是否保留或全部失效。
- client 是否能重新 open/session。
- proxy 与 host passthrough reset 如何同步。

### 16.7 SG payload object

当前 client descriptor/mmap 只接受 contiguous object。要支持更大的 BO 或减少
memslot fragmentation，需要设计 SG descriptor：

- 多 segment descriptor ABI。
- client mmap 多段 remap。
- VM_BIND 多 span map。
- object lifetime/pin 与 segment list 的一致性。

## 17. 如何阅读和调试当前实现

推荐阅读顺序：

1. `include/linux/panthor_vmshm.h`：先看支持哪些 message 和 request/response。
2. `drivers/gpu/drm/panthor-client/panthor_client_drv.c`：看 client 如何拦截
   DRM/Panthor ioctl、维护 local state、发 RPC。
3. `drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c`：看 proxy 如何维护 session
   和翻译 handle。
4. `drivers/gpu/drm/panthor/panthor_drv.c`：看 real Panthor helper 如何复用真实
   driver。
5. `drivers/gpu/drm/panthor/panthor_gem.c` 和 `panthor_mmu.c`：看 vmshm-backed BO
   如何成为真实 GPU page table mapping。
6. `drivers/char/*vmshm*`：看控制面和对象面如何在两个 memslot 上工作。
7. `docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md`：查每一步测试证据和
   已放弃方向。

调试时先区分失败属于哪一层：

| 症状 | 优先检查 |
| --- | --- |
| open 或 DEV_QUERY 失败 | comm memslot、broker、proxy handler 注册 |
| BO_CREATE 失败 | proxy payload allocator、memslot size、GET_OBJECT 权限 |
| mmap fault | client fake offset、descriptor range、payload GPA |
| VM_BIND 失败 | VM/BO/sync handle 翻译、payload spans、passthrough GPA->HPA |
| submit ret 非 0 | group handle、stream fields、sync ops、real Panthor submit |
| wait 超时 | proxy syncobj、IRQ chain、Panthor scheduler、passthrough completion |
| readback 错 | shared backing、cache/coherency、VM_BIND mapping、GPU execution |
| 两 client tail 大 | host placement、proxy submit scheduler、RPC stats、VM_BIND/setup tail |

## 18. 一句话总结

当前 GPU 共享虚拟化实现已经形成了清晰的 split-driver 架构：

```text
Client VM 提供 Panthor-compatible DRM frontend；
Proxy VM 通过 vmshm control RPC 接收请求；
需要共享给 client 或 GPU 的 BO 数据放入独立 vmshm-object memslot；
Proxy 将 client handle 翻译为真实 Panthor session handle；
真实 Panthor driver 在 Proxy VM 中通过自研 passthrough 路径驱动物理 GPU；
多 client 的 GPU work 调度点放在 panthor-proxy 的 GROUP_SUBMIT 进入真实
Panthor scheduler 之前。
```

这套实现已经能跑通真实 Mesa/Panfrost compute workload。下一阶段的关键不是
再证明“能不能提交”，而是把多 client 隔离、调度策略、RPC/setup tail、
cache/coherency、reset recovery 和跨 VM fd/object 协议补齐，让它从可用原型
走向更完整的共享 GPU 虚拟化系统。
