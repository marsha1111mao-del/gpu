# 安全边界与证据

| 边界 | 发布版保护 | 证据范围 |
| --- | --- | --- |
| 队列与会话 | 校验身份、窗口、描述符、序号和大小，按会话绑定对象与额度 | 离线检查和部分实体端点及异常输入 |
| 私有内存与 GPUVM | 校验实际页表、backing、归属与代次，事务维持引用和设备可见性 | 软件及实体用例覆盖特定路径 |
| 任务与设备 | 任务绑定当前命令、映射和状态，RMM 仲裁敏感配置及发布 | 已验证固定负载和部分异常，MEM05 仍待完整验证 |
| 完成与回收 | 按设备进度、可信 IRQ、错误历史和引用授权退休 | 双 Client 功能、IRQ 与 eventfd；部分故障缺少 owner-scoped 恢复 |

第二阶段 88 项 scoped evidence 的适用范围写在各检查中。四项物理结论仍为 NOT_VERIFIED。旧 Group submit fence 超时专项仍有未解决记录。[威胁模型](../shared/GPU_SHARED_THREAT_MODEL_SECURITY_DESIGN_ANALYSIS_20261109.md) · [验证矩阵](../shared/GPU_SHARED_SECURITY_TEST_MATRIX_20261109.csv)

## 实体反例

- 在本发布版本和板卡上，三个缺少 IOMMU 的 PL330 控制器在两种委托时序下共观察到六项 DMA 读写旁路。现有保护无法建立整个 SoC 的 DMA 隔离。
- raw-CSF 专项在特定用例中阻断了越界访问，受害数据保持，但有后续 Client 提交或计算失败。r152 候选观察到 quarantine 生效，后续恢复、引用回收和可用性仍 FAIL。
- 后续候选试验了命令页哈希及 mapping epoch 绑定。软件矩阵与实体结果分别判定。1170 版不包含这些后续候选。

判定分为 PASS、FAIL、NOT_RUN、NOT_VERIFIED。每条证据保留运行范围与退出码。资源恢复和安全目标分别判断。[发布验收记录](05-results.md)
