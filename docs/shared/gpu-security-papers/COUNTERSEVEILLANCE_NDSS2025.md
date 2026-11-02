# CounterSEVeillance：机密VM中断控制、性能计数器泄漏与GPU任务观察隔离

## 1. 书目、结论与研究位置

《CounterSEVeillance: Performance-Counter Attacks on AMD SEV-SNP》，Stefan Gast、Hannes Weissteiner、Robin Leander Schröder、Daniel Gruss，NDSS2025；正式DOI `10.14722/ndss.2025.241038`。作者来自TU Graz、Fraunhofer SIT及Fraunhofer Austria。官方PDF、会议页、Crossref四作者和题名相符；PDF会议日期24–28 February2025、San Diego。

核心结论：Host无法直接读机密VM的内存和寄存器，并不意味着它无法获取秘密。控制中断和执行粒度，再读取真实性能事件，可恢复秘密相关分支和操作数属性。论文没有破坏SEV-SNP页归属机制，也不是GPU/Arm CCA实现；它为本项目的“中断与统计观察隔离”提供支撑证据，不能替代PORTAL/CAGE/ACAI的直接GPU研究。

对项目最有价值的扩展，是把可信中断拆成通知归属、通知语义、执行干扰与信息暴露。合法事件同样可能泄漏；认证通知来源只解决其中一部分。内存授权依然必要，但不能单独证明执行隐私。

## 2. 原文、版本与审查边界

[NDSS官方页面](https://www.ndss-symposium.org/ndss-paper/counterseveillance-performance-counter-attacks-on-amd-sev-snp/)、[官方全文](https://www.ndss-symposium.org/wp-content/uploads/2025-1038-paper.pdf)、[作者全文](https://gruss.cc/files/counterseveillance.pdf)、[正式DOI](https://doi.org/10.14722/ndss.2025.241038)、[AMD公告](https://www.amd.com/en/resources/product-security/bulletin/amd-sb-3013.html)。完整阅读16页、§I–IX及105条引用；6图、4个Listing，无独立表格或附录；作者版全部16页视觉核对。

作者PDF339425字节，SHA256 `a70f25c044c950d9b092d47b5cf754ce47b19a1c201ea1f4d824a45cd34ee659`；官方PDF343705字节，SHA256 `07a5fe6ca10b7a8b6bd934099438ecf6c67c531f1d1c99e511105d4756a555a3`。使用同一PDFium提取两版，唯一文本差异为会议日期的 `24 - 28` 与 `24-28`；文件字节不同，未声称两版二进制相同或所有视觉元素逐像素一致。

论文基于修改后的SEV-Step；本轮未取得匹配CounterSEVeillance的作者代码、提交、原始trace和运行脚本。精确仓库名搜索零项不证明artifact不存在，也不把另一篇SEV-Step的开源实现当作本文完整artifact。仅执行自写提取、渲染、比对和算术脚本，没有运行作者软件、攻击、模拟器、构建或硬件测试。

## 3. 威胁模型与“被动”的准确含义

攻击者是控制Host/Hypervisor的特权对手，可调度VM、使用APIC timer使其退出、控制页访问权限并读取性能计数器。它了解目标二进制和必要编译信息，可借先前page-tracking方法定位Guest物理页。没有证明不知道目标程序的攻击者能全自动完成定位、路径对应与秘密恢复。

作者称passive，是与修改受害者数据或寄存器的攻击相区分；它仍主动操纵执行时序、中断和页访问。不能描述为无特权、无干扰的旁观者。single-trace指一次目标执行产生的整段轨迹，不是一次中断或一个计数器样本。

VMSA Register Protection不消除这个计数器通道。论文“fully patched”描述作者实验时期与配置；不能据此断言2026年全部SEV-SNP平台仍易受相同攻击，更不能直接推断Arm CCA GPU存在同一硬件行为。

## 4. 系统性计数器实验：覆盖与分母

Linux6.6.0、AMD EPYC7313P / Zen3、nbench2.2.3下分析335个内核列出的PMU事件。native非零226个、VM非零228个、共同非零219个、native独有7个、VM独有9个、两侧均零100个；独立复算100+219+7+9=335。228/335约68.06%，219/226约96.90%。

Zen3只有6个物理PMC槽，部分事件需两个槽；335是可选事件种类，不是335路同时监测。HG_ONLY过滤Guest仍包含其内核。native隔离核与完整Ubuntu VM的额外活动不同，数值比率不能当虚拟化开销或秘密泄漏强度的直接证明。

共同非零的219项按VM/native比率分为4、12、111、44、48项，合计219；111/219约50.68%落在0.8–1.2。100个两侧均零中66个与IOMMU有关，46个来自两个可能未使用的事件组；作者的硬件解释不等于每种零计数原因已经验证。

图1展示100+7+4+12+111+44+48=326项，未画入9个VM独有事件；若以全部335项理解native零值则应为109。记录图示覆盖口径，不据此推翻正文集合计数。正文称选取6个事件，但枚举的是Retired Instructions、Retired Branch Instructions、Retired Taken Branch Instructions、Div Op Count、Div Cycles Busy五个不同名称；不凭空补第六个。

## 5. 轨迹采集与中断控制

状态机利用起始页、目标页、非目标页和结束页切换单步/跳过模式，在vmrun前设置APIC timer，VM退出后读计数。Retired Instructions区分zero/single/multi-step；目标代码外可跳过不关心调用，再在返回页恢复采样。期间Guest timer中断不转发，以避免Guest进程正常被抢占；这与无侵入监测明显不同。

branch增量与taken增量结合已知二进制推断分支：0/0无分支，1/0可识别未跳转条件分支，1/1仍可能是已跳转条件分支或无条件跳转。必须依赖上下文，不是单个计数值自带控制流身份。目标页定位和最终轨迹对应包含人工分析。

单步尝试发生multi-step的比例约0.02%，但1000指令trace中约19.3%、500指令约13.4%包含multi-step；分母不同，不能称99.98%的整条轨迹完全正确。只有一个未知分支时，可扣除已知分支恢复结果；多个未知分支可能保留歧义，需要其他约束、计数器或后续搜索。

## 6. 四个案例：实证强度分开

| 案例 | 配置与作者结果 | 应保留的边界 |
| --- | --- | --- |
| RSA4096私钥 | MbedTLS3.5.2，固定window1，10个不同key均完整恢复；每条trace约20万次单步，平均记录428.9s，范围420–439s | 小于8分钟是记录时间，未证明包含所有定位和人工分析；不是全部默认生产配置或所有window的实测 |
| 6位TOTP | COTP逐字节提前退出比较；50/50在30s内恢复，平均31.1次猜测，端到端18.14s | 假设攻击者可重复提交并约每秒两次；不能推广为所有服务均无速率限制 |
| TOTP长期key | Base32线性查找泄漏字符索引；16字符实验74/86成功，成功例小于1s | 12例因跨字符multi-step失败；本文没有给出0.58s平均值，后续TEEcorrelate数值不回填为本论文实测 |
| HQC | 特定参考实现和编译产生DIV；400次测试398次区分除法结果大小，即99.5% | 展示plaintext-checking oracle，结合先前工作可用于key recovery；没有本文完整HQC密钥恢复端到端时间 |

RSA采用Ubuntu22.04.2 Host/Guest、EPYC7313P。window1让部分控制流简化，再通过mpi_select/mpi_montmul调用指纹恢复秘密位；此前研究对其他窗口的推广不能算本文已实现全部配置。默认编译选项也不消除明确设置window1的实验条件。

TOTP利用首个不匹配字符提前返回，35–70个single-step覆盖关键区间，遇multi-step可重试。500000/31.1约16077倍是平均猜测数量的对比，不是GPU性能提升。论文期望30次，与简单均匀位置且每位完整验证的33次模型不同；是否复用后缀/省略可推断查询需原始实验确认，不把模型差异称为结果造假。

长期key的Base32查找要按真实编译后的jnz解释，不能只看C伪代码就把taken方向反过来。16个完整Base32字符最多编码80bit，不自动表示实际secret有80bit熵。作者提出失败可重复尝试，未证明各次失败独立；其他库仅给出相似代码模式，不是同样完成了攻击实验。

HQC每轮75次除法，除数17669−i，i从0到74。无符号32位被除数时最大商floor((2^32−1)/17595)=244101，18bit。Zen3商小于512为7cycles，否则8cycles，阈值为512×(17669−i)，低商概率约0.21%；特定一周期差通过PMC可见，不依赖同核SMT竞争计时。

HQC每条trace约800次single-step；Div Cycles Busy最早在DIV退休前8条指令增加，作者推测与流水线/推测执行有关，每次除法可测4–8次并忽略至多一个异常值。因此“计数变化”不总是“该指令已经退休”的证据；同理不能用任意GPU统计变化直接当任务完成证明，但本文没有直接测GPU fence语义。

## 7. 缓解与厂商公告：按时间和目标区分

AMD-SB-3013初版日期2024-10-14，确认恶意Hypervisor可监测性能计数器并潜在恢复Guest数据；公告写明SEV/SEV-ES/SEV-SNP不保护这些计数器，建议避免秘密相关控制流/访问，并引用APM Vol2 §15.39的PMC virtualization，计划从Zen5产品开始提供。公告中的planned不证明任意现有Zen5机器已经配置和启用了保护。

论文建议禁用机密VM期间的计数器，或在进入/退出时受保护地切换虚拟计数器状态；这会影响Host性能监测、计费和恶意负载检测。它关闭本文观测通道，不等于解决全部中断、缓存、时间和共享资源侧信道。

只往受害代码添加噪声指令，可能被逐指令观测过滤。SecureTSC在可信启用、Guest实际检查等条件下有助于发现异常停顿，但不是公平调度保证或完整防泄漏证明。论文对TDX中断限速被绕过的讨论应绑定所引版本，不推广为当前所有TDX配置。

Core Slicing通过硬件分区移除不可信Host的相应控制，保护模型和管理权发生变化；它是另一条支撑设计路线，不是本文GPU实现。TEEcorrelate进一步讨论保留粗统计，需单独分析窗口边界、大事件差和跨核计数器，不能把后续提议说成本文已经部署的修复。

## 8. 对ProxyRealm / 多Client项目的具体建议

保留既有主线：RMM认证原始Client；ProxyRealm在建图时检查实际HPA、归属、权限和生命周期，GPU硬件Stage-1限制访问，其他设备授权Stage-2；保护真实表、根配置、关键MMIO和可信固件。本论文不否定这些假设，也不要求以实验板硬件能力限制研究模型。

建议增加“可信事件与观察策略”设计：在RMM/Proxy保护状态中绑定Client身份、device/context、job cookie、epoch和允许事件类型；完成事件仍需原生完整fence链和真实成功/错误状态。共享队列通知只能提示重新检查，不能携带无需验证的完成、授权或释放命令；过期epoch、重复或跨Client事件应拒绝或幂等处理。

再为PMU、GPU performance counter、overflow IRQ、trace/profiling接口、逐job时间戳、队列深度及日志列出配置者和读取者。模型须明确平台如何阻止Host绕开Proxy读取原始硬件状态；只限制Proxy公开API不能声称已保护所有观察通道。精确内部状态与外部聚合统计分别管理，策略绑定会话及证明。

对中断干扰，分别定义不可信方能注入、暂停、重排或抑制什么事件，以及可信层能保证什么。每Client合并/预算可抑制通知洪泛，但不能自动阻止CPU级single-step；必须覆盖真实可控入口，必要故障处理和合法进度仍要保留。Host能无限停机时不承诺无条件有界完成。

若研究目标包含任务时长或工作负载形状隐私，应另行评估完成发布时间、批处理或Telekine式执行模式约束；隐藏PMU后，真实完成IRQ和竞争者等待仍可能泄漏。对当前性能路径不直接加入未经验证的随机延迟，也不把概率统计当内存安全或任务成功判据。

继续区分：通知到达、任务终态、输出可见、应用正确、结果发布、DMA静默、安全复用。cookie/epoch防旧事件误配，但不能单独证明设备不再写旧页；撤销还需停止提交、排空/可信reset、映射失效及安全回收。本项目已有真实fence与私有snapshot语义不能被一个“可信IRQ”标签覆盖。

## 9. 建议验证与直接候选进展

后续安全验证宜覆盖跨Client/过期/重复事件、完成与取消/reset竞争、通知丢失/抑制、统计事件切换、overflow、反复中断与窗口填充、多counter联合及任务形状识别。分别测误接受、丢失唤醒、受害者状态、秘密分类优势、尾延迟与恢复；正常API返回、glmark分数或总IRQ数都不能独立证明全部目标。

直接GPU TEE候选继续保留优先级：本批重新请求XpuTEE正式PDF仍403；LGT4CG的OpenAlex条目匹配DOI `10.1016/j.sysarc.2026.103886`、标记OA但未提供PDF URL，尚未取得全文。GR-T、AccShield、HSMEM、RS-Infer等未完成项不以本篇CPU支撑论文抵扣，也不计为新的CCA GPU架构。

统一记录：补充机密计算中断驱动观测及GPU统计隔离｜glmark未测→未测，分差/百分比不适用｜未改运行代码，无新增性能测量｜16页全文/全部视觉/正式元数据与双版文本比对/AMD公告/独立算术/Notion完整回读；证据目录 `build/cca-gpu-followup-20261027/` 第132批｜无作者代码、攻击、模拟、构建或硬件run-id｜保留研究；设计建议未实现，整体续研active。
