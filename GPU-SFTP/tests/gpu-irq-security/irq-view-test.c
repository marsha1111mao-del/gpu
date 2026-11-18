/* Actual EL3 adapter + RMM bridge + event cores; architecture/MMIO/GIC doubles.
 * Two private 64-byte-line cache views communicate only through clean/invalidate.
 */
#include "platform.h"
#include <opencca_gpu_irq.h>
#include <opencca_gpu_irq_abi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char wire[4096] __attribute__((aligned(64)));
static unsigned char ram[4096], views[2][4096];
static unsigned char model_gpu_registers[0x3000], gic[0x7000];
static unsigned int world, pending_irq, groups[3] = {1, 1, 1};
static bool acquired;
static irq_handler_t handler;
static uint64_t ticks, smcs, semantic_hash = 1469598103934665603ULL;
static uint64_t cache_bytes, cache_lines, cache_calls;
static unsigned int corrupt;
static unsigned char view_ram[128], view_cache[2][128];
static unsigned int late_event;
static bool skip_registration;
static void physical(uint32_t, uint32_t);
static void check_record_before_clear(uintptr_t, unsigned int);
static void check_view_commit(spinlock_t *);
static void select_world(unsigned int target)
{
    unsigned char *view=(void *)c3_test_view_address();
    memcpy(views[world],wire,sizeof(wire));memcpy(view_cache[world],view,sizeof(view_ram));
    memcpy(wire,views[target],sizeof(wire));memcpy(view,view_cache[target],sizeof(view_ram));world=target;
}

static void record(uint64_t value)
{ semantic_hash = (semantic_hash ^ value) * 1099511628211ULL; }

static void cache(uintptr_t address,size_t size,bool clean)
{
    uintptr_t base;unsigned char *memory,*backing;size_t capacity;
    if(address>=(uintptr_t)wire && address+size<=(uintptr_t)wire+sizeof(wire)){
        base=(uintptr_t)wire;memory=wire;backing=ram;capacity=sizeof(wire);
    }else{
        base=c3_test_view_address();memory=(void *)base;backing=view_ram;capacity=sizeof(view_ram);
        assert(address>=base && address+size<=base+capacity);
    }
    assert(size && address>=base && address+size<=base+capacity);
    size_t begin=address-base,end=(begin+size+63U)&~(size_t)63U;
    cache_bytes+=size;cache_calls++;begin&=~(size_t)63U;cache_lines+=(end-begin)/64U;
    assert(end<=capacity);
    if(clean)memcpy(backing+begin,memory+begin,end-begin);
    else memcpy(memory+begin,backing+begin,end-begin);
}
void flush_dcache_range(uintptr_t p, size_t n) { cache(p, n, true); }
void inv_dcache_range(uintptr_t p, size_t n) { cache(p, n, false); }
unsigned long read_cntpct_el0(void) { return ++ticks; }
unsigned long read_mpidr_el1(void) { return 1; }
void dsbsy(void) { record(0xd5b); }
void spin_lock(spinlock_t *p) { assert(!*p); *p = 1; }
void spin_unlock(spinlock_t *p) { assert(*p); check_view_commit(p); *p = 0; }

static unsigned char *reg(uintptr_t address, size_t size)
{
    if (address >= 0xfb000000UL && address + size <= 0xfb000000UL + sizeof(model_gpu_registers))
        return model_gpu_registers + address - 0xfb000000UL;
    assert(address >= PLAT_RK_GICD_BASE && address + size <= PLAT_RK_GICD_BASE + sizeof(gic));
    return gic + address - PLAT_RK_GICD_BASE;
}
unsigned int mmio_read_32(uintptr_t p)
{
    uint32_t v;memcpy(&v,reg(p,4),4);record(p);record(v);
    if(!world && late_event && p==0xfb002008UL){
        late_event=0;physical(0,2U); /* fault after last actual mask sample */
    }
    return v;
}
uint64_t mmio_read_64(uintptr_t p)
{ uint64_t v; memcpy(&v, reg(p, 8), 8); record(p); record(v); return v; }
uint8_t mmio_read_8(uintptr_t p)
{ uint8_t v = *reg(p, 1); record(p); record(v); return v; }
void mmio_write_32(uintptr_t p, unsigned int v)
{
    if(p==0xfb001008UL)v&=UINT32_C(0x8000ffff); /* reserved JOB bits read zero */
    record(p); record(v);
    check_record_before_clear(p,v);
    if (p == 0xfb000024UL || p == 0xfb001004UL || p == 0xfb002004UL) {
        uint32_t raw; memcpy(&raw, reg(p - 4U, 4), 4); raw &= ~v;
        memcpy(reg(p - 4U, 4), &raw, 4);
    }
    memcpy(reg(p, 4), &v, 4);
}
void mmio_write_64(uintptr_t p, uint64_t v)
{ record(p); record(v); memcpy(reg(p, 8), &v, 8); }
void mmio_write_8(uintptr_t p, uint8_t v)
{ record(p); record(v); *reg(p, 1) = v; }
int register_interrupt_type_handler(unsigned int t, irq_handler_t h, uint32_t f)
{ (void)t; (void)f; handler = h; return 0; }
void panic(void) { abort(); }
unsigned int plat_my_core_pos(void) { return 1; }
unsigned int plat_ic_acknowledge_interrupt(void) { return pending_irq; }
void plat_ic_end_of_interrupt(unsigned int n) { record(0xe01); record(n); }
unsigned int gicv3_get_interrupt_group(unsigned int n, unsigned int c)
{ (void)c; assert(n >= 124 && n <= 126); return groups[n - 124]; }
unsigned int gicv3_get_interrupt_active(unsigned int n, unsigned int c)
{ (void)n; (void)c; return 0; }
void gicv3_disable_interrupt(unsigned int n, unsigned int c) { (void)c; record(n * 2U); }
void gicv3_enable_interrupt(unsigned int n, unsigned int c) { (void)c; record(n * 2U + 1U); }
void gicv3_clear_interrupt_pending(unsigned int n, unsigned int c) { (void)c; record(n + 0xc1eaU); }
void gicv3_set_interrupt_group(unsigned int n, unsigned int c, unsigned int g)
{ (void)c; groups[n - 124] = g; record(n + g); }
void gicv3_set_interrupt_priority(unsigned int n, unsigned int c, unsigned int p)
{ (void)c; record(n + p); }
void gicv3_set_spi_routing(unsigned int n, unsigned int m, uint64_t p)
{ record(n + m + p); }
size_t plat_rmmd_get_el3_rmm_shared_mem(uintptr_t *p)
{ assert(world == 1); *p = (uintptr_t)wire; return sizeof(wire); }
uintptr_t rmm_el3_ifc_get_shared_buf_locked(void)
{ assert(!world && !acquired); acquired = true; return (uintptr_t)wire; }
uintptr_t rmm_el3_ifc_get_shared_buf_pa(void) { return (uintptr_t)wire; }
void rmm_el3_ifc_release_shared_buf(void) { assert(acquired && !world); acquired = false; }

/* Include the actual EL3 source, not a reimplementation of its dispatcher. */
#include EL3_SOURCE

static void check_record_before_clear(uintptr_t p,unsigned int value)
{
    if(value && (p==0xfb000024UL || p==0xfb001004UL || p==0xfb002004UL)){
        assert(monitor.stats.queued && !monitor.stats.lost);
#if C3_HAS_VIEW
        if(published_view){
            struct ogi_fast_view copy;memcpy(&copy,view_ram,sizeof(copy));
            assert(copy.sequence && (copy.sequence&1U));
        }
#endif
    }
}
static void check_view_commit(spinlock_t *lock)
{
#if C3_HAS_VIEW
    if(lock==&irq_lock && published_view){
        struct ogi_fast_view copy;memcpy(&copy,view_ram,sizeof(copy));
        assert(copy.sequence==published_sequence && copy.sequence && !(copy.sequence&1U));
        assert(copy.abi==OGI_ABI && copy.magic==OGI_FAST_MAGIC && !copy.reserved);
        assert(!memcmp(&copy.stats,&monitor.stats,sizeof(monitor.stats)));
        assert(!memcmp(copy.masks,approved_masks,sizeof(approved_masks)));
        assert(copy.masks_valid==(unsigned int)approved_masks_valid);
    }
#else
    (void)lock;
#endif
}
#include "idle-platform.inc"


unsigned long monitor_call(unsigned long id, unsigned long cmd, unsigned long pa,
        unsigned long bytes, unsigned long a, unsigned long b, unsigned long c)
{
    assert(!world && acquired && id == SMC_RMM_OPENCCA_GPU_IRQ && !(a | b | c));
    select_world(1);
    smcs++; record(cmd);
    if(skip_registration && cmd==OGI_VIEW_REGISTER)
        ((struct ogi_mailbox *)(void *)ram)->view_pa=0; /* actual bounded validator rejection */
    unsigned long status=opencca_gpu_irq_smc(cmd,pa,bytes);
    if (corrupt) {
        struct ogi_mailbox *reply = (void *)ram;
        if (corrupt == 1) reply->count = OGI_BATCH + 1;
        if (corrupt == 2) reply->abi++;
        if (corrupt == 3) reply->command++;
        if (corrupt == 4) reply->status = status ^ 1U;
        if (corrupt == 5) reply->stats.device_epoch++;
        if (corrupt == 6) reply->stats.lost = 1;
        corrupt = 0;
    }
    select_world(0);
    return status;
}

static void physical(uint32_t job, uint32_t mmu)
{
    assert(!world);select_world(1);
    mmio_write_32(0xfb001000UL, job); mmio_write_32(0xfb002000UL, mmu);
    pending_irq = mmu ? OGI_MMU_INTID : OGI_JOB_INTID;
    handler(0,0,NULL,NULL);select_world(0);
}

int legacy_main(int argc, char **argv)
{
    unsigned int scenario = argc > 1 ? (unsigned int)atoi(argv[1]) : 0;
    static unsigned int owner;
    unsigned long values[4], event[4]; uint64_t epochs[OGI_CSGS];
    memset(wire, 0x31, sizeof(wire)); memset(ram, 0xa5, sizeof(ram));
    memset(views[1], 0x79, sizeof(views[1]));
    opencca_gpu_irq_init(); assert(opencca_gpu_irq_start());
    assert(opencca_gpu_irq_selftest(&owner, 101, 201, values));
    assert(values[0] >= 150 && values[1] == 131 && values[3] == 0);
    assert(opencca_gpu_irq_bind(&owner, 101, 201, 0, 1, &epochs[0]));
    if (scenario >= 1 && scenario <= 6) {
        corrupt = scenario;
        assert(!opencca_gpu_irq_sync(0, epochs[0], NULL));
        assert(!acquired);
        opencca_gpu_irq_revoke();
    } else {
        cache_bytes = cache_lines = cache_calls = 0;
        uint64_t before = smcs;
        for (unsigned int i = 0; i < 1000; i++)
            assert(opencca_gpu_irq_sync(0, epochs[0], NULL));
        assert(smcs-before==(C3_EXPECT_FAST?1U:1000U));
        printf("EMPTY_QUERY samples=1000 smcs=%llu requested_bytes=%llu cache_lines=%llu cache_calls=%llu\n",
            (unsigned long long)(smcs - before), (unsigned long long)cache_bytes,
            (unsigned long long)cache_lines, (unsigned long long)cache_calls);
        for (unsigned int i = 1; i < OGI_CSGS; i++)
            assert(opencca_gpu_irq_bind(&owner, 101 + i, 201 + i, i, 1 + i % 15, &epochs[i]));
        assert(opencca_gpu_irq_sync(0, epochs[0], NULL));
        physical(0xffffU, 0);
        assert(opencca_gpu_irq_sync(0, epochs[0], NULL));
        for (unsigned int i = 0; i < OGI_CSGS; i++) {
            assert(opencca_gpu_irq_next(i, epochs[i], 0, event) == OGI_OK);
            assert(event[2] == OGI_SOURCE_EL3_IRQ);
            assert(opencca_gpu_irq_claim(i, epochs[i], 0, event[0], epochs[i], event[3],
                OGI_CLAIM_COMPLETE, false) == OGI_STATE);
            assert(opencca_gpu_irq_claim(i, epochs[i], 0, event[0], epochs[i] + 1, event[3],
                OGI_CLAIM_PROGRESS, false) == OGI_STALE);
            assert(opencca_gpu_irq_claim(i, epochs[i], 0, event[0], epochs[i], event[3],
                OGI_CLAIM_PROGRESS, false) == OGI_OK);
            assert(opencca_gpu_irq_claim(i, epochs[i], 0, event[0], epochs[i], event[3],
                OGI_CLAIM_PROGRESS, false) == OGI_STALE);
        }
        if (scenario == 7) {
            physical(1, 1U << 1U);
            assert(!opencca_gpu_irq_sync(0, epochs[0], NULL));
            assert(opencca_gpu_irq_next(0, epochs[0], 0, event) == OGI_OK);
            assert(event[2] & OGI_EVENT_FAULT);
            assert(opencca_gpu_irq_claim(0, epochs[0], 0, event[0], epochs[0], event[3],
                OGI_CLAIM_COMPLETE, true) == OGI_STALE);
        } else {
            for (unsigned int i = 0; i < OGI_CSGS; i++)
                assert(opencca_gpu_irq_close(i, epochs[i]));
            assert(opencca_gpu_irq_bind(&owner, 101, 201, 0, 1, &epochs[0]));
            assert(opencca_gpu_irq_close(0, epochs[0]));
        }
        opencca_gpu_irq_revoke();
    }
    assert(!world && !acquired && !monitor.stats.active);
    printf("MAILBOX_SEMANTICS=PASS scenario=%u produced=%llu MODEL_ONLY\n",scenario,
        (unsigned long long)monitor.stats.produced);
    return 0;
}

int main(int argc,char **argv)
{
    assert(argc==2);unsigned int scenario=(unsigned int)atoi(argv[1]);
    if(scenario<8)return legacy_main(argc,argv);
    static unsigned int owner;uint64_t epoch;unsigned long event[4],stats[4];(void)stats;
    memset(wire,0x31,sizeof(wire));memset(ram,0xa5,sizeof(ram));memset(views[1],0x79,sizeof(wire));
    if(scenario==30)skip_registration=true;
    opencca_gpu_irq_init();assert(opencca_gpu_irq_start());
    assert(opencca_gpu_irq_bind(&owner,101,201,0,1,&epoch));
    assert(opencca_gpu_irq_sync(0,epoch,NULL));assert(opencca_gpu_irq_sync(0,epoch,NULL));
    uint64_t before=smcs;
    if(scenario==8){
        mmio_write_32(0xfb000028UL,0U);
        assert(opencca_gpu_irq_sync(0,epoch,NULL));
        assert(smcs>before && mmio_read_32(0xfb000028UL)==3U);
    }else if(scenario==9){
        mmio_write_32(0xfb001000UL,1U);assert(opencca_gpu_irq_sync(0,epoch,NULL));
        assert(smcs>before && opencca_gpu_irq_next(0,epoch,0,event)==OGI_OK);
        assert((event[2]&7U)==OGI_SOURCE_ROOT_SAMPLE);
    }else if(scenario==10 || scenario==11){
        mmio_write_32(scenario==10?0xfb002000UL:0xfb000020UL,scenario==10?2U:1U);
        assert(!opencca_gpu_irq_sync(0,epoch,NULL));assert(smcs>before);
        assert(opencca_gpu_irq_next(0,epoch,0,event)==OGI_OK && (event[2]&OGI_EVENT_FAULT));
        assert(!opencca_gpu_irq_sync(0,epoch,NULL));
    }else if(scenario==12){
        late_event=1;assert(!opencca_gpu_irq_sync(0,epoch,NULL));assert(smcs>before);
        assert(opencca_gpu_irq_next(0,epoch,0,event)==OGI_OK && (event[2]&OGI_EVENT_FAULT));
        assert((event[2]&7U)==OGI_SOURCE_EL3_IRQ);
    }else if(scenario==13){
        assert(opencca_gpu_irq_close(0,epoch));assert(smcs>=before+2 && masked);
    }else if(scenario==14){
        const uintptr_t bad[]={0,RMM_BASE-4096U,RMM_LIMIT,RMM_BASE+64U,UINT64_MAX&~4095UL};
        for(unsigned int i=0;i<sizeof(bad)/sizeof(bad[0]);i++)
            assert(c3_test_register_address(bad[i])==OGI_INPUT);
        assert(opencca_gpu_irq_sync(0,epoch,NULL));
    }else if(scenario==15){
#if C3_HAS_VIEW
        published_sequence=UINT64_MAX-1U;
        assert(opencca_gpu_irq_status(0,stats));
        assert(view_exhausted && published_view==NULL);
        before=smcs;assert(opencca_gpu_irq_sync(0,epoch,NULL));assert(smcs>before);
#endif
    }else if(scenario>=16 && scenario<=29){
#if C3_EXPECT_FAST
        struct ogi_fast_view copy;memcpy(&copy,view_ram,sizeof(copy));
        if(scenario==16)copy.sequence|=1U;
        if(scenario==17)copy.sequence-=2U;
        if(scenario==18)copy.abi++;
        if(scenario==19)copy.magic++;
        if(scenario==20)copy.reserved=1U;
        if(scenario==21)copy.stats.queued=1U;
        if(scenario==22)copy.stats.active=0U;
        if(scenario==23)copy.stats.lost=1U;
        if(scenario==24)copy.stats.simulation=1U;
        if(scenario==25)copy.stats.device_epoch++;
        if(scenario==26)copy.stats.binding_generation++;
        if(scenario==27)copy.stats.produced++;
        if(scenario==28)copy.stats.consumed++;
        if(scenario==29)copy.sequence=0U;
        memcpy(view_ram,&copy,sizeof(copy));
        assert(opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
#endif
    }else if(scenario==30){
        for(unsigned int i=0;i<10;i++)assert(opencca_gpu_irq_sync(0,epoch,NULL));
        assert(smcs==before+10);
    }else if(scenario==31){
        mmio_write_32(0xfb001008UL,0U);assert(opencca_gpu_irq_sync(0,epoch,NULL));
        assert(smcs>before && mmio_read_32(0xfb001008UL)==UINT32_C(0x8000ffff));
    }else if(scenario==32){
        mmio_write_32(0xfb002008UL,0U);assert(opencca_gpu_irq_sync(0,epoch,NULL));
        assert(smcs>before && mmio_read_32(0xfb002008UL)==0xffffU);
    }else if(scenario>=33 && scenario<=37){
#if C3_EXPECT_FAST
        struct ogi_fast_view copy;memcpy(&copy,view_ram,sizeof(copy));
        if(scenario==33)copy.masks_valid=0;
        if(scenario==34){copy.masks[0]=0;mmio_write_32(0xfb000028UL,0);}
        if(scenario==35){copy.masks[1]&=~(UINT32_C(1)<<31);mmio_write_32(0xfb001008UL,copy.masks[1]);}
        if(scenario==36){copy.masks[2]&=~2U;mmio_write_32(0xfb002008UL,copy.masks[2]);}
        if(scenario==37)copy.masks[1]=UINT32_MAX;
        memcpy(view_ram,&copy,sizeof(copy));
        assert(opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
#endif
    }else if(scenario==38 || scenario==39){
        mmio_write_32(scenario==38?0xfb000020UL:0xfb002000UL,scenario==38?2U:1U);
        assert(!opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
        assert(opencca_gpu_irq_next(0,epoch,0,event)==OGI_OK && (event[2]&OGI_EVENT_FAULT));
    }else if(scenario==40){
        mmio_write_32(0xfb002000UL,1U<<15);
        assert(!opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
        assert(opencca_gpu_irq_status(1,stats) && stats[3]);
    }else if(scenario==41){
        mmio_write_32(0xfb002000UL,1U<<16); /* command ACK, not an AS fault */
        assert(opencca_gpu_irq_sync(0,epoch,NULL));
#if C3_EXPECT_FAST
        assert(smcs==before);
#endif
    }else if(scenario==42){
        mmio_write_32(0xfb001000UL,UINT32_C(1)<<31);
        assert(opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
        assert(opencca_gpu_irq_next(0,epoch,0,event)==OGI_OK && !(event[2]&OGI_EVENT_FAULT));
    }else if(scenario==43){
        mmio_write_32(0xfb001000UL,UINT32_C(1)<<15); /* unbound progress is recorded, not completion */
        assert(opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
        assert(opencca_gpu_irq_status(0,stats) && stats[1]);
    }else if(scenario==44 || scenario==45){
        uintptr_t address=scenario==44?0xfb002008UL:0xfb000028UL;
        mmio_write_32(address,scenario==44?0x1ffffU:0x103U);
        assert(opencca_gpu_irq_sync(0,epoch,NULL) && smcs>before);
        assert(mmio_read_32(address)==(scenario==44?0xffffU:3U));
    }else if(scenario==46){
        assert(c3_test_register_address(RMM_BASE)==OGI_STATE); /* live bindings cannot re-register */
        assert(opencca_gpu_irq_sync(0,epoch,NULL));
    }else if(scenario==47){
        assert(c3_test_register_address(RMM_BASE+4096UL)==OGI_INPUT); /* no private-pointer substitution */
        assert(opencca_gpu_irq_sync(0,epoch,NULL));
    }else assert(false);
    opencca_gpu_irq_revoke();assert(!world && !acquired && !monitor.stats.active);
    printf("C3_BOUNDARY=PASS scenario=%u\n",scenario);return 0;
}
