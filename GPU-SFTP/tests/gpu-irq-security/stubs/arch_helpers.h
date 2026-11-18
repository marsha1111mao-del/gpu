#ifndef IRQ_TEST_ARCH_HELPERS_H
#define IRQ_TEST_ARCH_HELPERS_H
#include <stddef.h>
#include <stdint.h>
static inline void flush_dcache_range(uintptr_t p, size_t n) { (void)p;(void)n; }
static inline void inv_dcache_range(uintptr_t p, size_t n) { (void)p;(void)n; }
static inline unsigned long read_cntpct_el0(void) { static unsigned long n; return ++n; }
#endif

#define dsb(scope) ((void)0) /* Legacy transport adapter; noncoherent view ordering tested separately. */
