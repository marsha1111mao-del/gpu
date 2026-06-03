#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BINS_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../../.." && pwd)

exec "${BINS_DIR}/bin/firecracker" --no-api --no-seccomp --config-file "${BINS_DIR}/configs/shared/vmshm-1client/proxy-vm-config.json"
