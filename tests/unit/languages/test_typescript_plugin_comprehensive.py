#!/usr/bin/env python3
"""
Comprehensive tests for TypeScript plugin to improve coverage.

This module provides extensive test coverage for TypeScriptElementExtractor
and TypeScriptPlugin classes, focusing on untested methods and edge cases.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.languages.typescript_plugin import (
    TypeScriptElementExtractor,
    TypeScriptPlugin,
)


class TestTypeScriptElementExtractorComprehensive:
    """Comprehensive tests for TypeScriptElementExtractor"""

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        """Create a TypeScriptElementExtractor instance for testing"""
        return TypeScriptElementExtractor()

    @pytest.fixture
    def mock_node(self) -> Mock:
        """Create a mock tree-sitter node"""
        node = Mock()
        node.type = "function_declaration"
        node.start_point = (0, 0)
        node.end_point = (5, 0)
        node.start_byte = 0
        node.end_byte = 100
        node.children = []
        node.parent = None
        node.text = b"function test() {}"
        return node

    def test_get_node_text_optimized_cached(self, extractor, mock_node):
        """Test node text extraction with caching"""
        extractor.content_lines = ["function test() {", "  return 42;", "}"]
        extractor._file_encoding = "utf-8"

        # First call should cache the result
        text1 = extractor._get_node_text_optimized(mock_node)
        assert text1 is not None

        # Second call should use cache
        text2 = extractor._get_node_text_optimized(mock_node)
        assert text1 == text2
        # Cache uses (start_byte, end_byte) tuple as key
        assert (mock_node.start_byte, mock_node.end_byte) in extractor._node_text_cache

    def test_get_node_text_optimized_fallback(self, extractor, mock_node):
        """Test node text extraction fallback mechanism"""
        extractor.content_lines = ["function test() {", "  return 42;", "}"]

        # Mock encoding error to trigger fallback
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice",
            side_effect=Exception("Encoding error"),
        ):
            text = extractor._get_node_text_optimized(mock_node)
            assert text is not None

    def test_get_node_text_optimized_error_handling(self, extractor, mock_node):
        """Test node text extraction error handling"""
        extractor.content_lines = []

        # Mock both primary and fallback methods to fail
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice",
            side_effect=Exception("Primary error"),
        ):
            mock_node.start_point = (10, 0)  # Out of bounds
            mock_node.end_point = (15, 0)
            text = extractor._get_node_text_optimized(mock_node)
            assert text == ""

    def test_parse_function_signature_optimized(self, extractor):
        """Test function signature parsing"""
        mock_node = Mock()
        mock_node.children = []

        # Mock identifier child
        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"testFunction"

        # Mock parameters child
        params = Mock()
        params.type = "formal_parameters"

        # Mock type annotation child
        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        # Mock type parameters child
        type_params = Mock()
        type_params.type = "type_parameters"

        mock_node.children = [identifier, params, type_annotation, type_params]
        mock_node.type = "function_declaration"

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "async function testFunction<T>()",
                type_annotation: ": Promise<T>",
            }.get(n, "")
        )

        extractor._extract_parameters_with_types = Mock(return_value=["param1: string"])
        extractor._extract_generics = Mock(return_value=["T"])

        result = extractor._parse_function_signature_optimized(mock_node)

        assert result is not None
        name, parameters, is_async, is_generator, return_type, generics = result
        assert name == "testFunction"
        assert parameters == ["param1: string"]
        assert is_async is True
        assert is_generator is False
        assert return_type == "Promise<T>"
        assert generics == ["T"]

    def test_parse_function_signature_optimized_generator(self, extractor):
        """Test generator function signature parsing"""
        mock_node = Mock()
        mock_node.type = "generator_function_declaration"
        mock_node.children = []

        extractor._get_node_text_optimized = Mock(return_value="function* generator()")

        result = extractor._parse_function_signature_optimized(mock_node)
        assert result is not None
        _, _, is_async, is_generator, _, _ = result
        assert is_generator is True

    def test_parse_method_signature_optimized(self, extractor):
        """Test method signature parsing"""
        mock_node = Mock()
        mock_node.children = []

        # Mock property identifier
        prop_id = Mock()
        prop_id.type = "property_identifier"
        prop_id.text = b"methodName"

        # Mock parameters
        params = Mock()
        params.type = "formal_parameters"

        # Mock type annotation
        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        mock_node.children = [prop_id, params, type_annotation]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "public static async methodName()",
                type_annotation: ": Promise<void>",
            }.get(n, "")
        )

        extractor._extract_parameters_with_types = Mock(return_value=["param: string"])
        extractor._extract_generics = Mock(return_value=[])

        result = extractor._parse_method_signature_optimized(mock_node)

        assert result is not None
        (
            name,
            parameters,
            is_async,
            is_static,
            is_getter,
            is_setter,
            is_constructor,
            return_type,
            visibility,
            generics,
        ) = result

        assert name == "methodName"
        assert parameters == ["param: string"]
        assert is_async is True
        assert is_static is True
        assert visibility == "public"
        assert return_type == "Promise<void>"

    def test_parse_method_signature_optimized_constructor(self, extractor):
        """Test constructor method signature parsing"""
        mock_node = Mock()
        mock_node.children = []

        extractor._get_node_text_optimized = Mock(
            return_value="constructor(name: string)"
        )

        result = extractor._parse_method_signature_optimized(mock_node)
        assert result is not None
        (_, _, _, _, _, _, is_constructor, _, _, _) = result
        assert is_constructor is True

    def test_parse_method_signature_optimized_getter_setter(self, extractor):
        """Test getter/setter method signature parsing"""
        mock_node = Mock()
        mock_node.children = []

        # Test getter
        extractor._get_node_text_optimized = Mock(return_value="get value()")
        result = extractor._parse_method_signature_optimized(mock_node)
        assert result is not None
        (_, _, _, _, is_getter, is_setter, _, _, _, _) = result
        assert is_getter is True
        assert is_setter is False

        # Test setter
        extractor._get_node_text_optimized = Mock(return_value="set value(val: string)")
        result = extractor._parse_method_signature_optimized(mock_node)
        assert result is not None
        (_, _, _, _, is_getter, is_setter, _, _, _, _) = result
        assert is_getter is False
        assert is_setter is True

    def test_extract_parameters_with_types(self, extractor):
        """Test parameter extraction with types"""
        mock_params_node = Mock()

        # Mock parameter children
        param1 = Mock()
        param1.type = "required_parameter"
        param1.children = []

        param1_id = Mock()
        param1_id.type = "identifier"
        param1_id.text = b"param1"

        param1_type = Mock()
        param1_type.type = "type_annotation"

        param1.children = [param1_id, param1_type]

        param2 = Mock()
        param2.type = "optional_parameter"
        param2.children = []

        param2_id = Mock()
        param2_id.type = "identifier"
        param2_id.text = b"param2"

        param2.children = [param2_id]

        mock_params_node.children = [param1, param2]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                param1_type: ": string",
                param1: "param1: string",
                param2: "param2?",
            }.get(n, "")
        )

        result = extractor._extract_parameters_with_types(mock_params_node)

        assert len(result) == 2
        assert "param1: string" in result
        assert "param2?" in result

    def test_extract_generics(self, extractor):
        """Test generic type parameter extraction"""
        mock_type_params = Mock()

        # Mock type parameter children
        type_param1 = Mock()
        type_param1.type = "type_parameter"

        type_param2 = Mock()
        type_param2.type = "type_parameter"

        mock_type_params.children = [type_param1, type_param2]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                type_param1: "T",
                type_param2: "U extends string",
            }.get(n, "")
        )

        result = extractor._extract_generics(mock_type_params)

        assert len(result) == 2
        assert "T" in result
        assert "U extends string" in result

    def test_extract_import_info_simple(self, extractor):
        """Test simple import extraction"""
        mock_import_node = Mock()
        mock_import_node.type = "import_statement"
        mock_import_node.start_point = (0, 0)
        mock_import_node.end_point = (0, 30)
        mock_import_node.children = []

        # Mock import clause
        import_clause = Mock()
        import_clause.type = "import_clause"

        # Mock string literal (source)
        string_literal = Mock()
        string_literal.type = "string"
        string_literal.text = b"'./module'"

        mock_import_node.children = [import_clause, string_literal]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_import_node: "import { Component } from './module'",
                import_clause: "{ Component }",
            }.get(n, "")
        )

        extractor._extract_import_names = Mock(return_value=["Component"])

        result = extractor._extract_import_info_simple(mock_import_node)

        assert result is not None
        assert result.module_name == "./module"
        assert result.imported_names == ["Component"]
        assert result.language == "typescript"

    def test_extract_import_info_simple_type_import(self, extractor):
        """Test type-only import extraction"""
        mock_import_node = Mock()
        mock_import_node.type = "import_statement"
        mock_import_node.start_point = (0, 0)
        mock_import_node.end_point = (0, 35)
        mock_import_node.children = []
        mock_import_node.text = "import type { User } from './types'"

        extractor._get_node_text_optimized = Mock(
            return_value="import type { User } from './types'"
        )
        extractor._extract_import_names = Mock(return_value=["User"])

        # Mock import clause
        import_clause = Mock()
        import_clause.type = "import_clause"

        # Mock string literal
        string_literal = Mock()
        string_literal.type = "string"
        string_literal.text = b"'./types'"

        mock_import_node.children = [import_clause, string_literal]

        result = extractor._extract_import_info_simple(mock_import_node)

        assert result is not None
        assert result.module_name == "./types"
        assert result.imported_names == ["User"]
        # Note: is_type_import is not available in the Import model
        assert "type" in result.raw_text  # Check if type import is detected in raw text

    def test_extract_import_names(self, extractor):
        """Test import names extraction"""
        # Test named imports
        mock_clause = Mock()
        mock_clause.type = "import_clause"

        named_imports = Mock()
        named_imports.type = "named_imports"

        import_spec1 = Mock()
        import_spec1.type = "import_specifier"

        import_spec2 = Mock()
        import_spec2.type = "import_specifier"

        named_imports.children = [import_spec1, import_spec2]
        mock_clause.children = [named_imports]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                import_spec1: "Component",
                import_spec2: "useState as state",
            }.get(n, "")
        )

        result = extractor._extract_import_names(
            mock_clause, "import { Component, useState as state } from 'react'"
        )

        assert len(result) == 2
        assert "Component" in result
        assert "useState as state" in result

    def test_extract_import_names_default(self, extractor):
        """Test default import names extraction"""
        mock_clause = Mock()
        mock_clause.type = "import_clause"

        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"React"

        mock_clause.children = [identifier]

        result = extractor._extract_import_names(
            mock_clause, "import React from 'react'"
        )

        assert len(result) == 1
        assert "React" in result

    def test_extract_import_names_namespace(self, extractor):
        """Test namespace import names extraction"""
        mock_clause = Mock()
        mock_clause.type = "import_clause"

        namespace_import = Mock()
        namespace_import.type = "namespace_import"

        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"Utils"

        namespace_import.children = [Mock(), identifier]  # First child is 'as' keyword
        mock_clause.children = [namespace_import]

        result = extractor._extract_import_names(
            mock_clause, "import * as Utils from './utils'"
        )

        assert len(result) == 1
        assert "* as Utils" in result

    def test_extract_dynamic_import(self, extractor):
        """Test dynamic import extraction"""
        mock_expr_stmt = Mock()
        mock_expr_stmt.type = "expression_statement"
        mock_expr_stmt.start_point = (10, 0)
        mock_expr_stmt.end_point = (10, 30)

        # Mock call expression
        call_expr = Mock()
        call_expr.type = "call_expression"

        # Mock import identifier
        import_id = Mock()
        import_id.type = "import"

        # Mock arguments
        arguments = Mock()
        arguments.type = "arguments"

        string_literal = Mock()
        string_literal.type = "string"
        string_literal.text = b"'./dynamic-module'"

        arguments.children = [string_literal]
        call_expr.children = [import_id, arguments]
        mock_expr_stmt.children = [call_expr]

        extractor._get_node_text_optimized = Mock(
            return_value="import('./dynamic-module')"
        )

        result = extractor._extract_dynamic_import(mock_expr_stmt)

        assert result is not None
        assert result.module_name == "./dynamic-module"
        assert result.module_path == "./dynamic-module"
        assert "dynamic_import" in result.imported_names

    def test_extract_commonjs_requires(self, extractor):
        """Test CommonJS require extraction"""
        mock_tree = Mock()
        mock_root = Mock()

        # Mock variable declaration with require
        var_decl = Mock()
        var_decl.type = "variable_declaration"

        var_declarator = Mock()
        var_declarator.type = "variable_declarator"

        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"fs"

        call_expr = Mock()
        call_expr.type = "call_expression"

        require_id = Mock()
        require_id.type = "identifier"
        require_id.text = b"require"

        arguments = Mock()
        arguments.type = "arguments"

        string_literal = Mock()
        string_literal.type = "string"
        string_literal.text = b"'fs'"

        arguments.children = [string_literal]
        call_expr.children = [require_id, arguments]
        var_declarator.children = [identifier, call_expr]
        var_decl.children = [var_declarator]
        mock_root.children = [var_decl]
        mock_tree.root_node = mock_root

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                var_decl: "const fs = require('fs')",
                call_expr: "require('fs')",
            }.get(n, "")
        )

        result = extractor._extract_commonjs_requires(
            mock_tree, "const fs = require('fs')"
        )

        assert len(result) == 1
        assert result[0].module_name == "fs"
        assert result[0].imported_names == ["fs"]

    def test_extract_tsdoc_for_line(self, extractor):
        """Test TSDoc extraction for specific line"""
        extractor.content_lines = [
            "/**",
            " * This is a TSDoc comment",
            " * @param user The user object",
            " * @returns Promise with result",
            " */",
            "function testFunction(user: User): Promise<Result> {",
            "  return Promise.resolve();",
            "}",
        ]

        result = extractor._extract_tsdoc_for_line(6)  # Line with function

        assert result is not None
        assert "This is a TSDoc comment" in result
        assert "@param user The user object" in result
        assert "@returns Promise with result" in result

    def test_extract_tsdoc_for_line_no_comment(self, extractor):
        """Test TSDoc extraction when no comment exists"""
        extractor.content_lines = ["function testFunction() {", "  return 42;", "}"]

        result = extractor._extract_tsdoc_for_line(1)
        assert result is None

    def test_extract_tsdoc_for_line_single_line_comment(self, extractor):
        """Test TSDoc extraction for single line comment"""
        extractor.content_lines = [
            "/** Single line TSDoc */",
            "function testFunction() {",
            "  return 42;",
            "}",
        ]

        result = extractor._extract_tsdoc_for_line(2)
        assert result is not None
        assert "Single line TSDoc" in result

    def test_traverse_and_extract_iterative_max_depth(self, extractor):
        """Test iterative traversal with maximum depth limit"""
        # Create deeply nested mock structure
        root = Mock()
        root.type = "program"

        # Create a chain of nested nodes
        current = root
        for _i in range(60):  # Exceed max depth of 50
            child = Mock()
            child.type = "statement_block"
            child.children = []
            current.children = [child]
            current = child

        # Add a target node at the end
        target = Mock()
        target.type = "function_declaration"
        target.children = []
        current.children = [target]

        extractors = {"function_declaration": Mock(return_value=Mock())}
        results = []

        with patch.object(extractor, "_get_node_text_optimized", return_value="test"):
            extractor._traverse_and_extract_iterative(
                root, extractors, results, "function"
            )

        # Should not extract the deeply nested function due to depth limit
        assert len(results) == 0

    def test_traverse_and_extract_iterative_caching(self, extractor):
        """Test iterative traversal with caching"""
        root = Mock()
        root.type = "program"

        func_node = Mock()
        func_node.type = "function_declaration"
        func_node.children = []

        root.children = [func_node]

        # Pre-populate cache
        node_id = id(func_node)
        cache_key = (node_id, "function")
        mock_function = Mock()
        extractor._element_cache[cache_key] = mock_function

        extractors = {"function_declaration": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(root, extractors, results, "function")

        # Should use cached result
        assert len(results) == 1
        assert results[0] == mock_function
        assert not extractors["function_declaration"].called

    def test_traverse_and_extract_iterative_list_result(self, extractor):
        """Test iterative traversal with list result from extractor"""
        root = Mock()
        root.type = "program"

        var_node = Mock()
        var_node.type = "variable_declaration"
        var_node.children = []

        root.children = [var_node]

        # Mock extractor that returns a list
        mock_variables = [Mock(), Mock()]
        extractors = {"variable_declaration": Mock(return_value=mock_variables)}
        results = []

        extractor._traverse_and_extract_iterative(root, extractors, results, "variable")

        # Should extend results with list
        assert len(results) == 2
        assert results == mock_variables


class TestTypeScriptPluginComprehensive:
    """Comprehensive tests for TypeScriptPlugin"""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        """Create a TypeScriptPlugin instance for testing"""
        return TypeScriptPlugin()

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", True
    )
    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    @pytest.mark.asyncio
    async def test_analyze_file_success(self, mock_load_language, plugin):
        """Test successful file analysis"""
        # Mock language and parser
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        # Create temporary TypeScript file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(
                """
function greet(name: string): string {
    return `Hello, ${name}!`;
}

class Person {
    constructor(public name: string) {}

    greet(): string {
        return greet(this.name);
    }
}

const person = new Person("World");
"""
            )
            temp_file = f.name

        try:
            # Mock parser and tree
            mock_parser = Mock()
            mock_tree = Mock()
            mock_root = Mock()
            mock_root.children = []
            mock_tree.root_node = mock_root

            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.return_value = mock_tree

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is True
                assert result.file_path == temp_file
                assert result.language == "typescript"

        finally:
            os.unlink(temp_file)

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", True
    )
    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    @pytest.mark.asyncio
    async def test_analyze_file_with_parsing_error(self, mock_load_language, plugin):
        """Test file analysis with parsing error"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        # Create temporary file with invalid TypeScript
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("invalid typescript syntax {{{")
            temp_file = f.name

        try:
            # Mock parser to raise exception
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser = Mock()
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.side_effect = Exception("Parsing failed")

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is False
                assert "Parsing failed" in result.error_message

        finally:
            os.unlink(temp_file)

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", True
    )
    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    @pytest.mark.asyncio
    async def test_analyze_file_with_extraction_error(self, mock_load_language, plugin):
        """Test file analysis with extraction error"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function test() {}")
            temp_file = f.name

        try:
            # Mock parser and tree
            mock_parser = Mock()
            mock_tree = Mock()
            mock_root = Mock()
            mock_root.children = []
            mock_tree.root_node = mock_root

            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.return_value = mock_tree

                # Mock extractor to raise exception
                with patch.object(plugin, "create_extractor") as mock_create_extractor:
                    mock_extractor = Mock()
                    mock_extractor.extract_functions.side_effect = Exception(
                        "Extraction failed"
                    )
                    mock_create_extractor.return_value = mock_extractor

                    request = AnalysisRequest(file_path=temp_file)
                    result = await plugin.analyze_file(temp_file, request)

                    assert result.success is False
                    assert "Extraction failed" in result.error_message

        finally:
            os.unlink(temp_file)

    def test_get_tree_sitter_language_no_tree_sitter(self, plugin):
        """Test tree-sitter language getter when tree-sitter is not available"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
            False,
        ):
            result = plugin.get_tree_sitter_language()
            assert result is None

    def test_get_tree_sitter_language_load_failure(self, plugin):
        """Test tree-sitter language getter when language loading fails"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
            True,
        ):
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.loader.load_language",
                return_value=None,
            ):
                result = plugin.get_tree_sitter_language()
                assert result is None

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", True
    )
    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    @pytest.mark.asyncio
    async def test_analyze_file_with_node_counting(self, mock_load_language, plugin):
        """Test file analysis with node counting"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function test() { return 42; }")
            temp_file = f.name

        try:
            # Create mock tree with nested nodes
            mock_parser = Mock()
            mock_tree = Mock()

            # Create a tree structure for node counting
            root = Mock()
            root.type = "program"

            func_node = Mock()
            func_node.type = "function_declaration"
            func_node.children = []

            body_node = Mock()
            body_node.type = "statement_block"
            body_node.children = []

            return_node = Mock()
            return_node.type = "return_statement"
            return_node.children = []

            body_node.children = [return_node]
            func_node.children = [body_node]
            root.children = [func_node]

            mock_tree.root_node = root

            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.tree_sitter.Parser"
            ) as mock_parser_class:
                mock_parser_class.return_value = mock_parser
                mock_parser.parse.return_value = mock_tree

                request = AnalysisRequest(file_path=temp_file)
                result = await plugin.analyze_file(temp_file, request)

                assert result.success is True
                assert hasattr(result, "node_count")

        finally:
            os.unlink(temp_file)

    def test_plugin_info_comprehensive(self, plugin):
        """Test comprehensive plugin information"""
        info = plugin.get_plugin_info()

        # Verify all expected keys are present
        expected_keys = [
            "name",
            "language",
            "extensions",
            "version",
            "supported_queries",
            "features",
        ]
        for key in expected_keys:
            assert key in info

        # Verify features list is comprehensive
        features = info["features"]
        expected_features = [
            "TypeScript syntax support",
            "Interface declarations",
            "Type aliases",
            "Enums",
            "Generics",
            "Decorators",
            "TSX/JSX support",
            "React component detection",
            "Angular component detection",
            "Vue component detection",
            "Async/await support",
            "Arrow functions",
            "Method signatures",
            "Type annotations",
            "Import/export statements",
        ]

        for feature in expected_features:
            assert feature in features
