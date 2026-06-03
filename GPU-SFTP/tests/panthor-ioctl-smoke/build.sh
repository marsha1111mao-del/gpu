#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${ROOT}/../../.." && pwd)
OUT="${ROOT}/panthor_ioctl_smoke"
CC=${CC:-aarch64-linux-gnu-gcc}
DRM_UAPI=${DRM_UAPI:-/usr/include/drm}
INSTALL_PATH=${INSTALL_PATH:-"${REPO_ROOT}/GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke"}

if [[ -z "${PANTHOR_UAPI:-}" ]]; then
	if [[ -f "${REPO_ROOT}/Linux-Guest-GPU/include/uapi/drm/panthor_drm.h" ]]; then
		PANTHOR_UAPI="${REPO_ROOT}/Linux-Guest-GPU/include/uapi/drm"
	else
		PANTHOR_UAPI="${DRM_UAPI}"
	fi
fi

"${CC}" \
	-O2 -Wall -Wextra -static \
	-I"${DRM_UAPI}" \
	-I"${PANTHOR_UAPI}" \
	-o "${OUT}" \
	"${ROOT}/panthor_ioctl_smoke.c"

install -v -m 0755 "${OUT}" \
	"${INSTALL_PATH}"
