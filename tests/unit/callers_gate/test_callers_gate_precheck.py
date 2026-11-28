"""Local patch coverage of ``precheck`` counts lines the way Codecov does."""

from __future__ import annotations

from pathlib import Path

from benchmarks.callers_gate import precheck

PKG = "tree_sitter_analyzer/mcp/tools/callers_x.py"


def test_patch_coverage_counts_hits_misses_and_partials(tmp_path: Path) -> None:
    cov = {
        "files": {
            PKG: {
                "executed_lines": [1, 2, 3, 5],
                "missing_lines": [4],
                "missing_branches": [[3, 5]],
            }
        }
    }
    lines = {PKG: {2, 3, 4, 6}, "docs/x.md": {1}, "benchmarks/y.py": {1}}
    hits, misses, partials, uncovered = precheck.patch_coverage(cov, tmp_path, lines)
    # line 6 is not a statement (neither executed nor missing): not counted
    assert (hits, misses, partials) == (1, 1, 1)
    assert uncovered == [f"{PKG}:3 (partial)", f"{PKG}:4"]


def test_a_changed_module_no_test_imported_counts_every_statement_as_missed(
    tmp_path: Path,
) -> None:
    module = tmp_path / PKG
    module.parent.mkdir(parents=True)
    module.write_text("import os\n\n\ndef f():\n    return os.sep\n", encoding="utf-8")
    hits, misses, partials, _ = precheck.patch_coverage(
        {"files": {}}, tmp_path, {PKG: {1, 2, 4, 5}}
    )
    assert (hits, misses, partials) == (0, 3, 0)


def test_judge_patch_fails_below_target_and_without_a_target(tmp_path: Path) -> None:
    cov = {"files": {PKG: {"executed_lines": [1], "missing_lines": [2]}}}
    lines = {PKG: {1, 2}}
    logs: list[str] = []
    assert precheck._judge_patch(cov, tmp_path, lines, 50.0, logs.append) is True
    assert precheck._judge_patch(cov, tmp_path, lines, 90.51, logs.append) is False
    assert precheck._judge_patch(cov, tmp_path, lines, None, logs.append) is False
    assert any(
        "50.00% (1 hit, 1 miss, 0 partial) vs target 90.51%: FAIL" in m for m in logs
    )
    assert (
        precheck._judge_patch(cov, tmp_path, {"docs/a.md": {1}}, 99.0, logs.append)
        is True
    )
