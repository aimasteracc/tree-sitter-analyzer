from __future__ import annotations

from pathlib import Path

from scripts.ci_route import load_routing_config, route_changed_files

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_routing_config(PROJECT_ROOT / "config" / "ci-routing.yml")


def test_docs_change_keeps_core_gate_but_skips_slow_routes() -> None:
    result = route_changed_files(["docs/README.md"], CONFIG)

    assert result["run_quality"] is True
    assert result["run_test_matrix"] is True
    assert result["run_build"] is True
    assert result["run_benchmarks"] is False
    assert result["run_sql_platform_compat"] is False
    assert result["run_regression"] is False


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
