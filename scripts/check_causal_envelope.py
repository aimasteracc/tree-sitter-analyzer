#!/usr/bin/env python3
"""Dogfood the P1 one-call causal-envelope contract."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

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


async def _check(project_root: Path, file_path: str) -> dict[str, Any]:
    tool = SafeToEditTool(str(project_root))
    result = await tool.execute(
        {"file_path": file_path, "edit_type": "refactor", "output_format": "json"}
    )
    envelope = result.get("causal_envelope")
    fields = frozenset(envelope) if isinstance(envelope, dict) else frozenset()
    missing = sorted(CAUSAL_FIELDS - fields)
    return {
        "success": result.get("success") is True and not missing,
        "analyzer_calls": 1,
        "separate_causality_queries": 0,
        "file_path": file_path,
        "missing_fields": missing,
        "verification_command": (
            envelope.get("verification_command") if isinstance(envelope, dict) else None
        ),
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
