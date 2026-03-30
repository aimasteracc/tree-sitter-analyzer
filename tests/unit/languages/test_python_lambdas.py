#!/usr/bin/env python3
"""
Unit tests for Python lambda extraction in python_plugin.py.

Tests the _extract_lambda method with mock tree-sitter nodes.
No real parser, no tempfile, no asyncio - pure mock-based unit tests.
"""

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.languages.python_plugin import PythonElementExtractor
from tree_sitter_analyzer.models import Lambda


@pytest.fixture
def extractor() -> PythonElementExtractor:
    """Create a PythonElementExtractor instance for testing."""
    return PythonElementExtractor()


class TestLambdaExtraction:
    """Test lambda expression extraction."""

    @pytest.mark.unit
    def test_extract_simple_lambda(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of simple lambda: lambda x: x + 1"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 16)
        node.start_byte = 0
        node.end_byte = 16

        # Mock lambda_parameters child
        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        # Mock identifier parameter
        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 7
        param_id.end_byte = 8
        lambda_params.children = [param_id]

        # Mock body
        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 10
        body.end_byte = 15

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 15)] = "x + 1"
        extractor._node_text_cache[(0, 16)] = "lambda x: x + 1"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.name == "<lambda>"
        assert result.parameters == ["x"]
        assert result.body_preview == "x + 1"
        assert result.start_line == 1
        assert result.end_line == 1
        assert result.language == "python"
        assert result.element_type == "lambda"
        assert result.node_type == "lambda"

    @pytest.mark.unit
    def test_extract_lambda_multiple_parameters(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of lambda with multiple parameters: lambda x, y: x + y"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 20)
        node.start_byte = 0
        node.end_byte = 20

        # Mock lambda_parameters child with two parameters
        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param1 = MagicMock()
        param1.type = "identifier"
        param1.start_byte = 7
        param1.end_byte = 8

        param2 = MagicMock()
        param2.type = "identifier"
        param2.start_byte = 10
        param2.end_byte = 11

        lambda_params.children = [param1, MagicMock(), param2]
        lambda_params.children[1].type = ","

        # Mock body
        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 13
        body.end_byte = 18

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 11)] = "y"
        extractor._node_text_cache[(13, 18)] = "x + y"
        extractor._node_text_cache[(0, 20)] = "lambda x, y: x + y"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.parameters == ["x", "y"]
        assert result.body_preview == "x + y"
        assert result.name == "<lambda>"

    @pytest.mark.unit
    def test_extract_lambda_default_parameter(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of lambda with default parameter: lambda x, y=10: x + y"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 24)
        node.start_byte = 0
        node.end_byte = 24

        # Mock lambda_parameters child with default parameter
        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param1 = MagicMock()
        param1.type = "identifier"
        param1.start_byte = 7
        param1.end_byte = 8

        default_param = MagicMock()
        default_param.type = "default_parameter"

        param2_id = MagicMock()
        param2_id.type = "identifier"
        param2_id.start_byte = 10
        param2_id.end_byte = 11

        default_param.children = [param2_id, MagicMock(), MagicMock()]
        default_param.children[1].type = "="
        default_param.children[2].type = "integer"

        lambda_params.children = [param1, MagicMock(), default_param]
        lambda_params.children[1].type = ","

        # Mock body
        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 17
        body.end_byte = 22

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 11)] = "y"
        extractor._node_text_cache[(17, 22)] = "x + y"
        extractor._node_text_cache[(0, 24)] = "lambda x, y=10: x + y"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.parameters == ["x", "y"]
        assert result.body_preview == "x + y"

    @pytest.mark.unit
    def test_extract_nested_lambda(self, extractor: PythonElementExtractor) -> None:
        """Test extraction of nested lambda: lambda x: (lambda y: x + y)"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 30)
        node.start_byte = 0
        node.end_byte = 30

        # Outer lambda parameters
        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param1 = MagicMock()
        param1.type = "identifier"
        param1.start_byte = 7
        param1.end_byte = 8
        lambda_params.children = [param1]

        # Body is a parenthesized expression containing inner lambda
        body = MagicMock()
        body.type = "parenthesized_expression"
        body.start_byte = 10
        body.end_byte = 29

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 29)] = "(lambda y: x + y)"
        extractor._node_text_cache[(0, 30)] = "lambda x: (lambda y: x + y)"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.parameters == ["x"]
        assert result.body_preview == "(lambda y: x + y)"
        assert result.raw_text == "lambda x: (lambda y: x + y)"

    @pytest.mark.unit
    def test_extract_lambda_in_assignment(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of lambda in assignment: add_one = lambda x: x + 1"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 10)
        node.end_point = (0, 26)
        node.start_byte = 10
        node.end_byte = 26

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 17
        param_id.end_byte = 18
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 20
        body.end_byte = 25

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(17, 18)] = "x"
        extractor._node_text_cache[(20, 25)] = "x + 1"
        extractor._node_text_cache[(10, 26)] = "lambda x: x + 1"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.start_line == 1
        assert result.parameters == ["x"]

    @pytest.mark.unit
    def test_extract_lambda_as_argument(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of lambda as function argument: map(lambda x: x * 2, range(10))"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 4)
        node.end_point = (0, 19)
        node.start_byte = 4
        node.end_byte = 19

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 11
        param_id.end_byte = 12
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 14
        body.end_byte = 19

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(11, 12)] = "x"
        extractor._node_text_cache[(14, 19)] = "x * 2"
        extractor._node_text_cache[(4, 19)] = "lambda x: x * 2"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.body_preview == "x * 2"

    @pytest.mark.unit
    def test_extract_lambda_long_body_truncation(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test lambda with long body gets truncated to 50 chars"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 100)
        node.start_byte = 0
        node.end_byte = 100

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 7
        param_id.end_byte = 8
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 10
        body.end_byte = 95

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Very long body - should be truncated to 50 chars
        long_body = "x + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 11 + 12 + 13 + 14 + 15"
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 95)] = long_body
        extractor._node_text_cache[(0, 100)] = f"lambda x: {long_body}"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert len(result.body_preview) == 50
        # safe_preview truncates to 47 chars and adds "..." to make 50
        assert result.body_preview == long_body[:47] + "..."

    @pytest.mark.unit
    def test_extract_lambda_no_parameters(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test extraction of lambda with no parameters: lambda: 42"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 11)
        node.start_byte = 0
        node.end_byte = 11

        # No lambda_parameters node
        body = MagicMock()
        body.type = "integer"
        body.start_byte = 8
        body.end_byte = 10

        node.children = [MagicMock(), MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[1].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(8, 10)] = "42"
        extractor._node_text_cache[(0, 11)] = "lambda: 42"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.parameters == []
        assert result.body_preview == "42"

    @pytest.mark.unit
    def test_extract_lambda_complex_expression(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test lambda with complex expression body"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 40)
        node.start_byte = 0
        node.end_byte = 40

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 7
        param_id.end_byte = 8
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "conditional_expression"
        body.start_byte = 10
        body.end_byte = 38

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 38)] = "x * 2 if x > 0 else x * -2"
        extractor._node_text_cache[(0, 40)] = "lambda x: x * 2 if x > 0 else x * -2"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert isinstance(result, Lambda)
        assert result.body_preview == "x * 2 if x > 0 else x * -2"

    @pytest.mark.unit
    def test_extract_lambda_no_body(self, extractor: PythonElementExtractor) -> None:
        """Test lambda extraction fails when body is missing"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.start_byte = 0
        node.end_byte = 10

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"
        lambda_params.children = []

        # Only lambda keyword and parameters, no body
        node.children = [MagicMock(), lambda_params]
        node.children[0].type = "lambda"

        result = extractor._extract_lambda(node)

        assert result is None

    @pytest.mark.unit
    def test_extract_lambda_position_tracking(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test lambda position tracking is correct"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (5, 10)  # Line 5, column 10
        node.end_point = (5, 25)  # Same line
        node.start_byte = 50
        node.end_byte = 65

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 57
        param_id.end_byte = 58
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 60
        body.end_byte = 65

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(57, 58)] = "x"
        extractor._node_text_cache[(60, 65)] = "x + 1"
        extractor._node_text_cache[(50, 65)] = "lambda x: x + 1"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert result.start_line == 6  # tree-sitter is 0-indexed
        assert result.end_line == 6

    @pytest.mark.unit
    def test_extract_lambda_multiline(self, extractor: PythonElementExtractor) -> None:
        """Test lambda that spans multiple lines (rare but possible in expressions)"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (2, 5)  # Spans 3 lines
        node.start_byte = 0
        node.end_byte = 50

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 7
        param_id.end_byte = 8
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "parenthesized_expression"
        body.start_byte = 10
        body.end_byte = 48

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Pre-populate cache
        extractor._node_text_cache[(7, 8)] = "x"
        extractor._node_text_cache[(10, 48)] = "(\n    x + 1\n)"
        extractor._node_text_cache[(0, 50)] = "lambda x: (\n    x + 1\n)"

        result = extractor._extract_lambda(node)

        assert result is not None
        assert result.start_line == 1
        assert result.end_line == 3

    @pytest.mark.unit
    def test_extract_lambda_exception_handling(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test lambda extraction gracefully handles exceptions"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 15)

        # Force an exception by making children raise
        node.children = MagicMock()
        node.children.__iter__.side_effect = Exception("Simulated error")

        result = extractor._extract_lambda(node)

        assert result is None

    @pytest.mark.unit
    def test_extract_lambda_empty_cache(
        self, extractor: PythonElementExtractor
    ) -> None:
        """Test lambda extraction when cache is empty (returns empty strings)"""
        node = MagicMock()
        node.type = "lambda"
        node.start_point = (0, 0)
        node.end_point = (0, 16)
        node.start_byte = 0
        node.end_byte = 16

        lambda_params = MagicMock()
        lambda_params.type = "lambda_parameters"

        param_id = MagicMock()
        param_id.type = "identifier"
        param_id.start_byte = 7
        param_id.end_byte = 8
        lambda_params.children = [param_id]

        body = MagicMock()
        body.type = "binary_operator"
        body.start_byte = 10
        body.end_byte = 15

        node.children = [MagicMock(), lambda_params, MagicMock(), body]
        node.children[0].type = "lambda"
        node.children[2].type = ":"

        # Don't populate cache - _get_node_text_optimized will return empty string

        result = extractor._extract_lambda(node)

        # Should still create Lambda but with empty fields
        assert result is None or (result.body_preview == "")
