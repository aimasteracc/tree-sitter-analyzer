#!/usr/bin/env python3
"""
Edge case tests for TypeScript plugin to maximize coverage.

This module tests edge cases, error conditions, and complex scenarios
for TypeScriptElementExtractor and TypeScriptPlugin classes.
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


class TestTypeScriptElementExtractorEdgeCases:
    """Edge case tests for TypeScriptElementExtractor"""

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        """Create a TypeScriptElementExtractor instance for testing"""
        return TypeScriptElementExtractor()

    def test_extract_function_optimized_error_handling(self, extractor):
        """Test function extraction with error handling"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Mock _parse_function_signature_optimized to return None
        extractor._parse_function_signature_optimized = Mock(return_value=None)

        result = extractor._extract_function_optimized(mock_node)
        assert result is None

    def test_extract_function_optimized_exception(self, extractor):
        """Test function extraction with exception"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Mock to raise exception - use AttributeError which is caught
        extractor._parse_function_signature_optimized = Mock(
            side_effect=AttributeError("Test error")
        )

        result = extractor._extract_function_optimized(mock_node)
        assert result is None

    def test_extract_arrow_function_optimized_with_parent(self, extractor):
        """Test arrow function extraction with variable declarator parent"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        # Mock parent variable declarator
        parent = Mock()
        parent.type = "variable_declarator"

        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"myArrowFunc"

        parent.children = [identifier]
        mock_node.parent = parent

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "() => 42",
                identifier: "myArrowFunc",
            }.get(n, "")
        )

        extractor._extract_parameters_with_types = Mock(return_value=[])
        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._calculate_complexity_optimized = Mock(return_value=1)
        extractor.content_lines = ["const myArrowFunc = () => 42;"]

        result = extractor._extract_arrow_function_optimized(mock_node)

        assert result is not None
        assert result.name == "myArrowFunc"
        assert result.is_arrow is True

    def test_extract_arrow_function_optimized_single_param(self, extractor):
        """Test arrow function extraction with single parameter"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.parent = None

        # Mock single parameter (identifier without parentheses)
        param_node = Mock()
        param_node.type = "identifier"

        mock_node.children = [param_node]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {mock_node: "x => x * 2", param_node: "x"}.get(n, "")
        )

        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._calculate_complexity_optimized = Mock(return_value=1)

        result = extractor._extract_arrow_function_optimized(mock_node)

        assert result is not None
        assert result.parameters == ["x"]

    def test_extract_arrow_function_optimized_with_type_annotation(self, extractor):
        """Test arrow function extraction with return type annotation"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.parent = None
        mock_node.children = []

        # Mock type annotation
        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        mock_node.children = [type_annotation]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "(): string => 'hello'",
                type_annotation: ": string",
            }.get(n, "")
        )

        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._calculate_complexity_optimized = Mock(return_value=1)

        result = extractor._extract_arrow_function_optimized(mock_node)

        assert result is not None
        assert result.return_type == "string"

    def test_extract_method_optimized_error_handling(self, extractor):
        """Test method extraction with error handling"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Mock _parse_method_signature_optimized to return None
        extractor._parse_method_signature_optimized = Mock(return_value=None)

        result = extractor._extract_method_optimized(mock_node)
        assert result is None

    def test_extract_class_optimized_no_name(self, extractor):
        """Test class extraction with no name"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.children = []  # No type_identifier child

        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_extract_class_optimized_with_heritage(self, extractor):
        """Test class extraction with inheritance and interfaces"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)

        # Mock type identifier
        type_id = Mock()
        type_id.type = "type_identifier"
        type_id.text = b"MyClass"

        # Mock class heritage
        heritage = Mock()
        heritage.type = "class_heritage"

        # Mock type parameters
        type_params = Mock()
        type_params.type = "type_parameters"

        mock_node.children = [type_id, heritage, type_params]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                heritage: "extends BaseClass implements IInterface1, IInterface2",
                mock_node: "class MyClass<T> extends BaseClass implements IInterface1, IInterface2 {}",
            }.get(n, "")
        )

        extractor._extract_generics = Mock(return_value=["T"])
        extractor._extract_tsdoc_for_line = Mock(return_value="Class documentation")
        extractor._is_framework_component = Mock(return_value=False)
        extractor._is_exported_class = Mock(return_value=True)

        result = extractor._extract_class_optimized(mock_node)

        assert result is not None
        assert result.name == "MyClass"
        assert result.superclass == "BaseClass"
        assert "IInterface1" in result.interfaces
        assert "IInterface2" in result.interfaces

    def test_extract_interface_optimized_with_extends(self, extractor):
        """Test interface extraction with extends clause"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Mock type identifier
        type_id = Mock()
        type_id.type = "type_identifier"
        type_id.text = b"MyInterface"

        # Mock extends clause
        extends_clause = Mock()
        extends_clause.type = "extends_clause"

        mock_node.children = [type_id, extends_clause]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                extends_clause: "extends BaseInterface, OtherInterface",
                mock_node: "interface MyInterface extends BaseInterface, OtherInterface {}",
            }.get(n, "")
        )

        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._is_exported_class = Mock(return_value=False)

        result = extractor._extract_interface_optimized(mock_node)

        assert result is not None
        assert result.name == "MyInterface"
        assert result.class_type == "interface"
        assert "BaseInterface" in result.interfaces
        assert "OtherInterface" in result.interfaces

    def test_extract_enum_optimized_no_name(self, extractor):
        """Test enum extraction with no name"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.children = []  # No identifier child

        result = extractor._extract_enum_optimized(mock_node)
        assert result is None

    def test_extract_property_optimized_with_modifiers(self, extractor):
        """Test property extraction with visibility modifiers"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)

        # Mock property identifier
        prop_id = Mock()
        prop_id.type = "property_identifier"

        # Mock type annotation
        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        # Mock string value
        string_value = Mock()
        string_value.type = "string"

        mock_node.children = [prop_id, type_annotation, string_value]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                prop_id: "myProperty",
                type_annotation: ": string",
                string_value: "'default value'",
                mock_node: "private static myProperty: string = 'default value'",
            }.get(n, "")
        )

        result = extractor._extract_property_optimized(mock_node)

        assert result is not None
        assert result.name == "myProperty"
        assert result.variable_type == "string"
        assert result.initializer == "'default value'"
        assert result.is_static is True
        assert result.visibility == "private"

    def test_extract_property_signature_optimized_optional(self, extractor):
        """Test property signature extraction with optional property"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)

        # Mock property identifier
        prop_id = Mock()
        prop_id.type = "property_identifier"

        mock_node.children = [prop_id]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                prop_id: "optionalProp",
                mock_node: "optionalProp?: string",
            }.get(n, "")
        )

        result = extractor._extract_property_signature_optimized(mock_node)

        assert result is not None
        assert result.name == "optionalProp"

    def test_parse_variable_declarator_with_arrow_function(self, extractor):
        """Test variable declarator parsing that contains arrow function"""
        mock_node = Mock()

        # Mock identifier
        identifier = Mock()
        identifier.type = "identifier"

        # Mock arrow function (should be skipped)
        arrow_func = Mock()
        arrow_func.type = "arrow_function"

        mock_node.children = [identifier, arrow_func]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {identifier: "myFunc"}.get(n, "")
        )

        result = extractor._parse_variable_declarator(mock_node, "const", 1, 1)

        # Should return None because it contains arrow function
        assert result is None

    def test_parse_variable_declarator_with_assignment(self, extractor):
        """Test variable declarator parsing with assignment operator"""
        mock_node = Mock()

        # Mock identifier
        identifier = Mock()
        identifier.type = "identifier"

        # Mock assignment operator
        assignment = Mock()
        assignment.type = "="

        # Mock value
        value_node = Mock()
        value_node.type = "number"
        assignment.next_sibling = value_node

        mock_node.children = [identifier, assignment]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                identifier: "myVar",
                value_node: "42",
                mock_node: "myVar = 42",
            }.get(n, "")
        )

        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._infer_type_from_value = Mock(return_value="number")

        result = extractor._parse_variable_declarator(mock_node, "let", 1, 1)

        assert result is not None
        assert result.name == "myVar"
        assert result.initializer == "42"

    def test_parse_function_signature_optimized_no_name(self, extractor):
        """Test function signature parsing with no name"""
        mock_node = Mock()
        mock_node.type = "function_declaration"
        mock_node.children = []  # No identifier child

        extractor._get_node_text_optimized = Mock(return_value="function() {}")

        result = extractor._parse_function_signature_optimized(mock_node)

        assert result is not None
        name, _, _, _, _, _ = result
        assert name is None

    def test_parse_method_signature_optimized_no_name(self, extractor):
        """Test method signature parsing with no name"""
        mock_node = Mock()
        mock_node.children = []  # No property_identifier child

        extractor._get_node_text_optimized = Mock(return_value="() => void")
        extractor._extract_parameters_with_types = Mock(return_value=[])
        extractor._extract_generics = Mock(return_value=[])

        result = extractor._parse_method_signature_optimized(mock_node)

        assert result is not None
        name, _, _, _, _, _, _, _, _, _ = result
        assert name is None

    def test_extract_import_info_simple_no_source(self, extractor):
        """Test import extraction with no source string"""
        mock_import_node = Mock()
        mock_import_node.type = "import_statement"
        mock_import_node.start_point = (0, 0)
        mock_import_node.end_point = (0, 20)
        mock_import_node.children = []  # No string literal child

        extractor._get_node_text_optimized = Mock(return_value="import { Component }")

        result = extractor._extract_import_info_simple(mock_import_node)
        assert result is None

    def test_extract_import_info_simple_error_handling(self, extractor):
        """Test import extraction with error handling"""
        mock_import_node = Mock()
        mock_import_node.start_point = (0, 0)
        mock_import_node.end_point = (0, 20)

        # Mock to raise exception
        extractor._get_node_text_optimized = Mock(side_effect=Exception("Test error"))

        result = extractor._extract_import_info_simple(mock_import_node)
        assert result is None

    def test_extract_dynamic_import_no_call_expression(self, extractor):
        """Test dynamic import extraction with no call expression"""
        mock_expr_stmt = Mock()
        mock_expr_stmt.type = "expression_statement"
        mock_expr_stmt.children = []  # No call_expression child

        result = extractor._extract_dynamic_import(mock_expr_stmt)
        assert result is None

    def test_extract_dynamic_import_no_import_identifier(self, extractor):
        """Test dynamic import extraction with no import identifier"""
        mock_expr_stmt = Mock()
        mock_expr_stmt.type = "expression_statement"

        # Mock call expression without import identifier
        call_expr = Mock()
        call_expr.type = "call_expression"
        call_expr.children = []  # No import identifier

        mock_expr_stmt.children = [call_expr]

        result = extractor._extract_dynamic_import(mock_expr_stmt)
        assert result is None

    def test_extract_dynamic_import_error_handling(self, extractor):
        """Test dynamic import extraction with error handling"""
        mock_expr_stmt = Mock()

        # Mock to raise exception - use AttributeError which is caught
        extractor._get_node_text_optimized = Mock(
            side_effect=AttributeError("Test error")
        )

        result = extractor._extract_dynamic_import(mock_expr_stmt)
        assert result is None

    def test_extract_commonjs_requires_error_handling(self, extractor):
        """Test CommonJS require extraction with error handling"""
        mock_tree = Mock()

        # Mock to raise exception - use AttributeError which is caught
        extractor._get_node_text_optimized = Mock(
            side_effect=AttributeError("Test error")
        )

        result = extractor._extract_commonjs_requires(
            mock_tree, "const fs = require('fs')"
        )
        assert result == []

    def test_extract_tsdoc_for_line_error_handling(self, extractor):
        """Test TSDoc extraction with error handling"""
        extractor.content_lines = ["function test() {}"]

        # Mock to raise exception
        with patch.object(
            extractor, "_clean_tsdoc", side_effect=Exception("Test error")
        ):
            result = extractor._extract_tsdoc_for_line(1)
            assert result is None

    def test_calculate_complexity_optimized_error_handling(self, extractor):
        """Test complexity calculation with error handling"""
        mock_node = Mock()

        # Mock to raise exception - use TypeError which is caught by this method
        extractor._get_node_text_optimized = Mock(side_effect=TypeError("Test error"))

        result = extractor._calculate_complexity_optimized(mock_node)
        assert result == 1  # Should return default complexity

    def test_extract_variables_from_declaration_error_handling(self, extractor):
        """Test variable extraction from declaration with error handling"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.children = []

        # Mock to raise exception
        with patch.object(
            extractor, "_parse_variable_declarator", side_effect=Exception("Test error")
        ):
            result = extractor._extract_variables_from_declaration(mock_node, "let")
            assert result == []

    def test_extract_variable_optimized_delegation(self, extractor):
        """Test variable extraction delegation to _extract_variables_from_declaration"""
        mock_node = Mock()

        with patch.object(
            extractor, "_extract_variables_from_declaration"
        ) as mock_extract:
            mock_extract.return_value = [Mock()]

            result = extractor._extract_variable_optimized(mock_node)

            mock_extract.assert_called_once_with(mock_node, "var")
            assert result == mock_extract.return_value

    def test_extract_lexical_variable_optimized_let(self, extractor):
        """Test lexical variable extraction for let"""
        mock_node = Mock()

        extractor._get_node_text_optimized = Mock(return_value="let myVar = 42")

        with patch.object(
            extractor, "_extract_variables_from_declaration"
        ) as mock_extract:
            mock_extract.return_value = [Mock()]

            extractor._extract_lexical_variable_optimized(mock_node)

            mock_extract.assert_called_once_with(mock_node, "let")

    def test_extract_lexical_variable_optimized_const(self, extractor):
        """Test lexical variable extraction for const"""
        mock_node = Mock()

        extractor._get_node_text_optimized = Mock(return_value="const myVar = 42")

        with patch.object(
            extractor, "_extract_variables_from_declaration"
        ) as mock_extract:
            mock_extract.return_value = [Mock()]

            extractor._extract_lexical_variable_optimized(mock_node)

            mock_extract.assert_called_once_with(mock_node, "const")


class TestTypeScriptPluginEdgeCases:
    """Edge case tests for TypeScriptPlugin"""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        """Create a TypeScriptPlugin instance for testing"""
        return TypeScriptPlugin()

    def test_analyze_file_encoding_error(self, plugin):
        """Test file analysis with encoding error"""
        # Create a file with invalid encoding
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".ts", delete=False) as f:
            f.write(b"\xff\xfe\x00\x00invalid utf-8")
            temp_file = f.name

        try:
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
                True,
            ):
                with patch(
                    "tree_sitter_analyzer.languages.typescript_plugin.loader.load_language",
                    return_value=Mock(),
                ):
                    request = AnalysisRequest(file_path=temp_file)

                    # This should handle encoding errors gracefully
                    import asyncio

                    result = asyncio.run(plugin.analyze_file(temp_file, request))

                    # Should fail gracefully
                    assert result.success is False

        finally:
            os.unlink(temp_file)

    def test_analyze_file_permission_error(self, plugin):
        """Test file analysis with permission error"""
        # Use a non-existent file to simulate permission error
        non_existent_file = "/root/non_existent_file.ts"

        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
            True,
        ):
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.loader.load_language",
                return_value=Mock(),
            ):
                request = AnalysisRequest(file_path=non_existent_file)

                import asyncio

                result = asyncio.run(plugin.analyze_file(non_existent_file, request))

                assert result.success is False
                assert result.error_message is not None

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", True
    )
    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    def test_analyze_file_parser_creation_error(self, mock_load_language, plugin):
        """Test file analysis with parser creation error"""
        mock_language = Mock()
        mock_load_language.return_value = mock_language

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function test() {}")
            temp_file = f.name

        try:
            # Mock Parser to raise exception
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.tree_sitter.Parser",
                side_effect=Exception("Parser error"),
            ):
                request = AnalysisRequest(file_path=temp_file)

                import asyncio

                result = asyncio.run(plugin.analyze_file(temp_file, request))

                assert result.success is False
                assert "Parser error" in result.error_message

        finally:
            os.unlink(temp_file)

    def test_get_tree_sitter_language_exception(self, plugin):
        """Test tree-sitter language getter with exception"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
            True,
        ):
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.loader.load_language",
                side_effect=ImportError("Load error"),
            ):
                result = plugin.get_tree_sitter_language()
                assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
