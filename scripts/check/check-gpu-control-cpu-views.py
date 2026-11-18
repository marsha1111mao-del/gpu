"""Actual lifetime view adapter/platform helpers with two-PE TLB/cache doubles."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import resource
import subprocess

B=Path(__file__).resolve().parents[2];R=B
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
O=a.out.resolve();O.mkdir(exist_ok=False);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
S=B/'opencca/tf-rmm';registry=(S/'runtime/rsi/opencca_gpu_private.c').read_text()
platform=(S/'plat/common/src/plat_common_init.c').read_text()
def function(s,n):
    m=re.search(r'^(?:static )?(?:bool|void|int|void \*)\s*'+re.escape(n)+r'\(',s,re.M)
    if m is None:
        m=re.search(r'^static void \*'+re.escape(n)+r'\(',s,re.M)
    assert m,n
    return s[m.start():s.index('\n}',m.end())+2]
start=registry.index('struct control_cpu_view {');end=registry.index('static bool source_page(',start)
views=registry[start:end]
helpers='\n'.join(function(platform,n) for n in ['gpu_control_publish_tte','plat_cmn_gpu_control_map','plat_cmn_gpu_control_unmap'])
rw='\n'.join(function(registry,n) for n in ['clear_page','read_page','write_page'])
stub=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
/* ASan reserves the production 0xf0000000 address as shadow memory. Host
 * fixtures relocate only the VA constant; actual build/layout checks retain it.
 */
#define PLAT_CMN_GPU_CONTROL_BASE 0x30000000UL
#define PLAT_CMN_GPU_CONTROL_SLOTS 8192U
#define GPU_PRIVATE_CONTROL_PAGES 4096U
#define GRANULE_SIZE 4096UL
#define GRANULE_ALIGNED(p) (((p)&4095UL)==0UL)
#define GRANULE_STATE_DATA 3U
#define SLOT_RSI_CALL 1U
#define TRANSIENT_DESC (1UL<<55U)
#define XLAT_NG_DATA_ATTR 0x14UL
#define MT_REALM 0UL
#define TLBI_ADDR(p) ((p)>>12U)
#define XLAT_TABLES_CTX_CFG_VALID(p) ((p)->cfg!=NULL)
static struct {void *cfg;} runtime_xlat_ctx={(void *)1};
#define XLAT_TABLE_ENTRIES 512U
struct xlat_llt_info { unsigned int level; uint64_t *table; };
static uint64_t gpu_control_s1tt[16][512];
#define ttes ((uint64_t *)gpu_control_s1tt)
static uint64_t tlb[2][PLAT_CMN_GPU_CONTROL_SLOTS];
static unsigned int cpu, maps, unmaps, broadcasts, invalidates, buffer_maps,buffer_unmaps;
static unsigned int map_fail,unmap_fail,table_fail,level_override=3U;
static unsigned int event_log[262144],events;
static void event(unsigned int n) {assert(events<262144U);event_log[events++]=n;}
static void barrier(unsigned int n){event(n);}
#define dsb(scope) barrier(1U)
#define isb() barrier(2U)
static unsigned char physical[520][4096];
#define PA_BASE 0x60000000UL
struct granule {bool valid,locked;};
static struct granule granules[520];
static unsigned int pa_index(unsigned long pa) {
 assert(pa>=PA_BASE && GRANULE_ALIGNED(pa) && pa<PA_BASE+sizeof(physical));return (pa-PA_BASE)/4096U;
}
static struct granule *find_lock_granule(unsigned long pa,unsigned int state) {
 assert(state==GRANULE_STATE_DATA);unsigned int i=pa_index(pa);
 if(!granules[i].valid)return NULL;
 assert(!granules[i].locked);granules[i].locked=true;return &granules[i];
}
static void granule_unlock(struct granule *g){assert(g->locked);g->locked=false;}
typedef bool spinlock_t;
static void spinlock_acquire(spinlock_t *p){assert(!*p);*p=true;}
static void spinlock_release(spinlock_t *p){assert(*p);*p=false;}
static unsigned int va_index(uintptr_t va){assert(va>=PLAT_CMN_GPU_CONTROL_BASE && va<PLAT_CMN_GPU_CONTROL_BASE+PLAT_CMN_GPU_CONTROL_SLOTS*4096UL);return (va-PLAT_CMN_GPU_CONTROL_BASE)/4096U;}
static int xlat_get_llt_from_va(struct xlat_llt_info *table,void *ctx,uintptr_t va){
 assert(ctx==&runtime_xlat_ctx);table->table=&gpu_control_s1tt[va_index(va)/512U][0];table->level=level_override;return table_fail?-EFAULT:0;
}
static uint64_t *xlat_get_tte_ptr(struct xlat_llt_info *table,uintptr_t va){assert(table->level==3U);return &ttes[va_index(va)];}
static uint64_t xlat_read_tte(uint64_t *p){return *p;}
static int xlat_map_memory_page_with_attrs(struct xlat_llt_info *table,uintptr_t va,uintptr_t pa,uint64_t attrs){
 unsigned int i=va_index(va);assert(table->level==3U && ttes[i]==TRANSIENT_DESC);
 assert(attrs==(XLAT_NG_DATA_ATTR|MT_REALM));maps++;event(3U);
 if(map_fail==1U)return -EFAULT;
 ttes[i]=pa|3UL|TRANSIENT_DESC;
 return map_fail==2U?-EFAULT:0;
}
static int xlat_unmap_memory_page(struct xlat_llt_info *table,uintptr_t va){
 unsigned int i=va_index(va);assert(table->level==3U && (ttes[i]&3UL)==3UL);unmaps++;event(4U);
 if(unmap_fail==1U)return -EFAULT;
 ttes[i]=TRANSIENT_DESC;tlb[cpu][i]=0; /* Actual library's local TLBI semantics. */
 return unmap_fail==2U?-EFAULT:0;
}
static void tlbivae2is(unsigned long page){
 unsigned int i=va_index(page<<12U);assert(events>=2 && event_log[events-2]==5U && event_log[events-1]==1U);
 broadcasts++;event(6U);tlb[0][i]=tlb[1][i]=0;
}
static void inv_dcache_range(uintptr_t p,size_t bytes){
 assert(bytes && bytes<=4096U);invalidates++;event(7U);
 if(p>=PLAT_CMN_GPU_CONTROL_BASE && p<PLAT_CMN_GPU_CONTROL_BASE+8192UL*4096UL){
  unsigned int i=va_index(p);assert((ttes[i]&3UL)==3UL);
  unsigned long pa=ttes[i]&UINT64_C(0x000000fffffff000);
  assert(granules[pa_index(pa)].locked);
  size_t offset=p&4095UL;memcpy((void *)p,physical[pa_index(pa)]+offset,bytes);
 }
}
static void clean_dcache_range(uintptr_t p,size_t bytes){
 assert(bytes);event(5U);
 if(p>=PLAT_CMN_GPU_CONTROL_BASE && p<PLAT_CMN_GPU_CONTROL_BASE+8192UL*4096UL){
  unsigned int i=va_index(p);assert((ttes[i]&3UL)==3UL);unsigned long pa=ttes[i]&UINT64_C(0x000000fffffff000);
  assert(granules[pa_index(pa)].locked);size_t offset=p&4095UL;
  assert(offset+bytes<=4096U);memcpy(physical[pa_index(pa)]+offset,(void *)p,bytes);
 }
}
static void *buffer_granule_map(struct granule *g,unsigned int slot){
 assert(g->locked && slot==SLOT_RSI_CALL);buffer_maps++;return physical[g-granules];
}
static void buffer_unmap(void *p){assert(p>=(void *)physical && p<(void *)(physical+520));buffer_unmaps++;dsb(sy);isb();}
'''
test=r'''
static void cached_on_both(unsigned long pa) {
 struct granule *g=find_lock_granule(pa,GRANULE_STATE_DATA);assert(g);
 void *p=control_view_address(pa);assert(p);unsigned int i=va_index((uintptr_t)p);
 for(unsigned int c=0;c<2;c++)tlb[c][i]=ttes[i];granule_unlock(g);
}
static void assert_retired(unsigned long pa) {
 assert(events>=3 && event_log[events-3]==6U && event_log[events-2]==1U && event_log[events-1]==2U);
 for(unsigned int c=0;c<2;c++)for(unsigned int i=0;i<8192;i++)
  assert((tlb[c][i]&UINT64_C(0x000000fffffff000))!=pa);
}
int main(void) {
 void *memory=mmap((void *)PLAT_CMN_GPU_CONTROL_BASE,8192UL*4096UL,PROT_READ|PROT_WRITE,
    MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);assert(memory==(void *)PLAT_CMN_GPU_CONTROL_BASE);
 for(unsigned int i=0;i<8192;i++)ttes[i]=TRANSIENT_DESC;
 for(unsigned int i=0;i<520;i++)granules[i].valid=true;
 unsigned char owner,other;unsigned long pa=PA_BASE;unsigned long stats[4];
 assert(!pin_control_page(NULL,1,0,pa) && !pin_control_page(&owner,0,0,pa));
 assert(!pin_control_page(&owner,1,4096,pa) && !pin_control_page(&owner,1,0,0));
 assert(!pin_control_page(&owner,1,0,pa+1) && !pin_control_page(&owner,1,0,1UL<<40U));
 assert(!unpin_control_page(NULL,1,0,pa) && !maps);
 granules[0].valid=false;assert(!pin_control_page(&owner,1,0,pa));granules[0].valid=true;
 level_override=2;assert(!pin_control_page(&owner,1,0,pa));level_override=3;
 assert(!control_view_address(pa));assert(unpin_control_page(&owner,1,0,pa));
 assert(pin_control_page(&owner,1,0,pa));assert(pin_control_page(&owner,1,0,pa));
 assert(!pin_control_page(&other,1,0,pa) && !pin_control_page(&owner,2,0,pa));
 assert(!pin_control_page(&owner,1,1,pa));cached_on_both(pa);
 unsigned int oldmaps=maps,oldbuffers=buffer_maps;uint64_t value;
 for(unsigned int i=0;i<64;i++){
  *(uint64_t *)physical[0]=UINT64_C(0xabcdef0000)+i;
  cpu=i&1;assert(read_page(pa,0,&value,sizeof(value)) && value==UINT64_C(0xabcdef0000)+i);
 }
 assert(maps==oldmaps && buffer_maps==oldbuffers && invalidates>=64);
 value=0x987654321UL;assert(write_page(pa,8,&value,8));assert(*(uint64_t *)(physical[0]+8)==value);
 assert(!read_page(pa,4090,&value,8) && !write_page(pa,0,NULL,8));
 assert(!unpin_control_page(&other,1,0,pa) && !unpin_control_page(&owner,2,0,pa));
 assert(control_views_pinned==1U);
 assert(unpin_control_page(&owner,1,0,pa));assert_retired(pa);
 assert(clear_page(pa) && physical[0][0]==0 && !control_view_address(pa));
 assert(!control_views_pinned && buffer_maps==oldbuffers+1U && buffer_unmaps==buffer_maps);
 puts("C7_VIEW=PASS fresh-data exact-owner identity, hot access no remap, all-PE retirement");
 for(unsigned int failure=1;failure<=2;failure++) {
  map_fail=failure;assert(!pin_control_page(&owner,10+failure,0,pa));map_fail=0;
  assert(control_views_pinned==1 && !control_view_address(pa));
  assert(!pin_control_page(&other,20,0,pa));
  assert(unpin_control_page(&owner,10+failure,0,pa));assert_retired(pa);assert(!control_views_pinned);
 }
 for(unsigned int failure=1;failure<=2;failure++) {
  assert(pin_control_page(&owner,50,0,pa));cached_on_both(pa);
  unmap_fail=failure;assert(!unpin_control_page(&owner,50,0,pa));unmap_fail=0;
  assert(control_views_pinned==1 && !control_view_address(pa));
  assert(!pin_control_page(&owner,50,0,pa) && !pin_control_page(&other,60,0,pa));
  assert(unpin_control_page(&owner,50,0,pa));assert_retired(pa);assert(!control_views_pinned);
 }
 assert(pin_control_page(&owner,80,0,pa));bool found;unsigned int slot=control_view_find(pa,&found);assert(found);
 uint64_t saved=ttes[slot];ttes[slot]=(pa+4096UL)|3UL|TRANSIENT_DESC;
 assert(!unpin_control_page(&owner,80,0,pa) && !control_view_address(pa));ttes[slot]=saved;
 assert(unpin_control_page(&owner,80,0,pa));assert_retired(pa);
 puts("C7_VIEW=PASS partial-install/unmap quarantine, wrong actual PTE target rejects");
 /* Churn tombstones and reuse exactly the same page with new object generation. */
 for(unsigned int round=0;round<8;round++) {
  for(unsigned int i=0;i<513;i++)assert(pin_control_page(&owner,100+round,i,PA_BASE+i*4096UL));
  for(unsigned int i=0;i<513;i+=2)cached_on_both(PA_BASE+i*4096UL);
  for(unsigned int i=0;i<513;i++){
   assert(!unpin_control_page(&owner,99+round,i,PA_BASE+i*4096UL));
   assert(unpin_control_page(&owner,100+round,i,PA_BASE+i*4096UL));assert_retired(PA_BASE+i*4096UL);
  }
  assert(!control_views_pinned);
 }
 control_view_statistics(stats);assert(stats[0]>=64 && stats[3]==7 && !stats[2]);
 assert(munmap(memory,8192UL*4096UL)==0);
 puts("C7_VIEW=PASS 513-page lifecycle churn/generation, fresh DATA locks and unchanged physical quota; MODEL_ONLY");
 return 0;
}
'''
variants={'candidate':(views,helpers,rw)}
variants['omit-broadcast']=(views,helpers.replace('tlbivae2is(TLBI_ADDR(va));','(void)va;'),rw)
variants['omit-TTE-clean']=(views,helpers.replace('clean_dcache_range((uintptr_t)entry, sizeof(*entry));','(void)entry;'),rw)
variants['omit-completion-ISB']=(views,helpers.replace('\tisb();','\t(void)va;'),rw)
# Target read_page rather than clear_page for cache mutant.
variants['stale-payload']=(views,helpers,rw.replace(function(registry,'read_page'),function(registry,'read_page').replace('inv_dcache_range((uintptr_t)memory, GRANULE_SIZE);','(void)memory;')))
variants['ignore-owner']=(views.replace('control_views[i].owner == owner &&','true &&'),helpers,rw)
variants['mark-failed-install-usable']=(views.replace('control_views[i].usable = pinned;','control_views[i].usable = true;'),helpers,rw)
variants['ignore-real-PTE-target']=(views,helpers.replace('(descriptor & UINT64_C(0x000000fffffff000)) != pa ||','false ||'),rw)
records=[]
for name,(v,h,access) in variants.items():
 d=O/name;d.mkdir();src=d/'test.c';src.write_text(stub+'\n'+h+'\n'+v+'\n'+access+'\n'+test)
 cmd=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',str(src),'-o',str(d/'test')]
 build=subprocess.run(cmd,capture_output=True,text=True);(d/'build.log').write_text(build.stdout+build.stderr);assert build.returncode==0,(name,build.stderr)
 run=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=50);(d/'run.log').write_text(run.stdout+run.stderr)
 assert 'ERROR: AddressSanitizer' not in run.stderr and 'runtime error:' not in run.stderr
 if name=='candidate':assert run.returncode==0 and run.stdout.count('C7_VIEW=PASS')==3,(name,run.stderr)
 else:assert run.returncode==-6 and 'Assertion' in run.stderr,(name,run.returncode)
 records.append({'name':name,'command':cmd,'build_exit':build.returncode,'run_exit':run.returncode})
 (O/'commands.json').write_text(json.dumps(records,indent=2)+'\n');print(name,'PASS',flush=True)
(O/'summary.json').write_text(json.dumps({'status':'PASS_C7_ACTUAL_VIEW_PLATFORM_HELPER_MODELS','compiled_mutants_rejected':len(variants)-1,
 'source_sha256':{'adapter':hashlib.sha256(registry.encode()).hexdigest(),'platform':hashlib.sha256(platform.encode()).hexdigest()},
 'scope':'Actual adapter registry/data accesses and platform helper C; descriptor/cache/physical memory/two-CPU TLB/primitives/locks are models. Does not prove physical mapping installation, real concurrency or performance.'},indent=2)+'\n')
