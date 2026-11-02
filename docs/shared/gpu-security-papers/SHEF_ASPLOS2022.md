# ShEF（ASPLOS 2022）：独立 FPGA TEE、证明到运行时保护及其实现边界

研读日期：2026-10-27。完整阅读16页作者预印本、105条参考文献及artifact附录A.1–A.8；固定论文明确链接的公开仓库，完成8份文件全文静态阅读和2份RTL的定向片段检查。它是异构加速器TEE比较对象，不是CCA GPU实现。未改运行代码，无新增性能测量。

## 1. 书目、版本与获取范围

题名 ShEF: Shielded Enclaves for Cloud FPGAs；作者 Mark Zhao、Mingyu Gao、Christos Kozyrakis。ASPLOS 2022，1070–1085，DOI [10.1145/3503222.3507733](https://doi.org/10.1145/3503222.3507733)。正式书目由Crossref核对，全文首页同时给出会议、作者及DOI。

实际阅读[arXiv:2103.03500v2](https://arxiv.org/abs/2103.03500v2)，2022-01-28修订，16页、1192704字节，SHA256 `2247a7b56111aceafde0eb7bba158c648157123a55f4a0b279535fad4ee4c7a1`；首页页脚确认版本。不是把2021年v1或未取得的最终ACM PDF视为逐字节相同。全文、文字、书目与来源证据在 `build/cca-gpu-followup-20261027/` 的batch40/41文件。

论文脚注1及附录明确确认[stanford-mast/ShEF](https://github.com/stanford-mast/ShEF)。固定commit `8f04bdc366da4ace9b694c38f7294cf53d2f67c7`，提交日期2021-11-24，root tree `9c9eb9766a2cfe339a7adc337292f094aed3628d`，完整递归树1659项、未截断。这个公开提交早于所读v2；未证明其每个细节等于最终实验载荷。附录另给出归档DOI `10.5281/zenodo.5735634`，本报告不声称固定GitHub提交与未下载归档逐字节等价。

本轮未运行下载代码、Vivado、AWS CLI、云实例或实验硬件，没有复现攻击和论文性能。正文/表格以提取文字核对，未逐像素重建所有性能曲线。

## 2. 问题与威胁模型

云FPGA的CSP Shell提供PCIe、DRAM、寄存器和调试接口，用户加速器只能连接Shell暴露的端口。只加密bitstream不足以保护执行期间的数据，只使用CPU TEE也不能直接消除设备侧和Shell攻击面。ShEF把可信启动/证明与可定制运行时Shield组合，不依赖CPU enclave。

敌手控制Host OS、VMM、驱动和CPU软件，甚至可以控制FPGA Shell逻辑及访问片外DRAM/HBM或总线。FPGA封装、制造商、供应链及可信开发环境受信任；Data Owner还信任其选择的IP Vendor。所谓物理攻击保护有这个封装和制造信任边界，不是任意侵入式攻击均有实验证明。

DoS、针对CSP的攻击和covert channel排除。论文不保证消除全部侧信道，应用时序非干扰仍需IP Vendor设计。移除CPU TEE降低对CPU微架构的依赖，不等于FPGA逻辑、供电、工具链及外部时序自动安全。

数据所有者与IP供应商可以是同一主体，也可以分离。多个Shield可包围多个加速模块，属于可配置空间隔离；论文没有演示恶意多Client共用同一个GPU执行引擎的调度、MMU和虚拟IRQ隔离。

## 3. 四方角色与密钥层次

| 角色或密钥 | 职责与信任范围 |
| --- | --- |
| Manufacturer / Device AES Key | 制造时向e-fuse或BBRAM写入设备AES根；可结合PUF保护，属于硬件信任起点 |
| Device Key pair | 非对称私钥嵌入用设备AES根加密的SPB固件，公钥经制造商CA发布；不是任意Host生成的设备身份 |
| Security Kernel / Attestation Key | 设备根把Kernel哈希和证明公钥绑定，Kernel仅取得派生的证明密钥，设计上不直接取得设备私钥 |
| IP Vendor / Bitstream Key | 可信编译加速器与Shield，保护含IP及Shield私钥的bitstream，并在验证证明后释放解密密钥 |
| Shield Encryption Key | 每个Shield中嵌入私钥，Data Owner用其公钥包裹自己的Data Encryption Key，形成Load Key |
| Data Encryption Key | Data Owner生成的临时对称密钥，保护本次数据输入输出；与设备长期根及bitstream密钥不同 |

同一IP bitstream可以分发给多个用户，运行时再配置不同Data Encryption Key。长期设备根、Kernel身份、加速器设计、用户数据会话并非同一项身份；合法设备证书本身不能证明当前执行的是用户期待的设计。

ShEF没有要求修改FPGA硬件，但需要制造商预置密钥、CSP允许受控启动及配置端口管理。它是现有硬件上的体系设计要求，不等于AWS已向普通租户开放完整部署。这里按论文目标假设评价，不用RK3588模拟平台能力否定当前项目目标。

## 4. 启动、证明与密钥释放

启动时BootROM使用设备AES根装载SPB固件，固件测量Security Kernel，并以设备私钥生成与Kernel绑定的证明密钥及证书。Kernel在独立处理器的片上私有内存运行；若使用软核，还应把其配置bitstream纳入测量。Kernel负责加载Shell和加速器，并按设计持续保护编程/调试入口。

Data Owner通过TLS接触可信IP Vendor。Vendor发送随机nonce和Verification Key；Kernel测量加密加速器bitstream，通过证明密钥参与密钥交换并签署会话绑定信息，返回含nonce、bitstream哈希、Kernel哈希、证明公钥及Kernel证书的签名报告。

Vendor按制造商信任根检查设备和Kernel证书、Kernel参考哈希、报告签名、nonce、预期bitstream哈希及会话密钥签名，随后才传输Bitstream Key。Kernel在片上处理明文bitstream并加载。不能把“签名有效”替代“测量值符合用户接受策略”，或把远程证明当作无需检查的ready标志。

Data Owner取得受信Shield公钥，生成数据密钥并包裹为Load Key，由不可信Host转发到Shield。理论上Host只承载密文，不能读取数据密钥和应用明文；输出也受保护后返回。图3中证明及密钥绑定的具体密码实现仍需审计，本文没有给出完整形式化协议证明。

nonce防旧证明重放，不自动证明随后每条命令/结果的新鲜度，也不完整定义reset后的密钥、IV、计数器和旧数据处理。设计还需说明Load Key属于哪个已证明实例、用户会话和执行代次；这是迁移到持续共享GPU时必须补足的组合问题，不是论文已经完成的多Client协议。

## 5. Shield 与数据释放边界

Shield是插在加速器与Shell端口间的参数化RTL：寄存器面使用AXI4-Lite，内存面使用AXI4/DMA。它保护命令、数据及外存交互；加速器侧保持相同接口，IP Vendor在设计时配置region、engine set及安全策略，而非运行中由不可信Host随意改变安全边界。

寄存器写需先解密和认证再交给加速器，读需加密并附tag后交给Shell。可选把寄存器地址也藏在同一外部地址的密文中，避免直接泄漏访问哪个寄存器。该选项隐藏部分地址元数据，不保证整个应用访问时序不可观察。

内存请求按静态region分配到engine set；每组可独立设置AES-128/256、S-box并行度、HMAC/PMAC、chunk大小、缓冲及计数器。论文默认AES-CTR加HMAC，并提供PMAC替换。MAC应绑定地址及数据；可修改region还要绑定其可信版本计数，防止搬移和旧值复用。

每chunk有12字节IV及16字节MAC，使用encrypt-then-MAC；chunk可从很小粒度到整片内存。片上缓冲缓存解密并验证后的内容，写回时重新保护。实现必须确保未验证内容不能提前作为可信结果发布；仅看到加密/哈希模块返回valid还不等于验证成功。

对于只读/一次性写入区域，作者可省去某些新鲜度计数；对于多次读写同一chunk的区域，只有MAC无法阻止合法旧密文被重放。论文给出Bonsai Merkle Tree支持，并推荐在可用片上RAM足够时直接保存所需region的计数器，以减少片外树访问。

例如每次写chunk i递增片上ctr_i，读时验证 `MAC(i, ciphertext_i, ctr_i)`。这种运行内新鲜度还依赖初始化、计数器不回卷、密钥/IV不复用以及reset后的状态策略；不能从“有计数器”推定跨重启防回滚。大chunk也有多取数据和延迟验证成本，不能把NPU式访问假设无条件套到任意GPU。

## 6. 侧信道与隔离覆盖

论文提出增大chunk减少外部可观察的细粒度数据相关访问，提供active-fence逻辑生成脚本作为功耗侧信道缓解，并通过bitstream加密隐藏微架构。上述措施不能单独证明访问模式隐藏、ORAM语义或全部功耗安全；ORAM是可集成扩展，不是本轮所有基准都已启用的机制。

作者声称Shield密码引擎时序不依赖秘密，但应用本身仍可能有数据相关时延，需应用特定措施。本文未给出整个系统的时序非干扰证明，也没有用本轮静态阅读重新验证密码引擎常数时间性。

保护外存密文与保护命令来源仍需衔接：受认证字节要绑定正确任务、序列、实例和输出。ShEF没有展开多VM虚拟IRQ的pending/ACK、通知合并、迟到事件、取消及设备复位影响域。加密输出、设备证明与某个job的可信完成属于不同证据。

## 7. 原型和性能：两套实验不能合并

完整启动和证明在本地Ultra96演示：设备AES根写入e-fuse，Security Kernel跑在专用Cortex-R5片上内存，通过专用IPI联系SPB访问密码硬件。作者报告上电到bitstream加载完成约5.1秒；它不是GPU任务或中断往返时间，也不能与其他云VM的40秒以上启动直接构成同条件提速。

AWS F1不允许作者部署该启动流程，故F1实验明确假定正确启动和证明，只测Shield。RTL使用Vivado2019.2，runtime链接XRT；这部分不把Host程序和XRT纳入论文目标TCB，不意味着本轮审计过所有驱动配置。

| 工作负载 / 配置 | 作者结果与条件 |
| --- | --- |
| Vector add | 每输入/输出向量配置多engine set，AES-128/HMAC、512B chunk；增大S-box并行度后，各向量规模slowdown低于50%，短向量仍受初始化影响 |
| Matrix multiply微基准 | 作者写AES/4x最大约1.26倍；计算/数据比高，不能推广为所有内存密集型任务相同损失 |
| SDP storage | 1MB文件、4KB认证块，两组各16KB buffer；表2按其“% Overhead”给出298、297、59、20、20，对应增加S-box、HMAC→PMAC、engine数4→8→16；20是该配置下报告值，不把298误写为吞吐下降298% |
| Convolution | 27×27×96输入、5×5 filter、27×27×256输出，分组及512B chunk；约1.20–1.35倍执行时延 |
| Digit recognition | Rosetta/MNIST，不batch，约1.85–3.15倍；批量化进一步改善是作者预期，不是新增测量 |
| Affine transformation | 512×512图像、64B访问、每地址只读，约1.41–2.22倍；未启用可修改区域同样的计数成本 |
| DNNWeaver / LeNet | 权重4KB chunk、feature map64B，约1MB feature map配16KB片上计数；HMAC为3.20–3.83倍，替换权重侧4个PMAC后AES-128/16x约2.31倍 |
| Bitcoin | 76B输入、4B nonce，主要计算由寄存器接口保护，作者报告接近零开销；不代表随机访存也接近零成本 |

摘要称0–122%性能开销，正文DNNWeaver优化后2.31倍相当于增加131%，两者范围不完全一致，本报告按各自条件列出。附录A.6还示例5073µs对3054µs，约1.661倍/+66.11%；未给出足够参数把这组数字与正文2.31倍合并，不能择一覆盖其他结果。

表3按最大Shield配置列出BRAM/LUT/REG占比：Convolution为2.9/11/5.2%，Digit为0.71/3.3/1.4%，Affine为2.1/11/5.2%，DNNWeaver为3.1/7.1/3.5%，Bitcoin为0/1.4/0.42%。这些是FPGA资源，不是可信代码LoC，也不是等同于面积、功耗及安全强度的单一指标。

SDP例的最终资源为BRAM4.3%、LUT5.0%、REG2.5%；增加AES并行度却几乎不改善初始298→297，说明HMAC瓶颈必须独立定位。论文没有据此测量本项目软件IPA→HPA授权、SMMU映射或IRQ成本；本轮没有新增GPU性能数据。

## 8. Artifact 结构和实际静态范围

附录给出AWS FPGA AMI1.8.1、Developer Kit1.4.14、Vivado/SDAccel2019.2，开发z1d.2xlarge、运行f1.2xlarge；每个编译基准约10GB、多小时。README明确启动/证明不在云FPGA直接可用，`boot/`及部分SDAccel文档/构建脚本仍在开发；其链接的 `ATTESTATION_SETUP` 在本固定完整树中未见同名文件，不把说明文字当作可直接复现验收。

取得并核验10份选定blob的长度与Git SHA1。全文阅读8份：`README.md`、`boot/host/host.py`、`boot/u96/security_kernel/{main.c,security_kernel.c,security_kernel.h}`、`hdk/src/interfaces/free_common_defines.vh`、`hdk/src/lib/primitives/shield_counter.sv`、`hdk/src/lib/shield/shield_read_decryptor.sv`。

另对 `shield_controller.sv` 和 `shield_datapath.sv` 只检查请求分派、cache tag及相关状态片段，未全文审计；`tag_match`在这些片段比较的是cache地址tag，不是密码MAC，不能据其命名宣称认证已通过。具体阅读范围和blob证据另存batch41，未审计整套1659项树、FSBL/PMU、密码库及所有Shield调用者。

## 9. 固定提交中的协议与原型差异

验证端 `verify_attestation`核对nonce、Kernel证书和报告签名，但“从可信列表验证Kernel hash”仍是TODO。`verify_kernel_certificate`做RSA公钥模幂后只比较末48字节hash，没有按所标注PKCS#1 v1.5完整验证编码结构；这里记录检查范围，不声称已构造签名伪造。

`security_kernel.h`定义688字节报告，其中624字节为nonce、证明公钥、Kernel hash和512字节Kernel证书签名，后64字节为报告签名；另加64字节共享秘密签名。所读布局没有论文图3中加密bitstream哈希。Host虽保留bitstream签名检查辅助函数，主流程中的相关调用已注释，不能把论文的加速器测量绑定称为这个路径已核验。

Host演示打印shared secret和session key，主流程使用固定示例bitstream key及固定通道key；后续Bitcoin交互使用AES-ECB，没有在这个Python数据路径中展示MAC验证。这个程序兼具验证器/演示客户端职责，不能直接称为论文不可信Host转发器的生产部署；密钥存在本地CLI的事实本身不能证明远程可信端也部署在恶意Host上。

所读R5 `main.c`及 `security_kernel.c`保留seed、证明私钥、共享秘密、会话及bitstream key调试打印。实际泄漏还取决于UART路由和部署配置，本轮没有接触板端或验证可利用性。`main.c`加载后进入空 `while(1)`；不能以这个文件证明持续监测，也不据此断言尚未阅读的PMU其他路径没有监测功能。

启动正向路径把每个加密bitstream chunk放入片上buffer，检查AES-GCM状态后才送PCAP，并在结尾清部分DMA寄存器及本地bitstream key，符合减少明文暴露的方向。但 `program_bitstream`直接使用共享区size/地址；所读函数未先验证总长度、尾块至少含IV+tag及完整边界，void返回也未向调用者表达完整成功状态。上层/硬件是否补足需要继续审计，未把局部观察升级为可利用漏洞结论。

默认defines含固定示例AES/HMAC/PMAC key、IV配置及 `NO_TAG_CHECK_FIRST`；宏的存在不等于确认所有应用都实际跳过认证。`shield_read_decryptor`返回pad与计算出的MAC，tag是否匹配、失败是否阻止明文使用还需跟踪调用者。通用 `shield_counter`也不能仅凭文件名认定为论文每chunk的新鲜度计数器。本轮未完成完整运行时认证/计数器初始化、回卷和失败传播审计。

上述是限定提交、限定路径的静态事实，不是对全部ShEF实现或论文理论设计的攻击复现。源码公开允许核查这些边界，不能把有目录、有签名函数或小型RTL模块当作所有安全属性已实现的证据。

## 10. 与当前 CCA/GPU 设计的联系

ShEF与PORTAL/CAGE/ACAI都需要把设备保护与不可信Host分离，但ShEF在可重配置FPGA内建立Shield及设备根，本项目则由RMM认证原始Client、可信ProxyRealm控制SMMU。两种路线的可信边界不同，不能直接把FPGA里可插入密码RTL的能力当作现有Arm GPU必须具备的新硬件要求。

继续保留当前假设：建图时检查对象、实际HPA授权、访问权限及生命周期，软件IPA→HPA合成受保护的直达HPA GPU Stage-1，其他设备继续硬件Stage-2；保护实际页表、根配置及关键MMIO。ShEF补充的是证明策略到运行时实例、数据释放和撤销连续性的检查视角，不替代已有内存授权。

可借鉴的第一个设计是区分“证据签名有效”和“测量/版本满足策略”。已有认证链应把实际Proxy、设备/可信固件、Client及执行代次关联；复用已有身份和epoch，避免把所有合法设备或所有历史可信Kernel都视为当前可接受。

第二个设计是保持验证到使用的同一性。对共享命令、size、对象及映射，复用私有快照和受保护执行计划；对完成，按真实native fence终态确认，再检查输出可见和错误状态，最后发布绑定cookie/epoch的记录。密码引擎valid、物理IRQ及某个“done”标志都只能作为各自阶段的事件。

第三个设计是让reset/撤销形成明确后置条件：旧队列不再获准提交、旧映射停止访问、旧完成不能作用于新任务、最后DMA已处理、资源才能重新授权。继续使用GPUVM、认证队列、native fence和持久IRQ127，不增加每任务证明或另一套通用token框架。ShEF没有给出这些多Client中断与回收保证。

## 11. 独立评价与后续研究

论文最强之处是把云FPGA不可信Shell纳入威胁模型，分离制造/供应商/数据所有者，并让安全粒度和密码吞吐适应不同region。限制是完整链只在本地平台演示、F1性能假定证明正确、若干性能范围不一致，以及公开演示路径没有逐项闭合论文的策略和运行期保证。

对项目最有价值的不是照搬FPGA加密引擎，而是把“身份/证明→授权计划→实际设备执行→验证后的结果→撤销和回收”写成可检查的连续条件。当前内存及中断隔离仍应独立论证，不能以证明成功或链路加密涵盖全部安全目标。

后续沿参考52 Ambassy、72 MeetGo、73 Border Control及36 FPGAs for Trusted Cloud Computing追踪不同信任方向；它们各需独立全文和artifact核验。已取得HECTOR-V v3的13页全文，尚未完整精读/发布，保持pending，不因与本篇并列而计完成。

记录：改动目的｜补齐独立加速器TEE、证明/密钥链与运行期数据保护研究；对照版本与分数 → 本版分数｜未测 → 未测；分差及百分比｜不适用；测试条件差异｜完整论文、8文件全文及2文件定向片段静态研究；run-id、命令、退出码与日志｜无硬件run-id，batch40/41全文、完整树和blob证据保留；保留/撤回/待验证｜保留报告，完整部署/密码及IRQ路径和论文性能未复现。未改运行代码，无新增性能测量。
