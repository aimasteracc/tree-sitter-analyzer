"""Golden-master regression coverage for Swift output."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.commands.table_command import TableCommand


def _normalize_output(content: str) -> str:
    return content.replace("\r\n", "\n").rstrip() + "\n"


def test_swift_full_table_matches_golden_master(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Swift table output should stay stable across extractor changes."""
    sample_path = Path("examples/sample.swift")
    golden_path = Path("tests/golden_masters/full/swift_sample_full.md")

    if not sample_path.exists():
        pytest.skip(f"Input file not found: {sample_path}")

    args = Namespace(
        file_path=str(sample_path),
        project_root=".",
        table="full",
        language="swift",
        quiet=True,
        partial_read=False,
        include_javadoc=False,
        toon_use_tabs=False,
    )
    exit_code = TableCommand(args).execute()
    captured = capsys.readouterr()

    assert exit_code == 0
    current = captured.out
    expected = golden_path.read_text(encoding="utf-8")

    assert _normalize_output(current) == _normalize_output(expected)
