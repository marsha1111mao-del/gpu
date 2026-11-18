#!/usr/bin/env python3
"""Reject Client command/sync contents in Proxy scheduler diagnostics."""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Linux-Guest-GPU/drivers/gpu/drm/panthor/panthor_sched.c"
RUNNER = ROOT / "GPU-SFTP/tests/realm-xshm/run-realms.py"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
source = SOURCE.read_text(encoding="utf-8")
runner = RUNNER.read_text(encoding="utf-8")


def extract_function(text: str) -> str:
    name_at = text.index("panthor_dump_queue_diag_locked(")
    start = text.rfind("static void", 0, name_at)
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def disclosures(function: str) -> list[str]:
    findings = []
    forbidden = {
        "raw_instruction_words": r"instr[0-7]=",
        "raw_syncobj_words": r"sync_raw[01]=",
        "raw_ring_probe": r"(?<!_)rb_probe=%#llx",
    }
    for name, pattern in forbidden.items():
        if re.search(pattern, function) is not None:
            findings.append(name)
    if "READ_ONCE(*(u64 *)syncobj)" in function:
        findings.append("syncobj_raw_read_for_output")
    return findings


function = extract_function(source)
findings = disclosures(function)
required = {
    "content_summary_marker": "[MZH][PANTHOR_JOB_CONTENT_DIAG]",
    "bounded_word_count": "sampled_words=8",
    "non_content_summary": "sampled_nonzero=%u",
    "probe_presence_only": "rb_probe_present=%u",
}
missing = [name for name, marker in required.items() if marker not in function]

vulnerable_control = function.replace(
    """\t\tdrm_err(&ptdev->base,
\t\t\t "[MZH][PANTHOR_JOB_CONTENT_DIAG] reason=%s csg=%u cs=%u sampled_words=8 sampled_nonzero=%u\\n",
\t\t\t reason, csg_id, cs_id, sampled_nonzero);""",
    """\t\tdrm_err(&ptdev->base,
\t\t\t "[MZH][PANTHOR_JOB_INSTR] instr0=%#llx instr1=%#llx\\n",
\t\t\t (unsigned long long)sampled_nonzero, 0ULL);""",
    1,
)
control_findings = disclosures(vulnerable_control)
assert control_findings == ["raw_instruction_words"], control_findings

boot_args_visible = "loglevel=6" in runner
status = "PASS_DIAGNOSTIC_CONTENT_REDACTION" if not findings and not missing else "FAIL_DIAGNOSTIC_CONTENT_DISCLOSURE"
record = {
    "status": status,
    "findings": findings,
    "missing_protections": missing,
    "negative_control_findings": control_findings,
    "reachability": {
        "proxy_boot_loglevel": 6 if boot_args_visible else None,
        "diagnostic_calls_use_drm_err": "drm_err(&ptdev->base," in function,
    },
    "source_sha256": {
        str(SOURCE.relative_to(ROOT)): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        str(RUNNER.relative_to(ROOT)): hashlib.sha256(RUNNER.read_bytes()).hexdigest(),
        str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    },
    "scope": "Static audit of the actual Proxy scheduler fault/timeout diagnostic function; rejects raw instruction, syncobj and ring-probe words while requiring a bounded non-content summary",
    "not_covered": "Complete log/export inventory, real serial capture, debugfs mount permissions, coredump, FW readback, persistent outputs, and side channels",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, ensure_ascii=False))
raise SystemExit(0 if status == "PASS_DIAGNOSTIC_CONTENT_REDACTION" else 1)
