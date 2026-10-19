# IOMMU 映射准入与扩展 DMA 诊断探针

当前选定硬件结果见[设备授权验收](../../../docs/shared/GPU_DEVICE_ASSIGNMENT_VALIDATION_20261019.md)。
下文早期“尚未执行”保留对应阶段边界，不代表当前部署状态；每次新组合独立验证。

## Guest 设备授权与供电生命周期

RMM managed-IOMMU 开发 ABI 增加 Host-only `GRANT=9`、`REVOKE=10`，输入仍为
`(operation, handle, arg1, arg2, arg3)`：

| 操作 | handle | arg1 | arg2 | arg3 |
| --- | --- | --- | --- | --- |
| GRANT | 0 | 固定平台 device ID | Guest 已创建的 domain handle | 0 |
| REVOKE | 0 | 相同 device ID | 0 | 0 |

Host 须先通过真实 Rockchip 驱动挂接空 managed domain；驱动持续持有 IOMMU runtime-PM 与时钟引用。
RMM 只允许把这个已绑定、无映射、健康的设备授权给有效 Guest domain，先将设备停放在空 root，
再记录与 domain generation 绑定的授权。Guest RSI BIND 没有对应授权时在访问硬件前拒绝，
合法但未上电的其他 bank 也不能仅凭地址被 Guest 触碰。Guest 无权发起 GRANT/REVOKE。

授权期间 Host map/bind/unbind/quiesce 和目标 Guest domain destroy 被拒绝，保持供电引用和授权生命期。
Host REVOKE 不依赖 Guest 自报完成：RMM 停放真实设备、撤销 Guest 绑定，再恢复 Host 空 root。
Guest 的页面预留不会随授权撤销被提前释放，仍须完成自己的 unmap/destroy。
硬件停放失败进入隔离并保留所有权/引用；Host 的直接断电拒绝服务与 OpenCCA GPT/GPC 硬件边界不因此消失。

`opencca_iommu_assignment_probe.ko` 是真实 Host 调用者：创建并挂接空 codec domain、授权给
Guest handle、确认授权期间 Host RMI UNBIND 被拒绝，最终撤销并正常解绑释放供电引用。
Guest 模块以 `hold_mapping=1 device_test=1` 保持测试页与 domain，PID 1 的
`iommu-device 5/6` 仅写该探针的固定 sysfs 参数，执行 Guest BIND/UNBIND。
测试涵盖未授权拒绝、真实绑定/解绑/重绑、Host 强制撤销后再次绑定拒绝和 backing 释放。
它验证真实 IOMMU root/IOTLB 生命周期，不发起 codec 数据 DMA，也不代表 Guest codec 驱动整机直通已完成。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-guest-iommu-probe.py --images <冻结包> \
  --module <匹配Guest的opencca_guest_iommu_probe.ko> --realm-init <静态测试PID1> \
  --assignment-module <匹配Host的opencca_iommu_assignment_probe.ko>
```

当前验收范围是：其他使用 IOMMU 的设备建立映射时，拒绝映射 GPU/Realm 受保护物理页。
设计、结果和限制见 [IOMMU 映射防火墙](../../../docs/shared/IOMMU_MAPPING_FIREWALL_20261018.md)。
直接页表配置绕过和无 IOMMU 的 PL330 诊断另见
[先前扩展报告](../../../docs/shared/GPU_DMA_GUARD_IMPLEMENTATION_20261018.md)。

探针使用真实 Rockchip IOMMU 驱动创建的**未挂接 domain**，只操作测试所有的页和页表，
不启动视频编解码器，不对其他 Realm 的数据发起实际 DMA。
`iova_to_phys()` 成功只证明页表存在该映射，不能证明设备已经读到了数据。

## 构建

先读环境主手册，使用与板端 release、配置和模块相匹配的 Host 构建输出。
源码复制到忽略的构建目录后编译，避免生成文件污染源码目录：

```bash
mkdir -p build/dma-guard-20261018/probe-module
cp GPU-SFTP/tests/dma-guard/Makefile GPU-SFTP/tests/dma-guard/opencca_*.c \
    build/dma-guard-20261018/probe-module/
make -C Linux-Host-GPU O="$PWD/build/dma-guard-20261018/host" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    LOCALVERSION=-opencca-pmthor-opp3 \
    M="$PWD/build/dma-guard-20261018/probe-module" modules
bash scripts/check/check-dma-guard.sh
```

Host 必须启用 `CONFIG_OPENCCA_DMA_GUARD=y`，RMM 必须实现开发 ABI 1。
托管页表轮必须再启用 `CONFIG_OPENCCA_MANAGED_IOMMU=y`；runner 会拒绝缺少该配置的 Host。
STATUS 的能力 flags 当前为 0，明确表示没有硬件配置保护承诺。

## 板端执行

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
    python3 scripts/run/run-dma-guard.py \
    --module build/dma-guard-20261018/managed-probe-module/opencca_dma_probe.ko
```

默认选择 `fdb50000.video-codec`，可通过 `--device` 显式选择其他已启用 IOMMU 的设备。
当前板端没有启用 NPU 驱动，因此不声称已完成 NPU 推理或真实 NPU DMA 测试。

加 `--images build/safe-optimization-20261018/final`，会在完整 720p glmark 期间
采样真实 GPU 租约页并额外检查映射拒绝；该轮探针对性能有干扰，不能作为纯性能比较。
采样后不持有该 GPU 租约，但 Realm 页面归属仍独立阻止映射；这不是持续租约验证。
独立性能测量使用正常 Realm runner。

非托管模式默认 15 项检查覆盖普通页与 SG 正例、委托冲突、解除映射后委托、受保护页读写、
IOVA 别名与覆盖区间拒绝、SG 失败前缀回滚、解除委托后复用及 PTE/预留记录回收。
托管模式增加 direct driver 拒绝、RMM root 绑定、unbind 后 deny-all parking 与重绑恢复共 7 项，
合计 22 项。GPU 运行期间再增加 6 项采样页面检查，共 28 项。拒绝要求返回 `-EPERM` 且没有残留 PTE；
SG 回滚还要求 RMM 记录计数恢复，防止“全部拒绝”或留下部分映射冒充通过。

runner 保存 `build/lab-runs/<ID>/dma-guard.json` 和内核增量日志。
默认范围全部通过返回 **0**；准入、GPU 运行、内核健康或清理失败返回 **1**。

## 活跃 backing page 的原始 RMI 回收负例

`opencca_reclaim_probe.ko` 只用于测试。它从本次最小 Realm 的 Firecracker
进程取得 RD，对 Guest 探针单独分配并持有的页面直接调用 `RMI_DATA_DESTROY`，
要求返回 `RMI_ERROR_INPUT`，且前后 RTT entry 完全一致。它不通过 KVM 的正常
回收入口，因此不能由 Host 合作路径的 pin 检查代替 RMM 拒绝。

匹配 Host 构建此模块；Guest 的 `opencca_guest_iommu_probe.ko` 则必须使用匹配
Proxy Image 的 Guest 构建目录。测试 PID 1 需从当前 `tests/realm-xshm/init.c`
静态构建，支持向 `insmod` 传递有界参数。不要替换正在使用的冻结 initrd。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
    python3 scripts/run/run-guest-iommu-probe.py --images <冻结包> \
    --module <匹配Guest模块> --realm-init <新测试PID1> \
    --reclaim-module <匹配Host的opencca_reclaim_probe.ko>
```

默认持有 Guest RSI IOMMU 映射；另加 `--gpu-backing` 时，将 GPU 指定给本次
Proxy，改为持有 GPU HPA 租约。两种模式均只尝试销毁自己专门分配的测试页，
检查拒绝、entry 不变、撤销/释放和 Guest/Host 内核健康。GPU 模式不发起 GPU
任务，也不能替代完整 glmark、真实在途 DMA 或 hostile Host CPU MMIO 隔离验证。
原始命令、返回码、模块哈希、Guest 日志及 `host-reclaim.log` 保存在本次
`build/lab-runs/<ID>/`，未执行的模式须保留 `NOT_RUN`。
该模式没有执行实际设备 DMA，不能据此宣称硬件配置保护或复位保持通过。

显式加 `--audit-bypass` 会直接调用 `domain->ops->map_pages()`，故意绕过通用 Linux 接口：
当前结果是 `configuration_protection=FAIL_BYPASS_DETECTED`。
这是保留的防护失败证据，不应删除该负例或用普通接口 PASS 抵消它。
扩展诊断即使准入全通过也返回 **2**，因为完整 DMA 防护仍是 `INCOMPLETE`；
该标志不能与 `--transfer` 同时使用。

## 真实 PL330 DMA 读写

`opencca_dma_transfer_probe.c` 通过 DMAengine **独占申请指定空闲通道**，只使用三张自行
分配的 4 KiB 页面，不接受外部目标 PA，不访问运行中的 Realm/GPU BO。
本次 Host 为 4 KiB 页、PL330 内建，模块使用匹配 release 构建。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-dma-guard.py --transfer \
  --module build/dma-guard-20261018/probe-module/opencca_dma_transfer_probe.ko
```

默认只申请 `fea10000.dma-controller / dma0chan10`；忙时退出，不抢占其他通道。
另外两套控制器可分别显式选择 `--transfer-controller fea30000.dma-controller
--transfer-channel dma1chan0` 或 `fed10000.dma-controller / dma2chan0`。
不同测试串行执行；该模式拒绝 `--images`，不与 GPU 负载并行。

每次包含普通 NS 页拷贝正例，以及“先建立 DMA 映射再委托”和“先委托再建立 DMA 映射”
两种时序。受保护阶段先 DMA 写入委托页，再 DMA 读回至另一张普通页；每次拷贝检查完成
cookie，停机并成功 undelegate 后逐字节校验。CPU 不在页处于 DELEGATED 状态时读取目标页。
遵守 DMA map/unmap 的缓存所有权；不安装模块回调。停机或解除委托失败时保留资源并阻止
模块卸载，防止 DMA 继续访问已释放页面；需先检查该次日志，再安排恢复。

三套控制器实测均能完成上述读写，结果为 **FAIL_BYPASS_DETECTED**，外层退出 **2**。
`actual_dma_transfer=PASS` 只表示真实传输及内容校验成立；`full_dma_protection=INCOMPLETE`。
探针没有验证现役 Realm 秘密泄露，也没有验证真实 GPU BO 的防火墙允许/拒绝或复位保护。
完整结果、输入 SHA 和日志位置见开发报告第 3.4 节。

## 托管 IOMMU 与 GPU MMIO 探针

`opencca_guest_iommu_probe.c` 在 Guest 内直接调用 RSI FID `0xc40001b0`，
覆盖 ABI 版本、secure handle 创建、Realm assigned RAM 映射、真实 HPA/root 查询、
映射期间 destroy 拒绝、unmap 后 destroy 与 stale handle 拒绝。可用冻结 proxy 内核输出单独编译：

```bash
mkdir -p build/dma-guard-20261018/guest-module
printf 'obj-m += opencca_guest_iommu_probe.o\n' \
  > build/dma-guard-20261018/guest-module/Makefile
cp GPU-SFTP/tests/dma-guard/opencca_guest_iommu_probe.c \
  build/dma-guard-20261018/guest-module/
make -C Linux-Guest-GPU O="$PWD/build/verified-kernels/client" ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-realm \
  M="$PWD/build/dma-guard-20261018/guest-module" modules
```

控制器会校验冻结 proxy Image/initrd SHA-256 与模块 vermagic，向 run-id 专属候选 initrd
追加 `/opencca_guest_iommu_probe.ko`，再上传 Image/initrd/runner 并在 RK 上启动一个
最小 Realm。模块只在该 lab-run 独占窗口内 `insmod`/`rmmod`，以
`[GUEST_IOMMU_TEST] result=PASS` 且无新增 Guest 内核失败为通过：

设备授权测试的 `--assignment-module` 还必须包含当前 Host fault 检查，控制器会在访问
硬件前拒绝旧版探针。当前匹配输入为
`build/secure-services-20261019/iommu-irq/host-module/opencca_iommu_assignment_probe.ko`；
早期 device-assignment 模块不包含该接口。中途失败时先撤销 Host 授权并卸载 Guest
探针，释放其 backing，再退出 Realm；保留原失败结果并单独验证清理健康，不能把清理
成功改写为功能通过。失败复核记录见
[逐项排查](../../../docs/shared/GPU_FAILURE_STATUS_AUDIT_20261019.md)。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-guest-iommu-probe.py \
  --images build/safe-optimization-20261018/final \
  --module build/dma-guard-20261018/guest-client-module/opencca_guest_iommu_probe.ko
```

本地已通过两个 Python runner 的 `py_compile`、冻结 Image release/模块 vermagic 匹配检查，
以及候选 newc initrd 的追加与回读解析；本轮尚未执行硬件验证。

`opencca_kvm_mmio_probe.c` 创建最小 Realm VM，验证非 GPU/错位/超范围 MMIO 拒绝、
首个 Proxy 授权、owner 存活期间的合法 OPP 往返、第二个 Realm 拒绝、pmthor 复位释放以及销毁后释放。控制机静态编译并运行：

```bash
aarch64-linux-gnu-gcc -std=gnu11 -Wall -Wextra -Werror -O2 -static \
  GPU-SFTP/tests/dma-guard/opencca_kvm_mmio_probe.c \
  -o build/dma-guard-20261018/opencca_kvm_mmio_probe
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-kvm-mmio-probe.py \
  --probe build/dma-guard-20261018/opencca_kvm_mmio_probe
```

该探针只验证 KVM 请求、RMM 授权/PM 状态机和 pmthor 空会话复位释放，不启动 GPU 工作负载、不宣称 Host GPC 强制隔离；
本轮尚未执行硬件验证。

可选 `--audit-host-mmio` 诊断 Host 物理访问绕过。它在首个测试 Realm 获得 MMIO、
第二个 Realm 被拒绝后，通过 Host `/dev/mem` 访问固定的 `0xfb000028` IRQ mask。
只在 GPU 无活跃任务、无 GPU fault 时翻转 fault mask 位，读回变化并恢复原值；
随后完成正常 owner 释放和重新授权检查。该模式不能与真实 GPU 工作负载并发运行。
父进程保留会话，物理访问子进程异常退出后仍执行可信复位/释放。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-kvm-mmio-probe.py \
  --probe build/secure-services-20261019/physical-mmio/opencca_kvm_mmio_probe \
  --audit-host-mmio --uart-capture
```

读回修改且成功恢复时，`host_mmio_protection=FAIL_BYPASS_DETECTED`，外层退出 **2**；
11 项 ABI/owner 检查单独记录，不将它们的 PASS 当成物理隔离通过。
无法打开/映射 `/dev/mem`、设备忙、非预期访问异常或修改未被读回均为未证明，退出 **1**。
新增受控拒绝检查只接受固定地址的 `SIGBUS/BUS_OBJERR`：初次读、写1、读、恢复写0、
再次读共5项均须返回 `-EFAULT`，runner逐项核对地址、信号和错误码，才记录
`HOST_CPU_ACCESS_DENIED`、退出0。早期候选将任何信号记为NOT_PROVEN的历史记录保留。
该结论只覆盖所测Host用户态访问，不证明普通VM、DMA或其他物理范围已被保护。
不传该选项时继续执行原来的 11 项检查。

`--kernel-mmio-module` 使用匹配 Host 的 `opencca_gpu_mmio_probe.ko`，在同一个
空闲且已授权的会话中通过内核 `ioremap` 访问相同 IRQ mask。模块先查询 RMM，
要求状态为 DESIGNATED，再确认 GPU 不忙且无 fault pending；只翻转 fault mask 位，
读回并恢复。访问使用带异常修复的32位load/store；单次异常不构成拒绝验收。
模块只接受固定地址，不接受任意物理地址或寄存器参数。

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-kvm-mmio-probe.py \
  --probe build/secure-services-20261019/protected-el2/opencca_kvm_mmio_probe \
  --kernel-mmio-module build/secure-services-20261019/protected-el2/kernel-module/opencca_gpu_mmio_probe.ko \
  --uart-capture
```

控制机将模块源码复制到独立构建目录，用对应 Host 输出树、交叉工具链及显式
`LOCALVERSION=-opencca-pmthor-opp3` 构建模块；不要在测试源码目录留下编译产物。
runner 校验模块 SHA/vermagic，拒绝接管预先加载的同名模块；会话仍有效时完成
模块加载、结果读取和卸载，失败时也只清理本次拥有的模块。
runner 同时核对增量内核日志里的地址、不同值写入、实际读回、恢复值及四项访问错误码。
确认绕过时仍退出 **2**，不能用 11 项授权检查或模块卸载成功抵消失败。
若STATUS/RAWSTAT/MASK三次初读均为`-EFAULT`，继续在两个同时存在的`ioremap`别名上
检查写1、读、恢复写0、另一别名读写和首个别名复查；总计10项错误码均须为`-EFAULT`。
runner核对完整内核记录、11项owner/OPP/释放检查、模块卸载和内核健康，才记录
`HOST_CPU_ACCESS_DENIED`、退出0；其他读取失败、设备忙、写入未证实仍为NOT_PROVEN/退出1。
该选项与`--audit-host-mmio`、`--ordinary-vm-probe`互斥。旧负例见
[EL2兼容性与内核别名负例](../../../docs/shared/GPU_PROTECTED_EL2_COMPATIBILITY_20261019.md)，
新候选见[Host MMIO封堵与普通VM绕过](../../../docs/shared/GPU_HOST_MMIO_ENFORCEMENT_20261019.md)。

### 普通VM物理MMIO负例

`opencca_ordinary_mmio_probe`先用正常RAM代替设备页，验证普通VM实际执行、结果发布及
0x40→0x41→0x40读写；再将`/dev/mem`的GPU首个物理页作为另一个普通VM的memslot。
Guest检查GPU空闲及无fault pending后，翻转固定IRQ mask位并读回恢复；Host不直接读该映射。
完成通过固定虚拟MMIO退出和独立结果页核对，15秒超时、普通VM不能运行或无法读回均不记保护PASS。

```bash
aarch64-linux-gnu-gcc -std=gnu11 -Wall -Wextra -Werror -O2 -static \
  GPU-SFTP/tests/dma-guard/opencca_ordinary_mmio_probe.c \
  GPU-SFTP/tests/dma-guard/opencca_ordinary_mmio_guest.S \
  -o build/secure-services-20261019/host-mmio/opencca_ordinary_mmio_probe
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-kvm-mmio-probe.py \
  --probe build/secure-services-20261019/host-mmio/opencca_kvm_mmio_probe \
  --ordinary-vm-probe build/secure-services-20261019/host-mmio/opencca_ordinary_mmio_probe \
  --uart-capture
```

由父探针先建立指定Realm的owner会话，整个普通VM检查期间保留该会话，随后可信复位、
释放并重新授权。只有RAM正例和GPU实际修改/恢复均证实时才记录
`ordinary_vm_mmio_protection=FAIL_BYPASS_DETECTED`、退出2；Host直接访问检查独立记录。
禁止与实际GPU工作负载并发；本负例不授予普通VM合法GPU所有权。

`bash scripts/check/check-opencca-host-mmio.sh`在ASAN/UBSAN下测试实际Host范围裁剪及
共享异常入口辅助函数，覆盖18581种范围组合、393216种EL1/EL2异常状态组合。
这些单元测试不能替代上述实际CPU访问、普通VM负例和完整720p门槛。

### OpenCCA VMID 分区验证

Host `CONFIG_KVM_ARM_OPENCCA=y` 将普通 VM 分配限制在真实 VMID 空间的下半区，
其中0保留给受保护 Host；Realm 使用上半区。配套 RMM 按实际 CPU 特性选择8/16位，
拒绝用下半区创建 Realm，并按相同位宽设置 REC 的 VTCR。旧 RMM 固定8位的模拟值
不能与16位 Host 的上半区分配混用；新 RMM 也不接受旧 Host 从0分配的 Realm。
更新时保留配套 Host/RMM 回退，不能只更新一方后继承旧测试结论。

`bash scripts/check/check-opencca-vmid.sh` 在 ASAN/UBSAN 下编译实际 RMM 分配器，
分别验证常规/OpenCCA的8/16位边界、全部槽位耗尽、释放复用和16线程重复申请。
该单测使用测试原子操作，不替代 ARM 原子指令及实机生命周期验证。

`opencca_vmid_probe.ko` 绕过 KVM 分配器，直接经 RMI 请求创建有效 RD/RTT，验证
Host VMID0和普通 VM 上界被拒绝、Realm上下界可用、重复拒绝和销毁后复用。
正例与负例共用有效参数，避免把所有请求都失败误判为隔离通过；没有启动 REC、
GPU任务或 DMA。销毁/undelegate失败时保留相应页面并报失败，不提前回收。

```bash
mkdir -p build/secure-services-20261019/protected-realm/vmid-module
cp GPU-SFTP/tests/dma-guard/opencca_vmid_probe.c \
  build/secure-services-20261019/protected-realm/vmid-module/
printf 'obj-m += opencca_vmid_probe.o\n' \
  > build/secure-services-20261019/protected-realm/vmid-module/Makefile
make -C Linux-Host-GPU O="$PWD/build/dma-guard-20261018/host" \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-pmthor-opp3 \
  M="$PWD/build/secure-services-20261019/protected-realm/vmid-module" modules
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-opencca-vmid-probe.py \
  --module build/secure-services-20261019/protected-realm/vmid-module/opencca_vmid_probe.ko
```

runner核对模块SHA/release、六项结果、可信回收、卸载及增量内核健康。
这项测试不证明恶意 Host 无法通过普通 VM 的自建 stage-2 或直接物理访问绕过保护。

需要覆盖真实 Realm GPU workload 的最后 VM teardown、页引用释放和 Host 内核日志时，使用组合入口：

```bash
python3 scripts/maintenance/lab-run.py --run-id <唯一ID> -- \
  python3 scripts/run/run-gpu-pm-regression.py \
    --lease-monitor build/dma-guard-20261018/lease-monitor/opencca_lease_monitor.ko \
  --images build/safe-optimization-20261018/final \
  --kvm-probe build/dma-guard-20261018/opencca_kvm_mmio_probe \
  --workload compute
```

该入口先运行 KVM/OPP/复位探针，再运行双 Client compute。构建匹配 Host 的
`opencca_lease_monitor.ko` 后通过 `--lease-monitor` 指定：监视器只读取已有 RMI 状态，
要求负载期间 RMM GPU 租约峰值大于零，结束后 GPU/DMA 记录均归零，查询无错误。
同时检查 `last VM teardown` 复位、Host 引用释放日志与内核健康。
Host 引用数量可能为零，不可将该日志单独作为非零 RMM 租约释放证据。

`opencca_gpu_power_probe.ko` 只查询 RMM 电源状态并验证非法 OPP 被拒绝，不直接操作 GPU
任务寄存器。`scripts/run/run-gpu-power-cycle.py` 在独占窗口内解绑/重绑空闲 pmthor，
检查真实 GPU power domain、RMM OFF/UNOWNED、内核健康和频率恢复，再运行 KVM/MMIO 探针。
UART 与分阶段日志用于区分电源操作失败、恢复失败和验证失败；不把板级断电等同于 GPU 电源域关闭。

```bash
mkdir -p build/dma-guard-20261018/lease-monitor
cp GPU-SFTP/tests/dma-guard/opencca_lease_monitor.c build/dma-guard-20261018/lease-monitor/
printf 'obj-m += opencca_lease_monitor.o\n' > build/dma-guard-20261018/lease-monitor/Makefile
make -C Linux-Host-GPU O="$PWD/build/dma-guard-20261018/host" \
  ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-pmthor-opp3 \
  M="$PWD/build/dma-guard-20261018/lease-monitor" modules
```
