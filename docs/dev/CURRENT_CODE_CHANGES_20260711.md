# 2026-07-11 当前代码变更分析

> **2026-07-18模型修正：** Realm GPU页面保持`GPT_GPI_REALM`。Realm CPU通过
> GPC/GPT访问，Host/NS CPU被GPT拒绝；Mali DMA按当前平台模型绕过CPU侧GPC，
> 直接使用RMM验证后的HPA。RMM只保留owner/lifetime mapping lease，旧的
> RMM-to-EL3 GPU grant table已经移除，因为Mali事务不会消费它。单Realm直通
> 数据路径不要求SMMU、GPU Realm tag或EL3逐页grant。若需要防范恶意Host，仍须
> 另行隔离GPU MMIO/命令提交控制面，避免Host把GPU作为DMA oracle。

本文基于 `/home/mzh/RK3588/gpu` 当前 worktree、顶层 `git diff`、主要
submodule diff 和本地验证日志重写。它是开发快照，不是 commit log。

## 1. 总体结论

当前变更的核心不是“Realm GPU virtualization 已完成”，而是把
trusted-GPU Realm passthrough 的诊断链路推进到更准确的位置，同时保持现有
non-Realm 路径可用。

主要结论：

1. 普通 single-VM GPU passthrough 和 vmshm shared GPU virtualization 仍保持在
   `6.12.0-opencca-pmthor` SD boot 环境下可运行。
2. 新增一个严格受控的 single-VM trusted-GPU Realm passthrough smoke gate，
   只允许很小 workload，用于继续定位 Realm-private memory 对 Mali/Panthor 的
   device visibility 问题。
3. shared proxy/client Realm GPU mode 继续被显式阻断，避免在没有 protected
   vmshm / guestmemfd shared-buffer ABI 时误认为 shared virtualization 已支持
   Realm GPU。
4. Guest Panthor、Host KVM、Firecracker、RMM 和 TF-A 都围绕
   trusted-GPU grant / Realm MMIO shared alias / diagnostics 做了配套修改。
5. 当前最重要的技术判断是：IRQ path 已经足够活跃，失败焦点更像是 CSF 没有
   读取到 guest CPU 写入的 Realm-private ringbuffer bytes，而不是 runner、
   JSON config 或 IRQ routing。

顶层 diff 规模：

```text
12 files changed, 520 insertions(+), 47 deletions(-)
```

主要 submodule diff 规模：

```text
Linux-Guest-GPU:                 13 files changed, 1381 insertions(+), 270 deletions(-)
Linux-Host-GPU:                   3 files changed,   84 insertions(+),   7 deletions(-)
firecracker/Firecracker-CCA-MZH:  1 file  changed,   21 insertions(+),   3 deletions(-)
opencca/tf-rmm:                   6 files changed,   52 insertions(+)
opencca/trusted-firmware-a:       4 files changed,  244 insertions(+)
```

## 2. Worktree 状态

顶层 tracked files 已修改：

- `GPU-SFTP/tests/gpu-compute-smoke/gles_compute_smoke.c`
- `GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh`
- `docs/shared/CCA_CONFIDENTIAL_GPU_SHARING_DESIGN.md`
- `docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md`
- `docs/start/RASPBERRY_PI_FLASH_RUNBOOK.md`
- `scripts/build/build-host-kernel-payload.sh`
- `scripts/run/run-host-vs-passthrough-gles-perf.sh`
- `scripts/run/run-vmshm-2client-e2e.sh`

已修改 submodule entries：

- `Linux-Guest-GPU`
- `Linux-Host-GPU`
- `firecracker/Firecracker-CCA-MZH`
- `opencca`

未跟踪内容：

- `GPU-SFTP/firecracker-bins/configs/passthrough/generated/`
- `docs/dev/`
- `docs/start/OPENCCA_NETWORK_DISCOVERY_20260711.md`
- `docs/start/OpenCCA自动化配置.md`
- `scripts/net/`

注意：`git submodule status --recursive` 当前在
`firecracker/firecracker-deps` 下失败：

```text
fatal: no submodule mapping found in .gitmodules for path 'kvm-bindings/rust-vmm-ci'
```

提交前需要单独处理 Firecracker dependency tree 的 recursive submodule 状态。

## 3. GLES Smoke 诊断增强

### 3.1 `gles_compute_smoke.c`

`GPU-SFTP/tests/gpu-compute-smoke/gles_compute_smoke.c` 新增 `SIGBUS` 和
`SIGSEGV` handler。进程发生 mapping fault 或 memory fault 时，会输出：

```text
SIGNAL_DIAG sig=... code=... errno=... addr=...
SIGBUS_MAPS_BEGIN
...
SIGBUS_MAPS_END
```

作用：

- 在 guest VM 内没有 debugger 时，可以直接从 Firecracker serial log 判断 fault
  地址属于 EGL/Mesa、DRM mmap、vmshm mapping、guestmemfd private memory，
  还是普通 heap/stack。
- 对 Realm-private memory 和 vmshm mapping 问题特别有价值，因为这类失败经常
  只表现为 `SIGBUS` 或 `GPU_SMOKE_RESULT=FAIL`。

### 3.2 `gpu-smoke.sh`

`GPU-SFTP/tests/gpu-compute-smoke/gpu-smoke.sh` 新增两个 guest Panthor 诊断开关：

```text
gpu_smoke_guest_sync_only_diag
gpu_smoke_guest_ringbuf_read_probe
```

它们会从 kernel command line 导出为：

```text
GPU_SMOKE_GUEST_SYNC_ONLY_DIAG
GPU_SMOKE_GUEST_RINGBUF_READ_PROBE
```

脚本会在真正 GLES workload 前尝试写入 Panthor module parameters：

```text
/sys/module/panthor/parameters/realm_sync_only_diag
/sys/module/panthor/parameters/realm_ringbuf_read_probe
```

同时，`dmesg` 摘要匹配项加入：

```text
PANTHOR_SYNC_ONLY_DIAG
PANTHOR_RINGBUF_READ_PROBE
```

这让 Realm guest Panthor 可以进入 sync-only scheduler completion diagnostic
模式，并可把第一条 Realm guest Panthor ringbuffer instruction 改成 probe
instruction，用来判断 CSF 看到的是否是 guest CPU 写入的 private ringbuffer
bytes。

原先 optional `panthor_ioctl_smoke`、`eglinfo`、payload 检查、Panthor parameter
dump 和 vmshm lookup probe 被移动到诊断参数设置之后，确保诊断状态在真实
workload 开始前已经生效。

## 4. Passthrough Runner：受控 Realm Smoke Gate

`scripts/run/run-host-vs-passthrough-gles-perf.sh` 是顶层 diff 中最关键的脚本
变化。它新增显式实验入口：

```bash
--vm-realm-trusted-gpu-experimental
```

普通 `--vm-realm` 仍然会本地失败，不会触碰 RK3588。只有显式指定
`--vm-realm-trusted-gpu-experimental` 时，脚本才会：

- 设置 `VM_REALM=1` 和 `VM_TRUSTED_GPU_REALM=1`。
- 从现有 passthrough VM JSON 生成临时 Realm config。
- 写入 `machine-config.realm_config`。
- 将 generated config 放到
  `GPU-SFTP/firecracker-bins/configs/passthrough/generated/`。
- 强制要求 sync 到 RK host，避免远端找不到 generated JSON。
- 启动 Firecracker 时注入 `FC_ALLOW_TRUSTED_GPU_REALM=1`。
- 在 preflight、summary、result 中记录 `VM trusted-GPU Realm` 状态。

该模式被限制为很小的 smoke workload：

```text
count <= 4096
iterations <= 3
warmup <= 1
```

同时禁止：

- `--vm-huge-pages-2m`
- `--skip-vm`
- 默认 count sweep
- 非数字的 `count` / `iterations` / `warmup`

新增的两个 guest Panthor 诊断 flag 也被限制在 trusted-GPU Realm 模式下使用：

```text
--guest-panthor-sync-only-diag
--guest-panthor-ringbuf-read-probe
```

其中 `--guest-panthor-ringbuf-read-probe` 还要求同时开启
`--guest-panthor-sync-only-diag`。

这个 gate 的意义是让 trusted-GPU Realm passthrough 保持 fail-closed，只能用小
workload 做可复现诊断，避免被误当作正式 performance path。

## 5. Shared Runner：继续阻断 Realm Shared GPU

`scripts/run/run-vmshm-2client-e2e.sh` 只更新了 Realm mode 的说明和错误信息。

以下选项仍然会在本地失败：

```text
--gles-realm
--gles-client-realm
--gles-proxy-realm
```

新的错误信息要求先验证 single-VM
`--vm-realm-trusted-gpu-experimental`，再设计 proxy/client Realm GPU tasks 所需的
protected vmshm / guestmemfd sharing。

这保持了当前边界：

- proxy VM 和 client VM 的 shared GLES path 仍是 non-Realm 路径。
- single-VM trusted-GPU Realm smoke 不等于 shared Realm GPU support。
- 后续顺序应是先让单 Realm GPU owner 能访问自己的 private command buffers /
  sync objects，再讨论跨 VM shared-buffer ABI。

## 6. Host Kernel Payload Build：固定 `LOCALVERSION`

`scripts/build/build-host-kernel-payload.sh` 新增默认：

```bash
KERNEL_LOCALVERSION="${KERNEL_LOCALVERSION--opencca-pmthor}"
```

并在 kernel build、selected modules build、`kernelrelease` 查询和
`modules_install` 中传递 `LOCALVERSION`。

作用：

- 默认生成 `6.12.0-opencca-pmthor` 一致的 kernel release。
- 避免 host kernel Image 与 rootfs 中 `/lib/modules/6.12.0-opencca-pmthor`
  不匹配。
- 仍允许通过环境变量覆盖 `KERNEL_LOCALVERSION`，便于构建 diagnostic kernel。

## 7. `Linux-Guest-GPU`：Realm Panthor 可信 GPU 访问实验

`Linux-Guest-GPU` 的修改集中在 RSI helpers、Panthor GEM/MMU/scheduler/firmware
diagnostics 和 `io-pgtable-arm`。

修改文件：

- `arch/arm64/include/asm/rsi_cmds.h`
- `arch/arm64/include/asm/rsi_smc.h`
- `drivers/gpu/drm/panthor/panthor_device.*`
- `drivers/gpu/drm/panthor/panthor_drv.c`
- `drivers/gpu/drm/panthor/panthor_fw.*`
- `drivers/gpu/drm/panthor/panthor_gem.*`
- `drivers/gpu/drm/panthor/panthor_mmu.*`
- `drivers/gpu/drm/panthor/panthor_sched.c`
- `drivers/iommu/io-pgtable-arm.c`

### 7.1 RSI Command

guest kernel 新增 OpenCCA 实验 RSI helpers：

```text
SMC_RSI_OPENCCA_GPA_TO_HPA
SMC_RSI_OPENCCA_GPU_REVOKE
rsi_opencca_gpa_to_hpa()
rsi_opencca_gpu_revoke()
```

作用：

- guest Panthor 在建立 GPU page table 时，请求 RMM 将 Realm GPA 转换为 RMM
  验证过的 PA/HPA。
- unmap 或 teardown 时释放对应HPA的RMM mapping lease；这不改变GPT，也不
  撤销硬件GPU权限。

### 7.2 GEM / BO Memory 策略

`panthor_gem.c` 的方向发生关键变化：Realm GPU BO 不再通过
`set_memory_decrypted()` 转成 shared/decrypted memory。

新的策略：

- `panthor_gem_realm_gpu_enabled()` 判断当前是否在 encrypted/Realm 平台。
- `panthor_gem_realm_private_bo()` 识别非 imported、非 vmshm-backed 的
  Realm-private BO。
- Realm passthrough BO 保持 private。
- GPU侧通过Mali page table中的RMM-validated HPA直接访问这些页面。
- CPU/GPU 同步通过 `arch_sync_dma_for_device()`、`arch_sync_dma_for_cpu()`、
  `dma_wmb()`、`dma_rmb()` 等显式完成。

作用是避免把 guest private pages 转成 host-readable shared pages，把安全模型从
“临时共享内存”推进到“保持private，并让GPU直接使用验证过的HPA”。

### 7.3 Panthor Scheduler / MMU / Firmware Diagnostics

Panthor scheduler、MMU、firmware 和 `io-pgtable-arm` 增加大量诊断和路径分流：

- 对 Realm-private GEM/kernel BO 做 cache sync。
- 在GPU page-table path中接入Realm GPA-to-HPA验证和转换。
- 输出 page-table、job submit、scheduler、CSG/CS/queue、sync address、
  ringbuffer instruction 等诊断信息。
- 支持 sync-only completion diagnostic。
- 支持 ringbuffer read probe。
- 记录并帮助判断 CSF 是否读取到了 guest CPU 写入的 Realm-private ringbuffer。

当前诊断结论是：IRQ path 已经足够活跃，但 CSF 似乎没有读取到
Realm-private ringbuffer 的真实内容。问题焦点应继续放在 trusted GPU device
memory visibility，而不是 JSON config 或 IRQ route。

## 8. `Linux-Host-GPU`：Realm MMIO Shared Alias Mapping

`Linux-Host-GPU` 新增：

```c
realm_map_non_secure_phys(...)
```

并让 `KVM_SET_MMIO_REGION` 对 Realm VM 走特殊路径：

- 计算 `shared_bit = BIT_ULL(realm->ia_bits - 1)`。
- 将设备 MMIO 映射到 `guest_phys_addr | shared_bit`。
- 使用 RMM `RTT_MAP_UNPROTECTED`。
- memory attribute 使用 device-nGnRE。
- 非 Realm VM 继续走原来的 stage-2 device mapping。

原因是 Realm guest 的 `ioremap()` 会把 non-protected MMIO 标成 shared/decrypted
IPA alias；host 侧必须映射到同一个 shared alias。这个修改避免把 GPU MMIO
aperture 错误安装到 Realm private/base IPA view，是 single-VM trusted-GPU Realm
passthrough 能继续诊断的必要条件。

## 9. Firecracker：默认拒绝 Realm GPU Passthrough

`firecracker/Firecracker-CCA-MZH/src/vmm/src/builder.rs` 新增 fail-closed gate。

当 `realm_config` 与 `gpu_passthrough=true` 同时出现时，Firecracker 默认返回错误。
只有进程环境变量满足以下条件才允许启动：

```text
FC_ALLOW_TRUSTED_GPU_REALM=1
```

作用：

- 危险配置默认保持 fail-closed。
- 只有 passthrough runner 的 explicit smoke gate 会设置该环境变量。
- 防止手写 JSON 或误用 API 直接绕过当前不完整的 trusted-GPU model。

## 10. `opencca`：RMM HPA Validation And Mapping Leases

`opencca` 自身显示 nested submodule entry 变化，实际代码在 `tf-rmm` 和
`trusted-firmware-a`。

### 10.1 `tf-rmm`

修改点：

- `lib/smc/include/smc-rsi.h` 新增 `SMC_RSI_OPENCCA_GPA_TO_HPA` 和
  `SMC_RSI_OPENCCA_GPU_REVOKE`。
- `runtime/core/exit.c` 在 Realm RSI exit 中 dispatch 新命令。
- `runtime/include/rsi-handler.h` 声明 OpenCCA GPU RSI handlers。
- `runtime/rmi/realm.c` 在 Realm destroy 时调用
  `opencca_gpu_release_realm_mappings()`。
- `runtime/CMakeLists.txt` 纳入新的 runtime source。

作用是让Realm guest通过RSI请求RMM验证当前Realm IPA的所有权并取得HPA，同时
在unmap和Realm销毁时清理owner-scoped mapping leases。

### 10.2 `trusted-firmware-a`

TF-A不再包含OpenCCA GPU grant/revoke SMC或owner grant table。GPU页面继续是
普通Realm GPI；Host CPU隔离由现有GPT规则完成。Mali DMA按当前平台模型绕过
CPU侧GPC，直接使用guest写入Mali页表的HPA，因此TF-A不需要额外改变PAS/GPI。

## 11. 设计文档更新

### 11.1 `CCA_CONFIDENTIAL_GPU_SHARING_DESIGN.md`

新增内容集中在当前 trusted-GPU Realm 诊断结论：

- Realm GPU MMIO 应映射在 shared IPA alias，并通过 RMM `RTT_MAP_UNPROTECTED`
  建立。
- 最近诊断显示 IRQ delivery 已经足够支撑 scheduling 和 timeout diagnostics。
- 关键失败现象是 CSF 似乎没有读取到 guest CPU 写入的 Realm-private scheduler
  ringbuffer bytes。
- RMM GPA-to-HPA路径负责Realm所有权验证和mapping lease，不是GPU访问许可。
- 下一步应检查Mali page-table HPA、cache clean/invalidate和TLB时序，而不是增加
  OpenCCA device-access grant hook。

### 11.2 `PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md`

worklog 记录了：

- Realm MMIO mapping 修正。
- Firecracker fail-closed gate。
- passthrough runner 的 `--vm-realm-trusted-gpu-experimental`。
- shared vmshm Realm mode 仍阻断。

### 11.3 `RASPBERRY_PI_FLASH_RUNBOOK.md`

runbook 增加 DHCP 地址变化时的 LAN discovery 流程：

```bash
scripts/net/discover-opencca-hosts.sh --cidr 192.168.31.0/24
scripts/net/discover-opencca-hosts.sh --cidr 192.168.31.0/24 --update-docs
```

发现规则：

- 用 `/home/mzh/opencca-flash/flash.sh` 识别 Raspberry Pi flasher。
- 用 `/dev/pmthor`、`fb000000.gpu` 或 `opencca-pmthor` 识别 RK3588。
- 找到新 IP 后可批量更新 runbooks、skill snapshots、OpenCCA path defaults 和
  GPU run scripts 中的旧默认 IP。

## 12. 新增 Network Discovery 脚本和文档

`scripts/net/discover-opencca-hosts.sh` 是新增未跟踪脚本。

能力：

- 扫描一个或多个 `/24` CIDR。
- 并发探测 TCP/22。
- 用 `sshpass` 尝试默认账号密码。
- 识别 Raspberry Pi flasher。
- 识别 RK3588 target。
- 输出可直接 `export` 的环境变量。
- 使用 `--update-docs` 时替换旧 IP。

默认旧 IP：

```text
Pi:     192.168.31.52
RK3588: 192.168.31.18
```

`docs/start/OPENCCA_NETWORK_DISCOVERY_20260711.md` 记录了 discovery workflow 和
IP replacement path。但它仍包含“当前 Codex command sandbox cannot open network
sockets”的早期说明；提交前应确认这段是否仍准确。

`docs/start/OpenCCA自动化配置.md` 是中文硬件接线/自动化说明，覆盖 Rock 5B
Maskrom、Pi GPIO、USB-TTL serial 和 Xiaomi smart plug power control。提交前必须
处理其中的真实设备信息、外部图片 URL 和 smart plug token 示例，避免把敏感信息
提交到仓库。

## 13. Generated Passthrough Configs

`GPU-SFTP/firecracker-bins/configs/passthrough/generated/` 下有多份
`*-trusted-gpu-realm.json`，例如：

- `gpu-passthrough-realm-ringbuf-invalid-probe-20260612-161425-trusted-gpu-realm.json`
- `gpu-passthrough-realm-sync-only-cacheable-probe-20260612-155614-trusted-gpu-realm.json`
- `gpu-passthrough-rmm-gpa2hpa-smoke-20260612-104824-trusted-gpu-realm.json`

这些是 runner 生成的 diagnostic run artifacts，不应默认作为源码提交。更合理的
处理方式是：

- 加入 `.gitignore`；
- 或提交前清理；
- 或只挑选少量有文档价值的 sample config，并移动到明确的 docs/sample 位置。

## 14. 硬件验证结果

### 14.1 Pi Maskrom 和 SD Kernel Flash

当前代码存在后，已验证 Pi -> Maskrom -> SD kernel slot replacement 流程。

关键证据：

```text
Vid=0x2207,Pid=0x350b ... Maskrom
OPENCCA_KERNEL_STORAGE_ID=2
kernel image: opencca/snapshot/kernel-pmthor-rootfs-matched-extlinux.img
target LBA: 0x8000
```

刷写流程完成了：

- 识别 RK3588 已在 Maskrom。
- 传输 `rk3588_spl_loader_v1.16.113.bin`。
- 选择 Rockchip storage ID `2`，即 SD。
- 识别 Samsung SD storage 约 30436 MB。
- 写入 128 MiB kernel image 到 LBA `0x8000`。
- reset board。

启动后 RK3588 状态：

```text
Linux opencca-rock5b-rk3588 6.12.0-opencca-pmthor #1 SMP PREEMPT Thu Jun 11 23:04:28 CST 2026 aarch64 GNU/Linux
rootfs: /dev/mmcblk1p4 / ext4
GPU driver: pmthor
```

结论：SD kernel-only flash path 正常，未改变 rootfs 或 eMMC。

### 14.2 Shared GPU Virtualization Smoke

post-flash 后运行 two-client shared GLES 32 MiB smoke：

```text
Run ID: vmshm-2client-gles-32m-opencca-pmthor-20260711-151421
Result: GLES_PASS
```

本地日志：

```text
GPU-SFTP/log/shared/vmshm-2client/vmshm-2client-gles-32m-opencca-pmthor-20260711-151421
```

关键证据：

- `rootfs_payload_inject_done payload=gles-compute`
- `GLES affinity profile: auto-4cpu-split`
- CPU online mask 从 `0-3` 恢复到 `0-1`
- 两个 client 都使用 `Mali-G610 (Panfrost)`
- 两个 client 都使用 `OpenGL ES 3.1 Mesa 25.0.7-2`
- 两个 client 都输出 `COMPUTE_CHECK=PASS`
- 两个 client 都输出 `GPU_SMOKE_RESULT=PASS`
- 未发现 GPU fault、job timeout、panic、Oops、OOM、Firecracker killed 或
  software renderer 相关失败关键词。

32 MiB iteration averages：

```text
client0 avg iter_total: 29980.05 us
client1 avg iter_total: 29986.50 us
```

结论：普通 vmshm two-client shared GPU virtualization 在当前 SD boot 和 pmthor
host 环境下仍可通过。

## 15. 当前技术判断

当前变更把 trusted-GPU Realm path 推进到了更可诊断的状态，但还没有完成可用的
Realm GPU virtualization。

已经具备：

- 普通 passthrough/shared 路径仍可用。
- single-VM trusted-GPU Realm path 有 explicit smoke gate。
- shared proxy/client Realm GPU path 被明确阻断。
- Guest Panthor 已从“把 BO 变 shared”转向“保持 private + explicit sync +
  RMM-validated HPA”。
- Host KVM 已修正 Realm MMIO shared alias mapping。
- Firecracker 默认 fail-closed。

仍缺失的关键环节：

```text
guest Panthor map/unmap
  -> RSI GPA_TO_HPA / GPU_REVOKE
  -> RMM Realm IPA ownership check + mapping lease
  -> Mali page table contains HPA
  -> GPU DMA directly accesses DRAM without GPC lookup
```

下一步优先级是验证HPA是否正确写入所有层级Mali页表、非一致性cache维护和GPU
TLB失效时序。若威胁模型包含恶意Host，还必须另行实现可信GPU控制面，防止Host
通过MMIO把GPU当作DMA oracle；这与CPU侧GPT数据隔离是两个问题。

## 16. 提交前检查项

提交前建议处理：

1. 决定 `GPU-SFTP/firecracker-bins/configs/passthrough/generated/` 是否加入
   `.gitignore` 或清理。
2. 确认 `docs/start/OPENCCA_NETWORK_DISCOVERY_20260711.md` 中关于 sandbox network
   restriction 的说明是否仍准确。
3. 清理 `docs/start/OpenCCA自动化配置.md` 中的 smart plug token、真实 IP、外部图片
   URL 和硬件细节，避免提交敏感信息。
4. 为 `Linux-Guest-GPU`、`Linux-Host-GPU`、`firecracker/Firecracker-CCA-MZH` 和
   `opencca` 制作清晰 submodule commits，或固定到明确 revision。
5. 检查 `firecracker/firecracker-deps` 的 recursive submodule mapping 问题。
6. 不要把 `--vm-realm-trusted-gpu-experimental` 描述为 supported feature；它只是
   受控 smoke/diagnostic gate。

## 17. 2026-07-18 Realm GPU MMIO 硬件验证更新

本轮部署并验证了当前 Host KVM/RME MMIO 修改。关键纠正是：此前整机挂死测试实际
运行的是 2026-06-11 的旧 Host kernel，该版本的 `KVM_SET_MMIO_REGION` 对 Realm
仍走普通 `kvm_pgtable_stage2_map()`，并没有执行源码中的 shared alias/RMI 分支。

部署当前 Host Image 后，Host 日志确认：

```text
Mapping Realm MMIO shared alias:
  addr=fb000000 shared=40fb000000 size=200000
Realm MMIO map success
```

直接 PTY 运行完整 2 MiB MMIO 和正常 GPU IRQ 后，Realm 内结果为：

- GSI 92-94 三路 IRQ attach 成功；
- 读取真实 Mali-G610 ID `0xa867` 和 feature registers；
- GPA-to-HPA RSI 返回 Realm 页面 HPA，Mali页表使用这些HPA；
- CSF firmware v1.1.0、Panthor scheduler、DRM card/render node初始化成功；
- Realm进入 `/bin/sh`，Host保持在线。

4 KiB-only MMIO诊断也能读取GPU ID，但Panthor访问后续寄存器时出现
`AS_ACTIVE bit stuck`，随后错误清理路径触发Guest空指针；这属于诊断映射不完整的
预期限制，不是2 MiB block mapping问题。

最初rootfs中的Mesa userspace在GBM后报：

```text
MESA-LOADER: failed to retrieve device information
eglInitialize failed: EGL_NOT_INITIALIZED
```

原因不是Mesa版本不匹配，而是最小配置使用`init=/bin/sh`，没有挂载`/proc`和`/sys`；
Mesa无法通过sysfs关联DRM card/render node。手工挂载后再次运行得到：

```text
GL_RENDERER=Mali-G610 (Panfrost)
GL_VERSION=OpenGL ES 3.1 Mesa 25.0.7-2
COMPUTE_CHECK=PASS count=64
```

这证明GPU可以读取Realm-private命令和数据、完成CSF job并把结果写回Realm内存；
首次提交cache clean修复至少在该最小workload上有效。仍需补充更大规模重复workload、
teardown/error path，以及Host CPU访问同一Realm HPA被GPT拒绝的独立测试。

测试方法注意：Firecracker Guest serial应直接连接PTY；通过`tee`管道时
`BufferedStdout`可能不及时flush，不能把“无输出”误判为REC未启动。
