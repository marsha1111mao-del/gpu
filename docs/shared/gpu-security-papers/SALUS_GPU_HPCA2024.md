# Salus-GPU：异构内存迁移中的稳定身份、安全元数据与缓存生命周期

研读日期：2026-10-27。完整阅读作者公开16页全文，包括67条参考文献与两页artifact附录，核对正式DOI、作者出版页及公开实现入口。本轮仅文献与静态材料分析，未运行GPU、GPGPU-Sim、CUDA、VM或实验。未改运行代码，无新增性能测量。

## 1. 准确书目与全文来源

- 题名：Salus: Efficient Security Support for CXL-Expanded GPU Memory。
- 作者：Rahaf Abdullah、Hyokeun Lee、Huiyang Zhou、Amro Awad。
- IEEE HPCA 2024；DOI：10.1109/HPCA57654.2024.00027；IEEE文献号10476444。Crossref和OpenAlex页码记录为1–15，当前取得的作者camera-ready实际16页、含artifact附录，本文区分这两个口径，不补造正式会议录连续页码。
- [正式DOI](https://doi.org/10.1109/HPCA57654.2024.00027)；[IEEE条目](https://ieeexplore.ieee.org/document/10476444/)；[作者出版列表](https://hzhou.wordpress.ncsu.edu/publications/)；[作者全文](https://hzhou.wordpress.ncsu.edu/files/2024/02/Salus_HPCA_24_Camera_Ready.pdf)。

本报告使用2476083字节、16页作者稿，SHA256 9e090b064ba2875cdf5a15c3d99aabc6d701ef2d4f3964599d9bc09070975999。作者页明确链接该PDF并标记Artifact available；不是将第三方同名文件当作原文。证据在build/cca-gpu-followup-20261027，包含salusgpu-author-batch23.pdf、salusgpu-batch23.txt、作者页面、Crossref/OpenAlex及本轮获取记录。DBLP返回反机器人HTML，不视为取得其XML书目。

Salus-GPU与ASPLOS2024的Salus: A Practical Trusted Execution Environment for CPU-FPGA Heterogeneous Cloud Platforms是不同工作，不能共用架构结论或artifact。本文是GPU安全内存机制解读，不是新的CCA GPU管理系统。

## 2. 问题动机和核心贡献

显存容量有限，可以用低带宽CXL扩展内存配合高带宽HBM/GDDR，并将热点页面迁入显存。传统每种物理内存分别维护加密计数器、MAC和完整性树，页面移动就要按新位置重新计算安全元数据、重加密，且GPU通道交错会把同一页元数据分散在多个分区。

Salus让显存成为CXL地址空间的缓存，以稳定CXL地址参与加密认证，物理缓存位置改变时仍可使用同一逻辑安全身份。再用适配交错粒度的split counter、CXL侧计数器压缩、按访问取元数据和细粒度dirty tracking，减少迁移带来的带宽浪费。

贡献重点是迁移友好的安全元数据组织。它没有重新定义恶意Host下的Client授权，也没有提供可信GPU任务提交、固件加载或跨Realm完成协议；这些仍应由完整TEE系统处理。

## 3. 威胁模型与信任基础

可信边界为GPU芯片及片上组件，HBM/GDDR、CXL扩展内存和片外存储不可信。论文重点防片外总线窃听、数据篡改、拼接和旧版本重放；机密性用counter-mode encryption，完整性用MAC，新鲜度用Bonsai Merkle Tree（BMT）及片上可信根。

功耗、时序、电磁等侧信道明确排除。它假定片上控制逻辑、密钥、计数器处理、地址映射及认证检查可信；没有展开恶意Host如何修改GPU页表/MMIO、设备固件如何证明、多Client如何分配独立密钥与地址域。因此不能把“GPU内存安全”扩张为任意GPU执行路径都完整可信。

物理页移动并不取消地址授权：稳定地址只用于决定数据的安全身份，可信控制器仍须决定它当前对应哪个位置、哪个版本和哪个访问者。对于本项目，RMM身份与ProxyRealm实际HPA授权是另一层必须保持的责任。

## 4. 统一安全身份与位置翻译

Salus用CXL地址作为长期不变的地址，CME的空间唯一性和MAC关联使用该地址；显存缓存位置用于路由及查找数据。每份数据只有一套可跨两级内存使用的安全元数据，避免因纯位置改变而强制重加密。正常LLC miss和writeback仍触发安全操作。

论文把CPU/GPU页表固定为CXL地址，L1也按该地址标记；访问L1 miss后，在进入片上互连并选择L2/显存分区前，再查CXL→GPU映射。每个GPC连接有128项双端口mapping cache，miss由可信控制逻辑读映射、触发页迁入并在复制及映射建立后回复。

这里避免的是位置缓存迁移导致的原页表变动/TLB shootdown，并不是取消所有失效。显存页被逐出时，旧CXL→GPU mapping cache项仍必须失效；L2按显存位置寻址，重用该位置前的数据/元数据/在途访问协调仍要正确。

“稳定逻辑身份”和“当前实际物理位置”分离，可作为项目对象ID/实例代次与HPA映射的对照，但不能直接在项目中省略实际页授权、GPU页表撤销或IOTLB失效。现有直接HPA Stage-1路径与Salus两级位置缓存是不同架构，迁移该思想需明确适用层次。

## 5. 与GPU通道交错对齐的计数器

原split counter把一个major与多个minor放在一起；同一major覆盖的数据超过单次交错chunk，页面分布到不同通道时会出现多个major版本、非局部overflow与额外重加密。

Salus按256B交错chunk组织counter group，显存侧每个major关联8个minor，一个counter sector包含两个group，并给每group加入32位CXL页tag。这样搬运的计数器与实际搬运的数据chunk对应；显存内按本地位置索引元数据，认证计算仍用CXL地址。

32位CXL tag是元数据归属/缺失判定字段，不是MAC或不可伪造Client capability。安全仍依赖可信映射与元数据认证；同一显存位置可在不同时刻服务不同CXL地址，不能只因本地位置相同就复用旧metadata。

## 6. Collapsed counters：保留的重加密成本

CXL侧可把一个chunk的minor视为全零，只保留32位major；迁入显存时展开为细粒度split counter。逐出时若任一minor非零，则major加一、所有minor归零，并重加密受影响chunk。纯搬运同一版本的密文与计数器不同于把发生写入的版本压回较粗计数器状态。

传输时把major放入对应MAC sector空余位置，减少单独counter传输。正文讨论56位MAC，并不因此获得无条件128位伪造强度。CXL实际存储仍保留独立counter block供BMT使用，不是删除了CXL counter状态或完整性树。

显存与CXL分别维护本地freshness tree。要使一次迁移具有安全含义，仍需关联数据、稳定地址、计数器、MAC及可信根状态；单独存在两棵树不自动证明任意迁移并发/掉电时都原子一致。论文没有完整展开异常中断、counter wrap、租户更换密钥及持久恢复协议。

因此论文概括的“消除迁移安全操作”需按设计收窄：它减少纯位置变化引起的重复工作，IV-A2/IV-A4明确仍有dirty chunk压缩回写时重加密，以及访问时认证/树校验，不能写成所有迁移与回写完全无需安全计算。

## 7. 按访问取元数据与dirty tracking

页面迁入并不表示每个通道chunk都会被访问。Salus可只在实际访问时取对应MAC/计数器，用CXL tag判断显存中元数据是否匹配；不匹配则向扩展内存补取。这样节省从未触及数据的安全流量。

正文“optimistically访问”是先假定元数据可能已存在并检查tag，不是授权未认证明文产生外部副作用。论文没有提出通用GPU认证前执行屏障协议，不能把此机制等同TensorTEE式延迟验证或据此允许完成记录提前成功。

dirty tracking按交错chunk而非整页记录，bitmask放入辅助映射。控制逻辑额外有32项buffer，写请求按CXL地址更新dirty位；mapping cache可静默逐出，因为最新dirty状态在控制buffer或内存。buffer满时LRU回写，页逐出只传dirty chunk及相关元数据。

dirty mask和映射都影响哪些数据会被回写，属于安全相关控制状态。保守丢失dirty位可能变成数据丢失/旧版本恢复；让一个页继承另一页的dirty mask或tag也可能产生错误。论文的优化依赖这些字段按同一页实例正确初始化、更新、失效，不能只保护数据密文而忽略它们。

## 8. 安全论证的力度与尚未覆盖事项

论文主张保持已有GPU内存保护的安全水平，以稳定CXL地址防止同一显存位置不同数据复用OTP。该论点需要同密钥下稳定地址与计数器组合不重复，MAC绑定相同地址/版本，BMT根及映射不被攻击者回滚；“地址永久”并不单独解决地址释放后重新分配的新代对象问题。

正文未给出完整多租户密钥域、Client身份到CXL地址的授权协议、设备reset后的树根恢复、映射miss/逐出/写回的完整并发状态机或形式安全证明。此处是证据和适用范围限制，不是已经运行发现漏洞。不能据缺少这些内容断言作者芯片实现被攻破。

对项目建议把对象代次、映射代次与设备epoch分开追踪：对象逻辑身份可跨物理位置存活，但撤销后不能因稳定ID或缓存命中恢复旧授权；真实fence、输出可见与实际停止访问继续分别建立证据。

## 9. 模拟平台、基线和配置

全部主要结果来自扩展GPGPU-Sim v4.0的模拟，基于Volta模型：80个SM、1132MHz，每SM 256KB寄存器、32KB L1、96KB shared memory；总6MB L2；HBM 32分区、850MHz、868GB/s；CXL带宽主配置为HBM的1/16。扩展容量表写up to 16TB，不能据此声称真实分配了16TB实验数据。

显存主配置容纳应用footprint的35%；MAC、counter、BMT cache各2KB/partition，128B块、4路sector、256 MSHRs；MAC延迟40周期，每分区一个流水AES引擎。基准来自Rodinia3.1、Parboil、Lonestargpu2.0和Pannotia，选不同内存强度。文中动机提LLM/GPT3，不表示已完成端到端LLM训练或机密推理评估。

No-security、传统安全baseline和Salus使用相同异构内存配置比较；图10 IPC先各自归一到无安全系统，再比较安全机制。高于传统安全baseline的百分比不是高于无安全Native，也不是本项目Stage-1授权或IRQ路径性能。

## 10. 定量结果及内部口径差异

| 作者报告 | 结果与限制 |
| --- | --- |
| 主要性能 | 摘要/结论几何平均提升29.94%，最高190.43%；V-B1写29.4%，保留差异，不自行确定为同一舍入 |
| 安全流量 | 摘要称降至传统baseline的47.79%，最低17.71%；V-B2称减少52.03%，其剩余47.97%与摘要略不同，不当成完全一致 |
| 带宽利用 | CXL安全带宽使用相对baseline少14.92%，HBM安全带宽少2.05%；不同于总内存流量/端到端运行时间降低相同比例 |
| CXL带宽敏感性 | HBM的1/32、1/16、1/8、1/4时，相对传统安全提升32.79%、29.94%、32.90%、21.76%；非单调关系不能简化为带宽越低必然收益越大 |
| footprint敏感性 | 显存容纳20%/35%/50%时，V-B5均值为51.64%/34.48%/26.83%；35%项与主实验29.94%不一致，原文未充分解释，不拼成单一一致基线 |

NW、B+tree、Lava等只访问迁入页较少通道的工作负载收益更大；Backprop、Segmm可能持平或变慢，因为最终访问多数通道且访问时间分散，按需验证树的局部性不如baseline一次集中验证。所有数字只支持作者所模拟配置，不证明所有模型、页大小、租户数和迁移策略同样获益。

部分图中完整逐柱数值未提供可离线复算原始表；本文没有根据概述推算全部IPC或冒充重新跑出作者均值。未测本项目glmark、ML或共享吞吐。

## 11. Artifact核验与可复现性

附录明确给出扩展GPGPU-Sim、Ubuntu18.04、GCC/G++7.5、CUDA11.8、VM/压缩包选择及Fig10–12复现流程。作者建议至少20GB磁盘与40GB内存，多核64核完整实验约1.5天；这些是复现资源说明，本轮没有安装依赖或运行提供的命令。

附录给出的[Google Drive目录](https://drive.google.com/drive/folders/15UfYMRVOGaauKyf7U5YR31ribBeI4mIK)在本轮两种公开目录入口均连接超时，未取得列表、压缩包、源码或匹配提交。附录checklist同时标记Publicly available? No，而作者出版页写Artifact available；保留发布范围差异，不能据网页标签声称实现已公开可下载。

Salus+CXL及Salus GPU memory有界GitHub仓库搜索均未找到匹配实现，也不以同名CPU-FPGA仓库替代。当前没有Salus代码审计、源码哈希、原始数据重算或硬件复现的结论。

附录结果采集需手工记job范围、修改simNums并按N/B/S切换；脚本正文salus_results_collection与命令salue_results_collection拼写不一致，PDF文字中的部分目录分隔符也需结合实际代码确认。未取代码前不能判断实际哪个正确；这些是复现指引限制，不作为运行失败或代码漏洞证据。

## 12. 与已有论文和项目关系

PSSM针对partition/sector布局优化安全元数据，Common Counters压缩具有相同更新模式的计数器，Plutus减少元数据带宽；Salus进一步考虑跨内存层动态迁移，说明优化不能破坏稳定身份、counter生命周期与认证版本绑定。它和HPCA2024安全多GPU元数据是互补问题，不可把单GPU两级缓存当作多GPU/多Realm协议。

PORTAL、CAGE与ACAI更直接处理可信管理、设备访问和归属。Salus没有替代这些机制；对ProxyRealm的参考是数据位置缓存与安全身份分离后，辅助映射、tag、dirty及代次也必须进入安全状态范围。PhantomMap所强调实际页和生命周期检查仍适用。

本项目保留既定假设：RMM认证原始Client，可信ProxyRealm统一控制SMMU；建图时检查对象/物理页/权限/生命周期，软件IPA→HPA后合成受保护直接HPA Stage-1，其他设备继续硬件Stage-2。没有因Salus使用CXL或设备硬件扩展而否定该假设，也不要求当前Mali凭空实现CXL。

已有认证队列、GPUVM、私有快照、native fence、cookie/epoch和persistent IRQ127继续作为基础。Salus不提供多VM中断路由、通知新鲜度、ACK去重、任务失败或安全回收协议；它能提醒的是“位置缓存失效”和“对象授权撤销”是不同条件，旧通知也不能确认新代映射完成。

## 13. 独立评价及可验证后续方向

论文对动态迁移带来的重复认证工作给出具体优化，强项是身份、分区布局和带宽开销协同；边界是完整TEE管理与异常生命周期并未展开，实验为模拟且部分聚合数字不一致，公开artifact当前不可获取。

可借其思想审查项目中缓存或快照：同一对象换HPA后旧位置项是否被清除；同值句柄新代是否取得独立授权；撤销与并发提交、迟到fence/IRQ能否跨实例误关联；dirty/完成状态是否只在对应对象实例内更新。稳定逻辑ID可节省重复管理，但不能成为跨Client缓存复用或省略实际页授权的理由。这里只提出验证目标，未执行测试。

统一记录：Salus-GPU全文、书目、作者artifact入口及证据范围核验｜项目glmark前后均未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜资料获取记录保留，无GPU/VM/模拟器run-id或新增PASS｜保留artifact受阻、定量不一致及未覆盖生命周期，持续研究。
