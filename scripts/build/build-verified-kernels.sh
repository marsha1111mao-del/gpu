#!/usr/bin/env bash
# Build from the configuration snapshots used for the published baseline.
# A clean source tree is required for Linux out-of-tree builds.
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
BUILD_ROOT="${BUILD_ROOT:-${ROOT_DIR}/build/verified-kernels}"
JOBS="${JOBS:-8}"
ROLE="${1:-all}"
case "${ROLE}" in
all) roles=(host client proxy passthrough) ;;
host|client|proxy|passthrough) roles=("${ROLE}") ;;
*) echo "Usage: $0 [all|host|client|proxy|passthrough]" >&2; exit 2 ;;
esac
for role in "${roles[@]}"; do
	if [[ "${role}" == host ]]; then
		source_dir="${ROOT_DIR}/Linux-Host-GPU"
		destination="${ROOT_DIR}/GPU-SFTP/linux-host-kernel/Image"
	else
		source_dir="${ROOT_DIR}/Linux-Guest-GPU"
		if [[ "${role}" == passthrough ]]; then
			destination="${ROOT_DIR}/GPU-SFTP/firecracker-bins/kernels/passthrough/Image"
		else
			destination="${ROOT_DIR}/GPU-SFTP/firecracker-bins/kernels/shared/${role}/Image"
		fi
	fi
	if [[ -f "${source_dir}/.config" || -d "${source_dir}/include/config" ]]; then
		echo "${source_dir} has in-tree build outputs; use a clean checkout for this build." >&2
		exit 1
	fi
	out="${BUILD_ROOT}/${role}"
	mkdir -p "${out}" "$(dirname "${destination}")"
	cp "${ROOT_DIR}/configs/verified-20261015/${role}.config" "${out}/.config"
	make -C "${source_dir}" O="${out}" ARCH=arm64 \
		CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" olddefconfig
	make -C "${source_dir}" O="${out}" ARCH=arm64 \
		CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" -j"${JOBS}" Image
	install -m0644 "${out}/arch/arm64/boot/Image" "${destination}"
	echo "Installed ${role}: ${destination}"
done
