"""Shared cyclomatic/logical complexity counters for language plugins.

Provides:
  - CyclomaticCounter: counts decision points (if, for, while, case arms …)
  - LogicalBranchCounter: counts ``&&`` / ``||`` / ``and`` / ``or`` operators
  - ComplexityResult: combined result dataclass
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ComplexityResult:
    """Combined complexity measurement for a single function/method.

    Attributes:
        cyclomatic: McCabe cyclomatic complexity (= 1 + decision_count).
        logical_branches: Count of short-circuit logical operators
            (``&&``, ``||``, ``and``, ``or``).
        decision_count: Raw count of decision-point nodes (before adding 1).
    """

    cyclomatic: int = 1
    logical_branches: int = 0
    decision_count: int = 0


class CyclomaticCounter:
    """Count AST decision-point nodes to compute cyclomatic complexity.

    McCabe's cyclomatic complexity formula:
        M = 1 + number_of_decision_points

    This counter uses an explicit stack-based DFS to avoid RecursionError
    on deeply nested trees.

    Usage::

        counter = CyclomaticCounter(decision_node_types={"if_statement", "for_statement"})
        result = counter.count(root_node)
        assert result.cyclomatic == 1 + result.decision_count
    """

    def __init__(self, decision_node_types: set[str] | None = None) -> None:
        """Create a counter for the given set of decision-point node type names.

        Args:
            decision_node_types: A set of tree-sitter node type strings that
                each represent one decision branch (e.g. ``"if_statement"``,
                ``"for_statement"``, ``"elif_clause"``).
        """
        self._types: frozenset[str] = frozenset(decision_node_types or ())

    def count(self, root: Any) -> ComplexityResult:
        """Walk the subtree rooted at *root* and count decision-point nodes.

        Args:
            root: A tree-sitter Node (or any object with ``.type`` and
                ``.children`` attributes).

        Returns:
            A ComplexityResult where ``cyclomatic = 1 + decision_count``.
        """
        decisions = 0
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in self._types:
                decisions += 1
            for child in reversed(list(getattr(node, "children", []))):
                stack.append(child)
        return ComplexityResult(
            cyclomatic=1 + decisions,
            decision_count=decisions,
        )


# Token types (leaf nodes) that represent short-circuit logical operators.
_LOGICAL_OP_TOKENS: frozenset[str] = frozenset(
    {
        # Symbolic operators (tree-sitter emits these as bare tokens)
        "&&",
        "||",
        # Python / Ruby keyword operators (child node types)
        "and",
        "or",
        # Boolean-expression wrapper node types (some grammars wrap && / ||
        # in a boolean_operator or logical_expression container rather than
        # emitting a bare token; counting the wrapper avoids double-counting
        # in grammars that use both wrapper + bare token nodes).
        "boolean_operator",
        "logical_expression",
    }
)


class LogicalBranchCounter:
    """Count short-circuit logical operator occurrences in an AST subtree.

    Supports ``&&`` / ``||`` (C-family, JS, TypeScript, Java, Go, Rust, Kotlin)
    and ``and`` / ``or`` (Python, Ruby). Also handles wrapper node types
    ``boolean_operator`` (Python grammar) and ``logical_expression`` (Java grammar).

    Usage::

        counter = LogicalBranchCounter()
        result = counter.count(root_node)
        # result.logical_branches counts &&, ||, and, or
    """

    def __init__(
        self,
        extra_token_types: set[str] | None = None,
    ) -> None:
        """Create a counter, optionally extending the default token-type set.

        Args:
            extra_token_types: Additional node type strings to count as
                logical-branch operators (merged with the defaults).
        """
        if extra_token_types:
            self._tokens = _LOGICAL_OP_TOKENS | frozenset(extra_token_types)
        else:
            self._tokens = _LOGICAL_OP_TOKENS

    def count(self, root: Any) -> ComplexityResult:
        """Walk the subtree rooted at *root* and count logical operators.

        Args:
            root: A tree-sitter Node.

        Returns:
            A ComplexityResult where ``logical_branches`` is set and
            ``cyclomatic = 1`` (this counter does not count decision points).
        """
        branches = 0
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in self._tokens:
                branches += 1
            for child in reversed(list(getattr(node, "children", []))):
                stack.append(child)
        return ComplexityResult(logical_branches=branches)
