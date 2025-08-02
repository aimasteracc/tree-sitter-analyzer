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

from tree_sitter_analyzer.models import Function
from tree_sitter_analyzer.plugins.java_plugin import JavaElementExtractor


@pytest.fixture
def java_extractor():
    """Fixture to provide JavaElementExtractor instance"""
    return JavaElementExtractor()


def test_extract_detailed_method_info_with_valid_node(mocker, java_extractor):
    """Test detailed method info extraction with valid node"""
    # Mock node with proper structure
    mock_node = mocker.MagicMock()
    mock_node.start_point = (0, 0)
    mock_node.end_point = (5, 10)
    mock_node.start_byte = 0
    mock_node.end_byte = 27

    # Mock identifier child - "testMethod" is at position 12-22 in "public void testMethod() {}"
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"
    mock_identifier.start_byte = 12
    mock_identifier.end_byte = 22

    mock_node.children = [mock_identifier]

    source_code = "public void testMethod() {}"

    function = java_extractor._extract_detailed_method_info(
        mock_node, source_code, False
    )

    assert function is not None
    assert isinstance(function, Function)
    assert function.name == "testMethod"


def test_extract_name_from_node_with_identifier(mocker, java_extractor):
    """Test name extraction from node with identifier"""
    mock_identifier = mocker.MagicMock()
    mock_identifier.type = "identifier"
    # "testMethod" is at position 12-22 in "public void testMethod() {}"
    mock_identifier.start_byte = 12
    mock_identifier.end_byte = 22

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_identifier]

    source_code = "public void testMethod() {}"

    name = java_extractor._extract_name_from_node(mock_node, source_code)

    assert name == "testMethod"


def test_extract_parameters_from_node(mocker, java_extractor):
    """Test parameter extraction from method node"""
    mock_param_node = mocker.MagicMock()
    mock_param_node.type = "formal_parameter"
    # "String param" is at position 10-22 in "void test(String param) {}"
    mock_param_node.start_byte = 10
    mock_param_node.end_byte = 22

    mock_params_node = mocker.MagicMock()
    mock_params_node.type = "formal_parameters"
    mock_params_node.children = [mock_param_node]

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_params_node]

    source_code = "void test(String param) {}"

    parameters = java_extractor._extract_parameters_from_node(mock_node, source_code)

    assert len(parameters) == 1
    assert parameters[0] == "String param"


def test_extract_throws_from_node(mocker, java_extractor):
    """Test throws clause extraction from method node"""
    mock_throws_node = mocker.MagicMock()
    mock_throws_node.type = "throws"
    # "throws Exception, IOException" is at position 12-42 in "void test() throws Exception, IOException {}"
    mock_throws_node.start_byte = 12
    mock_throws_node.end_byte = 42

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_throws_node]

    source_code = "void test() throws Exception, IOException {}"

    throws = java_extractor._extract_throws_from_node(mock_node, source_code)

    assert "Exception" in throws
    assert "IOException" in throws


def test_extract_method_body(mocker, java_extractor):
    """Test method body extraction"""
    mock_body_node = mocker.MagicMock()
    mock_body_node.type = "block"
    # "{ return; }" is at position 12-23 in "void test() { return; }"
    mock_body_node.start_byte = 12
    mock_body_node.end_byte = 23

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_body_node]

    source_code = "void test() { return; }"

    body = java_extractor._extract_method_body(mock_node, source_code)

    assert body == "{ return; }"


def test_extract_superclass_from_node(mocker, java_extractor):
    """Test superclass extraction from class node"""
    mock_type_id = mocker.MagicMock()
    mock_type_id.type = "type_identifier"
    # "BaseClass" is at position 19-28 in "class Test extends BaseClass {}"
    mock_type_id.start_byte = 19
    mock_type_id.end_byte = 28

    mock_superclass = mocker.MagicMock()
    mock_superclass.type = "superclass"
    mock_superclass.children = [mock_type_id]

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_superclass]

    source_code = "class Test extends BaseClass {}"

    superclass = java_extractor._extract_superclass_from_node(mock_node, source_code)

    assert superclass == "BaseClass"


def test_extract_interfaces_from_node(mocker, java_extractor):
    """Test interface extraction from class node"""
    mock_type_id1 = mocker.MagicMock()
    mock_type_id1.type = "type_identifier"
    # "Interface1" is at position 22-32 in "class Test implements Interface1, Interface2 {}"
    mock_type_id1.start_byte = 22
    mock_type_id1.end_byte = 32

    mock_type_id2 = mocker.MagicMock()
    mock_type_id2.type = "type_identifier"
    # "Interface2" is at position 34-44 in "class Test implements Interface1, Interface2 {}"
    mock_type_id2.start_byte = 34
    mock_type_id2.end_byte = 44

    mock_interfaces = mocker.MagicMock()
    mock_interfaces.type = "super_interfaces"
    mock_interfaces.children = [mock_type_id1, mock_type_id2]

    mock_node = mocker.MagicMock()
    mock_node.children = [mock_interfaces]

    source_code = "class Test implements Interface1, Interface2 {}"

    interfaces = java_extractor._extract_interfaces_from_node(mock_node, source_code)

    assert len(interfaces) == 2
    assert "Interface1" in interfaces
    assert "Interface2" in interfaces
