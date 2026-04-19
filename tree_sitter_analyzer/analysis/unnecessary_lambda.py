"""Unnecessary Lambda Detector.

Detects lambda expressions that can be replaced with a direct
function reference:

  - trivial_lambda: lambda x: f(x) → use f instead
  - identity_lambda: lambda x: x → use identity or remove

Unnecessary lambdas add noise and reduce readability when a simple
function reference would suffice.

Supports Python only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"

ISSUE_TRIVIAL_LAMBDA = "trivial_lambda"
ISSUE_IDENTITY_LAMBDA = "identity_lambda"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_TRIVIAL_LAMBDA: "Lambda just wraps a single function call with matching arguments",
    ISSUE_IDENTITY_LAMBDA: "Lambda returns its own parameter (identity function)",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_TRIVIAL_LAMBDA: "Replace the lambda with a direct function reference.",
    ISSUE_IDENTITY_LAMBDA: "Remove the lambda and use the value directly.",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace")[:80] if node.text else ""


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _get_lambda_params(node: tree_sitter.Node) -> list[str]:
    params: list[str] = []
    params_node = node.child_by_field_name("parameters")
    if params_node is None:
        return params
    for child in params_node.children:
        if child.type == "identifier":
            params.append(_node_text(child))
        elif child.type == "typed_parameter":
            for tc in child.children:
                if tc.type == "identifier":
                    params.append(_node_text(tc))
                    break
        elif child.type == "default_parameter":
            name_node = child.child_by_field_name("name")
            if name_node:
                params.append(_node_text(name_node))
    return params


def _check_trivial_lambda(
    node: tree_sitter.Node,
    params: list[str],
) -> bool:
    body = node.child_by_field_name("body")
    if body is None:
        return False
    if body.type != "call":
        return False

    func = body.child_by_field_name("function")
    if func is None or func.type != "identifier":
        return False

    args_node = body.child_by_field_name("arguments")
    if args_node is None:
        return False

    named_args = [c for c in args_node.children if c.is_named]
    if len(named_args) != len(params):
        return False

    for arg in named_args:
        if arg.type != "identifier":
            return False

    arg_names = [_node_text(a) for a in named_args]
    return arg_names == params


def _check_identity_lambda(
    node: tree_sitter.Node,
    params: list[str],
) -> bool:
    if len(params) != 1:
        return False
    body = node.child_by_field_name("body")
    if body is None:
        return False
    if body.type != "identifier":
        return False
    return _node_text(body) == params[0]


@dataclass(frozen=True)
class UnnecessaryLambdaIssue:
    line: int
    issue_type: str
    severity: str
    description: str
    suggestion: str
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class UnnecessaryLambdaResult:
    file_path: str
    total_lambdas: int
    issues: list[UnnecessaryLambdaIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_lambdas": self.total_lambdas,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class UnnecessaryLambdaAnalyzer(BaseAnalyzer):
    """Detects unnecessary lambda expressions in Python."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> UnnecessaryLambdaResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return UnnecessaryLambdaResult(
                file_path=str(path),
                total_lambdas=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return UnnecessaryLambdaResult(
                file_path=str(path),
                total_lambdas=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        issues: list[UnnecessaryLambdaIssue] = []
        total_lambdas = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "lambda" and node.child_by_field_name("body") is not None:
                total_lambdas += 1
                params = _get_lambda_params(node)
                if _check_identity_lambda(node, params):
                    issues.append(UnnecessaryLambdaIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_IDENTITY_LAMBDA,
                        severity=SEVERITY_LOW,
                        description=_DESCRIPTIONS[ISSUE_IDENTITY_LAMBDA],
                        suggestion=_SUGGESTIONS[ISSUE_IDENTITY_LAMBDA],
                        context=_txt(node),
                    ))
                elif _check_trivial_lambda(node, params):
                    issues.append(UnnecessaryLambdaIssue(
                        line=node.start_point[0] + 1,
                        issue_type=ISSUE_TRIVIAL_LAMBDA,
                        severity=SEVERITY_LOW,
                        description=_DESCRIPTIONS[ISSUE_TRIVIAL_LAMBDA],
                        suggestion=_SUGGESTIONS[ISSUE_TRIVIAL_LAMBDA],
                        context=_txt(node),
                    ))
            for child in node.children:
                stack.append(child)

        return UnnecessaryLambdaResult(
            file_path=str(path),
            total_lambdas=total_lambdas,
            issues=issues,
        )
