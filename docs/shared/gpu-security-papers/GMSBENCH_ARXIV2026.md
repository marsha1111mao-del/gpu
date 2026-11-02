# GMSBench：GPU内存错误评测、对象生命周期与隔离验证边界

研读日期：2026-10-28。完整阅读arXiv v1的5页、§I–VI、10条参考文献、1图2表与Listing1；逐页视觉核对。本文是评测方法研究，不是CCA/GPU TEE架构。未运行作者代码、Compute Sanitizer、攻击或硬件测试；未改运行代码，无新增性能测量。

## 1. 来源、版本与作者

Saurabh Singh、Jaewon Lee、Seonjin Na、Hyesoon Kim，分别来自Georgia Institute of Technology、Microsoft、NVIDIA和Georgia Institute of Technology。Towards Standardized Evaluation of GPU Memory Safety with GMSBench，[arXiv:2609.08871v1](https://arxiv.org/abs/2609.08871v1)，2026-09-08。[明确版本PDF](https://arxiv.org/pdf/2609.08871v1)。本轮仅确认预印本，没有独立确认正式会议/期刊版本。

PDF为259536字节，SHA256为`87bdc4f4a2f641aff710b797385e76bede3cd2e9b2677fc379abe6d9ae4239a9`；明确v1与无版本PDF字节一致。正文、逐页渲染和获取记录位于build/cca-gpu-followup-20261027/的gmsbench与124批文件。作者人数依据PDF标题页和arXiv作者栏的四人，不能将网页自动生成的“other authors”说明当作额外作者。

## 2. 背景：页表合法不代表程序对象访问合法

论文关注GPU程序中的空间越界、生命周期错误及数据竞争。GPU具有global、shared、local、constant和host-pinned等内存域，不同域的分配、可见性、寿命和线程共享方式不同；只在global memory做几个overflow用例不足以比较检测器。

其关键动机是合法地址范围内仍可发生对象级错误：从buffer A越界到仍有效的buffer B，最终地址可能仍已映射；释放后原地址分给新对象，旧指针也可能重新落入合法页。页级访问控制与指针/对象语义解决不同问题，不能用后一类检测率直接评价前一类TEE隔离。

对本项目，这支持将“已授权Client的BO页不被其他Client访问”与“同一Client程序不会越过自身对象/字段边界”分开陈述。前者是GPUVM/HPA授权目标；后者若纳入目标，可能需要编译器、指针元数据或额外对象级检查，不能仅由现有Stage-1推出。

## 3. 威胁模型和适用范围

论文没有建立恶意Host、恶意固件或互不信任Realm的完整TEE威胁模型。它构造含明确错误的CUDA程序，评价原生执行的错误表现和工具诊断；既不认证设备，也不保护中断、密钥、MMIO或跨租户页归属。

测试具有攻击者/受害对象等角色，但这些主要是同一程序内的受控内存布局，不等于真实多Client攻击成功。三代际GPU上的一致结果也不是Arm/Mali或所有驱动版本的安全结论。作者以现有工具为对象的检测结果，不自动证明错误可被稳定武器化。

## 4. 四项设计原则

Systematic Coverage按可能改变错误表现或检测行为的语义维度选取测试，不穷举所有组合。Violation Isolation让一个独立测试聚焦一种错误情形；Listing1中的一次overflow情形仍可能执行多次越界写，不能理解成只执行一条非法访存指令。

Independent Ground Truth先在原生GPU执行中观察哨兵破坏、预置值泄露、错误计算或可信运行时拒绝，再独立判断工具是否报告。没有可靠原生表现的测试保留为detection-only。Mechanism-Agnostic通过共用harness和target配置复用测试逻辑，但实现仍是CUDA，不是任意GPU API可直接运行的无关平台套件。

## 5. 分类：错误、内存域、对象上下文和具体行为

Fig1使用四层分类：error class、memory window、object context、violation type。空间错误包括线性越界读写和定点越界；对象关系包括相邻/非相邻、跨frame、跨字段以及跨内存域来源。类型覆盖广度不等于覆盖每个可能组合。

global空间测试包括host端cudaMalloc、kernel内malloc和cudaHostAlloc的pinned内存。cudaMallocManaged没有空间类测试，作者理由是本次观察与cudaMalloc相同；这不是所有平台上两类内存安全语义完全等价的证明。constant只测试读，不能把该空缺当漏测设备写指令。

local覆盖同frame、跨frame、静态/动态stack对象及超出整个local window；shared覆盖static/dynamic组合、字段内越界和整个window之外。static→static才包含可可靠安排的相邻/非相邻变体。cross-space使用定点跳转，省略会先经过源window边界的线性溢出。

跨域测试的目标是检查pointer provenance，而不是只检查最终地址。对TEE而言，指针来自某种CUDA地址空间与实际HPA属于哪个Client也不同；即使程序指针有合法来源，映射授权仍须核验真实页。

## 6. 生命周期：地址复用、别名和失效对象

UAF区分immediate与delayed：后者在同地址被新对象复用后再访问，专门检验检测器是否跟踪分配实例。aliased UAF先复制指针别名，通过其中一个释放，再由另一个访问，检验寿命失效是否传播到所有别名。

managed只包含delayed UAF；作者观察其释放后解除映射，直接悬空读会fault而非泄露预置值。cudaMalloc的相应旧区域在该实验条件下仍可读。这是作者平台下的行为，不能变成本项目必须保留释放后映射的要求。

temporal还包括invalid free、double free、uninitialized read，以及local的use-after-scope/use-after-return及立即/延迟变体。shared无显式对象free，未配置UAF/IF/DF；shared未初始化读没有建立可靠ground truth，不纳入相同测试范围。

作者将初始化错误放入temporal分类，是评测taxonomy选择，不代表初始化与分配寿命在所有形式化定义中完全相同。对项目应分别验证新资源清理、旧授权失效和访问者停止。

## 7. 数据竞争和ground truth的限制

五个race用例对共享counter执行无同步、非原子的read-modify-write，以lost update作为错误表现；global覆盖同warp、同block和跨block，shared覆盖同warp与同block。论文报告三平台结果一致，但数据竞争本身依赖调度，不能从一次矩阵一致推出任意执行都必现。

文中称这些用例形成deterministic observable effect，但未给足以独立证明全部调度必然丢更新的源码与重复次数。应将其视为作者在给定实验中的稳定观察，不能把未丢更新当作程序不存在race的充分条件。

## 8. Listing1和评测harness

示例使用gms_cuda_malloc_adjacent取得32B攻击buffer与16B哨兵buffer，初始化哨兵后，kernel依据两个地址的差值循环写到目标前4B，再复制哨兵回host检查。采用实测地址安排角色，比根据声明顺序猜测布局更可靠。

但helper源码尚未取得，不能独立证明它总能生成两个独立分配、所需相邻关系或在所有失败路径正确退出。若port后把两个对象改成同一大分配的切片，测试就会从跨allocation变成allocation内部越界，必须记录这种语义变化。

每个CUDA文件定义gms_test()；共用harness提供入口、布局及检查，target配置描述编译、执行和诊断匹配。所需布局/分配无法建立时报告SETUP_FAIL，不计detector miss。这一做法可迁移到项目负例：未构造出合法基线、任务未真正执行和隔离成功必须分开。

仅崩溃或非零退出不证明预期错误被工具检测，可能是次生损坏或运行时失败。反过来，程序无异常也不证明非法写没有发生。detection-only的诊断依赖工具自身，证据强度不同于原生观察加独立哨兵验证。

## 9. 实验平台与结果

平台是RTX A5000（Ampere SM86）与A100（Ampere SM80）的x86主机，以及GH200（Grace AArch64 + Hopper SM90）。编译使用-arch=native。论文没有给足CUDA、driver、Compute Sanitizer的精确版本、每用例重复次数、全部原始诊断及置信区间，因此跨版本复现条件不完整。

| 项目 | 原文Table I | 正确解释 |
| --- | --- | --- |
| native manifestation | 134/149，约90% | 观察到预期错误表现的比例，不是工具检测率或系统不安全概率 |
| memcheck | 18/144，12.5% | 对空间/生命周期测试集合；不含5个race用例，不是所有GPU漏洞的全局检出率 |
| apicheck | 10/11，约91% | memcheck加--report-api-errors=explicit，对适用invalid/double-free子集，不是独立完备安全工具 |
| initcheck | 4/4，100% | 四个适用未初始化读用例，不能推为全类型100% |
| racecheck | 2/5，40% | 两个shared race报告、三个global race未报告；测试范围和工具目标需分别说明 |

表中三平台使用同一结果列，作者报告所有verdict一致，不是把三平台合计447项当149个独立错误类型。按表逐行复算：空间108、temporal36、race5，共149；native分别104、25、5，共134；未观察到native表现15项，包括4个beyond-window、1个host-allocated temporal、2个device-allocated temporal及8个local temporal。

memcheck的空间命中14、temporal命中4，共18。不能只对134个native显现项重算18/134，因为部分memcheck命中来自detection-only测试。四工具的边际命中数也不能直接相加当唯一错误覆盖，没有逐测试联合矩阵和重复计数消除依据。

## 10. 观察到的检测边界

作者观察memcheck可发现经过freed gap的线性overflow，但可漏掉落入另一live allocation的相邻越界、跳过检查区域的定点越界，以及字段内和cross-space错误。device-heap是例外，线性overflow的不同布局都被检测；不能概括为所有CUDA分配都具有同样行为。

immediate UAF可被报告，delayed和aliased UAF可漏检；失效地址被新对象占据后，单凭当前地址合法性无法识别旧对象身份。apicheck漏掉device侧free的double free，说明host API诊断不能覆盖所有kernel内分配行为。

这些是论文给定版本/配置/测试的结果。“tripwire”解释主要沿用相关工作，本文没有完整逆向或证明Compute Sanitizer所有内部机制。未给padding、不同优化级别和所有工具选项的消融，不将18/144称为厂商工具在任何配置下的固定上限。

## 11. 与相关研究的关系

Table II比较CuSafe的33测试、cuCatch的56测试及GMSBench的149测试，并以圆形填充表示各taxonomy维度覆盖程度。它比较测试集，不是对CuSafe/cuCatch/GPUArmor实际检测效果的同条件实验；本轮只测Compute Sanitizer。

CuSafe仍缺全文，本文对其测试数的描述只作为GMSBench作者引用，不替代CuSafe独立精读。GPUArmor、cuCatch的具体防护和性能仍引用各自报告；LAK/region bounds、Let-Me-In等参考工作可继续沿正式出处补查，不能把被引用就当作已经审计实现。

## 12. Artifact实际可获得性

论文脚注给出[GitHub仓库](https://github.com/gthparch/GMSBench)。此次GitHub仓库API、main commit入口和raw README均404；限定仓库检索用于寻找替代入口，结果按获取记录保留。404只说明本次无法访问，不能断言作者从未公开或永久闭源，也没有固定到可核验commit。

因此未取得149个CUDA文件、harness、target配置或原始结果，不能核实测试数与代码树一致性、布局helper、编译器防优化、诊断正则及误报率，也未执行任何作者程序。本轮完整研读的是论文设计和结果，不是实现安全审计或实验复现；后续若取得代码，应补固定版本和静态核查。

另取得arXiv出版源包，SHA256为`e49ea17de39d43a5194434b73d5b1fe08beb55f94b4628e888581e1900db4f0e`。12个tar成员含两个目录，逐成员记录哈希；完整静态阅读methodology.tex和evaluation.tex，并用自写脚本提取Table I的32行复算总数。该包是TeX/图表/参考文献，不是CUDA实现，未运行其构建或其他程序；其余文件取得不等于全部静态审计。

## 13. 对本项目的迁移：三类边界分别验收

继续接受RMM认证Client、ProxyRealm统一管SMMU、GPU映射期软件IPA→HPA授权并合成受保护硬件Stage-1、其他设备受检Stage-2，以及页表/root/MMIO/固件保护的假设。本文不能否定这些前提，也没有要求模拟平台具备NVIDIA硬件。

第一类是Client间隔离：同一Client内对象越界不必超出该Client授权页；只有跨入另一Client或未授权HPA才直接触及既定隔离目标。需要目标Client的私有哨兵、可信GPUVM/fault及实际backing证据，不能只在提交端看到一个错误码。

第二类是对象实例生命周期：让旧指针/句柄在地址或ID被新对象复用后再次访问，配合导入别名和reset重连，检查private plan持有对象、backing generation、cookie/epoch是否一致。CPU消息代际正确不证明旧GPU DMA已停，仍须可信停机与撤销/失效条件。

第三类是应用内错误检测：若研究目标扩展到同Client子对象和kernel内存安全，应明确增加对象元数据或编译器检查的TCB、性能和兼容代价。不能在只有GPUVM页隔离时宣称GMSBench全部错误都应被捕获，也不建议无条件把调试sanitizer塞入可信Proxy主路径。

## 14. 与可信完成和中断的联系

建议用两Client相同本地cookie、越界fault与正常完成并发、cancel后迟到事件及资源复用等负例检查任务归属。Client被唤醒、出现GPU IRQ和native fence进入终态分别记录；预期fault须返回正确任务错误，不能因为“测试进程退出”就当隔离通过。

受害者哨兵不变仅是数据完整性观察，还需证明探针实际执行、确实尝试目标访问、失败原因符合预期，并确认另一Client仍能正确执行。没有泄露迹象不独立证明机密性；非法读需建立独立的预置秘密与不可见性条件，同时避免将测试自身的合法导出当泄露。

Devlore/TEEtime保护事件路径，CAEC保护授权共享，PORTAL/CAGE/ACAI及PhantomMap支撑服务与实际页边界；GMSBench补充负例分类和判据，不替代任何一层。notification、任务终态、应用正确、输出发布、DMA静默与安全复用继续分别论证。

## 15. 综合评价与后续

贡献是更系统的GPU错误taxonomy、独立ground truth与检测结果分离，以及跨平台的149测试评估。局限是仅预印本、实现本轮不可访问、工具版本和重复实验信息不足、synthetic用例无代表性权重、未评误报/性能/真实多租户攻击。它适合作为项目验证方法支撑，不能充当新CCA GPU隔离架构。

下一步优先补取得artifact并核对delayed/alias UAF与布局helper，再把语义迁移为当前Mali/Proxy协议负例。CUDA源码不能直接视作Panthor/OpenGL测试；任何port都需说明改变了什么分配与生命周期条件。本轮只形成设计与验证建议，没有执行这些负例。

统一记录：完整5页/1图2表1Listing/10引用/来源与算术/Notion全文回读｜glmark未测→未测｜分差及百分比不适用｜未改运行代码，无新增性能测量｜无作者代码、攻击、模拟或硬件run-id｜保留支撑研究，整体继续。
