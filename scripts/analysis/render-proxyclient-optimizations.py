import json
import os
import re
from pathlib import Path
import runpy


renderer = runpy.run_path('scripts/analysis/render-clientproxy-guide.py')
Diagram = renderer['Diagram']
BLUE = renderer['BLUE']
GREEN = renderer['GREEN']
ORANGE = renderer['ORANGE']
PURPLE = renderer['PURPLE']
MUTED = renderer['MUTED']


def overview():
    diagram = Diagram('01  优化发生在哪一层？',
                      '蓝：Mesa原有接口；橙：ClientProxy内部协议；绿：原生驱动；紫：真实GPU与完成。', 1090)
    diagram.box(60, 155, 390, 150, '应用 / Mesa UMD',
                ['VM_CREATE、BO_CREATE、VM_BIND', 'GROUP_CREATE、GROUP_SUBMIT'], BLUE)
    diagram.box(525, 155, 390, 150, 'Client前端',
                ['缓存固定shape；按需物化对象', '快照、epoch与本地完成检查'], ORANGE)
    diagram.box(990, 155, 390, 150, 'Proxy / 原生Panthor',
                ['会话校验；真实GPUVM与job', '依赖、调度与真实fence'], GREEN)
    diagram.arrow([(450, 230), (525, 230)])
    diagram.arrow([(915, 230), (990, 230)])
    diagram.box(60, 400, 620, 145, '控制面：减少等待与重复处理',
                ['PLAN_REGISTER / PLAN_EXEC、TRANSFER_CAPTURE', '短轮询、退役捎带、驻留唤醒、SGI15'], ORANGE)
    diagram.box(760, 400, 620, 145, '数据面：共享页与缓存所有权',
                ['CPU与GPU访问同一份BO；分段分配', 'tiler交接、精确同步、旧目标后备回收'], GREEN)
    diagram.arrow([(720, 305), (720, 350), (370, 350), (370, 400)])
    diagram.arrow([(1185, 305), (1185, 400)])
    diagram.box(60, 650, 390, 155, '真实GPU执行',
                ['GPU读取命令 / 输入，写结果', '更新真实队列seqno并触发IRQ'], PURPLE)
    diagram.box(525, 650, 390, 155, 'Proxy完成路径',
                ['减少worker交接；有界提前观察', '真实fence → 精确cookie发布'], GREEN)
    diagram.box(990, 650, 390, 155, 'Client完成路径',
                ['匹配slot / cookie / epoch', 'signal本地fence → poll / wait'], BLUE)
    diagram.arrow([(450, 725), (525, 725)])
    diagram.arrow([(915, 725), (990, 725)])
    diagram.box(60, 870, 1320, 95, '两个不能混淆的返回',
                ['PLAN_EXEC回复＝原生驱动已接纳；cookie成功证明＝对应真实fence已完成。'], PURPLE)
    diagram.footer(['共享数据不随每次提交复制；控制请求仍私有复制和校验。',
                    'RMM授权、对象引用、真实执行与错误处理不因优化而省略。'])
    return diagram


def ownership():
    diagram = Diagram('02  缓存与内存：先明确所有权，再减少重复工作',
                      '同一物理页共享不等于CPU/GPU天然一致；缓存维护必须对应实际交接。', 1080)
    diagram.box(60, 165, 390, 180, '旧tiler同步方式',
                ['CPU初始化一次', '每次提交和完成都扫描 / 同步', '长期由GPU使用却反复交接'], ORANGE)
    diagram.box(525, 165, 855, 180, 'GPU-only heap交接',
                ['CPU初始化 → 全chunk clean / invalidate → 撤销vmap',
                 'GPU长期持有；普通BO / heap context仍按需同步',
                 '历史309 → 632；BO同步605.877 → 8.075 μs'], GREEN)
    diagram.arrow([(450, 250), (525, 250)])
    diagram.box(60, 440, 620, 160, 'managed提交：限定来源与同步点',
                ['授权、pinned、WC payload；root预留仍保留',
                 'ring / sync record / 固件输入在写入点维护',
                 '省去逐提交全BO扫描；普通VM保留原路径'], GREEN)
    diagram.box(760, 440, 620, 160, '分段BO：解决物理碎片',
                ['同一owner池内多个extent → 连续GPU VA',
                 'mmap按逻辑偏移遍历分段',
                 '提高可分配性；没有独立提分证据'], BLUE)
    diagram.box(60, 700, 620, 160, '共享前：两批物理后备',
                ['Proxy源页A + Client挂接目标旧页B',
                 '映射改到A后，B仍可能留在guest_memfd',
                 '旧384 MiB目标＝98304页'], ORANGE)
    diagram.box(760, 700, 620, 160, '共享后：同一批A，回收旧B',
                ['KVM成功切换属性 / 撤销旧映射后打洞',
                 '源页A仍保留98304页，旧B变为0页',
                 '分项峰值合计903.26 → 519.33 MiB'], GREEN)
    diagram.arrow([(680, 780), (760, 780)])
    diagram.footer(['回收旧后备不是回收仍供GPU使用的源池；启动阶段仍先取得目标区。',
                    '内存为历史ResNet50口径，非GLMark当前整机RAM；各分项峰值不保证同时发生。'])
    return diagram


def rpc():
    diagram = Diagram('03  一次同步RPC：先短轮询，再可靠地睡眠',
                      '轮询由已经等待的Client调用线程执行；Proxy接收侧忙等是另一种方案，曾被撤回。', 1080)
    diagram.box(60, 155, 620, 140, '① 发布请求',
                ['先登记seq / type对应的私有waiter',
                 '发布描述符 → RSI NOTIFY唤醒Proxy'], BLUE)
    diagram.box(760, 155, 620, 140, '② Proxy处理并发布回复',
                ['私有复制、owner / 参数校验、真实接纳',
                 '先写回复，再根据NO_NOTIFY提示决定通知'], GREEN)
    diagram.arrow([(680, 225), (760, 225)])
    diagram.box(60, 390, 620, 170, '③ Client短时检查',
                ['poll_lock只允许一个提示owner',
                 '处理所有可见回复，按seq / type分派',
                 '完成、need_resched或预算到期即退出'], ORANGE)
    diagram.box(760, 390, 620, 170, '④ 恢复通知并重新检查',
                ['清NO_NOTIFY → 完整屏障 → 排空回复',
                 '仍未完成的每个调用者独立ARM',
                 'ARM之后acquire重查，避免丢唤醒'], ORANGE)
    diagram.arrow([(1060, 295), (1060, 335), (370, 335), (370, 390)])
    diagram.arrow([(680, 475), (760, 475)])
    diagram.box(60, 665, 620, 145, '已收到匹配回复',
                ['返回本次RPC结果；不必睡眠',
                 'PLAN_EXEC成功仍不代表GPU已执行完成'], BLUE)
    diagram.box(760, 665, 620, 145, '仍未收到回复',
                ['wait_for_completion_timeout睡眠',
                 'IRQ → RX work → 匹配waiter → 唤醒'], PURPLE)
    diagram.arrow([(1060, 560), (1060, 610), (370, 610), (370, 665)])
    diagram.arrow([(1060, 560), (1060, 665)])
    diagram.box(60, 875, 1320, 80, '收益与代价',
                ['历史632 → 808；减少睡眠/通知往返，但忙轮询占CPU，未证明节能。'], GREEN)
    diagram.footer(['当前性能profile的回复轮询预算1000 μs；历史提分实验用100 μs，不能混用参数归因。',
                    'RPC回复轮询与sync_file worker的周期重试不是同一机制。'])
    return diagram


def snapshot():
    diagram = Diagram('04  快照生命周期与TRANSFER_CAPTURE',
                      '快照固定一次捕获时的真实fence；不是BO数据副本，也不是“GPU已完成”的猜测。', 1100)
    diagram.box(60, 150, 390, 190, 'Mesa原有调用',
                ['GROUP_SUBMIT', 'SYNCOBJ_TRANSFER', 'HANDLE_TO_FD → poll / wait', '最后关闭sync_file'], BLUE)
    diagram.box(525, 150, 390, 190, 'ClientProxy内部操作',
                ['PLAN_EXEC：结构缓存执行', 'TRANSFER_CAPTURE：搬移并捕获', '本地构造sync_file', '最后引用 → 有界退役队列'], ORANGE)
    diagram.box(990, 150, 390, 190, 'Proxy / 原生对象',
                ['接纳真实job，安装输出chain', '同一fence写入目标与私有快照', '返回handle + slot + cookie', '真实引用保护底层fence'], GREEN)
    diagram.arrow([(450, 245), (525, 245)])
    diagram.arrow([(915, 245), (990, 245)])
    diagram.box(60, 450, 620, 160, 'A  退役捎带',
                ['下次捕获时附带旧快照handle批次',
                 'Proxy全批验证后退役；满队 / close排空',
                 '历史1023 → 1159 / 1163；明显收益'], GREEN)
    diagram.box(760, 450, 620, 160, 'B  预捕获后导出本地命中',
                ['TRANSFER时已保存不可变快照',
                 'epoch未变、无并发修改时免导出RPC',
                 '历史1158 → 1156；只证明少RPC'], ORANGE)
    diagram.box(60, 715, 620, 160, '后续RESET / IMPORT / 新提交',
                ['公开syncobj可以改变',
                 '已导出的旧sync_file仍持有旧fence',
                 '源对象销毁不等于快照立即失效'], BLUE)
    diagram.box(760, 715, 620, 160, '回退与安全约束',
                ['不确定版本 → 重新捕获真实fence',
                 'slot不足 / 未完成 / 错误 → 原生WAIT',
                 '超时不能盲目重放TRANSFER或GPU提交'], PURPLE)
    diagram.footer(['A与B解决不同往返；不能把A的大幅提分算给B。',
                    '图示为已协商binary TRANSFER快路径；timeline目标保留原有语义。'])
    return diagram


def notification():
    diagram = Diagram('05  可信通知：依次减少发送端与目标端Host往返',
                      '物理SGI是唤醒提示；授权由RMM端点归属、可信pending和私有LR决定。', 1030)
    rows = [
        (165, '原路径', ['Client → RMM', '退出发送端Host', 'KVM kick目标', '目标RMM → Proxy'], ORANGE),
        (370, '驻留请求唤醒', ['Client → RMM', 'Root发SGI0', '目标Host → RMM', 'IRQ127 → Proxy'], BLUE),
        (575, '目标端直接返回', ['Client → RMM', 'Root发SGI15', '目标RMM校验TAKE', '私有LR → Proxy'], GREEN),
    ]
    for top, title, stages, color in rows:
        diagram.text(60, top - 22, title, 25, color, '700')
        for index, stage in enumerate(stages):
            left = 60 + index * 345
            diagram.box(left, top, 285, 110, stage, [], color)
            if index < 3:
                diagram.arrow([(left + 285, top + 55), (left + 345, top + 55)])
    diagram.box(60, 785, 1320, 110, '条件不满足就回退',
                ['接收方主动启用、REC0驻留另一CPU、归属/MPIDR/pending匹配；否则SGI0或Host路径。',
                 '两项独立结果：1158 → 1182（+2.07%）；1208 → 1237（+2.40%）。'], PURPLE)
    diagram.footer(['SGI15、Root服务与Host辅助模块是RK/OpenCCA集成，不是标准CCA通用接口。',
                    '这里只优化已驻留目标；Host仍决定未驻留vCPU何时获得运行机会。'])
    return diagram


def fence():
    diagram = Diagram('06  GPU完成：更早看到真实结果，减少通知交接',
                      '原生接纳 → GPU执行 → 真实fence → cookie → Client本地fence，语义始终分层。', 1280)
    diagram.box(60, 150, 620, 150, '提交端：复用原DRM调度器',
                ['原生创建job / 依赖 / 输出fence',
                 '释放drm_exec后trylock执行一次原调度',
                 '锁忙或依赖未就绪仍走原worker'], GREEN)
    diagram.box(760, 150, 620, 150, 'GPU执行与真实计数',
                ['ring / INSERT / doorbell → GPU执行',
                 'WAIT(all)完成后更新sync record',
                 '产生原物理IRQ与Guest JOB IRQ'], PURPLE)
    diagram.arrow([(680, 225), (760, 225)])
    diagram.box(60, 415, 620, 175, '普通路径仍保留',
                ['原JOB mask → IRQ线程ACK / drain / unmask',
                 '线程尾部trylock处理真实固件完成',
                 '锁忙 / reset → 原worker；进程上下文回收'], BLUE)
    diagram.box(760, 415, 620, 175, '硬IRQ有界提前观察',
                ['仅managed VM，短锁trylock、强引用',
                 'invalidate / dma_rmb，检查seqno与status',
                 '最多8个真实job fence；不提前unmask'], GREEN)
    diagram.arrow([(1060, 300), (1060, 415)])
    diagram.arrow([(1060, 350), (370, 350), (370, 415)])
    diagram.box(60, 700, 620, 165, '注册阶段：预先选择回调目标',
                ['chain_walk：旧前缀仍pending → 观察整链',
                 '旧前缀确已完成 → 观察当前真实fence',
                 '两种引用分别持有，销毁等待回调结束'], ORANGE)
    diagram.box(760, 700, 620, 165, '成功cookie发布与确认',
                ['成功真实回调 → release写cookie',
                 'Client acquire检查slot中精确cookie',
                 '匹配对象/point/epoch后完成本地fence'], BLUE)
    diagram.arrow([(370, 590), (370, 640), (1060, 640), (1060, 700)])
    diagram.arrow([(1060, 590), (1060, 700)])
    diagram.arrow([(680, 780), (760, 780)], dashed=True)
    diagram.box(60, 965, 1320, 130, '三个不同优化层次',
                ['提交＋IRQ线程尾部：1237 → 1267，+2.43%；前缀完成时观察leaf：1267 → 1311，+3.47%。',
                 '硬IRQ有界提前观察：1311 → 1405，+7.17%；GPU仍实际执行，IRQ数量没有因此下降。'], GREEN)
    diagram.footer(['cookie本身不会唤醒睡眠线程：worker未命中仍查WAIT并睡眠重试，完整完成订阅尚未实现。',
                    '错误不发布成功cookie；chain历史child错误的传播不能等同leaf错误检查。'])
    return diagram


def scores():
    diagram = Diagram('07  近期已保留的完整720p优化链',
                      '同单Client、128 MiB、CPU 1.8GHz / GPU594MHz；阶段计时关闭。', 1000)
    entries = [
        ('起始组合', 1158, '对照', MUTED),
        ('驻留请求唤醒', 1182, '+24 / +2.07%', BLUE),
        ('全路径所有权复用组合', 1208, '+26 / +2.20%', GREEN),
        ('SGI15目标端直接返回', 1237, '+29 / +2.40%', ORANGE),
        ('提交与IRQ尾部交接组合', 1267, '+30 / +2.43%', PURPLE),
        ('已完成前缀观察当前fence', 1311, '+44 / +3.47%', BLUE),
        ('硬IRQ有界提前观察完成', 1405, '+94 / +7.17%', GREEN),
    ]
    for index, (label, value, gain, color) in enumerate(entries):
        top = 163 + index * 93
        diagram.text(60, top + 28, label, 23)
        diagram.rect(455, top, value * 0.40, 42, color, radius=4)
        diagram.text(455 + value * 0.40 + 14, top + 29, str(value), 25, color, '700')
        diagram.text(1130, top + 28, gain, 22, color)
    diagram.box(60, 842, 1320, 64, '累计1158 → 1405：+247 / +21.33%', [], GREEN)
    diagram.footer(['横条从0分开始；这是历史演进顺序，不是收益排名，也不是GPU利用率。',
                    '同代码最新矩阵单轮1395（720p）/1043（1080p），不替换这条历史分阶段对照链。'])
    return diagram


def early_evolution():
    diagram = Diagram('08  达到1158之前：先修阻塞，再减少重复工作',
                      '普通VM与Realm分开阅读；框内数字为各阶段历史结果，不是统一条件下的连续A/B。', 1300)
    diagram.box(60, 155, 1320, 165, '更早的普通VM：基础能力',
                ['ACK：消除恒假条件导致的整tick等待；锁等待7.071 ms → 4.43 μs（短诊断）',
                 '并发RPC：720p 938 → 989；精确完成点缓存：989 → 1023',
                 '后续1058含OPP / 诊断差异；不能与Realm成绩直接串联。'], BLUE)
    entries = [
        (60, 395, 'Realm P1–P4', ['98 → 196 → 197 → 296 → 318',
                                '配置恢复、ACK_ARM、IRQ接收精简',
                                '融合快照 + 按需启动等待'], ORANGE),
        (760, 395, 'P8–P12', ['诊断309 → 632 → 808 → 820 → 826 → 829',
                              'tiler所有权交接、Client回复轮询',
                              '日志、Proxy空闲内联、睡前ARM'], GREEN),
        (60, 650, 'P17 / P19 / P25', ['829 → 859；诊断关闭864 → 882 / 881',
                                   '按对象同步固件输出',
                                   'FW worker直接执行原group完成'], PURPLE),
        (760, 650, 'P27–P30', ['881 → 902 → 914 → 918 → 957',
                               '先扩大RPC回复轮询预算',
                               '再以真实cookie覆盖完成等待'], BLUE),
        (60, 905, 'P38 + P39', ['957 → 962 → 1022 / 1022',
                                '完整原生chain的真实完成证明',
                                '同对象 / 同epoch覆盖较早有效point'], GREEN),
        (760, 905, 'P41 + P42', ['1022 → 1023 → 1159 / 1163',
                                '下一次捕获附带旧快照退役',
                                '省独立DESTROY，不复用旧快照'], ORANGE),
    ]
    for left, top, title, lines, accent in entries:
        diagram.box(left, top, 620, 175, title, lines, accent)
    diagram.arrow([(680, 480), (760, 480)])
    diagram.arrow([(1060, 570), (1060, 605), (370, 605), (370, 650)])
    diagram.arrow([(680, 735), (760, 735)])
    diagram.arrow([(1060, 825), (1060, 860), (370, 860), (370, 905)])
    diagram.arrow([(680, 990), (760, 990)])
    diagram.box(60, 1135, 1320, 65, '之后指定1158为近期对照，再推进到1405；两批输入与采样按各自报告读取。', [], BLUE)
    diagram.footer(['图中跳过的P阶段并未丢失：正文P1–P42索引保留撤回、未命中和未执行条目。',
                    '百分比不累加；配置恢复、关闭诊断与生产算法改动分开归因。'])
    return diagram


def ack_arm():
    diagram = Diagram('09  ACK_ARM：一次重置，加一次队列重查',
                      '事件序号由RMM维护；数据仍在共享队列，通知只表示应重新检查。', 1130)
    diagram.box(60, 155, 390, 150, '① Guest接收者排空',
                ['私有复制、校验并处理消息', '暂时观察到队列空'], BLUE)
    diagram.box(525, 155, 390, 150, '② RMM原子ACK_ARM',
                ['acknowledged = pending', 'armed = true'], ORANGE)
    diagram.box(990, 155, 390, 150, '③ Guest acquire重查',
                ['再次检查共享队列', '有数据就继续处理'], GREEN)
    diagram.arrow([(450, 230), (525, 230)])
    diagram.arrow([(915, 230), (990, 230)])
    diagram.box(60, 420, 620, 185, '情况A：通知早于ACK_ARM',
                ['数据已经发布；旧通知可能被本次确认',
                 '③重查发现数据，继续排空',
                 '不能因armed=true就直接睡眠'], BLUE)
    diagram.box(760, 420, 620, 185, '情况B：通知晚于ACK_ARM',
                ['发送者先发布数据，再NOTIFY',
                 'RMM看到armed，记录并触发可信唤醒',
                 '若③已取到消息，额外提示也允许'], GREEN)
    diagram.arrow([(720, 305), (720, 360), (370, 360), (370, 420)])
    diagram.arrow([(720, 360), (1060, 360), (1060, 420)])
    diagram.box(60, 725, 620, 150, '旧路径',
                ['排空 → QUERY → ACK → ARM → 重查',
                 '多次Realm / RMM调用'], PURPLE)
    diagram.box(760, 725, 620, 150, '新路径',
                ['排空 → ACK_ARM → 重查 → 必要时睡眠',
                 '身份、通道与生命周期检查保留'], ORANGE)
    diagram.arrow([(680, 800), (760, 800)])
    diagram.box(60, 935, 1320, 75, 'P2 196 → 197：单独未证明提分；P3进一步删IRQ线程 / QUERY后197 → 296。', [], GREEN)
    diagram.footer(['重查与发布顺序是避免丢唤醒的条件；IRQ不是数据授权，也不是GPU完成证明。',
                    '通知与等待队列协作仍须遵守内核等待协议；原子事件更新不代替队列内存序。'])
    return diagram


def two_polls():
    diagram = Diagram('10  两种主动轮询，与一种周期重试',
                      '三个位置都可能出现1000 μs，但等待的对象、回退和实验归因不同。', 1190)
    diagram.box(60, 155, 620, 240, 'A  RPC回复轮询',
                ['位置：client_comm_vmshm_poll_response',
                 '对象：seq / type匹配的本次RPC回复',
                 '参数：realm_poll_us，P27/P28改预算',
                 '881 → 902 → 914；100 → 200 → 1000 μs',
                 '没有回复：恢复通知 → ARM / 重查 → 睡眠'], BLUE)
    diagram.box(760, 155, 620, 240, 'B  真实GPU完成页检查',
                ['位置：panthor_client_completion_wait',
                 '对象：不可变快照对应的精确成功cookie',
                 'P29/P30：100 → 1000 μs，受用户超时裁剪',
                 '918 → 957；命中率1.44% → 99.58%',
                 '没有成功证明：回退原生WAIT RPC'], GREEN)
    diagram.box(60, 500, 1320, 150, '先后关系：提交已接纳，与GPU已完成是两个事件',
                ['GROUP_SUBMIT → PLAN_EXEC RPC → 接纳回复（A结束）→ GPU异步执行',
                 '导出 / 等待真实fence → 成功cookie（B可命中）→ Client完成对应等待'], ORANGE)
    diagram.arrow([(370, 395), (370, 500)])
    diagram.arrow([(1060, 395), (1060, 500)])
    diagram.box(60, 755, 1320, 165, 'C  sync_file worker：先查cookie，未完成则零超时WAIT，再睡眠重试',
                ['参数sync_file_poll_us控制usleep_range的间隔，是睡眠周期，不是忙轮询预算。',
                 'lazy_snapshot_wait决定有真实消费者时再启动worker；并非每次导出都启动。',
                 '成功cookie本身不唤醒睡眠线程；完整主动完成订阅仍未实现。'], PURPLE)
    diagram.box(60, 985, 1320, 75, '预算是上限：回复 / 真实完成、need_resched或截止时间到达，就提前退出。', [], BLUE)
    diagram.footer(['A减少通信睡眠；B减少冗余完成查询；C是后台等待机制，不能把三者混成一次实验。',
                    '主动检查可能增加CPU活跃时间；未测功耗，不宣称节能。'])
    return diagram


def ranking():
    diagram = Diagram('先看收益：早期突破与近期增量分开排序',
                      '各项只对自己的历史对照负责；两个面板的横轴不同，不能相加或直接比较成本收益。', 1220)
    groups = [
        (170, '早期历史突破（单轮或组合，详见正文）', 110,
         [('tiler heap所有权交接', 104.53, '309 → 632'),
          ('通信IRQ接收链精简', 50.25, '197 → 296'),
          ('Client回复轮询组合', 27.85, '632 → 808'),
          ('快照退役捎带', 13.69, '1023 → 1159 / 1163')], GREEN),
        (650, '1158之后六项保留增量（两轮均值）', 8,
         [('硬IRQ提前观察真实完成', 7.17, '1311 → 1405'),
          ('旧前缀完成后观察当前fence', 3.47, '1267 → 1311'),
          ('提交与完成两端减少交接', 2.43, '1237 → 1267'),
          ('SGI15目标端直接返回', 2.40, '1208 → 1237'),
          ('全路径所有权复用组合', 2.20, '1182 → 1208'),
          ('Proxy驻留请求唤醒', 2.07, '1158 → 1182')], BLUE),
    ]
    for top, title, maximum, rows, color in groups:
        diagram.text(60, top, title, 26, color, '700')
        diagram.text(445, top + 32, f'相对各自对照的分数增幅，横轴 0–{maximum}%', 20, MUTED)
        step = 80 if len(rows) == 4 else 65
        for index, (label, percent, comparison) in enumerate(rows):
            y = top + 57 + index * step
            diagram.text(60, y + 24, label, 23)
            width = percent / maximum * 600
            diagram.rect(445, y, width, 34, color, radius=3)
            diagram.text(445 + width + 10, y + 25, f'+{percent:.2f}%', 22, color, '700')
            diagram.text(1190, y + 24, comparison, 19, MUTED)
    diagram.footer(['早期退役捎带范围为+13.29%～+13.69%，图中展示范围上端；轮询组合还含超时判定修复。',
                    '1158→1405累计+21.33%，不是六项百分比相加；图中没有任何新增跑分。'])
    return diagram


def critical_path():
    diagram = Diagram('下一步如何定位：串行响应延迟与流水吞吐分开看',
                      '这是依赖关系示意，不按时间比例绘制；RPC、GPU执行和通知阶段可能重叠。', 1050)
    rows = [(170, 'CPU接纳链', ['Client发布请求', 'Proxy校验 / 接纳', '返回接纳结果'], BLUE),
            (400, '异步执行链', ['原生调度 / ring', 'GPU执行 / 缓存刷新', '真实fence完成'], GREEN),
            (630, '结果可见链', ['Proxy发布cookie', 'Client观察 / 唤醒', '应用继续或读回'], PURPLE)]
    for top, title, stages, color in rows:
        diagram.text(60, top - 22, title, 25, color, '700')
        for index, stage in enumerate(stages):
            x = 60 + 455 * index
            diagram.box(x, top, 410, 105, stage, [], color)
            if index < 2:
                diagram.arrow([(x + 410, top + 52), (x + 455, top + 52)])
    diagram.arrow([(720, 275), (720, 330), (265, 330), (265, 400)], dashed=True)
    diagram.arrow([(1175, 505), (1175, 560), (265, 560), (265, 630)])
    diagram.box(60, 815, 1320, 100, '先回答哪个条件让应用不能继续',
                ['同步finish看端到端延迟；异步多在途看服务率与瓶颈；多Client再看尾延迟与整批完成时间。'], ORANGE)
    diagram.footer(['不能把重叠计时相加，也不能由低Proxy CPU利用率证明它不在延迟关键路径上。',
                    'FLUSH_ID、WC读写、分配清零和准入限制都是候选解释，尚未通过新实验确定根因。'])
    return diagram


def main():
    output = Path('docs/shared/assets/proxyclient-optimizations-20261025')
    output.mkdir(parents=True, exist_ok=True)
    config = Path('build/clientproxy-guide-20261022/fonts.conf').resolve()
    os.environ['FONTCONFIG_FILE'] = str(config)
    results = []
    for name, make in [('overview', overview), ('ownership', ownership), ('rpc', rpc),
                       ('snapshot', snapshot), ('notification', notification),
                       ('fence', fence), ('scores', scores),
                       ('early-evolution', early_evolution), ('ack-arm', ack_arm),
                       ('two-polls', two_polls), ('ranking', ranking),
                       ('critical-path', critical_path)]:
        diagram = make()
        diagram.parts = [re.sub(r'(>)[0-9]{2}  ', r'\1', part) for part in diagram.parts]
        svg = diagram.write(output, name)
        png = renderer['render_png'](svg)
        results.append({'svg': str(svg), 'png': str(png), 'bytes': png.stat().st_size})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
