#!/usr/bin/env python3
"""Summarize verified concurrent ML runs against recorded Native latency."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]


def read_collected(directory):
    collected = json.loads((directory/'collection.json').read_text())
    assert collected['status'] == 'VERIFIED', directory
    for name, digest in collected['files'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest() == digest, name
    return json.loads((directory/'summary.json').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--not-run', nargs='*', type=Path, default=[], help='Verified runs rejected before boot for insufficient memory')
    parser.add_argument('--failed-case', nargs=2, action='append', default=[], metavar=('DIRECTORY', 'PROFILE'),
                        help='Record a collected GPU submission failure without accepting timings from its batch')
    parser.add_argument('--invalid-case', nargs=2, action='append', default=[], metavar=('DIRECTORY', 'PROFILE'),
                        help='Record an attempted case from a batch with GPU errors, without accepting its timing')
    args = parser.parse_args()
    historical = json.loads((ROOT/'docs/shared/evidence/native-proxyclient-summary-20261018/metrics.json').read_text())
    native = {entry['name']: entry for entry in historical['rows']
              if entry['group'] in ('ML/Attention', 'ML', 'NCNN')}
    rows = []
    runs = []
    for directory in args.runs:
        summary = read_collected(directory)
        lab = json.loads((directory/'lab-result.json').read_text())
        health = json.loads((directory/'host-kernel-health.json').read_text())
        leases = json.loads((directory/'lease-monitor.json').read_text())
        measurement_failures = [case['profile'] for case in summary['concurrent_ml']
                                if case.get('status') == 'FAIL_NO_OVERLAP']
        assert summary['status'] == ('FAIL' if measurement_failures else 'PASS'), directory
        assert 'error' not in summary, directory
        assert lab['status'] == ('FAILED' if measurement_failures else 'COMPLETED'), directory
        assert health['status'] == 'PASS' and leases['monitor_pass'], directory
        assert summary['vm_exit_codes'] == [0] * (summary['clients'] + 1), directory
        assert not any(any(issues.values()) for issues in summary['kernel_health'].values()), directory
        for realm in range(summary['clients'] + 1):
            serial = (directory/f'realm-{realm}.log').read_text(errors='replace')
            assert 'job timeout' not in serial and 'reason=job-timeout' not in serial, directory
        assert summary['host_performance']['before'] == summary['host_performance']['restored'], directory
        assert not any(summary.get(key) for key in ('transport_cleanup_errors', 'grant_cleanup_errors', 'host_restore_error')), directory
        assert leases['workload_returncode'] == (1 if measurement_failures else 0), directory
        assert leases['final'] == leases['dma_final'] == leases['errors'] == 0, directory
        samples = [json.loads(line) for line in (directory/'memory-samples.jsonl').read_text().splitlines()]
        runs.append({'run_id': summary['run_id'], 'clients': summary['clients'],
                     'status': summary['status'], 'measurement_failures': measurement_failures,
                     'profiles': summary['profiles'],
                     'memory_plan': summary['memory_plan'], 'lease_peak_pages': leases['peak'],
                     'host_min_available_mib': min(sample['available_kib'] for sample in samples)/1024,
                     'evidence': str(directory.resolve()), 'inputs': summary['inputs']})
        for case in summary['concurrent_ml']:
            status = case.get('status', 'PASS')
            assert case['barrier'] and status in ('PASS', 'FAIL_NO_OVERLAP'), case
            assert (case['overlap']['common_seconds'] > 0) == (status == 'PASS'), case
            assert len(case['clients']) == summary['clients'], case
            names = set(case['clients'][0]['metrics_ms'])
            assert all(set(client['metrics_ms']) == names for client in case['clients']), case
            for client in case['clients']:
                assert client['returncode'] == 0 and client['pass_marker'] and not client['errors'], client
            for name in sorted(names):
                values = [client['metrics_ms'][name] for client in case['clients']]
                original = native[name]
                average = statistics.mean(values)
                rows.append({'name': name, 'profile': case['profile'], 'clients': summary['clients'], 'status': status,
                             'native_ms': original['native'], 'native_run_id': original['native_run_id'],
                             'client_ms': values, 'mean_ms': average,
                             'performance_retention_pct': original['native']/average*100 if status == 'PASS' else None,
                             'run_id': summary['run_id'], 'overlap': case['overlap']})
    unexecuted = []
    for directory in args.not_run:
        summary = read_collected(directory)
        memory = summary['memory_plan']
        leases = json.loads((directory/'lease-monitor.json').read_text())
        health = json.loads((directory/'host-kernel-health.json').read_text())
        assert summary['status'] == 'FAIL' and summary['vm_exit_codes'] == [], directory
        assert sum(memory['realm_mib']) + memory['host_headroom_mib'] > memory['available_mib'], directory
        assert leases['monitor_pass'] and leases['peak'] == 0 and health['status'] == 'PASS', directory
        assert summary['profiles'] == ['ncnn-resnet50'], directory
        original = native['ncnn-resnet50']
        unexecuted.append({'run_id': summary['run_id'], 'memory_plan': memory,
                           'evidence': str(directory.resolve()), 'reason': 'Memory admission rejected before any Realm boot'})
        rows.append({'name': 'ncnn-resnet50', 'profile': 'ncnn-resnet50', 'clients': summary['clients'],
                     'status': 'NOT_RUN_MEMORY_ADMISSION', 'native_ms': original['native'],
                     'native_run_id': original['native_run_id'], 'client_ms': [], 'mean_ms': None,
                     'performance_retention_pct': None, 'run_id': summary['run_id']})
    failed_cases = []
    for directory_name, profile in args.failed_case:
        directory = Path(directory_name)
        summary = read_collected(directory)
        lab = json.loads((directory/'lab-result.json').read_text())
        assert summary['status'] == 'FAIL' and summary.get('error'), directory
        assert lab['status'] == 'FAILED' and lab['returncode'] != 0, directory
        cases = [case for case in summary['concurrent_ml'] if case['profile'] == profile]
        assert len(cases) == 1 and cases[0]['clients'], directory
        case = cases[0]
        gpu_errors = ('MESA: error:', 'VK_ERROR_', 'vkWaitForFences failed',
                      'PANTHOR_BO_CREATE failed', 'DRM_IOCTL_PANTHOR_VM_BIND failed')
        assert any(any(marker in error for marker in gpu_errors)
                   for client in case['clients'] for error in client.get('errors', [])), case
        names = set(case['clients'][0]['metrics_ms'])
        assert names, case
        failed_cases.append({'run_id': summary['run_id'], 'profile': profile,
                             'evidence': str(directory.resolve()), 'error': summary['error'],
                             'vm_exit_codes': summary['vm_exit_codes'],
                             'transport_cleanup_errors': summary.get('transport_cleanup_errors', [])})
        for name in sorted(names):
            original = native[name]
            rows.append({'name': name, 'profile': profile, 'clients': summary['clients'],
                         'status': 'FAIL_GPU_SUBMIT', 'native_ms': original['native'],
                         'native_run_id': original['native_run_id'], 'client_ms': [], 'mean_ms': None,
                         'performance_retention_pct': None, 'run_id': summary['run_id']})
    invalid_cases = []
    for directory_name, profile in args.invalid_case:
        directory = Path(directory_name)
        summary = read_collected(directory)
        assert summary['status'] == 'FAIL' and summary.get('error'), directory
        assert 'job timeout' in (directory/'failure-kernel-0.log').read_text(errors='replace'), directory
        cases = [case for case in summary['concurrent_ml'] if case['profile'] == profile]
        assert len(cases) == 1 and cases[0].get('status') in ('PASS', 'FAIL_NO_OVERLAP'), directory
        case = cases[0]
        assert len(case['clients']) == summary['clients']
        status = 'FAIL_NO_OVERLAP' if case['status'] == 'FAIL_NO_OVERLAP' else 'INVALID_GPU_BATCH'
        invalid_cases.append({'run_id': summary['run_id'], 'profile': profile,
                              'evidence': str(directory.resolve()), 'status': status})
        for name in sorted(case['clients'][0]['metrics_ms']):
            original = native[name]
            rows.append({'name': name, 'profile': profile, 'clients': summary['clients'],
                         'status': status, 'native_ms': original['native'],
                         'native_run_id': original['native_run_id'], 'client_ms': [], 'mean_ms': None,
                         'performance_retention_pct': None, 'run_id': summary['run_id']})
    identities = [(entry['name'], entry['clients']) for entry in rows]
    assert len(set(identities)) == len(identities), 'Duplicate workload/Client-count rows'
    rows.sort(key=lambda entry: (entry['name'], entry['clients'], entry['run_id']))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'metrics.json').write_text(json.dumps({'native_provenance': 'Historical single process, Host #7; current Host #31; not a same-configuration Native rerun',
        'retention_formula': 'Native latency / mean Client latency * 100; lower latency is better',
        'overlap_scope': 'Per-row observation_clock describes the measured window; legacy/NCNN use complete workload, warmup-barrier kernels use timed iterations',
        'invalid_measurements': 'FAIL_NO_OVERLAP retains raw latency but has no performance ratio and cannot qualify a concurrent performance result',
        'ncnn_scope': 'Random input/weights; GPU backend timing, not model accuracy',
        'runs': runs, 'unexecuted': unexecuted, 'failed_cases': failed_cases,
        'invalid_cases': invalid_cases, 'rows': rows}, indent=2)+'\n')
    table = ['| 测试 | Client 数 | Native 耗时 ms（历史单进程） | Clientproxy 耗时 ms（均值；各 Client） | 性能保留比例 |',
             '| --- | --- | --- | --- | --- |']
    for entry in rows:
        if entry['status'] != 'PASS':
            labels = {'NOT_RUN_MEMORY_ADMISSION': '未执行（内存准入拒绝）',
                      'FAIL_NO_OVERLAP': '无效（未观测到公共窗口）',
                      'FAIL_GPU_SUBMIT': '失败（GPU 提交错误）',
                      'INVALID_GPU_BATCH': '无效（整轮 GPU 出错）'}
            label = labels[entry['status']]
            table.append(f"| {entry['name']} | {entry['clients']} | {entry['native_ms']:.3f} | {label} | — |")
            continue
        values = ' / '.join(f'{value:.3f}' for value in entry['client_ms'])
        table.append(f"| {entry['name']} | {entry['clients']} | {entry['native_ms']:.3f} | {entry['mean_ms']:.3f}（{values}） | {entry['performance_retention_pct']:.2f}% |")
    (args.output/'results.md').write_text('\n'.join(table)+'\n')
    print(f'VERIFIED {len(runs)} completed runs, {len(unexecuted)} admission rejections, {len(failed_cases)} GPU failure cases, {len(rows)} workload/client-count rows')


if __name__ == '__main__':
    main()
