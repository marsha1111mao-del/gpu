"""Actual control core donation/destroy with tracked persistent-view callbacks."""

from pathlib import Path
import argparse
import hashlib
import json
import resource
import subprocess

from gpu_c_source import replace_c_fragment

B = Path(__file__).resolve().parents[2]
R = B
S = B / "opencca/tf-rmm"
p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
O = a.out.resolve()
O.mkdir(exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def replace_fixture_once(source, old, new):
    assert source.count(old) == 1, old[:80]
    return source.replace(old, new, 1)


core = (S / "runtime/core/opencca_gpu_private.c").read_text()
core += """\n/* Test-only visibility of the private lifecycle journal. */
unsigned int c7_test_hidden(const void *owner,unsigned long handle) {
 struct private_bo *bo=bo_lookup(owner,handle);return bo?bo->hidden:~0U;
}\n"""
fixture = (R / "opencca/tf-rmm/runtime/tests/opencca_gpu_control_test.c").read_text()
fixture = replace_fixture_once(
    fixture,
    "static unsigned int hides, restores, clears;",
    """static unsigned int hides, restores, clears;
static unsigned long view_handle[TEST_PAGES];
static bool tlb_valid[2][TEST_PAGES];
static unsigned int pins,unpins,fail_pin=UINT_MAX,fail_unpin=UINT_MAX;
static bool fail_pin_after;
extern unsigned int c7_test_hidden(const void *,unsigned long);
""",
)
fixture = replace_fixture_once(
    fixture,
    "\tfor (unsigned int j = 0U; j < PAGE; j++)\n",
    """\tassert(!view_handle[index] && !tlb_valid[0][index] && !tlb_valid[1][index]);
\tfor (unsigned int j = 0U; j < PAGE; j++)
""",
)
callbacks = """static bool pin_view(const void *owner,unsigned long handle,unsigned int index,unsigned long pa)
{
 unsigned int page=page_index(pa);assert(owner==&service && index==page);
 assert(!cpu_visible[page] && !view_handle[page]);
 assert(c7_test_hidden(owner,handle)==index+1U); /* Journal precedes exposure. */
 if(page==fail_pin && !fail_pin_after)return false;
 view_handle[page]=handle;tlb_valid[0][page]=tlb_valid[1][page]=true;pins++;
 return page!=fail_pin;
}
static bool unpin_view(const void *owner,unsigned long handle,unsigned int index,unsigned long pa)
{
 unsigned int page=page_index(pa);assert(owner==&service && index==page && !cpu_visible[page]);
 assert(!view_handle[page] || view_handle[page]==handle);
 if(page==fail_unpin)return false;
 view_handle[page]=0;tlb_valid[0][page]=tlb_valid[1][page]=false;unpins++;
 return true;
}
"""
fixture = replace_fixture_once(
    fixture,
    "static const struct gpu_private_ops ops = {",
    callbacks + "\nstatic struct gpu_private_ops ops = {",
)
fixture = replace_fixture_once(
    fixture,
    ".hide_page = hide, .restore_page = restore, .clear_page = clear",
    ".hide_page = hide, .restore_page = restore, .clear_page = clear,\n .pin_control_page=pin_view,.unpin_control_page=unpin_view",
)
fixture = replace_fixture_once(
    fixture,
    "\thides = restores = clears = 0U;",
    """\tfor(unsigned int i=0;i<TEST_PAGES;i++)assert(!view_handle[i]);
\tpins=unpins=0;fail_pin=fail_unpin=UINT_MAX;fail_pin_after=false;
\thides = restores = clears = 0U;""",
)
fixture = replace_fixture_once(
    fixture,
    "assert(result.status == GPU_PRIVATE_SUCCESS && hides == TEST_PAGES);",
    "assert(result.status == GPU_PRIVATE_SUCCESS && hides == TEST_PAGES && pins == TEST_PAGES);",
)
fixture = replace_fixture_once(
    fixture,
    "for (unsigned int fault = 0U; fault < 2U; fault++) {",
    "for (unsigned int fault = 0U; fault < 4U; fault++) {",
)
fixture = replace_fixture_once(
    fixture,
    "\t\tfail_clear = fault == 1U ? 3U : UINT_MAX;",
    "\t\tfail_clear = fault == 1U ? 3U : UINT_MAX;\n\t\tfail_pin = fault >= 2U ? 3U : UINT_MAX;\n\t\tfail_pin_after = fault == 3U;",
)
fixture = replace_fixture_once(
    fixture,
    "\t\tfail_restore = UINT_MAX;\n\t\tdestroy(object);",
    """\t\tfail_restore = UINT_MAX;
\t\tfail_unpin = 1U;
\t\tgpu_private_control_destroy(&ops,&service,object,&result);
\t\tassert(result.status==GPU_PRIVATE_STATE && !cpu_visible[1] && view_handle[1]==object);
\t\tassert(gpu_private_owner_busy(&service));
\t\tfail_unpin=UINT_MAX;
\t\tdestroy(object);""",
)
extra = """
    reset_data();object=create(1U);
    ops.unpin_control_page=NULL;
    gpu_private_control_append(&ops,&service,object,0,ipas,1,&result);
    assert(result.status==GPU_PRIVATE_INPUT && !hides && !pins);
    ops.unpin_control_page=unpin_view;destroy(object);
    puts("C7_CORE=PASS 513-pages, pre/post-pin failure journal, unpin failure keeps refs/CPU hidden, generation reuse, unchanged quotas");
"""
fixture = replace_fixture_once(
    fixture,
    '\tputs("GPU_CONTROL_MEMORY=PASS',
    extra + '\n\tputs("GPU_CONTROL_MEMORY=PASS',
)
variants = {
    "candidate": core,
    "skip-pin": replace_c_fragment(
        core, "!ops->pin_control_page(owner, handle, bo->hidden - 1U, pa)", "false"
    ),
    "skip-unpin": replace_c_fragment(
        core,
        "!ops->unpin_control_page(owner, handle, bo->registered - 1U, pa)",
        "false",
    ),
    "ignore-unpin-failure": replace_c_fragment(
        core,
        "!ops->unpin_control_page(owner, handle, bo->registered - 1U, pa)",
        "(!ops->unpin_control_page(owner, handle, bo->registered - 1U, pa) && false)",
    ),
}
records = []
for name, source in variants.items():
    d = O / name
    d.mkdir()
    (d / "core.c").write_text(source)
    (d / "test.c").write_text(fixture)
    cmd = [
        "cc",
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
        "-I" + str(S / "runtime/include"),
        str(d / "core.c"),
        str(d / "test.c"),
        "-o",
        str(d / "test"),
    ]
    build = subprocess.run(cmd, capture_output=True, text=True)
    (d / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, (name, build.stderr)
    run = subprocess.run([str(d / "test")], capture_output=True, text=True, timeout=60)
    (d / "run.log").write_text(run.stdout + run.stderr)
    assert (
        "ERROR: AddressSanitizer" not in run.stderr
        and "runtime error:" not in run.stderr
    )
    if name == "candidate":
        assert run.returncode == 0 and "C7_CORE=PASS" in run.stdout, (name, run.stderr)
    else:
        assert run.returncode == -6 and "Assertion" in run.stderr, (
            name,
            run.returncode,
        )
    records.append(
        {
            "name": name,
            "command": cmd,
            "build_exit": build.returncode,
            "run_exit": run.returncode,
        }
    )
    (O / "commands.json").write_text(json.dumps(records, indent=2) + "\n")
    print(name, "PASS", flush=True)
(O / "summary.json").write_text(
    json.dumps(
        {
            "status": "PASS_C7_ACTUAL_CORE_CONTROL_LIFECYCLE",
            "compiled_mutants_rejected": 3,
            "core_sha256": hashlib.sha256(
                (S / "runtime/core/opencca_gpu_private.c").read_bytes()
            ).hexdigest(),
            "scope": "Real memory-core donation/hold/reset/destroy+quota paths; pin/unpin/RTT/physical GPU/CPU/TLB are explicit models.",
        },
        indent=2,
    )
    + "\n"
)
