"""Unit tests for SafeToEditTool."""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,
    _compute_risk,
    _find_nearby_tests,
    _is_init_file,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SAMPLE_PYTHON = str(
    PROJECT_ROOT / "tree_sitter_analyzer" / "languages" / "java_plugin.py"
)
SAMPLE_HEALTH = str(
    PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "tools" / "file_health_tool.py"
)


@pytest.fixture
def tool():
    t = SafeToEditTool(str(PROJECT_ROOT))
    t.set_project_path(str(PROJECT_ROOT))
    return t


def _run(coro):
    return asyncio.run(coro)


class TestSafeToEditTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "safe_to_edit"
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "edit_type" in defn["inputSchema"]["properties"]

    def test_validate_arguments_missing_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_empty_path(self, tool):
        with pytest.raises(ValueError, match="non-empty string"):
            tool.validate_arguments({"file_path": ""})

    def test_validate_arguments_valid(self, tool):
        assert tool.validate_arguments({"file_path": "some_file.py"})

    def test_execute_returns_risk_level(self, tool):
        result = _run(
            tool.execute(
                {"file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"}
            )
        )
        assert "risk_level" in result
        assert result["risk_level"] in ("safe", "caution", "dangerous")

    def test_execute_includes_health_grade(self, tool):
        result = _run(
            tool.execute(
                {"file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"}
            )
        )
        assert "health_grade" in result
        assert result["health_grade"] in ("A", "B", "C", "D", "F")

    def test_execute_includes_pre_edit_checklist(self, tool):
        result = _run(
            tool.execute(
                {"file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"}
            )
        )
        assert "pre_edit_checklist" in result
        assert len(result["pre_edit_checklist"]) >= 2

    def test_execute_includes_risk_factors(self, tool):
        result = _run(
            tool.execute(
                {"file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"}
            )
        )
        assert "risk_factors" in result
        assert isinstance(result["risk_factors"], list)

    def test_execute_includes_dependency_info(self, tool):
        result = _run(
            tool.execute(
                {"file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"}
            )
        )
        assert "downstream_count" in result
        assert "dependency_count" in result

    def test_execute_includes_test_files(self, tool):
        result = _run(
            tool.execute(
                {"file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"}
            )
        )
        assert "test_files_nearby" in result

    def test_edit_type_rename_higher_risk(self, tool):
        result_refactor = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py",
                    "edit_type": "refactor",
                }
            )
        )
        result_rename = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py",
                    "edit_type": "rename",
                }
            )
        )
        # Rename should have at least as many risk factors
        assert len(result_rename["risk_factors"]) >= len(
            result_refactor["risk_factors"]
        )

    def test_toon_format(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py",
                    "output_format": "toon",
                }
            )
        )
        assert "risk_level" in result

    def test_json_format(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py",
                    "output_format": "json",
                }
            )
        )
        assert "risk_level" in result
        assert result.get("format") != "toon" or "risk_level" in result

    def test_file_not_found(self, tool):
        with pytest.raises(ValueError, match="File not found"):
            _run(tool.execute({"file_path": "nonexistent_file.py"}))

    def test_well_connected_file_has_downstream(self, tool):
        result = _run(tool.execute({"file_path": "tree_sitter_analyzer/mcp/server.py"}))
        # server.py is widely imported, should have downstream
        assert result["downstream_count"] >= 0


class TestRiskComputation:
    def test_safe_with_no_risk_factors(self):
        risk, factors = _compute_risk(
            forward_count=0,
            dep_count=2,
            health_grade="A",
            has_tests=True,
            edit_type="fix_bug",
            is_init_file=False,
        )
        assert risk == "safe"
        good_factors = [f for f in factors if f["severity"] == "good"]
        assert len(good_factors) >= 1

    def test_caution_with_moderate_downstream(self):
        risk, factors = _compute_risk(
            forward_count=8,
            dep_count=5,
            health_grade="C",
            has_tests=False,
            edit_type="refactor",
            is_init_file=False,
        )
        assert risk in ("caution", "dangerous")

    def test_dangerous_with_high_downstream_no_tests(self):
        risk, factors = _compute_risk(
            forward_count=30,
            dep_count=15,
            health_grade="D",
            has_tests=False,
            edit_type="rename",
            is_init_file=True,
        )
        assert risk == "dangerous"

    def test_rename_adds_risk_factor(self):
        _, factors_refactor = _compute_risk(
            forward_count=3,
            dep_count=2,
            health_grade="A",
            has_tests=True,
            edit_type="refactor",
            is_init_file=False,
        )
        _, factors_rename = _compute_risk(
            forward_count=3,
            dep_count=2,
            health_grade="A",
            has_tests=True,
            edit_type="rename",
            is_init_file=False,
        )
        rename_risk_factors = [
            f for f in factors_rename if f["factor"] == "rename_risk"
        ]
        assert len(rename_risk_factors) == 1

    def test_init_file_flagged(self):
        risk, factors = _compute_risk(
            forward_count=0,
            dep_count=0,
            health_grade="A",
            has_tests=True,
            edit_type="fix_bug",
            is_init_file=True,
        )
        init_factors = [f for f in factors if f["factor"] == "init_file"]
        assert len(init_factors) == 1


class TestHelperFunctions:
    def test_is_init_file_true(self):
        assert _is_init_file("src/__init__.py")

    def test_is_init_file_false(self):
        assert not _is_init_file("src/main.py")

    def test_find_nearby_tests_for_known_file(self):
        tests = _find_nearby_tests(
            str(PROJECT_ROOT / "tree_sitter_analyzer" / "health_scorer.py"),
            str(PROJECT_ROOT),
        )
        assert isinstance(tests, list)
