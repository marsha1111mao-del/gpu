#!/usr/bin/env python3
"""Audit dynamic-frequency Native runs while retaining historical Clientproxy scores."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import statistics


ROOT = Path(__file__).resolve().parents[2]
HELPERS = runpy.run_path(str(ROOT / 'scripts/analysis/summarize-fair-glmark.py'))
load = HELPERS['load']
digest = HELPERS['digest']
format_score = HELPERS['format_score']
POLICY = {'scaling_min_freq': '1008000', 'scaling_max_freq': '1800000',
          'scaling_governor': 'schedutil'}


def residency(before, after):
    assert before and after, 'frequency residency counters are required'
    initial = {int(line.split()[0]): int(line.split()[1]) for line in before.splitlines()}
    final = {int(line.split()[0]): int(line.split()[1]) for line in after.splitlines()}
    assert initial.keys() == final.keys()
    delta = {frequency: final[frequency] - initial[frequency] for frequency in initial}
    total = sum(delta.values())
    assert total > 0 and all(value >= 0 for value in delta.values())
    return {'percent_by_khz': {frequency: value * 100 / total for frequency, value in delta.items()},
            'time_weighted_khz': sum(frequency * value for frequency, value in delta.items()) / total}


def observe(experiment, run_id, case, samples):
    start = max(event['start'] for event in case['events'].values())
    end = min(event['end'] for event in case['events'].values())
    selected = [sample for sample in samples if start <= sample['monotonic_ns'] <= end]
    assert len(selected) >= 30, (run_id, case['case_id'], 'not enough observations')
    assert selected[-1]['monotonic_ns'] - selected[0]['monotonic_ns'] >= .9 * (end - start)
    assert all(sample['cpu_min'] == '1008000' and sample['cpu_max'] == '1800000'
               and sample['cpu_governor'] == 'schedutil' for sample in selected)
    assert all(sample['gpu_selected'] == '600000000' and sample['gpu_actual'] == '594000000'
               for sample in selected)
    assert all(1008000 <= int(sample['cpu_khz']) <= 1800000 for sample in selected)
    complete = 0
    expected_cpus = sorted(2 + index % 2 for index in range(case['count']))
    for sample in selected:
        tasks = [task for task in sample['tasks']
                 if task['name'].startswith('glmark2') and task['pid'] == task['tid']]
        assert all(task['affinity'] in ([2], [3]) for task in tasks)
        if sorted(task['affinity'][0] for task in tasks) == expected_cpus:
            complete += 1
    assert complete >= len(selected) - 2, (run_id, case['case_id'], 'process affinity coverage')
    return {'samples': len(selected), 'complete_process_samples': complete,
            'scoring_residency': residency(selected[0]['cpu_time_in_state'], selected[-1]['cpu_time_in_state']),
            'maximum_thermal_celsius': max(int(value) / 1000 for sample in selected
                for value in sample['thermal'].values() if value is not None)}


def audit_run(experiment, run):
    run_id = run['run_id']
    folder = experiment / 'native' / run_id
    HELPERS['verify_collection'](folder)
    HELPERS['verify_lab_recovery'](experiment, run_id)
    summary = load(folder / 'summary.json')
    lab = ROOT / 'build/lab-runs' / run_id
    mode = load(lab / 'native-mode.json')
    returncode = load(lab / 'result.json')['returncode']
    assert run['returncode'] == returncode == mode['workload_returncode']
    assert summary['status'] == mode['status'] == ('PASS' if returncode == 0 else 'FAIL')
    assert mode['config_restore'] == 'PASS' and not summary['cleanup_failures']
    assert all(mode['before'][key] == mode['restored'][key]
               for key in ('uname', 'cmdline', 'cpus', 'driver', 'rme_capability'))
    assert (lab / 'extlinux-before.conf').read_bytes().replace(
        b'kvm_arm.mode=protected', b'kvm_arm.mode=nvhe') == (lab / 'extlinux-native.conf').read_bytes()
    assert mode['image_sha256'] == '8c277a621abcc8cf40c2801176f25ca62fff795be6e8a0324e8d64325040999d'
    assert summary['runner_sha256'] == digest(experiment / 'native-runner-v4.py')
    assert summary['rootfs_sha256'] == load(folder / 'rootfs-after.json')['sha256']
    assert summary['rootfs_sha256'] == '5d0c2ec8e5c1830f6a93c39d34bd8ae02a99702792e9e16a9d9034388f606d60'
    assert summary['panthor_module_sha256'] == '2091b3f718dccef040a700bc53fb8e628f24481e28764249adaad6a6e8fa37ac'
    assert summary['userspace_hashes']['root/glmark2/bin/glmark2-es2-null-noop'] == '2251afb6b792c08181e14205756a29c13f8dd15d5a3eb8ab6652efe55a65bb2c'
    for name, key in (('gpu-smoke.sh', 'root/gpu-smoke.sh'), ('performance-suite.sh', 'tmp/performance-suite.sh')):
        assert summary['userspace_hashes'][key] == digest(experiment / 'bundle' / name)
    planned = [tuple(case) for case in summary['planned_cases']]
    attempted = [(case['size'], case['count']) for case in summary['cases']]
    assert attempted and attempted == planned[:len(attempted)]
    assert summary['status'] != 'PASS' or len(attempted) == len(planned)
    observation = experiment / 'observations' / run_id
    assert digest(observation / 'host-samples.jsonl') == load(observation / 'collection.json')['sha256']
    samples = [json.loads(line) for line in (observation / 'host-samples.jsonl').read_text().splitlines()]
    entries = []
    for index, case in enumerate(summary['cases']):
        assert case['policy'] == POLICY
        entry = {'run_id': run_id, 'round': summary['round'], 'size': case['size'],
                 'count': case['count'], 'case_id': case['case_id'],
                 'status': case['status'], 'batch_returncode': returncode}
        if case['status'] == 'PASS':
            HELPERS['kernel_health'](folder / 'dmesg-before.log', folder / case['case_id'] / 'dmesg-after.log')
            HELPERS['kernel_health'](folder / case['case_id'] / 'dmesg-before.log',
                                     folder / case['case_id'] / 'dmesg-after.log')
            assert case['overlap']['fraction'] >= .9
            scores = []
            for process in case['processes']:
                score, scenes = HELPERS['raw_result'](
                    folder / case['case_id'] / f'process-{process["index"]}.log', case['size'])
                assert process['returncode'] == 0 and process['score'] == score
                assert process['cpu'] == 2 + process['index'] % 2 and len(scenes) == 33
                scores.append(score)
            assert len(scores) == case['count'] and statistics.mean(scores) == case['mean_score']
            entry.update(scores=scores, mean_score=case['mean_score'],
                         overlap=case['overlap']['fraction'], observer=observe(experiment, run_id, case, samples))
        else:
            assert index == len(summary['cases']) - 1 and returncode != 0
            cancellation = run.get('scope_cancellation')
            if cancellation and cancellation['case_id'] == case['case_id']:
                assert (case['size'], case['count']) in ((1080, 2), (720, 1))
                assert case.get('error') == 'KeyboardInterrupt()'
                assert cancellation['scoring_started'] is False
                assert not any('start' in event for event in case['events'].values())
                assert load(experiment / cancellation.get('stop_evidence', 'scope-stop.jsonl'))['action'] == 'SIGINT'
                HELPERS['kernel_health'](folder / case['case_id'] / 'dmesg-before.log',
                                         folder / case['case_id'] / 'dmesg-after.log')
                entry.update(status='CANCELED', reason=cancellation['reason'])
                entries.append(entry)
                continue
            before = (folder / case['case_id'] / 'dmesg-before.log').read_bytes()
            after = (folder / case['case_id'] / 'dmesg-after.log').read_bytes()
            assert after.startswith(before), 'failed-case kernel evidence wrapped'
            delta = after[len(before):].decode(errors='replace')
            assert 'job timeout' in delta, 'unclassified failure; inspect before publication'
            assert not re.search(r'BUG:|Oops:|Kernel panic|Out of memory|oom-kill:', delta)
            entry.update(reason='GPU超时，整组分数排除', error=case.get('error'),
                         timeout_lines=[line for line in delta.splitlines() if 'job timeout' in line])
        entries.append(entry)
    if not returncode:
        HELPERS['kernel_health'](folder / 'dmesg-before.log', folder / 'dmesg-after.log')
    return entries


def audit_reused(experiment, specification):
    source = ROOT / specification['experiment']
    run_id = specification['run_id']
    folder = source / 'native' / run_id
    HELPERS['verify_collection'](folder)
    HELPERS['verify_lab_recovery'](source, run_id)
    assert digest(source / 'audit.json') == specification['audit_sha256']
    assert load(source / 'audit.json')['status'] == 'PASS'
    for name, expected in load(source / 'controller-hashes.json').items():
        assert digest(source / name) == expected
    summary = load(folder / 'summary.json')
    anchor = load(experiment / 'native/native-dynamic-a1-20261022/summary.json')
    assert summary['status'] == 'PASS' and not summary['cleanup_failures']
    for key in ('uname', 'cmdline', 'rootfs_sha256', 'panthor_module_sha256', 'userspace_hashes'):
        assert summary[key] == anchor[key], ('reused conditions differ', key)
    assert summary['rootfs_sha256'] == load(folder / 'rootfs-after.json')['sha256']
    assert summary['runner_sha256'] == digest(source / 'native-runner-v4.py')
    lab = ROOT / 'build/lab-runs' / run_id
    mode = load(lab / 'native-mode.json')
    assert load(lab / 'result.json')['returncode'] == mode['workload_returncode'] == 0
    assert mode['status'] == mode['config_restore'] == 'PASS'
    assert mode['image_sha256'] == '8c277a621abcc8cf40c2801176f25ca62fff795be6e8a0324e8d64325040999d'
    assert all(mode['before'][key] == mode['restored'][key]
               for key in ('uname', 'cmdline', 'cpus', 'driver', 'rme_capability'))
    HELPERS['kernel_health'](folder / 'dmesg-before.log', folder / 'dmesg-after.log')
    case = next(case for case in summary['cases'] if case['case_id'] == specification['case_id'])
    assert case['status'] == 'PASS' and case['policy'] == POLICY
    assert case['size'] == specification['size'] == 720 and case['count'] == specification['count'] == 1
    assert len(case['processes']) == 1 and case['overlap']['fraction'] == 1
    process = case['processes'][0]
    score, scenes = HELPERS['raw_result'](folder / case['case_id'] / 'process-0.log', 720)
    assert score == process['score'] == case['mean_score'] == specification['score']
    assert process['returncode'] == 0 and process['cpu'] == 2 and len(scenes) == 33
    HELPERS['kernel_health'](folder / case['case_id'] / 'dmesg-before.log', folder / case['case_id'] / 'dmesg-after.log')
    observations = source / 'observations' / run_id
    assert digest(observations / 'host-samples.jsonl') == load(observations / 'collection.json')['sha256']
    samples = [json.loads(line) for line in (observations / 'host-samples.jsonl').read_text().splitlines()]
    return {'run_id': run_id, 'round': specification['comparison_slot'], 'source_round': summary['round'],
            'size': 720, 'count': 1, 'case_id': case['case_id'], 'status': 'PASS', 'batch_returncode': 0,
            'scores': [score], 'mean_score': score, 'overlap': 1,
            'observer': observe(source, run_id, case, samples), 'reused_historical': True,
            'source_experiment': specification['experiment'], 'source_audit_sha256': specification['audit_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    matrix = load(experiment / 'matrix.json')
    for name, expected in load(experiment / 'controller-hashes.json').items():
        assert digest(experiment / name) == expected, ('controller drift', name)
    reduced_hashes = experiment / 'reduced-controller-hashes.json'
    if reduced_hashes.exists():
        for name, expected in load(reduced_hashes).items():
            assert digest(experiment / name) == expected, ('reduced controller drift', name)
    reuse_hashes = experiment / 'reuse-controller-hashes.json'
    if reuse_hashes.exists():
        for name, expected in load(reuse_hashes).items():
            assert digest(experiment / name) == expected, ('reuse controller drift', name)
    entries = [entry for run in matrix['runs'] for entry in audit_run(experiment, run)]
    entries += [audit_reused(experiment, specification) for specification in matrix.get('historical_reuse', [])]
    measured = [entry for entry in entries if entry['status'] != 'CANCELED']
    indexed = {(entry['size'], entry['count'], entry['round']): entry for entry in measured}
    assert len(indexed) == len(measured), 'duplicate case/round; do not retry to hide failures'
    missing = [(size, count, round_name) for size in (720, 1080) for count in range(1, 5)
               for round_name in ('a', 'b') if (size == 720 or count in (1, 4))
               and (size, count, round_name) not in indexed]
    assert args.allow_incomplete or not missing, ('missing cases', missing)
    reference_path = args.reference / 'analysis-final/audit.json'
    reference = load(reference_path)
    cells = []
    for size in (720, 1080):
        for count in range(1, 5):
            original = next(cell for cell in reference['cells'] if cell['size'] == size and cell['count'] == count)
            historical = [entry for entry in reference['entries']
                          if entry['mode'] == 'realm' and entry['size'] == size and entry['count'] == count]
            assert len(historical) == 2 and {entry['round'] for entry in historical} == {'a', 'b'}
            for entry in historical:
                folder = args.reference / 'realm' / entry['run_id']
                HELPERS['verify_collection'](folder)
                summary = load(folder / 'summary.json')
                assert summary['status'] == 'PASS' and summary['cpu_frequency_khz'] == 1800000
                assert summary['concurrent_glmark'] and not summary['rpc_stats']
            proxy = statistics.mean(entry['mean_score'] for entry in historical)
            assert proxy == original['realm']['mean_score']
            rounds = [indexed.get((size, count, round_name)) for round_name in ('a', 'b')]
            valid = all(entry and entry['status'] == 'PASS' for entry in rounds)
            mean = statistics.mean(entry['mean_score'] for entry in rounds) if valid else None
            if mean is not None:
                label = format_score(mean)
                if any(entry.get('reused_historical') for entry in rounds):
                    label += '（含历史复用）'
            else:
                label = ('未完成（' if any(entry is None for entry in rounds) else '失败（') + '，'.join(
                    f'{round_name.upper()}{"通过" if entry and entry["status"] == "PASS" else "GPU超时" if entry else "未执行"}'
                    for round_name, entry in zip(('a', 'b'), rounds)) + '）'
            fixed = original['native'].get('mean_score') if (
                len(original['native']['rounds']) == 2 and not original['native']['failed_rounds']) else None
            retained = size == 1080 and count in (2, 3)
            used_mean = mean
            if retained:
                assert all(entry is None for entry in rounds) and fixed is not None
                used_mean = fixed
                label = format_score(fixed) + '（固定频率历史值，未复测）'
            cells.append({'size': size, 'count': count, 'native_label': label,
                          'native_dynamic_mean': mean, 'clientproxy_historical_mean': proxy,
                          'native_used_mean': used_mean, 'native_retained_historical': retained,
                          'retention_pct': proxy / used_mean * 100 if used_mean else None,
                          'native_fixed_reference': fixed,
                          'native_delta_from_fixed': mean - fixed if mean is not None and fixed is not None else None,
                          'native_change_from_fixed_pct': (mean / fixed - 1) * 100 if mean is not None and fixed else None,
                          'rounds': rounds})
    table = ['| 分辨率 / 并发数 | Native 分数 | Clientproxy 分数 | 分数保留比例 |',
             '| --- | --- | --- | --- |']
    for cell in cells:
        resolution = '1280×720' if cell['size'] == 720 else '1920×1080'
        count = cell['count']
        label = '1 Client' if count == 1 else f'{count} Client 并发'
        retention = format_score(cell['retention_pct']) + '%' if cell['retention_pct'] is not None else '—'
        table.append(f'| {resolution}（{label}） | {cell["native_label"]} | '
                     f'{format_score(cell["clientproxy_historical_mean"])} | {retention} |')
    status = 'INCOMPLETE' if missing else 'VERIFIED_WITH_FAILURES' if any(entry['status'] == 'FAIL' for entry in entries) else 'VERIFIED'
    report = {'status': status, 'missing': missing, 'entries': entries, 'cells': cells,
              'measurement_counts': {'new_valid': sum(entry['status'] == 'PASS' and not entry.get('reused_historical') for entry in entries),
                                     'historical_reused': sum(bool(entry.get('reused_historical')) for entry in entries),
                                     'canceled_before_scoring': sum(entry['status'] == 'CANCELED' for entry in entries)},
              'reference_audit_sha256': digest(reference_path),
              'analysis_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': '720p 1–4 processes and 1080p 1/4 processes, A/B; 1080p 2/3 retain fixed-frequency historical Native',
              'conditions': 'Retested Native schedutil 1008–1800MHz; Clientproxy historical fixed 1800MHz; GPU594MHz',
              'table_markdown': '\n'.join(table)}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'table.md').write_text(report['table_markdown'] + '\n')
    print(status, 'valid', sum(entry['status'] == 'PASS' for entry in entries),
          'failed', sum(entry['status'] == 'FAIL' for entry in entries), 'missing', len(missing))
    print(report['table_markdown'])


if __name__ == '__main__':
    main()
