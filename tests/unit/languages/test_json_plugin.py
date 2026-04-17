#!/usr/bin/env python3
"""
Tests for JSON Plugin — element extraction and analysis.

Validates JSONElementExtractor, JSONElement, and JSONPlugin
against various JSON structures.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.languages.json_plugin import (
    JSON_AVAILABLE,
    JSONElement,
    JSONElementExtractor,
    JSONPlugin,
)


@pytest.mark.skipif(not JSON_AVAILABLE, reason="tree-sitter-json not installed")
class TestJSONElementExtractor:
    """Test JSON element extraction from various JSON structures."""

    def _extract(self, source: str) -> list[JSONElement]:
        """Helper: parse and extract elements from JSON string."""
        import tree_sitter
        import tree_sitter_json as ts_json

        lang = tree_sitter.Language(ts_json.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(source.encode("utf-8"))

        extractor = JSONElementExtractor()
        return extractor.extract_json_elements(tree, source)

    def test_empty_object(self) -> None:
        elements = self._extract("{}")
        objs = [e for e in elements if e.element_type == "object"]
        assert len(objs) >= 1

    def test_empty_array(self) -> None:
        elements = self._extract("[]")
        arrays = [e for e in elements if e.element_type == "array"]
        assert len(arrays) >= 1

    def test_simple_string_pair(self) -> None:
        elements = self._extract('{"name": "Alice"}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert len(pairs) == 1
        assert pairs[0].key == "name"
        assert pairs[0].value == "Alice"
        assert pairs[0].value_type == "string"

    def test_number_pair(self) -> None:
        elements = self._extract('{"age": 30}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert len(pairs) == 1
        assert pairs[0].key == "age"
        assert pairs[0].value == "30"
        assert pairs[0].value_type == "number"

    def test_boolean_true_pair(self) -> None:
        elements = self._extract('{"active": true}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert len(pairs) == 1
        assert pairs[0].value == "true"
        assert pairs[0].value_type == "boolean"

    def test_boolean_false_pair(self) -> None:
        elements = self._extract('{"disabled": false}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert pairs[0].value == "false"
        assert pairs[0].value_type == "boolean"

    def test_null_pair(self) -> None:
        elements = self._extract('{"data": null}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert pairs[0].value == "null"
        assert pairs[0].value_type == "null"

    def test_nested_object(self) -> None:
        source = '{"user": {"name": "Bob", "age": 25}}'
        elements = self._extract(source)
        objs = [e for e in elements if e.element_type == "object"]
        assert len(objs) == 2  # outer + inner

    def test_array_of_strings(self) -> None:
        source = '["a", "b", "c"]'
        elements = self._extract(source)
        arrays = [e for e in elements if e.element_type == "array"]
        assert len(arrays) == 1
        assert arrays[0].child_count == 3

    def test_array_of_numbers(self) -> None:
        source = "[1, 2, 3, 4, 5]"
        elements = self._extract(source)
        numbers = [e for e in elements if e.element_type == "number"]
        assert len(numbers) == 5

    def test_mixed_array(self) -> None:
        source = '[1, "hello", true, null, {}]'
        elements = self._extract(source)
        assert any(e.element_type == "number" for e in elements)
        assert any(e.element_type == "string" for e in elements)
        assert any(e.element_type == "true" for e in elements)
        assert any(e.element_type == "null" for e in elements)

    def test_nesting_level(self) -> None:
        source = '{"a": {"b": {"c": 1}}}'
        elements = self._extract(source)
        pairs = [e for e in elements if e.element_type == "pair"]
        # Inner pair should have higher nesting level
        by_key = {p.key: p for p in pairs}
        assert by_key["a"].nesting_level < by_key["c"].nesting_level

    def test_top_level_array(self) -> None:
        source = json.dumps([{"id": 1}, {"id": 2}])
        elements = self._extract(source)
        objs = [e for e in elements if e.element_type == "object"]
        assert len(objs) == 2

    def test_empty_string_value(self) -> None:
        elements = self._extract('{"key": ""}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert pairs[0].value == ""

    def test_special_chars_in_string(self) -> None:
        elements = self._extract('{"path": "C:\\\\Users\\\\test"}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert pairs[0].key == "path"

    def test_large_number(self) -> None:
        elements = self._extract('{"big": 999999999999}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert pairs[0].value == "999999999999"

    def test_negative_number(self) -> None:
        elements = self._extract('{"val": -42}')
        numbers = [e for e in elements if e.element_type == "number"]
        assert len(numbers) >= 1

    def test_float_number(self) -> None:
        elements = self._extract('{"pi": 3.14159}')
        pairs = [e for e in elements if e.element_type == "pair"]
        assert pairs[0].value_type == "number"

    def test_extract_functions_empty(self) -> None:
        extractor = JSONElementExtractor()
        assert extractor.extract_functions(None, "") == []

    def test_extract_classes_empty(self) -> None:
        extractor = JSONElementExtractor()
        assert extractor.extract_classes(None, "") == []

    def test_extract_variables_empty(self) -> None:
        extractor = JSONElementExtractor()
        assert extractor.extract_variables(None, "") == []

    def test_extract_imports_empty(self) -> None:
        extractor = JSONElementExtractor()
        assert extractor.extract_imports(None, "") == []

    def test_none_tree_returns_empty(self) -> None:
        extractor = JSONElementExtractor()
        result = extractor.extract_json_elements(None, "{}")
        assert result == []

    def test_extract_elements_alias(self) -> None:
        """extract_elements should be alias for extract_json_elements."""
        extractor = JSONElementExtractor()
        import tree_sitter
        import tree_sitter_json as ts_json

        lang = tree_sitter.Language(ts_json.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(b'{"x": 1}')

        result1 = extractor.extract_json_elements(tree, '{"x": 1}')
        result2 = extractor.extract_elements(tree, '{"x": 1}')
        assert len(result1) == len(result2)


@pytest.mark.skipif(not JSON_AVAILABLE, reason="tree-sitter-json not installed")
class TestJSONPlugin:
    """Test JSONPlugin class."""

    def test_plugin_metadata(self) -> None:
        plugin = JSONPlugin()
        assert plugin.get_language_name() == "json"
        assert plugin.get_file_extensions() == [".json"]

    def test_supported_element_types(self) -> None:
        plugin = JSONPlugin()
        types = plugin.get_supported_element_types()
        assert "object" in types
        assert "array" in types
        assert "pair" in types
        assert "string" in types
        assert "number" in types

    def test_element_categories(self) -> None:
        plugin = JSONPlugin()
        cats = plugin.get_element_categories()
        assert "structure" in cats
        assert "pairs" in cats
        assert "scalars" in cats

    def test_queries_empty(self) -> None:
        plugin = JSONPlugin()
        assert plugin.get_queries() == {}

    def test_create_extractor(self) -> None:
        plugin = JSONPlugin()
        ext = plugin.create_extractor()
        assert isinstance(ext, JSONElementExtractor)

    def test_tree_sitter_language(self) -> None:
        plugin = JSONPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None

    def test_execute_query_strategy_returns_none(self) -> None:
        plugin = JSONPlugin()
        assert plugin.execute_query_strategy(None, "json") is None
        assert plugin.execute_query_strategy("test", "json") is None
        assert plugin.execute_query_strategy("test", "python") is None

    @pytest.mark.asyncio
    async def test_analyze_simple_file(self) -> None:
        plugin = JSONPlugin()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"name": "test", "value": 42}, f)
            f.flush()

            from tree_sitter_analyzer.core.request import AnalysisRequest

            req = AnalysisRequest(
                file_path=f.name, language="json", include_details=True
            )
            result = await plugin.analyze_file(f.name, req)

        Path(f.name).unlink()
        assert result.success is True
        assert result.language == "json"
        assert len(result.elements) > 0

    @pytest.mark.asyncio
    async def test_analyze_nested_json(self) -> None:
        plugin = JSONPlugin()
        data = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
            ],
            "meta": {"total": 2, "page": 1},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()

            from tree_sitter_analyzer.core.request import AnalysisRequest

            req = AnalysisRequest(
                file_path=f.name, language="json", include_details=True
            )
            result = await plugin.analyze_file(f.name, req)

        Path(f.name).unlink()
        assert result.success is True
        assert result.line_count > 0

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self) -> None:
        plugin = JSONPlugin()
        from tree_sitter_analyzer.core.request import AnalysisRequest

        req = AnalysisRequest(
            file_path="/nonexistent/file.json",
            language="json",
            include_details=True,
        )
        result = await plugin.analyze_file("/nonexistent/file.json", req)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_analyze_empty_json(self) -> None:
        plugin = JSONPlugin()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{}")
            f.flush()

            from tree_sitter_analyzer.core.request import AnalysisRequest

            req = AnalysisRequest(
                file_path=f.name, language="json", include_details=True
            )
            result = await plugin.analyze_file(f.name, req)

        Path(f.name).unlink()
        assert result.success is True


class TestJSONElement:
    """Test JSONElement data class."""

    def test_basic_element(self) -> None:
        elem = JSONElement(
            name="test",
            start_line=1,
            end_line=1,
            raw_text='"test"',
            element_type="string",
            value="test",
            value_type="string",
        )
        assert elem.name == "test"
        assert elem.element_type == "string"
        assert elem.type == "string"
        assert elem.value == "test"
        assert elem.value_type == "string"

    def test_element_defaults(self) -> None:
        elem = JSONElement(
            name="obj",
            start_line=1,
            end_line=5,
            raw_text="{}",
        )
        assert elem.key is None
        assert elem.value is None
        assert elem.nesting_level == 0
        assert elem.child_count is None
        assert elem.language == "json"

    def test_element_with_all_fields(self) -> None:
        elem = JSONElement(
            name="user",
            start_line=1,
            end_line=10,
            raw_text='{"user": {...}}',
            element_type="pair",
            key="user",
            value=None,
            value_type="object",
            nesting_level=2,
            child_count=3,
        )
        assert elem.key == "user"
        assert elem.nesting_level == 2
        assert elem.child_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
