# 新机器复现与源码构建

完整流程见[无上下文 Agent 环境部署与测试手册](AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)。
该手册也记录了完整矩阵通过后，额外干净副本回归出现的 Group submit fence 超时，
请勿将本指南视为所有新环境已经稳定通过的保证。

## 1. 适用环境

本项目测试需要 RK3588 / Rock 5B、Mali GPU、匹配的 OpenCCA 固件和 Host 内核。
“新机器”可以是全新的 Linux 构建/控制机；GPU 测试仍在物理 RK3588 上执行。
仅 clone 到普通 PC 不能提供 GPU、KVM HVC 或 OpenCCA 硬件环境。

2026-10-15 普通共享测试基线：Host `6.12.0-opencca-pmthor #10`，
GPU 绑定 `pmthor`，无其他 VM 占用，Host CPU 通常在线 0–1。双 Client 测试
自动使用更多 CPU，结束后恢复。禁止并发启动多套回归。

全新板子的 SD 卡、固件、Host Image 和匹配模块准备见
`RASPBERRY_PI_FLASH_RUNBOOK.md` 与 `FROM_ZERO_REPRODUCTION.md`。需要直通对比时，
Host 必须同时有匹配当前内核的 `pmthor_drv.ko` 和 `panthor.ko`；只准备 Image
不足以完成驱动切换。用 rootfs 的 modprobe policy 默认选择 pmthor，
不要用内核命令行永久 blacklist panthor。

## 2. 控制机依赖与恢复

建议 Ubuntu 24.04 / Debian，Python ≥ 3.10，空闲磁盘至少 10 GiB；全量构建内核、
固件时预留更多空间。仓库可能较大，因为组件包含完整内核源码。

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 openssh-client \
    sshpass rsync file xz-utils
git clone https://github.com/marsha1111mao-del/gpu.git
cd gpu
./scripts/setup/bootstrap.sh
python3 scripts/check/check-checkout.py
```

bootstrap 初始化固定第一层子模块、恢复哈希固定的 ARM64 载荷并下载两个 rootfs。
不需要沿用原机器的绝对路径、SSH 私钥或 `.vscode` 配置。所有公开子模块使用
HTTPS。已有正确载荷可重复运行；若自己重建后内容不同，先备份，再决定是否
`restore-runtime.py --force` 恢复基线。`--no-rootfs` / `--no-runtime` 可分别跳过。

如需重新构建 OpenCCA：

```bash
./scripts/setup/bootstrap.sh --firmware
python3 opencca/scripts/setup/apply-local-patches.py --check
```

OpenCCA 内层上游仓库保持固定提交，必要修改以清单中的补丁保存；应用后这些内层
仓库出现 dirty 是预期现象。不要在内层仓库执行 `git reset --hard` 后直接构建。
清单检查基线和哈希，已应用的补丁不会重复应用，遇到冲突会停止。

## 3. 板端检查与全量回归

板端需要 root、SSH、`/dev/kvm`、`/dev/pmthor`、bash、tar、mount、losetup、
timeout、dmesg、taskset、modprobe、足够 rootfs 工作空间。建议安装 rsync，
脚本也提供 tar 同步兼容路径。板端 Python 3 用于部分报告与诊断。
源码编译 GLES/ML 时另需 gcc、pkg-config、libegl1-mesa-dev、libgles2-mesa-dev、
libgbm-dev 和 libdrm-dev。

```bash
export REMOTE_HOST=192.168.31.18
export REMOTE_USER=root
export REMOTE_PASS='root'  # 换成自己的板端凭据
python3 scripts/run/run-regression.py --passthrough
```

首次执行会同步运行树和 rootfs。后续确认板端文件一致时才加 `--remote-prepared`；
`--quick` 用于短回归，不能替代完整性能基线。`--passthrough` 会切换 Host GPU
驱动并进行 Host/Guest 对比。默认只运行普通共享矩阵。

| 组别 | 覆盖 |
| --- | --- |
| IOCTL | 17 项设备查询、BO、mmap、VM_BIND、syncobj/sync_file、Group/Heap |
| PFN | 32 次重复翻译、两种 device/VM 关闭顺序、EBUSY 与最终 reset/free |
| Compute | 4 / 16 / 64 / 128 MiB、结果校验、预热与测量 |
| ML | 六种算子、GEMM 512、Attention 320 |
| NCNN | 三个模型、Vulkan GPU 探针、完整网络、空权重 |
| 图形 | glmark2 720p / 1080p，null-noop，frame-end finish |
| 共享 | 两个 Client 同时提交 Compute |
| 直通（可选） | Host vs 单 VM passthrough，完成后恢复 pmthor |

每个用例在 `GPU-SFTP/log/regression/<run-id>/` 保存输出和退出码，
`summary.json` 持续更新；任何失败立即停止。单项脚本的 Guest/Proxy/Host 日志
位于 `GPU-SFTP/log/shared/` 或 `log/passthrough/`。异常中断后先检查远端残留 VM、
driver 绑定、挂载和 CPU 状态，再复测。

## 4. 从源码重建

快照用于复现已测组合，源码构建用于开发。构建后还需重新运行回归；源码在不同
工具链上的产物不承诺逐字节一致。

```bash
sudo apt-get install -y build-essential gcc-aarch64-linux-gnu \
    g++-aarch64-linux-gnu flex bison bc libssl-dev libelf-dev \
    device-tree-compiler libdrm-dev pkg-config cmake ninja-build \
    clang lld meson
./scripts/build/build-verified-kernels.sh
./scripts/build/build-panthor-ioctl-smoke.sh
./scripts/build/build-pfn-lifetime.sh
```

四种内核使用固定配置；`build-verified-kernels.sh` 要求干净源码目录并执行
out-of-tree 构建，默认 `JOBS=8`。已有 in-tree 构建环境可继续使用原来的
`build-guest-vmshm-kernels.sh` / `build-host-kernel-payload.sh`。完整 Host 模块：

```bash
INSTALL_MODULES=1 JOBS=8 ./scripts/build/build-host-kernel-payload.sh
```

Firecracker 使用仓库固定 Rust 1.83.0 和 Cargo.lock。安装 rustup 及
`aarch64-unknown-linux-musl` target，并准备真正的 aarch64 musl 交叉工具链：

```bash
rustup toolchain install 1.83.0 --profile minimal
rustup target add --toolchain 1.83.0 aarch64-unknown-linux-musl
LINKER=/path/to/aarch64-linux-musl-gcc ./scripts/build/build-firecracker-runtime.sh
```

不要把 glibc 的 `aarch64-linux-gnu-gcc` 当作 musl linker。组件使用
`cargo --locked`，Rust 依赖仓库已补全 rust-vmm-ci 的子模块映射。

GLES/ML 单项测试省略 `--skip-gles-remote-build`，就会在板端从当前 C 源码重建：

```bash
./scripts/run/run-vmshm-e2e.sh --skip-build --gles-ml-smoke
./scripts/run/run-vmshm-e2e.sh --skip-build --gles-compute-smoke
```

NCNN 和 glmark2 固定来源、定制内容及源码快照见 `GPU-SFTP/ARTIFACTS.md`。
重建这些第三方载荷后需更新对应探针、模型、依赖库和验证结果。

## 5. 实验边界

- Realm 最小 Compute 的历史成功不代表硬件机密隔离成功。RK3588/OpenCCA
  `HOST_READ_SUCCEEDED` 结果说明不能据此声称 Host 访问被硬件拒绝。
- `check-opencca-gpt-design-denial.sh` 检查设计/源码条件，不是硬件拒绝测试。
- PRIME 导出尚不支持；不能将预期失败包装成支持。
- ONNX Runtime 测试程序保留用于 CPU/后端探索，目前没有已通过的 GPU Provider
  基线。原始 Vulkan 探针是诊断工具；NCNN Vulkan 已纳入正常回归。
- SIGKILL Proxy 的故障注入及恢复记录保留于 2026-10-15 验证报告；故障工作负载
  本身预期失败，需另外检查 Host reset/PFN 回收和后续正常测试。
