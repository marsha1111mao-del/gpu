#!/bin/bash
set -euo pipefail
rid=$1
[[ $(uname -r) == 6.12.0-opencca-pmthor-opp3 ]]
! test -d /sys/module/pmthor_opp_probe
base=/root/GPU-SFTP
out="$base/log/glmark-optimization/$rid"
mnt="$out/mnt"
test ! -e "$out"
mkdir -p "$out"
exec > >(tee "$out/native.log") 2>&1
! pgrep -x firecracker
! pgrep -x vmshm-broker
[[ $(basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)") == pmthor ]]
cat /proc/sys/kernel/random/boot_id > "$out/boot-id"
cat /proc/cmdline > "$out/host-cmdline"
cat /proc/sys/kernel/printk > "$out/printk-before"
: > "$out/cpu-restore"
old_opp=$(cat /sys/class/devfreq/fb000000.gpu/cur_freq)
old_governor=$(cat /sys/class/devfreq/fb000000.gpu/governor)
switched=0
cleanup() {
 local rc=$?
 trap - EXIT
 set +e
 if [[ -f "$out/gpu-smoke.sh.before" && -d "$mnt/root" ]]; then cp "$out/gpu-smoke.sh.before" "$mnt/root/gpu-smoke.sh"; fi
 if [[ -f "$out/gpu-smoke.env.before" && -d "$mnt/root" ]]; then cp "$out/gpu-smoke.env.before" "$mnt/root/gpu-smoke.env"; elif [[ -f "$out/gpu-smoke.env.absent" && -d "$mnt/root" ]]; then rm -f "$mnt/root/gpu-smoke.env"; fi
 for part in tmp run sys proc dev ''; do
  if mountpoint -q "$mnt${part:+/$part}"; then
   for attempt in $(seq 1 30); do
    umount "$mnt${part:+/$part}" && break
    sleep 1
   done
   mountpoint -q "$mnt${part:+/$part}" && rc=90
  fi
 done
 if [[ "$switched" == 1 ]]; then
  driver=$(basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)")
  if [[ "$driver" == panthor ]]; then
   echo fb000000.gpu > /sys/bus/platform/drivers/panthor/unbind || rc=90
  fi
  if [[ ! -e /sys/bus/platform/devices/fb000000.gpu/driver ]]; then
   echo fb000000.gpu > /sys/bus/platform/drivers/pmthor/bind || rc=90
  fi
  if [[ $(basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)") == pmthor ]]; then
   echo userspace > /sys/class/devfreq/fb000000.gpu/governor || rc=90
   echo "$old_opp" > /sys/class/devfreq/fb000000.gpu/userspace/set_freq || rc=90
   echo "$old_governor" > /sys/class/devfreq/fb000000.gpu/governor || rc=90
   [[ $(cat /sys/class/devfreq/fb000000.gpu/cur_freq) == "$old_opp" ]] || rc=90
  else
   rc=90
  fi
  modprobe -r panthor || rc=90
 fi
 while read -r cpu; do echo 0 > "/sys/devices/system/cpu/cpu$cpu/online"; done < "$out/cpu-restore"
 cat "$out/printk-before" > /proc/sys/kernel/printk
 dmesg > "$out/host-dmesg-after.log"
 echo "NATIVE_COMMAND_RC=$rc"
 echo "DRIVER=$(basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)")"
 echo "CPUS=$(cat /sys/devices/system/cpu/online)"
 echo "NATIVE_CLEANUP_RC=$rc"
 cat /sys/class/devfreq/fb000000.gpu/governor /sys/class/devfreq/fb000000.gpu/cur_freq
 echo "$rc" > "$out/exit-code"
 exit "$rc"
}
trap cleanup EXIT
for cpu in 2 3; do
 if [[ $(cat "/sys/devices/system/cpu/cpu$cpu/online") == 0 ]]; then
  echo "$cpu" >> "$out/cpu-restore"
  echo 1 > "/sys/devices/system/cpu/cpu$cpu/online"
 fi
done
switched=1
echo fb000000.gpu > /sys/bus/platform/drivers/pmthor/unbind
modprobe panthor
if [[ ! -e /sys/bus/platform/devices/fb000000.gpu/driver ]]; then echo fb000000.gpu > /sys/bus/platform/drivers/panthor/bind; fi
[[ $(basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)") == panthor ]]
mkdir -p "$mnt"
mount -o loop "$base/firecracker-bins/rootfs/rootfs-panfrost.ext4" "$mnt"
mount --bind /dev "$mnt/dev"
mount -t proc proc "$mnt/proc"
mount -t sysfs sysfs "$mnt/sys"
mount -t tmpfs tmpfs "$mnt/run"
mount -t tmpfs tmpfs "$mnt/tmp"
if [[ -f "$mnt/root/gpu-smoke.env" ]]; then cp "$mnt/root/gpu-smoke.env" "$out/gpu-smoke.env.before"; else : > "$out/gpu-smoke.env.absent"; fi
cp "$mnt/root/gpu-smoke.sh" "$out/gpu-smoke.sh.before"
install -m0755 "$base/tests/gpu-compute-smoke/gpu-smoke.sh" "$mnt/root/gpu-smoke.sh"
[[ $(sha256sum "$mnt/root/glmark2/bin/glmark2-es2-null-noop" | cut -d' ' -f1) == 2251afb6b792c08181e14205756a29c13f8dd15d5a3eb8ab6652efe55a65bb2c ]]
sha256sum "$mnt/root/glmark2/bin/glmark2-es2-null-noop" "$mnt/root/gpu-smoke.sh" > "$out/payload-hashes"
for path in /sys/class/devfreq/*; do
 for attr in available_frequencies governor min_freq max_freq cur_freq; do
  [[ ! -f "$path/$attr" ]] || echo "$path/$attr=$(cat "$path/$attr")"
 done
done > "$out/devfreq-before.txt"
# Match the shared path using the same supported 600 MHz OPP (594 MHz PLL).
gpu_devfreq=/sys/class/devfreq/fb000000.gpu
[[ -d "$gpu_devfreq" ]]
grep -qw 600000000 "$gpu_devfreq/available_frequencies"
echo userspace > "$gpu_devfreq/governor"
echo 600000000 > "$gpu_devfreq/userspace/set_freq"
echo NATIVE_GPU_OPP_REQUEST_HZ=600000000
cat "$gpu_devfreq/cur_freq"
[[ $(cat "$gpu_devfreq/cur_freq") == 600000000 ]]
[[ $(cat /sys/kernel/debug/clk/clk_gpu/clk_rate) == 594000000 ]]
sha256sum "$(modinfo -n panthor)" > "$out/native-module.sha256"
final_rc=0
for size in 1280x720 1920x1080; do
 label="native-$size"
 cat > "$mnt/root/gpu-smoke.env" <<ENV
GPU_SMOKE_TEST=glmark
GPU_SMOKE_GLMARK_FLAVOR=null-noop
GPU_SMOKE_GLMARK_SIZE=$size
GPU_SMOKE_GLMARK_FRAME_END=finish
GPU_SMOKE_GLMARK_SKIP_VALIDATE=0
GPU_SMOKE_GLMARK_BENCHMARKS=''
GPU_SMOKE_DRM_NODE=/dev/dri/renderD128
GPU_SMOKE_QUIET_CONSOLE=1
GPU_SMOKE_GUEST_SUBMIT_STATS=0
GPU_SMOKE_GUEST_IRQ_STATS=0
ENV
 env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin taskset -c 2 timeout -k 5 1200 chroot "$mnt" /root/gpu-smoke.sh > "$out/$label.log" 2>&1 &
 workload_pid=$!
 (
  taskset -pc 0 "$BASHPID" >/dev/null
  while kill -0 "$workload_pid" 2>/dev/null; do
   date -Is
   grep -E 'clk_gpu_src |clk_gpu ' /sys/kernel/debug/clk/clk_summary
   for f in /sys/class/devfreq/*/cur_freq /sys/class/thermal/thermal_zone0/temp /sys/class/thermal/thermal_zone5/temp /sys/devices/system/cpu/cpu2/cpufreq/scaling_cur_freq; do [[ ! -r "$f" ]] || echo "$f=$(cat "$f")"; done
   sleep 5
  done
 ) > "$out/$label.clock.log" &
 monitor_pid=$!
 rc=0
 wait "$workload_pid" || rc=$?
 kill "$monitor_pid" 2>/dev/null || true
 wait "$monitor_pid" 2>/dev/null || true
 echo "$rc" > "$out/$label.exit-code"
 mkdir -p "$out/$label-tmp"
 cp -a "$mnt/tmp/." "$out/$label-tmp/"
 cat "$out/$label.log"
 echo "NATIVE_PROFILE_RC size=$size rc=$rc"
 [[ $rc == 0 ]] || final_rc=1
done
exit "$final_rc"
