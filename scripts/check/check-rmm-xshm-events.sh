#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
RMM_DIR="$ROOT_DIR/opencca/tf-rmm"
OUT_DIR="$ROOT_DIR/build/xshm-endpoint-check"
mkdir -p "$OUT_DIR"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
 -fsanitize=address,undefined -fno-omit-frame-pointer \
 -I"$RMM_DIR/runtime/include" \
 -iquote "$ROOT_DIR/Linux-Guest-GPU/include/uapi" \
 "$RMM_DIR/runtime/core/xshm_endpoint.c" \
 "$RMM_DIR/runtime/tests/xshm_endpoint_test.c" \
 -o "$OUT_DIR/xshm-endpoint-test"
"$OUT_DIR/xshm-endpoint-test"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
 -fsanitize=address,undefined -fno-omit-frame-pointer \
 -I"$RMM_DIR/runtime/include" \
 "$RMM_DIR/runtime/core/xshm_memory.c" \
 "$RMM_DIR/runtime/core/xshm_endpoint.c" \
 "$RMM_DIR/runtime/core/xshm_service.c" \
 "$RMM_DIR/runtime/tests/xshm_memory_test.c" \
 -o "$OUT_DIR/xshm-memory-test"
"$OUT_DIR/xshm-memory-test"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
 -fsanitize=address,undefined -fno-omit-frame-pointer \
 -I"$RMM_DIR/runtime/include" \
 "$RMM_DIR/runtime/core/opencca_gpu_lease.c" \
 "$RMM_DIR/runtime/core/opencca_gpu.c" \
 "$RMM_DIR/runtime/tests/opencca_gpu_lease_test.c" \
 -o "$OUT_DIR/opencca-gpu-lease-test"
"$OUT_DIR/opencca-gpu-lease-test"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
 -fsanitize=address,undefined -fno-omit-frame-pointer \
 -I"$RMM_DIR/runtime/include" \
 "$RMM_DIR/runtime/core/xshm_irq.c" \
 "$RMM_DIR/runtime/tests/xshm_irq_test.c" \
 -o "$OUT_DIR/xshm-irq-test"
"$OUT_DIR/xshm-irq-test"
