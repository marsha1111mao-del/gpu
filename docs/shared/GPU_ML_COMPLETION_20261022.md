# 多 Client ML 未完成项修复与验证

后续已补充[Native四进程 ↔ 四Client对照](GPU_NATIVE_ML4_COMPARISON_20261022.md)，7项Native有效、3项GPU失败；原历史单进程Native表及本页九条共享补测结果保持不变。

四 Client 的七个 ML/Attention 算子，以及三/四 Client ResNet50，共九条已全部补测通过。外层/runner退出0、所有Realm正常退出、内核健康、资源恢复和GPU/DMA租约归零均已核验。独立审计检查100份原始Client输出：[当前结果表](GPU_MULTICLIENT_ML_RESULTS_20261021.md)共40条，保留原31条有效数据并补入九条新数据，并非当前组合重测全部40条。原失败、无效和内存准入拒绝证据继续保存在[原报告](GPU_MULTICLIENT_ML_20261021.md)及各run目录。

| 补测项目 | Client数 | 每Client平均耗时 ms | Native历史单进程 ms | 性能保留比例 |
| --- | ---: | ---: | ---: | ---: |
| Reduction | 4 | 34.803 | 10.695 | 30.73% |
| 卷积 | 4 | 130.491 | 34.135 | 26.16% |
| 深度卷积 | 4 | 84.710 | 21.894 | 25.85% |
| GEMM | 4 | 111.144 | 29.116 | 26.20% |
| Softmax | 4 | 66.589 | 19.404 | 29.14% |
| Attention-256 | 4 | 2866.044 | 773.543 | 26.99% |
| Attention-320 | 4 | 4394.888 | 1221.823 | 27.80% |
| ResNet50 | 3 | 3170.780 | 1162.990 | 36.68% |
| ResNet50 | 4 | 5660.180 | 1162.990 | 20.55% |

性能保留比例为Native耗时除以Client均值。四Client同时运行，但GPU最多三个任务在途；表中包含排队、CPU竞争及代理执行成本，不是四路GPU稳态吞吐测量。

## 问题与实现

1. 四 Client Attention-320 在采用共享目标后备回收的 VMM 后仍复现 GPU 超时：`ml-fix-attention320-4c-20261022-a`，外层退出1，23条 job timeout 和 Mesa 提交错误。内存回收本身没有修复 GPU 调度问题。
2. 首个候选限制三个驻留Group，但 `ml-fix-attention320-4c-20261022-b` 触发CSG固件切换超时和Mesa提交错误，外层退出1，方案撤回。最终方案在DRM调度器处理原依赖后、任务真正进入GPU前，通过独立fence chain封装真实finished fence，限制最多三个在途任务；等待发生在提交前，不计作GPU执行超时，也不触发强制固件上下文切换。四Client启用 `panthor.max_inflight_jobs=3`，其他并发数保留默认调度。原5秒任务超时阈值不变；不缩小shader、模型、采样数或推理次数。七项四Client算子已通过硬件验收，不据此证明任意恶意任务或长期运行均无超时。
3. 原 Reduction 屏障位于进程入口，编译和预热错位导致没有共同执行窗口。新 GLES 测试程序在预热后报告 READY，全部 Client 就绪再开始原测量循环，以真实计时区间判断公共窗口。没有公共窗口仍判失败；NCNN 保留原完整工作负载窗口口径。
4. ResNet50 原准入把 Client 目标池旧后备和 Proxy 真实共享源池同时计入整个运行期。显式 `--reclaim-targets` 只允许已验证 SHA 的回收版 VMM 和单独 ResNet50 profile，按配置上界扣除已回收目标池；逐 Client 建池，每次分配前检查实际可用内存，以256 MiB作为Host准入/阶段余量门槛。启动阶段临时目标池另外检查，不把稳态预算当作启动峰值。该门槛不是运行期间强制保留256 MiB的硬隔离保证，实际最低可用内存另列。其他测试默认保留原准入。
5. 三 Client 使用原384 MiB池与304 MiB Client普通内存，稳态私有配置上界2416 MiB。复核旧实测发现304 MiB普通内存的Client在模型运行期间可用内存曾只有34.76 MiB，因此撤回未执行的256 MiB Client预算提案。四 Client 的D候选使用336 MiB池、304 MiB Client普通内存和192 MiB Proxy普通内存，稳态上界2832 MiB；加256 MiB Host余量需要3088 MiB，现场可用3074.11 MiB，启动前安全拒绝。E候选仅对四Client回收模式将每Realm SWIOTLB从16降至8 MiB，Client普通配置相应304→296 MiB，扣除bounce后可用预算仍为288 MiB；Proxy普通配置改为200 MiB，扣除bounce后的预算较D增加16 MiB。稳态上界2808 MiB，仍保留256 MiB Host余量及逐阶段检查。336 MiB池扣除1 MiB通信区和2 MiB对齐保留后，分配器管理333 MiB；对既有327.77 MiB用户BO峰值的名义余量约5.23 MiB，容量和I/O仍须完整模型实测验收。
6. 四份 ResNet50实际 GPU页超过原1 GiB全局租约容量。RMM候选把有界页租约表扩为2 GiB并相应扩大散列桶；owner、引用计数、互斥、撤销和失败回滚不变。扩容仅增加元数据容量，不预分配2 GiB物理内存。

ResNet50准入预算如下，准入时均另要求256 MiB Host余量。稳态列是配置推导的私有内存上界，实际峰值另由硬件采样记录；启动时还会临时分配一个目标池，因此每次source/target分配前均检查实际可用内存。

| 配置 | 每Client池 MiB | 每Client RAM MiB | Proxy RAM MiB | VM配置合计 MiB | 回收后的稳态私有上界 MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| 三Client原配置 | 384 | 704 | 1456 | 3568 | 原准入未扣除目标池 |
| 三Client新准入 | 384 | 704 | 1456 | 3568 | 2416 |
| 四Client原配置 | 384 | 704 | 1872 | 4688 | 原准入未扣除目标池 |
| 四Client D：准入拒绝，未运行 | 336 | 656 | 1552 | 4176 | 2832 |
| 四Client E：模型初始化失败 | 336 | 648 | 1560 | 4152 | 2808 |
| 四Client F：通过 | 336 | 640 | 1592 | 4152 | 2808 |

四Client E的额外CMA仍为16 MiB，SWIOTLB为8 MiB；三Client及其他profiles仍使用16 MiB SWIOTLB。不能把VM配置合计、共享页回收后的私有上界和实测同时内存峰值混为一个指标。

E已发现模型初始化失败：Client3通过独立Vulkan资格检查，但模型的 `vkCreateDevice failed -3` 后回退CPU，程序退出0，测试正确判为失败/rc125；该整批耗时不采信。Client串口显示实际模型在VM/前三个BO创建后、tiler heap成功标记之前退出；尚未取得当时Proxy的具体errno，不把该现象直接等同Host OOM。失败后追加的Proxy内存诊断显示可用35.10 MiB，而Client挂接后各有15.61 MiB空闲CMA。F仅将四Client回收模式的Client CMA额外预留16→8 MiB，把合计32 MiB转给Proxy普通内存200→232 MiB；Client普通配置296 MiB、SWIOTLB8 MiB、336 MiB共享池及模型参数保持。VM合计、稳态准入及Host256 MiB准入门槛均不变。F已独立通过模型与生命周期验收，支持该预算调整的有效性；没有直接取得E失败时的errno，因此不把E具体分配失败点写成已证明的根因。

## 已完成验证

改动目的｜解决驻留争用、测量错位及内存准入问题｜同期公平旧720p均值1158 → 调度候选A单轮1158｜0分 / 0%｜同Host #31、原1 GiB租约、128 MiB池、完整33场景、CPU固定1.8GHz与round-robin、GPU594MHz；新Proxy调度及测试载荷组合变化，不作单项提速归因｜`ml-fix-720-20261022-a`，外层及Realm runner退出0，两个Realm退出0，validation26/1/6、内核健康、GPU/DMA租约归零通过｜历史证据保留，驻留组方案随后因ML失败撤回。

证据目录：`build/ml-completion-20261022/`；硬件日志按 `runs/<run-id>/` 保存，独占锁、完整命令/退出码、租约、Host健康和资源前后对照在 `build/lab-runs/<run-id>/`。720p已收集11文件并逐一SHA核对。旧Attention320复现失败18文件同样已核对。

Proxy、静态init和GLES测试程序交叉构建通过；生产runner解析12项正反例、三/四Client预算及逐阶段余量边界检查通过。RMM endpoint、memory、GPU租约/可信控制及IRQ软件检查通过；2 GiB固件构建和ELF内存布局检查通过，并以 `ml-rmm-2g-20261022-a` 经SD2正式入口完成部署、启动区备份和恢复验收，退出0、Realm能力1、Host仍#31/pmthor。BSS较原1 GiB版本增加6.25 MiB，位于原固定RMM预留范围内。初次构建缺EGL/KHR头及默认交叉工具链前缀错误已修正，失败日志保留。这些软件检查不能替代硬件运行。

改动目的｜采用任务在途准入、测量屏障和2 GiB租约支持ML补测｜同期公平旧720p均值1158 → 最终GPU代码候选C单轮1157｜−1分 / −0.086%｜同Host #31、128 MiB池、CPU固定1.8GHz/round-robin、GPU594MHz；Proxy驱动、测试载荷及RMM容量组合变化，不作单项归因｜`ml-fix-720-20261022-c`，外层/runner退出0、两个Realm退出0、33场景、validation26/1/6、健康/恢复/GPU-DMA归零通过，11文件SHA核对；命令见下文及该轮 `result.json`｜保留。单Client门槛未启用四Client专用在途准入，不据此宣称该策略提速。D/E/F仅调整未在720p路径执行的四Client模型内存配置，内核及initrd与C相同。

`ml-fix-7profiles-4c-20261022-d` 七项算子均已通过，外层/runner退出0、五个Realm退出0，Host/Guest健康、解绑/撤销、CPU/GPU恢复及GPU/DMA租约归零通过，42文件回收SHA核对完成。真实计时公共窗口依次为Attention-320 34.925秒、Attention-256 238.176秒、Reduction 2.394秒、GEMM 10.218秒、卷积12.406秒、深度卷积8.121秒、Softmax 1.934秒。重叠比例16.47%–94.32%，仍包含固定CPU2–3预算下的域间不均，不把全部迭代均值解释为四路GPU稳态吞吐。四Client同时运行、GPU最多三个在途任务，排队时间计入应用迭代耗时。GPU租约峰值43957页，Host最低可用1263.06 MiB。

`ml-fix-api-2c-20261022-d` 双Client各19项ioctl、真实计算、分段BO mmap、权限/IRQ、Host/Guest健康、三个Realm退出0及GPU/DMA租约归零通过，外层/runner退出0、10文件SHA核对通过。未执行provider replacement或注入GPU故障，不扩大验收范围。

`ml-fix-resnet-3c-20261022-d` 三Client ResNet50通过，各100 loops、2 threads、224×224、panvk-direct；每次迭代分别3526.55 / 2353.87 / 3631.92 ms。外层/runner退出0，四个Realm退出0、Host/Guest健康、恢复与GPU/DMA租约归零通过，15文件SHA核对完成。只读gmem检查确认三个共享源各98304缓存页、三个Client旧目标均为0；GPU租约峰值260330页/1016.91 MiB，Host最低可用652.95 MiB。完整工作负载公共窗口318.73秒/55.94%，含资格检查和模型加载，不是推理循环精确同步。

`ml-fix-resnet-4c-20261022-d` 外层退出1、启动前内存准入拒绝，没有创建Realm或提交GPU任务；3文件SHA核对完成。保留该NOT_RUN及辅助gmem检查因无绑定而失败的原始记录，不通过取消Host余量获得PASS。E外层退出1，22文件SHA核对通过；五个Realm退出0、健康/恢复、GPU/DMA租约归零及四组源/目标真实缓存检查通过，模型失败仍保留为FAIL，Host最低可用142.62 MiB。失败后仅对已失败批次追加Proxy/Client3内核日志和内存诊断，命令记录在该轮lab目录的 `live-diagnostic*.json`。

`ml-fix-resnet-4c-20261022-f` 四Client ResNet50全部通过，各100 loops、2 threads、224×224、panvk-direct；每次迭代分别5555.43 / 5631.06 / 5686.08 / 5768.15 ms。外层/runner退出0，五个Realm退出0、Host/Guest健康、解绑/撤销、CPU/GPU恢复及GPU/DMA租约归零通过，18文件回收SHA核对完成。gmem只读检查确认四个真实共享源各86016页、四个Client旧目标均为0；GPU租约峰值347045页/1355.64 MiB，超过旧1 GiB上限。Host最低可用156.45 MiB，说明256 MiB阶段准入门槛不等于全程强制保留；本轮无OOM。完整工作负载公共窗口749.59秒/96.95%，包含资格检查和模型加载，不代表推理计时循环精确同步。

F在四个模型命令全部派发后，经空闲Proxy串口追加一次内核/内存初始化诊断；记录在该轮lab目录的 `initialization-diagnostic.{json,log}`，纳入本轮测试条件。12次TILER_HEAP_CREATE均返回0，最后四个独立模型session全部成功；Proxy建池后可用84456 KiB，较E增加31.93 MiB。独立审计同时验证F每个Client的实际普通内存容量不低于E、Proxy增加至少30 MiB。未修改模型输入、采样次数或GPU超时阈值。

最终分析和独立审计均退出0，记录为 `build/ml-completion-20261022/{analysis-command,final-audit,continuation-f}.json`；逐一核验100份Client输出、40条数据/保留比例、31条历史值不变、九条补测、固定输入SHA、退出/健康/资源恢复、真实共享源/目标缓存及原失败证据。结果表保持仅表格。

2026-10-22已同步至[Notion多Client并行测试结果合集](https://www.notion.so/3ff659a3b8cc813bbab7c109be10ad21)的「ML / NCNN（2026-10-22 补测完成）」区。回读核对40条/205单元格与本地一致，原31条数据未变，九条补测齐全；glmark、内存表及原历史原因表原文保留，旧失败明确标记为历史。完整回读、前后比较和发布核验在 `build/ml-completion-20261022/notion-{page-after-sync.md,publication.json}`。此次同步未改运行代码，无新增性能测量。

最终Pi/RK只读资源检查退出0、无门槛问题，记录在 `build/ml-completion-20261022/final-resources.json`。两端无实验VM/刷机进程；RK无loop或测试挂载，可用内存3102.60 MiB。追加独立只读检查 `final-host-probe.json` 为PASS：Host #31、Realm能力1、pmthor、CPU0–1、GPU300MHz，gmem/租约诊断模块均已卸载。Python解析、shell语法及根仓库/Guest/OpenCCA的 `git diff --check` 通过。当前冻结包、失败证据、构建输入和固件回退备份保留，不将其作为垃圾删除。

失败的候选A及其内存准入版本B保留于 `build/ml-completion-20261022/`，不用于最终验收。提交准入候选C用于新固件720p门槛；候选D/E/F与C的内核及initrd逐字节相同，只调整显式四Client ResNet内存/启动配置，冻结于同目录 `candidate-{c,d,e,f}/`。均有输入与源码SHA清单。运行中的冻结输入不修改，不更新原发布manifest。

## 复现与证据定位

所有命令从仓库根目录执行，凭据仅通过会话环境提供。`run-realm-lease-monitor.py`加载只读租约监视器；模型的 `run-resnet.py` 还检查guest_memfd共享源/旧目标的真实缓存页。完整实际命令、退出码及前后资源见每项 `build/lab-runs/<run-id>/result.json`；回收副本见 `build/ml-completion-20261022/runs/<run-id>/`。不要复用已存在的run-id。

```bash
python3 scripts/maintenance/lab-run.py --run-id <新的ID> -- \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/ml-completion-20261022/candidate-d \
  --workload glmark --performance --benchmark-only --suite \
  --profiles attention-320 ml-attention ml-reduction ml-gemm ml-conv ml-depthwise ml-softmax \
  --clients 4 --compact-memory --pool-mib 128

python3 scripts/maintenance/lab-run.py --run-id <另一个新的ID> -- \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 build/ml-completion-20261022/run-resnet.py \
  --clients 4 --pool-mib 336 --bundle build/ml-completion-20261022/candidate-f
```

三Client模型使用同一模型命令，改为 `--clients 3 --pool-mib 384 --bundle build/ml-completion-20261022/candidate-d`；双Client功能命令在监视器后运行 `scripts/run/run-realm-xshm.py --images build/ml-completion-20261022/candidate-d --workload compute --bo-sg-mmap`。完整720p使用candidate-c、`--clients 1 --compact-memory --pool-mib 128 --client-cpu-layout round-robin --cpu-frequency-khz 1800000 --telemetry --profiles glmark-720`，其余benchmark选项同上。E内核/initrd相同，四Client模型专用的8 MiB SWIOTLB预算没有用于720p，不能把单Client门槛当成该配置的回归证明。

| 当前输入 | SHA-256 |
| --- | --- |
| Client Image | `31f31f15c148bba2194bb1ccc0335f6bdbd300729ca0278ed1431fa439420647` |
| Proxy Image | `5f8975e634d2f0dd0ae5dd6bedbf72c2a21db8655fc863b9031a50de55ad731d` |
| initrd | `2b4900453c210b4adf233210fa7fa2a947349210e640826f408664988595ad4c` |
| D runner | `bd2bcb74374e93eb10227a49a05bcbe06e402284bfbf149a62e39768b4903e32` |
| E runner | `8b64f28f6a4afc7a2dd3a61a9cc96edf1c979e76cbf68951476cdaf8b75fb0ec` |
| F runner | `c8309f3d90083a795670ae902a6e873c39f4536a27b1e61b2a4622ccfafd4e55` |
| 已验证回收版VMM | `fb2c3816d776a288d34b8c7f5b74b1e1722bb64d79079cac9c303319361310ec` |
| RMM ELF | `f0f625e3cfedc40eccd536a53cfa7df69aec55a12a0923477ee98b0efe673482` |
| SD2 u-boot.itb | `963bdff1b4eec087344d83ca8921aad5c17769f81b28a071e1523fdeb7dd2ca1` |

固件备份和部署日志在 `build/firmware-runs/ml-rmm-2g-20261022-a/`。未更换Host内核，仍为 `6.12.0-opencca-pmthor-opp3 #31`。当前运行源码及固定包与旧发布manifest不同，复现必须使用对应组合。

Native仍引用原Host #7的历史单进程结果；本轮使用Host #31、新RMM及调度/测量/内存组合，不是同期同配置Native重测。NCNN使用随机输入/权重，不证明模型准确率。单次验收不证明长期稳定性，也不把模型迭代均值解释为纯GPU服务时间。
