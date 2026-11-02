#!/usr/bin/env python3
"""Run the actual RMI dispatcher/table/policy with checked host concurrency.

Leaves, ownership predicates, granules and SIMD are doubles; Arm spinlocks are
replaced by a checked pthread mutex. Does not test real RD creation, GPU or GPC.
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', required=True, type=Path)
parser.add_argument('--actual-only', action='store_true')
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
handler = RMM / 'runtime/core/handler.c'
policy = RMM / 'runtime/core/xshm_policy.c'
fixture = RMM / 'runtime/tests/opencca_gpu_rmi_dispatch_test.c'
source = handler.read_text()
begin = source.index('/* Maximum number of supported arguments */')
end = source.index('\n/*\n * Identifies an abort', begin)
dispatch = source[begin:end]
entries = re.findall(r'\bHANDLER\((\w+),\s*(\d),\s*(\d),\s*(\w+),\s*(?:true|false),\s*(?:true|false)\)', dispatch)
assert len(entries) == 28 and len({e[0] for e in entries}) == len(entries), entries
leaves = []
cases = []
for name, inputs, outputs, function in entries:
    count, result_count = int(inputs), int(outputs)
    parameters = [f'unsigned long a{i}' for i in range(count)]
    if result_count:
        parameters.append('struct smc_result *res')
    values = [f'a{i}' if i < count else '0UL' for i in range(5)]
    call = f'leaf(SMC_RMI_{name}, a, {"res" if result_count else "NULL"}, {result_count}U)'
    leaves.append(f'{"void" if result_count else "unsigned long"} {function}({", ".join(parameters) or "void"})\n'
                  '{\n\tconst unsigned long a[5] = {' + ', '.join(values) + '};\n\t' +
                  ('(void)' if result_count else 'return ') + call + ';\n}\n')
    cases.append(f'\t{{SMC_RMI_{name}, {count}U, {result_count}U}},')
texts = {
    'rmi-dispatch.inc': dispatch,
    'rmi-policy.c': policy.read_text(),
    'rmi-leaves.inc': '\n'.join(leaves),
    'rmi-cases.inc': 'static const struct { unsigned int fid, inputs, outputs; } cases[] = {\n' +
                     '\n'.join(cases) + '\n};\n',
    'granule.h': '#pragma once\nstruct granule { unsigned int unused; };\n'
                 'struct granule *find_granule(unsigned long pa);\n#define GRANULE_SHIFT 12U\n',
    's2tt.h': '#pragma once\n#include <assert.h>\n#define S2TT_PAGE_LEVEL 3L\n'
              'static inline unsigned long s2tte_map_size(long level)\n'
              '{ assert(level >= -1L && level <= 3L); return 1UL << (12L + 9L * (3L - level)); }\n',
    'spinlock.h': '#pragma once\ntypedef unsigned int spinlock_t;\n'
                  'void test_spinlock_acquire(spinlock_t *lock);\n'
                  'void test_spinlock_release(spinlock_t *lock);\n'
                  '#define spinlock_acquire test_spinlock_acquire\n'
                  '#define spinlock_release test_spinlock_release\n',
}
results = []


def run(name, files, fpu, oracle=None):
    case = out / name
    case.mkdir()
    for path, content in files.items():
        (case / path).write_text(content)
    command = [os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
               '-O2', '-g', '-pthread', '-fsanitize=address,undefined',
               '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-MMD',
               '-I' + str(case)]
    if fpu:
        command.append('-DRMM_FPU_USE_AT_REL2')
    command += ['-I' + str(RMM / p) for p in ['lib/smc/include', 'lib/common/include', 'runtime/include']]
    command += [str(fixture), str(case / 'rmi-policy.c'), '-o', str(case / 'test')]
    with (case / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    entry = dict(name=name, command=command, build_exit=built.returncode, fpu=fpu, oracle=oracle)
    results.append(entry)
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    assert built.returncode == 0, (name, 'compile failure', case / 'build.log')
    with (case / 'run.log').open('w') as log:
        ran = subprocess.run([str(case / 'test')], stdout=log, stderr=subprocess.STDOUT, timeout=30)
    entry['run_exit'] = ran.returncode
    entry['invocation'] = [str(case / 'test')]
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    log = (case / 'run.log').read_text()
    assert 'runtime error:' not in log and 'ERROR: AddressSanitizer' not in log, (name, 'sanitizer failure')
    if oracle is None:
        assert ran.returncode == 0 and 'GPU_RMI_DISPATCH=PASS' in log, (name, log)
        print(log.strip(), flush=True)
    else:
        expected = (f"Assertion `{oracle.removeprefix('production:')}' failed."
                    if oracle.startswith('production:') else f'GPU_RMI_DISPATCH_REJECT {oracle}\n')
        assert ran.returncode == -6 and expected in log, (name, log)
        print(f'GPU_RMI_DISPATCH_MUTANT_REJECTED={name}', flush=True)


run('actual-no-fpu', texts, False)
run('actual-fpu', texts, True)
mutations = [
    ('skip_gate', 'rmi-dispatch.inc', '\t\txshm_policy_lock();', '\t\t(void)0;',
     'authorization lookup executes under policy gate'),
    ('skip_policy', 'rmi-dispatch.inc', 'if (!xshm_rmi_allowed(function_id, arg0, arg1, arg2, arg3))',
     'if (!(xshm_rmi_allowed(function_id, arg0, arg1, arg2, arg3) || true))',
     'busy policy rejection never calls a leaf'),
    ('clear_status_only', 'rmi-dispatch.inc', 'i < SMC_RESULT_REGS', 'i < 1U',
     'policy rejection clears every result register'),
    ('skip_unlock', 'rmi-dispatch.inc', '\t\txshm_policy_unlock();', '\t\t(void)0;',
     'return balances policy gate and SIMD state'),
    ('gate_rec_enter', 'rmi-dispatch.inc', 'function_id != SMC_RMI_REC_ENTER', 'true',
     'handler executes inside its required gate'),
    ('authorization_gap', 'rmi-dispatch.inc', '\n\tswitch (handler->type)',
     '\n\tif (function_id != SMC_RMI_REC_ENTER) { xshm_policy_unlock(); xshm_policy_lock(); }\n\tswitch (handler->type)',
     'authorization and execution share one uninterrupted gate'),
    ('wrong_policy_owner', 'rmi-dispatch.inc', 'xshm_rmi_allowed(function_id, arg0, arg1, arg2, arg3)',
     'xshm_rmi_allowed(function_id, arg0 + 4096UL, arg1, arg2, arg3)',
     'busy policy rejection never calls a leaf'),
    ('skip_private_guard', 'rmi-policy.c', '!gpu_private_owner_busy(owner) &&', 'true &&',
     'busy policy rejection never calls a leaf'),
    ('skip_range_guard', 'rmi-policy.c', '!gpu_private_range_busy(owner, base, size) &&', 'true &&',
     'busy policy rejection never calls a leaf'),
    ('swap_leaf_args', 'rmi-dispatch.inc', 'handler->f_20(arg0, arg1)', 'handler->f_20(arg1, arg0)',
     'all argument positions retain their ABI order'),
    ('skip_sve_normalization', 'rmi-dispatch.inc', 'function_id &= ~SMC_SVE_HINT;', '(void)function_id;',
     'known dispatch checks CPU slots before and after'),
    ('skip_simd_restore', 'rmi-dispatch.inc', 'simd_context_restore(ns_simd_ctx);', '(void)ns_simd_ctx;',
     'production:simd_is_state_saved() == false'),
]
if not args.actual_only:
    for name, filename, old, new, oracle in mutations:
        assert old in texts[filename], name
        changed = dict(texts)
        changed[filename] = changed[filename].replace(old, new)
        run(name, changed, True, oracle)
dependencies = {handler, policy, fixture, Path(__file__).resolve()}
for depfile in (out / 'actual-fpu').glob('*.d'):
    tokens = depfile.read_text().replace('\\\n', ' ').split(':', 1)[1].split()
    dependencies.update(Path(p).resolve() for p in tokens if Path(p).resolve().is_relative_to(ROOT) and
                        not Path(p).resolve().is_relative_to(out))
summary = dict(status='PASS', results=results, mutated_builds=0 if args.actual_only else len(mutations),
               source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(dependencies)},
               scope='Production RMI dispatcher/table/FID headers/policy/lock wrappers; checked pthread mutex and '
                     'two actual host threads. Leaf handlers, busy predicates, granules and SIMD are doubles. '
                     'No real Arm lock instructions, RD creation/destruction, REC concurrency, GPU or physical GPC.',
               goal_complete=False)
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print('GPU_RMI_DISPATCH_CHECK=PASS', flush=True)
