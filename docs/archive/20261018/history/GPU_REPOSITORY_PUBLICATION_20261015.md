# GPU 仓库整理、发布与验证记录

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

日期：2026-10-15。部署与测试操作统一见[Agent 手册](../../../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)。本文区分已经完成的验证、历史结果和未解决问题。

## 1. 整理结果

保留已使用的 Guest/Host/RMM/Firecracker 修改，包括映射缓存属性、sync_file snapshot、映射长度复用、PFN 去重引用、device/VM 双持有与最终 reset/free。实现原理及更早故障注入结果见[测试与 Bug 分析](PANTHOR_SHARED_GPU_FIX_VERIFICATION_20261015.md)。

清理明确废弃的旧 raw-FIT mail patch、重复 crypto include、失效的禁用代码和不应吞掉失败的构建 workaround。保留源码实验工具但明确能力边界；临时 Mesa/NCNN、失败实验二进制、生成配置和日志不进入 Git。原始日志与整理前备份仍保留在本地忽略目录，没有作为仓库清理对象删除。

增加固定配置、bootstrap、运行归档校验、checkout 检查和统一回归。OpenCCA 内层上游修改转换为固定基线与 SHA-256 清单管理的补丁；复现不再依赖原开发机未发布的 tracked diff。

首次 tar 同步原先无条件排除 rootfs，已改为按请求调用 SHA 校验的原子同步；单/双 Client 共用 helper。固定运行归档不再重复上传板端。RK 板端已安装 rsync 3.5.0；根据用户要求不再新增 rsync 测试。

## 2. 已推送的组件版本

| 仓库路径 | 提交 |
| --- | --- |
| Linux-Guest-GPU | `d00c872e4eb1ca2f4cd12e94c7759a72ceb9fce9` |
| Linux-Host-GPU | `96b92dccc781163fec4d70209056214b7c376ae1` |
| firecracker/Firecracker-CCA-MZH | `530d114c1ad5b611d5caa1bf909e10755dbcfc38` |
| firecracker/firecracker-deps | `2a2107b481122594f17eea2d16ab991c4daa982c` |
| firecracker/vmshm-broker | `050edcb2c869701ec272a54215c69c951a20071b` |
| opencca | `b4339202a563040d91499dbb4f10b3747e1d612e` |
| opencca/tf-rmm | `3de4fbe9ad5adbf28f66a0d6843abf7647f1115c` |

主仓库的最终提交可用 `git rev-parse HEAD` 获取；组件指针以该主仓库提交为准。不要在文档中反向依赖最终提交自身的哈希。

## 3. 完整硬件回归：32/32 通过

运行 ID：`publication-20261015-full`。Host 为 `6.12.0-opencca-pmthor #10`。原始输出在 `GPU-SFTP/log/regression/publication-20261015-full/`，主输出在 `build/publication-checks-20261015/runtime-regression.log`。这两个原始日志目录不进入 Git；保留的[逐项 summary](../../../shared/evidence/publication-20261015/full-summary.json)给出名称、退出码、对应 run-id 和日志文件名，不替代完整原始日志。

| 分组 | 数量 | 结果与条件 |
| --- | ---: | --- |
| 前后状态检查 | 2 | PASS；末尾无 VM/broker，pmthor 恢复、CPU 0–1 |
| IOCTL | 17 | PASS；涵盖 BO、VM_BIND、syncobj/sync_file、Group/Heap |
| PFN 程序及日志检查 | 2 | PASS；含两种关闭顺序与最终 reset/free |
| GLES Compute | 4 | PASS；4/16 MiB 100 次，64/128 MiB 20 次，预热 5 |
| ML all 与 Attention 320 | 2 | PASS；all 六算子 100+5，长 Attention 10+2 |
| NCNN Vulkan | 1 | PASS；三个完整网络、100 次、空权重 |
| glmark2 | 2 | PASS；720p / 1080p，null-noop + finish；720p score 59 |
| 双 Client | 1 | PASS；每个 4 MiB，100+5 |
| Host vs passthrough | 1 | PASS；结束恢复共享模式 |
| 合计 | 32 | `REGRESSION_RESULT=PASS cases=32` |

分数、吞吐与延迟只适用于当次内核、频率、CPU、内存、分辨率和同步策略。NCNN 不验证模型精度；glmark 不测屏幕呈现。更多数值和 Bug 因果分析参见专门验证报告。

## 4. 构建与复现检查

| 检查 | 已完成结果 | 限制 |
| --- | --- | --- |
| Host、Client、Proxy 源码构建 | PASS | 不等于所有新构建二进制已替换板端后全量通过 |
| RMM 构建 | PASS | 未重新执行整套固件实体刷写 |
| Firecracker / broker ARM64 musl release | PASS | 与历史固定运行二进制的哈希可不同 |
| IOCTL/PFN 静态程序构建 | PASS | 功能证据另看硬件矩阵 |
| checkout 检查 | PASS，42 个脚本语法检查 | 固定载荷哈希校验，不证明无运行时问题 |
| 175 文件归档恢复、重复恢复与校验 | PASS | 默认拒绝覆盖本地不同文件 |
| 归档异常/冲突/路径检查 | PASS | 属于恢复工具验证 |
| 上游补丁干净应用、幂等与差异拒绝 | PASS | 固定 baseline，拒绝额外 tracked diff |
| 两个 Guest rootfs 公开 Release 重新下载 | PASS，大小与 SHA-256 匹配 | 没有包含完整 Host SD 系统 |
| 8 个仓库匿名 HTTPS 可读 | PASS | 不代表推送账号身份 |
| firecracker-deps 真实远端递归 clone | PASS | rust-vmm-ci 映射可用 |
| 本地对象来源的干净 clone + bootstrap | PASS | 不是最终主仓库从 GitHub 的完整下载验证 |
| 干净 clone Host 全量构建 | PASS | 已修复并检查 release 后缀 |

构建与检查原始输出保留在 `build/publication-checks-20261015/`。固定快照的来源、源码归档和许可证见 `GPU-SFTP/ARTIFACTS.md`。

## 5. 额外干净副本短回归：存在未解决失败

运行 ID：`fresh-clone-20261015-quick`，执行环境来自 `build/fresh-clone-20261015/`。该额外运行在用户要求停止追加测试前已经启动，之后自行结束。preflight 和前 15 项 IOCTL 通过，在第 16 项 IOCTL `group-submit-syncpoint` 失败，后续项目未执行。见[逐项 summary](../../../shared/evidence/publication-20261015/fresh-quick-summary.json)。

关键日志：

```text
GROUP_SUBMIT_SYNCPOINT ... stream_addr=0x0 stream_size=0 sync_flags=0x80000000
SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=1 failed: Timer expired
PANTHOR_IOCTL_INIT=FAIL status=1
RESULT: FAIL
```

Client 两个 session 都有等待超时。原始日志：
`build/fresh-clone-20261015/GPU-SFTP/log/regression/fresh-clone-20261015-quick/group-submit-syncpoint.log`。

尚未定位根因；不能据此断言 rsync、clone 或某一代码改动就是原因，也不能将之前完整通过改写为这次通过。因此当前结论是：**固定组合有完整通过记录，最新额外复现仍暴露一个待调查的 fence 等待失败**。没有删除失败用例，也没有降低判定标准。后续应比较此次 Proxy/Host 日志、fence 与 timeout，之后再谈稳定复现保证。

## 6. 新 Agent 的验收方式

按 Agent 手册恢复、发现和检查环境；健康 Host 直接运行统一矩阵，需要部署时再进入对应分支。保存每次独立 run-id、退出码、数值参数与日志，并检查末尾空闲状态。整盘空白板部署及完整第三方源码重建尚未在本次重新验证，必须写入现场交接的未执行项。不能因为文档给出命令就将其计为已通过。
