# Native glmark 提分来源排查

**720p Native提高百余分的主要原因已复现：测试从schedutil动态调频改为固定1.8GHz。** 同一Host/nVHE启动下，仅切换CPU策略，完整720p为1561 → 1428 → 1559，独立审计通过。固定频率两轮均值1560，对旧策略1428提高132分/+9.24%；历史原生提高123.5分/+8.59%与此接近。未修改GPU运行代码，没有发现需要以新驱动优化解释这项主要差距的证据。

## 历史差值与已核对条件

| 分辨率 | 2026-10-18 Native | 2026-10-21 Native两轮 | 提高 |
| --- | ---: | ---: | ---: |
| 1280×720 | 1437 | 1563 / 1558，均值1560.50 | +123.50 / +8.59% |
| 1920×1080 | 997 | 1128 / 1132，均值1130 | +133 / +13.34% |

| 条件 | 旧Native | 新Native |
| --- | --- | --- |
| Host | opp3 #7 | opp3 #31 |
| 实际KVM启动模式 | VHE | nVHE |
| CPU启动/测试 | maxcpus=2，测试前动态上线CPU2/3 | maxcpus=4，测试前恢复CPU2/3在线 |
| A55调频 | schedutil，1008–1800MHz | performance，min=max=1800MHz |
| glmark落核 | CPU2 | CPU2 |
| GPU | 请求600、实际594MHz | 相同 |
| 用户态 | Panfrost rootfs、glmark/Mesa | 相同rootfs与glmark二进制SHA |
| 负载 | 完整33场景，null-noop / frame-end finish，shader cache关闭 | 相同，增加验证后的计分开始屏障 |
| 测试顺序 | API/计算/模型后跑glmark | 原生矩阵中720p单进程首先执行 |

共同rootfs SHA为 `5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60`；glmark二进制SHA为 `2251afb6b792c08181e14205756a29c13f8dd15d5a3eb8ab6652efe55a65bb2c`。测试脚本差异主要是启动屏障、内存观测与其他非glmark负载入口，glmark渲染命令和场景未减少。

旧720p每5秒采样68/70点、1080p为66/70点报告1800MHz。这不能证明帧内没有降频或升频延迟，也不能证明调频策略必然贡献全部分差，需用同一启动中的策略切换验证。

原始输入：`GPU-SFTP/log/native-current/native-p42-comparison-20261018/`、`build/fair-glmark-20261021/native/`；逐场景比较复用 `build/single-client-path-20261022/scene-analysis.json`。

## 调频策略单变量实验

`native-origin-cpufreq-20261022-a` 已完成并独立验收。冻结当前Host #31及原生Panthor模块，同一nVHE启动、rootfs、脚本、CPU2、GPU594MHz和完整720p，依次运行固定1.8GHz、旧schedutil 1008–1800MHz、固定1.8GHz。只改变A55共享调频策略及其最低频率；记录频率驻留计数和独立2秒采样。两端固定配置用于观察漂移，不更换Image、模块或固件。结束已恢复原protected配置和CPU0–1/pmthor。

| 顺序 | governor / 最低–最高频率 | 完整720p分数 | 计分区间1.8GHz驻留 | 计分区间调频状态加权均值 |
| --- | --- | ---: | ---: | ---: |
| A1 | performance / 1800–1800MHz | 1561 | 100% | 1800MHz |
| B | schedutil / 1008–1800MHz | 1428 | 70.16% | 1711.93MHz |
| A2 | performance / 1800–1800MHz | 1559 | 100% | 1800MHz |

固定频率两轮仅相差−2分/−0.13%。本轮旧策略1428对历史1437为−9/−0.63%；固定均值1560对公平新均值1560.5为−0.5/−0.03%。所以在保留当前Host和nVHE的情况下，切回旧策略已近似复现旧分数，无需将Host版本或VHE/nVHE变化当作解释百余分差距的必要因素。

逐场景同样吻合：本轮固定均值对公平新Native的FPS绝对相对差中位数0.14%，本轮schedutil对历史旧Native为0.63%；33场景的历史提分与本轮策略提分的Pearson相关系数0.971。这是对总分结论的补充，相关性本身不代替同启动A/B/A干预证据，也不证明历史全部细小残差只有一个原因。

改动目的｜隔离Native调频策略对总分的贡献｜旧策略1428 → 固定频率两轮均值1560（1561/1559），执行顺序A/B/A｜+132分/+9.24%｜同内核/原生模块/用户态/CPU2/GPU，仅改变governor/minimum；相对历史仍有Host、启动模式及运行顺序差异｜run-id `native-origin-cpufreq-20261022-a`，lab/采集/独立审计/资源检查均退出0；日志及命令见下文｜保留因果对照结论和现有固定频率测试口径；未改GPU运行代码，新增调频对照性能测量，不作为代码优化发布。

## 为什么先前采样没有看出差异

本轮B的166次独立2秒瞬时采样全部报告1800MHz；但同一计分窗口的`stats/time_in_state`差分显示，3.50%在1008MHz、0.93%在1200MHz、3.11%在1416MHz、22.30%在1608MHz、70.16%在1800MHz。即**29.84%的调频状态驻留时间低于1.8GHz**。A1/A2则均为100%驻留1800MHz。这里驻留计数来自cpufreq状态统计，不是独立物理时钟探针。

因此“多数瞬时读数是1.8GHz”不足以证明锁频无效；本轮甚至展示了全部瞬时读数为1.8GHz、仍有近30%低频驻留的例子。采样时的唤醒和共享频率策略可能影响读数时刻，本轮未单独证明其偏差机制，不将它写成另一项已定位故障。

CPU0–3共用policy0。原生glmark运行中可以阻塞在`drm_syncobj_array_wait_timeout`等待GPU，schedutil按CPU负载调整频率；CPU侧准备、内核提交、同步和中断处理会受到动态频率及切换影响。将策略设为performance、min=max=1800000 kHz后，这些CPU路径保持高频，GPU仍为594MHz。实验隔离的是governor与最低频率这组策略，不进一步拆分两者或各驱动阶段的独占贡献。

Client旧、新绝对分数接近，当前Client高非idle包含轮询，Host对vCPU也有接近100%的忙碌观测。本篇Native实验未测Client；后续[单Client调频对照](GPU_CLIENT_CPU_FREQUENCY_RESPONSE_20261022.md)已在同一protected启动、同candidate-f冻结包完成固定/动态/固定：1155/1159/1151，固定均值1153较动态−6/−0.52%，无锁频增益；三个条件的计分驻留均100%为1.8GHz。由此确认单Client动态策略原已维持最高频率，与Native动态时29.84%的低频驻留不同。轮询和Host/Realm idle记账的独占贡献未拆分；提交协议仍可独立优化，不由频率结论推出GPU硬件上限。

## 实现变化、验收与证据

本轮只改独立诊断runner以切换策略和记录观测；未修改GPU驱动、RMM、Host Image或固件。暂切nVHE及恢复均使用同一Image，SHA `8c277a621abcc8cf40c2801176f25ca62fff795be6e8a0324e8d64325040999d`；Panthor模块SHA `2091b3f718dccef040a700bc53fb8e628f24481e28764249adaad6a6e8fa37ac`。三个条件使用同一测试脚本和用户态载荷。

三项各33场景、既有validation 26/1/6及允许的已知例外、clean、真实Mali renderer、进程退出0、各项和整批Host内核健康通过；12个回收文件SHA通过，冻结执行脚本及rootfs前后SHA一致。每项166个计分采样均核验落核和GPU594MHz，最高温度均55.461℃。原extlinux、Image、protected/RME能力、CPU0–1和pmthor恢复通过，Pi/RK资源检查通过，无残留实验进程/loop。未新增API或多Client回归，未修改其运行代码。

1080p本轮未执行同样反切，不能由720p把历史1080p的全部133分定量归因为调频；VHE/nVHE和其他条件的细小残差未单独测量。新增结论限于720p主要差距，而非唯一历史因果分解。

```bash
python3 scripts/maintenance/lab-run.py \
  --run-id native-origin-cpufreq-20261022-a --allow-rk-reboot -- \
  python3 build/native-origin-20261022/native-mode-controller-v4.py \
  --round a --cases 720:1
```

外层命令/退出码与恢复记录：`build/lab-runs/native-origin-cpufreq-20261022-a/`。原始三项输出、用户态及模块SHA、内核日志和回收清单：`build/native-origin-20261022/native/native-origin-cpufreq-20261022-a/`。独立审计及逐场景对照：同实验目录`audit.json`、`finalize.log`；采样：`observations/`；冻结输入：`controller-hashes.json`；最终资源：`final-resources.json`。
