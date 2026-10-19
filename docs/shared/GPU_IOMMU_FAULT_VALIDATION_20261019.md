# 场景二：托管 IOMMU 故障中断迁入 RMM

日期：2026-10-19。接续[设备授权与电源验收](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)。
原已实现7项、部分实现7项、失败/NOT_RUN/未解决6项及所有历史运行记录继续保留。
本轮补齐真实调用路径，整体安全状态仍为 **PARTIAL / INCOMPLETE**。

## 电源与任务寄存器的职责

Host 可以执行板级供电、时钟及合法 OPP 操作；进入工作态后，指定 Proxy 控制
GPU 队列、doorbell、GPUVM/MMU 根、地址空间、固件与任务 IRQ mask/clear。
Host 的电源执行权受可信状态机约束，不代表可以在运行中任意停钟、复位或降压。
同一保护页中混有电源字段时，不能把整页映射给 Host；需要受限可信接口。

复位、断电重启和 backing 回收必须协调：阻止新任务/引用，撤销旧 MMIO 授权，
可信确认设备停止后再释放页面；失败保留隔离状态和引用，上电后重新建立授权。
Host 自报停机不能作为回收证明。恶意切断物理电源仍能造成拒绝服务。

这是一项设计要求。Host #26 的0→1→0绕过负例保留，Host #27 本轮也独立复现相同物理写入，
不能把合作驱动或 RMI/RSI 正例写成 hostile Host 已被硬件禁止访问。
本轮 IOMMU IRQ 迁移同样不提供这个缺失的物理访问边界。

## 实现与失败处理

此前托管表/root/map/unmap 已交给 RMM，但 Rockchip IOMMU 的故障 IRQ 仍由 Host
直接执行 ZAP_CACHE、PAGE_FAULT_DONE 和 INT_CLEAR。本轮移除 managed 工作态的该路径：

| 主体 | 本轮行为 |
| --- | --- |
| Host Rockchip IRQ | 持有正常 PM/时钟引用，以缓存的 generation handle 请求 RMM FAULT；消费结果并报告本 Host domain 的故障，不直接写托管 bank |
| RMM 公共核心 | RMI/RSI 共用 owner、handle、设备绑定与隔离检查；Host 代收 Guest IRQ 时选择真实 Guest root，Guest 尚未 BIND 时选择 deny-all parking root |
| RK3588 后端 | 只访问固定允许设备；先校验全部 bank 的 root、paging 和 IRQ 位，再读取故障地址并由 RMM 清缓存、结束页故障和清中断；完成后再次核对配置 |
| 失败路径 | 失败同时隔离 Host grantor 与有效 Guest domain，保留映射与 backing；已隔离状态不再调用故障恢复后端 |

缓存 handle 在解绑后保留为该 bank 已受托管的标记；identity/旧 handle 不会回退到
Host 原始 IRQ 写入。绑定前设置缓存，覆盖部分绑定失败。绑定失败先尝试可信 parking；
无法确认停机时保留 PM/时钟引用并报告错误，不能为回滚而提前断电。
未启用 managed 模式的旧 IRQ 实现仍供普通 Rockchip 驱动使用。

开发 ABI 增加 `FAULT=11`，输入为 `(11, domain_handle, 固定 device ID, 0, 0)`。
成功返回 `x1` 每16位编码一个 bank 的 page-fault/bus-error 位及写故障位8；
bit32表示 Guest 路径；`x2/x3` 为两个 bank 的故障 IOVA，`x4` 为有效 domain handle。
Host IRQ 只消费 `x1..x3`，Guest 完整寄存器接口另校验 `x4`。
无 pending IRQ 不执行清除命令。无绑定、错误 owner/stale handle 或未供电设备在访问硬件前拒绝。
该扩展需配套部署 Host/RMM，不能给旧组合套用新版本验收结论。

## 输入与本地验证

| 输入 | SHA-256 |
| --- | --- |
| Host #27，内置 release `6.12.0-opencca-pmthor-opp3` | `16c6d4832169d03317ee1274f52fb313d2cf86b1487698258b60c3ac9e9df82c` |
| RMM ELF | `208110a40dbea82b3c7c5049f2867e16c8df03a9694d3ffde7d079be5a0f7b78` |
| FIT | `78ddf7acd01118e86d8ab689d9539ed6196d7368c5d4a9852190c865ca38b367` |

Proxy/Client/initrd 与原 `build/secure-services-20261019/final/` 一致。
Guest 探针使用独立生成的 initrd；不替换性能包。构建与运行输入的精简指纹见本轮证据。

`scripts/check/check-secure-iommu.sh` 退出0：ASAN/UBSAN 下原表/回收单元、Host 和 Guest
两种 fault-failure 隔离场景、实际 RK 后端 MMIO stub 均通过。覆盖未绑定/未授权、owner、
generation、parking/Guest root 选择、read/write/bus IRQ、双 bank 预校验、root 篡改、
unknown IRQ 拒绝、清除顺序，以及失败不释放 backing。
`scripts/check/check-dma-guard.sh` 退出0，原 GPU/DMA/PM 单元通过。
日志及准确命令在 `build/secure-services-20261019/iommu-irq/{local-checks.json,iommu-unit.log,dma-unit.log}`。

RMM 构建 `cmake --build build/dma-guard-20261018/rmm -j8` 退出0；Host 增量构建显式使用
`LOCALVERSION=-opencca-pmthor-opp3`，Image 内置 release、模块 vermagic 和部署配置核对一致。
固定上游补丁清单与实际 ELF/BSS/BL33 布局检查退出0；固件仅写 SD storage ID 2。

## 独立硬件验证

`firmware-iommu-irq-20261019-a`、`host-iommu-irq-20261019-a` 部署退出0并恢复 Host；
变更前 SD boot/kernel 分区备份保留。部署命令、SHA 和日志分别在
`build/firmware-runs/firmware-iommu-irq-20261019-a/`、
`build/host-runs/host-iommu-irq-20261019-a/` 和对应 `build/lab-runs/<run-id>/`。

测试通过独占 `lab-run.py` 串行执行，先以完整720p达到1000分为门槛，再扩展功能检查。
本轮八项功能运行各自退出0，不继承 #26 的结果。下表命令均以
`python3 scripts/maintenance/lab-run.py --run-id <本行run-id> --` 为前缀；
完整参数数组与66项源码、输入指纹见[精简验收](evidence/secure-services-20261019/iommu-fault-validation.json)。
日志均位于 `build/lab-runs/<run-id>/`。

| run-id | wrapper 后执行的命令 | 退出码 / 判定 | 日志 |
| --- | --- | --- | --- |
| `glmark720-iommu-irq-20261019-a` | `python3 scripts/run/run-realm-xshm.py --images build/secure-services-20261019/final --workload glmark --performance --benchmark-only --suite --profiles glmark-720` | 0；完整33场景720p **1168**，正确性/clean/Host健康/恢复PASS，Realm退出[0,0] | `collected/glmark-720.log、collected/summary.json、host-kernel-health.json` |
| `guest-device-iommu-irq-20261019-a` | `python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/iommu-irq/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/iommu-irq/realm-init --assignment-module build/secure-services-20261019/iommu-irq/host-module/opencca_iommu_assignment_probe.ko` | 0；14/14，含未授权/撤销后FAULT拒绝、Guest绑定与Host代收、parking和Guest真实root空pending检查 | `guest-iommu/result.json、guest-iommu/host-assignment.log、guest-iommu/host-lifecycle.log` |
| `guest-rsi-iommu-irq-20261019-a` | `python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/iommu-irq/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/iommu-irq/realm-init` | 0；17/17，含未授权codec与未供电VOP的FAULT在硬件访问前拒绝 | `guest-iommu/result.json、guest-iommu/host-lifecycle.log` |
| `managed-iommu-irq-20261019-a` | `python3 scripts/run/run-dma-guard.py --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko` | 0；22/22；本轮live GPU扩展及实际DMA仍NOT_RUN | `dma-guard.json、kernel-delta.log` |
| `guest-backing-iommu-irq-20261019-a` | `python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/iommu-irq/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/iommu-irq/realm-init --reclaim-module build/dma-guard-20261018/reclaim-probe-module/opencca_reclaim_probe.ko` | 0；3/3，活跃backing回收拒绝、表项不变和后续释放，完整生命周期健康 | `guest-iommu/result.json、guest-iommu/host-reclaim.log、guest-iommu/host-lifecycle.log` |
| `gpu-backing-iommu-irq-20261019-a` | `python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final --module build/secure-services-20261019/iommu-irq/guest-module/opencca_guest_iommu_probe.ko --realm-init build/secure-services-20261019/iommu-irq/realm-init --reclaim-module build/dma-guard-20261018/reclaim-probe-module/opencca_reclaim_probe.ko --gpu-backing` | 0；3/3，GPU活跃backing回收拒绝、表项不变和后续释放，完整生命周期健康 | `guest-iommu/result.json、guest-iommu/host-reclaim.log、guest-iommu/host-lifecycle.log` |
| `gpu-pm-iommu-irq-20261019-a` | `python3 scripts/run/run-gpu-pm-regression.py --images build/secure-services-20261019/final --kvm-probe build/secure-services-20261019/physical-mmio/opencca_kvm_mmio_probe --lease-monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko --workload compute --uart-capture` | 0；双Client各17项API、计算/权限/IRQ通过；RMM GPU租约峰值5559，最终GPU/DMA/查询错误均0，Realm退出[0,0,0] | `gpu-pm-regression.json、host-dmesg-new.log、collected/、rmm-uart.log` |
| `gpu-power-cycle-iommu-irq-20261019-a` | `python3 scripts/run/run-gpu-power-cycle.py --module build/secure-services-20261019/device-assignment/power-module/opencca_gpu_power_probe.ko --kvm-probe build/secure-services-20261019/physical-mmio/opencca_kvm_mmio_probe` | 0；4项电源/恢复检查及KVM11项；真实domain on→off-0→on，RMM 0→8→0，内核健康与环境恢复 | `gpu-power-cycle.json、power-cycle-kernel.log、power-cycle-uart.log、kvm-mmio.json` |

两轮 workload 原始日志已回收并逐文件对照板端 SHA，见各自
`collected/collection-hashes.json`。Guest三类测试的Host完整生命周期检查均通过。
Host引用释放日志的0不是RMM租约数；5559来自独立租约监视器。
上述FAULT实机正例是在空pending状态读取、验证真实root；实体故障恢复命令仍只有MMIO stub覆盖。

### 独立物理访问负例与保留的开发失败

`host-mmio-audit-iommu-irq-20261019-a` 退出 **2**，
`host_mmio_protection=FAIL_BYPASS_DETECTED`。指定Realm已获GPU MMIO时，Host仍可通过
`/dev/mem` 把 `0xfb000028` 从0写成1、读回1并恢复0。无活跃GPU任务；ABI11项、恢复与内核健康通过，
不能抵消物理保护失败。命令为上述wrapper前缀加
`python3 scripts/run/run-kvm-mmio-probe.py --probe build/secure-services-20261019/physical-mmio/opencca_kvm_mmio_probe --audit-host-mmio --uart-capture`。
日志在同名run的 `kvm-mmio.json、kvm-mmio-probe.log、kernel-dmesg.log、rmm-uart.log`。

本轮首版汇总脚本在720p硬件退出0后，因尚未回收 `collected/glmark-720.log` 而退出1。
修正日志回收与续跑后，校验原始日志SHA和1168分门槛，再执行后续项目；未重复运行或覆盖这次性能证据。
失败原因、退出码和处理见 `build/secure-services-20261019/iommu-irq/development-failures.json`。

## 性能记录

改动目的｜将managed IOMMU故障寄存器操作迁入RMM并修复绑定失败引用保留｜
对照Host #26 / RMM device-grant的1173 → Host #27 / 本轮RMM **1168**｜
**−5分 / −0.43%**｜完整720p/33场景、默认256 MiB、GPU请求600/实际594MHz、
null-noop/finish、CPU未锁恒频；Host/RMM同时变化，Proxy/Client/initrd不变，无并行探针｜
`glmark720-iommu-irq-20261019-a`，命令见表，退出0，日志见同名run目录｜
**保留开发候选，只归因组合观测，不宣称稳定回退或提分，不替换原冻结1171/1170。**

对原冻结均值1170.5为 **−2.5分 / −0.21%**。validation为26成功、1已知数值例外、
6无判据、非预期失败0；CPU0–3/600MHz请求在结束后恢复0–1/300MHz。
之前的所有分数、失败与NOT_RUN记录继续保留。文档整理与产物清理本身无新增性能测量。

## 验收后的三端清理

`iommu-irq-cleanup-20261019-a` 退出0，删除 **42文件**，实际文件系统释放
**213,692,416字节（203.79 MiB）**；各端即时空闲增量与所删文件分配字节一致。

| 角色 | 删除文件 | 逻辑字节 | 实际释放字节 | 范围 |
| --- | --- | --- | --- | --- |
| 控制机 | 28 | 515,739 | 585,728 | 本轮两种探针的中间对象、自动生成模块文件与编译索引；保留源码、Makefile和最终ko |
| Pi | 0 | 0 | 0 | 已核查；新固件为ACTIVE、#26为ROLLBACK，完整恢复镜像保留，无本轮废弃候选 |
| RK | 14 | 213,070,720 | 213,106,688 | 三个旧#26及两个本轮backing测试的重复Proxy Image/initrd/reclaim模块；控制机同SHA副本保留 |

命令：`python3 scripts/maintenance/lab-run.py --run-id iommu-irq-cleanup-20261019-a -- python3 build/secure-services-20261019/iommu-irq/cleanup.py`。
精确路径、SHA、mtime/inode、占用检查和结果在同名run的 `cleanup-plan.json、cleanup-result.json`。
逐项核查fd/maps、loop/挂载和实验/刷机进程；文件变化或占用即停止。
当前构建与运行输入、最新assignment/RSI复验输入、原冻结组合、#26完整回退分区、
Pi当前/回退/恢复镜像、全部日志及失败证据、基础rootfs和模型均保留。
此前181文件/3,985,047,552字节及随后单文件856,064字节的清理记录保持原值，不重写历史统计。
最终资源记录：`build/secure-services-20261019/iommu-irq/resources-after.json`。
该检查退出0、issues为空；两端无实验进程，RK无loop，Pi既有系统swap loop保留。
Host最终为#27、pmthor、CPU0–1、300MHz/userspace，回读见同目录 `final-host-state.json`。
清理未改运行代码、无新增性能测量。

Notion更新后回读确认原已实现7项、未实现/部分实现7项和历史状态6项均保留；
82个原证据标识及12个新run-id无缺失。仅逆转本轮新增段落与历史标题标注后，
原正文逐字一致，未覆盖任何旧候选。见[条目保留审计](evidence/secure-services-20261019/notion-iommu-fault-preservation.json)。

## 保留的缺口

- 实体 IOMMU 页故障/bus error 注入仍未执行；MMIO stub 验证不是实体故障验收。
- codec 数据 DMA、完整 Guest codec 驱动直通、NPU 负载未执行。
- Host #27 活跃GPU映射28项扩展未重跑；#26独立28/28及1171分保留，不继承为本轮PASS。
- Host 直接物理任务 MMIO、真实页表和配置的硬件封堵未完成；原 MMIO/PTE/PL330 绕过证据保留。
- 活跃任务断电、多故障组合、复位失败硬件注入、跨 Client/GPUVM 攻击与长期压力未验收。
- Group submit fence 历史超时继续 UNRESOLVED；Provider replacement、Native、1080p、NCNN 本轮未重测。
- 原冻结1171/1170及各历史候选原始分数、失败、未执行项均保留，本轮不替换冻结基线。
