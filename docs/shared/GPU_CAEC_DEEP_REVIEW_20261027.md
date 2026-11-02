# CAEC：跨 Realm 共享内存精读、作者代码静态复核及 GPU 启示

日期：2026-10-27。论文设计、公开 artifact 和本项目建议分别陈述；本次没有运行作者 benchmark。

## 1. 文献信息与证据

**CAEC: Confidential, Attestable, and Efficient Inter-CVM Communication with Arm CCA**，Sina Abdollahi、Amir Al Sadi、David Kotz、Marios Kogias、Hamed Haddadi，EuroS&P 2026，DOI [10.1109/EuroSP68448.2026.00056](https://doi.org/10.1109/EuroSP68448.2026.00056)。本次阅读 [arXiv:2512.01594](https://arxiv.org/abs/2512.01594) 的 v5（2026-05-06），首版为 2025-12-01。

原文与作者入口：[项目](https://caec-paper.github.io/)、[artifact](https://github.com/comet-cc/CAEC)、[RMM](https://github.com/comet-cc/RMM-CAEC)。完整 PDF SHA256：`7915ec3f6adf4c3e683f0bb9ed03029a8540992a49ebf76b384b8121206890c8`。`caec-v2.pdf` 为失败的部分下载，不作为证据；本次实际使用完整 `caec.pdf`。

## 2. 问题：机密 VM 间共享为什么不能沿用普通 Host 共享页

传统 CVM 通过 Host 可见共享区交换数据时，为防 Host 窃听篡改，需要额外加密认证或复制。若大模型权重等不可变数据在多个 CVM 内分别保留，还会浪费内存。

CAEC 的目标是让多个被授权 Realm 直接映射同一组受保护物理页，Host 负责资源供应但不能读写共享内容或伪造参与关系。它保护通信基础设施，并不使任意被授权参与者变得诚实。

## 3. 威胁模型与角色

CCA、RMM 及证明机制可信；Host 可恶意，非参与 Realm 不能访问共享页面。参与者是否可信、能否写、可否转发数据，仍由上层策略决定。恶意合法 Consumer 一旦获得 RW，自然可以写坏该共享区，不能把内容完整性理解为对已授权 writer 的防御。

每个共享区区分 Provider 与 Consumer。角色按共享区决定，不是某个 Realm 在全系统永久只有一种角色。Provider 控制授权和撤销；Consumer 要明确接受并保留自己的 IPA 范围。

可用性依赖 Host 继续供应和调度，物理攻击、侧信道及上层协议完整加固不属于本机制自动解决的范围。

## 4. 设计机制

### 4.1 Confidential Shared Memory 与 APT

共享页面继续位于 Realm PAS，而不是先降到 Normal world。RMM 维护受保护的 APT，记录共享区、Provider、Consumer 和授权；将同一 HPA 映射到多个参与 Realm 的 RTT。Host 可以提出内存配置请求，但不能通过 split-view 把两端指向不同数据而骗过可信检查。

因此，“共享内存由 Host 分配”不必等于“Host 获得内容权限”，关键在 RMM 对实际物理页和参与关系的执行。

### 4.2 身份必须绑定到具体实例

相同 RIM 只能说明代码/初始状态符合测量，不能区分两个实例；RD 物理地址、Host VMID 或 RPV 也不足以独立证明通信对端身份。Host 可重用 RD 地址，让新实例继承旧数值。

论文让 RMM 分配 Realm 标识，并把它作为独立 claim 纳入 attestation，参与方验证该标识和软件测量。对本项目的启示是：Client channel 的来源认证应连接到 Realm 实例及其生命周期，不能只比较请求中的 VMID，也不能因为两个 Proxy 镜像测量相同就认为授权可互换。

### 4.3 双方同意、安装和撤销

SHARE 记录 Provider 对 Consumer 的授权；RESERVE 表达 Consumer 对本地 IPA 范围的接受；ATTACH 执行实际映射。论文模型支持 RO/RW，并把相同 HPA 的映射一致性纳入可信检查。

REVOKE 移除 Consumer RTT 并维护 TLB；销毁及 DATA_CREATE_UNKNOWN / DATA_DESTROY 相关路径要保持多方映射一致。不能只删除 APT 后就宣布旧映射消失。

这里仍主要是 CPU RTT。即使 CPU 页撤销正确，也没有因此证明 GPU 页表撤销、GPU 在途任务停止、SMMU/GPU TLB 清理或设备 cache 已经安全。

## 5. 与本项目最相关的开放问题

CAEC §8.3 “CVM Signaling over CSM” 明确指出：共享内存上的 signaling、synchronization、coordination 仍待研究。标准 KVM/ivshmem 式接口能够实现事件通知，但 strong security、isolation、provenance 仍是开放问题。

这支持研究 Client–Proxy 的可信通知，但不能把一个普通 eventfd 包装为贡献。应进一步定义：谁可以通知哪个端点、事件对应哪个 session/job/generation、合并和重复时如何恢复状态、销毁之后旧通知为何不会改变新对象。

共享区受保护与发送者可信也不能替代参数验证。恶意 Client 在合法共享页中写入别人的对象编号，仍需由 Proxy 根据真实 channel 身份拒绝；不能因消息来自 CSM 就执行。

## 6. 实验与性能边界

| 实验 | 原文报告 | 本项目应怎样使用 |
| --- | --- | --- |
| 平台 | FVP 功能；OpenCCA Rock 5B+、16 GB、1 vCPU/Realm、绑核及高优先级 | 可参考模拟方法，不当成真实硅片全部安全能力 |
| TCB / 改动 | RMM 0.5 增 1825 LoC，表 3 为 6%；Host KVM 525、kvmtool 247、guest driver 594 | 原文贡献段另写 4%，存在口径/数字不一致；引用时保留说明 |
| 通信 | 64 B–32 KiB、1000 次、中位数、轮询；对照 Normal-world plaintext、OpenSSL、MbedTLS | 不是 GPU workload；事件通知安全未由这些轮询实验验证 |
| 对 OpenSSL | 延迟 24–212 倍、cycles 25–209 倍、吞吐 26–204 倍 | 是不同消息长度的范围，不是所有场景 212 倍；主要来自去掉加密路径 |
| 对 MbedTLS | 延迟 4.4–203 倍、cycles 4.5–200 倍、吞吐 4.8–194 倍 | 不能套用到已使用明文 vmshm 的项目 |
| 对明文共享 | CSM 与 Normal-world plaintext 表现接近 | 更接近安全代价接近零的结论，不是对当前项目的巨大提速预测 |
| LLM 权重共享 | 两/三个 Realm，内存减少 16.6%–44.4%；GPT-2 两方 960→800 MB；Llama-3.2-3B 三方 7800→4330 MB | CPU 侧共享数据实验，不是 GPU 推理性能 |
| GPT-2 推理 | 10 次 query，总体两种方式均约 13.4 s | 不宜据此宣称所有共享均无开销 |
| 页管理 | destroy 5196→5236 cycles（0.7%），9.6→10.9 µs（13.5%）；create 3459→3475 cycles（0.4%），9.1→10.4 µs（14.2%） | cycles 与时间的相对开销不同，不应只挑较小一组 |

## 7. 公开 artifact：固定版本与审查范围

主仓库固定为 [`271e1e10decc0cee75329b4ac1c4ad5c58de755f`](https://github.com/comet-cc/CAEC/tree/271e1e10decc0cee75329b4ac1c4ad5c58de755f)。manifest 使用的 RMM `CAEC` 分支在本次查询解析为 [`43ffec10b98a6a5ea6b1116c4429fee684069233`](https://github.com/comet-cc/RMM-CAEC/tree/43ffec10b98a6a5ea6b1116c4429fee684069233)，已完整下载到独立 build 证据目录。未替换本项目任何子模块。

artifact 仍引用若干移动分支；复现时应先解析全部依赖并固定提交，不能简单 `repo sync` 到最新后声称重现论文版本。本次未执行作者构建、刷写或 benchmark，也未证明这个公开 HEAD 与论文评测提交完全一致。

以下是定向静态发现，区分“看到了什么”和“尚需验证什么”，不作为已确认可利用漏洞公告。

### 7.1 实例身份：有 attestation claim，但不能忽略复用

[`runtime/core/realm_tag.c`](https://github.com/comet-cc/RMM-CAEC/blob/43ffec10b98a6a5ea6b1116c4429fee684069233/runtime/core/realm_tag.c) 的 tag 为 8 bit，`CONFIG_MAX_REALMS=10`，优先生成固定序列，后续计数生成并只避开当前活跃碰撞。移除 tag 后可复用；有限空间不能自动提供跨所有生命周期的新鲜身份。

[`realm_attest.c`](https://github.com/comet-cc/RMM-CAEC/blob/43ffec10b98a6a5ea6b1116c4429fee684069233/runtime/rsi/realm_attest.c) 确实读取 tag，token 路径确实把它写入自定义 claim（65001），因此不能说“没有证明绑定”。但**绑定短 tag**与**防止旧实例授权在 tag 复用后生效**是两个问题，还需 epoch/会话撤销和验证策略。

区域 ID 也使用 8 bit，当前注册表上限 64；APT 每类默认 20 区、每区最多 3 个 Consumer。这是原型限制，不等于论文概念上支持扩展的方案错误；报告应分开描述。

### 7.2 ATTACH 参数、重检与权限路径

[`shared_memory.c`](https://github.com/comet-cc/RMM-CAEC/blob/43ffec10b98a6a5ea6b1116c4429fee684069233/runtime/rsi/shared_memory.c) 中 `handle_rsi_csm_attach()` 将 `rec->regs[1]` 转成 `int region_index`，约第 346 行直接索引 `slave_memory[region_index]`，此前未见范围、used、enabled 检查。已查看 RSI dispatch，直接调用该 handler，未见在 dispatch 层补上该检查。正常 driver 传入合法值不能替代恶意 Realm RSI 的边界验证。

RESERVE 检查了授权关系和长度；ATTACH 随后按记录找到 master 并安装页，但未见重新核验当前 share slot/permission，且 [`map_ipa_to_pa()`](https://github.com/comet-cc/RMM-CAEC/blob/43ffec10b98a6a5ea6b1116c4429fee684069233/runtime/rsi/realm_ipa_helper.c) 接口不接收 RO/RW 参数，直接生成 assigned-ram 项。**在已追踪的这条安装路径中，没有看到 APT permission 被用于设置 CPU S2 权限。** 需要进一步结合生成的 S2 PTE 和并发撤销实际测试，不能把“APT 有 permission 字段”当成已执行权限。

handler 逐页安装时，失败退出未见已安装部分的显式回滚；mapping helper 对成功和缺少叶表都返回 0，handler 也未使用返回值验证全部安装。下一步应验证部分失败后的残留状态，而不是假设正常成功路径足以证明原子性。

### 7.3 撤销的线性化与销毁协议

REVOKE 先删除 Provider share、释放 Provider 锁，再操作 Consumer APT/RTT；如果找不到 Consumer RD/APT，可转到返回 SUCCESS 的分支。是否存在并发 ATTACH、销毁或 RD 地址复用窗口，需要完整锁序和状态机分析。目前不能仅以正常删除路径推断任意并发均安全。

公开 DESTROY 要求 `share_count==0`，由调用者先逐个 REVOKE；与论文概述的销毁时遍历撤销存在接口层差异。即便两种方式都可设计正确，也需要写明销毁返回成功时到底保证什么。

### 7.4 实际 benchmark 是往返确认，密码测试不是部署协议

主仓库 [`overlays/guestfs/shmem_test/Makefile`](https://github.com/comet-cc/CAEC/blob/271e1e10decc0cee75329b4ac1c4ad5c58de755f/overlays/guestfs/shmem_test/Makefile) 的 SRC 是 `shmem_test.c`；不要把并存的 `shmem_test_final.c` 或 `shmem_test_main.c` 当成实际构建目标。

实际文件以 `pread/pwrite` 访问 payload 和 seq/ack，sender 从加密/写入前计时直到 receiver ACK，因此 latency 是**经过往返确认的事务延迟**，不能称为纯单向到达延迟。

文件使用固定 key、固定 session ID；每个消息大小和 throughput/latency 两阶段都重新从 sequence 1 开始。GCM nonce 由 session 和 sequence 组成，因此走普通 GCM 的路径会在同 key 下重复 nonce。OpenSSL 又优先尝试 GCM-SIV/SIV、失败才回退 GCM，复现必须报告实际算法与版本；不能把不同模式统称完全相同 AES-GCM 基线。定义的 `read_header()` 在该实际文件只找到定义，未见调用，消息新鲜性也不能只靠这个 helper 的存在宣称完成。

这些是测试程序的安全性与测量解释问题；本次没有量化它们对论文倍数的影响，也不能由此否定 CSM 的所有内存隔离机制。该 benchmark 不宜直接当成安全通信协议移植。

## 8. 对本项目的设计建议

共享控制区可以借鉴 APT 的显式授权和证明身份，但不应直接套用短 tag。Client 实例、session、共享区/对象和设备 reset 的代际应有可信关联；删除旧 session 后，数值相同的新句柄不能继承旧授权。

CPU 共享授权与 GPU 使用授权分开：一个 Client 能读共享状态，不代表能把该 HPA 安装到自己的 GPUVM；Proxy 能读所有 Client 缓冲区，也不代表任一 Client 可指定任意 Proxy 可达 HPA。

通知协议沿用项目现有 RMM 受保护端点，明确 pending/armed/ACK_ARM 的线性化点及 close/reset 规则。通知只提示读取权威状态；合并与重复不会凭空产生完成，旧 epoch 不能确认新 job。

撤销时分别说明 CPU 映射失效、GPU 映射失效、在途执行停止和页面可复用四个条件。CAEC 的 RTT/TLB 机制是 CPU 侧参考，不能替代 GPU quiescence。

## 9. 研究定位与下一步

CAEC 提供了具体而有依据的开放方向：安全的跨 CVM 通知与同步。结合 Devlore，项目可研究设备事件经可信 Proxy 转成多 Client 作业完成的全过程，并以映射/对象生命周期约束资源回收。

先建立状态机、不变量及恶意输入模型，再以实例复用、权限降级、部分映射失败、REVOKE/ATTACH 并发、通知合并和 reset 旧事件验证。只有完成机制、证明/分析和实验证据，才能进一步主张贡献；“把两篇论文拼起来”本身不是成果。

关联：[聚焦报告](GPU_CCA_TEE_FOCUSED_RESEARCH_20261027.md)、[Devlore 精读](GPU_DEVLORE_DEEP_REVIEW_20261027.md)。

统一记录：CAEC 原文与固定 artifact 静态审查｜项目 glmark 未测 → 未测｜分差不适用｜未改运行代码，无新增性能测量｜无硬件 run-id、未执行作者 benchmark、无新增 PASS｜保留证据，代码疑点需独立验证。
