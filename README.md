# RK3588 GPU Virtualization

RK3588 / OpenCCA GPU 虚拟化工作区，包含 Host `pmthor`、Guest Panthor
Client/Proxy、Firecracker、RMM 共享通信、测试程序和自动化脚本。组件使用固定
Git 子模块提交，OpenCCA 上游组件的必要修改由带 SHA-256 的补丁清单恢复。

完整操作入口：**[无上下文 Agent 环境部署与测试手册](docs/start/AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)**，涵盖硬件探测、Pi 准备、Host 部署、全部测试、判定标准和故障恢复。

当前开发以 **[P42 + BO 容量修复基线](docs/shared/CURRENT_BASELINE.md)** 为准：
RMM 授权共享、可信 IRQ、可复用执行计划、原生 fence 完成凭据和批量快照回收。
最新 [Native / ProxyClient 对比](docs/shared/GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)
列出完整有效结果及哪些项目仍是 P42 参考。旧实验和论文提案见
[历史与研究归档](docs/archive/20261018/README.md)。

## 新机器开始

控制机建议 Ubuntu 24.04 / Debian，Python ≥ 3.10。运行硬件测试需要已启动匹配
OpenCCA Host 内核的 RK3588，普通 x86 机器负责构建和远程控制。

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 openssh-client \
    sshpass rsync file xz-utils
git clone https://github.com/marsha1111mao-del/gpu.git
cd gpu
./scripts/setup/bootstrap.sh
python3 scripts/check/check-checkout.py
```

bootstrap恢复的是manifest固定载荷；当前RMM-only Realm内核/initrd/VMM已单独打包，Host/RMM仍须按当前基线另行匹配，不会自动升级板端固件。
现有健康板端按当前基线核对冻结包与固件，再使用
`lab-run.py --run-id <唯一ID> -- python3 scripts/run/run-realm-xshm.py ...`。
测试会启动 VM、临时调整硬件状态，须先确认空闲与资源。
详细硬件准备、源码构建、日志和边界见
[新机器复现指南](docs/start/FRESH_CLONE.md)。

## 目录与入口

| 路径 | 用途 |
| --- | --- |
| `Linux-Host-GPU/` | Host 内核、pmthor GPU/PFN 生命周期 |
| `Linux-Guest-GPU/` | Client/Proxy 内核及 Panthor 驱动 |
| `firecracker/` | Firecracker、固定 Rust 依赖 |
| `opencca/` | RMM、固件构建和 SD 卡更新；`bootstrap.sh --firmware` 初始化 |
| `GPU-SFTP/tests/` | IOCTL、GLES Compute/ML、PFN、Vulkan 等测试源码 |
| `GPU-SFTP/runtime/` | 已验证 ARM64 载荷和 glmark 源码快照 |
| `configs/verified-20261015/` | 验证基线的四个内核配置 |
| `configs/performance/` | 当前 Realm 构建与性能配置 |
| `scripts/build/` | 源码构建 |
| `scripts/run/` | Realm 专项测试及 Host/直通性能 |
| `scripts/check/` | checkout、日志和设计检查 |
| `scripts/deploy/` | Host 内核部署；刷写操作详见专门 runbook |
| `docs/shared/` | 当前基线、最新性能和 BO 修复报告 |
| `docs/archive/` | 历史实现、逐轮实验、失败记录与研究提案 |

## 历史发布基线

截至 2026-10-15，普通 VM 共享路径的功能、GLES Compute/ML、NCNN Vulkan、
glmark2 和双 Client 结果见
[测试与 Bug 修复报告](docs/archive/20261018/history/PANTHOR_SHARED_GPU_FIX_VERIFICATION_20261015.md)。
旧普通 VM/memfd 代码和矩阵入口已退役，仅保留历史报告；当前使用 Realm runner。
完整发布回归曾 32/32 通过；随后干净副本短回归出现 Group submit fence 等待超时，
尚未定位。两次结果及边界见[仓库整理与验证记录](docs/archive/20261018/history/GPU_REPOSITORY_PUBLICATION_20261015.md)。

NCNN 使用随机输入和空权重，仅验证 Vulkan 执行与性能；glmark 使用
`null-noop`、`--frame-end finish`，没有显示器呈现性能含义。Realm 与 Host 访问
探针、PRIME、ONNX Runtime 等实验的证据边界见复现指南。

## 载荷与源码

为使 clone 后能重现已验证组合，本仓库固定保存一份压缩运行载荷；恢复程序同时
校验归档与每个文件的哈希。rootfs 继续使用固定 GitHub Release，下载后校验
大小和哈希。编译缓存、临时 Mesa/NCNN、失败实验二进制和日志不进入 Git。
参见 [载荷清单与来源](GPU-SFTP/ARTIFACTS.md)。

修改组件后，先提交并推送组件，再更新本仓库的子模块指针。OpenCCA 上游补丁
必须同步更新 `opencca/patches/manifest.json`。
