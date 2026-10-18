#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT_DIR="$ROOT_DIR/build/realm-xshm"
mkdir -p "$OUT_DIR"
"${CROSS_COMPILE:-aarch64-linux-gnu-}gcc" -O2 -Wall -Wextra -Werror -static \
 -iquote "$ROOT_DIR/Linux-Guest-GPU/include/uapi" \
 "$ROOT_DIR/GPU-SFTP/tests/realm-xshm/realm-xshm.c" \
 -o "$OUT_DIR/realm-xshm"
file "$OUT_DIR/realm-xshm"

"${CROSS_COMPILE:-aarch64-linux-gnu-}gcc" -O2 -Wall -Wextra -Werror -static \
 "${ROOT_DIR}/GPU-SFTP/tests/realm-xshm/init.c" -o "$OUT_DIR/init"
