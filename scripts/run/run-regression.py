#!/usr/bin/env python3
"""Run the supported ordinary-VM GPU regression matrix, with durable evidence."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-prepared", action="store_true",
                        help="Reuse an already synced runtime and rootfs on the RK3588")
    parser.add_argument("--quick", action="store_true",
                        help="Use short compute/ML loops and one glmark scene")
    parser.add_argument("--passthrough", action="store_true",
                        help="Also switch the host driver and run Host vs passthrough")
    parser.add_argument("--run-id", default="release-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run_id):
        parser.error("run-id must contain only letters, digits, '-' and '_'")
    env = os.environ.copy()
    host = env.get("REMOTE_HOST", "192.168.31.18")
    user = env.get("REMOTE_USER", "root")
    env["SSHPASS"] = env.get("REMOTE_PASS", "root")
    remote_root = env.get("REMOTE_ROOT", "/root/GPU-SFTP")
    remote_bins = remote_root + "/firecracker-bins"
    ssh = ["sshpass", "-e", "ssh", "-o", "ConnectTimeout=10",
           "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=6",
           "-o", "StrictHostKeyChecking=accept-new", f"{user}@{host}"]
    out = ROOT / "GPU-SFTP/log/regression" / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    rows = []

    def run(name, command, extra=None):
        print(f"START {name}", flush=True)
        case_env = env.copy()
        case_env["RUN_ID"] = args.run_id + "-" + name
        case_env.update(extra or {})
        with (out / f"{name}.log").open("w") as stream:
            result = subprocess.run(command, cwd=ROOT, env=case_env,
                                    stdout=stream, stderr=subprocess.STDOUT)
        rows.append({"name": name, "returncode": result.returncode,
                     "run_id": case_env["RUN_ID"], "log": f"{name}.log"})
        (out / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {name}", flush=True)
        if result.returncode:
            print(f"Stopped; inspect {out / (name + '.log')}", file=sys.stderr)
            raise SystemExit(1)

    run("preflight", ssh + [
        "set -eu; test -c /dev/kvm; test -c /dev/pmthor; "
        "test \"$(basename \"$(readlink -f /sys/bus/platform/devices/fb000000.gpu/driver)\")\" = pmthor; "
        "! pgrep -x firecracker; ! pgrep -x vmshm-broker; uname -a; "
        "cat /sys/devices/system/cpu/online"
    ])
    first = True

    def single(name, flags, extra=None):
        nonlocal first
        command = ["bash", "scripts/run/run-vmshm-e2e.sh", "--skip-build", *flags]
        if args.remote_prepared or not first:
            command += ["--skip-sync"]
        else:
            command += ["--sync-rootfs"]
        run(name, command, extra)
        first = False

    ioctl_modes = [
        "ioctl", "vm-create", "bo-create", "bo-lifecycle", "bo-mmap",
        "vm-bind", "vm-bind-async-sync", "vm-state-flush",
        "syncobj-lifecycle", "syncobj-wait", "syncobj-transfer",
        "syncobj-timeline-wait", "syncobj-signal-query", "sync-file-snapshot",
        "group-lifecycle", "group-submit-syncpoint", "tiler-heap-lifecycle",
    ]
    for mode in ioctl_modes:
        single(mode, [f"--{mode}-smoke"])
    # At this point the first launch has synced the prepared payload as needed.
    run("pfn-lifetime", ssh + [
        f"timeout 35 {shlex.quote(remote_bins + '/bin/pmthor-pfn-lifetime')}; "
        "status=$?; dmesg; exit \"$status\""
    ])
    run("pfn-log-check", [sys.executable,
                         "GPU-SFTP/tests/pmthor-pfn-lifetime/check_kernel_log.py",
                         str(out / "pfn-lifetime.log")])
    measured, warmup = (5, 2) if args.quick else (100, 5)
    common = ["--skip-gles-remote-build",
              "--gles-client-mem-mib", "512", "--gles-proxy-mem-mib", "384"]
    sizes = [1048576] if args.quick else [1048576, 4194304, 16777216, 33554432]
    for count in sizes:
        mib = count * 4 // (1024 * 1024)
        single(f"compute-{mib}mib", ["--gles-compute-smoke", *common,
               "--gles-smoke-args",
               f"--count {count} --iterations {measured if mib <= 16 else 20} --warmup {warmup} --perf --exclude-cpu-prepare"])
    single("ml-all", ["--gles-ml-smoke", *common, "--gles-smoke-args",
           f"--kernel all --gemm-size 512 --iterations {measured} --warmup {warmup}"])
    single("attention320", ["--gles-ml-smoke", *common, "--gles-smoke-args",
           f"--kernel attention --attention-size 320 --iterations {2 if args.quick else 10} --warmup 2"])
    single("ncnn", ["--gles-ncnn-smoke", *common],
           {"GLES_NCNN_LOOP_COUNT": str(measured), "GLES_CLIENT_BO_MMAP_CACHED": "0"})
    for size in ["1280x720", "1920x1080"]:
        single("glmark-" + size, ["--gles-glmark-smoke", *common,
               "--gles-glmark-size", size],
               {"GLES_GLMARK_FLAVOR": "null-noop", "GLES_GLMARK_FRAME_END": "finish",
                "GLES_GLMARK_BENCHMARKS": "build" if args.quick else ""})
    run("two-client", ["bash", "scripts/run/run-vmshm-2client-e2e.sh",
        "--skip-sync", "--gles-compute-smoke", "--skip-gles-remote-build",
        "--gles-smoke-args", f"--count 1048576 --iterations {measured} --warmup {warmup}",
        "--gles-client-mem-mib", "128", "--gles-proxy-mem-mib", "192"])
    if args.passthrough:
        run("passthrough", ["bash", "scripts/run/run-host-vs-passthrough-gles-perf.sh",
            "--host-rootfs-userspace", "--skip-sync", "--skip-remote-build",
            "--exclude-cpu-prepare", "--iterations", str(measured),
            "--warmup", str(warmup), "--large-count-iterations", "20",
            "--large-count-warmup", str(warmup)])
    run("idle-after", ssh + [
        "! pgrep -x firecracker; ! pgrep -x vmshm-broker; "
        "test -c /dev/pmthor; cat /sys/devices/system/cpu/online; "
        "grep -E 'MemAvailable|Shmem:' /proc/meminfo"
    ])
    print(f"REGRESSION_RESULT=PASS cases={len(rows)} evidence={out}", flush=True)


if __name__ == "__main__":
    main()
