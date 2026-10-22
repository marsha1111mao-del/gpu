import argparse
import ctypes
import ctypes.util
from html import escape
import json
import os
from pathlib import Path


INK = '#17243b'
MUTED = '#52627a'
BLUE = '#2767d8'
GREEN = '#16836a'
ORANGE = '#d58120'
PURPLE = '#7c58bb'
PALE = '#f3f6fb'


class Diagram:
    def __init__(self, title, subtitle, height=900):
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="{height}" viewBox="0 0 1440 {height}">',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#667791"/></marker></defs>',
            '<style>text { font-family: "Noto Sans CJK SC", sans-serif; }</style>',
            f'<rect width="1440" height="{height}" fill="white"/>',
        ]
        self.text(58, 64, title, 36, INK, '700')
        self.text(60, 104, subtitle, 21, MUTED)

    def text(self, left, top, value, size=23, color=INK, weight='400', anchor='start'):
        self.parts.append(
            f'<text x="{left}" y="{top}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'
        )

    def rect(self, left, top, width, height, fill=PALE, stroke='none', radius=14):
        self.parts.append(
            f'<rect x="{left}" y="{top}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'
        )

    def box(self, left, top, width, height, title, lines=(), accent=BLUE):
        self.rect(left, top, width, height, PALE, '#d9e1ee')
        self.rect(left, top, 6, height, accent, radius=3)
        self.text(left + 22, top + 38, title, 25, accent, '700')
        for index, line in enumerate(lines):
            self.text(left + 22, top + 76 + index * 30, line, 21)

    def arrow(self, points, label=None, label_position=None, dashed=False):
        coords = ' '.join(f'{left},{top}' for left, top in points)
        dash = ' stroke-dasharray="8,7"' if dashed else ''
        self.parts.append(
            f'<polyline points="{coords}" fill="none" stroke="#667791" stroke-width="2.5" marker-end="url(#arrow)"{dash}/>'
        )
        if label is not None:
            self.text(*label_position, label, 20, MUTED)

    def footer(self, lines):
        top = self.height - 42 - (len(lines) - 1) * 30
        for line in lines:
            self.text(60, top, line, 20, MUTED)
            top += 30

    def write(self, directory, name):
        output = directory / f'{name}.svg'
        output.write_text('\n'.join(self.parts + ['</svg>']) + '\n')
        return output


def architecture():
    diagram = Diagram('A  总体架构：控制、数据、通知三条路径',
                      'GPU命令由Client生成；可信Proxy操作真实设备；RMM授权共享与保存可信事件。')
    diagram.box(60, 150, 355, 165, 'Client Realm',
                ['应用 / Mesa / PanVK', 'panthor-client：DRM前端', '本地对象、计划、完成检查'])
    diagram.box(550, 150, 355, 165, '可信Proxy Realm',
                ['panthor-proxy：会话与校验', '原生Panthor：GPUVM / 调度', '设备控制与真实fence'], GREEN)
    diagram.box(1040, 150, 340, 165, 'Mali-G610',
                ['GPU内置MMU与页表遍历', '执行命令流 / 数据访存', '硬件中断 → 原生驱动'], PURPLE)
    diagram.arrow([(415, 205), (550, 205)], 'RPC', (452, 185))
    diagram.arrow([(905, 205), (1040, 205)], '提交', (945, 185))
    diagram.arrow([(1040, 270), (905, 270)], 'IRQ', (946, 298))
    diagram.arrow([(550, 270), (415, 270)], '回复', (452, 298))
    diagram.box(60, 398, 1320, 116, '数据面：长期共享BO池',
                ['Client CPU写入 / 读取；GPU经授权GPUVM访问同一批物理页。大块内容不随每次RPC复制。'], GREEN)
    diagram.arrow([(230, 315), (230, 398)], 'CPU访问', (247, 365))
    diagram.arrow([(1210, 315), (1210, 398)], 'GPU访存', (1228, 365))
    diagram.box(60, 605, 725, 137, 'RMM：可信基础能力',
                ['endpoint / channel / grant / RTT / pending / ACK_ARM', 'GPU物理页租约；其他托管IOMMU的真实表与root'], ORANGE)
    diagram.box(870, 605, 510, 137, 'Host KVM / VMM',
                ['创建和调度Realm；内存后备与供电时钟', '协作唤醒，不代替授权或完成判断'], PURPLE)
    diagram.arrow([(785, 665), (870, 665)], dashed=True)
    diagram.arrow([(420, 605), (420, 560), (700, 560), (700, 514)],
                  '共享授权 / 可信事件', (760, 568), dashed=True)
    diagram.footer(['实线：数据或请求路径；虚线：授权、事件与调度协作。',
                    'GPUVM页表由可信Proxy/Panthor维护；不能与RMM托管的其他IOMMU页表混为一谈。'])
    return diagram


def translation():
    diagram = Diagram('B  地址翻译：三条访问路径汇聚到同一HPA',
                      'CPU访问经过各自Realm RTT；GPU使用自己的GPUVM页表。共享的是最终物理页。')
    rows = [(200, 'Client CPU VA', 'Client IPA', 'Client RTT', BLUE),
            (400, 'Proxy CPU VA', 'Proxy IPA', 'Proxy RTT', GREEN),
            (600, 'GPU VA', 'GPUVM页表', '授权PTE → HPA', PURPLE)]
    for top, first, second, third, accent in rows:
        diagram.box(60, top, 255, 105, first, ['CPU地址' if top != 600 else '设备虚拟地址'], accent)
        diagram.box(395, top, 255, 105, second,
                    ['各Realm自己的地址' if top != 600 else '可信Panthor生成'], accent)
        diagram.box(730, top, 255, 105, third,
                    ['RMM管理二阶翻译' if top != 600 else '不遍历Client RTT'], accent)
        diagram.arrow([(315, top + 53), (395, top + 53)])
        diagram.arrow([(650, top + 53), (730, top + 53)])
    diagram.box(1110, 337, 270, 230, '同一批HPA页',
                ['数据只存一份', '页数与权限受授权限制', '不得映射控制页', '仍需正确缓存维护'], ORANGE)
    diagram.arrow([(985, 253), (1040, 253), (1040, 380), (1110, 380)])
    diagram.arrow([(985, 453), (1110, 453)])
    diagram.arrow([(985, 653), (1040, 653), (1040, 525), (1110, 525)])
    diagram.footer(['关键检查：session对象 → payload owner / generation / 范围 / 权限 → 真实GPUVM root → RMM翻译及租约。',
                    'Proxy可访问多个Client的授权池，因此“能翻译到HPA”本身不证明页面属于当前请求方。'])
    return diagram


def segmented_bo():
    diagram = Diagram('C  分段BO：逻辑连续不要求整块物理连续',
                      '示意使用三个extent；实际按页记录分段，mmap和GPU映射分别按请求范围解析。', 820)
    colors = [BLUE, GREEN, PURPLE]
    logical_left = [120, 520, 920]
    diagram.text(60, 177, '逻辑BO：offset连续，应用只看一个对象', 25, INK, '700')
    for index, left in enumerate(logical_left):
        diagram.rect(left, 210, 340, 90, colors[index])
        diagram.text(left + 170, 251, f'extent {index + 1}', 26, 'white', '700', 'middle')
        diagram.text(left + 170, 282, f'逻辑页 {index * 4}–{index * 4 + 3}', 21, 'white', anchor='middle')
    diagram.text(60, 541, '共享池实际位置：extent之间可以存在空洞', 25, INK, '700')
    slots = [(100, 240, BLUE, 'extent 1'), (340, 120, '#dce3ee', '空闲'),
             (460, 240, PURPLE, 'extent 3'), (700, 220, '#dce3ee', '其他BO'),
             (920, 240, GREEN, 'extent 2')]
    for left, width, color, label in slots:
        diagram.rect(left, 415, width, 86, color, radius=0)
        diagram.text(left + width / 2, 468, label, 23,
                     MUTED if color == '#dce3ee' else 'white', '700', 'middle')
    diagram.arrow([(290, 300), (220, 415)])
    diagram.arrow([(690, 300), (1040, 415)])
    diagram.arrow([(1090, 300), (580, 415)])
    diagram.box(60, 575, 620, 125, 'CPU局部mmap',
                ['请求offset / length只映射相交的逻辑页', '跨extent时逐段解析，不暴露池内其他对象'])
    diagram.box(720, 575, 660, 125, 'GPU连续VA绑定',
                ['把授权span的实际HPA装入相邻GPU PTE', '仍检查权限、root归属、pin与生命周期'], GREEN)
    diagram.footer(['减少连续大块分配需求；不自动减少每Client授权池的总容量，也不回收旧guest_memfd目标后备。'])
    return diagram


def memory_chart():
    diagram = Diagram('D  内存实测：消除旧目标副本，实际GPU数据不变',
                      '单Client ResNet50；单位MiB；同384 MiB共享源池。数据引用既有实验，无新增测量。', 940)
    scale = 1.08
    origin = 245
    components = [
        ('CPU模型/缓冲', BLUE), ('Native GPU BO', GREEN),
        ('共享源池', PURPLE), ('旧目标后备', ORANGE), ('元数据下限', '#c24e6a'),
    ]
    for index, (label, color) in enumerate(components):
        left = 60 + index * 272
        diagram.rect(left, 146, 20, 20, color, radius=3)
        diagram.text(left + 29, 164, label, 19)
    for tick in range(0, 1001, 200):
        left = origin + tick * scale
        diagram.parts.append(f'<path d="M{left},213 V610" stroke="#e3e9f2"/>')
        diagram.text(left, 642, tick, 20, MUTED, anchor='middle')
    rows = [
        (245, 'Native', [(126.40, BLUE), (327.77, GREEN)], '454.17', 'CPU 126.40 + GPU BO 327.77'),
        (375, '共享旧路径', [(133.02, BLUE), (384, PURPLE), (384, ORANGE), (2.24, '#c24e6a')],
         '903.26', 'CPU 133.02 + 源池 384 + 旧目标 384 + 元数据 2.24'),
        (505, '回收后', [(133.09, BLUE), (384, PURPLE), (2.24, '#c24e6a')],
         '519.33', 'CPU 133.09 + 源池 384 + 元数据 2.24'),
    ]
    for top, label, pieces, total, detail in rows:
        diagram.text(60, top + 42, label, 26, INK, '700')
        left = origin
        for amount, color in pieces:
            diagram.rect(left, top, amount * scale, 66, color, radius=0)
            left += amount * scale
        diagram.text(left + 15, top + 43, total, 25, INK, '700')
        diagram.text(origin, top + 96, detail, 20, MUTED)
    diagram.box(60, 695, 1320, 122, '结果与口径',
                ['合计减少383.93 MiB / 42.50%；相对Native额外占比由98.88%降至14.35%。',
                 '源池已含327.77 MiB用户BO，不能重复相加；旧目标实际缓存页98304 → 0。'], GREEN)
    diagram.footer(['这是各分项峰值之和，不是同时总峰值；排除OS/VM固定预算、GPU页表及未计全的协议分配。',
                    '启动时仍需临时目标CMA；回收后稳态占用不等于启动准入预算。'])
    return diagram


def rpc_chart():
    diagram = Diagram('E  RPC实测：优先减少整次往返，再拆请求通知',
                      '720p单Client；CPU 1.8GHz / GPU 594MHz；rpc-breakdown-720-20261022-a。单位μs。', 1000)
    origin = 360
    scale = 10
    metrics = [('Client总RTT', BLUE), ('Client请求通知', ORANGE), ('Proxy handler', GREEN)]
    for index, (label, color) in enumerate(metrics):
        left = 60 + index * 395
        diagram.rect(left, 150, 22, 22, color, radius=3)
        diagram.text(left + 34, 170, label, 22)
    for tick in range(0, 81, 20):
        left = origin + tick * scale
        diagram.parts.append(f'<path d="M{left},203 V716" stroke="#e3e9f2"/>')
        diagram.text(left, 744, tick, 20, MUTED, anchor='middle')
    rows = [('PLAN_EXEC', 454568, [76.431, 30.634, 20.255]),
            ('TRANSFER', 454357, [53.461, 23.111, 2.768]),
            ('SNAPSHOT_RETIRE', 380555, [56.649, 25.317, 7.489])]
    for index, (name, count, values) in enumerate(rows):
        top = 230 + index * 170
        diagram.text(60, top + 26, name, 25, INK, '700')
        diagram.text(60, top + 62, f'{count:,}次', 21, MUTED)
        for metric_index, (value, (_, color)) in enumerate(zip(values, metrics)):
            bar_top = top + metric_index * 38
            diagram.rect(origin, bar_top, value * scale, 28, color, radius=3)
            diagram.text(origin + value * scale + 12, bar_top + 23, f'{value:.3f}', 22)
    diagram.box(60, 785, 1320, 94, '如何理解',
                ['入队仅0.4–0.5μs；回复通知已抑制99.42%。TRANSFER预捕获快照仍是未实现候选。'], GREEN)
    diagram.footer(['三种时间是分别展示的区间，存在重叠，不能相加；通知含RMM、可能的Host退出及调度。',
                    '图中不是逐帧调用链；GPU完成→Client确认的端到端分位数仍待测量。'])
    return diagram


def render_png(svg_path):
    svg_library = ctypes.CDLL(ctypes.util.find_library('rsvg-2'))
    cairo_library = ctypes.CDLL(ctypes.util.find_library('cairo'))
    object_library = ctypes.CDLL(ctypes.util.find_library('gobject-2.0'))
    svg_library.rsvg_handle_new_from_file.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    svg_library.rsvg_handle_new_from_file.restype = ctypes.c_void_p
    svg_library.rsvg_handle_render_cairo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    svg_library.rsvg_handle_render_cairo.restype = ctypes.c_int
    svg_library.rsvg_handle_get_intrinsic_size_in_pixels.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
    svg_library.rsvg_handle_get_intrinsic_size_in_pixels.restype = ctypes.c_int
    cairo_library.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    cairo_library.cairo_image_surface_create.restype = ctypes.c_void_p
    cairo_library.cairo_create.argtypes = [ctypes.c_void_p]
    cairo_library.cairo_create.restype = ctypes.c_void_p
    cairo_library.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    cairo_library.cairo_surface_write_to_png.restype = ctypes.c_int
    cairo_library.cairo_destroy.argtypes = [ctypes.c_void_p]
    cairo_library.cairo_surface_destroy.argtypes = [ctypes.c_void_p]
    object_library.g_object_unref.argtypes = [ctypes.c_void_p]
    error = ctypes.c_void_p()
    handle = svg_library.rsvg_handle_new_from_file(os.fsencode(svg_path), ctypes.byref(error))
    if not handle:
        raise RuntimeError(f'Unable to load SVG: {svg_path}')
    width = ctypes.c_double()
    height = ctypes.c_double()
    if not svg_library.rsvg_handle_get_intrinsic_size_in_pixels(handle, ctypes.byref(width), ctypes.byref(height)):
        object_library.g_object_unref(handle)
        raise RuntimeError('SVG has no pixel size')
    surface = cairo_library.cairo_image_surface_create(0, int(width.value), int(height.value))
    context = cairo_library.cairo_create(surface)
    output = svg_path.with_suffix('.png')
    try:
        if not svg_library.rsvg_handle_render_cairo(handle, context):
            raise RuntimeError(f'Unable to render {svg_path}')
        status = cairo_library.cairo_surface_write_to_png(surface, os.fsencode(output))
        if status != 0:
            raise RuntimeError(f'PNG write status: {status}')
    finally:
        cairo_library.cairo_destroy(context)
        cairo_library.cairo_surface_destroy(surface)
        object_library.g_object_unref(handle)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('docs/shared/assets/clientproxy-guide-20261022'))
    parser.add_argument('--font-dir', type=Path, default=Path('build/clientproxy-guide-20261022/fonts'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cache = Path('build/clientproxy-guide-20261022/font-cache').resolve()
    cache.mkdir(parents=True, exist_ok=True)
    config = cache.parent / 'fonts.conf'
    config.write_text('<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                      f'<dir>{escape(str(args.font_dir.resolve()))}</dir>'
                      f'<cachedir>{escape(str(cache))}</cachedir></fontconfig>')
    os.environ['FONTCONFIG_FILE'] = str(config)
    outputs = []
    for name, diagram in [('architecture', architecture()), ('translation', translation()),
                          ('segmented-bo', segmented_bo()), ('memory', memory_chart()), ('rpc', rpc_chart())]:
        svg_path = diagram.write(args.output, name)
        png_path = render_png(svg_path)
        outputs.append({'svg': str(svg_path), 'png': str(png_path), 'bytes': png_path.stat().st_size})
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
