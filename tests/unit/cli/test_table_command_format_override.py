"""Regression tests for DOG-3: --output-format honored when --table is set."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = PROJECT_ROOT / "examples" / "Sample.java"


def _run(args: list[str]) -> str:
    """Run the CLI in-tree and return stdout text."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            str(FIXTURE),
            *args,
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"
    return proc.stdout


@pytest.mark.skipif(not FIXTURE.exists(), reason="examples/Sample.java missing")
class TestTableOutputFormatOverride:
    def test_table_full_default_is_markdown(self) -> None:
        """No --output-format flag = the documented markdown table layout."""
        out = _run(["--table=full"])
        assert out.startswith("# "), (
            "Without --output-format, --table=full must produce markdown.\n"
            f"Got: {out[:200]!r}"
        )

    def test_table_full_with_output_format_toon_emits_toon(self) -> None:
        """DOG-3: --output-format=toon must beat --table=full's default."""
        out = _run(["--table=full", "--output-format=toon"])
        assert "file_path:" in out, (
            "TOON output expected to start with key:value lines, got:\n"
            + out[:200]
        )
        assert not out.startswith("# "), "Should not fall back to markdown"
        # Sanity: contain at least one of the table-typical sections
        # rendered into TOON.
        assert "classes" in out or "package" in out

    def test_table_full_with_output_format_json_emits_json(self) -> None:
        out = _run(["--table=full", "--output-format=json"])
        # Must be valid JSON.
        parsed = json.loads(out)
        assert "file_path" in parsed
        assert "language" in parsed

    def test_table_full_with_short_format_alias_toon(self) -> None:
        """``--format`` (alias) also overrides table layout to TOON."""
        out = _run(["--table=full", "--format=toon"])
        assert "file_path:" in out
        assert not out.startswith("# ")

    def test_toon_is_smaller_than_json_for_same_table_data(self) -> None:
        """The whole point of TOON: significantly fewer bytes than JSON."""
        json_out = _run(["--table=full", "--output-format=json"])
        toon_out = _run(["--table=full", "--output-format=toon"])
        # Project README claims ~73% reduction on similar payloads. Use
        # a conservative 30% floor here so this test isn't fragile to
        # future TOON encoder tweaks.
        assert len(toon_out) < len(json_out) * 0.7, (
            f"TOON should be much smaller than JSON for the same payload: "
            f"json={len(json_out)} toon={len(toon_out)}"
        )

    def test_explicit_table_toon_still_works(self) -> None:
        """Pre-DOG-3 path: --table=toon alone (no --output-format) still emits TOON."""
        out = _run(["--table=toon"])
        assert "file_path:" in out
        assert not out.startswith("# ")
