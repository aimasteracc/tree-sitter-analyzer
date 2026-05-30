"""Unit tests for SmartContextTool."""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.smart_context_tool import (
    AgentSummaryInput,
    SmartContextTool,
    _build_agent_summary,
    _quick_risk,
)
from tree_sitter_analyzer.mcp.tools.utils.element_extractor import (
    extract_elements,
    get_all_exports,
    get_structure,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TARGET_FILE = "tree_sitter_analyzer/mcp/tools/smart_context_tool.py"


@pytest.fixture
def tool(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n")

    target = tmp_path / TARGET_FILE
    target.parent.mkdir(parents=True)
    target.write_text(
        """
class SmartContextTool:
    def execute(self):
        return {"success": True}


def build_summary():
    return "ready"
""".strip()
    )

    test_file = tmp_path / "tests/unit/mcp/test_smart_context_tool.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_smart_context_tool(): pass\n")

    t = SmartContextTool(str(tmp_path))
    t.set_project_path(str(tmp_path))
    return t


def _run(coro):
    return asyncio.run(coro)


class TestSmartContextTool:
    def test_validate_arguments_missing_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_valid(self, tool):
        assert tool.validate_arguments({"file_path": "some_file.py"})

    def test_execute_returns_complete_profile(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert "health" in result
        assert "exports" in result
        assert "structure" in result
        assert "dependencies" in result
        assert "tests" in result
        assert "edit_risk" in result
        assert "agent_summary" in result
        assert "recommendation" in result

    def test_agent_summary_guides_next_action(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        summary = result["agent_summary"]

        assert summary["risk"] in ("safe", "caution", "dangerous")
        assert summary["grade"] == result["health"]["grade"]
        assert summary["verification_command"].startswith("uv run pytest ")
        assert summary["change_impact_command"].endswith(
            f"--change-impact-scope {TARGET_FILE} --format json"
        )
        assert summary["downstream_count"] >= 0

    def test_health_has_grade_and_score(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        health = result["health"]
        assert "grade" in health
        assert "score" in health
        assert "weakest_dimension" in health

    def test_exports_include_classes_and_functions(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        exports = result["exports"]
        names = [e["name"] for e in exports]
        assert "SmartContextTool" in names

    def test_structure_has_line_ranges(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        for item in result["structure"]:
            assert "name" in item
            assert "kind" in item

    def test_dependencies_structure(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        deps = result["dependencies"]
        assert "imports_count" in deps
        assert "imported_by_count" in deps

    def test_edit_risk_is_valid(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert result["edit_risk"] in ("safe", "caution", "dangerous")

    def test_line_count(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert result["line_count"] > 0

    def test_language_detected(self, tool):
        result = _run(tool.execute({"file_path": TARGET_FILE}))
        assert result["language"] == "python"

    def test_file_not_found(self, tool):
        with pytest.raises(ValueError, match="File not found"):
            _run(tool.execute({"file_path": "nonexistent_file.py"}))

    def test_toon_format_works(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "output_format": "toon",
                }
            )
        )
        assert "health" in result

    def test_json_format_works(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": TARGET_FILE,
                    "output_format": "json",
                }
            )
        )
        assert "health" in result


class TestExportExtraction:
    def test_extracts_class(self):
        result = extract_elements(
            str(PROJECT_ROOT / "tree_sitter_analyzer" / "models.py"), "."
        )
        assert result is not None
        exports = get_all_exports(result)
        classes = [e for e in exports if e["kind"] == "class"]
        assert len(classes) > 0

    def test_excludes_private_functions(self):
        result = extract_elements(
            str(PROJECT_ROOT / "tree_sitter_analyzer" / "models.py"), "."
        )
        assert result is not None
        exports = get_all_exports(result)
        names = [e["name"] for e in exports]
        assert not any(n.startswith("_") for n in names)


class TestStructureExtraction:
    def test_extracts_structure(self):
        result = extract_elements(
            str(PROJECT_ROOT / "tree_sitter_analyzer" / "models.py"), "."
        )
        assert result is not None
        structure = get_structure(result)
        assert len(structure) > 0
        kinds = {s["kind"] for s in structure}
        assert "class" in kinds or "function" in kinds


class TestQuickRisk:
    def test_safe(self):
        assert _quick_risk(0, "A", True) == "safe"

    def test_caution(self):
        assert _quick_risk(6, "C", False) == "caution"

    def test_dangerous(self):
        assert _quick_risk(25, "D", False) == "dangerous"


class TestAgentSummary:
    def test_recommends_safe_to_edit_for_dangerous_files(self):
        summary = _build_agent_summary(
            AgentSummaryInput(
                file_path="src/risky file.py",
                grade="C",
                score=70.0,
                weakest="complexity",
                risk="dangerous",
                export_count=2,
                downstream_count=30,
                test_files=[],
            )
        )

        assert summary["next_step"].startswith("Run safe-to-edit")
        assert "'src/risky file.py'" in summary["safe_to_edit_command"]
        assert summary["focused_test_command"] == ""

    def test_recommends_refactor_for_low_grade_files(self):
        summary = _build_agent_summary(
            AgentSummaryInput(
                file_path="src/bad.py",
                grade="D",
                score=42.0,
                weakest="size",
                risk="caution",
                export_count=1,
                downstream_count=3,
                test_files=["tests/test_bad.py"],
            )
        )

        assert "refactoring suggestions" in summary["next_step"]
        assert summary["focused_test_command"] == "uv run pytest tests/test_bad.py -q"
        assert summary["stop_condition"].startswith("uv run pytest")
