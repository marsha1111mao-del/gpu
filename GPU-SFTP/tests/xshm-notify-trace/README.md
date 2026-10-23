# Host XSHM通知诊断探针

仅在`lab-run.py`独占租约内装载。模块观察`kvm_realm_xshm_wake`及Firecracker vCPU相关的`sched_wakeup`/`sched_switch`，不改变事件授权、GPU提交或调度策略。物理计数器每100ms中的前2ms采样，缓冲区固定上限262144条；必须检查`dropped`与`missed`。

先按[环境手册](../../../docs/start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)和[开发规范](../../../docs/start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)准备与板端匹配的Host构建树。下列示例对应当前`6.12.0-opencca-pmthor-opp3`，LOCALVERSION必须与实际板端一致：

```bash
mkdir -p build/notify-latency-20261022/host-trace
cp GPU-SFTP/tests/xshm-notify-trace/Makefile \
   GPU-SFTP/tests/xshm-notify-trace/xshm_notify_trace.c \
   build/notify-latency-20261022/host-trace/
make -C Linux-Host-GPU O="$PWD/build/dma-guard-20261018/host" \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  LOCALVERSION=-opencca-pmthor-opp3 \
  M="$PWD/build/notify-latency-20261022/host-trace" modules
modinfo build/notify-latency-20261022/host-trace/xshm_notify_trace.ko
```

将工作负载包在`scripts/run/run-xshm-notify-trace.py --module <模块路径> -- <命令>`内，再统一包一层`lab-run.py`。包装器校验上传SHA，结束时保存`build/lab-runs/<run-id>/host-notify-trace.{log,json}`并卸载本次模块；不能并行装载另一份或覆盖正在运行的脚本。

每条记录包含kind、CPU、当前TID、目标/next TID、起止物理计数器、目标Realm RD与调度状态。kind1为Host唤醒辅助函数区间，kind2为调度wakeup，kind3为调度switch。Guest序列号不跨到Host，分析器通过已校验的共同计数器区间及vCPU TID关联；跨采样边界的记录可能缺失。计数器和trace本身有开销，不能将开启诊断后的分差独立归因于某个实现。

完整流程与判定边界见[通知延迟拆分](../../../docs/shared/GPU_NOTIFICATION_LATENCY_20261022.md)。原始日志可能包含物理地址，仅保存在忽略的实验目录，仓库提交保留脱敏统计。
