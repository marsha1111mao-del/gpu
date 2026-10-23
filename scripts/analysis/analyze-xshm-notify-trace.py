#!/usr/bin/env python3
"""Pair physical-counter samples across RMM, Host and two GPU Realms."""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import runpy


ROOT = Path(__file__).resolve().parents[2]


def read_trace(path, marker, columns):
    lines = path.read_text().splitlines()
    header = next(line for line in lines if line.startswith(marker + ' '))
    metadata = dict(re.findall(r'(\w+)=(\S+)', header))
    records = []
    for line in lines[lines.index(header) + 2:]:
        values = line.split()
        if len(values) == len(columns) and all(value.lstrip('-').isdigit() for value in values):
            records.append(dict(zip(columns, map(int, values))))
    assert len(records) == int(metadata['count']), path
    assert int(metadata['dropped']) == 0, (path, metadata)
    assert metadata['clock'] == 'cntpct', path
    return metadata, records


def distribution(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    def percentile(fraction):
        index = (len(values) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (index - lower)
    return {'count': len(values), 'mean_us': sum(values) / len(values),
            'p50_us': percentile(.50), 'p95_us': percentile(.95),
            'p99_us': percentile(.99), 'min_us': values[0], 'max_us': values[-1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--host-trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    runpy.run_path(str(ROOT / 'scripts/analysis/summarize-fair-glmark.py'))['verify_collection'](args.run)
    summary = json.loads((args.run / 'summary.json').read_text())
    host_collection = json.loads(args.host_trace.with_suffix('.json').read_text())
    assert host_collection['run_id'] == summary['run_id']
    assert host_collection['workload_returncode'] == 0
    assert host_collection['trace_sha256'] == hashlib.sha256(args.host_trace.read_bytes()).hexdigest()
    assert summary['status'] == 'PASS' and summary['notify_trace']
    columns = 'kind channel sequence type flags status tick0 tick1 tick2 tick3 tick4'.split()
    source_meta, source = read_trace(args.run / 'notify-realm-1.log', 'XSHM_TRACE', columns)
    target_meta, target = read_trace(args.run / 'notify-realm-0.log', 'XSHM_TRACE', columns)
    host_meta, host = read_trace(args.host_trace, 'HOST_XSHM_TRACE',
                                'kind cpu tid peer tick0 tick1 target state'.split())
    assert int(host_meta['missed']) == 0
    assert all(meta['freq'] == source_meta['freq'] and
               meta['period'] == source_meta['period'] and
               meta['window'] == source_meta['window'] for meta in (target_meta, host_meta))
    assert source_meta['supported'] == target_meta['supported'] == '1'
    frequency = int(source_meta['freq'])
    tids = {int(vm): next(thread['tid'] for thread in threads
                         if thread['name'].startswith('fc_vcpu'))
            for vm, threads in summary['thread_affinity'].items()}
    receives = {(record['channel'], record['sequence'], record['type']): record
                for record in target if record['kind'] == 2}
    wakes = sorted((record for record in host if record['kind'] == 1 and
                    record['tid'] == tids[1]), key=lambda record: record['tick0'])
    wake_ticks = [record['tick0'] for record in wakes]
    wakeups = sorted((record for record in host if record['kind'] == 2 and
                      record['tid'] == tids[1] and record['peer'] == tids[0]),
                     key=lambda record: record['tick0'])
    wakeup_ticks = [record['tick0'] for record in wakeups]
    switches = sorted(record['tick0'] for record in host
                      if record['kind'] == 3 and record['peer'] == tids[0])
    measurements = defaultdict(list)
    grouped = defaultdict(lambda: defaultdict(list))
    classified = Counter()
    paired = []
    for sent in source:
        if sent['kind'] != 1:
            continue
        classified['sampled_notifications'] += 1
        if sent['status'] or sent['flags'] & 6:
            classified['failed_or_invalid_abi'] += 1
            continue
        before, after, entered, locked, ended = [sent['tick' + str(index)] for index in range(5)]
        assert 0 < before <= entered <= locked <= ended <= after, sent
        intervals = {'notify': after - before, 'guest_to_rmm': entered - before,
                     'rmm_lock': locked - entered, 'rmm_service': ended - locked,
                     'rmm_total': ended - entered, 'rmm_to_guest': after - ended}
        if sent['flags'] & 1:
            classified['host_exit_hint'] += 1
            index = bisect_left(wake_ticks, ended)
            if index < len(wakes) and wakes[index]['tick1'] <= after:
                wake = wakes[index]
                assert wake['tick0'] >= ended and wake['tick1'] >= wake['tick0']
                intervals.update({'rmm_to_host_helper': wake['tick0'] - ended,
                                  'host_wake_helper': wake['tick1'] - wake['tick0'],
                                  'host_helper_to_guest': after - wake['tick1']})
                classified['host_helper_matched'] += 1
                wake_index = bisect_left(wakeup_ticks, wake['tick0'])
                if wake_index < len(wakeups) and wakeups[wake_index]['tick0'] <= wake['tick1']:
                    event_tick = wakeups[wake_index]['tick0']
                    switch_index = bisect_left(switches, event_tick)
                    receive = receives.get((sent['channel'], sent['sequence'], sent['type']))
                    if receive and switch_index < len(switches) and switches[switch_index] <= receive['tick2']:
                        intervals['target_wakeup_to_switch'] = switches[switch_index] - event_tick
                        classified['target_scheduled_matched'] += 1
                else:
                    classified['no_target_sched_wakeup_in_helper'] += 1
            else:
                classified['host_helper_unmatched_sampling_boundary'] += 1
        key = (sent['channel'], sent['sequence'], sent['type'])
        receive = receives.get(key)
        if receive:
            assert receive['tick2'] >= before, (sent, receive)
            intervals['send_to_dispatch'] = receive['tick2'] - before
            intervals['rmm_end_to_dispatch'] = receive['tick2'] - ended
            if receive['tick2'] < after:
                classified['dispatch_before_sender_return'] += 1
            if before <= receive['tick0'] <= receive['tick1'] <= receive['tick2']:
                intervals['observed_irq_to_work'] = receive['tick1'] - receive['tick0']
                intervals['work_to_dispatch'] = receive['tick2'] - receive['tick1']
                intervals['rmm_end_to_observed_irq'] = receive['tick0'] - ended
                classified['receive_with_irq_after_send'] += 1
            else:
                classified['receive_already_draining_or_irq_coalesced'] += 1
            classified['receive_matched'] += 1
            paired.append({'channel': key[0], 'sequence': key[1], 'type': key[2],
                           'sent_tick': before, 'dispatch_tick': receive['tick2']})
        else:
            classified['receive_unmatched_sampling_boundary'] += 1
        for name, ticks in intervals.items():
            if ticks < 0:
                classified['overlapping_' + name] += 1
            else:
                measurements[name].append(ticks * 1e6 / frequency)
                grouped['host_hint_' + str(sent['flags'] & 1)][name].append(ticks * 1e6 / frequency)
                grouped[f'op_0x{sent["type"]:08x}'][name].append(ticks * 1e6 / frequency)
    assert classified['failed_or_invalid_abi'] == 0
    assert classified['receive_matched'] >= 100 and classified['host_helper_matched'] >= 100
    result = {'status': 'PASS', 'run_id': summary['run_id'], 'frequency': frequency,
              'host_collection': host_collection,
              'analysis_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'metadata': {'source': source_meta, 'target': target_meta, 'host': host_meta},
              'tids': tids, 'classification': dict(classified),
              'distributions': {name: distribution(values) for name, values in measurements.items()},
              'groups': {group: {name: distribution(values) for name, values in fields.items()}
                         for group, fields in grouped.items()},
              'pair_count': len(paired), 'pairs': paired,
              'limits': ['IRQ timestamps describe the last IRQ associated with work, not exclusive causality.',
                         'Source notification and target execution overlap; intervals must not be summed.',
                         'Deterministic 2ms windows every 100ms omit boundary-crossing matches.',
                         'No sched_wakeup event does not prove the target was running.']}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'run_id', 'classification', 'distributions')}, indent=2))


if __name__ == '__main__':
    main()
