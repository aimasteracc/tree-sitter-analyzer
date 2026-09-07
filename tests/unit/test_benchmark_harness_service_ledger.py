"""Issue #1376：service_ledger 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import (
    _qualification_v3_public_config,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_verifier_ledger_is_private_and_owned_by_service_uid(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178813: verifier USER 903 must own its writable ledger.
    import stat

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ChallengeLedger(tmp_path / "ledger.sqlite")
    metadata = (tmp_path / "ledger.sqlite").stat()
    assert metadata.st_uid == os.geteuid()
    assert stat.S_IMODE(metadata.st_mode) == 0o600


def test_decision_ledger_requires_uid_904_private_writable_parent(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744261023: SQLite WAL needs a service-owned private parent.
    import stat

    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    parent = tmp_path / "ledger"
    parent.mkdir(mode=0o700)
    real_stat = consumer.os.stat

    def service_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(st_uid=904, st_mode=stat.S_IFDIR | 0o700)
        return metadata

    monkeypatch.setattr(consumer.os, "stat", service_stat)
    monkeypatch.setattr(
        consumer.os,
        "access",
        lambda path, mode: (path, mode) == (parent, os.W_OK | os.X_OK),
    )

    ledger = consumer.DecisionLedger(
        parent / "decisions.sqlite", _qualification_v3_public_config()
    )

    assert ledger.path == parent / "decisions.sqlite"
    assert stat.S_IMODE(ledger.path.stat().st_mode) == 0o600

    def root_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o700)
        return metadata

    monkeypatch.setattr(consumer.os, "stat", root_stat)
    with pytest.raises(ValueError, match="UID 904 private 0700"):
        consumer.DecisionLedger(
            parent / "other.sqlite", _qualification_v3_public_config()
        )


def test_decision_consumer_recomputes_ordered_exact14_config_plan_binding():
    # PR #1249 review 3744261026: direct consumers must enforce root config plans.
    from benchmarks.codegraph_compare.decision_consumer_service import (
        verify_configured_plan_set,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    hashes = [f"{ordinal:064x}" for ordinal in range(1, 15)]
    plan_set_hash = hashlib.sha256(canonical_json_bytes(hashes)).hexdigest()
    contract = {
        "plan_set_hash": plan_set_hash,
        "cells": [
            {"repo_id": repo, "arm_id": arm, "plan_sha256": digest}
            for (repo, arm), digest in zip(EXPECTED_CELLS, hashes, strict=True)
        ],
    }
    config = {
        "trusted": {
            "plan_set_hash": plan_set_hash,
            "plan_hashes": {
                f"{repo}/{arm}": digest
                for (repo, arm), digest in zip(EXPECTED_CELLS, hashes, strict=True)
            },
        }
    }

    verify_configured_plan_set(contract, config)
    contract["cells"][13]["plan_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="root-config authorized"):
        verify_configured_plan_set(contract, config)


def test_verifier_manifest_parser_uses_64mib_protocol_not_receipt_limits():
    # PR #1249 review 3744261030: exact-14 manifests have independent frame bounds.
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier_service import _manifest_json_loads

    repeated_inventory = "x" * (17 * 1024 * 1024)
    manifest = {
        "operation": "verify-exact-14",
        "cells": [
            {
                "repo_id": f"repo-{ordinal}",
                "tracked_inventory": repeated_inventory if ordinal == 0 else "",
            }
            for ordinal in range(14)
        ],
    }
    payload = canonical_json_bytes(manifest)

    parsed = _manifest_json_loads(payload)

    assert len(payload) == 17_826_453
    assert len(parsed["cells"]) == 14


def test_decision_consumer_contains_four_malformed_connections_and_recovers(
    monkeypatch,
):
    # PR #1249 review 3744358507: per-connection failures must not drain workers.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    class Connection:
        def __init__(self, send_error=False):
            self.closed = False
            self.sent = []
            self.send_error = send_error

        def sendall(self, payload):
            if self.send_error:
                raise BrokenPipeError("peer disconnected")
            self.sent.append(payload)

        def close(self):
            self.closed = True

    key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
    connections = [
        Connection(),
        Connection(),
        Connection(),
        Connection(send_error=True),
    ]
    read_results = iter(
        (
            EOFError("truncated header"),
            ValueError("oversized frame"),
            ValueError("malformed JSON"),
            {"operation": "query-decision"},
        )
    )
    monkeypatch.setattr(consumer, "peer_allowed", lambda *_args: None)

    def read_request(*_args):
        result = next(read_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(consumer, "read_frame", read_request)
    monkeypatch.setattr(consumer, "consume_request", lambda *_args: {"ok": True})
    for connection in connections:
        consumer._serve_connection(connection, 901, {}, object(), key, {})

    healthy = Connection()
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: {"operation": "query"})
    consumer._serve_connection(healthy, 901, {}, object(), key, {})

    assert [connection.closed for connection in connections] == [True, True, True, True]
    assert healthy.closed is True
    assert len(healthy.sent) == 1


def test_decision_consumer_contains_peer_and_handler_errors(monkeypatch):
    # PR #1249 review 3744358507: SO_PEERCRED and handler errors stay connection-local.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    class Connection:
        def __init__(self):
            self.closed = False
            self.sent = []

        def sendall(self, payload):
            self.sent.append(payload)

        def close(self):
            self.closed = True

    key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x12" * 32)
    denied = Connection()
    monkeypatch.setattr(
        consumer,
        "peer_allowed",
        lambda *_args: (_ for _ in ()).throw(PermissionError("wrong UID")),
    )
    consumer._serve_connection(denied, 901, {}, object(), key, {})

    handled = Connection()
    monkeypatch.setattr(consumer, "peer_allowed", lambda *_args: None)
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: {})
    monkeypatch.setattr(
        consumer,
        "consume_request",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad decision")),
    )
    consumer._serve_connection(handled, 901, {}, object(), key, {})

    assert denied.closed is True
    assert denied.sent == []
    assert handled.closed is True
    assert len(handled.sent) == 1


def test_decision_consumer_rejects_wrong_private_key_before_ledger_or_listener(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358513: a wrong key must not poison the one-shot ledger.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    public = tmp_path / "public.json"
    public.write_bytes(b"{}")
    launch_attestation = tmp_path / "launch.json"
    launch_attestation.write_bytes(b"{}")
    configured_key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
    monkeypatch.setattr(consumer.os, "geteuid", lambda: 904)
    monkeypatch.setattr(
        consumer,
        "parse_public_config",
        lambda _raw: {
            "decision_consumer": {
                "peer_uid": 904,
                "public_key_hex": configured_key.public_key().public_bytes_raw().hex(),
            },
            "trusted": {"decision_consumer_runtime": {"measurement": {}}},
        },
    )
    monkeypatch.setattr(consumer, "measure_runtime", lambda _value: {})
    monkeypatch.setattr(consumer, "wait_for_launch_release", lambda *_args: b"{}")
    monkeypatch.setattr(
        consumer, "verify_service_launch_attestation", lambda *_args: {}
    )
    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(
        consumer, "secure_key", lambda *_args: (descriptor, b"\x65" * 32)
    )
    monkeypatch.setattr(
        consumer,
        "DecisionLedger",
        lambda *_args: (_ for _ in ()).throw(AssertionError("ledger opened")),
    )

    with pytest.raises(SystemExit, match="does not match public config"):
        consumer.main(
            [
                "--socket",
                str(tmp_path / "decision.sock"),
                "--private-key",
                str(tmp_path / "key"),
                "--public-config",
                str(public),
                "--ledger",
                str(tmp_path / "ledger.sqlite"),
                "--launch-attestation",
                str(launch_attestation),
                "--launch-release",
                str(tmp_path / "RELEASE"),
                "--allowed-client-uid",
                "901",
            ]
        )


def test_verifier_ledger_consumed_transition_persists_canonical_envelope_atomically(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744400335: a committed CONSUMED fact must recover its envelope.
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")
    manifest = "a" * 64
    challenge = ledger.begin(manifest)["challenge"]
    ledger.start_verifying(manifest, challenge)
    expected = canonical_json_bytes({"challenge": challenge, "signed": True})

    record, head, stored = ledger.finish_with_envelope(
        manifest, challenge, lambda _record, _head: expected
    )

    assert record["event"] == "CONSUMED"
    assert head == {"counter": record["counter"], "record_hash": record["record_hash"]}
    assert stored == expected
    assert ledger.verdict(manifest, challenge) == expected


def test_verifier_ledger_begin_is_manifest_idempotent(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744516421: a retry returns the already committed challenge.
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")

    first = ledger.begin("a" * 64)
    second = ledger.begin("a" * 64)

    assert second == first
    assert ledger.head()["counter"] == 1


def test_decision_issuer_separates_run_contract_directory(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744516427: operator input contains exactly run contracts.
    from benchmarks.codegraph_compare import decision_contract_issuer as issuer
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(issuer, "secure_key", lambda *_args: (descriptor, b"\x44" * 32))
    monkeypatch.setattr(
        issuer,
        "issue",
        lambda *_args, **_kwargs: (
            {"decision_id": "d" * 64},
            [
                {"cell": {"repo_id": repo, "arm_id": arm}}
                for repo, arm in EXPECTED_CELLS
            ],
        ),
    )
    output = tmp_path / "issued"

    result = issuer.main(
        [
            "--plans-dir",
            str(tmp_path),
            "--private-key",
            str(tmp_path / "unused.key"),
            "--output-dir",
            str(output),
        ]
    )

    assert result == 0
    assert sorted(path.name for path in output.glob("*.json")) == [
        "decision-contract.json"
    ]
    assert len(list((output / "run_contracts").glob("*.json"))) == 14


def test_decision_consumer_rejects_stale_verifier_runtime_identity():
    # PR #1249 review 3744516428: verdict runtime must match root-signed config.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64}
    envelope = {
        "manifest_sha256": "a" * 64,
        "decision_id": "d" * 64,
        "decision_contract_sha256": hashlib.sha256(
            consumer.canonical_json_bytes(contract)
        ).hexdigest(),
        "challenge": "b" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 1,
        "verdict": {},
        "service_identity": {"stale": True},
        "consumption_record": {},
        "ledger_head": {},
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": "0" * 128,
    }

    with pytest.raises(ValueError, match="verifier identity mismatch"):
        consumer.verify_verdict_envelope(envelope, contract, config)


@pytest.mark.parametrize(
    ("statement", "message"),
    (
        ("UPDATE events SET counter=3 WHERE counter=2", "counter discontinuity"),
        (
            "UPDATE events SET prev_hash=printf('%064d',9) WHERE counter=2",
            "previous hash mismatch",
        ),
        (
            "UPDATE events SET record_hash=printf('%064d',8) WHERE counter=2",
            "record hash mismatch",
        ),
        ("UPDATE meta SET head_hash=printf('%064d',7)", "meta head mismatch"),
        ("UPDATE challenges SET state='CONSUMED'", "materialized state mismatch"),
    ),
)
def test_verifier_ledger_startup_rejects_persisted_chain_corruption(
    tmp_path: Path, monkeypatch, statement: str, message: str
):
    # PR #1249 review 3744588266: no lease may extend a corrupted durable chain.
    import sqlite3

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    leases = []
    monkeypatch.setattr(
        ChallengeLedger, "_acquire_lease", lambda _self: leases.append("lease")
    )
    path = tmp_path / "verifier.sqlite"
    ledger = ChallengeLedger(path)
    challenge = ledger.begin("a" * 64)["challenge"]
    ledger.start_verifying("a" * 64, challenge)
    db = sqlite3.connect(path)
    try:
        db.execute(statement)
        db.commit()
    finally:
        db.close()
    leases.clear()

    with pytest.raises(ValueError, match=message):
        ChallengeLedger(path)

    assert leases == []


def test_decision_receipt_rejects_stale_configured_service_identity():
    # PR #1249 review 3744588264: a retained key cannot authorize an old runtime.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64}
    envelope = {"manifest_sha256": "e" * 64}
    body = {
        "schema_version": 1,
        "decision_id": contract["decision_id"],
        "decision_contract_sha256": hashlib.sha256(
            canonical_json_bytes(contract)
        ).hexdigest(),
        "manifest_sha256": envelope["manifest_sha256"],
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": {"stale": True},
    }
    reply = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex(),
    }

    with pytest.raises(ValueError, match="not bound"):
        consumer._verify_decision_receipt(reply, contract, envelope, config)


def test_decision_ledger_startup_rejects_corrupt_persisted_receipt(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744588266: decision SQLite is validated before listening.
    import sqlite3

    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    parent = tmp_path / "decision-ledger"
    parent.mkdir(mode=0o700)
    real_stat = consumer.os.stat

    def service_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(st_uid=904, st_mode=stat.S_IFDIR | 0o700)
        return metadata

    monkeypatch.setattr(consumer.os, "stat", service_stat)
    monkeypatch.setattr(consumer.os, "access", lambda *_args: True)
    path = parent / "decisions.sqlite"
    consumer.DecisionLedger(path, _qualification_v3_public_config())
    db = sqlite3.connect(path)
    try:
        db.execute(
            "INSERT INTO consumed VALUES(?,?,?,?,?)",
            ("a" * 64, "b" * 64, "c" * 64, 1, b"{}\n"),
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(ValueError, match="receipt is not canonical"):
        consumer.DecisionLedger(path, _qualification_v3_public_config())


def test_verifier_envelope_build_failure_durably_terminalizes_verifying(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744677886: an envelope persistence failure cannot strand VERIFYING.
    import sqlite3

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")
    manifest = "a" * 64
    challenge = ledger.begin(manifest)["challenge"]
    ledger.start_verifying(manifest, challenge)

    with pytest.raises(OSError, match="signing failed"):
        ledger.finish_with_envelope(
            manifest,
            challenge,
            lambda _record, _head: (_ for _ in ()).throw(OSError("signing failed")),
        )
    assert ledger.recover_envelope_or_fail(manifest, challenge) is None
    database = sqlite3.connect(ledger.path)
    try:
        state = database.execute(
            "SELECT state FROM challenges WHERE challenge=?", (challenge,)
        ).fetchone()[0]
    finally:
        database.close()

    assert state == "FAILED"


def test_decision_ledger_startup_verifies_persisted_receipt_signature(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744728250: logical receipt corruption fails before listen.
    import sqlite3

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import decision_consumer_service as consumer
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    parent = tmp_path / "signed-decision-ledger"
    parent.mkdir(mode=0o700)
    real_stat = consumer.os.stat

    def service_stat(path, *args, **kwargs):
        metadata = real_stat(path, *args, **kwargs)
        if Path(path) == parent:
            return SimpleNamespace(
                st_uid=904, st_mode=__import__("stat").S_IFDIR | 0o700
            )
        return metadata

    monkeypatch.setattr(consumer.os, "stat", service_stat)
    monkeypatch.setattr(consumer.os, "access", lambda *_args: True)
    config = _qualification_v3_public_config()
    path = parent / "decisions.sqlite"
    consumer.DecisionLedger(path, config)
    body = {
        "schema_version": 1,
        "decision_id": "a" * 64,
        "decision_contract_sha256": "d" * 64,
        "manifest_sha256": "c" * 64,
        "verdict_status": "SETUP_QUALIFIED",
        "consumed_at_ns": 1,
        "service_identity": config["trusted"]["decision_consumer_runtime"][
            "measurement"
        ],
    }
    signature = (
        Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
        .sign(consumer.RECEIPT_DOMAIN + canonical_json_bytes(body))
        .hex()
    )
    receipt = {
        "receipt": body,
        "key_id": config["decision_consumer"]["key_id"],
        "algorithm": "Ed25519",
        "signature": ("0" if signature[0] != "0" else "1") + signature[1:],
    }
    db = sqlite3.connect(path)
    try:
        db.execute(
            "INSERT INTO consumed VALUES(?,?,?,?,?)",
            ("a" * 64, "b" * 64, "c" * 64, 1, canonical_json_bytes(receipt)),
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(ValueError, match="signature invalid"):
        consumer.DecisionLedger(path, config)


def test_decision_ledger_rechecks_expiry_inside_transaction(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744776126: lock wait cannot permit post-expiry consumption.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    ledger = object.__new__(consumer.DecisionLedger)
    ledger.path = tmp_path / "decision.sqlite"
    captured = []
    monkeypatch.setattr(consumer.time, "time_ns", lambda: 100)

    with pytest.raises(TimeoutError, match="expired before consumption"):
        ledger.consume(
            {"decision_id": "a" * 64, "decision_nonce": "b" * 64, "expires_at_ns": 100},
            "c" * 64,
            lambda consumed_at: captured.append(consumed_at) or {},
        )

    assert captured == []


def test_decision_ledger_binds_receipt_and_row_to_transaction_timestamp(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744776126: one in-transaction timestamp binds durable facts.
    import sqlite3

    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    ledger = object.__new__(consumer.DecisionLedger)
    ledger.path = tmp_path / "decision.sqlite"
    database = sqlite3.connect(ledger.path)
    database.execute(
        "CREATE TABLE consumed(decision_id TEXT PRIMARY KEY,decision_nonce TEXT UNIQUE NOT NULL,manifest_sha256 TEXT NOT NULL,consumed_at_ns INTEGER NOT NULL,receipt_json BLOB NOT NULL)"
    )
    database.close()
    monkeypatch.setattr(consumer.time, "time_ns", lambda: 101)

    receipt = ledger.consume(
        {"decision_id": "a" * 64, "decision_nonce": "b" * 64, "expires_at_ns": 102},
        "c" * 64,
        lambda consumed_at: {"consumed_at_ns": consumed_at},
    )
    database = sqlite3.connect(ledger.path)
    try:
        row_time = database.execute(
            "SELECT consumed_at_ns FROM consumed WHERE decision_id=?", ("a" * 64,)
        ).fetchone()[0]
    finally:
        database.close()

    assert receipt["consumed_at_ns"] == 101
    assert row_time == 101


def test_verifier_expired_after_semantics_transitions_failed_without_envelope(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744915235: expiry immediately before commit is FAILED.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "deadline.sqlite")
    digest = "a" * 64
    challenge = ledger.begin(digest)["challenge"]
    ticks = iter((9, 10))
    monkeypatch.setattr(verifier_service.time, "monotonic_ns", lambda: next(ticks))
    monkeypatch.setattr(
        verifier_service,
        "_load_manifest",
        lambda *_args, **_kwargs: (
            {"cells": []},
            digest,
            challenge,
            "b" * 64,
            "c" * 64,
        ),
    )
    monkeypatch.setattr(verifier_service, "aggregate_verdict", lambda *_a, **_k: {})
    monkeypatch.setattr(verifier_service, "_validate_verdict_schema", lambda _v: None)

    with pytest.raises(TimeoutError, match="service contract deadline expired"):
        verifier_service._verify(
            {
                "manifest_sha256": digest,
                "challenge": challenge,
                "deadline_monotonic_ns": 10,
            },
            {},
            tmp_path,
            tmp_path,
            Ed25519PrivateKey.generate(),
            ledger,
            {},
        )
    database = sqlite3.connect(ledger.path)
    try:
        state = database.execute(
            "SELECT state FROM challenges WHERE challenge=?", (challenge,)
        ).fetchone()[0]
        verdict_count = database.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    finally:
        database.close()

    assert (state, verdict_count) == ("FAILED", 0)


def test_verifier_file_hash_checks_absolute_deadline(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744944740: large evidence hashes cannot outlive service work.
    from benchmarks.codegraph_compare import verifier

    evidence = tmp_path / "evidence.bin"
    evidence.write_bytes(b"payload")
    monkeypatch.setattr(verifier.time, "monotonic", lambda: 10.0)

    with pytest.raises(TimeoutError, match="hashing deadline expired"):
        verifier._sha_file(evidence, deadline_monotonic=10.0)


_mark_posix_qualification_section_tests()
