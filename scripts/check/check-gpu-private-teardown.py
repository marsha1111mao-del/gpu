#!/usr/bin/env python3
"""Run actual Host DATA teardown functions with RMI/page lifetime doubles.

Covers pre-REC policy refusal and post-reclaim retry, not real KVM or GPU.
"""
from pathlib import Path
import os,re,subprocess
root=Path(__file__).resolve().parents[2]
source=(root/'Linux-Host-GPU/arch/arm64/kvm/rme.c').read_text()
out=root/'build/rmm-client-bo-20261030/teardown-unit';out.mkdir(exist_ok=True)
def function(name):
 m=re.search(r'^(?:static )?(?:int|void|bool)\s+'+name+r'\(',source,re.M)
 assert m,name
 return source[m.start():source.index('\n}',m.end())+2]+'\n'
actual=''.join(function(n) for n in ['realm_destroy_protected','realm_unmap_range_private','realm_unmap_range','kvm_realm_unmap_range'])
(out/'actual.inc').write_text(actual)
# Final destruction must explicitly retry DATA after RMM reclamation, before RTTs.
destroy=function('kvm_destroy_realm')
assert destroy.index('realm_reclaim_private_gpu(')<destroy.index('!realm_unmap_range(')<destroy.index('realm_tear_down_rtt_range(')<destroy.index('rmi_realm_destroy(')
mmu=(root/'Linux-Host-GPU/arch/arm64/kvm/mmu.c').read_text()
start=mmu.index('void kvm_free_stage2_pgd(');end=mmu.index('\n}',start)
assert 'kvm_stage2_unmap_range(' not in mmu[start:end]
assert 'kvm_realm_destroy_rtts(' not in mmu[start:end]
subprocess.run([os.environ.get('HOST_CC','cc'),'-std=gnu11','-Wall','-Wextra','-Werror',
 '-Wno-unused-parameter','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
 '-I'+str(out),str(root/'GPU-SFTP/tests/gpu-private-reclaim/teardown-test.c'),'-o',str(out/'teardown-test')],check=True)
subprocess.run([str(out/'teardown-test')],check=True)
