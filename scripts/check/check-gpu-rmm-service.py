#!/usr/bin/env python3
"""Test actual native-service init/query source with host kernel/RSI doubles.

Checks ordering and failed admission, not real Linux probe/unplug or hardware.
"""
from pathlib import Path
import os, re, subprocess
root = Path(__file__).resolve().parents[2]
guest = root/'Linux-Guest-GPU/drivers/gpu/drm/panthor'
out = root/'build/rmm-client-bo-20261030/rmm-service-unit'
out.mkdir(parents=True, exist_ok=True)
def function(source, name):
    match = re.search(r'^(?:static )?(?:int|void|bool)\s+'+re.escape(name)+r'\s*\(', source, re.M)
    assert match, name
    start = match.start()
    end = source.index('\n}', match.end())+2
    result = source[start:end]
    assert ';' not in result[:result.index('{')], name
    return result+'\n'
device = (guest/'panthor_device.c').read_text()
driver = (guest/'panthor_drv.c').read_text()
mmu = (guest/'panthor_mmu.c').read_text()
(out/'actual.inc').write_text(function(mmu,'panthor_mmu_init')+function(device,'panthor_device_init_rmm_service')+
    function(driver,'panthor_vmshm_rmm_csif_info')+function(driver,'panthor_vmshm_fill_dev_query'))
subprocess.run([os.environ.get('HOST_CC','cc'),'-std=gnu11','-Wall','-Wextra','-Werror',
    '-Wno-unused-parameter','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
    '-D__user=','-I'+str(out),'-iquote',str(root/'Linux-Guest-GPU/include/uapi'),
    str(root/'GPU-SFTP/tests/gpu-rmm-service/service-test.c'),'-o',str(out/'service-test')],check=True)
subprocess.run([str(out/'service-test')],check=True)
