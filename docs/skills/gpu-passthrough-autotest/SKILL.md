---
name: gpu-passthrough-autotest
description: 在 RK3588/OpenCCA 上运行和诊断单 VM GPU 直通，以及 Host 原生与直通性能对比、驱动恢复和结果汇总。
---

# GPU 直通与原生性能对比

## 执行入口与实验室默认值

先读 [环境与测试主手册](../../start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md) 和
[开发与产物管理](../../start/DEVELOPMENT_AND_ARTIFACT_HYGIENE.md)，再读将执行的脚本。
命令从仓库根目录执行（`git rev-parse --show-toplevel`）；不依赖旧的绝对工作区路径。

实验室地址：RK `root@192.168.31.18`，Pi `mzh@192.168.31.189`；
`.52` 是同一 Pi 的无线备用地址。仓库副本不保存密码，先按主手册交互读取凭据并导出环境变量。
本机私有 skill 可保留用户指定的实验室配置，不将凭据同步到 Git：

```bash
export REMOTE_HOST="${REMOTE_HOST:-192.168.31.18}"
export REMOTE_USER="${REMOTE_USER:-root}"
export REMOTE_PASS="${REMOTE_PASS:?先按主手册设置凭据环境变量}"
export OPENCCA_RPI_HOST="${OPENCCA_RPI_HOST:-mzh@192.168.31.189}"
export OPENCCA_RPI_PASSWORD="${OPENCCA_RPI_PASSWORD:?先按主手册设置凭据环境变量}"
export OPENCCA_RPI_SUDO_PASSWORD="${OPENCCA_RPI_SUDO_PASSWORD:?先按主手册设置凭据环境变量}"
export OPENCCA_RK_HOST="${OPENCCA_RK_HOST:-root@192.168.31.18}"
export OPENCCA_RK_PASSWORD="${OPENCCA_RK_PASSWORD:?先按主手册设置凭据环境变量}"
```

所有测试通过 `python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- <测试命令>`
执行；不要嵌套 wrapper。首次部署前运行 `lab-resources.py --check` 检查 Pi 与 RK。
资源门槛、独占锁边界、选择性同步、snapshot 保留/清理和逐项证据要求统一见开发与产物管理文档。

## 直通路径与命令

本 skill 用于单 VM 直通；Proxy/Client 共享使用共享测试 skill。
Host 原生阶段可能切换 `pmthor` 到 `panthor`，VM 阶段按 runner 管理，退出后确认恢复 `pmthor`。
Image、initrd 和模块必须匹配 kernelrelease。不要设置阻断手动加载的内核 `module_blacklist=panthor,pmthor`。

```bash
python3 scripts/maintenance/lab-run.py --run-id "passthrough-perf-$(date +%Y%m%d-%H%M%S)" -- \
  bash scripts/run/run-host-vs-passthrough-gles-perf.sh \
    --host-rootfs-userspace --skip-sync --skip-remote-build \
    --count 8388608 --iterations 20 --warmup 5 --vm-timeout 900 --host-timeout 900
```

`--skip-sync` 仅限已同步相符载荷；`--skip-remote-build` 仅限已有相符的 ARM64 测试二进制。
首次准备或变更时按主手册构建与同步。比较口径遵从当前脚本，不能沿用旧版历史比值。
Host 和 VM 两边均需 correctness PASS、真实 Mali/Panfrost renderer、无 GPU fault/timeout/OOM；
最后检查 driver、CPU 在线集合、进程和挂载恢复。详细命令、日志目录及性能参数查主手册与 runner。
