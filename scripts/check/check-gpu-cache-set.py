#!/usr/bin/env python3
"""Actual core differential paths, AS/cache models, and rejected mutants."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu_private.c"
FIXTURE = ROOT / "opencca/tf-rmm/runtime/tests/opencca_gpu_cache_set_test.c"
HEADER = ROOT / "opencca/tf-rmm/runtime/include/opencca_gpu_private.h"


def main():
    source = CORE.read_text()
    mutations = {
        "epoch": ("set->context == context && set->epoch == ctx->mapping_epoch &&",
                  "set->context == context &&"),
        "lease": ("(for_cpu ? bo->cache_context != ctx->handle :\n\t\t\t\t(bo->cache_context != 0UL && bo->cache_context != ctx->handle))",
                  "((void)for_cpu, false)"),
        "barrier": ("\t\tgoto barrier;", "\t\tuncached_seen = false;\n\t\tgoto barrier;"),
        "closing": ("bo->service != service || bo->closing || bo->handle == 0UL",
                    "bo->service != service || bo->handle == 0UL"),
        "early_valid": ("set->eligible = true;", "set->eligible = true; set->valid = true;"),
        "hidden": ("bo->hidden != bo->pages || bo->mapped == 0U ||", "bo->mapped == 0U ||"),
    }
    versions = {"candidate": source}
    for name, (old, new) in mutations.items():
        assert source.count(old) == 1, name
        versions[name] = source.replace(old, new)
    # Source, fixture and logs can be retained in a run-owned evidence folder.
    supplied = os.environ.get("GPU_CACHE_SET_OUT")
    temporary = None if supplied else tempfile.TemporaryDirectory(prefix="gpu-cache-set-")
    out = Path(supplied or temporary.name)
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    outputs = {}
    for name, text in versions.items():
        folder = out / name
        folder.mkdir(exist_ok=True)
        (folder / CORE.name).write_text(text)
        (folder / FIXTURE.name).write_bytes(FIXTURE.read_bytes())
        (folder / HEADER.name).write_bytes(HEADER.read_bytes())
        command = [os.environ.get("HOST_CC", "cc"), "-std=c11", "-O2", "-Wall", "-Wextra",
                   "-Werror", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                   "-fno-pie", "-no-pie", "-I" + str(folder), str(folder / FIXTURE.name),
                   "-o", str(folder / "test")]
        build = subprocess.run(command, capture_output=True, text=True)
        (folder / "build.log").write_text(build.stdout + build.stderr)
        assert build.returncode == 0, (name, build.stderr)
        rejected = None
        lines = []
        modes = [0, 1] if name == "candidate" else [1]
        for enabled in modes:
            results = []
            for scenario in range(28):
                result = subprocess.run([str(folder / "test"), str(scenario), str(enabled)],
                                        capture_output=True, text=True)
                lines.append(result.stdout + result.stderr)
                results.append(result.stdout)
                if result.returncode:
                    rejected = dict(scenario=scenario, enabled=enabled, exit_code=result.returncode)
                    break
            if name == "candidate":
                assert rejected is None, rejected
                outputs[enabled] = results
            if rejected:
                break
        (folder / "run.log").write_text("".join(lines))
        if name != "candidate":
            assert rejected is not None, (name, "mutant escaped")
        checks.append(dict(name=name, build_command=command, build_exit=build.returncode,
                           runs=len(lines), rejected=rejected,
                           source_sha256=hashlib.sha256(text.encode()).hexdigest()))
    assert outputs[0] == outputs[1]
    record = dict(status="PASS", checks=checks, reference_cases=28, candidate_cases=28,
                  mutants_rejected=len(mutations), model_only=True, goal_complete=False)
    (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    print("GPU_PRIVATE_CACHE_SET=PASS cases=28 modes=2 mutants=6; actual core, modeled AS/cache/CPU visibility")
    if temporary:
        temporary.cleanup()


if __name__ == "__main__":
    main()
