#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="${GPU_PRIVATE_TEST_OUT:-$ROOT/build/rmm-client-bo-20261030/unit}"
RMM="$ROOT/opencca/tf-rmm"
mkdir -p "$OUT"
python3 "$ROOT/scripts/check/check-gpu-control-cache.py"
python3 "$ROOT/scripts/check/check-gpu-stream-status.py"
python3 "$ROOT/scripts/check/check-gpu-replay-input.py" --out "$OUT/replay-input-$$"
python3 "$ROOT/scripts/check/check-gpu-cache-set.py"
python3 "$ROOT/scripts/check/check-gpu-live-summary.py" --out "$OUT/live-summary-$$"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/tests/opencca_gpu_private_test.c" \
    -o "$OUT/opencca_gpu_private_test"
"$OUT/opencca_gpu_private_test"
"$OUT/opencca_gpu_private_test" --root-boundary
"$OUT/opencca_gpu_private_test" --service-mapping
"$OUT/opencca_gpu_private_test" --mapping-authorization
"$OUT/opencca_gpu_private_test" --device-revocation
"$OUT/opencca_gpu_private_test" --mapping-check
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/tests/opencca_gpu_control_test.c" \
    -o "$OUT/opencca_gpu_control_test"
"$OUT/opencca_gpu_control_test"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/tests/rtt-stubs" -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/core/xshm_rtt.c" "$RMM/runtime/core/xshm_policy.c" \
    "$RMM/runtime/tests/opencca_gpu_control_rtt_test.c" \
    -o "$OUT/opencca_gpu_control_rtt_test"
"$OUT/opencca_gpu_control_rtt_test"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -DGPU_PRIVATE_TABLES=8 -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/tests/opencca_gpu_private_test.c" \
    -o "$OUT/opencca_gpu_private_exhaustion_test"
"$OUT/opencca_gpu_private_exhaustion_test" --table-exhaustion
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/tests/opencca_gpu_extension_test.c" \
    -o "$OUT/opencca_gpu_extension_test"
for scenario in {0..34}; do
    "$OUT/opencca_gpu_extension_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -DGPU_PRIVATE_TABLES=8 -I"$RMM/runtime/include" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/tests/opencca_gpu_extension_test.c" \
    -o "$OUT/opencca_gpu_extension_exhaustion_test"
"$OUT/opencca_gpu_extension_exhaustion_test" 35
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror \
    -I"$RMM/runtime/include" -iquote "$ROOT/Linux-Guest-GPU/include/uapi" \
    "$ROOT/GPU-SFTP/tests/realm-xshm/realm-gpu-abi.c" \
    -o "$OUT/realm_gpu_abi_test"
"$OUT/realm_gpu_abi_test"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/tests/mmio-stubs" -I"$RMM/runtime/include" -I"$RMM/ext/mbedtls/include" \
    -I"$RMM/ext/mbedtls/library" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/core/opencca_gpu_firmware.c" \
    "$RMM/runtime/tests/opencca_gpu_firmware_test.c" \
    "$RMM/ext/mbedtls/library/sha256.c" \
    "$RMM/ext/mbedtls/library/platform_util.c" \
    -o "$OUT/opencca_gpu_firmware_test"
"$OUT/opencca_gpu_firmware_test" "$ROOT/GPU-SFTP/panthor_fw/mali_csffw.bin"
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_resident_test.c" \
    -o "$OUT/opencca_gpu_resident_test"
for scenario in {0..18}; do
    "$OUT/opencca_gpu_resident_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_sparse_cache_test.c" \
    -o "$OUT/opencca_gpu_sparse_cache_test"
for scenario in {0..5}; do
    "$OUT/opencca_gpu_sparse_cache_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_cache_budget_test.c" \
    -o "$OUT/opencca_gpu_cache_budget_test"
for scenario in {0..20}; do
    "$OUT/opencca_gpu_cache_budget_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_leaf_batch_test.c" \
    -o "$OUT/opencca_gpu_leaf_batch_test"
for scenario in {0..319}; do
    "$OUT/opencca_gpu_leaf_batch_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_uncached_test.c" \
    -o "$OUT/opencca_gpu_uncached_test"
for scenario in {0..23}; do
    "$OUT/opencca_gpu_uncached_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_return_replay_test.c" \
    -o "$OUT/opencca_gpu_return_replay_test"
for scenario in {0..22}; do
    "$OUT/opencca_gpu_return_replay_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_lease_groups_test.c" \
    -o "$OUT/opencca_gpu_lease_groups_test"
for scenario in {0..25}; do
    "$OUT/opencca_gpu_lease_groups_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_scan_window_test.c" \
    -o "$OUT/opencca_gpu_scan_window_test"
for scenario in {0..7}; do
    "$OUT/opencca_gpu_scan_window_test" "$scenario" current
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/tests/mmio-stubs" -I"$RMM/runtime/include" \
    -I"$RMM/ext/mbedtls/include" -I"$RMM/ext/mbedtls/library" \
    "$RMM/runtime/core/opencca_gpu_private.c" \
    "$RMM/runtime/tests/opencca_gpu_queue_history_test.c" \
    "$RMM/ext/mbedtls/library/sha256.c" \
    "$RMM/ext/mbedtls/library/platform_util.c" \
    -o "$OUT/opencca_gpu_queue_history_test"
for scenario in {0..17}; do
    "$OUT/opencca_gpu_queue_history_test" "$scenario"
done
"${HOST_CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
    -I"$RMM/runtime/core" -I"$RMM/runtime/include" \
    "$RMM/runtime/tests/opencca_gpu_live_lease_test.c" \
    -o "$OUT/opencca_gpu_live_lease_test"
for scenario in {0..30}; do
    "$OUT/opencca_gpu_live_lease_test" "$scenario"
done
python3 "$ROOT/scripts/check/check-gpu-group-bridge.py"

python3 "$ROOT/scripts/check/check-gpu-private-bind.py"
python3 "$ROOT/scripts/check/check-gpu-rmm-service.py"
python3 "$ROOT/scripts/check/check-gpu-task-bridge.py"
python3 "$ROOT/scripts/check/check-gpu-private-heap.py"
python3 "$ROOT/scripts/check/check-gpu-private-submit.py"
python3 "$ROOT/scripts/check/check-gpu-private-runner.py"
python3 "$ROOT/scripts/check/check-panthor-eventfd-smoke.py"
python3 "$ROOT/scripts/check/check-gpu-completion-eventfd.py" --out "$OUT/completion-eventfd"
python3 "$ROOT/scripts/check/check-gpu-private-reclaim.py"
python3 "$ROOT/scripts/check/check-gpu-private-teardown.py"
python3 "$ROOT/scripts/check/check-gpu-rsi-boundary.py" --out "$OUT/rsi-boundary-$$"
python3 "$ROOT/scripts/check/check-gpu-input-identity.py" --out "$OUT/input-identity-$$"
python3 "$ROOT/scripts/check/check-gpu-memory-ops.py" --out "$OUT/memory-ops-$$"
python3 "$ROOT/scripts/check/check-gpu-rsi-memory-chain.py" --out "$OUT/rsi-memory-chain-$$"
python3 "$ROOT/scripts/check/check-gpu-rsi-memory-chain.py" --task-chain --out "$OUT/rsi-task-chain-$$"
python3 "$ROOT/scripts/check/check-gpu-rsi-memory-chain.py" --realm-lifecycle --out "$OUT/realm-lifecycle-$$"
python3 "$ROOT/scripts/check/check-gpu-rmi-dispatch.py" --out "$OUT/rmi-dispatch-$$"
