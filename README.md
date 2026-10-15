# RK3588 GPU Virtualization

RK3588 / OpenCCA GPU 虚拟化工作区，包含 Host `pmthor`、Guest Panthor
Client/Proxy、Firecracker、vmshm-broker、测试程序和自动化脚本。组件使用固定
Git 子模块提交，OpenCCA 上游组件的必要修改由带 SHA-256 的补丁清单恢复。

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
export REMOTE_HOST=192.168.31.18 REMOTE_USER=root
export REMOTE_PASS='root'  # 按自己的板端账号设置
python3 scripts/run/run-regression.py --passthrough
```

首次回归会同步运行载荷和 rootfs；需要保证板端空闲且磁盘空间足够。该流程会启动
VM、切换 GPU 驱动、短暂调整 CPU 在线状态。详细硬件准备、源码构建、日志和边界见
[新机器复现指南](docs/start/FRESH_CLONE.md)。

## 目录与入口

| 路径 | 用途 |
| --- | --- |
| `Linux-Host-GPU/` | Host 内核、pmthor GPU/PFN 生命周期 |
| `Linux-Guest-GPU/` | Client/Proxy 内核及 Panthor 驱动 |
| `firecracker/` | Firecracker、固定 Rust 依赖和 vmshm-broker |
| `opencca/` | RMM、固件构建和 SD 卡更新；`bootstrap.sh --firmware` 初始化 |
| `GPU-SFTP/tests/` | IOCTL、GLES Compute/ML、PFN、Vulkan 等测试源码 |
| `GPU-SFTP/runtime/` | 已验证 ARM64 载荷和 glmark 源码快照 |
| `configs/verified-20261015/` | 验证基线的四个内核配置 |
| `scripts/build/` | 源码构建 |
| `scripts/run/` | 单项测试、共享/直通性能、完整回归 |
| `scripts/check/` | checkout、日志和设计检查 |
| `scripts/deploy/` | Host 内核部署；刷写操作详见专门 runbook |

## 测试基线

截至 2026-10-15，普通 VM 共享路径的功能、GLES Compute/ML、NCNN Vulkan、
glmark2 和双 Client 结果见
[测试与 Bug 修复报告](docs/shared/PANTHOR_SHARED_GPU_FIX_VERIFICATION_20261015.md)。
`run-regression.py` 提供统一复测入口，并为每项测试保存日志和 `summary.json`。

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
