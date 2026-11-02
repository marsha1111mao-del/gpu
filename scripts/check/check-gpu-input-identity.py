#!/usr/bin/env python3
"""Actual GPU RSI input copy, IPA translation and endpoint identity policy.

REC layout, S2 descriptors, memory slots, locks and caches remain host models.
No GPU workload, physical GPC denial, or Linux concurrency is exercised here.
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
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)


def function(path, name):
    source = path.read_text()
    match = re.search(r'^(?:static )?(?:bool|enum s2_walk_status) ' + name +
                      r'\([^;{}]*\)\s*\{', source, re.M)
    assert match, name
    return source[match.start():source.index('\n}', match.end()) + 2] + '\n'


def replace_once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


copy_path = RMM / 'runtime/rsi/opencca_gpu_private.c'
translate_path = RMM / 'runtime/rsi/realm_ipa_helper.c'
peer_path = RMM / 'runtime/core/xshm_endpoint.c'
fixture = RMM / 'runtime/tests/opencca_gpu_input_identity_test.c'
copy = function(copy_path, 'copy_page_input')
translate = function(translate_path, 'realm_ipa_to_pa')
peer = peer_path.read_text()
results = []


def run_case(name, copy_text, translate_text, peer_text, modes, mutant=False):
    case = out / name
    case.mkdir()
    (case / 'input-copy.inc').write_text(copy_text)
    (case / 'input-translate.inc').write_text(translate_text)
    (case / 'endpoint.c').write_text(peer_text)
    command = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
               '-Werror', '-O2', '-g', '-fsanitize=address,undefined',
               '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer',
               '-fno-pie', '-no-pie', '-I' + str(case),
               '-I' + str(RMM / 'runtime/include'), str(fixture),
               str(case / 'endpoint.c'), '-o', str(case / 'test')]
    with (case / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert built.returncode == 0, (name, 'build failed', case / 'build.log')
    for mode in modes:
        with (case / (mode + '.log')).open('w') as log:
            run = subprocess.run([str(case / 'test'), mode], stdout=log,
                                 stderr=subprocess.STDOUT)
        log = (case / (mode + '.log')).read_text()
        results.append(dict(name=name, mode=mode, build_command=command,
                            build_exit=built.returncode, run_exit=run.returncode))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        if mutant:
            # Require an oracle assertion, not just sanitizer/crash output.
            assert run.returncode == -6 and 'Assertion' in log, (name, log)
        else:
            assert run.returncode == 0 and '=PASS' in log, (name, log)
            print(log.strip(), flush=True)


run_case('actual', copy, translate, peer, ['copy', 'peer'])
for name, old, new in [
    ('skip_alignment_guards', '!GRANULE_ALIGNED(ipa)', 'false'),
    ('skip_par_guards', '!addr_in_rec_par(rec, ipa)',
     '(false && !addr_in_rec_par(rec, ipa))'),
    ('skip_invalidate', 'inv_dcache_range((uintptr_t)input, bytes);',
     '(void)inv_dcache_range;'),
    ('skip_unlock', 'granule_unlock(walk.llt);', '(void)walk.llt;'),
]:
    # The translation helper repeats both address guards. Removing only the
    # outer guard is safe redundancy, so exercise regression of both layers.
    translated = replace_once(translate, old, new) if name in (
        'skip_alignment_guards', 'skip_par_guards') else translate
    run_case(name, replace_once(copy, old, new), translated, peer, ['copy'], True)
run_case('skip_block_offset', copy,
         replace_once(translate, 's2_walk->pa += offset;', '(void)offset;'),
         peer, ['copy'], True)
for name, old, new in [
    ('allow_unaccepted_peer', 'channel->id != id || !channel->live', 'channel->id != id'),
    ('skip_peer_zero', '*peer_id = 0UL;', '(void)peer_id;'),
    ('allow_nonmember_peer', 'else\n\t\t\treturn NULL;\n\t\tfor (unsigned int j',
     'else\n\t\t\tpeer = channel->endpoint[0];\n\t\tfor (unsigned int j'),
]:
    run_case(name, copy, translate, replace_once(peer, old, new), ['peer'], True)

record = dict(status='PASS_GPU_INPUT_IDENTITY_MODELS', checks=results,
              source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [copy_path, translate_path, peer_path, fixture, Path(__file__)]},
              compiled_mutants_rejected=8,
              scope='Unmodified extracted copy_page_input and realm_ipa_to_pa; complete actual endpoint core. Synthetic REC/S2 descriptors/slots/locks/cache.',
              hardware_tests='NOT_RUN', goal_complete=False)
(out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(dict(status=record['status'], compiled_mutants_rejected=8,
                      evidence=str(out), models_only=True, goal_complete=False)))
