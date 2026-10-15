#!/usr/bin/env python3
"""Verify and restore the compact, versioned ARM64 regression payload."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_destination(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe artifact path: {name}")
    destination = root.joinpath(*path.parts)
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Artifact escapes destination: {name}")
    return destination


def restore(manifest_path, destination, check=False, force=False):
    manifest = json.loads(manifest_path.read_text())
    # Validate all archives and paths before replacing any payload.
    plan = []
    for artifact in manifest["artifacts"]:
        archive_path = safe_destination(ROOT, artifact["archive"])
        if (not archive_path.is_file()
                or archive_path.stat().st_size != artifact["size"]
                or sha256(archive_path) != artifact["sha256"]):
            raise ValueError(f"Missing or incorrect archive: {archive_path}")
        members = artifact["files"]
        with tarfile.open(archive_path) as archive:
            found = set()
            for member in archive.getmembers():
                safe_destination(destination, member.name)
                if not member.isfile() or member.name not in members:
                    raise ValueError(f"Unexpected archive entry: {member.name}")
                if member.name in found:
                    raise ValueError(f"Duplicate archive entry: {member.name}")
                found.add(member.name)
                entry = members[member.name]
                if member.size != entry["size"]:
                    raise ValueError(f"Incorrect size: {member.name}")
                with archive.extractfile(member) as source:
                    digest = hashlib.sha256(source.read()).hexdigest()
                if digest != entry["sha256"]:
                    raise ValueError(f"Incorrect member hash: {member.name}")
                target = safe_destination(destination, member.name)
                mode = member.mode & 0o777
                if target.is_file() and sha256(target) == entry["sha256"]:
                    if (target.stat().st_mode & 0o111) == (mode & 0o111):
                        continue
                if check:
                    raise ValueError(f"Unrestored or changed runtime file: {target}")
                if target.exists() and not force:
                    raise ValueError(
                        f"Local runtime differs: {target}; back it up and use --force"
                    )
                plan.append((archive_path, member.name, target, mode))
            if found != set(members):
                raise ValueError(f"Incomplete archive: {archive_path}")
    destination.mkdir(parents=True, exist_ok=True)
    for archive_path, name, target, mode in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path) as archive:
            with archive.extractfile(name) as source:
                fd, temporary = tempfile.mkstemp(prefix=".runtime-", dir=target.parent)
                try:
                    with os.fdopen(fd, "wb") as output:
                        shutil.copyfileobj(source, output)
                    os.chmod(temporary, mode)
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
    print(f"RUNTIME_{'VERIFY' if check else 'RESTORE'}=PASS files_restored={len(plan)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "GPU-SFTP/runtime-manifest.json")
    parser.add_argument("--dest", type=Path, default=ROOT / "GPU-SFTP")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        restore(args.manifest, args.dest, args.check, args.force)
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        sys.exit(str(error))
