"""Unit tests for project health agent guidance."""

from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace

from tree_sitter_analyzer.mcp.tools import project_health_tool
from tree_sitter_analyzer.mcp.tools.project_health_tool import (
    ProjectHealthTool,
    _build_agent_backlog,
    _build_project_agent_summary,
    _build_project_health_result,
    _build_project_recommendation,
    _is_agent_backlog_candidate,
)


def _run(coro):
    return asyncio.run(coro)


def _score(
    file_path: str,
    grade: str,
    total: float,
    dimensions: dict[str, float] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=file_path,
        grade=grade,
        total=total,
        dimensions=dimensions or {"complexity": total, "size": 95.0},
    )


def test_agent_backlog_orders_weakest_files_and_includes_cli_parity() -> None:
    backlog = _build_agent_backlog(
        [
            _score("src/healthy.py", "A", 94.0),
            _score("src/needs work.py", "C", 72.0, {"complexity": 35.0}),
            _score("src/bad.py", "D", 48.0, {"size": 22.0}),
            _score("src/awful.py", "F", 18.0, {"structure": 12.0}),
        ],
        limit=3,
    )

    assert [item["file"] for item in backlog] == [
        "src/awful.py",
        "src/bad.py",
        "src/needs work.py",
    ]
    assert backlog[0]["priority"] == "critical"
    assert backlog[0]["recommended_mcp_command"] == (
        "refactoring_suggestions(file_path='src/awful.py')"
    )
    assert backlog[0]["recommended_cli_command"] == (
        "uv run python -m tree_sitter_analyzer src/awful.py --refactor --format json"
    )
    assert backlog[0]["safety_mcp_command"] == (
        "safe_to_edit(file_path='src/awful.py')"
    )
    assert backlog[0]["safety_cli_command"] == (
        "uv run python -m tree_sitter_analyzer "
        "src/awful.py --safe-to-edit --format json"
    )
    assert backlog[0]["post_edit_commands"][-1] == "uv run pytest -q"

    c_grade_item = backlog[2]
    assert c_grade_item["priority"] == "medium"
    assert (
        "check_file_health(file_path='src/needs work.py')"
        in (c_grade_item["recommended_mcp_command"])
    )
    assert "weak: complexity" in c_grade_item["recommended_mcp_command"]
    assert c_grade_item["recommended_cli_command"] == (
        "uv run python -m tree_sitter_analyzer "
        "'src/needs work.py' --file-health --format json"
    )
    assert c_grade_item["post_edit_commands"][0] == (
        "uv run python -m tree_sitter_analyzer "
        "'src/needs work.py' --file-health --format json"
    )


def test_agent_backlog_skips_demo_fixture_queue_heads() -> None:
    backlog = _build_agent_backlog(
        [
            _score("examples/BigService.java", "D", 10.0),
            _score("tests/golden_masters/full/java_bigservice_full.md", "F", 5.0),
            _score("README.md", "D", 12.0),
            _score("src/runtime.py", "D", 58.0),
        ],
        limit=3,
    )

    assert [item["file"] for item in backlog] == ["src/runtime.py"]


def test_project_health_top_targets_skip_demo_fixture_queue_heads() -> None:
    result = _build_project_health_result(
        root="/repo",
        all_scores=[
            _score("examples/BigService.java", "D", 10.0),
            _score("tests/golden_masters/full/java_bigservice_full.md", "F", 5.0),
            _score("README.md", "D", 12.0),
            _score("src/runtime.py", "D", 58.0),
        ],
        min_grade="D",
        max_files=3,
    )

    assert [item["file"] for item in result["top_refactoring_targets"]] == [
        "src/runtime.py"
    ]
    assert result["agent_summary"]["queue_head"]["file"] == "src/runtime.py"


def test_agent_backlog_candidate_keeps_source_and_test_code() -> None:
    assert _is_agent_backlog_candidate(_score("src/runtime.py", "D", 58.0))
    assert _is_agent_backlog_candidate(_score("tests/unit/test_runtime.py", "D", 58.0))
    assert not _is_agent_backlog_candidate(_score("examples/demo.py", "D", 10.0))


def test_project_health_execute_exposes_agent_backlog(monkeypatch, tmp_path) -> None:
    scores = [
        _score("src/healthy.py", "A", 94.0),
        _score("src/bad.py", "D", 48.0, {"size": 22.0}),
    ]

    class FakeHealthScorer:
        def score_project(self, project_root: str) -> list[SimpleNamespace]:
            assert project_root == str(tmp_path)
            return scores

    monkeypatch.setattr(project_health_tool, "HealthScorer", FakeHealthScorer)

    tool = ProjectHealthTool(project_root=str(tmp_path))
    result = _run(
        tool.execute({"min_grade": "D", "max_files": 10, "output_format": "json"})
    )

    assert result["success"] is True
    assert result["agent_summary"]["risk"] == "high"
    assert result["agent_summary"]["queue_head"]["file"] == "src/bad.py"
    assert result["agent_summary"]["safety_command"].endswith(
        "--safe-to-edit --format json"
    )
    assert result["agent_backlog"][0]["file"] == "src/bad.py"
    assert result["agent_backlog"][0]["recommended_cli_command"].endswith(
        "--refactor --format json"
    )
    assert result["agent_backlog"][0]["safety_cli_command"].endswith(
        "--safe-to-edit --format json"
    )


def test_project_health_max_files_controls_agent_visible_lists(
    monkeypatch,
    tmp_path,
) -> None:
    scores = [
        _score("src/bad.py", "D", 48.0, {"size": 22.0}),
        _score("src/worse.py", "D", 47.0, {"complexity": 18.0}),
        _score("src/ok.py", "C", 70.0, {"coverage": 35.0}),
    ]

    class FakeHealthScorer:
        def score_project(self, project_root: str) -> list[SimpleNamespace]:
            assert project_root == str(tmp_path)
            return scores

    monkeypatch.setattr(project_health_tool, "HealthScorer", FakeHealthScorer)

    tool = ProjectHealthTool(project_root=str(tmp_path))
    result = _run(
        tool.execute({"min_grade": "C", "max_files": 1, "output_format": "json"})
    )

    assert result["matching_file_count"] == 3
    assert result["detail_limit"] == 1
    assert result["detail_count"] == 1
    assert result["hidden_detail_count"] == 2
    assert [item["file"] for item in result["files"]] == ["src/worse.py"]
    assert [item["file"] for item in result["top_refactoring_targets"]] == [
        "src/worse.py"
    ]
    assert [item["file"] for item in result["agent_backlog"]] == ["src/worse.py"]
    assert "--max-files 1" in result["agent_summary"]["project_health_command"]


def test_project_health_result_marks_coverage_unavailable_without_coverage_scores() -> (
    None
):
    scores = [
        _score("src/bad.py", "D", 48.0, {"size": 22.0, "complexity": 14.0}),
        _score("src/worse.py", "D", 30.0, {"size": 18.0, "complexity": 10.0}),
    ]

    result = _build_project_health_result(
        root="/repo",
        all_scores=scores,
        min_grade="D",
        max_files=10,
    )

    assert result["coverage_status"] == "unavailable"
    assert result["average_dimensions"]["coverage"] is None
    assert result["weakest_dimension"] == "complexity"


def test_project_health_result_marks_coverage_available_when_present() -> None:
    scores = [
        _score(
            "src/bad.py",
            "D",
            48.0,
            {"size": 22.0, "complexity": 14.0, "coverage": 12.5},
        ),
        _score(
            "src/worse.py",
            "D",
            30.0,
            {"size": 18.0, "complexity": 10.0, "coverage": 25.0},
        ),
    ]

    result = _build_project_health_result(
        root="/repo",
        all_scores=scores,
        min_grade="D",
        max_files=10,
    )

    assert result["coverage_status"] == "available"
    assert result["average_dimensions"]["coverage"] == 18.8
    assert result["weakest_dimension"] == "complexity"


def test_project_recommendation_handles_clean_projects() -> None:
    recommendation = _build_project_recommendation(
        Counter({"A": 2, "B": 1}),
        "complexity",
        total=3,
    )

    assert (
        recommendation
        == "All 3 files are grade C or better. Project health looks good."
    )


def test_project_agent_summary_handles_clean_project() -> None:
    summary = _build_project_agent_summary(
        root="/repo",
        total_files=3,
        grade_distribution={"A": 2, "B": 1, "C": 0, "D": 0, "F": 0},
        weakest_dim="coverage",
        agent_backlog=[],
    )

    assert summary["risk"] == "low"
    assert summary["backlog_count"] == 0
    assert summary["next_step"] == "No project-health queue item needs action."
    assert summary["verification_command"] == "uv run pytest -q"


def test_project_agent_summary_promotes_f_grade_queue_head() -> None:
    backlog = _build_agent_backlog(
        [
            _score("src/awful.py", "F", 10.0, {"structure": 5.0}),
            _score("src/ok.py", "C", 70.0, {"coverage": 35.0}),
        ]
    )
    summary = _build_project_agent_summary(
        root="/repo",
        total_files=2,
        grade_distribution={"A": 0, "B": 0, "C": 1, "D": 0, "F": 1},
        weakest_dim="structure",
        agent_backlog=backlog,
    )

    assert summary["risk"] == "critical"
    assert summary["queue_head"]["priority"] == "critical"
    assert summary["queue_head_command"].endswith("--refactor --format json")
    assert summary["next_step"].startswith("Run safe-to-edit")
