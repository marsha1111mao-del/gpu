# 开发、测试与板端产物管理

2026-10-17 起作为环境主手册的补充。命令默认从仓库根目录运行。

## 设备职责与目录

| 角色 | 应保留 | 不应逐次累积 |
| --- | --- | --- |
| 控制机 | 固定源码、构建目录、镜像来源、完整测试证据 | 将生成文件混入源码提交 |
| Pi | 刷机工具、当前镜像、必要回退、一个完整恢复镜像 | 各次实验镜像、多个整盘派生镜像、编译缓存 |
| RK3588 | 固定运行树、必要依赖/模型、基础 Guest rootfs、当前运行证据 | 源码副本、编译树、重复 tar 包、未归档的历史日志 |

控制机构建输出放 `build/<实验>/`，运行日志放既有 `GPU-SFTP/log/<模式>/<run-id>/`；
这些目录已忽略。不要将运行日志、设备 token 或编译缓存提交。实验室默认密码仅保留于本机私有 skill；仓库内 skill 副本使用环境变量，不提交实际凭据。

Pi `/tmp` 为约 453 MiB tmpfs，RK `/tmp` 为约 1.7 GiB tmpfs：只用于小型临时文件或挂载点，
不要暂存镜像或日志压缩包。传输流直接落到目标磁盘；容量检查按目标文件系统进行。

## 统一执行流程

1. 先读环境主手册、目标 runner，检查固定版本/补丁清单和设备角色；健康 Host 不刷机。
2. 控制机构建最小变更集合，记录 Image、模块、用户态及配置哈希。内核与模块 release 必须匹配。
   Host 的 LOCALVERSION 可能由 make 命令传入，不保存在 .config；增量构建要重复传入。
   刷写前检查 Image 内的 `Linux version ...` 与目标 `/lib/modules/<release>` 一致，不能只看 `/boot/vmlinuz-*` 文件名。
   缺少后缀曾生成 `6.12.0+` 并导致网络模块不可用，失败及 SD 恢复记录见 Proxy 任务服务实现记录。
3. 执行资源检查，按本次将写入的最大镜像、rootfs 副本、日志量另算工作空间；基础门槛不是容量承诺。
4. 只同步新增或变更的运行载荷。已有匹配运行树可 `--skip-sync`；rootfs 只首次或有意替换时同步。
5. 通过独占入口启动测试；一个 wrapper 包住整套矩阵，子项不重复获取锁。
   启动前记录 runner 哈希；运行期间不修改正在执行的脚本。开发需继续改 runner 时，先固定执行副本并保留其命令和哈希。
6. 每项保存命令、退出码、run-id、配置/镜像哈希、日志位置及语义判定；失败与 NOT_RUN 均保留。
7. 回收本次创建的进程、挂载、loop、socket 和临时目录；确认 CPU 集合、驱动与测试前一致。
8. 拉回本次日志并验证本地副本；评估本次新增文件，将保留项登记，删除已确认不再使用的暂存项。

```bash
python3 scripts/maintenance/lab-resources.py --check \
  --output build/lab-maintenance/preflight.json

python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py --images <冻结包> --workload compute
```

Realm入口只同步变化的冻结输入；历史普通VM的32项PASS不代表当前验收。
`lab-run.py` 按 Pi→RK 的顺序持有 flock（Pi `/tmp/gpu-workspace.lock`，
RK `/run/lock/gpu-workspace.lock`），直到命令及后检查完成。普通测试也必须取得 Pi 锁。
固件开发需要重启 RK 时，显式加 `--allow-rk-reboot`：完成空闲检查后释放 RK SSH 锁，
Pi 锁持续覆盖刷写、重启和后检查，避免连接随重启断开而误杀刷机命令。
新入口 `scripts/run/deploy-rmm-firmware.py` 要求该模式，核查 SD 类型、分区与镜像大小，
先将实际启动区备份到控制机，再仅向 storage ID 2 刷固件，保留 UART、哈希和恢复检查。
该入口不更新 Host 内核或 rootfs；只在验证新固件功能确有需要时使用。
锁冲突不启动测试；已有 Firecracker/broker/刷机进程或 loop 设备时拒绝启动，不自动杀进程。
SSH lease 断开时停止本地子进程组并记录异常；远端遗留资源必须依据本 run 的 PID/日志核查，
不承诺中断本地 SSH 就能终止所有远端进程。

执行证据位于 `build/lab-runs/<run-id>/{result,before,after}.json`；测试 stdout 保持实时，
完整测试日志仍由原 runner 保存。`result.json` 的 COMPLETED 仅表示外层命令退出 0，
不能代替每个 GPU workload 的 correctness 判定。

只读检查支持 `--role pi|rk|all`，记录内存、磁盘、inode、目录占用、挂载、loop 和实验进程。
默认最低门槛：Pi 可用内存 128 MiB、根分区空闲 2 GiB；RK 为 512 MiB / 4 GiB；
两者空闲 inode 至少 10000。实际 workload 仍须使用 runner 的内存门槛和 OOM 保护。
地址/密码接受 skill 列出的环境变量，以及 `PI_HOST/PI_PASSWORD`、`RK_HOST/RK_PASSWORD`。

## Snapshot 保留与删除

不以“文件旧”作为唯一依据。先区分以下角色：

- **ACTIVE**：正在运行或计划下一次验证的镜像，以及相匹配的模块、initrd、固件。
- **ROLLBACK**：最近可靠的回退镜像；重大变更期间保留上一档与变更前备份。
- **REPEAT_TEST**：仍会反复用到的回归或性能基线。
- **RECOVERY**：至少一个完整系统恢复镜像与必要 loader/固件。
- **OBSOLETE**：上述均不属于、已被替代的诊断/中间产物。

当前用户已授权清理 OBSOLETE snapshot，无需每个文件重复询问。不能把此授权扩大为清理
用户源代码、失败日志、当前运行树、模型、基础 rootfs 或整个其他工作区。

删除清单必须使用准确路径，记录大小、修改时间、SHA-256、删除原因与结果。
先查脚本实际输入、符号链接、进程 fd、loop、挂载和刷机活动；文件变化或占用时停止。
必要历史产物先归档到控制机并校验；明确废弃的派生镜像不要求永久归档。
禁止 `rm snapshot/*`、按年龄批量删除，以及不核对内容就用同名文件覆盖备份。

本次保留清单见 [设备检查报告](../archive/20261018/history/DEVICE_RESOURCE_AND_WORKFLOW_AUDIT_20261017.md)。
后续每次换镜像更新保留清单；不要把本次的文件名永久硬编码成清理标准。

## 日志、依赖与缓存

日志按 run-id 保存并直接流回控制机，不在板端 `/tmp` 先生成 tar。
清理板端日志之前，确认控制机完整副本和校验结果，保留失败项、当前诊断项及最新可复验基线。
默认建议只在板端保留最近 5 次成功运行和最近 7 天日志；这是归档后的候选范围，
不是无条件自动删除规则。超出容量先停止新测试并处理归档，不以删证据换一次 PASS。

不要为了“释放内存”执行 drop_caches、关闭桌面、删除 VSCode Server、卸载依赖或停系统服务。
page cache 可回收，关注 MemAvailable 和本次测试增量。未启用的诊断 swap 也先查 fstab 与来源。
NCNN/glmark/Mesa 源码、构建目录应迁回控制机；删除板端副本前核对 runner 是否仍引用。

## 当前尚未消除的旧入口限制

这些约束已落实到新入口和 skill，但旧 runner 不是完全改造后的产物生命周期管理器：

- 直接运行旧 runner 会绕过独占锁；所有操作者应使用统一入口。
- 旧 runner 内部还有全局 `pkill`、旧 `run-logs` 删除、rootfs 目录清理及 tar fallback 覆盖逻辑。
  wrapper 的空闲检查减少误伤机会，但不能防止有人绕过锁并发操作；不要在有其他任务时直接调用旧入口。
- 部分同步仍按整棵 GPU-SFTP 排除目录，未改成完整载荷 allowlist；因此同步前检查预览与源目录，
  不将大源码/编译目录放入待同步树。避免重复发送已准备的运行树。
- 现有 shared runner 会就地注入基础 rootfs，不能宣称它已经使用不可变基础镜像加每次独立副本。

本次不为清理任务变更 GPU 数据路径与全部 runner，也没有重跑 GPU 32 项。
后续重构这些旧路径，应单独提交可审查改动并跑相应硬件回归。

## 固件布局与离线恢复补充

RMM 的 `RMM_MAX_SIZE` 并不足以证明镜像可启动。RK3588 旧 U-Boot 初始装载点为
`0x00a00000`，扩大的 RMM BSS 曾覆盖它，导致 RMM 初始化完成但 Host 不启动。
候选将 BL33 初始装载移至 `0x10400000`；构建和正常部署入口均调用
`opencca/scripts/check-firmware-layout.py`，按 ELF LOAD 内存大小及独立 NOBITS/BSS
检查实际交叠，不能只查固件文件大小。当前固定补丁与 manifest 同步保存装载修复。

Host 已离线时，正常双机预检查无法取得 RK 锁。实际恢复可使用：
`lab-run.py --run-id <恢复ID> --allow-rk-reboot --recover-rk-offline -- <具体恢复命令>`。
该模式仍取得 Pi 独占锁，验证 Pi 角色/资源/无刷机进程，且要求 RK SSH 确实不可达；
不能用于绕过健康 Host 的空闲检查。恢复命令须使用已确认的 SD2 固件/备份和原 CPU 配置，
保存刷写与恢复证据。缺失的 RK 开始状态明确写 NOT_RUN，结束后仍完整审计 Host，
不能声称完成了无法取得的开始/结束对照。恢复成功不替代候选固件或 GPU 测试通过。
