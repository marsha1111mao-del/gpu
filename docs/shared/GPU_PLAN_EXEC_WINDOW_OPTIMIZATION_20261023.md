# PLAN_EXEC 多在途与请求通知合并实验

## 结论

**撤回。** 候选实现允许不同 plan slot 的同步 `PLAN_EXEC` RPC 有界并发，
并在请求队列已经有待处理项时抑制重复通知。两轮完整 720p glmark 均为 1160，
相对同期基线 1155 / 1151 的均值 1153 提升 7 分，即 **+0.61%**；未达到
预先规定的 1% 保留门槛 1164.53。候选运行代码、实验开关和二进制包已删除，
Client/Proxy 源码恢复为提交 `39d95dd028d485ca837bf1b3c5123db2eefbaa75` 的干净状态。

## 候选设计与语义边界

- 将 Client 文件级 plan 串行区缩小为每个 plan slot 独立保护，使不同 slot 的调用可以使用现有按 `seq/type` 匹配的 transport waiter 同时等待；并发仍受 8 个 plan slot、256 项共享队列和 Proxy 有界提交队列限制。
- Proxy 继续按 session 排队并等待真实 `panthor_vmshm_group_submit()` 同步接纳结果后才回复。没有提前返回成功、重放不确定请求或绕过原生 fence。
- 请求通知只在队列从无待处理请求转为有请求时发送；队列已有未消费请求时仅发布新描述符，由 Proxy 的 drain worker 一并排空。
- owner、VMID、session、plan ID、对象引用、动态提交参数和原生 Panthor 检查保持不变。`-ESTALE` 仍只允许在已证明未提交时重新注册并重试。
- close/reset 仍等待同步调用返回并走原有有界队列排空和资源释放路径；正式性能轮关闭高频 RPC 计时。

## 为什么收益很小

当前 glmark/Panfrost 路径在同一调用线程中执行同步 `GROUP_SUBMIT` ioctl；该 ioctl 等待
`PLAN_EXEC` 返回后，Mesa 才生成下一次提交。因此跨 ioctl 的并发深度基本为 1。
单次 ioctl 已经把最多 6 个 queue submit 合并到一个 `PLAN_EXEC`，候选无法取得尚未生成的
下一次请求，也不能在保持 ioctl 错误语义的前提下提前返回。

诊断运行的 `PAN_BATCH_DIAG` 也显示绝大多数 flush 的待提交深度为 1；偶发的多 queue
情况已由现有 `GROUP_SUBMIT` 批量结构覆盖。请求通知合并在正式轮 A 只抑制
511 / 993646 次，在正式轮 B 只抑制 327 / 998399 次，分别约 0.051% 和 0.033%，
不足以抵消主要的逐次同步 RPC 往返。

## 性能结果

| 版本 | run-id | 分数 | 相对同序号基线 | 退出码 |
| --- | --- | ---: | ---: | ---: |
| Baseline A | `plan-window-baseline-720-20261023-a` | 1155 | - | 0 |
| Baseline B | `plan-window-baseline-720-20261023-b` | 1151 | - | 0 |
| Candidate A | `plan-window-candidate-720-20261023-a` | 1160 | +5 / +0.43% | 0 |
| Candidate B | `plan-window-candidate-720-20261023-b` | 1160 | +9 / +0.78% | 0 |

基线均值为 1153，候选均值为 1160，差值为 **+7 / +0.61%**。两轮方向一致，
但没有达到 1% 门槛，因此结论为撤回，不能把这组分差记作已保留优化收益。

## 可比条件与验证

四轮均使用同一 Host/RMM、单 Client、完整 1280x720 glmark 33 场景、128 MiB
compact pool、Client CPU round-robin、CPU 固定 1.8 GHz、GPU 请求 600 MHz且实测
594 MHz、telemetry 和 `TRANSFER_CAPTURE`；未启用高频 RPC 计时。命令形状为：

```text
python3 scripts/maintenance/lab-run.py --run-id <run-id> -- \
  python3 build/submit-transfer-fusion-20261023/restore-after.py \
  python3 build/submit-transfer-fusion-20261023/observe-run.py \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py --images <baseline-or-candidate> \
  --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-720 --clients 1 --compact-memory --pool-mib 128 \
  --client-cpu-layout round-robin --cpu-frequency-khz 1800000 \
  --telemetry --transfer-capture
```

四轮均通过 33 场景、既定 validation 26/1/6、`GLMARK_CLEAN_RESULT`、
`GPU_SMOKE_RESULT`、Realm 退出、Host 内核健康和输入恢复检查。没有 GPU timeout、
translation fault、kernel warning/panic、OOM 或 Group submit fence 超时；GPU/DMA
租约最终均为 0。

诊断首次运行 `plan-window-batch-diag-720-20261023-a` 因实验性批量观测代码导致
EGL 初始化失败，退出 1；Host 健康和租约回收仍通过。修正后的诊断运行
`plan-window-batch-diag-v2-720-20261023-a` 退出 0，只用于确认提交窗口形状，
不作为无诊断性能对照。

## 停止门槛与未执行项

候选在首要 glmark 门槛失败后立即撤回，因此 ResNet50/Convolution/Softmax 和候选
双 Client fence/退出专项均标记为 **NOT_RUN**。这些测试只决定一个通过性能门槛的
候选能否最终保留；继续测试已经确定撤回的二进制不能改变结论，也会无谓占用硬件。
现有 baseline 的历史 ML 和双 Client PASS 不转记为本候选结果。

## 证据与清理

- 测试生命周期、命令和退出码：`build/lab-runs/<run-id>/result.json`。
- 部署输入 SHA：`build/lab-runs/<run-id>/realm-launch.json`。
- glmark、Realm 与统计日志：`build/plan-exec-window-20261023/baseline-remote/` 和
  `build/plan-exec-window-20261023/runs/`。
- Host 健康、租约和恢复：每个 run-id 目录中的 `host-kernel-health.json`、
  `lease-monitor.json` 和 `normal-inputs-restored.json`。
- 最终 Pi/RK 只读资源检查：`build/plan-exec-window-20261023/final-resources.json`，
  无活动实验进程和资源问题。

候选 Client/Proxy Image SHA 分别为
`48076252b625f2951e25b294dc04e1fcfb1adffe6bce5ffab5968f9a45bed9d7` 和
`80bfadfb778e8431bc5721b62f5668544742b7ceae4545f78ce66bfa7b1d6071`；二进制本体已按
撤回规则删除。保留约 12 MiB 的必要日志、资源报告和哈希证据。当前 RK Host 为
`6.12.0-opencca-pmthor-opp3`，GPU 绑定 `pmthor`，最终检查时无活动 Firecracker。

改动目的｜有界放开不同 PLAN slot 的端到端 RPC 在途并合并重复请求通知｜同期基线
1155 / 1151，均值1153 → 候选1160 / 1160，均值1160｜+7 / +0.61%｜同频率、落核、
镜像族、内存池、runner 和完整720p条件，均关闭高频计时｜上述四个run-id均退出0，
日志见上述路径｜**撤回**。
