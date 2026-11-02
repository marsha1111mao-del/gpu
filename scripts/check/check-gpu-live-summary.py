#!/usr/bin/env python3
"""Exercise warm BO summaries in the actual core and reject incorrect variants."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
source = (rmm / 'runtime/core/opencca_gpu_private.c').read_text()
fixture = rmm / 'runtime/tests/opencca_gpu_live_summary_test.c'
reference = rmm / 'runtime/tests/opencca_gpu_cache_set_test.c'
header = rmm / 'runtime/include/opencca_gpu_private.h'
start = source.index('bool gpu_private_task_live_eligible(')
end = source.index('\nbool gpu_private_task_flush_live(', start)
body = source[start:end]
variants = {'candidate': source}
replacements = {
    'no-invalidation': ('if (cache_metadata_epoch != 0UL)\n\t\tcache_metadata_epoch++;',
                        'if (cache_metadata_epoch != 0UL)\n\t\t(void)cache_metadata_epoch;'),
    'wrap-resumes': ('if (cache_metadata_epoch != 0UL)\n\t\tcache_metadata_epoch++;',
                     'cache_metadata_epoch++;'),
    'hit-no-barrier': ('return !set->live_uncached || ops->cache_barrier != NULL;',
                       'return true;'),
}
for name, (old, new) in replacements.items():
    assert source.count(old) == 1, name
    variants[name] = source.replace(old, new)
for name, old, new in [
    ('stale-map-epoch', 'set->epoch != ctx->mapping_epoch', 'false'),
    ('pending-reused', 'ctx->group_refs == 0U || ctx->pending != 0U ||',
                      'ctx->group_refs == 0U ||'),
    ('slot-reused', 'slot_owner[ctx->slot] != context', 'false'),
]:
    assert body.count(old) == 1, name
    variants[name] = source[:start] + body.replace(old, new) + source[end:]

# Inventory every BO predicate write, including memset and loop/if bodies.
# The production helper is the only conditional writer: an identical lease
# value does not change a predicate. All other writes invalidate immediately.
fields = 'owner|service|handle|cache_context|control|closing|resident|uncached|hidden|mapped|pages|control_gpu_refs'
write = re.compile(r'^(?:bo->(?:' + fields + r')|objects\[[^\n]+\]\.(?:' + fields + r'))\s*(?:=(?!=)|\+\+|--|\+=|-=)')
lines = source.splitlines()
writes = []
function = ''
for i, line in enumerate(lines):
    match = re.match(r'^(?:static )?(?:void|bool|unsigned int|unsigned long) (\w+)\(', line)
    if match:
        function = match.group(1)
    text = line.strip()
    if write.match(text) or text == 'memset(bo, 0, sizeof(*bo));':
        assert lines[i - 1].strip() == 'cache_metadata_invalidate();', (i + 1, text)
        writes.append(dict(function=function, line=i + 1, statement=text))
assert len(writes) == 36, writes
old = '\t\t\t\tcache_metadata_invalidate();\n\t\t\t\tbo->mapped++;'
assert source.count(old) == 1
variants['map-post-callback'] = source.replace(old, '\t\t\t\tbo->mapped++;')
records = []
for name, selected in variants.items():
    out = a.out / name
    out.mkdir()
    (out / 'opencca_gpu_private.c').write_text(selected)
    for f in [fixture, reference, header]:
        (out / f.name).write_bytes(f.read_bytes())
    command = [os.environ.get('HOST_CC', 'cc'), '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
               '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
               '-I' + str(out), str(out / fixture.name), '-o', str(out / 'test')]
    built = subprocess.run(command, capture_output=True, text=True)
    (out / 'build.log').write_text(built.stdout + built.stderr)
    assert built.returncode == 0, (name, built.stderr)
    scenarios = list(range(20)) if name == 'candidate' else {
        'no-invalidation': [10], 'wrap-resumes': [14], 'hit-no-barrier': [8],
        'stale-map-epoch': [4], 'pending-reused': [2], 'slot-reused': [5], 'map-post-callback': [18]
    }[name]
    results = []
    for scenario in scenarios:
        cmd = [str(out / 'test'), str(scenario)]
        done = subprocess.run(cmd, capture_output=True, text=True)
        (out / (str(scenario) + '.log')).write_text(done.stdout + done.stderr)
        if name == 'candidate':
            assert done.returncode == 0, (name, scenario, done.stderr)
        else:
            assert done.returncode == -6 and 'Assertion' in done.stderr, (name, scenario, done.returncode, done.stderr)
        results.append(dict(command=cmd, exit=done.returncode))
    records.append(dict(name=name, build_command=command, build_exit=built.returncode,
                        source_sha256=hashlib.sha256(selected.encode()).hexdigest(), runs=results))
record = dict(status='PASS', actual_core=True, warm_scenarios=20, rejected_mutants=7,
              writer_boundaries=writes, records=records, hardware='NOT_RUN',
              scope='Actual core with modeled AS/visibility/cache. Private BO metadata changes use production mutators; arbitrary attacker writes to RMM memory are not modeled as an authorized operation.',
              goal_complete=False)
(a.out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('GPU_PRIVATE_LIVE_SUMMARY=PASS warm=20 mutants=7 writes=36 ACTUAL_CORE_MODEL_ONLY')
