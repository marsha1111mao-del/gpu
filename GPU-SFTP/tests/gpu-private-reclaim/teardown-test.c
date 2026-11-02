/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual Host functions; RMI, page release, shared unmap and locks are doubles. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <sys/types.h>
#define RME_PAGE_SIZE 4096UL
#define PHYS_ADDR_MAX UINT64_MAX
#define GFP_KERNEL 0
#define RMI_SUCCESS 0
#define RMI_ERROR_INPUT 1
#define RMI_ERROR_RTT 4
#define REALM_STATE_NONE 0
#define RMI_RETURN_STATUS(v) ((v) & 255)
#define RMI_RETURN_INDEX(v) ((v) >> 8)
#define ALIGN(v,a) (((v)+(a)-1)&~((a)-1))
#define BIT(v) (1UL<<(v))
#define min(a,b) ((a)<(b)?(a):(b))
typedef unsigned long phys_addr_t;
typedef uint64_t u64;
struct realm { void *rd; unsigned int state,ia_bits; };
struct kvm { struct { struct realm realm; } arch; };
static unsigned int warnings, destroyed, undelegated, released, folds, calls;
static unsigned int refused, fatal;
static bool absent;
#define WARN_ON(v) ((v)?(warnings++,true):false)
static unsigned long virt_to_phys(void *p) { return (unsigned long)p; }
static void *phys_to_page(unsigned long p) { assert(p>=0x100000UL);return (void *)p; }
static void put_page(void *p) { assert(p);released++; }
static unsigned long alloc_delegated_page(struct realm *r,void *p,int flags)
{ assert(false);return 0; }
static void free_delegated_page(struct realm *r,unsigned long p) { assert(false); }
static int realm_rtt_create(struct realm *r,unsigned long ipa,int level,unsigned long pa)
{ assert(false);return -1; }
static int rmi_granule_undelegate(unsigned long pa)
{ assert(pa>=0x100000UL);undelegated++;return 0; }
static int rmi_data_destroy(unsigned long rd,unsigned long ipa,unsigned long *pa,unsigned long *next)
{
 unsigned int page=ipa/RME_PAGE_SIZE;
 assert(page<4);calls++;
 *pa=0;*next=~0UL; /* Error outputs must not advance/undelegate an arbitrary page. */
 if(refused&(1U<<page))return RMI_ERROR_INPUT;
 if(fatal&(1U<<page))return 2;
 *next=ipa+RME_PAGE_SIZE;
 if(absent)return RMI_ERROR_RTT;
 *pa=0x100000UL+ipa;destroyed++;return RMI_SUCCESS;
}
static int get_start_level(struct realm *r) { return 0; }
static void realm_unmap_range_shared(struct kvm *k,int level,unsigned long a,unsigned long b) {}
static void ensure_spare_page(struct realm *r) {}
static void realm_fold_rtt_range(struct realm *r,unsigned long a,unsigned long b) { folds++; }
#include "actual.inc"
int main(void)
{
 struct kvm k={.arch.realm={.rd=(void *)0x8000,.state=1,.ia_bits=32}};
 unsigned long next;
 refused=1;
 assert(realm_destroy_protected(&k.arch.realm,0,&next)==-EBUSY);
 assert(next==RME_PAGE_SIZE && !destroyed && !undelegated && !released && !warnings);
 refused=5;calls=0;
 assert(!realm_unmap_range_private(&k,0,4*RME_PAGE_SIZE));
 assert(calls==4 && destroyed==2 && released==2 && undelegated==2 && !warnings);
 calls=0;
 kvm_realm_unmap_range(&k,0,4*RME_PAGE_SIZE,true);
 assert(calls==4 && !folds && !warnings);
 /* Trusted revocation/REC death and restoration are external to these Host functions. */
 refused=0;calls=0;
 kvm_realm_unmap_range(&k,0,4*RME_PAGE_SIZE,true);
 assert(calls==4 && folds==1 && !warnings);
 absent=true;calls=0;
 assert(realm_unmap_range_private(&k,0,4*RME_PAGE_SIZE));
 assert(calls==4 && !warnings);
 absent=false;fatal=1;calls=0;
 assert(!realm_unmap_range_private(&k,0,4*RME_PAGE_SIZE));
 assert(calls==1 && warnings==2);
 warnings=0;fatal=0;refused=15;
 assert(!realm_unmap_range(&k,0,4*RME_PAGE_SIZE,true));
 assert(!warnings); /* Final caller must refuse RD teardown on this false result. */
 assert(realm_unmap_range(&k,0,4*RME_PAGE_SIZE,false));
 k.arch.realm.state=REALM_STATE_NONE;
 assert(realm_unmap_range(&k,0,4*RME_PAGE_SIZE,true));
 puts("GPU_PRIVATE_TEARDOWN=PASS cases=9 ACTUAL_HOST_FUNCTIONS_RMI_AND_PAGE_DOUBLES_ONLY");
 return 0;
}
