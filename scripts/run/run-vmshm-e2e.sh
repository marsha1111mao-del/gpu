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
  --sync-rootfs              Include rootfs.ext2 in local-to-remote rsync
  --ioctl-smoke              Run userspace /dev/dri/card0 VERSION/GET_CAP/DEV_QUERY smoke
  --vm-create-smoke          Run ioctl smoke plus PANTHOR_VM_CREATE/VM_DESTROY
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

	run_id_q=$(quote "${RUN_ID}")
	remote_root_q=$(quote "${REMOTE_ROOT}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	clean_q=$(quote "${CLEAN_REMOTE_PROCS}")
	ioctl_smoke_q=$(quote "${IOCTL_SMOKE}")
	ioctl_smoke_mode_q=$(quote "${IOCTL_SMOKE_MODE}")

	log "Running remote vmshm test: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BINS}"
	ssh_remote "RUN_ID=${run_id_q} REMOTE_ROOT=${remote_root_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} CLEAN_REMOTE_PROCS=${clean_q} IOCTL_SMOKE=${ioctl_smoke_q} IOCTL_SMOKE_MODE=${ioctl_smoke_mode_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_BINS}"
LOG_DIR="${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"
mkdir -p /run/vmshm "${LOG_DIR}"
SMOKE_ROOTFS="${REMOTE_BINS}/rootfs/rootfs-ioctl-smoke-${RUN_ID}.ext2"
SMOKE_CLIENT_CONFIG="${LOG_DIR}/client-ioctl-smoke-config.json"
SMOKE_MNT=""

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
	if [[ "${IOCTL_SMOKE}" == "1" ]]; then
		rm -f "${SMOKE_ROOTFS}"
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

prepare_ioctl_smoke_client() {
	[[ -x ./bin/panthor_ioctl_smoke ]] ||
		{ echo "missing executable ./bin/panthor_ioctl_smoke" >&2; return 1; }
	[[ -f ./rootfs/rootfs.ext2 ]] ||
		{ echo "missing ./rootfs/rootfs.ext2 on remote" >&2; return 1; }

	cp -f ./rootfs/rootfs.ext2 "${SMOKE_ROOTFS}"
	SMOKE_MNT=$(mktemp -d /tmp/panthor-ioctl-rootfs.XXXXXX)
	mount -o loop "${SMOKE_ROOTFS}" "${SMOKE_MNT}"
	install -m 0755 ./bin/panthor_ioctl_smoke "${SMOKE_MNT}/panthor_ioctl_smoke"
	cat >"${SMOKE_MNT}/panthor_ioctl_smoke_mode" <<EOF
${IOCTL_SMOKE_MODE}
EOF
	cat >"${SMOKE_MNT}/panthor_ioctl_smoke_init" <<'INIT_SCRIPT'
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
case "${mode}" in
	vm-create)
		smoke_arg="--vm-create"
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
	chmod 0755 "${SMOKE_MNT}/panthor_ioctl_smoke_init"
	sync
	umount "${SMOKE_MNT}"
	rmdir "${SMOKE_MNT}"
	SMOKE_MNT=""

	cat >"${SMOKE_CLIENT_CONFIG}" <<EOF
{
  "boot-source": {
    "kernel_image_path": "${REMOTE_BINS}/kernels/shared/client/Image",
    "boot_args": "console=ttyS0 root=/dev/vda rw rootfstype=ext4 init=/panthor_ioctl_smoke_init"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "${SMOKE_ROOTFS}",
      "is_root_device": false,
      "is_read_only": false
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
      "guest_phys_addr": "0x20000000",
      "slot": 1,
      "expected_size": 67108864,
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

if command -v perf >/dev/null 2>&1; then
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		perf stat \
			-e task-clock,context-switches,cpu-migrations \
			-o "${LOG_DIR}/broker.perf" \
			-- sh ./scripts/shared/vmshm-1client/broker-run.sh >"${LOG_DIR}/broker.log" 2>&1 &
	echo $! >"${LOG_DIR}/broker.pid"
	echo "perf stat enabled for vmshm-broker" >"${LOG_DIR}/broker.perf.status"
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/broker-run.sh >"${LOG_DIR}/broker.log" 2>&1 &
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

NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/vm-proxy-test.sh >"${LOG_DIR}/proxy.log" 2>&1 &
echo $! >"${LOG_DIR}/proxy.pid"

wait_for_log \
	"${LOG_DIR}/proxy.log" \
	"panthor-proxy: vmshm handler registered" \
	60 || true

if [[ "${IOCTL_SMOKE}" == "1" ]]; then
	prepare_ioctl_smoke_client >"${LOG_DIR}/ioctl-smoke-rootfs.log" 2>&1
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		./bin/firecracker --no-api --no-seccomp --config-file "${SMOKE_CLIENT_CONFIG}" \
		>"${LOG_DIR}/client.log" 2>&1 &
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/vm-client-test.sh >"${LOG_DIR}/client.log" 2>&1 &
fi
echo $! >"${LOG_DIR}/client.pid"

if [[ "${IOCTL_SMOKE}" == "1" ]]; then
	wait_for_log "${LOG_DIR}/client.log" "PANTHOR_IOCTL_SMOKE=(BASIC_PASS|VM_CREATE_PASS)|PANTHOR_IOCTL_INIT=FAIL|Kernel panic|Guest-boot failed" 80 || true
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

for pid_file in client.pid proxy.pid broker.pid; do
	if [[ -f "${LOG_DIR}/${pid_file}" ]]; then
		kill -INT "$(cat "${LOG_DIR}/${pid_file}")" 2>/dev/null || true
	fi
done
if [[ -f "${LOG_DIR}/broker.task.pid" ]]; then
	kill -INT "$(cat "${LOG_DIR}/broker.task.pid")" 2>/dev/null || true
fi
sleep 1

ioctl_mode_marker_ok() {
	case "${IOCTL_SMOKE_MODE}" in
	basic)
		grep -qa "PANTHOR_IOCTL_SMOKE=BASIC_PASS" "${LOG_DIR}/client.log"
		;;
	vm-create)
		grep -qa "PANTHOR_IOCTL_SMOKE=VM_CREATE_PASS" "${LOG_DIR}/client.log"
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

{
	if [[ "${IOCTL_SMOKE}" == "1" ]]; then
		echo "Panthor DRM open/session/version/cap/devquery vmshm test result"
	else
		echo "DRM_PANTHOR_DEV_QUERY vmshm test result"
	fi
	echo "Run ID: ${RUN_ID}"
	echo "Timestamp: $(date -Is)"
	echo "Remote log dir: ${LOG_DIR}"
	echo "IOCTL smoke: ${IOCTL_SMOKE}"
	echo "IOCTL smoke mode: ${IOCTL_SMOKE_MODE}"
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
	grep -aE "panthor-proxy: OPEN_SESSION session=[1-9][0-9]*|panthor-proxy: DEV_QUERY session=[1-9][0-9]*|panthor-proxy: VM_CREATE session=[1-9][0-9]*|panthor-proxy: VM_DESTROY session=[1-9][0-9]*|panthor-proxy: CLOSE_SESSION session=[1-9][0-9]*" \
		"${LOG_DIR}/proxy.log" | tail -n 80 || true
	echo
	if [[ -f "${LOG_DIR}/ioctl-smoke-rootfs.log" ]]; then
		echo "== IOCTL smoke rootfs prep =="
		sed -n '1,120p' "${LOG_DIR}/ioctl-smoke-rootfs.log" || true
		echo
	fi
	echo "== Client Panthor DRM =="
	grep -aE "registered vmshm notify|client_comm_vmshm .*irq notify enabled|client_comm_vmshm: perf|panthor-client: OPEN_SESSION|panthor-client: DEV_QUERY|panthor-client: VM_CREATE|panthor-client: VM_DESTROY|panthor-client: CLOSE_SESSION|panthor-client: registered DRM frontend|PANTHOR_IOCTL_|PANTHOR_BASIC_SMOKE|PANTHOR_VM_CREATE_SMOKE|OPEN path=|VERSION name=|GET_CAP|DEV_QUERY_SIZE|GPU_INFO|CSIF_INFO|VM_CREATE|VM_DESTROY|ERROR|WARN|Kernel panic|Guest-boot failed" \
		"${LOG_DIR}/client.log" || true
	echo
	if [[ "${IOCTL_SMOKE}" == "1" ]] &&
	   ioctl_mode_marker_ok &&
	   ioctl_common_markers_ok &&
	   ioctl_vm_create_markers_ok; then
		echo "RESULT: PASS"
	elif [[ "${IOCTL_SMOKE}" != "1" ]] &&
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
