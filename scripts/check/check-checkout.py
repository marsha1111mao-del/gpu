#!/usr/bin/env python3
"""Validate clone completeness, shell/Python syntax, payloads and rootfs hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import ast
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-rootfs", action="store_true")
    args = parser.parse_args()
    status = subprocess.check_output(
        ["git", "submodule", "status"], cwd=ROOT, text=True)
    if any(line and line[0] in "-+U" for line in status.splitlines()):
        raise ValueError("Submodules are absent or differ from pinned commits; run bootstrap.sh")
    for role in ("host", "client", "proxy", "passthrough"):
        path = ROOT / f"configs/verified-20261015/{role}.config"
        if not path.is_file():
            raise ValueError(f"Missing kernel config: {path}")
    count = 0
    for directory in ("scripts", "GPU-SFTP/tests", "GPU-SFTP/firecracker-bins/scripts"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.suffix == ".sh":
                run("bash", "-n", str(path))
                count += 1
            elif path.suffix == ".py":
                ast.parse(path.read_text(), filename=str(path))
                count += 1
    run(sys.executable, str(ROOT / "scripts/artifacts/restore-runtime.py"), "--check")
    runtime = json.loads((ROOT / "GPU-SFTP/runtime-manifest.json").read_text())
    for artifact in runtime.get("source_archives", []):
        path = ROOT / artifact["archive"]
        if (not path.is_file() or path.stat().st_size != artifact["size"]
                or digest(path) != artifact["sha256"]):
            raise ValueError(f"Missing or incorrect source archive: {path}")
        print(f"SOURCE_VERIFY=PASS {path.name}", flush=True)
    if not args.no_rootfs:
        manifest = json.loads((ROOT / "GPU-SFTP/rootfs-manifest.json").read_text())
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            if (not path.is_file() or path.stat().st_size != artifact["size"]
                    or digest(path) != artifact["sha256"]):
                raise ValueError(f"Missing or incorrect rootfs: {path}; run fetch-rootfs.sh")
            print(f"ROOTFS_VERIFY=PASS {path.name}", flush=True)
    print(f"CHECKOUT_RESULT=PASS scripts_checked={count}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
            SyntaxError) as error:
        sys.exit(str(error))
