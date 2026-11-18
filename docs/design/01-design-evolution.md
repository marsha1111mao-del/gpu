# 设计演进

## 1. 原生与设备直通

Host 原生 Panthor 提供历史性能对照。直通把设备交给 Guest，由 Guest 直接承担驱动和工作负载。扩展实验中的 Realm 分时直通允许多个 Realm 常驻，每次一个 Realm 持有整台 GPU。短请求需要把排队、设备交接与实际执行分别计量。[三方对照](05-results.md)

## 2. 普通 VM Proxy/Client

早期把 DRM render node 放在 Client，把设备访问和对象维护放在 Proxy。Client 经 vmshm 发出请求。应用关键路径多了传输、排队、依赖和完成反馈。原型曾用共享池与命令快照传输业务数据，通过融合、延迟复制与异步完成降低传输开销。这个阶段建立了多 Client 对象生命周期、fence 回调和 IRQ 的测量方法。[普通 VM 架构记录](../shared/GPU_CLIENTPROXY_ARCHITECTURE_GUIDE_20261022.md)

## 3. Realm 私有 BO

公开冻结的 FU/FT 阶段把 BO backing 留在 Client 私有内存。Proxy 维护功能对象并发出调度请求。RMM 管理实际 GPU 页表、命令授权及可信完成。设备仍可访问的页须保留引用，退休时核对停止、撤权和可见性。

性能关注点由业务数据搬运移向页表与域管理、命令捕获、设备完成观测及跨 Realm 唤醒。1170 版 Guest 源码移除了旧 vmshm manager，受保护控制队列继续服务私有路径。[FU/FT 冻结记录](../shared/GIT_BASELINES_20261102.md) · [私有 BO 逐轮实施记录](../shared/GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md) · [端到端实现](02-implementation.md)

## 4. 规范化与发布

迭代覆盖受保护域复用、批内阶段合并、等待重叠与 Client 本地完成通知。第一阶段规范化完整 720p 得 1163 分。第二阶段重建匹配的 RMM、Client 和 Proxy 后得 1170 分，并通过原验收检查。实验保留条件和未解决安全范围分别记录。[性能优化](04-optimization.md) · [第二阶段验收](../shared/GPU_CODE_NORMALIZATION_AND_CLEANUP_20261114.md)

| 方案 | 执行模型 | 实验中的信任与资源边界 |
| --- | --- | --- |
| Realm 私有共享 | 多 Client，经 Proxy 编排与 RMM 授权操作物理 GPU | protected hVHE，保护链含私有 backing、授权、可信完成与回收 |
| Realm 分时直通 | 整设备独占租约，同一时段一个 Realm 持有 | 分开统计排队、申请、加载、卸载和归还 |
| virtio-gpu | Guest 发 virtio 请求，Host QEMU/virglrenderer 使用实际 Mali GPU | 实验使用独立 nVHE，GPU 后端消耗 Host CPU 与内存，模型测试使用通过硬件检查的 Venus |
