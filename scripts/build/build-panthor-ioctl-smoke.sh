#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_DIR="${SRC_DIR:-"${ROOT_DIR}/GPU-SFTP/tests/panthor-ioctl-smoke"}"
OUT="${OUT:-"${SRC_DIR}/panthor_ioctl_smoke"}"
CC="${CC:-aarch64-linux-gnu-gcc}"
# Match ioctl structure sizes to the target kernel. New controller headers
# extend drm_syncobj_handle with a timeline point, changing HANDLE_TO_FD's
# ioctl number and bypassing the frontend's binary-syncobj interception.
if [[ -z "${DRM_UAPI:-}" ]]; then
	uapi_root="${ROOT_DIR}/build/panthor-ioctl-uapi"
	make -s -C "${ROOT_DIR}/Linux-Guest-GPU" \
		O="${uapi_root}/kbuild" ARCH=arm64 \
		INSTALL_HDR_PATH="${uapi_root}/export" headers_install
	DRM_UAPI="${uapi_root}/export/include/drm"
fi
INSTALL_PATH="${INSTALL_PATH:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke"}"

if [[ -z "${PANTHOR_UAPI:-}" ]]; then
	PANTHOR_UAPI="${DRM_UAPI}"
fi

"${CC}" \
	-O2 -Wall -Wextra -static \
	-I"${DRM_UAPI}" \
	-I"${PANTHOR_UAPI}" \
	-o "${OUT}" \
	"${SRC_DIR}/panthor_ioctl_smoke.c"

install -v -m 0755 "${OUT}" "${INSTALL_PATH}"
