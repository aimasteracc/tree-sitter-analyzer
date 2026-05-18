"""Unit tests for project overview agent guidance."""

from __future__ import annotations

import asyncio

from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
    ProjectOverviewTool,
    _build_agent_summary,
    _scan_project,
)


def _run(coro):
    return asyncio.run(coro)


def test_project_overview_execute_includes_agent_summary(tmp_path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not source\n", encoding="utf-8")

    tool = ProjectOverviewTool(project_root=str(tmp_path))
    result = _run(
        tool.execute(
            {
                "include_health": False,
                "max_depth": 5,
                "output_format": "json",
            }
        )
    )

    summary = result["agent_summary"]
    assert result["success"] is True
    assert summary["risk"] == "unknown"
    assert summary["top_language"] == "python"
    assert summary["source_files"] == 1
    assert summary["largest_file"] == "src/app.py"
    assert "project_health" in result["tool_routing"]


def test_scan_project_excludes_ignored_directories(tmp_path) -> None:
    visible = tmp_path / "src" / "visible.py"
    ignored = tmp_path / "node_modules" / "hidden.py"
    visible.parent.mkdir()
    ignored.parent.mkdir()
    visible.write_text("print('visible')\n", encoding="utf-8")
    ignored.write_text("print('hidden')\n", encoding="utf-8")

    scan = _scan_project(tmp_path, max_depth=5)

    assert scan["lang_dist"] == {"python": 1}
    assert [item["path"] for item in scan["source_files"]] == ["src/visible.py"]


def test_agent_summary_points_to_project_health_when_health_alert_exists() -> None:
    result = {
        "summary": {"source_files": 2, "languages_count": 1},
        "language_distribution": {"python": 2},
        "largest_source_files": [{"path": "src/large.py"}],
        "health_alert": "1 file(s) scored D or F",
    }

    summary = _build_agent_summary(result, include_health=True)

    assert summary["risk"] == "high"
    assert summary["health_checked"] is True
    assert summary["largest_file"] == "src/large.py"
    assert summary["next_step"].startswith("Run project-health")
