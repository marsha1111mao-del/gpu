#!/usr/bin/env python3
"""Exercise FIT/ELF packaging checks with real dtc/fdtget, without hardware."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('rmm_fit', Path(__file__).with_name('check-rmm-firmware.py'))
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def elf():
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HHIQQQ', header, 16, 3, 183, 1, 0, 64, 0)
    struct.pack_into('<HHH', header, 52, 64, 56, 2)
    return bytes(header) + struct.pack('<IIQQQQQQ', 1, 5, 176, 0, 0, 4, 4096, 4096) + struct.pack('<IIQQQQQQ', 1, 6, 180, 8192, 8192, 4, 8192, 4096) + b'CODEDATA'


def byte_array(value):
    return '[' + value.hex(' ') + ']'


def source(mode='inline'):
    nodes = []
    for i, payload in enumerate((b'CODE', b'DATA')):
        if mode == 'inline':
            data = 'data = ' + byte_array(payload) + ';'
        elif mode == 'offset':
            data = f'data-offset = <{i * 4}>; data-size = <4>;'
        else:
            data = f'data-position = <{4096 + i * 4}>; data-size = <4>;'
        nodes.append(f'''rmm-{i + 1} {{
            os = "rmm"; arch = "arm64"; type = "firmware"; compression = "none";
            load = <{0x201000 + i * 8192}>;
            {('entry = <0x201000>;' if not i else '')}
            {data}
            hash {{ algo = "sha256"; value = {byte_array(hashlib.sha256(payload).digest())}; }};
        }};''')
    return '''/dts-v1/; / {
        images { atf { os = "arm-trusted-firmware"; }; fdt { type = "flat_dt"; };
        ''' + '\n'.join(nodes) + ''' };
        configurations { default = "config-1";
            config-1 { firmware = "atf"; loadables = "rmm-1", "rmm-2"; };
        };
    };'''


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rmm-fit-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rmm, self.fit = self.root / 'rmm.elf', self.root / 'u-boot.itb'
        self.rmm.write_bytes(elf())

    def build(self, text=None, mode='inline'):
        path = self.root / 'fit.dts'
        path.write_text(source(mode) if text is None else text)
        subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(self.fit), str(path)],
                       capture_output=True, check=True)
        if mode != 'inline':
            blob = self.fit.read_bytes()
            length = (len(blob) + 3) & ~3 if mode == 'offset' else 4096
            assert len(blob) <= length
            self.fit.write_bytes(blob.ljust(length, b'\0') + b'CODEDATA')

    def rejected(self, text, expected):
        self.build(text)
        with self.assertRaisesRegex(ValueError, expected):
            CHECK.verify(self.fit, self.rmm)

    def test_valid_inline(self):
        self.build()
        result = CHECK.verify(self.fit, self.rmm)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(len(result['segments']), 2)
        self.assertFalse(result['boot_verified'])

    def test_valid_external_offset(self):
        self.build(mode='offset')
        self.assertEqual(CHECK.verify(self.fit, self.rmm)['status'], 'PASS')

    def test_valid_external_position(self):
        self.build(mode='position')
        self.assertEqual(CHECK.verify(self.fit, self.rmm)['status'], 'PASS')

    def test_stale_fit_for_new_elf(self):
        self.build()
        self.rmm.write_bytes(elf()[:-4] + b'NEW!')
        with self.assertRaisesRegex(ValueError, 'differs from supplied ELF'):
            CHECK.verify(self.fit, self.rmm)

    def test_wrong_load(self):
        self.rejected(source().replace('load = <2101248>', 'load = <2105344>'), 'segment differs')

    def test_wrong_entry(self):
        self.rejected(source().replace('entry = <0x201000>', 'entry = <0x202000>'), 'entry differs')

    def test_missing_entry(self):
        self.rejected(source().replace('entry = <0x201000>;', ''), 'exactly one entry')

    def test_missing_segment(self):
        self.rejected(source().replace('os = "rmm";', 'os = "other";', 1), 'all RMM segments')

    def test_wrong_hash(self):
        self.rejected(source().replace(byte_array(hashlib.sha256(b'CODE').digest()), byte_array(bytes(32))), 'hash differs')

    def test_compression(self):
        self.rejected(source().replace('compression = "none"', 'compression = "gzip"', 1), 'unsupported')

    def test_config_omits_segment(self):
        self.rejected(source().replace('"rmm-1", "rmm-2"', '"rmm-1"'), 'omits an RMM segment')

    def test_alternative_config_omits_segment(self):
        self.rejected(source().replace('default = "config-1";', 'default = "config-1"; config-2 { firmware = "atf"; loadables = "rmm-1"; };'), 'omits an RMM segment')

    def test_unknown_reference(self):
        self.rejected(source().replace('firmware = "atf"', 'firmware = "missing"'), 'image references')

    def test_duplicate_reference(self):
        self.rejected(source().replace('"rmm-1", "rmm-2"', '"rmm-1", "rmm-2", "rmm-1"'), 'image references')

    def test_external_payload_truncated(self):
        self.build(mode='offset')
        self.fit.write_bytes(self.fit.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, 'truncated or invalid'):
            CHECK.verify(self.fit, self.rmm)

    def test_ambiguous_data(self):
        self.rejected(source().replace('data = [43 4f 44 45];', 'data = [43 4f 44 45]; data-offset = <0>;'), 'ambiguous')

    def test_non_aarch64_elf(self):
        self.build()
        data = bytearray(elf())
        struct.pack_into('<H', data, 18, 62)
        self.rmm.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'AArch64'):
            CHECK.verify(self.fit, self.rmm)

    def test_overlapping_elf_segments(self):
        data = bytearray(elf())
        struct.pack_into('<Q', data, 64 + 56 + 24, 0)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            CHECK.elf_segments(bytes(data), 0x201000)

    def test_cli_failure_is_nonzero(self):
        self.build()
        self.rmm.write_bytes(elf()[:-4] + b'NEW!')
        result = subprocess.run(['python3', str(SPEC.origin), '--fit', str(self.fit), '--rmm', str(self.rmm)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('RMM_FIT=FAIL', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_deploy_rejects_stale_fit_before_hardware(self):
        self.build()
        self.rmm.write_bytes(elf()[:-4] + b'NEW!')
        # Run the real deployment entry in a temporary repository. Layout is
        # a stub here; the RMM/FIT check, subprocess and failure path are real.
        check_dir, run_dir = self.root / 'scripts/check', self.root / 'scripts/run'
        maintenance = self.root / 'scripts/maintenance'
        for path in (check_dir, run_dir, maintenance, self.root / 'opencca/scripts'):
            path.mkdir(parents=True)
        shutil.copy2(SPEC.origin, check_dir / 'check-rmm-firmware.py')
        deploy = Path(__file__).resolve().parents[1] / 'run/deploy-rmm-firmware.py'
        shutil.copy2(deploy, run_dir / deploy.name)
        (self.root / 'opencca/scripts/check-firmware-layout.py').write_text('print("{}")\n')
        marker = self.root / 'unexpected-hardware-access'
        (maintenance / 'lab-resources.py').write_text(
            'from pathlib import Path\n'
            'def audit(role):\n'
            f' Path({str(marker)!r}).touch()\n'
            ' raise AssertionError("hardware must not be reached")\n')
        firmware = self.root / 'firmware'
        firmware.mkdir()
        shutil.copy2(self.rmm, firmware / 'tf-rmm.elf')
        shutil.copy2(self.fit, firmware / 'u-boot.itb')
        env = os.environ.copy()
        env.update(RUN_ID='stale-fit-test', GPU_LAB_ALLOW_RK_REBOOT='1')
        result = subprocess.run(['python3', str(run_dir / deploy.name), '--firmware', str(firmware),
                                 '--run-id', 'stale-fit-test'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('RMM_FIT=FAIL', result.stderr)
        report = json.loads((self.root / 'build/firmware-runs/stale-fit-test/summary.json').read_text())
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['images'], {})
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
