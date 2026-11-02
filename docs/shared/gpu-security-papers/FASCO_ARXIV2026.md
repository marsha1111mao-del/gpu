# Fasco：CCA 可信服务 Realm、异常转发与共享缓冲的安全边界

研读日期：2026-10-28。完整阅读12页arXiv v1、§1–8及18条参考文献，无已排版附录；结合官方HTML与完整论文源包main.tex核对。8图、1表，视觉核对PDF第2/3/5/6/7/8/9/10/11页。本文是CCA机密容器设计，不是GPU保护架构；纳入原因是System Realm／Container Realm与本项目ProxyRealm／Client的服务隔离和异常通信直接相关。未改运行代码，无新增性能测量。

## 1. 文献与证据

Shielded but Lightweight: Building Practical Confidential Containers with ARM CCA。Liantao Song、Yiming Zhang、Fengwei Zhang、Yan Ding、Bin Zhou、Jie Yu、Yusong Tan。[arXiv:2605.26018v1](https://arxiv.org/abs/2605.26018v1)，2026-05-25；[PDF](https://arxiv.org/pdf/2605.26018v1)、[HTML](https://arxiv.org/html/2605.26018v1)。本次入口只列v1。论文仍有Conference／Woodstock 2018和DOI占位，不能据模板认定正式录用；Crossref限定标题前三项没有匹配版本。

PDF1255511字节、SHA256 `a68411fa1f4f5818b14fbcd6bc2a4b1f6f6f283f115c46661779d0d658d77ef5`；HTML175501字节、SHA256 `e1641fb0cb01887b7c6e12f2b1cf8480bd8813e094dddb0e779bc348a92504d3`。完整gzip源包791394字节、SHA256 `45491e457504d4eabf3157f0d6be25871c9c20d0e13dfb6181310452419a97e9`，包含main.tex、fasco.bib及8个图PDF；它是论文排版源，不是RMM/System Realm运行实现。

证据保存在`build/cca-gpu-followup-20261027/`，包括fasco89.pdf、fasco90.txt/.html、fasco-source90.tar.gz、fasco-source-main.tex及batch90渲染/请求记录。限定GitHub查询“Fasco CCA”无结果，不等于不存在实现。main.tex被注释的Open Science段落出现[匿名artifact地址](https://anonymous.4open.science/r/fasco-DD27/)，正文未发布这一段；访问重定向至站点API后返回HTTP401，响应及hash已保留。没有取得匹配固定运行源码、原始实验数据或命令，没有独立执行。

## 2. 研究问题与架构

传统机密容器常把容器装入microVM，带来guest kernel、启动和管理成本。Fasco改为每容器一个Container Realm，仅承载应用和轻量shim；独立System Realm提供装载、资源管理及服务中介，RMM负责底层生命周期、页表和受控切换。复杂文件/网络功能继续委托不可信Normal World Trim OS。

这与PORTAL的可信服务Realm路线相近，但保护粒度和接口不同。对本项目有用的是把复杂共享服务放在受保护ProxyRealm，将RMM维持在身份、授权及状态切换层；CPU容器不含完整guest kernel的结果，不能直接推导GPU driver可被删除或GPU DMA已获保护。

## 3. 威胁模型及TCB计数

攻击者控制Host OS、hypervisor及域外特权软件，可操纵通信并部署恶意同宿容器；同时作者假设受保护租户的workload/image自身非恶意。应区分诚实受保护应用和恶意其他租户，不把这两句混成“所有容器都可信”。物理CPU攻击及微架构侧信道排除在外，Host仍可拒绝调度、丢请求或扣留资源。

§3.2称System Realm是“richer, yet still trustworthy”的runtime，§4.1明确可信变更为RMM＋System Realm，并称Realm OS agents不可信。Table1却只列RMM＋TF-A为Fasco trusted components，遗漏System Realm/shim/密码依赖的解释，不能据表得出服务runtime不进TCB。正文的Normal World Trim OS和“Realm OS agents”命名也应明确各自位置及权限。

论文没有提供TCB LoC、依赖闭包或可核验的远程证明/key release流程。可信服务隔离可减少单个组件可直接访问的页，但如果它仍决定装载、参数和结果语义，其正确性仍影响端到端安全，不能仅按异常级别计算TCB。

## 4. 页表树独立与实际页独占

设计目标是每容器独立S1/S2，私有代码、堆栈和数据互不别名，显式共享页例外；初始化后System Realm撤销容器私有页访问。GPT的Realm PAS保护与每Realm RTT决定的私有页归属是不同层次，内存加密也不自动证明对象归属、页复用清理或所有完整性属性。

§4.2的具体路径递归clone源RTT：table entry分配新节点，non-table entry直接复制；随后逐页撤销源System Realm里选定容器IPA范围。新页表节点独立，不自动说明叶子指向的HPA互不重叠。若clone包含其他私有叶项，还需过滤并检查所有实际页归属；只撤销源树的选定范围也不能单独证明目标树只映射本容器。

正文紧接着又声明新树只映射容器所需页。缺少实现、完整伪代码和元数据不变量，无法判定实际程序是否已完成筛选，不能将上述描述差距宣布为复现漏洞。应把待补证据写清：叶项策略、RD/REC/引用状态、别名、失败回滚、并发切换和授权生效时刻。

S1从host-side执行上下文复制并设置private TTBR0_EL1，也需验证实际叶页和权限，不能只验证根地址。System Realm先装载再撤销的过渡阶段需要可信原子提交；销毁后应说明CPU/DMA静默、翻译失效、清零和安全归还，正文的生命周期目标尚不是完整回收协议。

## 5. 异常转发的机制说明仍不充分

§3.4概述异常被RMM截获、保存Container上下文、转给System Realm，后者执行eret“进入RMM”再恢复原PC。§4.2具体描述读取ESR_EL1/FAR_EL1，识别SVC/data abort，重入时恢复VBAR_EL1、private TTBR0_EL1及保存PC。

eret本身不意味着向更高异常级陷入；需要给出返回目标EL、异常路由、专用向量以及RSI/退出协议，才能连接这两种描述。EL1 syndrome读取与R-EL2截获也需明确分别属于哪一处理阶段。这里是机制欠明确，不因实验硬件或模拟方式否定该架构可实现。

SVC、可重试data abort、异步IRQ和signal的返回语义不同，恢复“原PC”不能无条件等同于正确重启；还需处理系统调用重启、嵌套事件、并发vCPU、取消及上下文frame的拥有者。论文没有完整GIC/INTID、claim/ack或物理IRQ委托协议。

## 6. 上下文完整性不等于中断真实性

即使PC/SP和寄存器被可信保存，仍须证明触发事件来自授权来源、属于当前Client和当前代任务、目标允许、次序合法。否则Host注入/重放的通知仍可能触发不应发生的状态转换。论文没有给出专门的伪造IRQ、迟到事件、跨Client投递或reset重放实验。

本项目应复用既有RMM认证队列、private plan/snapshot、native fence、cookie/epoch和持久IRQ127。RMM保留pending/ack/armed状态，IRQ只提示检查可信队列；任务完成由对应真实native fence及可信终态决定。不能从Fasco的上下文恢复再派生一套独立“中断即完成”凭据。

必须继续区分：IRQ到达、job成功、输出可见、计算正确、DMA停止和内存可安全复用。这些条件彼此不能代替。可信System Realm服务中断的结构，可以帮助设计转发路径，但没有直接证明GPU job完成与页回收的安全性。

## 7. 共享缓冲与Iago边界

注册接口记录VA、解析PA和size，支持一般共享区与signal stack。显式注册有助于缩小暴露范围，却还需要检查原始Client、每页实际归属/映射、跨页不连续、长度溢出、权限、pin、撤销和generation。单个首地址PA不足以证明整个range合法，注册时合法也不保证使用时仍合法。

syscall指针转向approved buffer需要覆盖嵌套指针、iovec/recvmsg、ioctl结构、句柄/FD namespace和状态机。返回长度检查能阻止部分越界，但不能独自阻止返回值引导控制流、错误对象身份或文件偏移语义等Iago攻击。请求应先复制到可信私有快照再解析，使用时绑定受保护对象和生命周期；返回及失败回滚也需检查。

共享signal frame若可由不可信侧写入，还需验证恢复PC/SP/status、写窗口和frame generation；只认可缓冲地址并不自动认证frame内容。全文未给足该协议，不宣称已证明可利用漏洞。

## 8. Shielded I/O及缓存一致性

作者提出透明文件加密、TLS/安全channel及console保护，但没有给出完整密钥供应、AEAD关联数据、nonce/重放、截断、持久文件rollback或服务端身份协议。数据位于注册缓冲不等于加密正确或消息新鲜，应分别标明明文私有区、可信共享区和Host可见密文区的读写主体。

缓存部分指出装载后的D-cache clean／代码I-cache invalidate、共享数据可见以及S2修改后TLBI。这些是必要问题，但“when necessary”的barrier描述尚不能替代具体发布/获取、DSB/ISB、多核shootdown和GPU域可见性协议。CPU一致共享区不必盲目每次全flush；CPU屏障也不代替真实DMA同步，invalidate之前还须处理脏数据和所有权。

## 9. 实验平台与证据边界

作者用Ubuntu22.04上的QEMU验证CCA功能，并在RK3588/OpenCCA上评价性能；接受模拟平台作为实现与测试载体。待补信息是RMM/TF-A/内核固定版本、模拟机制配置、核绑定/频率、次数/方差、workload命令和输入规模，而不是据芯片能力否定设计。

Non-CC RunC/Docker与受保护方案的安全目标不同；Kata、CoCo/Coco在图文中也有混用，应明确运行配置及是否具有相同加密/保护路径。论文没有安全攻击实测或完整OCI/Kubernetes覆盖率，若干CPU benchmark不能验证跨Client内存和中断隔离。

## 10. 性能数字及图文复核

UnixBench正文Fasco419.2、Coco173.6，分数比约2.415、增加141.47%；Fig7图例是RunC/Fasco/Kata。它是综合score，不能转述成所有操作延迟降低2.4倍。Table1的Fasco约12%与其他论文5.7%/10%/40%跨平台数字，也不是统一对照实验或可追溯的聚合开销。

Fig8b的LMBench纵轴印Time(s)，正文称syscall latency，缺原始计时定义，不能自行改成微秒。Hackbench正文单位×100ms与Fig8c的×10²ms相符；100k时Fasco2.62、RunC2.59，时间增加1.16%，800k时21.80对19.48，增加11.91%，不宜用一个总体数字掩盖负载差异。

Nginx 4KB正文Fasco792QPS、3.09MB/s，792×4096／2²⁰约3.094，更接近MiB/s；RunC约820QPS与3.35MB/s也需明确近似值、payload/wire和单位，不能据此直接判定数据错误。Fig8e含MySQL各操作平均时延，但缺正文实验设置和解释，报告保留这一面板而不补造结论。

生命周期start：Fasco1.406s、RunC1.006s、Kata6.727s，Fasco相对Kata减少79.10%、相对RunC增加39.76%。pause为0.152对Kata0.186s，正文称“matches”不精确；unpause均0.139s。kill为Fasco0.162、Docker0.124、Kata0.469s，Fasco比Docker慢30.65%，不能沿用正文“surpasses Docker”。remove为0.189对Kata0.399s，下降52.63%。Fig8a有断轴，柱长不能直接比例读取。

Fig8f横轴是Concurrency(threads)，正文却按容器数解释；Fasco约0.23–0.25s仅表明该测量下稳定，不能证明公平性、抢占或资源隔离。RContainer在8处尖峰的硬件/模拟归因是作者推测，缺控制实验。本文算术复核不属于重新运行作者benchmark，更不是本项目glmark测量。

## 11. 对本项目的设计建议

第一，明确ProxyRealm是可信服务TCB及其受限权限，RMM保存原始Client身份与授权状态。继续接受软件IPA→HPA授权并合成受保护GPU Stage-1的设计；CPU RTT独立不替代GPU实际HPA、对象归属、权限及生命周期校验，其他设备硬件Stage-2仍需同样的可信准入。

第二，把共享缓冲注册、私有快照、对象引用、映射有效期和返回结果绑定成一个可审计事务。跨Client句柄、注册后重映射/撤销、旧generation、并发修改、嵌套指针和失败回滚是应验证的负例。对现有机制补证据，不预先新增无使用者的框架。

第三，在既有IRQ127/pending/ack/armed与native fence上说明控制权：谁认定事件、谁改变任务终态、谁发布输出、谁允许回收。覆盖假唤醒、重放、乱序、合并、丢失、取消/reset和迟到完成；通知到达不授予权限，Host拒绝服务与可信路径被伪造分别评价。

第四，性能按可信入队、Proxy等待、GPU执行、真实完成、Client可见和回收分阶段，联合报告吞吐、尾延迟及各Client公平性。Fasco轻量服务结构可启发减少切换，但不能直接据它的CPU数据推导本项目GPU提分。

## 12. 统一记录

改动目的：扩展CCA可信服务及异常/共享缓冲文献｜对照glmark未测→本版未测｜绝对/百分比变化不适用｜纯文献、论文排版源静态核查，未改运行代码，无新增性能测量｜无硬件、构建、模型、攻击run-id或运行PASS；请求、全文、图像与Notion回读单列证据｜保留研究；匹配实现、完整异常协议及项目负例验证待完成。作者主张、来源观察、逻辑分析和项目建议分别表述，不把待补证据当作已复现漏洞。
