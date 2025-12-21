#!/usr/bin/env python3
"""
Comprehensive Tests for Enhanced JavaScript Plugin

Tests for the enhanced JavaScript plugin with comprehensive feature support
including ES6+, async/await, classes, modules, JSX, and framework-specific patterns.
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

import pytest

from tree_sitter_analyzer.languages.javascript_plugin import (
    JavaScriptElementExtractor,
    JavaScriptPlugin,
)


@pytest.fixture
def extractor():
    """Fixture to provide enhanced JavaScriptElementExtractor instance"""
    return JavaScriptElementExtractor()


@pytest.fixture
def plugin():
    """Fixture to provide enhanced JavaScriptPlugin instance"""
    return JavaScriptPlugin()


class TestEnhancedJavaScriptElementExtractor:
    """Tests for enhanced JavaScript element extractor"""

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


class TestEnhancedJavaScriptPlugin:
    """Tests for enhanced JavaScript plugin"""

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


class TestJavaScriptErrorHandling:
    """Tests for error handling in enhanced JavaScript plugin"""

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
