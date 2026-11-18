#!/usr/bin/env python3
"""MEM10 control-page residue model using the actual private GPU core."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from gpu_c_source import replace_c_fragment

ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
CORE = RMM / "runtime/core/opencca_gpu_private.c"
TEST = RMM / "runtime/tests/opencca_gpu_control_test.c"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = CORE.read_text(encoding="utf-8")

acquire = source[source.index("bool gpu_private_control_acquire(") :]
acquire = acquire[
    : acquire.index(
        "\n}\n", acquire.index("for (unsigned int i = 0U; i < bo->pages; i++)")
    )
    + 3
]
assert acquire.count("ops->clear_page(") == 1
assert acquire.index("ops->clear_page(") < acquire.index("bo->mapped = 1U")

clear_loop = """\tfor (unsigned int i = 0U; i < bo->pages; i++)
\t\tif (!ops->clear_page((unsigned long)bo_page(bo, i)->pa_page << 12U))
\t\t\treturn false;"""

skip_clear = replace_c_fragment(
    source,
    clear_loop,
    "\t(void)bo->pages;",
    1,
)
publish_before_clear = replace_c_fragment(
    source,
    clear_loop
    + """\n\t{
\t\tcache_metadata_invalidate();
\t\tbo->mapped = 1U;
\t}""",
    """\t{
\t\tcache_metadata_invalidate();
\t\tbo->mapped = 1U;
\t}
\t(void)bo->pages;""",
    1,
)
ignore_mapped = replace_c_fragment(
    source,
    "\t    bo->hidden != bo->pages || bo->mapped != 0U || bo->control_gpu_refs != 0U)",
    "\t    bo->hidden != bo->pages || false || bo->control_gpu_refs != 0U)",
    1,
)
assert (
    skip_clear != source and publish_before_clear != source and ignore_mapped != source
)

variants = {
    "candidate": (source, True),
    "skip-clear": (skip_clear, False),
    "publish-before-clear": (publish_before_clear, False),
    "ignore-mapped": (ignore_mapped, False),
}
results = []
for name, (core_text, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    core_path = case / "opencca-gpu-private.c"
    core_path.write_text(core_text, encoding="utf-8")
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
        "-I" + str(RMM / "runtime/include"),
        str(core_path),
        str(TEST),
        "-o",
        str(case / "test"),
    ]
    with (case / "build.log").open("w", encoding="utf-8") as log:
        build = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    run_exit = None
    output = (case / "build.log").read_text(encoding="utf-8")
    if build.returncode == 0:
        with (case / "run.log").open("w", encoding="utf-8") as log:
            run = subprocess.run(
                [str(case / "test")], stdout=log, stderr=subprocess.STDOUT, check=False
            )
        run_exit = run.returncode
        output = (case / "run.log").read_text(encoding="utf-8")
    passed = (
        expected_pass
        and build.returncode == 0
        and run_exit == 0
        and "GPU_CONTROL_MEMORY=PASS" in output
    )
    rejected = (
        not expected_pass
        and build.returncode == 0
        and run_exit == -6
        and "Assertion" in output
    )
    result = "PASS" if passed or rejected else "FAIL"
    results.append(
        {
            "name": name,
            "command": command,
            "run_command": [str(case / "test")],
            "build_exit_code": build.returncode,
            "run_exit_code": run_exit,
            "expected": "PASS" if expected_pass else "REJECT",
            "result": result,
            "log": str(case / ("run.log" if build.returncode == 0 else "build.log")),
        }
    )
    (out / "results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    assert result == "PASS", (name, output[-2000:])

record = {
    "status": "PASS_GPU_CONTROL_RESIDUE_MODEL",
    "results": results,
    "negative_variants_rejected": 3,
    "source_sha256": {
        str(CORE.relative_to(ROOT)): hashlib.sha256(CORE.read_bytes()).hexdigest(),
        str(TEST.relative_to(ROOT)): hashlib.sha256(TEST.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
    },
    "scope": "Actual private GPU core and control-memory test: old firmware bytes are seeded after revocation, gpu_private_control_acquire clears every donated page before mapped publication, and repeated acquisition remains denied",
    "not_covered": "GPU local memory, scratch, registers, firmware-private caches, hardware readback, and board execution",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "status": record["status"],
            "negative_variants_rejected": record["negative_variants_rejected"],
            "evidence": str(out),
            "models_only": True,
        },
        ensure_ascii=False,
    )
)
