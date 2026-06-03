#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BINS_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)
SFTP_DIR=$(CDPATH= cd -- "${BINS_DIR}/.." && pwd)
ROOTFS_IMAGE="${BINS_DIR}/rootfs/rootfs.ext2"
MNT_DIR="${BINS_DIR}/rootfs/mounts/mnt_rootfs"
SRC_DIR="${SFTP_DIR}/tests/vmshm-test"
VM_BIN="${BINS_DIR}/bin/vmshm_demo"
SUDO=
if [ "$(id -u)" -ne 0 ]; then
	SUDO=sudo
fi

cleanup() {
	if mountpoint -q "${MNT_DIR}" 2>/dev/null; then
		${SUDO} umount "${MNT_DIR}"
	fi
}
trap cleanup EXIT INT TERM

if [ ! -f "${ROOTFS_IMAGE}" ]; then
	echo "missing rootfs image: ${ROOTFS_IMAGE}" >&2
	exit 1
fi

aarch64-linux-gnu-gcc -static -o "${VM_BIN}" "${SRC_DIR}/vmshm-demo.c"
${SUDO} mkdir -p "${MNT_DIR}"
${SUDO} mount -o loop "${ROOTFS_IMAGE}" "${MNT_DIR}"
${SUDO} install -Dm0755 "${VM_BIN}" "${MNT_DIR}/root/vmshm_demo"
sync
${SUDO} umount "${MNT_DIR}"
trap - EXIT INT TERM
