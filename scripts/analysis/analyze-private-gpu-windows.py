#!/usr/bin/env python3
"""Account for private GPU completion waits without treating them as CPU cost.

Consumes a collected lab-run directory. Kernel windows share the Guest clock;
the glmark progress messages do not, so this tool does not assign scene names.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


WINDOW_FIELDS = (
    'ready_calls ready_pages ready_ns ready_empty ready_empty_ns return_ns '
    'complete_calls complete_ns complete_gap_ns sleep_ns relock_ns queue0_ns '
    'queue1_ns entry_lock_ns'
).split()
WAIT_FIELDS = ('sleep_ns', 'relock_ns', 'queue0_ns', 'queue1_ns', 'entry_lock_ns')
STAMP = re.compile(r'\[\s*(\d+\.\d+)\] panthor-client: ')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(line):
    return {key: int(value) for key, value in re.findall(r'\b(\w+)=(\d+)\b', line)}


def parse_windows(raw):
    unique = {}
    for line in raw.splitlines():
        if 'panthor-client: PRIVATE_WINDOW ' not in line:
            continue
        stamp = STAMP.search(line)
        require(stamp is not None, 'window lacks Guest kernel timestamp')
        row = fields(line)
        require(all(key in row for key in [*WINDOW_FIELDS, 'tasks', 'stride', 'active_pause']),
                'incomplete PRIVATE_WINDOW')
        require(row['stride'] == 1024 and row['active_pause'] == 1,
                'unsupported diagnostic format')
        require(row['tasks'] > 0 and row['tasks'] % row['stride'] == 0,
                'invalid retirement boundary')
        row['guest_ns'] = int(Decimal(stamp.group(1)) * 1_000_000_000)
        if row['tasks'] in unique:
            require(row == unique[row['tasks']], 'conflicting repeated window')
        else:
            unique[row['tasks']] = row
    rows = sorted(unique.values(), key=lambda row: row['guest_ns'])
    require(len(rows) >= 2, 'at least two complete kernel windows required')
    for before, after in zip(rows, rows[1:]):
        require(after['tasks'] > before['tasks'] and after['guest_ns'] > before['guest_ns'],
                'nonmonotonic window identity or timestamp')
        require(all(after[key] >= before[key] for key in WINDOW_FIELDS),
                'window counter rollback')
    return rows


def parse_totals(raw):
    phases, waits, prediction = {}, {}, None
    for line in raw.splitlines():
        if 'panthor-client: PRIVATE_PHASE ' in line:
            row = fields(line)
            key = row['phase']
            require(key not in phases or phases[key] == row, 'multiple worker phase totals')
            phases[key] = row
        elif 'panthor-client: PRIVATE_COMPLETION ' in line:
            row = fields(line)
            key = row['kind']
            require(key not in waits or waits[key] == row, 'multiple worker wait totals')
            waits[key] = row
        elif 'panthor-client: PRIVATE_POLL_PREDICT ' in line:
            row = fields(line)
            require(prediction is None or prediction == row, 'multiple prediction totals')
            prediction = row
    require(0 in phases and 4 in phases and set(waits) == set(range(5)) and prediction,
            'missing final worker totals')
    complete = phases[4]
    require(complete['calls'] > complete['again'] >= 0, 'invalid completed task count')
    retired = complete['calls'] - complete['again']
    require(prediction['trainings'] <= retired and prediction['initial_calls'] <= retired,
            'prediction count exceeds retired tasks')
    require(prediction['initial_ns'] <= waits[0]['ns'], 'initial pause exceeds all pauses')
    return phases, waits, prediction, retired


def accounting(retired, calls, operation_ns, gap_ns, wait_ns):
    require(retired > 0 and calls >= retired, 'invalid completion query count')
    residual = gap_ns - sum(wait_ns.values())
    require(residual >= 0, 'wait components exceed measured COMPLETE gap')
    return {
        'retired': retired,
        'queries_per_retired': calls / retired,
        'complete_operation_us_per_retired': operation_ns / retired / 1000,
        'complete_gap_us_per_retired': gap_ns / retired / 1000,
        'wait_us_per_retired': {key: value / retired / 1000 for key, value in wait_ns.items()},
        'wait_percent_of_complete_gap': {
            key: value * 100 / gap_ns if gap_ns else None for key, value in wait_ns.items()
        },
        'unattributed_gap_ns': residual,
    }


def analyze(raw):
    windows = parse_windows(raw)
    phases, waits, prediction, retired = parse_totals(raw)
    last = windows[-1]
    require(last['tasks'] <= retired and retired - last['tasks'] < last['stride'],
            'last kernel window does not match final worker totals')
    final_values = {
        'complete_calls': phases[4]['calls'], 'complete_ns': phases[4]['op_ns'],
        'complete_gap_ns': phases[4]['gap_ns'],
        **dict(zip(WAIT_FIELDS, [waits[k]['ns'] for k in range(5)])),
    }
    require(all(last[key] <= value for key, value in final_values.items()),
            'window exceeds final worker counters')
    intervals = []
    for before, after in zip(windows, windows[1:]):
        delta = {key: after[key] - before[key] for key in WINDOW_FIELDS}
        entry = accounting(after['tasks'] - before['tasks'], delta['complete_calls'],
                           delta['complete_ns'], delta['complete_gap_ns'],
                           {key: delta[key] for key in WAIT_FIELDS})
        entry.update(first_retired_exclusive=before['tasks'], last_retired=after['tasks'],
                     guest_start_ns=before['guest_ns'], guest_end_ns=after['guest_ns'],
                     wall_seconds=(after['guest_ns'] - before['guest_ns']) / 1e9,
                     missing_window_boundaries=(after['tasks'] - before['tasks']) // 1024 - 1)
        intervals.append(entry)
    total = accounting(retired, phases[4]['calls'], phases[4]['op_ns'], phases[4]['gap_ns'],
                       dict(zip(WAIT_FIELDS, [waits[k]['ns'] for k in range(5)])))
    phase_ns = sum(row['op_ns'] + row['gap_ns'] for row in phases.values())
    total.update(
        prepare_operation_us_per_retired=phases[0]['op_ns'] / retired / 1000,
        selected_phase_seconds=phase_ns / 1e9,
        immediate_queue_percent_of_selected_phase=waits[2]['ns'] * 100 / phase_ns,
        initial_pause_us_per_retired=prediction['initial_ns'] / retired / 1000,
        subsequent_pause_us_per_retired=(waits[0]['ns'] - prediction['initial_ns']) / retired / 1000,
        delayed_retry_calls=waits[3]['calls'],
        delayed_retry_ns=waits[3]['ns'],
        delayed_retry_average_us=waits[3]['ns'] / waits[3]['calls'] / 1000 if waits[3]['calls'] else None,
    )
    return {
        'totals': total,
        'window_coverage': {
            'snapshots': len(windows), 'first_retired': windows[0]['tasks'],
            'last_retired': last['tasks'],
            'prefix_not_resolved_into_windows': windows[0]['tasks'],
            'suffix_not_resolved_into_windows': retired - last['tasks'],
            'missing_internal_boundaries': sum(row['missing_window_boundaries'] for row in intervals),
        },
        'largest_delayed_retry_intervals': sorted(
            intervals, key=lambda row: row['wait_us_per_retired']['queue1_ns'], reverse=True)[:10],
        'intervals': intervals,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    evidence = args.run / 'realm-evidence'
    transfer = json.loads((args.run / 'evidence-transfer.json').read_text())
    require(transfer['status'] == 'PASS', 'evidence transfer failed')
    for name in ['realm-1.log', 'summary.json']:
        require(Path(name).name == name and name in transfer['files'], 'missing input digest')
        require(hashlib.sha256((evidence / name).read_bytes()).hexdigest() == transfer['files'][name],
                'input digest mismatch: ' + name)
    summary = json.loads((evidence / 'summary.json').read_text())
    require(summary['private_gpu'] and summary['clients'] == 1, 'requires one private GPU Client')
    require(summary['vm_exit_codes'] == [0, 0], 'workload did not exit cleanly')
    glmark = summary['concurrent_glmark']
    require(len(glmark) == 1 and len(glmark[0]['scenes']) == 33 and glmark[0]['returncode'] == 0,
            'requires a complete 33-scene measurement')
    require(glmark[0]['pass_marker'] and not glmark[0]['errors'], 'glmark workload errors')
    report = analyze((evidence / 'realm-1.log').read_text())
    report.update(
        run_id=args.run.name, score=glmark[0]['score'], validation=glmark[0]['validation'],
        performance_gate_pass=glmark[0]['score'] >= 1000,
        input_sha256={name: transfer['files'][name] for name in ['realm-1.log', 'summary.json']},
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limits=[
            'Historical logs only: no runtime code change and no new GPU measurement.',
            'Counters include warmup and validation, not just the timed 33 scenes.',
            'Operation time includes RPC/RMM/device interaction and scheduling; it is not CPU cost.',
            'Active pauses and delayed retries overlap GPU execution; neither is wholly removable overhead.',
            'Immediate queue time is an observed component, not an end-to-end speedup bound.',
            'Kernel windows missing from a wrapped log are not interpolated.',
            'Scene attribution unavailable: progress messages lack a matching Guest kernel clock.',
        ],
    )
    require(not args.output.exists(), 'refusing to overwrite report')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['run_id', 'score', 'totals', 'window_coverage']}, indent=2))


if __name__ == '__main__':
    main()
