# 私有 GPU 路径：性能候选与已有实验索引

**FX READY／RETURN租约摘要复用已撤回，仍保留FU RMM＋FT Client＋原DX。** 紧邻完整720p原版972→候选980（+8／+0.82%），未达预设982保留线。实际核心42组差分证明热路径BO扫描2→0，冷路径双遍扫描、真实NC屏障及硬件／完成检查保持；3个编译错误变体拒绝、完整私有回归退出0和平台／核心／RSI检查通过。两轮33场景validation逐项26/1/6一致、健康／资源与各11份SHA通过；219项FU输入、实际SD2及四Guest已恢复，246项候选输入另以封存副本核验。**无新增保留提速，1000与整体目标未完成，ML／API／多Client未扩展。** 见[实施记录FX节](GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md#fxreadyreturn-复用已持有租约摘要2026-11-02)。

**FW当前成本诊断已撤下，仍保留FU RMM＋FT Client＋原DX。** 近期未修改对照972→诊断969（−3／−0.31%，非紧邻／重启条件），无新增保留提速；原保留971／971。当前空闲anchor重验约32.218µs／退休批，占保留域准备92.410%；STATUS ACK约29.819µs／批，占完整FINISH29.537%。20项130标量冻结快照、实际后端三种计时模式输出一致／3错误变体、完整33场景逐项validation26/1/6、12份SHA、健康／资源核验通过；219项FU源码／实际SD2／四Guest已恢复并核验，诊断模块及Pi临时上传已清理。计时互有包含，不能相加当作CPU收益；优先研究回调边界完整的提交／完成事务组织，避免重复微调等待。1000与整体目标未完成，ML／API／多Client未扩展。见[实施记录FW节](GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md#fwfu-当前路径分段成本与冻结快照2026-11-02)。

**FV提示反馈候选已撤回，当前仍为FU RMM＋FT Client＋原DX。** 同期完整720p972→974（+2／+0.21%），未达预设982保留线；提示跳过／批5.923→2.723、立即排队5.962→3.704µs，但主动暂停293.803→300.226µs，局部减少没有足够整机收益。两轮33场景validation逐项26/1/6一致、健康／资源及各11份证据SHA通过。136个实际worker模型、3个编译错误变体、ARM64构建及634条私有PASS标记通过；两项源码撤回后130场景模型、219项FU冻结输入／实际SD2／四Guest终检通过。RMM未重建或刷写，**974不保留**；原保留两轮971／971，最新纯对照972。1000及整体目标未完成，不扩展ML／API／多Client，不仅调预测／等待常数重试。见[实施记录FV节](GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md#fv提示未到达反馈训练首查预测2026-11-02)。

截至FU，**当前性能保留候选：FU RMM＋FT Client＋原DX，完整720p971／971。** 同期FT对照957，**+14分／+1.46%**，两轮均过预设967保留线。稳定租约内复用BO元数据谓词，36处写边界失效；身份／映射代次／槽位及硬件根／故障／真实完成检查保持新鲜。三轮33场景validation逐项26/1/6一致，健康／资源及各11份证据SHA通过；折射86→82／79FPS的回退保留。20个暖摘要模型、7个错误变体、完整私有634条PASS标记和实际平台／核心／RSI检查通过；219冻结输入、实际SD2／四Guest终检通过。新包`build/rmm-client-bo-20261030/lease-summary-fu/runtime-candidate/`及同目录`firmware/`；FT保留回退。**1000尚未达到，ML／完整API／多Client未扩展，整体目标未完成。** CPU自动频率，两次候选不证明跨负载稳定收益。详见[实施记录FU节](GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md#fu稳定租约元数据摘要与ft提示观察组合2026-11-02)。

截至FT，**保留FS原样RMM固件＋FT Client＋原DX**：完整720p934→958／956（均值957，+23／+2.46%），两轮均过预设944保留线；1000尚未过。新增行为是让现有有界主动等待读取NC提示，提示到达立即回到真实FINISH；并非只更换等待常数。FS与FT的原始命令准入、8次跳过／8次真实pending快速重试、原deadline及回收检查不变。无提示任务保持原等待；worker独占task调用／put，stop同步取消后才释放，task持BO引用，reaper只释放abandoned任务。两轮主动暂停294.433／293.663µs／退休批，低于FS的322.711；查询1.1400／1.1411次／批，约14.9%提示等待提前结束。局部墙钟含设备／调度，不当作纯CPU或可累加收益。两轮逐项33场景validation26/1/6、健康／资源及各11份SHA通过；130个实际worker模型、3个编译错误变体拒绝、完整私有633条PASS标记及193冻结／实际SD2／四Guest核验。当前包`hint-wait-ft/runtime-candidate/`，旧DA／ED回退保留；后续从此组合优化，不回退至仅查询减少但无保留收益的FS。详见实施记录FT、`comparison-two-runs.json`及`final-verification.json`。

截至FS，RMM在保留原始start／bytes准入和受保护完成序列的基础上，为单成员任务生成Client可读NC进度提示；显式协商ABI，检查提示页身份、真实PTE、权限及生命周期，最多跳过8次查询后强制真实FINISH。完整720p934→936（+0.21%），未达944线，已恢复DA／ED934。查询／退休批2.463→1.138，COMPLETE调用198.609→106.656µs／批，但观察间隔265.867→339.845µs／批，主动暂停238.827→322.711µs／批；这些含设备与调度的墙钟不可当纯CPU或可直接节省时间。33场景逐项validation一致、健康／资源／11份SHA、166生产／201冻结输入及实际SD2／四Guest恢复核验。四个实际RMM错误变体编译成功后被断言拒绝；本地模型不替代实体隔离。与FQ区别在于原始命令范围未替换，提示由可信侧生成；性能仍不支持保留。后续不只调提示／等待常数；需要新的设备推进时序证据。详见实施记录FS及`trusted-progress-fs/final-verification.json`；1000未过。

截至FR，仅RMM的`-O2→-O3`已完成实机对照934→934（0.00%），未达预设944保留线，恢复DA／ED934。23份参数只归一化构建目录和优化等级后相同，Debug／断言／ISA保留；代码段283328→344768字节（+21.69%）、BSS不变，没有端到端收益。完整33场景、逐场景validation26/1/6一致、健康／资源／11份SHA、165生产／198冻结／四Guest／实际SD2恢复核验；私有633／后端4288条模型标记和O3 timer131072／66通过。后续不要仅换全局编译等级／调优标志或将小幅局部墙钟改善当作提分；应优先研究有新边界证据的设备状态观察与任务推进。见实施记录FR及`optimization-o3-fr/final-verification.json`；1000仍未过。

截至FQ，本地GPU写回提示／Client命令跳板候选在上板前否决：实际RMM页表／引用核心拒绝原始未映射命令，却接纳替换后的已映射跳板。提示不直接授权fence仍不足以保证原准入语义；以后不可只在Client增加检查便重试。候选未部署、候选完整720p为NOT_RUN；三项源码及165生产输入恢复，193冻结输入保留核验。原版新对照934（此前933，+0.11%）仅复测波动，无保留提速；完整33场景、validation26/1/6、健康／资源／11份SHA通过。见实施记录FQ和`local-progress-fq/final-verification.json`。后续任何设备提示应由可信侧在保留原始命令准入的前提下生成，并保留真实FINISH及有界回退。

截至FP，完成观察分段通过固定70字段冻结快照取得全程累计统计，933→诊断936（+0.32%），已撤下恢复DA／ED933。独立时钟未改变原策略／超时语句，真实固定后端三种编译变体拒绝；完整33场景、validation26/1/6、健康／资源、12份SHA及165生产／205冻结输入恢复核验通过。嵌套控制读取不与父阶段相加，SUCCESS不等于GPU完成。详细数值和证据见实施记录FP与`completion-phases-fp/profile.json`；本轮仅诊断，无保留提分，1000仍未过。

用于在提出候选、构建和部署前查重。当前运行版本、完整结果与证据仍以
[当前基线](CURRENT_BASELINE.md)和[实施记录](GPU_RMM_PRIVATE_BO_IMPLEMENTATION_20261030.md)为准。
本索引本身只整理实验记录，不修改运行代码；下列测量来自各轮独立实验。

截至FO，在FN一致timer快照固件上让原首次／八次GPU短等待均使用绝对零slack睡眠，完整720p933→855（-8.36%），未达944保留线，已恢复DA／ED933。与AD／FF的区别是已有FN同诊断Client的15.660s→7.497ms实机新依据；本组合仍未形成生产提分，后续不要只换睡眠常数。122个Client模型、timer131072／66、快照14400／4800及五变体、普通重建18415616字节代码相同、33场景／validation26/1/6／健康／资源／11份SHA，165生产／221冻结／四Guest／实际SD2恢复核验。详见实施记录FO及`cooperative-wait-fo/{assessment,wait-comparison,final-verification}.json`；1000与整体目标未完成。

截至FN，共同timer退出快照在同冻结睡眠诊断Client中478→891（+86.40%），入口最长15.660s→7.497ms、≥10ms19→0；但原始ED完整720p新对照933→候选932（−0.11%），未达预设944线，已撤回恢复DA／ED933。实际源码模型14400组合／4800边沿和五变体拒绝、原实现语义反例通过；未捕获此前实机Host／REC错配，不能称已解释原ED差距。四轮完整33／validation26/1/6、健康／资源／每轮11份SHA，165生产／270冻结／四Guest及实际SD2恢复，timer131072／66与Client113通过。下一候选只可基于此新时序依据验证协作等待，不把先前AD／FF无修正的睡眠试验直接当作结论；单纯FN本身没有生产提分，1000仍未过。详见实施记录FN及`timer-snapshot-fn/{assessment,pure-assessment,final-verification}.json`。

截至FM，实际IRQ27／HCR／Guest PC／同循环前序状态的292字段冻结采集完成；完整720p934→诊断314（−620／−66.38%），已撤下恢复DA／ED934。最大入口晚到15.842801秒与`run_realm`＋PAuth重合99.999582%；六个最长run的IRQ退出PC均为`cpu_do_idle+0x8`、WFI之后，两端全部LR无IRQ27匹配项，CTL5、CVAL不变。三个有效前序handler仅5→5，无前序重装／输出翻转证据；其他前序载荷无效且不使用。源码report→save的两次timer读取存在到期窗口，实际源码块3600有限时序复现850个不一致组合（虚拟600、物理300，可重叠），共同保存快照仅在隔离模型验证；尚未进入运行代码或部署，不是实机根因或提速证明。下一步先验证共同退出快照及负例，再完整720p因果／原ED对照；不直接修改EOI、使能或取消等待。完整33／validation26/1/6／健康／资源／12份SHA及163生产／270冻结／四项Guest／实际SD2恢复通过；本轮1105 LR组合、17解析拒绝、timer131072／66和Client113通过，完整639未重跑。初始按timer拆分计数预期错误的断言失败保留，v3读取顺序核对通过。见实施记录FM及`timer-delivery-fm/{assessment,boundary-review-v1,symbolization-v1,exit-snapshot-review/review-v3}.json`。1000及整体目标未完成。

截至FL，已替换FK不完整的UART报告，实机取得冻结代次的334字段快照，两次SMC读取／两次文件读取一致，越界与旧代次拒绝。完整720p934→诊断341（−593／−63.49%），诊断已撤下恢复DA／ED934，无保留提分。最大入口晚到15.470060秒的99.999434%重合`run_realm`＋PAuth，计数器桥接不确定度2.042µs；timer检查最大1.458µs、退出处理最大127.701ms。只证明该样本主要位于Realm执行区间，不能直接认定Guest忙等、WFI或某个中断缺陷。六个最长run边界的timer均到期／未屏蔽、CVAL未变、PPI27在退出处关闭；屏蔽到期PPI属于原设计，LR127不是timer LR，不能据此直接修EOI或只改使能。下一步收集timer IRQ27的实际LR、HCR／ELR及前序timer输出转换，检查快速返回Realm时的交付／空闲路径，再做有对照的优化。完整33场景、validation26/1/6、健康／资源、12份证据SHA、163生产／271冻结输入／四项Guest与实际SD2恢复核验；1000与整体目标未完成。见实施记录FL及`realm-phases-fl/{assessment,timeline-overlap,boundary-review}.json`。

截至FK，RMM内部阶段诊断完整720p934→190（−744／−79.66%），已恢复DA／ED934。CPU2-only、每阶段top6≥10ms的采集通过构建／固定布局，本地私有套件639条PASS标记及timer131072／66；初版BSS溢出保留。**UART阶段报告完整性FAIL，尚无RMM内部归因**，不能从局部字段推导Guest或RMM主因，也不能用它认定EOI／PPI修复。Client两组报告分别校验，最大入口晚到16.404910秒；原单报告解析失败保留，版本化解析不混合两组计数。33场景、健康／资源、161项生产输入／225项冻结输入／四项Guest及实际SD2恢复核验。下一步改用有界显式诊断状态读取与代次／字段完整性检查，先获得可信证据；尚未实现／测试。当前仍934，1000和整体验收未完成。见实施记录FK与`realm-phases-fk/assessment.json`。

截至FJ，已取得Host原始时钟／Guest单调时间的计数器桥接。934→391（−543／−58.14%）为非紧邻组合诊断，已撤下恢复DA／ED，不是新优化。CPU0 overrun31401使原全局分析FAIL；另行限定固定Client CPU2、零丢失的局部对账：最长入口晚到11.299秒中Host换出仅14µs，99.9990%在一次`kvm_rec_enter`内，不支持Host调度饥饿为该样本主因。该调用内仍可能是Guest运行／WFI、RMM或monitor处理，不能直接认定timer重装缺陷；标准软件LR.EOI维护路径在源码中存在。时钟锚点报告字段覆盖错误已独立纠正，原始证据／全局失败保留，端点重算一致。下一步需要调用内部阶段与timer／LR状态的共钟证据，尚未实现／测试；不只换PPI使能、slack或worker优先级。完整33场景、健康／资源、源码与实际SD2恢复核验，当前仍934，1000未过。见实施记录FJ和`host-timeline-fj/assessment.json`。

截至FI，同FH诊断Client只改RMM平台PPI使能，完整720p紧邻579→609（+30／+5.18%）；入口晚到最大15.983047→15.878619s，≥10ms14→18，未消除长尾，已撤回恢复DA／ED934。模型确认Host保存位为0时原逻辑漏使能，但实测不支持它是已观察长暂停的解释；不能再仅凭这个反例重复该候选。下一步需要Host vCPU运行／物理timer／RMM返回与Guest IRQ的共钟链；尚未取得，不据此改timer常数、取消等待或省略真实完成检查。33场景、健康／资源及输入恢复核验通过，1000未过。见实施记录FI与`timer-enable-fi/assessment.json`。

截至FG，沿用FF的首次绝对timer等待，仅加入本地sleeper分段诊断。原ED对照934→639（-295／-31.58%），已恢复DA／ED；不同于新保留优化。281762次睡眠全部回调；最大暂停15.239841秒，其中目标到回调晚到15.239570秒、回调到恢复191.042µs、取消0.291µs。原始总等待／回调晚到桶各13次≥10ms，回调到恢复桶无≥10ms，只有最大事件保留完整逐段时间，不给其余事件或场景补配关系。下一步定位Guest架构timer IRQ入口、hrtimer处理与Host vCPU／IRQ交付；Guest墙钟尚不能区分是哪层。33场景、健康／资源和输入恢复核验完成；仍934，1000未过。见实施记录FG与`timer-stages-fg/assessment.json`。

截至FF，FE识别到glmark主线程207／214快照可运行后，首次尝试只对已有首查预测区间让出CPU。紧邻原版934→566（-368／-39.40%），不满足预定保留规则，已恢复DA／ED。不是AD全部短usleep或EF慢等待回退的重跑：首查绝对截止／零slack，早醒用剩余主动间隔，后续8次快查不变。然而可运行线程存在并不保证让出CPU提分；后续不只调整slack、首查睡眠常数或优先级，应先定位实际被重叠的应用工作与设备／唤醒时序。完整33场景、健康／资源和输入核验完成，当前纯对照934，1000未过。见实施记录FF及`first-cooperate-ff/decision.json`。

截至FE，FE稀疏身份诊断：完整720p935→932（-3／-0.32%），已撤下恢复DA／ED。214个暂停后快照中，真正可运行／延迟出队／队列过渡状态分别出现在211／3／0个快照，类别可重叠。FD的nr_running>1不能直接解释为应用竞争；EEVDF睡眠任务可仍计入该数。只增加诊断，无保留提速；1000和扩展矩阵／整体目标未完成。见实施记录FE与`runnable-identity-fe/peer-summary.json`。

截至FD，完整720p诊断932（对935为-3／-0.32%），已恢复DA／ED；没有新增保留优化。等待前后nr_running()>1的暂停占99.1765%次／对应区间99.6114%累计时长。采样不识别线程、不覆盖区间内部，也不是CPU剖析；FE已确认nr_running计数可能包含EEVDF睡眠／延迟出队实体，不能直接称为频繁CPU竞争；下一步须识别就绪线程及其延迟；不能把约239µs等待全部归因于挤占应用，不据此重试短usleep、降低worker优先级或只换忙等常数。保留真实FINISH、deadline与错误语义；下一候选需有不同的提交／观察机制及实测成本证据。见实施记录FD。

截至FC，保留DA RMM＋ED Client＋原DX runner，最新紧邻纯对照935。首次优化通用libc memcpy的对齐64位精确复制路径，935→934（−0.11%），未达946保留线，已撤回并核验146项生产输入／43项冻结输入／实际SD2和四项Guest。两轮33场景、validation26/1/6、健康／资源通过，1000未过。边界／本地模型通过及实际标量指令不等于提分；不再仅换复制宽度／展开常数重试，须先有执行分布或不同提交／观察机制证据。见实施记录FC和`memcpy-fc/final-verification.json`。

截至FB，保留DA RMM＋ED Client＋原DX runner，最新紧邻纯对照929。RMM仅增加`-mtune=cortex-a55`得到937（+0.86%），未达预先946保留线，已撤回并核验实际SD2／四项Guest／145项生产输入。完整33场景和健康／资源通过，validation仍26/1/6，1000门槛未通过。此候选不修改源码或弱化检查，但不能将代码布局变化当作稳定提速；不再仅换CPU调度选项重复测量。同队列依赖任务一次发布也已审查：现有Client会阻止失败依赖的后继执行，GPU顺序和ERROR_BARRIER不能保证等价，未实现该候选。见实施记录FB及`cpu-tune-fb/{same-queue-review,final-verification}.json`。

截至EY，已实现并测量稳定租约BO元数据摘要：紧邻ED931→944（+1.40%），未达预设946保留线，撤回恢复DA／ED及原DX runner。最新纯对照931；944不得视作当前保留性能。两轮完整33场景、validation26/1/6、健康／资源、源码／冻结输入和实际SD2核验；1000门槛仍未通过。下述EW／EX的“摘要尚未实现”仅为当时状态。

截至EX，保留DA RMM＋ED Client＋原DX runner；最新紧邻纯对照935，EX932未达946保留线，已撤回恢复。完整33场景、validation26/1/6、健康／资源、源码／冻结输入及实际SD2均核验；1000门槛未通过。EX仅改变BO热字段布局，不等于已实现EW提出的稳定租约摘要；后者须有完整失效边界及实际负例验证。详见实施记录EX和`bo-layout-ex/final-verification.json`。

截至EV，保留DA RMM＋ED Client＋原DX runner；最新原ED完整对照934，EV938未达到946保留线，已撤回。两轮validation仍26/1/6，1000门槛未通过；EU936及下文其他分数属于各自历史轮次，不拼成新优化收益。最终恢复见实施记录EV及`completion-heap-hint-ev/final-verification.json`。

EH用原ED镜像开启已有RPC计时，完整720p931，仅诊断，当前仍保留ED934。353713次RMM_TASK占累计RPC墙钟99.426%，Client／Proxy handler均值138.172／93.491µs；1044次VM_BIND占0.284%。分段有包含关系，不能相减成纯通信成本，也不是整个生命周期占比。旧poll_sleeps字段为0不证明新回复路径逐次零睡眠；completion等待均值0.180µs仅支持阻塞等待较少。后续优先细分实际TASK_DISPATCH准备／接纳／启动路径；不继续仅调整映射队列优先级或重复Proxy接收忙等。证据见`rpc-profile-eh/rpc-breakdown.json`及实施记录EH。

截至EQ，保留版本仍为DA RMM＋ED Client高优先级推进队列；EP失败后同固件重启的完整恢复对照为929，历史确认934；EQ928未保留。原ED收益对照为：紧邻普通对照892，ED两轮931／934（+4.37%／+4.71%）。冻结包`worker-priority-ed/candidate/`；**1000门槛未通过**。EC819、DZ881仍撤回；EE只做独立源码／模型，未部署；EF934→937未达944，已撤回恢复ED。各行使用各自当时对照，不能横比为同一实验。

EZ新增实际STATUS轮询计数与独立时钟诊断（931→936），已恢复DA／ED；长UART行损坏，无完整副本quorum，硬件循环／延迟结论不可用。FA仅重试短行报告，不是新的优化；不得从EZ碎片推出可省时间。

FA完成短行重采（931→935，仅诊断），已恢复DA／ED。38组有效报告，最后前缀343527次成功FINISH调用内830805次ACK，平均6.368次轮询／20.431µs；终组68无足够完整副本，不能冒充全程终点。统计包含设备响应及缓存读取等待，不是纯CPU成本；不能据此重跑CY／EC，下一候选须有新的准入／观察协作或可信事务边界。见实施记录FA和`status-ack-compact-fa/assessment.json`。

| 候选机制与检索词 | 已有实验 | 结论及重新尝试需要的依据 |
| --- | --- | --- |
| RMM内部阶段：`run_realm`、handle exit、timer check、top6区间 | FK诊断934→190，已恢复DA／ED | UART记录损坏使阶段完整性FAIL，不能定位内部停顿；两组Client独立报告只确认最大入口晚16.404910秒。下一步需要显式读取完整诊断状态，不再仅增加UART副本或借碎片推断重装／EOI缺陷。初版全CPU记录表超BSS，缩减CPU2后保持原内存／栈与GPU容量。无新保留提速。 |
| Host／Guest共同计数器与REC跨度：CNTVCT、CNTPCT、mono_raw、CPU2 | FJ诊断934→391，已恢复DA／ED | 全局因CPU0丢31401事件FAIL；独立CPU2零丢失局部对账支持最大11.299秒样本主要在一次REC调用内，Host换出14µs。不能将REC在途等同Guest活跃执行或直接定位RMM；后续应分测`run_realm`与退出处理，采集重装／使能／LR状态。无新保留优化。 |
| 定时器触发／线程恢复分段：hrtimer callback、resume、cancel | FG诊断934→639，已恢复DA／ED | 最大15.240秒异常在回调前：回调晚15.239570秒，之后191.042µs恢复；非已唤醒worker等待15秒。下轮先定位timer IRQ入口与Host交付，不只改优先级／slack，也不将Guest计时直接归咎Host。 |
| 首次预测等待让出CPU：absolute hrtimer、zero slack、first-only | FF：紧邻934→566，保留线946 | 已撤回恢复DA／ED。只在已有首查区间睡眠、早醒剩余主动等待、后续8次快查不变；场景保护False／长尾保护False。不凭glmark可运行比例宣称能重叠足够应用工作，不只换睡眠常数重复。 |
| 稀疏任务身份／EEVDF延迟出队：sched_delayed、task state | FE诊断935→932，已恢复DA／ED | 214快照中runnable／delayed／transient为211／3／0，可重叠；只读有界RCU采样，非连续并发证明。FD的nr_running不等同于应用可运行；不据总计数盲改睡眠／优先级，无保留优化。 |
| 主动等待的Guest就绪竞争：nr_running、first/retry、runnable endpoints | FD诊断935→932，已恢复DA／ED | 869596次暂停，任一端点nr_running>1占99.1765%（可含延迟出队实体）；对应区间时长99.6114%。非线程身份／连续竞争／纯CPU时间证据，不据此进行短睡眠或优先级微调；无保留优化。 |
| 通用libc memcpy：aligned scalar copy、word copy、byte loop | FC：紧邻935→934（−0.11%），保留线946 | 已撤回恢复DA／ED。BD只改接口读取，FC首次改通用复制；原版／候选各1057282组边界检查，完整私有633／后端4288条PASS标记。PREPARE−1.62%、COMPLETE操作−1.16%，但观察间隔+1.22%、查询／批+1.30%，无总分收益；不把静态宽度或局部墙钟当纯CPU收益。后续不只换复制宽度／展开常数。 |
| RMM CPU编译调度：mtune、Cortex-A55 | FB：紧邻原版929→937，+0.86%，保留线946 | 已撤回恢复DA／ED。O2／Debug／断言／ISA不变，23份flags核验、完整私有本地套件和两轮33场景完成。单轮及重启条件不证明稳定收益；后续优先结构性减少提交／完成路径工作，不只更换编译调度选项。 |
| 稳定租约BO元数据摘要：live_epoch、cache_metadata_epoch、live_eligible | EY：紧邻ED931→944，+13／+1.40%，保留线946 | 已撤回恢复DA／ED。全局可信变更代次覆盖36处写边界，溢出永久禁用复用；context／映射代次／槽位及硬件根／真实完成保持新鲜。19组新模型、7个新编译错误变体拒绝和原cache-set／实际后端／RSI／私有套件／完整33场景通过。PREPARE／COMPLETE调用墙钟约−5.21%／−4.57%，查询间隔+1.11%，不是纯CPU成本或可累加收益。后续不只换字段布局、缓存标志或保留线；须有实质不同的执行／观察协作及完整失效边界证据。 |
| BO热字段布局：private_bo、hot/cold fields、cache line | EX：紧邻ED935→932，−0.32%，保留线946 | 已撤回恢复DA／ED。只调整字段顺序，所有实时谓词／根／完成检查和600字节容量保持；静态缓存行覆盖减少不代表实机miss或端到端收益。56／31组实际核心差分、六变体、combined后端／RSI、完整33场景及恢复核验通过；无扫描专用实机计时，不能断言扫描本身无改善。后续不只换字段顺序，优先验证稳定租约摘要的变更／别名／失败失效边界。 |
| RMM租约元数据扫描计时：live_eligible、cache_set_check、BO lease summary | EW诊断：934→929，−0.54%，已恢复DA／ED | 原完整帧仅认证至37222次可信退休；后加独立三行计数器认证保留最终三份一致数据，不补最终头／退休分母。live_eligible2.039µs／次、集合扫描1.845µs／次，区间重叠不相加。下一候选为稳定租约BO摘要，须先覆盖所有合法变更／别名／heap／reset／reclaim失效负例，不缓存实际硬件根／完成证明。尚未实现，不能以局部计时推算提分。见实施记录EW。 |
| 无OOM单次提示：FINISH_HINT、last START replay、skip HEAP_EVENT | EV：紧邻ED934→938，+0.43%，未达946 | 已撤回恢复DA／ED。实机观测去重每文件值534623次跳过查询；COMPLETE调用／退休批−6.92%，查询次数+3.43%、间隔+3.94%，局部工作减少不足以证明端到端收益。五个编译变体拒绝、36个combined模型场景、实际新RSI／ABI／完整33场景及恢复检查完成；与CW只合并RSI而不省扫描不同。重试须给出查询／等待交互的实证改善，不重复独立入口合并或全局常数微调。见实施记录EV。 |
| 空闲依赖重试被新提交提前唤醒：idle kick、timer_pending、mod_delayed_work | EU：紧邻ED936→933，−0.32%，保留线946 | 已撤回恢复ED。仅无活动run且已有timer时提前调度，活动任务预算／deadline不变；观测每文件计数值17，不代表任务已就绪或节省了对应等待。完整33场景、健康／资源及输入核验完成；不能凭发现pending timer便声称性能瓶颈，不再仅调整提前唤醒条件或时间常数重试。见实施记录EU。 |
| 同钟场景关联：CLOCK_MONOTONIC、PRIVATE_WINDOW mono_ns | ES诊断929→933，+0.43%，已恢复 | printk local_clock与用户态单调时间未认证；严格分析器拒绝ES场景归属，不用估计偏移。分数变化不计优化收益，ET已补ktime_get_ns明确端点，关联96256批／全文件27.19%；已覆盖refract窗口延迟重排975.98µs／批，而大卷积effect2d查询7.912次／批且无timer回退。两轮均933，诊断后恢复ED；未知窗口不归属，不能据此重复全局调参。见实施记录ES／ET。 |
| 完成间隔组成与局部慢窗口：PRIVATE_WINDOW、sleep_ns、queue0_ns、queue1_ns | ER：四份历史run分析，无新GPU测量 | ED929间隔266.565µs／批中，主动暂停239.489、普通延迟重排22.753、立即排队3.232；立即排队仅占已统计阶段0.535%。最慢10个已保存窗口含83.892%延迟重排等待；没有同钟场景边界，不能归到具体场景。先补定位证据，不重复全局等待常数／worker交接微调；不能把设备重叠等待当成可直接节省CPU成本。见实施记录ER。 |
| 单vCPU VMM I/O线程与Realm执行分离：isolate_vmm_io、CPU0 housekeeping | EQ：恢复后ED929→928，−1／−0.11% | 未达预先944保留线，撤回恢复ED；vCPU仍为Proxy1／Client2、各一个，仅非vCPU线程移至CPU0。两轮完整33场景及健康／资源核验，validation26/1/6保留，1000仍FAIL。不能把EP多核失败归因于I/O位置，也不凭部署上合理而宣称提分；见实施记录EQ。 |
| 双vCPU Client与应用／worker并行：SMP、Client vCPU count | EP：只改冻结runner，首个count1计算停滞，无glmark分数 | 已否决恢复ED；双REC启动／基础探针通过不等于GPU工作正确。中断runner并终止本run Client后，RTT teardown WARNING与EBUSY保留；同固件重启恢复并另跑ED完整720p。重试须先定位多核停滞及生命周期问题，不能只增核或取消REC0绑定约束；见实施记录EP。 |
| 设备事件辅助完成：JOB IRQ、event ACK/rearm、CSG_SYNC_UPDATE、Client wake | EN离线原型；EO完整接通并上板：934→878，−6.00% | EO已撤回并恢复ED934。实际33958条会话提示，查询／批+3.62%，完成调用墙钟+3.73%、观察间隔−6.17%，完整33场景仍退化且blur保护FAIL。保留原FINISH、deadline与轮询回退；不能只看唤醒／间隔下降。再次尝试先给出事件来源／合并／触发时机及IRQ、跨VM成本证据，不仅调等待常数或复用EN模型PASS；见实施记录EO及event-wake-eo证据。 |
| 跨调用硬件能力快照：device capabilities、GPU_ID、MMU format、AS_PRESENT、shader／tiler | EM仅隔离副本，未上板 | 实际后端失败，独立后安装故障对照：基线6/6拒绝、候选6/6接受，整个候选否决。34项有限模型的MMIO31→23不支持部署或提分；保留当前所有能力／根／属性／动态故障检查，不通过删除旧断言保留缓存。 |
| 准入前准备／任务选择：PICK、STAGE、snapshot、task stage pipeline | EL诊断：934→936；均恢复ED | PICK0.929／STAGE14.742µs每退休批，对照同轮PREPARE137.496／COMPLETE198.954µs。未证明准入流水线、快照复用或缩小Client clean范围值得优先实施；不要以操作存在代替成本证据，或把工作前移等同于端到端收益。详见实施记录EL。 |
| Proxy接纳worker优先级：RX work、system_highpri_wq | EK：934→931，保留线944 | 未达944保留线，撤回并恢复ED934；仅事件驱动排队优先级变化，无RX忙等。完整33场景及恢复检查；不能从Client ED收益推定Proxy收益，或将EH往返减handler直接当作调度耗时。 |
| 同调用PUBLISH接纳结果消费：publish accepted、terminal START replay | EJ：934→935，保留线944 | 未达到944保留线，撤回并恢复ED934；实际ACK后START结果只供同调用外层消费，7→6，不跨回调／硬件写入／锁／RSI。不能仅凭局部检查数重做；详见实施记录EJ。 |
| Proxy接收侧主动轮询与请求通知抑制：request poll、RX poll | 旧共享路径P5：318→296；后续8µs：1167→1125 | 历史候选均撤回；缩短窗口或加入need_resched判断不足以成为新依据。与Client等待本次回复的短轮询、RMM驻留SGI唤醒区分；先定位当前路径时序，参见[设计指南失败项](GPU_PROXYCLIENT_OPTIMIZATION_DESIGN_GUIDE_20261025.md)和[探索记录](GPU_PROXYCLIENT_OPTIMIZATION_EXPLORATION_20261024.md)。 |
| 映射生产者与GPU推进队列优先级一致：VM_BIND、private_wq、WQ_HIGHPRI | EG：ED934→935，保留线944 | 已撤回恢复ED；只提高有序VM_BIND队列优先级，三个场景保护通过，但整体仅+0.11%。不能由ED的GPU队列收益推导其他worker收益；后续先用实际RPC请求分布和分段耗时确定映射是否位于主要瓶颈。 |
| 八次快速重查后高精度睡眠：`usleep_range`、HZ250、slow fallback | EE仅准备模型；EF：ED934→937，保留线944 | 已撤回恢复ED；慢速观察等待6.34→1.33ms，但整机仅+0.32%，查询略增。包含第六诊断桶的组合效果；不能据局部等待下降宣称ML／多Client收益或只换常数重试。 |
| Client同一worker有界连续推进：private inline worker、phase loop | BP：BM645→645 | 已撤回；最多四阶段／1ms且每步释放锁，立即排队等待3.109→0.853µs／批仍无整体收益。不能把整个COMPLETE gap当作排队成本；需实质不同机制与新逐阶段证据，不能只调整循环上限。见实施记录BP。 |
| GPU推进worker与应用的调度竞争：`WQ_HIGHPRI`、ordered GPU worker | ED：普通紧邻892→同一候选931／934 | 已保留；只改Client队列标志，RMM／Proxy／Host等相同；三轮完整33场景和资源／健康检查，validation26/1/6保留。重建普通Image可执行段逐字节一致。不要将COMPLETE墙钟下降当作纯RMM成本或跨负载证明；1000仍FAIL。 |
| 跨RSI分阶段STATUS ACK：split-phase STATUS、async ACK continuation | EC：891→819，blur/terrain/5×5保护失败 | 已撤回；查询/批+48.13%，调用墙钟−10.55%，worker间隔+54.07%，合计+17.96%。保持原请求与固定deadline也不等于有性能收益；重做须改变ACK pending与执行pending的调度协作，并提供新逐场景证据，不能仅复用本轮退出忙等。 |
| 非零缓存维护包装函数去除重复DSB：cache wrapper | DT：893→895，保留线902 | 已撤回；真实指令屏障2→1、零长度屏障与检查保留，未形成满足门槛的整机结果。不要仅凭局部指令减少重复。 |
| 只读MMIO快照合并屏障：readonly MMIO barrier | AO：535→533 | 已撤回；19次寄存器读取不减，屏障38→10仍无端到端收益；此前索引漏列，本轮补入。 |
| 多stream缓存维护合批：stream invalidate batch | BO：645→648，未达保留线 | 已撤回；保持每个216字节范围、合并末尾屏障，没有形成保留收益。与DT无合批/无地址数组的机制区分。 |
| START重试只读取实际参与检查的输入：replay input copy | DP：893→895，未达902保留线 | 已撤回；56→5字有实际AArch64证据，但整机仅+0.22%。五字新鲜读取、首次完整发布及所有检查必须保留；不能仅凭拷贝减少重做。 |
| OBSERVE传入同次START配置/根证明：checked config | BT：706→707，未达714保留线 | 已撤回；与DP不同，属于证明复用。再次尝试须提供不同的检查边界或新证据。 |
| 控制页读取只失效请求覆盖的缓存行：`read_page`、`inv_dcache_range`、control range | AK：459→458；BG：620→620；DK 构建后发现重复，未跑 GPU 测量 | 已撤回。64 条缓存行降为 1 条是操作数，不是端到端收益；不能仅凭相同代码和相同局部模型再试。 |
| 同一次 RSI 保留控制页 CPU 临时映射：read mapping cache | DB：893→898，未达 902 保留线 | 已撤回。每次仍须新鲜失效/读取；先证明映射建立与拆除的实际成本占比。 |
| 同一次检查合并多队列完成页快照：completion snapshot | DE：893→892 | 已撤回；DF 另查出候选的 32 队列位移缺陷。先证明当前负载确有多队列收益，不复用旧缺陷实现。 |
| live flush 两侧分别合并配置与运行 AS 检查：flush running check | DI：893→896，未达 902 保留线 | 已撤回。模型 MMIO 146→124 不足以证明整机提速。 |
| RMM 链接时优化：LTO | DC：893→889 | 已撤回。不能把编译器理论收益作为再次部署理由。 |
| 一次 RSI 内重复完整 FINISH：finish window | DG：893→894，未达 902 保留线 | 已撤回。减少调用次数也可能只是把等待搬进 RMM。 |
| GPU 完成序号轻量提示：sequence probe、TASK_POLL | CU：867→866；terrain、5×5 effect2d 明显退化 | 已撤回。完整查询减少，但 worker 次数与等待增加；必须解释进展/堆事件处理时机，不能仅统计 SMC 次数。 |
| FINISH 内合法未完成预检查：negative observation、skip pending STATUS | CI：728→718，5×5 effect2d 保护失败 | 已撤回；在同次 FINISH 内读取所有活动队列、重验真实根／配置后，只对合法未完成序号返回 INCOMPLETE；成功仍走完整观察。与 CU 的独立 TASK_POLL 不同，但同样未形成收益，不能仅以省去无效 STATUS 为由重做。 |
| STATUS ACK 到齐后才扫描全部 stream：status poll | CY：881→877 | 已撤回。单纯减少忙等循环中的读取没有测得收益。 |
| 同次 DRAIN 复用前一轮完整新鲜观察：drain observation | CS：848→856，未达 857 保留线 | 已撤回。不能事后降低保留线；若重做，须提出新证据或实质不同边界。 |
| 缩短首次预测等待：first wait cap | CR：848→852，未达 857 保留线 | 已撤回。更早查询增加了查询成本，等待减少不能直接算应用收益。 |
| 首次/后续短等待、主动轮询预算：wait budget | CB、CD、CE、CF | 均未保留。需要新的逐场景时序证据；避免只换时间常数。 |
| FINISH 与 heap 查询合并：finish service | CW：867→867 | 已撤回。调用次数下降没有带来可测收益。 |
| 无 OOM 时只复制 ACK：heap header | CV：867→866 | 已撤回。设备状态与根检查等主要成本仍在。 |
| 同组依赖任务合批：deferred slice、chain closure、wave poll | BU、BW、BX、BY | 已识别依赖和批次机会，但未形成保留收益；需要同时解释后继发布、整批 fence 可见性和轮询预算。 |

保留机制的例子：BS 使用受保护映射代次与租约摘要减少重复扫描；CQ 在生产者冻结的内部域重验时保留真实根和全部队列检查；CT 按竞争状态调整域保留批数；CX 将单任务明确授权与 Proxy 接纳后的有界启动合并；DA 合并同次运行 AS 与固件检查。它们都不能省略映射归属、实际完成、错误或资源释放条件。

当前分段诊断见实施记录 CZ：FINISH 域约 172.926 µs/累计退休批，其中 pending 约 83.106 µs；全局 START 重放约 15 次/批。指标含嵌套、设备等待和预热/校验，不能全部相加，也不是当前 DA 的纯 CPU profile。新的候选需要定位具体调用者及其可复用边界。

查重建议：先在本索引和实施记录中用函数名、机制名及英文别名执行 `rg`，再核对 `build/rmm-client-bo-20261030/requirements-audit.json` 的相关字段。记录候选为何不同于旧实验、依据哪份当前证据、预设保留条件和回退输入；没有新依据时先继续诊断。

DO对当前DA增加临时START调用位置诊断（完整720p893→889，仅诊断，已恢复DA）：15.107次/累计退休批、103.372µs/批。逐调用者结果见实施记录DO节与`build/rmm-client-bo-20261030/start-sites-do/profile-summary.json`；包含设备等待、预热和校验，不是纯CPU profile。该证据不自动授权省略任何重验。

DS在同一START内部划分首启/重验各五段（完整720p893→891，仅诊断，已恢复DA）。重验102.345µs/累计退休批，最大段为真实运行AS、根与固件配置检查，占重验区间时间45.87%；阶段含额外计时成本和可能的等待，不是纯CPU profile。详见实施记录DS及`start-phases-ds/profile-summary.json`。下一步优先细分运行AS/配置检查中的平台MMIO与私有核心成本，研究同一可信事务内的检查边界；不能直接缓存跨调用的根证明或省略动态故障检查，BT/DI已有撤回记录。

DV进一步细分实际运行AS检查（完整720p893→891，诊断后恢复DA）。五段计时及全部调用者范围见实施记录DV与`running-cost-dv/profile-summary.json`；不是纯CPU时间，不与DS不同运行直接相减。后续研究可信配置写入边界和重复进入检查的调用结构，不能据局部计时省略真实根、末尾动态故障或读后重验。

DX已做受控Host CPU策略对照：同DA运行代码，自动891→固定1.8GHz 888（-3/-0.34%）。正式计分区间自动组349次瞬时采样均为1.8GHz；固定组亦确认配置生效。原策略已恢复，保留测试入口，不宣称代码收益。未达到1000，后续不因启动时降频重复此实验；详见实施记录DX及`cpu-policy-dx/hardware.json`。

DY在当前DA Client路径新增首次/后续FINISH结果和延迟桶诊断（891→892，已恢复）：首次94.30% pending，843036次查询对账340588批退休。重复查询主要为GPU pending，CPU归还续传仅1次；时长含抢占/设备交互，不是可直接消除的CPU成本。下一步可研究结果/成本反馈的按队列首查预测；不把它等同于CB/CF共享等待预算或CR常数调整。见实施记录DY和`completion-shape-dy/query-shape.json`。

DZ验证按队列pending调用成本反馈：首查上限400µs、样本≤100µs，后续八次快速重查独立保留，891→881（−1.12%），已恢复DA。查询/批−20.95%，调用+worker间隔反增2.04%；与CB/CF共享预算区分，仍无端到端收益。不再仅按查询数量增加首查等待；先分辨设备进展与worker可见性。见实施记录DZ及`poll-feedback-dz/assessment.json`。

EA普通FINISH诊断漏接生产保留域，完整892分不能支持全路径分类。EB补齐后完整893分，均恢复DA，不能当提分。EB原整帧解析器因UART数字丢失拒绝；事后按原三份报告要求至少两份完整30行表逐项一致，保留守恒/单调检查、不补值；终点205/206/207行表一致，退休头仅一份完整，认证头UNAVAILABLE。RMM首次94.65% pending，保留域482653次pending中482652次成员进度未满、1次堆事件边沿，无idle阶段pending。统计含预热与内部yield，不是计分窗口逐任务因果证明。后续优先探索split-phase STATUS或完成事件调度提示，仍须新模型与完整720p；尚未实现，不能只按比例推算可省时间或再次调首查常数。见实施记录EA／EB及`finish-state-eb/assessment.json`。

EC已完成EA/EB所建议的split-phase STATUS实测，819分并已恢复DA。元数据按Group增加1024字节，原构建flags/大小上限/预留区保持；完整私有套件在字段压缩前633条PASS，压缩后实际后端、实际RSI延迟ACK28个Client场景及6个编译变体拒绝通过。验证通过不代表提分。累计COMPLETE调用减少10.55%，但查询/批增加48.13%、worker间隔增加54.07%，合计增加17.96%；5×5 effect2d730→43、terrain27→15，不能单凭总分或局部调用时间保留。当前独立退出ACK忙等方案已否定；后续需先研究ACK与执行pending的不同调度时机及快速重查到timer回退的逐场景证据，或可信设备事件唤醒。见实施记录EC及`async-status-ec/{hardware,phase-comparison}.json`，整体1000门槛未完成。

EI完成DISPATCH冷／保留域嵌套计时（934→932，诊断后恢复ED934）：保留域提交86.541µs，准备44.218／发布25.861／READY9.816µs；START重验每次6.260µs、7次／提交，占50.64%。207份完整帧、69组一致快照，不能把嵌套时间相加或与EH异轮handler相减。下一步EJ验证实际PUBLISH ACK后同调用接纳结果消除外层最后一次重复START；不跨回调／硬件写入／解锁／RSI复用，不属于BT／DI原候选重跑。详见实施记录EI及`dispatch-cost-ei/profile-summary.json`。

FH：完整720p934→655（−29.87%，对照来自FF，非紧邻），诊断已撤下。279727条有效IRQ链中，最大16.062s暂停有16.061678s发生在架构timer处理函数之前，处理函数到回调13.125µs；未建立Host共同时间线，不能认定具体根因。只读空闲Host CPU0–1两种timer PPI均启用，CPU2–3离线，不代表异常期间每REC保存值。离线实际平台／核心测试新属性拒绝原逻辑，隔离候选`TIMER_MASK & ~mask`通过131072转换与66有界退休，并精确恢复Host和保留非timer位。它仍是待实机因果检验的候选，不能由模型宣称修复或提速。当前DA／ED／原DX，纯对照934；详见实施记录FH及`irq-stages-fh/`。
