"""
Unit tests for PythonCallExtractor.

Tests the extraction of Python function/method calls from AST nodes.
"""

import pytest

from tree_sitter_analyzer_v2.core.parser import TreeSitterParser
from tree_sitter_analyzer_v2.graph.extractors import PythonCallExtractor


@pytest.fixture
def python_parser():
    """Create Python parser for test cases."""
    return TreeSitterParser("python")


@pytest.fixture
def python_extractor():
    """Create Python call extractor."""
    return PythonCallExtractor()


def test_get_call_node_types(python_extractor):
    """Test that Python extractor returns correct node types."""
    node_types = python_extractor.get_call_node_types()
    assert node_types == ["call"]


def test_extract_simple_function_call(python_parser, python_extractor):
    """Test extraction of simple function call: func()"""
    code = """
def main():
    helper()
"""
    parse_result = python_parser.parse(code)
    calls = python_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "helper"
    assert calls[0]["type"] == "simple"
    assert calls[0]["qualifier"] is None
    assert calls[0]["line"] == 3


def test_extract_method_call(python_parser, python_extractor):
    """Test extraction of method call: obj.method()"""
    code = """
def main():
    user.getName()
"""
    parse_result = python_parser.parse(code)
    calls = python_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "getName"
    assert calls[0]["type"] == "method"
    assert calls[0]["qualifier"] == "user"
    assert calls[0]["line"] == 3


def test_extract_module_function_call(python_parser, python_extractor):
    """Test extraction of module function call: Module.function()"""
    code = """
def main():
    math.sqrt(16)
"""
    parse_result = python_parser.parse(code)
    calls = python_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 1
    assert calls[0]["name"] == "sqrt"
    assert calls[0]["type"] == "method"  # Can't distinguish from instance method at AST level
    assert calls[0]["qualifier"] == "math"


def test_extract_multiple_calls(python_parser, python_extractor):
    """Test extraction of multiple function calls."""
    code = """
def main():
    helper()
    user.process()
    Math.max(a, b)
"""
    parse_result = python_parser.parse(code)
    calls = python_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 3

    # First call: helper()
    assert calls[0]["name"] == "helper"
    assert calls[0]["type"] == "simple"

    # Second call: user.process()
    assert calls[1]["name"] == "process"
    assert calls[1]["type"] == "method"
    assert calls[1]["qualifier"] == "user"

    # Third call: Math.max()
    assert calls[2]["name"] == "max"
    assert calls[2]["qualifier"] == "Math"


def test_extract_no_calls(python_parser, python_extractor):
    """Test extraction when there are no function calls."""
    code = """
def main():
    x = 5
    y = x + 10
"""
    parse_result = python_parser.parse(code)
    calls = python_extractor.extract_calls(parse_result.tree)

    assert len(calls) == 0


def test_extract_nested_calls(python_parser, python_extractor):
    """Test extraction of nested function calls."""
    code = """
def main():
    result = process(get_data())
"""
    parse_result = python_parser.parse(code)
    calls = python_extractor.extract_calls(parse_result.tree)

    # Should extract both process() and get_data()
    assert len(calls) == 2
    call_names = {call["name"] for call in calls}
    assert "process" in call_names
    assert "get_data" in call_names
