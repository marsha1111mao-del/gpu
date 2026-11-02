# 1237基线提交路径计时

使用保留的final1237 Client/Proxy/initrd/runner、实际SD固件和SGI15模块，
仅增加`--rpc-stats`。完整720p诊断得分**1233**，相对关闭计时的基线均值
1237为**−4/−0.32%**；不是同期开关A/B，不拆分计时开销，不更新性能基线。
未改运行代码，无新增优化提分结论。

| 阶段 | 每次PLAN_EXEC平均μs | 同步往返占比 |
| --- | ---: | ---: |
| RPC：通信、排队与未分类残差 | 24.017 | 63.92% |
| lookup：会话及计划查找 | 0.362 | 0.96% |
| validate：Proxy显式检查 | 0.491 | 1.31% |
| assemble：原生结构构造 | 0.326 | 0.87% |
| native：同步接纳 | 10.625 | 28.28% |
| aux：完成观察及记账 | 1.755 | 4.67% |
| 合计 | 37.576 | 100.00% |

486231次执行尝试，Client/Proxy/分阶段计数一致；其中142次在原生提交前
被拒绝，486089次实际原生提交。RPC传输错误/超时均0。注册摊销每次执行
0.00775μs。RPC残差包含queue约0.676μs，不是纯共享内存传输时长；native
也不包含GPU异步执行。计时覆盖validation、计分与退出阶段。

原生内部均值9.903μs：创建job1.526、收集signal1.170、预留锁0.657、
映射BO同步0.095、arm/dependency1.933、push2.189、cleanup0.983，
其余为初始化及计时边界。异步run_job平均4.022μs，不能加到同步native。
TRANSFER_CAPTURE为486020次，Client往返21.293μs、Proxy handler6.944μs。

请求通知均值：PLAN_EXEC5.963μs、TRANSFER_CAPTURE3.312μs。回复轮询均值
29.591/16.655μs包含远端处理，不能与上述分阶段再次相加。
GPU job IRQ为986676次：硬中断至线程平均28.309μs、线程处理2.641μs，
不覆盖GPU执行和进入Guest硬中断前的路径；该延迟可能与RPC重叠。

Proxy Guest非idle30.61%、Client98.64%，采样包括validation和忙轮询，
没有证明Proxy或GPU饱和。历史1080p的81.152μs/61.238μs来自更早组合，
分辨率和代码均不同，不能将两组差额直接作为三项优化的独立延迟收益。

后续方向：lookup/validate/assemble合计1.179μs，整帧收益更小；单纯快照
对象优化已经在1237→1249（+0.97%）后撤回。优先检查异步完成的调度交接，
保留旧P18硬中断方案因IRQ数量增加而失败的记录，不直接重试。

命令、输入及退出码：`build/lab-runs/current-rpc-profile-720-20261024-a/`
的`result.json`、`realm-launch.json`；wrapper/runner均0。完整命令沿用
目标IRQ优化报告的720p入口，仅增加`--rpc-stats`。单Client/128MiB、
round-robin、CPU1.8GHz/GPU594MHz、telemetry/TRANSFER相同。
33场景/validation26-1-6、VM0/0、Host/Guest健康、无dmesg覆盖、CPU0-1/
pmthor/进程/挂载/loop恢复通过，11份日志SHA核验。实际快速返回1021872次。
原始数据、审计、分析与源码状态见`build/current-rpc-profile-20261024/`；
分析命令为`scripts/analysis/analyze-submit-phases.py --run <回收目录> --output <JSON>`。
本轮没有重复API/ML/1080p或多Client性能测试，不继承到新候选。
