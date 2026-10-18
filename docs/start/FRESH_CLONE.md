# 新机器复现与源码构建

完整流程见[无上下文 Agent 环境部署与测试手册](AGENT_ENVIRONMENT_AND_TEST_RUNBOOK.md)。
该手册也记录了完整矩阵通过后，额外干净副本回归出现的 Group submit fence 超时，
请勿将本指南视为所有新环境已经稳定通过的保证。

## 1. 适用环境

本项目测试需要 RK3588 / Rock 5B、Mali GPU、匹配的 OpenCCA 固件和 Host 内核。
“新机器”可以是全新的 Linux 构建/控制机；GPU 测试仍在物理 RK3588 上执行。
仅 clone 到普通 PC 不能提供 GPU、KVM HVC 或 OpenCCA 硬件环境。

当前Host、RMM、Realm冻结包及性能配置见[当前基线](../shared/CURRENT_BASELINE.md)。Host需绑定pmthor、无其他VM占用，通常CPU0–1在线；测试结束恢复。旧普通VM/memfd载荷不再是可运行路径，禁止并发启动多套回归。

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

## 3. 板端检查与Realm测试

确认SSH、/dev/kvm、/dev/pmthor、匹配的Host/RMM、Firecracker和只读Panfrost rootfs。先检查资源，再通过租约运行已冻结输入：

```bash
python3 scripts/maintenance/lab-resources.py --check --output build/preflight.json
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-realm-xshm.py --images <冻结包> \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

入口只上传冻结包中变化的内核/initrd/runner，不自动恢复Host/RMM/rootfs。优化首先以完整720p超过1000分为门槛，再运行双Client功能、IOCTL、Compute、ML及大负载；具体范围见[Realm说明](../../GPU-SFTP/tests/realm-xshm/README.md)。每项保存run-id、命令、退出码、输入哈希及日志；未选择项为NOT_RUN。旧32项普通VM矩阵和memfd脚本已删除，历史报告仅用于对照。

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
out-of-tree 构建，默认 `JOBS=8`。Client/Proxy始终合并REALM_XSHM配置；不要从旧普通VM配置单独构建。完整 Host 模块：

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

需安装构建机libclang/Clang头文件、rustfmt和libseccomp开发库；ARM64 musl目标另需交叉构建的静态libseccomp，可通过目标RUSTFLAGS的`-L native=/path/to/arm64-musl/lib`指定，不要指向Host架构库。旧aws-lc依赖要求兼容CMake策略的构建环境，记录实际工具链版本。

不要把 glibc 的 `aarch64-linux-gnu-gcc` 当作 musl linker。组件使用
`cargo --locked`，Rust 依赖仓库已补全 rust-vmm-ci 的子模块映射。

Realm完整initrd构建入口为`scripts/build/build-realm-xshm-initrd.py --help`；它打包当前测试源码对应的载荷，不使用旧memfd runner。

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
