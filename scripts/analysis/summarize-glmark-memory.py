#!/usr/bin/env python3
"""Audit sampled glmark task memory without counting shared BO pages twice."""
import argparse
import json
from pathlib import Path
import re
import runpy

ROOT = Path(__file__).resolve().parents[2]
HELPERS = runpy.run_path(str(ROOT / 'scripts/analysis/summarize-fair-glmark.py'))


def load(path):
    return json.loads(path.read_text())


def counters(text):
    return {name: int(value) for name, value in re.findall(r'(\w+)=(\d+)', text)}


def samples(path):
    readings = []
    for line in path.read_text(errors='replace').splitlines():
        if 'MEM_SAMPLE ' not in line:
            continue
        record = counters(line)
        record['stage'] = re.search(r'\bstage=(\S+)', line)[1]
        record['cpu_bytes'] = 1024 * (record['task_Pss_Anon_sum'] + record['task_Pss_File_sum'])
        readings.append(record)
    assert readings, path
    return readings


def audit_shared(directory, experiment, bundle):
    HELPERS['verify_collection'](directory)
    summary = load(directory / 'summary.json')
    run_id = summary['run_id']
    lab = experiment.parent / 'lab-runs' / run_id
    assert load(lab / 'result.json')['returncode'] == 0
    HELPERS['verify_lab_recovery'](experiment, run_id)
    assert summary['status'] == 'PASS'
    manifest = load(bundle / 'hashes.json')
    for name, suffix in (('runner.py', 'tests/realm-xshm/run-realms.py'),
                         ('client-Image', 'firecracker-bins/kernels/realm-xshm/Image'),
                         ('proxy-Image', 'firecracker-bins/kernels/realm-xshm/proxy/Image'),
                         ('initrd.cpio', 'firecracker-bins/kernels/realm-xshm/initrd.cpio')):
        assert summary['inputs']['/root/GPU-SFTP/' + suffix] == manifest[name]
    assert all(not issues for realm in summary['kernel_health'].values() for issues in realm.values())
    assert not any(summary.get(name) for name in ('transport_cleanup_errors', 'grant_cleanup_errors', 'host_restore_error'))
    assert summary['host_performance']['before'] == summary['host_performance']['restored']
    count = summary['clients']
    assert summary['vm_exit_codes'] == [0] * (count + 1)
    assert not any(summary[name] for name in ('rpc_stats', 'notify_trace', 'completion_trace'))
    assert load(lab / 'host-kernel-health.json')['status'] == 'PASS'
    lease = load(lab / 'lease-monitor.json')
    assert lease['monitor_pass'] and lease['workload_returncode'] == 0
    reclaim = load(lab / 'gmem-reclaim.json')
    assert reclaim['status'] == 'PASS' and reclaim['workload_returncode'] == 0
    assert len(reclaim['readings']) == 2 * count
    pool_bytes = summary['memory_pages'] * 4096 * count
    target_bytes = 0
    for reading in reclaim['readings']:
        values = counters(reading['reading'])
        assert values['requested_pages'] == summary['memory_pages']
        if reading['member']:
            assert values['cached_pages'] == values['cache_only_pages'] == 0
            target_bytes += values['cached_pages'] * 4096
        else:
            assert values['cached_pages'] == values['requested_pages']
    proxy = [record for record in samples(directory / 'memory-0.log')
             if record['stage'] == 'workload' and record.get('domains') == count]
    assert len(proxy) >= 100
    assert all(record['gpu_requested'] <= record['occupied'] <= record['capacity']
               and record['free'] + record['occupied'] <= record['capacity']
               for record in proxy)
    gpu_bytes = max(record['gpu_requested'] for record in proxy)
    assert 0 < gpu_bytes <= pool_bytes
    cpu_bytes = 0
    cpu_peaks = []
    scores = []
    size = int(summary['profiles'][0].removeprefix('glmark-'))
    for member in range(1, count + 1):
        task = [record for record in samples(directory / f'memory-{member}.log')
                if record['stage'] == 'workload' and record['task_count']]
        assert len(task) >= 100 and all(record['task_count'] == 1 for record in task)
        peak = max(task, key=lambda record: record['cpu_bytes'])
        cpu_bytes += peak['cpu_bytes']
        cpu_peaks.append({name: peak[name] for name in ('cpu_bytes', 'task_Pss_Anon_sum',
                          'task_Pss_File_sum', 'task_Pss_Shmem_sum', 'mem_MemAvailable')})
        score, scenes = HELPERS['raw_result'](directory / f'glmark-{size}-client-{member}.log', size)
        if size == 720 and count == 1:
            assert score >= 1000
        scores.append(score)
    metadata = max(record['metadata_min'] for record in proxy)
    affinities = {thread['tid']: thread['cpus']
                  for threads in summary['thread_affinity'].values() for thread in threads}
    observer = HELPERS['observer'](experiment, run_id, summary['benchmark_events'], affinities)
    return {'run_id': run_id, 'size': size, 'count': count, 'gpu_bytes': gpu_bytes,
            'cpu_bytes': cpu_bytes, 'pool_bytes': pool_bytes,
            'pool_remainder_bytes': pool_bytes - gpu_bytes, 'target_bytes': target_bytes,
            'metadata_min_bytes': metadata, 'total_component_peaks_bytes': pool_bytes + cpu_bytes + target_bytes + metadata,
            'scores': scores, 'proxy_samples': len(proxy), 'cpu_peak_samples': cpu_peaks,
            'observer': observer}


def audit_native(directory, experiment):
    HELPERS['verify_collection'](directory)
    summary = load(directory / 'summary.json')
    run_id = summary['run_id']
    lab = experiment.parent / 'lab-runs' / run_id
    assert load(lab / 'result.json')['returncode'] == 0
    assert load(lab / 'native-mode.json')['config_restore'] == 'PASS'
    HELPERS['verify_lab_recovery'](experiment, run_id)
    HELPERS['kernel_health'](directory / 'dmesg-before.log', directory / 'dmesg-after.log')
    assert summary['status'] == 'PASS' and not summary['cleanup_failures']
    results = []
    for case in summary['cases']:
        assert case['status'] == 'PASS'
        folder = directory / case['case_id']
        data = samples(folder / 'gpu-memory-samples.log')
        task = [record for record in data if record['stage'] == 'workload' and record['task_count']]
        assert len(task) >= 100
        assert max(record['task_count'] for record in task) == case['count']
        assert all(record['overflow'] == record['missed'] == record['untracked_free'] == 0 for record in data)
        final = counters(case['gem_final'])
        assert final['objects'] == final['resident'] == final['requested'] == 0
        assert final['created'] == final['freed'] and final['untracked_free'] == final['overflow'] == final['missed'] == 0
        scores = []
        for process in case['processes']:
            assert process['returncode'] == 0
            score, scenes = HELPERS['raw_result'](folder / f"process-{process['index']}.log", case['size'])
            scores.append(score)
        gpu_bytes = max(record['user_resident'] for record in task)
        assert gpu_bytes > 0
        cpu_bytes = max(record['cpu_bytes'] for record in task)
        peak = max(task, key=lambda record: record['cpu_bytes'])
        observer = HELPERS['observer'](experiment, run_id, case['events'], {},
                                      native_cpus=[2 + member % 2 for member in range(case['count'])])
        results.append({'run_id': run_id, 'case_id': case['case_id'], 'size': case['size'],
                        'count': case['count'], 'gpu_bytes': gpu_bytes, 'cpu_bytes': cpu_bytes,
                        'total_component_peaks_bytes': gpu_bytes + cpu_bytes,
                        'all_gem_resident_peak_bytes': max(record['resident'] for record in task),
                        'gpu_requested_peak_bytes': max(record['user_requested'] for record in task),
                        'samples': len(data), 'task_samples': len(task), 'scores': scores,
                        'cpu_peak_sample': {name: peak[name] for name in ('cpu_bytes', 'task_Pss_Anon_sum',
                            'task_Pss_File_sum', 'task_Pss_Shmem_sum', 'mem_MemAvailable')},
                        'final': final, 'observer': observer})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True, type=Path)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--shared', nargs='+', required=True, type=Path)
    parser.add_argument('--native', nargs='+', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    shared = [audit_shared(directory, args.experiment, args.bundle) for directory in args.shared]
    native = [entry for directory in args.native for entry in audit_native(directory, args.experiment)]
    comparisons = []
    for entry in shared:
        matching = [record for record in native if (record['size'], record['count']) == (entry['size'], entry['count'])]
        assert len(matching) == 1, (entry['size'], entry['count'])
        baseline = matching[0]
        difference = entry['total_component_peaks_bytes'] - baseline['total_component_peaks_bytes']
        comparisons.append({'size': entry['size'], 'count': entry['count'],
            'native_bytes': baseline['total_component_peaks_bytes'],
            'shared_bytes': entry['total_component_peaks_bytes'], 'extra_bytes': difference,
            'extra_percent_of_native': difference / baseline['total_component_peaks_bytes'] * 100,
            'extra_percent_of_shared': difference / entry['total_component_peaks_bytes'] * 100})
    result = {'status': 'VERIFIED_MEASURED_COMPONENTS', 'shared': shared, 'native': native,
              'comparisons': comparisons, 'definitions': {
                  'peaks': '200 ms sampled component maxima; their sum is not a simultaneous or exhaustive physical peak',
                  'cpu': 'glmark process Pss_Anon + Pss_File; Pss_Shmem excluded to avoid counting BOs twice; Native sums processes within each sample, shared sums per-Realm maxima',
                  'gpu': 'Native user GEM BOs with resident backing; shared manager GPU_BO requested bytes within pinned provider pools',
                  'pool': 'full provider pools counted once, split into sampled BO peak and remainder including slack, control objects and allocator alignment',
                  'metadata': 'measured private manager structure allocation sizes only; a lower bound, excludes xarray and other protocol/private allocations',
                  'excluded': 'OS and VM fixed budgets, GPU page tables and general driver memory, instrumentation; no claim of complete forwarding overhead'}}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'comparisons': comparisons}, indent=2))


if __name__ == '__main__':
    main()
