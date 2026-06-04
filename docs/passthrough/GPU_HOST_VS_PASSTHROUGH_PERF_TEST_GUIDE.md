# 远程 Host 与 GPU Passthrough VM 性能测试规范

本文档用于规范远程 GPU 服务器上的 Host direct 与 GPU passthrough VM 对比测试。正式结果只使用一张 Host/VM ratio 表表示，不再输出或要求旧的多张 overhead、phase share、historical baseline 分析表。

目标不是做完整图形 benchmark，而是用同一个 `gles-compute-smoke` OpenGL ES compute workload 比较两条路径：

1. Host 临时加载真实 `panthor` DRM driver，直接运行 GPU 任务。
2. Firecracker VM 通过 passthrough GPU 和 guest `panthor` driver 运行同一 GPU 任务。

正式性能结论只看 GPU task 稳态循环内的阶段均值。正确性检查只作为 PASS/FAIL sanity check，不计算耗时，也不参与性能指标。

当前正式口径还会使用 `--exclude-cpu-prepare` 排除每轮 `input[]` CPU 填充时间。这样 `PERF_ITER_US` / `iter_total` 只覆盖 CPU 填充完成之后的 buffer upload、submit、completion 和 unmap，避免把普通 CPU 写内存吞吐混入 GPU 虚拟化路径对比。

## 测试原则

正式性能 run 禁止使用会改变时序的 tracing wrapper：

- `strace`
- `ftrace`
- `bpftrace`
- `perf record`
- 其他会拦截 syscall、tracepoint、kprobe 或高频采样的调试工具

当前计时由 `GPU-SFTP/tests/gpu-compute-smoke/gles_compute_smoke.c` 内部通过 `clock_gettime(CLOCK_MONOTONIC)` 采集。它不是硬件 GPU timestamp，但不会像 tracing wrapper 那样改变 Mesa/DRM ioctl 路径。

正式性能 run 也不应打开内核诊断统计开关，例如：

- `--guest-panthor-pt-timing`
- `--pmthor-irq-stats`
- `--guest-panthor-irq-stats`
- `--guest-panthor-submit-stats`
- `--vm-huge-pages-2m`
- `--vm-taskset-cpu`
- `--pmthor-irq-affinity-cpu`

这些开关只用于定位问题。诊断 run 的数据可以辅助解释，但不能和正式 Host/VM baseline 混为同一组结果。

正式 run 前应确认 host/guest 热路径没有高频 `printk/pr_info/dev_info`，尤其是 IRQ、EOI、irqfd/resample、ACK notifier、submit、fence completion 和 page-table map 路径。历史测试已经证明热路径日志会把 completion/IRQ 路径拉到毫秒级，严重污染结果。

## 环境

固定远程环境：

```text
Remote SSH target: root@192.168.137.10
Remote password: root
Local artifact root: /home/mzh/gpu/GPU-SFTP
Remote artifact root: /root/GPU-SFTP
Local run logs: /home/mzh/gpu/GPU-SFTP/log/passthrough/perf
Remote run logs: /root/GPU-SFTP/log/passthrough/perf
```

GPU passthrough VM 使用：

```text
VM launcher: GPU-SFTP/firecracker-bins/scripts/passthrough/run-gpu-panfrost-vm.sh
VM config: GPU-SFTP/firecracker-bins/configs/passthrough/gpu-panfrost-vm-config.json
VM rootfs: /root/GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost.ext4
Canonical guest Image: /root/GPU-SFTP/firecracker-bins/kernels/passthrough/Image
```

`gpu-panfrost-vm-config.json` 必须指向 canonical guest Image，不能指向 `Image.bak-*`、旧日期内核或临时备份文件。脚本会在 `preflight.txt` 记录 host `uname`、VM kernel image 的 `Linux version`、active VM config 和当前 host GPU driver。

如果只修改 GPU passthrough guest kernel 代码，例如 guest `panthor`、guest io-pgtable 或 passthrough page-table 逻辑，不需要构建 vmshm client/proxy 两套 role kernel。使用单内核构建脚本：

```bash
cd /home/mzh/gpu
./scripts/build/build-guest-passthrough-kernel.sh
```

该脚本只构建普通 Panthor guest `Image`，并安装到：

```text
/home/mzh/gpu/GPU-SFTP/firecracker-bins/kernels/passthrough/Image
```

host kernel 修改后通常只需要替换 host `Image` 并重启。完整 module staging/sync 很慢，只有 `.ko` 内容、模块依赖、模块安装路径或模块配置确实变化时才需要执行。

推荐 host Image-only 快速部署：

```bash
cd /home/mzh/gpu
./scripts/deploy/deploy-host-kernel-and-test.sh \
  --skip-firecracker-build \
  --skip-tests \
  --run-id-prefix gpu-perf-host-kernel-fast
```

如果只改了少量 host module，例如 host direct `panthor.ko`，优先用 selected-module 快路径：

```bash
cd /home/mzh/gpu
./scripts/deploy/deploy-host-kernel-and-test.sh \
  --skip-firecracker-build \
  --skip-tests \
  --host-modules drivers/gpu/drm/panthor/panthor.ko \
  --run-id-prefix gpu-perf-host-kernel-panthor-module
```

只有确实需要全量 modules 时才使用 `--install-host-modules`。

## Workload

测试程序：

```text
GPU-SFTP/tests/gpu-compute-smoke/gles_compute_smoke.c
```

它通过 GBM/EGL 创建 OpenGL ES 3.1 context，编译 compute shader，对 SSBO 中每个 `uint32_t` 执行默认公式：

```text
value = value * 3 + 7
```

正式 workload 使用默认 `--alu-iters 1`。`--alu-iters N` 会改变 shader 指令形态和 completion 行为，只能作为单独诊断 workload。

默认 sweep：

```text
--perf --exclude-cpu-prepare --iterations 100 --warmup 5 --count-sweep 1048576,4194304,16777216
```

规模和轮次：

| Workload | `count` | measured iterations | warmup |
| ---: | ---: | ---: | ---: |
| 4 MiB | 1048576 | 100 | 5 |
| 16 MiB | 4194304 | 100 | 5 |
| 64 MiB | 16777216 | 20 | 5 |

`64 MiB` 单轮耗时较长，因此默认通过 `--large-count-iterations 20 --large-count-warmup 5` 覆盖全局轮次。比较不同 run 时必须保持 workload、iterations、warmup、rootfs userspace 和诊断开关一致。

## 计时阶段

程序输出每轮 GPU task 的 phase：

```text
PERF_CPU_PREPARE_EXCLUDED=1
PERF_PHASE_US name=cpu_prepare samples=N min=... avg=... max=... total=...
PERF_PHASE_US name=buffer_upload samples=N min=... avg=... max=... total=...
PERF_PHASE_US name=dispatch_call samples=N min=... avg=... max=... total=...
PERF_PHASE_US name=memory_barrier samples=N min=... avg=... max=... total=...
PERF_PHASE_US name=map_wait samples=N min=... avg=... max=... total=...
PERF_PHASE_US name=unmap samples=N min=... avg=... max=... total=...
PERF_PHASE_US name=iter_total samples=N min=... avg=... max=... total=...
COMPUTE_CHECK=PASS count=... samples=...
```

`cpu_prepare` 仍然会作为独立 phase 输出，用来观察 CPU input 填充是否异常；但在正式 `--exclude-cpu-prepare` run 中，它不再计入 `PERF_ITER_US`、`PERF_PHASE_US name=iter_total` 或正式表的 `metadata` 分组。

正式表使用五个 Host/VM ratio：

| 指标 | Host/VM ratio 定义 | 含义 |
| --- | --- | --- |
| `total` | `host(iter_total_without_cpu_prepare) / vm(iter_total_without_cpu_prepare)` | 排除 CPU input 填充后的 GPU task 稳态每轮性能比例。 |
| `metadata` | `host(buffer_upload) / vm(buffer_upload)` | 用户态数据上传和底层 BO/metadata 准备路径；不再包含 CPU input 填充。 |
| `submit` | `host(dispatch_call) / vm(dispatch_call)` | CPU 侧提交 API 调用路径。 |
| `completion` | `host(memory_barrier + map_wait) / vm(memory_barrier + map_wait)` | 提交后等待 GPU 完成并可读回的同步路径。 |
| `map_unmap` | `host(unmap) / vm(unmap)` | map 返回后的尾部 unmap 成本。 |

`host/vm = Host 耗时 / VM 耗时`。值越接近 `1.000`，VM passthrough 越接近 host direct。VM 比 host 慢时该值小于 `1.000`。正式结果不再报告反向开销、性能百分比或绝对耗时差。

## 阶段占比

阶段占总时间比例用于判断各阶段对整体性能的权重。因为 `--exclude-cpu-prepare` 改变了 `iter_total` 和 `metadata` 的定义，脚本现在在每次 run 中重新计算 Host phase share，而不是继续使用旧的固定参考值。

正式表最后一列为：

```text
Host phase share = metadata / submit / completion / map_unmap
```

其中 `metadata=buffer_upload`。这列是本次 Host direct run 的阶段权重，不是 host/vm ratio。

## 正式测试命令

默认正式命令：

```bash
cd /home/mzh/gpu
RUN_ID=gpu-perf-host-vs-passthrough-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900
```

`--host-rootfs-userspace` 会让 host direct 阶段临时 mount VM rootfs，并在 chroot 中使用与 VM 相同的 Mesa/Panfrost userspace 运行 workload。这样能减少 host/VM userspace 版本差异带来的归因噪声。测试结束后脚本会 unmount rootfs 并恢复 host GPU 到 `pmthor`。

如果远端 binary 和 rootfs 已确认最新，可以跳过重复准备：

```bash
RUN_ID=gpu-perf-host-vs-passthrough-fast-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --skip-sync \
  --skip-remote-build \
  --skip-rootfs-update \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900
```

只有确认 VM rootfs 中已有正确 `/root/gpu-smoke.env` 和支持 `--exclude-cpu-prepare` 的新 `/root/gles-compute-smoke` 时，才使用 `--skip-rootfs-update`。启用新口径时，result 会要求 VM 与 host 日志都包含 `PERF_CPU_PREPARE_EXCLUDED=1`。

## 正式结果格式

`result` 的正式性能部分只看一张表：

```text
== Formal Host/VM performance ratio table ==
| **Workload** | **iter** | **total** | **metadata** | **submit** | **completion** | **map_unmap** | **Host phase share** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 100 | ... | ... | ... | ... | ... | .../.../.../... |
| 16 MiB | 100 | ... | ... | ... | ... | ... | .../.../.../... |
| 64 MiB | 20 | ... | ... | ... | ... | ... | .../.../.../... |
```

正式报告只需要包含：

- run ID
- 本地日志路径
- `RESULT: PASS/FAIL`
- VM/Host renderer 和 GL version
- `Restored GPU driver: pmthor`
- 上面这一张 Host/VM ratio 表
- 明确说明是否打开了任何诊断开关；正式 baseline 应全部关闭

不要在正式报告里额外补充多张性能表。诊断数据可以留在对应 summary/log 中，需要定位问题时再单独读取。

历史脚本格式验证 run：

```text
Run ID: gpu-perf-ratio-table-20260603-154030
Local log dir: /home/mzh/gpu/GPU-SFTP/log/passthrough/perf/gpu-perf-ratio-table-20260603-154030
Host userspace: vm-rootfs
Tracing: disabled
Diagnostic stats: disabled
RESULT: PASS
```

该 run 发生在 `--exclude-cpu-prepare` 引入之前，表里的 `metadata` 仍是旧定义 `cpu_prepare + buffer_upload`，最后一列也是旧的固定 `Host phase share ref`。它只保留为脚本格式演进记录，不能与当前正式 baseline 直接混用。

| **Workload** | **iter** | **total** | **metadata** | **submit** | **completion** | **map_unmap** | **Host phase share ref** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4 MiB | 100 | 0.779 | 0.847 | 1.109 | 0.485 | 0.723 | 79.0/6.7/14.4/0.07 |
| 16 MiB | 100 | 0.792 | 0.843 | 0.856 | 0.590 | 0.714 | 81.0/2.0/16.3/0.02 |
| 64 MiB | 20 | 0.882 | 0.865 | 0.694 | 0.971 | 0.923 | 80.0/0.75/19.3/0.01 |

这张表只表示本次验证 run 的结果格式和当次性能。后续优化比较时，以新的正式 run 表为准，不要把历史多表结果继续混入判断。

## 日志结构

每次 run 的本地日志目录：

```text
/home/mzh/gpu/GPU-SFTP/log/passthrough/perf/${RUN_ID}/
```

关键文件：

| 文件 | 内容 |
| --- | --- |
| `result` | 正式 Host/VM ratio 表、renderer/version、driver restore 状态和 PASS/FAIL。 |
| `preflight.txt` | host kernel、VM config、rootfs、GPU driver、blacklist 等前置信息。 |
| `vm-count${COUNT}.log` | 对应 workload 的 VM console 输出。 |
| `vm-count${COUNT}-summary.txt` | 对应 workload 的 VM renderer、compute check、perf phase 摘要。 |
| `host-count${COUNT}.log` | 对应 workload 的 host direct 输出。 |
| `host-count${COUNT}-summary.txt` | 对应 workload 的 host renderer、compute check、perf phase 摘要。 |
| `sweep-files.txt` | 每个 count 对应的 VM/Host summary 文件路径。 |
| `restore-status.txt` | 测试结束后的 host GPU driver 状态。 |
| `host-switch.log` / `restore.log` | host GPU 在 `pmthor` 和 `panthor` 间切换与恢复的日志。 |
| `vm-count${COUNT}-interrupts-before/after.txt` | VM workload 前后的 host interrupt snapshot；诊断 IRQ 密度时使用。 |
| `vm-count${COUNT}-dmesg-before/after.txt` | VM workload 前后的 host dmesg snapshot。 |

诊断开关可能额外生成：

| 文件 | 触发条件 | 内容 |
| --- | --- | --- |
| `pmthor-irq-stats.log` | `--pmthor-irq-stats` | host `pmthor` IRQ stats 参数启用/恢复记录。 |
| `hugepages.log` | `--vm-huge-pages-2m` | hugepage 申请、可用数量和恢复记录。 |
| `affinity.log` | affinity 诊断 | `pmthor` IRQ affinity 和 Firecracker `taskset` 包装记录。 |

诊断日志不进入正式性能表。需要定位具体问题时，可以按需读取 summary、dmesg 或 stats log。

## 优化记录规范

`GPU_PASSTHROUGH_OPTIMIZATION_LOG.md` 是清零后的轻量优化日志，只记录重要优化和测试结论。一次比较重要的优化、回退、正式复测或能改变后续判断的诊断结束后，必须追加一个自增编号条目。

记录规则：

- 编号使用 `OPT-001`、`OPT-002`、`OPT-003`，按文件中已有最大编号递增。
- 每个条目只写一个小节，优化内容、测试结果和结论放在一起，不再拆成两个部分。
- 内容保持精炼：变更、动机、run ID、正式/诊断开关、结果表、采用或不采用结论。
- 正式 Host/VM sweep 使用本文档的 8 列 `Formal Host/VM performance ratio table`。
- VM-only 诊断可以不写正式表，但必须写清楚诊断开关、关键统计和为什么它不能替代 baseline。
- 如果确认某个方向不适合作为默认优化，除了写入本日志，还要把稳定反例补充进 `GPU_PASSTHROUGH_EFFECTIVE_OPTIMIZATIONS.md` 的失败方向黑名单。

条目格式：

```markdown
## OPT-001 - YYYY-MM-DD - 简短标题

- 变更：一句话说明改了什么。
- 动机：一句话说明要解决哪个阶段或哪类开销。
- 测试：`RUN_ID`，正式/诊断开关，是否 Host/VM sweep。
- 结果：正式 run 贴 8 列 Host/VM ratio 表；诊断 run 写关键统计。
- 结论：采用/不采用/继续观察，以及下一步。
```

## 诊断模式

诊断模式用于解释正式表里的异常阶段 ratio，但不能作为正式 baseline。

Page-table timing 诊断：

```bash
RUN_ID=gpu-perf-pttiming-vmonly-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --skip-host \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --guest-panthor-pt-timing \
  --vm-timeout 900
```

重点看 VM summary 中的 `PANTHOR_PT_TIMING` 和 `PANTHOR_PT_STATS`，用于判断 GPA->HPA HVC、2M candidate/fallback、普通 PTE 初始化等成本。

IRQ timing 诊断：

```bash
RUN_ID=gpu-perf-irqstats-vmonly-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --skip-host \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --pmthor-irq-stats \
  --guest-panthor-irq-stats \
  --vm-timeout 900
```

重点看 `pmthor-irq-stats.log`、VM summary 中的 `PANTHOR_JOB_IRQ_STATS`、以及 per-count interrupt snapshots。用于判断 completion 是否来自 host masked/resample/EOI 长尾、guest raw-to-thread wait、IRQ 密度，或 Mesa/fence wait 本身。

Submit timing 诊断：

```bash
RUN_ID=gpu-perf-submitstats-vmonly-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --skip-host \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --guest-panthor-submit-stats \
  --vm-timeout 900
```

重点看 VM summary 中的 `PANTHOR_SUBMIT_STATS`、`DRM_SCHED_PUSH_STATS` 和 `DRM_SCHED_RUN_JOB_STATS`。用于拆分 group submit、vm-bind、scheduler push/wakeup、backend `run_job`、queue-to-start 等成本。

Hugepage、affinity、ALU-heavy 都属于单独诊断轴。每次诊断后如要确认优化是否有效，必须再跑不带诊断开关的正式 Host/VM sweep。

## 手动检查与恢复

测试结束后检查 host 状态：

```bash
ssh root@192.168.137.10 '
  echo driver=$(basename $(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver 2>/dev/null))
  ls -l /dev/pmthor /dev/dri 2>&1 || true
  pgrep -a firecracker || true
'
```

期望：

```text
driver=pmthor
/dev/pmthor 存在
没有残留 firecracker
```

如需手动从 `panthor` 恢复到 `pmthor`：

```bash
ssh root@192.168.137.10 '
  pkill -x firecracker 2>/dev/null || true
  if [ "$(basename $(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver 2>/dev/null))" = panthor ]; then
    echo fb000000.gpu > /sys/bus/platform/drivers/panthor/unbind
    sleep 1
  fi
  if [ "$(basename $(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver 2>/dev/null))" != pmthor ]; then
    echo fb000000.gpu > /sys/bus/platform/drivers/pmthor/bind
    sleep 1
  fi
  modprobe -r panthor 2>/dev/null || true
  echo driver=$(basename $(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver 2>/dev/null))
  ls -l /dev/pmthor /dev/dri 2>&1 || true
'
```

## 常见失败

### VM 没有 `/dev/dri`

检查 `preflight.txt`、`vm-count${COUNT}.log` 和 active VM config。确认 config 指向：

```text
/root/GPU-SFTP/firecracker-bins/kernels/passthrough/Image
```

guest dmesg 应出现 Panthor 初始化信息。如果 config 指向 `Image.bak-*`，先修正为 canonical path。

### VM timeout status 为 124

当前脚本会设置：

```text
GPU_SMOKE_AFTER_RUN=poweroff
```

正常情况下 VM 应主动关机。如果仍 timeout，先看 `vm-count${COUNT}.log` 是否已经出现：

```text
GPU_SMOKE_RESULT=PASS
COMPUTE_CHECK=PASS
```

有 PASS 时通常是关机路径或 timeout 策略问题；没有 PASS 时再查 Panthor probe、Mesa 或 compute mismatch。

### Host 绑定不到 `panthor`

检查：

```text
host-switch.log
restore-status.txt
/etc/modprobe.d/*panthor*
```

host 可能有 `panthor` blacklist。脚本使用显式 `modprobe panthor` 和 sysfs bind，不永久删除 blacklist。

### Host workload 使用 software renderer

`gles-compute-smoke` 会拒绝 `llvmpipe`、`softpipe` 和 `Software Rasterizer`。如果出现 software renderer，检查 host `/dev/dri`、Mesa driver、`LIBGL_ALWAYS_SOFTWARE` 和 `MESA_LOADER_DRIVER_OVERRIDE`。

### Result 中 ratio 为 `NA`

说明对应日志里没有可解析的 `PERF_PHASE_US` 或 `PERF_ITER_US`。常见原因：

- 远端没有重新编译新的 `gles-compute-smoke`。
- VM rootfs 没有注入新的 `/root/gles-compute-smoke`。
- 使用了 `--skip-rootfs-update` 但 rootfs 内还是旧 binary。
- workload 失败，未进入 perf 输出。

重新运行时去掉 `--skip-remote-build` 和 `--skip-rootfs-update`。

### Completion 或 IRQ 突然出现长尾

先检查 host/guest dmesg 和 VM console 是否有高频热路径日志，尤其是：

```text
kvm_notify_acked_irq
kvm_notify_acked_gsi
pmthor
PANTHOR_JOB_IRQ
inject irq
resample
```

如果没有明显日志污染，再用 VM-only 的 `--pmthor-irq-stats --guest-panthor-irq-stats` 诊断 host masked/resample/EOI、guest raw-to-thread wait 和 IRQ 密度。诊断完成后必须再跑正式 Host/VM sweep。

## 下次让 Codex 快速测试时的指令

可以直接说：

```text
参考 GPU_HOST_VS_PASSTHROUGH_PERF_TEST_GUIDE.md，
运行一次 host vs passthrough GLES compute 正式性能测试，
参数 --host-rootfs-userspace --exclude-cpu-prepare --iterations 100 --warmup 5，
使用默认 4 MiB / 16 MiB / 64 MiB sweep，
其中 64 MiB 使用 --large-count-iterations 20，
不要使用 tracing、stats、hugepages、affinity 或其他诊断开关，
只报告 result 中的 Formal Host/VM performance ratio table。
```

Codex 应执行：

```bash
cd /home/mzh/gpu
RUN_ID=gpu-perf-host-vs-passthrough-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --host-rootfs-userspace \
  --exclude-cpu-prepare \
  --iterations 100 \
  --warmup 5 \
  --large-count-iterations 20 \
  --large-count-warmup 5 \
  --vm-timeout 900 \
  --host-timeout 900
```

然后读取：

```text
/home/mzh/gpu/GPU-SFTP/log/passthrough/perf/${RUN_ID}/result
```

报告内容只需要：

- run ID 和本地日志路径
- `RESULT`
- renderer/version 是否一致
- `Restored GPU driver`
- `Formal Host/VM performance ratio table`
- 是否存在诊断开关、Mesa 版本不一致或 PASS/FAIL 异常
