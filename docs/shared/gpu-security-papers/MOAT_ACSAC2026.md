# MOAT：机密计算中的可信 ATS、物理地址授权与撤销协议精读

研读日期：2026-10-27。定位：直接关联 Arm CCA/RME-DA、TDX-Connect 和 SEV-TIO 的可信 I/O 论文，研究 PCIe ATS；不是 Mali GPU 的共享虚拟化实现。完整研读作者 13 页全文和 48 条参考文献，未运行模拟器、构建、攻击或硬件实验。

## 1. 书目、版本与可获得材料

完整题名：Address Translation Service for Confidential Computing，系统名 MOAT。作者：Supraja Sridhara、Paul Ferdinand Heinen、Melisande Zonta-Roudes、Anjo Vahldiek-Oberwagner、Rupin Vakharwala、Mona Vij、Shweta Shinde。前三人与 Shinde 属 ETH Zurich，另三人属 Intel，以全文首页为准。

[作者主页](https://www.shwetashinde.org/)将该文列为 ACSAC 2026，并直接链接[作者全文](https://www.shwetashinde.org/publications/moat_acsac26.pdf)和 [moat-cc](https://github.com/moat-cc)。截至研读日会议尚未来，本报告依据作者公开稿；未核实正式 DOI、出版页码或最终 proceedings 的字节一致性，不把主页标注扩大为会议已经召开。

PDF 元数据标注 IEEE PDFExpress 认证时间 2026-10-22，这说明文件生成/认证记录，不单独作为同行评审或正式出版证明。本地 build/cca-gpu-followup-20261027/moat-complete-batch28.pdf，504,087 字节，SHA256：1f6ac290f914b23c5822b0b3a0d2bd97c7b032e31017c94e14e4574e52afaf1d。

下载通过校验 HTTP Content-Range 的分段完成，13 页均有可提取正文；全文、方程、表格、机制与参考文献已顺序研读。初始网络超时形成的部分文件未用来登记精读完成。

## 2. 问题：拿到真实翻译结果，不代表永远有权使用它

ATS 允许设备从 IOMMU 获取翻译结果，缓存在设备 TLB，再使用已经翻译的物理地址直接访问主存。这有助于缓解共享 IOTLB 争用，却可能让恶意设备宣称某个任意地址“已经翻译”，绕过正常授权路径。

在机密计算中，“设备已经证明可信”也必须限定范围。攻击者可以启动自己的 CVM，再为它接入设备；这个设备可能得到攻击者 CVM 的信任，却没有因此获得访问受害者 CVM 内存的权力。身份真实性与授权归属是不同条件。

此外，曾经授权的物理页可能被撤销并分配给另一个 CVM。若旧翻译及其认证码仍有效，即使认证码确实由可信 IOMMU 生成，也会形成跨所有者访问。论文因此同时研究空间授权和时间有效性。

## 3. 威胁模型及最关键的信任限制

信任运行 CVM 的处理器、机密计算隔离与可信固件；不信任 CSP 软件、hypervisor、其他 CVM、PCIe 网络和未被目标选择信任的设备。可信 I/O 提供可信事务 T 位、不可伪造的设备身份与相应保护结构，IDE/TDISP 参与设备接入与链路保护。

目标 CVM 信任自己的全部软件，包括 OS 和驱动；还信任经自己证明接入的设备，在访问本 CVM 内存时遵守 ATS 规范。设备访问其他 CVM 内存时则按恶意行为建模。这个“域内可信、域外不可信”的设备模型，是论文减少权限检查的根本前提。

因此，论文没有证明在某个 CVM 的 OS、应用或 GPU 控制流已恶意的情况下，硬件仍实施该 CVM 内全部细粒度权限。不能把目标 CVM 内可信设备的假设套到本项目所有不可信 Client 提交的任意命令上。

可信固件必须控制会改变 CVM 物理页授权的操作，保护 IOMMU 页表/配置/密钥；T=0 事务不能借用可信结构获取 CVM 访问权。仅有带密码学标签的地址而没有这些条件，并不能形成 MOAT 的安全模型。

## 4. 论证方式：与正常翻译路径比较

论文将 IOMMU 抽象为输入虚拟地址、访问属性和翻译状态 S，输出合法性、物理地址及翻译属性。设备缓存翻译状态 ATSstate；防御 Sol 要保证直接地址访问与正常翻译所允许的访问一致。

其方程区分本 CVM 内遵规设备、跨域恶意设备和全地址空间上的防御条件。核心用途是检查优化是否仍限制设备访问当前获授权的 CVM 物理页，而不是假设所有带 ATS 标志的请求自然合法。

全文提供符号化模型和分情况安全分析，没有给出机器检查的证明、完整并发操作语义或动态页表实现的形式化验证。正文也将动态数据结构形式化验证列为独立工作。对项目引用时，应明确写出“当前状态”和撤销完成的时点，避免以“存在某个历史状态曾授权”替代运行时授权。

## 5. 既有权限表与论文的简化

Arm RME-DA 的 DPT 按物理地址关联设备及权限；Intel TDX-Connect 的 HPT 按设备维护并使用不可伪造设备 ID 索引。直接地址请求仍须通过可信物理页授权表，不意味着 ATS 能绕过全部访问控制。

论文论证在其域内设备可信模型下，host 只需确认请求落在所属 CVM 的物理页；其他 rwx、NoSnoop 等属性可由所属 CVM 信任的设备执行。因此作者提出省略表中的部分读写检查，DPT 每项最多省 1 字节，整体表占用下降 6.25%。

该优化的结论是有前提的。若需要保护一个 Client 的只读对象不被另一个 Client、设备固件或恶意 command stream 修改，就仍要在相应可信执行边界实施权限；本项目的对象归属、实际页授权和访问权限检查不应因 MOAT 的表简化而删除。

## 6. MOAT 地址认证机制

MOAT 用 HMAC-SHA256 生成 ATS Authentication Code（AAC），替换每次直接地址访问的多级权限表查询。只有正常 IOMMU 授权通过后，可信侧才对翻译结果签发 AAC；设备 TLB 存储 AAC，并在 translated access 中携带它。

认证状态包含物理页地址、翻译范围大小和 Global 位。设备身份不直接拼入认证状态，而由不可伪造设备 ID 选择的独立密钥绑定；可选地使用每设备、每 PASID 的密钥，缺省 PASID 与 Global 翻译按规定选择密钥槽。

host 在每次 translated access 上重建认证状态、选择受保护密钥并验证 AAC，还必须检查请求的完整长度落在授权区间。PCIe 禁止跨 4 KB 的规定不足以约束恶意设备，因此不能只验证起始 PA，再相信设备自行限制长度。

密钥存放于可信固件配置的受保护 IOMMU device/PASID 结构，利用已有 context cache。对 SEV-TIO，AAC 签发需位于 RMP 授权检查之后；对 RME-DA/TDX-Connect，则依赖各自受保护翻译结构。认证码只能证明经过的可信授权，不能修复签发前的错误授权。

## 7. 撤销、续发和密钥切换

若只认证地址不处理撤销，恶意设备可保存旧 AAC，在物理页转交受害者后继续访问。论文首先讨论每次撤销都换密钥的方案：能拒绝旧 AAC，却会使该密钥下全部设备 TLB 项失效。

MOAT 利用 invalidation request 与 completion 之间仍允许旧翻译的窗口，给仍合法的缓存项续发 AAC。IOMMU 同时保有 checking key 与 new key；固件在发送 invalidation 前准备新密钥，正常检查暂时仍使用旧 checking key。

设备分批发送 PA/AAC 列表申请 refresh。可信侧必须验证旧 AAC，并确认对应范围不在本次撤销集合内，才用新密钥续发。收到 invalidation completion 或等待超时后，可信侧切换 checking key，拒绝所有旧 AAC。设备不配合会损害服务，但不能让旧密码学授权无限保持有效。

论文限定固件只写 new key、IOMMU 更新 checking key，且新一轮不能在当前协议完成前覆盖新密钥槽，以避免切换竞争。该结论还依赖实现正确串行化并发撤销、范围变更和 context 访问，本轮未取得实现验证这些路径。

从本项目角度还应区分“旧授权不能再准入新请求”和“先前已被接纳的 DMA 全部排空”。换密钥解决前者；页复用仍需后者及 cache/TLB 同步。不能把 AAC 失效、completion、超时或 epoch 更新单独视为全部在途访问已停止的证明。

正文没有完整展开 refresh 期间新旧 AAC 如何共存、何时允许设备开始使用新 AAC、在途 refresh/translation response 如何归属某轮，以及 GPA→PA 失效定位与页表更新的具体次序。这些是需要代码和并发模型补证的实现问题，本轮未据此认定已存在可利用漏洞。

## 8. 故障报告与中断通信的联系

AAC 检查失败时 IOMMU 阻止访问并报告不可恢复故障，host 可选择恢复或重置设备。恶意 hypervisor 可以忽略故障影响服务，也可以伪造故障消息诱导可信 handler。

为防止后者，MOAT 将实际故障原因写入受保护内存，由可信固件核验。这里直接体现了“通知是线索，受保护记录才支撑授权副作用”：中断或 Host 转发的消息不能直接成为停止 CVM、重置设备或释放资源的证据。

这与当前 persistent IRQ127、认证完成队列及 native fence 可以组合：通知促使可信侧查看记录，实际 Client/job/epoch、原因与状态决定允许转换。MOAT 本身没有实现跨 Realm GPU completion 路由，也没有给出 GPU 中断时序泄漏或公平服务保证。

## 9. 原型、性能和准确比较边界

功能原型使用 QEMU 8.1.0、Linux 5.4.0、Xilinx SystemC 2.3.2 ATS 模型。作者报告驱动 117 LoC、QEMU 619 LoC、设备 455 LoC 修改；这些是修改量，不是整个可信基大小。QEMU 不按周期精确，作者仅以它验证功能及指令数量。

性能另用 gem5/Parade；比较对象 PT 是作者实现的、受 Arm/Intel 启发的单级 PA→device ID 表，并非实测量产 DPT/HPT 多级页表硬件。面积另用 Cadence Stratus 估计设备 PCIe endpoint，不包含 host IOMMU 硬件成本。

| 指标 | 作者结果 | 条件与边界 |
| --- | --- | --- |
| 工作负载性能 | 32 项 TLB 平均比 PT 快 12.93%，Disparity 快 40.43% | gem5/Parade 七种加速器负载；不是当前 GPU/glmark |
| TLB 扩容 | 1024 项时平均快 14.95% | 与同配置 PT 比较 |
| host page-walk 等待 | 32/1024 项时相对 PT 分别少 51.93%/58.85% | 等待时间指标，不是端到端提速 |
| refresh 对 shootdown | 200 次撤销/秒、32 项时等待少 56.45%；1024 项时少 63.34% | 1000 次/秒下相应实验最多 66.48%；不要混合不同条件 |
| 设备面积 | 128 项 TLB 增加 0.58%；32 项增加 2.08% | endpoint 综合估计；host 成本未估计 |
| 存储 | host 每 PASID 增 512 bits；设备每 TLB 项 263 bits，原型按 33 bytes | 两个密钥槽与 AAC 状态；不代表无存储成本 |
| 功能兼容 | 2/4/8/16 加速器运行正确；单加速器平均多 3805 指令、约 0.2% | 作者测试结果，不是恶意并发协议的完整验证 |

论文按 PCIe 带宽及认证延迟估算，1 ms 撤销窗口可 refresh 约 48,000 项。这是给定参数的计算，不是所有设备/负载的实测上界，也不代表请求源可以无限不响应。

DPT 的 1 TB/4 KB 配置约需 4 GB，MOAT 在每设备 1K PASID 下需 64 KB，作者据此比较可容纳设备数量。这是特定结构/配置的占用比较，不能当作当前 Mali 或其他架构必然耗费同样内存。

## 10. 公开代码及本轮证据限制

全文和作者主页均宣称开源于 moat-cc。本轮实际访问其公开 org repos 与 user repos API，均返回空数组，尚未取得可以固定 commit 的匹配实现。只能说本轮未发现可访问源码，不能写成代码永远不存在或全文开源声明为虚假。

因此没有核验 HMAC 输入序列化、恒定时间比较、长度溢出、key/context cache 同步、故障记录原子性、设备重绑与密钥擦除、refresh/new-key 使用时序或撤销并发。上游 Xilinx/QEMU 的存在也不能代替 MOAT 修改代码审计。

13 页全文、HTTP 分段 provenance、PDF 哈希与每页正文长度、作者主页和公开代码查询结果保存在 build/cca-gpu-followup-20261027/ 的 moat/shinde 对应文件中。没有执行论文实现、Cadence、gem5、QEMU 或 GPU 测试。

## 11. 与 PORTAL、CAGE、ACAI、CryptoMMU 的关系

论文直接引用 ACAI、CAGE、PORTAL 和 StrongBox，认为这些可信设备接入工作仍需遵守 IOMMU 路径，而 MOAT 为可信 I/O 下启用 ATS 补充授权检查。它还比较 Border Control 与 CryptoMMU，强调机密计算中互不信任 CVM 及设备作用域带来的额外分析要求。

对本项目不必实现 PCIe ATS、AAC 或新的密码学数据面。更直接的借鉴是分析方法：把“正常可信翻译/授权”当作参照，论证软件 IPA→HPA 后的直接-HPA Stage-1 在生命周期内保持相应约束。

需要注意差别：MOAT 在每次 translated transaction 上验证 AAC；本项目是在映射建立时完成授权，随后由保护的 Stage-1 持续限制访问。因此还必须证明根配置、页表、设备 context、实际页归属和撤销顺序在映射存活期间受控，不能仅凭“建图时正确”推出所有未来访问都正确。

## 12. 对当前项目的具体建议

第一，为现有合成 Stage-1 写出可检查的不变量：每个可访问 HPA 范围都对应当前 RMM 认证 Client 的合法对象、实际页授权、权限和映射代次；映射存活期间权限收缩、页转交、reset 和 Client 重启必须使旧授权失效。GPUVA/IPA 数值相同不代表授权关系相同。

第二，沿已有 GPUVM、cookie/epoch、私有快照和 native fence 检查授权状态的组合，特别是完成、取消、unmap、reset 与重绑交错。epoch 用于识别旧状态，实际页表/cache/在途访问的撤销仍需执行，不增加一套与现有机制重复的 token。

第三，物理设备 ID 不能独立代表共享 GPU 中的 Client。MOAT 的每设备/每 PASID 隔离只有在相应身份不可伪造并与授权作用域一致时才有效；本项目继续以 RMM 认证的原始 Client 与可信 GPUVM/队列归属约束实际访问。

第四，检查 fault-to-action 路径：来自 Host 的 IRQ、错误码或 timeout 只能触发核验，不能独立授权设备 reset、跨 Client 取消或释放页。可信侧要依据实际受保护设备/队列记录，确定事件关联的 Client、job、epoch 和允许副作用。

第五，把优化的安全论证写成当前授权参照下的精化关系，同时允许优化路径保守拒绝。对合法请求被拒绝的情况另研究兼容性和可用性；安全性无需为了形式上的双向等价而允许越权请求。本建议是项目分析方法，不是论文已完成的项目证明。

统一记录：可信 ATS 论文 13 页全文及公开材料研读｜项目 glmark 前后均未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜无硬件 run-id/新增 PASS｜保留为直接 CCA/可信 I/O 后续文献；作者稿版本、设备信任前提与源码缺口明确记录。
