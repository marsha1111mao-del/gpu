#!/usr/bin/env bash
# Shared helpers for keeping /root/GPU-SFTP in the semantic artifact layout.

migrate_remote_gpu_sftp_layout() {
	local remote_root_q remote_bins_q

	remote_root_q=$(quote "${REMOTE_ROOT}")
	remote_bins_q=$(quote "${REMOTE_BINS}")

	log "Migrating remote GPU-SFTP layout"
	ssh_remote "REMOTE_ROOT=${remote_root_q} REMOTE_BINS=${remote_bins_q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

move_file() {
	local src="$1"
	local dst="$2"

	[[ -e "${src}" ]] || return 0
	mkdir -p "$(dirname -- "${dst}")"
	if [[ ! -e "${dst}" ]]; then
		mv -f -- "${src}" "${dst}"
	else
		rm -f -- "${src}"
	fi
}

merge_dir() {
	local src="$1"
	local dst="$2"

	[[ -d "${src}" ]] || return 0
	mkdir -p "${dst}"
	cp -a -n -- "${src}/." "${dst}/" 2>/dev/null || true
	rm -rf -- "${src}"
}

mkdir -p \
	"${REMOTE_ROOT}/artifacts/dtb" \
	"${REMOTE_ROOT}/artifacts/trace" \
	"${REMOTE_ROOT}/tests" \
	"${REMOTE_BINS}/bin" \
	"${REMOTE_BINS}/configs/shared/vmshm-1client" \
	"${REMOTE_BINS}/configs/shared/vmshm-2client" \
	"${REMOTE_BINS}/configs/passthrough" \
	"${REMOTE_BINS}/configs/passthrough/trace" \
	"${REMOTE_BINS}/kernels/shared/client" \
	"${REMOTE_BINS}/kernels/shared/proxy" \
	"${REMOTE_BINS}/kernels/passthrough" \
	"${REMOTE_BINS}/kernels/passthrough/backups" \
	"${REMOTE_BINS}/rootfs" \
	"${REMOTE_BINS}/rootfs/mounts" \
	"${REMOTE_BINS}/rootfs/work" \
	"${REMOTE_BINS}/scripts/shared/vmshm-1client" \
	"${REMOTE_BINS}/scripts/shared/vmshm-2client" \
	"${REMOTE_BINS}/scripts/passthrough" \
	"${REMOTE_BINS}/scripts/tools"

move_file "${REMOTE_BINS}/firecracker" "${REMOTE_BINS}/bin/firecracker"
move_file "${REMOTE_BINS}/vmshm-broker" "${REMOTE_BINS}/bin/vmshm-broker"
move_file "${REMOTE_BINS}/vmshm-client-test" "${REMOTE_BINS}/bin/vmshm-client-test"
move_file "${REMOTE_BINS}/panthor_ioctl_smoke" "${REMOTE_BINS}/bin/panthor_ioctl_smoke"
move_file "${REMOTE_BINS}/gles-compute-smoke" "${REMOTE_BINS}/bin/gles-compute-smoke"
move_file "${REMOTE_BINS}/vmshm_demo" "${REMOTE_BINS}/bin/vmshm_demo"

move_file "${REMOTE_BINS}/Image" "${REMOTE_BINS}/kernels/passthrough/Image"
move_file "${REMOTE_BINS}/kernel-client/Image" "${REMOTE_BINS}/kernels/shared/client/Image"
move_file "${REMOTE_BINS}/kernel-proxy/Image" "${REMOTE_BINS}/kernels/shared/proxy/Image"
for image_backup in "${REMOTE_BINS}"/Image.bak*; do
	[[ -e "${image_backup}" ]] || continue
	move_file "${image_backup}" "${REMOTE_BINS}/kernels/passthrough/backups/$(basename -- "${image_backup}")"
done

merge_dir "${REMOTE_BINS}/config" "${REMOTE_BINS}/configs/shared/vmshm-1client"
merge_dir "${REMOTE_BINS}/config-2client" "${REMOTE_BINS}/configs/shared/vmshm-2client"
move_file "${REMOTE_BINS}/gpu-panfrost-vm-config.json" "${REMOTE_BINS}/configs/passthrough/gpu-panfrost-vm-config.json"
move_file "${REMOTE_BINS}/gpu-passthrough-vm-config.json" "${REMOTE_BINS}/configs/passthrough/gpu-passthrough-vm-config.json"
move_file "${REMOTE_BINS}/gpu-panfrost-trace-vm-config.json" "${REMOTE_BINS}/configs/passthrough/trace/gpu-panfrost-trace-vm-config.json"
for config_backup in "${REMOTE_BINS}"/*.json.bak*; do
	[[ -e "${config_backup}" ]] || continue
	move_file "${config_backup}" "${REMOTE_BINS}/configs/passthrough/backups/$(basename -- "${config_backup}")"
done

for rootfs in "${REMOTE_BINS}"/rootfs*.ext*; do
	[[ -e "${rootfs}" ]] || continue
	move_file "${rootfs}" "${REMOTE_BINS}/rootfs/$(basename -- "${rootfs}")"
done
merge_dir "${REMOTE_BINS}/rootfs-panfrost-build" "${REMOTE_BINS}/rootfs/work/rootfs-panfrost-build"
merge_dir "${REMOTE_BINS}/rootfs-panfrost-hostcopy-build" "${REMOTE_BINS}/rootfs/work/rootfs-panfrost-hostcopy-build"
merge_dir "${REMOTE_BINS}/mnt_rootfs" "${REMOTE_BINS}/rootfs/mounts/mnt_rootfs"
merge_dir "${REMOTE_BINS}/mnt_rootfs_panfrost" "${REMOTE_BINS}/rootfs/mounts/mnt_rootfs_panfrost"

merge_dir "${REMOTE_ROOT}/gpu-compute-smoke" "${REMOTE_ROOT}/tests/gpu-compute-smoke"
merge_dir "${REMOTE_ROOT}/panthor-ioctl-smoke" "${REMOTE_ROOT}/tests/panthor-ioctl-smoke"
merge_dir "${REMOTE_ROOT}/vmshm-test" "${REMOTE_ROOT}/tests/vmshm-test"

move_file "${REMOTE_ROOT}/firecracker.dtb" "${REMOTE_ROOT}/artifacts/dtb/firecracker.dtb"
move_file "${REMOTE_ROOT}/firecracker.dts" "${REMOTE_ROOT}/artifacts/dtb/firecracker.dts"
move_file "${REMOTE_ROOT}/trans_dtb.sh" "${REMOTE_ROOT}/artifacts/dtb/trans_dtb.sh"
move_file "${REMOTE_BINS}/.last-panthor-trace-run-id" "${REMOTE_ROOT}/artifacts/trace/.last-panthor-trace-run-id"

rm -f \
	"${REMOTE_BINS}/broker-run.sh" \
	"${REMOTE_BINS}/broker-run-2client.sh" \
	"${REMOTE_BINS}/vm-proxy-test.sh" \
	"${REMOTE_BINS}/vm-client-test.sh" \
	"${REMOTE_BINS}/vm-proxy-2client-test.sh" \
	"${REMOTE_BINS}/vm-client0-2client-test.sh" \
	"${REMOTE_BINS}/vm-client1-2client-test.sh" \
	"${REMOTE_BINS}/install-vmshm-irq-configs.sh" \
	"${REMOTE_BINS}/install-vmshm-irq-configs-2client.sh" \
	"${REMOTE_BINS}/run-gpu-panfrost-vm.sh" \
	"${REMOTE_BINS}/run-gpu-passthrough-vm.sh" \
	"${REMOTE_BINS}/copy-vmshm-test.sh" \
	"${REMOTE_BINS}/json-test-busybox3.sh" \
	"${REMOTE_BINS}/test-cvm-config-busybox3.json"

rmdir \
	"${REMOTE_BINS}/kernel-client" \
	"${REMOTE_BINS}/kernel-proxy" \
	2>/dev/null || true

rm -rf -- "${REMOTE_ROOT}/firecracker-image-bins"
REMOTE_SCRIPT
}
