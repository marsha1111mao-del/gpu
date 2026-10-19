# Native 与 Proxy/Client 全部有效测试对照汇总（2026-10-18）

**2026-10-19 当前Host MMIO候选：完整720p1159。** 改动目的｜可信Host stage-2拒绝任务MMIO及异常返回｜Host #29的1152 → Host #31的1159｜**+7分/+0.61%**｜同RMM timer v6、完整33场景720p、256MiB、GPU请求600/实际594MHz、null-noop/finish、CPU未锁恒频；Host stage-2/异常处理同时变化，单轮仅记录组合观测｜`glmark720-host-mmio-denial-20261019-a`、退出0，命令与日志见[资源归属验收](GPU_HOST_MMIO_ENFORCEMENT_20261019.md)；正确性、Host/Guest健康及恢复通过｜保留局部实现，不替换原冻结1171/1170。Host内核与用户直接访问拒绝通过，普通VM物理访问仍FAIL_BYPASS_DETECTED。后续[失败复核](GPU_FAILURE_STATUS_AUDIT_20261019.md)已独立通过#31双Client各17项API/实际计算及生命周期健康；选定模拟主流程通过，完整物理对抗隔离不作完成声明。本轮仅修改测试入口/异常清理及文档，无新增性能测量，其他性能未重测。

**2026-10-19 上一受保护Host/Realm兼容候选（历史保留）：完整720p1152。** 改动目的｜EL1 Host/VMID/CPU初始化及RMM timer兼容修复｜Host #27/VHE的1168 → Host #29/protected/RMM timer v6的1152｜**−16分/−1.37%**｜同完整33场景720p、256MiB、GPU请求600/实际594MHz、null-noop/finish、CPU未锁恒频；Host/RMM、protected、VMID与CPU/timer机制同时变化，只归因组合效果｜`glmark720-protected-realm-20261019-c`、退出0，完整命令与日志见[受保护Realm验证](GPU_PROTECTED_REALM_VALIDATION_20261019.md)；validation、Host/Guest健康及资源恢复通过｜保留运行兼容候选，不替换原冻结1171/1170。双Client各17项API及计算已独立复验，其他性能未重测；protected模式Host内核物理写负例仍为FAIL_BYPASS_DETECTED，整体安全未完成。

**2026-10-19 上一IOMMU故障中断候选：完整720p1168。** 改动目的｜将managed IOMMU故障寄存器操作迁入RMM、修复绑定失败引用保留｜Host #26/RMM device-grant的1173 → Host #27/本轮RMM1168｜**−5分/−0.43%**，对原冻结均值1170.5为−2.5分/−0.21%｜完整33场景720p、256 MiB、GPU请求600/实际594MHz、null-noop/finish、CPU未锁恒频；Host/RMM同时变化，性能包不变，无并行探针｜`glmark720-iommu-irq-20261019-a`、退出0，命令与原始日志见[本轮报告](GPU_IOMMU_FAULT_VALIDATION_20261019.md)；正确性、Host健康和资源恢复通过｜保留开发候选，只记录组合观测，不替换原冻结1171/1170，不宣称稳定回退或提分。双Client功能/电源循环已独立复验，Native与其余性能未重测；Host物理MMIO负例仍FAIL。

**2026-10-19 上一设备授权/电源顺序候选：完整720p1173，对原冻结1171/1170均值1170.5为+2.5分/+0.21%。** 上一阶段1167→本版1173为+6/+0.51%，中间相同RMM/Host #23的1170→最终Host #26的1173为+3/+0.26%。run-id `glmark720-device-grant-20261019-b`、退出0，完整33场景、默认256 MiB、GPU请求600/实际594 MHz、离屏null-noop/finish；正确性、退出后内核健康与资源恢复通过。Host/RMM组合变化且各为单轮，只记录观测，不归因稳定优化。双Client各17项API/计算已独立重跑；其余性能未测，不替换原冻结基线。命令与证据见[当前设备授权验收](GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)。

**2026-10-19 此前安全服务开发候选：完整720p 1167，对原冻结1171/1170均值1170.5为−3.5分/−0.30%。** run-id `glmark720-gmem-reclaim-20261019-b`、退出0，完整33场景、默认256 MiB、GPU请求600/实际594 MHz，正确性、内核健康及资源恢复通过；Host/RMM/Proxy组合均有变化，只归因组合效果。双Client各17项API/计算重新验收通过，Native及其余性能未重测；不替换原冻结组合，下文33条与历史版本记录保留。命令、日志、失败与未执行项见[开发验收](SECURE_SERVICES_VALIDATION_20261019.md)。

**最新局部优化（本地）：GPUVM同步列表完整720p1171 / 1170；同期基线1162 / 1160，均值+9.5分/+0.82%。** 相对Native历史1437约保留81.5%，本轮未重测Native。新版本双Client各17项API/实际计算/权限/IRQ功能验收通过，但其他性能条目未重测。输入及逐次证据见[六方向优化实验](SAFE_PERFORMANCE_OPTIMIZATION_20261018.md)。下文原有33条对照及旧阶段分数保留其版本边界。

按每个测试的**最新有效记录**汇总：33 项单 Client 比较条目（17 IOCTL + 4 Compute + 7 ML/Attention + 3 NCNN + 2 glmark），另列 1 个双进程/双 Client 并发场景。它们不是历史“完整 32 项回归”的同一套编号，不能据此标注 32/32。

**版本边界：21 项来自 BO 修复后的实测，12 项沿用 P42 参考；双 Client 性能也沿用 P42。** 所列 Native 均来自同日原生测量，没有在 BO 修复后重新测量。当前版本未复测的条目不宣称当前 PASS，历史记录不覆盖旧失败。

**memfd退役阶段复测：该阶段RMM-only完整720p为1157（Native参考1437，保留80.5%），相对下文清理前1161为−4/−0.34%。** 新run-id为`memfd-retirement-720-20261018`；验证、完整命令与新哈希见[退役记录](MEMFD_RETIREMENT_20261018.md)。下文33项总表及逐场景数据保留为清理前对照，其余性能项未在退役后复测，不能据此宣称新代码全项通过。

| 分组 | 有有效 Native / Proxy 对照 | BO 修复后重新测量 | 仅 P42 参考 |
| --- | --- | --- | --- |
| IOCTL 共同路径 | 17 / 17 | 17 | 0 |
| Compute | 4 / 4 | 1（128 MiB） | 3 |
| ML / Attention | 7 / 7 | 0 | 7 |
| NCNN | 3 / 3 | 1（ResNet50） | 2 |
| glmark 完整测试 | 2 / 2 | 2 | 0 |
| 合计（不含并发） | 33 / 33 | 21 | 12 |
| 并发场景（单独统计） | 1 / 1 | 仅功能重验，无新性能数值 | 1 |

## 1. 比较条件与计算方法

平台为 RK3588 / Mali-G610，Host 6.12.0-opencca-pmthor-opp3 #7；GPU 请求 600 MHz、实测 594 MHz。CPU0–3 在线、A55 schedutil 1.008–1.8 GHz，未固定 CPU 频率。Native 单负载绑 CPU2；Proxy CPU1、Client CPU2，第二 Client CPU3。同一只读 rootfs 和用户态负载，关闭 Mesa shader cache。

| 标记 | 运行版本 / 资源 | 使用范围 |
| --- | --- | --- |
| 新·256M | P42 + BO 修复；每 Realm 1 vCPU / 768 MiB；池 256 MiB；CMA320 MiB | 完整 720p |
| 新·512M | 相同修复；每 Realm 1 vCPU / 1024 MiB；池 512 MiB；CMA576 MiB | IOCTL、128 MiB Compute、ResNet50、完整 1080p |
| P42参考 | 修复前冻结 P42；每 Realm 768 MiB；单 Client 池256 MiB / CMA320 MiB | 其余单 Client；当前修复版未复测 |
| P42并发参考 | 两个 Client 各128 MiB池，每 Realm768 MiB | 并发性能；与最新双 Client 功能回归区别 |

时间越低越好：时间倍率 = Proxy / Native；时间增幅 = (Proxy / Native − 1) × 100%；等效吞吐保留 = Native / Proxy × 100%。分数/FPS 越高越好：保留率 = Proxy / Native × 100%。**不把不同单位、不同负载合成一个平均性能百分比。** 每环境一个有效批次，迭代采样不等于独立批次；约1%的差异不证明稳定加速。512M 与 P42 资源不同，前后差异不能全部归因于分配器。

## 2. Compute、ML、NCNN 与 glmark

### Compute

| 项目 | Native | Proxy/Client | 单位 | 性能保留 | 时间倍率¹ | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| compute-4 | 1.362 | 1.691 | ms/iter | 80.5% | 1.242× | P42参考 |
| compute-16 | 4.709 | 5.303 | ms/iter | 88.8% | 1.126× | P42参考 |
| compute-64 | 17.788 | 19.274 | ms/iter | 92.3% | 1.084× | P42参考 |
| compute-128 | 35.605 | 37.724 | ms/iter | 94.4% | 1.060× | 新·512M |

### ML/Attention

| 项目 | Native | Proxy/Client | 单位 | 性能保留 | 时间倍率¹ | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| gemm_512_fp32 | 29.116 | 29.382 | ms/iter | 99.1% | 1.009× | P42参考 |
| conv2d_64x64x32_3x3_fp32 | 34.135 | 33.867 | ms/iter | 100.8% | 0.992× | P42参考 |
| depthwise_conv_128x128x128_3x3_fp32 | 21.894 | 21.896 | ms/iter | 100.0% | 1.000× | P42参考 |
| block_reduction_32mib_fp32 | 10.695 | 10.639 | ms/iter | 100.5% | 0.995× | P42参考 |
| row_softmax_16384x256_fp32 | 19.404 | 19.277 | ms/iter | 100.7% | 0.993× | P42参考 |
| single_head_attention_256x64_fp32 | 773.543 | 775.953 | ms/iter | 99.7% | 1.003× | P42参考 |
| single_head_attention_320x64_fp32 | 1221.823 | 1224.653 | ms/iter | 99.8% | 1.002× | P42参考 |

### NCNN

| 项目 | Native | Proxy/Client | 单位 | 性能保留 | 时间倍率¹ | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| ncnn-mobilenet_v2 | 31.260 | 32.140 | ms/inference | 97.3% | 1.028× | P42参考 |
| ncnn-mobilenet_v3 | 28.360 | 28.860 | ms/inference | 98.3% | 1.018× | P42参考 |
| ncnn-resnet50 | 1162.990 | 1463.960 | ms/inference | 79.4% | 1.259× | 新·512M |

### glmark

| 项目 | Native | Proxy/Client | 单位 | 性能保留 | 时间倍率¹ | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| glmark-720 | 1437 | 1161 | score | 80.8% | — | 新·256M |
| glmark-1080 | 997 | 901 | score | 90.4% | — | 新·512M |

¹ 时间倍率只适用于耗时。Compute 4/16 MiB 为100次+5预热，64/128 MiB为20+5；均排除 CPU prepare，抽查16个输出。ML六算子100+5，Attention320为10+2，并与 CPU reference 核对。NCNN为100 loops、2 threads、GPU0；随机权重性能模型，不是推理准确率实验。

两个 glmark 均为完整33计分场景，验证结果为26 Success / 1已知 medium-function数值差异 / 6 Unknown，非预期失败0；BO、映射、提交错误0。因此运行 PASS 不表示33个 validation 子项全部成功。

## 3. 全部17项 IOCTL 路径

每项3次预热+20次采样，计时包括 open→basic checks→case→close，不含 VM 启动，**不是一次裸 ioctl 的延迟**。共同 profile 比较双方支持的正向语义；17项均为新·512M，Native来自原生批次。

| 用例 | Native µs/case | Proxy µs/case | 时间倍率 | 绝对差 µs | 较 P42 旧值变化 |
| --- | --- | --- | --- | --- | --- |
| basic | 23.655 | 527.348 | 22.29× | 503.693 | +1.4% |
| vm-create | 39.959 | 709.216 | 17.75× | 669.257 | +0.3% |
| bo-create | 60.755 | 1630.475 | 26.84× | 1569.720 | +78.7% |
| bo-lifecycle | 109.684 | 2085.621 | 19.01× | 1975.937 | +58.2% |
| bo-mmap | 106.986 | 1690.996 | 15.81× | 1584.010 | +81.3% |
| vm-bind | 2472.866 | 7910.846 | 3.20× | 5437.980 | +10.8% |
| vm-bind-async-sync | 203.894 | 2430.254 | 11.92× | 2226.360 | +44.0% |
| vm-state-flush | 69.929 | 814.727 | 11.65× | 744.798 | +0.5% |
| syncobj-lifecycle | 39.522 | 537.994 | 13.61× | 498.472 | -2.1% |
| syncobj-wait | 49.497 | 990.121 | 20.00× | 940.624 | -0.4% |
| syncobj-transfer | 42.745 | 845.177 | 19.77× | 802.432 | -0.5% |
| syncobj-timeline-wait | 72.306 | 1403.894 | 19.42× | 1331.588 | -1.2% |
| syncobj-signal-query | 65.583 | 1325.362 | 20.21× | 1259.779 | -0.5% |
| sync-file-snapshot | 1718.525 | 43067.675 | 25.06× | 41349.150 | -1.4% |
| group-lifecycle | 202.174 | 1523.244 | 7.53× | 1321.070 | -2.6% |
| group-submit-syncpoint | 238.457 | 1948.931 | 8.17× | 1710.474 | +8.2% |
| tiler-heap-lifecycle | 284.002 | 1434.854 | 5.05× | 1150.852 | -0.1% |

BO create/lifecycle/mmap 与部分 bind 路径在新512M配置下比旧256M批次明显变慢；这是需保留的观测，不能以总体工作负载分数掩盖。新分配器与大池配置同时变化，现有数据没有分离池规模、分配扫描/清零、映射或批次条件的贡献，不能将增幅全部归因于某一项。sync-file-snapshot 约43ms/case仍是突出的细粒度开销。

## 4. Compute 分阶段平均耗时

单位 µs/iter；CPU prepare 单列但不计入总迭代时间。阶段是程序计时区间，不是 GPU 硬件执行时间。

| 档位 | 阶段 | Native | Proxy/Client | 来源 |
| --- | --- | --- | --- | --- |
| compute-4 | cpu_prepare | 1783.11 | 1901.05 | P42参考 |
| compute-4 | buffer_upload | 750.21 | 795.51 | P42参考 |
| compute-4 | dispatch_call | 195.33 | 436.89 | P42参考 |
| compute-4 | memory_barrier | 40.86 | 90.91 | P42参考 |
| compute-4 | map_wait | 373.62 | 365.70 | P42参考 |
| compute-4 | unmap | 1.58 | 1.84 | P42参考 |
| compute-16 | cpu_prepare | 7100.65 | 7496.17 | P42参考 |
| compute-16 | buffer_upload | 3071.53 | 3309.28 | P42参考 |
| compute-16 | dispatch_call | 227.75 | 516.87 | P42参考 |
| compute-16 | memory_barrier | 40.56 | 90.30 | P42参考 |
| compute-16 | map_wait | 1367.10 | 1384.14 | P42参考 |
| compute-16 | unmap | 2.00 | 2.89 | P42参考 |
| compute-64 | cpu_prepare | 28327.90 | 29781.95 | P42参考 |
| compute-64 | buffer_upload | 12371.90 | 13490.15 | P42参考 |
| compute-64 | dispatch_call | 285.85 | 629.85 | P42参考 |
| compute-64 | memory_barrier | 39.75 | 83.35 | P42参考 |
| compute-64 | map_wait | 5088.70 | 5068.25 | P42参考 |
| compute-64 | unmap | 1.95 | 2.25 | P42参考 |
| compute-128 | cpu_prepare | 56624.40 | 59749.35 | 新·512M |
| compute-128 | buffer_upload | 24824.60 | 27083.75 | 新·512M |
| compute-128 | dispatch_call | 292.80 | 652.55 | 新·512M |
| compute-128 | memory_barrier | 40.35 | 96.90 | 新·512M |
| compute-128 | map_wait | 10444.85 | 9888.85 | 新·512M |
| compute-128 | unmap | 2.05 | 2.45 | 新·512M |

128 MiB 总时间从P42的38.575ms变为37.725ms（-2.2%），但同时改用了512M配置；只能记录变化，不能宣称分配器单独加速2.2%。其上传27.084ms仍高于原生24.825ms，发起0.653ms高于原生0.293ms。

## 5. 双进程 / 双 Client 并发参考

| 参与方 | Native ms/iter | Proxy ms/iter | 等效吞吐保留 | 版本 |
| --- | --- | --- | --- | --- |
| dual-0 | 3.312 | 3.952 | 83.8% | P42参考 |
| dual-1 | 3.323 | 3.914 | 84.9% | P42参考 |

并发4 MiB、每方100+5，**包含 CPU prepare**，不与单 Client Compute直接混比。按两方均值倒数相加，Native 602.8 iter/s，Proxy 508.5 iter/s，保留 **84.4%**；这不是共同时间窗计数，也不证明 GPU 指令空间并行。BO修复后只重验双 Client 功能，未重测这一并发性能。

## 6. glmark 两种分辨率的全部场景

下表 FPS 均使用修复后的有效完整运行，场景按名称逐一匹配。

| 场景 | 720 Native | 720 Proxy | 保留 | 1080 Native | 1080 Proxy | 保留 |
| --- | --- | --- | --- | --- | --- | --- |
| [build] use-vbo=false | 994 | 1124 | 113.1% | 748 | 995 | 133.0% |
| [build] use-vbo=true | 2299 | 1759 | 76.5% | 1785 | 1475 | 82.6% |
| [texture] texture-filter=nearest | 2311 | 1762 | 76.2% | 1571 | 1344 | 85.6% |
| [texture] texture-filter=linear | 2321 | 1764 | 76.0% | 1580 | 1347 | 85.3% |
| [texture] texture-filter=mipmap | 2307 | 1754 | 76.0% | 1585 | 1347 | 85.0% |
| [shading] shading=gouraud | 1919 | 1554 | 81.0% | 1531 | 1317 | 86.0% |
| [shading] shading=blinn-phong-inf | 1890 | 1534 | 81.2% | 1449 | 1288 | 88.9% |
| [shading] shading=phong | 1709 | 1437 | 84.1% | 1267 | 1168 | 92.2% |
| [shading] shading=cel | 1705 | 1428 | 83.8% | 1240 | 1148 | 92.6% |
| [bump] bump-render=high-poly | 1086 | 1062 | 97.8% | 944 | 949 | 100.5% |
| [bump] bump-render=normals | 2611 | 1880 | 72.0% | 1826 | 1478 | 80.9% |
| [bump] bump-render=height | 2462 | 1814 | 73.7% | 1651 | 1389 | 84.1% |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0; | 1783 | 1483 | 83.2% | 937 | 929 | 99.1% |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1; | 829 | 840 | 101.3% | 447 | 435 | 97.3% |
| [pulsar] light=false:quads=5:texture=false | 1686 | 1400 | 83.0% | 1179 | 1100 | 93.3% |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4 | 388 | 226 | 58.2% | 233 | 172 | 73.8% |
| [desktop] effect=shadow:windows=4 | 845 | 698 | 82.6% | 579 | 571 | 98.6% |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map | 47 | 46 | 97.9% | 47 | 46 | 97.9% |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata | 47 | 46 | 97.9% | 47 | 46 | 97.9% |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map | 66 | 65 | 98.5% | 65 | 64 | 98.5% |
| [ideas] speed=duration | 480 | 441 | 91.9% | 426 | 402 | 94.4% |
| [jellyfish] <default> | 1210 | 1118 | 92.4% | 763 | 757 | 99.2% |
| [terrain] <default> | 78 | 42 | 53.8% | 57 | 36 | 63.2% |
| [shadow] <default> | 982 | 746 | 76.0% | 687 | 600 | 87.3% |
| [refract] <default> | 196 | 137 | 69.9% | 144 | 115 | 79.9% |
| [conditionals] fragment-steps=0:vertex-steps=0 | 1980 | 1562 | 78.9% | 1358 | 1198 | 88.2% |
| [conditionals] fragment-steps=5:vertex-steps=0 | 1862 | 1498 | 80.5% | 1259 | 1144 | 90.9% |
| [conditionals] fragment-steps=0:vertex-steps=5 | 1976 | 1569 | 79.4% | 1337 | 1202 | 89.9% |
| [function] fragment-complexity=low:fragment-steps=5 | 1973 | 1570 | 79.6% | 1362 | 1199 | 88.0% |
| [function] fragment-complexity=medium:fragment-steps=5 | 1747 | 1439 | 82.4% | 1093 | 1066 | 97.5% |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5 | 1971 | 1568 | 79.6% | 1328 | 1199 | 90.3% |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5 | 1970 | 1568 | 79.6% | 1331 | 1200 | 90.2% |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5 | 1737 | 1433 | 82.5% | 1082 | 1060 | 98.0% |

## 7. 功能、安全检查及未执行范围

| 检查 | 最新记录 | Native性能比值 |
| --- | --- | --- |
| 大池逐页共享 / 解绑 / 撤销 | 512 MiB：131072 / 131072 页通过；大负载批次exit0 | 不适用 |
| 双 Client API / 实际计算 | 2×17 API、两份小Compute通过；3 Realm健康 | 功能验证，不作为并发性能 |
| 越权与通知负例 | 跨owner描述拒绝、模糊池选择拒绝、权限自测、IRQ负例/合并检查通过 | 不适用 |
| 最新单Client内核健康 | 720p / 大负载批次两VM退出0；受检fault/timeout/WARN/Oops等无命中 | 不适用 |
| 历史完整32项回归入口 | 本次未重新执行；旧memfd专项不直接等同RMM共享路径 | 不标记32/32 |
| 独立Host-vs-passthrough | 本次未执行，也不混入Proxy/Client比值 | 无新增结果 |
| 恶意Host硬件机密性 / GPU跨Group shadow隔离 | GPT/GPC实验边界不变，未新增实现或安全证明 | 不能由功能PASS推导 |

旧ResNet50 ENOMEM/Vulkan错误及1080p不完整场景的939分、故障后的1156/1157等不计入性能。诊断轮1080p仅部分场景的分数也排除。历史FAIL与调度失败保留在原报告和原始日志；后续成功不改写它们。

## 8. 改动影响与判断

BO修复的默认720p：**1154 → 1161，+7 / +0.61%**，一次有效复测，按批次小幅波动处理。1080p与ResNet50由失败变为有效完成，旧失败时间/分数不参与加速计算。当前最明确的剩余性能问题是细粒度调用路径，尤其snapshot与BO生命周期；ML/Attention算子本体大多接近原生。大池下BO微测试退化应通过同配置对照定位，再考虑优化。本次统计本身没有引入代码或分数变化。

## 9. 逐运行证据与复现命令

以下6个有效运行外层退出码均为0。单项命令/退出码及验证标志见原始目录的 commands.jsonl / summary.json；Native目录保存其测量命令与校验清单。run-id已存在，实际重跑需使用新的唯一名称，并依照主runbook持有硬件租约。

| run-id | 用途 | 退出码 | 原始日志 | wrapper |
| --- | --- | --- | --- | --- |
| native-p42-comparison-20261018 | Native全部对照 | 0 | [日志](../../GPU-SFTP/log/native-current/native-p42-comparison-20261018/) | [记录](../../build/lab-runs/native-p42-comparison-20261018/result.json) |
| current-p42-clean-suite-20261018 | P42单Client参考 | 0 | [日志](../../GPU-SFTP/log/realm-xshm/current-p42-clean-suite-20261018/) | [记录](../../build/lab-runs/current-p42-clean-suite-20261018/result.json) |
| current-p42-dual-perf-20261018 | P42并发性能参考 | 0 | [日志](../../GPU-SFTP/log/realm-xshm/current-p42-dual-perf-20261018/) | [记录](../../build/lab-runs/current-p42-dual-perf-20261018/result.json) |
| bo-cap512-default720-20261018 | 新720p默认池 | 0 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-default720-20261018/) | [记录](../../build/lab-runs/bo-cap512-default720-20261018/result.json) |
| bo-cap512-targets-r2-20261018 | 新IOCTL/128MiB/ResNet/1080p | 0 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-targets-r2-20261018/) | [记录](../../build/lab-runs/bo-cap512-targets-r2-20261018/result.json) |
| bo-cap512-dual-isolation-20261018 | 新双Client功能与负例 | 0 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-dual-isolation-20261018/) | [记录](../../build/lab-runs/bo-cap512-dual-isolation-20261018/result.json) |

`native-p42-comparison-20261018`：

```bash
python3 scripts/maintenance/lab-run.py --run-id native-p42-comparison-20261018 --allow-rk-reboot -- \
  python3 build/native-current-20261018/native-controller.py
```

`current-p42-clean-suite-20261018`：

```bash
python3 scripts/maintenance/lab-run.py --run-id current-p42-clean-suite-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/native-current-20261018/qualified/clean --workload glmark --performance --benchmark-only --suite
```

`current-p42-dual-perf-20261018`：

```bash
python3 scripts/maintenance/lab-run.py --run-id current-p42-dual-perf-20261018 -- \
  python3 build/native-current-20261018/qualified/dual/launch.py --images build/native-current-20261018/qualified/dual --workload compute --performance
```

`bo-cap512-default720-20261018`：

```bash
python3 scripts/maintenance/lab-run.py --run-id bo-cap512-default720-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/bo-capacity-20261018/cap512-qualified --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

`bo-cap512-targets-r2-20261018`：

```bash
python3 scripts/maintenance/lab-run.py --run-id bo-cap512-targets-r2-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/bo-capacity-20261018/final --workload glmark --performance --benchmark-only --large-pool --suite --profiles ncnn-resnet50 glmark-1080 ioctl compute-128
```

`bo-cap512-dual-isolation-20261018`：

```bash
python3 scripts/maintenance/lab-run.py --run-id bo-cap512-dual-isolation-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/bo-capacity-20261018/final --workload compute
```

720p实际使用cap512-qualified冻结包；与final的Image/initrd/默认配置相同。以上命令按wrapper实录保留，不以重构后的当前入口冒充历史执行命令。

机器可读数据：[本汇总metrics.json](evidence/native-proxyclient-summary-20261018/metrics.json)，含33行比值、min/avg/max、阶段/场景原值、各项来源与实际执行命令。输入审计：[P42/Native](evidence/native-current-20261018/audit.json)、[BO修复](evidence/bo-capacity-fix-20261018/audit.json)。历史与实现：[P42完整性能报告](../archive/20261018/history/GPU_NATIVE_CURRENT_REALM_PERFORMANCE_20261018.md)、[BO修复报告](GPU_BO_CAPACITY_FIX_20261018.md)、[2026-10-15历史32项对照](../archive/20261018/history/GPU_REGRESSION_COMPARISON_20261015.md)。
