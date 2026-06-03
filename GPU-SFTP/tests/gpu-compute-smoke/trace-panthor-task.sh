#!/bin/sh
set -u

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

OUT_DIR=${OUT_DIR:-/tmp/panthor-task-trace}
TRACE_ROOT=${TRACE_ROOT:-/sys/kernel/tracing}
BPFTRACE_SCRIPT=${BPFTRACE_SCRIPT:-/root/panthor-task.bt}
RUN_BPFTRACE=${RUN_BPFTRACE:-0}
STRACE_CONST_STYLE=${STRACE_CONST_STYLE:-raw}

log() {
	printf '[panthor-trace] %s\n' "$*"
}

have_cmd() {
	command -v "$1" >/dev/null 2>&1
}

choose_default_node() {
	for node in /dev/dri/card* /dev/dri/renderD*; do
		if [ -e "${node}" ]; then
			printf '%s\n' "${node}"
			return 0
		fi
	done
	return 1
}

write_ioctl_map() {
	cat >"${OUT_DIR}/panthor-ioctl-map.txt" <<'EOF'
0xc0106440 DRM_IOCTL_PANTHOR_DEV_QUERY
0xc0106441 DRM_IOCTL_PANTHOR_VM_CREATE
0xc0086442 DRM_IOCTL_PANTHOR_VM_DESTROY
0xc0186443 DRM_IOCTL_PANTHOR_VM_BIND
0xc0086444 DRM_IOCTL_PANTHOR_VM_GET_STATE
0xc0186445 DRM_IOCTL_PANTHOR_BO_CREATE
0xc0106446 DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET
0xc0386447 DRM_IOCTL_PANTHOR_GROUP_CREATE
0xc0086448 DRM_IOCTL_PANTHOR_GROUP_DESTROY
0xc0186449 DRM_IOCTL_PANTHOR_GROUP_SUBMIT
0xc010644a DRM_IOCTL_PANTHOR_GROUP_GET_STATE
0xc028644b DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE
0xc008644c DRM_IOCTL_PANTHOR_TILER_HEAP_DESTROY
EOF
}

mount_tracefs() {
	if [ -d "${TRACE_ROOT}" ] && [ -f "${TRACE_ROOT}/tracing_on" ]; then
		return 0
	fi

	mkdir -p "${TRACE_ROOT}" 2>/dev/null || true
	mount -t tracefs tracefs "${TRACE_ROOT}" 2>/dev/null || true

	[ -f "${TRACE_ROOT}/tracing_on" ]
}

reset_ftrace() {
	[ -f "${TRACE_ROOT}/tracing_on" ] || return 1

	echo 0 >"${TRACE_ROOT}/tracing_on" 2>/dev/null || true
	echo >"${TRACE_ROOT}/trace" 2>/dev/null || true
	echo >"${TRACE_ROOT}/kprobe_events" 2>/dev/null || true
	return 0
}

add_probe() {
	event="$1"
	if ! printf '%s\n' "${event}" >>"${TRACE_ROOT}/kprobe_events" 2>/dev/null; then
		log "skip kprobe: ${event}"
	fi
}

start_ftrace() {
	if ! mount_tracefs; then
		log "tracefs is unavailable; ftrace disabled"
		return 1
	fi

	if ! reset_ftrace; then
		log "cannot reset ftrace; ftrace disabled"
		return 1
	fi

	add_probe 'p:panthor_dev_query panthor_ioctl_dev_query'
	add_probe 'r:panthor_dev_query_ret panthor_ioctl_dev_query $retval'
	add_probe 'p:panthor_vm_create panthor_ioctl_vm_create'
	add_probe 'r:panthor_vm_create_ret panthor_ioctl_vm_create $retval'
	add_probe 'p:panthor_bo_create panthor_ioctl_bo_create'
	add_probe 'r:panthor_bo_create_ret panthor_ioctl_bo_create $retval'
	add_probe 'p:panthor_bo_mmap_offset panthor_ioctl_bo_mmap_offset'
	add_probe 'r:panthor_bo_mmap_offset_ret panthor_ioctl_bo_mmap_offset $retval'
	add_probe 'p:panthor_vm_bind panthor_ioctl_vm_bind'
	add_probe 'r:panthor_vm_bind_ret panthor_ioctl_vm_bind $retval'
	add_probe 'p:panthor_group_create panthor_ioctl_group_create'
	add_probe 'r:panthor_group_create_ret panthor_ioctl_group_create $retval'
	add_probe 'p:panthor_group_submit panthor_ioctl_group_submit'
	add_probe 'r:panthor_group_submit_ret panthor_ioctl_group_submit $retval'
	add_probe 'p:panthor_job_create panthor_job_create'
	add_probe 'r:panthor_job_create_ret panthor_job_create $retval'
	add_probe 'p:panthor_vm_bind_sync_op panthor_vm_bind_exec_sync_op'
	add_probe 'r:panthor_vm_bind_sync_op_ret panthor_vm_bind_exec_sync_op $retval'
	add_probe 'p:panthor_queue_run queue_run_job'
	add_probe 'r:panthor_queue_run_ret queue_run_job $retval'
	add_probe 'p:panthor_queue_timeout queue_timedout_job'

	echo 1 >"${TRACE_ROOT}/events/kprobes/enable" 2>/dev/null || true
	echo 1 >"${TRACE_ROOT}/tracing_on" 2>/dev/null || true
	return 0
}

stop_ftrace() {
	[ -f "${TRACE_ROOT}/tracing_on" ] || return 0

	echo 0 >"${TRACE_ROOT}/tracing_on" 2>/dev/null || true
	cat "${TRACE_ROOT}/trace" >"${OUT_DIR}/ftrace.txt" 2>/dev/null || true
	echo 0 >"${TRACE_ROOT}/events/kprobes/enable" 2>/dev/null || true
	echo >"${TRACE_ROOT}/kprobe_events" 2>/dev/null || true
}

start_bpftrace() {
	BPFTRACE_PID=

	if [ "${RUN_BPFTRACE}" != "1" ]; then
		return 0
	fi

	if ! have_cmd bpftrace; then
		log "bpftrace not found; bpftrace disabled"
		return 0
	fi

	if [ ! -f "${BPFTRACE_SCRIPT}" ]; then
		log "missing ${BPFTRACE_SCRIPT}; bpftrace disabled"
		return 0
	fi

	log "starting bpftrace"
	bpftrace "${BPFTRACE_SCRIPT}" >"${OUT_DIR}/bpftrace.txt" 2>&1 &
	BPFTRACE_PID=$!
	sleep 1
}

stop_bpftrace() {
	if [ "${BPFTRACE_PID:-}" ]; then
		kill "${BPFTRACE_PID}" 2>/dev/null || true
		wait "${BPFTRACE_PID}" 2>/dev/null || true
	fi
}

run_workload_direct() {
	"$@"
}

run_workload_strace() {
	if ! have_cmd strace; then
		log "strace not found; running workload without syscall trace"
		run_workload_direct "$@"
		return $?
	fi

	log "starting strace"
	strace -ff \
		-X "${STRACE_CONST_STYLE}" \
		-e trace=openat,close,ioctl,mmap,munmap,poll,ppoll,read,write,futex \
		-s 256 \
		-ttt \
		-o "${OUT_DIR}/strace" \
		"$@"
}

extract_strace_summary() {
	if ! have_cmd grep; then
		return 0
	fi

	grep -h 'ioctl' "${OUT_DIR}"/strace* >"${OUT_DIR}/ioctl-all.txt" 2>/dev/null || true
	grep -hE 'c0106440|c0106441|c0086442|c0186443|c0086444|c0186445|c0106446|c0386447|c0086448|c0186449|c010644a|c028644b|c008644c' \
		"${OUT_DIR}"/strace* >"${OUT_DIR}/ioctl-panthor.txt" 2>/dev/null || true
}

mkdir -p "${OUT_DIR}"
write_ioctl_map

if [ "$#" -eq 0 ]; then
	if [ ! -x /root/gles-compute-smoke ]; then
		log "no command provided and /root/gles-compute-smoke is missing"
		exit 127
	fi

	node=$(choose_default_node || true)
	if [ -n "${node:-}" ]; then
		set -- /root/gles-compute-smoke "${node}"
	else
		set -- /root/gles-compute-smoke
	fi
fi

log "output directory: ${OUT_DIR}"
log "workload: $*"

start_ftrace || true
start_bpftrace

rc=0
run_workload_strace "$@" || rc=$?

stop_bpftrace
stop_ftrace
extract_strace_summary

log "workload rc=${rc}"
log "trace files:"
find "${OUT_DIR}" -maxdepth 1 -type f -print 2>/dev/null | sort 2>/dev/null || true

exit "${rc}"
