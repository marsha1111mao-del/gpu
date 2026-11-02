# GPU / CCA / TEE 调研：加速收敛范围与剩余核心论文

用户已要求加速阅读、适当省略相关性较弱论文。本轮停止开放式扩展，保留既有报告，不再为了扩大数量继续增加外围论文。当前已完成原库53篇及扩展154份，合计207份，包含版本与技术资料，不等于207套GPU TEE架构。

## 收敛后的交付标准

直接涉及GPU TEE、共享GPU隔离、异构机密内存及可信设备通信的论文继续优先。可靠全文到手后，每篇重点说明威胁模型/TCB、内存与设备归属、提交/完成/中断协议、撤销/reset/回收、评估条件与性能、与项目的关系和限制，写本地与Notion独立报告并核对正文。

不再逐页截图所有PDF；仅在图表、公式或提取歧义影响结论时视觉核对。不再默认展开完整artifact树、外围依赖或大范围源码审计；只在论文关键安全主张需要时定向查证。不运行作者软件、攻击、模拟器、构建或硬件测试。取得全文失败时保留来源状态，摘要/README分析不能冒充全文精读。

## 核心待办：10篇

| 论文 | 主要关联 | 当前证据边界 |
| --- | --- | --- |
| XpuTEE | CPU/GPU联合TEE、低开销通信 | DOI10.1145/3719653及四作者已核；作者页无全文，ACM403；未完成全文 |
| GR-T | TrustZone GPU录制/重放与可信控制 | DOI10.1145/3552326.3567483已核；作者仍链接早期CODY，不能替代正式版全文 |
| LGT4CG | 云GPU轻量TEE | DOI10.1016/j.sysarc.2026.103886已核；OA索引未提供可读全文 |
| HSMEM | CPU–GPU机密内存传输 | 机构确认题名、作者及方向；没有可读全文，不能推断协议 |
| RS-Infer | TrustZone、可撤回内存/NPU隔离 | 机构确认Flex-Mem/Flex-NPU；不是已确认的GPU/CCA实现，需全文 |
| ZeroKernel | 特权攻击者、GPU上下文隔离 | 原库TGS-044；缺可靠全文 |
| SEGIVE | 虚拟化GPU执行、多租户隔离 | 原库TGS-046；缺可靠全文 |
| GINN | GPU TEE下神经网络训练完整性 | 原库TGS-029；已有初步资料，仍缺全文，不计完成 |
| AccShield | CPU TEE与加速器可信访问 | 书目与匹配artifact已确认；仍缺论文全文 |
| SCALE | 机密分布式GPU通信、加密成本与collective选择 | 正式DOI10.1109/HPCA68181.2026.11408582及六作者已核；新取得作者SCALE-tuner README和固定仓库树，但不代替论文全文 |

这是加速后的核心队列，不把全部缺失项改标成已完成。RS-Infer在本队列作为与项目强相关的异构资源隔离候选保留，其NPU与GPU差异需明确。

## 从本轮必做范围移出：17篇

原库7篇：Creating the First Confidential GPUs；Exploiting Bank Conflict-based Side-channel Timing Leakage of GPUs；A Novel Side-Channel Timing Attack on GPUs；Cracking Randomized Coalescing Techniques with An Efficient Profiling-Based Side-Channel Attack to GPU；A Timing Side-Channel Attack on a Mobile GPU；A complete key recovery timing attack on a GPU；GPU obfuscation: attack and defense strategies。

扩展10篇：Securing AI Inference in the Cloud: Is CPU-GPU Confidential Computing Ready?；Salus CPU-FPGA；DICE-anchored Realms；FlexClave；Viola TMC扩展；Hecate；Enabling Confidential VMs Across Diverse ARM Platforms by Retrofitting TrustZone；Secure Dynamic Memory Scheduling Against Timing Channel Attacks；CUSAFE；Let-Me-In。

移出原因是相对当前主线的新增收益较低、已有同方向报告或属于CPU/FPGA/程序内存安全等外围支撑。不是宣称这些论文不重要、已读完或其安全目标已解决。历史原库53/63的计数保留，不把移出7篇写成原库60/63。

## 本轮新增来源进展与边界

SCALE作者JoongunPark的公开仓库SCALE-tuner明确关联HPCA2026论文，README说明其仅研究安全感知collective调优，并基于ASTRA-sim对加密开销建模；支持allreduce、reducescatter、allgather、alltoall，调整ring/tree与OTP缓冲区。以上仅为README说明，不是完整安全协议、真实GPU部署或性能复现结论。

固定提交 `4c74fbf90e781a0964c869b113192362c6fec2fe`，递归树16515项、未截断；论文PDF未在该树中找到。未进一步审计模拟核心，也没有执行安装说明。IEEE入口418、Semantic Scholar全文URL为空、定向arXiv查询零项，均不能证明不存在其他公开全文。证据见第133/134批获取清单。

## 对项目保留的研究主线

第一部分仍是Arm GPU直通、共享实现与性能优化；第二部分仍是GPU任务隔离，包括实际HPA授权/映射生命周期和可信中断通信。可信ProxyRealm控制SMMU、RMM认证Client、GPU建图时软件授权合成Stage-1等按既有研究假设分析，不以实验板能力否定设计。

优先分析提交到完成的身份与状态链：Client/device/context/job/cookie/epoch、真实原生fence、结果发布、错误与reset处理；通知不等于任务完成，完成不等于DMA静默和安全复用。CounterSEVeillance与TEEcorrelate作为已有观察隔离支撑保留，不继续沿CPU侧信道无限扩展。

统一记录：按用户要求收敛调研并减少低收益审计｜glmark未测→未测，分差/百分比不适用｜未改运行代码，无新增性能测量｜证据目录build/cca-gpu-followup-20261027/第133/134批；无作者代码执行、攻击、模拟或硬件run-id｜保留；核心10篇仍未达到全文完成标准，整体goal维持active。
