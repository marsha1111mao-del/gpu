#!/usr/bin/env python3
"""Exercise post-read completion/fault races in the actual GPU firmware core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess


from gpu_c_source import c_fragment_spans, replace_c_fragment

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
    "for (unsigned int phase = 214U; phase < 229U; phase++) {",
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
assert backend_limited.count("static bool domain_active, domain_dispatch_only;") == 1
backend_limited = backend_limited.replace(
    "static bool domain_active, domain_dispatch_only;",
    "extern unsigned int gpu_complete_fault_test_step;\nstatic bool domain_active, domain_dispatch_only;",
    1,
)
boundary_assert = """assert(result.status == GPU_PRIVATE_STATE && writes == before + 1U &&
\t\t\t\tas_count == commands_before && complete_reads_this_call == 3U &&
\t\t\t\t(model_groups[i].input[0] & 7U) == 1U);"""
assert backend_limited.count(boundary_assert) == 1
backend_limited = backend_limited.replace(
    boundary_assert,
    """assert(result.status == GPU_PRIVATE_STATE && writes == before + 1U &&
\t\t\t\tas_count == commands_before && complete_reads_this_call == 3U &&
\t\t\t\t(model_groups[i].input[0] & 7U) == 1U &&
\t\t\t\tgpu_complete_fault_test_step == 5U);""",
    1,
)

post_read_check = """task_start(ops, memory_ops, service, owner, group->context,
\t\tgroup->handle, token, false, internal, &checked);
\tif (checked.status != GPU_PRIVATE_SUCCESS)
\t\tgoto failed;"""
assert len(c_fragment_spans(firmware_original, post_read_check)) == 1
observe_failure = 'ERROR("GPU OBSERVE fail step=%u finish=%u\\n", step, finish);'
assert len(c_fragment_spans(firmware_original, observe_failure)) == 1
assert (
    len(
        c_fragment_spans(
            firmware_original, "static const unsigned char approved_digest[32] = {"
        )
    )
    == 1
)
instrumented_failure = "gpu_complete_fault_test_step = step;\n\t" + observe_failure
firmware_candidate = replace_c_fragment(
    firmware_original,
    "static const unsigned char approved_digest[32] = {",
    "unsigned int gpu_complete_fault_test_step;\nstatic const unsigned char approved_digest[32] = {",
    1,
).replace(
    observe_failure,
    instrumented_failure,
    1,
)
firmware_negative = replace_c_fragment(
    firmware_candidate,
    post_read_check,
    replace_c_fragment(
        post_read_check,
        "\tif (checked.status != GPU_PRIVATE_SUCCESS)\n\t\tgoto failed;",
        "\tchecked.status = GPU_PRIVATE_SUCCESS;",
    ),
    1,
)

(out / "backend-phase-214-228.c").write_text(backend_limited)
(out / "firmware-candidate.c").write_text(firmware_candidate)
(out / "firmware-skip-post-read-check.c").write_text(firmware_negative)

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
    out / "backend-phase-214-228.c",
]
variants = {
    "candidate": out / "firmware-candidate.c",
    "skip-post-read-check": out / "firmware-skip-post-read-check.c",
}
observation_mutations = {
    "forget-first-observation-failure": (
        "\tif (task->observation_error == 0U)\n\t\ttask->observation_error = step;",
        "\t(void)step;",
    ),
    "reobserve-failed-task": (
        "task->observation_error != 0U || task->observation_count == UINT32_MAX",
        "task->observation_count == UINT32_MAX",
    ),
}
for name, (old, new) in observation_mutations.items():
    assert len(c_fragment_spans(firmware_candidate, old)) == 1, name
    path = out / (name + ".c")
    path.write_text(replace_c_fragment(firmware_candidate, old, new, 1))
    variants[name] = path
records = []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


marker_cases: set[int] = set()
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
        marker_cases = {
            int(case)
            for case in re.findall(r"GPU_COMPLETE_STOP_FAULT=PASS case=(\d+) ", text)
        }
        assert run.returncode == 0
        assert marker_cases == set(range(1, 16)), sorted(marker_cases)
        history_cases = {
            int(case)
            for case in re.findall(r"GPU_TRUSTED_OBSERVATION=PASS case=(\d+) ", text)
        }
        assert history_cases == set(range(1, 16)), sorted(history_cases)
    else:
        assert run.returncode == -6 and "Assertion" in text

    print(name, "PASS", flush=True)

source_paths = common_sources[:-1] + [
    RMM / "runtime/core/opencca_gpu_firmware.c",
    RMM / "runtime/include/opencca_gpu_firmware.h",
    RMM / "runtime/include/opencca_gpu_private.h",
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
            "candidate_phases": list(range(214, 229)),
            "phase_limited_fixture": "Generated backend copy returns after phase 228; unrelated global teardown premises are not exercised",
            "boundary_cases": sorted(marker_cases),
            "negative_variant": "skip-post-read-check",
            "negative_variants": list(variants.keys())[1:],
            "trusted_observation_cases": sorted(marker_cases),
            "negative_variant_exit_code": -6,
            "negative_oracle": "Generated fixture requires observe rejection at step 5; bypassing the post-read check reaches step 6 and aborts",
            "source_sha256": {
                str(path.relative_to(ROOT)): sha256_file(path) for path in source_paths
            },
            "not_covered": (
                "No physical IRQ, real W1C timing, GPU execution, noncoherent hardware, "
                "Linux concurrency, or L3 device isolation is exercised"
            ),
        },
        indent=2,
    )
    + "\n"
)
