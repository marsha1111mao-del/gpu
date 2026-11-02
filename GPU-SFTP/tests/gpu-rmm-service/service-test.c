// SPDX-License-Identifier: GPL-2.0-only
/* Actual service init/query functions, host doubles only, no Linux/GPU claim. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "linux/realm_gpu.h"
#include "drm/panthor_drm.h"
typedef uint32_t u32;
#define U32_MAX UINT32_MAX
#define CC_ATTR_MEM_ENCRYPT 1
#define GPU_MMU_FEATURES_VA_BITS(x) ((x)&255)
#define GFP_KERNEL 0
#define WQ_UNBOUND 1
#define GENMASK(h,l) ((UINT32_MAX >> (31-(h))) & (UINT32_MAX << (l)))
#define RSI_SUCCESS 0
#define SMC_RSI_OPENCCA_GPU_CONTROL 123
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((long)(p))
#define min(a,b) ((a)<(b)?(a):(b))
#define PANTHOR_UOBJ_MIN_SIZE(x) sizeof(x)
#define PANTHOR_VMSHM_DEV_QUERY_F_DATA 1
struct device { int tag; };
struct platform_device { struct device base; };
struct drm_device { struct device *dev; };
struct list_head { bool initialized; };
#define INIT_LIST_HEAD(p) ((p)->initialized=true)
struct panthor_mmu {
    struct {struct list_head lru_list;int slots_lock;} as;
    struct {struct list_head list;int lock;void *wq;} vm;
    int irq;
};
struct panthor_device {
    struct drm_device base;void *iomem;uint64_t phys_addr;bool rmm_service;
    struct panthor_mmu *mmu;
    struct drm_panthor_gpu_info gpu_info;struct drm_panthor_csif_info csif_info;
};
struct resource { uint64_t start; };
struct arm_smccc_res { uint64_t a0; };
struct panthor_vmshm_dev_query_req {u32 type,flags,size;};
struct panthor_vmshm_dev_query_rsp {u32 type,size,data_len;unsigned char data[256];};
static bool realm,map_fail,claim_fail,isolated;
static unsigned int maps,claims,reads,isolate_calls,unmaps,mmus,registrations,properties;
static unsigned int sequence;
static unsigned int irq_lookups,irq_requests,workqueues;
static int isolate_error,mmu_error,register_error,property_fail_call;
static unsigned int bad_reply;
static uint64_t fw_state,group_count,stream_count,stream_features;
static bool cc_platform_has(int feature) {return realm;}
static struct platform_device *to_platform_device(struct device *d) {return (void *)d;}
static void *devm_platform_get_and_ioremap_resource(struct platform_device *d,int index,struct resource **out) {
    static struct resource res={.start=0xfb000000};maps++;assert(!sequence++);*out=&res;
    return map_fail?(void *)(intptr_t)-ENOMEM:(void *)(uintptr_t)0x10000;
}
static void arm_smccc_1_1_smc(unsigned int op,int a,int b,int c,int d,int e,int f,int g,struct arm_smccc_res *r) {
    claims++;assert(sequence++==1);r->a0=claim_fail?1:RSI_SUCCESS;
}
static void panthor_gpu_init_info(struct panthor_device *p) {
    reads++;assert(!isolated && p->iomem && sequence++==2);p->gpu_info.gpu_id=0x12345678;
}
static int realm_gpu_private_call_checked(struct realm_gpu_call *c) {
    if(c->operation==REALM_GPU_SERVICE_ISOLATE){
        isolate_calls++;assert(sequence++==3);isolated=true;
        if(isolate_error)return isolate_error;
        c->result[0]=bad_reply==1?0:1;c->result[3]=bad_reply==2?1:0;return 0;
    }
    assert(c->operation==REALM_GPU_FW_INSPECT || c->operation==REALM_GPU_FW_PROPERTIES);
    properties++;if(property_fail_call==(int)properties)return -EACCES;
    if(c->operation==REALM_GPU_FW_INSPECT){c->result[0]=fw_state;return 0;}
    if(!c->args[0])c->result[2]=group_count;
    else{assert(c->args[0]==1);c->result[0]=stream_count;c->result[1]=stream_features;}
    return 0;
}
static void devm_iounmap(struct device *d,void *mapping) {
    unmaps++;assert(mapping==(void *)(uintptr_t)0x10000 && sequence==(claim_fail?2:4));sequence++;
}
static void *drmm_kzalloc(struct drm_device *d,size_t bytes,int flags) {
    static struct panthor_mmu mmu;
    struct panthor_device *p=(void *)d;mmus++;assert(bytes==sizeof(mmu));
    if(p->rmm_service)assert(!p->iomem && isolated && sequence++==5);
    memset(&mmu,0,sizeof(mmu));return mmu_error?NULL:&mmu;
}
static int drmm_mutex_init(struct drm_device *d,int *lock) {*lock=0;return 0;}
static int platform_get_irq_byname(struct platform_device *p,const char *name) {
    assert(!isolated && !strcmp(name,"mmu"));irq_lookups++;return 17;
}
static u32 panthor_mmu_fault_mask(struct panthor_device *p,int mask) {assert(p->iomem && !isolated);return mask;}
static int panthor_request_mmu_irq(struct panthor_device *p,int *out,int irq,u32 mask) {
    assert(!isolated && irq==17);irq_requests++;*out=irq;return 0;
}
static void *alloc_workqueue(const char *name,int flags,int max) {workqueues++;return (void *)(uintptr_t)1;}
static void panthor_mmu_release_wq(struct drm_device *d,void *wq) { }
static int drmm_add_action_or_reset(struct drm_device *d,void (*fn)(struct drm_device *,void *),void *p) {return 0;}
static int drm_dev_register(struct drm_device *d,int flags) {
    registrations++;assert(sequence++==6);return register_error;
}
#define drm_info(...) ((void)0)
#include "actual.inc"

static struct device dev;
static struct panthor_device pt;
static unsigned int cases;
static void setup(void) {
    memset(&pt,0,sizeof(pt));pt.base.dev=&dev;pt.rmm_service=true;
    realm=true;map_fail=claim_fail=isolated=false;
    maps=claims=reads=isolate_calls=unmaps=mmus=registrations=properties=sequence=0;
    irq_lookups=irq_requests=workqueues=0;
    isolate_error=mmu_error=register_error=property_fail_call=bad_reply=0;
    fw_state=7;group_count=4;stream_count=8;stream_features=63|(8<<8);cases++;
}
int main(void) {
    setup();assert(!panthor_device_init_rmm_service(&pt));
    assert(!pt.iomem && maps==1 && claims==1 && reads==1 && unmaps==1 && mmus==1 && registrations==1);
    assert(!irq_lookups && !irq_requests && workqueues==1);
    setup();realm=false;assert(panthor_device_init_rmm_service(&pt)==-EOPNOTSUPP && !maps && !claims);
    setup();map_fail=true;assert(panthor_device_init_rmm_service(&pt)==-ENOMEM && !claims && !unmaps);
    setup();claim_fail=true;assert(panthor_device_init_rmm_service(&pt)==-EPERM && !reads && unmaps==1 && !mmus);
    setup();isolate_error=-EBUSY;assert(panthor_device_init_rmm_service(&pt)==-EBUSY && unmaps==1 && !mmus);
    for(unsigned int i=1;i<=2;i++){
        setup();bad_reply=i;assert(panthor_device_init_rmm_service(&pt)==-EPROTO && unmaps==1 && !mmus);
    }
    setup();mmu_error=-ENOMEM;assert(panthor_device_init_rmm_service(&pt)==-ENOMEM && !registrations && !pt.iomem);
    setup();register_error=-ENOMEM;assert(panthor_device_init_rmm_service(&pt)==-ENOMEM && registrations==1 && !pt.iomem);
    struct drm_panthor_csif_info info;
    setup();assert(!panthor_vmshm_rmm_csif_info(&info) && properties==3);
    assert(info.csg_slot_count==4 && info.cs_slot_count==8 && info.cs_reg_count==64 &&
        info.scoreboard_slot_count==8 && info.unpreserved_cs_reg_count==4 && !info.pad);
    for(unsigned int i=1;i<=3;i++){
        setup();property_fail_call=i;assert(panthor_vmshm_rmm_csif_info(&info)==-EACCES && properties==i);
    }
    setup();fw_state=5;assert(panthor_vmshm_rmm_csif_info(&info)==-EBUSY && properties==1);
    for(unsigned int i=0;i<7;i++){
        setup();
        if(i==0)group_count=0;
        if(i==1)group_count=32;
        if(i==2)stream_count=0;
        if(i==3)stream_count=33;
        if(i==4)stream_features=UINT64_C(1)<<32;
        if(i==5)stream_features=3;
        if(i==6)stream_features=63|(17<<8);
        assert(panthor_vmshm_rmm_csif_info(&info)==-EPROTO);
    }
    struct panthor_vmshm_dev_query_req req={.type=DRM_PANTHOR_DEV_QUERY_CSIF_INFO};
    struct panthor_vmshm_dev_query_rsp rsp;
    setup();assert(!panthor_vmshm_fill_dev_query(&pt,&req,&rsp) && !properties && rsp.size==sizeof(info));
    setup();req.flags=PANTHOR_VMSHM_DEV_QUERY_F_DATA;req.size=sizeof(info);
    pt.csif_info.cs_reg_count=1;
    assert(!panthor_vmshm_fill_dev_query(&pt,&req,&rsp) && properties==3 && rsp.data_len==sizeof(info));
    memcpy(&info,rsp.data,sizeof(info));assert(info.cs_reg_count==64 && pt.csif_info.cs_reg_count==1);
    setup();req.type=DRM_PANTHOR_DEV_QUERY_GPU_INFO;req.size=sizeof(pt.gpu_info);pt.gpu_info.gpu_id=42;
    assert(!panthor_vmshm_fill_dev_query(&pt,&req,&rsp) && !properties);
    struct drm_panthor_gpu_info gpu;memcpy(&gpu,rsp.data,sizeof(gpu));assert(gpu.gpu_id==42);
    setup();pt.rmm_service=false;pt.csif_info.cs_reg_count=32;req.type=DRM_PANTHOR_DEV_QUERY_CSIF_INFO;req.size=sizeof(info);
    assert(!panthor_vmshm_fill_dev_query(&pt,&req,&rsp) && !properties);memcpy(&info,rsp.data,sizeof(info));assert(info.cs_reg_count==32);
    setup();pt.rmm_service=false;pt.iomem=(void *)(uintptr_t)0x10000;
    assert(!panthor_mmu_init(&pt) && irq_lookups==1 && irq_requests==1 && workqueues==1);
    printf("GPU_RMM_SERVICE=PASS cases=%u actual service init/MMU/query functions; claim/read before handoff, unmap before metadata service, no rollback on failure, actual MMU init skips IRQ in service mode, no native firmware/scheduler calls, configured RMM CSIF only, invalid replies refused, shared IRQ/query retained; HOST_DOUBLES_ONLY\n",cases);
    return 0;
}
