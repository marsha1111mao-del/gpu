#!/usr/bin/env python3
"""Exercise actual Client vmshm queue validators over an untrusted window."""

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
test_path = ROOT / "GPU-SFTP/tests/xshm-queue-integrity/queue-integrity-test.c"
source = source_path.read_text(encoding="utf-8")

def function(name):
    match = re.search(r"\b" + re.escape(name) + r"\s*\(", source)
    assert match, name
    start = source.rfind("\n", 0, match.start()) + 1
    if source[start:match.start()].strip() == "":
        start = source.rfind("\n", 0, start - 1) + 1
    return source[start:source.index("\n}", match.end()) + 2] + "\n"

actual = "".join(function(name) for name in (
    "client_comm_vmshm_range_valid",
    "client_comm_vmshm_ptr",
    "client_comm_vmshm_queue_obj",
    "client_comm_vmshm_descs",
    "client_comm_vmshm_avail",
    "client_comm_vmshm_used",
    "client_comm_vmshm_queue_send",
    "client_comm_vmshm_queue_recv",
))
(out / "actual.inc").write_text(actual, encoding="utf-8")

linux = out / "stubs" / "linux"
linux.mkdir(parents=True)
(linux / "build_bug.h").write_text("#define static_assert _Static_assert\n", encoding="utf-8")
(linux / "stddef.h").write_text("#include <stddef.h>\n", encoding="utf-8")
(linux / "types.h").write_text(
    "#include <stdint.h>\n"
    "typedef uint8_t u8;\ntypedef uint16_t u16;\ntypedef uint32_t u32;\n"
    "typedef uint64_t u64;\ntypedef int16_t s16;\ntypedef int32_t s32;\n",
    encoding="utf-8",
)

command = [
    os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
    "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
    "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-I" + str(out),
    "-I" + str(out / "stubs"),
    "-I" + str(ROOT / "Linux-Guest-GPU/include"), str(test_path),
    "-o", str(out / "queue-integrity-test"),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
assert build.returncode == 0, (out / "build.log").read_text(encoding="utf-8")
with (out / "run.log").open("w", encoding="utf-8") as log:
    run = subprocess.run([str(out / "queue-integrity-test")], stdout=log,
                         stderr=subprocess.STDOUT, check=False)
output = (out / "run.log").read_text(encoding="utf-8")
assert run.returncode == 0 and "XSHM_QUEUE_INTEGRITY=PASS" in output, output

record = {
    "status": "PASS_XSHM_QUEUE_INTEGRITY_MODEL",
    "cases": 15,
    "build_exit_code": build.returncode,
    "run_exit_code": run.returncode,
    "source_sha256": {
        str(source_path.relative_to(ROOT)): hashlib.sha256(source_path.read_bytes()).hexdigest(),
        str(test_path.relative_to(ROOT)): hashlib.sha256(test_path.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": "Unmodified extracted Client queue send/receive helpers with a synthetic untrusted shared window; no concurrent peer, IRQ, or real vmshm device",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(output.strip())
