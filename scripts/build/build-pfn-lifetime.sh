#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="${OUT:-${ROOT_DIR}/GPU-SFTP/firecracker-bins/bin/pmthor-pfn-lifetime}"
mkdir -p "$(dirname "${OUT}")"
"${CC:-aarch64-linux-gnu-gcc}" -O2 -Wall -Wextra -Werror -static \
	-o "${OUT}" \
	"${ROOT_DIR}/GPU-SFTP/tests/pmthor-pfn-lifetime/pmthor_pfn_lifetime.c"
echo "Installed ${OUT}"
