"""Boundary tests for the external receipt-v3 signer services."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
from benchmarks.codegraph_compare.receipt_v3_service import (
    RESPONSE_DOMAIN,
    _paths,
    _verify_authority,
)


def _authority_envelope() -> tuple[dict[str, object], dict[str, object]]:
    key = Ed25519PrivateKey.from_private_bytes(b"A" * 32)
    response = {
        "contract_digest": "1" * 64,
        "job_id": "2" * 64,
        "cell": {"repo_id": "gin", "arm_id": "tsa-warm", "attempt": 1},
        "nonce": "3" * 64,
        "audit": {},
        "artifacts": [
            {
                "name": name,
                "id": "4" * 64,
                "sha256": "5" * 64,
                "size": 0,
                "path": f"{'2' * 64}/{name}",
            }
            for name in (
                "core",
                "data.img",
                "hash.img",
                "launch-audit.json",
                "verity-format.txt",
            )
        ],
    }
    envelope = {
        "response": response,
        "key_id": "authority",
        "algorithm": "Ed25519",
        "signature": key.sign(RESPONSE_DOMAIN + canonical_json_bytes(response)).hex(),
    }
    config = {
        "auditor": {
            "key_id": "authority",
            "public_key_hex": key.public_key().public_bytes_raw().hex(),
        }
    }
    return envelope, config


def test_receipt_service_rejects_mutated_authority_job_descriptor():
    envelope, config = _authority_envelope()
    envelope["response"]["nonce"] = "6" * 64
    with pytest.raises(InvalidSignature):
        _verify_authority(envelope, config)


def test_receipt_service_recomputes_artifact_descriptor_identity(tmp_path: Path):
    envelope, _config = _authority_envelope()
    response = envelope["response"]
    job = tmp_path / response["job_id"]
    core = job / "core"
    core.mkdir(parents=True)
    for item in response["artifacts"]:
        path = job / item["name"]
        if item["name"] == "core":
            digest = __import__(
                "benchmarks.codegraph_compare.setup_qualification_paths",
                fromlist=["_hash_tree"],
            )._hash_tree(path)
        else:
            path.write_bytes(b"")
            digest = hashlib.sha256(b"").hexdigest()
        item["sha256"] = digest
        item["id"] = hashlib.sha256(
            canonical_json_bytes(
                {key: item[key] for key in ("name", "sha256", "size", "path")}
            )
        ).hexdigest()
    response["artifacts"][0]["id"] = "0" * 64
    staged = tmp_path / "staged" / response["job_id"]
    staged.mkdir(parents=True)
    for name in (
        "plan.json",
        "inventory.json",
        "source-snapshot.tar",
        "tool",
        "config",
        "seccomp",
        "public-config.json",
    ):
        (staged / name).write_bytes(b"{}")
    with pytest.raises(ValueError, match="changed after signing"):
        _paths(response, tmp_path, tmp_path / "staged")
