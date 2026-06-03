#!/usr/bin/env bash
set -euo pipefail

install_modules=0
if [[ "${1:-}" == "--modules" ]]; then
	install_modules=1
fi

cp -v ./Image /boot/vmlinuz-6.12.0-opencca-wip
if [[ "${install_modules}" -eq 1 ]]; then
	if [[ -d modules-staging/lib/modules ]]; then
		cp -arv modules-staging/lib/modules/. /lib/modules/
	elif [[ -d lib/modules ]]; then
		cp -arv lib/modules/. /lib/modules/
	else
		echo "no staged modules found" >&2
		exit 1
	fi
else
	echo "Skipping host module install; pass --modules if modules changed."
fi
