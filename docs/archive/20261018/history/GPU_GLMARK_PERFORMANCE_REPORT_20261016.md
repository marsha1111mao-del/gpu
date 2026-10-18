# glmark 性能定位、优化与原生对照报告（2026-10-16）

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

本文汇总本地工作树的源码修改、RK3588 实测和验收证据。固定发布基线及早期失败不被覆盖；完整探索过程见[实验记录](GPU_GLMARK_OPTIMIZATION_20261016.md)。新的完整 32 项及同 Host 原生 glmark 全场景对照均已完成，以下为实际终态数值。

## 结论与测量范围

最初异常巨大的差距同时包含实现问题和测量条件问题：Proxy 等待 GPU 固件 ACK 时产生整 jiffy 延迟，并在持有 scheduler 锁时拖慢提交；原生与共享路径的默认 GPU 频率也不同。修复 ACK 等待、明确控制 GPU OPP 后，多数短帧场景呈现跨 VM RPC 和同步对象管理的固定成本特征；terrain 等场景仍有更大的未完全归因成本。IRQ 模式并发 RPC 和已完成 timeline 点的精确缓存进一步减少了开销。

不能把历史共享 score 58 与新成绩之比当成单一代码优化的因果收益：历史运行没有统一频率和亲和性。本次最终表使用同一次 opp3 Host 启动、相同实际 594 MHz GPU 频率、相同 glmark ELF 和用户态，在 CPU 2 上顺序测量。

| 分辨率 | 原生 score | 优化后 Clientproxy score | 总分保留率 | 总分下降 | 场景 FPS 保留率几何均值 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1280x720 | 1432 | 1058 | 73.88% | 26.12% | 77.17% |
| 1920x1080 | 997 | 847 | 84.95% | 15.05% | 87.27% |

异常的整 tick 等待已被消除，但当前软件代理架构仍有可测的固定往返成本。上述结果适合作为这个实现的实测开销；不能把它表述为所有场景均接近原生。

1280x720 保留率最低的三个场景：`[bump] bump-render=normals:` 保留 59.17%（每帧 +0.264 ms）；`[bump] bump-render=height:` 保留 61.92%（每帧 +0.249 ms）；`[texture] texture-filter=nearest:` 保留 64.99%（每帧 +0.232 ms）。

1920x1080 保留率最低的三个场景：`[bump] bump-render=normals:` 保留 76.37%（每帧 +0.170 ms）；`[build] use-vbo=true:` 保留 77.75%（每帧 +0.161 ms）；`[texture] texture-filter=linear:` 保留 78.83%（每帧 +0.171 ms）。

总分保留率定义为共享 score / 原生 score；它不是所有场景的统一开销。场景表同时给出原生/共享 FPS 和每帧增加的毫秒数，负数表示该单样本共享路径更快。不能把 FPS 下降百分比等同于完成时间增加百分比：例如保留 80% FPS 对应约 25% 时间增加。

使用定制 `null-noop` 后端与 `frame-end finish`，每帧等待 GPU 完成，不测量显示器呈现帧率。各路径各分辨率为一次完整 33 场景计时；短 A/B 有交替重复，但最终完整对照没有置信区间，不能声称所有微小差异有统计显著性。

## 环境和可追溯载荷

| 项目 | 本次条件 |
| --- | --- |
| 物理平台 | RK3588 / Mali-G610 |
| Host | `6.12.0-opencca-pmthor-opp3`；同一次启动顺序测试 |
| GPU 频率 | devfreq 请求 600 MHz；PLL 实际 594 MHz；未锁 min/max 绕过 QoS |
| CPU | 上线 0–3；共享 broker 0、Proxy 1、Client 2；原生 glmark 2；额外频率监视器 0 |
| VM | 单 Client/Proxy 各 1 vCPU、512/384 MiB |
| 用户态 | 相同 rootfs 用户态，Mesa 25.0.7-2；renderer `Mali-G610 (Panfrost)` |
| glmark ELF SHA-256 | `2251afb6b792c08181e14205756a29c13f8dd15d5a3eb8ab6652efe55a65bb2c` |
| Host Image SHA-256 | `5a692bc15bcd7e456820385c3b6c6a55304e358b067c61ebe7032ecbe21c1a6f` |
| Client Image SHA-256 | `e800a161dc03e5914a01fbf26fcfa2fae5cee43bbdd6bf2216621cc3a6934833` |
| Proxy Image SHA-256 | `e83f011122e8107860a3000a96b8f522bcbed59c2c99395a7dbe02ebf6ec9ca8` |
| 原生 Panthor 模块 SHA-256 | `2091b3f718dccef040a700bc53fb8e628f24481e28764249adaad6a6e8fa37ac` |
| 性能开关 | concurrent RPC=1、completed wait cache=1；fused/lazy/completed snapshot=0；BO cached mmap=0 |
| 统计和日志 | 两条路径均降低 console loglevel；最终共享 Proxy/RPC 计时统计关闭，缓存计数保留；原生 submit/IRQ 统计关闭 |

以上为未提交源码工作树的构建结果，不能称为原固定发布组合。Host 已通过 SD 的 kernel 分区部署，未重刷 rootfs 或固件；原生卸载修复随后仅更新匹配的 rootfs 模块。原先的模块归档未包含这一后续修复，更新包另存，详见长记录的载荷哈希。

## 已实施的修复与取舍

### 1. 消除持锁 ACK 等待的整 tick 延迟

Proxy 的[固件 ACK 等待](../../../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_fw.c)先短暂轮询真实 ACK，未完成再通过 waitqueue 有条件等待，唤醒及超时末尾均重新检查真实完成状态。保留 Realm 路径的缓存维护，没有提前伪造完成。

同工具链诊断中，旧控制组 scheduler 锁等待平均约 7.071 ms/次；修复组约 4.43 µs/次。两组完成帧数不同，比较的是按调用归一化值，不能直接用累计时间相减。降低 console 输出、改 scheduler tick、分离 CPU 均不能单独消除原问题。

### 2. 标准化 Host GPU 频率及资源生命周期

[pmthor](../../../../Linux-Host-GPU/drivers/pmthor/pmthor_drv.c)增加 OPP、regulator、clock 和 userspace devfreq 管理，保留 OPP notifier、QoS 和 cooling 约束；初始化及部分失败路径按资源依赖逆序释放。

runner 接受 `GLES_HOST_GPU_OPP_HZ`，拒绝非法或不支持的频率，并在请求未实际达到时于 VM 启动前失败。正常测试结束恢复之前的策略和频率。本次选取标准 600 MHz OPP，对应板上实际 594 MHz；没有通过把 min/max 同时写高而屏蔽降频约束。

非法频率及 QoS cap 的负向检查按预期退出 2，未启动 VM，恢复路径通过。温度监视和 cooling 采样用于检查持续限频；没有进行实际高温降频压力验证。该实现使用显式 userspace governor，没有自动负载调频或 runtime suspend，不能描述为完整生产级电源管理。

此前 Host DMA 引用路径已对唯一 PFN 建立 DMA 映射，并保持至设备/VM 释放、reset 完成后再解除。PFN 和计算验证支持本次使用路径，但不能由有限测试宣称所有缓存一致性问题已被证明消除，更不提供硬件 SMMU/GPC 隔离。

### 3. IRQ 模式允许独立 RPC 重叠

[Client transport](../../../../Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c)在 IRQ 通知模式下允许多个调用等待各自回复，保留请求队列、回复匹配及对象生命周期同步；轮询模式仍串行。去除覆盖整个 RPC 往返的全局 mutex，避免主线程和 fence worker 相互串行阻塞。

短 A/B 中 build 提高约 8.29%，blur 约 0.84%，terrain 无变化；早期同频完整总分由 938/777 提高至 989/804。后者是旧 DMA1 Host、统计开启时的历史结果，不作为最终 opp3 原生对比。活跃 RPC 峰值大于 1 只证明调用重叠，不代表多 Realm 或 GPU group 已获得安全并行。

### 4. 缓存经过真实确认的精确完成点

[Client DRM 前端](../../../../Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c)仅为单 handle、非零 point、WAIT_ALL、零超时的 timeline 查询提供快路。首次成功必须来自真实 Proxy 回复；缓存匹配同一对象、同一精确 point 和同一文件变更 epoch。没有把“较大 point 已完成”外推为所有较小 point 都安全。

reset、signal、import、transfer、VM_BIND、GROUP_SUBMIT 及其他非白名单操作先使旧证明失效，失败操作也不恢复旧证明；并发变更期间不命中、不记录证明，epoch 回绕后停用。持有对象引用避免 handle 销毁复用混淆。审计后仅将不会替换公开 syncobj fence 的 BO_CREATE、BO_MMAP_OFFSET、GEM_CLOSE 三个 BO 操作加入保留缓存的白名单。

早期全部文件操作失效的版本在 glmark 几乎没有缓存命中，不能仅凭微型探针有效就称真实应用优化成功。放开上述三个 BO 操作后才获得可测收益。当前实现不支持共享可变 syncobj 的 opaque FD 导入导出，支持的是 sync_file fence 快照；未来扩大共享对象 API 时必须重新审计失效范围。

同 opp3、同 e800 Client/正式 Proxy、并发 RPC 开启的 OFF/ON/OFF/ON 四轮对照如下。每项每条件两个 5 秒计时样本，每轮均执行完整严格 validation：

| 场景 | OFF 两次 FPS | ON 两次 FPS | 均值变化 |
| --- | --- | --- | ---: |
| build VBO | 1429 / 1421 | 1512 / 1513 | +6.14% |
| desktop blur | 240 / 239 | 251 / 251 | +4.80% |
| terrain | 50 / 50 | 54 / 54 | +8.00% |
| conditionals fragment-steps=5 | 1297 / 1282 | 1298 / 1291 | +0.39% |
| buffer interleave/map | 65 / 65 | 65 / 64 | −0.77% |

最后两项没有证明稳定改善；不隐藏轻微下降。缓存相关 reset/import/destroy/重建/倒序 point、BO 生命周期及历史 ABI 探针通过；未实际执行 32 位兼容用户态，也未穷尽所有并发重置竞争。该开关与并发 RPC 均保持默认关闭，由性能 profile 显式启用。

### 5. 修复原生对照后的卸载故障

历史原生 128 MiB 负载完成后，解绑发生 FW worker 访问已解除映射区域的 Oops，并卡在 workqueue 释放。本次在 Host [process_fw_events_work](../../../../Linux-Host-GPU/drivers/gpu/drm/panthor/panthor_sched.c)加入 `drm_dev_enter/exit`，使 unplug 等待既有读者，阻止 unplug 后的新读者进入。没有改变任务完成判据。

新匹配模块通过原生 128 MiB、20 次计算及卸载恢复的单项验证；后续完整矩阵和最终原生 glmark 的清理结果分别记录。有限的成功卸载不代表所有竞争均已穷尽。

### 未采用的实验

| 实验 | 观察 | 最终配置 |
| --- | --- | --- |
| sync-file poll 从 1000 改为 50 µs | 未证明 FPS 收益 | 1000 µs |
| 已完成快照导出快路 | 真实命中率约 0.1%，无稳定收益 | 关闭 |
| 融合快照 + 按需等待 | 总分提高，但定向交替确认 effect2d 下降 6.66% | 均关闭 |
| 仅全文件 epoch 失效缓存 | 微型探针有效，glmark 几乎不命中 | 改为审计后 BO 保留策略 |
| 调小 scheduler tick | 未消除最初整 jiffy 等待问题 | 不作为主修复 |

## 回归结果和剩余成本

完整矩阵 `glmark-opt-20261016-opp3-regression32` 使用原入口 `python3 scripts/run/run-regression.py --remote-prepared --passthrough --run-id glmark-opt-20261016-opp3-regression32`，未加 quick。全部 **32/32 通过**，矩阵、外层 suite 和 Guest 镜像恢复均退出 0。原生/直通项是原入口定义的 Compute 对照，最终 glmark 原生全场景比较另行执行，不能混为一项。

| 测试组 | 项数 | 结果 / 范围 |
| --- | ---: | --- |
| 前后环境检查 | 2 | PASS |
| IOCTL | 17 | PASS，含 Group submit fence 完成 |
| PFN 程序及日志 checker | 2 | PASS，两个关闭顺序及唯一页引用释放 |
| Compute | 4 | PASS，4/16/64/128 MiB |
| ML / Attention320 / NCNN | 3 | PASS，六算子、长 Attention、三模型 |
| glmark | 2 | PASS，每项完整 33 场景计时 |
| 双 Client | 1 | PASS，两份计算结果均校验；优化参数默认关闭 |
| 原生/直通 | 1 | PASS，4/16/64 MiB 对照及恢复 |

原生完整 glmark run-id 为 `glmark-opt-20261016-opp3-native-full`，两项 workload、外层命令和 cleanup 均退出 0。保持同 boot `de6db746-7603-440b-bd2b-528d3adaf559`。

1280x720：共享 67 个采样、原生 70 个采样，GPU 实际频率均为 594 MHz；GPU 温度共享 49.923–53.615°C，原生 49.000–53.615°C。约 5 秒采样不能排除所有瞬态。
1920x1080：共享 67 个采样、原生 70 个采样，GPU 实际频率均为 594 MHz；GPU 温度共享 49.923–53.615°C，原生 50.846–54.538°C。约 5 秒采样不能排除所有瞬态。

glmark 严格 validation 在原生和共享、两个分辨率下均为 26 Success、1 已知 Failure、6 Unknown，unexpected=0。已知例外为 function medium 场景的 framebuffer 验证，不应写成“33 项 validation 全通过”；矩阵 PASS 表示满足 runner 明确保留该例外的标准。

双 Client 功能项使用同 Client 镜像，但该 runner 未传播此次缓存/并发 RPC/Host OPP 实验参数，验证的是默认关闭路径。不能用这一项证明开启优化参数的双 Client 性能，或机密多 Realm 共享隔离。

此前启用计时统计的 e800 完整运行中，720p 的 SYNCOBJ_CREATE/TRANSFER/DESTROY 平均约 46/46/56 µs，GROUP_SUBMIT 约 62 µs；1080p 对应约 45/43/61/64 µs。这些是旧 DMA1 Host 的诊断平均值，含计时统计，不能冒充最终无统计运行的逐帧因果分解。它们与多个串行 RPC 累加为亚毫秒开销的解释一致。

多数短帧场景的新增时间符合固定往返成本特征，但不能用一个常数解释所有场景。此次 terrain 在 720p 从 12.973 ms 增至 19.942 ms，额外 6.969 ms；1080p 额外 3.622 ms，仍是明确的剩余性能缺口。此前把快照轮询从 1000 调到 50 µs 未带来收益，原生强制完整缓存刷新仅使相关重场景下降约 6%–7%，不足以完整解释 terrain。其精确逐帧归因尚未完成，不将缓存命中、普通 RPC 均值或 GPU 频率当作已经证明的全部原因。

较重 GPU 场景能够摊薄这类固定成本，高 FPS 的短任务更容易受影响。GPU 频率一致后仍有差距，不能再用提高共享路径频率或取消 `finish` 等待来声称消除了通信开销。下一步若有更严格的业务目标，应基于目标 workload 分析每帧 RPC 数与关键依赖链，考虑批量请求、可信的完成通知及减少对象往返；仍需保持 fence 快照、失败传播和对象生命周期语义。

## 复测与证据

推荐配置及其载荷前提见 [performance README](../../../../configs/performance/README.md) 和 [环境文件](../../../../configs/performance/glmark-clientproxy-opp3.env)。仅 source 配置不会部署新内核；旧固定 Client 不含这些开关。当前性能 profile 面向单 Client，不改变默认发布镜像或默认驱动参数。

原始日志保存在本控制机的 `GPU-SFTP/log/` 与 `build/glmark-optimization/`，均被 Git 忽略，不随 clone 自动获得。下列脱敏结构化证据随文档保存：

原生清理曾有四次 `umount ... target is busy` 提示，脚本的有界重试随后成功；cleanup 退出 0，最终独立检查确认没有本轮挂载残留。记录该暂态提示，不将其描述为第一次卸载就全部成功。

- [32 项完整用例与退出码](../../../shared/evidence/glmark-optimization-20261016/regression32-summary.json)
- [32 项结果及完整共享场景分析](../../../shared/evidence/glmark-optimization-20261016/regression32-analysis.json)
- [同 Host 原生/Clientproxy 完整比较](../../../shared/evidence/glmark-optimization-20261016/native-client-comparison.json)
- [同镜像缓存开关交替数据](../../../shared/evidence/glmark-optimization-20261016/cache-ab-comparison.json)
- [实际执行的原生测试脚本](../../../shared/evidence/glmark-optimization-20261016/native-opp3-glmark.sh)
- [载荷、命令、源码和结束状态清单](../../../shared/evidence/glmark-optimization-20261016/manifest.json)

结束时已将通过本轮验证的 e800 Client 候选安装到控制机和 RK 的 shared Client Image 路径，保留原 cadce Client 备份；Proxy 保持 e83，Host 保持 opp3。只有 source 性能 profile 才启用两个实验开关。该操作没有更新固定发布 manifest，也没有提交或推送；固定基线恢复工具会将此视为自行构建载荷差异。

最终检查同一次启动、无 VM/broker、pmthor 绑定、原生模块已卸载、CPU 0–1、userspace/300 MHz、无本轮原生挂载残留，未发现 BUG/Oops/WARNING/DMA-API/reset failed。保留系统启动时已有的其他外设及 efi.mount 错误，不宣称整机所有服务均健康。

控制机 `GPU-SFTP/linux-host-kernel/Image` 仍是原固定恢复载荷，并不是当前运行的 opp3 Host；重新部署 Host 必须使用本报告列出的 opp3 构建包和匹配模块，不能误用该旧 Image。

所有 PASS 均对应实际执行的命令、退出码、run-id 和日志路径。原始失败、未采用候选和未执行范围保留于长记录；没有提交、推送或发布代码。

## 1280x720 全部 33 个场景

| 场景 | 原生 FPS | Clientproxy FPS | FPS 保留率 | 每帧增加 ms |
| --- | ---: | ---: | ---: | ---: |
| `[build] use-vbo=false:` | 947 | 1020 | 107.71% | -0.075 |
| `[build] use-vbo=true:` | 2282 | 1524 | 66.78% | +0.218 |
| `[texture] texture-filter=nearest:` | 2322 | 1509 | 64.99% | +0.232 |
| `[texture] texture-filter=linear:` | 2319 | 1508 | 65.03% | +0.232 |
| `[texture] texture-filter=mipmap:` | 2304 | 1509 | 65.49% | +0.229 |
| `[shading] shading=gouraud:` | 1916 | 1432 | 74.74% | +0.176 |
| `[shading] shading=blinn-phong-inf:` | 1883 | 1422 | 75.52% | +0.173 |
| `[shading] shading=phong:` | 1717 | 1337 | 77.87% | +0.166 |
| `[shading] shading=cel:` | 1709 | 1335 | 78.12% | +0.165 |
| `[bump] bump-render=high-poly:` | 1069 | 1014 | 94.86% | +0.051 |
| `[bump] bump-render=normals:` | 2611 | 1545 | 59.17% | +0.264 |
| `[bump] bump-render=height:` | 2466 | 1527 | 61.92% | +0.249 |
| `[effect2d] kernel=0,1,0;1,-4,1;0,1,0;:` | 1761 | 1385 | 78.65% | +0.154 |
| `[effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;:` | 826 | 748 | 90.56% | +0.127 |
| `[pulsar] light=false:quads=5:texture=false:` | 1684 | 1234 | 73.28% | +0.217 |
| `[desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4:` | 387 | 256 | 66.15% | +1.323 |
| `[desktop] effect=shadow:windows=4:` | 847 | 681 | 80.40% | +0.288 |
| `[buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map:` | 47 | 46 | 97.87% | +0.730 |
| `[buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata:` | 47 | 46 | 97.87% | +0.711 |
| `[buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map:` | 66 | 65 | 98.48% | +0.152 |
| `[ideas] speed=duration:` | 481 | 404 | 83.99% | +0.395 |
| `[jellyfish] <default>:` | 1224 | 1055 | 86.19% | +0.131 |
| `[terrain] <default>:` | 78 | 51 | 65.38% | +6.969 |
| `[shadow] <default>:` | 982 | 779 | 79.33% | +0.266 |
| `[refract] <default>:` | 196 | 161 | 82.14% | +1.116 |
| `[conditionals] fragment-steps=0:vertex-steps=0:` | 1972 | 1440 | 73.02% | +0.188 |
| `[conditionals] fragment-steps=5:vertex-steps=0:` | 1855 | 1410 | 76.01% | +0.170 |
| `[conditionals] fragment-steps=0:vertex-steps=5:` | 1967 | 1449 | 73.67% | +0.182 |
| `[function] fragment-complexity=low:fragment-steps=5:` | 1965 | 1448 | 73.69% | +0.182 |
| `[function] fragment-complexity=medium:fragment-steps=5:` | 1737 | 1359 | 78.24% | +0.160 |
| `[loop] fragment-loop=false:fragment-steps=5:vertex-steps=5:` | 1961 | 1448 | 73.84% | +0.181 |
| `[loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5:` | 1962 | 1448 | 73.80% | +0.181 |
| `[loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5:` | 1731 | 1357 | 78.39% | +0.159 |

## 1920x1080 全部 33 个场景

| 场景 | 原生 FPS | Clientproxy FPS | FPS 保留率 | 每帧增加 ms |
| --- | ---: | ---: | ---: | ---: |
| `[build] use-vbo=false:` | 742 | 954 | 128.57% | -0.300 |
| `[build] use-vbo=true:` | 1775 | 1380 | 77.75% | +0.161 |
| `[texture] texture-filter=nearest:` | 1560 | 1235 | 79.17% | +0.169 |
| `[texture] texture-filter=linear:` | 1568 | 1236 | 78.83% | +0.171 |
| `[texture] texture-filter=mipmap:` | 1566 | 1239 | 79.12% | +0.168 |
| `[shading] shading=gouraud:` | 1517 | 1210 | 79.76% | +0.168 |
| `[shading] shading=blinn-phong-inf:` | 1481 | 1194 | 80.62% | +0.163 |
| `[shading] shading=phong:` | 1301 | 1094 | 84.09% | +0.145 |
| `[shading] shading=cel:` | 1277 | 1079 | 84.49% | +0.144 |
| `[bump] bump-render=high-poly:` | 943 | 883 | 93.64% | +0.072 |
| `[bump] bump-render=normals:` | 1820 | 1390 | 76.37% | +0.170 |
| `[bump] bump-render=height:` | 1620 | 1290 | 79.63% | +0.158 |
| `[effect2d] kernel=0,1,0;1,-4,1;0,1,0;:` | 937 | 860 | 91.78% | +0.095 |
| `[effect2d] kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;:` | 448 | 376 | 83.93% | +0.432 |
| `[pulsar] light=false:quads=5:texture=false:` | 1170 | 1032 | 88.21% | +0.114 |
| `[desktop] blur-radius=5:effect=blur:passes=1:separable=true:windows=4:` | 233 | 209 | 89.70% | +0.502 |
| `[desktop] effect=shadow:windows=4:` | 591 | 562 | 95.09% | +0.086 |
| `[buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=map:` | 47 | 44 | 93.62% | +1.780 |
| `[buffer] columns=200:interleave=false:update-dispersion=0.9:update-fraction=0.5:update-method=subdata:` | 47 | 43 | 91.49% | +1.764 |
| `[buffer] columns=200:interleave=true:update-dispersion=0.9:update-fraction=0.5:update-method=map:` | 65 | 65 | 100.00% | +0.076 |
| `[ideas] speed=duration:` | 433 | 374 | 86.37% | +0.368 |
| `[jellyfish] <default>:` | 762 | 712 | 93.44% | +0.092 |
| `[terrain] <default>:` | 57 | 48 | 84.21% | +3.622 |
| `[shadow] <default>:` | 688 | 610 | 88.66% | +0.184 |
| `[refract] <default>:` | 144 | 138 | 95.83% | +0.286 |
| `[conditionals] fragment-steps=0:vertex-steps=0:` | 1356 | 1128 | 83.19% | +0.149 |
| `[conditionals] fragment-steps=5:vertex-steps=0:` | 1250 | 1081 | 86.48% | +0.126 |
| `[conditionals] fragment-steps=0:vertex-steps=5:` | 1335 | 1129 | 84.57% | +0.137 |
| `[function] fragment-complexity=low:fragment-steps=5:` | 1333 | 1126 | 84.47% | +0.138 |
| `[function] fragment-complexity=medium:fragment-steps=5:` | 1114 | 1013 | 90.93% | +0.090 |
| `[loop] fragment-loop=false:fragment-steps=5:vertex-steps=5:` | 1332 | 1126 | 84.53% | +0.137 |
| `[loop] fragment-steps=5:fragment-uniform=false:vertex-steps=5:` | 1331 | 1127 | 84.67% | +0.136 |
| `[loop] fragment-steps=5:fragment-uniform=true:vertex-steps=5:` | 1109 | 1009 | 90.98% | +0.089 |
