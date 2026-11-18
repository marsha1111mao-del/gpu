#!/usr/bin/env python3
"""Check actual Client reply matching and expose sequence-wrap policy gaps."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)

source_path = ROOT / "Linux-Guest-GPU/drivers/char/client_vmshm_comm/client_comm_vmshm.c"
test_path = ROOT / "GPU-SFTP/tests/xshm-reply-replay/reply-replay-test.c"
source = source_path.read_text(encoding="utf-8")
match = re.search(r"^static int client_comm_vmshm_dispatch_response\(", source, re.M)
assert match
(out / "actual.inc").write_text(
    source[match.start():source.index("\n}", match.end()) + 2] + "\n",
    encoding="utf-8",
)

command = [
    os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
    "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
    "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-I" + str(out),
    str(test_path), "-o", str(out / "reply-replay-test"),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
assert build.returncode == 0, (out / "build.log").read_text(encoding="utf-8")
with (out / "run.log").open("w", encoding="utf-8") as log:
    run = subprocess.run([str(out / "reply-replay-test")], stdout=log,
                         stderr=subprocess.STDOUT, check=False)
output = (out / "run.log").read_text(encoding="utf-8")
assert run.returncode == 0 and "REPLY_MATCH=PASS" in output, output

allocator = "seq = (u64)atomic64_inc_return(&d->next_seq);"
initialization = "atomic64_set(&client_comm_vmshm_dev.next_seq, 0);"
assert source.count(allocator) >= 1
assert source.count(initialization) == 1
call_body = source[source.index(allocator):source.index("out_unlock:", source.index(allocator))]
wrap_guard = re.search(r"if\s*\([^)]*!seq", call_body) is not None
zero_accepted = "SEQUENCE_ZERO_ACCEPTED=1" in output
zero_rejected = "SEQUENCE_ZERO_REJECTED=1" in output
policy_gap = (zero_accepted or not zero_rejected) and not wrap_guard
status = "FAIL_XSHM_REPLY_REPLAY_WRAP_POLICY" if policy_gap else "PASS_XSHM_REPLY_REPLAY_MODEL"

record = {
    "status": status,
    "reply_matching_cases": 5,
    "build_exit_code": build.returncode,
    "run_exit_code": run.returncode,
    "sequence_zero_accepted_by_actual_dispatcher": zero_accepted,
    "explicit_wrap_guard_found": wrap_guard,
    "security_gap": (
        "The actual dispatcher accepts reply_to=0. next_seq starts at 0 and uses atomic64_inc_return without an explicit zero/overflow rejection, so a 2^64 wrap can recreate the accepted zero sequence."
        if policy_gap else None
    ),
    "source_sha256": {
        str(source_path.relative_to(ROOT)): hashlib.sha256(source_path.read_bytes()).hexdigest(),
        str(test_path.relative_to(ROOT)): hashlib.sha256(test_path.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": "Unmodified extracted Client response dispatcher with controlled receive double; sequence allocator policy checked from the actual call path source",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, ensure_ascii=False))
raise SystemExit(1 if policy_gap else 0)
