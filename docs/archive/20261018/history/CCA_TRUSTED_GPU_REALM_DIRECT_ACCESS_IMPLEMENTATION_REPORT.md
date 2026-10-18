# CCA Trusted GPU Realm Direct Access Implementation Report

> 历史记录或研究提案；不作为当前运行基线。最新实现见[当前基线](../../../shared/CURRENT_BASELINE.md)。历史分数、失败和未执行项按原版本理解。

Date: 2026-07-18

## 1. 文档目标

本文档总结当前 `RK3588/OpenCCA` 上 `trusted-GPU Realm` direct path 的设计和代码实现状态，重点回答以下问题：

- 如何利用 `GPC/GPT` 让 `Host CPU` 不能直接访问 `Realm` 的 GPU buffer memory；
- 如何让 `Mali GPU` 通过自己的 `GPU MMU` direct access 这些 private memory；
- `MMIO gate`、`Firecracker gate` 和 `Host KVM Realm MMIO shared alias` 当前做到了什么；
- 这些设计在代码中分别落在哪些文件；
- 已验证成果、已实现但待运行验证的测试，以及还没有解决的安全边界是什么。

本文档与 `docs/archive/20261018/research/CCA_CONFIDENTIAL_GPU_SHARING_DESIGN.md` 互补。后者描述总体设计，本文件侧重当前代码分析和实现成果。

## 2. 当前结论

当前实现已经从“把 GPU buffer 转成 Host shared/decrypted memory”推进到“Realm private memory + RMM validated HPA + Mali direct access”的模型。2026-07-18 的板端 `realm_host_access_probe` 证明：在 RK3588/OpenCCA 当前实现上，`Host CPU` 仍然可以读到 selected live Realm GPU HPA。这不是 GPU direct path 的错误，而是因为 RK3588 不支持真实 hardware `GPC/GPT` enforcement，OpenCCA 又把 `Realm PAS` 折叠为 `NS PAS`。

- `Realm CPU + Mali GPU` direct access 已验证；
- `Host CPU` runtime denial 不用 Host Linux software guard 伪造；
- “Host 不能访问 Realm memory” 作为设计目标，通过 simulated `GPT/GPC` model check 验证，而不是通过 RK3588 硬件 fault 验证。

已完成的关键成果：

1. `Realm` 中的 `Panthor` GPU buffer 不再通过 `set_memory_decrypted()` 转成 Host 可读 memory。
2. `Guest Panthor` 在建立 `Mali page table` 时，通过 `RSI_OPENCCA_GPA_TO_HPA` 请求 `RMM` 验证 `GPA/IPA` 属于当前 `Realm`，并返回对应 `HPA`。
3. `Mali page table` leaf entry 和 table descriptor 使用 `HPA`，让 `Mali GPU` 能通过自己的 `GPU MMU` direct access physical DRAM。
4. `RMM` 维护 per-`RD` mapping lease，防止同一个 active `HPA` 被另一个 `Realm` 绑定，同时在 unmap 和 `Realm` destroy 时清理 bookkeeping。
5. `Host KVM` 对 `Realm MMIO` 使用 `shared IPA alias` 和 `RTT_MAP_UNPROTECTED`，避免把 GPU register aperture 错误映射到 private IPA view。
6. `Firecracker` 默认拒绝 `realm_config + gpu_passthrough=true`，必须显式设置 `FC_ALLOW_TRUSTED_GPU_REALM=1`。
7. 已新增 `realm_host_access_probe`，用于在 guest workload hold 住 live mapping 时，从 `Host` 尝试读同一个 `HPA`。在 RK3588/OpenCCA 上该 probe 跑出 `HOST_READ_SUCCEEDED`，用于记录“底层未真实 enforcement”的实验 caveat。
8. 已新增 `scripts/check/check-opencca-gpt-design-denial.sh`，用于从代码设计上检查 `RMM -> EL3 GTSI -> TF-A GPT` 的 Realm GPI transition 是否存在，以及 RK3588/OpenCCA spoof/fold caveat 是否被显式识别。

已验证的功能成果：

- `Realm` guest 能读取真实 `G610` GPU ID；
- `Panthor` DRM 初始化和 `CSF firmware` 初始化已能完成；
- `Mesa/Panfrost` 能报告 `Mali-G610 (Panfrost)`；
- 4096-element `GLES compute` workload 已达到 `COMPUTE_CHECK=PASS`；
- `DESIGN_GPT_HOST_DENIAL_CHECK=PASS`，说明设计链路中 delegated granule 会进入 simulated `GPT_GPI_REALM`；
- `MMIO` 必须走 `shared IPA alias` 这一点已经由旧 Host kernel hang 和新映射成功路径间接确认。

仍需验证或未解决的部分：

- hardware `GPT/GPC` 对 arbitrary Host CPU load/store 的 denial 未达成；当前 RK3588/OpenCCA 代码中 `GPCCR_EL3/GPTBR_EL3` 是 dummy accessor，OpenCCA xlat path 还把 `Realm PAS` 当作 `NS`。
- 不再使用 Host Linux delegated-PFN software guard；运行时 probe 在 RK3588 上读成功是预期 caveat，不能作为设计失败。
- 当前设计不防御 malicious `Host kernel` 重新编程 `GPU MMIO`，把 unrestricted `Mali GPU` 当成 DMA oracle。
- 没有 `SMMU stage-2` 或 trusted scheduler 时，不支持 mutually distrusting Realms concurrent GPU sharing。

## 3. Threat Model 和设计边界

当前实现的目标曾是 data-plane confidential GPU passthrough：

```text
Realm CPU -> Realm translation + GPC/GPT -> Realm HPA -> allowed
Host CPU  -> NS translation    + GPC/GPT -> Realm HPA -> denied
Mali DMA  -> GPU MMU HPA, bypassing GPC  -> DRAM      -> allowed
```

这里的核心假设是：

```text
Mali normal-memory transactions are not rejected by the CPU-side GPC/GPT path.
```

设计上，`GPC/GPT` 应隔离 `Host CPU` 对 `GPT_GPI_REALM` granule 的访问；`Mali GPU` direct memory transaction 当前被视为不经过 CPU-side `GPC/GPT` enforcement path。`Mali GPU` 通过 guest 写入的 `HPA` page table 访问 DRAM。

baseline 代码和测试说明，Host CPU denial 这一行没有由硬件 `GPT/GPC` 实际成立。`realm_host_access_probe` 曾在 `COMPUTE_CHECK=PASS` 后对 selected workload HPA 读成功：

```text
run: GPU-SFTP/log/passthrough/perf/trusted-gpu-realm-host-deny-20260718-185436
selected_hpa=0x000000003573a000
COMPUTE_CHECK=PASS
realm_host_access_probe: HOST_READ_SUCCEEDED hpa=0x3573a000 bytes=4096 first_nonzero=2
```

因此，runtime probe 不是当前 “Host inaccessible” claim 的通过标准；它只是说明 RK3588/OpenCCA 底层没有真实硬件 enforcement。设计层验证改为：

```bash
scripts/check/check-opencca-gpt-design-denial.sh
```

当前输出：

```text
DESIGN_GPT_HOST_DENIAL_CHECK=PASS
NOTE=The CCA/GPT design path transitions delegated granules to Realm GPI, but RK3588/OpenCCA spoofs GPC registers and folds Realm PAS to NS, so this is a design/model check rather than hardware denial.
```

因此，当前模型不是新的 `GPT memory type`，也不是 `EL3 GPU grant table`。GPU buffer 仍然是普通 delegated `Realm granule`，安全属性来自：

- 设计上，hardware `GPT/GPC` 应让 `Host CPU` 不能直接 load/store `GPT_GPI_REALM` granule；
- 当前 RK3588/OpenCCA 只能通过 source-level simulated GPT model check 表达这个设计性质；
- `RMM` 只向当前 `Realm` 返回属于它自己的 `HPA`；
- `Guest Panthor` 只把这些 `RMM validated HPA` 写入 `Mali page table`；
- 一次运行中 whole GPU 只分配给一个 `Realm`。

## 4. RMM GPA-to-HPA Validation

代码位置：

- `opencca/tf-rmm/runtime/rsi/opencca_gpu.c`
- `opencca/tf-rmm/lib/smc/include/smc-rsi.h`
- `opencca/tf-rmm/runtime/core/exit.c`
- `opencca/tf-rmm/runtime/include/rsi-handler.h`
- `opencca/tf-rmm/runtime/rmi/realm.c`

`RMM` 新增两个 experimental `RSI`：

```text
SMC_RSI_OPENCCA_GPA_TO_HPA
SMC_RSI_OPENCCA_GPU_REVOKE
```

`handle_rsi_opencca_gpa_to_hpa()` 的职责是：

1. 验证 exchange array 是当前 `Realm` 的 IPA；
2. 从 array 读取 guest 填入的 `GPA/IPA`；
3. 对每个 `IPA` 调用 `realm_ipa_to_pa()`；
4. 确认 `IPA` 属于当前 `Realm` 的 valid mapping；
5. 返回对应 `PA/HPA`；
6. 调用 `opencca_gpu_track_mapping()` 记录 mapping lease。

`opencca_gpu_track_mapping()` 维护一个全局 mapping table：

```text
struct opencca_gpu_mapping {
    struct granule *rd;
    unsigned long hpa;
    unsigned short refcount;
    bool active;
};
```

这个 table 的安全意义不是“GPU permission table”，而是 address disclosure guard：

- 同一个 active `HPA` 只能被同一个 `RD` 绑定；
- 重复 map 会增加 refcount；
- 不同 `RD` 试图绑定相同 `HPA` 会返回 `RSI_ERROR_INPUT`；
- `Realm` destroy 时 `opencca_gpu_release_realm_mappings()` 清理所有残留 lease。

`handle_rsi_opencca_gpu_revoke()` 释放 lease。它不会改变 `GPT` state，也不会撤销硬件 GPU permission，因为当前平台没有给 `Mali GPU` 配置 per-page trusted permission table。

这个设计避免了一个容易误解的方向：不要再增加 `EL3 grant/revoke SMC` 作为 GPU data path 的核心权限机制。除非真实 `Mali transaction` 会消费那个 predicate，否则它只是 bookkeeping，不是 enforcement。

`opencca/trusted-firmware-a/lib/xlat_tables_v2/aarch64/xlat_tables_arch.c` 的 OpenCCA path 明确写着 `Realm PAS` 被当作 `NS` 处理，`opencca/trusted-firmware-a/opencca/include/opencca.h` 又把 `GPCCR_EL3/GPTBR_EL3` 读写伪装成 dummy register access。这说明当前 RK3588/OpenCCA 不能提供真正的 hardware `GPT/GPC` Host CPU denial；本仓库不再用 Host Linux policy 去掩盖这个事实。

## 5. Guest Panthor Memory Policy

代码位置：

- `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.c`
- `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.h`
- `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c`

`panthor_gem_realm_gpu_enabled()` 通过 `cc_platform_has(CC_ATTR_MEM_ENCRYPT)` 判断当前是否处于 Realm/confidential memory 环境。

`panthor_gem_realm_private_bo()` 定义了 Realm private BO：

```text
Realm GPU enabled
AND not imported dma-buf
AND not vmshm-backed
```

`panthor_gem_share_realm_gpu_pages()` 的名字保留了旧语义，但当前实现的实际行为是：

- 不调用 `set_memory_decrypted()`；
- 不把 private BO 转成 Host shared memory；
- 只 pin `drm_gem_shmem` pages，保证 backing pages 生命周期稳定；
- 标记 `realm_gpu_shared=true` 表示 “trusted local GPU usable”，不是 “Host shared readable”。

这点很关键：当前“shared”字段是历史命名，实际设计含义已经变成 `Realm private but GPU reachable through HPA page table`。

`panthor_gem_sync_realm_private_bo()` 负责 non-coherent cache maintenance：

- GPU 读 CPU 生成的数据前，调用 `arch_sync_dma_for_device()`；
- CPU 读 GPU 写回的数据前，调用 `arch_sync_dma_for_cpu()`；
- `panthor_mmu.c` 在 mapped BO range 上调用这些 helper。

当前成果是：minimal GLES compute workload 已经能通过。这说明至少对于短生命周期、少量 buffer、简单 compute 的路径，private BO + explicit cache sync + HPA page table 已经可工作。

## 6. Mali Page Table HPA Path

代码位置：

- `Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c`

`io-pgtable-arm.c` 是当前 direct path 的核心修改点。

### 6.1 GPA-to-HPA batch

`panthor_gpa_to_hpa_batch()` 将 `Guest GPA/IPA` 批量翻译成 `HPA`：

1. 将待翻译的 page-aligned `GPA` 写入 `panthor_gpa2hpa_page`；
2. 对 exchange page 做 `arch_sync_dma_for_device()`；
3. Realm 模式下调用 `opencca_rmm_gpa_to_hpa_batch()`，即 `rsi_opencca_gpa_to_hpa()`；
4. 非 Realm 诊断路径可走旧 `ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID`；
5. 调用 `arch_sync_dma_for_cpu()` 读取 `RMM` 写回的 `HPA`；
6. 可选写入 per-page GPA-to-HPA cache；
7. 打印 `[MZH][GPA2HPA][realm] gpa=... hpa=...` 诊断日志。

`panthor_realm_share_gpa2hpa_page()` 当前没有把 exchange page 转成 Host shared memory，而是保持 private page，并依赖 `RMM` protected mapping helper 读写。

### 6.2 Page table allocation 和 sync

`cfg_is_panthor_realm_direct()` 检测 `Panthor + Realm direct` 路径：

```text
cfg->alloc && cfg->free && panthor_rmm_gpa_to_hpa_enabled()
```

在这个路径下：

- page table pages 保持 private；
- 不走普通 DMA API bounce path；
- 使用 `arch_sync_dma_for_device(virt_to_phys(...))` 让 `Mali GPU` page-table walker 看到 CPU 写入的 table content。

### 6.3 Leaf PTE 和 block mapping

`arm_panthor_lpae_init_pte()` 不再把 `GPA` 写入 `Mali page table`，而是：

```text
GPA -> RSI_OPENCCA_GPA_TO_HPA -> HPA -> paddr_to_iopte(HPA)
```

`arm_panthor_lpae_init_2m_block_or_pages()` 会尝试 2 MiB block mapping。它先翻译 512 个 4 KiB page：

- 如果 `HPA` 2 MiB aligned 且连续，则写 block PTE；
- 如果不连续或未对齐，则 fallback 到 page/table mapping。

这避免了 Realm private pages 在 physical layout 不连续时错误地用一个 2 MiB block 覆盖错误 HPA range。

### 6.4 GPU_REVOKE

`panthor_realm_gpu_revoke_hpas()` 和 `panthor_realm_gpu_revoke_hpa_range()` 在 unmap/free page table 时调用 `RSI_OPENCCA_GPU_REVOKE`。

再次强调：`GPU_REVOKE` 释放的是 `RMM` mapping lease，不是硬件撤权。真实访问控制仍然来自 `GPT` 对 `Host CPU` 的 denial，以及运行期间 whole GPU assignment。

## 7. Host KVM Realm MMIO Shared Alias

代码位置：

- `Linux-Host-GPU/arch/arm64/include/asm/kvm_rme.h`
- `Linux-Host-GPU/arch/arm64/kvm/rme.c`
- `Linux-Host-GPU/arch/arm64/kvm/mmu.c`

GPU registers 不是 private memory。`Realm` guest 访问 GPU registers 时，应通过 shared/unprotected IPA alias。

当前实现新增 `realm_map_non_secure_phys()`：

```text
realm_map_non_secure_phys(realm, ipa, phys, map_size, memattr, memcache)
    -> rmi_rtt_map_unprotected(rd, ipa, level, desc)
```

`kvm_set_mmio_region()` 在 `kvm_is_realm(kvm)` 时走特殊路径：

1. 计算 `shared_bit = BIT_ULL(realm->ia_bits - 1)`；
2. 校验 guest base IPA 和 size 不越过 protected IPA view；
3. 将 guest register IPA 映射到 `addr | shared_bit`；
4. `phys` 使用真实 device physical address；
5. `memattr` 使用 `PTE_S2_MEMATTR(MT_S2_FWB_DEVICE_nGnRE)`；
6. 调用 `realm_map_non_secure_phys()`，底层使用 `RTT_MAP_UNPROTECTED`；
7. 支持 2 MiB chunk 或 4 KiB page chunk；
8. 映射后 flush TLB。

这解决了早期错误：旧 Host kernel 的 custom MMIO ioctl 用普通 KVM stage-2 mapper 处理 Realm MMIO，导致 GPU aperture 没有安装到 guest 实际访问的 shared alias 上，进而出现 whole Host hang 或 guest 无法正确读 register 的问题。

当前诊断结果说明：

- 2 MiB GPU MMIO aperture 作为 `RMI_RTT_MAP_UNPROTECTED` block descriptor 是可行的；
- 4 KiB-only MMIO diagnostic 能读到 GPU ID，但后续 `Panthor` 需要访问更多 register，所以 4 KiB 只适合定位，不是完整运行配置。

## 8. Firecracker Gate 和 MMIO Gate

代码位置：

- `firecracker/Firecracker-CCA-MZH/src/vmm/src/builder.rs`
- `scripts/run/run-host-vs-passthrough-gles-perf.sh`

`Firecracker` 现在对 `realm_config + gpu_passthrough=true` fail closed。

在 `build_microvm_for_boot()` 中：

```text
if is_realm && gpu_passthrough {
    require FC_ALLOW_TRUSTED_GPU_REALM=1
}
```

如果没有显式设置环境变量，启动会返回 `GpuPassthrough` error。这样可以防止手写 JSON 或 API 调用绕过当前还不完整的 trusted-GPU control-plane boundary。

runner 中的显式入口是：

```text
--vm-realm-trusted-gpu-experimental
```

该入口会：

- 生成临时 `realm_config`；
- 要求 tiny workload，不允许默认 sweep；
- 禁止和 `--vm-huge-pages-2m` 组合；
- 设置 `FC_ALLOW_TRUSTED_GPU_REALM=1`；
- 支持 diagnostic flags，例如 `--guest-panthor-sync-only-diag`、`--guest-panthor-ringbuf-read-probe`、`--realm-host-access-probe`。

`Firecracker` 还保留 diagnostic `MMIO gate`：

```text
FC_TRUSTED_GPU_REALM_SKIP_MMIO=1
FC_TRUSTED_GPU_REALM_MMIO_4K=1
FC_TRUSTED_GPU_REALM_SKIP_IRQ=1
```

这些不是正式安全机制，而是定位 `MMIO mapping`、`IRQ routing` 和 register aperture 问题的开关。

## 9. Host CPU Access Probe 和 Design Check

代码位置：

- `GPU-SFTP/tests/realm-host-access-probe/realm_host_access_probe.c`
- `scripts/build/build-realm-host-access-probe.sh`
- `scripts/run/run-host-vs-passthrough-gles-perf.sh`
- `scripts/check/check-opencca-gpt-design-denial.sh`

`realm_host_access_probe` 是 Host kernel module。它接收一个 page-aligned live `Realm HPA`：

```text
insmod realm_host_access_probe.ko hpa=0x...
```

probe 行为：

1. 校验 `hpa` page aligned 且 `pfn_valid()`；
2. 用 `pfn_to_page()` 找到 Host `struct page`；
3. 用 `vmap()` 建立 Host kernel VA；
4. 用 `copy_from_kernel_nofault()` 尝试读取一页；
5. 如果读 fault，则打印：

```text
realm_host_access_probe: HOST_READ_DENIED hpa=0x... ret=...
```

6. 如果读成功，则打印 `HOST_READ_SUCCEEDED` 和最多 64 bytes hex dump。

runner 集成逻辑：

1. `--realm-host-access-probe` 只能和 `--vm-realm-trusted-gpu-experimental` 一起使用；
2. guest `gles-compute-smoke` 增加 `--hold-after-check-sec`，默认 hold 20 秒；
3. Host runner 后台启动 VM；
4. 在 guest log 中等待 `[MZH][GPA2HPA][realm] ... hpa=0x...` 或 `[MZH][PANTHOR_KBO_MAP] ... first_iova_hpa=...`；
5. 抽取 latest live `HPA`；
6. 加载 `realm_host_access_probe.ko`；
7. 如果 selected `HPA` 出现 `HOST_READ_DENIED` 且没有 `HOST_READ_SUCCEEDED`，runtime probe 记为 `PASS`；
8. 如果出现 `HOST_READ_SUCCEEDED`，runtime probe 记为 `FAIL`，但在 RK3588/OpenCCA 上这是当前硬件/模拟 caveat 的预期结果，不等于 GPU direct path 失败。

构建方式：

```bash
./scripts/build/build-realm-host-access-probe.sh
```

当前本地已确认该脚本可以产出：

```text
GPU-SFTP/firecracker-bins/bin/realm_host_access_probe.ko
```

由于本地 `Linux-Host-GPU` 构建树缺 `Module.symvers`，`modpost` 会提示 unresolved symbol warning。脚本使用 `KBUILD_MODPOST_WARN=1` 继续产出 `.ko`。最终是否能加载，需要以 RK3588 当前运行内核为准。

建议验证命令：

```bash
REMOTE_HOST=192.168.31.18 REMOTE_PASS="${REMOTE_PASS:?set locally}" \
RUN_ID=trusted-gpu-realm-host-deny-$(date +%Y%m%d-%H%M%S) \
  ./scripts/run/run-host-vs-passthrough-gles-perf.sh \
  --vm-realm-trusted-gpu-experimental \
  --realm-host-access-probe \
  --host-rootfs-userspace \
  --skip-remote-build \
  --count 64 \
  --iterations 1 \
  --warmup 0 \
  --vm-timeout 180 \
  --host-timeout 180
```

runtime probe 的解释标准：

- VM log 中有 `COMPUTE_CHECK=PASS` 和 `GPU_SMOKE_RESULT=PASS`，说明 `Realm CPU + Mali GPU` 可以访问；
- 如果 `HOST_READ_SUCCEEDED`，说明 RK3588/OpenCCA 没有 runtime hardware `GPT/GPC` denial；
- 如果 `HOST_READ_DENIED`，只能说明当前平台或 kernel path 拒绝了这个读取，需要进一步区分硬件 fault、Linux policy 或 probe path failure；
- 没有 `Oops`、`panic`、`job timeout`、`GPU fault`。

2026-07-18 runtime probe 结果：

```text
run: GPU-SFTP/log/passthrough/perf/trusted-gpu-realm-host-deny-20260718-185436
VM renderer: Mali-G610 (Panfrost)
COMPUTE_CHECK=PASS
GPU_SMOKE_RESULT=PASS
selected_hpa=0x000000003573a000
HOST_READ_SUCCEEDED hpa=0x3573a000
RESULT: FAIL
```

设计层 Host denial check：

```bash
scripts/check/check-opencca-gpt-design-denial.sh
```

该脚本检查：

- `RMM` 是否存在 `SMC_RMM_GTSI_DELEGATE` 调用；
- `EL3 RMMD` 是否把 `RMM_GTSI_DELEGATE` 转到 `gpt_delegate_pas()`；
- TF-A GPT model 是否包含 `GPT_GPI_REALM`；
- RMM model/testbench 是否期待 delegate 后 `gpt == GPT_REALM`；
- RK3588/OpenCCA 是否显式 spoof `GPCCR_EL3/GPTBR_EL3`；
- RK3588/OpenCCA 是否显式把 `Realm PAS` 折叠成 `NS`；
- `Linux-Host-GPU` 是否没有残留 `realm_delegated` software guard。

当前输出为：

```text
DESIGN_GPT_HOST_DENIAL_CHECK=PASS
```

## 10. 已验证成果和证据链

当前成果可以分成三层。

### 10.1 GPU direct path 已跑通 minimal compute

`docs/archive/20261018/research/CCA_CONFIDENTIAL_GPU_SHARING_DESIGN.md` 记录当前 `Hardware Status On 2026-07-18`：

- `Realm` reads real `G610 ID 0xa867`；
- all three GPU IRQs attach to GSIs 92-94；
- `GPA-to-HPA RSI translation` supplies HPA leaves to `Mali page tables`；
- `CSF firmware v1.1.0` parsed and initialized；
- `Panthor scheduler` 和 DRM render node initialization complete；
- `Mesa` reports `Mali-G610 (Panfrost)`；
- 4096-element compute dispatch returns `COMPUTE_CHECK=PASS`。

这说明 data path 的最小闭环已经成立：

```text
Realm CPU private BO -> RMM validated HPA -> Mali page table -> GPU compute -> CPU validation
```

### 10.2 MMIO shared alias 修复已验证方向正确

旧问题中，whole Host hang 被定位到 Host kernel 对 Realm MMIO 使用了错误 mapper。当前 `kvm_set_mmio_region()` 已改为：

```text
guest MMIO IPA | shared_bit -> RTT_MAP_UNPROTECTED -> NS device PA
```

后续诊断显示：

- 4 KiB MMIO diagnostic 可以读 GPU ID；
- 2 MiB MMIO aperture 可以支持 `Panthor` 继续初始化；
- 问题不在 `GPC`、GPU IRQ 或 2 MiB `RMI` block descriptor 本身。

### 10.3 Host CPU denial 采用设计层 check，runtime probe 记录 caveat

`realm_host_access_probe` 是 runtime 诊断工具。它验证出 `Host CPU` 可以读 selected `Realm HPA`，说明 RK3588/OpenCCA 没有真正的 hardware `GPT/GPC` Host CPU denial。

当前不再采用 Host Linux software guard。设计层验证由 `scripts/check/check-opencca-gpt-design-denial.sh` 完成，它检查 simulated `GPT/GPC` model 中 delegated granule 是否进入 `GPT_GPI_REALM`，并显式记录 RK3588/OpenCCA 的 spoof/fold caveat。

当前可声称：

```text
Realm CPU and Mali GPU can access Realm GPU memory: PASS
Design/model GPT transition to Realm GPI: PASS
Runtime hardware GPT/GPC denial on RK3588/OpenCCA: FAIL / unsupported
```

## 11. 未解决问题和风险

### 11.1 Malicious Host control-plane 风险

当前 Host-denial property 只作为 design/model claim 成立，不等于完整 malicious Host security。

如果 Host kernel 是恶意的，并且仍能 program `GPU MMIO`，它可能：

- reset GPU；
- 替换 GPU page table base；
- submit malicious command stream；
- 让 unrestricted `Mali DMA` 读取 `Realm HPA`；
- 把 GPU 当成 DMA oracle 绕过 `Host CPU` 的 GPT denial。

因此，强 Host adversary 模型下还需要 trusted device control plane，例如：

- `EL3/RMM-owned GPU assignment`；
- `MMIO mediation`；
- Host 对 GPU register access 的可信封锁；
- GPU reset/reclaim protocol；
- 或有 `SMMU stage-2` 的 per-VM DMA isolation。

当前实现只满足：

```text
Functional property: Realm CPU and Mali can access Realm GPU memory.
Design/model property: delegated granules transition to GPT_GPI_REALM.
Deployment property: one Realm owns the whole GPU during a run.
```

不满足：

```text
Hardware GPT/GPC blocks arbitrary malicious Host CPU access.
Malicious Host cannot reprogram Mali to DMA Realm memory.
```

### 11.2 多 Realm shared GPU 不支持

没有 `SMMU stage-2` 或 trusted scheduler 时，无法安全支持 mutually distrusting `Realm` concurrent GPU sharing。

当前 `vmshm proxy/client` shared virtualization 是另一个 split-driver prototype，其 isolation 基于 `VMID`、`vmshm-object` 和 proxy session ownership；它不是本文所述 direct trusted-GPU Realm memory model。

### 11.3 Cache maintenance 和 workload 覆盖仍需扩大

minimal compute pass 只能证明短 workload。还需要覆盖：

- larger BO；
- repeated submit；
- teardown；
- error path；
- page-table free；
- GPU fault path；
- sync object writeback；
- CPU/GPU cache maintenance race；
- 2 MiB block fallback 和 fragmented HPA mapping。

## 12. GPU Ownership State Machine

要解决 malicious `Host` 重新编程 `GPU MMIO` 的问题，需要一个 Host 不能绕过的 trusted GPU ownership control plane。仅靠 `Firecracker gate`、Host driver unbind 或 Linux policy 不够，因为 malicious `Host kernel` 可以直接映射并写 `fb000000.gpu` register。

推荐的 state machine 是：

```text
IDLE
  -> ACQUIRE
  -> ASSIGNED
  -> RUNNING
  -> QUIESCE
  -> RESET_SCRUB
  -> RELEASE
  -> IDLE
```

各状态职责如下。

| State | Owner | 目标 |
| --- | --- | --- |
| `IDLE` | `Host`/platform | GPU 未分配给任何 `Realm`，Host 可以使用或保持 `pmthor` placeholder |
| `ACQUIRE` | `RMM/EL3` | 验证目标 `Realm`、阻止 Host driver、冻结 Host MMIO access、准备 IRQ/MMIO routing |
| `ASSIGNED` | `RMM/EL3` | whole GPU 归一个 `Realm`，Host 不应能 program GPU registers |
| `RUNNING` | `Realm` + trusted control plane | `Realm Panthor` 运行，GPU memory 只接受 `RMM validated HPA` |
| `QUIESCE` | trusted control plane | 停止 queue，等待 jobs idle，invalidate GPU TLB，阻止新 submit |
| `RESET_SCRUB` | trusted control plane | reset GPU，清理 firmware/shared interface/scheduler state，避免跨 owner 泄漏 |
| `RELEASE` | `RMM/EL3` | 释放 mapping lease，恢复 IRQ/MMIO ownership，GPU 回到 `IDLE` |

这个 state machine 需要两个 enforcement point：

1. `Host CPU memory isolation`：最终应由 `GPT/GPC` 让 Host direct load/store `Realm HPA` fault。当前 RK3588/OpenCCA 未提供这个硬件性质；prototype 只保留 design/model check，不使用 Host Linux delegated-PFN guard。
2. `GPU MMIO ownership isolation`：`Host` 在 `ASSIGNED/RUNNING` 期间不能直接写 GPU registers。否则 Host 可把 GPU 当 DMA oracle。

如果 RK3588 没有可由 `EL3/RMM` 控制的 device firewall / bus firewall / TZC / SMMU stage-2，那么这个 state machine 在 malicious Host threat model 下只能作为软件流程，不能提供强安全。那时准确边界应写成：

```text
Supported: honest-but-curious Host + whole-GPU exclusive assignment
Unsupported: malicious Host kernel with unrestricted physical MMIO access
```

真正的强方案优先级：

1. `SMMU stage-2`：让 GPU DMA 被 per-Realm stage-2 限制。这是最干净的标准方案，但当前 RK3588 path 没有可用 GPU `SMMU stage-2`。
2. `EL3/RMM-owned MMIO firewall`：在 `ASSIGNED/RUNNING` 期间从硬件上撤销 Host 对 GPU register aperture 的访问。
3. `MMIO mediation`：不把真实 GPU registers 直接暴露给 `Realm`，由 trusted monitor trap-and-emulate 或 whitelist register access。实现成本高，但能把 GPU reset/queue/page-table-base 等危险 register 纳入 policy。
4. `Trusted GPU proxy`：把 real `Panthor` owner 放进 trusted proxy Realm/secure component，client Realm 只提交经过验证的 high-level command。对 `Panthor CSF` command validation 工作量很大。

在当前代码状态下，Host CPU runtime probe 的读成功被记录为 RK3588/OpenCCA caveat。下一步如果继续沿 trusted GPU 方向推进，应把优先级放到扩大 data-plane 覆盖和设计 trusted GPU control plane；如果目标改成 malicious Host，则必须先确认 RK3588 是否存在 Host 不能绕过的 device firewall、memory controller firewall、TZC 或 `SMMU stage-2`。

## 13. 当前代码成果索引

| 领域 | 文件 | 当前作用 |
| --- | --- | --- |
| `RMM RSI ABI` | `opencca/tf-rmm/lib/smc/include/smc-rsi.h` | 定义 `SMC_RSI_OPENCCA_GPA_TO_HPA` 和 `SMC_RSI_OPENCCA_GPU_REVOKE` |
| `RMM handler` | `opencca/tf-rmm/runtime/rsi/opencca_gpu.c` | 验证 Realm IPA ownership，返回 HPA，维护 mapping lease |
| `RMM dispatch` | `opencca/tf-rmm/runtime/core/exit.c` | 在 `RSI` exit 中分发 OpenCCA GPU commands |
| `Realm destroy cleanup` | `opencca/tf-rmm/runtime/rmi/realm.c` | `Realm` 销毁时清理剩余 mapping lease |
| `Guest RSI wrapper` | `Linux-Guest-GPU/arch/arm64/include/asm/rsi_cmds.h` | 提供 `rsi_opencca_gpa_to_hpa()` 和 `rsi_opencca_gpu_revoke()` |
| `Guest RSI ID` | `Linux-Guest-GPU/arch/arm64/include/asm/rsi_smc.h` | 定义 guest-visible command IDs |
| `Guest BO policy` | `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.c` | Realm private BO 不 decrypt，显式 cache sync |
| `Guest BO state` | `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_gem.h` | 保存 `realm_gpu_shared`、pin state 等 |
| `Guest VM map sync` | `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c` | 对 mapped BO range 做 CPU/GPU cache sync |
| `Mali page table HPA` | `Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c` | GPA-to-HPA batch、HPA PTE、GPU_REVOKE、PT stats |
| `Host Realm MMIO ABI` | `Linux-Host-GPU/arch/arm64/include/asm/kvm_rme.h` | 声明 `realm_map_non_secure_phys()` |
| `Host RMI mapping` | `Linux-Host-GPU/arch/arm64/kvm/rme.c` | 实现 `RTT_MAP_UNPROTECTED` physical device mapping |
| `Host MMIO gate` | `Linux-Host-GPU/arch/arm64/kvm/mmu.c` | `KVM_SET_MMIO_REGION` 对 Realm 使用 shared IPA alias |
| `Firecracker gate` | `firecracker/Firecracker-CCA-MZH/src/vmm/src/builder.rs` | 默认拒绝 `realm_config + gpu_passthrough`，显式 env gate |
| `Runner gate` | `scripts/run/run-host-vs-passthrough-gles-perf.sh` | trusted-GPU Realm tiny smoke、MMIO/env gate、Host access runtime probe |
| `Host access probe` | `GPU-SFTP/tests/realm-host-access-probe/realm_host_access_probe.c` | Host kernel VA 读取 live Realm HPA，记录 runtime caveat |
| `Probe build` | `scripts/build/build-realm-host-access-probe.sh` | 构建并安装 `realm_host_access_probe.ko` |
| `Design check` | `scripts/check/check-opencca-gpt-design-denial.sh` | 静态检查 simulated `GPT/GPC` Host-denial 设计链路 |

## 14. 建议下一步

优先级从高到低：

1. 保留 `scripts/check/check-opencca-gpt-design-denial.sh` 作为 Host-denial 设计层 regression check。
2. 保留 `realm_host_access_probe` 作为 runtime caveat 记录工具，不把 RK3588 上的 `HOST_READ_SUCCEEDED` 当成 GPU direct path 失败。
3. 扩大 GLES workload：从 4096 elements 扩到 64 KiB、1 MiB、32 MiB，小步增加，观察 `GPA2HPA`、`PANTHOR_PT_STATS`、cache sync 和 teardown。
4. 专门测试 unmap/free path，确认 `GPU_REVOKE` lease cleanup 没有 leak。
5. 设计 trusted GPU control plane，解决 malicious Host 重新编程 `MMIO` 的风险。
6. 调研 RK3588 是否存在 Host 不能绕过的 device firewall / bus firewall / TZC / `SMMU stage-2`；如果没有，明确 malicious Host 不可纯软件解决。
7. 对 `realm_gpu_shared` 这类历史命名做后续清理，避免把 “GPU reachable” 误读成 “Host shared”。

## 15. 一句话总结

当前代码已经实现并验证了 `Realm private GPU memory` 经 `RMM validated HPA` 写入 `Mali page table` 后由 `GPU direct access` 的功能通路；`Host KVM` 和 `Firecracker` 已经加入 `MMIO shared alias` 与显式 experimental gate；`Host CPU` 对 live `Realm HPA` 的 runtime probe 在 RK3588/OpenCCA 上仍可读，这是硬件不支持真实 `GPC/GPT` enforcement 的预期 caveat。Host-denial claim 当前通过 simulated `GPT/GPC` design check 表达，而不是通过 Host Linux software guard。
