# 单 Client glmark 提交路径诊断

## 已核实的现象

历史比例下降主要来自Native分母提高，Client总分几乎不变。但这不能解释为什么Client未受益，也不能据此断言代理路径已达到硬件上限。本次先复核既有逐场景证据，再用当前冻结包运行单Client完整720p和现有RPC计时；不修改GPU运行代码，不刷写Host或固件。

| 分辨率 | 历史Native | 同期Native两轮均值 | 历史Client均值 | 同期Client两轮均值 | 原比例 → 同期比例 |
| --- | ---: | ---: | ---: | ---: | --- |
| 720p | 1437 | 1560.50 | 1157.50 | 1158 | 80.55% → 74.21% |
| 1080p | 997 | 1130 | 902.50 | 902 | 90.52% → 79.82% |

旧Native为Host #7/VHE，新Native为Host #31/nVHE，Realm为protected hVHE。最初尚未分离Host与测量条件变化；后续[Native提分来源对照](GPU_NATIVE_SCORE_ORIGIN_20261022.md)已在同一#31/nVHE中完成完整720p固定/旧schedutil/固定实验：1561/1428/1559，独立验收通过。固定均值1560较旧策略1428为+132/+9.24%，与历史提高123.5/+8.59%接近，确认CPU调频策略变化是720p的主要原因。旧5秒采样大多为1.8GHz曾不足以归因；新实验瞬时读数全部1.8GHz，驻留计数却显示旧策略29.84%计分时间低于1.8GHz，说明也不能据此排除调频影响。GPU均594MHz，rootfs/glmark用户态SHA一致；1080p未做同样反切，其全部差值仍不能定量归因。

## 逐场景得到的新增证据

数据来自同期公平对照A/B两轮，按每轮FPS倒数的均值计算帧时差：`mean(1/Client FPS) − mean(1/Native FPS)`。这是由整数FPS推导的执行栈差值，尚不是直接测得的RPC独占延迟。

事先按场景类型选取texture、shading、bump、effect2d、pulsar、conditionals、function、loop和build/use-vbo=true，共22项；不按差值筛选。720p的22项均落在163.12–176.97微秒/帧，中位数168.74微秒；1080p有21/22项落在150–200微秒，中位数171.59微秒，另一项259.16微秒。

| 场景 | 720p Native / Client FPS | 720p每帧差值 μs | 1080p Native / Client FPS | 1080p每帧差值 μs |
| --- | --- | ---: | --- | ---: |
| build，use-vbo=true | 2452 / 1738 | 167.5 | 1950 / 1476 | 164.7 |
| texture，nearest | 2463 / 1742 | 168.0 | 1732.5 / 1350 | 163.5 |
| shading，gouraud | 2080 / 1550.5 | 164.2 | 1683 / 1316 | 165.7 |
| bump，normals | 2755.5 / 1882 | 168.4 | 1986 / 1482.5 | 171.0 |

这22项占33场景FPS差值合计约91.3%（720p）/91.4%（1080p）；这是总分构成的代数分解，不是运行时间占比。用各分辨率的中位数作为固定帧成本，描述性拟合该22项FPS的绝对相对误差中位数约0.30%/0.33%。拟合不能证明全部差值可消除，也不能把它全部归因于RPC。

多pass场景更大：720p desktop/shadow约357微秒，desktop/blur约1749微秒，refract约2503微秒，terrain约11071微秒。说明约0.17毫秒不是任意场景的统一代价；这些场景需要按提交次数、同步及映射次数继续拆分。

相同约0.17毫秒的固定开销对短帧占比更高，可以解释720p保留率低于1080p的形状。这个模式更值得优先检查提交/同步链路，而不是直接认定GPU算力或Proxy持续满载。

固定开销也不能单独解释Client为何完全没有同步提高：若Native缩短的那段执行时间同样发生在Client路径中，即使再加固定代理开销，Client仍应获得一定收益。因此需要分开验证两件事：Native究竟改善了哪段且Client是否共享该改善；当前代理/Realm路径另加了多少等待。现有数据只证明Native组合变快、Client组合基本持平，以及同期栈差值的形状，尚不能证明前者的优化被代理开销完全抵消。

## 代码路径与待区分原因

当前Client每个同步RPC仍须发布请求、执行RMM NOTIFY、等待Proxy响应；性能模式有最长1000微秒的有界回复轮询，并可抑制回复通知。轮询可能使Client Guest非idle很高，因此98%–99%非idle不等于模型或Mesa有效计算已满核。

发送统计包住`d->lock`、消息发布及RMM通知，不能把send_avg_ns直接视为数据复制时间；等待统计包含轮询、响应分派及可能的睡眠。RMM在接收方已ARM时通过Host调度提示唤醒对端，可信pending状态仍由RMM保留。通信队列已使用WB映射，GPU payload使用独立WC映射，不能不经验证就把整池改为cached。

原有计划缓存、完成等待缓存、快照融合、惰性等待和GPUVM待同步列表仍有当前实现/启动配置。四Client三任务在途限制不在本次单Client启用，不能用它解释旧单Client差距。历史自适应轮询、缩计划锁、流水线等候选未改善完整720p的记录仍保留，不能将相同建议当作尚未尝试的新优化。

优先区分：每帧RPC次数是否过多；Client通知/域切换墙钟成本；Proxy接收和提交锁/调度；真实GPU完成后的回传与轮询；多pass额外提交和私有控制BO同步。现有四Client计时只作线索，不当作单Client定论。

## 新单 Client 硬件诊断

`single-path-720-20261022-a` 已独立验收，完整720p得分 **1144**。当前candidate-f内核/initrd/runner、Host #31、2 GiB RMM；128MiB池、一个Client、CPU1.8GHz/round-robin、GPU请求600/实际594MHz、完整33场景。仅开启已有聚合RPC/提交/IRQ统计和Guest/Host观测，计时本身有成本。对同期公平均值1158为−14分/−1.21%；对当前candidate-f不带RPC统计的既有单轮1157为−13分/−1.12%。这些是诊断条件下的分差，不是优化收益，也不能仅凭各一轮将差值全部归因于统计。

改动目的｜定位单Client未随Native受益的链路｜同期公平720p均值1158 → 本轮1144｜−14分/−1.21%｜Proxy调度代码/测试载荷、RMM容量和回收VMM较旧公平组合不同，CPU/池/负载匹配；新增RPC统计，不能单变量归因｜run-id `single-path-720-20261022-a`，lab/采集/审计退出码均0，日志在 `build/lab-runs/single-path-720-20261022-a/` 及 `build/single-client-path-20261022/`｜保留诊断证据，未改运行代码，无新增优化性能测量。

### 单 Client 的直接计时

统计为validation、计分和收尾的最后累计快照，不是逐场景独占计时；Client与Proxy计时互相嵌套，不能累加为耗时百分比。Proxy数值为对应handler墙钟，不能视为纯CPU执行时间；Client与handler的差值包含传输、通知、排队、调度和不同测量边界。

| 操作 | Client调用数 | Client平均往返 μs | 其中发送 / 等待 μs | Proxy handler平均 μs |
| --- | ---: | ---: | ---: | ---: |
| PLAN_EXEC，执行已登记计划 | 452266 | 77.641 | 31.365 / 45.611 | 20.531 |
| SYNCOBJ_TRANSFER，同步对象传递 | 452055 | 53.692 | 23.582 / 29.644 | 2.580 |
| SNAPSHOT_RETIRE，快照建立/完成登记及旧快照退役融合 | 378063 | 56.675 | 25.980 / 30.061 | 7.286 |
| SYNCOBJ_TIMELINE_WAIT | 60213 | 73.696 | 27.022 / 46.036 | 6.200 |
| SYNCOBJ_WAIT | 1532 | 1069.779 | 32.465 / 1036.648 | 987.322 |

普通同步对象传递的Proxy处理约2.58微秒，Client却要等待约53.69微秒；快照融合操作约7.29微秒对56.68微秒。两项各有数十万次调用，说明高频元数据操作的跨域同步往返是有实际测量支持的优化目标。PLAN_EXEC发送的31.37微秒也不能全部记为RMM执行；需继续拆通知、接收与回复。单纯优化Proxy里数微秒的操作，收益可能被往返成本限制。

Panthor GROUP_SUBMIT平均16.06微秒，run_job平均4.66微秒、其中提交锁等待平均1.13微秒；run_job错误为0。GPU job IRQ的硬中断至线程调度平均28.02微秒，线程处理平均2.56微秒；前者不包含GPU执行和硬件IRQ进入Guest硬中断前的路径。VM_BIND有930次RPC、handler平均242.91微秒，但底层VM_BIND细分计时全部为0，说明未覆盖服务入口，不能写成映射零开销。

Guest采样覆盖validation和计分：Proxy非idle **31.12%**，Client **99.25%**。Client包含有界忙轮询；Proxy没有持续满核证据，不能据此认定Proxy CPU吞吐已经到顶。Host计分窗口168个采样点均符合CPU1.8GHz、GPU594MHz及线程亲和性；最高温度53.615℃。GPU频率不等于GPU利用率，本轮没有直接证明GPU硬件饱和或空闲。

### 判断与下一步

后续[RPC关键路径细分](GPU_RPC_CRITICAL_PATH_20261022.md)已完成独立完整720p验收（1152分，新增计时，不宣称提分）：请求入队0.42–0.49微秒、通知23.11–30.63微秒，Proxy聚合回复发布0.775微秒；99.42%回复已抑制通知。高频整次往返及请求侧NOTIFY优先于普通回复发布和平均睡眠等待；TRANSFER预捕获不可变快照供export复用仍是未实现候选。以下为此前诊断的判断与保留方向，不代表这些候选已经完成。

目前更准确的判断是：**当前代理协议存在可见的高频同步往返成本，尚不能称为GPU硬件性能上限。** 既有逐场景约170微秒的栈差值与本轮多次约50–80微秒往返在量级上相符，但统计窗口不同、每帧调用数未直接配对，不能宣称已经精确解释每帧差值。

1. 优先追踪高频SYNCOBJ_TRANSFER能否与提交计划建立有序关系，减少独立往返；不是再次融合低频CREATE。必须保持ioctl返回后的可见性、timeline point、对象引用和错误语义，不能简单延后到下一次提交。
2. SNAPSHOT_RETIRE已经融合快照、完成登记与退役，不能再按“尚未合并”处理。进一步优化应针对快照依赖的表达和已有可信完成记录，保留快照不可变性、真实fence与对象生命周期；不能根据Client自报完成提前释放，也不把旧普通syncobj批量回收的失败候选重新记为新方案。
3. 以相同冻结包测量无GPU的往返，再细分通知、Proxy接收和回复，确认固定成本来源后再改通知策略。旧自适应轮询、计划锁和流水线候选已未获收益，不宜直接重复。若要断言GPU瓶颈，需要另采可靠GPU忙闲/队列证据。
4. 本篇RPC诊断未重测Native；后续独立调频A/B/A已确认720p主要提分来源，见上述报告。另已完成[单Client调频对照](GPU_CLIENT_CPU_FREQUENCY_RESPONSE_20261022.md)：同candidate-f不带RPC计时，固定/动态/固定1155/1159/1151，固定均值1153较动态−6/−0.52%，三个条件1.8GHz计分驻留均100%；单Client动态时原已高频，解释其锁频增益小。不能将这点小负差认定为策略回退，也不能把Native/Client路径差全部记为可消除的RPC开销。

### 正确性、恢复与证据

原始33场景、validation/clean标记、Host/Guest内核健康、两个Realm退出0、输入SHA、资源恢复及GPU/DMA租约最终为0均通过。采集11个文件的SHA核验通过；租约错误为0。Pi/RK收尾资源检查通过，RK恢复CPU0–1、pmthor、GPU300MHz，无残留实验进程或loop。未新增API/1080p/多Client测试，不由单Client诊断覆盖其验收。

完整命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id single-path-720-20261022-a -- \
  python3 build/single-client-path-20261022/observe-run.py \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/ml-completion-20261022/candidate-f \
  --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-720 --clients 1 --compact-memory --pool-mib 128 \
  --client-cpu-layout round-robin --cpu-frequency-khz 1800000 \
  --telemetry --rpc-stats
```

完整实际参数及退出码保存在lab目录的 `result.json`。主机输出为 `build/single-client-path-20261022/single-path-720-20261022-a.log`；原始Guest/Host证据在其 `runs/single-path-720-20261022-a/`；独立审计为 `diagnostic-audit.json`，采样在 `observations/`，资源检查为 `final-resources.json`。既有逐场景分析为同目录 `{analyze-scenes.py,scene-analysis.json,scene-comparison.md}`。

对照报告：[同期公平对照](GPU_FAIR_MULTICLIENT_GLMARK_20261021.md)、[旧720p](GPU_MULTICLIENT_GLMARK_20261020.md)、[旧1080p](GPU_GLMARK1080_VALIDATION_20261020.md)、[已尝试的优化](SAFE_PERFORMANCE_OPTIMIZATION_20261018.md)。
