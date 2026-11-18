# 端到端实现

~~~mermaid
sequenceDiagram
    participant C as Client DRM
    participant P as Proxy 服务
    participant R as RMM
    participant G as Mali GPU
    C->>P: 管理功能对象
    C->>R: 注册私有 backing、映射与任务
    C->>P: 提交控制请求
    P->>R: 受限任务请求
    R->>G: 检查、配置并发布
    G-->>R: 设备进度与 IRQ
    P->>R: 查询可信完成
    P-->>C: 回复任务状态
    C-->>C: 传播结果并唤醒本地 fence
~~~

## 对象和控制队列

Client DRM 管理 GEM handle、GPUVM、Group、堆和 syncobj，保留 Linux 用户态接口。Client BO 数据留在原 Realm，Proxy 对象表负责功能标识、请求编排和资源配额。关闭会话期间必须等相关异步请求与设备引用退出。新会话的授权与其当前对象绑定。

传输使用固定队列几何、窗口相对偏移及本地拥有的游标。接收方对共享描述符做快照和边界检查。回复按序号与预期类型定位 waiter，超时撤销和完成回复共用 waiter 锁。IRQ 与队列可读状态触发检查。[功能与保护入口](../shared/GPU_CODE_FUNCTION_AND_SECURITY_INVENTORY_20261114.md)

## 映射和执行

RMM 校验实际物理页归属、映射范围及代次，捕获每次请求的任务输入和映射依赖。执行域、实际 GPU 页表及固件状态满足约束后才可发布和启动。已授权的域及映射证明只在严格限定的生命周期内复用。引用、设备可见性和撤权按任务进入最终状态处理。

## 完成、故障与销毁

可信 IRQ 通知触发检查，设备进度、错误历史、所有权和完成状态决定 fence 结果。本地有界 IRQ-work 沿用 dma-fence 的依赖与错误语义。live backing 要等可信停止、撤权和引用归零才可释放。实体故障中出现过引用保留以及其他 Client 提交失败。[安全边界与回归](03-security.md)

| 责任 | 代码目录 |
| --- | --- |
| Client 用户 ABI、对象和提交 | Linux-Guest-GPU/drivers/gpu/drm/panthor-client 与 drivers/char/realm_gpu.c |
| Proxy 对象和功能处理 | Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy |
| 控制通信 | Linux-Guest-GPU/drivers/char 下的 client_vmshm_comm、proxy_vmshm_comm 和 realm_xshm.c |
| 可信状态机与平台固件 | opencca/tf-rmm/runtime 与 opencca/shared |
