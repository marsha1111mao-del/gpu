#!/usr/bin/env python3
"""Validate unpublished-ring preparation with actual RSI/core/platform code."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess

from gpu_c_source import c_fragment_spans, replace_c_fragment

root = Path.cwd()
rmm = root / "opencca/tf-rmm"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--reference", type=Path)
p.add_argument("--core", type=Path, default=rmm / "runtime/core/opencca_gpu_firmware.c")
p.add_argument(
    "--test", type=Path, default=rmm / "runtime/tests/opencca_gpu_backend_test.c"
)
p.add_argument(
    "--lease-header",
    type=Path,
    default=rmm / "runtime/tests/opencca_gpu_domain_lease_test.h",
)
a = p.parse_args()
out = a.out.resolve()
out.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
subprocess.run(
    [
        "python3",
        str(root / "scripts/check/check-gpu-domain-dispatch.py"),
        "--out",
        str(out),
        "--prepare-only",
    ],
    check=True,
)
core = a.core.read_text()
(out / "test.c").write_text(a.test.read_text())
(out / "opencca_gpu_domain_lease_test.h").write_text(a.lease_header.read_text())
start = core.index("static bool task_revalidate_idle(")
end = core.index("\n}", start) + 2
fragment = core[start:end]
call = "task_start_checked(ops, memory_ops, service, owner, group->context, group->handle, anchor->handle, false, true, snapshot, &checked);"
assert len(c_fragment_spans(fragment, call)) == 1
old = "if (!task_queue_snapshot(ops, memory_ops, group, anchor, false, &pending) || pending)"
assert len(c_fragment_spans(fragment, old)) == 1
pre = "if (!task_idle_anchor_valid(memory_ops, service, owner, group, anchor))\n\t\tgoto failed;"
assert len(c_fragment_spans(core, pre)) == 1
variants = {"candidate": (core, True)}
if a.reference:
    variants["reference"] = (a.reference.read_text(), True)
variants["ignore-post-start-failure"] = (
    core[:start]
    + replace_c_fragment(
        fragment, call, call + "\n\tchecked.status = GPU_PRIVATE_SUCCESS;"
    )
    + core[end:],
    False,
)
variants["skip-post-queue"] = (
    core[:start]
    + replace_c_fragment(fragment, old, "if (((void)pending, false))")
    + core[end:],
    False,
)
variants["skip-pre-metadata"] = (
    replace_c_fragment(core, pre, "if (false)\n\t\tgoto failed;"),
    False,
)
sources = [
    "plat/rk3588/src/rk3588_gpu.c",
    "runtime/core/opencca_gpu.c",
    "runtime/core/xshm_endpoint.c",
    "runtime/core/opencca_gpu_lease.c",
    "runtime/core/opencca_gpu_private.c",
    "ext/mbedtls/library/sha256.c",
    "ext/mbedtls/library/platform_util.c",
]
includes = [
    "runtime/tests/mmio-stubs",
    "runtime/tests",
    "runtime/include",
    "ext/mbedtls/include",
    "ext/mbedtls/library",
]
records = []


def record(row):
    records.append(row)
    (out / "results.json").write_text(json.dumps(records, indent=2) + "\n")


def build(name, code, lease=False):
    src = out / (name + ".c")
    src.write_text(code)
    cmd = [
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
        "-DGPU_DOMAIN_RSI_TEST",
        "-I" + str(out),
    ]
    if lease:
        cmd.append("-DGPU_DOMAIN_LEASE_TEST")
    cmd += (
        ["-I" + str(rmm / i) for i in includes]
        + [str(rmm / s) for s in sources]
        + [str(out / "test.c"), str(src), "-o", str(out / name)]
    )
    with (out / (name + "-build.log")).open("w") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    record(dict(name=name, phase="build", command=cmd, exit_code=rc))
    assert rc == 0, (name, rc)


def run(name, passing, case=None):
    cmd = [
        str(out / name),
        str(root / "GPU-SFTP/panthor_fw/mali_csffw.bin"),
        "--domain-only",
    ]
    label = name if case is None else name + "-" + str(case)
    env = {} if case is None else {"GPU_LEASE_CASE": str(case)}
    with (out / (label + "-run.log")).open("w") as f:
        rc = subprocess.run(
            cmd, env=dict(os.environ, **env), stdout=f, stderr=subprocess.STDOUT
        ).returncode
    text = (out / (label + "-run.log")).read_text()
    record(
        dict(
            name=name,
            phase="run",
            case=case,
            command=cmd,
            environment=env,
            exit_code=rc,
            log=str(out / (label + "-run.log")),
        )
    )
    if passing:
        marker = (
            "GPU_TASK_DOMAIN_ADVERSARIAL=PASS"
            if case is None
            else "GPU_DOMAIN_LEASE=PASS"
        )
        assert rc == 0 and text.count(marker) == (132 if case is None else 2), (
            label,
            rc,
            text[-600:],
        )
    else:
        assert rc == -6 and "Assertion" in text, (label, rc, text[-600:])
    return text


for name, (code, passing) in variants.items():
    build(name, code)
    text = run(name, passing)
    if passing:
        rows = [
            tuple(map(int, v))
            for v in re.findall(
                r"GPU_UNPUBLISHED_PREPARE case=(\d+) client=(\d+) ring_writes=(\d+)",
                text,
            )
        ]
        selected = [v for v in rows if 46 <= v[0] <= 66]
        assert len(selected) == 42 and all(
            v[2] == (2 if name == "candidate" else 0) for v in selected
        )
    print(name, "PASS", flush=True)
counts = {}
for name, (code, passing) in variants.items():
    if not passing:
        continue
    label = name + "-lease"
    build(label, code, True)
    for case in range(25):
        text = run(label, True, case)
        if case == 0:
            counts[name] = [
                int(v)
                for v in re.findall(
                    r"GPU_READY_DISPATCH_MMIO client=\d+ reads=(\d+)", text
                )
            ]
        if case >= 16:
            values = [
                int(v)
                for v in re.findall(
                    r"GPU_UNPUBLISHED_LEASE case=\d+ client=\d+ ring_writes=(\d+)", text
                )
            ]
            assert values == (
                [1, 1] if name == "candidate" or case <= 18 else [0, 0]
            ), (name, case, values)
    print(label, "25 cases PASS", flush=True)
assert len(counts["candidate"]) == 2
if a.reference:
    assert all(c < r for c, r in zip(counts["candidate"], counts["reference"]))
inputs = [a.core, a.test, a.lease_header] + ([a.reference] if a.reference else [])
manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
(out / "summary.json").write_text(
    json.dumps(
        dict(
            status="PASS",
            models_only=True,
            actual_rsi_core_platform=True,
            adversarial_cases_per_client=66,
            lease_cases_per_client=25,
            negative_variants=[n for n, (_, p) in variants.items() if not p],
            live_dispatch_mmio_reads=counts,
            input_sha256=manifest,
        ),
        indent=2,
    )
    + "\n"
)
