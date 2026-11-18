#!/usr/bin/env python3
"""Exercise the actual in-RMM queue-history helper with host doubles."""
from pathlib import Path
import argparse
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=ROOT / "build/rmm-client-bo-20261130/queue-history-unit")
out = parser.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=True)

build = [
    os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
    "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
    "-I" + str(RMM / "runtime/tests/mmio-stubs"),
    "-I" + str(RMM / "runtime/include"),
    "-I" + str(RMM / "ext/mbedtls/include"),
    "-I" + str(RMM / "ext/mbedtls/library"),
    str(RMM / "runtime/core/opencca_gpu_private.c"),
    str(RMM / "runtime/tests/opencca_gpu_queue_history_test.c"),
    str(RMM / "ext/mbedtls/library/sha256.c"),
    str(RMM / "ext/mbedtls/library/platform_util.c"),
    "-o", str(out / "queue-history-test"),
]
subprocess.run(build, check=True)
for scenario in range(18):
    subprocess.run([str(out / "queue-history-test"), str(scenario)], check=True)
