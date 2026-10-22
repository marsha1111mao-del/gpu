#!/usr/bin/env python3
"""Audit contemporaneous Native/Realm glmark evidence and summarize matched counts."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import statistics


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def format_score(score):
    return format(Decimal(str(score)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'f')


def verify_collection(folder):
    manifest = load(folder/'collection.json')
    assert manifest['status'] == 'VERIFIED', folder
    for name, expected in manifest['files'].items():
        assert digest(folder/name) == expected, (folder, name, 'SHA mismatch')


def verify_lab_recovery(experiment, run_id):
    lab = experiment.parent/'lab-runs'/run_id
    before, after = load(lab/'before.json'), load(lab/'after.json')
    assert after['role_verified'] and after['role'] == 'rk', run_id
    for key in ('hostname', 'kernel', 'online_cpus', 'gpu_driver'):
        assert after[key] == before[key], (run_id, key)
    assert after['online_cpus'] == '0-1' and after['gpu_driver'].endswith('/pmthor'), run_id
    assert not after['active_lab_processes'], run_id
    assert after['loops']['rc'] == 0 and not after['loops']['stdout'], run_id
    assert after['mounts']['rc'] == 0 and '/root/GPU-SFTP/' not in after['mounts']['stdout'], run_id
    assert after['memory']['MemAvailable'] >= 512*1024**2, run_id


def raw_result(path, size=None):
    data = path.read_text(errors='replace').replace('\r', '').replace('\x00', '')
    scores = re.findall(r'^GLMARK_SCORE=(\d+)\s*$', data, re.M)
    scenes = [(match[1], int(match[2])) for match in re.finditer(
        r'^(\[[^\n]+\].*?)FPS:\s*(\d+)\s+FrameTime:\s*([0-9.]+)', data, re.M)]
    assert len(scores) == 1 and int(scores[0]) > 0 and len(scenes) == 33, path
    if size is not None:
        expected = '1280x720' if size == 720 else '1920x1080'
        assert f'GLMARK_SIZE={expected}' in data, path
    assert 'GLMARK_VALIDATE_SUCCESS=26 FAILURE=1 UNKNOWN=6' in data, path
    assert re.search(r'GLMARK_RENDERER=.*(?:Mali|Panfrost)', data), path
    for marker in ('GLMARK_RESULT=PASS', 'GLMARK_VALIDATE=PASS',
                   'GLMARK_CLEAN_RESULT=PASS', 'PERFORMANCE_CASE_RESULT=PASS'):
        assert marker in data, (path, marker)
    assert not re.search(r'panfrost_batch_submit failed|PANTHOR_BO_CREATE failed|'
                         r'DRM_IOCTL_PANTHOR_VM_BIND failed|MESA: error: export failed', data), path
    return int(scores[0]), scenes


def kernel_health(before_path, after_path):
    before, after = before_path.read_bytes(), after_path.read_bytes()
    assert after.startswith(before), (after_path, 'dmesg ring wrapped')
    assert not re.search(rb'BUG:|Oops:|WARNING:|Unable to handle kernel|Kernel panic|'
                         rb'Out of memory|oom-kill:|job timeout|FW ping timeout|'
                         rb'CSG \d+ update request timedout|TRANSLATION_FAULT',
                         after[len(before):]), after_path


def cpu_counters(text):
    return {line.split()[0]: list(map(int, line.split()[1:9]))
            for line in text.splitlines() if re.match(r'^cpu(?:\d+)? ', line)}


def busy_percent(before, after):
    difference = [last-first for first, last in zip(before, after)]
    assert all(value >= 0 for value in difference), difference
    total = sum(difference)
    assert total > 0
    return 100*(total-difference[3]-difference[4]-difference[7])/total


def observer(experiment, run_id, events, expected_pids, native_cpus=None):
    folder = experiment/'observations'/run_id
    collection = load(folder/'collection.json')
    assert digest(folder/'host-samples.jsonl') == collection['sha256'], folder
    samples = [json.loads(line) for line in (folder/'host-samples.jsonl').read_text().splitlines()]
    start = max(event['start'] for event in events.values())
    end = min(event['end'] for event in events.values())
    selected = [sample for sample in samples if start <= sample['monotonic_ns'] <= end]
    assert len(selected) >= 30, (run_id, len(selected))
    assert selected[-1]['monotonic_ns']-selected[0]['monotonic_ns'] >= .9*(end-start), run_id
    assert all(sample['cpu_min'] == sample['cpu_max'] == '1800000'
               and sample['cpu_khz'] == '1800000' for sample in selected), run_id
    assert all(sample['gpu_selected'] == '600000000' for sample in selected), run_id
    actual = sorted({sample['gpu_actual'] for sample in selected if sample['gpu_actual'] is not None})
    assert actual == ['594000000'], (run_id, actual)
    for process_id, affinity in expected_pids.items():
        tasks = [task for sample in selected for task in sample['tasks']
                 if task['tid'] == process_id]
        assert tasks and all(task['affinity'] == affinity for task in tasks), (run_id, process_id)
    native_processes = {}
    if native_cpus is not None:
        complete = 0
        for sample in selected:
            tasks = [task for task in sample['tasks']
                     if task['name'].startswith('glmark2') and task['pid'] == task['tid']]
            assert all(task['affinity'] in ([2], [3]) for task in tasks), (run_id, tasks)
            if sorted(task['affinity'][0] for task in tasks) == sorted(native_cpus):
                complete += 1
            for task in tasks:
                fields = task['stat'].rsplit(')', 1)[1].split()
                native_processes.setdefault(str(task['pid']), []).append(
                    (sample['monotonic_ns'], int(fields[11])+int(fields[12]), task['affinity']))
        assert complete >= len(selected)-2, (run_id, complete, len(selected))
    before = cpu_counters(selected[0]['proc_stat'])
    after = cpu_counters(selected[-1]['proc_stat'])
    temperatures = [int(value)/1000 for sample in selected
                    for value in sample['thermal'].values() if value is not None]
    return {'window': 'common scoring window; two-second sampling',
            'samples': len(selected), 'gpu_actual_hz': actual,
            'native_observed_processes': {process_id: {'affinity': values[0][2],
                'cpu_ticks': values[-1][1]-values[0][1],
                'seconds': (values[-1][0]-values[0][0])/1e9}
                for process_id, values in native_processes.items()},
            'cpu_busy_percent': {name: busy_percent(before[name], after[name])
                                 for name in before if name in after},
            'maximum_thermal_zone_celsius': max(temperatures) if temperatures else None}


def guest_cpu(path):
    data = path.read_text()
    assert 'XSHM_CPU_SAMPLES_END' in data, path
    samples = [(float(match[1]), list(map(int, match[2].split()))[:8])
               for match in re.finditer(r'REALM_CPU_SAMPLE uptime=([0-9.]+) cpu\s+([0-9 ]+)', data)]
    assert len(samples) >= 30, path
    intervals = [busy_percent(before[1], after[1]) for before, after in zip(samples, samples[1:])]
    return {'window': 'validation plus scoring; not scoring-only', 'samples': len(samples),
            'seconds': samples[-1][0]-samples[0][0],
            'busy_percent': busy_percent(samples[0][1], samples[-1][1]),
            'steal_percent': 100*(samples[-1][1][7]-samples[0][1][7])/
                             sum(last-first for first, last in zip(samples[0][1], samples[-1][1])),
            'intervals_at_least_95_percent': sum(value >= 95 for value in intervals),
            'interval_count': len(intervals)}


def timing_snapshots(path, marker, by_operation=False):
    snapshots = {}
    for match in re.finditer(r'\['+re.escape(marker)+r'\] ([^\r\n]+)', path.read_text()):
        values = {}
        for name, value in re.findall(r'(\w+)=([^\s]+)', match[1]):
            values[name] = int(value, 16 if value.startswith('0x') else 10) if re.fullmatch(
                r'0x[0-9a-fA-F]+|[0-9]+', value) else value
        key = values['op'] if by_operation else marker
        snapshots[key] = values
    assert snapshots, (path, marker)
    return snapshots if by_operation else snapshots[marker]


def diagnostic_timings(folder, count):
    proxy = folder/'realm-0.log'
    return {
        'scope': 'last cumulative snapshot per operation or marker; validation, scoring and teardown',
        'semantics': 'elapsed wall time includes waits and scheduling; overlapping timers are not additive',
        'client_rpc': {str(index): timing_snapshots(folder/f'realm-{index}.log',
                      'CLIENT_COMM_RPC_STATS', by_operation=True) for index in range(1, count+1)},
        'proxy_rpc': timing_snapshots(proxy, 'PANTHOR_PROXY_RPC_STATS', by_operation=True),
        'group_submit': timing_snapshots(proxy, 'PANTHOR_SUBMIT_STATS_GROUP'),
        'vm_bind': timing_snapshots(proxy, 'PANTHOR_SUBMIT_STATS_VMBIND'),
        'run_job': timing_snapshots(proxy, 'PANTHOR_SUBMIT_STATS_RUN_JOB'),
        'job_irq': timing_snapshots(proxy, 'PANTHOR_JOB_IRQ_STATS')}


def audit_realm(experiment, folder, signatures, diagnostic=False):
    verify_collection(folder)
    result = load(folder/'summary.json')
    verify_lab_recovery(experiment, result['run_id'])
    assert load(folder/'lab-result.json')['returncode'] == 0, folder
    assert result['status'] == 'PASS' and result['rpc_stats'] == diagnostic, folder
    assert load(folder/'host-kernel-health.json')['status'] == 'PASS', folder
    lease = load(folder/'lease-monitor.json')
    assert lease['monitor_pass'] and lease['final'] == lease['dma_final'] == lease['errors'] == 0, folder
    count = result['clients']
    assert result['vm_exit_codes'] == [0]*(count+1), folder
    assert len(result['concurrent_glmark']) == count, folder
    assert sorted(client['client'] for client in result['concurrent_glmark']) == list(range(1, count+1)), folder
    assert all(not errors for realm in result['kernel_health'].values() for errors in realm.values()), folder
    assert not any(result.get(key) for key in ('transport_cleanup_errors', 'grant_cleanup_errors',
                                             'host_restore_error')), folder
    assert result['benchmark_overlap']['fraction'] >= .9, folder
    assert result['client_cpu_layout'] == 'round-robin' and result['cpu_frequency_khz'] == 1800000, folder
    assert all(result[key] for key in ('compact_memory', 'telemetry', 'performance',
                                      'benchmark_only', 'suite', 'benchmark_start_barrier')), folder
    size = int(result['profiles'][0].split('-')[1])
    assert result['memory_pages'] == (32768 if size == 720 else 49152), folder
    signature = (result['memory_pages'], tuple(sorted(result['inputs'].items())))
    assert signatures.setdefault(size, signature) == signature, (folder, 'configuration drift')
    expected_pids = {}
    for realm in range(count+1):
        assert not re.search(r'\bjob timeout\b', (folder/f'realm-{realm}.log').read_text()), folder
        threads = result['thread_affinity'][str(realm)]
        expected_cpu = 1 if realm == 0 else 2+(realm-1) % 2
        for thread in threads:
            expected = [expected_cpu] if thread['name'].startswith('fc_vcpu') else [0]
            assert thread['cpus'] == expected, (folder, thread)
            expected_pids[thread['tid']] = expected
        configuration = load(folder/f'realm-{realm}.json')
        if diagnostic:
            parameters = ('panthor.submit_stats=1', 'panthor.job_irq_stats=1',
                          'panthor_proxy.rpc_stats=1') if realm == 0 else (
                          'client_comm_vmshm.rpc_stats=1',)
            assert all(parameter in configuration['boot-source']['boot_args']
                       for parameter in parameters), folder
            markers = ('PANTHOR_PROXY_RPC_STATS', 'PANTHOR_SUBMIT_STATS_GROUP',
                       'PANTHOR_SUBMIT_STATS_VMBIND', 'PANTHOR_SUBMIT_STATS_RUN_JOB',
                       'PANTHOR_JOB_IRQ_STATS') if realm == 0 else ('CLIENT_COMM_RPC_STATS',)
            serial = (folder/f'realm-{realm}.log').read_text()
            assert all(f'[{marker}]' in serial for marker in markers), folder
        pool = 128 if size == 720 else 192
        cma = pool*(count if realm == 0 else 1)+16
        memory = cma+(192+32*count if realm == 0 else 192)
        assert configuration['machine-config']['mem_size_mib'] == memory, folder
        assert f'cma={cma}M swiotlb=8192' in configuration['boot-source']['boot_args'], folder
    scores, scenes = [], []
    for client in result['concurrent_glmark']:
        score, current_scenes = raw_result(folder/f'glmark-{size}-client-{client["client"]}.log', size)
        assert score == client['score'] and client['returncode'] == 0, folder
        scores.append(score)
        scenes.append(current_scenes)
    restored = result['host_performance']
    assert restored['before'] == restored['restored'], folder
    return {'mode': 'realm', 'run_id': result['run_id'], 'round': result['run_id'].rsplit('-', 1)[1],
            'size': size, 'count': count, 'scores': scores, 'mean_score': statistics.mean(scores),
            'overlap': result['benchmark_overlap']['fraction'], 'scenes': scenes,
            'observer': observer(experiment, result['run_id'], result['benchmark_events'], expected_pids),
            'guest_cpu': {str(realm): guest_cpu(folder/f'cpu-realm-{realm}.log')
                          for realm in range(count+1)},
            **({'timings': diagnostic_timings(folder, count)} if diagnostic else {})}


def audit_native(experiment, folder):
    verify_collection(folder)
    result = load(folder/'summary.json')
    verify_lab_recovery(experiment, result['run_id'])
    assert result['status'] in ('PASS', 'FAIL') and 1 <= len(result['cases']) <= 8, folder
    expected = ([(size, count) for size in (720, 1080) for count in (1, 2, 3, 4)]
                if result['round'] == 'a' else
                [(720, count) for count in (4, 3, 2, 1)]+[(1080, count) for count in (3, 2, 1, 4)])
    planned = [tuple(case) for case in result.get('planned_cases', expected)]
    assert planned and planned == [case for case in expected if case in planned], folder
    attempted = [(case['size'], case['count']) for case in result['cases']]
    assert attempted == planned[:len(attempted)], folder
    assert result['status'] != 'PASS' or len(attempted) == len(planned), folder
    assert not result['cleanup_failures'], folder
    assert load(folder/'rootfs-after.json')['sha256'] == result['rootfs_sha256'], folder
    assert result['runner_sha256'] in {digest(experiment/name)
        for name in ('native-runner.py', 'native-runner-v3.py', 'native-runner-v4.py')
        if (experiment/name).exists()}, folder
    for name, filename in (('root/gpu-smoke.sh', 'gpu-smoke.sh'),
                           ('tmp/performance-suite.sh', 'performance-suite.sh')):
        assert result['userspace_hashes'][name] == digest(experiment/'bundle'/filename), folder
    lab = experiment.parent/'lab-runs'/result['run_id']
    returncode = load(lab/'result.json')['returncode']
    assert (returncode == 0) == (result['status'] == 'PASS'), folder
    restoration = load(lab/'native-mode.json')
    assert restoration['config_restore'] == 'PASS' and restoration['status'] == result['status'], folder
    assert 'kvm_arm.mode=nvhe' in result['cmdline'], folder
    assert 'kvm_arm.mode=protected' in restoration['restored']['cmdline'], folder
    assert restoration['restored']['cpus'] == '0-1', folder
    failures = []
    if result['status'] == 'PASS':
        kernel_health(folder/'dmesg-before.log', folder/'dmesg-after.log')
    else:
        assert all(case['status'] == 'PASS' for case in result['cases'][:-1]), folder
        last = result['cases'][-1]
        assert last['status'] == 'FAIL', folder
        assert 'job timeout' in (folder/'dmesg-after.log').read_text(), folder
        failures.append({'mode': 'native', 'run_id': result['run_id'], 'case_id': last['case_id'],
            'size': last['size'], 'count': last['count'], 'round': result['round'],
            'status': 'FAIL', 'reason': 'GPU job timeout; all scores of this case excluded',
            'batch_returncode': returncode})
    assert (lab/'extlinux-before.conf').read_bytes() == (experiment.parent/'lab-runs'/
        'fair-native-nvhe-20261021-a'/'extlinux-before.conf').read_bytes(), folder
    entries = []
    for case in result['cases']:
        if case['status'] != 'PASS':
            break
        assert case['status'] == 'PASS' and case['overlap']['fraction'] >= .9, folder
        assert len(case['processes']) == case['count'], folder
        assert sorted(process['index'] for process in case['processes']) == list(range(case['count'])), folder
        kernel_health(folder/case['case_id']/'dmesg-before.log', folder/case['case_id']/'dmesg-after.log')
        kernel_health(folder/'dmesg-before.log', folder/case['case_id']/'dmesg-after.log')
        scores, scenes = [], []
        for process in case['processes']:
            score, current_scenes = raw_result(folder/case['case_id']/f'process-{process["index"]}.log', case['size'])
            assert process['returncode'] == 0 and process['score'] == score, folder
            assert process['cpu'] == 2+process['index'] % 2, folder
            scores.append(score)
            scenes.append(current_scenes)
        entries.append({'mode': 'native', 'run_id': result['run_id'], 'case_id': case['case_id'],
            'round': result['round'], 'size': case['size'], 'count': case['count'],
            'scores': scores, 'mean_score': statistics.mean(scores), 'scenes': scenes,
            'batch_status': result['status'], 'batch_returncode': returncode,
            'acceptance': 'individual case passed with clean kernel history before any later failure',
            'overlap': case['overlap']['fraction'],
            'observer': observer(experiment, result['run_id'], case['events'], {},
                                 [process['cpu'] for process in case['processes']])})
    return entries, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    for name, expected in load(args.experiment/'controller-hashes-v2.json').items():
        assert digest(args.experiment/name) == expected, ('controller drift', name)
    for name, expected in load(args.experiment/'controller-hashes-v3.json').items():
        assert digest(args.experiment/name) == expected, ('controller drift', name)
    if (args.experiment/'controller-hashes-v4.json').exists():
        for name, expected in load(args.experiment/'controller-hashes-v4.json').items():
            assert digest(args.experiment/name) == expected, ('controller drift', name)
    for name, expected in load(args.experiment/'bundle/hashes.json').items():
        assert digest(args.experiment/'bundle'/name) == expected, ('bundle drift', name)
    entries, signatures, excluded, native_signatures, failures = [], {}, [], set(), []
    diagnostics = []
    native_rootfs_hashes = set()
    for mode in ('native', 'realm'):
        for folder in sorted((args.experiment/mode).glob('*')):
            result = load(folder/'summary.json')
            if mode == 'realm' and result.get('rpc_stats') and result['status'] == 'PASS':
                diagnostics.append(audit_realm(args.experiment, folder, signatures, diagnostic=True))
                continue
            if result.get('rpc_stats') or (result['status'] != 'PASS' and
                not (mode == 'native' and result.get('cases') and result.get('rootfs_sha256'))):
                excluded.append({'run_id': result['run_id'], 'status': result['status'],
                                 'error': result.get('error'), 'diagnostic': result.get('rpc_stats', False)})
                continue
            if mode == 'native':
                native_signatures.add((result['uname'], result['cmdline'], result['panthor_module_sha256'],
                                       tuple(sorted(result['userspace_hashes'].items()))))
                accepted, failed = audit_native(args.experiment, folder)
                native_rootfs_hashes.add(result['rootfs_sha256'])
                entries.extend(accepted)
                failures.extend(failed)
            else:
                entries.append(audit_realm(args.experiment, folder, signatures))
    assert len(native_signatures) <= 1, 'Native binary/configuration drift between rounds'
    rootfs_hashes = {digest_value for signature in signatures.values()
                    for name, digest_value in signature[1] if name.endswith('rootfs-panfrost.ext4')}
    rootfs_hashes.update(native_rootfs_hashes)
    assert len(rootfs_hashes) <= 1, 'Native/Realm rootfs mismatch'
    if entries:
        scene_names = [scene[0] for scene in entries[0]['scenes'][0]]
        assert all([scene[0] for scene in scenes] == scene_names
                   for entry in entries for scenes in entry['scenes']), 'scene order mismatch'
    cells, missing = [], []
    for size in (720, 1080):
        for count in range(1, 5):
            cell = {'size': size, 'count': count}
            for mode in ('native', 'realm'):
                runs = [entry for entry in entries if (entry['size'], entry['count'], entry['mode']) ==
                        (size, count, mode)]
                rounds = [entry['round'] for entry in runs]
                failed_rounds = [entry['round'] for entry in failures
                                 if (entry['size'], entry['count'], entry['mode']) == (size, count, mode)]
                attempted = rounds+failed_rounds
                assert len(set(attempted)) == len(attempted), (size, count, mode, attempted)
                if sorted(attempted) != ['a', 'b']:
                    missing.append({'size': size, 'count': count, 'mode': mode,
                                    'rounds_found': rounds, 'failed_rounds': failed_rounds})
                means = [entry['mean_score'] for entry in runs]
                cell[mode] = {'rounds': rounds, 'failed_rounds': failed_rounds, 'round_mean_scores': means,
                              'mean_score': statistics.mean(means) if means else None,
                              'round_sample_stddev': statistics.stdev(means) if len(means) > 1 else None,
                              'minimum_process_score': min(score for entry in runs for score in entry['scores'])
                                                       if runs else None,
                              'maximum_process_score': max(score for entry in runs for score in entry['scores'])
                                                       if runs else None}
            native, realm = cell['native']['mean_score'], cell['realm']['mean_score']
            cell['retained_percent'] = 100*realm/native if native and realm and all(
                len(cell[mode]['rounds']) == 2 for mode in ('native', 'realm')) else None
            cells.append(cell)
    assert len(diagnostics) <= 1, 'duplicate diagnostic runs'
    if diagnostics:
        assert (diagnostics[0]['size'], diagnostics[0]['count']) == (1080, 4)
    diagnostic_missing = not diagnostics
    assert args.allow_incomplete or not missing and not diagnostic_missing, (missing, diagnostic_missing)
    args.output.mkdir(parents=True, exist_ok=True)
    output = {'status': 'INCOMPLETE' if missing or diagnostic_missing else (
              'VERIFIED_WITH_FAILURES' if failures else 'VERIFIED'),
              'missing': missing,
              'diagnostic_missing': diagnostic_missing, 'diagnostics': diagnostics,
              'excluded': excluded, 'failed_cases': failures, 'cells': cells, 'entries': entries}
    (args.output/'audit.json').write_text(json.dumps(output, indent=2)+'\n')
    lines = [f'状态：{output["status"]}。每格按两轮各进程/Client均分的均值统计。', '',
             'Native使用nVHE，Realm使用protected hVHE；同一Host镜像、固件、rootfs、',
             'CPU/GPU频率和工作负载。模式差异计入整个执行栈，不能单独归因于Proxy。', '',
             '| 分辨率 / 并发数 | Native 分数 | Clientproxy 分数 | 分数保留比例 |',
             '| --- | --- | --- | --- |']
    for cell in cells:
        rendered = []
        for mode in ('native', 'realm'):
            item = cell[mode]
            if item['failed_rounds']:
                rendered.append(f'失败（{len(item["failed_rounds"])}轮GPU超时；'
                                f'{len(item["rounds"])}轮通过）')
            else:
                rendered.append(f'{format_score(item["mean_score"])}（{len(item["rounds"])}轮）'
                                if item['mean_score'] is not None else '未完成')
        ratio = f'{cell["retained_percent"]:.2f}%' if cell['retained_percent'] is not None else '—'
        size = '1280×720' if cell['size'] == 720 else '1920×1080'
        lines.append(f'| {size}（{cell["count"]}） | {rendered[0]} | {rendered[1]} | {ratio} |')
    lines += ['', '各Client共享GPU且Client vCPU仅使用CPU2/3。仅在整套评分入口同步，',
              '没有逐场景屏障；分数之和不能当作总吞吐。', '',
              '| 模式 | run-id / case | 各进程或Client分数 | 共同计分窗口 |',
              '| --- | --- | --- | --- |']
    for entry in entries:
        lines.append(f'| {entry["mode"]} | {entry.get("case_id", entry["run_id"])} | '
                     f'{" / ".join(map(str, entry["scores"]))} | {100*entry["overlap"]:.2f}% |')
    lines += ['', 'Native按独立case验收：后续case失败不会追溯改写此前已完成且完整内核历史',
              '无异常的case；批次仍保留FAIL及非零退出码。失败case内所有进程分数均排除。']
    for failure in failures:
        lines.append(f'- {failure["run_id"]} / {failure["case_id"]}: FAIL，'
                     f'{failure["reason"]}，批次rc{failure["batch_returncode"]}。')
    lines += ['', 'Host采样中的vCPU满载可能包含忙等。Guest忙碌比例排除idle、iowait和steal，',
              '仍可能包含Guest驱动轮询；其窗口覆盖validation加评分，',
              '不是精确评分窗口。频率恒定也不能证明GPU满载。', '',
              '| Realm run-id | Proxy Guest忙碌比例 | 各Client Guest忙碌比例 |',
              '| --- | --- | --- |']
    for entry in entries:
        if entry['mode'] == 'realm':
            guest = entry['guest_cpu']
            clients = ' / '.join(f'{guest[str(index)]["busy_percent"]:.2f}%'
                                 for index in range(1, entry['count']+1))
            lines.append(f'| {entry["run_id"]} | {guest["0"]["busy_percent"]:.2f}% | {clients} |')
    lines += ['', 'RPC/提交/IRQ诊断单列，不计入正式分数或两轮均值。']
    if diagnostic_missing:
        lines.append('诊断：尚未完成独立核验。')
    for entry in diagnostics:
        lines.append(f'诊断：{entry["run_id"]}，完整正确性、健康、恢复、采样及计时日志核验通过；'
                     f'各Client分数{" / ".join(map(str, entry["scores"]))}，仅供诊断。')
    (args.output/'audit.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status': output['status'], 'audited_cases': len(entries),
                      'failed_cases': len(failures), 'missing_cells': len(missing),
                      'diagnostic_runs': len(diagnostics)}))


if __name__ == '__main__':
    main()
