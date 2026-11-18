#!/usr/bin/env python3
"""Exercise actual group bridge functions with host-side kernel/RSI doubles.

This checks branch/lifetime behavior, not Realm execution, Linux concurrency,
actual RMM authorization or hardware enforcement (covered separately).
"""
from pathlib import Path
import argparse, hashlib, json
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
guest = root / 'Linux-Guest-GPU'


def function(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*\(', source)
    assert match, name
    start = source.rfind('\n', 0, match.start()) + 1
    if source[start:match.start()].strip() == '':
        start = source.rfind('\n', 0, start - 1) + 1
    end = source.index('\n}', match.end()) + 2
    text = source[start:end]
    assert '{' in text and ';' not in text[:text.index('{')], name
    return text + '\n'


def structure(source, name):
    match = re.search(r'^struct ' + re.escape(name) + r' \{', source, re.M)
    assert match, name
    return source[match.start():source.index('\n};', match.end()) + 3] + '\n'


kernel = (guest / 'drivers/char/realm_gpu.c').read_text()
proxy = (guest / 'drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c').read_text()
wire = (guest / 'include/linux/panthor_vmshm.h').read_text()
test_source = root / 'GPU-SFTP/tests/gpu-group-bridge/group-bridge-test.c'
parts = [structure(wire, n) for n in ('panthor_vmshm_vm_bind_op', 'panthor_vmshm_vm_sync_req')]
parts += [structure(kernel, n) for n in ('realm_gpu_context', 'realm_gpu_group')]
parts += [structure(proxy, n) for n in ('panthor_proxy_vm', 'panthor_proxy_group')]
parts += [structure(wire, n) for n in ('panthor_vmshm_group_create_req', 'panthor_vmshm_group_create_rsp')]
(out / 'actual-structures.inc').write_text('\n'.join(parts))
parts = [function(kernel, n) for n in ('private_status', 'managed_context', 'managed_group', 'reap_groups', 'reap_contexts', 'realm_gpu_group_create', 'realm_gpu_group_handle', 'realm_gpu_group_configure', 'realm_gpu_group_put', 'realm_gpu_context_put')]
parts += [function(proxy, n) for n in ('panthor_proxy_session_group_create', 'panthor_proxy_session_group_destroy')]
(out / 'actual-functions.inc').write_text('\n'.join(parts))
cc = os.environ.get('HOST_CC', 'cc')
build = [cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-g', '-fsanitize=address,undefined',
         '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', '-D__user=', '-I' + str(out),
         '-iquote', str(guest / 'include/uapi'), str(test_source), '-o', str(out / 'group-bridge-test')]
with (out / 'build.log').open('w', encoding='utf-8') as log:
    built = subprocess.run(build, stdout=log, stderr=subprocess.STDOUT, check=False)
with (out / 'run.log').open('w', encoding='utf-8') as log:
    executed = subprocess.run([str(out / 'group-bridge-test')], stdout=log, stderr=subprocess.STDOUT, check=False)
output = (out / 'run.log').read_text(encoding='utf-8')
required = {'GPU_GROUP_BRIDGE=PASS'}
output_markers = {line.split(' ', 1)[0] for line in output.splitlines() if line}
passed = built.returncode == 0 and executed.returncode == 0 and required <= output_markers
source_files = [guest / 'drivers/char/realm_gpu.c', guest / 'drivers/gpu/drm/panthor-proxy/panthor_proxy_drv.c',
                guest / 'include/linux/panthor_vmshm.h', test_source, Path(__file__)]
record = {
    'status': 'PASS_GROUP_BRIDGE_MODEL' if passed else 'FAIL',
    'build_exit_code': built.returncode,
    'run_exit_code': executed.returncode,
    'observed_markers': sorted(required & output_markers),
    'source_sha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files},
    'scope': 'Actual Guest group bridge and Proxy reservation policy with host doubles; high group priority is denied before RMM validation and nonzero queue priority is rejected by the exact RMM validator',
    'not_covered': 'Real RMM scheduling fairness, actual RSI authorization, Linux concurrency, firmware queues, and GPU execution',
    'hardware_tests': 'NOT_RUN',
}
(out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
assert passed, output
print(output, end='')
