#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
TARGET="${TARGET:-aarch64-unknown-linux-musl}"
PROFILE="${PROFILE:-release}"
LINKER="${LINKER:-aarch64-linux-musl-gcc}"
SFTP_DIR="${SFTP_DIR:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins"}"

FC_DIR="${FC_DIR:-"${ROOT_DIR}/firecracker/Firecracker-CCA-MZH"}"
FC_OUT="${FC_OUT:-"${FC_DIR}/build/cargo_target/${TARGET}/${PROFILE}/firecracker"}"
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER="${LINKER}"

if [[ "${PROFILE}" != "release" && "${PROFILE}" != "debug" ]]; then
	echo "PROFILE must be 'release' or 'debug', got '${PROFILE}'" >&2
	exit 2
fi

echo "==> Building Firecracker"
(
	cd "${FC_DIR}"
	if [[ "${PROFILE}" == "release" ]]; then
		TARGET="${TARGET}" cargo build --locked --release --target "${TARGET}" --bin firecracker
	else
		TARGET="${TARGET}" cargo build --locked --target "${TARGET}" --bin firecracker
	fi
)

echo "==> Installing binaries to ${SFTP_DIR}"
mkdir -p "${SFTP_DIR}/bin"
install -v -m 0755 "${FC_OUT}" "${SFTP_DIR}/bin/firecracker"
