// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <opencca_gpu_irq_monitor.h>
#include <opencca_gpu_irq_consumer.h>

static struct ogi_monitor monitor;
static struct ogi_consumer consumer;
static struct ogi_binding a, b;
static struct ogi_record batch[OGI_BATCH];

static void start(void)
{
	ogi_monitor_stop(&monitor);
	assert(ogi_monitor_start(&monitor, true) == OGI_OK);
	ogi_consumer_start(&consumer, monitor.stats.device_epoch,
		monitor.stats.consumed, true);
	a = (struct ogi_binding){.owner=1, .context=101, .group=201, .csg=0, .as=1};
	b = (struct ogi_binding){.owner=2, .context=102, .group=202, .csg=1, .as=2};
	assert(ogi_monitor_bind(&monitor, &a) == OGI_OK);
	assert(ogi_consumer_bind(&consumer, &a) == OGI_OK);
	assert(ogi_monitor_bind(&monitor, &b) == OGI_OK);
	assert(ogi_consumer_bind(&consumer, &b) == OGI_OK);
}

static void capture(unsigned int job, unsigned int mmu)
{
	struct ogi_snapshot s = {.intid=OGI_JOB_INTID, .cpu=2,
		.flags=OGI_SOURCE_SIMULATION, .job_raw=job, .mmu_raw=mmu,
		.timestamp=1234};
	s.fault_status[1] = 0x42;
	s.fault_address[1] = 0x80001234;
	assert(ogi_monitor_capture(&monitor, &s) == OGI_OK);
}

static unsigned int read_batch(void)
{
	unsigned int count;
	assert(ogi_monitor_drain(&monitor, monitor.stats.consumed, batch, &count) == OGI_OK);
	return count;
}

static void transfer(void)
{
	unsigned int count = read_batch();
	for (unsigned int i=0; i<count; i++)
		assert(ogi_consumer_ingest(&consumer, &batch[i]) == OGI_OK);
	unsigned int next;
	unsigned int status = ogi_monitor_drain(&monitor, batch[count-1].sequence,
		batch, &next);
	assert(status == OGI_EMPTY && next == 0);
}

int main(void)
{
	struct ogi_record r, tampered;
	unsigned int count;
	start();
	capture(1U,0);
	uint64_t sequence=monitor.stats.produced;
	/* No acknowledged position may be fabricated before a read offer. */
	assert(ogi_monitor_drain(&monitor,sequence,batch,&count)==OGI_STALE);
	transfer();
	assert(ogi_consumer_next(&consumer,&a,0,&r)==OGI_OK);
	assert(r.owner==a.owner && r.context==a.context && r.group==a.group &&
		r.binding_epoch==a.epoch && r.cpu==2 && r.flags==OGI_SOURCE_SIMULATION);
	assert(ogi_consumer_next(&consumer,&b,0,&tampered)==OGI_EMPTY);
	assert(ogi_consumer_claim(&consumer,&b,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence+1,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch+1,
		r.device_epoch,OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch+1,OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_COMPLETE,false)==OGI_STATE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_COMPLETE,true)==OGI_OK);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_COMPLETE,true)==OGI_STALE);
	puts("GPU_IRQ_PROTOCOL_CASE=PASS owner/future/epoch/complete/replay");

	/* One physical/global event may concern multiple bindings. Ordering and
	 * partial queue progress never become one-IRQ/one-Job completion proof.
	 */
	capture(1U<<31U,0);transfer();
	assert(ogi_consumer_next(&consumer,&a,0,&r)==OGI_OK);
	assert(ogi_consumer_next(&consumer,&b,0,&tampered)==OGI_OK);
	assert(r.sequence!=tampered.sequence && r.owner!=tampered.owner);
	puts("GPU_IRQ_PROTOCOL_CASE=PASS multi-context-records");

	start();capture(1U,0);transfer();
	assert(ogi_consumer_next(&consumer,&a,0,&r)==OGI_OK);
	capture(1U,0);transfer();
	assert(consumer.coalesced==1);
	assert(ogi_consumer_next(&consumer,&a,0,&tampered)==OGI_OK && tampered.sequence==r.sequence);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_PROGRESS,false)==OGI_OK);
	puts("GPU_IRQ_PROTOCOL_CASE=PASS progress-coalescing-retains-first-reference");

	start();capture(1U,1U<<1U);transfer();
	assert(!ogi_consumer_healthy(&consumer,&a));
	assert(ogi_consumer_healthy(&consumer,&b));
	assert(ogi_consumer_next(&consumer,&a,0,&r)==OGI_OK);
	assert(r.fault_status==0x42 && r.fault_address==0x80001234);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_COMPLETE,true)==OGI_STALE);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_FAULT,false)==OGI_OK);
	assert(!ogi_consumer_healthy(&consumer,&a));
	puts("GPU_IRQ_PROTOCOL_CASE=PASS latched-fault-no-washout");

	start();capture(1U,0);count=read_batch();assert(count==1);
	tampered=batch[0];tampered.sequence++;
	assert(ogi_consumer_ingest(&consumer,&tampered)==OGI_LOST);
	assert(!ogi_consumer_healthy(&consumer,&a));
	start();capture(1U,0);count=read_batch();
	tampered=batch[0];tampered.flags=OGI_SOURCE_EL3_IRQ;
	assert(ogi_consumer_ingest(&consumer,&tampered)==OGI_LOST);
	start();capture(1U,1U<<1U);count=read_batch();
	tampered=batch[0];tampered.flags&=~OGI_EVENT_FAULT;
	assert(ogi_consumer_ingest(&consumer,&tampered)==OGI_LOST);
	puts("GPU_IRQ_PROTOCOL_CASE=PASS source/gap/hidden-fault");

	start();capture(1U,0);count=read_batch();r=batch[0];transfer();
	assert(ogi_monitor_unbind(&monitor,&a)==OGI_OK);
	assert(ogi_consumer_close(&consumer,&a)==OGI_OK);
	uint64_t old=a.epoch;
	a.owner=3;a.context=103;a.group=203;a.epoch=0;
	assert(ogi_monitor_bind(&monitor,&a)==OGI_OK && a.epoch>old);
	assert(ogi_consumer_bind(&consumer,&a)==OGI_OK);
	assert(ogi_consumer_claim(&consumer,&a,0,r.sequence,r.binding_epoch,
		r.device_epoch,OGI_CLAIM_PROGRESS,false)==OGI_STALE);
	puts("GPU_IRQ_PROTOCOL_CASE=PASS old-binding-slot-reuse");

	start();
	for (unsigned int i=0;i<OGI_CAPACITY;i++)capture(1U,0);
	struct ogi_record first=monitor.records[monitor.stats.consumed%OGI_CAPACITY];
	struct ogi_snapshot overflow={.intid=OGI_JOB_INTID,.cpu=0,
		.flags=OGI_SOURCE_SIMULATION,.job_raw=1U};
	assert(ogi_monitor_capture(&monitor,&overflow)==OGI_LOST);
	assert(monitor.stats.lost && monitor.stats.queued==OGI_CAPACITY);
	assert(!memcmp(&first,&monitor.records[monitor.stats.consumed%OGI_CAPACITY],sizeof(first)));
	assert(ogi_monitor_drain(&monitor,monitor.stats.consumed,batch,&count)==OGI_LOST);
	assert(ogi_monitor_unbind(&monitor,&a)==OGI_LOST);
	puts("GPU_IRQ_PROTOCOL_CASE=PASS overflow-retains-unconsumed-history");
	puts("GPU_IRQ_PROTOCOL=PASS actual_monitor_consumer_serialized MODEL_MMIO_GIC_TRANSPORT");
	return 0;
}
