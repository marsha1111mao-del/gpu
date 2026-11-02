"""Render explanatory figures for the three GPU sharing optimization mechanisms."""
import argparse
import json
import os
import runpy
from pathlib import Path

R = runpy.run_path('scripts/analysis/render-clientproxy-guide.py')
D = R['Diagram']
B, G, O, P = (R[x] for x in ('BLUE', 'GREEN', 'ORANGE', 'PURPLE'))


def ownership():
    d = D('缓存所有权：让同步跟随真实交接', 'GPU-only chunk、共享payload和控制对象采用不同策略；下面不是所有BO通用的状态机。', 1030)
    d.box(60, 155, 1320, 130, '原路径：GPU长期使用，CPU却反复参与同步',
          ['CPU初始化 → 提交时扫描 / 同步 → GPU执行 → 完成时扫描 / 同步 → 下一次提交重复',
           '瓶颈：对没有CPU消费者的tiler chunk，维护量随提交次数反复增长。'], O)
    stages = [('CPU初始化', ['写chunk头部', 'CPU暂时持有映射']),
              ('一次真实交接', ['clean / invalidate到PoC', '撤销vmap，标记gpu_owned']),
              ('GPU长期使用', ['通用同步排除GPU_ONLY', '不允许CPU任意重新访问'])]
    for i, (title, lines) in enumerate(stages):
        x = 60 + i * 455
        d.box(x, 365, 410, 145, title, lines, G)
        if i < 2:
            d.arrow([(x + 410, 438), (x + 455, 438)])
    d.box(60, 600, 620, 175, '共享payload：限定内存模型',
          ['授权且pinned；CPU使用WC映射', 'managed VM保留root reservation',
           '省去全BO准备；WC并非CPU访问零成本'], B)
    d.box(760, 600, 620, 175, '控制对象：仍需精确同步',
          ['ring / 固件输入：写入后发布', '完成记录 / 固件输出：读取前维护',
           'CPU屏障不能替代DMA缓存维护'], P)
    d.box(60, 825, 1320, 90, '正确性边界',
          ['GPU_ONLY不是用户可选的免同步权限；普通BO与普通GPUVM不能套用该例外。'], O)
    d.footer(['历史tiler实验：309 → 632（+104.53%）；单轮历史对照，不代表当前版本剩余收益。',
              '统一所有权状态机是可进一步完善的设计表达；当前实现是上述多处具体约束。'])
    return d


def completion():
    d = D('完成快速路径：GPU已完成，尽快让应用知道', '只提前观察真实完成；不省略GPU依赖，不把接纳回复当成完成。示意不按时间比例。', 1060)
    d.box(60, 155, 1320, 130, '原路径：真实完成之后仍有多层交接',
          ['GPU更新记录 → 硬IRQ → IRQ线程 / worker → 原生fence → chain处理 → Proxy → Client',
           '短任务或同步finish容易把这些串行交接暴露为应用等待。'], O)
    d.box(60, 370, 390, 190, '① 有界观察真实完成',
          ['managed + active + 无fault/reset', 'trylock；维护真实sync record',
           'status=0且seqno覆盖目标', '每次硬IRQ全局最多8个job'], G)
    d.box(525, 370, 390, 190, '② 化简完成依赖',
          ['旧前缀全部完成？', '是：观察当前真实fence',
           '否：仍观察完整chain', '完整chain身份 / 引用仍保留'], P)
    d.box(990, 370, 390, 190, '③ 发布精确完成证明',
          ['真实成功 → release写cookie', 'Client acquire读取并精确匹配',
           'slot复用前结束旧回调', '错误或不匹配 → 原等待路径'], B)
    d.arrow([(450, 465), (525, 465)])
    d.arrow([(915, 465), (990, 465)])
    d.box(60, 655, 620, 155, '失败与竞争：保留慢路径',
          ['锁忙 / 超预算 / 状态不符：跳过快路径', '原IRQ mask、ACK、drain、unmask保留',
           'job引用释放留在进程上下文'], O)
    d.box(760, 655, 620, 155, '依赖语义：完成当前不一定完成全部',
          ['完整完成 = 旧前缀完成 AND 当前完成', '不能仅按最大timeline值或cookie大小判断',
           '源对象reset不改变已导出的真实fence快照'], P)
    d.footer(['历史独立增量：有界观察+7.17%；前缀化简+3.47%。各自基线不同，百分比不能相加。',
              '精确cookie已有实现；完整主动完成订阅尚未实现，未命中仍可能走WAIT RPC。'])
    return d


def notification():
    d = D('可信通知：在驻留条件满足时减少Host往返', '本图只展开Client请求唤醒Proxy的优化方向；不代表任意中断或全部GPU完成通知。', 1110)
    rows = [
        (165, '原路径', ['Client → RMM', '发送端Host / KVM', '目标Host → RMM', 'IRQ127 → Proxy'], O),
        (390, '驻留唤醒：发送端可直接返回', ['Client → RMM', 'Root发送SGI0', '目标Host → RMM', 'IRQ127 → Proxy'], B),
        (615, '目标端快速返回：再减少目标Host往返', ['Client → RMM', 'Root发送SGI15', '目标RMM核对 / TAKE', '更新私有LR → Proxy'], G)]
    for top, title, boxes, color in rows:
        d.text(60, top - 20, title, 25, color, '700')
        for i, title in enumerate(boxes):
            x = 60 + i * 340
            d.box(x, top, 300, 95, title, [], color)
            if i < 3:
                d.arrow([(x + 300, top + 48), (x + 340, top + 48)])
    d.box(60, 825, 620, 145, '授权依据仍在可信状态中',
          ['RMM：endpoint / peer / pending / MPIDR', 'Root：受限SGI发送与TAKE',
           '物理SGI本身不证明消息合法或GPU完成'], P)
    d.box(760, 825, 620, 145, '条件不满足就回退',
          ['非驻留 / 同CPU / Root失败等走Host路径', '当前约束REC0；不是通用多vCPU承诺',
           'Host仍可拒绝调度，不保证任意时限送达'], O)
    d.footer(['历史各阶段：1158 → 1182（+2.07%）；1208 → 1237（+2.40%）。',
              'RK/OpenCCA平台扩展，非标准CCA现成ABI；普通中断和KVM VGIC路径继续保留。'])
    return d


def lifetime():
    d = D('同步对象：固定依赖，再减少不必要的RPC', '公开syncobj可以改变；已导出的sync_file必须继续指向导出时的真实依赖。', 930)
    d.box(60, 160, 620, 150, '公开syncobj',
          ['当前指向fence A', 'RESET / IMPORT / TRANSFER后可能指向B',
           '不能用它的新状态替代旧导出依赖'], O)
    d.box(760, 160, 620, 150, '私有不可变快照',
          ['导出时固定fence A并持有强引用', '源对象之后改变，旧sync_file仍等待A',
           '完成观察绑定精确fence / cookie'], G)
    d.arrow([(680, 230), (760, 230)])
    d.box(60, 415, 620, 150, '旧控制路径',
          ['最后用户释放 → 独立DESTROY RPC', '下一次导出 → 独立捕获RPC',
           '短生命周期对象带来额外往返'], O)
    d.box(760, 415, 620, 150, '退役捎带',
          ['无人使用的句柄进入有界退役队列', '下次捕获一起发送；Proxy整批校验',
           '满队 / close显式排空'], B)
    d.arrow([(680, 490), (760, 490)])
    d.box(60, 675, 1320, 110, '不改变GPU依赖，只改变控制对象的创建与回收时机',
          ['退役捎带不复用旧fence；TRANSFER_CAPTURE是另一机制，虽减少RPC，未证明GLMark提速。'], P)
    d.footer(['历史退役捎带：1023 → 1159 / 1163（+13.29%～13.69%）；不归因给其他快照优化。',
              '这项适合作为完成快速路径的支撑机制；单纯批处理不是独立的新颖性依据。'])
    return d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fontconfig', type=Path,
                        help='Fontconfig file when CJK fonts are not installed system-wide')
    args = parser.parse_args()
    out = Path('docs/shared/assets/gpu-core-optimizations-20261028')
    out.mkdir(parents=True, exist_ok=True)
    if args.fontconfig:
        if not args.fontconfig.is_file():
            parser.error(f'Fontconfig file not found: {args.fontconfig}')
        os.environ['FONTCONFIG_FILE'] = str(args.fontconfig.resolve())
    results = []
    for name, make in [('ownership', ownership), ('completion', completion),
                       ('notification', notification), ('lifetime', lifetime)]:
        svg = make().write(out, name)
        png = R['render_png'](svg)
        results.append({'name': name, 'png': str(png), 'bytes': png.stat().st_size})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
