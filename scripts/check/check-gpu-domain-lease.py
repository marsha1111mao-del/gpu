#!/usr/bin/env python3
"""Bounded Client dispatch through actual RSI/core/platform with device doubles."""

import argparse
import json
import os
from pathlib import Path
import resource
import subprocess

from gpu_c_source import c_fragment_spans, replace_c_fragment

root = Path(__file__).resolve().parents[2]
rmm = root / "opencca/tf-rmm"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--out", type=Path, required=True)
p.add_argument(
    "--ready-reference",
    type=Path,
    help="Compare READY proof composition with a frozen reference core",
)
p.add_argument(
    "--publish-reference",
    type=Path,
    help="Compare live READY/PUBLISH postcheck composition with a frozen core",
)
p.add_argument(
    "--idle-reference",
    type=Path,
    help="Compare hidden-anchor read-only observation with a frozen core",
)
a = p.parse_args()
if sum(bool(x) for x in (a.ready_reference, a.publish_reference, a.idle_reference)) > 1:
    p.error("select one proof comparison")
out = a.out.resolve()
out.mkdir(parents=True, exist_ok=False)
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
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
includes = [
    "runtime/tests/mmio-stubs",
    "runtime/include",
    "ext/mbedtls/include",
    "ext/mbedtls/library",
]
sources = [
    "plat/rk3588/src/rk3588_gpu.c",
    "runtime/core/opencca_gpu.c",
    "runtime/core/xshm_endpoint.c",
    "runtime/core/opencca_gpu_lease.c",
    "runtime/core/opencca_gpu_private.c",
    "ext/mbedtls/library/sha256.c",
    "ext/mbedtls/library/platform_util.c",
    "runtime/tests/opencca_gpu_backend_test.c",
]
core = rmm / "runtime/core/opencca_gpu_firmware.c"
original = core.read_text()
variants = {"candidate": (None, list(range(25)))}
variants["no-permission"] = (
    replace_c_fragment(original, "if (!anchor->continue_domain) {", "if (false) {"),
    [4],
)
old = "!gpu_private_mapping_accept(service, owner, task->resources.context, version)"
assert len(c_fragment_spans(original, old)) == 1
variants["stale-version"] = (replace_c_fragment(original, old, "false"), [2])
passing = {"candidate"}
if a.ready_reference:
    variants["reference"] = (a.ready_reference.read_text(), list(range(25)))
    passing.add("reference")
    old = "*ready_root = checked.root;"
    assert len(c_fragment_spans(original, old)) == 1
    variants["no-ready-reuse"] = (
        replace_c_fragment(original, old, "*ready_root = 0UL;"),
        [0],
    )
    passing.add("no-ready-reuse")
    variants["wrong-ready-root"] = (
        replace_c_fragment(original, old, "*ready_root = checked.root ^ 4096UL;"),
        [0],
    )
    old = """task_start_checked(ops, memory_ops, service, owner, group->context,
		group->handle, anchor->handle, false, true, snapshot, &checked);"""
    assert len(c_fragment_spans(original, old)) == 1
    variants["skip-final-anchor-check"] = (
        replace_c_fragment(
            original,
            old,
            """checked.status = GPU_PRIVATE_SUCCESS;
        if (snapshot != NULL) snapshot->root = ops->address(runtime_tables[0]);""",
        ),
        [16, 17, 18],
    )
    old = "gpu_private_task_cache(memory_ops, service, owner, group->context, token, result);"
    assert len(c_fragment_spans(original, old)) == 1
    variants["skip-ready-cache"] = (
        replace_c_fragment(original, old, "result->status = GPU_PRIVATE_SUCCESS;"),
        [10],
    )
results = []
if a.publish_reference:
    variants["reference"] = (a.publish_reference.read_text(), list(range(25)))
    passing.add("reference")
    old = "publish_root != NULL && result->status == GPU_PRIVATE_SUCCESS &&"
    assert len(c_fragment_spans(original, old)) == 1
    no_defer = replace_c_fragment(original, old, "false && " + old)
    old = "config = started.config;\n\t\tif (ready_root != 0UL && ready_root != root)"
    assert len(c_fragment_spans(original, old)) == 1
    repeated = old.replace(
        "\n\t\tif (ready_root",
        "\n\t\tif (!ops->configuration(root, &config)) goto failed;\n\t\tif (ready_root",
    )
    variants["no-publish-reuse"] = (replace_c_fragment(no_defer, old, repeated), [0])
    passing.add("no-publish-reuse")
    old = "*ready_root = checked.root;"
    assert len(c_fragment_spans(original, old)) == 1
    variants["wrong-ready-root"] = (
        replace_c_fragment(original, old, "*ready_root = checked.root ^ 4096UL;"),
        [0],
    )
    old = """task_start_checked(ops, memory_ops, service, owner, group->context,
			group->handle, token, false, false, &started, &checked);"""
    assert len(c_fragment_spans(original, old)) == 1
    variants["skip-publish-start"] = (
        replace_c_fragment(
            original,
            old,
            """{ checked.status = GPU_PRIVATE_SUCCESS;
        started.root = ops->address(runtime_tables[0]);
        (void)ops->configuration(started.root, &started.config); }""",
        ),
        [12],
    )
    old = "gpu_private_task_cache(memory_ops, service, owner, group->context, token, result);"
    assert len(c_fragment_spans(original, old)) == 1
    variants["skip-ready-cache"] = (
        replace_c_fragment(original, old, "result->status = GPU_PRIVATE_SUCCESS;"),
        [10],
    )
if a.idle_reference:
    variants["reference"] = (a.idle_reference.read_text(), list(range(25)))
    passing.add("reference")
    old = """task_start_checked(ops, memory_ops, service, owner, group->context,
		group->handle, anchor->handle, false, true, snapshot, &checked);"""
    assert len(c_fragment_spans(original, old)) == 1
    variants["missing-final-check"] = (
        replace_c_fragment(
            original,
            old,
            """checked.status = GPU_PRIVATE_SUCCESS;
        if (snapshot != NULL) {
            memset(snapshot, 0, sizeof(*snapshot));
            snapshot->root = ops->address(runtime_tables[0]);
        }""",
        ),
        list(range(16, 25)),
    )
    old = "if (!task_queue_snapshot(ops, memory_ops, group, anchor, false, &pending) || pending)"
    assert len(c_fragment_spans(original, old)) == 1
    variants["missing-queue-read"] = (
        replace_c_fragment(original, old, "if (((void)pending, false))"),
        list(range(16, 22)),
    )
for name, (text, cases) in variants.items():
    source = core
    if text is not None:
        assert text != original
        source = out / (name + ".c")
        source.write_text(text)
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
        "-DGPU_DOMAIN_RSI_TEST",
        "-DGPU_DOMAIN_LEASE_TEST",
        "-I" + str(out),
    ]
    command += ["-I" + str(rmm / d) for d in includes] + [str(rmm / s) for s in sources]
    command += [str(source), "-o", str(out / name)]
    with (out / (name + "-build.log")).open("w") as log:
        compiled = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    results.append(
        {"name": name + "-build", "command": command, "exit_code": compiled.returncode}
    )
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    assert compiled.returncode == 0, name
    for case in cases:
        cmd = [
            str(out / name),
            str(root / "GPU-SFTP/panthor_fw/mali_csffw.bin"),
            "--domain-only",
        ]
        log_path = out / (name + "-" + str(case) + ".log")
        with log_path.open("w") as log:
            run = subprocess.run(
                cmd,
                env=dict(os.environ, GPU_LEASE_CASE=str(case)),
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        text = log_path.read_text()
        results.append(
            {
                "name": name,
                "case": case,
                "command": cmd,
                "exit_code": run.returncode,
                "log": str(log_path),
            }
        )
        (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        if name in passing:
            assert run.returncode == 0 and text.count("GPU_DOMAIN_LEASE=PASS") == 2, (
                name,
                case,
            )
        else:
            assert run.returncode == -6 and "Assertion" in text, (name, case)
        print("DOMAIN_LEASE", name, case, "PASS", flush=True)
if a.ready_reference or a.publish_reference or a.idle_reference:
    import re

    def counts(name):
        text = (out / (name + "-0.log")).read_text()
        return [
            int(v)
            for v in re.findall(r"GPU_READY_DISPATCH_MMIO client=\d+ reads=(\d+)", text)
        ]

    measured = {name: counts(name) for name in passing}
    assert all(len(values) == 2 for values in measured.values())
    disabled = "no-ready-reuse" if a.ready_reference else "no-publish-reuse"
    if not a.idle_reference:
        assert measured[disabled] == measured["reference"]
    assert all(c < r for c, r in zip(measured["candidate"], measured["reference"]))
    summary = (
        "idle-proof-summary.json"
        if a.idle_reference
        else (
            "ready-proof-summary.json"
            if a.ready_reference
            else "publish-proof-summary.json"
        )
    )
    (out / summary).write_text(
        json.dumps(
            {
                "status": "PASS",
                "actual_rsi_platform_core": True,
                "models_only": True,
                "mmio_reads_per_live_dispatch": measured,
                "cases_per_client": 25,
                "negative_variants": [name for name in variants if name not in passing],
            },
            indent=2,
        )
        + "\n"
    )
