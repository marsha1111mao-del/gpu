/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual Client vmshm queue send/recv validators over an untrusted window. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#define u8 uint8_t
#define u16 uint16_t
#define u32 uint32_t
#define u64 uint64_t
#define s16 int16_t
#define s32 int32_t
#define barrier() __asm__ __volatile__("" ::: "memory")
#define READ_ONCE(value) (value)
#define WRITE_ONCE(target, value) ((target) = (value))
#define smp_load_acquire(target) (*(target))
#define smp_store_release(target, value) (*(target) = (value))
#define smp_wmb() barrier()
#define __aligned(alignment) __attribute__((aligned(alignment)))

struct vmshm_comm_tx {
	u32 type, flags;
	u64 seq, reply_to;
	s32 status;
	const void *payload;
	u32 len;
};

struct vmshm_comm_rx {
	u32 type, flags;
	u64 seq, reply_to;
	s32 status;
	void *payload;
	u32 payload_capacity, len;
	void *proxy_channel;
};

#include <linux/vmshm_comm_protocol.h>

struct client_comm_vmshm_dev {
	void *base;
	u32 size;
	struct proxy_comm_vmshm_queue_object queues[PROXY_COMM_VMSHM_MAX_QUEUES];
	u32 tx_avail[PROXY_COMM_VMSHM_MAX_QUEUES];
	u32 tx_used[PROXY_COMM_VMSHM_MAX_QUEUES];
	u32 rx_used[PROXY_COMM_VMSHM_MAX_QUEUES];
};

#include "actual.inc"

static unsigned char window[4096];
static unsigned char receive_payload[PROXY_COMM_VMSHM_MSG_SIZE];
static struct client_comm_vmshm_dev device;
static unsigned int cases;

static void reset_window(void)
{
	memset(window, 0xa5, sizeof(window));
	memset(&device, 0, sizeof(device));
	device.base = window;
	device.size = sizeof(window);
	device.queues[PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT] = (struct proxy_comm_vmshm_queue_object){
		.magic = PROXY_COMM_VMSHM_QUEUE_MAGIC,
		.queue_id = PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT,
		.direction = 1,
		.queue_size = 4,
		.queue_mask = 3,
		.msg_size = PROXY_COMM_VMSHM_MSG_SIZE,
		.desc_off = 0,
		.avail_off = 128,
		.used_off = 192,
		.msg_pool_off = 512,
	};
	device.queues[PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY] = device.queues[PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT];
	device.queues[PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY].queue_id = PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY;
	device.queues[PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY].direction = 0;
	memset(window + 128, 0, 128);
}

static struct proxy_comm_vmshm_desc *descriptors(void)
{
	return (struct proxy_comm_vmshm_desc *)window;
}

static struct proxy_comm_vmshm_avail_ring *available(void)
{
	return (struct proxy_comm_vmshm_avail_ring *)(window + 128);
}

static struct proxy_comm_vmshm_used_ring *used(void)
{
	return (struct proxy_comm_vmshm_used_ring *)(window + 192);
}

static struct proxy_comm_vmshm_msg *message(unsigned int descriptor)
{
	return (struct proxy_comm_vmshm_msg *)(window + 512 + descriptor * PROXY_COMM_VMSHM_MSG_SIZE);
}

static void publish(unsigned int descriptor, u32 payload_length, u32 descriptor_length)
{
	struct proxy_comm_vmshm_msg *entry = message(descriptor);
	memset(entry, 0, PROXY_COMM_VMSHM_MSG_SIZE);
	entry->type = 0x54535251U;
	entry->flags = 0x13579bdfU;
	entry->len = payload_length;
	entry->status = -7;
	entry->seq = 91;
	entry->reply_to = 17;
	entry->reserved = 0;
	for (u32 index = 0; index < payload_length && index < 472; index++)
		entry->payload[index] = (unsigned char)(index + 1);
	descriptors()[descriptor] = (struct proxy_comm_vmshm_desc){
		.msg_off = 512 + descriptor * PROXY_COMM_VMSHM_MSG_SIZE,
		.msg_capacity = PROXY_COMM_VMSHM_MSG_SIZE,
		.msg_len = descriptor_length,
		.seq = 91,
	};
	available()->idx = 1;
	available()->ring[0] = (u16)descriptor;
}

static struct vmshm_comm_rx receive_request(void)
{
	return (struct vmshm_comm_rx){
		.payload = receive_payload,
		.payload_capacity = sizeof(receive_payload),
	};
}

static void test_receive(void)
{
	struct vmshm_comm_rx rx;

	reset_window();
	publish(0, 12, sizeof(struct proxy_comm_vmshm_msg) + 12);
	rx = receive_request();
	assert(!client_comm_vmshm_queue_recv(&device, PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT, &rx));
	assert(rx.type == 0x54535251U && rx.flags == 0x13579bdfU);
	assert(rx.seq == 91 && rx.reply_to == 17 && rx.status == -7 && rx.len == 12);
	assert(!memcmp(rx.payload, message(0)->payload, 12));
	assert(device.rx_used[1] == 1 && used()->idx == 1);
	assert(used()->ring[0].desc_id == 0 && used()->ring[0].status == 0);
	assert(used()->ring[0].len == sizeof(struct proxy_comm_vmshm_msg) + 12);
	cases++;

	reset_window();
	device.rx_used[1] = 1;
	available()->idx = 0;
	rx = receive_request();
	assert(client_comm_vmshm_queue_recv(&device, PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT, &rx) == -EPROTO);
	assert(device.rx_used[1] == 1 && used()->idx == 0 && rx.len == 0);
	cases++;

	reset_window();
	available()->idx = 5;
	rx = receive_request();
	assert(client_comm_vmshm_queue_recv(&device, PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT, &rx) == -EPROTO);
	assert(device.rx_used[1] == 0 && used()->idx == 0);
	cases++;

	publish(0, 12, sizeof(struct proxy_comm_vmshm_msg) + 12);
	available()->ring[0] = 4;
	rx = receive_request();
	assert(client_comm_vmshm_queue_recv(&device, PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT, &rx) == -EINVAL);
	assert(device.rx_used[1] == 1 && used()->idx == 1 && used()->ring[0].status == -EINVAL);
	assert(used()->ring[0].len == 0 && rx.len == 0);
	cases++;

	const struct { u32 offset, capacity, length; u32 payload_length; } malformed[] = {
		{513, 512, 52, 12}, {512, 511, 52, 12},
		{512, 512, 39, 12}, {512, 512, 513, 12},
		{512, 512, 52, 473}, {512, 512, 53, 12},
	};
	for (size_t index = 0; index < sizeof(malformed) / sizeof(malformed[0]); index++) {
		reset_window();
		publish(0, malformed[index].payload_length,
			sizeof(struct proxy_comm_vmshm_msg) + malformed[index].payload_length);
		descriptors()[0].msg_off = malformed[index].offset;
		descriptors()[0].msg_capacity = malformed[index].capacity;
		descriptors()[0].msg_len = malformed[index].length;
		rx = receive_request();
		assert(client_comm_vmshm_queue_recv(&device, PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT, &rx) == -EINVAL);
		assert(device.rx_used[1] == 1 && used()->ring[0].status == -EINVAL && rx.len == 0);
		cases++;
	}

	reset_window();
	publish(0, 16, sizeof(struct proxy_comm_vmshm_msg) + 16);
	rx = receive_request();
	rx.payload_capacity = 8;
	assert(client_comm_vmshm_queue_recv(&device, PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT, &rx) == -EMSGSIZE);
	assert(device.rx_used[1] == 1 && used()->ring[0].status == -EMSGSIZE && rx.len == 0);
	cases++;
}

static void test_send(void)
{
	const unsigned char payload[12] = "queue-input";
	struct vmshm_comm_tx request = {
		.type = 0x54535152U,
		.flags = 0x2468ace0U,
		.seq = 37,
		.payload = payload,
		.len = sizeof(payload),
	};
	unsigned char before[sizeof(window)];

	reset_window();
	device.tx_avail[0] = 4;
	device.tx_used[0] = 0;
	used()->idx = 0;
	memcpy(before, window, sizeof(window));
	assert(client_comm_vmshm_queue_send(&device, PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY, &request) == -EAGAIN);
	assert(!memcmp(window, before, sizeof(window)) && device.tx_avail[0] == 4);
	cases++;

	used()->idx = 5;
	memcpy(before, window, sizeof(window));
	assert(client_comm_vmshm_queue_send(&device, PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY, &request) == -EPROTO);
	assert(!memcmp(window, before, sizeof(window)) && device.tx_avail[0] == 4);
	cases++;

	used()->idx = 1;
	assert(!client_comm_vmshm_queue_send(&device, PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY, &request));
	assert(device.tx_avail[0] == 5 && available()->idx == 5 && available()->ring[0] == 0);
	assert(descriptors()[0].msg_len == sizeof(struct proxy_comm_vmshm_msg) + sizeof(payload));
	assert(message(0)->type == request.type && message(0)->len == request.len);
	assert(!memcmp(message(0)->payload, payload, sizeof(payload)));
	cases++;

	request.len = PROXY_COMM_VMSHM_MSG_SIZE;
	assert(client_comm_vmshm_queue_send(&device, PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY, &request) == -EMSGSIZE);
	cases++;
}

int main(void)
{
	test_receive();
	test_send();
	printf("XSHM_QUEUE_INTEGRITY=PASS cases=%u actual send/recv validators; rollback, overflow, forged descriptor, mismatch and full-window rejection; MODEL_ONLY\n", cases);
	return 0;
}
