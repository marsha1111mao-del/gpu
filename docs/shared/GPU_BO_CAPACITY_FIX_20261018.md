# 大 BO 分配与 ResNet50 / 1080p 修复（2026-10-18）

完整 Native 对照、17 项 IOCTL 时延及两种分辨率逐场景数据见 [统一统计报告](GPU_NATIVE_PROXYCLIENT_COMPARISON_20261018.md)。

已通过本轮 ResNet50、完整 1080p、17 项共同 IOCTL 和 128 MiB Compute；两个 Realm 无受检 GPU fault / timeout / WARN / Oops。默认 256 MiB 配置在独立新建 Realm 中完成完整 720p，**1154 → 1161（+7，+0.61%）**。另通过 3 Realm / 双 Client 的 2×17 项 API、两份实际计算及越权/IRQ 负例检查。本轮不构成完整 32 项回归。

## 1. 根因：单块取整限制与真实容量不足同时存在

旧共享池为 256 MiB；控制区与保留区后，GPU 分配器实际管理 253 MiB。旧 buddy 单块最大 128 MiB，且每个连续 BO 按 2 的幂向上取整：

| 请求 | 旧实际保留 | 后果 |
| --- | --- | --- |
| ResNet50：152 MiB（0x9800000） | 256 MiB | 超过 max_order15，必定 ENOMEM |
| 1080p：32.375 MiB（0x2060000） | 64 MiB | 浪费约 31.6 MiB，放大资源压力 |
| 1080p：约 44.965 MiB（0x2cf7000） | 64 MiB | 浪费约 19.0 MiB |

仅修正取整仍不够。实机诊断记录：`request=159383552 free=19771 total=64768 pages`。申请 152 MiB 时仅余 **77.230 MiB**，已有分配约 **175.770 MiB**，两者相加至少需要 **327.770 MiB**；这一次是总容量不足，不能归咎于连续碎片。第一候选在默认池上仍发生 ENOMEM 和 translation fault；旧错误时间及故障后的分数继续作废。

## 2. 实际保留的修改

1. GPU BO 使用按页计量的连续 extent。与现有 buddy 共用页状态和同一把锁，搜索成功后才拆分/占用空闲块；分配失败不改变状态。保留连续 offset / mmap / GPU 映射协议。非 GPU 对象、slab 和已有 SG 路径继续使用原方式。
2. 新 backing 仍经既有 pin、最后引用、撤销和释放清零流程回收。没有启用跨 owner 复用、跳过授权、修改 GPU 页表权限或放宽消息边界。
3. Realm 前端和 RMM 的**单区域资源上限**从 256 MiB 调至 512 MiB；`--large-pool` 显式启用大负载配置。默认测试配置不变。
4. 测试入口新增 `--profiles`，可以直接选择失败负载，不再为每次实验复制修改调度列表。512 MiB 的逐页共享检查放在 GPU/队列解绑之后，检查通过才 detach/revoke。

实现入口：[分配器](../../Linux-Guest-GPU/drivers/char/proxy_vmshm_manager/proxy_vmshm_manager.c)、[Realm 前端](../../Linux-Guest-GPU/drivers/char/realm_xshm.c)、[RMM 上限](../../opencca/tf-rmm/runtime/include/xshm_memory.h)、[RMM 测试](../../opencca/tf-rmm/runtime/tests/xshm_memory_test.c)、[测试调度](../../GPU-SFTP/tests/realm-xshm/run-realms.py)。

| 资源 / 机制 | 默认配置 | 大负载配置 |
| --- | --- | --- |
| 每 Realm | 1 vCPU / 768 MiB | 1 vCPU / 1024 MiB |
| 每 Realm CMA | 320 MiB | 命令行显式 576 MiB |
| 共享池 | 256 MiB | 512 MiB |
| GPU 对象分配区 | 253 MiB | 509 MiB |
| RMM 每次处理预算 | 64 页 | 64 页，未改变 |
| 每 owner / 全局 grant 配额 | 8 / 64 | 8 / 64，未改变 |
| 通信 / 同步 | RMM 授权、可信 IRQ127、P42 task plan / snapshot 优化 | 相同机制 |

大配置消耗更多内存，建池/撤销处理页数也增加；不是零成本扩容。当前 256 MiB 预算本身仍不能容纳上述 ResNet50 峰值，应使用明确的大负载配置。本次没有实现自动无限扩容或跨 Group GPU shadow 隔离。

## 3. 测试与性能影响

GPU 请求 600 MHz、实际 594 MHz；Proxy CPU1 / Client CPU2；同一只读 rootfs、同一模型/计算/glmark 二进制、关闭 shader cache。720p 使用默认资源；大负载使用上表大配置。Native 引用上轮同机实测，未在修复轮重新运行；不把资源条件差异解释为纯分配器性能收益。

| 项目 | 修复前 | 本轮 | Native 参考 | 结论 |
| --- | --- | --- | --- | --- |
| glmark 720p，完整 33 场景 | 1154，干净基线 | **1161** | 1437 | PASS，分数保留 80.8% |
| glmark 1080p，完整 33 场景 | FAIL；939 无效 | **901** | 997 | PASS，分数保留 90.4% |
| ResNet50，100 loops / 2 threads / GPU0 | FAIL；错误时间无效 | **1463.96 ms/inference** | 1162.99 ms | PASS，等效吞吐保留 79.4% |
| IOCTL 共同 profile | 上轮 17/17 | 17/17 | 上轮 17/17 | PASS，不等于全部安全验收 |
| Compute 128 MiB，20+5 | 上轮 PASS | PASS，输出检查通过 | 上轮 PASS | 本轮验证大分配及提交完成 |
| 512 MiB 共享页校验 | 未执行 | 131072 / 131072 页 | 不适用 | PASS，每页校验字，之后 detach/revoke 成功 |
| 双 Client 安全功能回归 | 旧 P42 有独立证据 | 2×17 API、两份 Compute、越权/IRQ 负例 | 不适用 | PASS，3 Realm 健康，非并行性能测量 |

两个 glmark 均为 validation：26 Success / 1 已知 medium-function 数值差异 / 6 Unknown，非预期失败 0；33 个计分场景，BO / 映射 / 提交错误为 0。ResNet50 同时要求 PanVK GPU 后端资格和模型无 Vulkan 错误；它是随机权重性能负载，不能当作推理精度验证。

**大改动影响记录：** 目的为消除 BO 取整浪费并提供有界大负载资源；默认 720p **1154 → 1161，+7 / +0.61%**。只有一次新的独立有效运行，小幅变化按批次波动处理，不声称稳定加速；当前无明显退化证据，保留实现。大负载旧版不通过，没有有效旧分数可计算加速比。

## 4. 安全与失败处理边界

相对冻结 P42 的 58 份跟踪源码仅变更 5 份（其中 2 份为自测）：分配器、分配器权限自测、Realm 前端大小上限、RMM 大小常量、RMM 状态机测试；其余 53 项保持 SHA 一致。RMM 实际映射、来源/端点身份校验、借用者范围检查、撤销 TLBI、隔离失败状态、IRQ 注入策略、P42 生命周期优化没有改动。

本地检查包括实际 C 分配器的 30000 次混合随机操作、152 MiB / 满池分配、对齐/无重叠/计数及 ENOMEM 回滚（ASan/UBSan）；实际 RMM 状态机完整 512 MiB attach/revoke、超额一页拒绝、越权拒绝、既有部分安装失败/隔离/配额检查；另跑 endpoint 与 IRQ 防伪策略测试。这些本地状态机使用模拟翻译后端，不代替板端 RTT/TLBI 证据。

本轮实机正常工作负载未出现相关 GPU fault；没有证明“任意 OOM 后，上层 Vulkan 继续提交非法命令也不会 fault”。第一候选仍保留了该故障证据，不通过隐藏日志或放宽健康检查解决问题。RK3588/OpenCCA 既有 GPT/GPC 模拟边界不变，本次不升级为恶意 Host 下的硬件机密性声明。

## 5. 复现及证据

先部署同组 RMM 固件，再使用冻结包；固件保留实际 SD boot 区备份和 UART，storage ID 固定 2，只更新固件区，Host kernel/rootfs 不变。

```bash
python3 scripts/maintenance/lab-run.py --run-id bo-cap512-targets-r2-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/bo-capacity-20261018/final \
  --workload glmark --performance --benchmark-only --large-pool --suite \
  --profiles ncnn-resnet50 glmark-1080 ioctl compute-128

python3 scripts/maintenance/lab-run.py --run-id bo-cap512-default720-20261018 -- \
  python3 scripts/run/run-realm-xshm.py --images build/bo-capacity-20261018/final \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
```

双 Client 验收命令为 `python3 scripts/maintenance/lab-run.py --run-id bo-cap512-dual-isolation-20261018 -- python3 scripts/run/run-realm-xshm.py --images build/bo-capacity-20261018/final --workload compute`。

上面展示已用 run-id，重跑必须换唯一名称。720p 原运行包为 `cap512-qualified`，与 `final` 的两份 Image、initrd 和配置完全相同；runner 后续只修正大配置的逐页检查命令/位置，默认 720p 路径不变。

| run-id | 退出码 | 判定 / 用途 | 原始证据 |
| --- | --- | --- | --- |
| bo-extent-v1-targets-20261018 | 1 | 第一候选失败：容量不足、GPU fault；1157 / 929 不计有效性能 | [日志](../../GPU-SFTP/log/realm-xshm/bo-extent-v1-targets-20261018/) |
| bo-extent-diagnostic-20261018 | 1 | 容量诊断；1080p 仅两个场景且跳过 validation，不能作完整 PASS | [日志](../../GPU-SFTP/log/realm-xshm/bo-extent-diagnostic-20261018/) |
| bo-cap512-targets-20261018 | 1 | 调度命令拼写错误，模型未执行，修正后重跑 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-targets-20261018/) |
| bo-cap512-firmware-20261018 | 0 | SD 固件部署、Host 恢复 | [固件记录](../../build/firmware-runs/bo-cap512-firmware-20261018/summary.json) |
| bo-cap512-default720-20261018 | 0 | 独立默认配置性能 / 两 Realm 健康 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-default720-20261018/) |
| bo-cap512-targets-r2-20261018 | 0 | 大负载与逐页检查 / 两 Realm 健康 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-targets-r2-20261018/) |
| bo-cap512-dual-isolation-20261018 | 0 | 2×17 API、两份 Compute、越权/IRQ / 3 Realm 健康 | [日志](../../GPU-SFTP/log/realm-xshm/bo-cap512-dual-isolation-20261018/) |

逐项命令和退出码在各 `commands.jsonl` / `summary.json`；wrapper 的完整命令、前后资源与退出码在 `build/lab-runs/<run-id>/`。原始日志下载后逐文件核对远端 SHA；[机器审计](evidence/bo-capacity-fix-20261018/audit.json)包含哈希与判定，[冻结输入](../../build/bo-capacity-20261018/final/hashes.json)对应已测试 Image / initrd。最终 Pi/RK 资源审计无问题；RK 恢复 pmthor、CPU0–1、GPU300MHz，无残留 VM/broker/实验 loop。SD 固件按实际分区读回 SHA 一致，rootfs SHA 保持原样；见 [读回检查](../../build/bo-capacity-20261018/sd-readback-and-rootfs.json)。未部署的中间二进制副本已按清单删除，回收约 234 MiB；失败证据与部署过的冻结包保留。

旧版完整对照报告保留为历史基线：[Native / P42](../archive/20261018/history/GPU_NATIVE_CURRENT_REALM_PERFORMANCE_20261018.md)。
