#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SFTP_ROOT=${SFTP_ROOT:-"${ROOT_DIR}/GPU-SFTP"}
SFTP_BINS=${SFTP_BINS:-"${SFTP_ROOT}/firecracker-bins"}
SFTP_LOG_ROOT=${SFTP_LOG_ROOT:-"${SFTP_ROOT}/log"}

REMOTE_HOST=${REMOTE_HOST:-192.168.137.10}
REMOTE_USER=${REMOTE_USER:-root}
REMOTE_PASS=${REMOTE_PASS:-root}
REMOTE_ROOT=${REMOTE_ROOT:-/root/GPU-SFTP}
REMOTE_BINS=${REMOTE_BINS:-"${REMOTE_ROOT}/firecracker-bins"}
REMOTE_LOG_ROOT=${REMOTE_LOG_ROOT:-"${REMOTE_ROOT}/log"}

RUN_ID=${RUN_ID:-gpu-perf-host-vs-passthrough-$(date +%Y%m%d-%H%M%S)}
ITERATIONS=${ITERATIONS:-100}
WARMUP=${WARMUP:-5}
# Counts are uint32 element counts:
# 1048576 = 4 MiB, 4194304 = 16 MiB, 16777216 = 64 MiB.
COUNT=${COUNT:-1048576}
COUNT_SWEEP=${COUNT_SWEEP:-1048576,4194304,16777216}
LARGE_COUNT_THRESHOLD=${LARGE_COUNT_THRESHOLD:-16777216}
LARGE_COUNT_ITERATIONS=${LARGE_COUNT_ITERATIONS:-20}
LARGE_COUNT_WARMUP=${LARGE_COUNT_WARMUP:-5}
VM_TIMEOUT=${VM_TIMEOUT:-120}
HOST_TIMEOUT=${HOST_TIMEOUT:-120}
PASSTHROUGH_VM_RUNNER=${PASSTHROUGH_VM_RUNNER:-scripts/passthrough/run-gpu-panfrost-vm.sh}
PASSTHROUGH_VM_CONFIG=${PASSTHROUGH_VM_CONFIG:-configs/passthrough/gpu-panfrost-vm-config.json}
ROOTFS_IMAGE=${ROOTFS_IMAGE:-rootfs/rootfs-panfrost.ext4}
HOST_USE_ROOTFS_USERSPACE=${HOST_USE_ROOTFS_USERSPACE:-0}
ALU_ITERS=${ALU_ITERS:-1}
VM_HUGE_PAGES_2M=${VM_HUGE_PAGES_2M:-0}
VM_TASKSET_CPU=${VM_TASKSET_CPU:-}
PMTHOR_IRQ_AFFINITY_CPU=${PMTHOR_IRQ_AFFINITY_CPU:-}
PMTHOR_IRQ_AFFINITY_LABELS=${PMTHOR_IRQ_AFFINITY_LABELS:-pmthor-job}
PMTHOR_IRQ_STATS=${PMTHOR_IRQ_STATS:-0}
GUEST_PANTHOR_IRQ_STATS=${GUEST_PANTHOR_IRQ_STATS:-0}
GUEST_PANTHOR_SUBMIT_STATS=${GUEST_PANTHOR_SUBMIT_STATS:-0}
GUEST_PANTHOR_PT_TIMING=${GUEST_PANTHOR_PT_TIMING:-0}

SYNC_TO_REMOTE=1
REMOTE_BUILD=1
ROOTFS_UPDATE=1
RUN_VM=1
RUN_HOST=1
FETCH_LOGS=1
INSTALL_REMOTE_DEPS=0

usage() {
	cat <<EOF
Usage: $(basename "$0") [options]

Run a no-tracing OpenGL ES compute performance comparison between the remote
host GPU path and a Firecracker VM using GPU passthrough.

Options:
  --iterations N             Measured iterations, default: ${ITERATIONS}
  --warmup N                 Warmup iterations excluded from stats, default: ${WARMUP}
  --count N                  Run a single SSBO size in uint32 elements; clears the default sweep
  --count-sweep LIST         Comma-separated counts, default: ${COUNT_SWEEP}
                              Current default is 1048576,4194304,16777216
                              i.e. 4 MiB, 16 MiB, 64 MiB buffers
  --large-count-threshold N  Counts >= N use large-count iteration settings, default: ${LARGE_COUNT_THRESHOLD}
                              Default threshold is 64 MiB when count is uint32 elements
  --large-count-iterations N Measured iterations for large counts, default: ${LARGE_COUNT_ITERATIONS}
                              Default makes 64 MiB use 20 measured iterations instead of 100
  --large-count-warmup N     Warmup iterations for large counts, default: ${LARGE_COUNT_WARMUP}
  --host-rootfs-userspace    Run host direct smoke inside the VM rootfs userspace
  --alu-iters N              Diagnostic mode: shader ALU loop iterations per element, default: ${ALU_ITERS}
  --vm-huge-pages-2m         Diagnostic mode: run the passthrough VM with 2M hugetlbfs memory
  --vm-taskset-cpu CPU       Diagnostic mode: run Firecracker/launcher with taskset -c CPU
  --pmthor-irq-affinity-cpu CPU
                              Diagnostic mode: pin selected host pmthor IRQs during VM workload
  --pmthor-irq-affinity-labels LIST
                              Comma-separated IRQ labels to pin, default: ${PMTHOR_IRQ_AFFINITY_LABELS}
  --pmthor-irq-stats          Diagnostic mode: enable host pmthor IRQ timing stats
  --guest-panthor-irq-stats   Diagnostic mode: enable guest Panthor job IRQ timing stats
  --guest-panthor-submit-stats Diagnostic mode: enable guest Panthor submit/vm-bind aggregate timing stats
  --guest-panthor-pt-timing    Diagnostic mode: enable guest passthrough page-table aggregate timing stats
  --vm-timeout SEC           VM run timeout, default: ${VM_TIMEOUT}
  --host-timeout SEC         Host smoke timeout, default: ${HOST_TIMEOUT}
  --run-id ID                Run log directory name
  --skip-sync                Do not rsync GPU-SFTP to the remote host
  --skip-remote-build        Use existing remote gles-compute-smoke
  --skip-rootfs-update       Do not inject binary/scripts/env into rootfs
  --skip-vm                  Do not run passthrough VM workload
  --skip-host                Do not run host direct workload
  --skip-fetch-logs          Do not fetch logs back to local log directory
  --install-remote-deps      Install remote build deps before compiling smoke
  -h, --help                 Show this help

Environment overrides:
  REMOTE_HOST REMOTE_USER REMOTE_PASS REMOTE_ROOT REMOTE_BINS REMOTE_LOG_ROOT
  SFTP_ROOT SFTP_BINS SFTP_LOG_ROOT RUN_ID ITERATIONS WARMUP COUNT COUNT_SWEEP
  LARGE_COUNT_THRESHOLD LARGE_COUNT_ITERATIONS LARGE_COUNT_WARMUP
  VM_TIMEOUT HOST_TIMEOUT PASSTHROUGH_VM_RUNNER PASSTHROUGH_VM_CONFIG
  ROOTFS_IMAGE HOST_USE_ROOTFS_USERSPACE ALU_ITERS VM_HUGE_PAGES_2M
  VM_TASKSET_CPU PMTHOR_IRQ_AFFINITY_CPU
  PMTHOR_IRQ_AFFINITY_LABELS PMTHOR_IRQ_STATS GUEST_PANTHOR_IRQ_STATS
  GUEST_PANTHOR_SUBMIT_STATS GUEST_PANTHOR_PT_TIMING

Logs:
  remote: ${REMOTE_LOG_ROOT}/passthrough/perf/${RUN_ID}
  local:  ${SFTP_LOG_ROOT}/passthrough/perf/${RUN_ID}
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--iterations)
		shift; [[ $# -gt 0 ]] || { echo "--iterations requires an argument" >&2; exit 2; }
		ITERATIONS=$1
		;;
	--warmup)
		shift; [[ $# -gt 0 ]] || { echo "--warmup requires an argument" >&2; exit 2; }
		WARMUP=$1
		;;
	--count)
		shift; [[ $# -gt 0 ]] || { echo "--count requires an argument" >&2; exit 2; }
		COUNT=$1
		COUNT_SWEEP=
		;;
	--count-sweep)
		shift; [[ $# -gt 0 ]] || { echo "--count-sweep requires an argument" >&2; exit 2; }
		COUNT_SWEEP=$1
		;;
	--large-count-threshold)
		shift; [[ $# -gt 0 ]] || { echo "--large-count-threshold requires an argument" >&2; exit 2; }
		LARGE_COUNT_THRESHOLD=$1
		;;
	--large-count-iterations)
		shift; [[ $# -gt 0 ]] || { echo "--large-count-iterations requires an argument" >&2; exit 2; }
		LARGE_COUNT_ITERATIONS=$1
		;;
	--large-count-warmup)
		shift; [[ $# -gt 0 ]] || { echo "--large-count-warmup requires an argument" >&2; exit 2; }
		LARGE_COUNT_WARMUP=$1
		;;
	--host-rootfs-userspace)
		HOST_USE_ROOTFS_USERSPACE=1
		;;
	--alu-iters)
		shift; [[ $# -gt 0 ]] || { echo "--alu-iters requires an argument" >&2; exit 2; }
		ALU_ITERS=$1
		;;
	--vm-huge-pages-2m)
		VM_HUGE_PAGES_2M=1
		;;
	--vm-taskset-cpu)
		shift; [[ $# -gt 0 ]] || { echo "--vm-taskset-cpu requires an argument" >&2; exit 2; }
		VM_TASKSET_CPU=$1
		;;
	--pmthor-irq-affinity-cpu)
		shift; [[ $# -gt 0 ]] || { echo "--pmthor-irq-affinity-cpu requires an argument" >&2; exit 2; }
		PMTHOR_IRQ_AFFINITY_CPU=$1
		;;
	--pmthor-irq-affinity-labels)
		shift; [[ $# -gt 0 ]] || { echo "--pmthor-irq-affinity-labels requires an argument" >&2; exit 2; }
		PMTHOR_IRQ_AFFINITY_LABELS=$1
		;;
	--pmthor-irq-stats)
		PMTHOR_IRQ_STATS=1
		;;
	--guest-panthor-irq-stats)
		GUEST_PANTHOR_IRQ_STATS=1
		;;
	--guest-panthor-submit-stats)
		GUEST_PANTHOR_SUBMIT_STATS=1
		;;
	--guest-panthor-pt-timing)
		GUEST_PANTHOR_PT_TIMING=1
		;;
	--vm-timeout)
		shift; [[ $# -gt 0 ]] || { echo "--vm-timeout requires an argument" >&2; exit 2; }
		VM_TIMEOUT=$1
		;;
	--host-timeout)
		shift; [[ $# -gt 0 ]] || { echo "--host-timeout requires an argument" >&2; exit 2; }
		HOST_TIMEOUT=$1
		;;
	--run-id)
		shift; [[ $# -gt 0 ]] || { echo "--run-id requires an argument" >&2; exit 2; }
		RUN_ID=$1
		;;
	--skip-sync)
		SYNC_TO_REMOTE=0
		;;
	--skip-remote-build)
		REMOTE_BUILD=0
		;;
	--skip-rootfs-update)
		ROOTFS_UPDATE=0
		;;
	--skip-vm)
		RUN_VM=0
		;;
	--skip-host)
		RUN_HOST=0
		;;
	--skip-fetch-logs)
		FETCH_LOGS=0
		;;
	--install-remote-deps)
		INSTALL_REMOTE_DEPS=1
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

	tmpdir=$(mktemp -d /tmp/gpu-perf-ssh.XXXXXX)
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
		-oConnectTimeout=5 \
		"${REMOTE_USER}@${REMOTE_HOST}" \
		"$@"
}

rsync_remote() {
	with_ssh_password env \
		RSYNC_RSH="ssh -p 22 -oBatchMode=no -oStrictHostKeyChecking=accept-new -oConnectTimeout=5" \
		rsync "$@"
}

# shellcheck source=scripts/lib/gpu_sftp_layout.sh
source "${ROOT_DIR}/scripts/lib/gpu_sftp_layout.sh"

sync_to_remote() {
	local excludes=(
		--exclude='.vscode/'
		--exclude='.git/'
		--exclude='node_modules/'
		--exclude='log/'
		--exclude='firecracker-bins/run-logs/'
		--exclude='firecracker-bins/rootfs/'
		--exclude='linux-host-kernel/'
	)

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

run_remote_perf() {
	local run_id_q remote_root_q remote_bins_q remote_log_root_q
	local iterations_q warmup_q count_q
	local large_threshold_q large_iterations_q large_warmup_q
	local vm_timeout_q host_timeout_q runner_q config_q rootfs_q
	local count_sweep_q host_rootfs_q alu_iters_q vm_huge_pages_q
	local vm_taskset_cpu_q pmthor_irq_affinity_cpu_q pmthor_irq_affinity_labels_q pmthor_irq_stats_q
	local guest_panthor_irq_stats_q guest_panthor_submit_stats_q
	local guest_panthor_pt_timing_q
	local sync_q build_q update_q run_vm_q run_host_q deps_q remote_status

	run_id_q=$(quote "${RUN_ID}")
	remote_root_q=$(quote "${REMOTE_ROOT}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	iterations_q=$(quote "${ITERATIONS}")
	warmup_q=$(quote "${WARMUP}")
	count_q=$(quote "${COUNT}")
	large_threshold_q=$(quote "${LARGE_COUNT_THRESHOLD}")
	large_iterations_q=$(quote "${LARGE_COUNT_ITERATIONS}")
	large_warmup_q=$(quote "${LARGE_COUNT_WARMUP}")
	count_sweep_q=$(quote "${COUNT_SWEEP}")
	vm_timeout_q=$(quote "${VM_TIMEOUT}")
	host_timeout_q=$(quote "${HOST_TIMEOUT}")
	runner_q=$(quote "${PASSTHROUGH_VM_RUNNER}")
	config_q=$(quote "${PASSTHROUGH_VM_CONFIG}")
	rootfs_q=$(quote "${ROOTFS_IMAGE}")
	host_rootfs_q=$(quote "${HOST_USE_ROOTFS_USERSPACE}")
	alu_iters_q=$(quote "${ALU_ITERS}")
	vm_huge_pages_q=$(quote "${VM_HUGE_PAGES_2M}")
	vm_taskset_cpu_q=$(quote "${VM_TASKSET_CPU}")
	pmthor_irq_affinity_cpu_q=$(quote "${PMTHOR_IRQ_AFFINITY_CPU}")
	pmthor_irq_affinity_labels_q=$(quote "${PMTHOR_IRQ_AFFINITY_LABELS}")
	pmthor_irq_stats_q=$(quote "${PMTHOR_IRQ_STATS}")
	guest_panthor_irq_stats_q=$(quote "${GUEST_PANTHOR_IRQ_STATS}")
	guest_panthor_submit_stats_q=$(quote "${GUEST_PANTHOR_SUBMIT_STATS}")
	guest_panthor_pt_timing_q=$(quote "${GUEST_PANTHOR_PT_TIMING}")
	sync_q=$(quote "${SYNC_TO_REMOTE}")
	build_q=$(quote "${REMOTE_BUILD}")
	update_q=$(quote "${ROOTFS_UPDATE}")
	run_vm_q=$(quote "${RUN_VM}")
	run_host_q=$(quote "${RUN_HOST}")
	deps_q=$(quote "${INSTALL_REMOTE_DEPS}")

	log "Running remote host-vs-passthrough GLES perf test: ${RUN_ID}"
	set +e
	ssh_remote "RUN_ID=${run_id_q} REMOTE_ROOT=${remote_root_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} ITERATIONS=${iterations_q} WARMUP=${warmup_q} COUNT=${count_q} COUNT_SWEEP=${count_sweep_q} LARGE_COUNT_THRESHOLD=${large_threshold_q} LARGE_COUNT_ITERATIONS=${large_iterations_q} LARGE_COUNT_WARMUP=${large_warmup_q} VM_TIMEOUT=${vm_timeout_q} HOST_TIMEOUT=${host_timeout_q} PASSTHROUGH_VM_RUNNER=${runner_q} PASSTHROUGH_VM_CONFIG=${config_q} ROOTFS_IMAGE=${rootfs_q} HOST_USE_ROOTFS_USERSPACE=${host_rootfs_q} ALU_ITERS=${alu_iters_q} VM_HUGE_PAGES_2M=${vm_huge_pages_q} VM_TASKSET_CPU=${vm_taskset_cpu_q} PMTHOR_IRQ_AFFINITY_CPU=${pmthor_irq_affinity_cpu_q} PMTHOR_IRQ_AFFINITY_LABELS=${pmthor_irq_affinity_labels_q} PMTHOR_IRQ_STATS=${pmthor_irq_stats_q} GUEST_PANTHOR_IRQ_STATS=${guest_panthor_irq_stats_q} GUEST_PANTHOR_SUBMIT_STATS=${guest_panthor_submit_stats_q} GUEST_PANTHOR_PT_TIMING=${guest_panthor_pt_timing_q} SYNC_TO_REMOTE=${sync_q} REMOTE_BUILD=${build_q} ROOTFS_UPDATE=${update_q} RUN_VM=${run_vm_q} RUN_HOST=${run_host_q} INSTALL_REMOTE_DEPS=${deps_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

LOG_DIR="${REMOTE_LOG_ROOT}/passthrough/perf/${RUN_ID}"
SMOKE_SRC_DIR="${REMOTE_ROOT}/tests/gpu-compute-smoke"
SMOKE_BIN="${REMOTE_BINS}/bin/gles-compute-smoke"
ROOTFS_PATH="${REMOTE_BINS}/${ROOTFS_IMAGE}"
MNT="${LOG_DIR}/rootfs-mnt"
HOST_ROOTFS_MNT="${LOG_DIR}/host-rootfs-mnt"
PERF_ARGS=(--perf --iterations "${ITERATIONS}" --warmup "${WARMUP}" --count "${COUNT}")
COUNT_ITERATIONS="${ITERATIONS}"
COUNT_WARMUP="${WARMUP}"
ROOTFS_ENV_RESTORE_NEEDED=0
HOST_ROOTFS_MOUNTED=0
GPU_DEV=fb000000.gpu
ACTIVE_VM_CONFIG="${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}"
HUGEPAGES_ORIG_NR=
HUGEPAGES_RESTORE_NEEDED=0
PMTHOR_IRQ_AFFINITY_RESTORE_FILE="${LOG_DIR}/pmthor-irq-affinity.restore"
PMTHOR_IRQ_STATS_PARAM=
PMTHOR_IRQ_STATS_ORIG=
PMTHOR_IRQ_STATS_RESTORE_NEEDED=0

mkdir -p "${LOG_DIR}"

log() {
	printf '\n==> %s\n' "$*" | tee -a "${LOG_DIR}/remote-steps.log"
}

validate_workload_options() {
	if ! [[ "${ALU_ITERS}" =~ ^[0-9]+$ ]] || (( ALU_ITERS == 0 )); then
		write_failure_result "invalid --alu-iters value: ${ALU_ITERS}"
		exit 1
	fi
}

select_count_iterations() {
	local count="$1"

	COUNT_ITERATIONS="${ITERATIONS}"
	COUNT_WARMUP="${WARMUP}"
	if [[ "${count}" =~ ^[0-9]+$ ]] &&
	   [[ "${LARGE_COUNT_THRESHOLD}" =~ ^[0-9]+$ ]] &&
	   (( count >= LARGE_COUNT_THRESHOLD )); then
		COUNT_ITERATIONS="${LARGE_COUNT_ITERATIONS}"
		COUNT_WARMUP="${LARGE_COUNT_WARMUP}"
	fi
	PERF_ARGS=(--perf --iterations "${COUNT_ITERATIONS}" --warmup "${COUNT_WARMUP}" --count "${count}")
	if [[ "${ALU_ITERS}" -ne 1 ]]; then
		PERF_ARGS+=(--alu-iters "${ALU_ITERS}")
	fi
}

current_gpu_driver() {
	local driver

	driver=$(basename "$(readlink -f "/sys/bus/platform/devices/${GPU_DEV}/driver" 2>/dev/null)" 2>/dev/null || true)
	if [[ -n "${driver}" && "${driver}" != "." ]]; then
		printf '%s\n' "${driver}"
	else
		printf 'none\n'
	fi
}

wait_for_drm_node() {
	local i

	for i in $(seq 1 40); do
		if [[ -d /dev/dri ]] &&
		   { ls /dev/dri/card* >/dev/null 2>&1 || ls /dev/dri/renderD* >/dev/null 2>&1; }; then
			return 0
		fi
		sleep 0.1
	done
	return 1
}

restore_rootfs_env() {
	if [[ "${ROOTFS_ENV_RESTORE_NEEDED}" -ne 1 ]]; then
		return 0
	fi

	set +e
	log "Restoring rootfs gpu-smoke.env"
	pkill -x firecracker 2>/dev/null || true
	sleep 1
	if mountpoint -q "${MNT}"; then
		umount "${MNT}"
	fi
	mkdir -p "${MNT}"
	mount -o loop "${ROOTFS_PATH}" "${MNT}"
	if [[ -f "${LOG_DIR}/gpu-smoke.env.before" ]]; then
		install -Dm0644 "${LOG_DIR}/gpu-smoke.env.before" "${MNT}/root/gpu-smoke.env"
	else
		rm -f "${MNT}/root/gpu-smoke.env"
	fi
	sync
	umount "${MNT}"
	rmdir "${MNT}" 2>/dev/null || true
	ROOTFS_ENV_RESTORE_NEEDED=0
	set -e
}

unmount_host_rootfs_userspace() {
	set +e
	if [[ "${HOST_ROOTFS_MOUNTED}" -ne 1 ]]; then
		return 0
	fi

	for mp in run sys proc dev; do
		if mountpoint -q "${HOST_ROOTFS_MNT}/${mp}"; then
			umount "${HOST_ROOTFS_MNT}/${mp}"
		fi
	done
	if mountpoint -q "${HOST_ROOTFS_MNT}"; then
		umount "${HOST_ROOTFS_MNT}"
	fi
	rmdir "${HOST_ROOTFS_MNT}" 2>/dev/null || true
	HOST_ROOTFS_MOUNTED=0
	set -e
}

mount_host_rootfs_userspace() {
	if [[ "${HOST_ROOTFS_MOUNTED}" -eq 1 ]]; then
		return 0
	fi

	log "Mounting VM rootfs userspace for host direct run"
	[[ -f "${ROOTFS_PATH}" ]] || {
		write_failure_result "missing rootfs image for host userspace: ${ROOTFS_PATH}"
		exit 1
	}
	pkill -x firecracker 2>/dev/null || true
	sleep 1
	mkdir -p "${HOST_ROOTFS_MNT}"
	mount -o loop "${ROOTFS_PATH}" "${HOST_ROOTFS_MNT}"
	mount --bind /dev "${HOST_ROOTFS_MNT}/dev"
	mount -t proc proc "${HOST_ROOTFS_MNT}/proc"
	mount -t sysfs sysfs "${HOST_ROOTFS_MNT}/sys"
	mount -t tmpfs tmpfs "${HOST_ROOTFS_MNT}/run"
	mkdir -p "${HOST_ROOTFS_MNT}/tmp" "${HOST_ROOTFS_MNT}/dev/shm"
	chmod 1777 "${HOST_ROOTFS_MNT}/tmp" "${HOST_ROOTFS_MNT}/dev/shm"
	if [[ -x "${SMOKE_BIN}" ]]; then
		install -Dm0755 "${SMOKE_BIN}" "${HOST_ROOTFS_MNT}/root/gles-compute-smoke"
	fi
	HOST_ROOTFS_MOUNTED=1
}

restore_pmthor() {
	set +e

	log "Restoring host GPU driver to pmthor"
	pkill -x firecracker 2>/dev/null || true
	sleep 1

	driver=$(current_gpu_driver)
	if [[ "${driver}" == "panthor" ]]; then
		echo "${GPU_DEV}" > /sys/bus/platform/drivers/panthor/unbind 2>>"${LOG_DIR}/restore.log" || true
		sleep 1
	fi

	driver=$(current_gpu_driver)
	if [[ "${driver}" != "pmthor" ]]; then
		echo "${GPU_DEV}" > /sys/bus/platform/drivers/pmthor/bind 2>>"${LOG_DIR}/restore.log" || true
		sleep 1
	fi

	modprobe -r panthor 2>>"${LOG_DIR}/restore.log" || true

	{
		echo "timestamp=$(date -Is)"
		echo "driver=$(current_gpu_driver)"
		ls -l /dev/pmthor /dev/dri 2>&1 || true
		pgrep -a firecracker 2>&1 || true
	} >"${LOG_DIR}/restore-status.txt"
	set -e
}

restore_hugepages() {
	set +e
	if [[ "${HUGEPAGES_RESTORE_NEEDED}" -ne 1 || -z "${HUGEPAGES_ORIG_NR}" ]]; then
		return 0
	fi

	log "Restoring nr_hugepages to ${HUGEPAGES_ORIG_NR}"
	printf '%s\n' "${HUGEPAGES_ORIG_NR}" > /proc/sys/vm/nr_hugepages 2>>"${LOG_DIR}/hugepages.log" || true
	{
		echo "timestamp=$(date -Is)"
		echo "restored_nr_hugepages=${HUGEPAGES_ORIG_NR}"
		grep -i huge /proc/meminfo || true
	} >>"${LOG_DIR}/hugepages.log"
	HUGEPAGES_RESTORE_NEEDED=0
	set -e
}

restore_pmthor_irq_stats() {
	set +e
	if [[ "${PMTHOR_IRQ_STATS_RESTORE_NEEDED}" -ne 1 || -z "${PMTHOR_IRQ_STATS_ORIG}" ]]; then
		set -e
		return 0
	fi

	log "Restoring pmthor IRQ stats parameter to ${PMTHOR_IRQ_STATS_ORIG}"
	if [[ -w "${PMTHOR_IRQ_STATS_PARAM}" ]]; then
		printf '%s\n' "${PMTHOR_IRQ_STATS_ORIG}" >"${PMTHOR_IRQ_STATS_PARAM}" 2>>"${LOG_DIR}/pmthor-irq-stats.log" || true
	fi
	{
		echo "timestamp=$(date -Is)"
		echo "restore=${PMTHOR_IRQ_STATS_ORIG}"
		echo "current=$(cat "${PMTHOR_IRQ_STATS_PARAM}" 2>/dev/null || echo NA)"
	} >>"${LOG_DIR}/pmthor-irq-stats.log"
	PMTHOR_IRQ_STATS_RESTORE_NEEDED=0
	set -e
}

find_pmthor_irq_stats_param() {
	local path

	for path in /sys/module/pmthor_drv/parameters/irq_stats \
		    /sys/module/pmthor/parameters/irq_stats; do
		if [[ -e "${path}" ]]; then
			printf '%s\n' "${path}"
			return 0
		fi
	done
	find /sys/module -path '*/parameters/irq_stats' -print -quit 2>/dev/null
}

apply_pmthor_irq_stats() {
	if [[ "${PMTHOR_IRQ_STATS}" -ne 1 ]]; then
		return 0
	fi

	log "Enabling pmthor IRQ timing stats"
	if [[ -z "${PMTHOR_IRQ_STATS_PARAM}" ]]; then
		PMTHOR_IRQ_STATS_PARAM=$(find_pmthor_irq_stats_param)
	fi
	if [[ ! -e "${PMTHOR_IRQ_STATS_PARAM}" ]]; then
		write_failure_result "host kernel does not expose a pmthor irq_stats parameter; deploy pmthor irq_stats host kernel first"
		exit 1
	fi
	if [[ ! -w "${PMTHOR_IRQ_STATS_PARAM}" ]]; then
		write_failure_result "cannot write ${PMTHOR_IRQ_STATS_PARAM}"
		exit 1
	fi
	if [[ "${PMTHOR_IRQ_STATS_RESTORE_NEEDED}" -ne 1 ]]; then
		PMTHOR_IRQ_STATS_ORIG=$(cat "${PMTHOR_IRQ_STATS_PARAM}" 2>/dev/null || true)
		[[ -n "${PMTHOR_IRQ_STATS_ORIG}" ]] || PMTHOR_IRQ_STATS_ORIG=0
		PMTHOR_IRQ_STATS_RESTORE_NEEDED=1
	fi
	printf '1\n' >"${PMTHOR_IRQ_STATS_PARAM}" 2>/dev/null || printf 'Y\n' >"${PMTHOR_IRQ_STATS_PARAM}"
	{
		echo "timestamp=$(date -Is)"
		echo "param=${PMTHOR_IRQ_STATS_PARAM}"
		echo "original=${PMTHOR_IRQ_STATS_ORIG}"
		echo "enabled=$(cat "${PMTHOR_IRQ_STATS_PARAM}" 2>/dev/null || echo NA)"
	} >>"${LOG_DIR}/pmthor-irq-stats.log"
}

pmthor_irq_numbers_for_label() {
	local label="$1"

	awk -v label="${label}" '
		index($0, label) > 0 {
			irq = $1;
			sub(/:$/, "", irq);
			if (irq ~ /^[0-9]+$/)
				print irq;
		}
	' /proc/interrupts 2>/dev/null
}

restore_pmthor_irq_affinity() {
	local irq original

	set +e
	if [[ ! -f "${PMTHOR_IRQ_AFFINITY_RESTORE_FILE}" ]]; then
		set -e
		return 0
	fi

	log "Restoring pmthor IRQ affinity"
	while read -r irq original; do
		[[ -n "${irq}" && -n "${original}" ]] || continue
		if [[ -w "/proc/irq/${irq}/smp_affinity_list" ]]; then
			printf '%s\n' "${original}" >"/proc/irq/${irq}/smp_affinity_list" 2>>"${LOG_DIR}/affinity.log" || true
		fi
	done <"${PMTHOR_IRQ_AFFINITY_RESTORE_FILE}"
	rm -f "${PMTHOR_IRQ_AFFINITY_RESTORE_FILE}"
	{
		echo "timestamp=$(date -Is)"
		echo "restore=done"
		cat /proc/interrupts | grep -E 'pmthor-(job|mmu|gpu)' || true
	} >>"${LOG_DIR}/affinity.log"
	set -e
}

apply_pmthor_irq_affinity() {
	local label irq original found=0

	if [[ -z "${PMTHOR_IRQ_AFFINITY_CPU}" ]]; then
		return 0
	fi

	log "Pinning pmthor IRQ affinity to ${PMTHOR_IRQ_AFFINITY_CPU}"
	command -v taskset >/dev/null 2>&1 || {
		write_failure_result "taskset is required for affinity diagnostics"
		exit 1
	}
	taskset -c "${PMTHOR_IRQ_AFFINITY_CPU}" true 2>>"${LOG_DIR}/affinity.log" || {
		write_failure_result "invalid pmthor IRQ affinity CPU/list: ${PMTHOR_IRQ_AFFINITY_CPU}"
		exit 1
	}

	restore_pmthor_irq_affinity
	: >"${PMTHOR_IRQ_AFFINITY_RESTORE_FILE}"
	{
		echo "timestamp=$(date -Is)"
		echo "pmthor_irq_affinity_cpu=${PMTHOR_IRQ_AFFINITY_CPU}"
		echo "pmthor_irq_affinity_labels=${PMTHOR_IRQ_AFFINITY_LABELS}"
		echo "before:"
		cat /proc/interrupts | grep -E 'pmthor-(job|mmu|gpu)' || true
	} >>"${LOG_DIR}/affinity.log"

	for label in ${PMTHOR_IRQ_AFFINITY_LABELS//,/ }; do
		[[ -n "${label}" ]] || continue
		while read -r irq; do
			[[ -n "${irq}" ]] || continue
			if [[ ! -r "/proc/irq/${irq}/smp_affinity_list" || ! -w "/proc/irq/${irq}/smp_affinity_list" ]]; then
				echo "irq=${irq} label=${label} affinity_file_unavailable" >>"${LOG_DIR}/affinity.log"
				continue
			fi
			original=$(cat "/proc/irq/${irq}/smp_affinity_list" 2>/dev/null || true)
			[[ -n "${original}" ]] || original=NA
			printf '%s %s\n' "${irq}" "${original}" >>"${PMTHOR_IRQ_AFFINITY_RESTORE_FILE}"
			if printf '%s\n' "${PMTHOR_IRQ_AFFINITY_CPU}" >"/proc/irq/${irq}/smp_affinity_list" 2>>"${LOG_DIR}/affinity.log"; then
				echo "irq=${irq} label=${label} original=${original} new=${PMTHOR_IRQ_AFFINITY_CPU}" >>"${LOG_DIR}/affinity.log"
				found=1
			else
				echo "irq=${irq} label=${label} set_failed original=${original}" >>"${LOG_DIR}/affinity.log"
			fi
		done < <(pmthor_irq_numbers_for_label "${label}")
	done

	{
		echo "after:"
		for label in ${PMTHOR_IRQ_AFFINITY_LABELS//,/ }; do
			while read -r irq; do
				[[ -n "${irq}" ]] || continue
				printf 'irq=%s label=%s affinity=%s\n' \
					"${irq}" "${label}" \
					"$(cat "/proc/irq/${irq}/smp_affinity_list" 2>/dev/null || echo NA)"
			done < <(pmthor_irq_numbers_for_label "${label}")
		done
	} >>"${LOG_DIR}/affinity.log"

	if [[ "${found}" -ne 1 ]]; then
		write_failure_result "failed to find or set selected pmthor IRQ affinity; see affinity.log"
		exit 1
	fi
}

cleanup() {
	set +e
	if mountpoint -q "${MNT}"; then
		umount "${MNT}"
	fi
	restore_pmthor_irq_affinity
	restore_pmthor_irq_stats
	unmount_host_rootfs_userspace
	restore_rootfs_env
	restore_pmthor
	restore_hugepages
}
trap cleanup EXIT

write_failure_result() {
	local message="$1"

	{
		echo "OpenGL ES compute smoke host-vs-passthrough performance result"
		echo "Run ID: ${RUN_ID}"
		echo "Timestamp: $(date -Is)"
		echo "Remote log dir: ${LOG_DIR}"
		echo
		echo "RESULT: FAIL"
		echo "${message}"
	} >"${LOG_DIR}/result"
	cat "${LOG_DIR}/result"
}

install_remote_deps() {
	if [[ "${INSTALL_REMOTE_DEPS}" -ne 1 ]]; then
		return 0
	fi

	log "Installing remote build dependencies"
	apt-get update
	DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
		gcc pkg-config libegl-dev libgles-dev libgbm-dev
}

build_smoke() {
	if [[ "${REMOTE_BUILD}" -ne 1 ]]; then
		[[ -x "${SMOKE_BIN}" ]] || {
			write_failure_result "missing ${SMOKE_BIN}; rerun without --skip-remote-build"
			exit 1
		}
		return 0
	fi

	log "Compiling gles-compute-smoke on remote host"
	mkdir -p "$(dirname "${SMOKE_BIN}")"
	[[ -f "${SMOKE_SRC_DIR}/gles_compute_smoke.c" ]] || {
		write_failure_result "missing ${SMOKE_SRC_DIR}/gles_compute_smoke.c"
		exit 1
	}
	command -v cc >/dev/null 2>&1 || {
		write_failure_result "remote cc is missing; use --install-remote-deps"
		exit 1
	}
	command -v pkg-config >/dev/null 2>&1 || {
		write_failure_result "remote pkg-config is missing; use --install-remote-deps"
		exit 1
	}
	cc -O2 -Wall -Wextra -std=c11 \
		"${SMOKE_SRC_DIR}/gles_compute_smoke.c" \
		-o "${SMOKE_BIN}" \
		$(pkg-config --cflags --libs egl glesv2 gbm)
	chmod 0755 "${SMOKE_BIN}"
}

json_value() {
	local file="$1"
	local expr="$2"

	python3 - "$file" "$expr" <<'PY'
import json
import sys

path, expr = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    value = json.load(f)
for part in expr.split("."):
    value = value[part]
print(value)
PY
}

prepare_hugepages_config() {
	local mem_size_mib needed total free target

	if [[ "${VM_HUGE_PAGES_2M}" -ne 1 || "${RUN_VM}" -ne 1 ]]; then
		return 0
	fi

	log "Preparing 2M hugetlbfs-backed VM memory"
	command -v python3 >/dev/null 2>&1 || {
		write_failure_result "python3 is required to create temporary hugepage VM config"
		exit 1
	}

	mem_size_mib=$(json_value "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" 'machine-config.mem_size_mib')
	if ! [[ "${mem_size_mib}" =~ ^[0-9]+$ ]] || (( mem_size_mib == 0 || mem_size_mib % 2 != 0 )); then
		write_failure_result "hugepage VM memory requires even nonzero mem_size_mib; got ${mem_size_mib}"
		exit 1
	fi

	needed=$((mem_size_mib / 2))
	HUGEPAGES_ORIG_NR=$(cat /proc/sys/vm/nr_hugepages)
	HUGEPAGES_RESTORE_NEEDED=1
	total=$(awk '/HugePages_Total:/ {print $2}' /proc/meminfo)
	free=$(awk '/HugePages_Free:/ {print $2}' /proc/meminfo)
	target="${total}"
	if (( free < needed )); then
		target=$((total + needed - free))
		printf '%s\n' "${target}" > /proc/sys/vm/nr_hugepages 2>>"${LOG_DIR}/hugepages.log" || true
	fi

	free=$(awk '/HugePages_Free:/ {print $2}' /proc/meminfo)
	{
		echo "timestamp=$(date -Is)"
		echo "requested_mem_size_mib=${mem_size_mib}"
		echo "needed_2m_pages=${needed}"
		echo "original_nr_hugepages=${HUGEPAGES_ORIG_NR}"
		echo "target_nr_hugepages=${target}"
		grep -i huge /proc/meminfo || true
		mount | grep -i hugetlb || true
	} >"${LOG_DIR}/hugepages.log"

	if (( free < needed )); then
		write_failure_result "insufficient free 2M hugepages: need ${needed}, free ${free}; see hugepages.log"
		exit 1
	fi

	ACTIVE_VM_CONFIG="${LOG_DIR}/gpu-panfrost-vm-config-hugepages.json"
	python3 - "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" "${ACTIVE_VM_CONFIG}" <<'PY'
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, "r", encoding="utf-8") as f:
    obj = json.load(f)
obj.setdefault("machine-config", {})["huge_pages"] = "2M"
with open(dst, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2)
    f.write("\n")
PY
}

update_rootfs() {
	local count="${1:-${COUNT}}"

	if [[ "${ROOTFS_UPDATE}" -ne 1 ]]; then
		return 0
	fi

	log "Injecting smoke payload and temporary perf env into rootfs"
	[[ -f "${ROOTFS_PATH}" ]] || {
		write_failure_result "missing rootfs image: ${ROOTFS_PATH}"
		exit 1
	}
	[[ -x "${SMOKE_BIN}" ]] || {
		write_failure_result "missing executable smoke binary: ${SMOKE_BIN}"
		exit 1
	}
	[[ -f "${SMOKE_SRC_DIR}/gpu-smoke.sh" ]] || {
		write_failure_result "missing ${SMOKE_SRC_DIR}/gpu-smoke.sh"
		exit 1
	}
	[[ -f "${SMOKE_SRC_DIR}/init" ]] || {
		write_failure_result "missing ${SMOKE_SRC_DIR}/init"
		exit 1
	}

	pkill -x firecracker 2>/dev/null || true
	sleep 1
	mkdir -p "${MNT}"
	mount -o loop "${ROOTFS_PATH}" "${MNT}"
	if [[ -f "${MNT}/root/gpu-smoke.env" ]]; then
		cp -a "${MNT}/root/gpu-smoke.env" "${LOG_DIR}/gpu-smoke.env.before"
	else
		rm -f "${LOG_DIR}/gpu-smoke.env.before"
	fi
	ROOTFS_ENV_RESTORE_NEEDED=1

	install -Dm0755 "${SMOKE_BIN}" "${MNT}/root/gles-compute-smoke"
	install -Dm0755 "${SMOKE_SRC_DIR}/gpu-smoke.sh" "${MNT}/root/gpu-smoke.sh"
	install -Dm0755 "${SMOKE_SRC_DIR}/init" "${MNT}/init"
	local smoke_args

	smoke_args="--perf --iterations ${COUNT_ITERATIONS} --warmup ${COUNT_WARMUP} --count ${count}"
	if [[ "${ALU_ITERS}" -ne 1 ]]; then
		smoke_args="${smoke_args} --alu-iters ${ALU_ITERS}"
	fi
		cat >"${MNT}/root/gpu-smoke.env" <<EOF
GPU_SMOKE_ARGS="${smoke_args}"
GPU_SMOKE_QUIET_CONSOLE=1
GPU_SMOKE_GUEST_IRQ_STATS=${GUEST_PANTHOR_IRQ_STATS}
GPU_SMOKE_GUEST_SUBMIT_STATS=${GUEST_PANTHOR_SUBMIT_STATS}
GPU_SMOKE_GUEST_PT_TIMING=${GUEST_PANTHOR_PT_TIMING}
GPU_SMOKE_AFTER_RUN=poweroff
EOF
	sync
	umount "${MNT}"
	rmdir "${MNT}" 2>/dev/null || true
}

write_preflight() {
	if [[ -z "${PMTHOR_IRQ_STATS_PARAM}" ]]; then
		PMTHOR_IRQ_STATS_PARAM=$(find_pmthor_irq_stats_param)
	fi

	{
		echo "timestamp=$(date -Is)"
		echo "uname=$(uname -a)"
		echo "pwd=$(pwd)"
		echo "run_id=${RUN_ID}"
		echo "perf_args=${PERF_ARGS[*]}"
		echo "large_count_threshold=${LARGE_COUNT_THRESHOLD}"
		echo "large_count_iterations=${LARGE_COUNT_ITERATIONS}"
		echo "large_count_warmup=${LARGE_COUNT_WARMUP}"
		echo "vm_huge_pages_2m=${VM_HUGE_PAGES_2M}"
		echo "vm_taskset_cpu=${VM_TASKSET_CPU:-}"
			echo "pmthor_irq_affinity_cpu=${PMTHOR_IRQ_AFFINITY_CPU:-}"
			echo "pmthor_irq_affinity_labels=${PMTHOR_IRQ_AFFINITY_LABELS}"
			echo "pmthor_irq_stats=${PMTHOR_IRQ_STATS}"
			echo "guest_panthor_irq_stats=${GUEST_PANTHOR_IRQ_STATS}"
				echo "guest_panthor_submit_stats=${GUEST_PANTHOR_SUBMIT_STATS}"
				echo "guest_panthor_pt_timing=${GUEST_PANTHOR_PT_TIMING}"
				echo "guest_panthor_irq_stats_param=$(cat /sys/module/panthor/parameters/job_irq_stats 2>/dev/null || echo NA)"
				echo "guest_panthor_submit_stats_param=$(cat /sys/module/panthor/parameters/submit_stats 2>/dev/null || echo NA)"
				echo "guest_panthor_pt_timing_param=requested-in-vm"
				echo "pmthor_irq_stats_param=${PMTHOR_IRQ_STATS_PARAM:-NA}"
		if [[ -n "${PMTHOR_IRQ_STATS_PARAM}" ]]; then
			echo "pmthor_irq_stats_param_value=$(cat "${PMTHOR_IRQ_STATS_PARAM}" 2>/dev/null || echo NA)"
		else
			echo "pmthor_irq_stats_param_value=NA"
		fi
		echo "active_vm_config=${ACTIVE_VM_CONFIG}"
		echo "current_gpu_driver=$(current_gpu_driver)"
		echo
		echo "== files =="
		ls -lh "${REMOTE_BINS}/bin/firecracker" \
			"${REMOTE_BINS}/${PASSTHROUGH_VM_RUNNER}" \
			"${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" \
			"${ROOTFS_PATH}" \
			"${REMOTE_BINS}/kernels/passthrough/Image" \
			"${SMOKE_BIN}" 2>&1 || true
		echo
		echo "== passthrough config =="
		sed -n '1,160p' "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" 2>&1 || true
		if [[ "${ACTIVE_VM_CONFIG}" != "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" ]]; then
			echo
			echo "== active passthrough config =="
			sed -n '1,180p' "${ACTIVE_VM_CONFIG}" 2>&1 || true
		fi
		echo
		echo "== kernel image version strings =="
		strings "${REMOTE_BINS}/kernels/passthrough/Image" 2>/dev/null | grep -a -m 3 'Linux version' || true
		echo
		echo "== host panthor blacklist =="
		grep -R . /etc/modprobe.d 2>/dev/null | grep -i panthor || true
		echo
		echo "== gpu status =="
		echo "driver=$(current_gpu_driver)"
		ls -l /dev/pmthor /dev/dri 2>&1 || true
		echo
		echo "== hugepages =="
		grep -i huge /proc/meminfo || true
	} >"${LOG_DIR}/preflight.txt" 2>&1

	if [[ "${RUN_VM}" -eq 1 ]]; then
		if [[ ! -x "${REMOTE_BINS}/bin/firecracker" ]]; then
			write_failure_result "missing executable ${REMOTE_BINS}/bin/firecracker"
			exit 1
		fi
		if [[ ! -f "${REMOTE_BINS}/${PASSTHROUGH_VM_RUNNER}" ]]; then
			write_failure_result "missing ${REMOTE_BINS}/${PASSTHROUGH_VM_RUNNER}"
			exit 1
		fi
		if [[ ! -f "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" ]]; then
			write_failure_result "missing ${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}"
			exit 1
		fi
		if grep -qa 'Image\.bak' "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}"; then
			write_failure_result "${PASSTHROUGH_VM_CONFIG} points at Image.bak; use canonical latest Image"
			exit 1
		fi
		if ! grep -qa '"gpu_passthrough"[[:space:]]*:[[:space:]]*true' "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}"; then
			write_failure_result "${PASSTHROUGH_VM_CONFIG} does not enable gpu_passthrough"
			exit 1
		fi
	fi
}

run_vm_workload() {
	local count="$1"
	local suffix="$2"
	local vm_log="${LOG_DIR}/vm-${suffix}.log"
	local vm_summary="${LOG_DIR}/vm-${suffix}-summary.txt"
	local vm_dmesg_before="${LOG_DIR}/vm-${suffix}-dmesg-before.txt"
	local vm_dmesg_after="${LOG_DIR}/vm-${suffix}-dmesg-after.txt"
	local vm_interrupts_before="${LOG_DIR}/vm-${suffix}-interrupts-before.txt"
	local vm_interrupts_after="${LOG_DIR}/vm-${suffix}-interrupts-after.txt"
	local vm_cmd=()

	if [[ "${RUN_VM}" -ne 1 ]]; then
		return 0
	fi

	log "Running passthrough VM workload without tracing"
	cd "${REMOTE_BINS}"
	pkill -x firecracker 2>/dev/null || true
	sleep 1
	apply_pmthor_irq_affinity
	apply_pmthor_irq_stats
	dmesg >"${vm_dmesg_before}" 2>&1 || true
	cat /proc/interrupts >"${vm_interrupts_before}" 2>&1 || true

	if [[ "${ACTIVE_VM_CONFIG}" != "${REMOTE_BINS}/${PASSTHROUGH_VM_CONFIG}" ]]; then
		vm_cmd=(./bin/firecracker --no-api --no-seccomp --config-file "${ACTIVE_VM_CONFIG}")
	else
		vm_cmd=(sh "./${PASSTHROUGH_VM_RUNNER}")
	fi
	if [[ -n "${VM_TASKSET_CPU}" ]]; then
		command -v taskset >/dev/null 2>&1 || {
			write_failure_result "taskset is required for VM taskset diagnostics"
			exit 1
		}
		taskset -c "${VM_TASKSET_CPU}" true 2>>"${LOG_DIR}/affinity.log" || {
			write_failure_result "invalid VM taskset CPU/list: ${VM_TASKSET_CPU}"
			exit 1
		}
		vm_cmd=(taskset -c "${VM_TASKSET_CPU}" "${vm_cmd[@]}")
		{
			echo "timestamp=$(date -Is)"
			echo "vm_taskset_cpu=${VM_TASKSET_CPU}"
			echo "vm_command=${vm_cmd[*]}"
		} >>"${LOG_DIR}/affinity.log"
	fi
	set +e
	timeout -s INT -k 5 "${VM_TIMEOUT}" "${vm_cmd[@]}" </dev/null >"${vm_log}" 2>&1
	VM_STATUS=$?
	set -e

	sleep 1
	pkill -x firecracker 2>/dev/null || true
	sleep 1
	dmesg >"${vm_dmesg_after}" 2>&1 || true
	cat /proc/interrupts >"${vm_interrupts_after}" 2>&1 || true
	restore_pmthor_irq_stats
	restore_pmthor_irq_affinity

	{
		echo "count=${count}"
		echo "iterations=${COUNT_ITERATIONS}"
		echo "warmup=${COUNT_WARMUP}"
		echo "timeout_status=${VM_STATUS}"
			grep -aE 'GPU_SMOKE_RESULT|COMPUTE_CHECK|GL_RENDERER|GL_VERSION|PERF_|PANTHOR_PT_STATS|PANTHOR_PT_TIMING|PANTHOR_JOB_IRQ_STATS|PANTHOR_SUBMIT_STATS|DRM_SCHED_PUSH_STATS|DRM_SCHED_RUN_JOB_STATS|GPA2HPA|gles-compute-smoke rc|mismatch|Killed|Oops|Unable to handle|job timeout|Initialized panthor|CSF FW' "${vm_log}" || true
	} >"${vm_summary}"

	if [[ "${suffix}" == "count${COUNT}" ]]; then
		cp -f "${vm_log}" "${LOG_DIR}/vm.log"
		cp -f "${vm_summary}" "${LOG_DIR}/vm-summary.txt"
		cp -f "${vm_dmesg_before}" "${LOG_DIR}/vm-dmesg-before.txt"
		cp -f "${vm_dmesg_after}" "${LOG_DIR}/vm-dmesg-after.txt"
		cp -f "${vm_interrupts_before}" "${LOG_DIR}/vm-interrupts-before.txt"
		cp -f "${vm_interrupts_after}" "${LOG_DIR}/vm-interrupts-after.txt"
	fi
}

switch_host_to_panthor() {
	local driver

	log "Switching host GPU from pmthor to panthor"
	pkill -x firecracker 2>/dev/null || true
	sleep 1

	{
		echo "before_driver=$(current_gpu_driver)"
		ls -l /dev/pmthor /dev/dri 2>&1 || true
	} >"${LOG_DIR}/host-switch.log"

	driver=$(current_gpu_driver)
	if [[ "${driver}" == "pmthor" ]]; then
		echo "${GPU_DEV}" > /sys/bus/platform/drivers/pmthor/unbind 2>>"${LOG_DIR}/host-switch.log"
		sleep 1
	elif [[ "${driver}" != "panthor" && "${driver}" != "none" ]]; then
		echo "unexpected current driver: ${driver}" >>"${LOG_DIR}/host-switch.log"
	fi

	modprobe panthor >>"${LOG_DIR}/host-switch.log" 2>&1 || true
	driver=$(current_gpu_driver)
	if [[ "${driver}" == "none" ]]; then
		echo "${GPU_DEV}" > /sys/bus/platform/drivers/panthor/bind 2>>"${LOG_DIR}/host-switch.log" || true
		sleep 1
	fi

	{
		echo "after_driver=$(current_gpu_driver)"
		ls -l /dev/pmthor /dev/dri 2>&1 || true
	} >>"${LOG_DIR}/host-switch.log"

	if [[ "$(current_gpu_driver)" != "panthor" ]]; then
		write_failure_result "failed to bind host GPU to panthor; see host-switch.log"
		exit 1
	fi
	wait_for_drm_node || {
		write_failure_result "host panthor bound but no /dev/dri node appeared"
		exit 1
	}
}

run_host_workload() {
	local count="$1"
	local suffix="$2"
	local host_log="${LOG_DIR}/host-${suffix}.log"
	local host_summary="${LOG_DIR}/host-${suffix}-summary.txt"
	local host_cmd=()

	if [[ "${RUN_HOST}" -ne 1 ]]; then
		return 0
	fi

	switch_host_to_panthor

	log "Running host direct workload without tracing"
	export XDG_RUNTIME_DIR=/tmp/runtime-root
	mkdir -p "${XDG_RUNTIME_DIR}"
	chmod 700 "${XDG_RUNTIME_DIR}"
	export LIBGL_ALWAYS_SOFTWARE=0
	export MESA_DEBUG="${MESA_DEBUG:-context}"

	if [[ "${HOST_USE_ROOTFS_USERSPACE}" -eq 1 ]]; then
		mount_host_rootfs_userspace
		host_cmd=(env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin XDG_RUNTIME_DIR=/tmp/runtime-root LIBGL_ALWAYS_SOFTWARE=0 MESA_DEBUG=context chroot "${HOST_ROOTFS_MNT}" /bin/sh -c "mkdir -p /tmp/runtime-root; chmod 700 /tmp/runtime-root; exec /root/gles-compute-smoke ${PERF_ARGS[*]}")
	else
		host_cmd=("${SMOKE_BIN}" "${PERF_ARGS[@]}")
	fi

	set +e
	timeout -k 5 "${HOST_TIMEOUT}" "${host_cmd[@]}" >"${host_log}" 2>&1
	HOST_STATUS=$?
	set -e

	{
		echo "count=${count}"
		echo "iterations=${COUNT_ITERATIONS}"
		echo "warmup=${COUNT_WARMUP}"
		echo "status=${HOST_STATUS}"
		grep -aE 'COMPUTE_CHECK|GL_RENDERER|GL_VERSION|PERF_|DRM_NODE|GBM_BACKEND|mismatch|software renderer|GL error|EGL_.*failed' "${host_log}" || true
	} >"${host_summary}"

	if [[ "${suffix}" == "count${COUNT}" ]]; then
		cp -f "${host_log}" "${LOG_DIR}/host.log"
		cp -f "${host_summary}" "${LOG_DIR}/host-summary.txt"
	fi

	unmount_host_rootfs_userspace
	restore_pmthor
}

get_phase_avg() {
	local file="$1"
	local phase="$2"

	[[ -f "${file}" ]] || return 0
	awk -v phase="${phase}" '
		$1 == "PERF_PHASE_US" {
			name = ""; avg = "";
			for (i = 1; i <= NF; i++) {
				split($i, kv, "=");
				if (kv[1] == "name")
					name = kv[2];
				else if (kv[1] == "avg")
					avg = kv[2];
			}
			if (name == phase) {
				gsub(/\r/, "", avg);
				print avg;
				exit;
			}
		}
	' "${file}" 2>/dev/null
}

get_scalar() {
	local file="$1"
	local key="$2"

	[[ -f "${file}" ]] || return 0
	awk -F= -v key="${key}" '$1 == key {gsub(/\r/, "", $2); print $2; exit}' "${file}" 2>/dev/null
}

get_iter_avg() {
	local file="$1"
	local avg

	[[ -f "${file}" ]] || return 0
	avg=$(awk '
		$1 == "PERF_ITER_US" {
			for (i = 1; i <= NF; i++) {
				split($i, kv, "=");
				if (kv[1] == "avg") {
					gsub(/\r/, "", kv[2]);
					print kv[2];
					exit;
				}
			}
		}
	' "${file}" 2>/dev/null)
	if [[ -n "${avg}" ]]; then
		printf '%s\n' "${avg}"
		return 0
	fi

	get_phase_avg "${file}" iter_total
}

sum_values() {
	awk '
		BEGIN {
			sum = 0;
			valid = 1;
			for (i = 1; i < ARGC; i++) {
				if (ARGV[i] == "" || ARGV[i] == "NA") {
					valid = 0;
				} else {
					sum += ARGV[i];
				}
			}
			if (valid)
				printf "%.2f", sum;
			else
				printf "NA";
			exit;
		}
	' "$@"
}

host_vm_ratio_values() {
	awk -v vm="$1" -v host="$2" '
		BEGIN {
			if (vm == "" || host == "" || vm == "NA" || host == "NA" || vm + 0 == 0)
				printf "NA";
			else
				printf "%.3f", host / vm;
			exit;
		}
	'
}

workload_label() {
	case "$1" in
	1048576)
		printf '4 MiB'
		;;
	4194304)
		printf '16 MiB'
		;;
	16777216)
		printf '64 MiB'
		;;
	*)
		awk -v count="$1" 'BEGIN { printf "%.2f MiB", count * 4.0 / 1048576.0 }'
		;;
	esac
}

host_phase_share_ref() {
	case "$1" in
	1048576)
		printf '79.0/6.7/14.4/0.07'
		;;
	4194304)
		printf '81.0/2.0/16.3/0.02'
		;;
	16777216)
		printf '80.0/0.75/19.3/0.01'
		;;
	*)
		printf 'NA'
		;;
	esac
}

count_list() {
	if [[ -n "${COUNT_SWEEP}" ]]; then
		printf '%s\n' "${COUNT_SWEEP}" | tr ',' '\n' | awk 'NF {print $1}'
	else
		printf '%s\n' "${COUNT}"
	fi
}

write_sweep_result() {
	local overall=PASS restored_driver host_userspace
	local count suffix vm_log host_log vm_summary host_summary
	local vm_iter host_iter vm_meta host_meta vm_submit host_submit vm_wait host_wait vm_map host_map
	local count_iterations
	local vm_renderer= host_renderer= vm_version= host_version=

	restored_driver=$(awk -F= '$1 == "driver" {print $2; exit}' "${LOG_DIR}/restore-status.txt" 2>/dev/null || true)
	if [[ "${RUN_HOST}" -eq 1 && "${restored_driver}" != "pmthor" ]]; then
		overall=FAIL
	fi
	host_userspace=host-system
	if [[ "${HOST_USE_ROOTFS_USERSPACE}" -eq 1 ]]; then
		host_userspace=vm-rootfs
	fi

	{
		echo "OpenGL ES compute smoke host-vs-passthrough count sweep result"
		echo "Run ID: ${RUN_ID}"
		echo "Timestamp: $(date -Is)"
		echo "Remote log dir: ${LOG_DIR}"
		echo "Default iterations: ${ITERATIONS}"
		echo "Default warmup: ${WARMUP}"
		echo "Large-count threshold: ${LARGE_COUNT_THRESHOLD}"
		echo "Large-count iterations: ${LARGE_COUNT_ITERATIONS}"
		echo "Large-count warmup: ${LARGE_COUNT_WARMUP}"
		echo "Counts: $(count_list | paste -sd, -)"
		echo "Tracing: disabled; no strace/ftrace/bpftrace/perf-record wrapper is used"
		echo "Host userspace: ${host_userspace}"
		echo "VM runner: ${PASSTHROUGH_VM_RUNNER}"
		echo "VM config: ${PASSTHROUGH_VM_CONFIG}"
		echo "VM active config: ${ACTIVE_VM_CONFIG}"
		echo "VM huge pages 2M: ${VM_HUGE_PAGES_2M}"
		echo "VM taskset CPU: ${VM_TASKSET_CPU:-}"
		echo "ALU iters: ${ALU_ITERS}"
		echo "pmthor IRQ affinity CPU: ${PMTHOR_IRQ_AFFINITY_CPU:-}"
			echo "pmthor IRQ affinity labels: ${PMTHOR_IRQ_AFFINITY_LABELS}"
			echo "pmthor IRQ stats: ${PMTHOR_IRQ_STATS}"
			echo "Guest Panthor IRQ stats: ${GUEST_PANTHOR_IRQ_STATS}"
				echo "Guest Panthor submit stats: ${GUEST_PANTHOR_SUBMIT_STATS}"
				echo "Guest Panthor page-table timing: ${GUEST_PANTHOR_PT_TIMING}"
				echo "Rootfs: ${ROOTFS_PATH}"
		echo
		echo "Correctness is checked only as a post-loop PASS/FAIL sanity check and is excluded from PERF_ITER_US/iter_total."
		echo "Performance metric: host/vm = Host elapsed time / VM elapsed time; closer to 1.000 means passthrough is closer to host."
		echo "Phase groups: metadata=cpu_prepare+buffer_upload; submit=dispatch_call; completion=memory_barrier+map_wait; map_unmap=unmap."
		echo "Host phase share reference is fixed from stable Host baselines and is not recalculated for every report."
		echo
		echo "== Formal Host/VM performance ratio table =="
		echo "| **Workload** | **iter** | **total** | **metadata** | **submit** | **completion** | **map_unmap** | **Host phase share ref** |"
		echo "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"

		while read -r count; do
			[[ -n "${count}" ]] || continue
			suffix="count${count}"
			vm_log="${LOG_DIR}/vm-${suffix}.log"
			host_log="${LOG_DIR}/host-${suffix}.log"
			vm_summary="${LOG_DIR}/vm-${suffix}-summary.txt"
			host_summary="${LOG_DIR}/host-${suffix}-summary.txt"

			if [[ "${RUN_VM}" -eq 1 ]]; then
				if ! grep -qa 'GPU_SMOKE_RESULT=PASS' "${vm_log}" || ! grep -qa 'COMPUTE_CHECK=PASS' "${vm_log}"; then
					overall=FAIL
				fi
			fi
			if [[ "${RUN_HOST}" -eq 1 ]]; then
				if ! grep -qa 'COMPUTE_CHECK=PASS' "${host_log}"; then
					overall=FAIL
				fi
			fi

			if [[ -z "${vm_renderer}" ]]; then
				vm_renderer=$(get_scalar "${vm_log}" GL_RENDERER || true)
			fi
			if [[ -z "${host_renderer}" ]]; then
				host_renderer=$(get_scalar "${host_log}" GL_RENDERER || true)
			fi
			if [[ -z "${vm_version}" ]]; then
				vm_version=$(get_scalar "${vm_log}" GL_VERSION || true)
			fi
			if [[ -z "${host_version}" ]]; then
				host_version=$(get_scalar "${host_log}" GL_VERSION || true)
			fi

			count_iterations=$(awk -F= '$1 == "iterations" {gsub(/\r/, "", $2); print $2; exit}' "${vm_summary}" 2>/dev/null || true)
			if [[ -z "${count_iterations}" ]]; then
				count_iterations=$(awk -F= '$1 == "iterations" {gsub(/\r/, "", $2); print $2; exit}' "${host_summary}" 2>/dev/null || true)
			fi

			vm_iter=$(get_iter_avg "${vm_log}" || true)
			host_iter=$(get_iter_avg "${host_log}" || true)
			vm_meta=$(sum_values "$(get_phase_avg "${vm_log}" cpu_prepare)" "$(get_phase_avg "${vm_log}" buffer_upload)")
			host_meta=$(sum_values "$(get_phase_avg "${host_log}" cpu_prepare)" "$(get_phase_avg "${host_log}" buffer_upload)")
			vm_submit=$(sum_values "$(get_phase_avg "${vm_log}" dispatch_call)")
			host_submit=$(sum_values "$(get_phase_avg "${host_log}" dispatch_call)")
			vm_wait=$(sum_values "$(get_phase_avg "${vm_log}" memory_barrier)" "$(get_phase_avg "${vm_log}" map_wait)")
			host_wait=$(sum_values "$(get_phase_avg "${host_log}" memory_barrier)" "$(get_phase_avg "${host_log}" map_wait)")
			vm_map=$(sum_values "$(get_phase_avg "${vm_log}" unmap)")
			host_map=$(sum_values "$(get_phase_avg "${host_log}" unmap)")

			printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' \
				"$(workload_label "${count}")" \
				"${count_iterations:-NA}" \
				"$(host_vm_ratio_values "${vm_iter:-NA}" "${host_iter:-NA}")" \
				"$(host_vm_ratio_values "${vm_meta}" "${host_meta}")" \
				"$(host_vm_ratio_values "${vm_submit}" "${host_submit}")" \
				"$(host_vm_ratio_values "${vm_wait}" "${host_wait}")" \
				"$(host_vm_ratio_values "${vm_map}" "${host_map}")" \
				"$(host_phase_share_ref "${count}")"

			echo "count=${count} vm_summary=${vm_summary} host_summary=${host_summary}" >>"${LOG_DIR}/sweep-files.txt"
		done < <(count_list)

		echo
		echo "VM renderer: ${vm_renderer:-NA}"
		echo "VM GL version: ${vm_version:-NA}"
		echo "Host renderer: ${host_renderer:-NA}"
		echo "Host GL version: ${host_version:-NA}"
		echo "Restored GPU driver: ${restored_driver:-NA}"
		echo "Diagnostic stats remain in per-count summaries/log files and are not part of the formal performance table."
		echo
		echo "== Per-count log files =="
		sed -n '1,200p' "${LOG_DIR}/sweep-files.txt" 2>/dev/null || true
		echo
		echo "RESULT: ${overall}"
	} >"${LOG_DIR}/result"
	cat "${LOG_DIR}/result"

	if [[ "${overall}" == "PASS" ]]; then
		return 0
	fi
	return 1
}

cd "${REMOTE_BINS}"
validate_workload_options
install_remote_deps
build_smoke
prepare_hugepages_config
write_preflight
restore_pmthor
while read -r sweep_count; do
	[[ -n "${sweep_count}" ]] || continue
	COUNT="${sweep_count}"
	select_count_iterations "${COUNT}"
	suffix="count${COUNT}"
	update_rootfs "${COUNT}"
	run_vm_workload "${COUNT}" "${suffix}"
	restore_rootfs_env
	run_host_workload "${COUNT}" "${suffix}"
done < <(count_list)
write_sweep_result
REMOTE_SCRIPT
	remote_status=$?
	set -e

	return "${remote_status}"
}

fetch_logs() {
	log "Fetching logs to ${SFTP_LOG_ROOT}/passthrough/perf/${RUN_ID}"
	mkdir -p "${SFTP_LOG_ROOT}/passthrough/perf"
	rsync_remote -av --info=stats2,name1 \
		"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_LOG_ROOT}/passthrough/perf/${RUN_ID}/" \
		"${SFTP_LOG_ROOT}/passthrough/perf/${RUN_ID}/" || true
}

require_cmd ssh
require_cmd rsync
require_cmd setsid

[[ -d "${SFTP_ROOT}" ]] || die "missing SFTP root: ${SFTP_ROOT}"

if [[ "${SYNC_TO_REMOTE}" -eq 1 ]]; then
	sync_to_remote
fi

remote_status=0
run_remote_perf || remote_status=$?

if [[ "${FETCH_LOGS}" -eq 1 ]]; then
	fetch_logs
fi

result="${SFTP_LOG_ROOT}/passthrough/perf/${RUN_ID}/result"
if [[ -f "${result}" ]]; then
	log "Result summary"
	sed -n '1,260p' "${result}"
	echo
	echo "Local logs: ${SFTP_LOG_ROOT}/passthrough/perf/${RUN_ID}"
fi

exit "${remote_status}"
