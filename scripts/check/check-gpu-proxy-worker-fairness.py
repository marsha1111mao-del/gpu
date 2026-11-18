#!/usr/bin/env python3
"""RPC38: exercise actual Proxy IRQ worker Group round-robin fairness."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c"
TEST = ROOT / "GPU-SFTP/tests/gpu-irq-security/proxy-worker-fairness-test.c"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = SOURCE.read_text(encoding="utf-8")

start = source.index("static void panthor_proxy_irq_work(struct work_struct *work)\n{")
end = source.index("\nstatic int panthor_proxy_session_destroy(", start)
actual = source[start:end]
assert "session->irq_group_cursor" in actual
assert actual.index("visited++ < session->irq_group_cursor") < actual.index("if (!budget--)")
assert actual.index("if (!budget--)") < actual.index("session->irq_group_cursor =")

starved = actual.replace(
    "\t\tsession->irq_group_cursor = exhausted ? visited - 1 : 0;",
    "\t\t\tsession->irq_group_cursor = 0;",
    1,
).replace(
    "\t\tbool exhausted = false;",
    "\t\tbool exhausted = false; (void)exhausted;",
    1,
)
assert starved != actual
variants = {
    "candidate": (actual, True),
    "reset-group-cursor": (starved, False),
}
results = []
for name, (function, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    (case / "actual.inc").write_text(function, encoding="utf-8")
    command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
        "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
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
              "PROXY_IRQ_WORKER_FAIRNESS=PASS" in output)
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
    "status": "PASS_PROXY_IRQ_WORKER_FAIRNESS_MODEL",
    "results": results,
    "negative_variants_rejected": 1,
    "source_sha256": {
        str(SOURCE.relative_to(ROOT)): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        str(TEST.relative_to(ROOT)): hashlib.sha256(TEST.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": "Unmodified actual Proxy IRQ worker with modelled session list, xarray and persistent RMM Group events; 12 Groups must all be peeked/claimed within two budget-8 rounds",
    "not_covered": "Real Linux workqueue timing, IRQ injection, session churn, xarray concurrency, RMM event semantics, and board execution",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": record["status"],
                  "negative_variants_rejected": record["negative_variants_rejected"],
                  "evidence": str(out), "models_only": True}, ensure_ascii=False))
