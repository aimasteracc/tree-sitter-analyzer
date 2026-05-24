"""Unit tests for project health agent guidance."""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
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

        def score_project_with_stats(self, project_root: str):
            return self.score_project(project_root), {}

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

        def score_project_with_stats(self, project_root: str):
            return self.score_project(project_root), {}

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


class TestF9DescriptionAndBudget:
    """Regression tests for F9 — round-16b dogfood found that the MCP
    description advertised ``30s–3min`` while a 4k-file repo actually
    took ~5min, so agents that obeyed the documented budget timed out
    and abandoned the call. Two contracts now hold:

    1. The tool description mentions realistic numbers (4min / 5min+)
       and tells callers to read ``agent_summary.budget_seconds``.
    2. ``agent_summary.summary_line`` includes ``estimated_seconds=`` —
       and ``actual_seconds=`` when the executing tool measured the run.
    """

    def test_description_mentions_realistic_timing(self) -> None:
        """The description must NOT keep claiming ``30s–3min`` for
        anything bigger than a small repo — that's what tripped agents."""
        tool = ProjectHealthTool()
        definition = tool.get_tool_definition()
        description = definition["description"]
        # Anchor on the realistic numbers from the bucketed estimator.
        assert "4min" in description or "5min" in description, (
            "description must surface realistic upper-bound timing so "
            "agents budget correctly on large repos"
        )
        # The old misleading "30s–3min" string must be gone.
        assert "3min" not in description, (
            "stale ceiling — 4k-file repos take 5min, not 3min"
        )
        # And callers should know where to read the real number.
        assert "budget_seconds" in description

    def test_agent_summary_summary_line_includes_estimated_seconds(self) -> None:
        """summary_line must expose ``estimated_seconds=`` so the dispatch
        post-hook can emit a budget hint at the envelope level."""
        backlog = _build_agent_backlog(
            [_score("src/bad.py", "D", 30.0, {"size": 18.0})]
        )
        summary = _build_project_agent_summary(
            root="/repo",
            total_files=450,
            grade_distribution={"A": 100, "B": 50, "C": 290, "D": 10, "F": 0},
            weakest_dim="size",
            agent_backlog=backlog,
        )
        # No actual_seconds passed → only the estimate should appear.
        assert "estimated_seconds=" in summary["summary_line"]
        assert "actual_seconds=" not in summary["summary_line"]
        assert summary["budget_seconds"]["estimated"] > 0
        assert summary["budget_seconds"]["actual"] is None

    def test_agent_summary_summary_line_includes_actual_seconds_when_measured(
        self,
    ) -> None:
        """When the calling tool measured the scan, both ``estimated_seconds``
        and ``actual_seconds`` must reach the summary_line — the post-hook
        relies on the actual number for the budget hint."""
        backlog: list = []
        summary = _build_project_agent_summary(
            root="/repo",
            total_files=4500,
            grade_distribution={"A": 1000, "B": 500, "C": 3000, "D": 0, "F": 0},
            weakest_dim="complexity",
            agent_backlog=backlog,
            actual_seconds=287.4,
        )
        assert "estimated_seconds=" in summary["summary_line"]
        assert "actual_seconds=287.4" in summary["summary_line"]
        assert summary["budget_seconds"]["estimated"] >= 240  # 3k+ files bucket
        assert summary["budget_seconds"]["actual"] == 287.4

    def test_estimate_seconds_scales_with_project_size(self) -> None:
        """The size-based estimate must be monotonic and align with the
        documented buckets so the description stays accurate."""
        from tree_sitter_analyzer.mcp.tools.project_health_tool import (
            _estimate_seconds,
        )

        assert _estimate_seconds(50) <= _estimate_seconds(500)
        assert _estimate_seconds(500) <= _estimate_seconds(2500)
        assert _estimate_seconds(2500) <= _estimate_seconds(5000)
        # 4k-file repo (round-16b case) should land in the 5min+ bucket.
        assert _estimate_seconds(4500) >= 300


class TestQ4ProjectHealthExcludesNonCode:
    """Round-33 Q4: project_health was inflating total_files ~3x by
    grading ``.md`` / ``.yaml`` / ``.html`` golden_masters as code. The
    walker must pre-filter to extensions that map to a registered
    language plugin so the docs/fixtures bucket never reaches the
    scorer."""

    def test_source_extension_set_is_code_only(self) -> None:
        """``PROJECT_HEALTH_SOURCE_EXTS`` must be a strict subset of the
        extensions that ``_EXT_TO_LANG`` actually maps to a language —
        otherwise the scorer falls back to ``language=None`` and grades
        documentation as if it were code."""
        from tree_sitter_analyzer.health_scorer import (
            _EXT_TO_LANG,
            PROJECT_HEALTH_SOURCE_EXTS,
        )

        unknown = PROJECT_HEALTH_SOURCE_EXTS - set(_EXT_TO_LANG.keys())
        assert unknown == set(), (
            f"project_health would score files with no language plugin: "
            f"{sorted(unknown)}"
        )
        # Spot-check: the doc/markup extensions that round-33 surfaced as
        # offenders must not be in the scan set.
        for ext in (".md", ".yaml", ".yml", ".html", ".css", ".sql", ".txt"):
            assert ext not in PROJECT_HEALTH_SOURCE_EXTS, (
                f"{ext} is documentation/markup, not code — must not be scored"
            )

    def test_walker_skips_markdown_in_project_scan(self, tmp_path) -> None:
        """Even when a ``.md`` file sits next to source code, the project
        walker must not enumerate it. The pre-filter happens before
        score_file is called."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        (tmp_path / "main.py").write_text("def f():\n    return 1\n")
        (tmp_path / "README.md").write_text("# docs\n\nsome paragraph\n")
        (tmp_path / "config.yaml").write_text("key: value\n")
        (tmp_path / "page.html").write_text("<html><body>hi</body></html>")

        results = HealthScorer().score_project(str(tmp_path))
        names = {Path(score.file_path).name for score in results}

        assert "main.py" in names
        assert "README.md" not in names
        assert "config.yaml" not in names
        assert "page.html" not in names


class TestQ4ProjectHealthExcludesGoldenMasters:
    """Round-33 Q4: ``tests/golden_masters/**`` holds snapshots of
    expected MCP output. Even when an ``.md`` golden master sneaks back
    in via a future extension change, the walker must drop the entire
    fixture tree so it never leaks into the C-grade bucket."""

    def test_walker_skips_golden_masters_directory(self, tmp_path) -> None:
        from tree_sitter_analyzer.health_scorer import HealthScorer

        # Real source file that should be scored.
        (tmp_path / "main.py").write_text("def f():\n    return 1\n")

        # Golden masters that must NOT be enumerated.
        gm = tmp_path / "tests" / "golden_masters"
        gm.mkdir(parents=True)
        (gm / "snapshot.py").write_text("x = 1\n")  # even .py under gm
        (gm / "java_bigservice_full.py").write_text(
            "def something():\n    return None\n"
        )

        results = HealthScorer().score_project(str(tmp_path))
        names = {Path(score.file_path).name for score in results}

        assert "main.py" in names
        assert "snapshot.py" not in names
        assert "java_bigservice_full.py" not in names

    def test_walker_skips_fixture_and_test_data_directories(self, tmp_path) -> None:
        from tree_sitter_analyzer.health_scorer import HealthScorer

        (tmp_path / "main.py").write_text("def f():\n    return 1\n")
        for sub in ("fixtures", "test_data", "golden"):
            d = tmp_path / "tests" / sub
            d.mkdir(parents=True)
            (d / "sample.py").write_text("x = 1\n")

        results = HealthScorer().score_project(str(tmp_path))
        names = {Path(score.file_path).name for score in results}

        # Only the project source survives the walker filter.
        assert names == {"main.py"}

    def test_existing_fixture_self_scan_still_works(self) -> None:
        """When the scanned root *is* a fixture sub-tree, the walker
        must compute the exclusion relative to the scanned root so the
        fixture-self-test in ``test_health_scorer.py:test_score_project``
        keeps working."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        fixture = (
            Path(__file__).parent.parent.parent
            / "fixtures"
            / "project_graph"
            / "health_project"
        )
        results = HealthScorer().score_project(str(fixture))
        names = {Path(score.file_path).name for score in results}
        # The two known fixture files must still show up.
        assert "healthy.py" in names
        assert "unhealthy.py" in names


class TestQ5ProjectHealthAgentSummaryFileCount:
    """Round-33 Q5: ``agent_summary`` must be self-contained — consumers
    parsing ``agent_summary`` fields shouldn't have to fall back to
    string-parsing the headline ``summary_line`` to recover the file
    count."""

    def test_agent_summary_exposes_file_count(self) -> None:
        summary = _build_project_agent_summary(
            root="/repo",
            total_files=42,
            grade_distribution={"A": 10, "B": 15, "C": 12, "D": 4, "F": 1},
            weakest_dim="complexity",
            agent_backlog=[],
        )

        assert summary["file_count"] == 42
        # ``total_files`` stays as the legacy key — file_count is the
        # cross-tool alias.
        assert summary["total_files"] == 42

    def test_agent_summary_exposes_grade_distribution(self) -> None:
        summary = _build_project_agent_summary(
            root="/repo",
            total_files=42,
            grade_distribution={"A": 10, "B": 15, "C": 12, "D": 4, "F": 1},
            weakest_dim="complexity",
            agent_backlog=[],
        )

        assert summary["grade_distribution"] == {
            "A": 10,
            "B": 15,
            "C": 12,
            "D": 4,
            "F": 1,
        }

    def test_file_count_matches_top_level_total_files(self) -> None:
        """The two file-count fields (top-level ``total_files`` and
        ``agent_summary.file_count``) must always agree, even on a real
        end-to-end build_result call."""
        scores = [
            _score("src/a.py", "A", 95.0),
            _score("src/b.py", "B", 85.0),
            _score("src/c.py", "C", 72.0),
            _score("src/d.py", "D", 55.0, {"complexity": 30.0}),
        ]

        result = _build_project_health_result(
            root="/repo",
            all_scores=scores,
            min_grade="D",
            max_files=10,
        )

        assert result["agent_summary"]["file_count"] == result["total_files"]
        assert result["agent_summary"]["file_count"] == 4
