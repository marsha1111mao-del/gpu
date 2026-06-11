// SPDX-License-Identifier: MIT
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/ioctl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define CLIENT_COMM_VMSHM_IOC_MAGIC 'C'

#define PROXY_COMM_VMSHM_MAGIC 0x56534350U
#define PROXY_COMM_VMSHM_VERSION 1
#define PROXY_COMM_VMSHM_MAX_QUEUES 2
#define PROXY_COMM_VMSHM_QUEUE_MAGIC 0x51564350U
#define PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY 0
#define PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT 1

#define PANTHOR_VMSHM_MSG_CLOSE_SESSION_REQ 0x50544352U
#define PANTHOR_VMSHM_MSG_CLOSE_SESSION_RSP 0x50544353U
#define PANTHOR_VMSHM_MSG_DEV_QUERY_REQ 0x50545152U
#define PANTHOR_VMSHM_MSG_DEV_QUERY_RSP 0x50545153U

#define DRM_IOCTL_BASE 'd'
#define DRM_COMMAND_BASE 0x40
#define DRM_IOWR(nr, type) _IOWR(DRM_IOCTL_BASE, nr, type)
#define DRM_IOCTL_PANTHOR_DEV_QUERY \
	DRM_IOWR(DRM_COMMAND_BASE + 0, struct drm_panthor_dev_query)

#define DRM_PANTHOR_DEV_QUERY_GPU_INFO 0

#define DEFAULT_TIMEOUT_MS 1500
#define POLL_SLEEP_US 1000

struct proxy_comm_vmshm_queue {
	uint32_t queue_obj_id;
	uint32_t desc_obj_id;
	uint32_t avail_obj_id;
	uint32_t used_obj_id;
	uint32_t msg_pool_obj_id;
	uint32_t queue_off;
	uint32_t size;
	uint32_t msg_size;
	uint32_t desc_off;
	uint32_t avail_off;
	uint32_t used_off;
	uint32_t msg_pool_off;
	uint32_t direction;
	uint32_t flags;
	uint32_t reserved;
};

struct proxy_comm_vmshm_header {
	uint32_t magic;
	uint32_t version;
	uint32_t header_size;
	uint32_t total_size;
	uint32_t generation;
	uint32_t status[2];
	uint32_t heap_base_off;
	uint32_t heap_size;
	uint32_t next_free_off;
	uint32_t object_table_off;
	uint32_t object_count;
	uint32_t object_capacity;
	uint32_t queue_count;
	uint64_t feature_bits;
	struct proxy_comm_vmshm_queue queues[PROXY_COMM_VMSHM_MAX_QUEUES];
};

struct proxy_comm_vmshm_queue_object {
	uint32_t magic;
	uint32_t queue_id;
	uint32_t direction;
	uint32_t queue_size;
	uint32_t queue_mask;
	uint32_t msg_size;
	uint32_t desc_off;
	uint32_t avail_off;
	uint32_t used_off;
	uint32_t msg_pool_off;
	uint32_t desc_obj_id;
	uint32_t avail_obj_id;
	uint32_t used_obj_id;
	uint32_t msg_pool_obj_id;
	uint32_t flags;
	uint32_t reserved;
};

struct proxy_comm_vmshm_desc {
	uint32_t msg_off;
	uint32_t msg_capacity;
	uint32_t msg_len;
	uint32_t flags;
	uint64_t seq;
};

struct proxy_comm_vmshm_avail_ring {
	uint32_t idx;
	uint32_t flags;
	uint16_t ring[];
};

struct proxy_comm_vmshm_used_elem {
	uint16_t desc_id;
	int16_t status;
	uint32_t len;
};

struct proxy_comm_vmshm_used_ring {
	uint32_t idx;
	uint32_t flags;
	struct proxy_comm_vmshm_used_elem ring[];
};

struct proxy_comm_vmshm_msg {
	uint32_t type;
	uint32_t flags;
	uint32_t len;
	int32_t status;
	uint64_t seq;
	uint64_t reply_to;
	uint32_t reserved;
	uint8_t payload[];
};

struct client_comm_vmshm_info {
	uint64_t gpa;
	uint64_t size;
	uint32_t header_size;
	uint32_t queue_count;
};

#define CLIENT_COMM_VMSHM_IOC_GET_INFO \
	_IOR(CLIENT_COMM_VMSHM_IOC_MAGIC, 3, struct client_comm_vmshm_info)

struct panthor_vmshm_close_session_req {
	uint64_t session_id;
	uint32_t flags;
	uint32_t pad;
};

struct panthor_vmshm_close_session_rsp {
	int32_t ret;
	uint32_t pad;
};

struct panthor_vmshm_dev_query_req {
	uint64_t session_id;
	uint32_t type;
	uint32_t size;
	uint32_t flags;
	uint32_t pad;
};

struct panthor_vmshm_dev_query_rsp {
	int32_t ret;
	uint32_t type;
	uint32_t size;
	uint32_t data_len;
};

struct drm_panthor_dev_query {
	uint32_t type;
	uint32_t size;
	uint64_t pointer;
};

struct vmshm_layout {
	struct client_comm_vmshm_info info;
	struct proxy_comm_vmshm_header hdr;
	struct proxy_comm_vmshm_queue_object queues[PROXY_COMM_VMSHM_MAX_QUEUES];
};

struct raw_sent {
	uint64_t seq;
	uint32_t desc_id;
	uint32_t ring_idx;
	uint32_t used_idx_before;
};

struct raw_rx {
	uint32_t type;
	int32_t status;
	uint64_t seq;
	uint64_t reply_to;
	uint32_t len;
	uint8_t payload[512];
};

static void usage(const char *prog)
{
	fprintf(stderr,
		"usage: %s --session SESSION [--ops dev-query,close-session] [--device /dev/client_comm_vmshm] [--timeout-ms N] [--require-response] [--no-kick-drm]\n",
		prog);
}

static long long now_ms(void)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts))
		return 0;

	return (long long)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL;
}

static int parse_u64(const char *label, const char *value, uint64_t *out)
{
	char *end = NULL;
	unsigned long long parsed;

	errno = 0;
	parsed = strtoull(value, &end, 0);
	if (errno || !end || *end) {
		fprintf(stderr, "invalid %s: %s\n", label, value);
		return -1;
	}

	*out = (uint64_t)parsed;
	return 0;
}

static int parse_int(const char *label, const char *value, int *out)
{
	uint64_t parsed;

	if (parse_u64(label, value, &parsed))
		return -1;
	if (parsed > 1000000ULL) {
		fprintf(stderr, "invalid %s: %s\n", label, value);
		return -1;
	}

	*out = (int)parsed;
	return 0;
}

static int read_full(int fd, void *buf, size_t len, off_t off)
{
	uint8_t *p = buf;
	size_t done = 0;

	while (done < len) {
		ssize_t ret = pread(fd, p + done, len - done, off + (off_t)done);

		if (ret < 0) {
			if (errno == EINTR)
				continue;
			return -errno;
		}
		if (!ret)
			return -EIO;
		done += (size_t)ret;
	}

	return 0;
}

static int write_full(int fd, const void *buf, size_t len, off_t off)
{
	const uint8_t *p = buf;
	size_t done = 0;

	while (done < len) {
		ssize_t ret = pwrite(fd, p + done, len - done, off + (off_t)done);

		if (ret < 0) {
			if (errno == EINTR)
				continue;
			return -errno;
		}
		if (!ret)
			return -EIO;
		done += (size_t)ret;
	}

	return 0;
}

static int read_u32(int fd, off_t off, uint32_t *out)
{
	return read_full(fd, out, sizeof(*out), off);
}

static int write_u32(int fd, off_t off, uint32_t value)
{
	return write_full(fd, &value, sizeof(value), off);
}

static int range_ok(const struct client_comm_vmshm_info *info,
		    uint32_t off, uint32_t len)
{
	uint64_t end = (uint64_t)off + len;

	return end >= off && end <= info->size;
}

static int load_layout(int fd, struct vmshm_layout *layout)
{
	int ret;
	uint32_t i;

	memset(layout, 0, sizeof(*layout));
	ret = ioctl(fd, CLIENT_COMM_VMSHM_IOC_GET_INFO, &layout->info);
	if (ret < 0) {
		fprintf(stderr, "CLIENT_COMM_VMSHM_IOC_GET_INFO failed: %s\n",
			strerror(errno));
		return -1;
	}

	ret = read_full(fd, &layout->hdr, sizeof(layout->hdr), 0);
	if (ret) {
		fprintf(stderr, "read vmshm header failed: %s\n", strerror(-ret));
		return -1;
	}

	if (layout->hdr.magic != PROXY_COMM_VMSHM_MAGIC ||
	    layout->hdr.version != PROXY_COMM_VMSHM_VERSION ||
	    layout->hdr.header_size != sizeof(layout->hdr) ||
	    layout->hdr.queue_count != PROXY_COMM_VMSHM_MAX_QUEUES ||
	    layout->info.queue_count != PROXY_COMM_VMSHM_MAX_QUEUES) {
		fprintf(stderr,
			"invalid vmshm header magic=0x%x version=%u header_size=%u queue_count=%u info_queue_count=%u\n",
			layout->hdr.magic, layout->hdr.version,
			layout->hdr.header_size, layout->hdr.queue_count,
			layout->info.queue_count);
		return -1;
	}

	for (i = 0; i < PROXY_COMM_VMSHM_MAX_QUEUES; i++) {
		const struct proxy_comm_vmshm_queue *hq = &layout->hdr.queues[i];
		struct proxy_comm_vmshm_queue_object *q = &layout->queues[i];

		if (!range_ok(&layout->info, hq->queue_off, sizeof(*q))) {
			fprintf(stderr, "queue%u object is out of range\n", i);
			return -1;
		}

		ret = read_full(fd, q, sizeof(*q), hq->queue_off);
		if (ret) {
			fprintf(stderr, "read queue%u object failed: %s\n",
				i, strerror(-ret));
			return -1;
		}

		if (q->magic != PROXY_COMM_VMSHM_QUEUE_MAGIC ||
		    q->queue_id != i ||
		    q->queue_size == 0 ||
		    q->queue_size != q->queue_mask + 1 ||
		    q->msg_size < sizeof(struct proxy_comm_vmshm_msg) ||
		    !range_ok(&layout->info, q->desc_off,
			      q->queue_size * sizeof(struct proxy_comm_vmshm_desc)) ||
		    !range_ok(&layout->info, q->avail_off,
			      sizeof(struct proxy_comm_vmshm_avail_ring) +
				      q->queue_size * sizeof(uint16_t)) ||
		    !range_ok(&layout->info, q->used_off,
			      sizeof(struct proxy_comm_vmshm_used_ring) +
				      q->queue_size *
					      sizeof(struct proxy_comm_vmshm_used_elem)) ||
		    !range_ok(&layout->info, q->msg_pool_off,
			      q->queue_size * q->msg_size)) {
			fprintf(stderr,
				"invalid queue%u layout magic=0x%x id=%u size=%u mask=%u msg_size=%u\n",
				i, q->magic, q->queue_id, q->queue_size,
				q->queue_mask, q->msg_size);
			return -1;
		}
	}

	return 0;
}

static int wait_queue_idle(int fd, const struct proxy_comm_vmshm_queue_object *q,
			   int timeout_ms)
{
	long long deadline = now_ms() + timeout_ms;

	for (;;) {
		uint32_t avail_idx = 0, used_idx = 0;
		int ret;

		ret = read_u32(fd, q->avail_off + offsetof(struct proxy_comm_vmshm_avail_ring, idx),
			       &avail_idx);
		if (ret)
			return ret;
		ret = read_u32(fd, q->used_off + offsetof(struct proxy_comm_vmshm_used_ring, idx),
			       &used_idx);
		if (ret)
			return ret;
		if (avail_idx == used_idx)
			return 0;
		if (now_ms() >= deadline)
			return -ETIMEDOUT;
		usleep(POLL_SLEEP_US);
	}
}

static int queue_send(int fd, const struct proxy_comm_vmshm_queue_object *q,
		      uint32_t type, uint64_t seq, const void *payload,
		      uint32_t payload_len, struct raw_sent *sent)
{
	uint8_t msg_buf[512];
	struct proxy_comm_vmshm_desc desc;
	uint32_t avail_idx = 0, used_idx = 0, ring_idx, desc_id, msg_off;
	uint16_t desc_id16;
	int ret;

	if (q->msg_size > sizeof(msg_buf) ||
	    payload_len > q->msg_size - sizeof(struct proxy_comm_vmshm_msg))
		return -EMSGSIZE;

	ret = read_u32(fd, q->avail_off + offsetof(struct proxy_comm_vmshm_avail_ring, idx),
		       &avail_idx);
	if (ret)
		return ret;
	ret = read_u32(fd, q->used_off + offsetof(struct proxy_comm_vmshm_used_ring, idx),
		       &used_idx);
	if (ret)
		return ret;
	if ((uint32_t)(avail_idx - used_idx) >= q->queue_size)
		return -EAGAIN;

	ring_idx = avail_idx & q->queue_mask;
	desc_id = ring_idx;
	msg_off = q->msg_pool_off + desc_id * q->msg_size;

	memset(msg_buf, 0, sizeof(msg_buf));
	((struct proxy_comm_vmshm_msg *)msg_buf)->type = type;
	((struct proxy_comm_vmshm_msg *)msg_buf)->len = payload_len;
	((struct proxy_comm_vmshm_msg *)msg_buf)->seq = seq;
	if (payload_len)
		memcpy(msg_buf + offsetof(struct proxy_comm_vmshm_msg, payload),
		       payload, payload_len);

	memset(&desc, 0, sizeof(desc));
	desc.msg_off = msg_off;
	desc.msg_capacity = q->msg_size;
	desc.msg_len = sizeof(struct proxy_comm_vmshm_msg) + payload_len;
	desc.seq = seq;
	desc_id16 = (uint16_t)desc_id;

	ret = write_full(fd, msg_buf, q->msg_size, msg_off);
	if (ret)
		return ret;
	ret = write_full(fd, &desc, sizeof(desc),
			 q->desc_off + desc_id * sizeof(desc));
	if (ret)
		return ret;
	ret = write_full(fd, &desc_id16, sizeof(desc_id16),
			 q->avail_off +
				 offsetof(struct proxy_comm_vmshm_avail_ring, ring) +
				 ring_idx * sizeof(desc_id16));
	if (ret)
		return ret;
	ret = write_u32(fd,
			q->avail_off +
				offsetof(struct proxy_comm_vmshm_avail_ring, idx),
			avail_idx + 1);
	if (ret)
		return ret;

	memset(sent, 0, sizeof(*sent));
	sent->seq = seq;
	sent->desc_id = desc_id;
	sent->ring_idx = used_idx & q->queue_mask;
	sent->used_idx_before = used_idx;
	return 0;
}

static int wait_consumed(int fd, const struct proxy_comm_vmshm_queue_object *q,
			 const struct raw_sent *sent, int timeout_ms,
			 int16_t *queue_status)
{
	long long deadline = now_ms() + timeout_ms;

	for (;;) {
		uint32_t used_idx = 0;
		struct proxy_comm_vmshm_used_elem elem;
		int ret;

		ret = read_u32(fd, q->used_off +
				       offsetof(struct proxy_comm_vmshm_used_ring, idx),
			       &used_idx);
		if (ret)
			return ret;
		if ((uint32_t)(used_idx - sent->used_idx_before) >= 1) {
			ret = read_full(fd, &elem, sizeof(elem),
					q->used_off +
						offsetof(struct proxy_comm_vmshm_used_ring, ring) +
						sent->ring_idx * sizeof(elem));
			if (ret)
				return ret;
			*queue_status = elem.status;
			return 0;
		}
		if (now_ms() >= deadline)
			return -ETIMEDOUT;
		usleep(POLL_SLEEP_US);
	}
}

static int queue_recv_one(int fd, const struct proxy_comm_vmshm_queue_object *q,
			  struct raw_rx *rx)
{
	uint8_t msg_buf[512];
	struct proxy_comm_vmshm_desc desc;
	struct proxy_comm_vmshm_msg *msg = (struct proxy_comm_vmshm_msg *)msg_buf;
	struct proxy_comm_vmshm_used_elem elem;
	uint32_t avail_idx = 0, used_idx = 0, ring_idx, desc_id = 0;
	uint16_t desc_id16 = 0;
	uint32_t expected_msg_off;
	int ret = -EINVAL;

	memset(rx, 0, sizeof(*rx));
	if (q->msg_size > sizeof(msg_buf))
		return -EMSGSIZE;

	ret = read_u32(fd, q->used_off + offsetof(struct proxy_comm_vmshm_used_ring, idx),
		       &used_idx);
	if (ret)
		return ret;
	ret = read_u32(fd, q->avail_off + offsetof(struct proxy_comm_vmshm_avail_ring, idx),
		       &avail_idx);
	if (ret)
		return ret;
	if (used_idx == avail_idx)
		return -ENOENT;

	ring_idx = used_idx & q->queue_mask;
	ret = read_full(fd, &desc_id16, sizeof(desc_id16),
			q->avail_off + offsetof(struct proxy_comm_vmshm_avail_ring, ring) +
				ring_idx * sizeof(desc_id16));
	if (ret)
		goto out_used;
	desc_id = desc_id16;
	if (desc_id >= q->queue_size)
		goto out_used;

	ret = read_full(fd, &desc, sizeof(desc),
			q->desc_off + desc_id * sizeof(desc));
	if (ret)
		goto out_used;

	expected_msg_off = q->msg_pool_off + desc_id * q->msg_size;
	if (desc.msg_off != expected_msg_off ||
	    desc.msg_capacity != q->msg_size ||
	    desc.msg_len < sizeof(struct proxy_comm_vmshm_msg) ||
	    desc.msg_len > q->msg_size)
		goto out_used;

	ret = read_full(fd, msg_buf, desc.msg_len, desc.msg_off);
	if (ret)
		goto out_used;
	if (msg->len > q->msg_size - sizeof(*msg) ||
	    sizeof(*msg) + msg->len != desc.msg_len)
		goto out_used;

	rx->type = msg->type;
	rx->status = msg->status;
	rx->seq = msg->seq;
	rx->reply_to = msg->reply_to;
	rx->len = msg->len;
	if (msg->len)
		memcpy(rx->payload, msg->payload, msg->len);
	ret = 0;

out_used:
	memset(&elem, 0, sizeof(elem));
	elem.desc_id = (uint16_t)desc_id;
	elem.status = ret;
	elem.len = ret ? 0 : desc.msg_len;
	(void)write_full(fd, &elem, sizeof(elem),
			 q->used_off +
				 offsetof(struct proxy_comm_vmshm_used_ring, ring) +
				 ring_idx * sizeof(elem));
	(void)write_u32(fd,
			q->used_off +
				offsetof(struct proxy_comm_vmshm_used_ring, idx),
			used_idx + 1);
	return ret;
}

static int wait_response(int fd, const struct proxy_comm_vmshm_queue_object *q,
			 uint64_t seq, uint32_t expected_type, int timeout_ms,
			 struct raw_rx *rx)
{
	long long deadline = now_ms() + timeout_ms;

	for (;;) {
		int ret = queue_recv_one(fd, q, rx);

		if (!ret) {
			if (rx->reply_to == seq && rx->type == expected_type)
				return 0;
			printf("VMSHM_RAW_RPC_UNEXPECTED_RSP type=0x%x reply_to=%llu seq=%llu status=%d len=%u\n",
			       rx->type, (unsigned long long)rx->reply_to,
			       (unsigned long long)rx->seq, rx->status, rx->len);
			continue;
		}
		if (ret != -ENOENT)
			return ret;
		if (now_ms() >= deadline)
			return -ETIMEDOUT;
		usleep(POLL_SLEEP_US);
	}
}

static uint64_t make_seq(unsigned int op_index)
{
	uint64_t t = (uint64_t)now_ms();

	return ((uint64_t)(uint32_t)getpid() << 32) ^ (t << 8) ^ op_index;
}

static int kick_proxy_with_drm_query(void)
{
	static const char *const nodes[] = {
		"/dev/dri/card0",
		"/dev/dri/renderD128",
	};
	struct drm_panthor_dev_query query = {
		.type = DRM_PANTHOR_DEV_QUERY_GPU_INFO,
	};
	int saved_errno = ENOENT;

	for (size_t i = 0; i < sizeof(nodes) / sizeof(nodes[0]); i++) {
		int fd = open(nodes[i], O_RDWR | O_CLOEXEC);

		if (fd < 0) {
			saved_errno = errno;
			continue;
		}

		if (!ioctl(fd, DRM_IOCTL_PANTHOR_DEV_QUERY, &query)) {
			close(fd);
			printf("VMSHM_RAW_RPC_KICK_DRM node=%s size=%u\n",
			       nodes[i], query.size);
			return 0;
		}

		saved_errno = errno;
		close(fd);
	}

	fprintf(stderr, "raw RPC DRM kick failed: %s\n", strerror(saved_errno));
	return -1;
}

static int rsp_ret_for_op(const char *op, const struct raw_rx *rx, int32_t *rsp_ret)
{
	if (!strcmp(op, "close-session")) {
		const struct panthor_vmshm_close_session_rsp *rsp;

		if (rx->len < sizeof(*rsp))
			return -EPROTO;
		rsp = (const struct panthor_vmshm_close_session_rsp *)rx->payload;
		*rsp_ret = rsp->ret;
		return 0;
	}

	if (!strcmp(op, "dev-query")) {
		const struct panthor_vmshm_dev_query_rsp *rsp;

		if (rx->len < sizeof(*rsp))
			return -EPROTO;
		rsp = (const struct panthor_vmshm_dev_query_rsp *)rx->payload;
		*rsp_ret = rsp->ret;
		return 0;
	}

	return -EINVAL;
}

static int run_op(int fd, const struct vmshm_layout *layout, const char *op,
		  uint64_t session_id, unsigned int op_index, int timeout_ms,
		  int require_response, int kick_drm)
{
	const struct proxy_comm_vmshm_queue_object *txq =
		&layout->queues[PROXY_COMM_VMSHM_Q_CLIENT_TO_PROXY];
	const struct proxy_comm_vmshm_queue_object *rxq =
		&layout->queues[PROXY_COMM_VMSHM_Q_PROXY_TO_CLIENT];
	uint8_t payload[64];
	uint32_t req_type, rsp_type;
	uint32_t payload_len;
	struct raw_sent sent;
	struct raw_rx rx;
	uint64_t seq = make_seq(op_index);
	int32_t rsp_ret = 0;
	int16_t queue_status = 0;
	int ret;

	memset(payload, 0, sizeof(payload));
	if (!strcmp(op, "close-session")) {
		struct panthor_vmshm_close_session_req req = {
			.session_id = session_id,
		};

		req_type = PANTHOR_VMSHM_MSG_CLOSE_SESSION_REQ;
		rsp_type = PANTHOR_VMSHM_MSG_CLOSE_SESSION_RSP;
		payload_len = sizeof(req);
		memcpy(payload, &req, sizeof(req));
	} else if (!strcmp(op, "dev-query")) {
		struct panthor_vmshm_dev_query_req req = {
			.session_id = session_id,
			.type = DRM_PANTHOR_DEV_QUERY_GPU_INFO,
		};

		req_type = PANTHOR_VMSHM_MSG_DEV_QUERY_REQ;
		rsp_type = PANTHOR_VMSHM_MSG_DEV_QUERY_RSP;
		payload_len = sizeof(req);
		memcpy(payload, &req, sizeof(req));
	} else {
		fprintf(stderr, "unknown raw RPC op: %s\n", op);
		return -1;
	}

	ret = wait_queue_idle(fd, txq, timeout_ms);
	if (ret) {
		fprintf(stderr, "C2P queue did not become idle before %s: %s\n",
			op, strerror(-ret));
		return -1;
	}

	ret = queue_send(fd, txq, req_type, seq, payload, payload_len, &sent);
	if (ret) {
		fprintf(stderr, "raw RPC send op=%s failed: %s\n",
			op, strerror(-ret));
		return -1;
	}

	printf("VMSHM_RAW_RPC_SENT op=%s session=%llu type=0x%x seq=%llu desc=%u\n",
	       op, (unsigned long long)session_id, req_type,
	       (unsigned long long)seq, sent.desc_id);

	if (kick_drm && kick_proxy_with_drm_query())
		return -1;

	ret = wait_consumed(fd, txq, &sent, timeout_ms, &queue_status);
	if (ret) {
		fprintf(stderr, "raw RPC op=%s was not consumed by proxy: %s\n",
			op, strerror(-ret));
		return -1;
	}
	if (queue_status) {
		fprintf(stderr,
			"raw RPC op=%s consumed with transport status=%d\n",
			op, queue_status);
		return -1;
	}

	printf("VMSHM_RAW_RPC_CONSUMED op=%s session=%llu seq=%llu queue_status=%d\n",
	       op, (unsigned long long)session_id,
	       (unsigned long long)seq, queue_status);

	ret = wait_response(fd, rxq, seq, rsp_type, timeout_ms, &rx);
	if (ret == -ETIMEDOUT && !require_response) {
		printf("VMSHM_RAW_RPC_CONSUMED_NO_RSP op=%s session=%llu seq=%llu note=response_may_be_drained_by_client_comm_irq_worker\n",
		       op, (unsigned long long)session_id,
		       (unsigned long long)seq);
		return 0;
	}
	if (ret) {
		fprintf(stderr, "raw RPC response op=%s failed: %s\n",
			op, strerror(-ret));
		return -1;
	}

	ret = rsp_ret_for_op(op, &rx, &rsp_ret);
	if (ret) {
		fprintf(stderr, "raw RPC op=%s malformed response: %s\n",
			op, strerror(-ret));
		return -1;
	}

	if (rsp_ret == 0) {
		fprintf(stderr,
			"VMSHM_RAW_RPC_FAIL unexpected_success op=%s session=%llu msg_status=%d rsp_ret=%d\n",
			op, (unsigned long long)session_id, rx.status,
			rsp_ret);
		return -1;
	}

	if (rsp_ret != -ENOENT && rsp_ret != -EACCES) {
		fprintf(stderr,
			"VMSHM_RAW_RPC_FAIL unexpected_ret op=%s session=%llu msg_status=%d rsp_ret=%d\n",
			op, (unsigned long long)session_id, rx.status,
			rsp_ret);
		return -1;
	}

	printf("VMSHM_RAW_RPC_DENIED op=%s session=%llu msg_status=%d rsp_ret=%d\n",
	       op, (unsigned long long)session_id, rx.status, rsp_ret);
	return 0;
}

int main(int argc, char **argv)
{
	const char *dev = "/dev/client_comm_vmshm";
	char ops_buf[128] = "dev-query,close-session";
	uint64_t session_id = 0;
	int timeout_ms = DEFAULT_TIMEOUT_MS;
	int require_response = 0;
	int kick_drm = 1;
	struct vmshm_layout layout;
	int fd, rc = 0;
	char *saveptr = NULL;
	char *op;
	unsigned int op_index = 1;

	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--session")) {
			if (++i >= argc || parse_u64("--session", argv[i], &session_id))
				return 2;
		} else if (!strcmp(argv[i], "--ops")) {
			if (++i >= argc || strlen(argv[i]) >= sizeof(ops_buf))
				return 2;
			strcpy(ops_buf, argv[i]);
		} else if (!strcmp(argv[i], "--device")) {
			if (++i >= argc)
				return 2;
			dev = argv[i];
		} else if (!strcmp(argv[i], "--timeout-ms")) {
			if (++i >= argc || parse_int("--timeout-ms", argv[i], &timeout_ms))
				return 2;
		} else if (!strcmp(argv[i], "--require-response")) {
			require_response = 1;
		} else if (!strcmp(argv[i], "--no-kick-drm")) {
			kick_drm = 0;
		} else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
			usage(argv[0]);
			return 0;
		} else {
			usage(argv[0]);
			return 2;
		}
	}

	if (!session_id) {
		usage(argv[0]);
		return 2;
	}

	if (sizeof(struct proxy_comm_vmshm_msg) != 40 ||
	    offsetof(struct proxy_comm_vmshm_msg, payload) != 36) {
		fprintf(stderr,
			"unexpected vmshm message layout sizeof=%zu payload_off=%zu\n",
			sizeof(struct proxy_comm_vmshm_msg),
			offsetof(struct proxy_comm_vmshm_msg, payload));
		return 2;
	}

	fd = open(dev, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "open %s failed: %s\n", dev, strerror(errno));
		return 3;
	}

	if (load_layout(fd, &layout)) {
		close(fd);
		return 4;
	}

	for (op = strtok_r(ops_buf, ",", &saveptr); op;
	     op = strtok_r(NULL, ",", &saveptr), op_index++) {
		if (!*op)
			continue;
		if (run_op(fd, &layout, op, session_id, op_index, timeout_ms,
			   require_response, kick_drm))
			rc = 1;
	}

	close(fd);
	if (rc) {
		printf("VMSHM_RAW_RPC_RESULT=FAIL\n");
		return 10;
	}

	printf("VMSHM_RAW_RPC_RESULT=PASS\n");
	return 0;
}
