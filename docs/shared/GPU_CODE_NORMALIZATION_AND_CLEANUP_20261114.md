# GPU代码规范化与淘汰路径清理：第二阶段验收

本阶段完成项目自有核心GPU/通信代码的统一排版、旧接口收敛和配套测试维护。与第一阶段共用同一运行与安全设计；完整五项目标还包含大型真实任务和virtio-gpu性能对照，它们各自以独立实测结果验收。

Notion验收文档：https://app.notion.com/p/417659a3b8cc819f8efbc33bf6ff2893 。代码清单：https://app.notion.com/p/417659a3b8cc815a9d17f18e18ec0713 。

## 已完成的整理

| 工作 | 实际变更与依据 |
| --- | --- |
| 运行代码规范化 | 28份自有C/头文件统一到仓库Linux风格，25份有变化；逐文件C token及函数式宏类型一致，include顺序/字面量保持。clang-format18.1.8固定版本，全部目标dry-run通过 |
| 淘汰旧接口 | 删除无运行调用者的opencca_gpu_pm_destroy_blocked查询及声明；旧/新生产链接镜像均不含它；销毁实际仍经destroy_begin状态转换 |
| 测试真实保护 | lease模型直接核对destroy_begin在未撤权时拒绝，以及非owner销毁不改变真实GPUowner；3模式和2个成功编译的错误变体拒绝通过 |
| 保留有用模型适配器 | task_hold单范围适配器和冷finish适配器有明确模型使用者、共享同一实际内部逻辑且不进入生产镜像，头文件注明用途 |
| 检查器收敛 | 多个checker共用按C token匹配/唯一计数/完整函数提取，避免绑定缩进；清理9处已由公共替换函数覆盖的重复count断言。19个契约测试覆盖字符串/注释、行拼接、操作符、歧义/缺失、声明/调用和换行返回类型 |
| 阅读入口收敛 | 当前基线只保留当前包/条件/证据及链接；完整历史保留归档。功能安全清单按16组件、41文件及R01—R14对应真实入口 |

没有因低调用频率删除故障、冷启动、依赖错误传播、撤权、部分效果保留或安全退休路径。realm_xshm_trace_show由DEFINE_SHOW_ATTRIBUTE生成file ops引用，明确保留。生产API、私有ABI2、内部RPC6和Root IRQ ABI2保持；未引入额外权威缓存或未来空框架。

## 性能与功能

| 指标 | 第一阶段 | 第二阶段 | 判断 |
| --- | --- | --- | --- |
| 完整720p | 1163 | 1170 | +7/+0.60189%；同预算成套构建组合，不归因单项排版或删除 |
| S8历史原两轮 | 1170/1172，均值1171 | 1170 | 对均值−1/−0.08540%，不构成稳定退化判断 |
| 场景与validation | 完整33，26成功/1已知失败/6未知 | 相同 | 既有已知失败与未知保留 |
| blur/terrain/refract | 208/37/137 | 211/38/137 | 原保护线通过 |
| 双Client功能 | PASS | PASS | 两端真实DRM、每端4×65536全值、binary/timeline eventfd及端点/IRQ负例 |
| 全量离线 | 第一阶段61项 | 第二阶段累计63项PASS | 新增C源码匹配契约及控制机恢复契约；88项scoped/4项物理NOT_VERIFIED |

可比条件：固定Mesa25.0.7、1280×720完整33场景、GPU实际594MHz、原CPU/内存预算和配额8，Root/FW来源及用户态/runner/initrd保持；本阶段重建成套RMM/Client/Proxy，固件布局/FIT与来源核验通过，不将组合收益拆成独立优化项。

统一记录：规范化项目自有GPU路径并收敛已无运行调用的销毁查询｜第一阶段1163→第二阶段1170｜+7/+0.60189%｜条件及组合差异见上｜`gpu-normalize2-720-r1-20261114`外层/负载/UART/两Realm均0，9日志SHA；`gpu-normalize2-compute-r1-20261114`全部退出0、10日志SHA；`gpu-normalize2-full-offline-r5-20261114 --verify-runtime --include-aggregate`62项通过，`gpu-normalize2-aggregate-r6-20261114`完整汇总确认后累计63项PASS；`gpu-normalize2-final-audit-r1-20261114`来源/实际SD2/4运行输入/38源/Host健康资源审计0｜保留并安装匹配默认运行文件。

所有完整命令、退出码与前后资源在 `build/lab-runs/RUN_ID/`；图形/功能日志SHA副本在 `build/gpu-normalization-20261114/runs/RUN_ID/`；离线日志及模型/编译错误变体在 `build/security-runs/RUN_ID/`。权威摘要为 `phase2/phase2-graphics-audit.json`、`phase2/phase2-functional-audit.json`、`phase2/phase2-final-board-audit.json`、`phase2/format-proof.json` 和 `phase2/code-inventory-source.json`。

最终全量轮次常规62项通过，汇总晚期的回收负例因旧换行匹配失败；仅修正该负例匹配后另跑完整汇总，累计63项通过，不能称同轮63/63。首轮离线未通过的项目来自排版相关的旧源码提取/负例构造；保留原FAIL和原始日志，修正后执行最终完整回归，不改GPU准入/完成/可见性/退休条件换PASS。失败只在进度账本简述，不堆积为当前设计。

## 安全职责与代码清单

见[功能与安全代码清单](GPU_CODE_FUNCTION_AND_SECURITY_INVENTORY_20261114.md)，按Client/Proxy/RMM/Monitor/平台/Host及验证入口说明真实函数、数据关系和权限；另有R01—R14到实际实现入口对应。A数据隔离、B对象/意图、C敏感控制、D可信完成/可见性、E生命周期、F接口治理均保留现有机制和本轮相应范围证据。

本轮不升级MEM05完整操作数/间接流/准入后内容一致性、真实恶意shader或完整物理CPU/DMA/GIC/整设备残留保证；旧Group fence专项未复验。普通负载与软件负例通过不等于完整物理安全证明。Native性能基准按用户要求未执行。

冻结包为 `build/gpu-normalization-20261114/phase2/normalized-combination-r2/{graphics-runtime,compute-runtime,firmware}`，按成套清单恢复，不混搭旧固件或内核。新Client/Proxy均来自同一源码快照和原配置；Host/Image/rootfs未为规范化重刷。后续大型模型和virtio实验分别记录，未成功项不纳入本阶段性能结论。
