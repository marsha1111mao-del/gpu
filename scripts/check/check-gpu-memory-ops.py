#!/usr/bin/env python3
"""Actual private GPU memory callbacks/core/RTT with model cache/granules.

External shared/IOMMU/physical busy probes and RD/RTT/cache primitives remain
models. Does not prove real cache instructions, physical GPC or concurrency.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / 'opencca/tf-rmm'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
out = a.out.resolve()
out.mkdir(parents=True, exist_ok=False)
path = RMM / 'runtime/rsi/opencca_gpu_private.c'
source = path.read_text()
names = ['source_page', 'clear_page', 'write_page', 'read_page',
         'sync_page_for_device', 'sync_page_for_cpu', 'cache_barrier']
functions = {}
for name in names:
    match = re.search(r'^static bool ' + name + r'\([^;{}]*\)\s*\{', source, re.M)
    assert match, name
    functions[name] = source[match.start():source.index('\n}', match.end()) + 2] + '\n'
fixture = RMM / 'runtime/tests/opencca_gpu_memory_ops_test.c'
rtt_path = RMM / 'runtime/core/xshm_rtt.c'
rtt = rtt_path.read_text()
results = []


def run(name, bodies, rtt_text=rtt, mutant=False):
    case = out / name
    case.mkdir()
    (case / 'private-memory-ops.inc').write_text('\n'.join(bodies.values()))
    (case / 'rtt.c').write_text(rtt_text)
    command = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
               '-O2', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
               '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-I' + str(case)]
    command += ['-I' + str(RMM / x) for x in ['runtime/tests/rtt-stubs', 'runtime/tests', 'runtime/include']]
    command += [str(fixture), str(case / 'rtt.c'),
                str(RMM / 'runtime/core/opencca_gpu_private.c'), '-o', str(case / 'test')]
    with (case / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert built.returncode == 0, (name, 'build failure', case / 'build.log')
    with (case / 'run.log').open('w') as log:
        ran = subprocess.run([str(case / 'test')], stdout=log, stderr=subprocess.STDOUT)
    text = (case / 'run.log').read_text()
    results.append(dict(name=name, command=command, build_exit=built.returncode, run_exit=ran.returncode))
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    assert 'runtime error:' not in text and 'ERROR: AddressSanitizer' not in text, (name, 'sanitizer error')
    if mutant:
        assert ran.returncode == -6 and 'Assertion' in text and 'GPU_MEMORY_OPS_REJECT' in text, (name, 'expected oracle assertion', text)
    else:
        assert ran.returncode == 0 and 'GPU_MEMORY_OPS=PASS' in text, (name, text)
        print(text.strip(), flush=True)


run('actual', functions)
mutations = [
    ('skip_shared_guard', 'source_page', 'xshm_memory_range_busy(owner, ipa, GRANULE_SIZE)', 'false'),
    ('skip_private_guard', 'source_page', 'gpu_private_range_busy(owner, ipa, GRANULE_SIZE)', 'false'),
    ('skip_iommu_guard', 'source_page', 'opencca_iommu_range_busy(owner, ipa, GRANULE_SIZE)', 'false'),
    ('skip_physical_guard', 'source_page', '!opencca_gpu_page_busy(*pa)', '(true || opencca_gpu_page_busy(*pa))'),
    ('skip_read_invalidate', 'read_page', 'inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);', '(void)memory;'),
    ('skip_write_clean', 'write_page', 'clean_dcache_range((uintptr_t)memory + offset, bytes);', '(void)bytes;'),
    ('skip_scrub', 'clear_page', 'memset(memory, 0, GRANULE_SIZE);', '(void)memory;'),
    ('cpu_return_writes_back', 'sync_page_for_cpu', 'inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);', 'flush_dcache_range((uintptr_t)memory, GRANULE_SIZE);'),
    ('device_handoff_discards', 'sync_page_for_device', 'flush_dcache_range((uintptr_t)memory, GRANULE_SIZE);', '(void)flush_dcache_range; inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);'),
    ('skip_read_barrier', 'read_page', 'dsb(sy);', '(void)0;'),
    ('skip_data_unlock', 'write_page', 'granule_unlock(data);', '(void)data;'),
]
for name, function, old, new in mutations:
    changed = dict(functions)
    assert changed[function].count(old) == 1, name
    changed[function] = changed[function].replace(old, new, 1)
    run(name, changed, mutant=True)
summary = dict(status='PASS_ACTUAL_PRIVATE_MEMORY_CALLBACKS',
               extracted_functions=names, compiled_mutants_rejected=len(mutations),
               source_sha256={str(x.relative_to(ROOT)): hashlib.sha256(x.read_bytes()).hexdigest()
                              for x in [path, rtt_path, fixture, Path(__file__)]},
               cases=int(re.search(r'cases=(\d+)', (out / 'actual/run.log').read_text())[1]),
               models_only=True, hardware='NOT_RUN', goal_complete=False)
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
