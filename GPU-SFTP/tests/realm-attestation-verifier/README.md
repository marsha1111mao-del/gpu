# Realm GPU Proxy role delegated-token verifier

This offline Client-side MVP verifies a standard top-level CCA token's Realm
delegated `COSE_Sign1`: ES384 signature, exact 64-byte challenge, approved RIM,
Realm profile and hash algorithm, four REM slots, and the endpoint-derived GPU
role claim in REM slot 4.

```bash
python3 GPU-SFTP/tests/realm-attestation-verifier/verify_realm_proxy_role_token.py \
  --token proxy-token.cbor \
  --policy approved-proxy.json \
  --trust-anchor realm-delegated-key.pem
```

The policy schema is version 1 and requires `profile`, `hash_algorithm`,
64-byte `challenge_hex`, nonzero uint64 `endpoint_id`, and algorithm-sized
`rim_hex`. The trust anchor is a separately provisioned P-384 public key. The
repository intentionally provides no production policy or anchor: the current
frozen combination has no trusted Proxy Realm RIM.

The calling Client must generate `challenge_hex` for this verification and take
`endpoint_id` from its trusted current vmshm channel state. Neither value may
be accepted from the untrusted Proxy or Host.

This verifier does **not** prove the platform certificate chain, provision the
anchor/RIM, execute the Linux TSM report path, transport a Proxy token over
vmshm, or run hardware tests. A pass means the delegated Realm token and the
approved GPU role claim match the supplied trusted inputs.
