#!/usr/bin/env python3
"""Exercise interrupted internal-domain RETURN with the real RSI/core/backend.

The test adapter lowers only RETURN's scan budget to one entry and disables
its optional metadata shortcut, so a small fixture reaches the same bounded
continuation used by larger mappings. No completion or ownership check is
stubbed out. The production budget and metadata optimization are unchanged.
"""

import argparse
import json
import os
from pathlib import Path
import resource
import subprocess

from gpu_c_source import c_fragment_spans, replace_c_fragment

root = Path(__file__).resolve().parents[2]
rmm = root / "opencca/tf-rmm"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--out", type=Path, required=True)
p.add_argument(
    "--reference", type=Path, help="Old firmware core: must fail continuation"
)
a = p.parse_args()
out = a.out.resolve()
out.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
subprocess.run(
    [
        "python3",
        str(root / "scripts/check/check-gpu-domain-dispatch.py"),
        "--out",
        str(out),
        "--prepare-only",
    ],
    check=True,
)
core = (rmm / "runtime/core/opencca_gpu_private.c").read_text()
old = "unsigned int scan_budget = CACHE_SCAN_BATCH;"
assert len(c_fragment_spans(core, old)) == 1
core = replace_c_fragment(
    core,
    old,
    "extern bool test_return_slice;\n\tunsigned int scan_budget = for_cpu && test_return_slice ? 1U : CACHE_SCAN_BATCH;",
)
(out / "private.c").write_text(core)
test = (
    "#include <stdlib.h>\n"
    + (rmm / "runtime/tests/opencca_gpu_backend_test.c").read_text()
)
old = "static unsigned int domain_case;"
assert test.count(old) == 1
test = test.replace(old, old + "\nbool test_return_slice;")
old = "for (unsigned int phase = domain_dispatch_only ? 465U : 0U; phase < 551U; phase++) {"
assert test.count(old) == 1
test = test.replace(old, old + "\n\t\tif (phase != 466U && phase != 550U) continue;")
old = "\tdomain_old_token(owner, context, group, token);"
assert test.count(old) == 2
# The first occurrence is in task_domain_adversarial(), after a real DRAIN.
test = test.replace(
    old,
    old
    + """
    #undef gpu_firmware_task_stage_domain
    #undef gpu_firmware_task_cancel_staged
    struct gpu_private_ops sliced = donated_ops;
    unsigned int test_case = (unsigned int)strtoul(getenv("GPU_RETURN_CASE"), NULL, 10);
    unsigned int continuations = 0U;
    sliced.protected_mapping_summary = false;
    test_return_slice = true;
    gpu_firmware_context_yield(&fw_ops, &sliced, owner, context, &r);
    assert(r.status == GPU_PRIVATE_INCOMPLETE && words64(registers + at, 0U) == 0UL);
    gpu_firmware_group_inspect(&service, owner, group, &r);
    assert(r.status == GPU_PRIVATE_SUCCESS && r.value[0] == GPU_FIRMWARE_GROUP_QUIESCED);
    unsigned int retained_writes = writes;
    gpu_firmware_context_yield(&fw_ops, &sliced, &stranger, context, &r);
    assert(writes == retained_writes);
    gpu_firmware_task_finish(&fw_ops, &sliced, &service, owner, token, &r);
    assert(r.status == GPU_PRIVATE_INPUT && writes == retained_writes);
    gpu_firmware_group_destroy(&sliced, owner, group, &r);
    assert(r.status == GPU_PRIVATE_STATE);
    if (test_case == 3U) registers[at] = 0x1000U;
    for (unsigned int turn = 0U; turn < 1024U; turn++) {
        if (test_case == 1U)
            gpu_firmware_group_yield(&fw_ops, &sliced, owner, group, &r);
        else if (test_case == 2U) {
            stage_sync_pending = true;
            (gpu_firmware_task_stage_domain)(&fw_ops, &sliced, &service, owner,
                group, commands, 2U, 0UL, &r);
            stage_sync_pending = false;
        }
        else
            gpu_firmware_context_yield(&fw_ops, &sliced, owner, context, &r);
        if (test_case == 3U) {
            assert(r.status == GPU_PRIVATE_STATE);
            gpu_firmware_group_inspect(&service, owner, group, &r);
            assert(r.status == GPU_PRIVATE_SUCCESS && r.value[0] == GPU_FIRMWARE_GROUP_QUARANTINED);
            gpu_firmware_group_destroy(&sliced, owner, group, &r);
            assert(r.status == GPU_PRIVATE_STATE);
            destroy_prepared_bo(owner, prepared_bos[client], &r);
            assert(r.status == GPU_PRIVATE_STATE);
            break;
        }
        assert(r.status == GPU_PRIVATE_INCOMPLETE || r.status == GPU_PRIVATE_SUCCESS);
        continuations++;
        if (r.status == GPU_PRIVATE_SUCCESS) break;
    }
    if (test_case != 3U) {
        assert(r.status == GPU_PRIVATE_SUCCESS && continuations > 1U);
        if (test_case == 2U) {
            unsigned long successor = r.value[0];
            assert(successor != 0UL && successor != token);
            (gpu_firmware_task_cancel_staged)(&sliced, owner, successor, &r);
            assert(r.status == GPU_PRIVATE_SUCCESS);
        }
        gpu_firmware_group_inspect(&service, owner, group, &r);
        assert(r.status == GPU_PRIVATE_SUCCESS && r.value[0] == GPU_FIRMWARE_GROUP_RESERVED);
        assert(words64(registers + at, 0U) == 0UL);
    }
    test_return_slice = false;
    printf("GPU_DOMAIN_RETURN=PASS case=%u client=%u slices=%u MODEL_ONLY\\n",
        test_case, client, continuations);
    goto done;
    #define gpu_firmware_task_stage_domain domain_rsi_stage
    #define gpu_firmware_task_cancel_staged domain_rsi_cancel
""",
    1,
)
(out / "backend.c").write_text(test)
includes = [
    "runtime/tests",
    "runtime/tests/mmio-stubs",
    "runtime/include",
    "ext/mbedtls/include",
    "ext/mbedtls/library",
]
sources = [
    "plat/rk3588/src/rk3588_gpu.c",
    "runtime/core/opencca_gpu.c",
    "runtime/core/xshm_endpoint.c",
    "runtime/core/opencca_gpu_lease.c",
    "ext/mbedtls/library/sha256.c",
    "ext/mbedtls/library/platform_util.c",
]
variants = {"candidate": rmm / "runtime/core/opencca_gpu_firmware.c"}
if a.reference:
    variants["reference"] = a.reference.resolve()
records = []


def run(name, command, env=None):
    log = out / (name + ".log")
    with log.open("w") as stream:
        rc = subprocess.run(
            command, env=env, stdout=stream, stderr=subprocess.STDOUT
        ).returncode
    records.append(dict(name=name, command=command, exit_code=rc, log=str(log)))
    (out / "results.json").write_text(json.dumps(records, indent=2) + "\n")
    return rc, log.read_text()


for name, source in variants.items():
    command = [
        os.environ.get("HOST_CC", "cc"),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-pie",
        "-no-pie",
        "-DGPU_DOMAIN_RSI_TEST",
        "-I" + str(out),
    ]
    command += ["-I" + str(rmm / x) for x in includes] + [str(rmm / x) for x in sources]
    command += [
        str(out / "private.c"),
        str(out / "backend.c"),
        str(source),
        "-o",
        str(out / name),
    ]
    rc, _ = run(name + "-build", command)
    assert rc == 0
    for case in range(4):
        command = [
            str(out / name),
            str(root / "GPU-SFTP/panthor_fw/mali_csffw.bin"),
            "--domain-only",
        ]
        rc, text = run(
            name + "-" + str(case), command, dict(os.environ, GPU_RETURN_CASE=str(case))
        )
        if name == "candidate":
            assert rc == 0 and text.count("GPU_DOMAIN_RETURN=PASS") == 2, (name, case)
        else:
            assert rc == -6 and "Assertion" in text, (name, case)
        print("DOMAIN_RETURN", name, case, "PASS", flush=True)
