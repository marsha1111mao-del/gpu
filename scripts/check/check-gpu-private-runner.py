#!/usr/bin/env python3
"""Check actual private runner functions/CLI and initrd packaging offline.

Realm calls, serial processes and workloads are doubles. This does not test
Linux/RSI, GPU execution, memory isolation or hardware resource reclamation.
"""
import ast
from contextlib import redirect_stderr
import hashlib
import io
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'GPU-SFTP/tests/realm-xshm/run-realms.py'
WRAPPER = ROOT / 'scripts/run/run-realm-xshm.py'
PACKER = ROOT / 'scripts/build/build-realm-xshm-initrd.py'


def functions(path, names):
    tree = ast.parse(path.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    namespace = {'hashlib': hashlib, 'stat': stat, 'struct': struct}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def cli(path, arguments):
    # Execute the real parser/validation only, stopping before environment,
    # filesystem, SSH, lab lease or process mutations.
    tree = ast.parse(path.read_text())
    selected = []
    stop = 'vm_count' if path == RUNNER else 'run_id'
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                                                target.id == stop for target in node.targets):
            break
        selected.append(node)
    else:
        raise AssertionError('parser boundary missing')
    namespace = {'__file__': str(path)}
    with patch.object(sys, 'argv', [str(path)] + arguments), redirect_stderr(io.StringIO()):
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['a']


def environment(clients=2, benchmark=False, profiles=None):
    namespace = functions(RUNNER, ('realm_memory', 'gpu_mode_boot_args',
                                   'bootstrap_private_gpu', 'test_private_gpu'))
    args = SimpleNamespace(private_gpu=True, clients=clients, memory_pages=2049,
                           profiles=profiles, benchmark_only=benchmark,
                           suite=bool(profiles), compute_rootfs=None, glmark_rootfs=None)
    log, channels, irq_reads = [], [], {}
    result = {'private_gpu': {'bootstrap': 'NOT_RUN', 'drm_probes': {},
                              'gpu_completion_eventfd': 'NOT_RUN'}}
    processes = [SimpleNamespace(stdin=io.BytesIO()) for _ in range(clients + 1 if benchmark else 3)]
    namespace.update(a=args, vm_count=len(processes), result=result, processes=processes,
                     buffers={}, bindings=[], log=log, fail=None, score=1100)

    def call(vm, command, expected=0):
        log.append(('call', vm, command, expected))
        if command == 'register':
            return [1, 10 + vm, 16, 0]
        if command == 'irq-bind':
            return [127, 0, 0, 0]
        if command == 'irq-stats':
            irq_reads[vm] = irq_reads.get(vm, 0) + 1
            return [irq_reads[vm], 0, 0, 0]
        if command.startswith('offer '):
            channels.append(100 + vm + len(channels))
            return [channels[-1], 0, 0, 0]
        return [1000 + vm, 0, 0, 0]

    def text(vm, command, markers, timeout=120, sent=False):
        log.append(('text', vm, command, tuple(markers), sent))
        if namespace['fail'] == (vm, command):
            raise RuntimeError('injected serial/command failure')
        return '\n'.join(markers) + '\nalu_iters=64'

    def memory(vm, command, expected):
        log.append(('memory', vm, command, expected))
        return 200 + len(channels)

    def glmark(vm):
        log.append(('glmark', vm))
        result['glmark'] = {'score': namespace['score']}

    def concurrent_glmark():
        log.append(('concurrent_glmark',))
        result['concurrent_glmark'] = [{'score': namespace['score']} for _ in range(clients)]

    namespace.update(call=call, text_command=text, memory_operation=memory,
                     save=lambda: None, glmark=glmark, run_concurrent_glmark=concurrent_glmark,
                     run_concurrent_ml=lambda: log.append(('concurrent_ml',)),
                     ML_PROFILES=('ml-gemm', 'ncnn-resnet50'))
    return namespace


class RunnerTests(unittest.TestCase):
    def test_actual_c_driver_mode_check(self):
        source = (ROOT / 'GPU-SFTP/tests/realm-xshm/realm-gpu-private.c').read_text()
        start = source.index('static int private_mode(')
        actual = source[start:source.index('\n}', start) + 2]
        harness = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
static const char *value, *expected;
static FILE *mode_file(const char *path, const char *mode)
{
    assert(!strcmp(path, expected) && !strcmp(mode, "r"));
    if (!value) { errno = ENOENT; return NULL; }
    return fmemopen((void *)value, strlen(value), "r");
}
#define fopen mode_file
''' + actual + r'''
#undef fopen
int main(void)
{
    assert(private_mode("outsider") == 2);
    expected = "/sys/module/panthor_client/parameters/rmm_private_data";
    value = "Y\n"; assert(private_mode("client") == 0);
    value = "1\n"; assert(private_mode("client") == 0);
    value = "N\n"; assert(private_mode("client") == 1);
    value = ""; assert(private_mode("client") == 1);
    value = NULL; assert(private_mode("client") == 1);
    expected = "/sys/module/panthor/parameters/rmm_service";
    value = "Y\n"; assert(private_mode("proxy") == 0);
    value = "0\n"; assert(private_mode("proxy") == 1);
    puts("GPU_PRIVATE_MODE_SOURCE=PASS cases=8 FILE_IO_DOUBLES_ONLY");
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='gpu-private-mode-') as directory:
            path = Path(directory)
            (path / 'mode.c').write_text(harness)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            str(path / 'mode.c'), '-o', str(path / 'mode')], check=True,
                           capture_output=True)
            executed = subprocess.run([str(path / 'mode')], check=True, capture_output=True, text=True)
            self.assertIn('GPU_PRIVATE_MODE_SOURCE=PASS cases=8', executed.stdout)

    def test_private_boot_parameters(self):
        env = environment()
        self.assertEqual(env['gpu_mode_boot_args'](0), ' panthor.rmm_service=1')
        self.assertEqual(env['gpu_mode_boot_args'](1), ' panthor_client.rmm_private_data=1')
        self.assertEqual(env['gpu_mode_boot_args'](2), ' panthor_client.rmm_private_data=1')

    def test_shared_boot_parameters_unchanged(self):
        env = environment()
        env['a'].private_gpu = False
        self.assertEqual(env['gpu_mode_boot_args'](0), '')
        self.assertEqual(env['gpu_mode_boot_args'](1), '')

    def test_private_memory_is_not_cma_data_budget(self):
        env = environment()
        proxy, client = env['realm_memory'](0), env['realm_memory'](1)
        self.assertEqual(proxy, (308, 36))
        self.assertEqual(client, (476, 28))
        self.assertEqual(client[0] - client[1], 448)

    def test_private_outsider_and_large_model_memory(self):
        env = environment(clients=1)
        self.assertEqual(env['realm_memory'](2), (256, 16))
        env['a'].profiles = ['ncnn-resnet50']
        self.assertEqual(env['realm_memory'](1), (604, 28))

    def test_private_memory_meets_vmm_and_cma_alignment(self):
        env = environment()
        for clients in (1, 2, 3, 4):
            env['a'].clients = clients
            # Includes partial MiB control pools and maximum accepted pages.
            for pages in (1025, 2048, 2049, 2305, 65536):
                env['a'].memory_pages = pages
                for profiles in (None, ['glmark-720'], ['ncnn-resnet50']):
                    env['a'].profiles = profiles
                    for vm in range(clients + 2):
                        with self.subTest(clients=clients, pages=pages,
                                          profiles=profiles, vm=vm):
                            total, cma = env['realm_memory'](vm)
                            self.assertEqual(total % 2, 0)
                            self.assertEqual(cma % 4, 0)
                            if vm > clients:
                                self.assertEqual((total, cma), (256, 16))
                                continue
                            minimum = ((pages + 255) // 256) * (clients if vm == 0 else 1) + 16
                            self.assertGreaterEqual(cma, minimum)
                            self.assertLess(cma - minimum, 4)
                            ordinary = (208 + 32 * clients if vm == 0 else
                                        576 if profiles == ['ncnn-resnet50'] else 448)
                            self.assertGreaterEqual(total - cma, ordinary)

    def test_bootstrap_checks_all_roles_before_firmware(self):
        env = environment()
        env['bootstrap_private_gpu']()
        commands = [(item[1], item[2]) for item in env['log'] if item[0] == 'text']
        self.assertEqual(commands, [(0, 'gpu-private mode-check proxy'),
                                    (1, 'gpu-private mode-check client'),
                                    (2, 'gpu-private mode-check client'),
                                    (0, 'gpu-private service-bootstrap /mali_csffw.bin')])
        self.assertEqual(env['result']['private_gpu']['bootstrap'], 'CONFIGURED')

    def test_old_client_kernel_blocks_bootstrap(self):
        env = environment()
        env['fail'] = (1, 'gpu-private mode-check client')
        with self.assertRaises(RuntimeError):
            env['bootstrap_private_gpu']()
        self.assertFalse(any('service-bootstrap' in item[2] for item in env['log']))
        self.assertEqual(env['result']['private_gpu']['bootstrap'], 'NOT_RUN')

    def test_partial_bootstrap_is_not_retried_or_reset(self):
        env = environment()
        env['fail'] = (0, 'gpu-private service-bootstrap /mali_csffw.bin')
        with self.assertRaises(RuntimeError):
            env['bootstrap_private_gpu']()
        self.assertEqual(env['result']['private_gpu']['bootstrap'], 'ATTEMPTED')
        self.assertEqual(sum('service-bootstrap' in item[2] for item in env['log']), 1)
        self.assertFalse(any('reset' in item[2] for item in env['log']))

    def test_two_client_private_drm_and_compute_flow(self):
        env = environment()
        env['a'].compute_rootfs = Path('/fixture/rootfs')
        env['test_private_gpu']()
        private = env['result']['private_gpu']
        self.assertEqual(private['drm_probes'], {'1': 'PASS', '2': 'PASS'})
        self.assertEqual(env['result']['two_client_compute_check'], 'PASS')
        self.assertTrue(all(process.stdin.getvalue() == b'compute-eventfd\n' for process in env['processes'][1:]))
        self.assertEqual(private['gpu_completion_eventfd'], 'PASS')
        self.assertEqual(env['bindings'], [])
        self.assertEqual(private['control_transport_cleanup'], 'PASS')
        self.assertEqual(private['trusted_device_reclamation'], 'NOT_VERIFIED')
        denied = [item for item in env['log'] if item[0] == 'call' and item[2].startswith('mem-describe')]
        self.assertEqual(len(denied), 2)
        self.assertTrue(all(item[3] == 1 for item in denied))
        self.assertFalse(any(item[0] == 'text' and item[2].startswith('gpu-smoke') for item in env['log']))

    def test_gpu_completion_eventfd_failure_cannot_pass(self):
        for client in (1, 2):
            env = environment()
            env['a'].compute_rootfs = Path('/fixture/rootfs')
            env['fail'] = (client, 'compute-eventfd')
            with self.subTest(client=client), self.assertRaises(RuntimeError):
                env['test_private_gpu']()
            self.assertEqual(env['result']['private_gpu']['gpu_completion_eventfd'], 'ATTEMPTED')
            self.assertNotIn('two_client_compute_check', env['result'])

    def test_single_client_outsider_not_bound(self):
        env = environment(clients=1)
        env['test_private_gpu']()
        self.assertEqual(env['result']['private_gpu']['drm_probes'], {'1': 'PASS'})
        self.assertFalse(any(item[0] == 'call' and item[1] == 2 and
                             item[2].startswith('pool-bind') for item in env['log']))

    def test_private_probe_failure_cannot_fall_back(self):
        env = environment()
        env['fail'] = (1, 'gpu-private drm-selftest')
        with self.assertRaises(RuntimeError):
            env['test_private_gpu']()
        self.assertEqual(env['result']['private_gpu']['drm_probes'], {})
        self.assertEqual(len(env['bindings']), 4)  # Outer runner owns failure cleanup.
        self.assertFalse(any(item[0] == 'glmark' for item in env['log']))

    def test_benchmark_only_does_not_run_api_probes(self):
        env = environment(clients=1, benchmark=True, profiles=['glmark-720'])
        env['test_private_gpu']()
        self.assertEqual(env['result']['private_gpu']['drm_probes'], {})
        self.assertEqual(env['result']['private_gpu']['glmark_720_gate']['status'], 'PASS')
        self.assertEqual(env['result']['private_gpu']['gpu_completion_eventfd'], 'NOT_RUN')
        self.assertIn(('concurrent_glmark',), env['log'])

    def test_low_full_720p_score_is_failure(self):
        env = environment(clients=1, benchmark=True, profiles=['glmark-720'])
        env['score'] = 999
        with self.assertRaises(AssertionError):
            env['test_private_gpu']()
        self.assertEqual(env['result']['private_gpu']['glmark_720_gate']['status'], 'FAIL')

    def test_private_plain_glmark_and_explicit_ml(self):
        env = environment(clients=1, benchmark=True)
        env['test_private_gpu']()
        self.assertIn(('glmark', 1), env['log'])
        env = environment(clients=2, benchmark=True, profiles=['ml-gemm'])
        env['test_private_gpu']()
        self.assertIn(('concurrent_ml',), env['log'])
        self.assertNotIn('glmark_720_gate', env['result']['private_gpu'])

    def test_actual_runner_parser_accepts_private_control_pool(self):
        args = cli(RUNNER, ['--run-id', 'offline', '--private-gpu', '--gpu-flow', '--transport',
                            '--trusted-events', '--memory-pages', '2049', '--benchmark-only',
                            '--glmark-rootfs', '/fixture/rootfs', '--suite', '--profiles', 'glmark-720'])
        self.assertTrue(args.private_gpu)
        self.assertEqual(args.memory_pages, 2049)

    def test_actual_runner_parser_rejects_missing_trust_and_cookie_modes(self):
        base = ['--run-id', 'offline', '--private-gpu', '--gpu-flow', '--transport', '--memory-pages', '2049']
        for arguments in (base, base + ['--trusted-events', '--transfer-capture'],
                          base + ['--trusted-events', '--completion-trace']):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as error:
                cli(RUNNER, arguments)
            self.assertEqual(error.exception.code, 2)

    def test_private_full_glmark_allows_controlled_cpu_frequency(self):
        base = ['--run-id', 'offline', '--private-gpu', '--gpu-flow', '--transport',
                '--trusted-events', '--memory-pages', '2049', '--benchmark-only',
                '--performance', '--glmark-rootfs', '/fixture/rootfs', '--suite']
        for profile in ('glmark-720', 'glmark-1080'):
            args = cli(RUNNER, base + ['--profiles', profile, '--cpu-frequency-khz', '1800000'])
            self.assertEqual(args.cpu_frequency_khz, 1800000)
            self.assertFalse(args.compact_memory)
        for extra in (['--profiles', 'ml-gemm', '--cpu-frequency-khz', '1800000'],
                      ['--profiles', 'glmark-720', '--cpu-frequency-khz', '0'],
                      ['--profiles', 'glmark-720', '--cpu-frequency-khz', '-1'],
                      ['--profiles', 'glmark-720', '--telemetry'],
                      ['--profiles', 'glmark-720', '--client-cpu-layout', 'round-robin']):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as error:
                cli(RUNNER, base + extra)
            self.assertEqual(error.exception.code, 2)

    def test_wrapper_parser_accepts_private_full_720p(self):
        args = cli(WRAPPER, ['--images', '/fixture/images', '--workload', 'glmark', '--private-gpu',
                            '--benchmark-only', '--suite', '--profiles', 'glmark-720'])
        self.assertTrue(args.private_gpu)

    def test_wrapper_parser_rejects_event_and_shared_modes(self):
        base = ['--images', '/fixture/images', '--private-gpu']
        for extra in (['--workload', 'events'], ['--transfer-capture'], ['--gpu-fault-isolation']):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as error:
                cli(WRAPPER, base + extra)
            self.assertEqual(error.exception.code, 2)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='gpu-private-runner-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        elf = bytearray(b'\x7fELF\x02\x01' + bytes(26))
        struct.pack_into('<H', elf, 18, 183)
        (self.directory / 'init').write_bytes(elf + b'/realm-gpu-private\0compute-eventfd\0')
        (self.directory / 'realm-xshm').write_bytes(elf)
        (self.directory / 'realm-gpu-private').write_bytes(elf + b'mode-check\0')
        (self.directory / 'gles-compute-smoke').write_bytes(elf + b'--gpu-eventfd\0')
        self.archive = self.directory / 'initrd.cpio'
        self.command = [sys.executable, str(PACKER), '--tools-dir', str(self.directory),
                        '--gpu-private', str(self.directory / 'realm-gpu-private'),
                        '--output', str(self.archive)]
        self.firmware = ROOT / 'GPU-SFTP/panthor_fw/mali_csffw.bin'
        self.parse = functions(WRAPPER, ('private_initrd_inputs',))['private_initrd_inputs']

    def pack(self, firmware=True):
        command = self.command + (['--gpu-firmware', str(self.firmware)] if firmware else [])
        return subprocess.run(command, capture_output=True, text=True)

    def test_actual_packer_and_input_validator(self):
        self.assertEqual(self.pack().returncode, 0)
        entries = self.parse(self.archive)
        self.assertEqual(set(entries), {'init', 'realm-gpu-private', 'mali_csffw.bin'})
        self.assertEqual(entries['mali_csffw.bin']['sha256'], hashlib.sha256(self.firmware.read_bytes()).hexdigest())
        self.assertEqual(entries['mali_csffw.bin']['mode'], oct(stat.S_IFREG | 0o644))

    def test_private_workload_requires_scripts_before_upload(self):
        self.assertEqual(self.pack().returncode, 0)
        with self.assertRaisesRegex(ValueError, 'glmark.env'):
            self.parse(self.archive, 'compute')

    def test_full_glmark_packaging_does_not_require_ioctl_probe(self):
        self.command += ['--glmark-env', str(ROOT / 'GPU-SFTP/tests/realm-xshm/glmark.env'),
                         '--performance-suite', str(ROOT / 'GPU-SFTP/tests/realm-xshm/performance-suite.sh')]
        self.assertEqual(self.pack().returncode, 0)
        entries = self.parse(self.archive, 'glmark', ['glmark-720'])
        self.assertTrue({'glmark.env', 'gpu-smoke.sh', 'performance-suite.sh'} <= set(entries))
        self.assertNotIn('ioctl-perf', entries)

    def test_compute_packaging_requires_matched_gpu_fence_probe(self):
        self.command += ['--glmark-env', str(ROOT / 'GPU-SFTP/tests/realm-xshm/glmark.env')]
        self.assertEqual(self.pack().returncode, 0)
        with self.assertRaisesRegex(ValueError, 'gles-compute-smoke'):
            self.parse(self.archive, 'compute')
        self.command += ['--gles-compute', str(self.directory / 'gles-compute-smoke')]
        self.assertEqual(self.pack().returncode, 0)
        self.assertIn('gles-compute-smoke', self.parse(self.archive, 'compute'))

    def test_compute_packaging_rejects_stale_init_or_probe_and_wrong_arch(self):
        self.command += ['--glmark-env', str(ROOT / 'GPU-SFTP/tests/realm-xshm/glmark.env'),
                         '--gles-compute', str(self.directory / 'gles-compute-smoke')]
        for name, old, new, error in (
                ('init', b'compute-eventfd', b'compute-old', 'compute-eventfd command'),
                ('gles-compute-smoke', b'--gpu-eventfd', b'--old-probe', 'GPU eventfd mode'),
                ('gles-compute-smoke', b'\xb7\x00', b'\x3e\x00', 'AArch64')):
            path = self.directory / name
            original = path.read_bytes()
            with self.subTest(name=name, error=error):
                path.write_bytes(original.replace(old, new))
                self.assertEqual(self.pack().returncode, 0)
                with self.assertRaisesRegex(ValueError, error):
                    self.parse(self.archive, 'compute')
            path.write_bytes(original)

    def test_compute_override_requires_workload_root(self):
        self.command += ['--gles-compute', str(self.directory / 'gles-compute-smoke')]
        self.assertEqual(self.pack().returncode, 2)
        self.assertFalse(self.archive.exists())

    def test_ml_packaging_requires_matched_workload_binary(self):
        self.command += ['--glmark-env', str(ROOT / 'GPU-SFTP/tests/realm-xshm/glmark.env'),
                         '--performance-suite', str(ROOT / 'GPU-SFTP/tests/realm-xshm/performance-suite.sh')]
        self.assertEqual(self.pack().returncode, 0)
        with self.assertRaisesRegex(ValueError, 'gles-ml-smoke'):
            self.parse(self.archive, 'glmark', ['ml-gemm'])
        self.command += ['--gles-ml', str(self.directory / 'realm-xshm')]
        self.assertEqual(self.pack().returncode, 0)
        self.assertIn('gles-ml-smoke', self.parse(self.archive, 'glmark', ['ml-gemm']))

    def test_missing_firmware_rejected_before_upload(self):
        self.assertEqual(self.pack(firmware=False).returncode, 0)
        with self.assertRaises(ValueError):
            self.parse(self.archive)

    def test_bad_firmware_does_not_replace_existing_archive(self):
        self.archive.write_bytes(b'previous artifact')
        self.firmware = self.directory / 'bad-firmware'
        self.firmware.write_bytes(b'bad firmware')
        self.assertEqual(self.pack().returncode, 2)
        self.assertEqual(self.archive.read_bytes(), b'previous artifact')

    def test_firmware_requires_private_tool(self):
        command = self.command[:]
        position = command.index('--gpu-private')
        del command[position:position + 2]
        self.assertEqual(subprocess.run(command + ['--gpu-firmware', str(self.firmware)],
                                       capture_output=True).returncode, 2)
        self.assertFalse(self.archive.exists())

    def test_old_init_without_dispatch_rejected(self):
        old = (self.directory / 'init').read_bytes().replace(b'/realm-gpu-private', b'/old-tool')
        (self.directory / 'init').write_bytes(old)
        self.assertEqual(self.pack().returncode, 0)
        with self.assertRaisesRegex(ValueError, 'dispatch'):
            self.parse(self.archive)

    def test_old_tool_without_mode_check_rejected(self):
        old = (self.directory / 'realm-gpu-private').read_bytes().replace(b'mode-check', b'old-tool')
        (self.directory / 'realm-gpu-private').write_bytes(old)
        self.assertEqual(self.pack().returncode, 0)
        with self.assertRaisesRegex(ValueError, 'driver-mode checking'):
            self.parse(self.archive)

    def test_non_aarch64_tool_rejected(self):
        old = bytearray((self.directory / 'realm-gpu-private').read_bytes())
        struct.pack_into('<H', old, 18, 62)
        (self.directory / 'realm-gpu-private').write_bytes(old)
        self.assertEqual(self.pack().returncode, 0)
        with self.assertRaisesRegex(ValueError, 'AArch64'):
            self.parse(self.archive)

    def test_truncated_and_nonzero_trailer_rejected(self):
        self.assertEqual(self.pack().returncode, 0)
        original = self.archive.read_bytes()
        for mutation in (original[:-1], original[:-1] + b'\x01'):
            with self.subTest(length=len(mutation)):
                self.archive.write_bytes(mutation)
                with self.assertRaises(ValueError):
                    self.parse(self.archive)

    def test_duplicate_tool_entry_rejected(self):
        self.assertEqual(self.pack().returncode, 0)
        original = self.archive.read_bytes()
        position, init_record = 0, None
        while True:
            fields = [int(original[position + 6 + 8 * i:position + 14 + 8 * i], 16)
                      for i in range(13)]
            start = position + 110
            name = original[start:start + fields[11] - 1].decode()
            body = (start + fields[11] + 3) & ~3
            following = (body + fields[6] + 3) & ~3
            if name == 'init':
                init_record = original[position:following]
            if name == 'TRAILER!!!':
                break
            position = following
        self.assertIsNotNone(init_record)
        mutated = original[:position] + init_record + original[position:]
        self.archive.write_bytes(mutated + bytes(-len(mutated) % 4096))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.parse(self.archive)

    def test_corrupt_firmware_inside_archive_rejected(self):
        self.assertEqual(self.pack().returncode, 0)
        archive = bytearray(self.archive.read_bytes())
        position = archive.index(self.firmware.read_bytes())
        archive[position] ^= 1
        self.archive.write_bytes(archive)
        with self.assertRaisesRegex(ValueError, 'firmware differs'):
            self.parse(self.archive)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print(f'GPU_PRIVATE_RUNNER=PASS cases={result.testsRun} OFFLINE_SERIAL_AND_WORKLOAD_DOUBLES_ONLY')
