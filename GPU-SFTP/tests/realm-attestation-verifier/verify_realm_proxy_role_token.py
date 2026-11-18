#!/usr/bin/env python3
"""Verify a Realm delegated token's approved GPU Proxy role claim."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


PROFILE = "tag:arm.com,2023:realm#1.0.0"
HASH_ALGORITHMS = {
    "sha-256": hashlib.sha256,
    "sha-512": hashlib.sha512,
}
HASH_SIZES = {"sha-256": 32, "sha-512": 64}
TRUSTED_CCA_TAG = 399
REALM_DELEGATED_TOKEN = 44241
PLATFORM_TOKEN = 44234
REALM_CHALLENGE = 10
REALM_PROFILE = 265
REALM_HASH_ALGORITHM = 44236
REALM_PUBLIC_KEY = 44237
REALM_INITIAL_MEASUREMENT = 44238
REALM_EXTENSIBLE_MEASUREMENTS = 44239
REALM_PUBLIC_KEY_HASH_ALGORITHM = 44240
ES384 = -47
POLICY_KEYS = {
    "schema_version",
    "profile",
    "hash_algorithm",
    "challenge_hex",
    "endpoint_id",
    "rim_hex",
}


class TokenError(ValueError):
    pass


class CborTag:
    def __init__(self, tag: int, value: Any) -> None:
        self.tag = tag
        self.value = value


def encode_cbor(value: Any) -> bytes:
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if value is None:
        return b"\xf6"
    if isinstance(value, int) and value >= 0:
        return encode_head(0, value)
    if isinstance(value, int):
        return encode_head(1, -1 - value)
    if isinstance(value, bytes):
        return encode_head(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return encode_head(3, len(encoded)) + encoded
    if isinstance(value, list):
        return encode_head(4, len(value)) + b"".join(encode_cbor(item) for item in value)
    if isinstance(value, dict):
        if not all(isinstance(key, int) for key in value):
            raise TokenError("CBOR map keys must be integers")
        return encode_head(5, len(value)) + b"".join(
            encode_cbor(key) + encode_cbor(value[key]) for key in sorted(value)
        )
    if isinstance(value, CborTag):
        return encode_head(6, value.tag) + encode_cbor(value.value)
    raise TokenError(f"unsupported CBOR value: {type(value).__name__}")


def encode_head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")
    raise TokenError("CBOR integer is out of range")


def decode_cbor(data: bytes) -> Any:
    value, offset = decode_cbor_item(data, 0, 0)
    if offset != len(data):
        raise TokenError("trailing bytes after CBOR value")
    return value


def decode_cbor_item(data: bytes, offset: int, depth: int) -> tuple[Any, int]:
    if depth > 8:
        raise TokenError("CBOR nesting depth exceeded")
    if offset >= len(data):
        raise TokenError("truncated CBOR value")
    initial = data[offset]
    offset += 1
    major = initial >> 5
    additional = initial & 0x1F
    if additional == 31:
        raise TokenError("indefinite-length CBOR is not accepted")
    if additional < 24:
        argument: int = additional
    elif additional in (24, 25, 26, 27):
        width = 1 << (additional - 24)
        if offset + width > len(data):
            raise TokenError("truncated CBOR length")
        argument = int.from_bytes(data[offset:offset + width], "big")
        offset += width
    else:
        raise TokenError("reserved CBOR additional information")
    if major == 0:
        return argument, offset
    if major == 1:
        return -1 - argument, offset
    if major in (2, 3):
        if offset + argument > len(data):
            raise TokenError("truncated CBOR string")
        payload = data[offset:offset + argument]
        offset += argument
        if major == 2:
            return payload, offset
        try:
            return payload.decode("utf-8"), offset
        except UnicodeDecodeError as error:
            raise TokenError("invalid UTF-8 CBOR text") from error
    if major == 4:
        items, offset = decode_cbor_items(data, offset, argument, depth)
        return items, offset
    if major == 5:
        if argument > 16:
            raise TokenError("CBOR map has too many entries")
        result: dict[int, Any] = {}
        for _ in range(argument):
            key, offset = decode_cbor_item(data, offset, depth + 1)
            if not isinstance(key, int):
                raise TokenError("CBOR map key is not an integer")
            if key in result:
                raise TokenError("duplicate CBOR map key")
            result[key], offset = decode_cbor_item(data, offset, depth + 1)
        return result, offset
    if major == 6:
        value, offset = decode_cbor_item(data, offset, depth + 1)
        return CborTag(argument, value), offset
    if major == 7 and additional == 20:
        return False, offset
    if major == 7 and additional == 21:
        return True, offset
    if major == 7 and additional == 22:
        return None, offset
    raise TokenError("unsupported CBOR major type")


def decode_cbor_items(data: bytes, offset: int, count: int, depth: int) -> tuple[list[Any], int]:
    if count > 64:
        raise TokenError("CBOR array is too large")
    items: list[Any] = []
    for _ in range(count):
        item, offset = decode_cbor_item(data, offset, depth + 1)
        items.append(item)
    return items, offset


def reject(reason: str) -> dict[str, Any]:
    return {
        "status": "REJECTED",
        "reason": reason,
        "platform_token_verified": False,
        "full_cca_chain_verified": False,
        "hardware_tests": "NOT_RUN",
    }


def load_hex(value: str, name: str) -> bytes:
    try:
        decoded = bytes.fromhex(value)
    except ValueError as error:
        raise TokenError(f"{name} is not hexadecimal") from error
    if len(decoded) * 2 != len(value) or not decoded:
        raise TokenError(f"{name} must use non-empty even-length hexadecimal")
    return decoded


def load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TokenError(f"policy is unreadable: {error}") from error
    if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
        raise TokenError("policy fields do not match schema version 1")
    if policy["schema_version"] != 1:
        raise TokenError("unsupported policy schema version")
    if policy["profile"] != PROFILE:
        raise TokenError("unapproved Realm profile")
    if policy["hash_algorithm"] not in HASH_ALGORITHMS:
        raise TokenError("unapproved measurement algorithm")
    endpoint_id = policy["endpoint_id"]
    if not isinstance(endpoint_id, int) or isinstance(endpoint_id, bool) or not 0 < endpoint_id < 2**64:
        raise TokenError("endpoint_id must be a nonzero uint64")
    challenge = load_hex(policy["challenge_hex"], "challenge")
    rim = load_hex(policy["rim_hex"], "RIM")
    expected_size = HASH_SIZES[policy["hash_algorithm"]]
    if len(challenge) != 64:
        raise TokenError("challenge must be 64 bytes")
    if len(rim) != expected_size:
        raise TokenError("RIM length does not match the measurement algorithm")
    return policy


def load_trust_anchor(path: Path) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError) as error:
        raise TokenError(f"trust anchor is unreadable: {error}") from error
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP384R1):
        raise TokenError("trust anchor must be a P-384 public key")
    return key


def extract_realm_token(data: bytes) -> bytes:
    top_level = decode_cbor(data)
    if not isinstance(top_level, CborTag) or top_level.tag != TRUSTED_CCA_TAG:
        raise TokenError("input is not a CCA attestation token")
    if not isinstance(top_level.value, dict):
        raise TokenError("CCA token payload is not a map")
    platform_token = top_level.value.get(PLATFORM_TOKEN)
    realm_token = top_level.value.get(REALM_DELEGATED_TOKEN)
    if not isinstance(platform_token, bytes) or not platform_token:
        raise TokenError("CCA platform token is missing")
    if not isinstance(realm_token, bytes):
        raise TokenError("Realm delegated token is missing")
    return realm_token


def verify_signature(realm_token: bytes, trust_anchor: ec.EllipticCurvePublicKey) -> tuple[dict[Any, Any], bytes]:
    cose = decode_cbor(realm_token)
    if not isinstance(cose, list) or len(cose) != 4:
        raise TokenError("delegated token is not COSE_Sign1")
    protected_bytes, unprotected, payload, signature = cose
    if not isinstance(protected_bytes, bytes) or not isinstance(unprotected, dict):
        raise TokenError("invalid COSE headers")
    if not isinstance(payload, bytes) or not isinstance(signature, bytes):
        raise TokenError("invalid COSE payload or signature")
    protected = decode_cbor(protected_bytes)
    if protected != {1: ES384}:
        raise TokenError("COSE algorithm is not ES384")
    if len(signature) != 96:
        raise TokenError("ES384 signature length is invalid")
    signature_input = encode_cbor(["Signature1", protected_bytes, b"", payload])
    der_signature = encode_dss_signature(
        int.from_bytes(signature[:48], "big"), int.from_bytes(signature[48:], "big")
    )
    try:
        trust_anchor.verify(der_signature, signature_input, ec.ECDSA(hashes.SHA384()))
    except InvalidSignature as error:
        raise TokenError("delegated token signature does not match trust anchor") from error
    claims = decode_cbor(payload)
    if not isinstance(claims, dict):
        raise TokenError("delegated token payload is not a map")
    return claims, payload


def verify_policy(claims: dict[Any, Any], policy: dict[str, Any]) -> None:
    required_text = {
        REALM_PROFILE: PROFILE,
        REALM_HASH_ALGORITHM: policy["hash_algorithm"],
    }
    for label, expected in required_text.items():
        if claims.get(label) != expected:
            raise TokenError(f"Realm claim {label} does not match policy")
    if not isinstance(claims.get(REALM_PUBLIC_KEY), bytes) or not claims[REALM_PUBLIC_KEY]:
        raise TokenError("Realm public key is missing")
    public_key_hash = claims.get(REALM_PUBLIC_KEY_HASH_ALGORITHM)
    if not isinstance(public_key_hash, str) or public_key_hash not in ("sha-256", "sha-384", "sha-512"):
        raise TokenError("Realm public-key hash algorithm is invalid")
    if claims.get(REALM_CHALLENGE) != load_hex(policy["challenge_hex"], "challenge"):
        raise TokenError("challenge replay or mismatch")
    if claims.get(REALM_INITIAL_MEASUREMENT) != load_hex(policy["rim_hex"], "RIM"):
        raise TokenError("RIM is not approved")
    measurements = claims.get(REALM_EXTENSIBLE_MEASUREMENTS)
    if not isinstance(measurements, list) or len(measurements) != 4:
        raise TokenError("REM array is not the required four slots")
    if not all(isinstance(item, bytes) for item in measurements):
        raise TokenError("REM array contains a non-byte-string measurement")
    expected_size = HASH_SIZES[policy["hash_algorithm"]]
    if any(len(item) != expected_size for item in measurements):
        raise TokenError("REM length does not match the measurement algorithm")
    role_claim = struct.pack("<8sQQ", b"OCCAGPU1", 1, policy["endpoint_id"])
    expected_role = HASH_ALGORITHMS[policy["hash_algorithm"]](role_claim).digest()
    if measurements[3] != expected_role:
        raise TokenError("GPU role claim does not match the current endpoint")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--trust-anchor", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result: dict[str, Any]
    try:
        policy = load_policy(args.policy)
        trust_anchor = load_trust_anchor(args.trust_anchor)
        token = args.token.read_bytes()
        claims, _ = verify_signature(extract_realm_token(token), trust_anchor)
        verify_policy(claims, policy)
        result = {
            "status": "PASS_REALM_DELEGATED_TOKEN_VERIFIED",
            "profile": policy["profile"],
            "hash_algorithm": policy["hash_algorithm"],
            "endpoint_bound": True,
            "challenge_bound": True,
            "rim_approved": True,
            "platform_token_verified": False,
            "full_cca_chain_verified": False,
            "hardware_tests": "NOT_RUN",
        }
    except (OSError, TokenError) as error:
        result = reject(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
