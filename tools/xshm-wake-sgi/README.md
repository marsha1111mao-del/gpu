# Host fallback for the experimental Realm wake SGI

Reserves physical Group1NS SGI15, registers a per-CPU fallback handler and
enables/disables it through CPU hotplug callbacks. It refuses an existing
mapping. This does not authorize a Realm notification: RMM private channel
state remains the authority. Secure SGIs and Linux SMP SGI0-7 are untouched.

Build against the running Host's exact configuration, symbols and release:

```bash
make -C Linux-Host-GPU O=<matching-host-build> ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-opencca-pmthor-opp3 \
  M="$PWD/tools/xshm-wake-sgi" -j8 modules
modinfo tools/xshm-wake-sgi/xshm_wake_sgi.ko
```

Run only through the lab lease, wrapping the ordinary frozen Realm runner:

```bash
python3 scripts/maintenance/lab-run.py --run-id <unique> -- \
  python3 scripts/run/run-realm-wake-sgi.py \
  --module tools/xshm-wake-sgi/xshm_wake_sgi.ko -- \
  python3 scripts/run/run-realm-xshm.py --images <frozen> <workload-options>
```

The wrapper checks Host release, uploads/verifies the module, captures IRQ
and dmesg evidence, runs the workload and removes the module after all VMs
exit. It refuses removal with live Firecracker processes. Root checks the
actual target SGI group/enabled state on every fast kick; absent this helper,
resident notifications retain the SGI0 route. Firmware, Guest and helper
must come from the same tested combination. Results are not a portable CCA
interrupt ABI or a claim of hardware isolation on RK3588.
