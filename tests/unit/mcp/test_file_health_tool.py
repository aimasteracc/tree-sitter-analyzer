"""Unit tests for FileHealthTool."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
from tree_sitter_analyzer.mcp.tools.utils.file_health_response import (
    build_file_health_result,
)
from tree_sitter_analyzer.mcp.tools.utils.file_health_smells import (
    _add_high_coupling_smell,
    _add_low_complexity_smell,
    _add_low_structure_smell,
    _check_deep_nesting,
    _check_god_class,
    _check_heuristic_long_methods,
    _check_long_functions,
    _check_technical_debt,
)
from tree_sitter_analyzer.models import Function


def _run(coro):
    return asyncio.run(coro)


def test_tool_definition_exposes_file_health_contract() -> None:
    tool = FileHealthTool()

    definition = tool.get_tool_definition()

    assert definition["name"] == "check_file_health"
    assert definition["inputSchema"]["required"] == ["file_path"]
    assert "output_format" in definition["inputSchema"]["properties"]


def test_validate_arguments_requires_non_empty_file_path() -> None:
    tool = FileHealthTool()

    with pytest.raises(ValueError, match="file_path is required"):
        tool.validate_arguments({})
    with pytest.raises(ValueError, match="file_path must be a non-empty string"):
        tool.validate_arguments({"file_path": ""})


def test_execute_scores_file_and_returns_agent_signal(tmp_path) -> None:
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def greet(name: str) -> str:\n    return f'hello {name}'\n",
        encoding="utf-8",
    )

    tool = FileHealthTool(project_root=str(tmp_path))
    result = _run(
        tool.execute(
            {
                "file_path": "src/example.py",
                "language": "python",
                "output_format": "json",
            }
        )
    )

    assert result["success"] is True
    assert result["file_path"] == "src/example.py"
    assert result["grade"] in {"A", "B", "C", "D", "F"}
    assert isinstance(result["dimensions"], dict)
    assert isinstance(result["code_smells"], list)
    assert isinstance(result["recommendation"], str)
    assert "agent_summary" in result
    assert "next_step" in result["agent_summary"]
    assert "agent_next_action" in result
    assert "priority" in result["agent_next_action"]


def test_execute_reports_missing_file_with_clear_error(tmp_path) -> None:
    tool = FileHealthTool(project_root=str(tmp_path))

    with pytest.raises(ValueError, match="File not found: missing.py"):
        _run(tool.execute({"file_path": "missing.py", "output_format": "json"}))


def test_file_health_result_marks_healthy_files_as_no_action() -> None:
    health = SimpleNamespace(
        grade="A",
        total=96.0,
        dimensions={"complexity": 95.0, "size": 98.0},
    )

    result = build_file_health_result(
        "src/healthy.py", health, [], "/tmp/healthy.py", None
    )

    assert result["agent_next_action"] == {
        "priority": "none",
        "reason": "file is healthy enough; no immediate refactor needed",
        "mcp_command": "",
        "cli_command": "",
        "post_edit_commands": [],
    }
    assert result["agent_summary"] == {
        "risk": "none",
        "grade": "A",
        "score": 96.0,
        "weakest_dimension": "complexity",
        "weakest_score": 95.0,
        "next_step": "No immediate refactor needed.",
        "verification_command": (
            "uv run python -m tree_sitter_analyzer "
            "src/healthy.py --file-health --format json"
        ),
        "stop_condition": "File remains grade A/B with no actionable smells.",
    }


def test_file_health_result_includes_direct_agent_commands_for_smells() -> None:
    health = SimpleNamespace(
        grade="C",
        total=72.0,
        dimensions={"complexity": 35.0, "size": 90.0},
    )
    smells = [
        {
            "smell": "long_method",
            "detail": "'run' is 80 lines (L12)",
            "severity": "warning",
            "fix": "Extract helper functions",
        }
    ]

    result = build_file_health_result(
        "src/needs work.py", health, smells, "/tmp/x.py", None
    )
    action = result["agent_next_action"]

    assert action["priority"] == "medium"
    assert action["reason"] == "grade C with actionable smell(s): long_method"
    assert (
        action["mcp_command"]
        == "refactoring_suggestions(file_path='src/needs work.py')"
    )
    assert action["cli_command"] == (
        "uv run python -m tree_sitter_analyzer "
        "'src/needs work.py' --refactor --format json"
    )
    assert action["post_edit_commands"] == [
        (
            "uv run python -m tree_sitter_analyzer "
            "'src/needs work.py' --file-health --format json"
        ),
        "uv run python -m tree_sitter_analyzer --change-impact --format json",
    ]
    assert result["agent_summary"] == {
        "risk": "medium",
        "grade": "C",
        "score": 72.0,
        "weakest_dimension": "complexity",
        "weakest_score": 35.0,
        "next_step": (
            "Run refactoring suggestions: uv run python -m tree_sitter_analyzer "
            "'src/needs work.py' --refactor --format json"
        ),
        "verification_command": (
            "uv run python -m tree_sitter_analyzer "
            "'src/needs work.py' --file-health --format json"
        ),
        "stop_condition": (
            "Re-run uv run python -m tree_sitter_analyzer "
            "'src/needs work.py' --file-health --format json and confirm "
            "the grade improves or smell_count drops."
        ),
        "target_smell": "long_method",
    }


def test_agent_summary_avoids_refactor_when_smell_is_generic_complexity() -> None:
    health = SimpleNamespace(
        grade="C",
        total=76.0,
        dimensions={"complexity": 28.0, "size": 95.0},
    )
    smells = [
        {
            "smell": "high_complexity",
            "detail": "Complexity score: 28/100",
            "severity": "warning",
            "fix": "Break complex functions into smaller, focused ones",
        }
    ]

    result = build_file_health_result(
        "src/service.py", health, smells, "/tmp/x.py", None
    )

    assert result["agent_summary"]["next_step"] == (
        "Inspect the weakest health dimension and make a focused cleanup."
    )
    assert result["agent_summary"]["target_smell"] == "high_complexity"


def test_agent_summary_surfaces_target_symbol_and_detail() -> None:
    health = SimpleNamespace(
        grade="C",
        total=76.0,
        dimensions={"complexity": 28.0, "size": 95.0},
    )
    smells = [
        {
            "smell": "high_complexity",
            "detail": "Complexity score: 28/100; inspect 'run_pipeline' at L42",
            "severity": "warning",
            "fix": "Break complex functions into smaller, focused ones",
            "line": 42,
            "symbol": "run_pipeline",
        }
    ]

    result = build_file_health_result(
        "src/service.py", health, smells, "/tmp/x.py", None
    )

    assert result["agent_summary"]["target_smell"] == "high_complexity"
    assert result["agent_summary"]["target_line"] == 42
    assert result["agent_summary"]["target_symbol"] == "run_pipeline"
    assert result["agent_summary"]["target_detail"] == (
        "Complexity score: 28/100; inspect 'run_pipeline' at L42"
    )


def test_low_complexity_smell_reports_largest_function_location() -> None:
    smells: list[dict[str, object]] = []
    analysis = SimpleNamespace(
        elements=[
            Function(name="small", start_line=3, end_line=8),
            Function(name="run_pipeline", start_line=20, end_line=95),
        ]
    )

    _add_low_complexity_smell(
        smells,
        {"complexity": 24.0},
        ["def small():", "    pass"],
        analysis,
    )

    assert smells == [
        {
            "smell": "high_complexity",
            "detail": "Complexity score: 24/100; inspect 'run_pipeline' at L20",
            "severity": "warning",
            "line": 20,
            "symbol": "run_pipeline",
            "fix": "Break complex functions into smaller, focused ones",
        }
    ]


def test_low_complexity_smell_falls_back_to_control_flow_line() -> None:
    smells: list[dict[str, object]] = []

    _add_low_complexity_smell(
        smells,
        {"complexity": 8.0},
        ["def handle(value):", "    if value:", "        return value"],
        None,
    )

    assert smells == [
        {
            "smell": "high_complexity",
            "detail": "Complexity score: 8/100; first control-flow branch at L2",
            "severity": "critical",
            "line": 2,
            "fix": "Break complex functions into smaller, focused ones",
        }
    ]


def test_low_structure_smell_reports_deepest_line_when_available() -> None:
    smells: list[dict[str, object]] = []
    lines = [
        "def handle(value):",
        "    if value:",
        "        for item in value:",
        "            if item.ready:",
        "                while item.pending:",
        "                    return item",
    ]

    _add_low_structure_smell(smells, {"structure": 20.0}, lines)

    assert smells == [
        {
            "smell": "deep_nesting",
            "detail": "Structure score: 20/100 - deep nesting detected near L6",
            "severity": "warning",
            "fix": "Flatten nesting with early returns, guard clauses, or extract helper functions",
            "line": 6,
            "nesting_depth": 5,
        }
    ]


def test_high_coupling_smell_reports_import_cluster_line() -> None:
    smells: list[dict[str, object]] = []

    _add_high_coupling_smell(
        smells,
        {"dependencies": 12.0},
        ["from pathlib import Path", "import json", "def run(): pass"],
    )

    assert smells == [
        {
            "smell": "high_coupling",
            "detail": "Dependency score: 12/100; import cluster starts near L1",
            "severity": "warning",
            "fix": "Reduce imports - consider dependency injection or facade pattern",
            "line": 1,
        }
    ]


def test_deep_nesting_reports_actionable_line_number() -> None:
    smells: list[dict[str, object]] = []
    lines = [
        "def handle(value):",
        "    if value:",
        "        for item in value:",
        "            if item.ready:",
        "                while item.pending:",
        "                    if item.retry:",
        "                        return item",
    ]

    _check_deep_nesting(smells, lines)

    assert smells == [
        {
            "smell": "deep_nesting",
            "detail": "Max nesting depth: 6 at L7 (recommended < 4)",
            "severity": "warning",
            "line": 7,
            "fix": "Extract nested logic into helper functions or use early returns",
        }
    ]


def test_deep_nesting_ignores_multiline_data_literals() -> None:
    smells: list[dict[str, object]] = []
    lines = [
        "def schema():",
        "    return {",
        '        "properties": {',
        '            "include_skeleton": {',
        '                "description": (',
        '                    "Include code skeletons in extraction plans "',
        '                    "(default: false, saves tokens)"',
        "                ),",
        "            },",
        "        },",
        "    }",
    ]

    _check_deep_nesting(smells, lines)

    assert smells == []


def test_god_class_requires_exactly_one_oversized_class() -> None:
    smells: list[dict[str, object]] = []

    _check_god_class(smells, line_count=400, classes=[])
    _check_god_class(
        smells,
        line_count=420,
        classes=[
            {"name": "One", "line": 1, "end_line": 350},
            {"name": "Two", "line": 351, "end_line": 420},
        ],
    )
    _check_god_class(
        smells,
        line_count=450,
        classes=[{"name": "Small", "line": 10, "end_line": 100}],
    )

    assert smells == []


def test_god_class_reports_actionable_symbol_location() -> None:
    smells: list[dict[str, object]] = []

    _check_god_class(
        smells,
        line_count=420,
        classes=[{"name": "HugeService", "line": 12, "end_line": 380}],
    )

    assert smells == [
        {
            "smell": "god_class",
            "detail": "Single class 'HugeService' spans 369 lines",
            "severity": "warning",
            "line": 12,
            "symbol": "HugeService",
            "fix": "Extract responsibilities into separate classes (Single Responsibility Principle)",
        }
    ]


def test_long_function_smells_report_symbol_and_line() -> None:
    smells: list[dict[str, object]] = []

    _check_long_functions(
        smells,
        [
            {"name": "small", "line": 3, "lines": 12},
            {"name": "large", "line": 30, "lines": 75},
        ],
    )

    assert smells == [
        {
            "smell": "long_method",
            "detail": "'large' is 75 lines (L30)",
            "severity": "warning",
            "line": 30,
            "symbol": "large",
            "fix": "Extract logical sections into separate helper methods",
        }
    ]


def test_heuristic_long_method_smells_report_symbol_and_line() -> None:
    smells: list[dict[str, object]] = []
    lines = ["def bulky():"] + ["    value = 1"] * 55

    _check_heuristic_long_methods(smells, lines)

    assert smells == [
        {
            "smell": "long_method",
            "detail": "'bulky' is ~56 lines (L1)",
            "severity": "warning",
            "line": 1,
            "symbol": "bulky",
            "fix": "Extract logical sections into separate helper methods",
        }
    ]


def test_technical_debt_ignores_marker_strings_in_code() -> None:
    smells: list[dict[str, object]] = []
    lines = [
        'TECH_DEBT_MARKERS = ("TODO", "FIXME", "HACK", "XXX")',
        'text = "TODO in a string literal"',
        "pattern = r'FIXME|HACK|XXX'",
        "def has_marker(value):",
        "    return 'TODO' in value",
        "markers = ['TODO', 'FIXME', 'HACK', 'XXX']",
    ]

    _check_technical_debt(smells, lines)

    assert smells == []


def test_technical_debt_reports_first_comment_line() -> None:
    smells: list[dict[str, object]] = []
    lines = [
        "def work():",
        "    pass  # TODO: split this",
        "    # FIXME: cover edge case",
        "    // HACK: generated fixture",
        "    /* XXX: old parser */",
        "    <!-- TODO: docs -->",
        "    -- FIXME: sql note",
    ]

    _check_technical_debt(smells, lines)

    assert smells == [
        {
            "smell": "technical_debt",
            "detail": "6 TODO/FIXME/HACK markers",
            "severity": "info",
            "line": 2,
            "fix": "Resolve or create issues for outstanding TODOs",
        }
    ]


def test_god_class_reports_single_oversized_class_span() -> None:
    smells: list[dict[str, object]] = []

    _check_god_class(
        smells,
        line_count=450,
        classes=[{"name": "LargeController", "line": 10, "end_line": 330}],
    )

    assert smells == [
        {
            "smell": "god_class",
            "detail": "Single class 'LargeController' spans 321 lines",
            "severity": "warning",
            "line": 10,
            "symbol": "LargeController",
            "fix": "Extract responsibilities into separate classes (Single Responsibility Principle)",
        }
    ]


# ---------------------------------------------------------------------------
# Binary + empty file guards (regression for bugs M6 + M7)
#
# Before the fix:
#   - Binary files (.pyc) were scored grade F with an empty-string dimension
#     leak in the recommendation.
#   - 0-byte files were scored grade B / SAFE with a confusing
#     ``large_file`` signal.
# ---------------------------------------------------------------------------


def test_file_health_binary_file(tmp_path) -> None:
    """Bug M6 regression: refuse to analyze binary files cleanly."""
    binary = tmp_path / "test_module.pyc"
    binary.write_bytes(b"\x42\x0d\x0d\x0a\x00\x00\x00\x00" + b"\xff" * 200)

    tool = FileHealthTool(project_root=str(tmp_path))
    result = _run(tool.execute({"file_path": str(binary), "output_format": "json"}))

    assert result["success"] is False
    assert result["error_type"] == "binary_file"
    assert "binary" in result["error"].lower()
    assert result["file_path"] == str(binary)
    assert result["agent_summary"]["verdict"] == "ERROR"
    assert result["agent_summary"]["next_step"] == "skip"


def test_file_health_empty_file(tmp_path) -> None:
    """Bug M7 regression: 0-byte file returns an n/a envelope, never grade B."""
    empty = tmp_path / "empty.py"
    empty.write_text("", encoding="utf-8")

    tool = FileHealthTool(project_root=str(tmp_path))
    result = _run(tool.execute({"file_path": str(empty), "output_format": "json"}))

    assert result["success"] is True
    assert result["grade"] == "N/A"
    assert result["verdict"] == "n/a"
    assert result["signal"] == "empty_file"
    assert "empty" in result["recommendation"].lower()
    # The follow-up actions must be no-ops — agents must not chain refactor
    # commands on a 0-byte file.
    assert result["agent_next_action"]["mcp_command"] == ""
    assert result["agent_next_action"]["post_edit_commands"] == []
