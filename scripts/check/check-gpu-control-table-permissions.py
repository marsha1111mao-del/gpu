"""Actual cold leaf redirection and runtime helpers with real host RO protection."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import resource
import subprocess

B=Path(__file__).resolve().parents[2];S=B/'opencca/tf-rmm'
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();O=a.out.resolve();O.mkdir(exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
source=(S/'plat/common/src/plat_common_init.c').read_text()
def fn(n):
 m=re.search(r'^(?:static )?(?:void|int) '+n+r'\(',source,re.M);assert m,n
 return source[m.start():source.index('\n}',m.end())+2]
cold=fn('gpu_control_install_leaf_tables')
hot='\n'.join(fn(n) for n in ['gpu_control_publish_tte','plat_cmn_gpu_control_map','plat_cmn_gpu_control_unmap'])
stub=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#define GRANULE_SIZE 4096UL
#define GRANULE_ALIGNED(x) (((x)&4095UL)==0UL)
#define XLAT_TABLE_ENTRIES 512U
#define XLAT_ADDR_SHIFT(l) (12U+(3U-(l))*9U)
#define PLAT_CMN_GPU_CONTROL_BASE 0xf0000000UL
#define PLAT_CMN_GPU_CONTROL_SLOTS 8192U
#define GPU_CONTROL_LEAF_TABLES 16U
#define GPU_CONTROL_STATIC_TABLES 64U
#define TRANSIENT_DESC (1UL<<55U)
#define XLAT_NG_DATA_ATTR 0x14UL
#define MT_REALM 0UL
#define TLBI_ADDR(p) ((p)>>12U)
#define XLAT_TABLES_CTX_CFG_VALID(p) ((p)->cfg!=NULL)
static uint64_t static_s1tt[64*512] __attribute__((aligned(4096)));
static uint64_t gpu_control_s1tt[16][512] __attribute__((aligned(4096)));
static struct {int base_level;} runtime_xlat_ctx_cfg={1};
static struct {uint64_t *tables;} runtime_tbls={static_s1tt};
static struct {void *cfg;} runtime_xlat_ctx={&runtime_xlat_ctx_cfg};
struct xlat_llt_info {int level;uint64_t *table;};
static bool mmu_enabled;
static bool is_mmu_enabled(void){return mmu_enabled;}
static unsigned int broadcasts,cleans;
static void clean_dcache_range(uintptr_t p,size_t bytes){assert(p && bytes);cleans++;}
#define dsb(scope) ((void)0)
#define isb() ((void)0)
static void tlbivae2is(unsigned long page){assert(page>=PLAT_CMN_GPU_CONTROL_BASE/4096UL);broadcasts++;}
static uint64_t xlat_read_tte(uint64_t *p){return *p;}
static void xlat_write_tte(uint64_t *p,uint64_t v){assert(!mmu_enabled);*p=v;}
static int xlat_get_llt_from_va(struct xlat_llt_info *info,void *ctx,uintptr_t va){
 assert(ctx==&runtime_xlat_ctx);uint64_t *table=runtime_tbls.tables;
 for(int l=runtime_xlat_ctx_cfg.base_level;l<3;l++){
  unsigned int i=(va>>XLAT_ADDR_SHIFT(l))&511U;uint64_t d=table[i];
  if((d&3UL)!=3UL)return -EFAULT;
  table=(void *)(uintptr_t)(d&UINT64_C(0x0000fffffffff000));
 }
 info->table=table;info->level=3;return 0;
}
static uint64_t *xlat_get_tte_ptr(struct xlat_llt_info *p,uintptr_t va){return &p->table[(va>>12U)&511U];}
static int xlat_map_memory_page_with_attrs(struct xlat_llt_info *p,uintptr_t va,uintptr_t pa,uint64_t attr){
 assert(mmu_enabled && attr==(XLAT_NG_DATA_ATTR|MT_REALM));
 assert((uintptr_t)p->table>=(uintptr_t)gpu_control_s1tt && (uintptr_t)p->table<(uintptr_t)(gpu_control_s1tt+16));
 uint64_t *entry=xlat_get_tte_ptr(p,va);if(*entry!=TRANSIENT_DESC)return -EFAULT;
 *entry=pa|TRANSIENT_DESC|3UL;return 0;
}
static int xlat_unmap_memory_page(struct xlat_llt_info *p,uintptr_t va){
 assert(mmu_enabled);uint64_t *entry=xlat_get_tte_ptr(p,va);if((*entry&3UL)!=3UL)return -EFAULT;
 *entry=TRANSIENT_DESC;return 0;
}
'''
test=r'''
int main(void){
 uint64_t *l2=static_s1tt+512;
 static_s1tt[(PLAT_CMN_GPU_CONTROL_BASE>>30U)&511U]=(uintptr_t)l2|3UL;
 for(unsigned int i=0;i<16;i++){
  uintptr_t va=PLAT_CMN_GPU_CONTROL_BASE+i*512UL*4096UL;
  uint64_t *leaf=static_s1tt+(2U+i)*512U;
  l2[(va>>21U)&511U]=(uintptr_t)leaf|3UL;
  for(unsigned int j=0;j<512;j++)leaf[j]=TRANSIENT_DESC;
 }
 assert(gpu_control_install_leaf_tables()==0);
 for(unsigned int i=0;i<16;i++){
  struct xlat_llt_info leaf;uintptr_t va=PLAT_CMN_GPU_CONTROL_BASE+i*512UL*4096UL;
  assert(xlat_get_llt_from_va(&leaf,&runtime_xlat_ctx,va)==0 && leaf.table==gpu_control_s1tt[i]);
  for(unsigned int j=0;j<512;j++)assert(leaf.table[j]==TRANSIENT_DESC);
 }
 /* Match the linker contract: the original tables become read-only after
  * setup. Hot operations must continue to work without changing permission.
  */
 assert(mprotect(static_s1tt,sizeof(static_s1tt),PROT_READ)==0);mmu_enabled=true;
 for(unsigned int i=0;i<8192;i+=17){
  void *address=NULL;unsigned long pa=0x60000000UL+i*4096UL;
  assert(plat_cmn_gpu_control_map(i,pa,&address)==0);
  assert(address==(void *)(PLAT_CMN_GPU_CONTROL_BASE+i*4096UL));
  assert(plat_cmn_gpu_control_unmap(i,pa)==0);
 }
 assert(broadcasts>900 && cleans>900);
 assert(mprotect(static_s1tt,sizeof(static_s1tt),PROT_READ|PROT_WRITE)==0);
 puts("C7_TABLE_PERMISSIONS=PASS actual cold redirection/runtime helpers, immutable upper tables protected by host mprotect, dedicated RW leaves only, fixed80tableallocation; MODEL_ONLY");return 0;
}
'''
variants={'candidate':cold,
 'skip-leaf-redirect':cold.replace('(desc & ~UINT64_C(0x0000fffffffff000)) |\n\t\t\t(uintptr_t)&gpu_control_s1tt[i][0]','desc',1),
 'skip-transient-initialization':cold.replace('gpu_control_s1tt[i][j] = TRANSIENT_DESC;','gpu_control_s1tt[i][j] = 0;',1),
 'wrong-leaf-target':cold.replace('(uintptr_t)&gpu_control_s1tt[i][0]','(uintptr_t)&gpu_control_s1tt[(i+1U)%16U][0]',1)}
records=[]
for name,body in variants.items():
 d=O/name;d.mkdir();(d/'test.c').write_text(stub+'\n'+body+'\n'+hot+'\n'+test)
 cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',str(d/'test.c'),'-o',str(d/'test')]
 build=subprocess.run(cmd,capture_output=True,text=True);(d/'build.log').write_text(build.stdout+build.stderr);assert build.returncode==0,(name,build.stderr)
 run=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=30);(d/'run.log').write_text(run.stdout+run.stderr)
 assert 'ERROR: AddressSanitizer' not in run.stderr and 'runtime error:' not in run.stderr
 if name=='candidate':assert run.returncode==0 and 'C7_TABLE_PERMISSIONS=PASS' in run.stdout,(name,run.stderr)
 else:assert run.returncode==-6 and 'Assertion' in run.stderr,(name,run.returncode)
 records.append({'name':name,'command':cmd,'build_exit':build.returncode,'run_exit':run.returncode});(O/'commands.json').write_text(json.dumps(records,indent=2)+'\n');print(name,'PASS',flush=True)
(O/'summary.json').write_text(json.dumps({'status':'PASS_C7_COLD_TABLE_PERMISSIONS_MODEL','compiled_mutants_rejected':3,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
 'scope':'Actual cold/runtime helper C, real host RO enforcement; descriptor walker/primitives/CPU/cache/TLB are models. Does not replace actual EL2 permissions/boot verification.'},indent=2)+'\n')
