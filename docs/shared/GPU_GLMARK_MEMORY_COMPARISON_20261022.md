# glmark 原生与 Client/Proxy 任务内存实测（2026-10-22）

本轮补采完整 glmark 的 **720p、1080p 单 Client** 内存分项，各配置一轮；原生对应单进程。没有重跑旧性能 A/B 矩阵，没有改 GPU 运行代码。Client/Proxy 使用已经回收旧目标后备页的 VMM，RPC、通知和完成回传计时均关闭。

单位为 MiB（2²⁰字节）。以下是每 200 ms 采样取得的**各分项峰值及其合计**，不是同一时刻的整机物理峰值，也没有包含全部协议私有分配。

## 1280×720，单 Client

| 内存项目 | 原生 | Client/Proxy（优化后） |
| --- | ---: | ---: |
| GPU 任务缓冲 | 93.80 | 91.46 |
| CPU 渲染进程与运行缓冲 | 132.63 | 102.18 |
| 共享池余量及控制空间 | — | 36.54 |
| Client 原目标后备页 | — | 0.00（已回收） |
| 已计量私有管理结构 | — | 至少 0.75 |
| **已测分项峰值合计** | **226.43** | **230.93** |

已测合计增加 **4.50 MiB / 1.99%**。完整源池为 128 MiB，GPU BO 与余量/控制空间是这个池的分解，不能在完整池之外再重复相加。

## 1920×1080，单 Client

| 内存项目 | 原生 | Client/Proxy（优化后） |
| --- | ---: | ---: |
| GPU 任务缓冲 | 170.00 | 181.08 |
| CPU 渲染进程与运行缓冲 | 131.83 | 101.10 |
| 共享池余量及控制空间 | — | 10.92 |
| Client 原目标后备页 | — | 0.00（已回收） |
| 已计量私有管理结构 | — | 至少 1.13 |
| **已测分项峰值合计** | **301.83** | **294.23** |

已测合计相差 **−7.59 MiB / −2.52%**。完整源池为 192 MiB；合计按未取整字节计算，再保留两位小数。

## 如何理解额外开销

可以单独确认的**池内余量/控制空间加已计量私有元数据**，720p 为 **37.29 MiB**，1080p 为 **12.05 MiB**，分别相当于原生已测分项合计的 **16.47% / 3.99%**。这部分仍然存在；旧目标后备已从挂接后的稳态占用中消除，启动时先分配目标 CMA 的需求仍存在。

总量差还叠加了 CPU 驻留峰值与 GPU BO 采样峰值差异，不能将它直接解释成纯粹的转发开销，更不能据 1080p 的负差宣称共享本身节省内存。CPU 峰值样本中，原生文件页 PSS 为 52.68 / 52.71 MiB，共享为 26.62 / 23.85 MiB；原生可用 RAM 约 2.9 GiB，Client 当时只有约 29 / 24 MiB。两侧内存压力与驻留状态不同，本轮没有通过额外 A/B 隔离原因。200 ms 采样还可能遗漏短暂 BO 峰值，原生与代理的对象生命周期节奏也不同。

在共享 BO 峰值样本中，池的分解为：

| 分解项目 | 720p | 1080p |
| --- | ---: | ---: |
| GPU BO | 91.460938 | 181.078125 |
| buddy 空闲 | 33.535156 | 7.917969 |
| 其他池内对象（fence 页） | 0.003906 | 0.003906 |
| 池内控制及分配器保留 | 3.000000 | 3.000000 |
| **完整源池** | **128.000000** | **192.000000** |

## 口径与实验条件

- GPU：原生通过 GEM 创建/释放探针区分用户 BO 与驱动内部 BO，主表只计有实际后备页的用户 BO 采样峰值；共享读取 Proxy manager 的 `GPU_BO` 对象申请空间，所有源池页均有真实物理后备。原生用户 BO 的请求与驻留采样峰值本轮相同。
- CPU：glmark 进程的 `Pss_Anon + Pss_File`，不含 `Pss_Shmem`。额外抽查原生 16 个 DRM 映射，RSS/PSS 均为 0；GPU BO 单独统计。该分项包含进程映射的库与资源文件驻留。
- 元数据：只计 manager 的 domain、buddy、object、grant、slab、SG 等结构申请字节下限，不含全部 xarray 节点、分配器取整和全部请求快照、队列私有副本及完成记录。不能把 0.75 / 1.13 MiB 当作全部转发和安全检查成本。
- 排除 Host、Proxy、Client 的普通 OS/VM 固定预算、一般驱动内存、GPU 页表和采样工具自身；不使用 VMM RSS 代替 Guest 私有物理页。
- RK3588 / Mali-G610；同一 Host #31、相同固件和 rootfs/Mesa/glmark。原生临时使用 nVHE + Host Panthor，共享使用 protected + Proxy/Client Realm；Client/Proxy Image 与最新 `candidate-c` 一致，诊断 initrd/runner 额外加入内存采样。VMM SHA 为 `fb2c3816d776a288d34b8c7f5b74b1e1722bb64d79079cac9c303319361310ec`。
- 两侧 CPU 固定 1.8 GHz，GPU 请求 600 MHz、实际 594 MHz；原生进程与单 Client vCPU 在 CPU2，Proxy vCPU 在 CPU1，VMM I/O 在 CPU0。`null-noop`、`finish`、完整 33 场景与既定 validation/clean 检查；共享保持 `--transfer-capture` 开启，三个高频计时开关均关闭。

两种共享配置在绑定后直接读取对应 VMM 的 guest_memfd 页缓存：源池分别为 32768 / 49152 页，Client 旧目标区的 `cached_pages`、`cache_only_pages`、`prepared_pages` 均为 **0**。这证明工作负载阶段没有额外保留 128 / 192 MiB 旧后备；没有靠 VMM RSS 或 Guest CMA 计数推断回收。

## 测试结果与性能记录

| run-id / 配置 | 结果 | 说明 |
| --- | --- | --- |
| `glmark-memory-720-1c-20261022-a` | setup FAIL / rc1 | 旧诊断模块 vermagic 不匹配，在 `gpu-memory load-pool` 退出，未进入 glmark；两个 Realm 正常退出0/0，失败输入和日志保留 |
| `glmark-memory-720-1c-20261022-b` | PASS / rc0，1132分 | 重编匹配当前 Guest 的诊断模块；有效 Proxy 负载样本1794，Client含任务样本1700；原目标后备0 |
| `glmark-memory-1080-1c-20261022-a` | PASS / rc0，881分 | 有效 Proxy 负载样本1784，Client原目标后备0 |
| `glmark-memory-native-20261022-a`，720p | PASS / 外层rc0，1538分 | 总样本1726、含任务1691；GEM创建/释放1222/1222，最终对象和驻留字节0，漏记/溢出0 |
| 同上，1080p | PASS / 外层rc0，1118分 | 总样本1723、含任务1690；GEM创建/释放1232/1232，最终对象和驻留字节0，漏记/溢出0 |

四个有效配置均完成完整 33 场景、Mali renderer、既定 validation（26成功/1既有数值例外/6无判据）和 clean 检查，Host/Guest 健康检查通过。两个共享运行的 GPU/DMA 租约最终归零，Realm 均退出0/0。原生结束后逐字恢复 extlinux，Host Image SHA 不变，并恢复 protected、CPU0–1、pmthor；所有采集文件逐文件核验 SHA。

| 目的 | 历史对照 → 本轮采样分数 | 分差 / 百分比 | 可比边界与状态 |
| --- | --- | --- | --- |
| 720p共享内存采样 | 同candidate-c关闭计时1159 → 1132 | −27 / −2.33% | GPU代码、池、频率、落核、TRANSFER设置一致；新增200ms采样与诊断模块/runner，不同时段、各单轮；保留内存测量，不归因单项计时开销 |
| 1080p共享内存采样 | 历史固定频率902 → 881 | −21 / −2.33% | 同分辨率/池/固定频率，候选和RMM组合、TRANSFER设置及时段不同；不作为同输入A/B |
| 原生内存采样 | 固定频率历史1560.50/1130 → 1538/1118 | −22.50/−1.44%；−12/−1.06% | 同Host、rootfs、分辨率、CPU2及锁频设置；新增GEM探针与200ms采样，时段/固件组合不同；不归因单一因素 |

本轮分数用于完整运行和门槛检查，**不替换既有性能主表，也不替换动态调频结果**。仅增加内存测量，没有做本轮采样开/关性能 A/B。2–4 Client 内存分项及全部协议私有分配未测，不从单 Client 外推；未新增 API/计算全矩阵回归。

## 命令与证据

以下命令的 run-id 已使用，复测必须换新 ID。凭据由会话环境提供，不写入脚本。冻结包、临时采样源码和模块位于忽略的 `build/glmark-memory-20261022/`，不属于发布运行载荷。

```bash
python3 scripts/maintenance/lab-run.py --run-id glmark-memory-720-1c-20261022-b -- \
  python3 build/glmark-memory-20261022/run-shared.py --size 720
python3 scripts/maintenance/lab-run.py --run-id glmark-memory-1080-1c-20261022-a -- \
  python3 build/glmark-memory-20261022/run-shared.py --size 1080
python3 scripts/maintenance/lab-run.py --allow-rk-reboot --run-id glmark-memory-native-20261022-a -- \
  python3 build/glmark-memory-20261022/native-mode-controller-v4.py --round a --cases 720:1 1080:1
python3 scripts/analysis/summarize-glmark-memory.py \
  --experiment build/glmark-memory-20261022 --bundle build/glmark-memory-20261022/bundle-v2 \
  --shared build/glmark-memory-20261022/runs/glmark-memory-720-1c-20261022-b \
    build/glmark-memory-20261022/runs/glmark-memory-1080-1c-20261022-a \
  --native build/glmark-memory-20261022/native/glmark-memory-native-20261022-a \
  --output build/glmark-memory-20261022/analysis.json
```

共享包装命令通过 Host 观测与租约 monitor 调用标准 Realm 入口；每项具体命令、rc、前后资源、目标后备直接读数和健康证据在 `build/lab-runs/<run-id>/`。原始共享日志及逐文件SHA在 `build/glmark-memory-20261022/runs/<run-id>/`，原生在 `native/glmark-memory-native-20261022-a/`，失败在 `failed/glmark-memory-720-1c-20261022-a/`。观测在同实验的 `observations/<run-id>/`，完整字节值与独立核验在 `analysis.json`。

结束恢复命令为 `lab-run.py --run-id glmark-memory-finalize-20261022-a -- python3 build/glmark-memory-20261022/finalize.py`：恢复普通 candidate-c 的 initrd/runner，逐项确认四个运行输入 SHA，移除内存采样的自动入口；不删除诊断实现或原有优化。恢复命令 rc0，证据为该 lab 目录的 `normal-runtime-restored.json`；Pi/RK 终检与最终审计见同实验的 `final-resources.json`、`final-audit.json`。
