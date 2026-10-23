from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import statistics
import subprocess
import sys

parser = argparse.ArgumentParser(description='Audit paired plan-cache glmark runs and control-allocation ledgers')
parser.add_argument('--experiment', type=Path, required=True)
parser.add_argument('--partial', action='store_true')
args = parser.parse_args()
experiment = args.experiment
helpers = runpy.run_path('scripts/analysis/summarize-fair-glmark.py')
provenance = json.loads((experiment / 'provenance.json').read_text())
for name, expected in provenance['sources'].items():
    assert hashlib.sha256((Path('Linux-Guest-GPU') / name).read_bytes()).hexdigest() == expected, name
rmm_reference = provenance['unchanged_rmm_reference']
rmm_elf = Path(rmm_reference['elf'])
assert hashlib.sha256(rmm_elf.read_bytes()).hexdigest() == rmm_reference['sha256']
symbol_output = subprocess.check_output(['aarch64-linux-gnu-nm', '-S', str(rmm_elf)], text=True)
rmm_symbols = {}
for line in symbol_output.splitlines():
    columns = line.split()
    if len(columns) == 4 and columns[3] in ('leases', 'buckets', 'dma_maps', 'gpu_batch'):
        assert columns[2].lower() == 'b' and columns[3] not in rmm_symbols
        rmm_symbols[columns[3]] = int(columns[1], 16)
assert rmm_symbols == {'leases': 524288 * 24, 'buckets': 131072 * 4,
                       'dma_maps': 1024 * 32, 'gpu_batch': 65536}, rmm_symbols

def fields(text):
    return {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', text)}

def control(path):
    lines = path.read_text().replace('\r', '').splitlines()
    header = next(fields(line) for line in lines if line.startswith('enabled='))
    total = next(fields(line) for line in lines if line.startswith('total '))
    sites = {line.split()[0]: fields(line) for line in lines if ' site requested=' in line}
    assert header['enabled'] == 1 and header['lost'] == 0, (path, header)
    for values in [total, *sites.values()]:
        assert values['requested_in'] - values['requested_out'] == values['requested']
        assert values['allocated_in'] - values['allocated_out'] == values['allocated']
        assert values['allocations'] >= values['frees']
        assert values['peak_requested'] >= values['requested']
        assert values['peak_allocated'] >= values['allocated'] >= values['requested']
    assert len(sites) == header['sites'], (path, sites, header)
    for field in ('requested', 'allocated', 'allocations', 'frees', 'requested_in', 'requested_out', 'allocated_in', 'allocated_out'):
        assert sum(value[field] for value in sites.values()) == total[field], (path, field)
    return {'header': header, 'total': total, 'sites': sites}

def timings(folder, mode):
    measured = helpers['diagnostic_timings'](folder, 1)
    phase_snapshots = helpers['timing_snapshots'](folder / 'realm-0.log', 'PANTHOR_PROXY_SUBMIT_PHASES', by_operation=True)
    operation = 'PLAN_EXEC' if mode == 'on' else 'UNCACHED_SUBMIT'
    phase = phase_snapshots['PLAN_EXEC']
    client = measured['client_rpc']['1'][operation]
    proxy = measured['proxy_rpc'][operation]
    assert phase['calls'] == client['calls'] == proxy['calls'] > 0
    assert client['errors'] == client['timeouts'] == 0
    native_calls = measured['group_submit']['group_calls']
    assert phase['calls'] - phase['errors'] == native_calls
    names = ('lookup', 'validate', 'assemble', 'native', 'auxiliary')
    residual = client['total_ns'] - sum(phase[name + '_ns'] for name in names)
    assert residual >= phase['queue_ns']
    assert phase['service_ns'] >= sum(phase[name + '_ns'] for name in names) + phase['queue_ns']
    means = {name: phase[name + '_ns'] / phase['calls'] / 1000 for name in names}
    means['rpc'] = residual / phase['calls'] / 1000
    means['roundtrip'] = client['total_ns'] / phase['calls'] / 1000
    registration = measured['client_rpc']['1'].get('PLAN_REGISTER', {})
    if mode == 'off':
        assert not registration.get('calls', 0)
        assert phase['errors'] == 0
    return {'operation': operation, 'calls': phase['calls'], 'native_calls': native_calls,
            'mean_us': means, 'registration': registration, 'raw_phase': phase,
            'client_rpc': client, 'proxy_rpc': proxy}

runs = []
excluded = []
pending = []
for workflow_path in sorted(experiment.glob('*-workflow.json')):
    workflow = json.loads(workflow_path.read_text())
    if workflow['status'] == 'FAIL':
        excluded.append(workflow)
        continue
    if workflow['status'] == 'RUNNING' and args.partial:
        pending.append(workflow['run_id'])
        continue
    assert workflow['status'] == 'PASS', workflow
    run_id = workflow['run_id']
    folder = experiment / 'runs' / run_id
    helpers['verify_collection'](folder)
    helpers['verify_lab_recovery'](experiment, run_id)
    summary = json.loads((folder / 'summary.json').read_text())
    assert summary['status'] == 'PASS'
    if workflow['kind'] != 'api':
        assert summary['plan_cache'] == (workflow['mode'] == 'on')
    assert summary['host_performance']['before'] == summary['host_performance']['restored']
    assert summary['transfer_capture']
    assert all(not issues for realm in summary['kernel_health'].values() for issues in realm.values())
    assert not any(summary.get(key) for key in ('transport_cleanup_errors', 'grant_cleanup_errors', 'host_restore_error'))
    lab = Path('build/lab-runs') / run_id
    assert json.loads((lab / 'result.json').read_text())['returncode'] == 0
    assert json.loads((folder / 'host-kernel-health.json').read_text())['status'] == 'PASS'
    lease = json.loads((lab / 'lease-monitor.json').read_text())
    assert lease['monitor_pass'] and lease['final'] == lease['dma_final'] == lease['errors'] == 0
    assert json.loads((lab / 'normal-inputs-restored.json').read_text())['status'] == 'PASS'
    record = {key: workflow[key] for key in ('run_id', 'mode', 'kind', 'size', 'timing')}
    record['lease_peak'] = lease['peak']
    bundle = Path(workflow['bundle'])
    manifest = json.loads((bundle / 'hashes.json').read_text())
    for name, suffix in [('client-Image', 'firecracker-bins/kernels/realm-xshm/Image'),
                         ('proxy-Image', 'firecracker-bins/kernels/realm-xshm/proxy/Image'),
                         ('initrd.cpio', 'firecracker-bins/kernels/realm-xshm/initrd.cpio'),
                         ('runner.py', 'tests/realm-xshm/run-realms.py')]:
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == manifest[name]
        assert summary['inputs']['/root/GPU-SFTP/' + suffix] == manifest[name]
    if workflow['kind'] != 'api':
        assert summary['vm_exit_codes'] == [0, 0]
        assert summary['profiles'] == [f'glmark-{workflow["size"]}']
        assert summary['cpu_frequency_khz'] == 1800000 and summary['client_cpu_layout'] == 'round-robin'
        assert summary['memory_pages'] == (32768 if workflow['size'] == 720 else 49152)
        score, scenes = helpers['raw_result'](folder / f'glmark-{workflow["size"]}-client-1.log', workflow['size'])
        record.update(score=score, scenes=len(scenes))
        expected_pids = {}
        for member in range(2):
            for thread in summary['thread_affinity'][str(member)]:
                assert thread['cpus'] == ([member + 1] if thread['name'].startswith('fc_vcpu') else [0])
                expected_pids[thread['tid']] = thread['cpus']
            configuration = json.loads((folder / f'realm-{member}.json').read_text())
            commandline = configuration['boot-source']['boot_args']
            assert f'panthor_client.plan_cache={int(workflow["mode"] == "on")}' in commandline
            assert ('realm_xshm_control.enabled=1' in commandline) == (workflow['kind'] == 'memory')
            assert ('client_comm_vmshm.rpc_stats=1' in commandline) == bool(member and workflow['timing'])
        record['observer'] = helpers['observer'](experiment, run_id, summary['benchmark_events'], expected_pids)
    else:
        for member in range(1, 3):
            configuration = json.loads((folder / f'realm-{member}.json').read_text())
            commandline = configuration['boot-source']['boot_args']
            assert f'panthor_client.plan_cache={int(workflow["mode"] == "on")}' in commandline
        audit = subprocess.run([sys.executable, 'scripts/analysis/audit-transfer-capture.py',
            '--experiment', str(experiment), '--run-id', run_id, '--bundle', str(bundle),
            '--capture', '--api'], capture_output=True, text=True)
        (experiment / f'{run_id}-independent-audit.log').write_text(audit.stdout + audit.stderr)
        audit.check_returncode()
        record['api_audit'] = json.loads((experiment / f'{run_id}-audit.json').read_text())
    if workflow['kind'] == 'memory':
        record['control'] = {str(member): {
            stage: control(folder / f'control-{stage}-{member}.log')
            for stage in ('after-workload', 'after-detach')} for member in range(2)}
        for ledger in record['control'].values():
            detached = ledger['after-detach']
            assert detached['total']['requested'] == detached['total']['allocated'] == 0
            assert detached['total']['allocations'] == detached['total']['frees']
            assert detached['header']['observer_current'] == 0
        pools = []
        cpu = []
        for member in range(2):
            samples = []
            for line in (folder / f'memory-{member}.log').read_text().splitlines():
                if not line.startswith('MEM_SAMPLE ') or 'stage=workload ' not in line:
                    continue
                sample = fields(re.sub(r'\w+=\{[^}]*\}', '', line))
                match = re.search(r'pool_memory=\{([^}]+)\}', line)
                if match:
                    pool = fields(match[1])
                    assert pool['capacity'] == pool['free'] + pool['occupied'] + 2 * 1024**2
                    assert pool['capacity'] + 1024**2 == summary['memory_pages'] * 4096
                    pool['source_capacity'] = pool['capacity'] + 1024**2
                    pool['control_and_alignment_reserved'] = 3 * 1024**2
                    pool['allocation_slack'] = pool['occupied'] - pool['gpu_requested'] - pool['other_requested']
                    assert pool['allocation_slack'] >= 0, pool
                    pools.append(pool)
                samples.append(sample)
            assert samples
            cpu.append(max((sample['task_Pss_Anon_sum'] + sample['task_Pss_File_sum']) * 1024 for sample in samples))
        peak = max(pools, key=lambda sample: sample['gpu_requested'])
        record['pool_at_gpu_peak'] = peak
        record['cpu_pss_peaks_bytes'] = cpu
    if workflow['timing']:
        record['timings'] = timings(folder, workflow['mode'])
    runs.append(record)

comparisons = []
for size in (720, 1080):
    groups = {mode: [run['score'] for run in runs if run['kind'] == 'performance' and run['size'] == size and run['mode'] == mode]
              for mode in ('on', 'off')}
    if not args.partial:
        assert all(len(values) == 2 for values in groups.values()), groups
    if not all(groups.values()):
        continue
    means = {mode: statistics.mean(values) for mode, values in groups.items()}
    comparisons.append({'size': size, 'scores': groups, 'means': means,
        'delta': means['on'] - means['off'], 'improvement_percent': (means['on'] / means['off'] - 1) * 100})
if not args.partial:
    for mode in ('on', 'off'):
        assert len([run for run in runs if run['kind'] == 'api' and run['mode'] == mode]) == 1
        for size in ((720, 1080) if mode == 'on' else (1080,)):
            assert len([run for run in runs if run['kind'] == 'memory' and run['mode'] == mode and run['size'] == size]) == 1
    manifests = [json.loads((experiment / 'v3' / f'performance-{mode}' / 'hashes.json').read_text()) for mode in ('on', 'off')]
    for name in ('client-Image', 'proxy-Image', 'initrd.cpio'):
        assert manifests[0][name] == manifests[1][name]
result = {'status': 'PARTIAL' if args.partial else 'PASS', 'runs': runs,
          'comparisons': comparisons, 'excluded_failed_runs': excluded, 'pending': pending,
          'rmm_static': {'elf': str(rmm_elf), 'sha256': rmm_reference['sha256'],
                         'symbols_bytes': rmm_symbols, 'selected_total_bytes': sum(rmm_symbols.values())}}
(experiment / ('analysis-partial.json' if args.partial else 'analysis.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'status': result['status'], 'runs': len(runs), 'comparisons': comparisons}, ensure_ascii=False, indent=2))
