#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BINS_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../../.." && pwd)

exec "${BINS_DIR}/bin/vmshm-broker" --config "${BINS_DIR}/configs/shared/vmshm-1client/broker-config.toml"
