#!/usr/bin/env python3
"""
Tests for Plugin System - Fixed Version

Tests for the plugin-based architecture including plugin registry,
language plugins, and element extractors.
"""

import sys

# Add project root to path
sys.path.insert(0, ".")


import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor
from tree_sitter_analyzer.models import Function, Class


@pytest.fixture
def java_extractor():
    """Fixture to provide JavaElementExtractor instance"""
    return JavaElementExtractor()


def test_extract_method_optimized_with_valid_node(mocker, java_extractor):
    """Test method extraction with valid node using current implementation"""
    # Create a more realistic mock node structure for method_declaration
    mock_node = mocker.MagicMock()
    mock_node.type = "method_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (5, 10)
    mock_node.start_byte = 0
    mock_node.end_byte = 50

    # Mock method name identifier
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"
    mock_identifier.start_byte = 12
    mock_identifier.end_byte = 22

    # Mock return type
    mock_return_type = mocker.MagicMock()
    mock_return_type.type = "void_type"
    mock_return_type.start_byte = 7
    mock_return_type.end_byte = 11

    # Mock modifiers
    mock_modifiers = mocker.MagicMock()
    mock_modifiers.type = "modifiers"
    mock_modifiers.children = []

    # Mock formal parameters
    mock_params = mocker.MagicMock()
    mock_params.type = "formal_parameters"
    mock_params.children = []

    mock_node.children = [mock_modifiers, mock_return_type, mock_identifier, mock_params]

    # Mock the source code and content lines
    java_extractor.source_code = "public void testMethod() {}"
    java_extractor.content_lines = ["public void testMethod() {}"]

    # Mock the _get_node_text_optimized method to return expected values
    def mock_get_text(node):
        if node == mock_identifier:
            return "testMethod"
        elif node == mock_return_type:
            return "void"
        elif node == mock_modifiers:
            return "public"
        elif node == mock_params:
            return "()"
        return ""

    java_extractor._get_node_text_optimized = mock_get_text

    function = java_extractor._extract_method_optimized(mock_node)

    assert function is not None
    assert isinstance(function, Function)
    assert function.name == "testMethod"


def test_extract_class_name_with_identifier(mocker, java_extractor):
    """Test class name extraction from node with identifier using current implementation"""
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"
    mock_identifier.start_byte = 6
    mock_identifier.end_byte = 14

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_identifier]

    # Mock the _get_node_text_optimized method
    java_extractor._get_node_text_optimized = lambda node: "TestClass" if node == mock_identifier else ""

    name = java_extractor._extract_class_name(mock_node)

    assert name == "TestClass"


def test_parse_method_signature_parameters(mocker, java_extractor):
    """Test parameter extraction from method signature using current implementation"""
    # Create mock node structure for method with parameters
    mock_param_node = mocker.MagicMock()
    mock_param_node.type = "formal_parameter"

    mock_params_node = mocker.MagicMock()
    mock_params_node.type = "formal_parameters"
    mock_params_node.children = [mock_param_node]

    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "method_declaration"
    mock_node.children = [mock_identifier, mock_params_node]

    # Mock the _get_node_text_optimized method
    def mock_get_text(node):
        if node == mock_identifier:
            return "testMethod"
        elif node == mock_param_node:
            return "String param"
        elif node == mock_params_node:
            return "(String param)"
        return ""

    java_extractor._get_node_text_optimized = mock_get_text

    result = java_extractor._parse_method_signature_optimized(mock_node)

    assert result is not None
    method_name, return_type, parameters, modifiers, throws = result
    assert method_name == "testMethod"
    assert len(parameters) == 1
    assert parameters[0] == "String param"


def test_parse_method_signature_throws(mocker, java_extractor):
    """Test throws clause extraction from method signature using current implementation"""
    mock_throws_node = mocker.MagicMock()
    mock_throws_node.type = "throws"

    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "method_declaration"
    mock_node.children = [mock_identifier, mock_throws_node]

    # Mock the _get_node_text_optimized method
    def mock_get_text(node):
        if node == mock_identifier:
            return "testMethod"
        elif node == mock_throws_node:
            return "throws Exception, IOException"
        return ""

    java_extractor._get_node_text_optimized = mock_get_text

    result = java_extractor._parse_method_signature_optimized(mock_node)

    assert result is not None
    method_name, return_type, parameters, modifiers, throws = result
    assert method_name == "testMethod"
    assert len(throws) >= 1  # Should extract at least one exception
    # The current implementation uses regex to find exceptions
    assert any("Exception" in throw for throw in throws) or any("IOException" in throw for throw in throws)


def test_extract_method_with_body(mocker, java_extractor):
    """Test method extraction includes body information using current implementation"""
    # Create a mock method node with body
    mock_body_node = mocker.MagicMock()
    mock_body_node.type = "block"

    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "method_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (2, 1)
    mock_node.children = [mock_identifier, mock_body_node]

    # Mock the source code and content lines
    java_extractor.source_code = "void test() { return; }"
    java_extractor.content_lines = ["void test() { return; }"]

    # Mock the _get_node_text_optimized method
    def mock_get_text(node):
        if node == mock_identifier:
            return "test"
        elif node == mock_body_node:
            return "{ return; }"
        return ""

    java_extractor._get_node_text_optimized = mock_get_text

    function = java_extractor._extract_method_optimized(mock_node)

    assert function is not None
    assert isinstance(function, Function)
    assert function.name == "test"
    # The method should have extracted the body information in raw_text
    assert "return" in function.raw_text


def test_extract_class_with_superclass(mocker, java_extractor):
    """Test class extraction with superclass using current implementation"""
    mock_type_id = mocker.MagicMock()
    mock_type_id.type = "type_identifier"

    mock_superclass = mocker.MagicMock()
    mock_superclass.type = "superclass"
    mock_superclass.children = [mock_type_id]

    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "class_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (2, 1)
    mock_node.children = [mock_identifier, mock_superclass]

    # Mock the source code and content lines
    java_extractor.source_code = "class Test extends BaseClass {}"
    java_extractor.content_lines = ["class Test extends BaseClass {}"]

    # Mock all the helper methods to avoid infinite loops
    java_extractor._extract_modifiers_optimized = mocker.MagicMock(return_value=[])
    java_extractor._determine_visibility = mocker.MagicMock(return_value="public")
    java_extractor._find_annotations_for_line_cached = mocker.MagicMock(return_value=[])
    java_extractor._is_nested_class = mocker.MagicMock(return_value=False)
    java_extractor._find_parent_class = mocker.MagicMock(return_value=None)

    # Mock the _get_node_text_optimized method
    def mock_get_text(node):
        if node == mock_identifier:
            return "Test"
        elif node == mock_type_id:
            return "BaseClass"
        elif node == mock_superclass:
            return "extends BaseClass"
        return ""

    java_extractor._get_node_text_optimized = mock_get_text

    class_obj = java_extractor._extract_class_optimized(mock_node)

    assert class_obj is not None
    assert isinstance(class_obj, Class)
    assert class_obj.name == "Test"
    assert class_obj.superclass == "BaseClass"


def test_extract_class_with_interfaces(mocker, java_extractor):
    """Test class extraction with interfaces using current implementation"""
    mock_type_id1 = mocker.MagicMock()
    mock_type_id1.type = "type_identifier"

    mock_type_id2 = mocker.MagicMock()
    mock_type_id2.type = "type_identifier"

    mock_interfaces = mocker.MagicMock()
    mock_interfaces.type = "super_interfaces"
    mock_interfaces.children = [mock_type_id1, mock_type_id2]

    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"

    mock_node = mocker.MagicMock()
    mock_node.type = "class_declaration"
    mock_node.start_point = (0, 0)
    mock_node.end_point = (2, 1)
    mock_node.children = [mock_identifier, mock_interfaces]

    # Mock the source code and content lines
    java_extractor.source_code = "class Test implements Interface1, Interface2 {}"
    java_extractor.content_lines = ["class Test implements Interface1, Interface2 {}"]

    # Mock all the helper methods to avoid infinite loops
    java_extractor._extract_modifiers_optimized = mocker.MagicMock(return_value=[])
    java_extractor._determine_visibility = mocker.MagicMock(return_value="public")
    java_extractor._find_annotations_for_line_cached = mocker.MagicMock(return_value=[])
    java_extractor._is_nested_class = mocker.MagicMock(return_value=False)
    java_extractor._find_parent_class = mocker.MagicMock(return_value=None)

    # Mock the _get_node_text_optimized method
    def mock_get_text(node):
        if node == mock_identifier:
            return "Test"
        elif node == mock_type_id1:
            return "Interface1"
        elif node == mock_type_id2:
            return "Interface2"
        elif node == mock_interfaces:
            return "implements Interface1, Interface2"
        return ""

    java_extractor._get_node_text_optimized = mock_get_text

    class_obj = java_extractor._extract_class_optimized(mock_node)

    assert class_obj is not None
    assert isinstance(class_obj, Class)
    assert class_obj.name == "Test"
    assert len(class_obj.interfaces) == 2
    assert "Interface1" in class_obj.interfaces
    assert "Interface2" in class_obj.interfaces
