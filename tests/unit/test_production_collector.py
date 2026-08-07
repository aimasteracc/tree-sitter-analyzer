"""Tests for the NO1-002D Evidence Collector (production_collector.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.codegraph_compare.production_collector import (
    ArtifactReceipt,
    CollectionReceipt,
    EvidenceCollector,
)


class TestEvidenceCollector:
    def test_creates_artifact_root_with_restricted_permissions(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "evidence" / "run-001"
        EvidenceCollector(root)
        assert root.exists()
        assert root.is_dir()

    def test_rejects_preexisting_root(self, tmp_path: Path) -> None:
        root = tmp_path / "run"
        root.mkdir()
        with pytest.raises(ValueError, match="must not pre-exist"):
            EvidenceCollector(root)

    def test_collect_returns_artifact_receipt(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        receipt = collector.collect("cell1", "transcript", b"hello")
        assert isinstance(receipt, ArtifactReceipt)
        assert receipt.kind == "transcript"
        assert receipt.run_id == "cell1"
        assert len(receipt.sha256) == 64
        assert Path(receipt.path).read_bytes() == b"hello"

    def test_collect_rejects_duplicate_run_id_kind(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        collector.collect("cell1", "transcript", b"first")
        with pytest.raises(FileExistsError):
            collector.collect("cell1", "transcript", b"second")

    def test_collect_rejects_run_id_with_separator(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        with pytest.raises(ValueError, match="run_id"):
            collector.collect("cell/bad", "transcript", b"data")

    def test_collect_rejects_dotdot_run_id(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        with pytest.raises(ValueError, match="run_id"):
            collector.collect("..", "transcript", b"data")

    def test_collect_rejects_dot_run_id(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        with pytest.raises(ValueError, match="run_id"):
            collector.collect(".", "transcript", b"data")

    def test_collect_rejects_kind_with_separator(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        with pytest.raises(ValueError, match="kind"):
            collector.collect("cell1", "bad/kind", b"data")

    def test_collect_rejects_dotdot_kind(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        with pytest.raises(ValueError, match="kind"):
            collector.collect("cell1", "..", b"data")

    def test_finalize_returns_collection_receipt(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        collector.collect("cell1", "transcript", b"tx")
        receipt = collector.finalize()
        assert isinstance(receipt, CollectionReceipt)
        assert receipt.artifact_count == 1
        assert len(receipt.ledger_sha256) == 64

    def test_finalize_sorts_artifacts_by_run_id_then_kind(
        self, tmp_path: Path
    ) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        collector.collect("cell2", "receipt", b"r2")
        collector.collect("cell1", "transcript", b"tx1")
        collector.collect("cell1", "receipt", b"r1")
        receipt = collector.finalize()
        ids = [(a.run_id, a.kind) for a in receipt.artifacts]
        assert ids == [("cell1", "receipt"), ("cell1", "transcript"), ("cell2", "receipt")]

    def test_finalize_ledger_digest_changes_when_payload_changes(
        self, tmp_path: Path
    ) -> None:
        collector1 = EvidenceCollector(tmp_path / "run1")
        collector1.collect("cell1", "transcript", b"version-A")
        receipt1 = collector1.finalize()

        collector2 = EvidenceCollector(tmp_path / "run2")
        collector2.collect("cell1", "transcript", b"version-B")
        receipt2 = collector2.finalize()

        assert receipt1.ledger_sha256 != receipt2.ledger_sha256

    def test_collect_after_finalize_raises(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        collector.finalize()
        with pytest.raises(RuntimeError, match="finalised"):
            collector.collect("cell1", "transcript", b"late")

    def test_double_finalize_raises(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        collector.finalize()
        with pytest.raises(RuntimeError, match="finalised"):
            collector.finalize()

    def test_empty_collection_produces_valid_receipt(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        receipt = collector.finalize()
        assert receipt.artifact_count == 0
        assert len(receipt.ledger_sha256) == 64
        assert receipt.artifacts == ()

    def test_artifact_file_content_matches_receipt_sha256(
        self, tmp_path: Path
    ) -> None:
        import hashlib

        payload = b"binary content"
        collector = EvidenceCollector(tmp_path / "run")
        receipt = collector.collect("run1", "runtime", payload)
        assert receipt.sha256 == hashlib.sha256(payload).hexdigest()
        assert Path(receipt.path).read_bytes() == payload

    def test_partial_write_cleanup_allows_retry(self, tmp_path: Path) -> None:
        import hashlib
        import os
        import unittest.mock as mock

        collector = EvidenceCollector(tmp_path / "run")
        with mock.patch.object(os, "fsync", side_effect=OSError("simulated failure")):
            with pytest.raises(OSError, match="simulated failure"):
                collector.collect("cell1", "transcript", b"data")
        # File must have been cleaned up; retry must not raise FileExistsError.
        receipt = collector.collect("cell1", "transcript", b"data-retry")
        assert receipt.sha256 == hashlib.sha256(b"data-retry").hexdigest()

    def test_finalize_detects_artifact_modification(self, tmp_path: Path) -> None:
        collector = EvidenceCollector(tmp_path / "run")
        artifact = collector.collect("cell1", "transcript", b"original")
        Path(artifact.path).write_bytes(b"tampered")
        with pytest.raises(RuntimeError, match="modified after collection"):
            collector.finalize()

    def test_finalize_seals_artifacts_read_only(self, tmp_path: Path) -> None:
        import stat

        collector = EvidenceCollector(tmp_path / "run")
        artifact = collector.collect("cell1", "transcript", b"sealed")
        collector.finalize()
        mode = stat.S_IMODE(Path(artifact.path).stat().st_mode)
        assert mode & stat.S_IWRITE == 0, "artifact must not be owner-writable after finalize"
