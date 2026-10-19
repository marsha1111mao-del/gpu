# GPU MMIO 与可信 PM/复位协调

**当前资源归属方向（Host #31）：** 按用户要求，不引入EL2接管普通VM页表。RMM维护指定Proxy Realm的MMIO owner，并在Realm RTT映射入口核对物理区间；第二Realm拒绝已实测。若要同时阻断Host/普通VM，资源标记还须有实际平台物理访问强制检查，不能仅凭owner或`MT_REALM`声明完成。当前Host直接访问已拒绝，普通VM物理绕过仍FAIL；最新1159分、测试与缺口见[资源归属验收](GPU_HOST_MMIO_ENFORCEMENT_20261019.md)。以下旧候选描述保留其历史范围。

**当前职责划分与电源顺序修复：** Host管理板级供电、时钟和合法OPP；指定Proxy掌握工作态任务MMIO，复位/撤销/页面回收由RMM协调。Host #26已修复平台电源域detach先于devres可信复位的竞态，并验证空闲GPU电源域关闭/恢复。当前实现和独立测试见[设备授权与电源验收](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)；下文早期状态/未执行项按历史边界保留。

**历史阶段记录：** 本文下述 ABI、Host reset 与最终销毁顺序描述早期候选。当前已改为 RMM 真实复位、RSI owner claim/reset、guest_memfd 最终关闭前撤销，见[当前开发验收](SECURE_SERVICES_VALIDATION_20261019.md)。旧构建与失败证据继续保留，不代表当前代码。

日期：2026-10-19。状态：**PM owner 生命周期问题已修复并通过选定硬件验收。**
最终候选、根因、部署哈希、KVM/compute/glmark 结果见
[GPU PM owner 生命周期修复](GPU_PM_OWNER_LIFECYCLE_FIX_20261019.md)。本文早前的
“硬件未执行/凭据阻塞”仅保留为当时本地构建记录，不代表当前板端状态。

## 目标与状态机

### 场景二的权限边界

Host负责板级资源管理，工作态GPU任务寄存器由指定Proxy独占；这个划分成立的前提是
Host的电源权限不能变成修改任务状态、重新授权MMIO或提前释放backing的旁路。
“电源寄存器”不能仅按名称或所在页放行，必须根据操作对GPU状态和内存访问的影响分类。

| 操作 | 权限与约束 |
| --- | --- |
| 板级供电、时钟、合法OPP | Host提出请求并管理板级资源；可信层校验状态和允许范围，必要时先让Proxy停机。不得允许Host任意写共享控制页。 |
| 任务队列、doorbell、地址空间/页表根、MMU配置、任务IRQ配置及清除 | 工作态只允许指定Proxy操作；Host、普通VM、其他Realm及物理别名均不能修改。敏感状态的读取权限也应单独限定。 |
| GPU内部电源、reset、断电重启、owner更换 | 属于可信生命周期操作，由RMM协调Proxy与Host；不能因归为PM而向Host直接开放任务MMIO。 |
| 页面回收与复用 | 停止新任务、撤销访问并确认设备停止DMA后，才能释放租约和backing；失败保留引用并隔离设备。 |

仅将任务MMIO从Host驱动中移除不能证明上述边界成立。还须在Host不能修改的可信执行层
约束Host及普通VM的CPU访问、物理别名、映射重建和控制内存，并独立处理其他设备DMA。
Host可能拒绝调度或切断电源造成拒绝服务；这种可用性限制不能被解释为允许它篡改任务、
重配页表或在GPU仍可能访问时回收页面。

当前状态仍为**部分实现**：软件owner/PM/撤销路径已有选定验收，#31已验证Host直接访问拒绝，
但普通VM物理访问仍能绕过。更早Host直接写入绕过证据保留对应版本范围，
不能宣称已达到“进入工作态后Host不可修改”的完整强制保护要求。
受保护模式启动和Realm能力恢复也不等于物理访问封堵完成；详见
[受保护EL2兼容性与负例](GPU_PROTECTED_EL2_COMPATIBILITY_20261019.md)。

RMM 为单 GPU 维护与 MMIO owner、GPU 页面租约同锁保护的 PM 状态：

| 状态 | 含义 | 允许的后续操作 |
| --- | --- | --- |
| `UNOWNED` | 尚无 Realm 获得 GPU MMIO | 可进入无 owner 的复位/变频，或授予首个 owner |
| `RUNNING` | 一个 RD 拥有 MMIO，可获取页面租约 | 复位、变频、最终撤销，或进入 Realm 销毁前置等待 |
| `RESETTING` / `POWERING` | Host 正在复位或切换 OPP | 仅结束本次过渡；新租约和 MMIO 授权被拒绝 |
| `QUARANTINED` | 复位/变频失败 | 仅允许再次尝试复位恢复；Realm 销毁被拒绝 |
| `REVOKED` | pmthor 已在成功复位后撤销 MMIO 并释放该 RD 页面租约 | 仅允许对应 Realm 销毁 |
| `DESTROYING` | RD 销毁已原子占位 | 拒绝新的 PM 过渡，Realm 销毁完成时清理 owner |

开发 ABI 为 RMI `0xc400016e`（`SMC_RMI_OPENCCA_GPU_PM`），`x1` 取值 0–6，分别表示
复位开始/成功/失败、变频开始/成功/失败和最终撤销。Host pmthor 在每次软复位前后、
OPP 切换前后调用该接口；`pmthor` 仍合法管理时钟、电压、power domain 和 reset 序列。

## 关键顺序

1. KVM 只能在 RMM 授予单 owner 后映射 `0xfb000000/2 MiB` GPU MMIO alias。
2. 页面租约只允许当前 `RUNNING` owner 获取；复位/变频中拒绝新租约，失败进入隔离。
3. 最后一个 KVM VM 引用归零时立即执行 `last VM teardown` 复位并把 RMM 状态切到
   `REVOKED`；RMM 此时撤销 MMIO 并释放该 RD 的页面租约。pinned HPA 仍由 Host 保留，
   待 `/dev/pmthor` 关闭并再次复位成功后释放。
4. 持有 GPU MMIO 的 Realm 在 RMM 状态达到 `REVOKED` 前不能销毁，避免 Realm 销毁先释放
   租约而异步 GPU 或尚未复位的设备仍访问 backing page。
5. 复位失败保留 MMIO owner 与页面租约并进入 `QUARANTINED`；下一次打开/reset 可恢复。
   清理路径不得释放仍处隔离状态的页引用。

这仍是 OpenCCA/RMM 软件协调模型：Host 仍执行合法供电、时钟和 reset 寄存器操作，
本状态机不证明 hostile Host GPC 已强制阻断直接寄存器或页表写入。

## 代码入口

| 模块 | 入口 |
| --- | --- |
| RMM PM 状态与租约联动 | [opencca_gpu_lease.c](../../opencca/tf-rmm/runtime/core/opencca_gpu_lease.c) |
| RMI PM 服务 | [opencca_gpu.c](../../opencca/tf-rmm/runtime/rsi/opencca_gpu.c)、[smc-rmi.h](../../opencca/tf-rmm/lib/smc/include/smc-rmi.h) |
| Realm 销毁前置 | [realm.c](../../opencca/tf-rmm/runtime/rmi/realm.c) |
| Host pmthor 复位/OPP/释放调用 | [pmthor_drv.c](../../Linux-Host-GPU/drivers/pmthor/pmthor_drv.c) |
| Host RMI FID | [rmi_smc.h](../../Linux-Host-GPU/arch/arm64/include/asm/rmi_smc.h) |
| KVM/MMIO/OPP/复位探针 | [opencca_kvm_mmio_probe.c](../../GPU-SFTP/tests/dma-guard/opencca_kvm_mmio_probe.c)、[runner](../../scripts/run/run-kvm-mmio-probe.py) |
| 真实 workload PM 组合回归 | [run-gpu-pm-regression.py](../../scripts/run/run-gpu-pm-regression.py) |
| Guest RSI managed-IOMMU 探针 | [opencca_guest_iommu_probe.c](../../GPU-SFTP/tests/dma-guard/opencca_guest_iommu_probe.c)、[Realm runner](../../GPU-SFTP/tests/dma-guard/run_guest_iommu_probe.py)、[controller](../../scripts/run/run-guest-iommu-probe.py) |

## 本地验证

| 项目 | 命令 / 输入 | 退出码 | 结果 |
| --- | --- | --- | --- |
| GPU 租约/DMA/PM 状态单元 | `scripts/check/check-dma-guard.sh` | 0 | 租约容量、回滚、隔离恢复、撤销、销毁占位 PASS |
| 托管 IOMMU 单元 | `scripts/check/check-secure-iommu.sh` | 0 | 真实表、owner、回滚、隔离与页面生命周期 PASS |
| RMM 构建 | `cmake --build build/dma-guard-20261018/rmm -j8` | 0 | `rmm.elf` SHA-256 `974c92ef1e932827eca274c83d02f49cc2feaecb566dec7ed9ed59ece53c0df1` |
| RMM 部署包 | 固定 `idbloader.img/u-boot/u-boot.itb` 与最终 `tf-rmm.elf` 组合，`check-firmware-layout.py` | 0 | `build/dma-guard-20261018/firmware-final-20261019/`，布局 PASS，哈希见 `final-build-20261019/firmware-hashes.txt` |
| Host Image/modules | 显式 `LOCALVERSION=-opencca-pmthor-opp3` 构建 | 0 | 内置 release `6.12.0-opencca-pmthor-opp3`，Image SHA-256 `cf31f624b9372442842938381eb8917106e9ad4558276cfc0e794012edfd27cb` |
| Host 测试模块 | 匹配 Host O 目录重建 | 0 | vermagic `6.12.0-opencca-pmthor-opp3 SMP preempt mod_unload aarch64`，SHA-256 `3b0c0aab495169a2298c06b71c47dbc02a588e9715793bdd7e249881dde1340e` |
| KVM 静态探针 / runner | `aarch64-linux-gnu-gcc ... -Werror`、`py_compile` | 0 / 0 | 探针 SHA-256 `cc094c621b6a9842db3604ad461f8ef7478db74e65076ab8ef0038c6c332fe69`；硬件未运行 |
| Guest RSI 探针 / controller | `python3 -m py_compile ...`、冻结输入哈希/vermagic/newc 回读校验 | 0 | proxy release `6.12.0-g3cd87b3eedc6-dirty` 与模块 vermagic 匹配；模块 SHA-256 `4b2afb56120cebf9481db18a637be6429ded6351914e72b5a13be6ca7ab19bf7`；候选 initrd SHA-256 `eb7838743719355deb863d99c80ccecc1c74c36175e6ef320e20fadc03eaabbe`，本地解析通过；硬件未运行 |
| 真实 workload 组合入口 | `run-gpu-pm-regression.py --workload compute` | 未执行 | 覆盖 KVM/OPP/复位、双 Client compute、last-VM reset、页释放与 dmesg 负例 |

本地最终构建证据 run-id `local-final-build-20261019`（非硬件 lab-run）：命令与退出码见
`build/dma-guard-20261018/final-build-20261019/result.json`，日志位于其 `logs/` 子目录；
状态为 `PASS_LOCAL_ONLY`，不包含硬件或性能测量。

## 凭据恢复后的硬件顺序

以下仍是待执行计划，不构成 PASS 证据。每个入口单独使用一个新的 `lab-run.py`
run-id，并在进入下一项前确认返回码、日志和 postflight 资源恢复。

1. 部署 RMM 固件包并等待 RK 恢复：
   `python3 scripts/maintenance/lab-run.py --allow-rk-reboot --run-id <ID> -- python3 scripts/run/deploy-rmm-firmware.py --firmware build/dma-guard-20261018/firmware-final-20261019 --run-id <ID>`
2. 部署同 release Host Image 并确认内置 `6.12.0-opencca-pmthor-opp3`：
   `python3 scripts/maintenance/lab-run.py --allow-rk-reboot --run-id <ID> -- python3 scripts/run/deploy-host-image.py --image build/dma-guard-20261018/host/arch/arm64/boot/Image --config build/dma-guard-20261018/host/.config --release 6.12.0-opencca-pmthor-opp3 --run-id <ID>`
3. Guest RSI managed-IOMMU：`run-guest-iommu-probe.py`，要求所有正/负检查与 Guest 内核健康 PASS。
4. Host managed-IOMMU：`run-dma-guard.py --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko`，要求 22 项 root/parking/recovery 与准入检查 PASS。
5. KVM/MMIO/OPP/复位：`run-kvm-mmio-probe.py`，要求单 owner、第二 Realm 拒绝、OPP 往返和释放检查 PASS。
6. PM 真实 workload：`run-gpu-pm-regression.py --workload compute`，要求 last-VM reset、非零页释放且无新增 PM/内核失败。
7. 纯性能轮：`run-realm-xshm.py --workload glmark --performance --benchmark-only --suite --profiles glmark-720`，要求完整 glmark 正确性、内核健康与资源恢复；以 1000 分为门槛并按统一格式记录对比。
8. 最后再执行冻结完整回归/正确性矩阵；Group submit fence 超时回归仍需保留，不得沿用旧 PASS。

保留本地构建过程问题：第一次增量 Host 构建未显式传 `LOCALVERSION`，曾生成
`6.12.0+`；该中间 Image 不作为候选，随即按规范重建为上述 release。未产生硬件影响。

## 未执行与边界

- 未部署 RMM/Host Image，未运行 `lab-run.py` 硬件探针、managed-IOMMU、Guest RSI、
  KVM MMIO/PM、完整 720p glmark、正确性、内核健康或资源恢复检查。
- 当前控制机没有可用 RK SSH 凭据；只读 `resources.audit('rk')` 因认证失败返回 1，
  记录在 `build/dma-guard-20261018/final-build-20261019/logs/hardware-access.log`。
  这是硬件验证的外部阻塞，不得改写为已部署或已执行。
- KVM 探针覆盖 owner 存活期间的 OPP 往返和空会话复位；组合入口覆盖真实 workload
  的最后 VM teardown 与页释放。reset-failure 注入和恢复仍需专门硬件/故障模拟回归。
- OpenCCA 的模拟边界不变：不能宣称 hostile Host GPC、跨 Group shadow 页表隔离、
  完整远程证明或长期压力证明。
- 统一记录：实现 PM/复位协调｜对照版本无同条件新测量 → 未测｜无分差，不能计算百分比｜
  仅本地单元/构建，未运行硬件负载｜本文所列命令、退出码与构建产物；硬件 run-id 不存在｜待验证。
