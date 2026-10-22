#!/usr/bin/env python3
"""Summarize complete concurrent Realm glmark runs without treating score sums as throughput."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def describe(values):
    mean = statistics.mean(values)
    deviation = statistics.stdev(values) if len(values) > 1 else None
    return {'count': len(values), 'mean': mean, 'min': min(values), 'max': max(values),
            'sample_stddev': deviation,
            'cv_percent': deviation / mean * 100 if deviation is not None and mean else None}


def summarize(paths):
    groups = {}
    failures = []
    identities = set()
    configuration = None
    for path in paths:
        result = json.loads((path/'summary.json').read_text())
        if result['run_id'] in identities:
            raise ValueError('duplicate run: '+result['run_id'])
        identities.add(result['run_id'])
        lab = json.loads((path/'lab-result.json').read_text())
        host = json.loads((path/'host-kernel-health.json').read_text())
        if result['status'] != 'PASS' or lab['returncode'] or host['status'] != 'PASS':
            failures.append({'run_id': result['run_id'], 'path': str(path),
                             'error': result.get('error'), 'lab': lab['status']})
            continue
        clients = result['concurrent_glmark']
        count = result['clients']
        if len(clients) != count or len(set(client['client'] for client in clients)) != count:
            raise ValueError('missing or duplicate Client results: '+result['run_id'])
        if any(client['returncode'] or not client['pass_marker'] or len(client['scenes']) != 33
               or client['validation'] != [26, 1, 6] or client['errors'] for client in clients):
            raise ValueError('incomplete glmark result: '+result['run_id'])
        if len(result['vm_exit_codes']) != count+1 or any(result['vm_exit_codes']):
            raise ValueError('unclean Realm exits: '+result['run_id'])
        if any(result.get(key) for key in ('transport_cleanup_errors', 'grant_cleanup_errors', 'host_restore_error')):
            raise ValueError('incomplete cleanup: '+result['run_id'])
        if result['benchmark_overlap']['fraction'] < 0.9:
            raise ValueError('insufficient concurrent window: '+result['run_id'])
        signature = {'memory_pages': result['memory_pages'],
                     'profiles': result.get('profiles'),
                     'performance': result['performance'],
                     'compact_memory': result['compact_memory'],
                     'benchmark_start_barrier': bool(result.get('benchmark_start_barrier')),
                     'separate_vmm_io': bool(result.get('thread_affinity')),
                     'input_hashes': sorted(result['inputs'].values())}
        if configuration is not None and signature != configuration:
            raise ValueError('different input or placement configurations; summarize separately')
        configuration = signature
        scores = [client['score'] for client in clients]
        samples = [json.loads(line) for line in (path/'memory-samples.jsonl').read_text().splitlines()]
        entry = {'run_id': result['run_id'], 'path': str(path), 'scores': scores,
                 'mean_score': statistics.mean(scores), 'score_sum_index': sum(scores),
                 'jain_score_index': sum(scores)**2/(count*sum(score**2 for score in scores)),
                 'overlap': result['benchmark_overlap'],
                 'minimum_available_mib': min(sample['available_kib'] for sample in samples)/1024,
                 'clients': clients, 'inputs': result['inputs'],
                 'memory_pages': result['memory_pages']}
        groups.setdefault(str(count), []).append(entry)
    summary = {'groups': {}, 'failures': failures,
               'profile': configuration['profiles'][0] if configuration else None}
    baseline = statistics.mean(run['mean_score'] for run in groups['1']) if '1' in groups else None
    for count, runs in sorted(groups.items(), key=lambda item: int(item[0])):
        mean_scores = describe([run['mean_score'] for run in runs])
        summary['groups'][count] = {'runs': runs, 'round_mean_scores': mean_scores,
            'all_client_scores': describe([score for run in runs for score in run['scores']]),
            'retained_percent': mean_scores['mean']/baseline*100 if baseline else None,
            'score_sum_index_mean': statistics.mean(run['score_sum_index'] for run in runs),
            'minimum_available_mib': min(run['minimum_available_mib'] for run in runs),
            'minimum_overlap_percent': min(run['overlap']['fraction'] for run in runs)*100,
            'mean_jain_score_index': statistics.mean(run['jain_score_index'] for run in runs)}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.runs)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'statistics.json').write_text(json.dumps(summary, indent=2)+'\n')
    size = '1920×1080' if summary['profile'] == 'glmark-1080' else '1280×720'
    lines = ['# 多 Client 并行 glmark 统计', '',
             f'完整{size}、33场景、null-noop/finish。每个Client独立Realm和资源池，共享一个可信Proxy与GPU。', '',
             '分数不是屏幕FPS；分数之和只作为聚合评分指数，不代表严格系统吞吐。Jain指数只描述评分均衡性。', '',
             '| Client数 | 独立轮数 | 每轮Client均分的均值 | 轮间样本标准差 | 相对单Client | 聚合评分指数 | 最低可用内存MiB | 最小窗口重叠 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for count, group in summary['groups'].items():
        scores = group['round_mean_scores']
        deviation = f"{scores['sample_stddev']:.2f}" if scores['sample_stddev'] is not None else '未测重复性'
        retained = f"{group['retained_percent']:.2f}%" if group['retained_percent'] is not None else '无同期对照'
        lines.append(f"| {count} | {scores['count']} | {scores['mean']:.2f} | {deviation} | {retained} | {group['score_sum_index_mean']:.2f} | {group['minimum_available_mib']:.1f} | {group['minimum_overlap_percent']:.2f}% |")
    lines += ['', '同轮Client共享GPU，不能将同轮的多个Client当成独立重复实验。标准差按独立轮次的Client均分计算。', '',
              '## 各轮分数与证据', '', '| run-id | 各Client分数 | 均分 | Jain评分指数 | 结果 |', '| --- | --- | --- | --- | --- |']
    for group in summary['groups'].values():
        for run in group['runs']:
            lines.append(f"| {run['run_id']} | {', '.join(map(str, run['scores']))} | {run['mean_score']:.2f} | {run['jain_score_index']:.4f} | PASS，外层rc0、Host健康、所有Realm退出0 |")
    for failure in summary['failures']:
        lines.append(f"| {failure['run_id']} | — | — | — | FAIL：{failure['error'] or failure['lab']} |")
    lines += ['', '## 33场景平均FPS', '',
              '各列对该并发数下所有有效轮次和Client的对应场景求算术平均；场景执行未逐项设置跨Realm屏障，不用相加FPS推断吞吐。', '']
    counts = list(summary['groups'])
    lines += ['| 场景 | '+' | '.join(count+' Client' for count in counts)+' |',
              '| --- | '+' | '.join('---' for count in counts)+' |']
    if counts:
        first = summary['groups'][counts[0]]['runs'][0]['clients'][0]['scenes']
        for index, scene in enumerate(first):
            means = []
            for count in counts:
                values = []
                for run in summary['groups'][count]['runs']:
                    for client in run['clients']:
                        current = client['scenes'][index]
                        if current['scene'] != scene['scene']:
                            raise ValueError('scene mismatch')
                        values.append(current['fps'])
                means.append(f'{statistics.mean(values):.2f}')
            lines.append('| '+scene['scene'].replace('|', '\\|')+' | '+' | '.join(means)+' |')
    (args.output/'statistics.md').write_text('\n'.join(lines)+'\n')
    with (args.output/'client-scores.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['clients', 'run_id', 'client', 'score', 'validation_success', 'validation_known_failure', 'validation_unknown'])
        for count, group in summary['groups'].items():
            for run in group['runs']:
                for client in run['clients']:
                    writer.writerow([count, run['run_id'], client['client'], client['score'], *client['validation']])
    print(json.dumps({count: group['round_mean_scores'] for count, group in summary['groups'].items()}, indent=2))


if __name__ == '__main__':
    main()
