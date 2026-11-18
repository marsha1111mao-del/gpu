#!/usr/bin/env python3
"""Exercise the actual RK3588 GPU reset timeout and ACK-loss recovery path."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from gpu_c_source import replace_c_fragment

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
PLATFORM = RMM / "plat/rk3588/src/rk3588_gpu.c"
TEST = RMM / "runtime/tests/opencca_gpu_flush_recovery_test.c"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)

source = PLATFORM.read_text(encoding="utf-8")
fallback_old = """\tif (!completed) {
\t\treg_write(GPU_CMD, GPU_HARD_RESET);
\t\tcompleted = poll(GPU_INT_RAWSTAT, GPU_RESET_COMPLETED, GPU_RESET_COMPLETED);
\t}"""
soft_retry_new = """\tif (!completed) {
\t\treg_write(GPU_CMD, GPU_SOFT_RESET);
\t\tcompleted = poll(GPU_INT_RAWSTAT, GPU_RESET_COMPLETED, GPU_RESET_COMPLETED);
\t\treg_write(GPU_CMD, GPU_HARD_RESET);
\t\tcompleted = poll(GPU_INT_RAWSTAT, GPU_RESET_COMPLETED, GPU_RESET_COMPLETED);
\t}"""
skip_hard_new = """\tif (!completed) {
\t\t(void)GPU_HARD_RESET;
\t}"""
final_barrier_old = """\tdsb(sy);
\treturn completed;"""
final_barrier_new = """\t(void)0;
\treturn completed;"""

variants = {
    "candidate": (source, True),
    "soft-retry-loop": (
        replace_c_fragment(source, fallback_old, soft_retry_new, 1),
        False,
    ),
    "skip-hard-fallback": (
        replace_c_fragment(source, fallback_old, skip_hard_new, 1),
        False,
    ),
    "false-success-on-double-ack-loss": (
        replace_c_fragment(
            source,
            final_barrier_old,
            final_barrier_old.replace("return completed;", "return true;"),
            1,
        ),
        False,
    ),
    "skip-final-barrier": (
        replace_c_fragment(source, final_barrier_old, final_barrier_new, 1),
        False,
    ),
}
for name in (
    "soft-retry-loop",
    "skip-hard-fallback",
    "false-success-on-double-ack-loss",
    "skip-final-barrier",
):
    assert variants[name][0] != source, name

records = []
for name, (platform_source, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    (case / "rk3588_gpu.c").write_text(platform_source, encoding="utf-8")
    (case / "opencca_gpu_flush_recovery_test.c").write_text(
        TEST.read_text(encoding="utf-8"), encoding="utf-8"
    )
    command = [
        os.environ.get("HOST_CC", "cc"),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-O2",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-sanitize-recover=undefined",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        "-I" + str(case),
        "-I" + str(RMM / "runtime/tests"),
        "-I" + str(RMM / "runtime/tests/mmio-stubs"),
        "-I" + str(RMM / "runtime/include"),
        "-I" + str(RMM / "ext/mbedtls/include"),
        "-I" + str(RMM / "ext/mbedtls/library"),
        str(case / "rk3588_gpu.c"),
        str(RMM / "runtime/core/opencca_gpu.c"),
        str(RMM / "runtime/core/xshm_endpoint.c"),
        str(RMM / "runtime/core/opencca_gpu_lease.c"),
        str(RMM / "runtime/core/opencca_gpu_private.c"),
        str(RMM / "runtime/core/opencca_gpu_firmware.c"),
        str(RMM / "ext/mbedtls/library/sha256.c"),
        str(RMM / "ext/mbedtls/library/platform_util.c"),
        str(case / "opencca_gpu_flush_recovery_test.c"),
        "-o",
        str(case / "test"),
    ]
    with (case / "build.log").open("w", encoding="utf-8") as log:
        built = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    run_exit = None
    output = ""
    if built.returncode == 0:
        with (case / "run.log").open("w", encoding="utf-8") as log:
            ran = subprocess.run(
                [str(case / "test")],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
        run_exit = ran.returncode
        output = (case / "run.log").read_text(encoding="utf-8")
    else:
        output = (case / "build.log").read_text(encoding="utf-8")
    passed = (
        expected_pass
        and built.returncode == 0
        and run_exit == 0
        and "GPU_FLUSH_RECOVERY=PASS" in output
    )
    rejected = not expected_pass and run_exit == -6 and "Assertion" in output
    records.append(
        {
            "name": name,
            "command": command,
            "build_exit_code": built.returncode,
            "run_exit_code": run_exit,
            "expected": "PASS" if expected_pass else "REJECT",
            "result": "PASS" if passed or rejected else "FAIL",
            "log": str(case / ("run.log" if built.returncode == 0 else "build.log")),
        }
    )
    (out / "results.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    assert passed or rejected, (name, output[-2000:])

source_files = [
    PLATFORM,
    RMM / "runtime/core/opencca_gpu.c",
    RMM / "runtime/core/opencca_gpu_lease.c",
    RMM / "runtime/core/opencca_gpu_private.c",
    RMM / "runtime/core/opencca_gpu_firmware.c",
    RMM / "runtime/tests/opencca_gpu_backend_test.c",
    TEST,
    Path(__file__),
]
record = {
    "status": "PASS_FLUSH_RECOVERY_MODEL",
    "results": records,
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Actual RK3588 reset register sequence with modeled MMIO ACK and timer; persistent soft-reset ACK loss performs exactly one hard fallback, double-ACK loss remains fail-closed with bounded commands and a final barrier",
    "not_covered": "Physical GPU reset latency, real IRQ state, task termination, Linux concurrency, DMA stop proof, or old-task SUCCESS; those task/resource properties are covered separately by task-recovery evidence",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(
    "GPU_FLUSH_RECOVERY=PASS actual RK3588 reset sequence; MMIO ACK/timer doubles only"
)
