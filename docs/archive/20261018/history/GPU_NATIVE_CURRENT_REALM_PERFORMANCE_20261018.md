# Native 与当前 P42 Proxy/Client Realm 性能重新测量（2026-10-18）

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

**最新统一统计入口：** [Native / ProxyClient 全部有效结果汇总](../../../shared/GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)，按项纳入 BO 修复后结果，并明确区分 P42 参考。本页保留原始测量历史。

本报告比较同一块 RK3588 上的 Host 原生 Panthor 与当前 P42 Proxy/Client Realm。两边均为本轮重新测量；历史普通 VM 数据不参与本轮比值。GPU 内核与 RMM 没有因本次测量重新构建或更改，新增部分仅为测试调度与可选配置文件入口。

**后续修复更新：** ResNet50 与 1080p 已在 P42 + BO 容量修复组合的显式 512 MiB 配置下通过，独立默认配置 720p 为 1161。详见 [大 BO 修复及验收报告](../../../shared/GPU_BO_CAPACITY_FIX_20261018.md)。本报告以下数据继续保留为修复前的实测基线，不改写历史失败。

## 1. 主要结果

- glmark 720p：Native **1437**，当前 Realm **1154**，保留 **80.3%**，分数差 **-19.7%**。
- glmark 1080p：Native **997**，当前 Realm **FAIL**（BO 分配错误；原始分数 939 无效），不计算分数保留率。
- 当前 ResNet50 因 BO 分配/Vulkan 错误失败，未采用其打印的时间；其他结果按逐项判定列出。
- 详细计算、ML、NCNN、17 项 IOCTL 和双 Client 结果见下表。时间比值包含虚拟化、驱动及代理路径的综合影响，不能直接解释为单独的 RMM 开销。

### 测量范围与通过情况

| 分组 | Native | 当前 Realm | 统计说明 |
| --- | --- | --- | --- |
| IOCTL 共同路径 | 17 / 17 | 17 / 17 | 每项 3+20；不把共同路径当作全部安全策略验收 |
| Compute | 4 / 4 | 4 / 4 | 4、16、64、128 MiB |
| ML / Attention | 6 + 1 通过 | 6 + 1 通过 | 六算子与 Attention320 分别统计 |
| NCNN | 3 / 3 | 2 / 3 | ResNet50 FAIL，不使用错误时间 |
| glmark | 2 / 2 | 1 / 2 | 当前 1080p FAIL，不使用 939 分 |
| 双进程 / 双 Client | 双方通过 | 双方通过 | 并发 4 MiB；当前另有 2×17 类 API 与 IRQ 检查 |
| 历史完整 32 项入口 | 未执行 | 未执行 | 本报告是专项性能重新测量，不标注 32/32 |

## 2. 对照条件与计时口径

| 项目 | 本轮条件 |
| --- | --- |
| 硬件 / Host | RK3588 / Mali-G610；6.12.0-opencca-pmthor-opp3 #7 |
| GPU | 请求 600 MHz，实际 clk_gpu 594 MHz；统计计时诊断关闭 |
| CPU | CPU 0–3 在线；A55 policy0 schedutil，1.008–1.8 GHz；未锁 CPU 恒定频率 |
| Native | Host Panthor；单负载绑 CPU 2，双进程绑 CPU 2 / 3 |
| 当前方案 | P42 Proxy Realm 绑 CPU 1；Client Realm 绑 CPU 2，第二 Client 绑 CPU 3；每 Realm 1 vCPU / 768 MiB |
| 共享与通知 | 真实 RMM 授权共享池和可信 IRQ 127；单 Client 池 256 MiB，双 Client 各 128 MiB |
| 用户态 | 同一只读 rootfs，相同 compute / ML / NCNN / glmark 二进制与库；MESA_SHADER_CACHE_DISABLE=true |
| Compute | 4 / 16 MiB：100 次；64 / 128 MiB：20 次；预热 5；排除 CPU prepare；最终抽查 16 个输出 |
| ML | 六算子各 100+5，GEMM 512；另测 Attention 320（10+2）；末次结果与 CPU reference 比较 |
| NCNN | 三个模型分别 100 loops、2 threads、GPU device 0；PanVK 实机资格检查；随机权重性能负载，不是模型精度验证 |
| glmark | 720p / 1080p；null-noop、finish；全 33 场景；validate 开启 |
| IOCTL | 共同支持语义；3 次预热 + 20 次采样；open→basic checks→case→close；不含 VM 启动；不是一个裸 ioctl 的时延 |
| 双 Client | 两边各 4 MiB、100+5，并发启动；CPU prepare 包含在迭代时间内，不能与上方单 Client 的计时直接混算 |
| 统计范围 | 每种环境一个有效批次，迭代 min/avg/max 保存在 metrics.json；没有跨批次置信区间或长期稳定性结论 |

时间表：倍率 = 当前 / Native；时间增幅 = 倍率 − 1；等效吞吐保留 = Native / 当前。分数和 FPS 越高越好，其保留比例直接使用当前 / Native。

## 3. 计算负载

| 输入档位 | Native ms/iter | 当前 ms/iter | 时间倍率 | 时间增幅 | 等效吞吐保留 |
| --- | --- | --- | --- | --- | --- |
| compute-4 MiB | 1.362 | 1.691 | 1.242× | +24.2% | 80.5% |
| compute-16 MiB | 4.709 | 5.303 | 1.126× | +12.6% | 88.8% |
| compute-64 MiB | 17.788 | 19.274 | 1.084× | +8.4% | 92.3% |
| compute-128 MiB | 35.605 | 38.575 | 1.083× | +8.3% | 92.3% |

分阶段平均时间（µs/iter），用于观察上传、提交和等待路径；各阶段按测试程序定义计时，不代表 GPU 硬件计数器。

| 档位 | 阶段 | Native µs | 当前 µs |
| --- | --- | --- | --- |
| compute-4 | cpu_prepare | 1783.11 | 1901.05 |
| compute-4 | buffer_upload | 750.21 | 795.51 |
| compute-4 | dispatch_call | 195.33 | 436.89 |
| compute-4 | memory_barrier | 40.86 | 90.91 |
| compute-4 | map_wait | 373.62 | 365.70 |
| compute-4 | unmap | 1.58 | 1.84 |
| compute-16 | cpu_prepare | 7100.65 | 7496.17 |
| compute-16 | buffer_upload | 3071.53 | 3309.28 |
| compute-16 | dispatch_call | 227.75 | 516.87 |
| compute-16 | memory_barrier | 40.56 | 90.30 |
| compute-16 | map_wait | 1367.10 | 1384.14 |
| compute-16 | unmap | 2.00 | 2.89 |
| compute-64 | cpu_prepare | 28327.90 | 29781.95 |
| compute-64 | buffer_upload | 12371.90 | 13490.15 |
| compute-64 | dispatch_call | 285.85 | 629.85 |
| compute-64 | memory_barrier | 39.75 | 83.35 |
| compute-64 | map_wait | 5088.70 | 5068.25 |
| compute-64 | unmap | 1.95 | 2.25 |
| compute-128 | cpu_prepare | 56624.40 | 59542.95 |
| compute-128 | buffer_upload | 24824.60 | 27133.80 |
| compute-128 | dispatch_call | 292.80 | 1438.30 |
| compute-128 | memory_barrier | 40.35 | 89.05 |
| compute-128 | map_wait | 10444.85 | 9911.15 |
| compute-128 | unmap | 2.05 | 2.75 |

4 MiB 的 dispatch_call 平均从约 195 µs 增至 437 µs，memory_barrier 从约 41 µs 增至 91 µs，而 map_wait 约为 374 / 366 µs。这说明小负载差额主要出现在本轮计时所覆盖的上传/发起/同步调用路径，而不能直接说 GPU 内核执行变慢 24%。128 MiB 的上传与 dispatch_call 也有更大差额；各阶段的明确边界以测试程序为准。

## 4. ML 算子

| 算子 | Native ms/iter | 当前 ms/iter | 时间倍率 | 时间增幅 | 等效吞吐保留 |
| --- | --- | --- | --- | --- | --- |
| gemm_512_fp32 | 29.116 | 29.382 | 1.009× | +0.9% | 99.1% |
| conv2d_64x64x32_3x3_fp32 | 34.135 | 33.867 | 0.992× | -0.8% | 100.8% |
| depthwise_conv_128x128x128_3x3_fp32 | 21.894 | 21.896 | 1.000× | +0.0% | 100.0% |
| block_reduction_32mib_fp32 | 10.695 | 10.639 | 0.995× | -0.5% | 100.5% |
| row_softmax_16384x256_fp32 | 19.404 | 19.277 | 0.993× | -0.7% | 100.7% |
| single_head_attention_256x64_fp32 | 773.543 | 775.953 | 1.003× | +0.3% | 99.7% |
| single_head_attention_320x64_fp32 | 1221.823 | 1224.653 | 1.002× | +0.2% | 99.8% |

## 5. NCNN / Vulkan

| 模型 | Native ms/inference | 当前 ms/inference | 时间倍率 | 时间增幅 | 等效吞吐保留 |
| --- | --- | --- | --- | --- | --- |
| mobilenet_v2 | 31.260 | 32.140 | 1.028× | +2.8% | 97.3% |
| mobilenet_v3 | 28.360 | 28.860 | 1.018× | +1.8% | 98.3% |
| resnet50 | 1162.990 | FAIL：BO ENOMEM / Vulkan error | N/A | N/A | N/A |

ResNet50：当前日志记录申请 0x9800000（152 MiB）BO 返回 -ENOMEM，随后出现 vkEndCommandBuffer / vkQueueSubmit 错误；即使模型 rc=0 并打印 avg=5.24 ms，该时间也无效。现有共享池共 256 MiB，且 BO payload 使用连续区间；驱动单池上限 SZ_256M、RMM 上限 65536 页。进一步结合实现可定位到单 BO 的结构性上限：本轮 domain 日志为 size=0xff00000、alloc=[0x200000,0xfd00000]、max_order=15，即最大 buddy 块 128 MiB；152 MiB 会向上取整为 256 MiB（order 16），超过 max_order 后必然 ENOMEM。GPU BO 标记 CONTIG 且需要 MMAP，当前不会退回 SG；因此不是只增加可用系统 RAM 就能解决。总活跃峰值和额外碎片影响尚未计量，本轮不更改生产内核或池容量来掩盖失败。

2 threads 在单核心亲和性内运行；两边设置一致。后端资格通过与模型成功分别检查，含 vkWaitForFences / Vulkan 错误的结果不能列为有效性能。

## 6. glmark 与优化历史的关系

| 分辨率 | Native score | 当前 score | 分数保留 | Native 验证 success/failure/unknown | 当前验证 |
| --- | --- | --- | --- | --- | --- |
| glmark-720 | 1437 | 1154 | 80.3% | [26, 1, 6] | [26, 1, 6] |
| glmark-1080 | 997 | FAIL（原始 939 不合格） | N/A | [26, 1, 6] | [26, 1, 6] |

1080p 的 benchmark 阶段出现 12 次 BO_CREATE 错误，申请 0x2060000 / 0x2cf7000（约 32.375 / 44.965 MiB）失败；buddy 会分别扩为 64 MiB 分配。其问题是当前共享 payload 池内可满足的块/容量不足，不能据此声称 GPU 算力只有原生的某个比例；确切活跃占用与碎片比例尚未计量。由分配粒度可以推断，分辨率增大后附件 BO 跨过 32 MiB 分档、被扩为 64 MiB，会放大容量压力；这解释了 720p 能运行并不保证 1080p 能运行，但不是对峰值总量的直接测量。该轮只记录到 31 条完整 FPS 行；939 分和逐场景 FPS 仅保留为原始诊断数据，不参与性能比值。

验证中的 1 个 failure 是 function / fragment-complexity=medium / fragment-steps=5 的既有数值验证例外，6 个 unknown 也沿用既有口径；因此表中的 wrapper PASS 不等于全部 33 个 validate 子项成功。逐项原始验证输出与错误计数保留在日志中。

P42 上次独立 720p 两轮为 1159 / 1163（均值 1161）；本轮隔离后的干净负载批次为 **1154**，相对该均值 **-0.60%**。本次没有新的 GPU 性能优化改动，变化属于批次条件下的重新测量，不把波动归因于测试入口改进。旧普通 VM 1058 仅作历史背景，不用于计算 Native 保留率。

### glmark-720 逐场景

| 场景 | Native FPS | 当前 FPS | FPS 保留 |
| --- | --- | --- | --- |
| [build] use-vbo=false | 994 | 1120 | 112.7% |
| [build] use-vbo=true | 2299 | 1742 | 75.8% |
| [texture] texture-filter=nearest | 2311 | 1758 | 76.1% |
| [texture] texture-filter=linear | 2321 | 1757 | 75.7% |
| [texture] texture-filter=mipmap | 2307 | 1744 | 75.6% |
| [shading] shading=gouraud | 1919 | 1539 | 80.2% |
| [shading] shading=blinn-phong-inf | 1890 | 1523 | 80.6% |
| [shading] shading=phong | 1709 | 1432 | 83.8% |
| [shading] shading=cel | 1705 | 1425 | 83.6% |
| [bump] bump-render=high-poly | 1086 | 1066 | 98.2% |
| [bump] bump-render=normals | 2611 | 1876 | 71.8% |
| [bump] bump-render=height | 2462 | 1806 | 73.4% |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0; | 1783 | 1473 | 82.6% |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1; | 829 | 837 | 101.0% |
| [pulsar] light=false:quads=5:texture=false | 1686 | 1392 | 82.6% |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4 | 388 | 231 | 59.5% |
| [desktop] effect=shadow:windows=4 | 845 | 696 | 82.4% |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map | 47 | 46 | 97.9% |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata | 47 | 46 | 97.9% |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map | 66 | 65 | 98.5% |
| [ideas] speed=duration | 480 | 436 | 90.8% |
| [jellyfish] <default> | 1210 | 1111 | 91.8% |
| [terrain] <default> | 78 | 40 | 51.3% |
| [shadow] <default> | 982 | 742 | 75.6% |
| [refract] <default> | 196 | 135 | 68.9% |
| [conditionals] fragment-steps=0:vertex-steps=0 | 1980 | 1551 | 78.3% |
| [conditionals] fragment-steps=5:vertex-steps=0 | 1862 | 1490 | 80.0% |
| [conditionals] fragment-steps=0:vertex-steps=5 | 1976 | 1554 | 78.6% |
| [function] fragment-complexity=low:fragment-steps=5 | 1973 | 1550 | 78.6% |
| [function] fragment-complexity=medium:fragment-steps=5 | 1747 | 1434 | 82.1% |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5 | 1971 | 1552 | 78.7% |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5 | 1970 | 1554 | 78.9% |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5 | 1737 | 1424 | 82.0% |

## 7. 17 项 IOCTL 共同支持路径

| 用例 | Native µs/case | 当前 µs/case | 时间倍率 | 时间增幅 | 等效吞吐保留 |
| --- | --- | --- | --- | --- | --- |
| basic | 23.655 | 520.304 | 21.996× | +2099.6% | 4.5% |
| vm-create | 39.959 | 706.825 | 17.689× | +1668.9% | 5.7% |
| bo-create | 60.755 | 912.334 | 15.017× | +1401.7% | 6.7% |
| bo-lifecycle | 109.684 | 1318.698 | 12.023× | +1102.3% | 8.3% |
| bo-mmap | 106.986 | 932.896 | 8.720× | +772.0% | 11.5% |
| vm-bind | 2472.866 | 7140.656 | 2.888× | +188.8% | 34.6% |
| vm-bind-async-sync | 203.894 | 1687.554 | 8.277× | +727.7% | 12.1% |
| vm-state-flush | 69.929 | 810.629 | 11.592× | +1059.2% | 8.6% |
| syncobj-lifecycle | 39.522 | 549.558 | 13.905× | +1290.5% | 7.2% |
| syncobj-wait | 49.497 | 993.694 | 20.076× | +1907.6% | 5.0% |
| syncobj-transfer | 42.745 | 849.348 | 19.870× | +1887.0% | 5.0% |
| syncobj-timeline-wait | 72.306 | 1421.510 | 19.660× | +1866.0% | 5.1% |
| syncobj-signal-query | 65.583 | 1331.808 | 20.307× | +1930.7% | 4.9% |
| sync-file-snapshot | 1718.525 | 43696.800 | 25.427× | +2442.7% | 3.9% |
| group-lifecycle | 202.174 | 1563.187 | 7.732× | +673.2% | 12.9% |
| group-submit-syncpoint | 238.457 | 1800.502 | 7.551× | +655.1% | 13.2% |
| tiler-heap-lifecycle | 284.002 | 1436.473 | 5.058× | +405.8% | 19.8% |

共同 profile 去掉 Client 专属不支持能力断言；BO mmap 比较合法可映射 BO 的正向行为，不把 Native 的 NO_MMAP offset 查询策略差异当作性能失败。Group submit 使用 CLOCK_MONOTONIC 的正确绝对 deadline，并等待 fence 完成。原生与 Client 使用同一计时探针 SHA；探针源码和二进制保存在本轮冻结目录。

## 8. 双 Client / 原生双进程

| 参与方 | Native ms/iter | 当前 ms/iter | 时间倍率 | 时间增幅 | 等效吞吐保留 |
| --- | --- | --- | --- | --- | --- |
| Client / process 0 | 3.312 | 3.952 | 1.193× | +19.3% | 83.8% |
| Client / process 1 | 3.323 | 3.914 | 1.178× | +17.8% | 84.9% |

按两个参与方迭代均值的倒数相加，稳态汇总约为 Native **602.8 iter/s**、当前 **508.5 iter/s**，保留 **84.4%**。此数是并发负载的均值推导，不是按共同时间窗计数的硬件吞吐；不声称两个 Realm 的 GPU 指令获得空间并行或硬件安全隔离。

## 9. 结果说明与下一步优先级

本轮 Compute 时间倍率为 1.083–1.242×，ML / Attention 为 0.992–1.009×；IOCTL case 的倍率则为 2.89–25.43×。这些负载的瓶颈并不相同，不应将 glmark 分数比例推广成整个方案的统一开销。接近 1 的小幅正负差异，在本轮样本范围内不构成稳定加速结论。

优先级首先是大 BO 可用性：在保持 RMM 授权和正确映射的前提下，重新设计多区域/按页 backing、分配粒度或大 BO 的映射路径；仅继续压低 RPC 延迟无法让当前 152 MiB BO 成功。其次是 ENOMEM 后的错误传播与设备恢复：ResNet50 失败期间实际出现过 translation fault，需要单独定位，不能用随后还能计分代替恢复验证。最后才是在正确性成立的负载上继续减少细粒度 RPC、同步和生命周期操作；本轮只定位性能现象，没有分离测量单个 RMM 调用的固有成本。

## 10. 有效性、失败记录及未执行范围

- 首轮 `current-p42-suite-20261018` **FAIL / 作废**：rootfs 的 sed 缺 libacl.so.1；旧调度器对空脚本的中间返回码不足以判定，最终任务重复运行计数检查拦截。该轮计算、ML、NCNN、glmark 不进入统计。修复为显式可选配置文件后，增加逐项 correctness / backend / performance 标志检查；最终成功项目以独立 clean-suite 为统计来源。
- r2 的 12 个调度项为 10 个中间通过 / 2 FAIL（ResNet50、1080p），且 ResNet50 时出现 GPU translation fault，外层退出 1；不将故障后数据当成干净基线。后续新建 Realm 的 clean-suite 只重测可运行项目，主要性能表采用该批次及独立双 Client；ResNet50 / 1080p 保留 r2 失败证据，不计算比值。
- 本轮重新测量不等于复跑历史完整 32 项入口。旧 memfd PFN lifetime/log 用例不直接适用于 RMM 共享；独立 Host-vs-passthrough 不在本次 Native-vs-当前代理的范围，记为未执行。
- OpenCCA 当前 GPT/GPC 仍为软件实验环境；本报告测的是性能和所列功能检查，不证明抵御恶意 Host 的硬件机密性，也未实现跨 Group 的 GPU shadow 页表安全验证。
- 原生阶段保持 Panthor 到批次结束，再受控重启恢复 pmthor；没有通过危险的原生卸载路径来“修复”测试结果。最终资源与驱动恢复以 wrapper postflight 为准。

## 11. 复现入口与证据

本轮主要命令（均从仓库根目录执行，串行；clean 使用冻结 runner 排除已确认失败的 ResNet50 / 1080p，失败项仍来自 r2）：

```bash
python3 scripts/maintenance/lab-run.py --run-id current-p42-clean-suite-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/native-current-20261018/qualified/clean \
  --workload glmark --performance --benchmark-only --suite

python3 scripts/maintenance/lab-run.py --run-id current-p42-dual-perf-20261018 -- \
  python3 build/native-current-20261018/qualified/dual/launch.py \
  --images build/native-current-20261018/qualified/dual --workload compute --performance

python3 scripts/maintenance/lab-run.py --run-id native-p42-comparison-20261018 --allow-rk-reboot -- \
  python3 build/native-current-20261018/native-controller.py
```

| run-id | 外层退出码 | 状态 | 原始日志 | 环境审计 |
| --- | --- | --- | --- | --- |
| current-p42-suite-20261018 | 1 | FAILED | [原始日志](../../../../GPU-SFTP/log/realm-xshm/current-p42-suite-20261018/) | [wrapper](../../../../build/lab-runs/current-p42-suite-20261018/result.json) |
| current-p42-suite-r2-20261018 | 1 | FAILED | [原始日志](../../../../GPU-SFTP/log/realm-xshm/current-p42-suite-r2-20261018/) | [wrapper](../../../../build/lab-runs/current-p42-suite-r2-20261018/result.json) |
| current-p42-clean-suite-20261018 | 0 | COMPLETED | [原始日志](../../../../GPU-SFTP/log/realm-xshm/current-p42-clean-suite-20261018/) | [wrapper](../../../../build/lab-runs/current-p42-clean-suite-20261018/result.json) |
| current-p42-dual-perf-20261018 | 0 | COMPLETED | [原始日志](../../../../GPU-SFTP/log/realm-xshm/current-p42-dual-perf-20261018/) | [wrapper](../../../../build/lab-runs/current-p42-dual-perf-20261018/result.json) |
| native-p42-comparison-20261018 | 0 | COMPLETED | [原始日志](../../../../GPU-SFTP/log/native-current/native-p42-comparison-20261018/) | [wrapper](../../../../build/lab-runs/native-p42-comparison-20261018/result.json) |

[完整机器可读指标](../../../shared/evidence/native-current-20261018/metrics.json)，包含迭代 min / avg / max、阶段明细、算子和所有 glmark 场景。[逐运行审计](../../../shared/evidence/native-current-20261018/audit.json) 保存退出码、输入与原始文件校验数量。原始日志保留在本地，不提交运行日志或镜像。

| 冻结输入 | SHA-256 |
| --- | --- |
| client-Image | `bd823f88df688c98140c3d852fc19d84fd6a1523b3dfe34eb00a4ac961d126b1` |
| proxy-Image | `198ee612bdaa6c7a6000173cb0ad7cf8220ec89b24ee71eb4517724969e703ea` |
| initrd.cpio | `c3cdd4fa34c168e528460c9dd63f58354b5b66437c51973415fc5edb60931299` |
| runner.py | `271ded95304a4eca1b87662ada957c43daf172de20bdb7127c6d4cd834ead89d` |
| rootfs-panfrost.ext4 | `5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60` |

其他固件来源沿用 [P42 优化记录](PROXY_REALM_PERFORMANCE_OPTIMIZATION_20261018.md)；本轮详细输入与端到端校验清单见各 run 的 summary.json / controller-verification.json，以及 Native 的 local-sha256.json。
