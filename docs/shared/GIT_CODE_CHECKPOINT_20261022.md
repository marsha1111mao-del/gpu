# 当前源码的 GitHub 提交快照

日期：2026-10-22。按用户要求再次保存当前开发进度；先推送组件，再更新主仓库指针。没有改写历史或创建新分支，冻结运行包和旧发布manifest保持不变。

## 最新源码快照

| 仓库 | 提交 | 内容 |
| --- | --- | --- |
| `opencca/tf-rmm` | `15c7ee14af5deacda757342c169fd98722f58f90` | 新增默认路径不启用的计时通知ABI，供拆分RMM锁与服务时间；未部署上板 |
| `Linux-Guest-GPU` | `206c612afc921bc8b65dcfae210b1db18c858a2e` | TRANSFER捕获不可变快照、导出复用及默认关闭的通知/接收时间戳诊断 |
| `opencca` | `8014f360db0c7d4912a6e0cd4f5c5ee18e586435` | 固定上述RMM提交 |

Host和Firecracker保持下方上一快照版本。主仓库另保存扩展快照语义探针、runner开关、结果审计脚本及[实现与测试报告](GPU_TRANSFER_CAPTURE_20261022.md)。

本次提交前Client/Proxy Image、RMM增量构建及Realm用户态工具构建均退出0；RMM策略ASan/UBSan检查、固定上游补丁校验、Python语法、Git空白和新增内容凭据检查通过。构建日志留在忽略目录 `build/notify-latency-20261022/checkpoint-{client,proxy,rmm}.log`。此次未运行新的硬件负载、未刷固件；新通知计时源码仍待硬件验收，Host调度关联工具与真实GPU完成至Client确认分布未实现。不能把旧冻结包PASS继承给最新源码整体。

改动目的｜固定TRANSFER融合验证成果和通知诊断开发进度｜既有无计时720p关闭1158 → 开启1156，计时轮1149｜融合−2/−0.17%；开启计时较1156为−7/−0.61%｜前两轮同镜像同条件，仅切capture；第三轮增加计时，不独立归因；提交本身无新增性能测量｜run-id、命令、退出码、日志见[TRANSFER报告](GPU_TRANSFER_CAPTURE_20261022.md)｜保留默认关闭候选与未验收诊断，不宣称提分或三项优化全部完成。

## 上一源码快照

以下保留此前 `f22f837` 快照的组件与检查记录，当时依次推送RMM、Guest、Firecracker、OpenCCA及主仓库。

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

改动目的｜固定当前源码、测试和文档｜既有RPC诊断720p 1152 → 本次未新增测量｜分差不适用｜提交推送未改运行代码内容，不据此宣称提分｜既有run-id `rpc-breakdown-720-20261022-a`、命令/退出码/证据见[RPC报告](GPU_RPC_CRITICAL_PATH_20261022.md)，其他性能与验证条件见[当前基线](CURRENT_BASELINE.md)｜保留源码快照；独立RPC融合在该检查点时尚未实现，后续实测回退并撤回。
