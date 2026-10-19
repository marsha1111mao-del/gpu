# GPU MMIO：Host 拒绝访问与 Realm 资源归属

**2026-10-20平台前提：** 页表/关键配置、任务MMIO及未授权CPU/DMA访问的物理保护现明确假设目标平台已提供，不列为模拟工程待开发项；本报告原物理绕过结果和历史结论保留。当前完成范围见[平台假设](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)。纯文档整理，未改运行代码，无新增性能测量。

**后续失败项复核：** 当前选定模拟主流程已通过，Guest授权探针版本预检与异常清理已补齐；原失败逐条保留。用户最新口径以模拟行为和总体设计一致为准，真实物理隔离及权限穷举作为边界，不作为本轮门槛。最新结论及复测见[失败项复核](GPU_FAILURE_STATUS_AUDIT_20261019.md)，下文为此前阶段记录。

日期：2026-10-19。Host #31 / protected hVHE / RMM timer v6。
整体 **PARTIAL / INCOMPLETE**。本报告接续
[Host #29 验收](GPU_PROTECTED_REALM_VALIDATION_20261019.md)，保留此前所有失败与未执行项。
[结构化证据](evidence/secure-services-20261019/host-mmio-enforcement.json)记录每次完整命令、
退出码、run-id、日志目录和本轮源码哈希；原始运行日志不纳入源码。

## 设计方向：RMM 管资源归属

按用户最新要求，**不引入 EL2 接管普通 VM 页表的方案**。
GPU 任务 MMIO 由 RMM 记录指定 Proxy Realm 的 owner，并在建立 Realm RTT 映射时验证
owner、物理区间、IPA 和大小；其他 Realm 即便改用别名或覆盖该区间的大块映射也必须被拒绝。
代码入口为 `runtime/core/opencca_gpu.c:opencca_gpu_mapping_allowed` 和
`runtime/rmi/rtt.c:map_unmap_ns`。

这分为两个实际执行条件：

| 边界 | 执行机制与当前证据 |
| --- | --- |
| 指定 Proxy 与其他 Realm | RMM 掌握 Realm RTT，按 owner 校验 GPU 物理区间；本轮第二 Realm 拒绝检查通过。 |
| Realm 资源与 Host / 普通 VM | 必须有独立于不可信页表的物理访问强制检查。当前 owner 记录和 RMM 自身的 `MT_REALM` 映射属性不能替代它；普通 VM 绕过已实测。 |
| Host 电源权限 | 保留板级供电、时钟和合法 OPP；GPU 内部 reset、撤销和回收由可信状态机协调，不开放工作态任务寄存器。 |
| GPU 与其他设备 DMA | 单独验证 GPUVM、IOMMU 真实页表和 backing 生命周期；CPU 的 MMIO 检查不代表 DMA 隔离。 |

真实 RME 的 GPT/GPC 区分物理地址空间，**不以单个 Realm 身份区分 owner**：
Realm 之间仍需 RMM 的 RTT 授权。只有平台支持并对该 MMIO 实际执行所需的物理访问检查，
才能用资源归属封堵 Non-secure Host / 普通 VM，而无需接管普通 VM 页表。
当前 RK3588/OpenCCA 不能据软件标记宣称已经满足这一条件。
这里讨论 CPU 访问 GPU 寄存器，不改变场景二“不依赖 GPU 数据路径外置 SMMU S2 /
GPU GPC 隔离”的前提。

## 本轮运行代码与输入

Host stage-2 的可信建表入口拒绝与 GPU `0xfb000000..0xfb200000` 重叠的区间，
懒映射先裁剪区间再选择块大小，防止邻接大块覆盖。特定拒绝返回 EL1 异常，
内核 nofault 访问返回 `-EFAULT`，用户访问收到 `SIGBUS/BUS_OBJERR`。
该机制目前限制 Host CPU，不能扩展解释为普通 VM 或 DMA 同样受限。
当前规则在 protected 模式下也限制空闲 Host；Host 原生 GPU 路径未在本候选重新验收。

内核探针验证两个并存 ioremap 别名及重新访问；用户探针验证固定地址、信号及读写错误。
普通 VM 探针先完成 RAM 0x40→0x41→0x40 控制，再在指定 Realm 持有设备时测试真实 GPU 页。
任意异常、无法运行和未完成诊断都不能判为安全 PASS。

| 输入 | SHA-256 / 身份 |
| --- | --- |
| Host #31 `host-Image-v2` | `8c277a621abcc8cf40c2801176f25ca62fff795be6e8a0324e8d64325040999d` |
| Host config | `87f30afabaad65d94a331e8e07f8624a600c1e090888986e548aa50935a693f8` |
| RMM timer v6 ELF | `58127713a4d9dc0d0826ba791270be53a0f79755a8e7f1735546ca27ea9d3bad` |
| 固件 FIT | `8dfa6df1d21b88c61fad094b4b99a747c3a2f755d054d5a94eba1e2bae160fed` |
| Realm 包 | `build/secure-services-20261019/final/`；每次运行独立校验 |
| Host 回退 #29 | `build/secure-services-20261019/host-mmio/rollback/` |

Host 内置 release 与模块均为 `6.12.0-opencca-pmthor-opp3`，增量构建显式传
`LOCALVERSION=-opencca-pmthor-opp3`。Host #30 仅完成启动，随后差异审查发现异常重构
遗漏 Guest 向量 PC 赋值；已恢复并构建 #31。**#30 已替代，不属于工作负载验收候选**，
其部署和修正证据继续保留。

## 实测状态

硬件测试均通过 `scripts/maintenance/lab-run.py` 获取 Pi / RK 独占锁。
每项完整命令与退出码见结构化证据，原始路径为 `build/lab-runs/<run-id>/`；
控制机 stdout 另存 `build/secure-services-20261019/host-mmio/`。

| run-id | 退出码 / 结论 | 证据与范围 |
| --- | --- | --- |
| `host-mmio-denial-baseline-20261019-a` | 2，历史绕过复验 | #29 仍可写 IRQ mask 0→1→0；新探针未丢失绕过检测能力。 |
| `host-mmio-denial-deploy-20261019-a` | 0，仅启动 | #30，已替代；保留遗漏与修复记录。 |
| `host-mmio-denial-deploy-20261019-b` | 0，部署/启动 | #31，release/配置、RME、pmthor 与资源恢复检查通过。 |
| `glmark720-host-mmio-denial-20261019-a` | 0，完整720p **1159** | 33场景；validation 26成功/1已知例外/6无判据，非预期失败0；BO/export/VM bind/提交错误0；Host/Guest健康、Realm退出[0,0]、CPU0–1/300MHz恢复；`collected/` 及校验清单。 |
| `host-kernel-mmio-denied-20261019-a` | 0，HOST_CPU_ACCESS_DENIED | 两个 ioremap 别名，10项错误均为−14；11项owner/OPP/释放、模块卸载及内核健康通过；`kvm-mmio.json`。 |
| `host-devmem-mmio-denied-20261019-a` | 0，HOST_CPU_ACCESS_DENIED | 5项错误均−14，信号7/code3；11项owner/OPP/释放及内核健康通过；`kvm-mmio.json`。 |
| `ordinary-vm-mmio-audit-20261019-a` | **2，FAIL_BYPASS_DETECTED** | RAM控制通过；指定Realm持有GPU时，普通VM仍可对0xfb000028写0→1→0并恢复；11项owner/OPP/释放和健康通过不能抵消此失败；`kvm-mmio.json`。 |
| `managed-iommu-host-mmio-20261019-a` | 0，22/22 | 真实codec root/parking/解绑/重绑与准入；live GPU映射和实际DMA仍NOT_RUN；`dma-guard.json`。 |
| `gpu-power-host-mmio-20261019-a` | 0，所列电源检查通过 | 空闲domain on→off→on、非法OPP拒绝、恢复后KVM11项与健康；`gpu-power-cycle.json`。 |
| `guest-rsi-host-mmio-20261019-a` | 0，17/17 | 实际Guest domain/map/query/unmap及准入负例；Guest与Host生命周期健康；`guest-iommu/result.json`。 |

本地 `bash scripts/check/check-opencca-host-mmio.sh` 退出0：
ASAN/UBSAN 下真实生产区间/异常辅助函数18581组区间、393216组PSTATE/向量组合通过；
日志 `build/secure-services-20261019/host-mmio/unit.log`。
单元测试不替代真实异常入口和物理访问负例。

统一性能记录：限制 Host 任务 MMIO｜
Host #29 / timer v6 **1152 → Host #31 / timer v6 1159**｜
**+7分 / +0.61%**｜
同完整33场景720p、256MiB、null-noop/finish、GPU请求600/实际594MHz、CPU未锁恒频；
Host stage-2 与异常处理同时变化，单轮仅记录组合观测｜
`glmark720-host-mmio-denial-20261019-a`、退出0、命令见结构化证据、
日志 `build/lab-runs/glmark720-host-mmio-denial-20261019-a/collected/`｜
保留局部实现，整体待验证，不替换原冻结1171/1170，不宣称稳定提分。

## 保留的失败与未执行项

- RMM 拒绝第二 Realm 是已验证行为；当前平台的普通 VM 物理绕过仍未解决。
  后续沿资源归属与平台物理访问检查推进，不新增普通 VM 页表接管。
- Host #31 双Client计算/API矩阵、完整攻击/故障矩阵、其他设备DMA绕过封堵未执行完成；
  #29与更早PASS不继承。历史Group submit fence超时、故障注入和provider replacement等缺口继续保留。
- 不将资源owner登记、pKVM启动、Host直接访问拒绝或managed-IOMMU正例称作完整硬件隔离。
- 本报告当时的完整开发/安全验收未完成，三端最终清理为 **NOT_RUN**；后续2026-10-20已完成[废弃产物清理](WORKSPACE_ARTIFACT_CLEANUP_20261020.md)，未改运行代码、无新增性能测量。硬件能力按页首平台假设处理。
  保留失败证据、当前运行输入、#29回退、SD分区备份与完整恢复材料。
- 本次按用户方向修正文档未改运行代码，无新增性能测量；1159及上述结果均为已完成运行的登记。
