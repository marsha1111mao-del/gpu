#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE_ROOT=$(cd -- "${ROOT}/../../.." && pwd)
exec "${WORKSPACE_ROOT}/scripts/build/build-vmshm-demo.sh" "$@"
