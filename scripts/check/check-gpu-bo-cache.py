#!/usr/bin/env python3
"""Exercise actual Client BO cache functions with modeled memory/RSI/locks."""
import argparse, os, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
s=(ROOT/'Linux-Guest-GPU/drivers/char/realm_gpu.c').read_text()
structs=[]
for name in ['realm_gpu_bo_cache','realm_gpu_bo']:
 m=re.search(r'^struct '+name+r' \{.*?^};',s,re.M|re.S);assert m;structs.append(m[0])
names=['realm_gpu_bo_set_uncached','bo_cache_put','bo_idle_locked','realm_gpu_bo_cache_create','realm_gpu_bo_cache_close','realm_gpu_bo_alloc_cached','realm_gpu_bo_put']
fns=[]
for name in names:
 m=re.search(r'^(?:static )?[\w *]+\b'+name+r'\([^;{}]*\)\n\{',s,re.M);assert m,name
 end=s.index('\n}',m.end())+2;fns.append(s[m.start():end])
(a.out/'cache-structs.inc').write_text('\n'.join(structs))
(a.out/'cache-functions.inc').write_text('\n'.join(fns))
cmd=[os.getenv('HOST_CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie','-I'+str(a.out),str(ROOT/'GPU-SFTP/tests/gpu-private-bo-cache/cache-test.c'),'-o',str(a.out/'test')]
subprocess.run(cmd,check=True);subprocess.run([str(a.out/'test')],check=True)
