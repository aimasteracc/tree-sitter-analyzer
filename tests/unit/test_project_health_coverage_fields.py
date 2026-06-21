"""Pin the coverage-transparency fields on ``project_health`` output.

Background
----------
Before 2026-05-23 ``project_health`` returned ``total_files`` (the
number of files actually scored) but said NOTHING about how many were
scanned, how many were skipped, or why. When an agent or user asked
"did you really scan my whole project?" the response had no answer.

The dogfood verification (docs/internal/TRUST_BUT_VERIFY_2026-05-23.md)
flagged this as the Q2 ⚠. This test pins the fix so the fields cannot
quietly disappear.

Required fields:
  - total_files_scanned   (rglob hits, pre-filter)
  - total_files_analyzed  (alias of total_files for the scored set)
  - total_files_skipped   (scanned but not scored)
  - skip_reasons          {excluded_dir: N, scoring_failed: N}
  - coverage_pct          (analyzed / scanned * 100, rounded to 0.1)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.project_health_tool import ProjectHealthTool


def _make_project(tmp_path: Path) -> Path:
    # Two well-formed Python files (scored).
    (tmp_path / "a.py").write_text("def a(): return 1\n")
    (tmp_path / "b.py").write_text("def b(): return 2\n")
    # One file under an excluded dir (must be skipped — not scored).
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text("def x(): pass\n")
    return tmp_path


def test_project_health_emits_coverage_fields(tmp_path: Path) -> None:
    """All five coverage-transparency fields must appear in the response."""
    project = _make_project(tmp_path)
    tool = ProjectHealthTool(str(project))
    result = asyncio.run(tool.execute({"output_format": "json", "max_files": 5}))

    for required in (
        "total_files_scanned",
        "total_files_analyzed",
        "total_files_skipped",
        "skip_reasons",
        "coverage_pct",
    ):
        assert required in result, (
            f"project_health missing coverage field {required!r}. "
            f"This breaks the TRUST_BUT_VERIFY_2026-05-23 contract — "
            f"agents need to know how much of the project was actually scanned."
        )


def test_excluded_dirs_show_up_in_skip_reasons(tmp_path: Path) -> None:
    """``__pycache__/ignored.py`` must be counted as excluded_dir skip."""
    project = _make_project(tmp_path)
    tool = ProjectHealthTool(str(project))
    result = asyncio.run(tool.execute({"output_format": "json", "max_files": 5}))

    skip_reasons = result["skip_reasons"]
    # The excluded-dir count must reflect the pycache file we planted.
    assert skip_reasons["excluded_dir"], (
        f"expected at least 1 excluded_dir skip (the __pycache__ file), "
        f"got skip_reasons={skip_reasons}"
    )
    # No scoring failures expected on this trivial fixture.
    assert skip_reasons["scoring_failed"] == 0


def test_coverage_pct_is_consistent(tmp_path: Path) -> None:
    """coverage_pct must equal analyzed / scanned * 100, rounded to 0.1."""
    project = _make_project(tmp_path)
    tool = ProjectHealthTool(str(project))
    result = asyncio.run(tool.execute({"output_format": "json", "max_files": 5}))

    scanned = result["total_files_scanned"]
    analyzed = result["total_files_analyzed"]
    expected = round(100.0 * analyzed / scanned, 1) if scanned else 100.0
    assert result["coverage_pct"] == expected, (
        f"coverage_pct={result['coverage_pct']} disagrees with "
        f"analyzed/scanned*100 ({expected})"
    )


def test_total_files_analyzed_matches_total_files_legacy(tmp_path: Path) -> None:
    """``total_files_analyzed`` is the modern alias of the legacy ``total_files``.

    Both fields are kept for back-compat. They must report the SAME number
    so external consumers can switch over at their own pace.
    """
    project = _make_project(tmp_path)
    tool = ProjectHealthTool(str(project))
    result = asyncio.run(tool.execute({"output_format": "json", "max_files": 5}))

    assert result["total_files"] == result["total_files_analyzed"], (
        "total_files and total_files_analyzed must agree — they're aliases"
    )
