#!/usr/bin/env python3
"""
Unreachable Code Path Detector — AST-level unreachable code detection.

Detects code that can never execute within function/method bodies:

- Code after ``return`` / ``raise`` / ``break`` / ``continue``
- ``else`` branch after ``if False:`` (constant-false conditions)
- Code after ``sys.exit()`` / ``os._exit()`` / ``exit()`` / ``quit()``
- Unreachable ``except`` handlers that shadow earlier catch-all

Unlike the dead code analyzer (function-level: "is anyone calling this?"),
this detects **statement-level** dead code within live functions.

Uses Tree-sitter AST analysis for cross-language support.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .core.parser import Parser
from .function_extraction import _FUNC_DEF_TYPES
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".cache",
    ".eggs",
    ".idea",
    ".vscode",
    ".claude",
}

_TERMINAL_STATEMENT_TYPES: dict[str, set[str]] = {
    "python": {"return_statement", "raise_statement"},
    "javascript": {"return_statement", "throw_statement"},
    "typescript": {"return_statement", "throw_statement"},
    "java": {"return_statement", "throw_statement"},
    "go": {"return_statement"},
    "c": {"return_statement"},
    "cpp": {"return_statement"},
}

_LOOP_BREAK_TYPES: dict[str, set[str]] = {
    "python": {"break_statement", "continue_statement"},
    "javascript": {"break_statement", "continue_statement"},
    "typescript": {"break_statement", "continue_statement"},
    "java": {"break_statement", "continue_statement"},
    "go": {"break_statement", "continue_statement"},
    "c": {"break_statement", "continue_statement"},
    "cpp": {"break_statement", "continue_statement"},
}

_TERMINAL_CALL_NAMES = frozenset(
    {
        "sys.exit",
        "os._exit",
        "exit",
        "quit",
        "abort",
        "fatal",
        "die",
        "panic",
    }
)

_BLOCK_TYPES: dict[str, str] = {
    "python": "block",
    "javascript": "statement_block",
    "typescript": "statement_block",
    "java": "block",
    "go": "block",
    "c": "compound_statement",
    "cpp": "compound_statement",
}

_IF_TYPES: dict[str, str] = {
    "python": "if_statement",
    "javascript": "if_statement",
    "typescript": "if_statement",
    "java": "if_statement",
    "go": "if_statement",
    "c": "if_statement",
    "cpp": "if_statement",
}

_TRY_TYPES: dict[str, str] = {
    "python": "try_statement",
    "javascript": "try_statement",
    "typescript": "try_statement",
    "java": "try_statement",
    "go": "try_statement",
    "c": "try_statement",
    "cpp": "try_statement",
}


@dataclass
class UnreachableBlock:
    file_path: str
    function_name: str
    start_line: int
    end_line: int
    reason: str
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "function": self.function_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass
class UnreachableCodeResult:
    file_path: str
    language: str
    unreachable_blocks: list[UnreachableBlock] = field(default_factory=list)
    functions_analyzed: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "language": self.language,
            "functions_analyzed": self.functions_analyzed,
            "unreachable_count": len(self.unreachable_blocks),
            "unreachable_blocks": [b.to_dict() for b in self.unreachable_blocks],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Low-level node helpers
# ---------------------------------------------------------------------------


def _node_text(node: Any, source: str) -> str:
    try:
        text = node.text
        if isinstance(text, bytes):
            return text.decode("utf-8")
        return str(text)
    except Exception:
        return source[node.start_byte : node.end_byte]


def _is_terminal_call(node: Any, source: str, language: str) -> bool:
    if language not in ("python", "javascript", "typescript", "java"):
        return False
    call_type = "call" if language == "python" else "call_expression"
    if node.type != call_type:
        return False
    func_node = _find_call_func_node(node, language)
    if func_node is None:
        return False
    call_name = _node_text(func_node, source).strip()
    return any(
        call_name.endswith(pattern) or call_name == pattern
        for pattern in _TERMINAL_CALL_NAMES
    )


def _find_call_func_node(node: Any, language: str) -> Any:
    """Extract the function-name node from a call node."""
    func_node = node.child_by_field_name("function")
    if func_node is not None:
        return func_node
    if language in ("javascript", "typescript"):
        for child in node.children:
            if child.type in ("identifier", "member_expression"):
                return child
    return None


def _is_terminal_statement(node: Any, source: str, language: str) -> bool:
    terminal_types = _TERMINAL_STATEMENT_TYPES.get(language, set())
    if node.type in terminal_types:
        return True
    return _is_terminal_call(node, source, language)


def _is_false_literal(node: Any, source: str) -> bool:
    if node is None:
        return False
    text = _node_text(node, source).strip()
    return text in ("False", "false", "0", "None", "null", "nil", "undefined")


def _is_true_literal(node: Any, source: str) -> bool:
    if node is None:
        return False
    text = _node_text(node, source).strip()
    return text in ("True", "true", "1")


def _find_children_by_type(node: Any, type_name: str) -> list[Any]:
    result = []
    for child in getattr(node, "children", []):
        if child.type == type_name:
            result.append(child)
    return result


# ---------------------------------------------------------------------------
# Block-level analysis
# ---------------------------------------------------------------------------


def _analyze_block_unreachable(
    block_node: Any,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> bool:
    """Walk a block's children; detect unreachable statements after terminals.

    Returns True if the block itself always terminates (ends with return/raise).
    """
    children = list(getattr(block_node, "children", []))
    if not children:
        return False

    found_terminal = False
    terminal_idx = -1

    for i, child in enumerate(children):
        if found_terminal:
            _report_unreachable_after_terminal(
                child, children[terminal_idx], func_name, file_path, results
            )
            continue

        if _is_terminal_statement(child, source, language):
            found_terminal = True
            terminal_idx = i
            _analyze_child_nodes(child, source, language, func_name, file_path, results)
            continue

        if language in _LOOP_BREAK_TYPES and child.type in _LOOP_BREAK_TYPES[language]:
            found_terminal = True
            terminal_idx = i
            continue

        if_type = _IF_TYPES.get(language)
        if if_type and child.type == if_type:
            _analyze_if_statement(
                child, source, language, func_name, file_path, results
            )

        try_type = _TRY_TYPES.get(language)
        if try_type and child.type == try_type:
            _analyze_try_statement(
                child, source, language, func_name, file_path, results
            )

    return found_terminal


def _report_unreachable_after_terminal(
    child: Any,
    terminal_node: Any,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    """Append an UnreachableBlock for code that follows a terminal statement."""
    if child.type in ("comment", "pass_statement"):
        return
    start_line = child.start_point[0] + 1
    end_line = child.end_point[0] + 1
    if start_line == end_line and child.type in ("newline",):
        return
    terminal_line = terminal_node.start_point[0] + 1
    reason = (
        f"code after {terminal_node.type.replace('_', ' ')} on line {terminal_line}"
    )
    results.append(
        UnreachableBlock(
            file_path=file_path,
            function_name=func_name,
            start_line=start_line,
            end_line=end_line,
            reason=reason,
            severity="warning",
        )
    )


def _analyze_child_nodes(
    node: Any,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    block_type = _BLOCK_TYPES.get(language)
    for child in getattr(node, "children", []):
        if block_type and child.type == block_type:
            _analyze_block_unreachable(
                child, source, language, func_name, file_path, results
            )
        else:
            _analyze_child_nodes(child, source, language, func_name, file_path, results)


# ---------------------------------------------------------------------------
# If-statement analysis helpers
# ---------------------------------------------------------------------------


def _get_if_condition(node: Any, language: str) -> Any:
    """Return the condition node for an if statement."""
    condition = node.child_by_field_name("condition")
    if condition is None and language in (
        "javascript",
        "typescript",
        "java",
        "c",
        "cpp",
    ):
        for child in node.children:
            if child.type == "parenthesized_expression":
                return child
    return condition


def _get_consequence_and_alternative(node: Any, block_type: str) -> tuple[Any, Any]:
    """Return the (consequence_block, alternative_clause) for an if node."""
    consequence = None
    alternative = None
    for child in getattr(node, "children", []):
        if child.type == block_type and consequence is None:
            consequence = child
        elif child.type in ("else_clause", "else"):
            alternative = child
    return consequence, alternative


def _report_dead_branch(
    branch_node: Any,
    condition: Any,
    reason_template: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    """Append an UnreachableBlock for a statically-dead if/else branch."""
    start_line = branch_node.start_point[0] + 1
    end_line = branch_node.end_point[0] + 1
    condition_line = condition.start_point[0] + 1
    results.append(
        UnreachableBlock(
            file_path=file_path,
            function_name=func_name,
            start_line=start_line,
            end_line=end_line,
            reason=reason_template.format(line=condition_line),
            severity="info",
        )
    )


def _analyze_if_statement(
    node: Any,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    condition = _get_if_condition(node, language)
    block_type = _BLOCK_TYPES.get(language, "block")
    consequence, alternative = _get_consequence_and_alternative(node, block_type)

    if condition is not None:
        _check_constant_condition(
            condition,
            consequence,
            alternative,
            block_type,
            source,
            func_name,
            file_path,
            results,
        )

    if consequence is not None:
        _analyze_block_unreachable(
            consequence, source, language, func_name, file_path, results
        )
    if alternative is not None:
        _analyze_alternative_clause(
            alternative, source, language, func_name, file_path, results
        )


def _check_constant_condition(
    condition: Any,
    consequence: Any,
    alternative: Any,
    block_type: str,
    source: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    """Flag consequence or alternative as unreachable for constant conditions."""
    if _is_false_literal(condition, source) and consequence is not None:
        _report_dead_branch(
            consequence,
            condition,
            "if-False branch is never executed (condition is always False on line {line})",
            func_name,
            file_path,
            results,
        )
    elif _is_true_literal(condition, source) and alternative is not None:
        alt_block = _find_block_in_clause(alternative, block_type)
        if alt_block is not None:
            _report_dead_branch(
                alt_block,
                condition,
                "else branch of if-True is never executed (condition is always True on line {line})",
                func_name,
                file_path,
                results,
            )


def _find_block_in_clause(clause: Any, block_type: str) -> Any:
    """Return the first block child of an else clause."""
    for child in getattr(clause, "children", []):
        if child.type == block_type:
            return child
    return None


def _analyze_alternative_clause(
    alternative: Any,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    """Recursively analyze the else or elif clause of an if statement."""
    block_type_name = _BLOCK_TYPES.get(language, "block")
    if_type = _IF_TYPES.get(language, "")
    for child in getattr(alternative, "children", []):
        if child.type == block_type_name:
            _analyze_block_unreachable(
                child, source, language, func_name, file_path, results
            )
        elif child.type == if_type:
            _analyze_if_statement(
                child, source, language, func_name, file_path, results
            )


# ---------------------------------------------------------------------------
# Try-statement analysis
# ---------------------------------------------------------------------------


def _analyze_try_statement(
    node: Any,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    block_type = _BLOCK_TYPES.get(language, "block")
    for child in getattr(node, "children", []):
        if child.type == block_type:
            _analyze_block_unreachable(
                child, source, language, func_name, file_path, results
            )
        elif child.type in ("except_clause", "catch_clause", "handler_clause"):
            _analyze_handler_block(
                child, block_type, source, language, func_name, file_path, results
            )
        elif child.type in ("finally_clause", "finally_block"):
            _analyze_handler_block(
                child, block_type, source, language, func_name, file_path, results
            )


def _analyze_handler_block(
    handler: Any,
    block_type: str,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    """Analyze all block children within an except/finally handler."""
    for sub in getattr(handler, "children", []):
        if sub.type == block_type:
            _analyze_block_unreachable(
                sub, source, language, func_name, file_path, results
            )


# ---------------------------------------------------------------------------
# Function walker — extracted from closure to module level
# ---------------------------------------------------------------------------


def _walk_functions_in_tree(
    root: Any,
    func_def_types: set[str],
    block_type: str,
    source: str,
    language: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> int:
    """Walk the AST and analyze every function body for unreachable code.

    Returns the count of functions analyzed.

    This was previously an inner closure inside ``analyze_file_unreachable``,
    which caused nesting depth > 6. Extracting it to module level eliminates
    that structural issue.
    """
    counter = [0]  # mutable int — avoids nonlocal in a closure

    def _visit(node: Any) -> None:
        if not hasattr(node, "type"):
            return
        if node.type in func_def_types:
            counter[0] += 1
            func_name = _get_function_name(node, source, language)
            _analyze_function_body(
                node, block_type, source, language, func_name, file_path, results
            )
            # Recurse into the function's body to find nested function definitions.
            for child in getattr(node, "children", []):
                _visit(child)
            return
        if node.type in _CLASS_DEF_TYPES_SET:
            for child in getattr(node, "children", []):
                _visit(child)
            return
        for child in getattr(node, "children", []):
            _visit(child)

    _visit(root)
    return counter[0]


def _analyze_function_body(
    func_node: Any,
    block_type: str,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    """Analyze the body of a single function node."""
    body = func_node.child_by_field_name("body")
    if body is None:
        return
    if body.type == block_type:
        _analyze_block_unreachable(
            body, source, language, func_name, file_path, results
        )
        return
    for child in getattr(body, "children", []):
        if child.type == block_type:
            _analyze_block_unreachable(
                child, source, language, func_name, file_path, results
            )


# ---------------------------------------------------------------------------
# File-level analysis
# ---------------------------------------------------------------------------


def _read_file_bytes(file_path: str) -> bytes | None:
    """Read file bytes; return None on I/O error."""
    try:
        with open(file_path, "rb") as f:
            return f.read()
    except OSError as exc:
        logger.debug("Cannot read %s: %s", file_path, exc)
        return None


def _parse_tree(file_path: str, language: str, source_bytes: bytes) -> Any:
    """Parse source bytes with tree-sitter; return root node or None on failure."""
    parser = Parser()
    result = parser.parse_file(file_path, language)
    if not result.success or result.tree is None:
        return None
    return result.tree.root_node


def analyze_file_unreachable(
    file_path: str,
    language: str | None = None,
) -> UnreachableCodeResult:
    """Analyze a single file for unreachable code paths."""
    if language is None:
        language = _language_from_ext(file_path)  # pass full path, not just ext
    if language is None:
        return UnreachableCodeResult(file_path=file_path, language="unknown", errors=1)

    source_bytes = _read_file_bytes(file_path)
    if source_bytes is None:
        return UnreachableCodeResult(file_path=file_path, language=language, errors=1)

    source = source_bytes.decode("utf-8", errors="replace")
    root = _parse_tree(file_path, language, source_bytes)
    if root is None:
        return UnreachableCodeResult(file_path=file_path, language=language, errors=1)

    func_def_types = _FUNC_DEF_TYPES.get(language, set())
    block_type = _BLOCK_TYPES.get(language, "block")
    results: list[UnreachableBlock] = []

    functions_analyzed = _walk_functions_in_tree(
        root, func_def_types, block_type, source, language, file_path, results
    )

    return UnreachableCodeResult(
        file_path=file_path,
        language=language,
        unreachable_blocks=results,
        functions_analyzed=functions_analyzed,
    )


def _get_function_name(node: Any, source: str, language: str) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node, source)
    if language in ("javascript", "typescript"):
        return _infer_js_function_name(node, source)
    return "<anonymous>"


def _infer_js_function_name(node: Any, source: str) -> str:
    """Try to infer name for anonymous JS/TS functions from their parent."""
    parent = node.parent
    if parent is None:
        return "<anonymous>"
    key_node = parent.child_by_field_name("key")
    if key_node is not None:
        return _node_text(key_node, source)
    prop = parent.child_by_field_name("property")
    if prop is not None:
        return _node_text(prop, source)
    return "<anonymous>"


# ---------------------------------------------------------------------------
# Project-level scanner
# ---------------------------------------------------------------------------


def analyze_project_unreachable(
    project_root: str,
    *,
    include_test_files: bool = False,
    max_files: int = 500,
) -> list[UnreachableCodeResult]:
    """Scan a project for unreachable code paths."""
    import re

    _test_pattern = re.compile(
        r"(?:^test_|_test\.|\.test\.|\.spec\.|_spec\.|tests?/|Test\.py$)",
        re.IGNORECASE,
    )

    results: list[UnreachableCodeResult] = []
    count = 0

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in sorted(filenames):
            if count >= max_files:
                break
            full = os.path.join(dirpath, fname)
            lang = _language_from_ext(full)
            if lang is None:
                continue
            rel = os.path.relpath(full, project_root)
            rel_posix = rel.replace(os.sep, "/")  # normalize for cross-platform regex
            if not include_test_files and _test_pattern.search(rel_posix):
                continue
            result = analyze_file_unreachable(full, language=lang)
            if result.unreachable_blocks or result.errors:
                results.append(result)
            count += 1

    return results


# ---------------------------------------------------------------------------
# Class-definition type set (populated lazily from dead_code_analyzer)
# ---------------------------------------------------------------------------

_CLASS_DEF_TYPES_SET: set[str] = set()
try:
    from .dead_code_analyzer import _CLASS_DEF_TYPES

    for _s in _CLASS_DEF_TYPES.values():
        _CLASS_DEF_TYPES_SET.update(_s)
except Exception:
    pass
