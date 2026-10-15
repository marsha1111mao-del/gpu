#!/usr/bin/env python3
"""Check a dmesg capture from one pmthor_pfn_lifetime invocation."""
import re
import sys
from pathlib import Path


def check(text):
    for order, vm_refs in (("vm-first", 0), ("device-first", 1)):
        def marker(phase):
            return f"PMTHOR_PFN_TEST order={order} phase={phase}"

        start = text.rindex(marker("begin"))
        end = text.index(marker("pass"), start)
        section = text[start:end]
        closed = list(re.finditer(
            rf"GPU session closed pages=1 vm_refs={vm_refs}\b", section))
        released = list(re.finditer(
            r"released GPU page references=1\b", section))
        assert len(closed) == 1, f"{order}: incorrect unique-page/VM count"
        assert len(released) == 1, f"{order}: expected exactly one page release"
        assert "GPU reset failed" not in section, f"{order}: reset failed"
        assert "hardware quiesced for session release" in section
        if order == "vm-first":
            assert section.index(marker("vm-closed")) < closed[0].start()
            assert closed[0].start() < released[0].start()
            assert released[0].start() < section.index(marker("device-closed"))
        else:
            assert closed[0].start() < section.index(
                marker("device-closed-vm-alive"))
            assert section.index(marker("reopen-blocked")) < section.index(
                "hardware quiesced for last VM teardown")
            assert section.index("hardware quiesced for last VM teardown") < \
                released[0].start()
            assert section.index(marker("device-closed-vm-alive")) < \
                released[0].start() < section.index(marker("vm-closed"))
    print("PMTHOR_PFN_LIFETIME_RESULT=PASS orders=2 unique_pages_per_order=1")


if __name__ == "__main__":
    check(Path(sys.argv[1]).read_text())
