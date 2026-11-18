#!/usr/bin/env python3
"""Run the offline firmware-interface configuration model against pinned CSF metadata."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=ROOT / "build/rmm-client-bo-20261130/firmware-config-unit")
parser.add_argument("--firmware", type=Path, default=ROOT / "GPU-SFTP/panthor_fw/mali_csffw.bin")
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)

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
    "-o", str(out / "firmware-config-test"),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    built = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT, check=False)

run = [str(out / "firmware-config-test"), str(args.firmware.resolve())]
with (out / "run.log").open("w", encoding="utf-8") as log:
    executed = subprocess.run(run, stdout=log, stderr=subprocess.STDOUT, check=False)

output = (out / "run.log").read_text(encoding="utf-8")
required = {
    "GPU_FIRMWARE_FRAGMENT=PASS",
    "GPU_FIRMWARE_CONFIG=PASS",
    "GPU_GROUP_RINGS=PASS",
    "GPU_FIRMWARE_SNAPSHOT=PASS",
}
output_markers = {line.split(" ", 1)[0] for line in output.splitlines() if line}
passed = built.returncode == 0 and executed.returncode == 0 and required <= output_markers
source_files = [
    RMM / "runtime/core/opencca_gpu_private.c",
    RMM / "runtime/core/opencca_gpu_firmware.c",
    RMM / "runtime/tests/opencca_gpu_firmware_test.c",
    RMM / "ext/mbedtls/library/sha256.c",
    RMM / "ext/mbedtls/library/platform_util.c",
    args.firmware.resolve(),
    Path(__file__),
]
record = {
    "status": "PASS_FIRMWARE_CONFIG_MODEL" if passed else "FAIL",
    "build_exit_code": built.returncode,
    "run_exit_code": executed.returncode,
    "observed_markers": sorted(required & output_markers),
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Pinned CSF image accepted through ordered 4KiB upload with exact BEGIN total, bounded chunks, sequential offsets, duplicate/out-of-order rejection and incomplete SEAL retention; private snapshot, digest seal and runtime root setup; header/section/executable-byte tampering or crypto failure revokes instead of booting, advertised stream upper bound accepted, two-queue groups configured and validated, Client rings are immutable read-only GPU mappings, CALL wrappers are admission snapshots, and cached FW properties ignore live pointer changes",
    "not_covered": "Physical firmware installation, MCU boot, actual GPU slots/execution, and multi-queue workload output",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
assert passed, output
print(output, end="")
