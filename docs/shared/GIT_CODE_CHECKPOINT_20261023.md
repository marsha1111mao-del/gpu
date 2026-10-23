# 2026-10-23 ProxyClient 源码基线发布记录

本次按“组件先推送、父仓库再更新指针”的顺序，将无收益实验路径清理后的正式ProxyClient设计固定为当前GitHub源码基线。不改写历史，不提交镜像、原始运行日志、凭据或编译缓存。

## 发布版本

| 仓库 | 提交 | 本次状态 |
| --- | --- | --- |
| `Linux-Guest-GPU` | `39d95dd028d485ca837bf1b3c5123db2eefbaa75` | 已推送并核对远端`main`；保留默认关闭的提交阶段与完成回传诊断 |
| `Linux-Host-GPU` | `64510307c4ae432447d60a0e3735616dbce4e310` | 未改动 |
| `opencca/tf-rmm` | `15c7ee14af5deacda757342c169fd98722f58f90` | 未改动 |
| `opencca` | `8014f360db0c7d4912a6e0cd4f5c5ee18e586435` | 未改动，继续固定上述RMM提交 |
| `firecracker/Firecracker-CCA-MZH` | `349436426b2f8264f6010f28944dcb388137b4e4` | 未改动 |
| 主仓库 `gpu` | 本记录所在提交 | 固定组件指针、runner、分析工具、文档与配图 |

## 当前设计边界

- 正式提交协议只保留`PLAN_REGISTER/PLAN_EXEC`；安全校验、真实Panthor提交、完整fence完成cookie和TRANSFER预捕获保持不变。
- 删除计划缓存A/B专用的`plan_cache=0`、`UNCACHED_SUBMIT`及控制结构分配账本；撤回无稳定收益的`SUBMIT_CAPTURE`融合和Proxy接收侧8微秒轮询。
- RPC、通知和完成回传计时均默认关闭，不由`--performance`自动开启；诊断代码不作为性能优化计入基线。
- 父仓库新增或更新完成回传、通知延迟、提交阶段、内存和动态频率分析工具及报告；历史失败与未执行项继续保留。

## 构建与硬件验收

Client/Proxy ARM64完整Image增量构建均退出0：

```bash
make -C Linux-Guest-GPU O=build/verified-kernels/client ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=build/verified-kernels/firmware -j8 Image
make -C Linux-Guest-GPU O=build/verified-kernels/proxy ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- CONFIG_EXTRA_FIRMWARE_DIR=build/verified-kernels/firmware -j8 Image
```

| 输入 | SHA-256 |
| --- | --- |
| Client Image | `8e336f099408d90e178b64fab84fd4a115bd1d8b8b6316b55e2387246230a564` |
| Proxy Image | `ea4714ecadf358e6ea794a5bc9c48001ac631cb03a738b7468f50dbd80ecfa27` |
| initrd | `903465ce6f7ca4290aed6f979c7501606ff6729c03656b9e48de4de1f343f0f3` |
| runner | `08880f70f8325e4178efba61e0316fad893aad793961f632185e9b7493b83a4a` |

改动目的｜清理无收益实验路径并固定正式设计｜历史同条件完整720p 1156 → 本版1160｜+4/+0.35%｜单Client、33场景、CPU固定1.8GHz、GPU请求600MHz/实际594MHz、128MiB紧凑池、round-robin、TRANSFER预捕获开启、RPC/通知/完成诊断关闭；不同日期且各单轮，不宣称稳定提分｜run-id `clientproxy-cleanup-720-20261023-b`、外层rc0、本地证据`build/lab-runs/clientproxy-cleanup-720-20261023-b/`｜保留为当前源码基线。

该轮runner状态PASS，validation为26/1/6，两个VM退出0；Host内核健康、GPU/DMA租约最终归零且普通输入恢复通过。准备轮`clientproxy-cleanup-720-20261023-a`使用旧runner，因仍要求已删除的A/B参数而在glmark前失败；无分数，不计为第二轮有效测试，失败证据保留。

## 未执行与限制

- 本次没有重跑1080p、API、计算、多Client、ML/NCNN或完整安全回归，旧PASS不能自动覆盖新提交。
- 新源码不更新旧runtime manifest；忽略目录中的候选Image和运行证据用于本机复现，不进入Git。
- 当前硬件继续承担行为模拟；真实平台的页表、关键配置和设备保护能力仍是部署前提，而不是本模拟工程新增的待实现硬件任务。
