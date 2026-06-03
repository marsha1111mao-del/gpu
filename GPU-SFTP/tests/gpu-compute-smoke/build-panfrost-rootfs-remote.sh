#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR=${TARGET_DIR:-/root/GPU-SFTP/firecracker-bins/rootfs}
SRC_DIR=${SRC_DIR:-/root/GPU-SFTP/tests/gpu-compute-smoke}
FW_SRC=${FW_SRC:-/root/GPU-SFTP/panthor_fw/mali_csffw.bin}
IOCTL_SMOKE_TEST=${IOCTL_SMOKE_TEST:-${RAW_IOCTL_TEST:-/root/GPU-SFTP/firecracker-bins/bin/panthor_ioctl_smoke}}
IMAGE_NAME=${IMAGE_NAME:-rootfs-panfrost.ext4}
IMAGE_SIZE=${IMAGE_SIZE:-1536M}
SUITE=${SUITE:-trixie}
MIRROR=${MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian}

IMAGE_PATH="${TARGET_DIR}/${IMAGE_NAME}"
WORK_DIR="${TARGET_DIR}/work/rootfs-panfrost-build"
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

apt_install_host_deps() {
	local need=0
	local packages=(
		gcc
		pkg-config
		libegl-dev
		libgles-dev
		libgbm-dev
	)

	for pkg in "${packages[@]}"; do
		if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed'; then
			need=1
		fi
	done

	if [[ "${need}" -eq 1 ]]; then
		log "Installing host build dependencies"
		apt-get update
		DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
	fi
}

package_exists() {
	apt-cache show "$1" >/dev/null 2>&1
}

cleanup() {
	set +e
	if mountpoint -q "${MNT}"; then
		umount "${MNT}"
	fi
}
trap cleanup EXIT

require_cmd debootstrap
require_cmd mkfs.ext4
require_cmd mount
require_cmd umount
require_cmd truncate
require_cmd cc
require_cmd apt-cache

[[ -d "${TARGET_DIR}" ]] || die "missing target directory: ${TARGET_DIR}"
[[ -d "${SRC_DIR}" ]] || die "missing source directory: ${SRC_DIR}"
[[ -f "${SRC_DIR}/gles_compute_smoke.c" ]] || die "missing ${SRC_DIR}/gles_compute_smoke.c"
[[ -f "${SRC_DIR}/gpu-smoke.sh" ]] || die "missing ${SRC_DIR}/gpu-smoke.sh"
[[ -f "${SRC_DIR}/init" ]] || die "missing ${SRC_DIR}/init"
[[ -f "${FW_SRC}" ]] || die "missing firmware: ${FW_SRC}"

apt_install_host_deps

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

packages=(
	bash
	busybox-static
	ca-certificates
	kmod
	procps
	psmisc
	strace
	util-linux
	libdrm2
	libdrm-common
	libegl1
	libgles2
	libgbm1
	libgl1-mesa-dri
	mesa-libgallium
)

optional_packages=(
	libdrm-panfrost1
	mesa-utils-bin
	eglinfo
)

for pkg in "${optional_packages[@]}"; do
	if package_exists "${pkg}"; then
		packages+=("${pkg}")
	fi
done

include_list=$(IFS=,; echo "${packages[*]}")

log "Bootstrapping Debian ${SUITE} arm64 rootfs"
debootstrap \
	--arch=arm64 \
	--variant=minbase \
	--include="${include_list}" \
	"${SUITE}" \
	"${MNT}" \
	"${MIRROR}"

log "Installing smoke test, firmware, and init"
install -Dm0755 "${SRC_DIR}/init" "${MNT}/init"
install -Dm0755 "${SRC_DIR}/gpu-smoke.sh" "${MNT}/root/gpu-smoke.sh"
install -Dm0755 "${SMOKE_BIN}" "${MNT}/root/gles-compute-smoke"
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

mkdir -p "${MNT}/dev" "${MNT}/proc" "${MNT}/sys" "${MNT}/run" "${MNT}/tmp"
chmod 1777 "${MNT}/tmp"
if [[ ! -e "${MNT}/dev/console" ]]; then
	mknod -m 600 "${MNT}/dev/console" c 5 1
fi
if [[ ! -e "${MNT}/dev/null" ]]; then
	mknod -m 666 "${MNT}/dev/null" c 1 3
fi

log "Cleaning rootfs package cache"
chroot "${MNT}" /bin/sh -c 'ldconfig; apt-get clean; rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*'

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
