#!/usr/bin/env python3
"""Deterministic RPC27 timeout/late-callback model using actual Client code."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c"
TEST = ROOT / "GPU-SFTP/tests/xshm-reply-replay/late-callback-test.c"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = SOURCE.read_text(encoding="utf-8")


def extract(name: str) -> str:
    match = re.search(rf"^(?:static )?(?:int|void|bool) {name}\(", source, re.MULTILINE)
    assert match, name
    return source[match.start():source.index("\n}", match.end()) + 2] + "\n"


wire = (ROOT / "Linux-Guest-GPU/include/linux/panthor_vmshm.h").read_text()
wire_parts = ["#include <linux/types.h>"] + [line for line in wire.splitlines() if line.startswith("#define PANTHOR_VMSHM_") and "RMM_TASK" in line]
for name in ["panthor_vmshm_rmm_task_req", "panthor_vmshm_rmm_task_rsp"]:
    start = wire.index("struct " + name + " {")
    wire_parts.append(wire[start:wire.index("\n};", start) + 3])
actual = "\n".join(wire_parts) + "\n" + extract("client_comm_vmshm_event_wait")
actual += extract("client_comm_vmshm_dispatch_response") + extract("client_comm_vmshm_call")

# These source-order properties are the lifetime contract exercised below.
dispatch = actual[:actual.index("int client_comm_vmshm_call(")]
assert dispatch.index("spin_lock(&d->waiters_lock);") < dispatch.index("goto found_waiter;")
assert dispatch.index("goto found_waiter;") < dispatch.index("list_del_init(&waiter->node);")
assert dispatch.index("list_del_init(&waiter->node);") < dispatch.index("complete(&waiter->done);")
assert dispatch.index("complete(&waiter->done);") < dispatch.index("spin_unlock(&d->waiters_lock);")
call = actual[actual.index("int client_comm_vmshm_call("):]
timeout_at = call.index("if (!timeout) {")
timeout_path = call[timeout_at:call.index("out_unlock:", timeout_at)]
assert timeout_path.index("spin_lock(&d->waiters_lock);") < timeout_path.index("completed = list_empty(&waiter.node);")
assert timeout_path.index("completed = list_empty(&waiter.node);") < timeout_path.index("list_del_init(&waiter.node);")
assert timeout_path.index("list_del_init(&waiter.node);") < timeout_path.index("spin_unlock(&d->waiters_lock);")

variants = {
    "candidate": (actual, True),
    "dispatch-keep-completed-node": (
        actual.replace("\t\tlist_del_init(&waiter->node);\n\t\tcomplete(&waiter->done);",
                       "\t\tcomplete(&waiter->done);", 1), False),
    "timeout-ignore-race-result": (
        actual.replace("\t\t\tcompleted = list_empty(&waiter.node);",
                       "\t\t\tcompleted = false;", 1), False),
}
assert variants["dispatch-keep-completed-node"][0] != actual
assert variants["timeout-ignore-race-result"][0] != actual

results = []
for name, (code, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    (case / "actual.inc").write_text(code, encoding="utf-8")
    command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
        "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-pthread",
        "-I" + str(case), str(TEST), "-o", str(case / "test"),
    ]
    with (case / "build.log").open("w", encoding="utf-8") as log:
        build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    run_exit = None
    output = (case / "build.log").read_text(encoding="utf-8")
    if build.returncode == 0:
        with (case / "run.log").open("w", encoding="utf-8") as log:
            run = subprocess.run([str(case / "test")], stdout=log,
                                 stderr=subprocess.STDOUT, check=False)
        run_exit = run.returncode
        output = (case / "run.log").read_text(encoding="utf-8")
    passed = (expected_pass and build.returncode == 0 and run_exit == 0 and
              "RPC_LATE_WAITER=PASS" in output)
    rejected = (not expected_pass and build.returncode == 0 and
                run_exit == -6 and "Assertion" in output)
    result = "PASS" if passed or rejected else "FAIL"
    results.append({
        "name": name,
        "command": command,
        "build_exit_code": build.returncode,
        "run_exit_code": run_exit,
        "expected": "PASS" if expected_pass else "REJECT",
        "result": result,
        "log": str(case / ("run.log" if build.returncode == 0 else "build.log")),
    })
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    assert result == "PASS", (name, output[-2000:])

record = {
    "status": "PASS_RPC_LATE_WAITER_MODEL",
    "results": results,
    "negative_variants_rejected": 2,
    "source_sha256": {
        str(SOURCE.relative_to(ROOT)): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        str(TEST.relative_to(ROOT)): hashlib.sha256(TEST.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": "Unmodified actual client_comm_vmshm_call and response dispatcher with host completion/jiffies/queue doubles; deterministic dispatcher-first and timeout-first interleavings, including a late reply blocked until timeout removal",
    "not_covered": "Real Linux IRQ/workqueue scheduling, waitqueue internals, signal interruption, transport loss, and KASAN/KCSAN board execution",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "status": record["status"],
    "negative_variants_rejected": record["negative_variants_rejected"],
    "evidence": str(out),
    "models_only": True,
}, ensure_ascii=False))
