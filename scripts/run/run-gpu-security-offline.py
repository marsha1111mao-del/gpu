#!/usr/bin/env python3
"""Repeatable Phase 1 offline runner for the GPU shared-security matrix.

The runner executes only the offline checks declared by the capability map,
creates one fresh evidence directory per run, and records commands, exit codes,
manifest hashes and per-matrix-ID scoped outcomes. It never invokes hardware,
SSH, flashing or performance tests, and never converts L1/L2 model evidence
into a physical-security PASS.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "configs/security/offline-attack-map.json"
DEFAULT_MATRIX = ROOT / "docs/shared/GPU_SHARED_SECURITY_TEST_MATRIX_20261109.csv"
STATUS_HELP = {
    "EVIDENCE_PASS_SCOPED": "All mapped offline checks exited 0; scope remains model/control-flow only",
    "EVIDENCE_FAIL": "At least one mapped offline check failed",
    "NOT_RUN": "Mapped check was not selected in this run",
    "NOT_IMPLEMENTED": "No offline check capability is mapped for this L1/L2-capable item",
    "NOT_VERIFIED": "Physical/L3 evidence is required and was not attempted",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="unique run ID; output must not already exist")
    parser.add_argument("--out", type=Path, help="evidence root (default build/security-runs/<run-id>)")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP, help="capability map JSON")
    parser.add_argument("--seed", help="stable seed recorded for future deterministic injections")
    parser.add_argument("--only", action="append", default=[], metavar="CHECK", help="run named check only; repeatable")
    parser.add_argument("--only-matrix", action="append", default=[], metavar="ID", help="run checks covering matrix ID; repeatable")
    parser.add_argument("--timeout", type=int, default=900, help="per-check timeout in seconds (default 900)")
    parser.add_argument("--manifest-only", action="store_true", help="freeze inputs and schema without executing checks")
    parser.add_argument("--verify-runtime", action="store_true",
                        help="verify frozen firmware and all runtime hashes before running offline checks")
    parser.add_argument("--include-aggregate", action="store_true", help="also run the offline aggregate baseline gate")
    parser.add_argument("--list", action="store_true", help="print mapped IDs/checks and exit without writing evidence")
    args = parser.parse_args()
    if not args.run_id and not args.list:
        parser.error("--run-id is required unless --list is used")
    if args.run_id and ("/" in args.run_id or args.run_id in {".", ".."}):
        parser.error("--run-id must be one path component, not a path")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_map(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "matrix", "baseline", "checks", "manifest_sources"}
    missing = required - data.keys()
    assert not missing, f"capability map missing fields: {sorted(missing)}"
    assert data["schema_version"] == 1, "unsupported capability map schema"
    names = [check["name"] for check in data["checks"]]
    assert len(names) == len(set(names)), "duplicate check names in capability map"
    return data


def load_matrix(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["ID"] for row in rows]
    assert len(ids) == 92 and len(ids) == len(set(ids)), "expected 92 unique matrix IDs"
    return rows


def selected_checks(mapping: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = []
    wanted_ids = set(args.only_matrix)
    for check in mapping["checks"]:
        baseline_gate = bool(check.get("baseline_gate"))
        if baseline_gate and not args.include_aggregate:
            continue
        if args.only and check["name"] not in args.only:
            continue
        if wanted_ids and not wanted_ids.intersection(check["matrix_ids"]):
            continue
        selected.append(check)
    if args.only:
        known = {check["name"] for check in mapping["checks"]}
        unknown = set(args.only) - known
        assert not unknown, f"unknown checks: {sorted(unknown)}"
    if wanted_ids:
        covered = {item for check in selected for item in check["matrix_ids"]}
        missing = wanted_ids - covered
        assert not missing, f"matrix IDs without selected checks: {sorted(missing)}"
    return selected


def build_command(check: dict[str, Any], out_dir: Path) -> tuple[list[str], dict[str, str]]:
    script = ROOT / check["script"]
    mode = check["output"]["mode"]
    if check["kind"] == "python":
        command = [sys.executable, str(script)]
        if mode == "arg":
            command += [check["output"]["flag"], str(out_dir)]
            env = {}
        else:
            env = {check["output"]["variable"]: str(out_dir)}
        command += check.get("extra_args", [])
        return command, env
    if check["kind"] == "shell":
        assert mode == "env", "shell checks must use env output mode"
        return ["bash", str(script)], {check["output"]["variable"]: str(out_dir)}
    raise AssertionError(f"unsupported check kind: {check['kind']}")


def run_check(check: dict[str, Any], evidence: Path, timeout: int, seed: str) -> dict[str, Any]:
    out_dir = evidence / "checks" / check["name"]
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    command, extra_env = build_command(check, out_dir)
    env = os.environ.copy()
    env.update(extra_env)
    env["GPU_SECURITY_RUN_SEED"] = seed
    started = dt.datetime.now(dt.timezone.utc)
    stdout_path = evidence / "logs" / f"{check['name']}.stdout.log"
    stderr_path = evidence / "logs" / f"{check['name']}.stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            proc = subprocess.run(command, cwd=ROOT, env=env, timeout=timeout,
                                  stdout=stdout, stderr=stderr, check=False)
            exit_code, timeout_flag = proc.returncode, False
        except subprocess.TimeoutExpired:
            exit_code, timeout_flag = 124, True
    finished = dt.datetime.now(dt.timezone.utc)
    return {
        "name": check["name"],
        "command": command,
        "output_env": extra_env,
        "timeout_seconds": timeout,
        "timed_out": timeout_flag,
        "exit_code": exit_code,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "stdout_log": str(stdout_path.relative_to(evidence)),
        "stderr_log": str(stderr_path.relative_to(evidence)),
        "output_dir": str(out_dir.relative_to(evidence)),
        "matrix_ids": check["matrix_ids"],
        "evidence_boundary": check["evidence_boundary"],
        "result": "PASS_OFFLINE" if exit_code == 0 and not timeout_flag else "FAIL_OFFLINE",
    }


def git_state() -> dict[str, Any]:
    def git(*arguments: str) -> str:
        proc = subprocess.run(["git", *arguments], cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    status = git("status", "--short")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status),
    }


def freeze_manifest(evidence: Path, args: argparse.Namespace, mapping: dict[str, Any],
                    matrix_rows: list[dict[str, str]]) -> dict[str, Any]:
    matrix_path = (ROOT / mapping["matrix"]).resolve()
    hashes: dict[str, str] = {}
    for relative in mapping["manifest_sources"]:
        path = (ROOT / relative).resolve()
        assert path.is_file(), f"manifest source missing: {relative}"
        hashes[relative] = sha256_file(path)
    for check in mapping["checks"]:
        relative = check["script"]
        path = ROOT / relative
        assert path.is_file(), f"mapped check missing: {relative}"
        hashes[relative] = sha256_file(path)
    captured_at = dt.datetime.now(dt.timezone.utc)
    seed = args.seed or hashlib.sha256(f"{args.run_id}|{captured_at.isoformat()}".encode()).hexdigest()
    manifest = {
        "schema_version": 1,
        "run_id": args.run_id,
        "captured_at": captured_at.isoformat(),
        "phase": "Phase 1 offline capability and evidence freeze",
        "hardware_tests": "NOT_RUN",
        "performance_tests": "NOT_RUN",
        "runtime_gpu_code_changed": False,
        "seed": seed,
        "seed_semantics": "recorded for future deterministic injection; current checks do not claim to consume it",
        "baseline": mapping["baseline"],
        "matrix": {
            "path": str(matrix_path.relative_to(ROOT)),
            "rows": len(matrix_rows),
            "sha256": sha256_file(matrix_path),
        },
        "capability_map": {
            "path": str(args.map.resolve().relative_to(ROOT)),
            "sha256": sha256_file(args.map.resolve()),
        },
        "git": git_state(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "sources": hashes,
    }
    write_json(evidence / "manifest.json", manifest)
    return manifest


def verify_runtime_freeze(mapping: dict[str, Any]) -> dict[str, Any]:
    freeze = mapping.get("runtime_freeze")
    assert isinstance(freeze, dict), "capability map has no runtime_freeze section"
    root = ROOT / freeze["root"]
    entries: dict[str, Any] = {}
    for relative, expected in freeze.get("firmware", {}).items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else None
        entries[relative] = {"expected": expected, "actual": actual,
                             "match": actual == expected}
    manifests: dict[str, Any] = {}
    for relative in freeze.get("manifests", []):
        manifest_path = root / relative
        if not manifest_path.is_file():
            manifests[relative] = {"match": False, "files": {}}
            continue
        declared = json.loads(manifest_path.read_text(encoding="utf-8"))
        files: dict[str, Any] = {}
        for name, expected in declared.items():
            path = manifest_path.parent / name
            actual = sha256_file(path) if path.is_file() else None
            files[name] = {"expected": expected, "actual": actual,
                           "match": actual == expected}
        manifests[relative] = {"match": all(item["match"] for item in files.values()),
                               "files": files}
    result = {
        "root": str(root),
        "firmware": entries,
        "manifests": manifests,
        "match": all(item["match"] for item in entries.values()) and
                 all(item["match"] for item in manifests.values()),
        "boundary": "Local frozen payload verification only; it does not prove current SD2 or deployed Guest contents",
    }
    return result


def matrix_results(mapping: dict[str, Any], rows: list[dict[str, str]],
                   outcomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    mapped: dict[str, list[str]] = {}
    for check in mapping["checks"]:
        if check.get("baseline_gate"):
            continue
        for item in check["matrix_ids"]:
            mapped.setdefault(item, []).append(check["name"])
    results: dict[str, Any] = {}
    for row in rows:
        item = row["ID"]
        layers = row["验证层次"]
        names = mapped.get(item, [])
        if not names:
            status = "NOT_VERIFIED" if "L1" not in layers and "L2" not in layers else "NOT_IMPLEMENTED"
            executed = []
        else:
            executed = [outcomes[name] for name in names if name in outcomes]
            if not executed:
                status = "NOT_RUN"
            elif all(entry["result"] == "PASS_OFFLINE" for entry in executed):
                status = "EVIDENCE_PASS_SCOPED"
            else:
                status = "EVIDENCE_FAIL"
        results[item] = {
            "status": status,
            "layers": layers,
            "priority": row["优先级"],
            "mapped_checks": names,
            "executed_checks": [entry["name"] for entry in executed],
            "full_pass_boundary": "Current mapped evidence is L1/L2 model/control-flow only; it cannot certify physical security or replace L3",
        }
    return results


def evidence_index(evidence: Path) -> list[dict[str, str]]:
    entries = []
    for path in sorted(p for p in evidence.rglob("*") if p.is_file()):
        entries.append({
            "path": str(path.relative_to(evidence)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        })
    return entries


def main() -> int:
    args = parse_args()
    mapping = load_map(args.map)
    matrix_rows = load_matrix(ROOT / mapping["matrix"])
    mapped_ids = {item for check in mapping["checks"] for item in check["matrix_ids"]}
    known_ids = {row["ID"] for row in matrix_rows}
    assert mapped_ids <= known_ids, f"map contains unknown matrix IDs: {sorted(mapped_ids - known_ids)}"
    if args.list:
        for check in mapping["checks"]:
            print(f"{check['name']}: {' '.join(check['matrix_ids']) or '(baseline gate)'}")
        return 0

    evidence = (args.out or ROOT / "build/security-runs" / args.run_id).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence / "logs").mkdir()
    manifest = freeze_manifest(evidence, args, mapping, matrix_rows)
    if args.verify_runtime:
        runtime = verify_runtime_freeze(mapping)
        manifest["runtime_verification"] = runtime
        write_json(evidence / "manifest.json", manifest)
        if not runtime["match"]:
            write_json(evidence / "summary.json", {
                "schema_version": 1, "run_id": args.run_id,
                "status": "FAIL_RUNTIME_FREEZE", "checks_run": 0,
                "runtime_verification": runtime,
                "hardware_tests": "NOT_RUN", "performance_tests": "NOT_RUN",
                "conclusion_boundary": "Frozen runtime payload mismatch; offline attack checks were not executed",
            })
            write_json(evidence / "evidence-index.json", evidence_index(evidence))
            print(json.dumps({"status": "FAIL_RUNTIME_FREEZE", "run_id": args.run_id,
                              "evidence": str(evidence)}, ensure_ascii=False))
            return 2
    outcomes: dict[str, dict[str, Any]] = {}
    if args.manifest_only:
        check_results = []
        harness_status = "PASS_MANIFEST_ONLY"
    else:
        checks = selected_checks(mapping, args)
        check_results = [run_check(check, evidence, args.timeout, manifest["seed"]) for check in checks]
        outcomes = {entry["name"]: entry for entry in check_results}
        harness_status = ("PASS_OFFLINE_HARNESS"
                          if check_results and all(entry["result"] == "PASS_OFFLINE" for entry in check_results)
                          else "FAIL_OFFLINE_HARNESS")
    write_json(evidence / "check-results.json", check_results)
    matrix = matrix_results(mapping, matrix_rows, outcomes)
    write_json(evidence / "matrix-results.json", matrix)
    counts: dict[str, int] = {}
    for entry in matrix.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    summary = {
        "schema_version": 1,
        "run_id": args.run_id,
        "status": harness_status,
        "checks_run": len(check_results),
        "matrix_counts": counts,
        "status_definitions": STATUS_HELP,
        "hardware_tests": "NOT_RUN",
        "performance_tests": "NOT_RUN",
        "glmark": {"measured_by_this_runner": False, "reference_name": mapping["baseline"]["name"],
                    "reference_score": mapping["baseline"].get("single_client_720p_glmark"),
                    "scope": "External candidate reference only; offline checks do not measure or certify performance"},
        "conclusion_boundary": "Phase 1 inventory/capability evidence only; scoped offline pass is not a physical-security PASS",
    }
    write_json(evidence / "summary.json", summary)
    write_json(evidence / "evidence-index.json", evidence_index(evidence))
    print(json.dumps({
        "status": summary["status"], "run_id": args.run_id,
        "evidence": str(evidence), "matrix_counts": counts,
        "hardware_tests": "NOT_RUN", "performance_tests": "NOT_RUN",
    }, ensure_ascii=False))
    return 0 if summary["status"] in {"PASS_OFFLINE_HARNESS", "PASS_MANIFEST_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
