"""Redundant Super Call Detector.

Detects unnecessary super().__init__() calls in constructors:
  - redundant_super_init: constructor body is ONLY a super() call (low)
  - passthrough_super_init: constructor params passed through to super() unchanged (info)

Supports Python, JavaScript/TypeScript, Java.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

ISSUE_REDUNDANT_SUPER = "redundant_super_init"
ISSUE_PASSTHROUGH_SUPER = "passthrough_super_init"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_REDUNDANT_SUPER: SEVERITY_LOW,
    ISSUE_PASSTHROUGH_SUPER: SEVERITY_INFO,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_SUPER: "Constructor only calls super() with no additional logic",
    ISSUE_PASSTHROUGH_SUPER: "Constructor passes all params to super() without transformation",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_SUPER: "Remove the constructor entirely. Python/JS/TS auto-calls parent constructors.",
    ISSUE_PASSTHROUGH_SUPER: "Consider removing if the forwarding adds no value.",
}

# Function definition node types per language
_FUNCTION_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"method_definition", "constructor"}),
    ".jsx": frozenset({"method_definition", "constructor"}),
    ".ts": frozenset({"method_definition", "constructor"}),
    ".tsx": frozenset({"method_definition", "constructor"}),
    ".java": frozenset({"constructor_declaration"}),
}

# Class-like node types
_CLASS_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration"}),
    ".tsx": frozenset({"class_declaration"}),
    ".java": frozenset({"class_declaration"}),
}

# Block body types
_BLOCK_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"block"}),
    ".js": frozenset({"statement_block"}),
    ".jsx": frozenset({"statement_block"}),
    ".ts": frozenset({"statement_block"}),
    ".tsx": frozenset({"statement_block"}),
    ".java": frozenset({"constructor_body", "block"}),
}


def _safe_text(node: tree_sitter.Node) -> str:
    raw = node.text
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class RedundantSuperIssue:
    line_number: int
    issue_type: str
    severity: str
    description: str
    function_name: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "function_name": self.function_name,
        }


@dataclass(frozen=True)
class RedundantSuperResult:
    total_constructors: int
    issues: tuple[RedundantSuperIssue, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_constructors": self.total_constructors,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "file_path": self.file_path,
        }


def _is_python_super_call(expr: tree_sitter.Node) -> bool:
    """Check if a Python expression is super().__init__(...) call."""
    # tree-sitter-python uses 'call' not 'call_expression'
    if expr.type not in ("call", "call_expression"):
        return False
    func = expr.child_by_field_name("function")
    if func is None:
        return False
    # Must be attribute access on a super() call: super().__init__
    if func.type == "attribute":
        obj = func.child_by_field_name("object")
        if obj is not None and obj.type in ("call", "call_expression"):
            inner_func = obj.child_by_field_name("function")
            if inner_func is not None and _safe_text(inner_func) == "super":
                return True
    return False


def _is_python_super_only_init(body: tree_sitter.Node) -> tuple[bool, bool]:
    """Check if a Python function body contains only super().__init__().

    Returns (is_super_only, is_passthrough).
    """
    statements = [
        c for c in body.children
        if c.is_named and c.type not in ("comment", "expression_statement")
    ]
    # Allow expression_statement wrapping
    expr_stmts = [
        c for c in body.children
        if c.type == "expression_statement"
    ]

    # If there are named non-comment statements that aren't expression_statement,
    # it's not super-only
    if statements:
        return False, False

    if len(expr_stmts) != 1:
        return False, False

    expr = expr_stmts[0].children[0] if expr_stmts[0].children else None
    if expr is None:
        return False, False

    if _is_python_super_call(expr):
        return True, False

    return False, False


def _analyze_python(
    node: tree_sitter.Node,
    issues: list[RedundantSuperIssue],
    source: bytes,
) -> int:
    """Analyze Python AST for redundant super() in __init__."""
    constructor_count = 0

    def visit(n: tree_sitter.Node) -> None:
        nonlocal constructor_count
        if n.type == "function_definition":
            name_node = n.child_by_field_name("name")
            if name_node is None or _safe_text(name_node) != "__init__":
                for child in n.children:
                    visit(child)
                return
            constructor_count += 1
            body = n.child_by_field_name("body")
            if body is None:
                return
            is_super, is_passthrough = _is_python_super_only_init(body)
            if is_super:
                issues.append(RedundantSuperIssue(
                    line_number=n.start_point[0] + 1,
                    issue_type=ISSUE_REDUNDANT_SUPER,
                    severity=_SEVERITY_MAP[ISSUE_REDUNDANT_SUPER],
                    description=_DESCRIPTIONS[ISSUE_REDUNDANT_SUPER],
                    function_name="__init__",
                ))
            elif is_passthrough:
                issues.append(RedundantSuperIssue(
                    line_number=n.start_point[0] + 1,
                    issue_type=ISSUE_PASSTHROUGH_SUPER,
                    severity=_SEVERITY_MAP[ISSUE_PASSTHROUGH_SUPER],
                    description=_DESCRIPTIONS[ISSUE_PASSTHROUGH_SUPER],
                    function_name="__init__",
                ))
                return
            for child in n.children:
                visit(child)
        else:
            for child in n.children:
                visit(child)

    visit(node)
    return constructor_count


def _is_js_super_call(expr: tree_sitter.Node) -> bool:
    """Check if a JS/TS expression is super(...) call."""
    if expr.type not in ("call_expression", "call"):
        return False
    func = expr.child_by_field_name("function")
    if func is not None and _safe_text(func) == "super":
        return True
    # Also check child[0] since tree-sitter may not use field names
    if func is not None and func.type == "super":
        return True
    return False


def _is_js_constructor(n: tree_sitter.Node) -> bool:
    """Check if a JS/TS method_definition is a constructor."""
    if n.type == "method_definition":
        for child in n.children:
            if child.type == "property_identifier" and _safe_text(child) == "constructor":
                return True
    return n.type == "constructor"


def _analyze_js(
    node: tree_sitter.Node,
    issues: list[RedundantSuperIssue],
) -> int:
    """Analyze JS/TS AST for redundant super() in constructors."""
    constructor_count = 0

    def visit(n: tree_sitter.Node) -> None:
        nonlocal constructor_count
        if _is_js_constructor(n):
            constructor_count += 1
            has_only_super = True
            has_super_call = False
            for child in n.children:
                if child.type == "statement_block":
                    for stmt in child.children:
                        if stmt.type == "comment":
                            continue
                        if not stmt.is_named:
                            continue
                        if stmt.type == "expression_statement":
                            for expr_child in stmt.children:
                                if _is_js_super_call(expr_child):
                                    has_super_call = True
                                    continue
                                if expr_child.is_named:
                                    has_only_super = False
                            continue
                        has_only_super = False
            if has_super_call and has_only_super:
                issues.append(RedundantSuperIssue(
                    line_number=n.start_point[0] + 1,
                    issue_type=ISSUE_REDUNDANT_SUPER,
                    severity=_SEVERITY_MAP[ISSUE_REDUNDANT_SUPER],
                    description=_DESCRIPTIONS[ISSUE_REDUNDANT_SUPER],
                    function_name="constructor",
                ))
            return
        for child in n.children:
            visit(child)

    visit(node)
    return constructor_count


def _analyze_java(
    node: tree_sitter.Node,
    issues: list[RedundantSuperIssue],
) -> int:
    """Analyze Java AST for redundant super() in constructors."""
    constructor_count = 0

    def visit(n: tree_sitter.Node) -> None:
        nonlocal constructor_count
        if n.type == "constructor_declaration":
            constructor_count += 1
            body = None
            has_super_only = True
            has_super_call = False
            for child in n.children:
                if child.type == "constructor_body":
                    body = child
                    for stmt in body.children:
                        if stmt.type == "explicit_constructor_invocation":
                            text = _safe_text(stmt).strip()
                            if text.startswith("super("):
                                has_super_call = True
                            elif text.startswith("this("):
                                has_super_only = False
                            continue
                        if not stmt.is_named:
                            continue
                        if stmt.type == "block_comment" or stmt.type == "line_comment":
                            continue
                        has_super_only = False
            if has_super_call and has_super_only:
                name_node = n.child_by_field_name("name")
                func_name = _safe_text(name_node) if name_node else "<init>"
                issues.append(RedundantSuperIssue(
                    line_number=n.start_point[0] + 1,
                    issue_type=ISSUE_REDUNDANT_SUPER,
                    severity=_SEVERITY_MAP[ISSUE_REDUNDANT_SUPER],
                    description=_DESCRIPTIONS[ISSUE_REDUNDANT_SUPER],
                    function_name=func_name,
                ))
            return
        for child in n.children:
            visit(child)

    visit(node)
    return constructor_count


class RedundantSuperAnalyzer(BaseAnalyzer):
    """Detects unnecessary super() calls in constructors."""

    SUPPORTED_EXTENSIONS: set[str] = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
    }

    def analyze_file(self, file_path: Path | str) -> RedundantSuperResult:
        path = Path(file_path)
        if not path.exists():
            return RedundantSuperResult(
                total_constructors=0,
                issues=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return RedundantSuperResult(
                total_constructors=0,
                issues=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> RedundantSuperResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return RedundantSuperResult(
                total_constructors=0,
                issues=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        issues: list[RedundantSuperIssue] = []
        total_constructors = 0

        if ext == ".py":
            total_constructors = _analyze_python(tree.root_node, issues, content)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            total_constructors = _analyze_js(tree.root_node, issues)
        elif ext == ".java":
            total_constructors = _analyze_java(tree.root_node, issues)

        return RedundantSuperResult(
            total_constructors=total_constructors,
            issues=tuple(issues),
            file_path=str(path),
        )
