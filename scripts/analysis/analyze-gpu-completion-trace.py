#!/usr/bin/env python3
"""Measure full native fence callback to first Client proof observation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy


ROOT = Path(__file__).resolve().parents[2]


def counters(path):
    return {key: int(value) for key, value in
            re.findall(r'\b(\w+)=(\d+)\b', path.read_text())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-rpc-paths', action='store_true')
    args = parser.parse_args()
    runpy.run_path(str(ROOT / 'scripts/analysis/summarize-fair-glmark.py'))['verify_collection'](args.run)
    helpers = runpy.run_path(str(ROOT / 'scripts/analysis/analyze-xshm-notify-trace.py'))
    read_trace, distribution = helpers['read_trace'], helpers['distribution']
    summary = json.loads((args.run / 'summary.json').read_text())
    assert summary['status'] == 'PASS' and summary['completion_trace']
    columns = 'kind channel sequence type flags status tick0 tick1 tick2 tick3 tick4'.split()
    client_meta, client = read_trace(args.run / 'notify-realm-1.log', 'XSHM_TRACE', columns)
    proxy_meta, proxy = read_trace(args.run / 'notify-realm-0.log', 'XSHM_TRACE', columns)
    assert client_meta['freq'] == proxy_meta['freq']
    frequency = int(client_meta['freq'])
    brackets = Counter()
    for role, records in (('client', client), ('proxy', proxy)):
        for record in records:
            if record['kind'] != 1:
                continue
            assert record['status'] == 0 and record['flags'] & 6 == 0
            before, after, entered, locked, ended = [record['tick' + str(index)] for index in range(5)]
            assert 0 < before <= entered <= locked <= ended <= after
            brackets[role] += 1
    assert brackets['client'] >= 100 and brackets['proxy'] > 0
    records = [record for record in client if record['kind'] == 3]
    assert len({(record['channel'], record['sequence']) for record in records}) == len(records)
    for record in records:
        assert record['status'] == 0 and record['flags'] in (1, 2) and 1 <= record['type'] <= 6
        assert record['tick4'] == frequency
        assert 0 < record['tick0'] <= record['tick1'] <= record['tick2'] <= record['tick3']
        assert record['tick0'] % (frequency // 10) < frequency // 500
    native = [record for record in records if record['flags'] == 1]
    immediate = [record for record in records if record['flags'] == 2]
    assert len(native) >= 100, 'not enough real callback observations'
    client_counts = counters(args.run / 'completion-stats-realm-1.log')
    proxy_counts = counters(args.run / 'completion-stats-realm-0.log')
    rpc_covered = 'rpc_successes' in client_counts
    if args.require_rpc_paths:
        assert rpc_covered and client_counts['rpc_successes'] > 0
        assert any(record['type'] >= 4 for record in native), 'RPC success path was not observed'
    assert client_counts['metadata_errors'] == 0
    assert client_counts['completion_samples'] == len(records)
    assert client_counts['first_seen'] == client_counts['unsampled'] + len(records)
    unobserved = {'callbacks': proxy_counts['sampled_callbacks'] - len(native),
                  'immediate': proxy_counts['sampled_immediate'] - len(immediate)}
    assert min(unobserved.values()) >= 0
    pending = proxy_counts['requested'] - sum(proxy_counts[key] for key in
              ('callbacks', 'immediate', 'errors', 'slot_full', 'cancelled', 'watch_failed'))
    assert pending >= 0

    def summarize(selected):
        fields = {'callback_to_publication_pre_store': ('tick1', 'tick0'),
                  'publication_to_client_proof': ('tick2', 'tick1'),
                  'callback_to_client_proof': ('tick2', 'tick0'),
                  'client_metadata_read': ('tick3', 'tick2')}
        return {name: distribution([(record[end] - record[start]) * 1e6 / frequency
                                    for record in selected])
                for name, (end, start) in fields.items()}

    observed_ticks = [record['tick0'] for record in native]
    result = {'status': 'PASS', 'run_id': summary['run_id'], 'frequency': frequency,
              'analysis_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'metadata': {'client': client_meta, 'proxy': proxy_meta},
              'clock_brackets': dict(brackets), 'client_counts': client_counts,
              'proxy_counts': proxy_counts, 'sampled_unobserved': unobserved,
              'pending_watches_at_collection': pending,
              'real_callback': summarize(native),
              'by_path': {name: summarize([record for record in native if record['type'] == path])
                          for path, name in (
                              (1, 'snapshot_worker_poll' if rpc_covered else 'snapshot_initial'),
                              (2, 'timeline_local_proof'), (3, 'binary_local_poll'),
                              (4, 'snapshot_worker_rpc'), (5, 'timeline_rpc'), (6, 'binary_rpc'))},
              'rpc_observation_coverage': {
                  'instrumented': rpc_covered,
                  'successful_confirmations': client_counts.get('rpc_successes'),
                  'without_tracked_proof': client_counts.get('rpc_without_proof')},
              'already_signaled_at_registration': {
                  'count': len(immediate),
                  'registration_to_client_proof': distribution([
                      (record['tick2'] - record['tick0']) * 1e6 / frequency for record in immediate])},
              'callback_sample_span_seconds': (max(observed_ticks) - min(observed_ticks)) / frequency,
              'sample_windows': len({tick // (frequency // 10) for tick in observed_ticks}),
              'limits': ['Start is the complete native fence callback, not an independent GPU hardware timestamp.',
                         'Already-signaled registration observations are excluded from true completion latency.',
                         'End is the first exact-cookie Client proof acceptance, before userspace syscall return.',
                         'Each cookie is observed once; multiple watches may refer to the same underlying fence.',
                         'Sampled completions never queried by Client remain explicitly unobserved.',
                         'The publication timestamp precedes the release store by a few instructions.']}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in
                      ('status', 'run_id', 'real_callback', 'by_path',
                       'already_signaled_at_registration', 'sampled_unobserved',
                       'pending_watches_at_collection')}, indent=2))


if __name__ == '__main__':
    main()
