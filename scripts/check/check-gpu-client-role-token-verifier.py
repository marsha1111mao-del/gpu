#!/usr/bin/env python3
"""Exercise the Client-side GPU role delegated-token verifier fail-closed."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


ROOT = Path(__file__).resolve().parents[2]
RMM = ROOT / "opencca/tf-rmm"
VERIFIER = ROOT / "GPU-SFTP/tests/realm-attestation-verifier/verify_realm_proxy_role_token.py"
SCALAR_SEED = b"offline-proxy-role-token-verifier-fixed-key-v1"
ALTERNATE_SCALAR_SEED = b"offline-proxy-role-token-verifier-wrong-key-v1"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_key(seed: bytes) -> ec.EllipticCurvePrivateKey:
    scalar = int.from_bytes(hashlib.sha512(seed).digest()[:4], "big") + 1
    return ec.derive_private_key(scalar, ec.SECP384R1())


def load_verifier():
    spec = importlib.util.spec_from_file_location("realm_role_verifier", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VERIFIER_MODULE = load_verifier()


def encode_cbor(value):
    return VERIFIER_MODULE.encode_cbor(value), VERIFIER_MODULE


def build_case(name: str, *, challenge=None, rim=None, endpoint_id=0x123456789abcdef0):
    challenge = challenge or bytes(range(64))
    rim = rim or bytes.fromhex("11" * 64)
    role_claim = struct.pack("<8sQQ", b"OCCAGPU1", 1, endpoint_id)
    claims = {
        10: challenge,
        265: "tag:arm.com,2023:realm#1.0.0",
        44235: b"realm-personalization-value",
        44236: "sha-512",
        44237: b"realm-public-key",
        44238: rim,
        44239: [b"\x22" * 64, b"\x33" * 64, b"\x44" * 64, hashlib.sha512(role_claim).digest()],
        44240: "sha-384",
    }
    encoded_claims, verifier = encode_cbor(claims)
    protected, verifier = encode_cbor({1: -47})
    signature_input, verifier = encode_cbor(["Signature1", protected, b"", encoded_claims])
    key = private_key(SCALAR_SEED)
    r, s = decode_dss_signature(key.sign(signature_input, ec.ECDSA(hashes.SHA384())))
    raw_signature = r.to_bytes(48, "big") + s.to_bytes(48, "big")
    assert len(raw_signature) == 96
    cose, verifier = encode_cbor([protected, {}, encoded_claims, raw_signature])
    cca, verifier = encode_cbor(verifier.CborTag(399, {44234: b"platform-token", 44241: cose}))
    case_dir = out / name
    case_dir.mkdir()
    (case_dir / "token.cbor").write_bytes(cca)
    (case_dir / "trust-anchor.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    policy = {
        "schema_version": 1,
        "profile": "tag:arm.com,2023:realm#1.0.0",
        "hash_algorithm": "sha-512",
        "challenge_hex": challenge.hex(),
        "endpoint_id": endpoint_id,
        "rim_hex": rim.hex(),
    }
    (case_dir / "policy.json").write_text(json.dumps(policy, indent=2) + "\n")
    return case_dir, cca, verifier


base_dir, base_token, verifier_module = build_case("candidate")
command = [
    "python3", str(VERIFIER),
    "--token", str(base_dir / "token.cbor"),
    "--policy", str(base_dir / "policy.json"),
    "--trust-anchor", str(base_dir / "trust-anchor.pem"),
]
with (out / "candidate.log").open("w") as log:
    candidate = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
candidate_output = (out / "candidate.log").read_text()
assert candidate.returncode == 0 and "PASS_REALM_DELEGATED_TOKEN_VERIFIED" in candidate_output, candidate_output

wrong_challenge = bytes(64)
wrong_challenge_dir, _, _ = build_case("wrong-challenge", challenge=wrong_challenge)
wrong_challenge_policy = json.loads((wrong_challenge_dir / "policy.json").read_text())
wrong_challenge_policy["challenge_hex"] = bytes(range(64)).hex()
(wrong_challenge_dir / "policy.json").write_text(json.dumps(wrong_challenge_policy) + "\n")

wrong_rim_dir, _, _ = build_case("wrong-rim")
wrong_rim_policy = json.loads((wrong_rim_dir / "policy.json").read_text())
wrong_rim_policy["rim_hex"] = ("00" * 64)
(wrong_rim_dir / "policy.json").write_text(json.dumps(wrong_rim_policy) + "\n")

wrong_endpoint_dir, _, _ = build_case("wrong-endpoint")
wrong_endpoint_policy = json.loads((wrong_endpoint_dir / "policy.json").read_text())
wrong_endpoint_policy["endpoint_id"] += 1
(wrong_endpoint_dir / "policy.json").write_text(json.dumps(wrong_endpoint_policy) + "\n")

wrong_profile_dir, _, _ = build_case("wrong-profile")
wrong_profile_policy = json.loads((wrong_profile_dir / "policy.json").read_text())
wrong_profile_policy["profile"] = "unapproved-profile"
(wrong_profile_dir / "policy.json").write_text(json.dumps(wrong_profile_policy) + "\n")

tampered_dir = out / "tampered-signature"
tampered_dir.mkdir()
tampered_token = bytearray(base_token)
tampered_token[-1] ^= 1
(tampered_dir / "token.cbor").write_bytes(tampered_token)
(tampered_dir / "trust-anchor.pem").write_bytes((base_dir / "trust-anchor.pem").read_bytes())
(tampered_dir / "policy.json").write_bytes((base_dir / "policy.json").read_bytes())

wrong_key_dir = out / "wrong-key"
wrong_key_dir.mkdir()
(wrong_key_dir / "token.cbor").write_bytes(base_token)
wrong_key = private_key(ALTERNATE_SCALAR_SEED)
(wrong_key_dir / "trust-anchor.pem").write_bytes(wrong_key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
))
(wrong_key_dir / "policy.json").write_bytes((base_dir / "policy.json").read_bytes())

results = [{
    "name": "candidate",
    "command": command,
    "exit_code": candidate.returncode,
    "log": str(out / "candidate.log"),
}]
for name in (
    "wrong-challenge", "wrong-rim", "wrong-endpoint", "wrong-profile",
    "tampered-signature", "wrong-key",
):
    case_dir = out / name
    case_command = [
        "python3", str(VERIFIER),
        "--token", str(case_dir / "token.cbor"),
        "--policy", str(case_dir / "policy.json"),
        "--trust-anchor", str(case_dir / "trust-anchor.pem"),
    ]
    log_path = out / f"{name}.log"
    with log_path.open("w") as log:
        result = subprocess.run(case_command, stdout=log, stderr=subprocess.STDOUT, check=False)
    text = log_path.read_text()
    assert result.returncode == 2 and '"status": "REJECTED"' in text, (name, text)
    results.append({
        "name": name,
        "command": case_command,
        "exit_code": result.returncode,
        "log": str(log_path),
    })
    print(name, "REJECTED", flush=True)

source_paths = [
    VERIFIER,
    VERIFIER.parent / "README.md",
    Path(__file__),
    RMM / "runtime/include/opencca_gpu_role.h",
    RMM / "runtime/core/opencca_gpu_role.c",
    RMM / "lib/attestation/src/attestation_token.c",
]
(out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
(out / "summary.json").write_text(json.dumps({
    "status": "PASS_GPU_CLIENT_ROLE_TOKEN_VERIFIER_MODELS",
    "actual_verifier": True,
    "signature_verified": True,
    "policy_fail_closed": True,
    "candidate_exit_code": candidate.returncode,
    "negative_cases": 6,
    "negative_exit_codes": [2] * 6,
    "deterministic_key_seed_sha256": hashlib.sha256(SCALAR_SEED).hexdigest(),
    "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in source_paths},
    "scope": "Actual delegated COSE_Sign1 verifier with fixed trust anchor, exact challenge/RIM policy, endpoint-derived REM slot 4 claim, and fail-closed negative fixtures",
    "not_covered": "No platform certificate chain verification, trusted anchor/RIM provisioning, full TSM execution, Proxy token transport, Linux concurrency, or hardware/L3 validation",
    "hardware_tests": "NOT_RUN",
    "goal_complete": False,
}, indent=2) + "\n")
print(json.dumps({
    "status": "PASS_GPU_CLIENT_ROLE_TOKEN_VERIFIER_MODELS",
    "negative_cases": 6,
    "evidence": str(out),
    "delegated_token_only": True,
    "goal_complete": False,
}))
