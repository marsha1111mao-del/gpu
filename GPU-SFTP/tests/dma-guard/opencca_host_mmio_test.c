#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef uint64_t u64;

#include <hyp/exception.h>
#include <nvhe/opencca_mmio.h>

static void check_range(u64 address, u64 original_start, u64 original_end)
{
	u64 start = original_start, end = original_end;
	bool allowed = opencca_host_mmio_clip_range(address, &start, &end);
	bool protected = address >= 0xfb000000ULL && address < 0xfb200000ULL;
	bool contained = address >= original_start && address < original_end;

	assert(allowed == (contained && !protected));
	if (!allowed)
		return;
	assert(start >= original_start && end <= original_end);
	assert(start <= address && address < end);
	assert(opencca_host_mmio_range_allowed(start, end));
	if (address < 0xfb000000ULL)
		assert(end <= 0xfb000000ULL);
	else
		assert(start >= 0xfb200000ULL);
}

static void check_pstate(unsigned long target, const unsigned long vectors[6])
{
	const unsigned long modes[] = {
		PSR_MODE_EL0t, PSR_MODE_EL1t, PSR_MODE_EL1h,
		PSR_MODE_EL2t, PSR_MODE_EL2h, PSR_MODE32_BIT
	};
	const unsigned long flags[] = {
		PSR_N_BIT, PSR_Z_BIT, PSR_C_BIT, PSR_V_BIT, PSR_DIT_BIT,
		PSR_PAN_BIT, PSR_UAO_BIT, PSR_SSBS_BIT, PSR_TCO_BIT,
		1UL << 20, 1UL << 21, PSR_BTYPE_MASK
	};
	const unsigned long inherited = PSR_N_BIT | PSR_Z_BIT | PSR_C_BIT |
		PSR_V_BIT | PSR_DIT_BIT | PSR_PAN_BIT;
	const unsigned long fixed = PSR_D_BIT | PSR_A_BIT | PSR_I_BIT | PSR_F_BIT;

	for (unsigned int mode = 0; mode < 6; mode++) {
		assert(exception64_vector(modes[mode], target) == vectors[mode]);
		for (unsigned int bits = 0; bits < (1U << 12); bits++) {
			unsigned long old = modes[mode];

			for (unsigned int flag = 0; flag < 12; flag++)
				if (bits & (1U << flag))
					old |= flags[flag];
			for (unsigned int policy = 0; policy < 8; policy++) {
				unsigned long sctlr = (policy & 1 ? SCTLR_EL1_SPAN : 0) |
					(policy & 2 ? SCTLR_ELx_DSSBS : 0);
				unsigned long expected = (old & inherited) | fixed | target;

				if (!(policy & 1))
					expected |= PSR_PAN_BIT;
				if (policy & 2)
					expected |= PSR_SSBS_BIT;
				if (policy & 4)
					expected |= PSR_TCO_BIT;
				assert(exception64_pstate(old, sctlr, target,
							 policy & 4) == expected);
			}
		}
	}
}

int main(void)
{
	const unsigned long el1_vectors[] = { 0x400, 0, 0x200, 0x400, 0x400, 0x600 };
	const unsigned long el2_vectors[] = { 0x400, 0x400, 0x400, 0, 0x200, 0x600 };
	const u64 boundaries[] = {
		0, 1, 0x10f000, 0xfaffffff, 0xfb000000, 0xfb000028,
		0xfb001000, 0xfb1fffff, 0xfb200000, 0xfb200001,
		0xfc000000, UINT64_MAX - 1, UINT64_MAX
	};
	unsigned int combinations = 0;

	for (unsigned int start = 0; start < 13; start++)
		for (unsigned int end = 0; end < 13; end++) {
			bool valid = boundaries[start] < boundaries[end];
			bool overlap = boundaries[start] < 0xfb200000ULL &&
				boundaries[end] > 0xfb000000ULL;

			assert(opencca_host_mmio_range_allowed(boundaries[start],
				boundaries[end]) == (valid && !overlap));
			for (unsigned int address = 0; address < 13; address++) {
				check_range(boundaries[address], boundaries[start], boundaries[end]);
				combinations++;
			}
		}
	for (u64 address = 0xfa000000; address < 0xfc000000; address += 4096) {
		check_range(address, 0, UINT64_MAX);
		check_range(address, address, address + 4096);
		combinations += 2;
	}
	check_pstate(PSR_MODE_EL1h, el1_vectors);
	check_pstate(PSR_MODE_EL2h, el2_vectors);
	printf("opencca-host-mmio: PASS ranges=%u pstate=393216\n", combinations);
	return 0;
}
