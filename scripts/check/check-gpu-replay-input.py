#!/usr/bin/env python3
"""Exercise current START replay inputs through the actual firmware/backend."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--reference', type=Path)
p.add_argument('--mutants', action='store_true')
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
fixture = (rmm / 'runtime/tests/opencca_gpu_backend_test.c').read_text()
needle = 'static void task_start_backend('
assert fixture.count(needle) == 1
fixture = fixture.replace(needle, '''void gpu_replay_input_test(const struct gpu_firmware_ops *,
    const struct gpu_private_ops *, const void *, const void *,
    unsigned long, unsigned long, unsigned long);

''' + needle, 1)
needle = '\t\t\tassert(model_glb_out[2] == model_glb_in[2]); /* Preserve the first Client\'s bit. */'
assert fixture.count(needle) == 1
fixture = fixture.replace(needle, needle + '''
            if (scenario == 13U) {
                unsigned int old_writes = writes, old_controls = control_writes;
                unsigned int old_bells = firmware_doorbells, old_cleans = launch_cleans;
                gpu_replay_input_test(&fw_ops, &donated_ops, &service, owners[i],
                    contexts[i], groups[i], tokens[i]);
                assert(writes == old_writes && control_writes == old_controls &&
                    firmware_doorbells == old_bells && launch_cleans == old_cleans);
            }''', 1)
fixture_path = a.out / 'backend.c'
fixture_path.write_text(fixture)
core = (rmm / 'runtime/core/opencca_gpu_firmware.c').read_text()
tail = (rmm / 'runtime/tests/opencca_gpu_replay_input_test.h').read_text()
variants = {'candidate': core}
if a.reference:
    variants['reference'] = a.reference.read_text()
if a.mutants:
    begin = core.index('static void task_start(', core.index('static void task_start(') + 1)
    end = core.index('\n}', begin) + 2
    start_body = core[begin:end]
    changes = {
        'ignore-as': ('csg_in[20] != checked.value[0]', '(!task->start_attempted && csg_in[20] != checked.value[0])'),
        'ignore-global-config': ('((glb_in[0] ^ glb_out[0]) & GLB_CONFIG_MASK) != 0U',
                                '(!task->start_attempted && ((glb_in[0] ^ glb_out[0]) & GLB_CONFIG_MASK) != 0U)'),
        'ignore-global-doorbell': ('((glb_in[2] ^ glb_out[2]) & csg_mask) != 0U',
                                  '(!task->start_attempted && ((glb_in[2] ^ glb_out[2]) & csg_mask) != 0U)'),
        'ignore-child-doorbell': ('((csg_in[2] ^ csg_out[2]) & cs_mask) != 0U',
                                 '(!task->start_attempted && ((csg_in[2] ^ csg_out[2]) & cs_mask) != 0U)'),
        'ignore-group-state': ('(csg_in[0] & 7U) != (group->suspended ? 3U : 1U) || ((csg_out[0] ^ csg_in[0]) & TASK_CSG_ACK_MASK) != 0U',
                               '(!task->start_attempted && ((csg_in[0] & 7U) != (group->suspended ? 3U : 1U) || ((csg_out[0] ^ csg_in[0]) & TASK_CSG_ACK_MASK) != 0U))')}
    for name, (before, after) in changes.items():
        assert start_body.count(before) == 1, name
        variants[name] = core[:begin] + start_body.replace(before, after, 1) + core[end:]
results = []
for name, source in variants.items():
    directory = a.out / name
    directory.mkdir()
    firmware = directory / 'firmware.c'
    firmware.write_text(source + '\n' + tail)
    command = [os.getenv('HOST_CC', 'cc'), '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
               '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
    command += ['-I' + str(rmm / path) for path in ['runtime/tests/mmio-stubs', 'runtime/include',
                                                  'ext/mbedtls/include', 'ext/mbedtls/library']]
    command += [str(rmm / path) for path in ['plat/rk3588/src/rk3588_gpu.c', 'runtime/core/opencca_gpu.c',
                'runtime/core/opencca_gpu_lease.c', 'runtime/core/opencca_gpu_private.c',
                'ext/mbedtls/library/sha256.c', 'ext/mbedtls/library/platform_util.c']]
    command += [str(firmware), str(fixture_path), '-o', str(directory / 'model')]
    with (directory / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert built.returncode == 0, (name, 'compile failure is not a rejection')
    invocation = [str(directory / 'model'), str(root / 'GPU-SFTP/panthor_fw/mali_csffw.bin')]
    with (directory / 'run.log').open('w') as log:
        ran = subprocess.run(invocation, stdout=log, stderr=subprocess.STDOUT)
    output = (directory / 'run.log').read_text()
    assert 'AddressSanitizer' not in output and 'runtime error:' not in output, name
    if name.startswith('ignore-'):
        assert ran.returncode == -6 and 'replay rejects changed input' in output, (name, ran.returncode)
    else:
        assert ran.returncode == 0 and output.count('GPU_REPLAY_INPUT=PASS') >= 2, (name, ran.returncode)
    results.append(dict(name=name, command=command, invocation=invocation,
                        build_exit=built.returncode, run_exit=ran.returncode,
                        injected_passes=output.count('GPU_REPLAY_INPUT=PASS')))
if a.reference:
    # Error lines and semantic output must also agree, not merely PASS counts.
    assert (a.out / 'candidate/run.log').read_bytes() == (a.out / 'reference/run.log').read_bytes()
record = dict(status='PASS', checks=results, reference_identical=bool(a.reference),
              compiled_mutants_rejected=5 if a.mutants else 0,
              cases=results[0]['injected_passes'] * 56, models_only=True, goal_complete=False)
(a.out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
print('GPU_REPLAY_INPUT_CHECKS=PASS fresh inputs and no publication; MODEL_ONLY')
