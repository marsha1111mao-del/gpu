#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_DIR="${SRC_DIR:-"${ROOT_DIR}/GPU-SFTP/tests/realm-host-access-probe"}"
HOST_KERNEL_DIR="${HOST_KERNEL_DIR:-"${ROOT_DIR}/Linux-Host-GPU"}"
ARCH="${ARCH:-arm64}"
CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
JOBS="${JOBS:-16}"
INSTALL_PATH="${INSTALL_PATH:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins/bin/realm_host_access_probe.ko"}"

log() {
	printf '\n==> %s\n' "$*"
}

[[ -f "${SRC_DIR}/realm_host_access_probe.c" ]] || {
	echo "missing probe source: ${SRC_DIR}/realm_host_access_probe.c" >&2
	exit 1
}
[[ -d "${HOST_KERNEL_DIR}" ]] || {
	echo "missing host kernel dir: ${HOST_KERNEL_DIR}" >&2
	exit 1
}

log "Building realm_host_access_probe.ko against Linux-Host-GPU"
make -C "${HOST_KERNEL_DIR}" \
	ARCH="${ARCH}" \
	CROSS_COMPILE="${CROSS_COMPILE}" \
	M="${SRC_DIR}" \
	KBUILD_MODPOST_WARN=1 \
	-j"${JOBS}" \
	modules

log "Installing probe module to ${INSTALL_PATH}"
install -D -m 0644 "${SRC_DIR}/realm_host_access_probe.ko" "${INSTALL_PATH}"

log "Realm Host access probe ready"
printf 'Module: %s\n' "${INSTALL_PATH}"
