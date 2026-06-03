#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TARGET=${TARGET:-aarch64-unknown-linux-musl}
SFTP_DIR=${SFTP_DIR:-/home/mzh/gpu/GPU-SFTP/firecracker-bins}

FC_DIR="${ROOT}/Firecracker-CCA-MZH"
BROKER_DIR="${ROOT}/vmshm-broker"
FC_OUT="${FC_DIR}/build/cargo_target/${TARGET}/release/firecracker"
BROKER_OUT="${BROKER_DIR}/build/cargo_target/${TARGET}/release/vmshm-broker"
CLIENT_TEST_OUT="${BROKER_DIR}/build/cargo_target/${TARGET}/release/vmshm-client-test"

mkdir -p "${SFTP_DIR}"

echo "==> Building Firecracker"
(
	cd "${FC_DIR}"
	TARGET="${TARGET}" ./sftp-build.sh
)

echo
echo "==> Building vmshm-broker"
(
	cd "${BROKER_DIR}"
	TARGET="${TARGET}" ./sftp-build.sh
)

echo
echo "==> Installing binaries to ${SFTP_DIR}"
mkdir -p "${SFTP_DIR}/bin"
install -v -m 0755 "${FC_OUT}" "${SFTP_DIR}/bin/firecracker"
install -v -m 0755 "${BROKER_OUT}" "${SFTP_DIR}/bin/vmshm-broker"
install -v -m 0755 "${CLIENT_TEST_OUT}" "${SFTP_DIR}/bin/vmshm-client-test"
