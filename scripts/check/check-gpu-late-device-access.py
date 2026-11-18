#!/usr/bin/env python3
"""MEM07 model: trusted release drains a late transaction before reuse."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
CORE = RMM / "runtime/core/opencca_gpu.c"
TEST = RMM / "runtime/tests/opencca_gpu_lease_test.c"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)

core = CORE.read_text(encoding="utf-8")
test = TEST.read_text(encoding="utf-8")
release_path = core[core.index("case OPENCCA_GPU_RELEASE:"):core.index("case OPENCCA_GPU_OPP_BEGIN:")]
assert release_path.index("ops->revoke_mmio(owner)") < release_path.index("reset(ops, false)")
assert release_path.index("reset(ops, false)") < release_path.index("opencca_gpu_lease_release_owner(owner)")
assert "late_transaction_pending = false;" in test

skip_reset = release_path.replace(
    "\t\tif (!reset(ops, false))\n\t\t\treturn false;",
    "\t\t(void)reset(ops, false);",
    1,
)
assert skip_reset != release_path
release_before_reset = release_path.replace(
    """\t\tif (!reset(ops, false))
\t\t\treturn false;
\t\tif (owner != NULL) {
\t\t\t(void)opencca_gpu_lease_release_owner(owner);
\t\t\tstate = OPENCCA_GPU_REVOKED;
\t\t}""",
    """\t\tif (owner != NULL) {
\t\t\t(void)opencca_gpu_lease_release_owner(owner);
\t\t\tstate = OPENCCA_GPU_REVOKED;
\t\t}
\t\tif (!reset(ops, false))
\t\t\treturn false;""",
    1,
)
assert release_before_reset != release_path
skip_drain = test.replace(
    "\t\tlate_transaction_pending = false;",
    "\t\t(void)late_transaction_pending;",
    1,
)
assert skip_drain != test

variants = {
    "candidate": (core, test, True),
    "skip-release-reset": (core.replace(release_path, skip_reset, 1), test, False),
    "release-before-drain": (core.replace(release_path, release_before_reset, 1), test, False),
    "skip-drain": (core, skip_drain, False),
}
results = []
for name, (core_text, test_text, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    core_path = case / "opencca-gpu.c"
    test_path = case / "opencca-gpu-lease-test.c"
    core_path.write_text(core_text, encoding="utf-8")
    test_path.write_text(test_text, encoding="utf-8")
    command = [
        os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-fno-pie", "-no-pie", "-I" + str(RMM / "runtime/include"),
        str(RMM / "runtime/core/opencca_gpu_lease.c"),
        str(test_path), str(core_path), "-o", str(case / "test"),
    ]
    with (case / "build.log").open("w", encoding="utf-8") as log:
        build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    run_exit = None
    output = (case / "build.log").read_text(encoding="utf-8")
    if build.returncode == 0:
        with (case / "run.log").open("w", encoding="utf-8") as log:
            run = subprocess.run([str(case / "test"), "--late-transaction"],
                                 stdout=log, stderr=subprocess.STDOUT, check=False)
        run_exit = run.returncode
        output = (case / "run.log").read_text(encoding="utf-8")
    passed = (expected_pass and build.returncode == 0 and run_exit == 0 and
              "GPU_LATE_TRANSACTION=PASS" in output)
    rejected = (not expected_pass and build.returncode == 0 and
                run_exit == -6 and "Assertion" in output)
    result = "PASS" if passed or rejected else "FAIL"
    results.append({
        "name": name,
        "command": command,
        "run_command": [str(case / "test"), "--late-transaction"],
        "build_exit_code": build.returncode,
        "run_exit_code": run_exit,
        "expected": "PASS" if expected_pass else "REJECT",
        "result": result,
        "log": str(case / ("run.log" if build.returncode == 0 else "build.log")),
    })
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    assert result == "PASS", (name, output[-2000:])

record = {
    "status": "PASS_GPU_LATE_DEVICE_ACCESS_MODEL",
    "results": results,
    "negative_variants_rejected": 3,
    "source_sha256": {
        str(CORE.relative_to(ROOT)): hashlib.sha256(CORE.read_bytes()).hexdigest(),
        str(TEST.relative_to(ROOT)): hashlib.sha256(TEST.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": "Actual GPU release/control and lease cores. A device double represents one delayed transaction; it can drain only during successful reset while the old page lease is still present. Failed revoke/reset and all negative variants retain isolation or fail the oracle.",
    "not_covered": "Physical GPU/GPC/IOMMU transaction retirement, hardware TLBI, malicious Host DMA, reset timing, and board execution",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": record["status"],
                  "negative_variants_rejected": record["negative_variants_rejected"],
                  "evidence": str(out), "models_only": True}, ensure_ascii=False))
