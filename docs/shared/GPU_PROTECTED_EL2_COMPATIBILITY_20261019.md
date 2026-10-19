# 场景二：受保护 EL2 兼容性与 Host 内核别名负例

**本页保留#27阶段的完整历史结果。** 后续#29已修复EL1 Host初始化、VMID分区及部分Realm
运行兼容性，当前protected/RME能力1；新的CPU初始化、timer修订、实际REC运行和失败记录
见[受保护Realm验证](GPU_PROTECTED_REALM_VALIDATION_20261019.md)。这不覆盖本页原失败，
也未实现Host物理任务MMIO强制保护。

日期：2026-10-19。接续[托管 IOMMU 故障中断验收](GPU_IOMMU_FAULT_VALIDATION_20261019.md)。
本轮改动验证代码，未改 Host/RMM/Guest 运行代码；临时启动参数已恢复。
原已实现7项、部分实现7项、失败/NOT_RUN/未解决6项及历史证据全部保留。
整体目标仍为 **PARTIAL / INCOMPLETE**，Host 物理任务 MMIO 保护仍为 **FAIL_BYPASS_DETECTED**。

## 本轮确定的事实

| 项目 | 证据 | 判定及边界 |
| --- | --- | --- |
| 受保护 EL2 启动 | 原 #27 Image 添加 `kvm_arm.mode=protected`，内核记录 `Protected hVHE mode initialized successfully`，SSH 恢复 | 启动兼容性通过；未添加 GPU/IOMMU 物理范围保护 |
| Host EL1 的 RMI 转发 | 同次启动中，电源探针 STATUS 返回 UNOWNED，非法 OPP 被拒绝 | 所列两个调用通过，不代表所有 RMI/REC/RSI 已兼容 |
| Realm 集成 | 同一 Image 的 `KVM_CHECK_EXTENSION(KVM_CAP_ARM_RME)` 从1变为0 | **FAIL_RME_UNAVAILABLE**；当前 Proxy/Client Realm 尚不能运行 |
| 恢复原配置 | extlinux 内容逐字节恢复；重启后命令行、#27、CPU0–1、pmthor、300MHz/userspace、RME能力1与开始一致 | 恢复通过；旧探针与最终新探针分别独立完成11项检查 |
| Host 内核物理写入 | 恢复原VHE配置后，指定测试 Realm 持有 MMIO 时，内核模块经 `ioremap` 将 `0xfb000028` 从0写为1、读回1并恢复0 | **FAIL_BYPASS_DETECTED**，退出2；仅限制 `/dev/mem` 不足以封堵 Host |
| 原 `/dev/mem` 负例 | 最终新用户态探针独立复验，同样读回0→1→0 | **FAIL_BYPASS_DETECTED**，退出2；原负例路径继续有效 |

## 新增的实际验证路径

`GPU-SFTP/tests/dma-guard/opencca_gpu_mmio_probe.c` 是内核别名负例的实际调用者，
由 `scripts/run/run-kvm-mmio-probe.py --kernel-mmio-module` 配合现有用户态探针执行。
父进程保持第一个 Realm 与 pmthor 会话，完成第二个 Realm 拒绝检查后加载模块，
读取结果并卸载模块，随后继续正常可信释放及销毁后重新授权检查。

模块只接受固定 GPU 地址，先经 RMI 确认 DESIGNATED，再检查 GPU 不忙且无 fault pending。
对 IRQ fault mask 位执行不同值写入、读回及恢复；32位 load/store 使用内核异常修复表，
写后执行 `dsb sy`。runner 核对内核日志的地址、四个值和四项错误码，校验模块 SHA/vermagic，
拒绝接管预先加载的同名模块，并检查卸载、增量内核健康及资源恢复。两个物理诊断选项互斥。

本轮四项访问错误码均为0，11项授权/OPP/释放检查通过，模块卸载退出0，内核无新增 BUG/Oops/WARNING。
这些正例不能抵消硬件边界失败。读取异常、设备忙、写入或恢复未证实只记 NOT_PROVEN/退出1。
本轮没有触发真实访问拒绝；异常修复分支及受保护 EL2 的拒绝转交仍未实机验收。
两个物理写入负例均在恢复原VHE配置后运行，未在受保护模式下运行指定Realm或这些负例。

用户态探针以 `-std=gnu11 -Wall -Wextra -Werror -O2 -static` 构建退出0；模块使用现有 #27
Host 输出树及显式 `LOCALVERSION=-opencca-pmthor-opp3` 构建退出0，vermagic匹配。
Python语法检查、固定上游补丁清单检查退出0；最终无诊断选项的控制运行独立退出0、11/11。
原66项源码指纹中仅4项测试文件改变，旧指纹保留；新增模块单独记录，Host/RMM/Guest运行源码未改。

## 仍需完成的实现

以下是源码复核得到的集成要求，不是本轮已部署的保护：

1. `arch/arm64/kvm/arm.c:kvm_arm_init()` 仅在 Host 处于 EL2 时初始化 RME，
   与受保护模式下的 Host EL1 冲突。还须审计 Realm vCPU 创建/销毁与普通 pKVM 路径，不能只改初始化条件。
2. pKVM Host stage-2 使用 VMID0；Host RME bitmap 从0分配，RMM也未拒绝0。
   OpenCCA使用真实Non-secure上下文，必须由可信层管理这些VMID的互斥、复用及TLB生命周期。
3. `hyp/nvhe/mem_protect.c:host_stage2_idmap()` 默认按需建立普通MMIO映射。
   必须限制GPU、托管IOMMU配置和可信内存的全部物理别名，并约束大块映射与惰性重建；
   `handle_host_mem_abort()` 对非预期拒绝执行 `BUG_ON`，还需安全地向Host交付访问异常。
4. `hyp/nvhe/hyp-main.c:flush_hyp_vcpu()` 从Host复制 `hw_mmu`，普通VM运行路径加载该上下文。
   Host自建普通VM的stage-2也须封堵；本轮仅做源码复核，未实机运行恶意普通VM。
5. RMM页表、GPUVM控制页和动态delegated backing需要可信所有权交接。
   Host stage-2不能忽略RMM的delegate/undelegate，也不能允许Host经RMI让RMM改写pKVM私有页；
   可信交接、失败回滚与释放顺序仍待实现和验证。
6. 不能盲目封锁整段低地址内存：Host DTS的SCMI mailbox位于BL31预留区内的 `0x0010f000`。
   板级电源、时钟、OPP及复位共享页仍需受限可信接口，不能整体开放物理页。
7. CPU stage-2不限制其他设备DMA。原直接PTE/PL330绕过记录保留；非托管DMA、总线访问控制、
   配置替换和复位恢复仍需独立闭合，不能把启动成功视作完整硬件隔离。

## 命令、退出码与日志

下表命令前缀为 `python3 scripts/maintenance/lab-run.py --run-id <本行run-id>`；
仅启动实验加 `--allow-rk-reboot`。完整参数、输入/源码和日志SHA见
[精简证据](evidence/secure-services-20261019/protected-el2-compatibility.json)。原始日志位于 `build/lab-runs/<run-id>/`。

| run-id | wrapper后命令 | 退出码 / 判定 | 主要日志 |
| --- | --- | --- | --- |
| `protected-el2-boot-20261019-a` | `python3 build/secure-services-20261019/protected-el2/boot-experiment.py`；当时版本留在本run的`runner.py` | 1；错误假定extlinux路径，未修改配置或重启；本次挂载已卸载 | `protected-el2.json、runner.py、result.json` |
| `protected-el2-boot-20261019-b` | 同上；执行版本留在本run的`runner.py` | 0；实验与恢复完成；其中Realm集成为FAIL，安全与性能验收NOT_RUN | `protected-el2.json、*-dmesg.log、uart.log、extlinux-*.conf` |
| `kvm-mmio-protected-restore-20261019-a` | `python3 scripts/run/run-kvm-mmio-probe.py --probe build/secure-services-20261019/physical-mmio/opencca_kvm_mmio_probe --uart-capture`；原runner | 0；恢复后原探针11/11 | `kvm-mmio.json、kernel-dmesg.log、rmm-uart.log` |
| `host-kernel-mmio-audit-20261019-a` | `python3 scripts/run/run-kvm-mmio-probe.py --probe build/secure-services-20261019/protected-el2/opencca_kvm_mmio_probe --kernel-mmio-module build/secure-services-20261019/protected-el2/kernel-module/opencca_gpu_mmio_probe.ko --uart-capture` | 2；内核物理写入绕过，11项及恢复通过 | `kvm-mmio.json、kvm-mmio-probe.log、kernel-dmesg.log、rmm-uart.log` |
| `host-devmem-mmio-audit-20261019-c` | 同一新用户态探针，改传`--audit-host-mmio --uart-capture` | 2；原/dev/mem路径独立复验绕过，11项及恢复通过 | 同上 |
| `kvm-mmio-kernel-probe-control-20261019-a` | 同一新用户态探针，不传物理诊断选项 | 0；默认路径11/11，内核健康与恢复通过 | `kvm-mmio.json、kvm-mmio-probe.log、kernel-dmesg.log` |

实际SD kernel分区备份保留在控制机两个启动run目录；仅主启动项临时改变，rescue项及Image/initrd/DTB/模块/固件不替换。
首轮失败完整保留；第二轮在线恢复成功，Pi刷写恢复预案未执行。当前仍为#27 / RMM IOMMU-fault，原失败不改判。

## 性能与产物

改动目的｜确认受保护EL2启动条件并补齐Host内核别名负例｜对照#27完整720p **1168** → 本轮**未测**｜
绝对/百分比分差**不适用**｜本轮仅临时启动参数与无负载诊断，未改运行代码，无新增性能测量｜
上述run-id、命令、退出码和日志｜保留验证代码与失败证据，不替换原冻结1171/1170，不宣称提分或隔离修复。

`protected-el2-cleanup-20261019-a/b` 均退出0，两轮共清理23文件、实际分配容量 **272,277,504字节（259.66 MiB）**：
控制机15文件/299,008字节，Pi2个临时恢复分区副本/268,435,456字节，RK6个重复诊断程序/模块/3,543,040字节。
精确路径、SHA、inode/mtime、fd/maps/loop/挂载检查和结果位于各run的 `cleanup-plan.json、cleanup-result.json`。
当前测试模块/探针和可复验构建输入、控制机实际SD备份、全部失败日志、当前/回退/完整恢复镜像、
原冻结包、基础rootfs和模型均保留。清理不构成GPU功能或安全验收通过。
