// SPDX-License-Identifier: GPL-2.0-only
/* Actual kernel/Proxy function tests; all RSI, memory and transport are doubles.
 * No real RMM policy, hardware completion or DRM scheduling is established here.
 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "linux/realm_gpu.h"

typedef uint32_t u32;
typedef uint64_t u64;
#define GFP_KERNEL 0
#define __GFP_ZERO 0
#define PRIVATE_STATUS_INPUT 1U
#define PRIVATE_STATUS_STATE 2U
#define PRIVATE_STATUS_FULL 3U
#define PRIVATE_STATUS_INCOMPLETE 4U
#define IS_ALIGNED(n,a) (((n) & ((a)-1)) == 0)
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095L)
#define PTR_ERR(p) ((intptr_t)(p))
static unsigned int allocations, frees, attempts, fail_allocation, cases;
static void *kzalloc(size_t size, int flags)
{
	if (++attempts == fail_allocation) return NULL;
	void *p = calloc(1, size); assert(p); allocations++; return p;
}
static void kfree(void *p) { if (p) { frees++; free(p); } }
struct page { unsigned char data[4096]; };
static struct page *alloc_page(int flags) { return kzalloc(sizeof(struct page), flags); }
static void *page_address(struct page *p) { return p->data; }
static void __free_page(struct page *p) { kfree(p); }
struct list_head { struct list_head *next, *prev; };
#define LIST_HEAD(n) struct list_head n = { &(n), &(n) }
#define entry(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define list_for_each_entry(p,h,m) \
	for (p=entry((h)->next,__typeof__(*p),m); &(p)->m!=(h); p=entry((p)->m.next,__typeof__(*p),m))
#define list_for_each_entry_safe(p,n,h,m) \
	for (p=entry((h)->next,__typeof__(*p),m),n=entry((p)->m.next,__typeof__(*p),m); \
	     &(p)->m!=(h); p=n,n=entry((n)->m.next,__typeof__(*n),m))
static void list_add_tail(struct list_head *p, struct list_head *h)
{
	p->next=h; p->prev=h->prev; h->prev->next=p; h->prev=p;
}
static void list_del(struct list_head *p) { p->prev->next=p->next; p->next->prev=p->prev; }
static bool list_empty(struct list_head *p) { return p->next == p; }
static int gpu_lock;
static void mutex_lock(int *lock) { assert(!*lock); *lock=1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock=0; }
static bool realm = true;
static bool is_realm_world(void) { return realm; }
struct xarray { void *slot[8]; };
static void *xa_load(struct xarray *xa, u32 id) { return id < 8 ? xa->slot[id] : NULL; }
struct proxy_comm_vmshm_channel { u32 client; u64 rmm; };
struct panthor_proxy_session {
	u64 session_id;
	int lock;
	bool closing;
	struct proxy_comm_vmshm_channel *channel;
	struct xarray groups, vms;
};
struct vmshm_comm_rx { u64 seq; };
#include "structures.inc"
_Static_assert(sizeof(struct panthor_vmshm_rmm_task_req)==24, "request layout");
_Static_assert(sizeof(struct panthor_vmshm_rmm_task_rsp)==24, "reply layout");
static LIST_HEAD(private_groups);
static LIST_HEAD(private_tasks);
static struct realm_gpu_group group = { .handle = 41 };
static struct proxy_comm_vmshm_channel channel = { .client=1, .rmm=7 };
static struct panthor_proxy_group proxy_group = { .private_group=41, .client_vm_id=2,
	.proxy_vm_id=12, .queue_count=2 };
static struct panthor_proxy_vm proxy_vm = { .rmm_private=true, .private_context=71,
	.proxy_vm_id=12 };
static struct panthor_proxy_session session = { .session_id=9, .channel=&channel };
static u64 token, next_token = 0xcca6000000010001ULL;
static unsigned int phase, calls, cancel_calls, service_calls, reply_fault, retire_fault;
static bool retire_preserve;
static bool transport_failure, partial, done, lost_response, duplicate_token, zero_token;
static struct realm_gpu_task_command *caller_commands;
static struct realm_gpu_task_command captured[6];
static unsigned int captured_count;
static bool delegated_stage;
static u64 progress_mask;
static struct panthor_vmshm_rmm_task_rsp response;
static unsigned int sends, session_puts;

static void corrupt_reply(struct realm_gpu_call *call)
{
	if (reply_fault==1) call->result[0]++;
	if (reply_fault==2) call->result[1]++;
	if (reply_fault==3) call->result[2]++;
	if (reply_fault==4) call->result[3]=1;
	if (reply_fault==5) call->result[3]=2;
}
static int gpu_call_locked(struct realm_gpu_call *call, struct page *snapshot)
{
	assert(gpu_lock); calls++;
	memset(call->result,0,sizeof(call->result));
	if (transport_failure) return -EIO;
	call->status=0;
	if (call->operation==REALM_GPU_TASK_STAGE_BATCH) {
		assert(call->handle==41 && call->args[1]==7 && snapshot &&
		       call->args[3]==(REALM_GPU_TASK_DEFERRED | (delegated_stage?REALM_GPU_TASK_DELEGATE:0)) && !call->args[4]);
		captured_count=call->args[2]; assert(captured_count && captured_count<=6);
		if (caller_commands) memset(caller_commands,0xff,captured_count*sizeof(*caller_commands));
		memcpy(captured,page_address(snapshot),captured_count*sizeof(*captured));
		u32 mask=0;
		for (u32 i=0;i<captured_count;i++) mask|=1U<<captured[i].queue;
		if (duplicate_token) {
			assert(token);
			call->result[0]=token; call->result[1]=captured_count; call->result[2]=mask;
			return 0;
		}
		assert(!token);
		if (zero_token) return 0;
		token=next_token++; phase=1;
		call->result[0]=token; call->result[1]=captured_count; call->result[2]=mask;
		/* Stage fault 1 changes count, not token, so orphan cleanup can be checked. */
		if (reply_fault==1) call->result[1]++;
		else corrupt_reply(call);
		return 0;
	}
	assert(!snapshot);
	if (call->operation==REALM_GPU_TASK_CANCEL) {
		cancel_calls++;
		for (unsigned int i=0;i<5;i++) assert(call->args[i]==0);
		if (!token || call->handle!=token) call->status=1;
		else if (phase==1) { token=0; phase=0; corrupt_reply(call); }
		else call->status=2;
		return 0;
	}
	assert(call->handle==token && token && call->args[0]==7);
	if (call->operation==REALM_GPU_TASK_PUBLISH) {
		assert(!call->args[2] && !call->args[3] && !call->args[4]);
		if (phase!=3 && phase!=4) {call->status=2;return 0;}
		call->result[0]=call->args[1];call->result[1]=captured_count;
		for(u32 i=0;i<captured_count;i++)call->result[2]|=1U<<captured[i].queue;
		if(partial)call->status=4,call->result[0]=0;
		corrupt_reply(call);
		return 0;
	}
	assert(!call->args[1] && !call->args[2] && !call->args[3] && !call->args[4]);
	if (call->operation==REALM_GPU_TASK_PROGRESS) {
		if (phase!=4 && phase!=5) {call->status=2;return 0;}
		call->result[0]=partial?0:progress_mask;call->result[1]=captured_count;
		for(u32 i=0;i<captured_count;i++)call->result[2]|=1U<<captured[i].queue;
		if(partial)call->status=4;
		if(reply_fault==1)call->result[0]=1ULL<<63;
		else corrupt_reply(call);
		return 0;
	}
	call->result[1]=1; /* Original first queue, not a Proxy-selected queue. */
	if (call->operation==REALM_GPU_TASK_READY || call->operation==REALM_GPU_TASK_READY_PUBLISH || call->operation==REALM_GPU_TASK_READY_LAUNCH) {
		if (phase!=2 && phase!=3) call->status=2;
		else if (partial) call->status=4,call->result[2]=1;
		else phase=call->operation==REALM_GPU_TASK_READY_LAUNCH?4:3,call->result[0]=1,call->result[2]=2;
	} else if (call->operation==REALM_GPU_TASK_COMPLETE) {
		if (phase!=4 && phase!=5) call->status=2;
		else if (!done) call->status=4;
		else phase=5,call->result[0]=1;
	} else if (call->operation==REALM_GPU_TASK_RETURN) {
		if (phase!=5 && phase!=6) call->status=2;
		else if (partial) call->status=4,call->result[2]=1;
		else phase=6,call->result[0]=1,call->result[2]=2;
	} else if (call->operation==REALM_GPU_TASK_FINISH) {
		if (phase!=4 && phase!=5 && phase!=6) call->status=2;
		else if (phase==4 && !done) call->status=4;
		else if (partial) call->status=4,phase=5,call->result[3]=1;
		else token=0,phase=0,call->result[0]=1;
	} else if (call->operation==REALM_GPU_TASK_RECLAIM) {
		if (phase!=5 && phase!=6) call->status=2;
		else if (partial) call->status=4;
		else token=0,phase=0,call->result[0]=1;
	} else {
		assert(call->operation==REALM_GPU_TASK_RETIRE);
		if (phase!=6) call->status=2;
		else if (partial) call->status=4,call->result[2]=64;
		else token=0,phase=0,call->result[0]=1,call->result[2]=retire_preserve?0:71;
	}
	if (call->operation==REALM_GPU_TASK_RETIRE && retire_preserve) {
		if (retire_fault==1) call->result[0]=0;
		if (retire_fault==2) call->result[1]++;
		if (retire_fault==3) call->result[3]=1;
		if (retire_fault==4) call->result[2]=REALM_GPU_CONTROL_MAX_PAGES+1ULL;
		if (retire_fault==5) call->result[2]=0; /* INCOMPLETE without progress. */
		if (retire_fault==6) call->result[0]=1; /* INCOMPLETE claiming retirement. */
	}
	if (!call->status || call->status==4) corrupt_reply(call);
	return 0;
}
static u64 proxy_comm_vmshm_channel_rmm_channel(struct proxy_comm_vmshm_channel *p) { return p->rmm; }
static u32 proxy_comm_vmshm_channel_client_vmid(struct proxy_comm_vmshm_channel *p) { return p->client; }
static int realm_gpu_private_call_checked(struct realm_gpu_call *call)
{
	assert(session.lock && !gpu_lock); service_calls++;
	assert(call->args[0]==7 && call->args[1]==71 && call->args[2]==41);
	assert(!call->args[3] && !call->args[4]);
	if (transport_failure) return -EIO;
	if (!token || call->handle!=token) return -EINVAL;
	memset(call->result,0,sizeof(call->result)); call->result[1]=1;
	if (call->operation==REALM_GPU_TASK_DISPATCH) {
        if (!delegated_stage || phase!=1) return -EBUSY;
        phase=partial?2:4; call->result[0]=partial?4:5;
    } else if (call->operation==REALM_GPU_TASK_PREPARE || call->operation==REALM_GPU_TASK_PREPARE_LAUNCH) {
		if (phase!=1 && phase!=2) return -EBUSY;
		phase=2; call->result[0]=4;
	} else if (call->operation==REALM_GPU_TASK_START) {
		if (phase!=3 && phase!=4) return -EBUSY;
		phase=4; call->result[0]=5;
	} else {
		assert(call->operation==REALM_GPU_TASK_QUIESCE);
		if (phase!=4 && phase!=5) return -EBUSY;
		phase=5; call->result[0]=6;
	}
	corrupt_reply(call);
	return 0;
}
static struct panthor_proxy_session *panthor_proxy_session_lookup(u64 id,u32 owner)
{
	return id==session.session_id && owner==1 ? &session : NULL;
}
static void panthor_proxy_session_put(struct panthor_proxy_session *p) { if (p) session_puts++; }
static int panthor_proxy_send_rsp(struct proxy_comm_vmshm_channel *p,u64 seq,u32 type,
	int ret,const void *payload,size_t bytes)
{
	assert(seq==17 && type==PANTHOR_VMSHM_MSG_RMM_TASK_RSP && bytes==24);
	memcpy(&response,payload,bytes); assert(response.ret==ret); sends++;
	return lost_response ? -EIO : 0;
}
#define pr_warn_ratelimited(...) ((void)0)
/* Raw diagnostic entry point is extracted too: no real user access or RSI. */
#define PAGE_SIZE 4096U
#define CAP_SYS_ADMIN 21
static bool admin=true, copy_fault;
static bool capable(int cap) { assert(cap==CAP_SYS_ADMIN); return admin; }
static int copy_from_user(void *dst,const void *src,size_t n)
{
	if (copy_fault) return 1;
	memcpy(dst,src,n); return 0;
}
static int copy_to_user(void *dst,const void *src,size_t n) { return copy_from_user(dst,src,n); }
#define u64_to_user_ptr(n) ((void *)(uintptr_t)(n))
static int private_alloc_ioctl(unsigned long arg,bool control) { assert(false); return -EIO; }
static bool managed_handle(u64 h) { return false; }
static bool managed_context(u64 h) { return false; }
static void reap_groups(void) { }
static void reap_contexts(void) { }
static void reap_backing(unsigned int n) { assert(n==8); }
static void reap_heaps(void) { }
static bool heap_range_busy(const struct realm_gpu_call *call) { return false; }
/* No hint is configured in this transport-only fixture; real hint lifetime
 * and original-command admission are covered by the PT/firmware/heap tests. */
static void task_drop_hint_locked(struct realm_gpu_task *task)
{ assert(!task->hint_bo); }
static void local_hint_commands(struct realm_gpu_task *task, struct realm_gpu_group *group,
        struct realm_gpu_call *call)
{ (void)task;(void)call;assert(!group->local_hint); }
#include "actual.inc"

static struct realm_gpu_task *stage(void)
{
	struct realm_gpu_task_command commands[6] = {
		{ .start=0x100000,.bytes=8,.queue=1 },
		{ .start=0x101000,.bytes=8,.queue=0 }, { .queue=1 }, {0}, {0}, {0}
	};
	caller_commands=commands;
	struct realm_gpu_task *task=realm_gpu_task_stage(&group,7,commands,6,delegated_stage);
	caller_commands=NULL;
	return task;
}
static void rpc(u32 action,u64 handle)
{
	struct vmshm_comm_rx rx={.seq=17};
	struct panthor_vmshm_rmm_task_req req={.session_id=9,.token=handle,
		.client_group_handle=3,.action=action};
	panthor_proxy_handle_rmm_task(&channel,&rx,&req);
}
static void reset(void)
{
	/* Trusted reset is simulated ONLY by clearing the model token. */
	token=0; phase=0; reply_fault=0; partial=false; done=false; duplicate_token=false; zero_token=false;
	transport_failure=false; lost_response=false;
	progress_mask=0; retire_fault=0; retire_preserve=false;
	mutex_lock(&gpu_lock); reap_tasks(); mutex_unlock(&gpu_lock);
	assert(list_empty(&private_tasks));
	assert(!gpu_lock && !session.lock);
}
int main(void)
{
	list_add_tail(&group.link,&private_groups);
	session.groups.slot[3]=&proxy_group; session.vms.slot[2]=&proxy_vm;
	for (unsigned int bad=0;bad<9;bad++) {
		struct realm_gpu_task_command cmd={.start=0x100000,.bytes=8,.queue=1};
		unsigned int before=calls;
		if (bad==0) cmd.pad=1;
		if (bad==1) cmd.queue=32;
		if (bad==2) cmd.start++;
		if (bad==3) cmd.bytes++;
		if (bad==4) cmd.start=0;
		if (bad==5) cmd.bytes=0;
		if (bad==6) group.retired=true;
		if (bad==7) realm=false;
		struct realm_gpu_task *task=realm_gpu_task_stage(&group,7,&cmd,bad==8?7:1,false);
		assert(IS_ERR(task) && PTR_ERR(task)==-EINVAL && calls==before);
		group.retired=false; realm=true; cases++;
	}
	for (unsigned int bad=1;bad<=2;bad++) {
		fail_allocation=attempts+bad;
		assert(PTR_ERR(stage())==-ENOMEM && !token);
		fail_allocation=0; cases++;
	}
	transport_failure=true;
	assert(PTR_ERR(stage())==-EIO && list_empty(&private_tasks));
	transport_failure=false; cases++;
	reply_fault=1;
	assert(PTR_ERR(stage())==-EPROTO && !token && list_empty(&private_tasks));
	reply_fault=0; cases++;
	zero_token=true;
	assert(PTR_ERR(stage())==-EPROTO && !token && list_empty(&private_tasks));
	zero_token=false; cases++;
	/* Admission retry needs an explicit trusted proof, not a Proxy error. */
	struct realm_gpu_task invalid={0};
	unsigned int before_cancel=calls;
	assert(realm_gpu_task_cancel_unprepared(NULL)==-EINVAL && calls==before_cancel);cases++;
	assert(realm_gpu_task_cancel_unprepared(&invalid)==-EINVAL && calls==before_cancel);cases++;
	invalid.handle=123;
	assert(realm_gpu_task_cancel_unprepared(&invalid)==-EINVAL && calls==before_cancel);cases++;
	struct realm_gpu_task *cancel_task=stage();
	u64 cancel_handle=realm_gpu_task_handle(cancel_task);
	assert(!realm_gpu_task_cancel_unprepared(cancel_task));
	assert(!token && !realm_gpu_task_handle(cancel_task) && !managed_task(cancel_handle));
	before_cancel=calls;
	assert(realm_gpu_task_cancel_unprepared(cancel_task)==-EINVAL && calls==before_cancel);
	realm_gpu_task_put(cancel_task);cases++;
	cancel_task=stage();cancel_handle=realm_gpu_task_handle(cancel_task);
	cancel_task->abandoned=true;before_cancel=calls;
	assert(realm_gpu_task_cancel_unprepared(cancel_task)==-EINVAL && calls==before_cancel);
	assert(managed_task(cancel_handle));realm_gpu_task_put(cancel_task);reset();cases++;
	cancel_task=stage();cancel_handle=realm_gpu_task_handle(cancel_task);
	transport_failure=true;
	assert(realm_gpu_task_cancel_unprepared(cancel_task)==-EIO &&
	       realm_gpu_task_handle(cancel_task)==cancel_handle && managed_task(cancel_handle));
	transport_failure=false;realm_gpu_task_put(cancel_task);reset();cases++;
	for (unsigned int bad=1;bad<=4;bad++) {
		cancel_task=stage();cancel_handle=realm_gpu_task_handle(cancel_task);reply_fault=bad;
		assert(realm_gpu_task_cancel_unprepared(cancel_task)==-EPROTO &&
		       realm_gpu_task_handle(cancel_task)==cancel_handle && managed_task(cancel_handle));
		reply_fault=0;realm_gpu_task_put(cancel_task);reset();cases++;
	}
	cancel_task=stage();cancel_handle=realm_gpu_task_handle(cancel_task);
	rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,cancel_handle);
	assert(!response.ret && phase==2);
	assert(realm_gpu_task_cancel_unprepared(cancel_task)==-EBUSY &&
	       token==cancel_handle && managed_task(cancel_handle));
	realm_gpu_task_put(cancel_task);assert(managed_task(cancel_handle));reset();cases++;
	struct realm_gpu_task *task=stage();
	assert(!IS_ERR(task) && managed_task(realm_gpu_task_handle(task)));
	assert(captured_count==6 && captured[0].start==0x100000 && captured[1].queue==0 && !captured[5].pad);
	u64 handle=realm_gpu_task_handle(task);
	unsigned int cancels_before=cancel_calls;
	duplicate_token=true;
	assert(PTR_ERR(stage())==-EPROTO && managed_task(handle) && token==handle);
	assert(cancel_calls==cancels_before && phase==1);
	duplicate_token=false; cases++;
	/* Privileged diagnostics cannot alter a kernel-owned task or group. */
	const u32 denied[]={REALM_GPU_TASK_CANCEL,REALM_GPU_TASK_READY,REALM_GPU_TASK_READY_PUBLISH,REALM_GPU_TASK_READY_LAUNCH,
		REALM_GPU_TASK_COMPLETE,REALM_GPU_TASK_RETURN,REALM_GPU_TASK_RETIRE,
		REALM_GPU_TASK_PROGRESS,REALM_GPU_TASK_PUBLISH,REALM_GPU_TASK_RECLAIM,REALM_GPU_TASK_FINISH,
		REALM_GPU_TASK_STAGE,REALM_GPU_GROUP_DESTROY,REALM_GPU_GROUP_CONFIGURE,
		REALM_GPU_TASK_STAGE_BATCH};
	for (unsigned int i=0;i<sizeof(denied)/sizeof(denied[0]);i++) {
		struct realm_gpu_task_command cmd={0};
		struct realm_gpu_call raw={.operation=denied[i],.handle=(denied[i]==REALM_GPU_TASK_STAGE || denied[i]==REALM_GPU_GROUP_DESTROY ||
			denied[i]==REALM_GPU_GROUP_CONFIGURE || denied[i]==REALM_GPU_TASK_STAGE_BATCH)?41:handle};
		if (raw.operation==REALM_GPU_GROUP_CONFIGURE || raw.operation==REALM_GPU_TASK_STAGE_BATCH)
			raw.args[0]=(uintptr_t)&cmd,raw.args[2]=1;
		unsigned int old_calls=calls;
		assert(realm_gpu_ioctl(REALM_GPU_CALL,(unsigned long)&raw)==-EBUSY && calls==old_calls);
		assert(managed_task(handle) && token==handle); cases++;
	}
	struct realm_gpu_call raw={.operation=REALM_GPU_TASK_CANCEL,.handle=handle};
	admin=false;
	assert(realm_gpu_ioctl(REALM_GPU_CALL,(unsigned long)&raw)==-EPERM);
	admin=true; copy_fault=true;
	assert(realm_gpu_ioctl(REALM_GPU_CALL,(unsigned long)&raw)==-EFAULT);
	copy_fault=false; cases+=2;
	struct realm_gpu_call result;
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_START,&result)==-EINVAL);
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_READY,&result)==-EBUSY);
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_PROGRESS,&result)==-EBUSY);cases++;
	rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
	assert(!response.ret && response.state==4 && response.token==handle && response.queue==1);
	rpc(PANTHOR_VMSHM_RMM_TASK_START,handle);
	assert(response.ret==-EBUSY && !response.token);
	partial=true;
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_READY,&result)==-EAGAIN && !result.result[0]);
	partial=false;
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY,&result));
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_PUBLISH,&result)==-EINVAL);cases++;
	unsigned int old_calls=calls;
	assert(realm_gpu_task_publish(task,64,&result)==-EINVAL && calls==old_calls);cases++;
	assert(!realm_gpu_task_publish(task,2,&result) && result.result[0]==2 &&
	       result.result[1]==6 && result.result[2]==3 && phase==3);cases++;
	for(u32 bad=1;bad<=4;bad++) {
		reply_fault=bad;
		assert(realm_gpu_task_publish(task,3,&result)==-EPROTO && !result.result[0] &&
		       managed_task(handle) && phase==3);cases++;
	}
	reply_fault=0;partial=true;
	assert(realm_gpu_task_publish(task,3,&result)==-EPROTO && !result.result[0]);cases++;
	partial=false;
	rpc(PANTHOR_VMSHM_RMM_TASK_START,handle);
	assert(!response.ret && phase==4);
	assert(!realm_gpu_task_publish(task,63,&result) && result.result[0]==63 &&
	       phase==4 && managed_task(handle));cases++;
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_PROGRESS,&result) && !result.result[0]);cases++;
	progress_mask=2;
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_PROGRESS,&result) && result.result[0]==2 &&
	       result.result[1]==6 && result.result[2]==3 && phase==4 && managed_task(handle));cases++;
	partial=true;
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_PROGRESS,&result)==-EAGAIN && !result.result[0]);
	partial=false;cases++;
	progress_mask=63;
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_PROGRESS,&result) && result.result[0]==63 &&
	       phase==4 && managed_task(handle));
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_RETURN,&result)==-EBUSY);cases++;
	for(u32 bad=1;bad<=4;bad++) {
		reply_fault=bad;
		assert(realm_gpu_task_call(task,REALM_GPU_TASK_PROGRESS,&result)==-EPROTO &&
		       !result.result[0] && managed_task(handle) && phase==4);cases++;
	}
	reply_fault=0;
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_COMPLETE,&result)==-EAGAIN);
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_RETURN,&result)==-EBUSY);
	done=true;
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_COMPLETE,&result));
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_RETIRE,&result)==-EBUSY);
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_RETURN,&result));
	partial=true;
	assert(realm_gpu_task_call(task,REALM_GPU_TASK_RETIRE,&result)==-EAGAIN && managed_task(handle));
	partial=false;
	assert(!realm_gpu_task_call(task,REALM_GPU_TASK_RETIRE,&result));
	assert(!realm_gpu_task_handle(task) && !managed_task(handle));
	realm_gpu_task_put(task); cases++;
	/* A live token is never freed merely because its owner abandons it. */
	task=stage(); handle=realm_gpu_task_handle(task);
	rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
	unsigned int before=calls;
	realm_gpu_task_put(task);
	assert(managed_task(handle) && calls==before+1 && phase==2);
	reset(); cases++;
	/* Lost responses cause no replay, READY, cache return or retirement. */
	task=stage(); handle=realm_gpu_task_handle(task); lost_response=true;
	unsigned int service_before=service_calls;
	rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
	assert(service_calls==service_before+1 && phase==2);
	realm_gpu_task_put(task); reset(); cases++;
	/* Missing/foreign session, channel, group, VM and malformed actions. */
	for (unsigned int bad=0;bad<9;bad++) {
		task=stage(); handle=realm_gpu_task_handle(task);
		struct panthor_vmshm_rmm_task_req req={.session_id=9,.token=handle,
			.client_group_handle=3,.action=PANTHOR_VMSHM_RMM_TASK_PREPARE};
		struct panthor_vmshm_rmm_task_rsp rsp={0};
		struct proxy_comm_vmshm_channel other=channel;
		service_before=service_calls;
		if (bad==0) req.session_id=10;
		if (bad==1) req.action=6;
		if (bad==2) req.token=0;
		if (bad==3) session.closing=true;
		if (bad==4) req.client_group_handle=7;
		if (bad==5) proxy_group.private_group=0;
		if (bad==6) proxy_vm.rmm_private=false;
		if (bad==7) proxy_vm.proxy_vm_id=99;
		assert(panthor_proxy_session_rmm_task(&session,bad==8?&other:&channel,&req,&rsp)<0);
		assert(service_calls==service_before && !rsp.token);
		session.closing=false; proxy_group.private_group=41;
		proxy_vm.rmm_private=true; proxy_vm.proxy_vm_id=12;
		realm_gpu_task_put(task); assert(!token); cases++;
	}
	/* Every typed Proxy reply field is validated; no retry after bad ACK. */
	for (unsigned int bad=1;bad<=4;bad++) {
		task=stage(); handle=realm_gpu_task_handle(task); reply_fault=bad;
		service_before=service_calls;
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
		assert(response.ret==-EPROTO && !response.token && service_calls==service_before+1);
		realm_gpu_task_put(task); reset(); cases++;
	}
	/* Client COMPLETE reply corruption cannot become release authority. */
	for (unsigned int bad=1;bad<=4;bad++) {
		task=stage(); handle=realm_gpu_task_handle(task);
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY,&result));
		rpc(PANTHOR_VMSHM_RMM_TASK_START,handle);
		done=true; reply_fault=bad;
		assert(realm_gpu_task_call(task,REALM_GPU_TASK_COMPLETE,&result)==-EPROTO);
		assert(managed_task(handle) && !result.result[0]);
		realm_gpu_task_put(task); reset(); cases++;
	}
	/* Successful persistent-state retirement legitimately scrubs zero pages;
	 * malformed flags/queue/reserved/count or incomplete zero-progress cannot
	 * release the kernel token. Exercise actual task_call parsing, not a mock.
	 */
	for (unsigned int bad=0;bad<=6;bad++) {
		task=stage(); handle=realm_gpu_task_handle(task);
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY,&result));
		rpc(PANTHOR_VMSHM_RMM_TASK_START,handle);
		done=true;
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_COMPLETE,&result));
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_RETURN,&result));
		retire_preserve=true;retire_fault=bad;partial=bad>=5;
		int ret=realm_gpu_task_call(task,REALM_GPU_TASK_RETIRE,&result);
		if (!bad) assert(!ret && result.result[0]==1 && !result.result[2] &&
			!realm_gpu_task_handle(task) && !managed_task(handle));
		else assert(ret==-EPROTO && !result.result[0] && managed_task(handle));
		realm_gpu_task_put(task);reset();cases++;
	}
	/* Compound cleanup: pre-COMPLETE refusal, bounded continuation, exact
	 * token retirement, and every malformed success/pending field retained.
	 */
	for (unsigned int pending=0;pending<2;pending++) for (unsigned int bad=0;bad<=4;bad++) {
		task=stage(); handle=realm_gpu_task_handle(task);
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY,&result));
		rpc(PANTHOR_VMSHM_RMM_TASK_START,handle);
		assert(realm_gpu_task_call(task,REALM_GPU_TASK_RECLAIM,&result)==-EBUSY && managed_task(handle));
		done=true;
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_COMPLETE,&result));
		partial=pending;reply_fault=bad;
		int ret=realm_gpu_task_call(task,REALM_GPU_TASK_RECLAIM,&result);
		if (bad) assert(ret==-EPROTO && managed_task(handle) && !result.result[0]);
		else if (pending) {
			assert(ret==-EAGAIN && managed_task(handle) && realm_gpu_task_handle(task)==handle);
			partial=false;
			assert(!realm_gpu_task_call(task,REALM_GPU_TASK_RECLAIM,&result) && !managed_task(handle));
		} else assert(!ret && !managed_task(handle) && !realm_gpu_task_handle(task));
		reply_fault=0;realm_gpu_task_put(task);reset();cases++;
	}
	/* Combined preparation preserves typed pending/success parsing and holds
	 * the token on every malformed field; publication is not retirement.
	 */
	for (unsigned int pending=0;pending<2;pending++) for (unsigned int bad=0;bad<=4;bad++) {
		if (bad==3) continue; /* Cumulative pages are telemetry, not a completion flag. */
		task=stage(); handle=realm_gpu_task_handle(task);
		assert(realm_gpu_task_call(task,REALM_GPU_TASK_READY_PUBLISH,&result)==-EBUSY);
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE,handle);
		partial=pending;reply_fault=bad;
		int ret=realm_gpu_task_call(task,REALM_GPU_TASK_READY_PUBLISH,&result);
		assert(managed_task(handle) && realm_gpu_task_handle(task)==handle);
		if (bad) assert(ret==-EPROTO && !result.result[0]);
		else if (pending) {
			assert(ret==-EAGAIN && !result.result[0]);
			partial=false;
			assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY_PUBLISH,&result));
		} else assert(!ret && result.result[0]==1);
		reply_fault=0;realm_gpu_task_put(task);reset();cases++;
	}
	/* New selected-task path: Proxy permission then Client readiness starts,
	 * never completes or retires. Strict reply checks and managed raw denial.
	 */
	for (unsigned int pending=0;pending<2;pending++) for (unsigned int bad=0;bad<=4;bad++) {
		if (bad==3) continue; /* Cumulative cache pages remain telemetry. */
		task=stage();handle=realm_gpu_task_handle(task);
		assert(realm_gpu_task_call(task,REALM_GPU_TASK_READY_LAUNCH,&result)==-EBUSY);
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH,handle);
		partial=pending;reply_fault=bad;
		int ret=realm_gpu_task_call(task,REALM_GPU_TASK_READY_LAUNCH,&result);
		assert(managed_task(handle) && realm_gpu_task_handle(task)==handle);
		if (bad) assert(ret==-EPROTO && !result.result[0]);
		else if (pending) {
			assert(ret==-EAGAIN && !result.result[0] && phase==2);
			partial=false;
			assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY_LAUNCH,&result));
			assert(phase==4 && managed_task(handle));
		} else assert(!ret && result.result[0]==1 && phase==4);
		reply_fault=0;realm_gpu_task_put(task);reset();cases++;
	}
	/* FINISH: distinguish GPU pending/CPU return; only exact retirement removes
	 * the managed token. Malformed success/pending preserves kernel ownership.
	 */
	for (unsigned int state=0;state<3;state++) for (unsigned int bad=0;bad<=5;bad++) {
		if (state==2 && bad==4) continue; /* kind=1 is valid CPU continuation. */
		task=stage();handle=realm_gpu_task_handle(task);
		assert(realm_gpu_task_call(task,REALM_GPU_TASK_FINISH,&result)==-EBUSY);
		rpc(PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH,handle);
		assert(!realm_gpu_task_call(task,REALM_GPU_TASK_READY_LAUNCH,&result));
		done=state!=1;partial=state==2;reply_fault=bad;
		int ret=realm_gpu_task_call(task,REALM_GPU_TASK_FINISH,&result);
		/* A kind=1 pending response is a legal CPU continuation even if the
		 * mock intended a GPU wait; it never authorizes completion. */
		if (state==1 && bad==4) assert(ret==-EAGAIN && result.result[3]==1 && managed_task(handle));
		else if (bad) assert(ret==-EPROTO && managed_task(handle) && !result.result[0]);
		else if (state) {
			assert(ret==-EAGAIN && result.result[3]==(state==2) && managed_task(handle));
			done=true;partial=false;
			assert(!realm_gpu_task_call(task,REALM_GPU_TASK_FINISH,&result));
			assert(!managed_task(handle) && !realm_gpu_task_handle(task));
		} else assert(!ret && !managed_task(handle) && !realm_gpu_task_handle(task));
		reply_fault=0;realm_gpu_task_put(task);reset();cases++;
	}
	/* Feature negotiation requires each of the actual lifecycle capabilities. */
	for (unsigned int op=REALM_GPU_TASK_HEAP_EVENT;op<=REALM_GPU_TASK_HEAP_GROW;op++) {
		task=stage();handle=realm_gpu_task_handle(task);
		struct realm_gpu_call raw={.operation=op,.handle=handle};
		unsigned int before=calls;
		assert(realm_gpu_ioctl(REALM_GPU_CALL,(unsigned long)&raw)==-EBUSY && calls==before);
		assert(realm_gpu_task_call(task,op,&result)==-EINVAL && calls==before);
		realm_gpu_task_put(task);reset();cases++;
	}
	const u64 all_caps=33554427ULL|REALM_GPU_CAP_TASK_READY_LAUNCH;
	struct realm_gpu_call caps={.result={REALM_GPU_ABI,all_caps,0,0}};
	assert(panthor_proxy_rmm_task_control_available(&caps));
	const u64 required[]={REALM_GPU_CAP_TASK_BATCH,REALM_GPU_CAP_TASK_PREPARE,
		REALM_GPU_CAP_TASK_READY,REALM_GPU_CAP_TASK_START,REALM_GPU_CAP_TASK_QUIESCE,
		REALM_GPU_CAP_TASK_COMPLETE,REALM_GPU_CAP_TASK_RETURN,REALM_GPU_CAP_TASK_RETIRE,REALM_GPU_CAP_TASK_READY_LAUNCH};
	for (unsigned int i=0;i<sizeof(required)/sizeof(required[0]);i++) {
		caps.result[1]=all_caps & ~required[i];
		assert(!panthor_proxy_rmm_task_control_available(&caps)); cases++;
	}
    for(unsigned int mode=0;mode<9;mode++) {
        reset();delegated_stage=true;struct realm_gpu_task *t=stage();assert(!IS_ERR(t));
        if(mode==1)partial=true;
        if(mode>=2 && mode<=5)reply_fault=mode-1;
        if(mode==6)transport_failure=true;
        if(mode==7)lost_response=true;
        if(mode==8)delegated_stage=false;
        unsigned int before=service_calls;
        rpc(PANTHOR_VMSHM_RMM_TASK_DISPATCH,realm_gpu_task_handle(t));
        assert(service_calls==before+1);
        if(mode>=2 && mode<=6)assert(response.ret<0 && !response.token);
        else if(mode==8)assert(response.ret==-EBUSY);
        else assert(!response.ret && response.state==(mode==1?4:5));
        assert(token && managed_task(token));realm_gpu_task_put(t);reset();cases++;
        delegated_stage=false;
    }
	reset(); list_del(&group.link);
	assert(allocations==frees && session_puts && sends && cancel_calls);
	printf("GPU_TASK_BRIDGE=PASS cases=%u actual kernel token lifecycle and Proxy RPC; copied descriptors, strict session/channel/context binding, typed replies, lost-response no retry, orphan retention, separate completion/return/retire; HOST_DOUBLES_ONLY no DRM scheduling or real GPU\n",cases);
	return 0;
}
