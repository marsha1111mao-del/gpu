#!/usr/bin/env python3
"""Exercise actual Proxy session admission, rollback, close and ID exhaustion."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess

from gpu_c_source import extract_c_function, replace_c_fragment

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c"
WIRE = ROOT / "Linux-Guest-GPU/include/linux/panthor_vmshm.h"
REALM = ROOT / "Linux-Guest-GPU/include/uapi/linux/realm_gpu.h"
TEST = ROOT / "GPU-SFTP/tests/gpu-proxy-session-budget/session-budget-test.c"


def structure(source, name):
    match = re.search(r"^struct " + re.escape(name) + r" \{", source, re.M)
    assert match, name
    return source[match.start() : source.index("\n};", match.end()) + 3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source = SOURCE.read_text()
    wire = WIRE.read_text()
    names = (
        "panthor_proxy_session_find_locked",
        "panthor_proxy_session_reserve",
        "panthor_proxy_session_unreserve",
        "panthor_proxy_session_create",
        "panthor_proxy_session_release",
        "panthor_proxy_session_put",
        "panthor_proxy_session_destroy",
        "panthor_proxy_sessions_destroy_all",
        "panthor_proxy_session_lookup",
        "panthor_proxy_handle_open_session",
    )
    actual = "\n".join(extract_c_function(source, name) for name in names)
    constants = "\n".join(
        line
        for line in (source + "\n" + wire).splitlines()
        if re.match(r"#define (?:PANTHOR_PROXY_MAX_SESSIONS|PANTHOR_VMSHM_)", line)
    )
    structures = "\n".join(
        (
            structure(source, "panthor_proxy_session"),
            structure(source, "panthor_proxy_session_budget"),
            structure(wire, "panthor_vmshm_open_session_req"),
            structure(wire, "panthor_vmshm_open_session_rsp"),
        )
    )
    mutations = {
        "ignore-client-limit": (
            "budget->sessions >= PANTHOR_PROXY_MAX_SESSIONS_PER_CLIENT",
            "false",
        ),
        "ignore-global-limit": (
            "atomic_read(&panthor_proxy_active_sessions) >= PANTHOR_PROXY_MAX_SESSIONS",
            "false",
        ),
        "leak-failed-create": (
            "out_budget:\n\tpanthor_proxy_session_unreserve(owner_vmid);",
            "out_budget:\n\t(void)owner_vmid;",
        ),
        "keep-failed-open-response": (
            "panthor_proxy_session_destroy(rsp.session_id, owner_vmid);",
            "(void)rsp.session_id;",
        ),
    }
    variants = {"candidate": actual}
    for name, (old, new) in mutations.items():
        variants[name] = replace_c_fragment(actual, old, new, 1)
    results = []
    for name, text in variants.items():
        case = output / name
        case.mkdir()
        (case / "actual.inc").write_text(text)
        (case / "structures.inc").write_text(constants + "\n" + structures + "\n")
        command = [
            os.environ.get("HOST_CC", "cc"),
            "-std=gnu11",
            "-pthread",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-parameter",
            "-g",
            "-O1",
            "-fsanitize=address,undefined",
            "-fno-sanitize-recover=undefined",
            "-fno-omit-frame-pointer",
            "-fno-pie",
            "-no-pie",
            "-I" + str(case),
            "-iquote",
            str(ROOT / "Linux-Guest-GPU/include/uapi"),
            str(TEST),
            "-o",
            str(case / "test"),
        ]
        with (case / "build.log").open("w") as log:
            built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        assert built.returncode == 0, (name, case / "build.log")
        with (case / "run.log").open("w") as log:
            ran = subprocess.run(
                [str(case / "test")], stdout=log, stderr=subprocess.STDOUT, timeout=30
            )
        transcript = (case / "run.log").read_text()
        results.append(
            {
                "case": name,
                "command": command,
                "build_exit_code": built.returncode,
                "run_exit_code": ran.returncode,
                "build_log": str(case / "build.log"),
                "run_log": str(case / "run.log"),
            }
        )
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        assert (
            "ERROR: AddressSanitizer" not in transcript
            and "runtime error:" not in transcript
        )
        if name == "candidate":
            assert (
                ran.returncode == 0 and "GPU_PROXY_SESSION_BUDGET=PASS" in transcript
            ), transcript
        else:
            assert ran.returncode == -6 and "Assertion" in transcript, (
                name,
                transcript,
            )
        print(name + " PASS", flush=True)
    summary = {
        "status": "PASS_PROXY_SESSION_BUDGET_MODEL",
        "negative_variants": len(mutations),
        "scope": "Actual Proxy session create/release/lookup/destroy/open-response functions; bounded pending and retained sessions, allocation rollback, concurrent admission and permanent ID exhaustion; pthread locks and native-channel/DRM doubles",
        "not_covered": "No real Linux workqueue, DRM hardware lifecycle, physical protection or board execution",
        "hardware_tests": "NOT_RUN",
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (SOURCE, WIRE, REALM, TEST, Path(__file__).resolve())
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
