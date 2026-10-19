# 保留安全约束的六方向性能优化实验

2026-10-18。**当前结论：仅保留 GPUVM 待同步映射列表；其完整720p两轮为1171、1170，对照1162、1160，均值提高9.5分（约0.82%）。** 同BO区间合并1171，与仅列表1171/1170没有增量收益证据，已撤回。最终双Client功能验收已通过，板端已部署同一冻结输入。

## 基线、条件与判断标准

依据用户要求，六个方向均实现候选、构建冻结并运行完整720p；不提分的候选撤回，不留下闲置开关或框架。当前基线入口见[CURRENT_BASELINE](CURRENT_BASELINE.md)。

- 父仓库对照：`87f5403223b54cef2cde67cb1625d93ad9ce4dc1`；Guest对照：`3cd87b3eedc675f9f1c6ce1cc22f41451da1614a`。保留代码目前是该Guest提交之上的本地三文件补丁，没有将旧发布manifest冒充新载荷。
- 对照冻结包：`build/memfd-retirement-20261018/candidate/`。本次两个同期对照1162、1160；历史1157只作背景，不能当作本次优化前单变量对照。
- 条件：默认256MiB池、每Realm768MiB、CMA320MiB，Proxy CPU1 / Client CPU2；GPU请求600MHz、实际594MHz；CPU未固定恒定频率。相同runner、initrd、配置、用户态及33场景；正式计分关闭RPC计时。
- 单侧改动保留另一侧原镜像，逐包核验SHA。未修改Host/RMM/VMM/固件，没有刷写。硬件运行全经lab-run独占租约，前后记录资源。
- 微小单轮分差不足以证明稳定收益或退化。列表候选两轮均优于同期对照，故保留这项小幅优化；两对样本不足以给出统计显著性、长期稳定性或其他负载收益保证。

## 分数与保留决定

表中单轮候选统一对照首轮1162，第二组列表另外与紧邻的基线1160配对。分差未必都是代码导致，撤回标准是没有足够收益支持新增复杂度。

| 方向/候选 | 对照 → 候选 | 分差 | 决定 |
| --- | --- | --- | --- |
| 扩大普通syncobj延迟/批量回收 | 1162 → 1160 | −2 / −0.17% | 撤回 |
| 融合首次物化的CREATE+TRANSFER | 1162 → 1161 | −1 / −0.09% | 撤回 |
| GPUVM待同步映射列表，第1组 | 1162 → 1171 | +9 / +0.77% | 保留，已重复测量 |
| GPUVM待同步映射列表，第2组 | 1160 → 1170 | +10 / +0.86% | 保留 |
| 自适应RPC短轮询 | 1162 → 1161 | −1 / −0.09% | 撤回；未测CPU占用/功耗 |
| 缩短计划锁、固定在途槽位 | 1162 → 1159 | −3 / −0.26% | 撤回 |
| 分离接收与原生提交的有界流水线 | 1162 → 1156 | −6 / −0.52% | 撤回 |
| 按原生完成进度跳过无效输出扫描 | 1162 → 1156 | −6 / −0.52% | 撤回 |
| 列表＋同BO重叠/相邻区间并集 | 1162 → 1171 | +9 / +0.77%；对仅列表0—1分 | 撤回额外合并逻辑；无增量收益证据 |

列表：对照均值1161 → 候选均值1170.5，**+9.5 / +0.82%**。首轮33场景中27升、3降、3平；第二轮30升、0降、3平。逐场景数据保留在实验目录`paired-scenes.json`。这不是所有场景都有固定百分比收益的承诺。

旧文档1157 → 本次未改代码的基线1162，+5/+0.43%，仅为重测差异，不能记作本次代码提分。Native1437是历史参考，本轮没有重新测Native。

## 保留实现：减少遍历，不减少必要同步

涉及三个文件：

- [panthor_gem.c](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.c)：把原有资格判断提取为`panthor_gem_needs_realm_sync()`，保持“Realm私有、非导入、非共享池、非GPU_ONLY”的原条件。
- [panthor_gem.h](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.h)：模块内声明，无新用户接口或协议位。
- [panthor_mmu.c](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c)：每个GPUVM维护待同步VMA列表；map/remap/unmap同步维护节点；缓存同步在`op_lock`保护下只遍历这份列表。

原实现每次扫描GPUVM全部映射，再由BO函数排除无需维护的对象。新实现提前维护索引，避免高频路径反复遍历无关映射和判断。必要BO的偏移、长度、同步方向和DMA操作不变；没有合并或扩大范围，也不依赖Client自报dirty状态。列表资格相关字段在BO建立时确定，已映射期间不改；释放时先解绑节点，保持现有对象引用及原生VM生命周期。

缓存同步新增`op_lock`，与原map/remap/unmap使用相同锁保护列表；复核未发现新增的直接反向锁等待。硬件性能配置未开启完整lockdep，不能据此宣称完成锁关系证明。RMM端点授权、会话归属、私有消息副本、配额、BO清零、真实fence和IRQ/ACK_ARM路径均未更改。

冻结最终输入：`build/safe-optimization-20261018/final/`，逐字节复制两轮已测`sync-list`包；保留源码逐文件与该包快照比较一致，不因目录名不同重计一次性能验证。

## 其余候选实现及无收益原因

以下为结合调用频率和实现结构的解释，不是独立时延剖析得到的精确归因。

| 候选 | 已实现的安全约束 | 本负载未获益的解释/边界 |
| --- | --- | --- |
| 普通syncobj退休 | 最后Client引用后入队；容量8；关闭/满队回原路径；Proxy全批归属校验后删除；原生引用保活和计划失效 | 已有P42覆盖高频私有快照，新增范围主要是剩余低频对象；不删除原P42 |
| CREATE+TRANSFER融合 | 功能协商；先取源引用再分配；native失败清理新对象；成功后才发布新句柄；传输超时不重放 | 累计384007个本地syncobj仅72个物化，不能把本地惰性创建量误当可节省RPC量 |
| 自适应轮询 | 私有16桶反馈、64—1000us有界预算及周期探测；保留IRQ、通知恢复、ACK_ARM和睡前重查 | 反馈也有成本；没有CPU占用或功耗数据，不称同分节能 |
| 缩短计划锁 | 每槽在途users固定身份/代际；8槽全忙时第9请求等待；仅派发前ESTALE重试，传输超时不重放 | glmark主要串行提交，可消除的锁竞争有限，却新增引用维护及加锁 |
| 有界提交流水线 | 256项私有请求；通道/会话引用；关闭排空；原生提交校验后回复，完成仍看真实fence | 单线程Client仍等待同步接纳，worker交接可能抵消接收重叠；未测多Client吞吐，不否定其他流水线设计 |
| 完成进度过滤 | 同步元数据后捕获完成序号，再同步payload；只发布捕获范围内fence；缓存错误不发布 | 没有单独统计worker空转比例，不能将几分差异精确归因到某分支 |
| 同BO区间并集 | 列表上16项有界栈批次，只合并同对象交叠/相邻范围；保留空洞/对象边界；校验溢出/BO长度，无信任Clientdirty | 组合1171，对仅列表1171/1170仅0—1分；没有额外收益证据，不将列表收益重复归因 |

主会话457661次计划执行，Client缓存457658命中/3未命中；Proxy76次注册还包括资源变更引起的重新注册。普通BO_DESTROY日志31条，也不支持逐帧大量销毁的假设。

## 构建、验证及证据边界

八个独立候选的Image均构建通过。实验时补丁和源码快照位于忽略的`build/safe-optimization-20261018/<候选>/`；后续清理已移除这些候选目录，补丁/源码/配置/哈希统一归档至`build/safe-optimization-20261018/archive/experiment-source-20261018.tar.gz`，不保留无收益候选镜像。生产源码只保留列表改动，当前可运行冻结包为`final/`。每包核验配置/runner/initrd一致、另一侧镜像一致、SHA正确且补丁可应用于发布基线；OpenCCA补丁清单检查通过，其预期diff未被清理。

实际候选函数提取的ASan/UBSan检查覆盖：退休最后引用/批次/额度；融合权限与失败清理；列表资格、别名范围和解绑；轮询预算及通知；8并发计划及第9等待；流水线256额度、引用、失败/关闭；捕获完成到缓存再到fence顺序及负向突变；区间并集桥接/空洞/对象身份、100别名与独立位图比较、批次上限和越界错误。

日志`*-check.log`仍在实验目录；脚本`check-*.py`和生成的检查源码已移入上述证据归档，临时可执行文件已删除。使用传输、内核锁和原生操作桩，不能代替内核完整并发证明。保留的初版检查失败是测试模型问题：只读轮询参数被当作运行中可变、函数提取误匹配声明、模型VMA未走延后清理；修正模型后通过，原失败日志未删除。

已完成的完整720p均为wrapper退出0、工作负载PASS、33场景、validation **26成功 / 1既有数值例外 / 6无判据**、Realm退出0；内核健康无异常，CPU/驱动恢复，无VM/loop残留。不称33项全正确，也不继承旧32项PASS。

最终双Client验收：**PASS**，`safeopt-20261018-final-dual`，wrapper退出0、三个Realm退出0；各17项API（含VM_BIND、异步同步、Group提交/fence及BO/Group生命周期）通过；各65536元素计算、16样本校验、64次ALU迭代通过。双绑定、共享内存检查、权限负例、IRQ127负例与合并检查通过，内核健康和资源恢复通过。独立provider replacement生命周期用例为**NOT_RUN**，不由双Client测试代替。1080p、ResNet50、完整历史矩阵、多vCPU、长期压力和CPU功耗本轮均未执行。

当前GPT/GPC仍有模拟边界，GPU跨Group shadow页表隔离尚未实现；本轮局部优化不扩大机密隔离保证，Host仍可拒绝服务。

## 复现与逐次运行记录

所有性能运行使用：

```bash
python3 scripts/maintenance/lab-run.py --run-id <下表ID> -- \
  python3 scripts/run/run-realm-xshm.py --images <冻结包> \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

每次记录均包含：改动目的｜对照→候选分数及绝对/百分比变化｜配置差异｜run-id、完整命令、退出码及日志｜保留/撤回。上表提供前两项，下面表格提供运行对应关系；完整命令和输入SHA在同名wrapper证据中。

| 目的 | run-id（前缀均为`safeopt-20261018-`） | 测量时冻结包（实验目录下，基线除外） | 退出码 |
| --- | --- | --- | --- |
| 首轮对照 | `baseline-r1` | `build/memfd-retirement-20261018/candidate` | 0 |
| 扩大回收 | `retire-r1` | `retire-syncobjs` | 0 |
| RPC融合 | `clone-r1` | `clone-syncobj` | 0 |
| 待同步列表 | `sync-list-r1` | `sync-list` | 0 |
| 自适应轮询 | `adaptive-r1` | `adaptive-poll` | 0 |
| 缩短计划锁 | `plan-lock-r1` | `plan-lock` | 0 |
| 接收/提交流水线 | `pipeline-r1` | `pipeline` | 0 |
| 完成进度过滤 | `cache-progress-r1` | `cache-progress` | 0 |
| 第二轮对照 | `baseline-r2` | 同首轮对照 | 0 |
| 列表复测 | `sync-list-r2` | `sync-list`，与首轮逐字节相同 | 0 |
| 列表＋区间并集 | `cache-union-r1` | `cache-union` | 0 |
| 最终双Client功能 | `final-dual` | `final`，与两轮列表包相同 | 0 |

本地wrapper：`build/lab-runs/<完整run-id>/`（命令、退出码、前后资源）；原始输出：`build/safe-optimization-20261018/logs/<完整run-id>/`；对应归档为同实验目录的`<完整run-id>.tar.gz`，包含远端`summary.json`及串口日志。远端原始位置：`/root/GPU-SFTP/log/realm-xshm/<完整run-id>/`。原始运行日志、编译缓存和凭据不提交Git。

最终功能命令为将上面负载参数改为`--workload compute`，包为`build/safe-optimization-20261018/final`。实验目录`results.json`保留每次命令、SHA、退出码、分数、场景、健康及资源恢复记录；已定版精简证据：[逐次结果与保留决定](evidence/safe-optimization-20261018/results.json)、[候选校验](evidence/safe-optimization-20261018/candidate-validation.json)、[两组逐场景对照](evidence/safe-optimization-20261018/paired-scenes.json)、[最终功能验收](evidence/safe-optimization-20261018/final-validation.json)、[最终输入](evidence/safe-optimization-20261018/retained-inputs.json)、[源码SHA](evidence/safe-optimization-20261018/runtime-source-hashes.json)、[板端输入SHA](evidence/safe-optimization-20261018/deployed-inputs.json)、[最终资源](evidence/safe-optimization-20261018/final-resources.json)。

最终审计：板端client/proxy/initrd/runner均与`final`包SHA一致；RK无VM/loop残留，CPU0—1及pmthor恢复。Pi空闲，`/dev/loop0 /var/swap`是系统交换文件，未删除。Pi约15.60GiB、RK约13.94GiB可用。旧发布runtime-manifest未改；当前本地源码和新冻结包需在后续发布时另行归档，不能由旧manifest恢复出本次优化。

## 无收益候选清理复核

本轮仅清理开发产物并复核源码：**未改运行代码，无新增性能测量**，不据此宣称提分。已验证的列表版本仍为1171/1170；同期对照1162/1160，均值+9.5/+0.82%的结论不变。

- Guest相对发布基线仅保留列表三文件补丁，且与已测`final/guest.patch`逐字节一致。Client通信、Client驱动、Proxy驱动、调度完成处理及协议头五文件均与基线完全一致；12个撤回候选特有标记均不存在，无未跟踪的Guest源码文件。
- 删除八个测量候选目录（七个撤回候选、一个已被`final/`替代的重复列表包）、已结束的实验执行/生成脚本、临时检查程序和两个无收益候选残留的构建缓存Image；共130文件，净回收704.11MiB。普通增量构建缓存不作为运行镜像；后续构建需重新生成Image。
- 补丁、源码、配置、原始输入哈希及检查脚本压缩归档，SHA为`f2dd78d1e2cf27d7e0114873004fa1340e426882631e93c4e033c4030e032338`；原始运行/失败日志、对照基线及当前`final/`冻结包保留。表中的旧候选目录仅说明测量时来源，已不能直接用作`--images`输入。
- 删除前核对文件SHA、大小、修改时间和进程占用；归档内容校验后删除，清理后复核130个路径全部消失。当前60项源码哈希和`final/`四项冻结输入哈希保持一致。没有操作Pi/RK或改变板端已验收输入，因此没有追加硬件测试。

逐文件大小、时间、SHA、删除原因、归档位置及验证结果见[清理审计](evidence/safe-optimization-20261018/cleanup-audit.json)。
