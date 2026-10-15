# pmthor PFN lifetime regression

Run on an idle ARM64 pmthor host as root. This test creates two tiny KVM VMs,
translates 32 copies of one GPA per VM through the project's GPA_TO_HPA HVC,
then exercises both device/VM close orders. It submits no GPU commands.

```bash
aarch64-linux-gnu-gcc -O2 -Wall -Wextra -Werror -static \
  -o pmthor-pfn-lifetime pmthor_pfn_lifetime.c
# Copy binary to the RK3588, then:
timeout 35 ./pmthor-pfn-lifetime
dmesg > pfn-lifetime-kernel.log
python3 check_kernel_log.py pfn-lifetime-kernel.log
```

The C program verifies HVC success and identical HPAs. The kernel log checker
additionally requires exactly one retained/released PFN per VM, device-close
VM-reference counts of zero/one respectively, and release after both ownership
references end. Device-first also requires reopening to fail with EBUSY while
the VM lives, followed by another successful reset after the last VM teardown
and before page release. `/dev/kmsg` must be writable to delimit each phase. An old
kernel can pass translation while failing the lifetime checker.

This checks normal teardown and duplicate translations. It does not prove
reset-failure recovery, active platform unbind, hostile VMM isolation, or
arbitrary GPU DMA revocation. GPU workloads require separate end-to-end tests.
