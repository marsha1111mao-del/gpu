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

cmdline_value() {
	local key="$1"
	local word

	for word in $(cat /proc/cmdline 2>/dev/null); do
		case "${word}" in
		"${key}="*)
			printf '%s\n' "${word#*=}"
			return 0
			;;
		esac
	done
	return 1
}

decode_cmdline_arg_tokens() {
	local rest="$1"
	local out=""
	local token

	while :; do
		case "${rest}" in
		*:*)
			token="${rest%%:*}"
			rest="${rest#*:}"
			;;
		*)
			token="${rest}"
			rest=""
			;;
		esac

		if [ -n "${token}" ]; then
			if [ -n "${out}" ]; then
				out="${out} ${token}"
			else
				out="${token}"
			fi
		fi

		[ -n "${rest}" ] || break
	done

	printf '%s\n' "${out}"
}

apply_cmdline_overrides() {
	local value

	value="$(cmdline_value gpu_smoke_args_tokens || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_ARGS="$(decode_cmdline_arg_tokens "${value}")"
		export GPU_SMOKE_ARGS
	fi

	value="$(cmdline_value gpu_smoke_args_b64 || true)"
	if [ -n "${value}" ]; then
		if ! command -v base64 >/dev/null 2>&1; then
			log "missing base64 for gpu_smoke_args_b64"
			return 1
		fi
		GPU_SMOKE_ARGS="$(printf '%s' "${value}" | base64 -d 2>/dev/null)" || {
			log "failed to decode gpu_smoke_args_b64"
			return 1
		}
		export GPU_SMOKE_ARGS
	fi

	value="$(cmdline_value gpu_smoke_quiet_console || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_QUIET_CONSOLE="${value}"
		export GPU_SMOKE_QUIET_CONSOLE
	fi

	value="$(cmdline_value gpu_smoke_after_run || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_AFTER_RUN="${value}"
		export GPU_SMOKE_AFTER_RUN
	fi

	value="$(cmdline_value gpu_smoke_start_epoch || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_START_EPOCH="${value}"
		export GPU_SMOKE_START_EPOCH
	fi

	value="$(cmdline_value gpu_smoke_start_uptime_ms || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_START_UPTIME_MS="${value}"
		export GPU_SMOKE_START_UPTIME_MS
	fi

	value="$(cmdline_value gpu_smoke_vmshm_probe_handle || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_VMSHM_PROBE_HANDLE="${value}"
		export GPU_SMOKE_VMSHM_PROBE_HANDLE
	fi

	value="$(cmdline_value gpu_smoke_vmshm_probe_expect || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_VMSHM_PROBE_EXPECT="${value}"
		export GPU_SMOKE_VMSHM_PROBE_EXPECT
	fi

	value="$(cmdline_value gpu_smoke_vmshm_probe_spoof_vmid || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_VMSHM_PROBE_SPOOF_VMID="${value}"
		export GPU_SMOKE_VMSHM_PROBE_SPOOF_VMID
	fi

	value="$(cmdline_value gpu_smoke_ioctl_mode || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_IOCTL_MODE="${value}"
		export GPU_SMOKE_IOCTL_MODE
	fi

	value="$(cmdline_value gpu_smoke_ioctl_args_tokens || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_IOCTL_ARGS="$(decode_cmdline_arg_tokens "${value}")"
		export GPU_SMOKE_IOCTL_ARGS
	fi

	value="$(cmdline_value gpu_smoke_raw_rpc_probe_session || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_RAW_RPC_PROBE_SESSION="${value}"
		export GPU_SMOKE_RAW_RPC_PROBE_SESSION
	fi

	value="$(cmdline_value gpu_smoke_raw_rpc_probe_ops || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_RAW_RPC_PROBE_OPS="${value}"
		export GPU_SMOKE_RAW_RPC_PROBE_OPS
	fi

	value="$(cmdline_value gpu_smoke_raw_rpc_probe_timeout_ms || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_RAW_RPC_PROBE_TIMEOUT_MS="${value}"
		export GPU_SMOKE_RAW_RPC_PROBE_TIMEOUT_MS
	fi
}

dump_perf_dmesg() {
	log "post-run passthrough dmesg excerpt:"
	dmesg | grep -E 'CLIENT_COMM_RPC_STATS|PANTHOR_PT_STATS|PANTHOR_PT_TIMING|PANTHOR_JOB_IRQ_STATS|PANTHOR_SUBMIT_STATS|DRM_SCHED_PUSH_STATS|DRM_SCHED_RUN_JOB_STATS|GPA2HPA|PTW|PTFREE|TABLE|gpu fault|job timeout|Unhandled fault|Oops|Unable to handle|WARN|ERROR|Failed' | tail -n 240 || true
}

dump_client_comm_rpc_stats() {
	local param="/sys/module/client_comm_vmshm/parameters/rpc_stats"
	local value

	if [ ! -w "${param}" ]; then
		return 0
	fi

	value="$(cat "${param}" 2>/dev/null || true)"
	case "${value}" in
	1 | Y | y | true | True)
		log "dumping client vmshm RPC timing stats"
		echo 0 >"${param}" 2>/dev/null || true
		;;
	esac
}

dump_panthor_client_params() {
	local path="/sys/module/panthor_client/parameters/bo_mmap_cached"
	local value

	if [ ! -r "${path}" ]; then
		log "PANTHOR_CLIENT_BO_MMAP_CACHED=missing"
		return 0
	fi

	value="$(cat "${path}" 2>/dev/null || true)"
	log "PANTHOR_CLIENT_BO_MMAP_CACHED=${value}"
}

run_vmshm_lookup_probe() {
	local handle="${GPU_SMOKE_VMSHM_PROBE_HANDLE:-}"
	local expect="${GPU_SMOKE_VMSHM_PROBE_EXPECT:-denied}"
	local spoof="${GPU_SMOKE_VMSHM_PROBE_SPOOF_VMID:-}"
	local rc

	[ -n "${handle}" ] || return 0

	if [ ! -x /root/vmshm_lookup_probe ]; then
		log "missing /root/vmshm_lookup_probe for vmshm isolation probe"
		echo "VMSHM_ISOLATION_RESULT=FAIL"
		return 126
	fi

	if [ -n "${spoof}" ]; then
		log "+ /root/vmshm_lookup_probe --handle ${handle} --expect ${expect} --spoof-vmid ${spoof}"
		/root/vmshm_lookup_probe \
			--handle "${handle}" \
			--expect "${expect}" \
			--spoof-vmid "${spoof}" 2>&1
	else
		log "+ /root/vmshm_lookup_probe --handle ${handle} --expect ${expect}"
		/root/vmshm_lookup_probe \
			--handle "${handle}" \
			--expect "${expect}" 2>&1
	fi
	rc=$?

	if [ "${rc}" -eq 0 ]; then
		echo "VMSHM_ISOLATION_RESULT=PASS"
	else
		echo "VMSHM_ISOLATION_RESULT=FAIL rc=${rc}"
	fi
	return "${rc}"
}

run_vmshm_raw_rpc_probe() {
	local session="${GPU_SMOKE_RAW_RPC_PROBE_SESSION:-}"
	local ops="${GPU_SMOKE_RAW_RPC_PROBE_OPS:-dev-query,close-session}"
	local timeout_ms="${GPU_SMOKE_RAW_RPC_PROBE_TIMEOUT_MS:-1500}"
	local rc

	[ -n "${session}" ] || return 0

	if [ ! -x /root/vmshm_raw_rpc_probe ]; then
		log "missing /root/vmshm_raw_rpc_probe for raw vmshm RPC isolation probe"
		echo "VMSHM_RAW_RPC_RESULT=FAIL"
		return 126
	fi

	log "+ /root/vmshm_raw_rpc_probe --session ${session} --ops ${ops} --timeout-ms ${timeout_ms}"
	/root/vmshm_raw_rpc_probe \
		--session "${session}" \
		--ops "${ops}" \
		--timeout-ms "${timeout_ms}" 2>&1
	rc=$?

	if [ "${rc}" -ne 0 ]; then
		echo "VMSHM_RAW_RPC_RESULT=FAIL rc=${rc}"
	fi
	return "${rc}"
}

run_panthor_ioctl_holder() {
	local rc

	case "${GPU_SMOKE_IOCTL_MODE:-}" in
	holder | bo-hold)
		;;
	*)
		return 1
		;;
	esac

	if [ ! -x /root/panthor_ioctl_smoke ]; then
		log "missing /root/panthor_ioctl_smoke for ioctl holder"
		echo "GPU_SMOKE_RESULT=FAIL"
		return 126
	fi

	wait_for_smoke_start
	log "+ /root/panthor_ioctl_smoke ${GPU_SMOKE_IOCTL_ARGS:-}"
	# shellcheck disable=SC2086
	/root/panthor_ioctl_smoke ${GPU_SMOKE_IOCTL_ARGS:-} 2>&1
	rc=$?
	log "panthor_ioctl_smoke rc=${rc}"
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	if [ "${rc}" -eq 0 ]; then
		echo "GPU_SMOKE_RESULT=PASS"
	else
		echo "GPU_SMOKE_RESULT=FAIL"
	fi
	return "${rc}"
}

wait_for_smoke_start_epoch() {
	local target="${GPU_SMOKE_START_EPOCH:-0}"
	local now remaining

	case "${target}" in
	0 | '')
		return 0
		;;
	*[!0-9]*)
		log "invalid GPU_SMOKE_START_EPOCH=${target}; continuing without sync wait"
		return 0
		;;
	esac

	now="$(date +%s 2>/dev/null || echo 0)"
	case "${now}" in
	*[!0-9]*)
		now=0
		;;
	esac

	if [ "${now}" -ge "${target}" ]; then
		log "sync start epoch already reached target=${target} now=${now}"
		return 0
	fi

	remaining=$((target - now))
	if [ "${remaining}" -gt 120 ]; then
		log "sync start wait too large target=${target} now=${now} remaining=${remaining}; continuing without sync wait"
		return 0
	fi

	log "waiting for sync start epoch target=${target} now=${now} sleep=${remaining}"
	sleep "${remaining}"
	log "sync start epoch reached now=$(date +%s 2>/dev/null || echo unknown)"
}

uptime_ms() {
	awk '{printf "%d\n", $1 * 1000}' /proc/uptime 2>/dev/null || echo 0
}

wait_for_smoke_start_uptime() {
	local target="${GPU_SMOKE_START_UPTIME_MS:-0}"
	local now remaining sleep_sec

	case "${target}" in
	0 | '')
		return 1
		;;
	*[!0-9]*)
		log "invalid GPU_SMOKE_START_UPTIME_MS=${target}; continuing without sync wait"
		return 0
		;;
	esac

	now="$(uptime_ms)"
	case "${now}" in
	*[!0-9]*)
		now=0
		;;
	esac

	if [ "${now}" -ge "${target}" ]; then
		log "sync start uptime already reached target_ms=${target} now_ms=${now}"
		return 0
	fi

	remaining=$((target - now))
	if [ "${remaining}" -gt 120000 ]; then
		log "sync start uptime wait too large target_ms=${target} now_ms=${now} remaining_ms=${remaining}; continuing without sync wait"
		return 0
	fi

	sleep_sec=$(((remaining + 999) / 1000))
	log "waiting for sync start uptime target_ms=${target} now_ms=${now} sleep_sec=${sleep_sec}"
	sleep "${sleep_sec}"
	log "sync start uptime reached now_ms=$(uptime_ms)"
	return 0
}

wait_for_smoke_start() {
	if wait_for_smoke_start_uptime; then
		return 0
	fi

	wait_for_smoke_start_epoch
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

if ! apply_cmdline_overrides; then
	echo "GPU_SMOKE_RESULT=FAIL"
	exit 125
fi

if ! run_vmshm_raw_rpc_probe; then
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	echo "GPU_SMOKE_RESULT=FAIL"
	exit 126
fi

if [ -x /root/panthor_ioctl_smoke ]; then
	run_optional /root/panthor_ioctl_smoke
fi

case "${GPU_SMOKE_IOCTL_MODE:-}" in
holder | bo-hold)
	run_panthor_ioctl_holder
	exit $?
	;;
esac

if command -v eglinfo >/dev/null 2>&1; then
	run_optional eglinfo -B
fi

if [ ! -x /root/gles-compute-smoke ]; then
	log "missing /root/gles-compute-smoke"
	echo "GPU_SMOKE_RESULT=FAIL"
	exit 127
fi

dump_panthor_client_params

if ! run_vmshm_lookup_probe; then
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	echo "GPU_SMOKE_RESULT=FAIL"
	exit 126
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

wait_for_smoke_start

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
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	echo "GPU_SMOKE_RESULT=PASS"
	exit 0
fi

dump_client_comm_rpc_stats
dump_perf_dmesg
echo "GPU_SMOKE_RESULT=FAIL"
exit "${rc}"
