#!/usr/bin/env python3
"""Exercise actual xshm memory/service boundary parsing and peer identity.

Uses the production xshm memory, endpoint and service cores with the existing
host test doubles. This is L1/L2 evidence only: it does not model a hostile
shared-memory transport race or execute an actual Realm CPU.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
out = parser.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=False)

build = [
    os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
    "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
    "-fno-pie", "-no-pie", "-I" + str(RMM / "runtime/include"),
    str(RMM / "runtime/core/xshm_memory.c"),
    str(RMM / "runtime/core/xshm_endpoint.c"),
    str(RMM / "runtime/core/xshm_service.c"),
    str(RMM / "runtime/tests/xshm_memory_test.c"),
    "-o", str(out / "xshm-memory-test"),
]
with (out / "build.log").open("w") as log:
    built = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT)
run = [str(out / "xshm-memory-test")]
with (out / "run.log").open("w") as log:
    executed = subprocess.run(run, stdout=log, stderr=subprocess.STDOUT)

record = {
    "status": "PASS_ACTUAL_XSHM_MEMORY_BOUNDARY_MODEL_ONLY" if built.returncode == 0 and executed.returncode == 0 else "FAIL",
    "build_command": build,
    "build_exit": built.returncode,
    "run_command": run,
    "run_exit": executed.returncode,
    "matrix_ids": ["T01", "T03"],
    "scope": "Production xshm memory/endpoint/service cores plus existing host doubles",
    "not_covered": "Shared-queue races, malicious REC execution, physical memory access and transport response loss",
    "hardware_tests": "NOT_RUN",
}
(out / "results.json").write_text(json.dumps(record, indent=2) + "\n")
assert built.returncode == 0, "xshm memory boundary build failed"
assert executed.returncode == 0, "xshm memory boundary test failed"
print("GPU_XSHM_MEMORY_BOUNDARY=PASS actual cores, host doubles, MODEL_ONLY")
