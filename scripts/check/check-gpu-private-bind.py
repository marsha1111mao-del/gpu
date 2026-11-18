#!/usr/bin/env python3
"""Run actual private VM_BIND driver functions with host kernel/DRM/RPC doubles.

Tests control flow, input ownership, fences and failure cleanup. This does not
prove Linux concurrency, actual RSI, native Panthor service or GPU execution.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess
root = Path(__file__).resolve().parents[2]
guest = root/'Linux-Guest-GPU'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=root/'build/rmm-client-bo-20261030/private-bind-unit')
out = parser.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=True)
source = (guest/'drivers/gpu/drm/panthor-client/panthor_client_drv.c').read_text()
wire = (guest/'include/linux/panthor_vmshm.h').read_text()
test_source = root/'GPU-SFTP/tests/gpu-private-bind/bind-test.c'
def function(name):
    match = re.search(r'\b'+re.escape(name)+r'\s*\(', source)
    assert match, name
    start = source.rfind('\n', 0, match.start())+1
    if not source[start:match.start()].strip():
        start = source.rfind('\n', 0, start-1)+1
    end = source.index('\n}', match.end())+2
    return source[start:end]+'\n'
def structure(name):
    match = re.search(r'^struct '+name+r' \{', wire, re.M)
    assert match, name
    return wire[match.start():wire.index('\n};', match.end())+3]+'\n'
(out/'wire.inc').write_text('\n'.join(structure(n) for n in (
    'panthor_vmshm_vm_bind_op','panthor_vmshm_vm_sync_req','panthor_vmshm_vm_sync_rsp')))
vmtypes = []
for name in ('panthor_client_mapping', 'panthor_client_vm'):
    match = re.search(r'^struct '+name+r' \{', source, re.M)
    assert match
    vmtypes.append(source[match.start():source.index('\n};', match.end())+3])
(out/'vmtypes.inc').write_text('\n'.join(vmtypes))
start = source.index('#define PANTHOR_CLIENT_PRIVATE_BATCH_LIMIT')
end = source.index('/* Private GROUP_SUBMIT:', start)
vmput = source.index('static void panthor_client_vm_put(struct panthor_client_vm *vm)\n{')
parts = [source[vmput:source.index('\n}', vmput)+2], function('panthor_client_check_group_submit_sync_op'),function('panthor_client_copy_vm_bind_ops'),source[start:end]]
(out/'actual.inc').write_text('\n'.join(parts))
build = [os.environ.get('HOST_CC','cc'),'-std=gnu11','-Wall','-Wextra','-Werror',
    '-Wno-unused-parameter','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
    '-D__user=','-I'+str(out),'-iquote',str(guest/'include/uapi'),
    str(test_source),'-o',str(out/'bind-test')]
with (out/'build.log').open('w',encoding='utf-8') as log:
    built = subprocess.run(build,stdout=log,stderr=subprocess.STDOUT,check=False)
with (out/'run.log').open('w',encoding='utf-8') as log:
    executed = subprocess.run([str(out/'bind-test')],stdout=log,stderr=subprocess.STDOUT,check=False)
output = (out/'run.log').read_text(encoding='utf-8')
required = {'GPU_PRIVATE_BIND_BRIDGE=PASS'}
output_markers = {line.split(' ',1)[0] for line in output.splitlines() if line}
passed = built.returncode == 0 and executed.returncode == 0 and required <= output_markers
source_files = [guest/'drivers/gpu/drm/panthor-client/panthor_client_drv.c',guest/'include/linux/panthor_vmshm.h',test_source,Path(__file__)]
record = {
    'status': 'PASS_PRIVATE_BIND_PLANNER_MODEL' if passed else 'FAIL',
    'build_exit_code': built.returncode,
    'run_exit_code': executed.returncode,
    'observed_markers': sorted(required & output_markers),
    'source_sha256': {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files},
    'scope': 'Actual Client VM_BIND planner/GPUVA control flow, including failed-UNMAP retry, adjacent-node replacement, middle-range unmap and hole remap, with host kernel/DRM/RPC doubles',
    'not_covered': 'Linux concurrency, actual RSI/PTE state, native Panthor service, and GPU execution',
    'hardware_tests': 'NOT_RUN',
}
(out/'summary.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
assert passed, output
print(output,end='')
