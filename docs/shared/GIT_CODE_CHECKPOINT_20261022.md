# 当前源码的 GitHub 提交快照

日期：2026-10-22。本次按用户要求提交当前开发版本，依次推送 RMM、Guest、Firecracker、OpenCCA，再更新主仓库组件指针。没有改写历史、创建新分支或重新打包运行镜像。

## 已推送组件

| 仓库 | 提交 | 内容 |
| --- | --- | --- |
| `opencca/tf-rmm` | `4815fa05f9ff8265787b2534ccd5a9c10e7f35d7` | 有界GPU页租约容量扩为2 GiB并调整散列桶 |
| `Linux-Guest-GPU` | `29fc19336764df2bd62113849499230d723fd5c6` | 分段BO与Client局部mmap、真实fence在途准入、翻译失败处理及RPC阶段计时 |
| `firecracker/Firecracker-CCA-MZH` | `349436426b2f8264f6010f28944dcb388137b4e4` | 私有转共享后回收旧guest_memfd后备，配套范围校验、聚焦测试及seccomp规则 |
| `opencca` | `2f13284a3c0da42d25df204f11cd80cb419c2e77` | 更新到已推送的RMM提交；原固定上游补丁保持 |

上述组件均推送至各自`origin/main`并通过`git ls-remote --heads origin main`核对。主仓库提交包含本页、测试入口、结果分析脚本、架构说明与配图，其自身提交号以Git历史和远端main为准，不在本页循环嵌入。

## 提交前检查与版本边界

- `python3 opencca/scripts/setup/apply-local-patches.py --check`退出0：六组固定补丁与三个loader副本校验通过；预期的上游补丁差异保留。
- `bash scripts/check/check-rmm-xshm-events.sh`退出0：endpoint、共享内存、GPU租约/可信控制、IRQ策略通过，启用ASan/UBSan。
- 改动Python脚本AST解析、Shell语法、seccomp及摘要JSON解析、本地Markdown链接、Git空白和待提交敏感信息检查通过。
- 原始运行日志、凭据、临时Notion授权、编译缓存和镜像构建目录不进入本次提交；文档配图及脱敏摘要保留。
- 本次未重新构建镜像、未运行硬件负载，旧runtime manifest与恢复归档保持原版本。获取最新源码不等于旧预编译包自动更新；重建和测试需遵循[当前入口](CURRENT_BASELINE.md)及相应报告。
- 完整Firecracker单测已有接口编译失败、Group fence历史间歇超时、Native四并发失败等记录保留，不因本次提交转为PASS。

改动目的｜固定当前源码、测试和文档｜既有RPC诊断720p 1152 → 本次未新增测量｜分差不适用｜提交推送未改运行代码内容，不据此宣称提分｜既有run-id `rpc-breakdown-720-20261022-a`、命令/退出码/证据见[RPC报告](GPU_RPC_CRITICAL_PATH_20261022.md)，其他性能与验证条件见[当前基线](CURRENT_BASELINE.md)｜保留源码快照，独立RPC融合仍未实现。
