# 1080p 多 Client：内存分层与 GPU 租约容量

目标是在现有 RK3588 / OpenCCA 模拟平台完成真正并发的完整 1080p glmark。应用、分辨率、33 个场景和既定 validation 判据保持一致，不以失败运行的 raw score 作为成绩。

## 三个不同的容量限制

| 层级 | 原限制及现象 | 处理 |
| --- | --- | --- |
| owner 内的 BO 分配 | 必须连续，空闲足够但碎片导致大 BO 失败 | 已实现同一授权池内 SG BO，连续 GPU VA / CPU VMA |
| RMM 全局 GPU 页租约 | 131072 个独立 4 KiB 页，即 512 MiB；所有 Client 的 GPU 映射及可信 GPU 内存共用 | 候选改为 262144 页，即 1 GiB；哈希桶同步扩大一倍 |
| Realm 的 CMA 与普通内存 | 每池附加 64 MiB CMA，每个Realm还默认预留64MiB SWIOTLB；Proxy普通内存必须容纳多域GEM/页表元数据 | F候选将 CMA 额外预留改为16MiB、SWIOTLB改为16MiB；Client普通内存保留192MiB，Proxy保留192+32×N MiB；削减普通内存的D/E已因OOM撤回 |

SG 只解决碎片化，不能让实际存活 BO 超过池容量。`mc1080-sg160-1c-20261020-a` 使用旧 SG-B 内核、160 MiB 池，仍有四次 BO_CREATE ENOMEM，外层 rc1、workload125；raw929无效。Host 健康及 Realm 退出0/0、CPU/GPU恢复完成；失败诊断与 transport 清理各有一次超时，保留原 summary。完整证据已逐文件 SHA 校验回收至 `build/multiclient1080-design-20261020/runs/<run-id>/`。

## 映射拒绝的错误处理

旧三 Client 运行出现五次用户态 `VM_BIND err=62`，最初被解释为超时。Proxy 同时有五次 GPA→HPA `ret=1`，来自 RMM 的正数 RSI_ERROR_INPUT。Linux ioctl 错误必须为负 errno；正数状态向上传递后，用户态 errno 可能保留之前的等待错误。因此这不是有效的超时根因证据。

候选把正数翻译失败转换成 `-EACCES`，原始 RSI 状态仍打印在内核日志。只有确认翻译成功的 HPA 数组才能用于失败撤销，避免把尚未转换的 GPA 当成 HPA 撤销。Client / Proxy 内核构建通过，当前冻结包为 `build/multiclient1080-design-20261020/candidate-f/`，内核与 runner / initrd 的 SHA 见其中 `hashes.json`。

## 租约扩容没有放宽授权

扩大的是有限的可信元数据表。每个 HPA 仍只允许同一 Realm owner 持有，引用计数、DMA 排他、运行状态、批次失败回滚以及撤销后回收保持原检查。四个192MiB授权池合计768MiB，1GiB全局容量还为 GPU 固件、页表等留出空间；不代表任意数量 Client 无上限运行。

原有 GPU lease 单元测试使用 ASan/UBSan、`-Wall -Wextra -Werror`，在新上限下填满1GiB对应的条目，再验证溢出拒绝、批次引用回滚和清理归零，rc0。`bash scripts/check/check-rmm-xshm-events.sh`四组软件测试也全部rc0，日志为`build/multiclient1080-design-20261020/rmm-unit-tests.log`。GPU 实际占用另外通过只读状态监测模块每100ms采样；卸载时要求 GPU/DMA 最终租约和查询错误均为0。

固件使用独立构建目录，不覆盖旧回退包。首次复用旧 CMake 缓存因平台 mmap 配置冲突失败；改为独立目录后 RMM / U-Boot 构建及 ELF 装载布局检查通过。部署仍须先备份实际 SD 启动区，只写 storage ID2，不改 Host 内核/rootfs。板端验证状态以随后各 run 的结果为准，不能由编译成功推断通过。

## 验证记录

| 目的 | run-id / 输入 | 状态 |
| --- | --- | --- |
| 确认原三 Client 失败时的租约峰值 | `mc1080-3c-leases-20261021-a`，旧 SG-B 内核/旧 RMM、3×192MiB池 | FAIL/rc1；峰值130099页（508.20MiB），最终GPU/DMA租约0、查询错误0；峰值采样接近512MiB，尚不能独立证明是容量耗尽 |
| 新固件部署与Host恢复 | `mc1080-rmm1g-deploy-20261021-a` | rc0；布局PASS、SD启动区备份、storage2、Host#31/pmthor/Realm能力1及前后资源恢复 |
| 单纯削减余量的反例 | `mc1080-lean-720-20261021-d`，16MiB额外CMA/160MiB Client普通内存、仍为64MiB SWIOTLB | FAIL：validation中Client OOM两次、工作负载rc125。缺少READY时runner原会等待900秒，确认失败后只向本run的runner发送SIGINT，正常执行回收并保留KeyboardInterrupt；Realm退出0/0、Host健康与频率/CPU恢复 |
| 普通内存削减仍不足的反例 | `mc1080-lean-720-20261021-e`，16MiB SWIOTLB、160MiB Client普通内存 | FAIL/rc1：validation后段OOM，anon RSS约77MiB；新runner已提前识别屏障前退出。Realm退出0/0、Host健康/恢复、最终GPU/DMA租约0；保留transport清理异常 |
| 新内核完整720p门槛 | `mc1080-lean-720-20261021-f`，F内核 / initrd / runner、16MiB SWIOTLB、192MiB Client普通内存与1GiB租约RMM | PASS/rc0，1157分；33场景、26/1/6、clean、Host/Guest健康、退出0/0、恢复通过；峰值26559页，最终GPU/DMA0 |
| 三Client完整1080p | `mc1080-3c-20261021-f`，F+1GiB租约、3×192MiB池 | PASS/rc0；292/569/303，均分388；评分重叠96.50%，全部33场景/26/1/6/clean、Host/Guest健康、退出0/0/0/0及恢复通过 |
| 四Client完整1080p | `mc1080-4c-20261021-f`，同一F+1GiB租约、4×192MiB池 | PASS/rc0；296/280/271/260，均分276.75；评分重叠99.10%，全部33场景/26/1/6/clean、Host/Guest健康、退出0/0/0/0/0及恢复通过 |
| 最终双 Client API / compute / SG mmap | `mc1080-api-compute-20261021-f`，与最终图形相同F内核/initrd/runner及1GiB固件，正常功能内存配置 | PASS/rc0；两侧各19项API、实际计算65536元素/16样本/64 ALU、权限/IRQ、内存及SG mmap通过；Host/Guest健康、退出0/0/0、恢复及租约归零 |

完整720p对照：降低固定预留并扩大全局租约｜旧SG-A 1158 → F 1157｜−1分/−0.086%｜同128MiB池、33场景、600MHz请求/594MHz实际、null-noop/finish；RMM、内存和错误处理组合变化，仅记录组合观测｜上述F run及统一命令，外层/workload均0、SHA回收VERIFIED｜保留F继续验证多Client。Realm总配置800→704MiB（−96/−12%），Host最低MemAvailable2203.75→2354.19MiB；Client评分采样最低可用27.09MiB，CMA128KiB，未发生OOM。旧SG-A单Client1080p905、双Client597/596仍仅对应旧组合，未重测同期Native。

三Client1080p对照：解决映射容量并降低固定预留｜旧SG三ClientFAIL/无有效分数 → F 292/569/303、均分388｜旧轮失败，不计算绝对/百分比提分｜同3×192MiB池和CPU2–3固定Client预算；RMM/内存/错误处理组合变化｜上述run、完整统一命令，外层及三个workload均0，15文件SHA回收VERIFIED｜保留。RAM总配置2272→2080MiB，最低Host可用844.25MiB；三个Client评分最低可用约23.41–24.24MiB。租约峰值**141812页=553.95MiB，实际超过旧512MiB容量**，说明旧上限不足以容纳该完整负载；最终GPU/DMA租约和查询错误均0。评分重叠96.50%，全域均完成33场景；CPU固定预算使Client评分不均，不表述为纯GPU扩展效率。历史Native单进程997仅作参考，均分388保留38.92%。

四Client1080p对照：使配置通过内存准入并完成实际并发｜旧SG四Client因预算不足NOT_RUN → F 296/280/271/260、均分276.75｜旧轮未执行，不计算提分｜同192MiB池与固定CPU预算，改用F组合｜上述run及统一命令`--clients 4`，外层及四个workload均0，18文件SHA回收VERIFIED｜保留。Proxy1104MiB、四Client各400MiB，共2704MiB；Host初始可用3094.56MiB，最低采样**144.70MiB**，未发生OOM，但该板余量有限。四个Client评分最低可用约22.84–24.54MiB；GPU租约峰值192221页=750.86MiB，最终GPU/DMA租约和查询错误均0。窗口重叠99.10%，历史Native997参考保留27.76%。各并发数只有一轮F测量，未证明长期稳定性或纯GPU公平调度；未执行故障注入，也不继承其他负载的性能结论。

F新配置按每池 P MiB / N Client：Proxy RAM=N×P+208+32×N、CMA=N×P+16；Client RAM=P+208、CMA=P+16。192MiB池的四Client总配置2944→2704MiB，减少240MiB（8.15%），仍要求额外256MiB Host准入预算。BO池未减小；最终是否可用必须通过完整图形、内核健康和回收检查。`memory-info`记录各Realm绑定前后内存，评分进度记录Client可用内存与CMA余量，防止把预算推导当成通过证明。

`swiotlb=8192`按2KiB slab计为16MiB；不使用noforce，不绕过Realm共享DMA缓冲语义。GPU BO经授权池及真实GPU页表映射，不经这块Host virtio块设备bounce buffer。每Realm少48MiB固定预留，五Realm合计少240MiB；F保留Client普通内存，避免D/E的OOM。是否足够支持磁盘I/O仍通过只读rootfs的完整validation/评分和内核健康检查验证。失败用例促成runner在任一Client于评分屏障前退出时立即报错，避免继续等待不存在的READY；不改变PASS判据。生产receive函数已用独立输入验证“等待一个Client时另一Client提前失败”立即报错，正常READY仍成功，rc0。

## 复现与输入

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-lease-monitor.py \
  --monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko -- \
  python3 scripts/run/run-realm-xshm.py \
  --images build/multiclient1080-design-20261020/candidate-f \
  --workload glmark --performance --benchmark-only --suite \
  --profiles glmark-1080 --clients 3 --compact-memory --pool-mib 192
```

四Client改`--clients 4`；720p门槛改`--profiles glmark-720 --clients 1 --pool-mib 128`。功能回归使用同一F包，改为`--workload compute --bo-sg-mmap`，不加benchmark/compact参数。监测模块必须与Host模块release匹配，wrapper验证传输SHA且只在GPU/DMA租约均0时加载；该只读诊断不是GPU授权机制。

| 文件 | SHA-256 |
| --- | --- |
| F client-Image | `31f31f15c148bba2194bb1ccc0335f6bdbd300729ca0278ed1431fa439420647` |
| F proxy-Image | `f3c3f28e25617784d7d681fa6a1270b5561eaf82526e9ce41a97e9fd399103fc` |
| F initrd.cpio | `10e2721ce4a57f32a1fb10aac643cc56f41c55917e06727fd1c18916d3799e03` |
| F runner.py | `99d492e0877eb91ec322ec9c003a52149114b4307589f92c982c90d17d7698c1` |
| 新 RMM ELF | `dc755c2395a8906df651a9e51aff4ab1ee035e73a060d4a5a179addfa86ce227` |
| 新 u-boot.itb | `f063440cbf2001a056e3115a6228c4a6b949be49b3b7e769458c4ed3a533794c` |
| 新 idbloader.img | `7a69e5e3d8c95d5d7c003cf16390ebef8e4abd4c1c1991b9cc48176a2050d4af` |

固件构建/布局/部署和前启动区备份位于`build/multiclient1080-design-20261020/`及`build/firmware-runs/mc1080-rmm1g-deploy-20261021-a/`。每轮图形日志回收至前者的`runs/<run-id>/`，`collection.json`逐文件核对板端SHA；外层命令/rc和前后资源位于`build/lab-runs/<run-id>/`。监测JSON与dmesg另复制进该轮回收目录，不覆盖既有证据。

## 产物整理

F完成720p、三/四Client1080p后，清理未使用的C及被F替代的D/E共15文件、233.76MiB；F完整输入哈希在删除前后均验证一致。D/E失败的runner、串口、内核OOM、输入哈希、退出/回收和监测证据已SHA验证回收，不删除失败项。准确路径、mtime、大小、SHA及结果见`build/multiclient1080-design-20261020/cleanup-inventory-final.json`。当前F、1GiB固件、旧回退/SD启动区备份和增量构建树保留。Pi仅新增当前固件，没有本轮废弃编译树；RK按冻结输入原位同步，未新增重复内核包，运行证据保留。

最终功能回归GPU租约峰值5447页，最终GPU/DMA与查询错误均0。两侧均记录实际1MiB BO为2段，完整mmap及`bo_offset=0x7f000 size=0x2000`跨段别名检查通过。正常功能配置仍为3×768MiB、默认SWIOTLB；图形低内存配置由完整720p和三/四Client1080p分别验证。未执行GPU故障注入，provider replacement仍按runner保留NOT_RUN，不把本次结果扩展为全负载验收。Notion1080p页面已回读确认只含四列表格，旧单/双Client标注旧配置，新三/四Client均分及历史Native保留比例已写入。

收尾核验`build/multiclient1080-design-20261020/final-validation.json`为PASS：四轮最终F运行共14个Realm退出均0，8次Client完整评分/264场景全部符合判据；功能两侧各19条实际gpu-smoke调用、计算及2段别名证据一致。重新核对每轮回收文件SHA、F输入SHA、内核健康、清理结果、评分重叠和最终租约归零；全部日志未发现SWIOTLB buffer full、SWIOTLB分配失败或块设备I/O error。源码/补丁/构建组合另存`final-source-manifest.json`及`final-*.patch`，不提交日志、凭据或缓存。
