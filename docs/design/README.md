# GPU 虚拟化设计与实验

本项目在 RK3588 的 OpenCCA Realm 上运行 Mali-G610。发布基线用一个 Proxy Realm 服务一个或多个 Client Realm，由 RMM 管理私有 GPU 内存、任务授权和可信完成。验收为单 Client 完整 720p glmark2 1170 分。[发布与复验入口](../shared/CURRENT_BASELINE.md)

| 阅读主题 | 涵盖内容 |
| --- | --- |
| [设计演进](01-design-evolution.md) | 从直通、普通 VM Proxy/Client 到 Realm 私有 BO，解释信任边界迁移 |
| [端到端实现](02-implementation.md) | 从 DRM ioctl、对象和任务授权到设备完成、fence、故障和回收 |
| [安全与证据](03-security.md) | 每层职责、软件与实体测试的覆盖范围、仍未解决的反例 |
| [性能优化](04-optimization.md) | 等待、提交、完成、内存热点，保留与撤回的方案 |
| [实验结果](05-results.md) | 1170 发布验收、多 Client、真实模型、直通及 virtio 对照 |

开发记录采用“改动目的｜对照版本与分数 → 本版分数｜分差及百分比｜条件差异｜run-id、命令、退出码与日志｜保留、撤回或待验证”。多项同时改变时记录组合效果。Git 仓库存放结果摘要与载荷清单。正文中的历史 run-id 和日志路径可在控制机查原始证据。
