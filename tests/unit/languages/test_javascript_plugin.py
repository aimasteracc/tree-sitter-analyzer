#!/usr/bin/env python3
"""
Tests for Enhanced JavaScript Plugin

Tests for the enhanced JavaScript plugin with comprehensive feature support
including ES6+, async/await, classes, modules, JSX, and framework-specific patterns.

Consolidated from:
  - test_javascript_plugin_comprehensive.py (canonical)
  - test_javascript_plugin_edge_cases.py
  - test_javascript_plugin_extended.py
  - test_javascript_plugin_coverage_boost.py
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)
from tree_sitter_analyzer.models import Class, Function, Variable


@pytest.fixture
def extractor():
    """Fixture to provide enhanced JavaScriptElementExtractor instance"""
    return JavaScriptElementExtractor()


@pytest.fixture
def plugin():
    """Fixture to provide enhanced JavaScriptPlugin instance"""
    return JavaScriptPlugin()


class TestJavaScriptElementExtractor:
    """Tests for JavaScript element extractor"""

    def test_detect_file_characteristics_module(self, extractor):
        """Test detection of ES6 module characteristics"""
        extractor.source_code = "import React from 'react'; export default MyComponent;"
        extractor._detect_file_characteristics()

        assert extractor.is_module is True
        assert extractor.framework_type == "react"

    def test_detect_file_characteristics_jsx(self, extractor):
        """Test detection of JSX characteristics"""
        extractor.current_file = "Component.jsx"
        extractor.source_code = "return <div>Hello World</div>;"
        extractor._detect_file_characteristics()

        assert extractor.is_jsx is True

    def test_detect_file_characteristics_vue(self, extractor):
        """Test detection of Vue framework"""
        extractor.source_code = "import Vue from 'vue';"
        extractor._detect_file_characteristics()

        assert extractor.framework_type == "vue"

    def test_infer_type_from_value_string(self, extractor):
        """Test type inference for string values"""
        assert extractor._infer_type_from_value('"hello"') == "string"
        assert extractor._infer_type_from_value("'world'") == "string"
        assert extractor._infer_type_from_value("`template`") == "string"

    def test_infer_type_from_value_number(self, extractor):
        """Test type inference for number values"""
        assert extractor._infer_type_from_value("42") == "number"
        assert extractor._infer_type_from_value("3.14") == "number"
        assert extractor._infer_type_from_value("-10") == "number"

    def test_infer_type_from_value_boolean(self, extractor):
        """Test type inference for boolean values"""
        assert extractor._infer_type_from_value("true") == "boolean"
        assert extractor._infer_type_from_value("false") == "boolean"

    def test_infer_type_from_value_null_undefined(self, extractor):
        """Test type inference for null and undefined"""
        assert extractor._infer_type_from_value("null") == "null"
        assert extractor._infer_type_from_value("undefined") == "undefined"

    def test_infer_type_from_value_array_object(self, extractor):
        """Test type inference for arrays and objects"""
        assert extractor._infer_type_from_value("[1, 2, 3]") == "array"
        assert extractor._infer_type_from_value("{ a: 1 }") == "object"

    def test_infer_type_from_value_function(self, extractor):
        """Test type inference for functions"""
        assert extractor._infer_type_from_value("function() {}") == "function"
        assert extractor._infer_type_from_value("() => {}") == "function"

    def test_parse_import_statement_default(self, extractor):
        """Test parsing default import statements"""
        result = extractor._parse_import_statement("import React from 'react';")
        assert result is not None
        import_type, names, source, is_default, is_namespace = result
        assert import_type == "default"
        assert names == ["React"]
        assert source == "react"
        assert is_default is True
        assert is_namespace is False

    def test_parse_import_statement_named(self, extractor):
        """Test parsing named import statements"""
        result = extractor._parse_import_statement(
            "import { useState, useEffect } from 'react';"
        )
        assert result is not None
        import_type, names, source, is_default, is_namespace = result
        assert import_type == "named"
        assert "useState" in names
        assert "useEffect" in names
        assert source == "react"
        assert is_default is False
        assert is_namespace is False

    def test_parse_import_statement_namespace(self, extractor):
        """Test parsing namespace import statements"""
        result = extractor._parse_import_statement("import * as React from 'react';")
        assert result is not None
        import_type, names, source, is_default, is_namespace = result
        assert import_type == "namespace"
        assert names == ["React"]
        assert source == "react"
        assert is_default is False
        assert is_namespace is True

    def test_parse_export_statement_default(self, extractor):
        """Test parsing default export statements"""
        result = extractor._parse_export_statement("export default MyComponent;")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "default"
        assert names == ["MyComponent"]
        assert is_default is True

    def test_parse_export_statement_named(self, extractor):
        """Test parsing named export statements"""
        result = extractor._parse_export_statement("export { Component1, Component2 };")
        assert result is not None
        export_type, names, is_default = result
        assert export_type == "named"
        assert "Component1" in names
        assert "Component2" in names
        assert is_default is False

    def test_extract_parameters_regular(self, extractor, mocker):
        """Test parameter extraction for regular parameters"""
        mock_params_node = mocker.MagicMock()

        # Mock identifier child
        mock_identifier = mocker.MagicMock()
        mock_identifier.type = "identifier"
        extractor._get_node_text_optimized = mocker.MagicMock(return_value="param1")

        mock_params_node.children = [mock_identifier]

        params = extractor._extract_parameters(mock_params_node)
        assert params == ["param1"]

    def test_extract_parameters_rest(self, extractor, mocker):
        """Test parameter extraction for rest parameters"""
        mock_params_node = mocker.MagicMock()

        # Mock rest parameter child
        mock_rest = mocker.MagicMock()
        mock_rest.type = "rest_parameter"
        extractor._get_node_text_optimized = mocker.MagicMock(return_value="...args")

        mock_params_node.children = [mock_rest]

        params = extractor._extract_parameters(mock_params_node)
        assert params == ["...args"]

    def test_extract_parameters_destructuring(self, extractor, mocker):
        """Test parameter extraction for destructuring parameters"""
        mock_params_node = mocker.MagicMock()

        # Mock destructuring parameter child
        mock_destructure = mocker.MagicMock()
        mock_destructure.type = "object_pattern"
        extractor._get_node_text_optimized = mocker.MagicMock(return_value="{ a, b }")

        mock_params_node.children = [mock_destructure]

        params = extractor._extract_parameters(mock_params_node)
        assert params == ["{ a, b }"]

    def test_clean_jsdoc(self, extractor):
        """Test JSDoc cleaning functionality"""
        jsdoc_text = """/**
         * This is a function
         * @param {string} name - The name parameter
         * @returns {string} The greeting
         */"""

        cleaned = extractor._clean_jsdoc(jsdoc_text)
        expected = "This is a function @param {string} name - The name parameter @returns {string} The greeting"
        assert cleaned == expected

    def test_calculate_complexity_optimized(self, extractor, mocker):
        """Test complexity calculation"""
        mock_node = mocker.MagicMock()
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="if (x) { while (y) { for (z) { } } }"
        )

        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert complexity >= 4  # Base 1 + if + while + for

    def test_get_variable_kind_const(self, extractor):
        """Test variable kind detection for const"""
        var_data = {"raw_text": "const x = 1;"}
        kind = extractor._get_variable_kind(var_data)
        assert kind == "const"

    def test_get_variable_kind_let(self, extractor):
        """Test variable kind detection for let"""
        var_data = {"raw_text": "let x = 1;"}
        kind = extractor._get_variable_kind(var_data)
        assert kind == "let"

    def test_get_variable_kind_var(self, extractor):
        """Test variable kind detection for var"""
        var_data = {"raw_text": "var x = 1;"}
        kind = extractor._get_variable_kind(var_data)
        assert kind == "var"

    def test_extract_commonjs_requires(self, extractor, mocker):
        """Test CommonJS require extraction"""
        mock_tree = mocker.MagicMock()
        source_code = "const fs = require('fs');\nconst path = require('path');"

        imports = extractor._extract_commonjs_requires(mock_tree, source_code)

        assert len(imports) == 2
        assert imports[0].name == "fs"
        assert imports[0].module_path == "fs"
        assert imports[1].name == "path"
        assert imports[1].module_path == "path"

    def test_extract_commonjs_exports(self, extractor, mocker):
        """Test CommonJS exports extraction"""
        mock_tree = mocker.MagicMock()
        source_code = "module.exports = MyClass;\nexports.helper = function() {};"

        exports = extractor._extract_commonjs_exports(mock_tree, source_code)

        assert len(exports) >= 1
        # Check that at least one export was found
        export_names = [exp.get("names", []) for exp in exports]
        assert any("MyClass" in names for names in export_names)

    # --- Merged from test_javascript_plugin_extended.py ---

    def test_extract_function_optimized_with_valid_node(self, extractor, mocker):
        """Test function info extraction with valid node"""
        source_code = "function testFunc(a) { return a; }"
        extractor.source_code = source_code
        extractor.content_lines = [source_code]

        mock_node = mocker.MagicMock()
        mock_node.type = "function_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, len(source_code))
        mock_node.start_byte = 0
        mock_node.end_byte = len(source_code)

        mock_identifier = mocker.MagicMock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 9
        mock_identifier.end_byte = 17
        mock_identifier.text = b"testFunc"

        mock_params = mocker.MagicMock()
        mock_params.type = "formal_parameters"
        mock_param_child = mocker.MagicMock()
        mock_param_child.type = "identifier"
        mock_param_child.start_byte = 18
        mock_param_child.end_byte = 19
        mock_param_child.text = b"a"
        mock_params.children = [mock_param_child]

        mock_node.children = [mock_identifier, mock_params]

        def mock_get_text(node):
            if node == mock_node:
                return source_code
            elif node == mock_identifier:
                return "testFunc"
            elif node == mock_param_child:
                return "a"
            elif node == mock_params:
                return "(a)"
            return ""

        mocker.patch.object(
            extractor, "_get_node_text_optimized", side_effect=mock_get_text
        )

        function = extractor._extract_function_optimized(mock_node)

        assert function is not None
        assert isinstance(function, Function)
        assert function.name == "testFunc"
        assert function.parameters == ["a"]
        assert function.language == "javascript"

    def test_extract_class_optimized_with_valid_node(self, extractor, mocker):
        """Test class info extraction with valid node"""
        source_code = "class MyClass { constructor() {} }"
        extractor.source_code = source_code

        mock_node = mocker.MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, len(source_code))
        mock_node.start_byte = 0
        mock_node.end_byte = len(source_code)

        mock_identifier = mocker.MagicMock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 6
        mock_identifier.end_byte = 13
        mock_identifier.text = b"MyClass"

        mock_node.children = [mock_identifier]

        cls = extractor._extract_class_optimized(mock_node)

        assert cls is not None
        assert isinstance(cls, Class)
        assert cls.name == "MyClass"
        assert cls.class_type == "class"
        assert cls.language == "javascript"

    def test_extract_variable_info_with_valid_node(self, extractor, mocker):
        """Test variable info extraction with valid node"""
        mock_node = mocker.MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 15

        mock_declarator = mocker.MagicMock()
        mock_declarator.type = "variable_declarator"

        mock_identifier = mocker.MagicMock()
        mock_identifier.type = "identifier"
        mock_identifier.start_byte = 4
        mock_identifier.end_byte = 9

        mock_declarator.children = [mock_identifier]
        mock_node.children = [mock_declarator]

        source_code = "let myVar = 42;"

        extractor.source_code = source_code
        extractor.content_lines = [source_code]

        mock_node.type = "variable_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, len(source_code))
        mock_identifier.text = b"myVar"

        variables = extractor._extract_variable_optimized(mock_node)

        assert variables is not None
        assert len(variables) > 0
        variable = variables[0]
        assert isinstance(variable, Variable)
        assert variable.name == "myVar"
        assert variable.language == "javascript"


class TestJavaScriptPlugin:
    """Tests for JavaScript plugin"""

    def test_plugin_enhanced_properties(self, plugin):
        """Test enhanced plugin properties"""
        assert plugin.language_name == "javascript"
        assert plugin.get_language_name() == "javascript"

        extensions = plugin.get_file_extensions()
        expected_extensions = [".js", ".mjs", ".jsx", ".es6", ".es"]
        for ext in expected_extensions:
            assert ext in extensions

    def test_get_supported_queries(self, plugin):
        """Test supported queries include enhanced features"""
        queries = plugin.get_supported_queries()

        expected_queries = [
            "function",
            "class",
            "variable",
            "import",
            "export",
            "async_function",
            "arrow_function",
            "method",
            "constructor",
            "react_component",
            "react_hook",
            "jsx_element",
        ]

        for query in expected_queries:
            assert query in queries

    def test_get_plugin_info(self, plugin):
        """Test enhanced plugin info"""
        info = plugin.get_plugin_info()

        assert info["name"] == "JavaScript Plugin"
        assert info["language"] == "javascript"
        assert info["version"] == "2.0.0"

        features = info["features"]
        expected_features = [
            "ES6+ syntax support",
            "Async/await functions",
            "Arrow functions",
            "JSX support",
            "React component detection",
            "CommonJS support",
            "JSDoc extraction",
            "Complexity analysis",
        ]

        for feature in expected_features:
            assert feature in features

    def test_is_applicable_enhanced_extensions(self, plugin):
        """Test applicability for enhanced file extensions"""
        test_files = ["app.js", "module.mjs", "Component.jsx", "legacy.es6", "old.es"]

        for file_path in test_files:
            assert plugin.is_applicable(file_path) is True

    def test_is_not_applicable(self, plugin):
        """Test non-applicable file types"""
        test_files = ["style.css", "data.json", "Main.java", "script.py", "README.md"]

        for file_path in test_files:
            assert plugin.is_applicable(file_path) is False

    # --- Merged from test_javascript_plugin_extended.py ---

    def test_create_extractor(self, plugin):
        """Test extractor creation"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, JavaScriptElementExtractor)

    def test_tree_sitter_language_caching(self, plugin):
        """Test tree-sitter language caching"""
        language1 = plugin.get_tree_sitter_language()
        language2 = plugin.get_tree_sitter_language()
        assert language1 is language2

    # --- Merged from test_javascript_plugin_edge_cases.py ---

    def test_plugin_with_invalid_tree(self, plugin):
        """Test plugin behavior with invalid tree"""
        result = plugin.extract_elements(None, "function test() {}")
        assert result == {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
            "exports": [],
        }

        invalid_tree = Mock()
        invalid_tree.root_node = None

        result = plugin.extract_elements(invalid_tree, "function test() {}")
        assert result == {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
            "exports": [],
        }

    def test_plugin_with_extraction_errors(self, plugin):
        """Test plugin behavior when extraction methods raise errors"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(plugin, "extractor") as mock_extractor:
            mock_extractor.extract_functions.side_effect = Exception(
                "Function extraction error"
            )
            mock_extractor.extract_classes.side_effect = Exception(
                "Class extraction error"
            )
            mock_extractor.extract_variables.side_effect = Exception(
                "Variable extraction error"
            )
            mock_extractor.extract_imports.side_effect = Exception(
                "Import extraction error"
            )
            mock_extractor.extract_exports.side_effect = Exception(
                "Export extraction error"
            )

            result = plugin.extract_elements(mock_tree, "function test() {}")

            assert result == {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "exports": [],
            }


class TestJavaScriptComplexityAnalysis:
    """Tests for JavaScript complexity analysis"""

    def test_complexity_simple_function(self, extractor, mocker):
        """Test complexity calculation for simple function"""
        mock_node = mocker.MagicMock()
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="function simple() { return 'hello'; }"
        )

        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert complexity == 1  # Base complexity

    def test_complexity_with_conditionals(self, extractor, mocker):
        """Test complexity calculation with conditionals"""
        mock_node = mocker.MagicMock()
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="function complex(x) { if (x > 0) return x; else if (x < 0) return -x; else return 0; }"
        )

        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert complexity >= 3  # Base 1 + if + else if

    def test_complexity_with_loops(self, extractor, mocker):
        """Test complexity calculation with loops"""
        mock_node = mocker.MagicMock()
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="function loop() { for (let i = 0; i < 10; i++) { while (condition) { } } }"
        )

        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert complexity >= 3  # Base 1 + for + while

    def test_complexity_with_logical_operators(self, extractor, mocker):
        """Test complexity calculation with logical operators"""
        mock_node = mocker.MagicMock()
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="function logical(a, b, c) { return a && b || c; }"
        )

        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert complexity >= 3  # Base 1 + && + ||


class TestJavaScriptFrameworkDetection:
    """Tests for framework-specific detection"""

    def test_react_component_detection(self, extractor, mocker):
        """Test React component detection"""
        mock_node = mocker.MagicMock()
        extractor.framework_type = "react"
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="class MyComponent extends React.Component { render() { return <div />; } }"
        )

        is_react = extractor._is_react_component(mock_node, "MyComponent")
        assert is_react is True

    def test_non_react_component(self, extractor, mocker):
        """Test non-React component detection"""
        mock_node = mocker.MagicMock()
        extractor.framework_type = "vue"
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="class MyClass { constructor() {} }"
        )

        is_react = extractor._is_react_component(mock_node, "MyClass")
        assert is_react is False

    def test_exported_class_detection(self, extractor):
        """Test exported class detection"""
        extractor.exports = [
            {"names": ["MyComponent"], "is_default": True},
            {"names": ["Helper", "Utility"], "is_default": False},
        ]

        assert extractor._is_exported_class("MyComponent") is True
        assert extractor._is_exported_class("Helper") is True
        assert extractor._is_exported_class("Unknown") is False

    # --- Merged from test_javascript_plugin_edge_cases.py ---

    def test_framework_detection_with_mixed_frameworks(self, extractor):
        """Test framework detection with mixed framework imports"""
        mixed_code = """
        import React from 'react';
        import Vue from 'vue';
        import { Component } from '@angular/core';
        """

        extractor.source_code = mixed_code
        extractor._detect_file_characteristics()

        # Should detect one of the frameworks (first one found)
        assert extractor.framework_type in ["react", "vue", "angular", ""]

    def test_jsx_detection_with_false_positives(self, extractor):
        """Test JSX detection with potential false positives"""
        false_positive_code = """
        const template = '<div>Not JSX</div>';
        const comparison = a < b && c > d;
        const generic = new Map<string, number>();
        """

        extractor.source_code = false_positive_code
        extractor.current_file = "test.js"
        extractor._detect_file_characteristics()

        # Should not detect as JSX
        assert extractor.is_jsx is False


class TestJavaScriptErrorHandling:
    """Tests for error handling in JavaScript plugin"""

    def test_parse_function_signature_error(self, extractor, mocker):
        """Test function signature parsing with error"""
        mock_node = mocker.MagicMock()
        mock_node.children = []
        extractor._get_node_text_optimized = mocker.MagicMock(
            side_effect=Exception("Parse error")
        )

        result = extractor._parse_function_signature_optimized(mock_node)
        assert result is None

    def test_parse_method_signature_error(self, extractor, mocker):
        """Test method signature parsing with error"""
        mock_node = mocker.MagicMock()
        mock_node.children = []
        extractor._get_node_text_optimized = mocker.MagicMock(
            side_effect=Exception("Parse error")
        )

        result = extractor._parse_method_signature_optimized(mock_node)
        assert result is None

    def test_parse_import_statement_error(self, extractor):
        """Test import statement parsing with malformed input"""
        result = extractor._parse_import_statement("invalid import statement")
        assert result is None

    def test_parse_export_statement_error(self, extractor):
        """Test export statement parsing with malformed input"""
        result = extractor._parse_export_statement("invalid export statement")
        assert result is None

    def test_extract_jsdoc_error(self, extractor):
        """Test JSDoc extraction with error conditions"""
        extractor.content_lines = []
        jsdoc = extractor._extract_jsdoc_for_line(1)
        assert jsdoc is None

    def test_complexity_calculation_error(self, extractor, mocker):
        """Test complexity calculation with error"""
        mock_node = mocker.MagicMock()
        extractor._get_node_text_optimized = mocker.MagicMock(
            side_effect=Exception("Text error")
        )

        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert complexity == 1  # Should return base complexity on error

    # --- Merged from test_javascript_plugin_edge_cases.py ---

    def test_empty_source_code(self, extractor):
        """Test handling of empty source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        functions = extractor.extract_functions(mock_tree, "")
        classes = extractor.extract_classes(mock_tree, "")
        variables = extractor.extract_variables(mock_tree, "")
        imports = extractor.extract_imports(mock_tree, "")
        exports = extractor.extract_exports(mock_tree, "")

        assert functions == []
        assert classes == []
        assert variables == []
        assert imports == []
        assert exports == []

    def test_malformed_javascript_code(self, extractor):
        """Test handling of malformed JavaScript code"""
        malformed_code = """
        function incomplete(
        class MissingBrace {
            method() {
                // missing closing brace

        const incomplete =

        import from 'module';
        export ;
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should not crash with malformed code
        functions = extractor.extract_functions(mock_tree, malformed_code)
        classes = extractor.extract_classes(mock_tree, malformed_code)
        variables = extractor.extract_variables(mock_tree, malformed_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)

    def test_unicode_and_special_characters(self, extractor):
        """Test handling of Unicode and special characters"""
        unicode_code = """
        // Japanese comments
        const variable = "value";

        function func(param) {
            return "result";
        }

        const emoji = "test";
        const symbols = "!@#$%^&*()_+-=[]{}|;':,./<>?";
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle Unicode without crashing
        functions = extractor.extract_functions(mock_tree, unicode_code)
        classes = extractor.extract_classes(mock_tree, unicode_code)
        variables = extractor.extract_variables(mock_tree, unicode_code)

        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)

    def test_deeply_nested_structures(self, extractor):
        """Test handling of deeply nested code structures"""
        nested_code = """
        function level1() {
            function level2() {
                function level3() {
                    function level4() {
                        function level5() {
                            return "deep";
                        }
                        return level5();
                    }
                    return level4();
                }
                return level3();
            }
            return level2();
        }
        """

        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Should handle nested structures
        functions = extractor.extract_functions(mock_tree, nested_code)
        assert isinstance(functions, list)

    def test_arrow_function_without_parent(self, extractor):
        """Test arrow function extraction without proper parent"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.parent = None
        mock_node.children = []

        extractor.content_lines = ["() => {}"]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.return_value = "() => {}"

            with patch.object(extractor, "_extract_jsdoc_for_line") as mock_jsdoc:
                mock_jsdoc.return_value = None

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 1

                    result = extractor._extract_arrow_function_optimized(mock_node)

                    assert isinstance(result, Function)
                    assert result.name == "anonymous"

    def test_class_extraction_without_name(self, extractor):
        """Test class extraction when class has no name"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []  # No identifier child

        result = extractor._extract_class_optimized(mock_node)
        assert result is None


class TestJavaScriptCaching:
    """Tests for caching mechanisms in JavaScript plugin"""

    def test_node_text_caching(self, extractor, mocker):
        """Test node text caching"""
        mock_node = mocker.MagicMock()

        # Mock the node properties
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        extractor.content_lines = ["test code here"]

        # First call should compute and cache
        text1 = extractor._get_node_text_optimized(mock_node)

        # Second call should return cached result
        text2 = extractor._get_node_text_optimized(mock_node)

        assert text1 == text2
        # Cache uses (start_byte, end_byte) tuple as key
        assert (mock_node.start_byte, mock_node.end_byte) in extractor._node_text_cache

    def test_jsdoc_caching(self, extractor):
        """Test JSDoc caching"""
        extractor.content_lines = [
            "/**",
            " * Test function",
            " */",
            "function test() {}",
        ]

        # First call should compute and cache
        jsdoc1 = extractor._extract_jsdoc_for_line(4)

        # Second call should return cached result
        jsdoc2 = extractor._extract_jsdoc_for_line(4)

        assert jsdoc1 == jsdoc2
        assert 4 in extractor._jsdoc_cache

    def test_complexity_caching(self, extractor, mocker):
        """Test complexity calculation caching"""
        mock_node = mocker.MagicMock()
        node_id = id(mock_node)
        extractor._get_node_text_optimized = mocker.MagicMock(
            return_value="if (x) return x;"
        )

        # First call should compute and cache
        complexity1 = extractor._calculate_complexity_optimized(mock_node)

        # Second call should return cached result
        complexity2 = extractor._calculate_complexity_optimized(mock_node)

        assert complexity1 == complexity2
        assert node_id in extractor._complexity_cache


# ---------------------------------------------------------------------------
# NEW: Integration tests using real tree-sitter parsing
# ---------------------------------------------------------------------------


@pytest.fixture
def js_parser():
    """Create a real JavaScript tree-sitter parser."""
    from tree_sitter_analyzer.language_loader import loader
    parser = loader.create_parser_safely("javascript")
    if parser is None:
        pytest.skip("JavaScript tree-sitter parser not available")
    return parser


class TestExtractFunctionsIntegration:
    """Integration tests for extract_functions using real tree-sitter parsing."""

    def test_extract_regular_function(self, extractor, js_parser):
        code = "function greet(name) {\n  return 'Hello ' + name;\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) == 1
        assert functions[0].name == "greet"
        assert functions[0].is_async is False
        assert functions[0].is_arrow is False

    def test_extract_async_function(self, extractor, js_parser):
        code = "async function fetchData(url) {\n  return fetch(url);\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) == 1
        assert functions[0].is_async is True

    def test_extract_generator_function(self, extractor, js_parser):
        code = "function* counter() {\n  let i = 0;\n  while (true) { yield i++; }\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) == 1
        assert functions[0].is_generator is True

    def test_extract_arrow_function(self, extractor, js_parser):
        code = "const add = (a, b) => a + b;\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) == 1
        assert functions[0].is_arrow is True
        assert functions[0].name == "add"

    def test_extract_class_methods(self, extractor, js_parser):
        code = "class MyClass {\n  constructor(name) { this.name = name; }\n  static create() { return new MyClass('x'); }\n  async fetch() { return 1; }\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        names = [f.name for f in functions]
        assert "constructor" in names
        assert "create" in names
        assert "fetch" in names

    def test_extract_getter_setter(self, extractor, js_parser):
        code = "class P {\n  get name() { return this._n; }\n  set name(v) { this._n = v; }\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) == 2

    def test_extract_function_with_jsdoc(self, extractor, js_parser):
        code = "/**\n * Greets a user\n * @param {string} name\n */\nfunction greet(name) { return name; }\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert len(functions) == 1
        assert functions[0].docstring is not None

    def test_extract_function_complexity(self, extractor, js_parser):
        code = "function complex(x) {\n  if (x > 0) {\n    for (let i = 0; i < x; i++) {\n      if (i % 2 === 0 && x > 10) { return i; }\n    }\n  }\n  return x || 0;\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        functions = extractor.extract_functions(tree, code)
        assert functions[0].complexity_score > 1


class TestExtractClassesIntegration:

    def test_extract_basic_class(self, extractor, js_parser):
        code = "class Animal {\n  constructor(name) { this.name = name; }\n}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert len(classes) == 1
        assert classes[0].name == "Animal"

    def test_extract_class_extends(self, extractor, js_parser):
        code = "class Animal {}\nclass Dog extends Animal { bark() { return 'Woof'; } }\n"
        tree = js_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        dog = next(c for c in classes if c.name == "Dog")
        assert dog.superclass == "Animal"

    def test_extract_class_with_jsdoc(self, extractor, js_parser):
        code = "/**\n * A vehicle\n */\nclass Vehicle { constructor() {} }\n"
        tree = js_parser.parse(code.encode("utf-8"))
        classes = extractor.extract_classes(tree, code)
        assert classes[0].docstring is not None


class TestExtractVariablesIntegration:

    def test_extract_const(self, extractor, js_parser):
        code = "const MAX = 100;\n"
        tree = js_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        assert len(variables) == 1
        assert variables[0].is_constant is True

    def test_extract_various_types(self, extractor, js_parser):
        code = "const s = 'hello';\nconst n = 42;\nconst b = true;\nconst a = [1,2];\nconst o = {k:'v'};\n"
        tree = js_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        type_map = {v.name: v.variable_type for v in variables}
        assert type_map.get("s") == "string"
        assert type_map.get("n") == "number"
        assert type_map.get("b") == "boolean"

    def test_arrow_not_counted_as_variable(self, extractor, js_parser):
        code = "const fn = (x) => x * 2;\nconst val = 10;\n"
        tree = js_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "fn" not in names
        assert "val" in names


class TestExtractImportsIntegration:

    def test_extract_named_imports(self, extractor, js_parser):
        code = "import { useState, useEffect } from 'react';\n"
        tree = js_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert len(imports) == 1
        assert imports[0].module_path == "react"

    def test_extract_require(self, extractor, js_parser):
        code = "const fs = require('fs');\nconst path = require('path');\n"
        tree = js_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert len(imports) == 2

    def test_extract_dynamic_import(self, extractor, js_parser):
        code = "import('./module.js');\n"
        tree = js_parser.parse(code.encode("utf-8"))
        imports = extractor.extract_imports(tree, code)
        assert len(imports) == 1
        assert imports[0].name == "dynamic_import"


class TestExtractExportsIntegration:

    def test_extract_default_export(self, extractor, js_parser):
        code = "export default MyComponent;\n"
        tree = js_parser.parse(code.encode("utf-8"))
        exports = extractor.extract_exports(tree, code)
        assert len(exports) >= 1

    def test_extract_named_exports(self, extractor, js_parser):
        code = "export { helper, utility };\n"
        tree = js_parser.parse(code.encode("utf-8"))
        exports = extractor.extract_exports(tree, code)
        assert len(exports) >= 1

    def test_extract_direct_function_export(self, extractor, js_parser):
        code = "export function doSomething() {}\n"
        tree = js_parser.parse(code.encode("utf-8"))
        exports = extractor.extract_exports(tree, code)
        assert len(exports) >= 1

    def test_extract_commonjs_module_exports(self, extractor, js_parser):
        code = "module.exports = MyClass;\n"
        tree = js_parser.parse(code.encode("utf-8"))
        exports = extractor.extract_exports(tree, code)
        assert len(exports) >= 1


class TestExtractElementsIntegration:

    def test_extractor_extract_elements(self, extractor, js_parser):
        code = "import React from 'react';\nconst MAX = 100;\nfunction hello() { return 1; }\nclass Foo { constructor() {} }\n"
        tree = js_parser.parse(code.encode("utf-8"))
        elements = extractor.extract_elements(tree, code)
        types = {e.element_type for e in elements}
        assert "function" in types
        assert "class" in types

    def test_plugin_extract_elements(self, plugin, js_parser):
        code = "import React from 'react';\nconst MAX = 100;\nfunction hello() { return 1; }\nclass Foo { constructor() {} }\n"
        tree = js_parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result


class TestPluginMethodsExtended:

    def test_execute_query_strategy_none(self, plugin):
        assert plugin.execute_query_strategy(None, "javascript") is None

    def test_get_element_categories(self, plugin):
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        assert "function" in cats
        assert "class" in cats
        assert "variable" in cats
        assert "import" in cats
        assert "export" in cats

    def test_get_node_type_for_element(self, plugin):
        func = Function(name="test", start_line=1, end_line=1)
        assert plugin._get_node_type_for_element(func) == "function_declaration"
        cls = Class(name="test", start_line=1, end_line=1)
        assert plugin._get_node_type_for_element(cls) == "class_declaration"
        var = Variable(name="test", start_line=1, end_line=1)
        assert plugin._get_node_type_for_element(var) == "variable_declaration"


class TestAnalyzeFileIntegration:

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin, tmp_path):
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        js_file = tmp_path / "test.js"
        js_file.write_text("function hello() { return 1; }\nconst x = 42;\nclass Foo {}\n")
        request = AnalysisRequest(file_path=str(js_file))
        result = await plugin.analyze_file(str(js_file), request)
        assert result.success is True
        assert len(result.elements) >= 2

    @pytest.mark.asyncio
    async def test_analyze_file_language_unavailable(self, plugin):
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        request = AnalysisRequest(file_path="test.js")
        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            result = await plugin.analyze_file("test.js", request)
            assert result.success is False

    @pytest.mark.asyncio
    async def test_analyze_file_tree_sitter_unavailable(self, plugin):
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        request = AnalysisRequest(file_path="test.js")
        with patch("tree_sitter_analyzer.languages.javascript_plugin.TREE_SITTER_AVAILABLE", False):
            result = await plugin.analyze_file("test.js", request)
            assert result.success is False


class TestTraversalEdgeCases:

    def test_traverse_with_none_root(self, extractor):
        results = []
        extractor._traverse_and_extract_iterative(None, {}, results, "function")
        assert results == []


class TestResetCaches:

    def test_reset_caches(self, extractor):
        extractor._node_text_cache[(0, 10)] = "cached"
        extractor._processed_nodes.add(123)
        extractor._reset_caches()
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0


class TestDetectFileCharacteristics:

    def test_detect_angular(self, extractor):
        extractor.source_code = "import { Component } from '@angular/core';"
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "angular"

    def test_detect_no_framework(self, extractor):
        extractor.source_code = "function hello() { return 1; }"
        extractor.current_file = "test.js"
        extractor._detect_file_characteristics()
        assert extractor.is_module is False

    def test_detect_module_from_export(self, extractor):
        extractor.source_code = "export function hello() {}"
        extractor._detect_file_characteristics()
        assert extractor.is_module is True


class TestGetNodeTextFallback:

    def test_fallback_both_fail(self, extractor):
        extractor.content_lines = []
        extractor.source_code = ""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (100, 0)
        node.end_point = (100, 10)
        with patch("tree_sitter_analyzer.languages.javascript_plugin.safe_encode", side_effect=Exception("err")):
            assert extractor._get_node_text_optimized(node) == ""


class TestDynamicImportEdgeCases:

    def test_no_match(self, extractor):
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        extractor._get_node_text_optimized = Mock(return_value="console.log('hi')")
        assert extractor._extract_dynamic_import(node) is None

    def test_exception(self, extractor):
        node = Mock()
        extractor._get_node_text_optimized = Mock(side_effect=Exception("err"))
        assert extractor._extract_dynamic_import(node) is None


class TestCleanJsdocExtended:

    def test_empty(self, extractor):
        assert extractor._clean_jsdoc("") == ""

    def test_none(self, extractor):
        assert extractor._clean_jsdoc(None) == ""

    def test_end_marker(self, extractor):
        assert extractor._clean_jsdoc("*/") == ""


# ====================================================================== #
# TARGETED TESTS for coverage boost (79.7% -> 80%+)
# ====================================================================== #


class TestJavaScriptFallbackBranches:
    """Tests targeting specific uncovered fallback/exception branches."""

    def test_get_node_text_fallback_single_line(self, extractor):
        """Cover lines 319-322: fallback single-line text extraction"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (0, 2)
        node.end_point = (0, 7)
        extractor.content_lines = ["Hello World!"]

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert result == "llo W"

    def test_get_node_text_fallback_multiline(self, extractor):
        """Cover lines 323-334: fallback multiline text extraction"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 30
        node.start_point = (0, 5)
        node.end_point = (2, 3)
        extractor.content_lines = ["Hello World!", "Middle line", "End text"]

        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert "World!" in result
            assert "Middle line" in result
            assert "End" in result

    def test_extract_function_optimized_exception(self, extractor):
        """Cover lines 380-385: exception during function extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_function_optimized(node)
        assert result is None

    def test_extract_arrow_function_exception(self, extractor):
        """Cover lines 444-446: exception during arrow function extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_arrow_function_optimized(node)
        assert result is None

    def test_extract_method_optimized_no_info(self, extractor):
        """Cover line 457: method info returns None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        extractor._parse_method_signature_optimized = Mock(return_value=None)
        result = extractor._extract_method_optimized(node)
        assert result is None

    def test_extract_generator_function_exception(self, extractor):
        """Cover lines 544-546: exception in generator function"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_generator_function_optimized(node)
        assert result is None

    def test_extract_generator_function_no_info(self, extractor):
        """Cover line 514: generator function signature returns None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        extractor._parse_function_signature_optimized = Mock(return_value=None)
        result = extractor._extract_generator_function_optimized(node)
        assert result is None

    def test_extract_class_optimized_exception(self, extractor):
        """Cover lines 595-597: exception in class extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_class_optimized(node)
        assert result is None

    def test_extract_property_optimized_no_name(self, extractor):
        """Cover lines 635-636: property with no name"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.children = []
        node.parent = None
        extractor._get_node_text_optimized = Mock(return_value="some_value")
        result = extractor._extract_property_optimized(node)
        assert result is None

    def test_extract_property_optimized_with_parent_static(self, extractor):
        """Cover lines 630-633: property with static parent"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 30)

        prop_id = Mock()
        prop_id.type = "property_identifier"
        value_node = Mock()
        value_node.type = "number"
        node.children = [prop_id, value_node]

        parent = Mock()
        node.parent = parent

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                prop_id: "myProp",
                value_node: "42",
                node: "static myProp = 42",
                parent: "static myProp = 42",
            }.get(n, "")
        )

        result = extractor._extract_property_optimized(node)
        assert result is not None
        assert result.name == "myProp"
        assert result.is_static is True

    def test_extract_property_optimized_exception(self, extractor):
        """Cover lines 655-657: exception during property extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_property_optimized(node)
        assert result is None

    def test_extract_variables_from_declaration_exception(self, extractor):
        """Cover lines 678-679: exception in variable declaration extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_variables_from_declaration(node, "const")
        assert result == []

    def test_parse_variable_declarator_skip_arrow(self, extractor):
        """Cover lines 722-723: skip arrow function in value assignment"""
        node = Mock()
        identifier = Mock()
        identifier.type = "identifier"
        eq_node = Mock()
        eq_node.type = "="
        arrow = Mock()
        arrow.type = "arrow_function"
        eq_node.next_sibling = arrow
        node.children = [identifier, eq_node, arrow]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                identifier: "myFunc",
                arrow: "() => {}",
                node: "myFunc = () => {}",
            }.get(n, "")
        )
        result = extractor._parse_variable_declarator(node, "const", 1, 1)
        assert result is None

    def test_parse_variable_declarator_no_name(self, extractor):
        """Cover line 728: no identifier found"""
        node = Mock()
        node.children = []
        node.parent = None
        extractor._get_node_text_optimized = Mock(return_value="")
        result = extractor._parse_variable_declarator(node, "const", 1, 1)
        assert result is None

    def test_parse_variable_declarator_exception(self, extractor):
        """Cover lines 765-767: exception in variable declarator parsing"""
        node = Mock()
        type(node).children = property(
            lambda self: (_ for _ in ()).throw(Exception("bad"))
        )
        result = extractor._parse_variable_declarator(node, "const", 1, 1)
        assert result is None

    def test_extract_import_info_simple_exception(self, extractor):
        """Cover lines 896-898: exception in import info extraction"""
        node = Mock()
        node.start_point = Mock(side_effect=Exception("error"))
        extractor.source_code = "import x from 'y';"
        result = extractor._extract_import_info_simple(node)
        assert result is None

    def test_extract_import_info_enhanced(self, extractor):
        """Cover lines 929-955: enhanced import info extraction"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 30)
        extractor._get_node_text_optimized = Mock(
            return_value="import React from 'react';"
        )
        result = extractor._extract_import_info_enhanced(node, "import React from 'react';")
        assert result is not None
        assert result.module_path == "react"

    def test_extract_import_info_enhanced_no_match(self, extractor):
        """Cover line 939: enhanced import returns None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        extractor._get_node_text_optimized = Mock(return_value="invalid")
        result = extractor._extract_import_info_enhanced(node, "invalid")
        assert result is None

    def test_extract_import_info_enhanced_exception(self, extractor):
        """Cover lines 953-955: exception in enhanced import"""
        node = Mock()
        extractor._get_node_text_optimized = Mock(side_effect=Exception("err"))
        result = extractor._extract_import_info_enhanced(node, "test")
        assert result is None

    def test_find_parent_class_name(self, extractor):
        """Cover lines 1159-1168: find parent class name"""
        class_node = Mock()
        class_node.type = "class_declaration"
        id_node = Mock()
        id_node.type = "identifier"
        class_node.children = [id_node]
        class_node.parent = None

        method_node = Mock()
        method_node.type = "method_definition"
        method_node.parent = class_node

        extractor._get_node_text_optimized = Mock(return_value="MyClass")
        result = extractor._find_parent_class_name(method_node)
        assert result == "MyClass"

    def test_find_parent_class_name_none(self, extractor):
        """Cover line 1168: no parent class found"""
        node = Mock()
        node.parent = None
        result = extractor._find_parent_class_name(node)
        assert result is None

    def test_extract_elements_extractor_exception(self, extractor):
        """Cover lines 1222-1223: exception in extract_elements"""
        extractor.extract_functions = Mock(side_effect=Exception("err"))
        tree = Mock()
        tree.root_node = Mock()
        tree.root_node.children = []
        result = extractor.extract_elements(tree, "code")
        assert result == []

    def test_jsdoc_extraction_for_line_1(self, extractor):
        """Cover line 1253: target_line <= 1"""
        extractor.content_lines = ["function test() {}"]
        result = extractor._extract_jsdoc_for_line(1)
        assert result is None

    def test_jsdoc_extraction_cache_hit(self, extractor):
        """Cover lines 1249-1250: cache hit"""
        extractor._jsdoc_cache[5] = "Cached"
        result = extractor._extract_jsdoc_for_line(5)
        assert result == "Cached"

    def test_jsdoc_extraction_exception(self, extractor):
        """Cover lines 1291-1293: exception in jsdoc extraction"""
        extractor.content_lines = None  # Will cause exception
        result = extractor._extract_jsdoc_for_line(5)
        assert result is None

    def test_get_variable_kind_string_input(self, extractor):
        """Cover lines 1231-1232: string input for _get_variable_kind"""
        assert extractor._get_variable_kind("const x = 1") == "const"
        assert extractor._get_variable_kind("let x = 1") == "let"
        assert extractor._get_variable_kind("var x = 1") == "var"

    def test_get_variable_kind_empty(self, extractor):
        """Cover lines 1234-1235: empty input"""
        assert extractor._get_variable_kind("") == "unknown"
        assert extractor._get_variable_kind({"raw_text": ""}) == "unknown"

    def test_get_variable_kind_unknown(self, extractor):
        """Cover lines 1244-1245: unknown kind"""
        assert extractor._get_variable_kind("something else") == "unknown"

    def test_commonjs_exports_exception(self, extractor):
        """Cover lines 1073-1074: exception in CommonJS exports"""
        tree = Mock()
        with patch("re.finditer", side_effect=Exception("err")):
            result = extractor._extract_commonjs_exports(tree, "module.exports = X;")
            assert result == []


class TestJavaScriptPluginAdditionalMethods:
    """Tests for additional plugin-level methods."""

    def test_get_node_type_for_arrow_function(self, plugin):
        """Cover lines 1447-1448: arrow function node type"""
        func = Function(name="test", start_line=1, end_line=1)
        func.is_arrow = True
        func.is_method = False
        assert plugin._get_node_type_for_element(func) == "arrow_function"

    def test_get_node_type_for_method(self, plugin):
        """Cover lines 1449-1450: method definition node type"""
        func = Function(name="test", start_line=1, end_line=1)
        func.is_arrow = False
        func.is_method = True
        assert plugin._get_node_type_for_element(func) == "method_definition"

    def test_get_node_type_for_import(self, plugin):
        """Cover lines 1457-1458: import node type"""
        from tree_sitter_analyzer.models import Import
        imp = Import(name="test", start_line=1, end_line=1)
        assert plugin._get_node_type_for_element(imp) == "import_statement"

    def test_get_node_type_for_unknown(self, plugin):
        """Cover lines 1459-1460: unknown element type"""
        assert plugin._get_node_type_for_element("unknown") == "unknown"

    def test_extract_elements_exception(self, plugin):
        """Cover lines 1611-1613: extract_elements with exception"""
        tree = Mock()
        tree.root_node = Mock()
        tree.root_node.children = []

        with patch.object(plugin._extractor, "extract_functions", side_effect=Exception("err")):
            result = plugin.extract_elements(tree, "code")
            assert result == {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "exports": [],
            }

    @pytest.mark.asyncio
    async def test_analyze_file_exception(self, plugin, tmp_path):
        """Cover lines 1578-1585: analyze_file with exception"""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        request = AnalysisRequest(file_path="test.js")
        result = await plugin.analyze_file("/nonexistent/file.js", request)
        assert result.success is False
        assert result.error_message is not None


class TestJavaScriptParseStatements:
    """Tests for parse_export_statement edge cases."""

    def test_parse_export_default_no_name(self, extractor):
        """Cover line 1131: export default without specific name"""
        result = extractor._parse_export_statement("export default function() {}")
        assert result is not None
        assert result[2] is True  # is_default

    def test_parse_export_direct_unknown(self, extractor):
        """Cover lines 1152-1153: direct export without matching pattern"""
        result = extractor._parse_export_statement("export something_else")
        assert result is not None
        assert result[0] == "direct"
        assert result[1] == ["unknown"]

    def test_parse_import_statement_none(self, extractor):
        """Cover line 1114: no source match in import"""
        result = extractor._parse_import_statement("import something")
        assert result is None
