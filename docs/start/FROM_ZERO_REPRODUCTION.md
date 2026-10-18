# 从零复现：统一入口

本页的旧路径、旧网络地址与镜像策略已被当前流程替代。
请使用[无上下文 Agent 环境部署与测试手册](AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)。

- 已有健康板端：[快速复现](FRESH_CLONE.md)。
- 新 Pi、串口、Maskrom、SD 刷写：[Pi 刷机手册](RASPBERRY_PI_FLASH_RUNBOOK.md)。
- 固定载荷与第三方来源：[ARTIFACTS](../../GPU-SFTP/ARTIFACTS.md)。
- 已执行验证与未解决记录：[发布记录](../archive/20261018/history/GPU_REPOSITORY_PUBLICATION_20261015.md)。

先确认控制机、Pi、RK 三种角色，再恢复固定子模块与载荷。两个 Guest rootfs
不能替代完整 Host SD 镜像；当前正常刷写目标固定为 storage ID 2（SD）。
新机器无需复用原开发者私钥或绝对路径。
