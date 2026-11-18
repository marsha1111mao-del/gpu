#!/usr/bin/env python3
"""Exercise actual task owner/RPC source with kernel, transport and RSI doubles.

Checks ownership, copied input, typed replies and retention. It does not run
Linux concurrency, real RSI, device firmware or DRM dependency scheduling.
"""

from pathlib import Path
import argparse, hashlib, json, os
import re
import subprocess

from gpu_c_source import extract_c_function

root = Path(__file__).resolve().parents[2]
guest = root / "Linux-Guest-GPU"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--out", type=Path, default=root / "build/rmm-client-bo-20261030/task-bridge-unit"
)
out = parser.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=True)


def function(source, name):
    return extract_c_function(source, name)


def structure(source, name):
    match = re.search(r"^struct " + re.escape(name) + r" \{", source, re.M)
    assert match, name
    return source[match.start() : source.index("\n};", match.end()) + 3] + "\n"


kernel = (guest / "drivers/char/realm_gpu.c").read_text()
proxy = (guest / "drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c").read_text()
wire = (guest / "include/linux/panthor_vmshm.h").read_text()
test_source = root / "GPU-SFTP/tests/gpu-task-bridge/task-test.c"
parts = [
    structure(wire, name)
    for name in (
        "panthor_vmshm_vm_bind_op",
        "panthor_vmshm_vm_sync_req",
        "panthor_vmshm_vm_sync_rsp",
    )
]
# Extracted kernel functions call kernel-only logging helpers. The model
# harness checks state transitions, not console formatting.
parts += ["#define pr_info(...) do { } while (0)\n"]
parts += [
    structure(kernel, name)
    for name in ("realm_gpu_context", "realm_gpu_group", "realm_gpu_task")
]
parts += [
    structure(proxy, name)
    for name in ("panthor_proxy_group", "panthor_proxy_vm", "panthor_proxy_bo")
]
parts += [
    structure(wire, name)
    for name in ("panthor_vmshm_rmm_task_req", "panthor_vmshm_rmm_task_rsp")
]
# Keep request types/actions and the feature bit sourced from the real header.
parts += [
    line
    for line in wire.splitlines()
    if line.startswith("#define PANTHOR_VMSHM_")
    and ("RMM_TASK" in line or "MAX_GROUP_QUEUES" in line)
]
(out / "structures.inc").write_text("\n".join(parts))
parts = [
    function(kernel, name)
    for name in (
        "private_status",
        "managed_group",
        "managed_task",
        "reap_tasks",
        "realm_gpu_task_stage",
        "realm_gpu_task_handle",
        "realm_gpu_task_mapping_version",
        "realm_gpu_task_cancel_unprepared",
        "realm_gpu_private_call",
        "task_call",
        "realm_gpu_task_call",
        "realm_gpu_task_publish",
        "realm_gpu_task_put",
        "realm_gpu_ioctl",
    )
]
parts += [
    function(proxy, name)
    for name in (
        "panthor_proxy_rmm_task_control_available",
        "panthor_proxy_session_vm_sync",
        "panthor_proxy_session_rmm_task",
        "panthor_proxy_handle_rmm_task",
    )
]
(out / "actual.inc").write_text("\n".join(parts))
build = [
    os.environ.get("HOST_CC", "cc"),
    "-std=gnu11",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wno-unused-parameter",
    "-g",
    "-fsanitize=address,undefined",
    "-ftrivial-auto-var-init=pattern",
    "-fno-omit-frame-pointer",
    "-fno-pie",
    "-no-pie",
    "-D__user=",
    "-I" + str(out),
    "-iquote",
    str(guest / "include/uapi"),
    str(test_source),
    "-o",
    str(out / "task-test"),
]
with (out / "build.log").open("w", encoding="utf-8") as log:
    built = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT, check=False)
with (out / "run.log").open("w", encoding="utf-8") as log:
    executed = subprocess.run(
        [str(out / "task-test")], stdout=log, stderr=subprocess.STDOUT, check=False
    )
output = (out / "run.log").read_text(encoding="utf-8")
required = {"GPU_TASK_BRIDGE=PASS"}
output_markers = {line.split(" ", 1)[0] for line in output.splitlines() if line}
passed = (
    built.returncode == 0 and executed.returncode == 0 and required <= output_markers
)
handler_names = re.findall(r"\.handler = (panthor_proxy_handle_\w+)", proxy)
assert len(handler_names) == len(set(handler_names)) and handler_names
for handler_name in handler_names:
    declaration = re.search(r"\b" + re.escape(handler_name) + r"\s*\(", proxy)
    assert declaration, handler_name
    brace = proxy.index("{", declaration.end())
    depth = 0
    for index in range(brace, len(proxy)):
        depth += proxy[index] == "{"
        depth -= proxy[index] == "}"
        if depth == 0:
            body = proxy[declaration.start() : index + 1]
            break
    else:
        raise AssertionError(handler_name)
    response_types = re.findall(r"struct (panthor_vmshm_\w+) rsp", body)
    assert len(response_types) == 1, (handler_name, response_types)
    assert re.search(
        r"struct panthor_vmshm_\w+ rsp = \{ 0 \};|memset\(&rsp, 0, sizeof\(rsp\)\);",
        body,
    ), handler_name
    send = re.search(r"panthor_proxy_send_rsp\([^\;]+sizeof\(rsp\)", body, re.S)
    assert send, handler_name
    response_match = re.search(
        r"^struct " + response_types[0] + r" \{(.*?)^\};", wire, re.M | re.S
    )
    assert response_match and not re.search(r"\*\s*[^;]+;", response_match.group(1)), (
        response_types[0]
    )
source_files = [
    guest / "drivers/char/realm_gpu.c",
    guest / "drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c",
    guest / "include/linux/panthor_vmshm.h",
    test_source,
    Path(__file__),
]
record = {
    "status": "PASS_TASK_BRIDGE_MODEL" if passed else "FAIL",
    "build_exit_code": built.returncode,
    "run_exit_code": executed.returncode,
    "observed_markers": sorted(required & output_markers),
    "source_sha256": {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    },
    "scope": "Actual kernel token lifecycle and Proxy RPC session/channel/version binding; every Proxy handler response is whole-zero initialized and sent at typed size, while pattern-initialized RMM_TASK replies are checked byte-for-byte across error/success paths",
    "not_covered": "Proxy disconnect/session recreation transport, Linux concurrency, real RSI, firmware, DRM scheduling, GPU execution, and DEV_QUERY query-data semantics",
    "hardware_tests": "NOT_RUN",
}
(out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
assert passed, output
print(output, end="")
