"""Unused Parameter Detector.

Detects function/method parameters that are never referenced in the function body:
  - unused_parameter: parameter declared but never used in the function body
  - unused_callback_param: callback-style unused param (_ prefix, err convention)
  - unused_self_param: self/cls/this parameter never used (static candidate)

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_UNUSED_PARAMETER = "unused_parameter"
ISSUE_UNUSED_CALLBACK_PARAM = "unused_callback_param"
ISSUE_UNUSED_SELF_PARAM = "unused_self_param"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_UNUSED_PARAMETER: SEVERITY_MEDIUM,
    ISSUE_UNUSED_CALLBACK_PARAM: SEVERITY_LOW,
    ISSUE_UNUSED_SELF_PARAM: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_UNUSED_PARAMETER: "Parameter is declared but never used in the function body",
    ISSUE_UNUSED_CALLBACK_PARAM: "Callback parameter with unused convention (_ prefix) is not used",
    ISSUE_UNUSED_SELF_PARAM: "self/cls/this parameter is never referenced, consider making this static",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_UNUSED_PARAMETER: "Remove the unused parameter or prefix with _ to indicate intentionally unused.",
    ISSUE_UNUSED_CALLBACK_PARAM: "Consider removing or consolidating callback parameters.",
    ISSUE_UNUSED_SELF_PARAM: "Consider making this a static method or class method.",
}

# Node types that define a function/method scope per language
_FUNCTION_SCOPES: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "function_definition",
    }),
    ".js": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".jsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".ts": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".tsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
    }),
    ".java": frozenset({
        "method_declaration", "constructor_declaration",
        "lambda_expression",
    }),
    ".go": frozenset({
        "function_declaration", "method_declaration",
        "func_literal",
    }),
}

# Sub-scopes to skip when scanning for references (nested functions etc.)
_SUB_SCOPE_CREATORS: dict[str, frozenset[str]] = {
    ".py": frozenset({
        "function_definition", "lambda", "class_definition",
        "list_comprehension", "set_comprehension",
        "dictionary_comprehension", "generator_expression",
    }),
    ".js": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".jsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".ts": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".tsx": frozenset({
        "function_declaration", "function_expression",
        "arrow_function", "method_definition",
        "class_declaration",
    }),
    ".java": frozenset({
        "method_declaration", "constructor_declaration",
        "lambda_expression", "class_declaration",
        "interface_declaration",
    }),
    ".go": frozenset({
        "function_declaration", "method_declaration",
        "func_literal",
    }),
}

# Implicitly-used self parameters per language (skip checking)
_SELF_PARAMS: dict[str, frozenset[str]] = {
    ".py": frozenset({"self", "cls"}),
    ".java": frozenset({"this"}),
}

# Conventionally-ignored parameter prefixes (report as low severity)
_IGNORED_PREFIXES = ("_",)


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def _collect_parameters(
    func_node: tree_sitter.Node,
    ext: str,
) -> list[tuple[str, int]]:
    """Extract (name, line) of all parameters from a function node."""
    params: list[tuple[str, int]] = []

    if ext == ".py":
        _collect_python_params(func_node, params)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        _collect_js_params(func_node, params)
    elif ext == ".java":
        _collect_java_params(func_node, params)
    elif ext == ".go":
        _collect_go_params(func_node, params)

    return params


def _collect_python_params(
    func_node: tree_sitter.Node,
    params: list[tuple[str, int]],
) -> None:
    """Collect parameters from Python function_definition."""
    for child in func_node.children:
        if child.type == "parameters":
            _collect_identifiers_from_params(child, params)
            break


def _collect_js_params(
    func_node: tree_sitter.Node,
    params: list[tuple[str, int]],
) -> None:
    """Collect parameters from JS/TS function nodes."""
    for child in func_node.children:
        if child.type == "formal_parameters":
            for param in child.children:
                if param.type == "identifier":
                    name = _safe_text(param)
                    if name:
                        params.append((name, param.start_point[0] + 1))
                # TS: required_parameter (x: number)
                elif param.type in ("required_parameter", "optional_parameter", "rest_parameter"):
                    for pc in param.children:
                        if pc.type == "identifier":
                            name = _safe_text(pc)
                            if name:
                                params.append((name, pc.start_point[0] + 1))
                            break
                # destructuring patterns
                elif param.type in ("object_pattern", "array_pattern"):
                    _collect_identifiers_from_params(param, params)
            break
        # Arrow functions with single unparenthesized param: x => x
        if (
            child.type == "identifier"
            and func_node.type == "arrow_function"
        ):
            # Check if this is the first named child (before =>)
            named_siblings = [c for c in func_node.children if c.is_named]
            if named_siblings and named_siblings[0].id == child.id:
                name = _safe_text(child)
                if name:
                    params.append((name, child.start_point[0] + 1))
                break


def _collect_java_params(
    func_node: tree_sitter.Node,
    params: list[tuple[str, int]],
) -> None:
    """Collect parameters from Java method/constructor."""
    for child in func_node.children:
        if child.type == "formal_parameters":
            for param in child.children:
                if param.type == "identifier":
                    name = _safe_text(param)
                    if name:
                        params.append((name, param.start_point[0] + 1))
                elif param.type == "formal_parameter":
                    for pc in param.children:
                        if pc.type == "identifier":
                            name = _safe_text(pc)
                            if name:
                                params.append((name, pc.start_point[0] + 1))
                            break
                elif param.type.endswith("_declaration") or param.type == "spread_parameter":
                    for pc in param.children:
                        if pc.type == "identifier":
                            name = _safe_text(pc)
                            if name:
                                params.append((name, pc.start_point[0] + 1))
            break


def _collect_go_params(
    func_node: tree_sitter.Node,
    params: list[tuple[str, int]],
) -> None:
    """Collect parameters from Go function/method.

    For method_declaration, the first parameter_list is the receiver.
    The second parameter_list contains the actual function parameters.
    """
    found_params = False
    for child in func_node.children:
        if child.type == "parameter_list":
            if found_params:
                # This is the actual parameter list (not receiver)
                _collect_go_param_list(child, params)
                break
            if func_node.type == "method_declaration":
                # Skip receiver parameter list, look for the next one
                found_params = True
                continue
            _collect_go_param_list(child, params)
            break


def _collect_go_param_list(
    param_list: tree_sitter.Node,
    params: list[tuple[str, int]],
) -> None:
    """Collect parameter names from a Go parameter_list node."""
    for param in param_list.children:
        if param.type == "parameter_declaration":
            for pc in param.children:
                if pc.type == "identifier":
                    name = _safe_text(pc)
                    if name:
                        params.append((name, pc.start_point[0] + 1))
        elif param.type == "variadic_parameter_declaration":
            for pc in param.children:
                if pc.type == "identifier":
                    name = _safe_text(pc)
                    if name:
                        params.append((name, pc.start_point[0] + 1))


def _collect_identifiers_from_params(
    params_node: tree_sitter.Node,
    params: list[tuple[str, int]],
) -> None:
    """Collect identifier names from a parameters/formal_parameters node."""
    for child in params_node.children:
        if child.type == "identifier":
            name = _safe_text(child)
            if name:
                params.append((name, child.start_point[0] + 1))
        elif child.type == "typed_parameter":
            for gc in child.children:
                if gc.type == "identifier":
                    name = _safe_text(gc)
                    if name:
                        params.append((name, gc.start_point[0] + 1))
                    break
        elif child.type == "default_parameter":
            for gc in child.children:
                if gc.type == "identifier":
                    name = _safe_text(gc)
                    if name:
                        params.append((name, gc.start_point[0] + 1))
                    break
        elif child.type == "typed_default_parameter":
            for gc in child.children:
                if gc.type == "identifier":
                    name = _safe_text(gc)
                    if name:
                        params.append((name, gc.start_point[0] + 1))
                    break
        elif child.type == "list_splat_pattern":
            for gc in child.children:
                if gc.type == "identifier":
                    name = _safe_text(gc)
                    if name:
                        params.append((name, gc.start_point[0] + 1))
                    break
        elif child.type == "dictionary_splat_pattern":
            for gc in child.children:
                if gc.type == "identifier":
                    name = _safe_text(gc)
                    if name:
                        params.append((name, gc.start_point[0] + 1))
                    break


def _collect_identifier_refs(
    node: tree_sitter.Node,
    sub_scopes: frozenset[str],
    refs: set[str],
) -> None:
    """Collect all identifier references in a node, skipping sub-scopes."""
    if node.type in sub_scopes:
        return
    if node.type == "identifier":
        name = _safe_text(node)
        if name:
            refs.add(name)
        return
    if node.type == "member_expression" or node.type == "field_access":
        # For member expressions like self.x, we want to count 'self' as referenced
        obj = node.child_by_field_name("object")
        if obj is not None:
            _collect_identifier_refs(obj, sub_scopes, refs)
        # Don't recurse into the property/field part for parameter checking
        return
    for child in node.children:
        _collect_identifier_refs(child, sub_scopes, refs)


def _get_body_node(func_node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Get the body/block node of a function.

    For arrow functions with expression bodies (no braces), returns the
    expression node directly.
    """
    for child in func_node.children:
        if child.type in (
            "block", "body", "statement_block",
            "compound_statement", "constructor_body",
        ):
            return child

    # Arrow functions with expression body: (x, y) => x + y
    # The body is the last named child after =>
    if func_node.type == "arrow_function":
        named_children = [c for c in func_node.children if c.is_named]
        # Last named child that isn't formal_parameters is the body
        for child in reversed(named_children):
            if child.type != "formal_parameters":
                return child

    return None


@dataclass(frozen=True)
class UnusedParameterIssue:
    line_number: int
    issue_type: str
    parameter_name: str
    severity: str
    description: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "parameter_name": self.parameter_name,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class UnusedParameterResult:
    total_functions: int
    issues: tuple[UnusedParameterIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_functions": self.total_functions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


class UnusedParameterAnalyzer(BaseAnalyzer):
    """Analyzes code for unused function parameters."""

    def analyze_file(self, file_path: Path | str) -> UnusedParameterResult:
        path = Path(file_path)
        if not path.exists():
            return UnusedParameterResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return UnusedParameterResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> UnusedParameterResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return UnusedParameterResult(
                total_functions=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        function_scopes = _FUNCTION_SCOPES.get(ext, frozenset())
        sub_scopes = _SUB_SCOPE_CREATORS.get(ext, frozenset())
        self_params = _SELF_PARAMS.get(ext, frozenset())
        issues: list[UnusedParameterIssue] = []
        total_functions = 0

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total_functions

            if node.type in function_scopes:
                total_functions += 1
                self._analyze_function(node, ext, sub_scopes, self_params, issues)

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return UnusedParameterResult(
            total_functions=total_functions,
            issues=tuple(issues),
            file_path=str(path),
        )

    def _analyze_function(
        self,
        func_node: tree_sitter.Node,
        ext: str,
        sub_scopes: frozenset[str],
        self_params: frozenset[str],
        issues: list[UnusedParameterIssue],
    ) -> None:
        """Analyze a single function for unused parameters."""
        params = _collect_parameters(func_node, ext)
        if not params:
            return

        body = _get_body_node(func_node)
        if body is None:
            return

        refs: set[str] = set()
        _collect_identifier_refs(body, sub_scopes, refs)

        for param_name, line in params:
            if param_name in refs:
                continue

            if param_name in self_params:
                issues.append(UnusedParameterIssue(
                    line_number=line,
                    issue_type=ISSUE_UNUSED_SELF_PARAM,
                    parameter_name=param_name,
                    severity=_SEVERITY_MAP[ISSUE_UNUSED_SELF_PARAM],
                    description=_DESCRIPTIONS[ISSUE_UNUSED_SELF_PARAM],
                ))
                continue

            if param_name.startswith(_IGNORED_PREFIXES):
                issues.append(UnusedParameterIssue(
                    line_number=line,
                    issue_type=ISSUE_UNUSED_CALLBACK_PARAM,
                    parameter_name=param_name,
                    severity=_SEVERITY_MAP[ISSUE_UNUSED_CALLBACK_PARAM],
                    description=_DESCRIPTIONS[ISSUE_UNUSED_CALLBACK_PARAM],
                ))
                continue

            issues.append(UnusedParameterIssue(
                line_number=line,
                issue_type=ISSUE_UNUSED_PARAMETER,
                parameter_name=param_name,
                severity=_SEVERITY_MAP[ISSUE_UNUSED_PARAMETER],
                description=_DESCRIPTIONS[ISSUE_UNUSED_PARAMETER],
            ))
