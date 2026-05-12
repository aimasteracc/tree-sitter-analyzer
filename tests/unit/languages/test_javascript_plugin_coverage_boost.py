"""
Coverage boost tests for JavaScript plugin.
Targets uncovered lines in javascript_plugin.py to raise coverage above 80%.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)
from tree_sitter_analyzer.models import Class, Function, Import, Variable


@pytest.fixture
def extractor():
    return JavaScriptElementExtractor()


@pytest.fixture
def plugin():
    return JavaScriptPlugin()


# --- _parse_import_statement (lines 1078-1116) ---


class TestParseImportStatement:
    def test_namespace_import(self, extractor):
        result = extractor._parse_import_statement("import * as React from 'react';")
        assert result is not None
        import_type, names, source, is_default, is_namespace = result
        assert import_type == "namespace"
        assert names == ["React"]
        assert source == "react"
        assert is_namespace is True

    def test_named_imports(self, extractor):
        result = extractor._parse_import_statement(
            "import { useState, useEffect } from 'react';"
        )
        assert result is not None
        import_type, names, source, is_default, is_namespace = result
        assert import_type == "named"
        assert "useState" in names
        assert "useEffect" in names
        assert source == "react"
        assert is_namespace is False

    def test_default_import(self, extractor):
        result = extractor._parse_import_statement("import express from 'express';")
        assert result is not None
        import_type, names, source, is_default, is_namespace = result
        assert import_type == "default"
        assert names == ["express"]
        assert source == "express"
        assert is_default is True

    def test_no_source_returns_none(self, extractor):
        result = extractor._parse_import_statement("import something")
        assert result is None

    def test_exception_returns_none(self, extractor):
        result = extractor._parse_import_statement(None)
        assert result is None


# --- _parse_export_statement (lines 1118-1157) ---


class TestParseExportStatement:
    def test_default_export_with_name(self, extractor):
        result = extractor._parse_export_statement("export default MyComponent;")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "default"
        assert names == ["MyComponent"]
        assert is_default is True

    def test_default_export_no_name(self, extractor):
        result = extractor._parse_export_statement("export default;")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "default"
        assert names == ["default"]
        assert is_default is True

    def test_named_exports(self, extractor):
        result = extractor._parse_export_statement("export { foo, bar };")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "named"
        assert "foo" in names
        assert "bar" in names
        assert is_default is False

    def test_direct_export_function(self, extractor):
        result = extractor._parse_export_statement("export function helper() {}")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "direct"
        assert names == ["helper"]
        assert is_default is False

    def test_direct_export_class(self, extractor):
        result = extractor._parse_export_statement("export class MyClass {}")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "direct"
        assert names == ["MyClass"]

    def test_direct_export_const(self, extractor):
        result = extractor._parse_export_statement("export const PI = 3.14;")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "direct"
        assert names == ["PI"]

    def test_direct_export_unknown(self, extractor):
        result = extractor._parse_export_statement("export something_weird")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "direct"
        assert names == ["unknown"]

    def test_invalid_export_returns_none(self, extractor):
        result = extractor._parse_export_statement("invalid export statement")
        assert result is None

    def test_non_export_returns_none(self, extractor):
        result = extractor._parse_export_statement("const x = 1;")
        assert result is None

    def test_exception_returns_none(self, extractor):
        result = extractor._parse_export_statement(None)
        assert result is None


# --- _extract_dynamic_import (lines 957-983) ---


class TestExtractDynamicImport:
    def test_dynamic_import(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)
        extractor.content_lines = ["const mod = import('my-module');"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "import('my-module')"
            result = extractor._extract_dynamic_import(mock_node)

        assert result is not None
        assert isinstance(result, Import)
        assert result.name == "dynamic_import"
        assert result.module_path == "my-module"

    def test_dynamic_import_not_found(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)
        extractor.content_lines = ["console.log()"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "console.log()"
            result = extractor._extract_dynamic_import(mock_node)

        assert result is None

    def test_dynamic_import_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)
        mock_node.start_byte = Mock(side_effect=Exception("fail"))

        result = extractor._extract_dynamic_import(mock_node)
        assert result is None


# --- _extract_commonjs_requires (lines 985-1016) ---


class TestExtractCommonjsRequires:
    def test_const_require(self, extractor):
        source = "const fs = require('fs');"
        mock_tree = Mock()
        result = extractor._extract_commonjs_requires(mock_tree, source)
        assert len(result) == 1
        assert result[0].name == "fs"
        assert result[0].module_path == "fs"

    def test_let_require(self, extractor):
        source = "let path = require('path');"
        mock_tree = Mock()
        result = extractor._extract_commonjs_requires(mock_tree, source)
        assert len(result) == 1
        assert result[0].name == "path"

    def test_var_require(self, extractor):
        source = "var util = require('util');"
        mock_tree = Mock()
        result = extractor._extract_commonjs_requires(mock_tree, source)
        assert len(result) == 1
        assert result[0].name == "util"

    def test_multiple_requires(self, extractor):
        source = "const fs = require('fs');\nconst path = require('path');"
        mock_tree = Mock()
        result = extractor._extract_commonjs_requires(mock_tree, source)
        assert len(result) == 2

    def test_no_requires(self, extractor):
        source = "import x from 'y';"
        mock_tree = Mock()
        result = extractor._extract_commonjs_requires(mock_tree, source)
        assert result == []


# --- _extract_commonjs_exports (lines 1044-1076) ---


class TestExtractCommonjsExports:
    def test_module_exports_assignment(self, extractor):
        source = "module.exports = myFunc;"
        mock_tree = Mock()
        result = extractor._extract_commonjs_exports(mock_tree, source)
        assert len(result) >= 1
        assert any(e["is_default"] for e in result)

    def test_module_exports_property(self, extractor):
        source = "module.exports.helper = helperFn;"
        mock_tree = Mock()
        result = extractor._extract_commonjs_exports(mock_tree, source)
        assert len(result) >= 1
        assert result[0]["names"] == ["helper"]

    def test_exports_property(self, extractor):
        source = "exports.foo = bar;"
        mock_tree = Mock()
        result = extractor._extract_commonjs_exports(mock_tree, source)
        assert len(result) >= 1
        assert result[0]["names"] == ["foo"]

    def test_no_commonjs_exports(self, extractor):
        source = "export default x;"
        mock_tree = Mock()
        result = extractor._extract_commonjs_exports(mock_tree, source)
        assert result == []


# --- _infer_type_from_value (lines 1185-1209) ---


class TestInferTypeFromValue:
    def test_string_double_quotes(self, extractor):
        assert extractor._infer_type_from_value('"hello"') == "string"

    def test_string_single_quotes(self, extractor):
        assert extractor._infer_type_from_value("'hello'") == "string"

    def test_string_template_literal(self, extractor):
        assert extractor._infer_type_from_value("`hello`") == "string"

    def test_boolean_true(self, extractor):
        assert extractor._infer_type_from_value("true") == "boolean"

    def test_boolean_false(self, extractor):
        assert extractor._infer_type_from_value("false") == "boolean"

    def test_null(self, extractor):
        assert extractor._infer_type_from_value("null") == "null"

    def test_undefined(self, extractor):
        assert extractor._infer_type_from_value("undefined") == "undefined"

    def test_array(self, extractor):
        assert extractor._infer_type_from_value("[1, 2, 3]") == "array"

    def test_object(self, extractor):
        assert extractor._infer_type_from_value("{a: 1}") == "object"

    def test_number(self, extractor):
        assert extractor._infer_type_from_value("42") == "number"

    def test_float(self, extractor):
        assert extractor._infer_type_from_value("3.14") == "number"

    def test_negative_number(self, extractor):
        assert extractor._infer_type_from_value("-1") == "number"

    def test_function_value(self, extractor):
        assert extractor._infer_type_from_value("function() {}") == "function"

    def test_arrow_function(self, extractor):
        assert extractor._infer_type_from_value("() => {}") == "function"

    def test_none_value(self, extractor):
        assert extractor._infer_type_from_value(None) == "unknown"

    def test_empty_value(self, extractor):
        assert extractor._infer_type_from_value("") == "unknown"

    def test_unknown_value(self, extractor):
        assert extractor._infer_type_from_value("someVar") == "unknown"


# --- _get_variable_kind (lines 1227-1245) ---


class TestGetVariableKind:
    def test_const(self, extractor):
        assert extractor._get_variable_kind("const x = 1;") == "const"

    def test_let(self, extractor):
        assert extractor._get_variable_kind("let x = 1;") == "let"

    def test_var(self, extractor):
        assert extractor._get_variable_kind("var x = 1;") == "var"

    def test_dict_input(self, extractor):
        assert extractor._get_variable_kind({"raw_text": "const x = 1;"}) == "const"

    def test_dict_empty(self, extractor):
        assert extractor._get_variable_kind({"raw_text": ""}) == "unknown"

    def test_empty_string(self, extractor):
        assert extractor._get_variable_kind("") == "unknown"

    def test_unknown_prefix(self, extractor):
        assert extractor._get_variable_kind("x = 1;") == "unknown"


# --- _clean_jsdoc (lines 1295-1316) ---


class TestCleanJsdoc:
    def test_basic_jsdoc(self, extractor):
        text = "/**\n * Hello world\n */"
        result = extractor._clean_jsdoc(text)
        assert "Hello world" in result

    def test_empty_jsdoc(self, extractor):
        assert extractor._clean_jsdoc("") == ""

    def test_jsdoc_with_params(self, extractor):
        text = "/**\n * @param {string} name\n * @returns {void}\n */"
        result = extractor._clean_jsdoc(text)
        assert "@param" in result
        assert "@returns" in result


# --- _get_node_type_for_element (lines 1442-1460) ---


class TestGetNodeTypeForElement:
    def test_arrow_function(self, plugin):
        func = Function(
            name="fn",
            start_line=1,
            end_line=1,
            raw_text="x => x",
            language="javascript",
            is_arrow=True,
        )
        assert plugin._get_node_type_for_element(func) == "arrow_function"

    def test_method(self, plugin):
        func = Function(
            name="method",
            start_line=1,
            end_line=1,
            raw_text="method() {}",
            language="javascript",
            is_method=True,
        )
        assert plugin._get_node_type_for_element(func) == "method_definition"

    def test_regular_function(self, plugin):
        func = Function(
            name="fn",
            start_line=1,
            end_line=1,
            raw_text="function fn() {}",
            language="javascript",
        )
        assert plugin._get_node_type_for_element(func) == "function_declaration"

    def test_class_element(self, plugin):
        cls = Class(
            name="MyClass",
            start_line=1,
            end_line=1,
            raw_text="class MyClass {}",
            language="javascript",
        )
        assert plugin._get_node_type_for_element(cls) == "class_declaration"

    def test_variable_element(self, plugin):
        var = Variable(
            name="x",
            start_line=1,
            end_line=1,
            raw_text="const x = 1;",
            language="javascript",
        )
        assert plugin._get_node_type_for_element(var) == "variable_declaration"

    def test_import_element(self, plugin):
        imp = Import(
            name="x",
            start_line=1,
            end_line=1,
            raw_text="import x from 'y';",
            language="javascript",
        )
        assert plugin._get_node_type_for_element(imp) == "import_statement"

    def test_unknown_element(self, plugin):
        assert plugin._get_node_type_for_element("not an element") == "unknown"


# --- execute_query_strategy (lines 1435-1440) ---


class TestExecuteQueryStrategy:
    def test_none_query_key(self, plugin):
        result = plugin.execute_query_strategy(None, "javascript")
        assert result is None

    def test_invalid_query_key(self, plugin):
        result = plugin.execute_query_strategy("nonexistent_key", "javascript")
        assert result is None


# --- get_element_categories (lines 1462+) ---


class TestGetElementCategories:
    def test_returns_dict(self, plugin):
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        assert "function" in cats
        assert "class" in cats
        assert "variable" in cats
        assert "import" in cats


# --- _detect_file_characteristics angular branch (line 206) ---


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


# --- _find_parent_class_name (lines 1159-1168) ---


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


# --- _is_react_component (lines 1170-1179) ---


class TestIsReactComponent:
    def test_react_component(self, extractor):
        extractor.framework_type = "react"
        mock_node = Mock()
        extractor.content_lines = ["class MyComp extends React.Component {}"]
        extractor._file_encoding = "utf-8"
        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "class MyComp extends React.Component {}"
            assert extractor._is_react_component(mock_node, "MyComp") is True

    def test_not_react_framework(self, extractor):
        extractor.framework_type = "vue"
        mock_node = Mock()
        assert extractor._is_react_component(mock_node, "MyComp") is False


# --- _is_exported_class (lines 1181-1183) ---


class TestIsExportedClass:
    def test_exported(self, extractor):
        extractor.exports = [{"names": ["MyClass"]}]
        assert extractor._is_exported_class("MyClass") is True

    def test_not_exported(self, extractor):
        extractor.exports = []
        assert extractor._is_exported_class("MyClass") is False


# --- _extract_export_info (lines 1020-1042) ---


class TestExtractExportInfo:
    def test_valid_export(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 25)
        extractor.content_lines = ["export default MyComponent;"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
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
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "const x = 1;"
            result = extractor._extract_export_info(mock_node)

        assert result is None


# --- extract_elements at extractor level (lines 1211-1225) ---


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


# --- _extract_generator_function_optimized (lines 503-546) ---


class TestExtractGeneratorFunction:
    def test_generator_extraction(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 1)

        extractor.content_lines = ["function* gen() {", "  yield 1;", "}"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
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


# --- _extract_property_optimized (lines 612-657) ---


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
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = lambda *a, **kw: {
                (0, 4): "name",
                (7, 14): "'value'",
                (0, 14): "name = 'value'",
            }.get((mock_extract.call_count, 0), "name")

            # Simplify: just mock _get_node_text_optimized directly
            pass

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


# --- _extract_import_info_enhanced (lines 929-955) ---


class TestExtractImportInfoEnhanced:
    def test_valid_import(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)
        extractor.content_lines = ["import React from 'react';"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
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
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "import ;"
            result = extractor._extract_import_info_enhanced(mock_node, "import ;")

        assert result is None


# --- _extract_import_names (lines 900-927) ---


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


# --- get_queries / get_supported_features (lines 1420+) ---


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


# --- Multi-line node text extraction fallback (lines 324-334) ---


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
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "err")
            result = extractor._get_node_text_optimized(mock_node)

        assert "line one content" in result
        assert "line two content" in result
