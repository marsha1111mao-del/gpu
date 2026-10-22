# 多 Client 并行 glmark：性能、内存设计与验收

## 一、结论与验收范围

**2、3、4 Client并行完整720p glmark均已完成，每个并发数两轮；同期单Client也完成两轮。8轮全部PASS、外层退出码0，共20次Client完整评分、660条场景记录、28个Realm正常退出。** 每次均为Mali-G610真实渲染、33场景、validation 26成功/1既有数值例外/6无判据，额外验证失败、BO/export/VM_BIND/提交错误均为0；Host/Guest健康及资源恢复通过。

本次解决了扩展时的Proxy普通内存不足、VMM设备线程被vCPU挤占，以及validation结束时间不一致导致的评分错位。4Client与Proxy总Realm配置2432MiB，使用每Client128MiB授权池，共享只读rootfs；完整测试没有OOM。以下分数包含固定两核Client CPU预算下的CPU竞争与GPU共享影响。

| Client数 | 独立轮数 | 每轮Client均分的均值 | 轮间样本SD | CV | 对同期单Client分差/变化 | 评分保留比例 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 1157.50 | 3.54 | 0.31% | +0.00 / +0.00% | 100.00% |
| 2 | 2 | 668.25 | 146.02 | 21.85% | -489.25 / -42.27% | 57.73% |
| 3 | 2 | 497.17 | 0.24 | 0.05% | -660.33 / -57.05% | 42.95% |
| 4 | 2 | 360.25 | 9.90 | 2.75% | -797.25 / -68.88% | 31.12% |

均值先按一轮内全部Client求均分，再对两轮求均值；样本标准差也按两个轮均分计算。同轮Client共享资源，不能当作独立重复实验。两轮只支持描述性统计，不支持稳定性承诺或可靠置信区间。

### 与原生Panthor驱动对比（历史单进程参考）

**原生完整720p为1437分。** 来自2026-10-18的native-p42-comparison-20261018，原生glmark与外层均rc0，33场景、validation26/1/6、正确性及恢复检查通过；本次重新核对原始日志SHA和分数，没有重跑原生。

| 运行方式 | 平均分/Client | 对原生分差 | 对原生变化 | 原生单进程评分保留比例 |
| --- | --- | --- | --- | --- |
| 原生Panthor / 单进程 | 1437.00 | 0.00 | 0.00% | 100.00% |
| Proxy / 1 Client | 1157.50 | -279.50 | -19.45% | 80.55% |
| Proxy / 2 Client | 668.25 | -768.75 | -53.50% | 46.50% |
| Proxy / 3 Client | 497.17 | -939.83 | -65.40% | 34.60% |
| Proxy / 4 Client | 360.25 | -1076.75 | -74.93% | 25.07% |

两组均为RK3588/Mali-G610、1280×720、完整33场景、null-noop/finish、GPU请求600/实际594MHz、shader cache关闭。原生为Host #7、单进程固定CPU2；本轮为Host #31/protected/RMM timer v6，Proxy CPU1、Client共享CPU2–3，内核版本组合、运行日期及内存条件不同，CPU频率均未锁定。因此这是历史参考比较，单Client相差−279.50分/−19.45%也不能精确归因于虚拟化；多Client下降还包含共享资源竞争，不能直接称为额外虚拟化开销。

没有测量原生2/3/4进程并行glmark，不能将单进程1437分当作这些并发数的原生实测结果，也不能用1437除以Client数作为实测基线。下文另外给出合计评分指数对1437的比例，仅用于描述评分，不证明吞吐或加速。

原生证据：GPU-SFTP/log/native-current/native-p42-comparison-20261018/中的glmark-720.log、glmark-720.exit-code、glmark-720.clock.log和local-sha256.json；外层build/lab-runs/native-p42-comparison-20261018/result.json。原命令为python3 scripts/maintenance/lab-run.py --run-id native-p42-comparison-20261018 --allow-rk-reboot -- python3 build/native-current-20261018/native-controller.py。纯文档整理，未改运行代码，无新增性能测量。

## 二、环境、输入与可比条件

RK3588/Mali-G610；Host `6.12.0-opencca-pmthor-opp3 #31`，protected hVHE，RMM timer v6。复用GPUVM隔离v1最终F的Client/Proxy内核、静态工具、Firecracker及只读1.5GiB Panfrost rootfs；initrd仅重打包gpu-smoke.sh和performance-suite.sh。未重编Guest内核，未刷写Host、SD或固件。开发OOM之后同版本重启一次，正式矩阵全部在同一恢复启动周期执行。

负载为完整1280×720、null-noop、frame-end=finish、shader cache关闭。GPU请求600MHz，实际clk_gpu为594MHz；CPU频率未锁定。VMM非vCPU串口/设备线程固定CPU0，CPU0也承载Host控制工作；Proxy vCPU固定CPU1，全部Client vCPU允许CPU2–3。1/2/3/4Client保持相同CPU预算，未启用未经核验的CPU4及以上核心。

冻结执行包：`build/multiclient-glmark-20261020/candidate-e/`。以下SHA-256与8轮launch记录、最终源码一致：

| 输入 | SHA-256 |
| --- | --- |
| client-Image | a7e56e417a5dec024a977f2df2cb9f45f439491d3ce61b236f958e8fc074c511 |
| proxy-Image | 4265f1c22b199108ac42bf1c04a7856b0adc86eab5aa0fc6338350e125990e3c |
| initrd.cpio | be2960f2d1324ab2ace0524929a9e80f10d85604f28af706646709043d1f7903 |
| runner.py | 32f5cf42cca264588a6ffbdad73a50bb050761be8fff0dd0d6f146efc91314c2 |

原冻结1171/1170及GPUVM隔离v1最终F1159仍单独保留，本次不替换原runtime-manifest。旧1159为256MiB池、两个768MiB Realm；正式新配置单Client均值见上表，池、RAM、线程和评分启动策略同时调整，差异仅解释为组合观测，不能归因为某一项提速。

## 三、逐轮结果与并行证据

| run-id（实际顺序） | 各Client分数 | 轮均分 | 评分窗口重叠 | 最低采样MemAvailable MiB | Jain评分指数 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| multi-glmark-1c-128m-20261020-bar-a | 1160 | 1160.00 | 100.00% | 2191.93 | 1.0000 | PASS / rc0 |
| multi-glmark-3c-128m-20261020-bar-a | 371/757/364 | 497.33 | 96.99% | 902.50 | 0.8800 | PASS / rc0 |
| multi-glmark-4c-128m-20261020-bar-a | 353/334/378/348 | 353.25 | 99.64% | 240.88 | 0.9980 | PASS / rc0 |
| multi-glmark-2c-128m-20261020-bar-a | 566/564 | 565.00 | 99.98% | 1545.36 | 1.0000 | PASS / rc0 |
| multi-glmark-2c-128m-20261020-bar-b | 733/810 | 771.50 | 99.97% | 1527.62 | 0.9975 | PASS / rc0 |
| multi-glmark-4c-128m-20261020-bar-b | 233/235/766/235 | 367.25 | 94.20% | 244.54 | 0.7179 | PASS / rc0 |
| multi-glmark-3c-128m-20261020-bar-b | 365/764/362 | 497.00 | 96.97% | 874.57 | 0.8739 | PASS / rc0 |
| multi-glmark-1c-128m-20261020-bar-b | 1155 | 1155.00 | 100.00% | 2204.80 | 1.0000 | PASS / rc0 |

所有Client完成validation后报告READY并等待；Host收到全部READY后连续发送GO。时间来自Host CLOCK_MONOTONIC的串口接收观测，公共评分窗口/联合窗口至少90%，未逐项同步33个场景，串口记录存在传输误差。该证据证明评分阶段大部分时间重叠，不等于GPU硬件级同时执行时间戳。

双Client两轮均分565与771.5，波动明显，不能挑选较高一轮代表整体。四Client第二轮233/235/766/235，也不能仅因整体均分接近首轮就宣称公平性稳定。

Host命令行包含isolcpus=1,2,3，允许CPU2–3不保证自动均衡落核：四Client第二轮评分中的一次观察为Client1/2/4在CPU2、Client3在CPU3；双Client第二轮观察为CPU2/3各一个。三Client首轮回收阶段与第二轮评分阶段分别观察到2+1分布。它们与部分评分差异方向一致，但属于单次采样，未记录完整评分调度轨迹，不能确定全部差异原因。双Client首轮没有有效落核采样。CPU频率及温度未全程固定，因此本报告描述此部署的应用可见性能，不作纯GPU扩展效率或调度公平性的证明。

## 四、内存设计与调度修正

RK空闲MemAvailable约3.0GiB，直接复制原768MiB/Realm的4Client+Proxy需3840MiB。新配置按池大小P MiB及Client数N计算：Client RAM=P+256、CMA=P+64；Proxy RAM=N×P+256+32×N、CMA=N×P+64。Client CMA外普通内存192MiB，Proxy为192+32×N MiB。

| Client数 | 每Client池MiB | Proxy RAM/CMA MiB | 每Client RAM/CMA MiB | Realm总配置MiB |
| --- | --- | --- | --- | --- |
| 1 | 128 | 416/192 | 384/192 | 800 |
| 2 | 128 | 576/320 | 384/192 | 1344 |
| 3 | 128 | 736/448 | 384/192 | 1888 |
| 4 | 128 | 896/576 | 384/192 | 2432 |

启动准入要求全部Realm配置再加256MiB不超过Host初始MemAvailable；运行期间每秒采样。256MiB是准入预算，不是运行时可用内存硬下限；表中最低值是采样最低值，可能漏掉短暂低谷。RAM总配置也不等于实际驻留内存。不增加Host swap，不丢弃系统cache，不关闭服务。128MiB池已覆盖本次完整720p，不能据此推断1080p、NCNN或任意负载足够。

原Proxy固定192MiB CMA外普通内存，三Client在GEM/shmem元数据分配时OOM：约114MiB内核reserved，普通GFP_KERNEL水位不足，虽然CMA仍空闲约61MiB、Host仍有约0.85GiB可用。增加32MiB/Client普通内存后，3/4Client各两轮通过；授权、GPUVM根绑定、pin/fence及安全回收保持原语义。

VMM在XSHM_READY后把非vCPU线程移到CPU0，vCPU仍使用上述固定预算；避免忙等vCPU挤占串口/设备线程。所有VM先关停，再恢复CPU/GPU频率，避免先下线VM绑定CPU。

## 五、聚合评分与33场景明细

**glmark分数不是屏幕FPS；评分之和仅为聚合评分指数，不代表严格系统吞吐。** Jain只描述评分均衡性。各场景FPS列对该并发数下两轮全部Client取算术平均，未逐场景同步，不能把各Client FPS之和解释为同时吞吐。

| Client数 | 评分之和指数均值 | 合计指数/原生单进程1437（非吞吐） | Jain评分指数均值 | 最低采样可用内存MiB |
| --- | --- | --- | --- | --- |
| 1 | 1157.50 | 80.55% | 1.0000 | 2191.93 |
| 2 | 1336.50 | 93.01% | 0.9988 | 1527.62 |
| 3 | 1491.50 | 103.79% | 0.8770 | 874.57 |
| 4 | 1441.00 | 100.28% | 0.8579 | 240.88 |

三/四Client合计评分指数达到原生单进程评分的103.79%/100.28%，不表示比原生更快；并发阶段未逐场景同步，而且没有相同并发数的原生对照。下表原生列为同一历史单进程批次，1/2/3/4Client列为本轮各组平均FPS。

| 场景 / 平均FPS | 原生单进程（历史） | 1 Client | 2 Client | 3 Client | 4 Client |
| --- | --- | --- | --- | --- | --- |
| [build] use-vbo=false:  | 994 | 1120.00 | 711.00 | 540.67 | 379.25 |
| [build] use-vbo=true:  | 2299 | 1742.00 | 962.00 | 706.67 | 512.88 |
| [texture] texture-filter=nearest:  | 2311 | 1751.50 | 957.25 | 691.50 | 501.12 |
| [texture] texture-filter=linear:  | 2321 | 1753.50 | 950.75 | 691.67 | 502.25 |
| [texture] texture-filter=mipmap:  | 2307 | 1746.00 | 943.25 | 687.83 | 501.62 |
| [shading] shading=gouraud:  | 1919 | 1543.50 | 901.50 | 669.83 | 483.25 |
| [shading] shading=blinn-phong-inf:  | 1890 | 1526.00 | 897.00 | 668.83 | 481.88 |
| [shading] shading=phong:  | 1709 | 1431.50 | 845.25 | 629.83 | 450.38 |
| [shading] shading=cel:  | 1705 | 1427.50 | 844.00 | 627.33 | 449.00 |
| [bump] bump-render=high-poly:  | 1086 | 1057.50 | 599.75 | 434.17 | 319.00 |
| [bump] bump-render=normals:  | 2611 | 1876.50 | 1019.00 | 716.17 | 515.38 |
| [bump] bump-render=height:  | 2462 | 1804.00 | 997.25 | 722.67 | 524.12 |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0;:  | 1783 | 1476.50 | 867.50 | 630.17 | 456.25 |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;:  | 829 | 835.00 | 462.50 | 352.33 | 261.50 |
| [pulsar] light=false:quads=5:texture=false:  | 1686 | 1397.50 | 864.75 | 625.33 | 449.50 |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4:  | 388 | 232.50 | 117.75 | 86.17 | 63.88 |
| [desktop] effect=shadow:windows=4:  | 845 | 699.50 | 434.00 | 344.67 | 249.62 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map:  | 47 | 47.00 | 33.50 | 29.00 | 20.88 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata:  | 47 | 46.00 | 33.50 | 29.00 | 21.25 |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map:  | 66 | 65.50 | 47.00 | 41.00 | 29.88 |
| [ideas] speed=duration:  | 480 | 438.50 | 318.00 | 269.17 | 195.38 |
| [jellyfish] &lt;default&gt;:  | 1210 | 1115.50 | 685.00 | 550.33 | 398.62 |
| [terrain] &lt;default&gt;:  | 78 | 42.50 | 20.75 | 17.50 | 12.88 |
| [shadow] &lt;default&gt;:  | 982 | 753.00 | 433.25 | 316.50 | 216.38 |
| [refract] &lt;default&gt;:  | 196 | 137.50 | 68.75 | 63.17 | 38.88 |
| [conditionals] fragment-steps=0:vertex-steps=0:  | 1980 | 1562.00 | 892.25 | 569.00 | 515.12 |
| [conditionals] fragment-steps=5:vertex-steps=0:  | 1862 | 1491.00 | 888.25 | 653.17 | 431.75 |
| [conditionals] fragment-steps=0:vertex-steps=5:  | 1976 | 1564.00 | 907.75 | 659.50 | 482.50 |
| [function] fragment-complexity=low:fragment-steps=5:  | 1973 | 1562.50 | 907.00 | 673.67 | 477.25 |
| [function] fragment-complexity=medium:fragment-steps=5:  | 1747 | 1434.00 | 851.50 | 645.33 | 455.12 |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5:  | 1971 | 1561.00 | 896.75 | 685.00 | 480.38 |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5:  | 1970 | 1562.00 | 899.25 | 659.83 | 543.62 |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5:  | 1737 | 1429.50 | 844.50 | 767.83 | 516.12 |

## 六、开发失败、恢复与未执行项

| run-id | 原结果 | 原因/处理 |
| --- | --- | --- |
| multi-glmark-3c-128m-20261020-a | 中断 / rc255 / 无评分 | 建池仍推进，但VMM串口/主线程受vCPU挤占；定向清理后4个VM退出0。旧summary为RUNNING但外层失败与最终退出证明已结束。后续分离非vCPU线程。 |
| multi-glmark-3c-128m-20261020-io-a | FAIL / rc1 / 无有效评分 | Proxy普通内存OOM/panic，非Host OOM；保存证据后同版本重启，增加32MiB/Client普通内存。异常撤销产生的Host WARNING不宣称已修复。 |
| multi-glmark-3c-128m-20261020-mem-a | FAIL / rc1 / 不纳统计 | 三个Client虽完成370/420/738分，但评分窗口仅重叠88.59%，低于90%；VM退出[0,0,0,-15]。增加validation后READY/GO屏障并后移CPU恢复。 |
| multi-glmark-post-oom-reboot-20261020-a | 恢复 / rc0 | 仅同版本正常重启，未刷写；正式矩阵在恢复后的同一启动周期执行。 |

早期资格/开发PASS也不混入正式重复统计：紧凑单Client1158/1156；旧线程策略双Client805/736；线程分离后单Client1153、双Client738/802。它们的输入或线程/内存/屏障配置不同，原始证据独立保留。没有因后续PASS删除失败事实。

本次未重跑API/计算/1080p/NCNN、长期压力、多vCPU、侧信道等扩展；历史Group submit fence间歇超时及异常撤销WARNING不由此次glmark矩阵宣称解决。

## 七、清理与最终健康

控制机删除被candidate-e替代的candidate-a/b/c/d共20个文件；已核对SHA、保留等价输入和打开fd。独有文件分配释放204800字节，另已计目录块12288字节；另清除本任务4个Python缓存及3个空目录，分别释放文件分配118784字节与目录块12288字节。大镜像为硬链接，不能把逻辑大小当作实际释放容量。最终candidate-e、原GPUVM final-f、当前源码及所有成功/失败证据保留。

矩阵完成后，经独占维护multi-glmark-cleanup-20261020-a删除RK上8份已校验回收的旧成功日志副本，保留最近5次正式成功及全部失败日志；删除93个文件，释放最后链接文件块23314432字节及目录块32768字节。控制机全部原始证据保留。未删除基础rootfs、模型、固件、运行输入或Pi回退snapshot；本轮未新增板端编译树或Pi snapshot。

| 设备 | 任务初始→最终MemAvailable MiB | 根分区可用GiB | 最终实验室进程 |
| --- | --- | --- | --- |
| pi | 669.04 → 662.88 | 16.354 → 16.354 | 0 |
| rk | 3105.89 → 3100.02 | 14.166 → 14.140 | 0 |

上述任务起止资源变化包含测量证据写入与正常系统活动，不能全部归因于清理。实际删除分配容量以前述逐文件块统计为准。最终RK恢复pmthor、CPU0–1、GPU300MHz，无本轮VM/loop/工作负载挂载残留；Pi/RK角色与资源门槛通过，维护外层rc0。

## 八、命令、证据与复现

每轮先通过lab-run.py取得Pi/RK独占锁；以下N取1/2/3/4，run-id使用上表对应值或全新唯一值。先完成单Client完整720p并达到1000分，再扩展并发。

```bash
python3 scripts/maintenance/lab-run.py --run-id <run-id> -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/multiclient-glmark-20261020/candidate-e \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720 \
  --clients <N> --compact-memory --pool-mib 128
```

各轮原始命令、外层退出码、前后资源及Host健康：`build/lab-runs/<run-id>/`。逐文件SHA校验回收的summary、33场景、串口、commands.jsonl、memory-samples.jsonl：`build/multiclient-glmark-20261020/runs/<run-id>/`。统计：`statistics-barrier/statistics.json`、`statistics.md`和`client-scores.csv`；审计：`final-audit.json`；清理：`qualification-cleanup.json`、`obsolete-bundles-cleanup.json`、`log-cleanup-result.json`。以上相对路径均从本仓库根目录起算，不是Notion可直接下载链接。

回收命令：`python3 scripts/maintenance/collect-realm-evidence.py --run-id <run-id> --output <新目录>`；统计命令：`python3 scripts/analysis/summarize-multiclient-glmark.py --runs <本表8轮回收目录> --output <统计目录>`。统计拒绝重复run-id、不完整场景、混合输入、未清理Realm和低于90%窗口的结果；本表8轮已按原始日志和SHA独立审计。

统一记录：扩展2/3/4Client完整720p并解决内存/线程/同步问题｜GPUVM v1单Client1159 → 本版单Client均值1157.50｜-1.50分 / -0.13%｜池256→128MiB，RAM/线程/屏障组合变化，CPU频率未锁定，多并发保持CPU2–3预算｜本表8个run-id、上述完整命令、rc0及日志目录｜保留candidate-e和本轮统计，不替换原冻结1171/1170。
