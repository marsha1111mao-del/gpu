#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="$ROOT/build/secure-services-20261019/host-mmio/unit"
TESTS="$ROOT/GPU-SFTP/tests/dma-guard"
mkdir -p "$OUT"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$TESTS/mmio-stubs" \
    -I"$ROOT/Linux-Host-GPU/arch/arm64/kvm/hyp/include" \
    -I"$ROOT/Linux-Host-GPU/arch/arm64/include/uapi" \
    "$TESTS/opencca_host_mmio_test.c" -o "$OUT/opencca-host-mmio-test"
"$OUT/opencca-host-mmio-test"
