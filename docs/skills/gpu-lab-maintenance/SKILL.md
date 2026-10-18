---
name: gpu-lab-maintenance
description: 检查 GPU 实验室 Pi/RK3588 的内存磁盘、清理废弃 snapshot 与暂存产物，并维护开发测试资源流程。
---

# Pi / RK3588 实验环境维护

先读 [环境主手册](../../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md) 和
[开发与产物管理](../../start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)。从仓库根目录执行。

实验室地址：Pi `mzh@192.168.31.189`（无线备用 `.52`），RK `root@192.168.31.18`。
仓库副本不保存密码；按主手册设置 `PI_HOST/PI_PASSWORD`、`RK_HOST/RK_PASSWORD`
或 `OPENCCA_*` / `REMOTE_*` 环境变量，也可使用已配置的 SSH 密钥。用户指定的凭据仅保留在本机私有 skill。

```bash
python3 scripts/maintenance/lab-resources.py --check \
  --output build/lab-maintenance/<时间戳>/resources.json
```

先识别设备角色，再按目录占用定位来源；关注 MemAvailable，不能把 page cache 全算泄漏。
Pi /tmp 为小 tmpfs，禁止存大镜像。控制机构建，Pi 刷机，RK 运行；避免把源代码/缓存反复同步上板。

用户已授权清理不再使用的 snapshot：逐个核对 ACTIVE、ROLLBACK、REPEAT_TEST、RECOVERY，
只删除 OBSOLETE，保留明确的删除清单、SHA-256、原因和前后资源报告。
不要仅按年龄猜测；核查引用、打开 fd、loop/挂载与刷机进程，发现占用或变化就停止该项。
历史失败证据、基础 rootfs、模型和库不视作垃圾。日志先回收校验，再处理板端副本。
不全局 pkill、不关闭服务、不刷写 SD、不修改网络来完成日常清理。

后续测试使用 `scripts/maintenance/lab-run.py`，互斥与记录边界见管理文档。
维护结束报告实际释放容量、保留项及理由、未处理占用和验证范围；不要将工具验证写成 GPU 回归通过。
