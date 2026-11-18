#!/usr/bin/env python3
"""Execute the actual Proxy vmshm request dispatcher under sustained pressure."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from gpu_c_source import c_fragment_spans

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)

source_path = ROOT / "Linux-Guest-GPU/drivers/char/proxy_vmshm_comm/proxy_comm_vmshm.c"
test_path = ROOT / "GPU-SFTP/tests/gpu-rpc-work-budget/work-budget-test.c"
protocol_path = ROOT / "Linux-Guest-GPU/include/linux/vmshm_comm_protocol.h"
source = source_path.read_text(encoding="utf-8")


def function(name: str) -> str:
    definition = None
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", source):
        close = source.find(")", match.end())
        if close >= 0 and source[close + 1 : close + 24].lstrip().startswith("{"):
            definition = match
    assert definition is not None, name
    match = definition
    start = source.rfind("\n", 0, match.start()) + 1
    if source[start : match.start()].strip() == "":
        start = source.rfind("\n", 0, start - 1) + 1
    return source[start : source.index("\n}", match.end()) + 2] + "\n"


actual = "".join(
    function(name)
    for name in (
        "proxy_comm_vmshm_range_valid",
        "proxy_comm_vmshm_ptr",
        "proxy_comm_vmshm_queue_obj",
        "proxy_comm_vmshm_descs",
        "proxy_comm_vmshm_avail",
        "proxy_comm_vmshm_used",
        "proxy_comm_vmshm_queue_send",
        "proxy_comm_vmshm_queue_recv",
        "proxy_comm_vmshm_ready_locked",
        "proxy_comm_vmshm_recv_from_dev",
        "proxy_comm_vmshm_dispatch_one",
        "proxy_comm_vmshm_drain_rx",
        "proxy_comm_vmshm_rx_work",
    )
)
(out / "actual.inc").write_text(actual, encoding="utf-8")
assert c_fragment_spans(
    actual,
    "u8 payload[PROXY_COMM_VMSHM_MSG_SIZE - sizeof(struct proxy_comm_vmshm_msg)];",
)
assert re.search(r"^#define\s+PROXY_COMM_VMSHM_RX_WORK_BUDGET\s+256\s*$", source, re.M)
assert "unsigned int budget = PROXY_COMM_VMSHM_RX_WORK_BUDGET;" in actual
assert "while (budget--)" in actual
assert "schedule_work(&d->rx_work);" in actual

object_path = out / "work-budget-test.o"
compile_command = [
    os.environ.get("HOST_CC", "cc"),
    "-std=gnu11",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-g",
    "-fsanitize=undefined",
    "-fno-sanitize-recover=undefined",
    "-fno-omit-frame-pointer",
    "-fstack-usage",
    "-fno-pie",
    "-I" + str(out),
    "-c",
    str(test_path),
    "-o",
    str(object_path),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    built = subprocess.run(
        compile_command, stdout=log, stderr=subprocess.STDOUT, check=False
    )
stack_usage = None
if built.returncode == 0:
    executable = out / "work-budget-test"
    link_command = [
        os.environ.get("HOST_CC", "cc"),
        "-fsanitize=undefined",
        "-no-pie",
        str(object_path),
        "-o",
        str(executable),
    ]
    with (out / "link.log").open("w", encoding="utf-8") as log:
        linked = subprocess.run(
            link_command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    if linked.returncode == 0:
        with (out / "run.log").open("w", encoding="utf-8") as log:
            executed = subprocess.run(
                [str(executable)], stdout=log, stderr=subprocess.STDOUT, check=False
            )
    else:
        executed = subprocess.CompletedProcess([str(executable)], None)
else:
    linked = subprocess.CompletedProcess([], 1)
    executed = subprocess.CompletedProcess([], None)

output = (
    (out / "run.log").read_text(encoding="utf-8") if (out / "run.log").exists() else ""
)
metrics_line = next(
    (line for line in output.splitlines() if line.startswith("METRICS ")), ""
)
metrics = dict(re.findall(r"([a-z_]+)=([0-9]+)", metrics_line))
stack_usage_path = out / "work-budget-test.su"
if stack_usage_path.exists():
    usage_lines = stack_usage_path.read_text(encoding="utf-8").splitlines()
    dispatch_usage = next(
        (line for line in usage_lines if "proxy_comm_vmshm_dispatch_one\t" in line), ""
    )
    usage_match = re.search(r"\t([0-9]+)\tstatic$", dispatch_usage)
    if usage_match:
        metrics["stack_bytes_per_request"] = usage_match.group(1)
control_valid = "ORACLE_CONTROL=PASS" in output
actual_budgeted = "GPU_RPC_WORK_BUDGET=PASS" in output
response_backpressure = (
    "RESPONSE_BACKPRESSURE=PASS blocked_queue=256 independent_victim_requests=1"
    in output
)
shared_snapshot = "SHARED_SNAPSHOT=PASS post_receive_shared_mutation_ignored" in output
valid = (
    built.returncode == 0
    and linked.returncode == 0
    and executed.returncode == 0
    and control_valid
    and actual_budgeted
    and response_backpressure
    and shared_snapshot
    and int(metrics.get("max_requests_per_work", "-1")) == 256
    and int(metrics.get("work_reschedules", "-1")) == 32
    and int(metrics.get("total_requests", "-1")) == 8192
    and int(metrics.get("retained_slots", "-1")) == 256
    and int(metrics.get("max_payload_bytes", "0")) == 472
    and int(metrics.get("payload_bytes", "0")) == 8192 * 472
    and int(metrics.get("mutex_visits", "-1")) == 8192
    and int(metrics.get("policy_lock_visits", "-1")) == 8192
    and int(metrics.get("empty_wakeup_count", "-1")) == 4096
    and int(metrics.get("stack_bytes_per_request", "0")) > 472
    and int(metrics.get("victim_before_requests", "-1")) == 1
    and int(metrics.get("victim_after_requests", "-1")) == 1
)
source_files = [source_path, test_path, protocol_path, Path(__file__)]
record = {
    "status": "PASS_RPC_WORK_BUDGET_MODEL" if valid else "FAIL_INVALID_ORACLE",
    "build_exit_code": built.returncode,
    "link_exit_code": linked.returncode if built.returncode == 0 else None,
    "run_exit_code": executed.returncode
    if built.returncode == 0 and linked.returncode == 0
    else None,
    "metrics": metrics,
    "negative_control": "PASS" if control_valid else "FAIL",
    "response_backpressure": "PASS" if response_backpressure else "FAIL",
    "shared_snapshot": "PASS" if shared_snapshot else "FAIL",
    "actual_work_budget": "256_requests_per_work_with_reschedule"
    if actual_budgeted
    else "invalid_oracle",
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Unmodified actual Proxy vmshm queue send/receive, request dispatch, drain, and rx-work functions with a host producer double. A full Proxy-to-Client response queue returns EAGAIN while an independent Client-to-Proxy victim request is still processed. Received header/desc/payload remain a stable private snapshot after the shared window is rewritten. A legal 472-byte payload stream refills the 256-slot request queue across 32 work invocations; the oracle bounds each invocation to 256 requests, verifies rescheduling, and counts requests, stack-allocation events and bytes, mutex/policy-lock visits and intervals, retained slots, empty wakeups, and victim latency before and after pressure",
    "not_covered": "Real Linux workqueue scheduling, concurrent untrusted process timing, Proxy handler implementations beyond the validation double, RMM service cost, physical IRQ delivery, fairness policy, and continuous-availability SLO; this is an L2 scoped resource-budget oracle",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
if not valid:
    raise AssertionError(output or (out / "build.log").read_text(encoding="utf-8"))
print(output, end="")
raise SystemExit(0 if valid else 1)
