#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="$ROOT/build/dma-guard-20261018/unit"
RMM="$ROOT/opencca/tf-rmm"
mkdir -p "$OUT"
for test in opencca_gpu_lease opencca_dma_guard; do
    "${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        -I"$RMM/runtime/include" "$RMM/runtime/core/opencca_gpu_lease.c" \
        "$RMM/runtime/core/opencca_gpu.c" \
        "$RMM/runtime/tests/${test}_test.c" -o "$OUT/$test"
    "$OUT/$test"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$RMM/runtime/tests/mmio-stubs" -I"$RMM/runtime/include" \
    "$RMM/plat/rk3588/src/rk3588_gpu.c" \
    "$RMM/runtime/tests/opencca_gpu_backend_test.c" -o "$OUT/opencca_gpu_backend"
"$OUT/opencca_gpu_backend"
