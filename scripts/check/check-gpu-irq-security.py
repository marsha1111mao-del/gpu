#!/usr/bin/env python3
"""Check actual Monitor/RMM event cores and bridge with explicit transport doubles."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess

from gpu_c_source import c_fragment_spans, replace_c_fragment

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
out = a.out.resolve()
out.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
producer = ROOT / "opencca/shared/opencca_gpu_irq_monitor.c"
consumer = ROOT / "opencca/shared/opencca_gpu_irq_consumer.c"
tests = ROOT / "GPU-SFTP/tests/gpu-irq-security"
records = []
mutations = {
    "ack-without-read": (producer, "ack > m->offered", "ack > m->stats.produced"),
    "complete-without-evidence": (
        consumer,
        "kind == OGI_CLAIM_COMPLETE && (!completed || !ogi_consumer_healthy(c, b))",
        "false && (!completed || !ogi_consumer_healthy(c, b))",
    ),
    "replay-consumed-event": (
        consumer,
        "memset(&c->records[i], 0, sizeof(c->records[i]));\n\t\t\tc->claimed++;",
        "c->claimed++;",
    ),
    "forge-simulation-source": (
        consumer,
        "((source == OGI_SOURCE_SIMULATION) != c->simulation) ||",
        "false ||",
    ),
    "overwrite-overflow": (
        producer,
        "count > OGI_CAPACITY - m->stats.queued ||\n\t    m->stats.produced > UINT64_MAX - count",
        "false",
    ),
}
for name in ["candidate", *mutations]:
    folder = out / name
    folder.mkdir()
    sources = {producer: producer.read_text(), consumer: consumer.read_text()}
    if name != "candidate":
        path, old, new = mutations[name]
        assert sources[path].count(old) == 1, name
        sources[path] = sources[path].replace(old, new, 1)
    inputs = []
    for path, text in sources.items():
        copy = folder / path.name
        copy.write_text(text)
        inputs.append(str(copy))
    command = [
        os.getenv("HOST_CC", "cc"),
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        "-I" + str(ROOT / "opencca/shared/include"),
        *inputs,
        str(tests / "irq-protocol-test.c"),
        "-o",
        str(folder / "test"),
    ]
    with (folder / "build.log").open("w") as log:
        build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert build.returncode == 0, name
    with (folder / "run.log").open("w") as log:
        run = subprocess.run(
            [str(folder / "test")], stdout=log, stderr=subprocess.STDOUT
        )
    text = (folder / "run.log").read_text()
    if name == "candidate":
        assert run.returncode == 0 and "GPU_IRQ_PROTOCOL=PASS" in text
    else:
        assert (
            run.returncode == -6
            and "Assertion" in text
            and "ERROR: AddressSanitizer" not in text
        ), name
    records.append(
        {
            "name": name,
            "command": command,
            "build_exit": build.returncode,
            "run_exit": run.returncode,
        }
    )
    print(name, "PASS", flush=True)
command = [
    os.getenv("HOST_CC", "cc"),
    "-std=c11",
    "-O2",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-g",
    "-fsanitize=address,undefined",
    "-fno-omit-frame-pointer",
    "-fno-pie",
    "-no-pie",
    "-I" + str(tests / "stubs"),
    "-I" + str(ROOT / "opencca/shared/include"),
    "-I" + str(ROOT / "opencca/tf-rmm/runtime/include"),
    str(producer),
    str(consumer),
    str(ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu_irq.c"),
    str(tests / "irq-adapter-test.c"),
    "-o",
    str(out / "adapter"),
]
with (out / "adapter-build.log").open("w") as log:
    build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
assert build.returncode == 0
with (out / "adapter-run.log").open("w") as log:
    run = subprocess.run([str(out / "adapter")], stdout=log, stderr=subprocess.STDOUT)
assert (
    run.returncode == 0
    and "GPU_IRQ_ADAPTER=PASS" in (out / "adapter-run.log").read_text()
)
records.append(
    {
        "name": "adapter",
        "command": command,
        "build_exit": build.returncode,
        "run_exit": run.returncode,
    }
)

firmware = ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu_firmware.c"
original = firmware.read_text()
fresh = "\t\ttask_observe(ops, memory_ops, service, owner, token, true, false, NULL, &checked);"
assert len(c_fragment_spans(original, fresh)) == 1
begin = c_fragment_spans(
    original,
    "ops->irq->next(group->hardware_csg, group->irq_epoch, task->irq_floor, &checked);",
)[0][0]
end = original.index("\t\t/* An event reference", begin)
fw_variants = {
    "firmware-gate": original,
    "skip-fresh-claim-evidence": replace_c_fragment(
        original, fresh, "(void)memory_ops; checked.status = GPU_PRIVATE_SUCCESS;"
    ),
    "skip-reference-before-mmio": original[:begin] + original[end:],
}
for name, source in fw_variants.items():
    folder = out / name
    folder.mkdir()
    (folder / "firmware.c").write_text(source)
    command = [
        os.getenv("HOST_CC", "cc"),
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        "-I" + str(folder),
        "-I" + str(ROOT / "opencca/shared/include"),
        "-I" + str(ROOT / "opencca/tf-rmm/runtime/include"),
        "-I" + str(ROOT / "opencca/tf-rmm/runtime/tests/mmio-stubs"),
        str(consumer),
        str(ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu_private.c"),
        str(ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu_lease.c"),
        str(ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu.c"),
        str(tests / "irq-firmware-gate-test.c"),
        "-o",
        str(folder / "test"),
    ]
    with (folder / "build.log").open("w") as log:
        build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert build.returncode == 0, (name, "build")
    with (folder / "run.log").open("w") as log:
        run = subprocess.run(
            [str(folder / "test")], stdout=log, stderr=subprocess.STDOUT
        )
    text = (folder / "run.log").read_text()
    if name == "firmware-gate":
        assert run.returncode == 0 and "GPU_IRQ_FW_GATE=PASS" in text
    else:
        assert (
            run.returncode == -6
            and "Assertion" in text
            and "ERROR: AddressSanitizer" not in text
        ), name
    records.append(
        {
            "name": name,
            "command": command,
            "build_exit": build.returncode,
            "run_exit": run.returncode,
        }
    )
    print(name, "PASS", flush=True)
paths = [
    producer,
    consumer,
    ROOT / "opencca/tf-rmm/runtime/core/opencca_gpu_irq.c",
    Path(__file__),
    firmware,
    ROOT / "opencca/tf-rmm/runtime/include/opencca_gpu_firmware.h",
    *list((ROOT / "opencca/shared/include").glob("*.h")),
    *list(tests.rglob("*.[ch]")),
]
(out / "results.json").write_text(json.dumps(records, indent=2) + "\n")
(out / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS_IRQ_SECURITY_MODELS",
            "compiled_mutants_rejected": len(mutations) + 2,
            "source_sha256": {
                str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in paths
            },
            "scope": "Actual Monitor producer, RMM consumer and mailbox bridge; architecture/cache/SMC/GIC/physical IRQ delivery are doubles. Not a board or physical-isolation result.",
        },
        indent=2,
    )
    + "\n"
)
print("GPU_IRQ_SECURITY_MODELS=PASS mutants=" + str(len(mutations) + 2), flush=True)
