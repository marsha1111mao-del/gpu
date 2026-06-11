#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SFTP_ROOT=${SFTP_ROOT:-"${ROOT_DIR}/GPU-SFTP"}
SFTP_BINS=${SFTP_BINS:-"${SFTP_ROOT}/firecracker-bins"}
SFTP_LOG_ROOT=${SFTP_LOG_ROOT:-"${SFTP_ROOT}/log"}

REMOTE_HOST=${REMOTE_HOST:-192.168.31.18}
REMOTE_USER=${REMOTE_USER:-root}
REMOTE_PASS=${REMOTE_PASS:-root}
REMOTE_ROOT=${REMOTE_ROOT:-/root/GPU-SFTP}
REMOTE_BINS=${REMOTE_BINS:-"${REMOTE_ROOT}/firecracker-bins"}
REMOTE_LOG_ROOT=${REMOTE_LOG_ROOT:-"${REMOTE_ROOT}/log"}

RUN_ID=${RUN_ID:-2client-direct-eventfd-$(date +%Y%m%d-%H%M%S)}
SYNC_TO_REMOTE=1
FETCH_LOGS=1
CLEAN_REMOTE_PROCS=1
SYNC_ROOTFS=0
GLES_COMPUTE_SMOKE=0
GLES_REMOTE_BUILD=${GLES_REMOTE_BUILD:-1}
GLES_SMOKE_ARGS=${GLES_SMOKE_ARGS:-"--count 64"}
GLES_CLIENT_MEM_MIB=${GLES_CLIENT_MEM_MIB:-384}
GLES_PROXY_MEM_MIB=${GLES_PROXY_MEM_MIB:-384}
GLES_CLIENT_VCPUS=${GLES_CLIENT_VCPUS:-1}
GLES_PROXY_VCPUS=${GLES_PROXY_VCPUS:-1}
GLES_CLIENT_START_GAP_SEC=${GLES_CLIENT_START_GAP_SEC:-0}
GLES_SYNC_START_DELAY_SEC=${GLES_SYNC_START_DELAY_SEC:-0}
GLES_MIN_HOST_AVAILABLE_MIB=${GLES_MIN_HOST_AVAILABLE_MIB:-auto}
GLES_PROXY_PANTHOR_STATS=${GLES_PROXY_PANTHOR_STATS:-0}
GLES_CLIENT_BO_MMAP_CACHED=${GLES_CLIENT_BO_MMAP_CACHED:-0}
GLES_HOST_ONLINE_CPUS=${GLES_HOST_ONLINE_CPUS:-}
GLES_BROKER_CPUS=${GLES_BROKER_CPUS:-}
GLES_PROXY_CPUS=${GLES_PROXY_CPUS:-}
GLES_CLIENT0_CPUS=${GLES_CLIENT0_CPUS:-}
GLES_CLIENT1_CPUS=${GLES_CLIENT1_CPUS:-}
GLES_PANTHOR_SCHED_TICK_MS=${GLES_PANTHOR_SCHED_TICK_MS:-0}
GLES_PANTHOR_SCHED_HIGHPRI_WQ=${GLES_PANTHOR_SCHED_HIGHPRI_WQ:-0}
GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS=${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS:-0}

usage() {
	cat <<EOF
Usage: $(basename "$0") [options]

Run an isolated experiment with one proxy VM and two client VMs.
This uses firecracker-bins/configs/shared/vmshm-2client and does not overwrite
the existing single-client config directory.

Options:
  --skip-sync              Do not rsync GPU-SFTP to the remote host
  --skip-fetch-logs        Do not rsync this run's logs back from the remote host
  --no-clean-remote-procs  Do not pkill existing firecracker/vmshm-broker first
  --sync-rootfs            Include base rootfs images in local-to-remote
                           rsync. Normal runs reuse the remote base Panfrost
                           rootfs and inject the current GLES payload by
                           loop-mounting the image before VM launch.
  --gles-compute-smoke     Boot both shared clients with the base Panfrost
                           rootfs after injecting the GLES compute payload
                           and run
                           /root/gpu-smoke.sh correctness/perf smoke
  --skip-gles-remote-build
                           In GLES mode, reuse an existing executable
                           firecracker-bins/bin/gles-compute-smoke instead
                           of compiling it on the remote host
  --gles-smoke-args ARGS   Arguments passed to /root/gpu-smoke.sh in GLES mode
  --gles-client-mem-mib N  Memory size for each GLES client VM. Default: ${GLES_CLIENT_MEM_MIB}
  --gles-proxy-mem-mib N   Memory size for the GLES proxy VM. Default: ${GLES_PROXY_MEM_MIB}
  --gles-client-vcpus N     vCPU count for each GLES client VM. Default: ${GLES_CLIENT_VCPUS}
  --gles-proxy-vcpus N      vCPU count for the GLES proxy VM. Default: ${GLES_PROXY_VCPUS}
  --gles-client-start-gap-sec N
                           In GLES mode, 0 starts client1 immediately after
                           client0; N>0 waits for client0 DRM frontend and then
                           sleeps N seconds. Default: ${GLES_CLIENT_START_GAP_SEC}
  --gles-sync-start-delay-sec N
                           In GLES mode, pass both clients the same future host
                           epoch before running /root/gles-compute-smoke.
                           0 disables synchronized perf-loop start. Default: ${GLES_SYNC_START_DELAY_SEC}
  --gles-min-host-available-mib N|auto
                           Abort GLES mode before launching Firecracker when
                           host MemAvailable is below N MiB. Default: ${GLES_MIN_HOST_AVAILABLE_MIB}
                           Use 0 to disable the guard.
  --gles-proxy-panthor-stats
                           Enable proxy Panthor/RPC and client vmshm RPC
                           timing stats for diagnostic runs.
  --gles-client-bo-mmap-cached
                           In GLES mode, boot shared clients with
                           panthor_client.bo_mmap_cached=1 so BO payload
                           mmap uses cached WB instead of write-combine.
  --gles-host-online-cpus LIST
                           Diagnostic mode: temporarily online host CPUs in
                           LIST before launching GLES VMs, then restore CPUs
                           that were offline before the run.
  --gles-broker-cpus LIST  Diagnostic mode: run vmshm-broker with taskset -c LIST.
  --gles-proxy-cpus LIST   Diagnostic mode: run proxy Firecracker with taskset -c LIST.
  --gles-client0-cpus LIST Diagnostic mode: run client0 Firecracker with taskset -c LIST.
  --gles-client1-cpus LIST Diagnostic mode: run client1 Firecracker with taskset -c LIST.
  --gles-panthor-sched-tick-ms N
                           Diagnostic mode: set Panthor CSG scheduler tick
                           period in the proxy VM. 0 keeps driver default.
  --gles-panthor-sched-highpri-wq
                           Diagnostic mode: use a high-priority Panthor
                           scheduler workqueue in the proxy VM.
  --gles-panthor-proxy-group-core-partitions N
                           Experimental mode: ask panthor-proxy to partition
                           each shared client's group shader core mask across
                           N partitions. 0 keeps the default Panthor/Mesa
                           group masks.
  --run-id ID              Use a fixed run log directory name
  -h, --help               Show this help

Environment overrides:
  SFTP_ROOT SFTP_BINS SFTP_LOG_ROOT
  REMOTE_HOST REMOTE_USER REMOTE_PASS REMOTE_ROOT REMOTE_BINS REMOTE_LOG_ROOT RUN_ID
  GLES_REMOTE_BUILD

Default remote is ${REMOTE_USER}@${REMOTE_HOST}, logs go under:
  remote: ${REMOTE_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}
  local:  ${SFTP_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--skip-sync)
		SYNC_TO_REMOTE=0
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
	--gles-compute-smoke)
		GLES_COMPUTE_SMOKE=1
		;;
	--skip-gles-remote-build)
		GLES_REMOTE_BUILD=0
		;;
	--gles-smoke-args)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-smoke-args requires an argument" >&2
			exit 2
		fi
		GLES_SMOKE_ARGS=$1
		;;
	--gles-client-mem-mib)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-client-mem-mib requires an argument" >&2
			exit 2
		fi
		GLES_CLIENT_MEM_MIB=$1
		;;
	--gles-proxy-mem-mib)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-proxy-mem-mib requires an argument" >&2
			exit 2
		fi
		GLES_PROXY_MEM_MIB=$1
		;;
	--gles-client-vcpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-client-vcpus requires an argument" >&2
			exit 2
		fi
		GLES_CLIENT_VCPUS=$1
		;;
	--gles-proxy-vcpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-proxy-vcpus requires an argument" >&2
			exit 2
		fi
		GLES_PROXY_VCPUS=$1
		;;
	--gles-client-start-gap-sec)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-client-start-gap-sec requires an argument" >&2
			exit 2
		fi
		GLES_CLIENT_START_GAP_SEC=$1
		;;
	--gles-sync-start-delay-sec)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-sync-start-delay-sec requires an argument" >&2
			exit 2
		fi
		GLES_SYNC_START_DELAY_SEC=$1
		;;
	--gles-min-host-available-mib)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-min-host-available-mib requires an argument" >&2
			exit 2
		fi
		GLES_MIN_HOST_AVAILABLE_MIB=$1
		;;
	--gles-proxy-panthor-stats)
		GLES_PROXY_PANTHOR_STATS=1
		;;
	--gles-client-bo-mmap-cached)
		GLES_CLIENT_BO_MMAP_CACHED=1
		;;
	--gles-host-online-cpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-host-online-cpus requires an argument" >&2
			exit 2
		fi
		GLES_HOST_ONLINE_CPUS=$1
		;;
	--gles-broker-cpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-broker-cpus requires an argument" >&2
			exit 2
		fi
		GLES_BROKER_CPUS=$1
		;;
	--gles-proxy-cpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-proxy-cpus requires an argument" >&2
			exit 2
		fi
		GLES_PROXY_CPUS=$1
		;;
	--gles-client0-cpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-client0-cpus requires an argument" >&2
			exit 2
		fi
		GLES_CLIENT0_CPUS=$1
		;;
	--gles-client1-cpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-client1-cpus requires an argument" >&2
			exit 2
		fi
		GLES_CLIENT1_CPUS=$1
		;;
	--gles-panthor-sched-tick-ms)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-panthor-sched-tick-ms requires an argument" >&2
			exit 2
		fi
		GLES_PANTHOR_SCHED_TICK_MS=$1
		;;
	--gles-panthor-sched-highpri-wq)
		GLES_PANTHOR_SCHED_HIGHPRI_WQ=1
		;;
	--gles-panthor-proxy-group-core-partitions)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-panthor-proxy-group-core-partitions requires an argument" >&2
			exit 2
		fi
		GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS=$1
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

install_configs() {
	local installer="${SFTP_BINS}/scripts/shared/vmshm-2client/install-vmshm-irq-configs-2client.sh"

	[[ -x "${installer}" ]] || die "missing executable installer: ${installer}"
	log "Installing isolated 2-client vmshm configs under SFTP"
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
	local gles_compute_smoke_q gles_remote_build_q gles_smoke_args_q
	local gles_client_mem_mib_q gles_proxy_mem_mib_q
	local gles_client_vcpus_q gles_proxy_vcpus_q
	local gles_client_start_gap_sec_q
	local gles_sync_start_delay_sec_q
	local gles_min_host_available_mib_q gles_proxy_panthor_stats_q
	local gles_client_bo_mmap_cached_q
	local gles_host_online_cpus_q gles_broker_cpus_q gles_proxy_cpus_q
	local gles_client0_cpus_q gles_client1_cpus_q
	local gles_panthor_sched_tick_ms_q gles_panthor_sched_highpri_wq_q
	local gles_panthor_proxy_group_core_partitions_q

	run_id_q=$(quote "${RUN_ID}")
	remote_root_q=$(quote "${REMOTE_ROOT}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	clean_q=$(quote "${CLEAN_REMOTE_PROCS}")
	gles_compute_smoke_q=$(quote "${GLES_COMPUTE_SMOKE}")
	gles_remote_build_q=$(quote "${GLES_REMOTE_BUILD}")
	gles_smoke_args_q=$(quote "${GLES_SMOKE_ARGS}")
	gles_client_mem_mib_q=$(quote "${GLES_CLIENT_MEM_MIB}")
	gles_proxy_mem_mib_q=$(quote "${GLES_PROXY_MEM_MIB}")
	gles_client_vcpus_q=$(quote "${GLES_CLIENT_VCPUS}")
	gles_proxy_vcpus_q=$(quote "${GLES_PROXY_VCPUS}")
	gles_client_start_gap_sec_q=$(quote "${GLES_CLIENT_START_GAP_SEC}")
	gles_sync_start_delay_sec_q=$(quote "${GLES_SYNC_START_DELAY_SEC}")
	gles_min_host_available_mib_q=$(quote "${GLES_MIN_HOST_AVAILABLE_MIB}")
	gles_proxy_panthor_stats_q=$(quote "${GLES_PROXY_PANTHOR_STATS}")
	gles_client_bo_mmap_cached_q=$(quote "${GLES_CLIENT_BO_MMAP_CACHED}")
	gles_host_online_cpus_q=$(quote "${GLES_HOST_ONLINE_CPUS}")
	gles_broker_cpus_q=$(quote "${GLES_BROKER_CPUS}")
	gles_proxy_cpus_q=$(quote "${GLES_PROXY_CPUS}")
	gles_client0_cpus_q=$(quote "${GLES_CLIENT0_CPUS}")
	gles_client1_cpus_q=$(quote "${GLES_CLIENT1_CPUS}")
	gles_panthor_sched_tick_ms_q=$(quote "${GLES_PANTHOR_SCHED_TICK_MS}")
	gles_panthor_sched_highpri_wq_q=$(quote "${GLES_PANTHOR_SCHED_HIGHPRI_WQ}")
	gles_panthor_proxy_group_core_partitions_q=$(quote "${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS}")

	log "Running remote 2-client vmshm test: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BINS}"
	ssh_remote "RUN_ID=${run_id_q} REMOTE_ROOT=${remote_root_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} CLEAN_REMOTE_PROCS=${clean_q} GLES_COMPUTE_SMOKE=${gles_compute_smoke_q} GLES_REMOTE_BUILD=${gles_remote_build_q} GLES_SMOKE_ARGS=${gles_smoke_args_q} GLES_CLIENT_MEM_MIB=${gles_client_mem_mib_q} GLES_PROXY_MEM_MIB=${gles_proxy_mem_mib_q} GLES_CLIENT_VCPUS=${gles_client_vcpus_q} GLES_PROXY_VCPUS=${gles_proxy_vcpus_q} GLES_CLIENT_START_GAP_SEC=${gles_client_start_gap_sec_q} GLES_SYNC_START_DELAY_SEC=${gles_sync_start_delay_sec_q} GLES_MIN_HOST_AVAILABLE_MIB=${gles_min_host_available_mib_q} GLES_PROXY_PANTHOR_STATS=${gles_proxy_panthor_stats_q} GLES_CLIENT_BO_MMAP_CACHED=${gles_client_bo_mmap_cached_q} GLES_HOST_ONLINE_CPUS=${gles_host_online_cpus_q} GLES_BROKER_CPUS=${gles_broker_cpus_q} GLES_PROXY_CPUS=${gles_proxy_cpus_q} GLES_CLIENT0_CPUS=${gles_client0_cpus_q} GLES_CLIENT1_CPUS=${gles_client1_cpus_q} GLES_PANTHOR_SCHED_TICK_MS=${gles_panthor_sched_tick_ms_q} GLES_PANTHOR_SCHED_HIGHPRI_WQ=${gles_panthor_sched_highpri_wq_q} GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS=${gles_panthor_proxy_group_core_partitions_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_BINS}"
LOG_DIR="${REMOTE_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}"
mkdir -p /run/vmshm "${LOG_DIR}"
GLES_SMOKE_SRC_DIR="${REMOTE_ROOT}/tests/gpu-compute-smoke"
GLES_SMOKE_BIN="${REMOTE_BINS}/bin/gles-compute-smoke"
GLES_CLIENT_RESULT_TIMEOUT_SEC=${GLES_CLIENT_RESULT_TIMEOUT_SEC:-900}
GLES_REMOTE_BUILD=${GLES_REMOTE_BUILD:-1}
GLES_CLIENT_MEM_MIB=${GLES_CLIENT_MEM_MIB:-384}
GLES_PROXY_MEM_MIB=${GLES_PROXY_MEM_MIB:-384}
GLES_CLIENT_VCPUS=${GLES_CLIENT_VCPUS:-1}
GLES_PROXY_VCPUS=${GLES_PROXY_VCPUS:-1}
GLES_CLIENT_START_GAP_SEC=${GLES_CLIENT_START_GAP_SEC:-0}
GLES_SYNC_START_DELAY_SEC=${GLES_SYNC_START_DELAY_SEC:-0}
GLES_MIN_HOST_AVAILABLE_MIB=${GLES_MIN_HOST_AVAILABLE_MIB:-auto}
GLES_PROXY_PANTHOR_STATS=${GLES_PROXY_PANTHOR_STATS:-0}
GLES_CLIENT_BO_MMAP_CACHED=${GLES_CLIENT_BO_MMAP_CACHED:-0}
GLES_HOST_ONLINE_CPUS=${GLES_HOST_ONLINE_CPUS:-}
GLES_BROKER_CPUS=${GLES_BROKER_CPUS:-}
GLES_PROXY_CPUS=${GLES_PROXY_CPUS:-}
GLES_CLIENT0_CPUS=${GLES_CLIENT0_CPUS:-}
GLES_CLIENT1_CPUS=${GLES_CLIENT1_CPUS:-}
GLES_PANTHOR_SCHED_TICK_MS=${GLES_PANTHOR_SCHED_TICK_MS:-0}
GLES_PANTHOR_SCHED_HIGHPRI_WQ=${GLES_PANTHOR_SCHED_HIGHPRI_WQ:-0}
GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS=${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS:-0}
GLES_SMOKE_START_EPOCH=0
GLES_SMOKE_START_UPTIME_MS=0
SMOKE_MNT=""
GLES_BROKER_CONFIG="${LOG_DIR}/broker-config.toml"
GLES_CPU_RESTORE_FILE="${LOG_DIR}/cpu-online.restore"

gles_smoke_count() {
	local -a argv
	local i

	read -r -a argv <<<"${GLES_SMOKE_ARGS}"
	for ((i = 0; i < ${#argv[@]}; i++)); do
		if [[ "${argv[i]}" == "--count" && $((i + 1)) -lt ${#argv[@]} ]]; then
			printf '%s\n' "${argv[i + 1]}"
			return 0
		fi
	done

	printf '\n'
}

gles_object_window_mib_for_count() {
	local count="$1"

	case "${count}" in
	16777216)
		printf '224\n'
		;;
	8388608)
		printf '128\n'
		;;
	4194304)
		printf '96\n'
		;;
	1048576)
		printf '64\n'
		;;
	*)
		printf '224\n'
		;;
	esac
}

GLES_SMOKE_COUNT=$(gles_smoke_count)
GLES_OBJECT_WINDOW_MIB=$(gles_object_window_mib_for_count "${GLES_SMOKE_COUNT}")
GLES_OBJECT_WINDOW_BYTES=$((GLES_OBJECT_WINDOW_MIB * 1024 * 1024))

if [[ "${CLEAN_REMOTE_PROCS}" == "1" ]]; then
	pkill -x firecracker 2>/dev/null || true
	pkill -x vmshm-broker 2>/dev/null || true
	sleep 1
fi
rm -f /run/vmshm/*.sock

mem_available_mib() {
	awk '/^MemAvailable:/ {printf "%d\n", $2 / 1024; found=1} END {if (!found) print 0}' /proc/meminfo 2>/dev/null
}

write_mem_snapshot() {
	local label="$1"
	local out="${LOG_DIR}/preflight.txt"

	{
		echo
		echo "== ${label} =="
		echo "ts=$(date -Is)"
		echo "mem_available_mib=$(mem_available_mib)"
		free -m 2>/dev/null || true
		echo "-- firecracker/vmshm-broker rss --"
		ps -eo pid,comm,rss,args 2>/dev/null |
			awk '$2=="firecracker"||$2=="vmshm-broker"{print}' || true
	} >>"${out}"
}

expand_cpu_list() {
	local list="$1"
	local item start end cpu

	for item in ${list//,/ }; do
		[[ -n "${item}" ]] || continue
		if [[ "${item}" =~ ^([0-9]+)-([0-9]+)$ ]]; then
			start="${BASH_REMATCH[1]}"
			end="${BASH_REMATCH[2]}"
			if ((start > end)); then
				return 1
			fi
			for ((cpu = start; cpu <= end; cpu++)); do
				printf '%s\n' "${cpu}"
			done
		elif [[ "${item}" =~ ^[0-9]+$ ]]; then
			printf '%s\n' "${item}"
		else
			return 1
		fi
	done
}

host_online_cpus() {
	cat /sys/devices/system/cpu/online 2>/dev/null || echo unknown
}

write_affinity_snapshot() {
	local label="$1"

	{
		echo
		echo "== ${label} =="
		echo "ts=$(date -Is)"
		echo "online_cpus=$(host_online_cpus)"
		echo "requested_online_cpus=${GLES_HOST_ONLINE_CPUS:-}"
		echo "broker_cpus=${GLES_BROKER_CPUS:-}"
		echo "proxy_cpus=${GLES_PROXY_CPUS:-}"
		echo "client0_cpus=${GLES_CLIENT0_CPUS:-}"
		echo "client1_cpus=${GLES_CLIENT1_CPUS:-}"
		echo "-- cpu topology --"
		for c in /sys/devices/system/cpu/cpu[0-9]*; do
			[[ -d "${c}" ]] || continue
			printf "%s online=" "${c##*/}"
			cat "${c}/online" 2>/dev/null || printf "always"
			printf " core="
			cat "${c}/topology/core_id" 2>/dev/null || printf "?"
			printf " cluster="
			cat "${c}/topology/cluster_id" 2>/dev/null || printf "?"
			printf "\n"
		done
	} >>"${LOG_DIR}/affinity.log"
}

restore_host_online_cpus() {
	local cpu

	[[ -f "${GLES_CPU_RESTORE_FILE}" ]] || return 0

	{
		echo
		echo "== restore host cpu online state =="
		echo "ts=$(date -Is)"
		echo "before_restore=$(host_online_cpus)"
	} >>"${LOG_DIR}/affinity.log"

	while read -r cpu; do
		[[ -n "${cpu}" ]] || continue
		if [[ -w "/sys/devices/system/cpu/cpu${cpu}/online" ]]; then
			printf '0\n' >"/sys/devices/system/cpu/cpu${cpu}/online" 2>>"${LOG_DIR}/affinity.log" || true
		fi
	done <"${GLES_CPU_RESTORE_FILE}"

	{
		echo "after_restore=$(host_online_cpus)"
	} >>"${LOG_DIR}/affinity.log"
	rm -f "${GLES_CPU_RESTORE_FILE}"
}

apply_host_online_cpus() {
	local cpu was_online

	: >"${GLES_CPU_RESTORE_FILE}"
	write_affinity_snapshot "before optional host cpu online"

	[[ -n "${GLES_HOST_ONLINE_CPUS}" ]] || return 0

	if ! expand_cpu_list "${GLES_HOST_ONLINE_CPUS}" >/dev/null; then
		echo "invalid GLES_HOST_ONLINE_CPUS=${GLES_HOST_ONLINE_CPUS}" >"${LOG_DIR}/result"
		return 2
	fi

	while read -r cpu; do
		[[ -n "${cpu}" ]] || continue
		if [[ ! -d "/sys/devices/system/cpu/cpu${cpu}" ]]; then
			echo "missing requested host cpu${cpu}" >"${LOG_DIR}/result"
			return 2
		fi
		if [[ ! -e "/sys/devices/system/cpu/cpu${cpu}/online" ]]; then
			continue
		fi
		was_online=$(cat "/sys/devices/system/cpu/cpu${cpu}/online" 2>/dev/null || echo 1)
		if [[ "${was_online}" != "1" ]]; then
			echo "${cpu}" >>"${GLES_CPU_RESTORE_FILE}"
			printf '1\n' >"/sys/devices/system/cpu/cpu${cpu}/online"
		fi
	done < <(expand_cpu_list "${GLES_HOST_ONLINE_CPUS}")

	write_affinity_snapshot "after optional host cpu online"
}

validate_taskset_list() {
	local label="$1"
	local cpus="$2"

	[[ -n "${cpus}" ]] || return 0

	command -v taskset >/dev/null 2>&1 || {
		echo "taskset is required for ${label} affinity" >"${LOG_DIR}/result"
		return 2
	}
	if ! taskset -c "${cpus}" true 2>>"${LOG_DIR}/affinity.log"; then
		echo "invalid ${label} taskset CPU/list: ${cpus}" >"${LOG_DIR}/result"
		return 2
	fi
}

validate_gles_affinity() {
	validate_taskset_list broker "${GLES_BROKER_CPUS}"
	validate_taskset_list proxy "${GLES_PROXY_CPUS}"
	validate_taskset_list client0 "${GLES_CLIENT0_CPUS}"
	validate_taskset_list client1 "${GLES_CLIENT1_CPUS}"
	write_affinity_snapshot "after taskset validation"
}

validate_uint_setting() {
	local label="$1"
	local value="$2"

	if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
		echo "invalid ${label}: ${value}" >"${LOG_DIR}/result"
		return 2
	fi
}

validate_gles_proxy_sched() {
	validate_uint_setting gles_panthor_sched_tick_ms "${GLES_PANTHOR_SCHED_TICK_MS}"
	validate_uint_setting gles_panthor_sched_highpri_wq "${GLES_PANTHOR_SCHED_HIGHPRI_WQ}"
	validate_uint_setting gles_panthor_proxy_group_core_partitions "${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS}"
	validate_uint_setting gles_sync_start_delay_sec "${GLES_SYNC_START_DELAY_SEC}"
	case "${GLES_PANTHOR_SCHED_HIGHPRI_WQ}" in 0|1) ;; *)
		echo "invalid gles_panthor_sched_highpri_wq: ${GLES_PANTHOR_SCHED_HIGHPRI_WQ}" >"${LOG_DIR}/result"
		return 2
		;;
	esac
}

write_launch_command() {
	local label="$1"
	shift

	{
		printf 'launch_%s=' "${label}"
		printf '%q ' "$@"
		printf '\n'
	} >>"${LOG_DIR}/affinity.log"
}

gles_auto_min_available_mib() {
	local object_mib="${GLES_OBJECT_WINDOW_MIB}"
	local comm_mib=64
	local guard_mib=512

	printf '%s\n' $((GLES_PROXY_MEM_MIB + GLES_CLIENT_MEM_MIB * 2 + object_mib + comm_mib + guard_mib))
}

gles_preflight_host_memory() {
	local requested="${GLES_MIN_HOST_AVAILABLE_MIB}"
	local threshold mode available

	[[ "${GLES_COMPUTE_SMOKE}" == "1" ]] || return 0

	if [[ "${requested}" == "auto" ]]; then
		threshold=$(gles_auto_min_available_mib)
		mode=auto
	else
		threshold="${requested}"
		mode=manual
	fi

	if ! [[ "${threshold}" =~ ^[0-9]+$ ]]; then
		echo "invalid GLES_MIN_HOST_AVAILABLE_MIB=${requested}" >"${LOG_DIR}/result"
		return 2
	fi

	write_mem_snapshot "after cleanup"
	available=$(mem_available_mib)

	{
		echo "gles_client_mem_mib=${GLES_CLIENT_MEM_MIB}"
		echo "gles_proxy_mem_mib=${GLES_PROXY_MEM_MIB}"
		echo "gles_client_vcpus=${GLES_CLIENT_VCPUS}"
		echo "gles_proxy_vcpus=${GLES_PROXY_VCPUS}"
		echo "gles_sync_start_delay_sec=${GLES_SYNC_START_DELAY_SEC}"
		echo "gles_object_window_mib=${GLES_OBJECT_WINDOW_MIB}"
		echo "gles_object_window_bytes=${GLES_OBJECT_WINDOW_BYTES}"
		echo "gles_min_host_available_mib=${threshold}"
		echo "gles_min_host_available_mode=${mode}"
		echo "gles_mem_guard_formula=proxy + 2*client + ${GLES_OBJECT_WINDOW_MIB}(object) + 64(comm) + 512(guard)"
		echo "gles_mem_available_mib=${available}"
		echo "gles_host_online_cpus=$(host_online_cpus)"
		echo "gles_host_online_cpus_requested=${GLES_HOST_ONLINE_CPUS:-}"
		echo "gles_broker_cpus=${GLES_BROKER_CPUS:-}"
		echo "gles_proxy_cpus=${GLES_PROXY_CPUS:-}"
		echo "gles_client0_cpus=${GLES_CLIENT0_CPUS:-}"
		echo "gles_client1_cpus=${GLES_CLIENT1_CPUS:-}"
	} >>"${LOG_DIR}/preflight.txt"

	if [[ "${threshold}" -gt 0 && "${available}" -lt "${threshold}" ]]; then
		{
			echo "2-client shared GLES compute smoke result"
			echo "Run ID: ${RUN_ID}"
			echo "Timestamp: $(date -Is)"
			echo "Remote log dir: ${LOG_DIR}"
			echo "GLES compute smoke: ${GLES_COMPUTE_SMOKE}"
			echo "GLES smoke args: ${GLES_SMOKE_ARGS}"
			echo
			echo "== GLES host memory preflight =="
			cat "${LOG_DIR}/preflight.txt"
			echo
			echo "RESULT: PREFLIGHT_FAIL"
		} >"${LOG_DIR}/result"
		return 1
	fi
}

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
	local hz total_ticks voluntary nonvoluntary migrations runtime_ns
	local task task_stat task_rest task_fields task_utime task_stime task_runtime _

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

cleanup_gles_rootfs() {
	if [[ -n "${SMOKE_MNT}" && -d "${SMOKE_MNT}" ]]; then
		umount "${SMOKE_MNT}" 2>/dev/null || true
		rmdir "${SMOKE_MNT}" 2>/dev/null || true
	fi
}

cleanup_gles_run() {
	restore_host_online_cpus
	cleanup_gles_rootfs
}
trap cleanup_gles_run EXIT

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	apply_host_online_cpus
	validate_gles_affinity
	validate_gles_proxy_sched
	gles_preflight_host_memory
fi

build_gles_compute_smoke() {
	if [[ "${GLES_COMPUTE_SMOKE}" != "1" ]]; then
		return 0
	fi

	if [[ "${GLES_REMOTE_BUILD}" != "1" ]]; then
		if [[ ! -x "${GLES_SMOKE_BIN}" ]]; then
			echo "missing executable ${GLES_SMOKE_BIN}; rerun without --skip-gles-remote-build" >&2
			return 1
		fi
		echo "using existing ${GLES_SMOKE_BIN} (GLES_REMOTE_BUILD=0)" >&2
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
	local client_id="$1"
	local comm_socket="$2"
	local dtb_name="$3"
	local rootfs_path="$4"
	local config_out="${LOG_DIR}/${client_id}-gles-compute-config.json"
	local client_stats_args=""
	local client_mmap_args=""
	local sync_start_args=""
	local smoke_arg_tokens

	[[ -f "${rootfs_path}" ]] ||
		{ echo "missing GLES rootfs ${rootfs_path}" >&2; return 1; }
	smoke_arg_tokens=$(gles_smoke_args_tokens)

	if [[ "${GLES_PROXY_PANTHOR_STATS}" == "1" ]]; then
		client_stats_args=" client_comm_vmshm.rpc_stats=1"
	fi
	if [[ "${GLES_CLIENT_BO_MMAP_CACHED}" == "1" ]]; then
		client_mmap_args=" panthor_client.bo_mmap_cached=1"
	fi
	if [[ "${GLES_SMOKE_START_UPTIME_MS}" != "0" ]]; then
		sync_start_args=" gpu_smoke_start_uptime_ms=${GLES_SMOKE_START_UPTIME_MS}"
	elif [[ "${GLES_SMOKE_START_EPOCH}" != "0" ]]; then
		sync_start_args=" gpu_smoke_start_epoch=${GLES_SMOKE_START_EPOCH}"
	fi

	cat >"${config_out}" <<EOF
{
  "boot-source": {
    "kernel_image_path": "${REMOTE_BINS}/kernels/shared/client/Image",
    "boot_args": "console=ttyS0 root=/dev/vda ro rootfstype=ext4 init=/init panic=-1 print-fatal-signals=1 gpu_smoke_args_tokens=${smoke_arg_tokens} gpu_smoke_quiet_console=1 gpu_smoke_after_run=shell${client_stats_args}${client_mmap_args}${sync_start_args}"
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
    "vcpu_count": ${GLES_CLIENT_VCPUS},
    "mem_size_mib": ${GLES_CLIENT_MEM_MIB},
    "cpu_template": null,
    "gpu_passthrough": false,
    "dump_fdt_path": "${REMOTE_ROOT}/artifacts/dtb/${dtb_name}"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-${client_id}",
      "role": "client",
      "guest_phys_addr": "0x30000000",
      "slot": 1,
      "expected_size": ${GLES_OBJECT_WINDOW_BYTES},
      "fdt_node_name": "client-vmshm-manager",
      "fdt_compatible": "client-vmshm-manager"
    },
    {
      "socket_path": "${comm_socket}",
      "name": "vmshm-comm-${client_id}",
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

	printf '%s\n' "${config_out}"
}

prepare_gles_compute_proxy() {
	local config_out="${LOG_DIR}/proxy-gles-compute-config.json"
	local panthor_stats_args=""
	local proxy_sched_args=""

	if [[ "${GLES_PROXY_PANTHOR_STATS}" == "1" ]]; then
		panthor_stats_args=" panthor.submit_stats=1 panthor.job_irq_stats=1 panthor_proxy.rpc_stats=1"
	fi
	if [[ "${GLES_PANTHOR_SCHED_TICK_MS}" != "0" ]]; then
		proxy_sched_args+=" panthor.sched_tick_ms=${GLES_PANTHOR_SCHED_TICK_MS}"
	fi
	if [[ "${GLES_PANTHOR_SCHED_HIGHPRI_WQ}" == "1" ]]; then
		proxy_sched_args+=" panthor.sched_highpri_wq=1"
	fi
	if [[ "${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS}" != "0" ]]; then
		proxy_sched_args+=" panthor_proxy.group_core_partitions=${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS}"
	fi

	cat >"${config_out}" <<EOF
{
  "boot-source": {
    "kernel_image_path": "${REMOTE_BINS}/kernels/shared/proxy/Image",
    "boot_args": "console=ttyS0 root=/dev/vda rw rootfstype=ext4 init=/bin/sh${panthor_stats_args}${proxy_sched_args}"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "${REMOTE_BINS}/rootfs/rootfs.ext2",
      "is_root_device": false,
      "is_read_only": false
    }
  ],
  "machine-config": {
    "vcpu_count": ${GLES_PROXY_VCPUS},
    "mem_size_mib": ${GLES_PROXY_MEM_MIB},
    "cpu_template": null,
    "gpu_passthrough": true,
    "dump_fdt_path": "${REMOTE_ROOT}/artifacts/dtb/vmshm-2client-proxy-gles-${RUN_ID}.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x30000000",
      "slot": 1,
      "expected_size": ${GLES_OBJECT_WINDOW_BYTES},
      "fdt_node_name": "proxy-vmshm-manager",
      "fdt_compatible": "proxy-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm-client0.sock",
      "name": "vmshm-comm-client0-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "proxy_comm_vmshm_client0",
      "fdt_compatible": "proxy_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f100000",
        "doorbell_size": "0x1000",
        "irq": 81
      }
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm-client1.sock",
      "name": "vmshm-comm-client1-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x26000000",
      "slot": 3,
      "expected_size": 33554432,
      "fdt_node_name": "proxy_comm_vmshm_client1",
      "fdt_compatible": "proxy_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f110000",
        "doorbell_size": "0x1000",
        "irq": 82
      }
    }
  ]
}
EOF

	printf '%s\n' "${config_out}"
}

write_gles_broker_config() {
	cat >"${GLES_BROKER_CONFIG}" <<EOF
[broker]
socket_dir = "/run/vmshm"

[[domains]]
id = "vmshm-object"
socket_path = "/run/vmshm/vmshm-object.sock"
memfd_name = "vmshm-object-2client-gles-${RUN_ID}"
window_size = ${GLES_OBJECT_WINDOW_BYTES}
seal = true

[[domains]]
id = "vmshm-comm-client0"
socket_path = "/run/vmshm/vmshm-comm-client0.sock"
memfd_name = "vmshm-comm-client0-gles-${RUN_ID}"
window_size = 33554432
seal = true

[[domains]]
id = "vmshm-comm-client1"
socket_path = "/run/vmshm/vmshm-comm-client1.sock"
memfd_name = "vmshm-comm-client1-gles-${RUN_ID}"
window_size = 33554432
seal = true
EOF
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

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	{
		GLES_ROOTFS_PATH=""
		prune_rootfs_base_layout
		GLES_ROOTFS_PATH=$(inject_gles_compute_payload)
		echo "gles_client_mem_mib=${GLES_CLIENT_MEM_MIB}"
		echo "gles_proxy_mem_mib=${GLES_PROXY_MEM_MIB}"
		echo "gles_remote_build=${GLES_REMOTE_BUILD}"
		echo "gles_client_vcpus=${GLES_CLIENT_VCPUS}"
		echo "gles_proxy_vcpus=${GLES_PROXY_VCPUS}"
		echo "gles_client_start_gap_sec=${GLES_CLIENT_START_GAP_SEC}"
		echo "gles_sync_start_delay_sec=${GLES_SYNC_START_DELAY_SEC}"
		GLES_SMOKE_START_UPTIME_MS=0
		if [[ "${GLES_SYNC_START_DELAY_SEC}" != "0" ]]; then
			GLES_SMOKE_START_EPOCH=$(($(date +%s) + GLES_SYNC_START_DELAY_SEC))
		else
			GLES_SMOKE_START_EPOCH=0
		fi
		echo "gles_smoke_start_uptime_ms=${GLES_SMOKE_START_UPTIME_MS}"
		echo "gles_smoke_start_epoch=${GLES_SMOKE_START_EPOCH}"
		echo "gles_min_host_available_mib=${GLES_MIN_HOST_AVAILABLE_MIB}"
		echo "gles_proxy_panthor_stats=${GLES_PROXY_PANTHOR_STATS}"
		echo "gles_panthor_sched_tick_ms=${GLES_PANTHOR_SCHED_TICK_MS}"
		echo "gles_panthor_sched_highpri_wq=${GLES_PANTHOR_SCHED_HIGHPRI_WQ}"
		echo "gles_panthor_proxy_group_core_partitions=${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS}"
		echo "gles_object_window_mib=${GLES_OBJECT_WINDOW_MIB}"
		echo "gles_object_window_bytes=${GLES_OBJECT_WINDOW_BYTES}"
		echo "gles_rootfs=${GLES_ROOTFS_PATH}"
		write_gles_broker_config
		echo "broker_config=${GLES_BROKER_CONFIG}"
		PROXY_GLES_CONFIG=$(prepare_gles_compute_proxy)
		CLIENT0_GLES_CONFIG=$(prepare_gles_compute_client \
			client0 /run/vmshm/vmshm-comm-client0.sock \
			"vmshm-2client-client0-gles-${RUN_ID}.dtb" \
			"${GLES_ROOTFS_PATH}")
		CLIENT1_GLES_CONFIG=$(prepare_gles_compute_client \
			client1 /run/vmshm/vmshm-comm-client1.sock \
			"vmshm-2client-client1-gles-${RUN_ID}.dtb" \
			"${GLES_ROOTFS_PATH}")
		echo "proxy_config=${PROXY_GLES_CONFIG}"
		echo "client0_config=${CLIENT0_GLES_CONFIG}"
		echo "client1_config=${CLIENT1_GLES_CONFIG}"
	} >"${LOG_DIR}/gles-compute-rootfs.log" 2>&1
fi

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	broker_cmd=(./bin/vmshm-broker --config "${GLES_BROKER_CONFIG}")
	if [[ -n "${GLES_BROKER_CPUS}" ]]; then
		broker_cmd=(taskset -c "${GLES_BROKER_CPUS}" "${broker_cmd[@]}")
	fi
	write_launch_command broker "${broker_cmd[@]}"
	if command -v perf >/dev/null 2>&1; then
		NO_COLOR=1 RUST_LOG_STYLE=never nohup \
			perf stat \
				-e task-clock,context-switches,cpu-migrations \
				-o "${LOG_DIR}/broker.perf" \
				-- "${broker_cmd[@]}" \
				< /dev/null >"${LOG_DIR}/broker.log" 2>&1 &
		echo $! >"${LOG_DIR}/broker.pid"
		echo "perf stat enabled for vmshm-broker" >"${LOG_DIR}/broker.perf.status"
	else
		NO_COLOR=1 RUST_LOG_STYLE=never nohup \
			"${broker_cmd[@]}" \
			< /dev/null >"${LOG_DIR}/broker.log" 2>&1 &
		echo $! >"${LOG_DIR}/broker.pid"
		echo "perf command not found on remote host" >"${LOG_DIR}/broker.perf.status"
	fi
elif command -v perf >/dev/null 2>&1; then
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		perf stat \
			-e task-clock,context-switches,cpu-migrations \
			-o "${LOG_DIR}/broker.perf" \
			-- sh ./scripts/shared/vmshm-2client/broker-run-2client.sh \
			< /dev/null >"${LOG_DIR}/broker.log" 2>&1 &
	echo $! >"${LOG_DIR}/broker.pid"
	echo "perf stat enabled for vmshm-broker" >"${LOG_DIR}/broker.perf.status"
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/broker-run-2client.sh \
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

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	proxy_cmd=(./bin/firecracker --no-api --no-seccomp --config-file "${PROXY_GLES_CONFIG}")
	if [[ -n "${GLES_PROXY_CPUS}" ]]; then
		proxy_cmd=(taskset -c "${GLES_PROXY_CPUS}" "${proxy_cmd[@]}")
	fi
	write_launch_command proxy "${proxy_cmd[@]}"
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		"${proxy_cmd[@]}" \
		< /dev/null >"${LOG_DIR}/proxy.log" 2>&1 &
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/vm-proxy-2client-test.sh \
		< /dev/null >"${LOG_DIR}/proxy.log" 2>&1 &
fi
echo $! >"${LOG_DIR}/proxy.pid"

wait_for_log \
	"${LOG_DIR}/proxy.log" \
	"panthor-proxy: vmshm handler registered|class_create failed|device_create failed|shared protocol init failed|Guest-boot failed" \
	60 || true

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	client0_cmd=(./bin/firecracker --no-api --no-seccomp --config-file "${CLIENT0_GLES_CONFIG}")
	if [[ -n "${GLES_CLIENT0_CPUS}" ]]; then
		client0_cmd=(taskset -c "${GLES_CLIENT0_CPUS}" "${client0_cmd[@]}")
	fi
	write_launch_command client0 "${client0_cmd[@]}"
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		"${client0_cmd[@]}" \
		< /dev/null >"${LOG_DIR}/client0.log" 2>&1 &
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/vm-client0-2client-test.sh \
		< /dev/null >"${LOG_DIR}/client0.log" 2>&1 &
fi
echo $! >"${LOG_DIR}/client0.pid"

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	if [[ "${GLES_CLIENT_START_GAP_SEC}" != "0" ]]; then
		wait_for_log "${LOG_DIR}/client0.log" \
			"panthor-client: registered DRM frontend|GPU_SMOKE_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops" \
			120 || true
		sleep "${GLES_CLIENT_START_GAP_SEC}"
	fi
else
	wait_for_log "${LOG_DIR}/client0.log" "panthor-client: registered DRM frontend|Guest-boot failed" 60 || true
fi

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	client1_cmd=(./bin/firecracker --no-api --no-seccomp --config-file "${CLIENT1_GLES_CONFIG}")
	if [[ -n "${GLES_CLIENT1_CPUS}" ]]; then
		client1_cmd=(taskset -c "${GLES_CLIENT1_CPUS}" "${client1_cmd[@]}")
	fi
	write_launch_command client1 "${client1_cmd[@]}"
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		"${client1_cmd[@]}" \
		< /dev/null >"${LOG_DIR}/client1.log" 2>&1 &
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/vm-client1-2client-test.sh \
		< /dev/null >"${LOG_DIR}/client1.log" 2>&1 &
fi
echo $! >"${LOG_DIR}/client1.pid"

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	wait_for_log "${LOG_DIR}/client0.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout|mismatch|software renderer detected" "${GLES_CLIENT_RESULT_TIMEOUT_SEC}" || true
	wait_for_log "${LOG_DIR}/client1.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout|mismatch|software renderer detected" "${GLES_CLIENT_RESULT_TIMEOUT_SEC}" || true
else
	wait_for_log "${LOG_DIR}/client1.log" "panthor-client: registered DRM frontend|Guest-boot failed" 60 || true
fi

if [[ ! -f "${LOG_DIR}/broker.perf" && -f "${LOG_DIR}/broker.task.pid" ]]; then
	snapshot_broker_proc "$(cat "${LOG_DIR}/broker.task.pid")" "${LOG_DIR}/broker.proc.end" || true
	write_broker_proc_delta \
		"${LOG_DIR}/broker.proc.start" \
		"${LOG_DIR}/broker.proc.end" \
		"${LOG_DIR}/broker.perf" || true
fi

for pid_file in client0.pid client1.pid proxy.pid broker.pid broker.task.pid; do
	stop_pid_file "${LOG_DIR}/${pid_file}"
done
sleep 1
if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	write_mem_snapshot "after stop"
fi

{
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		echo "2-client shared GLES compute smoke result"
	else
		echo "2-client direct eventfd vmshm test result"
	fi
	echo "Run ID: ${RUN_ID}"
	echo "Timestamp: $(date -Is)"
	echo "Remote log dir: ${LOG_DIR}"
	echo "GLES compute smoke: ${GLES_COMPUTE_SMOKE}"
	echo "GLES remote build: ${GLES_REMOTE_BUILD}"
	echo "GLES smoke args: ${GLES_SMOKE_ARGS}"
	echo "GLES client BO mmap cached: ${GLES_CLIENT_BO_MMAP_CACHED}"
	echo "GLES sync start delay sec: ${GLES_SYNC_START_DELAY_SEC}"
	echo "GLES smoke start uptime ms: ${GLES_SMOKE_START_UPTIME_MS:-0}"
	echo "GLES smoke start epoch: ${GLES_SMOKE_START_EPOCH:-0}"
	echo "GLES Panthor sched tick ms: ${GLES_PANTHOR_SCHED_TICK_MS}"
	echo "GLES Panthor sched highpri wq: ${GLES_PANTHOR_SCHED_HIGHPRI_WQ}"
	echo "GLES Panthor proxy group core partitions: ${GLES_PANTHOR_PROXY_GROUP_CORE_PARTITIONS}"
	echo
	echo "== Broker direct bridges =="
	grep -aE "vmshm domain is listening|vmshm notify direct eventfd|sent vmshm memfd|vmshm connection failed" \
		"${LOG_DIR}/broker.log" | tail -n 80 || true
	echo
	echo "== Broker perf stat =="
	cat "${LOG_DIR}/broker.perf.status" 2>/dev/null || true
	sed -n '1,80p' "${LOG_DIR}/broker.perf" 2>/dev/null || true
	echo
	echo "== Proxy vmshm/panthor =="
	grep -aE "registered vmshm notify|proxy_comm_vmshm .*irq notify enabled|proxy_comm_vmshm: selftest passed|PANTHOR_SUBMIT_STATS|PANTHOR_JOB_IRQ_STATS|PANTHOR_PROXY_RPC_STATS|DRM_SCHED_PUSH_STATS|DRM_SCHED_RUN_JOB_STATS|panthor-proxy: vmshm handler registered|panthor-proxy: OPEN_SESSION|panthor-proxy: VM_CREATE|panthor-proxy: BO_CREATE|panthor-proxy: VM_BIND|panthor-proxy: GROUP_CORE_PARTITION|panthor-proxy: GROUP_CREATE|panthor-proxy: GROUP_SUBMIT|panthor-proxy: GROUP_DESTROY|panthor-proxy: VM_DESTROY|panthor-proxy: CLOSE_SESSION|Guest-boot failed|ERROR|WARN" \
		"${LOG_DIR}/proxy.log" | tail -n 160 || true
	echo
	if [[ -f "${LOG_DIR}/gles-compute-rootfs.log" ]]; then
		echo "== GLES compute rootfs prep =="
		sed -n '1,160p' "${LOG_DIR}/gles-compute-rootfs.log" || true
		echo
	fi
	if [[ -f "${LOG_DIR}/preflight.txt" ]]; then
		echo "== Host memory preflight =="
		sed -n '1,160p' "${LOG_DIR}/preflight.txt" || true
		echo
	fi
	if [[ -f "${LOG_DIR}/affinity.log" ]]; then
		echo "== Host CPU affinity =="
		grep -aE "== |online_cpus=|requested_online_cpus=|broker_cpus=|proxy_cpus=|client[01]_cpus=|launch_|before_restore=|after_restore=" \
			"${LOG_DIR}/affinity.log" | tail -n 120 || true
		echo
	fi
	echo "== Client0 =="
	grep -aE "client_comm_vmshm: perf selftest passed|CLIENT_COMM_RPC_STATS|PANTHOR_CLIENT_BO_MMAP_CACHED|panthor-client: BO mmap cached=|panthor-client: registered DRM frontend|panthor-client: MMAP .*attr=|GPU_SMOKE_RESULT|COMPUTE_CHECK|GL_RENDERER|GL_VENDOR|GL_VERSION|GBM_BACKEND|DRM_NODE|STAGE=|PERF_|gles-compute-smoke rc|mismatch|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|Guest-boot failed|ERROR|WARN" \
		"${LOG_DIR}/client0.log" | tail -n 120 || true
	echo
	echo "== Client1 =="
	grep -aE "client_comm_vmshm: perf selftest passed|CLIENT_COMM_RPC_STATS|PANTHOR_CLIENT_BO_MMAP_CACHED|panthor-client: BO mmap cached=|panthor-client: registered DRM frontend|panthor-client: MMAP .*attr=|GPU_SMOKE_RESULT|COMPUTE_CHECK|GL_RENDERER|GL_VENDOR|GL_VERSION|GBM_BACKEND|DRM_NODE|STAGE=|PERF_|gles-compute-smoke rc|mismatch|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|Guest-boot failed|ERROR|WARN" \
		"${LOG_DIR}/client1.log" | tail -n 120 || true
	echo

	gles_client_ok() {
		local log_file="$1"

		grep -qa "GPU_SMOKE_RESULT=PASS" "${log_file}" || return 1
		grep -qa "COMPUTE_CHECK=PASS" "${log_file}" || return 1
		grep -qaE "GL_RENDERER=.*Mali|GL_RENDERER=.*Panfrost" "${log_file}" || return 1
		if [[ "${GLES_SMOKE_ARGS}" == *"--exclude-cpu-prepare"* ]]; then
			grep -qa "PERF_CPU_PREPARE_EXCLUDED=1" "${log_file}" || return 1
		fi
		! grep -qaE "software renderer detected|llvmpipe|softpipe|Software Rasterizer|COMPUTE_CHECK=FAIL|GPU_SMOKE_RESULT=FAIL|Kernel panic|Oops|job timeout|mismatch" "${log_file}"
	}

	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		if gles_client_ok "${LOG_DIR}/client0.log" &&
		   gles_client_ok "${LOG_DIR}/client1.log"; then
			echo "RESULT: GLES_PASS"
		else
			echo "RESULT: GLES_FAIL"
		fi
	elif grep -qa "client_comm_vmshm: perf selftest passed" "${LOG_DIR}/client0.log" &&
	   grep -qa "client_comm_vmshm: perf selftest passed" "${LOG_DIR}/client1.log"; then
		echo "RESULT: COMM_PASS"
	else
		echo "RESULT: COMM_FAIL"
	fi

	if [[ "${GLES_COMPUTE_SMOKE}" != "1" ]] &&
	   grep -qa "panthor-client: DEV_QUERY selftest passed" "${LOG_DIR}/client0.log" &&
	   grep -qa "panthor-client: DEV_QUERY perf selftest passed" "${LOG_DIR}/client0.log" &&
	   grep -qa "panthor-client: DEV_QUERY selftest passed" "${LOG_DIR}/client1.log" &&
	   grep -qa "panthor-client: DEV_QUERY perf selftest passed" "${LOG_DIR}/client1.log"; then
		echo "RESULT: QUERY_PASS"
	elif [[ "${GLES_COMPUTE_SMOKE}" != "1" ]]; then
		echo "RESULT: QUERY_FAIL"
	fi
} >"${LOG_DIR}/result"

cat "${LOG_DIR}/result"
echo "LOG_DIR=${LOG_DIR}"

	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		grep -qa "RESULT: GLES_PASS" "${LOG_DIR}/result"
	else
		grep -qa "RESULT: COMM_PASS" "${LOG_DIR}/result" &&
		grep -qa "RESULT: QUERY_PASS" "${LOG_DIR}/result"
	fi
REMOTE_SCRIPT
}

fetch_logs() {
	log "Fetching logs back to ${SFTP_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}"
	mkdir -p "${SFTP_LOG_ROOT}/shared/vmshm-2client"
	rsync_remote -av --info=stats2,name1 \
		"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}/" \
		"${SFTP_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}/"
}

show_summary() {
	local result="${SFTP_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}/result"

	if [[ -f "${result}" ]]; then
		log "Result summary"
		sed -n '1,260p' "${result}"
		echo
		echo "Local logs: ${SFTP_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}"
	else
		log "No local result fetched yet"
		echo "Expected: ${result}"
	fi
}

require_cmd ssh
require_cmd rsync
require_cmd setsid

install_configs
if [[ "${SYNC_TO_REMOTE}" -eq 1 ]]; then
	sync_to_remote
fi

remote_status=0
run_remote_test || remote_status=$?

if [[ "${FETCH_LOGS}" -eq 1 ]]; then
	fetch_logs
fi

show_summary
exit "${remote_status}"
