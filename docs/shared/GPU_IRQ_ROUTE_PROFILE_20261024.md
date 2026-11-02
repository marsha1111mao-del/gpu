# 1267基线的GPU中断路径诊断

状态：诊断已完成，未改GPU运行代码，不更新1267性能基线。本轮对保留冻结包
增加已有RPC计时、Host kprobe和pmthor IRQ计时，完整720p **1240**，对1267为
**−27/−2.13%**；诊断组合同时变化且仅一轮，不拆分各项计时开销或宣称代码退化。

| 观测 | 实测 | 含义 |
| --- | ---: | --- |
| irqfd原子注入返回 | 1,042,976次，全部成功 | 本次未进入慢路径 |
| 原子注入EWOULDBLOCK／其他错误／漏采 | 0／0／0 | 零值由实际探针覆盖，不是未采样 |
| 通用irqfd注入worker | 0次 | 不能把每个GPU IRQ都计入system_wq等待 |
| ICC_DIR系统寄存器陷入 | 0次 | 本次没有证据支持优化DIR陷入 |
| SGI系统寄存器陷入 | 487,972次 | 值得继续确认SGI编号和来源 |
| GPU物理JOB IRQ／resample解除屏蔽 | 988,861／988,861次 | 该路径实际频繁运行 |
| JOB物理IRQ屏蔽区间 | 均值43.356μs | 触发至resample，不等于CPU处理时间 |
| Guest JOB raw至IRQ线程 | 均值30.254μs，988,858样本 | 不含进入Guest raw之前的区间 |
| RMM返回Host的REC退出 | 3,945,722次 | 含所有Realm及多种原因 |

物理MMU/GPU错误IRQ计数均0。物理与Guest JOB计数相差3次，统计入口和启动/
退出边界不同，不据此认定丢失中断。irqfd总数可能包括其他虚拟设备；REC IRQ
退出也不能全部归为GPU。探针覆盖整个validation、计分和退出阶段。

本轮488047次PLAN_EXEC尝试、487905次真实原生接纳；SGI次数与真实job数接近，
仅是相关性。代码上`dma_fence_chain_cb()`会排`irq_work`，ARM64的
`arch_irq_work_raise()`会向自身发送IPI。后续应确认实际SGI编号或调用来源，
再研究能否在旧chain前缀已经真实完成时观察当前真实fence，避免额外irq_work。
未完成的前序fence、错误、对象重置/销毁和强引用均必须保留；不能只观察最新
GPU job就宣称整条timeline完成。目前未证明该方向的提分，也未修改DMA fence实现。

| PLAN_EXEC阶段 | 每次平均μs |
| --- | ---: |
| 通信、排队和未分类残差 | 24.630 |
| lookup／validate／assemble | 0.348／0.501／0.335 |
| native同步接纳 | 17.561 |
| aux | 1.844 |
| 同步往返合计 | 45.220 |

TRANSFER_CAPTURE往返26.079μs。1267版内联调度已将部分原来异步的run_job工作
移到同步接纳路径，且本轮新增Host探针，不能与1237旧表的10.625μs直接比较
并认定原生驱动退化。IRQ线程耗时也包含已保留的完成处理，不能与这些区间相加。

同单Client/128MiB、CPU固定1.8GHz/GPU594MHz、round-robin、telemetry/TRANSFER；
仅本轮开启诊断。命令是lab-run包住实验目录run-with-profile，再包既有SGI15
入口和run-realm-xshm；冻结包仍为`build/both-native-handoffs-20261024/candidate/`。
run-id `gpu-irq-route-profile-720-20261024-a`，wrapper/runner均rc0，33场景及
validation26/1/6、VM0/0、Host/Guest健康、无dmesg覆盖、CPU/频率/pmthor/
进程/挂载/loop恢复与11份远端日志SHA通过。两种辅助模块均已卸载，pmthor
irq_stats由原始N恢复N，没有刷写Host或固件。

完整argv、退出码和资源记录在`build/lab-runs/<run-id>/`；Host原始计数、
pmthor日志及模块哈希也在该目录。Guest完整证据、分析、审计、诊断源码、
构建命令/日志及设计保存在`build/gpu-irq-route-profile-20261024/`。
构建显式使用LOCALVERSION=-opencca-pmthor-opp3，模块vermagic与运行Host一致。
本轮没有API/ML/1080p/多Client性能测量，不继承到其他候选。
