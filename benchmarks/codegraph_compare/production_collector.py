"""Append-only Evidence Collector for NO1-002D production trust.

This module implements the Evidence Collector role defined in issue #1223.
All writes use O_CREAT | O_EXCL so existing files are never overwritten.
The artifact root must not exist before collection begins; the collector
creates it and owns it exclusively until finalize() is called.

The resulting CollectionReceipt contains a SHA-256 ledger of every artifact,
suitable for binding into a JudgeRecord or SpendAttestation.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactReceipt:
    """Immutable record of a single collected artifact."""

    kind: str
    run_id: str
    path: str
    sha256: str


@dataclass(frozen=True)
class CollectionReceipt:
    """Immutable summary of an evidence collection session.

    The ledger_sha256 is the SHA-256 of the canonical JSON serialisation of
    all (kind, run_id, sha256) tuples, sorted by run_id then kind.  This
    provides a single digest that binds the entire collection.
    """

    root: str
    artifact_count: int
    ledger_sha256: str
    artifacts: tuple[ArtifactReceipt, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "artifact_count": self.artifact_count,
            "ledger_sha256": self.ledger_sha256,
            "artifacts": [
                {
                    "kind": a.kind,
                    "run_id": a.run_id,
                    "path": a.path,
                    "sha256": a.sha256,
                }
                for a in self.artifacts
            ],
        }


class EvidenceCollector:
    """Append-only evidence collector backed by an exclusive filesystem root.

    Usage::

        collector = EvidenceCollector(Path("/evidence/run-001"))
        collector.collect("cell-1", "transcript", transcript_bytes)
        collector.collect("cell-1", "receipt", receipt_bytes)
        receipt = collector.finalize()

    After finalize() is called, further collect() calls raise RuntimeError.
    The artifact_root directory is created with mode 0o700 and must not exist
    beforehand; the caller is responsible for ensuring the path is outside
    every evidence bundle and source checkout.
    """

    def __init__(self, artifact_root: Path) -> None:
        if artifact_root.exists():
            raise ValueError(
                f"Artifact root must not pre-exist; cannot guarantee immutability: "
                f"{artifact_root}"
            )
        artifact_root.mkdir(parents=True, mode=0o700)
        self._root = artifact_root
        self._artifacts: list[ArtifactReceipt] = []
        self._finalized = False

    @property
    def root(self) -> Path:
        return self._root

    def collect(self, run_id: str, kind: str, payload: bytes) -> ArtifactReceipt:
        """Write payload to a new exclusive file and return an immutable receipt.

        Raises:
            RuntimeError: If the collector has already been finalised.
            ValueError: If run_id or kind contain path separators.
            FileExistsError: If an artifact with the same (run_id, kind) already exists.
        """
        if self._finalized:
            raise RuntimeError("Collector is already finalised; no further artifacts accepted")
        if not run_id or "/" in run_id or "\\" in run_id or "." in run_id:
            raise ValueError(f"run_id must be a plain identifier without separators: {run_id!r}")
        if not kind or "/" in kind or "\\" in kind or "." in kind:
            raise ValueError(f"kind must be a plain identifier without separators: {kind!r}")
        filename = f"{run_id}_{kind}"
        target = self._root / filename
        descriptor = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            raise
        digest = hashlib.sha256(payload).hexdigest()
        receipt = ArtifactReceipt(
            kind=kind,
            run_id=run_id,
            path=str(target.resolve()),
            sha256=digest,
        )
        self._artifacts.append(receipt)
        return receipt

    def finalize(self) -> CollectionReceipt:
        """Close the collection and return an immutable summary receipt.

        After this call, collect() raises RuntimeError.

        Raises:
            RuntimeError: If the collector was already finalised.
        """
        if self._finalized:
            raise RuntimeError("Collector is already finalised")
        self._finalized = True
        sorted_artifacts = sorted(
            self._artifacts, key=lambda a: (a.run_id, a.kind)
        )
        ledger_entries = [
            {"kind": a.kind, "run_id": a.run_id, "sha256": a.sha256}
            for a in sorted_artifacts
        ]
        ledger_bytes = json.dumps(
            ledger_entries,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        ledger_digest = hashlib.sha256(ledger_bytes).hexdigest()
        return CollectionReceipt(
            root=str(self._root.resolve()),
            artifact_count=len(self._artifacts),
            ledger_sha256=ledger_digest,
            artifacts=tuple(sorted_artifacts),
        )
