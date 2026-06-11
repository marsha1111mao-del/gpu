# Panthor IOCTL 虚拟化设计整理

本文档基于 `GPU_VIRTUALIZATION_DRIVER_ANALYSIS.md`、当前
`panthor-client`/`panthor-proxy` 实现状态，以及一次 Mesa/Panthor GLES
compute workload 的真实 IOCTL 生命周期，整理 client VM 通过 proxy VM 使用真实
Mali/Panthor GPU 时，各类 DRM/Panthor IOCTL 应如何虚拟化。

核心目标是让 client VM userspace 仍然看到一个 Panthor-compatible DRM device，
Mesa/Panthor 可以按正常路径执行：

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

最终效果是 client VM 没有真实 GPU MMIO 和真实 Panthor driver，但仍能通过
proxy VM 中的真实 Panthor driver 完成 GPU command stream 提交、fence 等待和
SSBO readback。

## 1. 当前状态

当前实现是 split GPU virtualization prototype：

- proxy VM 拥有真实 Mali/Panthor GPU，并运行真实 `DRM_PANTHOR` driver。
- client VM 暴露 `panthor-client` DRM frontend，不直接访问真实 GPU。
- 两个 VM 通过 Firecracker/VMM 提供的 `vmshm` shared memory 通信。
- `*_vmshm_comm` 是 control-plane RPC 通道。
- `*_vmshm_manager` 管理 payload/object shared memory window。

当前一客户端原型已经越过 discovery-only 阶段。`panthor-client`/`panthor-proxy`
已经实现并验证了以下 Panthor/DRM 路径：

- `OPEN_SESSION` / `CLOSE_SESSION`
- `DRM_IOCTL_VERSION` / `DRM_IOCTL_GET_CAP`
- `DRM_IOCTL_PANTHOR_DEV_QUERY`
- `DRM_IOCTL_PANTHOR_VM_CREATE` / `VM_DESTROY` / `VM_GET_STATE`
- `DRM_IOCTL_PANTHOR_BO_CREATE` / `BO_MMAP_OFFSET` / client `.mmap`
- `DRM_IOCTL_PANTHOR_VM_BIND`，包括同步 MAP/UNMAP、async MAP/UNMAP 和
  `SYNC_ONLY`
- `DRM_IOCTL_SYNCOBJ_CREATE` / `DESTROY` / `WAIT` / `TRANSFER` /
  `TIMELINE_WAIT` / `RESET` / `SIGNAL` / `TIMELINE_SIGNAL` / `QUERY`
- `DRM_IOCTL_PANTHOR_GROUP_CREATE` / `GROUP_DESTROY` / `GROUP_GET_STATE` /
  `GROUP_SUBMIT`
- `DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE` / `TILER_HEAP_DESTROY`
- client close 后的 session resource cleanup

这些路径已经通过一客户端 16 模式 ioctl sweep，并通过一次
`gles-compute-smoke --count 4096 --iterations 5 --warmup 1 --perf` 的真实
Mesa/Panfrost compute workload。该 workload 证明了非零 `GROUP_SUBMIT`、
vmshm-backed BO、proxy 真实 Panthor `VM_BIND`、syncobj/timeline wait 和 CPU
readback 可以串起来工作。

两 client 32 MiB GLES 路径已经完成性能验证；VMID-scoped vmshm-object 分域和
live-BO 负向 lookup probe 已经证明 client1 不能查询 client0 的 live BO
payload descriptor。仍待继续证明的是更长时间运行、reset/fault recovery、资源
泄漏自由、大内存压力，以及 cross-VM fd/dma-buf/eventfd transport。PRIME 和
syncobj fd/eventfd 相关 ioctl 目前应继续显式拒绝，而不是裸转发 fd 数字。

## 2. 设计原则

这里不能做简单的裸 IOCTL number 转发。原因有四个：

1. DRM/GEM/syncobj handle 是 per-`drm_file` namespace。client VM 的 handle
   和 proxy VM 的真实 handle 必须建立映射。
2. Panthor UAPI 中很多结构包含 user pointer，例如
   `drm_panthor_obj_array::array`。proxy VM 不能直接解引用 client VM userspace
   pointer。
3. Mesa 会通过 `mmap` 直接写 shader、descriptor、command stream、SSBO 等 BO。
   proxy GPU 执行时必须看到同一批物理页。
4. GPU fence/syncobj 在 proxy 真实 Panthor driver 中 signal，client VM 本地
   syncobj 如果不 mirror 到 proxy，就无法正确等待 GPU completion。

因此正确模型应该是：

```text
client userspace
  -> panthor-client DRM frontend
  -> per-open client session / handle translation
  -> control vmshm RPC
  -> panthor-proxy per-client proxy session
  -> real DRM_PANTHOR ioctl path
  -> physical GPU

client mmap BO
  -> client fake mmap offset
  -> vmshm payload shared object
  -> same backing pages visible to proxy
  -> real GPU page table maps these pages
```

一句话概括：

> 控制面翻译 IOCTL 和 handle，数据面用 vmshm 共享 BO，提交面保持 GPU VA 语义
> 但翻译 group/sync/BO，完成面用 proxy syncobj fence 驱动 client wait/readback。

## 3. 必须维护的虚拟状态

每个 client VM 中的 DRM open 都应对应一个 proxy-side Panthor session。这个
session 是所有 handle translation 的根。

| 对象 | client VM 状态 | proxy VM 状态 | 说明 |
| --- | --- | --- | --- |
| session | `drm_file -> session_id` | real Panthor `drm_file` 或等价 proxy session | GEM、VM、syncobj、group handle 都依赖 per-file namespace |
| VM | `client_vm_id` | `proxy_vm_id` | `VM_BIND`、`GROUP_CREATE`、tiler heap 都引用 VM |
| BO | `client_bo_handle`、client fake mmap offset | real GEM handle、vmshm payload object | client CPU mmap 和 proxy GPU page table 必须指向同一份 payload |
| VMA | fake offset -> BO | payload offset / real GEM mapping metadata | proxy fake mmap offset 不能直接给 client 使用 |
| syncobj | `client_sync_handle` | `proxy_sync_handle` | submit wait/signal 必须落在 proxy real syncobj 上 |
| group | `client_group_handle` | `proxy_group_handle` | `GROUP_SUBMIT`、`GROUP_DESTROY` 需要翻译 |
| tiler heap | `client_heap_handle` | `proxy_heap_handle` | real handle 可能编码 VM 信息，跨 VM id 映射时不能裸用 |

建议在 client frontend 中维护：

```text
struct panthor_client_file {
    u64 session_id;
    idr vm_idr;
    idr bo_idr;
    idr syncobj_idr;
    idr group_idr;
    idr heap_idr;
    xarray mmap_offsets;
};
```

proxy 侧维护：

```text
struct panthor_proxy_session {
    u64 session_id;
    struct file *real_drm_file;
    idr vm_map;       // client_vm_id -> proxy_vm_id
    idr bo_map;       // client_bo_handle -> proxy GEM handle + payload object
    idr syncobj_map;  // client_sync_handle -> proxy_sync_handle
    idr group_map;    // client_group_handle -> proxy_group_handle
    idr heap_map;     // client_heap_handle -> proxy_heap_handle
};
```

## 4. Control RPC 与 Payload 分工

control vmshm window 只传小消息和元数据：

- IOCTL type
- session id
- flattened UAPI argument
- translated object arrays
- return code
- returned handles / GPU VA / sizes

payload vmshm window 承载真实 BO 数据：

- shader binary/code buffer
- descriptor/state buffer
- command stream buffer
- SSBO / UBO / storage buffer
- queue/internal state buffer
- scratch buffer
- fence/event page，若后续需要

BO 的数据路径必须避免 submit-time 全量 copy。Mesa 会反复 mmap、写入、提交、
等待、读回。如果每次 submit 才 copy command stream 或 SSBO，不但开销大，还会
引入 dirty tracking、CPU/GPU cache coherence、异步 fence 顺序等复杂问题。

推荐的 POC 方向是：

1. proxy manager 分配或登记一个 payload shared object。
2. client `mmap` 映射到该 payload object 的 client VM alias。
3. proxy 将同一 payload backing pages 创建为真实 Panthor GEM BO 或导入到真实
   Panthor BO。
4. proxy `VM_BIND` 时把这些 pages 映射进真实 GPU page table。

## 5. IOCTL 虚拟化明细

### 5.1 `open("/dev/dri/card0")` / render node

client frontend：

- 创建 client-side `drm_file`。
- 初始化 per-open `panthor_client_file`。
- 通过 RPC 发送 `PANTHOR_VMSHM_MSG_OPEN_SESSION_REQ`。
- 保存 proxy 返回的 `session_id`。

proxy：

- 为该 client VM/open 创建 `panthor_proxy_session`。
- 打开真实 `/dev/dri/card*` 或持有真实 `drm_device`/`drm_file` 等价 session。
- 后续所有 GEM/syncobj/VM/group handle 都归属于这个 session。

关键点：

- 不能多个 client open 共用一个 proxy DRM file，除非显式设计 handle namespace
  隔离层。
- client process 崩溃或 close(fd) 时，proxy 必须兜底释放该 session 下所有对象。

### 5.2 `DRM_IOCTL_VERSION`

client frontend：

- 本地返回 driver name `panthor`。
- version/date/desc 最好与 proxy 真实 driver 对齐，或至少满足 Mesa loader 识别。

proxy：

- 可在启动时查询真实 driver version 并缓存。

关键点：

- Mesa loader 依赖 DRM driver name 选择 DRI driver。client 不能暴露为
  `panthor-client`，否则 userspace 可能加载失败。

### 5.3 `DRM_IOCTL_GET_CAP`

client frontend：

- 必须正确返回 `DRM_CAP_SYNCOBJ = 1`。
- 必须正确返回 `DRM_CAP_SYNCOBJ_TIMELINE = 1`。
- 其他 GEM/render 相关 capability 应与真实 Panthor 保持兼容。

proxy：

- 可查询真实 device capability 并缓存。

关键点：

- `panthor-client` 当前应只暴露已经虚拟化并测试过的 capability。
- `DRM_CAP_SYNCOBJ` 和 `DRM_CAP_SYNCOBJ_TIMELINE` 需要为 `1`，因为 Mesa
  submit/wait 路径依赖 syncobj/timeline。
- `DRM_CAP_PRIME` 当前必须为 `0`。PRIME fd import/export、syncobj fd
  import/export 和 `DRM_IOCTL_SYNCOBJ_EVENTFD` 没有 cross-VM fd/eventfd 协议，
  必须返回 `-EOPNOTSUPP`。
- 不要依赖 DRM core 默认 capability 泄漏；client frontend 应拦截并只声明
  已经有语义保证的能力。

### 5.4 `DRM_IOCTL_PANTHOR_DEV_QUERY`

当前已实现 discovery RPC，可继续沿用。

client frontend：

- 对 `GPU_INFO`、`CSIF_INFO` 查询发 `DEV_QUERY_REQ`。
- 如果用户传 `pointer == NULL`，只返回结构大小。
- 如果用户传 data pointer，client 负责 `copy_to_user()`。

proxy：

- 调用真实 Panthor 侧 `panthor_vmshm_dev_query()`。
- 返回真实 GPU info / CSIF info。

关键点：

- 单 client POC 可以直接暴露真实 capability。
- 多 VM sharing 时可裁剪 `shader_present`、`tiler_present`、core mask、CSG/CS slot
  等能力，形成虚拟资源分区。

### 5.5 `DRM_IOCTL_PANTHOR_VM_CREATE`

client frontend：

- 接收 `struct drm_panthor_vm_create`。
- RPC `VM_CREATE_REQ { session_id, flags, user_va_range }`。
- proxy 成功后返回 `client_vm_id` 和最终 `user_va_range`。
- 建立 `client_vm_id -> proxy_vm_id` 映射。

proxy：

- 在对应 `panthor_proxy_session` 中调用真实 `VM_CREATE` 路径。
- 保存 `proxy_vm_id`。

关键点：

- client 暴露给 Mesa 的 VM id 可以和 proxy VM id 相同，但建议仍然通过映射层，
  方便后续多 client 隔离和 handle remap。
- `user_va_range` 返回值必须回填给 userspace，因为 Mesa 后续分配 GPU VA 会依赖。

### 5.6 `DRM_IOCTL_PANTHOR_BO_CREATE`

client frontend：

- 接收 `struct drm_panthor_bo_create`。
- 如果 `exclusive_vm_id != 0`，翻译为对应 proxy VM id。
- RPC `BO_CREATE_REQ { session_id, size, flags, client_exclusive_vm_id }`。
- 返回 client BO handle 和 page-aligned size。
- 记录 BO metadata：
  - size
  - flags
  - payload object handle
  - proxy GEM handle
  - mmap allowed state

proxy：

- 分配 vmshm payload object。
- 基于该 payload backing 创建或导入真实 Panthor GEM BO。
- 返回 proxy GEM handle、payload descriptor、aligned size。

关键点：

- BO 是 command stream、shader、descriptor、SSBO 的基础对象。
- 如果 BO 使用 `DRM_PANTHOR_BO_NO_MMAP`，client 侧可以不创建 CPU mmap fake offset，
  但仍然需要支持 GPU mapping。
- `exclusive_vm_id` 的语义要保留：该 BO 只能绑定到指定 VM。

### 5.7 `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET`

client frontend：

- 接收 BO handle。
- 查 client BO table。
- 分配 client-local fake mmap offset。
- 返回这个 fake offset。

proxy：

- 不需要把 proxy real fake mmap offset 原样返回给 client。
- 只需确保 payload object 可被 client VM 映射。

关键点：

- DRM fake mmap offset 是 per-DRM-device/per-file 的 VMA namespace。
- proxy offset 属于 proxy DRM fd，client VM 的 `mmap(fd, ..., offset)` 用不了。

### 5.8 `mmap(BO fake offset)`

client frontend：

- 实现 `.mmap`。
- 根据 fake offset 找到 client BO。
- 将对应 vmshm payload shared pages 映射到 client process VMA。
- 按 BO/cache policy 设置 pgprot。

proxy：

- payload object 在 BO 生命周期内必须 pin 住。
- proxy 侧真实 GEM/VM_BIND 使用同一批 backing pages。

关键点：

- 这是数据面正确性的核心。
- Mesa 会用这个 mapping 写 command stream、shader/state 和 SSBO 初值。
- GPU 完成后，Mesa 也会通过这个 mapping 读回 SSBO。

### 5.9 `mmap(DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET)`

Panthor userspace 会 mmap LATEST_FLUSH_ID register page，减少 ioctl 往返。

client frontend：

- 识别 `DRM_PANTHOR_USER_FLUSH_ID_MMIO_OFFSET`。
- 映射一个只读 dummy/virtual flush-id page。

proxy：

- 可选：周期性或按需把真实 latest flush id 同步到 client readable page。

POC 建议：

- 保守返回 `0` 或较低值，让 Mesa 过度 flush。
- 不能返回高于真实状态的值，避免 userspace 误以为 GPU cache 已经 flush 而跳过必要
  flush。

关键点：

- 该 mmap 不是 BO mmap。
- 之前 passthrough 路径中 flush page 初始化错误会导致 mmap fault；虚拟化路径也要
  确保 page 存在且只读。

### 5.10 `DRM_IOCTL_PANTHOR_VM_BIND`

client frontend：

- `copy_from_user()` 解出 `struct drm_panthor_vm_bind`。
- 根据 `ops.count/stride/array` 拷贝 `drm_panthor_vm_bind_op[]`。
- 对每个 op：
  - 翻译 `bo_handle` 为 proxy GEM handle。
  - `bo_offset`、`va`、`size` 原样保留。
  - 拷贝 nested `syncs[]`。
  - 翻译 syncobj handle。
- RPC 发送 flattened bind request。
- 如果同步 VM_BIND 失败，需要按 Panthor UAPI 语义回填 `ops.count` 为失败 op index。

proxy：

- 翻译 client VM id 为 proxy VM id。
- 调真实 Panthor `VM_BIND`。
- 在 real GPU page table 中建立：

```text
GPU VA -> shared BO backing pages
```

关键点：

- `va` 是 GPU virtual address，通常不需要重新分配或翻译，因为 Mesa 后续
  command stream 中写入的也是这个 GPU VA。
- `bo_handle` 和 sync handle 必须翻译。
- `DRM_PANTHOR_VM_BIND_ASYNC` 需要 proxy 侧真实 fence/syncobj 管理。
- MAP/UNMAP/SYNC_ONLY 三类 op 都要支持。

### 5.11 `DRM_IOCTL_SYNCOBJ_CREATE`

client frontend：

- 拦截 DRM core syncobj create。
- 分配 client-visible syncobj handle。
- RPC `SYNCOBJ_CREATE_REQ { session_id, flags }`。
- 保存 `client_sync_handle -> proxy_sync_handle`。

proxy：

- 在真实 DRM file/session 中创建 real syncobj。
- 返回 proxy syncobj handle。

关键点：

- 不能只在 client DRM core 本地创建 syncobj。
- Panthor `GROUP_SUBMIT` 的 sync wait/signal 在 proxy 真实 driver 中发生，因此真实
  syncobj 必须存在于 proxy DRM file namespace。

### 5.12 `DRM_IOCTL_SYNCOBJ_WAIT`

client frontend：

- 拷贝 handles array。
- 翻译每个 client sync handle 为 proxy sync handle。
- timeout 建议从 absolute monotonic 转成 relative timeout 传给 proxy。
- proxy 返回后回填 `first_signaled`。

proxy：

- 将 relative timeout 转换为 proxy VM 自己的 absolute monotonic timeout。
- 调真实 `DRM_IOCTL_SYNCOBJ_WAIT` 或等价内核 API。

关键点：

- UAPI 的 `timeout_nsec` 是绝对 `CLOCK_MONOTONIC`。
- client VM 和 proxy VM 的 monotonic clock 不一定一致，不能裸转发 absolute timeout。
- `timeout=0` 保持 nonblocking。
- `timeout=-1` 保持 infinite。

### 5.13 `DRM_IOCTL_SYNCOBJ_TRANSFER`

client frontend：

- 翻译 `src_handle`、`dst_handle`。
- 原样保留 `src_point`、`dst_point`、flags。
- RPC 到 proxy。

proxy：

- 在真实 syncobj namespace 中执行 transfer。

关键点：

- Mesa dispatch 后常用 timeline transfer。
- timeline point 不能丢，否则后续 `TIMELINE_WAIT` 会等错 fence。

### 5.14 `DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT`

client frontend：

- 拷贝 handles array 和 points array。
- 翻译 handles。
- points 原样保留。
- timeout 按 relative 语义转发。
- 回填 `first_signaled`。

proxy：

- wait 真实 timeline syncobj fence。

关键点：

- 短暂 `-ETIME` 通常只是 Mesa timeout polling，不代表失败，应原样返回。
- `WAIT_AVAILABLE`、`WAIT_FOR_SUBMIT`、`WAIT_ALL` 等 flags 要保持原语义。

### 5.15 `DRM_IOCTL_PANTHOR_GROUP_CREATE`

client frontend：

- 拷贝 `queues[]`。
- 翻译 `vm_id`。
- 可根据虚拟化策略裁剪 core mask 或 priority。
- RPC 到 proxy。
- proxy 成功后返回 client group handle。

proxy：

- 调真实 Panthor `GROUP_CREATE`。
- 保存 `client_group_handle -> proxy_group_handle`。

关键点：

- group 是 CSF execution context / scheduler group。
- 多 VM sharing 时，group/queue 是公平调度、priority、core partition 的主要控制点。

### 5.16 `DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE`

client frontend：

- 翻译 `vm_id`。
- RPC 到 proxy。
- 返回 client heap handle、`tiler_heap_ctx_gpu_va`、
  `first_heap_chunk_gpu_va`。

proxy：

- 在对应 real VM 上创建 tiler heap。
- 保存 heap handle 映射。

关键点：

- Panthor real driver 的 heap handle 可能组合了 VM id 和 heap id。
- 因此跨 client/proxy VM id 映射时不应裸返回 proxy heap handle。
- compute-only workload 也可能在 context init 过程中创建 tiler heap 或 context
  supporting object，不能假设一定没有。

### 5.17 `DRM_IOCTL_PANTHOR_GROUP_SUBMIT`

client frontend：

- 拷贝 `drm_panthor_group_submit`。
- 拷贝 `queue_submits[]`。
- 对每个 queue submit：
  - 翻译 `group_handle`。
  - `queue_index` 原样。
  - `stream_addr` 原样，因为它是 GPU VA。
  - `stream_size` 原样。
  - `latest_flush` 来自 virtual flush-id page，可原样或修正。
  - 拷贝 nested `syncs[]`。
  - 翻译每个 syncobj handle。
- 提交前对相关 shared BO 做必要 CPU cache flush，确保 proxy GPU 可见。
- RPC 到 proxy。

proxy：

- 调真实 Panthor `GROUP_SUBMIT`。
- 真实 driver 创建 job、注册 dependencies、arm fence、push 到 scheduler。
- signal 操作会更新 proxy real syncobj。

关键点：

- `stream_addr` 是 GPU VA，不是 user pointer。它指向此前 `VM_BIND` 映射的 command
  stream BO。
- command stream 内部引用 shader、descriptor、SSBO GPU VA，因此 VM_BIND 阶段必须
  保持同一 GPU VA 语义。
- submit 返回成功只表示 job 入队成功，不表示 GPU 已完成；完成靠 syncobj wait。

### 5.18 dispatch 后 CPU readback

client frontend：

- `SYNCOBJ_TIMELINE_WAIT` 或相关 wait 成功后，需要保证 GPU 写入对 client CPU 可见。
- 对 mapped SSBO 做 invalidate，或使用 coherent/uncached mapping。

proxy：

- GPU fence signal 后，真实 BO backing pages 已被 GPU 写入。

关键点：

- `COMPUTE_CHECK=PASS` 的关键是：GPU 写回 SSBO 和 client CPU readback 读的是同一份
  shared backing pages，并且 cache coherence 处理正确。
- 如果 submit/fence 都成功但读回仍是 0 或旧值，优先检查 payload backing 和 cache
  maintenance。

### 5.19 cleanup: `VM_BIND` unmap

client frontend：

- cleanup 阶段多次 `VM_BIND` 通常表示 unmap。
- 翻译 VM id、sync handle。
- 对 unmap op，`bo_handle` 应为 0，按 UAPI 保持。

proxy：

- 调真实 VM_BIND unmap，解除 GPU VA -> BO pages 映射。

关键点：

- 即使 VM 后续要 destroy，也应尽量按 userspace 请求执行 unmap，保持 driver 状态和
  Mesa 预期一致。

### 5.20 `DRM_IOCTL_GEM_CLOSE`

client frontend：

- 拦截 GEM close。
- 删除 client BO handle。
- RPC 到 proxy close real GEM handle。
- 释放 client fake mmap offset 和 payload 引用。

proxy：

- 对真实 GEM handle 执行 close/drop reference。
- 当最后引用释放时，释放 payload object。

关键点：

- `DRM_IOCTL_GEM_CLOSE` 是 DRM core ioctl，不是 Panthor private ioctl。
- 如果不虚拟化，proxy GEM BO 会泄漏。

### 5.21 `DRM_IOCTL_SYNCOBJ_DESTROY`

client frontend：

- 删除 client sync handle。
- RPC destroy proxy syncobj。

proxy：

- destroy/drop real syncobj handle。

关键点：

- 与 GEM close 类似，syncobj 属于 DRM core UAPI，但 Panthor submit 强依赖它。

### 5.22 `GROUP_DESTROY` / `TILER_HEAP_DESTROY` / `VM_DESTROY` / `close(fd)`

client frontend：

- 翻译 handle 后 RPC destroy。
- close(fd) 时按反向依赖关系清理残留对象：

```text
outstanding submit/fence
  -> group / tiler heap
  -> VM_BIND unmap if needed
  -> BO/GEM
  -> syncobj
  -> VM
  -> session
```

proxy：

- 对真实 Panthor session 执行同样 cleanup。
- 如果 client 崩溃，proxy session release 必须兜底释放所有真实 GPU 资源。

关键点：

- cleanup 不能只依赖 userspace 完整执行。VM 崩溃、进程 kill、RPC 中断都必须能回收。

## 6. 推荐新增 Panthor vmshm 消息

现有：

```text
PANTHOR_VMSHM_MSG_DEV_QUERY_REQ
PANTHOR_VMSHM_MSG_DEV_QUERY_RSP
```

建议按对象生命周期扩展：

```text
PANTHOR_VMSHM_MSG_OPEN_SESSION_REQ/RSP
PANTHOR_VMSHM_MSG_CLOSE_SESSION_REQ/RSP

PANTHOR_VMSHM_MSG_VM_CREATE_REQ/RSP
PANTHOR_VMSHM_MSG_VM_DESTROY_REQ/RSP
PANTHOR_VMSHM_MSG_VM_GET_STATE_REQ/RSP
PANTHOR_VMSHM_MSG_VM_BIND_REQ/RSP

PANTHOR_VMSHM_MSG_BO_CREATE_REQ/RSP
PANTHOR_VMSHM_MSG_BO_MMAP_OFFSET_REQ/RSP
PANTHOR_VMSHM_MSG_GEM_CLOSE_REQ/RSP

PANTHOR_VMSHM_MSG_SYNCOBJ_CREATE_REQ/RSP
PANTHOR_VMSHM_MSG_SYNCOBJ_DESTROY_REQ/RSP
PANTHOR_VMSHM_MSG_SYNCOBJ_WAIT_REQ/RSP
PANTHOR_VMSHM_MSG_SYNCOBJ_TIMELINE_WAIT_REQ/RSP
PANTHOR_VMSHM_MSG_SYNCOBJ_TRANSFER_REQ/RSP
PANTHOR_VMSHM_MSG_SYNCOBJ_RESET_REQ/RSP
PANTHOR_VMSHM_MSG_SYNCOBJ_SIGNAL_REQ/RSP

PANTHOR_VMSHM_MSG_GROUP_CREATE_REQ/RSP
PANTHOR_VMSHM_MSG_GROUP_DESTROY_REQ/RSP
PANTHOR_VMSHM_MSG_GROUP_GET_STATE_REQ/RSP
PANTHOR_VMSHM_MSG_GROUP_SUBMIT_REQ/RSP

PANTHOR_VMSHM_MSG_TILER_HEAP_CREATE_REQ/RSP
PANTHOR_VMSHM_MSG_TILER_HEAP_DESTROY_REQ/RSP
```

对于 `VM_BIND` 和 `GROUP_SUBMIT`，建议使用 flattened payload，而不是嵌套 user
pointer：

```text
VM_BIND_REQ
  session_id
  client_vm_id
  flags
  op_count
  ops[]:
    flags
    client_bo_handle
    bo_offset
    va
    size
    sync_first
    sync_count
  syncs[]:
    flags
    client_sync_handle
    timeline_value
```

```text
GROUP_SUBMIT_REQ
  session_id
  client_group_handle
  qsubmit_count
  qsubmits[]:
    queue_index
    stream_size
    stream_addr
    latest_flush
    sync_first
    sync_count
  syncs[]:
    flags
    client_sync_handle
    timeline_value
```

proxy 收到后再把 client handles 翻译成 proxy handles，组装成真实 Panthor UAPI
结构或调用等价内核 helper。

## 7. Cache 与内存一致性

虚拟化 BO 后，至少有三方会访问同一 backing pages：

- client userspace CPU：写 command stream、shader、descriptor、SSBO 初值，读 SSBO
  结果。
- proxy VM/real Panthor driver：建立 GEM/VM_BIND/submit。
- physical GPU：读 command stream 和资源，写 SSBO。

因此必须定义 cache maintenance 策略。

POC 可选方案：

1. 对 client BO mmap 使用 uncached 或 write-combine mapping。
2. 在 `GROUP_SUBMIT` 前对所有可能 dirty 的 shared BO 粗粒度 flush。
3. 在 wait 成功后对 GPU writeable BO 粗粒度 invalidate。

更完整方案：

- 在 client BO table 中记录 CPU map/write 状态。
- 在 VM_BIND 中记录 BO 是否 GPU writable。
- 在 GROUP_SUBMIT 中根据 referenced BO 集合做精细 flush。
- 在 fence completion 后对被 signal fence 覆盖的 writable BO 做 invalidate。

如果 cache 没处理好，典型现象是：

```text
GROUP_SUBMIT returns 0
SYNCOBJ_TIMELINE_WAIT succeeds
CPU readback mismatch, got old value or zero
```

这说明调度/fence 可能已经成功，但数据面没有真正 coherent。

## 8. 实施顺序建议

### 阶段 1：让 Mesa 识别 client Panthor device

- `DRM_IOCTL_VERSION` 返回 `panthor`。
- `DRM_IOCTL_GET_CAP` 返回 syncobj/timeline capability。
- client driver features 补齐 `DRIVER_GEM`、`DRIVER_SYNCOBJ`、
  `DRIVER_SYNCOBJ_TIMELINE`。
- flush-id page mmap 返回有效只读 page。

目标：

```text
Mesa loader 能打开 client DRM node，并继续进入 Panthor userspace path。
```

### 阶段 2：session、VM、BO、mmap

- 实现 `OPEN_SESSION/CLOSE_SESSION`。
- 实现 `VM_CREATE/DESTROY`。
- 实现 `BO_CREATE`。
- 实现 client fake `BO_MMAP_OFFSET`。
- 实现 `.mmap` 到 vmshm payload object。
- 实现 `GEM_CLOSE`。

目标：

```text
client userspace 能创建 BO、mmap BO、写入 payload，proxy 能看到同一份内容。
```

### 阶段 3：syncobj mirror

- 实现 `SYNCOBJ_CREATE/DESTROY`。
- 实现 `SYNCOBJ_WAIT`。
- 实现 `SYNCOBJ_TRANSFER`。
- 实现 `SYNCOBJ_TIMELINE_WAIT`。
- 保持 timeout、ETIME、first_signaled 语义。

目标：

```text
Mesa 的 fence management 不再卡在 client/proxy namespace 不一致上。
```

### 阶段 4：VM_BIND

- 实现 `VM_BIND` flattened RPC。
- 支持 MAP/UNMAP/SYNC_ONLY。
- 支持 sync 和 async bind。
- 翻译 BO/sync handles。
- proxy 真实 GPU page table 映射 shared BO backing pages。

目标：

```text
GPU VA -> shared BO pages 映射正确。
```

### 阶段 5：group、tiler heap、submit

- 实现 `GROUP_CREATE/DESTROY/GET_STATE`。
- 实现 `TILER_HEAP_CREATE/DESTROY`。
- 实现 `GROUP_SUBMIT` flattened RPC。
- 提交前处理 CPU cache flush。
- wait 成功后处理 readback invalidate。

目标：

```text
eglCreateContext/eglMakeCurrent 附近的 internal submit 能完成，
glDispatchCompute 的 GROUP_SUBMIT 能执行并 signal fence。
```

### 阶段 6：多 VM sharing 能力

- resource quota。
- core mask partition。
- group priority policy。
- per-client memory accounting。
- GPU fault isolation。
- reset isolation。
- eventfd/async notification。
- tracepoint 和 debugfs 状态导出。

目标：

```text
从单 client compute smoke 走向多 client GPU sharing。
```

## 9. 验证路径

推荐验证顺序：

1. `DRM_IOCTL_PANTHOR_DEV_QUERY` selftest 仍通过。
2. raw ioctl demo：

```text
open
DEV_QUERY
VM_CREATE
BO_CREATE
BO_MMAP_OFFSET
mmap write/read
VM_BIND
GROUP_CREATE
GROUP_SUBMIT empty job
syncobj wait
cleanup
```

3. Mesa `eglinfo -B` 能识别 `Mali-G610 (Panfrost)`，不是 `llvmpipe`。
4. `gles-compute-smoke` 输出：

```text
STAGE=dispatch
STAGE=map-result
COMPUTE_CHECK=PASS count=64 formula=x*3+7
```

5. trace 检查：

```text
DRM_IOCTL_PANTHOR_VM_CREATE
DRM_IOCTL_PANTHOR_BO_CREATE
DRM_IOCTL_PANTHOR_VM_BIND
DRM_IOCTL_SYNCOBJ_CREATE
DRM_IOCTL_PANTHOR_GROUP_CREATE
DRM_IOCTL_PANTHOR_GROUP_SUBMIT
DRM_IOCTL_SYNCOBJ_TRANSFER
DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT
DRM_IOCTL_PANTHOR_GROUP_DESTROY
DRM_IOCTL_GEM_CLOSE
DRM_IOCTL_PANTHOR_VM_DESTROY
```

6. proxy 侧检查：

- session 是否释放。
- GEM BO 是否释放。
- syncobj 是否释放。
- VM/group/heap 是否释放。
- payload object 是否无泄漏。

## 10. 风险点速查

| 风险 | 典型症状 | 优先检查 |
| --- | --- | --- |
| driver name 不对 | Mesa 不加载 Panthor/Panfrost userspace driver | `DRM_IOCTL_VERSION` |
| syncobj cap 不对 | Mesa 初始化失败或 fallback | `GET_CAP` / driver_features |
| proxy offset 误返回 client | mmap 失败或 mmap 到错误对象 | `BO_MMAP_OFFSET` fake offset |
| user pointer 裸转发 | proxy `-EFAULT` 或 kernel fault | `obj_array` flatten |
| BO backing 不共享 | submit 成功但 GPU 读不到 command/data | payload object / GEM backing |
| cache 不一致 | fence 成功但 readback 旧值 | submit flush / wait invalidate |
| syncobj 本地化 | submit signal 后 client wait 永远等不到 | syncobj handle mirror |
| timeout 裸转发 absolute time | wait 过早超时或等待过久 | relative timeout conversion |
| heap handle 裸返回 | destroy heap 失败或 VM id 不匹配 | heap handle mapping |
| close 清理不完整 | proxy GEM/VM/group 泄漏 | session release cleanup |

## 11. 最小可运行 POC 范围

如果目标只是让当前 `gles-compute-smoke` 在 client VM 通过 proxy VM 跑通，最小集合是：

- `VERSION`
- `GET_CAP`
- `DEV_QUERY`
- `VM_CREATE`
- `BO_CREATE`
- `BO_MMAP_OFFSET`
- `.mmap` BO
- `.mmap` flush-id page
- `VM_BIND`
- `SYNCOBJ_CREATE`
- `SYNCOBJ_WAIT`
- `SYNCOBJ_TRANSFER`
- `SYNCOBJ_TIMELINE_WAIT`
- `GROUP_CREATE`
- `TILER_HEAP_CREATE`
- `GROUP_SUBMIT`
- `TILER_HEAP_DESTROY`
- `GROUP_DESTROY`
- `SYNCOBJ_DESTROY`
- `GEM_CLOSE`
- `VM_DESTROY`
- `close(fd)` session cleanup

其中真正决定 compute 是否能 `COMPUTE_CHECK=PASS` 的关键链路是：

```text
BO_CREATE creates shared backing
  -> client mmap writes SSBO / command / shader / descriptor
  -> VM_BIND maps same backing to GPU VA
  -> GROUP_SUBMIT submits command stream using those GPU VAs
  -> proxy real syncobj receives GPU fence
  -> client TIMELINE_WAIT observes proxy fence completion
  -> client mmap readback sees GPU writes
```

只要这条链路中任意一环变成 copy-only、local-only 或 handle namespace 不一致，
Mesa compute 都可能表现为初始化失败、submit 失败、wait 超时，或者最终 readback
mismatch。
