#!/usr/bin/env python3
"""Decompose matched Client/Proxy PLAN RPC totals without overlapping timers."""
import argparse
import json
from pathlib import Path
import re
import runpy


def analyze(folder):
    helpers = runpy.run_path(str(Path(__file__).with_name('summarize-fair-glmark.py')))
    helpers['verify_collection'](folder)
    summary = helpers['load'](folder / 'summary.json')
    assert summary['status'] == 'PASS' and summary['rpc_stats']
    assert summary['clients'] == 1 and summary['vm_exit_codes'] == [0, 0]
    assert helpers['load'](folder / 'lab-result.json')['returncode'] == 0
    assert helpers['load'](folder / 'host-kernel-health.json')['status'] == 'PASS'
    assert all(not issues for realm in summary['kernel_health'].values() for issues in realm.values())
    timings = helpers['diagnostic_timings'](folder, 1)
    phases = helpers['timing_snapshots'](
        folder / 'realm-0.log', 'PANTHOR_PROXY_SUBMIT_PHASES', by_operation=True)
    breakdown = {}
    for operation in ('PLAN_EXEC', 'PLAN_REGISTER'):
        phase = phases[operation]
        client = timings['client_rpc']['1'][operation]
        proxy = timings['proxy_rpc'][operation]
        assert phase['calls'] == client['calls'] == proxy['calls'] > 0, operation
        assert client['errors'] == client['timeouts'] == 0, operation
        if operation == 'PLAN_REGISTER':
            assert phase['errors'] == 0, operation
        fields = ('lookup_ns', 'validate_ns', 'assemble_ns', 'native_ns',
                  'queue_ns', 'auxiliary_ns')
        accounted = sum(phase[name] for name in fields)
        assert phase['service_ns'] >= accounted, operation
        assert client['total_ns'] >= phase['service_ns'], operation
        residual = client['total_ns'] - sum(phase[name] for name in fields if name != 'queue_ns')
        assert residual >= phase['queue_ns'], operation
        mean = {name.removesuffix('_ns'): phase[name] / phase['calls'] / 1000 for name in fields}
        mean.update(
            rpc=residual / phase['calls'] / 1000,
            roundtrip=client['total_ns'] / phase['calls'] / 1000,
            service=phase['service_ns'] / phase['calls'] / 1000,
            phase_gap=(phase['service_ns'] - accounted) / phase['calls'] / 1000,
            outside_service=(client['total_ns'] - phase['service_ns']) / phase['calls'] / 1000)
        categories = ('rpc', 'lookup', 'validate', 'assemble', 'native', 'auxiliary')
        assert abs(sum(mean[name] for name in categories) - mean['roundtrip']) < 1e-9
        breakdown[operation] = {
            'calls': phase['calls'], 'mean_us': mean,
            'raw_phases': phase, 'client_rpc': client, 'proxy_rpc': proxy,
            'share_percent': {name: mean[name] / mean['roundtrip'] * 100 for name in categories},
        }
    execution = breakdown['PLAN_EXEC']
    registration = breakdown['PLAN_REGISTER']
    group = timings['group_submit']
    assert group['group_calls'] > 0
    assert execution['calls'] - group['group_calls'] == execution['raw_phases']['errors']
    native_outer_per_call = execution['raw_phases']['native_ns'] / group['group_calls'] / 1000
    proxy_sessions = {int(session): {'registered': int(registered), 'runs': int(runs)}
                      for session, registered, runs in re.findall(
                          r'TASK_PLAN_STATS session=(\d+) registered=(\d+) runs=(\d+)',
                          (folder / 'realm-0.log').read_text())}
    observed_runs = sum(session['runs'] for session in proxy_sessions.values())
    observed_registers = sum(session['registered'] for session in proxy_sessions.values())
    assert observed_runs <= group['group_calls']
    assert observed_registers <= registration['calls']
    client_sessions = {int(session): {'hits': int(hits), 'misses': int(misses)}
                       for session, hits, misses in re.findall(
                           r'TASK_PLAN_STATS session=(\d+) hits=(\d+) misses=(\d+)',
                           (folder / 'realm-1.log').read_text())}
    assert client_sessions
    for session, values in client_sessions.items():
        assert values['hits'] + values['misses'] == proxy_sessions[session]['runs']
    native_fields = ('init_ctx', 'create_jobs', 'collect_signals', 'prepare_resvs',
                     'sync_mapped_bos', 'arm_jobs', 'push_jobs', 'cleanup')
    native_subphases = {name: group['group_' + name + '_ns'] / group['group_calls'] / 1000
                        for name in native_fields}
    register_per_exec = registration['calls'] / execution['calls']
    return {
        'status': 'PASS', 'run_id': summary['run_id'], 'breakdown': breakdown,
        'register_per_exec': register_per_exec,
        'amortized_register_roundtrip_us': register_per_exec * registration['mean_us']['roundtrip'],
        'amortized_total_roundtrip_us': execution['mean_us']['roundtrip'] +
                                      register_per_exec * registration['mean_us']['roundtrip'],
        'native_subphases_us': native_subphases,
        'native_calls': group['group_calls'],
        'execution_attempts_without_native': execution['calls'] - group['group_calls'],
        'amortized_rpc_per_native_us': (execution['client_rpc']['total_ns'] +
                                        registration['client_rpc']['total_ns']) / group['group_calls'] / 1000,
        'native_outer_per_call_us': native_outer_per_call,
        'proxy_sessions': proxy_sessions,
        'observed_client_sessions': client_sessions,
        'native_calls_outside_session_snapshots': group['group_calls'] - observed_runs,
        'registrations_outside_session_snapshots': registration['calls'] - observed_registers,
        'native_internal_mean_us': group['group_avg_ns'] / 1000,
        'native_outer_minus_internal_us': native_outer_per_call - group['group_avg_ns'] / 1000,
        'scope': 'last cumulative matched snapshots: validation, scoring and teardown',
        'semantics': 'elapsed wall time; RPC is an aggregate residual including queue waits and unclassified gaps; native excludes asynchronous GPU completion',
        'timings': timings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'run_id', 'breakdown')}, indent=2))


if __name__ == '__main__':
    main()
