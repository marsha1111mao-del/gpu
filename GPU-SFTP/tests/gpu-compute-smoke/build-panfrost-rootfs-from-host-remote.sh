#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR=${TARGET_DIR:-/root/GPU-SFTP/firecracker-bins/rootfs}
SRC_DIR=${SRC_DIR:-/root/GPU-SFTP/tests/gpu-compute-smoke}
FW_SRC=${FW_SRC:-/root/GPU-SFTP/panthor_fw/mali_csffw.bin}
IOCTL_SMOKE_TEST=${IOCTL_SMOKE_TEST:-${RAW_IOCTL_TEST:-/root/GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke}}
IMAGE_NAME=${IMAGE_NAME:-rootfs-panfrost.ext4}
IMAGE_SIZE=${IMAGE_SIZE:-1536M}

IMAGE_PATH="${TARGET_DIR}/${IMAGE_NAME}"
WORK_DIR="${TARGET_DIR}/work/rootfs-panfrost-hostcopy-build"
MNT="${WORK_DIR}/mnt"
NEW_IMAGE="${WORK_DIR}/${IMAGE_NAME}.new"
SMOKE_BIN="${WORK_DIR}/gles-compute-smoke"

log() {
	printf '\n==> %s\n' "$*"
}

die() {
	echo "error: $*" >&2
	exit 1
}

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

cleanup() {
	set +e
	if mountpoint -q "${MNT}"; then
		umount "${MNT}"
	fi
}
trap cleanup EXIT

copy_path() {
	local src="$1"
	local dst

	[[ -e "${src}" || -L "${src}" ]] || return 0
	dst="${MNT}${src}"
	mkdir -p "$(dirname "${dst}")"
	cp -a --no-dereference "${src}" "${dst}"
}

copy_path_with_target() {
	local src="$1"
	local resolved

	copy_path "${src}"
	if [[ -L "${src}" ]]; then
		resolved=$(readlink -f "${src}" || true)
		if [[ -n "${resolved}" && "${resolved}" == /* ]]; then
			copy_path_with_target "${resolved}"
		fi
	fi
}

copy_tree() {
	local src="$1"
	local dst

	[[ -e "${src}" ]] || return 0
	dst="${MNT}${src}"
	mkdir -p "$(dirname "${dst}")"
	cp -a "${src}" "${dst}"
}

copy_ldd_deps() {
	local elf="$1"

	[[ -e "${elf}" ]] || return 0
	if ! file -b "${elf}" | grep -q 'ELF'; then
		return 0
	fi

	ldd "${elf}" 2>/dev/null |
		awk '
			/=> \// { print $3; next }
			/^\// { print $1; next }
		' |
		while read -r dep; do
			[[ -n "${dep}" ]] || continue
			copy_path_with_target "${dep}"
		done
}

copy_binary() {
	local bin="$1"
	local path

	if [[ "${bin}" == /* ]]; then
		path="${bin}"
	else
		path=$(type -P "${bin}" 2>/dev/null || true)
	fi
	[[ -n "${path}" ]] || return 0

	copy_path_with_target "${path}"
	copy_ldd_deps "$(readlink -f "${path}")"
}

copy_dynamic_loader() {
	copy_path_with_target /lib/ld-linux-aarch64.so.1
	copy_path_with_target /lib/aarch64-linux-gnu/ld-linux-aarch64.so.1
}

copy_glob() {
	local pattern="$1"
	local path

	shopt -s nullglob
	for path in ${pattern}; do
		copy_path_with_target "${path}"
		copy_ldd_deps "$(readlink -f "${path}")"
	done
	shopt -u nullglob
}

copy_mesa_runtime() {
	local f

	copy_tree /usr/lib/aarch64-linux-gnu/dri
	copy_tree /usr/lib/aarch64-linux-gnu/gbm
	copy_tree /usr/local/lib/aarch64-linux-gnu/gbm
	copy_tree /usr/share/glvnd
	copy_tree /etc/glvnd
	copy_tree /usr/share/drirc.d
	copy_tree /etc/OpenCL
	copy_tree /etc/sensors.d
	copy_path /etc/sensors3.conf

	copy_glob '/usr/lib/aarch64-linux-gnu/libEGL*.so*'
	copy_glob '/usr/lib/aarch64-linux-gnu/libGLES*.so*'
	copy_glob '/usr/lib/aarch64-linux-gnu/libGLdispatch*.so*'
	copy_glob '/usr/lib/aarch64-linux-gnu/libglapi*.so*'
	copy_glob '/usr/lib/aarch64-linux-gnu/libgbm*.so*'
	copy_glob '/usr/lib/aarch64-linux-gnu/libgallium*.so*'
	copy_glob '/usr/local/lib/aarch64-linux-gnu/libgbm*.so*'

	for f in \
		/usr/lib/aarch64-linux-gnu/dri/*.so \
		/usr/lib/aarch64-linux-gnu/gbm/*.so \
		/usr/local/lib/aarch64-linux-gnu/gbm/*.so \
		/usr/lib/aarch64-linux-gnu/libEGL_mesa.so* \
		/usr/lib/aarch64-linux-gnu/libgbm.so* \
		/usr/local/lib/aarch64-linux-gnu/libgbm.so*; do
		[[ -e "${f}" || -L "${f}" ]] || continue
		copy_ldd_deps "$(readlink -f "${f}")"
	done
}

write_guest_config() {
	cat >"${MNT}/etc/passwd" <<'EOF'
root:x:0:0:root:/root:/bin/sh
EOF

	cat >"${MNT}/etc/group" <<'EOF'
root:x:0:
video:x:44:root
render:x:107:root
EOF

	cat >"${MNT}/etc/nsswitch.conf" <<'EOF'
passwd: files
group: files
shadow: files
hosts: files dns
networks: files
protocols: files
services: files
ethers: files
rpc: files
EOF

	cat >"${MNT}/etc/hostname" <<'EOF'
firecracker-gpu-smoke
EOF

	cat >"${MNT}/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 firecracker-gpu-smoke
EOF

	cat >"${MNT}/etc/fstab" <<'EOF'
/dev/vda / ext4 defaults 0 1
proc /proc proc defaults 0 0
sysfs /sys sysfs defaults 0 0
devtmpfs /dev devtmpfs defaults 0 0
EOF

	cat >"${MNT}/etc/ld.so.conf" <<'EOF'
include /etc/ld.so.conf.d/*.conf
EOF

	mkdir -p "${MNT}/etc/ld.so.conf.d"
	cat >"${MNT}/etc/ld.so.conf.d/aarch64-linux-gnu.conf" <<'EOF'
/usr/local/lib/aarch64-linux-gnu
/lib/aarch64-linux-gnu
/usr/lib/aarch64-linux-gnu
EOF
}

make_device_nodes() {
	mkdir -p "${MNT}/dev"
	[[ -e "${MNT}/dev/console" ]] || mknod -m 600 "${MNT}/dev/console" c 5 1
	[[ -e "${MNT}/dev/null" ]] || mknod -m 666 "${MNT}/dev/null" c 1 3
	[[ -e "${MNT}/dev/zero" ]] || mknod -m 666 "${MNT}/dev/zero" c 1 5
	[[ -e "${MNT}/dev/tty" ]] || mknod -m 666 "${MNT}/dev/tty" c 5 0
}

require_cmd cc
require_cmd file
require_cmd ldd
require_cmd mkfs.ext4
require_cmd mount
require_cmd umount
require_cmd truncate

[[ -d "${TARGET_DIR}" ]] || die "missing target directory: ${TARGET_DIR}"
[[ -d "${SRC_DIR}" ]] || die "missing source directory: ${SRC_DIR}"
[[ -f "${SRC_DIR}/gles_compute_smoke.c" ]] || die "missing ${SRC_DIR}/gles_compute_smoke.c"
[[ -f "${SRC_DIR}/gpu-smoke.sh" ]] || die "missing ${SRC_DIR}/gpu-smoke.sh"
[[ -f "${SRC_DIR}/init" ]] || die "missing ${SRC_DIR}/init"
[[ -f "${FW_SRC}" ]] || die "missing firmware: ${FW_SRC}"

log "Compiling GLES compute smoke test"
rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"
cc -O2 -Wall -Wextra -std=c11 \
	"${SRC_DIR}/gles_compute_smoke.c" \
	-o "${SMOKE_BIN}" \
	$(pkg-config --cflags --libs egl glesv2 gbm)

mkdir -p "${MNT}"

log "Creating ${IMAGE_SIZE} ext4 image"
truncate -s "${IMAGE_SIZE}" "${NEW_IMAGE}"
mkfs.ext4 -F -L panfrost-rootfs "${NEW_IMAGE}"

log "Mounting new image"
mount -o loop "${NEW_IMAGE}" "${MNT}"

log "Creating base directory layout"
mkdir -p \
	"${MNT}/bin" \
	"${MNT}/sbin" \
	"${MNT}/lib" \
	"${MNT}/usr/bin" \
	"${MNT}/usr/sbin" \
	"${MNT}/usr/lib" \
	"${MNT}/usr/local/lib" \
	"${MNT}/etc" \
	"${MNT}/lib/firmware" \
	"${MNT}/proc" \
	"${MNT}/sys" \
	"${MNT}/run" \
	"${MNT}/tmp" \
	"${MNT}/root"
chmod 1777 "${MNT}/tmp"

log "Copying shell, tools, and shared-library closure"
copy_dynamic_loader
for bin in \
	/bin/sh \
	/bin/dash \
	/bin/bash \
	cat \
	chmod \
	dmesg \
	find \
	grep \
	hostname \
	ls \
	mkdir \
	mount \
	mountpoint \
	printf \
	readlink \
	sleep \
	sync \
	tail \
	tee \
	touch \
	uname \
	strace \
	bpftrace \
	trace-cmd \
	/sbin/ldconfig; do
	copy_binary "${bin}"
done

log "Copying Mesa GBM/EGL/GLES runtime"
copy_mesa_runtime

log "Installing smoke test, firmware, and init"
install -Dm0755 "${SRC_DIR}/init" "${MNT}/init"
install -Dm0755 "${SRC_DIR}/gpu-smoke.sh" "${MNT}/root/gpu-smoke.sh"
install -Dm0755 "${SMOKE_BIN}" "${MNT}/root/gles-compute-smoke"
copy_ldd_deps "${SMOKE_BIN}"
install -Dm0644 "${FW_SRC}" "${MNT}/lib/firmware/arm/mali/arch10.8/mali_csffw.bin"

if [[ -f "${SRC_DIR}/trace-panthor-task.sh" ]]; then
	install -Dm0755 "${SRC_DIR}/trace-panthor-task.sh" "${MNT}/root/trace-panthor-task.sh"
fi

if [[ -f "${SRC_DIR}/panthor-task.bt" ]]; then
	install -Dm0644 "${SRC_DIR}/panthor-task.bt" "${MNT}/root/panthor-task.bt"
fi

if [[ -f "${IOCTL_SMOKE_TEST}" ]]; then
	install -Dm0755 "${IOCTL_SMOKE_TEST}" "${MNT}/root/panthor_ioctl_smoke"
fi

write_guest_config
make_device_nodes

log "Refreshing guest dynamic linker cache"
chroot "${MNT}" /sbin/ldconfig

log "Final image content summary"
du -sh "${MNT}" || true
find "${MNT}/root" "${MNT}/usr/lib/aarch64-linux-gnu/dri" "${MNT}/usr/lib/aarch64-linux-gnu/gbm" \
	-maxdepth 1 -mindepth 1 -printf '%p\n' 2>/dev/null | sed -n '1,120p'

sync
umount "${MNT}"

if [[ -f "${IMAGE_PATH}" ]]; then
	backup="${IMAGE_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
	log "Backing up existing ${IMAGE_PATH} to ${backup}"
	mv "${IMAGE_PATH}" "${backup}"
fi

mv "${NEW_IMAGE}" "${IMAGE_PATH}"
chmod 0644 "${IMAGE_PATH}"
sync

log "Built ${IMAGE_PATH}"
ls -lh "${IMAGE_PATH}"
