#!/usr/bin/env python3
"""Verify that only a mediated service identity can expose GPU MMIO."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
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

source = (RMM / "runtime/core/opencca_gpu.c").read_text()
allowed = """bool opencca_gpu_mmio_allowed(const void *candidate)
{
\treturn candidate != NULL && candidate == owner &&
\t       !mediated &&
\t       (state == OPENCCA_GPU_DESIGNATED || state == OPENCCA_GPU_RUNNING);
}"""

ignore_isolation = replace_c_fragment(
    source,
    allowed,
    """bool opencca_gpu_mmio_allowed(const void *candidate)
{
\t(void)candidate;
\treturn true;
}""",
    1,
)

exact_window = """\treturn pa == OPENCCA_GPU_MMIO_BASE && size == OPENCCA_GPU_MMIO_SIZE &&
\t       ipa == gpu_ipa &&
\t       opencca_gpu_mmio_allowed(candidate);"""

allow_partial_alias = replace_c_fragment(
    source,
    exact_window,
    "\t(void)candidate;\n\treturn physical_overlap || alias_overlap;",
    1,
)

(out / "opencca-gpu-ignore-isolation.c").write_text(ignore_isolation)
(out / "opencca-gpu-allow-partial-alias.c").write_text(allow_partial_alias)

include_paths = [RMM / "runtime/include"]
common_sources = [
    RMM / "runtime/core/opencca_gpu_lease.c",
    RMM / "runtime/tests/opencca_gpu_lease_test.c",
]
variants = {
    "candidate": RMM / "runtime/core/opencca_gpu.c",
    "ignore-isolation": out / "opencca-gpu-ignore-isolation.c",
    "allow-partial-alias": out / "opencca-gpu-allow-partial-alias.c",
}
records = []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


for name, core_source in variants.items():
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
        str(core_source),
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

    run_command = [str(out / name), "--service-isolation"]
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
        assert run.returncode == 0
        assert text.count("GPU_SERVICE_ISOLATION=PASS") == 1
    else:
        assert run.returncode == -6 and "Assertion" in text
    print(name, "PASS", flush=True)

source_paths = common_sources + [RMM / "runtime/core/opencca_gpu.c"]
(out / "results.json").write_text(json.dumps(records, indent=2) + "\n")
(out / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS",
            "models_only": True,
            "actual_service_core": True,
            "service_isolation_scenario": True,
            "negative_variants": ["ignore-isolation", "allow-partial-alias"],
            "negative_variant_exit_codes": [-6, -6],
            "source_sha256": {
                str(path.relative_to(ROOT)): sha256_file(path) for path in source_paths
            },
            "not_covered": (
                "No physical CPU instruction, SMMU stage, DMA request, mixed-page mapping, "
                "real Proxy process, concurrent Linux access, or L3 MMIO isolation is exercised"
            ),
        },
        indent=2,
    )
    + "\n"
)
