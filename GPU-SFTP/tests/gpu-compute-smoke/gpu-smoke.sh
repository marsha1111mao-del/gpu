#!/bin/sh
set -u

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

log() {
	printf '[gpu-smoke] %s\n' "$*"
}

run_optional() {
	log "+ $*"
	"$@" 2>&1
	rc=$?
	log "optional rc=${rc}"
	return 0
}

dump_perf_dmesg() {
	log "post-run passthrough dmesg excerpt:"
	dmesg | grep -E 'PANTHOR_PT_STATS|PANTHOR_PT_TIMING|PANTHOR_JOB_IRQ_STATS|PANTHOR_SUBMIT_STATS|DRM_SCHED_PUSH_STATS|DRM_SCHED_RUN_JOB_STATS|GPA2HPA|PTW|PTFREE|TABLE|gpu fault|job timeout|Unhandled fault|Oops|Unable to handle|WARN|ERROR|Failed' | tail -n 200 || true
}

find_panthor_pt_timing_param() {
	for path in \
		/sys/module/io_pgtable_arm/parameters/panthor_pt_timing \
		/sys/module/io-pgtable-arm/parameters/panthor_pt_timing \
		/sys/module/*/parameters/panthor_pt_timing; do
		if [ -w "${path}" ]; then
			printf '%s\n' "${path}"
			return 0
		fi
	done
	return 1
}

wait_for_drm() {
	i=0
	while [ "${i}" -lt 50 ]; do
		if [ -d /dev/dri ] &&
			{ ls /dev/dri/card* >/dev/null 2>&1 || ls /dev/dri/renderD* >/dev/null 2>&1; }; then
			return 0
		fi
		i=$((i + 1))
		sleep 0.1
	done
	return 1
}

log "kernel=$(uname -a)"
log "cmdline=$(cat /proc/cmdline 2>/dev/null || true)"

if wait_for_drm; then
	log "DRM nodes:"
	ls -l /dev/dri 2>&1 || true
else
	log "no DRM nodes appeared under /dev/dri"
fi

log "DRM sysfs:"
find /sys/class/drm -maxdepth 3 -type f \
	\( -name status -o -name dev -o -name driver -o -name vendor -o -name device \) \
	-print -exec sh -c 'printf "  "; cat "$1" 2>/dev/null || true' sh {} \; 2>/dev/null || true

log "panthor dmesg excerpt:"
dmesg | grep -E 'panthor|Panthor|drm|mali|MCU|firmware|Failed|ERROR|WARN' | tail -n 160 || true

export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}"

export LIBGL_ALWAYS_SOFTWARE=0
if [ -n "${MESA_LOADER_DRIVER_OVERRIDE:-}" ]; then
	export MESA_LOADER_DRIVER_OVERRIDE
fi
export MESA_DEBUG="${MESA_DEBUG:-context}"

if [ -f /root/gpu-smoke.env ]; then
	# shellcheck disable=SC1091
	. /root/gpu-smoke.env
fi

if [ -x /root/panthor_ioctl_smoke ]; then
	run_optional /root/panthor_ioctl_smoke
fi

if command -v eglinfo >/dev/null 2>&1; then
	run_optional eglinfo -B
fi

if [ ! -x /root/gles-compute-smoke ]; then
	log "missing /root/gles-compute-smoke"
	echo "GPU_SMOKE_RESULT=FAIL"
	exit 127
fi

if [ "${GPU_SMOKE_QUIET_CONSOLE:-0}" = 1 ]; then
	log "lowering console loglevel for performance run"
	dmesg -n 1 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_IRQ_STATS:-0}" = 1 ] &&
	[ -w /sys/module/panthor/parameters/job_irq_stats ]; then
	log "enabling guest panthor job IRQ timing stats"
	echo 1 >/sys/module/panthor/parameters/job_irq_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_SUBMIT_STATS:-0}" = 1 ] &&
	[ -w /sys/module/panthor/parameters/submit_stats ]; then
	log "enabling guest panthor submit timing stats"
	echo 1 >/sys/module/panthor/parameters/submit_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_SUBMIT_STATS:-0}" = 1 ] &&
	[ -w /sys/module/gpu_sched/parameters/push_stats ]; then
	log "enabling guest DRM scheduler push timing stats"
	echo 1 >/sys/module/gpu_sched/parameters/push_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_SUBMIT_STATS:-0}" = 1 ] &&
	[ -w /sys/module/gpu_sched/parameters/run_job_stats ]; then
	log "enabling guest DRM scheduler run-job worker timing stats"
	echo 1 >/sys/module/gpu_sched/parameters/run_job_stats 2>/dev/null || true
fi

PANTHOR_PT_TIMING_PARAM=
if [ "${GPU_SMOKE_GUEST_PT_TIMING:-0}" = 1 ]; then
	PANTHOR_PT_TIMING_PARAM=$(find_panthor_pt_timing_param || true)
	if [ -n "${PANTHOR_PT_TIMING_PARAM}" ]; then
		log "enabling guest passthrough page-table timing stats"
		echo 1 >"${PANTHOR_PT_TIMING_PARAM}" 2>/dev/null || true
	else
		log "guest passthrough page-table timing parameter not found"
	fi
fi

rc=99
for node in /dev/dri/card* /dev/dri/renderD* ""; do
	if [ -n "${node}" ] && [ ! -e "${node}" ]; then
		continue
	fi

	if [ -n "${node}" ]; then
		log "+ /root/gles-compute-smoke ${GPU_SMOKE_ARGS:-} ${node}"
		# shellcheck disable=SC2086
		/root/gles-compute-smoke ${GPU_SMOKE_ARGS:-} "${node}" 2>&1
	else
		log "+ /root/gles-compute-smoke ${GPU_SMOKE_ARGS:-}"
		# shellcheck disable=SC2086
		/root/gles-compute-smoke ${GPU_SMOKE_ARGS:-} 2>&1
	fi
	rc=$?
	log "gles-compute-smoke rc=${rc}"
	if [ "${rc}" -eq 0 ]; then
		break
	fi
done

if [ "${GPU_SMOKE_GUEST_IRQ_STATS:-0}" = 1 ] &&
	[ -w /sys/module/panthor/parameters/job_irq_stats ]; then
	log "disabling guest panthor job IRQ timing stats"
	echo 0 >/sys/module/panthor/parameters/job_irq_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_SUBMIT_STATS:-0}" = 1 ] &&
	[ -w /sys/module/panthor/parameters/submit_stats ]; then
	log "disabling guest panthor submit timing stats"
	echo 0 >/sys/module/panthor/parameters/submit_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_SUBMIT_STATS:-0}" = 1 ] &&
	[ -w /sys/module/gpu_sched/parameters/push_stats ]; then
	log "disabling guest DRM scheduler push timing stats"
	echo 0 >/sys/module/gpu_sched/parameters/push_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_SUBMIT_STATS:-0}" = 1 ] &&
	[ -w /sys/module/gpu_sched/parameters/run_job_stats ]; then
	log "disabling guest DRM scheduler run-job worker timing stats"
	echo 0 >/sys/module/gpu_sched/parameters/run_job_stats 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_PT_TIMING:-0}" = 1 ] &&
	[ -n "${PANTHOR_PT_TIMING_PARAM}" ] &&
	[ -w "${PANTHOR_PT_TIMING_PARAM}" ]; then
	log "disabling guest passthrough page-table timing stats"
	echo 0 >"${PANTHOR_PT_TIMING_PARAM}" 2>/dev/null || true
fi

if [ "${rc}" -eq 0 ]; then
	dump_perf_dmesg
	echo "GPU_SMOKE_RESULT=PASS"
	exit 0
fi

dump_perf_dmesg
echo "GPU_SMOKE_RESULT=FAIL"
exit "${rc}"
