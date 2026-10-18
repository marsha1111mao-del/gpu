# 工作区整理与基线固化（2026-10-18）

目的：将当前设计与已验证载荷作为开发入口，清除被替代的诊断代码和源码目录产物，避免历史设计被误读成当前实现要求。

## 实际变更

| 范围 | 处理 |
| --- | --- |
| 当前设计 | 新建[当前基线](CURRENT_BASELINE.md)，集中记录已实现机制、源码入口、资源档位、冻结输入与能力边界 |
| 当前结果 | 保留[统一性能报告](GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)与[BO修复报告](GPU_BO_CAPACITY_FIX_20261018.md)作为最新结果入口 |
| 历史文档 | 将27份文档移至[归档](../archive/20261018/README.md)：20份历史记录、7份研究/提案，修正引用并增加历史标记 |
| 过时说明 | 重写Realm工具和性能配置说明，去掉旧候选流水账，修正单池256→512 MiB上限、ACK_ARM能力和大负载用法 |
| 默认入口 | README、AGENTS、主手册和shared skill链接指向当前基线；旧普通VM矩阵标为历史对照 |
| 废弃代码 | 移除`GPU-SFTP/tests/pmthor-fixed-opp/`中的旧固定OPP模块源码/Makefile/说明及生成文件；正式Host devfreq已替代它，当前脚本/配置无调用者 |
| 可再生缓存 | 清除`scripts/`、`GPU-SFTP/tests/`内Python字节码缓存 |

删除共28个文件，合计475691字节（约465 KiB）；其中固定OPP目录18个文件、Python缓存10个文件。没有以“旧”作为删除源码的唯一依据。历史OPP源码小归档位于本机`build/workspace-cleanup-20261018/retired-fixed-opp-source.tar.gz`，仅用于核对当时SHA，不是当前构建输入。

文档迁移不重复复制原始日志和镜像；保留失败、未执行项目和逐轮分数。仍有实际用途的普通VM、Native、直通比较脚本及固定发布载荷保留；内核构建缓存保留以免后续重建成本增加。Pi/RK未被操作，未部署或刷写。

## 验证与性能影响

- 当前60项运行源码整理前后SHA一致；已测client/proxy Image、initrd、runner四项冻结载荷SHA一致。见[基线清单](evidence/current-baseline-20261018/source-hashes.json)。
- Markdown本地链接检查、工具Python语法解析、shell入口语法检查和`git diff --check`通过；这是离线整理检查，不是GPU回归。
- 删除前核对固定OPP模块无当前构建/runner调用者、无可见进程打开该目录；没有修改Host正式devfreq实现。
- `python3 opencca/scripts/setup/apply-local-patches.py --check`退出1：`opencca-build: changes differ from the published patch`。该组件已有本地改动，未在本轮更改或重置；完整清单检查未通过，不能宣称工作树等同固定发布补丁。下一次从零恢复前需审查并固化这些既有差异。

**未改运行代码，无新增性能测量。** 720p最新有效成绩仍为1161；已测BO修复前1154→1161（+7 / +0.61%）来自前一轮，不能算作本轮目录整理收益。GPU完整回归本轮NOT_RUN。

[逐文件迁移/删除清单](evidence/current-baseline-20261018/cleanup.json)记录原路径、归档路径、删除前SHA、大小、时间和原因；完整本地审计位于`build/workspace-cleanup-20261018/audit.json`。
