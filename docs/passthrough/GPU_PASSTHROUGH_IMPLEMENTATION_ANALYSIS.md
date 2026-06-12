# GPU Passthrough Implementation Analysis

本文档只分析本工作区里的 GPU 直通实现，不分析 vmshm、proxy/client 共享内存、GPU 虚拟化共享通信等内容。涉及 vmshm 的配置文件只在说明 `gpu_passthrough` 开关或 guest kernel 产物时顺带点名，不展开其协议。

## Scope

GPU 直通相关代码主要分布在三个仓库：

- `Linux-Host-GPU`
  - host KVM 增强：把 GPU MMIO 区间映射进 guest stage-2 页表。
  - host KVM 增强：给 guest 提供 `GPA -> HPA` SMCCC hypercall，让 guest panthor 能把 GPU 页表项写成真实 host physical address。
  - host `pmthor` 驱动：占用物理 GPU 设备资源，提供 `/dev/pmthor`，把物理 GPU IRQ 转成 eventfd，并实现 automask/resample 语义。
  - host kernel 构建和部署脚本。
- `firecracker/Firecracker-CCA-MZH`
  - Firecracker machine config 增加 `gpu_passthrough` 开关。
  - aarch64 FDT 生成 GPU 节点。
  - VM 启动时设置 GPU MMIO stage-2 映射。
  - VM 启动时打开 `/dev/pmthor`，注册 KVM irqfd/resamplefd，绑定 host IRQ eventfd。
  - VM 退出时清理 KVM irqfd 和 host `pmthor` IRQ session。
- `Linux-Guest-GPU`
  - guest `panthor` 驱动仍按真实 Mali GPU probe，但是 GPU VM 页表格式改成 panthor 专用的 `ARM_64_PANATHOR_LPAE_S1`。
  - guest 建 GPU 页表时不把 guest physical address 直接写入 GPU PTE，而是通过 SMCCC hypercall 批量把 GPA 翻译成 HPA，再把 HPA 写进 GPU leaf PTE、table descriptor 和 TTBR。
  - guest 为了让 CPU 还能递归维护这些写了 HPA 的 GPU 页表，维护 `HPA -> guest virtual table pointer` hash table。
  - guest VM_BIND map/unmap 路径强制按 4K page 粒度更新，避免把 guest 连续 GPA 误当成 host 连续 HPA。

运行侧相关文件：

- `GPU-SFTP/firecracker-bins/configs/passthrough/gpu-passthrough-vm-config.json`
- `GPU-SFTP/firecracker-bins/scripts/passthrough/run-gpu-passthrough-vm.sh`
- `GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/proxy-vm-config.json`
- `GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/client-vm-config.json`
- `scripts/deploy/deploy-host-kernel-and-test.sh`

## Commit Timeline

关键提交大致按实现层次展开：

- `Linux-Host-GPU`
  - `1a5eb20d5fe6` / `7e3df4d87300`, `finish mmio s2map`: 给 host KVM 增加 `KVM_SET_MMIO_REGION`，把 guest IPA 映射到同地址物理 GPU MMIO。
  - `21672ead598c` / `354e1eeb5d28`, `init gpa2hpa call,but don't have real func`: 开始在 host KVM/SMCCC 侧预留 `GPA_TO_HPA` hypercall 入口。
  - `4f0afb327956` / `44d143f6dd79`, `finish hypercall and gpa2hpa`: 实现 guest 传入 GPA 数组、host KVM 查询 memslot/PFN 并把 HPA 写回 guest 数组的 batch hypercall。
  - `5de83cff32fe` / `b16a200329c4`, `FINISH gpu passthrough`: 新增 `drivers/pmthor`，实现 `/dev/pmthor` 和 VFIO-style IRQ eventfd 接口。
  - `c73794e3f137`, `add irq clean`: 增加 IRQ session 清理、`VFIO_IRQ_CLEAN`、release 清理。
  - `3270dc60f41a`, `Stabilize pmthor GPU passthrough reset`: 增加硬件 quiesce/reset、IRQ enabled 状态机、单 owner 保护。
- `Linux-Guest-GPU`
  - `2d9e51d7a`, `hook map pages,but have not do real hypercall`: 在 guest panthor/io-pgtable 路径上开始接管 GPU map_pages。
  - `c67e1afcd`, `finish hypercall and gpa2hpa`: guest 侧增加 `ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID` 调用，把 GPA 翻译成 HPA。
  - `d0a676621`, `get hpa of ttbr for gpu vm`: GPU address-space TTBR 不再写 guest `virt_to_phys(pgd)`，而是写 host 返回的 TTBR HPA。
  - `458ea9b8d`, `modify the ttbr gpa_to_hpa`: 调整 TTBR GPA->HPA 转换逻辑。
  - `e1e96b0a1`, `finish hashtable for pte(hpa)->gva when panthor_map_pages`: 因为 GPU 页表 descriptor 里存的是 HPA，guest CPU 递归 walk/unmap/free 时不能再 `__va(HPA)`，所以增加 `HPA -> GVA` hash table。
  - `024bf8463`, `FINISH PASSTHROUGH`: 完成 panthor 专用 io-pgtable map/unmap/iova_to_phys/free 路径。
  - `647516453`, `Fix GPU Passthrough Bug When Run A Real GPU Task Like OpenGL-Smoke`: 修复真实 OpenGL/GLES 任务触发的 GPU 页表问题，重点强化 4K 粒度 map/unmap、batch GPA->HPA、HPA table descriptor 和 `HPA -> GVA` 递归维护。
- `firecracker/Firecracker-CCA-MZH`
  - `e8e70684`, `add gpu passthrough`: 初版 GPU FDT、MMIO、IRQ eventfd 绑定。
  - `5fa7b2f2`, `util 3stage`: `GpuPassthroughManager` 改成由 `Vmm` 持有，不再依赖 `Box::leak`。
  - `75360263`, `QUERY-IOCTL Finish`: `GpuPassthroughManager` 改成 `Option`，FDT GPU 节点只在拿到 GPU 时暴露。
  - `c924ee43`, `fix irq passthrough bug`: 增加 `gpu_passthrough` 配置开关，整理 irqfd/resamplefd 注册顺序和清理路径。

## High-Level Architecture

直通路径可以分成四块：

```text
host KVM MMIO path
  Firecracker KVM_SET_MMIO_REGION
  -> host KVM kvm_set_mmio_region()
  -> stage-2 map IPA 0xfb000000 -> PA 0xfb000000 as device memory

guest GPU page-table path
  guest panthor VM_BIND / kernel mapping
  -> ARM_64_PANATHOR_LPAE_S1 custom io-pgtable
  -> SMCCC GPA_TO_HPA batch hypercall
  -> host KVM translates guest GPA to host HPA
  -> guest writes HPA into GPU TTBR/table PTE/leaf PTE
  -> physical GPU page walker and DMA use real host physical memory

guest device discovery path
  Firecracker FDT create_gpu_node()
  -> guest sees gpu@fb000000
  -> guest panthor probes MMIO + job/mmu/gpu IRQs

host IRQ forwarding path
  physical GPU IRQ
  -> host pmthor IRQ handler
  -> trigger eventfd
  -> KVM irqfd
  -> guest GSI 92/93/94

guest EOI return path
  guest handles IRQ and EOI
  -> KVM resamplefd
  -> host pmthor unmask handler
  -> host physical IRQ re-enabled
```

核心思想是：MMIO 直通用 stage-2 device mapping，GPU 页表里写 host physical address，IRQ 直通用 KVM irqfd + resamplefd，而物理 GPU session 生命周期由 host `pmthor` 驱动守住。

## Host KVM: GPU MMIO Stage-2 Mapping

### UAPI

`Linux-Host-GPU/include/uapi/linux/kvm.h` 增加了自定义结构和 ioctl：

```c
struct kvm_mmio_region {
	__u64 guest_phys_addr;
	__u64 memory_size;
};

#define KVM_SET_MMIO_REGION _IOR(KVMIO, 0xb7, struct kvm_mmio_region)
```

`KVM_SET_IRQ_PASS` 也被定义过，但当前 GPU 直通实现实际使用的是 KVM irqfd/resamplefd，不走这个 `KVM_SET_IRQ_PASS` 路径。

### Firecracker kvm-ioctls Binding

`firecracker/firecracker-deps/kvm-bindings/src/arm64/bindings.rs` 增加 `kvm_mmio_region`：

```rust
pub struct kvm_mmio_region {
    pub guest_phys_addr: __u64,
    pub memory_size: __u64,
}
```

`firecracker/firecracker-deps/kvm-ioctls/src/kvm_ioctls.rs` 增加 ioctl 编码：

```rust
ioctl_ior_nr!(KVM_SET_MMIO_REGION, KVMIO, 0xb7, kvm_mmio_region);
```

`firecracker/firecracker-deps/kvm-ioctls/src/ioctls/vm.rs` 增加 `VmFd::set_mmio_region()`：

```rust
pub fn set_mmio_region(&self, guest_phys_addr: u64, memory_size: u64) -> Result<()> {
    let mmio_region = kvm_mmio_region {
        guest_phys_addr,
        memory_size,
    };
    ioctl_with_ref(self, KVM_SET_MMIO_REGION(), &mmio_region)
}
```

### Host KVM ioctl Handler

`Linux-Host-GPU/virt/kvm/kvm_main.c` 增加 `KVM_SET_MMIO_REGION` 分支：

```text
kvm_vm_ioctl()
  -> copy_from_user(struct kvm_mmio_region)
  -> kvm_vm_ioctl_set_mmio_region()
  -> kvm_arch_set_mmio_region()
```

`kvm_vm_ioctl_set_mmio_region()` 做基本校验：

- `guest_phys_addr != 0`
- `memory_size != 0`
- 地址和大小页对齐

然后进入 arch 层。

### arm64 Stage-2 Mapping

`Linux-Host-GPU/arch/arm64/kvm/arm.c` 新增：

```c
int kvm_arch_set_mmio_region(struct kvm *kvm,
			     struct kvm_mmio_region *mmio_region)
{
	return kvm_set_mmio_region(kvm, mmio_region);
}
```

`Linux-Host-GPU/arch/arm64/kvm/mmu.c` 的 `kvm_set_mmio_region()` 做真正映射：

```text
prot = R | W | DEVICE
addr = mmio_region->guest_phys_addr
size = mmio_region->memory_size
cur_phys = cur_addr
kvm_pgtable_stage2_map(pgt, cur_addr, cur_size, cur_phys, prot, ...)
kvm_flush_remote_tlbs(kvm)
```

这里是 identity mapping：guest IPA `0xfb000000` 映射到 host PA `0xfb000000`。GPU 寄存器访问不再从 userspace MMIO emulation 退出到 Firecracker，而是直接走 stage-2 device memory 映射访问真实 GPU MMIO。

## Host KVM: GPA to HPA Hypercall

GPU 直通不只需要 MMIO 和 IRQ。真实 GPU 的 MMU page walker 不理解 KVM stage-2，也不会把 guest 写进 GPU 页表的 GPA 再走一层 guest IPA -> host PA 翻译。GPU 页表 descriptor 里如果仍写 guest `virt_to_phys()` 得到的 GPA，物理 GPU DMA 时会把这个数当作 host physical address 使用，轻则访问错页，重则任务超时、MMU fault、MCU/CSF 初始化失败。

因此 host KVM 增加了一个受控的 `GPA -> HPA` hypercall：guest panthor 在构造 GPU 页表时，把需要写进 GPU 页表的 guest physical page frame 发给 host KVM，host KVM 根据当前 VM memslot 查到对应 PFN/HPA，再写回 guest 提供的数组。

### SMCCC Function ID

`Linux-Host-GPU/include/linux/arm-smccc.h` 和 `Linux-Guest-GPU/include/linux/arm-smccc.h` 都增加：

```c
#define ARM_SMCCC_KVM_FUNC_GPA_TO_HPA 64

#define ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID \
	ARM_SMCCC_CALL_VAL(ARM_SMCCC_FAST_CALL, ARM_SMCCC_SMC_64, \
			   ARM_SMCCC_OWNER_VENDOR_HYP, \
			   ARM_SMCCC_KVM_FUNC_GPA_TO_HPA)
```

它走 KVM vendor hypervisor service，function number 是 `64`。这是 guest kernel 和 host KVM 之间的私有接口，不经过 Firecracker userspace。

`Linux-Host-GPU/arch/arm64/include/uapi/asm/kvm.h` 还给 firmware feature bitmap 增加：

```c
KVM_REG_ARM_VENDOR_HYP_BIT_GPA_TO_HPA = 2,
```

`Linux-Host-GPU/arch/arm64/kvm/hypercalls.c` 的 `KVM_ARM_SMCCC_VENDOR_HYP_FEATURES` 会把这个 bit 暴露出去，`kvm_smccc_test_fw_bmap()` 也允许 `ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID` 被 KVM 处理。

### Hypercall ABI

guest 调用格式：

```text
x0 / func_id: ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID
x1: guest physical address of an array of u64
x2: count
return x0: SMCCC_RET_SUCCESS or SMCCC_RET_INVALID_PARAMETER
```

数组内容是输入输出复用：

```text
before hypercall:
  array[i] = GPA page base

after hypercall:
  array[i] = HPA page base
```

host 侧 `kvm_gpa_to_hpa()` 做的事：

```text
gpa_array_gpa = smccc_get_arg1(vcpu)
count = smccc_get_arg2(vcpu)
validate count 1..512
validate array GPA 8-byte aligned
validate the array stays within the mapped page
reject the array page if it is Realm private memory

for each element:
    kvm_read_guest(kvm, element_gpa, &current_gpa, 8)
    require current_gpa page-aligned
    reject current_gpa if it is Realm private memory
    pfn = gfn_to_pfn_prot(kvm, current_gpa >> PAGE_SHIFT, true, &writable)
    hpa = PFN_PHYS(pfn)
    kvm_write_guest(kvm, element_gpa, &hpa, 8)

return SMCCC_RET_SUCCESS
```

The last two checks are important for ARM CCA. `GPA_TO_HPA` is only valid for
normal VM memory and explicit shared/non-secure windows such as vmshm. It must
not translate Realm private guestmemfd pages into GPU-visible HPA, because the
physical GPU is not an RME Realm device and would DMA outside the private Realm
access model. In the current host kernel this is enforced with
`kvm_mem_is_private(kvm, gfn)` in
`Linux-Host-GPU/arch/arm64/kvm/hypercalls.c`.

当前 host handler 要求数组里的每个 `current_gpa` 是 page base。guest 如果原始地址有页内 offset，会先传 page base 给 host，收到 HPA page base 后自己把 offset OR 回去。

### Why Host Must Translate

guest kernel 能知道的是 GPA：

```text
guest virtual address
  -> guest kernel linear map / page allocator
  -> guest physical address
```

真实 GPU 需要的是 HPA：

```text
GPU page-table descriptor
  -> host physical address
  -> real DRAM bus address
```

KVM stage-2 只在 CPU 或 stage-2-aware guest memory access 路径上生效。外设 DMA 或 GPU 自己的 MMU page walker 看到的 GPU 页表内容不会自动再经过 KVM stage-2。这个实现选择让 host KVM 显式把 GPA 翻译成 HPA，再让 guest panthor 把 HPA 写进 GPU 页表，从而让物理 GPU 的 page walker 直接走真实 host physical memory。

### Batch Translation

guest 的 `panthor_gpa_to_hpa_batch()` 每次分配一个临时 page 作为 u64 数组，因此最大 batch 数等于：

```c
PAGE_SIZE / sizeof(u64) // 512
```

这和 host handler 的 `count > 512` 检查一致。batch 的用途是降低 map_pages 时每个 4K PTE 都单独 trap 到 KVM 的成本，尤其是真实 GLES/OpenGL workload 会频繁 VM_BIND 大量 buffer。

## Host Kernel Device: pmthor

### Build Integration

新增目录：

```text
Linux-Host-GPU/drivers/pmthor/
  Kconfig
  Makefile
  pmthor_drv.c
  pmthor_drv.h
  pmthor_regs.h
```

接入点：

- `Linux-Host-GPU/drivers/Kconfig`
  - `source "drivers/pmthor/Kconfig"`
- `Linux-Host-GPU/drivers/Makefile`
  - `obj-$(CONFIG_PMTHOR) += pmthor/`
- `Linux-Host-GPU/.config`
  - `CONFIG_PMTHOR=y`
- `Linux-Host-GPU/rk3588_fragment.config`
  - `CONFIG_PMTHOR=y`

`pmthor` 驱动的 `of_match_table` 匹配：

```c
{ .compatible = "rockchip,rk3588-mali" },
{ .compatible = "arm,mali-valhall-csf" },
```

host DTS 中的 SoC 级 GPU 节点来自 `Linux-Host-GPU/arch/arm64/boot/dts/rockchip/rk3588-base.dtsi`：

```dts
gpu: gpu@fb000000 {
	compatible = "rockchip,rk3588-mali", "arm,mali-valhall-csf";
	reg = <0x0 0xfb000000 0x0 0x200000>;
	interrupts = <GIC_SPI 92 IRQ_TYPE_LEVEL_HIGH 0>,
		     <GIC_SPI 93 IRQ_TYPE_LEVEL_HIGH 0>,
		     <GIC_SPI 94 IRQ_TYPE_LEVEL_HIGH 0>;
	interrupt-names = "job", "mmu", "gpu";
	status = "disabled";
};
```

这里的 `disabled` 是 base dtsi 的默认值。具体板级 DTS 会按硬件把 GPU 节点打开，例如：

- `Linux-Host-GPU/arch/arm64/boot/dts/rockchip/rk3588s-rock-5a.dts`
  - `&gpu { mali-supply = <&vdd_gpu_s0>; status = "okay"; };`
- `Linux-Host-GPU/arch/arm64/boot/dts/rockchip/rk3588-rock-5b.dts`
  - 同样通过 `&gpu { ... status = "okay"; };` 覆盖 base 默认值。

因此 host 侧能 probe 到 GPU 的实际条件是：板级 DTB 把 GPU 节点置为 `okay`，同时 `CONFIG_PMTHOR=y` 且 `pmthor` 的 compatible 匹配这个节点。

直通方案里，host 用 `pmthor` 占用这个硬件资源，不让 host DRM `panthor` 正常作为 host GPU 用户使用。guest 侧再由 Firecracker 生成自己的 FDT GPU 节点，让 guest `panthor` probe。

### Device State

`Linux-Host-GPU/drivers/pmthor/pmthor_drv.h` 定义了两个核心结构：

```c
struct pmthor_irq {
	int irq;
	unsigned long hwintid;
	const char *label;
	spinlock_t lock;
	bool masked;
	bool enabled;
	struct eventfd_ctx *trigger;
	struct virqfd *mask;
	struct virqfd *unmask;
};

struct pmthor_device {
	struct miscdevice miscdev;
	struct mutex owner_lock;
	bool opened;
	phys_addr_t phys_addr;
	void __iomem *iomem;
	struct pmthor_irq job_irq;
	struct pmthor_irq mmu_irq;
	struct pmthor_irq gpu_irq;
};
```

三路 IRQ 分别对应 GPU 的：

- `job`
- `mmu`
- `gpu`

### Probe Path

`pmthor_probe()` 负责：

```text
devm_kzalloc pmthor_device
mutex_init(owner_lock)
pmthor_clk_init()
pmthor_pm_init()
devm_platform_get_and_ioremap_resource()
pmthor_vfio_irq_init()
misc_register(/dev/pmthor)
platform_set_drvdata()
```

`pmthor_clk_init()` 获取并打开 GPU 相关 clock：

- unnamed core clock
- optional `stacks`
- optional `coregroup`

`pmthor_pm_init()` 调 `dev_pm_domain_attach()`，把 GPU power domain 拉起来。

`pmthor_vfio_irq_init()` 根据 DT interrupt names 获取三路 Linux IRQ：

```text
platform_get_irq_byname(..., "job")
platform_get_irq_byname(..., "mmu")
platform_get_irq_byname(..., "gpu")
request_irq(..., IRQF_NO_AUTOEN, pmthor_automasked_irq_handler, ...)
```

使用 `IRQF_NO_AUTOEN` 是关键：host probe 阶段只注册 IRQ handler，不立即打开物理 IRQ。只有 Firecracker 通过 `/dev/pmthor` 安装 trigger fd 后，pmthor 才 enable 这一路 IRQ。

### Misc Device and Ownership

`pmthor` 注册 `/dev/pmthor`：

```c
ptdev->miscdev.name = DRV_NAME; // "pmthor"
ptdev->miscdev.fops = &pmthor_misc_fops;
ptdev->miscdev.mode = 0666;
```

`pmthor_misc_open()` 做单 owner 保护：

```text
lock owner_lock
if opened: return -EBUSY
opened = true
unlock
pmthor_hw_quiesce(ptdev, "open")
```

这保证同一时间只有一个 Firecracker VM 拥有物理 GPU passthrough session。Firecracker 侧如果打开 `/dev/pmthor` 得到 `EBUSY`，会把 VM 当成无 GPU VM 启动，避免多 VM 抢同一物理 GPU。

`pmthor_misc_release()` 做 session 清理：

```text
pmthor_vfio_irq_release_session()
opened = false
```

### VFIO-Style IRQ ioctl

host `pmthor` 复用 `struct vfio_irq_set` 风格，Firecracker 侧手工构造同布局的 ioctl payload。

命令号：

```c
#define PMTHOR_IOCTL_SET_IRQS _IOW('P', 0x01, struct vfio_irq_set)
```

自定义扩展 flag：

```c
#define VFIO_IRQ_CLEAN (1 << 6)
```

支持的 action：

- `VFIO_IRQ_SET_ACTION_TRIGGER`
  - 安装或清理 physical IRQ -> trigger eventfd。
- `VFIO_IRQ_SET_ACTION_UNMASK`
  - 安装或清理 resamplefd -> unmask handler。
- `VFIO_IRQ_SET_ACTION_MASK`
  - 保留并实现了 mask virqfd/直接 mask，但 Firecracker 当前主路径重点用 trigger/unmask。
- `VFIO_IRQ_CLEAN`
  - 清理整个 session。

`pmthor_misc_ioctl()` 大致逻辑：

```text
copy vfio_irq_set header
if flags has VFIO_IRQ_CLEAN:
    pmthor_vfio_irq_release_session()
    return
select irq by index 0/1/2
if count == 0 && action == TRIGGER:
    pmthor_set_trigger(irq, -1)
if DATA_EVENTFD:
    copy fd after header
switch action:
    TRIGGER -> pmthor_set_trigger()
    MASK -> pmthor_set_irq_mask() or pmthor_mask()
    UNMASK -> pmthor_set_irq_unmask() or pmthor_unmask()
```

### IRQ Automask/Resample Model

这是当前 IRQ 直通最重要的设计。

#### Installing trigger

`pmthor_set_trigger(irq, fd)`：

```text
release old trigger
eventfd_ctx_fdget(fd)
irq->trigger = trigger
irq->masked = false
enable_irq()
irq->enabled = true
```

安装 trigger 的同时会打开 host 物理 IRQ，所以 Firecracker 必须最后安装 trigger。

#### Physical IRQ handler

`pmthor_automasked_irq_handler()`：

```text
lock
if irq->trigger && !irq->masked:
    disable_irq_nosync()
    irq->enabled = false
    irq->masked = true
    trigger = irq->trigger
unlock
if trigger:
    eventfd_signal(trigger)
```

物理 IRQ 一到，host 立即 automask 这一路 IRQ，只 signal 一次 trigger eventfd。后续是否重新打开，取决于 guest 完成处理后 KVM 触发 resamplefd。

#### Installing unmask event

`pmthor_set_irq_unmask(irq, fd)`：

```text
vfio_virqfd_enable(irq, pmthor_unmask_handler, ..., &irq->unmask, fd)
```

KVM signal resamplefd 后，`vfio_virqfd` 执行：

```text
pmthor_unmask_handler()
  -> pmthor_unmask()
```

`pmthor_unmask()`：

```text
lock
if irq->trigger:
    irq->masked = false
    enable_irq()
    irq->enabled = true
unlock
```

因此完整 IRQ 循环是：

```text
GPU physical IRQ
  -> host pmthor automask handler
  -> trigger eventfd
  -> KVM irqfd injects guest GSI
  -> guest panthor IRQ handler
  -> guest EOI
  -> KVM resamplefd
  -> host pmthor unmask handler
  -> enable host physical IRQ
```

### Hardware Quiesce and Reset

`pmthor_hw_quiesce()` 在 session 边界清理 GPU 状态：

```text
pmthor_hw_mask_and_clear_irqs()
write MCU_CONTROL = DISABLE
poll MCU_STATUS == DISABLED
clear GPU_IRQ_RESET_COMPLETED
write GPU_CMD = GPU_SOFT_RESET
poll GPU_INT_RAWSTAT & GPU_IRQ_RESET_COMPLETED
if timeout:
    write GPU_CMD = GPU_HARD_RESET
    poll reset completed again
pmthor_hw_mask_and_clear_irqs()
log MCU/GPU/JOB/MMU raw status
```

相关寄存器在 `pmthor_regs.h`：

```c
GPU_INT_RAWSTAT 0x20
GPU_INT_CLEAR   0x24
GPU_INT_MASK    0x28
GPU_CMD         0x30
MCU_CONTROL     0x700
MCU_STATUS      0x704
JOB_INT_*       0x1000...
MMU_INT_*       0x2000...
```

调用点：

- `/dev/pmthor` open 时：清理上一轮状态，给新 VM 一个干净 GPU。
- session release / clean 时：清理当前 VM 留下的 pending IRQ、MCU 和 reset 状态。
- driver remove 时：通过 `pmthor_vfio_irq_cleanup()` 释放 IRQ 和 session。

## Firecracker: Machine Config

`firecracker/Firecracker-CCA-MZH/src/vmm/src/vmm_config/machine_config.rs` 给 `MachineConfig` 增加：

```rust
#[serde(default)]
pub gpu_passthrough: bool,
```

默认值是 `false`。`MachineConfigUpdate` 也增加：

```rust
pub gpu_passthrough: Option<bool>,
```

`MachineConfig::update()` 会保留旧值或应用新值：

```rust
gpu_passthrough: update.gpu_passthrough.unwrap_or(self.gpu_passthrough)
```

这个开关直接控制三件 Firecracker/VMM 侧事情：

1. 是否打开 `/dev/pmthor` 并创建 IRQ passthrough manager。
2. 是否调用 `KVM_SET_MMIO_REGION` 映射 GPU MMIO。
3. 是否在 guest FDT 里暴露 `gpu@fb000000`。

guest GPU 页表的 GPA->HPA hypercall 不是这个 JSON 字段直接配置的；它由 guest kernel 的 panthor/custom io-pgtable 代码在 probe 和 VM_BIND 运行时触发。换句话说，`gpu_passthrough=true` 负责让 guest 能看到真实 GPU，而 `Linux-Guest-GPU` 的页表修改负责让真实 GPU DMA 到正确的 host memory。

`GPU-SFTP/firecracker-bins/configs/passthrough/gpu-passthrough-vm-config.json` 单 VM 直通配置里：

```json
"machine-config": {
  "vcpu_count": 1,
  "mem_size_mib": 512,
  "cpu_template": null,
  "gpu_passthrough": true,
  "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/firecracker.dtb"
}
```

多 VM 场景的配置里，当前是 proxy 开启 GPU，client 关闭 GPU：

```text
config/proxy-vm-config.json   -> gpu_passthrough: true
config/client-vm-config.json  -> gpu_passthrough: false
```

注意：这里仅说明直通开关，不分析这些文件里的 vmshm 字段。

## Firecracker: Vmm Owns the GPU Session

`firecracker/Firecracker-CCA-MZH/src/vmm/src/lib.rs` 增加模块：

```rust
pub mod gpu_passthrough;
pub mod pmthor;
```

`Vmm` 增加字段：

```rust
gpu_passthrough_manager: Option<GpuPassthroughManager>,
```

`Vmm::has_gpu_passthrough()`：

```rust
pub(crate) fn has_gpu_passthrough(&self) -> bool {
    self.gpu_passthrough_manager.is_some()
}
```

早期实现曾经用 `Box::leak(gpu_mgr)` 保持 eventfd 生命周期。现在 `GpuPassthroughManager` 被 `Vmm` 持有，生命周期和 VM 对齐，退出时可以显式 detach。

`Drop for Vmm`：

```text
self.stop(...)
if Some(gpu_passthrough_manager):
    gpu_passthrough_manager.detach_from_kvm(vm.fd())
```

这使得 trigger eventfd、resample eventfd、KVM irqfd、host pmthor virqfd 都有明确清理点。

## Firecracker: VM Build Path

`build_microvm_for_boot()` 里相关顺序：

```text
create KVM VM
memory_init()
create_vmm_and_vcpus()
attach other devices
if machine_config.gpu_passthrough:
    vmm.gpu_passthrough_manager = gpu_irq_init(&vmm.vm)?
configure_system_for_boot()
wrap Vmm in Arc<Mutex<_>>
if vmm.has_gpu_passthrough():
    gpu_mmio_init(&vmm.vm)?
start vcpus
```

这里有一个实现特点：IRQ manager 在 FDT 生成之前建立，因此 `configure_system_for_boot()` 可以通过 `vmm.has_gpu_passthrough()` 决定是否写 GPU node。MMIO mapping 在 VMM 被包装进 Arc 后、启动 vCPU 之前执行。只要 guest 开始运行前完成 stage-2 mapping 即可。

### Handling EBUSY

`gpu_irq_init()` 打开 `/dev/pmthor`：

```rust
let gpu_mgr = match GpuPassthroughManager::new("/dev/pmthor", 92) {
    Ok(gpu_mgr) => gpu_mgr,
    Err(e) if e.raw_os_error() == Some(libc::EBUSY) => {
        info!("GPU device is already owned by another VM; booting this VM without GPU");
        return Ok(None);
    }
    Err(e) => return Err(...)
};
```

如果 host `pmthor` 报 `EBUSY`，Firecracker 不强行启动失败，而是返回 `Ok(None)`，让这个 VM 不暴露 GPU。

`attach_to_kvm()` 如果遇到 `EBUSY`，也会尝试 detach 后返回 `Ok(None)`。

## Firecracker: GPU MMIO Mapping

`firecracker/Firecracker-CCA-MZH/src/vmm/src/builder.rs`：

```rust
fn gpu_mmio_init(vm: &Vm) -> Result<(), StartMicrovmError> {
    const GPU_MMIO_ADDR: u64 = 0xfb000000;
    const GPU_MMIO_SIZE: u64 = 0x200000;
    vm.fd()
        .set_mmio_region(GPU_MMIO_ADDR, GPU_MMIO_SIZE)
        .map_err(StartMicrovmError::GpuMmioInit)?;
    Ok(())
}
```

这和 guest FDT 的 `reg = <0x0 0xfb000000 0x0 0x00200000>` 一致。guest panthor 访问 `fb000000.gpu` MMIO 时，KVM stage-2 已经把该 IPA 映射到同地址 host PA 的 device memory。

## Firecracker: Guest FDT GPU Node

`firecracker/Firecracker-CCA-MZH/src/vmm/src/arch/aarch64/mod.rs` 给 `configure_system()` 增加参数：

```rust
has_gpu_passthrough: bool
```

`firecracker/Firecracker-CCA-MZH/src/vmm/src/arch/aarch64/fdt.rs` 的 `create_fdt()`：

```rust
if has_gpu_passthrough {
    create_gpu_node(&mut fdt_writer)?;
}
```

`create_gpu_node()` 写入：

```text
node name: gpu@fb000000
compatible: rockchip,rk3588-mali
reg: 0xfb000000 size 0x200000
interrupts:
  SPI 92 level-high
  SPI 93 level-high
  SPI 94 level-high
interrupt-names:
  job
  mmu
  gpu
status: okay
```

这让 guest Linux 的 panthor 驱动按标准 DT 方式 probe GPU。guest 不需要知道 host 的 `/dev/pmthor`，只看到一个真实的 Mali GPU MMIO region 和三路 IRQ。

现在生成的 FDT dump 是启动配置里的可选项：在 `machine-config.dump_fdt_path`
指定路径时写出 DTB，例如 `/root/GPU-SFTP/artifacts/dtb/firecracker.dtb`；
不配置时不写 dump。这样避免了 Firecracker 源码里硬编码旧的
top-level DTB dump 路径。

```rust
create_fdt(..., machine_config.dump_fdt_path.as_deref())
```

## Guest Kernel: Panthor GPU Page Tables

这是之前文档最容易漏掉、但对真实 GPU workload 最关键的一块。Firecracker 和 host KVM 把 GPU MMIO/IRQ 暴露给 guest 后，guest `panthor` 驱动确实可以像裸机一样 probe GPU；但当 GPU 开始跑真实任务时，GPU MMU page walker 读取的是 guest panthor 写进 GPU 页表的地址。这个地址必须是真实 HPA，而不是 guest GPA。

传统 panthor/io-pgtable 路径大致是：

```text
guest panthor maps GEM/BO pages
  -> sg_dma_address()/virt_to_phys() returns guest physical address
  -> io-pgtable writes GPA into GPU PTE/table descriptor/TTBR
  -> physical GPU treats that GPA as a real PA
  -> wrong memory is walked or DMAed
```

直通修复后的路径是：

```text
guest panthor maps GEM/BO pages
  -> panthor custom io-pgtable receives GPA
  -> guest calls KVM GPA_TO_HPA hypercall
  -> host KVM returns HPA
  -> guest writes HPA into GPU-visible page-table descriptors
  -> physical GPU walks real host memory
```

### Bug Mechanism and Fix

之前 IRQ/MMIO 直通修好以后，guest 里 `panthor` 能 probe 到 GPU，不代表真实 GPU task 一定能跑。probe 阶段主要验证的是 MMIO、IRQ、power/clock/firmware 初始化；真实 OpenGL/GLES workload 会进一步触发大量 buffer/heap/firmware/queue 的 VM_BIND 和 GPU MMU page-table walk。

这个 bug 的根因是地址语义错位：

```text
guest panthor wrote GPA into GPU page table
physical GPU interpreted that field as HPA
```

只要 GPU 访问到这些 PTE，就会把 guest physical address 当作真实总线地址。初始探测可能侥幸还没覆盖到复杂映射；真实任务一跑，shader buffer、heap chunk、queue、firmware data 等对象需要 GPU DMA，错误就会暴露。

最终修复不是单点改一个 PTE，而是把 GPU page-table walk 的所有 GPU-visible 地址都改成 HPA：

- `TTBR`: GPU address-space 根页表基址必须是 HPA。
- `table descriptor`: 每一级指向下一级页表页的 descriptor 必须是 HPA。
- `leaf PTE`: 指向 GEM/BO/heap/buffer page 的 leaf entry 必须是 HPA。
- `CPU shadow metadata`: guest CPU 递归维护页表时必须能从 HPA 找回 guest virtual table pointer。
- `mapping granularity`: VM_BIND map/unmap 必须按 4K 粒度翻译，不能把 guest 连续 GPA 当成 host 连续 HPA。

这也是 `Linux-Guest-GPU` 最新修复提交 `647516453` 的核心：真实任务失败不是 IRQ 链路的问题，而是 GPU 页表里仍有 GPA 或者 guest CPU 维护 HPA 页表时走错递归指针的问题。

### New io-pgtable Format

`Linux-Guest-GPU/include/linux/io-pgtable.h` 增加了 panthor 专用格式：

```c
enum io_pgtable_fmt {
	ARM_32_LPAE_S1,
	ARM_32_LPAE_S2,
	ARM_64_LPAE_S1,
	ARM_64_PANATHOR_LPAE_S1,
	ARM_64_LPAE_S2,
	...
};
```

`Linux-Guest-GPU/drivers/iommu/io-pgtable.c` 把这个格式接到新的 init fns：

```c
[ARM_64_PANATHOR_LPAE_S1] =
	&io_pgtable_arm_64_panthor_lpae_s1_init_fns,
```

注意枚举名里实际拼写是 `PANATHOR`，文档保留代码里的真实名字。

`Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c` 定义：

```c
struct io_pgtable_init_fns io_pgtable_arm_64_panthor_lpae_s1_init_fns = {
	.caps = IO_PGTABLE_CAP_CUSTOM_ALLOCATOR,
	.alloc = arm_64_panthor_lpae_alloc_pgtable_s1,
	.free = arm_panthor_lpae_free_pgtable,
};
```

它和普通 `ARM_64_LPAE_S1` 的区别不是 TCR/MAIR 基本格式，而是 ops 全部换成 panthor 版本：

```c
data->iop.ops = (struct io_pgtable_ops){
	.map_pages = arm_panthor_lpae_map_pages,
	.unmap_pages = arm_panthor_lpae_unmap_pages,
	.iova_to_phys = arm_panthor_lpae_iova_to_phys,
	.read_and_clear_dirty = arm_lpae_read_and_clear_dirty,
};
```

### Panthor Uses the Custom Format

`Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c` 的 `panthor_vm_create()` 不再分配普通 ARM LPAE S1：

```c
vm->pgtbl_ops =
	alloc_io_pgtable_ops(ARM_64_PANATHOR_LPAE_S1, &pgtbl_cfg, vm);
```

这意味着后面的 `panthor_vm_map_pages()` 虽然仍然从 sg-table 取 `sg_dma_address(sgl)`，但是 `ops->map_pages()` 已经进入 panthor 专用的 `arm_panthor_lpae_map_pages()`。所以真正的 GPA->HPA 转换不在 `panthor_vm_map_pages()` 表面，而藏在 custom io-pgtable ops 里。

### Guest Batch Hypercall Wrapper

`Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c` include 了：

```c
#include <linux/arm-smccc.h>
#include <linux/hashtable.h>
```

guest 发起 hypercall 的最小 wrapper 是：

```c
static long kvm_hypercall_gpa_to_hpa_batch(u64 addr_array, u64 count)
{
	struct arm_smccc_res res;

	arm_smccc_1_1_invoke(ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID,
			     addr_array, count, &res);

	return res.a0;
}
```

上层 `panthor_gpa_to_hpa_batch(gpa, stride, num_entries, hpas)` 做 batch 参数准备：

```text
alloc one page for u64 array
for i in num_entries:
    array[i] = (gpa + i * stride) & PAGE_MASK
flush_dcache_page(page)
wmb()
hypercall(page_to_phys(page), num_entries)
rmb()
for i in num_entries:
    hpas[i] = array[i] | original_page_offset
free page
```

这里传给 hypercall 的 `page_to_phys(page)` 仍然是 guest 物理地址。host KVM 用 `kvm_read_guest()` 读取这个数组，再用 `kvm_write_guest()` 把 HPA 写回数组，所以 guest 不需要把临时数组本身先翻译成 HPA。

单地址版本只是 batch 包装：

```c
static int panthor_gpa_to_hpa(phys_addr_t gpa, phys_addr_t *hpa)
{
	return panthor_gpa_to_hpa_batch(gpa, PAGE_SIZE, 1, hpa);
}
```

### Leaf PTE Writes HPA

普通 `__arm_lpae_init_pte()` 会直接：

```c
ptep[i] = pte | paddr_to_iopte(paddr + i * sz, data);
```

panthor 版本 `__arm_panthor_lpae_init_pte()` 改成：

```text
sz = ARM_LPAE_BLOCK_SIZE(lvl, data)
panthor_gpa_to_hpa_batch(paddr, sz, num_entries, hpas)
for each entry:
    ptep[i] = prot/type bits | paddr_to_iopte(hpas[i], data)
sync PTE if page-table walk is non-coherent
```

也就是说，`panthor_vm_map_pages()` 传下来的 `paddr` 是 GPA，最终写入 GPU leaf PTE 的地址字段是 HPA。

这是修复真实任务的核心之一：GPU shader/job 访问用户 buffer、BO、heap chunk 时，GPU MMU leaf PTE 指向真实 host memory，而不是 guest 视角的 pseudo physical memory。

### Table Descriptor Writes HPA

GPU page table 不只有 leaf PTE。多级页表里，上一级 table descriptor 指向下一级 page-table page。如果这里仍写 GPA，GPU page walker 连下一层页表都找不到。

普通 `arm_lpae_install_table()` 会写：

```c
new = paddr_to_iopte(__pa(table), data) | ARM_LPAE_PTE_TYPE_TABLE;
```

panthor 版本 `arm_panthor_lpae_install_table()` 改成：

```text
gpa = __pa(table)
hpa = panthor_gpa_to_hpa(gpa)
panthor_new = paddr_to_iopte(hpa, data) | ARM_LPAE_PTE_TYPE_TABLE
store_mapping(HPA address bits, guest virtual table pointer)
cmpxchg64_relaxed(ptep, curr, panthor_new)
sync PTE if needed
```

所以 GPU 看到的 table descriptor 指向 HPA，下一级页表页也能被真实 GPU page walker 继续读取。

### TTBR Writes HPA

address space 激活时，panthor 会把 `cfg->arm_lpae_s1_cfg.ttbr` 写到 GPU MMU AS 寄存器：

```c
transtab = cfg->arm_lpae_s1_cfg.ttbr;
panthor_mmu_as_enable(vm->ptdev, vm->as.id, transtab, transcfg,
		      vm->memattr);
```

普通 ARM LPAE S1 allocator 里 TTBR 是：

```c
cfg->arm_lpae_s1_cfg.ttbr = virt_to_phys(data->pgd);
```

panthor allocator 里改成：

```text
data->pgd = allocate pgd
gpa_ttbr = virt_to_phys(data->pgd)
ttbr_hpa = panthor_gpa_to_hpa(gpa_ttbr)
cfg->arm_lpae_s1_cfg.ttbr = ttbr_hpa
```

这保证 GPU MMU 的根页表基址本身也是 HPA。到这里，GPU page-table walk 的三个层次都变成了 HPA：

```text
TTBR/root pgd address: HPA
non-leaf table descriptor: HPA
leaf memory PTE: HPA
```

### HPA to GVA Hash Table

把 GPU-visible descriptor 改成 HPA 会引出一个新问题：guest CPU 维护页表时还要递归 walk、unmap、free 下级页表。普通代码可以用：

```c
#define iopte_deref(pte, d) __va(iopte_to_paddr(pte, d))
```

但 panthor PTE 里的地址字段现在是 HPA，不是 guest physical address。guest 内核不能 `__va(HPA)` 得到可用的 guest virtual pointer。

所以 `struct arm_lpae_io_pgtable` 增加：

```c
DECLARE_HASHTABLE(panthor_table_pte_map, 10);
```

并新增 mapping 结构：

```c
struct panthor_table_pte_mapping {
	u64 hpa;
	u64 gva;
	struct hlist_node node;
};
```

当安装下级 table descriptor 时：

```text
store_mapping(table_hpa_addr_bits, (u64)table_gva)
```

当 map/unmap/free/iova_to_phys 需要进入下一级页表时，不再用 `iopte_deref()`，而是：

```text
panthor_table_from_pte(data, pte, lvl, iova, op)
  -> hpa = pte & ARM_LPAE_PTE_ADDR_MASK
  -> lookup_mapping(hpa)
  -> return guest virtual table pointer
```

这些 panthor 专用路径都使用这个 hash table：

- `__arm_panthor_lpae_map()`
- `__arm_panthor_lpae_unmap()`
- `__arm_panthor_lpae_free_pgtable()`
- `arm_panthor_lpae_iova_to_phys()`

释放页表时，`__arm_panthor_lpae_free_pgtable()` 会根据当前 table 的 GPA 再查一次 HPA，然后 `remove_mapping()`，最后释放 guest page-table page，避免 hash table 留下悬挂的 HPA->GVA 记录。

### 4K Granularity for Real Workloads

`panthor_mmu.c` 里保留了传统 `get_pgsize()`，它会在合适时用 2M block mapping。但直通路径新增并实际使用：

```c
static size_t SZ_4K_get_pgsize(u64 addr, size_t size, size_t *count)
{
	*count = size / SZ_4K;
	if (*count == 0 && size > 0)
		*count = 1;
	return SZ_4K;
}
```

map 和 unmap 都改成调用 `SZ_4K_get_pgsize()`：

```text
panthor_vm_map_pages()
  -> pgsize = SZ_4K_get_pgsize(iova | paddr, len, &pgcount)
  -> ops->map_pages(... pgsize=4K, pgcount=N ...)

panthor_vm_unmap_pages()
  -> pgsize = SZ_4K_get_pgsize(iova + offset, size - offset, &pgcount)
  -> ops->unmap_pages(... pgsize=4K, pgcount=N ...)
```

原因是 guest 里一段连续 GPA 不保证对应 host 上连续 HPA。如果用 2M block PTE，guest 会把一个 2M GPA range 变成一个 2M GPU block mapping；但 host memslot 背后的 HPA 可能在 4K 粒度上不连续。强制 4K leaf PTE 后，每个 guest page 都单独 GPA->HPA，真实 GPU DMA 才不会跨到错误的 host physical page。

最新真实任务修复提交 `647516453` 也把 `panthor_vm_map_pages()` 的调试从简单打印 `paddr` 改成对比：

```text
sg_dma_address(sgl)
sg_phys(sgl)
page_to_phys(sg_page(sgl)) + sgl->offset
```

这用于确认 guest 内部 DMA address/physical address/page physical 的关系是否一致。即使它们一致，也只说明 guest 视角的 GPA 一致；GPU 页表最终仍需要 custom io-pgtable 把它转换成 HPA。

### End-to-End Memory Translation Chain

一次用户态 GPU buffer 映射到真实 GPU 的链路可以整理成：

```text
guest userspace / Mesa / DRM ioctl
  -> panthor VM_BIND
  -> panthor_vm_map_pages()
  -> sg_dma_address() obtains guest DMA/GPA
  -> ARM_64_PANATHOR_LPAE_S1 map_pages
  -> panthor_gpa_to_hpa_batch()
  -> SMCCC vendor hyp GPA_TO_HPA
  -> host KVM gfn_to_pfn_prot()
  -> HPA returned into guest array
  -> guest writes GPU leaf PTE with HPA
  -> GPU job executes and page walker/DMA accesses host DRAM
```

页表自身的 walk 链路是：

```text
GPU MMU AS register TTBR = HPA(root pgd)
  -> root pgd entry table descriptor = HPA(next table)
  -> lower table descriptor = HPA(next table)
  -> leaf PTE = HPA(buffer page)
```

guest CPU 维护这些页表的链路是：

```text
guest keeps root pgd GVA directly in data->pgd
  -> non-leaf PTE contains HPA
  -> lookup HPA in panthor_table_pte_map
  -> recover child table GVA
  -> continue map/unmap/free/iova_to_phys
```

这个设计相当于 guest 维护一套 “GPU-visible HPA page table”，同时在软件里保存足够的 `HPA -> GVA` shadow metadata，让 guest CPU 仍能修改和释放它。

## Firecracker: pmthor Userspace Wrapper

`firecracker/Firecracker-CCA-MZH/src/vmm/src/pmthor.rs` 是 `/dev/pmthor` 的 userspace wrapper。

它定义了和 host `pmthor` 对齐的 IRQ index：

```rust
pub enum IrqIndex {
    Job = 0,
    Mmu = 1,
    Gpu = 2,
}
```

定义与 `struct vfio_irq_set` 对齐的 header：

```rust
pub struct VfioIrqSet {
    pub argsz: u32,
    pub flags: u32,
    pub index: u32,
    pub start: u32,
    pub count: u32,
}
```

常量：

```rust
VFIO_IRQ_SET_DATA_EVENTFD = 1 << 2
VFIO_IRQ_SET_ACTION_UNMASK = 1 << 4
VFIO_IRQ_SET_ACTION_TRIGGER = 1 << 5
VFIO_IRQ_CLEAN = 1 << 6
PMTHOR_IOCTL_SET_IRQS = 0x40145001
```

提供的操作：

- `PmThorDevice::open(path)`
  - 打开 `/dev/pmthor`。
- `set_trigger(index, fd)`
  - 发送 `DATA_EVENTFD | TRIGGER`，让 host 物理 IRQ signal 这个 eventfd。
- `clear_trigger(index)`
  - 发送 `TRIGGER` + `count=0`，让 host 清 trigger。
- `set_unmask_event(index, fd)`
  - 发送 `DATA_EVENTFD | UNMASK`，让 host 监听 resamplefd。
- `clear_unmask_event(index)`
  - 发送 `DATA_EVENTFD | UNMASK` + `fd=-1`，让 host disable unmask virqfd。
- `clean_irq()`
  - 发送 `VFIO_IRQ_CLEAN`，清整个 pmthor IRQ session。

## Firecracker: GpuPassthroughManager

`firecracker/Firecracker-CCA-MZH/src/vmm/src/gpu_passthrough.rs` 是 IRQ 直通核心。

### Data Model

固定三路 IRQ：

```rust
const GPU_IRQS: [IrqIndex; 3] = [IrqIndex::Job, IrqIndex::Mmu, IrqIndex::Gpu];
```

每一路有一对 eventfd：

```rust
pub struct GpuIrqContext {
    trigger: EventFd,
    resample: EventFd,
    gsi: u32,
}
```

`trigger` 是去程：

```text
host physical IRQ -> trigger eventfd -> KVM irqfd -> guest GSI
```

`resample` 是回程：

```text
guest EOI -> KVM resamplefd -> host pmthor unmask handler
```

`GpuPassthroughManager` 持有：

```rust
pmthor: PmThorDevice,
irqs: Vec<GpuIrqContext>,
```

`new("/dev/pmthor", 92)` 为三路 IRQ 创建：

```text
job -> trigger/resample -> GSI 92
mmu -> trigger/resample -> GSI 93
gpu -> trigger/resample -> GSI 94
```

### Attach Sequence

`attach_to_kvm()`：

```text
pmthor.clean_irq()
for each irq:
    attach_irq()
```

`attach_irq()` 顺序非常关键：

```text
1. vm_fd.register_irqfd_with_resample(trigger, resample, gsi)
2. pmthor.set_unmask_event(host_irq, resample_fd)
3. pmthor.set_trigger(host_irq, trigger_fd)
```

原因：

- `set_trigger()` 会 enable host physical IRQ。
- 一旦 physical IRQ 到来，host handler 会 automask/disable 该 IRQ。
- 如果 KVM irqfd 或 pmthor unmask event 尚未准备好，guest EOI 无法通过 resamplefd 回来，host IRQ 可能被 mask 后无法恢复。

因此必须先接好 KVM 去程和 resample 回程，最后才打开 host trigger。

失败回滚也按已完成资源反向清理：

- 如果 `set_unmask_event()` 失败：unregister KVM irqfd。
- 如果 `set_trigger()` 失败：clear unmask event，再 unregister KVM irqfd。
- 如果某一路 attach 失败：`detach_attached_irqs()` 清理此前成功的 IRQ。

### Detach Sequence

`detach_from_kvm()`：

```text
for each irq:
    clear_unmask_event()
    clear_trigger()
    unregister_irqfd()
pmthor.clean_irq()
```

每一步的理由：

1. 先清 unmask event，阻止 late guest EOI/resample 在退出过程中重新 enable host IRQ。
2. 再清 trigger，阻止物理 GPU IRQ 继续 signal trigger eventfd。
3. 再 unregister KVM irqfd，释放 KVM 对 eventfd 的引用，停止向 guest 注入。
4. 最后 clean 整个 pmthor session，确保 host virqfd、trigger、硬件状态都释放。

## IRQ End-to-End Chain

当前完整链路：

```text
GPU physical IRQ
  -> host Linux invokes pmthor_automasked_irq_handler()
  -> pmthor disables/masks host IRQ
  -> eventfd_signal(trigger)
  -> KVM irqfd injects guest GSI 92/93/94
  -> guest panthor IRQ handler runs
  -> guest EOI
  -> KVM signals resamplefd
  -> host pmthor_unmask_handler()
  -> pmthor enables host IRQ again
```

三路对应：

```text
host pmthor IrqIndex::Job -> guest GSI 92 -> FDT interrupt-name "job"
host pmthor IrqIndex::Mmu -> guest GSI 93 -> FDT interrupt-name "mmu"
host pmthor IrqIndex::Gpu -> guest GSI 94 -> FDT interrupt-name "gpu"
```

这是一个 level IRQ 的 VFIO-style automask/resample 模型，而不是简单的 edge event 转发。

## Why irqfd + resamplefd Before Host Trigger

`pmthor.set_trigger()` 会真正 enable host physical IRQ。trigger 一装，GPU IRQ 就可能马上到来。

如果顺序错误，例如：

```text
set_trigger()
register_irqfd_with_resample()
set_unmask_event()
```

可能发生：

```text
1. set_trigger() enable host IRQ
2. physical IRQ fires
3. pmthor handler disables/masks host IRQ
4. handler signals trigger eventfd
5. KVM has not registered irqfd/resamplefd yet, or pmthor has not registered unmaskfd yet
6. guest EOI return path is absent
7. host IRQ remains masked/disabled
```

因此当前正确顺序是：

```text
register KVM irqfd + resamplefd
register pmthor unmask event using resamplefd
register pmthor trigger event and enable host IRQ
```

这样物理 IRQ 一旦进来，去程和回程都已经存在。

## Why VM Exit Clears Both KVM and pmthor State

这里有三边状态：

- Firecracker owns `EventFd` objects.
- KVM holds irqfd references to trigger/resample.
- host `pmthor` holds eventfd_ctx/virqfd references and host IRQ mask/enable state.

只清 KVM 不清 pmthor：

```text
host physical IRQ may still fire
pmthor still masks host IRQ and signals trigger
KVM no longer injects to guest
host IRQ can stay disabled without guest EOI return
```

只清 pmthor 不清 KVM：

```text
KVM still holds irqfd references
late/stale trigger events can still inject
eventfd lifetimes are extended unexpectedly
```

只依赖 file close/release 不够稳，因为 VMM 退出包含 vCPU stop、KVM fd teardown、eventfd drop、pmthor file release 等多个对象析构。显式 detach 在 `Vmm::Drop` 里按已知关系拆干净，避免退出阶段资源顺序不确定。

## Runtime Files

### Single Passthrough VM

`GPU-SFTP/firecracker-bins/configs/passthrough/gpu-passthrough-vm-config.json`：

```json
{
  "boot-source": {
    "kernel_image_path": "/root/GPU-SFTP/firecracker-bins/kernels/passthrough/Image",
    "boot_args": "console=ttyS0 root=/dev/vda rw rootfstype=ext4 init=/bin/sh"
  },
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 512,
    "cpu_template": null,
    "gpu_passthrough": true,
    "dump_fdt_path": "/root/GPU-SFTP/artifacts/dtb/firecracker.dtb"
  }
}
```

这里的 `Image` 必须来自包含 `Linux-Guest-GPU` panthor GPA->HPA 页表修改的 guest kernel。否则 VM 即使能看到 GPU MMIO/IRQ，也可能在真实 GPU task 建页表时把 GPA 写进 GPU descriptor。

`GPU-SFTP/firecracker-bins/scripts/passthrough/run-gpu-passthrough-vm.sh`：

```sh
exec "${BINS_DIR}/bin/firecracker" --no-api --no-seccomp --config-file "${BINS_DIR}/configs/passthrough/gpu-passthrough-vm-config.json"
```

### Proxy/Client Example

`GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/proxy-vm-config.json`:

```json
"gpu_passthrough": true
```

`GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/client-vm-config.json`:

```json
"gpu_passthrough": false
```

这里的重点是只有 proxy VM 拿物理 GPU。client VM 不打开 `/dev/pmthor`，不映射 GPU MMIO，也不暴露 GPU FDT 节点。该文档不分析这些配置中的 vmshm 设备。

## Build and Deploy Path

### Host Kernel

`scripts/build/build-host-kernel-payload.sh`：

```text
make CROSS_COMPILE=aarch64-linux-gnu- ARCH=arm64 -j${JOBS}
copy arch/arm64/boot/Image -> GPU-SFTP/linux-host-kernel/Image
make modules_install -> GPU-SFTP/linux-host-kernel/modules-staging
```

这用于把含有 `CONFIG_PMTHOR=y`、KVM MMIO ioctl、pmthor driver 的 host kernel 打包到 `GPU-SFTP`。

### Guest Kernel

`scripts/build/build-guest-vmshm-kernels.sh` 会构建 guest kernel image，并安装 proxy/client kernel 产物：

```text
GPU-SFTP/firecracker-bins/kernels/shared/client/Image
GPU-SFTP/firecracker-bins/kernels/shared/proxy/Image
```

单 VM passthrough config 当前使用：

```text
GPU-SFTP/firecracker-bins/kernels/passthrough/Image
```

这个 guest `Image` 需要包含：

- `ARM_64_PANATHOR_LPAE_S1`
- guest `ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID`
- panthor custom io-pgtable map/unmap/free/iova_to_phys
- TTBR/table descriptor/leaf PTE 的 GPA->HPA 转换
- `HPA -> GVA` page-table hash table
- 4K 粒度 VM_BIND map/unmap

这些是运行真实 GPU workload 的必要条件，和 host `pmthor`/Firecracker IRQ 直通是不同层面的直通修改。

### Firecracker

`scripts/build/build-firecracker-runtime.sh`：

```text
cargo build --release --target aarch64-unknown-linux-musl --bins --examples
```

`scripts/build/build-firecracker-runtime.sh` 会构建 Firecracker 并安装到：

```text
GPU-SFTP/firecracker-bins/bin/firecracker
```

该 top-level 脚本同时构建 vmshm broker，但这属于共享虚拟化链路，不是本文重点。

### Host Deploy and Passthrough Test

`scripts/deploy/deploy-host-kernel-and-test.sh` 做完整远端流程：

```text
build Linux-Host-GPU
build Firecracker
rsync GPU-SFTP to remote
install host Image to /boot/vmlinuz-6.12.0-opencca-wip
reboot remote
wait for SSH
verify /dev/pmthor exists
run run-gpu-passthrough-vm.sh several times
grep guest log for "Initialized panthor"
collect dmesg/proc/interrupts/run logs
```

测试里还会检查 passthrough config 必须包含：

```text
"gpu_passthrough": true
```

成功标准主要是 guest 日志出现 panthor 初始化成功，且没有：

```text
Failed to boot MCU
probe with driver panthor failed
```

## End-to-End Boot Sequence

以单 VM passthrough 为例：

```text
remote host boots Linux-Host-GPU
  -> pmthor probes physical GPU node
  -> clocks/power/iomem/IRQ registered
  -> /dev/pmthor exists, IRQs requested but disabled

Firecracker starts with gpu_passthrough=true
  -> MachineConfig enables GPU path
  -> gpu_irq_init opens /dev/pmthor
  -> pmthor open quiesces GPU hardware
  -> GpuPassthroughManager creates trigger/resample eventfds
  -> attach_to_kvm cleans previous IRQ session
  -> KVM irqfd/resamplefd registered for GSI 92/93/94
  -> pmthor unmask virqfd registered
  -> pmthor trigger fd registered, host physical IRQ enabled

Firecracker configures guest
  -> FDT includes gpu@fb000000
  -> KVM_SET_MMIO_REGION maps 0xfb000000-0xfb1fffff as device memory
  -> vCPUs start

guest Linux boots
  -> sees gpu@fb000000
  -> panthor probes MMIO and interrupts job/mmu/gpu
  -> panthor creates GPU/MCU VM objects with ARM_64_PANATHOR_LPAE_S1
  -> guest io-pgtable allocates root pgd
  -> guest asks host KVM for root pgd HPA through GPA_TO_HPA hypercall
  -> GPU MMU TTBR is programmed with HPA(root pgd)
  -> panthor maps firmware/heap/buffer pages
  -> guest batch-translates GPA pages to HPA pages
  -> GPU leaf PTEs and table descriptors contain HPA
  -> panthor initializes MCU/CSF
  -> GPU is usable in guest

VM exits
  -> Vmm::Drop stops vCPUs
  -> GpuPassthroughManager clears pmthor unmask/trigger
  -> KVM irqfd unregistered
  -> pmthor clean session
  -> pmthor hardware quiesce/reset
  -> /dev/pmthor release clears opened owner flag
```

## Important Invariants

当前代码依赖这些不变量：

1. 只有 `gpu_passthrough=true` 的 VM 才能尝试 GPU 直通。
2. `/dev/pmthor` 单 owner，第二个打开者得到 `EBUSY`。
3. GPU MMIO FDT `reg`、Firecracker `GPU_MMIO_ADDR/SIZE`、host KVM stage-2 mapping 三者必须一致：
   - base `0xfb000000`
   - size `0x200000`
4. guest FDT interrupts、Firecracker GSI、host pmthor IRQ index 必须一致：
   - job: `92`
   - mmu: `93`
   - gpu: `94`
5. attach 顺序必须是 KVM irqfd/resamplefd -> pmthor unmask -> pmthor trigger。
6. host physical IRQ handler 必须 automask，然后等 resamplefd 再 unmask。
7. detach 必须同时清 pmthor 和 KVM 状态。
8. session open/release 必须 quiesce/reset GPU，避免上一轮 guest 状态污染下一轮。
9. guest GPU page table descriptor 里 GPU 可见的地址必须是 HPA，不是 GPA。
10. guest `ARM_SMCCC_VENDOR_HYP_GPA_TO_HPA_FUNC_ID` 和 host KVM function id/ABI 必须一致：
   - function number `64`
   - `x1 = GPA of u64 array`
   - `x2 = count`
   - array in-place 从 GPA page base 变成 HPA page base
11. host `kvm_gpa_to_hpa()` 当前要求数组里的 GPA page-aligned，guest 负责传 page base 并在返回后恢复页内 offset；CCA Realm 下还必须拒绝 private GPA，只允许 normal/shared GPA 进入 GPU PTE。
12. GPU 页表的 TTBR、non-leaf table descriptor、leaf PTE 三者都必须写 HPA；只修 leaf PTE 不够。
13. guest CPU 维护 panthor 页表时不能对 HPA 使用 `__va()`，必须通过 `panthor_table_pte_map` 做 `HPA -> GVA` lookup。
14. guest panthor VM_BIND map/unmap 必须按 4K 粒度处理，不能把 guest 连续 GPA 假设成 host 连续 HPA。

## What Is Not Part of Passthrough Here

本文没有分析：

- vmshm broker 协议
- vmshm guest FDT 节点
- proxy/client 共享内存窗口
- GPU proxy/client 驱动的 ioctl 转发
- 多 VM GPU 虚拟化共享通信
- Mesa/panthor userspace 虚拟化适配

这些属于 GPU 虚拟化共享方案，不是本文的物理 GPU passthrough 直通路径。

## Key Files Index

Host kernel:

- `Linux-Host-GPU/include/uapi/linux/kvm.h`
- `Linux-Host-GPU/include/linux/arm-smccc.h`
- `Linux-Host-GPU/virt/kvm/kvm_main.c`
- `Linux-Host-GPU/arch/arm64/kvm/arm.c`
- `Linux-Host-GPU/arch/arm64/kvm/mmu.c`
- `Linux-Host-GPU/arch/arm64/kvm/hypercalls.c`
- `Linux-Host-GPU/arch/arm64/include/uapi/asm/kvm.h`
- `Linux-Host-GPU/arch/arm64/include/asm/kvm_mmu.h`
- `Linux-Host-GPU/drivers/pmthor/pmthor_drv.c`
- `Linux-Host-GPU/drivers/pmthor/pmthor_drv.h`
- `Linux-Host-GPU/drivers/pmthor/pmthor_regs.h`
- `Linux-Host-GPU/drivers/pmthor/Kconfig`
- `Linux-Host-GPU/drivers/pmthor/Makefile`
- `Linux-Host-GPU/arch/arm64/boot/dts/rockchip/rk3588-base.dtsi`
- `scripts/build/build-host-kernel-payload.sh`

Guest kernel:

- `Linux-Guest-GPU/include/linux/io-pgtable.h`
- `Linux-Guest-GPU/include/linux/arm-smccc.h`
- `Linux-Guest-GPU/drivers/iommu/io-pgtable.c`
- `Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c`
- `Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_mmu.c`
- `scripts/build/build-guest-vmshm-kernels.sh`

Firecracker:

- `firecracker/firecracker-deps/kvm-bindings/src/arm64/bindings.rs`
- `firecracker/firecracker-deps/kvm-ioctls/src/kvm_ioctls.rs`
- `firecracker/firecracker-deps/kvm-ioctls/src/ioctls/vm.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/vmm_config/machine_config.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/builder.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/lib.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/pmthor.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/gpu_passthrough.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/arch/aarch64/mod.rs`
- `firecracker/Firecracker-CCA-MZH/src/vmm/src/arch/aarch64/fdt.rs`
- `scripts/build/build-firecracker-runtime.sh`

Runtime/test:

- `GPU-SFTP/firecracker-bins/configs/passthrough/gpu-passthrough-vm-config.json`
- `GPU-SFTP/firecracker-bins/scripts/passthrough/run-gpu-passthrough-vm.sh`
- `GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/proxy-vm-config.json`
- `GPU-SFTP/firecracker-bins/configs/shared/vmshm-1client/client-vm-config.json`
- `scripts/deploy/deploy-host-kernel-and-test.sh`
