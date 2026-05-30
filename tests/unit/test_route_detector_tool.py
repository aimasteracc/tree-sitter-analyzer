"""Tests for RouteDetectorTool MCP layer (schema validation and execute modes)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool
from tree_sitter_analyzer.route_detector import RouteDetector

# ---------------------------------------------------------------------------
# MCP tool layer — schema validation
# ---------------------------------------------------------------------------


class TestRouteDetectorToolSchema:
    def test_get_tool_definition_name(self):
        defn = RouteDetectorTool().get_tool_definition()
        assert defn["name"] == "detect_routes"
        assert "inputSchema" in defn

    def test_validate_lookup_requires_url_pattern(self):
        with pytest.raises(ValueError, match="url_pattern"):
            RouteDetectorTool().validate_arguments({"mode": "lookup"})

    def test_validate_prefix_requires_url_pattern(self):
        with pytest.raises(ValueError, match="url_pattern"):
            RouteDetectorTool().validate_arguments({"mode": "prefix"})

    def test_validate_file_requires_file_path(self):
        with pytest.raises(ValueError, match="file_path"):
            RouteDetectorTool().validate_arguments({"mode": "file"})

    def test_validate_summary_no_args(self):
        assert RouteDetectorTool().validate_arguments({"mode": "summary"})


# ---------------------------------------------------------------------------
# MCP tool layer — execute modes
# ---------------------------------------------------------------------------


class TestRouteDetectorToolExecute:
    @staticmethod
    def _run(tool: RouteDetectorTool, args: dict) -> dict:
        return asyncio.run(tool.execute(args))

    def test_execute_summary_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert result["success"] is True
        assert result["mode"] == "summary"
        assert result["total_routes"] == 3

    def test_execute_all_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(tool, {"mode": "all", "output_format": "json"})
        assert result["success"] is True
        assert result["route_count"] == 3
        assert len(result["routes"]) == 3

    def test_execute_all_with_framework_filter(self, multi_framework_project: Path):
        tool = RouteDetectorTool(str(multi_framework_project))
        result = self._run(
            tool,
            {"mode": "all", "framework": "flask", "output_format": "json"},
        )
        assert all(r["framework"] == "flask" for r in result["routes"])

    def test_execute_lookup_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(
            tool,
            {"mode": "lookup", "url_pattern": "/healthz", "output_format": "json"},
        )
        assert result["match_count"] == 1
        assert result["routes"][0]["handler_name"] == "healthz"

    def test_execute_prefix_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(
            tool,
            {"mode": "prefix", "url_pattern": "/api", "output_format": "json"},
        )
        assert result["match_count"] == 1

    def test_execute_file_mode(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        result = self._run(
            tool,
            {
                "mode": "file",
                "file_path": str(flask_project / "app.py"),
                "output_format": "json",
            },
        )
        assert result["route_count"] == 3

    def test_execute_unknown_mode_raises(self, flask_project: Path):
        tool = RouteDetectorTool(str(flask_project))
        # validate_arguments does not catch unknown modes; the dispatch in
        # execute() raises ValueError for any mode outside the documented set.
        with pytest.raises((ValueError, KeyError)):
            self._run(tool, {"mode": "bogus", "output_format": "json"})

    def test_file_mode_runs_path_through_validator(
        self, flask_project: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Security regression: file mode must route agent-supplied paths
        through BaseMCPTool.resolve_and_validate_file_path before parsing."""
        tool = RouteDetectorTool(str(flask_project))
        seen: list[str] = []
        original = tool.resolve_and_validate_file_path

        def spy(path: str) -> str:
            seen.append(path)
            return original(path)

        monkeypatch.setattr(tool, "resolve_and_validate_file_path", spy)
        self._run(
            tool,
            {
                "mode": "file",
                "file_path": str(flask_project / "app.py"),
                "output_format": "json",
            },
        )
        assert seen == [str(flask_project / "app.py")]

    def test_file_mode_rejects_path_traversal(self, flask_project: Path):
        """Security regression: file mode must reject ../ escapes."""
        tool = RouteDetectorTool(str(flask_project))
        with pytest.raises((ValueError, Exception)):
            self._run(
                tool,
                {
                    "mode": "file",
                    "file_path": "../../../etc/passwd",
                    "output_format": "json",
                },
            )

    def test_walk_skips_symlinks_outside_project(self, tmp_path: Path):
        """Security regression: rglob must not follow symlinks that escape project root."""
        import os

        project = tmp_path / "proj"
        project.mkdir()
        (project / "app.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n"
            "@app.route('/inside')\ndef inside(): pass\n"
        )
        # Sneak in a symlink pointing at a sibling tree that contains a file
        # with a fake route — must be ignored.
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "leak.py").write_text("@app.route('/leak')\ndef leak(): pass")
        try:
            os.symlink(outside, project / "data")
        except OSError:
            pytest.skip("symlinks not supported on this platform")

        routes = RouteDetector(str(project)).detect_all()
        assert all("/leak" not in r.url_pattern for r in routes)
        assert all("/outside/" not in r.file_path for r in routes)

    def test_set_project_path_resets_detector(
        self, flask_project: Path, tmp_path: Path
    ):
        tool = RouteDetectorTool(str(flask_project))
        first = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert first["total_routes"] == 3
        # Repoint at empty dir; cached detector must be reset.
        empty = tmp_path / "empty"
        empty.mkdir()
        tool.set_project_path(str(empty))
        second = self._run(tool, {"mode": "summary", "output_format": "json"})
        assert second["total_routes"] == 0
