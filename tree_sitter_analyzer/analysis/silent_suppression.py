"""Silent Error Suppression Detector.

Detects catch/except blocks that silently suppress errors without
meaningful recovery, re-raise, or state cleanup.

Issues detected:
  - silent_suppression: handler body is empty/pass/continue/return None
  - logging_only_suppression: handler body contains only logging calls

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_SILENT = "silent_suppression"
ISSUE_LOGGING_ONLY = "logging_only_suppression"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_SILENT: SEVERITY_HIGH,
    ISSUE_LOGGING_ONLY: SEVERITY_MEDIUM,
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_SILENT: (
        "Either re-raise the exception, handle it meaningfully, "
        "or let it propagate"
    ),
    ISSUE_LOGGING_ONLY: (
        "Add recovery logic, re-raise, or propagate the error after logging"
    ),
}

_PY_LOGGING_PREFIXES: frozenset[str] = frozenset({
    "logging.", "logger.", "log.",
})

_PY_LOGGING_METHODS: frozenset[str] = frozenset({
    "debug", "info", "warning", "warn", "error",
    "critical", "exception", "log",
})

_PY_SILENT_VALUES: frozenset[str] = frozenset({
    "None", "False", "-1", "0",
})

_JS_LOGGING_OBJECTS: frozenset[str] = frozenset({"console"})
_JS_LOGGING_METHODS: frozenset[str] = frozenset({
    "log", "warn", "error", "info", "debug",
})

_GO_LOGGING_OBJECTS: frozenset[str] = frozenset({"log", "slog", "logger"})
_GO_LOGGING_METHODS: frozenset[str] = frozenset({
    "Print", "Printf", "Println",
    "Debug", "Info", "Warn", "Error",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _named_children(node: tree_sitter.Node) -> list[tree_sitter.Node]:
    return [c for c in node.children if c.is_named]


def _is_py_logging_call(node: tree_sitter.Node) -> bool:
    if node.type != "expression_statement":
        return False
    child = node.children[0] if node.children else None
    if not child or child.type != "call":
        return False
    func = child.child_by_field_name("function")
    if not func:
        return False
    text = _txt(func)
    for prefix in _PY_LOGGING_PREFIXES:
        if text.startswith(prefix):
            method = text[len(prefix):]
            if method in _PY_LOGGING_METHODS:
                return True
    if func.type == "attribute":
        obj = func.child_by_field_name("object")
        if obj and obj.type == "attribute":
            outer_text = _txt(obj)
            for prefix in _PY_LOGGING_PREFIXES:
                if outer_text.startswith(prefix):
                    return True
    return False


def _is_js_logging_call(node: tree_sitter.Node) -> bool:
    if node.type != "expression_statement":
        return False
    child = node.children[0] if node.children else None
    if not child or child.type != "call_expression":
        return False
    func = child.child_by_field_name("function")
    if not func or func.type != "member_expression":
        return False
    obj = func.child_by_field_name("object")
    prop = func.child_by_field_name("property")
    if obj and prop:
        return (
            _txt(obj) in _JS_LOGGING_OBJECTS
            and _txt(prop) in _JS_LOGGING_METHODS
        )
    return False


def _is_java_logging_call(node: tree_sitter.Node) -> bool:
    if node.type != "expression_statement":
        return False
    child = node.children[0] if node.children else None
    if not child or child.type != "method_invocation":
        return False
    method_name = ""
    for mc in child.children:
        if mc.type == "identifier":
            method_name = _txt(mc)
    if method_name == "printStackTrace":
        return True
    obj = child.child_by_field_name("object")
    method = child.child_by_field_name("name")
    if obj and method:
        obj_text = _txt(obj).lower()
        method_text = _txt(method)
        if obj_text in ("log", "logger", "logging", "logs"):
            if method_text in (
                "debug", "info", "warn", "warning", "error", "fatal", "trace",
            ):
                return True
    return False


def _is_go_logging_call(node: tree_sitter.Node) -> bool:
    if node.type != "expression_statement":
        return False
    child = node.children[0] if node.children else None
    if not child or child.type != "call_expression":
        return False
    func = child.child_by_field_name("function")
    if not func or func.type != "selector_expression":
        return False
    operand = func.child_by_field_name("operand")
    field = func.child_by_field_name("field")
    if operand and field:
        return (
            _txt(operand) in _GO_LOGGING_OBJECTS
            and _txt(field) in _GO_LOGGING_METHODS
        )
    return False


def _go_body_returns_err(body: tree_sitter.Node) -> bool:
    for stmt in _named_children(body):
        stmt_text = _txt(stmt)
        if stmt.type == "return_statement" and "err" in stmt_text:
            return True
        if "log.Fatal" in stmt_text or "os.Exit" in stmt_text:
            return True
        if "panic" in stmt_text:
            return True
    return False


@dataclass(frozen=True)
class SilentSuppressionIssue:
    line: int
    issue_type: str
    severity: str
    handler_type: str
    description: str
    suggestion: str


@dataclass(frozen=True)
class SilentSuppressionResult:
    issues: tuple[SilentSuppressionIssue, ...]
    total_issues: int
    high_severity: int
    medium_severity: int
    file_path: str
    language: str


def _empty_result(file_path: str, language: str) -> SilentSuppressionResult:
    return SilentSuppressionResult(
        issues=(),
        total_issues=0,
        high_severity=0,
        medium_severity=0,
        file_path=file_path,
        language=language,
    )


class SilentSuppressionAnalyzer(BaseAnalyzer):
    """Detects catch/except blocks that silently suppress errors."""

    def analyze_file(self, file_path: Path | str) -> SilentSuppressionResult:
        path = Path(file_path)
        if not path.exists():
            return _empty_result(str(path), "unknown")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return _empty_result(str(path), "unknown")

        language_map: dict[str, str] = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go",
        }
        lang = language_map.get(ext, "unknown")

        content = path.read_bytes()

        if ext == ".py":
            issues = self._analyze_python(content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues = self._analyze_javascript(content)
        elif ext == ".java":
            issues = self._analyze_java(content)
        elif ext == ".go":
            issues = self._analyze_go(content)
        else:
            issues = []

        issue_tuple = tuple(issues)
        high = sum(1 for i in issue_tuple if i.severity == SEVERITY_HIGH)
        medium = sum(1 for i in issue_tuple if i.severity == SEVERITY_MEDIUM)
        return SilentSuppressionResult(
            issues=issue_tuple,
            total_issues=len(issue_tuple),
            high_severity=high,
            medium_severity=medium,
            file_path=str(path),
            language=lang,
        )

    # -- Python -----------------------------------------------------------

    def _analyze_python(self, content: bytes) -> list[SilentSuppressionIssue]:
        language, parser = self._get_parser(".py")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SilentSuppressionIssue] = []
        self._walk_py_except(tree.root_node, issues)
        return issues

    def _walk_py_except(
        self, node: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        if node.type == "except_clause":
            for child in node.children:
                if child.type == "block":
                    self._classify_py_handler(child, issues)
                    break

        for child in node.children:
            self._walk_py_except(child, issues)

    def _classify_py_handler(
        self, block: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        stmts = _named_children(block)
        if not stmts:
            issues.append(SilentSuppressionIssue(
                line=block.start_point[0] + 1,
                issue_type=ISSUE_SILENT,
                severity=SEVERITY_HIGH,
                handler_type="empty",
                description="Empty except block silently suppresses errors",
                suggestion=_SUGGESTIONS[ISSUE_SILENT],
            ))
            return

        for s in stmts:
            if s.type == "raise_statement":
                return

        if len(stmts) == 1:
            s = stmts[0]
            if s.type == "pass_statement":
                issues.append(SilentSuppressionIssue(
                    line=s.start_point[0] + 1,
                    issue_type=ISSUE_SILENT,
                    severity=SEVERITY_HIGH,
                    handler_type="pass",
                    description="except block with only 'pass' silently suppresses errors",
                    suggestion=_SUGGESTIONS[ISSUE_SILENT],
                ))
                return
            if s.type == "continue_statement":
                issues.append(SilentSuppressionIssue(
                    line=s.start_point[0] + 1,
                    issue_type=ISSUE_SILENT,
                    severity=SEVERITY_HIGH,
                    handler_type="continue",
                    description="except block with 'continue' silently suppresses errors",
                    suggestion=_SUGGESTIONS[ISSUE_SILENT],
                ))
                return
            if s.type == "return_statement":
                named = _named_children(s)
                if not named:
                    issues.append(SilentSuppressionIssue(
                        line=s.start_point[0] + 1,
                        issue_type=ISSUE_SILENT,
                        severity=SEVERITY_HIGH,
                        handler_type="return",
                        description="except block with bare return suppresses errors",
                        suggestion=_SUGGESTIONS[ISSUE_SILENT],
                    ))
                    return
                val = _txt(named[0])
                if val in _PY_SILENT_VALUES:
                    issues.append(SilentSuppressionIssue(
                        line=s.start_point[0] + 1,
                        issue_type=ISSUE_SILENT,
                        severity=SEVERITY_HIGH,
                        handler_type=f"return {val}",
                        description=f"except block returns {val}, suppressing error",
                        suggestion=_SUGGESTIONS[ISSUE_SILENT],
                    ))
                    return

        if all(_is_py_logging_call(s) for s in stmts):
            issues.append(SilentSuppressionIssue(
                line=stmts[0].start_point[0] + 1,
                issue_type=ISSUE_LOGGING_ONLY,
                severity=SEVERITY_MEDIUM,
                handler_type="logging_only",
                description="except block only logs error without recovery or re-raise",
                suggestion=_SUGGESTIONS[ISSUE_LOGGING_ONLY],
            ))

    # -- JavaScript/TypeScript --------------------------------------------

    def _analyze_javascript(self, content: bytes) -> list[SilentSuppressionIssue]:
        language, parser = self._get_parser(".js")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SilentSuppressionIssue] = []
        self._walk_js_catch(tree.root_node, issues)
        return issues

    def _walk_js_catch(
        self, node: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        if node.type == "catch_clause":
            body = node.child_by_field_name("body")
            if body:
                self._classify_js_handler(body, issues)

        for child in node.children:
            self._walk_js_catch(child, issues)

    def _classify_js_handler(
        self, body: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        stmts = _named_children(body)
        if not stmts:
            issues.append(SilentSuppressionIssue(
                line=body.start_point[0] + 1,
                issue_type=ISSUE_SILENT,
                severity=SEVERITY_HIGH,
                handler_type="empty",
                description="Empty catch block silently suppresses errors",
                suggestion=_SUGGESTIONS[ISSUE_SILENT],
            ))
            return

        for s in stmts:
            if s.type == "throw_statement":
                return

        if len(stmts) == 1:
            s = stmts[0]
            if s.type == "return_statement":
                named = _named_children(s)
                if not named:
                    issues.append(SilentSuppressionIssue(
                        line=s.start_point[0] + 1,
                        issue_type=ISSUE_SILENT,
                        severity=SEVERITY_HIGH,
                        handler_type="return",
                        description="catch block with bare return suppresses errors",
                        suggestion=_SUGGESTIONS[ISSUE_SILENT],
                    ))
                    return
                val = _txt(named[0])
                if val in ("null", "undefined", "false", "-1", "0"):
                    issues.append(SilentSuppressionIssue(
                        line=s.start_point[0] + 1,
                        issue_type=ISSUE_SILENT,
                        severity=SEVERITY_HIGH,
                        handler_type=f"return {val}",
                        description=f"catch block returns {val}, suppressing error",
                        suggestion=_SUGGESTIONS[ISSUE_SILENT],
                    ))
                    return

        if all(_is_js_logging_call(s) for s in stmts):
            issues.append(SilentSuppressionIssue(
                line=stmts[0].start_point[0] + 1,
                issue_type=ISSUE_LOGGING_ONLY,
                severity=SEVERITY_MEDIUM,
                handler_type="logging_only",
                description="catch block only logs error without recovery or re-throw",
                suggestion=_SUGGESTIONS[ISSUE_LOGGING_ONLY],
            ))

    # -- Java -------------------------------------------------------------

    def _analyze_java(self, content: bytes) -> list[SilentSuppressionIssue]:
        language, parser = self._get_parser(".java")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SilentSuppressionIssue] = []
        self._walk_java_catch(tree.root_node, issues)
        return issues

    def _walk_java_catch(
        self, node: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        if node.type == "catch_clause":
            for child in node.children:
                if child.type == "block":
                    self._classify_java_handler(child, issues)
                    break

        for child in node.children:
            self._walk_java_catch(child, issues)

    def _classify_java_handler(
        self, body: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        stmts = _named_children(body)
        if not stmts:
            issues.append(SilentSuppressionIssue(
                line=body.start_point[0] + 1,
                issue_type=ISSUE_SILENT,
                severity=SEVERITY_HIGH,
                handler_type="empty",
                description="Empty catch block silently suppresses errors",
                suggestion=_SUGGESTIONS[ISSUE_SILENT],
            ))
            return

        for s in stmts:
            if s.type == "throw_statement":
                return

        if len(stmts) == 1:
            s = stmts[0]
            if s.type == "return_statement":
                named = _named_children(s)
                if not named:
                    issues.append(SilentSuppressionIssue(
                        line=s.start_point[0] + 1,
                        issue_type=ISSUE_SILENT,
                        severity=SEVERITY_HIGH,
                        handler_type="return",
                        description="catch block with bare return suppresses errors",
                        suggestion=_SUGGESTIONS[ISSUE_SILENT],
                    ))
                    return
                val = _txt(named[0])
                if val in ("null", "false", "-1", "0"):
                    issues.append(SilentSuppressionIssue(
                        line=s.start_point[0] + 1,
                        issue_type=ISSUE_SILENT,
                        severity=SEVERITY_HIGH,
                        handler_type=f"return {val}",
                        description=f"catch block returns {val}, suppressing error",
                        suggestion=_SUGGESTIONS[ISSUE_SILENT],
                    ))
                    return

        if all(_is_java_logging_call(s) for s in stmts):
            issues.append(SilentSuppressionIssue(
                line=stmts[0].start_point[0] + 1,
                issue_type=ISSUE_LOGGING_ONLY,
                severity=SEVERITY_MEDIUM,
                handler_type="logging_only",
                description="catch block only logs error without recovery or re-throw",
                suggestion=_SUGGESTIONS[ISSUE_LOGGING_ONLY],
            ))

    # -- Go ---------------------------------------------------------------

    def _analyze_go(self, content: bytes) -> list[SilentSuppressionIssue]:
        language, parser = self._get_parser(".go")
        if language is None or parser is None:
            return []

        tree = parser.parse(content)
        issues: list[SilentSuppressionIssue] = []
        self._walk_go_err_check(tree.root_node, issues)
        return issues

    def _walk_go_err_check(
        self, node: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        if node.type == "if_statement":
            cond = node.child_by_field_name("condition")
            if cond and re.search(r"!=\s*nil", _txt(cond)):
                for child in node.children:
                    if child.type == "block":
                        self._classify_go_handler(child, issues)
                        break

        for child in node.children:
            self._walk_go_err_check(child, issues)

    def _classify_go_handler(
        self, body: tree_sitter.Node, issues: list[SilentSuppressionIssue],
    ) -> None:
        if _go_body_returns_err(body):
            return

        stmts = _named_children(body)
        if not stmts:
            issues.append(SilentSuppressionIssue(
                line=body.start_point[0] + 1,
                issue_type=ISSUE_SILENT,
                severity=SEVERITY_HIGH,
                handler_type="empty",
                description="Empty error check block silently suppresses errors",
                suggestion=_SUGGESTIONS[ISSUE_SILENT],
            ))
            return

        if all(_is_go_logging_call(s) for s in stmts):
            issues.append(SilentSuppressionIssue(
                line=stmts[0].start_point[0] + 1,
                issue_type=ISSUE_LOGGING_ONLY,
                severity=SEVERITY_MEDIUM,
                handler_type="logging_only",
                description="Error check only logs without propagating or recovering",
                suggestion=_SUGGESTIONS[ISSUE_LOGGING_ONLY],
            ))
