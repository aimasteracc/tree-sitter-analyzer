"""Shared types and constants for variable mutability analysis."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import tree_sitter

MUTABILITY_SHADOW = "shadow_variable"
MUTABILITY_UNUSED = "unused_assignment"
MUTABILITY_REASSIGNED_CONST = "reassigned_constant"
MUTABILITY_LOOP_MUTATION = "mutation_in_iteration"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

_SEVERITY_MAP: dict[str, str] = {
    MUTABILITY_SHADOW: SEVERITY_MEDIUM,
    MUTABILITY_UNUSED: SEVERITY_LOW,
    MUTABILITY_REASSIGNED_CONST: SEVERITY_HIGH,
    MUTABILITY_LOOP_MUTATION: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    MUTABILITY_SHADOW: "Inner scope redeclares variable from outer scope",
    MUTABILITY_UNUSED: "Variable is assigned but never used afterward",
    MUTABILITY_REASSIGNED_CONST: "UPPER_SNAKE_CASE variable is reassigned (constant violation)",
    MUTABILITY_LOOP_MUTATION: "Loop body modifies variable declared in outer scope",
}

_SUGGESTIONS: dict[str, str] = {
    MUTABILITY_SHADOW: "Rename the inner variable to avoid shadowing",
    MUTABILITY_UNUSED: "Remove the unused assignment or use the variable",
    MUTABILITY_REASSIGNED_CONST: "Use a lowercase name or avoid reassignment",
    MUTABILITY_LOOP_MUTATION: "Use a return value instead of mutating outer state",
}

_UPPER_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

_PYTHON_SCOPE_NODES = frozenset({
    "function_definition", "class_definition", "lambda",
    "list_comprehension", "set_comprehension", "dictionary_comprehension",
    "generator_expression", "for_statement", "while_statement",
    "if_statement", "with_statement", "try_statement",
})
_JS_SCOPE_NODES = frozenset({
    "function_declaration", "function_expression", "arrow_function",
    "method_definition", "for_statement", "for_in_statement",
    "for_of_statement", "while_statement", "if_statement",
    "block_statement", "catch_clause",
})
_JAVA_SCOPE_NODES = frozenset({
    "method_declaration", "constructor_declaration", "lambda_expression",
    "for_statement", "enhanced_for_statement", "while_statement",
    "if_statement", "try_statement", "catch_clause",
    "switch_statement", "synchronized_statement",
})
_GO_SCOPE_NODES = frozenset({
    "function_declaration", "method_declaration", "func_literal",
    "for_statement", "if_statement",
})


@dataclass(frozen=True)
class MutabilityIssue:
    issue_type: str
    line: int
    column: int
    variable_name: str
    severity: str
    description: str
    suggestion: str


@dataclass(frozen=True)
class MutabilityResult:
    file_path: str
    issues: tuple[MutabilityIssue, ...]
    total_issues: int
    quality_score: float
    issue_counts: dict[str, int] = field(default_factory=dict)


def _decode(node: tree_sitter.Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")


def _empty_result(file_path: str) -> MutabilityResult:
    return MutabilityResult(
        file_path=file_path,
        issues=(),
        total_issues=0,
        quality_score=100.0,
        issue_counts={},
    )


def _compute_score(issue_count: int, issues: list[MutabilityIssue]) -> float:
    if issue_count == 0:
        return 100.0
    penalty = 0.0
    for iss in issues:
        if iss.severity == SEVERITY_HIGH:
            penalty += 20.0
        elif iss.severity == SEVERITY_MEDIUM:
            penalty += 10.0
        else:
            penalty += 3.0
    return max(0.0, 100.0 - penalty)
