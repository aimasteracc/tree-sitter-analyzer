#!/usr/bin/env python3
"""Python AST-based mutation engine (RFC-0029).

No mutmut, no os.fork — works on Windows, macOS, and Linux.
Applies exactly one mutation from the closed set below at a given line:

1. Invert boolean condition:   ``if C:`` → ``if not C:``  (also ``while``)
2. Flip comparison operator:   ``==``↔``!=``, ``<``↔``>=``, ``>``↔``<=``
3. Negate returned boolean:    ``return True`` → ``return False`` (and vice versa)
4. Drop a keyword flag arg:    ``open(f, newline="")`` → ``open(f)``
5. Hoist a statement:          move first stmt from a ``with``/``try`` body
                               to immediately before that block

The set is deliberately small and closed.  See the false-negative profile in
the test suite for what this set does NOT detect.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

# Operator pairs for flip-comparison mutation.
_OP_FLIP: dict[type, type] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
}
_OP_SYM: dict[type, str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.GtE: ">=",
    ast.Gt: ">",
    ast.LtE: "<=",
}


@dataclass
class MutationResult:
    """A successful mutation: contains the mutated source bytes and a description."""

    mutated_bytes: bytes
    description: str
    mutation_kind: str  # class name of the mutator that applied


class _MutationTransformer(ast.NodeTransformer):
    """Base class for single-shot AST mutation transformers.

    Each transformer walks the AST looking for the first applicable mutation
    at ``target_lineno`` and sets ``self.applied = True`` once it fires.
    Callers MUST check ``self.applied`` after ``visit()`` to know if any
    mutation was made.
    """

    def __init__(self, target_lineno: int) -> None:
        self.target_lineno = target_lineno
        self.applied = False
        self.description = ""

    def _at_target(self, node: ast.AST) -> bool:
        """True when the node starts exactly at the target line."""
        return getattr(node, "lineno", None) == self.target_lineno

    def _within_target(self, node: ast.AST) -> bool:
        """True when the target line falls inside the node's span."""
        start: int | None = getattr(node, "lineno", None)
        end: int | None = getattr(node, "end_lineno", None)
        if start is None or end is None:
            return False
        return bool(start <= self.target_lineno <= end)


class _HoistMutator(_MutationTransformer):
    """Move the first statement out of a ``with``/``try`` body to before the block.

    This reproduces the "guarded region is violated" bug shape:
    a timing window, a lock, a transaction, a suppress, a temp-dir lifetime.
    """

    def _hoist(
        self,
        node: ast.AST,
        body: list[ast.stmt],
        new_node_fn: Any,
        block_type: str,
    ) -> ast.AST | list[ast.AST]:
        if self.applied or not self._within_target(node):
            return self.generic_visit(node)
        if len(body) < 2:
            # Need at least 2 statements; hoisting the only statement leaves
            # an empty body, which is a syntax error.
            return self.generic_visit(node)
        first_stmt = body[0]
        new_body = body[1:]
        new_node = new_node_fn(new_body)
        self.applied = True
        try:
            stmt_repr = ast.unparse(first_stmt)[:60]
        except Exception:  # noqa: BLE001
            stmt_repr = "<stmt>"
        self.description = (
            f"hoisted '{stmt_repr}' before '{block_type}' block at line "
            f"{getattr(node, 'lineno', '?')}"
        )
        # Return the hoisted statement followed by the mutated block.
        # Returning a list from a NodeTransformer replaces the node with
        # multiple nodes in the parent's body.
        ast.copy_location(new_node, node)
        return [first_stmt, new_node]

    def visit_With(self, node: ast.With) -> ast.AST | list[ast.AST]:
        return self._hoist(
            node,
            list(node.body),
            lambda new_body: ast.With(items=node.items, body=new_body),
            "with",
        )

    def visit_Try(self, node: ast.Try) -> ast.AST | list[ast.AST]:
        return self._hoist(
            node,
            list(node.body),
            lambda new_body: ast.Try(
                body=new_body,
                handlers=node.handlers,
                orelse=node.orelse,
                finalbody=node.finalbody,
            ),
            "try",
        )


class _InvertConditionMutator(_MutationTransformer):
    """Invert the boolean test of an ``if`` or ``while`` at the target line."""

    @staticmethod
    def _invert(test: ast.expr) -> ast.expr:
        # Unwrap double negation: ``not (not x)`` → ``x``
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return test.operand
        return ast.UnaryOp(op=ast.Not(), operand=test)

    def visit_If(self, node: ast.If) -> ast.AST:
        if not self.applied and self._at_target(node):
            new_node = ast.If(
                test=self._invert(node.test),
                body=node.body,
                orelse=node.orelse,
            )
            self.applied = True
            self.description = f"inverted if-condition at line {self.target_lineno}"
            return ast.copy_location(new_node, node)
        return self.generic_visit(node)

    def visit_While(self, node: ast.While) -> ast.AST:
        if not self.applied and self._at_target(node):
            new_node = ast.While(
                test=self._invert(node.test),
                body=node.body,
                orelse=node.orelse,
            )
            self.applied = True
            self.description = f"inverted while-condition at line {self.target_lineno}"
            return ast.copy_location(new_node, node)
        return self.generic_visit(node)


class _FlipComparisonMutator(_MutationTransformer):
    """Flip the first comparison operator in a ``Compare`` node."""

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        if not self.applied and self._at_target(node) and node.ops:
            first_op = node.ops[0]
            flipped_cls = _OP_FLIP.get(type(first_op))
            if flipped_cls is not None:
                new_ops = [flipped_cls(), *node.ops[1:]]
                new_node = ast.Compare(
                    left=node.left,
                    ops=new_ops,
                    comparators=node.comparators,
                )
                self.applied = True
                old_sym = _OP_SYM.get(type(first_op), "?")
                new_sym = _OP_SYM.get(flipped_cls, "?")
                self.description = (
                    f"flipped comparison {old_sym!r} → {new_sym!r} "
                    f"at line {self.target_lineno}"
                )
                return ast.copy_location(new_node, node)
        return self.generic_visit(node)


class _NegateBooleanReturnMutator(_MutationTransformer):
    """Replace ``return True`` with ``return False`` (and vice versa)."""

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if (
            not self.applied
            and self._at_target(node)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, bool)
        ):
            old_val: bool = node.value.value
            new_node = ast.Return(value=ast.Constant(value=not old_val))
            self.applied = True
            self.description = (
                f"negated return {old_val} → {not old_val} at line {self.target_lineno}"
            )
            return ast.copy_location(new_node, node)
        return self.generic_visit(node)


class _DropKeywordArgMutator(_MutationTransformer):
    """Remove the first flag-bearing keyword argument from a function call.

    A "flag-bearing" keyword arg is one whose value is a bool, empty string,
    or None literal — the shapes that matter for ``newline=""``,
    ``follow_symlinks=True``, etc.
    """

    @staticmethod
    def _is_flag_value(value: ast.expr) -> bool:
        return isinstance(value, ast.Constant) and isinstance(
            value.value, (bool, str, type(None))
        )

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if not self.applied and self._at_target(node):
            for i, kw in enumerate(node.keywords):
                if kw.arg is not None and self._is_flag_value(kw.value):
                    new_keywords = [*node.keywords[:i], *node.keywords[i + 1 :]]
                    new_node = ast.Call(
                        func=node.func,
                        args=node.args,
                        keywords=new_keywords,
                    )
                    self.applied = True
                    self.description = (
                        f"dropped keyword arg {kw.arg!r} at line {self.target_lineno}"
                    )
                    return ast.copy_location(new_node, node)
        return self.generic_visit(node)


# Priority order: hoist first (flagship), then condition/comparison/boolean/kwarg.
_MUTATORS: tuple[type[_MutationTransformer], ...] = (
    _HoistMutator,
    _InvertConditionMutator,
    _FlipComparisonMutator,
    _NegateBooleanReturnMutator,
    _DropKeywordArgMutator,
)


def apply_mutation(source_bytes: bytes, lineno: int) -> MutationResult | None:
    """Apply the first applicable mutation at *lineno*.

    Returns a :class:`MutationResult` on success, ``None`` when no mutation
    in the closed set applies at the given line (→ NO_INVERTIBLE_BRANCH).

    The mutated bytes are produced by ``ast.unparse()``, which reformats the
    entire module.  Comments and whitespace are lost, but the result is always
    valid Python — guaranteed by the compile() check below.
    """
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None

    try:
        ast.parse(source)  # quick validity check before mutating
    except SyntaxError:
        return None

    for mutator_cls in _MUTATORS:
        fresh_tree = ast.parse(source)
        mutator = mutator_cls(lineno)
        new_tree = mutator.visit(fresh_tree)
        if not mutator.applied:
            continue
        ast.fix_missing_locations(new_tree)
        try:
            mutated_source = ast.unparse(new_tree)
            compile(mutated_source, "<mutation>", "exec")  # verify valid
        except (SyntaxError, Exception):  # noqa: BLE001
            continue
        return MutationResult(
            mutated_bytes=mutated_source.encode("utf-8"),
            description=mutator.description,
            mutation_kind=mutator_cls.__name__,
        )
    return None
