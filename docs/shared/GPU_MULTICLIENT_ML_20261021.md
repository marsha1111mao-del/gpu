# 多 Client ML / NCNN 测试（2026-10-21）

**后续修复完成（2026-10-22）：** [未完成项修复与验证](GPU_ML_COMPLETION_20261022.md)。四Client七项算子及三/四Client ResNet50九条均已独立复测通过，退出、健康、租约归零和证据校验通过。[当前结果表](GPU_MULTICLIENT_ML_RESULTS_20261021.md)保留原31条有效结果，补入九条新结果，共40条；并非新组合重测全部40条。本文下述31条有效和九条失败/无效/未执行，是2026-10-21原批次的历史状态；原始证据继续保留。

原批次覆盖10项负载×1–4 Client，共40条：**31条有效性能、4条整轮GPU出错导致无效、1条无公共窗口、2条GPU提交失败、2条内存准入拒绝未执行**。一至三Client的九项常规负载、四Client的MobileNet-v2/v3、单/双Client的ResNet50均有通过且完成健康/回收检查的运行。当时不能宣称四Client ML全部通过。

原批次四Client Attention-256/320在正常负载中出现GPU job timeout及Mesa提交错误，当时未修复；其整轮其他耗时也未采信。ResNet50三/四Client在启动前因内存不足拒绝。原失败、无效和未执行项在本文及原实验目录保留，Native使用明确标注的历史单进程参考；最新结果表已用独立验收的九条新数据补齐，当前配置、命令及限制见后续修复报告。

## 范围与条件

本轮验证七个 ML/Attention 算子和三个 NCNN 模型在 1–4 个 Client 下的行为及耗时。每个 Client 使用独立 Realm、授权池、GPUVM，通过同一可信 Proxy 访问 Mali-G610。所有 Client vCPU 共享 CPU2–3，Proxy vCPU 使用 CPU1，VMM I/O 使用 CPU0；因此结果包含 CPU 竞争，不代表纯 GPU 扩展效率。

Host 保持 `6.12.0-opencca-pmthor-opp3 #31`，RMM 保持 timer-v6 + 1 GiB GPU 页租约组合；Client/Proxy 内核沿用已验收 F，未修改 GPU 数据路径。GPU 请求 600 MHz，实测 594 MHz；未锁 CPU 恒定频率，禁用 Mesa shader cache。只读 rootfs、算子实现和 NCNN 用户态保持不变。

改动目的｜为已有 ML 负载增加多 Client 同步启动及结果收集｜对照 F 完整720p **1157** → 本轮 **未重测 glmark**｜分差及百分比：不适用｜仅测试 runner、dispatcher 和 workload 内存配置变化，不宣称提分｜最终保留输入及本轮 ML 命令、退出码、日志另列。

每个 profile 在全部 Client READY 后释放 GO；所有 Client 完成后才启动下一个 profile。最终选用六个独立ml profiles，每算子100次采样、5次预热，并检查 CPU reference；参数与原ml-all一致。Attention-320为10次采样、2次预热。NCNN 保留100 loops、2 threads、GPU0、224×224 输入和 panvk-direct 后端，使用随机输入/权重，只验证后端运行及性能，不代表模型准确率。

Native 为 `native-p42-comparison-20261018` 的历史单进程数据，Host #7，与本轮 #31 不是同期同配置对照。耗时越低越好，性能保留 = Native 耗时 / 各 Client 耗时均值 ×100%。不把不同算子合成总平均，不把各 Client 倒数之和当作共同时间窗实测吞吐。重叠率来自串口观测的完整 workload 窗口，包含初始化，不表示各算子每次迭代严格同步。

本轮是多个Client进程同时执行同一profile的场景测量；屏障位于进程入口，尚未移入用户态程序的编译/预热后计时区间。因此短算子的测量循环可能只部分重叠，三/四Client在固定两核CPU预算下也可能出现初始化错位和域间耗时不均。表格保留每个Client，不能用均值倒推满GPU稳态并发能力，也不能把某档均值较低解释为增加Client后GPU变快。长Attention负载同样只按本轮实际条件报告，不推广为调度公平性证明。

## 测试入口与证据

控制机实验目录为 `build/multiclient-ml-20261021/`。每轮经 `scripts/maintenance/lab-run.py` 获取 Pi/RK 独占锁，使用只读租约监视器，保存前后资源、Host/Guest 内核健康、逐 Client 日志及全部 Realm 退出码。collector 回收后逐文件核对 SHA-256；租约监视器检查最终 GPU/DMA 页引用均为0。

最终输入分为E/F两个冻结包：`build/multiclient-ml-20261021/candidate-e/`用于常规一/二Client及ResNet50，`candidate-f/`用于常规三/四Client。两包Client/Proxy内核与initrd逐字节相同，内核沿用1080p最终F；initrd只更新测试dispatcher。ML测试F的runner在某项未观测到公共窗口时记录`FAIL_NO_OVERLAP`并继续后续项，整轮仍为FAIL；计算、GPU或驱动错误仍终止测试。E/F的区别不属于GPU执行路径优化。

每包`hashes.json`记录输入SHA。共同Client内核为`31f31f15c148bba2194bb1ccc0335f6bdbd300729ca0278ed1431fa439420647`，Proxy为`f3c3f28e25617784d7d681fa6a1270b5561eaf82526e9ce41a97e9fd399103fc`，initrd为`d9e3500c8b4c012dacdba8e7c0bbfafd405ef78cc8b854e81f05a039487d1d8f`。F runner为`56fcf4800ad9c30f8ff0fe3caaf6a63fe184d87a953c098adad9a2637bbef45f`。`check-runner.py`的11个正反例覆盖双Client解析、单算子profile、完整条目、采样数、CPU后端误用、零耗时、映射/fence错误，以及无公共窗口仍保留测量失败；rc0，日志`build/multiclient-ml-20261021/parser-check.log`。软件检查不代替硬件测试。

`check-analysis.py`的7项验收检查通过、rc0，日志`build/multiclient-ml-20261021/analysis-check.log`：允许显式记录失败或整轮无效标签，同时拒绝错误profile、把成功标为GPU失败/无效、把GPU失败整轮当性能，以及重复场景。统计另检查完整Realm串口中无GPU job timeout；Host健康或程序rc0均不能替代GPU执行成功。

## 失败与待验证

| run-id | 结果 | 定位与处理 |
| --- | --- | --- |
| `ml-1c-192m-20261021-a` | FAIL / 外层rc1；ResNet50进程rc137、profile rc125 | Client普通内存192MiB、GPU池192MiB；加载ResNet50时Guest OOM，`benchncnn` anon-rss108852KiB。前面九项已输出耗时，但整轮不计PASS，不进入最终有效结果表。Host健康PASS、Realm退出0/0、GPU/DMA租约最终0；失败诊断串口超时及Client解绑响应异常一并保留。 |
| `ml-1c-192m-20261021-resnet-c` | FAIL / 外层rc1、profile rc125 | 普通内存320MiB消除本轮OOM，但192MiB GPU池耗尽，BO_CREATE ENOMEM、Vulkan/fence错误。程序rc0和raw均值5.00ms无效，不能入表。GPU租约峰值47912页/187.16MiB，最终GPU/DMA0、Host健康和退出0/0通过；失败诊断超时与Client解绑响应异常保留。 |
| `ml-1c-256m-20261021-resnet-d` | FAIL / 外层rc1、profile rc125；Host健康FAIL | 普通内存304MiB，无OOM；已有约187MiB映射后申请0x9800000/152MiB BO，256MiB池仍不足。BO/Vulkan/fence错误使raw耗时无效。退出0/0、GPU/DMA租约0不能抵消Host的Realm RTT回收WARNING；后续启动失败，需重启恢复。 |
| `ml-1c-384m-20261021-resnet-e` | FAIL / 外层rc1，未执行模型 | 上一失败后Proxy启动报Error init gpu mmio，Realm退出1/0，租约峰值0；不记录性能。随后受控重启，保留该失败及恢复前后证据。 |
| `ml-1c-128m-20261021-sync-g` | 配置错误后人为中止 / rc1，不计性能 | 实验矩阵默认列表误带ResNet50，发现后在ML阶段向本轮runner发SIGINT，未执行ResNet50；保留KeyboardInterrupt和串口诊断/解绑响应异常。Host健康PASS、退出0/0、GPU/DMA最终0、CPU/频率恢复通过。已修正实验矩阵默认列表并拒绝ResNet50与其他profiles混跑；最终sync-h显式列出九项profiles，实际命令已核验。 |
| `ml-3c-128m-20261021-sync-h` | 测量FAIL / rc1，中止于reduction | 三个程序计算/退出正常，但reduction串口观测无公共窗口（−25.60s），该项不能作并发性能；保留首四项原始结果，未执行后续五项。Host健康PASS、退出0/0/0/0、恢复及GPU/DMA租约0，回收SHA通过。后续F测试包保留无窗口失败并继续其他项，未放宽有效性判据。 |
| `ml-4c-128m-20261021-sync-i` | GPU提交FAIL / rc1，中止于Attention-320 | Proxy出现多次GPU job timeout，Client 1有六次`MESA: error: panfrost_batch_submit failed: 22`。其raw耗时及ML_CHECK=PASS不能抵消驱动错误；本轮全部耗时均不进入有效性能表，后续两个MobileNet未执行。Host健康PASS、退出0/0/0/0/0、CPU/频率恢复及GPU/DMA租约0；Guest诊断超时、pool-unbind响应异常和完整43文件SHA回收证据保留。后续sync-j单独测试其余八项，Attention-320在最终表保留失败，不宣称GPU超时已修复。 |
| `ml-4c-128m-20261021-sync-j` | GPU提交FAIL / rc1，中止于Attention-256 | Client 2有八次同类Mesa提交错误，Proxy仍出现GPU job timeout。先前GEMM/卷积/深度卷积/Softmax的程序输出及耗时不能让该整轮成为性能PASS；Reduction另有无公共窗口。全部耗时排除，两个MobileNet未执行。Host健康PASS、退出0/0/0/0/0、解绑/撤销、恢复及GPU/DMA租约0，40文件SHA回收通过。随后同版本软重启恢复，再单独测试两个MobileNet。Attention-256/320超时均保留为未修复问题。 |

上述各轮原始证据、OOM堆栈、逐Client日志、清理异常、命令和哈希保存在`build/multiclient-ml-20261021/runs/<run-id>/`，采集状态VERIFIED。后续成功不能抹去这些失败。

早期`ml-1c-128m-20261021-b`、`ml-2c-128m-20261021-b`整轮PASS/rc0并已核验回收，采用整套ml-all入口屏障。双Client softmax为37.393/106.525ms，说明算子阶段错位时会与对方Attention竞争；这两轮保留为整套混合负载证据，不用作最终逐算子同步表。原矩阵在双Client正常结束后停止，计划中的三/四Client该版本未执行，后续由逐算子同步矩阵覆盖。

九项常规负载使用128MiB池、192MiB普通内存。ResNet50最终E候选允许384MiB池、304MiB普通内存；Client RAM704MiB、CMA400MiB；Proxy RAM=384×N+208+32×N、CMA=384×N+16MiB。一/二/三/四Client总RAM为1328/2448/3568/4688MiB。三/四Client超出当前约3GiB Host可用内存，保留准入拒绝/NOT_RUN，没有模型耗时。384MiB池来自实测分配需求，未缩小模型或减少100次推理；对应实测及拒绝记录见最终运行表。

`ml-host-recovery-20261021-a`经lab-run的allow-rk-reboot模式获取Pi独占锁后，仅执行Host软重启，无刷写。退出0，确认boot ID已改变、同Host #31/pmthor、CPU0–1、GPU300MHz和Realm能力1。完整前后资源及新启动dmesg在`build/lab-runs/ml-host-recovery-20261021-a/`。恢复不算修复Realm回收问题，也不替代模型通过。恢复后重新运行ResNet50和最终逐算子矩阵，未完成项不记PASS。

`ml-host-recovery-20261021-b`在两轮四Client GPU超时并全部回收后，用相同受锁保护入口软重启，rc0；同Host/RMM/驱动、Realm能力1、CPU0–1和GPU300MHz恢复，未刷写。其后`ml-4c-128m-20261021-ncnn-k`只执行MobileNet-v2/v3；这两项与一至三Client来自不同启动周期，报告保留该条件差异。恢复没有证明四Client Attention或历史RTT WARNING已修复。

2026-10-21 Notion连接恢复，已将本地[结果表](GPU_MULTICLIENT_ML_RESULTS_20261021.md)的40条结果按既有表格格式追加至[多Client并行测试结果合集](https://app.notion.com/p/3ff659a3b8cc813bbab7c109be10ad21)的「ML / NCNN（2026-10-21）」区，并回读核对全部205个表格单元格。保留失败、无效和未执行标签，以及历史Native和并发测量条件说明；原glmark表格保留。此次发布未改运行代码，无新增性能测量。

2026-10-22九项补测已同步至同页「ML / NCNN（2026-10-22 补测完成）」区，当前表40条/205单元格回读与本地一致；原31条有效数据不变，九条失败/无效/未执行标签由新验收结果更新，原原因表保留并标记历史。glmark和内存对照区保持原文；发布证据见 `build/ml-completion-20261022/notion-publication.json`。此次仅同步文档，未改运行代码，无新增性能测量。

## 最终运行记录

| run-id | 条件 | 有效结果 | 验收 |
| --- | --- | --- | --- |
| `ml-1c-128m-20261021-sync-h` | E / 128MiB池、192MiB普通内存，九个独立profiles，总RAM704MiB | 七个ML/Attention算子和两个MobileNet均有有效耗时；完整结果见[结果表](GPU_MULTICLIENT_ML_RESULTS_20261021.md)；GPU租约峰值11484页/44.86MiB，Host最低可用2347.91MiB | PASS/rc0，采样/预热与原负载相同；Host/Guest健康、退出0/0、解绑/撤销、CPU/频率恢复、GPU/DMA归零与回收SHA通过 |
| `ml-2c-128m-20261021-sync-h` | 同E / 同每Client资源，2Client，总RAM1200MiB | 九项两边均有有效耗时；同步softmax38.003/37.882ms，原混合阶段错位已避免，不作运行代码提速归因；GPU租约峰值22783页/89.00MiB，Host最低可用1779.00MiB | PASS/rc0，Host/Guest健康、退出0/0/0、解绑/撤销、CPU/频率恢复、GPU/DMA归零与回收SHA通过 |
| `ml-3c-128m-20261021-sync-i` | F / 同每Client资源，3Client，总RAM1696MiB | 九项三侧均有有效耗时；GPU租约峰值32918页/128.59MiB，Host最低可用1206.93MiB | PASS/rc0，Host/Guest健康、退出0/0/0/0、解绑/撤销、CPU/频率恢复、GPU/DMA归零与39文件回收SHA通过 |
| `ml-4c-128m-20261021-ncnn-k` | F / 同每Client资源，4Client，总RAM2192MiB；恢复b后只运行两个MobileNet | v2均值79.870ms、历史Native保留39.14%；v3均值74.760ms、保留37.93%；GPU租约峰值34082页/133.13MiB，Host最低可用848.25MiB | PASS/rc0，Host/Guest健康、退出0/0/0/0/0、解绑/撤销、CPU/频率恢复、GPU/DMA归零与22文件回收SHA通过 |
| `ml-1c-384m-20261021-resnet-f` | E / 384MiB GPU池、304MiB普通内存，1Client | ResNet50 1532.36ms；对历史Native1162.99ms性能保留75.90%；GPU租约峰值86900页/339.45MiB，Host最低可用1764.80MiB | PASS/rc0，100 loops；Host/Guest健康、Realm退出0/0、解绑/撤销、CPU/频率恢复、GPU/DMA租约归零通过，回收SHA VERIFIED |
| `ml-2c-384m-20261021-resnet-f` | 同E / 同每Client资源，2Client，总RAM2448MiB | ResNet50 2782.37/2791.13ms，均值2786.75ms；对历史Native保留41.73%；GPU租约峰值173615页/678.18MiB，Host最低可用623.58MiB，窗口重叠99.83% | PASS/rc0，两侧各100 loops；Host/Guest健康、退出0/0/0、解绑/撤销、CPU/频率恢复、GPU/DMA租约归零通过，回收SHA VERIFIED |
| `ml-3c-384m-20261021-resnet-f` | E / 3Client需3568MiB，另保留Host256MiB | NOT_RUN_MEMORY_ADMISSION，无模型耗时 | 外层rc1，启动前拒绝；未创建Realm、GPU租约峰值/最终0，Host健康与回收SHA通过 |
| `ml-4c-384m-20261021-resnet-f` | E / 4Client需4688MiB，另保留Host256MiB | NOT_RUN_MEMORY_ADMISSION，无模型耗时 | 外层rc1，启动前拒绝；未创建Realm、GPU租约峰值/最终0，Host健康与回收SHA通过 |

全部场景已完成结果记录。四Client七个ML/Attention条目来自两轮失败尝试：GEMM/卷积/深度卷积/Softmax标为整轮GPU出错导致无效，Reduction保留无公共窗口，Attention-256/320保留提交失败；均无性能比例。四Client两个MobileNet使用恢复后的独立成功批次。ResNet50仅1/2Client有有效性能，3/4为明确未执行。各Client的原始数值、窗口和错误保存在对应summary及串口中，失败整轮的raw值不进入成绩表。

生成命令`python3 build/multiclient-ml-20261021/generate-results.py`为rc0，完整argv保存在`analysis-command.json`；它显式选择六个完成运行、两个准入拒绝、两个GPU失败项和五个失败整轮中的无效项。独立核验`python3 build/multiclient-ml-20261021/audit-results.py`为PASS/rc0，见同目录`final-audit.json`和`final-audit.log`：40条覆盖完整、65条已完成Client负载输出逐项核对、Native的51个文件SHA和10个原始指标一致、E/F输入及当前runner一致。六个完成运行均为PASS，全部19个Realm退出0，线程绑核、594MHz、可信IRQ、Host/Guest健康及资源恢复符合记录。另核对七轮失败及一次人为中止的保留证据，不将它们算作成功。

所有原始日志在`build/multiclient-ml-20261021/runs/<run-id>/`，命令及外层退出码见各自`realm-launch.json`和`lab-result.json`。统一外层资源/退出记录在`build/lab-runs/<run-id>/`；GPU故障来自实际负载，未进行故障注入，也未修改驱动超时来获得成绩。本轮测试发现的问题继续保留，不继承旧PASS。

## 复现与结果生成

先按环境主手册设置SSH环境变量。健康Host不重新刷写；使用已部署的Host #31 / RMM timer-v6 + 1GiB租约及匹配的只读rootfs。以下为四Client最终MobileNet成功批次的命令；每次使用新的run-id：

```bash
python3 scripts/maintenance/lab-run.py --run-id <新的run-id> -- \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/multiclient-ml-20261021/candidate-f \
  --workload glmark --performance --benchmark-only --suite \
  --profiles ncnn-mobilenet_v2 ncnn-mobilenet_v3 \
  --clients 4 --compact-memory --pool-mib 128
```

一至三Client使用完整`--profiles ml-gemm ml-conv ml-depthwise ml-reduction ml-softmax ml-attention attention-320 ncnn-mobilenet_v2 ncnn-mobilenet_v3`及对应`--clients`，一/二Client用E包，三Client用F包。四Client完整九项的sync-i及去掉Attention-320的八项sync-j均失败，按前述表格保留，不能把本例扩展为完整九项通过。

ResNet50单独运行：改为E包、`--profiles ncnn-resnet50 --pool-mib 384`，按目标选择`--clients 1`或`2`。三/四Client在当前板端已被内存准入拒绝，不用降低模型规模、减少loops或跳过检查替代原场景。`--workload glmark`沿用历史启动选项，实际执行的是显式列出的ML profiles。

每轮结束后用`collect-realm-evidence.py --run-id <run-id> --output <新目录>`回收SHA校验日志，并复制该轮`build/lab-runs/<run-id>/lease-monitor.json`及`lease-monitor-dmesg.log`到回收目录。外层完整命令/退出码、设备前后资源、Host健康位于`build/lab-runs/<run-id>/`；逐Client性能、屏障、Guest健康和退出码位于回收目录。统计使用`scripts/analysis/summarize-multiclient-ml.py`的`--runs`选择完成运行，`--not-run`选择两次ResNet50准入拒绝。输出`metrics.json`保留未舍入的耗时与观测窗口，`results.md`仅包含可发布表格；显示值保留三位小数，比例按未舍入值计算。

GPU提交失败用`--failed-case <目录> <profile>`单独记录；失败整轮中已执行的其他项用`--invalid-case <目录> <profile>`保留无效标签，均不采纳耗时。最终完整命令和退出码以`analysis-command.json`为准，结果表与生成文件逐字节一致。

## 清理与最终资源

独立核验通过后，仅删除从未部署、无运行引用的`candidate-b`五个文件，实际释放文件分配空间**77.9375MiB**。删除前检查所有矩阵终态、lab命令、打开fd、输入manifest、mtime及SHA；清单和结果在`build/multiclient-ml-20261021/cleanup-unused.json`，命令`python3 build/multiclient-ml-20261021/cleanup-unused.py`为rc0。E/F、使用过的失败输入、七轮失败、一次中止、两次恢复及全部已回收日志保留，没有删除成功/失败证据或用户源码。

最终资源命令`python3 scripts/maintenance/lab-resources.py --check --output build/multiclient-ml-20261021/final-resources.json`为rc0、issues为空，凭据通过环境变量提供。Pi/RK角色确认，无实验室VM/刷写进程；RK无loop残留，恢复Host #31/pmthor、CPU0–1、GPU请求/实际300MHz。Pi原有`/dev/loop0 → /var/swap`与开始时一致，未处理系统swap；Pi snapshot清单未变化。本轮未新增Pi固件/编译树，也未清理RK原始证据。

最终采样Pi可用内存668.76MiB、根分区可用16.35GiB；RK为3099.48MiB、14.00GiB。资源变化包含正常系统活动及受控重启，不能归因于上述控制机文件清理。所有新增运行日志留在既定证据目录，不把日志、凭据或编译缓存加入源码提交；本轮没有提交Git或更新发布manifest。
