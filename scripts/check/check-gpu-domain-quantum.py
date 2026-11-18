#!/usr/bin/env python3
"""Actual RSI/core/platform tests for bounded solo retention and immediate contention yield."""
import argparse,hashlib,json,os,resource,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
rmm=root/'opencca/tf-rmm'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--reference',type=Path,help='Frozen 32-batch core for differential validation')
a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
subprocess.run(['python3',str(root/'scripts/check/check-gpu-domain-dispatch.py'),'--out',str(out),'--prepare-only'],check=True)
core=rmm/'runtime/core/opencca_gpu_firmware.c';original=core.read_text()
start=original.index('static unsigned int task_domain_quantum(');end=original.index('\n}',start)+2
fragment=original[start:end];assert fragment.count('unsigned int quantum = 128U;')==1
variants={'candidate':(original,128,True)}
if a.reference:variants['reference']=(a.reference.read_text(),32,True)
for name,old,new in [('no-waiter-yield','return 1U;','return 8U;'),('ignore-competition','quantum = 8U;','quantum = 128U;'),('wrong-solo-bound','quantum = 128U;','quantum = 256U;')]:
 assert fragment.count(old)==1
 variants[name]=(original[:start]+fragment.replace(old,new)+original[end:],128,False)
sources=['plat/rk3588/src/rk3588_gpu.c','runtime/core/opencca_gpu.c','runtime/core/xshm_endpoint.c','runtime/core/opencca_gpu_lease.c','runtime/core/opencca_gpu_private.c','ext/mbedtls/library/sha256.c','ext/mbedtls/library/platform_util.c','runtime/tests/opencca_gpu_backend_test.c']
includes=['runtime/tests/mmio-stubs','runtime/include','ext/mbedtls/include','ext/mbedtls/library']
rows=[]
for name,(code,quantum,passing) in variants.items():
 src=out/(name+'.c');src.write_text(code)
 cmd=[os.environ.get('HOST_CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie','-DGPU_DOMAIN_RSI_TEST','-DGPU_DOMAIN_LEASE_TEST','-DGPU_TEST_SOLO_QUANTUM='+str(quantum),'-I'+str(out)]
 cmd+=['-I'+str(rmm/i) for i in includes]+[str(rmm/s) for s in sources]+[str(src),'-o',str(out/name)]
 with (out/(name+'-build.log')).open('w') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 rows.append(dict(name=name,phase='build',command=cmd,exit_code=rc));assert rc==0,(name,rc)
 run=[str(out/name),str(root/'GPU-SFTP/panthor_fw/mali_csffw.bin'),'--domain-only']
 with (out/(name+'-run.log')).open('w') as f:rc=subprocess.run(run,env=dict(os.environ,GPU_LEASE_CASE='0'),stdout=f,stderr=subprocess.STDOUT).returncode
 text=(out/(name+'-run.log')).read_text()
 assert (rc==0 and text.count('GPU_DOMAIN_LEASE=PASS')==2) if passing else rc==-6 and 'Assertion' in text,(name,rc)
 rows.append(dict(name=name,phase='run',command=run,environment={'GPU_LEASE_CASE':'0'},exit_code=rc));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(name,'PASS',flush=True)
source_files=[core,rmm/'runtime/tests/opencca_gpu_backend_test.c',root/'scripts/check/check-gpu-domain-dispatch.py',Path(__file__)]
(out/'summary.json').write_text(json.dumps(dict(status='PASS',models_only=True,cycles_per_client=384,solo=128,competing=8,waiting_next_boundary=True,negative_variants=[n for n,(_,_,p) in variants.items() if not p],source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},scope='Actual RSI/core/platform bounded domain selection for two clients with 384 legal cycles per client; shared execution yields every 8 batches and solo execution every 128, with old-token rejection and staged waiter handoff',not_covered='Normal stop/UNMAP followed by BO reuse, physical GPU execution, real IRQ timing, Linux concurrency, and whole-device reset',hardware_tests='NOT_RUN'),indent=2)+'\n')
