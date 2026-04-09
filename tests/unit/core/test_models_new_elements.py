#!/usr/bin/env python3
"""
Unit Tests for New CodeElement Types (Lambda, Comprehension, Expression)

Tests instantiation, serialization, and field validation for the new element types
added for Python grammar coverage.
"""

from dataclasses import asdict

from tree_sitter_analyzer.models import (
    Comprehension,
    Expression,
    Lambda,
)


class TestLambdaModel:
    """Tests for Lambda dataclass"""

    def test_lambda_creation_minimal(self):
        """Test creating Lambda with minimal fields"""
        lambda_elem = Lambda(
            name="lambda",
            start_line=1,
            end_line=1,
        )

        assert lambda_elem.name == "lambda"
        assert lambda_elem.element_type == "lambda"
        assert lambda_elem.parameters == []
        assert lambda_elem.body_preview == ""

    def test_lambda_creation_with_parameters(self):
        """Test creating Lambda with parameters"""
        lambda_elem = Lambda(
            name="lambda",
            start_line=1,
            end_line=1,
            parameters=["x", "y"],
            body_preview="x + y",
        )

        assert lambda_elem.parameters == ["x", "y"]
        assert lambda_elem.body_preview == "x + y"

    def test_lambda_serialization(self):
        """Test Lambda can be serialized to dict"""
        lambda_elem = Lambda(
            name="add_one",
            start_line=5,
            end_line=5,
            parameters=["x"],
            body_preview="x + 1",
        )

        data = asdict(lambda_elem)

        assert data["name"] == "add_one"
        assert data["element_type"] == "lambda"
        assert data["parameters"] == ["x"]
        assert data["body_preview"] == "x + 1"
        assert data["start_line"] == 5
        assert data["end_line"] == 5

    def test_lambda_with_empty_parameters(self):
        """Test Lambda with empty parameter list"""
        lambda_elem = Lambda(
            name="lambda",
            start_line=1,
            end_line=1,
            parameters=[],
            body_preview="42",
        )

        assert lambda_elem.parameters == []
        assert lambda_elem.body_preview == "42"


class TestComprehensionModel:
    """Tests for Comprehension dataclass"""

    def test_comprehension_creation_minimal(self):
        """Test creating Comprehension with minimal fields"""
        comp = Comprehension(
            name="list_comprehension",
            start_line=1,
            end_line=1,
        )

        assert comp.name == "list_comprehension"
        assert comp.element_type == "comprehension"
        assert comp.comprehension_type == ""
        assert comp.target_variable == ""
        assert comp.iterable_preview == ""
        assert comp.has_condition is False

    def test_comprehension_list_type(self):
        """Test list comprehension"""
        comp = Comprehension(
            name="list_comprehension",
            start_line=1,
            end_line=1,
            comprehension_type="list",
            target_variable="x",
            iterable_preview="range(10)",
            has_condition=False,
        )

        assert comp.comprehension_type == "list"
        assert comp.target_variable == "x"
        assert comp.iterable_preview == "range(10)"
        assert comp.has_condition is False

    def test_comprehension_with_condition(self):
        """Test comprehension with condition"""
        comp = Comprehension(
            name="list_comprehension",
            start_line=1,
            end_line=1,
            comprehension_type="list",
            target_variable="x",
            iterable_preview="range(100)",
            has_condition=True,
        )

        assert comp.has_condition is True

    def test_comprehension_set_type(self):
        """Test set comprehension"""
        comp = Comprehension(
            name="set_comprehension",
            start_line=2,
            end_line=2,
            comprehension_type="set",
            target_variable="item",
            iterable_preview="my_list",
            has_condition=False,
        )

        assert comp.comprehension_type == "set"
        assert comp.target_variable == "item"

    def test_comprehension_dict_type(self):
        """Test dict comprehension"""
        comp = Comprehension(
            name="dict_comprehension",
            start_line=3,
            end_line=3,
            comprehension_type="dict",
            target_variable="k, v",
            iterable_preview="items",
            has_condition=True,
        )

        assert comp.comprehension_type == "dict"
        assert comp.target_variable == "k, v"

    def test_comprehension_generator_type(self):
        """Test generator expression"""
        comp = Comprehension(
            name="generator_expression",
            start_line=4,
            end_line=4,
            comprehension_type="generator",
            target_variable="n",
            iterable_preview="numbers",
            has_condition=False,
        )

        assert comp.comprehension_type == "generator"

    def test_comprehension_serialization(self):
        """Test Comprehension can be serialized to dict"""
        comp = Comprehension(
            name="filtered_list",
            start_line=10,
            end_line=10,
            comprehension_type="list",
            target_variable="x",
            iterable_preview="range(100)",
            has_condition=True,
        )

        data = asdict(comp)

        assert data["name"] == "filtered_list"
        assert data["element_type"] == "comprehension"
        assert data["comprehension_type"] == "list"
        assert data["target_variable"] == "x"
        assert data["iterable_preview"] == "range(100)"
        assert data["has_condition"] is True


class TestExpressionModel:
    """Tests for Expression dataclass"""

    def test_expression_creation_minimal(self):
        """Test creating Expression with minimal fields"""
        expr = Expression(
            name="expression",
            start_line=1,
            end_line=1,
        )

        assert expr.name == "expression"
        assert expr.element_type == "expression"
        assert expr.expression_kind == ""
        assert expr.preview == ""

    def test_expression_conditional(self):
        """Test conditional expression"""
        expr = Expression(
            name="conditional_expression",
            start_line=1,
            end_line=1,
            expression_kind="conditional",
            preview="x if condition else y",
        )

        assert expr.expression_kind == "conditional"
        assert expr.preview == "x if condition else y"

    def test_expression_subscript(self):
        """Test subscript expression"""
        expr = Expression(
            name="subscript",
            start_line=2,
            end_line=2,
            expression_kind="subscript",
            preview="my_list[0]",
        )

        assert expr.expression_kind == "subscript"
        assert expr.preview == "my_list[0]"

    def test_expression_list_literal(self):
        """Test list literal expression"""
        expr = Expression(
            name="list",
            start_line=3,
            end_line=3,
            expression_kind="list",
            preview="[1, 2, 3, 4, 5]",
        )

        assert expr.expression_kind == "list"
        assert expr.preview == "[1, 2, 3, 4, 5]"

    def test_expression_serialization(self):
        """Test Expression can be serialized to dict"""
        expr = Expression(
            name="ternary",
            start_line=15,
            end_line=15,
            expression_kind="conditional",
            preview="result if success else fallback",
        )

        data = asdict(expr)

        assert data["name"] == "ternary"
        assert data["element_type"] == "expression"
        assert data["expression_kind"] == "conditional"
        assert data["preview"] == "result if success else fallback"

    def test_expression_long_preview(self):
        """Test Expression with long preview text"""
        long_text = "a" * 100
        expr = Expression(
            name="expression",
            start_line=1,
            end_line=1,
            expression_kind="conditional",
            preview=long_text,
        )

        # Preview can be any length (truncation handled by extractor)
        assert expr.preview == long_text


class TestNewElementsIntegration:
    """Integration tests for new element types"""

    def test_all_new_types_have_element_type_field(self):
        """Test all new types have element_type field"""
        lambda_elem = Lambda(
            name="lambda",
            start_line=1,
            end_line=1,
        )
        comp = Comprehension(
            name="comprehension",
            start_line=1,
            end_line=1,
        )
        expr = Expression(
            name="expression",
            start_line=1,
            end_line=1,
        )

        assert lambda_elem.element_type == "lambda"
        assert comp.element_type == "comprehension"
        assert expr.element_type == "expression"

    def test_all_new_types_have_position_tracking(self):
        """Test all new types track position correctly"""
        lambda_elem = Lambda(
            name="lambda",
            start_line=5,
            end_line=7,
        )
        comp = Comprehension(
            name="comprehension",
            start_line=10,
            end_line=12,
        )
        expr = Expression(
            name="expression",
            start_line=15,
            end_line=15,
        )

        # Lambda position
        assert lambda_elem.start_line == 5
        assert lambda_elem.end_line == 7

        # Comprehension position
        assert comp.start_line == 10
        assert comp.end_line == 12

        # Expression position
        assert expr.start_line == 15
        assert expr.end_line == 15
