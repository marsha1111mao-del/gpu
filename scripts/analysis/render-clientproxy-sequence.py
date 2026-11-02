"""Render the architecture guide's task sequence as SVG and PNG.

Accepts the participant declarations and ->>/-->> messages used by this figure.
The .mmd source is retained alongside the generated image for editing.
"""
import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import runpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fontconfig', type=Path)
    args = parser.parse_args()
    if args.fontconfig:
        if not args.fontconfig.is_file():
            parser.error(f'Missing font configuration: {args.fontconfig}')
        os.environ['FONTCONFIG_FILE'] = str(args.fontconfig.resolve())

    directory = Path('docs/shared/assets/clientproxy-guide-20261022')
    source = directory / 'task-sequence.mmd'
    participants, messages = [], []
    for line in source.read_text().splitlines():
        line = line.strip()
        if not line or line == 'sequenceDiagram':
            continue
        participant = re.fullmatch(r'participant (\w+) as (.+)', line)
        message = re.fullmatch(r'(\w+)(-->>|->>)(\w+): (.+)', line)
        if participant:
            participants.append(participant.groups())
        elif message:
            messages.append(message.groups())
        else:
            raise ValueError(f'Unsupported sequence statement: {line}')

    # Effective size on a page depends on font-size / canvas-width, not PNG pixels.
    # Narrower lanes and wrapped labels approximately double the displayed text.
    font_size = 34
    lane_gap = 270
    xs = {key: 115 + i * lane_gap for i, (key, _) in enumerate(participants)}
    width = 230 + (len(participants) - 1) * lane_gap

    def measure(label):
        return sum(font_size if ord(c) > 255 else
                   font_size * (0.35 if c.isspace() else 0.67)
                   for c in label)

    def wrap(label, maximum):
        preferred = {
            '创建实际对象并建立映射': ['创建实际对象', '并建立映射'],
            '写共享BO中的命令和输入': ['写共享BO中的', '命令和输入'],
            '调度并启动命令流': ['调度并启动', '命令流'],
            '真实fence回调发布完成cookie': ['真实fence回调发布', '完成cookie'],
            '等待完成或导出同步': ['等待完成', '或导出同步'],
            '本地可信命中或真实等待结果': ['本地可信命中', '或真实等待结果'],
        }
        if label in preferred and all(measure(line) <= maximum for line in preferred[label]):
            return preferred[label]
        lines, line = [], ''
        for token in re.findall(r'[A-Za-z0-9_]+|[^A-Za-z0-9_]', label):
            if line and measure(line + token) > maximum:
                lines.append(line.rstrip())
                line = ''
            line += token
        if line:
            lines.append(line.rstrip())
        return lines

    layouts = []
    top = 185
    for sender, arrow, receiver, label in messages:
        available = (abs(xs[sender] - xs[receiver]) or lane_gap) - 20
        lines = wrap(label, available)
        arrow_y = top + (len(lines) - 1) * 44 + 22
        layouts.append((sender, arrow, receiver, label, lines, top, arrow_y))
        top = arrow_y + (100 if sender == receiver else 84)
    bottom = top + 10
    height = bottom + 135
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#334155"/></marker></defs>',
        '<style>text{font-family:"Noto Sans CJK SC",sans-serif;fill:#17243b}</style>',
        f'<rect width="{width}" height="{height}" fill="white"/>',
    ]

    def text(x, y, label, size=font_size, anchor='middle', weight=500):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{escape(label)}</text>')

    def actor(x, y, label, index):
        color = '#2563eb' if index < 3 else '#13846d' if index < 5 else '#8056b8'
        fill = '#eff5ff' if index < 3 else '#edf8f4' if index < 5 else '#f5f0fc'
        parts.append(f'<rect x="{x-110}" y="{y}" width="220" height="88" rx="10" fill="{fill}" stroke="{color}" stroke-width="2.5"/>')
        text(x, y + 56, label, 32, weight=600)

    for i, (key, label) in enumerate(participants):
        x = xs[key]
        parts.append(f'<line x1="{x}" y1="138" x2="{x}" y2="{bottom}" stroke="#9aa9bd" stroke-width="2.3" stroke-dasharray="9 8"/>')
        actor(x, 50, label, i)
        actor(x, bottom, label, i)

    for sender, arrow, receiver, label, lines, label_top, y in layouts:
        x1, x2 = xs[sender], xs[receiver]
        dashed = ' stroke-dasharray="10 7"' if arrow == '-->>' else ''
        parts.append(f'<g><title>{escape(label)}</title>')
        if sender == receiver:
            loop = lane_gap - 35
            parts.append(f'<path d="M{x1},{y} H{x1+loop} V{y+40} H{x1}" fill="none" stroke="#334155" stroke-width="3.2"{dashed} marker-end="url(#arrow)"/>')
            label_x = x1 + loop / 2
        else:
            parts.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#334155" stroke-width="3.2"{dashed} marker-end="url(#arrow)"/>')
            label_x = (x1 + x2) / 2
        for j, line in enumerate(lines):
            label_y = label_top + j * 44
            label_width = measure(line) + 12
            parts.append(f'<rect x="{label_x-label_width/2}" y="{label_y-35}" width="{label_width}" height="45" fill="white"/>')
            text(label_x, label_y, line)
        parts.append('</g>')

    parts.append('</svg>')
    svg = directory / 'task-sequence.svg'
    svg.write_text('\n'.join(parts) + '\n')
    renderer = runpy.run_path('scripts/analysis/render-clientproxy-guide.py')
    png = renderer['render_png'](svg)
    print(json.dumps({'source': str(source), 'svg': str(svg), 'png': str(png),
                      'participants': len(participants), 'messages': len(messages),
                      'width': width, 'height': height, 'message_font_px': font_size,
                      'effective_text_scale_vs_previous': round((font_size / width) / (27 / 2510), 2)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
