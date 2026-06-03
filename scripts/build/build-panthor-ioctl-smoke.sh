#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_DIR="${SRC_DIR:-"${ROOT_DIR}/GPU-SFTP/tests/panthor-ioctl-smoke"}"
OUT="${OUT:-"${SRC_DIR}/panthor_ioctl_smoke"}"
CC="${CC:-aarch64-linux-gnu-gcc}"
DRM_UAPI="${DRM_UAPI:-/usr/include/drm}"
INSTALL_PATH="${INSTALL_PATH:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke"}"

if [[ -z "${PANTHOR_UAPI:-}" ]]; then
	if [[ -f "${ROOT_DIR}/Linux-Guest-GPU/include/uapi/drm/panthor_drm.h" ]]; then
		PANTHOR_UAPI="${ROOT_DIR}/Linux-Guest-GPU/include/uapi/drm"
	else
		PANTHOR_UAPI="${DRM_UAPI}"
	fi
fi

"${CC}" \
	-O2 -Wall -Wextra -static \
	-I"${DRM_UAPI}" \
	-I"${PANTHOR_UAPI}" \
	-o "${OUT}" \
	"${SRC_DIR}/panthor_ioctl_smoke.c"

install -v -m 0755 "${OUT}" "${INSTALL_PATH}"
