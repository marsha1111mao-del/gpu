# Proxy/Client 共享 GPU 修复与最终验证（2026-10-15）

修复已部署到 RK3588。最终 Host #10、同一 Client/Proxy 内核对，在一次开机中完成
Proxy 故障退出、恢复测试、全部长负载和双 Client 回归。下表均为最终部署版本的实际结果，
每轮启动器正常退出为 0。glmark 通过共享启动器的新默认入口运行。

```text
Client Mesa/PanVK → panthor-client → vmshm RPC
    → panthor-proxy → Proxy Panthor → Mali-G610
BO payload: vmshm-object；通信 ring: 独立的 vmshm-comm
```

## 最终运行矩阵

| 测试 | 结果与范围 | Run ID |
| --- | --- | --- |
| 故障后 Attention 320×64 | PASS；10 次测量、2 次预热；CPU reference/clean PASS，平均 3.7436 秒 | `shared-final-host-attention320-recovery-20261015-1230` |
| 六算子，GEMM 512 | PASS；六个算子各 100 次、预热 5 次；六项 correctness 与 clean PASS | `shared-final-host-ml-all512-100it-20261015-1230` |
| NCNN 三模型 | PASS；MobileNet v2/v3、ResNet50 各 100 次，失败模型 0/3 | `shared-final-host-ncnn-all-100loops-20261015-1230` |
| 720p 完整 glmark | PASS；Score 59；分配/export/VM_BIND/意外 framebuffer 错误均为 0 | `shared-final-host-glmark720-full-20261015-1230` |
| 1080p 完整 glmark | PASS；Score 58；同上错误检查均为 0 | `shared-final-host-glmark1080-full-20261015-1230` |
| 映射尺寸复用 | PASS；4 KiB → 2 MiB → 64 KiB → 2 MiB，四轮通过 | `shared-final-host-vm-bind-20261015-1230` |
| sync_file snapshot/import | PASS；export 128、import 64；源 reset/destroy/关闭 DRM FD | `shared-final-host-sync-snapshot-20261015-1230` |
| 双 Client 并发 | PASS；每个 Client 4 MiB、100 次测量、5 次预热，GLES_PASS | `shared-final-host-2client-4mib-100it-20261015-1230` |
| 双 Client 再次重复 | PASS；同配置再运行一次，启动器退出 0 | `shared-final-host-2client-repeat-20261015-1258` |

单 Client 日志：`GPU-SFTP/log/shared/vmshm-1client/<run-id>/`；双 Client：
`GPU-SFTP/log/shared/vmshm-2client/<run-id>/`。每轮的 `result` 保留原始结果，
`client.log` / `proxy.log`（双 Client 为 `client0.log` / `client1.log`）保留内核与用户态证据。
汇总核对数据：`GPU-SFTP/log/shared/host-recovery-20261015/final-matrix-verification.json`。

NCNN 平均时间为 MobileNet v2 **176.54 ms**、MobileNet v3 **172.79 ms**、
ResNet50 **979.67 ms**。benchncnn 使用零填充权重；此处验证图执行、同步与稳定性，
没有验证预训练模型精度，也未建立与 native 的同条件性能比较。

glmark 使用 `null-noop` 无窗口前端和 `finish` 等待 GPU 完成，仍执行真实渲染场景。
Client 目前不支持 PRIME buffer 导入/导出，因此这些结果不覆盖 stock GBM/PRIME。
已有的一个 framebuffer validation 例外被显式计数，意外 framebuffer 错误为零；
分配、export、VM_BIND 错误均为零。没有用跳过检查代替错误修复。

## 根因与修复

| 故障 | 修复及源码位置 |
| --- | --- |
| 小页 unmap 后，同一 VA 的 2 MiB map 返回 EEXIST | `Linux-Guest-GPU/drivers/iommu/io-pgtable-arm.c`：`arm_panthor_lpae_init_2m_block_or_pages()` 移除遗留下级表；`arm_panthor_lpae_init_pte()` 使用理解 HPA descriptor 的 Panthor 专用 unmap walker。 |
| Client WC 与 Proxy WB 访问同一 BO payload | `drivers/char/{client_vmshm_manager,proxy_vmshm_manager}/` 中对象窗口内核映射、Proxy debug mmap 统一为 WC；通信 ring 保持原协议。避免分配器清零与 Client 写入之间的缓存属性混用。 |
| 224 MiB 对象窗口不足 | `scripts/run/run-vmshm-e2e.sh` 按负载选择 glmark 512 MiB、NCNN 768 MiB；显式覆盖有效。ResNet50 的 152 MiB BO 需要 buddy 的 256 MiB 块，旧窗口无法提供。 |
| 扩大低地址窗口覆盖 UART/virtio MMIO | 大于 256 MiB 的对象窗口整体移到 GPA `0x100000000`；Client/Proxy 地址和容量一致。保留低地址 224 MiB 会通过，直接把它扩大到 768 MiB 则不能启动。 |
| 大窗口逐页 buddy 元数据 kcalloc 失败 | `proxy_vmshm_manager.c` 的 CPU 元数据使用 `kvcalloc/kvfree`，覆盖正常释放与失败路径；不要求这份元数据物理连续。 |
| 两个 VM 共享根盘的 journal 恢复失败 | 两侧根盘使用 VMM 只读 block device 和 `root=/dev/vda ro`；Host 在启动 VM 前完成 payload 注入并卸载文件系统。 |
| fence 等待占用串行 RPC | Client export worker 零超时查询不可变 snapshot，pending 时在 RPC 外睡眠；保留有界等待。不能据此宣称端到端性能提升。 |
| timing/零退出码掩盖底层错误 | ML 检查完整算子名及 clean marker；NCNN 拒绝 Mesa/Vulkan、BO_CREATE、VM_BIND 错误。NUL/CRLF parser 修复及负例 fixture 防止错误被 timing 掩盖。 |
| Host GPA→HPA 每次翻译获取 PFN 引用却不释放 | `Linux-Host-GPU/arch/arm64/kvm/hypercalls.c` 与 `drivers/pmthor/pmthor_drv.c`：按 PFN 去重，归还重复获取引用；设备和绑定 VM 都结束后，确认 GPU reset，再释放唯一引用。 |

共享启动器默认改为 `GLES_GLMARK_FLAVOR=null-noop`、`GLES_GLMARK_FRAME_END=finish`。
显式选择其他前端和 frame-end 的参数仍可使用；通用 `gpu-smoke.sh` 的其他工作流保留原行为。

## Host 页面生命周期与故障恢复

最终实现由设备 owner mutex 保护活动 session 和绑定 VM 计数：

1. 第一次翻译将 KVM 绑定到设备会话；xarray 以 PFN 索引，重复翻译立即归还额外引用。
2. VM 先退出时，页面保留到设备文件关闭，设备 reset 成功后释放。
3. 设备文件先关闭时，立即停止 IRQ 会话并 reset，但仍保留页面及独占会话。
   旧 VM 存活期间，新会话打开返回 EBUSY，防止旧 MMIO 映射和新 owner 并存。
4. 最后一个 VM 销毁时再次 reset，随后才能释放页面，因为 VM 可能在第一次 reset 后继续写 MMIO。
5. reset 失败时保留页面和会话，后续成功 open/reset 才能回收。

`GPU-SFTP/tests/pmthor-pfn-lifetime/` 在实际 ARM64 KVM 上测试两种关闭顺序，
每轮 32 次同页翻译。最终版本每轮只保留/释放一个 PFN，device-first 的重新打开得到
EBUSY，日志确认最后 VM reset 在最终页面释放之前。
`check_kernel_log.py` 的负例验证会拒绝漏释放、错误去重数量、缺少最后 reset、缺少独占检查。
证据：`final-host-pfn-{test,kernel,check}.log`。

`shared-final-host-proxy-sigkill-20261015-1228` 在长 Attention 测试记录至少五次 pending
import 后故意 SIGKILL Proxy，再停止该轮 Client/broker。该轮 workload FAIL / launcher
exit 1 是预期结果，另有 `fault-injection-intent.txt` 标注。Host 完成两次 reset 并释放
2968 个 PFN。紧接其后的 Attention 320 和完整长负载全部通过，中间没有重启。

## 内存回收实测

下表是每轮退出后的原始快照，MiB 按 1024 KiB 换算；不把后续诊断值回填到原始记录。

| 负载 | 前 MemAvailable/MiB | 后 MemAvailable/MiB | 最终释放 PFN 数 |
| --- | ---: | ---: | ---: |
| 故障后 Attention 320×64 | 3156.6 | 3154.3 | 2,968 |
| 六算子，GEMM 512 | 3154.3 | 3151.7 | 22,410 |
| NCNN 三模型 | 3151.7 | 3151.3 | 87,188 |
| 720p 完整 glmark | 3151.3 | 3152.6 | 40,201 |
| 1080p 完整 glmark | 3152.4 | 3150.8 | 78,021 |
| 映射尺寸复用 | 3150.8 | 3130.2 | 705 |
| sync_file snapshot/import | 3129.8 | 3133.9 | 185 |
| 双 Client 并发 | 3133.7 | 3055.1 | 7,595 |

ML、NCNN、720p、1080p 连续长测后约 **3151–3153 MiB** 可用，Shmem 回到约
1328 KiB。每轮 session closed 的去重页面数量与 released 数量一致。

双 Client 后原始 MemAvailable 约 3055 MiB，进一步检查发现 CPU1 PCP 持有约
24,960 个已经释放的空闲页。重复双 Client 仍通过。通过读取内核 `stat_refresh`
入口触发既有的 PCP 衰减流程，取得以下成对证据：

```text
之前: MemAvailable=3127236 KiB, PCP=23949 pages, Shmem=1328 KiB
之后: MemAvailable=3206776 KiB, PCP= 4032 pages, Shmem=1328 KiB
PCP 减少 19917 pages = 79668 KiB = 77.80 MiB
MemAvailable 增加       79540 KiB = 77.68 MiB
```

因此这部分差值对应已经归还 PCP 的空闲页，不能只依据 MemAvailable 判断为 GPU
引用泄漏。源码 `mm/page_alloc.c` 的 `free_unref_page_commit()` / `decay_pcp_high()`
和 `mm/show_mem.c:si_mem_available()` 解释了 PCP 与 buddy 统计的区别。
诊断未改变 sysctl 配置；读取入口本身会触发 PCP 回收，故单独列出其前后值。
证据：`pcp-refresh-single.log`、`pcp-refresh-proof.log`、
`after-final-dual-detailed-mem.log` 以及重复测试的 before/after 日志。

## 部署、对照与复现

```text
Host: 6.12.0-opencca-pmthor #10
Build: Thu Oct 15 12:23:44 CST 2026
Host Image SHA256:
ca8fb02a1ca95b588ef1e2fcd3191865c98ab3b1b758d586d3b36e90c88c3f6c
Client Image SHA256:
e797e3180e65407eecb5cfed894725f9e5f8b31f822f1089feb38a820062e68f
Proxy Image SHA256:
24e213e91b4ecc2ce2c4e6dece0b1bad15d445d3b7207e8701f4f70da5922b55
Boot image: opencca/snapshot/kernel-pmthor-final-session-pfn-20261015.img
Boot image SHA256:
27c6ad71937d8cee1d8c7d976f6e76cca41ed6ab51b6f9eb0bebeacfb44ae4bb
```

Host 经 Pi wrapper 检查 live SD/GPT 后，仅刷 SD storage ID 2 的 p3 kernel 分区，
起始 LBA `0x8000`；使用现有 initrd/DTB。最终远端 Guest Image 哈希已核对。
长测结束无 Firecracker/broker 残留进程，Host CPU 恢复为 `0-1`。

关键对照：旧 Proxy 在 `shared-vm-bind-size-reuse-oldkernel-20261015-1043`
的第二轮 2 MiB map 失败 -17，修复版四轮通过；旧混合 WC/WB 的 NCNN 前缀失败，
匹配 WC 后相同前缀通过。Host #9 虽通过完整 GPU 矩阵，但新增重新打开检查实际失败
（`joint-host-pfn-reopen-control.log`），最终 #10 完整通过增强生命周期检查。
较早仅 VM 计数或仅设备计数的候选没有作为最终部署版本使用。
完整历史和运行 ID 见 [工作日志](PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md)。

复现以下命令需要远端具备本文哈希对应的内核与当前测试二进制；`--skip-sync` 复用这些产物。
去掉 `--skip-gles-remote-build` 时，远端需提供 cc、pkg-config 与 EGL/GLES/GBM 开发包。

```bash
./scripts/run/run-vmshm-e2e.sh --skip-build --skip-sync \
  --gles-glmark-smoke --skip-gles-remote-build \
  --gles-glmark-size 1920x1080 \
  --gles-client-mem-mib 512 --gles-proxy-mem-mib 384

GLES_CLIENT_BO_MMAP_CACHED=0 GLES_NCNN_LOOP_COUNT=100 \
  ./scripts/run/run-vmshm-e2e.sh --skip-build --skip-sync \
    --gles-ncnn-smoke --skip-gles-remote-build \
    --gles-client-mem-mib 512 --gles-proxy-mem-mib 384

./scripts/run/run-vmshm-e2e.sh --skip-build --skip-sync \
  --gles-ml-smoke --skip-gles-remote-build \
  --gles-smoke-args '--kernel all --iterations 100 --warmup 5 --gemm-size 512' \
  --gles-client-mem-mib 512 --gles-proxy-mem-mib 384
```

## 验证边界

- Attention 参数默认 256，允许 128–1024、64 的倍数；本次扩大到 320 并验证恢复，
  较早同一 Guest 对也完成三次独立 320 生命周期。允许范围不保证每个规模满足 GPU watchdog。
- snapshot 测试覆盖 initially-signaled fence 的源 reset/destroy/关闭 DRM FD；实际 ML
  路径覆盖 pending import，尚未构造所有 pending-fence 并发销毁竞争。
- Host reset 失败时保留引用的路径经过源码审查，未做硬件 reset-failure 注入。
  本次修复不是完整 DMA pin/migration/revoke 协议，不覆盖活跃 platform unbind，
  不构成机密多 VM GPU 隔离能力证明。
