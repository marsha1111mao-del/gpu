#!/usr/bin/env python3
"""Check the lab wrapper's actual explicit recovery-state contract without SSH."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'scripts/maintenance/lab-run.py'
tree = ast.parse(path.read_text())
node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name == 'expected_postflight')
namespace = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
expected = namespace['expected_postflight']


class PostflightTests(unittest.TestCase):
    def setUp(self):
        self.before = {'online_cpus': '0-3', 'gpu_driver': '/sys/bus/platform/drivers/panthor'}

    def test_default_preserves_both_observed_fields(self):
        self.assertEqual(expected(self.before), self.before)

    def test_recovery_explicitly_requires_baseline(self):
        self.assertEqual(expected(self.before, '0-1', 'pmthor'),
                         {'online_cpus': '0-1', 'gpu_driver': '/sys/bus/platform/drivers/pmthor'})

    def test_cpu_override_keeps_original_driver_requirement(self):
        self.assertEqual(expected(self.before, '0-1')['gpu_driver'], self.before['gpu_driver'])

    def test_driver_override_keeps_original_cpu_requirement(self):
        self.assertEqual(expected(self.before, gpu_driver='pmthor')['online_cpus'], '0-3')

    def test_snapshot_remains_immutable(self):
        copy = dict(self.before)
        expected(self.before, '0-1', 'pmthor')
        self.assertEqual(self.before, copy)

    def test_offline_recovery_does_not_invent_unobserved_fields(self):
        self.assertEqual(expected({'available': False}), {})
        self.assertEqual(expected({'available': False}, '0-1', 'pmthor'),
                         {'online_cpus': '0-1', 'gpu_driver': '/sys/bus/platform/drivers/pmthor'})


if __name__ == '__main__':
    unittest.main()
