#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="$ROOT/build/secure-iommu-20261018/unit"
RMM="$ROOT/opencca/tf-rmm"
mkdir -p "$OUT"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_iommu.c" \
    "$RMM/runtime/core/opencca_gpu_lease.c" \
    "$RMM/runtime/core/opencca_gpu.c" \
    "$RMM/runtime/tests/opencca_iommu_test.c" \
    -o "$OUT/opencca_iommu_test"
"$OUT/opencca_iommu_test"
"$OUT/opencca_iommu_test" --fault-failure
"$OUT/opencca_iommu_test" --guest-fault-failure
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$RMM/runtime/tests/mmio-stubs" -I"$RMM/runtime/include" \
    "$RMM/plat/rk3588/src/rk3588_iommu.c" \
    "$RMM/runtime/tests/opencca_iommu_backend_test.c" \
    -o "$OUT/opencca_iommu_backend_test"
"$OUT/opencca_iommu_backend_test"
