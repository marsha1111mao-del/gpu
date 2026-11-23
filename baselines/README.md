# GPU 1200 与 1170

1200 是当前开发与复验版本。1170 是板端默认回退版本。两版的源码提交和运行载荷按版本固定。

| 版本 | 固定源码 | 完整运行载荷 |
| --- | --- | --- |
| 1200 | `release/gpu-1200-20261122`，Guest `50ee7dba2b82d7e0e07f1de1251a3f1b694a7f89`，OpenCCA `b0484b33c45bbea30fb17c80cf9a8b6c53b749d4`，RMM `ba15e8ce360d0c0fb0dc6e1480a603ded3bcf115` | [1200 图形、计算、固件和配置](gpu-1200-20261122/manifest.json) |
| 1170 | `release/gpu-1170-20261114`，父仓库 `dbfd426fa198a05635bf22a52990c7e4d7b87a9f` [原验收源码哈希](gpu-1170-20261114/source-hashes.json) | [1170 图形、计算、对照和固件](gpu-1170-20261114/full-manifest.json) |

1170 的本机精确构建输入及共有依赖分别位于 `build/baselines/gpu-1170-20261114/` 和 `build/baselines/shared-rk3588-opp3/`。本机文件摘要见 [local-archive.sha256](gpu-1170-20261114/local-archive.sha256)。1200 可以从同一源码归档应用其三个补丁恢复。清理历史产物时保留两版及其匹配固件、设备树、恢复镜像和校验依据。

恢复 1200 见[版本说明](gpu-1200-20261122/README.md)。在此分支的检出目录中恢复 1170 完整载荷可执行以下命令。

```bash
manifest=baselines/gpu-1170-20261114/full-manifest.json
dest=build/baselines/gpu-1170-20261114/payload
python3 scripts/artifacts/restore-runtime.py --manifest "$manifest" --dest "$dest"
python3 scripts/artifacts/restore-runtime.py --manifest "$manifest" --dest "$dest" --check
```

部署前核对实际 Host、rootfs、Firecracker 和 SD2 固件，使用仓库[硬件执行手册](../docs/start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)规定的独占入口。
