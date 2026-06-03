#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
TARGET="${TARGET:-aarch64-unknown-linux-musl}"
PROFILE="${PROFILE:-release}"
LINKER="${LINKER:-aarch64-linux-musl-gcc}"
SFTP_DIR="${SFTP_DIR:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins"}"

FC_DIR="${FC_DIR:-"${ROOT_DIR}/firecracker/Firecracker-CCA-MZH"}"
BROKER_DIR="${BROKER_DIR:-"${ROOT_DIR}/firecracker/vmshm-broker"}"
FC_OUT="${FC_OUT:-"${FC_DIR}/build/cargo_target/${TARGET}/${PROFILE}/firecracker"}"
BROKER_TARGET_DIR="${BROKER_TARGET_DIR:-"${BROKER_DIR}/build/cargo_target"}"
BROKER_PROFILE_DIR="${BROKER_PROFILE_DIR:-"${BROKER_TARGET_DIR}/${TARGET}/${PROFILE}"}"
BROKER_OUT="${BROKER_OUT:-"${BROKER_PROFILE_DIR}/vmshm-broker"}"
CLIENT_TEST_OUT="${CLIENT_TEST_OUT:-"${BROKER_PROFILE_DIR}/vmshm-client-test"}"

if [[ "${PROFILE}" != "release" && "${PROFILE}" != "debug" ]]; then
	echo "PROFILE must be 'release' or 'debug', got '${PROFILE}'" >&2
	exit 2
fi

echo "==> Building Firecracker"
(
	cd "${FC_DIR}"
	if [[ "${PROFILE}" == "release" ]]; then
		TARGET="${TARGET}" cargo build --release --target "${TARGET}" --bins --examples
	else
		TARGET="${TARGET}" cargo build --target "${TARGET}" --bins --examples
	fi
)

echo
echo "==> Building vmshm-broker"
(
	cd "${BROKER_DIR}"
	TARGET="${TARGET}" \
	PROFILE="${PROFILE}" \
	LINKER="${LINKER}" \
	CARGO_TARGET_DIR="${BROKER_TARGET_DIR}" \
		./scripts/build-aarch64.sh
)

echo
echo "==> Installing binaries to ${SFTP_DIR}"
mkdir -p "${SFTP_DIR}/bin"
install -v -m 0755 "${FC_OUT}" "${SFTP_DIR}/bin/firecracker"
install -v -m 0755 "${BROKER_OUT}" "${SFTP_DIR}/bin/vmshm-broker"
install -v -m 0755 "${CLIENT_TEST_OUT}" "${SFTP_DIR}/bin/vmshm-client-test"
