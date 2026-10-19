#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="$ROOT/build/secure-services-20261019/protected-realm/unit"
RMM="$ROOT/opencca/tf-rmm"
mkdir -p "$OUT"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$RMM/runtime/tests/timer-stubs" -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_timers.c" \
    "$RMM/plat/rk3588/src/rk3588_timers.c" \
    "$RMM/runtime/tests/opencca_timers_test.c" \
    -o "$OUT/opencca-timers-test"
"$OUT/opencca-timers-test"
