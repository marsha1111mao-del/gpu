# 同期 Native / 多 Client glmark 公平对照

正式矩阵已全部执行并独立核验：720p、1080p各覆盖原生1–4进程与1–4 Client，
A/B各一轮，共32个配置；29个有效、3个因原生GPU超时无效。全部16个Realm配置通过。
独立四Client 1080p RPC/提交/IRQ诊断通过；最终独立核验为VERIFIED_WITH_FAILURES，
没有缺失的正式配置。Notion正式对照表已更新并回读核对，全部36个表格单元格正确，
40条ML/NCNN结果及原有原因说明逐字保留。

## 同并发数对照结果

每格先计算一轮内各进程/Client的算术均分，再取A/B两轮均值；分数越高越好。
保留比例=同分辨率、同并发数的Clientproxy均分÷Native均分。任一模式未取得两轮
有效结果时不计算比例，失败分数不参与均值，也不使用历史单进程数据补位。

| 分辨率 / 并发数 | Native 每进程分数 | Clientproxy 每Client分数 | 分数保留比例 |
| --- | --- | --- | --- |
| 1280×720（1） | 1560.50 | 1158.00 | 74.21% |
| 1280×720（2） | 812.50 | 768.00 | 94.52% |
| 1280×720（3） | 536.67 | 498.33 | 92.86% |
| 1280×720（4） | 失败（A通过，B超时） | 355.50 | — |
| 1920×1080（1） | 1130.00 | 902.00 | 79.82% |
| 1920×1080（2） | 587.75 | 597.50 | 101.66% |
| 1920×1080（3） | 394.50 | 387.17 | 98.14% |
| 1920×1080（4） | 失败（A/B均超时） | 276.63 | — |

Native并发本身同样显著降分，因此旧表以单进程Native作所有行分母，会混入共享
资源后的正常分摊。当前双/三Client与同并发Native的差距明显小于该旧口径。
1080p双Client超过100%是本次两轮、整体执行栈下的观测，不证明代理本身带来加速。
只有两轮，不据此宣称统计显著、长期稳定或四进程原生可稳定运行。

## 可比条件与边界

| 条件 | Native | Proxy / Client |
| --- | --- | --- |
| 硬件/固件 | 同一RK3588，Host #31 / RMM timer-v6 + 1GiB GPU租约 | 相同 |
| Host模式 | nVHE | protected hVHE |
| 用户态 | 同一只读Panfrost rootfs、Mesa和glmark二进制 | 相同 |
| CPU预算 | CPU0–3在线、policy0固定1.8GHz，负载按CPU2/3/2/3放置 | 相同负载放置；Proxy CPU1、VMM I/O CPU0 |
| GPU | 请求600MHz，采样实际594MHz | 相同 |
| 工作负载 | 完整33场景，null-noop离屏、frame-end finish，shader cache禁用 | 相同 |
| 开始同步 | 所有进程验证完毕后统一放行计分 | 所有Client验证完毕后统一放行计分 |
| 内存布局 | 各进程独立只读chroot和256MiB私有tmpfs | 按统一F公式扩展，见下文 |

Host #31在protected模式下阻止Host GPU MMIO访问，Native必须切为nVHE。
所以这是原生执行栈与受保护Realm代理执行栈的比较，不能把全部差异单独归因于
Proxy转发，也不能宣称两者的内存访问路径或RSS完全相同。没有修改Host Image或RMM。

Realm统一采用Client普通内存192MiB、额外CMA16MiB、SWIOTLB16MiB；720p池128MiB，
1080p池192MiB。Client RAM=192+池大小+16MiB；Proxy RAM=192+32×Client数+
池大小×Client数+16MiB。各并发数均采用这一公式，未混入旧单/双Client配置。

只在整套计分入口同步，没有逐场景屏障；应用、驱动及GPU调度均包含在成绩内。
有效配置的共同计分窗口最低96.88%，均超过90%门槛；整套窗口重叠不代表每个
场景均严格重叠。各进程分数之和不能当作GPU总吞吐或纯硬件扩展效率。

顺序：A轮分辨率/并发数递增；Realm B轮递减。Native B先执行720p四进程，失败
后恢复并重启，只补720p 3/2/1及1080p 3/2/1/4，已失败项不重试。该恢复和顺序
差异保留披露，未改变各配置的频率、绑核、内存、负载与用户态输入。

## 两轮各进程原始分数

| 分辨率 / 并发数 / 模式 | A轮 | B轮 |
| --- | --- | --- |
| 720p / 1 / native | 1563 | 1558 |
| 720p / 1 / realm | 1159 | 1157 |
| 720p / 2 / native | 813 / 808 | 816 / 813 |
| 720p / 2 / realm | 799 / 738 | 785 / 750 |
| 720p / 3 / native | 634 / 783 / 189 | 638 / 786 / 190 |
| 720p / 3 / realm | 361 / 766 / 368 | 374 / 757 / 364 |
| 720p / 4 / native | 253 / 346 / 385 / 534 | FAIL（整组分数排除） |
| 720p / 4 / realm | 381 / 359 / 332 / 353 | 353 / 355 / 332 / 379 |
| 1080p / 1 / native | 1128 | 1132 |
| 1080p / 1 / realm | 902 | 902 |
| 1080p / 2 / native | 588 / 586 | 590 / 587 |
| 1080p / 2 / realm | 601 / 595 | 598 / 596 |
| 1080p / 3 / native | 307 / 570 / 308 | 523 / 560 / 99 |
| 1080p / 3 / realm | 299 / 563 / 297 | 300 / 578 / 286 |
| 1080p / 4 / native | FAIL（整组分数排除） | FAIL（整组分数排除） |
| 1080p / 4 / realm | 280 / 262 / 273 / 290 | 304 / 259 / 286 / 259 |

三进程时，原生720p两轮分别634/783/189和638/786/190；1080p分别307/570/308和
523/560/99，均存在明显不均。Realm的Client1/3共享CPU2，Client2独占CPU3。
CPU预算、落核、原生调度和场景阶段均须考虑；这一关联不能证明唯一瓶颈来自CPU，
也不能仅由均分下降认定GPU只能串行执行。

## 补充CPU观测

Host每2秒采集CPU计数、线程亲和性、频率、温度和内存，并在各组共同计分窗口
核验实际落核及频率；Realm另每2秒采集/proc/stat。下表Guest窗口覆盖验证加计分，
非idle排除idle/iowait/steal，但仍可能包含驱动轮询。未报告steal不证明没有物理CPU竞争。

| 分辨率 / Client数 / 轮次 | Proxy Guest非idle | 各Client Guest非idle |
| --- | --- | --- |
| 720p / 1 / A | 31.03% | 99.10% |
| 1080p / 1 / A | 26.21% | 98.66% |
| 1080p / 1 / B | 25.36% | 98.71% |
| 1080p / 2 / A | 47.16% | 93.90% / 93.90% |
| 1080p / 2 / B | 48.07% | 93.88% / 93.35% |
| 1080p / 3 / A | 47.14% | 90.66% / 85.49% / 87.81% |
| 1080p / 3 / B | 46.90% | 90.36% / 85.87% / 87.67% |
| 1080p / 4 / A | 46.24% | 88.79% / 81.79% / 79.44% / 82.62% |
| 1080p / 4 / B | 47.74% | 90.01% / 84.06% / 86.47% / 84.29% |
| 720p / 1 / B | 29.71% | 98.31% |
| 720p / 2 / A | 59.36% | 95.80% / 95.18% |
| 720p / 2 / B | 58.94% | 96.10% / 95.45% |
| 720p / 3 / A | 57.13% | 92.24% / 87.52% / 92.81% |
| 720p / 3 / B | 54.67% | 92.88% / 88.12% / 91.83% |
| 720p / 4 / A | 57.52% | 92.95% / 92.65% / 89.75% / 90.70% |
| 720p / 4 / B | 57.16% | 90.56% / 91.42% / 87.63% / 90.45% |

所有正式Realm配置均未观测到Proxy两秒区间非idle达到95%。现有数据不支持
“Proxy持续满载”的判断，但不能排除短时热点、锁等待或串行提交。
Host观察到vCPU 100%可能含空闲忙等；GPU频率594MHz也不等于GPU利用率。
当前没有可靠的GPU busy计数，不把CPU采样或提交耗时当作GPU执行时间。

## 独立RPC / 提交 / IRQ诊断

fair-diagnostic-1080-4c-20261021-a退出0，264/270/281/287，均分275.50，
共同计分窗口99.6747%；完整正确性、Host/Guest健康、五个Realm退出0、恢复及
GPU/DMA租约归零通过，23个文件SHA收集核验通过。租约峰值185559页，最终
GPU/DMA/errors均0。Proxy Guest非idle47.84%，没有两秒区间达到95%。
沿用四Client1080p配置，仅增加已有RPC、提交及IRQ计时；成绩不计入正式两轮均值。

计时范围含验证、计分和退出，按每种操作/marker最后可见累计快照提取，不累加
重复快照。Client合计1445512次RPC，记录的传输错误/超时均0；PLAN_EXEC、
SYNCOBJ_WAIT、SYNCOBJ_TRANSFER及SNAPSHOT_RETIRE的四Client调用数之和，
均与Proxy相应计数一致。Group提交与run_job计数均432860，run_job错误0。

| 观察点 | 平均耗时或次数 | 含义 |
| --- | --- | --- |
| Client PLAN_EXEC完整RPC | 每Client平均0.740–0.850ms；合计433433次 | 包含发送、响应与调度等待 |
| Client PLAN_EXEC发送区间 | 每Client平均0.652–0.762ms | 包含d->lock、队列发布和RMM通知，不等于数据复制的CPU时间 |
| Proxy PLAN_EXEC处理 | 34.644μs | 服务端处理墙钟时间 |
| Proxy SYNCOBJ_WAIT处理 | 809.187μs；120819次 | 包含真实完成等待，不能当作可删除的计算开销 |
| Proxy内Panthor GROUP_SUBMIT | 22.921μs；其中映射BO缓存同步平均7.201μs/次 | 不含整个GPU执行时长 |
| Proxy内Panthor run_job | 53.260μs；其中sched->lock等待平均47.254μs/次 | 值得继续拆分锁等待和线程调度影响 |
| Proxy VM_BIND处理 | 327.280μs；4294次 | 当前可用的绑定路径测量 |
| job IRQ raw到thread | 平均30.613μs，最大111.349ms；1271717样本 | 下半部调度延迟；不是GPU执行时长 |
| job IRQ硬中断/下半部处理 | 平均0.229μs / 2.914μs | 不含raw到thread的等待 |

原生VM_BIND细分计数为0：当前内核服务走panthor_vmshm_vm_bind，未进入这组
ioctl细分计时点，因此这组0不能解释为没有VM_BIND或没有映射开销；采用Proxy
处理计数，保留这一覆盖限制。完整原始统计位于analysis-final/audit.json的
diagnostics[].timings，并可对照realm-0至realm-4.log。

RPC及驱动计时为含锁、等待和调度的墙钟时间，嵌套计时不能相加为互斥百分比。
现有证据更值得优先细分Client发送路径和原生提交锁等待，再评估绑核、通知合并及
在途额度；尚不能断言RMM执行慢、Proxy CPU已满载，或GPU缺少并行能力。

## 验收与失败记录

每个有效配置均检查真实Mali renderer、完整33场景、validation与clean、退出码、
完整新增内核日志、实际频率/亲和性、共享计分窗口、输入哈希及测试后资源恢复。
Validation为26项成功、1项既有数值例外、6项无判据，不称33项均有像素正确性证明。
Realm还核验全部Realm退出0、GPU/DMA租约与错误归零。Native只读rootfs哈希前后一致。

| run-id / case | 状态及证据 | 采信与恢复 |
| --- | --- | --- |
| fair-native-20261021-a / protected启动 | modprobe SIGSEGV11，GPU MMIO权限异常/Oops，未计分 | 不计入32配置；已恢复。原始摘要保留，但完整Oops未在重启前独立归档，journal不可用，证据有此限制 |
| fair-native-nvhe-20261021-a / native-1080-4p-a | 两次job timeout，Mesa提交错误，两进程rc125；批次/外层rc1 | 四个分数全部排除；此前七个独立配置完整内核历史健康，单独采信。原extlinux、同镜像、protected/CPU0–1/pmthor恢复通过 |
| fair-native-nvhe-20261021-b / native-720-4p-b | 一次job timeout，process-2 rc125且clean FAIL；外层rc1 | 四个分数全部排除，即使其他进程clean PASS。挂载/loop清理、rootfs/配置/镜像及Host恢复通过 |
| fair-native-nvhe-20261021-b-rest / native-1080-4p-b | 一次job timeout，process-3 rc125；外层rc1 | 四个分数全部排除；此前六项完整内核历史健康，单独采信。挂载/loop清理、rootfs/配置/镜像及Host恢复通过 |

三个失败配置均无OOM、BO分配、导出或VM_BIND错误证据；GPU超时根因未确定，
不能归因于内存不足。失败批次保留FAIL和非零退出码，不被其他配置PASS覆盖。

测试工具修正：原健康正则漏掉裸job timeout，后续runner及独立核验器已补齐；
原v3编排只接受最后一项失败，720p四进程失败后如实停止。冻结v4仅新增显式case
选择以补未执行项；核验器按计划的已执行前缀检查部分批次，保留失败、检查历史
内核健康及重复轮次，不能通过删失败或重跑至PASS来补齐矩阵。

## 改动、门槛与复现

改动目的｜统一同期同并发测量｜旧F完整720p单轮1157 → 本轮单Client两轮均值1158
（1159/1157）｜+1分/+0.086%｜CPU固定1.8GHz、落核及采样条件变化，旧单轮与新
均值不可单变量归因｜门槛A为1159≥1000，退出0，正确性/健康/恢复通过｜保留测量
配置；未修改GPU运行代码，不宣称代码优化提分。

固定输入位于build/fair-glmark-20261021/bundle/，SHA见bundle/hashes.json。
控制器分别由controller-hashes-v2/v3/v4.json冻结。Guest仍为F组合；不替换旧发布manifest。
共享rootfs SHA：5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60。
Host Image SHA：8c277a621abcc8cf40c2801176f25ca62fff795be6e8a0324e8d64325040999d。

Realm正式命令（每项独立run-id，720p/1080p池分别128/192MiB）：

```bash
python3 scripts/maintenance/lab-run.py --run-id <run-id> -- \
  python3 build/fair-glmark-20261021/observe-run.py \
  python3 scripts/run/run-realm-lease-monitor.py --monitor \
  build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py --images build/fair-glmark-20261021/bundle \
  --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-<720或1080> --clients <1至4> --compact-memory \
  --pool-mib <128或192> --client-cpu-layout round-robin \
  --cpu-frequency-khz 1800000 --telemetry
```

计时诊断在四Client1080p命令末尾增加--rpc-stats。Native A、B及续测命令分别使用
native-mode-controller.py、native-mode-controller-v3.py及native-mode-controller-v4.py；
完整实际命令、退出码和run-id保存在matrix-v3.json、matrix-v4.json及各lab result.json。
续测v4显式参数为--round b --cases 720:3 720:2 720:1 1080:3 1080:2 1080:1 1080:4，
通过lab-run.py --allow-rk-reboot执行；只切换SD2现有extlinux模式并恢复，未更换Image。

独立核验命令：

```bash
python3 scripts/analysis/summarize-fair-glmark.py \
  --experiment build/fair-glmark-20261021 \
  --output build/fair-glmark-20261021/analysis-final
```

本机证据：build/fair-glmark-20261021/{realm,native,observations}/<run-id>/，
含完整原始输出、SHA收集清单、计分事件、CPU样本和内核日志；
build/lab-runs/<run-id>/{before,after,result}.json含命令、退出码及Host资源恢复。
板端原始目录为/root/GPU-SFTP/log/{realm-xshm,fair-native}/<run-id>/。
所有正式Realm命令/外层rc0；三个原生失败配置所在批次外层rc1。

最终独立核验：29个有效、3个失败、无缺失正式配置，另有1个有效独立诊断；
状态VERIFIED_WITH_FAILURES。核验命令退出0，失败原始批次仍为非零退出码。
最终资源检查退出0、issues为空；Pi/RK均角色正确、无活动实验进程。Pi可用内存
680.29MiB/根盘空闲16.35GiB；RK为3111.47MiB/13.84GiB，CPU0–1、pmthor，
无残留loop或GPU-SFTP挂载。Pi原有/var/swap loop保留。记录见final-resources.json。
[Notion多Client并行测试结果合集](https://app.notion.com/p/3ff659a3b8cc813bbab7c109be10ad21)
已更新正式结果和诊断，最终回读核验全部36个表格单元格，40条ML/NCNN及原因说明
逐字未变。副本为实验目录的notion-before.json、notion-after-primary.json及
notion-after-final.json。
