// SPDX-License-Identifier: GPL-2.0-only
/* Actual planner/worker; doubles below do not prove Linux or GPU execution. */
#include "kernel-doubles.inc"
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define BIT(n) (1U << (n))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK(h,l) ((UINT32_MAX >> (31-(h))) & (UINT32_MAX << (l)))
#define PANTHOR_CLIENT_PRIVATE_BATCH_LIMIT 128
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define pr_warn(...) ((void)0)
#define pr_info(...) ((void)0)
struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *h) { h->next=h->prev=h; }
static bool list_empty(struct list_head *h) { return h->next==h; }
static void list_add_tail(struct list_head *n,struct list_head *h) {
    n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;
}
static void list_del(struct list_head *n) {n->next->prev=n->prev;n->prev->next=n->next;}
#define list_entry(p,t,m) container_of(p,t,m)
#define list_for_each_entry(p,h,m) \
    for(p=list_entry((h)->next,__typeof__(*p),m);&p->m!=(h);p=list_entry(p->m.next,__typeof__(*p),m))
#define list_for_each_entry_safe(p,n,h,m) \
    for(p=list_entry((h)->next,__typeof__(*p),m),n=list_entry(p->m.next,__typeof__(*p),m); \
        &p->m!=(h);p=n,n=list_entry(n->m.next,__typeof__(*n),m))
static bool refcount_inc_not_zero(refcount_t *r) {if(!r->value)return false;r->value++;return true;}
struct delayed_work { struct work_struct work; };
#define to_delayed_work(w) container_of(w,struct delayed_work,work)
static struct delayed_work *scheduled;
static unsigned long scheduled_delay;
static u64 profile_clock, simulated_pause_ns;
static void (*complete_pause_hook)(void);
static void check_complete_pause(void);
static void cpu_relax(void) {
    check_complete_pause();profile_clock+=1000+simulated_pause_ns;simulated_pause_ns=0;
    if(complete_pause_hook)complete_pause_hook();
}
static u64 ktime_get_ns(void) { return ++profile_clock; }
static unsigned int destroyed;
static unsigned long msecs_to_jiffies(unsigned long n) {return n;}
static bool queue_delayed_work(struct workqueue_struct *q,struct delayed_work *w,unsigned long delay) {
    assert(!scheduled || scheduled==w);if(scheduled)return false;scheduled=w;scheduled_delay=delay;return true;
}
static void cancel_delayed_work_sync(struct delayed_work *w) {if(scheduled==w)scheduled=NULL;}
static void destroy_workqueue(struct workqueue_struct *q) {destroyed++;}
struct realm_gpu_group { u64 handle; };
struct realm_gpu_task { u64 handle;bool retired; };
#include "structures.inc"
struct panthor_client_private_run;
struct panthor_client_file {
    u64 session_id;struct mutex private_submit_lock,private_gpu_lock,lock;
    bool private_closing,private_gpu_failed,private_data,private_dispatch;
    struct workqueue_struct *private_gpu_wq;
    struct delayed_work private_gpu_work;
    struct list_head private_jobs,private_map_waiters;
    struct panthor_client_private_run *private_run;
    atomic_t private_gpu_pending;
    u64 private_phase_calls[7],private_phase_ns[7],private_phase_again[7],private_phase_gap_ns[7];
    u64 private_phase_pages[7],private_phase_empty_calls[7],private_phase_empty_ns[7];
    u64 private_cache_regressions;
    u64 private_retired_slices, private_local_hint_skips, private_local_hint_tasks;
    u64 private_hint_pause_watches,private_hint_pause_early,private_hint_pause_reads;
    u64 private_complete_wait_calls[5],private_complete_wait_ns[5];
    u64 private_complete_wait_max_ns[5],private_complete_wait_late[5];
    u64 private_first_poll_pauses,private_first_poll_pause_ns,private_poll_trainings;
    struct xarray groups,heaps;
};
static struct panthor_client_file *sleep_file;
static void check_complete_pause(void) {
    assert(sleep_file && !sleep_file->private_gpu_lock.held && !sleep_file->lock.held &&
        !sleep_file->private_submit_lock.held);
}
struct drm_device { unsigned int unused; };
static unsigned int heap_creates,heap_destroys;
static int heap_error;
static int panthor_client_tiler_heap_create(struct panthor_client_file *p,struct drm_panthor_tiler_heap_create *a) {
    if(p->private_data)assert(p->private_gpu_lock.held && p->private_submit_lock.held);
    heap_creates++;return heap_error;
}
static int panthor_client_tiler_heap_destroy(struct panthor_client_file *p,u32 handle) {
    if(p->private_data)assert(p->private_gpu_lock.held && p->private_submit_lock.held);
    heap_destroys++;return heap_error;
}
static unsigned int destroy_rpc,group_releases;
static int panthor_client_group_destroy_rpc_session(u64 session,u32 id,u32 *proxy) {
    assert(session==222 && id);destroy_rpc++;return 0;
}
static void realm_gpu_group_put(struct realm_gpu_group *g) {if(g)group_releases++;}
static int copy_struct_from_user(void *dst,size_t n,const void *src,size_t stride) {
    if(!src)return -EFAULT;
    memset(dst,0,n);memcpy(dst,src,stride<n?stride:n);return 0;
}
static u64 client_comm_vmshm_rmm_channel(void) {return 77;}
static u64 realm_gpu_task_handle(const struct realm_gpu_task *t) {assert(t);return t->handle;}
static struct realm_gpu_task_command observed[REALM_GPU_TASK_BATCH_MAX];
static unsigned int stages,observed_count,retires,abandoned,task_frees,cancels;
static u64 last_canceled;
static int stage_error,operation_error,rpc_error,cancel_error;
static u32 error_operation,error_action;
static unsigned int operation_calls[64],rpc_calls[6];
static unsigned int again[64];
static u64 timed_gpu_duration_ns,timed_gpu_ready_at;
static unsigned int heap_calls,heap_again,return_again,return_progress_calls;
static int heap_service_error;
static int realm_gpu_task_heap_service(struct realm_gpu_task *t) {
    assert(t && !t->retired);heap_calls++;
    if(heap_service_error)return heap_service_error;
    if(heap_again){heap_again--;return -EAGAIN;}
    return 0;
}
static unsigned int malformed,dispatch_state;
static bool staged_delegation;
static struct realm_gpu_task *realm_gpu_task_stage(struct realm_gpu_group *g,u64 channel,
        const struct realm_gpu_task_command *commands,u32 count,bool delegate) {
    assert(g && channel==77 && count && count<=REALM_GPU_TASK_BATCH_MAX);stages++;staged_delegation=delegate;
    if(stage_error)return ERR_PTR(stage_error);
    observed_count=count;memcpy(observed,commands,count*sizeof(*commands));
    struct realm_gpu_task *t=calloc(1,sizeof(*t));assert(t);t->handle=1000+stages;return t;
}
static int realm_gpu_task_call(struct realm_gpu_task *t,u32 operation,struct realm_gpu_call *r) {
    assert(t && !t->retired && operation<64);operation_calls[operation]++;
    memset(r,0,sizeof(*r));
    if(operation==error_operation)return operation_error;
    if(again[operation]){again[operation]--;return -EAGAIN;}
    if(operation==REALM_GPU_TASK_READY_LAUNCH && timed_gpu_duration_ns)
        timed_gpu_ready_at=profile_clock+timed_gpu_duration_ns;
    if(operation==REALM_GPU_TASK_FINISH && timed_gpu_ready_at && profile_clock<timed_gpu_ready_at)
        return -EAGAIN;
    if(operation==REALM_GPU_TASK_FINISH && return_again){
        return_again--;return_progress_calls++;r->result[3]=1;return -EAGAIN;
    }
    if(operation==REALM_GPU_TASK_FINISH){t->retired=true;retires++;}
    return 0;
}
static int realm_gpu_task_publish(struct realm_gpu_task *t,u64 members,struct realm_gpu_call *r) {
    assert(members==BIT_ULL(observed_count)-1);return realm_gpu_task_call(t,REALM_GPU_TASK_PUBLISH,r);
}
static int realm_gpu_task_cancel_unprepared(struct realm_gpu_task *t) {
    assert(t && t->handle && !t->retired);cancels++;
    if(cancel_error)return cancel_error;
    assert(t->handle>last_canceled);last_canceled=t->handle;t->handle=0;return 0;
}
static void realm_gpu_task_put(struct realm_gpu_task *t) {
    if(!t)return;
    if(t->handle && !t->retired)abandoned++;
    task_frees++;free(t); /* Counts abandoned holds; real typed helper retains them. */
}
static int panthor_client_rpc_call(u32 req_type,const void *req,u32 req_len,u32 rsp_type,
        void *rsp,u32 capacity,u32 min_len,void *rx) {
    const struct panthor_vmshm_rmm_task_req *q=req;
    struct panthor_vmshm_rmm_task_rsp *r=rsp;
    assert(req_type==PANTHOR_VMSHM_MSG_RMM_TASK_REQ && rsp_type==PANTHOR_VMSHM_MSG_RMM_TASK_RSP);
    assert(req_len==sizeof(*q) && capacity==sizeof(*r) && min_len==sizeof(*r));
    assert(q->session_id==222 && q->token==1000+stages && q->client_group_handle);
    assert(q->action && q->action<6);rpc_calls[q->action]++;
    if(q->action==error_action)return rpc_error;
    *r=(struct panthor_vmshm_rmm_task_rsp){.state=q->action==PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH?4:q->action+3,.token=q->token,.queue=observed[0].queue};
    if(q->action==PANTHOR_VMSHM_RMM_TASK_DISPATCH)r->state=dispatch_state;
    if(malformed==1)r->token++;
    if(malformed==2)r->state++;
    if(malformed==3)r->queue++;
    if(malformed==4)r->pad=1;
    if(malformed==5)r->ret=1;
    return 0;
}
static bool hint_enabled, hint_pending;
static bool realm_gpu_task_has_hint(struct realm_gpu_task *t) { assert(t && !t->retired); return hint_enabled && observed_count==1; }
static bool realm_gpu_task_hint_pending(struct realm_gpu_task *t) { assert(t && !t->retired); return hint_pending; }
#include "actual.inc"

static struct panthor_client_file pc;
static struct drm_file file;
static struct workqueue_struct wq;
static struct realm_gpu_group native_group={.handle=111};
static struct panthor_client_group *group;
static struct drm_panthor_queue_submit inputs[6];
static struct drm_panthor_sync_op syncs[16];
static struct drm_panthor_group_submit args;
static unsigned int cases;
static void setup(void) {
    assert(!scheduled && !queued_count && fence_allocs==fence_frees);
    memset(&pc,0,sizeof(pc));memset(&file,0,sizeof(file));
    memset(inputs,0,sizeof(inputs));memset(syncs,0,sizeof(syncs));
    memset(operation_calls,0,sizeof(operation_calls));memset(rpc_calls,0,sizeof(rpc_calls));
    memset(again,0,sizeof(again));scheduled_delay=0;
    sleep_file=&pc;complete_pause_hook=NULL;hint_enabled=hint_pending=false;
    profile_clock=0;simulated_pause_ns=0;
    timed_gpu_duration_ns=timed_gpu_ready_at=0;
    heap_calls=heap_again=return_again=return_progress_calls=0;heap_service_error=0;
    dispatch_state=5;staged_delegation=false;
    stages=observed_count=retires=abandoned=task_frees=cancels=0;last_canceled=0;
    stage_error=operation_error=rpc_error=cancel_error=0;error_operation=error_action=malformed=0;
    destroy_rpc=group_releases=destroyed=0;fail_alloc_after=-1;
    for(unsigned int i=1;i<16;i++)file.objects[i].refs=1;
    group=calloc(1,sizeof(*group));assert(group);
    *group=(struct panthor_client_group){.session_id=222,.client_handle=1,
        .private_group=&native_group,.private_vm_id=7,.private_queue_count=16,
        .private_user_va_end=0x80000000};
    refcount_set(&group->refcnt,1);
    pc.groups.entries[1]=group;pc.session_id=222;pc.private_gpu_wq=&wq;pc.private_data=true;file.driver_priv=&pc;
    pc.private_gpu_work.work.fn=panthor_client_private_gpu_work;
    INIT_LIST_HEAD(&pc.private_jobs);
    INIT_LIST_HEAD(&pc.private_map_waiters);
    heap_creates=heap_destroys=0;heap_error=0;wait_hook=NULL;
    args=(struct drm_panthor_group_submit){.group_handle=1,
        .queue_submits={.array=(uintptr_t)inputs,.count=1,.stride=sizeof(inputs[0])}};
    for(unsigned int i=0;i<6;i++)inputs[i]=(struct drm_panthor_queue_submit){
        .queue_index=i,.stream_addr=0x200000+i*0x1000,.stream_size=64};
    cases++;
}
static void tick(void) {
    assert(scheduled);
    struct delayed_work *w=scheduled;scheduled=NULL;jiffies++;w->work.fn(&w->work);
}
static void drain(void) {
    unsigned int limit=2048;
    while(scheduled && limit--)tick();
    assert(!scheduled);
}
static void cleanup(void) {
    pc.private_closing=true;panthor_client_private_gpu_stop(&pc);
    assert(!pc.private_run && !pc.private_gpu_pending.value && !scheduled);
    assert(list_empty(&pc.private_jobs));
    assert(list_empty(&pc.private_map_waiters));
    assert(!pc.lock.held && !pc.private_gpu_lock.held && !pc.private_submit_lock.held);
    if(group){assert(group->refcnt.value==1);panthor_client_group_put(group);group=NULL;}
    for(unsigned int i=1;i<16;i++){
        assert(file.objects[i].refs==1);dma_fence_put(file.objects[i].fence);file.objects[i].fence=NULL;
    }
    assert(fence_allocs==fence_frees);
}
static int submit(void) {return panthor_client_private_group_submit(&pc,&file,&args);}
static void signal_op(unsigned int i,u32 handle,u64 point) {
    syncs[i]=(struct drm_panthor_sync_op){.handle=handle,.timeline_value=point,
        .flags=DRM_PANTHOR_SYNC_OP_SIGNAL|(point?DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ:0)};
}
static void sync_range(unsigned int job,unsigned int first,unsigned int count) {
    inputs[job].syncs=(struct drm_panthor_obj_array){.array=(uintptr_t)&syncs[first],
        .count=count,.stride=sizeof(syncs[0])};
}
static int status(u32 id) {assert(file.objects[id].fence);return dma_fence_get_status(file.objects[id].fence);}
static struct dma_fence *external(u32 handle,bool signaled,int error) {
    struct dma_fence *f=panthor_client_private_fence_alloc();assert(f);
    if(error)dma_fence_set_error(f,error);
    if(signaled)dma_fence_signal(f);
    drm_syncobj_replace_fence(&file.objects[handle],f);return f;
}
static void advance_for_mapping(void) {
    assert(!pc.private_gpu_lock.held && panthor_client_private_mapping_waiting(&pc,7));
    if(scheduled)tick();
}
static void advance_and_pick(void) {
    advance_for_mapping();
    if(!pc.private_run && scheduled)tick(); /* Give the GPU worker first access. */
}
static void close_for_mapping(void) {pc.private_closing=true;wait_hook=NULL;}
static void close_in_complete_sleep(void) { pc.private_closing=true; }
static void expire_in_complete_sleep(void) { jiffies=pc.private_run->deadline; }
static void nested_mapping(void) {
    wait_hook=advance_for_mapping;
    assert(!panthor_client_private_mapping_lock(&pc,7) && pc.private_gpu_lock.held);
    mutex_unlock(&pc.private_gpu_lock);wait_hook=NULL;
    assert(panthor_client_private_mapping_waiting(&pc,7)); /* Outer ticket survives. */
}
static u64 hint_arrive_at;
static void arrive_in_hint_pause(void) {
    assert(pc.private_run && pc.private_run->task && !pc.private_run->task->retired);
    assert(!pc.private_gpu_lock.held);
    if(profile_clock>=hint_arrive_at)hint_pending=false;
}
int main(void) {
    /* Hints are per queue and only schedule a later real FINISH. A timed GPU
     * double verifies fewer premature queries without manufacturing success.
     */
    setup();signal_op(0,2,0);sync_range(0,0,1);timed_gpu_duration_ns=300000;
    unsigned int first_queries=0,last_queries=0;
    for(unsigned int i=0;i<12;i++){
        unsigned int before=operation_calls[REALM_GPU_TASK_FINISH];
        assert(!submit());drain();assert(status(2)==1 && retires==i+1);
        unsigned int queries=operation_calls[REALM_GPU_TASK_FINISH]-before;
        if(!i)first_queries=queries;
        last_queries=queries;
        assert(group->private_poll_delay_ns[0]<=PANTHOR_CLIENT_PRIVATE_POLL_DELAY_MAX_NS);
        assert(pc.private_poll_trainings==i+1);
    }
    assert(last_queries<first_queries && group->private_poll_delay_ns[0]>0);
    assert(pc.private_first_poll_pauses==11 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START]);cleanup();

    for(unsigned int mode=0;mode<3;mode++){
        setup();signal_op(0,2,0);sync_range(0,0,1);
        group->private_poll_delay_ns[0]=mode==2?UINT64_MAX:80000;
        if(mode==1)return_again=3;
        assert(!submit());drain();assert(status(2)==1 && retires==1 && !heap_calls);
        assert(pc.private_first_poll_pauses==1 && pc.private_poll_trainings==1);
        assert(group->private_poll_delay_ns[0]==(mode==2?150000:60000));
        assert(pc.private_first_poll_pause_ns<=PANTHOR_CLIENT_PRIVATE_POLL_DELAY_MAX_NS+1000);
        cleanup();
    }
    for(unsigned int mode=0;mode<2;mode++){
        setup();signal_op(0,2,0);sync_range(0,0,1);group->private_poll_delay_ns[0]=80000;
        if(mode){again[REALM_GPU_TASK_FINISH]=1;heap_service_error=-EPROTO;}
        else{error_operation=REALM_GPU_TASK_FINISH;operation_error=-EIO;}
        assert(!submit());drain();assert(status(2)==(mode?-EPROTO:-EIO));
        assert(!pc.private_poll_trainings && group->private_poll_delay_ns[0]==80000 && !retires);
        assert(abandoned==1);cleanup();
    }
    setup();args.queue_submits.count=2;group->private_poll_delay_ns[0]=200000;
    group->private_poll_delay_ns[1]=150000;
    signal_op(0,2,0);signal_op(1,3,0);sync_range(0,0,1);sync_range(1,1,1);
    assert(!submit());drain();assert(status(2)==1 && status(3)==1 && retires==1);
    assert(!pc.private_poll_trainings && !pc.private_first_poll_pauses &&
        group->private_poll_delay_ns[0]==200000 && group->private_poll_delay_ns[1]==150000);cleanup();

    for(unsigned int mode=0;mode<2;mode++){
        setup();signal_op(0,2,0);sync_range(0,0,1);group->private_poll_delay_ns[0]=200000;
        complete_pause_hook=mode?expire_in_complete_sleep:close_in_complete_sleep;
        assert(!submit());drain();assert(!operation_calls[REALM_GPU_TASK_FINISH] && !retires);
        assert(pc.private_first_poll_pauses==1 && !pc.private_poll_trainings);
        if(mode)assert(status(2)==-ETIMEDOUT && abandoned==1);
        else assert(!status(2) && pc.private_run);
        cleanup();
    }
    setup();signal_op(0,2,0);sync_range(0,0,1);timed_gpu_duration_ns=300000;
    assert(!submit());drain();u64 queue0_hint=group->private_poll_delay_ns[0];assert(queue0_hint>0);
    inputs[0].queue_index=1;assert(!submit());drain();
    assert(group->private_poll_delay_ns[0]==queue0_hint && group->private_poll_delay_ns[1]>0);
    assert(!pc.private_first_poll_pauses && pc.private_poll_trainings==2);cleanup();

    /* A descheduling outlier is capped and still needs trusted completion. */
    setup();signal_op(0,2,0);sync_range(0,0,1);again[REALM_GPU_TASK_FINISH]=1;
    assert(!submit());while(pc.private_run==NULL || pc.private_run->phase!=PANTHOR_PRIVATE_COMPLETE)tick();
    profile_clock+=2000000000ULL;tick();assert(!status(2) && !retires);
    drain();assert(status(2)==1 && retires==1 && group->private_poll_delay_ns[0]==50000);cleanup();

    /* CPU-only cursor continuations should not pay a timer tick. Each work
     * item still makes one bounded call, releases the mutex and retains the
     * exact original deadline; true GPU pending/OOM sleeps outside the lock.
     */
    const u32 continuation_ops[]={REALM_GPU_TASK_READY_LAUNCH,REALM_GPU_TASK_FINISH,
        REALM_GPU_TASK_RECLAIM};
    for(unsigned int i=0;i<ARRAY_SIZE(continuation_ops);i++) {
        setup();signal_op(0,2,0);sync_range(0,0,1);
        u32 op=i==2?REALM_GPU_TASK_FINISH:continuation_ops[i];
        if(i==2)return_again=2;else again[op]=2;
        assert(!submit());
        while(!operation_calls[op])tick();
        unsigned long deadline=pc.private_run->deadline;
        assert(operation_calls[op]==1 && scheduled && !pc.private_gpu_lock.held && !status(2));
        u32 phase=pc.private_run->phase;
        assert(pc.private_phase_calls[phase]==1 && pc.private_phase_again[phase]==1 &&
            pc.private_phase_ns[phase]>0);
        assert(scheduled_delay==0 && pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==(i==1?1:0));
        if(i==1)assert(pc.private_complete_wait_max_ns[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]>=50000 &&
            pc.private_complete_wait_max_ns[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]<=51000);
        tick();
        assert(operation_calls[op]==2 && pc.private_run->deadline==deadline && !status(2));
        assert(pc.private_phase_calls[phase]==2 && pc.private_phase_again[phase]==2 &&
            pc.private_phase_gap_ns[phase]>0);
        assert(scheduled_delay==0 && pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==(i==1?2:0));
        drain();assert(status(2)==1 && retires==1 && !abandoned &&
            !operation_calls[REALM_GPU_TASK_READY] && !operation_calls[REALM_GPU_TASK_PUBLISH] &&
            !pc.private_phase_calls[PANTHOR_PRIVATE_PUBLISH]);cleanup();
    }
    /* Only eight short retries, then the original delayed polling; each
     * turn issues one real COMPLETE under the same deadline, no START replay.
     */
    setup();signal_op(0,2,0);sync_range(0,0,1);again[REALM_GPU_TASK_FINISH]=12;
    assert(!submit());
    while(operation_calls[REALM_GPU_TASK_FINISH]<8)tick();
    unsigned long complete_deadline=pc.private_run->deadline;
    assert(pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==8 && scheduled_delay==0 && !status(2));
    for(unsigned int i=8;i<12;i++) {
        tick();assert(operation_calls[REALM_GPU_TASK_FINISH]==i+1 &&
            pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==8 && scheduled_delay>0 && !status(2) &&
            pc.private_run->deadline==complete_deadline);
    }
    drain();assert(status(2)==1 && retires==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START]);cleanup();
    setup();signal_op(0,2,0);sync_range(0,0,1);again[REALM_GPU_TASK_FINISH]=1;
    complete_pause_hook=close_in_complete_sleep;assert(!submit());drain();
    assert(pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==1 && !scheduled && !status(2) && pc.private_run && !retires);
    panthor_client_private_gpu_stop(&pc);
    assert(status(2)==-ECANCELED && abandoned==1 && !retires);cleanup();
    setup();signal_op(0,2,0);sync_range(0,0,1);again[REALM_GPU_TASK_FINISH]=1;
    complete_pause_hook=expire_in_complete_sleep;assert(!submit());drain();
    assert(pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==1 && status(2)==-ETIMEDOUT && abandoned==1 && !retires);
    assert(operation_calls[REALM_GPU_TASK_FINISH]==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START]);cleanup();
    /* Inject a 20ms active-pause descheduling overrun, then a separate 30ms immediate
     * queue wait and 40ms delayed wait. Diagnostics must distinguish them,
     * preserve the deadline and never complete a fence on a timing sample.
     */
    setup();signal_op(0,2,0);sync_range(0,0,1);again[REALM_GPU_TASK_FINISH]=9;return_again=1;
    simulated_pause_ns=20000000;assert(!submit());
    while(operation_calls[REALM_GPU_TASK_FINISH]<1)tick();
    complete_deadline=pc.private_run->deadline;
    assert(pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==1 &&
        pc.private_complete_wait_ns[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==20001003 &&
        pc.private_complete_wait_max_ns[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==20001003 &&
        pc.private_complete_wait_late[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==1 && !status(2));
    assert(pc.private_complete_wait_ns[PANTHOR_PRIVATE_WAIT_RELOCK]==1);
    simulated_pause_ns=0;profile_clock+=30000000;tick();
    assert(pc.private_complete_wait_late[PANTHOR_PRIVATE_WAIT_QUEUE_IMMEDIATE]==1 &&
        pc.private_complete_wait_max_ns[PANTHOR_PRIVATE_WAIT_QUEUE_IMMEDIATE]==30000001 &&
        pc.private_complete_wait_late[PANTHOR_PRIVATE_WAIT_SHORT_PAUSE]==1 &&
        pc.private_run->deadline==complete_deadline && !status(2));
    while(operation_calls[REALM_GPU_TASK_FINISH]<9)tick();
    assert(scheduled_delay>0 && !status(2));profile_clock+=40000000;tick();
    assert(pc.private_complete_wait_calls[PANTHOR_PRIVATE_WAIT_QUEUE_DELAYED]==1 &&
        pc.private_complete_wait_max_ns[PANTHOR_PRIVATE_WAIT_QUEUE_DELAYED]==40000001 &&
        pc.private_complete_wait_late[PANTHOR_PRIVATE_WAIT_QUEUE_DELAYED]==1 && !status(2));
    drain();assert(status(2)==1 && retires==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START]);cleanup();
    /* Proxy acceptance, real completion, CPU return and retirement are distinct. */
    setup();signal_op(0,2,0);sync_range(0,0,1);
    again[REALM_GPU_TASK_READY_LAUNCH]=2;again[REALM_GPU_TASK_FINISH]=2;
    return_again=4;
    assert(!submit() && !stages && !status(2));
    while(!return_progress_calls){assert(!status(2));tick();}
    assert(!status(2) && !retires && return_progress_calls==1 && !heap_service_error && heap_calls==2 &&
        !operation_calls[REALM_GPU_TASK_RETURN] && !operation_calls[REALM_GPU_TASK_RETIRE]);
    drain();assert(status(2)==1 && retires==1 && !abandoned);
    assert(rpc_calls[PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH]==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START] && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]);cleanup();

    /* OOM handling/continuation never advances COMPLETE, repeats START,
     * signals a fence or extends the original task deadline.
     */
    setup();signal_op(0,2,0);sync_range(0,0,1);
    again[REALM_GPU_TASK_FINISH]=6;heap_again=3;
    assert(!submit());tick();
    unsigned long heap_deadline=pc.private_run->deadline;
    while(pc.private_run->phase!=PANTHOR_PRIVATE_COMPLETE)tick();
    for(unsigned int i=0;i<6;i++) {
        tick();assert(pc.private_run && pc.private_run->phase==PANTHOR_PRIVATE_COMPLETE);
        assert(pc.private_run->deadline==heap_deadline && !status(2) && !retires);
        assert(stages==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START]);
    }
    assert(heap_calls==6 && !heap_again);drain();assert(status(2)==1 && retires==1);cleanup();
    for(unsigned int error=0;error<2;error++) {
        setup();signal_op(0,2,0);sync_range(0,0,1);
        again[REALM_GPU_TASK_FINISH]=1;heap_service_error=error?-EPROTO:-EIO;
        assert(!submit());drain();
        assert(status(2)==heap_service_error && heap_calls==1 && abandoned==1 && !retires);
        assert(stages==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START]);cleanup();
    }

    /* Six independent queue heads can share one RMM lease. */
    setup();args.queue_submits.count=6;
    for(unsigned int i=0;i<6;i++){signal_op(i,i+2,0);sync_range(i,i,1);}
    assert(!submit());tick();assert(observed_count==6);drain();
    for(unsigned int i=0;i<6;i++)assert(status(i+2)==1);
    assert(stages==1 && retires==1);cleanup();

    /* FIFO and per-job output fences, not one fence for the whole ioctl. */
    setup();args.queue_submits.count=2;inputs[1].queue_index=0;
    signal_op(0,2,0);signal_op(1,3,0);sync_range(0,0,1);sync_range(1,1,1);
    assert(!submit());while(!status(2))tick();
    assert(!status(3) && stages==1);drain();assert(stages==2 && status(3)==1);cleanup();

    /* Array-order signal/wait edges leave unrelated queues runnable. */
    setup();args.queue_submits.count=3;signal_op(0,2,0);
    syncs[1]=(struct drm_panthor_sync_op){.handle=2};signal_op(2,3,0);signal_op(3,4,0);
    sync_range(0,0,1);sync_range(1,1,2);sync_range(2,3,1);
    assert(!submit());tick();assert(observed_count==2 && observed[0].queue==0 && observed[1].queue==2);
    while(!status(2))tick();
    assert(status(4)==1 && !status(3));
    drain();assert(status(3)==1 && stages==2);cleanup();

    /* A blocked earlier job must not block a later ioctl on another queue. */
    setup();struct dma_fence *dep=external(1,false,0);
    syncs[0]=(struct drm_panthor_sync_op){.handle=1};signal_op(1,2,0);sync_range(0,0,2);
    assert(!submit());tick();assert(!stages && !status(2));
    inputs[0].queue_index=1;signal_op(0,3,0);sync_range(0,0,1);
    assert(!submit());while(!status(3))tick();assert(stages==1 && !status(2));
    dma_fence_signal(dep);dma_fence_put(dep);drain();assert(stages==2 && status(2)==1);cleanup();

    /* Readiness scanning also bypasses a blocked different group/VM. */
    setup();struct panthor_client_group *other=calloc(1,sizeof(*other));assert(other);
    *other=*group;other->client_handle=2;other->private_vm_id=8;pc.groups.entries[2]=other;
    dep=external(1,false,0);syncs[0]=(struct drm_panthor_sync_op){.handle=1};
    signal_op(1,2,0);sync_range(0,0,2);assert(!submit());
    args.group_handle=2;signal_op(0,3,0);sync_range(0,0,1);assert(!submit());
    while(!status(3))tick();
    assert(stages==1 && !status(2) && !panthor_client_private_gpu_vm_busy(&pc,8));
    dma_fence_signal(dep);dma_fence_put(dep);drain();assert(status(2)==1);
    assert(other->refcnt.value==1);panthor_client_group_put(other);cleanup();

    /* Queue FIFO also applies between ioctls without explicit syncobjs. */
    setup();dep=external(1,false,0);syncs[0]=(struct drm_panthor_sync_op){.handle=1};
    signal_op(1,2,0);sync_range(0,0,2);assert(!submit());
    signal_op(0,3,0);sync_range(0,0,1);assert(!submit());tick();assert(!stages);
    dma_fence_signal(dep);dma_fence_put(dep);drain();assert(stages==2 && status(2)==1 && status(3)==1);cleanup();

    /* Waiting before a later same-batch signal uses the original point fence. */
    setup();dep=external(2,true,0);dma_fence_put(dep);args.queue_submits.count=2;
    syncs[0]=(struct drm_panthor_sync_op){.handle=2};signal_op(1,3,0);signal_op(2,2,0);
    sync_range(0,0,2);sync_range(1,2,1);assert(!submit());tick();assert(observed_count==2);drain();cleanup();
    setup();args.queue_submits.count=2;syncs[0]=(struct drm_panthor_sync_op){.handle=2};
    signal_op(1,2,0);sync_range(0,0,1);sync_range(1,1,1);
    assert(submit()==-EINVAL && !file.objects[2].fence && !scheduled && !group->private_last[0]);cleanup();

    /* Fence-only submission still has queue ordering and trusted retirement. */
    setup();inputs[0].stream_addr=inputs[0].stream_size=0;signal_op(0,2,7);sync_range(0,0,1);
    assert(!submit());drain();assert(status(2)==1 && !observed[0].bytes && retires==1);cleanup();

    /* Dependency errors, including a contained timeline point, never launch. */
    for(unsigned int mode=0;mode<3;mode++){
        setup();dep=external(1,mode!=2,mode==0?-EIO:0);
        if(mode==1){
            struct dma_fence *point=panthor_client_private_fence_alloc();
            dma_fence_set_error(point,-EACCES);dma_fence_signal(point);
            drm_syncobj_add_point(&file.objects[1],dma_fence_chain_alloc(),point,8);dma_fence_put(point);
        }
        dma_fence_put(dep);syncs[0]=(struct drm_panthor_sync_op){.handle=1,.timeline_value=mode==1?8:0,
            .flags=mode==1?DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_TIMELINE_SYNCOBJ:0};
        signal_op(1,2,0);sync_range(0,0,2);assert(!submit());
        if(mode==2)jiffies+=60001;
        drain();assert(status(2)==(mode==0?-EIO:mode==1?-EACCES:-ETIMEDOUT) && !stages);cleanup();
    }

    /* Client-private descriptor snapshots survive user mutation after ioctl. */
    setup();signal_op(0,2,0);sync_range(0,0,1);assert(!submit());
    inputs[0].stream_addr=0xbad;syncs[0].handle=15;drain();
    assert(observed[0].start==0x200000 && status(2)==1 && !file.objects[15].fence);cleanup();

    /* Every malformed Proxy acceptance is a failure, never a completion. */
    for(unsigned int mode=1;mode<=5;mode++){
        setup();malformed=mode;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
        assert(status(2)==-EPROTO && pc.private_gpu_failed && abandoned==1 && !retires);
        assert(rpc_calls[PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH]==1 && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START] && rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]==1 && !operation_calls[REALM_GPU_TASK_READY_LAUNCH]);cleanup();
    }

    /* Lost PREPARE_LAUNCH replies and Proxy EAGAIN must never be replayed. */
    for(unsigned int mode=0;mode<2;mode++){
        const unsigned int action=PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH;
        setup();error_action=action;rpc_error=mode?-EAGAIN:-EIO;
        signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
        assert(status(2)==rpc_error && abandoned==1 && rpc_calls[action]==1 && rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]==1);
        assert(!operation_calls[REALM_GPU_TASK_FINISH]);cleanup();
    }

    /* No READY/PUBLISH/COMPLETE/RETURN/RETIRE failure can turn into success. */
    const u32 operations[]={REALM_GPU_TASK_READY_LAUNCH,REALM_GPU_TASK_FINISH};
    for(unsigned int i=0;i<ARRAY_SIZE(operations);i++){
        setup();error_operation=operations[i];operation_error=-EIO;
        signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
        assert(status(2)==-EIO && !retires && abandoned==1 && pc.private_gpu_failed);
        assert(submit()==-EIO && rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]==1);cleanup();
    }
    setup();again[REALM_GPU_TASK_FINISH]=100000;signal_op(0,2,0);sync_range(0,0,1);
    assert(!submit());while(!operation_calls[REALM_GPU_TASK_FINISH])tick();
    jiffies+=60001;drain();assert(status(2)==-ETIMEDOUT && abandoned==1 && !retires);cleanup();

    /* Shared task capacity waits without dropping jobs or extending deadlines. */
    setup();stage_error=-ENOSPC;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());tick();
    assert(pc.private_run && !status(2) && !pc.private_run->task);
    unsigned long admission_deadline=pc.private_run->deadline;
    tick();tick();
    assert(!status(2) && stages==3 && !cancels && !pc.private_run->task &&
           pc.private_run->deadline==admission_deadline && !pc.private_gpu_failed && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH]);
    stage_error=0;drain();assert(status(2)==1 && stages==4 && retires==1 && !abandoned);cleanup();

    setup();stage_error=-ENOSPC;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());tick();
    jiffies=pc.private_run->deadline-1;tick();
    assert(status(2)==-ETIMEDOUT && !scheduled && !cancels && !pc.private_gpu_failed && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]);
    stage_error=0;inputs[0].queue_index=1;signal_op(0,3,0);assert(!submit());drain();assert(status(3)==1);cleanup();

    setup();stage_error=-ENOSPC;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());tick();
    pc.private_closing=true;panthor_client_private_gpu_stop(&pc);
    assert(status(2)==-ECANCELED && !cancels && !abandoned && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]);cleanup();

    /* Full CSGs require trusted cancellation, then staging a fresh exact token. */
    setup();error_action=PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH;rpc_error=-ENOSPC;
    args.queue_submits.count=2;inputs[1].queue_index=0;
    signal_op(0,2,0);signal_op(1,3,0);sync_range(0,0,1);sync_range(1,1,1);
    assert(!submit());tick();admission_deadline=pc.private_run->deadline;tick();tick();
    assert(stages==3 && cancels==3 && last_canceled==1003 && task_frees==3 && !abandoned &&
           !status(2) && !status(3) && !pc.private_run->task && !pc.private_run->exposed &&
           pc.private_run->deadline==admission_deadline && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START] && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]);
    error_action=0;drain();
    assert(stages==5 && retires==2 && cancels==3 && status(2)==1 && status(3)==1 &&
           !pc.private_gpu_failed && !abandoned);cleanup();

    setup();error_action=PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH;rpc_error=-ENOSPC;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());tick();
    jiffies=pc.private_run->deadline-1;tick();
    assert(status(2)==-ETIMEDOUT && cancels==1 && !abandoned && !pc.private_gpu_failed && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]);cleanup();

    setup();error_action=PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH;rpc_error=-ENOSPC;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());tick();
    pc.private_closing=true;panthor_client_private_gpu_stop(&pc);
    assert(status(2)==-ECANCELED && cancels==1 && !abandoned && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]);cleanup();

    /* A lying Proxy/partial preparation/uncertain cancellation cannot replay. */
    const int cancel_errors[]={-EBUSY,-EIO,-EPROTO,-EINVAL};
    for(unsigned int i=0;i<ARRAY_SIZE(cancel_errors);i++){
        setup();error_action=PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH;rpc_error=-ENOSPC;cancel_error=cancel_errors[i];
        signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
        assert(status(2)==-ENOSPC && stages==1 && cancels==1 && abandoned==1 &&
               pc.private_gpu_failed && !retires && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_START] && rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]==1);cleanup();
    }
    setup();error_operation=REALM_GPU_TASK_READY_LAUNCH;operation_error=-ENOSPC;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
    assert(status(2)==-ENOSPC && stages==1 && !cancels && abandoned==1 && pc.private_gpu_failed);cleanup();
    setup();error_action=PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH;rpc_error=-EAGAIN;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
    assert(status(2)==-EAGAIN && stages==1 && !cancels && abandoned==1 && pc.private_gpu_failed);cleanup();

    /* Permanent stage failure still errors the job; a fresh submission is possible. */
    setup();stage_error=-EINVAL;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());drain();
    assert(status(2)==-EINVAL && !pc.private_gpu_failed && !abandoned && !rpc_calls[PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH]);
    stage_error=0;inputs[0].queue_index=1;signal_op(0,3,0);assert(!submit());drain();assert(status(3)==1);cleanup();

    /* The largest dependency set includes sixteen explicit waits plus FIFO. */
    setup();assert(!submit());dep=external(1,true,0);dma_fence_put(dep);
    for(unsigned int i=0;i<16;i++)syncs[i]=(struct drm_panthor_sync_op){.handle=1};
    sync_range(0,0,16);assert(!submit());drain();assert(stages==2 && retires==2);cleanup();

    /* A slice allocation failure releases all jobs without exposing a token. */
    setup();signal_op(0,2,0);sync_range(0,0,1);assert(!submit());fail_alloc_after=0;
    tick();fail_alloc_after=-1;assert(status(2)==-ENOMEM && !stages && !scheduled);cleanup();

    /* An uncertain active run cancels queued successors without launching them. */
    setup();args.queue_submits.count=2;inputs[1].queue_index=0;
    signal_op(0,2,0);signal_op(1,3,0);sync_range(0,0,1);sync_range(1,1,1);
    error_operation=REALM_GPU_TASK_READY_LAUNCH;operation_error=-EIO;assert(!submit());drain();
    assert(status(2)==-EIO && status(3)==-ECANCELED && stages==1 && abandoned==1);cleanup();

    /* VM id protection covers both pending jobs and an active run. */
    setup();assert(!panthor_client_private_gpu_vm_busy(&pc,7));assert(!submit());
    assert(panthor_client_private_gpu_vm_busy(&pc,7) && !panthor_client_private_gpu_vm_busy(&pc,8));
    tick();assert(panthor_client_private_gpu_vm_busy(&pc,7));drain();
    assert(!panthor_client_private_gpu_vm_busy(&pc,7));cleanup();

    /* Closing at any phase errors fences and stops each exposed run once. */
    for(unsigned int phase=0;phase<4;phase++){
        setup();return_again=1;signal_op(0,2,0);sync_range(0,0,1);assert(!submit());
        for(unsigned int j=0;j<phase;j++)tick();
        pc.private_closing=true;panthor_client_private_gpu_stop(&pc);
        assert(status(2)==-ECANCELED && !scheduled && !pc.private_gpu_pending.value);
        assert(rpc_calls[PANTHOR_VMSHM_RMM_TASK_QUIESCE]==(phase?1:0) && abandoned==(phase?1:0));cleanup();
    }

    /* Delegated launch uses one Proxy request and no Client READY when
     * STARTED; bounded PREPARED falls through to the original READY cursor.
     * A response is never completion: only trusted FINISH can signal output.
     */
    for(unsigned int mode=0;mode<12;mode++) {
        setup();pc.private_dispatch=true;signal_op(0,2,0);sync_range(0,0,1);
        if(mode==1)dispatch_state=4;
        if(mode>=2 && mode<=6)malformed=mode-1;
        if(mode==7){error_action=PANTHOR_VMSHM_RMM_TASK_DISPATCH;rpc_error=-EIO;}
        if(mode==8){error_action=PANTHOR_VMSHM_RMM_TASK_DISPATCH;rpc_error=-EAGAIN;}
        if(mode==9){error_operation=REALM_GPU_TASK_FINISH;operation_error=-EBUSY;}
        if(mode==10)again[REALM_GPU_TASK_FINISH]=2;
        if(mode==11){dispatch_state=4;again[REALM_GPU_TASK_READY_LAUNCH]=2;}
        assert(!submit());drain();assert(staged_delegation && rpc_calls[PANTHOR_VMSHM_RMM_TASK_DISPATCH]==1);
        assert(!rpc_calls[PANTHOR_VMSHM_RMM_TASK_PREPARE_LAUNCH]);
        assert(!pc.private_phase_pages[PANTHOR_PRIVATE_PREPARE]);
        if(mode>=2 && mode<=9)assert(status(2)<0 && abandoned==1);
        else assert(status(2)==1 && retires==1 && !abandoned);
        if(mode!=1 && mode!=11)assert(!operation_calls[REALM_GPU_TASK_READY_LAUNCH]);
        if(mode==1)assert(operation_calls[REALM_GPU_TASK_READY_LAUNCH]==1);
        if(mode==11)assert(operation_calls[REALM_GPU_TASK_READY_LAUNCH]==3);
        cleanup();
    }

    /* Group destroy retains queued jobs and defers the remote destroy. */
    setup();signal_op(0,2,0);sync_range(0,0,1);assert(!submit());
    group->destroy_pending=true;pc.groups.entries[1]=NULL;panthor_client_group_put(group);group=NULL;
    assert(!destroy_rpc);drain();assert(status(2)==1 && destroy_rpc==1 && group_releases==1);cleanup();

    /* Validation/allocation failures leave every output and FIFO tail unchanged. */
    for(unsigned int mode=0;mode<12;mode++){
        setup();signal_op(0,2,0);sync_range(0,0,1);
        switch(mode){
        case 0:inputs[0].queue_index=16;break;
        case 1:inputs[0].stream_addr++;break;
        case 2:inputs[0].stream_size++;break;
        case 3:inputs[0].stream_addr=0;break;
        case 4:inputs[0].stream_addr=0x80000000;break;
        case 5:inputs[0].stream_addr=0x7fffffc0;inputs[0].stream_size=128;break;
        case 6:syncs[0].handle=0;break;
        case 7:pc.private_closing=true;break;
        case 8:pc.private_gpu_pending.value=128;break;
        case 9:args.pad=1;break;
        case 10:inputs[0].latest_flush=BIT(24);break;
        case 11:args.group_handle=2;break;
        }
        assert(submit()<0 && !file.objects[2].fence && !group->private_last[0] && !scheduled);
        pc.private_gpu_pending.value=0;cleanup();
    }
    for(int fail=0;fail<4;fail++){
        setup();signal_op(0,2,5);sync_range(0,0,1);fail_alloc_after=fail;
        int ret=submit();fail_alloc_after=-1;
        if(ret){assert(ret==-ENOMEM && !file.objects[2].fence && !group->private_last[0] && !scheduled);}
        else{drain();assert(status(2)==1);}
        cleanup();
    }
    /* Mapping waits only for an active run, never for a job waiting on a bind. */
    setup();dep=external(1,false,0);syncs[0]=(struct drm_panthor_sync_op){.handle=1};
    signal_op(1,2,0);sync_range(0,0,2);assert(!submit());
    assert(!panthor_client_private_mapping_lock(&pc,7) && pc.private_gpu_lock.held && !stages);
    assert(list_empty(&pc.private_map_waiters));mutex_unlock(&pc.private_gpu_lock);
    dma_fence_signal(dep);dma_fence_put(dep);drain();assert(status(2)==1);cleanup();

    /* Active mapping guard waits through COMPLETE, all RETURN and RETIRE. */
    setup();signal_op(0,2,0);sync_range(0,0,1);assert(!submit());tick();
    again[REALM_GPU_TASK_FINISH]=2;return_again=4;
    wait_hook=advance_for_mapping;
    assert(!panthor_client_private_mapping_lock(&pc,7) && pc.private_gpu_lock.held);
    assert(status(2)==1 && retires==1 && list_empty(&pc.private_map_waiters));
    mutex_unlock(&pc.private_gpu_lock);wait_hook=NULL;cleanup();

    /* An unrelated VM's mapping need not wait for the running VM. */
    setup();assert(!submit());tick();
    assert(!panthor_client_private_mapping_lock(&pc,8) && pc.private_gpu_lock.held && !retires);
    mutex_unlock(&pc.private_gpu_lock);drain();cleanup();

    /* Timeout/close/fault release the stack ticket, lock and temporary fence. */
    setup();assert(!submit());tick();
    assert(panthor_client_private_mapping_lock(&pc,7)==-ETIMEDOUT);
    assert(!pc.private_gpu_lock.held && list_empty(&pc.private_map_waiters) && !retires);cleanup();
    setup();assert(!submit());tick();wait_hook=close_for_mapping;
    assert(panthor_client_private_mapping_lock(&pc,7)==-ECANCELED);
    assert(!pc.private_gpu_lock.held && list_empty(&pc.private_map_waiters));cleanup();
    setup();assert(!submit());tick();error_operation=REALM_GPU_TASK_FINISH;operation_error=-EIO;
    wait_hook=advance_for_mapping;
    assert(panthor_client_private_mapping_lock(&pc,7)==-EIO);
    assert(!pc.private_gpu_lock.held && list_empty(&pc.private_map_waiters) && abandoned==1);cleanup();

    /* Ready mapping wins over same-VM successors; another VM can still run. */
    setup();other=calloc(1,sizeof(*other));assert(other);*other=*group;
    other->client_handle=2;other->private_vm_id=8;pc.groups.entries[2]=other;
    args.queue_submits.count=2;inputs[1].queue_index=0;
    signal_op(0,2,0);signal_op(1,3,0);sync_range(0,0,1);sync_range(1,1,1);
    assert(!submit());tick();args.group_handle=2;args.queue_submits.count=1;
    inputs[0].queue_index=3;signal_op(0,4,0);sync_range(0,0,1);assert(!submit());
    wait_hook=advance_and_pick;
    assert(!panthor_client_private_mapping_lock(&pc,7));
    assert(pc.private_gpu_lock.held && stages==2 && pc.private_run->jobs[0]->group==other);
    assert(status(2)==1 && !status(3) && !status(4));
    mutex_unlock(&pc.private_gpu_lock);wait_hook=NULL;drain();
    assert(stages==3 && status(3)==1 && status(4)==1);panthor_client_group_put(other);cleanup();

    for(unsigned int mode=0;mode<2;mode++){
        setup();pc.private_closing=mode==0;pc.private_gpu_failed=mode==1;
        assert(panthor_client_private_mapping_lock(&pc,7)==(mode?-EIO:-ECANCELED));
        assert(!pc.private_gpu_lock.held && list_empty(&pc.private_map_waiters));cleanup();
    }
    /* Concurrent mapping waiters retain distinct tickets and cannot deadlock. */
    setup();assert(!submit());tick();wait_hook=nested_mapping;
    assert(!panthor_client_private_mapping_lock(&pc,7) && retires==1);
    assert(list_empty(&pc.private_map_waiters));mutex_unlock(&pc.private_gpu_lock);cleanup();

    /* The actual heap ioctl wrappers acquire the same guard around mutation. */
    struct drm_panthor_tiler_heap_create heap_create={.vm_id=7};
    struct drm_panthor_tiler_heap_destroy heap_destroy={.handle=1};
    struct panthor_client_heap heap={.client_vm_id=7};
    setup();assert(!submit());tick();wait_hook=advance_for_mapping;
    assert(!panthor_client_ioctl_tiler_heap_create(NULL,&heap_create,&file));
    assert(heap_creates==1 && retires==1 && !pc.private_gpu_lock.held && !pc.private_submit_lock.held);cleanup();
    setup();pc.heaps.entries[1]=&heap;assert(!submit());tick();wait_hook=advance_for_mapping;
    assert(!panthor_client_ioctl_tiler_heap_destroy(NULL,&heap_destroy,&file));
    assert(heap_destroys==1 && retires==1 && !pc.private_gpu_lock.held && !pc.private_submit_lock.held);cleanup();
    setup();heap_error=-EINVAL;
    assert(panthor_client_ioctl_tiler_heap_create(NULL,&heap_create,&file)==-EINVAL);
    assert(heap_creates==1 && !pc.private_gpu_lock.held && !pc.private_submit_lock.held);cleanup();
    setup();assert(panthor_client_ioctl_tiler_heap_destroy(NULL,&heap_destroy,&file)==-EINVAL);
    assert(!heap_destroys && !pc.private_submit_lock.held);cleanup();
    setup();assert(!submit());tick();heap_create.vm_id=8;
    assert(!panthor_client_ioctl_tiler_heap_create(NULL,&heap_create,&file));
    assert(heap_creates==1 && !retires);heap_create.vm_id=7;drain();cleanup();
    setup();pc.private_data=false;
    assert(!panthor_client_ioctl_tiler_heap_create(NULL,&heap_create,&file));
    assert(!panthor_client_ioctl_tiler_heap_destroy(NULL,&heap_destroy,&file));
    assert(heap_creates==1 && heap_destroys==1 && !pc.private_gpu_lock.held);cleanup();
    for(unsigned int mode=0;mode<2;mode++){
        setup();pc.heaps.entries[1]=&heap;pc.private_gpu_failed=mode==0;pc.private_closing=mode==1;
        assert(panthor_client_ioctl_tiler_heap_destroy(NULL,&heap_destroy,&file)==(mode?-ECANCELED:-EIO));
        assert(!heap_destroys && !pc.private_gpu_lock.held && !pc.private_submit_lock.held);cleanup();
    }

    /* Repeated false hints cannot complete fences or suppress real checks. */
    setup();signal_op(0,2,0);sync_range(0,0,1);hint_pending=true;assert(!submit());tick();tick();
    for(unsigned int i=0;i<8;i++) {
        unsigned int before=operation_calls[REALM_GPU_TASK_FINISH];
        tick();assert(operation_calls[REALM_GPU_TASK_FINISH]==before && !retires && !status(2));
    }
    assert(pc.private_run->local_hint_skips==8);hint_pending=false;
    drain();assert(status(2)==1 && retires==1);cleanup();
    setup();signal_op(0,2,0);sync_range(0,0,1);hint_pending=true;assert(!submit());tick();tick();
    for(unsigned int i=0;i<8;i++)tick();
    error_operation=REALM_GPU_TASK_FINISH;operation_error=-EIO;
    tick();assert(status(2)==-EIO && !retires && abandoned==1);hint_pending=false;cleanup();
    setup();signal_op(0,2,0);sync_range(0,0,1);hint_pending=true;assert(!submit());tick();tick();
    tick();pc.private_run->deadline=jiffies;
    tick();assert(status(2)==-ETIMEDOUT && !retires);hint_pending=false;cleanup();

    /* FT: observe only advice inside the same bounded active pause. */
    for(unsigned int mode=0;mode<3;mode++) {
        setup();hint_enabled=true;hint_pending=mode!=0;
        signal_op(0,2,0);sync_range(0,0,1);group->private_poll_delay_ns[0]=200000;
        if(mode==1) {hint_arrive_at=10000;complete_pause_hook=arrive_in_hint_pause;}
        assert(!submit());tick();tick();
        assert(pc.private_run && pc.private_run->task && !status(2) && !retires);
        assert(!operation_calls[REALM_GPU_TASK_FINISH] && pc.private_hint_pause_watches==1);
        if(mode<2) {
            assert(pc.private_hint_pause_early==1 && pc.private_hint_pause_reads>0);
            assert(pc.private_first_poll_pause_ns<20000);
        } else {
            assert(!pc.private_hint_pause_early && pc.private_first_poll_pause_ns>=200000);
            for(unsigned int i=0;i<8;i++)tick();
            assert(!operation_calls[REALM_GPU_TASK_FINISH] && !status(2));
            assert(pc.private_run->local_hint_skips==8);
        }
        complete_pause_hook=NULL;drain();
        assert(status(2)==1 && retires==1 && operation_calls[REALM_GPU_TASK_FINISH]==1);
        cleanup();cases++;
    }
    /* A forged arrival never bypasses errors, pending/OOM or deadline. */
    for(unsigned int mode=0;mode<3;mode++) {
        setup();hint_enabled=true;hint_pending=false;
        signal_op(0,2,0);sync_range(0,0,1);group->private_poll_delay_ns[0]=200000;
        if(mode==0){error_operation=REALM_GPU_TASK_FINISH;operation_error=-EIO;}
        if(mode==1){again[REALM_GPU_TASK_FINISH]=12;heap_service_error=-EPROTO;}
        assert(!submit());tick();tick();
        if(mode==2)pc.private_run->deadline=jiffies;
        drain();assert(status(2)==(mode==0?-EIO:mode==1?-EPROTO:-ETIMEDOUT));
        assert(!retires && abandoned==1);cleanup();cases++;
    }
    /* Worker owns the task across unlock; close is drained before task_put. */
    setup();hint_enabled=hint_pending=true;
    signal_op(0,2,0);sync_range(0,0,1);group->private_poll_delay_ns[0]=200000;
    complete_pause_hook=close_in_complete_sleep;
    assert(!submit());tick();tick();
    assert(pc.private_closing && pc.private_run && pc.private_run->task && !task_frees);
    assert(!retires && !status(2) && !scheduled);
    cleanup();assert(task_frees==1);cases++;
    printf("GPU_PRIVATE_SUBMIT=PASS cases=%u actual Client planner/ready-slice worker; per-job binary/timeline fences, queue FIFO and cross-submit readiness, immutable inputs, trusted return/retire gate, failure/close retention and no launch replay; HOST_DOUBLES_ONLY NO_LINUX_CONCURRENCY_OR_GPU_EXECUTION\n",cases);
    return 0;
}
