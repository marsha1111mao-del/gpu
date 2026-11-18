#ifndef IRQ_TEST_RMM_EL3_IFC_H
#define IRQ_TEST_RMM_EL3_IFC_H
#include <stdint.h>
#define SMC_RMM_OPENCCA_GPU_IRQ 0xc40001ccUL
uintptr_t rmm_el3_ifc_get_shared_buf_locked(void);
uintptr_t rmm_el3_ifc_get_shared_buf_pa(void);
void rmm_el3_ifc_release_shared_buf(void);
#endif
