#!/usr/bin/env python3
"""AnalyzeCodeStructureTool helper tests — formatting, next steps, helpers."""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
    _convert_class,
    extract_metadata,
)
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    _build_next_steps,
    _format_table,
)


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


class TestConvertClass:
    """Tests for _convert_class — ensures class attributes are passed through."""

    def _make_cls(self, **kwargs):
        cls = MagicMock()
        cls.name = kwargs.get("name", "MyClass")
        cls.start_line = kwargs.get("start_line", 1)
        cls.end_line = kwargs.get("end_line", 10)
        cls.class_type = kwargs.get("class_type", "class")
        cls.visibility = kwargs.get("visibility", "public")
        cls.extends_class = kwargs.get("extends_class", None)
        cls.implements_interfaces = kwargs.get("implements_interfaces", [])
        cls.annotations = kwargs.get("annotations", [])
        return cls

    def test_converts_public_visibility(self):
        cls = self._make_cls(visibility="public")
        result = _convert_class(cls)
        assert result["visibility"] == "public"

    def test_converts_package_private_visibility(self):
        """Package-private classes must not be reported as 'public'."""
        cls = self._make_cls(visibility="package-private")
        result = _convert_class(cls)
        assert result["visibility"] == "package-private"

    def test_converts_protected_visibility(self):
        cls = self._make_cls(visibility="protected")
        result = _convert_class(cls)
        assert result["visibility"] == "protected"

    def test_converts_private_visibility(self):
        cls = self._make_cls(visibility="private")
        result = _convert_class(cls)
        assert result["visibility"] == "private"

    def test_defaults_to_public_when_no_visibility_attr(self):
        cls = MagicMock(spec=[])
        result = _convert_class(cls)
        assert result["visibility"] == "public"

    def _make_cls_non_java(self, **kwargs):
        """Build a Class mock using superclass/interfaces (non-Java spellings)."""
        cls = MagicMock()
        cls.name = kwargs.get("name", "MyClass")
        cls.start_line = kwargs.get("start_line", 1)
        cls.end_line = kwargs.get("end_line", 10)
        cls.class_type = kwargs.get("class_type", "class")
        cls.visibility = kwargs.get("visibility", "public")
        cls.annotations = kwargs.get("annotations", [])
        # Non-Java spellings (JS/TS/Python/Ruby/PHP/C++/C#/Go):
        cls.superclass = kwargs.get("superclass", None)
        cls.interfaces = kwargs.get("interfaces", [])
        # Force Java-spelling aliases to None / [] so they don't accidentally
        # satisfy the truthiness check in _resolve_class_extends / _resolve_class_implements.
        cls.extends_class = None
        cls.implements_interfaces = []
        return cls

    def test_convert_class_superclass_field_surfaces_as_extends(self):
        """superclass= (non-Java spelling) must surface as extends in output."""
        cls = self._make_cls_non_java(superclass="Animal")
        result = _convert_class(cls)
        assert result["extends"] == "Animal"

    def test_convert_class_interfaces_field_surfaces_as_implements(self):
        """interfaces= (non-Java spelling) must surface as implements in output."""
        cls = self._make_cls_non_java(interfaces=["IFoo", "IBar"])
        result = _convert_class(cls)
        assert result["implements"] == ["IFoo", "IBar"]

    def test_convert_class_both_non_java_fields_surface(self):
        """Both superclass= and interfaces= surface when set together."""
        cls = self._make_cls_non_java(superclass="Base", interfaces=["IA", "IB"])
        result = _convert_class(cls)
        assert result["extends"] == "Base"
        assert result["implements"] == ["IA", "IB"]

    def test_convert_class_java_spelling_extends_class_takes_priority(self):
        """extends_class= (Java spelling) surfaces when set, even if superclass= is also set."""
        cls = self._make_cls(extends_class="JavaBase", implements_interfaces=["IFoo"])
        result = _convert_class(cls)
        assert result["extends"] == "JavaBase"
        assert result["implements"] == ["IFoo"]
