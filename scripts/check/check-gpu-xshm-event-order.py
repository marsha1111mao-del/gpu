#!/usr/bin/env python3
"""Run the actual xshm endpoint event-order policy test."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)

source_files = [
    RMM / "runtime/core/xshm_endpoint.c",
    RMM / "runtime/tests/xshm_endpoint_test.c",
    ROOT / "Linux-Guest-GPU/include/uapi/linux/realm_xshm.h",
]
build = [
    os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
    "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
    "-fno-pie", "-no-pie", "-I" + str(RMM / "runtime/include"),
    "-iquote", str(ROOT / "Linux-Guest-GPU/include/uapi"),
    str(source_files[0]), str(source_files[1]), "-o", str(out / "xshm-event-test"),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    built = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT, check=False)
run = [str(out / "xshm-event-test")]
with (out / "run.log").open("w", encoding="utf-8") as log:
    executed = subprocess.run(run, stdout=log, stderr=subprocess.STDOUT, check=False)
output = (out / "run.log").read_text(encoding="utf-8")
required = {
    "XSHM_RESIDENT_REQUEST_WAKE_TEST=PASS",
    "XSHM_FAST_IRQ_POLICY_TEST=PASS",
    "XSHM_ENDPOINT_POLICY_TEST=PASS",
    "XSHM_IRQ_HISTORY_POLICY_TEST=PASS cases=5",
    "XSHM_IRQ_LOG_INTEGRITY_POLICY_TEST=PASS cases=6",
}
passed = built.returncode == 0 and executed.returncode == 0 and required <= set(output.splitlines())

record = {
    "status": "PASS_XSHM_EVENT_ORDER_MODEL" if passed else "FAIL",
    "build_exit_code": built.returncode,
    "run_exit_code": executed.returncode,
    "observed_markers": sorted(required & set(output.splitlines())),
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [*source_files, Path(__file__)]
    },
    "scope": "Actual xshm endpoint event pending/acknowledged/arm state machine; duplicate notifications coalesce while pending count is retained, stale ACK/ARM and nonparticipant operations are rejected, query/rearm interleaving is repeated, a bounded trusted-history model fails closed on log overflow, skipped/duplicate consumption, or capture/consume reentry, and a trusted IRQ ring rejects forged tail/head, owner changes, unrecorded CPU migration, and overwrite of unconsumed records while safe consumed wraparound continues",
    "not_covered": "FINISH status authority, task binding, fence, physical IRQ source, physical IRQ log storage, GPU execution, and global FIFO ordering",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
assert passed, output
print("GPU_XSHM_EVENT_ORDER=PASS actual endpoint event state machine, host model only")
