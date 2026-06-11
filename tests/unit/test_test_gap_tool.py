#!/usr/bin/env python3

import pytest

from tree_sitter_analyzer.mcp.tools.test_gap_tool import CodeGraphTestGapTool
from tree_sitter_analyzer.test_gap_analyzer import _collect_files, analyze_coverage_gaps


@pytest.fixture
def tool(tmp_path):
    t = CodeGraphTestGapTool()
    t.set_project_path(str(tmp_path))
    return t


@pytest.fixture
def project_with_code(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "service.py").write_text(
        "def process(data):\n    return data\n\n"
        "def validate(item):\n    return bool(item)\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_service.py").write_text(
        "def test_process():\n    assert process([]) == []\n"
    )
    return tmp_path


class TestCodeGraphTestGapTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_test_gap"
        assert "inputSchema" in defn

    def test_schema_has_modes(self, tool):
        schema = tool.get_tool_schema()
        mode_enum = schema["properties"]["mode"]["enum"]
        assert "summary" in mode_enum
        assert "gaps" in mode_enum
        assert "file" in mode_enum

    def test_output_format_defaults_to_toon(self, tool):
        # Wave 1b (audit health-03): MCP default is TOON (CLAUDE.md §1).
        # test_gap was the lone tool defaulting to json.
        schema = tool.get_tool_schema()
        assert schema["properties"]["output_format"]["default"] == "toon"

    @pytest.mark.asyncio
    async def test_default_output_is_toon_formatted(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute({"mode": "summary"})
        assert result.get("format") == "toon"
        assert "toon_content" in result

    def test_validate_no_mode(self):
        t = CodeGraphTestGapTool()
        assert t.validate_arguments({})

    def test_validate_invalid_mode(self):
        t = CodeGraphTestGapTool()
        with pytest.raises(ValueError, match="Invalid mode"):
            t.validate_arguments({"mode": "invalid"})

    def test_validate_file_mode_no_path(self):
        t = CodeGraphTestGapTool()
        with pytest.raises(ValueError, match="file_path"):
            t.validate_arguments({"mode": "file"})

    @pytest.mark.asyncio
    async def test_execute_summary(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute({"mode": "summary"})
        assert result["success"] is True
        assert "coverage_pct" in result
        assert "total_production_symbols" in result

    @pytest.mark.asyncio
    async def test_execute_gaps(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        # json mode pins the structured shape; in TOON mode `gaps` is a bulk
        # field carried only inside toon_content (issue #439 strip surface).
        result = await tool.execute({"mode": "gaps", "output_format": "json"})
        assert result["success"] is True
        assert "gaps" in result
        assert isinstance(result["gaps"], list)

    @pytest.mark.asyncio
    async def test_execute_gaps_toon_strips_bulk(self, tool, project_with_code):
        """Issue #439: in TOON mode the gaps list lives only in toon_content."""
        tool.set_project_path(str(project_with_code))
        result = await tool.execute({"mode": "gaps"})
        assert result["success"] is True
        assert "gaps" not in result
        assert "gaps:" in result["toon_content"]

    @pytest.mark.asyncio
    async def test_execute_file_mode(self, tool, project_with_code):
        tool.set_project_path(str(project_with_code))
        result = await tool.execute(
            {
                "mode": "file",
                "file_path": "service.py",
            }
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_no_project_root(self):
        t = CodeGraphTestGapTool()
        result = await t.execute({"mode": "summary"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_empty_project(self, tool, tmp_path):
        tool.set_project_path(str(tmp_path))
        result = await tool.execute({"mode": "gaps"})
        assert result["success"] is True
        assert result["gap_count"] == 0


class TestPackageScopeCollectFiles:
    """Issue #457: max_files cap must not let test dirs crowd out the package tree."""

    def _make_project(self, tmp_path):
        """Multi-package project with a tests/ dir that sorts before pkg/."""
        # Production package with 2 functions
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub").mkdir()
        (tmp_path / "pkg" / "sub" / "module.py").write_text(
            "def alpha():\n    pass\n\ndef beta():\n    pass\n"
        )
        # Root-level utility (production — not in any non-prod dir)
        (tmp_path / "util.py").write_text("def helper():\n    pass\n")
        # tests/ directory with 10 files (sorts before pkg/)
        (tmp_path / "tests").mkdir()
        for i in range(10):
            (tmp_path / "tests" / f"test_x{i:02d}.py").write_text(
                f"def test_func{i}():\n    pass\n"
            )
        return tmp_path

    def test_max_files_cap_counts_production_files_only(self, tmp_path):
        """max_files cap must be reached only by production files.

        Previously a shared counter burned the budget on test files so that
        pkg/sub/module.py was never reached (issue #457).  With the fix, each
        unit of max_files corresponds to exactly one *production* file."""
        project = self._make_project(tmp_path)
        # With max_files=3 we expect exactly 3 production files in the result
        # (util.py + pkg/__init__.py + pkg/sub/module.py).  Previously, 3 test
        # files would have exhausted the budget first and no production file
        # would appear.
        files = _collect_files(str(project), None, max_files=3)
        prod = [(f, lang) for f, lang, t in files if not t]
        assert len(prod) == 3

    def test_tests_collected_after_production_cap_reached(self, tmp_path):
        """Codex P2 (#479): the production cap must not stop the walk.

        With a production dir (app/) sorting BEFORE tests/, exhausting
        max_files on production files used to early-return and skip tests/
        entirely — naming-based matching then misreported covered symbols
        as gaps.  After the fix the walk continues: production collection
        stops at the cap but ALL later test files are still collected."""
        (tmp_path / "app").mkdir()
        for i in range(5):
            (tmp_path / "app" / f"mod{i}.py").write_text(f"def fn{i}():\n    pass\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_mod0.py").write_text("def test_fn0():\n    pass\n")
        files = _collect_files(str(tmp_path), None, max_files=2)
        prod = [f for f, lang, t in files if not t]
        tests = [f for f, lang, t in files if t]
        assert len(prod) == 2
        assert len(tests) == 1
        assert tests[0].endswith("test_mod0.py")

    def test_package_symbols_included_in_scan(self, tmp_path):
        """pkg/sub/module.py symbols must appear in production count even when
        tests/ has many files and sorts before pkg/ (issue #457)."""
        project = self._make_project(tmp_path)
        result = analyze_coverage_gaps(str(project), max_files=5)
        # 2 functions in pkg/sub/module.py + 1 in util.py = 3 prod symbols
        assert result.total_production_symbols == 3

    def test_tests_dir_does_not_count_as_production(self, tmp_path):
        """Files inside tests/ are never counted as production symbols."""
        project = self._make_project(tmp_path)
        result = analyze_coverage_gaps(str(project), max_files=1000)
        # Production files: pkg/__init__.py, pkg/sub/module.py, util.py = 3 files
        assert result.summary["production_files"] == 3

    def test_test_files_still_used_for_naming_coverage(self, tmp_path):
        """Tests inside tests/ are still scanned for naming-convention matching
        even though they do not count as production code."""
        project = self._make_project(tmp_path)
        # test_x00.py contains test_func0 — this does not match alpha/beta/helper
        result = analyze_coverage_gaps(str(project), max_files=1000)
        # All 3 prod symbols should be gaps (test names don't match alpha/beta/helper)
        assert result.gap_count == 3

    def test_non_prod_dirs_excluded_from_production(self, tmp_path):
        """corpus/, examples/, benchmarks/ are treated as non-production dirs."""
        for non_prod in ("corpus", "examples", "benchmarks"):
            d = tmp_path / non_prod
            d.mkdir()
            (d / "sample.py").write_text("def sample_func():\n    pass\n")
        # Single production function in pkg/
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "real.py").write_text("def real_func():\n    pass\n")

        result = analyze_coverage_gaps(str(tmp_path), max_files=1000)
        # Only real_func is a production symbol; sample_func (×3) must not appear
        assert result.total_production_symbols == 1
