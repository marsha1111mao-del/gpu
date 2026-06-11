#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
HOST_KERNEL_DIR=${HOST_KERNEL_DIR:-"${ROOT_DIR}/Linux-Host-GPU"}
SFTP_ROOT=${SFTP_ROOT:-"${ROOT_DIR}/GPU-SFTP"}
SFTP_HOST_KERNEL=${SFTP_HOST_KERNEL:-"${SFTP_ROOT}/linux-host-kernel"}
SFTP_BINS=${SFTP_BINS:-"${SFTP_ROOT}/firecracker-bins"}
SFTP_LOG_ROOT=${SFTP_LOG_ROOT:-"${SFTP_ROOT}/log"}
BUILD_HOST_KERNEL_PAYLOAD=${BUILD_HOST_KERNEL_PAYLOAD:-"${ROOT_DIR}/scripts/build/build-host-kernel-payload.sh"}
BUILD_FIRECRACKER_RUNTIME=${BUILD_FIRECRACKER_RUNTIME:-"${ROOT_DIR}/scripts/build/build-firecracker-runtime.sh"}

REMOTE_HOST=${REMOTE_HOST:-192.168.31.18}
REMOTE_USER=${REMOTE_USER:-root}
REMOTE_PASS=${REMOTE_PASS:-root}
REMOTE_ROOT=${REMOTE_ROOT:-/root/GPU-SFTP}
REMOTE_HOST_KERNEL=${REMOTE_HOST_KERNEL:-"${REMOTE_ROOT}/linux-host-kernel"}
REMOTE_BINS=${REMOTE_BINS:-"${REMOTE_ROOT}/firecracker-bins"}
REMOTE_LOG_ROOT=${REMOTE_LOG_ROOT:-"${REMOTE_ROOT}/log"}
REMOTE_BOOT_IMAGE=${REMOTE_BOOT_IMAGE:-/boot/vmlinuz-6.12.0-opencca-wip}

RUN_ID_PREFIX=${RUN_ID_PREFIX:-host-pmthor-deploy}
SSH_TIMEOUT=${SSH_TIMEOUT:-180}
SYNC_ROOTFS=${SYNC_ROOTFS:-0}
INSTALL_HOST_MODULES=${INSTALL_HOST_MODULES:-0}
HOST_MODULES=${HOST_MODULES:-}
PASSTHROUGH_RUNS=${PASSTHROUGH_RUNS:-5}
VM_TIMEOUT=${VM_TIMEOUT:-35}
PASSTHROUGH_VM_RUNNER=${PASSTHROUGH_VM_RUNNER:-scripts/passthrough/run-gpu-passthrough-vm.sh}
PASSTHROUGH_VM_CONFIG=${PASSTHROUGH_VM_CONFIG:-configs/passthrough/gpu-passthrough-vm-config.json}

BUILD_HOST_KERNEL=1
BUILD_FIRECRACKER=1
SYNC_TO_REMOTE=1
INSTALL_AND_REBOOT=1
RUN_TESTS=1

usage() {
	cat <<EOF
Usage: $(basename "$0") [options]

Build Linux-Host-GPU, sync GPU-SFTP to the remote host, install the host
kernel under /boot, reboot, wait for SSH, then repeatedly boot one normal
Firecracker VM with GPU passthrough and check that the guest panthor driver
probes successfully.

Options:
  --skip-host-build          Do not run scripts/build/build-host-kernel-payload.sh
  --skip-firecracker-build   Do not run scripts/build/build-firecracker-runtime.sh
  --skip-sync                Do not rsync GPU-SFTP to the remote host
  --skip-install-reboot      Do not replace /boot image or reboot
  --skip-tests               Do not run GPU passthrough probe tests after reboot
  --sync-rootfs              Include rootfs.ext2 in local-to-remote rsync
  --install-host-modules     Sync and install host kernel modules. Default skips modules.
  --host-modules LIST        Build/sync/install only selected .ko files; comma-separated paths.
                              Implies --install-host-modules.
  --runs N                   Number of single-VM boot attempts, default: ${PASSTHROUGH_RUNS}
  --vm-timeout SEC           Seconds to let each VM run before SIGINT, default: ${VM_TIMEOUT}
  --run-id-prefix PREFIX     Prefix for generated run log IDs
  -h, --help                 Show this help

Environment overrides:
  REMOTE_HOST REMOTE_USER REMOTE_PASS REMOTE_ROOT REMOTE_BOOT_IMAGE
  SSH_TIMEOUT RUN_ID_PREFIX SFTP_ROOT SFTP_HOST_KERNEL SFTP_LOG_ROOT
  PASSTHROUGH_RUNS VM_TIMEOUT REMOTE_LOG_ROOT
  INSTALL_HOST_MODULES HOST_MODULES PASSTHROUGH_VM_RUNNER PASSTHROUGH_VM_CONFIG
  BUILD_HOST_KERNEL_PAYLOAD BUILD_FIRECRACKER_RUNTIME

Logs:
  remote: ${REMOTE_LOG_ROOT}/passthrough/probe/<generated-run-id>
  local:  ${SFTP_LOG_ROOT}/passthrough/probe/<generated-run-id>
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--skip-host-build)
		BUILD_HOST_KERNEL=0
		;;
	--skip-firecracker-build)
		BUILD_FIRECRACKER=0
		;;
	--skip-sync)
		SYNC_TO_REMOTE=0
		;;
	--skip-install-reboot)
		INSTALL_AND_REBOOT=0
		;;
	--skip-tests)
		RUN_TESTS=0
		;;
	--sync-rootfs)
		SYNC_ROOTFS=1
		;;
	--install-host-modules)
		INSTALL_HOST_MODULES=1
		;;
	--host-modules)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--host-modules requires an argument" >&2
			exit 2
		fi
		INSTALL_HOST_MODULES=1
		HOST_MODULES=${1//,/ }
		;;
	--runs)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--runs requires an argument" >&2
			exit 2
		fi
		PASSTHROUGH_RUNS=$1
		;;
	--vm-timeout)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--vm-timeout requires an argument" >&2
			exit 2
		fi
		VM_TIMEOUT=$1
		;;
	--run-id-prefix)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--run-id-prefix requires an argument" >&2
			exit 2
		fi
		RUN_ID_PREFIX=$1
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

	tmpdir=$(mktemp -d /tmp/gpu-host-ssh.XXXXXX)
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

build_host_kernel() {
	log "Building host kernel payload"
	HOST_KERNEL_DIR="${HOST_KERNEL_DIR}" \
	INSTALL_MODULES="${INSTALL_HOST_MODULES}" \
	HOST_MODULES="${HOST_MODULES}" \
		"${BUILD_HOST_KERNEL_PAYLOAD}"
	[[ -f "${SFTP_HOST_KERNEL}/Image" ]] ||
		die "missing host Image: ${SFTP_HOST_KERNEL}/Image"
}

build_firecracker() {
	log "Building Firecracker payload"
	"${BUILD_FIRECRACKER_RUNTIME}"
	[[ -x "${SFTP_BINS}/bin/firecracker" ]] ||
		die "missing firecracker binary: ${SFTP_BINS}/bin/firecracker"
}

sync_to_remote() {
	local excludes=(
		--exclude='.vscode/'
		--exclude='.git/'
		--exclude='node_modules/'
		--exclude='log/'
		--exclude='firecracker-bins/run-logs/'
	)

	if [[ "${SYNC_ROOTFS}" -eq 0 ]]; then
		excludes+=(--exclude='firecracker-bins/rootfs/')
	fi
	if [[ "${INSTALL_HOST_MODULES}" -eq 0 ]]; then
		excludes+=(
			--exclude='linux-host-kernel/modules-staging/'
			--exclude='linux-host-kernel/lib/modules/'
		)
	elif [[ -n "${HOST_MODULES}" ]]; then
		excludes+=(--exclude='linux-host-kernel/lib/modules/')
	fi

	log "Ensuring remote SFTP directory exists"
	ssh_remote "mkdir -p $(quote "${REMOTE_ROOT}")"

	log "Removing obsolete remote firecracker-bins/run-logs"
	ssh_remote "rm -rf $(quote "${REMOTE_BINS}/run-logs")"

	if [[ -n "${HOST_MODULES}" ]]; then
		log "Removing stale remote selected-module staging"
		ssh_remote "rm -rf $(quote "${REMOTE_HOST_KERNEL}/modules-staging")"
	fi

	log "Syncing GPU-SFTP to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_ROOT}"
	rsync_remote -av --info=stats2,name1 \
		"${excludes[@]}" \
		"${SFTP_ROOT}/" \
		"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_ROOT}/"

	migrate_remote_gpu_sftp_layout
}

install_kernel_and_reboot() {
	local remote_kernel_q remote_boot_q install_modules_q host_modules_q

	remote_kernel_q=$(quote "${REMOTE_HOST_KERNEL}")
	remote_boot_q=$(quote "${REMOTE_BOOT_IMAGE}")
	install_modules_q=$(quote "${INSTALL_HOST_MODULES}")
	host_modules_q=$(quote "${HOST_MODULES}")

	log "Installing remote host kernel and rebooting ${REMOTE_HOST}"
	set +e
	ssh_remote "REMOTE_HOST_KERNEL=${remote_kernel_q} REMOTE_BOOT_IMAGE=${remote_boot_q} INSTALL_HOST_MODULES=${install_modules_q} HOST_MODULES=${host_modules_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_HOST_KERNEL}"
test -f Image

backup="${REMOTE_BOOT_IMAGE}.bak.$(date +%Y%m%d-%H%M%S)"
if [[ -f "${REMOTE_BOOT_IMAGE}" ]]; then
	cp -av "${REMOTE_BOOT_IMAGE}" "${backup}"
fi

cp -v Image "${REMOTE_BOOT_IMAGE}"
if [[ "${INSTALL_HOST_MODULES}" -eq 1 ]]; then
	if [[ -d modules-staging/lib/modules ]]; then
		if [[ -n "${HOST_MODULES}" && -f modules-staging/selected-modules.txt ]]; then
			echo "Installing selected host modules:"
			sed 's/^/  /' modules-staging/selected-modules.txt
			for release_dir in modules-staging/lib/modules/*; do
				[[ -d "${release_dir}" ]] || continue
				release=$(basename "${release_dir}")
				while IFS= read -r module; do
					[[ -n "${module}" ]] || continue
					src="${release_dir}/kernel/${module}"
					dst="/lib/modules/${release}/kernel/${module}"
					if [[ ! -f "${src}" ]]; then
						echo "missing selected module in staging: ${src}" >&2
						exit 1
					fi
					install -D -m 0644 -v "${src}" "${dst}"
				done < modules-staging/selected-modules.txt
				depmod "${release}" || true
			done
			sync
			nohup sh -c 'sleep 2; reboot' </dev/null >/tmp/gpu-host-reboot.log 2>&1 &
			exit 0
		fi
		cp -arv modules-staging/lib/modules/. /lib/modules/
		for release_dir in modules-staging/lib/modules/*; do
			[[ -d "${release_dir}" ]] || continue
			release=$(basename "${release_dir}")
			depmod "${release}" || true
		done
	elif [[ -d lib/modules ]]; then
		cp -arv lib/modules/. /lib/modules/
		for release_dir in lib/modules/*; do
			[[ -d "${release_dir}" ]] || continue
			release=$(basename "${release_dir}")
			depmod "${release}" || true
		done
	else
		echo "INSTALL_HOST_MODULES=1 but no staged modules found under ${REMOTE_HOST_KERNEL}" >&2
		exit 1
	fi
else
	echo "Skipping host module install; pass --install-host-modules if modules changed."
fi
sync
nohup sh -c 'sleep 2; reboot' </dev/null >/tmp/gpu-host-reboot.log 2>&1 &
REMOTE_SCRIPT
	local ssh_status=$?
	set -e

	if [[ "${ssh_status}" -ne 0 && "${ssh_status}" -ne 255 ]]; then
		return "${ssh_status}"
	fi
}

wait_for_remote() {
	local deadline now

	log "Waiting for remote SSH to return"
	deadline=$((SECONDS + SSH_TIMEOUT))
	while (( SECONDS < deadline )); do
		if ssh_remote "true" >/dev/null 2>&1; then
			log "Remote SSH is back"
			ssh_remote "uname -a; test -e /dev/pmthor && ls -l /dev/pmthor || true"
			return 0
		fi
		sleep 5
	done

	die "remote SSH did not return within ${SSH_TIMEOUT}s"
}

run_tests() {
	local stamp run_id run_id_q remote_bins_q remote_log_root_q
	local runs_q timeout_q runner_q config_q
	local remote_status result

	stamp=$(date +%Y%m%d-%H%M%S)
	run_id="${RUN_ID_PREFIX}-gpu-passthrough-${stamp}"

	run_id_q=$(quote "${run_id}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	runs_q=$(quote "${PASSTHROUGH_RUNS}")
	timeout_q=$(quote "${VM_TIMEOUT}")
	runner_q=$(quote "${PASSTHROUGH_VM_RUNNER}")
	config_q=$(quote "${PASSTHROUGH_VM_CONFIG}")

	log "Running single-VM GPU passthrough panthor probe test: ${run_id}"
	set +e
	ssh_remote "RUN_ID=${run_id_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} PASSTHROUGH_RUNS=${runs_q} VM_TIMEOUT=${timeout_q} PASSTHROUGH_VM_RUNNER=${runner_q} PASSTHROUGH_VM_CONFIG=${config_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_BINS}"
LOG_DIR="${REMOTE_LOG_ROOT}/passthrough/probe/${RUN_ID}"
mkdir -p "${LOG_DIR}"

write_failure_result() {
	local message="$1"

	{
		echo "GPU passthrough panthor probe test result"
		echo "Run ID: ${RUN_ID}"
		echo "Timestamp: $(date -Is)"
		echo "Remote log dir: ${LOG_DIR}"
		echo
		echo "RESULT: FAIL"
		echo "${message}"
	} >"${LOG_DIR}/result"
	cat "${LOG_DIR}/result"
}

{
	echo "timestamp=$(date -Is)"
	echo "uname=$(uname -a)"
	echo "pwd=$(pwd)"
	echo
	echo "== files =="
	ls -l bin/firecracker "${PASSTHROUGH_VM_RUNNER}" "${PASSTHROUGH_VM_CONFIG}" rootfs/rootfs.ext2 kernels/passthrough/Image 2>&1 || true
	echo
	echo "== config =="
	sed -n '1,120p' "${PASSTHROUGH_VM_CONFIG}" 2>&1 || true
} >"${LOG_DIR}/preflight.txt" 2>&1

if [[ ! -x ./bin/firecracker ]]; then
	write_failure_result "missing executable ./bin/firecracker"
	exit 1
fi
if [[ ! -f "${PASSTHROUGH_VM_RUNNER}" ]]; then
	write_failure_result "missing ./${PASSTHROUGH_VM_RUNNER}"
	exit 1
fi
if [[ ! -f "${PASSTHROUGH_VM_CONFIG}" ]]; then
	write_failure_result "missing ./${PASSTHROUGH_VM_CONFIG}"
	exit 1
fi
if ! grep -qa '"gpu_passthrough"[[:space:]]*:[[:space:]]*true' "${PASSTHROUGH_VM_CONFIG}"; then
	write_failure_result "${PASSTHROUGH_VM_CONFIG} does not enable gpu_passthrough"
	exit 1
fi
if [[ ! -f ./rootfs/rootfs.ext2 ]]; then
	write_failure_result "missing ./rootfs/rootfs.ext2 on remote; rerun with --sync-rootfs if needed"
	exit 1
fi

pkill -x firecracker 2>/dev/null || true
sleep 1

dmesg >"${LOG_DIR}/dmesg-before.txt" 2>&1 || true
cat /proc/interrupts >"${LOG_DIR}/interrupts-before.txt" 2>&1 || true

pass_count=0
fail_count=0
i=1
while (( i <= PASSTHROUGH_RUNS )); do
	run_log="${LOG_DIR}/run${i}.log"
	meta="${LOG_DIR}/run${i}.meta"

	{
		echo "run=${i}"
		echo "start=$(date -Is)"
		echo "timeout=${VM_TIMEOUT}"
	} >"${meta}"
	dmesg >"${LOG_DIR}/dmesg-run${i}-before.txt" 2>&1 || true
	cat /proc/interrupts >"${LOG_DIR}/interrupts-run${i}-before.txt" 2>&1 || true

	set +e
	timeout -s INT -k 5 "${VM_TIMEOUT}" sh "${PASSTHROUGH_VM_RUNNER}" </dev/null >"${run_log}" 2>&1
	status=$?
	set -e

	{
		echo "timeout_status=${status}"
		echo "end=$(date -Is)"
	} >>"${meta}"

	sleep 1
	pkill -x firecracker 2>/dev/null || true
	sleep 1

	dmesg >"${LOG_DIR}/dmesg-run${i}-after.txt" 2>&1 || true
	cat /proc/interrupts >"${LOG_DIR}/interrupts-run${i}-after.txt" 2>&1 || true

	if grep -qa "Initialized panthor" "${run_log}" &&
	   ! grep -qaE "Failed to boot MCU|probe with driver panthor failed" "${run_log}"; then
		echo "result=PASS" >>"${meta}"
		pass_count=$((pass_count + 1))
	else
		echo "result=FAIL" >>"${meta}"
		fail_count=$((fail_count + 1))
	fi

	{
		echo
		echo "== panthor/gpu excerpts =="
		grep -aE "panthor|Panthor|GPU|MCU|drm|probe|irq|ERROR|WARN|Initialized" "${run_log}" | tail -n 120 || true
	} >>"${meta}"

	i=$((i + 1))
done

dmesg >"${LOG_DIR}/dmesg-after.txt" 2>&1 || true
cat /proc/interrupts >"${LOG_DIR}/interrupts-after.txt" 2>&1 || true
{
	dmesg | grep -aE "pmthor|panthor|inject irq|hardware quiesced|Failed to boot MCU|probe with driver panthor failed" | tail -n 240
} >"${LOG_DIR}/dmesg-summary.txt" 2>&1 || true

{
	echo "GPU passthrough panthor probe test result"
	echo "Run ID: ${RUN_ID}"
	echo "Timestamp: $(date -Is)"
	echo "Remote log dir: ${LOG_DIR}"
	echo "Runs: ${PASSTHROUGH_RUNS}"
	echo "Pass: ${pass_count}"
	echo "Fail: ${fail_count}"
	echo
	echo "== Per-run result =="
	for meta in "${LOG_DIR}"/run*.meta; do
		[[ -f "${meta}" ]] || continue
		printf '%s: ' "$(basename "${meta}" .meta)"
		awk -F= '/^(result|timeout_status)=/ {printf "%s=%s ", $1, $2} END {print ""}' "${meta}"
	done
	echo
	echo "== Guest panthor excerpts =="
	for run_log in "${LOG_DIR}"/run*.log; do
		[[ -f "${run_log}" ]] || continue
		echo "-- $(basename "${run_log}") --"
		grep -aE "panthor|Panthor|Failed to boot MCU|probe with driver panthor failed|Initialized panthor" "${run_log}" | tail -n 80 || true
	done
	echo
	echo "== Host pmthor excerpts =="
	sed -n '1,240p' "${LOG_DIR}/dmesg-summary.txt" 2>/dev/null || true
	echo
	if [[ "${fail_count}" -eq 0 ]]; then
		echo "RESULT: PASS"
	else
		echo "RESULT: FAIL"
	fi
} >"${LOG_DIR}/result"

cat "${LOG_DIR}/result"
if [[ "${fail_count}" -eq 0 ]]; then
	exit 0
fi
exit 1
REMOTE_SCRIPT
	remote_status=$?
	set -e

	log "Fetching GPU passthrough logs back to ${SFTP_LOG_ROOT}/passthrough/probe/${run_id}"
	mkdir -p "${SFTP_LOG_ROOT}/passthrough/probe"
	rsync_remote -av --info=stats2,name1 \
		"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_LOG_ROOT}/passthrough/probe/${run_id}/" \
		"${SFTP_LOG_ROOT}/passthrough/probe/${run_id}/" || true

	result="${SFTP_LOG_ROOT}/passthrough/probe/${run_id}/result"
	if [[ -f "${result}" ]]; then
		log "Result summary"
		sed -n '1,220p' "${result}"
		echo
		echo "Local logs: ${SFTP_LOG_ROOT}/passthrough/probe/${run_id}"
	fi

	return "${remote_status}"
}

require_cmd ssh
require_cmd rsync
require_cmd setsid

if [[ "${BUILD_HOST_KERNEL}" -eq 1 ]]; then
	build_host_kernel
fi
if [[ "${BUILD_FIRECRACKER}" -eq 1 ]]; then
	build_firecracker
fi
if [[ "${SYNC_TO_REMOTE}" -eq 1 ]]; then
	sync_to_remote
fi
if [[ "${INSTALL_AND_REBOOT}" -eq 1 ]]; then
	install_kernel_and_reboot
	log "Giving remote reboot time"
	sleep 15
	wait_for_remote
fi
if [[ "${RUN_TESTS}" -eq 1 ]]; then
	run_tests
fi
