# GPU PM owner 生命周期修复（2026-10-19）

**历史候选：** 本文哈希及1164分属于 PM owner 阶段；当前 Host #23 及 RMM 可信复位/活跃页回收、guest_memfd 关闭顺序修复与1167分另见[开发验收](SECURE_SERVICES_VALIDATION_20261019.md)。保留本文根因、失败与未执行项，旧 PASS 不继承到新候选。

## 结论

本次修复两个 teardown 问题，最终候选已通过选定硬件验收：

- 未创建 Realm 不再进入 RTT fold/unmap 路径，消除以 `NULL` RD 派生地址触发的 `RTT_FOLD` 警告。
- Proxy Realm 获得 GPU MMIO owner 前会绑定当前 `/dev/pmthor` session；runner 反向退出 Realm，保证 owner 最后销毁。`RMI_REALM_DESTROY` 不再在 PM owner 仍为 `PM_RUNNING` 时被拒绝。

最终候选输入：

| 组件 | SHA-256 |
| --- | --- |
| Host Image | `42693e592d9ec67f5a477db4dacefeae334b043db323565183536d6bd13ee0f3` |
| RMM ELF | `a786aabec2c9f9464f26026aa9005695b5221c8d2cb7efd5b5ea86500260f072` |
| U-Boot FIT | `05f7236447b7fb4696516ebd000da70d378d0064a155468b5373ad1b05182b31` |
| idbloader | `ca79e34e28b91cfe3a39c3ca33899e122bb84d9bf7f9c63f96e36f685caed390` |
| Realm runner | `2b984a21bba288d071fa091181d584ef65fba63f1020853df7fff91c973ff690` |
| KVM probe | `1e59e574f90f8c2f831cdb8986888b17411124d71d8db744802825493219b278` |

构建与布局：RMM/U-Boot/Host 构建退出码均为 0，`build/gpu-pm-owner-bind-20261019/final/firmware-layout.txt` 为 PASS；Host 内置 release 为 `6.12.0-opencca-pmthor-opp3`。

## 根因记录

第一轮诊断确认 Host warning 位于 `rmi_realm_destroy()`，不是此前推断的 `RMI_GRANULE_UNDELEGATE()`。RMM 诊断日志显示：

```text
REALM_DESTROY PM rejected: rd=<proxy-rd>
```

Host grant 日志确认该 RD 正是 Proxy GPU MMIO owner。旧流程中 Proxy KVM 只申请 RMM MMIO owner，不因为该授权绑定 `pmthor` session 的 `vm_refs`；因此 `/dev/pmthor` 文件可先关闭，Proxy KVM 随后销毁时全局 PM owner 仍是 `PM_RUNNING`，RMM 正确拒绝 `RMI_REALM_DESTROY`。runner 原按启动顺序退出也会让 owner/Proxy 先于 Client 退出。

诊断 UART 保留于 `build/lab-runs/gpu-pm-compute-realm-destroy-diagnose-20261019-d/` 和 `build/lab-runs/gpu-pm-compute-rd-log-20261019-a/`；最终构建已删除临时诊断字符串。

## 验收记录

| 项目 | run-id / 证据 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 最终 RMM 部署 | `gpu-pm-owner-bind-firmware-deploy-20261019-a` | 0 | storage ID 2，Host SSH 恢复 |
| 最终 Host 部署 | `gpu-pm-owner-bind-host-deploy-20261019-b` | 0 | Image SHA 与内置 release 校验通过 |
| KVM/MMIO/PM 探针 1 | `gpu-pm-owner-bind-kvm-20261019-a` | 0 | PASS |
| KVM/MMIO/PM 探针 2 | `gpu-pm-owner-bind-kvm-20261019-b` | 0 | PASS |
| 双 Client compute teardown | `gpu-pm-owner-bind-compute-20261019-a` | 0 | workload PASS；释放标记、reset、内核负例 PASS |
| compute 后复用探针 | `gpu-pm-owner-bind-postcompute-kvm-20261019-a` | 0 | `/dev/pmthor` 与 RMM PM 状态可复用 |
| 完整 720p glmark | `glmark720-owner-bind-20261019-a` | 0 | 33 场景、validation、clean result、内核健康和资源恢复 PASS |
| glmark 后复用探针 | `glmark720-owner-bind-post-kvm-20261019-a` | 0 | `/dev/pmthor` 与 RMM PM 状态可复用 |

性能统一记录：

```text
修复 PM owner teardown｜对照 1171 / 1170（均值1170.5） → 本版1164｜
-6.5分 / -0.56%｜同为完整离屏720p、33场景、默认256 MiB、请求600MHz/实际594MHz；
本版新增owner生命周期绑定与反向退出，Guest内核/Image/rootfs固定，CPU频率未固定｜
run-id=glmark720-owner-bind-20261019-a，命令见build/lab-runs/glmark720-owner-bind-20261019-a/result.json，
退出码0，日志build/lab-runs/glmark720-owner-bind-20261019-a-collect-b/glmark-720.log｜保留
```

validation 为 26 成功、1 已知数值例外、6 无判据；分数高于 1000 门槛。单轮 -0.56% 不能证明稳定性能回退，只作为本轮组合变化记录。

## 边界

- 未重跑 managed-IOMMU、Guest RSI、API/多 Client 完整矩阵和冻结全项回归；不得继承历史 PASS。
- `group-submit-syncpoint` fence 超时回归仍保留为未解决记录。
- OpenCCA 保护边界仍是模拟/策略边界，不能宣称 hostile Host GPC 强制隔离。
- compute 本轮 `released_pages_count=0`；验收条件是存在释放标记和全部 teardown 检查通过，不宣称非零页引用释放。
