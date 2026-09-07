"""Issue #1376：test_benchmark_harness_verifier_ledger 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_verifier_ledger_is_private_and_owned_by_service_uid(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744178813: verifier 的 USER 903 必须拥有其可写账本。

    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ChallengeLedger(tmp_path / "ledger.sqlite")
    metadata = (tmp_path / "ledger.sqlite").stat()
    assert metadata.st_uid == os.geteuid()
    assert stat.S_IMODE(metadata.st_mode) == 0o600


def test_verifier_manifest_parser_uses_64mib_protocol_not_receipt_limits():
    # PR #1249 review 3744261030: exact-14 manifest 具有独立的帧界限。
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


def test_verifier_ledger_consumed_transition_persists_canonical_envelope_atomically(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744400335: 已提交的 CONSUMED 事实必须能恢复其 envelope。
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
    # PR #1249 review 3744516421: 重试返回已经提交的 challenge。
    from benchmarks.codegraph_compare.verifier_ledger import ChallengeLedger

    monkeypatch.setattr(ChallengeLedger, "_acquire_lease", lambda _self: None)
    ledger = ChallengeLedger(tmp_path / "verifier.sqlite")

    first = ledger.begin("a" * 64)
    second = ledger.begin("a" * 64)

    assert second == first
    assert ledger.head()["counter"] == 1


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
    # PR #1249 review 3744588266: 任何租约都不能延长已损坏的持久链。
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


def test_verifier_envelope_build_failure_durably_terminalizes_verifying(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744677886: envelope 持久化失败不能遗留 VERIFYING 状态。
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


def test_verifier_expired_after_semantics_transitions_failed_without_envelope(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744915235: 在提交前一刻过期必须转为 FAILED。
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
    # PR #1249 review 3744944740: 大证据的哈希操作不能超过服务工作的截止时间。
    from benchmarks.codegraph_compare import verifier

    evidence = tmp_path / "evidence.bin"
    evidence.write_bytes(b"payload")
    monkeypatch.setattr(verifier.time, "monotonic", lambda: 10.0)

    with pytest.raises(TimeoutError, match="hashing deadline expired"):
        verifier._sha_file(evidence, deadline_monotonic=10.0)


_mark_posix_qualification_section_tests()
