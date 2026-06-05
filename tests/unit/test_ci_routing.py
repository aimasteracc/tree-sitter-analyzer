from __future__ import annotations

from pathlib import Path

from scripts.ci_route import load_routing_config, route_changed_files

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_routing_config(PROJECT_ROOT / "config" / "ci-routing.yml")


def test_docs_only_change_skips_matrix_runs_docs_check() -> None:
    """A pure docs change skips the heavy Win/macOS test matrix + build, and
    runs the lightweight docs-check instead (which still validates README
    counts/structure). The slow routes stay off."""
    result = route_changed_files(["docs/guide.md", "rfcs/0004-x.md"], CONFIG)

    # Heavy jobs skipped — no point running the full matrix for prose.
    assert result["run_test_matrix"] is False
    assert result["run_build"] is False
    assert result["run_quality"] is False
    # But the cheap docs validation still runs (README count/structure safety).
    assert result["run_docs_check"] is True
    # Slow routes stay off.
    assert result["run_benchmarks"] is False
    assert result["run_sql_platform_compat"] is False
    assert result["run_regression"] is False


def test_readme_change_is_docs_only_but_docs_check_guards_counts() -> None:
    """README.md is docs-only (skips the matrix) but docs-check runs the
    README count/structure tests, so a count drift is still caught."""
    result = route_changed_files(["README.md"], CONFIG)
    assert result["run_test_matrix"] is False
    assert result["run_docs_check"] is True


def test_docs_plus_code_change_runs_full_matrix() -> None:
    """A change that touches BOTH docs and code is NOT docs-only — the full
    matrix runs (docs-only skip must be conservative)."""
    result = route_changed_files(
        ["README.md", "tree_sitter_analyzer/ast_cache.py"], CONFIG
    )
    assert result["run_test_matrix"] is True
    assert result["run_build"] is True
    assert result["run_docs_check"] is False


def test_empty_changeset_is_not_docs_only() -> None:
    """An empty changed-file list must not be misclassified as docs-only."""
    result = route_changed_files([], CONFIG)
    assert result["run_test_matrix"] is True
    assert result["run_docs_check"] is False


def test_ci_workflow_md_change_is_not_docs_only() -> None:
    """A workflow/config change that happens to be docs-shaped still forces the
    full suite (full_suite paths win over docs-only)."""
    result = route_changed_files([".github/workflows/ci.yml"], CONFIG)
    assert result["run_test_matrix"] is True
    assert result["run_docs_check"] is False


def test_sql_plugin_change_routes_sql_and_grammar() -> None:
    result = route_changed_files(
        ["tree_sitter_analyzer/languages/sql_plugin/extractor.py"], CONFIG
    )

    assert result["run_sql_platform_compat"] is True
    assert result["run_grammar_coverage"] is True


def test_workflow_change_forces_full_suite() -> None:
    result = route_changed_files([".github/workflows/ci.yml"], CONFIG)

    assert result["full_suite_required"] is True
    assert result["run_benchmarks"] is True
    assert result["run_regression"] is True
    assert result["run_sql_platform_compat"] is True


def test_regression_scope_is_narrow_when_only_api_changes() -> None:
    result = route_changed_files(["tree_sitter_analyzer/api.py"], CONFIG)

    assert result["run_regression"] is True
    assert result["regression_scope"] == "api"


def test_multiple_regression_scopes_upgrade_to_all() -> None:
    result = route_changed_files(
        ["tree_sitter_analyzer/api.py", "tree_sitter_analyzer/formatters/json.py"],
        CONFIG,
    )

    assert result["run_regression"] is True
    assert result["regression_scope"] == "all"
