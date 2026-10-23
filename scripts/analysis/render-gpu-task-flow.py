import json
import os
from pathlib import Path
import runpy


renderer = runpy.run_path('scripts/analysis/render-clientproxy-guide.py')
Diagram = renderer['Diagram']
BLUE = renderer['BLUE']
GREEN = renderer['GREEN']
PURPLE = renderer['PURPLE']
ORANGE = renderer['ORANGE']
MUTED = renderer['MUTED']

ABI_FILL = '#eaf1ff'
INTERNAL_FILL = '#fff3df'
NATIVE_FILL = '#e9f6f0'


def badge(diagram, left, top, width, label, color, fill):
    diagram.rect(left, top, width, 34, fill, color, radius=7)
    diagram.text(left + width / 2, top + 24, label, 17, color, '700', 'middle')


def resources():
    diagram = Diagram('01  调用边界：Mesa ioctl如何变成ClientProxy内部请求',
                      '左列是Native与ProxyClient共用的DRM UAPI；中、右列是ProxyClient新增实现，不由Mesa直接调用。', 1390)
    badge(diagram, 60, 132, 390, 'Mesa / UMD调用：公开DRM ioctl或syscall', BLUE, ABI_FILL)
    badge(diagram, 525, 132, 390, 'panthor-client转换：内部RPC或本地快路径', ORANGE, INTERNAL_FILL)
    badge(diagram, 990, 132, 390, 'Proxy / 原生Panthor：真实资源操作', GREEN, NATIVE_FILL)
    stages = [
        (215, '① VM_CREATE ioctl', ['Mesa请求GPU地址空间'],
         'VM_CREATE RPC', ['携带session、flags与VA范围'],
         '创建真实GPUVM', ['维护Client句柄 → 原生对象']),
        (415, '② BO_CREATE / MMAP_OFFSET', ['随后通过mmap写入BO'],
         'BO请求＋共享页映射', ['mmap后的普通CPU写入不是RPC'],
         '创建真实BO', ['使用已授权的共享物理页']),
        (615, '③ VM_BIND ioctl', ['BO＋offset＋GPUVA＋范围'],
         'VM_BIND RPC', ['发送句柄和范围，不复制BO内容'],
         '校验并建立GPU映射', ['GPUVA → 当前Client授权页']),
        (815, '④ GROUP_CREATE ioctl', ['SYNCOBJ_CREATE是通用DRM ioctl'],
         'GROUP_CREATE RPC', ['普通syncobj可先本地创建、按需物化'],
         '创建group / queue', ['绑定真实GPUVM和调度对象']),
    ]
    for top, umd_title, umd_lines, client_title, client_lines, proxy_title, proxy_lines in stages:
        diagram.box(60, top, 390, 130, umd_title, umd_lines, BLUE)
        diagram.box(525, top, 390, 130, client_title, client_lines, ORANGE)
        diagram.box(990, top, 390, 130, proxy_title, proxy_lines, GREEN)
        diagram.arrow([(450, top + 65), (525, top + 65)], '进入前端', (456, top + 48))
        diagram.arrow([(915, top + 65), (990, top + 65)], '内部调用', (922, top + 48))
    diagram.box(60, 1030, 390, 130, '⑤ CPU写命令与输入',
                ['普通内存写；不是DRM ioctl', '也不发送ClientProxy RPC'], BLUE)
    diagram.box(525, 1030, 390, 130, '共享BO保持同一批物理页',
                ['Client与Proxy映射同一份数据', '控制RPC只传句柄、范围和同步点'], ORANGE)
    diagram.box(990, 1030, 390, 130, 'GPU稍后按GPUVA读取BO',
                ['命令内容不随提交整块复制', 'GPU执行由真实Panthor调度'], PURPLE)
    diagram.arrow([(450, 1095), (525, 1095)])
    diagram.arrow([(915, 1095), (990, 1095)])
    diagram.rect(60, 1205, 1320, 82, '#f3f6fb', '#d9e1ee')
    diagram.text(82, 1240, '识别规则：VM_CREATE / BO_CREATE / VM_BIND / GROUP_CREATE等是Mesa可见UAPI；', 22, BLUE, '700')
    diagram.text(82, 1272, '带RPC、PLAN、CAPTURE、cookie、NOTIFY字样的是ClientProxy内部协议或机制。', 22, ORANGE, '700')
    diagram.footer(['图示为依赖关系，不强制所有应用采用完全相同调用顺序；VM_BIND也可带同步依赖。',
                    'Panthor ioctl名称均省略DRM_IOCTL_PANTHOR_前缀；SYNCOBJ_*属于通用DRM UAPI。'])
    return diagram


def submission():
    diagram = Diagram('02  提交与导出：公开ioctl、内部RPC和真实fence',
                      '蓝色标签＝Mesa / libdrm调用；橙色标签＝ClientProxy内部；绿色标签＝Proxy对原生Panthor的调用。', 1390)
    lanes = [(190, 'Client应用 / Mesa', BLUE), (550, 'Client前端', BLUE),
             (910, 'Proxy / 原生Panthor', GREEN), (1270, 'GPU / 固件', PURPLE)]
    for center, title, color in lanes:
        diagram.rect(center - 150, 145, 300, 58, '#f3f6fb')
        diagram.text(center, 182, title, 24, color, '700', 'middle')
        diagram.parts.append(f'<path d="M{center},205 V1220" stroke="{color}" stroke-opacity="0.25" stroke-width="2" stroke-dasharray="7,7"/>')

    def message(start, finish, top, label, color=BLUE):
        diagram.arrow([(start, top), (finish, top)])
        diagram.rect(min(start, finish) + 8, top - 42, abs(finish - start) - 16, 32, 'white', radius=0)
        diagram.text((start + finish) / 2, top - 17, label, 20, color, anchor='middle')

    badge(diagram, 70, 220, 255, 'UMD / DRM ioctl', BLUE, ABI_FILL)
    message(190, 550, 290, 'GROUP_SUBMIT')
    diagram.text(60, 333, '参数：group、命令流GPUVA / 长度、等待与输出同步点', 21, MUTED)
    badge(diagram, 586, 332, 255, 'ClientProxy内部RPC', ORANGE, INTERNAL_FILL)
    message(550, 910, 400, '首次PLAN_REGISTER；每次PLAN_EXEC', ORANGE)
    diagram.box(725, 435, 375, 146, 'Proxy校验 → 原生提交入口',
                ['创建job、绑定依赖和输出fence', '将fence安装进输出syncobj', '完成必要同步并进入调度队列'], GREEN)
    diagram.box(725, 605, 375, 146, '可选：注册提交完成观察',
                ['保留精确的真实fence chain', '共享page[7].cookie先清为0', '保存期望值42，安装完成回调'], ORANGE)
    message(910, 550, 810, 'PLAN_EXEC响应：ret + 可选slot / cookie', GREEN)
    message(550, 190, 860, 'GROUP_SUBMIT ioctl返回：仅表示接纳', GREEN)
    message(910, 1270, 850, '固件调度GPU（可与返回重叠）', PURPLE)

    badge(diagram, 70, 875, 255, 'UMD / 通用DRM ioctl', BLUE, ABI_FILL)
    message(190, 550, 945, 'SYNCOBJ_TRANSFER(point N → binary)')
    badge(diagram, 586, 902, 255, 'ClientProxy内部RPC', ORANGE, INTERNAL_FILL)
    message(550, 910, 1015, 'TRANSFER_CAPTURE', ORANGE)
    diagram.box(725, 1045, 375, 112, '一次查找同一真实fence chain',
                ['写入binary目标＋私有snapshot', '返回snapshot句柄、cookie / slot'], GREEN)
    message(910, 550, 1195, 'TRANSFER结果＋捕获凭据', GREEN)
    message(550, 190, 1250, '随后EXPORT_SYNC_FILE：命中缓存则不再发snapshot RPC', BLUE)
    diagram.footer(['GROUP_SUBMIT、SYNCOBJ_TRANSFER、HANDLE_TO_FD是公开DRM UAPI；PLAN_*与TRANSFER_CAPTURE只存在于ClientProxy内部。',
                    'cookie / slot是观察凭据，不是完成通知；GROUP_SUBMIT不返回内核fence指针，也不自动返回FD。'])
    return diagram


def cookie_publication():
    diagram = Diagram('03  ClientProxy内部完成证明：cookie不是Mesa ioctl',
                      'slot＝7、cookie＝42仅作示例。Mesa不会读写完成页；读写和校验均由Client / Proxy内核驱动完成。', 1130)
    badge(diagram, 60, 125, 370, '内部：Proxy fence回调与共享完成页', ORANGE, INTERNAL_FILL)
    diagram.box(60, 180, 350, 125, 'GPU执行结束 / 物理IRQ',
                ['Proxy完成必要的结果同步', '确认原生fence / chain完成'], PURPLE)
    diagram.box(545, 180, 350, 125, '调用已注册的fence回调',
                ['snapshot_complete → publish', '只发布无错误的成功状态'], GREEN)
    diagram.box(1030, 180, 350, 125, 'release写入共享完成页',
                ['page[7].cookie：0 → 42', '这里不调用RMM NOTIFY'], ORANGE)
    diagram.arrow([(410, 242), (545, 242)])
    diagram.arrow([(895, 242), (1030, 242)])
    diagram.box(60, 375, 600, 155, 'Proxy已完成发布，但Client不一定在运行',
                ['没有Client观察者：状态留在共享页，等以后检查',
                 '已经睡眠的线程：不会被这次内存写入直接唤醒',
                 '已发出WAIT RPC的线程：由RPC回复路径结束等待'], GREEN)
    diagram.box(780, 375, 600, 155, '完成页：双方映射到同一批物理页',
                ['不是完成之后再复制cookie给Client',
                 'Client内核持有页映射及私有expected_cookie＝42',
                 '图中箭头表示内存访问，不代表中断投递'], ORANGE)
    diagram.arrow([(1205, 305), (1205, 375)])
    diagram.box(780, 600, 600, 155, 'Client驱动等待代码 / sync_file worker读取',
                ['observed = smp_load_acquire(page[7].cookie)',
                 'observed == 42：该观察对应的真实fence已成功完成',
                 '不匹配：不能证明完成，按具体等待路径回退'], BLUE)
    diagram.arrow([(1080, 530), (1080, 600)], '内部读取', (1102, 572))
    diagram.box(60, 600, 600, 155, '为什么不能只判断cookie非零',
                ['slot以后可能复用，必须与私有期望值精确相等',
                 'timeline还须检查对象、point与状态版本',
                 'fence错误不发布成功cookie，通过真实查询取结果'], ORANGE)
    diagram.rect(60, 825, 1320, 145, '#fff3df')
    diagram.text(80, 863, '边界：cookie、slot、completion page、snapshot_complete都属于ClientProxy内部。', 25, ORANGE, '700')
    diagram.text(80, 905, 'Mesa只能观察公开结果：WAIT ioctl返回，或导出的sync_file变为signaled。', 23, BLUE, '700')
    diagram.text(80, 945, 'publish里的complete(watch->done)只供Proxy回收；它不是Client waiter.done或本地dma_fence。', 22, MUTED)
    diagram.footer(['release / acquire保证CPU发布与观察的顺序；不能代替GPU数据所需的缓存维护。',
                    '若注册回调时fence已经完成，则立即走同一发布逻辑；失败记录不会被当成成功证明。'])
    return diagram


def client_observation():
    diagram = Diagram('04  公开等待ioctl进入后：Client内部怎样判断完成',
                      '每列顶部是用户态可见入口；cookie检查、WAIT RPC和worker循环都属于ClientProxy内部实现。', 1360)
    badge(diagram, 60, 120, 360, '蓝色标题：公开DRM UAPI / FD行为', BLUE, ABI_FILL)
    badge(diagram, 510, 120, 420, '框内流程：ClientProxy内部快路径或RPC', ORANGE, INTERNAL_FILL)
    columns = [
        (60, 'A  UAPI：TIMELINE_WAIT查询', BLUE,
         ['单句柄、正point、WAIT_ALL', '非阻塞且状态版本匹配才走快路径'],
         '内部：检查timeline完成证明',
         ['读取slot并精确比较cookie', '完整chain证明可覆盖更早有效点'],
         '命中：当前ioctl直接返回成功',
         ['没有额外唤醒动作', '调用线程本来就在执行'],
         '内部回退：TIMELINE_WAIT RPC',
         ['由原生同步对象判断结果', '阻塞等待不使用这个本地查询快路径']),
        (510, 'B  UAPI：SYNCOBJ_WAIT', BLUE,
         ['对象已持有不可变snapshot', '并且有完成页 / cookie观察凭据'],
         '内部：短时检查共享完成页',
         ['最长约1000μs，受原期限限制', '调度需求 / 信号可提前结束'],
         '命中：当前WAIT ioctl返回成功',
         ['按WAIT_ALL / WAIT_ANY判定', '不是收到一个完成中断'],
         '内部回退：发送真实WAIT RPC',
         ['按剩余期限等待 / 查询', '成功、未完成或错误均看回复结果']),
        (960, 'C  UAPI：HANDLE_TO_FD / poll', BLUE,
         ['poll / epoll等需要本地fence信号', '启用signaling后安排Client worker'],
         '内部worker先检查snapshot cookie',
         ['命中则完成；否则发非阻塞WAIT RPC', 'RPC携带真实fence状态查询标志'],
         '仍未完成：worker定时休眠再检查',
         ['usleep_range默认约1–2ms', '定时唤醒，不是cookie把它唤醒'],
         '成功：signal本地dma_fence',
         ['再由sync_file唤醒FD等待者', '错误先set_error再signal，等待有界']),
    ]
    for left, title, color, introduction, check_title, check_lines, hit_title, hit_lines, fallback_title, fallback_lines in columns:
        diagram.box(left, 150, 420, 148, title, introduction, color)
        diagram.box(left, 355, 420, 150, check_title, check_lines, color)
        diagram.box(left, 565, 420, 150, hit_title, hit_lines, color)
        diagram.box(left, 775, 420, 150, fallback_title, fallback_lines, color)
        diagram.arrow([(left + 210, 298), (left + 210, 355)])
        diagram.arrow([(left + 210, 505), (left + 210, 565)])
        if left < 960:
            diagram.text(left + 225, 542, '匹配', 18, color)
            diagram.arrow([(left, 430), (left - 14, 430),
                           (left - 14, 850), (left, 850)])
            diagram.text(left + 20, 750, '未匹配 → 直接回退（不经过成功返回）', 18, MUTED)
        else:
            diagram.text(left + 225, 542, '仍未完成', 18, color)
            diagram.arrow([(left, 640), (left - 14, 640),
                           (left - 14, 430), (left, 430)])
            diagram.arrow([(left + 420, 430), (left + 434, 430),
                           (left + 434, 850), (left + 420, 850)])
            diagram.text(left + 20, 750, '命中 / 查询成功 → 直接完成本地fence', 18, MUTED)
    diagram.rect(60, 1000, 1320, 185, '#fff3df')
    diagram.text(80, 1040, '用户态只调用WAIT / HANDLE_TO_FD并观察返回值或FD；不会直接调用cookie检查和WAIT RPC。', 24, ORANGE, '700')
    diagram.text(80, 1082, 'A / B：命中时Client前端直接返回ioctl。C：worker signal本地fence，再唤醒FD等待者。', 23, BLUE, '700')
    diagram.text(80, 1124, 'C的内部循环是“查cookie → 查真实状态 → 未完成则定时睡眠 → 重试”，不是长时间阻塞Proxy。', 22, MUTED)
    diagram.text(80, 1162, 'A / B左线表示未命中回退；C左线表示重试、右线表示成功。无凭据时仍有真实查询。', 22, MUTED)
    diagram.footer(['sync_file启用惰性等待时由enable_signaling启动worker；关闭惰性等待则导出后即安排worker。',
                    '完成页短轮询、RPC回复短轮询和sync_file worker定时重查是三件不同的事。'])
    return diagram


def notifications():
    diagram = Diagram('05  ClientProxy内部通知：Mesa不调用NOTIFY或ACK_ARM',
                      '公开WAIT ioctl进入Client前端后，才可能触发下列RPC、RMM事件与回复分发。', 1450)
    badge(diagram, 60, 125, 355, '内部：Client / Proxy通信协议', ORANGE, INTERNAL_FILL)
    badge(diagram, 1030, 125, 350, '对用户态只返回WAIT结果', BLUE, ABI_FILL)
    diagram.box(60, 180, 350, 145, 'Client前端发送WAIT / 查询RPC',
                ['发布请求 → RMM NOTIFY', '为请求建立waiter.done', '可短时轮询RPC回复队列'], BLUE)
    diagram.box(545, 180, 350, 145, 'Proxy调用原生DRM wait',
                ['阻塞请求：等待fence或超时', '零超时查询：立即返回状态', 'GPU物理IRQ驱动真实完成'], GREEN)
    diagram.box(1030, 180, 350, 145, 'Proxy写内部WAIT_RSP回复',
                ['返回ret及first_signaled等', 'ret可为成功、未完成或错误', '先发布消息，再判断是否通知'], GREEN)
    diagram.arrow([(410, 252), (545, 252)])
    diagram.arrow([(895, 252), (1030, 252)])
    diagram.box(60, 425, 600, 140, '分支1：Client前端还在短时轮询回复',
                ['NO_NOTIFY有效：Proxy可省掉RMM回复通知',
                 '调用线程从共享回复队列读到对应WAIT_RSP',
                 '这里读的是RPC回复，不是完成页cookie'], BLUE)
    diagram.box(780, 425, 600, 140, '分支2：内部通知，Client线程可能已睡眠',
                ['Proxy NOTIFY → RMM可信事件 → Client事件IRQ',
                 'IRQ安排RX worker；worker读取共享回复队列',
                 '这是通信IRQ，不是GPU物理IRQ'], ORANGE)
    diagram.arrow([(1205, 325), (1205, 375), (360, 375), (360, 425)])
    diagram.arrow([(1205, 325), (1205, 425)])
    diagram.box(360, 655, 720, 140, 'Client驱动统一分发：按reply_to / type匹配请求',
                ['拷贝结果 → complete(waiter.done)',
                 '若调用线程在睡眠则唤醒；已完成则等待函数直接返回',
                 'RPC交付完成后，还须检查WAIT_RSP中的实际ret'], BLUE)
    diagram.arrow([(360, 565), (360, 605), (600, 605), (600, 655)])
    diagram.arrow([(1080, 565), (1080, 605), (840, 605), (840, 655)])
    diagram.box(60, 870, 600, 140, '回到公开WAIT ioctl调用线程',
                ['WAIT成功：按接口语义返回给用户态',
                 '未完成 / 超时 / 错误：返回对应状态',
                 '不会把“收到回复”自动当成“GPU成功完成”'], BLUE)
    diagram.box(780, 870, 600, 140, 'Client内部sync_file worker后续动作',
                ['真实状态查询成功：signal本地fence',
                 '仍未完成：定时睡眠后重新检查cookie / 查询',
                 '最终由本地fence唤醒poll / epoll等FD等待者'], PURPLE)
    diagram.arrow([(600, 795), (600, 835), (360, 835), (360, 870)])
    diagram.arrow([(840, 795), (840, 835), (1080, 835), (1080, 870)])
    diagram.rect(60, 1075, 1320, 185, '#fff3df')
    diagram.text(80, 1117, '全部属于内部实现：RMM NOTIFY、NO_NOTIFY、ACK_ARM、WAIT_RSP、reply_to和waiter.done。', 23, ORANGE, '700')
    diagram.text(80, 1161, 'Mesa / 应用只看到公开WAIT ioctl最终返回，或本地sync_file FD变为signaled。', 23, BLUE, '700')
    diagram.text(80, 1205, 'cookie成功证明、RPC交付完成、本地fence signal是不同层；cookie写入不会自动发完成IRQ。', 22, MUTED)
    diagram.footer(['阻塞WAIT可在Proxy等待真实fence；sync_file worker刻意使用非阻塞状态查询并在Client侧睡眠。',
                    'Host / VMM协作运行和唤醒Realm；RMM事件及IRQ只提示检查，结果始终以真实状态为准。'])
    return diagram


def main():
    output = Path('docs/shared/assets/gpu-task-flow-20261022')
    output.mkdir(parents=True, exist_ok=True)
    font_config = Path('build/clientproxy-guide-20261022/fonts.conf')
    if font_config.exists():
        os.environ['FONTCONFIG_FILE'] = str(font_config.resolve())
    artifacts = []
    for name, diagram in [('resources', resources()), ('submission-fence', submission()),
                          ('cookie-publication', cookie_publication()),
                          ('client-observation', client_observation()), ('notifications', notifications())]:
        svg = diagram.write(output, name)
        png = renderer['render_png'](svg)
        artifacts.append({'svg': str(svg), 'png': str(png), 'bytes': png.stat().st_size})
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
