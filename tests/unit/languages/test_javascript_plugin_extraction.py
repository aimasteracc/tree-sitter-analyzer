"""
Extraction tests for JavaScript plugin.
Split from test_javascript_plugin_coverage_boost.py.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)
from tree_sitter_analyzer.models import Function, Import, Variable


@pytest.fixture
def extractor():
    return JavaScriptElementExtractor()


@pytest.fixture
def plugin():
    return JavaScriptPlugin()


class TestExecuteQueryStrategy:
    def test_none_query_key(self, plugin):
        result = plugin.execute_query_strategy(None, "javascript")
        assert result is None

    def test_invalid_query_key(self, plugin):
        result = plugin.execute_query_strategy("nonexistent_key", "javascript")
        assert result is None


class TestGetElementCategories:
    def test_returns_dict(self, plugin):
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        assert "function" in cats
        assert "class" in cats
        assert "variable" in cats
        assert "import" in cats


class TestDetectFileCharacteristics:
    def test_angular_detection(self, extractor):
        extractor.source_code = "import { Component } from '@angular/core';"
        extractor.current_file = "app.component.ts"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "angular"

    def test_react_detection(self, extractor):
        extractor.source_code = "import React from 'react';"
        extractor.current_file = "App.jsx"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "react"

    def test_vue_detection(self, extractor):
        extractor.source_code = "import Vue from 'vue';"
        extractor.current_file = "App.vue"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "vue"


class TestFindParentClassName:
    def test_finds_class_declaration(self, extractor):
        mock_identifier = Mock()
        mock_identifier.type = "identifier"

        mock_class = Mock()
        mock_class.type = "class_declaration"
        mock_class.children = [mock_identifier]
        mock_class.parent = None

        mock_method = Mock()
        mock_method.parent = mock_class

        with patch.object(
            extractor, "_get_node_text_optimized", return_value="MyClass"
        ):
            result = extractor._find_parent_class_name(mock_method)
        assert result == "MyClass"

    def test_no_parent(self, extractor):
        mock_node = Mock()
        mock_node.parent = None
        result = extractor._find_parent_class_name(mock_node)
        assert result is None

    def test_class_without_identifier(self, extractor):
        mock_class = Mock()
        mock_class.type = "class_declaration"
        mock_class.children = []
        mock_class.parent = None

        mock_method = Mock()
        mock_method.parent = mock_class

        result = extractor._find_parent_class_name(mock_method)
        assert result is None


class TestIsReactComponent:
    def test_react_component(self, extractor):
        extractor.framework_type = "react"
        mock_node = Mock()
        extractor.content_lines = ["class MyComp extends React.Component {}"]
        extractor._file_encoding = "utf-8"
        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "class MyComp extends React.Component {}"
            assert extractor._is_react_component(mock_node, "MyComp") is True

    def test_not_react_framework(self, extractor):
        extractor.framework_type = "vue"
        mock_node = Mock()
        assert extractor._is_react_component(mock_node, "MyComp") is False


class TestIsExportedClass:
    def test_exported(self, extractor):
        extractor.exports = [{"names": ["MyClass"]}]
        assert extractor._is_exported_class("MyClass") is True

    def test_not_exported(self, extractor):
        extractor.exports = []
        assert extractor._is_exported_class("MyClass") is False


class TestExtractExportInfo:
    def test_valid_export(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 25)
        extractor.content_lines = ["export default MyComponent;"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "export default MyComponent;"
            result = extractor._extract_export_info(mock_node)

        assert result is not None
        assert result["type"] == "default"
        assert "MyComponent" in result["names"]

    def test_unparseable_export(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)
        extractor.content_lines = ["const x = 1;"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "const x = 1;"
            result = extractor._extract_export_info(mock_node)

        assert result is None


class TestExtractElementsExtractor:
    def test_extract_elements_combines_all(self, extractor):
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(extractor, "extract_functions", return_value=[Mock()]):
            with patch.object(extractor, "extract_classes", return_value=[Mock()]):
                with patch.object(
                    extractor, "extract_variables", return_value=[Mock()]
                ):
                    with patch.object(
                        extractor, "extract_imports", return_value=[Mock()]
                    ):
                        result = extractor.extract_elements(mock_tree, "code")

        assert len(result) == 4

    def test_extract_elements_handles_error(self, extractor):
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(
            extractor, "extract_functions", side_effect=Exception("fail")
        ):
            result = extractor.extract_elements(mock_tree, "code")

        assert isinstance(result, list)


class TestExtractGeneratorFunction:
    def test_generator_extraction(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 1)

        extractor.content_lines = ["function* gen() {", "  yield 1;", "}"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "function* gen() { yield 1; }"
            with patch.object(
                extractor,
                "_parse_function_signature_optimized",
                return_value=("gen", [], False, None),
            ):
                with patch.object(
                    extractor, "_extract_jsdoc_for_line", return_value=None
                ):
                    with patch.object(
                        extractor,
                        "_calculate_complexity_optimized",
                        return_value=2,
                    ):
                        result = extractor._extract_generator_function_optimized(
                            mock_node
                        )

        assert result is not None
        assert isinstance(result, Function)
        assert result.name == "gen"
        assert result.is_generator is True

    def test_generator_no_signature(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 1)

        with patch.object(
            extractor,
            "_parse_function_signature_optimized",
            return_value=None,
        ):
            result = extractor._extract_generator_function_optimized(mock_node)
            assert result is None

    def test_generator_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 1)

        with patch.object(
            extractor,
            "_parse_function_signature_optimized",
            side_effect=Exception("fail"),
        ):
            result = extractor._extract_generator_function_optimized(mock_node)
            assert result is None


class TestExtractPropertyOptimized:
    def test_property_with_value(self, extractor):
        prop_id = Mock()
        prop_id.type = "property_identifier"
        prop_id.start_byte = 0
        prop_id.end_byte = 4
        prop_id.start_point = (0, 0)
        prop_id.end_point = (0, 4)

        value_node = Mock()
        value_node.type = "string"
        value_node.start_byte = 7
        value_node.end_byte = 14
        value_node.start_point = (0, 7)
        value_node.end_point = (0, 14)

        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 14)
        mock_node.children = [prop_id, value_node]
        mock_node.parent = None

        extractor.content_lines = ["name = 'value'"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = lambda *a, **kw: {
                (0, 4): "name",
                (7, 14): "'value'",
                (0, 14): "name = 'value'",
            }.get((mock_extract.call_count, 0), "name")

        with patch.object(extractor, "_get_node_text_optimized") as mock_text:
            mock_text.side_effect = ["name", "'value'", "name = 'value'"]
            result = extractor._extract_property_optimized(mock_node)

        assert result is not None
        assert isinstance(result, Variable)
        assert result.name == "name"

    def test_property_no_name(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)
        mock_node.children = []
        mock_node.parent = None

        with patch.object(extractor, "_get_node_text_optimized", return_value=""):
            result = extractor._extract_property_optimized(mock_node)
            assert result is None

    def test_property_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)
        mock_node.children = [Mock(side_effect=Exception("fail"))]

        result = extractor._extract_property_optimized(mock_node)
        assert result is None


class TestExtractImportInfoEnhanced:
    def test_valid_import(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)
        extractor.content_lines = ["import React from 'react';"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "import React from 'react';"
            result = extractor._extract_import_info_enhanced(
                mock_node, "import React from 'react';"
            )

        assert result is not None
        assert isinstance(result, Import)
        assert result.name == "React"
        assert result.module_path == "react"

    def test_unparseable_import(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)
        extractor.content_lines = ["import ;"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "import ;"
            result = extractor._extract_import_info_enhanced(mock_node, "import ;")

        assert result is None


class TestExtractImportNames:
    def test_default_import_name(self, extractor):
        source = "import React from 'react';"
        extractor.source_code = source

        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 7
        mock_identifier.end_byte = 12

        mock_specifier = Mock()
        mock_specifier.type = "import_default_specifier"
        mock_specifier.children = [mock_identifier]

        mock_clause = Mock()
        mock_clause.children = [mock_specifier]

        names = extractor._extract_import_names(mock_clause)
        assert "React" in names

    def test_named_imports(self, extractor):
        source = "import { useState, useEffect } from 'react';"
        extractor.source_code = source

        mock_id1 = Mock()
        mock_id1.type = "identifier"
        mock_id1.start_byte = 9
        mock_id1.end_byte = 17

        mock_spec1 = Mock()
        mock_spec1.type = "import_specifier"
        mock_spec1.children = [mock_id1]

        mock_id2 = Mock()
        mock_id2.type = "identifier"
        mock_id2.start_byte = 19
        mock_id2.end_byte = 28

        mock_spec2 = Mock()
        mock_spec2.type = "import_specifier"
        mock_spec2.children = [mock_id2]

        mock_named = Mock()
        mock_named.type = "named_imports"
        mock_named.children = [mock_spec1, mock_spec2]

        mock_clause = Mock()
        mock_clause.children = [mock_named]

        names = extractor._extract_import_names(mock_clause)
        assert len(names) >= 1


class TestPluginCapabilities:
    def test_get_plugin_info(self, plugin):
        info = plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert info["name"] == "JavaScript Plugin"
        assert "features" in info

    def test_get_supported_queries(self, plugin):
        queries = plugin.get_supported_queries()
        assert isinstance(queries, list)
        assert "function" in queries
        assert "class" in queries

    def test_get_element_categories_coverage(self, plugin):
        cats = plugin.get_element_categories()
        assert "arrow_function" in cats
        assert "method" in cats
        assert "constructor" in cats
        assert "classes" in cats
        assert "variables" in cats
        assert "imports" in cats


class TestGetNodeTextMultiLine:
    def test_multiline_node_fallback(self, extractor):
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 50
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 5)
        extractor.content_lines = [
            "line one content",
            "line two content",
            "line three",
        ]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "err")
            result = extractor._get_node_text_optimized(mock_node)

        assert "line one content" in result
        assert "line two content" in result


# ---------------------------------------------------------------------------
# Issue #534 — JS private method name (Scope A2)
# ---------------------------------------------------------------------------


class TestPrivateMethodNameExtraction:
    """Private class fields (#name) must produce a non-empty name — not ''."""

    def test_private_method_name_is_not_empty(self, plugin):
        """#logActivity must be extracted as 'logActivity', not empty string."""
        import tree_sitter

        lang = plugin.get_tree_sitter_language()
        parser = tree_sitter.Parser(lang)
        code = "class Logger {\n    #logActivity(msg) { console.log(msg); }\n    normalMethod() {}\n}\n"
        tree = parser.parse(bytes(code, "utf-8"))
        extractor = plugin.extractor
        fns = extractor.extract_functions(tree, code)
        # normalMethod is definitely present; #logActivity should have a non-empty name
        method_names = [f.name for f in fns if f.is_method]
        assert "#logActivity" in method_names or "logActivity" in method_names, (
            f"Expected private method name in {method_names!r}, got empty string"
        )
        # No method should have an empty name
        empty_names = [f.name for f in fns if f.name == ""]
        assert empty_names == [], f"Methods with empty names: {empty_names!r}"
