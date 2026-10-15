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

REMOTE_HOST=${REMOTE_HOST:-192.168.31.18}
REMOTE_USER=${REMOTE_USER:-root}
REMOTE_PASS=${REMOTE_PASS:-root}
REMOTE_ROOT=${REMOTE_ROOT:-/root/GPU-SFTP}
REMOTE_BINS=${REMOTE_BINS:-"${REMOTE_ROOT}/firecracker-bins"}
REMOTE_LOG_ROOT=${REMOTE_LOG_ROOT:-"${REMOTE_ROOT}/log"}

RUN_ID=${RUN_ID:-$(date +%Y%m%d-%H%M%S)}
if [[ -z "${RUN_ID}" || "${RUN_ID}" == */* || "${RUN_ID}" == *..* ]]; then
	echo "invalid or empty RUN_ID: ${RUN_ID}" >&2
	exit 2
fi

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
GLES_SMOKE_ARGS=${GLES_SMOKE_ARGS:-}
GLES_WORKLOAD=${GLES_WORKLOAD:-compute}
GLES_GLMARK_SIZE=${GLES_GLMARK_SIZE:-1280x720}
GLES_GLMARK_FRAME_END=${GLES_GLMARK_FRAME_END:-finish}
GLES_GLMARK_PROGRESS_TRACE=${GLES_GLMARK_PROGRESS_TRACE:-1}
GLES_GLMARK_BENCHMARKS=${GLES_GLMARK_BENCHMARKS:-}
GLES_GLMARK_EXTRA_ARGS=${GLES_GLMARK_EXTRA_ARGS:-}
GLES_DRM_NODE=${GLES_DRM_NODE-/dev/dri/renderD128}
GLES_CLIENT_BO_MMAP_CACHED=${GLES_CLIENT_BO_MMAP_CACHED:-0}
GLES_REMOTE_BUILD=${GLES_REMOTE_BUILD:-1}
GLES_CLIENT_MEM_MIB=${GLES_CLIENT_MEM_MIB:-512}
GLES_PROXY_MEM_MIB=${GLES_PROXY_MEM_MIB:-512}
GLES_CLIENT_VCPUS=${GLES_CLIENT_VCPUS:-1}
GLES_PROXY_VCPUS=${GLES_PROXY_VCPUS:-1}
GLES_HOST_ONLINE_CPUS=${GLES_HOST_ONLINE_CPUS:-}
GLES_BROKER_CPUS=${GLES_BROKER_CPUS:-}
GLES_PROXY_CPUS=${GLES_PROXY_CPUS:-}
GLES_CLIENT_CPUS=${GLES_CLIENT_CPUS:-}
GLES_PANTHOR_SCHED_TICK_MS=${GLES_PANTHOR_SCHED_TICK_MS:-0}
GLES_PANTHOR_SCHED_HIGHPRI_WQ=${GLES_PANTHOR_SCHED_HIGHPRI_WQ:-0}
GLES_PROXY_PANTHOR_STATS=${GLES_PROXY_PANTHOR_STATS:-0}
# The shared client has no PRIME import/export. Use the supported offscreen
# frontend and wait for GPU completion; explicit backend overrides remain.
GLES_GLMARK_FLAVOR=${GLES_GLMARK_FLAVOR:-null-noop}
GLES_GLMARK_SKIP_VALIDATE=${GLES_GLMARK_SKIP_VALIDATE:-0}
GLES_GLMARK_PROGRESS_INTERVAL_S=${GLES_GLMARK_PROGRESS_INTERVAL_S:-5}
GLES_NCNN_LOOP_COUNT=${GLES_NCNN_LOOP_COUNT:-100}
GLES_NCNN_THREADS=${GLES_NCNN_THREADS:-2}
GLES_NCNN_GPU_DEVICE=${GLES_NCNN_GPU_DEVICE:-0}
GLES_NCNN_COOLING_DOWN=${GLES_NCNN_COOLING_DOWN:-0}
GLES_NCNN_TIMEOUT_S=${GLES_NCNN_TIMEOUT_S:-900}
GLES_NCNN_MODELS=${GLES_NCNN_MODELS:-"mobilenet_v2 mobilenet_v3 resnet50"}
GLES_RAW_VK_QUEUE_COUNTS=${GLES_RAW_VK_QUEUE_COUNTS:-1,2,3}
GLES_RAW_VK_SUBMIT_MODE=${GLES_RAW_VK_SUBMIT_MODE:-sequential}
GLES_RAW_VK_CASES=${GLES_RAW_VK_CASES:-full}
GLES_MIN_HOST_AVAILABLE_MIB=${GLES_MIN_HOST_AVAILABLE_MIB:-auto}
GLES_OBJECT_WINDOW_MIB=${GLES_OBJECT_WINDOW_MIB:-auto}

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
  --sync-file-snapshot-smoke Verify export across reset/destroy/DRM file close
  --group-lifecycle-smoke    Run ioctl smoke plus GROUP_CREATE/GET_STATE/DESTROY
  --group-submit-syncpoint-smoke
                             Run ioctl smoke plus zero-length GROUP_SUBMIT syncpoint
  --tiler-heap-lifecycle-smoke
                             Run ioctl smoke plus TILER_HEAP_CREATE/DESTROY
  --gles-compute-smoke       Boot the shared client with the base Panfrost
                             rootfs after injecting the GLES compute payload
                             and run
                             /root/gpu-smoke.sh correctness smoke
  --gles-glmark-smoke        Boot the shared client with the base Panfrost
                             rootfs and run the downloaded arm64 glmark2
                             off-screen suite through gpu-smoke.sh. Set
                             GLES_GLMARK_FLAVOR=gbm|gbm-render-only|gbm-render-only-debug|null|null-noop
                             to select the surface implementation (default: null-noop).
  --gles-ml-smoke            Boot the shared client with the base Panfrost
                             rootfs and run the GEMM/conv/reduction/softmax/
                             attention compute-kernel suite
  --gles-ncnn-smoke          Boot the shared client with the base Panfrost
                             rootfs and run real NCNN model graphs through
                             direct PanVK. Weights are zero-filled by benchncnn.
  --gles-raw-vk-smoke        Boot the shared client with a minimal direct-PanVK
                             queue/device/fence probe, independent of NCNN.
  --gles-smoke-args ARGS     Arguments passed to /root/gpu-smoke.sh in GLES mode
  --gles-glmark-size WxH    glmark2 off-screen size. Default: ${GLES_GLMARK_SIZE}
  GLES_GLMARK_FRAME_END     glmark2 --frame-end override: auto|none|finish
                            Default: finish.
  GLES_GLMARK_PROGRESS_TRACE
                            1 enables a periodic glmark2 scene/RSS/FD trace
  GLES_GLMARK_PROGRESS_INTERVAL_S
                            glmark2 progress sampling interval. Default: 5
  GLES_GLMARK_BENCHMARKS  Comma-separated glmark2 benchmark selectors. When
                            unset, run the full suite. Example:
                            build:use-vbo=false
  GLES_GLMARK_EXTRA_ARGS  Extra raw arguments appended to the glmark2
                            benchmark invocation. Use sparingly for bounded
                            diagnostics.
  GLES_NCNN_*               loop count, threads, GPU device, cooling down,
                            timeout, and model list for NCNN runs
  GLES_RAW_VK_QUEUE_COUNTS  comma-separated queue counts. Default: ${GLES_RAW_VK_QUEUE_COUNTS}
  GLES_RAW_VK_SUBMIT_MODE   sequential|concurrent. Default: ${GLES_RAW_VK_SUBMIT_MODE}
  GLES_RAW_VK_CASES         comma-separated reduction cases. Default: full
  GLES_DRM_NODE             Force the in-guest DRM node. The default is
                            /dev/dri/renderD128. Set it explicitly to an empty
                            string to use card-then-render-node discovery.
  --gles-client-bo-mmap-cached
                             In GLES mode, boot the shared client with
                             panthor_client.bo_mmap_cached=1 so BO payload
                             mmap uses cached WB instead of write-combine.
  --gles-client-mem-mib N   GLES client VM memory in MiB. Default: ${GLES_CLIENT_MEM_MIB}
  --gles-proxy-mem-mib N    GLES proxy VM memory in MiB. Default: ${GLES_PROXY_MEM_MIB}
  --gles-client-vcpus N     GLES client VM vCPU count. Default: ${GLES_CLIENT_VCPUS}
  --gles-proxy-vcpus N      GLES proxy VM vCPU count. Default: ${GLES_PROXY_VCPUS}
  GLES_OBJECT_WINDOW_MIB   Force the client vmshm object-window size, instead
                            of deriving it from --count. Default: auto.
  --gles-min-host-available-mib N|auto
                             Abort a GLES run when host MemAvailable is below
                             this threshold. Default: ${GLES_MIN_HOST_AVAILABLE_MIB}
  --gles-host-online-cpus LIST
                             Temporarily online host CPUs in LIST for a GLES
                             run, restoring CPUs that were originally offline.
  --gles-broker-cpus LIST   Run the per-run GLES vmshm-broker with taskset -c LIST.
  --gles-proxy-cpus LIST    Run the per-run GLES proxy Firecracker with taskset -c LIST.
  --gles-client-cpus LIST   Run the GLES client Firecracker with taskset -c LIST.
  --gles-proxy-panthor-stats
                             Enable Panthor submit/IRQ and vmshm RPC timing
                             statistics in diagnostic runs.
  --gles-panthor-sched-tick-ms N
                             Set the proxy Panthor scheduler tick in ms.
  --gles-panthor-sched-highpri-wq
                             Use a high-priority Panthor scheduler workqueue.
  --skip-gles-remote-build   Reuse the existing remote gles-compute-smoke
                             binary instead of rebuilding it on RK3588
  --run-id ID                Use a fixed run log directory name
  -h, --help                 Show this help

Environment overrides:
  SFTP_ROOT SFTP_BINS SFTP_LOG_ROOT
  BUILD_GUEST_VMSHM_KERNELS BUILD_FIRECRACKER_RUNTIME BUILD_PANTHOR_IOCTL_SMOKE
  GLES_REMOTE_BUILD
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
	--sync-file-snapshot-smoke)
		IOCTL_SMOKE=1
		IOCTL_SMOKE_MODE=sync-file-snapshot
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
	--gles-glmark-smoke)
		IOCTL_SMOKE=0
		GLES_COMPUTE_SMOKE=1
		GLES_WORKLOAD=glmark
		;;
	--gles-ml-smoke)
		IOCTL_SMOKE=0
		GLES_COMPUTE_SMOKE=1
		GLES_WORKLOAD=ml
		;;
	--gles-ncnn-smoke)
		IOCTL_SMOKE=0
		GLES_COMPUTE_SMOKE=1
		GLES_WORKLOAD=ncnn
		;;
	--gles-raw-vk-smoke)
		IOCTL_SMOKE=0
		GLES_COMPUTE_SMOKE=1
		GLES_WORKLOAD=raw-vk
		;;
	--gles-smoke-args)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-smoke-args requires an argument" >&2
			exit 2
		fi
		GLES_SMOKE_ARGS=$1
		;;
	--gles-glmark-size)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-glmark-size requires an argument" >&2
			exit 2
		fi
		if [[ ! "$1" =~ ^[0-9]+x[0-9]+$ ]]; then
			echo "--gles-glmark-size must be WxH: $1" >&2
			exit 2
		fi
		GLES_GLMARK_SIZE=$1
		;;
	--gles-client-bo-mmap-cached)
		GLES_CLIENT_BO_MMAP_CACHED=1
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
	--gles-min-host-available-mib)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-min-host-available-mib requires an argument" >&2
			exit 2
		fi
		GLES_MIN_HOST_AVAILABLE_MIB=$1
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
	--gles-client-cpus)
		shift
		if [[ $# -eq 0 ]]; then
			echo "--gles-client-cpus requires an argument" >&2
			exit 2
		fi
		GLES_CLIENT_CPUS=$1
		;;
	--gles-proxy-panthor-stats)
		GLES_PROXY_PANTHOR_STATS=1
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
	--skip-gles-remote-build)
		GLES_REMOTE_BUILD=0
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

# --count belongs to gles-compute-smoke, not gles-ml-smoke. Keep the old
# compute default, but make an accidental ML default/explicit --count fail at
# the launcher instead of showing up as workload rc=2 inside the guest.
if [[ -z "${GLES_SMOKE_ARGS}" ]]; then
	if [[ "${GLES_WORKLOAD}" == "ml" ]]; then
		GLES_SMOKE_ARGS=""
	else
		GLES_SMOKE_ARGS="--count 64"
	fi
fi
if [[ "${GLES_WORKLOAD}" == "ml" && " ${GLES_SMOKE_ARGS} " == *" --count "* ]]; then
	echo "GLES_SMOKE_ARGS '--count' is invalid for --gles-ml-smoke; use --iterations/--warmup/--gemm-size/--attention-size/--kernel" >&2
	exit 2
fi

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
		-oServerAliveInterval=15 \
		-oServerAliveCountMax=6 \
		"${REMOTE_USER}@${REMOTE_HOST}" \
		"$@"
}

rsync_remote() {
	with_ssh_password env \
		RSYNC_RSH="ssh -p 22 -oBatchMode=no -oStrictHostKeyChecking=accept-new -oServerAliveInterval=15 -oServerAliveCountMax=6" \
		rsync "$@"
}

remote_has_cmd() {
	local cmd="$1"

	ssh_remote "command -v $(quote "${cmd}") >/dev/null 2>&1"
}

tar_fetch_logs() {
	local remote_log="${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"
	local local_log="${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"

	remote_has_cmd tar || die "remote host is missing both rsync and tar"

	log "Remote rsync missing; fetching logs via tar stream"
	mkdir -p "${local_log}"
	ssh_remote "cd $(quote "${remote_log}") && tar -cf - ." |
		tar -C "${local_log}" -xf -
}

tar_sync_to_remote() {
	remote_has_cmd tar || die "remote host is missing both rsync and tar"

	log "Remote rsync missing; syncing selected GPU-SFTP tree via tar stream"
	ssh_remote "mkdir -p $(quote "${REMOTE_ROOT}")"
	tar -C "${SFTP_ROOT}" \
		--exclude='./.git' \
		--exclude='./.vscode' \
		--exclude='./node_modules' \
		--exclude='./log' \
		--exclude='./firecracker-bins/run-logs' \
		--exclude='./firecracker-bins/rootfs' \
		--exclude='./linux-host-kernel' \
		--exclude='./linux-host-kernel/' \
		-cf - . |
		ssh_remote "tar -C $(quote "${REMOTE_ROOT}") --overwrite -xf -"
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
	if remote_has_cmd rsync; then
		rsync_remote -av --info=stats2,name1 \
			"${excludes[@]}" \
			"${SFTP_ROOT}/" \
			"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_ROOT}/"
	else
		tar_sync_to_remote
	fi

	migrate_remote_gpu_sftp_layout
}

run_remote_test() {
	local run_id_q remote_root_q remote_bins_q remote_log_root_q clean_q
	local ioctl_smoke_q ioctl_smoke_mode_q
	local gles_compute_smoke_q gles_smoke_args_q
	local gles_workload_q gles_glmark_size_q
	local gles_client_bo_mmap_cached_q
	local gles_remote_build_q
	local gles_glmark_skip_validate_q
	local gles_glmark_flavor_q
	local gles_glmark_frame_end_q
	local gles_glmark_progress_trace_q
	local gles_glmark_progress_interval_q
	local gles_glmark_benchmarks_q gles_glmark_extra_args_q
	local gles_drm_node_q
	local gles_client_mem_mib_q gles_proxy_mem_mib_q
	local gles_client_vcpus_q gles_proxy_vcpus_q
	local gles_min_host_available_mib_q
	local gles_host_online_cpus_q gles_broker_cpus_q gles_proxy_cpus_q gles_client_cpus_q
	local gles_ncnn_loop_count_q gles_ncnn_threads_q gles_ncnn_gpu_device_q
	local gles_ncnn_cooling_down_q gles_ncnn_timeout_q gles_ncnn_models_q
	local gles_raw_vk_queue_counts_q gles_raw_vk_submit_mode_q
	local gles_raw_vk_cases_q
	local gles_object_window_mib_q

	run_id_q=$(quote "${RUN_ID}")
	remote_root_q=$(quote "${REMOTE_ROOT}")
	remote_bins_q=$(quote "${REMOTE_BINS}")
	remote_log_root_q=$(quote "${REMOTE_LOG_ROOT}")
	clean_q=$(quote "${CLEAN_REMOTE_PROCS}")
	ioctl_smoke_q=$(quote "${IOCTL_SMOKE}")
	ioctl_smoke_mode_q=$(quote "${IOCTL_SMOKE_MODE}")
	gles_compute_smoke_q=$(quote "${GLES_COMPUTE_SMOKE}")
	gles_smoke_args_q=$(quote "${GLES_SMOKE_ARGS}")
	gles_workload_q=$(quote "${GLES_WORKLOAD}")
	gles_glmark_size_q=$(quote "${GLES_GLMARK_SIZE}")
	gles_client_bo_mmap_cached_q=$(quote "${GLES_CLIENT_BO_MMAP_CACHED}")
	gles_remote_build_q=$(quote "${GLES_REMOTE_BUILD}")
	gles_glmark_flavor_q=$(quote "${GLES_GLMARK_FLAVOR}")
	gles_glmark_skip_validate_q=$(quote "${GLES_GLMARK_SKIP_VALIDATE}")
	gles_glmark_frame_end_q=$(quote "${GLES_GLMARK_FRAME_END}")
	gles_glmark_progress_trace_q=$(quote "${GLES_GLMARK_PROGRESS_TRACE}")
	gles_glmark_progress_interval_q=$(quote "${GLES_GLMARK_PROGRESS_INTERVAL_S}")
	gles_glmark_benchmarks_q=$(quote "${GLES_GLMARK_BENCHMARKS}")
	gles_glmark_extra_args_q=$(quote "${GLES_GLMARK_EXTRA_ARGS}")
	gles_drm_node_q=$(quote "${GLES_DRM_NODE}")
	gles_client_mem_mib_q=$(quote "${GLES_CLIENT_MEM_MIB}")
	gles_proxy_mem_mib_q=$(quote "${GLES_PROXY_MEM_MIB}")
	gles_client_vcpus_q=$(quote "${GLES_CLIENT_VCPUS}")
	gles_proxy_vcpus_q=$(quote "${GLES_PROXY_VCPUS}")
	gles_min_host_available_mib_q=$(quote "${GLES_MIN_HOST_AVAILABLE_MIB}")
	gles_host_online_cpus_q=$(quote "${GLES_HOST_ONLINE_CPUS}")
	gles_broker_cpus_q=$(quote "${GLES_BROKER_CPUS}")
	gles_proxy_cpus_q=$(quote "${GLES_PROXY_CPUS}")
	gles_client_cpus_q=$(quote "${GLES_CLIENT_CPUS}")
	gles_ncnn_loop_count_q=$(quote "${GLES_NCNN_LOOP_COUNT}")
	gles_ncnn_threads_q=$(quote "${GLES_NCNN_THREADS}")
	gles_ncnn_gpu_device_q=$(quote "${GLES_NCNN_GPU_DEVICE}")
	gles_ncnn_cooling_down_q=$(quote "${GLES_NCNN_COOLING_DOWN}")
	gles_ncnn_timeout_q=$(quote "${GLES_NCNN_TIMEOUT_S}")
	gles_ncnn_models_q=$(quote "${GLES_NCNN_MODELS}")
	gles_raw_vk_queue_counts_q=$(quote "${GLES_RAW_VK_QUEUE_COUNTS}")
	gles_raw_vk_submit_mode_q=$(quote "${GLES_RAW_VK_SUBMIT_MODE}")
	gles_raw_vk_cases_q=$(quote "${GLES_RAW_VK_CASES}")
	gles_object_window_mib_q=$(quote "${GLES_OBJECT_WINDOW_MIB}")

	log "Running remote vmshm test: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BINS}"
	ssh_remote "RUN_ID=${run_id_q} REMOTE_ROOT=${remote_root_q} REMOTE_BINS=${remote_bins_q} REMOTE_LOG_ROOT=${remote_log_root_q} CLEAN_REMOTE_PROCS=${clean_q} IOCTL_SMOKE=${ioctl_smoke_q} IOCTL_SMOKE_MODE=${ioctl_smoke_mode_q} GLES_COMPUTE_SMOKE=${gles_compute_smoke_q} GLES_SMOKE_ARGS=${gles_smoke_args_q} GLES_WORKLOAD=${gles_workload_q} GLES_GLMARK_SIZE=${gles_glmark_size_q} GLES_GLMARK_FLAVOR=${gles_glmark_flavor_q} GLES_GLMARK_SKIP_VALIDATE=${gles_glmark_skip_validate_q} GLES_GLMARK_FRAME_END=${gles_glmark_frame_end_q} GLES_GLMARK_PROGRESS_TRACE=${gles_glmark_progress_trace_q} GLES_GLMARK_PROGRESS_INTERVAL_S=${gles_glmark_progress_interval_q} GLES_GLMARK_BENCHMARKS=${gles_glmark_benchmarks_q} GLES_GLMARK_EXTRA_ARGS=${gles_glmark_extra_args_q} GLES_NCNN_LOOP_COUNT=${gles_ncnn_loop_count_q} GLES_NCNN_THREADS=${gles_ncnn_threads_q} GLES_NCNN_GPU_DEVICE=${gles_ncnn_gpu_device_q} GLES_NCNN_COOLING_DOWN=${gles_ncnn_cooling_down_q} GLES_NCNN_TIMEOUT_S=${gles_ncnn_timeout_q} GLES_NCNN_MODELS=${gles_ncnn_models_q} GLES_RAW_VK_QUEUE_COUNTS=${gles_raw_vk_queue_counts_q} GLES_RAW_VK_SUBMIT_MODE=${gles_raw_vk_submit_mode_q} GLES_RAW_VK_CASES=${gles_raw_vk_cases_q} GLES_DRM_NODE=${gles_drm_node_q} GLES_CLIENT_BO_MMAP_CACHED=${gles_client_bo_mmap_cached_q} GLES_REMOTE_BUILD=${gles_remote_build_q} GLES_CLIENT_MEM_MIB=${gles_client_mem_mib_q} GLES_PROXY_MEM_MIB=${gles_proxy_mem_mib_q} GLES_CLIENT_VCPUS=${gles_client_vcpus_q} GLES_PROXY_VCPUS=${gles_proxy_vcpus_q} GLES_MIN_HOST_AVAILABLE_MIB=${gles_min_host_available_mib_q} GLES_OBJECT_WINDOW_MIB=${gles_object_window_mib_q} GLES_HOST_ONLINE_CPUS=${gles_host_online_cpus_q} GLES_BROKER_CPUS=${gles_broker_cpus_q} GLES_PROXY_CPUS=${gles_proxy_cpus_q} GLES_CLIENT_CPUS=${gles_client_cpus_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_BINS}"
LOG_DIR="${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}"
mkdir -p /run/vmshm "${LOG_DIR}"
SMOKE_CLIENT_CONFIG="${LOG_DIR}/client-ioctl-smoke-config.json"
GLES_CLIENT_CONFIG="${LOG_DIR}/client-gles-compute-config.json"
GLES_PROXY_CONFIG="${LOG_DIR}/proxy-gles-config.json"
GLES_BROKER_CONFIG="${LOG_DIR}/broker-config.toml"
GLES_CPU_RESTORE_FILE="${LOG_DIR}/host-cpu-restore.txt"
GLES_SMOKE_SRC_DIR="${REMOTE_ROOT}/tests/gpu-compute-smoke"
GLES_SMOKE_BIN="${REMOTE_BINS}/bin/gles-compute-smoke"
GLES_ML_SRC_DIR="${REMOTE_ROOT}/tests/gpu-ml-smoke"
GLES_ML_BIN="${REMOTE_BINS}/bin/gles-ml-smoke"
GLMARK_PAYLOAD_SRC="${REMOTE_ROOT}/artifacts/glmark2-arm64/rootfs-${GLES_GLMARK_FLAVOR}"
NCNN_PAYLOAD_SRC="${REMOTE_ROOT}/artifacts/ncnn-arm64/rootfs-ncnn"
RAW_VK_PROBE_SRC="${REMOTE_ROOT}/tests/vulkan-bench/bin/raw-vk-probe"
SMOKE_MNT=""
GLES_WORKLOAD=${GLES_WORKLOAD:-compute}
GLES_GLMARK_SIZE=${GLES_GLMARK_SIZE:-1280x720}
GLES_GLMARK_FRAME_END=${GLES_GLMARK_FRAME_END:-finish}
GLES_GLMARK_FLAVOR=${GLES_GLMARK_FLAVOR:-null-noop}
GLES_GLMARK_SKIP_VALIDATE=${GLES_GLMARK_SKIP_VALIDATE:-0}
GLES_GLMARK_PROGRESS_TRACE=${GLES_GLMARK_PROGRESS_TRACE:-1}
GLES_GLMARK_PROGRESS_INTERVAL_S=${GLES_GLMARK_PROGRESS_INTERVAL_S:-5}
GLES_GLMARK_BENCHMARKS=${GLES_GLMARK_BENCHMARKS:-}
GLES_GLMARK_EXTRA_ARGS=${GLES_GLMARK_EXTRA_ARGS:-}
GLES_NCNN_LOOP_COUNT=${GLES_NCNN_LOOP_COUNT:-100}
GLES_NCNN_THREADS=${GLES_NCNN_THREADS:-2}
GLES_NCNN_GPU_DEVICE=${GLES_NCNN_GPU_DEVICE:-0}
GLES_NCNN_COOLING_DOWN=${GLES_NCNN_COOLING_DOWN:-0}
GLES_NCNN_TIMEOUT_S=${GLES_NCNN_TIMEOUT_S:-900}
GLES_NCNN_MODELS=${GLES_NCNN_MODELS:-"mobilenet_v2 mobilenet_v3 resnet50"}
GLES_RAW_VK_QUEUE_COUNTS=${GLES_RAW_VK_QUEUE_COUNTS:-1,2,3}
GLES_RAW_VK_SUBMIT_MODE=${GLES_RAW_VK_SUBMIT_MODE:-sequential}
GLES_RAW_VK_CASES=${GLES_RAW_VK_CASES:-full}
GLES_DRM_NODE=${GLES_DRM_NODE-}
GLES_CLIENT_BO_MMAP_CACHED=${GLES_CLIENT_BO_MMAP_CACHED:-0}
GLES_REMOTE_BUILD=${GLES_REMOTE_BUILD:-1}
GLES_CLIENT_MEM_MIB=${GLES_CLIENT_MEM_MIB:-512}
GLES_PROXY_MEM_MIB=${GLES_PROXY_MEM_MIB:-512}
GLES_CLIENT_VCPUS=${GLES_CLIENT_VCPUS:-1}
GLES_PROXY_VCPUS=${GLES_PROXY_VCPUS:-1}
GLES_MIN_HOST_AVAILABLE_MIB=${GLES_MIN_HOST_AVAILABLE_MIB:-auto}
GLES_OBJECT_WINDOW_MIB=${GLES_OBJECT_WINDOW_MIB:-auto}
GLES_HOST_ONLINE_CPUS=${GLES_HOST_ONLINE_CPUS:-}
GLES_BROKER_CPUS=${GLES_BROKER_CPUS:-}
GLES_PROXY_CPUS=${GLES_PROXY_CPUS:-}
GLES_CLIENT_CPUS=${GLES_CLIENT_CPUS:-}

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

	case "${GLES_WORKLOAD}" in
		ncnn)
			# ResNet50 includes a 152 MiB BO, rounded to a 256 MiB
			# buddy allocation, alongside persistent model buffers.
			printf '768\n'
			return
			;;
		glmark)
			# The full 1080p suite exhausts the 224 MiB compute window
			# in terrain/shadow scenes, even with free host memory.
			printf '512\n'
			return
			;;
	esac

	case "${count}" in
		33554432)
			printf '224\n'
			;;
		16777216)
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

# Keep the object window comfortably larger than the workload BO. Mesa creates
# internal BOs and the Panthor allocator reserves part of the same vmshm
# window, so a 128 MiB window cannot host a 128 MiB workload BO.
# GLES_OBJECT_WINDOW_MIB explicitly overrides the workload-specific default.
if [[ "${GLES_OBJECT_WINDOW_MIB}" == "auto" ]]; then
	GLES_OBJECT_WINDOW_MIB=128
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		GLES_SMOKE_COUNT=$(gles_smoke_count)
		GLES_OBJECT_WINDOW_MIB=$(gles_object_window_mib_for_count "${GLES_SMOKE_COUNT}")
	fi
fi
GLES_OBJECT_WINDOW_BYTES=$((GLES_OBJECT_WINDOW_MIB * 1024 * 1024))
# The legacy window starts below the VMM's UART/virtio MMIO at 1 GiB.
# Larger capacities must move as a whole; extending it in place hides MMIO
# behind a RAM memslot and can prevent even the proxy console from booting.
GLES_OBJECT_WINDOW_GPA=0x30000000
if [[ "${GLES_OBJECT_WINDOW_MIB}" -gt 256 ]]; then
	GLES_OBJECT_WINDOW_GPA=0x100000000
fi

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

cleanup_vmshm_run() {
	cleanup_ioctl_smoke_rootfs
	restore_host_online_cpus
}
trap cleanup_vmshm_run EXIT

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

wait_for_client_log() {
	local file="$1"
	local pattern="$2"
	local timeout="$3"
	local pid_file="$4"
	local pid
	local i=0

	while [[ "${i}" -lt "${timeout}" ]]; do
		if grep -qaE "${pattern}" "${file}" 2>/dev/null; then
			return 0
		fi
		pid=$(cat "${pid_file}" 2>/dev/null || true)
		if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
			echo "client process exited before producing a result marker (pid=${pid:-missing})" >&2
			return 1
		fi
		i=$((i + 1))
		sleep 1
	done
	return 1
}

record_client_exit_if_done() {
	local pid_file="$1"
	local out_file="$2"
	local pid rc state

	[[ -f "${out_file}" ]] && return 0
	pid=$(cat "${pid_file}" 2>/dev/null || true)
	[[ -n "${pid}" ]] || return 0
	# A zombie Firecracker still satisfies kill -0.  Treat /proc state Z as
	# exited so wait(1pid) can reap it and preserve the real exit status.
	state=$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null || true)
	if [[ -n "${state}" && "${state}" != "Z" ]]; then
		return 0
	fi
	if [[ -z "${state}" ]] && kill -0 "${pid}" 2>/dev/null; then
		return 0
	fi
	{
		set +e
		wait "${pid}"
		rc=$?
		set -e
	}
	echo "client_firecracker_pid=${pid}" >"${out_file}"
	echo "client_firecracker_exit_code=${rc}" >>"${out_file}"
	date -Is >>"${out_file}"
	free -m 2>/dev/null >>"${out_file}" || true
	dmesg 2>/dev/null | tail -n 120 >>"${out_file}" || true
	printf 'CLIENT_FIRECRACKER_EXIT_CODE=%s\n' "${rc}" >>"${LOG_DIR}/client.log"
	return 0
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

mem_available_mib() {
	awk '/^MemAvailable:/ {printf "%d\n", $2 / 1024; found=1} END {if (!found) print 0}' /proc/meminfo 2>/dev/null
}

write_mem_snapshot() {
	local label="$1"

	{
		echo "== ${label} =="
		echo "ts=$(date -Is)"
		echo "mem_available_mib=$(mem_available_mib)"
		free -m 2>/dev/null || true
	} >>"${LOG_DIR}/preflight.txt"
}

expand_cpu_list() {
	local list="$1"
	local item start end cpu

	for item in ${list//,/ }; do
		[[ -n "${item}" ]] || continue
		if [[ "${item}" =~ ^([0-9]+)-([0-9]+)$ ]]; then
			start="${BASH_REMATCH[1]}"
			end="${BASH_REMATCH[2]}"
			[[ "${start}" -le "${end}" ]] || return 1
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
		echo "== ${label} =="
		echo "ts=$(date -Is)"
		echo "online_cpus=$(host_online_cpus)"
		echo "requested_online_cpus=${GLES_HOST_ONLINE_CPUS:-}"
		echo "broker_cpus=${GLES_BROKER_CPUS:-}"
		echo "proxy_cpus=${GLES_PROXY_CPUS:-}"
		echo "client_cpus=${GLES_CLIENT_CPUS:-}"
	} >>"${LOG_DIR}/affinity.log"
}

restore_host_online_cpus() {
	local cpu

	[[ -f "${GLES_CPU_RESTORE_FILE}" ]] || return 0
	{
		echo "== restore host cpu online state =="
		echo "before_restore=$(host_online_cpus)"
	} >>"${LOG_DIR}/affinity.log"
	while read -r cpu; do
		[[ -n "${cpu}" ]] || continue
		if [[ -w "/sys/devices/system/cpu/cpu${cpu}/online" ]]; then
			printf '0\n' >"/sys/devices/system/cpu/cpu${cpu}/online" 2>>"${LOG_DIR}/affinity.log" || true
		fi
	done <"${GLES_CPU_RESTORE_FILE}"
	echo "after_restore=$(host_online_cpus)" >>"${LOG_DIR}/affinity.log"
	rm -f "${GLES_CPU_RESTORE_FILE}"
}

apply_host_online_cpus() {
	local cpu was_online

	: >"${GLES_CPU_RESTORE_FILE}"
	write_affinity_snapshot "before optional host cpu online"
	[[ -n "${GLES_HOST_ONLINE_CPUS}" ]] || return 0

	expand_cpu_list "${GLES_HOST_ONLINE_CPUS}" >/dev/null ||
		{ echo "invalid GLES_HOST_ONLINE_CPUS=${GLES_HOST_ONLINE_CPUS}" >"${LOG_DIR}/result"; return 2; }
	while read -r cpu; do
		[[ -n "${cpu}" ]] || continue
		if [[ ! -d "/sys/devices/system/cpu/cpu${cpu}" ]]; then
			echo "missing requested host cpu${cpu}" >"${LOG_DIR}/result"
			return 2
		fi
		[[ -e "/sys/devices/system/cpu/cpu${cpu}/online" ]] || continue
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
	command -v taskset >/dev/null 2>&1 ||
		{ echo "taskset is required for ${label} affinity" >"${LOG_DIR}/result"; return 2; }
	taskset -c "${cpus}" true 2>>"${LOG_DIR}/affinity.log" ||
		{ echo "invalid ${label} taskset CPU/list: ${cpus}" >"${LOG_DIR}/result"; return 2; }
}

validate_gles_launch_settings() {
	local setting

	for setting in \
		"gles_client_mem_mib:${GLES_CLIENT_MEM_MIB}" \
		"gles_proxy_mem_mib:${GLES_PROXY_MEM_MIB}" \
		"gles_client_vcpus:${GLES_CLIENT_VCPUS}" \
		"gles_proxy_vcpus:${GLES_PROXY_VCPUS}"; do
		if ! [[ "${setting#*:}" =~ ^[1-9][0-9]*$ ]]; then
			echo "invalid ${setting%%:*}=${setting#*:}" >"${LOG_DIR}/result"
			return 2
		fi
	done
	if ! [[ "${GLES_MIN_HOST_AVAILABLE_MIB}" == "auto" || "${GLES_MIN_HOST_AVAILABLE_MIB}" =~ ^[0-9]+$ ]]; then
		echo "invalid gles_min_host_available_mib=${GLES_MIN_HOST_AVAILABLE_MIB}" >"${LOG_DIR}/result"
		return 2
	fi
	if ! [[ "${GLES_OBJECT_WINDOW_MIB}" == "auto" || "${GLES_OBJECT_WINDOW_MIB}" =~ ^[1-9][0-9]*$ ]]; then
		echo "invalid gles_object_window_mib=${GLES_OBJECT_WINDOW_MIB}" >"${LOG_DIR}/result"
		return 2
	fi
	validate_taskset_list broker "${GLES_BROKER_CPUS}"
	validate_taskset_list proxy "${GLES_PROXY_CPUS}"
	validate_taskset_list client "${GLES_CLIENT_CPUS}"
	write_affinity_snapshot "after taskset validation"
}

gles_preflight_host_memory() {
	local threshold mode available

	[[ "${GLES_COMPUTE_SMOKE}" == "1" ]] || return 0
	if [[ "${GLES_MIN_HOST_AVAILABLE_MIB}" == "auto" ]]; then
		threshold=900
		# Account for the configured guests and shared payload capacity;
		# a large NCNN window must not pass the old 900 MiB-only check.
		local capacity_threshold=$((GLES_CLIENT_MEM_MIB + GLES_PROXY_MEM_MIB + GLES_OBJECT_WINDOW_MIB + 256))
		if [[ "${capacity_threshold}" -gt "${threshold}" ]]; then
			threshold="${capacity_threshold}"
		fi
		mode=auto-oneclient
	else
		threshold="${GLES_MIN_HOST_AVAILABLE_MIB}"
		mode=manual
	fi
	write_mem_snapshot "before GLES launch"
	available=$(mem_available_mib)
	{
		echo "gles_client_mem_mib=${GLES_CLIENT_MEM_MIB}"
		echo "gles_proxy_mem_mib=${GLES_PROXY_MEM_MIB}"
		echo "gles_client_vcpus=${GLES_CLIENT_VCPUS}"
		echo "gles_proxy_vcpus=${GLES_PROXY_VCPUS}"
		echo "gles_object_window_mib=${GLES_OBJECT_WINDOW_MIB}"
		echo "gles_object_window_bytes=${GLES_OBJECT_WINDOW_BYTES}"
		echo "gles_object_window_gpa=${GLES_OBJECT_WINDOW_GPA}"
		echo "gles_min_host_available_mib=${threshold}"
		echo "gles_min_host_available_mode=${mode}"
		echo "gles_mem_available_mib=${available}"
		echo "gles_host_online_cpus=$(host_online_cpus)"
	} >>"${LOG_DIR}/preflight.txt"
	if [[ "${threshold}" -gt 0 && "${available}" -lt "${threshold}" ]]; then
		echo "insufficient host memory: available=${available} MiB threshold=${threshold} MiB" >"${LOG_DIR}/result"
		return 2
	fi
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
	sync-file-snapshot)
		smoke_arg="--sync-file-snapshot"
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

if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	validate_gles_launch_settings
	gles_preflight_host_memory
	apply_host_online_cpus
fi

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
      "guest_phys_addr": "${GLES_OBJECT_WINDOW_GPA}",
      "slot": 1,
      "expected_size": ${GLES_OBJECT_WINDOW_BYTES},
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
	if [[ "${GLES_REMOTE_BUILD}" != "1" ]]; then
		[[ -x "${GLES_SMOKE_BIN}" ]] ||
			{ echo "missing executable ${GLES_SMOKE_BIN}; rerun without --skip-gles-remote-build" >&2; return 1; }
		echo "reusing existing ${GLES_SMOKE_BIN}" >&2
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

build_gles_ml_smoke() {
	if [[ "${GLES_WORKLOAD}" != "ml" ]]; then
		return 0
	fi
	if [[ "${GLES_REMOTE_BUILD}" != "1" ]]; then
		[[ -x "${GLES_ML_BIN}" ]] ||
			{ echo "missing executable ${GLES_ML_BIN}; rerun without --skip-gles-remote-build" >&2; return 1; }
		echo "reusing existing ${GLES_ML_BIN}" >&2
		return 0
	fi

	echo "building current gles-ml-smoke from ${GLES_ML_SRC_DIR}" >&2
	[[ -f "${GLES_ML_SRC_DIR}/gles_ml_smoke.c" ]] ||
		{ echo "missing ${GLES_ML_SRC_DIR}/gles_ml_smoke.c" >&2; return 1; }
	command -v cc >/dev/null 2>&1 ||
		{ echo "missing cc on remote host" >&2; return 1; }
	command -v pkg-config >/dev/null 2>&1 ||
		{ echo "pkg-config unavailable; using explicit EGL/GLES/GBM link flags" 2>&1; }

	mkdir -p "$(dirname "${GLES_ML_BIN}")"
	local gles_ml_flags=""
	if command -v pkg-config >/dev/null 2>&1; then
		gles_ml_flags=$(pkg-config --cflags --libs egl glesv2 gbm)
	else
		gles_ml_flags="-lEGL -lGLESv2 -lgbm"
	fi
	cc -O2 -Wall -Wextra -std=c11 \
		"${GLES_ML_SRC_DIR}/gles_ml_smoke.c" \
		-o "${GLES_ML_BIN}" \
		${gles_ml_flags} -lm
	chmod 0755 "${GLES_ML_BIN}"
	"${GLES_ML_BIN}" --help >/dev/null 2>&1
	echo "installed ${GLES_ML_BIN}" >&2
}

inject_gles_compute_payload() {
	local rootfs_path="${REMOTE_BINS}/rootfs/rootfs-panfrost.ext4"
	local glmark_lib
	local glmark_binary

	[[ -f "${rootfs_path}" ]] ||
		{ echo "missing ${rootfs_path} on remote" >&2; return 1; }
	[[ -f "${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/gles_compute_smoke.c" >&2; return 1; }
	[[ -f "${GLES_SMOKE_SRC_DIR}/gpu-smoke.sh" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/gpu-smoke.sh" >&2; return 1; }
	[[ -f "${GLES_SMOKE_SRC_DIR}/init" ]] ||
		{ echo "missing ${GLES_SMOKE_SRC_DIR}/init" >&2; return 1; }
	if [[ "${GLES_WORKLOAD}" == "ml" ]]; then
		[[ -f "${GLES_ML_SRC_DIR}/gles_ml_smoke.c" ]] ||
			{ echo "missing ${GLES_ML_SRC_DIR}/gles_ml_smoke.c" >&2; return 1; }
	fi
	if [[ "${GLES_WORKLOAD}" == "ncnn" ]]; then
		[[ -x "${NCNN_PAYLOAD_SRC}/bin/benchncnn" ]] ||
			{ echo "missing executable ${NCNN_PAYLOAD_SRC}/bin/benchncnn" >&2; return 1; }
		[[ -x "${NCNN_PAYLOAD_SRC}/bin/ncnn-vk-probe" ]] ||
			{ echo "missing executable ${NCNN_PAYLOAD_SRC}/bin/ncnn-vk-probe" >&2; return 1; }
		[[ -f "${NCNN_PAYLOAD_SRC}/libs/libvulkan_panfrost.so" ]] ||
			{ echo "missing direct PanVK driver under ${NCNN_PAYLOAD_SRC}/libs" >&2; return 1; }
		[[ -f "${NCNN_PAYLOAD_SRC}/libs/libgomp.so.1" ]] ||
			{ echo "missing NCNN OpenMP runtime ${NCNN_PAYLOAD_SRC}/libs/libgomp.so.1" >&2; return 1; }
		for ncnn_runtime_lib in libm.so.6 libmvec.so.1; do
			[[ -f "${NCNN_PAYLOAD_SRC}/libs/${ncnn_runtime_lib}" ]] ||
				{ echo "missing NCNN runtime library ${NCNN_PAYLOAD_SRC}/libs/${ncnn_runtime_lib}" >&2; return 1; }
		done
		for ncnn_model in ${GLES_NCNN_MODELS}; do
			[[ -f "${NCNN_PAYLOAD_SRC}/models/${ncnn_model}.param" ]] ||
				{ echo "missing NCNN model ${ncnn_model}.param" >&2; return 1; }
		done
	fi
	if [[ "${GLES_WORKLOAD}" == "raw-vk" ]]; then
		[[ -x "${RAW_VK_PROBE_SRC}" ]] ||
			{ echo "missing executable ${RAW_VK_PROBE_SRC}" >&2; return 1; }
		[[ -f "${NCNN_PAYLOAD_SRC}/libs/libvulkan_panfrost.so" ]] ||
			{ echo "missing direct PanVK driver under ${NCNN_PAYLOAD_SRC}/libs" >&2; return 1; }
		[[ -f "${NCNN_PAYLOAD_SRC}/libs/libstdc++.so.6" ]] ||
			{ echo "missing raw-probe C++ runtime under ${NCNN_PAYLOAD_SRC}/libs" >&2; return 1; }
		[[ -f "${NCNN_PAYLOAD_SRC}/libs/libgcc_s.so.1" ]] ||
			{ echo "missing raw-probe GCC runtime under ${NCNN_PAYLOAD_SRC}/libs" >&2; return 1; }
	fi
	if [[ "${GLES_WORKLOAD}" == "glmark" ]]; then
		case "${GLES_GLMARK_FLAVOR}" in
			gbm) glmark_binary=glmark2-es2-gbm ;;
			gbm-render-only) glmark_binary=glmark2-es2-gbm ;;
			gbm-render-only-debug) glmark_binary=glmark2-es2-gbm ;;
			null) glmark_binary=glmark2-es2-null ;;
			null-noop) glmark_binary=glmark2-es2-null-noop ;;
			*)
				echo "unsupported GLES_GLMARK_FLAVOR=${GLES_GLMARK_FLAVOR}; expected gbm, gbm-render-only, gbm-render-only-debug, null, or null-noop" >&2
				return 1
				;;
		esac
		[[ -x "${GLMARK_PAYLOAD_SRC}/usr/bin/${glmark_binary}" ]] ||
			{ echo "missing ${GLMARK_PAYLOAD_SRC}/usr/bin/${glmark_binary}" >&2; return 1; }
		[[ -d "${GLMARK_PAYLOAD_SRC}/usr/share/glmark2" ]] ||
			{ echo "missing ${GLMARK_PAYLOAD_SRC}/usr/share/glmark2" >&2; return 1; }
	fi

	build_gles_compute_smoke
	build_gles_ml_smoke
	echo "rootfs_payload_inject_start payload=gles-${GLES_WORKLOAD} rootfs=${rootfs_path} ts=$(date -Is)" >&2
	SMOKE_MNT=$(mktemp -d /tmp/panthor-gles-rootfs.XXXXXX)
	mount -o loop,rw "${rootfs_path}" "${SMOKE_MNT}"

	install -Dm0755 "${GLES_SMOKE_BIN}" "${SMOKE_MNT}/root/gles-compute-smoke"
	if [[ "${GLES_WORKLOAD}" == "ml" ]]; then
		install -Dm0755 "${GLES_ML_BIN}" "${SMOKE_MNT}/root/gles-ml-smoke"
	fi
	install -Dm0755 "${GLES_SMOKE_SRC_DIR}/gpu-smoke.sh" "${SMOKE_MNT}/root/gpu-smoke.sh"
	install -Dm0755 "${GLES_SMOKE_SRC_DIR}/init" "${SMOKE_MNT}/init"

	# The trimmed rootfs intentionally has no awk.  The glmark2 and NCNN
	# parsers use awk to tolerate CRLF and mixed progress output; install the
	# host's libc-only mawk binary just as timeout/tr are installed below.
	if [[ "${GLES_WORKLOAD}" == "glmark" || "${GLES_WORKLOAD}" == "ncnn" ]]; then
		if [[ ! -x "${SMOKE_MNT}/usr/bin/awk" ]]; then
			local awk_host_tool
			awk_host_tool=$(command -v awk || true)
			[[ -n "${awk_host_tool}" && -x "${awk_host_tool}" ]] ||
				{ echo "missing host tool awk for ${GLES_WORKLOAD} payload" >&2; return 1; }
			install -Dm0755 "${awk_host_tool}" "${SMOKE_MNT}/usr/bin/awk"
		fi
	fi

	if [[ "${GLES_WORKLOAD}" == "glmark" ]]; then
		rm -rf "${SMOKE_MNT}/root/glmark2"
		mkdir -p \
			"${SMOKE_MNT}/root/glmark2/bin" \
			"${SMOKE_MNT}/root/glmark2/libs" \
			"${SMOKE_MNT}/root/glmark2/share/glmark2"
		install -m0755 \
			"${GLMARK_PAYLOAD_SRC}/usr/bin/${glmark_binary}" \
			"${SMOKE_MNT}/root/glmark2/bin/${glmark_binary}"
		for glmark_lib in \
			libjpeg.so.62 \
			libpng16.so.16 \
			libudev.so.1 \
			libgcc_s.so.1; do
			cp -L \
				"${GLMARK_PAYLOAD_SRC}/usr/lib/aarch64-linux-gnu/${glmark_lib}" \
				"${SMOKE_MNT}/root/glmark2/libs/${glmark_lib}"
		done
		cp -a \
			"${GLMARK_PAYLOAD_SRC}/usr/share/glmark2/." \
			"${SMOKE_MNT}/root/glmark2/share/glmark2/"
	fi
	if [[ "${GLES_WORKLOAD}" == "ncnn" ]]; then
		mkdir -p \
			"${SMOKE_MNT}/root/ncnn/bin" \
			"${SMOKE_MNT}/root/ncnn/models" \
			"${SMOKE_MNT}/root/ncnn/libs"
		for ncnn_model in ${GLES_NCNN_MODELS}; do
			[[ "${ncnn_model}" =~ ^[A-Za-z0-9_.-]+$ ]] ||
				{ echo "invalid NCNN model name: ${ncnn_model}" >&2; return 1; }
		done
		install -Dm0755 "${NCNN_PAYLOAD_SRC}/bin/benchncnn" \
			"${SMOKE_MNT}/root/ncnn/bin/benchncnn"
		install -Dm0755 "${NCNN_PAYLOAD_SRC}/bin/ncnn-vk-probe" \
			"${SMOKE_MNT}/root/ncnn/bin/ncnn-vk-probe"
		for ncnn_model in ${GLES_NCNN_MODELS}; do
			install -m0644 "${NCNN_PAYLOAD_SRC}/models/${ncnn_model}.param" \
				"${SMOKE_MNT}/root/ncnn/models/${ncnn_model}.param"
		done
		cp -a "${NCNN_PAYLOAD_SRC}/libs/." "${SMOKE_MNT}/root/ncnn/libs/"

		# The trimmed Firecracker rootfs intentionally keeps only the tools used
		# by the base smoke.  NCNN model runs additionally need timeout(1) and
		# tr(1); both are libc-only coreutils binaries on the RK3588 host.
		for ncnn_guest_tool in timeout tr; do
			if [[ ! -x "${SMOKE_MNT}/usr/bin/${ncnn_guest_tool}" ]]; then
				ncnn_host_tool=$(command -v "${ncnn_guest_tool}" || true)
				[[ -n "${ncnn_host_tool}" && -x "${ncnn_host_tool}" ]] ||
					{ echo "missing host tool ${ncnn_guest_tool} for NCNN payload" >&2; return 1; }
				install -Dm0755 "${ncnn_host_tool}" \
					"${SMOKE_MNT}/usr/bin/${ncnn_guest_tool}"
			fi
		done
	fi
	if [[ "${GLES_WORKLOAD}" == "raw-vk" ]]; then
		mkdir -p \
			"${SMOKE_MNT}/root/vulkan/bin" \
			"${SMOKE_MNT}/root/vulkan/libs"
		install -Dm0755 "${RAW_VK_PROBE_SRC}" \
			"${SMOKE_MNT}/root/vulkan/bin/raw-vk-probe"
		cp -a "${NCNN_PAYLOAD_SRC}/libs/." "${SMOKE_MNT}/root/vulkan/libs/"
	fi

	cat >"${SMOKE_MNT}/root/gpu-smoke.env" <<EOF
GPU_SMOKE_AFTER_RUN=shell
GPU_SMOKE_TEST=${GLES_WORKLOAD}
GPU_SMOKE_GLMARK_FLAVOR=${GLES_GLMARK_FLAVOR}
GPU_SMOKE_GLMARK_SIZE=${GLES_GLMARK_SIZE}
GPU_SMOKE_GLMARK_SKIP_VALIDATE=${GLES_GLMARK_SKIP_VALIDATE}
GPU_SMOKE_GLMARK_FRAME_END=${GLES_GLMARK_FRAME_END}
GPU_SMOKE_GLMARK_PROGRESS_TRACE=${GLES_GLMARK_PROGRESS_TRACE}
GPU_SMOKE_GLMARK_PROGRESS_INTERVAL_S=${GLES_GLMARK_PROGRESS_INTERVAL_S:-5}
	GPU_SMOKE_NCNN_LOOP_COUNT=${GLES_NCNN_LOOP_COUNT}
	GPU_SMOKE_NCNN_THREADS=${GLES_NCNN_THREADS}
	GPU_SMOKE_NCNN_GPU_DEVICE=${GLES_NCNN_GPU_DEVICE}
	GPU_SMOKE_NCNN_COOLING_DOWN=${GLES_NCNN_COOLING_DOWN}
	GPU_SMOKE_NCNN_TIMEOUT_S=${GLES_NCNN_TIMEOUT_S}
	GPU_SMOKE_NCNN_MODELS='${GLES_NCNN_MODELS}'
GPU_SMOKE_RAW_VK_QUEUE_COUNTS=${GLES_RAW_VK_QUEUE_COUNTS}
GPU_SMOKE_RAW_VK_SUBMIT_MODE=${GLES_RAW_VK_SUBMIT_MODE}
GPU_SMOKE_RAW_VK_CASES=${GLES_RAW_VK_CASES}
GPU_SMOKE_DRM_NODE=${GLES_DRM_NODE}
EOF
	printf 'GPU_SMOKE_GLMARK_BENCHMARKS=%q\n' "${GLES_GLMARK_BENCHMARKS}" \
		>>"${SMOKE_MNT}/root/gpu-smoke.env"
	printf 'GPU_SMOKE_GLMARK_EXTRA_ARGS=%q\n' "${GLES_GLMARK_EXTRA_ARGS}" \
		>>"${SMOKE_MNT}/root/gpu-smoke.env"
	sync -f "${SMOKE_MNT}" 2>/dev/null || sync
	umount "${SMOKE_MNT}"
	rmdir "${SMOKE_MNT}"
	SMOKE_MNT=""
	echo "rootfs_payload_inject_done payload=gles-${GLES_WORKLOAD} rootfs=${rootfs_path} ts=$(date -Is)" >&2
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
    "boot_args": "console=ttyS0 root=/dev/vda ro rootfstype=ext4 init=/init panic=-1 print-fatal-signals=1 gpu_smoke_args_tokens=${smoke_arg_tokens} gpu_smoke_quiet_console=0 gpu_smoke_after_run=shell${client_mmap_args}"
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
    "dump_fdt_path": "${REMOTE_ROOT}/artifacts/dtb/client-gles-compute-${RUN_ID}.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-client",
      "role": "client",
      "guest_phys_addr": "${GLES_OBJECT_WINDOW_GPA}",
      "slot": 1,
      "expected_size": ${GLES_OBJECT_WINDOW_BYTES},
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

prepare_gles_proxy() {
	cat >"${GLES_PROXY_CONFIG}" <<EOF
{
  "boot-source": {
    "kernel_image_path": "${REMOTE_BINS}/kernels/shared/proxy/Image",
    "boot_args": "console=ttyS0 root=/dev/vda ro rootfstype=ext4 init=/bin/sh"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "${REMOTE_BINS}/rootfs/rootfs.ext2",
      "is_root_device": false,
      "is_read_only": true
    }
  ],
  "machine-config": {
    "vcpu_count": ${GLES_PROXY_VCPUS},
    "mem_size_mib": ${GLES_PROXY_MEM_MIB},
    "cpu_template": null,
    "gpu_passthrough": true,
    "dump_fdt_path": "${REMOTE_ROOT}/artifacts/dtb/vmshm-1client-proxy-gles-${RUN_ID}.dtb"
  },
  "vmshm": [
    {
      "socket_path": "/run/vmshm/vmshm-object.sock",
      "name": "vmshm-object-proxy",
      "role": "proxy",
      "guest_phys_addr": "${GLES_OBJECT_WINDOW_GPA}",
      "slot": 1,
      "expected_size": ${GLES_OBJECT_WINDOW_BYTES},
      "fdt_node_name": "proxy-vmshm-manager",
      "fdt_compatible": "proxy-vmshm-manager"
    },
    {
      "socket_path": "/run/vmshm/vmshm-comm.sock",
      "name": "vmshm-comm-proxy",
      "role": "proxy",
      "guest_phys_addr": "0x24000000",
      "slot": 2,
      "expected_size": 33554432,
      "fdt_node_name": "proxy_comm_vmshm",
      "fdt_compatible": "proxy_comm_vmshm",
      "notify": {
        "doorbell_addr": "0x2f100000",
        "doorbell_size": "0x1000",
        "irq": 81
      }
    }
  ]
}
EOF
	printf '%s\n' "${GLES_PROXY_CONFIG}"
}

prune_rootfs_base_layout >"${LOG_DIR}/rootfs-base-layout-prune.log" 2>&1
if [[ "${IOCTL_SMOKE}" == "1" ]]; then
	prepare_ioctl_smoke_client >"${LOG_DIR}/ioctl-smoke-rootfs.log" 2>&1
elif [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	{
		prepare_gles_compute_client
		prepare_gles_proxy
		echo "gles_client_mem_mib=${GLES_CLIENT_MEM_MIB}"
		echo "gles_proxy_mem_mib=${GLES_PROXY_MEM_MIB}"
		echo "gles_client_vcpus=${GLES_CLIENT_VCPUS}"
		echo "gles_proxy_vcpus=${GLES_PROXY_VCPUS}"
		echo "gles_object_window_mib=${GLES_OBJECT_WINDOW_MIB}"
		echo "gles_object_window_bytes=${GLES_OBJECT_WINDOW_BYTES}"
		echo "gles_object_window_gpa=${GLES_OBJECT_WINDOW_GPA}"
		echo "broker_config=${GLES_BROKER_CONFIG}"
		echo "gles_host_online_cpus=${GLES_HOST_ONLINE_CPUS:-}"
		echo "gles_broker_cpus=${GLES_BROKER_CPUS:-}"
		echo "gles_proxy_cpus=${GLES_PROXY_CPUS:-}"
		echo "gles_client_cpus=${GLES_CLIENT_CPUS:-}"
	} >"${LOG_DIR}/gles-compute-rootfs.log" 2>&1
fi

cat >"${GLES_BROKER_CONFIG}" <<EOF
[broker]
socket_dir = "/run/vmshm"

[[domains]]
id = "vmshm-object"
socket_path = "/run/vmshm/vmshm-object.sock"
memfd_name = "vmshm-object"
window_size = ${GLES_OBJECT_WINDOW_BYTES}
seal = true

[[domains]]
id = "vmshm-comm"
socket_path = "/run/vmshm/vmshm-comm.sock"
memfd_name = "vmshm-comm"
window_size = 33554432
seal = true
EOF

broker_cmd=(./bin/vmshm-broker --config "${GLES_BROKER_CONFIG}")
if [[ -n "${GLES_BROKER_CPUS}" && "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
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
	NO_COLOR=1 RUST_LOG_STYLE=never nohup "${broker_cmd[@]}" \
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

proxy_cmd=(sh ./scripts/shared/vmshm-1client/vm-proxy-test.sh)
if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	proxy_cmd=(./bin/firecracker --no-api --no-seccomp --config-file "${GLES_PROXY_CONFIG}")
fi
if [[ -n "${GLES_PROXY_CPUS}" && "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	proxy_cmd=(taskset -c "${GLES_PROXY_CPUS}" "${proxy_cmd[@]}")
fi
write_launch_command proxy "${proxy_cmd[@]}"
NO_COLOR=1 RUST_LOG_STYLE=never nohup "${proxy_cmd[@]}" \
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
		client_cmd=(./bin/firecracker --no-api --no-seccomp --config-file "${GLES_CLIENT_CONFIG}")
		if [[ -n "${GLES_CLIENT_CPUS}" ]]; then
			client_cmd=(taskset -c "${GLES_CLIENT_CPUS}" "${client_cmd[@]}")
		fi
		write_launch_command client "${client_cmd[@]}"
		NO_COLOR=1 RUST_LOG_STYLE=never nohup "${client_cmd[@]}" \
			< /dev/null >"${LOG_DIR}/client.log" 2>&1 &
else
	NO_COLOR=1 RUST_LOG_STYLE=never nohup sh ./scripts/shared/vmshm-1client/vm-client-test.sh \
		< /dev/null >"${LOG_DIR}/client.log" 2>&1 &
fi
echo $! >"${LOG_DIR}/client.pid"

if [[ "${IOCTL_SMOKE}" == "1" ]]; then
	wait_for_client_log "${LOG_DIR}/client.log" "PANTHOR_IOCTL_SMOKE=(BASIC_PASS|VM_CREATE_PASS|BO_CREATE_PASS|BO_LIFECYCLE_PASS|BO_MMAP_PASS|VM_BIND_PASS|VM_BIND_ASYNC_SYNC_PASS|VM_STATE_FLUSH_PASS|SYNCOBJ_LIFECYCLE_PASS|SYNCOBJ_WAIT_PASS|SYNCOBJ_TRANSFER_PASS|SYNCOBJ_TIMELINE_WAIT_PASS|SYNCOBJ_SIGNAL_QUERY_PASS|SYNC_FILE_SNAPSHOT_PASS|GROUP_LIFECYCLE_PASS|GROUP_SUBMIT_SYNCPOINT_PASS|TILER_HEAP_LIFECYCLE_PASS)|PANTHOR_IOCTL_INIT=FAIL|Kernel panic|Guest-boot failed" 80 "${LOG_DIR}/client.pid" || true
elif [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
	if [[ "${GLES_WORKLOAD}" == "glmark" ]]; then
		wait_for_client_log "${LOG_DIR}/client.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|GLMARK_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout|software renderer detected" 900 "${LOG_DIR}/client.pid" || true
	elif [[ "${GLES_WORKLOAD}" == "ml" ]]; then
		wait_for_client_log "${LOG_DIR}/client.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|ML_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout|mismatch|software renderer detected" 900 "${LOG_DIR}/client.pid" || true
	elif [[ "${GLES_WORKLOAD}" == "ncnn" ]]; then
		# The NCNN inventory intentionally prints libvulkan paths before the
		# workload starts.  Do not use "vulkan" as an early completion marker.
		wait_for_client_log "${LOG_DIR}/client.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|NCNN_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout|VK_ERROR_DEVICE_LOST" 1800 "${LOG_DIR}/client.pid" || true
	elif [[ "${GLES_WORKLOAD}" == "raw-vk" ]]; then
		# A reduction suite intentionally records intermediate VK_ERROR values;
		# wait for the wrapper's terminal result instead of stopping case 1.
		wait_for_client_log "${LOG_DIR}/client.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|RAW_VK_SUITE_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout" 900 "${LOG_DIR}/client.pid" || true
	else
		# COMPUTE_CHECK is emitted before the measured loop. Treating it as a
		# completion marker can stop the client before PERF_* markers appear.
		wait_for_client_log "${LOG_DIR}/client.log" "GPU_SMOKE_RESULT=(PASS|FAIL)|Kernel panic|Guest-boot failed|Oops|job timeout|mismatch|software renderer detected" 180 "${LOG_DIR}/client.pid" || true
	fi
else
	wait_for_client_log "${LOG_DIR}/client.log" "panthor-client: registered DRM frontend" 60 "${LOG_DIR}/client.pid" || true
fi

record_client_exit_if_done "${LOG_DIR}/client.pid" "${LOG_DIR}/client.firecracker.exit.log"

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
	sync-file-snapshot)
		grep -qa "PANTHOR_IOCTL_SMOKE=SYNC_FILE_SNAPSHOT_PASS" "${LOG_DIR}/client.log"
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
	if [[ "${IOCTL_SMOKE_MODE}" == "sync-file-snapshot" ]]; then
		grep -qa "PANTHOR_SYNC_FILE_SNAPSHOT_SMOKE=PASS exports=128 source_reset=1 source_destroy=1 drm_close=1" "${LOG_DIR}/client.log" || return 1
		grep -qa "PANTHOR_SYNC_FILE_IMPORT_SMOKE=PASS imports=64 target_reset=1 target_destroy=1" "${LOG_DIR}/client.log" || return 1
		grep -qaE "panthor-client: OPEN_SESSION session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
		grep -qaE "panthor-proxy: OPEN_SESSION session=[1-9][0-9]*" "${LOG_DIR}/proxy.log"
		return
	fi
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
	grep -qaE "panthor-proxy: BO_CREATE( seq=[0-9]+)? session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
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
	grep -qaE "panthor-proxy: BO_CREATE( seq=[0-9]+)? session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
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
	grep -qaE "panthor-proxy: BO_CREATE( seq=[0-9]+)? session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor: BO_CREATE vmshm-backed handle=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
}

ioctl_vm_bind_markers_ok() {
	[[ "${IOCTL_SMOKE_MODE}" != "vm-bind" ]] && return 0

	grep -qa "PANTHOR_VM_BIND_SMOKE=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "PANTHOR_VM_BIND_SIZE_REUSE=PASS rounds=4" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_MAP vm=" "${LOG_DIR}/client.log" || return 1
	grep -qa "VM_BIND_UNMAP vm=" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: VM_BIND session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: VM_BIND session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-proxy: VM_BIND session=[1-9][0-9]*.*ret=0" "${LOG_DIR}/proxy.log" || return 1
	grep -qaE "panthor-client: BO_CREATE session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-client: BO_DESTROY session=[1-9][0-9]*" "${LOG_DIR}/client.log" || return 1
	grep -qaE "panthor-proxy: BO_CREATE( seq=[0-9]+)? session=[1-9][0-9]*" "${LOG_DIR}/proxy.log" || return 1
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

gles_glmark_markers_ok() {
	grep -qa "GPU_SMOKE_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "GLMARK_FLAVOR=${GLES_GLMARK_FLAVOR}" "${LOG_DIR}/client.log" || return 1
	if [[ "${GLES_GLMARK_SKIP_VALIDATE}" == "1" ]]; then
		grep -qa "GLMARK_VALIDATE=SKIPPED" "${LOG_DIR}/client.log" || return 1
	else
		grep -qa "GLMARK_VALIDATE=PASS" "${LOG_DIR}/client.log" || return 1
	fi
	grep -qa "GLMARK_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	# The serial guest log can carry CRLF endings.  Keep the required prefix
	# anchored, but do not require '$' after Score/Renderer.
	grep -qaE '^GLMARK_SCORE=[1-9][0-9]*' "${LOG_DIR}/client.log" || return 1
	grep -qaE '^GLMARK_RENDERER=.*(Mali|Panfrost)' "${LOG_DIR}/client.log" || return 1
	grep -qa "GLMARK_CLEAN_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "COMPUTE_CHECK=PASS" "${LOG_DIR}/client.log" || return 1
	return 0
}

gles_ml_markers_ok() {
	local kernel selected_kernel=all gemm_size=512 attention_size=256 i
	local -a smoke_args
	read -r -a smoke_args <<<"${GLES_SMOKE_ARGS:-}"
	for ((i = 0; i < ${#smoke_args[@]}; i++)); do
		case "${smoke_args[i]}" in
		--kernel) selected_kernel="${smoke_args[i + 1]:-}" ;;
		--gemm-size) gemm_size="${smoke_args[i + 1]:-}" ;;
		--attention-size) attention_size="${smoke_args[i + 1]:-}" ;;
		esac
	done
	local kernels=(
		"gemm_${gemm_size}_fp32"
		conv2d_64x64x32_3x3_fp32
		depthwise_conv_128x128x128_3x3_fp32
		block_reduction_32mib_fp32
		row_softmax_16384x256_fp32
		"single_head_attention_${attention_size}x64_fp32"
	)

	grep -qa "GPU_SMOKE_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "ML_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "ML_CLEAN_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	! grep -qaE 'ML_CLEAN_RESULT=FAIL|MESA: error: export failed|DMA_BUF_IOCTL_EXPORT_SYNC_FILE failed' "${LOG_DIR}/client.log" || return 1
	grep -qaE '^GL_RENDERER=.*(Mali|Panfrost)' "${LOG_DIR}/client.log" || return 1
	if [[ "${selected_kernel}" != "all" ]]; then
		case "${selected_kernel}" in
		gemm) kernels=("${kernels[0]}") ;;
		conv) kernels=("${kernels[1]}") ;;
		depthwise) kernels=("${kernels[2]}") ;;
		reduction) kernels=("${kernels[3]}") ;;
		softmax) kernels=("${kernels[4]}") ;;
		attention) kernels=("${kernels[5]}") ;;
		*) return 1 ;;
		esac
	fi
	[[ "$(grep -ac '^ML_CHECK=PASS' "${LOG_DIR}/client.log" 2>/dev/null || true)" -ge "${#kernels[@]}" ]] || return 1
	for kernel in "${kernels[@]}"; do
		grep -qaE "ML_KERNEL=${kernel}[[:space:]]*$" "${LOG_DIR}/client.log" || return 1
	done
	return 0
}

gles_ncnn_markers_ok() {
	local expected_models

	grep -qa "GPU_SMOKE_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "NCNN_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "NCNN_BACKEND_QUALIFICATION=PASS" "${LOG_DIR}/client.log" || return 1
	# The client serial console appends CR to LF.  Do not anchor fields that
	# can be followed by CR at line end.
	if grep -qa '^NCNN_BACKEND=cpu' "${LOG_DIR}/client.log"; then
		:
	else
		grep -qa "NCNN_BACKEND=panvk-direct" "${LOG_DIR}/client.log" || return 1
	fi
	grep -qa "NCNN_FAILED_MODELS=0" "${LOG_DIR}/client.log" || return 1
	! grep -qaE 'MESA: error:|vk[A-Za-z0-9_]+ failed|VK_ERROR_|panthor-client: (BO_CREATE|VM_BIND) failed' "${LOG_DIR}/client.log" || return 1
	expected_models=$(grep -ao '^NCNN_TOTAL_MODELS=[0-9][0-9]*' "${LOG_DIR}/client.log" 2>/dev/null | tail -n1 | cut -d= -f2)
	expected_models=${expected_models:-0}
	[[ "${expected_models}" -gt 0 ]] || return 1
	[[ "$(grep -ac '^NCNN_MODEL_RESULT=PASS' "${LOG_DIR}/client.log" 2>/dev/null || true)" -ge "${expected_models}" ]] || return 1
	return 0
}

gles_raw_vk_markers_ok() {
	grep -qa "GPU_SMOKE_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "RAW_VK_SUITE_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qa "RAW_VK_PROBE_RC=0" "${LOG_DIR}/client.log" || return 1
	grep -qa "RAW_VK_RESULT=PASS" "${LOG_DIR}/client.log" || return 1
	grep -qaE '^RAW_VK_DEVICE_NAME=.*(Mali|Panfrost)' "${LOG_DIR}/client.log" || return 1
	[[ "$(grep -ac '^RAW_VK_CASE_RESULT=PASS' "${LOG_DIR}/client.log" 2>/dev/null || true)" -ge 1 ]] || return 1
	return 0
}

{
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		if [[ "${GLES_WORKLOAD}" == "glmark" ]]; then
			echo "Panthor shared GLES glmark2 smoke result"
		elif [[ "${GLES_WORKLOAD}" == "ml" ]]; then
			echo "Panthor shared GLES ML-kernel smoke result"
		elif [[ "${GLES_WORKLOAD}" == "ncnn" ]]; then
			echo "Panthor shared NCNN real-model graph smoke result"
	elif [[ "${GLES_WORKLOAD}" == "raw-vk" ]]; then
		echo "Panthor shared raw Vulkan queue/fence probe result"
		else
			echo "Panthor shared GLES compute smoke result"
		fi
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
	echo "GLES workload: ${GLES_WORKLOAD}"
	echo "GLES glmark flavor: ${GLES_GLMARK_FLAVOR}"
	echo "GLES glmark size: ${GLES_GLMARK_SIZE}"
	echo "GLES glmark frame end: ${GLES_GLMARK_FRAME_END}"
	echo "GLES glmark progress trace: ${GLES_GLMARK_PROGRESS_TRACE}"
	if [[ "${GLES_WORKLOAD}" == "ncnn" ]]; then
		echo "NCNN loop count: ${GLES_NCNN_LOOP_COUNT}"
		echo "NCNN threads: ${GLES_NCNN_THREADS}"
		echo "NCNN GPU device: ${GLES_NCNN_GPU_DEVICE}"
		echo "NCNN cooling down: ${GLES_NCNN_COOLING_DOWN}"
		echo "NCNN timeout: ${GLES_NCNN_TIMEOUT_S}s"
		echo "NCNN models: ${GLES_NCNN_MODELS}"
	fi
	if [[ "${GLES_WORKLOAD}" == "raw-vk" ]]; then
		echo "Raw Vulkan queue counts: ${GLES_RAW_VK_QUEUE_COUNTS}"
		echo "Raw Vulkan submit mode: ${GLES_RAW_VK_SUBMIT_MODE}"
		echo "Raw Vulkan cases: ${GLES_RAW_VK_CASES}"
	fi
	echo "GLES DRM node: ${GLES_DRM_NODE:-auto}"
	echo "GLES smoke args: ${GLES_SMOKE_ARGS}"
	echo "GLES client memory MiB: ${GLES_CLIENT_MEM_MIB}"
	echo "GLES proxy memory MiB: ${GLES_PROXY_MEM_MIB}"
	echo "GLES client vCPUs: ${GLES_CLIENT_VCPUS}"
	echo "GLES proxy vCPUs: ${GLES_PROXY_VCPUS}"
	echo "GLES object window MiB: ${GLES_OBJECT_WINDOW_MIB}"
	echo "GLES broker config: ${GLES_BROKER_CONFIG}"
	echo "GLES host online CPUs: ${GLES_HOST_ONLINE_CPUS:-auto}"
	echo "GLES broker CPUs: ${GLES_BROKER_CPUS:-auto}"
	echo "GLES proxy CPUs: ${GLES_PROXY_CPUS:-auto}"
	echo "GLES client CPUs: ${GLES_CLIENT_CPUS:-auto}"
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
	grep -aE "panthor: BO_CREATE vmshm-backed|panthor: VM_BIND vmshm payload mapped|panthor-proxy: OPEN_SESSION session=[1-9][0-9]*|panthor-proxy: DEV_QUERY session=[1-9][0-9]*|panthor-proxy: VM_CREATE session=[1-9][0-9]*|panthor-proxy: VM_DESTROY session=[1-9][0-9]*|panthor-proxy: VM_BIND session=[1-9][0-9]*|panthor-proxy: VM_GET_STATE session=[1-9][0-9]*|panthor-proxy: BO_CREATE( seq=[0-9]+)? session=[1-9][0-9]*|panthor-proxy: BO_CREATE vmshm-backed session=[1-9][0-9]*|panthor-proxy: BO_DESTROY session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_CREATE session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_DESTROY session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_WAIT session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_TRANSFER session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_TIMELINE_WAIT session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_RESET session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_SIGNAL session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_TIMELINE_SIGNAL session=[1-9][0-9]*|panthor-proxy: SYNCOBJ_QUERY session=[1-9][0-9]*|panthor-proxy: GROUP_CREATE session=[1-9][0-9]*|panthor-proxy: GROUP_GET_STATE session=[1-9][0-9]*|panthor-proxy: GROUP_SUBMIT session=[1-9][0-9]*|panthor-proxy: GROUP_DESTROY session=[1-9][0-9]*|panthor-proxy: TILER_HEAP_CREATE session=[1-9][0-9]*|panthor-proxy: TILER_HEAP_DESTROY session=[1-9][0-9]*|panthor-proxy: SESSION_RELEASE session=[1-9][0-9]*|panthor-proxy: CLOSE_SESSION session=[1-9][0-9]*" \
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
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" && -f "${LOG_DIR}/affinity.log" ]]; then
		echo "== GLES affinity and memory preflight =="
		cat "${LOG_DIR}/affinity.log"
		cat "${LOG_DIR}/preflight.txt" 2>/dev/null || true
		echo
	fi
	echo "== Client Panthor DRM =="
	grep -aE "registered vmshm notify|client_comm_vmshm .*irq notify enabled|client_comm_vmshm: perf|PANTHOR_CLIENT_BO_MMAP_CACHED|panthor-client: BO mmap cached=|panthor-client: OPEN_SESSION|panthor-client: DEV_QUERY|panthor-client: VM_CREATE|panthor-client: VM_DESTROY|panthor-client: VM_BIND|panthor-client: VM_GET_STATE|panthor-client: BO_CREATE|panthor-client: BO_DESTROY|panthor-client: BO_MMAP_OFFSET|panthor-client: MMAP|panthor-client: MMAP_FLUSH_ID|panthor-client: SYNCOBJ_CREATE|panthor-client: SYNCOBJ_DESTROY|panthor-client: SYNCOBJ_WAIT|panthor-client: SYNCOBJ_TRANSFER|panthor-client: SYNCOBJ_TIMELINE_WAIT|panthor-client: SYNCOBJ_RESET|panthor-client: SYNCOBJ_SIGNAL|panthor-client: SYNCOBJ_TIMELINE_SIGNAL|panthor-client: SYNCOBJ_QUERY|panthor-client: GROUP_CREATE|panthor-client: GROUP_GET_STATE|panthor-client: GROUP_SUBMIT|panthor-client: GROUP_DESTROY|panthor-client: TILER_HEAP_CREATE|panthor-client: TILER_HEAP_DESTROY|panthor-client: CLOSE_SESSION|panthor-client: registered DRM frontend|PANTHOR_IOCTL_|PANTHOR_BASIC_SMOKE|PANTHOR_VM_CREATE_SMOKE|PANTHOR_BO_CREATE_SMOKE|PANTHOR_BO_LIFECYCLE_SMOKE|PANTHOR_BO_MMAP_SMOKE|PANTHOR_VM_BIND_SMOKE|PANTHOR_VM_BIND_ASYNC_SYNC_SMOKE|PANTHOR_VM_STATE_FLUSH_SMOKE|PANTHOR_SYNCOBJ_LIFECYCLE_SMOKE|PANTHOR_SYNCOBJ_WAIT_SMOKE|PANTHOR_SYNCOBJ_TRANSFER_SMOKE|PANTHOR_SYNCOBJ_TIMELINE_WAIT_SMOKE|PANTHOR_SYNCOBJ_SIGNAL_QUERY_SMOKE|PANTHOR_GROUP_LIFECYCLE_SMOKE|PANTHOR_GROUP_SUBMIT_SYNCPOINT_SMOKE|PANTHOR_TILER_HEAP_LIFECYCLE_SMOKE|OPEN path=|VERSION name=|GET_CAP|DEV_QUERY_SIZE|GPU_INFO|CSIF_INFO|VM_CREATE|VM_DESTROY|VM_BIND|VM_GET_STATE|GROUP_|TILER_HEAP_|MMAP_FLUSH_ID|MUNMAP_FLUSH_ID|BO_CREATE|BO_MMAP|BO_MUNMAP|PRIME_|SYNCOBJ_|GEM_CLOSE|ERROR|WARN|Kernel panic|Guest-boot failed" \
			"${LOG_DIR}/client.log" | tail -n 200 || true
	if [[ "${GLES_COMPUTE_SMOKE}" == "1" ]]; then
		echo
		echo "== GLES compute smoke =="
		if [[ "${GLES_WORKLOAD}" == "ml" ]]; then
			grep -aE "PANTHOR_CLIENT_BO_MMAP_CACHED|GPU_SMOKE_RESULT|ML_KERNEL|ML_CHECK|ML_ITER_US|ML_PHASE_US|ML_WORK_OPS|ML_BYTES_MOVED|ML_OPS_PER_SEC|ML_RESULT|GL_RENDERER|GL_VENDOR|GL_VERSION|GBM_BACKEND|DRM_NODE|gles-ml-smoke rc|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|ERROR|WARN" \
				"${LOG_DIR}/client.log" || true
		elif [[ "${GLES_WORKLOAD}" == "ncnn" ]]; then
			grep -aE "PANTHOR_CLIENT_BO_MMAP_CACHED|GPU_SMOKE_RESULT|NCNN_|NCNN_VK_|benchncnn|vk-probe|MESA: error|VK_ERROR|vulkan|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|ERROR|WARN" \
				"${LOG_DIR}/client.log" || true
		elif [[ "${GLES_WORKLOAD}" == "raw-vk" ]]; then
			grep -aE "PANTHOR_CLIENT_BO_MMAP_CACHED|GPU_SMOKE_RESULT|RAW_VK_|raw-vk-probe|MESA: error|VK_ERROR|vulkan|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|ERROR|WARN" \
				"${LOG_DIR}/client.log" || true
		else
			grep -aE "PANTHOR_CLIENT_BO_MMAP_CACHED|GPU_SMOKE_RESULT|COMPUTE_CHECK|GL_RENDERER|GL_VENDOR|GL_VERSION|GLMARK_|glmark2 Score|GBM_BACKEND|DRM_NODE|STAGE=|PERF_|gles-compute-smoke rc|glmark2-es2-(gbm|drm|null)|software renderer detected|job timeout|gpu fault|Oops|Unable to handle|Kernel panic|ERROR|WARN" \
				"${LOG_DIR}/client.log" || true
		fi
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
	elif [[ "${GLES_COMPUTE_SMOKE}" == "1" && "${GLES_WORKLOAD}" == "glmark" ]] &&
	     gles_glmark_markers_ok &&
	     ! grep -qaE "software renderer detected|llvmpipe|softpipe|Software Rasterizer|COMPUTE_CHECK=FAIL|GPU_SMOKE_RESULT=FAIL|GLMARK_RESULT=FAIL|Kernel panic|Oops|job timeout|Error: Failed" "${LOG_DIR}/client.log"; then
			echo "RESULT: PASS"
	elif [[ "${GLES_COMPUTE_SMOKE}" == "1" && "${GLES_WORKLOAD}" == "ml" ]] &&
	     gles_ml_markers_ok &&
	     ! grep -qaE "software renderer detected|llvmpipe|softpipe|Software Rasterizer|ML_CHECK=FAIL|ML_RESULT=FAIL|GPU_SMOKE_RESULT=FAIL|Kernel panic|Oops|job timeout|mismatch" "${LOG_DIR}/client.log"; then
			echo "RESULT: PASS"
	elif [[ "${GLES_COMPUTE_SMOKE}" == "1" && "${GLES_WORKLOAD}" == "ncnn" ]] &&
	     gles_ncnn_markers_ok &&
	     ! grep -qaE "NCNN_RESULT=FAIL|NCNN_MODEL_RESULT=FAIL|NCNN_BACKEND_QUALIFICATION=FAIL|GPU_SMOKE_RESULT=FAIL|Kernel panic|Oops|job timeout|VK_ERROR|vulkan device.*failed|Unable to handle" "${LOG_DIR}/client.log"; then
			echo "RESULT: PASS"
	elif [[ "${GLES_COMPUTE_SMOKE}" == "1" && "${GLES_WORKLOAD}" == "raw-vk" ]] &&
	     gles_raw_vk_markers_ok &&
	     ! grep -qaE "RAW_VK_RESULT=FAIL|GPU_SMOKE_RESULT=FAIL|Kernel panic|Oops|job timeout|VK_ERROR|Unable to handle" "${LOG_DIR}/client.log"; then
			echo "RESULT: PASS"
	elif [[ "${GLES_COMPUTE_SMOKE}" == "1" && "${GLES_WORKLOAD}" == "compute" ]] &&
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
	if remote_has_cmd rsync; then
		rsync_remote -av --info=stats2,name1 \
			"${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}/" \
			"${SFTP_LOG_ROOT}/shared/vmshm-1client/${RUN_ID}/"
	else
		tar_fetch_logs
	fi
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
