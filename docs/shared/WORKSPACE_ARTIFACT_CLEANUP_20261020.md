# 工作区与板端产物清理

日期：2026-10-20。两次独占维护均退出0，清理35,360个文件、332个空目录。
本次未改运行代码，无新增GPU回归或性能测量；维护通过不等于新增GPU验收PASS。

## 实际结果

| 位置 | 删除文件 / 空目录 | 删除释放的实际分配空间 | 空间净变化 |
| --- | --- | --- | --- |
| 控制机 | 26,569 / 99 | 6.35 GiB | build从24.27降至18.72 GiB，净减5.55 GiB，已计入迁回归档及维护证据 |
| Pi | 8 / 27 | 1.00 GiB | 根分区可用增加1.00 GiB |
| RK | 8,783 / 206 | 1.76 GiB | 根分区可用增加1.75 GiB |

控制机删除已由当前Host构建树替代的编译中间文件、退役实验的Guest镜像/initrd、
探针生成中间文件和Python字节码；保留原实验源码快照、补丁、配置、哈希与结果日志。
旧Host构建树的Image、模块和配置保留，当前Host/Guest增量构建树不变。
探针构建说明已改用当前 `build/dma-guard-20261018/host`，避免继续使用旧缓存目录。
硬链接按最后一个链接实际释放的块数统计，未重复计入共享文件空间。

Pi清理8份已替代的历史kernel snapshot；RK清理52份旧部署/探针上传副本，
并将NCNN源码与编译树的8,731个文件完整迁回控制机后删除。
60份板端副本逐一匹配控制机文件或回收校验SHA；NCNN归档另逐文件校验，
共新增约0.73 GiB冷归档，位于维护证据目录的 `archived/`。
历史候选的已删除运行镜像需从保留源码/配置重建，原日志与失败事实继续可查。

## 保留与检查

当前Host #31、RMM timer v6、原冻结1171/1170包、当前安全服务包、匹配模块、
最近回退/SD分区备份、Pi完整恢复镜像、基础rootfs、模型、运行库及失败证据保留。
最新Guest设备授权/RSI/GPU backing三套复验输入保留。
NCNN运行树26个ELF的动态路径及符号链接独立检查，不依赖已迁走的源码/构建树。

364份运行源码指纹未变，Host/Guest/OpenCCA/RMM组件状态未变，20份当前/冻结/回退输入SHA复核通过。
安全服务探针保留实际调用与诊断验证用途，本轮未裁剪运行实现。
三个入口help、上游补丁清单及文档检查通过；最终资源issues为空，
无实验进程，RK仍为#31/pmthor/CPU0–1/300MHz且无loop，Pi系统swap loop保留。

## 执行与证据

以下命令均从仓库根执行，退出码均为0：

```bash
python3 scripts/maintenance/lab-run.py --run-id workspace-artifact-cleanup-20261020-a -- \\
  python3 build/lab-maintenance/cleanup-20261020/cleanup.py apply
python3 scripts/maintenance/lab-run.py --run-id workspace-artifact-cleanup-20261020-b -- \\
  python3 build/lab-maintenance/cleanup-20261020/prune-empty.py
```

完整删除清单含路径、大小、mtime、inode、SHA、原因与结果，连同归档索引、前后资源和源码指纹，
在 `build/lab-maintenance/cleanup-20261020/`；独占运行记录在 `build/lab-runs/<run-id>/`。
仓库保留[脱敏汇总](evidence/cleanup-20261020/summary.json)，不提交原始运行日志、缓存或镜像。

## Notion精简

按用户最新要求，「假设场景2实现」仅保留**已实现（必须保留）**、**未实现 / 部分实现（必须保留）**两区，
共9项已实现和5项未实现/部分实现；去除历史候选、重复结论、失败清单和逐轮测试流水。
页内由51,829字符缩减至约2,000字符，回读确认两区及14项完整；Notion列宽元数据变化不影响条目内容。
平台保护继续作为已有能力假设；软件正确性、可选扩展和发布任务分清范围。
[本地实现清单](SCENARIO2_IMPLEMENTATION_STATUS.md)同步维护，历史证据在仓库原报告保留。

统一记录：清理废弃产物并精简状态文档｜对照Host #31既有完整720p1159 → 本次未测｜
分差/百分比不适用｜未改运行代码，无新增性能测量｜上述命令、run-id、rc0及维护证据｜
保留清理结果、当前输入与历史证据，原冻结1171/1170不变。
