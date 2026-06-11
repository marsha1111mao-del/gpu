#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_DIR="${SRC_DIR:-"${ROOT_DIR}/GPU-SFTP/tests/vmshm-lookup-probe"}"
OUT="${OUT:-"${SRC_DIR}/vmshm_lookup_probe"}"
CC="${CC:-aarch64-linux-gnu-gcc}"
INSTALL_PATH="${INSTALL_PATH:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins/bin/vmshm_lookup_probe"}"

"${CC}" -O2 -Wall -Wextra -static -o "${OUT}" \
	"${SRC_DIR}/vmshm_lookup_probe.c"

install -v -m 0755 "${OUT}" "${INSTALL_PATH}"
