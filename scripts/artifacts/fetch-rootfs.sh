#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
MANIFEST="${MANIFEST:-"${ROOT_DIR}/GPU-SFTP/rootfs-manifest.json"}"
DEST_DIR="${DEST_DIR:-"${ROOT_DIR}/GPU-SFTP/firecracker-bins/rootfs"}"
FORCE=0
ONLY=()

usage() {
	cat <<EOF
Usage: $(basename "$0") [options] [artifact-name ...]

Download rootfs artifacts listed in GPU-SFTP/rootfs-manifest.json, verify their
size and sha256, and install them under GPU-SFTP/firecracker-bins/rootfs/.

Options:
  --manifest PATH  Use a different manifest file
  --dest DIR       Download/install into a different rootfs directory
  --force          Redownload even when a local artifact already verifies
  -h, --help       Show this help

Artifact names:
  rootfs.ext2
  rootfs-panfrost.ext4
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--manifest)
		shift
		[[ $# -gt 0 ]] || { echo "--manifest requires a path" >&2; exit 2; }
		MANIFEST=$1
		;;
	--dest)
		shift
		[[ $# -gt 0 ]] || { echo "--dest requires a directory" >&2; exit 2; }
		DEST_DIR=$1
		;;
	--force)
		FORCE=1
		;;
	-h | --help)
		usage
		exit 0
		;;
	-*)
		echo "unknown option: $1" >&2
		usage >&2
		exit 2
		;;
	*)
		ONLY+=("$1")
		;;
	esac
	shift
done

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || {
		echo "missing command: $1" >&2
		exit 1
	}
}

contains_name() {
	local needle="$1"
	local item

	[[ "${#ONLY[@]}" -gt 0 ]] || return 0
	for item in "${ONLY[@]}"; do
		[[ "${item}" == "${needle}" ]] && return 0
	done
	return 1
}

verify_file() {
	local path="$1"
	local size="$2"
	local sha="$3"
	local actual_size actual_sha

	[[ -f "${path}" ]] || return 1
	actual_size=$(stat -c '%s' "${path}")
	[[ "${actual_size}" == "${size}" ]] || return 1
	actual_sha=$(sha256sum "${path}" | awk '{print $1}')
	[[ "${actual_sha}" == "${sha}" ]]
}

require_cmd curl
require_cmd python3
require_cmd sha256sum
require_cmd stat

[[ -f "${MANIFEST}" ]] || {
	echo "missing manifest: ${MANIFEST}" >&2
	exit 1
}

mkdir -p "${DEST_DIR}"

read -r RELEASE_REPO RELEASE_TAG < <(
	python3 - "${MANIFEST}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    manifest = json.load(f)

release = manifest.get("release", {})
print(release.get("repository", ""), release.get("tag", ""))
PY
)

mapfile -t records < <(
	python3 - "${MANIFEST}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    manifest = json.load(f)

for artifact in manifest.get("artifacts", []):
    print("{name}\t{url}\t{size}\t{sha256}".format(**artifact))
PY
)

if [[ "${#records[@]}" -eq 0 ]]; then
	echo "manifest has no artifacts: ${MANIFEST}" >&2
	exit 1
fi

download_artifact() {
	local name="$1"
	local url="$2"
	local dst="$3"
	local gh_tmp

	if curl -fL --retry 3 --continue-at - --output "${dst}" "${url}"; then
		return 0
	fi

	if command -v gh >/dev/null 2>&1 &&
	   [[ -n "${RELEASE_REPO}" && -n "${RELEASE_TAG}" ]]; then
		echo "curl download failed; retrying ${name} with gh release download" >&2
		gh_tmp=$(mktemp -d /tmp/gpu-rootfs-gh.XXXXXX)
		if gh release download "${RELEASE_TAG}" \
			--repo "${RELEASE_REPO}" \
			--pattern "${name}" \
			--dir "${gh_tmp}"; then
			mv -f -- "${gh_tmp}/${name}" "${dst}"
			rm -rf -- "${gh_tmp}"
			return 0
		fi
		rm -rf -- "${gh_tmp}"
	fi

	return 1
}

for record in "${records[@]}"; do
	IFS=$'\t' read -r name url size sha <<<"${record}"
	contains_name "${name}" || continue

	dst="${DEST_DIR}/${name}"
	tmp="${dst}.download"

	if [[ "${FORCE}" -eq 0 ]] && verify_file "${dst}" "${size}" "${sha}"; then
		echo "OK: ${dst}"
		continue
	fi

	echo "Downloading ${name}"
	rm -f -- "${tmp}"
	download_artifact "${name}" "${url}" "${tmp}"

	if ! verify_file "${tmp}" "${size}" "${sha}"; then
		rm -f -- "${tmp}"
		echo "verification failed: ${name}" >&2
		exit 1
	fi

	mv -f -- "${tmp}" "${dst}"
	echo "Installed: ${dst}"
done
