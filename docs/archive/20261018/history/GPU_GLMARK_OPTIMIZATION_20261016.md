# glmark Client/Proxy 性能定位与优化实验记录（2026-10-16）

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

最新进展：opp3 Host及原生卸载修复模块组合的**完整32项全部通过**，
run-id为`glmark-opt-20261016-opp3-regression32`，矩阵、suite及正式Guest镜像restore均退出0。
完整720p/1080p总分**1058 /847**，两项各33场景计时、严格validation无新增失败；
原生/直通项和双Client功能项均完成。最新证据及范围见本文末尾；此前“未完成”段落为历史记录。
同一Host启动、同实际594MHz的原生完整glmark新对照已完成，原生1432/997，
共享保留73.88%/84.95%。完整66场景、复测配置及剩余terrain开销见
[最终性能报告](GPU_GLMARK_PERFORMANCE_REPORT_20261016.md)。
该轮关闭了Proxy/RPC计时统计，不能把相对旧1023/841的变化全部归因于OPP实现。

## 历史定位记录（按执行顺序，保留当时的未完成状态）

此前DMA1 Host的两分辨率完整对照：并发RPC+BO操作保留的精确完成点缓存，同频594MHz完整720p **1023**、1080p **841**，
保留原生总分 **70.99% /83.76%**，相对仅并发RPC的989/804提高 **3.44% /4.60%**。
两项各33场景计时与严格validation无新增失败；新/旧策略短场景四次交替提高4.39%–7.00%。
早期全文件失效缓存几乎无命中，排除三个已审计BO操作后才获得约34%–43%的完整运行命中率。
各分辨率完整测量仅一次，部分场景仍比历史基线低约1%–2%，未完成同镜像开关复核，
缓存继续默认关闭；完整32项尚待完成。常规OPP控制Host已部署，基础调频/恢复验证通过，
同镜像缓存开关四次交替、六项同步语义、大小缓冲区计算、PFN生命周期及空闲重绑定均通过。
该新Host的完整glmark总分及完整32项仍不能沿用旧组合结果。

先前融合快照+按需等待组合1016/813虽提高总分，但effect2d定向交替确认下降6.66%，
不作为推荐配置；新完成缓存候选关闭这些参数，720p该场景748，高于仅并发基线718。
完整命令、退出码、哈希、失败/未执行边界及常规OPP候选构建见末尾。

目标是解释并消除相对原生驱动异常偏大的开销，保留 GPU 完成等待、结果验证和隔离语义。本文件记录正在进行的实验，尚不能作为优化完成或完整回归通过的结论。


早期正式共享配置的定位结论（不含页首最新缓存候选）：已确认并修复 Proxy ACK
等待路径的整 jiffy 延迟，且发现原生与pmthor 默认 GPU 频率不同。DMA1 Host 的同频 594 MHz 完整 720p
为原生 **1441**、Clientproxy **938**，分数保留率 **65.1%**；
完整 1080p 为原生 **1004**、Clientproxy **777**，分数保留率 **77.4%**。
两分辨率共享路径均无新增验证失败，另有四次冷 VM 启动、每次八轮验证无新增失败；
样本仍不能证明首次错误稳定修复，完整功能回归尚未完成。
1000/50 µs 轮询对照未产生帧率收益，默认维持 1000 µs；单 VM 强制完整缓存刷新
使 blur/terrain 帧率下降约 6%–7%，不足以解释共享路径全部差距。
合并同步快照创建与复制 RPC 的候选已通过四组合快照语义/兼容验证；
三场景两组固定 A/B 中 build 均值 +2.66%、blur +0.63%、terrain 无变化，
不足以消除剩余差距，仍默认关闭。期间修正探针误用控制机较新 DRM UAPI 的构建问题，
失败记录及修正后验证均保留。IRQ 并发 RPC 候选通过六项相关语义测试；
三场景两组固定 A/B 中 build +8.29%、blur +0.84%、terrain 无变化，
全局 RPC 锁等待统计归零；完整720p score989（较938提升5.44%，原生分数保留率68.63%），
两分辨率均33场景无新增验证失败、峰值4个活跃RPC调用；完整1080p score804（较777提升3.47%，
原生分数保留率80.08%）。候选默认关闭。已完成fence快照候选通过六组合语义验证，
但真实负载快路命中率仅约0.1%，四次A/B未证明稳定性能收益，维持关闭。
按需等待候选已通过四组合快照语义测试及四次短A/B；两次开启均无快照等待轮询，
build均值+2.03%、blur+0.62%，完整场景与更广功能验证待完成，仍默认关闭。
历史结果与失败全部保留在下文，不能称整体优化完成。

## 测量条件与历史基线

控制机 `/home/mzh/gpu`；RK3588 Host 为 `6.12.0-opencca-pmthor #10`，GPU 绑定 pmthor。用户态为 Mesa 25.0.7-2，renderer 为 Mali-G610 (Panfrost)。Client/Proxy 分别 512/384 MiB、各 1 vCPU。使用定制 glmark2 `null-noop`，`frame-end finish`，短实验分辨率为 1280×720。控制机日期为 2026-10-16，RK 时钟仍为 2026-10-15，不能直接按两机墙钟相减推算时延。

历史全场景结果见 [原生/Clientproxy 性能报告](GPU_NATIVE_CLIENTPROXY_PERFORMANCE_20261015.md)：720p score 1496/58，1080p 1161/58。该历史对比未固定频率与 CPU 亲和性，后续优化必须说明比较条件。

## 已完成的定位实验

下表每行运行同样两个短场景：`build:use-vbo=true:duration=3,desktop:effect=shadow:windows=4:duration=3`。每次仍执行完整 validation；已知 framebuffer 例外单列，不把该例外写成验证全通过。

| run-id 后缀 | 条件 | build FPS / ms | desktop FPS / ms | score | 退出码 / 结果 |
| --- | --- | --- | --- | ---: | --- |
| baseline | 原始参数，Host CPU 0–1 | 58 / 17.463 | 39 / 26.309 | 47 | 0 / PASS |
| quiet | 两侧关闭高频串口输出 | 66 / 15.299 | 45 / 22.261 | 54 | 0 / PASS |
| pinned-stats | 请求上线 0–3、分离亲和性 | 未运行 | 未运行 | — | 2 / 启动前检查失败 |
| pinned-stats-v2 | quiet；broker 0、Proxy 1、Client 2；统计开启 | 64 / 15.786 | 40 / 25.213 | 51 | 0 / PASS |
| tick1-stats | 与上一行相同，仅调度 tick 改为 1 ms | 64 / 15.828 | 41 / 24.561 | 51 | 0 / PASS |

完整 run-id 为 `glmark-opt-20261016-<后缀>`。原始日志位于控制机及 RK 运行树 `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`，包含 `result`、`client.log`、`proxy.log`、实际 VM JSON、`affinity.log`。控制机入口日志为 `build/glmark-optimization/<后缀>.log`（被 Git 忽略，不随 clone 提供）。启动前失败的原因是脚本在上线 CPU 前校验 CPU 2 的 taskset；已调整顺序，后续运行证明 CPU 0–3 上线且最终恢复 0–1。

复测命令模板：

```bash
RUN_ID=glmark-opt-20261016-pinned-stats-v2 \
GLES_QUIET_CONSOLE=1 \
GLES_GLMARK_BENCHMARKS='build:use-vbo=true:duration=3,desktop:effect=shadow:windows=4:duration=3' \
./scripts/run/run-vmshm-e2e.sh --skip-build --skip-sync --no-clean-remote-procs \
  --gles-glmark-smoke --skip-gles-remote-build \
  --gles-client-mem-mib 512 --gles-proxy-mem-mib 384 \
  --gles-host-online-cpus 0-3 --gles-broker-cpus 0 \
  --gles-proxy-cpus 1 --gles-client-cpus 2 --gles-proxy-panthor-stats
```

`tick1-stats` 另加 `--gles-panthor-sched-tick-ms 1`。baseline 不设置 quiet、亲和性、上线 CPU 和统计；quiet 使用临时脚本提前降低 Proxy loglevel，最终 runner 已提供相同用途的 console 控制。

## 当前证据与候选修复

降低串口日志只改善约 14%–15%，不足以解释原生差距。分离 CPU 和缩短调度周期没有消除问题。

`pinned-stats-v2` 的 GPU IRQ raw→thread 平均 15.940 µs；普通 RPC 多为几十至几百微秒。779 次 `run_job` 共耗时 5.684 s，其中等待 `sched->lock` 为 5.678 s，平均约 7.29 ms/次。`tick1-stats` 的同一锁等待仍为 5.691 s/787 次。统计包含 validation 和两个短 benchmark，不能据此直接声称每一场景的锁等待相同。

Guest 的 `panthor_fw_wait_acks()` 在确认未就绪时调用 `wait_event_timeout(*wq, false, 1)`：条件恒为假，收到中断也不能提前返回，而是等待一整个 jiffy 后再检查 ACK。配置 `CONFIG_HZ=250`，一个 tick 为 4 ms。调度器在等待固件 ACK 时可能持有 `sched->lock`，因此固件确认的延迟会传递到提交路径。这与原生 Host 驱动的“短轮询 + 按 ACK 条件唤醒”不同。

候选修复恢复 10 µs 有界轮询和真实 ACK 条件等待；每次读 ACK 仍调用 Realm shared-interface 同步函数。保留原有 timeout 和最终确认、失败 ACK 位计算，不提前报告作业完成，不删除 fence 等待。下文同工具链控制实验与锁等待统计已验证它是主要瓶颈；剩余开销需要分频率和逐场景比较。

同时修复运行脚本已声明但未传入 VM 的调度/统计参数，增加 per-run Proxy 控制台采集统计，避免在热路径同步打印所有日志。默认保留原始日志行为，诊断运行显式设置 `GLES_QUIET_CONSOLE=1`。

## 当前进度与剩余工作

ACK 修复已构建并部署，完成同工具链未修复对照、198 MHz 两种分辨率完整测试，以及同步/Group/双 Client 的受影响功能验证。同频完整 720p 为共享 914 / 原生 1432；同频 1080p 因新增验证失败未进入 benchmark。相同诊断 ELF 的固定 8 轮对照中，原生新增失败 0，未修复共享新增 1，优化共享新增 2；详见末尾统计。当前继续定位正确性问题，不宣布优化完成或本轮完整 32 项回归通过。

### 构建记录

控制机安装了交叉构建依赖，当前编译器为 `aarch64-linux-gnu-gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0`。发布镜像配置记录的原编译器为 GCC 11.4，因此不能只将新镜像与旧镜像对比就排除编译器影响。

`JOBS=12 ./scripts/build/build-verified-kernels.sh proxy` 首次退出码 2：固定配置引用 `/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin`，控制机没有该文件。没有修改配置或换用新固件；将仓库 `GPU-SFTP/panthor_fw/mali_csffw.bin` 复制到本地构建固件树，SHA-256 为 `43c3c36b914c031d88ae152fd89019d8f99ad41d9879fb5ab7496ed13f7b378b`，以下命令继续构建：

```bash
make -C Linux-Guest-GPU O=/home/mzh/gpu/build/verified-kernels/proxy \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/glmark-optimization/firmware \
  -j12 Image
```

构建日志分别为 `build/glmark-optimization/build-proxy-ackfix.log`、`build-proxy-ackfix-resume.log`。候选构建只改变 Proxy，不更新 Host 固件或刷写 SD。

## 候选修复的初步硬件结果

候选与未修复对照均由 GCC 15.2、同一配置、同一固定固件构建。只恢复未修复的 `panthor_fw.c` 重建对照镜像，随后还原候选源码，没有改变其他 Guest 源码。

| run-id 后缀 | build FPS / ms | desktop FPS / ms | validation 成功/失败/无判据 | 实际结论 |
| --- | --- | --- | --- | --- |
| ackfix-stats | 958 / 1.045 | 441 / 2.270 | 24/3/6 | 脚本 rc=0，但有两项新增失败，正确性不接受 |
| control-stats | 64 / 15.715 | 43 / 23.347 | 26/1/6 | 同工具链未修复对照，rc=0 |
| ackfix-strict | 未运行 | 未运行 | 26/1/6 | rc=1；临时开启 debug 改变日志格式，首次严格解析器误把已知失败计为新增失败 |
| ackfix-strict-v2 | 959 / 1.043 | 440 / 2.273 | 26/1/6 | rc=0；恢复普通验证日志，严格规则判新增失败=0 |

`ackfix-stats` 的 5867 次 run_job 总锁等待为 25.998 ms，平均 4.43 µs；同工具链 `control-stats` 的 800 次为 5.657 s，平均 7.071 ms。前者包含更多完成的帧，不能直接比较累计时间；按调用归一化后仍能清楚确认等待路径的差异。

第一轮额外失败为 `texture-filter=nearest` 和 effect2d 的边缘检测 kernel，原因尚未解释，保留为风险。后续 debug 及正常严格复测未再出现，不能用后续通过覆盖第一轮失败，也不能声称已经排除偶发正确性问题。

发现原 gpu-smoke.sh 只要求 validation 成功至少 20 项、失败不超过 4 项，会掩盖新增失败。现改为仅豁免完整匹配的 `[function] fragment-complexity=medium:fragment-steps=5` 已知失败，其他验证失败一律使测试失败；发生失败时额外运行 debug 采集参考/实际像素，但诊断重跑不能改变原始失败判定。3 组最小输入检查验证了“已知失败=0 新增”“已知+texture=1 新增”“无失败=0 新增”的解析，shell 语法检查通过。

镜像 SHA-256：

- 原发布 Proxy：`24e213e91b4ecc2ce2c4e6dece0b1bad15d445d3b7207e8701f4f70da5922b55`。
- 同工具链未修复 Proxy：`b927618d0ad6d660f3d1ac84d69f6bd6a82972a6b6922601692b0beefd2a4467`。
- 候选修复 Proxy：`e83f011122e8107860a3000a96b8f522bcbed59c2c99395a7dbe02ebf6ec9ca8`，部署前本地与 RK 校验一致。
- Client 保持原发布镜像：`e797e3180e65407eecb5cfed894725f9e5f8b31f822f1089feb38a820062e68f`。

### 另一个待控制变量：GPU 频率

完整 720p 测量期间，从 Host debugfs 读到实际 `clk_gpu` / `clk_gpu_src` 为 198 MHz。`pmthor_clk_init()` 只获取并启用时钟，没有原生 Panthor 的 OPP/devfreq 初始化。原生 Panthor 则使用 OPP 和 simple_ondemand 调频；历史日志还出现过切换驱动后 pmthor 继承 300/396 MHz 的记录。因此驱动切换顺序和频率可能影响旧性能对比。尚未用本轮原生实测证明影响大小，不能将全部差距归为代理开销，也不能仅按频率比例外推性能。

## 完整场景与受影响功能验证（候选修复，198 MHz）

两次完整测试都不设置 `GLES_GLMARK_BENCHMARKS`，保留默认 33 场景、finish、完整 validation，其他参数与 pinned-stats-v2 相同。

| run-id 后缀 | 分辨率 / 内容 | score | validation 成功/已知失败/无判据 | 新增验证失败 | 退出码 / 结论 |
| --- | --- | ---: | --- | ---: | --- |
| ackfix-full720 | 1280×720，33 场景 | 618 | 26/1/6 | 0 | 0 / PASS（含明确例外） |
| ackfix-full1080 | 1920×1080，33 场景 | 408 | 26/1/6 | 0 | 0 / PASS（含明确例外） |
| ackfix-2cpu | 双核默认放置，两个短场景 | 472 | 26/1/6 | 0 | 0 / PASS（含明确例外） |
| sync-snapshot | sync_file snapshot/export/import 生命周期 | — | 不适用 | 不适用 | 0 / SYNC_FILE_SNAPSHOT_PASS |
| two-client | 两 Client 各 4 MiB Compute，100 次 + 5 预热 | — | 两侧 COMPUTE_CHECK=PASS | 不适用 | 0 / GLES_PASS |

`ackfix-2cpu` 的短场景为 596 FPS / 1.679 ms 和 350 FPS / 2.864 ms；与分离 CPU 的 959 / 440 FPS 相比，说明主等待修复后 CPU 超配又成为可见影响因素。score 472 为两个短场景分数，不能与全场景 score 618 比较。

完整 720p 的 terrain 为 30 FPS / 33.454 ms，1080p 为 22 FPS / 45.966 ms。历史未修复 Clientproxy 为 2 FPS / 551.373 ms 和 2 FPS / 538.810 ms。全场景分数相对历史的提升约为 10.66 倍和 7.03 倍；CPU 放置、串口设置等不同，不能把这些总提升全部当作单行补丁的独立效果，独立效果应看同工具链控制实验。

单 Client 日志仍位于 `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`；双 Client 日志位于 `GPU-SFTP/log/shared/vmshm-2client/glmark-opt-20261016-two-client/`。各命令外层退出码记录在 `build/glmark-optimization/<后缀>.status`。两侧 Client 镜像未更换，未运行新版本全 32 项矩阵，不沿用历史 32/32 作为本轮证明。

### 可移植构建入口与后续同频实验

已修复 `scripts/build/build-verified-kernels.sh`：Guest 构建自动从固定运行树复制同一份 Mali 固件到构建目录，并将该目录作为 Make 参数传入，不再要求控制机预装 `/usr/lib/firmware/...`。随后 `JOBS=12 ./scripts/build/build-verified-kernels.sh proxy` 实际构建退出码为 0，固件哈希一致。该复核产物另存为 `proxy-portable-build.Image`；为保持后续对照只改变 GPU 频率，运行树恢复为已测过的 `e83f...` 候选镜像。

Group 有效期限探针首次以非可执行辅助脚本直接启动，控制机退出码 126、未启动 VM；改为 `bash` 执行的 `glmark-opt-20261016-group-deadline-v2` 退出码 0、RESULT: PASS。其辅助程序只修正过期的绝对期限，不能覆盖原始固定探针失败记录。

## 同频对照：实际 594 MHz（进行中）

原生 run-id 为 `glmark-opt-20261016-native-600`，RK 命令：
`bash /root/GPU-SFTP/log/native-glmark-optimization.sh glmark-opt-20261016-native-600`。
辅助脚本保存在控制机 `build/glmark-optimization/native-glmark.sh`，SHA-256
`a38ef1f0d937256d295bcab0df4876f295dc48571f47fe49082dfd534d0b6bd1`。
CPU 上线 0–3，工作负载固定 CPU 2，使用相同 rootfs 的 glmark ELF、库和数据。
原生 devfreq 设置 userspace，min/max/target 均为 600 MHz OPP；两个 profile
全程采样的实际 clk_gpu 都为 594 MHz，电压 675 mV。glmark ELF SHA-256 为
`2251afb6b792c08181e14205756a29c13f8dd15d5a3eb8ab6652efe55a65bb2c`。

| 原生 profile | benchmark 场景 | score | validation 成功/已知失败/无判据 | 新增失败 | profile 退出码 |
| --- | ---: | ---: | --- | ---: | ---: |
| 1280×720 | 33 | 1432 | 26/1/6 | 0 | 0 |
| 1920×1080 | 33 | 1002 | 26/1/6 | 0 | 0 |

两项负载本身通过，但原生脚本第一次卸载自己的 rootfs 挂载返回 busy，
**整体退出码为 90，不能记整体 PASS**。随后检查未发现用户进程持有这些挂载，
只重试本次 dev/rootfs 的普通 umount 成功，loop 已释放，日志保留在
`build/glmark-optimization/native-cleanup-retry.log`。没有执行已知有 Oops 风险的
Panthor 工作后解绑；保存证据并 sync 后通过 SysRq 重启恢复 pmthor。
重启后的 boot-id 为 `b31022ac-f5d0-4200-b837-742356f9e853`。
原生完整证据已保存到控制机
`GPU-SFTP/log/glmark-optimization/glmark-opt-20261016-native-600/`，含每个 profile
的日志、退出码、时钟采样、dmesg 和原始整体 exit-code=90。

共享模式同频诊断使用标准 regulator/OPP 接口，将 GPU 从实际 198 MHz 调到
594 MHz，读回电压同为 675 mV。模块只允许空闲 pmthor 加载，不直接写 PLL；
当时源代码及复现说明位于 `GPU-SFTP/tests/pmthor-fixed-opp/`（2026-10-18已因正式devfreq替代而移除，历史源码核对见[归档说明](../README.md)）。其源 SHA-256 为
`4421730641cbec59ef71bfa2780397975f061694810184cfd9333bec7f10f992`。
使用固定 Host 配置准备 headers、CONFIG_MODVERSIONS=n；初次构建在缺少完整
Module.symvers 的情况下显式允许 modpost 警告，板端加载器实际解析符号成功，
加载退出码 0。此实验例外不是其他内核兼容性或安全性的保证。

模块保留资源直到重启，不支持卸载或本次启动内切换 GPU 驱动；它是固定频率
诊断工具，**不是已经完成的生产 devfreq/热管理支持**。原生和共享的 Host Image
未替换，也未刷写 SD。共享继续使用已测 e83f... Proxy 镜像，仅改变实际时钟。

`glmark-opt-20261016-ackfix-600-stats` 短测退出码 0，validation 26/1/6，新增失败 0。
两个短场景为 build 1285 FPS / 0.779 ms、desktop shadow 635 FPS / 1.575 ms，
相比相同配置 198 MHz 的 959/440 FPS 分别提高 34.0%/44.3%。两个场景 score=959，
不能与全场景 score 比较。命令和日志仍为
`build/glmark-optimization/ackfix-600-stats.{command,log,status}` 及单 Client run-id 目录。

共享同频 720p 已完成，1080p 被新增验证失败拦截，详见后文；不按频率比推算未测结果。

### 720p：同频完整 33 场景结果

`glmark-opt-20261016-ackfix-600-full720` 退出码 0，RESULT: PASS，score **914**。
validation 26 成功 / 1 已知失败 / 6 无判据，新增失败 0；实际 GPU 采样均为
594 MHz。命令为 `bash build/glmark-optimization/run-full600.sh ackfix-600-full720 1280x720`，
其内部实际 runner 命令记录在 `build/glmark-optimization/ackfix-600-full720.command`。

相对原生 score 1432，score 保留率 **63.8%**；33 场景 FPS 比值的几何平均
**68.5%**，新增帧时间中位数 **0.301 ms**，帧时间开销中位数 **52.5%**。
score 比值不是逐帧时间比，也不是所有场景开销一致。固定频率后仍有明显
差距，不能将当前结果描述为接近零开销。

以下均为本轮同一实际 GPU 频率；每个场景只有一次完整运行，尚无多次重复
的置信区间。负载为 null-noop/finish，不代表屏幕呈现 FPS。

| 场景 | 原生 FPS / ms | Clientproxy FPS / ms | FPS 保留率 | 帧时间开销 |
| --- | ---: | ---: | ---: | ---: |
| [build] use-vbo=false: | 979 / 1.022 | 897 / 1.116 | 91.6% | +9.2% |
| [build] use-vbo=true: | 2281 / 0.439 | 1279 / 0.782 | 56.1% | +78.1% |
| [texture] texture-filter=nearest: | 2310 / 0.433 | 1277 / 0.784 | 55.3% | +81.1% |
| [texture] texture-filter=linear: | 2316 / 0.432 | 1276 / 0.784 | 55.1% | +81.5% |
| [texture] texture-filter=mipmap: | 2290 / 0.437 | 1275 / 0.785 | 55.7% | +79.6% |
| [shading] shading=gouraud: | 1913 / 0.523 | 1224 / 0.817 | 64.0% | +56.2% |
| [shading] shading=blinn-phong-inf: | 1880 / 0.532 | 1212 / 0.825 | 64.5% | +55.1% |
| [shading] shading=phong: | 1713 / 0.584 | 1152 / 0.869 | 67.3% | +48.8% |
| [shading] shading=cel: | 1707 / 0.586 | 1149 / 0.871 | 67.3% | +48.6% |
| [bump] bump-render=high-poly: | 1073 / 0.932 | 931 / 1.075 | 86.8% | +15.3% |
| [bump] bump-render=normals: | 2589 / 0.386 | 1301 / 0.769 | 50.3% | +99.2% |
| [bump] bump-render=height: | 2446 / 0.409 | 1278 / 0.783 | 52.2% | +91.4% |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0;: | 1761 / 0.568 | 1181 / 0.847 | 67.1% | +49.1% |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;: | 824 / 1.214 | 710 / 1.409 | 86.2% | +16.1% |
| [pulsar] light=false:quads=5:texture=false: | 1661 / 0.602 | 1089 / 0.918 | 65.6% | +52.5% |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4: | 383 / 2.614 | 232 / 4.315 | 60.6% | +65.1% |
| [desktop] effect=shadow:windows=4: | 844 / 1.186 | 639 / 1.565 | 75.7% | +32.0% |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 47 / 21.300 | 46 / 22.107 | 97.9% | +3.8% |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata: | 47 / 21.362 | 46 / 22.171 | 97.9% | +3.8% |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 66 / 15.256 | 65 / 15.553 | 98.5% | +1.9% |
| [ideas] speed=duration: | 481 / 2.082 | 389 / 2.577 | 80.9% | +23.8% |
| [jellyfish] <default>: | 1217 / 0.822 | 969 / 1.032 | 79.6% | +25.5% |
| [terrain] <default>: | 77 / 13.058 | 48 / 21.067 | 62.3% | +61.3% |
| [shadow] <default>: | 985 / 1.016 | 691 / 1.448 | 70.2% | +42.5% |
| [refract] <default>: | 196 / 5.112 | 153 / 6.541 | 78.1% | +28.0% |
| [conditionals] fragment-steps=0:vertex-steps=0: | 1978 / 0.506 | 1234 / 0.811 | 62.4% | +60.3% |
| [conditionals] fragment-steps=5:vertex-steps=0: | 1859 / 0.538 | 1205 / 0.830 | 64.8% | +54.3% |
| [conditionals] fragment-steps=0:vertex-steps=5: | 1976 / 0.506 | 1240 / 0.807 | 62.8% | +59.5% |
| [function] fragment-complexity=low:fragment-steps=5: | 1976 / 0.506 | 1241 / 0.806 | 62.8% | +59.3% |
| [function] fragment-complexity=medium:fragment-steps=5: | 1745 / 0.573 | 1157 / 0.865 | 66.3% | +51.0% |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5: | 1972 / 0.507 | 1242 / 0.805 | 63.0% | +58.8% |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5: | 1972 / 0.507 | 1242 / 0.806 | 63.0% | +59.0% |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5: | 1738 / 0.576 | 1154 / 0.867 | 66.4% | +50.5% |

较轻的纹理、shading、conditionals 等场景多出约 0.28–0.38 ms，支持固定
提交/同步成本在短帧中占比更高的解释；不能仅按 GPU 频率解释剩余差距。
但 terrain 多出 **8.009 ms**，desktop blur 多出 **1.701 ms**，也不能用统一
0.3 ms 常数解释所有场景。buffer 三场景的帧时间增加约 1.9%–3.8%，本身
并不能证明计算密集场景均接近原生。

源码还显示 `panthor_client_sync_fence_work()` 在快照尚未完成时，先做
非阻塞 RPC 检查，再在 RPC 锁外 `usleep_range(1000, 2000)`，而每次导出
sync_file 会建立私有快照并发起 create/transfer/wait/destroy 操作。
这是合理的死锁规避与快照生命周期机制，但可能为较长任务引入完成通知
延迟及额外 RPC。**目前是待量化的下一定位方向，不是已证明的 terrain 根因**；
后续优化必须保留导出时 fence 的快照、pending import 立即替换、源对象
reset/destroy 后的有效性，以及禁止持共享 RPC 锁阻塞等待的语义。

### 1080p 同频测试被新增验证失败拦截

`glmark-opt-20261016-ackfix-600-full1080` **退出码 1 / FAIL**。在 benchmark
开始之前，validation 得到 25 成功 / 2 失败 / 6 无判据，其中除已知 function
以外，新增 effect2d 的 `kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;` 模糊场景失败。
新增失败数为 1，Guest `GPU_SMOKE_RESULT=FAIL rc=125`；**没有有效 1080p 分数**。
随后自动 debug 诊断只出现已知 function 的 `Expected=0xff5e5e5e,
Actual=0xff474747`，未复现新增失败。它不能覆盖首次失败，也不能代表问题已解决。
原始非 debug 运行没有输出失败像素，这是当前诊断证据的缺口。

停止直接补跑性能，先将 Proxy 切到同 GCC 15.2 的未修复控制镜像 b927...，
保持实际 594 MHz，执行 `bash build/glmark-optimization/run-short.sh control-600-strict`。
该控制 run 退出码 0，validation 26/1/6、新增失败 0，两个短场景 score=52。
单次控制通过不足以排除原有偶发问题，更不足以证明 ACK 修复就是原因。
目前 1080p 同频比较未完成，偶发正确性问题仍为优化验收的阻塞项。

### 固定 8 轮诊断：未修复控制也存在新增失败

为采集原始失败像素，使用固定归档的 glmark 源码制作独立诊断版本：成功
路径不启用 debug；验证已经判定失败后将源文件、期望像素、实际像素和
距离写入 `/tmp/glmark-validation-pixels.log`，8 轮完成后打印。`main()` 在
**同一进程/GL context 内**执行 8 次原验证流程，不是 8 次冷 VM 启动。
shader、参考值、容差和验证返回值未修改；诊断版时间不计正式性能。
诊断 ELF SHA-256：`fdc4dd2ccc67ae3698145a201dfb9b11c71396c652e58d5c7c6064ad2bcfd2e3`。
本地源码：`build/glmark-optimization/glmark-pixel-source/`，改动文件哈希在
`glmark-pixel-source-changes.sha256`，构建日志在同一 build 父目录。

`glmark-opt-20261016-control-600-pixel8` 使用同 GCC 未修复 b927... Proxy、
实际 594 MHz、原 Client：**退出码 1 / FAIL**。原始 8 轮合计 207 成功、
9 失败、48 无判据，其中已知 function 失败 8 次，新增 nearest 失败 1 次，
发生在第 1 轮；第 2–8 轮只有已知失败。nearest 原始像素证据：

```text
Expected: 0xff282a2b Actual: 0xff2e2e2e Distance: 7.810250
```

按 RGBA 解码，期望 RGB=(43,42,40)，实际=(46,46,46)，不是只有已知 function
的同一数值偏差。该失败证明未修复路径也会出现此类现象，**不能归因于 ACK
修复独有，也不能据此认定候选没有问题**。原始 8 轮与后续自动 debug 重跑
分开统计；机器可读摘要为 `build/glmark-optimization/control-600-pixel8-validation.json`。
候选 `glmark-opt-20261016-ackfix-600-pixel8` 也已结束，退出码 1 / FAIL：
原始 8 轮为 206 成功 / 10 失败 / 48 无判据，已知 function 8 次，新增 2 次，
都在第 1 轮。nearest 的期望/实际像素与控制镜像完全相同；另一次为 desktop
shadow，期望 `0xff0d271f`、实际 `0xff319a79`、距离 150.402793。其余第 2–8 轮
只有已知 function 失败。摘要为 `build/glmark-optimization/ackfix-600-pixel8-validation.json`。
两轮诊断均严格保留 FAIL，没有使用后续 debug 运行改写结果。

诊断 ELF 是重新构建的版本，还改变了验证重复方式，因此控制镜像上出现
失败只能直接证明“该诊断条件下未修复路径也失败”，不能替代原始 ELF 的
未修复对照，更不能断言已定位根因。为了排除诊断程序/原生渲染也具有该现象，
接下来用同一个诊断 ELF 做原生 8 轮对照。运行树 artifacts 的 glmark 已恢复
原始 SHA `2251afb6...`，当前 Client Image 仍为原始版本，Proxy 恢复为 e83f...。
诊断固定 OPP 模块通过受控重启移除；原生对照将使用原生 devfreq 固定同一 OPP。

诊断构建第一段为 CPU 0 上的 j2 编译，主动停止后增量恢复；尝试上线 CPU4
返回 I/O error（Host `CPU4: failed to come online`），该恢复阶段 rc=1、没有启动
VM，CPU 在线仍为 0–1。随后仅使用已支持的 CPU 0–3，最终构建 rc=0，并恢复
0–1；诊断 GPU 测试由 runner 重新上线 0–3。上述构建/环境失败保留在
`glmark-pixel-build*.log`，不能计作 GPU 验证通过。

### 另一个明确的性能差异：flush-ID 映射

Client 的 `panthor_client_mmap_flush_id()` 提供零初始化的只读软件页，提交
时透传该值到 Proxy 的 `latest_flush`。UAPI `drm_panthor_queue_submit.latest_flush`
的说明明确规定 **0 表示无条件 flush**；调度器确实在用户命令流前生成
`FLUSH_CACHE2.clean_inv_all` 和 WAIT。因此零值不是跳过刷新或已经发现的
正确性漏洞；它是保守但可能增加成本的行为。原生用户态可读取真实 GPU
flush-ID，以消除已经不再需要的刷新。

这提供一个后续性能定位方向：量化无条件刷新对各场景的成本，再考虑可信、
保守的 flush-ID 发布。不能简单在 Proxy 提交时用“当前硬件 ID”替换用户构建
命令流时的 ID，也不能随便改成非零常数；优化必须处理 CPU 写入与刷新先后、
GPU reset 和计数回绕，否则可能错误省略必要的 cache flush。当前未修改此路径，
没有将其成本或正确性影响写成已验证结论。

### 原生使用同一诊断 ELF 的 8 轮对照

run-id：`glmark-opt-20261016-native-pixel8`。RK 命令：
`bash /root/GPU-SFTP/log/native-pixel8.sh glmark-opt-20261016-native-pixel8`，
控制脚本源在 `build/glmark-optimization/native-pixel8.sh`。保持原生实际 594 MHz、
CPU 0–3 在线、进程 CPU 2；相同诊断 ELF fdc4...、相同数据和 gpu-smoke.sh。
**profile 退出码 0，整体退出码 0**；清理中的瞬时 umount busy 在有限重试内
恢复，没有解绑工作后的 Panthor。

| 相同诊断 ELF，8 轮同进程验证 | 成功 | 已知 function 失败 | 新增失败 | 无判据 | 整体退出码 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原生 native-pixel8 | 208 | 8 | 0 | 48 | 0 |
| 未修复共享 control-600-pixel8 | 207 | 8 | 1（nearest，第 1 轮） | 48 | 1 |
| 优化共享 ackfix-600-pixel8 | 206 | 8 | 2（nearest、desktop shadow，第 1 轮） | 48 | 1 |

每次都是固定 8 轮，失败没有提前缩减统计，自动 debug 重跑不计入本表。
原生全部 8 轮都仅出现已知 function 数值差异，nearest/desktop 未失败。
该对照使问题更指向共享路径；仍不能证明具体缓存或 fence 根因，也不能用
样本 1/8、2/8 推断稳定发生率或证明 ACK 修复提高了失败概率。
原生短 benchmark 只用于完成 harness，不参与前面的正式 score 比较。

原生证据已保存到控制机 `GPU-SFTP/log/glmark-optimization/glmark-opt-20261016-native-pixel8/`，
含原始日志、逐项/整体退出码、相同 ELF/脚本哈希和时钟采样；解析摘要在
`build/glmark-optimization/native-pixel8-validation.json`。

### 阶段结论与下一验收条件

本轮已经证明并修复固件 ACK 等待的主要阻塞，且实测确认 pmthor 的低频配置
显著影响性能。原始 ELF 的完整 720p 同频结果为 **914 / 原生 1432**，仍存在
明显的提交/同步/缓存刷新成本。**1080p 同频性能未完成，优化验收未完成**。
原有共享路径的首次验证问题需要先定位，后续不得通过放宽容差、扩大豁免、
跳过验证或仅重跑到通过来获得性能结论。

下一步应围绕首轮/后续轮差异，检查共享 payload 的 Host/Client/Proxy 缓存
属性、首次页分配与 DMA 可见性、BO 生命周期和 fence 发布顺序，并使用上述
原始失败像素、相同 ELF 的原生/未修复/优化对照验证假设。当前只发现 PFN
保活路径，尚未证明其是否缺少必要 DMA 缓存维护，不能先写成根因。正确性
恢复后，再量化非阻塞快照轮询与无条件 GPU flush 的独立成本，完成两种
分辨率的同频完整对照，最后按修改范围重跑功能回归。

本阶段结束时已恢复板端原始 glmark artifact（SHA `2251afb6...`）、原始 Client
镜像和已测 ACK 候选 Proxy（SHA `e83f0111...`）；诊断 ELF 仅保留在日志目录。
原生验证完成后保存证据、释放自己的挂载并 sync，通过 SysRq 重启恢复 pmthor，
未做 Panthor 工作后解绑。最终 boot-id：`c4a2f506-7f4f-4b9c-ac62-0eb5cbecec9c`；
CPU 0–1、GPU 实际 198 MHz、固定 OPP 模块不存在，无 firecracker/broker、无 loop
残留。状态证据：`build/glmark-optimization/after-pixel8-final-state.txt`。
Host Image、Host 源码与 SD 固件未修改。shell 语法、主仓库及 Guest diff 检查通过。
源码、可复现诊断工具和文档均未提交/推送。

## 后续定位：Host 首次分配与 shader cache 对照

本阶段开始确认 Host 仍为 pmthor、CPU 0–1、boot-id c4a2...，没有 VM/broker
或 loop 残留。重新加载相同的实验固定 OPP 模块，读回实际 594 MHz。
使用相同诊断 ELF fdc4...，固定 8 轮验证，不改变参考像素或容差。

在启动任何 VM 之前，仅对本 run broker 新建的 vmshm-object memfd 做处理。
实验工具验证 broker 进程名、memfd 名和准确大小，通过 `/proc/<pid>/fd`
打开该 memfd。两种处理都写零预分配整个 512 MiB；clean 另对每条 64 B
cache line 执行 Host `DC CIVAC`，最后 `DSB SY`。工具先用自己的匿名 8 KiB
映射做指令/内容自检，退出码 0；随后 Werror 构建通过。它不操作活跃 GPU
缓冲区，不修改 Host 内核，不能当作已实施的生产修复。

| run-id 后缀 | 唯一实验变化 | 8 轮成功/已知失败/无判据 | 新增失败 | 退出码 |
| --- | --- | --- | ---: | ---: |
| cache-none-pixel8 | 不预处理 | 208/8/48 | 0 | 0 |
| cache-prefault-pixel8 | 启动 VM 前写零预分配 512 MiB | 208/8/48 | 0 | 0 |
| cache-clean-pixel8 | 预分配后清理 Host 缓存至 PoC | 208/8/48 | 0 | 0 |
| cacheoff-pixel8 | 不预处理；仅 export MESA_SHADER_CACHE_DISABLE=true | 208/8/48 | 0 | 0 |

完整 run-id 前缀仍为 `glmark-opt-20261016-`，各退出码在
`build/glmark-optimization/<后缀>.status`，run 目录包含 payload-prepare.log（如适用）。
汇总为 `build/glmark-optimization/cache-experiment-results.json`。工具源、二进制、
原始/修正构建日志、自检日志和仅用于实验的 runner 副本保留在相同 build 目录。
初版工具出现编译警告，已修正并用 `-Wall -Wextra -Werror` 重建；未将警告隐藏。

**四组都没有复现新增失败，不能宣称预分配、缓存清理或禁用 shader cache
修好了问题。** KVM 源码在安装 cacheable CPU Stage-2 PTE 前已有 CMO；
因此“所有共享页面首次分配都完全没有缓存维护”的推断不成立。GPU 原始 HPA
路径与只供 GPU 使用的页面仍值得审计，但当前证据不足以改 Host DMA 逻辑。
原始 glmark artifact 已恢复 2251...，诊断数据不作为性能分数。

## 后续性能实验：可调 sync-file 轮询（尚未验收）

为量化快照 worker 的固定睡眠开销，Client 增加只读启动参数
`panthor_client.sync_file_poll_us`，范围 50–10000 µs，默认 **1000 µs**，保留
原来的 1–2 ms 行为。仅调整非阻塞检查失败后、RPC 锁外的 sleep 范围，
保持 60 秒上限、快照不可变语义、pending import 和最终 fence 结果。

同时增加只读 `sync_file_wait_stats`：累计 waits、polls、worker 等待时间、
errors。等待时间不包含 worker 开始执行前的排队时间；不能当作完整导出
时延。gpu-smoke 在结束时采集统计，runner 通过
`GLES_CLIENT_SYNC_FILE_POLL_US` 校验并转发启动参数。
计划用同一新 Client 二进制分别测默认 1000 µs 和 50 µs，对比 terrain、
desktop blur、build 的帧时间、重试数和 CPU 成本；尚未用未测结果声称优化。


## 可调轮询：构建与首轮硬件证据

新 Client 构建退出码 0，日志 `build/glmark-optimization/build-client-poll.log`。
Image SHA-256：`cadce91888406da32d2b04906deb24f93792de0141e4c5a03572c3e32120007b`。
板端 Image 和 gpu-smoke 脚本部署后逐项校验一致；Proxy 仍为 e83f...，原始
性能 glmark 仍为 2251...。Host boot-id c4a2...，加载实验 OPP 模块后实测
594 MHz。两组均为 CPU 0–3、broker 0、Proxy 1、Client 2、quiet console，
计划测 build VBO、desktop blur、terrain 各 5 秒，验证失败后均未执行性能场景。

| run-id 后缀 | poll 参数 | 验证成功/失败/无判据 | 新增失败场景 | 外层退出码 | 性能分数 |
| --- | ---: | --- | --- | ---: | --- |
| poll1000-three | 1000 µs | 25/2/6 | desktop shadow | 1 | 未执行 |
| poll50-three | 50 µs | 25/2/6 | texture mipmap | 1 | 未执行 |

每组还包含已知 function medium 失败，新增失败均为 1；诊断重跑未复现新增
失败，不覆盖原始 FAIL。没有降低容差、增加豁免或跳过验证。
快照 worker 结束统计分别为：

- 1000 µs：waits=66，polls=97，total_wait_ns=89392871，errors=0。
- 50 µs：waits=66，polls=93，total_wait_ns=34443296，errors=0。

这些累计值来自各自验证及失败诊断阶段，场景运行并不构成有效性能配对，
不能据此宣称 FPS 提升或 CPU 成本降低；errors=0 也不能证明像素正确。
命令、退出码和镜像身份见 `build/glmark-optimization/<后缀>.{command,status,images.sha256}`；
原始 client/proxy/config/result 日志见同名 run-id 的单 Client 证据目录。

新 Client 的快照生命周期测试：`poll50-snapshot` 外层 rc=0，128 exports，
source reset/destroy/DRM close 均 PASS，但检查启动命令后发现 IOCTL 路径
没有转发该参数，实际测试的是默认 1000 µs。此记录保留，不能称其覆盖 50 µs。
runner 已把参数校验/生成提取为共用函数并用于 IOCTL 与 GLES 配置；
`poll50-snapshot-v2` 的实际 boot_args 明确包含
`panthor_client.sync_file_poll_us=50`，外层 rc=0，
`PANTHOR_SYNC_FILE_SNAPSHOT_SMOKE=PASS exports=128 source_reset=1 source_destroy=1 drm_close=1`，
`PANTHOR_IOCTL_SMOKE=SYNC_FILE_SNAPSHOT_PASS`。没有据此宣称全 32 项通过。

下一项诊断保留原始失败判定，在已发现失败后对同一像素额外执行 glFinish
读回及等待 1 ms 后再次 glFinish 读回，不重绘、不修改首次像素或参考值。
用于区分读回延迟与持续渲染错误；该诊断程序的帧率不计入性能报告。


## 同像素重复读回：两种轮询间隔均复现首轮错误

诊断 ELF SHA-256：`e586cb078161629b5460273f97aff6e6fe7c5481dafefb1cbb0d396b14aa1bdd`。
从前一版 fdc4... 的 8 轮验证诊断源码复制独立目录，仅在首次失败判定后
追加同坐标读回。源文件/构建日志位于
`build/glmark-optimization/glmark-readback-source/`、`build-readback-probe.log`；
构建 rc=0。该程序不修改首次像素、参考值、容差或失败判定；额外读回不重绘。

| run-id 后缀 | Client | 8 轮成功/失败/无判据 | 第 1 轮新增失败 | 第 2–8 轮新增失败 | 外层 rc |
| --- | --- | --- | --- | ---: | ---: |
| readback1000-pixel8 | cadce...；1000 µs | 206/10/48 | texture mipmap、desktop shadow | 0 | 1 |
| readback50-pixel8 | cadce...；50 µs | 206/10/48 | texture nearest、desktop shadow | 0 | 1 |

两组每轮均另有已知 function medium 失败。对每个失败像素，首次值、额外
`glFinish` 后的值、等待 1 ms 再 `glFinish` 后的值完全相同：

| 场景 | 参考 RGBA packed 值 | 首次及两次追加读回值 | 原始距离 |
| --- | --- | --- | ---: |
| 1000 µs，texture mipmap | 0xff2a2d2c | 0xff2e2e2f | 5.099020 |
| 50 µs，texture nearest | 0xff282a2b | 0xff2e2e2e | 7.810250 |
| 两组 desktop shadow | 0xff0d271f | 0xff319a79 | 150.402793 |

汇总 `build/glmark-optimization/readback-probe-results.json` 仅统计原始 8 轮，
不把失败后自动执行的 debug 诊断再次加入样本。两组均未执行性能场景。
该结果不支持“首次读回过早，额外等待 1 ms 即恢复”的解释；它不能单独
证明某种缓存缺陷，更不能排除资源发布、GPU 缓存、映射或渲染状态问题。

另一个正在检查的假设：用户态通过 WC 映射填充 BO，提交 RPC 的 ring 发布
使用 CPU 间屏障，Proxy 可轮询取请求，可能早于 Client 随后的 doorbell I/O
屏障。实验 Client 在 GROUP_SUBMIT RPC 发布前增加 `wmb()`，不修改任何
映射或 fence 语义；编译 rc=0，Image SHA-256
`8c4f5aac0ccafdb99e287337f19ebc17d756d89e28e7ba649b4b548b87110b54`。
原 cadce... 已备份为 `build/glmark-optimization/client-poll-only.Image`。
`barrier1000-pixel8` 使用相同 e586... 诊断 ELF、1000 µs、594 MHz，外层 rc=0，
8 轮为 208 成功/8 已知失败/48 无判据，新增失败 0。该单次通过不能证明
根因或稳定修复，因为此前不加屏障的其他诊断也出现过全通过。
反汇编确认 RPC 前生成 `dsb st`，记录于
`build/glmark-optimization/client-submit-barrier.disassembly`。

为避免只重复候选直到 PASS，预先保存了 4 次冷启动诊断顺序：control1、
enabled1、control2、enabled2，分别部署 cadce.../8c4f.../cadce.../8c4f...。
所有运行仍使用相同 e586... ELF、1000 µs、8 轮严格验证和 CPU/GPU 配置。
计划在 `build/glmark-optimization/barrier-ab.schedule.json`，逐次退出码更新于
`barrier-ab.results.json`；待全部结束后再解释结果。诊断 ELF 的分数不纳入
正式性能对照。


## 写屏障交替对照的最终结果与撤回

固定顺序的四次冷 VM 启动均已执行，未按结果增加或删除运行：

| run-id 后缀 | Client 是否含提交前屏障 | 成功/失败/无判据 | 新增失败 | 外层 rc |
| --- | --- | --- | ---: | ---: |
| barrier-ab-control1 | 否，cadce... | 208/8/48 | 0 | 0 |
| barrier-ab-enabled1 | 是，8c4f... | 207/9/48 | 1 | 1 |
| barrier-ab-control2 | 否，cadce... | 207/9/48 | 1 | 1 |
| barrier-ab-enabled2 | 是，8c4f... | 208/8/48 | 0 | 0 |

有、无屏障各 1 次通过、1 次失败，不能归因于写屏障或宣称稳定修复。
此处的通过仍包含 8 次已知 function medium 失败和 48 项无判据，不表述为
所有场景验证通过。失败自动诊断不覆盖首次结果，诊断 ELF 分数不用于性能比较。
该小样本不能估计总体失败概率，也不能证明两者在统计意义上等效。

已从当前 Client 源码撤回实验 `wmb()`，保留独立实验补丁
`build/glmark-optimization/client-submit-barrier.patch`、8c4f... 镜像及全部原始日志。
本地运行 Client Image 恢复 cadce...（可调轮询与统计，默认 1000 µs），
Proxy 保持 e83f... ACK 候选。没有把 50 µs 设置为默认值，没有声称其改善帧率；
两组原始性能尝试均因严格验证失败而未进入性能场景。

新增证据将后续排查重点落在首次渲染前的资源发布、映射和缓存状态。
失败后重复读回仍错误，不能靠增加 CPU 等待来掩盖。下一步需要对首次 GPU
资源访问建立可观察的输入/输出与同步证据，再完成 720p/1080p 同频完整性能
对照和受影响功能回归；目前未满足优化验收，也未执行新版本全 32 项矩阵。


本阶段最终状态已重新验证：原始 glmark artifact 2251...、Client cadce...、
Proxy e83f...，板端与本地镜像哈希一致。保存日志并 sync 后经 SysRq 重启，
未执行 Panthor 工作后解绑。新 boot-id
`89124031-8784-4840-902e-be2d61336479`；Host 仍为 pmthor #10，CPU 0–1，
GPU 读回 198 MHz，实验固定 OPP 模块不存在，无 firecracker/broker 或 loop。
首次 SSH 观察超时已保留，后续重试成功且 boot-id 改变，没有重复复位。
状态日志 `build/glmark-optimization/after-poll-final-state-retry.txt`，
逐项断言 `poll-final-restore-assertions.log`。Host Image、固件和 SD 分区未修改。
当前源码已撤回写屏障实验；shell 语法、主仓库和 Guest 的 diff 检查通过。
本阶段所有新代码、文档及实验材料均未提交/推送。


## 首次 DMA 页缓存维护、单 VM 对照与轮询性能补充

以下为后续实验，运行前重新确认 Host boot-id 为
`89124031-8784-4840-902e-be2d61336479`、pmthor #10，无其他 VM/broker。
重新加载固定 OPP 诊断模块，GPU 实际 594 MHz；此前“重启恢复 198 MHz”描述
是上一阶段结束状态，不是这些实验的运行状态。Client 为 cadce...，Proxy 为 e83f...。

### 首次 PFN 暴露前缓存维护：固定四次顺序

诊断模块通过 `pmthor_gpu_track_pfn` 返回值区分首次成功 pin（0）和重复 PFN
（-EBUSY）。仅对首次页执行 Host 线性映射的逐缓存行 `DC CIVAC`，前后 DSB SY；
重复页不做维护，避免破坏 GPU 已持有的数据。这不是完整 DMA ownership 协议，
也不是生产修复。源码、构建日志与顺序保存在 `build/glmark-optimization/first-dma-probe/`
和 `firstdma.schedule.json`，模块 SHA-256 为
`bd4467ad3763189e4df69c2b690d0e746e7f039ee6fd5723606290449923263b`。
匹配 Host headers 构建 rc=0；缺少 Module.symvers 的 modpost 警告保留，实际加载成功。

所有 run-id 前缀为 `glmark-opt-20261016-`，命令在相应 `.command`，外层日志为
`build/glmark-optimization/<后缀>.log`，Guest/Proxy/Host 日志在
`GPU-SFTP/log/shared/vmshm-1client/<run-id>/`。使用 e586... ELF 的 8 轮严格验证：

| 后缀 | 首次页维护 | 成功/失败/无判据 | 新增失败 | rc | 新 PFN / 已维护 PFN | 维护累计时间 |
| --- | --- | --- | ---: | ---: | --- | ---: |
| firstdma-observe1 | 否 | 207/9/48 | 1（nearest） | 1 | 40616 / 0 | 0 |
| firstdma-clean1 | 是 | 208/8/48 | 0 | 0 | 37787 / 37787 | 26.301 ms |
| firstdma-observe2 | 否 | 208/8/48 | 0 | 0 | 36966 / 0 | 0 |
| firstdma-clean2 | 是 | 208/8/48 | 0 | 0 | 40321 / 40321 | 26.565 ms |

所有探针 failed=0、missed=0；每次结束后卸载探针。
维护组 2/2 无新增失败，对照组 1/2 无新增失败，样本不足以证明根因或稳定修复。
失败组自动追加 debug 工作量，不能将 PFN 或调用次数差异解读成性能收益。
8 次失败均为原有 function medium 例外；48 项无判据不能算验证成功。
结构化原始统计在 `firstdma.results.json`、`firstdma.analysis.json`。

### 同一个 Proxy 内核的单 VM GPU 直通对照

run-id `glmark-opt-20261016-direct-proxy-pixel8`，直接使用 e83f... GPU 内核、
相同 e586... 用户态、594 MHz、单 vCPU 绑 CPU2、896 MiB；无 Client 前端、
RPC、broker、vmshm，也未加载首次页维护探针。8 轮为 208/8/48、新增失败 0，
Firecracker rc=0，外层 rc=0；后续审计发现 PSCI 请求之后 PID 1 返回触发 panic，
因此只认可负载结果，不认可清理阶段通过。单次结果支持继续排查共享路径，
不能证明直通绝不会出现问题。命令、配置、退出码与日志在
`GPU-SFTP/log/glmark-optimization/glmark-opt-20261016-direct-proxy-pixel8/`；
诊断 ELF 分数不用于性能对照。没有解绑工作后的 Panthor。

### 原始 ELF 的 1000 / 50 µs 性能对照

恢复原始 2251... glmark ELF；两组均加载首次页维护诊断探针，固定相同
594 MHz、broker CPU0 / Proxy CPU1 / Client CPU2，1000 µs 先、50 µs 后。
命令见 `build/glmark-optimization/run-poll.sh`，顺序与退出码为
`firstdma-poll.schedule.json`、`firstdma-poll.results.json`。
两组均先通过严格验证：26 成功、1 已知失败、6 无判据、新增失败 0，外层 rc=0。
每个性能场景 5 秒，分辨率 1280×720，frame-end finish：

| run-id 后缀 | poll µs | build VBO FPS / ms | desktop blur FPS / ms | terrain FPS / ms | 三场景分数 |
| --- | ---: | --- | --- | --- | ---: |
| firstdma-poll1000-three | 1000 | 1304 / 0.767 | 236 / 4.249 | 49 / 20.433 | 528 |
| firstdma-poll50-three | 50 | 1282 / 0.780 | 236 / 4.249 | 49 / 20.542 | 521 |

1000 µs 组快照 worker waits=7973、polls=13855、total_wait_ns=11787458738；
50 µs 组 waits=7863、polls=15652、total_wait_ns=2587938766，两组 errors=0。
worker 累计等待时间降低约 78%，但帧率没有改善；该统计不包含 worker 排队时间，
不能等同 CPU 使用率或端到端延迟。不修改默认 1000 µs。
首次页维护累计 22.504/21.466 ms，探针 missed=0；测试后均卸载。
三场景分数不能替代完整 33 场景，也不能当作已完成同频 1080p 对照。

后续性能假设：Client 的 flush-ID 软件页恒为 0，而 Panthor UAPI 明确规定 0
请求每次提交无条件 flush+invalidate(all)，原生用户态则读取实际硬件 flush ID
允许消除冗余刷新。需要先用加强刷新而不削弱正确性的对照量化代价；不能在
Proxy 提交时随意填入一个新的非零 ID，因其不再代表用户态构造 stream 的时刻。


## flush-ID 的单 VM 因果对照及关机脚本修复

为量化恒零 flush ID 的代价，临时编译同一个诊断 Proxy 内核，增加只读启动参数
`panthor.diagnostic_force_full_flush`。关闭时不改提交；开启时仅将驱动 job 中的
latest_flush 置 0，请求更强的缓存维护，不跳过任何必要刷新。诊断补丁为
`build/glmark-optimization/proxy-force-flush-diagnostic.patch`，构建 rc=0，Image SHA-256
`43ed12bf06e5d7b9b3e1b85cbe147de434ee9d04c466550ef30140d1b1483525`。
已撤回该临时源码改动，正式 Proxy 源码仍只有 ACK 修复；运行树仍为 e83f...。
诊断 Image 单独部署在 RK log 目录，不替换正式 Image。

每组使用此相同 Image、原始 2251... ELF、594 MHz、单 VM CPU2、896 MiB、
相同三个 5 秒场景，没有 Client/RPC/broker/首次页维护探针。
所有运行严格验证均为 26 成功、1 已知失败、6 无判据、新增失败 0。
运行前缀 `glmark-opt-20261016-direct-flush-`：

| 后缀 | 强制完整刷新 | build FPS / ms | blur FPS / ms | terrain FPS / ms | 外层 rc / 清理 |
| --- | --- | --- | --- | --- | --- |
| native1 | 否 | 2003 / 0.499 | 322 / 3.112 | 69 / 14.554 | 0，但事后审计发现 panic |
| zero1 | 是 | 2005 / 0.499 | 298 / 3.358 | 65 / 15.485 | 0，但事后审计发现 panic |
| zero2 | 是 | 1996 / 0.501 | 298 / 3.361 | 65 / 15.533 | 1，严格检测到 panic |
| native2 | 否 | 1999 / 0.500 | 321 / 3.121 | 69 / 14.622 | 0，正常 SHUTDOWN |
| zero3 | 是 | 2007 / 0.498 | 299 / 3.353 | 65 / 15.500 | 0，正常 SHUTDOWN |

zero2/zero3 实际读回 sysfs 参数 Y，日志确认原始 ID=0xffffe0 后被强制置 0；
native2 参数 N。前两次参数已出现在启动配置且未被内核列为未知参数，但最初
未导出 sysfs/诊断日志，因此后续增加了明确的生效证据。所有原始结果保留，
单独的 audit.json 区分 workload_pass、cleanup_panic、normal_shutdown、whole_run_pass，
不会把先前脚本误判的 passed=true 当全流程通过。
证据在 `GPU-SFTP/log/glmark-optimization/<run-id>/`，配置及精确启动命令均在其中；
控制机外层日志 `build/glmark-optimization/direct-flush-<后缀>.outer.log`，
结构化汇总为 `direct-flush.analysis.json`。

最后一对正常清理的实验中，完整刷新使 blur FPS 降低 6.85%、terrain 降低
5.80%，对应帧时间增加 0.232/0.878 ms；build 基本不变。前几次负载阶段也表现
相同方向，但这些是单 VM 短测试，不能把百分比直接归因为共享路径每场景的
精确损失。尤其 build 仍从约 2000 降至共享约 1300，而完整刷新不显著影响
单 VM build，说明仍需要优化或解释通信与同步路径，不能只修 flush-ID。
不能在 Proxy 提交瞬间填入当前 ID 来替代用户态构造 stream 时读取的 ID。

关机问题根因为精简 Guest rootfs 缺少 poweroff/halt 命令，原 init 将两次失败
隐藏在 stderr 重定向之后，再 exit 0，导致 PID 1 退出 panic；随后 panic reset
使 Firecracker 收到 RESET（type 2）并返回 0，原辅助脚本只检查退出码与负载
PASS，因此误判清理。已修复 `GPU-SFTP/tests/gpu-compute-smoke/init`：命令不可用
时请求 Guest 内核 SysRq poweroff，并保持 PID 1 存活；native2/zero3 实测得到
Power down、KVM SHUTDOWN（type 1）、无 panic、外层 rc=0。这项修复不影响
此前共享脚本的 after_run=shell 模式，也不将旧失败追认为通过。

另外对 firstdma-poll1000-three 的 RPC 日志去除完全重复输出后统计：
SYNCOBJ_TIMELINE_WAIT 64372 次、累计 2.820 s，TRANSFER 47621 次、2.602 s，
WAIT 21906 次、2.087 s，GROUP_SUBMIT 31955 次、2.037 s；各自平均约
43.8/54.6/95.3/63.7 µs。它们覆盖 validation、性能及 worker，线程间时间可能
重叠，不能相加推断端到端延迟；足以支持下一步按场景定位同步往返的关键路径。
原始数据和范围说明见 `build/glmark-optimization/poll1000-rpc-analysis.json`。


### 当前候选完整 1080p 再测：严格验证失败，未产生性能成绩

run-id `glmark-opt-20261016-poll1000-full1080-v2`，Client cadce...、Proxy e83f...，
原始 glmark 2251...、594 MHz、1000 µs 默认轮询、1920×1080，未加载首次页维护
探针，也未使用强制完整刷新诊断内核。命令在
`build/glmark-optimization/poll1000-full1080-v2.command`，外层 rc=1；日志在
`GPU-SFTP/log/shared/vmshm-1client/glmark-opt-20261016-poll1000-full1080-v2/`。
首次 validation 为 25 成功/2 失败/6 无判据，新增 mipmap 失败 1 项，另 1 项是
已知 function medium。GPU smoke rc=125，未进入完整性能场景，不记录分数；
失败后的自动诊断不能覆盖首次结果。该结果再次表明 correctness 尚未收敛，
当前不能接受优化完成，也没有新的有效同频 1080p Clientproxy 完整成绩。
本阶段不追加同配置重跑以获得偶然 PASS。


本阶段结束状态：保存证据、确认无 VM/broker/loop 后 sync，并仅执行一次 SysRq
重启以卸除固定 OPP 实验。新 boot-id 为
`57478278-8ab7-493c-99c0-756531789b4f`，pmthor #10、CPU 0–1、GPU 198 MHz，
无首次页维护或固定 OPP 模块，无残留 VM/broker/loop，正式 Image 仍为
Client cadce... / Proxy e83f...。首次 SSH timeout 后重新检查同一次重启成功，
没有再次复位。状态证据 `build/glmark-optimization/flush-final-state-retry.log`
为 FINAL_STATE_PASS；未修改 Host Image、固件或 SD 分区，未解绑工作后的 Panthor。
Guest init 关机回退经过正常关闭的两次实测，shell 语法和主仓库/Guest diff 检查通过。
所有新代码、报告、诊断内核和实验记录均未提交/推送。优化目标保持进行中：
首次验证错误没有稳定修复，完整同频 1080p 和新版本全 32 项验收仍不满足。


## 分配前初始化的交替诊断（后续阶段）

在新 boot-id `57478278-8ab7-493c-99c0-756531789b4f` 上确认空闲后，重新加载固定
OPP，GPU 实际 594 MHz。Host 运行 Image 未改；Client cadce...；临时 Proxy
Image `ca0e00af90e343c57c26337e8e33ce608f226dd1ea1b99bb706f50843538580d`
基于 e83f... 源码增加默认关闭的只读 `proxy_vmshm_manager.diagnostic_zero_on_alloc`。
它在 alloc_ext 对象发布前清零已分配 backing（buddy/slab/SG）并 wmb，记录
objects/bytes/zero_ns；不改变释放时清零、pin、grant 或 fence 语义。
这会通过 Proxy CPU 访问此前可能仅供 GPU 使用的页，不等同完整 Host DMA 协议。
构建 rc=0，补丁与 Image 在 `build/glmark-optimization/alloc-zero-diagnostic.patch`
及 `proxy-alloc-zero-diagnostic.Image`。

预先固定的 4 次顺序在 `alloc-zero.schedule.json`，原始 rc 在
`alloc-zero.results.json`，结构化检查为 `alloc-zero.analysis.json`。
相同 e586... ELF 每次验证 8 轮；run-id 前缀 `glmark-opt-20261016-`：

| 后缀 | 开关 | 成功/失败/无判据 | 新增失败 | 外层 rc | 计数读回 |
| --- | --- | --- | ---: | ---: | --- |
| alloc-observe1 | 0 | 208/8/48 | 0 | 0 | 未读到，sysfs 未挂载 |
| alloc-zero1 | 1 | 208/8/48 | 0 | 2 | 未读到；另有本地脚本收尾错误 |
| alloc-observe2 | 0 | 207/9/48 | 1 | 1 | enabled=0，objects=0 |
| alloc-zero2 | 1 | 208/8/48 | 0 | 0 | enabled=1，objects=621 |

最后一组 bytes=431849472（约 412 MiB）、zero_ns=593004332。
前两组启动配置包含开关，但没有实际 sysfs 生效计数，因此结论权重较弱。
所有命令在 `build/glmark-optimization/<后缀>.command`，外层日志为同名 `.log`，
Guest/Proxy/Host 日志在 `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`。
alloc-zero1 在负载已经完成后，由于 Agent 运行中修改本地辅助脚本，bash 随后
读取文件时发生解析错误，未执行正常的本地取回流程，外层 rc=2 必须保留。
已单独取回该目录的常规日志；不能把负载 PASS 写成全流程 PASS。
后两组脚本在执行前固定，并在负载完成后挂载 sysfs 才读取计数；没有在负载
阶段改变映射、缓存属性或清零开关。临时脚本版本均保存于 build 目录。

该小样本仍不足以认定稳定修复：关闭开关也能通过，开启开关改变了初始化和
时序。诊断 ELF 的分数不纳入性能结论。随后恢复原始 2251... ELF，启动
`alloc-zero-full1080` 的完整 1080p 尝试，保持同一 ca0e... Image、开启分配前
清零、1000 µs、相同绑核；只在严格验证通过后进入性能场景。

同时准备 Host DMA 候选：首次 unique PFN 在返回 HPA 前进行 dma_map_page，
重复 PFN 不重复转换缓存所有权；只接受 DMA address==HPA，否则返回错误并
撤销新映射；设备与 VM 都结束并复位 GPU 后再 dma_unmap_page 和释放页引用。
按硬件 MMU PA bits 配置 DMA mask。该修改还不能替代 Guest 自身的 CPU/GPU
同步，也不提供 SMMU/GPC 隔离。匹配 Host 配置的 pmthor_drv.o 编译 rc=0，日志
`build/glmark-optimization/host-dma-map-object-build.log`；完整候选 Image/模块
以独立 release `6.12.0-opencca-pmthor-dma1` 在控制机构建中，尚未部署或验证。


### 分配前初始化候选的完整 1080p 结果

`glmark-opt-20261016-alloc-zero-full1080` 已完成，外层 rc=0、RESULT: PASS。
严格验证 26 成功/1 已知 function medium 失败/6 无判据、新增失败 0；
完整 33 个性能场景，Mali-G610 renderer、1920×1080、原始 2251... ELF、
frame-end finish，没有跳过验证或完成等待。Proxy 计数读回 enabled=1、
objects=441、bytes=750817280（约 716 MiB）、zero_ns=1445122913。
这些是整个进程阶段的累计清零量与耗时，不能直接从 benchmark 总时长中扣除。
初始化与 wmb 是组合诊断，尚未拆分两者贡献，也未证明偶发错误根因。

| 指标 | 同频原生 | 分配前清零候选 | 对比 |
| --- | ---: | ---: | --- |
| 完整 glmark 分数 | 1002 | 772 | 保留 77.05% |
| 33 场景 FPS 比值几何均值 | — | — | 保留 80.67% |
| 场景帧时间增加中位数 | — | — | 0.245 ms |
| 场景帧时间开销中位数 | — | — | 28.15% |

原生为既有 `glmark-opt-20261016-native-600` 的 1080p profile，GPU 同为
594 MHz、相同 ELF/分辨率/完成等待；候选为同一旧 Host #10、Client cadce...、
诊断 Proxy ca0e...、1000 µs、broker0/Proxy1/Client2、512/384 MiB。
这是不同路径的同频比较；没有同一诊断 Image 关闭开关的完整 1080p 成绩，
因此不能把 772 相对历史成绩的变化归因于清零。原生该次已知 cleanup busy
记录继续保留，不将 profile 负载通过等同整个原生脚本无异常。
新 Host DMA 候选未参与本测量。

精确命令在 `build/glmark-optimization/alloc-zero-full1080.command`，退出码在
同名 `.status`，原始全部日志在
`GPU-SFTP/log/shared/vmshm-1client/glmark-opt-20261016-alloc-zero-full1080/`。
33 项场景和结构化比较保存在 `alloc-zero-full1080-comparison.json/.md`，
生成脚本同时断言双方恰好 33 项且顺序/场景参数相同。
下表是完整逐场景比较，不能将分数比例表述为每个应用的固定开销：

| 场景 | 原生 FPS | 候选 FPS | FPS 保留率 | 增加帧时间 ms |
| --- | ---: | ---: | ---: | ---: |
| [build] use-vbo=false: | 792 | 885 | 111.7% | -0.133 |
| [build] use-vbo=true: | 1790 | 1209 | 67.5% | 0.268 |
| [texture] texture-filter=nearest: | 1564 | 1110 | 71.0% | 0.261 |
| [texture] texture-filter=linear: | 1571 | 1114 | 70.9% | 0.261 |
| [texture] texture-filter=mipmap: | 1575 | 1116 | 70.9% | 0.262 |
| [shading] shading=gouraud: | 1520 | 1091 | 71.8% | 0.259 |
| [shading] shading=blinn-phong-inf: | 1483 | 1075 | 72.5% | 0.257 |
| [shading] shading=phong: | 1302 | 998 | 76.7% | 0.234 |
| [shading] shading=cel: | 1278 | 989 | 77.4% | 0.228 |
| [bump] bump-render=high-poly: | 946 | 844 | 89.2% | 0.128 |
| [bump] bump-render=normals: | 1815 | 1216 | 67.0% | 0.271 |
| [bump] bump-render=height: | 1615 | 1142 | 70.7% | 0.257 |
| [effect2d] kernel=0,1,0;1,-4,1;0,1,0;: | 931 | 805 | 86.5% | 0.169 |
| [effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;: | 448 | 349 | 77.9% | 0.635 |
| [pulsar] light=false:quads=5:texture=false: | 1168 | 956 | 81.8% | 0.190 |
| [desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4: | 234 | 200 | 85.5% | 0.740 |
| [desktop] effect=shadow:windows=4: | 594 | 531 | 89.4% | 0.202 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 47 | 46 | 97.9% | 0.591 |
| [buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata: | 47 | 46 | 97.9% | 0.539 |
| [buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map: | 66 | 65 | 98.5% | 0.225 |
| [ideas] speed=duration: | 433 | 365 | 84.3% | 0.430 |
| [jellyfish] <default>: | 761 | 660 | 86.7% | 0.201 |
| [terrain] <default>: | 57 | 46 | 80.7% | 4.250 |
| [shadow] <default>: | 698 | 556 | 79.7% | 0.367 |
| [refract] <default>: | 145 | 133 | 91.7% | 0.620 |
| [conditionals] fragment-steps=0:vertex-steps=0: | 1353 | 1016 | 75.1% | 0.245 |
| [conditionals] fragment-steps=5:vertex-steps=0: | 1275 | 995 | 78.0% | 0.221 |
| [conditionals] fragment-steps=0:vertex-steps=5: | 1343 | 1018 | 75.8% | 0.238 |
| [function] fragment-complexity=low:fragment-steps=5: | 1339 | 1017 | 76.0% | 0.237 |
| [function] fragment-complexity=medium:fragment-steps=5: | 1117 | 948 | 84.9% | 0.160 |
| [loop] fragment-loop=false:fragment-steps=5:vertex-steps=5: | 1344 | 1018 | 75.7% | 0.239 |
| [loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5: | 1343 | 1016 | 75.7% | 0.239 |
| [loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5: | 1118 | 944 | 84.4% | 0.165 |


本阶段完成后恢复原始 2251... glmark 和正式 Client cadce... / Proxy e83f...，
删除已归档的临时诊断 runner。保存日志并 sync、仅一次 SysRq 重启卸除 OPP；
新 boot-id `620a0216-9561-4c10-b95e-60452dec2207`，Host pmthor #10、CPU 0–1、
GPU 198 MHz，无 VM/broker/loop，无 OPP/首次页维护模块。
`build/glmark-optimization/alloc-final-state-retry.log` 为 FINAL_STATE_PASS；首次
SSH timeout 保留，后续检查同一次重启成功，没有再次复位。未部署新 Host，
未修改 SD 启动配置/固件，未进行工作后的 Panthor 解绑。

主仓库、Host/Guest 的 diff 检查及 shell 语法检查通过。Host DMA 候选源码保留
在 Host 工作树，Guest 分配前清零诊断默认仍关闭；两者均不能作为已完成硬件
验收的生产修复。Host 完整 Image/modules 构建仍在控制机运行，工具 session
13518 已实际轮询确认存活，命令/观察记录为 `host-dma-build-state.json`；下一步
必须继续观察该进程，不能仅凭状态文件或一次观察超时重启构建。
新版本全 32 项矩阵未执行，首次错误的稳定修复及剩余性能优化仍待完成。
本阶段全部代码、补丁、报告和证据均未提交/推送。

## Host DMA 候选构建、部署与验证（后续阶段）

先前完整构建进程 session 13518 已确认退出 0；不是仅根据状态文件判定。
`host-dma-full-build.log`、`host-dma1-deploy/build.exit-code` 保留结果。
独立 release 为 `6.12.0-opencca-pmthor-dma1`，Image SHA-256
`0ba8d83978fd1a242c014d9a60bd3c93b4fcaef3b705b218467d25acacda08b4`。
匹配模块安装包和板端 mkinitramfs 均完成；initrd SHA-256
`2ed06fcc861e4daed59942d000203a70980c856b04b76479014be29c9e1ca645`。
新构建使用 GCC 15.2 / binutils 2.46，旧固定配置来自 GCC 11.4 / binutils 2.38；
自动配置另启用 RELR 等工具链能力。完整差异保存在
`build/glmark-optimization/host-dma1-deploy/config.diff`，因此不能声称新旧二进制
仅有 DMA 修改，后续性能归因需要同一新 Host 的原生对照。

Group submit 探针源码已把错误的绝对 `1000000000 ns` 改为现有 helper 生成的
`CLOCK_MONOTONIC 当前值 + 1 秒`，保留其他立即返回/过期期限测试语义。
静态探针 SHA-256 `134dd69f27f8d505a1089b3f9ad049dd0f2603c22c5b6cac9a8a908b816d7ccc`。
旧 Host 上命令：

```bash
RUN_ID=glmark-opt-20261016-deadline-sourcefix \
  ./scripts/run/run-vmshm-e2e.sh --skip-build --skip-sync \
  --no-clean-remote-procs --group-submit-syncpoint-smoke
```

外层退出码 0，`PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS`、
`PANTHOR_IOCTL_INIT=PASS`、`RESULT: PASS`。记录的绝对期限为 `2164311708 ns`。
证据目录 `GPU-SFTP/log/shared/vmshm-1client/glmark-opt-20261016-deadline-sourcefix/`，
控制机日志 `build/glmark-optimization/deadline-sourcefix.log`。这不覆盖历史失败，
也不等于新 Host 或完整 32 项通过。

部署前确认旧 Host 空闲、根分区为 SD `/dev/mmcblk1p4`，kernel 分区 p3
起始 32768 扇区、长度 262144 扇区；root 起始 294912 扇区。
旧 p3 完整 128 MiB 备份 SHA-256
`27c6ad71937d8cee1d8c7d976f6e76cca41ed6ab51b6f9eb0bebeacfb44ae4bb`，
控制机和 Pi 均保存并校验。保持旧 DTB 和 cmdline，仅更换匹配的内核与 initrd。
新 ext4 启动分区镜像 SHA-256
`a35def75e7729949695c31c726ba4f743bef7762304390935c0e085c42a9dc94`，
大小 134217728 字节，离线 `e2fsck -fn` 退出 0，extlinux 内容经检查。

补丁清单检查本次失败：`opencca-flash: initialize the pinned submodule first`；
当前控制机部分固件子模块未初始化，不能记录全清单通过。此次不构建/更新固件，
使用仓库部署脚本，已核对 Pi 上脚本及固定 SPL loader 的 SHA-256 与本地/manifest 一致。
通过 Pi 的 SD-only、读取 GPT 校验保护流程只写 storage ID 2 的 kernel 分区，
刷写 session 19597 退出 0。完整日志 `build/glmark-optimization/dma1-flash.log`，
串口日志 `dma1-uart.log`；初次 SSH 观察 timeout 单独保留，继续检查同一次启动，
不能把刷写退出 0 当作启动或负载验证通过。

同一次启动随后确认 `DMA1_BOOT_PASS`，boot-id
`f98b03ac-f694-4bab-9c40-e0fa27a71af7`，release 与候选一致、pmthor 绑定、CPU 0–1、
GPU 198 MHz、无 VM/broker。串口有 `efi.mount` 失败，Host 已进入系统且 SSH 可用，
不隐藏该启动消息；尚未确认它是否与旧配置的自动发现行为相同。
首次 timeout 和第二次 connection refused 保留在独立观察日志，没有额外复位。

新 Host 的分项验证：

| 用例 / run-id | 命令要点 | 退出码 | 证据与结果 |
| --- | --- | ---: | --- |
| PFN 生命周期 | `timeout 35 .../bin/pmthor-pfn-lifetime`，随后运行 `check_kernel_log.py` | 程序 0 / checker 0 | `build/glmark-optimization/dma1-pfn-lifetime.log`；两种关闭顺序、每种 32 次翻译、唯一页释放检查通过 |
| `glmark-opt-20261016-dma1-group` | 标准 runner `--skip-build --skip-sync --no-clean-remote-procs --group-submit-syncpoint-smoke` | 0 | `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`；Group submit、INIT 和整体 PASS |
| `glmark-opt-20261016-dma1-compute4` | 标准 runner `--gles-compute-smoke --skip-gles-remote-build`，Client/Proxy 512/384 MiB，`--count 1048576 --iterations 10 --warmup 2 --perf --exclude-cpu-prepare` | 0 | 同上 run-id 目录；`GPU_SMOKE_RESULT=PASS`，仅为 4 MiB 分项验证 |

完整控制机入口日志和退出码分别为 `dma1-group.log/.exit-code`、
`dma1-compute4.log/.exit-code`，均在 `build/glmark-optimization/`。
正式 Client cadce...、Proxy e83f... 保持不变，未启用分配清零诊断。
匹配新完整内核输出重建的 OPP 诊断模块编译退出 0，板端加载成功，
实际频率 594 MHz；此启动内不卸载该模块、不切换 GPU 驱动，结束时重启恢复。
接着按预先固定四次冷 VM 启动安排执行 e586... ELF 的每次 8 轮验证，
命令/退出码逐项保存，不将失败重跑成通过。

固定四次诊断已经全部完成，外层均退出 0：

| run-id 后缀 | 成功 / 已知失败 / 无判据 | 新增失败 | 退出码 |
| --- | --- | ---: | ---: |
| dma1-pixel8-1 | 208 / 8 / 48 | 0 | 0 |
| dma1-pixel8-2 | 208 / 8 / 48 | 0 | 0 |
| dma1-pixel8-3 | 208 / 8 / 48 | 0 | 0 |
| dma1-pixel8-4 | 208 / 8 / 48 | 0 | 0 |

前缀 `glmark-opt-20261016-`，日志仍位于标准 shared/vmshm-1client run-id 目录。
精确命令与退出码见 `build/glmark-optimization/dma1-pixel8-<序号>.command/.status`，
汇总 `dma1-four-diagnostics-results.json`。合计是 4 次冷 VM 启动、32 轮图形验证，
**不是完整 32 项功能矩阵**；832 成功、32 已知 function 失败、192 无判据。
全部在同一次 Host boot、594 MHz 上执行，正式 Proxy 没有分配清零诊断。
相比此前控制样本出现首次错误，这为首次 DMA 准备不足的假设提供进一步证据，
但样本量有限且存在新 Host 工具链差异，不能声明稳定修复或纯 DMA 因果关系。
四次结束后恢复原始 2251... ELF，开始 `dma1-full720` 完整性能测量；
未执行的新 Host 原生对照不能用旧 Host 分数替代。

`glmark-opt-20261016-dma1-full720` 已完成：外层退出 0、`GLMARK_RESULT=PASS`、
完整 33 性能场景，原始 ELF、frame-end finish，严格验证 26 成功 / 1 已知失败 /
6 无判据，新增失败 0。**score 938**；旧 Host 同频正式 ACK 路径为 914，
数值增加约 2.6%，但工具链/自动配置不同，不能据此归因于 DMA 修改，
更不能用旧 Host 原生 1432 作为最终同环境开销结论。
本次完整分辨率为 1280×720，594 MHz，Client/Proxy cadce.../e83f...，
poll 1000 µs、关闭清零诊断、broker/Proxy/Client 分别绑 CPU 0/1/2。
精确命令 `build/glmark-optimization/dma1-full720.command`、退出码 `.status`、
摘要 `dma1-full720-summary.json`；完整日志为标准 shared run-id 目录。
接续 `glmark-opt-20261016-dma1-full1080` 完整测试，尚未有结果；
新 Host 原生两分辨率对照和完整 32 项仍未执行。此次进展不能作为优化完成验收。

### 下一候选：合并同步文件快照的创建与复制

`dma1-full720` 的去重累计 RPC 统计保存于
`build/glmark-optimization/dma1-full720-rpc-analysis.json`。整个运行（含验证）
SYNCOBJ_CREATE 619737 次、平均 56.82 µs，TRANSFER 1003947 次、平均 56.03 µs，
DESTROY 619737 次、平均 56.73 µs，GROUP_SUBMIT 389704 次、平均 65.33 µs。
这些统计包含不同线程并可能重叠，不能把各项累计时间相加后当作帧关键路径。

源码中 `panthor_client_syncobj_snapshot` 为每次 sync_file 导出分别发出 CREATE
与 TRANSFER 两次 RPC。新增默认关闭的只读 `panthor_client.fused_snapshot`
实验参数，以及 OPEN_SESSION feature bit 协商的一次 SYNCOBJ_SNAPSHOT RPC，
在 Proxy 内复用现有创建/二进制 transfer 路径；复制失败销毁新对象，session
仍通过通道 Client VMID 校验。保留独立目标对象，等待和销毁沿用原快照路径，
不取消 GPU 完成等待、不直接引用会被用户 reset/reuse 的源 syncobj。
新 Client 与旧 Proxy 协商不到能力时继续原路径；旧 Client 忽略新增能力位。
新请求没有改变现有请求结构或用户态 DRM ABI。

两角色增量 Image 构建均退出 0，日志
`fused-snapshot-client-build.log`、`fused-snapshot-proxy-build.log`。
保存候选（尚未部署为正式运行镜像）：

| 候选 | SHA-256 |
| --- | --- |
| Client | fd62dc83713b53feb60e2d45d99033b9ef829ff557a4a79e7a400dbbd34b085b |
| Proxy | 4c8c20a2141014a1dfc3e38bd06de270a35b77e9419534aec9888dcaed77dc38 |

构建不会证明语义/性能收益。接下来需要同一候选二进制开关对照、
snapshot reset/destroy/file-close 回归、旧 Proxy 能力回退验证与图形数值验证。
正在运行的 `dma1-full1080` 仍为正式 cadce.../e83f...，未混入本候选。

后续审查修正合并请求边界：先验证并持有源 syncobj 引用，再分配目标，
避免无效源 ID 恰好被新目标分配复用后错误地通过检查。传输使用持有引用的真实
源对象句柄；失败释放新目标，最后释放源引用。Proxy v2 重新构建退出 0，
`fused-snapshot-proxy-build-v2.log`，Image SHA-256
`7e077e867623b2e4d27dad4e29bf4c20bb1649b411a48bbf5f5db48b5493a350`。
前表 4c8c... 是未部署的第一版归档，后续实验应使用 v2；语义硬件验证仍待进行。

`glmark-opt-20261016-dma1-full1080` 随后完成，外层退出 0、完整 33 场景、
score **777**，严格验证 26 成功 / 1 已知失败 / 6 无判据、新增失败 0，
`GLMARK_RESULT=PASS`。同一新 Host、594 MHz、正式 cadce.../e83f...，
使用原始 ELF，没有启用分配前清零候选或合并快照候选。
标准 shared run-id 目录保留原始日志，控制机 `.command/.status` 与
`dma1-full1080-summary.json` 记录命令、退出码和摘要。
因此此次无需分配前清零诊断也得到完整 1080p 成绩，但这不证明首次错误根因。
在确认无 VM/broker/loop 后保存 dmesg、sync，发起一次 SysRq 重启卸除 OPP，
为新 Host 原生对照准备；尚不能将旧 Host 原生 1002 当作最终同环境基线。

重启后 boot-id `3b6f6ec4-dd0d-4da0-b116-e84aa71285a9`，版本仍为 dma1、
pmthor 绑定、CPU 0–1、无 OPP 模块/VM/broker，匹配 Panthor 模块 vermagic；
`dma1-pre-native-boot.log` 中 `DMA1_PRE_NATIVE_BOOT_PASS`。
启动 `glmark-opt-20261016-dma1-native` 原生两分辨率完整对照，命令：

```bash
bash /root/GPU-SFTP/log/glmark-optimization/host-dma1-deploy/native-dma1-glmark.sh \
  glmark-opt-20261016-dma1-native
```

脚本先从空闲 pmthor 切换原生 Panthor；原始 ELF 哈希经断言，使用与 Client
相同的当前严格验证 gpu-smoke.sh（哈希 84b449...），保留并恢复 rootfs 中旧脚本。
请求 600 MHz OPP、实际时钟读回 594 MHz，用户态绑 CPU2。保留完整时钟记录。
结束时不解绑工作后的 Panthor；先保存结果、恢复/卸载本次挂载，再重启恢复 pmthor。
该对照仍在运行，不能提前报告退出码或成绩。

合并快照 runner 已提供环境开关 `GLES_CLIENT_FUSED_SNAPSHOT=0|1`，通过
统一 boot-arg helper 传给 IOCTL 与 GLES Client；默认 0，非法值拒绝。
Client 的 OPEN_SESSION 日志记录协商 feature bits 和实际选择的快照路径，
便于后续确认旧 Proxy 回退。新增日志后 Client v2 重新编译通过，
具体 SHA-256 见 `build/glmark-optimization/fused-snapshot-v2-images.sha256`。
本轮未替换正式 Client/Proxy 运行镜像，未在原生测试期间启动其他硬件回归。

### 新 Host 原生对照进展

原生 `glmark-opt-20261016-dma1-native` 的 720p profile 已退出 0，完整 33 场景，
score **1441**，严格验证 26 成功 / 1 已知失败 / 6 无判据、新增失败 0。
Clientproxy 同 Host 720p 为 **938**，分数保留率 **65.09%**。
这说明剩余差距在新 Host 上仍存在；Host DMA 候选没有消除 RPC/缓存等路径开销。
逐场景统计 `build/glmark-optimization/dma1-720-comparison.json`，原生日志
`GPU-SFTP/log/glmark-optimization/glmark-opt-20261016-dma1-native/native-1280x720.log`。
原生 1080p 仍在执行，原生脚本整体退出码及最终清理状态尚不能判为通过。

随后原生 1080p 和板端脚本完成，两个 profile 及板端 `exit-code` 文件均为 0，
两个分辨率均为 33 场景、26/1/6 严格验证、无新增失败。
本次 /dev 挂载曾短暂 busy，脚本有界重试后清理成功，最终无本次挂载或 loop。
工作后的 Panthor 未解绑；保存证据并 sync 后发起一次 SysRq 重启恢复 pmthor。
原控制机 SSH 命令在板端进程结束后仍未返回，因此其外层退出码应与板端
工作负载/脚本退出码分开记录，不能省略收尾异常。

| 新 Host、594 MHz | 原生分数 | Clientproxy 分数 | 分数保留率 | 33 场景 FPS 比几何均值 | 帧时间增加中位数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1280×720 | 1441 | 938 | 65.09% | 69.42% | 0.289 ms |
| 1920×1080 | 1004 | 777 | 77.39% | 81.10% | 0.242 ms |

原生日志完整取回 `GPU-SFTP/log/glmark-optimization/glmark-opt-20261016-dma1-native/`；
与共享路径逐场景参数/顺序对齐，比较程序断言双方各恰好 33 项、严格验证通过。
比较数据 `build/glmark-optimization/dma1-native-client-comparison.json`，同名 `.md`
包含两分辨率全部 66 行场景比较；不将总分比例当作单一应用固定开销。
检查本次保存的 Host dmesg 未发现 BUG/Oops/WARNING/DMA-API/reset failed 记录。


### 融合快照语义首轮失败与 UAPI 构建修正

首轮固定四组合 `glmark-opt-20261016-fused-snapshot-{on,off,fallback,oldclient}`
均退出 1：两次 DRM session 都在 empty export 返回 ENOENT(2)，期望 EINVAL(22)。
保留全部失败，不将其归因于融合 RPC。退出恢复镜像成功（restore exit-code=0），
板端已确认恢复 cadce... Client / e83f... Proxy、无 VM/broker、pmthor 绑定。

代码核对发现探针构建默认包含控制机 `/usr/include/drm/drm.h`，其
`drm_syncobj_handle` 新增 `point` 字段，结构大小 24、HANDLE_TO_FD 编号
`0xc01864c1`；目标 6.12 内核为 16 字节、`0xc01064c1`。
前端按完整 cmd 匹配，因此新编号走 DRM core 回退，在前端独立管理的 handle
之外查找对象而返回 ENOENT。此前快照 PASS 使用的旧探针不能证明新构建的 ABI 正确。

已修正 `scripts/build/build-panthor-ioctl-smoke.sh`：默认以目标 Guest 内核
`headers_install` 导出的 UAPI 编译，同时保留显式 DRM_UAPI 覆盖。
直接包含未导出的内核头第一次编译失败（__user 注解），亦保留 build 日志；
改用正式 headers_install 后构建退出 0，新探针 SHA-256
`f1b16dbebfe88b352d6f1e4c37e7e3e51f83a0b805d18f705f9f4c0b345007a8`。
独立大小/编号打印程序确认上述差异；测试源码及 errno 判据没有放宽。
新一轮使用独立 `glmark-opt-20261016-fused-uapi-snapshot-*` run-id，结果待验证。

原生对照的控制机 SSH 收尾现已确认：板端脚本及两 profile 均退出 0，
原控制机 SSH 在工作完成、证据取回、板端重启恢复后仍未返回，核实 PID 213504
命令归属后仅对该 SSH 发 SIGTERM，最终控制机外层退出 255。
`dma1-native-ssh-cleanup.json` 保留动作；不能将外层也写成 PASS。
当前 boot-id `e9a252ce-34bf-47b2-808b-635bfb23e888`，恢复 pmthor，OPP 模块未加载。


目标 UAPI 探针复测四组合全部退出 0，suite=0、restore=0：
`glmark-opt-20261016-fused-uapi-snapshot-{on,off,fallback,oldclient}`。
各自 Client 日志均有 `PANTHOR_SYNC_FILE_SNAPSHOT_SMOKE=PASS exports=128
source_reset=1 source_destroy=1 drm_close=1`。on 协商 features=1/fused=1，
off=1/0，fallback=0/0；oldclient 与新 Proxy 兼容。
标准目录 `GPU-SFTP/log/shared/vmshm-1client/<run-id>/`，命令与退出码
在 `build/glmark-optimization/fused-uapi-snapshot-*.status/.log`，
runner 为 `run-fused-uapi-semantics.sh`。此结果证明上述快照语义及兼容路径，
不等于完整 32 项通过，也不证明性能收益。

空闲设备上加载与 dma1 Host 匹配的 OPP 诊断模块，实际 594 MHz。
开始固定顺序 off1/on1/off2/on2 对照，保持候选 v2 两镜像完全相同，
仅启动参数切换融合快照。原始 glmark ELF 2251...；720p、finish、
Client512MiB/Proxy384MiB、HostCPU0–3、broker0/Proxy1/Client2、静默控制台。
场景为 build use-vbo、desktop blur(radius5,passes1,separable,windows4)、terrain，
各 5 秒；严格验证保留。run-id `glmark-opt-20261016-fused-ab-*`。
尚未完成，不能提前声称优化。


### 融合快照固定 A/B 结果

四次 `glmark-opt-20261016-fused-ab-{off1,on1,off2,on2}` 均退出 0，
suite=0、restore=0。每次全量严格验证 26/1/6、新增错误 0，之后执行三个
5 秒场景。相同 v2 Client/Proxy、同一 boot、594 MHz，不改原始 ELF。

| 场景 | off1 / off2 FPS | on1 / on2 FPS | 均值变化 |
| --- | ---: | ---: | ---: |
| [build] duration=5:use-vbo=true: | 1319 / 1316 | 1354 / 1351 | +2.66% |
| [desktop] blur-radius=5:duration=5:effect=blur:passes=1:separable=true:windows=4: | 237 / 237 | 239 / 238 | +0.63% |
| [terrain] duration=5: | 50 / 50 | 50 / 50 | +0.00% |

开启后确有 SYNCOBJ_SNAPSHOT RPC：on1=8240 次、on2=8220 次，错误均 0；
off 组合没有该 RPC。on1 CREATE=8321、TRANSFER=40560；off1 分别为
16203、48095。运行帧数不同，不能直接用总次数之差声称每帧收益；
统计覆盖验证与计时，且 worker 与主线程有重叠，RPC 总耗时不可相加当关键路径。
静默控制台隐藏 OPEN_SESSION 日志，因此性能分析核对实际 boot cmdline 和
SNAPSHOT 调用计数；四组合语义测试另保留 feature 协商日志。

结论：融合 RPC 能减少通信，build 的两次同向提升约 2.66%，blur 约 0.63%，
terrain 按整数 FPS 无变化。每开关仅两次、每场景 5 秒，不作为完整 glmark
或稳定收益声明；该优化不足以解释并消除剩余性能差距，维持实验开关默认关闭。
完整双分辨率融合性能与完整 32 项尚未执行，不将本次短对照替代这些验收。

证据：`build/glmark-optimization/fused-ab-comparison.json` 包含逐次场景及去重 RPC
统计；同目录 `.command/.status/.log` 保存命令、退出码；标准 shared run-id
目录保存 Guest/Proxy/broker 日志和配置。`fused-ab-opp-setup.log` 与
`fused-ab-clock-start.log` 保留实际 594 MHz、boot-id、温度。

下一处已从源码确认的开销来源：`client_comm_vmshm_call()` 在 IRQ 模式下仍以
全局 rpc_lock 覆盖发送至响应完成；快照 worker 的 wait/destroy 会与用户提交
争抢同一锁。底层 send 有独立队列锁，IRQ 接收按 seq/type 匹配 waiter，且现有
burst 自测已具备多个 waiter 的基础。因此可进一步验证 IRQ 模式下并发在途 RPC
能否缩短排队时间；尚未实现/验证，不能提前宣称安全或性能收益。

本轮结束前已恢复正式 Client/Proxy 镜像，确认无 VM/broker/挂载/loop，
保存 Host dmesg（未发现 BUG/Oops/WARNING/DMA-API/reset failed）后单次 SysRq 重启。
重启观察第一轮 SSH timeout、第二轮 connection refused，均保留，没有因此重复复位。
第三次检查退出 0：`FUSED_AB_RECOVERY_PASS`，boot-id
`a9ed949a-9751-4abb-ba41-a3712f3534d4`，Host dma1、pmthor、CPU0–1、GPU198MHz，
OPP 诊断模块已随重启卸除，镜像仍为 cadce.../e83f...。
证据 `build/glmark-optimization/fused-ab-recovery-attempt3.log`。
本轮有实质进展（定位并修正探针 ABI、完成四组合语义验证及四次性能对照），
但剩余性能开销尚未达到目标，目标保持进行中。

### IRQ RPC 并发候选实现与验证启动

前一轮属于实质进展：探针 UAPI 根因得到确认及修复，四组合语义与四次
融合 A/B 完成；当前目标仍未完成。本轮先确认板端仍为 boot-id
`a9ed949a-9751-4abb-ba41-a3712f3534d4`、dma1 Host、pmthor、CPU0–1、
无 VM/broker、正式 cadce.../e83f... 两镜像。

新增只读启动参数 `client_comm_vmshm.concurrent_rpc`，默认 false。
仅参数开启且 IRQ 通知已配置时，`client_comm_vmshm_call()` 不再持有 rpc_lock
跨越整个响应等待期。消息发布仍持有独立 d->lock；seq 由 atomic64 生成，
接收 worker 在 waiters_lock 内按 seq/type 匹配并完成 waiter，超时/发送失败
仍移除自身 waiter。非 IRQ 轮询分支保留串行锁，避免不同调用者消费并丢弃
彼此的响应。没有缩短超时、跳过 fence 等待或改变 GPU/内存权限。

runner 新增 `GLES_CLIENT_CONCURRENT_RPC=0|1`，默认 0，同时覆盖 IOCTL/GLES，
经引用传递并拒绝其他值。开启 RPC stats 时记录 `RPC_CONCURRENCY peak`，
其口径为重叠活跃 RPC 调用数峰值（包含发队列前短暂准备/锁等待），
不应直接解释为硬件/GPU 并发数或精确队列深度。

Client 第一版（未部署）SHA-256 04f707...；增加上述峰值计数后的 v2 构建退出 0，
完整 SHA-256 `084c9ed35d14f8aed5ad84f74b8de80532c7384a878a65e989eef533cafc1c82`。
日志 `build/glmark-optimization/client-concurrent-rpc-v2-build.log/.exit-code`。
使用正式旧 Proxy e83f...，融合快照维持关闭，以单独测量并发 RPC。
固定语义测试次序：snapshot-off、snapshot-on、transfer-on、group-on、bind-on、
compute-on（4MiB，10 次，2 预热），分别独立启动 VM，不重跑覆盖失败。
run-id `glmark-opt-20261016-concurrent-*`；测试进行中，不提前宣称通过。

上述六项固定语义测试均完成，全部外层退出 0，suite=0、restore=0。
开关关闭/开启的快照均通过 128 exports / 64 imports 与 reset/destroy/close 校验；
开启并发的 transfer、Group submit fence、异步 VM_BIND、4MiB Compute 均通过。
命令、退出码与日志：`build/glmark-optimization/concurrent-*.command/.status/.log`；
原始 Guest/Proxy 证据在标准 shared run-id 目录。不能据此宣称完整 32 项通过。

随后确认设备空闲，加载匹配 dma1 的 OPP 模块，原始 198MHz → 实际 594MHz，
见 `concurrent-ab-opp-setup.log`。开始固定 off1/on1/off2/on2 三场景短性能对照：
同一 v2 Client 084c...、正式 Proxy e83f...、融合快照关闭、原始 ELF2251...，
其余 CPU/内存/finish/严格验证条件与上一轮融合 A/B 相同。
测试进行中，结果待统计；不能把开关启用直接当作性能提升证据。


### IRQ RPC 并发固定 A/B 结果

四次 `glmark-opt-20261016-concurrent-ab-{off1,on1,off2,on2}` 全部退出 0，
suite=0、restore=0。每次严格验证 26 成功 / 1 已知失败 / 6 无判据，新增失败 0。
相同 Client084c...、Proxy e83f...、594MHz、原始 ELF、融合快照关闭。

| 场景 | off1 / off2 FPS | on1 / on2 FPS | 均值变化 |
| --- | ---: | ---: | ---: |
| [build] duration=5:use-vbo=true: | 1317 / 1314 | 1425 / 1424 | +8.29% |
| [desktop] blur-radius=5:duration=5:effect=blur:passes=1:separable=true:windows=4: | 238 / 237 | 240 / 239 | +0.84% |
| [terrain] duration=5: | 50 / 50 | 50 / 50 | +0.00% |

开启后的所有导出 RPC 统计中，`lock_wait_avg_ns` 和 `lock_wait_max_ns` 均为 0，
确认绕过了全局 rpc_lock；on1 CREATE 平均 49.58µs、TRANSFER48.33µs，
off1 分别 60.72µs、53.96µs。仍存在发送/接收队列锁及处理/通知等待，不能称为
“无锁通信”。两次每场景仅5秒，以上收益属于短场景证据，尚不能推广至完整 glmark。

峰值活跃调用计数未出现在首轮 A/B 导出日志，不能将 JSON 中缺失值0解读为实际峰值0。
核对到 gpu-smoke 的诊断 grep 只包含 CLIENT_COMM_RPC_STATS，遗漏 RPC_CONCURRENCY，
静默控制台又抑制了其直接 printk。A/B 结束后，仅给诊断 grep 增加该 marker，
没有改变测试参数、验证或性能代码；已经结束的 A/B 结果仍保留为缺少峰值证据。
分析程序据实际启动参数、真实 RPC 调用和锁等待统计确认路径，不伪造峰值。

已启动 `glmark-opt-20261016-concurrent-full720` 与后续 `concurrent-full1080`，
完整33场景，保持开关开启、融合关闭、同频/亲和性及原始ELF，且保留严格验证。
该顺序套件的 handle 是控制机 exec session12262；runner
`build/glmark-optimization/run-concurrent-rpc-full.sh`，逐项 `.command/.status/.log`，
结束 trap 恢复正式 Client 镜像。两分辨率尚未完成，不能提前给出总分或 PASS。
完整运行使用增加峰值导出的诊断脚本；与 A/B 的变化仅为日志过滤器。

### 已完成 fence 快照候选（本地构建，尚未部署）

完整并发 RPC 测试运行期间继续分析同步路径：即使导出时源 fence 已成功完成，
现有融合操作仍分配私有 Proxy syncobj，随后 Client worker 发 WAIT 和 DESTROY。
新增默认关闭的 `panthor_client.completed_snapshot` 候选，仅在融合快照开启且
双方协商新 feature bit1 时，请求允许返回“已成功完成”的快照。

Proxy 先保持源对象引用，利用 DRM 的 `drm_syncobj_find_fence()` 取得当前 fence
引用，再检查 `dma_fence_get_status()`。只有状态>0才返回完成标志及零句柄；
这次捕获即为快照时点，源对象随后 reset/reuse 不改变已捕获的成功完成。
未完成(0)或错误(<0)仍分配真实私有快照并沿用等待/错误传播。
空对象保持 EINVAL，非法句柄/会话仍拒绝。状态辅助函数不读取可变源对象两次
后再合成完成；快速返回依据的是持有引用的那一个 fence。

Client 保持自有 fence ops 和 session identity，立即 signal 本地 fence，
不创建 Proxy 私有对象/worker/DRM file 引用；因此仍可执行原有同会话 import，
且已完成导出不再依赖源对象或 DRM fd 存活。未完成路径保持原引用生命周期。
不能用通用 stub fence替代自有类型，否则现有 import 的类型检查会拒绝它。
新增 completed_exports 计数，只有成功安装 fd 后增加。

协议复用 snapshot req/rsp 的 pad 位，但必须双重选择：新 feature bit + 请求
ALLOW_COMPLETED。旧 Client 请求 pad=0 始终得到原私有句柄；新 Client 遇旧 Proxy
不发送新 flag。结构大小及旧消息编号均未改变；未识别的返回标志拒绝为 EPROTO。
此设计/代码审查不是硬件正确性证据，需后续四组合兼容、快照生命周期及实际
GPU 未完成路径验证后才能评价。

本地两角色构建均退出0：

- Client `631f9c13b568b9bd35128d2ff4766c39398268920c6bfa9c2f502726c0bf0c99`
- Proxy `0dc4315fd9686b333b116873f7bbad05ad767cdf12ff24d3bf99da91ca7eb484`

日志 `build/glmark-optimization/{client,proxy}-completed-snapshot-build.log/.exit-code`，
Image 同目录 `*-completed-snapshot.Image`。这些新镜像没有替换正在测试的
并发 RPC v2 084c.../正式 Proxy e83f...；runner 未在执行期间修改。
目前没有已完成快照快路的硬件结果，不能宣称加速幅度或通过验收。


`glmark-opt-20261016-concurrent-full720` 已完成，外层退出0、33场景，
严格验证26成功/1已知失败/6无判据、新增失败0，GLMARK_RESULT=PASS。
score **989**，此前同Host/594MHz正式Clientproxy为938，提升 **5.44%**；
原生1441的分数保留率为 **68.63%**。不是配对多次完整对照，不将该比例当作
所有应用的固定开销。`RPC_CONCURRENCY peak=4` 本次成功导出，证明确有多个
活跃RPC调用重叠（并非GPU任务并发度）。
统计 `build/glmark-optimization/concurrent-full720-summary.json`，原始日志标准
shared目录，控制机同run-id后缀 `.command/.status/.log`。1080p仍在执行，
套件整体退出及镜像恢复尚未判定。期间只读检查CPU策略schedutil、当前1.8GHz、
GPU594MHz，`concurrent-full-clock-cpu-check.log`；未在运行中修改时钟或镜像。

下一快照候选两Image已复制至板端独立实验目录并核对完整SHA-256，未安装到
运行路径、未启用。后续六组合测试helper已准备但尚未执行，必须等完整双分辨率
套件结束后再给runner增加completed_snapshot启动参数并开始硬件验收。

720p逐场景补充：normals bump +8.58%、VBO build +7.94%、height bump +7.88%、
三类texture约+7.60%至+7.84%；blur +0.84%。两个非interleave buffer场景
45→44 FPS（约-2.22%），没有隐藏回退；单次整数FPS不足以判定小回退稳定性。
`concurrent-full720-scene-changes.json` 保存33项与旧同频共享路径的逐项变化。
这些差异说明移除全局RPC排队只解决部分开销，GPU重负载/多阶段场景仍需进一步分析。


### 并发 RPC 完整双分辨率结果

`glmark-opt-20261016-concurrent-full{720,1080}` 均外层退出0，suite=0、restore=0。
各33场景、严格验证26/1/6、新增失败0，两个Guest日志均确认活跃RPC峰值4。

| 分辨率 | 原生 | 此前共享 | 并发RPC共享 | 较此前共享变化 | 原生分数保留率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1280x720 | 1441 | 938 | 989 | +5.44% | 68.63% |
| 1920x1080 | 1004 | 777 | 804 | +3.47% | 80.08% |

完整比较 `build/glmark-optimization/concurrent-full-comparison.json`，解析程序
确认双方场景次序相同、各恰好33项，并校验两侧严格验证marker及实际启动开关。
本次使用084c... Client、e83f... Proxy；融合快照关闭；不是下一631f.../0dc4...组合。
新增日志过滤后的gpu-smoke SHA-256
`b9902930a08f6165758a13c49f15d37691ae17eb34102e8406fca2f033c831c3`。
两个完整测量与既有原生测量非多次交替配对，不能将分数比例当作固定开销。

套件结束后确认无firecracker/broker、CPU0–1、pmthor、正式cadce.../e83f...镜像已恢复；
保存 `concurrent-full-host-after.log`。OPP诊断仍保留本boot 594MHz，便于后续同频实验，
不得在此模块加载状态切换GPU驱动。当前目标仍未达到，候选并发开关维持默认关闭。

确认上述套件terminal后才修改runner，新增 `GLES_CLIENT_COMPLETED_SNAPSHOT=0|1`，
默认0、引用传递至远端并验证取值，供IOCTL/GLES共同使用；运行中未编辑runner。
开始六组合快照语义测试 `glmark-opt-20261016-completed-snapshot-*`：
新组合on/off、旧融合Proxy回退、原始Proxy回退、旧Client兼容、同时启用并发RPC。
相关helper `run-completed-snapshot-semantics.sh`，结果待验证；每组合仅一次尝试。

已完成快照六组合均完成，全部退出0，suite=0、restore=0：
`glmark-opt-20261016-completed-snapshot-{on,off,oldfused,fallback,oldclient,concurrent}`。
每项均128 exports/64 imports，reset/destroy/DRM close验证通过。
on/concurrent组合日志出现snapshot_sync=0；其余四组合均未出现该标记，
确认新Proxy不会向未选择快路的旧Client返回零句柄，两个旧Proxy回退正确。
feature协商分别为新Proxy0x3、旧融合Proxy0x1、原始Proxy0x0，原始Proxy回退到两RPC。
此测试主要覆盖已成功完成的fence，不据此宣称新的未完成/错误路径已覆盖充分。

开始固定off1/on1/off2/on2性能A/B：`glmark-opt-20261016-completed-ab-*`，
同一631f...Client/0dc4...Proxy、并发RPC=1、融合快照=1，仅completed_snapshot切换。
594MHz，原始ELF2251...，三场景各5秒，每次保留完整严格验证。
分析程序将同时检查completed_exports>0及worker waits>0，确认新快路和原私有快照
路径均在实际GPU工作负载中执行；性能结果待验证，不提前声明收益。
命令/日志/状态在`build/glmark-optimization/completed-ab-*`，suite handle63554。


### 已完成快照固定 A/B 结果：未证明性能收益

四项 `glmark-opt-20261016-completed-ab-{off1,on1,off2,on2}` 均外层退出0，
suite=0、restore=0，严格验证均26/1/6、新增失败0。分析同时确认开启组合
确有completed_exports>0，且worker waits>0；快速和原私有快照路径均在真实GPU负载中执行。

| 场景 | off1 / off2 FPS | on1 / on2 FPS | 均值变化 |
| --- | ---: | ---: | ---: |
| [build] duration=5:use-vbo=true: | 1449 / 1453 | 1445 / 1446 | -0.38% |
| [desktop] blur-radius=5:duration=5:effect=blur:passes=1:separable=true:windows=4: | 240 / 240 | 239 / 240 | -0.21% |
| [terrain] duration=5: | 49 / 49 | 50 / 50 | +2.04% |

- `glmark-opt-20261016-completed-ab-off1`：completed_exports=0，worker waits=8718。
- `glmark-opt-20261016-completed-ab-on1`：completed_exports=10，worker waits=8685。
- `glmark-opt-20261016-completed-ab-off2`：completed_exports=0，worker waits=8739。
- `glmark-opt-20261016-completed-ab-on2`：completed_exports=7，worker waits=8696。

开启后每次约8700个快照仅命中7–10个已完成快路（约0.08%–0.115%）；多数导出发生在GPU
完成之前。build/blur未改善，terrain只变化1整数FPS，不能据两次5秒样本宣称稳定收益。
因此不推广此候选，不追加它的完整双分辨率性能测试，默认保持关闭。
代码与镜像保留为实验，不能作为目标已实现或性能提升的交付结论。
JSON `build/glmark-optimization/completed-ab-comparison.json` 保留每次数据及RPC统计，
各 `.command/.status/.log` 和标准shared目录保存命令、退出码及原始日志。

下一处更贴合测量结果的候选是减少无须本地等待的导出所触发的主动worker轮询：
当前每次export立即启动worker，即使用户只将sync_file导入另一syncobj后关闭fd。
可研究通过dma_fence的enable_signaling按需启动等待；未请求本地等待的导出仍保留
真实不可变Proxy快照供同步import，最后一个引用释放时异步销毁快照。
必须解决release不能睡眠、异步销毁对象/DRM file/模块生命周期和poll/回调竞态，
并以原快照生命周期测试及真实GPU提交验证。该方案尚未实现，不能预先认定收益。

本轮结束状态已检查：完成A/B后确认无VM/broker/本次挂载/loop，正式镜像恢复，
保存Host dmesg未发现BUG/Oops/WARNING/DMA-API/reset failed，单次SysRq重启卸除OPP。
恢复检查退出0，`COMPLETED_AB_RECOVERY_PASS`，boot-id
`bc08e8e8-5940-4e5f-87e7-564b8abf26e3`，dma1 Host、pmthor、CPU0–1、GPU198MHz、
无OPP模块，正式cadce.../e83f...两镜像。证据
`build/glmark-optimization/completed-ab-recovery.log`。
本轮属于实质进展：完成并发RPC完整双分辨率测量，验证并测量新的快照候选，
由约0.115%命中率证据排除其主要收益假设。剩余差距、生产PM生命周期及受影响
完整回归未完成，目标保持进行中，不将分项PASS扩展为完整32项或整体优化完成。


## 按需启动快照等待的实验候选（2026-10-16，短A/B完成）

前一轮的已完成快照快路覆盖率很低，因此本轮直接减少未被本地等待的快照的
主动轮询。已实现只读参数 `panthor_client.lazy_snapshot_wait`，默认0；runner通过
`GLES_CLIENT_LAZY_SNAPSHOT_WAIT=0|1`传递并验证。该候选不改变协议和Proxy实现，
保留原有fused快照与旧Proxy的CREATE+TRANSFER回退。

开启后export仍先在Proxy捕获真实不可变fence，并为快照持有DRM file引用；
仅在dma_fence的enable_signaling回调中为worker取得fence引用并入队，回调不做RPC、
不睡眠。内核dma-fence核心在fence自旋锁内保证该回调至多调用一次。
poll/等待请求仍走原worker、真实完成检查、错误传播和快照销毁。
仅导入然后关闭、从未请求本地通知的快照，在最后一个fence引用释放时入队独立
cleanup_work，异步DESTROY真实Proxy快照，再fput和dma_fence_free；release自身不睡眠。
import持有fence引用并在snapshot_lock下同步转移Proxy fence，清理不能抢先释放该对象。
计数器新增lazy_discards以区分这个路径与实际启动的wait worker。

Client候选Image SHA-256：
`e3aabc02ad7285792f569f6ea0cac3dc8844f63bb0f3392c87c1c00b1c33d339`。
构建命令为 `make -C Linux-Guest-GPU O=/home/mzh/gpu/build/verified-kernels/client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`，
退出0，日志 `build/glmark-optimization/client-lazy-snapshot-build.log`。
镜像仅放在本地build和RK实验目录；正式镜像由测试入口备份并恢复。
本轮开始重新检查RK boot-id仍为bc08e8e8...、dma1 Host、pmthor、CPU0–1、正式cadce/e83，
无已有VM/broker和OPP模块。新候选未推广，构建成功不等于硬件同步正确或有性能收益。


四组快照语义测试已完成：run-id均为`glmark-opt-20261016-lazy-snapshot-`前缀，
后缀on/off/fallback/concurrent；每组退出0，suite和镜像恢复退出0。
每组128次导出、64次导入，并验证源/目标reset/destroy/reuse、关闭DRM fd后poll及
SYNC_IOC_FILE_INFO的成功状态。fallback实际features=0并走旧Proxy两RPC路径，
on/concurrent实际features=3、completed_snapshot=0。Client日志未见BUG/WARNING或
unused snapshot destroy failed。该测试主要覆盖按需启动后的等待路径，
异步不等待清理路径还需真实GPU负载和lazy_discards统计验证。
命令与每项退出码见`build/glmark-optimization/run-lazy-snapshot-semantics.sh`、
`lazy-snapshot-*.status`，原始日志位于标准shared/vmshm-1client对应run-id目录。
随后只在无VM时加载匹配dma1 Host的OPP诊断模块，实际594MHz，固定四次
lazy-ab-off1/on1/off2/on2交替A/B正在执行，尚无性能结论。


首对A/B的路径统计已经确认：off1 waits=8739、polls=17456、lazy_discards=0；
on1 waits=0、polls=0、lazy_discards=8900，并且SYNCOBJ_SNAPSHOT calls=8900。
即该次GPU负载的快照全部走不等待清理路径，没有通过省略GPU完成等待来虚增FPS；
GPU同步仍通过import后的真实Proxy fence完成，frame-end保持finish。
第一对build为1452/1482、blur240/242、terrain49/50；须等第二对完成再统计，
不能把这一个短样本扩展为完整分辨率或稳定收益结论。


四次固定交替短A/B均已完成，run-id为`glmark-opt-20261016-lazy-ab-`加
`off1/on1/off2/on2`，每项退出0，suite退出0，正式镜像恢复退出0。
全部运行保持594MHz、原始glmark ELF、finish、完整33场景validation，结果
26 Success / 1已知framebuffer失败 / 6 Unknown，unexpected=0；另有三个5秒计时场景。
融合快照=1、并发RPC=1、已完成快路=0，仅lazy_snapshot_wait参数不同。

| 场景 | 关闭两次FPS | 开启两次FPS | 均值变化 |
| --- | --- | --- | ---: |
| build VBO | 1452 / 1451 | 1482 / 1480 | +2.032% |
| blur | 240 / 241 | 242 / 242 | +0.624% |
| terrain | 49 / 50 | 50 / 50 | +1.010% |

路径计数：off1/off2 waits=8739/8735、polls=17456/17441、lazy_discards=0；
on1/on2 waits=0、polls=0，lazy_discards=8900/8889，恰好分别等于
SYNCOBJ_SNAPSHOT calls=8900/8889。两次完成路径errors=0；成功清理对应的
SYNCOBJ_DESTROY统计errors=0，并保留CLOSE_SESSION/最终Host teardown日志。
因此确认候选省去了未使用的本地wait worker和轮询，并实际覆盖了异步释放路径；
不代表没有任何其他同步RPC，GPU依赖仍经import转移并由实际GPU fence约束。

这些结果仅为每条件两次、每场景5秒；terrain仅1整数FPS，不能声称稳定收益。
build的小幅提升与该项开销可移除一致，但约1.75万次后台等待轮询消失后仍仅提升约2%，
说明不能把后台轮询总耗时直接解释为渲染关键路径耗时或剩余性能差距。
下一步需要完整双分辨率和更多受影响功能覆盖，再决定是否推广；默认仍关闭。
真正未完成的还有生产PM/DVFS生命周期和完整受影响回归，目标不标记完成。

可复查入口：`build/glmark-optimization/run-lazy-snapshot-ab.sh`、
`compare-lazy-ab.py`和`lazy-ab-comparison.json`；每项`.command/.status/.log`
及标准shared目录保存实际命令、退出码、VM参数和原始Client/Proxy日志。
Host后检查`lazy-ab-host-after.log`确认无残留VM/broker/loop/本次挂载，
CPU0–1、pmthor，正式Client cadce... / Proxy e83f...，未见BUG/Oops/WARNING/DMA-API/reset failed。
本轮属于实质进展：实现新的等待生命周期候选，完成4项语义测试与4次真实GPU短A/B，
得到可移除开销与有限帧率收益的直接证据，而非仅重复状态或未执行计划。

已完成单次SysRq重启恢复：首个SSH观察连接被拒绝（退出255，原始记录另存
`lazy-ab-recovery-attempt1.log`），未重复重启；继续观察同一次重启后恢复检查退出0，
`LAZY_AB_RECOVERY_PASS`。新boot-id `e6508c38-fb8e-47f8-8e78-da90ccfb2a21`，
dma1 Host、pmthor、CPU0–1、GPU198MHz、无OPP模块/VM/broker，正式cadce/e83镜像。
最终证据 `build/glmark-optimization/lazy-ab-recovery.log`。


## 按需等待组合的完整双分辨率验证（2026-10-16，已完成）

本轮开始重新核对RK：boot-id e6508c38...、dma1 Host、pmthor、CPU0–1、正式cadce/e83、
无VM/broker/OPP模块。只在空闲时加载已验证匹配该Host的OPP模块，实际594MHz。
`run-lazy-snapshot-full.sh`按720p、1080p顺序串行运行，各完整33计时场景与33项validation，
保留原始ELF与finish，未设置场景缩减参数。
Client e3aabc02...、Proxy 0dc4315f...；参数concurrent_rpc=1、fused_snapshot=1、
lazy_snapshot_wait=1、completed_snapshot=0，其余内存/CPU亲和性与前次同频完整测量相同。
run-id为`glmark-opt-20261016-lazy-full720`、`glmark-opt-20261016-lazy-full1080`。
各`.command/.status/.log`和标准shared日志保存证据；脚本EXIT恢复正式两镜像。
尚未完成前不把短A/B收益扩展为完整场景结果。

同时增加仅统计的timeline wait分类：现有sync_file_wait_stats读取接口追加
`timeline_flags_x=总次数/单handle且非零point次数`，x为原始flags的十六进制值。
只在完成参数与handle校验、实际发起RPC之前计数，不缓存结果或跳过任何等待。
目标是区分WAIT_AVAILABLE（fence已挂入timeline）与真正等待GPU完成。
分类Client SHA-256 `5d53b3a715dafd4c26520a1c1bcaf117701f024cb8cc72a50ce90044eeff4fe9`，
构建退出0，日志`client-timeline-profile-build.log`；独立归档并上传实验目录，
未替换正在运行的完整测量镜像。待当前硬件套件结束后才执行诊断。


完整720p与1080p均已结束：每项退出0、suite退出0、正式两镜像恢复退出0。
两次各33计时场景、validation 26/1/6，unexpected=0，GLMARK_RESULT=PASS。

| 分辨率 | 同频原生旧测量 | 正式共享旧测量 | 并发RPC旧组合 | 并发+融合+按需等待 | 相对并发组合变化 | 原生总分保留率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1280x720 | 1441 | 938 | 989 | 1016 | +2.730% | 70.507% |
| 1920x1080 | 1004 | 777 | 804 | 813 | +1.119% | 80.976% |

相对正式共享旧测量（ACK修复/DMA1、同频）分别+8.316%/+4.633%；以上是总分变化，
不是屏幕呈现FPS或每场景统一提升。新组合相对并发旧组合还同时开启了融合快照，
因此不能把完整总分变化全部归因于按需等待。隔离该参数的短A/B仍以+2.032%/+0.624%为准。
原生/旧组合与新组合未做完整交替重复测量，保留单次测量和CPU条件的证据边界。

720p/1080p分别335695/268520个快照，lazy_discards与SYNCOBJ_SNAPSHOT次数完全相等；
waits/polls/errors/completed_exports全部为0，SYNCOBJ_DESTROY的RPC errors=0。
两次活跃RPC调用峰值均2，不能将此当作GPU并行度或精确队列深度。
CPU/GPU运行中采样为1.8GHz/594MHz，GPU温度约50.8°C；仅为采样，非全程温度追踪。

逐场景比较保留全部33项，不只列上涨项。相对仅并发RPC旧组合的下降项：

- 1280x720：`[bump] bump-render=high-poly:` 978→964（-1.431%）；`[effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;:` 718→689（-4.039%）

- 1920x1080：`[bump] bump-render=high-poly:` 845→836（-1.065%）；`[jellyfish] <default>:` 692→654（-5.491%）；`[terrain] <default>:` 47→46（-2.128%）；`[function] fragment-complexity=medium:fragment-steps=5:` 978→973（-0.511%）；`[loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5:` 975→967（-0.821%）

720p effect2d与high-poly bump已安排固定交替对照检查其可重复性；不能根据一对完整
运行就断言由优化导致，也不能因总分上涨而忽略。精确effect2d selector沿用原始默认
benchmarks里的kernel字符串，未改成其他卷积矩阵。
完整证据和33项比较为`lazy-full-comparison.json`、`lazy-full-analysis.log`与对应标准shared目录。
下一项timeline-profile只增加分类计数，串行执行；不混入上述性能结果。


timeline-profile已完成，run-id `glmark-opt-20261016-timeline-profile`，退出0，suite和恢复均0，
完整validation无新增失败，三个5秒计时场景结束。分类总数与RPC统计精确相等：
全部67079次均为flags=1（WAIT_ALL），且全部是单handle、非零point；
WAIT_AVAILABLE及其他flags均为0。证据`timeline-profile-classification.json`与标准shared日志。
因此排除“该负载大量查询fence是否已提交，可以仅缓存已提交point来替代这些等待”的假设。
这不是GPU完成通知或完成缓存已实现的证据，不能直接跳过WAIT_ALL。
随后只统计的v2候选补充zero-relative-timeout、success、ETIME/ETIMEDOUT计数，
用于区分零超时查询与实际阻塞等待，构建退出0，Image SHA-256
`55c40fcfdb2d588d2893ce0596a561cecdf2e8c3de61ac71ea3bae323377100b`。
未更改任何同步返回值，待当前交替测试终止后才部署。


针对完整720p中下降的两项，已完成预先固定的4次交替、每场景10秒对照。
旧组合为Client084c/Proxy e83、并发=1融合=0；新组合为Client e3/Proxy0dc，
并发=1融合=1按需=1。所有run-id为`glmark-opt-20261016-lazy-regression-`加
`off1/on1/off2/on2`，每项退出0，suite/恢复退出0，validation无新增失败。

| 场景 | 旧组合两次FPS | 新组合两次FPS | 均值变化 |
| --- | --- | --- | ---: |
| effect2d 原默认第二kernel | 716 / 746 | 686 / 686 | -6.156% |
| bump high-poly | 976 / 972 | 965 / 965 | -0.924% |

新组合effect2d两次都较低，旧组合自身有约4%的样本波动，需保留该边界；
不能因总分更高就推广新组合。精确数据`lazy-regression-comparison.json`。
该对照同时改变融合和按需两个机制，尚不能归因给其中一个。
因此预先固定同一e3/0dc镜像的四种参数组合（都关/仅融合/仅按需/都开）各两次，
顺序00、10、01、11、11、01、10、00，以减轻顺序漂移；全部保留10秒同场景和完整validation。
不重跑覆盖失败，也不更换shader、GPU完成等待或验证标准。
源码统计v2的独立诊断完成后才启动上述8次测量。


timeline-profile-v2已完成，run-id `glmark-opt-20261016-timeline-profile-v2`，每项/suite/恢复
退出均0，完整validation无新增失败。66934次timeline RPC均为单handle非零point的WAIT_ALL；
其中zero-relative-timeout=66905（99.9567%），
成功=66904，ETIME/ETIMEDOUT=30，后两者之和与RPC总数相等。
零超时和成功是独立总计，未记录交集，不能把两者误写成完全相同的请求集合。
分类结果`timeline-profile-v2-classification.json`，镜像/命令/原始日志均保留。
这指向“频繁查询已经完成的timeline point”的潜在开销；下一候选应先测量可复用的
已确认完成结果，而非将已提交误当成完成。若做本地缓存，需绑定syncobj对象和精确point，
对所有reset/signal/import/transfer/VM_BIND/GROUP_SUBMIT等变更失效，并处理并发RPC期间的
代际与在途变更，避免重置后仍错误报告完成。仅凭这些统计还不能安全删除任何WAIT_ALL。


后续本地完成结果缓存的设计边界（尚未实现）：只考虑单handle、非零精确point、
零超时且无deadline副作用的WAIT_ALL；缓存依据必须是Proxy确认的成功等待结果，
不是提交成功。任何能改变fence绑定的操作开始前失效，整个在途变更期间不得命中，
等待响应只有在同一代际、无并发变更时才可写缓存。
还必须同时审计unlocked_ioctl与compat_ioctl：当前compat非core驱动IOCTL直接走
`drm_compat_ioctl`，只包装普通ioctl会漏掉VM_BIND/GROUP_SUBMIT等变更。
私有快照worker与跨session限制也需逐项审计；不能因单线程glmark通过而放宽这些要求。
该方案只是下一候选，不计作已完成的性能优化。生产PM/DVFS的正常生命周期集成
仍然必要，目前594MHz依靠一次启动内诊断模块，未作为正式运行配置交付。


## 四组合正反顺序测量结果与当前决策

全部8次已完成，run-id为`glmark-opt-20261016-snapshot-isolation-`加
`neither1/fused1/lazy1/both1/both2/lazy2/fused2/neither2`，每项执行退出0，
suite退出0、正式两镜像恢复退出0。每次完整33项validation均26/1/6、unexpected=0；
每次只对两项回退场景计时，各10秒。所有条件使用同一e3/0dc镜像，
并发RPC=1、completed_snapshot=0，仅融合与按需参数变化，固定顺序未追加重试。
执行/正确性PASS不等于每个条件的性能都改善。

| 条件 | effect2d 两次FPS | effect2d 均值相对都关 | high-poly bump 两次FPS | bump 均值相对都关 |
| --- | --- | ---: | --- | ---: |
| 都关 | 746 / 725 | +0.000% | 972 / 974 | +0.000% |
| 仅融合 | 746 / 718 | -0.476% | 971 / 968 | -0.360% |
| 仅按需 | 723 / 718 | -2.039% | 973 / 967 | -0.308% |
| 都开 | 688 / 685 | -6.662% | 967 / 977 | -0.103% |

effect2d都开688/685，均低于另三种条件的所有样本；相对都关均值-6.662%。
仅按需均值-2.039%，仅融合-0.476%，但各仅两次且都关/融合存在约3%–4%的样本波动，
不能给出精确的单项因果占比或统计显著性结论。数据支持组合存在局部性能代价，
不能由全局总分的提升掩盖。bump在这8次中未稳定复现原先约1%下降，
保留初始完整/交替观察与这些反证，不把它定性为已确认的性能缺陷。

当前决策：不推广按需等待，也不把1016/813组合当作推荐默认配置；实验参数继续默认0。
融合快照可继续单独评估，需完整双分辨率与更广功能覆盖，不能从这两个场景推广。
当前尚未证明造成effect2d下降的具体调度、队列或fence处理原因，不能把“少了后台worker”
直接当作精确根因；需要新的控制实验才能下结论。
`run-snapshot-isolation.sh`、每项`.command/.status/.log`和
`snapshot-isolation-comparison.json`保存完整数据，标准shared run-id目录保留原始日志。

本轮共完成2次完整分辨率测量、2次只统计诊断、4次旧/新定向对照、8次同镜像隔离测量，
共16次独立运行；不是16项功能矩阵，也不是完整32项回归。新证据排除WAIT_AVAILABLE
优化假设，确认多数timeline请求是零超时完成查询，并识别组合的effect2d回退，
改变下一步优化选择。仍需正常生命周期的PM/DVFS、可验证的完成查询优化及受影响
功能回归；整体目标继续进行，不标记完成。

结束前Host检查`snapshot-isolation-host-after.log`确认正式cadce/e83、pmthor、CPU0–1，
无VM/broker/loop/本次挂载，无BUG/Oops/WARNING/DMA-API/reset failed或私有快照销毁错误。
随后仅执行一次SysRq重启以释放诊断OPP引用，恢复检查结果另记。

单次重启后的恢复检查退出0，`SNAPSHOT_ISOLATION_RECOVERY_PASS`：
boot-id `7aaae98e-12ff-4a3d-b63a-8058ca029986`，dma1 Host、pmthor、CPU0–1、
GPU198MHz，无OPP模块/VM/broker，正式Client cadce...和Proxy e83f...，
记录 `build/glmark-optimization/snapshot-isolation-recovery.log`。
本轮全部构建/测试/恢复进程均已结束，无正在后台运行的硬件套件。

## 精确完成点缓存：实现与六项语义验证

上述“尚未实现”的候选现已实现，仍默认关闭：
`panthor_client.completed_wait_cache=0`。候选 Client Image SHA-256 为
`9af256369c1affaf1cd370fc958e0d7e2d4326f2b515727b56d6a513c303ccbd`，
构建命令为 `make -C Linux-Guest-GPU O=/home/mzh/gpu/build/verified-kernels/client ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=/home/mzh/gpu/build/verified-kernels/firmware -j8 Image`，
退出0，日志 `build/glmark-optimization/client-completed-wait-cache-build.log`。
无需新增协议，使用正式 e83f... Proxy。

缓存绑定实际 syncobj 对象、精确非零 point、文件代际，只处理单 handle、
恰好 WAIT_ALL、相对超时为0的请求；Proxy 确认成功后才记录。
不将较大 point 的完成推广到较小 point，也不把提交成功当成完成。
任何未明确列入只读白名单的 IOCTL 在开始时推进代际，整个在途变更期间禁止命中和记录；
即使 IOCTL 失败也失效。代际溢出后永久禁用该文件缓存。普通及 compat 非 core 路径均包装，
VM_BIND/GROUP_SUBMIT 因而也覆盖。采用文件级失效，正确性保守，实际命中率尚待测量。

新增探针进行16轮 reset、sync_file 导入、destroy/recreate、下降 point 检查，
每次清空/替换后的旧 point 必须返回精确 EINVAL；现代48字节及历史40字节
timeline wait ABI 都执行。它们均为 ARM64 用户态，不是实际32位 compat 运行验证。
探针构建退出0，日志 `wait-cache-probe-build.log`，二进制 SHA-256
`7fadd15223ac2bdd594ce33eedc3e7fa43da162e1dd64a0b5bab7341bbdd312c`。

| run-id 后缀（前缀 glmark-opt-20261016-wait-cache-） | 缓存 | 并发RPC | 用例 | 退出码 |
| --- | ---: | ---: | --- | ---: |
| off | 0 | 0 | timeline wait及新增失效检查 | 0 |
| on | 1 | 0 | timeline wait及新增失效检查 | 0 |
| concurrent | 1 | 1 | timeline wait及新增失效检查 | 0 |
| snapshot | 1 | 1 | 不可变sync_file快照 | 0 |
| bind | 1 | 1 | 异步VM_BIND同步 | 0 |
| group | 1 | 1 | Group提交同步点 | 0 |

三项 timeline 运行均有 `PANTHOR_TIMELINE_CACHE_INVALIDATION_SMOKE=PASS iterations=16`。
on/concurrent 的 cache_hits=32、cache_candidates=144、cache_records=32，
flags1实际RPC=112；off 的 hits=0、flags1实际RPC=144。
这证明探针中的重复查询减少了32次RPC，不证明 glmark 有同样命中率。
其余三个用例按各自原有 marker 和整体 RESULT 判定，未代替完整32项回归。
运行脚本 `build/glmark-optimization/run-wait-cache-semantics.sh`，suite退出0；
每项 `.command/.status/.log` 保存完整命令与退出码，原始日志位于
`GPU-SFTP/log/shared/vmshm-1client/<run-id>/`。
正式 Client 恢复退出0，记录 `wait-cache-semantics-restore.log`。

随后开始同候选镜像的 off/on/off/on glmark 控制实验，保持 concurrent=1、
fused/lazy/completed_snapshot=0，只改变完成点缓存；尚在测量时不声称性能改善。
本次固定OPP诊断确认原始198MHz、请求600MHz、实际594MHz，
`wait-cache-perf-opp.log` 保存模块/Proxy哈希及内核日志。结束后必须重启释放诊断引用。

### 精确完成点缓存的实际 glmark 对照：没有收益

`run-wait-cache-perf.sh` 四次预定 off/on/off/on 全部完成，suite退出0，
正式镜像恢复退出0。run-id 前缀 `glmark-opt-20261016-wait-cache-perf-`，
后缀 off1/on1/off2/on2；每项 `.command/.status/.log` 保存命令和退出0证据，
原始日志在标准 shared run-id 目录。四次均使用9af... Client、e83... Proxy，
concurrent=1，其余快照实验参数全0，GPU实际594MHz，720p、finish、原始glmark ELF。
每次完整33项 validation 为26 Success /1已知Failure /6 Unknown，unexpected=0；
计时仅三个场景各5秒，不是四次完整计时矩阵，也不是完整32项功能回归。

| 场景 | 关闭缓存两次FPS | 开启缓存两次FPS | 开启均值相对关闭 |
| --- | --- | --- | ---: |
| build VBO | 1430 / 1426 | 1427 / 1412 | -0.595% |
| desktop blur | 240 / 240 | 240 / 238 | -0.417% |
| terrain | 50 / 50 | 50 / 50 | 0.000% |

开启两次分别 candidates=66302/66019、hits=1/1（约0.0015%），
records=66269/65991、mutations=159909/159103。关闭两次 hits=0。
故当前文件代际+精确point的保守缓存虽然通过定向语义检查，
却几乎不能减少真实 glmark 的RPC，不作为推荐配置；未证明微小下降具有统计显著性。
解析脚本 `compare-wait-cache-perf.py`、结构化结果 `wait-cache-perf-comparison.json`。
不能从大量成功/零超时查询推导“同一对象同一点反复查询”，也不能未经测量就
将所有未命中归因于文件级失效。

为区分原因，另增只读分类统计：empty（对象尚无记录）、point（已有记录但点不同）、
epoch（同一点但代际改变）、blocked（在途变更/代际溢出）。point优先于epoch，
因此point计数不代表代际一定未改变。分类不修改任何命中/失效规则。
该版本构建退出0，日志 `client-wait-cache-miss-build.log`，镜像SHA-256
`39aad902fa98ccd8b4359ee9ef04468d3d60018d865eca00d40e05a0b0fdb834`，
本地及板端归档 `client-wait-cache-miss.Image`；一轮诊断正在执行，结果另记。

源码审查还确认 `panthor_submit_ctx_push_jobs{,_stats}` 在返回前调用
`panthor_submit_ctx_push_fences`，后者执行 add_point/replace_fence。
VM_BIND及GROUP_SUBMIT经这些提交路径，不能把异步GPU执行误认为fence绑定也在IOCTL后异步替换。
此审查不代替多线程失效竞态压力测试，后者仍未执行。

### 未命中诊断结果及下一步

诊断 `glmark-opt-20261016-wait-cache-miss-on`、suite与正式镜像恢复均退出0，
validation仍26/1/6、unexpected=0，三个计时场景1423/239/50 FPS。
candidates=66055，hits=1，empty=4，point=33387，epoch=32663，blocked=0，
各分类加hits严格等于candidates。实际timeline RPC=66083（含非候选请求），
records=66025，mutations=159326。结构化结果 `wait-cache-miss-classification.json`。

这排除“只有新point所以缓存绝无机会”的说法：32663次检查具有相同记录point，
只是文件代际已失效。但这些变更是否影响目标syncobj、是否可安全保留旧point证明，
尚未逐操作归因；不能直接宣称按对象失效一定减少32663次RPC或提高相同比例FPS。
下一步应记录造成同point失效的变更种类并审计目标对象，区分无关BO生命周期操作、
对其他syncobj变更、对本对象reset/import/transfer/提交；只有确认不改变该证明的操作
才能排除。对新point和旧point映射可变性的保护仍必须保留。

本轮实际完成六项语义、四次性能控制、一轮分类诊断，共11次独立运行；不是完整32项。
所有均退出0，但当前缓存没有性能收益，仍默认关闭。
截至这里测试套件与构建均终止，正式cadce/e83镜像恢复，CPU0–1、pmthor、无VM/broker；
`wait-cache-host-after.log`保存重启前完整状态及dmesg。
已请求一次SysRq重启释放诊断OPP引用，重启后恢复检查另记。

重启第一次SSH观察退出255（连接超时），保留 `wait-cache-recovery.log`，没有再次复位。
对同一次重启的第二次观察退出0、`WAIT_CACHE_RECOVERY_PASS`，
boot-id `5410174b-8c02-4467-b7ad-b9508fe01162`；dma1 Host、pmthor、CPU0–1、
GPU198MHz，无OPP模块/VM/broker，正式cadce/e83镜像哈希正确。
证据 `build/glmark-optimization/wait-cache-recovery-observation2.log`。
重启前dmesg扫描未发现BUG/Oops/WARNING/DMA-API/reset failed。
当前无正在运行的本轮构建、上传或硬件套件。整体性能目标仍未完成：
完成查询优化未取得收益、生产PM/DVFS及候选正式回归仍待推进，不能宣称已交付合理开销配置。

## BO 操作保留完成缓存的候选

继续审计发现三个可以明确保留已完成证明的命令：BO_CREATE、BO_MMAP_OFFSET、GEM_CLOSE。
Client 创建路径只创建payload/BO并插入bos表，mmap offset只分配BO映射偏移；
关闭路径从bos删除并最终发送BO_DESTROY。Proxy BO创建/销毁最终分别调用
`panthor_vmshm_bo_create_from_payload` / `drm_gem_handle_delete`，不替换公开syncobj fence；
Client延迟BO销毁同样不修改syncobj。已完成fence不因这些BO生命周期操作恢复为未完成。
因此将这三个精确命令加入fence-preserving白名单；其他未知操作仍按可能变更处理，
VM_BIND/GROUP_SUBMIT/reset/signal/import/transfer的失效保护保持。
仍是文件级代际，只减少已审计的无关失效，不宣称已实现完整按对象失效。
整个完成缓存参数仍默认0。

该候选Client镜像SHA-256
`e800a161dc03e5914a01fbf26fcfa2fae5cee43bbdd6bf2216621cc3a6934833`，
构建命令与上轮相同，退出0，`client-cache-bo-preserve-build.log`保存日志，
归档`build/glmark-optimization/client-cache-bo-preserve.Image`及板端owned目录同名文件。
对照为分类统计版本39aad...，两版只差这三个命令白名单及相关注释。

探针扩展：每轮point7的现代/历史ABI两次等待之间插入一个4KiB BO的创建、
mmap offset查询和关闭；随后继续reset、import、destroy/recreate、下降point旧检查。
新marker追加`bo_lifecycle=16`；不额外创建VM以免VM生命周期失效掩盖BO保留行为。
探针构建退出0，`cache-bo-probe-build.log`，SHA-256
`b29d553540a0aa6b0be3d881c671efd94ac7e74fdc37722b67a4173f009a6a39`。
本轮Host初始boot-id `5410174b-8c02-4467-b7ad-b9508fe01162`，dma1、pmthor、
CPU0–1、正式cadce/e83镜像、无VM/broker；无刷新固件/SD操作。

六项语义验证已全部完成：run-id前缀`glmark-opt-20261016-cache-bo-semantics-`，
后缀off/on/concurrent/snapshot/bind/group，对应与上一轮同六种组合及用例。
每项退出0、整体suite退出0、正式Client恢复退出0；
`run-cache-bo-semantics.sh`及每项`.command/.status/.log`保存命令、配置及退出码，
原始日志位于标准shared目录。三项timeline均追加bo_lifecycle=16且失效检查PASS；
on/concurrent命中32/候选144，实际flags1RPC112，off命中0、实际flags1RPC144。
快照导出128/导入64及源reset/destroy/DRMclose检查PASS，
VM_BIND_ASYNC_SYNC、GROUP_SUBMIT_SYNCPOINT marker均PASS。
这是定向语义覆盖，非完整32项；多线程reset/查询交错压力及实际32位compat仍未运行。

随后在同一次启动内仅空闲pmthor时加载既有匹配OPP诊断模块，
记录`cache-bo-perf-opp.log`：198MHz→请求600MHz、实际594MHz。
`run-cache-bo-perf.sh`按旧/新/旧/新固定顺序开始测量，
两版都设置completed_wait_cache=1，并发RPC=1，fused/lazy/completed_snapshot=0，
formal e83 Proxy不变，每项三场景各5秒并完整33项validation。
此处off/on后缀表示BO保留策略旧/新，**不表示缓存关闭/开启**；
每项`.images.sha256`区分39aad...旧版与e800...新版。

### BO保留策略交替测量：三个短场景均提高

四次固定顺序旧/新/旧/新已全部完成，每项退出0、suite退出0、正式镜像恢复退出0。
run-id前缀`glmark-opt-20261016-cache-bo-perf-`，后缀off1/on1/off2/on2。
两版都开缓存，严格validation每次26/1/6、unexpected=0。

| 场景 | 旧策略两次FPS | BO保留两次FPS | 新策略均值提升 |
| --- | --- | --- | ---: |
| build VBO | 1425 / 1419 | 1507 / 1507 | +5.977% |
| desktop blur | 239 / 239 | 250 / 249 | +4.393% |
| terrain | 50 / 50 | 53 / 54 | +7.000% |

旧策略 hits/candidates=1/66226、1/66035；新版22246/69623、23959/70007，
命中率约31.95%/34.22%。实际flags1RPC旧66254/66063、新47406/46077；
新版FPS增加意味着总工作量不同，RPC绝对数差值不应解释为固定工作量下的精确节省比例。
所有同步快照worker errors=0，fused/lazy/completed snapshot均未启用。
命中和计时数据都支持这三个已审计BO操作的保留策略有实际收益，
但未单独计数三者各自贡献，不能只将收益归为其中某一个命令。
解析脚本`compare-cache-bo-perf.py`及`cache-bo-perf-comparison.json`；
每项完整命令/退出码/镜像哈希和原始Client/Proxy日志均保留。

为检查全局及局部回退，已启动720p/1080p全部33场景计时，
脚本`run-cache-bo-full.sh`，run-id `glmark-opt-20261016-cache-bo-full720` / `...full1080`，
同e800/e83、cache=1、concurrent=1，其余实验快照参数0，固定594MHz。
完成前不将短场景收益外推至总分，也不改变正式默认值。

### 常规 OPP 控制候选：仅构建，未部署

等待全场景测量期间完成Host候选`6.12.0-opencca-pmthor-opp1`，尚未用于任何硬件测量。
新增标准OPP/devfreq userspace控制，取设备树OPP并由标准接口调整电压/频率，
初始推荐OPP保持启动频率；若启用DEVFREQ_THERMAL则注册OF cooling设备，
经devfreq QoS接受热限频。没有伪造GPU利用率，尚不提供自动负载调频或runtime suspend。
目标是在后续同频测量中使用标准sysfs频率策略，摆脱不可卸载诊断模块和每轮释放引用的重启。

同时将core/stacks/coregroup时钟改为managed enabled获取，电源域detach也由devres管理，
修补旧probe失败不完整回收和remove只关闭core的路径；
devres按cooling→OPP notifier→devfreq→OPP/supply→domain→clock顺序释放。
频率更新经owner_lock与owner teardown/reset互斥。普通GPU执行可调整频率，
但目前只有显式userspace策略，不能宣称与原生ondemand等价。

构建命令：`make -C Linux-Host-GPU O=/home/mzh/gpu/build/glmark-optimization/host-dma-build ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-pmthor-opp1 -j8 Image modules`，
退出0，日志`host-opp1-build.log`；modules_install到独立staging也退出0，日志
`host-opp1-modules-install.log`。Image SHA-256
`e6afec016da5676293466e4c69f9ac9194fa4515acb94fc8020c70ab8ae14cb6`，
归档`host-opp1.Image`；模块位于`host-opp1-modules/lib/modules/6.12.0-opencca-pmthor-opp1/`，
Panthor vermagic与该release一致。旧已部署dma1 Image在修改构建目录前校验为0ba8...并保留
`host-dma1-before-opp.Image`。编译成功不证明板端供电、cooling、回收或功能正确，
必须在当前测量结束后另部署验证；当前板端仍运行原dma1 Host。

### BO保留完成缓存：两分辨率完整计时结果

两项run均已完成且分别退出0，正式镜像恢复退出0，controller suite进程261772已终止。
中途工具会话句柄丢失，但controller/板端同run-id的真实进程持续可见，未重启套件；
外层suite.exit-code没有写出，故不把推导的聚合状态伪装成捕获的外层退出码。
逐项`.status`、restore.exit-code及实际日志作为结果依据。

| 模式（同dma1 Host、实际594MHz） | 720p score | 1080p score |
| --- | ---: | ---: |
| 原生历史同频对照 | 1441 | 1004 |
| 正式共享ACK修复/DMA1 | 938 | 777 |
| 仅并发RPC候选 | 989 | 804 |
| 并发RPC+BO保留完成缓存 | **1023** | **841** |

新候选相对仅并发RPC为+3.438% /+4.602%，原生分数保留70.992% /83.765%。
这是各分辨率一次完整计时与先前同频完整基线的比较，不是当前启动内原生/共享交替测量；
受控的因果支持来自前述四次短场景旧/新对照。不能声称总分差异完全由缓存单因素精确决定。
两个run均有全部33项计时和原有严格validation26/1/6，unexpected=0，
快照worker errors=0、SYNCOBJ_DESTROY RPC errors=0；并发峰值至少2。
720p缓存292365/867352（约33.71%），1080p306427/718643（约42.64%）。
融合/按需/已完成快照实验全关闭，未重现它们组合的effect2d明显回退：
720p该场景748 FPS，对照仅并发718（+4.18%），high-poly bump1012 vs978（+3.48%）。

仍保留局部下降：720p interleaved-buffer 65→64（-1.54%）、
loop fragment-uniform 1238→1224（-1.13%）、部分conditionals约-1%；
1080p非交织buffer两项45→44（-2.22%）、交织65→64（-1.54%）。
低FPS buffer的1 FPS差异不能与高FPS场景的相同比例混为精确显著性，
且各只有一个完整样本；这些下降尚未做同镜像缓存开关交替复核。
解析`compare-cache-bo-full.py`、`cache-bo-full-comparison.json`保存全部33场景，
不能仅以总分掩盖这些记录。

测量中一次Host采样`cache-bo-full-host-sample.log`实际594MHz，GPU51.769°C；
不是全程热/频率采样。结束状态`cache-bo-full-host-after.log`确认pmthor、CPU0–1、
正式cadce/e83、无VM/broker，保存完整dmesg。本轮不是完整32项功能回归。

Host常规OPP候选自审补充：opp1虽然编译成功，但其资源逆序会先释放供电再关时钟，
因此不部署该版。修正为先移除devfreq/cooling回调，再显式释放managed enabled时钟，
然后释放供电和domain；还将电源初始化放到IRQ注册前，避免action注册OOM即时关钟后
IRQ错误清理继续访问设备。修正后的release为`6.12.0-opencca-pmthor-opp2`，
最终源码重新构建Image/modules退出0，`host-opp2-final-build.log`。
opp1的构建、未执行硬件验证和取代原因保留，不写成硬件失败或通过。

### 常规 OPP 控制：部署前资源释放复核

opp2也未刷写。复核`drivers/base/devres.c`发现`release_all`先将资源项移出设备链表，
因此action内再调用`devm_clk_put`无法找到该资源，可能触发WARN。
已用对称的`clk_prepare_enable`/`clk_disable_unprepare`替代嵌套managed释放；
三路时钟在供电之后启用，最后一路成功后注册直接关闭三路时钟的action，
中途失败逐路回退。最终释放顺序为cooling→notifier→devfreq→关闭时钟→供电→domain。
最终候选release为`6.12.0-opencca-pmthor-opp3`，Image/modules构建与modules_install均退出0，
日志`host-opp3-build.log`、`host-opp3-modules-install.log`及对应`.exit-code`。
Image SHA-256：`5a692bc15bcd7e456820385c3b6c6a55304e358b067c61ebe7032ecbe21c1a6f`。
opp1/opp2均为部署前淘汰构建，不计硬件测试PASS或FAIL。

运行入口新增可选`GLES_HOST_GPU_OPP_HZ`，使用Host devfreq userspace接口选择设备树中的精确OPP，
保存原governor及原请求频率，退出时恢复；保留原min/max及thermal限制，受限无法达到请求值则失败。
恢复失败将run退出码置90。无该环境变量时不调整策略。
若原userspace请求是`undefined`，恢复原当前OPP，不能称恢复其内部未设置标志。
该入口和新Host仍须硬件验证，不能以`bash -n`/编译成功替代。

部署前`apply-local-patches.py --check`实际退出1：固定`opencca-flash`子模块未初始化。
保存`opp2-patch-manifest-check.log`及退出码，不将其写成PASS，也不reset已有补丁。
本轮仅使用仓库kernel分区构建/刷写入口更新Host内核，不构建或刷写OpenCCA固件；
Pi现有loader SHA-256已核对为manifest固定的`4cc43c2ff29e08b5491b4d52528346aa7da6948128c17e670ff8a000029c9408`。
现有SD kernel分区备份SHA-256为`a35def75e7729949695c31c726ba4f743bef7762304390935c0e085c42a9dc94`，
控制机、RK及Pi各保留一份；文件名含opp2，内容是当前可启动dma1基线。

### opp3 Host 已部署：标准 OPP 基础验证

仅SD storage ID 2的p3 kernel分区写入，未刷固件或root分区。wrapper dry-run及实际刷写均退出0，
实际写入前在线布局及Pi读取GPT检查均通过。命令为
`flash-rk3588-via-pi.sh --kernel-image build/glmark-optimization/host-opp3-deploy/kernel-opp3-extlinux.img --flash-kernel --wait-rk`，
实际输入为该路径的绝对路径。分区镜像SHA-256为
`e0cb4f31ff053e7bb9ff67677d6e304cc51104471ddd7b0da5a0e9d8417563d8`；
匹配initrd SHA-256为`e2c9121785c3748cf4f99ed01277b03f05edf940e72a1894f23d17a06aa1028f`，
DTB沿用已核对的baseline。日志`opp3-prepare-initrd.log`、`opp3-build-kernel-slot.log`、
`opp3-flash.log`及对应退出码均保留在ignored build目录，不提交含凭据的原始刷写命令日志。

启动ID为`de6db746-7603-440b-bd2b-528d3adaf559`，release确认为opp3，
`/dev/kvm`、`/dev/pmthor`及pmthor绑定正常，没有加载旧OPP诊断模块。
启动等待中曾SSH暂不可达，通过同次启动UART确认进入系统，没有再次复位或刷写。
完整dmesg保留`opp3-boot-dmesg.log`；没有BUG/Oops/WARNING，
但存在`efi.mount`试图将ext4 kernel分区当FAT挂载失败，以及其他外设初始化错误，
不将此次启动写成所有systemd单元/外设全部健康。

`opp3-opp-hardware-check.log`及`.exit-code=0`：设备树可用OPP为300/400/500/600/700/800/900/1000MHz；
启动OPP是300MHz，不是先前diagnostic实验的198MHz。
标准userspace请求600MHz，nominal cur_freq=600MHz，实测clk_gpu=594MHz；
恢复启动OPP后nominal/actual均300MHz。
`devfreq-fb000000.gpu` cooling注册成功，状态0、max_state=7；这证明注册及接口存在，
未实际升温触发热节流，也未证明自动负载调频或runtime suspend。

运行入口两个负例run-id为`glmark-opt-20261016-opp3-opp-invalid`（bad）及
`...-unsupported`（123456789Hz），各实际退出2，在VM启动前拒绝，
之后无firecracker/broker，频率保持300MHz、CPU0–1。
负例拒绝是预期结果，不计作GPU工作负载PASS。
随后启动同e800 Client镜像缓存OFF/ON/OFF/ON四次对照，标准OPP请求600MHz，
并发RPC开启，其余三个快照实验关闭；每次仍执行严格33项validation。
run-id前缀`glmark-opt-20261016-opp3-cache-ab-`，完成前不宣称性能或频率恢复已通过。

### opp3 同镜像缓存开关交替：四项均完成

上述四次run均实际退出0，外层suite与正式镜像恢复也均捕获退出0。
每次严格33项validation均为26 Success/1已知Failure/6 Unknown，unexpected=0；
worker errors=0。e800 Client与e83 Proxy固定不变，仅缓存OFF/ON/OFF/ON，
concurrent=1，fused/lazy/completed_snapshot=0；720p，各场景每次5秒。
每项`host-gpu-opp.log`均记录实际594MHz及恢复userspace/300MHz PASS。

| 场景 | 缓存OFF两次FPS | 缓存ON两次FPS | 均值变化 |
| --- | --- | --- | ---: |
| build VBO | 1429 /1421 | 1512 /1513 | +6.140% |
| desktop blur | 240 /239 | 251 /251 | +4.802% |
| terrain | 50 /50 | 54 /54 | +8.000% |
| conditionals fragment-steps=5 | 1297 /1282 | 1298 /1291 | +0.388% |
| buffer interleave=true map | 65 /65 | 65 /64 | -0.769% |

这次对照更直接支持完成缓存的前三场景收益，而非仅支持旧/新失效策略差异。
conditionals未重复此前约1%的下降，但buffer仍有一次1 FPS下降，
不能宣称所有场景均改善或已经排除局部回退；短场景也不能替代新Host完整总分。
开启时hits/candidates分别24025/84182、24081/84218（约28.5%），关闭时两计数均0。
各run完整命令/状态/镜像SHA保存在`build/glmark-optimization/opp3-cache-ab-*.command/.status/.images.sha256`，
Client/Proxy/OPP日志位于标准shared run目录；解析`compare-opp3-cache-ab.py`，
结构化结果`opp3-cache-ab-comparison.json`。

OPP约束负例`glmark-opt-20261016-opp3-opp-capped`：测试临时将既有max_freq设500MHz，
请求600MHz，标准devfreq实际选择500MHz，入口退出2且未启动VM；
cleanup仍恢复原300MHz，未绕过max限制，外层随后恢复原max_freq=1000MHz，退出0。
`opp3-opp-cap-check.log`、`opp3-opp-cap-restore.log`及对应退出码保留。
此为用户QoS上限测试，不是实际高温触发thermal节流实验。

### opp3 生命周期、同步语义及计算验证

所有硬件测试顺序执行，没有并行运行两套回归。

| 验证 | 命令/run-id | 捕获退出码及依据 |
| --- | --- | --- |
| PFN生命周期程序 | `timeout 35 /root/GPU-SFTP/firecracker-bins/bin/pmthor-pfn-lifetime` | 0；`opp3-pfn-lifetime.log/.exit-code` |
| PFN内核日志检查 | `python3 GPU-SFTP/tests/pmthor-pfn-lifetime/check_kernel_log.py build/glmark-optimization/opp3-pfn-lifetime.log` | 0；两关闭顺序、每种32次翻译、唯一页引用/最终reset后释放均通过；`opp3-pfn-log-check.log/.exit-code` |
| pmthor空闲解绑/重绑定 | 向platform pmthor的unbind/bind写`fb000000.gpu`，无VM/broker | 0；解绑后devfreq及/dev/pmthor消失，重绑定后重建，cooling重新注册，300MHz；`opp3-pmthor-rebind.log/.exit-code` |
| 六项同步语义 | `glmark-opt-20261016-opp3-cache-semantics-{off,on,concurrent,snapshot,bind,group}` | 六项各0、suite=0、正式镜像restore=0；每项command/status/log保存 |
| 4MiB计算 | `glmark-opt-20261016-opp3-cache-compute-4mib`，count=1048576、100次、预热5 | 0，GPU_SMOKE_RESULT=PASS、OPP恢复PASS |
| 128MiB计算 | `glmark-opt-20261016-opp3-cache-compute-128mib`，count=33554432、20次、预热5 | 0，GPU_SMOKE_RESULT=PASS、OPP恢复PASS |

同步语义逐项原始marker已核对：三种timeline条件均完成16轮reset/import/destroy-recreate/
descending-point/BO lifecycle，以及ARM64 modern/historical ABI；snapshot完成128次导出、
64次导入及源/目标重置销毁、DRM关闭；bind/group分别有对应PASS marker。
不是实际32位compat测试，也不是专门的多线程reset/query竞争压力测试。
结构化检查`opp3-cache-semantics-analysis.json`保留六项run-id、退出码及marker。
一次整理脚本误写不存在的snapshot联合marker，断言失败后按实际两个独立marker修正；
没有重跑硬件用例或隐藏失败工作负载，最终检查通过。

计算使用同e800/e83、cache=1、concurrent=1，三个快照实验关闭，实际594MHz，
`--perf --exclude-cpu-prepare`，Client/Proxy 512/384MiB，CPU亲和性同前。
iter_total平均分别1714.31µs、36928.90µs；不是原生/共享交替性能对照，
不以这些绝对耗时推导新的原生开销比例。
两项suite/正式镜像restore均0；命令与日志位于`opp3-cache-compute-*`及标准shared目录。
这些计算在新Host的pmthor重绑定后执行，补充证明恢复后的真实shader执行和读回路径。

本轮保留边界：未完成opp3全33场景两分辨率计时；未完成新组合完整32项功能回归；
未实际触发高温热节流；未验证所有probe失败注入路径；未修复原生Panthor已知卸载问题。
空闲pmthor解绑通过不能替代原生Panthor负载后解绑安全性。
完成缓存与并发RPC仍为显式实验开关，未改为默认开启，未提交或推送组件/父仓库。

### 后续扩大回归：31项运行中，不能称32项通过

保存分项验证结束状态`opp3-final-host-state.log/.exit-code=0`：同opp3启动ID，
pmthor、CPU0–1、userspace 300MHz、max_freq 1000MHz，正式cadce/e83 Guest镜像恢复，
无VM/broker、无旧诊断模块，完整dmesg未匹配BUG/Oops/WARNING/DMA-API/reset failed。
空闲时读回整个SD p3的SHA-256为`e0cb4f31ff053e7bb9ff67677d6e304cc51104471ddd7b0da5a0e9d8417563d8`，
与实际刷写输入一致；源码diff检查与入口bash语法检查通过。

之后顺序启动`run-opp3-regression31.sh`，执行
`python3 scripts/run/run-regression.py --remote-prepared --run-id glmark-opt-20261016-opp3-regression31`，
未加`--quick`。完整命令及环境记录`opp3-regression31.command`，
逐项退出码/日志实时写入`GPU-SFTP/log/regression/glmark-opt-20261016-opp3-regression31/summary.json`，
外层`opp3-regression31-suite.log`，结束后trap恢复正式镜像并记录restore退出码。
输入仍e800/e83、opp3；单Client显式cache/concurrent开启，其余快照实验关闭，
GLES使用标准OPP请求600MHz、实际594MHz，并在各项结束后恢复。
双Client入口目前不传播这两个实验参数或Host OPP环境变量，因此该项验证同镜像的默认关闭路径，
不能把它写成双Client已启用缓存/并发RPC性能验证。

此矩阵不含`--passthrough`，共31项，保留原生Panthor卸载已知问题作为第32项的待解决限制；
不改验收标准、不把31项替代32项。运行未结束前，表述只能是进行中，
不能沿用旧组合的全部通过结论或完整glmark总分。

### 原生卸载 Oops：已准备修复候选，未部署

在上述31项运行期间仅做控制机源码分析/构建，不修改正在测试的Host/Guest载荷。
历史`host-native-unbind-oops.log`显示`JOB_INT_GLOBAL_IF`事件的
`process_fw_events_work+0xa8`读取已解除映射地址，随后scheduler销毁workqueue无法完成。
当前源码`panthor_device_unplug`先执行`drm_dev_unplug`，再scheduler unplug，
然后firmware unplug销毁FW section映射；scheduler workqueue到DRM managed释放才销毁。
`process_fw_events_work`原实现没有`drm_dev_enter/exit`，因此晚处理的事件可能访问已销毁映射。
该路径与历史故障一致，是源码支持的候选根因，尚非硬件复现后确认的完整修复。

仅Host原生Panthor的该worker增加DRM unplug临界区：已经进入的reader由
`drm_dev_unplug`的SRCU同步等待结束，unplug后的reader直接返回。
不改GPU调度/完成判据，不通过延时或吞掉计算错误掩盖问题。
候选`make ... LOCALVERSION=-opencca-pmthor-opp3 -j8 modules`退出0，
日志`opp3-native-unplug-build.log/.exit-code`；strip副本
`opp3-native-unplug-candidate/panthor.ko` SHA-256为
`2091b3f718dccef040a700bc53fb8e628f24481e28764249adaad6a6e8fa37ac`，vermagic匹配opp3。
原始部署包及已启动31项仍使用原native模块；候选未传到RK、未安装、未加载。
必须在矩阵结束后单独验证负载完成后的卸载/恢复，不能以编译成功宣称第32项已通过。

### opp3 扩大回归中的完整720p结果

`glmark-opt-20261016-opp3-regression31-glmark-1280x720`实际退出0，
完整33项计时，总分1058，validation仍26/1/6、unexpected=0，worker errors=0。
同e800/e83、cache/concurrent开启，标准OPP600MHz、实际594MHz，结束恢复300MHz PASS。
该轮未启用Proxy/RPC计时统计，与前述旧DMA1完整1023轮的统计开关及启动状态不同，
不能把+3.42%总分变化单独归因于Host OPP或其它单一变化。
缓存381353/887403（约42.97%），不是固定工作量RPC减少比例。

相对旧完整1023轮，build VBO1505→1531，blur249→253，conditionals等部分场景提高，
同时保留terrain54→51（-5.56%）、refract168→160（-4.76%）、
interleaved-buffer64→63（-1.56%）等下降。
这是一组跨启动/统计配置的单样本比较，不认定缓存或OPP是这些差异的单因素原因。
对缓存自身的因果支持仍来自同Host同镜像开关交替实验，不能用总分掩盖局部下降。

从720p计时中段开始，增加约5秒间隔的只读频率/GPU温度/cooling采样，
控制机日志`opp3-regression31-clock-samples.log`，监视器绑定实际存活的矩阵PID，
随其退出结束；不启动第二套硬件测试、不修改频率策略。
采样用于排查持续限频，不代表排除所有亚秒瞬态或所有CPU频率变化。
1080p、双Client及矩阵总状态仍须等实际结束再统计。

### opp3 的31项扩大回归全部通过

`glmark-opt-20261016-opp3-regression31`实际完成全部31项，
打印`REGRESSION_RESULT=PASS cases=31`，外层suite和正式镜像restore均捕获退出0。
17项IOCTL、PFN程序及checker、四容量Compute、ML-all、长Attention、NCNN三模型、
两分辨率完整glmark、双Client、前后环境检查全部完成；这不含原生/直通项。
逐项命令日志与summary位于`GPU-SFTP/log/regression/glmark-opt-20261016-opp3-regression31/`。
`analyze-opp3-regression31.py`核对完整用例名序列、31个退出码、IOCTL marker及glmark细节，
分析通过，结构化结果`opp3-regression31-analysis.json`。

| 分辨率 | score | 缓存命中/候选 | validation |
| --- | ---: | --- | --- |
| 1280×720 | 1058 | 381353 /887403 | 26 Success /1已知Failure /6 Unknown，unexpected=0 |
| 1920×1080 | 847 | 308691 /723719 | 同上 |

完整33场景明细均保留。1080p与旧841轮比较的差异也不能单独归因为Host OPP，
该组统计配置不同，且各分辨率只有一个完整样本。
720p/1080p实际关联到glmark VM的5秒采样分别54/67个，全部594MHz，
GPU温度范围50.846–53.615°C、cooling=0；720p采样从中段开始。
两项结束各恢复300MHz；双Client没有传播实验cache/concurrent或Host OPP参数，
实际验证同镜像默认关闭路径，不能冒称该项已经验证这些参数开启时的双Client性能。
矩阵及restore结束后确认无VM/broker，CPU0–1、300MHz，监视器已随矩阵退出。

### 原生卸载修复模块：首次硬件验证通过

31项结束后才部署native模块，期间未改变正在执行的测试载荷。
保存旧模块`/root/GPU-SFTP/log/glmark-optimization/opp3-native-unplug1/panthor.before.ko`，
SHA-256为`6d5c037fb308a0bfe3b792bfbcf80c2afe7ae328526dde4914ed99083e0e0e82`；
新模块2091...安装到同opp3 release路径，depmod退出0，install脚本退出0，
`opp3-native-unplug-install.log/.exit-code`保存校验依据。
先检查实际initrd列表没有Panthor模块，因此本次只更新rootfs中的匹配模块，未再次刷SD。
Host Image、initrd、pmthor代码和Guest镜像均不变，不能将旧归档模块包误称为已含此修复。

验证命令：`RUN_ID=glmark-opt-20261016-opp3-native-unplug-smoke ./scripts/run/run-host-vs-passthrough-gles-perf.sh --host-rootfs-userspace --skip-sync --skip-remote-build --skip-vm --count 33554432 --iterations 20 --warmup 5 --large-count-iterations 20 --large-count-warmup 5`。
原生128MiB计算20次、预热5次，COMPUTE_CHECK及总体PASS；脚本退出0。
随后Panthor成功解绑并卸载，`/sys/module/panthor`消失，pmthor重新绑定，
标准策略恢复userspace/300MHz，CPU0–1，无firecracker/broker，
完整dmesg未匹配BUG/Oops/WARNING/DMA-API/reset failed。
独立postcheck通过，外层suite退出0，保持同启动ID，不依赖复位恢复。
原始日志位于标准`GPU-SFTP/log/passthrough/perf/glmark-opt-20261016-opp3-native-unplug-smoke/`，
控制机`opp3-native-unplug-{smoke,after,suite}.log`及对应退出码。
这是一次特定负载/卸载路径验证，不宣称所有卸载竞争已穷尽。

### 含直通的完整32项：已启动，尚未完成

紧接着启动`run-opp3-regression32.sh`，执行
`python3 scripts/run/run-regression.py --remote-prepared --passthrough --run-id glmark-opt-20261016-opp3-regression32`，
未加quick；命令/环境保存`opp3-regression32.command`。
启动前额外核对native模块SHA为2091...且未加载，e800/e83 Guest及opp3 Host固定，
其它参数与31项相同；结束时trap恢复正式Guest镜像。
实时证据`GPU-SFTP/log/regression/glmark-opt-20261016-opp3-regression32/summary.json`，
外层`opp3-regression32-suite.log`；最终退出码和完整PASS仍待实际结束。
本轮31项及原生单项通过不代替该完整32项的终态。

修复后模块包另存`build/glmark-optimization/host-opp3-native-unplug1-deploy/modules-6.12.0-opencca-pmthor-opp3-native-unplug1.tar.gz`，
SHA-256为`d55e961742e74d2008b0510cf090ce2da90680ccc3c08cb1c89086907fbf323c`；
由原opp3模块staging的独立副本替换Panthor2091...构成，原模块包保留不变。
同目录`payload.sha256`同时列出不变的Host Image、kernel分区镜像及更新后的模块哈希。
此包已准备，硬件安装使用的是同哈希单模块；完整32项尚未完成，不能称该包已通过完整验收。

### opp3 完整32项终态：全部通过；同Host原生新对照启动

`glmark-opt-20261016-opp3-regression32`已实际执行全部32项，打印
`REGRESSION_RESULT=PASS cases=32`，矩阵返回0，外层suite及正式Guest镜像restore均退出0。
完整用例序列包含原生/直通，未使用quick。输入为Host 5a69...、原生模块2091...、
Client e800...、Proxy e83...；单Client缓存/并发RPC开启，三个快照实验关闭。
源码构建组合的范围与默认发布基线继续区分。

| 分辨率 | score | 完成缓存 hits /candidates | validation |
| --- | ---: | --- | --- |
| 1280×720 | 1058 | 383980 /887507 | 26 Success /1已知Failure /6 Unknown，unexpected=0 |
| 1920×1080 | 847 | 311791 /724159 | 同上 |

`analyze-opp3-regression32.py`核对32个精确用例名/退出码、17项IOCTL marker、
四容量Compute的原始Client结果、ML六算子及Attention完成标记、NCNN三模型及总结果、
PFN程序和checker、两份Client计算结果、原生/直通总PASS、glmark33场景及配置。
分析退出0，`opp3-regression32-analysis.json/.log`保存结构化结果。
各glmark关联到VM的5秒采样均67个，全部实际594MHz，GPU温度49.923–53.615°C，
两项各自恢复300MHz PASS；未证明所有亚秒瞬态或高温压力下行为。
双Client仍为该runner的默认关闭优化参数路径，不扩展声明。

后处理首次误把checker的`PMTHOR_PFN_LIFETIME_RESULT`标记用于检查程序日志，导致分析器assert失败，
在启动原生glmark前停止；这不是硬件用例失败。原失败日志保留为
`opp3-regression32-analysis-failed-pfn-marker.log`及`opp3-final-sequence.log`，
首次顺序封装退出1保留。依据实际程序的`PMTHOR_PFN_TRANSLATION_RESULT=PASS`修正分析，
复核已有日志通过，未重跑矩阵。

矩阵结束后只读确认同boot、pmthor、CPU0–1、userspace/300MHz、原生模块已卸载、无VM/broker；
正式Guest已恢复cadce.../e83...。随后才通过独立preflight并启动
`glmark-opt-20261016-opp3-native-full`，使用相同ELF、rootfs用户态、CPU2、实际594MHz，
统计关闭、完整33场景×两分辨率及严格validation。新原生结果尚待终态，
不能以旧DMA1原生1441/1004直接代替该同Host比较。
新原生helper哈希`79833a3dd200d50e4b16f27cc0b79c04657f67cc9259716f955186bd4d01b6a8`，
`opp3-native-full-preflight.log`、`opp3-native-full-helper.sha256`与
`opp3-native-full-suite.log`记录入口及执行；原始日志在
`GPU-SFTP/log/glmark-optimization/glmark-opt-20261016-opp3-native-full/`。

单Client性能配置已整理为`configs/performance/glmark-clientproxy-opp3.env`，
README明确Host/Client/Proxy/原生模块哈希、依赖和复测命令。
它不会部署候选内核，不适用于旧固定Client或双Client调优。

### 同Host原生全场景终态、候选安装与报告归档

`glmark-opt-20261016-opp3-native-full`已完成两个分辨率各33场景，
720p原生1432、1080p原生997；对照同boot完整32项的共享1058/847，
总分保留73.8827%/84.9549%，场景FPS比的几何均值77.1716%/87.2747%。
各分辨率计时后严格validation均26/1/6、unexpected0；workload、suite、cleanup退出0。
原生各70个约5秒采样全部实际594MHz，GPU温度49.000–54.538°C；
`compare-opp3-final.py`核对同boot、ELF/模块哈希、场景名、完成标记、频率与退出码，分析通过。
完整明细在`opp3-final-comparison.json`及最终性能报告，不以旧原生分数代替。

原生cleanup有四次dev挂载busy提示，有界重试后成功、cleanup=0；
最终独立挂载检查无该run残留。保留原提示，未强制卸载或依赖复位。
720p terrain原生12.973ms、共享19.942ms，额外6.969ms；1080p额外3.622ms。
这不是统一0.15–0.26ms RPC常数可解释的结果，精确归因尚未完成。
短帧中较高固定成本与terrain剩余缺口同时列入报告，不能只看总分。

全场景及32项确认后，执行`activate-opp3-client-profile.sh`退出0，
将同哈希e800候选安装到控制机/RK的shared Client Image路径，Proxy保持e83。
旧cadce在本地`build/glmark-optimization/opp3-profile-activation/client-before.Image`及
RK `/root/GPU-SFTP/log/glmark-optimization/opp3-profile-activation/client-before.Image`保留。
性能开关仍默认关闭，通过`configs/performance/glmark-clientproxy-opp3.env`显式启用。
未更新固定发布manifest、未提交或推送；控制机Host运行树旧Image未替换，
不得拿该旧文件冒充当前opp3 Host的可部署镜像。

最终health脚本退出0，same boot、pmthor、/dev/kvm和/dev/pmthor正常，
原生模块已卸载、无VM/broker、CPU0–1、userspace/300MHz且实际300MHz，
无本轮挂载残留、未匹配BUG/Oops/WARNING/DMA-API/reset failed。
`opp3-final-health.log/.exit-code`、`opp3-profile-activation.*`及目录保存依据。
系统其他启动期外设/efi.mount错误没有因此被认定修复。

gpu-smoke.sh控制机/RK逐字节一致；init只差PID1退出说明注释，非注释行完全一致。
原先“两个脚本均应逐字节一致”的过强断言失败保留，人工diff及执行代码核对确认无行为差异，
没有为此改动正在执行的原生载荷或追加硬件重跑。

最终报告为[GPU_GLMARK_PERFORMANCE_REPORT_20261016.md](GPU_GLMARK_PERFORMANCE_REPORT_20261016.md)，
随附脱敏JSON、原生实际脚本和manifest在`docs/shared/evidence/glmark-optimization-20261016/`；
原始日志与二进制仍被Git忽略，不随clone提供。
