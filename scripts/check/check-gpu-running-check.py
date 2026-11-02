#!/usr/bin/env python3
"""Exercise the combined running-AS checks in actual GPU cores and platform code."""
import argparse
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = (rmm / 'runtime/tests/opencca_gpu_backend_test.c').read_text()

def replace_once(old, new):
    global source
    assert source.count(old) == 1, old
    source = source.replace(old, new, 1)

replace_once('static unsigned int detach_read_corruption;', '''static unsigned int detach_read_corruption;
static unsigned int running_dynamic, running_checks;''')
replace_once('static unsigned int soft_commands, hard_commands, barriers;', '''static unsigned int soft_commands, hard_commands, barriers;
void gpu_running_metadata_test(const struct gpu_private_ops *, const void *,
    const void *, unsigned long, unsigned long, struct gpu_firmware_config *);''')
replace_once('\tmmio_reads++;', '''	mmio_reads++;
    if (offset == 0x2474UL) {
        if (running_dynamic == 1U) registers[0x700U / 4U] = 0U;
        if (running_dynamic == 2U) registers[0x704U / 4U] = 0U;
        if (running_dynamic == 3U) registers[0x2000U / 4U] = 1U;
        if (running_dynamic == 4U) registers[0x20U / 4U] = 1U;
        if (running_dynamic == 5U) timer_frequency++;
    }''')
replace_once('static void prepare_mmio(unsigned long firmware_root)', '''static void running_mmio(unsigned long root, unsigned long firmware_root)
{
    struct gpu_firmware_config combined, separate;
    uint32_t snapshot[sizeof(registers) / sizeof(registers[0])];
    const unsigned int offsets[] = {0U, 0x14U, 0x18U, 0x2400U, 0x2404U,
        0x2408U, 0x240cU, 0x2430U, 0x2434U, 0x700U, 0x704U, 0x304U,
        0x2000U, 0x20U, 0x110U, 0x114U, 0x2440U, 0x2444U, 0x2448U,
        0x244cU, 0x2470U, 0x2474U};
    unsigned int before = writes, commands = as_count, bells = firmware_doorbells;
    unsigned int separate_reads, combined_reads;
    memcpy(snapshot, registers, sizeof(snapshot));
    for (unsigned int pass = 0U; pass < 2U; pass++) {
        registers[0x34U / 4U] = pass; /* Idle and busy GPU are both valid. */
        mmio_reads = 0U;
        assert(plat_opencca_gpu_firmware_configuration(firmware_root, &separate));
        assert(plat_opencca_gpu_pt_prepare(root, 1U, firmware_root, true));
        separate_reads = mmio_reads;
        mmio_reads = 0U;
        assert(plat_opencca_gpu_pt_check_running(root, 1U, firmware_root, &combined));
        combined_reads = mmio_reads;
        assert(combined_reads < separate_reads);
        assert(combined.shader_mask == separate.shader_mask &&
            combined.poweroff_timer == separate.poweroff_timer &&
            combined.idle_timer == separate.idle_timer &&
            combined.ack_timeout_ticks == separate.ack_timeout_ticks);
    }
    for (unsigned int i = 0U; i < sizeof(offsets) / sizeof(offsets[0]); i++) {
        memcpy(registers, snapshot, sizeof(snapshot));
        unsigned int offset = offsets[i];
        registers[offset / 4U] ^= offset == 0U ? 1U << 24U : 1U;
        bool original = plat_opencca_gpu_firmware_configuration(firmware_root, &separate) &&
            plat_opencca_gpu_pt_prepare(root, 1U, firmware_root, true);
        assert(!original);
        assert(!plat_opencca_gpu_pt_check_running(root, 1U, firmware_root, &combined));
    }
    memcpy(registers, snapshot, sizeof(snapshot));
    for (unsigned int i = 0U; i < 6U; i++) {
        timer_frequency = i == 0U ? 0UL : i == 1U ? 1000000001UL : 1000000UL;
        unsigned long selected_root = i == 2U ? root + 1UL : i == 3U ? firmware_root : root;
        unsigned int slot = i == 4U ? 0U : i == 5U ? 16U : 1U;
        assert(!plat_opencca_gpu_pt_check_running(selected_root, slot, firmware_root, &combined));
    }
    timer_frequency = 1000000UL;
    assert(!plat_opencca_gpu_pt_check_running(root, 1U, firmware_root, NULL));
    registers[0x100U / 4U] = registers[0x104U / 4U] = 0U;
    assert(!plat_opencca_gpu_pt_check_running(root, 1U, firmware_root, &combined));
    for (running_dynamic = 1U; running_dynamic <= 5U; running_dynamic++) {
        memcpy(registers, snapshot, sizeof(snapshot));
        timer_frequency = 1000000UL;
        assert(!plat_opencca_gpu_pt_check_running(root, 1U, firmware_root, &combined));
    }
    running_dynamic = 0U;
    timer_frequency = 1000000UL;
    memcpy(registers, snapshot, sizeof(snapshot));
    assert(writes == before && as_count == commands && firmware_doorbells == bells);
    printf("GPU_RUNNING_MMIO=PASS separate_reads=%u combined_reads=%u static_rejections=30 dynamic_rejections=5 no_writes MODEL_ONLY\\n",
        separate_reads, combined_reads);
}

static void prepare_mmio(unsigned long firmware_root)''')
replace_once('\textend_mmio(root, firmware_root);', '\trunning_mmio(root, firmware_root);\n\textend_mmio(root, firmware_root);')
replace_once('static bool extend_private(unsigned long root, unsigned int slot, unsigned long firmware_root)', '''static bool check_running_private(unsigned long root, unsigned int slot,
        unsigned long firmware_root, struct gpu_firmware_config *config)
{
    assert(alias_revoked && opencca_gpu_service_isolated(&service));
    running_checks++;
    return plat_opencca_gpu_pt_check_running(root, slot, firmware_root, config);
}

static bool extend_private(unsigned long root, unsigned int slot, unsigned long firmware_root)''')
replace_once('\t.prepare_as = prepare_private, .extend_as = extend_private, .write_page = donated_write,',
             '\t.prepare_as = prepare_private, .check_running_as = check_running_private,\n\t.extend_as = extend_private, .write_page = donated_write,')
replace_once('\t\tassert(gpu_firmware_task_resources(&service, owners[i], tokens[i], &task));', '''
        struct gpu_firmware_config running_config;
        unsigned int running_before = running_checks, writes_before = writes;
        for (unsigned int bad = 0U; bad < 8U; bad++) {
            struct gpu_private_ops missing = donated_ops;
            if (bad == 5U) missing.check_running_as = NULL;
            if (bad == 6U) missing.table_pa = NULL;
            gpu_private_context_check_running(&missing,
                bad == 0U ? &stranger : bad == 1U ? NULL : &service,
                bad == 2U ? &service : bad == 3U ? &stranger : owners[i],
                bad == 4U ? contexts[i] + 1UL : contexts[i], root,
                bad == 7U ? NULL : &running_config, &result);
            assert(result.status != GPU_PRIVATE_SUCCESS);
        }
        assert(running_checks == running_before && writes == writes_before);
        gpu_private_context_check_running(&donated_ops, &service, owners[i], contexts[i],
            root, &running_config, &result);
        assert(result.status == GPU_PRIVATE_SUCCESS && running_checks == running_before + 1U);
        assert(writes == writes_before);
        gpu_running_metadata_test(&donated_ops, &service, owners[i], contexts[i], root, &running_config);
        assert(writes == writes_before);
		assert(gpu_firmware_task_resources(&service, owners[i], tokens[i], &task));''')
replace_once('\tfirmware_integration(argv[1]);', '''	firmware_integration(argv[1]);
    assert(running_checks > 100U);
    printf("GPU_RUNNING_CORE=PASS actual combined path, metadata rejection before callback, callbacks=%u MODEL_ONLY\\n", running_checks);''')
fixture = out / 'fixture.c'
fixture.write_text(source)
common = [os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-g',
          '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
common += ['-I' + str(rmm / p) for p in ['runtime/tests/mmio-stubs', 'runtime/tests', 'runtime/include',
           'ext/mbedtls/include', 'ext/mbedtls/library']]
sources = [rmm / p for p in ['plat/rk3588/src/rk3588_gpu.c', 'runtime/core/opencca_gpu.c',
           'runtime/core/opencca_gpu_lease.c', 'runtime/core/opencca_gpu_private.c',
           'runtime/core/opencca_gpu_firmware.c', 'ext/mbedtls/library/sha256.c',
           'ext/mbedtls/library/platform_util.c']]
private_original = sources[3].read_text()
private_fixture = out / 'private-core.c'
private_fixture.write_text(private_original + '''
/* Model-only entry: exercise real context metadata without a production API. */
static bool reject_running(unsigned long root, unsigned int slot,
        unsigned long firmware_root, struct gpu_firmware_config *config)
{
    (void)root; (void)slot; (void)firmware_root; (void)config;
    return false;
}
void gpu_running_metadata_test(const struct gpu_private_ops *ops, const void *service,
        const void *owner, unsigned long context, unsigned long firmware_root,
        struct gpu_firmware_config *config)
{
    struct private_context *ctx = ctx_lookup(owner, context), saved;
    struct gpu_private_result result;
    assert(ctx != NULL && ctx->slot > 0U && ctx->slot < GPU_PRIVATE_AS_SLOTS);
    saved = *ctx;
    unsigned long saved_owner = slot_owner[saved.slot];
    for (unsigned int scenario = 0U; scenario < 10U; scenario++) {
        *ctx = saved;
        switch (scenario) {
        case 0U: ctx->quarantined = true; break;
        case 1U: ctx->revoked = true; break;
        case 2U: ctx->quiesced = true; break;
        case 3U: ctx->task_refs = 0U; break;
        case 4U: ctx->pending = 1U; break;
        case 5U: ctx->activated = false; break;
        case 6U: ctx->live_prepared = false; break;
        case 7U: ctx->slot = 0U; break;
        case 8U: ctx->slot = GPU_PRIVATE_AS_SLOTS; break;
        case 9U: slot_owner[saved.slot] = context + 1UL; break;
        }
        gpu_private_context_check_running(ops, service, owner, context, firmware_root, config, &result);
        assert(result.status == GPU_PRIVATE_STATE);
        slot_owner[saved.slot] = saved_owner;
    }
    *ctx = saved;
    struct gpu_private_ops fail = *ops;
    fail.check_running_as = reject_running;
    gpu_private_context_check_running(&fail, service, owner, context, firmware_root, config, &result);
    assert(result.status == GPU_PRIVATE_STATE && ctx->quarantined);
    assert(ctx->task_refs == saved.task_refs && ctx->slot == saved.slot && ctx->activated);
    assert(slot_owner[saved.slot] == saved_owner);
    *ctx = saved;
}
''')
sources[3] = private_fixture
results = []

def run_case(name, selected_sources, options=(), arguments=(), expected=0):
    exe = out / name
    cmd = common + list(options) + [str(p) for p in selected_sources] + [str(fixture), '-o', str(exe)]
    with (out / (name + '-build.log')).open('w') as log:
        build = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    assert build.returncode == 0, (name, 'compile failure', build.returncode)
    with (out / (name + '-run.log')).open('w') as log:
        run = subprocess.run([str(exe), str(root / 'GPU-SFTP/panthor_fw/mali_csffw.bin')] + list(arguments),
                             stdout=log, stderr=subprocess.STDOUT)
    results.append(dict(name=name, command=cmd, build_exit=build.returncode, run_exit=run.returncode))
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    assert run.returncode == expected, (name, run.returncode, expected)

run_case('candidate', sources)
subprocess.run(['python3', str(root / 'scripts/check/check-gpu-domain-dispatch.py'), '--out', str(out / 'rsi'), '--prepare-only'], check=True)
run_case('rsi-test', sources, ['-DGPU_DOMAIN_RSI_TEST', '-I' + str(out / 'rsi')], ['--domain-only'])
mutants = [
    ('skip_dynamic_mcu', 0, 'reg_read(MCU_STATUS) == 1U &&', 'true &&'),
    ('skip_dynamic_fault', 0, '(reg_read(MMU_INT_RAWSTAT) & MMU_FAULT_MASK) == 0U &&', 'true &&'),
    ('skip_dynamic_frequency', 0, 'read_cntfrq_el0() == frequency &&', 'true &&'),
    ('skip_service_identity', 3, 'ctx->service != service ||', 'false ||'),
]
for name, index, old, new in mutants:
    code = sources[index].read_text()
    start = code.index('bool plat_opencca_gpu_pt_check_running(' if index == 0 else 'void gpu_private_context_check_running(')
    end = code.index('\n}', start) + 2
    fragment = code[start:end]
    assert old in fragment
    if name == 'skip_dynamic_frequency':
        new = '(void)frequency, true &&'
        # Parenthesize the return expression to keep the comma in the expression.
        fragment = fragment.replace('return ' + old, 'return ((void)frequency, true) &&', 1)
    else:
        fragment = fragment.replace(old, new, 1)
    target = out / (name + '.c')
    target.write_text(code[:start] + fragment + code[end:])
    selected = list(sources)
    selected[index] = target
    run_case(name, selected, expected=-6)
print(json.dumps(dict(status='PASS_RUNNING_CHECK_ACTUAL_PLATFORM_CORE_RSI', checks=len(results),
                      evidence=str(out), models_only=True, goal_complete=False)))
