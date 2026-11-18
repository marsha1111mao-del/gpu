#!/usr/bin/env python3
"""RPC09/RPC12: exact lengths and directions for every Proxy handler."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c"
TEST = ROOT / "GPU-SFTP/tests/gpu-proxy-handler-dispatch/handler-dispatch-test.c"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = SOURCE.read_text(encoding="utf-8")

table_start = source.index("static const struct panthor_proxy_msg_handler panthor_proxy_handlers[] = {")
table_end = source.index("\n};\n", table_start) + 3
table = source[table_start:table_end]
entries = re.findall(r"\.req_type\s*=\s*(PANTHOR_VMSHM_MSG_[A-Z0-9_]+)", table)
assert len(entries) >= 12 and len(entries) == len(set(entries))
assert table.count(".req_size = sizeof(struct panthor_vmshm_") == len(entries)
assert table.count(".handler = panthor_proxy_handle_") == len(entries)

macros = sorted(set(re.findall(r"PANTHOR_VMSHM_MSG_[A-Z0-9_]+", table)))
prefix = "#include <stdint.h>\n"
for index, macro in enumerate(macros):
    prefix += f"#define {macro} (0x1000U + {index}U)\n"
table = re.sub(r"\.req_size\s*=\s*sizeof\(struct panthor_vmshm_[A-Za-z0-9_]+\)",
               ".req_size = sizeof(struct dispatched_request)", table)
table = re.sub(r"\.handler\s*=\s*panthor_proxy_handle_[A-Za-z0-9_]+",
               ".handler = observed_handler", table)
table += f"\nstatic const u32 panthor_proxy_handlers_count = {len(entries)}U;\n"

find_start = source.index("static const struct panthor_proxy_msg_handler *\npanthor_proxy_find_handler(")
find_end = source.index("\n}\n", find_start) + 3
rx_start = source.index("static int panthor_proxy_rx_handler(")
rx_end = source.index("\n}\n", rx_start) + 3
actual = source[find_start:find_end] + "\n" + source[rx_start:rx_end]
assert "rx->len != handler->req_size" in actual
assert actual.index("panthor_proxy_find_handler(rx->type)") < actual.index("rx->len != handler->req_size")
assert actual.index("rx->len != handler->req_size") < actual.index("handler->handler(")

skip_length = actual.replace(
    "if (rx->len != handler->req_size) {",
    "if (false) {",
    1,
)
assert skip_length != actual
variants = {
    "candidate": (actual, True),
    "skip-length": (skip_length, False),
}
results = []
for name, (dispatch, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    (case / "table.inc").write_text(prefix + table, encoding="utf-8")
    (case / "actual.inc").write_text(dispatch, encoding="utf-8")
    command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-parameter",
        "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
        "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-I" + str(case),
        str(TEST), "-o", str(case / "test"),
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
              "PROXY_HANDLER_DISPATCH=PASS" in output)
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
    "status": "PASS_PROXY_HANDLER_DISPATCH_MODEL",
    "handler_count": len(entries),
    "results": results,
    "negative_variants_rejected": 1,
    "source_sha256": {
        str(SOURCE.relative_to(ROOT)): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        str(TEST.relative_to(ROOT)): hashlib.sha256(TEST.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": f"Unmodified actual Proxy find/rx dispatch functions over all {len(entries)} registered request handlers; every handler rejects short and long payloads before callback, response types do not match request dispatch, and exact-size legal requests reach the handler",
    "not_covered": "Per-handler semantic flags/reserved fields, Client response structure semantics, real vmshm transport, and Linux concurrency",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": record["status"],
                  "handler_count": record["handler_count"],
                  "negative_variants_rejected": record["negative_variants_rejected"],
                  "evidence": str(out), "models_only": True}, ensure_ascii=False))
