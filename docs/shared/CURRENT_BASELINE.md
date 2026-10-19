# 当前开发基线：RMM-only / P42 + BO 容量修复 + GPUVM同步列表

更新：2026-10-19。**原冻结 GPUVM 待同步映射列表组合：完整720p1171 / 1170，对同期基线1162 / 1160，均值+9.5分/+0.82%；该组合双Client各17项API、实际计算、权限及IRQ验收通过。** 六方向共八候选，其余无新增收益证据已撤回，见[优化实验](SAFE_PERFORMANCE_OPTIMIZATION_20261018.md)。memfd已退役；旧发布manifest不包含该阶段本地三文件补丁，冻结包为`build/safe-optimization-20261018/final/`。该优化阶段的无收益镜像、临时执行代码和重复冻结目录已清理，仅保留列表三文件补丁；当前源码另含下述安全服务开发改动，对比证据见优化实验中的清理复核。

日常开发以本页、当前源码和对应冻结输入为准。普通 VM/memfd 发布包和历史论文方案不代表当前 Realm 实现；固定 Git 发布载荷也不会自动包含本地未提交改动。

场景二的简明实现清单见[当前实现状态](SCENARIO2_IMPLEMENTATION_STATUS.md)。Notion「假设场景2实现」按用户要求仅维护已实现、未实现/部分实现两区；历史开发与失败证据在仓库原报告保留。

**2026-10-20三端清理完成：** 移除35,360个废弃文件和332个空目录；控制机build含迁回归档后净减5.55GiB，Pi/RK根分区可用分别增加1.00/1.75GiB。运行源码、当前构建树、冻结/回退/恢复输入与失败证据保留，RK仍为#31/pmthor/CPU0–1/300MHz。两次独占维护rc0；仅维护验证，无新增GPU回归或性能测量。命令与清单见[清理记录](WORKSPACE_ARTIFACT_CLEANUP_20261020.md)。

**2026-10-20平台假设与完成状态：** 按用户确认，可信页表/控制内存、IOMMU关键配置、工作态任务MMIO及未授权CPU/DMA访问的物理保护，均假设目标平台已提供，不列为当前模拟工程待开发任务。**统一安全IOMMU服务、Host与其他IOMMU设备的托管映射控制均已实现并完成当前范围验收。** 软件owner/generation、授权/映射互斥、撤销及回收仍由代码执行；不引入EL2接管普通VM页表。历史绕过FAIL与NOT_RUN原样保留，其他软件/发布任务独立跟踪。详见[平台假设与完成范围](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)。本次纯文档整理，未改运行代码，无新增性能测量。

**板端当前：Host #31 / protected hVHE / RMM timer v6。选定模拟主流程验收通过。** 按用户要求，以硬件模拟行为、总体设计一致和主流程可运行为准；完整物理对抗隔离不在本轮验收范围，也不作完成声明。既有完整720p **1159**，相对#29的1152为 **+7/+0.61%**；相同33场景、256MiB、null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频。Host stage-2/异常处理组合变化，单轮仅记录组合观测；正确性、Host/Guest健康与资源恢复通过。本轮失败复核未改Host/RMM/Guest内核运行代码，无新增性能测量。Host内核及`/dev/mem`直接访问GPU MMIO已分别验证拒绝，第二Realm映射拒绝通过；普通VM物理写入仍 **FAIL_BYPASS_DETECTED**，作为物理隔离边界保留。按用户方向采用RMM资源归属，不引入EL2接管普通VM页表。当前双Client各17项API及实际计算、Host managed-IOMMU22项、Guest RSI17项、Guest设备授权14项、GPU backing3项及空闲电源循环独立通过，Host/Guest生命周期健康。Group fence本轮通过、历史间歇超时仍保留观察；PL330旧绕过和未执行项不删除。命令、退出码、run-id、日志及两项测试入口/异常清理修正见[失败项状态复核](GPU_FAILURE_STATUS_AUDIT_20261019.md)；既有性能与物理边界见[Host MMIO与资源归属验收](GPU_HOST_MMIO_ENFORCEMENT_20261019.md)；不替换原冻结1171/1170。

**上一受保护Host/Realm运行兼容候选（历史保留）。** Host `6.12.0-opencca-pmthor-opp3 #29`，RMM timer v6；protected hVHE、Realm能力1、pmthor正常。独立完整720p **1152**，对#27的1168为 **−16/−1.37%**；同默认池/负载/频率，Host/RMM/protected与CPU初始化/timer同时变化，只记录组合差异。33场景、validation、Host/Guest内核健康、Realm退出[0,0]及CPU0–1/300MHz恢复通过；其他功能不继承#27结果。该候选Host物理MMIO强制保护未实现，原绕过记录保留，整体 **PARTIAL / INCOMPLETE**。输入SHA、全部新增失败及命令见[受保护Realm验证](GPU_PROTECTED_REALM_VALIDATION_20261019.md)；不替换原冻结1171/1170。

**上一托管 IOMMU 故障中断候选（历史保留）。** Host `6.12.0-opencca-pmthor-opp3 #27`（Image `16c6d4832169d03317ee1274f52fb313d2cf86b1487698258b60c3ac9e9df82c`），RMM ELF `208110a40dbea82b3c7c5049f2867e16c8df03a9694d3ffde7d079be5a0f7b78`。managed IRQ的缓存清理/页故障结束/清中断迁入RMM；Host/Guest共用授权、真实root检查与失败隔离。八项独立功能运行退出0：完整720p **1168**（对#26的1173为 **−5/−0.43%**，对冻结均值1170.5为 **−2.5/−0.21%**；同默认池/频率/负载，Host与RMM同时变化，单轮只记录组合观测），Guest设备14/14、RSI17/17、Host22/22、双Client各17项API/计算及电源循环通过，GPU租约峰值5559、最终GPU/DMA均0。#27独立物理写负例仍退出2，0→1→0复现Host直接修改任务IRQ mask；整体仍 **PARTIAL / INCOMPLETE**。实体IOMMU故障注入、活跃任务断电、完整攻击/冻结矩阵未验收；不替换原冻结1171/1170。见[本轮验收与清理](GPU_IOMMU_FAULT_VALIDATION_20261019.md)。

**上一设备授权与 GPU 电源顺序修复候选（历史保留）。** Host `6.12.0-opencca-pmthor-opp3 #26`，Image `ce66d275ba9509104dfbe38ac01c7785d42ac27889d7e460d37132a36b688be2`；RMM device-grant，ELF `7cc379993f609720a947bc5d4658c539e46f42f1352da1082e5534cd35591d13`。最终七项独立回归退出0，完整720p **1173**（对原冻结均值1170.5为 **+2.5分 / +0.21%**），双Client各17项API/计算、内核和资源恢复通过；RMM GPU租约峰值5511、最终GPU/DMA均0。Guest真实codec IOMMU授权/供电生命周期9项、RSI15项、Host22项通过；空闲GPU电源域on/off/on及恢复后KVM11项通过。见[当前设备授权与电源验收](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)。Host管理板级供电/时钟/合法OPP，任务MMIO由指定Proxy控制，复位/撤销/回收经RMM。Host直接物理访问的硬件强制保护、完整攻击/故障与冻结矩阵仍未完成，整体安全状态为PARTIAL / INCOMPLETE；单轮分差不证明稳定提分，不替换原冻结基线。

**后续物理访问负例与负载专项：** 同一Host #26 / RMM device-grant，Host在测试Realm持有GPU MMIO时仍可经物理映射修改IRQ mask，`host-mmio-physical-audit-20261019-a/b`均退出2，安全结论为 **FAIL_BYPASS_DETECTED**；11项ABI检查及恢复通过不能抵消此失败。另行`managed-iommu-live-device-grant-20261019-c`退出0、28/28，补齐活跃GPU页映射拒绝/SG回滚专项；完整720p为1171（对独立性能轮1173为−2/−0.17%，同时有探针与UART，条件不同，不替换原测量）。仅改验证代码，未改部署运行代码；详见[追加验收与边界](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)。整体安全仍未完成。

**上一阶段统一安全服务候选（历史保留）：** Host #23 / RMM page-reclaim 完整720p **1167**，对原冻结均值−3.5分/−0.30%；七项回归、双Client各17项API/计算与租约归零通过，峰值4401。见[上一阶段验收与三端清理](SECURE_SERVICES_VALIDATION_20261019.md)。随后新增空闲电源循环发现平台detach先于devres复位的竞态，三次失败及诊断偶然PASS均保留；该问题由当前候选修复。

**历史 DMA 防护候选：** 新增 Host/RMM 映射准入检查，独立完整 720p 为 1169，双 Client 功能验收通过。
该阶段用户确认的验收范围为 **IOMMU 映射入口的物理页互斥**，见
[IOMMU 映射防火墙](IOMMU_MAPPING_FIREWALL_20261018.md)。基础 15 项与 GPU 负载期间扩展 21 项全部通过，
本轮完整 720p 仍为 1169，正确性、内核健康及资源恢复通过；NPU 未启用，使用 codec 的真实 IOMMU domain 验证映射入口。
先前直接 PTE 和无 IOMMU PL330 的绕过记录作为扩展边界保留，后者不纳入本轮验收。
本页 1171/1170 来自原 Host/RMM 组合，不得将候选视为已冻结安全基线。
部署输入、测试与回退记录见 [DMA 防护开发报告](GPU_DMA_GUARD_IMPLEMENTATION_20261018.md)。

**2026-10-19 PM owner 生命周期候选：** 修复未创建 Realm 的 RTT 路径和 Proxy GPU MMIO owner 先于 PM session 释放问题。最终 Host/RMM 已部署并连续通过两轮 KVM/MMIO/PM 探针、双 Client compute teardown、compute 后复用探针；完整 720p glmark 为 **1164**（对照 1171/1170 均值 -6.5 分 / -0.56%），门槛 1000、正确性、内核健康与资源恢复通过。完整 API/多 Client/冻结回归未重跑，不继承历史 PASS。见 [PM owner 生命周期修复](GPU_PM_OWNER_LIFECYCLE_FIX_20261019.md)。

**后续架构与负例验证：** 同一#27临时添加`kvm_arm.mode=protected`可启动且所列RMI电源调用通过，但Realm能力从1变0，集成为FAIL；原配置已恢复。新增Host内核`ioremap`负例也读回IRQ mask的0→1→0，退出2，原`/dev/mem`负例独立复验仍失败；各自11项授权检查、恢复和内核健康通过不能抵消绕过。未改Host/RMM/Guest运行代码、无新增性能测量，原冻结与全部状态项保留。见[受保护EL2兼容性与内核别名负例](GPU_PROTECTED_EL2_COMPATIBILITY_20261019.md)。

## 阅读入口

| 内容 | 文档 |
| --- | --- |
| 环境、设备角色、构建与测试流程 | [主手册](../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md) |
| 六方向优化、同期对照及最终验收 | [优化实验](SAFE_PERFORMANCE_OPTIMIZATION_20261018.md) |
| 当前统一IOMMU、GPU可信复位/回收与三端清理 | [开发验收](SECURE_SERVICES_VALIDATION_20261019.md) |
| Guest设备授权、Host受限电源与工作态MMIO、电源顺序修复 | [当前设备授权验收](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md) |
| PM owner teardown 修复与2026-10-19候选验收 | [生命周期修复](GPU_PM_OWNER_LIFECYCLE_FIX_20261019.md) |
| 当前 Native / ProxyClient 全部有效对照 | [性能汇总](GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md) |
| 大 BO 分配、512 MiB 配置及最新验收 | [BO 修复报告](GPU_BO_CAPACITY_FIX_20261018.md) |
| 资源、租约与产物管理 | [开发规范](../start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md) |
| 多 Realm 通信、GPU 转发与执行的代码和原理 | [代码讲解](REALM_COMMUNICATION_AND_GPU_EXECUTION_CODE_WALKTHROUGH_20261018.md) |
| RMM 共享接口与测试用法 | [Realm 工具说明](../../GPU-SFTP/tests/realm-xshm/README.md) |
| 基线 Git 同步、组件版本与发布检查 | [同步记录](GIT_BASELINE_PUBLICATION_20261018.md) |
| 历史失败、逐轮优化与论文调研 | [归档索引](../archive/20261018/README.md) |

## 已实现的数据路径

```mermaid
flowchart LR
    C[Client Realm / DRM 前端] -->|注册计划 / 执行引用| Q[RMM 授权共享队列和 BO 池]
    Q --> P[Proxy Realm / 资源校验与执行计划]
    P --> G[原生 Panthor / GPU]
    G --> F[真实原生 fence]
    F -->|完成 cookie| C
    C <-->|RMM 持久事件 / 可信 IRQ127| P
```

- **提交：** 资源注册与可复用执行计划代替直接 GROUP_SUBMIT RPC；Proxy 按会话校验引用，资源生命周期变化使计划失效。不是 GPU shadow task 或跨 Group 页表隔离。
- **共享：** RMM 校验 Realm 端点、通道和授权范围，建立长期池，支持分段 attach/detach/revoke；队列身份来自 RMM。描述符和消息先复制到私有内存再校验，队列几何及本端进度保存在私有状态。
- **通知：** RMM 保存 pending/ack/armed 状态并控制 IRQ127；hard IRQ 只调度接收工作，worker 排空后 ACK+ARM 并重查。中断只提示检查队列，不是访问授权或 GPU 完成证明。
- **缓存：** tiler heap 初始化后按 GPU 所有权交接，避免逐提交重复同步；固件输出按实际读取范围维护。保留真实 DMA 缓存维护及发布顺序，不能以 CPU 屏障代替。
- **完成：** 原生完整 fence/chain 成功后发布精确 cookie；Client 在对象、cookie、epoch 和无后续写入等条件满足时本地确认完成，否则回退真实等待。
- **回收：** 私有快照最后引用释放后有界排队，下一次新导出附带回收；不复用旧快照，不在含糊的传输失败后重放执行。
- **BO：** GPU 连续对象按页分配 extent，沿用 pin、引用、撤销和释放清零；大负载显式启用512 MiB池，默认仍为256 MiB。

## 代码入口

| 职责 | 当前路径 |
| --- | --- |
| Client 前端、完成凭据和快照回收 | [panthor_client_drv.c](../../Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c) |
| Proxy 会话、计划与原生后端 | [panthor_proxy_drv.c](../../Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c) |
| 通信与对象协议 | [panthor_vmshm.h](../../Linux-Guest-GPU/include/linux/panthor_vmshm.h)、[vmshm_comm_protocol.h](../../Linux-Guest-GPU/include/linux/vmshm_comm_protocol.h) |
| GPU BO 分配器 | [proxy_vmshm_manager.c](../../Linux-Guest-GPU/drivers/char/proxy_vmshm_manager/proxy_vmshm_manager.c) |
| Realm Guest 共享前端 | [realm_xshm.c](../../Linux-Guest-GPU/drivers/char/realm_xshm.c) |
| RMM 端点、共享和 IRQ 策略 | [runtime/core](../../opencca/tf-rmm/runtime/core/) 中的 xshm_endpoint / xshm_memory / xshm_service / xshm_irq |
| 成套构建配置 | [configs/performance](../../configs/performance/README.md) |
| 受租约保护的测试入口 | [run-realm-xshm.py](../../scripts/run/run-realm-xshm.py)、[lab-run.py](../../scripts/maintenance/lab-run.py) |

Host原生与单VM直通对照入口保留。普通VM的memfd/irqfd共享入口、Host broker和外部memslot集成已删除；vmshm名称仍用于当前RMM队列/对象协议，不代表继续使用memfd。

## 测量基线与边界

| 项目 | 最新有效结果 | 说明 |
| --- | --- | --- |
| 原冻结完整720p | 1171 / 1170，Native历史参考1437 | GPUVM同步列表；同期对照1162 / 1160 → 均值+9.5/+0.82%；默认256 MiB，Native本轮未重测 |
| 当前Host MMIO候选720p | 1159 | 对#29的1152为+7/+0.61%；同timer v6、默认池/频率/负载，Host stage-2/异常处理组合变化，单轮观测；Host直接访问拒绝通过，普通VM绕过FAIL；不替换冻结基线 |
| 上一IOMMU故障中断候选720p（历史） | 1168 | 对上一#26的1173为−5/−0.43%，对原冻结均值1170.5为−2.5/−0.21%；Host/RMM组合变化，单轮观测；功能通过，物理MMIO保护FAIL，不替换冻结基线 |
| 上一设备授权候选720p（历史） | 1173 | 对原冻结均值+2.5/+0.21%；相对上一阶段1167为+6/+0.51%，中间Host #23/device-grant为1170；选定回归通过，未替换原冻结基线 |
| 完整1080p | 901，Native997 | 显式512 MiB；旧失败分数无效 |
| ResNet50 | 1463.96ms，Native1162.99ms | 显式512 MiB；随机权重性能模型 |
| P42重复性能验证 | 1159 / 1163 | 修复前同镜像两轮，历史参考 |
| BO修复阶段33项对照条目 | 21项修复后实测，12项P42参考 | 另列P42双Client性能；不称当前32/32 |

列表版本新增两轮完整720p和双Client功能验收，范围见优化实验；未重测1080p、ResNet50等性能。清理前BO修复组合及memfd退役组合的历史验收分别保留，不继承为新代码全项PASS。

glmark为离屏null-noop / finish、完整33场景；validation为26成功、1已知数值例外、6无判据。GPU请求600MHz、实际594MHz；未固定CPU恒定频率。不能把不同资源配置和历史批次解释为单变量收益。

RK3588/OpenCCA的GPT/GPC仍有模拟边界；本基线未实现GPU跨Group shadow页表隔离、完整远程证明、多vCPU验收或长期压力证明。Host仍可拒绝调度。历史失败继续保留，不从旧PASS推断新版本全通过。

## 冻结输入与复现

**原冻结列表组合：** `build/safe-optimization-20261018/final/`，与两轮1171/1170的输入逐字节相同，该组合双Client验收通过。[输入SHA](evidence/safe-optimization-20261018/retained-inputs.json)、[源码SHA](evidence/safe-optimization-20261018/runtime-source-hashes.json)、[验收](evidence/safe-optimization-20261018/final-validation.json)。该阶段相对Guest已发布提交仅三个文件的列表补丁；当前安全服务候选另有改动和输入，见新报告。未改旧runtime-manifest和归档，后续发布需单独打包。

**原已发布RMM-only对照：** `build/memfd-retirement-20261018/candidate/`，720p已实测1157，双Client API/Compute/权限与IRQ负例通过；client/proxy/initrd/VMM随当前runtime-manifest归档恢复。输入哈希见[新组合清单](evidence/memfd-retirement-20261018/inputs.json)，当前源码哈希见[新源码清单](evidence/memfd-retirement-20261018/runtime-source-hashes.json)。

下表为**清理前已验证对照包** `build/bo-capacity-20261018/final/`，其1080p/ResNet50等历史结果不能直接继承给新源码。其[SHA与清理前60项源码清单](evidence/current-baseline-20261018/source-hashes.json)用于识别版本；不能仅凭一个提交号或Image文件名宣称等同已测组合。

| 输入 | SHA-256 |
| --- | --- |
| client-Image | `5dc92273d905f49f2a47ae6b418b74cb6aa68494ec3a7c9a7de97f94201d195a` |
| proxy-Image | `dc2e26213e378abb8466821ffe2bdad166921c9b213871cfb24e0974f251be7e` |
| initrd.cpio | `c3cdd4fa34c168e528460c9dd63f58354b5b66437c51973415fc5edb60931299` |
| runner.py | `e7703ec7d913676cb65f87e5e92e1751943f933000a039df4bb6414edd2152e9` |
| RMM ELF | `643b0e212a5f44646baa86779c9a9f347b10163852df8079ace588c0cd05a4ec` |

Host为`6.12.0-opencca-pmthor-opp3 #7`，需匹配模块、固件与只读用户态rootfs。主手册说明部署前检查；健康Host不因整理目录而刷写。运行前确认无其他硬件任务，用新的唯一run-id：

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py --images build/safe-optimization-20261018/final \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

大负载另加`--large-pool`，选择`--profiles ncnn-resnet50 glmark-1080 ioctl compute-128`；双Client功能使用`--workload compute`。未选负载记为未执行。

前一轮目录整理未改运行代码，见[整理记录](WORKSPACE_CLEANUP_20261018.md)。随后memfd退役修改了运行代码；其构建、性能与新输入单独记录于[退役记录](MEMFD_RETIREMENT_20261018.md)。
