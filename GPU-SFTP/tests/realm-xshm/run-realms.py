#!/usr/bin/env python3
"""Real three-Realm endpoint/event test. Run on idle RK under the lab lease."""
import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import selectors
import subprocess
import threading
import time

PERFORMANCE_PROFILES = ('ioctl', 'compute-4', 'compute-16', 'compute-64', 'compute-128',
                        'ml-all', 'attention-320', 'ncnn-mobilenet_v2',
                        'ncnn-mobilenet_v3', 'ncnn-resnet50', 'glmark-720', 'glmark-1080')
ML_PROFILES = ('ml-all', 'attention-320', 'ncnn-mobilenet_v2',
               'ncnn-mobilenet_v3', 'ncnn-resnet50', 'ml-gemm', 'ml-conv',
               'ml-depthwise', 'ml-reduction', 'ml-softmax', 'ml-attention')

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--run-id', required=True)
p.add_argument('--memory-pages', type=int, default=0)
p.add_argument('--large-pool', action='store_true', help='512 MiB RMM pool; 1024 MiB per Realm and 576 MiB CMA (requires updated RMM)')
p.add_argument('--profiles', nargs='+', choices=tuple(dict.fromkeys(PERFORMANCE_PROFILES + ML_PROFILES)), help='Explicit subset of --suite; omitted cases are not tested')
p.add_argument('--trusted-events', action='store_true', help='Require RMM-owned actual virtual IRQ delivery and negative/coalescing checks')
p.add_argument('--transport', action='store_true', help='Bind the RMM pool to real kernel control queues')
p.add_argument('--parallel-boot', action='store_true', help='Exercise concurrent Host Realm population')
p.add_argument('--gpu-flow', action='store_true', help='Assign GPU to provider and exercise Client DRM over the RMM pool')
p.add_argument('--glmark-rootfs', type=Path, help='Read-only prepared Panfrost rootfs for the complete glmark suite')
p.add_argument('--compute-rootfs', type=Path, help='Read-only rootfs for concurrent actual compute in two Clients')
p.add_argument('--clients', type=int, choices=(1, 2, 3, 4), default=1)
p.add_argument('--compact-memory', action='store_true', help='Bound benchmark RAM and CMA using the actual per-Client pool size')
p.add_argument('--reclaim-targets', action='store_true', help='Use verified target-backing reclamation and staged ResNet50 memory admission')
p.add_argument('--pin-cpus', action='store_true', help='Explicit RK CPU 0 Proxy / CPU 1 active Client placement')
p.add_argument('--performance', action='store_true', help='600 MHz OPP, separate CPUs, concurrent RPC, wait cache, fused/lazy snapshots and 1000 us Client reply polling')
p.add_argument('--benchmark-only', action='store_true', help='Two Realms and full glmark; defer the broader lifecycle/API suite')
p.add_argument('--suite', action='store_true', help='Remeasure common IOCTL, compute, ML, NCNN and both full glmark sizes')
p.add_argument('--rpc-stats', action='store_true', help='Measure Client/Proxy RPC, backend submission and GPU IRQ latency (adds timing overhead)')
p.add_argument('--client-cpu-layout', choices=('shared', 'round-robin'), default='shared')
p.add_argument('--cpu-frequency-khz', type=int, help='Lock Host CPU policy0 for a controlled performance comparison')
p.add_argument('--telemetry', action='store_true', help='Collect Realm CPU accounting during full concurrent glmark')
p.add_argument('--gpu-fault-isolation', action='store_true', help='Require an intentional foreign-VA GPU fault and victim recovery in the two-Client suite')
p.add_argument('--bo-sg-mmap', action='store_true', help='Validate fragmented BO CPU mappings in the two-Client compute suite')
p.add_argument('--root', type=Path, default=Path('/root/GPU-SFTP'))
a = p.parse_args()
if a.profiles and not a.suite:
    p.error('--profiles requires --suite')
if a.large_pool and (not a.benchmark_only or not a.glmark_rootfs or a.memory_pages != 131072):
    p.error('--large-pool requires --benchmark-only, --glmark-rootfs and --memory-pages 131072')
if not a.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run_id):
    p.error('invalid run-id')
bins = a.root/'firecracker-bins'
out = a.root/'log/realm-xshm'/a.run_id
if not 0 <= a.memory_pages <= (131072 if a.large_pool or a.compact_memory else 65536):
    p.error('memory-pages exceeds the selected pool profile')
if a.transport and a.memory_pages < 256:
    p.error('--transport requires at least 256 memory pages')
if a.gpu_flow and (not a.transport or a.memory_pages < 1025):
    p.error('--gpu-flow requires --transport and at least 1025 memory pages')
if a.compact_memory and (not a.benchmark_only or a.large_pool or a.memory_pages not in (32768, 40960, 49152, 65536, 86016, 98304)):
    p.error('--compact-memory requires benchmark-only and a 128/160/192/256/336/384 MiB pool')
if a.reclaim_targets and not (a.compact_memory and a.profiles == ['ncnn-resnet50']):
    p.error('--reclaim-targets requires compact memory and only ncnn-resnet50')
if a.glmark_rootfs and (not a.gpu_flow or (not a.compact_memory and a.memory_pages != (131072 if a.large_pool else 65536))):
    p.error('--glmark-rootfs requires --gpu-flow and the selected pool size')
if a.compute_rootfs and (not a.gpu_flow or a.clients != 2):
    p.error('--compute-rootfs requires --gpu-flow --clients 2')
if a.clients > 1 and (not a.gpu_flow or (not a.benchmark_only and a.clients != 2)):
    p.error('multiple Clients require GPU flow and either benchmark-only or the two-Client compute suite')
if a.benchmark_only and (a.compact_memory or a.clients > 1) and (not a.suite or not a.profiles or
        not (a.profiles in (['glmark-720'], ['glmark-1080']) or all(profile in ML_PROFILES for profile in a.profiles))):
    p.error('concurrent benchmarks require --suite and either one glmark profile or explicit ML profiles')
if a.suite and not a.benchmark_only:
    p.error('--suite requires --benchmark-only')
if a.benchmark_only and not a.glmark_rootfs:
    p.error('--benchmark-only requires --glmark-rootfs')
if a.performance and not a.gpu_flow:
    p.error('--performance requires --gpu-flow')
if a.gpu_fault_isolation and (not a.compute_rootfs or a.benchmark_only):
    p.error('--gpu-fault-isolation requires the two-Client compute suite')
if a.bo_sg_mmap and (not a.compute_rootfs or a.benchmark_only):
    p.error('--bo-sg-mmap requires the two-Client compute suite')
if (a.client_cpu_layout != 'shared' or a.cpu_frequency_khz or a.telemetry) and not (
        a.performance and a.benchmark_only and a.compact_memory and
        a.profiles in (['glmark-720'], ['glmark-1080'])):
    p.error('controlled CPU placement/frequency/telemetry require a compact full glmark performance run')
vm_count = a.clients + 1 if a.benchmark_only else 3
workload_rootfs = a.glmark_rootfs or a.compute_rootfs
out.mkdir(parents=True, exist_ok=False)
processes, files, buffers, commands, grants, bindings = [], [], {}, [], [], []
sel = selectors.DefaultSelector()
result = {'run_id': a.run_id, 'status': 'RUNNING', 'commands': commands,
          'memory_pages': a.memory_pages, 'transport': a.transport,
          'trusted_events': a.trusted_events,
          'parallel_boot': a.parallel_boot, 'gpu_flow': a.gpu_flow,
          'clients': a.clients, 'pin_cpus': a.pin_cpus,
          'performance': a.performance, 'benchmark_only': a.benchmark_only,
          'compute_rootfs': str(a.compute_rootfs) if a.compute_rootfs else None,
          'glmark_rootfs': str(a.glmark_rootfs) if a.glmark_rootfs else None,
          'rpc_stats': a.rpc_stats, 'suite': a.suite, 'large_pool': a.large_pool,
          'profiles': a.profiles}
result['compact_memory'] = a.compact_memory
result['reclaim_targets'] = a.reclaim_targets
result['client_cpu_layout'] = a.client_cpu_layout
result['cpu_frequency_khz'] = a.cpu_frequency_khz
result['telemetry'] = a.telemetry
result['bo_sg_mmap_check'] = 'NOT_RUN'
result['inputs'] = {}
inputs = [Path(__file__), bins/'bin/firecracker',
          bins/'kernels/realm-xshm/Image', bins/'kernels/realm-xshm/initrd.cpio']
if a.gpu_flow:
    inputs.append(bins/'kernels/realm-xshm/proxy/Image')
if workload_rootfs:
    inputs.append(workload_rootfs)
for path in inputs:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    result['inputs'][str(path)] = digest.hexdigest()
(out/'runner.py').write_bytes(Path(__file__).read_bytes())
command_log = (out/'commands.jsonl').open('w')
host_restore = {}
expected_gpu_fault_lines = set()
benchmark_events = {}
monitor_stop = threading.Event()
monitor_thread = None


def monitor_resources():
    with (out/'memory-samples.jsonl').open('w') as stream:
        while not monitor_stop.is_set():
            memory = {line.split(':')[0]: int(line.split()[1])
                      for line in Path('/proc/meminfo').read_text().splitlines()}
            sample = {'monotonic_ns': time.monotonic_ns(),
                      'available_kib': memory['MemAvailable'], 'swap_free_kib': memory['SwapFree']}
            stream.write(json.dumps(sample)+'\n')
            stream.flush()
            monitor_stop.wait(1)


def realm_memory(vm):
    if a.benchmark_only and (a.compact_memory or a.clients > 1):
        cma_mib = (a.memory_pages // 256) * (a.clients if vm == 0 else 1) + 16
        ordinary_mib = (192 + 32 * a.clients if vm == 0 else
                        (304 if 'ncnn-resnet50' in (a.profiles or []) else 192))
        if a.reclaim_targets and a.clients == 4:
            ordinary_mib = 232 if vm == 0 else 296
            if vm:
                cma_mib -= 8
        return cma_mib + ordinary_mib, cma_mib
    return (1024, 576) if a.large_pool else ((768 if workload_rootfs else 512), None)


def realm_swiotlb_mib():
    return 8 if a.reclaim_targets and a.clients == 4 else 16


def isolate_vmm_io(vm):
    process = processes[vm]
    threads = []
    vcpus = []
    for task in sorted(Path(f'/proc/{process.pid}/task').iterdir()):
        name = (task/'comm').read_text().strip()
        tid = int(task.name)
        if name.startswith('fc_vcpu'):
            vcpus.append(tid)
        else:
            os.sched_setaffinity(tid, {0})
        threads.append({'tid': tid, 'name': name, 'cpus': sorted(os.sched_getaffinity(tid))})
    assert len(vcpus) == 1, threads
    result.setdefault('thread_affinity', {})[str(vm)] = threads
    save()


def save():
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')


def memory_guard(stage, allocation_mib=0):
    available_mib = next(int(line.split()[1]) / 1024
                         for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
    sample = {'stage': stage, 'available_mib': available_mib,
              'allocation_mib': allocation_mib, 'headroom_mib': 256}
    result.setdefault('memory_stage_guards', []).append(sample)
    save()
    assert available_mib >= allocation_mib + 256, sample


def host_snapshot():
    gpu = Path('/sys/class/devfreq/fb000000.gpu')
    return {'online': Path('/sys/devices/system/cpu/online').read_text().strip(),
            'governor': (gpu/'governor').read_text().strip(),
            'selected_hz': int((gpu/'cur_freq').read_text()),
            'actual_hz': int(Path('/sys/kernel/debug/clk/clk_gpu/clk_rate').read_text())}


def prepare_performance():
    gpu = Path('/sys/class/devfreq/fb000000.gpu')
    assert Path('/sys/bus/platform/devices/fb000000.gpu/driver').resolve().name == 'pmthor'
    assert '600000000' in (gpu/'available_frequencies').read_text().split()
    host_restore['before'] = host_snapshot()
    host_restore['cpus'] = {}
    # Record restoration data before the first mutation, including partial setup.
    for cpu in (2, 3):
        path = Path(f'/sys/devices/system/cpu/cpu{cpu}/online')
        host_restore['cpus'][str(path)] = path.read_text().strip()
        path.write_text('1')
    if a.cpu_frequency_khz:
        policy = Path('/sys/devices/system/cpu/cpufreq/policy0')
        assert str(a.cpu_frequency_khz) in (policy/'scaling_available_frequencies').read_text().split()
        host_restore['cpu_policy'] = {name: (policy/name).read_text().strip() for name in
            ('scaling_governor', 'scaling_min_freq', 'scaling_max_freq')}
        (policy/'scaling_max_freq').write_text(str(a.cpu_frequency_khz))
        (policy/'scaling_min_freq').write_text(str(a.cpu_frequency_khz))
        (policy/'scaling_governor').write_text('performance')
    request = (gpu/'userspace/set_freq').read_text().strip()
    host_restore['request'] = request if request.isdigit() else str(host_restore['before']['selected_hz'])
    (gpu/'governor').write_text('userspace')
    (gpu/'userspace/set_freq').write_text('600000000')
    result['host_performance'] = {'before': host_restore['before'], 'selected': host_snapshot()}
    assert result['host_performance']['selected']['selected_hz'] == 600000000, 'GPU OPP constrained'
    save()


def restore_performance():
    gpu = Path('/sys/class/devfreq/fb000000.gpu')
    if 'request' in host_restore:
        (gpu/'governor').write_text('userspace')
        (gpu/'userspace/set_freq').write_text(host_restore['request'])
        (gpu/'governor').write_text(host_restore['before']['governor'])
    if 'cpu_policy' in host_restore:
        policy = Path('/sys/devices/system/cpu/cpufreq/policy0')
        for name in ('scaling_min_freq', 'scaling_max_freq', 'scaling_governor'):
            (policy/name).write_text(host_restore['cpu_policy'][name])
        assert all((policy/name).read_text().strip() == value
                   for name, value in host_restore['cpu_policy'].items())
    for name, value in host_restore.get('cpus', {}).items():
        Path(name).write_text(value)
    if host_restore:
        result.setdefault('host_performance', {})['restored'] = host_snapshot()
        assert result['host_performance']['restored']['online'] == host_restore['before']['online']
        assert result['host_performance']['restored']['governor'] == host_restore['before']['governor']


def receive(vm, marker, timeout=120):
    deadline = time.monotonic() + timeout
    while marker not in buffers[vm]:
        if marker in (b'GLMARK_BENCHMARK_READY', b'ML_BENCHMARK_READY', b'ML_TIMING_READY'):
            for target in range(1, vm_count):
                if (b'XSHM_COMMAND_EXIT=' in buffers[target] and
                        marker not in buffers[target]):
                    raise RuntimeError(f'Realm {target}: workload exited before benchmark barrier')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f'Realm {vm}: timeout waiting for {marker!r}')
        for key, _ in sel.select(min(remaining, 1)):
            target = key.data
            data = os.read(key.fd, 65536)
            if not data:
                sel.unregister(key.fd)
                raise RuntimeError(f'Realm {target} exited during test: {processes[target].poll()}')
            files[target].write(data)
            files[target].flush()
            buffers[target] += data
            for label, token in (('ready', b'GLMARK_BENCHMARK_READY'),
                                 ('start', b'GLMARK_PROGRESS_START '),
                                 ('end', b'== glmark2 output =='),
                                 ('ready', b'ML_BENCHMARK_READY'),
                                 ('start', b'ML_BENCHMARK_START'),
                                 ('end', b'ML_BENCHMARK_END'),
                                 ('timing_ready', b'ML_TIMING_READY'),
                                 ('timing_start', b'ML_TIMING_START'),
                                 ('timing_end', b'ML_TIMING_END')):
                if token in buffers[target]:
                    benchmark_events.setdefault(str(target), {}).setdefault(label, time.monotonic_ns())
    before, buffers[vm] = buffers[vm].split(marker, 1)
    return before


def parse_command_exit(line):
    # printk may follow the integer on the same serial line. Accept only
    # the exact decimal token before an identifiable printk prefix.
    match = re.fullmatch(rb'([0-9]{1,3})(?:\[\s*[0-9]+\.[0-9]+\].*)?', line)
    if not match or int(match[1]) > 255:
        raise RuntimeError(f'Malformed command exit line: {line!r}')
    return int(match[1])


def call(vm, command, expected=0):
    proc = processes[vm]
    buffers[vm] = b''
    proc.stdin.write((command+'\n').encode())
    proc.stdin.flush()
    data = receive(vm, b'XSHM_COMMAND_EXIT=')
    # Preserve command exit codes as well as the RMM response.
    exit_line = receive(vm, b'\n').strip().strip(b'\r')
    responses = []
    for line in data.splitlines():
        start = line.find(b'{"command":')
        if start >= 0:
            # Kernel printk may append a message after a complete JSON
            # object on the serial line. Decode exactly that object, keeping
            # the original line in the raw log for review.
            response, _ = json.JSONDecoder().raw_decode(line[start:].decode())
            responses.append(response)
    if len(responses) != 1:
        raise RuntimeError(f'Realm {vm}: missing/ambiguous response to {command!r}')
    response = responses[0]
    if response['command'] != command.split()[2 if command.startswith('--pool ') else 0]:
        raise RuntimeError('serial response does not match command')
    entry = {'realm': vm, 'command': command, 'expected_status': expected,
             'response': response, 'returncode': parse_command_exit(exit_line)}
    commands.append(entry)
    command_log.write(json.dumps(entry)+'\n')
    command_log.flush()
    if (expected is not None and response['status'] != expected) or entry['returncode'] != (0 if response['status'] == 0 else (1 if response['status'] < 0 else 3)):
        raise RuntimeError(f'Unexpected Realm response: {entry}')
    return response['result']


def memory_operation(vm, command, expected_state):
    response = call(vm, command, None)
    grant = response[0]
    if command.startswith('mem-offer ') and grant:
        grants.append((vm, grant))
    for _ in range(3*a.memory_pages//64 + 16):
        status = commands[-1]['response']['status']
        if status == 0:
            assert response[1] == expected_state
            if command.startswith('mem-revoke ') and (vm, grant) in grants:
                grants.remove((vm, grant))
            return grant
        assert status == 3
        response = call(vm, f'mem-continue {grant}', None)
    raise RuntimeError('memory operation failed to make bounded progress')


def text_command(vm, command, markers, timeout=120, sent=False):
    if not sent:
        buffers[vm] = b''
        processes[vm].stdin.write((command+'\n').encode())
        processes[vm].stdin.flush()
    data = receive(vm, b'XSHM_COMMAND_EXIT=', timeout)
    code = parse_command_exit(receive(vm, b'\n').strip().strip(b'\r'))
    entry = {'realm': vm, 'command': command, 'returncode': code,
             'markers': {marker: marker.encode() in data for marker in markers}}
    commands.append(entry)
    command_log.write(json.dumps(entry)+'\n')
    command_log.flush()
    if code or not all(entry['markers'].values()):
        raise RuntimeError(f'GPU workload failed: {entry}')
    return data.decode(errors='replace')


# Exercise the baseline DRM modes and GPUVM isolation over the actual Realm
# transport. Host PFN and passthrough cases remain separate.
GPU_IOCTL_MODES = (
    'basic', 'vm-create', 'bo-create', 'bo-lifecycle', 'bo-mmap',
    'vm-bind', 'vm-bind-async-sync', 'vm-state-flush',
    'syncobj-lifecycle', 'syncobj-wait', 'syncobj-transfer',
    'syncobj-timeline-wait', 'syncobj-signal-query', 'sync-file-snapshot',
    'group-lifecycle', 'group-submit-syncpoint', 'tiler-heap-lifecycle',
    'gpuvm-isolation',
)


def kernel_issues(log):
    patterns = {
        'csg_update_timeout': r'CSG \d+ update request timedout',
        'fw_ping_timeout': r'FW ping timeout',
        'gpu_translation_fault': r'(?:TRANSLATION_FAULT|translation fault|Translation fault)',
        'kernel_warning': r'WARNING:',
        'kernel_oops': r'Oops:',
        'kernel_panic': r'Kernel panic',
        'out_of_memory': r'(?:Out of memory|invoked oom-killer|oom-kill:)',
    }
    lines = re.split(r'[\r\n]', log)
    return {name: sorted({line for line in lines if re.search(pattern, line)})
            for name, pattern in patterns.items()}


def gpu_fault_identity(line):
    match = re.search(r'\[\s*([0-9.]+)\]\s*(.*)$', line)
    return match.groups() if match else (None, line.strip())


def gpu_smoke(vm, mode):
    text_command(vm, f'gpu-smoke --{mode} /dev/dri/renderD128',
                 ['PANTHOR_IOCTL_SMOKE='+mode.upper().replace('-', '_')+'_PASS'])


def glmark(vm):
    data = text_command(vm, 'glmark', ['GLMARK_VALIDATE=PASS',
                        'GLMARK_CLEAN_RESULT=PASS', 'GLMARK_RESULT=PASS',
                        'GPU_SMOKE_RESULT=PASS', 'COMPUTE_CHECK=PASS'], 900)
    renderer = re.search(r'GLMARK_RENDERER=([^\r\n]+)', data)
    score = re.search(r'GLMARK_SCORE=(\d+)', data)
    validation = re.search(r'GLMARK_VALIDATE_SUCCESS=(\d+) FAILURE=(\d+) UNKNOWN=(\d+)', data)
    scenes = re.findall(r'^\[[^\r\n]+\].*FPS:\s*\d+', data, re.MULTILINE)
    submission_errors = re.findall(r'[^\r\n]*panfrost_batch_submit failed[^\r\n]*', data)
    # Keep measured evidence even when validation below rejects the run.
    result['glmark'] = {'score': int(score[1]) if score else None,
                       'renderer': renderer[1] if renderer else None,
                       'scenes': len(scenes),
                       'validation': list(map(int, validation.groups())) if validation else None,
                       'submission_errors': submission_errors}
    assert not submission_errors, f'GPU submission failed: {submission_errors}'
    assert renderer and ('Mali' in renderer[1] or 'Panfrost' in renderer[1])
    assert score and int(score[1]) > 0 and validation
    assert len(scenes) == 33, f'Expected all 33 benchmark scenes, got {len(scenes)}'


def parse_glmark(data):
    renderer = re.search(r'GLMARK_RENDERER=([^\r\n]+)', data)
    size = re.search(r'GLMARK_SIZE=([^\r\n]+)', data)
    score = re.search(r'GLMARK_SCORE=(\d+)', data)
    validation = re.search(r'GLMARK_VALIDATE_SUCCESS=(\d+) FAILURE=(\d+) UNKNOWN=(\d+)', data)
    scenes = [{'scene': match[1], 'fps': int(match[2]), 'frame_ms': float(match[3])}
              for match in re.finditer(r'^(\[[^\r\n]+\].*?)FPS:\s*(\d+)\s+FrameTime:\s*([0-9.]+)', data, re.MULTILINE)]
    errors = re.findall(r'[^\r\n]*(?:panfrost_batch_submit failed|PANTHOR_BO_CREATE failed|DRM_IOCTL_PANTHOR_VM_BIND failed|MESA: error: export failed)[^\r\n]*', data)
    measured = {'score': int(score[1]) if score else None,
                'size': size[1] if size else None,
                'renderer': renderer[1] if renderer else None,
                'validation': list(map(int, validation.groups())) if validation else None,
                'scenes': scenes, 'errors': errors}
    assert score and int(score[1]) > 0 and renderer and ('Mali' in renderer[1] or 'Panfrost' in renderer[1]), measured
    assert len(scenes) == 33 and measured['validation'] == [26, 1, 6] and not errors, measured
    expected_size = '1920x1080' if a.profiles == ['glmark-1080'] else '1280x720'
    assert measured['size'] == expected_size, measured
    return measured


def run_concurrent_ml():
    result['concurrent_ml'] = []
    for profile in a.profiles:
        benchmark_events.clear()
        prepared = {}
        for vm in range(1, vm_count):
            buffers[vm] = b''
            benchmark_events[str(vm)] = {'dispatch': time.monotonic_ns()}
            processes[vm].stdin.write(f'performance {profile}-barrier\n'.encode())
            processes[vm].stdin.flush()
        for vm in range(1, vm_count):
            prepared[vm] = receive(vm, b'ML_BENCHMARK_READY', 120)
            receive(vm, b'\n')
        for vm in range(1, vm_count):
            benchmark_events[str(vm)]['release'] = time.monotonic_ns()
            processes[vm].stdin.write(b'ML_BENCHMARK_GO\n')
            processes[vm].stdin.flush()
        timed_barrier = not profile.startswith('ncnn-') and profile != 'ml-all'
        if timed_barrier:
            for vm in range(1, vm_count):
                prepared[vm] += receive(vm, b'ML_TIMING_READY', 900)
                prepared[vm] += receive(vm, b'\n')
            for vm in range(1, vm_count):
                benchmark_events[str(vm)]['timing_release'] = time.monotonic_ns()
                processes[vm].stdin.write(b'ML_TIMING_GO\n')
                processes[vm].stdin.flush()
        case = {'profile': profile, 'clients': [], 'barrier': True}
        result['concurrent_ml'].append(case)
        for vm in range(1, vm_count):
            data = prepared[vm] + receive(vm, b'XSHM_COMMAND_EXIT=', 2400)
            code = parse_command_exit(receive(vm, b'\n').strip().strip(b'\r'))
            (out/f'{profile}-client-{vm}.log').write_bytes(data)
            log = data.decode(errors='replace').replace('\r', '').replace('\x00', '')
            required = (['NCNN_RESULT=PASS', 'NCNN_MODEL_RESULT=PASS',
                         'NCNN_BACKEND_QUALIFICATION=PASS', 'NCNN_BACKEND=panvk-direct']
                        if profile.startswith('ncnn-') else
                        ['ML_RESULT=PASS', 'ML_CLEAN_RESULT=PASS', 'GL_RENDERER=Mali-G610'])
            errors = re.findall(r'[^\n]*(?:vk\w+ failed|VK_ERROR_|MESA: error:|PANTHOR_BO_CREATE failed|DRM_IOCTL_PANTHOR_VM_BIND failed|ML_CHECK=FAIL|ML_RESULT=FAIL|NCNN_MODEL_RESULT=FAIL)[^\n]*', log)
            entry = {'client': vm, 'returncode': code,
                     'pass_marker': all(marker in log for marker in required + ['PERFORMANCE_CASE_RESULT=PASS']),
                     'errors': errors, 'metrics_ms': {}}
            case['clients'].append(entry)
            if profile.startswith('ncnn-'):
                timings = re.findall(r'^NCNN_ITER_MS_AVG=([0-9.]+)$', log, re.MULTILINE)
                if len(timings) == 1:
                    entry['metrics_ms'][profile] = float(timings[0])
                expected = 1
            else:
                timings = re.findall(r'^ML_KERNEL=([^\n]+)\nML_CHECK=PASS samples=(\d+) warmup=(\d+)\nML_ITER_US min=\d+ avg=([0-9.]+)', log, re.MULTILINE)
                entry['metrics_ms'] = {name: float(avg)/1000 for name, samples, warmup, avg in timings}
                expected = 6 if profile == 'ml-all' else 1
                assert all((int(samples), int(warmup)) == ((10, 2) if profile == 'attention-320' else (100, 5))
                           for name, samples, warmup, avg in timings), entry
            save()
            assert not code and entry['pass_marker'] and not errors, entry
            assert len(entry['metrics_ms']) == expected and all(value > 0 for value in entry['metrics_ms'].values()), entry
            print('CONCURRENT_ML', profile, vm, entry['metrics_ms'], flush=True)
        starts = [benchmark_events[str(vm)]['timing_start' if timed_barrier else 'start'] for vm in range(1, vm_count)]
        ends = [benchmark_events[str(vm)]['timing_end' if timed_barrier else 'end'] for vm in range(1, vm_count)]
        case['events'] = dict(benchmark_events)
        case['overlap'] = {'observation_clock': ('Host CLOCK_MONOTONIC serial receive; measured iterations after warmup' if timed_barrier else
                                               'Host CLOCK_MONOTONIC serial receive; complete workload including setup'),
                           'common_seconds': (min(ends)-max(starts))/1e9,
                           'union_seconds': (max(ends)-min(starts))/1e9,
                           'fraction': (min(ends)-max(starts))/(max(ends)-min(starts))}
        case['status'] = ('PASS' if case['overlap']['common_seconds'] > 0 else 'FAIL_NO_OVERLAP')
        print('ML_CASE_RESULT', profile, case['status'], flush=True)
        save()


def test_concurrent_benchmark():
    result['realm_memory_samples'] = {}
    for vm in range(vm_count):
        result['realm_memory_samples'][str(vm)] = {'before_pool': text_command(
            vm, 'memory-info', ['XSHM_MEMORY_INFO_END'])}
    endpoints = [call(vm, 'register') for vm in range(vm_count)]
    assert len({endpoint[1] for endpoint in endpoints}) == vm_count
    assert all(endpoint[2] & 16 for endpoint in endpoints)
    for vm in range(vm_count):
        assert call(vm, 'irq-bind')[0] == 127
    before = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
    active = []
    size = a.memory_pages * 4096
    for vm in range(1, vm_count):
        channel = call(0, f'offer {endpoints[vm][1]}')[0]
        call(vm, f'accept {channel}')
        if a.reclaim_targets:
            memory_guard(f'client-{vm}-before-source', 2 * size / (1024 * 1024))
        source = call(0, f'pool-source {size}')[0]
        if a.reclaim_targets:
            memory_guard(f'client-{vm}-before-target', size / (1024 * 1024))
        target = call(vm, f'pool-target {size}')[0]
        grant = memory_operation(0, f'mem-offer {channel} {source} {size}', 2)
        memory_operation(vm, f'mem-attach {grant} {target}', 5)
        if a.reclaim_targets:
            memory_guard(f'client-{vm}-after-attach')
        for member in (0, vm):
            call(member, f'pool-bind-gpu {grant}')
            bindings.append((member, grant))
        active.append((vm, channel, grant))
    result['simultaneous_client_bindings'] = a.clients
    if a.reclaim_targets:
        memory_guard('before-workload')
    for vm in range(vm_count):
        result['realm_memory_samples'][str(vm)]['bound_pool'] = text_command(
            vm, 'memory-info', ['XSHM_MEMORY_INFO_END'])
    log = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
    for endpoint in endpoints[1:]:
        assert f'permissions PASS owner={endpoint[1]}' in log
        assert f'GPU isolation PASS owner={endpoint[1]}' in log
    if all(profile in ML_PROFILES for profile in a.profiles):
        run_concurrent_ml()
    else:
        run_concurrent_glmark()
    after = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
    assert all(after[vm] > before[vm] for vm in range(vm_count))
    result['event_irq'] = {'before': before, 'after_workloads': after, 'intid': 127}
    for vm, channel, grant in reversed(active):
        for member in (vm, 0):
            call(member, f'pool-unbind {grant}')
            bindings.remove((member, grant))
        memory_operation(vm, f'mem-detach {grant}', 2)
        memory_operation(0, f'mem-revoke {grant}', 0)
        call(0, f'close {channel}')
    for vm in range(vm_count):
        call(vm, 'unregister')


def run_concurrent_glmark():
    profile = a.profiles[0]
    command = f'performance {profile}-barrier'
    result['concurrent_glmark'] = []
    if a.telemetry:
        for vm in range(vm_count):
            text_command(vm, 'telemetry-start', [])
    prepared = {}
    for vm in range(1, vm_count):
        buffers[vm] = b''
        benchmark_events[str(vm)] = {'dispatch': time.monotonic_ns()}
        processes[vm].stdin.write((command+'\n').encode())
        processes[vm].stdin.flush()
    for vm in range(1, vm_count):
        prepared[vm] = receive(vm, b'GLMARK_BENCHMARK_READY', 900)
        receive(vm, b'\n')
        assert b'GLMARK_VALIDATE=PASS' in prepared[vm], f'Realm {vm}: validation missing before barrier'
    result['benchmark_start_barrier'] = True
    for vm in range(1, vm_count):
        benchmark_events[str(vm)]['release'] = time.monotonic_ns()
        processes[vm].stdin.write(b'GLMARK_BENCHMARK_GO\n')
        processes[vm].stdin.flush()
    for vm in range(1, vm_count):
        data = prepared[vm] + receive(vm, b'XSHM_COMMAND_EXIT=', 2400)
        code = parse_command_exit(receive(vm, b'\n').strip().strip(b'\r'))
        (out/f'{profile}-client-{vm}.log').write_bytes(data)
        entry = {'client': vm, 'returncode': code,
                 'pass_marker': all(marker in data for marker in
                     (b'PERFORMANCE_CASE_RESULT=PASS', b'GLMARK_RESULT=PASS',
                      b'GLMARK_VALIDATE=PASS', b'GLMARK_CLEAN_RESULT=PASS'))}
        result['concurrent_glmark'].append(entry)
        save()
        assert not code and entry['pass_marker'], entry
        entry.update(parse_glmark(data.decode(errors='replace').replace('\r', '').replace('\x00', '')))
        save()
        print('CONCURRENT_GLMARK', vm, entry['score'], flush=True)
    result['benchmark_events'] = benchmark_events
    starts = [benchmark_events[str(vm)]['start'] for vm in range(1, vm_count)]
    ends = [benchmark_events[str(vm)]['end'] for vm in range(1, vm_count)]
    result['benchmark_overlap'] = {'observation_clock': 'Host CLOCK_MONOTONIC serial receive',
        'common_seconds': (min(ends)-max(starts))/1e9,
        'union_seconds': (max(ends)-min(starts))/1e9,
        'fraction': (min(ends)-max(starts))/(max(ends)-min(starts)),
        'dispatch_spread_ms': (max(event['dispatch'] for event in benchmark_events.values())-
                               min(event['dispatch'] for event in benchmark_events.values()))/1e6}
    assert result['benchmark_overlap']['fraction'] >= 0.9, result['benchmark_overlap']
    if a.telemetry:
        for vm in range(vm_count):
            samples = text_command(vm, 'telemetry-stop', ['XSHM_CPU_SAMPLES_END'])
            (out/f'cpu-realm-{vm}.log').write_text(samples)
def test_benchmark():
    endpoints = [call(vm, 'register') for vm in range(2)]
    assert endpoints[0][1] != endpoints[1][1]
    assert all(endpoint[2] & 16 for endpoint in endpoints)
    for vm in range(2):
        assert call(vm, 'irq-bind')[0] == 127
    before = [call(vm, 'irq-stats')[0] for vm in range(2)]
    channel = call(0, f'offer {endpoints[1][1]}')[0]
    call(1, f'accept {channel}')
    size = a.memory_pages * 4096
    source = call(0, f'pool-source {size}')[0]
    target = call(1, f'pool-target {size}')[0]
    grant = memory_operation(0, f'mem-offer {channel} {source} {size}', 2)
    memory_operation(1, f'mem-attach {grant} {target}', 5)
    for vm, ipa in ((0, source), (1, target)):
        identity = call(vm, f'mem-describe {grant}')
        assert identity[0] == channel and identity[3] == ipa
        call(vm, f'pool-bind-gpu {grant}')
        bindings.append((vm, grant))
    log = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
    assert f'permissions PASS owner={endpoints[1][1]}' in log
    if a.suite:
        result['performance_cases'] = []
        for profile in a.profiles or PERFORMANCE_PROFILES:
            command = 'performance '+profile
            buffers[1] = b''
            processes[1].stdin.write((command+'\n').encode())
            processes[1].stdin.flush()
            data = receive(1, b'XSHM_COMMAND_EXIT=', 1800)
            code = parse_command_exit(receive(1, b'\n').strip().strip(b'\r'))
            (out/(profile+'.log')).write_bytes(data)
            required = ([b'IOCTL_MATRIX_DONE failures=0'] if profile == 'ioctl' else
                        [b'COMPUTE_CHECK=PASS', b'PERF_ITER_US', b'GL_RENDERER=Mali-G610'] if profile.startswith('compute-') else
                        [b'ML_RESULT=PASS', b'ML_CHECK=PASS', b'ML_CLEAN_RESULT=PASS'] if profile in ML_PROFILES and not profile.startswith('ncnn-') else
                        [b'NCNN_RESULT=PASS', b'NCNN_MODEL_RESULT=PASS', b'NCNN_BACKEND_QUALIFICATION=PASS'] if profile.startswith('ncnn-') else
                        [b'GLMARK_RESULT=PASS', b'GLMARK_VALIDATE=PASS', b'GLMARK_CLEAN_RESULT=PASS', b'GLMARK_SCORE='])
            result['performance_cases'].append({'profile': profile, 'returncode': code,
                'pass_marker': b'PERFORMANCE_CASE_RESULT=PASS' in data and all(m in data for m in required),
                'required_markers': {m.decode(): m in data for m in required}})
            save()
            print('PERFORMANCE_CASE', profile, code, flush=True)
    else:
        glmark(1)
    log = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
    plans = re.findall(r'TASK_PLAN_STATS session=(\d+) registered=(\d+) runs=(\d+)', log)
    result['task_plans'] = {'registered': sum(int(p[1]) for p in plans),
                            'runs': sum(int(p[2]) for p in plans)}
    assert result['task_plans']['registered'] > 0
    assert result['task_plans']['runs'] > result['task_plans']['registered']
    after = [call(vm, 'irq-stats')[0] for vm in range(2)]
    assert all(after[vm] > before[vm] for vm in range(2)), 'workload did not use trusted IRQ'
    result['event_irq'] = {'before': before, 'after_workloads': after, 'intid': 127}
    for vm in (1, 0):
        call(vm, f'pool-unbind {grant}')
        bindings.remove((vm, grant))
    if a.large_pool:
        # After all GPU users/transport queues are gone, exercise every page
        # through the still-active RMM lease without poisoning fresh BO data.
        assert call(0, 'pool-fill-pages 280512')[2] == a.memory_pages
        assert call(1, f'pool-check-pages 280512 {grant}')[2] == a.memory_pages
        result['large_pool_page_check'] = {'pages': a.memory_pages, 'status': 'PASS'}
    memory_operation(1, f'mem-detach {grant}', 2)
    memory_operation(0, f'mem-revoke {grant}', 0)
    call(0, f'close {channel}')
    for vm in range(2):
        call(vm, 'unregister')


def test_memory(channel):
    size = a.memory_pages * 4096
    source = call(0, f'pool-source {size}')[0]
    target = call(1, f'pool-target {size}')[0]
    seed = 0x1122334455000000
    assert call(0, f'pool-fill-pages {seed}')[2] == a.memory_pages
    grant = memory_operation(0, f'mem-offer {channel} {source} {size}', 2)
    call(2, f'mem-attach {grant} {target}', 1)
    call(2, f'mem-revoke {grant}', 1)
    memory_operation(1, f'mem-attach {grant} {target}', 5)
    call(0, f'close {channel}', 2)
    call(1, 'unregister', 2)
    call(1, f'mem-offer {channel} {target} {size}', 1)
    # Check every page, including both sides of every 64-page SMC boundary.
    assert call(1, f'pool-check-pages {seed} {grant}')[2] == a.memory_pages
    call(1, f'pool-write {size-8} 1234567 {grant}')
    assert call(0, f'pool-read {size-8}')[2] == 1234567
    if a.transport:
        # This creates real comm platform devices using only RMM identity.
        provider = call(0, f'mem-describe {grant}')
        borrower = call(1, f'mem-describe {grant}')
        assert provider[:3] == borrower[:3]
        assert provider[0] == channel and provider[3] == source
        assert borrower[3] == target
        call(2, f'mem-describe {grant}', 1)
        call(2, f'pool-bind {grant}', -6)  # No prepared pool: ENXIO.
        for iteration in range(2):
            pending_provider = call(0, f'query {channel}')[0]
            pending_borrower = call(1, f'query {channel}')[0]
            bind = 'pool-bind-gpu' if a.gpu_flow else 'pool-bind'
            call(0, f'{bind} {grant}')
            bindings.append((0, grant))
            call(1, f'{bind} {grant}')  # Probe includes a real HELLO/ACK RPC.
            bindings.append((1, grant))
            assert call(1, f'pool-unbind-busy {grant}')[2] == 16
            assert call(0, f'pool-unbind-busy {grant} /dev/proxy_comm_vmshm')[2] == 16
            assert call(1, 'pool-info')[3] == grant
            call(0, f'mem-revoke {grant}', -16)
            call(1, f'mem-detach {grant}', -16)
            call(1, f'pool-write 0 999 {grant}', -16)
            if a.gpu_flow:
                for mode in GPU_IOCTL_MODES:
                    gpu_smoke(1, mode)
                if a.glmark_rootfs and iteration == 0:
                    glmark(1)
            # Require new publications after each fresh binding.
            assert call(0, f'query {channel}')[0] > pending_provider
            assert call(1, f'query {channel}')[0] > pending_borrower
            call(1, f'pool-unbind {grant}')
            bindings.remove((1, grant))
            call(0, f'pool-unbind {grant}')
            bindings.remove((0, grant))
        # Queue initialization consumed the control window. Restore the two
        # data probes used by the subsequent grant lifecycle checks.
        call(0, f'pool-write 0 {seed}')
        call(0, f'pool-write {size-8} 1234567')
        result['transport_check'] = 'PASS'
        if a.gpu_flow:
            result['gpu_flow_check'] = 'PASS'
        if a.glmark_rootfs:
            data = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
            plans = re.findall(r'TASK_PLAN_STATS session=(\d+) registered=(\d+) runs=(\d+)', data)
            registered = sum(int(plan[1]) for plan in plans)
            runs = sum(int(plan[2]) for plan in plans)
            assert registered > 0 and runs > registered
            result['task_plans'] = {'registered': registered, 'runs': runs}
    memory_operation(1, f'mem-detach {grant}', 2)
    memory_operation(1, f'mem-attach {grant} {target}', 5)
    assert call(1, f'pool-read {size-8} {grant}')[2] == 1234567
    memory_operation(0, f'mem-revoke {grant}', 0)
    call(1, f'mem-status {grant}', 2)
    # Reuse the same borrower IPA for a different provider's distinct DATA
    # pages. Reattaching the old grant alone cannot expose a stale PA/TLB.
    other = call(2, f'pool-source {size}')[0]
    peer = call(1, 'register')[1]
    other_channel = call(2, f'offer {peer}')[0]
    call(1, f'accept {other_channel}')
    probes = sorted({0, (a.memory_pages // 2) * 4096, size - 8})
    for offset in probes:
        call(2, f'pool-write {offset} {seed+size+offset}')
    other_grant = memory_operation(2, f'mem-offer {other_channel} {other} {size}', 2)
    memory_operation(1, f'mem-attach {other_grant} {target}', 5)
    for offset in probes:
        assert call(1, f'pool-read {offset} {other_grant}')[2] == seed+size+offset
    assert call(0, 'pool-read 0')[2] == seed
    call(0, f'mem-revoke {other_grant}', 1)
    memory_operation(1, f'mem-detach {other_grant}', 2)
    memory_operation(2, f'mem-revoke {other_grant}', 0)
    call(2, f'close {other_channel}')
    result['provider_replacement_check'] = 'PASS'
    result['memory_check'] = 'PASS'


def test_two_clients(channel, endpoints):
    size = a.memory_pages * 4096
    channels = [channel, call(0, f'offer {endpoints[2]}')[0]]
    call(2, f'accept {channels[1]}')
    sources = [call(0, f'pool-source {size}')[0] for _ in range(2)]
    assert sources[0] != sources[1]
    # Ambiguous access must not silently choose another Client's pool.
    call(0, 'pool-info', -22)
    call(0, 'pool-read 0', -22)
    active = []
    for n, vm in enumerate((1, 2)):
        target = call(vm, f'pool-target {size}')[0]
        seed = 0x3344556600000000 + n * 0x100000
        call(0, f'--pool {sources[n]} pool-fill-pages {seed}')
        grant = memory_operation(0, f'mem-offer {channels[n]} {sources[n]} {size}', 2)
        memory_operation(vm, f'mem-attach {grant} {target}', 5)
        assert call(vm, f'pool-check-pages {seed} {grant}')[2] == a.memory_pages
        # Each Client is unauthorized to inspect or attach the other grant.
        other = 3 - vm
        call(other, f'mem-describe {grant}', 1)
        call(0, f'pool-bind-gpu {grant}')
        bindings.append((0, grant))
        call(vm, f'pool-bind-gpu {grant}')
        bindings.append((vm, grant))
        active.append((vm, grant))
    result['simultaneous_client_bindings'] = 2
    # Check initialization evidence before a long workload can wrap dmesg.
    log = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
    for endpoint in endpoints[1:]:
        assert f'permissions PASS owner={endpoint}' in log, f'missing permission selftest for endpoint {endpoint}'
        assert f'GPU isolation PASS owner={endpoint}' in log, f'missing GPU lifetime selftest for endpoint {endpoint}'
    result['permission_selftests'] = 'PASS'
    modes = GPU_IOCTL_MODES + (('bo-sg-mmap',) if a.bo_sg_mmap else ())
    for mode in modes:
        command = f'gpu-smoke --{mode} /dev/dri/renderD128'
        for vm in (1, 2):
            buffers[vm] = b''
            processes[vm].stdin.write((command+'\n').encode())
            processes[vm].stdin.flush()
        for vm in (1, 2):
            text_command(vm, command, ['PANTHOR_IOCTL_SMOKE='+mode.upper().replace('-', '_')+'_PASS'], sent=True)
    if a.bo_sg_mmap:
        result['bo_sg_mmap_check'] = 'PASS'
    if a.compute_rootfs:
        for vm in (1, 2):
            buffers[vm] = b''
            processes[vm].stdin.write(b'compute\n')
            processes[vm].stdin.flush()
        for vm in (1, 2):
            data = text_command(vm, 'compute', ['COMPUTE_CHECK=PASS count=65536 samples=16',
                                'GL_RENDERER=Mali-G610'], 300, sent=True)
            assert 'alu_iters=64' in data
        result['two_client_compute_check'] = 'PASS'
    if a.gpu_fault_isolation:
        before = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
        gpu_smoke(1, 'gpuvm-fault-isolation')
        after = text_command(0, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
        prior_faults = {gpu_fault_identity(line) for line in kernel_issues(before)['gpu_translation_fault']}
        new_faults = {line for line in kernel_issues(after)['gpu_translation_fault']
                      if gpu_fault_identity(line) not in prior_faults}
        addresses = set(re.findall(r'Unhandled Page fault in AS\d+ at VA (0x[0-9A-Fa-f]+)', after)) - set(re.findall(r'Unhandled Page fault in AS\d+ at VA (0x[0-9A-Fa-f]+)', before))
        assert len({gpu_fault_identity(line) for line in new_faults}) == 1 and all('TRANSLATION_FAULT' in line for line in new_faults), new_faults
        assert {int(address, 16) for address in addresses} == {0xa00000}, addresses
        expected_gpu_fault_lines.update(gpu_fault_identity(line) for line in new_faults)
        result['expected_gpu_fault'] = {'status': 'PASS', 'address': '0xa00000', 'lines': sorted(new_faults)}
    for vm, grant in reversed(active):
        call(vm, f'pool-unbind {grant}')
        bindings.remove((vm, grant))
        call(0, f'pool-unbind {grant}')
        bindings.remove((0, grant))
        memory_operation(vm, f'mem-detach {grant}', 2)
        memory_operation(0, f'mem-revoke {grant}', 0)
    call(0, f'close {channels[1]}')
    result['two_client_gpu_flow_check'] = 'PASS'
    result['memory_check'] = 'PASS'
    result['provider_replacement_check'] = 'NOT_RUN (separate single-Client lifecycle test)'


save()
try:
    memory_plan = [realm_memory(vm) for vm in range(vm_count)]
    available_kib = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
    result['memory_plan'] = {'realm_mib': [memory[0] for memory in memory_plan],
                             'cma_mib': [memory[1] for memory in memory_plan],
                             'swiotlb_mib': realm_swiotlb_mib() if a.compact_memory else None,
                             'host_headroom_mib': 256, 'available_mib': available_kib / 1024}
    admission_mib = sum(memory[0] for memory in memory_plan)
    if a.reclaim_targets:
        vmm_digest = result['inputs'][str(bins/'bin/firecracker')]
        assert vmm_digest == 'fb2c3816d776a288d34b8c7f5b74b1e1722bb64d79079cac9c303319361310ec', vmm_digest
        admission_mib -= a.clients * a.memory_pages / 256
        result['memory_plan']['admission_basis'] = 'private configuration minus reclaimed Client target pools; bootstrap allocations guarded separately'
        result['memory_plan']['steady_private_upper_mib'] = admission_mib
    assert admission_mib + 256 <= available_kib / 1024, result['memory_plan']
    save()
    monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
    monitor_thread.start()
    if a.performance:
        prepare_performance()
    for vm in range(vm_count):
        config = {
            'boot-source': {
                'kernel_image_path': str(bins/'kernels/realm-xshm/Image'),
                'initrd_path': str(bins/'kernels/realm-xshm/initrd.cpio'),
                'boot_args': 'console=ttyS0 rdinit=/init panic=-1 loglevel=6',
            },
            'drives': [],
            'machine-config': {
                'vcpu_count': 1, 'mem_size_mib': memory_plan[vm][0],
                'realm_config': {
                    'hash_algorithm': 'SHA256',
                    'personalization_value': base64.b64encode(bytes([vm+1])*64).decode(),
                },
            },
        }
        path = out/f'realm-{vm}.json'
        if memory_plan[vm][1] is not None:
            config['boot-source']['boot_args'] += f' cma={memory_plan[vm][1]}M swiotlb={realm_swiotlb_mib() * 512}'
        if a.gpu_flow and vm == 0:
            if a.clients == 4:
                config['boot-source']['boot_args'] += ' panthor.max_inflight_jobs=3'
            config['machine-config']['gpu_passthrough'] = True
            config['boot-source']['kernel_image_path'] = str(bins/'kernels/realm-xshm/proxy/Image')
            if a.rpc_stats:
                config['boot-source']['boot_args'] += (
                    ' panthor.submit_stats=1 panthor.job_irq_stats=1 panthor_proxy.rpc_stats=1')
        if a.performance and vm:
            config['boot-source']['boot_args'] += (
                ' client_comm_vmshm.realm_poll_us=1000 client_comm_vmshm.concurrent_rpc=1'
                ' panthor_client.completed_wait_cache=1 panthor_client.fused_snapshot=1'
                ' panthor_client.lazy_snapshot_wait=1')
        if a.rpc_stats and vm:
            config['boot-source']['boot_args'] += ' client_comm_vmshm.rpc_stats=1'
        if workload_rootfs and (a.benchmark_only and vm or vm == 1 or (a.clients == 2 and vm == 2)):
            config['drives'] = [{'drive_id': 'workload', 'path_on_host': str(workload_rootfs),
                                 'is_root_device': False, 'is_read_only': True}]
        path.write_text(json.dumps(config, indent=2)+'\n')
        command = [str(bins/'bin/firecracker'), '--no-api', '--no-seccomp', '--config-file', str(path),
                   '--id', f'xshm-{vm}']
        if a.pin_cpus or a.performance:
            cpu = ('1' if vm == 0 else '2,3') if a.performance and a.benchmark_only and (a.compact_memory or a.clients > 1) else str(vm + 1 if a.performance else (1 if vm else 0))
            if vm and a.client_cpu_layout == 'round-robin':
                cpu = str(2 + (vm - 1) % 2)
            command = ['taskset', '-c', str(cpu)] + command
        env = os.environ.copy()
        if a.gpu_flow and vm == 0:
            # Explicit opt-in for the existing RK3588 trusted local GPU model.
            # This does not provide a physical SMMU/GPC isolation boundary.
            env['FC_ALLOW_TRUSTED_GPU_REALM'] = '1'
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True, env=env)
        processes.append(proc)
        buffers[vm] = b''
        files.append((out/f'realm-{vm}.log').open('wb'))
        sel.register(proc.stdout, selectors.EVENT_READ, vm)
        if not a.parallel_boot:
            receive(vm, b'XSHM_READY')
            if a.performance and a.benchmark_only and (a.compact_memory or a.clients > 1):
                isolate_vmm_io(vm)
    if a.parallel_boot:
        for vm in range(vm_count):
            receive(vm, b'XSHM_READY')
            if a.performance and a.benchmark_only and (a.compact_memory or a.clients > 1):
                isolate_vmm_io(vm)
    if a.benchmark_only:
        if a.compact_memory or a.clients > 1:
            test_concurrent_benchmark()
        else:
            test_benchmark()
    else:
        ea = call(0, 'register')
        eb = call(1, 'register')
        ec = call(2, 'register')
        assert len({ea[1], eb[1], ec[1]}) == 3
        assert ea[0] == eb[0] == ec[0] == 1
        assert all(x[2] & 3 == 3 for x in (ea, eb, ec))
        if a.trusted_events:
            assert all(x[2] & 16 for x in (ea, eb, ec)), 'RMM IRQ capability missing'
            for vm in range(3):
                assert call(vm, 'irq-bind')[0] == 127
            irq_before = [call(vm, 'irq-stats')[0] for vm in range(3)]
        channel = call(0, f'offer {eb[1]}')[0]
        call(2, f'accept {channel}', 1)
        call(0, f'accept {channel}', 1)
        call(0, f'notify {channel}', 2)
        call(1, f'accept {channel}')
        for operation in ('query', 'notify', 'close', 'ack'):
            call(2, f'{operation} {channel}'+(' 0' if operation == 'ack' else ''), 1)
        if a.trusted_events:
            assert [call(vm, 'irq-stats')[0] for vm in range(3)] == irq_before, 'unauthorized event injected an IRQ'
        call(1, f'arm {channel} 0')
        wake = call(0, f'notify {channel}')
        assert wake[:3] == [1, eb[1], 1]
        wake = call(0, f'notify {channel}')
        assert wake[:3] == [2, eb[1], 0]
        if a.trusted_events:
            irq_after = [call(vm, 'irq-stats')[0] for vm in range(3)]
            assert irq_after == [irq_before[0], irq_before[1] + 1, irq_before[2]], 'IRQ ownership/coalescing failure'
            result['event_irq'] = {'before': irq_before, 'after_two_notifications': irq_after,
                                   'intid': 127, 'negative_and_coalescing': 'PASS'}
        state = call(1, f'query {channel}')
        assert state[:2] == [2, 0]
        call(1, f'ack {channel} 3', 1)
        call(1, f'arm {channel} 2', 1)
        call(1, f'ack {channel} 1')
        assert call(1, f'arm {channel} 1')[2] & 2 == 0
        call(1, f'ack {channel} 2')
        assert call(1, f'arm {channel} 2')[2] & 2
        if a.memory_pages:
            if a.clients == 2:
                test_two_clients(channel, [ea[1], eb[1], ec[1]])
            else:
                test_memory(channel)
        if a.trusted_events:
            result['event_irq']['after_workloads'] = [call(vm, 'irq-stats')[0] for vm in range(3)]
            for vm in range(2 if a.clients == 1 else 3):
                if a.transport:
                    assert result['event_irq']['after_workloads'][vm] > irq_after[vm], 'workload did not use event IRQ'
        call(0, f'close {channel}')
        call(0, f'notify {channel}', 2)
        call(1, 'unregister')
        replacement = call(1, 'register')[1]
        assert replacement != eb[1]
        call(0, f'offer {eb[1]}', 1)
        new_channel = call(0, f'offer {replacement}')[0]
        assert new_channel != channel
        call(1, f'accept {new_channel}')
        assert call(1, f'query {new_channel}')[:2] == [0, 0]
        call(1, f'close {new_channel}')
        for vm in range(3):
            call(vm, 'unregister')
    if a.gpu_flow:
        result['kernel_health'] = {}
        for vm in range(vm_count):
            log = text_command(vm, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
            # Errors/warnings are also printed on the serial console;
            # retain these even if the kernel ring wrapped during the suite.
            files[vm].flush()
            serial = (out/f'realm-{vm}.log').read_text(errors='replace')
            issues = kernel_issues(log+'\n'+serial)
            if vm == 0 and expected_gpu_fault_lines:
                issues['gpu_translation_fault'] = [line for line in issues['gpu_translation_fault']
                    if gpu_fault_identity(line) not in expected_gpu_fault_lines]
            result['kernel_health'][str(vm)] = issues
            assert not any(issues.values()), f'Realm {vm}: kernel faults: '+str(
                {name: len(lines) for name, lines in issues.items() if lines})
    result['status'] = ('FAIL' if any(c['returncode'] or not c['pass_marker'] for c in result.get('performance_cases', [])) or
                        any(case['status'] != 'PASS' for case in result.get('concurrent_ml', [])) else 'PASS')
except (Exception, KeyboardInterrupt) as exc:
    result['status'] = 'FAIL'
    result['error'] = str(exc) or type(exc).__name__
    for vm, process in enumerate(processes):
        if process.poll() is not None:
            continue
        try:
            failure_log = text_command(vm, 'kernel-log', ['XSHM_KERNEL_LOG_END'], 15)
            (out/f'failure-kernel-{vm}.log').write_text(failure_log)
        except Exception as diagnostic_error:
            result.setdefault('failure_log_errors', []).append(str(diagnostic_error))
finally:
    for vm, grant in reversed(bindings):
        try:
            call(vm, f'pool-unbind {grant}')
        except Exception as exc:
            result.setdefault('transport_cleanup_errors', []).append(str(exc))
    # Drop only grants created by this test before terminating their Realms.
    for provider, grant in list(grants):
        try:
            memory_operation(provider, f'mem-revoke {grant}', 0)
        except Exception as exc:
            result.setdefault('grant_cleanup_errors', []).append(str(exc))
    # Touch only processes created by this invocation.
    for proc in reversed(processes):
        if proc.poll() is None:
            try:
                proc.stdin.write(b'halt\n')
                proc.stdin.flush()
                proc.wait(timeout=10)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    result['vm_exit_codes'] = [proc.returncode for proc in processes]
    try:
        restore_performance()
    except Exception as exc:
        result['status'] = 'FAIL'
        result['host_restore_error'] = str(exc)
    monitor_stop.set()
    if monitor_thread is not None:
        monitor_thread.join(timeout=5)
    if result['status'] == 'PASS' and any(code != 0 for code in result['vm_exit_codes']):
        result['status'] = 'FAIL'
        result['error'] = 'Realm did not shut down cleanly'
    for stream in files:
        stream.close()
    sel.close()
    command_log.close()
    save()
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
