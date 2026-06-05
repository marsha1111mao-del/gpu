#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

SFTP_ROOT=${SFTP_ROOT:-"${ROOT_DIR}/GPU-SFTP"}
SFTP_BINS=${SFTP_BINS:-"${SFTP_ROOT}/firecracker-bins"}
SFTP_LOG_ROOT=${SFTP_LOG_ROOT:-"${SFTP_ROOT}/log"}
BUILD_GUEST_VMSHM_KERNELS=${BUILD_GUEST_VMSHM_KERNELS:-"${ROOT_DIR}/scripts/build/build-guest-vmshm-kernels.sh"}
BUILD_FIRECRACKER_RUNTIME=${BUILD_FIRECRACKER_RUNTIME:-"${ROOT_DIR}/scripts/build/build-firecracker-runtime.sh"}
BUILD_PANTHOR_IOCTL_SMOKE=${BUILD_PANTHOR_IOCTL_SMOKE:-"${ROOT_DIR}/scripts/build/build-panthor-ioctl-smoke.sh"}

REMOTE_HOST=${REMOTE_HOST:-192.168.137.10}
REMOTE_USER=${REMOTE_USER:-root}
REMOTE_PASS=${REMOTE_PASS:-root}
REMOTE_ROOT=${REMOTE_ROOT:-/root/GPU-SFTP}
REMOTE_BINS=${REMOTE_BINS:-"${REMOTE_ROOT}/firecracker-bins"}
REMOTE_LOG_ROOT=${REMOTE_LOG_ROOT:-"${REMOTE_ROOT}/log"}

RUN_ID=${RUN_ID:-$(date +%Y%m%d-%H%M%S)}

BUILD_KERNEL=1
BUILD_FIRECRACKER=1
INSTALL_CONFIGS=1
SYNC_TO_REMOTE=1
RUN_REMOTE=1
FETCH_LOGS=1
CLEAN_REMOTE_PROCS=1
SYNC_ROOTFS=0
IOCTL_SMOKE=0
IOCTL_SMOKE_MODE=basic
GLES_COMPUTE_SMOKE=0
GLES_SMOKE_ARGS=${GLES_SMOKE_ARGS:-"--count 64"}
GLES_CLIENT_BO_MMAP_CACHED=${GLES_CLIENT_BO_MMAP_CACHED:-0}

usage() {
	cat <<EOF
Usage: $(basename "$0") [options]

Build, sync, run the vmshm Firecracker test, collect logs, and generate result.

Options:
  --skip-kernel-build        Do not run scripts/build/build-guest-vmshm-kernels.sh
  --skip-firecracker-build   Do not run scripts/build/build-firecracker-runtime.sh
  --skip-build               Skip both kernel and Firecracker/broker builds
  --skip-config-install      Do not regenerate SFTP vmshm irq configs
  --skip-sync                Do not rsync GPU-SFTP to the remote host
  --skip-remote-run          Do not start broker/proxy/client on the remote host
  --skip-fetch-logs          Do not rsync this run's logs back from the remote host
  --no-clean-remote-procs    Do not pkill existing firecracker/vmshm-broker first
  --sync-rootfs              Include base rootfs images in local-to-remote
                             rsync. Normal runs reuse remote base rootfs
                             images and inject the current test payload by
                             loop-mounting the image before VM launch.
  --ioctl-smoke              Run userspace /dev/dri/card0 VERSION/GET_CAP/DEV_QUERY smoke
  --vm-create-smoke          Run ioctl smoke plus PANTHOR_VM_CREATE/VM_DESTROY
  --bo-create-smoke          Run ioctl smoke plus PANTHOR_BO_CREATE/GEM_CLOSE
  --bo-lifecycle-smoke       Run ioctl smoke plus multi-BO lifecycle/close cleanup stress
  --bo-mmap-smoke            Run ioctl smoke plus BO_MMAP_OFFSET/client mmap read-write
  --vm-bind-smoke            Run ioctl smoke plus synchronous PANTHOR_VM_BIND MAP/UNMAP
  --vm-bind-async-sync-smoke Run ioctl smoke plus async VM_BIND sync arrays/SYNC_ONLY
  --vm-state-flush-smoke     Run ioctl smoke plus VM_GET_STATE and flush-id mmap
  --syncobj-lifecycle-smoke  Run ioctl smoke plus SYNCOBJ_CREATE/DESTROY lifecycle
  --syncobj-wait-smoke       Run ioctl smoke plus SYNCOBJ_WAIT poll semantics
  --syncobj-transfer-smoke   Run ioctl smoke plus SYNCOBJ_TRANSFER binary path
  --syncobj-timeline-wait-smoke
                             Run ioctl smoke plus SYNCOBJ_TIMELINE_WAIT points path
  --syncobj-signal-query-smoke
                             Run ioctl smoke plus SYNCOBJ_SIGNAL/RESET/QUERY paths
  --group-lifecycle-smoke    Run ioctl smoke plus GROUP_CREATE/GET_STATE/DESTROY
  --group-submit-syncpoint-smoke
                             Run ioctl smoke plus zero-length GROUP_SUBMIT syncpoint
  --tiler-heap-lifecycle-smoke
                             Run ioctl smoke plus TILER_HEAP_CREATE/DESTROY
  --gles-compute-smoke       Boot the shared client with the base Panfrost
                             rootfs after injecting the GLES compute payload
                             and run
                             /root/gpu-smoke.sh correctness smoke
  --gles-smoke-args ARGS     Arguments passed to /root/gpu-smoke.sh in GLES mode
  --gles-client-bo-mmap-cached
                             In GLES mode, boot the shared client with
                             panthor_client.bo_mmap_cached=1 so BO payload
                             mmap uses cached WB instead of write-combine.
  --run-id ID                Use a fixed run log directory name
  -h, --help                 Show this help

Environment overrides:
  SFTP_ROOT SFTP_BINS SFTP_LOG_ROOT
  BUILD_GUEST_VMSHM_KERNELS BUILD_FIRECRACKER_RUNTIME BUILD_PANTHOR_IOCTL_SMOKE
  REMOTE_HOST REMOTE_USER REMOTE_PASS REMOTE_ROOT REMOTE_BINS REMOTE_LOG_ROOT RUN_ID

Default remote is ${REMOTE_USER}@${REMOTE_HOST}, logs go under:
  remote: ${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}
  local:  ${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--skip-kernel-build)
		BUILD_KERNEL=0
		;;
	--skip-firecracker-build)
		BUILD_FIRECRACKER=0
		;;
	--skip-build)
		BUILD_KERNEL=0
		BUILD_FIRECRACKER=0
		;;
	--skip-config-install)
		INSTALL_CONFIGS=0
		;;
	--skip-sync)
		SYNC_TO_REMOTE=0
		;;
	--skip-remote-run)
		RUN_REMOTE=0
		;;
	--skip-fetch-logs)
		FETCH_LOGS=0
		;;
	--no-clean-remote-procs)
		CLEAN_REMOTE_PROCS=0
		;;
	--sync-rootfs)
		SYNC_ROOTFS=1
		;;
	--ioctl-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=basic
		;;
	--vm-create-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=vm-create
		;;
	--bo-create-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=bo-create
		;;
	--bo-lifecycle-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=bo-lifecycle
		;;
	--bo-mmap-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=bo-mmap
		;;
	--vm-bind-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=vm-bind
		;;
	--vm-bind-async-sync-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=vm-bind-async-sync
		;;
	--vm-state-flush-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=vm-state-flush
		;;
	--syncobj-lifecycle-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=syncobj-lifecycle
		;;
	--syncobj-wait-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=syncobj-wait
		;;
	--syncobj-transfer-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=syncobj-transfer
		;;
	--syncobj-timeline-wait-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=syncobj-timeline-wait
		;;
	--syncobj-signal-query-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=syncobj-signal-query
		;;
	--group-lifecycle-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=group-lifecycle
		;;
	--group-submit-syncpoint-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=group-submit-syncpoint
		;;
	--tiler-heap-lifecycle-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=tiler-heap-lifecycle
		;;
	--gles-compute-smoke)
		IOCTL_SMOKE=0
		GLES_COMPUTE_SMOKE=1
		;;
	--gles-smoke-args)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-smoke-args requires an argument" >&2
			exit 2
		fi
		GLES_SMOKE_ARGS=$1
		;;
	--gles-client-bo-mmap-cached)
		GLES_CLIENT_BO_MMAP_CACHED=1
		;;
	--run-id)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--run-id requires an argument" >&2
			exit 2
		fi
		RUN_ID=$1
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "unknown option: $1" >&2
		usage >&2
		exit 2
		;;
	esac
	shift
done

log() {
	printf '\n==> %s\n' "$*"
}

die() {
	echo "error: $*" >&2
	exit 1
}

quote() {
	printf '%q' "$1"
}

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

with_ssh_password() {
	local tmpdir status

	tmpdir=$(mktemp -d /tmp/vmshm-ssh.XXXXXX)
	cat >"${tmpdir}/askpass" <<'EOF'
#!/bin/sh
printf '%s' "$VMSSH_PASSWORD"
EOF
	chmod 700 "${tmpdir}/askpass"

	set +e
	VMSSH_PASSWORD="${REMOTE_PASS}" \
	SSH_ASKPASS="${tmpdir}/askpass" \
	SSH_ASKPASS_REQUIRE=force \
	DISPLAY="${DISPLAY:-none}" \
	setsid -w "$@"
	status=$?
	set -e

	rm -rf "${tmpdir}"
	return "${status}"
}

ssh_remote() {
	with_ssh_password ssh \
		-oBatchMode=no \
		-oStrictHostKeyChecking=accept-new \
		"${REMOTE_USER}@${REMOTE_HOST}" \
		"$@"
}

rsync_remote() {
	with_ssh_password env \
		RSYNC_RSH="ssh -p 22 -oBatchMode=no -oStrictHostKeyChecking=accept-new" \
		rsync "$@"
}

# shellcheck source=scripts/lib/gpu_sftp_layout.sh
source "${ROOT_DIR}/scripts/lib/gpu_sftp_layout.sh"

build_kernels() {
	log "Building client/proxy arm64 kernels"
	"${BUILD_GUEST_VMSHM_KERNELS}"

	[[ -f "${SFTP_BINS}/kernels/shared/client/Image" ]] ||
		die "missing client Image: ${SFTP_BINS}/kernels/shared/client/Image"
	[[ -f "${SFTP_BINS}/kernels/shared/proxy/Image" ]] ||
		die "missing proxy Image: ${SFTP_BINS}/kernels/shared/proxy/Image"
}

build_firecracker() {
	log "Building Firecracker and vmshm-broker"
	"${BUILD_FIRECRACKER_RUNTIME}"

	[[ -x "${SFTP_BINS}/bin/firecracker" ]] ||
		die "missing firecracker binary: ${SFTP_BINS}/bin/firecracker"
	[[ -x "${SFTP_BINS}/bin/vmshm-broker" ]] ||
		die "missing vmshm-broker binary: ${SFTP_BINS}/bin/vmshm-broker"
}

build_ioctl_smoke() {
	if [[ "${IOCTL_SMOKE}" -eq 0 ]]; then
		return 0
	fi

	log "Building Panthor userspace ioctl smoke test"
	"${BUILD_PANTHOR_IOCTL_SMOKE}"

	[[ -x "${SFTP_BINS}/bin/panthor_ioctl_smoke" ]] ||
		die "missing ioctl smoke binary: ${SFTP_BINS}/bin/panthor_ioctl_smoke"
}

install_configs() {
	local installer="${SFTP_BINS}/scripts/shared/vmshm-1client/install-vmshm-irq-configs.sh"

	if [[ ! -x "${installer}" ]]; then
		log "Skipping config install; not executable: ${installer}"
		return 0
	fi

	log "Installing vmshm irq configs under SFTP"
	"${installer}"
}

sync_to_remote() {
	local excludes=(
		--exclude='.vscode/'
		--exclude='.git/'
		--exclude='node_modules/'
		--exclude='log/'
		--exclude='firecracker-bins/run-logs/'
		--exclude='linux-host-kernel/'
	)

	if [[ "${SYNC_ROOTFS}" -eq 0 ]]; then
		excludes+=(--exclude='firecracker-bins/rootfs/')
	fi

	log "Ensuring remote SFTP directory exists"
	ssh_remote "mkdir -p $(quote "${REMOTE_ROOT}")"

	log "Removing obsolete remote firecracker-bins/run-logs"
	ssh_remote "rm -rf $(quote "${REMOTE_BINS}/run-logs")"

	log "Syncing GPU-SFTP to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_ROOT}"
	rsync_remote -av --info=stats2,name1 \
		"${excludes[@]}" \
		"${SFTP_ROOT}/" \
		"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_ROOT}/"

	migrate_remote_gpu_sftp_layout
}

run_remote_test() {
	local run_id_q remote_root_q remote_bins_q remote_log_root_q clean_q
	local ioctl_smoke_q ioctl_smoke_mode_q
	local gles_compute_smoke_q gles_smoke_args_q
	local gles_client_bo_mmap_cached_q

	run_id_q=$(quote "${RUN_ID}")
	remote_root_q=$(quote "${REMOTE_ROOT}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	clean_q=$(quote "${CLEAN_REMOTE_PROCS}")
	ioctl_smoke_q=$(quote "${IOCTL_SMOKE}")
	ioctl_smoke_mode_q=$(quote "${IOCTL_SMOKE_MODE}")
	gles_compute_smoke_q=$(quote "${GLES_COMPUTE_SMOKE}")
	gles_smoke_args_q=$(quote "${GLES_SMOKE_ARGS}")
	gles_client_bo_mmap_cached_q=$(quote "${GLES_CLIENT_BO_MMAP_CACHED}")

	log "Running remote vmshm test: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BINS}"
	ssh_remote "RUN_ID=${run_id_q} REMOTE_ROOT=${remote_root_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} CLEAN_REMOTE_PROCS=${clean_q} IOCTL_SMOKE=${ioctl_smoke_q} IOCTL_SMOKE_MODE=${ioctl_smoke_mode_q} GLES_COMPUTE_SMOKE=${gles_compute_smoke_q} GLES_SMOKE_ARGS=${gles_smoke_args_q} GLES_CLIENT_BO_MMAP_CACHED=${gles_client_bo_mmap_cached_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_BINS}"
LOG_DIR="${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"
mkdir -p /run/vmshm "${LOG_DIR}"
SMOKE_CLIENT_CONFIG="${LOG_DIR}/client-ioctl-smoke-config.json"
GLES_CLIENT_CONFIG="${LOG_DIR}/client-gles-compute-config.json"
GLES_SMOKE_SRC_DIR="${REMOTE_ROOT}/tests/gpu-compute-smoke"
GLES_SMOKE_BIN="${REMOTE_BINS}/bin/gles-compute-smoke"
SMOKE_MNT=""
GLES_CLIENT_BO_MMAP_CACHED=${GLES_CLIENT_BO_MMAP_CACHED:-0}

if [[ "${CLEAN_REMOTE_PROCS}" == "1" ]]; then
	pkill -x firecracker 2>/dev/null || true
	pkill -x vmshm-broker 2>/dev/null || true
	sleep 1
fi
rm -f /run/vmshm/*.sock

cleanup_ioctl_smoke_rootfs() {
	if [[ -n "${SMOKE_MNT}" && -d "${SMOKE_MNT}" ]]; then
		umount "${SMOKE_MNT}" 2>/dev/null || true
		rmdir "${SMOKE_MNT}" 2>/dev/null || true
	fi
}
trap cleanup_ioctl_smoke_rootfs EXIT

wait_for_log() {
	local file="$1"
	local pattern="$2"
	local timeout="$3"
	local i=0

	while [[ "${i}" -lt "${timeout}" ]]; do
		if grep -qaE "${pattern}" "${file}" 2>/dev/null; then
			return 0
		fi
		i=$((i + 1))
		sleep 1
	done
	return 1
}

find_broker_task_pid() {
	local i=0 pid

	while [[ "${i}" -lt 20 ]]; do
		pid=$(pgrep -x vmshm-broker | head -n 1 || true)
		if [[ -n "${pid}" ]]; then
			printf '%s\n' "${pid}"
			return 0
		fi
		i=$((i + 1))
		sleep 0.1
	done
	return 1
}

snapshot_broker_proc() {
	local pid="$1"
	local out="$2"
	local stat rest utime stime total_ticks hz voluntary nonvoluntary migrations runtime_ns
	local task task_stat task_rest task_fields task_utime task_stime task_runtime _
	local fields=()

	if [[ -z "${pid}" || ! -r "/proc/${pid}/stat" ]]; then
		echo "missing=1" >"${out}"
		echo "pid=${pid}" >>"${out}"
		return 1
	fi

	hz=$(getconf CLK_TCK 2>/dev/null || echo 100)
	total_ticks=0
	voluntary=0
	nonvoluntary=0
	migrations=0
	runtime_ns=0

	for task in /proc/"${pid}"/task/*; do
		[[ -d "${task}" ]] || continue

		if [[ -r "${task}/stat" ]]; then
			task_stat=$(cat "${task}/stat" 2>/dev/null || echo "")
			task_rest="${task_stat##*) }"
			task_fields=()
			read -r -a task_fields <<<"${task_rest}"
			task_utime="${task_fields[11]:-0}"
			task_stime="${task_fields[12]:-0}"
			total_ticks=$((total_ticks + task_utime + task_stime))
		fi

		voluntary=$((voluntary + $(awk '/^voluntary_ctxt_switches:/ {print $2}' "${task}/status" 2>/dev/null || echo 0)))
		nonvoluntary=$((nonvoluntary + $(awk '/^nonvoluntary_ctxt_switches:/ {print $2}' "${task}/status" 2>/dev/null || echo 0)))
		migrations=$((migrations + $(awk -F: '/nr_migrations/ {gsub(/[ \t]/, "", $2); print $2; exit}' "${task}/sched" 2>/dev/null || echo 0)))

		if [[ -r "${task}/schedstat" ]]; then
			read -r task_runtime _ <<<"$(cat "${task}/schedstat" 2>/dev/null || echo 0)"
			runtime_ns=$((runtime_ns + ${task_runtime:-0}))
		fi
	done

	{
		echo "missing=0"
		echo "pid=${pid}"
		echo "hz=${hz}"
		echo "task_clock_ticks=${total_ticks}"
		echo "sched_runtime_ns=${runtime_ns:-0}"
		echo "voluntary_context_switches=${voluntary:-0}"
		echo "nonvoluntary_context_switches=${nonvoluntary:-0}"
		echo "cpu_migrations=${migrations:-0}"
	} >"${out}"
}

proc_value() {
	local key="$1"
	local file="$2"

	awk -F= -v key="${key}" '$1 == key {print $2; exit}' "${file}" 2>/dev/null
}

gles_smoke_args_tokens() {
	local -a argv
	local arg

	read -r -a argv <<<"${GLES_SMOKE_ARGS}"
	for arg in "${argv[@]}"; do
		if [[ "${arg}" == *:* || "${arg}" == *[[:space:]]* || "${arg}" == *\"* || "${arg}" == *\\* ]]; then
			echo "unsupported GLES smoke arg for kernel cmdline token transport: ${arg}" >&2
			return 1
		fi
	done

	(IFS=:; printf '%s' "${argv[*]}")
}

stop_pid_file() {
	local pid_file="$1"
	local pid

	[[ -f "${pid_file}" ]] || return 0
	pid=$(cat "${pid_file}" 2>/dev/null || true)
	[[ -n "${pid}" ]] || return 0

	kill -INT "${pid}" 2>/dev/null || true
	sleep 0.2
	if kill -0 "${pid}" 2>/dev/null; then
		kill -TERM "${pid}" 2>/dev/null || true
	fi
	sleep 0.5
	if kill -0 "${pid}" 2>/dev/null; then
		kill -KILL "${pid}" 2>/dev/null || true
	fi
}

write_broker_proc_delta() {
	local start="$1"
	local end="$2"
	local out="$3"
	local hz runtime_start runtime_end ticks_start ticks_end
	local voluntary_start voluntary_end nonvoluntary_start nonvoluntary_end
	local migrations_start migrations_end runtime_delta ticks_delta
	local voluntary_delta nonvoluntary_delta switch_delta migration_delta task_clock_ms

	if [[ ! -f "${start}" || ! -f "${end}" ]] ||
	   [[ "$(proc_value missing "${start}")" != "0" ]] ||
	   [[ "$(proc_value missing "${end}")" != "0" ]]; then
		echo "procfs fallback unavailable" >"${out}"
		return 0
	fi

	hz=$(proc_value hz "${end}")
	runtime_start=$(proc_value sched_runtime_ns "${start}")
	runtime_end=$(proc_value sched_runtime_ns "${end}")
	ticks_start=$(proc_value task_clock_ticks "${start}")
	ticks_end=$(proc_value task_clock_ticks "${end}")
	voluntary_start=$(proc_value voluntary_context_switches "${start}")
	voluntary_end=$(proc_value voluntary_context_switches "${end}")
	nonvoluntary_start=$(proc_value nonvoluntary_context_switches "${start}")
	nonvoluntary_end=$(proc_value nonvoluntary_context_switches "${end}")
	migrations_start=$(proc_value cpu_migrations "${start}")
	migrations_end=$(proc_value cpu_migrations "${end}")

	runtime_delta=$((runtime_end - runtime_start))
	ticks_delta=$((ticks_end - ticks_start))
	voluntary_delta=$((voluntary_end - voluntary_start))
	nonvoluntary_delta=$((nonvoluntary_end - nonvoluntary_start))
	switch_delta=$((voluntary_delta + nonvoluntary_delta))
	migration_delta=$((migrations_end - migrations_start))

	if [[ "${runtime_delta}" -gt 0 ]]; then
		task_clock_ms=$(awk -v ns="${runtime_delta}" 'BEGIN { printf "%.3f", ns / 1000000.0 }')
	else
		task_clock_ms=$(awk -v ticks="${ticks_delta}" -v hz="${hz:-100}" 'BEGIN { printf "%.3f", ticks * 1000.0 / hz }')
	fi

	{
		echo "procfs fallback for broker task; remote perf command was unavailable"
		echo "task-clock-ms-approx ${task_clock_ms}"
		echo "context-switches ${switch_delta}"
		echo "voluntary-context-switches ${voluntary_delta}"
		echo "nonvoluntary-context-switches ${nonvoluntary_delta}"
		echo "cpu-migrations ${migration_delta}"
	} >"${out}"
}

ioctl_smoke_mode_label() {
	printf '%s' "${IOCTL_SMOKE_MODE}" | tr -c 'A-Za-z0-9._-' '_'
}

write_ioctl_smoke_init_script() {
	cat <<'INIT_SCRIPT'
#!/bin/sh
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /dev/dri /proc /sys
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true

echo "PANTHOR_IOCTL_INIT=start"
i=0
while [ "${i}" -lt 60 ]; do
	if [ -e /dev/dri/card0 ] || [ -e /dev/dri/renderD128 ]; then
		break
	fi
	i=$((i + 1))
	sleep 1
done

ls -l /dev/dri /dev/dri/* 2>&1 || true
mode="$(cat /panthor_ioctl_smoke_mode 2>/dev/null || echo basic)"
for word in $(cat /proc/cmdline 2>/dev/null); do
	case "${word}" in
	panthor_ioctl_smoke_mode=*)
		mode="${word#*=}"
		break
		;;
	esac
done
case "${mode}" in
	vm-create)
		smoke_arg="--vm-create"
		;;
	bo-create)
		smoke_arg="--bo-create"
		;;
	bo-lifecycle)
		smoke_arg="--bo-lifecycle"
		;;
	bo-mmap)
		smoke_arg="--bo-mmap"
		;;
	vm-bind)
		smoke_arg="--vm-bind"
		;;
	vm-bind-async-sync)
		smoke_arg="--vm-bind-async-sync"
		;;
	vm-state-flush)
		smoke_arg="--vm-state-flush"
		;;
	syncobj-lifecycle)
		smoke_arg="--syncobj-lifecycle"
		;;
	syncobj-wait)
		smoke_arg="--syncobj-wait"
		;;
	syncobj-transfer)
		smoke_arg="--syncobj-transfer"
		;;
	syncobj-timeline-wait)
		smoke_arg="--syncobj-timeline-wait"
		;;
	syncobj-signal-query)
		smoke_arg="--syncobj-signal-query"
		;;
	group-lifecycle)
		smoke_arg="--group-lifecycle"
		;;
	group-submit-syncpoint)
		smoke_arg="--group-submit-syncpoint"
		;;
	tiler-heap-lifecycle)
		smoke_arg="--tiler-heap-lifecycle"
		;;
	*)
		smoke_arg="--basic"
		;;
esac

if /panthor_ioctl_smoke "${smoke_arg}" /dev/dri/card0; then
	echo "PANTHOR_IOCTL_INIT=PASS"
elif /panthor_ioctl_smoke "${smoke_arg}" /dev/dri/renderD128; then
	echo "PANTHOR_IOCTL_INIT=PASS"
else
	status=$?
	echo "PANTHOR_IOCTL_INIT=FAIL status=${status}"
fi

sync
sleep 2
poweroff -f 2>/dev/null || reboot -f 2>/dev/null || while true; do sleep 60; done
INIT_SCRIPT
}

prune_rootfs_base_layout() {
	echo "rootfs_base_layout_prune_start root=${REMOTE_BINS}/rootfs ts=$(date -Is)" >&2
	find ./rootfs -mindepth 1 -maxdepth 1 -type d \
		! -name mounts \
		! -name work \
		-exec rm -rf {} +
	find ./rootfs -mindepth 1 -maxdepth 1 \( -type f -o -type l \) \
		! -name rootfs.ext2 \
		! -name rootfs-panfrost.ext4 \
		! -name .gitkeep \
		-exec rm -f {} +
	echo "rootfs_base_layout_prune_done root=${REMOTE_BINS}/rootfs ts=$(date -Is)" >&2
}

inject_ioctl_smoke_payload() {
	local rootfs_path="${REMOTE_BINS}/rootfs/rootfs.ext2"

	[[ -x ./bin/panthor_ioctl_smoke ]] ||
		{ echo "missing executable ./bin/panthor_ioctl_smoke" >&2; return 1; }
	[[ -f "${rootfs_path}" ]] ||
		{ echo "missing ${rootfs_path} on remote" >&2; return 1; }

	echo "rootfs_payload_inject_start payload=panthor-ioctl-smoke rootfs=${rootfs_path} ts=$(date -Is)" >&2
	SMOKE_MNT=$(mktemp -d /tmp/panthor-ioctl-rootfs.XXXXXX)
	mount -o loop,rw "${rootfs_path}" "${SMOKE_MNT}"
	install -Dm0755 ./bin/panthor_ioctl_smoke "${SMOKE_MNT}/panthor_ioctl_smoke"
	write_ioctl_smoke_init_script >"${SMOKE_MNT}/panthor_ioctl_smoke_init"
	chmod 0755 "${SMOKE_MNT}/panthor_ioctl_smoke_init"
	sync -f "${SMOKE_MNT}" 2>/dev/null || sync
	umount "${SMOKE_MNT}"
	rmdir "${SMOKE_MNT}"
	SMOKE_MNT=""
	echo "rootfs_payload_inject_done payload=panthor-ioctl-smoke rootfs=${rootfs_path} ts=$(date -Is)" >&2
	printf '%s\n' "${rootfs_path}"
}

prepare_ioctl_smoke_client() {
	local rootfs_path mode_arg

	rootfs_path=$(inject_ioctl_smoke_payload)
	echo "ioctl_rootfs=${rootfs_path}" >&2
	[[ -f "${rootfs_path}" ]] ||
		{ echo "missing IOCTL smoke rootfs ${rootfs_path}" >&2; return 1; }
	mode_arg="$(ioctl_smoke_mode_label)"

	cat >"${SMOKE_CLIENT_CONFIG}" <<EOF
{
  "boot-source": {
    "kernel_image_path": "${REMOTE_BINS}/kernels/shared/client/Image",
    "boot_args": "console=ttyS0 root=/dev/vda ro rootfstype=ext4 init=/panthor_ioctl_smoke_init panthor_ioctl_smoke_mode=${mode_arg}"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "${rootfs_path}",
      "is_root_device": false,
      "is_read_only": true
    }
  ],
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 512,
    "cpu_template": null,
    "gpu_passthrough": false,
    "dump_fdt_path": "${REMOTE_ROOT}/artifacts/dtb/client-ioctl-smoke-${RUN_ID}.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-client",
      "role": "client",
      "guest_phys_addr": "0x30000000",
      "slot": 1,
      "expected_size": 134217728,
      "fdt_node_name": "client-vmshm-manager",
      "fdt_compatible": "client-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm.sock",
      "name": "vmshm-comm-client",
      "role": "client",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "client_comm_vmshm",
      "fdt_compatible": "client_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f000000",
        "doorbell_size": "0x1000",
        "irq": 80
      }
    }
  ]
}
EOF
}

build_gles_compute_smoke() {
	if [[ "${GLES_COMPUTE_SMOKE}" != "1" ]]; then
		return 0
	fi

	echo "building current gles-compute-smoke from ${GLES_SMOKE_SRC_DIR}" >&2
	[[ -f "${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" >&2; return 1; }
	command -v cc >/dev/null 2>&1 ||
		{ echo "missing cc on remote host" >&2; return 1; }
	command -v pkg-config >/dev/null 2>&1 ||
		{ echo "missing pkg-config on remote host" >&2; return 1; }

	mkdir -p "$(dirname "${GLES_SMOKE_BIN}")"
	cc -O2 -Wall -Wextra -std=c11 \
		"${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" \
		-o "${GLES_SMOKE_BIN}" \
		$(pkg-config --cflags --libs egl glesv2 gbm)
	chmod 0755 "${GLES_SMOKE_BIN}"
	"${GLES_SMOKE_BIN}" --help >/dev/null 2>&1
	echo "installed ${GLES_SMOKE_BIN}" >&2
}

inject_gles_compute_payload() {
	local rootfs_path="${REMOTE_BINS}/rootfs/rootfs-panfrost.ext4"

	[[ -f "${rootfs_path}" ]] ||
		{ echo "missing ${rootfs_path} on remote" >&2; return 1; }
	[[ -f "${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" >&2; return 1; }
	[[ -f "${GLES_SMOKE_SRC_DIR}/gpu-smoke.sh" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/gpu-smoke.sh" >&2; return 1; }
	[[ -f "${GLES_SMOKE_SRC_DIR}/init" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/init" >&2; return 1; }

	build_gles_compute_smoke
	echo "rootfs_payload_inject_start payload=gles-compute rootfs=${rootfs_path} ts=$(date -Is)" >&2
	SMOKE_MNT=$(mktemp -d /tmp/panthor-gles-rootfs.XXXXXX)
	mount -o loop,rw "${rootfs_path}" "${SMOKE_MNT}"

	install -Dm0755 "${GLES_SMOKE_BIN}" "${SMOKE_MNT}/root/gles-compute-smoke"
	install -Dm0755 "${GLES_SMOKE_SRC_DIR}/gpu-smoke.sh" "${SMOKE_MNT}/root/gpu-smoke.sh"
	install -Dm0755 "${GLES_SMOKE_SRC_DIR}/init" "${SMOKE_MNT}/init"

	cat >"${SMOKE_MNT}/root/gpu-smoke.env" <<EOF
GPU_SMOKE_AFTER_RUN=shell
EOF
	sync -f "${SMOKE_MNT}" 2>/dev/null || sync
	umount "${SMOKE_MNT}"
	rmdir "${SMOKE_MNT}"
	SMOKE_MNT=""
	echo "rootfs_payload_inject_done payload=gles-compute rootfs=${rootfs_path} ts=$(date -Is)" >&2
	printf '%s\n' "${rootfs_path}"
}

prepare_gles_compute_client() {
	local rootfs_path smoke_arg_tokens
	local client_mmap_args=""

	rootfs_path=$(inject_gles_compute_payload)
	echo "gles_rootfs=${rootfs_path}" >&2
	[[ -f "${rootfs_path}" ]] ||
		{ echo "missing GLES rootfs ${rootfs_path}" >&2; return 1; }
	smoke_arg_tokens=$(gles_smoke_args_tokens)
	if [[ "${GLES_CLIENT_BO_MMAP_CACHED}" == "1" ]]; then
		client_mmap_args=" panthor_client.bo_mmap_cached=1"
	fi

	cat >"${GLES_CLIENT_CONFIG}" <<EOF
{
  "boot-source": {
    "kernel_image_path": "${REMOTE_BINS}/kernels/shared/client/Image",
    "boot_args": "console=ttyS0 root=/dev/vda ro rootfstype=ext4 init=/init panic=-1 print-fatal-signals=1 gpu_smoke_args_tokens=${smoke_arg_tokens} gpu_smoke_quiet_console=1 gpu_smoke_after_run=shell${client_mmap_args}"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "${rootfs_path}",
      "is_root_device": false,
      "is_read_only": true
    }
  ],
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 512,
    "cpu_template": null,
    "gpu_passthrough": false,
    "dump_fdt_path": "${REMOTE_ROOT}/artifacts/dtb/client-gles-compute-${RUN_ID}.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-client",
      "role": "client",
      "guest_phys_addr": "0x30000000",
      "slot": 1,
      "expected_size": 134217728,
      "fdt_node_name": "client-vmshm-manager",
      "fdt_compatible": "client-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm.sock",
      "name": "vmshm-comm-client",
      "role": "client",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "client_comm_vmshm",
      "fdt_compatible": "client_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f000000",
        "doorbell_size": "0x1000",
        "irq": 80
      }
    }
  ]
	}
EOF
}

prune_rootfs_base_layout >"${LOG_DIR}/rootfs-base-layout-prune.log" 2>&1
if [[ "${IOCTL_SMOKE}" == "1" ]]; then
	prepare_ioctl_smoke_client >"${LOG_DIR}/ioctl-smoke-rootfs.log" 2>&1
elif [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	prepare_gles_compute_client >"${LOG_DIR}/gles-compute-rootfs.log" 2>&1
fi

if command -v perf >/dev/null 2>&1; then
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
			perf stat \
				-e task-clock,context-switches,cpu-migrations \
				-o "${LOG_DIR}/broker.perf" \
				-- sh ./scripts/shared/vmshm-1client/broker-run.sh \
				< /dev/null >"${LOG_DIR}/broker.log" 2>&1 &
	echo $! >"${LOG_DIR}/broker.pid"
	echo "perf stat enabled for vmshm-broker" >"${LOG_DIR}/broker.perf.status"
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/broker-run.sh \
		< /dev/null >"${LOG_DIR}/broker.log" 2>&1 &
	echo $! >"${LOG_DIR}/broker.pid"
	echo "perf command not found on remote host" >"${LOG_DIR}/broker.perf.status"
fi

wait_for_log "${LOG_DIR}/broker.log" "listening|socket|broker" 10 || true
if broker_task_pid=$(find_broker_task_pid); then
	echo "${broker_task_pid}" >"${LOG_DIR}/broker.task.pid"
	if [[ ! -f "${LOG_DIR}/broker.perf" ]]; then
		snapshot_broker_proc "${broker_task_pid}" "${LOG_DIR}/broker.proc.start" || true
	fi
fi

NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/vm-proxy-test.sh \
	< /dev/null >"${LOG_DIR}/proxy.log" 2>&1 &
echo $! >"${LOG_DIR}/proxy.pid"

wait_for_log \
	"${LOG_DIR}/proxy.log" \
	"panthor-proxy: vmshm handler registered" \
	60 || true

if [[ "${IOCTL_SMOKE}" == "1" ]]; then
		NO_COLOR=1 RUST_LOG_STYLE=never nohup \
			./bin/firecracker --no-api --no-seccomp --config-file "${SMOKE_CLIENT_CONFIG}" \
			< /dev/null >"${LOG_DIR}/client.log" 2>&1 &
elif [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		NO_COLOR=1 RUST_LOG_STYLE=never nohup \
			./bin/firecracker --no-api --no-seccomp --config-file "${GLES_CLIENT_CONFIG}" \
			< /dev/null >"${LOG_DIR}/client.log" 2>&1 &
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/vm-client-test.sh \
		< /dev/null >"${LOG_DIR}/client.log" 2>&1 &
fi
echo $! >"${LOG_DIR}/client.pid"

if [[ "${IOCTL_SMOKE}" == "1" ]]; then
	wait_for_log "${LOG_DIR}/client.log" "PANTHOR_IOCTL_SMOKE=(BASIC_PASS|VM_CREATE_PASS|BO_CREATE_PASS|BO_LIFECYCLE_PASS|BO_MMAP_PASS|VM_BIND_PASS|VM_BIND_ASYNC_SYNC_PASS|VM_STATE_FLUSH_PASS|SYNCOBJ_LIFECYCLE_PASS|SYNCOBJ_WAIT_PASS|SYNCOBJ_TRANSFER_PASS|SYNCOBJ_TIMELINE_WAIT_PASS|SYNCOBJ_SIGNAL_QUERY_PASS|GROUP_LIFECYCLE_PASS|GROUP_SUBMIT_SYNCPOINT_PASS|TILER_HEAP_LIFECYCLE_PASS)|PANTHOR_IOCTL_INIT=FAIL|Kernel panic|Guest-boot failed" 80 || true
elif [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	wait_for_log "${LOG_DIR}/client.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|COMPUTE_CHECK=PASS|Kernel panic|Guest-boot failed|Oops|job timeout|mismatch|software renderer detected" 180 || true
else
	wait_for_log "${LOG_DIR}/client.log" "panthor-client: registered DRM frontend" 60 || true
fi

if [[ ! -f "${LOG_DIR}/broker.perf" && -f "${LOG_DIR}/broker.task.pid" ]]; then
	snapshot_broker_proc "$(cat "${LOG_DIR}/broker.task.pid")" "${LOG_DIR}/broker.proc.end" || true
	write_broker_proc_delta \
		"${LOG_DIR}/broker.proc.start" \
		"${LOG_DIR}/broker.proc.end" \
		"${LOG_DIR}/broker.perf" || true
fi

for pid_file in client.pid proxy.pid broker.pid broker.task.pid; do
	stop_pid_file "${LOG_DIR}/${pid_file}"
done
sleep 1

ioctl_mode_marker_ok() {
	case "${IOCTL_SMOKE_MODE}" in
	basic)
		grep -qa "PANTHOR_IOCTL_SMOKE=BASIC_PASS" "${LOG_DIR}/client.log"
		;;
	vm-create)
		grep -qa "PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS" "${LOG_DIR}/client.log"
		;;
	bo-create)
		grep -qa "PANTHOR_IOCTL_SMOKE=BO_CREATE_PASS" "${LOG_DIR}/client.log"
		;;
	bo-lifecycle)
		grep -qa "PANTHOR_IOCTL_SMOKE=BO_LIFECYCLE_PASS" "${LOG_DIR}/client.log"
		;;
	bo-mmap)
		grep -qa "PANTHOR_IOCTL_SMOKE=BO_MMAP_PASS" "${LOG_DIR}/client.log"
		;;
	vm-bind)
		grep -qa "PANTHOR_IOCTL_SMOKE=VM_BIND_PASS" "${LOG_DIR}/client.log"
		;;
	vm-bind-async-sync)
		grep -qa "PANTHOR_IOCTL_SMOKE=VM_BIND_ASYNC_SYNC_PASS" "${LOG_DIR}/client.log"
		;;
	vm-state-flush)
		grep -qa "PANTHOR_IOCTL_SMOKE=VM_STATE_FLUSH_PASS" "${LOG_DIR}/client.log"
		;;
	syncobj-lifecycle)
		grep -qa "PANTHOR_IOCTL_SMOKE=SYNCOBJ_LIFECYCLE_PASS" "${LOG_DIR}/client.log"
		;;
	syncobj-wait)
		grep -qa "PANTHOR_IOCTL_SMOKE=SYNCOBJ_WAIT_PASS" "${LOG_DIR}/client.log"
		;;
	syncobj-transfer)
		grep -qa "PANTHOR_IOCTL_SMOKE=SYNCOBJ_TRANSFER_PASS" "${LOG_DIR}/client.log"
		;;
	syncobj-timeline-wait)
		grep -qa "PANTHOR_IOCTL_SMOKE=SYNCOBJ_TIMELINE_WAIT_PASS" "${LOG_DIR}/client.log"
		;;
	syncobj-signal-query)
		grep -qa "PANTHOR_IOCTL_SMOKE=SYNCOBJ_SIGNAL_QUERY_PASS" "${LOG_DIR}/client.log"
		;;
	group-lifecycle)
		grep -qa "PANTHOR_IOCTL_SMOKE=GROUP_LIFECYCLE_PASS" "${LOG_DIR}/client.log"
		;;
	group-submit-syncpoint)
		grep -qa "PANTHOR_IOCTL_SMOKE=GROUP_SUBMIT_SYNCPOINT_PASS" "${LOG_DIR}/client.log"
		;;
	tiler-heap-lifecycle)
		grep -qa "PANTHOR_IOCTL_SMOKE=TILER_HEAP_LIFECYCLE_PASS" "${LOG_DIR}/client.log"
		;;
	*)
		return 1
		;;
	esac
}

ioctl_common_markers_ok() {
	grep -qa "VERSION name=panthor" "${LOG_DIR}/client.log" || return 1
	grep -qa "GET_CAP DRM_CAP_SYNCOBJ=1" "${LOG_DIR}/client.log" || return 1
	grep -qa "GET_CAP DRM_CAP_SYNCOBJ_TIMELINE=1" "${LOG_DIR}/client.log" || return 1
	grep -qa "GPU_INFO" "${LOG_DIR}/client.log" || return 1
	grep -qa "CSIF_INFO" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: OPEN_SESSION session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: DEV_QUERY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: CLOSE_SESSION session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: OPEN_SESSION session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: DEV_QUERY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: CLOSE_SESSION session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_vm_create_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "vm-create" ]] && return 0

	grep -qa "PANTHOR_VM_CREATE_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_bo_create_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "bo-create" ]] && return 0

	grep -qa "PANTHOR_BO_CREATE_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_bo_lifecycle_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "bo-lifecycle" ]] && return 0

	grep -qa "PANTHOR_BO_LIFECYCLE_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "GEM_CLOSE_DOUBLE .*expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "GEM_CLOSE_INVALID .*expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SESSION_RELEASE session=[1-9][0-9]* leftover_bos=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_bo_mmap_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "bo-mmap" ]] && return 0

	grep -qa "PANTHOR_BO_MMAP_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "BO_MMAP_OFFSET handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "BO_MMAP_RW handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "BO_MMAP_OFFSET_NO_MMAP .*expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_MMAP_OFFSET session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: MMAP session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor: BO_CREATE vmshm-backed handle=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_vm_bind_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "vm-bind" ]] && return 0

	grep -qa "PANTHOR_VM_BIND_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_MAP vm=" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_UNMAP vm=" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_BIND session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_BIND session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: VM_BIND session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-client: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor: BO_CREATE vmshm-backed handle=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor: VM_BIND vmshm payload mapped iova=0x[0-9a-f]+ size=0x[0-9a-f]+ spans=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_vm_bind_async_sync_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "vm-bind-async-sync" ]] && return 0

	grep -qa "PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_ASYNC_MAP vm=" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_ASYNC_SYNC_ONLY vm=" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_ASYNC_UNMAP vm=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_AFTER_VM_BIND_MAP handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_AFTER_VM_BIND_SYNC_ONLY handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_AFTER_VM_BIND_UNMAP handle=" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_BIND session=[1-9][0-9]*.*syncs=1.*flags=0x1" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_BIND session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor: VM_BIND vmshm payload mapped iova=0x[0-9a-f]+ size=0x[0-9a-f]+ spans=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_vm_state_flush_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "vm-state-flush" ]] && return 0

	grep -qa "PANTHOR_VM_STATE_FLUSH_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_GET_STATE vm=" "${LOG_DIR}/client.log" || return 1
	grep -qa "MMAP_FLUSH_ID offset=" "${LOG_DIR}/client.log" || return 1
	grep -qa "MUNMAP_FLUSH_ID" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_GET_STATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: MMAP_FLUSH_ID offset=" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_GET_STATE session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-client: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_syncobj_lifecycle_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "syncobj-lifecycle" ]] && return 0

	grep -qa "PANTHOR_SYNCOBJ_LIFECYCLE_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_CREATE\\[0\\] handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_CREATE\\[1\\] handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_DESTROY\\[0\\] handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_DESTROY_DOUBLE .*expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_DESTROY\\[1\\] handle=" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_CREATE session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_syncobj_wait_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "syncobj-wait" ]] && return 0

	grep -qa "PANTHOR_SYNCOBJ_WAIT_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT\\[0\\] count=1" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_ALL count=2" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_UNSIGNALED_POLL expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_INVALID expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_WAIT session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_WAIT session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_WAIT session=[1-9][0-9]*.*ret=-" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_syncobj_transfer_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "syncobj-transfer" ]] && return 0

	grep -qa "PANTHOR_SYNCOBJ_TRANSFER_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TRANSFER_BINARY src=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_TRANSFER_DST handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TRANSFER_INVALID_SRC expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_TRANSFER session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_WAIT session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_TRANSFER session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_syncobj_timeline_wait_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "syncobj-timeline-wait" ]] && return 0

	grep -qa "PANTHOR_SYNCOBJ_TIMELINE_WAIT_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TRANSFER_TIMELINE\\[0\\] src=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TRANSFER_TIMELINE\\[1\\] src=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT\\[0\\] handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT_ALL count=2" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT_AVAILABLE\\[0\\] handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT_AVAILABLE_EMPTY expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT_MISSING_POINT expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT_INVALID expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_TIMELINE_WAIT session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_TRANSFER session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=[1-9][0-9]*.*ret=-" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_TRANSFER session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_syncobj_signal_query_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "syncobj-signal-query" ]] && return 0

	grep -qa "PANTHOR_SYNCOBJ_SIGNAL_QUERY_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_SIGNAL_BINARY handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_AFTER_SIGNAL handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_RESET_BINARY handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_AFTER_RESET expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_SIGNAL_INVALID expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_SIGNAL count=2" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_TIMELINE_WAIT_AFTER_SIGNAL count=2" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_QUERY count=2 point0=5 point1=9" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_QUERY_LAST_SUBMITTED count=2 point0=5 point1=9" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_QUERY_INVALID expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_SIGNAL session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_RESET session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_TIMELINE_SIGNAL session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_QUERY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_SIGNAL session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_RESET session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_TIMELINE_SIGNAL session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_QUERY session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	return 0
}

ioctl_group_lifecycle_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "group-lifecycle" ]] && return 0

	grep -qa "PANTHOR_GROUP_LIFECYCLE_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "GROUP_CREATE handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "GROUP_GET_STATE handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "GROUP_DESTROY handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "GROUP_DESTROY_DOUBLE .*expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_GET_STATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: GROUP_CREATE session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: GROUP_GET_STATE session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: GROUP_DESTROY session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_group_submit_syncpoint_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "group-submit-syncpoint" ]] && return 0

	grep -qa "PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "GROUP_SUBMIT_SYNCPOINT group=" "${LOG_DIR}/client.log" || return 1
	grep -qa "SYNCOBJ_WAIT_AFTER_GROUP_SUBMIT handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "GROUP_GET_STATE_AFTER_SUBMIT handle=" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_SUBMIT session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: SYNCOBJ_WAIT session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_GET_STATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: GROUP_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: GROUP_CREATE session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: GROUP_SUBMIT session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: SYNCOBJ_WAIT session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: GROUP_GET_STATE session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: GROUP_DESTROY session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_tiler_heap_lifecycle_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "tiler-heap-lifecycle" ]] && return 0

	grep -qa "PANTHOR_TILER_HEAP_LIFECYCLE_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "TILER_HEAP_CREATE handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "TILER_HEAP_DESTROY handle=" "${LOG_DIR}/client.log" || return 1
	grep -qa "TILER_HEAP_DESTROY_DOUBLE .*expected_failure" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: TILER_HEAP_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: TILER_HEAP_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: TILER_HEAP_CREATE session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: TILER_HEAP_DESTROY session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
}

gles_metric_markers_ok() {
	if [[ "${GLES_SMOKE_ARGS}" == *"--exclude-cpu-prepare"* ]]; then
		grep -qa "PERF_CPU_PREPARE_EXCLUDED=1" "${LOG_DIR}/client.log" || return 1
	fi
	return 0
}

{
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		echo "Panthor shared GLES compute smoke result"
	elif [[ "${IOCTL_SMOKE}" == "1" ]]; then
		echo "Panthor DRM open/session/version/cap/devquery vmshm test result"
	else
		echo "DRM_PANTHOR_DEV_QUERY vmshm test result"
	fi
	echo "Run ID: ${RUN_ID}"
	echo "Timestamp: $(date -Is)"
	echo "Remote log dir: ${LOG_DIR}"
	echo "IOCTL smoke: ${IOCTL_SMOKE}"
	echo "IOCTL smoke mode: ${IOCTL_SMOKE_MODE}"
	echo "GLES compute smoke: ${GLES_COMPUTE_SMOKE}"
	echo "GLES smoke args: ${GLES_SMOKE_ARGS}"
	echo
	echo "== Broker notify relay =="
	grep -aE "vmshm notify relay started|vmshm notify direct eventfd|sent vmshm memfd|registered vmshm notify" \
		"${LOG_DIR}/broker.log" | tail -n 40 || true
	echo
	echo "== Broker perf stat =="
	cat "${LOG_DIR}/broker.perf.status" 2>/dev/null || true
	sed -n '1,80p' "${LOG_DIR}/broker.perf" 2>/dev/null || true
	echo
	echo "== Proxy vmshm/panthor =="
	grep -aE "registered vmshm notify|proxy_comm_vmshm .*irq notify enabled|proxy_comm_vmshm: selftest passed|proxy_comm_vmshm: perf|panthor-proxy: vmshm handler registered" \
		"${LOG_DIR}/proxy.log" || true
	grep -aE "panthor: BO_CREATE vmshm-backed|panthor: VM_BIND vmshm payload mapped|panthor-proxy: OPEN_SESSION session=[1-9][0-9]*|panthor-proxy: DEV_QUERY session=[1-9][0-9]*|panthor-proxy: VM_CREATE session=[1-9][0-9]*|panthor-proxy: VM_DESTROY session=[1-9][0-9]*|panthor-proxy: VM_BIND session=[1-9][0-9]*|panthor-proxy: VM_GET_STATE session=[1-9][0-9]*|panthor-proxy: BO_CREATE session=[1-9][0-9]*|panthor-proxy: BO_CREATE vmshm-backed session=[1-9][0-9]*|panthor-proxy: BO_DESTROY session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_CREATE session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_DESTROY session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_WAIT session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_TRANSFER session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_RESET session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_SIGNAL session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_TIMELINE_SIGNAL session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_QUERY session=[1-9][0-9]*|panthor-proxy: GROUP_CREATE session=[1-9][0-9]*|panthor-proxy: GROUP_GET_STATE session=[1-9][0-9]*|panthor-proxy: GROUP_SUBMIT session=[1-9][0-9]*|panthor-proxy: GROUP_DESTROY session=[1-9][0-9]*|panthor-proxy: TILER_HEAP_CREATE session=[1-9][0-9]*|panthor-proxy: TILER_HEAP_DESTROY session=[1-9][0-9]*|panthor-proxy: SESSION_RELEASE session=[1-9][0-9]*|panthor-proxy: CLOSE_SESSION session=[1-9][0-9]*" \
		"${LOG_DIR}/proxy.log" | tail -n 80 || true
	echo
	if [[ -f "${LOG_DIR}/ioctl-smoke-rootfs.log" ]]; then
		echo "== IOCTL smoke rootfs prep =="
		sed -n '1,120p' "${LOG_DIR}/ioctl-smoke-rootfs.log" || true
		echo
	fi
	if [[ -f "${LOG_DIR}/gles-compute-rootfs.log" ]]; then
		echo "== GLES compute rootfs prep =="
		sed -n '1,120p' "${LOG_DIR}/gles-compute-rootfs.log" || true
		echo
	fi
	echo "== Client Panthor DRM =="
	grep -aE "registered vmshm notify|client_comm_vmshm .*irq notify enabled|client_comm_vmshm: perf|PANTHOR_CLIENT_BO_MMAP_CACHED|panthor-client: BO mmap cached=|panthor-client: OPEN_SESSION|panthor-client: DEV_QUERY|panthor-client: VM_CREATE|panthor-client: VM_DESTROY|panthor-client: VM_BIND|panthor-client: VM_GET_STATE|panthor-client: BO_CREATE|panthor-client: BO_DESTROY|panthor-client: BO_MMAP_OFFSET|panthor-client: MMAP|panthor-client: MMAP_FLUSH_ID|panthor-client: SYNCOBJ_CREATE|panthor-client: SYNCOBJ_DESTROY|panthor-client: SYNCOBJ_WAIT|panthor-client: SYNCOBJ_TRANSFER|panthor-client: SYNCOBJ_TIMELINE_WAIT|panthor-client: SYNCOBJ_RESET|panthor-client: SYNCOBJ_SIGNAL|panthor-client: SYNCOBJ_TIMELINE_SIGNAL|panthor-client: SYNCOBJ_QUERY|panthor-client: GROUP_CREATE|panthor-client: GROUP_GET_STATE|panthor-client: GROUP_SUBMIT|panthor-client: GROUP_DESTROY|panthor-client: TILER_HEAP_CREATE|panthor-client: TILER_HEAP_DESTROY|panthor-client: CLOSE_SESSION|panthor-client: registered DRM frontend|PANTHOR_IOCTL_|PANTHOR_BASIC_SMOKE|PANTHOR_VM_CREATE_SMOKE|PANTHOR_BO_CREATE_SMOKE|PANTHOR_BO_LIFECYCLE_SMOKE|PANTHOR_BO_MMAP_SMOKE|PANTHOR_VM_BIND_SMOKE|PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE|PANTHOR_VM_STATE_FLUSH_SMOKE|PANTHOR_SYNCOBJ_LIFECYCLE_SMOKE|PANTHOR_SYNCOBJ_WAIT_SMOKE|PANTHOR_SYNCOBJ_TRANSFER_SMOKE|PANTHOR_SYNCOBJ_TIMELINE_WAIT_SMOKE|PANTHOR_SYNCOBJ_SIGNAL_QUERY_SMOKE|PANTHOR_GROUP_LIFECYCLE_SMOKE|PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE|PANTHOR_TILER_HEAP_LIFECYCLE_SMOKE|OPEN path=|VERSION name=|GET_CAP|DEV_QUERY_SIZE|GPU_INFO|CSIF_INFO|VM_CREATE|VM_DESTROY|VM_BIND|VM_GET_STATE|GROUP_|TILER_HEAP_|MMAP_FLUSH_ID|MUNMAP_FLUSH_ID|BO_CREATE|BO_MMAP|BO_MUNMAP|PRIME_|SYNCOBJ_|GEM_CLOSE|ERROR|WARN|Kernel panic|Guest-boot failed" \
		"${LOG_DIR}/client.log" || true
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		echo
		echo "== GLES compute smoke =="
		grep -aE "PANTHOR_CLIENT_BO_MMAP_CACHED|GPU_SMOKE_RESULT|COMPUTE_CHECK|GL_RENDERER|GL_VENDOR|GL_VERSION|GBM_BACKEND|DRM_NODE|STAGE=|PERF_|gles-compute-smoke rc|mismatch|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|ERROR|WARN" \
			"${LOG_DIR}/client.log" || true
	fi
	echo
	if [[ "${IOCTL_SMOKE}" == "1" ]] &&
	   ioctl_mode_marker_ok &&
	   ioctl_common_markers_ok &&
	   ioctl_vm_create_markers_ok &&
	   ioctl_bo_create_markers_ok &&
		   ioctl_bo_lifecycle_markers_ok &&
		   ioctl_bo_mmap_markers_ok &&
		   ioctl_vm_bind_markers_ok &&
		   ioctl_vm_bind_async_sync_markers_ok &&
		   ioctl_vm_state_flush_markers_ok &&
	   ioctl_syncobj_lifecycle_markers_ok &&
	   ioctl_syncobj_wait_markers_ok &&
		   ioctl_syncobj_transfer_markers_ok &&
			   ioctl_syncobj_timeline_wait_markers_ok &&
			   ioctl_syncobj_signal_query_markers_ok &&
			   ioctl_group_lifecycle_markers_ok &&
			   ioctl_group_submit_syncpoint_markers_ok &&
			   ioctl_tiler_heap_lifecycle_markers_ok; then
			echo "RESULT: PASS"
	elif [[ "${GLES_COMPUTE_SMOKE}" == "1" ]] &&
	     grep -qa "GPU_SMOKE_RESULT=PASS" "${LOG_DIR}/client.log" &&
	     grep -qa "COMPUTE_CHECK=PASS" "${LOG_DIR}/client.log" &&
	     grep -qaE "GL_RENDERER=.*Mali|GL_RENDERER=.*Panfrost" "${LOG_DIR}/client.log" &&
	     gles_metric_markers_ok &&
	     ! grep -qaE "software renderer detected|llvmpipe|softpipe|Software Rasterizer|COMPUTE_CHECK=FAIL|GPU_SMOKE_RESULT=FAIL|Kernel panic|Oops|job timeout|mismatch" "${LOG_DIR}/client.log"; then
			echo "RESULT: PASS"
	elif [[ "${IOCTL_SMOKE}" != "1" && "${GLES_COMPUTE_SMOKE}" != "1" ]] &&
	     grep -qa "panthor-client: DEV_QUERY selftest passed" "${LOG_DIR}/client.log" &&
	     grep -qa "panthor-client: DEV_QUERY perf selftest passed" "${LOG_DIR}/client.log"; then
		echo "RESULT: PASS"
	else
		echo "RESULT: FAIL"
	fi
} >"${LOG_DIR}/result"

cat "${LOG_DIR}/result"
echo "LOG_DIR=${LOG_DIR}"

grep -qa "RESULT: PASS" "${LOG_DIR}/result"
REMOTE_SCRIPT
}

fetch_logs() {
	log "Fetching logs back to ${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"
	mkdir -p "${SFTP_LOG_ROOT}/shared/vmshm-1client"
	rsync_remote -av --info=stats2,name1 \
		"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}/" \
		"${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}/"
}

show_summary() {
	local result="${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}/result"

	if [[ -f "${result}" ]]; then
		log "Result summary"
		sed -n '1,220p' "${result}"
		echo
		echo "Local logs: ${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"
	else
		log "No local result fetched yet"
		echo "Expected: ${result}"
	fi
}

require_cmd ssh
require_cmd rsync
require_cmd setsid

if [[ "${BUILD_KERNEL}" -eq 1 ]]; then
	build_kernels
fi
if [[ "${BUILD_FIRECRACKER}" -eq 1 ]]; then
	build_firecracker
fi
build_ioctl_smoke
if [[ "${INSTALL_CONFIGS}" -eq 1 ]]; then
	install_configs
fi
if [[ "${SYNC_TO_REMOTE}" -eq 1 ]]; then
	sync_to_remote
fi

remote_status=0
if [[ "${RUN_REMOTE}" -eq 1 ]]; then
	run_remote_test || remote_status=$?
fi
if [[ "${FETCH_LOGS}" -eq 1 ]]; then
	fetch_logs
fi

show_summary
exit "${remote_status}"
