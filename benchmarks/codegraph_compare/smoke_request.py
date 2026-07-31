"""Strict command-boundary parsing for manifest-backed Smoke execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.integrity import (
    ExperimentManifestV1,
    parse_manifest_v1,
)


def parse_manifest_request(
    *,
    manifest_path: str | Path | None,
    setup_only: bool,
    dry_run: bool,
    index_evidence_path: str | Path | None,
    strict_json_loader: Any,
) -> ExperimentManifestV1 | None:
    """Validate CLI option relationships and parse one immutable manifest."""

    if setup_only and not manifest_path:
        raise ValueError("--setup-only requires --manifest <experiment-manifest.json>")
    if setup_only and dry_run:
        raise ValueError("--setup-only cannot be combined with --dry-run")
    if setup_only and not index_evidence_path:
        raise ValueError(
            "--setup-only requires --index-evidence <index-evidence.json>"
        )
    if index_evidence_path and not manifest_path:
        raise ValueError("--index-evidence requires --manifest")
    if manifest_path and not index_evidence_path:
        raise ValueError("--manifest requires --index-evidence <index-evidence.json>")
    if not manifest_path:
        return None
    try:
        return parse_manifest_v1(strict_json_loader(manifest_path))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid experiment manifest {manifest_path}: {exc}") from exc
