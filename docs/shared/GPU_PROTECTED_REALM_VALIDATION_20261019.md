# 场景二：受保护 Host 与实际 Realm 运行

**后续状态：** 本文保留Host #29阶段的全部结果与失败；当前#31已分别验证Host内核/用户直接MMIO访问拒绝，普通VM仍能绕过，完整720p1159（对1152为+7/+0.61%）。最新资源归属设计、输入及未执行项见[后续验收](GPU_HOST_MMIO_ENFORCEMENT_20261019.md)，不继承本文PASS。

日期：2026-10-19。接续[受保护EL2兼容性与内核别名负例](GPU_PROTECTED_EL2_COMPATIBILITY_20261019.md)。
本轮修改了Host、RMM和U-Boot运行代码；此前#27的结果作为历史保留，不继承为本轮PASS。
整体仍为 **PARTIAL / INCOMPLETE**，Host物理任务MMIO强制保护 **NOT_IMPLEMENTED**。
Notion原已实现7项、部分实现7项、原失败/NOT_RUN/未解决6项及后续历史证据均保留。

## 实现与边界

- Host启用`CONFIG_KVM_ARM_OPENCCA`，允许EL1 Host初始化Realm；Realm避开普通pKVM
  shadow VM创建/销毁及普通VMID上下文更新，修复EL1 Host的REC VGIC LR复制。
- 普通VM与Realm使用硬件VMID的下半区/上半区，RMM拒绝下半区Realm VMID；两端都使用
  实际硬件位宽，本板为16位。这不证明恶意Host无法在普通VM路径伪造上下文。
- U-Boot不再覆盖extlinux追加`maxcpus=2`；主启动项在protected模式下初始化4个CPU，
  完成特征核验后恢复CPU0–1。rescue启动项保持原内容，未放宽pKVM CPU特征检查。
- OpenCCA定时器保留Guest原始CNTx_CTL，通过GIC redistributor屏蔽已断言的timer PPI，
  保存/恢复原使能状态，并限制pending退休轮询次数。移除覆盖旧状态导致比较失效的逻辑、
  修改Guest IMASK的路径和SIMD过渡屏蔽补丁。RK平台按MPIDR匹配redistributor。
- 固件只替换指定U-Boot或RMM载荷；保留已部署BL31/FDT/idbloader，检查FIT哈希和内存布局。
  部署入口还要求`KVM_CAP_ARM_RME=1`，不能只凭SSH/uname称Realm固件部署成功。

这些改动补齐运行兼容性，**没有**增加GPU/IOMMU物理范围的Host stage-2拒绝规则、
普通VM访问封堵、RMM/pKVM可信页面交接或其他设备DMA封堵。
既有Host内核和`/dev/mem`物理写入绕过证据继续有效；本候选已独立复验Host内核负例，
protected模式下仍能修改任务IRQ mask，判定 **FAIL_BYPASS_DETECTED**。
GPU内部电源/reset也不能作为Host直接操作任务MMIO的例外，职责见
[MMIO与受限PM边界](GPU_MMIO_PM_COORDINATION_20261019.md)。

## 当前输入

控制机包：`build/secure-services-20261019/protected-realm/`。
板端Host为`6.12.0-opencca-pmthor-opp3 #29`，配套模块release相同。

| 输入 | SHA-256 |
| --- | --- |
| `host-Image-v2` | `c2c524a875667f59baa4a271213b57b02c1f9752fb395c90b59f1ed046837aa6` |
| `firmware-v6/tf-rmm.elf` | `58127713a4d9dc0d0826ba791270be53a0f79755a8e7f1735546ca27ea9d3bad` |
| `firmware-v6/u-boot.itb` | `8dfa6df1d21b88c61fad094b4b99a747c3a2f755d054d5a94eba1e2bae160fed` |
| `firmware-v6/idbloader.img` | `dbaa953f5cd962ee096dd727d7331077120bb3ba713e50734d816c9f346bf126` |

主启动参数包含`kvm_arm.mode=protected maxcpus=4`，启动后空闲CPU集合为0–1。
Realm包仍为`build/secure-services-20261019/final/`，输入哈希由每次runner独立记录。
原`final-inputs.json`和失败v4的`timer-inputs.json`保留历史身份，不作为v6清单。

## 独立测试与失败记录

以下硬件命令均由`python3 scripts/maintenance/lab-run.py --run-id <run-id> --`包裹，
部署/重启另加`--allow-rk-reboot`。完整参数与返回码见每个run的`result.json`；
原始日志在`build/lab-runs/<run-id>/`。所有失败保留。

| run-id | 结果 | 主要证据与限制 |
| --- | --- | --- |
| `kvm-mmio-vmid-split-20261019-a` | rc1，FAIL | 新Host使用16位VMID、旧RMM仍按8位，CREATE_RD失败；随后修正RMM位宽。 |
| `protected-realm-boot-20261019-a` | rc0，启动/探针通过 | protected hVHE、RME能力1、RD/owner/MMIO/PM探针11/11；未证明REC执行。 |
| `trusted-vmid-protected-20261019-a` | rc0，6/6 | `run-opencca-vmid-probe.py --module .../vmid-module/opencca_vmid_probe.ko`；RMI VMID正负例及清理通过。 |
| `glmark720-protected-realm-20261019-a` | rc1，FAIL，无分数 | 启动只初始化2个CPU，pKVM拒绝未经特征核验的CPU2上线；未启动VM。 |
| `firmware-protected-cpus-20261019-a` | rc0，启动/热插拔通过 | `deploy-boot-cpu.py`；主启动项4CPU，rescue原样，protected/RME1，CPU2/3上线后恢复0–1；`boot-cpus.json、hotplug.log、extlinux-*.conf`。 |
| `glmark720-protected-realm-20261019-b` | rc1，FAIL，无分数 | Proxy与Client实际Linux/REC启动并到达XSHM_READY；256MiB共享池推进到2944/65536后命令超时，未进入glmark；`collected/summary.json、collected/、uart.log`。 |
| `firmware-protected-timers-20261019-a` | rc1，FAIL | v4平台映射数受旧CMake缓存限制，RMM初始化-34；Host可登录但RME0、pmthor未绑定。 |
| `firmware-protected-timers-20261019-b` | rc1，FAIL | v5映射数已改4，但GICR位于UART之后，不满足映射排序，RMM初始化-1；新部署检查正确拒绝RME0。 |
| `firmware-protected-timers-20261019-c` | 外层rc1，POSTFLIGHT_FAILED | v6修正计数及排序，部署命令成功、RME1、pmthor恢复；开始时未绑定、结束时pmthor导致gpu_driver前后差异，保留外层失败，不记整轮PASS。 |
| `glmark720-protected-realm-20261019-c` | rc0，所列性能/健康/恢复通过 | v6完整33场景720p **1152**；validation26成功/1已知例外/6无判据，非预期失败0，BO/export/VM bind/提交错误均0；Realm退出[0,0]，Host/Guest内核健康，恢复CPU0–1及300MHz；`collected/glmark-720.log、collected/summary.json、host-kernel-health.json、result.json`。 |
| `host-kernel-mmio-protected-20261019-a` | rc2，FAIL_BYPASS_DETECTED | 指定Realm持有MMIO时，Host内核`ioremap`对`0xfb000028`写入0→1→0，四项访问错误码均0；11/11授权/OPP/释放正例、模块卸载、内核健康及恢复通过，不能抵消物理保护失败；`kvm-mmio.json、kvm-mmio-probe.log、kernel-dmesg.log、rmm-uart.log`。 |
| `compute-protected-realm-20261019-a` | rc0，所列功能/健康/恢复通过 | 两Client各17项API、实际计算、权限/IRQ/内存检查通过；Group submit fence本轮各通过；三个Realm退出[0,0,0]，Host/Guest内核健康。provider replacement仍NOT_RUN；`collected/summary.json、collected/commands.jsonl、host-kernel-health.json、result.json`。 |
| `vmid-protected-timers-20261019-a` | rc0，6/6 | v6上独立复验VMID分区、重复拒绝、销毁后复用，模块清理及内核健康通过；`vmid.json、vmid-probe.log、kernel-dmesg.log、result.json`。 |
| `managed-iommu-protected-20261019-a` | rc0，22/22 | Host真实codec managed-IOMMU、root/parking/撤销及清理、内核健康通过；live GPU映射与实际DMA仍NOT_RUN；`dma-guard.json、kernel-delta.log、result.json`。 |
| `guest-rsi-protected-20261019-a` | rc0，17/17 | 实际Realm中Guest RSI domain/map/query/unmap、owner/授权/供电及FAULT准入负例通过；Guest与Host完整生命周期健康；`guest-iommu/result.json、guest-iommu/host-lifecycle.log、result.json`。 |

性能轮完整命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id glmark720-protected-realm-20261019-c -- \
  python3 build/secure-services-20261019/protected-realm/capture-command.py \
  python3 scripts/run/run-realm-xshm.py --images build/secure-services-20261019/final \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

protected物理负例完整命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id host-kernel-mmio-protected-20261019-a -- \
  python3 scripts/run/run-kvm-mmio-probe.py \
  --probe build/secure-services-20261019/protected-el2/opencca_kvm_mmio_probe \
  --kernel-mmio-module build/secure-services-20261019/protected-el2/kernel-module/opencca_gpu_mmio_probe.ko \
  --uart-capture
```

功能复验命令（分别取得独占锁）：

```bash
python3 scripts/maintenance/lab-run.py --run-id compute-protected-realm-20261019-a -- \
  python3 scripts/run/run-realm-xshm.py --images build/secure-services-20261019/final --workload compute
python3 scripts/maintenance/lab-run.py --run-id vmid-protected-timers-20261019-a -- \
  python3 scripts/run/run-opencca-vmid-probe.py \
  --module build/secure-services-20261019/protected-realm/vmid-module/opencca_vmid_probe.ko
python3 scripts/maintenance/lab-run.py --run-id managed-iommu-protected-20261019-a -- \
  python3 scripts/run/run-dma-guard.py \
  --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko
python3 scripts/maintenance/lab-run.py --run-id guest-rsi-protected-20261019-a -- \
  python3 scripts/run/run-guest-iommu-probe.py --images build/secure-services-20261019/final \
  --module build/secure-services-20261019/iommu-irq/guest-module/opencca_guest_iommu_probe.ko \
  --realm-init build/secure-services-20261019/iommu-irq/realm-init
```

定时器本地单元`bash scripts/check/check-opencca-timers.sh`退出0，ASAN/UBSAN，
生产core及RK后端共131072种状态转换、66个有界pending检查通过；日志
`build/secure-services-20261019/protected-realm/timer-unit.log`。
`check-secure-iommu.sh`、`check-dma-guard.sh`本轮也各退出0，日志为同目录
`timer-iommu-unit.log、timer-dma-unit.log`。RMM构建日志`rmm-timers-build-v3.log`退出0。
单元与构建成功不能代替硬件完整负载。

另保留一次tracefs诊断失败：per-instance `set_graph_function`返回PermissionError，
已关闭tracer并删除本次instance；空trace不作为成功采样。b轮Host timer/preemption
交互存在待查现象；v6的c轮共享池及完整负载已通过，但尚未证明唯一根因或长期稳定性。

## 性能、剩余验收与产物

改动目的｜受保护Host/Realm兼容及定时器修复｜对照#27完整720p **1168** → 本版**1152**｜
**−16分/−1.37%**｜同为完整33场景720p、256MiB、null-noop/finish、GPU请求600/实际594MHz，
CPU未锁恒频；protected模式、Host/RMM、VMID分区、U-Boot CPU初始化和timer机制均变化，
只能归因组合效果｜`glmark720-protected-realm-20261019-c`，上述完整命令，退出0与所列日志｜
**保留运行兼容候选；整体安全未完成，不替换原冻结1171/1170**。

完整720p门槛、正确性/内核健康及资源恢复通过后，已扩展上述API、计算、多Client及管理路径
复验。Host物理MMIO负例仍失败，普通VM绕过、可信控制页、其他设备DMA、故障组合和长期
稳定性仍未闭合。本轮两个Client的Group submit fence通过不覆盖历史超时和长期专项。
provider replacement、v6上的Guest实体设备授权/供电循环、backing回收专项、活跃任务断电、
复位失败注入及完整攻击/冻结矩阵未重新验收；原历史PASS和NOT_RUN逐项保留。

本轮未执行新的三端产物删除；当前运行输入、失败证据、可靠v3与#27配套回退、实际SD分区
备份和完整恢复镜像保留。成功验收后再按产物管理流程核对引用及占用，清理确认废弃的中间产物。

精简机器证据（15个run、99项源码指纹、输入及日志SHA）：
[protected-realm-validation.json](evidence/secure-services-20261019/protected-realm-validation.json)。
完整720p与双Client两轮的回收日志分别8/9文件，已与板端逐文件SHA-256核对一致。
最终资源检查`lab-resources.py --check --output build/secure-services-20261019/protected-realm/resources-after.json`
退出0、issues为空；Pi/RK无实验进程，RK为pmthor/CPU0–1且无loop，Pi既有系统swap loop保留。
资源检查不代表物理隔离验收通过，也未释放任何新增产物容量。
