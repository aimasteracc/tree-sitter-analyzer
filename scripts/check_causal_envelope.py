#!/usr/bin/env python3
"""Dogfood the P1 one-call causal-envelope contract."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.index_snapshot import lease_existing_snapshot
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
    certified_default_test_command,
)

CAUSAL_FIELDS = frozenset(
    {
        "dependents",
        "dependencies",
        "exercising_tests",
        "constraint_verdict",
        "verification_command",
        "stale_edges",
    }
)


def _invalid_causal_fields(envelope: Any, file_path: str | None = None) -> list[str]:
    """Return certified causal fields whose values violate the P1 contract."""
    if not isinstance(envelope, dict):
        return sorted(CAUSAL_FIELDS)
    invalid: list[str] = []
    fact_names = ("dependents", "dependencies", "exercising_tests", "stale_edges")
    unavailable = all(envelope.get(name) is None for name in fact_names)
    for name in fact_names:
        value = envelope.get(name)
        if unavailable:
            continue
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            invalid.append(name)
    if envelope.get("constraint_verdict") not in {
        "unknown",
        "SAFE",
        "CAUTION",
        "UNSAFE",
    }:
        invalid.append("constraint_verdict")
    verification = envelope.get("verification_command")
    if unavailable and verification is not None:
        invalid.append("verification_command")
    if verification is not None and (
        not isinstance(verification, str) or not verification.strip()
    ):
        invalid.append("verification_command")
    if (
        isinstance(envelope.get("exercising_tests"), list)
        and envelope["exercising_tests"]
        and verification is None
        and (file_path is None or certified_default_test_command(file_path) is not None)
    ):
        invalid.append("verification_command")
    return sorted(set(invalid))


async def _check(project_root: Path, file_path: str) -> dict[str, Any]:
    tool = SafeToEditTool(str(project_root))
    with lease_existing_snapshot(str(project_root)) as snapshot:
        if (
            snapshot.completeness != "complete"
            or snapshot.snapshot_id is None
            or snapshot.source_generation is None
        ):
            return {
                "success": False,
                "analyzer_calls": 0,
                "separate_causality_queries": 0,
                "certified_snapshot": False,
                "file_path": file_path,
                "missing_fields": sorted(CAUSAL_FIELDS),
                "invalid_fields": [],
                "verification_command": None,
                "reason": snapshot.reason or "INDEX_SNAPSHOT_INCOMPLETE",
            }
        result = await tool.execute(
            {
                "file_path": file_path,
                "edit_type": "refactor",
                "access_mode": "read_existing",
                "snapshot_id": snapshot.snapshot_id,
                "source_generation": snapshot.source_generation,
                "output_format": "json",
            }
        )
    envelope = result.get("causal_envelope")
    fields = frozenset(envelope) if isinstance(envelope, dict) else frozenset()
    missing = sorted(CAUSAL_FIELDS - fields)
    invalid = _invalid_causal_fields(envelope, file_path)
    return {
        "success": (
            result.get("success") is True
            and result.get("access_state") == "available"
            and not missing
            and not invalid
        ),
        "analyzer_calls": 1,
        "separate_causality_queries": 0,
        "certified_snapshot": result.get("access_state") == "available",
        "file_path": file_path,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "verification_command": (
            envelope.get("verification_command") if isinstance(envelope, dict) else None
        ),
        "reason": result.get("access_reason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    report = asyncio.run(_check(Path(args.project_root).resolve(), args.file_path))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
