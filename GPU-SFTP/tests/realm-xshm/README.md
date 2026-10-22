# Realm 共享、可信通知与 GPU 测试

当前源码包含P42、BO容量修复及GPUVM隔离v1。设计、冻结输入与验收边界统一见[当前基线](../../../docs/shared/CURRENT_BASELINE.md)，不再在工具说明中重复历史实验。

## 入口与构建

从仓库根目录运行。先读[环境主手册](../../../docs/start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)，确认Pi/RK角色、Host/RMM匹配并取得硬件租约：

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py --images <冻结包> --workload compute
```

| 选项 | 实际范围 |
| --- | --- |
| `--workload events` | 三Realm可信事件与拒绝语义 |
| `--workload compute` | 两个Client独立池、各18项API（含GPUVM隔离）、实际计算、权限与IRQ检查；需匹配新版冻结包 |
| `--workload compute --gpu-fault-isolation` | 另加实际GPU访问外域VA的翻译故障、错误fence和受害Group恢复检查 |
| `--workload glmark --performance --benchmark-only --suite --profiles glmark-720` | 默认256 MiB，完整720p性能 |
| 上述glmark模式加`--large-pool --profiles ncnn-resnet50 glmark-1080 ioctl compute-128` | 512 MiB池、每Realm1 GiB、CMA576 MiB；要求支持512 MiB的RMM |

冻结包包含`client-Image`、`proxy-Image`、`initrd.cpio`、`runner.py`及`hashes.json`。入口逐文件校验，仅上传变化内容；不替换Host/RMM/rootfs。rootfs须已准备并按只读方式使用。清理后已测包是`build/memfd-retirement-20261018/candidate/`（720p1157）；client/proxy/initrd/VMM已进入当前runtime-manifest。旧`build/bo-capacity-20261018/final/`保留为历史性能对照，不等同清理后源码。

### 多 Client 完整 720p / 1080p

2026-10-20分段BO候选已以192 MiB池跑通单Client完整1080p，905分；720p/128 MiB为1158。实现、配套内核、并发验收与证据见[分段内存报告](../../../docs/shared/GPU_BO_SEGMENTED_MEMORY_20261020.md)。此前连续BO实现的1080p单Client大池两轮为904/901，均值902.5；其小池失败与多Client NOT_RUN作为历史保留，见[原1080p验收](../../../docs/shared/GPU_GLMARK1080_VALIDATION_20261020.md)。

使用含当前 runner 和评分屏障脚本的冻结包，通过统一入口增加 `--clients 1|2|3|4 --compact-memory --pool-mib 128`，同时保留 `--workload glmark --performance --benchmark-only --suite --profiles glmark-720`。入口也接受单独的 `--profiles glmark-1080`；使用配套分段BO内核时可选 `--compact-memory --pool-mib 192`，具体已通过的Client数量以分段内存报告为准。旧连续BO内核的完整1080p单Client仍使用 `--large-pool --profiles glmark-1080`，不加compact参数。图形并发一次只选一个分辨率；ML并发另见下节。每个 Client 使用独立 Realm、授权池和 GPUVM，共享只读 rootfs 与可信 Proxy；同时派发完整负载，不缩减33个场景或跳过 validation。每个Client完成validation后通过串口报告READY并等待，Host确认全部READY后连续派发GO，再开始完整评分，避免validation耗时差异造成评分错位。

当前紧凑候选按每池大小 P MiB 分配：默认Client RAM=P+208、CMA=P+16；Proxy RAM=N×P+208+32×N、CMA=N×P+16。P可选128/160/192/256/336/384。默认Client保留192 MiB CMA外普通内存，显式ResNet50改为304MiB、RAM=P+320，见ML节。Proxy仍保留192+32×N MiB以容纳内核保留区、GEM/slab与共享页元数据。192 MiB池时4Client与Proxy总配置2704 MiB，对旧同池配置2944 MiB减少240 MiB；启动前仍额外保留256 MiB Host预算，实际内存最低值每秒记录。新组合的实测及固件要求见[多Client1080p设计记录](../../../docs/shared/GPU_MULTICLIENT1080_DESIGN_20261021.md)，不能继承旧配置PASS。该预算是准入门槛，不保证任意工作负载都能装入所选池；ENOMEM必须保留为失败，调整池后单独复测。原连续BO实现的1080p/128–256 MiB池存在碎片化失败；SG的160MiB池也已独立出现容量不足，不能用其raw分数替代clean检查。

性能模式仅使用已核验的CPU0–3：Proxy vCPU固定CPU1，所有Client vCPU共享CPU2–3；VMM串口/设备线程与Host使用CPU0，避免设备线程被忙等的vCPU挤占。记录每个线程的实际affinity；不因Client数增加启用未经核验的大核。这个固定CPU预算下的扩展结果同时包含CPU竞争和GPU共享影响。

同期Native/Realm图形对照可另加`--client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry`。
Client vCPU按2/3/2/3固定落核，Proxy仍为CPU1、VMM I/O为CPU0；固定policy0频率，并在退出时恢复原频率策略。
这些选项仅允许紧凑内存的单分辨率完整glmark性能模式，默认共享CPU2–3的行为保持不变。
`--telemetry`在每个Realm内每2秒记录`/proc/stat`，输出`cpu-realm-N.log`；窗口包含validation和评分，不能直接称为仅评分阶段的CPU占用。
同期对照方案与实际进度见[公平对照报告](../../../docs/shared/GPU_FAIR_MULTICLIENT_GLMARK_20261021.md)，
不能将新增绑核/频率配置与旧成绩混合作为单变量对照。

紧凑模式默认设置`swiotlb=8192`，保留16MiB共享DMA bounce buffer，替代每Realm默认64MiB固定预留；四Client单独ResNet50且显式启用`--reclaim-targets`时改用`swiotlb=4096`/8MiB。不禁用强制bounce或改变GPU授权池。普通/API模式保持原配置。完整负载及内核日志须检查I/O错误和缓冲区不足，不能只按内存公式判断适用范围。

每轮输出 `glmark-720-client-N.log` 或 `glmark-1080-client-N.log`、逐Client分数/实际分辨率/33场景FPS、validation、Host单调时钟观测的评分窗口重叠、派发时间差、`memory-samples.jsonl`、内核健康和全部Realm退出码。新initrd支持`memory-info`，runner保存绑定前后各Realm的`/proc/meminfo`，评分进度同时记录Client的MemAvailable/CmaFree。实际分辨率必须与所选profile一致。公共评分窗口至少覆盖联合窗口90%，否则不记为有效并行测试。串口观测存在传输误差，不等于硬件执行时间戳；各场景没有逐项跨Realm屏障。分数之和只能称聚合评分指数，不能称GPU总吞吐。

每轮结束后运行 `python3 scripts/maintenance/collect-realm-evidence.py --run-id <run-id> --output <新回收目录>`，逐文件校验远端SHA-256并保存外层结果、前后资源和Host健康记录；拒绝采集仍在运行的测试或覆盖既有目录。回收工具只读板端，不删除失败证据。

本地日志回收后可运行 `python3 scripts/analysis/summarize-multiclient-glmark.py --runs <各轮回收目录> --output <统计目录>`。统计独立轮次的Client均分、标准差、分数保留比例、评分均衡性和33场景均值，失败轮次单列；不同分辨率、冻结输入或内存配置分别统计，不混为同一组。复用固定Guest内核、静态工具和只读rootfs；评分屏障只需将当前performance-suite.sh和gpu-smoke.sh重新打包进initrd，无须重编内核。全部VM退出后再恢复CPU和GPU频率；每轮仍检查VM、挂载、loop与资源恢复。

构建工具：`bash scripts/build/build-realm-xshm.sh`，输出位于`build/realm-xshm/`；成套内核：`bash scripts/build/build-verified-kernels.sh realm`。配置和完整构建范围见[配置说明](../../../configs/performance/README.md)。`build-realm-xshm-initrd.py --help`列出可选探针与工作负载打包参数；仅编译工具不等于生成完整可验证包。

### 多 Client ML / NCNN

运行结果、Native历史参考、内存限制和逐项有效性见[多Client ML / NCNN报告](../../../docs/shared/GPU_MULTICLIENT_ML_20261021.md)及[仅含表格的结果](../../../docs/shared/GPU_MULTICLIENT_ML_RESULTS_20261021.md)。

同一 benchmark 入口接受 `--profiles ml-gemm ml-conv ml-depthwise ml-reduction ml-softmax ml-attention attention-320 ncnn-mobilenet_v2 ncnn-mobilenet_v3 --clients 1|2|3|4 --compact-memory --pool-mib 128`；ResNet50可单独选择 `--profiles ncnn-resnet50 --pool-mib 384`。`--workload glmark` 是沿用的启动选项，实际执行上述显式 profiles。需要包含 ML 屏障 dispatcher 和新版 runner 的冻结包，内核可复用已通过图形门槛的配套 SG 组合。显式含ResNet50的紧凑模式将Client普通内存提高到304MiB；启动前仍检查Host预算，不承诺四Client大模型均可装入。

2026-10-22实现增加预热后的单算子计时屏障，并在四Client时选择Proxy启动参数 `panthor.max_inflight_jobs=3`；需要配套原生Panthor准入驱动，不可用旧内核替代。ResNet50另可显式选择 `--reclaim-targets`：仅接受已验证回收版VMM的确切SHA、compact内存和单独的ResNet50 profile，采用扣除旧目标池后的稳态准入，顺序建立每个池并检查256MiB Host阶段余量；这不是运行期硬保留。四Client F配置使用336MiB池、296MiB Client普通配置和232MiB Proxy普通配置；每Client RAM640MiB/CMA344MiB、Proxy RAM1592MiB/CMA1360MiB，扣除回收目标后的稳态私有配置上界2808MiB。Client多余CMA预留从16降至8MiB，合计32MiB转给Proxy；Client扣除8MiB SWIOTLB后的普通预算与原304−16MiB相同。三Client保留384MiB池、原普通预算及16MiB SWIOTLB。四Client GPU租约需求超过原1GiB，须配套2GiB租约固件。七算子四Client及三/四Client模型九项均已硬件验收通过，完整720p1157、双Client功能/健康/退出/恢复及租约归零通过；具体输入、命令、原失败证据和限制见[修复报告](../../../docs/shared/GPU_ML_COMPLETION_20261022.md)。

每个 profile 在所有 Client READY 后一起释放 GO，全部完成后才进入下一项。六个独立ml profiles与原ml-all采用相同参数，各100次采样/5次预热，attention-320 为10/2，NCNN 为100 loops、2 threads、GPU0。独立profiles避免较快Client提前进入下一算子；仍接受历史ml-all，但它只在整套入口设置屏障，逐算子结果可能混入对方其他算子的竞争，应与独立profiles分开统计。逐 Client 核对 CPU reference、Mali 后端、完整耗时条目、错误日志及退出码；NCNN 随机输入/权重只验证 GPU 后端性能，不验证模型准确率。每轮还检查内核健康、可信 IRQ、授权池解绑/撤销和资源恢复。

`concurrent_ml` 保存每个 profile、各 Client 的 ms 耗时、屏障事件和完整 workload 的串口观测重叠。这包含初始化，不能当作单个算子迭代的精确重叠率，也不要求图形评分的90%门槛。每个 profile 必须有公共运行窗口；缺失时该项为`FAIL_NO_OVERLAP`、整轮仍FAIL，但在计算/驱动无错误时继续完成其余profiles。原始耗时保留，不计算该项性能保留率；这也不能单独证明平台不支持该Client数量。固定CPU2–3的竞争和初始化错位仍计入结果。耗时越低越好，性能保留为Native耗时/Client均值×100%，不采用分数保留公式。

先按前述collector回收，另将`build/lab-runs/<run-id>/lease-monitor.json`放入回收目录，再运行`python3 scripts/analysis/summarize-multiclient-ml.py --runs <回收目录...> --not-run <启动前内存拒绝目录...> --output <统计目录>`。统计器校验采集SHA、整轮状态、Host/Guest健康、Realm退出和租约归零；整轮若仅因公共窗口缺失而失败，保留无效项并提取其他有效项，不改写整轮FAIL。GPU/正确性/内核错误或其他异常仍拒绝采信。Native为明确标注的历史单进程参考。失败和受内存准入限制的未执行项独立保留，不能由有效耗时抵消。

需要在最终表格记录GPU提交失败时，显式增加`--failed-case <失败回收目录> <profile>`：必须有已校验的失败状态及GPU错误证据，该项仅输出失败标签、不使用耗时或保留比例，也不接受该失败整轮的其他性能数据。四Client Attention-320已有此类失败，见报告；不能用程序rc0或ML_CHECK=PASS覆盖Mesa错误。统计还检查各Realm完整串口日志中的GPU job timeout。

若某profile已执行完，但所在整轮随后出现GPU错误，可用`--invalid-case <失败回收目录> <profile>`保留尝试记录。必须有该profile完成状态及整轮GPU超时证据；仅输出整轮无效标签，原有无公共窗口仍保留为测量无效，均不输出性能数值。四Client Attention-256/320两轮失败不能据此采信更早profile的耗时。

## 接口语义

`realm-xshm`访问0600权限的`/dev/realm-xshm`，Guest需`CONFIG_REALM_XSHM=y`；调用进入真实RSI，不模拟RMM。管理操作需Guest `CAP_SYS_ADMIN`。关闭fd不注销Realm端点，必须显式unregister或销毁Realm。

REGISTER返回`[ABI, endpoint, capabilities, capacity]`。按实际能力位检查端点、持久事件、映射、身份描述、IRQ和ACK_ARM，不以历史cap31替代当前能力检查。当前成套Guest要求ACK_ARM；不支持的固件不能降级后冒充可信IRQ通过。端点ID不是远程证明。

| 操作 | 含义 |
| --- | --- |
| `register / unregister` | 本Realm端点生命周期 |
| `offer PEER / accept CHANNEL / close CHANNEL` | 通道创建与销毁 |
| `notify CHANNEL` | 通知对端，RMM验证参与者身份 |
| `ack-arm CHANNEL` | 原子确认当前pending并重新armed；排空后仍需acquire重查队列 |
| `irq-bind / irq-stats` | 绑定INTID127、读取真实分发计数 |
| `mem-offer CHANNEL SOURCE_IPA SIZE` | 提供已准备的私有DATA页 |
| `mem-attach GRANT TARGET_IPA` | 挂接到准备好的受保护RAM空闲L3 entries |
| `mem-status / mem-continue GRANT` | 查看或推进分段操作 |
| `mem-detach / mem-revoke GRANT` | 借用方解除、提供方撤销 |
| `mem-describe GRANT` | 经身份校验获得通道、双方端点与本Realm IPA |

内存操作返回`[grant, state, progress, pages]`，状态3表示分段未完成，应CONTINUE，不能重新OFFER/ATTACH。通知/提交不自动重试；EFAULT或传输超时不证明RMM未执行。

## 池与传输

- `pool-source SIZE / pool-target SIZE`建立内核持久池；每Realm最多8个，单池上限512 MiB，实际受CMA限制。默认性能池仍为256 MiB。
- `pool-info/read/write`用于受控诊断；多个池时用`--pool LOCAL_IPA`明确选择，目标访问需ACTIVE grant。不是任意用户缓冲区注册或hot-unload接口。
- `pool-fill-pages SEED [GRANT] / pool-check-pages SEED [GRANT]`检查每页首个64位字，不能表述为验证每个字节。
- `pool-bind GRANT`绑定前1 MiB通信队列，身份取自RMM；`pool-bind-gpu GRANT`还绑定池后部的对象分配区。数据区移除WB线性映射后建立WC映射，队列仍为WB。
- `pool-unbind GRANT`要求活动fd/session/对象引用已释放；未排空pin时保持quiesced，不能提前回收。绑定期间拒绝原始字访问和本地撤销。

当前源码的GPU BO优先分配按页取整的连续extent，空间碎片化时可回退到同一owner池内的多个分段，最多256段。GPU页表将这些分段映射到连续GPU VA；Client按段建立同一个用户VMA。GET_OBJECT按`segment_index`查询，每次查询均校验通道身份、owner、generation和权限；Client核对描述符一致、段范围、段间不重叠及总长度。控制页继续使用连续对象，GPUVM根绑定、pin、撤销和释放清零沿用原路径。池本身仍使用RMM授权的连续CMA区域。

分段描述符扩展了内部GET_OBJECT响应，必须使用同一冻结包内配套构建的Client和Proxy内核。仅更新runner或initrd不能启用该路径；旧720p/1080p成绩不代表新版已验收。

配套新版runner和smoke二进制可在`--workload compute`后增加`--bo-sg-mmap`：保留正常18项API，并额外用512 KiB对象填满小池、隔项释放，再申请1 MiB对象，检查跨分段的完整mmap、局部别名映射、初始清零和读写一致性。该选项包含预期的容量ENOMEM，不触发GPU故障；未选择时结果保留NOT_RUN。需同时检查Client内核日志的`MMAP ... segments>1`，不能仅凭用户态读写成功宣称已覆盖SG。

RMM授权与IRQ不替代消息边界验证。IRQ只提示队列检查；GPU完成仍由真实原生fence确认。当前固定一Realm一vCPU、INTID127，需匹配Host的LR预留策略。没有新增硬件GPT/GPC或跨Group shadow页表保护声明。

## 判定与证据

工具输出JSON：退出0为RMM成功，1为本地设备/ioctl失败，2为参数错误，3为RMM拒绝；负例必须核对具体返回，不能把任意失败当作拒绝通过。

runner保存实际命令、逐项退出码、输入哈希、串口及summary；wrapper保存前后资源。性能需同时核对Mali后端、正确性、完整场景、BO/提交错误、内核健康与恢复；不能只看score或外层exit0。未选择项目记为NOT_RUN。

GPUVM探针与隔离标志见[专项说明](../panthor-ioctl-smoke/GPUVM_ISOLATION.md)。互不信任Group须使用独立GPUVM并设置`DRM_PANTHOR_VM_CREATE_ISOLATED`；普通Mesa同GPUVM内的Group仍共享地址空间。预期故障只按本次准确时间戳/消息单列，其他故障仍导致健康检查失败。

最新结果及历史失败：[性能汇总](../../../docs/shared/GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)、[BO修复](../../../docs/shared/GPU_BO_CAPACITY_FIX_20261018.md)、[历史实现记录](../../../docs/archive/20261018/history/PROXY_TASK_SERVICE_IMPLEMENTATION_20261017.md)。
