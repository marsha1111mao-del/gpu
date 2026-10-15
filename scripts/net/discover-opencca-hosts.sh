#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

PI_USER=${PI_USER:-mzh}
PI_PASS=${PI_PASS:-root}
RK_USER=${RK_USER:-root}
RK_PASS=${RK_PASS:-root}
SSH_PORT=${SSH_PORT:-22}
CONNECT_TIMEOUT=${CONNECT_TIMEOUT:-2}
JOBS=${JOBS:-64}
OLD_PI_IP=${OLD_PI_IP:-192.168.31.52}
OLD_RK_IP=${OLD_RK_IP:-192.168.31.18}
PREFERRED_PI_IP=${PREFERRED_PI_IP:-192.168.31.189}
SCAN_CIDRS=${SCAN_CIDRS:-}
UPDATE_DOCS=0

usage() {
	cat <<EOF
Usage: $(basename "$0") [options]

Discover the OpenCCA Raspberry Pi flasher and RK3588 board on the LAN.

Options:
  --cidr CIDR       Scan CIDR, for example 192.168.31.0/24. Can be repeated.
  --pi-user USER    Raspberry Pi SSH user. Default: ${PI_USER}
  --pi-pass PASS    Raspberry Pi SSH password. Default: ${PI_PASS}
  --rk-user USER    RK3588 SSH user. Default: ${RK_USER}
  --rk-pass PASS    RK3588 SSH password. Default: ${RK_PASS}
  --preferred-pi-ip Prefer this Raspberry Pi address when multiple addresses answer
  --update-docs     Replace the old documented IPs after both hosts are found.
  -h, --help        Show this help.

Environment:
  SCAN_CIDRS        Space-separated CIDRs. Used when --cidr is not supplied.
  JOBS              Parallel TCP probes. Default: ${JOBS}
  CONNECT_TIMEOUT   Per-connection SSH timeout in seconds. Default: ${CONNECT_TIMEOUT}
  OLD_PI_IP         Old IP used in mzh@IP references when --update-docs is used.
  OLD_RK_IP         IP to replace for RK when --update-docs is used. Default: ${OLD_RK_IP}
  PREFERRED_PI_IP   Pi address tried first. Default: ${PREFERRED_PI_IP}

Examples:
  scripts/net/discover-opencca-hosts.sh --cidr 192.168.31.0/24
  scripts/net/discover-opencca-hosts.sh --cidr 192.168.31.0/24 --update-docs
EOF
}

log() {
	printf '[discover-opencca] %s\n' "$*"
}

die() {
	printf '[discover-opencca] error: %s\n' "$*" >&2
	exit 1
}

need_cmd() {
	local cmd
	for cmd in "$@"; do
		command -v "$cmd" >/dev/null 2>&1 || die "missing required command: $cmd"
	done
}

while (($#)); do
	case "$1" in
		--cidr)
			[[ $# -ge 2 ]] || die "--cidr needs an argument"
			SCAN_CIDRS="${SCAN_CIDRS:+$SCAN_CIDRS }$2"
			shift 2
			;;
		--pi-user)
			[[ $# -ge 2 ]] || die "--pi-user needs an argument"
			PI_USER=$2
			shift 2
			;;
		--pi-pass)
			[[ $# -ge 2 ]] || die "--pi-pass needs an argument"
			PI_PASS=$2
			shift 2
			;;
		--rk-user)
			[[ $# -ge 2 ]] || die "--rk-user needs an argument"
			RK_USER=$2
			shift 2
			;;
		--rk-pass)
			[[ $# -ge 2 ]] || die "--rk-pass needs an argument"
			RK_PASS=$2
			shift 2
			;;
		--preferred-pi-ip)
			[[ $# -ge 2 ]] || die "--preferred-pi-ip needs an argument"
			PREFERRED_PI_IP=$2
			shift 2
			;;
		--update-docs)
			UPDATE_DOCS=1
			shift
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			die "unknown argument: $1"
			;;
	esac
done

need_cmd ssh sshpass timeout sed awk sort

if [[ -z "$SCAN_CIDRS" ]]; then
	if command -v ip >/dev/null 2>&1; then
		SCAN_CIDRS=$(ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | tr '\n' ' ' || true)
	fi
fi
if [[ -z "$SCAN_CIDRS" ]]; then
	SCAN_CIDRS="192.168.31.0/24"
	log "no local CIDR discovered; falling back to ${SCAN_CIDRS}"
fi

cidr_hosts() {
	local cidr=$1
	local base prefix a b c d host
	base=${cidr%/*}
	prefix=${cidr#*/}
	IFS=. read -r a b c d <<<"$base"
	case "$prefix" in
		24)
			for host in $(seq 1 254); do
				printf '%s.%s.%s.%s\n' "$a" "$b" "$c" "$host"
			done
			;;
		*)
			die "unsupported CIDR ${cidr}; pass a /24 CIDR"
			;;
	esac
}

tcp22_open() {
	local ip=$1
	timeout "$CONNECT_TIMEOUT" bash -c ":</dev/tcp/${ip}/${SSH_PORT}" >/dev/null 2>&1
}

ssh_probe() {
	local user=$1 pass=$2 ip=$3 cmd=$4
	sshpass -p "$pass" ssh \
		-p "$SSH_PORT" \
		-o ConnectTimeout="$CONNECT_TIMEOUT" \
		-o ConnectionAttempts=1 \
		-o StrictHostKeyChecking=accept-new \
		-o UserKnownHostsFile=/tmp/opencca_discover_known_hosts \
		-o PreferredAuthentications=password \
		-o PubkeyAuthentication=no \
		-o NumberOfPasswordPrompts=1 \
		"${user}@${ip}" "$cmd" </dev/null 2>/dev/null
}

is_pi() {
	local ip=$1
	ssh_probe "$PI_USER" "$PI_PASS" "$ip" \
		'printf "hostname=%s\n" "$(hostname)"; test -x /home/mzh/opencca-flash/flash.sh && echo flash.sh=ok; uname -m; ls -l /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null || true' \
		| awk 'BEGIN{ok=1} /flash.sh=ok/{ok=0} END{exit ok}'
}

is_rk() {
	local ip=$1
	ssh_probe "$RK_USER" "$RK_PASS" "$ip" \
		'printf "hostname=%s\n" "$(hostname)"; uname -r; findmnt -no SOURCE,TARGET,FSTYPE /; test -e /dev/pmthor && echo pmthor=ok; test -e /sys/bus/platform/devices/fb000000.gpu && echo gpu=ok; basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)" 2>/dev/null || true' \
		| awk 'BEGIN{ok=1} /pmthor=ok|gpu=ok|opencca-pmthor/{ok=0} END{exit ok}'
}

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

log "scanning CIDR(s): ${SCAN_CIDRS}"
for cidr in $SCAN_CIDRS; do
	cidr_hosts "$cidr"
done | sort -u >"$tmpdir/hosts"

log "probing TCP/${SSH_PORT}; parallel jobs=${JOBS}"
xargs -r -P "$JOBS" -I{} bash -c '
	ip=$1
	timeout "$2" bash -c ":</dev/tcp/${ip}/'"$SSH_PORT"'" >/dev/null 2>&1 && printf "%s\n" "$ip"
	exit 0
' _ {} "$CONNECT_TIMEOUT" <"$tmpdir/hosts" | sort -V >"$tmpdir/ssh-open"

# Prefer the wired Pi address when both wired and wireless addresses are live.
# Keep the other SSH hosts in numeric order so discovery remains deterministic.
if [[ -n "$PREFERRED_PI_IP" ]] && grep -qx "$PREFERRED_PI_IP" "$tmpdir/ssh-open"; then
	grep -vx "$PREFERRED_PI_IP" "$tmpdir/ssh-open" >"$tmpdir/ssh-open-other"
	printf '%s\n' "$PREFERRED_PI_IP" >"$tmpdir/ssh-open"
	cat "$tmpdir/ssh-open-other" >>"$tmpdir/ssh-open"
fi

if [[ ! -s "$tmpdir/ssh-open" ]]; then
	die "no SSH hosts found in: ${SCAN_CIDRS}"
fi

log "SSH hosts:"
sed 's/^/  /' "$tmpdir/ssh-open"

pi_ip=
rk_ip=
while IFS= read -r ip; do
	if [[ -z "$pi_ip" ]] && is_pi "$ip"; then
		pi_ip=$ip
		log "identified Raspberry Pi: ${PI_USER}@${pi_ip}"
		ssh_probe "$PI_USER" "$PI_PASS" "$pi_ip" \
			'hostname; test -x /home/mzh/opencca-flash/flash.sh && echo flash.sh=ok; ls -l /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null || true' \
			| sed 's/^/  pi> /'
	fi
	if [[ -z "$rk_ip" ]] && is_rk "$ip"; then
		rk_ip=$ip
		log "identified RK3588: ${RK_USER}@${rk_ip}"
		ssh_probe "$RK_USER" "$RK_PASS" "$rk_ip" \
			'hostname; uname -r; findmnt -no SOURCE,TARGET,FSTYPE /; basename "$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)" 2>/dev/null || true; ls -l /dev/pmthor /dev/dri/card0 2>/dev/null || true' \
			| sed 's/^/  rk> /'
	fi
done <"$tmpdir/ssh-open"

[[ -n "$pi_ip" ]] || log "Raspberry Pi not identified"
[[ -n "$rk_ip" ]] || log "RK3588 not identified"

cat <<EOF

Detected environment:
  export PI_HOST=${PI_USER}@${pi_ip:-<not-found>}
  export PI_PASSWORD='${PI_PASS}'
  export RK_HOST=${RK_USER}@${rk_ip:-<not-found>}
  export RK_PASSWORD='${RK_PASS}'
  export OPENCCA_RPI_HOST=${PI_USER}@${pi_ip:-<not-found>}
  export OPENCCA_RPI_PASSWORD='${PI_PASS}'
  export OPENCCA_RPI_SUDO_PASSWORD='${PI_PASS}'
  export OPENCCA_RK_HOST=${RK_USER}@${rk_ip:-<not-found>}
  export OPENCCA_RK_PASSWORD='${RK_PASS}'
  export REMOTE_HOST=${rk_ip:-<not-found>}
  export REMOTE_PASS='${RK_PASS}'
EOF

if [[ "$UPDATE_DOCS" -eq 0 ]]; then
	exit 0
fi

[[ -n "$pi_ip" ]] || die "--update-docs requested but Raspberry Pi was not identified"
[[ -n "$rk_ip" ]] || die "--update-docs requested but RK3588 was not identified"

log "updating documented/default IPs: Pi ${OLD_PI_IP} -> ${pi_ip}, RK ${OLD_RK_IP} -> ${rk_ip}"
files=(
	"opencca/docs/SD_CARD_FLASH_RUNBOOK.md"
	"docs/shared/PANTHOR_SHARED_VIRTUALIZATION_WORKLOG.md"
	"docs/start/RASPBERRY_PI_FLASH_RUNBOOK.md"
	"scripts/run/run-host-vs-passthrough-gles-perf.sh"
	"scripts/run/run-vmshm-2client-e2e.sh"
	"scripts/run/run-vmshm-e2e.sh"
	"scripts/deploy/deploy-host-kernel-and-test.sh"
	"opencca/scripts/lib/opencca_paths.sh"
)

[[ -n "$OLD_PI_IP" ]] || die "--update-docs needs a non-empty OLD_PI_IP"

for rel in "${files[@]}"; do
	path="${ROOT_DIR}/${rel}"
	[[ -f "$path" ]] || continue
	sed -i \
		-e "s/${PI_USER}@${OLD_PI_IP//./\\.}/${PI_USER}@${pi_ip}/g" \
		-e "s/${OLD_RK_IP//./\\.}/${rk_ip}/g" \
		"$path"
	printf '  updated %s\n' "$rel"
done

log "done"
