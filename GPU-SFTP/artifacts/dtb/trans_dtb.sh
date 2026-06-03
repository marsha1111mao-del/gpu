#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DTB_DIR="${ROOT_DIR}"

if ! command -v dtc >/dev/null 2>&1; then
	echo "missing command: dtc (install device-tree-compiler)" >&2
	exit 1
fi

dtc -I dtb -O dts "${DTB_DIR}/firecracker.dtb" -o "${DTB_DIR}/firecracker.dts"
