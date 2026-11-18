# GPU共享代码清单：功能、权限与安全边界

状态：第二阶段核心规范化及清理已验收；入口和权限边界按当前源码核对。配套累计63项离线、完整720p1170、双Client真实计算/eventfd及最终来源/实际SD2/资源审计通过。完整目标中的大型任务和virtio性能对照另行验收。

## 按组件阅读

### Client

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| DRM对象、GPUVM/BO意图、依赖、任务序列及结果交付 | Client本地身份与引用、先验依赖/错误传播；成功仍由本Realm可信FINISH决定，Proxy提示无完成权 | A/B/D/E/F |

文件：`Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c`。

入口：`panthor_client_private_group_submit`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c:2810`）、`panthor_client_private_gpu_work`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c:2307`）、`panthor_client_private_mapping_lock`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c:1337`）、`panthor_client_private_observer_wait`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c:2181`）。

### Client

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 私有BO/backing、RSI封装、映射和任务kernel对象生命周期 | 实际页归属、token与对象引用；拒绝旧引用，未决任务不因RPC错误直接释放 | A/B/E/F |

文件：`Linux-Guest-GPU/drivers/char/realm_gpu.c`、`Linux-Guest-GPU/include/linux/realm_gpu.h`。

入口：`realm_gpu_task_stage`（`Linux-Guest-GPU/drivers/char/realm_gpu.c:640`）、`realm_gpu_task_call`（`Linux-Guest-GPU/drivers/char/realm_gpu.c:900`）、`realm_gpu_bo_cache_create`（`Linux-Guest-GPU/drivers/char/realm_gpu.c:1174`）。

### Client/Proxy通信

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 有界RPC队列、request/reply序号、waiter超时、事件唤醒 | 端点和序号关联、长度/预算、迟到回复互斥；超时不代表没有设备效果，不隐式重放发布 | A/B/E/F |

文件：`Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c`、`Linux-Guest-GPU/drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c`、`Linux-Guest-GPU/include/linux/vmshm_comm_protocol.h`。

入口：`client_comm_vmshm_call`（`Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c:1065`）、`client_comm_vmshm_dispatch_response`（`Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c:872`）、`proxy_comm_vmshm_send_to_channel`（`Linux-Guest-GPU/drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c:1148`）。

### Proxy

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 会话/对象元数据、已授权任务编排、IRQ声明与有界提示等待 | typed零初始化回复、配额、通道绑定；不持有真实页表或成功权威，不可自报owner替代RMM鉴权 | A/B/D/F |

文件：`Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c`、`Linux-Guest-GPU/include/linux/panthor_vmshm.h`。

入口：`panthor_proxy_session_rmm_task`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c:1542`）、`panthor_proxy_session_vm_sync`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c:940`）、`panthor_proxy_irq_work`（`Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c:120`）。

### Proxy功能驱动

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 原Panthor功能对象和受限服务接入，Native/单VM角色仍有明确使用者 | 受限路径的真实控制效果经可信层；不能把保留的普通驱动角色当作Proxy越权入口 | A/B/C/E |

文件：`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_drv.c`、`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c`、`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_sched.c`、`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.c`。

入口：`panthor_vmshm_session_open`（`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_drv.c:1448`）、`panthor_vmshm_vm_create_private`（`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_drv.c:1557`）、`panthor_vmshm_bo_import_private`（`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_drv.c:1579`）。

### RMM入口

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 真实调用身份、私有请求快照、RSI分派、受保护控制页CPU视图 | 输入范围和RTT/granule锁、真实通道对端、敏感来源检查；先记可能暴露再映射，TLBI完成后才清引用 | A/B/C/E/F |

文件：`opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c`。

入口：`handle_rsi_opencca_gpu_private`（`opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c:593`）、`copy_page_input`（`opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c:537`）、`map_command_page`（`opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c:325`）、`pin_control_page`（`opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c:74`）、`unpin_control_page`（`opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c:112`）。

### RMM内存核心

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| BO/GPUVM、真实多级PTE、映射事务、配额/引用与命令准入 | 真实owner/backing/PTE权限，版本及事务状态，旧引用/翻译在途未结束时禁止危险复用；opcode规则覆盖范围有限 | A/B/C/E/F |

文件：`opencca/tf-rmm/runtime/core/opencca_gpu_private.c`、`opencca/tf-rmm/runtime/include/opencca_gpu_private.h`。

入口：`gpu_private_map_begin`（`opencca/tf-rmm/runtime/core/opencca_gpu_private.c:2740`）、`gpu_private_map_step`（`opencca/tf-rmm/runtime/core/opencca_gpu_private.c:2857`）、`gpu_private_mapping_check`（`opencca/tf-rmm/runtime/core/opencca_gpu_private.c:2502`）、`gpu_private_task_hold_batch`（`opencca/tf-rmm/runtime/core/opencca_gpu_private.c:1171`）、`gpu_private_task_scan_commands`（`opencca/tf-rmm/runtime/core/opencca_gpu_private.c:1181`）。

### RMM设备/FW核心

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 固件批准与运行镜像、Group/Queue/ring、任务准入发布、完成和退休 | 批准同一字节、受保护根和ring、逐任务token/一次发布、粘滞故障、新鲜完成/写回/可见性，hint不改变终态 | A/B/C/D/E/F |

文件：`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c`、`opencca/tf-rmm/runtime/include/opencca_gpu_firmware.h`。

入口：`gpu_firmware_seal`（`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c:471`）、`gpu_firmware_prepare`（`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c:563`）、`gpu_firmware_task_finish_domain`（`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c:4660`）、`gpu_firmware_task_observer_poll`（`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c:3926`）。

### RMM设备控制

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| GPU接管、敏感入口隔离、reset/OPP、设备与页面lease和销毁边界 | 真实服务代次、撤MMIO、可信reset、未撤权拒绝销毁；旧query已退役，实际begin状态转换保护保留 | A/B/C/E/F |

文件：`opencca/tf-rmm/runtime/core/opencca_gpu.c`、`opencca/tf-rmm/runtime/rsi/opencca_gpu.c`、`opencca/tf-rmm/runtime/core/opencca_gpu_lease.c`。

入口：`opencca_gpu_service_isolate`（`opencca/tf-rmm/runtime/core/opencca_gpu.c:51`）、`opencca_gpu_pm_destroy_begin`（`opencca/tf-rmm/runtime/core/opencca_gpu.c:243`）、`opencca_gpu_service_release_locked`（`opencca/tf-rmm/runtime/rsi/opencca_gpu.c:460`）。

### RMM可信IRQ

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 物理事件消费、绑定代次关联、故障历史和Proxy声明核验 | Monitor记录与模拟来源区分；错代次/重复声明拒绝，故障粘滞，IRQ次数不单独证明任务成功 | B/C/D/E/F |

文件：`opencca/tf-rmm/runtime/core/opencca_gpu_irq.c`、`opencca/tf-rmm/runtime/include/opencca_gpu_irq.h`、`opencca/shared/include/opencca_gpu_irq_abi.h`。

入口：`opencca_gpu_irq_bind`（`opencca/tf-rmm/runtime/core/opencca_gpu_irq.c:241`）、`opencca_gpu_irq_sync`（`opencca/tf-rmm/runtime/core/opencca_gpu_irq.c:268`）、`opencca_gpu_irq_claim`（`opencca/tf-rmm/runtime/core/opencca_gpu_irq.c:324`）。

### Monitor

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 真实GPU/JOB/MMU中断捕获、受保护事件记录及Root IRQ视图 | 物理来源和事件序列/丢失记录；Root查询提示不替代RMM任务关联和最终FINISH | C/D/E |

文件：`opencca/trusted-firmware-a/plat/rockchip/rk3588/opencca/rk3588_gpu_irq.c`。

入口：`opencca_gpu_irq_init`（`opencca/trusted-firmware-a/plat/rockchip/rk3588/opencca/rk3588_gpu_irq.c:185`）。

### 可信平台

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 真实AS根/CSG与MMIO语义、cache/TLB、固定控制映射与全PE退休 | 硬件实际根/属性核对与错误保留；全PE翻译退休先于页面恢复；物理隔离完整性仍是明确未验证项 | A/C/D/E |

文件：`opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c`、`opencca/tf-rmm/plat/common/src/plat_common_init.c`、`opencca/tf-rmm/plat/common/include/plat_common.h`。

入口：`plat_opencca_gpu_pt_check_running`（`opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c:510`）、`plat_opencca_gpu_reset`（`opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c:672`）、`plat_cmn_gpu_control_unmap`（`opencca/tf-rmm/plat/common/src/plat_common_init.c:145`）。

### RMM跨Realm底座

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 端点/通道代次、受控共享映射、持久pending与控制IRQ | 身份与共享授权、RTT锁/引用、解绑撤权；知道端点/handle不等于获得权限，控制IRQ不等于GPU完成 | A/B/E/F |

文件：`opencca/tf-rmm/runtime/core/xshm_endpoint.c`、`opencca/tf-rmm/runtime/core/xshm_policy.c`、`opencca/tf-rmm/runtime/core/xshm_rtt.c`、`opencca/tf-rmm/runtime/core/xshm_irq.c`、`opencca/tf-rmm/runtime/rsi/xshm.c`。

入口：`xshm_endpoint_peer`（`opencca/tf-rmm/runtime/core/xshm_endpoint.c:56`）、`xshm_endpoint_release`（`opencca/tf-rmm/runtime/core/xshm_endpoint.c:197`）。

### Client通知优化

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 真实完成后的当前任务自有chain工作本地有界处理 | owner/CPU上下文、原claim/single/RCU/64项上限和溢出回退；不能提前授权GPU任务或伪造完成 | B/D/E/F |

文件：`Linux-Guest-GPU/kernel/irq_work.c`、`Linux-Guest-GPU/include/linux/irq_work.h`、`Linux-Guest-GPU/drivers/dma-buf/dma-fence-chain.c`。

入口：`irq_work_local_begin`（`Linux-Guest-GPU/kernel/irq_work.c:244`）、`irq_work_local_end`（`Linux-Guest-GPU/kernel/irq_work.c:310`）、`irq_work_queue_local_batch`（`Linux-Guest-GPU/kernel/irq_work.c:270`）。

### Host集成

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| KVM/Realm设备集成、GPU电源/驱动生命周期和底层回收请求 | Host只能请求可信语义操作，不能自证reset或回收完成；protected项目与nVHE virtio对照信任边界不同 | A/C/E |

文件：`Linux-Host-GPU/drivers/pmthor/pmthor_drv.c`、`Linux-Host-GPU/arch/arm64/kvm/rme.c`。

入口：`pmthor_gpu_bind_vm`（`Linux-Host-GPU/drivers/pmthor/pmthor_drv.c:61`）、`pmthor_gpu_track_pfn`（`Linux-Host-GPU/drivers/pmthor/pmthor_drv.c:174`）、`pmthor_gpu_put_vm_session`（`Linux-Host-GPU/drivers/pmthor/pmthor_drv.c:141`）。

### 验证与执行入口

| 功能 | 安全职责 | 保护目标 |
| --- | --- | --- |
| 冻结输入、范围明确的离线检查、硬件独占租约和资源恢复 | 测试并非运行时TCB；失败/未执行不能继承PASS，L1/L2不升级物理保证，Native基准按用户要求不重跑 | A/B/C/D/E/F |

文件：`scripts/run/run-gpu-security-offline.py`、`configs/security/offline-attack-map.json`、`scripts/maintenance/lab-run.py`、`scripts/run/run-realm-xshm.py`。

入口：`verify_runtime_freeze`（`scripts/run/run-gpu-security-offline.py:228`）、`expected_postflight`（`scripts/maintenance/lab-run.py:63`）。

## 生命周期中的权威链

Client提供私有backing和任务意图、维护应用依赖；Proxy建立功能元数据并建议编排；RMM从真实调用身份与通道取得owner、捕获私有快照、授权对象/映射/执行并持有引用。可信平台安装真实页表根、绑定和发布受保护ring；Monitor记录物理IRQ，RMM关联绑定/故障历史并完成新鲜状态/结果可见性核验。只有真实Client FINISH成功才交付成功；撤权、旧翻译与在途访问退出后才可复用资源。

知道handle/token、收到Proxy回复、看到控制通知IRQ、提示页变化、fence回调或普通计数都不能代替此链。多Client提示出错会回退原FINISH，错误仍报告；它不是新的成功权限。

## 保留、收敛与验证用途

- 保留完整冷/热路径、超时/错误/部分效果处理、依赖错误传播、可信完成、撤权和退休；它们有当前调用者或安全回退用途。
- 已淘汰的manager/共享业务BO数据路径不恢复；内部RPC ABI6只保留当前私有BO/元数据/RMM执行合同，旧action编号不复用。
- 删除 `opencca_gpu_pm_destroy_blocked()`：无运行调用者、旧/新链接镜像均不包含它；测试改为直接检查真实 `opencca_gpu_pm_destroy_begin()` 的状态及owner保护，并用两个已编译错误变体验证。
- `gpu_private_task_hold()` 和 `gpu_firmware_task_finish()` 是明确的模型适配器，委托同一批量/内部实现；当前生产路径使用batch/live和finish_domain，两个适配器不在链接RMM镜像中。头文件注明实际验证使用者，保留原范围模型不复制另一套安全规则。
- `realm_xshm_trace_show()` 由 `DEFINE_SHOW_ATTRIBUTE(realm_xshm_trace)` 生成的file ops引用；不能因文字扫描只见一次就删除。
- 运行时诊断有明确使用者：单轮profiling、IRQ证据、负例和资源恢复。当前固定日志/控制接口不承载业务BO，不凭减少输出就删除故障记录。

## 测试证据如何使用

| 证据 | 可以说明 | 不能说明 |
| --- | --- | --- |
| C token/宏类型一致、配套编译 | 本次排版保持代码表达式和调用顺序，配置/接口可构建 | 完整物理隔离或任意并发无竞态 |
| 实际核心/RSI/Client模型及编译错误变体 | 指定授权/映射/完成/生命周期规则被实际代码拒绝，负例确实可运行 | 完整硬件cache/TLB/GPC行为 |
| 完整720p、双Client计算/eventfd、IRQ/资源审计 | 本轮正常负载功能/性能、启用路径、内核健康与结束状态 | MEM05任意恶意shader、全操作数/间接流/验证后内容一致性 |
| 独占锁、冻结哈希、来源/布局核验 | 运行输入一致、日志和退出码可追溯、资源不混用 | 远程证明或Host绝对可信 |

本轮验证及run-id见[规范化与清理验收](GPU_CODE_NORMALIZATION_AND_CLEANUP_20261114.md)。物理CPU/DMA/GIC及整设备残留、MEM05和旧Group fence专项等既有未验证项保持；Native性能基准不重跑。大型真实模型与virtio对照有独立结果文档，未成功项目不写成PASS。

## R01—R14到实际代码的对应

| 功能组 | 实际入口 | 权威状态/判定 | 保护目标 |
| --- | --- | --- | --- |
| R01 身份、对象关系、预算 | `bo_lookup()`、`ctx_lookup()`、`new_handle()`；`opencca/tf-rmm/runtime/core/opencca_gpu_private.c` | 真实owner与不复用代次、BO/GPUVM引用及容量；另由FW task/group记录建立执行关联 | A/B/E/F |
| R02 敏感设备入口 | `opencca_gpu_service_isolate()`、`opencca_gpu_mmio_allowed()`；`opencca/tf-rmm/runtime/core/opencca_gpu.c` | 受控接管、撤销原MMIO授权、服务端点代次与失败状态 | A/B/C/E |
| R03 固件与启动 | `gpu_firmware_seal()`、`gpu_firmware_prepare()`、`gpu_firmware_boot()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 批准快照、同一固件字节、真实运行页与MCU根、启动握手 | A/C/E |
| R04 GPU页表事务 | `gpu_private_map_begin()`、`gpu_private_map_step()`、`gpu_private_unmap_bo()`；`opencca/tf-rmm/runtime/core/opencca_gpu_private.c` | 真实PTE/backing/权限、保留事务及失败引用、必要同步/翻译撤销 | A/B/C/E/F |
| R05 Group/Queue控制内存 | `gpu_firmware_group_configure()`、`gpu_firmware_group_queue_validate()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 组队列关联、控制页持有、受保护ring与生命周期 | A/B/C/E/F |
| R06 准入和有限授权 | `gpu_firmware_task_stage_domain()`、`gpu_firmware_task_ready()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 捕获命令意图、逐任务token/引用和阶段；不把同Client当免检条件 | A/B/C/E/F |
| R07 实际绑定 | `plat_opencca_gpu_pt_prepare()`、`plat_opencca_gpu_pt_check_running()`；`opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c` | 可信对象与AS/根/配置实际一致，旧使用者退出边界 | A/B/C/E |
| R08 数据交接与发布 | `task_publish()`、`task_ready_publish()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 受保护wrapper、设备暴露状态、producer/notify顺序及部分效果保留 | A/B/C/E |
| R09 事件和故障 | `opencca_gpu_irq_sync()`、`opencca_gpu_irq_claim()`；`opencca/tf-rmm/runtime/core/opencca_gpu_irq.c` | 物理记录按当前绑定/代次消费，错声明拒绝，故障历史不因干净快照抹除 | B/C/D/E |
| R10 成功与可见性 | `task_observe()`、`task_finish()`、`gpu_firmware_task_finish_domain()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 所有必要完成条件、故障、GPU写回与CPU可见性满足后才返回可信成功 | A/B/D/E |
| R11 动态资源 | `gpu_firmware_task_heap()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 实际事件、对象关系、预算与Client新页事务，受控FW握手 | A/B/C/E/F |
| R12 撤权和退休 | `task_retire()`、`gpu_firmware_task_reclaim()`；`opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c` | 停止/解绑、归还与引用退出，旧token/翻译/访问不进入新使用者生命周期 | A/B/C/E |
| R13 隔离与复位 | `plat_opencca_gpu_reset()`；`opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c` | 可信reset/ACK和回收边界；不确定资源保留，故障不授权清他人活动资源 | A/C/D/E/F |
| R14 接口与通信 | `xshm_endpoint_peer()`、`xshm_endpoint_release()`；`opencca/tf-rmm/runtime/core/xshm_endpoint.c` | 真实通道对端和代次、共享授权/持久事件；两端仍负责完整RPC解析和内存安全 | A/B/E/F |

每个入口均已核对当前源码存在；表格说明功能责任，不将源码存在视作物理安全证明。实际运行和负例证据在验收记录中单列。

## 大型任务的独立验证代码

`GPU-SFTP/tests/ncnn-bench/trained_model_check.cpp` 执行真实权重加载、FP32 CPU参考、GPU预热/计时及每轮全部1000项数值比较；它是工作负载验证代码，不负责授予GPU权限或认定安全退休。构建入口为同目录 `CMakeLists.txt` 及 `scripts/build/build-trained-model-check.sh`，固定SDK并使用目标Guest数学库。实测二进制、来源与计时口径见[官方ResNet50验证](GPU_TRAINED_RESNET50_VALIDATION_20261114.md)，规范Release构建产物不自动继承实机结果。

Notion代码清单：https://app.notion.com/p/417659a3b8cc815a9d17f18e18ec0713 。
