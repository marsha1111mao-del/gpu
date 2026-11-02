#!/usr/bin/env python3
"""Exercise actual RMM dead-owner cleanup/PM dispatch with lifecycle doubles.

Real core/lease/device sources; RD, RTT restoration and GPU reset are models.
"""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
rmm = root / 'opencca/tf-rmm'
out = root / 'build/rmm-client-bo-20261030/reclaim-unit'
out.mkdir(parents=True, exist_ok=True)


def function(path, name):
    source = path.read_text()
    match = re.search(r'^(?:static )?(?:void|int|unsigned long)\s+' + re.escape(name) + r'\s*\(', source, re.M)
    assert match, name
    end = source.index('\n}', match.end()) + 2
    body = source[match.start():end]
    assert ';' not in body[:body.index('{')], name
    return body + '\n'


(out / 'actual.inc').write_text(
    function(rmm / 'runtime/rsi/opencca_gpu_private.c', 'opencca_gpu_private_device_revoked') +
    function(rmm / 'runtime/rsi/opencca_gpu_private.c', 'opencca_gpu_private_reclaim') +
    function(rmm / 'runtime/rsi/opencca_gpu.c', 'smc_opencca_gpu_pm') +
    function(rmm / 'runtime/rsi/opencca_gpu.c', 'smc_opencca_gpu_mmio_grant') +
    function(root / 'Linux-Host-GPU/arch/arm64/kvm/rme.c', 'realm_reclaim_private_gpu'))
# Integration ordering is checked separately from the helper's execution.
host = (root / 'Linux-Host-GPU/arch/arm64/kvm/rme.c').read_text()
destroy = function(root / 'Linux-Host-GPU/arch/arm64/kvm/rme.c', 'kvm_destroy_realm')
assert destroy.index('realm_reclaim_private_gpu(') < destroy.index('realm_tear_down_rtt_range(') < destroy.index('rmi_realm_destroy(')
arm = function(root / 'Linux-Host-GPU/arch/arm64/kvm/arm.c', 'kvm_arch_destroy_vm')
assert arm.index('kvm_destroy_vcpus(') < arm.index('kvm_destroy_realm(')
header = (root / 'Linux-Host-GPU/arch/arm64/include/asm/rmi_smc.h').read_text()
for name, value in [('RMI_OPENCCA_GPU_PRIVATE_RECLAIM', 7), ('RMI_OPENCCA_GPU_PRIVATE_SUCCESS', 0),
                    ('RMI_OPENCCA_GPU_PRIVATE_STATE', 2), ('RMI_OPENCCA_GPU_PRIVATE_INCOMPLETE', 4)]:
    assert re.search(r'^#define\s+' + name + r'\s+' + str(value) + r'\s*$', header, re.M), name
subprocess.run([
    os.environ.get('HOST_CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
    '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
    '-I' + str(out), '-I' + str(rmm / 'runtime/include'),
    str(rmm / 'runtime/core/opencca_gpu_private.c'),
    str(rmm / 'runtime/core/opencca_gpu.c'),
    str(rmm / 'runtime/core/opencca_gpu_lease.c'),
    str(rmm / 'runtime/tests/opencca_gpu_reclaim_test.c'),
    '-o', str(out / 'reclaim-test')], check=True)
subprocess.run([str(out / 'reclaim-test')], check=True)
