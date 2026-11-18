// SPDX-License-Identifier: GPL-2.0-only
/* Actual RMM bridge + Monitor/consumer cores. Transport/cache/GIC are doubles. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <opencca_gpu_irq.h>
#include <opencca_gpu_irq_monitor.h>

static unsigned char shared[4096];
static bool locked;
static unsigned long requests;
static struct ogi_monitor monitor;
static bool fault_on_start;

uintptr_t rmm_el3_ifc_get_shared_buf_locked(void)
{ assert(!locked);locked=true;return (uintptr_t)shared; }
uintptr_t rmm_el3_ifc_get_shared_buf_pa(void) { return (uintptr_t)shared; }
void rmm_el3_ifc_release_shared_buf(void) { assert(locked);locked=false; }

unsigned long monitor_call(unsigned long id, unsigned long command,
		unsigned long pa, unsigned long bytes, unsigned long a,
		unsigned long b, unsigned long c)
{
	struct ogi_mailbox *m=(void *)shared;
	assert(locked && id==0xc40001ccUL && pa==(uintptr_t)shared &&
		bytes==sizeof(*m) && !(a|b|c) && m->abi==OGI_ABI && m->command==command);
	requests++;
	unsigned int status=OGI_INPUT;
	switch(command) {
	case OGI_START:
		status=ogi_monitor_start(&monitor,m->snapshot.flags==OGI_SOURCE_SIMULATION);
		if (status==OGI_OK && fault_on_start) {
			struct ogi_snapshot fault={.intid=OGI_GPU_INTID,.cpu=0,
				.flags=OGI_SOURCE_ROOT_SAMPLE,.gpu_raw=1};
			assert(ogi_monitor_capture(&monitor,&fault)==OGI_OK);
		}
		break;
	case OGI_STOP:ogi_monitor_stop(&monitor);status=OGI_OK;break;
	case OGI_BIND:status=ogi_monitor_bind(&monitor,&m->binding);break;
	case OGI_UNBIND:status=ogi_monitor_unbind(&monitor,&m->binding);break;
	case OGI_DRAIN:case OGI_DRAIN_QUIET:
		status=ogi_monitor_drain(&monitor,m->acknowledge,m->records,&m->count);break;
	case OGI_SIM_CAPTURE:
		assert(monitor.stats.simulation);
		status=ogi_monitor_capture(&monitor,&m->snapshot);break;
	case OGI_STATS:status=OGI_OK;break;
	}
	m->stats=monitor.stats;m->status=status;
	return status;
}

int main(void)
{
	static unsigned int owner;
	unsigned long values[4], event[4];
	uint64_t epoch;
	assert(opencca_gpu_irq_start());
	assert(opencca_gpu_irq_selftest(&owner,101,201,values));
	assert(values[0]>=150 && values[1]>=131 && values[2]>1 && values[3]==0);
	assert(!locked && monitor.stats.active && !monitor.stats.simulation && !monitor.stats.lost);
	assert(opencca_gpu_irq_bind(&owner,101,201,0,1,&epoch));
	uint64_t before=monitor.stats.device_epoch;
	assert(!opencca_gpu_irq_selftest(&owner,101,201,values));
	assert(monitor.stats.device_epoch==before);
	struct ogi_snapshot snapshot={.intid=OGI_JOB_INTID,.cpu=1,
		.flags=OGI_SOURCE_ROOT_SAMPLE,.job_raw=1};
	assert(ogi_monitor_capture(&monitor,&snapshot)==OGI_OK);
	assert(opencca_gpu_irq_next(0,epoch,0,event)==OGI_OK);
	assert(event[2]==OGI_SOURCE_ROOT_SAMPLE);
	assert(opencca_gpu_irq_claim(0,epoch,0,event[0]+1,epoch,event[3],OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(opencca_gpu_irq_claim(0,epoch,0,event[0],epoch,event[3],OGI_CLAIM_PROGRESS,false)==OGI_OK);
	assert(opencca_gpu_irq_claim(0,epoch,0,event[0],epoch,event[3],OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(opencca_gpu_irq_close(0,epoch));
	assert(opencca_gpu_irq_status(1,values) && values[0]==1 && values[1]>=2 && !values[3]);
	opencca_gpu_irq_revoke();assert(!monitor.stats.active && !locked);
	fault_on_start=true;
	assert(!opencca_gpu_irq_start());
	assert(opencca_gpu_irq_status(1,values) && values[3]);
	opencca_gpu_irq_revoke();assert(!monitor.stats.active && !locked);
	printf("GPU_IRQ_ADAPTER=PASS requests=%lu actual_RMM_bridge_Monitor_consumer TRANSPORT_CACHE_GIC_DOUBLES_ONLY\n",requests);
	return 0;
}
