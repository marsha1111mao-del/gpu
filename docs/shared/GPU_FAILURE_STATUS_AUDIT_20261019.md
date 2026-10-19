# 场景二：失败项状态复核

**2026-10-20口径补充：** 用户已将可信页表/控制内存、关键配置、任务MMIO与未授权CPU/DMA访问的物理保护明确为目标平台已有能力假设。统一安全IOMMU服务、Host与其他IOMMU设备的托管映射控制转为“已实现，当前范围验收完成”；当前状态清单为已实现9项、部分实现5项。下文保留2026-10-19的31类判定与原7/7分类历史，硬件绕过FAIL不改成PASS，平台能力不再作为模拟开发缺口。见[平台假设与状态迁移](SCENARIO2_PLATFORM_ASSUMPTIONS_20261020.md)。纯文档整理，未改运行代码，无新增性能测量。

日期：2026-10-19。复核当前Notion「假设场景2实现」及其引用的开发报告。
**验收口径按用户最新要求收敛：以硬件模拟行为、总体设计一致和主流程可运行为准。**
本轮owner/映射、双Client计算、受限PM、撤销及backing回收等选定模拟流程已通过。
普通VM/PL330的真实物理隔离、权限穷举和长期攻击测试作为边界保留，不作为本轮模拟验收门槛。
Group fence本轮通过、历史超时保留观察；tracefs旧诊断失败不阻塞主流程。

**原记录归为29类，另发现并处理2项本轮测试问题；共31类：17类已修复或仅在所列范围通过，
9类为已纠正/已退役的历史流程与诊断，1类仅功能恢复，4类仍未闭合。**
这些数字包含本地测试与探针问题，不能解释成17项硬件安全能力已经完成。

当前Host仍为 `6.12.0-opencca-pmthor-opp3 #31`、protected hVHE、RMM timer v6。
复核未修改Host/RMM/Guest内核运行代码；仅修改Guest IOMMU测试的输入检查与失败清理。
**选定模拟主流程验收通过；完整硬件对抗隔离不作完成声明。** 保留原已实现7项、部分实现7项、原失败/NOT_RUN/未解决6项
及全部历史结果。本报告给出当前判定，不覆盖或删除原始FAIL。

## 判定标准

下表区分有修复依据的条目和“未复现/恢复”的条目；后者可以满足本轮模拟功能检查，
但不写成间歇问题已经根治。旧候选的PASS只证明旧候选；
工具退役、范围外和NOT_RUN也不等于安全通过。

[结构化证据](evidence/secure-services-20261019/failure-status-audit.json)保存完整命令、
退出码、run-id、原始证据目录、源码指纹及逐项状态。
所有硬件操作均经 `scripts/maintenance/lab-run.py` 独占执行，未重放旧失败内核或固件。

## 逐项判定

| 编号 / 原失败 | 当前判定 | 依据与限制 |
| --- | --- | --- |
| F01 KVM owner reopen / destroy 失败 | **已修复，所列路径通过** | pmthor session绑定、最终关闭前可信撤销；当前11项owner/OPP/释放复验；`failure-audit-host-kernel-20261019-a` |
| F02 未创建Realm触发NULL RD / RTT_FOLD警告 | **已修复，所列路径通过** | REALM_STATE_NONE提前返回；实际Realm完整退出与增量内核健康；`failure-audit-host-kernel-20261019-a` |
| F03 GPU backing退出WARNING / page-reclaim伪PASS | **已修复，所列路径通过** | guest_memfd最终关闭前quiesce；需当前GPU backing专项与生命周期健康；`failure-audit-gpu-backing-20261019-a` |
| F04 首次private-unmap修复过早撤销，无法hold backing | **已修复，所列路径通过** | 错误private-unmap分支已删除；需当前hold/destroy-denied/release验证；`failure-audit-gpu-backing-20261019-a` |
| F05 空闲GPU解绑失联 / RCU stall | **已修复，所列路径通过** | remove返回前停机/关闭时钟，devres幂等；当前无诊断电源循环；`failure-audit-power-20261019-a` |
| F06 protected模式RME不可用 | **已修复，所列路径通过** | EL1 Host RME初始化和Realm/普通pKVM分支隔离；当前真实REC执行；`failure-audit-compute-20261019-a` |
| F07 Host/RMM VMID位宽不匹配 | **已修复，所列路径通过** | 按实际位宽分区；当前6项VMID与实际Realm；`failure-audit-vmid-20261019-a` |
| F08 CPU2特征未核验导致720p启动失败 | **已修复，所列路径通过** | 主启动maxcpus=4完成核验；原#31完整720p1159和本轮CPU恢复证据；`failure-audit-compute-20261019-a` |
| F09 共享池2944/65536处超时 | **功能恢复，根因未闭合** | v6完整池/glmark已通过；timer/调度交互尚无唯一根因或长期稳定性证明；`failure-audit-compute-20261019-a` |
| F10 RMM映射计数旧CMake缓存导致初始化-34 | **已修复，所列路径通过** | 映射计数4；v6部署及实际REC执行，当前timer单元通过；`failure-audit-compute-20261019-a` |
| F11 RMM MMIO映射排序导致初始化-1 | **已修复，所列路径通过** | GICR在UART之前；v6启动与实际REC执行；`failure-audit-compute-20261019-a` |
| F12 部署前无驱动/部署后pmthor触发POSTFLIGHT_FAILED | **历史外层失败保留** | 部署子命令恢复RME1，但外层原rc1不改；当前一致前后资源单独验收；`failure-audit-compute-20261019-a` |
| F13 Host内核ioremap物理MMIO绕过 | **限定范围已解决** | 可信Host stage-2区间拒绝及异常交付；两个别名10项−14；`failure-audit-host-kernel-20261019-a` |
| F14 Host /dev/mem物理MMIO绕过 | **限定范围已解决** | 可信Host stage-2拒绝；5项−14与SIGBUS7/code3；`failure-audit-host-devmem-20261019-a` |
| F15 普通VM物理MMIO绕过 | **未解决，本轮复现** | RMM owner拒绝第二Realm不覆盖普通VM物理访问；不采用普通VM页表接管；`failure-audit-ordinary-vm-20261019-a` |
| F16 绕过通用IOMMU层直接调用driver map_pages | **限定范围已解决** | RMM托管root/真实表及direct_driver_delegation_denied；不证明Host原始CPU写PTE受限；`failure-audit-iommu-20261019-a` |
| F17 三套PL330读取/写入DELEGATED页绕过 | **未证明已解决，本轮未复测** | 非IOMMU DMA不在当前准入范围；保留六个实测防护失败，不称已修复 |
| F18 Group submit fence间歇超时 | **本轮未复现，仍未闭合** | 当前双Client复验只判断本次是否复现；缺少确定根因/修复及针对性长期证据；`failure-audit-compute-20261019-a` |
| F19 tracefs set_graph_function PermissionError / 空trace | **诊断失败未证明解决** | 诊断instance已清理；没有成功采样证据，不能以GPU运行通过认定采样问题解决 |
| F20 Pi非交互sudo导致清理计划失败 | **历史流程已纠正** | 后续-c使用已授权stdin凭据成功；本轮不删除文件 |
| F21 汇总器未回收glmark日志即读取导致FileNotFoundError | **历史流程已纠正** | 原硬件rc0；后续回收8个日志并校验SHA后续跑，原汇总rc1保留 |
| F22 IOMMU容量耗尽单元使用已授予Host域触发断言 | **本地测试修正并通过** | 独立未绑定域做容量测试；当前secure-IOMMU单元含失败隔离通过 |
| F23 旧固件打包器要求ELF段大小相等 | **旧工具已替换** | 外部FIT偏移/大小/hash重建；旧helper未宣称已修好，新v6真实启动 |
| F24 FIT审计假定FDT有load属性导致KeyError | **历史流程已纠正** | load可选；v3后续部署，v6布局和实际启动证据 |
| F25 诊断kprobes指针数组/格式导致编译失败 | **诊断已退役** | 诊断构建后通过且最终删除，不作为当前生产输入 |
| F26 诊断上传目录在重启后缺失 | **诊断已退役** | 后续诊断-b上传完成；最终无诊断电源循环独立通过 |
| F27 protected启动实验错误假定extlinux路径 | **历史流程已纠正** | 首次未改配置；后续-b正确挂载并逐字节恢复 |
| F28 增量构建遗漏LOCALVERSION生成6.12.0+ | **历史流程已纠正** | 显式LOCALVERSION；当前#31内置release及板端module匹配 |
| F29 Host #30异常重构遗漏Guest向量PC赋值 | **已修复，所列路径通过** | 恢复赋值、重建#31；当前真实REC、异常辅助单元与物理异常负例；`failure-audit-compute-20261019-a` |
| F30 本轮误选旧Host授权探针导致action11返回EINVAL | **已修复，所列路径通过** | 误选device-assignment旧模块；当前runner需要iommu-irq模块。新增控制机预检在SSH前拒绝缺少fault检查的模块；`failure-audit-guest-device-20261019-b` |
| F31 设备授权中途失败未卸载Guest探针，teardown出现9条WARNING | **限定范围已解决** | 失败路径漏掉Guest模块卸载；新增异常清理并保留原失败，需故障注入证明Guest卸载和Host生命周期健康；`failure-audit-guest-device-cleanup-20261019-a` |

F03/F04指原GPU backing正常生命周期问题；本轮设备授权异常清理发现的独立缺陷另列F31，
不能用GPU正常路径的PASS掩盖异常路径。F16原失败是绕过通用层直接调用驱动 `map_pages`；
它的专项修复不代表Host任意原始CPU改写IOMMU寄存器或RMM页表已经受硬件阻断。

## 本轮独立复测

每行完整命令/退出码在结构化证据及 `build/lab-runs/<run-id>/result.json`。
控制机输出另存 `build/failure-audit-20261019/`。

| run-id | 结果 | 实际覆盖 |
| --- | --- | --- |
| `failure-audit-compute-20261019-a` | rc0 | 双Client各17项API，两个Group fence、实际计算、权限/IRQ/内存通过；三个Realm退出0/0/0，Host/Guest健康；8份原始日志回收并逐一校验SHA。 |
| `failure-audit-host-kernel-20261019-a` | rc0 | 两个ioremap别名及重访10项−14；owner/OPP/释放11项、卸载和健康通过。 |
| `failure-audit-host-devmem-20261019-a` | rc0 | 5项−14、SIGBUS7/code3；owner/OPP/释放11项和健康通过。 |
| `failure-audit-ordinary-vm-20261019-a` | **rc2 / FAIL_BYPASS_DETECTED** | RAM控制通过；指定Realm持有GPU时普通VM仍可写IRQ mask 0→1→0并恢复。 |
| `failure-audit-power-20261019-a` | rc0 | 无诊断空闲domain on→off→on、非法OPP拒绝、恢复后KVM11项和健康通过。 |
| `failure-audit-vmid-20261019-a` | rc0 / 6项 | VMID分区、重复拒绝、销毁后复用及模块清理通过。 |
| `failure-audit-iommu-20261019-a` | rc0 / 22项 | codec真实root/parking/重绑、直接驱动映射拒绝和准入通过；实际codec DMA仍NOT_RUN。 |
| `failure-audit-guest-rsi-20261019-a` | rc0 / 17项 | Guest RSI真实domain/map/query/unmap与准入，完整生命周期健康。 |
| `failure-audit-gpu-backing-20261019-a` | rc0 / 3项 | 活跃GPU backing的原始RMI DATA_DESTROY被拒绝、RTT不变、正常释放；Host/Guest健康。 |
| `failure-audit-guest-device-20261019-a` | **rc1 / FAIL** | 本次误选旧Host授权探针，action11返回EINVAL；失败清理漏卸载Guest探针，随后9条Host teardown WARNING。原结果保留。 |
| `failure-audit-same-version-reboot-20261019-a` | rc0，仅恢复 | 独占锁内同#31重启清除本次隔离残留，boot-id变化，protected/pmthor/CPU0–1恢复；UART和前后资源保留。 |
| `failure-audit-guest-device-cleanup-20261019-a` | rc0，仅异常清理验收 | 故意绕过控制机预检，使用旧探针重现EINVAL；子测试仍FAIL/rc1，新增Guest卸载返回0、Realm退出0、Host生命周期PASS且无WARNING。**清理通过不改写功能失败。** |
| `failure-audit-guest-device-20261019-b` | rc0 / 14项 | 使用匹配的iommu-irq Host探针，Guest grant/BIND/FAULT/解绑/重绑/revoke及backing释放通过，Host/Guest健康。 |
| `failure-audit-guest-rsi-20261019-b` | rc0 / 17项 | 修正worker后重跑普通RSI路径；卸载与Host/Guest生命周期健康通过。 |
| `failure-audit-gpu-backing-20261019-b` | rc0 / 3项 | 修正worker后重跑GPU backing；活跃页回收拒绝、RTT不变和释放通过，Host/Guest健康。 |

另外，`check-dma-guard.sh`、`check-secure-iommu.sh`、`check-opencca-host-mmio.sh`、
`check-opencca-vmid.sh` 和 `check-opencca-timers.sh` 均独立退出0，日志在控制机复核目录。
包含ASAN/UBSAN、失败隔离、18581组MMIO区间/393216组异常状态、
8/16位VMID以及131072组timer转换/66次有界退休检查。
Python语法检查通过；旧授权探针在访问硬件前被控制器以退出2明确拒绝。

最终资源检查退出0、issues为空：Pi/RK无实验进程，RK保持pmthor/CPU0–1且无loop；
Pi系统swap loop保留。完整前后资源在控制机复核目录，结构化证据附资源摘要。

## 本轮新增问题的根因与修正

本次误用了 `device-assignment/host-module/opencca_iommu_assignment_probe.ko`
（SHA `47caec8b2df8980d0427aebdaa45b642640b2a5bd52e6ae8b1e3cd40f15f46b8`），
而当前worker要求 `iommu-irq/host-module/` 的版本
（SHA `dbae41681ab63a0f5fd6051b9d497ccb5a7e5a8f5de9075dcbbeb07a028a670a`）。
旧模块没有Host fault操作，vermagic相同也不能证明测试ABI匹配。
控制机现在检查当前验证依赖的fault标记，在任何SSH/部署前拒绝不匹配输入。

设备授权中途失败时，旧worker只撤销Host授权并halt，漏掉Guest探针的卸载；
Guest domain仍持有backing引用，RMM正确拒绝回收，Host teardown因此产生WARNING。
worker现在记录Guest探针是否加载，在异常路径先卸载释放backing再退出Realm，
并保持原功能失败。真实异常清理测试独立验证了这一点；没有放宽RMM的页面回收检查。

## 仍未解决与未执行

- 普通VM物理MMIO绕过本轮再次确认；继续按RMM资源归属与平台物理访问强制检查推进，
  不引入EL2接管普通VM页表。
- Group submit fence本轮两个Client均通过，但没有确定的间歇故障根因/修复和长期针对性证据。
  原 `fresh-clone-20261015-quick` 超时仍保留为未解决。
- 原三套PL330委托页读写绕过仍无修复证明，本轮未重跑；无IOMMU DMA保留原范围边界。
- tracefs PermissionError/空trace没有成功复测，保留为诊断未解决；不将它当成GPU功能失败。
- 共享池超时在v6上恢复并完成过完整720p；仍不宣称其唯一根因或长期稳定性已经证明。
- Provider replacement仍NOT_RUN；其他设备真实DMA、Host原始配置写入、可信控制页、
  完整攻击/故障/长期压力及冻结发布矩阵尚未完成。历史live GPU28项不继承给本轮。
- 本报告复核当时最终废弃产物清理为NOT_RUN；后续2026-10-20已执行[三端清理](WORKSPACE_ARTIFACT_CLEANUP_20261020.md)，原失败日志、回退、SD备份、当前输入与模型保留。
  资源空闲不代表旧故障中的所有RMM对象都已释放，因此首次异常后执行了受锁同版本重启。

统一记录：复核失败状态并修正测试输入/异常清理｜
对照Host #31完整720p1159 → 本轮未测｜
分差/百分比不适用｜
未改Host/RMM/Guest内核运行代码，无新增性能测量，仅测试入口和文档变化｜
本页run-id、命令/退出码和结构化证据｜
保留专项修复与全部失败，选定模拟主流程通过，不替换原冻结1171/1170；完整硬件隔离不在本轮验收口径内。
