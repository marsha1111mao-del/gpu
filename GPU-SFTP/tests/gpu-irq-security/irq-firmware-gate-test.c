// SPDX-License-Identifier: GPL-2.0-only
/* White-box setup of stale metadata; actual FW claim entry/observer execute.
 * It must revalidate hardware even with an old cached completed flag.
 */
#include <assert.h>
#include <stdio.h>
#include <opencca_gpu_irq_consumer.h>
#include "firmware.c"

static struct ogi_consumer events;
static struct ogi_binding binding;
static unsigned int hardware_calls;
static void next_event(unsigned int csg, uint64_t epoch, uint64_t after,
		struct gpu_private_result *r)
{
	struct ogi_record event;
	assert(csg==0 && epoch==binding.epoch);
	memset(r,0,sizeof(*r));
	unsigned int status=ogi_consumer_next(&events,&binding,after,&event);
	r->status=status==OGI_OK?GPU_PRIVATE_SUCCESS:GPU_PRIVATE_INCOMPLETE;
	if(status==OGI_OK) {
		r->value[0]=event.sequence;r->value[1]=event.binding_epoch;
		r->value[2]=event.flags;r->value[3]=event.device_epoch;
	}
}
static void claim_event(unsigned int csg, uint64_t epoch, uint64_t after,
		uint64_t sequence,uint64_t record_epoch,uint64_t device_epoch,
		unsigned int kind,bool complete,struct gpu_private_result *r)
{
	assert(csg==0 && epoch==binding.epoch);
	memset(r,0,sizeof(*r));
	r->status=ogi_consumer_claim(&events,&binding,after,sequence,record_epoch,
		device_epoch,kind,complete)==OGI_OK?GPU_PRIVATE_SUCCESS:GPU_PRIVATE_INPUT;
}
static bool sync_events(unsigned int csg,uint64_t epoch,uint64_t *seq)
{ assert(csg==0 && epoch==binding.epoch);if(seq)*seq=events.received;return ogi_consumer_healthy(&events,&binding); }
static unsigned long address(const void *memory) { (void)memory;hardware_calls++;return 0; }
static bool config(unsigned long root,struct gpu_firmware_config *c)
{ (void)root;(void)c;hardware_calls++;return false; }
static void cache(const void *p,size_t n) { (void)p;(void)n; }
static bool notify(unsigned long root) { (void)root;hardware_calls++;return false; }
static unsigned long clock_now(void) { return 1; }
static bool read_page(unsigned long p,size_t offset,void *to,size_t bytes)
{ (void)p;(void)offset;(void)to;(void)bytes;return false; }
static bool detach(unsigned long p,unsigned int slot,unsigned long root,bool done)
{ (void)p;(void)slot;(void)root;(void)done;return false; }

int main(void)
{
	static unsigned int owner,service;
	unsigned long group=GROUP_PREFIX|(1UL<<16)|1UL;
	unsigned long token=TASK_PREFIX|(1UL<<16)|1UL;
	image_service=&service;state=GPU_FIRMWARE_CONFIGURED;
	interfaces.groups=interfaces.streams=1;
	groups[0]=(struct fw_group){.owner=&owner,.handle=group,.context=101,
		.prepared_task=token,.streams=1,.hardware_csg=0,.hardware_as=1,
		.irq_epoch=3,.state=GPU_FIRMWARE_GROUP_STARTED};
	hardware_groups[0]=group;
	tasks[0]=(struct fw_task){.owner=&owner,.handle=token,.ready=true,.started=true,
		.start_attempted=true,.completed=true,.count=1,.irq_publication=true,
		.resources={.context=101,.group=group}};
	ogi_consumer_start(&events,2,0,true);
	binding=(struct ogi_binding){.owner=(uintptr_t)&owner,.context=101,.group=group,
		.epoch=3,.csg=0,.as=1};
	assert(ogi_consumer_bind(&events,&binding)==OGI_OK);
	struct ogi_record r={.sequence=1,.device_epoch=2,.binding_epoch=3,
		.owner=(uintptr_t)&owner,.context=101,.group=group,.intid=OGI_JOB_INTID,
		.flags=OGI_SOURCE_SIMULATION,.csg=0,.as=1,.job_raw=1};
	assert(ogi_consumer_ingest(&events,&r)==OGI_OK);
	struct gpu_firmware_irq_ops irq={.next=next_event,.claim=claim_event,.sync=sync_events};
	struct gpu_firmware_ops ops={.address=address,.configuration=config,
		.clean=cache,.invalidate=cache,.notify=notify,.clock=clock_now,.irq=&irq};
	struct gpu_private_ops memory={.read_page=read_page,.detach_as=detach};
	struct gpu_private_result result;
	gpu_firmware_group_irq_claim(&ops,&service,&owner,group,1,3,
		GPU_PRIVATE_IRQ_COMPLETE,2,&result);
	assert(result.status==GPU_PRIVATE_INPUT && hardware_calls==0 && events.claimed==0);
	static unsigned int foreign;
	gpu_firmware_group_irq_peek(&ops,&service,&foreign,group,&result);
	assert(result.status==GPU_PRIVATE_INPUT && hardware_calls==0);
	gpu_firmware_group_irq_peek(&ops,&service,&owner,group,&result);
	assert(result.status==GPU_PRIVATE_SUCCESS && result.value[0]==1 &&
		result.value[1]==3 && result.value[3]==2);
	gpu_firmware_task_irq_claim(&ops,&memory,&service,&owner,token,2,3,
		GPU_PRIVATE_IRQ_COMPLETE,2,&result);
	assert(result.status!=GPU_PRIVATE_SUCCESS && hardware_calls==0 &&
		tasks[0].observation_count==0 && events.claimed==0);
	/* The cached completed bit must not authorize a valid event if current
	 * hardware/configuration/context checks cannot establish completion.
	 */
	gpu_firmware_task_irq_claim(&ops,&memory,&service,&owner,token,1,3,
		GPU_PRIVATE_IRQ_COMPLETE,2,&result);
	assert(result.status!=GPU_PRIVATE_SUCCESS && events.claimed==0 &&
		tasks[0].observation_count==1 && tasks[0].observation_error!=0);
	/* The Monitor has already recorded the fault before its device bit is
	 * cleared. A later ordinary FINISH must see the protected consumer latch,
	 * even though the current hardware double would otherwise look clean.
	 */
	struct ogi_record fault=r;
	fault.sequence=2;fault.flags|=OGI_EVENT_FAULT;fault.mmu_raw=1U<<1U;
	assert(ogi_consumer_ingest(&events,&fault)==OGI_OK);
	tasks[0].observation_count=tasks[0].observation_error=0;
	groups[0].state=GPU_FIRMWARE_GROUP_STARTED;
	unsigned int before=hardware_calls;
	gpu_firmware_task_complete(&ops,&memory,&service,&owner,token,&result);
	assert(result.status!=GPU_PRIVATE_SUCCESS && events.claimed==0 &&
		hardware_calls==before && tasks[0].observation_error==7);
	events.faulted[0]=false;events.global_fault=false;events.lost=true;
	tasks[0].observation_count=tasks[0].observation_error=0;
	groups[0].state=GPU_FIRMWARE_GROUP_STARTED;
	gpu_firmware_task_complete(&ops,&memory,&service,&owner,token,&result);
	assert(result.status!=GPU_PRIVATE_SUCCESS && hardware_calls==before &&
		tasks[0].observation_error==7);
	puts("GPU_IRQ_FW_GATE=PASS invalid_reference_has_no_status_MMIO stale_completed_needs_fresh_device_evidence MODEL_ONLY");
	puts("GPU_IRQ_FW_HISTORY=PASS Monitor_fault_and_history_loss_block_FINISH_before_device_callbacks MODEL_ONLY");
	return 0;
}
