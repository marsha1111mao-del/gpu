# GPUVM 隔离强化开发与验收

本轮在已发布开发检查点之后强化可信Proxy管理的真实GPUVM，不修改Host/RMM。设计依据和取舍见[GPUVM隔离v1](GPUVM_ISOLATION_V1_20261020.md)，前置发布版本见[Git检查点](GIT_DEVELOPMENT_CHECKPOINT_20261020.md)。平台已保护页表、控制内存、关键配置与工作态MMIO的假设保持不变。

## 软件约束

- Client/Proxy接受`DRM_PANTHOR_VM_CREATE_ISOLATED`；隔离GPUVM一生只允许一个Group，Group销毁后也不可在旧根重建。互不信任任务必须使用不同GPUVM；普通Mesa同GPUVM内的多个Group继续共享信任域。
- vmshm BO首次准备MAP时永久绑定真实根GEM引用。跨根普通/只读别名拒绝；整数VM句柄复用不能替换根身份。
- 可信Panthor检查对象存续、pin、GPU数据/命令类型及读写权限；Proxy核对session、owner、对象句柄/generation，并限制Client MAP/UNMAP的用户VA范围和溢出。
- 活动Group/heap阻止VM销毁；旧backing直到最后pin释放才可清零复用。管理器自测覆盖foreign owner、权限升级、控制页、撤销、旧generation与复用。
- 导出sync-file的内部私有snapshot等待显式检查原生fence错误；普通DRM等待保持原语义。成功cookie仍只代表完整原生fence成功。

这些检查发生在创建、映射、销毁和必要的sync-file回退等待处，不扫描每次正常提交的页表，不增加每条GPU指令的监控调用。没有增加Client影子页表或外置GPU SMMU S2。

## 输入与条件

Host为`6.12.0-opencca-pmthor-opp3 #31`，protected hVHE；RMM timer v6，Host/RMM/Firecracker/rootfs沿用既有组合。默认256MiB池，完整720p为null-noop/finish、33场景、shader cache禁用；性能模式CPU0–3、Proxy CPU1/Client CPU2，GPU请求600/实际594MHz。结束恢复CPU0–1、pmthor及300MHz。

当前开发冻结包为`build/gpuvm-isolation-20261020/final-f/`，包含匹配的Client/Proxy Image、initrd和runner。旧runtime-manifest和原冻结1171/1170包保持独立，不将源码发布等同二进制发布。

## 已知开发失败与修正

| run-id | 结果 | 原因与处理 |
| --- | --- | --- |
| `gpuvm-v1-720-20261020-a` | FAIL，rc1，无有效分数 | 自测错误要求buddy控制页复用extent数据页偏移；改为先用GPU_BO检查复用清零，再单独验证FENCE_PAGE拒绝 |
| `gpuvm-v1-720-20261020-b` | FAIL，rc1，无有效分数 | 无条件单Group限制破坏Mesa共享device GPUVM的EGL上下文创建；改为可信Proxy强制的显式隔离模式 |
| `gpuvm-v1-720-20261020-c` | PASS，rc0，1158 | 完整33场景与健康/恢复通过；未包含最终Client保留VA保护，不作为最终验收输入 |
| `gpuvm-v1-720-20261020-d` | PASS，rc0，1155 | 包含Client保留VA保护，完整33场景、0额外验证失败、健康与恢复通过；尚未包含sync-file错误传递修复 |
| `gpuvm-v1-dual-20261020-a` | FAIL，rc1，GPUVM探针未执行 | 非融合快照通过旧CREATE+TRANSFER路径创建，不具Proxy私有标记；新增状态读取错误拒绝它，sync-file为−EACCES。移除不必要的私有标记限制，保留会话归属、单对象范围与原生fence检查 |

原始A/B/C证据已拉回`build/gpuvm-isolation-20261020/attempts-a-b-c.tar.gz`。开发检查还修正了探针对foreign session的预期错误码，并补上导出sync-file后的poll；没有把这些修正前的未执行探针标为PASS。

## 验收记录

候选E完整720p：`gpuvm-v1-720-20261020-e`，rc0，**1160**，对照同Host #31/RMM timer v6既有1159为**+1分/+0.0863%**。完整33场景，validation为26成功、1既有数值例外、6无判据，额外失败0；Host/Guest无新增内核故障，VM退出均0，资源恢复通过。单轮波动不能归因为确定提速；本轮强化组合未观察到明显性能退化。该测量早于非融合快照兼容修复，不将E镜像标为最终验收输入。

最终F完整720p：`gpuvm-v1-720-20261020-f`，**PASS / rc0 / 1159**，与同Host/RMM的1159对照相比**0分/0%**。完整33场景、validation 26/1/6、额外失败0；Host/Guest健康与资源恢复通过，VM退出均0。F包含非融合快照兼容修复；本轮未观察到明显性能退化，不宣称确定提速。

统一记录：强化GPUVM映射/生命周期与错误完成语义｜同Host/RMM既有1159 → 最终F1159｜0/0%｜默认256MiB、相同720p/频率/CPU策略，Guest及探针重建，未固定CPU频率，多项强化按组合比较｜`gpuvm-v1-720-20261020-f`、复现章节性能命令、rc0、`build/gpuvm-isolation-20261020/720-f.log`及板端同run-id日志｜保留已验收开发冻结包，不替换原冻结1171/1170。

最终F的`gpuvm-v1-dual-20261020-b` **PASS / rc0**，完成以下语义检查，三个Realm退出均0，Host/Guest健康及资源恢复通过：

| 范围 | 实测结果 |
| --- | --- |
| 两侧API与快照 | 每Client 18模式通过，含128次导出/64次导入、源重置/销毁、DRM关闭及Group真实完成 |
| 每Client独立GPUVM | 两GPUVM同VA `0x401000`，交替32次实际CSF LOAD/STORE，canary与读回正确、sync-file成功；VM整数句柄实际复用，旧BO仍不能进入新根 |
| 软件负例与合法别名 | 第二Group、活动根销毁、跨根普通/只读别名、BO边界、保留VA MAP/UNMAP、溢出VA、foreign session及旧根重绑定拒绝；同域只读别名通过 |
| 双Client实际计算 | 两侧Mali-G610后端，count65536/samples16/alu_iters64，正确性通过 |
| 实际GPU越域VA | Client1中攻击Group读取只属于受害GPUVM的`0xa00000`，产生翻译故障，攻击者fence错误且Group fatal；受害canary完整并再次实际执行成功 |
| 管理器与健康 | 两个owner的GPU权限、控制页、旧generation、延迟复用/清零自测通过；准确单列一条本次预期TRANSLATION_FAULT_2，其余故障/警告列表为空 |

GPU实际故障测试针对同Client内的两个独立GPUVM；跨Client另有双侧实际执行、会话句柄拒绝与manager owner检查。跨Client的原始恶意RPC全矩阵未执行，不能把本地句柄拒绝称为绕过Client的RPC攻击验收。未执行1080p、NCNN、长时间压力、多vCPU、侧信道或片上残留测试；不继承历史PASS。真实控制内存、关键配置与物理访问保护沿用平台已有能力假设。

## 保留输入、清理与发布

Guest源码已发布为`af4eb42a1244ab221b73c15e15564de428721c97`；Host/RMM/Firecracker仍为前置检查点版本。最终输入与已测源码逐项SHA校验通过，见[输入](evidence/gpuvm-isolation-20261020/inputs.json)、[源码](evidence/gpuvm-isolation-20261020/source-hashes.json)及[验收汇总](evidence/gpuvm-isolation-20261020/validation.json)。开发包单独保留；正式二进制载荷/manifest与原冻结基线替换仍是独立发布工作。

最终双Client和性能完整原始证据在`build/gpuvm-isolation-20261020/final-evidence.tar.gz`，SHA为`1f46fc1383e0a91e1dbb0bd6a4dbb5ebefdc7e8511ed11d74f52b1a9eb98d22f`。D/E、失败dual A及A/B/C分别保存在同目录的`performance-d-e.tar.gz`、`dual-a-evidence.tar.gz`、`attempts-a-b-c.tar.gz`；失败事实不由后续PASS抵消。

验收后按准确路径、mtime、inode、SHA及打开fd检查，删除22个被F替代的中间镜像/initrd/重复探针，实际释放471.30MiB；最终F、当前构建树、全部源码/哈希及失败证据保留。详细清单位于`build/gpuvm-isolation-20261020/obsolete-cleanup-result.json`。Pi未新增snapshot，RK保留当前运行树和本轮近期证据，未新增板端编译树；此前三端清理结果见[清理报告](WORKSPACE_ARTIFACT_CLEANUP_20261020.md)。

本地场景二状态已更新为10项已实现、4项未实现/部分实现；Notion此前精简的9/5两区已核对。本轮再次连接时服务返回`MCP authentication required`，最新GPUVM条目迁移尚未写入Notion，需重新连接后同步；不将本地更新称为远端写入成功。

## 复现

先通过[主手册](../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)核对设备角色与输入，再使用独占入口：

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一性能ID> -- \
  python3 scripts/run/run-realm-xshm.py --images build/gpuvm-isolation-20261020/final-f \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
python3 scripts/maintenance/lab-run.py --run-id <唯一隔离ID> -- \
  python3 scripts/run/run-realm-xshm.py --images build/gpuvm-isolation-20261020/final-f \
  --workload compute --gpu-fault-isolation
```

wrapper证据位于`build/lab-runs/<run-id>/`，板端逐项命令、summary和串口位于`/root/GPU-SFTP/log/realm-xshm/<run-id>/`。原始日志不提交到Git；Notion仅维护当前两类状态，不追加失败流水。
