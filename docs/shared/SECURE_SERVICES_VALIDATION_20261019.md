# 场景二：统一 IOMMU 与 GPU MMIO/PM 开发验收

**2026-10-20当前状态：** 统一安全IOMMU服务及Host与其他IOMMU设备的托管映射控制均已实现、当前范围验收完成。可信页表/控制内存、关键配置、任务MMIO及未授权CPU/DMA访问的物理保护作为目标平台已有能力假设，不再作为模拟工程待开发任务；下文历史缺口及FAIL/NOT_RUN原样保留。见[平台假设与完成范围](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)。纯文档整理，未改运行代码，无新增性能测量。

**失败项当前判定：** 已逐项核对历史失败并在#31上复测，选定模拟主流程通过；原FAIL/NOT_RUN继续保留，最新适用范围见[失败项复核](GPU_FAILURE_STATUS_AUDIT_20261019.md)。按用户最新口径，不以完整物理隔离或权限穷举作为本轮模拟验收门槛。

**历史阶段边界：** 本文记录 Host #23 / RMM page-reclaim 的1167分与当时缺口。
当前 Host #26 / RMM device-grant 为1173分，Guest设备授权/供电生命周期与空闲GPU电源域循环已另行验证；
新增电源顺序竞态的失败和修复见[后续设备授权验收](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)。
下文原已实现、未完成、失败/NOT_RUN和清理记录均保留，不把历史PASS继承给新组合。

日期：2026-10-19。**选定功能与生命周期回归通过；整体安全验收仍为 PARTIAL / INCOMPLETE。**
本文按组织结构记录当前开发候选，原冻结性能基线 1171/1170 保持不变。
Notion「假设场景2实现」同步保留已实现、未实现/部分实现、失败/NOT_RUN/未解决、实现状态与缺口四区；状态变化不删除原条目及历史 run-id。

## 组织结构、实现与边界

| 主体 | 已实现 | 未实现或未验收 |
| --- | --- | --- |
| Client Realm | 授权共享队列、对象句柄和计划引用；Guest RSI 与 Host RMI 共用 IOMMU 核心；非 owner GPU claim/reset 拒绝 | 恶意 GPU 指令、跨 Client 攻击完整矩阵与长期压力 |
| RMM | domain owner/generation、真实 RK 设备页表、root、stall/IOTLB、deny-all parking；GPU/DMA HPA 互斥；活跃 backing 的 DATA_DESTROY 拒绝 | GPT/GPC 仍为 OpenCCA 模拟，不能证明 hostile Host 每次物理访问均受硬件保护 |
| 可信 Proxy / Panthor | session/对象校验、真实 GPUVM、执行计划、原生调度与 fence；RSI claim/reset | owner 是 Host 指定的首个 RD，未做镜像测量/远程证明 |
| GPUVM | Proxy 创建真实 GPU 页表，PTE 使用 RMM 翻译出的 HPA | 跨 Client 越权、Group/GPUVM 绑定强化、页表与控制内存保护、撤销后页复用攻击矩阵 |
| GPU 内置 MMU | 依 GPUVM 完成 GPU VA→HPA | GPU 数据路径没有外置 SMMU S2；租约不是每次访存的外层硬件检查 |
| Host 与其他 IOMMU 设备 | 标准及 managed 直接驱动入口转 RMM；真实 codec IOMMU 验证；绑定期间持续持有时钟/PM，解绑后 parking | Guest BIND 对合法但未分配/未供电 device ID 缺独立授权/PM token 检查；Guest 实体设备 BIND 未验收；NPU 未启用 |
| GPU MMIO / PM | RMM 单 Proxy RD 授权、可信真实复位、受限合法 OPP、撤销 MMIO 后释放租约；guest_memfd 最终关闭前协调回收 | Host 直接物理寄存器/PTE 写入的硬件阻断、完整断电/复位失败硬件注入仍未证明 |

统一服务核心位于 `opencca/tf-rmm/runtime/core/opencca_iommu.c`，真实硬件后端位于
`plat/rk3588/src/rk3588_iommu.c` 和 `rk3588_gpu.c`；Host 接入位于
`Linux-Host-GPU/drivers/iommu/rockchip-iommu.c` 与 `drivers/pmthor/`。
Guest 已验证 domain/map/query/unmap 等 RSI 路径，**不能写成 Guest 已获实体设备分配与供电授权**。

## 本轮根因修复与无效代码清理

加入活跃 HPA 回收拒绝后，旧 runner 只检查负载阶段，把退出时 Host WARNING 漏判为 PASS。
实际顺序是 guest_memfd 最终关闭先于 KVM VM 最终销毁；原 pre_destroy hook 太晚，GPU 仍有租约，RMM 正确拒绝 DATA_DESTROY。

最终修复在 `virt/kvm/guest_memfd.c` 的最终 release、持有 `slots_lock` 且失效 backing 之前，调用
`kvm_arch_gmem_pre_release()`。arm64 RME 仅对绑定 GPU session 的 Realm 发起既有 RMI RELEASE，
由 RMM 撤销 MMIO、完成可信复位、排空租约，再执行原回收路径。失败保留错误和 RMM 活跃页拒绝，不放宽安全检查。
通用弱默认回调供其他架构/非 RME 的 guest_memfd 使用，维持其既有行为；arm64 RME 提供实际实现。

已删除首次修复中错误的普通 private-unmap 提前撤销分支、临时 teardown 诊断、被替代的
`pmthor_regs.h` 和未使用 include；修复 KVM 探针重复 close 及失败路径资源回收。
PM runner 删除没有实际验证用途的 glmark 分支，完整 glmark 使用独立入口。
新增 lease monitor 有真实 PM 回归调用者：只读 RMM 状态，记录非零峰值和最终 GPU/DMA 归零。
Host 引用释放日志计数为 0，不冒充真实 GPU 租约释放数量。

`run-realm-xshm.py`、KVM/MMIO 和 Guest 探针现检查完整退出后的 Host 增量 dmesg；
新增 WARNING/BUG/Oops、释放失败或 ring wrap 均使验收失败，不能只依据远端 workload summary。

## 当前部署输入

| 输入 | 当前值 / SHA-256 |
| --- | --- |
| Host | `6.12.0-opencca-pmthor-opp3 #23` |
| Host Image | `3091c1eabb69453a3f96962a4667b95ea1e9ba58f773d9d012c74d2817f03197` |
| RMM FIT | `a85bb3dbb73d885f372a26dbba31c23d5c580960cfb142602b6e2c12cc7c90da` |
| 已部署 RMM ELF | `c0504d28da33779ddf14248d7b20e62411f23d2470210daefe08974ccee08db0` |
| idbloader | `dbaa953f5cd962ee096dd727d7331077120bb3ba713e50734d816c9f346bf126` |
| Proxy Image | `2f407eb397bb21bef4f891510b976a241d6d98de5305145d98f309ce583222b1` |
| Client Image | `a8bcdb5583ddcb9e1651169222308ad3a29f686af527847640aa6a3080e4f94c` |
| initrd | `c3cdd4fa34c168e528460c9dd63f58354b5b66437c51973415fc5edb60931299` |
| Realm runner | `2b984a21bba288d071fa091181d584ef65fba63f1020853df7fff91c973ff690` |

输入目录 `build/secure-services-20261019/final/`；全部源码/输入指纹见
`build/secure-services-20261019/final-source-inputs.json`。
RMM 删除未使用 include 后，重建 ELF 的所有 PT_LOAD 字节及布局与已部署版本一致，
见 `build/secure-services-20261019/unused-include-load-equivalence.json`；未因此重新刷固件。

Host 构建命令（退出 0，保留与板端模块匹配的 release）：

```bash
make -C Linux-Host-GPU O="$PWD/build/dma-guard-20261018/host" \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  LOCALVERSION=-opencca-pmthor-opp3 -j8 Image
```

构建日志 `build/secure-services-20261019/host-gmem-reclaim-build-b.log`；部署
`host-gmem-reclaim-20261019-b` 退出 0，部署日志在 `build/host-runs/` 与 `build/lab-runs/` 同名目录。

## 最终七项验收

以下均使用当前候选重新运行，外层退出码全部 **0**。每项命令均通过
`python3 scripts/maintenance/lab-run.py --run-id <run-id> -- <下表命令>` 串行执行。
表中命令省略的共同参数 `--images` 均为 `build/secure-services-20261019/final`。
每项外层证据为 `build/lab-runs/<run-id>/{result,before,after}.json`；完整命令另存
`build/secure-services-20261019/final-validation-progress.json`。

| run-id | 命令入口及关键参数 | 结果 | 同名 run 目录内日志 |
| --- | --- | --- | --- |
| `gpu-lease-gmem-reclaim-20261019-b` | `scripts/run/run-guest-iommu-probe.py --gpu-backing`，带 reclaim module/init | GPU 活跃 backing 回收拒绝、表项不变和释放 3/3；Realm/模块退出 0 | `guest-iommu/result.json`、`guest-iommu/host-lifecycle.log` |
| `glmark720-gmem-reclaim-20261019-b` | `scripts/run/run-realm-xshm.py --workload glmark --performance --benchmark-only --suite --profiles glmark-720` | 完整 33 场景 **1167**；validation/clean/内核/恢复 PASS；Realm 退出 `[0,0]` | `collected/`、`host-kernel-health.json` |
| `kvm-mmio-gmem-reclaim-20261019-b` | `scripts/run/run-kvm-mmio-probe.py --probe build/dma-guard-20261018/opencca_kvm_mmio_probe` | 11/11，含 owner/session/销毁；Host 错误为空 | `kvm-mmio.json`、`kernel-dmesg.log` |
| `guest-rsi-gmem-reclaim-20261019-b` | `scripts/run/run-guest-iommu-probe.py`，带 Guest module/init | 13/13；Guest/Host 全生命周期健康 | `guest-iommu/result.json`、`guest-iommu/host-lifecycle.log` |
| `managed-iommu-gmem-reclaim-20261019-b` | `scripts/run/run-dma-guard.py --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko` | 22/22，真实 codec domain；清理 0，内核错误为空 | `dma-guard.json`、`kernel-delta.log` |
| `guest-iommu-gmem-reclaim-20261019-b` | `scripts/run/run-guest-iommu-probe.py`，带 reclaim module/init | Guest IOMMU 活跃 backing 回收拒绝/不变/释放 3/3；生命周期健康 | `guest-iommu/result.json`、`guest-iommu/host-lifecycle.log` |
| `gpu-pm-gmem-reclaim-20261019-b` | `scripts/run/run-gpu-pm-regression.py --workload compute --uart-capture`，带 KVM probe 和 lease monitor | 双 Client 各 17 项 API、真实计算、权限/IRQ/内存 PASS；三 Realm 退出 0；RMM GPU 峰值 **4401**，最终 GPU/DMA 0，查询错误 0 | `gpu-pm-regression.json`、`realm-workload.log`、`collected/`、UART/dmesg |

完整子命令及哈希存于 [精简验收清单](evidence/secure-services-20261019/validation.json)。
原始日志留在上述 build 目录，不加入源码仓库。PM 的 `host_released_pages_count=0` 与
`rmm_gpu_lease_peak=4401` 明确区分。CPU0–3 测试后恢复 CPU0–1，GPU 从请求 600/实际 594 MHz 恢复 300 MHz。

本地单元 `scripts/check/check-dma-guard.sh` 和 `scripts/check/check-secure-iommu.sh` 均退出 0，
日志分别为 `build/secure-services-20261019/final-dma-unit.log`、`final-iommu-unit.log`；
覆盖 ASAN/UBSAN 租约/DMA、真实复位后端 mock、owner/真实表/回滚/隔离与页回收。

## 性能记录

改动目的｜统一可信服务与回收顺序修复｜对照原冻结 1171/1170，均值 1170.5 → 本版 **1167**｜
**−3.5 分 / −0.30%**｜均为完整 720p、33 场景、默认 256 MiB、GPU 请求 600/实际 594 MHz、
离屏 null-noop/finish；CPU 未固定恒频，Host/RMM/Proxy 组合已变化｜
run-id `glmark720-gmem-reclaim-20261019-b`，命令见上表，退出 0，日志见同名 run 目录｜
**保留开发候选，不替换冻结基线；只归因组合效果，不宣称稳定提分或单因素退化。**

validation 为 26 成功、1 已知数值例外、6 无判据，非预期失败 0；超过 1000 门槛后才完成后续探针/API/计算。
Native、1080p、ML/NCNN 性能未在本轮重测。历史 service-integration 1169 保留；
page-reclaim 1168 因退出 WARNING 不作为健康通过或最终可发布结果。
本次纯文档重排与产物清理未改运行代码，无新增性能测量。

## 失败、未执行与未解决记录（保留）

| run / 条目 | 原结果与当前判定 |
| --- | --- |
| `kvm-mmio-clock-fix-20261019-a` | 历史 rc=1，owner reopen/destroy 失败；后续独立修复验证不删除原证据 |
| `host-kvm-teardown-diag-20261019-a` | 历史诊断 Host，已退出使用；不作为最终输入 |
| `gpu-lease-reclaim-20261019-a` | 原探针 3/3、wrapper 0；后验发现退出 WARNING，健康验收失败，不沿用原 PASS |
| `glmark720-page-reclaim-20261019-a` | 1168、原 wrapper 0/summary PASS，但退出有两条 Host WARNING；`host-kernel-review.json` 明确 `FAIL_HOST_KERNEL_HEALTH` / `accepted_for_release=false` |
| `gpu-pm-page-reclaim-20261019-a` | rc=1；API/计算正例和租约归零通过，但 Host WARNING，整体 FAIL |
| `gpu-lease-gmem-reclaim-20261019-a` | rc=1；首次把 RELEASE 放普通 private-unmap，内存属性切换过早撤销 GPU，Guest 不能 hold backing；错误分支已删除 |
| `secure-services-cleanup-20261019-a` / `-b` | rc=1，Pi 非交互 sudo 不允许该命令，均在生成清理计划阶段停止，尚未删除文件；后续改用已授权凭据从 stdin 提供 |
| Provider replacement | 最终 compute 明确 `NOT_RUN (separate single-Client lifecycle test)`，不称完整生命周期全矩阵 |
| 完整冻结性能/攻击/长期压力 | NOT_RUN；Guest 实体设备授权/PM、reset 硬件失败注入、完整断电故障组合未验收 |
| Group submit fence | 既有超时仍为 UNRESOLVED；本轮 17 项 API PASS 不能消除间歇历史 |
| 直接 PTE / PL330 绕过 | 历史证据保留；无 IOMMU DMA 在既定范围之外，映射入口 PASS 不代表所有 DMA 路径均被封堵 |

## 三端产物清理

`secure-services-cleanup-20261019-c` 退出 0，删除 **148 文件，实际释放 3,812,438,016 字节（约3.55 GiB）**。
只处理已确认 OBSOLETE，保留源码、活跃构建输入、失败日志、
原冻结包、最近可靠回退、完整恢复镜像、base rootfs、模型和依赖。
清理通过 lab-run 独占锁执行，逐文件核对 SHA/大小/mtime/inode、进程 fd/maps、loop/挂载；变化或占用即停止。
Pi 副本还必须有控制机相同 SHA 的保留件。清理清单与实际结果均留在对应 run 目录，不能以逻辑大小冒充文件系统实际释放量。

| 角色 | 删除文件 | 删除逻辑字节 | 实际文件系统释放字节 | 范围 |
| --- | --- | --- | --- | --- |
| 控制机 | 43 | 2,243,952,640 | 2,243,952,640（约2.09 GiB） | 被替代的每 run SD kernel/boot 分区备份 |
| Pi | 54 | 53,850,988 | 53,915,648（约51.42 MiB） | 已有控制机同 SHA 副本的过时每 run loader/FIT |
| RK | 51 | 1,514,470,440 | 1,514,569,728（约1.41 GiB） | 旧部署 Image/kernel-before、旧探针重复 Image/initrd/module |

命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id secure-services-cleanup-20261019-c -- \
  python3 build/secure-services-20261019/cleanup-artifacts.py
```

精确路径、SHA、大小/mtime/inode、保留分类和结果在
`build/lab-runs/secure-services-cleanup-20261019-c/{cleanup-plan,cleanup-result}.json`。
RK 即时 statvfs 原记录误取 `/sys` 角色标记文件系统，原值0不用于结论；
采用同一独占锁下 before/after 审计 `/root/GPU-SFTP` 的可用字节增量1,514,569,728，
与删除文件 allocated 字节一致。原记录保留，修订依据存 `cleanup-measurement-review.json`；没有重复删除。

当前 Host #23、RMM page-reclaim、最终 Realm 包及其构建树、原冻结1171/1170包、可靠回退
Host `580145…`、更换前完整SD kernel备份、Pi完整约3.8 GiB恢复镜像均保留。
所有失败日志保留，Pi未匹配本地保留SHA的候选数为0。
最终只读资源审计退出0：`build/lab-maintenance/secure-services-20261019/after.json`；
无本轮实验进程或新增loop残留，Pi既有 `/var/swap` 系统loop保留；RK pmthor、CPU0–1与300 MHz恢复。
验收结束后重新核对63项源码与11项输入SHA一致，清理未改活跃输入。
