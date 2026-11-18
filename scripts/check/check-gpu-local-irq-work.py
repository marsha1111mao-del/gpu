#!/usr/bin/env python3
"""Exercise actual Client IRQ-work and chain bodies with modeled CPU/IRQ/RCU.

The four compiled mutants must be rejected. This is not real concurrency,
GPU completion, SGI timing or physical-isolation evidence.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
out = p.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=False)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
fixtures = ROOT / 'GPU-SFTP/tests/gpu-local-irq-work'
guest = ROOT / 'Linux-Guest-GPU'
irq = (guest / 'kernel/irq_work.c').read_text()
header = (guest / 'include/linux/irq_work.h').read_text()
chain = (guest / 'drivers/dma-buf/dma-fence-chain.c').read_text()
def function(text, signature):
    match = re.search(r'(?m)^' + re.escape(signature) + r'[^;]*?\n\{', text)
    assert match, signature
    return text[match.start():text.index('\n}', match.end()) + 2]
def once_pattern(text, pattern, replacement):
    assert len(re.findall(pattern, text)) == 1, pattern
    return re.sub(pattern, lambda _: replacement, text, count=1)
prefix = (fixtures / 'core-prefix.inc').read_text()
start = header.index('#define IRQ_WORK_LOCAL_BATCH_BUDGET ')
end = header.index('\n', header.index('bool irq_work_queue_local_batch(', start))
prefix += header[start:end] + '\n'
native = '\n'.join(function(irq, name) for name in [
    'static bool irq_work_claim(', 'static __always_inline void irq_work_raise(',
    'static void __irq_work_queue_local(', 'bool irq_work_queue(', 'void irq_work_single('])
native = native.replace('static __always_inline', 'static inline')
start = irq.index('static DEFINE_PER_CPU(struct irq_work_local_batch *, local_completion_batch);')
implementation = irq[start:irq.index('static void irq_work_run_list(', start)]
def normalized_enum(text):
    enum = re.search(r'enum \{.*?\n\};', text, re.S)[0]
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/', '', enum, flags=re.S)).replace(',};', '};')
assert normalized_enum((guest / 'include/linux/smp_types.h').read_text()) == normalized_enum(prefix)
variants = {
    'candidate': implementation,
    'drop-spill': once_pattern(implementation, r'__irq_work_queue_local\(work\);', '(void)work;'),
    'no-owner-gate': once_pattern(implementation, r'!batch\s*\|\|\s*batch->owner\s*!=\s*current', '!batch'),
    'no-RCU': once_pattern(implementation, r'\brcu_read_lock\(\);', ''),
    'leak-scope': once_pattern(implementation, r'__this_cpu_write\(local_completion_batch,\s*NULL\);', ''),
}
records = []
def run(name, code, reject=False):
    case = out / name
    case.mkdir()
    (case / 'test.c').write_text(code)
    command = [os.environ.get('HOST_CC', 'cc'), '-std=gnu11', '-O2', '-Wall', '-Wextra',
        '-Werror', '-fno-strict-aliasing', '-g', '-fsanitize=address,undefined',
        '-fno-pie', '-no-pie', str(case / 'test.c'), '-o', str(case / 'test')]
    with (case / 'build.log').open('w') as log:
        built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert built.returncode == 0, case / 'build.log'
    with (case / 'run.log').open('w') as log:
        ran = subprocess.run([str(case / 'test')], stdout=log, stderr=subprocess.STDOUT, timeout=60)
    message = (case / 'run.log').read_text()
    if reject:
        assert ran.returncode != 0 and ('Assertion' in message or 'AddressSanitizer' in message), name
    else:
        assert ran.returncode == 0 and '=PASS' in message, name
    records.append({'name': name, 'command': command, 'build_exit': 0,
                    'run_exit': ran.returncode, 'expected_reject': reject})
core_cases = (fixtures / 'core-cases.inc').read_text()
for name, body in variants.items():
    run(name, prefix + native + '\n' + body + core_cases, name != 'candidate')
actual_chain = '\n'.join(function(chain, name) for name in [
    'static void dma_fence_chain_irq_work(', 'static void dma_fence_chain_cb(',
    'static bool dma_fence_chain_enable_signaling('])
run('chain', prefix + native + '\n' + implementation +
    (fixtures / 'chain-types.inc').read_text() + actual_chain + '\n' +
    function(core_cases, 'static void pump(') + (fixtures / 'chain-cases.inc').read_text())
sources = [Path(__file__), guest / 'kernel/irq_work.c', guest / 'include/linux/irq_work.h',
           guest / 'include/linux/smp_types.h', guest / 'drivers/dma-buf/dma-fence-chain.c', *sorted(fixtures.glob('*.inc'))]
result = {'status': 'PASS_LOCAL_IRQ_WORK_ACTUAL_CORE_CHAIN_MODELS', 'commands': records,
    'compiled_mutants_rejected': 4,
    'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    'scope': 'Actual claim/queue/single/local batch plus native chain callback/enable/rearm; '
             'modeled atomic/CPU/IRQ/RCU/fence primitives. Covers ownership, repeat/requeue, '
             'fallback, RCU self-free, reference graph, errors and 100-node graph with 64-node spill. '
             'No hardware, timing, whole-worker or physical-isolation proof.'}
(out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(result['status'])
