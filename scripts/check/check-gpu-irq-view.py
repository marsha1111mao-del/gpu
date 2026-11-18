#!/usr/bin/env python3
"""Check actual IRQ view code with independent noncoherent Root/RMM cache models."""

from pathlib import Path
import hashlib
import json
import resource
import subprocess

import argparse
import os

from gpu_c_source import c_fragment_spans, replace_c_fragment

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
OUT = a.out.resolve()
OUT.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
fixtures = ROOT / "GPU-SFTP/tests/gpu-irq-security"
platform = (fixtures / "irq-view-platform.h").read_text()
test = (fixtures / "irq-view-test.c").read_text()
stubs = OUT / "stubs"
for n in [
    "arch_helpers.h",
    "bl31/interrupt_mgmt.h",
    "common/debug.h",
    "drivers/arm/gicv3.h",
    "lib/mmio.h",
    "lib/spinlock.h",
    "plat/common/platform.h",
    "platform_def.h",
    "services/rmm_core_manifest.h",
    "debug.h",
    "rmm_el3_ifc.h",
    "smc.h",
]:
    p = stubs / n
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("/* declarations supplied by platform.h */\n")
includes = OUT / "include"
includes.mkdir()
for p in (ROOT / "opencca/shared/include").glob("*.h"):
    (includes / p.name).write_bytes(p.read_bytes())
header = ROOT / "opencca/tf-rmm/runtime/include/opencca_gpu_irq.h"
(includes / header.name).write_bytes(header.read_bytes())
rootrel = "opencca/trusted-firmware-a/plat/rockchip/rk3588/opencca/rk3588_gpu_irq.c"
rmmrel = "opencca/tf-rmm/runtime/core/opencca_gpu_irq.c"
platrel = "opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c"
root = (ROOT / rootrel).read_text()
rmm = (ROOT / rmmrel).read_text()
plat = (ROOT / platrel).read_text()
start = plat.index("bool plat_opencca_gpu_irq_idle(")
end = plat.index("\nstatic void reg_write(", start)
idle = plat[start:end]
definitions = "\n".join(
    line
    for line in plat.splitlines()
    if line.startswith("#define ")
    and line.split()[1]
    in [
        "GPU_INT_RAWSTAT",
        "JOB_INT_RAWSTAT",
        "MMU_INT_RAWSTAT",
        "MMU_FAULT_MASK",
        "GPU_INT_MASK",
        "JOB_INT_MASK",
        "MMU_INT_MASK",
    ]
)
idle = (
    definitions
    + "\nstatic uint32_t reg_read(unsigned long offset){return mmio_read_32(0xfb000000UL+offset);}\n"
    + idle
)
candidate_getters = """
uintptr_t c3_test_view_address(void){return (uintptr_t)&fast_view;}
bool c3_test_fast_empty(void){return fast_empty();}
unsigned int c3_test_register_address(uintptr_t address){mailbox.view_pa=address;return invoke(OGI_VIEW_REGISTER);}
"""
variants = {"candidate": (root, rmm, True, True, list(range(48)))}
mutations = [
    (
        "skip-second-sequence",
        "rmm",
        "if (after != before || (after & 1U) != 0U)",
        "if (((void)after, false))",
        [12],
    ),
    ("skip-queued-guard", "rmm", "snapshot.stats.queued != 0U ||", "false ||", [21]),
    (
        "skip-device-epoch",
        "rmm",
        "snapshot.stats.device_epoch != consumer.device_epoch ||",
        "false ||",
        [25],
    ),
    (
        "omit-odd-publication",
        "root",
        "__atomic_store_n(&published_view->sequence, published_sequence, __ATOMIC_RELEASE);",
        "(void)published_sequence;",
        [10],
    ),
    (
        "omit-payload-clean",
        "root",
        "flush_dcache_range((uintptr_t)published_view + sizeof(uint64_t),\n\t\tsizeof(*published_view) - sizeof(uint64_t));",
        "(void)published_view;",
        [0],
    ),
    (
        "allow-view-wrap",
        "root",
        "if (published_sequence > UINT64_MAX - 2U) {",
        "if (false) {",
        [15],
    ),
    (
        "ignore-current-raw",
        "idle",
        "(gpu | job | mmu) == 0U",
        "((void)gpu, (void)job, (void)mmu, true)",
        [10],
    ),
    (
        "ignore-current-masks",
        "idle",
        "gpu_mask == expected_gpu &&\n\t\tjob_mask == expected_job && mmu_mask == expected_mmu",
        "((void)gpu_mask, (void)job_mask, (void)mmu_mask, (void)expected_gpu, (void)expected_job, (void)expected_mmu, true)",
        [8],
    ),
    (
        "skip-approved-mask-valid",
        "rmm",
        "snapshot.masks_valid != 1U || snapshot.masks[0] != 3U",
        "false",
        [33],
    ),
    (
        "skip-required-mask-sources",
        "rmm",
        "(snapshot.masks[1] & required_job) != required_job ||\n\t    (snapshot.masks[2] & required_mmu) != required_mmu ||",
        "((void)required_job, (void)required_mmu, false) ||",
        [35],
    ),
    (
        "ignore-MCU-AS0-fault",
        "idle",
        "reg_read(MMU_INT_RAWSTAT) & MMU_FAULT_MASK",
        "reg_read(MMU_INT_RAWSTAT) & 0xfffeU",
        [39],
    ),
    (
        "ignore-high-AS-fault",
        "idle",
        "reg_read(MMU_INT_RAWSTAT) & MMU_FAULT_MASK",
        "reg_read(MMU_INT_RAWSTAT) & 0xffU",
        [40],
    ),
    (
        "ignore-global-job-event",
        "idle",
        "uint32_t job = reg_read(JOB_INT_RAWSTAT);",
        "uint32_t job = reg_read(JOB_INT_RAWSTAT) & 0x7fffffffU;",
        [42],
    ),
    (
        "accept-extra-mask-sources",
        "idle",
        "gpu_mask == expected_gpu &&\n\t\tjob_mask == expected_job && mmu_mask == expected_mmu",
        "(gpu_mask & expected_gpu) == expected_gpu &&\n\t\t(job_mask & expected_job) == expected_job && (mmu_mask & expected_mmu) == expected_mmu",
        [44],
    ),
]
for name, where, oldvalue, newvalue, scenarios in mutations:
    selected = {"root": root, "rmm": rmm, "idle": idle}[where]
    if name == "omit-odd-publication":
        # Only the beginning stamp, never the final even commit.
        start = selected.index("static void view_begin(")
        end = selected.index("static void view_end(", start)
        body = selected[start:end]
        assert len(c_fragment_spans(body, oldvalue)) == 1
        selected = (
            selected[:start]
            + replace_c_fragment(body, oldvalue, newvalue, 1)
            + selected[end:]
        )
    else:
        selected = replace_c_fragment(selected, oldvalue, newvalue, 1)
    variants[name] = (
        selected if where == "root" else root,
        selected if where == "rmm" else rmm,
        True,
        True,
        scenarios,
    )
    if where == "idle":
        variants[name] += (selected,)
results = []
semantics = {}
for name, entry in variants.items():
    el3, adapter, has_view, expected, scenarios = entry[:5]
    out = OUT / name
    out.mkdir()
    (out / "platform.h").write_text(platform)
    (out / "test.c").write_text(test)
    (out / "el3.c").write_text(el3)
    (out / "rmm.c").write_text(adapter + candidate_getters)
    (out / "idle-platform.inc").write_text(entry[5] if len(entry) > 5 else idle)
    command = [
        os.getenv("HOST_CC", "cc"),
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Wshadow",
        "-Werror",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        "-DC3_HAS_VIEW=" + str(int(has_view)),
        "-DC3_EXPECT_FAST=" + str(int(expected)),
        "-include",
        str(out / "platform.h"),
        "-I" + str(includes),
        "-I" + str(stubs),
        "-I" + str(ROOT / "opencca/tf-rmm/runtime/include"),
        '-DEL3_SOURCE="' + str(out / "el3.c") + '"',
        str(out / "rmm.c"),
        str(out / "test.c"),
        str(ROOT / "opencca/shared/opencca_gpu_irq_monitor.c"),
        str(ROOT / "opencca/shared/opencca_gpu_irq_consumer.c"),
        "-o",
        str(out / "test"),
    ]
    built = subprocess.run(command, capture_output=True, text=True)
    (out / "build.log").write_text(built.stdout + built.stderr)
    assert built.returncode == 0, (name, built.stderr)
    for scenario in scenarios:
        run = subprocess.run(
            [str(out / "test"), str(scenario)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        (out / (str(scenario) + ".log")).write_text(run.stdout + run.stderr)
        assert (
            "ERROR: AddressSanitizer" not in run.stderr
            and "runtime error:" not in run.stderr
        ), (name, scenario)
        if name in ["reference", "candidate"]:
            assert run.returncode == 0, (name, scenario, run.stderr)
            semantics[name, scenario] = next(
                line
                for line in run.stdout.splitlines()
                if line.startswith(("MAILBOX_SEMANTICS=", "C3_BOUNDARY="))
            )
        else:
            assert run.returncode == -6 and "Assertion" in run.stderr, (
                name,
                scenario,
                run.returncode,
            )
        results.append(
            {
                "name": name,
                "scenario": scenario,
                "command": command,
                "build_exit": built.returncode,
                "run_exit": run.returncode,
            }
        )
    print(name, "PASS", flush=True)
(OUT / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS_ACTUAL_IRQ_VIEW_MODELS",
            "source_sha256": {
                str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in [
                    ROOT / rootrel,
                    ROOT / rmmrel,
                    ROOT / platrel,
                    header,
                    Path(__file__),
                    *fixtures.glob("irq-view-*.[ch]"),
                    *list((ROOT / "opencca/shared/include").glob("*.h")),
                    ROOT / "opencca/shared/opencca_gpu_irq_monitor.c",
                    ROOT / "opencca/shared/opencca_gpu_irq_consumer.c",
                ]
            },
            "candidate_scenarios": 48,
            "compiled_mutants_rejected": len(mutations),
            "records": results,
            "scope": "Actual Root adapter/RMM bridge/cores and extracted actual fixed RK hardware helper. Mailbox and protected128Bview have independent per-world caches and PoC; MMIO/GIC/CPU/physical IRQ are models.  all raw/mask/fault/view-generation/queue/quiet/bounds/overflow/fallback contracts asserted. Not board performance or full physical isolation.",
        },
        indent=2,
    )
    + "\n"
)
