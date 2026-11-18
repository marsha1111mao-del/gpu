#!/usr/bin/env python3
"""Reject GPU-forged completion pages, consumers, and counters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess


from gpu_c_source import replace_c_fragment

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

firmware_original = (RMM / "runtime/core/opencca_gpu_firmware.c").read_text()
backend_original = (RMM / "runtime/tests/opencca_gpu_backend_test.c").read_text()

phase_loop = (
    "for (unsigned int phase = domain_dispatch_only ? 465U : 0U; "
    "phase < 551U; phase++) {"
)
assert backend_original.count(phase_loop) == 1
backend_limited = backend_original.replace(
    phase_loop,
    "for (unsigned int phase = 65U; phase < 93U; phase++) {",
    1,
)
phase_exit = """\t\tfirmware_starts = firmware_doorbells = 0U;
\t}
\tassert(opencca_gpu_pm_destroy_begin(&service));"""
assert backend_limited.count(phase_exit) == 1
backend_limited = backend_limited.replace(
    phase_exit,
    "\t\tfirmware_starts = firmware_doorbells = 0U;\n\t}\n\treturn;",
    1,
)

pending_authority = """\t\tpending_work |= extract != insert || cs_out.scoreboards != 0U || cs_out.blocked_reason != 0U ||
\t\t\tsequence != first_sequence + task->queue_count[queue];"""

firmware_skip_pending = replace_c_fragment(
    firmware_original,
    pending_authority,
    "\t\t(void)extract; (void)insert; (void)cs_out.scoreboards; "
    "(void)cs_out.blocked_reason; (void)sequence;",
    1,
)

(out / "backend-phase-65-92.c").write_text(backend_limited)
(out / "firmware-skip-pending-authority.c").write_text(firmware_skip_pending)

include_paths = [
    RMM / "runtime/tests/mmio-stubs",
    RMM / "runtime/include",
    RMM / "ext/mbedtls/include",
    RMM / "ext/mbedtls/library",
]
common_sources = [
    RMM / "plat/rk3588/src/rk3588_gpu.c",
    RMM / "runtime/core/opencca_gpu.c",
    RMM / "runtime/core/xshm_endpoint.c",
    RMM / "runtime/core/opencca_gpu_lease.c",
    RMM / "runtime/core/opencca_gpu_private.c",
    RMM / "ext/mbedtls/library/sha256.c",
    RMM / "ext/mbedtls/library/platform_util.c",
    out / "backend-phase-65-92.c",
]
variants = {
    "candidate": RMM / "runtime/core/opencca_gpu_firmware.c",
    "skip-pending-authority": out / "firmware-skip-pending-authority.c",
}
records = []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


scenarios: set[int] = set()
for name, firmware_source in variants.items():
    command = [
        os.environ.get("HOST_CC", "cc"),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        *[f"-I{path}" for path in include_paths],
        *map(str, common_sources),
        str(firmware_source),
        "-o",
        str(out / name),
    ]
    build_log = out / f"{name}-build.log"
    with build_log.open("w") as handle:
        build = subprocess.run(
            command, stdout=handle, stderr=subprocess.STDOUT, check=False
        )
    records.append(
        {
            "name": f"{name}-build",
            "command": command,
            "exit_code": build.returncode,
            "log": str(build_log),
        }
    )
    assert build.returncode == 0, name

    run_command = [str(out / name), str(ROOT / "GPU-SFTP/panthor_fw/mali_csffw.bin")]
    run_log = out / f"{name}.log"
    with run_log.open("w") as handle:
        run = subprocess.run(
            run_command, stdout=handle, stderr=subprocess.STDOUT, check=False
        )
    text = run_log.read_text(encoding="utf-8", errors="replace")
    records.append(
        {
            "name": name,
            "command": run_command,
            "exit_code": run.returncode,
            "log": str(run_log),
        }
    )
    if name == "candidate":
        scenarios = {
            int(scenario)
            for scenario in re.findall(
                r"GPU_TASK_COMPLETE_BACKEND=PASS scenario=(\d+) ", text
            )
        }
        assert run.returncode == 0
        assert scenarios == set(range(66, 94)), sorted(scenarios)
    else:
        assert run.returncode == -6 and "Assertion" in text
    print(name, "PASS", flush=True)

source_paths = common_sources[:-1] + [
    RMM / "runtime/core/opencca_gpu_firmware.c",
    RMM / "runtime/tests/opencca_gpu_backend_test.c",
    ROOT / "GPU-SFTP/panthor_fw/mali_csffw.bin",
]
(out / "results.json").write_text(json.dumps(records, indent=2) + "\n")
(out / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS",
            "models_only": True,
            "actual_firmware_core": True,
            "candidate_scenarios": list(range(66, 94)),
            "phase_limited_fixture": "Generated backend copy returns after phase 92; unrelated global teardown premises are not exercised",
            "negative_variant": "skip-pending-authority",
            "negative_variant_exit_code": -6,
            "source_sha256": {
                str(path.relative_to(ROOT)): sha256_file(path) for path in source_paths
            },
            "not_covered": (
                "No physical GPU command, real Stage-1 DMA, device write path, Linux concurrency, "
                "or L3 device isolation is exercised"
            ),
        },
        indent=2,
    )
    + "\n"
)
