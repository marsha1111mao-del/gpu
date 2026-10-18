# Pi / RK3588 资源检查、snapshot 清理与流程规范

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-17。设备为 Pi `mzh@192.168.31.189` 和 RK `root@192.168.31.18`。
本次仅做环境检查、用户授权的废弃 snapshot 清理和工具/文档验证，不部署新内核，不运行 GPU 回归。

## 检查结论

Pi 的主要问题是旧刷机镜像积累，并非内存泄漏。初次检查根分区约 29 GiB、已用 21 GiB、
空闲 6.7 GiB（76%）；`opencca-flash/snapshot` 约 14 GiB，其中三份旧整盘镜像各约 4 GB。
Pi 内存总计 905 MiB，初次 MemAvailable 约 640 MiB，swap 904 MiB、已用约 43 MiB。
`/tmp` 是约 453 MiB 的 tmpfs，大镜像放入其中可能耗尽内存。

RK 当前 `6.12.0-opencca-pmthor-opp3 #5`，GPU 绑定 pmthor，在线 CPU 为 0–1。
内存总计约 3307 MiB，MemAvailable 约 3 GiB；根分区约 30 GiB，空闲约 14.4 GiB。
检查时没有 Firecracker/broker，也没有遗留 loop 设备。`/tmp` 为约 1.7 GiB tmpfs。
没有证据表明当前板端因开发垃圾发生内存耗尽，但长期日志与构建副本需要生命周期管理。

| 位置 | 约占用 | 处理 |
| --- | ---: | --- |
| Pi opencca-flash/snapshot | 清理前 14 GiB | 核对保留角色，删除旧派生镜像与实验 kernel |
| Pi opencca-flash/log | 257 MiB | 保留历史诊断证据 |
| Pi .vscode-server | 896 MiB | 保留开发环境，不当作垃圾删除 |
| RK GPU-SFTP/log | 2.51 GiB | 保留；下次完成归档校验后按 run-id 清理 |
| RK GPU-SFTP/firecracker-bins | 2.45 GiB | 保留运行内核、二进制和基础 rootfs |
| RK GPU-SFTP/artifacts | 863 MiB | 保留依赖；源码/构建目录列为后续迁移候选 |
| RK /root/opencca-diag.swap | 3 GiB | 未启用、fstab 无引用；本次保留，未扩大 snapshot 删除范围 |
| RK system journal | 约 683 MiB | 未修改系统日志策略 |

Pi 的 `/dev/loop0 -> /var/swap` 属于系统 swap，不是遗留测试挂载，未处理。
没有 drop_caches、swapoff、关闭桌面/服务或删除用户代码。没有更新上游版本或更改网络。

## Snapshot 保留依据

保留目录：Pi `/home/mzh/opencca-flash/snapshot/`。

| 文件 | 角色与原因 |
| --- | --- |
| kernel-opp3-extlinux.img | 当前运行 OPP3 Host；控制机 build/glmark-optimization/host-opp3-deploy/ 另有载荷 |
| opp2-baseline-kernel-partition.img | OPP3 更新前的直接回退 |
| kernel-glmark-dma1-extlinux.img | 近期 DMA/性能对照与回退 |
| glmark-dma1-baseline-kernel.img | DMA 变更前的分区备份 |
| kernel-pmthor-final-session-pfn-20261015.img | 10 月 15 日基线复验候选 |
| kernel-pmthor-joint-session-pfn-20261015.img | 同期联合修复实验的复验候选 |
| kernel-pmthor-rootfs-matched-extlinux.img | 旧版匹配 rootfs 的恢复路径，仍被操作文档引用 |
| opencca-image-rockchip-rock5b-rk3588.img | 唯一原始完整系统恢复镜像；flash.sh 默认 rootfs 输入 |
| idbloader.img / u-boot.itb / tf-rmm.elf / u-boot-rockchip-spi.bin | 固件与恢复资源 |

这些文件按用途保留，不代表本次重新验证了各旧镜像能够启动。今后实验结束继续重新判断，
不要求所有历史回退永久留在 Pi。当前用户明确允许删除无需再用的 snapshot。

清理仅覆盖准确文件名清单；执行前检查 regular file、mtime、刷机进程、进程打开 fd 和 loop 引用，
逐文件计算 SHA-256，复查 inode/size/mtime 未变后删除。没有对已删除废弃镜像保留完整副本；
保留了文件身份、校验和与删除结果。不是通配符删除，也不是自动按年龄回收整个目录。

## 工具与 skill 改动

- 新增 `scripts/maintenance/lab-resources.py`：只读采集角色、内存、磁盘、inode、挂载、loop、目录大小和 Pi snapshot 清单；支持 JSON 与最低资源门槛。
- 新增 `scripts/maintenance/lab-run.py`：RK 侧 flock lease、测试前空闲/资源检查、命令/退出码记录、测试后检查、CPU/driver 恢复比对；不主动终止未知远端任务。
- 重写共享/直通两个 skill：去掉旧绝对工作区、全局 pkill 示例、过时失败结论和在 /tmp 打包大日志的流程，转向统一主手册与维护规则。
- 新增 `gpu-lab-maintenance` skill，将目录角色、snapshot 保留、只读检查和清理证据要求独立描述。
- 按用户要求，skill 明确记录 SSH 与 Pi sudo 默认密码 root，保留环境变量覆盖。
- 三个 skill 已通过本地软链接安装到 `/home/mzh/.codex/skills/`；未覆盖其他 skill。
- 主手册及 AGENTS 增加维护入口；详细规则见 [开发与产物管理](../../../start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)。

独占锁只约束使用 wrapper 的操作者。旧 runner 内部的全局 pkill、旧日志删除、rootfs 清理、
整树同步与就地 rootfs 注入尚未整体重构，本次没有声称这些风险已经消除。
当前使用 wrapper 并先确认板端空闲；后续修改旧 runner 应配合独立硬件回归。

## 验证与证据位置

本地证据目录 `build/lab-maintenance/20261017/`，未纳入 Git。新增 Python 工具通过语法检查，
三个 skill 通过 skill-creator 的 quick_validate，Git diff whitespace 检查通过。

| 验证 | 预期/实际 | 证据 |
| --- | --- | --- |
| RK 上 wrapper 正常命令 | 外层 rc=0，完成前后检查 | build/lab-runs/maintenance-wrapper-final-20261017/ |
| 两会话争用同一 RK 锁 | contender rc=1，未执行子命令；holder rc=0 | maintenance-lock-holder-20261017 / maintenance-lock-contender-20261017 |
| 子命令退出 7 | 外层原样返回 7；锁释放后可再次运行 | build/lab-runs/maintenance-exit7-20261017/ |
| 资源检查初版 | Pi 非登录 PATH 缺少 losetup 导致失败 | resources-after.json；随后修复 PATH 并重新验证 |
| 资源检查修复版 | 两台角色确认，基础门槛通过 | resources-mid.json；最终清理后再采集 resources-final.json |

并发验证脚本及输出位于证据目录的 `verify-wrapper.py`、`wrapper-verification.stdout`。
wrapper 正常运行的 COMPLETED 仅证明该命令退出 0，不表示 GPU 测试通过。
本次 GPU 回归状态为 **NOT_RUN**；历史 32 项结果和 Group fence 超时记录没有被本次检查覆盖。

## 最终清理结果

成功删除 **14 个废弃 snapshot**（2 个整盘派生镜像、12 个实验 kernel），按已分配块统计释放 **9.20 GiB**（9,879,068,672 bytes）。
清理脚本退出码为 0，已从 Pi 移除该临时脚本；本地保留脚本、SHA-256 与逐文件结果。

| 设备 | 最终 MemAvailable | 最终根分区空闲 | 检查 |
| --- | ---: | ---: | --- |
| pi | 625 MiB | 15.87 GiB | 角色与基础门槛 PASS |
| rk | 3033 MiB | 14.40 GiB | 角色与基础门槛 PASS |

Pi 空闲空间由约 6.7 GiB 增加至约 15.9 GiB；RK 未删除运行树或日志，空闲约 14.4 GiB。
Pi snapshot 目录剩余 12 个文件；最终 JSON 的 snapshots 清单与保留表一致。
RK 仍为 pmthor、CPU 0–1，无 Firecracker/broker 或 loop 残留。

删除清单如下；完整 SHA-256、mtime、实际分配大小与删除事件见 `build/lab-maintenance/20261017/pi-snapshot-prune.jsonl`。

| 已删除文件 | 大小 | SHA-256 前 16 位 |
| --- | ---: | --- |
| opencca-image-rockchip-rock5b-rk3588-raw-kernel.img | 3943 MiB | `c8269700f1739c81` |
| opencca-image-rockchip-rock5b-rk3588-extlinux-kernel.img | 3943 MiB | `f5829cbfa1d64227` |
| kernel-extlinux.img | 128 MiB | `5b41a8d86bdc5272` |
| kernel-pmthor-blacklist-extlinux.img | 128 MiB | `622958c41c923952` |
| kernel-pmthor-extlinux.img | 128 MiB | `3e29aff748388b5b` |
| kernel-pmthor-module-diagnostic-extlinux.img | 128 MiB | `2d70a539a90bb7f3` |
| kernel-pmthor-no-host-pfn-guard-20260718-extlinux.img | 128 MiB | `916573ea28cfe687` |
| kernel-pmthor-realm-delegated-20260718-extlinux.img | 128 MiB | `f6ac5f86ef808685` |
| kernel-pmthor-realm-mmio-rmi-20260718-extlinux.img | 128 MiB | `6dda9c9f8611ac48` |
| kernel-pmthor-rootfs-matched-blacklist-extlinux.img | 128 MiB | `4316d9521c1f1494` |
| kernel-pmthor-trusted-gpu-realm-mmio-extlinux.img | 128 MiB | `105f325673dded56` |
| kernel-pmthor-trusted-gpu-realm-mmio-localversion-extlinux.img | 128 MiB | `332f04bc6030015c` |
| kernel-with-initrd.img | 128 MiB | `d85000b2e89744b6` |
| kernel.img | 128 MiB | `eaae4126a077a5bd` |


## 后续 RMM 固件开发的保留项增补

`xshm-memory-firmware-20261017` 部署后，Pi 的
`snapshot/xshm-memory-firmware-20261017/{idbloader.img,u-boot.itb}` 为 ACTIVE，
只保留实际刷写的两份文件。原根目录的同名固件作为 ROLLBACK：已逐字节核对，
它们与部署前实际 SD 的对应内容一致。实际 SD 启动区完整备份及 SHA-256 位于控制机
`build/firmware-runs/xshm-memory-firmware-20261017/`；没有额外复制整盘镜像。

普通测试与固件部署现在都先持有 Pi 独占锁，再取得 RK 锁。固件部署明确使用
`--allow-rk-reboot`，Pi 锁持续覆盖 RK 重启及恢复检查；实际部署已退出 0。
空闲模式、普通持锁及锁冲突拒绝也分别验证，证据在 `build/lab-runs/lab-*-lease-*-20261017/`。
这些是本文最初清理之后的开发变更，不属于上方 14 个文件的删除统计。

### RMM 队列身份版本 / Host populate 修复保留项

- ACTIVE：Pi `snapshot/xshm-memory-identity-firmware-20261017/` 中 idbloader/ITB 两文件，SD2 固件部署退出 0。
- ACTIVE：Pi `snapshot/kernel-rme-populate-extlinux.img`，Host `6.12.0-opencca-pmthor-opp3 #6`，只替换 SD kernel 分区中的 Image。
- ROLLBACK：控制机 `build/proxy-service-v2/host-rme-populate/kernel-before.img`，实际 SD p3 的 128 MiB 完整备份，SHA-256 `e0cb4f31ff053e7bb9ff67677d6e304cc51104471ddd7b0da5a0e9d8417563d8`。
- 保留此前可靠固件/Host 回退，不以新镜像能够启动替代 GPU 回归证明；新 Host 队列验证完成后另记结果。

### GPU lease 索引版本固件保留项更新

`xshm-gpu-lease-firmware-v2-20261017` 部署和环境恢复退出 0 后：

- ACTIVE：Pi `snapshot/xshm-gpu-lease-firmware-v2-20261017/` 的 idbloader/ITB 两文件。
- ROLLBACK：`snapshot/xshm-memory-identity-firmware-20261017/`；该版本已在本次启动失败后实际回退成功。
- 失败候选：`snapshot/xshm-gpu-lease-firmware-20261017/`，存在 RMM BSS 与旧 U-Boot 装载区冲突，禁止重用。
- 失败 UART、实际 SD 启动区备份和修复后的 ELF 布局证据保留在控制机 `build/firmware-runs/`，不另存整盘副本。

上述条目替代此前固件的 ACTIVE 分类，Host 内核保留项不变。失败候选可在证据归档后删除；
运行中的硬件回归结束前不并行执行清理操作。


### RMM 事件 IRQ 版本更新

`xshm-host-trusted-irq-20261017`、`xshm-trusted-irq-firmware-20261017` 部署退出 0，
新组合的三方事件与双 Client 实际计算分别通过，完整 glmark 独立验收：

- ACTIVE Host：Pi `snapshot/kernel-trusted-irq-extlinux.img`，`6.12.0-opencca-pmthor-opp3 #7`。
- ACTIVE 固件：Pi `snapshot/xshm-trusted-irq-firmware-20261017/` 的 idbloader/ITB。
- ROLLBACK：`snapshot/kernel-rme-populate-extlinux.img` 与 `snapshot/xshm-gpu-lease-firmware-v2-20261017/`，组成上一档已验证组合；identity 固件保留为曾实际恢复成功的额外回退。
- 控制机实际备份：`build/proxy-service-v2/host-trusted-irq/kernel-before.img` 和
  `build/firmware-runs/xshm-trusted-irq-firmware-20261017/sd-boot-before.bin`，准确哈希见实现记录。

以上替代先前 ACTIVE 分类。正在执行回归时不同时清理 snapshot；不额外复制整盘镜像。


### 纯 IRQ trace-off 固件、WFI 回退及废弃候选清理

以下替代上文旧 ACTIVE 分类：Host 当前仍为 #7，Pi
`snapshot/kernel-trusted-irq-extlinux.img`；WFI Host #11 已实际回退，源码实验也已撤出。
当前实验固件为 `snapshot/xshm-no-rsi-trace-firmware-20261017/` 的 idbloader/ITB，
纯 IRQ、RSI_LOG_LEVEL=0，无 WFI guard。双 Client 与完整 Realm glmark 功能通过，
但完整负载有 74 次 CSG 超时，性能未合格；准确哈希、失败和测试边界见任务服务实现记录。
`snapshot/xshm-trusted-irq-firmware-20261017/` 留作日志开启的回退/复验组合，
更早的可靠回退和完整系统恢复镜像仍保留。

`xshm-obsolete-snapshot-prune-20261017` 经 lab wrapper 独占执行，退出 0。
已删除五个 OBSOLETE 文件：

- `snapshot/kernel-realm-wfi-extlinux.img`：已撤出的失败 #11 Host。
- `snapshot/xshm-realm-wfi-firmware-20261017/{idbloader.img,u-boot.itb}`：已撤出的 WFI guard 候选。
- `snapshot/xshm-gpu-lease-firmware-20261017/{idbloader.img,u-boot.itb}`：存在 BSS/BL33 交叠的旧失败候选。

删除前核对 Pi 当前配置无引用、无 fd/mmap/loop/挂载占用，逐文件哈希与控制机失败载荷一致，
保留控制机文件及失败 UART/运行证据。删除清单含准确路径、大小、mtime、SHA-256、原因与结果，
位于 `build/lab-maintenance/20261017-wfi-prune/`；外层资源审计在同 run-id 的 lab-runs 目录。
按已分配块实际释放 **138,170,368 bytes（131.77 MiB）**；未删除 RK 运行树、模型、rootfs 或失败日志。
