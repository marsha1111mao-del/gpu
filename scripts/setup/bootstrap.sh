#!/usr/bin/env bash
# Restore a portable checkout without deploying or flashing hardware.
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
FIRMWARE=0
ROOTFS=1
RUNTIME=1
while [[ $# -gt 0 ]]; do
	case "$1" in
	--firmware) FIRMWARE=1 ;;
	--no-rootfs) ROOTFS=0 ;;
	--no-runtime) RUNTIME=0 ;;
	-h|--help)
		echo "Usage: $0 [--firmware] [--no-rootfs] [--no-runtime]"
		echo "Initialize source repositories; verify/restore runtime and rootfs artifacts."
		echo "--firmware also initializes and patches the pinned OpenCCA build inputs."
		exit 0 ;;
	*) echo "Unknown option: $1" >&2; exit 2 ;;
	esac
	shift
done
git -C "${ROOT_DIR}" submodule update --init
if [[ "${FIRMWARE}" == 1 ]]; then
	git -C "${ROOT_DIR}/opencca" submodule update --init --recursive \
		armbian-rkbin opencca-assets opencca-build opencca-flash \
		debian-image-recipes u-boot trusted-firmware-a tf-rmm rkbin
	python3 "${ROOT_DIR}/opencca/scripts/setup/apply-local-patches.py"
fi
if [[ "${RUNTIME}" == 1 ]]; then
	python3 "${ROOT_DIR}/scripts/artifacts/restore-runtime.py"
fi
if [[ "${ROOTFS}" == 1 ]]; then
	"${ROOT_DIR}/scripts/artifacts/fetch-rootfs.sh"
fi
echo "Bootstrap complete. Hardware prerequisites and regression commands: docs/start/FRESH_CLONE.md"
