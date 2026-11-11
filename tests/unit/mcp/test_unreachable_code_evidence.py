"""Unreachable-code answers must carry counted evidence (#1955).

A clean project used to answer ``success: true`` with
``total_functions_analyzed: 0``: the scanner dropped every file without
findings, so the tool summed functions over an empty list. And a scan that
truly analyzed nothing (wrong root, tests only, no functions) also said
success. These tests pin the honest contract for the CLI and MCP paths.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade
from tree_sitter_analyzer.mcp.tools.unreachable_code_tool import UnreachableCodeTool
from tree_sitter_analyzer.unreachable_code import analyze_project_unreachable
from tree_sitter_analyzer.unreachable_code_scan import scan_project_unreachable


def _write(root: Path, rel: str, code: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


_CLEAN = """\
    def f():
        return 1

    def g():
        return 2
"""

_DEAD = """\
    def h():
        return 0
        y = 1
"""


async def _project(root: Path, **extra: object) -> dict:
    tool = UnreachableCodeTool(project_root=str(root))
    return await tool.execute({"mode": "project", **extra})


class TestScanCountsEveryAnalyzedFile:
    def test_clean_files_are_counted(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _CLEAN)
        _write(tmp_path, "pkg/b.py", _DEAD)

        scan = scan_project_unreachable(str(tmp_path))

        assert scan.files_analyzed == 2
        assert scan.functions_analyzed == 3
        assert [r.file_path for r in scan.results] == [str(tmp_path / "pkg/b.py")]

    def test_skipped_test_files_are_counted(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_x.py", _CLEAN)

        scan = scan_project_unreachable(str(tmp_path))

        assert scan.files_analyzed == 0
        assert scan.skipped_test_files == 1

    def test_max_files_marks_truncated(self, tmp_path: Path) -> None:
        for i in range(3):
            _write(tmp_path, f"m{i}.py", _CLEAN)

        scan = scan_project_unreachable(str(tmp_path), max_files=2)

        assert scan.files_analyzed == 2
        assert scan.truncated is True

    def test_legacy_list_api_is_unchanged(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", _CLEAN)
        _write(tmp_path, "b.py", _DEAD)

        results = analyze_project_unreachable(str(tmp_path))

        assert [Path(r.file_path).name for r in results] == ["b.py"]


class TestProjectAnswer:
    @pytest.mark.asyncio
    async def test_clean_project_reports_real_function_count(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "pkg/a.py", _CLEAN)

        resp = await _project(tmp_path)

        assert resp["success"] is True
        assert resp["status"] == "none_found"
        assert resp["verdict"] == "INFO"
        assert resp["files_analyzed"] == 1
        assert resp["total_functions_analyzed"] == 2
        assert resp["total_unreachable_blocks"] == 0

    @pytest.mark.asyncio
    async def test_findings_are_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", _CLEAN)
        _write(tmp_path, "pkg/b.py", _DEAD)

        resp = await _project(tmp_path)

        assert resp["success"] is True
        assert resp["status"] == "unreachable_found"
        assert resp["verdict"] == "CAUTION"
        assert resp["total_functions_analyzed"] == 3
        assert resp["files_with_issues"] == 1

    @pytest.mark.asyncio
    async def test_empty_root_is_unknown_not_success(self, tmp_path: Path) -> None:
        resp = await _project(tmp_path)

        assert resp["success"] is False
        assert resp["status"] == "unknown"
        assert resp["error_code"] == "INSUFFICIENT_EVIDENCE"
        assert resp["total_functions_analyzed"] == 0
        assert "--unreachable-code-mode project --project-root" in resp["next_step"]

    @pytest.mark.asyncio
    async def test_tests_only_names_include_tests_command(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_x.py", _CLEAN)

        resp = await _project(tmp_path)

        assert resp["success"] is False
        assert resp["status"] == "unknown"
        assert resp["skipped_test_files"] == 1
        assert "--unreachable-code-include-tests" in resp["next_step"]
        assert "include_test_files=true" in resp["next_step"]

    @pytest.mark.asyncio
    async def test_files_without_functions_are_unknown(self, tmp_path: Path) -> None:
        _write(tmp_path, "settings.py", "X = 1\nY = 2\n")

        resp = await _project(tmp_path)

        assert resp["success"] is False
        assert resp["status"] == "unknown"
        assert resp["files_analyzed"] == 1
        assert "--outline" in resp["next_step"]
        assert "settings.py" in resp["next_step"]

    @pytest.mark.asyncio
    async def test_truncated_scan_names_larger_max_files(self, tmp_path: Path) -> None:
        for i in range(3):
            _write(tmp_path, f"m{i}.py", _CLEAN)

        resp = await _project(tmp_path, max_files=2)

        assert resp["success"] is True
        assert resp["truncated"] is True
        assert "--unreachable-code-max-files 4" in resp["next_step"]


class TestFileAnswer:
    @pytest.mark.asyncio
    async def test_file_without_functions_is_unknown(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "consts.py", "X = 1\n")
        tool = UnreachableCodeTool(project_root=str(tmp_path))

        resp = await tool.execute({"mode": "file", "file_path": str(path)})

        assert resp["success"] is False
        assert resp["status"] == "unknown"
        assert resp["error_code"] == "INSUFFICIENT_EVIDENCE"
        assert "--outline" in resp["next_step"]

    @pytest.mark.asyncio
    async def test_clean_file_is_none_found(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "a.py", _CLEAN)
        tool = UnreachableCodeTool(project_root=str(tmp_path))

        resp = await tool.execute({"mode": "file", "file_path": str(path)})

        assert resp["success"] is True
        assert resp["status"] == "none_found"
        assert resp["functions_analyzed"] == 2


class TestMcpHealthFacade:
    @pytest.mark.asyncio
    async def test_health_unreachable_empty_root_is_unknown(
        self, tmp_path: Path
    ) -> None:
        facade = build_health_facade(str(tmp_path))

        resp = await facade.execute({"action": "unreachable", "mode": "project"})

        assert resp["success"] is False
        assert resp["status"] == "unknown"
        assert "health action=unreachable" in resp["next_step"]

    @pytest.mark.asyncio
    async def test_health_unreachable_clean_project_counts(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "pkg/a.py", _CLEAN)
        facade = build_health_facade(str(tmp_path))

        resp = await facade.execute({"action": "unreachable", "mode": "project"})

        assert resp["success"] is True
        assert resp["total_functions_analyzed"] == 2
