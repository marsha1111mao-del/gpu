#!/usr/bin/env python3
"""Exercise actual Panthor GEM publication with DRM reference-count doubles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
GUEST = ROOT / "Linux-Guest-GPU"
R10_TEST = ROOT / "GPU-SFTP/tests/gpu-gem-lifecycle/gem-lifecycle-test.c"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)

source = (GUEST / "drivers/gpu/drm/panthor/panthor_gem.c").read_text(encoding="utf-8")

def extract(name):
    match = f"\nint {name}("
    assert source.count(match) == 1, name
    start = source.index(match) + 1
    end = source.index("\n}\n", start) + 3
    return source[start:end]

actual = "".join(extract(name) for name in (
    "panthor_gem_create_private_with_handle",
    "panthor_gem_create_with_handle",
))
(out / "actual.inc").write_text(actual, encoding="utf-8")
(out / "gem-lifecycle-test.c").write_text(R10_TEST.read_text(encoding="utf-8"), encoding="utf-8")

publish_before_init_old = """\tbo->flags = flags;
\tbo->rmm_private_handle = private_handle;
\tbo->rmm_channel = channel;
\tbo->base.base.funcs = &private_gem_funcs;
\tif (exclusive_vm) {
\t\tbo->exclusive_vm_root_gem = panthor_vm_root_gem(exclusive_vm);
\t\tdrm_gem_object_get(bo->exclusive_vm_root_gem);
\t\tbo->base.base.resv = bo->exclusive_vm_root_gem->resv;
\t}
\tret = drm_gem_handle_create(file, &shmem->base, handle);"""
publish_before_init_new = """\tret = drm_gem_handle_create(file, &shmem->base, handle);
\tbo->flags = flags;
\tbo->rmm_private_handle = private_handle;
\tbo->rmm_channel = channel;
\tbo->base.base.funcs = &private_gem_funcs;
\tif (exclusive_vm) {
\t\tbo->exclusive_vm_root_gem = panthor_vm_root_gem(exclusive_vm);
\t\tdrm_gem_object_get(bo->exclusive_vm_root_gem);
\t\tbo->base.base.resv = bo->exclusive_vm_root_gem->resv;
\t}"""
skip_private_put_old = """\tif (!ret)
\t\t*size = shmem->base.size;
\tdrm_gem_object_put(&shmem->base);"""
skip_private_put_new = """\tif (!ret)
\t\t*size = shmem->base.size;"""
skip_share_cleanup_old = """\tif (ret)
\t\tgoto err_put_object;
"""
skip_share_cleanup_tail_old = """\treturn ret;

err_put_object:
\tdrm_gem_object_put(&shmem->base);
\treturn ret;
}"""
skip_share_cleanup_tail_new = """\treturn ret;
}"""
skip_share_cleanup_old = """\tif (ret)
\t\tgoto err_put_object;"""
skip_share_cleanup_new = """\tif (ret)
\t\treturn ret;"""

variants = {
    "candidate": (actual, True),
    "publish-before-init": (
        actual.replace(publish_before_init_old, publish_before_init_new, 1), False),
    "skip-private-put": (
        actual.replace(skip_private_put_old, skip_private_put_new, 1), False),
    "skip-share-cleanup": (
        actual.replace(skip_share_cleanup_old, skip_share_cleanup_new, 1)
              .replace(skip_share_cleanup_tail_old, skip_share_cleanup_tail_new, 1), False),
}
assert variants["publish-before-init"][0] != actual
assert variants["skip-private-put"][0] != actual
assert variants["skip-share-cleanup"][0] != actual

records = []
for name, (code, expected_pass) in variants.items():
    case = out / name
    case.mkdir()
    (case / "actual.inc").write_text(code, encoding="utf-8")
    (case / "gem-lifecycle-test.c").write_text(R10_TEST.read_text(encoding="utf-8"), encoding="utf-8")
    command = [
        os.environ.get("HOST_CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
        "-I" + str(case), str(case / "gem-lifecycle-test.c"), "-o", str(case / "test"),
    ]
    with (case / "build.log").open("w", encoding="utf-8") as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    ran_returncode = None
    if built.returncode == 0:
        with (case / "run.log").open("w", encoding="utf-8") as log:
            ran = subprocess.run([str(case / "test")], stdout=log, stderr=subprocess.STDOUT, check=False)
        ran_returncode = ran.returncode
        output = (case / "run.log").read_text(encoding="utf-8")
    else:
        output = (case / "build.log").read_text(encoding="utf-8")
    passed = expected_pass and built.returncode == 0 and ran_returncode == 0 and "GPU_GEM_LIFECYCLE=PASS" in output
    rejected = not expected_pass and (built.returncode != 0 or ran_returncode == -6 or "Assertion" in output)
    records.append({
        "name": name,
        "command": command,
        "build_exit_code": built.returncode,
        "run_exit_code": ran_returncode,
        "expected": "PASS" if expected_pass else "REJECT",
        "result": "PASS" if passed or rejected else "FAIL",
        "log": str(case / ("run.log" if built.returncode == 0 else "build.log")),
    })
    (out / "results.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    assert passed or rejected, (name, output[-1000:])

source_files = [
    GUEST / "drivers/gpu/drm/panthor/panthor_gem.c",
    GUEST / "drivers/gpu/drm/drm_gem.c",
    R10_TEST,
    Path(__file__),
]
record = {
    "status": "PASS_GEM_LIFECYCLE_MODEL",
    "results": records,
    "source_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Actual private and shared Panthor GEM publication functions with DRM handle/reference doubles; verifies initialization before publication, exact failure cleanup, post-success creation-reference drop, immediate handle close, and diagnostic lookup reference lifetime",
    "not_covered": "Real IDR allocation, DRM debugfs entry, Linux concurrency, GEM shrinker, DMA or GPU access",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print("GPU_GEM_LIFECYCLE=PASS actual Panthor publication functions; DRM doubles only")
