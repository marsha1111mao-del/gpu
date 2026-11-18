#!/usr/bin/env python3
"""Verify GPU service authority is bound to a live endpoint generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import re
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


core_path = RMM / "runtime/core/opencca_gpu.c"
endpoint_path = RMM / "runtime/core/xshm_endpoint.c"
core = core_path.read_text()
endpoint = endpoint_path.read_text()

variants = {
    "allow-unregistered-claim": replace_c_fragment(
        core,
        "if (endpoint_id == 0UL || !opencca_gpu_mmio_allowed(caller))",
        "if (!opencca_gpu_mmio_allowed(caller))",
    ),
    "ignore-running-generation": replace_c_fragment(
        core,
        "endpoint_id != 0UL && endpoint_id == service_endpoint_id &&\n\t       (state == OPENCCA_GPU_RUNNING",
        "((void)endpoint_id, state == OPENCCA_GPU_RUNNING",
    ),
    "ignore-isolated-generation": replace_c_fragment(
        core,
        "endpoint_id != 0UL && endpoint_id == service_endpoint_id &&\n\t       mediated &&",
        "((void)endpoint_id, mediated) &&",
    ),
    "keep-invalid-generation": replace_c_fragment(
        core,
        "\tservice_endpoint_id = 0UL;\n\tif (state == OPENCCA_GPU_REVOKED",
        "(void)service_endpoint_id;\n\tif (state == OPENCCA_GPU_REVOKED",
    ),
    "skip-fail-closed-state": replace_c_fragment(
        core,
        "\t    state == OPENCCA_GPU_OFF)\n\t\treturn;\n\tmediated = true;\n\tstate = OPENCCA_GPU_QUARANTINED;",
        "\t    state == OPENCCA_GPU_OFF)\n\t\treturn;\n\tmediated = true;\n\tstate = OPENCCA_GPU_MEDIATED;",
    ),
    "reuse-endpoint-id": replace_c_fragment(
        endpoint,
        "\t\t\t\tendpoint->id = ++next_endpoint_id;",
        "\t\t\t\tendpoint->id = 1UL;",
    ),
}

adapter = (RMM / "runtime/rsi/opencca_gpu.c").read_text()
xshm = (RMM / "runtime/rsi/xshm.c").read_text()
private = (RMM / "runtime/rsi/opencca_gpu_private.c").read_text()
for required in (
    "opencca_gpu_claim(rec->realm_info.g_rd,",
    "endpoint_id = xshm_endpoint_id(rec->realm_info.g_rd)",
    "accepted = opencca_gpu_claim(rec->realm_info.g_rd, endpoint_id);",
    "opencca_gpu_service_isolate(&gpu_ops, service,",
    "xshm_endpoint_id(service));",
    "opencca_gpu_service_release(rec->realm_info.g_rd);",
    "opencca_gpu_service_release_locked(g_rd);",
):
    assert required in (adapter + xshm), required
assert xshm.index("opencca_gpu_service_release_locked(g_rd);") < xshm.index(
    "xshm_endpoint_release(g_rd);"
)
isolated_calls = re.findall(
    r"opencca_gpu_service_isolated\(\s*(?:owner|service|client),\s*xshm_endpoint_id\(",
    private,
)
running_calls = re.findall(
    r"opencca_gpu_service_running\(\s*service,\s*xshm_endpoint_id\(",
    private,
)
assert len(isolated_calls) == private.count("opencca_gpu_service_isolated(")
assert len(running_calls) == private.count("opencca_gpu_service_running(")

sources = [
    RMM / "runtime/core/opencca_gpu_lease.c",
    RMM / "runtime/core/xshm_endpoint.c",
    RMM / "runtime/tests/opencca_gpu_service_binding_test.c",
]
results = []
cases = {"candidate": core}
cases.update(
    {name: text for name, text in variants.items() if name != "reuse-endpoint-id"}
)
cases["reuse-endpoint-id"] = core
for name, core_text in cases.items():
    case_dir = out / name
    case_dir.mkdir()
    core_copy = case_dir / "opencca_gpu.c"
    endpoint_copy = case_dir / "xshm_endpoint.c"
    core_copy.write_text(core_text)
    endpoint_copy.write_text(
        endpoint if name != "reuse-endpoint-id" else variants[name]
    )
    command = [
        os.environ.get("HOST_CC", "cc"),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-sanitize-recover=undefined",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        f"-I{RMM / 'runtime/include'}",
        str(RMM / "runtime/core/opencca_gpu_lease.c"),
        str(endpoint_copy),
        str(core_copy),
        str(sources[2]),
        "-o",
        str(case_dir / "test"),
    ]
    with (case_dir / "build.log").open("w") as log:
        build = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    results.append(
        {
            "name": f"{name}-build",
            "command": command,
            "exit_code": build.returncode,
            "log": str(case_dir / "build.log"),
        }
    )
    assert build.returncode == 0, name
    with (case_dir / "run.log").open("w") as log:
        run = subprocess.run(
            [str(case_dir / "test")], stdout=log, stderr=subprocess.STDOUT, check=False
        )
    text = (case_dir / "run.log").read_text()
    results.append(
        {
            "name": name,
            "command": [str(case_dir / "test")],
            "exit_code": run.returncode,
            "log": str(case_dir / "run.log"),
        }
    )
    if name == "candidate":
        assert run.returncode == 0 and "GPU_SERVICE_BINDING=PASS" in text, text
    else:
        assert run.returncode == -6 and "Assertion" in text, (name, text)
    print(name, "PASS", flush=True)

source_paths = sources + [
    core_path,
    endpoint_path,
    RMM / "runtime/rsi/opencca_gpu.c",
    RMM / "runtime/rsi/xshm.c",
    RMM / "runtime/rsi/opencca_gpu_private.c",
    Path(__file__),
]
(out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
(out / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS_GPU_SERVICE_BINDING_MODELS",
            "actual_core_and_endpoint": True,
            "production_adapter_wiring_audited": True,
            "negative_variants": list(variants),
            "negative_variant_exit_codes": [-6] * len(variants),
            "source_sha256": {
                str(path.relative_to(ROOT)): digest(path) for path in source_paths
            },
            "scope": "Actual GPU service core and complete endpoint core; production claim/unregister/RD-destroy adapter wiring is source-audited. Synthetic trusted reset callbacks and same-address RD model.",
            "not_covered": "No full RMM link, real Proxy measurement/remote attestation, role provisioning, Linux concurrency, physical IRQ/DMA, or L3 hardware isolation",
            "hardware_tests": "NOT_RUN",
            "goal_complete": False,
        },
        indent=2,
    )
    + "\n"
)
print(
    json.dumps(
        {
            "status": "PASS_GPU_SERVICE_BINDING_MODELS",
            "negative_variants": len(variants),
            "evidence": str(out),
            "models_only": True,
            "goal_complete": False,
        }
    )
)
