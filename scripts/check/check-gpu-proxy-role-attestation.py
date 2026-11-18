#!/usr/bin/env python3
"""Verify the RMM-private Proxy GPU role attestation claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess


from gpu_c_source import c_fragment_spans

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


def replace_once(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


role_path = RMM / "runtime/core/opencca_gpu_role.c"
test_path = RMM / "runtime/tests/opencca_gpu_role_claim_test.c"
role = role_path.read_text()
adapter = (RMM / "runtime/rsi/opencca_gpu.c").read_text()
attest = (RMM / "runtime/rsi/realm_attest.c").read_text()
token = (RMM / "lib/attestation/src/attestation_token.c").read_text()
cmake = (RMM / "runtime/CMakeLists.txt").read_text()
header = (RMM / "runtime/include/opencca_gpu.h").read_text()

assert "#include <opencca_gpu_role.h>" in adapter
assert c_fragment_spans(adapter, "opencca_gpu_role_claim_measure(rec->realm_info.g_rd,")
assert c_fragment_spans(adapter, "opencca_gpu_role_claim_clear_locked(owner);")
assert adapter.index("accepted = opencca_gpu_claim(") < adapter.index(
    "opencca_gpu_role_claim_measure(rec->realm_info.g_rd,"
)
assert adapter.index("opencca_gpu_service_invalidate(owner);") < adapter.index(
    "opencca_gpu_role_claim_clear_locked(owner);"
)
assert "(index == OPENCCA_GPU_ROLE_MEASUREMENT_SLOT)" in attest
assert "for (unsigned int i = 1U; i < num_measurements; ++i)" in token
assert c_fragment_spans(adapter, "opencca_gpu_role_measure(rd->algorithm, endpoint_id,")
assert c_fragment_spans(adapter, "rd->measurement[OPENCCA_GPU_ROLE_MEASUREMENT_SLOT]")
assert '"core/opencca_gpu_role.c"' in cmake
assert "void opencca_gpu_service_release(struct granule *owner);" in header
assert "void opencca_gpu_service_release_locked(struct granule *owner);" in header

variants = {
    "constant-endpoint": replace_once(
        role,
        ".endpoint_id = (uint64_t)endpoint_id",
        ".endpoint_id = UINT64_C(1)",
    ),
    "wrong-magic": replace_once(role, "'O', 'C'", "'X', 'C'"),
    "partial-clear": replace_once(
        role,
        "(void)memset(measurement, 0, MAX_MEASUREMENT_SIZE);",
        "(void)memset(measurement, 0, 1U);",
    ),
}

results = [
    {
        "name": "production-wiring-audit",
        "command": ["source-audit"],
        "exit_code": 0,
        "log": None,
    }
]
cases = {"candidate": role}
cases.update(variants)
for name, role_text in cases.items():
    case_dir = out / name
    case_dir.mkdir()
    role_copy = case_dir / "opencca_gpu_role.c"
    role_copy.write_text(role_text)
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
        f"-I{RMM / 'lib/measurement/include'}",
        f"-I{RMM / 'lib/smc/include'}",
        f"-I{RMM / 'lib/common/include'}",
        str(role_copy),
        str(test_path),
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
        assert run.returncode == 0 and "GPU_ROLE_CLAIM=PASS" in text, text
    else:
        assert run.returncode == -6 and "Assertion" in text, (name, text)
    print(name, "PASS", flush=True)

source_paths = [
    role_path,
    test_path,
    RMM / "runtime/include/opencca_gpu_role.h",
    RMM / "runtime/rsi/opencca_gpu.c",
    RMM / "runtime/rsi/realm_attest.c",
    RMM / "lib/attestation/src/attestation_token.c",
    RMM / "runtime/CMakeLists.txt",
    RMM / "runtime/include/opencca_gpu.h",
    Path(__file__),
]
(out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
(out / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS_GPU_PROXY_ROLE_ATTESTATION_MODELS",
            "actual_role_core": True,
            "production_claim_clear_and_token_wiring_audited": True,
            "negative_variants": list(variants),
            "negative_variant_exit_codes": [-6] * len(variants),
            "source_sha256": {
                str(path.relative_to(ROOT)): digest(path) for path in source_paths
            },
            "scope": "Actual endpoint-bound role claim encoding/clear core; claim, service invalidation, guest measurement rejection, and REM slot token inclusion are source-audited.",
            "not_covered": "No full RMM link, signed token execution, Proxy image/RIM approval policy, Client verifier, approved-role provisioning, Linux concurrency, physical IRQ/DMA, or L3 hardware isolation",
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
            "status": "PASS_GPU_PROXY_ROLE_ATTESTATION_MODELS",
            "negative_variants": len(variants),
            "evidence": str(out),
            "models_and_source_audit_only": True,
            "goal_complete": False,
        }
    )
)
