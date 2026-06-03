#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${ROOT}/../../.." && pwd)
CC=${CC:-aarch64-linux-gnu-gcc}
OUT=${OUT:-"${ROOT}/vmshm_demo"}
INSTALL_PATH=${INSTALL_PATH:-"${REPO_ROOT}/GPU-SFTP/firecracker-bins/bin/vmshm_demo"}

"${CC}" -O2 -Wall -Wextra -static -o "${OUT}" "${ROOT}/vmshm-demo.c"
install -v -m 0755 "${OUT}" "${INSTALL_PATH}"
