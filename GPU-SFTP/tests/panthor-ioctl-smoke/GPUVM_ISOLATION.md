# 旧 Proxy GPUVM 隔离探针的退役说明

2026-11-09 源码清理移除了 `--gpuvm-isolation`、`--gpuvm-fault-isolation`、
`gpuvm_isolation.h` 及 `DRM_PANTHOR_VM_CREATE_ISOLATED`。
原探针依赖 Proxy manager 的 BO 归属和“一生一个 GROUP”策略，不能直接用于当前
Client 私有 BO、RMM 页面/任务授权与可信 FINISH 设计。VM_CREATE 的 flags 现在必须为零。
此文件保留为历史文档链接的说明入口，不是可执行测试说明。

当前验证入口为 [Realm 工具说明](../realm-xshm/README.md)中的私有 DRM/提交探针、
双 Client GLES 数据与 eventfd 校验，以及 `scripts/check/check-rmm-gpu-private.sh`
涵盖的真实 RMM 代码配合受控后端的授权、页表、控制资源和撤权负例。
这些测试各有范围，不等价于已执行任意恶意 GPU 命令或实体平台跨域访问攻击。

旧报告中的同 GPUVA LOAD/STORE、故障注入、manager 自测及其 PASS 只适用于当时版本。
当前恶意访问和物理隔离的专项验证仍按
[攻击测试计划](../../../docs/shared/GPU_SHARED_ATTACK_TEST_PLAN_20261109.md)分别设计与执行，
未执行项保持 NOT_RUN/NOT_VERIFIED；不因移除旧探针而宣称新的隔离证明完成。
