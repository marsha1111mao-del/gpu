"""Actual conditional MMIO-root equality versus independent 64-bit equality."""
from pathlib import Path
import argparse
import hashlib
import json
import resource
import subprocess

B=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();O=a.out.resolve();O.mkdir(exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
source=(B/'opencca/tf-rmm/plat/rk3588/src/rk3588_gpu.c').read_text()
start=source.index('static unsigned long root_comparisons,');end=source.index('\nstatic bool private_pt_command(',start)
actual=source[start:end]
stub=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#define GPU_AS_COUNT 16U
#define GPU_AS_PRESENT 32U
#define AS_TRANSTAB_LO(s) ((s)*2U)
#define AS_TRANSTAB_HI(s) ((s)*2U+1U)
static uint32_t registers[33];static unsigned int reads[33];
static uint32_t reg_read(unsigned long offset){assert(offset<33);reads[offset]++;return registers[offset];}
'''
test=r'''
static uint64_t random_state=UINT64_C(0x7ac8a03b47b4);
static uint64_t next_random(void){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
int main(void){
 uint64_t boundaries[]={0,1,4096,UINT32_MAX,UINT64_C(0x100000000),UINT64_C(0x100001000),
    UINT64_C(0x10000000000),UINT64_C(0x8000000000000000),UINT64_MAX};
 unsigned long cases=0;unsigned long stats[4];
 for(unsigned int slot=0;slot<16;slot++)for(unsigned int a=0;a<9;a++)for(unsigned int b=0;b<9;b++){
  uint64_t hardware=boundaries[a],expected=boundaries[b];
  registers[slot*2]=(uint32_t)hardware;registers[slot*2+1]=(uint32_t)(hardware>>32);
  unsigned int low=reads[slot*2],high=reads[slot*2+1];
  bool result=private_pt_root_matches(slot,expected);
  assert(result==(hardware==expected));
  assert(reads[slot*2]==low+1U && reads[slot*2+1]==high+((uint32_t)hardware==(uint32_t)expected));cases++;
 }
 for(unsigned int i=0;i<200000;i++){
  unsigned int slot=i%16;uint64_t hardware=next_random(),expected=next_random();
  if(i%3==0)expected=(expected&UINT64_C(0xffffffff00000000))|(uint32_t)hardware;
  if(i%7==0)expected=hardware;
  registers[slot*2]=(uint32_t)hardware;registers[slot*2+1]=hardware>>32;
  unsigned int low=reads[slot*2],high=reads[slot*2+1];
  assert(private_pt_root_matches(slot,expected)==(hardware==expected));
  assert(reads[slot*2]==low+1U && reads[slot*2+1]==high+((uint32_t)hardware==(uint32_t)expected));cases++;
 }
 plat_opencca_gpu_root_statistics(stats);
 assert(stats[0]==cases && stats[0]==stats[1]+stats[2] && stats[3]==9UL);
 assert(stats[1]>100000UL && stats[2]>20000UL);
 /* Counter overflow is observable but cannot change the root decision. */
 root_comparisons=~0UL;registers[0]=0;registers[1]=1;
 assert(private_pt_root_matches(0,UINT64_C(0x100000000)));
 assert(!private_pt_root_matches(0,UINT64_C(0x200000000)));
 plat_opencca_gpu_root_statistics(stats);assert(stats[3]==0UL);
 root_statistics_overflow=false;root_comparisons=root_low_misses=root_high_reads=0;
 unsigned long mask_cases=0;uint64_t expected_root=UINT64_C(0x100002000);
 const uint32_t masks[]={1U,3U,0xffU,0xffffU,0x8003U,0x8001U,0xaaaaU,0x10003U};
 for(unsigned int m=0;m<8;m++)for(unsigned int slot=1;slot<16;slot++)for(unsigned int alias=0;alias<16;alias++){
  registers[GPU_AS_PRESENT]=masks[m];
  for(unsigned int j=0;j<16;j++){uint64_t value=j==alias?expected_root:0UL;registers[2*j]=value;registers[2*j+1]=value>>32;}
  bool expected=(masks[m]&((1U<<slot)|1U))==((1U<<slot)|1U) && !(masks[m]>>16U) &&
    !(alias && alias!=slot && (masks[m]&(1U<<alias)));
  assert(private_pt_no_aliases(slot,expected_root)==expected);mask_cases++;
 }
 for(unsigned int test=0;test<100000;test++){
  unsigned int slot=1U+test%15U;uint32_t mask=(uint32_t)next_random()&0xffffU;
  if(test%3==0)mask|=1U|(1U<<slot);registers[GPU_AS_PRESENT]=mask;
  uint64_t root=next_random()|4096UL;bool alias_found=false;
  for(unsigned int j=0;j<16;j++){
   uint64_t value=next_random();if(test%7==0 && j==((test/7)%16U))value=root;
   registers[2*j]=(uint32_t)value;registers[2*j+1]=value>>32;
   if(j && j!=slot && (mask&(1U<<j)) && value==root)alias_found=true;
  }
  bool expected=(mask&((1U<<slot)|1U))==((1U<<slot)|1U) && !alias_found;
  assert(private_pt_no_aliases(slot,root)==expected);mask_cases++;
 }
 for(unsigned int j=0;j<32;j++)registers[j]=0;
 registers[GPU_AS_PRESENT]=0xff;assert(private_pt_no_aliases(1,expected_root));
 registers[30]=(uint32_t)expected_root;registers[31]=expected_root>>32;
 registers[GPU_AS_PRESENT]=0x8003;assert(!private_pt_no_aliases(1,expected_root)); /* Refresh each invocation. */
 registers[30]^=1U;assert(private_pt_no_aliases(1,expected_root));
 registers[GPU_AS_PRESENT]=0xff;assert(!private_pt_no_aliases(15,expected_root));
 assert(!private_pt_no_aliases(0,expected_root) && !private_pt_no_aliases(16,expected_root) && !private_pt_no_aliases(1,0));
 plat_opencca_gpu_as_statistics(stats);assert(stats[0]>100000 && stats[1]>0 && stats[3]==9UL);
 printf("C9_PRESENT_AS=PASS cases=%lu fresh masks/holes/bit15/unsupported AS/current-AS disappearance and true64bit alias refusal; MODEL_ONLY\n",mask_cases);

 printf("C8_ROOT_EQUALITY=PASS cases=%lu exact64bit/high-word-only/4GB/zero/random, conditionalHI and diagnostic overflow not authorization; MODEL_ONLY\n",cases);return 0;
}
'''
variants={'candidate':actual,
 'cached-eight-mask':actual.replace('present = reg_read(GPU_AS_PRESENT);','present = 0xffU;',1),
 'omit-bit15':actual.replace('present = reg_read(GPU_AS_PRESENT);','present = reg_read(GPU_AS_PRESENT) & 0x7fffU;',1),
 'ignore-current-presence':actual.replace('(present & ((1U << slot) | 1U)) != ((1U << slot) | 1U) ||','false ||',1),
 'accept-low-alone':actual.replace('return reg_read(AS_TRANSTAB_HI(slot)) == (uint32_t)(root >> 32U);','return true;',1),
 'ignore-low':actual.replace('if (low != (uint32_t)root)', 'if (false && low != (uint32_t)root)',1),
 'wrong-slot':actual.replace('reg_read(AS_TRANSTAB_LO(slot))','reg_read(AS_TRANSTAB_LO(slot ^ 1U))',1),
 'truncate-high':actual.replace('(uint32_t)(root >> 32U)','(uint32_t)root',1)}
records=[]
for name,body in variants.items():
 d=O/name;d.mkdir();(d/'test.c').write_text(stub+'\n'+body+'\n'+test)
 cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',str(d/'test.c'),'-o',str(d/'test')]
 build=subprocess.run(cmd,capture_output=True,text=True);(d/'build.log').write_text(build.stdout+build.stderr);assert build.returncode==0,(name,build.stderr)
 run=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=30);(d/'run.log').write_text(run.stdout+run.stderr)
 assert 'ERROR: AddressSanitizer' not in run.stderr and 'runtime error:' not in run.stderr
 if name=='candidate':assert run.returncode==0 and 'C8_ROOT_EQUALITY=PASS' in run.stdout,(name,run.stderr)
 else:assert run.returncode==-6 and 'Assertion' in run.stderr,(name,run.returncode)
 records.append({'name':name,'command':cmd,'build_exit':build.returncode,'run_exit':run.returncode});(O/'commands.json').write_text(json.dumps(records,indent=2)+'\n');print(name,'PASS',flush=True)
(O/'summary.json').write_text(json.dumps({'status':'PASS_C9_ACTUAL_ROOT_AND_AS_MASK','root_pairs':201296,'mask_cases':101920,'compiled_mutants_rejected':7,
 'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'scope':'Actual helper and counters; independent64bit value equality and modeled MMIO. Register/configuration writers remain excluded by original locks; not real GPU/physical isolation or concurrent hostile-MMIO proof.'},indent=2)+'\n')
