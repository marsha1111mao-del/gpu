# 运行载荷、源码和复现策略

## 固定运行载荷

`runtime-manifest.json` 固定 2026-10-15 验证组合的归档大小、SHA-256 和归档内
每个文件的大小/哈希。`scripts/artifacts/restore-runtime.py` 先验证完整清单，
再恢复到本目录；重复执行幂等，默认拒绝覆盖内容不同的本地文件。

```bash
python3 scripts/artifacts/restore-runtime.py          # 在仓库根目录执行
python3 scripts/artifacts/restore-runtime.py --check
# 确认已备份自行构建的载荷后才使用 --force
```

| 归档 | 内容 / 来源 |
| --- | --- |
| `runtime/arm64-userspace-20261015.tar.gz` | 已验证 Firecracker、broker、测试程序、NCNN Vulkan 及 glmark2 null-noop 用户态 |
| `runtime/arm64-host-20261015.tar.gz` | 已验证 Host #10 pmthor Image |
| `runtime/arm64-client-20261015.tar.gz` | 已验证共享 Client Image |
| `runtime/arm64-proxy-20261015.tar.gz` | 已验证共享 Proxy Image |
| `runtime/arm64-passthrough-20261015.tar.gz` | 2026-07-18 验证的直通 Guest Image |
| `runtime/ncnn-source-20260526.tar.gz` | 板端实际构建使用的 NCNN 源码，含 glslang 和许可证 |
| `runtime/glmark2-null-noop-source.tar.gz` | 板端 glmark2 定制源码，包含许可证；不安装到运行目录 |

这是明确版本的复现快照。新构建载荷可以替换运行目录中的文件；不要把不同
内核/固件/用户态混用后的结果归到此基线。单个内核压缩包均小于 50 MiB。
归档固定保存于 Git，替代依赖旧机器私有目录的临时缓存。更新时需一并更新清单、
来源及回归报告，避免堆积多套历史二进制。

## 第三方来源

- Firecracker、vmshm-broker、Host/Guest 内核、RMM 源码固定在各子模块，
  保留各自 LICENSE。内核配置在 `configs/verified-20261015/`。
- glmark2 基线为上游提交 `22c527cb0556f3a1ac4445aaa52cc532760928d5`，
  `GLStateEGL::swap()` 在 null 模式下跳过无 surface 的 `eglSwapBuffers()`。
  使用归档中的源码和 COPYING；运行时明确设置 `--frame-end finish`。
  载荷内旧 `BUILD.txt` 中 `frame-end none` 是早期调试说明，最终验证采用 finish。
- NCNN 为上游 `20260526` / `e54f7b1f88434e1d844ea0551b880a1cfb079ce1`，
  CMake 启用 `NCNN_VULKAN=ON`。只保留 mobilenet_v2、mobilenet_v3、resnet50
  三个完整 param；`benchncnn` 使用空权重模式。对应源码快照和 `runtime/licenses/NCNN-LICENSE.txt` 保留 BSD 许可证。
- glmark 的运行依赖保留在对应 `rootfs-null-noop/usr/lib/`。Mesa/Vulkan 驱动
  由固定的 Panfrost rootfs 提供；NCNN 载荷包含其构建使用的 Vulkan 依赖。
- `panthor_fw/mali_csffw.bin` 为已有 Mali CSF 固件输入，源路径继续保留。

`runtime/licenses/debian/` 同时保留所带动态依赖的 Debian copyright 文件。
源码归档哈希见 `runtime-manifest.json` 的 `source_archives`。

## rootfs

`rootfs-manifest.json` 固定 `rootfs-20260603` Release 的两个 rootfs，合计约
1.75 GiB。`scripts/artifacts/fetch-rootfs.sh` 校验文件大小与 SHA-256，已有正确
文件不会重复下载。不需要 GitHub 账号；需要能访问公开 Release 下载服务。

`--sync-rootfs` 会将本地固定镜像同步到板端。运行脚本会从基础镜像制作测试副本、
注入载荷，不应依赖旧机器曾手工修改过的副本。

## 源码构建入口

| 目标 | 仓库根目录命令 |
| --- | --- |
| 四种内核 Image | `./scripts/build/build-verified-kernels.sh` |
| Firecracker/broker/client-test | `./scripts/build/build-firecracker-runtime.sh` |
| IOCTL 测试 | `./scripts/build/build-panthor-ioctl-smoke.sh` |
| PFN 生命周期 | `./scripts/build/build-pfn-lifetime.sh` |
| GPA/RPC 辅助探针 | `./scripts/build/build-vmshm-lookup-probe.sh`、`build-vmshm-raw-rpc-probe.sh` |
| GLES Compute/ML | 单项共享脚本省略 `--skip-gles-remote-build`，在 ARM64 板端从源码编译 |
| Host Image/模块 | `INSTALL_MODULES=1 ./scripts/build/build-host-kernel-payload.sh` |
| Realm Host 探针模块 | `./scripts/build/build-realm-host-access-probe.sh` |

完整依赖和设备准备见 `docs/start/FRESH_CLONE.md`。

## 不提交的文件

`firecracker-bins/bin/`、`kernels/`、rootfs、Host Image/模块 staging 均为恢复或
构建目标；`artifacts/{gdb-arm64,mesa-vulkan-arm64,ncnn-arm64,glmark2-arm64}` 为解包
目录；临时实验、core、生成配置和运行日志被忽略。只在 `runtime/` 保留一份固定
载荷，不提交整个下载缓存。日志默认位于 `GPU-SFTP/log/`。
