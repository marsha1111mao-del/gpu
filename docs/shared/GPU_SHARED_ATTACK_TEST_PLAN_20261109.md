# GPU 安全共享：扩展攻击测试计划与 CVE 对照

Notion：[GPU 安全共享｜威胁模型、安全设计与攻击验证（含 CVE）](https://app.notion.com/p/413659a3b8cc8135b0dddc71449cb2fa)，第 4 节及其 92 项 CSV 附件。

日期：2026-11-09，2026-11-10 更新执行状态。清单从 40 类负例和 6 类正常对照扩展为 **80 类攻击或故障场景和 12 类正常对照，共 92 项**。初稿全部为 NOT_RUN。历史离线运行 `security-phase1-phase2-fixes-r57-20261110 --verify-runtime` 退出 0，42/42 检查通过，矩阵 88 项为 `EVIDENCE_PASS_SCOPED`，4 项物理证据为 `NOT_VERIFIED`。结果范围为控制机模型与控制流。[发布版本的安全证据](../design/03-security.md)

## 1. 测试目标与当前版本

保护一个诚实 Client A；攻击者可以完全控制 Host、Proxy 及其他 Client 并串通。A 的 Guest 内核和本地结果交付路径可信；RMM、Monitor/Root 服务、可信设备后端、批准 FW 与硬件隔离属于安全前提。复杂驱动被攻陷后仍不能跨越内存、授权、真实控制、完成和撤权边界，是核心检验目标。

**TCB 被假设正确不意味着其接口免于攻击测试。** 恶意输入触发 RMM、可信后端或 FW 漏洞会破坏前提，因此边界检查、解析器、并发与错误清理必须测试；这里只不承诺在 TCB 已被任意改写后继续安全。

冻结运行基线与当前边界以 [CURRENT_BASELINE.md](CURRENT_BASELINE.md) 为准：本地 ABI6 设计清理包保留单 Client 完整 720p 1095 参考；2026-11-10 安全修复只完成控制机离线验证，尚未构建/部署为新的 RMM 固件。执行时必须分别记录源码及 Client/Proxy/RMM/固件哈希，不沿用原基线 PASS，也不把 ABI6 1095 继承为新安全修改的性能结果。

**先区分三类结论。**

| 类别 | 例子 | 可下的结论 |
| --- | --- | --- |
| 当前机制的实际代码检查 | 私有 BO 登记、RMM 页表、有限委托、FINISH、BO_IDLE | 能指出防线与待测入口；不能因此给攻击用例 PASS |
| 待实现的协议扩展 | Monitor 物理 IRQ 记录、可信清除与日志消费 | 可先做状态机/故障注入模型；不能称现有 IRQ 路径已经安全实现 |
| 平台前提验证 | Host 物理 MMIO、其他设备 DMA、恶意命令权限、设备残留 | 必须有具备相应隔离能力的设备；RK3588/OpenCCA 功能原型不替代真实 CCA 证明 |

## 2. 如何把四类防御变成可验证的要求

| 防御 | 必须保持的不变量 | 不够充分的验收 |
| --- | --- | --- |
| 私有内存与 GPU 地址空间 | 实际 CPU/DMA/GPU 访问不超授权；旧访问尚可能发生时 backing 不交给新 owner | 只看 mmap 报错、PTE 值或应用未崩溃 |
| 对象关系与任务授权 | 每次真实发布都对应合法身份、关系、映射/绑定代次和未消耗授权 | 只检查 handle 存在或 Proxy 返回成功 |
| MMIO/FW/控制内存 | 所有等效控制路径被约束，设备只消费可信提交的控制状态 | 只检查文件哈希，却不检查运行镜像及写入来源 |
| 任务完成与交付 | 对应执行实例全部必要工作完成，无相关错误且结果可见，才 signal 成功 | 只收到 IRQ、consumer 追上 producer 或一个完成字变化 |

生命周期、共享 RPC 和恢复是四类防御共同依赖的部分，所以矩阵独立列组，避免漏测。残留内容直接泄露不同于时序侧信道；若能从 GPU 本地存储读出上一 Client 的数据，不能简单归入“不考虑侧信道”。服务饥饿/时限与数据隔离分别报告。

## 3. 完整清单的组织

| 类别 | ID | 数量 | 主要覆盖 |
| --- | --- | --- | --- |
| 私有内存与地址空间 | M01–M12 | 12 | owner、范围、别名、权限、PTE/root、特权绕过、旧 TLB、分裂映射、RTT 并发、缓存失效、残留 |
| 对象与授权 | A01–A12 | 12 | 身份、关系、描述替换、代次、重复执行、依赖、TOCTOU、输出、slots、优先级、跨 REC、重建 |
| 硬件/FW/控制内存 | H01–H14 | 14 | MMIO、Host 绕过、固件替换、控制区、假完成、旧接口、DMA、接管、解析、上传、映射属性、调试、reset |
| 中断与完成语义 | C01–C16 | 16 | 假通知、OOM、错任务、旧 IRQ、乱序、错误语义、旧 ACK、丢故障、日志溢出、可见性、缓存行、fence |
| 撤权与资源压力 | R01–R12 | 12 | 提前释放、终态与撤权、阶段失败、退出、并发、耗尽、缓存、VA 树、worker、GEM、flush、分配回滚 |
| 共享 RPC | T01–T10 | 10 | 包边界、ABI、响应绑定、迟到响应、队列索引、同步丢失、假状态、快照、背压、返回泄露 |
| 串通与组合攻击 | X01–X04 | 4 | 错绑完成、发布丢回复后复用、完全失陷 Proxy、压力驱动不安全清理 |
| 正常对照 | P01–P12 | 12 | 合法同地址、事件合并/轮询、OOM、复用、并发、缓存、部分解绑、上界、恢复与幂等 |

完整 92 行位于 [CSV 测试矩阵](GPU_SHARED_SECURITY_TEST_MATRIX_20261109.csv)，包含攻击者、注入入口、预期行为、关键观测、CVE、优先级、前提和结果字段。原 M01–M08/A01–A08/H01–H08/C01–C10/R01–R06/P01–P06 的细节保留在 [主分析文档](GPU_SHARED_THREAT_MODEL_SECURITY_DESIGN_ANALYSIS_20261109.md)。下面集中列本轮新增项。

L1：有限模型/接口边界；L2：实际被测代码＋可控后端/故障注入，不自动覆盖真实 Linux 并发和硬件语义；L3：目标平台实测。P0 表示隔离、内存安全、授权或终态关键项，不要求一次全部完成；P1 表示随后覆盖的策略、信息与压力项。混合用例执行时需拆成具体变体，不能用一个 PASS 代表所有主体/层次。

**新增：地址空间**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| M09 | 部分 MAP/UNMAP 跨多个 backing 段、页表边界；从映射中间挖洞并让第二个分裂节点分配失败 | 只改变目标范围；左右保留段和 offset 正确；失败按声明的事务原子性回退或报告已提交前缀 | L1/L2/L3 |
| M10 | 提交 IPA 上限、空洞、不同 RTT 层级描述符，穿插 RMI 页面移除或属性变化 | 根据有效 RTT 和页面状态解析；地址截断不得命中另一页；固定页面的变更必须协调或拒绝 | L1/L2/L3 |
| M11 | 让映射检查缓存命中后改变权限、别名、绑定或 reset，再重放旧版本 | 改变安全条件必须使缓存结论失效；缓存淘汰只损失性能，不能扩大权限 | L1/L2 |
| M12 | A 在 GPU 本地/共享 scratch 或寄存器中留下随机标记，切给 B 后尝试读出残留 | 若设备暴露跨租户残留则隔离声明失败；需硬件保证、可信清理或限制共享，不能用 BO 页表正确掩盖 | L3 |

**新增：授权**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| A09 | FW 实际提供 s 个 stream，提交 0、s、s+1、MAX、MAX+1 个队列并伪造能力响应 | 同时检查实际初始化数量与协议上限；不存在未初始化接口访问；合法 s 不误拒 | L1/L2/L3 |
| A10 | 越权请求高优先级、独占资源或超大配额，Proxy 将低优先级任务改为高优先级 | 只接受策略允许的配置；拒绝不能变相扩大执行权限；公平性单独测量，不承诺恶意 Host 下进展 | L1/L2/L3 |
| A11 | 同一 Client 的两个 REC/CPU 并发使用同一 token，分别请求发布、取消或退休 | 互斥或原子状态迁移只允许一个合法结果；身份相同不代表可以重复消耗授权 | L1/L2 |
| A12 | Proxy 重连、Realm 重建或受支持的恢复后，重放旧会话 handle/token/授权快照 | 新身份不继承旧授权；未支持的恢复必须拒绝；若可信状态也可回滚须另建外部新鲜性机制 | L1/L2/L3 |

**新增：硬件与固件**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| H09 | FW 节区 data_size 大于 VA 大小、零大小、重叠、截断及元数据加法回绕 | 生产入口先认证受保护镜像，非法镜像不得到达设备；解析器独立测试也要有界拒绝 | L1/L2 |
| H10 | FW 接口的 group/stream stride 溢出、接口跨末尾、输入输出区域别名或共享节过短 | 按真实 FW 结构尺寸及宽整数验证范围，拒绝重叠/越界，不按 Host wrapper 大小判断 | L1/L2 |
| H11 | 分片上传乱序/重复/留洞，seal 后覆盖或切换 service，再请求重新安装 | 按上传协议拒绝不合法序列；批准字节与运行镜像一致；认证状态不跨不合法会话复用 | L1/L2 |
| H12 | 将只读 MMIO 或控制页经 mprotect、MAP_PRIVATE/COW、fork 和属性别名改为可写 | 软件映射标志与平台权限都不放宽；改变 VMA 不能取得敏感寄存器或控制页写权 | L2/L3 |
| H13 | 通过性能计数器、debugfs、trace、崩溃转储、FW 调试或读回接口获取其他 Client 信息 | 仅披露接口允许的元数据；调试 DMA 和可读地址受隔离；内容泄露与允许的时序信息分开报告 | L2/L3 |
| H14 | 任务运行时从不同控制入口执行 reset、掉电、时钟切换或 SMMU 重配置 | 失去控制连续性时不得交付未经证实的成功；旧授权失效且 backing 保留到可信撤权 | L2/L3 |

**新增：完成语义**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| C11 | 伪造或重复 tiler OOM，换 heap/pool 地址，提交过大扩展，恢复后重放旧请求 | 只服务当前受保护上下文的新请求，扩展只用该 Client 合法页；错误指针不解引用；服务成功不是 JOB 成功 | L1/L2/L3 |
| C12 | consumer 已追上 producer，但 scoreboard、blocked 状态或另一成员仍未结束 | 消耗命令与执行完成分开；必要成员全部达到完成条件前保持 PENDING | L1/L2/L3 |
| C13 | 让 CPU 输入和 GPU 输出共享缓存行，交错 clean/invalidate 与 GPU 写入 | 协议分离写者及缓存行，维护操作不覆盖新输出；混合快照不能用于成功判定 | L1/L2/L3 |
| C14 | 同一 IRQ 内完成与 fault 同时出现，或在状态读取和 W1C 清除之间到达新 fault | 按设备协议保留相关故障，再清除/应答；不得抹去新事件，不能依赖固定 IRQ 优先顺序 | L1/L2/L3 |
| C15 | 伪造 IRQ 日志条目、tail/head，重复消费，环绕覆盖或中断迁移到未记录 CPU | 日志与索引在可信内存，消费有界且归属一致；不可恢复的安全历史缺口阻止成功 | L1/L2/L3 |
| C16 | 错误/取消 fence 被 Proxy 包装成成功，混用 timeline point/eventfd，重复交付旧结果 | Client 仅依据相应 RMM 终态设置本地 fence；保留错误码并绑定正确 point；重复提示幂等 | L1/L2/L3 |

**新增：撤权与回收**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| R07 | BO 被判 idle 后，在放入缓存或重新取出前产生映射/任务引用；跨文件/上下文复用缓存项 | idle 检查及缓存归属契约防止活动页复用；取出时重新满足使用条件；不带入旧授权 | L1/L2/L3 |
| R08 | UNMAP 返回失败，随后销毁相邻 GPUVA 节点或再次清理同一对象 | 元数据无悬挂节点/双重释放；仍可能被 GPU 访问的 backing 继续固定；元数据修复不能替代撤权 | L1/L2/L3 |
| R09 | IRQ 已排队的 FW worker、timer 或 fence callback 与 unplug/Realm 退出并发 | 停止新入队并排空已有回调后才释放其内存；对设备在途访问另行撤权 | L1/L2/L3 |
| R10 | drm_gem_handle_create 失败、发布 handle 后立即 close，debug/诊断路径继续使用已 put 对象 | 发布前完成所需初始化，所有观察者有合法引用；失败清理只发生一次 | L1/L2 |
| R11 | GPU flush 持续超时、控制 ACK 丢失，诱导反复重试并将 reset 完成视为原任务完成 | 有界重试/隔离；恢复重置未决控制状态，旧任务不假成功、不盲重发；停止未证实不释放 | L1/L2/L3 |
| R12 | 在第 n 个页/SG/控制 backing 分配失败；错误清理后再次重试同一操作 | get/put 与页登记逐项守恒；没有半授权、重复释放或丢失的保留资源 | L1/L2 |

**新增：共享 RPC**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| T01 | 构造短包、超长包、溢出的 count/stride、未对齐 payload 或跨 RPC 队列边界 | 在边界内复制和解析；未知组合拒绝，无可信内存越界和半状态提交 | L1/L2 |
| T02 | 混用旧 ABI、未知 opcode、保留标志、错误响应类型、32/64 位长度和值域 | 按协商后的当前 ABI 接纳，拒绝含糊解释；退休编号不变成新的授权路径 | L1/L2 |
| T03 | 将 A 的 response 与 B 的 request ID 组合，跨 session 复用相同序号 | 匹配端点/会话/请求类型与本地对象；不能只凭 sequence 完成另一个调用 | L1/L2 |
| T04 | 超时后迟到的回复命中新建请求，或 sequence 环绕复用 | 旧响应不完成新请求；使用会话代次/未决记录及明确回绕策略 | L1/L2 |
| T05 | 伪造共享队列 head/tail、回退索引、发布一半消息，制造满队列覆盖 | 按传输协议检查范围及发布顺序；共享状态损坏只导致拒绝/服务失败，不变成安全授权 | L1/L2 |
| T06 | 在 RMM 已提交 VM_BIND 后丢弃 VM_SYNC 响应，随后 Proxy 声称未映射或同步到旧版本 | 以 RMM 映射版本为准；有限重试/重建功能元数据，不反向覆盖真实权限 | L1/L2 |
| T07 | 伪造 STARTED、PENDING、错误恢复游标或页数，引导 Client 跳过 READY/FINISH | 功能响应不生成成功；只有可信接口的合法 continuation 能推进；输入错误不触发盲重发 | L1/L2 |
| T08 | 与检查并发修改共享页中的嵌套地址、数组或成员；检查一个副本却使用另一个 | 所有安全相关字段使用同一已验证快照；不要求原始并发快照等同诚实输入，但所得任意值必须安全 | L1/L2 |
| T09 | 发送大量合法形状但昂贵请求、反复唤醒空队列、永久持有请求槽位 | 可信处理时间与内存消耗有界，不能因压力跳过检查；公平性/持续可用性另报 | L1/L2/L3 |
| T10 | 使 Proxy 响应泄露 padding、未用 result 字段、上次 Client 的元数据或原始物理地址 | 可信对外返回按契约初始化并限域；Proxy 自有不可信内容仍按不可信输入处理 | L1/L2 |

**新增：组合攻击**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| X01 | Proxy 掩盖 A 的 fault，同时让 B 用同数值 GPUVA/槽位运行，并重放 A 的旧完成提示 | 按真实 owner、绑定与错误历史处理；B 不能替 A 成功，A 的故障不能污染无关 B | L1/L2/L3 |
| X02 | A 的发布回复丢失后 Proxy 声称取消，Host 回收/重分配 P，B 尝试用旧 GPU 工作访问 P | 只要发布可能生效便固定 P；未经可信撤权不得复用；旧授权不能访问新 owner | L1/L2/L3 |
| X03 | 先假设 Proxy 完全失陷，再组合合法服务 token、原生驱动控制入口、另一设备 DMA 或 reset | 所有等效控制路径保持同一边界；攻陷 Proxy 不能取得 Client 数据或可信控制状态 | L2/L3 |
| X04 | A 使用密集故障/长任务和最高可申请优先级，Proxy 借资源压力要求清理 B 的活动页 | 可以降级服务或拒绝，但压力不得触发 B 的提前回收、假成功或权限复用 | L1/L2/L3 |

**新增：正常对照**

| ID | 场景与注入 | 预期行为 | 层次 |
| --- | --- | --- | --- |
| P07 | 同一可信 Client 在多个线程/REC 提交独立任务并交错查询 | 合法并发推进，各 token 只发布一次；不把多线程等同重放 | L1/L2/L3 |
| P08 | BO 正常进入缓存，再由原归属上下文取出、改数据并重新授权 | 合法缓存复用成功，无旧任务授权；按 API 契约清零或由所有者初始化 | L1/L2/L3 |
| P09 | 从映射中间解除部分范围，再重映射该洞；两端保持可用 | 按公开 API 支持的粒度正确工作；不支持的操作明确拒绝且不改变已有映射 | L1/L2/L3 |
| P10 | FW 能力给出合法最大队列数，合法镜像按支持的分片协议上传 | 合法上界接纳；不以拒绝全部固件/队列满足攻击测试 | L1/L2/L3 |
| P11 | 任务真实失败，Client 收到错误终态后进行可信恢复并提交新任务 | 旧任务报错不报成功；恢复后的新任务可运行；页释放仍受撤权约束 | L1/L2/L3 |
| P12 | Proxy 断连后恢复功能会话，或 VM_SYNC 幂等重试，无新的执行授权 | 允许协议支持的重建/查询；不重复执行旧任务，不遗失权威映射与引用 | L1/L2/L3 |

## 4. 六个可以直接细化为测试的实例

**实例一：假完成与多队列部分完成（C01/C12/C16，配 P02/P03）。** A 提交两个队列成员，后端只让第一个完成，第二个保持 blocked 或有非零 scoreboard。Proxy 发送成功回复、hint、虚拟 IRQ，并重复旧 timeline point。Client 必须继续查询 RMM，不得交付成功；错误 fence 的 signal 与成功需要区分。随后让第二个完成并满足 cache 可见性，正常对照必须能成功。记录全部成员状态、可信 FINISH 返回、本地 fence status 和 CPU 读回的已知输出。

**实例二：首次发布之后丢回复（A05/T07/X02）。** 在第一笔可能被设备观察的 producer/doorbell 更新之后丢掉响应，Proxy 随即请求重试并声称上次未执行。检查授权只被消耗一次，真实执行计数不增加第二次；Client 不能仅因超时重新提交。此时关闭对象，backing 仍必须保留。只有可信路径确认旧访问退出才能复用页面。用受保护发布轨迹或隔离的计数输出验证，不依赖 Proxy 日志。

**实例三：页表/BO 生命周期竞态（M08/R07，配 P08）。** 先让任务持有 BO，再并发 UNMAP、BO_IDLE、close 与缓存取出；在最后一次引用变化前后逐点暂停线程。检查活动页不会进入可复用缓存，同一 GPUVA 不会悄悄换成新 backing。正常完成及撤权后，再由原 owner 缓存命中并提交新任务，确保安全检查没有把复用功能整体封死。

**实例四：固件认证与解析器是两道边界（H03/H09/H10）。** 生产入口测试修改镜像一个字节、分片留洞、seal 后替换来源，期望在认证边界拒绝且零启动。解析器单独测试 data_size>section_size、最大 stride、尾部短接口和区间重叠，使用测试专用受控输入并启用 ASan/UBSan；它不证明生产环境能加载这些镜像。不得为了覆盖解析器而把测试摘要或通用验签绕过带入运行固件。

**实例五：真实旧 IRQ 错绑新任务（C04/C14/C15/X01，IRQ 扩展用例）。** A 在槽位 s 上产生事件并暂缓交付；执行合法切换流程后尝试将 s 绑定 B，再递交 A 的旧事件。记录必须在切换边界被消费、保持旧归属或标为不可归属，不能事后加 B 的 generation 就当 B 的完成证据。B 的成功只能来自 B 独立充分的设备证据。若 A 的 fault 历史已遗失且影响范围不明，应按可证明的保守范围阻止成功；不可一概把所有无 IRQ 的轮询任务阻塞。

**实例六：GPU 内部残留（M12）。** A 在实际设备支持的本地/scratch 存储写入每轮新随机标记，按不同停止、抢占、reset 和 Client 切换方式交给 B；B 用受控程序尝试读未由自己初始化的可见区域。包含未播种、A/B 顺序互换、同 Client 与跨 Client 对照，避免把自身未初始化数据误认成泄露。一次没读到标记不证明不存在残留，需要覆盖实际清理粒度和调度状态；若平台不提供这种访问能力，记录适用性依据，不伪造 PASS。

## 5. 从 CVE 提炼测试，不直接宣称本项目有同一漏洞

本轮重新获取 CVE 官方 CNA 记录，精选 **22 个 CVE：7 个 Mali KMD、13 个 Linux Panthor、1 个 Panfrost、1 个 GPU 残留数据案例**。先用 NVD 关键词发现候选，再按 CVE 官方记录核实；关键词只出现在栈或模块列表的无关条目未纳入。版本/产品/修复提交原文保存在证据 JSON，不能仅凭 Linux 6.12 或 GPU 型号推断状态。

| CVE（官方记录） | 组件 | 已披露问题 | 对应测试 | 本项目适用性与边界 |
| --- | --- | --- | --- | --- |
| [CVE-2022-22706](https://www.cve.org/CVERecord?id=CVE-2022-22706) | Mali KMD | 只读页被写 | M04/M08 | 类比权限放大；不据 Mali 型号判定当前 Panthor/RMM 受影响 |
| [CVE-2022-38181](https://www.cve.org/CVERecord?id=CVE-2022-38181) | Mali KMD | GPU 内存 UAF；原披露涉及 JIT/回收生命周期 | R01/R06/R07 | 类比引用与缓存复用；未采用同一实现则不搬用原 PoC |
| [CVE-2023-4211](https://www.cve.org/CVERecord?id=CVE-2023-4211) | Mali KMD | 访问已释放 GPU 内存 | M08/R01/R04 | 类比释放与设备映射不同步 |
| [CVE-2023-33200](https://www.cve.org/CVERecord?id=CVE-2023-33200) | Mali KMD | 竞态引发 UAF | A07/R05 | 类比检查、引用与关闭窗口 |
| [CVE-2023-6241](https://www.cve.org/CVERecord?id=CVE-2023-6241) | Mali KMD | 内存处理竞态/UAF | R03/R05 | 类比正常与失败路径的并发回收 |
| [CVE-2024-4610](https://www.cve.org/CVERecord?id=CVE-2024-4610) | Mali KMD | GPU 内存 UAF | R01/R02/R05 | 类比整类生命周期不变量 |
| [CVE-2023-26083](https://www.cve.org/CVERecord?id=CVE-2023-26083) | Mali KMD | 内核元数据泄露 | A08/H13/T10 | 测试返回字段与清零；不是内存耗尽意义上的 leak |
| [CVE-2024-46837](https://www.cve.org/CVERecord?id=CVE-2024-46837) | Linux Panthor | 无权限检查的高优先级 GROUP 可导致 DoS | A10/X04 | 权限策略与可用性；不能据此承诺恶意 Host 下公平 |
| [CVE-2024-53071](https://www.cve.org/CVERecord?id=CVE-2024-53071) | Linux Panthor | IO mmap 标志允许后续提写权或不合适的私有映射 | H12 | 公告并未认定 FLUSH_ID 写入本身可控制敏感硬件；测试映射属性组合 |
| [CVE-2024-53116](https://www.cve.org/CVERecord?id=CVE-2024-53116) | Linux Panthor | 部分 BO 映射跨 scatterlist 时 offset 处理错误 | M09 | 私有 backing 和原生 SG 路径分别验证 |
| [CVE-2025-21843](https://www.cve.org/CVERecord?id=CVE-2025-21843) | Linux Panthor | priorities_info 未初始化并返回用户 | A08/H13/T10 | 当前所读 DEV_QUERY 无该分支；按同类输出泄露用例研究 |
| [CVE-2025-38596](https://www.cve.org/CVERecord?id=CVE-2025-38596) | Linux Panthor | GEM put 后 debugfs 路径访问对象 | R10 | 当前所读函数在 put 后直接返回，未见公告所述后续 debugfs 使用 |
| [CVE-2025-40225](https://www.cve.org/CVERecord?id=CVE-2025-40225) | Linux Panthor | 部分 UNMAP 需要两个新 GPUVA 节点却仅预留一个 | M09 | 对合法分裂及第二次分配失败同时验证 |
| [CVE-2025-68747](https://www.cve.org/CVERecord?id=CVE-2025-68747) | Linux Panthor | UNMAP 失败后遗留 VA 树节点造成 UAF | R08 | 元数据清理与 backing 安全保留必须分开；不能机械照搬释放策略 |
| [CVE-2025-68748](https://www.cve.org/CVERecord?id=CVE-2025-68748) | Linux Panthor | unplug 与待处理 FW worker 竞态/UAF | R09 | 软件回调排空和真实 GPU 撤权是两个条件 |
| [CVE-2025-71314](https://www.cve.org/CVERecord?id=CVE-2025-71314) | Linux Panthor | cache flush 卡死后的未决请求与恢复处理 | R11/H14 | 不能用超时、reset ACK 证明原任务成功或资源安全 |
| [CVE-2026-74452](https://www.cve.org/CVERecord?id=CVE-2026-74452) | Linux Panthor | FW 数据长度超过所分配节区造成越界 | H09 | 当前 RMM parse_sections 有 data_size≤size；原生 loader 是另一条待核验路径 |
| [CVE-2026-89825](https://www.cve.org/CVERecord?id=CVE-2026-89825) | Linux Panthor | FW 接口 offset 32 位回绕及使用错误结构尺寸 | H10 | 当前原生接口函数仍见该检查形式；RMM shared_ready 使用独立范围校验 |
| [CVE-2026-89826](https://www.cve.org/CVERecord?id=CVE-2026-89826) | Linux Panthor | FW build-info 范围回绕、短 metadata 与零长度 | H09 | 先核对对应解析分支是否存在，再做边界变体 |
| [CVE-2026-99003](https://www.cve.org/CVERecord?id=CVE-2026-99003) | Linux Panthor | queue 数超过 FW 初始化槽位数 | A09 | 当前工作树两个入口已有实际 slots 检查；尚不能当冻结镜像已验证 |
| [CVE-2024-35951](https://www.cve.org/CVERecord?id=CVE-2024-35951) | Linux Panfrost | 缺页映射分配失败时 page 引用回滚不平衡 | R12 | Panfrost 不是本共享路径；迁移错误路径守恒测试 |
| [CVE-2023-4969](https://www.cve.org/CVERecord?id=CVE-2023-4969) | 多厂商 GPU / LeftoverLocals | GPU local memory 跨工作负载残留泄露 | M12 | 不能推断 Mali-G610 受影响；必须按具体 GPU/驱动/清理机制验证 |

判定“本项目受影响”需要同时建立：对应缺陷代码存在、构建启用、攻击者输入可达、未被当前协议阻断、症状/修复差异得到验证。当前仅作来源查证和定向源码对照，没有执行 CVE 利用程序，也没有完成上述适用性闭环。

**修复所在组件决定安全意义。** Proxy 的普通驱动崩溃属于功能可靠性问题；若导致其完全失陷，威胁模型本来就允许这种状态，仍需验证无法越过 RMM。相同缺陷落入 RMM/可信 FW 或 Client A 的可信内核则直接影响 TCB，不能以“Proxy 不可信”忽略。原生/直通路径也有真实使用者，应单独维护，不能套用共享模式的隔离结论。

**四处定向代码核对，均非新增测试 PASS：**

- RMM 的 parse_sections 明确检查节区数据不大于运行区间，seal 对私有快照求摘要；对应 H09。独立解析器测试和生产认证测试应分别保留。
- RMM 的 shared_ready 使用宽整数验证 group/stream 尺寸，再检查输入输出区间；原生 Panthor 的 panthor_init_cs_iface/panthor_init_csg_iface 仍可见 u32 offset 与 Host wrapper sizeof 检查形式，对应 CVE-2026-89825，需单独确认路径及输入可达性。
- 当前工作树的 GROUP 创建已在 ioctl 和内部入口核验实际 cs_slot_count，与 CVE-2026-99003 的关键边界对应。应测试 0/s/s+1/MAX/MAX+1，不能因有条件语句就宣称候选镜像已完成验收。
- 当前 DEV_QUERY 没有公告中的 priorities_info 分支；所读 GEM 创建函数在最后 put 后直接 return，未见公告中的 debugfs 使用。因此这两条用于同类测试，不列为已确认漏洞。

代码定位（本轮只读核对的工作树，具体哈希见证据清单）：

| 关注点 | 代码入口 |
| --- | --- |
| 真实页面来源、别名冲突与描述快照 | [RSI 私有 GPU 入口](../../opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c)：source_page、input_pages/input_commands |
| BO 登记、映射事务、映射检查缓存 | [私有内存核心](../../opencca/tf-rmm/runtime/core/opencca_gpu_private.c)：BO/mapping/cache-set 生命周期 |
| 固件认证、接口范围、队列证据与完成 | [RMM 固件协议核心](../../opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c)：parse_sections、gpu_firmware_seal、shared_ready、task_queue_snapshot、task_finish |
| 当前 IRQ 掩码及实际设备操作 | [RK3588 可信 GPU 后端](../../opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c)：GPU_INT_MASK/MMU_INT_MASK/JOB_INT_MASK |
| BO 缓存、最终注销及 Guest 可信调用 | [realm_gpu](../../Linux-Guest-GPU/drivers/char/realm_gpu.c)：realm_gpu_bo_put、realm_gpu_bo_alloc_cached、realm_gpu_task_call |
| 功能响应与真实完成的分界 | [Client 驱动](../../Linux-Guest-GPU/drivers/gpu/drm/panthor-client/panthor_client_drv.c)：READY_LAUNCH、FINISH 与本地 fence |
| 与 CVE 对照的原生接口解析 | [原生 Panthor FW](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_fw.c)：panthor_fw_load_section_entry、panthor_init_cs_iface、panthor_init_csg_iface |
| 实际槽位检查与 GROUP 建立 | [Panthor 调度器](../../Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_sched.c)：panthor_group_create 的 cs_slot_count 检查 |

## 6. 现有测试入口与覆盖边界

以下为现存入口，方便扩展用例；本次未执行。现有测试不自动等价覆盖本矩阵全部变体。源码正在清理时应先完成测试夹具与 ABI 迁移，并冻结被测输入。

| 现有入口（仓库根目录） | 可承接的用例 | 证据边界 |
| --- | --- | --- |
| python3 scripts/check/check-gpu-rsi-boundary.py --out <新目录> | M01/A01/A07/A11/T08 | 真实边界代码提取与替身，不能替代实际 REC 并发/硬件权限 |
| python3 scripts/check/check-gpu-private-bind.py | M02/M08/M09/T06 | Client VM_BIND 控制流/失败清理，不证明实体 PTE 及设备访问 |
| python3 scripts/check/check-gpu-private-metadata.py | M09/T06/H06 | 验证元数据路径不改变硬件映射；仍是后端替身 |
| python3 scripts/check/check-gpu-task-bridge.py | A02/A05/A07/T02/T03/T07/C16 | 实际 owner/RPC 代码＋kernel/RSI 替身；不涵盖真实 FW |
| python3 scripts/check/check-gpu-private-submit.py | A06/A07/C16/P07 | 提交规划、依赖和交付；并发内核行为需补集成测试 |
| python3 scripts/check/check-gpu-bo-cache.py --out <新目录> | R07/P08 | 缓存函数＋锁/内存/RSI 模型，不代表 Linux 竞态已证明 |
| python3 scripts/check/check-gpu-stream-status.py | C07/C10/C12/C13 | 状态读取与新鲜性；真实 GPU 时序需 L3 |
| bash scripts/check/check-rmm-gpu-private.sh | 核心映射/FW/控制/撤权等回归 | 完整离线集合；不是实体攻击覆盖率或跨租户安全证明 |

输出到固定 build 目录的脚本不要并行运行，避免证据被覆盖；使用独立工作树或为 harness 增加明确输出参数。硬件阶段先读运行手册，通过 lab-run.py 获取独占锁；侵入式故障注入与性能跑分分批进行。当前要求仍是先完成 720p 门槛，再扩展 API/计算/多 Client/ML，不能直接沿用旧成绩或旧安全 PASS。

**建议的第一批 12 组：** M01/M04（归属与权限）、M08/M09（映射与旧访问）、A02/A05（关系与只发布一次）、A09（真实 slots 上界）、H01/H02（MMIO 完全中介）、H03/H09/H10（FW 与接口）、H05（GPU 不能伪造全部完成依据）、C01/C12/C16（假成功与交付）、R01/R03/R07（回收与缓存）、T01/T02/T06/T08（传输边界与快照）、X02/X03（串通绕过）、M12（残留前提）。先用 L1/L2 暴露协议错误，涉及实体前提的组必须再做 L3。IRQ 扩展就绪后增加 C04/C14/C15。

## 7. 验收判据与记录方式

每项以“配置一个已知合法状态→在指定边界注入→执行操作→核对安全效果→移除注入执行正常对照→验证恢复”组织。可控并发先穷举关键切点，再做带种子的随机交错；随机压力不能替代关键竞态的确定复现。

- **证据充分才 PASS。** 要看到预期拒绝/保留行为，实际无越权读写、无额外硬件发布、无假成功、无提前复用，并且匹配的合法用例可运行。一个 -EINVAL 或 Proxy 日志不够。
- **FAIL 区分影响。** 内存隔离失败、授权失败、假成功、提前复用属于安全失败；合法输入崩溃、死锁或恢复失败还应单列功能/可用性失败。单纯恶意方拒绝服务不是保密性破坏。
- **执行状态与前提分列。** NOT_RUN 表示未执行；机制缺失记录 NOT_IMPLEMENTED；硬件边界不能证明记录 NOT_VERIFIED；NOT_APPLICABLE 需要版本/代码/能力不适用的具体证据。不要将后几项计入 PASS 分母。
- **观察必须可信。** HPA、真实 PTE、授权和发布次数从可信插桩/受控后端取证；Client 随机哨兵和已知输出独立交叉核对。调试接口只能存在于实验构建，不可引入生产绕过。
- **同时保留性能代价。** 记录拒绝成本、RMM 调用/驻留时间、锁占用、设备恢复耗时、峰值保留页和正常 Client 延迟；这些是测试设计，当前没有新增测量结果。

记录字段：版本及镜像哈希｜攻击主体/目标 owner｜对象与映射/绑定代次｜注入阶段和随机种子｜实际命令/run-id/退出码｜可信前后状态/控制写入/错误历史｜fence 与输出｜引用和资源恢复｜PASS/FAIL/NOT_RUN/NOT_IMPLEMENTED/NOT_VERIFIED/NOT_APPLICABLE 及原因。

影响版本以官方 CNA 记录为据。候选发现使用 NVD 的 Panthor 和 Panfrost 检索。[CVE 官方记录](https://www.cve.org/) · [GHSL-2022-054](https://securitylab.github.com/advisories/GHSL-2022-054_Arm_Mali/) · [CERT VU#446598](https://kb.cert.org/vuls/id/446598)

统一记录：扩展安全攻击验证计划与 CVE 对照｜现有完整单 Client 720p 1099 → 本次未测｜差值/百分比 N/A｜纯文档和只读代码/资料分析，未改运行代码，无新增性能测量｜资料与源码指纹：build/security-attack-expansion-20261109/｜新增 46 项全部 NOT_RUN；既有 46 项亦未在本轮执行，不继承 PASS。
