"""Issue #1376：test_benchmark_harness_service_ledger 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

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


def test_decision_ledger_requires_uid_904_private_writable_parent(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744261023: SQLite WAL 需要服务自身拥有的私有父目录。
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


def test_decision_issuer_separates_run_contract_directory(tmp_path: Path, monkeypatch):
    # PR #1249 review 3744516427: operator 输入精确包含运行契约。
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


def test_decision_receipt_rejects_stale_configured_service_identity():
    # PR #1249 review 3744588264: 留存密钥不能授权旧的运行时身份。
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
    # PR #1249 review 3744588266: decision SQLite 必须在监听前验证。

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


def test_decision_ledger_startup_verifies_persisted_receipt_signature(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744728250: receipt 的逻辑损坏必须在监听之前失败。

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
    # PR #1249 review 3744776126: 等待锁不能允许在过期后消耗请求。
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
    # PR #1249 review 3744776126: 用同一个事务内时间戳绑定持久事实。

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


_mark_posix_qualification_section_tests()
