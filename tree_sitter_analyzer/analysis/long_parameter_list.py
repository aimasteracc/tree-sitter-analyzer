"""Long Parameter List Detector.

Detects functions/methods with too many parameters (default threshold: 5).
Classic Fowler code smell — long parameter lists suggest the function
does too much or should use a parameter object.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

ISSUE_MANY_PARAMS = "many_params"
ISSUE_EXCESSIVE_PARAMS = "excessive_params"

DEFAULT_THRESHOLD = 5
EXCESSIVE_THRESHOLD = 8

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_MANY_PARAMS: SEVERITY_MEDIUM,
    ISSUE_EXCESSIVE_PARAMS: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_MANY_PARAMS: "Function has many parameters — consider using a parameter object",
    ISSUE_EXCESSIVE_PARAMS: "Function has excessive parameters — almost certainly needs refactoring",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_MANY_PARAMS: "Group related parameters into a data class or dictionary.",
    ISSUE_EXCESSIVE_PARAMS: "This function likely has too many responsibilities. Split it or use a builder/config pattern.",
}

_PARAM_LIST_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"parameters"}),
    ".js": frozenset({"formal_parameters"}),
    ".jsx": frozenset({"formal_parameters"}),
    ".ts": frozenset({"formal_parameters"}),
    ".tsx": frozenset({"formal_parameters"}),
    ".java": frozenset({"formal_parameters"}),
    ".go": frozenset({"parameter_list"}),
}

_FUNCTION_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition", "lambda"}),
    ".js": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".jsx": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".ts": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".tsx": frozenset({"function_declaration", "arrow_function", "method_definition"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _count_parameters(param_node: tree_sitter.Node) -> int:
    named_children = [c for c in param_node.children if c.is_named]
    return len(named_children)


def _get_function_name(node: tree_sitter.Node) -> str:
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "field_identifier"):
            return _safe_text(child)
    for child in node.children_by_field_name("name"):
        return _safe_text(child)
    return "<anonymous>"


@dataclass(frozen=True)
class LongParameterIssue:
    issue_type: str
    function_name: str
    line: int
    column: int
    param_count: int
    severity: str
    description: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "function_name": self.function_name,
            "line": self.line,
            "column": self.column,
            "param_count": self.param_count,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass
class LongParameterResult:
    file_path: str
    total_functions: int
    issues: list[LongParameterIssue]
    max_params: int
    avg_params: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_functions": self.total_functions,
            "issue_count": len(self.issues),
            "max_params": self.max_params,
            "avg_params": round(self.avg_params, 2),
            "issues": [i.to_dict() for i in self.issues],
        }


class LongParameterListAnalyzer(BaseAnalyzer):
    """Detects functions with too many parameters."""

    def __init__(self, threshold: int = DEFAULT_THRESHOLD) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }
        self._threshold = threshold

    def analyze_file(
        self, file_path: str | Path,
    ) -> LongParameterResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return self._empty_result(str(path))
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return self._empty_result(str(path))

        try:
            source = path.read_bytes()
        except OSError:
            return self._empty_result(str(path))

        tree = parser.parse(source)
        if tree.root_node is None:
            return self._empty_result(str(path))

        func_types = _FUNCTION_TYPES.get(ext)
        param_types = _PARAM_LIST_TYPES.get(ext)
        if func_types is None or param_types is None:
            return self._empty_result(str(path))

        issues: list[LongParameterIssue] = []
        total_functions = 0
        max_params = 0
        total_params = 0

        for node in _walk(tree.root_node):
            if node.type not in func_types:
                continue
            total_functions += 1

            param_node = self._find_params(node, param_types)
            if param_node is None:
                continue

            count = _count_parameters(param_node)
            max_params = max(max_params, count)
            total_params += count

            if count >= self._threshold:
                issues.append(self._make_issue(node, count))

        avg = total_params / total_functions if total_functions > 0 else 0.0
        return LongParameterResult(
            file_path=str(path),
            total_functions=total_functions,
            issues=issues,
            max_params=max_params,
            avg_params=avg,
        )

    def _find_params(
        self,
        func_node: tree_sitter.Node,
        param_types: frozenset[str],
    ) -> tree_sitter.Node | None:
        last_param: tree_sitter.Node | None = None
        for child in func_node.children:
            if child.type in param_types:
                last_param = child
        return last_param

    def _make_issue(
        self,
        node: tree_sitter.Node,
        param_count: int,
    ) -> LongParameterIssue:
        if param_count >= EXCESSIVE_THRESHOLD:
            issue_type = ISSUE_EXCESSIVE_PARAMS
        else:
            issue_type = ISSUE_MANY_PARAMS

        return LongParameterIssue(
            issue_type=issue_type,
            function_name=_get_function_name(node),
            line=node.start_point[0] + 1,
            column=node.start_point[1],
            param_count=param_count,
            severity=_SEVERITY_MAP[issue_type],
            description=_DESCRIPTIONS[issue_type],
            suggestion=_SUGGESTIONS[issue_type],
        )

    def _empty_result(self, path: str) -> LongParameterResult:
        return LongParameterResult(
            file_path=path,
            total_functions=0,
            issues=[],
            max_params=0,
            avg_params=0.0,
        )


def _walk(node: tree_sitter.Node) -> Any:
    cursor = node.walk()
    reached_root = False
    while not reached_root:
        yield cursor.node
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False
