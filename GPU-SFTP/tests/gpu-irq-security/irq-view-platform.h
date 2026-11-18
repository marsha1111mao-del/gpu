#ifndef MAILBOX_PLATFORM_H
#define MAILBOX_PLATFORM_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ULL(x) x##ULL
#define PLAT_RK_GICD_BASE 0x10000000UL
#define MPIDR_AFFINITY_MASK 0xff00ffffffUL
#define INTR_GROUP0 0U
#define INTR_GROUP1NS 1U
#define INTR_TYPE_EL3 0U
#define NON_SECURE 0U
#define SECURE 1U
#define SMC_RMM_OPENCCA_GPU_IRQ 0xc40001ccUL
#define INFO(...) ((void)0)
#define ERROR(...) ((void)0)
typedef unsigned int spinlock_t;
typedef uint64_t (*irq_handler_t)(uint32_t, uint32_t, void *, void *);
void flush_dcache_range(uintptr_t, size_t);
void inv_dcache_range(uintptr_t, size_t);
unsigned long read_cntpct_el0(void);
unsigned long read_mpidr_el1(void);
void dsbsy(void);
void spin_lock(spinlock_t *);
void spin_unlock(spinlock_t *);
unsigned int mmio_read_32(uintptr_t);
uint64_t mmio_read_64(uintptr_t);
uint8_t mmio_read_8(uintptr_t);
void mmio_write_32(uintptr_t, unsigned int);
void mmio_write_64(uintptr_t, uint64_t);
void mmio_write_8(uintptr_t, uint8_t);
#define set_interrupt_rm_flag(f, s) ((f) |= 1U << (s))
int register_interrupt_type_handler(unsigned int, irq_handler_t, uint32_t);
void panic(void);
unsigned int plat_my_core_pos(void);
unsigned int plat_ic_acknowledge_interrupt(void);
void plat_ic_end_of_interrupt(unsigned int);
unsigned int gicv3_get_interrupt_group(unsigned int, unsigned int);
unsigned int gicv3_get_interrupt_active(unsigned int, unsigned int);
void gicv3_disable_interrupt(unsigned int, unsigned int);
void gicv3_enable_interrupt(unsigned int, unsigned int);
void gicv3_clear_interrupt_pending(unsigned int, unsigned int);
void gicv3_set_interrupt_group(unsigned int, unsigned int, unsigned int);
void gicv3_set_interrupt_priority(unsigned int, unsigned int, unsigned int);
void gicv3_set_spi_routing(unsigned int, unsigned int, uint64_t);
#define INTR_ROUTING_MODE_PE 0U
size_t plat_rmmd_get_el3_rmm_shared_mem(uintptr_t *);
uintptr_t rmm_el3_ifc_get_shared_buf_locked(void);
uintptr_t rmm_el3_ifc_get_shared_buf_pa(void);
void rmm_el3_ifc_release_shared_buf(void);
unsigned long monitor_call(unsigned long, unsigned long, unsigned long,
                          unsigned long, unsigned long, unsigned long, unsigned long);

uintptr_t c3_test_view_address(void);
bool c3_test_fast_empty(void);
unsigned int c3_test_register_address(uintptr_t);
#define RMM_BASE (c3_test_view_address())
#define RMM_LIMIT (RMM_BASE + 8192UL)
#define dsb(scope) dsbsy()
#endif
