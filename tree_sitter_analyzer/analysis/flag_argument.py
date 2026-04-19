"""Flag Argument Detector.

Detects boolean parameters (flag arguments) that indicate SRP violations.
Boolean parameters mean the function does more than one thing.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


def _txt(node: tree_sitter.Node) -> str:
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go"}

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_FLAG_ARGUMENT = "flag_argument"

_SUGGESTION = (
    "Split this function into two separate functions instead of using a "
    "boolean parameter to control behavior"
)


def _is_boolean_type(type_node: tree_sitter.Node) -> bool:
    """Check if a type annotation node represents boolean."""
    text = _txt(type_node).strip().lstrip(":").strip()
    if text == "boolean":
        return True
    for child in type_node.children:
        child_text = _txt(child).strip()
        if child_text == "boolean":
            return True
        if child.type == "predefined_type":
            if _txt(child).strip() == "boolean":
                return True
    return False


_FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".jsx": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".ts": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".tsx": frozenset({
        "function_declaration", "method_definition",
        "arrow_function", "function_expression",
    }),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"function_declaration", "method_declaration"}),
}


@dataclass(frozen=True)
class FlagArgumentIssue:
    issue_type: str
    line: int
    message: str
    severity: str
    param_name: str
    suggestion: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "param_name": self.param_name,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class FlagArgumentResult:
    issues: tuple[FlagArgumentIssue, ...]
    functions_analyzed: int
    total_issues: int
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "functions_analyzed": self.functions_analyzed,
            "total_issues": self.total_issues,
            "issues": [i.to_dict() for i in self.issues],
        }


class FlagArgumentAnalyzer(BaseAnalyzer):
    """Detects boolean parameters (flag arguments) in function definitions."""

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    def __init__(self) -> None:
        super().__init__()

    def analyze_file(self, file_path: str) -> FlagArgumentResult:
        path = Path(file_path)
        ext = path.suffix
        if ext not in SUPPORTED_EXTENSIONS:
            return FlagArgumentResult(
                issues=(), functions_analyzed=0,
                total_issues=0, file_path=file_path,
            )

        source = path.read_bytes()
        _, parser = self._get_parser(ext)
        if parser is None:
            return FlagArgumentResult(
                issues=(), functions_analyzed=0,
                total_issues=0, file_path=file_path,
            )
        tree = parser.parse(source)
        root = tree.root_node

        issues: list[FlagArgumentIssue] = []
        functions_analyzed = 0
        func_types = _FUNCTION_NODE_TYPES.get(ext, frozenset())

        def _walk(n: tree_sitter.Node) -> None:
            nonlocal functions_analyzed
            if n.type in func_types:
                functions_analyzed += 1
                issues.extend(self._check_function(n, ext))
            for child in n.children:
                _walk(child)

        _walk(root)

        return FlagArgumentResult(
            issues=tuple(issues),
            functions_analyzed=functions_analyzed,
            total_issues=len(issues),
            file_path=file_path,
        )

    def _check_function(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> list[FlagArgumentIssue]:
        params_node = self._find_params_node(func_node, ext)
        if params_node is None:
            return []
        return self._scan_params(params_node, ext, func_node)

    def _find_params_node(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> tree_sitter.Node | None:
        for child in func_node.children:
            if ext == ".py" and child.type == "parameters":
                return child
            if ext in {".js", ".jsx", ".ts", ".tsx"} and child.type == "formal_parameters":
                return child
            if ext == ".java" and child.type == "formal_parameters":
                return child
            if ext == ".go" and child.type == "parameter_list":
                return child
        return None

    def _scan_params(
        self, params_node: tree_sitter.Node, ext: str,
        func_node: tree_sitter.Node,
    ) -> list[FlagArgumentIssue]:
        issues: list[FlagArgumentIssue] = []
        func_name = self._get_func_name(func_node, ext)

        for child in params_node.children:
            name_and_flag = self._is_boolean_param(child, ext)
            if name_and_flag is not None:
                name, severity = name_and_flag
                issues.append(FlagArgumentIssue(
                    issue_type=ISSUE_FLAG_ARGUMENT,
                    line=child.start_point[0] + 1,
                    message=(
                        f"Boolean parameter '{name}' in function "
                        f"'{func_name}' indicates SRP violation"
                    ),
                    severity=severity,
                    param_name=name,
                    suggestion=_SUGGESTION,
                ))
        return issues

    def _get_func_name(
        self, func_node: tree_sitter.Node, ext: str,
    ) -> str:
        for child in func_node.children:
            if child.type in {"identifier", "property_identifier"}:
                return _txt(child)
        return "<anonymous>"

    def _is_boolean_param(
        self, param_node: tree_sitter.Node, ext: str,
    ) -> tuple[str, str] | None:
        if ext == ".py":
            return self._check_python_param(param_node)
        if ext in {".js", ".jsx"}:
            return self._check_js_param(param_node)
        if ext in {".ts", ".tsx"}:
            return self._check_ts_param(param_node)
        if ext == ".java":
            return self._check_java_param(param_node)
        if ext == ".go":
            return self._check_go_param(param_node)
        return None

    def _check_python_param(
        self, node: tree_sitter.Node,
    ) -> tuple[str, str] | None:
        if node.type == "typed_parameter":
            name = self._get_identifier(node)
            type_node = node.child_by_field_name("type")
            if type_node and _txt(type_node).strip() == "bool":
                return name, SEVERITY_MEDIUM
        if node.type == "default_parameter":
            name = self._get_identifier(node)
            for child in node.children:
                if child.type in ("true", "false"):
                    return name, SEVERITY_MEDIUM
        if node.type == "typed_default_parameter":
            name = self._get_identifier(node)
            type_node = node.child_by_field_name("type")
            if type_node and _txt(type_node).strip() == "bool":
                return name, SEVERITY_MEDIUM
        return None

    def _check_js_param(
        self, node: tree_sitter.Node,
    ) -> tuple[str, str] | None:
        if node.type == "assignment_pattern":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right and right.type in ("true", "false"):
                return _txt(left).strip(), SEVERITY_LOW
        return None

    def _check_ts_param(
        self, node: tree_sitter.Node,
    ) -> tuple[str, str] | None:
        if node.type in ("required_parameter", "optional_parameter"):
            name = self._get_identifier(node)
            type_ann = node.child_by_field_name("type")
            if type_ann and _is_boolean_type(type_ann):
                return name, SEVERITY_MEDIUM
        if node.type == "assignment_pattern":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right and right.type in ("true", "false"):
                name = self._get_ts_param_name(left)
                return name, SEVERITY_LOW
        return None

    def _get_ts_param_name(self, node: tree_sitter.Node) -> str:
        if node.type in ("required_parameter", "optional_parameter"):
            ident = self._get_identifier(node)
            return ident
        return _txt(node).strip()

    def _check_java_param(
        self, node: tree_sitter.Node,
    ) -> tuple[str, str] | None:
        if node.type == "formal_parameter":
            has_bool = False
            name = ""
            for child in node.children:
                if child.type == "boolean_type":
                    has_bool = True
                if child.type == "identifier":
                    name = _txt(child).strip()
            if has_bool and name:
                return name, SEVERITY_MEDIUM
        return None

    def _check_go_param(
        self, node: tree_sitter.Node,
    ) -> tuple[str, str] | None:
        if node.type == "parameter_declaration":
            name = ""
            is_bool = False
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child).strip()
                if child.type == "type_identifier" and _txt(child).strip() == "bool":
                    is_bool = True
            if is_bool and name:
                return name, SEVERITY_MEDIUM
        return None

    def _get_identifier(self, node: tree_sitter.Node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return _txt(child).strip()
        return _txt(node).strip()
