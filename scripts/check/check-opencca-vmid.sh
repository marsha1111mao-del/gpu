#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="$ROOT/build/secure-services-20261019/protected-realm/unit"
RMM="$ROOT/opencca/tf-rmm"
mkdir -p "$OUT"
for opencca in 0 1; do
    "${HOST_CC:-cc}" -std=c11 -D_XOPEN_SOURCE=700 -DENABLE_OPENCCA="$opencca" \
        -Wall -Wextra -Werror -g -pthread \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        -I"$RMM/lib/arch/tests/vmid-stubs" -I"$RMM/lib/arch/include" \
        -I"$RMM/lib/common/include" \
        "$RMM/lib/arch/src/vmid.c" "$RMM/lib/arch/tests/vmid_test.c" \
        -o "$OUT/vmid-test-$opencca"
    "$OUT/vmid-test-$opencca" 8
    "$OUT/vmid-test-$opencca" 16
done
