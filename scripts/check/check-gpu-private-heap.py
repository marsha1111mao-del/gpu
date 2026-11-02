#!/usr/bin/env python3
"""Actual Client/kernel heap lifecycle and growth linked to the RMM PT core.

Allocator, RSI, CPU mapping, locks and DRM xarrays are host doubles. Checks real
RMM ownership/PTE/refcounts and driver flow, not Linux concurrency or GPU use.
"""
from pathlib import Path
import os, re, subprocess
root=Path(__file__).resolve().parents[2]
guest=root/'Linux-Guest-GPU'
out=root/'build/rmm-client-bo-20261030/private-heap-unit';out.mkdir(parents=True,exist_ok=True)
kernel=(guest/'drivers/char/realm_gpu.c').read_text()
client=(guest/'drivers/gpu/drm/panthor-client/panthor_client_drv.c').read_text()
wire=(guest/'include/linux/panthor_vmshm.h').read_text()
def function(source,name):
    m=re.search(r'^(?:static )?(?:struct \w+ \*|int\s+|long\s+|bool\s+|void\s+|u64\s+)'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{',source,re.M)
    assert m,name
    start=m.start()
    end=source.index('\n}',m.end())+2
    result=source[start:end]
    assert ';' not in result[:result.index('{')],name
    return result+'\n'
def structure(source,name):
    m=re.search(r'^struct '+name+r' \{',source,re.M);assert m,name
    return source[m.start():source.index('\n};',m.end())+3]+'\n'
parts=[structure(kernel,n) for n in ('realm_gpu_bo','realm_gpu_context','realm_gpu_task',
                                  'realm_gpu_heap_chunk','realm_gpu_heap','realm_gpu_group')]
parts += [structure(client,'panthor_client_heap')]
parts += [structure(wire,'panthor_vmshm_tiler_heap_'+n) for n in ('create_req','create_rsp')]
parts += [l for l in kernel.splitlines() if l.startswith('#define PRIVATE_')]
(out/'structures.inc').write_text('\n'.join(parts))
names=('private_status','managed_handle','managed_context','heap_context_busy','heap_range_busy','free_backing',
       'unregister_bo','seal_bo_locked','realm_gpu_bo_set_uncached','reap_backing','reap_contexts','realm_gpu_bo_put','realm_gpu_context_put',
       'realm_gpu_context_set_va_split','heap_unmap_range_locked','heap_unmap_locked',
       'heap_forget_locked','heap_free_va_locked','reap_heaps',
       'realm_gpu_heap_create','realm_gpu_heap_context_va','realm_gpu_heap_first_chunk_va',
       'realm_gpu_heap_put','realm_gpu_task_heap_service','realm_gpu_reap_private',
       'realm_gpu_ioctl','realm_gpu_private_call','task_drop_hint_locked','realm_gpu_group_local_hint',
       'local_hint_commands','realm_gpu_task_has_hint','realm_gpu_task_hint_pending')
(out/'kernel.inc').write_text('\n'.join(function(kernel,n) for n in names))
names=('panthor_client_private_heap_create','panthor_client_tiler_heap_create',
       'panthor_client_tiler_heap_destroy','panthor_client_heaps_release_local',
       'panthor_client_private_heaps_release_vm')
initializers=re.findall(r'\txa_init(?:_flags)?\(&pcfile->\w+[^;]*;',
                        function(client,'panthor_client_open'))
assert len(initializers)==5
(out/'client.inc').write_text('\n'.join(function(client,n) for n in names)+
    '\nstatic void actual_frontend_xarray_init(struct panthor_client_file *pcfile)\n{\n'+
    '\n'.join(initializers)+'\n}\n')
subprocess.run([os.environ.get('HOST_CC','cc'),'-std=gnu11','-Wall','-Wextra','-Werror',
    '-Wno-unused-parameter','-D__user=','-g','-fsanitize=address,undefined',
    '-fno-omit-frame-pointer','-fno-pie','-no-pie','-I'+str(out),
    '-I'+str(root/'opencca/tf-rmm/runtime/core'),'-I'+str(root/'opencca/tf-rmm/runtime/include'),
    '-iquote',str(guest/'include/uapi'),str(root/'GPU-SFTP/tests/gpu-private-heap/heap-test.c'),
    '-o',str(out/'heap-test')],check=True)
subprocess.run([str(out/'heap-test')],check=True)

rsi=(root/'opencca/tf-rmm/runtime/rsi/opencca_gpu_private.c').read_text()
(out/'rsi.inc').write_text(function(rsi,'task_heap_call'))
# The actual dispatcher must invoke the adapter while holding the policy gate.
dispatch=function(rsi,'handle_rsi_opencca_gpu_private')
start=dispatch.index('case GPU_PRIVATE_TASK_HEAP_EVENT:')
end=dispatch.index('case GPU_PRIVATE_TASK_READY:',start)
assert dispatch[start:end].count('task_heap_call(rec, &result)')==1
assert dispatch.index('xshm_policy_lock()')<start<end<dispatch.index('xshm_policy_unlock()')
subprocess.run([os.environ.get('HOST_CC','cc'),'-std=c11','-Wall','-Wextra','-Werror',
    '-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
    '-I'+str(out),'-I'+str(root/'opencca/tf-rmm/runtime/include'),
    str(root/'GPU-SFTP/tests/gpu-private-heap/rsi-test.c'),'-o',str(out/'rsi-test')],check=True)
subprocess.run([str(out/'rsi-test')],check=True)
