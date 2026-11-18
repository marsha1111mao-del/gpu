// SPDX-License-Identifier: GPL-2.0-only
/* Actual Proxy handler lookup/dispatch over a generated full handler table. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint32_t u32;
typedef uint64_t u64;

#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))

struct vmshm_comm_rx {
	u32 type;
	u32 flags;
	u64 seq, reply_to;
	long status;
	const void *payload;
	u32 payload_capacity, len;
	void *proxy_channel;
};

struct panthor_proxy_msg_handler {
	u32 req_type;
	u32 rsp_type;
	u32 req_size;
	const char *name;
	void (*handler)(void *channel, const struct vmshm_comm_rx *rx,
			const void *payload);
};

struct dispatched_request { unsigned char bytes[64]; };

static unsigned int bad_rx, unknown_type, bad_len, enabled_calls, handler_calls;
static u64 now;
static const void *last_payload;

static void panthor_proxy_rpc_stats_record_bad_rx(void) { bad_rx++; }
static void panthor_proxy_rpc_stats_record_unknown_type(void) { unknown_type++; }
static void panthor_proxy_rpc_stats_record_bad_len(void) { bad_len++; }
static bool panthor_proxy_rpc_stats_is_enabled(void) { return handler_calls < 2; }
static u64 ktime_get_ns(void) { return ++now; }
static void panthor_proxy_rpc_stats_record_op(u32 index, u64 elapsed)
{
	(void)index;
	(void)elapsed;
	enabled_calls++;
}

static u32 panthor_proxy_handler_index(const struct panthor_proxy_msg_handler *handler)
{
	(void)handler;
	return 0U;
}

static void observed_handler(void *channel, const struct vmshm_comm_rx *rx,
			     const void *payload)
{
	(void)channel;
	assert(rx && payload == rx->payload);
	last_payload = payload;
	handler_calls++;
}

#include "table.inc"
#include "actual.inc"

int main(void)
{
	struct dispatched_request request;
	unsigned int types = 0;

	memset(&request, 0xa5, sizeof(request));
	assert(panthor_proxy_handlers_count >= 12U);
	for (u32 i = 0; i < panthor_proxy_handlers_count; i++) {
		const struct panthor_proxy_msg_handler *handler = &panthor_proxy_handlers[i];
		struct vmshm_comm_rx rx = {
			.type = handler->req_type,
			.payload = request.bytes,
			.payload_capacity = sizeof(request),
			.len = sizeof(request),
		};

		assert(handler->req_type && handler->rsp_type &&
		       handler->req_size == sizeof(request) && handler->handler);
		assert(panthor_proxy_find_handler(handler->rsp_type) == NULL);

		rx.len--;
		assert(panthor_proxy_rx_handler(&rx, NULL) == -EPROTO &&
		       handler_calls == types && bad_len > types);
		rx.len += 2;
		assert(panthor_proxy_rx_handler(&rx, NULL) == -EPROTO &&
		       handler_calls == types && bad_len > types + 1U);
		rx.len--;
		assert(panthor_proxy_rx_handler(&rx, NULL) == 0);
		types++;
		assert(handler_calls == types && last_payload == request.bytes);
	}

	struct vmshm_comm_rx unknown = {
		.type = 0xffffffffU,
		.payload = request.bytes,
		.payload_capacity = sizeof(request),
		.len = sizeof(request),
	};
	assert(panthor_proxy_rx_handler(&unknown, NULL) == -ENOENT &&
	       handler_calls == types && unknown_type == 1U);
	assert(panthor_proxy_rx_handler(NULL, NULL) == -EPROTO && bad_rx == 1U);
	assert(panthor_proxy_rx_handler(&(struct vmshm_comm_rx){0}, NULL) == -ENOENT);

	printf("PROXY_HANDLER_DISPATCH=PASS handlers=%u exact_length_and_direction_enforced\n",
	       panthor_proxy_handlers_count);
	return 0;
}
