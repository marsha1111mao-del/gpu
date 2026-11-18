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

PERFORMANCE_PROFILES = ('glmark-720', 'glmark-1080')
ML_PROFILES = ('ml-all', 'attention-320', 'ncnn-mobilenet_v2',
               'ncnn-mobilenet_v3', 'ncnn-resnet50', 'ml-gemm', 'ml-conv',
               'ml-depthwise', 'ml-reduction', 'ml-softmax', 'ml-attention')

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--run-id', required=True)
p.add_argument('--memory-pages', type=int, default=0)
p.add_argument('--profiles', nargs='+', choices=tuple(dict.fromkeys(PERFORMANCE_PROFILES + ML_PROFILES)), help='Explicit subset of --suite; omitted cases are not tested')
p.add_argument('--trusted-events', action='store_true', help='Require RMM-owned actual virtual IRQ delivery and negative/coalescing checks')
p.add_argument('--transport', action='store_true', help='Bind the RMM pool to real kernel control queues')
p.add_argument('--parallel-boot', action='store_true', help='Exercise concurrent Host Realm population')
p.add_argument('--gpu-flow', action='store_true', help='Assign GPU to provider and exercise Client DRM over the RMM pool')
p.add_argument('--session-quota', type=int, default=0, help='Check the actual per-Client DRM session limit before the workload')
p.add_argument('--security-selftests', action='store_true', help='Run Client-owned RMM group/observation boundary checks before the workload')
p.add_argument('--glmark-rootfs', type=Path, help='Read-only prepared Panfrost rootfs for the complete glmark suite')
p.add_argument('--compute-rootfs', type=Path, help='Read-only rootfs for concurrent actual compute in two Clients')
p.add_argument('--clients', type=int, choices=(1, 2, 3, 4), default=1)
p.add_argument('--pin-cpus', action='store_true', help='Explicit RK CPU 0 Proxy / CPU 1 active Client placement')
p.add_argument('--performance', action='store_true', help='600 MHz OPP, separate CPUs, concurrent RPC and bounded Client reply polling')
p.add_argument('--notify-trace', action='store_true', help='Record bounded RMM/notification/receive physical-counter samples')
p.add_argument('--benchmark-only', action='store_true', help='Two Realms and full glmark; defer the broader lifecycle/API suite')
p.add_argument('--suite', action='store_true', help='Run selected full glmark or ML/NCNN profiles')
p.add_argument('--rpc-stats', action='store_true', help='Report current Client/Proxy RPC transport timing (adds overhead)')
p.add_argument('--client-cpu-layout', choices=('shared', 'round-robin'), default='shared')
p.add_argument('--cpu-frequency-khz', type=int, help='Lock Host CPU policy0 for a controlled performance comparison')
p.add_argument('--root', type=Path, default=Path('/root/GPU-SFTP'))
a = p.parse_args()
# Versioned together with the only supported private Client/Proxy protocol.
SHARED_GPU_ABI = 6
if a.profiles and not a.suite:
    p.error('--profiles requires --suite')
if not a.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run_id):
    p.error('invalid run-id')
bins = a.root/'firecracker-bins'
out = a.root/'log/realm-xshm'/a.run_id
if not 0 <= a.memory_pages <= 65536:
    p.error('memory-pages exceeds the bounded control/transport pool')
if a.transport and a.memory_pages < 256:
    p.error('--transport requires at least 256 memory pages')
if a.gpu_flow and (not a.transport or not a.trusted_events or a.memory_pages < 1025):
    p.error('--gpu-flow requires --transport --trusted-events and at least 1025 control pages')
if not 0 <= a.session_quota <= 64 or (a.session_quota and not a.gpu_flow):
    p.error('--session-quota requires GPU flow and a limit between 1 and 64')
if a.security_selftests and not a.gpu_flow:
    p.error('--security-selftests requires GPU flow')
if a.glmark_rootfs and not a.gpu_flow:
    p.error('--glmark-rootfs requires --gpu-flow')
if a.compute_rootfs and (not a.gpu_flow or a.clients != 2):
    p.error('--compute-rootfs requires --gpu-flow --clients 2')
if a.glmark_rootfs and a.compute_rootfs:
    p.error('select only one workload rootfs')
if a.clients > 1 and (not a.gpu_flow or (not a.benchmark_only and a.clients != 2)):
    p.error('multiple Clients require GPU flow and either benchmark-only or the two-Client compute suite')
if a.suite and not a.benchmark_only:
    p.error('--suite requires --benchmark-only')
if a.benchmark_only and not a.glmark_rootfs:
    p.error('--benchmark-only requires --glmark-rootfs')
if a.performance and not a.gpu_flow:
    p.error('--performance requires --gpu-flow')
if a.suite and (not a.profiles or not (
        a.profiles in (['glmark-720'], ['glmark-1080']) or
        all(profile in ML_PROFILES for profile in a.profiles))):
    p.error('GPU suite requires one full glmark profile or explicit ML profiles')
if a.benchmark_only and a.clients > 1 and not a.suite:
    p.error('concurrent benchmarks require an explicit suite')
if a.client_cpu_layout != 'shared' and not (
        a.performance and a.benchmark_only and a.suite and a.profiles and
        (a.profiles in (['glmark-720'], ['glmark-1080']) or
         all(profile in ML_PROFILES for profile in a.profiles))):
    p.error('controlled CPU placement requires a private GPU performance suite')
if a.cpu_frequency_khz is not None and not (
        a.cpu_frequency_khz > 0 and a.performance and a.benchmark_only and
        a.profiles in (['glmark-720'], ['glmark-1080'])):
    p.error('controlled CPU frequency requires a full glmark performance run')
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
          'rpc_stats': a.rpc_stats,
          'notify_trace': a.notify_trace,
          'suite': a.suite, 'shared_gpu_abi': SHARED_GPU_ABI,
          'profiles': a.profiles}
result['client_cpu_layout'] = a.client_cpu_layout
result['cpu_frequency_khz'] = a.cpu_frequency_khz
result['private_gpu'] = {'enabled': a.gpu_flow, 'bootstrap': 'NOT_RUN',
                         'drm_probes': {}, 'shared_data_fallback': False,
                         'gpu_completion_eventfd': 'NOT_RUN',
                         'isolation_attacks': 'NOT_RUN', 'dynamic_tiler_growth': 'NOT_VERIFIED'}
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
    if a.gpu_flow:
        # Only RPC/control pools use CMA. Private BOs and the donated arena
        # use ordinary alloc_page backing, so shared-mode CMA sizing cannot
        # be used as their memory budget. These are admission estimates, not
        # runtime reservations or guarantees that a workload fits.
        if vm > a.clients:
            return 256, 16  # Unbound outsider in the three-Realm suite.
        control_mib = (a.memory_pages + 255) // 256
        cma_mib = control_mib * (a.clients if vm == 0 else 1) + 16
        # CMA uses 4 MiB allocation alignment on this 4 KiB-page kernel.
        # Round up without borrowing from the ordinary/private data budget.
        cma_mib = (cma_mib + 3) & ~3
        ordinary_mib = (208 + 32 * a.clients if vm == 0 else
                        192 + (384 if 'ncnn-resnet50' in (a.profiles or []) else 256))
        # Firecracker's Realm FDT requires a 2 MiB-aligned memory size.
        return (cma_mib + ordinary_mib + 1) & ~1, cma_mib
    return 512, None



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


def gpu_mode_boot_args(vm):
    if not a.gpu_flow:
        return ''
    return '' if vm else ' panthor.rmm_service=1'


def bootstrap_private_gpu():
    # Actual driver parameters catch old Images which ignore unknown boot
    # args. Bootstrap independently requires RMM-observed MMIO handoff and
    # fixed firmware verification. No retry/reset on partial failure.
    for vm in range(vm_count):
        role = 'client' if vm else 'proxy'
        text_command(vm, f'gpu-private mode-check {role}',
                     [f'GPU_PRIVATE_MODE=PASS role={role}'])
    result['private_gpu']['bootstrap'] = 'ATTEMPTED'
    save()
    text_command(0, 'gpu-private service-bootstrap /mali_csffw.bin',
                 ['GPU_RMM_SERVICE_BOOTSTRAP=CONFIGURED'], 300)
    result['private_gpu']['bootstrap'] = 'CONFIGURED'
    save()


def test_private_event_irq(endpoints):
    """Force armed events independently of RPC polling and GPU completion."""
    checks = []
    for client in range(1, a.clients + 1):
        channel = call(0, f'offer {endpoints[client][1]}')[0]
        call(client, f'accept {channel}')
        for sender, receiver in ((0, client), (client, 0)):
            before = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
            call(receiver, f'arm {channel} 0')
            for outsider in range(vm_count):
                if outsider not in (sender, receiver):
                    call(outsider, f'notify {channel}', 1)
            denied = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
            assert denied == before, 'unauthorized private control event injected IRQ'
            first = call(sender, f'notify {channel}')
            second = call(sender, f'notify {channel}')
            assert first[:3] == [1, endpoints[receiver][1], 1], first
            assert second[:3] == [2, endpoints[receiver][1], 0], second
            after = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
            expected = before.copy()
            expected[receiver] += 1
            assert after == expected, 'private control IRQ missing, misrouted or not coalesced'
            assert call(receiver, f'query {channel}')[:2] == [2, 0]
            call(receiver, f'ack {channel} 2')
            checks.append({'sender': sender, 'receiver': receiver, 'before': before,
                           'after_two_notifications': after, 'outsider_denied': True})
        call(0, f'close {channel}')
    result['event_irq'] = {'intid': 127, 'controlled_armed_events': checks,
                           'negative_and_coalescing': 'PASS',
                           'scope': 'Realm control notification; not physical GPU completion IRQ'}
    save()


def test_private_gpu():
    """Exercise private data through ordinary DRM; pools carry RPC control only."""
    endpoints = [call(vm, 'register') for vm in range(vm_count)]
    assert len({endpoint[1] for endpoint in endpoints}) == vm_count
    assert all(endpoint[2] & 16 for endpoint in endpoints)
    for vm in range(vm_count):
        assert call(vm, 'irq-bind')[0] == 127
    # Exercise real armed delivery before timing. A short benchmark can
    # legally complete all RPCs in the bounded poll path without new IRQs.
    test_private_event_irq(endpoints)
    before = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
    active = []
    size = a.memory_pages * 4096
    for vm in range(1, a.clients + 1):
        channel = call(0, f'offer {endpoints[vm][1]}')[0]
        call(vm, f'accept {channel}')
        source = call(0, f'pool-source {size}')[0]
        target = call(vm, f'pool-target {size}')[0]
        grant = memory_operation(0, f'mem-offer {channel} {source} {size}', 2)
        memory_operation(vm, f'mem-attach {grant} {target}', 5)
        for other in range(1, vm_count):
            if other != vm:
                call(other, f'mem-describe {grant}', 1)
        for member in (0, vm):
            call(member, f'pool-bind {grant}')
            bindings.append((member, grant))
        active.append((vm, channel, grant))
    result['private_gpu']['control_pool_bytes_per_client'] = size
    result['simultaneous_client_bindings'] = a.clients
    save()
    for vm, channel, grant in active:
        if a.session_quota:
            text_command(vm, f'session-quota {a.session_quota}',
                         [f'GPU_PROXY_SESSION_QUOTA=PASS limit={a.session_quota}'], 180)
        if a.security_selftests:
            text_command(vm, f'gpu-private group-selftest {channel} 2',
                         ['GPU_GROUP_MEMORY=PASS', 'GPU_TASK_OBSERVATION=PASS',
                          'GPU_IRQ_SECURITY_SELFTEST=PASS'], 300)
    def irq_status():
        vm, channel, _ = active[0]
        text = text_command(vm, f'gpu-private irq-status {channel}', ['GPU_IRQ_STATUS='])
        match = re.search(r'GPU_IRQ_STATUS=(\{[^\r\n]+\})', text)
        assert match, 'RMM IRQ status missing'
        return json.loads(match[1])
    irq_before = irq_status()
    result['gpu_irq_security'] = {'before': irq_before,
                                  'simulation_selftest': a.security_selftests}
    result['private_gpu']['session_quota'] = a.session_quota or 'NOT_RUN'
    result['private_gpu']['observation_selftests'] = 'PASS' if a.security_selftests else 'NOT_RUN'
    save()
    if a.benchmark_only:
        if a.profiles and all(profile in ML_PROFILES for profile in a.profiles):
            run_concurrent_ml()
        elif a.suite:
            run_concurrent_glmark()
        else:
            glmark(1)
        # The optimization admission threshold is a single-Client baseline
        # requirement. Concurrent Clients share GPU/CPU resources; their
        # valid per-Client scores must not each be required to exceed 1000.
        if a.clients == 1 and (a.profiles == ['glmark-720'] or not a.suite):
            scores = ([item['score'] for item in result['concurrent_glmark']]
                      if a.suite else [result['glmark']['score']])
            result['private_gpu']['glmark_720_gate'] = {
                'threshold': 1000, 'scores': scores,
                'status': 'PASS' if all(score >= 1000 for score in scores) else 'FAIL'}
            save()
    else:
        for vm in range(1, a.clients + 1):
            text_command(vm, 'gpu-private drm-selftest', ['GPU_PRIVATE_DRM=PASS'], 300)
            text_command(vm, 'gpu-private drm-submit-selftest', ['GPU_PRIVATE_DRM_SUBMIT=PASS'], 300)
            result['private_gpu']['drm_probes'][str(vm)] = 'PASS'
            save()
        if a.compute_rootfs:
            result['private_gpu']['gpu_completion_eventfd'] = 'ATTEMPTED'
            save()
            for vm in range(1, a.clients + 1):
                buffers[vm] = b''
                processes[vm].stdin.write(b'compute-eventfd\n')
                processes[vm].stdin.flush()
            for vm in range(1, a.clients + 1):
                data = text_command(vm, 'compute-eventfd', ['COMPUTE_CHECK=PASS count=65536 samples=16',
                                    'GPU_COMPLETION_EVENTFD=PASS iterations=4 values_per_iteration=65536 binary=1 timeline=1 source=PRIVATE_GPU_SYNC_FILE',
                                    'GL_RENDERER=Mali-G610'], 300, sent=True)
                assert 'alu_iters=64' in data
            result['private_gpu']['gpu_completion_eventfd'] = 'PASS'
            result['two_client_compute_check'] = 'PASS'
        if a.glmark_rootfs:
            glmark(1)
    irq_after = irq_status()
    result['gpu_irq_security']['after'] = irq_after
    result['gpu_irq_security']['provenance'] = (
        'EL3_PHYSICAL_IRQ' if irq_after['physical'] > irq_before['physical'] else
        'ROOT_DEVICE_SAMPLING' if irq_after['root_samples'] > irq_before['root_samples'] else
        'NO_DEVICE_EVENT')
    assert not irq_after['lost'], 'Monitor/RMM event history incomplete'
    assert irq_after['overflows'] == irq_before['overflows'], 'new event overflow during workload'
    assert result['gpu_irq_security']['provenance'] != 'NO_DEVICE_EVENT', 'GPU workload has no trusted device events'
    assert irq_after['claims'] > irq_before['claims'], 'Proxy made no accepted event statements'
    save()
    gate = result['private_gpu'].get('glmark_720_gate')
    if gate:
        assert gate['status'] == 'PASS', 'private full-720p score below 1000'
    after = [call(vm, 'irq-stats')[0] for vm in range(vm_count)]
    # Require delivery/ownership/coalescing in the controlled test above;
    # incidental workload traffic may finish without ever arming an IRQ.
    result['event_irq'].update(before=before, after_workloads=after)
    save()
    for vm, channel, grant in reversed(active):
        for member in (vm, 0):
            call(member, f'pool-unbind {grant}')
            bindings.remove((member, grant))
        memory_operation(vm, f'mem-detach {grant}', 2)
        memory_operation(0, f'mem-revoke {grant}', 0)
        call(0, f'close {channel}')
    for vm in range(vm_count):
        call(vm, 'unregister')
    result['private_gpu']['control_transport_cleanup'] = 'PASS'
    # GPU arena retirement and dead-Realm cleanup are separate obligations;
    # successful pool teardown is not proof of whole-device reclamation.
    result['private_gpu']['trusted_device_reclamation'] = 'NOT_VERIFIED'


def kernel_issues(log):
    patterns = {
        'csg_update_timeout': r'CSG \d+ update request timedout',
        'fw_ping_timeout': r'FW ping timeout',
        'gpu_translation_fault': r'(?:TRANSLATION_FAULT|translation fault|Translation fault)',
        'kernel_warning': r'WARNING:',
        'kernel_oops': r'Oops:',
        'kernel_panic': r'Kernel panic',
        'rcu_stall': r'rcu:.*(?:detected.*stall|kthread.*starved|timer wakeup didn.t happen)',
        'cpu_lockup': r'(?i)(?:soft lockup|hard lockup)',
        'hung_task': r'INFO: task .* blocked for more than',
        'out_of_memory': r'(?:Out of memory|invoked oom-killer|oom-kill:)',
    }
    lines = re.split(r'[\r\n]', log)
    return {name: sorted({line for line in lines if re.search(pattern, line)})
            for name, pattern in patterns.items()}






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




def run_concurrent_glmark():
    profile = a.profiles[0]
    command = f'performance {profile}-barrier'
    result['concurrent_glmark'] = []
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
            bind = 'pool-bind'
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




save()
try:
    memory_plan = [realm_memory(vm) for vm in range(vm_count)]
    available_kib = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
    result['memory_plan'] = {'realm_mib': [memory[0] for memory in memory_plan],
                             'cma_mib': [memory[1] for memory in memory_plan],
                             'swiotlb_mib': 16 if a.gpu_flow else None,
                             'host_headroom_mib': 256, 'available_mib': available_kib / 1024}
    admission_mib = sum(memory[0] for memory in memory_plan)
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
            config['boot-source']['boot_args'] += f' cma={memory_plan[vm][1]}M swiotlb={16 * 512}'
        config['boot-source']['boot_args'] += gpu_mode_boot_args(vm)
        if a.gpu_flow and vm == 0:
            if a.clients == 4:
                config['boot-source']['boot_args'] += ' panthor.max_inflight_jobs=3'
            config['machine-config']['gpu_passthrough'] = True
            config['boot-source']['kernel_image_path'] = str(bins/'kernels/realm-xshm/proxy/Image')
            if a.rpc_stats:
                config['boot-source']['boot_args'] += (
                    ' panthor_proxy.rpc_stats=1')
        if a.performance and vm:
            config['boot-source']['boot_args'] += (
                ' client_comm_vmshm.realm_poll_us=1000 client_comm_vmshm.concurrent_rpc=1')
        if a.notify_trace:
            config['boot-source']['boot_args'] += ' realm_xshm.notify_trace=1'
        if a.rpc_stats and vm:
            config['boot-source']['boot_args'] += ' client_comm_vmshm.rpc_stats=1'
        if a.security_selftests and vm == 0:
            config['boot-source']['boot_args'] += ' panthor_proxy.irq_probe=1'
        if workload_rootfs and (a.benchmark_only and vm or vm == 1 or (a.clients == 2 and vm == 2)):
            config['drives'] = [{'drive_id': 'workload', 'path_on_host': str(workload_rootfs),
                                 'is_root_device': False, 'is_read_only': True}]
        path.write_text(json.dumps(config, indent=2)+'\n')
        command = [str(bins/'bin/firecracker'), '--no-api', '--no-seccomp', '--config-file', str(path),
                   '--id', f'xshm-{vm}']
        if a.pin_cpus or a.performance:
            cpu = ('1' if vm == 0 else '2,3') if a.performance and a.benchmark_only and a.clients > 1 else str(vm + 1 if a.performance else (1 if vm else 0))
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
            if a.performance and a.benchmark_only and a.clients > 1:
                isolate_vmm_io(vm)
    if a.parallel_boot:
        for vm in range(vm_count):
            receive(vm, b'XSHM_READY')
            if a.performance and a.benchmark_only and a.clients > 1:
                isolate_vmm_io(vm)
    if a.notify_trace:
        for vm in range(vm_count):
            assert call(vm, 'register')[2] & 64, 'RMM notification timing capability missing'
    if a.gpu_flow:
        bootstrap_private_gpu()
        test_private_gpu()
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
        if a.notify_trace:
            call(0, f'notify-timed {channel}', 2)
        call(1, f'accept {channel}')
        for operation in ('query', 'notify', 'close', 'ack'):
            call(2, f'{operation} {channel}'+(' 0' if operation == 'ack' else ''), 1)
        if a.notify_trace:
            call(2, f'notify-timed {channel}', 1)
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
        if a.notify_trace:
            timed = call(0, f'notify-timed {channel}')
            assert 0 < timed[0] <= timed[1] <= timed[2]
            assert timed[3] >> 32 > 0 and timed[3] & 1
            assert call(1, f'query {channel}')[:2] == [3, 2]
            coalesced = call(0, f'notify-timed {channel}')
            assert 0 < coalesced[0] <= coalesced[1] <= coalesced[2]
            assert coalesced[3] >> 32 == timed[3] >> 32
            assert coalesced[3] & 1 == 0
            assert call(1, f'query {channel}')[:2] == [4, 2]
            call(1, f'ack {channel} 4')
            assert call(1, f'arm {channel} 4')[2] & 2
            result['timed_notify_abi'] = {'status': 'PASS', 'armed': timed,
                                          'coalesced': coalesced,
                                          'inactive_and_outsider_denied': True}
        if a.memory_pages:
            test_memory(channel)
        if a.trusted_events:
            result['event_irq']['after_workloads'] = [call(vm, 'irq-stats')[0] for vm in range(3)]
            for vm in range(2 if a.clients == 1 else 3):
                if a.transport:
                    assert result['event_irq']['after_workloads'][vm] > irq_after[vm], 'workload did not use event IRQ'
        call(0, f'close {channel}')
        call(0, f'notify {channel}', 2)
        if a.notify_trace:
            call(0, f'notify-timed {channel}', 2)
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
    if a.notify_trace:
        for vm in range(vm_count):
            trace = text_command(vm, 'notify-trace', ['XSHM_NOTIFY_TRACE_END'])
            (out/f'notify-realm-{vm}.log').write_text(trace)
    if a.gpu_flow:
        result['kernel_health'] = {}
        for vm in range(vm_count):
            log = text_command(vm, 'kernel-log', ['XSHM_KERNEL_LOG_END'])
            # Errors/warnings are also printed on the serial console;
            # retain these even if the kernel ring wrapped during the suite.
            files[vm].flush()
            serial = (out/f'realm-{vm}.log').read_text(errors='replace')
            if vm == 0 and a.security_selftests:
                assert 'GPU_IRQ_PROXY_STATEMENT=PASS' in log+serial, 'Proxy event statement probes not executed'
                assert 'GPU_IRQ_PROXY_STATEMENT=FAIL' not in log+serial, 'Proxy event statement probe failed'
                result['gpu_irq_security']['proxy_statement_probes'] = 'PASS'
            issues = kernel_issues(log+'\n'+serial)
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
            failure_log = text_command(vm, 'kernel-log', ['XSHM_KERNEL_LOG_END'], 120)
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
