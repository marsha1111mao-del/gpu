# 当前优化版的多 Client 与内存复核（2026-10-25）

本次使用当前单 Client 720p 均分 1405 的冻结组合，未改生产运行代码、未重建镜像、未刷写固件。
四 Client 完整 720p glmark、三/四 Client GEMM 与卷积均已通过。
未重复已完成的单 Client 720p、1080p 和双 Client API/计算测试。

## 历史混合调频 glmark 对照（已由完整同频新测替代）

后续已重新执行 Native/Clientproxy、720p/1080p、1–4 并发全部 16 个配置，
两侧 CPU 固定 1.8 GHz、GPU 实际 594 MHz，见[完整同频新测](GPU_FIXED_FREQUENCY_GLMARK_20261025.md)。
下表保留当时的混合条件与缺项，不作为当前同频性能结论；本报告后续内存数据仍属于原批次。

| 分辨率 / 并发数 | Native 分数 | Clientproxy 分数 | 分数保留比例 |
| --- | --- | --- | --- |
| 1280×720（1 Client） | 1431.50 | 1405.00 | 98.15% |
| 1280×720（2 Client 并发） | 813.75 | 未测（当前版本） | — |
| 1280×720（3 Client 并发） | 532.33 | 未测（当前版本） | — |
| 1280×720（4 Client 并发） | 378.13 | 381.00 | 100.76% |
| 1920×1080（1 Client） | 1008.50 | 1044.00 | 103.52% |
| 1920×1080（2 Client 并发） | 587.75 | 未测（当前版本） | — |
| 1920×1080（3 Client 并发） | 394.50 | 未测（当前版本） | — |
| 1920×1080（4 Client 并发） | 277.38 | 未测（当前版本） | — |

Native 全部沿用历史引用，本轮未重测；其中 1080p 双/三进程为固定 1.8 GHz 历史值，
其余来自动态调频复测。当前 Clientproxy 均为固定 CPU 1.8 GHz、GPU 实际 594 MHz，
round-robin、TRANSFER/telemetry 开启、阶段计时关闭；720p 使用每 Client 128 MiB 池，1080p 单 Client 使用 192 MiB。
两列时段、CPU 策略及固件/运行栈不同，超过 100% 不代表同期同频条件下的虚拟化加速。
720p 单 Client 为 1406/1404 两轮均分，四 Client 为 379/381/382/382 单轮各 Client 均分，
1080p 单 Client 为单轮 1044；未测行不复用旧版 Clientproxy 成绩。
本节当时仅整理已有结果，未改运行代码，无新增性能测量；当时因 Notion MCP 需要重新认证未同步。
重新认证后的完整同频重测结果已追加至 Notion，不将本历史表改写为新测。

## 多 Client 实测

| 测试 | Client 数 | 结果 | 并发有效性 |
| --- | ---: | --- | --- |
| 完整 720p glmark | 4 | 379 / 381 / 382 / 382，均分 **381.00** | 共同执行窗口 351.800 s，占总窗口 99.86% |
| GEMM / 卷积 | 2 | 复用同载荷已通过结果：GEMM 57.56239 / 57.85380 ms；卷积 66.58179 / 66.25267 ms | 共同计量窗口占 99.11% / 99.27% |
| GEMM / 卷积 | 3 | 全部实际计算校验通过；GEMM 88.02214 / 57.61216 / 84.62764 ms；卷积 104.15263 / 66.33572 / 93.86760 ms | 共同计量窗口 5.588 / 6.312 s，占 63.49% / 60.57% |
| GEMM / 卷积 | 4 | 全部实际计算校验通过；GEMM 105.96421 / 107.35064 / 120.23617 / 112.69609 ms；卷积 131.54169 / 137.39525 / 123.89714 / 123.88684 ms | 共同计量窗口 10.551 / 12.353 s，占 87.72% / 88.50% |

计算负载使用 GEMM 512 FP32、卷积 64×64×32 / 3×3 FP32，每项每 Client 100 次计量、5 次预热。
通过预热后的计量 barrier 确认实际并发；各 Client 完成速度不一致，有一部分计量发生于其他 Client 结束之后，
因此本轮用于兼容性及内存验证，不当作稳态全并发吞吐或同条件旧版速度对照。
ML 沿用性能入口默认 shared CPU 布局，未传固定 CPU 频率参数；
glmark 则显式使用 round-robin 和 CPU 1.8 GHz。两类测试不是相同的 CPU 控制条件。

四个 glmark 各自完成 33 场景，validation 为 26 / 1 / 6，均为真实 Mali-G610 渲染；
五个 VM 全部退出 0，Host/Guest 无 GPU 超时、OOM、WARNING/Oops/panic。
原生提前完成路径实际完成 582637 个 job，Proxy 快速通知路径计数 1207139，优化并未因多 Client 而整体停用。
运行后 SGI 辅助模块卸载、CPU 恢复 0–1、GPU 归还 pmthor，进程与 loop 挂载清理通过。

统一记录：验证当前优化组合的四 Client 图形兼容性｜历史四 Client 均分 355.50 → 本轮 381.00｜
**+25.50 / +7.17%**｜均为 720p、每 Client 128 MiB 池、CPU 1.8 GHz/GPU 594 MHz，
但 Client/Proxy、VMM、RMM/Root、runner 均有变化，当前四 Client 还启用
`panthor.max_inflight_jobs=3`；不是最近一次优化的独立 A/B｜
`current-multi-720-4c-20261025-a`，wrapper/runner/采集 rc 均为 0｜保留当前代码；仅一轮，不宣称稳定提分。
单 Client 基线仍是 1405，本次没有新增单 Client 提分测量。

## 配置预算有没有变化

**近期性能优化未扩大 GPU 共享池或 VM RAM 配置。** 普通紧凑配置的预算如下，单位 MiB：

| Client 数 | Proxy RAM | 每个 Client RAM | VM RAM 总预算 | 源共享池总容量 | 加 256 MiB Host 余量后的准入预算 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 368 | 336 | 704 | 128 | 960 |
| 2 | 528 | 336 | 1200 | 256 | 1456 |
| 3 | 688 | 336 | 1696 | 384 | 1952 |
| 4 | 848 | 336 | 2192 | 512 | 2448 |

来自 `GPU-SFTP/tests/realm-xshm/run-realms.py:151` 的 `realm_memory()`。
每 Client 池大小为 P、Client 数为 N 时，Client RAM=P+208，Proxy RAM=N×P+208+32N。
此表使用 P=128；ResNet50 的普通内存及四 Client 回收模式另有配置，不适用此表。
256 MiB 是启动准入余量，不保证运行中始终保留同样的物理空闲量。

**VM 配置预算、Guest MemAvailable 和 Host 实际物理占用不能直接相加。**
GPU BO 在池内分配，不能在源池容量之外再算一次 BO；Client 映射的是同一批源页。
Client Guest 仍将目标 CMA 区域视为保留/占用，因此其 CmaFree 可能接近零；这本身不说明 Host 上仍留有一份重复数据。

## 实际采样

Host 每秒采样 MemAvailable，覆盖启动、挂接、任务执行及退出前收尾；无 swap。

| 测试 | 初始可用 MiB | 最低可用 MiB | 可用量最大下降 MiB |
| --- | ---: | ---: | ---: |
| 当前双 Client GEMM / 卷积（已有） | 3076.73 | 2110.55 | 966.18 |
| 当前三 Client GEMM / 卷积 | 3081.14 | 1692.16 | 1388.98 |
| 当前四 Client GEMM / 卷积 | 3095.39 | 1291.86 | 1803.54 |
| 当前四 Client glmark | 3084.91 | **1247.39** | **1837.52** |
| 历史四 Client glmark A | 3080.72 | 663.44 | 2417.28 |
| 历史四 Client glmark B | 3068.00 | 654.88 | 2413.13 |

当前四 Client 的下降量比历史两轮均值少 **577.68 MiB（23.92%）**。
这是系统层面观测，包含 Host、VM、页缓存与日志，不能当作精确任务内存，
也不能全部归因于近期性能优化；历史 VMM 尚不是当前目标后备页回收版本，runner 在途限制等也不同。
每秒采样可能错过瞬时峰值，且没有同期旧镜像对照，因此这里只报告观测差异。

当前四 Client glmark 的进程 RSS 采样峰值分别为 102.84 / 100.38 / 101.76 / 100.38 MiB；
各 Guest MemAvailable 最低为 26.10 / 25.02 / 25.59 / 26.01 MiB。
RSS 包含共享映射，不能把这四项与池容量相加当作物理总量；Guest 余量也不能替代共享池自身容量检查。

## 控制结构与旧目标页

近期优化主要增加锁、链表头、引用和计数器，没有为每次提交新增一份 GPU 缓冲副本。
提前完成路径把原 `job->node` 移入 `raw_done_jobs`，由进程上下文回收引用；
它会改变对象保留时间，但没有创建第二份 job 载荷。
计划槽仍为 8、完成槽为 64、单次退休上限为 8，未因多 Client 扩大。

下表从 ARM64 对象 DWARF 读取，当前构建 Image SHA 与已测 Proxy 一致。
旧参照是较早源码的 rollback 重建对象，不是严格同条件的运行对照。

| 结构 | 旧构建参照 bytes | 当前 bytes | 单对象变化 bytes |
| --- | ---: | ---: | ---: |
| panthor_group | 568 | 592 | +24 |
| panthor_scheduler | 1240 | 1272 | +32 |
| panthor_proxy_snapshot_watch | 88 | 104 | +16 |
| panthor_proxy_session | 328 | 352 | +24 |
| panthor_proxy_plan | 392 | 392 | 0 |

这些是指定结构的请求尺寸，不含 slab 档位取整、指向对象及活跃对象数量，
不能据此得出全部控制结构物理峰值，也不能宣称总内存完全不变。
本次没有重新加入已撤回的生产分配账本。

Client 旧目标后备页的回收实现和已测 VMM 保持一致：共享挂接成功后，对旧 guest_memfd 区间执行
`FALLOC_FL_PUNCH_HOLE | FALLOC_FL_KEEP_SIZE`，随后 Client 使用源池物理页。
此前单 Client 384 MiB 实验已直接核验 98304 页 → 0；本次没有对四个 Client 逐一重新计数旧目标驻留页，
因此不把历史单 Client 的直接测量改写为本次四 Client 的直接证明。

## 命令、日志与边界

四 Client 图形命令：

```bash
python3 scripts/maintenance/lab-run.py --run-id current-multi-720-4c-20261025-a -- \
  python3 scripts/run/run-realm-wake-sgi.py \
  --module build/fast-target-irq-20261024/host-sgi/xshm_wake_sgi.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/raw-fence-observation-20261024/candidate \
  --workload glmark --performance --benchmark-only --suite --compact-memory \
  --pool-mib 128 --transfer-capture --profiles glmark-720 --clients 4 \
  --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry
```

原始采集目录为 `build/multiclient-current-20261025/runs/<run-id>/`，
包含 summary、逐 Realm 日志、Host 内存采样及文件 SHA；硬件锁、前后资源和内核健康证据在
`build/lab-runs/<run-id>/`。当前图形运行 23 份远端文件 SHA 与采集内容全部匹配。
双 Client 已有结果位于 `build/optimization-review-20261025/runs/optimization-review-ml2-20261025-a/`。

三/四 Client 计算使用同一外层锁与 SGI 包装、同一冻结包，去掉图形专用的 CPU/telemetry 参数，
将尾部替换为 `--profiles ml-gemm ml-conv --clients 3` 或 `--clients 4`。
run-id 分别为 `current-multi-ml-3c-20261025-a`、`current-multi-ml-4c-20261025-a`；
两项 wrapper/runner/采集 rc 均为 0，四/五个 VM 全退出 0，18/22 份采集文件 SHA 匹配，
计算正确性、内核健康、真实优化路径启用及资源恢复检查全部通过。
四 Client glmark 加两项计算共 63 份远端证据文件通过 SHA 核验。

最后以独立锁运行 `current-multi-finalize-20261025-a`，执行
`python3 build/optimization-review-20261025/restore-and-verify.py`，rc=0。
六项板端运行输入与本次已测冻结组合一致，无需替换；实际 SD 的 idbloader/u-boot 字节摘要
与 `build/fast-target-irq-20261024/firmware-final/` 一致。
51 份源码/测试输入摘要仍与前次审查相同，Host CPU、GPU 驱动、进程及 loop 状态恢复通过。
可移植的结果、命令、输入/证据 SHA、结构尺寸和历史内存对照见
[`evidence/multiclient-current-20261025/`](evidence/multiclient-current-20261025/)。

本次没有实验失败或准入拒绝；未执行范围如下，不继承旧 PASS。

本报告原批次未执行：双/三 Client glmark、四 Client 1080p、ResNet50、长稳/reset 压力和完整安全矩阵。
后续完整同频 glmark 已补齐全部图形配置；Native 1080p 四进程 GPU 超时失败仍保留，详见新报告。
这里确认已测负载可运行，不扩展成任意模型、任意池大小均足够的保证。
原有额外 Group submit fence 超时及其他历史失败记录保留，不被本次 PASS 覆盖。
