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
realm) roles=(client proxy) ;;
host|client|proxy|passthrough) roles=("${ROLE}") ;;
*) echo "Usage: $0 [all|host|client|proxy|passthrough|realm]" >&2; exit 2 ;;
esac
for role in "${roles[@]}"; do
	extra_make=()
	if [[ "${role}" == host ]]; then
		source_dir="${ROOT_DIR}/Linux-Host-GPU"
		destination="${ROOT_DIR}/GPU-SFTP/linux-host-kernel/Image"
		extra_make+=(LOCALVERSION=-opencca-pmthor)
	else
		source_dir="${ROOT_DIR}/Linux-Guest-GPU"
		# The published config embeds this fixed repository firmware. Do not
		# depend on a controller-specific /usr/lib/firmware installation.
		firmware_source="${ROOT_DIR}/GPU-SFTP/panthor_fw/mali_csffw.bin"
		if [[ ! -r "${firmware_source}" ]]; then
			echo "Missing ${firmware_source}; restore the pinned runtime payload first." >&2
			exit 1
		fi
		mkdir -p "${BUILD_ROOT}/firmware"
		firmware_dir=$(cd "${BUILD_ROOT}/firmware" && pwd)
		install -Dm0644 "${firmware_source}" \
			"${firmware_dir}/arm/mali/arch10.8/mali_csffw.bin"
		extra_make+=("CONFIG_EXTRA_FIRMWARE_DIR=${firmware_dir}")
		if [[ "${role}" == client ]]; then
			destination="${ROOT_DIR}/GPU-SFTP/firecracker-bins/kernels/realm-xshm/Image"
		elif [[ "${role}" == proxy ]]; then
			destination="${ROOT_DIR}/GPU-SFTP/firecracker-bins/kernels/realm-xshm/proxy/Image"
		elif [[ "${role}" == passthrough ]]; then
			destination="${ROOT_DIR}/GPU-SFTP/firecracker-bins/kernels/passthrough/Image"

		fi
	fi
	if [[ -f "${source_dir}/.config" || -d "${source_dir}/include/config" ]]; then
		echo "${source_dir} has in-tree build outputs; use a clean checkout for this build." >&2
		exit 1
	fi
	out="${BUILD_ROOT}/${role}"
	mkdir -p "${out}" "$(dirname "${destination}")"
	cp "${ROOT_DIR}/configs/verified-20261015/${role}.config" "${out}/.config"
	if [[ "${role}" == client || "${role}" == proxy ]]; then
		"${source_dir}/scripts/kconfig/merge_config.sh" -m -O "${out}" \
			"${out}/.config" "${ROOT_DIR}/configs/performance/realm-${role}.config"
	fi
	make -C "${source_dir}" O="${out}" ARCH=arm64 \
		CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" "${extra_make[@]}" olddefconfig
	make -C "${source_dir}" O="${out}" ARCH=arm64 \
		CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" "${extra_make[@]}" -j"${JOBS}" Image
	install -m0644 "${out}/arch/arm64/boot/Image" "${destination}"
	echo "Installed ${role}: ${destination}"
done
