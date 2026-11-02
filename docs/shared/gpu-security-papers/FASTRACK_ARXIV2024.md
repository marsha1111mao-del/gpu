# Fastrack：GPU TEE 的可信 I/O 优化、分块认证与推测提交边界

研读日期：2026-10-28。完整阅读12页arXiv v1、§1–8、29条参考文献，无附录，12图2表；视觉核对第2–11页，覆盖全部图表。结合完整论文TeX源包定向检查设计/安全/实验段落，并查NIST SP800-38D有关GCM并行性、认证解密和IV唯一性的条款。本文直接研究GPU TEE安全传输，非Arm CCA设备分配架构。未改运行代码，无新增性能测量。

## 1. 来源及版本

Fastrack: Fast IO for Secure ML using GPU TEEs。Yongqin Wang、Rachit Rajat、Jonghyun Lee、Tingting Tang、Murali Annavaram，USC；前两位共同贡献。[arXiv:2410.15240v1](https://arxiv.org/abs/2410.15240v1)，2024-10-20；[PDF](https://arxiv.org/pdf/2410.15240v1)、[HTML](https://arxiv.org/html/2410.15240v1)。本次摘要入口只列v1；限定Crossref标题前三项没有匹配正式出版版本，按预印本研读。

PDF1379048字节、SHA256 `3cc92d17f793feb675479e76dfb68a1b3994c96d5c7510d1d746a4526e2a0d73`；HTML166110字节、SHA256 `dd767998ed1b7d0438b68def6d3977f016bdc6d18b4ea463543ab8bbd90f7b64`。完整论文源包980031字节、SHA256 `814c4792a41dbc0e26027e2875d3d4086e9c9003f086c53e1c171ca298147aeb`，包含TeX/图PDF/排版与图片资源，不等于CUDA安全实现。

请求、PDF/文本/HTML、源包成员清单、设计/实验TeX静态核查、10页渲染和算术记录保存在`build/cca-gpu-followup-20261027/`的fastrack相关文件。正文未提供已确认实现artifact，限定GitHub“Fastrack GPU TEE”零结果；不据此声称无公开实现。没有匹配代码审计、模型运行、攻击复现或完整产品安全验证。

## 2. 问题：可信端点之间重复处理数据

基线为远端用户→CPU TEE→GPU TEE。CPU TEE内有driver；用户数据先由CPU解密/认证，再用CPU–GPU会话重新加密，经不可信bounce buffer和PCIe进入GPU，GPU解密/认证后计算。作者认为重复加密、逐链认证和串行传输使I/O密集模型受损。

三项优化分别是用户与GPU直接建立密钥关系、每sample分为多个带tag的链、传输/AES预计算/认证/工作负载流水。它们优化已存在GPU TEE的通信，不解决GPUVM隔离、原始Client身份、页所有权或可信中断投递；不能把H100的密文通路直接套作Arm共享内存的必要要求。

## 3. 威胁模型与信任边界

攻击者控制Host软件、DMA bounce buffer、网络及CPU–GPU通路，并具有外部总线探测能力。CPU/GPU package、CVM内driver及执行代码可信，GPU封装内存可信，侧信道排除。这里的CPU TEE不是不可信Host；论文说“entire system software”时必须同时保留CVM内部可信例外。

论文在这些前提下主张与NVIDIA CC相同机密性和完整性。密码原语正确只是条件之一，端点认证、nonce生命周期、完整消息组合和认证前使用的副作用还需证明。本文不以硬件是否支持某项修改否定系统方案，而检查优化是否保持这些不变量。

## 4. Direct communication的收益与条件

GPU与用户直接协商共享密钥，CPU只转交密文/tag，可省去CPU解密再加密。论文用Diffie–Hellman说明建链，并称用户原本控制CPU TEE，因而本来就知道GPU通道密钥。这个结论依赖部署确实是同一租户控制的CVM；在多Client共享ProxyRealm中，用户并不自然有权取得所有Client共用的driver/device会话密钥。

DH本身不认证对端，需要把协商公钥、nonce、GPU/服务证明、策略和目标会话绑定，防止中间人/错误设备。每Client、方向、用途和epoch的派生隔离也应明确。减少中间重加密不等于允许绕过ProxyRealm的原始身份、对象及实际页授权。

移除CPU预处理的需求由GPU完成解码/crop/normalization，减少JPEG展开后的PCIe字节量。作者举112KiB对588KiB约5倍的例子；收益组合了密码路径、工作放置和数据格式，不能全归因单项加密优化。GPU内图像解析代码也进入可信输入处理面，恶意密文不能在认证前直接交给未防御输入的复杂parser。

## 5. Multi-chaining并不是“GCM数学上不能并行”

作者将每sample切成通常8–16块，每块附tag和1字节AAD序号，可并行验证；声明认证kernel加速5–15倍，实验使用16链并称最高16倍。链内Horner递推确有依赖，但GHASH可表示为有限域多项式，利用H的幂并行计算/合并；标准单tag GCM本身可并行。NIST SP800-38D §3也明确其函数可并行，不能把某CUDA实现的瓶颈当原语不可并行的定理。

分块独立tag可以是合理记录层方案，但它改变消息格式及认证组合，不能只以“每块仍是AES-GCM”证明整体与一条完整消息相同。应比较优化单tag GHASH与多record方案的性能及完整协议成本，区分实现基线与密码学必然下界。

## 6. Nonce、完整性和跨消息拼接

Fig8每链均标Nonce，但没有给出独立IV派生规则；正文也未完整定义sample/batch/session到nonce和counter的映射。不能据图中同名标签就认定代码真的复用nonce；也不能在缺实现时断言已安全。若同一key/IV被多个GCM调用重复使用，仅AAD链序号不同不修复IV重复问题。

1字节序号足以编码16个位置，却不自动绑定原始Client、模型/任务、sample/batch ID、总块数、总长度、chunk长度、方向和epoch。若仅认证位置，攻击者可能重放其他合法消息同位置的块；是否成功取决于未说明的key/nonce和接收状态，本文不宣称无条件成立的攻击。

需要接收端强制预期序号、完整块集合、唯一消费和总长度，拒绝重复/缺失/截断/跨会话拼接，并在整个任务认证成功后提交。GCM检测修改与防止合法旧消息重放不同；所有单块tag正确不自动保证消息最新、完整或目标正确。

标准tag计算也需澄清。论文§3.2/Fig4把最终值与“Nonce”直接XOR来说明tag；NIST §7.1实际对包含AAD/密文/长度的GHASH结果使用由J0生成的GCTR掩码，128位tag相当于与AES_K(J0)异或。若图为简写需说明；不能把字面简图当安全实现，也不能据排版源就认定作者CUDA实现错用了公开nonce。

## 7. AES预计算较易保持边界

AES-CTR的密钥流块只依赖key和counter，可以在密文到达前预计算，随后XOR。其正确性不要求提前信任密文，适合隐藏传输时延。但必须保证每个key/counter唯一、buffer所有权和长度明确、预计算状态不跨epoch错误重用，缓存密钥流属于敏感状态并应安全清理。

“可以先解密”与“可把未认证明文交给任意代码”是不同结论。NIST认证解密允许内部先算P再比tag，但对外输出为P或FAIL。流水优化可以维持这一语义，前提是认证通过前的计算及所有可观察副作用被隔离或可完全撤销。

## 8. Eager evaluation的核心风险是提交语义

§1.2提出认证完成前推测运行，训练暂存gradients，推理可向用户标记tentative，失败后丢弃或通知旧结果损坏；§5.3则描述本batch计算与下batch传输/上batch认证重叠。仅说仍使用AES-GCM，不足以证明这种使用顺序与先认证后执行相同安全。

训练不仅有gradient：BatchNorm running stats、optimizer momentum、RNG、loss scaler、step counter、数据采样状态和持久日志都可能改变。若未认证batch污染这些状态，丢弃梯度无法恢复；若下一batch依赖未提交状态，还需取消或回滚所有依赖。论文未给完整事务/恢复机制，不能将“buffer gradients”当全部状态可撤销的证明。

推理中，返回tentative logits、token、日志或网络结果已经产生发布行为；事后通知不能撤回泄漏或调用方已执行的动作。自回归KV cache、会话状态和工具调用也要等待正确授权。即使所有侧信道排除，显式输出和持久写入仍是模型内问题。

此外AES-CTR对密文修改会导致可控明文差分，虽然正确tag最终会失败，但认证前parser/kernel仍可能接触攻击者影响的数据；复杂解码和数据依赖索引需独立限制。这里提出待证明条件，不声称已经攻破作者实现。更稳妥的默认是认证后使用；若要推测，须定义受限私有计算区与完整提交/中止协议，连同尾批认证drain、失败风暴、取消/reset一起证明。

## 9. 实验究竟测了什么

平台H100、Xeon Gold6548Y+、512GB DRAM；ResNet50/ImageNet batch64、3层mean GraphSAGE/ogbn-products batch1024及TTNN/MovieLens1M batch1024。作者以OpenSSL CPU路径＋自写CUDA解密/认证重建协议baseline，再实现Fastrack；另测真实H100 CC on/off端到端作为对比。

因此Table1/2及baseline分解不是厂商内部实现剖析，最高84.6%也以自实现baseline为分母，不能改称“修改厂商生产安全通路后较原版快84.6%”。真实CC on/off是另一对照。论文未说明完整driver/firmware/TDX配置、证明链、Fastrack密码层在CC on时如何接入/避免重复加密，不能据custom CUDA kernel吞吐自动认定完整产品安全链已部署。

缺固定源码、执行命令、重复次数/误差、失败路径计时、认证终态与drain计入方式，以及预处理是否各路径相同等信息。§6.7明确没有多GPU/LLM训练评估；预期收益不能当测量。认证kernel仅用5%资源也不保证任意负载下无带宽/调度争用或完全重叠。

## 10. 算术与图文差异

按Table2同一non-TEE时间为分母重算如下；全部是印刷数字算术，不是重新运行。

| 模型 | 训练时间增加 | 推理时间增加 |
| --- | --- | --- |
| ResNet50 | 10.18% | 54.13% |
| GraphSAGE | 352.19% | 803.88% |
| TTNN | 138.99% | 529.94% |

摘要“推理最高903.9% slower”、导言TTNN“629.9%”将倍率百分比与增量混用；Table2对应时间比903.88%和629.94%，减100个百分点才是时间增加。摘要训练455%及导言TTNN238.9%也无法由所印Table2复现，不能擅自补造不同配置解释。

GraphSAGE训练通信32.6／39.16约83.25%，与§6.2的83.24%近似一致，但§4写91.93%不一致。§6.2一句称GraphSAGE“GPU authentication per batch”比ResNet快，而同段数字13.4ms对1.13ms相反；可能想谈单sample，但正文未说明，不能替作者改写。

Fig12的84.6%时间下降对应6.49倍速度比；72.5%对应3.64倍、81.7%对应5.46倍、55.7%对应2.26倍。作者称GraphSAGE最终仍比non-CC慢38.7%/24.2%，TTNN慢6.9%/2.7%；这是相对另一基线，不能与前述减少百分比直接相减。图中ResNet baseline柱与Table2约17.37/39.49ms也未严格一致，应要求原始数值及测量配置，不用目测柱高补造精确结果。

Fig12视觉及图例明确第7柱CC on、第8柱CC off，§6.6中把最后柱或第7柱称CC off的文字有相互冲突，按图辨认并保留差异。16链相对单链按作者公式增加15个16B tag＋16B AAD＝256B，112KiB样本约0.223%；“约0.5%”依赖实际sample/IV/封装尺寸，不是恒定开销。

## 11. 对项目两大部分的启发

在直通/共享实现与性能部分，可以研究受保护长期buffer、减少重复复制/转换、按真实所有权同步和流水重叠。共享内存已经处在可信授权域时，不应为模仿PCIe系统额外重复加密；是否需要密文通路由威胁模型决定。所有收益须对同安全条件和相同输入/预处理测量，本轮没有项目性能结果。

在任务隔离部分，先保留RMM认证原始Client与ProxyRealm实际HPA/归属/权限/生命周期授权，软件IPA→HPA合成受保护GPU Stage-1；其他设备保留硬件Stage-2。认证或校验通过只能说明被检查的对象，不能越过GPUVM、private plan/snapshot或设备访问授权。

项目已有native fence、cookie/epoch和IRQ127，应围绕它们明确提交权限：真实GPU完成、输入/协议校验通过、输出发布和资源回收分别满足条件；不另起一套并行完成标志。本文的延迟认证不能被误用为允许Host IRQ绕过可信终态，或在未认证元数据下先建立可访问其他Client的映射。

优先负例包括跨Client同序号块、旧epoch消息、重复/缺失尾块、认证失败但GPU已运行、失败后下一任务复用、尾批无下一batch、reset后的迟到完成和输出先于授权可见。通过现有状态机补齐失败语义比新增“tentative完成”快捷分支更适合目前项目；这里只提出设计和验证方向，没有修改实现或执行测试。

## 12. 支撑标准及统一记录

[NIST SP800-38D（2007）](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf)本次取得完整39页PDF，271960字节、SHA256 `d99f3921ccebca049e7522426553aba071dae14ec3d5b6041e8c111a6cb57bba`；定向阅读§3、§5.2–5.3、§7.1–7.2及§8的相关唯一性条款，非全标准独立精读，不额外计篇数。正文提取有CFF字体解析警告，相关条款文字可读，公式结合算法步骤而非乱码顺序解读。

改动目的：补充GPU TEE可信I/O和推测执行提交边界｜glmark未测→未测｜绝对/百分比变化不适用｜未改运行代码，无新增性能测量｜完整12页/10页视觉/论文源包静态核查、GCM标准定向阅读、算术与Notion回读另列证据，无硬件/构建/模型/攻击run-id或运行PASS｜保留研究；作者运行实现、完整协议证明与项目负例验证待完成。
