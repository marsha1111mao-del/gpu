# Realm 控制通道与私有 GPU 共享测试

2026-11-11 安全模拟候选增加可选验收项：`run-realm-xshm.py --session-quota 8 --security-selftests` 在正常负载前，逐Client通过实际DRM打开/关闭验证会话配额，并运行原始RMM Group/任务观察边界检查。打包时需匹配的新`init`、`realm-gpu-private`及`--session-quota-probe <AArch64工具>`，wrapper会拒绝缺失/陈旧输入。候选进展和旧失败见[RK3588模拟实现记录](../../../docs/shared/GPU_SECURITY_RK3588_SIMULATION_IMPLEMENTATION_20261110.md)。

只读 `REALM_GPU_TASK_OBSERVATION` 使用任务token为handle、args[0]为实际服务通道、其余参数为0；返回 `[进入可信观察路径的次数, 首次失败阶段, 协议状态flags, 同一任务token]`。通道、实际owner、服务实例和旧token均由RMM核验。失败阶段一经记录不因设备状态后来变干净而清除；只有可信回收/失效结束该记录。

该调用的SUCCESS仅表示读取元数据成功。`COMPLETED`表示执行协议阶段，`RETURNED`表示CPU归还阶段；两者都不能单独替代FINISH成功或安全释放。`START_ATTEMPTED`/`STOP_ATTEMPTED`和`PENDING`保留可能已生效/未决操作信息；`LIVE`说明保留执行域；`RMM_SOURCE`说明摘要由RMM维护，次数不等于物理IRQ次数或新鲜STATUS ACK次数。通过Proxy转发的同名flags不具有独立认证意义，实际可信查询走本Realm的RSI。该软件摘要本身不证明物理IRQ来源；物理捕获由下述独立Monitor链路提供。

**当前新增Monitor中断证据链已验收。** 冻结包 `build/gpu-irq-security-20261111/candidate-r3/{graphics-runtime,compute-runtime,firmware}/`，可选IRQ能力bit42；EL3物理IRQ、Root设备采样、可信模拟分别标记，RMM按当前绑定消费并核对Proxy引用。Group只能声明进度/故障，任务完成声明仍需新鲜FINISH；当前worker有界查询，不要求每个Job都有IRQ。`--security-selftests`还执行固定可信IRQ模拟和真实Proxy拒绝探针；注入只在没有prepared/running硬件Group时允许，不能把模拟当真实GPU故障。

完整720p1026分（stage2 1046→1026，−20/−1.91%；旧ABI6 1095→1026，−69/−6.30%），33场景、validation26/1/6；双Client DRM/计算/eventfd、配额/观察/IRQ自检及最终审计通过。run-id为 `gpu-irq-security-720-r3-20261111`、`gpu-irq-security-two-client-r3-20261111`，退出0。相同完整720p/Mesa25.0.7/GPU实际594MHz/性能策略，IRQ/FW/内核、自检与UART为组合条件，不作单项归因。命令、日志、来源和保留失败见[中断安全交付记录](../../../docs/shared/GPU_IRQ_SECURITY_IMPLEMENTATION_20261111.md)，旧stage2整套保留回退；完整物理GPC/DMA/GIC及残留清理未获证明。

当前使用说明更新于 2026-11-09。设计、冻结输入和验收范围以[当前基线](../../../docs/shared/CURRENT_BASELINE.md)顶部条目为准；构建部署先读[环境主手册](../../../docs/start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)和[开发与产物管理](../../../docs/start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)。命令默认从仓库根目录执行。

**当前源码只保留私有 GPU 数据路径，Client/Proxy 内部 RPC ABI 为 6。** Client 分配业务 BO，Proxy 维护驱动功能对象和元数据，RMM 管理真实 GPU 映射、任务授权、敏感设备操作和完成判定。共享池承载通信与控制对象，不承载业务 BO。独立的 Realm 事件和内存传输测试仍保留，Host 原生与单 VM 直通另有实际测试入口。

**历史stage2安全功能模拟验收。** 包为 `build/security-rk3588-sim-20261110/stage2-candidate/{graphics-runtime,compute-runtime,firmware}/`，完整720p1046分（相对原ABI6/1095为−49/−4.47%），33场景、validation26/1/6；双Client真实DRM/提交、65536值计算、4轮binary/timeline eventfd及逐Client配额/观察自检通过。run-id分别为 `security-rk-sim-observation-720-r1-20261111` 与 `security-rk-sim-observation-two-client-r1-20261111`，退出0，Host健康和资源恢复通过。命令、条件差异、失败/未测项见[模拟实现记录](../../../docs/shared/GPU_SECURITY_RK3588_SIMULATION_IMPLEMENTATION_20261110.md)。同720p/用户态/GPU实际594MHz及性能策略，改动和UART为组合条件，不作单项归因；原1095整套包保留为回退，不混搭。此为固定可信载荷及P1—P5合同内的GPU协议模拟，不是完整物理隔离或生产Guest保护证明。

## 冻结输入与统一入口

GPU 冻结包包含 `client-Image`、`proxy-Image`、`initrd.cpio`、`runner.py` 和四个文件的 `hashes.json`。`runner.py` 必须是匹配本包协议的冻结副本。wrapper 在上传前检查文件哈希、ABI 标记、initrd 格式、工具架构、固定 FW 和所选负载依赖；这用于发现打包错误，不是远程证明。

Host/RMM、Firecracker 和板端只读 Panfrost rootfs 必须预先匹配。wrapper 只同步变化的冻结文件，不安装 Host/RMM/rootfs，不重刷健康 Host。所有硬件测试都通过 `lab-run.py` 获取 Pi/RK 独占锁；一次只运行一套测试，不嵌套租约，不给普通测试添加 `--allow-rk-reboot`。

每轮优化先执行完整单 Client 720p，达到 1000 分且正确性、内核健康和回收检查通过后，再扩展功能、计算和多 Client：

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py --images <匹配的冻结包> \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

以下为使用示例；本轮实际已执行的范围以上述记录为准，未选的历史矩阵不继承PASS。

| 目的 | 传给控制机 wrapper 的参数 | 实际范围 |
| --- | --- | --- |
| 完整单 Client 720p | 上述命令 | 完整 validation 与 33 场景，单路分数至少 1000 |
| 多 Client 图形 | `--workload glmark --performance --benchmark-only --suite --profiles glmark-1080 --clients 4` | 支持 1–4 Client；一次选择一个分辨率，也可选 `glmark-720` |
| 双 Client 功能/计算 | `--workload compute` | 自动启动两个 Client，执行私有 DRM/提交探针与真实 GLES 完成 eventfd 检查 |
| 多 Client ML 算子 | `--workload glmark --performance --benchmark-only --suite --profiles ml-gemm ml-conv ml-depthwise ml-reduction ml-softmax ml-attention --clients 4` | 同一 profile 的所有 Client 完成后再进入下一项 |
| 多 Client 模型 | `--workload glmark --performance --benchmark-only --suite --profiles ncnn-resnet50 --clients 4` | 需要匹配模型、GPU 后端和冻结工作负载配置 |
| 独立可信事件 | `--workload events` | 三 Realm 端点、持久 pending/ack、身份拒绝与实际控制 IRQ 检查；不启用 GPU 服务 |

ML 入口沿用 `--workload glmark` 选择只读 workload rootfs，实际执行内容由显式 `--profiles` 决定。可用 ML profile 为 `ml-gemm`、`ml-conv`、`ml-depthwise`、`ml-reduction`、`ml-softmax`、`ml-attention`、`attention-320`、`ml-all` 以及 `ncnn-mobilenet_v2`、`ncnn-mobilenet_v3`、`ncnn-resnet50`。图形与 ML 不在同一次 suite 混选；未选项目记录为 NOT_RUN。

无需设置 Client 模式开关。runner 核验 Client 的只读 `private_gpu` 标记；Proxy 通过 `panthor.rmm_service=1` 选择受限服务路径，随后由 `gpu-private service-bootstrap /mali_csffw.bin` 完成可信接管和固件初始化。初始化、能力或私有探针失败即失败，不改走其他数据路径。

## 内存与 CPU 条件

wrapper 固定每 Client 控制池为 2049 个 4 KiB 页，即 8 MiB + 4 KiB。业务 BO 使用 Client 普通私有内存；不能按共享池容量或 CMA 大小推断可分配 BO 总量。

当前 `realm_memory()` 按控制池页数、Client 数和 profile 计算内存，保留 256 MiB Host 准入余量，并记录 `memory_plan`：

| 配置 | Client RAM / CMA | Proxy RAM / CMA |
| --- | --- | --- |
| 普通图形或算子，1 Client | 476 / 28 MiB | 268 / 28 MiB |
| 普通图形或算子，4 Client | 每路 476 / 28 MiB | 388 / 52 MiB |
| 显式 ResNet50，4 Client | 每路 604 / 28 MiB | 388 / 52 MiB |

这只是当前脚本的准入估计，不是运行时硬保留，也不保证任意任务都能装入内存。GPU Realm 使用 16 MiB SWIOTLB；OOM、分配失败及启动前拒绝均保留。内存方案变化时以实际 `memory_plan` 为证，重新比较测试条件。

性能模式请求 GPU 600 MHz，目标板已记录实际 594 MHz；每轮仍核验实际频率。单 Client 性能默认 Proxy CPU1、Client CPU2；多 Client 默认所有 Client 共享 CPU2–3，VMM I/O 固定 CPU0。`--client-cpu-layout round-robin` 将多路 Client 按 2/3/2/3 固定落核。`--cpu-frequency-khz <值>` 仅用于完整图形性能对照，退出时恢复原策略。不同布局、频率或 Client 数的结果不得当作单变量对照。

正式计分默认关闭 `--rpc-stats` 和 `--notify-trace`。需要诊断时单独启用并记录额外开销；诊断结果不与关闭诊断的分数混计。

## 功能与性能判据

**图形。** 每路核对 Mali/Panfrost renderer、实际 1280×720 或 1920×1080、完整 33 场景、退出码和 validation。当前冻结负载的 validation 期望为 26/1/6，已知例外按基线单列，不得隐藏新增失败。Client 完成 validation 后等待 READY/GO 屏障再评分；多路公共评分窗口须覆盖联合窗口至少 90%。串口窗口不是 GPU 硬件执行时间，各场景也没有逐项屏障。单路 720p 的 1000 分门槛不逐路施加于多 Client 并发结果。

**计算和 eventfd。** `--workload compute` 运行每个 Client 的 `gpu-private drm-selftest`、`gpu-private drm-submit-selftest`，再在两路真实 GLES dispatch 后导出 sync_file，检查 binary/timeline eventfd 和结果。匹配探针为 `gles-compute-smoke --gpu-eventfd --count 65536 --iterations 4 --alu-iters 64 /dev/dri/renderD128`；要求底层 fence 来源 `panthor-client-private` 及完整成功标记。只执行 glFlush 提交，通知检查前不依赖 CPU SIGNAL 或 glFinish。注册时 fence 已完成是合法情况，因此通过不单独证明一定走过 pending 回调。

**ML/NCNN。** 独立算子按预热后的计时屏障推进；`ml-all` 只在整套入口同步，应独立统计。检查 CPU reference、GPU renderer、样本/预热数、完整耗时字段、错误日志和退出码。NCNN 还须确认 `panvk-direct` 后端与模型成功标记；正式轮数按冻结 `glmark.env` 及日志核对。随机输入/权重不证明模型精度，出现 Vulkan wait、Mesa 或 GPU 错误的耗时不能作为有效性能。每项必须有公共运行窗口，不能用单路运行时间伪称并发。

**控制 IRQ 与完成。** runner 在计时前主动检查通道身份、目标 IRQ 投递及两次通知合并。这里的 INTID127 是 Realm 控制通知，不是 GPU 物理完成 IRQ；成功提交、普通提示及控制 IRQ 计数均不能替代 RMM 完成与结果可见性判定。

**回收。** 工作负载后核验控制池 unbind、detach、revoke、端点注销和全部 Realm 退出，并检查 Host/Guest 新增内核错误与资源恢复。控制通道清理通过不等于整设备及死亡 Realm 的可信回收已证明；当前 runner 将 `trusted_device_reclamation` 保留为 NOT_VERIFIED，攻击隔离等未执行项同样不得升级为 PASS。

## 独立事件与内存传输

`realm-xshm` 访问权限 0600 的 `/dev/realm-xshm`，Guest 需启用 `CONFIG_REALM_XSHM=y`；调用进入真实 RSI。管理操作要求 Guest `CAP_SYS_ADMIN`。关闭 fd 不等于端点注销，必须显式 unregister 或销毁对应 Realm。

`REGISTER` 返回 ABI、endpoint、capabilities、capacity。按实际能力位判断事件、映射、身份查询和 IRQ 支持；端点编号不是远程证明。

| 操作 | 用途与边界 |
| --- | --- |
| `register / unregister` | 本 Realm 端点生命周期 |
| `offer / accept / close` | 有身份约束的通道建立与关闭 |
| `notify / query / ack / arm / ack-arm` | 持久事件与唤醒；重新 armed 后仍需按协议重查队列 |
| `irq-bind / irq-stats` | 绑定并观察控制通知 IRQ，不证明 GPU 完成 |
| `mem-offer / mem-attach / mem-continue / mem-status` | 分段共享授权与挂接；未完成时推进同一 grant |
| `mem-describe` | 核验参与者后返回授权及本 Realm 地址信息 |
| `mem-detach / mem-revoke` | 借用方解除与提供方撤销 |
| `pool-source / pool-target / pool-info` | 为传输测试准备和查询池，不是私有业务 BO 分配接口 |
| `pool-bind / pool-unbind` | 绑定控制队列并按引用条件解绑 |

底层冻结 `run-realms.py` 还支持独立 `--memory-pages <页数> --transport --trusted-events`，用于通道、跨 Realm 内存可见性、身份拒绝和撤销协议，不设置 `--gpu-flow`。控制机 wrapper 的 `--workload events` 默认只选事件测试；需要独立内存/transport 验证时，在同一 `lab-run.py` 租约下用经审查的远端启动命令执行冻结 runner，并记录完整参数和哈希，不能直接在控制机运行面向 RK 的底层脚本。

内存操作返回 grant、state、progress、pages。分段未完成不代表未接纳，应按状态继续原操作；超时或回复丢失也不能直接重新发布。`pool-fill-pages`/`pool-check-pages` 检查每页首个 64 位字，不宣称验证每个字节。活跃引用或 pin 未排空时，解绑/撤销失败应保留资源。

## 构建与打包

构建前核对当前 Guest 源码、配置、RMM 能力和内部协议，输出放本轮独立 `build/` 目录，不覆盖正在执行的输入。静态工具入口为：

```bash
REALM_XSHM_BUILD_OUT=build/<本轮目录>/tools \
  bash scripts/build/build-realm-xshm.sh
python3 scripts/build/build-realm-xshm-initrd.py \
  --tools-dir build/<本轮目录>/tools \
  --gpu-private build/<本轮目录>/tools/realm-gpu-private \
  --gpu-firmware GPU-SFTP/panthor_fw/mali_csffw.bin \
  --glmark-env GPU-SFTP/tests/realm-xshm/glmark.env \
  --performance-suite GPU-SFTP/tests/realm-xshm/performance-suite.sh \
  --output build/<本轮目录>/initrd.cpio
```

这是完整图形包的模板。计算包还需 `--gles-compute <匹配ARM64探针>`；ML 算子包需 `--gles-ml <匹配ARM64探针>`。固定 FW 文件须通过打包器摘要检查，initrd 按 4 KiB 填充。仅构建这些工具不等于构建了 Client/Proxy Image；两端内核须由本轮源码和相应配置成套生成，再连同 runner 制作 SHA 清单。ABI 6 不能靠替换旧包的 runner 标记或忽略能力检查启用。

离线入口 `scripts/check/check-rmm-gpu-private.sh` 覆盖当前私有核心、Guest 桥接与 runner 检查，使用模型和测试后端的结果应标为离线证据。构建、离线检查和正常 GPU 负载均不能替代实体隔离攻击验证。具体新候选的执行结果只登记到本轮报告。

## 日志回收与复验

控制机外层证据保存于 `build/lab-runs/<run-id>/`，RK 原始运行证据保存于 `/root/GPU-SFTP/log/realm-xshm/<run-id>/`。每项记录命令、退出码、输入哈希、run-id、日志位置和语义检查；失败及未执行项保留。

运行结束后回收并校验：

```bash
python3 scripts/maintenance/collect-realm-evidence.py \
  --run-id <同一run-id> --output <新的本地回收目录>
```

collector 拒绝采集仍在运行的测试或覆盖已有目录。多 Client 图形/ML 统计入口分别为 `scripts/analysis/summarize-multiclient-glmark.py` 与 `scripts/analysis/summarize-multiclient-ml.py`，使用前先读脚本，确认其接受当前证据结构；不能以统计器旧格式假设覆盖实际 runner 判定。分数之和是聚合评分指数，不是硬件总吞吐。

结束时确认没有本次残留 VM、挂载或 loop，恢复原 CPU 策略和 pmthor。发生异常只处理本次已确认归属的资源，禁止全局杀进程或用超时替代可信撤权。Host 原生与单 VM 直通测试见主手册第 8.3 节，与私有共享结果分别记录。

统一记录：更新唯一私有路径的执行说明｜已冻结单 Client 720p 1099 → ABI 6 清理候选未测｜分差及百分比 N/A｜纯文档整理，未改运行代码，无新增性能测量｜无新增硬件 run-id｜候选构建及硬件验收待完成。
