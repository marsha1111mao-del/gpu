#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

fail=0

check_contains() {
	local file="$1"
	local pattern="$2"
	local label="$3"

	if grep -qE "$pattern" "${ROOT_DIR}/${file}"; then
		printf 'PASS %-34s %s\n' "${label}" "${file}"
	else
		printf 'FAIL %-34s %s\n' "${label}" "${file}"
		fail=1
	fi
}

check_absent() {
	local pattern="$1"
	local label="$2"

	if rg -q "$pattern" "${ROOT_DIR}/Linux-Host-GPU"; then
		printf 'FAIL %-34s Linux-Host-GPU still contains %s\n' "${label}" "${pattern}"
		fail=1
	else
		printf 'PASS %-34s Linux-Host-GPU\n' "${label}"
	fi
}

printf 'OpenCCA GPT/GPC design denial check\n'
printf 'root=%s\n\n' "${ROOT_DIR}"

check_contains \
	"opencca/tf-rmm/lib/rmm_el3_ifc/include/rmm_el3_ifc.h" \
	"SMC_RMM_GTSI_DELEGATE" \
	"RMM calls EL3 GTSI delegate"

check_contains \
	"opencca/trusted-firmware-a/services/std_svc/rmmd/rmmd_main.c" \
	"RMM_GTSI_DELEGATE.*gpt_delegate_pas|gpt_delegate_pas\\(x1, PAGE_SIZE_4KB, SMC_FROM_REALM\\)" \
	"EL3 delegates through GPT library"

check_contains \
	"opencca/trusted-firmware-a/lib/gpt_rme/gpt_rme.c" \
	"target_pas.*GPT_GPI_REALM|GPT_GPI_REALM" \
	"GPT model has Realm GPI"

check_contains \
	"opencca/tf-rmm/tools/cbmc/testbenches/tb_rmi_granule_delegate.c" \
	"gpt == GPT_REALM" \
	"RMM model expects GPT_REALM"

check_contains \
	"opencca/trusted-firmware-a/opencca/include/opencca.h" \
	"read_gpccr_el3_spoofed|read_gptbr_el3_spoofed" \
	"RK3588 OpenCCA spoofs GPC regs"

check_contains \
	"opencca/trusted-firmware-a/lib/xlat_tables_v2/aarch64/xlat_tables_arch.c" \
	"treat Realm PAS as NS|MT_NS != MT_REALM" \
	"RK3588 OpenCCA folds Realm PAS"

check_absent "realm_delegated" "No Host Linux PFN guard"

printf '\n'
if [[ "${fail}" -eq 0 ]]; then
	printf 'DESIGN_GPT_HOST_DENIAL_CHECK=PASS\n'
	printf 'NOTE=The CCA/GPT design path transitions delegated granules to Realm GPI, but RK3588/OpenCCA spoofs GPC registers and folds Realm PAS to NS, so this is a design/model check rather than hardware denial.\n'
else
	printf 'DESIGN_GPT_HOST_DENIAL_CHECK=FAIL\n'
fi

exit "${fail}"
