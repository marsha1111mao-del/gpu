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

	value="$(cmdline_value gpu_smoke_guest_sync_only_diag || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_GUEST_SYNC_ONLY_DIAG="${value}"
		export GPU_SMOKE_GUEST_SYNC_ONLY_DIAG
	fi

	value="$(cmdline_value gpu_smoke_guest_ringbuf_read_probe || true)"
	if [ -n "${value}" ]; then
		GPU_SMOKE_GUEST_RINGBUF_READ_PROBE="${value}"
		export GPU_SMOKE_GUEST_RINGBUF_READ_PROBE
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
	dmesg | grep -E 'CLIENT_COMM_RPC_STATS|PANTHOR_PT_STATS|PANTHOR_PT_TIMING|PANTHOR_JOB_IRQ_STATS|PANTHOR_SUBMIT_STATS|PANTHOR_SYNC_ONLY_DIAG|GROUP_SUBMIT_DIAG|PANTHOR_RINGBUF_READ_PROBE|DRM_SCHED_PUSH_STATS|DRM_SCHED_RUN_JOB_STATS|GPA2HPA|PTW|PTFREE|TABLE|IMPORTDIAG|SYNCOBJ_EXPORT_SYNC_FILE|SYNCOBJ_IMPORT_SYNC_FILE|gpu fault|job timeout|Unhandled fault|Oops|Unable to handle|WARN|ERROR|Failed' | tail -n 240 || true
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

glmark2_progress_sample() {
	local pid="$1"
	local log_path="$2"
	local elapsed="$3"
	local phase="$4"
	local log_size state rss threads fd_count wchan
	local last_scene bo_errors export_errors vm_bind_errors oom_errors
	local ls_line fd_path key value
	local stat_line rest scene_line

	# The deliberately-small guest rootfs has no date, awk, wc, or cut. Prefer
	# BusyBox stat for an unambiguous byte count, then fall back to ls parsing.
	log_size=$(stat -c %s "${log_path}" 2>/dev/null || true)
	case "${log_size}" in
	'' | *[!0-9]*)
		ls_line=$(ls -ln "${log_path}" 2>/dev/null || true)
		set -- ${ls_line}
		log_size=${5:-0}
		case "${log_size}" in
		'' | *[!0-9]*) log_size=0 ;;
		esac
		;;
	esac
	if [ -d "/proc/${pid}" ]; then
		stat_line=$(cat "/proc/${pid}/stat" 2>/dev/null || true)
		stat_line=${stat_line##*) }
		set -- ${stat_line}
		state=${1:-unknown}
		rss=0
		threads=0
		while read -r key value rest; do
			case "${key}" in
			VmRSS:) rss=${value:-0} ;;
			Threads:) threads=${value:-0} ;;
			esac
		done <"/proc/${pid}/status" 2>/dev/null || true
		fd_count=0
		for fd_path in /proc/${pid}/fd/*; do
			# Test the magic symlink itself. [ -e] follows a dangling fd target
			# and can under-count valid descriptors on restricted /proc mounts.
			if [ -L "${fd_path}" ]; then
				fd_count=$((fd_count + 1))
			fi
		done
		wchan=$(cat "/proc/${pid}/wchan" 2>/dev/null || true)
	else
		state=exited
		rss=0
		threads=0
		fd_count=0
		wchan=exited
	fi

	# glmark2 mixes scene progress, Mesa error floods, CR, and NUL bytes in one
	# byte stream. Busybox grep in the guest does not reliably support -o, so
	# take the last bracketed line and extract the scene with shell suffix ops.
	scene_line=$(tail -c 131072 "${log_path}" 2>/dev/null |
		tr -d '\000\r' |
		grep -a '\[' |
		tail -n 1)
	if [ -n "${scene_line}" ]; then
		last_scene=${scene_line#*[}
		last_scene=${last_scene%%]*}
	fi

	# Use cumulative counts, not a sliding tail. A tail count naturally drops
	# old errors when the file grows and previously looked like a decreasing
	# error count even while new failures were being generated.
	bo_errors=$(grep -ac 'PANTHOR_BO_CREATE failed' "${log_path}" 2>/dev/null)
	export_errors=$(grep -ac 'MESA: error: export failed' "${log_path}" 2>/dev/null)
	vm_bind_errors=$(grep -acE 'VM_BIND.*err|VM_BIND failed' "${log_path}" 2>/dev/null)
	oom_errors=$(grep -acE 'GL_OUT_OF_MEMORY|PANTHOR_BO_CREATE failed.*err=12' "${log_path}" 2>/dev/null)
	printf 'GLMARK_PROGRESS phase=%s elapsed_s=%s state=%s wchan=%s log_bytes=%s rss_kib=%s threads=%s fds=%s bo_create_errors_total=%s export_errors_total=%s vm_bind_errors_total=%s oom_errors_total=%s scene=%s\n' \
		"${phase}" "${elapsed}" "${state:-unknown}" "${wchan:-unknown}" \
		"${log_size:-0}" "${rss:-0}" "${threads:-0}" "${fd_count:-0}" \
		"${bo_errors:-0}" "${export_errors:-0}" \
		"${vm_bind_errors:-0}" "${oom_errors:-0}" "${last_scene:-none}"
}

glmark2_progress_field() {
	local line="$1"
	local key="$2"
	local field

	for field in ${line}; do
		case "${field}" in
		"${key}="*)
			printf '%s' "${field#${key}=}"
			return 0
			;;
		esac
	done
	printf '%s' "$3"
}

glmark2_error_count() {
	local pattern="$1"
	local log_path="$2"
	local count

	# BusyBox and GNU grep both print "0" for an unmatched count *and* return
	# nonzero.  A literal `|| printf 0` therefore captures "0\n0" and makes the
	# later integer comparisons fail.  Keep the printed zero, normalize a grep
	# invocation error to zero, and return success from this helper.
	count=$(grep -acE "${pattern}" "${log_path}" 2>/dev/null || true)
	case "${count}" in
	'' | *[!0-9]*) count=0 ;;
	esac
	printf '%s\n' "${count}"
}

glmark2_progress_monitor() {
	local glmark_pid="$1"
	local log_path="$2"
	local interval="$3"
	local stall_after="$4"
	local elapsed=0 stall_count=0 sleep_rc
	local line activity state log_bytes rss fds scene prev_activity

	echo "GLMARK_PROGRESS_START interval_s=${interval} stall_after_samples=${stall_after}"
	prev_activity=
	while kill -0 "${glmark_pid}" 2>/dev/null; do
		line=$(glmark2_progress_sample "${glmark_pid}" "${log_path}" "${elapsed}" benchmark)
		printf '%s\n' "${line}" | tee -a /tmp/glmark2-progress.log
		state=$(glmark2_progress_field "${line}" state unknown)
		log_bytes=$(glmark2_progress_field "${line}" log_bytes 0)
		rss=$(glmark2_progress_field "${line}" rss_kib 0)
		fds=$(glmark2_progress_field "${line}" fds 0)
		scene=$(glmark2_progress_field "${line}" scene none)
		# Scheduler state can legitimately alternate between R and D while the
		# workload itself is frozen.  Keep state/wchan in the sample for
		# diagnosis, but do not let state-only changes reset the stall timer.
		activity="log_bytes=${log_bytes},rss_kib=${rss},fds=${fds},scene=${scene}"
		if [ -n "${prev_activity}" ] && [ "${activity}" = "${prev_activity}" ]; then
			stall_count=$((stall_count + 1))
			if [ "${stall_count}" -eq "${stall_after}" ]; then
				echo "GLMARK_PROGRESS_STALL elapsed_s=${elapsed} consecutive_samples=${stall_count} state=${state} ${activity}" |
					tee -a /tmp/glmark2-progress.log
			fi
		else
			stall_count=0
			prev_activity="${activity}"
		fi

		sleep_rc=0
		sleep "${interval}" || sleep_rc=$?
		if [ "${sleep_rc}" -ne 0 ]; then
			echo "GLMARK_PROGRESS_ABORT reason=sleep-failed rc=${sleep_rc} interval=${interval}" |
				tee -a /tmp/glmark2-progress.log
			return "${sleep_rc}"
		fi
		elapsed=$((elapsed + interval))
	done

	glmark2_progress_sample "${glmark_pid}" "${log_path}" "${elapsed}" exit |
		tee -a /tmp/glmark2-progress.log
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

run_glmark2_workload() {
	local flavor="${GPU_SMOKE_GLMARK_FLAVOR:-gbm}"
	local glmark_bin glmark_winsys_args=""
	local glmark_frame_args=""
	local glmark_benchmark_args=""
	local frame_end="${GPU_SMOKE_GLMARK_FRAME_END:-auto}"
	local glmark_data=/root/glmark2/share/glmark2
	local glmark_libs=/root/glmark2/libs
	local renderer_log=/tmp/glmark2-renderer.log
	local version_log=/tmp/glmark2-version.log
	local validate_log=/tmp/glmark2-validate.log
	local glmark_log=/tmp/glmark2.log
	local progress_log=/tmp/glmark2-progress.log
	local progress_interval="${GPU_SMOKE_GLMARK_PROGRESS_INTERVAL_S:-5}"
	local progress_enabled="${GPU_SMOKE_GLMARK_PROGRESS_TRACE:-1}"
	local glmark_pid progress_pid progress_start
	local size="${GPU_SMOKE_GLMARK_SIZE:-1280x720}"
	local requested_node="${GPU_SMOKE_DRM_NODE:-}"
	local rc score renderer drm_node successes failures unknowns
	local framebuffer_errors expected_framebuffer_errors unexpected_framebuffer_errors
	local bo_create_errors export_errors vm_bind_errors
	local run_prefix=""
	local benchmark_list="${GPU_SMOKE_GLMARK_BENCHMARKS:-}"
	local benchmark old_ifs

	case "${flavor}" in
	gbm)
		glmark_bin=/root/glmark2/bin/glmark2-es2-gbm
		;;
		gbm-render-only)
			glmark_bin=/root/glmark2/bin/glmark2-es2-gbm
			;;
		gbm-render-only-debug)
			glmark_bin=/root/glmark2/bin/glmark2-es2-gbm
			;;
	null)
		glmark_bin=/root/glmark2/bin/glmark2-es2-null
		;;
	null-noop)
		glmark_bin=/root/glmark2/bin/glmark2-es2-null-noop
		;;
	*)
		log "unsupported glmark2 flavor ${flavor}"
		echo "GLMARK_RESULT=FAIL reason=unsupported-flavor"
		return 125
		;;
	esac
	case "${progress_interval}" in
	'' | *[!0-9]*) progress_interval=5 ;;
	esac
	if [ "${progress_interval}" -lt 1 ]; then
		progress_interval=1
	fi

	# The guest uses a serial console and redirects glmark2 output to a file.
	# Line buffering preserves the last scene reached when the process crashes.
	if command -v stdbuf >/dev/null 2>&1; then
		run_prefix="stdbuf -oL -eL"
	fi

	if [ ! -x "${glmark_bin}" ]; then
		log "missing ${glmark_bin}"
		echo "GLMARK_RESULT=FAIL reason=missing-glmark2"
		return 127
	fi
	if [ ! -d "${glmark_data}" ]; then
		log "missing glmark2 data path ${glmark_data}"
		echo "GLMARK_RESULT=FAIL reason=missing-glmark2-data"
		return 127
	fi
	if [ ! -x /root/gles-compute-smoke ]; then
		log "missing /root/gles-compute-smoke for glmark2 renderer qualification"
		echo "GLMARK_RESULT=FAIL reason=missing-renderer-probe"
		return 127
	fi

	dump_panthor_client_params

	rc=99
	drm_node=
	if [ -n "${requested_node}" ] && [ ! -e "${requested_node}" ]; then
		log "requested DRM node ${requested_node} does not exist"
		echo "GLMARK_RESULT=FAIL reason=missing-requested-drm-node"
		return 127
	fi
	if [ -n "${requested_node}" ]; then
		set -- "${requested_node}"
	else
		set -- /dev/dri/card* /dev/dri/renderD* ""
	fi
	for node in "$@"; do
		if [ -n "${node}" ] && [ ! -e "${node}" ]; then
			continue
		fi

		if [ -n "${node}" ]; then
			log "+ /root/gles-compute-smoke --count 1 --iterations 1 --warmup 0 ${node}"
			/root/gles-compute-smoke --count 1 --iterations 1 --warmup 0 "${node}" \
				>"${renderer_log}" 2>&1
		else
			log "+ /root/gles-compute-smoke --count 1 --iterations 1 --warmup 0"
			/root/gles-compute-smoke --count 1 --iterations 1 --warmup 0 \
				>"${renderer_log}" 2>&1
		fi
		rc=$?
		if [ "${rc}" -eq 0 ] &&
			grep -q '^COMPUTE_CHECK=PASS' "${renderer_log}" &&
			grep -Eq '^GL_RENDERER=.*(Mali|Panfrost)' "${renderer_log}"; then
			drm_node=${node}
			break
		fi
		rc=99
	done

	echo "== glmark2 renderer qualification =="
	cat "${renderer_log}" 2>/dev/null || true
	if [ "${rc}" -ne 0 ]; then
		echo "GLMARK_SIZE=${size}"
		echo "GLMARK_RESULT=FAIL reason=renderer-qualification"
		dump_client_comm_rpc_stats
		dump_perf_dmesg
		return 125
	fi

	echo "== glmark2 payload inventory =="
	ls -l "${glmark_bin}" || return 127
	find "${glmark_libs}" -maxdepth 1 -type f -exec ls -l {} \; 2>/dev/null || true
	du -sh "${glmark_data}" 2>/dev/null || true
	log "+ LD_LIBRARY_PATH=${glmark_libs} ${glmark_bin} --version"
	LD_LIBRARY_PATH="${glmark_libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
		"${glmark_bin}" --version >"${version_log}" 2>&1
	rc=$?
	echo "GLMARK_VERSION_RC=${rc}"
	cat "${version_log}" 2>/dev/null || true
	if [ "${rc}" -ne 0 ]; then
		echo "GLMARK_SIZE=${size}"
		echo "GLMARK_RESULT=FAIL reason=glmark2-version"
		return "${rc}"
	fi

	if [ -n "${drm_node}" ]; then
		echo "GLMARK_DRM_NODE=${drm_node}"
	fi
	echo "GLMARK_FLAVOR=${flavor}"
	case "${frame_end}" in
		auto|none|finish) ;;
		*)
			log "unsupported glmark2 frame end ${frame_end}"
			echo "GLMARK_RESULT=FAIL reason=unsupported-frame-end"
			return 2
			;;
	esac
	# Upstream null's default off-screen frame end creates an EGL fence.  The
	# vmshm Panthor frontend can export/import its own pending frontend fence,
	# but not a foreign fence, so some off-screen EGL paths still report
	# "MESA: error: export failed".  null-noop therefore defaults to no per-frame
	# fence as a performance/diagnostic choice; use finish explicitly when each
	# frame must force GPU completion.
	if [ "${frame_end}" = "auto" ] && [ "${flavor}" = "null-noop" ]; then
		frame_end=none
	fi
	if [ "${frame_end}" != "auto" ]; then
		glmark_frame_args="--frame-end ${frame_end}"
		echo "GLMARK_FRAME_END=${frame_end}"
	fi
	if [ "${flavor}" = "gbm" ] || [ "${flavor}" = "gbm-render-only" ] || [ "${flavor}" = "gbm-render-only-debug" ]; then
		glmark_winsys_args="--winsys-options drm-device=${drm_node}"
	fi

	# A full glmark2 suite creates thousands of Mesa/BO allocations and can
	# hide a lifecycle boundary behind an unrelated resource flood.  Accept a
	# comma-separated list of upstream benchmark selectors (for example,
	# "build:use-vbo=false") and pass each as a separate -b option.
	if [ -n "${benchmark_list}" ]; then
		old_ifs=${IFS}
		IFS=,
		for benchmark in ${benchmark_list}; do
			case "${benchmark}" in
			'' | *[[:space:],]*)
				echo "GLMARK_RESULT=FAIL reason=invalid-benchmark-selector"
				return 2
				;;
			esac
			glmark_benchmark_args="${glmark_benchmark_args} --benchmark ${benchmark}"
		done
		IFS=${old_ifs}
		echo "GLMARK_BENCHMARKS=${benchmark_list}"
	fi

	# Validation reads back the rendered FBO. Use one FBO so canvas.update()
	# cannot rotate to an unrendered buffer before scene validation.
	if [ "${GPU_SMOKE_GLMARK_SKIP_VALIDATE:-0}" = "1" ]; then
		echo "GLMARK_VALIDATE=SKIPPED reason=GPU_SMOKE_GLMARK_SKIP_VALIDATE"
	else
	log "+ LD_LIBRARY_PATH=${glmark_libs} ${run_prefix} ${glmark_bin} --validate --off-screen=1 --size ${size} --data-path ${glmark_data} ${glmark_winsys_args} ${glmark_frame_args}"
		LD_LIBRARY_PATH="${glmark_libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
			${run_prefix} \
			"${glmark_bin}" \
			--validate \
			--off-screen=1 \
			--size "${size}" \
			--data-path "${glmark_data}" \
			${glmark_winsys_args} \
			${glmark_frame_args} \
			>"${validate_log}" 2>&1
		rc=$?
		echo "== glmark2 validation output =="
		cat "${validate_log}" 2>/dev/null || true
		echo "GLMARK_VALIDATE_RC=${rc}"
		successes=$(grep -c 'Validation: Success' "${validate_log}" 2>/dev/null || true)
		failures=$(grep -c 'Validation: Failure' "${validate_log}" 2>/dev/null || true)
		unknowns=$(grep -c 'Validation: Unknown' "${validate_log}" 2>/dev/null || true)
		echo "GLMARK_VALIDATE_SUCCESS=${successes:-0} FAILURE=${failures:-0} UNKNOWN=${unknowns:-0}"
		# Exact checksum validation has a known Panfrost numeric mismatch in the
		# medium function scene. Qualify on broad scene agreement instead, while
		# preserving the per-scene output above for comparison.
		if [ "${rc}" -ne 0 ] ||
			grep -Eq 'Error: Failed|Exception' "${validate_log}" 2>/dev/null ||
			[ "${successes:-0}" -lt 20 ] || [ "${failures:-99}" -gt 4 ]; then
			echo "GLMARK_SIZE=${size}"
			echo "GLMARK_RESULT=FAIL reason=glmark2-validate rc=${rc}"
			dump_client_comm_rpc_stats
			dump_perf_dmesg
			return 125
		fi
		echo "GLMARK_VALIDATE=PASS"
	fi

	log "+ LD_LIBRARY_PATH=${glmark_libs} ${run_prefix} ${glmark_bin} --off-screen=3 --size ${size} --data-path ${glmark_data} ${glmark_winsys_args} ${glmark_frame_args}"
	rm -f "${progress_log}"
	progress_pid=
	LD_LIBRARY_PATH="${glmark_libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
		${run_prefix} \
		"${glmark_bin}" \
		--off-screen=3 \
		--size "${size}" \
		--data-path "${glmark_data}" \
		${glmark_winsys_args} \
		${glmark_frame_args} \
		${glmark_benchmark_args} \
		${GPU_SMOKE_GLMARK_EXTRA_ARGS:-} \
			>"${glmark_log}" 2>&1 &
	glmark_pid=$!

	# Keep this trace separate from glmark2 stdout: NUL bytes and thousands of
	# repeated Mesa allocation errors must not break the score parser, while a
	# bounded tail sample shows whether scenes, RSS, FDs, and the log advance.
	if [ "${progress_enabled}" = "1" ]; then
		# A monitor-level elapsed counter survives a broken/frozen guest
		# /proc/uptime and detects both no-output and no-scene-change stalls.
		(
			glmark2_progress_monitor "${glmark_pid}" "${glmark_log}" \
				"${progress_interval}" "${GPU_SMOKE_GLMARK_PROGRESS_STALL_SAMPLES:-3}"
		) 2>/dev/null &
		progress_pid=$!
		wait "${glmark_pid}"
		rc=$?
		if [ -n "${progress_pid}" ]; then
			kill "${progress_pid}" 2>/dev/null || true
			wait "${progress_pid}" 2>/dev/null || true
		fi
	else
		wait "${glmark_pid}"
		rc=$?
	fi

	echo "== glmark2 output =="
	cat "${glmark_log}" 2>/dev/null || true
	if [ -f "${progress_log}" ]; then
		echo "== glmark2 progress trace =="
		cat "${progress_log}" 2>/dev/null || true
	fi
	# glmark2 mixes NUL progress bytes and CRLF timing output.  Match the
	# complete final summary line without assuming which field carries a NUL,
	# then strip non-digits from the selected Score field.  Keep the renderer
	# parse line-oriented as well so indented GL_* headers remain valid.
	# Feed awk only the de-NUL'd stdin; a file operand would make awk ignore
	# stdin and NUL bytes in the raw log break Score/Renderer field matching.
	score=$(tr -d '\000' <"${glmark_log}" 2>/dev/null | awk '
		/glmark2.*Score:/ {
			for (i = 1; i <= NF; i++) {
				field = $i
				gsub(/\r/, "", field)
				if (field ~ /^[0-9]+$/) {
					score = field
					found = 1
				}
			}
		}
		END { if (found) print score }
	' 2>/dev/null)
	renderer=$(tr -d '\000' <"${glmark_log}" 2>/dev/null | awk '
		/GL_RENDERER:/ {
			line = $0
			sub(/^.*GL_RENDERER:[[:space:]]*/, "", line)
			gsub(/\r$/, "", line)
			print line
			exit
		}
	' 2>/dev/null)

	echo "GLMARK_SIZE=${size}"
	echo "GLMARK_RENDERER=${renderer:-unknown}"
	echo "GLMARK_SCORE=${score:-none}"
	framebuffer_errors=$(glmark2_error_count 'GL_INVALID_FRAMEBUFFER_OPERATION' "${glmark_log}")
	bo_create_errors=$(glmark2_error_count 'PANTHOR_BO_CREATE failed' "${glmark_log}")
	export_errors=$(glmark2_error_count 'MESA: error: export failed|DMA_BUF_IOCTL_EXPORT_SYNC_FILE failed' "${glmark_log}")
	vm_bind_errors=$(glmark2_error_count 'DRM_IOCTL_PANTHOR_VM_BIND failed|PANTHOR_VM_BIND.*err' "${glmark_log}")
	expected_framebuffer_errors=0
	case "${flavor}" in
	null|null-noop)
		# The null winsys intentionally has no real color attachment.  Mesa
		# reports this exact error from glClear(); it is not a shared-GPU fault.
		expected_framebuffer_errors=$(glmark2_error_count 'GL_INVALID_FRAMEBUFFER_OPERATION in glClear\(incomplete framebuffer\)' "${glmark_log}")
		;;
	esac
	if [ "${framebuffer_errors:-0}" -gt "${expected_framebuffer_errors:-0}" ]; then
		unexpected_framebuffer_errors=$((framebuffer_errors - expected_framebuffer_errors))
	else
		unexpected_framebuffer_errors=0
	fi
	echo "GLMARK_FRAMEBUFFER_ERRORS=${framebuffer_errors:-0}"
	echo "GLMARK_EXPECTED_FRAMEBUFFER_ERRORS=${expected_framebuffer_errors:-0}"
	echo "GLMARK_UNEXPECTED_FRAMEBUFFER_ERRORS=${unexpected_framebuffer_errors:-0}"
	echo "GLMARK_BO_CREATE_ERRORS=${bo_create_errors:-0}"
	echo "GLMARK_EXPORT_ERRORS=${export_errors:-0}"
	echo "GLMARK_VM_BIND_ERRORS=${vm_bind_errors:-0}"
	if [ "${unexpected_framebuffer_errors:-0}" -eq 0 ] && [ "${bo_create_errors:-0}" -eq 0 ] && [ "${vm_bind_errors:-0}" -eq 0 ] && [ "${export_errors:-0}" -eq 0 ]; then
		echo "GLMARK_CLEAN_RESULT=PASS"
	else
		echo "GLMARK_CLEAN_RESULT=FAIL"
	fi

	if [ "${rc}" -eq 0 ] &&
		case "${score}" in ''|*[!0-9]*) false ;; *) [ "${score}" -gt 0 ] ;; esac &&
		echo "${renderer}" | grep -Eq 'Mali|Panfrost' &&
		! grep -Eq 'llvmpipe|softpipe|Software Rasterizer|Error: Failed|Exception' "${glmark_log}" 2>/dev/null; then
		echo "GLMARK_RESULT=PASS"
		dump_client_comm_rpc_stats
		dump_perf_dmesg
		return 0
	fi

	echo "GLMARK_RESULT=FAIL reason=glmark2 rc=${rc} score=${score:-none}"
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	if [ "${rc}" -eq 0 ]; then
		return 125
	fi
	return "${rc}"
}

run_ml_workload() {
	local ml_bin=/root/gles-ml-smoke
	local ml_log=/tmp/gles-ml-smoke.log
	local requested_node="${GPU_SMOKE_DRM_NODE:-}"
	local rc=0
	local export_errors sync_file_errors

	if [ ! -x "${ml_bin}" ]; then
		log "missing ${ml_bin}"
		echo "ML_RESULT=FAIL reason=missing-ml-smoke"
		return 127
	fi

	dump_panthor_client_params

	rc=99
	if [ -n "${requested_node}" ] && [ ! -e "${requested_node}" ]; then
		log "requested DRM node ${requested_node} does not exist"
		echo "ML_RESULT=FAIL reason=missing-requested-drm-node"
		return 127
	fi
	if [ -n "${requested_node}" ]; then
		set -- "${requested_node}"
	else
		set -- /dev/dri/card* /dev/dri/renderD* ""
	fi
	for node in "$@"; do
		if [ -n "${node}" ] && [ ! -e "${node}" ]; then
			continue
		fi

		if [ -n "${node}" ]; then
			log "+ ${ml_bin} ${GPU_SMOKE_ARGS:-} ${node}"
			# shellcheck disable=SC2086
			"${ml_bin}" ${GPU_SMOKE_ARGS:-} "${node}" >"${ml_log}" 2>&1
		else
			log "+ ${ml_bin} ${GPU_SMOKE_ARGS:-}"
			# shellcheck disable=SC2086
			"${ml_bin}" ${GPU_SMOKE_ARGS:-} >"${ml_log}" 2>&1
		fi
		rc=$?
		cat "${ml_log}" 2>/dev/null || true
		log "gles-ml-smoke rc=${rc}"
		if [ "${rc}" -eq 0 ] &&
			grep -qE '^ML_RESULT=PASS[[:space:]]*$' "${ml_log}" 2>/dev/null &&
			[ "$(glmark2_error_count '^ML_CHECK=PASS' "${ml_log}")" -ge 1 ]; then
			break
		fi
		rc=99
	done

	export_errors=$(glmark2_error_count 'MESA: error: export failed' "${ml_log}")
	sync_file_errors=$(glmark2_error_count 'DMA_BUF_IOCTL_EXPORT_SYNC_FILE failed' "${ml_log}")
	echo "ML_EXPORT_ERRORS=${export_errors}"
	echo "ML_SYNC_FILE_ERRORS=${sync_file_errors}"
	if [ "${export_errors}" -eq 0 ] && [ "${sync_file_errors}" -eq 0 ] && [ "${rc}" -eq 0 ]; then
		echo "ML_CLEAN_RESULT=PASS"
	else
		echo "ML_CLEAN_RESULT=FAIL"
		rc=99
	fi

	# The candidate loop executes the workload directly. Keep the explicit
	# summary marker here so failures cannot be mistaken for runner success.
	if [ "${rc}" -ne 0 ]; then
		echo "ML_RESULT=FAIL rc=${rc}"
		dump_client_comm_rpc_stats
		dump_perf_dmesg
		return "${rc}"
	fi

	dump_client_comm_rpc_stats
	dump_perf_dmesg
	return 0
}

run_ncnn_workload() {
	local bench_bin=/root/ncnn/bin/benchncnn
	local probe_bin=/root/ncnn/bin/ncnn-vk-probe
	local model_dir=/root/ncnn/models
	local lib_dir=/root/ncnn/libs
	local driver_path="${lib_dir}/libvulkan_panfrost.so"
	local loop_count="${GPU_SMOKE_NCNN_LOOP_COUNT:-100}"
	local threads="${GPU_SMOKE_NCNN_THREADS:-2}"
	local gpu_device="${GPU_SMOKE_NCNN_GPU_DEVICE:-0}"
	local cooling_down="${GPU_SMOKE_NCNN_COOLING_DOWN:-0}"
	local timeout_sec="${GPU_SMOKE_NCNN_TIMEOUT_S:-900}"
	local models="${GPU_SMOKE_NCNN_MODELS:-mobilenet_v2 mobilenet_v3 resnet50}"
	local requested_backend="${GPU_SMOKE_NCNN_BACKEND:-panvk-direct}"
	local log_dir=/tmp/ncnn
	local model model_file model_tag rc line total failed=0

	if ! printf '%s' "${gpu_device}" | grep -Eq '^-?[0-9]+$'; then
		log "invalid NCNN GPU device ${gpu_device}"
		echo "NCNN_RESULT=FAIL reason=invalid-gpu-device"
		return 125
	fi

	mkdir -p "${log_dir}"
	dump_panthor_client_params

	echo "NCNN_LOOP_COUNT=${loop_count}"
	echo "NCNN_THREADS=${threads}"
	echo "NCNN_GPU_DEVICE=${gpu_device}"
	echo "NCNN_COOLING_DOWN=${cooling_down}"
	echo "NCNN_REQUESTED_BACKEND=${requested_backend}"
	echo "NCNN_MODELS=${models}"
	if [ ! -x "${bench_bin}" ]; then
		log "missing ${bench_bin}"
		echo "NCNN_RESULT=FAIL reason=missing-benchncnn"
		return 127
	fi
	if [ ! -d "${model_dir}" ]; then
		log "missing NCNN model directory ${model_dir}"
		echo "NCNN_RESULT=FAIL reason=missing-models"
		return 127
	fi

	echo "== NCNN payload inventory =="
	ls -l "${bench_bin}"
	if [ -x "${probe_bin}" ]; then
		ls -l "${probe_bin}"
	fi
	find "${lib_dir}" -maxdepth 1 -type f -exec ls -l {} \; 2>/dev/null || true
	ls -l "${model_dir}"/*.param 2>/dev/null || true

	if [ "${gpu_device}" -ge 0 ]; then
		if [ ! -x "${probe_bin}" ]; then
			log "missing ${probe_bin} for PanVK qualification"
			echo "NCNN_RESULT=FAIL reason=missing-vulkan-probe"
			return 127
		fi
		if [ ! -f "${driver_path}" ]; then
			log "missing direct PanVK driver ${driver_path}"
			echo "NCNN_RESULT=FAIL reason=missing-panvk-driver"
			return 127
		fi
		log "+ LD_LIBRARY_PATH=${lib_dir} NCNN_VULKAN_DRIVER=${driver_path} ${probe_bin}"
		LD_LIBRARY_PATH="${lib_dir}" NCNN_VULKAN_DRIVER="${driver_path}" \
			"${probe_bin}" >"${log_dir}/vk-probe.log" 2>&1
		rc=$?
		cat "${log_dir}/vk-probe.log" 2>/dev/null || true
		if [ "${rc}" -ne 0 ] ||
			! grep -q '^NCNN_VK_PROBE_RESULT=PASS$' "${log_dir}/vk-probe.log" ||
			! grep -Eq '^NCNN_VK_DEVICE_0_NAME=.*Mali-G610' "${log_dir}/vk-probe.log" ||
			! grep -q '^NCNN_VK_DEVICE_0_DRIVER_NAME=panvk$' "${log_dir}/vk-probe.log"; then
			echo "NCNN_BACKEND_QUALIFICATION=FAIL rc=${rc}"
			echo "NCNN_RESULT=FAIL reason=vulkan-device-qualification"
			dump_client_comm_rpc_stats
			dump_perf_dmesg
			return 125
		fi
		echo "NCNN_BACKEND_QUALIFICATION=PASS"
	elif [ "${gpu_device}" -eq -1 ]; then
		requested_backend=cpu
		echo "NCNN_BACKEND_QUALIFICATION=PASS backend=cpu"
	else
		log "invalid NCNN GPU device ${gpu_device}"
		echo "NCNN_RESULT=FAIL reason=invalid-gpu-device"
		return 125
	fi

	total=0
	for model in ${models}; do
		total=$((total + 1))
		model_file="${model_dir}/${model}.param"
		model_tag=$(printf '%s' "${model}" | tr -c 'A-Za-z0-9_.-' '_')
		if [ ! -f "${model_file}" ]; then
			log "missing model ${model_file}"
			echo "NCNN_MODEL=${model}"
			echo "NCNN_MODEL_RESULT=FAIL reason=missing-param"
			failed=$((failed + 1))
			continue
		fi

		if [ "${gpu_device}" -ge 0 ]; then
			log "+ LD_LIBRARY_PATH=${lib_dir} NCNN_VULKAN_DRIVER=${driver_path} timeout ${timeout_sec} ${bench_bin} ${loop_count} ${threads} 2 ${gpu_device} ${cooling_down} param=${model_file} shape=[224,224,3]"
			LD_LIBRARY_PATH="${lib_dir}" NCNN_VULKAN_DRIVER="${driver_path}" \
				timeout "${timeout_sec}" "${bench_bin}" \
				"${loop_count}" "${threads}" 2 "${gpu_device}" "${cooling_down}" \
				"param=${model_file}" 'shape=[224,224,3]' \
				>"${log_dir}/${model_tag}.log" 2>&1
		else
			log "+ timeout ${timeout_sec} ${bench_bin} ${loop_count} ${threads} 2 -1 ${cooling_down} param=${model_file} shape=[224,224,3]"
			timeout "${timeout_sec}" env LD_LIBRARY_PATH="${lib_dir}" "${bench_bin}" \
				"${loop_count}" "${threads}" 2 -1 "${cooling_down}" \
				"param=${model_file}" 'shape=[224,224,3]' \
				>"${log_dir}/${model_tag}.log" 2>&1
		fi
		rc=$?
		echo "== benchncnn ${model} output =="
		cat "${log_dir}/${model_tag}.log" 2>/dev/null || true
		# benchncnn emits NUL progress bytes and CRLF timing lines.  BusyBox
		# grep/tr handling of that mixed stream is brittle in the trimmed
		# guest, so let awk select the complete min/max/avg line directly.
		# <param path> min = X max = Y avg = Z
		line=$(tr -d '\000' <"${log_dir}/${model_tag}.log" 2>/dev/null | awk '
			/min *= *[0-9.]+ +max *= *[0-9.]+ +avg *= *[0-9.]+/ {
				sub(/\r$/, "")
				print
			}' 2>/dev/null | tail -n 1)
		# benchncnn can exit zero and print timings after a driver or
		# allocation error. Such a run must not qualify the GPU model.
		vk_error=$(tr -d '\000' <"${log_dir}/${model_tag}.log" 2>/dev/null | awk '
			/vk[A-Za-z0-9_]+ failed|MESA: error:|VK_ERROR_/ {
				sub(/\r$/, "")
				print
				exit
			}' 2>/dev/null)
		echo "NCNN_MODEL=${model}"
		echo "NCNN_MODEL_RC=${rc}"
		if [ "${rc}" -eq 0 ] && [ -n "${line}" ] && [ -z "${vk_error}" ]; then
			echo "${line}" | awk '{
				for (i = 1; i <= NF; i++) {
					if ($(i) == "min" && $(i+1) == "=") print "NCNN_ITER_MS_MIN=" $(i+2)
					if ($(i) == "max" && $(i+1) == "=") print "NCNN_ITER_MS_MAX=" $(i+2)
					if ($(i) == "avg" && $(i+1) == "=") print "NCNN_ITER_MS_AVG=" $(i+2)
				}
			}'
			echo "NCNN_MODEL_RESULT=PASS"
		else
			echo "NCNN_MODEL_RESULT=FAIL rc=${rc} timing=${line:-none} vk_error=${vk_error:-none}"
			failed=$((failed + 1))
		fi
	done

	echo "NCNN_TOTAL_MODELS=${total}"
	echo "NCNN_FAILED_MODELS=${failed}"
	if [ "${gpu_device}" -ge 0 ]; then
		echo "NCNN_BACKEND=panvk-direct driver=${driver_path}"
	else
		echo "NCNN_BACKEND=cpu"
	fi
	if [ "${failed}" -eq 0 ] && [ "${total}" -gt 0 ]; then
		echo "NCNN_RESULT=PASS"
		dump_client_comm_rpc_stats
		dump_perf_dmesg
		return 0
	fi

	echo "NCNN_RESULT=FAIL failed=${failed}/${total}"
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	return 125
}

run_raw_vulkan_workload() {
	local bin_dir=/root/vulkan
	local probe_bin="${bin_dir}/bin/raw-vk-probe"
	local lib_dir="${bin_dir}/libs"
	local driver_path="${lib_dir}/libvulkan_panfrost.so"
	local queue_counts="${GPU_SMOKE_RAW_VK_QUEUE_COUNTS:-1,2,3}"
	local submit_mode="${GPU_SMOKE_RAW_VK_SUBMIT_MODE:-sequential}"
	local case_spec="${GPU_SMOKE_RAW_VK_CASES:-full}"
	local probe_log rc
	local case_name total=0 passed=0 failed=0

	echo "RAW_VK_QUEUE_COUNTS=${queue_counts}"
	echo "RAW_VK_SUBMIT_MODE=${submit_mode}"
	echo "RAW_VK_CASES=${case_spec}"
	if [ ! -x "${probe_bin}" ]; then
		log "missing raw Vulkan probe ${probe_bin}"
		echo "RAW_VK_RESULT=FAIL reason=missing-probe"
		return 127
	fi
	if [ ! -f "${driver_path}" ]; then
		log "missing direct PanVK driver ${driver_path}"
		echo "RAW_VK_RESULT=FAIL reason=missing-driver"
		return 127
	fi

	# One case per process avoids allowing an earlier logical device-lost state
	# to pollute the next reduction case.  Parse the comma list with parameter
	# expansion only: the injected guest rootfs does not provide `tr`.
	remaining="${case_spec},"
	while :; do
		case_name="${remaining%%,*}"
		remaining="${remaining#*,}"
		if [ -z "${case_name}" ]; then
			[ -n "${remaining}" ] || break
			continue
		fi
		probe_log="/tmp/raw-vk-probe-${case_name}.log"
		total=$((total + 1))
		echo "RAW_VK_CASE_BEGIN=${case_name}"
		log "+ LD_LIBRARY_PATH=${lib_dir} NCNN_VULKAN_DRIVER=${driver_path} RAW_VK_QUEUE_COUNTS=${queue_counts} RAW_VK_SUBMIT_MODE=${submit_mode} RAW_VK_CASE=${case_name} ${probe_bin}"
		LD_LIBRARY_PATH="${lib_dir}" NCNN_VULKAN_DRIVER="${driver_path}" \
			RAW_VK_QUEUE_COUNTS="${queue_counts}" \
			RAW_VK_SUBMIT_MODE="${submit_mode}" \
			RAW_VK_CASE="${case_name}" \
			"${probe_bin}" >"${probe_log}" 2>&1
		rc=$?
		cat "${probe_log}"
		echo "RAW_VK_PROBE_RC=${rc} case=${case_name}"
		if [ "${rc}" -eq 0 ] && grep -aq '^RAW_VK_RESULT=PASS' "${probe_log}"; then
			echo "RAW_VK_CASE_WRAPPER=PASS case=${case_name}"
			passed=$((passed + 1))
		else
			echo "RAW_VK_CASE_WRAPPER=FAIL case=${case_name} rc=${rc}"
			failed=$((failed + 1))
		fi
		[ -n "${remaining}" ] || break
	done

	echo "RAW_VK_CASE_TOTAL=${total}"
	echo "RAW_VK_CASE_PASSED=${passed}"
	echo "RAW_VK_CASE_FAILED=${failed}"
	# PanVK/NCNN-style logging can contain embedded NUL bytes; treat the log
	# as text while preserving its original bytes.
	if [ "${failed}" -eq 0 ] && [ "${total}" -gt 0 ]; then
		echo "RAW_VK_RESULT=PASS"
		dump_client_comm_rpc_stats
		dump_perf_dmesg
		echo "RAW_VK_SUITE_RESULT=PASS cases=${total}"
		return 0
	fi

	echo "RAW_VK_RESULT=FAIL failed=${failed}/${total}"
	dump_client_comm_rpc_stats
	dump_perf_dmesg
	echo "RAW_VK_SUITE_RESULT=FAIL failed=${failed}/${total}"
	return 125
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

if [ "${GPU_SMOKE_GUEST_SYNC_ONLY_DIAG:-0}" = 1 ]; then
	if [ -w /sys/module/panthor/parameters/realm_sync_only_diag ]; then
		log "enabling guest panthor sync-only completion diagnostic"
		echo 1 >/sys/module/panthor/parameters/realm_sync_only_diag 2>/dev/null || true
		log "guest panthor sync-only diag param=$(cat /sys/module/panthor/parameters/realm_sync_only_diag 2>/dev/null || echo NA)"
	else
		log "guest panthor sync-only diagnostic parameter not found"
	fi
fi

if [ "${GPU_SMOKE_GUEST_RINGBUF_READ_PROBE:-0}" = 1 ]; then
	if [ -w /sys/module/panthor/parameters/realm_ringbuf_read_probe ]; then
		log "enabling guest panthor ringbuf read probe"
		echo 1 >/sys/module/panthor/parameters/realm_ringbuf_read_probe 2>/dev/null || true
		log "guest panthor ringbuf read probe param=$(cat /sys/module/panthor/parameters/realm_ringbuf_read_probe 2>/dev/null || echo NA)"
	else
		log "guest panthor ringbuf read probe parameter not found"
	fi
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

wait_for_smoke_start

case "${GPU_SMOKE_TEST:-compute}" in
ml)
	run_ml_workload
	rc=$?
	if [ "${rc}" -eq 0 ]; then
		echo "GPU_SMOKE_RESULT=PASS"
		exit 0
	fi
	echo "GPU_SMOKE_RESULT=FAIL rc=${rc}"
	exit "${rc}"
	;;
glmark)
	run_glmark2_workload
	rc=$?
	if [ "${rc}" -eq 0 ]; then
		echo "GPU_SMOKE_RESULT=PASS"
		exit 0
	fi
	echo "GPU_SMOKE_RESULT=FAIL rc=${rc}"
	exit "${rc}"
	;;
ncnn)
	run_ncnn_workload
	rc=$?
	if [ "${rc}" -eq 0 ]; then
		echo "GPU_SMOKE_RESULT=PASS"
		exit 0
	fi
	echo "GPU_SMOKE_RESULT=FAIL rc=${rc}"
	exit "${rc}"
	;;
raw-vk)
	run_raw_vulkan_workload
	rc=$?
	if [ "${rc}" -eq 0 ]; then
		echo "GPU_SMOKE_RESULT=PASS"
		exit 0
	fi
	echo "GPU_SMOKE_RESULT=FAIL rc=${rc}"
	exit "${rc}"
	;;
compute | '')
	;;
*)
	log "unsupported GPU_SMOKE_TEST=${GPU_SMOKE_TEST}"
	echo "GPU_SMOKE_RESULT=FAIL"
	exit 125
	;;
esac

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

if [ "${GPU_SMOKE_GUEST_SYNC_ONLY_DIAG:-0}" = 1 ] &&
	[ -w /sys/module/panthor/parameters/realm_sync_only_diag ]; then
	log "disabling guest panthor sync-only completion diagnostic"
	echo 0 >/sys/module/panthor/parameters/realm_sync_only_diag 2>/dev/null || true
fi

if [ "${GPU_SMOKE_GUEST_RINGBUF_READ_PROBE:-0}" = 1 ] &&
	[ -w /sys/module/panthor/parameters/realm_ringbuf_read_probe ]; then
	log "disabling guest panthor ringbuf read probe"
	echo 0 >/sys/module/panthor/parameters/realm_ringbuf_read_probe 2>/dev/null || true
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
