"""Boundary tests for the external verifier service."""

from __future__ import annotations

import secrets
import socket
import threading
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS
from benchmarks.codegraph_compare.verifier_service import (
    CHALLENGE_DOMAIN,
    LEDGER_DOMAIN,
    VERDICT_DOMAIN,
    _frame,
    _send,
    request_verdict,
)


def _verdict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "evaluation_stage": "E0",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "unlock_allowed": False,
        "status": "SETUP_QUALIFIED",
        "authorization": "PRODUCTION_VERIFIER",
        "top_level_reasons": [],
        "expected_cells": 14,
        "observed_receipts": 14,
        "attempts_per_cell": 1,
        "counters": {
            "api_cost_usd": 0,
            "input_tokens": 0,
            "model_calls": 0,
            "network_requests": 0,
            "output_tokens": 0,
            "provider_requests": 0,
        },
        "cell_diagnostics": [
            {"repo_id": repo, "arm_id": arm, "reasons": []}
            for repo, arm in EXPECTED_CELLS
        ],
    }


def _measurement() -> dict[str, object]:
    return {
        "interpreter_sha256": "6" * 64,
        "closure_manifest": {},
        "closure_manifest_sha256": "3" * 64,
        "uid": 1000,
        "gid": 1000,
        "rootfs_readonly": True,
        "allowed_writable_mounts": ["/tmp"],
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 2,
        "correlation_nonce": "4" * 64,
        "cells": [
            {
                "contract": {
                    "decision_id": "7" * 64,
                    "decision_contract_sha256": "a" * 64,
                }
            }
        ],
    }


def _config(key: Ed25519PrivateKey) -> dict[str, object]:
    return {
        "verifier": {
            "peer_uid": __import__("os").getuid(),
            "key_id": "verifier",
            "public_key_hex": key.public_key().public_bytes_raw().hex(),
        },
        "trusted": {
            "verifier_runtime": {
                "image_digest": "sha256:" + "1" * 64,
                "image_id": "sha256:" + "2" * 64,
                "closure_manifest_sha256": "3" * 64,
                "measurement": _measurement(),
            }
        },
    }


def _server(path: Path, key: Ed25519PrivateKey, *, forge: bool) -> threading.Thread:
    ready = threading.Event()

    def run() -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(2)
        ready.set()
        first, _ = listener.accept()
        begin_request = _frame(first)
        challenge_signed = {
            "manifest_sha256": begin_request["manifest_sha256"],
            "challenge": "5" * 64,
            "ledger_counter": 1,
            "ledger_prev_hash": "0" * 64,
            "issued_at_ns": 123,
            "service_identity": _measurement(),
        }
        _send(
            first,
            {
                **challenge_signed,
                "key_id": "verifier",
                "algorithm": "Ed25519",
                "signature": key.sign(
                    CHALLENGE_DOMAIN + canonical_json_bytes(challenge_signed)
                ).hex(),
            },
        )
        first.close()
        connection, _ = listener.accept()
        request = _frame(connection)
        manifest = strict_json_loads(request["manifest_bytes"].encode("utf-8"))
        decision = manifest["cells"][0]["contract"]
        consumed = {
            "counter": 3,
            "event": "CONSUMED",
            "challenge": request["challenge"],
            "manifest_sha256": request["manifest_sha256"],
            "issued_at_ns": 123,
            "event_at_ns": 125,
            "prev_hash": "8" * 64,
            "record_hash": "9" * 64,
        }
        head = {"counter": 3, "record_hash": "9" * 64}

        def ledger_proof(record: dict[str, object]) -> dict[str, object]:
            return {
                "record": record,
                "key_id": "verifier",
                "algorithm": "Ed25519",
                "signature": key.sign(
                    LEDGER_DOMAIN + canonical_json_bytes(record)
                ).hex(),
            }

        signed = {
            "manifest_sha256": request["manifest_sha256"],
            "decision_id": decision["decision_id"],
            "decision_contract_sha256": decision["decision_contract_sha256"],
            "challenge": request["challenge"],
            "ledger_counter": 3,
            "ledger_prev_hash": "8" * 64,
            "issued_at_ns": 123,
            "verdict": _verdict(),
            "service_identity": _measurement(),
            "consumption_record": ledger_proof(consumed),
            "ledger_head": ledger_proof(head),
        }
        signer = Ed25519PrivateKey.generate() if forge else key
        _send(
            connection,
            {
                **signed,
                "key_id": "verifier",
                "algorithm": "Ed25519",
                "signature": signer.sign(
                    VERDICT_DOMAIN + canonical_json_bytes(signed)
                ).hex(),
            },
        )
        connection.close()
        listener.close()
        path.unlink(missing_ok=True)

    thread = threading.Thread(target=run)
    thread.start()
    ready.wait(2)
    return thread


@pytest.mark.skipif(
    not hasattr(socket, "SO_PEERCRED"),
    reason="tracked: external verifier peer credentials require Linux CI",
)
def test_external_verifier_client_accepts_signed_runtime_bound_envelope(tmp_path: Path):
    key = Ed25519PrivateKey.generate()
    path = Path("/tmp") / f"v-{secrets.token_hex(4)}.sock"
    thread = _server(path, key, forge=False)
    envelope = request_verdict(
        socket_path=path,
        manifest=_manifest(),
        config=_config(key),
        timeout=2,
    )
    thread.join(2)
    assert envelope["verdict"] == _verdict()


@pytest.mark.skipif(
    not hasattr(socket, "SO_PEERCRED"),
    reason="tracked: external verifier peer credentials require Linux CI",
)
def test_external_verifier_client_rejects_forged_verdict_signature(tmp_path: Path):
    key = Ed25519PrivateKey.generate()
    path = Path("/tmp") / f"v-{secrets.token_hex(4)}.sock"
    thread = _server(path, key, forge=True)
    with pytest.raises(InvalidSignature):
        request_verdict(
            socket_path=path,
            manifest=_manifest(),
            config=_config(key),
            timeout=2,
        )
    thread.join(2)
