"""Actual merged RSI status arm and service auth; explicit endpoint/device doubles."""
from pathlib import Path
import hashlib
import json
import subprocess
import resource

B=Path(__file__).resolve().parents[2];S=B/'opencca/tf-rmm'
import argparse
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();O=a.out.resolve();O.mkdir(exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
source=(S/'runtime/rsi/opencca_gpu_private.c').read_text()
a=source.index('\tcase GPU_PRIVATE_IRQ_STATUS:');z=source.index('\n\tcase GPU_PRIVATE_IRQ_SELFTEST:',a);arm=source[a:z]
fw=(S/'runtime/core/opencca_gpu_firmware.c').read_text()
def fn(s,signature):
 a=s.index(signature);return s[a:s.index('\n}',a)+2]
auth=fn(fw,'static bool authenticated(');qstats=fn(fw,'bool gpu_firmware_queue_statistics(')
wrapper=fn((S/'runtime/rsi/opencca_gpu.c').read_text(),'bool opencca_gpu_root_statistics(')
stub=r'''
#include <assert.h>
#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <opencca_gpu_private.h>
#include <opencca_gpu_firmware.h>
static unsigned char proxy,client,outsider;
static const void *image_service=&proxy;
static unsigned int state=GPU_FIRMWARE_CONFIGURED;
static unsigned long queue_notify_publications=100,global_queue_publications=2;
static unsigned int channel_lookups,calls[7],device_state;
static bool mediated=true,mapping_locked;
#define OPENCCA_GPU_MEDIATED 2U
static int opencca_gpu_mappings_lock;
static void spinlock_acquire(int *p){assert(p==&opencca_gpu_mappings_lock && !mapping_locked);mapping_locked=true;}
static void spinlock_release(int *p){assert(p==&opencca_gpu_mappings_lock && mapping_locked);mapping_locked=false;}
static unsigned int opencca_gpu_state(void){return device_state;}
static void plat_opencca_gpu_root_statistics(unsigned long v[4]){assert(mapping_locked);calls[3]++;v[0]=31;v[1]=32;v[2]=33;v[3]=9;}
static void plat_opencca_gpu_as_statistics(unsigned long v[4]){assert(mapping_locked);calls[4]++;v[0]=41;v[1]=42;v[2]=255;v[3]=9;}
static void control_view_statistics(unsigned long v[4]){calls[6]++;v[0]=61;v[1]=62;v[2]=4096;v[3]=7;}
static void fake_irq_stats(unsigned int selector,struct gpu_private_result *r){
 assert(selector<=2);unsigned int public_selector=selector==2?5:selector;calls[public_selector]++;
 r->status=GPU_PRIVATE_SUCCESS;r->value[0]=public_selector*10+1;r->value[1]=public_selector*10+2;
 r->value[2]=1;r->value[3]=selector==2?2:0;
}
static const struct gpu_firmware_irq_ops irq_ops={.stats=fake_irq_stats};
static struct gpu_firmware_ops firmware_operations={.irq=&irq_ops};
static unsigned long xshm_endpoint_id(const void *p){return p==&proxy?10:p==&client?20:0;}
static bool opencca_gpu_service_isolated(const void *p,unsigned long endpoint){return mediated && p==&proxy && endpoint==10;}
static const void *xshm_endpoint_peer(const void *owner,unsigned long channel,unsigned long *id){
 channel_lookups++;*id=0;
 if(channel!=7)return NULL;
 if(owner==&proxy){*id=20;return &client;}
 if(owner==&client){*id=10;return &proxy;}
 return NULL;
}
'''
function='''
static struct gpu_private_result call(const void *owner,unsigned long channel,unsigned long handle,unsigned long b,unsigned long c,unsigned long d,unsigned long e)
{
 const void *client=NULL;unsigned long a=channel,peer_id=0;
 struct gpu_private_result result={.status=GPU_PRIVATE_INPUT};
 switch(GPU_PRIVATE_IRQ_STATUS){
'''+arm+'''
 default:assert(false);
 }
 assert(!mapping_locked);return result;
}
'''
test=r'''
int main(void){
 device_state=OPENCCA_GPU_MEDIATED;
 for(unsigned int caller=0;caller<2;caller++)for(unsigned int selector=0;selector<=6;selector++){
  unsigned int old=calls[selector];struct gpu_private_result r=call(caller?&client:&proxy,7,selector,0,0,0,0);
  assert(r.status==GPU_PRIVATE_SUCCESS);
  if(selector==2)assert(r.value[0]==100 && r.value[3]==4);
  else {assert(calls[selector]==old+1);assert(r.value[3]==(selector==3||selector==4?9:selector==5?2:selector==6?7:0));}
 }
 for(unsigned int selector=0;selector<=6;selector++){
  unsigned int before=0;for(unsigned int i=0;i<7;i++)before+=calls[i];
  assert(call(&outsider,7,selector,0,0,0,0).status==GPU_PRIVATE_INPUT);
  assert(call(&client,8,selector,0,0,0,0).status==GPU_PRIVATE_INPUT);
  mediated=false;assert(call(&client,7,selector,0,0,0,0).status==GPU_PRIVATE_INPUT);mediated=true;
  for(unsigned int field=0;field<4;field++){
   unsigned int lookups=channel_lookups;
   assert(call(&client,7,selector,field==0,field==1,field==2,field==3).status==GPU_PRIVATE_INPUT);
   assert(channel_lookups==lookups);
  }
  unsigned int after=0;for(unsigned int i=0;i<7;i++)after+=calls[i];assert(before==after);
 }
 unsigned int lookups=channel_lookups;assert(call(&client,7,7,0,0,0,0).status==GPU_PRIVATE_INPUT);assert(channel_lookups==lookups);
 state=GPU_FIRMWARE_QUARANTINED;
 for(unsigned int selector=2;selector<=6;selector++)assert(call(&client,7,selector,0,0,0,0).status==GPU_PRIVATE_INPUT);
 state=GPU_FIRMWARE_CONFIGURED;device_state=0;
 assert(call(&client,7,3,0,0,0,0).status==GPU_PRIVATE_STATE && call(&client,7,4,0,0,0,0).status==GPU_PRIVATE_STATE);
 puts("C10_DIAGNOSTIC_ROUTING=PASS actual RSI arm/FW service auth/mapping-lock wrapper, all7selectors, peer/role/state/bounds/restrictedfields; DOUBLES_ONLY");return 0;
}
'''
text=stub+'\n'+auth+'\n'+qstats+'\n'+wrapper+'\n'+function+'\n'+test
(O/'test.c').write_text(text)
cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie','-I'+str(S/'runtime/include'),str(O/'test.c'),'-o',str(O/'test')]
p=subprocess.run(cmd,capture_output=True,text=True);(O/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
p=subprocess.run([str(O/'test')],capture_output=True,text=True);(O/'run.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
(O/'summary.json').write_text(json.dumps({'status':'PASS_C10_ACTUAL_DIAGNOSTIC_ROUTING','build_command':cmd,'build_exit':0,'run_exit':0,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'scope':'Actual merged status arm/firmware auth/mapping wrapper; endpoint lookup/rec identity/device/cache/primitives are explicit doubles. Counters are not execution or completion authority.'},indent=2)+'\n');print('C10_DIAGNOSTIC_ROUTING=PASS')
