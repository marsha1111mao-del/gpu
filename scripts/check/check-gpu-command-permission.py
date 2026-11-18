#!/usr/bin/env python3
"""Execute RMM task admission against synthetic privileged command-stream bytes."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
OPCODE_REFERENCE = ROOT / "configs/security/csf-opcodes-mesa-25.0.7.json"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=ROOT / "build/rmm-client-bo-20261130/command-permission-unit")
parser.add_argument("--firmware", type=Path, default=ROOT / "GPU-SFTP/panthor_fw/mali_csffw.bin")
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def check_opcode_classification():
    reference = json.loads(OPCODE_REFERENCE.read_text())
    expected = set(reference['values'].values())
    assert len(expected) == len(reference['values']) == 39
    assert reference['values']['FINISH_TILING'] == 9
    source = (RMM / 'runtime/core/opencca_gpu_firmware.c').read_text()
    match = re.search(r'^static bool client_csf_opcode_allowed\([^;{}]+\)\s*\{', source, re.M)
    assert match
    function = source[match.start():source.index('\n}', match.end()) + 2]
    variants = {'candidate': function}
    for name, old, new in (
        ('drop-finish-tiling', 'case 0U ... 9U:', 'case 0U ... 8U:'),
        ('allow-undefined-19', 'case 16U ... 18U:', 'case 16U ... 19U:'),
        ('allow-undefined-35', 'case 32U ... 34U:', 'case 32U ... 35U:'),
    ):
        assert function.count(old) == 1
        variants[name] = function.replace(old, new, 1)
    initializers = ', '.join('[' + str(opcode) + '] = true' for opcode in sorted(expected))
    test = ('#include <assert.h>\n#include <stdbool.h>\n#include <stdint.h>\n#include <stdio.h>\n'
            '#include "actual.inc"\n'
            'static const bool expected[256] = {' + initializers + '};\n'
            'int main(void) {\n'
            ' for (uint64_t opcode=0; opcode<256; opcode++)\n'
            '  assert(client_csf_opcode_allowed(opcode)==expected[opcode]);\n'
            ' assert(!client_csf_opcode_allowed(256));\n'
            ' assert(!client_csf_opcode_allowed(UINT64_MAX));\n'
            ' puts("GPU_CSF_OPCODE_ENUM=PASS defined=39 tested=256");\n'
            ' return 0;\n}\n')
    results = []
    for name, actual in variants.items():
        directory = out / 'opcode-classification' / name
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'actual.inc').write_text(actual + '\n')
        (directory / 'test.c').write_text(test)
        command = [os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                   '-g', '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
                   '-I' + str(directory), str(directory / 'test.c'), '-o', str(directory / 'test')]
        with (directory / 'build.log').open('w') as log:
            built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        assert built.returncode == 0, name
        with (directory / 'run.log').open('w') as log:
            executed = subprocess.run([str(directory / 'test')], stdout=log, stderr=subprocess.STDOUT, check=False)
        transcript = (directory / 'run.log').read_text()
        if name == 'candidate':
            assert executed.returncode == 0 and 'GPU_CSF_OPCODE_ENUM=PASS' in transcript
        else:
            assert executed.returncode == -6 and 'Assertion' in transcript, (name, transcript)
        results.append({'name': name, 'command': command, 'build_exit_code': built.returncode,
                        'run_exit_code': executed.returncode, 'log': str(directory / 'run.log')})
    (out / 'opcode-results.json').write_text(json.dumps(results, indent=2) + '\n')
    return results


opcode_results = check_opcode_classification()

build = [
    os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-g",
    "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
    "-I" + str(RMM / "runtime/tests/mmio-stubs"),
    "-I" + str(RMM / "runtime/include"),
    "-I" + str(RMM / "ext/mbedtls/include"),
    "-I" + str(RMM / "ext/mbedtls/library"),
    str(RMM / "runtime/core/opencca_gpu_private.c"),
    str(RMM / "runtime/core/opencca_gpu_firmware.c"),
    str(RMM / "runtime/tests/opencca_gpu_firmware_test.c"),
    str(RMM / "ext/mbedtls/library/sha256.c"),
    str(RMM / "ext/mbedtls/library/platform_util.c"),
    "-o", str(out / "command-permission-test"),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    built = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT, check=False)
if built.returncode != 0:
    record = {
        "status": "FAIL",
        "build_exit_code": built.returncode,
        "run_exit_code": None,
        "actual_admission": "invalid_oracle",
        "negative_control": "FAIL",
        "source_sha256": {},
        "scope": "Build failed before actual admission execution",
        "not_covered": "No command-permission conclusion can be drawn",
        "hardware_tests": "NOT_RUN",
    }
    (out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1)

run = [str(out / "command-permission-test"), str(args.firmware.resolve())]
with (out / "run.log").open("w", encoding="utf-8") as log:
    executed = subprocess.run(run, stdout=log, stderr=subprocess.STDOUT, check=False)

output = (out / "run.log").read_text(encoding="utf-8")
markers = {line.split(" ", 1)[0] for line in output.splitlines() if line}
control_present = "GPU_COMMAND_PERMISSION_CONTROL=PASS" in markers
finish_tiling_accepted = "GPU_COMMAND_FINISH_TILING=PASS" in markers
actual_rejected = "GPU_COMMAND_PERMISSION=PASS" in markers
actual_accepted = "GPU_COMMAND_PERMISSION=FAIL" in markers
valid = built.returncode == 0 and executed.returncode == 0 and control_present and finish_tiling_accepted and (
    actual_rejected ^ actual_accepted
)
passed = valid and actual_rejected
source_files = [
    RMM / "runtime/core/opencca_gpu_private.c",
    RMM / "runtime/core/opencca_gpu_firmware.c",
    RMM / "runtime/tests/opencca_gpu_firmware_test.c",
    RMM / "ext/mbedtls/library/sha256.c",
    RMM / "ext/mbedtls/library/platform_util.c",
    args.firmware.resolve(),
    OPCODE_REFERENCE,
    Path(__file__),
]
record = {
    "status": "PASS_COMMAND_PERMISSION_SCOPED" if passed else "FAIL",
    "build_exit_code": built.returncode,
    "run_exit_code": executed.returncode,
    "actual_admission": "rejected_undefined_opcode_stream" if actual_rejected else (
        "accepted_privileged_stream" if actual_accepted else "invalid_oracle"
    ),
    "negative_control": "PASS" if control_present else "FAIL",
    "finish_tiling_accepted": finish_tiling_accepted,
    "opcode_classification": opcode_results,
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Actual admission accepts FINISH_TILING and rejects synthetic undefined opcode streams before a hold; the actual opcode predicate is checked for all 256 byte values against the independently pinned Mesa 25.0.7 enum, including rejection of undefined 19/35 and three classifier mutants. This classifies opcodes only; it does not prove GPU privilege semantics",
    "not_covered": "Physical GPU execution, hardware Stage-1 enforcement, real privileged opcode semantics, command-field authorization beyond opcode admission, and post-admission Client stream mutation",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
if not valid:
    raise AssertionError(output)
print(output, end="")
if not passed:
    raise SystemExit(1)
