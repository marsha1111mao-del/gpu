#!/usr/bin/env python3
"""Audit one full 720p TRANSFER capture experiment and its recovery evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--api', action='store_true')
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    folder = experiment / 'runs' / args.run_id
    helpers = runpy.run_path(str(ROOT / 'scripts/analysis/summarize-fair-glmark.py'))
    load = helpers['load']
    helpers['verify_collection'](folder)
    helpers['verify_lab_recovery'](experiment, args.run_id)
    summary = load(folder / 'summary.json')
    lab = ROOT / 'build/lab-runs' / args.run_id
    assert load(lab / 'result.json')['returncode'] == 0
    manifest = load(experiment / ('semantic' if args.api else 'candidate') / 'hashes.json')
    for name, suffix in (('runner.py', 'tests/realm-xshm/run-realms.py'),
                         ('client-Image', 'firecracker-bins/kernels/realm-xshm/Image'),
                         ('proxy-Image', 'firecracker-bins/kernels/realm-xshm/proxy/Image'),
                         ('initrd.cpio', 'firecracker-bins/kernels/realm-xshm/initrd.cpio')):
        assert summary['inputs']['/root/GPU-SFTP/' + suffix] == manifest[name]
    assert all(not issues for realm in summary['kernel_health'].values() for issues in realm.values())
    if args.api:
        assert args.capture and summary['transfer_capture']
        assert summary['status'] == 'PASS' and summary['vm_exit_codes'] == [0, 0, 0]
        for key in ('two_client_gpu_flow_check', 'two_client_compute_check',
                    'bo_sg_mmap_check', 'memory_check'):
            assert summary[key] == 'PASS'
        assert load(folder / 'host-kernel-health.json')['status'] == 'PASS'
        lease = load(lab / 'lease-monitor.json')
        assert lease['monitor_pass'] and lease['workload_returncode'] == 0
        assert lease['final'] == lease['dma_final'] == lease['errors'] == 0
        commands = {}
        for member in (1, 2):
            text = (folder / f'realm-{member}.log').read_text(errors='replace')
            assert 'PANTHOR_TRANSFER_CAPTURE_SMOKE=PASS' in text
            assert 'PANTHOR_SYNC_FILE_SNAPSHOT_SMOKE=PASS' in text
            assert 'PANTHOR_SYNC_FILE_IMPORT_SMOKE=PASS' in text
            assert not re.search(r'BUG:|Oops:|WARNING:|job timeout|Out of memory', text)
            modes = [command for command in summary['commands']
                     if command['realm'] == member and command['command'].startswith('gpu-smoke')]
            assert len(modes) == 19
            assert all(command['returncode'] == 0 and
                       all(command['markers'].values()) for command in modes)
            commands[str(member)] = [command['command'] for command in modes]
        record = {'status': 'PASS', 'run_id': args.run_id, 'commands': commands,
                  'vm_exit_codes': summary['vm_exit_codes'], 'lease': lease,
                  'audit_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (experiment / f'{args.run_id}-audit.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))
        return
    assert summary['status'] == 'PASS' and summary['vm_exit_codes'] == [0, 0]
    assert summary['transfer_capture'] == args.capture
    assert summary['profiles'] == ['glmark-720'] and summary['clients'] == 1
    assert summary['memory_pages'] == 32768
    assert summary['cpu_frequency_khz'] == 1800000
    assert summary['client_cpu_layout'] == 'round-robin'
    assert load(folder / 'host-kernel-health.json')['status'] == 'PASS'
    lease = load(lab / 'lease-monitor.json')
    assert lease['monitor_pass'] and lease['workload_returncode'] == 0
    assert lease['final'] == lease['dma_final'] == lease['errors'] == 0
    assert summary['host_performance']['before'] == summary['host_performance']['restored']
    assert not any(summary.get(key) for key in
                   ('transport_cleanup_errors', 'grant_cleanup_errors', 'host_restore_error'))
    score, scenes = helpers['raw_result'](folder / 'glmark-720-client-1.log', 720)
    assert summary['concurrent_glmark'][0]['score'] == score and score >= 1000
    affinities = {}
    for member in range(2):
        config = load(folder / f'realm-{member}.json')
        enabled = 'panthor_client.transfer_capture=1' in config['boot-source']['boot_args']
        assert enabled == bool(member and args.capture)
        for thread in summary['thread_affinity'][str(member)]:
            expected = [member + 1] if thread['name'].startswith('fc_vcpu') else [0]
            assert thread['cpus'] == expected
            affinities[thread['tid']] = expected
        serial = (folder / f'realm-{member}.log').read_text(errors='replace')
        assert not re.search(r'job timeout|CSG \d+ update request timedout|FW ping timeout|'
                             r'MESA: error:|Out of memory|BUG:|Oops:|WARNING:|Kernel panic', serial)
    observation = helpers['observer'](experiment, args.run_id,
                                      summary['benchmark_events'], affinities)
    text = (folder / 'glmark-720-client-1.log').read_text(errors='replace')
    snapshots = re.findall(r'PANTHOR_CLIENT_SYNC_FILE_WAIT_STATS ([^\r\n]+)', text)
    assert snapshots
    counters = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', snapshots[-1])}
    if args.capture:
        assert counters['capture_calls'] > 0 and counters['capture_hits'] > 0
        assert counters['capture_records'] <= counters['capture_calls']
    else:
        assert counters['capture_calls'] == counters['capture_hits'] == 0
    record = {
        'status': 'PASS', 'run_id': args.run_id, 'capture': args.capture,
        'rpc_stats': summary['rpc_stats'], 'score': score, 'scenes': len(scenes),
        'counters': counters, 'observer': observation, 'lease': lease,
        'vm_exit_codes': summary['vm_exit_codes'],
        'input_sha256': manifest,
        'audit_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if summary['rpc_stats']:
        record['timings'] = helpers['diagnostic_timings'](folder, 1)
        for values in record['timings']['client_rpc']['1'].values():
            assert values['errors'] == values['timeouts'] == 0
    (experiment / f'{args.run_id}-audit.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in
                      ('status', 'run_id', 'score', 'capture', 'rpc_stats', 'counters')}, indent=2))


if __name__ == '__main__':
    main()
