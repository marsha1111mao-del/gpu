# 历史记录与研究资料

本目录于2026-10-18整理。当前实现以[当前基线](../../shared/CURRENT_BASELINE.md)为准，本文档归档不改变任何历史测试结论。

- `history/`：20份历史实现、发布、资源审计与实验报告，保留失败、未执行项和逐轮性能证据。
- `research/`：7份论文调研、理想模型与架构提案，部分内容尚未实现，不能当作当前代码能力。
- 原始日志、镜像与旧冻结输入仍位于报告记录的位置，不复制到文档目录。

主要历史入口：

| 资料 | 用途 |
| --- | --- |
| [P42逐轮性能优化](history/PROXY_REALM_PERFORMANCE_OPTIMIZATION_20261018.md) | P1–P42保留/撤回原因、前后分数与命令 |
| [任务代理与RMM实现演进](history/PROXY_TASK_SERVICE_IMPLEMENTATION_20261017.md) | 协议、生命周期、通知与故障修复证据 |
| [修复前Native/P42全套性能](history/GPU_NATIVE_CURRENT_REALM_PERFORMANCE_20261018.md) | 修复前指标与失败记录 |
| [历史32项回归对照](history/GPU_REGRESSION_COMPARISON_20261015.md) | 旧普通VM矩阵，不等同当前Realm验收 |
| [发布与后续失败](history/GPU_REPOSITORY_PUBLICATION_20261015.md) | 固定发布载荷及额外fence超时 |
| [Portal实现分析](research/PORTAL_IMPLEMENTATION_DEEP_DIVE_20261015.md) | 论文机制参考 |
| [Portal/CAGE/ACAI研究方向](research/PORTAL_CAGE_ACAI_RESEARCH_IDEAS_20261015.md) | 待研究的创新方向 |
| [V2架构提案](research/PROXY_REALM_GPU_ARCHITECTURE_V2_20261017.md) | 提案范围；实际已实现子集见当前基线 |

2026-10-16固定OPP诊断模块已由Host正式devfreq替代，没有当前构建或runner调用者，源目录已移除。为核对历史源码SHA，本机保存了小型源文件归档`build/workspace-cleanup-20261018/retired-fixed-opp-source.tar.gz`；历史报告提到该路径时是当时状态，不表示仍应加载旧模块。
