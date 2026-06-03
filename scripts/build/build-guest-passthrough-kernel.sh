#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
#
# Build the arm64 guest kernel used by the single-VM GPU passthrough path.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
LINUX_DIR="${LINUX_DIR:-"${ROOT_DIR}/Linux-Guest-GPU"}"
ARCH="${ARCH:-arm64}"
CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
BASE_DEFCONFIG="${BASE_DEFCONFIG:-defconfig}"
BASE_FRAGMENT="${BASE_FRAGMENT:-rk3588_fragment.config}"
BUILD_DIR="${BUILD_DIR:-"${LINUX_DIR}/out/passthrough-arm64"}"
TARGETS="${TARGETS:-Image}"
JOBS="${JOBS:-$(nproc)}"
FIRECRACKER_BINS="${FIRECRACKER_BINS:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins"}"
PASSTHROUGH_IMAGE="${PASSTHROUGH_IMAGE:-"${FIRECRACKER_BINS}/kernels/passthrough/Image"}"

make_args=(
	-C "${LINUX_DIR}"
	O="${BUILD_DIR}"
	ARCH="${ARCH}"
	CROSS_COMPILE="${CROSS_COMPILE}"
)

mkdir -p "${BUILD_DIR}"

make "${make_args[@]}" "${BASE_DEFCONFIG}"
if [[ -f "${LINUX_DIR}/${BASE_FRAGMENT}" ]]; then
	"${LINUX_DIR}/scripts/kconfig/merge_config.sh" \
		-m -O "${BUILD_DIR}" "${BUILD_DIR}/.config" \
		"${LINUX_DIR}/${BASE_FRAGMENT}"
	make "${make_args[@]}" olddefconfig
fi

make "${make_args[@]}" -j"${JOBS}" ${TARGETS}

if [[ " ${TARGETS} " == *" Image "* || " ${TARGETS} " == *" all "* ]]; then
	image="${BUILD_DIR}/arch/${ARCH}/boot/Image"
	if [[ ! -f "${image}" ]]; then
		echo "missing passthrough Image: ${image}" >&2
		exit 1
	fi

	mkdir -p "$(dirname "${PASSTHROUGH_IMAGE}")"
	cp -f "${image}" "${PASSTHROUGH_IMAGE}"
	echo "passthrough Image installed: ${PASSTHROUGH_IMAGE}"
	strings "${PASSTHROUGH_IMAGE}" 2>/dev/null | grep -a -m 2 'Linux version' || true
else
	echo "passthrough build: ${BUILD_DIR}"
fi
