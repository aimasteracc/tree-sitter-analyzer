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

    def test_table_full_with_output_format_json_emits_json(self) -> None:
        out = _run(["--table=full", "--output-format=json"])
        # Must be valid JSON.
        parsed = json.loads(out)
        assert "file_path" in parsed
        assert "language" in parsed
