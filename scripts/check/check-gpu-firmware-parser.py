#!/usr/bin/env python3
"""Exercise the actual firmware section parser with malicious metadata mutants."""
from pathlib import Path
import argparse
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=ROOT / "build/rmm-client-bo-20261130/firmware-parser-unit")
parser.add_argument("--firmware", type=Path, default=ROOT / "GPU-SFTP/panthor_fw/mali_csffw.bin")
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)

build = [
    os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
    "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
    "-I" + str(RMM / "runtime/tests/mmio-stubs"),
    "-I" + str(RMM / "runtime/include"),
    "-I" + str(RMM / "ext/mbedtls/include"),
    "-I" + str(RMM / "ext/mbedtls/library"),
    str(RMM / "runtime/core/opencca_gpu_private.c"),
    str(RMM / "runtime/tests/opencca_gpu_firmware_parser_test.c"),
    str(RMM / "ext/mbedtls/library/sha256.c"),
    str(RMM / "ext/mbedtls/library/platform_util.c"),
    "-o", str(out / "firmware-parser-test"),
]
subprocess.run(build, check=True)
subprocess.run([str(out / "firmware-parser-test"), str(args.firmware.resolve())], check=True)
