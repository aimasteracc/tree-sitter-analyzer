"""Boundary tests for the external verifier service."""

from __future__ import annotations

import secrets
import socket
import threading
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
from benchmarks.codegraph_compare.verifier_service import (
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
        "authorization": "PRODUCTION_ROOT",
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
        "cell_diagnostics": [],
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
            }
        },
    }


def _server(path: Path, key: Ed25519PrivateKey, *, forge: bool) -> threading.Thread:
    ready = threading.Event()

    def run() -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        request = _frame(connection)
        signed = {
            "manifest_sha256": request["manifest_sha256"],
            "challenge": request["challenge"],
            "verdict": _verdict(),
            "service_identity": {
                "image_digest": "sha256:" + "1" * 64,
                "image_id": "sha256:" + "2" * 64,
                "closure_manifest_sha256": "3" * 64,
            },
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
        manifest={"schema_version": 2, "correlation_nonce": "4" * 64, "cells": []},
        challenge="5" * 64,
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
            manifest={"schema_version": 2, "correlation_nonce": "4" * 64, "cells": []},
            challenge="5" * 64,
            config=_config(key),
            timeout=2,
        )
    thread.join(2)
