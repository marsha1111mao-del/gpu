#!/usr/bin/env python3
"""Cross-Client hostile RSI calls against actual RMM GPU cores and platform.

Uses the complete endpoint core and actual input-copy/IPA-translation helpers
with synthetic REC/S2 layouts, locks, slots, caches and device primitives.
Byte comparisons do not prove physical GPC or Linux concurrency.
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


def replace_once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


def function(path, name):
    source = path.read_text()
    match = re.search(r'^(?:static )?(?:bool|enum s2_walk_status) ' + name +
                      r'\([^;{}]*\)\s*\{', source, re.M)
    assert match, name
    return source[match.start():source.index('\n}', match.end()) + 2] + '\n'


copy = function(RMM / 'runtime/rsi/opencca_gpu_private.c', 'copy_page_input')
translate = function(RMM / 'runtime/rsi/realm_ipa_helper.c', 'realm_ipa_to_pa')
endpoint = (RMM / 'runtime/core/xshm_endpoint.c').read_text()
(out / 'identity-copy.inc').write_text(copy)
(out / 'identity-translate.inc').write_text(translate)
(out / 'endpoint.c').write_text(endpoint)

# The ordinary backend still uses its independent synthetic adapters. This
# checker replaces those adapters, not the production dispatcher/helper bodies.
header = (RMM / 'runtime/tests/opencca_gpu_domain_rsi_test.h').read_text()
start = header.index('struct rec {')
end = header.index('static unsigned long input_pages', start)
header = header[:start] + '#include "opencca_gpu_rsi_identity_test.h"\n' + header[end:]
header = replace_once(header, 'static bool domain_input_fault, domain_disconnected;',
                      'static bool domain_input_fault, identity_manual_input;')
start = header.index('static const void *xshm_endpoint_peer(')
end = header.index('bool opencca_gpu_isolate_service(', start)
header = header[:start] + header[end:]
header = replace_once(header,
    'struct rec rec = { .realm_info = {owner}, .regs = {0, op, handle, a, b, c, d, e} };',
    '''domain_identity_setup();
    unsigned int client = identity_index(owner);
    if (!identity_manual_input) {
        identity_reset();
        size_t bytes = op == GPU_PRIVATE_TASK_STAGE_BATCH ? c * sizeof(input_commands[0][0]) :
            op == GPU_PRIVATE_GROUP_CONFIGURE ? c * sizeof(input_queues[0][0]) :
            op == GPU_PRIVATE_BO_APPEND || op == GPU_PRIVATE_CONTROL_APPEND ? b * sizeof(unsigned long) : 0U;
        if (bytes && bytes <= GRANULE_SIZE && a) {
            memcpy(identity_device[client], (void *)(uintptr_t)a, bytes);
            a = IDENTITY_IPA;
            identity_mutate_source = true;
        }
        if (domain_input_fault) identity_entries[client] = IDENTITY_EMPTY;
    }
    struct rec rec = { .realm_info = { .g_rd = owner, .s2_ctx = identity_contexts[client] },
        .regs = {0, op, handle, a, b, c, d, e} };''')
header = replace_once(header,
    'res.action == UPDATE_REC_RETURN_TO_REALM);',
    '(identity_manual_input || res.action == UPDATE_REC_RETURN_TO_REALM));\n'
    '\tidentity_last_action = res.action; identity_last_level = res.rtt_level;\n'
    '\tassert(identity_locks == identity_unlocks);\n'
    '\tfor (unsigned int i = 0; i < 4U; i++)\n'
    '\t\tassert(!identity_tables[i].locked && !identity_tables[i].mapped && !identity_pages[i].mapped);')
header = replace_once(header,
    'domain_service_channel(const void *candidate)\n{ return candidate == &service ? 7UL : 99UL; }',
    'domain_service_channel(const void *candidate, const void *owner)\n'
    '{ domain_identity_setup(); unsigned int i = identity_index(owner); '
    'return candidate == &service && i < 2U ? domain_channels[i] : ULONG_MAX; }')
header = header.replace('domain_service_channel(s)', 'domain_service_channel(s, o)')
header = header.replace('o == &client_a ? 7UL : o == &client_b ? 8UL : 99UL',
                        'o == &client_a ? domain_channels[0] : o == &client_b ? domain_channels[1] : ULONG_MAX')
(out / 'opencca_gpu_domain_rsi_test.h').write_text(header)

boundary = (RMM / 'runtime/tests/opencca_gpu_rsi_boundary_test.h').read_text()
boundary = boundary.replace('client == 0U ? 8UL : 7UL', 'domain_channels[client ^ 1U]')
boundary = boundary.replace('client == 0U ? 7UL : 8UL', 'domain_channels[client]')
boundary = boundary.replace(', 7,', ', right_channel,')
boundary = replace_once(boundary, 'gpu_boundary_private_snapshot(true);',
    'domain_identity_setup();\n\tgpu_boundary_private_snapshot(true);')
boundary = replace_once(boundary,
    '\tprintf("GPU_RSI_BOUNDARY=PASS',
    '\tdomain_identity_boundary(context, group, token, bo, client, lifecycle);\n'
    '\tprintf("GPU_RSI_BOUNDARY=PASS')
(out / 'opencca_gpu_rsi_boundary_test.h').write_text(boundary)


def snapshot(name, fields):
    # Test-only appendage: no production statement or API is replaced.
    body = '\nvoid gpu_boundary_' + name + '_snapshot(bool save)\n{\n'
    for field in fields:
        body += (f' static unsigned char saved_{field}[sizeof({field})];\n'
                 f' if (save) memcpy(saved_{field}, &{field}, sizeof({field}));\n'
                 f' else assert(memcmp(saved_{field}, &{field}, sizeof({field})) == 0);\n')
    return body + '}\n'


private = RMM / 'runtime/core/opencca_gpu_private.c'
firmware = RMM / 'runtime/core/opencca_gpu_firmware.c'
private_copy = out / 'private.c'
firmware_copy = out / 'firmware.c'
private_copy.write_text(private.read_text() + snapshot('private', [
    'objects', 'contexts', 'cache_sets', 'cache_set_victim', 'backing',
    'backing_owner', 'tables', 'leaf_object', 'leaf_groups', 'table_owner',
    'slot_owner', 'next_id', 'map_grants',
]))
firmware_copy.write_text(firmware.read_text() + snapshot('firmware', [
    'image', 'sections', 'image_service', 'state', 'received', 'section_count',
    'memory_size', 'runtime_pages', 'runtime_tables', 'table_count', 'section_page',
    'control_object', 'control_pages', 'groups', 'control_user', 'group_generation',
    'heap_generation', 'tasks', 'task_generation', 'hardware_groups', 'resume_fast',
    'resume_fallback', 'suspend_finish_fast', 'suspend_finish_fallback', 'interfaces',
    'fw_storage', 'iface_range_count',
]))
fixture = (RMM / 'runtime/tests/opencca_gpu_backend_test.c').read_text()
fixture = replace_once(fixture,
    '#include "opencca_gpu_domain_rsi_test.h"',
    '#include "opencca_gpu_domain_rsi_test.h"\n'
    '#include "opencca_gpu_rsi_identity_boundary_test.h"\n'
    '#include "opencca_gpu_rsi_boundary_test.h"')
fixture = fixture.replace('client == 0U ? 7UL : 8UL', 'domain_channels[client]')
fixture = fixture.replace('owner == &client_a ? 7UL : owner == &client_b ? 8UL : 99UL',
                          'owner == &client_a ? domain_channels[0] : owner == &client_b ? domain_channels[1] : ULONG_MAX')
fixture = replace_once(fixture, 'domain_disconnected = true;', 'domain_identity_disconnect(owner);')
fixture = replace_once(fixture, 'domain_disconnected = false;', 'domain_identity_reconnect(owner);')
fixture = replace_once(fixture, 'context, 7, 2, 0, 0, 0, &r);',
                        'context, domain_channels[client], 2, 0, 0, 0, &r);')
fixture = replace_once(fixture, '(unsigned long)(uintptr_t)queues, 7, 2, 0, 0, &r);',
                        '(unsigned long)(uintptr_t)queues, domain_channels[client], 2, 0, 0, &r);')
fixture = replace_once(fixture, '(unsigned long)(uintptr_t)commands, 7UL, count, flags, 0UL, r);',
                        '(unsigned long)(uintptr_t)commands, domain_channels[0], count, flags, 0UL, r);')
fixture = replace_once(fixture,
    '\tunsigned int kept = 0U, yielded = 0U;',
    '\tunsigned int kept = 0U, yielded = 0U;\n'
    '\tif (domain_case == 1U) domain_rsi_boundary(context, group, token, prepared_bos[client], client, "running");')
fixture = replace_once(fixture,
    '\t\tassert(next != token && gpu_firmware_task_resources(&service, owner, next, &resources));',
    '\t\tassert(next != token && gpu_firmware_task_resources(&service, owner, next, &resources));\n'
    '\t\tif (cycle == 0U || cycle == 31U || cycle == 32U || cycle == 95U)\n'
    '\t\t\tdomain_rsi_boundary(context, group, next, prepared_bos[client], client, "staged-successor");')
(out / 'fixture.c').write_text(fixture)

subprocess.run(['python3', str(ROOT / 'scripts/check/check-gpu-domain-dispatch.py'),
                '--out', str(out), '--prepare-only'], check=True)
actual = (out / 'opencca_gpu_domain_dispatch.inc').read_text()
compiler = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer',
            '-fno-pie', '-no-pie', '-DGPU_DOMAIN_RSI_TEST', '-I' + str(out)]
compiler += ['-I' + str(RMM / p) for p in [
    'runtime/tests/mmio-stubs', 'runtime/tests', 'runtime/include',
    'ext/mbedtls/include', 'ext/mbedtls/library']]
sources = [RMM / p for p in ['plat/rk3588/src/rk3588_gpu.c',
           'runtime/core/opencca_gpu.c', 'runtime/core/opencca_gpu_lease.c']]
sources += [private_copy, firmware_copy]
sources += [RMM / p for p in ['ext/mbedtls/library/sha256.c',
                              'ext/mbedtls/library/platform_util.c']]
sources.append(out / 'fixture.c')
sources.append(out / 'endpoint.c')
results = []


def run_case(name, dispatcher, expected, copy_text=copy, translate_text=translate,
             endpoint_text=endpoint, oracle='GPU_RSI_BOUNDARY_REJECT'):
    # A separate include directory fixes each executable's exact dispatcher.
    case = out / name
    case.mkdir()
    (case / 'opencca_gpu_domain_dispatch.inc').write_text(dispatcher)
    (case / 'identity-copy.inc').write_text(copy_text)
    (case / 'identity-translate.inc').write_text(translate_text)
    # Keep fixture and generated headers beside each variant: quoted includes
    # must select this executable's dispatcher and helpers, not out's baseline.
    (case / 'opencca_gpu_rsi_identity_test.h').write_text(
        (RMM / 'runtime/tests/opencca_gpu_rsi_identity_test.h').read_text())
    (case / 'opencca_gpu_domain_rsi_test.h').write_text(header)
    (case / 'opencca_gpu_rsi_boundary_test.h').write_text(boundary)
    (case / 'fixture.c').write_text(fixture)
    (case / 'endpoint.c').write_text(endpoint_text)
    command = compiler[:1] + ['-I' + str(case)] + compiler[1:] + [str(p) for p in sources]
    command = [str(case / 'endpoint.c') if x == str(out / 'endpoint.c') else x for x in command]
    command = [str(case / 'fixture.c') if x == str(out / 'fixture.c') else x for x in command]
    command += ['-o', str(case / 'test')]
    with (case / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert built.returncode == 0, (name, 'build failure', built.returncode)
    with (case / 'run.log').open('w') as log:
        run = subprocess.run([str(case / 'test'), str(ROOT / 'GPU-SFTP/panthor_fw/mali_csffw.bin'),
                              '--domain-only'], stdout=log, stderr=subprocess.STDOUT)
    text = (case / 'run.log').read_text()
    assert 'runtime error:' not in text and 'ERROR: AddressSanitizer' not in text, (name, 'sanitizer failure')
    results.append(dict(name=name, command=command, build_exit=built.returncode,
                        run_exit=run.returncode,
                        matrix_passes=text.count('GPU_RSI_BOUNDARY=PASS'),
                        targeted_rejection=oracle in text,
                        integrated_matrices=text.count('GPU_RSI_IDENTITY=PASS')))
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    assert run.returncode == expected, (name, run.returncode, expected)
    if expected:
        assert oracle in text and 'Assertion' in text, (name, 'not rejected by intended oracle')
    else:
        assert text.count('GPU_RSI_BOUNDARY=PASS') == 10, 'missing lifecycle matrices'
        assert text.count('GPU_RSI_IDENTITY=PASS') == 10, 'missing integrated matrices'


run_case('candidate', actual, 0)
for name, begin, end, old, new in [
    ('wrong_inspect_peer', 'case GPU_PRIVATE_BO_INSPECT:', 'case GPU_PRIVATE_SERVICE_MAP:',
     'xshm_endpoint_peer(owner, handle, &peer_id)', 'xshm_endpoint_peer(owner, domain_channels[0], &peer_id)'),
    ('wrong_task_peer', 'case GPU_PRIVATE_TASK_VALIDATE:', 'case GPU_PRIVATE_GROUP_INSPECT:',
     'xshm_endpoint_peer(owner, a, &peer_id)', 'xshm_endpoint_peer(owner, domain_channels[0], &peer_id)'),
    ('ignore_reserved_d', 'case GPU_PRIVATE_TASK_VALIDATE:', 'case GPU_PRIVATE_GROUP_INSPECT:',
     '(d | e) != 0UL', 'e != 0UL'),
    ('ignore_reserved_e', 'case GPU_PRIVATE_TASK_VALIDATE:', 'case GPU_PRIVATE_GROUP_INSPECT:',
     '(d | e) != 0UL', 'd != 0UL'),
]:
    start = actual.index(begin)
    finish = actual.index(end, start)
    fragment = replace_once(actual[start:finish], old, new)
    run_case(name, actual[:start] + fragment + actual[finish:], -6)

for name, old, new, oracle in [
    ('input_skip_invalidate', 'inv_dcache_range((uintptr_t)input, bytes);',
     '(void)inv_dcache_range;', 'identity_invalidations == 1U'),
    ('input_skip_unlock', 'granule_unlock(walk.llt);', '(void)walk.llt;',
     'identity_locks == identity_unlocks'),
]:
    run_case(name, actual, -6, copy_text=replace_once(copy, old, new), oracle=oracle)
run_case('input_wrong_rec_table', actual, -6,
         translate_text=replace_once(translate, 's2_ctx = &(rec->realm_info.s2_ctx);',
                                     's2_ctx = &identity_contexts[0];'),
         oracle='GPU_RSI_IDENTITY_REJECT')
run_case('channel_allow_unaccepted', actual, -6,
         endpoint_text=replace_once(endpoint, 'channel->id != id || !channel->live',
                                     'channel->id != id'), oracle='GPU_RSI_IDENTITY_REJECT')
run_case('channel_allow_nonmember', actual, -6,
         endpoint_text=replace_once(endpoint,
             'else\n\t\t\treturn NULL;\n\t\tfor (unsigned int j',
             'else\n\t\t\tpeer = channel->endpoint[0];\n\t\tfor (unsigned int j'),
         oracle='GPU_RSI_IDENTITY_REJECT')

record = dict(status='PASS_ACTUAL_RSI_CROSS_CLIENT_BOUNDARY', checks=results,
              production_sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [private, firmware, RMM / 'runtime/rsi/opencca_gpu_private.c',
                                            RMM / 'runtime/rsi/realm_ipa_helper.c',
                                            RMM / 'runtime/core/xshm_endpoint.c']},
              scope='Actual dispatcher/copy/IPA translation/complete endpoint/core/platform; synthetic REC/S2/locks/slots/cache/device, private snapshots are test-only appendages',
              hardware_tests='NOT_RUN', goal_complete=False)
(out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(dict(status=record['status'], matrices=10, integrated_matrices=10, compiled_mutants_rejected=9,
                      evidence=str(out), models_only=True, goal_complete=False)))
