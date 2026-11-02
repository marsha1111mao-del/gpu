#!/usr/bin/env python3
"""Conservatively associate kernel accounting windows with userspace scenes."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy


CORE = runpy.run_path(str(Path(__file__).with_name('analyze-private-gpu-windows.py')))
require = CORE['require']
WAIT_FIELDS = CORE['WAIT_FIELDS']


def scene_regions(raw, scenes):
    clocks = {}
    for line in raw.splitlines():
        marker = 'GLMARK_SCENE_CLOCK '
        if marker not in line:
            continue
        parts = line.split(marker, 1)[1].split()
        require(all('=' in part for part in parts), 'incomplete scene clock record')
        pairs = [part.split('=', 1) for part in parts]
        require(len({key for key, _ in pairs}) == len(pairs), 'duplicate scene clock field')
        row = dict(pairs)
        keys = {'before_ns', 'after_ns', 'completed_scenes', 'active_hint',
                'snapshot_bytes', 'device', 'inode', 'prefix_hex'}
        require(set(row) == keys, 'unsupported scene clock fields')
        for key in keys - {'prefix_hex'}:
            require(row[key].isascii() and row[key].isdigit(), 'invalid scene clock number')
            row[key] = int(row[key])
        require(0 < row['before_ns'] <= row['after_ns'], 'invalid clock read bracket')
        require(0 <= row['completed_scenes'] <= len(scenes) and row['active_hint'] in (0, 1),
                'invalid scene count or active hint')
        require(row['snapshot_bytes'] <= 131072, 'oversize scene log snapshot')
        if row['prefix_hex'] == 'none':
            prefix = None
        else:
            prefix = bytes.fromhex(row['prefix_hex']).decode('utf-8').rstrip()
        require(bool(prefix) == bool(row['active_hint']), 'prefix and active hint disagree')
        index = row['completed_scenes']
        row['matched_scene'] = index if (
            prefix and index < len(scenes) and prefix == scenes[index]['scene'].rstrip()) else None
        key = row['before_ns']
        require(key not in clocks or clocks[key] == row, 'conflicting scene clock copy')
        clocks[key] = row
    clocks = sorted(clocks.values(), key=lambda row: row['before_ns'])
    require(len(clocks) >= 2, 'insufficient scene clock samples')
    regions = []
    for before, after in zip(clocks, clocks[1:]):
        require(after['before_ns'] >= before['after_ns'], 'overlapping clock samples')
        require(after['completed_scenes'] >= before['completed_scenes'], 'scene count rollback')
        require((before['device'], before['inode']) == (after['device'], after['inode']),
                'benchmark log file identity changed')
        require(after['snapshot_bytes'] >= before['snapshot_bytes'], 'benchmark log was truncated')
        if before['matched_scene'] is not None and before['matched_scene'] == after['matched_scene']:
            regions.append({'scene_index': before['matched_scene'],
                            'start_ns': before['after_ns'], 'end_ns': after['before_ns']})
    return clocks, regions


def monotonic_intervals(raw, accounting):
    """Require explicit ktime_get_ns endpoints; printk local_clock is distinct."""
    snapshots = CORE['parse_windows'](raw)
    require(all('mono_ns' in row and row['mono_ns'] > 0 for row in snapshots),
            'uncertified clock domain: PRIVATE_WINDOW requires explicit mono_ns')
    require(all(after['mono_ns'] > before['mono_ns']
                for before, after in zip(snapshots, snapshots[1:])),
            'nonmonotonic explicit kernel monotonic clock')
    require(len(accounting['intervals']) == len(snapshots) - 1,
            'accounting and monotonic window counts disagree')
    intervals = []
    for before, after, window in zip(snapshots, snapshots[1:], accounting['intervals']):
        require((window['first_retired_exclusive'], window['last_retired']) ==
                (before['tasks'], after['tasks']), 'monotonic window identity mismatch')
        intervals.append({**window, 'guest_start_ns': before['mono_ns'],
                          'guest_end_ns': after['mono_ns'],
                          'wall_seconds': (after['mono_ns'] - before['mono_ns']) / 1e9})
    return intervals


def assign(raw, scenes, accounting):
    intervals = monotonic_intervals(raw, accounting)
    clocks, regions = scene_regions(raw, scenes)
    assigned, unassigned = [], []
    for window in intervals:
        matches = [region for region in regions if
                   region['start_ns'] <= window['guest_start_ns'] and
                   window['guest_end_ns'] <= region['end_ns']]
        require(len(matches) <= 1, 'ambiguous scene region')
        if matches:
            assigned.append({**window, 'scene_index': matches[0]['scene_index']})
        else:
            unassigned.append(window)
    by_scene = []
    for index, scene in enumerate(scenes):
        selected = [window for window in assigned if window['scene_index'] == index]
        retired = sum(window['retired'] for window in selected)
        entry = {'scene_index': index, 'scene': scene['scene'], 'fps': scene['fps'],
                 'accounted_windows': len(selected), 'accounted_retired': retired}
        if retired:
            for key in ['queries_per_retired', 'complete_operation_us_per_retired',
                        'complete_gap_us_per_retired']:
                entry[key] = sum(window[key] * window['retired'] for window in selected) / retired
            entry['wait_us_per_retired'] = {
                key: sum(window['wait_us_per_retired'][key] * window['retired']
                         for window in selected) / retired for key in WAIT_FIELDS
            }
        by_scene.append(entry)
    saved_retired = sum(window['retired'] for window in intervals)
    assigned_retired = sum(window['retired'] for window in assigned)
    return {
        'clock_domain': 'Guest CLOCK_MONOTONIC / explicit kernel ktime_get_ns mono_ns',
        'scene_clock_samples': len(clocks), 'stable_scene_regions': len(regions),
        'coverage': {'all_retired': accounting['totals']['retired'],
                     'saved_window_retired': saved_retired,
                     'assigned_retired': assigned_retired,
                     'unassigned_saved_window_retired': saved_retired - assigned_retired,
                     'unresolved_prefix_and_suffix': accounting['totals']['retired'] - saved_retired},
        'by_scene': by_scene,
        'largest_assigned_delayed_retry_windows': sorted(
            assigned, key=lambda row: row['wait_us_per_retired']['queue1_ns'], reverse=True)[:10],
        'largest_unassigned_delayed_retry_windows': sorted(
            unassigned, key=lambda row: row['wait_us_per_retired']['queue1_ns'], reverse=True)[:10],
        'regions': regions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.run / 'realm-evidence'
    transfer = json.loads((args.run / 'evidence-transfer.json').read_text())
    require(transfer['status'] == 'PASS', 'evidence transfer failed')
    for name in ['realm-1.log', 'summary.json']:
        require(hashlib.sha256((evidence / name).read_bytes()).hexdigest() == transfer['files'][name],
                'evidence digest mismatch: ' + name)
    summary = json.loads((evidence / 'summary.json').read_text())
    require(summary['private_gpu'] and summary['clients'] == 1 and summary['vm_exit_codes'] == [0, 0],
            'requires a completed single private GPU Client run')
    glmark = summary['concurrent_glmark']
    require(len(glmark) == 1 and len(glmark[0]['scenes']) == 33 and
            glmark[0]['returncode'] == 0 and glmark[0]['pass_marker'] and not glmark[0]['errors'],
            'requires all 33 glmark scenes without workload errors')
    raw = (evidence / 'realm-1.log').read_text()
    accounting = CORE['analyze'](raw)
    report = assign(raw, glmark[0]['scenes'], accounting)
    report.update(
        run_id=args.run.name, score=glmark[0]['score'], validation=glmark[0]['validation'],
        performance_gate_pass=glmark[0]['score'] >= 1000,
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        accounting_analyzer_sha256=hashlib.sha256(
            Path(__file__).with_name('analyze-private-gpu-windows.py').read_bytes()).hexdigest(),
        input_sha256={name: transfer['files'][name] for name in ['realm-1.log', 'summary.json']},
        limits=[
            'printk local_clock timestamps are never used for userspace scene attribution.',
            'Scene names describe observed userspace output; they are not hardware task identities.',
            'Only whole kernel intervals inside two matching scene snapshots are assigned.',
            'Read brackets, scene transitions, missing kernel windows and unmatched prefixes stay unassigned.',
            'Scene regions may include setup, teardown or work submitted before the userspace marker.',
            'Selected intervals need not represent an entire scene; low-throughput scenes may have none.',
            'The diagnostic changes workload sampling and the initrd, so its score is not an optimization gain.',
            'Wait and operation wall time can overlap GPU execution and do not establish removable CPU cost.',
        ],
    )
    require(not args.output.exists(), 'refusing to overwrite scene report')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in [
        'run_id', 'score', 'scene_clock_samples', 'stable_scene_regions', 'coverage']}, indent=2))


if __name__ == '__main__':
    main()
