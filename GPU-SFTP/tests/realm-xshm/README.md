# Realm 共享、可信通知与 GPU 测试

当前源码包含P42、BO容量修复及GPUVM隔离v1。设计、冻结输入与验收边界统一见[当前基线](../../../docs/shared/CURRENT_BASELINE.md)，不再在工具说明中重复历史实验。

### 私有模式 GPU 完成 eventfd 探针（待实机运行）

`gles-compute-smoke --gpu-eventfd --count 65536 --iterations 4 --alu-iters 64 /dev/dri/renderD128`
在实际 GLES dispatch 后导出 EGL native sync_file，导入本地 binary syncobj 并转到 timeline point 7，分别注册完成 eventfd。
只执行 glFlush 提交；通知检查前不执行 CPU SIGNAL、glFinish 或阻塞结果映射。
探针要求底层 fence 驱动名为 `panthor-client-private`，收到两个通知后再检查整体及各 fence 的成功状态，并逐元素核验每轮计算结果。
它允许注册前已经完成的 GPU fence；因此不证明一定经历了 pending 回调，也不单独证明中断来源、跨 Client 隔离或任务绑定安全。

用 `--gles-compute <匹配的ARM64二进制>` 打入独立 initrd，同时传 `--glmark-env`；init 将冻结探针绑定到只读 workload root 中。
私有 runner 的 compute 路径执行串口命令 `compute-eventfd`，只有所有 Client 输出精确完成标记和计算校验才记录 PASS。
打包检查拒绝缺少探针、旧 init、旧探针或错误架构；这是版本检查，不是远程证明。
该模式禁止与 `--perf` 组合，完整720p评分路径不启用它。实机扩展仍须遵守先达到1000分的门槛。
`scripts/check/check-gpu-completion-eventfd.py` 使用真实 Linux eventfd 和 DRM/EGL 替身检查探针，不计作 GPU 执行证据。

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

正式性能计分保持诊断关闭：不传`--rpc-stats`、`--notify-trace`和`--completion-trace`，
三者均默认关闭，`--performance`不会自动启用它们。`--completion-trace`会连带启用通知采样；
开启诊断的成绩应单独标记，不能直接当作关闭诊断后的运行性能。
含新提交计时扩展的Proxy内核在`--rpc-stats`下额外输出`PANTHOR_PROXY_SUBMIT_PHASES`；
单Client结果可用`scripts/analysis/analyze-submit-phases.py --run <回收目录> --output <新JSON>`分析。
该统计区分PLAN_REGISTER与PLAN_EXEC尝试、原生提交和附加完成观察；完整1080p测量及边界见[提交路径分解](../../../docs/shared/GPU_SUBMIT_PHASES_20261022.md)。
`--transfer-capture`是独立的实验优化开关，不属于计时诊断，也不由`--performance`自动启用。

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

通知延迟诊断使用`--notify-trace`（默认关闭），要求REGISTER能力位64及匹配的Guest/initrd。采样窗口为物理计数器每100ms中的前2ms，输出`notify-realm-N.log`；配套Host探针、时钟校验及证据边界见[通知延迟拆分](../../../docs/shared/GPU_NOTIFICATION_LATENCY_20261022.md)。`notify-timed CHANNEL`仍执行原NOTIFY授权和事件语义，但成功返回三个RMM时间戳及打包的计数频率/Host提示，不能当作普通NOTIFY的sequence结果解析。

完成回传诊断使用`--completion-trace`（默认关闭，自动启用notify trace），要求匹配的Client/Proxy能力位`1<<9`。在完整原生fence回调发布精确cookie后，记录Client本地检查或RPC成功分支首次采用该cookie的物理计数器时间；输出kind3 trace及`completion-stats-realm-N.log`，当前Guest trace容量65536条。`analyze-gpu-completion-trace.py --run <已校验的单Client回收目录> --output <新JSON> --require-rpc-paths`校验时钟及实际RPC回退样本；注册时已完成、未观察cookie及无对应证明的RPC分别报告。测量边界和已验证输入见[完成回传报告](../../../docs/shared/GPU_COMPLETION_LATENCY_20261022.md)，时间戳不承担完成授权。

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

## RMM 私有 BO/PT：当前状态与开发探针

**当前实现与验收状态以[当前基线](../../../docs/shared/CURRENT_BASELINE.md)和[实施记录末节](../../../docs/shared/GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md)为准。** 正常私有 DRM 提交、RMM 控制的真实 GPU 执行、可信完成和缓存归还/退休已经接线；已有单 Client 计算和完整 720p 运行证据，性能门槛与多 Client/实体攻击验收仍未完成，完整执行能力位继续清零。该能力位清零表示整体验收未开放，不能据此推断实验执行路径尚未接通，也不能把成功运行当作硬件隔离证明。当前 ABI 2、RPC ABI 4；能力掩码以实际版本查询为准，当前候选为 2147483643。

READY/RETURN 每次元数据检查上限已为 16384 项，昂贵的物理页缓存维护仍限 512 页，两种预算独立。NC/驻留数据仍检查真实 PTE、归属、生命周期和缓存租约；不是省去授权检查。硬件配置、真实完成、停止/禁用及安全回收条件另见当前实施记录。

下文保留早期操作 17–44 的接口说明和分阶段开发证据。其中“未接普通提交”“仅模型验证”“512 个表项”等描述属于对应开发阶段，不代表当前状态。操作语义和单项探针是否已在板端执行须按具体证据区分；正常工作负载通过不自动覆盖所有诊断探针。此次仅整理文档，未改运行代码、无新增性能测量。

### 历史开发步骤与接口说明

`scripts/build/build-realm-xshm.sh` 同时生成静态 `realm-gpu-private`；可用
`REALM_XSHM_BUILD_OUT` 将产物放入本次构建目录。initrd 打包器通过
`--gpu-private <二进制>` 显式加入工具，`--tools-dir` 选择配套 init/realm-xshm。
`--gpu-firmware GPU-SFTP/panthor_fw/mali_csffw.bin`加入RMM固定允许的固件，打包时校验长度和SHA。

- `realm-gpu-private version`：查询独立 GPU 私有接口 ABI/能力。当前 ABI 2、能力 268435451，包含私有映射、组/任务、可信完成及前缀发布；完整 Client 任务执行能力位保持清零。
- `realm-gpu-private mode-check client|proxy`：检查实际只读驱动参数已启用私有模式；不是仅核对可能被旧内核忽略的cmdline，也不是硬件隔离证明。
- `realm-gpu-private selftest CHANNEL [PAGES]`：特权分配器 → RSI → RMM 建表/撤销，默认 513 页；CHANNEL 必须是本 Realm 到实际 GPU service 的活动通道。
- `realm-gpu-private drm-selftest [DEVICE [PAGES]]`：默认 `/dev/dri/renderD128`、513 页，经过正常 BO_CREATE/mmap/VM_BIND 和 Proxy 元数据导入；测试局部重映射、CPU 映射边界及 GEM/VMA 生命周期。
- `realm-gpu-private firmware-snapshot FILE`：在已交权的实际 service Realm 执行，按页上传、核验并封存 RMM 私有固件快照。仅接受当前固定的 `panthor_fw/mali_csffw.bin`（274432 字节、SHA-256 `43c3c36b914c031d88ae152fd89019d8f99ad41d9879fb5ab7496ed13f7b378b`），拒绝篡改、乱序及封存后覆盖；不安装 MCU 页表、不启动固件或任务。工具和 RMM 接口已构建，Realm 内尚未执行。

DRM 探针要求 Client 启动时设置 `panthor_client.rmm_private_data=1`，并核对只读
sysfs 参数确实启用，防止共享旧路径冒充私有路径成功。两端内核与 RMM 必须配套；
当前 RPC ABI 4 保留 8 操作/8 同步与 472 字节 VM_BIND 请求。私有 MAP 必须携带 Client 经 RSI
取得的一次性精确授权；异步绑定在原生依赖就绪后消费授权，成功接纳不等于绑定完成。
私有 BO/context 登记还要求 GPU service 实际完成控制交权，原始 MMIO 仍开放时返回 STATE。
交权诊断入口在实际 service Realm 执行 `realm-gpu-private call 17 0`，须先停止并解绑旧 GPU
驱动；该操作撤销原始 MMIO 并验证复位，不能在正常工作负载期间调用。交权后可用服务调用
`call 8 CONTEXT AS_SLOT` 安装 RMM 根，AS_SLOT 为非零硬件槽且 MCU/GPU 必须停止。
二者都没有 GPU 执行能力。原生驱动在交权后的完整服务接口尚未接通，所以 DRM 探针仍待运行。
封存固定固件后，服务可执行 `call 22 0` 创建 RMM 私有运行页和 MCU 页表，再执行
`firmware-control BYTES` 可在此时捐赠并绑定最多 16 MiB 的受保护内部控制页（如 `firmware-control 16777216`），再执行
`call 23 0` 安装 AS0、上电 L2 并启动 MCU，检查实际启动标志、状态和初始化接口。
启动还校验全部 group/stream 的完整范围、缓存行及交叉别名；属性在 RMM 内缓存。
服务可用 `call 25 0 0` 查询版本/features/group 数/instrumentation features，
`call 25 0 1` 查询每 group 的 stream 数/features/普通及保护模式 suspend 字节数；不返回地址。
`call 24 0` 使用硬件 shader mask 和固定计时器配置受保护 global input，
由 RMM 写 global doorbell 并有界检查真实 ACK，成功进入状态 7 CONFIGURED。
不会启用 Client 队列、计数器或中断；写入后的失败保留 backing，要求可信复位。
没有向 Proxy 返回根或页面地址；安装/启动失败会隔离并保留运行页，直到可信整设备复位。
此启动路径仅有本地寄存器模型和真实页表集成证据，未在 Realm/GPU 上执行；不发布 Client 队列。
私有模式不会在能力不足时降级。现阶段已有受保护内部控制 backing，但逐 Client 的 GPU 控制资源及 ring 分配/建表已接入，已接停止态硬件队列准备，诊断任务启动/停止与归还/退休已接入，正常 DRM 提交仍未接入，
私有上下文拒绝执行 GPU 工作负载。此模式尚不能用于 glmark 或宣称抵御恶意 Proxy。

控制机检查为 `bash scripts/check/check-rmm-gpu-private.sh`：覆盖身份/范围/权限、真实
硬件描述符、表池耗尽回滚、服务映射、精确授权/防重放/取消/待处理引用、旧句柄及可信设备撤销后的状态；不替代实体测试。
同一检查现也执行真实固定固件的 SHA-256、区段解析、私有副本、上传与封存状态负例；不将快照核验等同于固件可信启动。
新增运行页内容/清零、真实 MCU PTE 权限、初始化接口范围、失败保留/可信复位退休检查；`check-dma-guard.sh` 同时执行实际固件后端的寄存器模型集成。
该集成现已覆盖真实固定镜像到 global 配置/模型 ACK 的路径；核心另覆盖元数据别名/溢出、缓存行隔离、旧 ACK 翻转、失败和计数器回绕。模型 MCU 属性是测试构造值，不是实体能力测量。
两个 Guest 探针目前仅编译，`GPU_PRIVATE_EXECUTION`、CPU Realm 隔离和实际 GPC
保留 NOT_RUN。完整范围、构建证据和未完成项见
[RMM 私有 BO/PT 实施记录](../../../docs/shared/GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md)。

受保护控制内存使用独立的 `REALM_GPU_CONTROL_ALLOC` fd：成功分配已撤销原 CPU
Stage-2 映射并清零，mmap 必须返回 EACCES；fd 没有 read/write 接口。绑定只返回容量和页数，
不返回页表或数据地址，不能在 MCU 启动后绑定。关闭 fd 后固件持有的页仍被保留；
只有可信整设备 RESET/RELEASE 后才可清零并恢复原 CPU 映射，复位本身不会恢复权限。
分批清理或恢复失败继续保留 backing，可在后续诊断操作中有界重试。RPC 共享控制页
不使用此机制；arena 已支持按实际 Client/context 预留 suspend 和队列 I/O 页，并已分配/映射受保护 ring，已可通过操作 38 配置停止态硬件队列，诊断 START/QUIESCE/RETURN/RETIRE 已接入，普通 DRM 任务尚未接通。
工具和实际 RTT/平台源代码模型已验证，Realm ioctl 和实体 GPU 均未运行。

Client 可用 `realm-gpu-private group-selftest CHANNEL [STREAMS]`（默认 1）验证操作 30–37 的 Client 路径；
前提是 service 完成交权、固件封存/prepare、控制 arena 绑定、boot 和 configure。
CREATE 由 Client 自己通过 RSI 授权，绑定真实 context；每 Client 跨 context 最多 8 组，
全局最多 32 组。服务只能通过已认证的 peer channel 查询元数据，不能返回地址或替 Client
销毁组。创建时清零失败会返回隔离清理句柄；销毁 status=4 时必须继续有界重试，
不能提前释放 context 或复用资源。组销毁只适用于尚未发布到硬件的预留内存。
此探针验证 context 引用、通道与旧句柄拒绝，尚未运行 Realm ioctl；正常 DRM 组创建/
销毁和 ring 配置已经接入；已接停止态 AS/CSG/CS 与 ring 准备，诊断可信 START 已接，诊断可信完成已有模型，正常提交/可信 fence 仍未接入，完整执行能力位保持清零。

组接线补充：私有模式正常 DRM GROUP_CREATE/DESTROY 已接 Client 托管的 RMM 预留与 Proxy 元数据；RPC ABI 4。服务侧 `call 33 GROUP CHANNEL CONTEXT STREAMS` 只校验实际通道 peer、精确 context/stream 数及可用组状态，不返回地址或授予执行。Client 无权调用服务侧校验，group-selftest 包含该拒绝检查。私有 GROUP_SUBMIT、计划及组状态查询仍不进入原生执行路径；停止态硬件队列准备和诊断 START 已实现，诊断可信完成已有模型，正常提交及可信 fence 尚未接通。

控制机可运行 `python3 scripts/check/check-gpu-group-bridge.py` 检查真实驱动函数的分支/生命周期；它使用内核和 RSI 测试替身，不能替代 Realm ioctl 或实体 GPU 测试。

操作 34 `GROUP_CONFIGURE` 由 Client 授权不可变队列大小/优先级，私有复制参数后分配 CPU 隐藏的 ring/completion 并建立软件 PTE。正常 DRM 组创建已调用；Proxy 导入逐队列用操作 33 核对。公共 MAP/AUTH/UNMAP 无法修改顶部保留的 16 MiB GPU VA。清零/建表部分失败保持隔离和映射引用，退休先拆全部 alias 再清零；后续操作 38 可配置停止态硬件。

操作 35 `call 35 GROUP CHANNEL QUEUE STREAM_GPU_VA STREAM_BYTES LATEST_FLUSH` 由实际 Client 暂存任务。RMM 检查全部已映射的私有命令流页（非空、8 字节对齐、最多 512 页），冻结 context 映射并生成私有原生 CALL/sync wrapper，返回 token/queue；不返回地址。操作 36 `call 36 TOKEN` 由 Client 取消预启动记录，活跃或隔离 context 保留；操作 37 `call 37 TOKEN CHANNEL CONTEXT GROUP` 仅服务可校验精确归属。全局最多 128 个、每 Client 32 个，旧 token 不复用；有任务时不能销毁组。`group-selftest` 已增加实际私有分配/跨页暂存、映射冻结、Client 冒充服务拒绝、取消与旧 token 检查，尚未在 Realm 执行。

TASK_STAGE 只建立 RMM 内记录；服务可执行操作 38 `call 38 TOKEN CHANNEL CONTEXT GROUP`，由 RMM 选择 AS/CSG、写入受保护 ring 和保持 STOP/TERMINATE 的 CS/CSG 输入，返回状态 4 PREPARED/queue。首次根安装只接受空闲 AS；同 token 重试只核对非零根/属性，不重写 ring/描述符或门铃。准备开始后的部分失败保留资源，要求可信整设备复位。只支持已固定后端/单 tiler0 拓扑，接口地址取启动时的可信缓存；不返回根、槽位或地址。启动前缓存交接已接下述操作 39；尚未接普通 DRM GROUP_SUBMIT、依赖接线或本地可信 fence；诊断可信完成见操作 44；中止后缓存归还与退休见操作 42/43；诊断硬件 START 已接下述操作 40；completion 页面也不能单独证明任务完成或授权回收。执行能力位仍为零，不能用于私有 glmark。当前软件检查与构建不代表真实 Realm/GPU 运行通过。

操作 39 `call 39 TOKEN CHANNEL` 只能由原 Client 在 TASK_PREPARE 后调用，表示其依赖/CPU 写入已结束。RMM 用冻结的真实 GPUVM 表归属/对象标签，分批 clean+invalidate 所有普通数据页到 PoC；每次最多检查 512 个表项，内部控制页和其他 context 不进入数据回调。返回 `[ready(0/1), queue, 累计同步数据页数, 0]`，status=4 时重复同一调用，游标不能由调用者指定；ready=1 只表示启动前同步结束。Proxy/其他 Client 不能冒充就绪；重复 READY 不重新同步数据。BO 已交给另一个 context 时拒绝，部分失败保持隔离和 backing，直到可信整设备复位。Client 须在 GPU 使用期间停止相关 CPU 写入；正常 DRM 依赖调用时机和可信 fence 尚未接入；诊断可信完成见操作 44；中止后归还/退休和复用见操作 42/43。READY 不启动任务，不证明完成，不允许提前回收。

操作 40 `call 40 TOKEN CHANNEL CONTEXT GROUP` 仅由实际隔离服务调用，要求精确 token 已 PREPARE 且由原 Client 完整 READY。RMM 核对真实 AS 根和固件状态，按 CS→CSG→global 顺序发布受保护请求、写固定 MMIO 门铃，再检查实际父/子门铃、CSG 完整状态/endpoint 和 CS START ACK。返回 `[5 STARTED, queue, 0, 0]` 只表示启动接纳，不是完成证明。第一次发布前记录尝试；精确重试只核验，不重发门铃、不重写 ring 或重复缓存同步；超时/故障保留任务和 backing，须可信复位。20 个启动场景已通过实际平台源代码的寄存器模型；尚未部署或执行真实 GPU 任务，正常 DRM GROUP_SUBMIT 和可信 fence 仍未接入；诊断可信完成见操作 44；诊断缓存归还见操作 42。

操作 41 `call 41 TOKEN CHANNEL CONTEXT GROUP` 仅由实际隔离服务调用，对精确已 STARTED 的任务执行 CS STOP/CSG TERMINATE，核对实际 ACK 后由 RMM FLUSH_MEM、清零 Client AS 根/属性、写 Mali UNMAPPED=1 并完成 UPDATE。返回 `[6 QUIESCED, queue, 0, 0]` 表示中止/停止，不是任务成功或可回收通知；任务、映射、缓存交接及 backing 引用仍保留，仅 QUIESCE 不归还缓存或退休任务，须继续执行操作 42/43。精确重试只核验、不重发；部分失败须可信复位。每 context 当前只允许一个已发布组，不同 Client/context 可并行；第二组在 PREPARE 前被拒绝。15 个新增场景及实际 MMIO 后端模型通过，包含伪造 completion 计数不能替代 STOP ACK、单独停止不影响另一 Client、FLUSH/UPDATE 失败保持引用。尚未在 Realm/GPU 执行。

操作 42 `call 42 TOKEN CHANNEL` 仅由原 Client 在成功 QUIESCE 后调用。每批前后核验真实 STOP ACK、固件配置和已禁用 AS，由 RMM 临时私有映射失效数据页 CPU 缓存，最多检查 512 个表项；跳过内部控制和其他 context。返回 `[returned(0/1), queue, 累计数据页数, 0]`，status=4 时继续同一调用，完整成功前不得访问数据。精确重试重新检查硬件但不再同步数据；成功不证明任务成功，不释放任务或缓存租约。

操作 43 `call 43 TOKEN CHANNEL` 仅由原 Client 在完整 RETURN 后调用。RMM 重新核验停止/禁用状态，分批清零该组 suspend/I/O/ring/completion，移除旧 CS/CSG 地址，再解除精确任务、缓存和 AS/CSG 槽位租约。返回 `[retired(0/1), queue, 累计清零页数, 0]`；status=4 时继续，成功使旧 token 失效，重复旧 token 返回拒绝。BO 映射和其他暂存任务引用保留；组可再次使用或显式销毁。部分失败保留引用，须可信复位。18 个新增实际平台源模型场景通过；它也可接在操作 44 成功之后；**退休本身不证明成功执行，也不是普通 DRM 提交路径，实体 GPU/缓存行为尚未验证。**

操作 44 `call 44 TOKEN CHANNEL` 只能由原 Client 查询已 STARTED 的精确任务。RMM 主动请求 fresh STATUS_UPDATE，核验父/CSG ACK，从受保护 arena 读取 ring 进度、scoreboard、阻塞与错误及精确同步记录；计数本身不是完成证明。未完成返回 status=4、`[0, queue, 0, 0]`，可继续查询；已有待 ACK 请求时不重复发布。发现完成后必须先 STOP/TERMINATE、FLUSH 并禁用 Client AS，重新核验后才返回 `[1, queue, 0, 0]`。显式中止不能升级为成功；成功重试只核验硬件。随后仍须完整执行 42 RETURN 和 43 RETIRE，才能访问数据和复用资源。28 个新增实际平台源模型场景 66–93 通过；正常 DRM fence、Realm/GPU 执行尚未完成。

私有 DRM 同步对象现由 Client 本地 DRM 核心管理，WAIT/QUERY、sync_file、时间线、CPU SIGNAL/RESET 不调用 Proxy 同步 RPC，也不使用共享完成页。`drm-selftest` 已加入二进制/时间线/旧版 WAIT、信号/重置/查询/转换与导出快照探针，仅构建未运行。私有正常 GROUP_SUBMIT 仍返回 EOPNOTSUPP。私有同步/异步 VM_BIND 已共用 Client 有序 worker：本地依赖满足后才申请 MAP 授权，以不含本地 syncobj 的单操作同步 RPC 执行，再调用操作 45 MAPPING_CHECK 检查实际 PTE 和跨批 epoch；只有核验成功才成功完成本地 fence。每 file 限 128 个待处理批次，依赖/核验截止各 60 秒；时间线当前点错误会阻止授权。操作 45 只证明映射快照，不是 GPU 完成或映射租约。操作 46 阶段的总能力 33554427，ABI 2/RPC 4，执行位仍清零。控制机 25 项实际驱动函数替身测试通过；drm-selftest 已加入 MAP→UNMAP→SYNC_ONLY 异步依赖和真实 sync_file 状态检查，仅构建未运行。不能用旧共享路径代替私有执行。


受限原生服务候选：Proxy 启动参数 `panthor.rmm_service=1` 在 probe 期间完成 claim、静态能力快照和 RMM MMIO 交权；随后仅保留私有对象/GPUVA bridge，不启动原生 IRQ/固件/任务调度，不接受本地 DRM open 或普通 VM/共享 BO。初始化后内核 I/O 映射也已释放，不需要解绑才能交权。Proxy 中新增 `realm-gpu-private service-bootstrap /path/to/mali_csffw.bin` 串联可信固件准备、16 MiB arena 捐赠、MCU 启动和配置；部分失败保持现场，不能自动复位重启。Client 再以私有模式执行 drm-selftest。26 个实际服务初始化/MMU/查询函数替身场景通过；两端内核和工具已构建，Linux/Realm/真实 GPU 未运行，runner 尚未自动串联，普通私有 GROUP_SUBMIT/任务 fence/私有 tiler heap 未完成。

多队列批次候选：操作 46 `TASK_STAGE_BATCH` 接收原 Client 的 1–6 个私有描述快照，支持重复队列和 fence-only；总计最多检查 512 个命令页，只持有一份 context/cache 租约。RMM 准备同队列有序 wrapper，启动/停止核验所有参与 CS，完成检查要求每条参与队列进度、最终序号与错误正确，并在 STOP/禁用 AS 后再次检查。能力位 16777216，总能力 33554427，执行位仍清零。18 个实际平台源模型场景通过，不是 GPU 命令执行证据。`group-selftest CHANNEL [STREAMS]` 已包含六成员批次、坏成员拒绝与取消探针，仅编译未运行；普通私有 GROUP_SUBMIT、任务 fence、私有 tiler heap、runner 和实体 GPU 验收仍未完成。

Client 内核任务与 Proxy 控制桥接：`realm_gpu_task_stage/call/put` 托管批次 token，诊断 ioctl 不得修改托管任务；Proxy 新会话特性 `RMM_TASK_CONTROL` 只允许 PREPARE/START/QUIESCE，使用已有通道/VM/组元数据调用 RMM，不接受地址/根/槽位。完成、缓存归还和退休仍由原 Client 发起；准备后放弃不会自动释放。`python3 scripts/check/check-gpu-task-bridge.py` 已覆盖实际 API、Proxy handler 与诊断 ioctl 的 54 个替身场景，非 Linux/Realm/GPU 实测；也已加入 `check-rmm-gpu-private.sh`。普通私有 GROUP_SUBMIT 仍 EOPNOTSUPP，需先解决每 job 依赖/信号和跨提交进度，不能将整批统一完成代替 DRM 语义。

初始私有 tiler heap 候选：私有 DRM TILER_HEAP_CREATE/DESTROY 改为 Client 本地 BO 初始化/VA 预留，再由 RMM 分批建立 RW/XN/WB PTE；不发 Proxy heap RPC，不接受其提供的 heap 地址。VM 创建固定用户/内核 VA 边界，普通 VM_BIND 不能越界。失败/活跃任务保持 backing、VA 和回收游标，RMM 确认 UNMAP/BO_DESTROY 或可信撤销后才能释放。单初始 BO（含一页 context）最多512 MiB，每 context 最多128个 heap。`python3 scripts/check/check-gpu-private-heap.py` 的52个实际 Client/内核函数与真实 RMM 核心联合场景通过，仍使用平台/锁/RSI/分配器替身；bind 场景增至27。`drm-selftest` 已增加8 MiB初始chunk的正常heap创建/销毁、用户VA拒绝、重复销毁及零chunk负例，仅编译未运行。**动态固件 OOM 扩容与 max_chunks/target_in_flight 的增长策略尚未接通，正常私有提交/fence/runner/GPU验收也未完成；初始heap成功不是GPU执行证明。**


初始 heap 回收修正：新增操作 **47 UNMAP_BO**（能力位33554432，该阶段总能力67108859，ABI2/RPC4、完整执行位清零）。RMM在同一策略锁内核对实际BO/PTE和预期页偏移，仅移除匹配叶子；空页和其他BO的映射保留，匹配BO但偏移不符或页表损坏时整批拒绝。用于失败建表的回滚与正常heap销毁，防止按VA范围误删建表前已有的映射。原授权不因此取消：未消费的授权及后续映射继续持有BO/context引用，实际销毁前不能释放页面。Client私有模式握手要求此能力，普通和诊断入口不能借新操作改写活跃heap预留。联合测试增至75个，含旧授权在回收前/后被服务消费及同BO残留授权；旧回收函数在新冲突场景失败。控制机联合测试、完整私有/DMA/共享回归及两端内核构建通过；真实selftest新增错偏移拒绝、幂等精确撤销/重建探针，工具及initrd已重建，Realm/GPU运行仍NOT_RUN。无新增性能测量。
## 私有任务逐成员执行进度（未部署）

新增操作 **48 TASK_PROGRESS**，能力位67108864、当前总能力134217723；ABI2/RPC4不变，完整执行位清零。输入为原Client的token和认证channel，SUCCESS返回`[成员位图, 成员数, 队列位图, 0]`；位i对应原暂存数组成员i。同队列按各自ordinal核对受保护sequence与真实消费前缀，全部队列、fresh STATUS ACK和根配置通过后才发布；进度倒退会隔离组。无fresh观察时INCOMPLETE返回零成员位图。

COMPLETE复用同一观察器，仍保留全队列idle/error、STOP/排空/AS禁用和停机后复查。PROGRESS全满位图不等于COMPLETE、CPU RETURN、RETIRE或DRM fence成功。Client typed对象检查原成员数、队列集合、位图范围和保留字段；通用/诊断入口不能对托管token代执行有状态观察。Proxy RPC仍只允许PREPARE/START/QUIESCE。

平台模型新增18个进度场景（多队列模型共36个），任务接口由54增至64个，heap75、bind27、service26及既有回归保留。group-selftest增加未启动/已取消任务的进度拒绝探针，仅构建打包未在Realm运行。正常私有GROUP_SUBMIT、依赖就绪后的逐成员发布、跨提交ring追加、逐job fence/缓存交接、动态heap与实机验收仍未完成。

## 私有任务逐队列前缀发布（未部署）

新增操作49 TASK_PUBLISH（能力134217728，当前总能力268435451，ABI2/RPC4，完整执行位清零）。TASK_STAGE_BATCH的args[3]可设TASK_DEFERRED=1；Client typed暂存固定使用该标志，PREPARE生成完整wrapper但保持INSERT为零。原Client完成CPU数据准备/READY后，按设备依赖就绪情况发布累积成员位图；各队列必须为前缀，允许不同队列独立推进。Proxy不能代发布，START空队列也不会使隐藏成员执行。标志0仅保留既有诊断整批授权。

RMM在写入前核对所有旧INSERT和真实根，运行中按固定子/父门铃通知并检查ACK；精确重试不重写/通知，部分写入和不确定ACK隔离并保留引用。PROGRESS不得超过已发布前缀；COMPLETE仍要求全部原成员结束。发布成功不是fence或CPU RETURN。typed回复严格检查，诊断入口禁止修改内核托管token。

平台模型新增18个发布场景（多队列模型54个，其中进度18个），任务桥74个，保留heap75/bind27/service26。group-selftest新增未准备/未READY发布拒绝，并使用DEFERRED暂存；仅构建未运行。逐job依赖调度、CPU可读fence/缓存归还、跨提交ring追加、动态heap和实体GPU验收仍未完成。

## 正常私有提交与就绪切片（未部署）

`GROUP_SUBMIT`在私有模式下已转至Client本地planner/独立GPU worker。按数组顺序处理batch内binary/timeline信号和等待，同队列跨IOCTL保持FIFO；等待中的队列/Group不阻塞后续就绪工作。同Group最多六个独立就绪队列头共用一个RMM token，依次PREPARE→READY→PUBLISH→START→COMPLETE→RETURN→RETIRE。只有最后三项全部可信成功，才signal各job成功fence；Proxy响应、PROGRESS、完成cookie均不是依据。启动响应丢失不重放，异常保留RMM引用并停止该file后续提交。

`python3 scripts/check/check-gpu-private-submit.py`：58个实际Client函数场景通过，已接完整私有检查入口。kernel/DRM/锁/RSI/硬件为替身，不证明Linux并发或真实GPU。新增`realm-gpu-private drm-submit-selftest [DEVICE]`，要求私有Client及已配置的可信服务，通过正常IOCTL检查两队列、跨提交依赖和三个精确成功sync_file；零长度用户流仍需执行受保护wrapper。工具和initrd仅构建，**Realm运行NOT_RUN；不是shader计算或隔离攻击验收**。

每片仍完整交接整个GPUVM，不允许新批次在活跃context中追加；完整执行能力位保持清零。原生VM_BIND/BO reservation隐式同步兼容尚未完整接入，映射与活跃lease并发可能返回EBUSY；正常Mesa兼容、动态heap、runner、死亡Realm回收及真实GPU/缓存/性能验收仍待完成。未部署、无新增性能测量。

## 映射与执行互斥（未部署）

原生Panthor使用显式syncobj依赖，VM/BO reservation中的BOOKKEEP仅用于生命周期记账；不应将所有排队GPU任务自动变为VM_BIND的依赖。本阶段对前述待办作此修正，并补齐整GPUVM租约下的实际执行互斥。

私有VM_BIND执行MAP/UNMAP前、初始heap创建/销毁前，取得同一`private_gpu_lock`保护：同VM存在已选中/运行任务时，释放锁等待其精确job fence，并在重获锁后重新核对run/失败状态；仅在可信COMPLETE、完整RETURN和RETIRE后进入映射临界区。栈上等待票据让同VM新片不能抢先，其他VM可继续；尚未选中的排队任务不会阻塞本次映射，避免“任务等bind，bind又等任务”的伪依赖。锁覆盖Client授权、Proxy RPC、剩余grant取消和真实PTE检查。RMM仍独立验证身份、映射冻结及引用，本地互斥不是授权证明。SYNC_ONLY不修改页表，不取得该锁；同步VM_BIND拒绝携带显式sync对象，与原生接口保持一致。

`check-gpu-private-submit.py`增至76项（含实际heap IOCTL wrapper），`check-gpu-private-bind.py`增至32项，完整私有检查及两端Image通过。旧picker替换进当前真实源码夹具后，在“同VM不能抢先、另一VM可继续”用例预期失败，证据保留。锁/调度/RSI/硬件为替身，不证明真实并发或GPU。ABI2/RPC4、能力268435451及完整执行位清零不变；工具/initrd/RMM/平台源码未改，按SHA复核上一阶段证据。运行中跨批追加、动态heap、runner、死亡Realm回收和真实GPU/缓存/隔离/720p验收仍未完成；未部署、无新增性能测量。

### 私有启动入口（源码已接入，未部署）

统一控制机入口和冻结runner新增`--private-gpu`。Proxy使用`panthor.rmm_service=1`，Client使用`panthor_client.rmm_private_data=1`；PID1通过`gpu-private ...`执行静态工具。所有Realm先检查实际只读参数，Proxy再执行`service-bootstrap /mali_csffw.bin`；只有RMM确认配置成功后才建立控制通道和DRM会话。参数、固件、初始化或私有探针失败会使运行失败，不尝试共享数据回退或重置后重试。

私有模式默认使用2049页、约8MiB的每Client共享**控制池**；业务BO仍由Client分散分配。内存计划单独保留Client普通内存预算，Proxy另计受保护arena；准入预算不是硬保留或任意应用可装入的保证。旧共享池/CMA性能配置、远端cookie跟踪和旧共享BO故障探针不能混入私有模式。

打包完整720p开发候选的命令如下；`initrd.cpio`必须包含当前工具、固定固件和工作负载脚本：

```bash
REALM_XSHM_BUILD_OUT=build/rmm-client-bo-20261030/runner-tools \
  bash scripts/build/build-realm-xshm.sh
python3 scripts/build/build-realm-xshm-initrd.py \
  --tools-dir build/rmm-client-bo-20261030/runner-tools \
  --gpu-private build/rmm-client-bo-20261030/runner-tools/realm-gpu-private \
  --gpu-firmware GPU-SFTP/panthor_fw/mali_csffw.bin \
  --glmark-env GPU-SFTP/tests/realm-xshm/glmark.env \
  --performance-suite GPU-SFTP/tests/realm-xshm/performance-suite.sh \
  --output build/rmm-client-bo-20261030/runner-tools/initrd.cpio
```

glmark不再要求携带无关的ioctl计时程序；`ioctl` profile仍需`--ioctl-perf`。ML算子profile还需通过`--gles-ml`打包配套AArch64二进制。控制机在任何上传前核对newc、工具架构/权限、固件和所选工作负载依赖，旧init或旧工具也会被拒绝。

已生成冻结开发包`build/rmm-client-bo-20261030/private-runner-candidate/`，含两端Image、完整720p用initrd、runner和四文件SHA清单。**没有部署；需匹配的候选RMM，不能直接继承板端旧固件或旧1405分结果。** 后续硬件首轮计划通过lab租约执行`--private-gpu --workload glmark --performance --benchmark-only --suite --profiles glmark-720 --clients 1`；保留完整33场景、正确性/内核健康/退出检查，并要求分数至少1000，再扩展API、计算和多Client。这里列出的是计划，不是已执行命令。

`python3 scripts/check/check-gpu-private-runner.py`：31项离线检查，包含实际CLI、runner函数、实际打包器/newc输入检查，以及真实C模式检查函数的8个文件I/O替身场景；已加入完整私有检查。串口、Realm和工作负载均为替身。非benchmark私有流程串联`drm-selftest`、`drm-submit-selftest`及所选计算，benchmark-only只执行所选完整工作负载。

控制池解绑记录与GPU/arena退休明确分开，后者仍为`NOT_VERIFIED`。死亡Realm/arena回收、动态tiler增长、跨批活跃追加、真实Linux并发/缓存/攻击负例及实际720p验收仍未完成。未登录硬件、未部署、无新增性能测量，完整执行能力位保持清零。
