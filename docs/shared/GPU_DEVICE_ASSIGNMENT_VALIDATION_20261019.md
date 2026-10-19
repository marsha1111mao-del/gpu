# 场景二：设备授权与 GPU 电源生命周期验收

**后续当前候选：** Host #27 / RMM 的托管IOMMU故障中断迁移、八项独立功能验收、
完整720p1168分、物理MMIO绕过失败和三端清理见[后续报告](GPU_IOMMU_FAULT_VALIDATION_20261019.md)。
本文#26/1173分及其源码/输入快照、失败与未执行项均按历史原值保留，不替换为后续结果。

日期：2026-10-19。本文接续[上一阶段开发验收](SECURE_SERVICES_VALIDATION_20261019.md)，
保留其中已实现、部分实现、失败、NOT_RUN 与历史分数。新阶段采用独立 run-id，
不把旧 PASS 继承到新 Host/RMM；原冻结 1171/1170 组合保持不变。

## Host 电源管理与工作态 MMIO 的边界

设计成立：Host 管理板级供电、电源域、时钟和合法 OPP；指定 Proxy 管理 GPU 工作态。
任务相关 MMIO 包括队列/doorbell、GPUVM/MMU 根、地址空间、固件控制、提交以及 IRQ mask/clear。
工作态不得让 Host 直接修改这些寄存器；有副作用的读取也不能作为普通遥测接口开放。
GPU 内部电源寄存器若与任务寄存器共享保护粒度，应经可信接口操作，不能为 Host 映射整个寄存器页。

复位或断电重启必须先阻止新任务与引用，撤销旧 MMIO 授权，由 RMM 确认设备停止，
再允许回收 backing。重新上电不自动恢复旧授权与旧任务；需要重新建立有效会话。
Host 可以拒绝调度或切断物理电源，现有软件不能保证可用性；也不能把 Host 自报“已经断电”当作释放页面的证明。

| 主体 | 责任与当前实现 | 保留的边界 |
| --- | --- | --- |
| Host | 实际板级电源/时钟/OPP 操作，RMI 请求授权和撤销；pmthor 不映射任务寄存器 | 后续物理写探针已确认 Host 仍能修改已授权设备的 IRQ mask；不具备不可绕过的任务 MMIO 保护 |
| RMM | 单 Proxy MMIO owner、可信复位与撤销、活跃页回收拒绝；托管真实 RK IOMMU 表、root、IOTLB 与 parking | GPT/GPC 仍有模拟边界，GPU 无外置 SMMU S2 |
| Proxy / Panthor | 经 RSI claim/reset，维护真实 GPUVM、提交和 fence | 首个指定 RD 未做镜像身份测量；跨 Client/Group/GPUVM 攻击专项未完成 |
| Guest / 其他 IOMMU 设备 | 仅对 RMM 已授权且 Host 保持供电的设备执行 BIND | 本轮验证真实 codec IOMMU root 生命周期，未运行 codec 数据 DMA 或完整 Guest codec 驱动直通 |

### Host 物理访问保护的源码复核

本次源码复核未改运行代码，无新增性能测量；下列结论不改变已记录的九次选定验收，也不把整体安全状态提升为完成。后续新增的实际物理写诊断另列于下节。

TF-A 的 `opencca/include/opencca.h` 将 `write_gpccr_el3`、`write_gptbr_el3`
替换为写 `AFSR0_EL3` 的 dummy 操作，读取返回平台常量；同文件的
`opencca_tlb_flush()` 明确说明 RMM 与 Linux 复用 normal world。
`lib/el3_runtime/aarch64/context_mgmt.c` 与 `opencca/include/opencca_asm.h`
用保存的 `SCR_EL3_SPOOFED` 区分软件 Realm 上下文。这些软件状态不能给总线访问增加真实 Realm 安全属性。
RMM 的 `plat/rk3588/src/rk3588_setup.c` 中 `MT_REALM` 映射为 RMM 建立可访问视图，
不能单独撤销 Host 自建物理映射的访问权。

RK3588 的 TF-A `plat/rockchip/rk3588/drivers/secure/secure.c` 提供 DSU/DDR/SYSMEM
防火墙，但现有安全/非安全 master 配置不等于指定 Proxy/Host 的区分。
仅把 GPU MMIO 改为 secure，不能保持当前 normal-world Proxy 的直接访问路径；
若改为安全世界代理，需要重新设计可信执行边界、GPU 访问路径和验证方案。
不能只修改 GPT 元数据或重复增加驱动 hook 就宣称补齐硬件保护；本轮未盲写防火墙寄存器。

| 要求 | 当前结论 | 证据边界 |
| --- | --- | --- |
| RMI/RSI 共用托管 IOMMU，真实表/root/IOTLB/撤销 | 已实现并通过所列选定验收 | codec root 生命周期通过；数据 DMA、完整故障组合和物理配置防护未验收 |
| 指定 Proxy 独占工作态任务 MMIO | ABI 与 Realm RTT 授权路径已实现 | KVM11项不包含恶意 Host 物理写入阻断测试，不能作为该项硬件 PASS |
| Host 受限 PM、可信复位与页面回收顺序 | 已实现并通过所列选定验收 | 空闲电源域循环及 workload teardown 通过；活跃任务断电/复位失败组合仍未完成 |
| Host 无法直接写任务 MMIO、真实页表及其配置 | 任务 MMIO 物理写入已复现绕过；不可绕过的硬件边界未实现 | 需要独立于 Host 的真实访问控制及正反例；当前模拟 GPT/GPC 不满足这一证明要求 |

Host 保留电源执行权不代表允许任意运行中停钟、复位或切换电压；正常操作必须满足可信状态机和合法 OPP。
若威胁模型允许 Host 恶意切断物理电源，可用性不保证；失败应保留隔离状态和 backing 引用，
不能仅根据 Host 报告就释放页面，也不能在重新上电后继续使用旧授权。

### 实机 Host 物理 MMIO 写入负例

`host-mmio-physical-audit-20261019-a` 在同一 Host #26 / RMM device-grant 上运行，
外层退出 **2**，`host_mmio_protection=FAIL_BYPASS_DETECTED`。
首个测试 Realm 已获 GPU MMIO，第二个 Realm 被拒绝；GPU 无活跃任务，未启动 vCPU 或 workload。
Host 绕过 RMI/RSI，经 `/dev/mem` 直接将 `0xfb000028`（GPU IRQ mask）从 **0 写为 1**，
读回 **1** 后恢复 **0**。这是实际修改/读回证据，不是同值写入或只读探测。

11 项 ABI/owner/OPP/释放/重新授权检查仍通过，但不能抵消物理访问防护失败。
探针子进程访问固定寄存器；仅在 GPU 无活动且 fault 未 pending 时翻转 fault mask 位，
父进程持有会话并继续可信复位/释放。恢复读回通过，增量内核错误为空，
结束后 pmthor、CPU0–1、无实验进程/loop 均恢复。该负例未测试在途 GPU 任务攻击或其他物理地址。

命令：`python3 scripts/maintenance/lab-run.py --run-id host-mmio-physical-audit-20261019-a -- python3 scripts/run/run-kvm-mmio-probe.py --probe build/secure-services-20261019/physical-mmio/opencca_kvm_mmio_probe --audit-host-mmio --uart-capture`。
日志：`build/lab-runs/host-mmio-physical-audit-20261019-a/` 下的
`kvm-mmio-probe.log`、`kvm-mmio.json`、`kernel-dmesg.log`、`rmm-uart.log` 和资源记录。
源码/二进制 SHA 与精简结果见[物理 MMIO 负例证据](evidence/secure-services-20261019/host-mmio-physical-audit.json)。

仅改验证探针、对应 runner 与说明，Host/RMM/Guest 运行源码及板端固件/内核未变；
保留旧九次验收及其原 66 项源码快照，不用新探针 SHA 覆盖历史测试输入。
未执行性能测量，整体安全验收继续 **PARTIAL / INCOMPLETE**。

最终 runner 将“未能证明物理写入”与 ABI 失败分开判定后，
`host-mmio-physical-audit-20261019-b` 以当前源码独立复验，退出 **2**，
同样读回 **0→1→0**、ABI **11/11**、内核健康及恢复通过；安全结论仍为绕过失败。
首轮 -a 与最终 -b 的 runner SHA 分别保留，不覆盖历史输入。

同板可进一步评估受保护 EL2 管理 Host EL1 的架构；这不是开启现有 pKVM 参数即可完成的修复。
当前 Host `arch/arm64/kvm/arm.c:kvm_arm_init()` 只在 `is_kernel_in_hyp_mode()` 为真时初始化 RME；
`hyp/nvhe/mem_protect.c:host_stage2_idmap()` 默认按需恢复 Host MMIO 映射。
因此需要另行设计 RMM 与受保护 EL2 的信任关系、受限物理范围及故障处理，
并验证 Host 内核别名写入、CPU 上下线/恢复和设备 DMA 路径，不能宣称已兼容或已强制保护。
本轮未改变启动参数或部署该架构。

后续独立实验已验证同一#27能以受保护hVHE启动且所列RMI电源调用通过，但Realm能力变为0；
原启动配置已恢复。新增内核`ioremap`负例同样实测0→1→0绕过。详见
[受保护EL2兼容性与内核别名负例](GPU_PROTECTED_EL2_COMPATIBILITY_20261019.md)，不修改本段历史结论或继承安全PASS。

### GPU 负载期间托管 IOMMU 追加验收

`managed-iommu-live-device-grant-20261019-c` 退出 **0**，**28/28** 检查通过，
`live_gpu_mapping_check=PASS`。新增六项覆盖活跃 GPU HPA 的只读、可写、别名、
覆盖范围、SG 映射拒绝与 SG 回滚；包括原 22 项真实 codec IOMMU root/parking/恢复检查。
模块卸载退出0，Host/Guest 内核健康通过，两个 Realm 退出 `[0,0]`，频率及 CPU 恢复。
`configuration_protection=PASS_DIRECT_DRIVER_PATH` 只指 managed 直接驱动入口，
不覆盖上文已经失败的 Host 物理写入；`actual_dma_transfer=NOT_RUN` 继续保留。

命令：`python3 scripts/maintenance/lab-run.py --run-id managed-iommu-live-device-grant-20261019-c -- python3 scripts/run/run-dma-guard.py --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko --images build/secure-services-20261019/final --uart-capture`。
日志在同名 run 目录的 `dma-guard.json`、`kernel-delta.log`、`rmm-uart.log`、
`host-kernel-health.json` 与 `collected/`。板端8个原始文件已归档到 `collected/`，逐文件 SHA 一致。

改动目的｜补齐活跃 GPU 页的托管 IOMMU 准入验收，未改运行代码｜同候选独立性能轮1173 → 本轮 **1171**｜
**−2分 / −0.17%**｜完整720p/33场景、默认256 MiB、null-noop/finish，GPU请求600/实际594 MHz，CPU未锁恒频；
本轮同时运行 IOMMU 探针及 UART 采集，条件不同｜上述 run-id/命令，退出0，`collected/glmark-720.log`｜
**保留专项验收；不归因于单项改动，不替换独立性能轮或原冻结基线。**
validation 为26成功、1已知数值例外、6无判据、非预期失败0，clean PASS；
CPU0–3/600MHz请求恢复为CPU0–1/300MHz。Native/1080p/NCNN未新增测量。

最终负例与负载专项的命令、输入/源码 SHA 和结果见
[追加验收清单](evidence/secure-services-20261019/mmio-and-live-iommu-validation.json)。
这次只修改验证探针/runner与文档，未修改 Host/RMM/Guest 运行代码、固件或内核。

追加清理 `host-mmio-probe-cleanup-20261019-a` 退出0：仅删除 RK 首轮 -a 的重复探针二进制1个，
逻辑852,704字节、实际释放 **856,064字节（0.82 MiB）**，分区可用空间增量一致。
逐项核对原值SHA、inode/mtime、fd/maps、loop/挂载与最终 -b 保留副本，保留全部失败日志、
控制机当前构建与最终板端复验输入。Pi本轮无新增镜像/编译产物，既有保留分类不变。
精确清单、执行命令及前后资源在同名 run 目录的 `cleanup-result.json`、`result.json`、`before.json`、`after.json`；
这笔清理单独记录，不改写之前181文件/3.71 GiB的历史统计。

Notion 追加后回读确认原已实现7项、部分实现7项、历史失败/未执行6项及43个既有run-id标识均保留；
移除本次新增段落后，原页面正文一致。见[追加条目保留审计](evidence/secure-services-20261019/notion-mmio-live-preservation.json)。

## 补齐 Guest 设备分配与供电授权

Host-only `GRANT=9` 把一个真实已绑定、健康、无映射的 Host managed domain 中的设备，
授权给有效 Guest domain handle；handle 包含 generation，避免旧授权重用。
Host Rockchip 驱动在绑定期持有时钟/runtime-PM 引用，RMM 先把设备停在空 root，再发布授权。
未授权的 Guest BIND 在触碰硬件前拒绝，包括合法但未供电的其他 bank。

授权期间 Host map/bind/unbind/quiesce/destroy 和目标 Guest destroy 被拒绝，
防止供电引用或授权对象提前消失。Host-only `REVOKE=10` 不依赖 Guest 自报完成：
RMM 先 parking 并同步 IOTLB，撤销 Guest 绑定，再恢复 Host 空 root。
Guest backing 预留继续保留，须正常 unmap/destroy 才释放；失败进入隔离并保留引用。

真实调用者是 `opencca_iommu_assignment_probe.ko`，Guest 探针保持 domain 与映射，
经固定 `iommu-device 5/6` 命令执行 BIND/UNBIND。两端 runner 实际调用新增接口，
没有仅为未来需求预留的空框架。ABI 与复现命令见[探针说明](../../GPU-SFTP/tests/dma-guard/README.md)。

## 电源循环发现的问题与修复

Host #23 的电源循环 `gpu-power-cycle-device-grant-20261019-a/b/c` 均失败：
空闲平台解绑时 RK 失联，UART 有 RCU stall，外层退出 1。
诊断 `gpu-power-diag-20261019-b` 曾通过，但去掉诊断后的 `-c` 再次失败，
因此诊断 PASS 不作为问题已解决的证据。

根因是 `drivers/base/platform.c:platform_remove()` 在设备 remove 返回后先
`dev_pm_domain_detach()`，而 devres 清理在此之后。旧 pmthor 把会访问 GPU MMIO 的
RMM POWER_OFF 复位留在 devres 时钟回调，实际与异步电源域关闭竞争。
诊断日志记录了 GPU domain power-off 已进入、随后才执行时钟清理，解释了时序扰动下的偶然通过。

修复将可信停机与时钟关闭提前到 pmthor remove 返回之前，并覆盖显式 probe 失败回收；
后续 devres 回调幂等，不再访问已掉电 GPU。OPP 与时钟关闭共用 owner 锁，
关闭后拒绝新的变频回调。删除了平台层已管理的重复 domain attach/detach、
无用 PM 字段、coherent 字段、旧声明与未使用 include。

`gpu-power-cycle-device-grant-20261019-d` 在修复版 Host #25 上无诊断通过，
真实电源域 on→off-0→on、RMM UNOWNED→OFF→UNOWNED、非法 OPP 拒绝、频率恢复及 KVM 11 项均通过。
删除无用字段后的最终 Host #26 已另行完成七项回归与两次无诊断电源循环，结果及清理证据见下节。

失败原始日志和三次仅电源恢复均保留在 `build/lab-runs/<run-id>/`。
诊断上传目录缺失的 rc=1、诊断模块首次构建 rc=2，以及更早单元/打包失败也保留，
见 `build/secure-services-20261019/device-assignment/{development-failures,power-development-history}.json`。

## 当前输入与验收记录

最终候选 Host 为 `6.12.0-opencca-pmthor-opp3 #26`，Image SHA-256
`ce66d275ba9509104dfbe38ac01c7785d42ac27889d7e460d37132a36b688be2`；
RMM ELF `7cc379993f609720a947bc5d4658c539e46f42f1352da1082e5534cd35591d13`，
FIT `e9957c3bcc21cf6cedb0046c4eb013fb0adc980542841adc629c1b478d44ba75`。
Host/Guest release 与模块一致，Host 增量构建显式使用 `LOCALVERSION=-opencca-pmthor-opp3`。

RMM 部署 `rmm-device-grant-deploy-20261019-a`、最终 Host 部署
`host-power-order-deploy-20261019-b` 均退出 0，只使用 SD storage ID 2。
扩大的 RMM FIT 经布局检查和 UART 七个镜像 SHA 校验，保留更新前完整启动区与 kernel 分区备份。
Realm 包仍为 `build/secure-services-20261019/final/`，Proxy/Client/initrd 未在本阶段修改。

本地检查均退出 0，原始输出在 `build/secure-services-20261019/device-assignment/`：

| 命令 | 范围 | 日志 |
| --- | --- | --- |
| `scripts/check/check-secure-iommu.sh` | ASAN/UBSAN；Guest 未授权、自授权、stale handle、非空 Host domain 拒绝；真实表、授权/撤销、保留 backing、回滚与隔离 | `unit.log` |
| `scripts/check/check-dma-guard.sh` | ASAN/UBSAN 租约/DMA/可信状态机与真实复位后端 mock | `dma-unit.log` |
| `cmake --build build/dma-guard-20261018/rmm -j8` | RMM 构建 | `rmm-build.log` |
| `make -C Linux-Host-GPU O="$PWD/build/dma-guard-20261018/host" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-pmthor-opp3 -j8 Image` | 最终清理版 Host 构建 | `host-power-order-clean-build.log` |

七项最终回归和连续两次无诊断电源循环均在 Host #26 / RMM device-grant 上独立运行，外层退出码全部 **0**。
每项的外层命令、前后资源和退出码在 `build/lab-runs/<run-id>/{result,before,after}.json`；
下表日志均相对于同名 run 目录，原始日志不加入源码仓库。

| run-id | 完整命令（控制机仓库根目录） | 退出码与结果 | 日志 |
| --- | --- | --- | --- |
| `glmark720-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id glmark720-device-grant-20261019-b -- python3 scripts/run/run-realm-xshm.py --images build/secure-services-20261019/final --workload glmark --performance --benchmark-only --suite --profiles glmark-720` | 0；完整33场景720p **1173**，validation/clean/退出后Host内核健康PASS；Realm退出[0,0] | `collected/summary.json、collected/glmark-720.log、host-kernel-health.json` |
| `guest-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id guest-device-grant-20261019-b -- python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/device-assignment/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/device-assignment/realm-init --assignment-module build/secure-services-20261019/device-assignment/host-module/opencca_iommu_assignment_probe.ko` | 0；9/9，真实codec授权/绑定/解绑/重绑/强制撤销与backing释放；Host/Guest生命周期健康 | `guest-iommu/result.json、guest-iommu/host-assignment.log、guest-iommu/host-lifecycle.log` |
| `guest-rsi-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id guest-rsi-device-grant-20261019-b -- python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/device-assignment/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/device-assignment/realm-init` | 0；15/15，含未授权codec和未供电VOP BIND在硬件访问前拒绝 | `guest-iommu/result.json、guest-iommu/host-lifecycle.log` |
| `managed-iommu-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id managed-iommu-device-grant-20261019-b -- python3 scripts/run/run-dma-guard.py --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko` | 0；22/22，真实codec托管表/root/撤销；live_gpu_mapping_check=NOT_RUN | `dma-guard.json、kernel-delta.log` |
| `guest-backing-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id guest-backing-device-grant-20261019-b -- python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/device-assignment/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/device-assignment/realm-init --reclaim-module build/dma-guard-20261018/reclaim-probe-module/opencca_reclaim_probe.ko` | 0；3/3，活跃backing回收拒绝、表项不变及后续正常释放；全生命周期健康 | `guest-iommu/result.json、guest-iommu/host-reclaim.log、guest-iommu/host-lifecycle.log` |
| `gpu-backing-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id gpu-backing-device-grant-20261019-b -- python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/device-assignment/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/device-assignment/realm-init --reclaim-module build/dma-guard-20261018/reclaim-probe-module/opencca_reclaim_probe.ko --gpu-backing` | 0；3/3，活跃backing回收拒绝、表项不变及后续正常释放；全生命周期健康 | `guest-iommu/result.json、guest-iommu/host-reclaim.log、guest-iommu/host-lifecycle.log` |
| `gpu-pm-device-grant-20261019-b` | `python3 scripts/maintenance/lab-run.py --run-id gpu-pm-device-grant-20261019-b -- python3 scripts/run/run-gpu-pm-regression.py --images build/secure-services-20261019/final --kvm-probe build/dma-guard-20261018/opencca_kvm_mmio_probe --lease-monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko --workload compute --uart-capture` | 0；双Client各17项API、真实计算/权限/IRQ通过；GPU租约峰值5511，最终GPU/DMA及查询错误均0；三Realm退出[0,0,0] | `gpu-pm-regression.json、host-dmesg-new.log、collected/、rmm-uart.log` |
| `gpu-power-cycle-device-grant-20261019-e` | `python3 scripts/maintenance/lab-run.py --run-id gpu-power-cycle-device-grant-20261019-e -- python3 scripts/run/run-gpu-power-cycle.py --module build/secure-services-20261019/device-assignment/power-module/opencca_gpu_power_probe.ko --kvm-probe build/dma-guard-20261018/opencca_kvm_mmio_probe` | 0；4项电源/恢复检查及KVM11项通过；真实domain on→off-0→on，RMM 0→8→0，非法OPP拒绝，内核健康与环境恢复 | `gpu-power-cycle.json、power-cycle-kernel.log、power-cycle-uart.log、kvm-mmio.json` |
| `gpu-power-cycle-device-grant-20261019-f` | `python3 scripts/maintenance/lab-run.py --run-id gpu-power-cycle-device-grant-20261019-f -- python3 scripts/run/run-gpu-power-cycle.py --module build/secure-services-20261019/device-assignment/power-module/opencca_gpu_power_probe.ko --kvm-probe build/dma-guard-20261018/opencca_kvm_mmio_probe` | 0；4项电源/恢复检查及KVM11项通过；真实domain on→off-0→on，RMM 0→8→0，非法OPP拒绝，内核健康与环境恢复 | `gpu-power-cycle.json、power-cycle-kernel.log、power-cycle-uart.log、kvm-mmio.json` |

精简验收与 **66项源码、13项输入、3项固件SHA** 见
[设备授权验收清单](evidence/secure-services-20261019/device-assignment-validation.json)。
验收后逐项回读源码哈希一致。中间 Host #23 / 新RMM 的七项 `*-device-grant-20261019-a` 也均退出0，
当时720p为1170、GPU租约峰值5428；后续电源循环失败不能被该批功能PASS掩盖。
本阶段GPU电源域循环只覆盖空闲设备；不据此宣称所有活跃任务/故障组合都已验证。

## 性能记录

改动目的｜Guest设备授权/供电生命周期与GPU电源顺序修复｜上一阶段1167 → 本版 **1173**｜
**+6分 / +0.51%**｜完整720p、33场景、默认256 MiB，GPU请求600/实际594 MHz，
离屏null-noop/finish，CPU未锁恒频；Host/RMM组合变化，Proxy/Client/initrd不变｜
`glmark720-device-grant-20261019-b`，完整命令见表，退出0，日志见同名run目录｜
**保留开发候选；只记录组合观测，不替换原冻结1171/1170基线，不宣称稳定提分。**

中间同RMM、Host #23的1170 → 最终Host #26的1173为 **+3分 / +0.26%**；
相对原冻结均值1170.5为 **+2.5分 / +0.21%**。各仅单轮，不能把差异归因于某个修复。
validation为26成功、1已知数值例外、6无判据、非预期失败0；CPU0–3/600MHz请求恢复CPU0–1/300MHz。
Native、1080p和NCNN等未重测。纯文档维护与产物删除未改运行代码，无新增性能测量。

## 验收后的三端清理

`device-grant-cleanup-20261019-a` 退出0，新增删除 **33文件**，实际释放
**172,609,536字节（164.61 MiB）**。

| 角色 | 删除文件 | 逻辑字节 | 实际文件系统释放字节 | 范围 |
| --- | --- | --- | --- | --- |
| 控制机 | 21 | 2,026,622 | 2,072,576 | 失败FIT提取副本与已退役诊断模块编译产物 |
| Pi | 0 | 0 | 0 | 无新增废弃候选；保留当前固件、回退和完整恢复镜像 |
| RK | 12 | 170,500,624 | 170,536,960 | 中间-a批Guest探针重复Image/initrd/module；保留最终-b批复验输入 |

命令：`python3 scripts/maintenance/lab-run.py --run-id device-grant-cleanup-20261019-a -- python3 build/secure-services-20261019/device-assignment/cleanup-final.py`。
逐文件路径、SHA、大小、mtime/inode、占用检查与保留分类见同名run目录的
`cleanup-plan.json`、`cleanup-result.json`。查验fd/maps、loop/挂载与实验/刷机进程，
变化或占用即停止。旧Guest输入有控制机同SHA副本；所有日志、当前构建输入、回退/恢复镜像和模型保留。
临时kprobe诊断源码/调用脚本已退役删除，生产源码中的重复实现与无用字段已在最终构建前清除。

上一阶段三端清理148文件、3,812,438,016字节（3.55 GiB）的记录保持不变；
两阶段合计 **181文件、3,985,047,552字节（3.71 GiB）**。
不将Pi本轮0项误写成未检查，上一阶段Pi实际清理54文件/53,915,648字节。
最终资源审计：`build/lab-maintenance/secure-services-20261019/after-device-assignment.json`；
退出0、issues为空。最终回读确认Host #26、pmthor、CPU0–1、300MHz/userspace，
见 `build/secure-services-20261019/device-assignment/final-host-state.json`；两端无实验进程，RK无loop，Pi既有系统swap loop保留。

Notion更新后回读确认原已实现7项、部分实现7项、历史状态6项顺序与条目不变，
39个原历史run-id/证据标识及新增9个run-id全部保留，缺口区仍在。
核对见[条目保留审计](evidence/secure-services-20261019/notion-device-assignment-preservation.json)。


## 仍未执行或未解决

- 完整冻结性能/攻击矩阵、长期压力、多故障组合及复位失败硬件注入未验收；空闲 GPU 电源域循环不等于所有断电故障组合已通过。
- compute 的 Provider replacement 单独生命周期项继续为 NOT_RUN；Native、1080p、NCNN 性能本轮未重测。
- 原 `managed-iommu-device-grant-20261019-b` 的 `live_gpu_mapping_check=NOT_RUN` 记录保留；后续独立 `managed-iommu-live-device-grant-20261019-c` 已以28/28补齐该专项，不能据此宣称实际 codec 数据 DMA 或物理访问防护通过。
- hostile Host 任务 MMIO 物理写入已由后续负例复现绕过；物理配置保护未完成，不能仅标为尚未运行测试。镜像证明、GPUVM 跨 Client/Group 强化和每次访存的硬件隔离仍未证明。
- Group submit fence 历史超时继续 UNRESOLVED；直接 PTE/无 IOMMU PL330 绕过记录保留，不能被新正例抵消。
- 本文和 Notion 继续保留原已实现 7 项、未实现/部分实现 7 项及原失败/NOT_RUN/未解决 6 项，不删除已推进条目的历史缺口。
