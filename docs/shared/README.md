# 当前设计与结果

从 [CURRENT_BASELINE.md](CURRENT_BASELINE.md) 开始；下面几项说明当前实现、代码调用链、资源配置和性能：

1. [当前设计、代码入口与冻结版本](CURRENT_BASELINE.md)
2. [Native / ProxyClient 全部有效性能对照](GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)
3. [大 BO 容量修复与最新验收](GPU_BO_CAPACITY_FIX_20261018.md)
4. [多 Realm 通信与 GPU 转发执行的代码与原理](REALM_COMMUNICATION_AND_GPU_EXECUTION_CODE_WALKTHROUGH_20261018.md)

[环境主手册](../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)负责部署与测试流程；[开发规范](../start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)负责资源与产物管理。

旧设计、逐轮实验和论文调研统一移到[归档索引](../archive/20261018/README.md)，不作为当前运行基线。`evidence/`保存脱敏指标/审计；原始运行日志和镜像保留在既有忽略目录。

[本轮目录整理记录](WORKSPACE_CLEANUP_20261018.md)说明删除范围、验证和保留原因。

[memfd退役与清理后验证](MEMFD_RETIREMENT_20261018.md)记录本次代码删除及性能影响。

[当前基线 Git 同步与发布检查](GIT_BASELINE_PUBLICATION_20261018.md)记录组件版本、离线检查和远端同步状态。
