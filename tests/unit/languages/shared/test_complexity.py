"""Tests for tree_sitter_analyzer.languages.shared.complexity."""

from __future__ import annotations

from types import SimpleNamespace

from tree_sitter_analyzer.languages.shared.complexity import (
    ComplexityResult,
    CyclomaticCounter,
    LogicalBranchCounter,
)


def _leaf(type_: str) -> SimpleNamespace:
    return SimpleNamespace(type=type_, children=[])


def _node(type_: str, children: list) -> SimpleNamespace:
    return SimpleNamespace(type=type_, children=children)


class TestComplexityResult:
    def test_default_values(self):
        r = ComplexityResult()
        assert r.cyclomatic == 1
        assert r.logical_branches == 0
        assert r.decision_count == 0

    def test_explicit_values(self):
        r = ComplexityResult(cyclomatic=5, logical_branches=3, decision_count=4)
        assert r.cyclomatic == 5
        assert r.logical_branches == 3
        assert r.decision_count == 4


class TestCyclomaticCounter:
    def test_empty_tree_returns_1(self):
        """No decision points → cyclomatic = 1 (base)."""
        counter = CyclomaticCounter({"if_statement"})
        root = _node("function_definition", [_leaf("identifier"), _leaf("block")])
        result = counter.count(root)
        assert result.cyclomatic == 1
        assert result.decision_count == 0

    def test_single_if_returns_2(self):
        """One if_statement → cyclomatic = 2."""
        counter = CyclomaticCounter({"if_statement"})
        root = _node("function_definition", [_leaf("if_statement")])
        result = counter.count(root)
        assert result.cyclomatic == 2
        assert result.decision_count == 1

    def test_three_branches_returns_4(self):
        """REQ acceptance criterion: 3 branches → cyclomatic = 4."""
        counter = CyclomaticCounter({"if_statement", "for_statement"})
        root = _node("function_definition", [
            _leaf("if_statement"),
            _leaf("for_statement"),
            _leaf("if_statement"),
        ])
        result = counter.count(root)
        assert result.cyclomatic == 4
        assert result.decision_count == 3

    def test_nested_decision_points_counted(self):
        """Decision points nested inside the function are counted."""
        counter = CyclomaticCounter({"if_statement"})
        inner_if = _leaf("if_statement")
        body = _node("block", [inner_if])
        outer_if = _node("if_statement", [body])
        root = _node("function_definition", [outer_if])
        result = counter.count(root)
        # Both outer_if and inner_if are if_statement nodes
        assert result.cyclomatic == 3
        assert result.decision_count == 2

    def test_non_matching_types_not_counted(self):
        """Nodes whose type is not in decision_node_types are ignored."""
        counter = CyclomaticCounter({"if_statement"})
        root = _node("function_definition", [_leaf("comment"), _leaf("identifier")])
        result = counter.count(root)
        assert result.cyclomatic == 1

    def test_empty_decision_types_returns_1_always(self):
        """Empty type set → base complexity of 1 regardless of tree shape."""
        counter = CyclomaticCounter(set())
        root = _node("function_definition", [_leaf("if_statement"), _leaf("for_statement")])
        result = counter.count(root)
        assert result.cyclomatic == 1

    def test_cyclomatic_equals_1_plus_decision_count(self):
        """Invariant: cyclomatic == 1 + decision_count."""
        counter = CyclomaticCounter({"if_statement", "while_statement", "for_statement"})
        root = _node("func", [
            _leaf("if_statement"),
            _node("while_statement", [_leaf("if_statement")]),
        ])
        result = counter.count(root)
        assert result.cyclomatic == 1 + result.decision_count


class TestLogicalBranchCounter:
    def test_no_operators_returns_zero_logical_branches(self):
        """No && / || → logical_branches = 0."""
        counter = LogicalBranchCounter()
        root = _node("func", [_leaf("identifier")])
        result = counter.count(root)
        assert result.logical_branches == 0

    def test_single_and_and_operator(self):
        """One '&&' leaf → logical_branches = 1."""
        counter = LogicalBranchCounter()
        root = _node("func", [_leaf("&&")])
        result = counter.count(root)
        assert result.logical_branches == 1

    def test_or_operator(self):
        counter = LogicalBranchCounter()
        root = _node("func", [_leaf("||")])
        result = counter.count(root)
        assert result.logical_branches == 1

    def test_python_and_or_keywords(self):
        """Python 'and' / 'or' tokens are counted."""
        counter = LogicalBranchCounter()
        root = _node("func", [_leaf("and"), _leaf("or")])
        result = counter.count(root)
        assert result.logical_branches == 2

    def test_boolean_operator_node_counted(self):
        """boolean_operator wrapper node (Python grammar) counts once."""
        counter = LogicalBranchCounter()
        root = _node("func", [_node("boolean_operator", [_leaf("and")])])
        result = counter.count(root)
        # boolean_operator + nested "and" = 2
        assert result.logical_branches == 2

    def test_extra_token_types(self):
        """Custom token types passed via constructor are counted."""
        counter = LogicalBranchCounter(extra_token_types={"xor"})
        root = _node("func", [_leaf("xor"), _leaf("&&")])
        result = counter.count(root)
        assert result.logical_branches == 2

    def test_cyclomatic_is_1_for_logical_counter(self):
        """LogicalBranchCounter does not touch cyclomatic."""
        counter = LogicalBranchCounter()
        root = _node("func", [_leaf("&&"), _leaf("||")])
        result = counter.count(root)
        assert result.cyclomatic == 1
