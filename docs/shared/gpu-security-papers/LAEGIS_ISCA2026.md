# LÆGIS：可信IV状态、UVM预加密与异步生命周期的安全边界

## 1. 论文身份与阅读证据

论文：LÆGIS: Pinpointing and Addressing Performance Overheads of GPU-based Confidential Computing；Yang Yang、Adwait Jog；ISCA2026，Raleigh，2026年6月；DOI：10.1109/ISCA66397.2026.00046，465–481页。

[正式DOI](https://doi.org/10.1109/ISCA66397.2026.00046)；[作者全文](https://adwaitjog.github.io/docs/pdf/yang_laegis_isca26.pdf)；[作者主页](https://adwaitjog.github.io/)；[artifact](https://github.com/insight-cal-uva/laegis-isca26-artifact)。PDF为1187922 bytes、17页，SHA256：3918a617a33bc0576ec7e33f6208f296a405dd03236b9be6c46ba7e6ce453021；正式题名、两作者、日期与17页长度一致。README称camera-ready，PDF页脚仍写will appear；IEEE PDF入口502，未做出版PDF字节比对。

已完整阅读17页、§I–X及145条参考文献；视觉核对第1–13页，覆盖全部16图、两表、Listing1、IV构造和安全段。全文为`laegis121-full.txt`，渲染清单为`laegis-render122.json`；渲染17页不等于声称参考文献四页也全部做了视觉阅读。证据根目录为`build/cca-gpu-followup-20261027`。

公开artifact固定commit为6af67279ad0ec5a0507b3586ecfead42a1206077，完整1975项树未截断、head/tree一致；取得8个选定blob并核Git blob SHA1及SHA256。静态范围为README、驱动HOWTO、libspdm AEAD两个文件、gmmu实现/头文件及gpu-sim头文件的相关段落，不是全仓库或完整驱动调用链审计。

重要证据限制：root README明确写用于Figure12/13/14/16的LÆGIS专用实现尚未公开。公开模拟器是基础设施，不能把其下载成功等同于取得IV Bank、预加密调度和全部性能结果的可复现实现。没有运行作者代码、模拟器、模型、工作负载、攻击、构建或硬件测试。

本文与ISPASS2025 Dissecting GPU CC直接相关：前作拆分launch/queue/transfer/UVM开销，本篇进一步研究kernel-space UVM加密与显式IV状态。它是GPU CC性能/密码状态设计研究，不是新的Arm CCA GPU隔离架构，也不是多Client可信中断协议。

## 2. 接受的假设与项目位置

系统采用CPU CVM/TD加CC GPU，信任CPU/GPU片上组件、TD私有内存保护、固件及正确驱动；Host和PCIe不可信。HBM被当作可信、难以物理篡改的片上封装内存，侧信道排除；本文不是在完整物理攻击模型下证明HBM永不出错。

作者专门区分GPUHammer的GDDR6攻击与服务器HBM，并引用HBM2读扰动研究；安全边界应写成对选定HBM平台的假设。按项目约定，不因实验硬件尚不具备同样结构否定研究，而分析保护元数据与异步操作需满足的抽象条件。

本项目仍以RMM认证原始Client、可信ProxyRealm控制SMMU、映射阶段校验实际HPA归属/权限/生命周期、运行期受保护直接HPA Stage-1为前提。这里最可迁移的是“允许提前做工作，但由可信状态判断是否仍可提交”，无需照搬HBM结构或引入不必要的加密层。

HBM可信只解决元数据保存位置，不能自动解决哪个Client有权使用某ID、哪个版本有效、允许哪个迁移目标以及何时回收。MAC有效、nonce未重复、对象归属正确、数据最新和任务真实完成，是不同安全命题。

## 3. UVM处理链与实际瓶颈

GPU PTE无效产生replayable fault，由GMMU写入fault buffer并通过中断触发CPU驱动批处理：fetch→preprocess→service/encrypt→迁移/decrypt→replay。这个fault服务中断用于恢复执行，不是任务完成中断，更不能直接用于发布应用输出。

基础页4KB，VABlock为2MB；树式预取TBNp以64KB叶为粒度，一个VABlock有32叶。Pt越小越积极，默认51%、积极1%；真实测量比较Bf256/1024，而模拟TableII列Bt128，不能默认为同一参数/同一批大小已验证等价。

GEMM预取从1%改91%时，加密占比44%降16%，但batch149→1310约8.79倍、fault数超过11倍，端到端反而可能变差。CNN有相反取舍：batch只增8.3%、加密数据少96.8%，说明不能只按加密占比或fault数单指标选策略。

与前作容易混淆的关键区别：UVM在kernel-space通过CSL/LCA相关路径做4KB同步加密；非UVM bulk copy使用user-space OpenSSL。公开AEAD文件在USE_LKCA分支调用crypto_aead_encrypt/decrypt并等待结果，支持存在kernel crypto实现，但未独立还原专有CSL的全部运行时调用链。

因此升级用户态OpenSSL不直接加速nvidia_uvm.ko。Figure15测得LCA在2MB约2.5GB/s、UVM有效约1.3GB/s，而新OpenSSL可将用户态峰值3.03提高到8.61GB/s；这三个层次不能当同一个函数的版本变化。

GEMM每batch加密吞吐约1.28/1.24GB/s，原文把1.28对应4KB约2.98µs。独立单位核对：4096B/1.28十进制GB/s为3.20µs，按GiB/s为2.9802µs；保留单位标注差异，不把它改写成已测的精确纳秒值。

驱动thread平均true idle约87%，并不表示整CPU空闲87%或所有核可免费挪用。true idle是等待下一batch；false idle是当前驱动忙于准备fault但未执行AES，需额外辅助线程才有机会重叠加密，CPU资源与上下文切换成本不能省略。

## 4. 从隐式同步到显式IV Bank

基线让CPU/GPU随传输顺序共同推进IV，减小持久元数据成本，但加密受运行顺序约束。LÆGIS把每VABlock的IV状态保存到可信GPU HBM和CPU可信内存，让提前加密顺序不必等于传输顺序。

GPU IV Bank Entry为128bit，核心含ID19bit、RV77bit，另有V/D/O/R四标志、CTR9bit及剩余空间；ID复用PDE0的19个空闲位，MC将IBE取到CE，16项IV cache缓存状态。CPU端可在TDX私有内存或可信HBM保存镜像。

独立容量核对：2^19×16B=8MiB，可表示2^19个2MiB对象即1TiB；对模拟8GiB HBM，预留占约0.09766%。16项cache是256B，对1MiB L2约0.02441%，与原文0.02%量级一致，不等于完整控制逻辑/互连面积和功耗也已被测出。

§V-A写每stack预留8MB，§V-D又写增加stack无需复制IV Bank、改变mapping即可；应区分单stack设计点与多stack扩展策略，不能同时套“每stack线性增长”和“全局固定8MB”。多GPU共享/复制状态只作扩展讨论，没有完整多GPU一致性实验。

论文AES输入公式为RV77∥ID19∥blkidx17∥0^15，共128bit；2MiB/16B确有2^17个AES block。公式描述OTP构造，但不独立给出全部GCM初始counter、AAD、tag和分片协议细节，不能从位数相加正确就推导完整认证加密实现安全。

ID把不同VABlock的IV空间分开，前提是同一key/direction的所有并发对象和设备共享正确的命名空间。PDE0携带ID还需受保护、与实际映射对象绑定；编号不重复不等于Client身份已认证。

## 5. 预加密与提交过程

初始化为对象分配PFN和ID，在CPU IV Bank中建立ID/RV状态，候选集合Sa保存尚未预加密页。处理当前FA时，从fault buffer取未来FB候选；优先加密这些候选，再在有余量时顺序加密其他CPU驻留页。

FB真正被服务时，已准备的密文可跳过关键路径加密，未准备页照常加密。迁移时发送密文与MAC/ID，GPU据ID获取状态、验证/解密并存HBM；论文walkthrough将verify、首次GPU初始化和读取IBE的先后叙述较简略，实际协议须定义可信初始化与原子提交顺序。

F版本利用false idle，IR随机选择CPU页利用true idle，IN选择fault-buffer候选利用true idle；IFN结合二者并在空闲剩余时顺序预加密。加p前缀采用积极预取；IR不是攻击实验，随机候选表现较低只是策略收益差异。

顺序解耦不等于版本解耦。预加密后CPU可能修改源页，或对象被撤销/换归属；提交必须重新确认内容版本和当前授权，失效候选应丢弃或重新加密。正文没有给出类似PipeLLM写保护/完整dirty-generation机制的细节，公开专用代码也缺失，不能声称该竞态已被审计排除。

对项目private plan或地址翻译缓存，同样应把结构匹配、对象仍存活、内容/页集合未变化和当前Client授权分别验证；提前工作是候选结果，只有通过当前可信检查才能变成设备可执行状态。

## 6. Nonce、部分迁移与新鲜性审查

4KB子页共享同VABlock的ID/RV，以offset区分；正文说512个base page都迁移后才推进RV，CTR9bit统计部分迁移；整VABlock eviction也推进RV并刷新页。安全段又概括RV每次access递增，两处粒度不同，应由完整状态机消除歧义。

条件反例只用于提出约束：若同key/direction下某4KB页在其余511页迁移前被CPU改写并再次加密，而ID/RV/blkidx均未变，则同一AES输入被重复使用。实现可能通过页独占、版本推进或禁止这种顺序避免；本轮未取得专用实现、未复现漏洞，不能将此称为已攻破LÆGIS。

CTR只给计数不能自动识别“同一页重复到达”和“不同页各到达一次”，9bit最大511而完整计数为512，需要carry、额外flag或等价编码。论文未充分说明终态与去重记录；这是实现需明确的不变量，不是仅凭位宽就确认溢出漏洞。

随机RV初始化的平均剩余空间约2^76，只是期望，不保证每次初始化都有同样长寿命。O/R标志提到overflow、key rotation和重加密，但没有完整断电/reset、失败回滚、旧密文失效及ID重分配协议；恢复与释放必须拒绝旧版本，不能只把valid清零。

按q=2^19次96bit随机初始化，简单birthday近似约1.73×10^-18，论文所列q²·2^-95.26界约5.79×10^-18；仅这个bank大小的一轮初始化不能直接证明碰撞风险很高。更关键的是同key下长期生成量、重复ID、RV推进及会话边界，显式ID的优点应按这些条件论证。

论文将109bit MAC与19bit ID打包成128bit。[NIST SP800-38D原文](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf) §5.2.1.2明确允许128/120/112/104/96及受限64/32bit，不允许其他t；本轮仅定向阅读PDF第17页/印刷第9页，不计标准全文精读。109不在其中，公开既有wrapper也按byte接受12–16B，不能直接提供109bit tag接口。这不自动意味着方案不安全，但须定义自定截断格式、验证预算和与GCM实现的兼容规则，不能仅写NIST-standard IV length就覆盖MAC设计。

AEAD tag验证成功只证明所给key/nonce/AAD下消息一致；若旧密文仍使用可接受的RV/offset，它仍可能通过验证。必须另定义已接收集合或单调版本、防跨对象替换、方向/目标绑定，以及验证成功前禁止数据进入可见执行状态的规则。

对本项目，等价关注点为Client/BO/页集合/权限/epoch与操作目的共同绑定，重复或迟到记录不得重新完成新任务。nonce唯一性、映射生命周期和native fence的task cookie各有作用，不能用其中一个代替其他全部保护。

## 7. 与PipeLLM的比较边界

LÆGIS指出PipeLLM预测未来IV可能变旧，需在TD私有内存暂存候选、提交前检查，并用NOP推进或丢弃候选。本库PipeLLM精读也记录了源页写保护和匹配检查；因此不能把LÆGIS的动机概括成“已证明PipeLLM存在可利用漏洞”。

LÆGIS减少按序IV和NOP修补需求，但“无需NOP”只移除一种显式事件，不等于没有时序泄露。作者承认PCIe活跃时长会变化且侧信道排除；预加密候选、fault节奏与发布行为仍可能被观察。

论文性能/代码声明明确没有发现新安全漏洞，也未给协议的机器检查证明或恶意Host replay测试。应把作者“无新风险”的设计主张、上述待补条件和实际公开实现范围并列，不把性能图当作安全证明。

## 8. 真实测量与模拟设计分开

真实平台Xeon6530 Gold2.1GHz、TDX1.5、补丁Linux6.2/QEMU7.2、CUDA12.4、H100、驱动550.163.01，用于测量fault处理、idle和AES。不能照搬前作550.127.05的所有模式细节；本篇未在正文明确写出完整CC-devtools/生产CC-on等价测量，本轮未自行补完该设置。

LÆGIS收益来自GPGPU-Sim4.2加UVMSmart模型、基于真实测量标定：80SM、1MiB L2、单8GiB HBM2 stack、4KB base/2MB big page、双向各64GB/s PCIe、IV cache16项20cycle、线程切换2µs。它不是在现成H100上部署了完整硬件IV Bank后测得的加速。

Figure12实际列16个工作负载，包括CNN和独立FlashAttention kernel；不能把正文“16应用，另外CNN/FlashAttention”的措辞机械累加成18，也不能把独立FlashAttention等同于端到端LLM服务或多租户调度实验。

Ideal只隐藏密码开销，仍保留fault/batch等系统成本；不是nonCC裸机，更不是本项目native。故接近Ideal不证明保护开销全部消除，或端到端应用已达到无隔离基线性能。

## 9. 结果与独立算术核对

全部默认归一化到Baseline：IFN平均2.22、最高3.13倍；pIFN平均2.74、最高5.05倍。pBaseline本身约1.22倍，用舍入聚合数复算pIFN/pBaseline约2.2459，不能把2.74说成相对同积极预取基线的纯增量。

默认Ideal2.36、pIdeal4.60；用舍入数算IFN距Ideal约5.93%、pIFN距pIdeal约40.43%，正文5.8%/40.34%可能来自未舍入值。该百分比是速度指标差，不是“相对nonCC只剩5.8%安全开销”；2.22倍速度对应归一化时间减少约54.95%，不是减少122%。

F/IN/IR平均约1.51/2.17/1.38；积极版本约1.37/2.10/1.62。pF平均低于F，不能把“pF应用未相对Baseline退化”扩大为积极预取相对F每case都有收益。论文还明确3DCONV/NW/SSSP积极Baseline可退化2–5%。

Figure13显示CPU加密移出关键路径后GPU解密和fault准备成本显现；fault准备优化也会缩短预加密可用窗口，两项收益不可直接相加。Figure14 full IFN/pIFN active比例约53.2%/88.3%，CPU更忙是资源换延迟的代价，不等于能量或公平性一定更好。

多线程和硬件AES敏感性同样是模拟假设：MT-Baseline默认平均退化35%，积极版本约1.08倍；X-Baseline1.19、X-pBaseline1.58。不能把这些模型结果当作已修改真实TDX引擎或内核UVM线程后测得的性能。

X-IFN2.13略低于软件IFN2.22，正文解释短窗口、不可抢占加密与管理成本；X-pIFN3.57、最高6.82。舍入数2.13/1.19约1.79、3.57/1.58约2.26，对应作者1.78/2.26；与未加硬件的Baseline比较是另一组分母。

X变体假定可重配置TME-MK AES-XTS datapath执行AES-GCM，40cycle fill、16B/cycle。共享AES primitive不自动实现GCM认证、请求接口与安全仲裁；这是设计假设及需计入的状态/调度成本，不能由“同Galois Field”一句就视为现实平台已支持。本报告不因硬件差异否定方案。

## 10. 公开代码实际能支持什么

README明确不公开专用路径，是最强的artifact范围证据。选定gmmu段落可见按crypto保护范围/吞吐估算ready cycle的模型，不是AES-GCM密码协议、IV Bank生命周期或消息重放验证器；未在该小范围找到某机制不能断言整个仓库都没有其他实现。

libspdm AEAD两文件支持kernel-space gcm(aes)与同步等待的接口解释；HOWTO指导改驱动、打开debug/builtin tests、设预取/批量参数、重启。本轮只读这些操作说明，没有执行；不能把README中的复现步骤当作本项目已做硬件验证。

由于专用代码和原始结果重建链缺失，独立复算限于位数、容量、单位和正文舍入比例；没有声称完整重画Figure12–16、验证全部候选命中率或复现安全反例。未来源码更新须固定新commit并重新界定证据范围。

## 11. 项目可采用的设计改进

第一部分可借鉴以真实并发和等待窗口安排有界提前工作：预校验、页解析、候选计划准备等可与执行重叠，最终提交时再核当前授权与对象版本；先测CPU资源、关键路径和每Client公平性，再判断哪些操作适合缓存或流水化。

第二部分建议统一定义“候选→已授权→已提交→真实终态→数据可见→已发布→静默后回收”的状态及允许转换。每一步绑定原始Client、对象和epoch，reset/撤销对候选与在途操作都生效，不能只清理当前GPU页表而遗漏后台准备结果。

fault服务与任务完成应为不同事件类型；来自GPU/Host的中断只触发读取可信记录。页迁移完成、replay恢复、native fence完成、输出可发布和DMA静默各自需要依据；对方不能通过构造fault或迟到IRQ使新epoch对象提前完成。

若未来引入加密共享缓冲，应显式规范AAD/目标范围/方向/版本、新鲜性、原子接纳和候选失效，避免“合法密文但对应旧页/旧Client”。不引入加密时也保留等价的所有权与生命周期绑定，不能把无需密码处理误当无需控制面授权。

适合后续验证的场景包括部分页反复迁移、预处理期间改写/撤销、ID/slot复用、重复通知、reset后旧回调及多Client资源竞争；当前是从论文推导的验证需求，不是已执行或已通过的测试。

## 12. 后续线索与记录

可沿引用继续研究SecNDP、Battering RAM、HBM2读扰动和UVM多任务调度，先核版本与是否已有独立报告再计数；这些线索不在本篇完成数中。LÆGIS与既有PipeLLM/Dissecting GPU CC应按不同机制和证据交叉引用，不重复当同一平台多次独立安全验证。

统一记录：改动目的为GPU UVM显式状态与异步授权边界精读｜glmark未测→未测｜分差/百分比不适用｜未改运行代码，无新增性能测量｜无作者代码/模拟/攻击/工作负载/构建/硬件run-id或测试退出码｜保留研究；源码/算术/发布回读证据单独核验，整体调研继续。
