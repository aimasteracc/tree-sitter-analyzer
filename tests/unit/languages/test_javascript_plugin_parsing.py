"""
Parsing tests for JavaScript plugin.
Split from test_javascript_plugin_coverage_boost.py.
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


class TestExtractDynamicImport:
    def test_dynamic_import(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)
        extractor.content_lines = ["const mod = import('my-module');"]
        extractor._file_encoding = "utf-8"

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
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
            "tree_sitter_analyzer.languages.javascript_plugin.extractor.extract_text_slice"
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
