# Panthor GLES Compute Smoke Baseline Trace 分析报告

本文档记录一次在 Firecracker guest 中运行 `gles-compute-smoke` 的 Panthor IOCTL baseline trace，并基于 `strace -X raw`、guest console log 和 guest `dmesg` 对 GPU task 的创建、dispatch、执行、readback 和 cleanup 路径进行分析。

本文的文字说明使用中文，核心专业术语保留英文，例如 `IOCTL`、`VM_BIND`、`GROUP_SUBMIT`、`BO`、`GPU VA`、`GPA`、`HPA`、`syncobj`、`timeline fence`、`CSF`。

## 1. 结论摘要

这次 baseline 可以确认：

- `gles-compute-smoke` 在 Firecracker guest 中成功使用 Panthor/Mesa userspace driver 执行真实 GPU compute task。
- workload 打开的设备是 `/dev/dri/card0`，Mesa renderer 是 `Mali-G610 (Panfrost)`，不是 `llvmpipe` 或其他 software renderer。
- compute shader 完成了 `values[i] = values[i] * 3 + 7`，CPU readback 校验通过，输出 `COMPUTE_CHECK=PASS count=64 formula=x*3+7`。
- Panthor private IOCTL 全部返回 `0`，没有出现 `-EINVAL`、`-ENOENT`、`-ETIMEDOUT`、`-EFAULT` 等错误。
- 真实路径中出现了 `DRM_IOCTL_PANTHOR_GROUP_SUBMIT` 两次，其中第二次位于 `STAGE=dispatch` 之后，是本次 compute dispatch 的核心提交点。
- guest `dmesg` 中没有 `Oops`、`Call trace`、`fault`、`reset`、`WARN`、`ERROR` 等异常信号。
- `VM_BIND` 总计 28 次，结合最终 GPU writeback 正确，说明当前 guest shadow GPU page table 路径至少能支撑这个 Mesa/Panthor compute workload 的 command stream、state buffer、shader buffer、SSBO 和 cleanup unmap。

更准确地说，这份 baseline 证明了当前 GPU passthrough 在单 VM、单 process、短生命周期 GLES compute workload 下已经具备功能正确性。它不证明复杂 workload、多 VM sharing、fault isolation、reset isolation、fair scheduling 或 memory accounting 已经完成，但它是后续 GPU virtualization sharing 研究的有效起点。

## 2. 实验环境与产物

### 2.1 远程 host

```text
Host: 192.168.137.10
Hostname: opencca-rock5b-rk3588
Host kernel: Linux opencca-rock5b-rk3588 6.12.0+ #5 SMP PREEMPT Fri May 29 18:10:11 CST 2026 aarch64
Architecture: aarch64
```

### 2.2 guest

```text
Guest kernel: Linux firecracker-gpu-trace 6.12.0-ge0e960df8a04-dirty #211 SMP PREEMPT Mon Jun 1 15:41:43 CST 2026 aarch64
Firecracker rootfs: /root/GPU-SFTP/firecracker-bins/rootfs/rootfs-panfrost-trace.ext4
Firecracker config: /root/GPU-SFTP/firecracker-bins/configs/passthrough/trace/gpu-panfrost-trace-vm-config.json
Firecracker boot args: console=ttyS0 root=/dev/vda rw rootfstype=ext4 init=/init panic=-1 print-fatal-signals=1
```

### 2.3 本地 trace 产物

最终用于分析的是第三轮 raw baseline：

```text
Run ID: panthor-baseline-raw-20260601-162811
本地目录: panthor-baseline-raw-20260601-162811/
guest console: panthor-baseline-raw-20260601-162811/guest.log
trace tarball: panthor-baseline-raw-20260601-162811/panthor-baseline-trace.tar.gz
trace 目录: panthor-baseline-raw-20260601-162811/panthor-baseline-trace/
```

trace 目录中的关键文件：

```text
dmesg-after.txt        guest dmesg after workload
ioctl-all.txt          raw strace 中所有 ioctl
ioctl-panthor.txt      raw strace 中过滤出的 Panthor private ioctl
panthor-ioctl-map.txt  Panthor ioctl number 映射表
strace.86              workload 主线程 strace
strace.88              Mesa worker thread strace
```

### 2.4 Firecracker 外层返回码说明

本次 Firecracker wrapper 的返回码是：

```text
FIRECRACKER_RC=124
```

这个 `124` 来自外层 `timeout 75s`。原因是 guest `/init` 在 trace 完成后进入 `/bin/sh`，Firecracker 本身不会自动退出。因此判断 workload 成败不能看外层 `FIRECRACKER_RC`，而应看 guest 内部输出：

```text
[panthor-trace] workload rc=0
[init-trace] TRACE_RESULT rc=0
COMPUTE_CHECK=PASS count=64 formula=x*3+7
```

本次 workload 成功。

## 3. Trace 方法

### 3.1 使用的脚本

本次使用：

```text
GPU-SFTP/tests/gpu-compute-smoke/trace-panthor-task.sh
```

脚本会执行：

```sh
strace -ff \
  -X raw \
  -e trace=openat,close,ioctl,mmap,munmap,poll,ppoll,read,write,futex \
  -s 256 \
  -ttt \
  -o "${OUT_DIR}/strace" \
  /root/gles-compute-smoke /dev/dri/card0
```

这里必须使用 `-X raw`。如果不使用 raw style，`strace` 会把 Panthor private IOCTL 的 raw number 错误显示成其他 DRM driver 的同号名字，例如 `DRM_IOCTL_VC4_CREATE_SHADER_BO`、`DRM_IOCTL_MSM_GEM_INFO`、`DRM_IOCTL_I915_GETPARAM` 等。那些名字并不代表真实调用了 VC4/MSM/I915 driver，只是 `strace` 对 DRM command number 的有限解码导致的歧义。

使用 raw style 后，关键命令以十六进制形式稳定出现：

```text
0xc0106440 DRM_IOCTL_PANTHOR_DEV_QUERY
0xc0106441 DRM_IOCTL_PANTHOR_VM_CREATE
0xc0086442 DRM_IOCTL_PANTHOR_VM_DESTROY
0xc0186443 DRM_IOCTL_PANTHOR_VM_BIND
0xc0186445 DRM_IOCTL_PANTHOR_BO_CREATE
0xc0106446 DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET
0xc0386447 DRM_IOCTL_PANTHOR_GROUP_CREATE
0xc0086448 DRM_IOCTL_PANTHOR_GROUP_DESTROY
0xc0186449 DRM_IOCTL_PANTHOR_GROUP_SUBMIT
0xc028644b DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE
0xc008644c DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY
```

### 3.2 ftrace/bpftrace 状态

本次 guest 输出：

```text
[panthor-trace] tracefs is unavailable; ftrace disabled
```

因此本次分析主要基于 `strace -X raw` 与 `dmesg`。这意味着：

- 可以确定 IOCTL 的顺序、次数、返回值、所在 workload stage。
- 可以确定 userspace 层面是否进入 `GROUP_SUBMIT`、`VM_BIND`、`BO_CREATE`。
- 不能直接解码 `struct drm_panthor_vm_bind_op` 中每个 `bo_handle`、`bo_offset`、`va`、`size`、`flags`。
- 不能直接解码 `struct drm_panthor_queue_submit` 中的 `stream_addr`、`stream_size`、`latest_flush`。
- 不能直接看到 guest `GPA` 经 `HVC` 转 `HPA` 后写入 GPU page table 的每个 entry。

后续如果要分析 GPU virtualization sharing 的 memory accounting、address translation、job scheduling，需要启用 guest `ftrace`/`bpftrace` 或添加 Panthor driver tracepoint。

## 4. Workload 内容

`gles-compute-smoke` 的主要逻辑：

```text
open /dev/dri/card0
gbm_create_device()
eglGetPlatformDisplayEXT(EGL_PLATFORM_GBM_MESA, ...)
eglInitialize()
eglCreateContext()
eglMakeCurrent()
glCreateShader(GL_COMPUTE_SHADER)
glCompileShader()
glLinkProgram()
glBufferData(GL_SHADER_STORAGE_BUFFER, ...)
glDispatchCompute(64, 1, 1)
glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT | GL_BUFFER_UPDATE_BARRIER_BIT)
glMapBufferRange(GL_SHADER_STORAGE_BUFFER, ...)
CPU readback verify
```

compute shader：

```glsl
#version 310 es
layout(local_size_x = 1) in;
layout(std430, binding = 0) buffer Data { uint values[]; };
void main() {
    uint i = gl_GlobalInvocationID.x;
    values[i] = values[i] * 3u + 7u;
}
```

校验目标：

```text
count = 64
expected[i] = i * 3 + 7
```

最终输出：

```text
GL_RENDERER=Mali-G610 (Panfrost)
COMPUTE_CHECK=PASS count=64 formula=x*3+7
```

这说明 workload 使用的是 Panfrost/Panthor GPU path，而不是 software renderer。

## 5. Stage 时间线

根据 `strace.86` 中 workload 自己输出的 `STAGE=`，得到时间线如下。

| Stage | 相对上一阶段耗时 | 说明 |
| --- | ---: | --- |
| `open-drm` | 起点 | 打开 `/dev/dri/card0` |
| `gbm-create-device` | 1.902 ms | 创建 `gbm_device`，Mesa 开始加载 GBM/DRI driver |
| `egl-get-display` | 587.244 ms | Mesa loader、Gallium、driver config、DRI scan 等初始化成本主要在这里 |
| `egl-initialize` | 28.745 ms | EGL display 初始化 |
| `egl-choose-config` | 40.437 ms | EGL config 选择 |
| `egl-create-context` | 1.862 ms | EGL context 创建开始 |
| `egl-make-current` | 100.284 ms | context 激活，Panthor VM/group/queue 等对象基本建立完成 |
| `gl-query` | 10.668 ms | 查询 GL vendor/renderer/version |
| `compile-shader` | 4.780 ms | compute shader compile 开始 |
| `link-program` | 124.827 ms | shader link，期间访问 Mesa shader cache |
| `buffer-setup` | 32.205 ms | 创建并初始化 SSBO 或相关 BO |
| `dispatch` | 2.690 ms | 调用 `glDispatchCompute()` |
| `map-result` | 41.902 ms | `glMemoryBarrier()` 后进入 readback |
| `COMPUTE_CHECK=PASS` | `map-result` 后 2.516 ms | CPU readback 校验通过 |

从 `open-drm` 到 `map-result` 总计约：

```text
977.546 ms
```

从 `dispatch` 到 `map-result` 约：

```text
41.902 ms
```

注意这个耗时包含 `strace` overhead、Mesa shader cache IO、userspace 同步等待、driver 初始化和 Firecracker 环境因素，不应该直接当成裸 GPU execution latency。

## 6. IOCTL 总览

### 6.1 Panthor private IOCTL 计数

| IOCTL | raw number | 次数 | 返回值 |
| --- | ---: | ---: | --- |
| `DRM_IOCTL_PANTHOR_DEV_QUERY` | `0xc0106440` | 2 | 全部 `0` |
| `DRM_IOCTL_PANTHOR_VM_CREATE` | `0xc0106441` | 1 | `0` |
| `DRM_IOCTL_PANTHOR_VM_DESTROY` | `0xc0086442` | 1 | `0` |
| `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | 28 | 全部 `0` |
| `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | 14 | 全部 `0` |
| `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | 21 | 全部 `0` |
| `DRM_IOCTL_PANTHOR_GROUP_CREATE` | `0xc0386447` | 1 | `0` |
| `DRM_IOCTL_PANTHOR_GROUP_DESTROY` | `0xc0086448` | 1 | `0` |
| `DRM_IOCTL_PANTHOR_GROUP_SUBMIT` | `0xc0186449` | 2 | 全部 `0` |
| `DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE` | `0xc028644b` | 1 | `0` |
| `DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY` | `0xc008644c` | 1 | `0` |

关键信息：

- 所有 Panthor private IOCTL 都成功返回。
- `VM_BIND` 数量最多，说明 Mesa/Panthor 对多个 BO 进行了 GPU VA mapping，也在 cleanup 时进行了 unmap。
- `GROUP_SUBMIT` 出现两次，说明 workload 至少经历了一个 Mesa/Panthor internal submit 和一个实际 compute dispatch submit。
- `TILER_HEAP_CREATE` 在 compute workload 中也出现一次，这不一定代表本次 workload 真的走了 fragment/tiler workload，它更可能是 Mesa/Panthor context/group 初始化时统一创建的 supporting object。

### 6.2 Common DRM IOCTL 计数

| IOCTL | raw number | 次数 | 返回值 |
| --- | ---: | ---: | --- |
| `DRM_IOCTL_VERSION` | `0xc0406400` | 12 | 全部 `0` |
| `DRM_IOCTL_GET_CAP` | `0xc010640c` | 1 | `0` |
| `DRM_IOCTL_SYNCOBJ_CREATE` | `0xc00864bf` | 3 | 全部 `0` |
| `DRM_IOCTL_SYNCOBJ_WAIT` | `0xc02864c3` | 2 | 全部 `0` |
| `DRM_IOCTL_SYNCOBJ_TRANSFER` | `0xc02064cc` | 1 | `0` |
| `DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT` | `0xc03064ca` | 5 | 3 次 `0`，2 次 `-1 ETIME` |
| `DRM_IOCTL_SYNCOBJ_DESTROY` | `0xc00864c0` | 3 | 全部 `0` |
| `DRM_IOCTL_GEM_CLOSE` | `0x40086409` | 14 | 全部 `0` |

`DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT` 出现两次 `-1 ETIME (Timer expired)`，随后又出现成功 wait：

```text
0xc03064ca = -1 ETIME
0xc03064ca = -1 ETIME
0xc03064ca = 0
0xc03064ca = 0
0xc03064ca = 0
```

这更像 Mesa/Panthor userspace 使用 short timeout 或 nonblocking polling 方式检查 fence/timeline 状态。由于后续 wait 成功且最终 `COMPUTE_CHECK=PASS`，这两个 `ETIME` 不表示 GPU task 失败。

## 7. Panthor IOCTL 生命周期分析

### 7.1 `gbm-create-device` 阶段

该阶段 Panthor private IOCTL：

```text
DEV_QUERY x2
VM_CREATE x1
BO_CREATE x2
VM_BIND x2
BO_MMAP_OFFSET x2
```

典型序列：

```text
DRM_IOCTL_PANTHOR_DEV_QUERY
DRM_IOCTL_PANTHOR_DEV_QUERY
DRM_IOCTL_PANTHOR_VM_CREATE
DRM_IOCTL_PANTHOR_BO_CREATE
DRM_IOCTL_PANTHOR_VM_BIND
DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET
DRM_IOCTL_PANTHOR_BO_CREATE
DRM_IOCTL_PANTHOR_VM_BIND
DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET
```

解释：

- 两次 `DEV_QUERY` 通常对应 GPU info 和 CSIF info 查询。
- `VM_CREATE` 创建本进程的 GPU address space。
- 早期 `BO_CREATE`/`VM_BIND`/`BO_MMAP_OFFSET` 用于 Mesa/Panthor 初始化所需的基础 BO，例如 driver state、flush page、queue/control 相关 buffer 或 internal object。
- 这个阶段说明 userspace driver 已经从单纯打开 DRM node 进入 Panthor UAPI 初始化。

### 7.2 `egl-create-context` 阶段

该阶段 Panthor private IOCTL：

```text
BO_CREATE x7
VM_BIND x7
BO_MMAP_OFFSET x6
GROUP_CREATE x1
TILER_HEAP_CREATE x1
GROUP_SUBMIT x1
```

关键序列：

```text
DRM_IOCTL_PANTHOR_GROUP_CREATE
DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE
...
DRM_IOCTL_PANTHOR_GROUP_SUBMIT
```

解释：

- `GROUP_CREATE` 表示 Panthor scheduler group 和 queue 已经创建。
- `TILER_HEAP_CREATE` 出现在 context 创建后，说明 Mesa/Panthor 统一准备了 tiler heap supporting object。即使本 workload 是 compute-only，也可能创建这个 object。
- 第一笔 `GROUP_SUBMIT` 出现在 `egl-create-context` 到 `egl-make-current` 之间，更可能是 Mesa/Panthor internal initialization submit，而不是用户显式 `glDispatchCompute()`。
- guest `dmesg` 同期出现新的 `arm-lpae io-pgtable` 和 `enable as`：

```text
arm-lpae io-pgtable: [MZH][arm_lpae_s1_cfg.ttbr]:5c58f000
[MZH][panthor_vm_active]vm->as.id=1
[MZH][enable as]:as_nr=1 transtab=5c58f000 ...
```

这与 `VM_CREATE` 后 VM 被绑定到 GPU address space 的过程吻合。

### 7.3 `buffer-setup` 阶段

该阶段 Panthor private IOCTL：

```text
BO_CREATE x1
VM_BIND x1
BO_MMAP_OFFSET x1
```

解释：

- workload 在 `glBufferData(GL_SHADER_STORAGE_BUFFER, ...)` 附近创建并初始化 SSBO。
- 这组 `BO_CREATE`/`VM_BIND`/`BO_MMAP_OFFSET` 很可能对应用户 visible buffer 或与 SSBO backing storage 相关的 BO。
- 由于后续 CPU readback 看到正确结果，这个 BO 的 CPU mapping 与 GPU mapping 在当前 passthrough path 下是一致的。

### 7.4 `dispatch` 阶段

该阶段 Panthor private IOCTL：

```text
BO_CREATE x4
VM_BIND x4
BO_MMAP_OFFSET x6
GROUP_SUBMIT x1
```

核心序列：

```text
STAGE=dispatch
...
DRM_IOCTL_PANTHOR_BO_CREATE
DRM_IOCTL_PANTHOR_VM_BIND
DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET
...
DRM_IOCTL_PANTHOR_GROUP_SUBMIT
...
DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT = -1 ETIME
DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT = -1 ETIME
DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT = 0
```

解释：

- `STAGE=dispatch` 之后的 `GROUP_SUBMIT` 是本次 compute shader 真正提交给 GPU 的关键证据。
- `GROUP_SUBMIT` 返回 `0` 说明 kernel driver 接受了 job submission。
- 随后的 `syncobj`/`timeline fence` wait 表明 userspace 等待 GPU job 完成。
- 两个短暂 `ETIME` 后 wait 成功，不是错误路径。
- guest `dmesg` 在 `dispatch` 和 `map-result` 附近出现 `Panthor_job_irq_handler`：

```text
[    1.565091] [MZH]Panthor_job_irq_handler
[    1.786929] [MZH]Panthor_job_irq_handler
```

这说明 GPU job interrupt path 被触发，和 userspace fence wait 成功相互印证。

### 7.5 `map-result` 与 cleanup 阶段

该阶段 Panthor private IOCTL：

```text
BO_MMAP_OFFSET x6
TILER_HEAP_DESTROY x1
GROUP_DESTROY x1
VM_BIND x14
VM_DESTROY x1
```

解释：

- `map-result` 后 Mesa 需要确保 GPU 写入的 buffer 对 CPU 可见，然后执行 readback。
- `COMPUTE_CHECK=PASS` 出现在 `map-result` 后约 2.516 ms，说明 CPU 读回的 SSBO 内容正确。
- 后续大量 `VM_BIND` 很可能是 unmap 操作。由于 raw `strace` 没有解码 `struct drm_panthor_vm_bind_op.flags`，这里不能仅从 syscall 层区分 map/unmap，但它发生在 `GROUP_DESTROY` 之后和 `VM_DESTROY` 之前，符合 cleanup unmap 行为。
- `GEM_CLOSE x14` 和 `BO_CREATE x14` 数量一致，说明 userspace 关闭了创建过的 GEM handles。
- `VM_DESTROY` 返回 `0`，说明 VM 生命周期正常结束。

## 8. GPU 执行正确性的证据链

本次 baseline 不是单纯 probe 成功，而是形成了完整证据链。

### 8.1 userspace driver 选择正确

```text
DRM_NODE=/dev/dri/card0
GBM_BACKEND=drm
EGL_VENDOR=Mesa Project
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
```

这说明：

- workload 通过 DRM/GBM/EGL 进入 Mesa/Panfrost/Panthor path。
- `GL_RENDERER` 是真实 Mali-G610/Panfrost，不是 `llvmpipe` 或 `softpipe`。

### 8.2 Panthor UAPI 生命周期完整

本次看到完整对象生命周期：

```text
DEV_QUERY
VM_CREATE
BO_CREATE
VM_BIND
BO_MMAP_OFFSET
GROUP_CREATE
TILER_HEAP_CREATE
GROUP_SUBMIT
syncobj wait
TILER_HEAP_DESTROY
GROUP_DESTROY
VM_BIND cleanup
VM_DESTROY
GEM_CLOSE
```

这说明用户态 driver 不是只打开设备或查询参数，而是完成了 GPU address space、buffer object、scheduler group、queue submit 和 cleanup。

### 8.3 GPU job 进入 execution path

关键点：

```text
DRM_IOCTL_PANTHOR_GROUP_SUBMIT x2, 全部返回 0
dispatch 阶段出现 GROUP_SUBMIT
dispatch/map-result 附近出现 Panthor_job_irq_handler
syncobj timeline wait 最终返回 0
```

这说明 job 被 kernel 接收，并且 GPU interrupt/fence path 正常推进。

### 8.4 GPU writeback 被 CPU 正确读回

最终输出：

```text
COMPUTE_CHECK=PASS count=64 formula=x*3+7
```

这条最关键。它说明至少对本 workload：

- command stream 可被 GPU 正确读取。
- shader/state/descriptor 相关 BO 可被 GPU 正确读取。
- SSBO 可被 GPU 正确写入。
- GPU 写入结果对 CPU readback 可见。
- 当前 guest shadow GPU page table 中 `GPU VA -> Host PA` mapping 对实际计算路径有效。

## 9. 与当前 GPU passthrough 特殊设计的关系

当前 guest Panthor 路径包含特殊设计：

```text
guest DMA address / GPA
  -> HVC
  -> host KVM 查询 HPA
  -> guest 构造 GPU VA -> Host PA shadow page table
  -> GPU 使用该 page table 访问 memory
```

这次 baseline 对该链路的意义：

- `VM_BIND x28` 全部成功，说明 userspace 请求的 BO mapping 能进入 kernel driver 的 VM map path。
- `GROUP_SUBMIT x2` 全部成功，说明 job submit 之前的 address space 与 BO mapping 没有被 driver 拒绝。
- `COMPUTE_CHECK=PASS` 说明 GPU 最终确实通过这些 mapping 读写了正确 memory。
- 没有出现 GPU fault/reset，说明至少没有触发明显 invalid PTE、permission fault、address size fault 或 unmapped VA fault。

但这份 `strace` 还不能证明：

- 每个 `VM_BIND` 的 `GPU VA`、`BO offset`、`size`、`flags` 是什么。
- 每个 leaf GPU PTE 里写入的 `HPA` 是什么。
- 每次 `HVC GPA->HPA` 是否覆盖了所有 page、是否出现 fallback、是否存在 partial map。
- cache maintenance、TLB invalidation、sync object dependency 在复杂 workload 下是否仍然完全正确。

因此下一阶段应该在 `panthor_vm_map_pages()`、`io-pgtable-arm.c map_pages`、`panthor_gpa_to_hpa_batch()`、`panthor_job_create()`、`queue_run_job()` 增加 tracepoint 或 debug hook，把 syscall-level baseline 扩展成 address-level baseline。

## 10. 重要观察

### 10.1 `strace` 默认 IOCTL decode 会误导

第二轮非 raw `strace` 中曾出现类似：

```text
DRM_IOCTL_VC4_CREATE_SHADER_BO
DRM_IOCTL_AMDGPU_BO_LIST or DRM_IOCTL_MSM_GEM_INFO
DRM_IOCTL_I915_GETPARAM
```

这些不是实际 driver。原因是 DRM private IOCTL command number 在不同 driver 间共享 offset，`strace` 没有 Panthor UAPI 的完整解码时会把相同 raw number 显示成其他 driver 的名字。

因此后续所有 Panthor IOCTL baseline 都应使用：

```sh
strace -X raw ...
```

然后用 `panthor-ioctl-map.txt` 或本报告的 mapping 表手动解释。

### 10.2 `tracefs` 当前在 guest 内不可用

脚本输出：

```text
tracefs is unavailable; ftrace disabled
```

这表示当前 rootfs/kernel 组合下不能直接使用 guest ftrace/kprobe。为了拿到 `VM_BIND` 参数、`GROUP_SUBMIT` 参数、`queue_run_job` 信息，需要下一步做其中之一：

- 调整 guest kernel config，启用并验证 `CONFIG_FTRACE`、`CONFIG_KPROBES`、`CONFIG_TRACEFS`。
- 在 guest rootfs 中确保 `/sys/kernel/tracing` 可挂载。
- 使用 driver 内置 `tracepoint` 或临时 `pr_info` hook。
- 使用 host-side tracing 观察 HVC/KVM 路径，和 guest-side syscall trace 对齐。

### 10.3 `TILER_HEAP_CREATE` 出现在 compute workload 中

本 workload 是 `GL_COMPUTE_SHADER`，但仍看到：

```text
DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE x1
DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY x1
```

这可能是 Mesa/Panthor context/group 初始化统一创建 supporting object，不应简单理解为本 workload 执行了 fragment/tiler rendering。后续如果要区分 compute-only 与 graphics workload，需要结合 `GROUP_CREATE` 参数中的 queue/core mask、`GROUP_SUBMIT` command stream、以及 shader stage 信息。

### 10.4 cleanup 中 `VM_BIND x14` 很关键

cleanup 阶段出现 14 次 `VM_BIND`，随后 `VM_DESTROY`：

```text
VM_BIND x14
VM_DESTROY x1
```

这些 `VM_BIND` 很可能是 unmap 操作。对 GPU virtualization sharing 来说，unmap path 和 map path 同样重要：

- 共享设计中需要准确回收 per-VM GPU memory accounting。
- shadow page table 需要删除旧 `GPU VA -> HPA` mapping。
- 如果 unmap 与 job completion/fence ordering 处理不当，后续 VM 或后续 workload 可能访问 stale mapping。

因此下一阶段 trace 不能只看 submit，还要看 cleanup/unmap。

## 11. 可作为 regression gate 的 baseline 条件

后续修改 guest/host GPU virtualization 代码后，可以用这份 baseline 作为最小功能回归条件。

建议 gate：

```text
1. guest console 中必须出现 GL_RENDERER=Mali-G610 (Panfrost)
2. guest console 中必须出现 COMPUTE_CHECK=PASS
3. guest console 中必须出现 TRACE_RESULT rc=0
4. Panthor private IOCTL 返回值必须全部为 0
5. 至少出现：
   DEV_QUERY >= 2
   VM_CREATE >= 1
   BO_CREATE >= 1
   VM_BIND >= 1
   GROUP_CREATE >= 1
   GROUP_SUBMIT >= 1
   VM_DESTROY >= 1
6. dmesg 中不能出现 Oops、Call trace、GPU fault、fatal fault、reset loop
7. 如果启用 raw strace，不能只看 strace 默认解码出来的 driver 名，必须按 raw number 映射 Panthor IOCTL
```

对当前这份 baseline，实际值是：

```text
DEV_QUERY=2
VM_CREATE=1
BO_CREATE=14
VM_BIND=28
BO_MMAP_OFFSET=21
GROUP_CREATE=1
GROUP_SUBMIT=2
TILER_HEAP_CREATE=1
TILER_HEAP_DESTROY=1
GROUP_DESTROY=1
VM_DESTROY=1
```

## 12. 后续建议

### 12.1 先补 guest-side ftrace/bpftrace 能力

为了从 syscall-level 进入 parameter-level，需要能 hook：

```text
panthor_ioctl_vm_bind()
panthor_vm_bind_exec_sync_op()
panthor_ioctl_group_submit()
panthor_job_create()
queue_run_job()
queue_timedout_job()
panthor_vm_map_pages()
panthor_gpa_to_hpa_batch()
```

如果 `bpftrace` 可用，最优先解码：

```text
drm_panthor_vm_bind_op.flags
drm_panthor_vm_bind_op.bo_handle
drm_panthor_vm_bind_op.bo_offset
drm_panthor_vm_bind_op.va
drm_panthor_vm_bind_op.size

drm_panthor_queue_submit.queue_index
drm_panthor_queue_submit.stream_addr
drm_panthor_queue_submit.stream_size
drm_panthor_queue_submit.latest_flush
```

### 12.2 增加 driver tracepoint

长期研究不建议依赖 `pr_info` 或 hardcoded bpftrace offset。建议在 Panthor guest driver 中增加 tracepoint：

```text
panthor_vm_create
panthor_bo_create
panthor_vm_bind
panthor_shadow_pt_map
panthor_gpa_to_hpa
panthor_group_create
panthor_group_submit
panthor_job_create
panthor_job_run
panthor_job_done
panthor_job_timeout
panthor_gpu_fault
```

其中对当前 passthrough 设计最重要的是：

```text
GPU VA
guest DMA address / GPA
HPA
page size
page count
prot flags
VM id
BO handle
group handle
queue index
stream_addr
stream_size
latest_flush
```

### 12.3 扩展 workload

当前 workload 是单次短 compute。建议后续按这个顺序扩展：

```text
1. 多次 glDispatchCompute，观察 GROUP_SUBMIT 是否增长、VM/group 是否复用。
2. 多个 SSBO，观察 BO_CREATE/VM_BIND 数量和 cleanup unmap。
3. 多 context 单 process，观察 VM_CREATE/GROUP_CREATE 数量。
4. 多 process 单 VM 环境，观察 per-process DRM file、VM、group 生命周期。
5. 多 Firecracker VM sharing，观察 host 侧调度、HVC GPA->HPA 查询、GPU fault/reset 影响域。
```

## 13. 附录：完整 Panthor private IOCTL 序列

下面是本次 raw baseline 中的 Panthor private IOCTL 序列，按时间排序。`stage` 表示该 IOCTL 发生时最近一个 workload `STAGE=`。

| # | stage | IOCTL | raw number | ret |
| ---: | --- | --- | ---: | --- |
| 1 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_DEV_QUERY` | `0xc0106440` | `0` |
| 2 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_DEV_QUERY` | `0xc0106440` | `0` |
| 3 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_VM_CREATE` | `0xc0106441` | `0` |
| 4 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 5 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 6 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 7 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 8 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 9 | `gbm-create-device` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 10 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 11 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 12 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 13 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 14 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 15 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 16 | `egl-create-context` | `DRM_IOCTL_PANTHOR_GROUP_CREATE` | `0xc0386447` | `0` |
| 17 | `egl-create-context` | `DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE` | `0xc028644b` | `0` |
| 18 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 19 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 20 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 21 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 22 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 23 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 24 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 25 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 26 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 27 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 28 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 29 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 30 | `egl-create-context` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 31 | `egl-create-context` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 32 | `egl-create-context` | `DRM_IOCTL_PANTHOR_GROUP_SUBMIT` | `0xc0186449` | `0` |
| 33 | `buffer-setup` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 34 | `buffer-setup` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 35 | `buffer-setup` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 36 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 37 | `dispatch` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 38 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 39 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 40 | `dispatch` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 41 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 42 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 43 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 44 | `dispatch` | `DRM_IOCTL_PANTHOR_GROUP_SUBMIT` | `0xc0186449` | `0` |
| 45 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 46 | `dispatch` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 47 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 48 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_CREATE` | `0xc0186445` | `0` |
| 49 | `dispatch` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 50 | `dispatch` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 51 | `map-result` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 52 | `map-result` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 53 | `map-result` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 54 | `map-result` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 55 | `map-result` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 56 | `map-result` | `DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET` | `0xc0106446` | `0` |
| 57 | `map-result` | `DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY` | `0xc008644c` | `0` |
| 58 | `map-result` | `DRM_IOCTL_PANTHOR_GROUP_DESTROY` | `0xc0086448` | `0` |
| 59 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 60 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 61 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 62 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 63 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 64 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 65 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 66 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 67 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 68 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 69 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 70 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 71 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 72 | `map-result` | `DRM_IOCTL_PANTHOR_VM_BIND` | `0xc0186443` | `0` |
| 73 | `map-result` | `DRM_IOCTL_PANTHOR_VM_DESTROY` | `0xc0086442` | `0` |

## 14. 最终判断

这份 baseline 表明：当前 Firecracker guest 中 Panthor passthrough 不只是 driver probe 成功，而是已经跑通了一个完整 Mesa/Panthor userspace GPU compute task。任务经历了 `VM_CREATE`、`BO_CREATE`、`VM_BIND`、`GROUP_CREATE`、`GROUP_SUBMIT`、`syncobj wait`、GPU interrupt、CPU readback、cleanup 的完整生命周期，并且最终 GPU 写回数据正确。

因此，当前状态可以作为后续 GPU virtualization sharing 研究的基础 baseline。下一步研究重点应从“能不能跑”转向“如何观测、隔离和调度多个 VM 的 VM、BO、GPU VA、HPA、job、fence、fault 和 reset 影响域”。
