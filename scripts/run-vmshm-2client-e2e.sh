#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/.." && pwd)
SFTP_ROOT=${SFTP_ROOT:-"${ROOT_DIR}/GPU-SFTP"}
SFTP_BINS=${SFTP_BINS:-"${SFTP_ROOT}/firecracker-bins"}
SFTP_LOG_ROOT=${SFTP_LOG_ROOT:-"${SFTP_ROOT}/log"}

REMOTE_HOST=${REMOTE_HOST:-192.168.137.10}
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
  --sync-rootfs            Include rootfs.ext2 in local-to-remote rsync
  --run-id ID              Use a fixed run log directory name
  -h, --help               Show this help

Environment overrides:
  SFTP_ROOT SFTP_BINS SFTP_LOG_ROOT
  REMOTE_HOST REMOTE_USER REMOTE_PASS REMOTE_ROOT REMOTE_BINS REMOTE_LOG_ROOT RUN_ID

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
source "${SCRIPT_DIR}/lib/gpu_sftp_layout.sh"

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
	local run_id_q remote_bins_q remote_log_root_q clean_q

	run_id_q=$(quote "${RUN_ID}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	clean_q=$(quote "${CLEAN_REMOTE_PROCS}")

	log "Running remote 2-client vmshm test: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BINS}"
	ssh_remote "RUN_ID=${run_id_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} CLEAN_REMOTE_PROCS=${clean_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_BINS}"
LOG_DIR="${REMOTE_LOG_ROOT}/shared/vmshm-2client/${RUN_ID}"
mkdir -p /run/vmshm "${LOG_DIR}"

if [[ "${CLEAN_REMOTE_PROCS}" == "1" ]]; then
	pkill -x firecracker 2>/dev/null || true
	pkill -x vmshm-broker 2>/dev/null || true
	sleep 1
fi
rm -f /run/vmshm/*.sock

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

if command -v perf >/dev/null 2>&1; then
	NO_COLOR=1 RUST_LOG_STYLE=never nohup \
		perf stat \
			-e task-clock,context-switches,cpu-migrations \
			-o "${LOG_DIR}/broker.perf" \
			-- sh ./scripts/shared/vmshm-2client/broker-run-2client.sh >"${LOG_DIR}/broker.log" 2>&1 &
	echo $! >"${LOG_DIR}/broker.pid"
	echo "perf stat enabled for vmshm-broker" >"${LOG_DIR}/broker.perf.status"
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/broker-run-2client.sh >"${LOG_DIR}/broker.log" 2>&1 &
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

NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/vm-proxy-2client-test.sh >"${LOG_DIR}/proxy.log" 2>&1 &
echo $! >"${LOG_DIR}/proxy.pid"

wait_for_log \
	"${LOG_DIR}/proxy.log" \
	"panthor-proxy: vmshm handler registered|class_create failed|device_create failed|shared protocol init failed|Guest-boot failed" \
	60 || true

NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/vm-client0-2client-test.sh >"${LOG_DIR}/client0.log" 2>&1 &
echo $! >"${LOG_DIR}/client0.pid"

wait_for_log "${LOG_DIR}/client0.log" "panthor-client: registered DRM frontend|Guest-boot failed" 60 || true

NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-2client/vm-client1-2client-test.sh >"${LOG_DIR}/client1.log" 2>&1 &
echo $! >"${LOG_DIR}/client1.pid"

wait_for_log "${LOG_DIR}/client1.log" "panthor-client: registered DRM frontend|Guest-boot failed" 60 || true

if [[ ! -f "${LOG_DIR}/broker.perf" && -f "${LOG_DIR}/broker.task.pid" ]]; then
	snapshot_broker_proc "$(cat "${LOG_DIR}/broker.task.pid")" "${LOG_DIR}/broker.proc.end" || true
	write_broker_proc_delta \
		"${LOG_DIR}/broker.proc.start" \
		"${LOG_DIR}/broker.proc.end" \
		"${LOG_DIR}/broker.perf" || true
fi

for pid_file in broker.pid proxy.pid client0.pid client1.pid; do
	if [[ -f "${LOG_DIR}/${pid_file}" ]]; then
		kill -INT "$(cat "${LOG_DIR}/${pid_file}")" 2>/dev/null || true
	fi
done
if [[ -f "${LOG_DIR}/broker.task.pid" ]]; then
	kill -INT "$(cat "${LOG_DIR}/broker.task.pid")" 2>/dev/null || true
fi
sleep 1

{
	echo "2-client direct eventfd vmshm test result"
	echo "Run ID: ${RUN_ID}"
	echo "Timestamp: $(date -Is)"
	echo "Remote log dir: ${LOG_DIR}"
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
	grep -aE "registered vmshm notify|proxy_comm_vmshm|panthor-proxy: vmshm handler registered|Guest-boot failed|ERROR|WARN" \
		"${LOG_DIR}/proxy.log" || true
	echo
	echo "== Client0 =="
	grep -aE "registered vmshm notify|client_comm_vmshm|panthor-client: DEV_QUERY|panthor-client: registered DRM frontend|Guest-boot failed|ERROR|WARN" \
		"${LOG_DIR}/client0.log" || true
	echo
	echo "== Client1 =="
	grep -aE "registered vmshm notify|client_comm_vmshm|panthor-client: DEV_QUERY|panthor-client: registered DRM frontend|Guest-boot failed|ERROR|WARN" \
		"${LOG_DIR}/client1.log" || true
	echo

	if grep -qa "client_comm_vmshm: perf selftest passed" "${LOG_DIR}/client0.log" &&
	   grep -qa "client_comm_vmshm: perf selftest passed" "${LOG_DIR}/client1.log"; then
		echo "RESULT: COMM_PASS"
	else
		echo "RESULT: COMM_FAIL"
	fi

	if grep -qa "panthor-client: DEV_QUERY selftest passed" "${LOG_DIR}/client0.log" &&
	   grep -qa "panthor-client: DEV_QUERY perf selftest passed" "${LOG_DIR}/client0.log" &&
	   grep -qa "panthor-client: DEV_QUERY selftest passed" "${LOG_DIR}/client1.log" &&
	   grep -qa "panthor-client: DEV_QUERY perf selftest passed" "${LOG_DIR}/client1.log"; then
		echo "RESULT: QUERY_PASS"
	else
		echo "RESULT: QUERY_FAIL"
	fi
} >"${LOG_DIR}/result"

cat "${LOG_DIR}/result"
echo "LOG_DIR=${LOG_DIR}"

grep -qa "RESULT: COMM_PASS" "${LOG_DIR}/result" &&
grep -qa "RESULT: QUERY_PASS" "${LOG_DIR}/result"
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
