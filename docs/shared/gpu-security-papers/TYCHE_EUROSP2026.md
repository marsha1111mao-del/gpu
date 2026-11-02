# Tyche：可组合隔离、可信中断策略与 GPU 资源撤销的设计启示

## 1. 论文身份、版本和阅读范围

《Tyche: Composable Isolation as a Foundation to Manage Trust in the Cloud》，Adrien Ghosn、Charly Castes、Neelu S. Kalani、Yuchen Qian、Marios Kogias、Edouard Bugnion。正式出版元数据独立核对为EuroS&P2026，772–788页，DOI [10.1109/EuroSP68448.2026.00055](https://doi.org/10.1109/EuroSP68448.2026.00055)。本轮精读[arXiv2507.12364v2](https://arxiv.org/abs/2507.12364v2)，2026-05-21，17页，PDF SHA-256为`f0b2eecead064d26e2674d40d3822bacbfddee1e4ad498a017e278db9d3ab757`；正式出版方PDF请求418，未作两版本逐字比对，不把arXiv文件冒充出版方下载件。

完整阅读§1–9和110条参考文献，无附录或独立算法；12图4表，12页视觉核对覆盖全部图表和实现/评估页。取得完整HTML和48成员TeX源包，定向复核当前paper.tex引入的设计、威胁模型、实现、评估与case study，不把未引入的历史段落当作现行机制。

论文明确链接[公开仓库](https://github.com/epfl-dcsl/tyche-devel)，固定`562424d56799479c0dba7cb5af8c4b8ab7d62d6e`，提交日期2025-09-19，早于本次v2；完整递归树1283项、3个gitlink固定记录，29个选取blob通过长度/Git SHA-1/SHA-256校验。README、权限/序列化/签名小文件及选定测试入口完整读，较大engine/backend/region/segment/设备路径定向静态阅读；未完整审计TPM启动链、所有架构或SDK，也未构建/运行作者代码。当前公开提交不能自动等同2026论文实验快照。

## 2. 对本项目的定位：统一授权语义的支撑论文

Tyche不是Arm CCA实现，也不是GPU TEE/直通论文。其完整后端基于x86 VT-x/EPT/IOMMU，另有RISC-V M-mode/PMP原型；Arm与GPU安全直通均在讨论/未来工作中。LLM案例明确为CPU推理，不将摘要“约2%”写成GPU性能。

它与PORTAL/ACAI/CAGE的联系是：由单一可信管理层把内存、设备、核心、控制转移及证明放在一致的授权模型下，避免“资源管理者自然可访问数据”的隐含信任。当前项目继续接受RMM认证原始Client、可信ProxyRealm统一SMMU、实际HPA授权与软件翻译合成GPU Stage-1、其他设备授权Stage-2、页表/根/MMIO与可信固件受保护等假设。测试硬件仅用于机制验证，不以平台缺少某项能力否定研究设计。

## 3. 研究问题：机密性与封装需要同时成立

互不信任组件既要保护自己的秘密，也要处理他人的数据。CPU enclave保护模型权重，却未必阻止恶意模型runtime向第三方泄漏prompt；sandbox约束外发，却不一定保护内部模型免受sandbox管理者读取。现有嵌套VM、SGX、VMPL、TDX partition和用户沙箱组合常重复执行层、争用权限层并使证明链复杂。

Tyche提出Security Domain（SD）作为统一执行域，可信monitor管理访问和边界，非可信SD决定资源分配、调度及业务策略。逻辑上的递归父子域由同一层执行，不要求每嵌套一层再增加一次硬件嵌套虚拟化。所谓管理/访问解耦，并不表示管理者失去撤销或拒绝调度的能力。

## 4. 威胁模型与不能推出的保证

硬件、物理设备、访问控制机制和monitor可信；CSP及租户可在其SD内运行任意代码，攻击API、设备配置、特权指令及中断，试图越权读取、破坏元数据、窃取证明私钥或阻止撤销。物理读DRAM/PCI总线排除；共享微架构侧信道未被整体解决，只有切换flush及可组合核分区/着色等缓解方向。

静态monitor内存耗尽可以阻止新域创建，作者主张现有域的隔离、切换、证明和撤销仍可继续。该主张需要容量与失败路径证据，不能由“Rust无unsafe核心”直接推出。CSP仍可关机或停止服务，平台并不保证业务可用性；权限隔离也不证明LLM或GPU计算结果正确。

## 5. 两棵派生树：资源权限与管理关系

Memory CDT记录实际物理区间、R/W/X、exclusive/aliased及子区间；SD CDT记录父子管理、核心许可、中断路由和域间依赖。新能力从既有能力派生，权限不扩大，撤销可以沿子树级联。API包括CREATE、SET/GET、SEND、SEAL、ATTEST、ENUMERATE、SWITCH、ALIAS、CARVE、REVOKE、GETCHAN。

能力是monitor维护的不可伪造对象，调用者仅传自己的局部索引，不是把任意Client自填ID当作权限。项目可借鉴“从已有授权派生、只缩小范围、统一失效”的规则，无需为此另造一套通用微内核或复制现有BO/GPUVM/队列体系。

## 6. alias、carve、send 与实际页归属

alias允许父域继续访问同一物理子区间；carve从父域拿走该区间。只有从exclusive区间连续carve才能获得exclusive子区间，从已有共享区carve不能消除其他别名。send转移某个能力的所有权，别名能力的存在仍决定实际页是否独占。

这与ACAI的映射归属一致性及PhantomMap的实际页视角一致：私有对象标签或独立页表根不是物理页独占证明。项目必须把同HPA的CPU/GPU/其他设备别名、权限、generation与残余访问全部计入；授权集合应以实际页及实例为准，不能只检查IPA或句柄范围。

## 7. hash、clean、vital、META 的价值与边界

hash在授权转移时记录exclusive内容初值；clean要求撤销时清零；vital要求资源撤销时一并撤销依赖它的域。属性绑定所有权，不等同所有CDT边永久继承。META用于由父域提供monitor元数据页，必须exclusive、vital且撤销时清理，父子都不能直接访问，但仍纳入证明。

hash证明初始内容绑定，不是持续内容完整性或计算验证。clean只能在所有旧访问已失效后执行并保证新所有者不能提前观察；vital是依赖关系终止，不等于强制结束设备DMA。项目可把不可拆分的plan、原生对象、映射和任务引用表达为依赖关系，但仍需原生fence与设备静默证据。

## 8. seal：固定边界而非冻结业务

子域创建后未sealed不可执行，父域配置初始寄存器、核心、中断和monitor调用策略，再seal。论文描述seal后固定初始化和策略，同时允许中断处理期间按显式寄存器权限访问子域状态；应以具体bitmap和后端检查解释，不能笼统说所有寄存器永远不可写。

封装子域还需禁止其seal后接收/发送新能力，并将其内存约束为父域exclusive资源的子集。否则“当前没有外部通道”的证明可能被之后新增通道绕过。项目不必冻结所有BO动态分配，可以固定授权规则并让每次映射/提交/撤销受检；改变证明相关拓扑、设备租约或策略时推进epoch并重新认证。

## 9. 中断策略：Deliver、Report、Not report

每vector配置三态及父域可访问的寄存器集合。Deliver由当前域处理；否则monitor沿SD祖先查找首个Deliver handler并转移控制。该handler看到的是从其直接子域返回的事件，而非自动获得更深层子域的全部寄存器。恢复时沿树下降，Report域接收报告并决定是否恢复自己的子域，Not report域被跳过。

论文vector0例子：SD2除零→跳过Report的SD1，交给Deliver的SD0；SD0仅按SD1策略接触状态，恢复到SD1时再向SD1报告其子域SD2异常。SD1读取/修改SD2哪些寄存器仍受SD2策略限制。调度和状态可见性成为可证明接口，这是比“把IRQ转发给正确VM”更完整的研究视角。

但Not report不表示外部观察者无法看到异常发生次数/时间；异常vector也可能成为恶意子域主动编码的通道。side channel排除项仍有效。真实物理IRQ来源、软件注入权限、路由正确性和任务完成语义必须分开，不能因该三态策略而声称抗所有中断伪造/时序泄漏。

## 10. channel：共享不附带管理权

SD管理能力在论文设计中不可转移，以保留父域调度/撤销责任；GETCHAN生成可转移的弱引用，使非父子域可以互相证明、交换内存/其他channel，却不能配置、调度或撤销对方。设备被抽象为SD，配置空间/MMIO和DMA访问由能力表达，SD0最初拥有设备channel，随后可授权给其他域。

这适合项目区分“Client可提交指定工作”与“Client可管理Proxy/SMMU/设备reset”。共享服务发现不应隐含管理权限；向Proxy传递BO访问权也不应传递对其他Client对象或整台GPU的控制权。设备SD只是统一抽象，完整设备固件、命令验证与设备内部状态还需独立保护。

## 11. 跨核更新与撤销：线性化关系

论文engine按受影响SD/区间序列化操作，将更新放入各核队列，IPI抢占相关核心，用两阶段barrier确保所有受影响核停止后更新全局授权和硬件映射，再做本地失效并恢复。资源接收者不能在旧所有者仍可访问时提前运行，这比只更新软件归属表更关键。

移植到GPU时，CPU抢占/barrier不自动停止GPU、设备TLB、排队命令或固件MCU。必须增加设备对应的停止新提交、任务终态/静默、SMMU失效完成及对象引用排空。不能把CPU的跨核原子更新过程直接写成GPU页回收证明，也不能用超时返回代替设备静默。

## 12. 证明：身份、初值与共享边界

设计将TPM quote、monitor/boot-info/public key度量与monitor签名的SD报告结合。报告包含初始寄存器、核心/monitor/interrupt策略、能力及直接子项，远程证明绑定验证方public key、nonce和域生成的public key；报告以请求者局部重新编号降低全局拓扑泄露。

证明不是遍历一切后代，也不是直接证明业务输出正确。设计通过权限单调和固定接口使历史报告仍有可推理的语义，但接收者必须检查可接收新能力、撤销、重启和实例身份等条件。项目建议把Client/Proxy实例、设备租约/reset epoch、固件与映射策略摘要、允许发布端和fresh nonce一起绑定，而非只验某个镜像RIM。

## 13. 固定公开代码核对：实现版本不能混同论文

Cargo路径确认monitor使用所读capability-engine、attestation和x86 vtd。当前公开engine以固定数组和全局状态实现较早版本，权限文件主要为allowed-trap bitmap与寄存器组bitmap；已读路由采用can_handle查祖先/创建resume能力并由backend重注入。没有在这些路径中取得论文完整三态Report传播与多组件证明的同等实现证据，不据历史design文档“只支持前32异常”否定当前已有external interrupt路径。

当前代码允许send处理Management能力并留有避免cycle TODO，与v2“SD能力不能转移”不同；send先移除原能力，代码自行注明后续失败时需要调整顺序。已读segment撤销中的VITAL副作用被注释禁用。它们应记录为固定旧公开提交与v2规范的差距，不能宣称这是作者2026正式实验版本的已证漏洞。

## 14. 固定公开代码核对：设备与安全回收

`update_domain_iopt`重建映射时明确留有“invalidate context/PASID cache and flush IOTLB”TODO；对含READ的有效区间统一设置READ/WRITE/EXECUTE，而不是在所读函数逐位保留授权R/W。`setup_iommu_context`为所有256 root项复用同一context页，256 context项指向同一I/O页表，所读helper不按独立设备ID划分域。

这可以是早期单设备/共享域原型，但不足以支撑多设备、只读授权与完整设备生命周期安全。未核验全部启动配置、其他调用者或真实设备行为，不声称已执行跨设备DMA或越权写攻击。项目应保留实际HPA/权限检查和设备归属，不能把capability API作为省略SMMU上下文隔离/失效的理由。

跨核域撤销的公开路径确实先通知/停止相关核再回收能力，不能只看底层“域仍运行返回错误”便宣称完全不能撤销运行域。Cleanup路径直接对区间fill(0)，旁有“当前未校验区间是否真实RAM，root含设备”的警告；清零准入需要区分普通RAM/设备MMIO。update缓冲有容量错误，backend部分push使用unwrap，边界资源不足与撤销始终成功还需容量预算/调用图证明。本轮没有构造panic、竞态或安全利用。

## 15. 固定公开代码核对：证明与测试的实际范围

公开`attestation_domain.rs`包含仅HASH区域内容度量及旧报告helper，签名输入为域hash与usize nonce；所读完整capability serializer另输出全局regions/domains，未包含v2所述全部interrupt/core策略，也不是同一份已核实签名报告。旧helper在所读monitor调用表中没有完整对接，不能把这些文件并置就声称已证明完整远程证明流程可用。

旧签名helper从Seed::default派生密钥。进一步核对Cargo确实依赖仓库内fork，fork的default虽然注释称随机，实际填入0至31的固定seed；这是演示/旧实现不能作为生产信任根的静态证据。由于未确认该helper当前完整远程调用链，不能扩展成“作者正式部署的TPM私钥可被攻破”，也没有执行密钥生成或签名伪造。

interrupt-routing示例设置bitmap、执行软件int并检查共享marker777；multicore-revoke示例在另一核运行域、等待共享标记、触发raw revoke再join。它们证明仓库存在相应验证意图，不等于测试已执行通过，更未覆盖恶意多Client、通知丢失、迟到事件、重置和GPU静默。本轮完整读两个Host测试入口，trusted中断代码定向读，不称全部测试/SDK审计。

## 16. 实验数据：不能把 CPU 推理推广成 GPU 性能

作者x86平台为i7-10700、SGXv1/94MB EPC、Linux6.2；正文称16-core，但应区分论文测试的16个执行线程与该CPU的物理核心/SMT概念，本文不将其当作16个独立物理隔离核的证据。RISC-V为VisionFive2/JH7110、每hart8PMP、Linux5.15。VM/CVM为4GiB/8执行核、VIRTIO，CVM加SWIOTLB；作者取10次中最好9次平均，需披露该裁剪口径，不视为全部重复均值或长尾稳定性。

| 项目 | 作者结果/独立算术 | 边界 |
| --- | --- | --- |
| x86切换 | 1.171±0.002μs，entry+exit0.493μs | 1000操作平均；entry部分约42.10% |
| RISC-V切换 | 3.897±0.007μs，entry+exit0.246μs | 总切换约x86的3.33倍，不能只按特权切换快慢推测总成本 |
| CPU | SD1对native VM约+1%，对native约+4%时间/开销描述 | 不代表所有应用、所有I/O或GPU路径 |
| 多VM | CPU约2%、内存<1%对native VM开销 | 作者CPU/sysbench配置；非恶意共享攻击压力 |
| Redis p50 | native0.86ms→VM1.77ms | +105.81%，需区分VM/driver通路与Tyche独立增量 |
| Redis pipeline30 | 4.16M→3.54M req/s | 吞吐低14.90%；增加pipeline掩盖延迟不消除单请求成本 |
| CPU LLaMa | SD2约2%开销，对SGX约10倍速度 | 小型Llama3.2-1B量化模型、四线程、1000tokens；94MB EPC对照受限 |
| capability内存 | 平均每SD两4KiB页 | 512SD换算4MiB，仅元数据线性外推，非512SD实际压力/全系统占用 |

KVM修改400/14.6k行约2.74%，Gramine300/14.9k约2.01%；这是适配改动比例，不是可信代码减少比例。核心engine约4k、后端约6k Rust、二进制约230KB，也不包含全部启动、硬件固件与密码依赖。论文称engine无unsafe并fuzz，不是形式化验证、整个monitor无unsafe或不存在逻辑错误。

## 17. 评估与论证中需保留的限制

网络正文称pipeline1 GETs，表4同时列10%write/90%read，应保留配置表述差异，不在没有精确脚本/原始数据时替作者统一。图11是多种runtime和driver的组合对照，QEMU/VHOST可改善共同路径，不能把所有差距归因Tyche或把改driver结果称为安全机制本身提速。

SGXv1 EPC94MB与模型/runtime约4GiB不匹配，作者也承认更大EPC的SGX版本可能更好；10倍优势不是同等威胁模型/内存能力下所有GPU TEE的结论。私有共享免去1KB20μs、1MB2ms、100MB0.24s的加密bounce开销，只是所选CPU crypto路径，不表示零通信成本或恶意对端无需消息校验。

encapsulation限制路径，不能自动阻止恶意模型通过合法输出泄漏权重给获准接收者；prompt到达恶意runtime后，时序、响应内容和后续授权请求仍需威胁模型和去分类规则。共享Proxy可访问A/B时，拓扑能力不替代Proxy内部按Client鉴权和分区。这些是迁移到项目的推理边界，不是本轮已复现论文失效。

## 18. 项目建议：可证明的资源与事件策略

复用既有BO/GPUVM、RMM认证队列、private plan/snapshot、native fence、cookie/epoch与IRQ127，在可信记录中明确所有者、实际HPA集合、CPU/GPU/其他设备权限、允许提交/完成/发布端、派生关系及实例epoch。检查派生只缩权；跨Client共享须显式授权，不能由某个可转发句柄隐式扩大权限。

中断部分借鉴三态思想，分别列出设备物理IRQ由谁接收、哪些事件通知Client、Host/父域可见哪些寄存器与错误字段、谁可注入何类提示。IRQ127仅提示重查可信队列；任务终态仍由匹配native fence/cookie/epoch确认，重复/迟到事件幂等且不跨实例，ACK/ARM与并发新事件需重查。路由可证明不等于中断存在性/时序不可见。

证明可绑定这些策略的摘要和版本，但不要求每个动态BO都重新完整证明；应明确哪些变化是既有规则允许的执行，哪些改变了被证明边界。任何可接收新能力、管理权限转移、设备reset或固件变化，都应进入策略/实例生命周期，不让旧报告永久授权新状态。

## 19. 项目建议：撤销是完整协议

建议按既有实现组织可检查顺序：拒绝新提交/授权，推进撤销或设备epoch，收敛在途任务与DMA，撤销实际映射并等待失效完成，排空CPU/GPU及队列/计划引用，清理残余状态，最后清零并授权新所有者。CPU核停止、页表项删除、通知ACK、任务取消和设备静默分别保留证据。

负例优先覆盖：只读能力被转成可写DMA、同HPA经别名重获权限、撤销与映射/提交并发、在途GPU任务后旧TLB、设备reset后旧cookie、空闲域能力耗尽、策略seal后补发通道、父域读取未授权寄存器、设备身份上下文混用、清零错误覆盖MMIO、容量失败后部分授权。以上为建议验证计划，本轮未执行，不沿用历史PASS保证新设计。

## 20. 证据与统一记录

证据位于`build/cca-gpu-followup-20261027/`：17页`tyche99.txt`、HTML/48项源包清单、12页render、Crossref搜索及精确元数据/正式PDF418、固定commit/1283树/29blob清单、独立算术、Notion全文回读及父页原文/子页保护审计。限定静态阅读没有执行作者libFuzzer、SDK测试、TPM、模型或设备攻击。

统一记录：全文/110引用/12图4表/12页视觉/源包定向阅读/固定源码选读/算术/Notion回读｜glmark未测→未测｜绝对/百分比分差不适用｜未改运行代码，无新增性能测量｜无构建/硬件/训练/作者程序/攻击run-id｜保留研究；正式元数据核实，全文版本比对与完整设备/证明实现仍待验证。论文机制、旧公开代码观察、条件推理和项目建议分别陈述。
