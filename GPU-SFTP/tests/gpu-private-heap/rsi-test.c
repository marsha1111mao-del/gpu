/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual RSI adapter, synthetic REC/channel and firmware-call boundaries. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "opencca_gpu_firmware.h"

struct rec { struct { const void *g_rd; } realm_info; unsigned long regs[8]; };
static int client_a, client_b, service;
static bool isolated = true, disconnected;
static unsigned int calls;
static const struct gpu_firmware_ops firmware_operations;
static const struct gpu_private_ops operations;
static const void *xshm_endpoint_peer(const void *owner, unsigned long channel, unsigned long *peer)
{
	if (disconnected || channel != 7UL)
		return NULL;
	*peer = 123UL;
	return owner == &service ? &client_a : &service;
}
static bool opencca_gpu_service_isolated(const void *owner)
{ return owner == &service && isolated; }
void gpu_firmware_task_heap_event(const struct gpu_firmware_ops *f,
		const struct gpu_private_ops *m, const void *s, const void *o,
		unsigned long task, struct gpu_private_result *r)
{
	calls++;
	assert(f == &firmware_operations && m == &operations && s == &service);
	/* The real firmware core checks this binding; here the stub verifies
	 * that the adapter passes the actual RD, not the peer ID or payload.
	 */
	if (o == &client_a && task == 55UL) {
		r->status = GPU_PRIVATE_SUCCESS;
		r->value[0] = 99UL;
	}
}
void gpu_firmware_task_heap_grow(const struct gpu_firmware_ops *f,
		const struct gpu_private_ops *m, const void *s, const void *o,
		unsigned long task, unsigned long event, unsigned long bo,
		unsigned long va, struct gpu_private_result *r)
{
	gpu_firmware_task_heap_event(f, m, s, o, task, r);
	if (event != 99UL || !((bo == 88UL && va == 0x80000000UL) || (!bo && !va)))
		r->status = GPU_PRIVATE_INPUT;
}
#include "rsi.inc"
int main(void)
{
	for (unsigned int scenario = 0U; scenario < 13U; scenario++) {
		struct rec rec = { .realm_info = { &client_a },
			.regs = { 0, GPU_PRIVATE_TASK_HEAP_EVENT, 55, 7 } };
		struct gpu_private_result r = { .status = GPU_PRIVATE_INPUT };
		bool expect_call = scenario == 0U || scenario == 6U || scenario == 7U ||
			scenario == 8U || scenario == 12U;
		calls = 0U;
		isolated = scenario != 4U;
		disconnected = scenario == 5U;
		if (scenario == 1U) rec.regs[7] = 1UL;
		if (scenario == 2U) rec.regs[4] = 99UL;
		if (scenario == 3U) rec.regs[3] = 8UL;
		if (scenario == 6U) rec.realm_info.g_rd = &client_b;
		if (scenario == 7U || scenario == 8U || scenario == 9U || scenario == 12U) {
			rec.regs[1] = GPU_PRIVATE_TASK_HEAP_GROW;
			rec.regs[4] = scenario == 12U ? 100UL : 99UL;
			if (scenario != 8U) rec.regs[5] = 88UL, rec.regs[6] = 0x80000000UL;
		}
		if (scenario == 9U) rec.regs[7] = 1UL;
		if (scenario == 10U) rec.realm_info.g_rd = &service;
		if (scenario == 11U) rec.regs[1] = GPU_PRIVATE_TASK_PUBLISH;
		task_heap_call(&rec, &r);
		assert(calls == (unsigned int)expect_call);
		assert(r.status == ((scenario == 0U || scenario == 7U || scenario == 8U) ?
			GPU_PRIVATE_SUCCESS : GPU_PRIVATE_INPUT));
		printf("GPU_PRIVATE_HEAP_RSI=PASS scenario=%u ADAPTER_DOUBLES_ONLY\n", scenario);
	}
	return 0;
}
