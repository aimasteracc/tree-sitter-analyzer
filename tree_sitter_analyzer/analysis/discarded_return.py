"""Discarded Return Value Detector.

Detects function/method calls whose return values are silently discarded:
  - discarded_result: function call used as a bare expression statement
  - discarded_await: async function call without await (JS/TS Promise lost)
  - discarded_error: error-returning call whose error value is discarded (Go)

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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_DISCARDED_RESULT = "discarded_result"
ISSUE_DISCARDED_AWAIT = "discarded_await"
ISSUE_DISCARDED_ERROR = "discarded_error"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_DISCARDED_RESULT: SEVERITY_LOW,
    ISSUE_DISCARDED_AWAIT: SEVERITY_HIGH,
    ISSUE_DISCARDED_ERROR: SEVERITY_HIGH,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_DISCARDED_RESULT: "Function return value is discarded",
    ISSUE_DISCARDED_AWAIT: "Async function called without await — Promise result is lost",
    ISSUE_DISCARDED_ERROR: "Error return value is discarded",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_DISCARDED_RESULT: "Store the return value or explicitly discard with _ if intentional.",
    ISSUE_DISCARDED_AWAIT: "Add await keyword to properly handle the Promise.",
    ISSUE_DISCARDED_ERROR: "Check the error return value before proceeding.",
}

# Call expression node types per language
_CALL_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"call"}),
    ".js": frozenset({"call_expression"}),
    ".jsx": frozenset({"call_expression"}),
    ".ts": frozenset({"call_expression"}),
    ".tsx": frozenset({"call_expression"}),
    ".java": frozenset({"method_invocation"}),
    ".go": frozenset({"call_expression"}),
}

# Expression statement node types per language
_EXPR_STMT_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"expression_statement"}),
    ".js": frozenset({"expression_statement"}),
    ".jsx": frozenset({"expression_statement"}),
    ".ts": frozenset({"expression_statement"}),
    ".tsx": frozenset({"expression_statement"}),
    ".java": frozenset({"expression_statement"}),
    ".go": frozenset({"expression_statement"}),
}

# Assignment-like parent types where the result IS used
_ASSIGNMENT_TYPES: frozenset[str] = frozenset({
    "assignment",
    "augmented_assignment",
    "variable_declarator",
    "init_declarator",
    "short_var_declaration",
    "assignment_expression",
    "var_declaration",
    "local_declaration",
    "for_statement",
    "return_statement",
    "yield_statement",
    "assert_statement",
    "raise_statement",
    "if_statement",
    "while_statement",
    "conditional_expression",
    "ternary_expression",
    "boolean_operator",
    "binary_operator",
    "comparison_operator",
    "not_operator",
    "parenthesized_expression",
    "argument_list",
    "argument",
    "pair",
    "array",
    "list",
    "tuple",
    "dictionary",
    "set",
    "list_comprehension",
    "set_comprehension",
    "dictionary_comprehension",
    "generator_expression",
    "await_expression",
    "member_expression",
    "subscript",
    "chained_expression",
    "attribute",
})

# Known fire-and-forget functions (low false-positive rate)
_SAFE_FUNCTIONS: frozenset[str] = frozenset({
    "print", "println", "printf", "fmt.Println", "fmt.Printf",
    "log", "logger.info", "logger.debug", "logger.warning",
    "logger.error", "logger.critical", "console.log", "console.warn",
    "console.error", "console.info", "console.debug",
    "append", "push", "push_back", "push_front",
    "add", "put", "set", "remove", "delete", "clear",
    "close", "flush", "sync", "commit",
    "write", "writeln", "writeLine",
    "notify", "notifyAll", "notify_all",
    "System.out.println", "System.out.print",
    "System.err.println", "System.err.print",
    "assert", "assertEqual", "assertTrue", "assertFalse",
    "assertNotNull", "assertNull", "assertRaises",
    "fail", "skip", "skipTest",
    "time.Sleep", "sleep", "time.sleep",
    "wait", "waitFor", "wait_for",
})

# Python async call patterns (inside an async function but not awaited)
_ASYNC_KEYWORDS: frozenset[str] = frozenset({"async"})


@dataclass(frozen=True)
class DiscardedReturnIssue:
    """A single discarded return value issue."""

    issue_type: str
    line: int
    column: int
    function_name: str
    severity: str
    description: str
    suggestion: str
    context: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "column": self.column,
            "function_name": self.function_name,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "context": self.context,
        }


@dataclass
class DiscardedReturnResult:
    """Result of discarded return value analysis."""

    file_path: str
    total_calls: int
    issues: list[DiscardedReturnIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_calls": self.total_calls,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class DiscardedReturnAnalyzer(BaseAnalyzer):
    """Detects function calls whose return values are discarded."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(self, file_path: str | Path) -> DiscardedReturnResult:
        """Analyze a single file for discarded return values."""
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return DiscardedReturnResult(
                file_path=str(path), total_calls=0, issues=[],
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return DiscardedReturnResult(
                file_path=str(path), total_calls=0, issues=[],
            )

        try:
            source = path.read_bytes()
        except OSError:
            return DiscardedReturnResult(
                file_path=str(path), total_calls=0, issues=[],
            )

        tree = parser.parse(source)
        if tree.root_node is None:
            return DiscardedReturnResult(
                file_path=str(path), total_calls=0, issues=[],
            )

        issues: list[DiscardedReturnIssue] = []
        total_calls = 0

        call_types = _CALL_TYPES.get(ext, frozenset())
        expr_stmt_types = _EXPR_STMT_TYPES.get(ext, frozenset())

        for node in _walk(tree.root_node):
            if node.type not in call_types:
                continue
            total_calls += 1

            func_name = _extract_function_name(node, source)
            if func_name is None:
                continue

            # Skip known fire-and-forget functions
            if _is_safe_function(func_name):
                continue

            parent = node.parent
            if parent is None:
                continue

            # Check if parent is an expression statement (bare call)
            if parent.type not in expr_stmt_types:
                continue

            context = _safe_text(parent, source)

            issue_type = ISSUE_DISCARDED_RESULT
            severity = _SEVERITY_MAP[ISSUE_DISCARDED_RESULT]
            description = _DESCRIPTIONS[ISSUE_DISCARDED_RESULT]
            suggestion = _SUGGESTIONS[ISSUE_DISCARDED_RESULT]

            # Language-specific checks
            if ext in (".js", ".jsx", ".ts", ".tsx"):
                if _looks_async(func_name, node, source, ext):
                    issue_type = ISSUE_DISCARDED_AWAIT
                    severity = _SEVERITY_MAP[ISSUE_DISCARDED_AWAIT]
                    description = _DESCRIPTIONS[ISSUE_DISCARDED_AWAIT]
                    suggestion = _SUGGESTIONS[ISSUE_DISCARDED_AWAIT]

            if ext == ".go":
                if _go_error_discarded(node, source):
                    issue_type = ISSUE_DISCARDED_ERROR
                    severity = _SEVERITY_MAP[ISSUE_DISCARDED_ERROR]
                    description = _DESCRIPTIONS[ISSUE_DISCARDED_ERROR]
                    suggestion = _SUGGESTIONS[ISSUE_DISCARDED_ERROR]

            issues.append(DiscardedReturnIssue(
                issue_type=issue_type,
                line=node.start_point[0] + 1,
                column=node.start_point[1],
                function_name=func_name,
                severity=severity,
                description=description,
                suggestion=suggestion,
                context=context[:200],
            ))

        return DiscardedReturnResult(
            file_path=str(path),
            total_calls=total_calls,
            issues=issues,
        )


def _walk(node: tree_sitter.Node) -> Any:
    """Depth-first traversal of all nodes."""
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


def _safe_text(node: tree_sitter.Node, source: bytes) -> str:
    """Extract text from a node safely."""
    raw = node.text
    return raw.decode("utf-8", errors="replace") if raw else ""


def _extract_function_name(
    node: tree_sitter.Node, source: bytes,
) -> str | None:
    """Extract the function name from a call node."""
    if node.child_count == 0:
        return None

    first_child = node.child(0)
    if first_child is None:
        return None

    # Direct identifier: funcName(...)
    if first_child.type == "identifier":
        return _safe_text(first_child, source)

    # Attribute/member access: obj.method(...)
    if first_child.type in (
        "attribute", "member_expression", "field_expression",
        "scoped_identifier", "scoped_type_identifier",
    ):
        # Get the last child (the actual function name)
        children = [c for c in first_child.children if c.is_named]
        if children:
            last = children[-1]
            name = _safe_text(last, source)
            obj = _safe_text(children[0], source) if len(children) > 1 else ""
            if obj:
                return f"{obj}.{name}"
            return name
        return _safe_text(first_child, source)

    # Parenthesized or other expression — recurse
    text = _safe_text(first_child, source)
    if len(text) > 60:
        return None
    return text


def _is_safe_function(name: str) -> bool:
    """Check if the function is a known fire-and-forget function."""
    # Check exact match
    if name in _SAFE_FUNCTIONS:
        return True
    # Check suffix (e.g., self.print, this.log)
    parts = name.rsplit(".", maxsplit=1)
    if len(parts) == 2:
        if parts[1] in _SAFE_FUNCTIONS:
            return True
    # Common assertion patterns
    lower = name.lower()
    if lower.startswith("assert") or lower.startswith("expect"):
        return True
    # Common logging patterns
    if "log" in lower or "print" in lower:
        return True
    return False


def _looks_async(
    func_name: str,
    node: tree_sitter.Node,
    source: bytes,
    ext: str,
) -> bool:
    """Check if a JS/TS function call looks like it returns a Promise."""
    lower = func_name.lower()

    # Match common async function names with word boundaries
    async_prefixes = (
        "fetch", "async", "await_", "promise",
    )
    async_exact = (
        "then", "catch", "finally",
        "get", "post", "put", "delete", "patch", "head",
        "request", "send", "receive",
        "read", "write",
        "connect", "disconnect",
        "open", "close",
        "start", "stop",
        "load", "save",
        "parse", "stringify",
        "execute", "query", "run",
        "wait", "delay", "sleep", "timeout",
        "subscribe", "listen", "observe",
        "transform", "process",
    )

    for prefix in async_prefixes:
        if lower.startswith(prefix):
            return True

    # Check exact match or word-boundary match (e.g., "fetchData" but not "compute")
    for pattern in async_exact:
        if lower == pattern:
            return True
        # CamelCase boundary: pattern at start followed by uppercase
        if lower.startswith(pattern) and len(lower) > len(pattern):
            next_char = lower[len(pattern)]
            if next_char.isupper() or next_char == "_":
                return True

    return False


def _go_error_discarded(node: tree_sitter.Node, source: bytes) -> bool:
    """Check if a Go call discards its error return value.

    In Go, error-returning calls like:
      val, err := doSomething()  // good
      doSomething()              // bad if it returns error
    """
    # The call is already confirmed to be a bare expression statement.
    # We check if the function name suggests it returns an error.
    first_child = node.child(0)
    if first_child is None:
        return False
    name = _safe_text(first_child, source)

    # Common Go functions that return errors
    error_patterns = (
        "Open", "Create", "Read", "Write", "Close",
        "Marshal", "Unmarshal", "Parse", "Format",
        "Copy", "Move", "Remove", "Rename",
        "Connect", "Dial", "Listen", "Accept",
        "Get", "Post", "Put", "Delete",
        "Exec", "Run", "Start", "Wait",
        "Scan", "Query", "Exec",
        "New", "Make",
        "Encode", "Decode",
        "Compress", "Decompress",
        "Encrypt", "Decrypt",
        "Sign", "Verify",
        "Validate", "Check",
        "Send", "Receive",
        "Lookup", "Resolve",
    )

    for pattern in error_patterns:
        if pattern in name:
            return True

    return False
