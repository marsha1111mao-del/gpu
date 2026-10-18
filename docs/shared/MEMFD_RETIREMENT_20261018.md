# memfd共享路径退役与当前Realm基线

2026-10-18。按用户要求删除历史共享实现，保留历史文档供设计与性能比较。当前共享通信只接受RMM授权的Realm池和通知，不提供旧Host broker兼容入口。

| 层 | 已删除 | 当前保留 |
| --- | --- | --- |
| Host/VMM | vmshm-broker子模块；SCM_RIGHTS分发memfd；外部memslot、MMIO doorbell及irqfd集成；旧DT节点生成 | Firecracker启动Realm、GPU集成；通用guestmemfd/virtio内存功能仍有实际用途 |
| Guest | 从Host DT接入共享窗口的分支；原始manager字符设备；通信窗口任意read/write/ioctl；旧轮询dispatcher与无IRQ降级 | RMM身份/通道绑定、IRQ订阅与ACK_ARM、内核队列、对象/权限/extent分配器、生命周期引用 |
| 测试 | 旧单/双Client runner、普通VM32项矩阵、memfd探针和demo及其配置/构建入口 | 当前Realm runner、17项API、Compute/ML/NCNN/glmark负载，Host原生和单VM直通对照 |
| 运行包 | 旧broker/探针二进制、普通VM Client/Proxy Image归档 | RMM-only内核、initrd、新Firecracker；保留单独标注版本的Host/直通参考载荷 |

`vmshm`仍是当前队列和对象协议的代码名称，不能仅凭名字删除；P42执行计划、完成cookie、快照回收和BO容量修复继续使用这些有效代码。通信字符设备仅保留open/release持有引用，以验证忙碌时拒绝unbind。

审计清单确认删除43个源码/脚本/配置文件，共353,425字节；不含现存文件内删去的分支和替换的二进制归档。

旧`vmshm`顶层VMM配置现在返回unknown field；不静默忽略，也不回退Host共享。`build-verified-kernels.sh`的client/proxy目标始终合并REALM_XSHM配置。恢复清单已重打包，避免bootstrap重新装入旧共享组件。主手册、共享测试skill和新机器指南同步更新。

## 验证与性能

构建日志位于`build/memfd-retirement-20261018/`，清理审计见[evidence](evidence/memfd-retirement-20261018/cleanup.json)。

| 检查 | 结果与证据 |
| --- | --- |
| Client/Proxy内核Image | PASS；`client-rmm-only-build.log`、`proxy-rmm-only-build.log`，退出0 |
| ARM64 musl Firecracker | PASS；`firecracker-final-build-r6.log`，退出0；Rust1.83.0/Cargo.lock，交叉libseccomp2.5.5 |
| checkout/归档/语法/rootfs | PASS；`checkout-final.log`，33个脚本、172个运行文件；退出0 |
| 旧配置拒绝 | PASS；实际新VMM返回unknown field vmshm，退出1为预期拒绝；硬件run目录`retired-config.log` |
| VMM测试目标编译 | FAIL；`firecracker-tests-rme-check.log`。现有RealmConfig导入、Vm::new参数、Vmm::new/clone及BufferedStdout测试接口未同步；这些报错路径未被本轮修改。不能声称VMM全量单元测试通过 |
| OpenCCA补丁清单 | FAIL（既有差异）；`opencca-patch-check.log`：opencca-build differs from published patch；保留原有修改，未reset |
| 新组合完整720p | PASS；1157分，run-id `memfd-retirement-720-20261018`，退出0；完整33场景、validation26成功/1已知例外/6无判据，无新增失败，内核健康且两VM正常退出 |
| 双Client功能/权限/IRQ | PASS；`memfd-retirement-dual-20261018`，退出0；两Client各17项API、实际Compute、权限与IRQ负例/合并；三VM退出0、内核受检项无错误 |
| 其他性能/大负载 | NOT_RUN；本轮不重跑完整矩阵 |

清理前完整720p为1161，新组合1157：−4分/−0.34%。单次测量不能证明稳定回退或提速；已超过1000分优化门槛。此次删除的是旧传输与调试入口，不预设会带来帧率提升。当前硬件GPT/GPC模拟边界及尚无GPU跨Group shadow页表隔离的限制不变。

## 复现与证据

当前冻结包：`build/memfd-retirement-20261018/candidate/`；[输入哈希](evidence/memfd-retirement-20261018/inputs.json)、[源码哈希](evidence/memfd-retirement-20261018/runtime-source-hashes.json)、[720p结果](evidence/memfd-retirement-20261018/720-summary.json)、[双Client结果](evidence/memfd-retirement-20261018/dual-summary.json)。RMM仍为BO修复时已部署版本，Host为6.12.0-opencca-pmthor-opp3 #7，不刷写固件/SD。

实际硬件命令（适配器先部署新VMM并验证旧配置拒绝，再调用当前Realm入口）：

```bash
python3 scripts/maintenance/lab-run.py --run-id memfd-retirement-720-20261018 -- \
  python3 build/memfd-retirement-20261018/run-candidate.py \
  --workload glmark --performance --benchmark-only --suite --profiles glmark-720
python3 scripts/maintenance/lab-run.py --run-id memfd-retirement-dual-20261018 -- \
  python3 build/memfd-retirement-20261018/run-candidate.py --workload compute
```

run-id不可复用。新运行使用新ID；VMM已匹配时直接调用`scripts/run/run-realm-xshm.py --images <冻结包>`即可。720p执行计划注册150次、复用455899次，真实IRQ127两侧均有增长。未执行provider replacement独立生命周期、其他性能、大配置和长期压力，不从本次结果外推。

日志在`build/memfd-retirement-20261018/logs/<run-id>/`及RK `/root/GPU-SFTP/log/realm-xshm/<run-id>/`；控制机`build/lab-runs/<run-id>/`记录命令、退出0、前后资源和部署SHA。两批原始日志逐文件SHA校验通过。结束后pmthor、CPU0–1、GPU300MHz恢复，无遗留VM/loop。

压缩安装暂存与失败构建缓存已清除，保留成功构建的可复用工具链/增量目录和验证日志；旧共享运行归档不再双份保留在审计暂存中，Git历史和比较文档保留设计依据。

## 历史比较

历史memfd实现、32项回归与随后fence超时继续保留于[历史归档](../archive/20261018/README.md)。主要对照：[旧IOCTL设计](../archive/20261018/history/PANTHOR_IOCTL_VIRTUALIZATION_DESIGN.md)、[2026-10-15验证](../archive/20261018/history/PANTHOR_SHARED_GPU_FIX_VERIFICATION_20261015.md)、[优化报告](../archive/20261018/history/GPU_GLMARK_PERFORMANCE_REPORT_20261016.md)。不保留另一套失效运行代码作为备用入口。
