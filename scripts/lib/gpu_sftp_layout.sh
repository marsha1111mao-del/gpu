#!/usr/bin/env bash
# Shared helpers for keeping /root/GPU-SFTP in the semantic artifact layout.

stream_file_to_remote_atomic() {
	local rel_path="$1"
	local src="${SFTP_ROOT}/${rel_path}"
	local dst="${REMOTE_ROOT}/${rel_path}"
	local dst_dir tmp digest

	[[ -f "${src}" ]] || die "missing local file for rootfs sync: ${src}"
	dst_dir=$(dirname -- "${dst}")
	tmp="${dst}.tmp.$$"
	digest=$(sha256sum "${src}" | cut -d' ' -f1)
	log "Syncing ${rel_path} via verified atomic ssh stream"
	ssh_remote "mkdir -p $(quote "${dst_dir}")"
	if ! cat "${src}" |
		ssh_remote "cat > $(quote "${tmp}") && printf '%s  %s\\n' $(quote "${digest}") $(quote "${tmp}") | sha256sum -c - && chmod 0644 $(quote "${tmp}") && mv -f $(quote "${tmp}") $(quote "${dst}")"; then
		ssh_remote "rm -f -- $(quote "${tmp}")" || true
		die "rootfs sync failed: ${rel_path}"
	fi
}

sync_rootfs_to_remote_atomic() {
	stream_file_to_remote_atomic "firecracker-bins/rootfs/rootfs.ext2"
	stream_file_to_remote_atomic "firecracker-bins/rootfs/rootfs-panfrost.ext4"
}

# Runtime layout is fixed; prepare directories without moving or deleting files.
prepare_remote_gpu_sftp_layout() {
	ssh_remote "mkdir -p $(quote "${REMOTE_BINS}/bin") $(quote "${REMOTE_BINS}/rootfs") $(quote "${REMOTE_BINS}/configs/passthrough") $(quote "${REMOTE_BINS}/kernels/passthrough")"
}
