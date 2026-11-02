#!/usr/bin/env python3
"""Actual RSI/endpoint/snapshot/RTT/memory/private-PT chain; host primitives.

Optional task chain models launch/completion with actual memory callbacks.
Does not test shader execution, real GPC/TLBI/cache instructions or concurrent RECs.
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
parser.add_argument('--task-chain', action='store_true', help='include modeled firmware and two-Client task lifecycle')
parser.add_argument('--realm-lifecycle', action='store_true', help='actual RMI policy/Realm destruction followed by modeled RD address reuse')
parser.add_argument('--actual-only', action='store_true', help='run real-source scenarios without mutation checks')
args = parser.parse_args()
if args.realm_lifecycle:
    args.task_chain = True
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
private = RMM / 'runtime/rsi/opencca_gpu_private.c'
translate = RMM / 'runtime/rsi/realm_ipa_helper.c'
busy = RMM / 'runtime/rsi/opencca_gpu.c'


def extract(path, name):
    source = path.read_text()
    match = re.search(r'^(?:static )?(?:bool|void|unsigned long|int|enum s2_walk_status) ' + name + r'\([^;{}]*\)\s*\{', source, re.M)
    assert match, name
    return source[match.start():source.index('\n}', match.end()) + 2] + '\n'


memory_names = ['source_page', 'clear_page', 'write_page', 'read_page',
                'sync_page_for_device', 'sync_page_for_cpu', 'cache_barrier']
texts = {
    'chain-memory.inc': '\n'.join(extract(private, n) for n in memory_names),
    'chain-copy.inc': extract(private, 'copy_page_input'),
    'chain-translate.inc': extract(translate, 'realm_ipa_to_pa'),
    'chain-busy.inc': extract(busy, 'opencca_gpu_page_busy'),
    'chain-dispatch.inc': '\n'.join(extract(private, n) for n in ['task_heap_call', 'handle_rsi_opencca_gpu_private']),
}
if args.task_chain:
    texts['chain-lifecycle.inc'] = '\n'.join([
        extract(private, 'opencca_gpu_private_device_revoked'),
        extract(private, 'opencca_gpu_private_reclaim'),
        extract(busy, 'smc_opencca_gpu_pm'),
        extract(busy, 'handle_rsi_opencca_gpu_control'),
    ])
if args.realm_lifecycle:
    realm = RMM / 'runtime/rmi/realm.c'
    texts['chain-realm-actual.inc'] = '\n'.join([
        extract(RMM / 'runtime/core/xshm_policy.c', 'xshm_rmi_allowed'),
        extract(busy, 'opencca_gpu_pm_destroy_allowed'),
        extract(busy, 'opencca_gpu_release_realm_mappings'),
        extract(RMM / 'runtime/rsi/xshm.c', 'opencca_xshm_release_realm'),
        extract(realm, 'free_sl_rtts'),
        extract(realm, 'total_root_rtt_refcount'),
        extract(realm, 'smc_realm_destroy'),
    ])
copied_sources = {
    'chain-core.c': RMM / 'runtime/core/opencca_gpu_private.c',
    'chain-endpoint.c': RMM / 'runtime/core/xshm_endpoint.c',
    'chain-rtt.c': RMM / 'runtime/core/xshm_rtt.c',
}
texts.update({name: path.read_text() for name, path in copied_sources.items()})
sources = [
    'plat/rk3588/src/rk3588_gpu.c', 'runtime/core/opencca_gpu.c',
    'runtime/core/opencca_gpu_lease.c', 'runtime/core/opencca_gpu_firmware.c',
    'ext/mbedtls/library/sha256.c',
    'ext/mbedtls/library/platform_util.c',
    ('runtime/tests/opencca_gpu_rsi_realm_lifecycle_test.c' if args.realm_lifecycle else
     'runtime/tests/opencca_gpu_rsi_task_chain_test.c' if args.task_chain else 'runtime/tests/opencca_gpu_rsi_memory_chain_test.c'),
]
results = []
oracles = {
    'skip_input_invalidate': 'expected successful RSI request',
    'skip_physical_busy': 'real legacy GPU lease denies source page',
    'skip_shared_busy': 'hostile RSI request denied',
    'skip_iommu_busy': 'hostile RSI request denied',
    'skip_scrub': 'scrub published before restoring WB',
    'skip_handoff_flush': 'handoff flushes each real backing page',
    'skip_input_unlock': 'valid serialized granule lock',
    'skip_private_busy': 'hostile RSI request denied',
    'resolve_as_service': 'hostile RSI request denied',
    'allow_unaccepted_peer': 'hostile RSI request denied',
    'restore_nc_as_wb': 'scrub published before restoring WB',
    'skip_write_clean': 'trusted control write reaches device bytes',
    'task_skip_device_flush': 'READY flushes actual two Client pages',
    'task_skip_cpu_invalidate': 'exact two data-page CPU returns',
    'task_skip_control_invalidate': 'bounded complete/return/retire continuation',
    'revoke_skip_private': 'revoked contexts release after trusted reset',
    'revoke_skip_firmware': 'revoked firmware group handle is stale',
    'revoke_on_failure': 'failed reset retains task references',
    'revoke_accept_host_error': 'malformed Host reset rejected without side effects',
    'revoke_allow_proxy_reset': 'Realm reset cannot bypass trusted mediated control',
    'reclaim_ignore_rec_refs': 'Host reclaim must prove dead REC-free non-NEW owner and trusted revocation',
    'reclaim_allow_new_rd': 'Host reclaim must prove dead REC-free non-NEW owner and trusted revocation',
    'reclaim_keep_bo_service': 'recycled service RD cannot inspect living Client BO',
    'reclaim_keep_context_service': 'recycled service RD cannot inspect living Client context',
    'reclaim_skip_live_scrub': 'scrub published before restoring WB',
    'destroy_skip_private_policy': 'RMI policy blocks destroy while private registrations remain',
    'destroy_skip_rec_guard': 'existing REC blocks destroy before RTT traversal',
    'destroy_skip_root_guard': 'nonempty RTT must reject destroy before VMID release',
    'destroy_skip_endpoint_release': 'actual Realm destroy releases endpoint and pending IRQ identity',
    'destroy_skip_gpu_release': 'destroyed GPU owner is detached before RD reuse',
    'destroy_skip_rd_scrub': 'RD transition follows complete metadata scrub',
    'destroy_skip_rtt_scrub': 'RTT transition follows complete table scrub',
    'destroy_keep_old_channel': 'destroyed Realm removes old channel event authority',
}


def run(name, changed, mutant=False):
    case = out / name
    case.mkdir()
    for path, content in changed.items():
        (case / path).write_text(content)
    command = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
               '-O2', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
               '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-MMD', '-I' + str(case)]
    command += ['-I' + str(RMM / p) for p in ['runtime/tests/rtt-stubs', 'runtime/tests/mmio-stubs',
                'runtime/include', 'ext/mbedtls/include', 'ext/mbedtls/library']]
    command += [str(RMM / p) for p in sources] + [str(case / name) for name in copied_sources] + ['-o', str(case / 'test')]
    with (case / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert built.returncode == 0, (name, 'build failure', case / 'build.log')
    scenarios = [7, 8] if args.realm_lifecycle else list(range(7)) if args.task_chain and not mutant else [0]
    if name.startswith('destroy_'):
        scenarios = [8 if name == 'destroy_skip_gpu_release' else 7]
    if name.startswith('revoke_'):
        scenarios = [3 if name == 'revoke_on_failure' else 4]
    if name.startswith('reclaim_'):
        scenarios = [6]
    for scenario in scenarios:
        invocation = [str(case / 'test')]
        if args.task_chain:
            invocation += [str(ROOT / 'GPU-SFTP/panthor_fw/mali_csffw.bin'), str(scenario)]
        logfile = case / ('run.log' if scenario == 0 else f'run-{scenario}.log')
        with logfile.open('w') as log:
            ran = subprocess.run(invocation, stdout=log, stderr=subprocess.STDOUT, timeout=60)
        log = logfile.read_text()
        results.append(dict(name=name, scenario=scenario, command=command, invocation=invocation,
                            build_exit=built.returncode, run_exit=ran.returncode))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        assert 'runtime error:' not in log and 'ERROR: AddressSanitizer' not in log, (name, 'sanitizer failure')
        if mutant:
            expected = 'GPU_RSI_MEMORY_CHAIN_REJECT ' + oracles[name]
            assert ran.returncode == -6 and 'Assertion' in log and expected in log, (name, 'expected oracle assertion', expected, log)
        else:
            marker = 'GPU_RSI_TASK_CHAIN=PASS' if args.task_chain else 'GPU_RSI_MEMORY_CHAIN=PASS'
            assert ran.returncode == 0 and marker in log, (name, log)
            print(log.strip(), flush=True)


run('actual', texts)
mutations = [
    ('skip_input_invalidate', 'chain-copy.inc', 'inv_dcache_range((uintptr_t)input, bytes);', '(void)input;'),
    ('skip_physical_busy', 'chain-memory.inc', '!opencca_gpu_page_busy(*pa)', '(true || opencca_gpu_page_busy(*pa))'),
    ('skip_shared_busy', 'chain-memory.inc', 'xshm_memory_range_busy(owner, ipa, GRANULE_SIZE)', 'false'),
    ('skip_iommu_busy', 'chain-memory.inc', 'opencca_iommu_range_busy(owner, ipa, GRANULE_SIZE)', 'false'),
    ('skip_scrub', 'chain-memory.inc', 'memset(memory, 0, GRANULE_SIZE);', '(void)memory;'),
    ('skip_handoff_flush', 'chain-memory.inc', 'flush_dcache_range((uintptr_t)memory, GRANULE_SIZE);', '(void)flush_dcache_range;'),
    ('skip_input_unlock', 'chain-copy.inc', 'granule_unlock(walk.llt);', '(void)walk.llt;'),
    ('skip_private_busy', 'chain-memory.inc', 'gpu_private_range_busy(owner, ipa, GRANULE_SIZE)', 'false'),
    ('resolve_as_service', 'chain-core.c', '!ops->source_page(owner, ipas[i], &pa)', '!ops->source_page(bo->service, ipas[i], &pa)'),
    ('allow_unaccepted_peer', 'chain-endpoint.c', 'channel->id != id || !channel->live', 'channel->id != id'),
    ('restore_nc_as_wb', 'chain-rtt.c', '(0x5UL << 2U)', '(0xfUL << 2U)'),
    ('skip_write_clean', 'chain-memory.inc', 'clean_dcache_range((uintptr_t)memory + offset, bytes);', '(void)bytes;'),
]
if args.actual_only or args.realm_lifecycle:
    mutations = []
for name, path, old, new in mutations:
    changed = dict(texts)
    assert changed[path].count(old) == 1, name
    changed[path] = changed[path].replace(old, new, 1)
    run(name, changed, True)
if args.task_chain and not args.realm_lifecycle and not args.actual_only:
    for name, function, old, new in [
        ('task_skip_device_flush', 'sync_page_for_device',
         'flush_dcache_range((uintptr_t)memory, GRANULE_SIZE);',
         'if (!domain_active) flush_dcache_range((uintptr_t)memory, GRANULE_SIZE);'),
        ('task_skip_cpu_invalidate', 'sync_page_for_cpu',
         'inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);',
         'if (!domain_active) inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);'),
        ('task_skip_control_invalidate', 'read_page',
         'inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);',
         'if (!domain_active) inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);'),
    ]:
        changed = dict(texts)
        original = extract(private, function)
        assert original.count(old) == 1, name
        changed['chain-memory.inc'] = changed['chain-memory.inc'].replace(original, original.replace(old, new), 1)
        run(name, changed, True)
    revoke_mutations = [
        ('revoke_skip_private', 'gpu_private_device_revoked(&operations);', '(void)operations;'),
        ('revoke_skip_firmware', 'gpu_firmware_device_revoked();', '(void)0;'),
        ('revoke_on_failure', 'if (accepted && (operation == OPENCCA_GPU_RELEASE ||',
         'if ((accepted || (operation == OPENCCA_GPU_RESET && argument == 0UL && error == 0UL)) && (operation == OPENCCA_GPU_RELEASE ||'),
        ('revoke_accept_host_error', 'argument, error);', 'argument, 0UL);'),
        ('revoke_allow_proxy_reset', 'opencca_gpu_control(&gpu_ops, rec->realm_info.g_rd,',
         'opencca_gpu_control(&gpu_ops, NULL,'),
    ]
    for name, old, new in revoke_mutations:
        changed = dict(texts)
        assert changed['chain-lifecycle.inc'].count(old) == 1, name
        changed['chain-lifecycle.inc'] = changed['chain-lifecycle.inc'].replace(old, new, 1)
        run(name, changed, True)
    reclaim_mutations = [
        ('reclaim_ignore_rec_refs', 'chain-lifecycle.inc',
         'dead = granule_refcount_read(owner) == 0U;',
         'dead = true; (void)granule_refcount_read(owner);'),
        ('reclaim_allow_new_rd', 'chain-lifecycle.inc',
         'dead = dead && (get_rd_state_locked(rd) == REALM_ACTIVE ||\n\t\t       get_rd_state_locked(rd) == REALM_SYSTEM_OFF);',
         'dead = dead && get_rd_state_locked(rd) != 99U;'),
        ('reclaim_keep_bo_service', 'chain-core.c',
         'objects[i].service = NULL;', '(void)objects[i].service;'),
        ('reclaim_keep_context_service', 'chain-core.c',
         'ctx->service = NULL;', '(void)ctx->service;'),
        ('reclaim_skip_live_scrub', 'chain-memory.inc',
         'memset(memory, 0, GRANULE_SIZE);', 'if (!domain_active) memset(memory, 0, GRANULE_SIZE);'),
    ]
    for name, path, old, new in reclaim_mutations:
        changed = dict(texts)
        assert changed[path].count(old) == 1, name
        changed[path] = changed[path].replace(old, new, 1)
        run(name, changed, True)
    mutant_count = len(mutations) + 3 + len(revoke_mutations) + len(reclaim_mutations)
else:
    mutant_count = len(mutations)
if args.realm_lifecycle and not args.actual_only:
    realm_mutations = [
        ('destroy_skip_private_policy', 'chain-realm-actual.inc', '!gpu_private_owner_busy(owner) &&', 'true &&'),
        ('destroy_skip_rec_guard', 'chain-realm-actual.inc',
         'res = find_lock_unused_granule(rd_addr, GRANULE_STATE_RD, &g_rd);',
         '(void)find_lock_unused_granule; g_rd = find_lock_granule(rd_addr, GRANULE_STATE_RD); res = g_rd == NULL ? -EINVAL : 0;'),
        ('destroy_skip_root_guard', 'chain-realm-actual.inc', 'if (root_refcount != 0UL)', 'if (root_refcount == ~0UL)'),
        ('destroy_skip_endpoint_release', 'chain-realm-actual.inc', 'opencca_xshm_release_realm(g_rd);', '(void)g_rd;'),
        ('destroy_skip_gpu_release', 'chain-realm-actual.inc', 'opencca_gpu_release_realm_mappings(g_rd);', '(void)g_rd;'),
        ('destroy_skip_rd_scrub', 'chain-realm-actual.inc', 'buffer_granule_memzero(g_rd, SLOT_RD);', '(void)g_rd;'),
        ('destroy_skip_rtt_scrub', 'chain-realm-actual.inc', 'buffer_granule_memzero(g, SLOT_RTT);', '(void)g;'),
        ('destroy_keep_old_channel', 'chain-endpoint.c', 'channels[i] = (struct xshm_channel){0};', '(void)channels[i];'),
    ]
    for name, path, old, new in realm_mutations:
        changed = dict(texts)
        assert changed[path].count(old) == 1, name
        changed[path] = changed[path].replace(old, new, 1)
        run(name, changed, True)
    mutant_count = len(realm_mutations)
dependencies = {private, translate, busy, Path(__file__), RMM / 'runtime/tests/opencca_gpu_backend_test.c',
                RMM / 'runtime/tests/opencca_gpu_rsi_memory_chain_test.c',
                RMM / 'runtime/tests/rtt-stubs/control_rtt_model.h'}
if args.task_chain:
    dependencies.add(ROOT / 'GPU-SFTP/panthor_fw/mali_csffw.bin')
if args.realm_lifecycle:
    dependencies.update(RMM / p for p in ['runtime/rmi/realm.c', 'runtime/core/xshm_policy.c',
                                         'runtime/rsi/xshm.c', 'runtime/tests/opencca_gpu_rsi_task_chain_test.c'])
dependencies.update(RMM / p for p in sources)
dependencies.update(copied_sources.values())
for depfile in (out / 'actual').glob('*.d'):
    for entry in depfile.read_text().replace('\\\n', ' ').split()[1:]:
        dependency = Path(entry)
        if dependency.is_file() and dependency.is_relative_to(ROOT) and not dependency.is_relative_to(out):
            dependencies.add(dependency)
summary = dict(status='PASS_ACTUAL_RSI_REALM_LIFECYCLE' if args.realm_lifecycle else 'PASS_ACTUAL_RSI_TASK_CHAIN' if args.task_chain else 'PASS_ACTUAL_RSI_MEMORY_CHAIN', checks=results,
               compiled_mutants_rejected=mutant_count, models_only=True,
               scope='Actual RSI dispatcher/endpoint/input copy/IPA translation/private core/xshm_rtt/seven physical callbacks and real physical lease tables; REC/RTT/granules/slots/cache/MMIO modeled. ' +
                     ('Includes modeled firmware boot/two-Client task dispatch/finish/return/retire, post-snapshot root/stream faults, actual RMI PM/revocation/dead-owner reclaim adapters, failed reset retention, stale task replay after reset/reuse, REC-count/NEW-state reclaim guards, bounded control scrub and service identity detachment. RMI dispatcher policy locking and RD lifetime are modeled. No shader execution, physical GPC or concurrency.' if args.task_chain else 'No GPU launch, hardware GPC or concurrency.'),
               source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dependencies)},
               hardware='NOT_RUN', production_changed=False, goal_complete=False)
if args.realm_lifecycle:
    summary['scope'] = ('Actual two-Client RSI task/memory/RTT/device-revocation/reclaim chain, '
                        'xshm_rmi_allowed, REALM_DESTROY, root-ref traversal, GPU PM/mapping release, '
                        'endpoint release and RD/RTT zero-before-delegation call sites. '
                        'RD reallocation, REC references, RTT teardown primitives, memory-zero primitive, '
                        'outer dispatcher policy lock, cache/TLBI and MMIO remain modeled. '
                        'Does not execute smc_realm_create, real RMI dispatcher, shader, physical GPC or concurrency.')
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(dict(status=summary['status'], compiled_mutants_rejected=mutant_count, evidence=str(out))))
