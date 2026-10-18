# 当前基线的 Git 同步与发布检查

日期：2026-10-18。目的：将已认可的 RMM-only / P42 + BO 容量修复、memfd 退役、运行载荷、测试证据及代码原理文档固定到 Git，组件先推送，再更新父仓库指针。

## 当前同步状态

已通过 SSH 验证 GitHub 身份，并按 RMM / 内核 / VMM → OpenCCA → 主仓库顺序同步。下列 5 个组件均已推送到各自 `origin/main`，通过 `git ls-remote --heads origin main` 核对完整 SHA 后才更新父仓库指针。主仓库的代码、固定载荷和文档由包含本报告的发布提交统一固定；主仓库自身 SHA 以远端 main 为准，不在提交内容中循环嵌入自身哈希。全程不强制推送、不改写历史。

首次 HTTPS 推送曾因未配置凭据退出 128；用户配置 SSH 后恢复同步。该失败保留在本机发布日志中，不能当作成功推送。

| 组件 | 本地提交 | 同步状态 |
| --- | --- | --- |
| `opencca/tf-rmm` | `8b92ea3d2dec2229bad084654cdaae0a57b9b243` | 已推送；远端 main SHA 已核对 |
| `Linux-Guest-GPU` | `3cd87b3eedc675f9f1c6ce1cc22f41451da1614a` | 已推送；远端 main SHA 已核对 |
| `Linux-Host-GPU` | `cfe4c5d6ebc8667bb23b096a42bde37dbd528455` | 已推送；远端 main SHA 已核对 |
| `firecracker/Firecracker-CCA-MZH` | `250f1493b5050c88b91c346c7af03e1134d8123f` | 已推送；远端 main SHA 已核对 |
| `opencca` | `748e7d35e228914e746e4814bb1502e749ab0315` | 已推送；含 tf-rmm 指针、补丁及布局检查 |
| 主仓库 `gpu` | 本报告所在的发布提交 | 固定组件指针、载荷、配置、文档及脱敏证据 |

组件版本见[发布版本清单](evidence/git-publication-20261018/components.json)，离线检查见[发布验证清单](evidence/git-publication-20261018/validation.json)。本机 push URL 使用 SSH，公开仓库与子模块的 HTTPS clone URL 保留。

## 本次发布准备内容

- 固定 RMM 认证通道、分段 RTT 共享与撤销、可信 IRQ、GPU lease 策略与逻辑测试。
- 固定 Guest 执行计划、原生 fence 完成 cookie、快照回收、BO extent 分配，以及对应 Host 配套改动。
- 删除历史 Host memfd broker、VMM 外部共享窗口及旧测试入口，保留真实使用中的 vmshm 队列和对象协议。
- 保存当前 Realm 内核、initrd、VMM 压缩载荷及逐文件哈希；固定 Host/直通历史参考载荷仍独立标注版本。
- 整理当前文档入口与历史归档，加入[代码与原理讲解](REALM_COMMUNICATION_AND_GPU_EXECUTION_CODE_WALKTHROUGH_20261018.md)。

发布准备未修改 GPU 执行代码，也未重建或替换已测镜像。新增调整仅涉及：将现有 `RSI_LOG_LEVEL` 构建配置准确归档到 OpenCCA 补丁与 SHA 清单；移除仓库 skill、历史命令示例和控制机脚本中的默认密码；资源检查工具在无密码环境变量时使用 SSH 密钥路径。本机私有 skill 的用户配置保留。原始运行日志、凭据、token、编译缓存不提交。

## 检查与已知限制

| 检查 | 命令 / 范围 | 退出码与结果 |
| --- | --- | --- |
| RMM 策略逻辑 | `bash scripts/check/check-rmm-xshm-events.sh` | 0 / PASS：endpoint、memory、GPU lease、IRQ；ASan/UBSan |
| 固定补丁 | `python3 opencca/scripts/setup/apply-local-patches.py --check` | 0 / PASS：6 个补丁及 3 个 loader copy；不 reset 上游 |
| 运行载荷 | `python3 scripts/artifacts/restore-runtime.py --check` | 0 / PASS，日志 `build/git-publication-20261018/runtime-check.log` |
| 脚本语法 | 全部维护入口的 `bash -n` / Python `ast.parse` | 0 / PASS，33 个脚本 |
| 固定 rootfs 与源归档 | 对照 rootfs/runtime manifest 的大小及 SHA-256 | 0 / PASS，2 个 rootfs 与 2 个源归档 |
| skill 元数据 | `skill-creator/scripts/quick_validate.py`，3 个仓库 skill | 均 0 / PASS |
| 认证选择 | 资源工具的环境变量密码 / 无密码 SSH 路径 | PASS；未连接设备 |
| 凭据检查 | 改动文本及运行归档中的小型文本输入 | 未发现凭据/token 遗留；本机私有 skill 不纳入提交 |
| Git 空白检查 | 源码与脚本 `git diff --check` | PASS；嵌套 `.patch` 的 diff 上下文保留原始空白，按补丁完整性检查 |
| 完整 checkout 检查 | `python3 scripts/check/check-checkout.py` | 0 / PASS：父指针已更新，33 个脚本、运行载荷、源归档和两份 rootfs；日志 `build/git-publication-20261018/checkout-check.log` |
| 本次硬件测试 | 未启动板端工作负载 | NOT_RUN，不追加新的性能结论 |

机器可读检查记录位于 `build/git-publication-20261018/local-checks.json`；Git 提交/推送原始输出也在该忽略目录，未提交原始日志。之前 VMM 测试目标编译失败仍未解决，见[退役报告](MEMFD_RETIREMENT_20261018.md)。当时补丁清单 FAIL 继续作为历史事实保留；本次已通过归档现有构建配置修复其可恢复性，不改写旧证据。更早的 Group submit fence 超时记录仍保留。

## 性能与版本边界

改动目的｜固定已认可基线及恢复流程｜清理前 1161 → 清理后已测 1157｜−4 / −0.34%｜既有单次测量，不证明稳定回退｜`memfd-retirement-720-20261018`，退出 0，命令与日志见[退役验收](MEMFD_RETIREMENT_20261018.md)｜保留为 baseline。

**本次 Git 同步准备没有新增性能测量；文档整理未改运行代码，不据此宣称提分。** 既有清理后 720p 1157 / Native 参考 1437；双 Client 功能使用 `memfd-retirement-dual-20261018`，退出 0。完整命令、输入和日志索引见退役验收。其他历史结果不自动变成本次提交的全量 PASS。

RK3588/OpenCCA GPT/GPC 模拟边界、缺少跨 Group shadow GPU 页表隔离、尚无完整远程证明/多 vCPU/长期压力验收的限制不变。
