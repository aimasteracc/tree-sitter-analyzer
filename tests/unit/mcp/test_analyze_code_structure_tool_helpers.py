#!/usr/bin/env python3
"""
Unit tests for AnalyzeCodeStructureTool.

Tests for analyze_code_structure tool which provides code structure
analysis with detailed overview tables (classes, methods, fields).
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
    extract_metadata,
)
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
    _attach_agent_summary,
    _build_next_steps,
    _convert_parameters,
    _format_table,
    _get_field_modifiers,
    _get_method_modifiers,
    _get_method_parameters,
)
from tree_sitter_analyzer.mcp.tools.tool_response import CANONICAL_VERDICTS


@pytest.fixture
def tool():
    """Create an AnalyzeCodeStructureTool instance for testing."""
    return AnalyzeCodeStructureTool()


def test_attach_agent_summary_emits_canonical_info_verdict():
    """Wave 1b (audit structure-07): a successful structural analysis must emit
    the canonical INFO verdict, not the off-ladder "n/a" placeholder (which is
    not in CANONICAL_VERDICTS and an agent branching on verdict cannot read)."""
    response: dict = {"success": True}
    _attach_agent_summary(
        response,
        MagicMock(),  # _ExecutionOptions — unused by the verdict path
        {"classes_count": 1, "methods_count": 2, "fields_count": 0, "total_lines": 10},
        [],
    )
    assert response["verdict"] == "INFO"
    assert response["verdict"] in CANONICAL_VERDICTS
    assert response["agent_summary"]["verdict"] == "INFO"


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeCodeStructureTool instance with a project root."""
    return AnalyzeCodeStructureTool(project_root="/test/project")


class TestAnalyzeCodeStructureHelpers:
    """Tests for module-level analyze_code_structure helpers."""

    def test_extract_metadata_coerces_non_int_statistics_to_zero(self):
        """Non-integer statistics should not leak into response metadata."""
        metadata = extract_metadata(
            {
                "statistics": {
                    "class_count": 2,
                    "method_count": "3",
                    "field_count": None,
                    "total_lines": 42,
                }
            }
        )

        assert metadata == {
            "classes_count": 2,
            "methods_count": 0,
            "fields_count": 0,
            "total_lines": 42,
        }

    def test_extract_metadata_defaults_missing_statistics_to_zero(self):
        """Missing statistics should produce stable zero counts."""
        assert extract_metadata({}) == {
            "classes_count": 0,
            "methods_count": 0,
            "fields_count": 0,
            "total_lines": 0,
        }


class TestAnalyzeCodeStructureFormatting:
    """Tests for module-level structure table formatting."""

    def test_format_table_uses_language_formatter_and_normalizes_newlines(self):
        """Language-backed formats should return stable LF-only text."""
        formatter = MagicMock()
        formatter.format_structure.return_value = "line1\r\nline2\r\n"

        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
            return_value=formatter,
        ) as get_formatter:
            output = _format_table({}, MagicMock(), "python", "full")

        assert output == "line1\nline2"
        get_formatter.assert_called_once_with("python", "full")

    def test_format_table_raises_for_unsupported_format(self):
        """Unsupported formats should fail before formatter lookup."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.is_format_supported",
            return_value=False,
        ):
            with pytest.raises(ValueError, match="Unsupported format type"):
                _format_table({}, MagicMock(elements=[]), "python", "unsupported")


class TestAnalyzeCodeStructureNextSteps:
    """Tests for next-step suggestions exposed to agents."""

    def test_build_next_steps_prefers_complex_method(self):
        """Complex methods should route agents to focused section extraction."""
        structure = {
            "methods": [
                {
                    "name": "simple",
                    "complexity_score": 1,
                    "line_range": {"start": 10, "end": 12},
                },
                {
                    "name": "hard_part",
                    "complexity_score": 11,
                    "line_range": {"start": 40, "end": 80},
                },
            ],
            "classes": [],
            "statistics": {"total_lines": 120},
        }

        steps = _build_next_steps(structure, "example.py")

        assert steps == [
            "extract_code_section(start_line=40, end_line=80) "
            "to read complex method 'hard_part' (complexity=11)"
        ]

    def test_build_next_steps_handles_invalid_collections(self):
        """Invalid structure shapes should not produce noisy suggestions."""
        steps = _build_next_steps(
            {
                "methods": "not-a-list",
                "classes": None,
                "statistics": {"total_lines": "many"},
            },
            "example.py",
        )

        assert steps == []

    def test_build_next_steps_adds_query_navigation_steps(self):
        """Larger method and class sets should route agents to query tools."""
        methods = [
            {"name": f"method_{index}", "complexity_score": 1} for index in range(6)
        ]
        structure = {
            "methods": methods,
            "classes": [{"name": "One"}, {"name": "Two"}],
            "statistics": {"total_lines": 120},
        }

        steps = _build_next_steps(structure, "example.py")

        assert steps == [
            "query_code(query_key='methods') to get detailed method list with filters",
            "query_code(query_key='classes') to examine class relationships",
        ]

    def test_build_next_steps_uses_large_file_fallback(self):
        """Large files without complex methods should suggest a first read slice."""
        structure = {
            "methods": [
                {
                    "name": "entrypoint",
                    "complexity_score": 2,
                    "line_range": {"start": 25, "end": 40},
                }
            ],
            "classes": [],
            "statistics": {"total_lines": 800},
        }

        steps = _build_next_steps(structure, "example.py")

        assert steps == [
            "extract_code_section(start_line=25, end_line=40) to read 'entrypoint'"
        ]

    def test_build_next_steps_caps_to_three_suggestions(self):
        """The agent-facing response should stay compact even for busy files."""
        methods = [
            {
                "name": "hard_part",
                "complexity_score": 12,
                "line_range": {"start": 5, "end": 55},
            },
            *[{"name": f"method_{index}", "complexity_score": 1} for index in range(6)],
        ]
        structure = {
            "methods": methods,
            "classes": [{"name": "One"}, {"name": "Two"}],
            "statistics": {"total_lines": 900},
        }

        steps = _build_next_steps(structure, "example.py")

        assert len(steps) == 3
        assert steps[0].startswith("extract_code_section(start_line=5, end_line=55)")


class TestAnalyzeCodeStructureToolConvertParameters:
    """Tests for _convert_parameters helper."""

    def test_convert_parameters_empty(self):
        """Test converting empty parameters."""
        result = _convert_parameters([])
        assert result == []

    def test_convert_parameters_dict(self):
        """Test converting dict parameters."""
        parameters = [{"name": "param1", "type": "string"}]
        result = _convert_parameters(parameters)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"

    def test_convert_parameters_object(self):
        """Test converting object parameters."""
        mock_param = MagicMock()
        mock_param.name = "param1"
        mock_param.param_type = "string"
        parameters = [mock_param]
        result = _convert_parameters(parameters)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"


class TestAnalyzeCodeStructureToolGetMethodModifiers:
    """Tests for _get_method_modifiers helper."""

    def test_get_method_modifiers_none(self):
        """Test getting modifiers with no modifiers."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = False
        mock_method.is_abstract = False

        result = _get_method_modifiers(mock_method)
        assert result == []

    def test_get_method_modifiers_static(self):
        """Test getting static modifier."""
        mock_method = MagicMock()
        mock_method.is_static = True
        mock_method.is_final = False
        mock_method.is_abstract = False

        result = _get_method_modifiers(mock_method)
        assert result == ["static"]

    def test_get_method_modifiers_final(self):
        """Test getting final modifier."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = True
        mock_method.is_abstract = False

        result = _get_method_modifiers(mock_method)
        assert result == ["final"]

    def test_get_method_modifiers_abstract(self):
        """Test getting abstract modifier."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = False
        mock_method.is_abstract = True

        result = _get_method_modifiers(mock_method)
        assert result == ["abstract"]

    def test_get_method_modifiers_multiple(self):
        """Test getting multiple modifiers."""
        mock_method = MagicMock()
        mock_method.is_static = True
        mock_method.is_final = True
        mock_method.is_abstract = True

        result = _get_method_modifiers(mock_method)
        assert len(result) == 3
        assert "static" in result
        assert "final" in result
        assert "abstract" in result


class TestAnalyzeCodeStructureToolGetFieldModifiers:
    """Tests for _get_field_modifiers helper."""

    def test_get_field_modifiers_none(self):
        """Test getting modifiers with no modifiers."""
        mock_field = MagicMock()
        mock_field.visibility = "public"
        mock_field.is_static = False
        mock_field.is_final = False

        result = _get_field_modifiers(mock_field)
        # Public visibility is added as a modifier (not package)
        assert result == ["public"]

    def test_get_field_modifiers_private(self):
        """Test getting private visibility."""
        mock_field = MagicMock()
        mock_field.visibility = "private"
        mock_field.is_static = False
        mock_field.is_final = False

        result = _get_field_modifiers(mock_field)
        assert result == ["private"]

    def test_get_field_modifiers_static(self):
        """Test getting static modifier."""
        mock_field = MagicMock()
        mock_field.visibility = "public"
        mock_field.is_static = True
        mock_field.is_final = False

        result = _get_field_modifiers(mock_field)
        # Public visibility is added as a modifier
        assert result == ["public", "static"]

    def test_get_field_modifiers_multiple(self):
        """Test getting multiple modifiers."""
        mock_field = MagicMock()
        mock_field.visibility = "private"
        mock_field.is_static = True
        mock_field.is_final = True

        result = _get_field_modifiers(mock_field)
        assert len(result) == 3
        assert "private" in result
        assert "static" in result
        assert "final" in result


class TestAnalyzeCodeStructureToolGetMethodParameters:
    """Tests for _get_method_parameters helper."""

    def test_get_method_parameters_empty(self):
        """Test getting empty parameters."""
        mock_method = MagicMock()
        mock_method.parameters = []

        result = _get_method_parameters(mock_method)
        assert result == []

    def test_get_method_parameters_list_of_strings(self):
        """Test getting parameters as list of strings."""
        mock_method = MagicMock()
        mock_method.parameters = ["str param1", "str param2"]

        result = _get_method_parameters(mock_method)
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "str"

    def test_get_method_parameters_list_of_dicts(self):
        """Test getting parameters as list of dicts."""
        mock_method = MagicMock()
        mock_method.parameters = [{"name": "param1", "type": "string"}]

        result = _get_method_parameters(mock_method)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"

    def test_get_method_parameters_mixed(self):
        """Test getting mixed parameters."""
        mock_method = MagicMock()
        # Use all string format (the implementation handles this case)
        mock_method.parameters = ["str param1", "int param2"]

        result = _get_method_parameters(mock_method)
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "int"

    def test_get_method_parameters_compound_generic_types(self):
        """#576: ``name: <generic with spaces>`` must split on the FIRST ':',
        not whitespace — otherwise ``result: dict[str, Any]`` parsed as
        name='Any]', type='result: dict[str,'. Covers the modern typed-Python
        forms (generics, nested brackets, defaults) that whitespace-splitting
        mangled."""
        mock_method = MagicMock()
        mock_method.parameters = [
            "result: dict[str, Any]",
            "cb: Callable[[int], str]",
            "items: list[tuple[int, str]]",
            'breed: str = "Mixed"',
        ]
        result = _get_method_parameters(mock_method)
        assert result[0] == {"name": "result", "type": "dict[str, Any]"}
        assert result[1] == {"name": "cb", "type": "Callable[[int], str]"}
        assert result[2] == {"name": "items", "type": "list[tuple[int, str]]"}
        assert result[3] == {"name": "breed", "type": "str", "default": '"Mixed"'}
